# CoreDNS availability

Talos bootstraps the `kube-system/coredns` Deployment. The Deployment manifest here
is a partial server-side apply overlay for that existing object: Flux owns the
replica count and required hostname anti-affinity, while the image, containers,
selector, ServiceAccount, Corefile, and other bootstrap resources stay outside
this overlay.

Two replicas require two eligible nodes. Required anti-affinity keeps the pods
on different hosts; if only one host is available, the second pod stays Pending.
The PodDisruptionBudget requires one healthy pod during voluntary evictions,
including node drains. It cannot prevent outages caused by node failures, and
Deployment rollouts do not use the eviction API.

The `ssa: Merge` annotation preserves fields owned by other managers and skips
Flux's managed-field cleanup. The `prune: disabled` annotation protects the
bootstrap Deployment if the overlay is removed or pruning is enabled later.
Removing this directory does not roll back the applied Deployment fields; remove
the required anti-affinity and adjust replicas explicitly when retiring it.

This overlay cannot create CoreDNS from scratch because it deliberately omits
the Deployment selector and containers. Talos must create CoreDNS first. Talos
1.13.11 skips bootstrap manifests already in its inventory or already present
in Kubernetes; it does not continuously overwrite this overlay.

Before rollout, verify the existing Deployment labels and run a server-side dry
run against the target cluster:

```sh
kubectl -n kube-system get deployment coredns -o yaml
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
kubectl apply --server-side --dry-run=server --force-conflicts \
  --field-manager=kustomize-controller -f cluster/core/coredns/deployment.yaml
kubectl apply --server-side --dry-run=server \
  -f cluster/core/coredns/poddisruptionbudget.yaml
```

After Flux reconciliation, check the rollout, host placement, and disruption
budget. Two Ready pods on different nodes should allow one disruption:

```sh
kubectl -n kube-system rollout status deployment/coredns
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
kubectl -n kube-system get pdb coredns
```

References:

- [Flux 1.7.3 Merge apply policy](https://github.com/fluxcd/kustomize-controller/blob/v1.7.3/docs/spec/v1/kustomizations.md#merge)
- [Flux 1.7.3 Merge cleanup exclusion](https://github.com/fluxcd/kustomize-controller/blob/v1.7.3/internal/controller/kustomization_controller.go#L874-L890)
- [Flux 1.7.3 pruning exclusions](https://github.com/fluxcd/kustomize-controller/blob/v1.7.3/internal/controller/kustomization_controller.go#L1061-L1068)
- [Talos 1.13.11 bootstrap apply behavior](https://github.com/siderolabs/talos/blob/v1.13.11/internal/app/machined/pkg/controllers/k8s/manifest_apply.go#L335-L347)
