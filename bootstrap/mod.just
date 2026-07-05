set shell := ['bash', '-euo', 'pipefail', '-c']

kubernetes_dir := justfile_dir()

[private]
default:
    @just --list

# Extract CustomResourceDefinitions from Helm charts and apply them to the cluster.
# Runs before Flux reconciliation to ensure CRDs exist before any Kustomization
# that references them.
[doc('Extract and apply CRDs from Helm charts')]
crds:
    helmfile -f "{{ kubernetes_dir }}/bootstrap/helmfile.d/00-crds.yaml" template -q \
        | yq 'select(.kind == "CustomResourceDefinition")' \
        | kubectl apply --server-side --field-manager bootstrap --force-conflicts -f -

# TODO: migrate remaining bootstrap stages from Flux to helmfile:
#   - flux bootstrap (flux-operator, flux-instance)
#   - cilium (CNI + BGP config)
#   - coredns
#   - spegel
#   - cert-manager + webhook
#   - external-secrets + onepassword-connect
#   See: https://raw.githubusercontent.com/bjw-s-labs/home-ops/refs/heads/main/kubernetes/bootstrap/mod.just
#   See: https://raw.githubusercontent.com/onedr0p/home-ops/refs/heads/main/bootstrap/mod.just
