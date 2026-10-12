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

## Postgres sizing before migration

Both Crunchy clusters currently run three Postgres instances, one per
node. Their Ceph PVC requests are 35 GiB for `default-cluster` and 30 GiB
for `immich-cluster`: 65 GiB per node, 195 GiB total. The separate
100 GiB default-cluster backup repository uses NFS and is not part of
the local database capacity requirement.

Read-only `df` measurements on 2026-10-12 showed much lower actual usage:

| Node | Default cluster | Immich cluster | Combined |
| --- | ---: | ---: | ---: |
| cw01 | 12.31 GiB | 2.18 GiB | 14.50 GiB |
| cw02 | 1.72 GiB | 2.12 GiB | 3.84 GiB |
| cw03 | 1.91 GiB | 2.17 GiB | 4.09 GiB |

All six instances used about 22.42 GiB in total. The large cw01 instance
contained 11.59 GiB of WAL; its main database directory was only about
0.64 GiB. Capacity planning must include WAL retention, growth, snapshots,
and any temporary migration volumes, rather than just SQL database sizes.

The 32 GiB disks fit today's physical usage, but not the current PVC
requests under the conservative provisioning limits. A migration would
need smaller replacement PVCs (existing PVCs cannot be shrunk), or larger
disks. Retaining the current 35+30 GiB claims needs more than 65 GiB per
node after pool overhead; 96 GiB per node leaves useful headroom.
This PR does not change Postgres instance sets, PVCs, or storage classes.

Upstream: [requirements](https://miroir.home-operations.com/requirements/),
[quickstart](https://miroir.home-operations.com/quickstart/), and
[configuration](https://miroir.home-operations.com/configuration/).
