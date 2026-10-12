# Miroir local storage

Miroir 0.12.5 provides the opt-in `miroir-local` StorageClass: one local
copy, ext4, delayed binding (`WaitForFirstConsumer`), and online expansion.
Ceph remains the default; this deployment does not migrate existing PVCs.
Volumes stay on their storage node and become unavailable while that node
is down. Losing its disk loses the local data.

Each of `homeprod-cw01`, `homeprod-cw02`, and `homeprod-cw03` has a dedicated
32 GiB disk at `/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2`.
Read-only Talos checks on 2026-10-12 confirmed this disk was `/dev/sdc`
with no detected filesystem or partition table on all three nodes.
Miroir initializes an LVM-thin pool on this disk when the topology is
reconciled. The OS disk is `drive-scsi0`; the Ceph OSD is `drive-scsi1`.
Talhelper now pins installation to `drive-scsi0`, since the previous
`<= 100GB` selector also matched the new Miroir disk.

The stock Talos 1.13 kernel provides `dm_thin_pool`; no DRBD or ZFS extension
is needed for one-copy LVM volumes. Pools have slightly less than 32 GiB
usable capacity after metadata. Provisioning uses `overcommitRatio: 1`
and `freeSpaceRatio: 1`; CSI storage-capacity tracking helps the scheduler
select a node with room. Snapshots also consume pool space, so check usage
before sizing volumes or retaining snapshots.

## Reconciliation and rollout

The `miroir` Flux Kustomization installs the OCI chart and waits for its
HelmRelease. That release depends on the existing snapshot-controller,
which supplies the snapshot CRDs. `miroir-storage` waits for `miroir`, then
applies the three MiroirNodes, StorageClass, and VolumeSnapshotClass.
The privileged namespace is required for the per-node storage agent.
MiroirNodes are protected from automatic Flux pruning; decommissioning
storage nodes remains an explicit operation.

This PR only prepares configuration. Before merging, recheck the three
`drive-scsi2` disks are still empty and dedicated to Miroir. Apply the
Talhelper install-disk change through the normal Talos configuration
workflow before a future reinstall; a Git merge does not itself apply
Talos machine configuration.

After merge and Flux reconciliation:

```sh
kubectl -n flux-system get kustomizations miroir miroir-storage
kubectl -n miroir-system get helmrelease miroir
kubectl get miroirnodes
kubectl get storageclass miroir-local
kubectl get volumesnapshotclass miroir-local
```

For a first smoke test, create a small PVC with
`storageClassName: miroir-local` and a consuming pod. An unconsumed PVC
staying Pending is expected with delayed binding. Verify write/read,
snapshot/restore, and expansion before moving an application. The
snapshot class is also `miroir-local`; snapshots stay on the same local
disk and are not off-node backups.

Upstream: [requirements](https://miroir.home-operations.com/requirements/),
[quickstart](https://miroir.home-operations.com/quickstart/), and
[configuration](https://miroir.home-operations.com/configuration/).
