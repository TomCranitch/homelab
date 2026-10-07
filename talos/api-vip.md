# Kubernetes API VIP rollout

Reserve `192.168.29.169` outside the DHCP pool. Talos elects one control-plane
node to own this LAN address; the other nodes take over when the owner becomes
unavailable. All three nodes must share the same layer-2 network. This requires
etcd quorum, so keep using direct node IPs for Talos management and recovery.

The Kubernetes endpoint stays `https://cranitch.k8s:6443`. Change its DNS only
after the VIP works and moves between nodes. The extra API certificate SAN
allows testing the VIP directly without disabling TLS verification.

## Check the live configuration

Run these commands from `talos/`, after the Cilium KubePrism change has rolled
out successfully:

```sh
talosctl --talosconfig clusterconfig/talosconfig \
  -e 192.168.29.170 -n 192.168.29.170,192.168.29.171,192.168.29.172 \
  get addresses -o yaml
kubectl get nodes
kubectl -n kube-system rollout status daemonset/cilium
```

Confirm the LAN addresses use `bond0` on cw01/cw02 and `ens18` on cw03. If they
do not, correct the respective `Layer2VIPConfig.link` in `talconfig.yaml` before
proceeding. Verify `.169` is unused in DHCP reservations, DNS and the router's
address table; an unanswered ping alone does not establish that an IP is free.

## Generate and apply one node at a time

Use a Talhelper version that supports Talos 1.13 multidocument network configs
(this change was generated with Talhelper 3.1.17 and validated with Talos
1.13.11). Generate using the existing cluster secrets, never new secrets:

```sh
talhelper genconfig
talosctl --talosconfig clusterconfig/talosconfig \
  -e 192.168.29.170 -n 192.168.29.170 apply-config \
  --file clusterconfig/homeprod-homeprod-cw01.yaml --mode=no-reboot --dry-run
```

Inspect the diff locally. Expect the VIP document and API certificate SAN;
investigate unrelated changes before applying. Generated files contain cluster
credentials: do not commit or paste them.

```sh
talosctl --talosconfig clusterconfig/talosconfig \
  -e 192.168.29.170 -n 192.168.29.170 apply-config \
  --file clusterconfig/homeprod-homeprod-cw01.yaml --mode=no-reboot
kubectl --server=https://192.168.29.169:6443 get --raw=/readyz
kubectl get nodes
kubectl -n kube-system rollout status daemonset/cilium
```

Wait for successful API readiness, all nodes Ready and Cilium healthy. Repeat
the dry-run, apply and checks for each remaining node individually:

| Node | `-e` / `-n` address | Generated file |
| --- | --- | --- |
| cw02 | `192.168.29.171` | `clusterconfig/homeprod-homeprod-cw02.yaml` |
| cw03 | `192.168.29.172` | `clusterconfig/homeprod-homeprod-cw03.yaml` |

Do not force a reboot if `--mode=no-reboot` rejects a change; investigate the
reported difference first.

## Test ownership transfer, then change DNS

After all three nodes have the VIP configuration, run the address query above
again to identify the node that currently owns `.169`. Test transfer without
rebooting workloads by temporarily deleting only its VIP document:

```sh
cat > /tmp/remove-api-vip.yaml <<'EOF'
apiVersion: v1alpha1
kind: Layer2VIPConfig
name: 192.168.29.169
$patch: delete
EOF

# Replace this value with the current owner, not necessarily cw01.
VIP_OWNER=192.168.29.170
talosctl --talosconfig clusterconfig/talosconfig \
  -e "$VIP_OWNER" -n "$VIP_OWNER" patch machineconfig \
  --patch @/tmp/remove-api-vip.yaml --mode=no-reboot --dry-run
talosctl --talosconfig clusterconfig/talosconfig \
  -e "$VIP_OWNER" -n "$VIP_OWNER" patch machineconfig \
  --patch @/tmp/remove-api-vip.yaml --mode=no-reboot
kubectl --server=https://192.168.29.169:6443 get --raw=/readyz
```

Allow for election and ARP convergence, then repeat the readiness and address
checks. Confirm `.169` has moved to another node. Restore the removed document
by applying the original generated file for `VIP_OWNER` with `--mode=no-reboot`.
Check API readiness and node/Cilium health again. This verifies configuration
transfer; measure abrupt host-failure recovery later during a planned outage
test, once application and storage HA changes are complete. Existing API
connections may need to reconnect during failover.

Once those checks pass, replace the three existing `cranitch.k8s` A records with
one A record for `192.168.29.169`. Check any AAAA records too: this change adds
only an IPv4 VIP. After DNS caches expire, verify normal `kubectl get nodes` and
`kubectl get --raw=/readyz` work through the hostname.

## Roll back

If DNS was changed, restore its previous records first and verify the hostname
works. Revert the VIP entries in `talconfig.yaml`, regenerate with the existing
secrets, inspect dry-runs and apply to each node individually with
`--mode=no-reboot`. Keep Talos management pointed at direct node IPs throughout.

Reference: [Talos virtual IP documentation](https://docs.siderolabs.com/talos/v1.13/networking/vip).
