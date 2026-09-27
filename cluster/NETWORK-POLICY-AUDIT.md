# Network policy review — 2026-09-27

The 26 new enforcing Cilium policies in this change are local proposals, not
deployed policies. App-template workloads use `values.networkpolicies`.

## Runtime evidence

Reviewed kguardian per-pod traffic for the proposed workloads and additional
candidates, alongside the manifests and live pod/service labels and ports.
Observations support API-only access for the PostgreSQL operator, user-init
controller and NFS provisioner; database/HTTPS access for Authentik; API/HTTPS
access for cert-manager; and the vmalert-to-vmsingle/Alertmanager connections.
Configured dependencies absent from the sample are retained, including
cert-manager's recursive DNS servers, Zigbee2MQTT's coordinator and model/plugin
downloads. NFS volume mounts are performed by the node.

Kguardian has no recorded flows for the current Grafana, Immich ML, Karakeep
Meilisearch, Snapshot Controller and PostgreSQL dump pods. Their proposed rules
remain configuration-derived, not runtime-validated. The VictoriaLogs history
also contains discovery traffic and port 8123 inconsistent with that workload;
those records were not promoted into allow rules.

Host-network peer attribution is ambiguous: node IPs appear under unrelated
Ceph/Cilium pod names. Confirmed the API endpoints as the three node IPs on
6443 and the probe sources as their CiliumInternalIP addresses.

## Non-enforcing audit

Installed 26 `AuditNetworkPolicy` objects named `netpol-review-*`, labelled
`networking.home.arpa/audit=netpol-review`. These are temporary review resources,
not part of Flux reconciliation. The submitted bundle is
`/tmp/homelab-netpol-audits.json` in the editing environment.

The audit engine accepts standard NetworkPolicy, so these are L3/L4 models of
the Cilium proposals, including shared DNS, Envoy and SSO allowances. Entity
rules are modelled using current node addresses, API service records include
the pre-DNAT address/port, and node probe traffic is exempted in the model.
They do not validate Cilium L7/SNI behavior, named-port enforcement or datapath
identity translation. Audit success would not establish those properties.

At review time all audit statuses were empty and no verdicts had been returned.
The broker has EVALUATOR_URL configured and the evaluator reports synced caches.
Empty verdicts are not evidence that the policies pass; runtime audit remains
pending. Review evaluation counts and WouldDeny results before enforcement.

## Validation

All 26 Cilium policies passed Kubernetes server-side dry-run validation.
The affected app-template releases rendered successfully and their policy
selectors and Envoy named ports were checked. Flate changed-tree validation
passed with 84 passed and 10 unchanged/skipped; the existing PostgreSQL operator
warning about the unused `monitoring` value remains.

A final rerun after adding this report failed on sandbox DNS access to the
Crunchy and pgmqtt chart registries. The retry with network access stalled for
over 38 minutes and was stopped. The passing run above covered the final policy
manifests; only this report was added afterwards.
