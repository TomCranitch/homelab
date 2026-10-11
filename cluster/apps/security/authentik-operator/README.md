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
existing network policy. Metrics are disabled.

The Kubernetes API allowance is required because this pod's egress is denied by
default and no shared policy grants it API access. The pod uses the ordinary
`kubernetes.default.svc` Service, whose backend port is normally 6443.
[PR #1897](https://github.com/TomCranitch/homelab/pull/1897) configures Cilium's
own host-networked client to use node-local KubePrism at `localhost:7445`; it
does not redirect this operator's Kubernetes client to pod-local port 7445.
Check the live Kubernetes Service endpoints when validating connectivity.

## Rollout

The Flux Kustomizations are enabled. The account's API token is stored in the
SOPS-managed Secret. Application manifests preserve the live provider settings
and use `IfMatch` to refuse adoption if their declared fields differ. Existing
workload configuration and credential Secrets are unchanged.

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

Flows use readable slugs, scopes use `scopeName`, and the signing certificate
uses its name. Live lookup confirmed the scope names resolve uniquely. Empty
display fields and default-valued options are omitted; optional omitted fields
are left unmanaged on existing objects. The five-minute access-token lifetime
and existing grant types remain explicit because they differ from server
creation defaults. Helm values likewise rely on the pinned chart's defaults
for replicas, leader election, resync, RBAC scope and CRD retention.

`IfMatch` is the initial adoption check, not a dry run of access rules. Once
adoption succeeds the operator enforces the declared fields, adopts matching
bindings, and prunes undeclared ones. Read all adoption differences before
changing the manifest; do not switch to `Force` to bypass them.

Removing the CR with `deletionPolicy: Delete` deletes its managed Authentik
application, provider and bindings. The independent SOPS-managed Secret is not
owned by the CR and stays while its manifest remains in Git. For rollback,
release ownership deliberately; do not simply delete the CR. Remove managed
CRs and let their finalizers complete before uninstalling the operator.

## Other deployed applications

Each application uses the existing `ks.yaml`, `app/` and `authentik/` pattern,
including Echo, Gateway, Home Assistant, Immich, Karakeep, Linkding, Mealie,
ownCloud and Windmill. Root `ks.yaml` defines separate workload and
`<slug>-authentik` Flux Kustomizations. Workload Kustomizations decrypt their
existing SOPS files and use the same cluster substitutions as their former
parent. Authentik Kustomizations depend on the operator; Karakeep also depends
on `karakeep`, and Gateway on `envoy`, to ensure their credential Secrets exist.
Workloads do not depend on Authentik adoption. All application health checks
require current-generation readiness.

Gateway's CR is in `ingress` to reference the existing `envoy-oidc-secret`.
Karakeep's CR is in `default` and references the existing `karakeep` Secret's
`OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` keys. Both credential pairs were
compared against the live providers without printing their values.

Immich, Windmill, Mealie and ownCloud omit `credentials`. The operator therefore
does not read, create, export or rotate their client credentials. They remain
under their existing manual/application configuration. This does not provide
credential recovery: if a provider is deleted and recreated, its newly generated
credentials must be restored manually before its existing client can log in.

Provider differences are intentional: Gateway and Windmill use implicit consent;
the other applications use explicit consent. Gateway has a regex redirect URI.
Mealie and ownCloud are public clients, with `offline_access` and `ocis_role`
scope mappings respectively. Echo, Home Assistant and Linkding use single-host
forward-auth providers already attached to the embedded outpost; their additional
proxy scope mappings are outside the operator's supported managed fields.
No reverse-proxy authentication configuration is changed here.

All nine applications have no application access bindings. Their manifests use
`public: true` and `prune: true`, preserving that state. Login flows still apply.
Ownership and deletion use the same semantics as Grafana.

Paperless, Radicale, the legacy VMAgent proxy and Domain authorization remain
manual cleanup candidates. The VMAgent route now uses the shared Gateway OIDC
provider; no deployed route references the domain forward-auth provider.
ownCloud Desktop also remains manual: it is a companion client, not a separate
deployed server, and should only be deleted if no desktop clients use it.
The unattached Owncloud Android provider is another client to review, not an
application manifest to adopt. Nothing in this change deletes these objects.

## Flux ownership handoff

The eight newly separated workload Kustomizations take ownership from
`flux-system/apps`. Existing resource names, namespaces and rendered workload
configuration remain unchanged. Envoy and Grafana already have child
Kustomizations and do not need a workload ownership transfer.

1. Merge [the prune-protection PR](https://github.com/TomCranitch/homelab/pull/1906)
   separately and confirm `flux-system/apps.spec.prune` is `false` in-cluster.
2. Merge the layout/adoption migration only after that protection is live.
3. Verify each child Kustomization has reconciled the migration revision, has
   inventoried its workload resources, and those resources carry the child's
   `kustomize.toolkit.fluxcd.io/name` and namespace labels. Confirm the parent
   `apps` inventory no longer contains the transferred resources. Investigate
   existing workload readiness failures separately from the ownership check.
4. Restore `apps.spec.prune: true` in a follow-up after those checks pass.

Do not combine protection and transfer into one first rollout: both controllers
watch the source, so the parent could process the new tree before its pruning
setting is updated. This follows the
[Flux migration procedure](https://fluxcd.io/flux/faq/#how-can-i-safely-move-resources-from-one-dir-to-another).

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
