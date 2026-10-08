# Authentik operator

The operator is pinned to `2026.8.1` for Authentik `2026.8.x` and runs in
`default` under the existing `gvisor` RuntimeClass. It uses ownership role
`authentik-operator-homelab` and reconciles every ten minutes.

The Helm post-render patches preserve the upstream container security settings
and remove permission to create Kubernetes Secrets. Secret access is limited to
`get`, `list`, and `watch`; the chart's Secret rule is checked before patching,
so a changed rule layout fails rendering instead of silently restoring writes.
The operator still writes application/provider configuration in Authentik.

Cilium policies allow Kubernetes API access, direct access to the Authentik
server's HTTP port, and node health probes. The existing cluster-wide DNS policy
provides DNS access. The matching Authentik server ingress allowance is in its
existing network policy. Metrics are disabled for the pilot.

The Kubernetes API allowance is required because this pod's egress is denied by
default and no shared policy grants it API access. The pod uses the ordinary
`kubernetes.default.svc` Service, whose backend port is normally 6443.
[PR #1897](https://github.com/TomCranitch/homelab/pull/1897) configures Cilium's
own host-networked client to use node-local KubePrism at `localhost:7445`; it
does not redirect this operator's Kubernetes client to pod-local port 7445.
Check the live Kubernetes Service endpoints when validating connectivity.

## Rollout

Both Flux Kustomizations are enabled. The account's API token is stored in the
SOPS-managed Secret. Grafana's CR was generated from live inventory, including
verification that the existing SOPS credentials match its provider. Operator
permissions, network connectivity, adoption and login still need checking after
rollout. Grafana's configuration and existing SOPS-managed
`monitoring/grafana-env` Secret are unchanged.

1. Use the configured read-only kubeconfig for cluster verification, and
   authorized Authentik API access and a SOPS decryption identity for inventory.
2. Provision a dedicated service account and API token (`intent=api`,
   `expiring=false`), with the permissions from the
   [upstream chart README](https://github.com/SlashNephy/authentik-operator/blob/v2026.8.1/charts/chart/README.md).
   It does not need to be a superuser. The
   `guardian.view_roleobjectpermission` permission requires assignment through
   the Authentik API; it is absent from the UI permission picker.
3. The SOPS-encrypted `app/secret.sops.yaml` defines Secret
   `default/authentik-operator-token`, key `token`, using this repository's age
   recipient, and is included in `app/kustomization.yaml`. The operator's Flux
   Kustomization is enabled; verify its API permissions and connectivity after
   reconciliation. Grafana adoption depends on the operator being ready.
4. Verify the inventoried Grafana CR adopts the existing application/provider
   and preserves login and access behaviour after Flux reconciliation.

Token values must not be pasted into chat, command arguments, plaintext tracked
files, or logs. Provisioning is separate from the ownership-marker role created
by the operator. Do not assign users to that ownership role.

To add the account's API token, run this from the repository root. It prompts
without echoing, passes the value through stdin, writes an encrypted Secret,
and refuses to overwrite an existing file. Encryption uses the public age
recipient in `.sops.yaml`; it does not require the private age identity.

```sh
(
  set -euo pipefail
  set -o noclobber
  IFS= read -r -s -p 'Authentik API token: ' authentik_api_token
  printf '\n'
  test -n "$authentik_api_token"
  printf '%s' "$authentik_api_token" | jq -Rs '{
    apiVersion: "v1", kind: "Secret",
    metadata: {name: "authentik-operator-token", namespace: "default"},
    type: "Opaque", stringData: {token: .}
  }' | sops --encrypt \
    --filename-override cluster/apps/security/authentik-operator/app/secret.sops.yaml \
    --input-type json --output-type yaml /dev/stdin \
    > cluster/apps/security/authentik-operator/app/secret.sops.yaml
)
```

The subshell discards the token variable when it exits. The existing encrypted
file is already referenced by `app/kustomization.yaml`; the operator will
consume it when Flux reconciles this change.

## Grafana pilot

The pilot uses the existing client ID and secret, without rotation or a Grafana
restart. Its CR and Secret both belong in `monitoring`. The separate
`grafana-authentik` Flux Kustomization depends on the operator and on
`grafana-resources`, which supplies the existing credential Secret; there is no
reverse dependency from Grafana to Authentik adoption.

The reviewed manifest is saved as
`cluster/apps/monitoring/grafana/authentik/application.yaml` and included in
that directory's `kustomization.yaml`. The pilot's health check requires
`Ready=True` for the current CR generation. Live inventory found no application
access bindings, so `public: true` preserves the current absence of group/user
restrictions; provider login flows still apply. All existing OAuth grant types,
scope mappings, flows and redirect URIs are preserved without hardening changes.

`IfMatch` is the initial adoption check, not a dry run of access rules. Once
adoption succeeds the operator enforces the declared fields, adopts matching
bindings, and prunes undeclared ones. Read all adoption differences before
changing the manifest; do not switch to `Force` to bypass them.

Removing the CR with `deletionPolicy: Delete` deletes its managed Authentik
application, provider and bindings. The independent SOPS-managed Secret is not
owned by the CR and stays while its manifest remains in Git. For rollback,
release ownership deliberately; do not simply delete the CR. Remove managed
CRs and let their finalizers complete before uninstalling the operator.

## Validation

```sh
kustomize build cluster
kustomize build cluster/charts
kustomize build cluster/apps
git diff --check
```

Render the pinned chart using the HelmRelease's actual values and its
post-render patches. Verify the Deployment and ServiceAccount references use
`default`, the pod has `runtimeClassName: gvisor`, the Secret rule only permits
reads, and CRDs have the Helm keep annotation. `flate build hr` can perform
the repository's Flux-aware chart rendering.

After rollout, also check effective service-account permissions,
pod/network health, unchanged application/provider IDs, current-generation
readiness, authorized/unauthorized Grafana login, and idempotent reconciliation.
Do not infer adoption from pod readiness alone: the chart's readiness probe is
not an Authentik connectivity or permission check.
