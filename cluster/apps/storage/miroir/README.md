# Miroir local storage

`miroir-local` provisions one-copy LVM-thin volumes with ext4,
`WaitForFirstConsumer`, and online expansion. The VolumeSnapshotClass
has the same name. Ceph remains the default storage class.

Each of `homeprod-cw01`, `homeprod-cw02`, and `homeprod-cw03` uses its
32 GiB `/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2` disk.
Miroir initializes the pool on first reconciliation; this disk must be
empty and dedicated to Miroir. Talos installation is pinned to
`drive-scsi0`; Ceph uses `drive-scsi1`.

The `miroir` Flux Kustomization installs the driver after the existing
snapshot-controller. `miroir-storage` applies the topology and storage
classes after the driver is ready. The agent requires a privileged
namespace; namespace and MiroirNode pruning are disabled.

Provisioning does not overcommit the disks. Usable capacity is less than
32 GiB per node after metadata; allow room for WAL, growth, and snapshots.
Volumes remain on their storage node and are unavailable while it is down.
Snapshots use the same disk and do not replace off-node backups.

```sh
kubectl -n flux-system get kustomizations miroir miroir-storage
kubectl -n miroir-system get helmrelease miroir
kubectl get miroirnodes
```

A PVC needs a consuming pod before it binds. Test provisioning,
read/write, snapshot/restore, and expansion before migrating workloads.

Upstream: [setup](https://miroir.home-operations.com/quickstart/) and
[configuration](https://miroir.home-operations.com/configuration/).
