# Ceph three-copy rollout

This change sets `ceph-blockpool` to three copies across hosts and explicitly
sets `parameters.min_size: "2"`. With all PGs `active+clean` at size 2 before
the change, every PG already has two complete copies to meet the new minimum
while the third copy backfills. Peering transitions and recovery load can
still delay I/O. Start with all three hosts healthy and keep node maintenance
out of the entire recovery window.

The October 7, 2026 preflight showed three 220 GiB OSDs, one on each host, all
`up/in`, all 33 PGs `active+clean`, and `HEALTH_OK`. The block pool had 86 GiB
stored and consumed 165 GiB with two copies. Three copies should consume about
248 GiB before additional overhead and growth, roughly 38% of the 660 GiB raw
capacity. The live nearfull/backfillfull/full thresholds were 85%/90%/95%.
These figures establish headroom for this change; recheck if application data
or disk capacity has changed.

## Before merging

Keep node upgrades, drains and reboots out of the backfill window. Confirm the
preflight still holds:

```bash
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd df tree
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd pool get ceph-blockpool size
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd pool get ceph-blockpool min_size
```

Require a fresh `HEALTH_OK`, all three OSDs `up/in`, and all PGs `active+clean`.
Confirm the expected starting pool size 2 and minimum 1. If the health or
capacity preflight has changed, resolve the difference before merging.
After merging, Flux and Rook reconcile the pool in place; no new PVCs or data
migration to another pool are needed.

## Wait for the third copy

```bash
kubectl -n rook-ceph get helmrelease rook-ceph-cluster
kubectl -n rook-ceph get cephblockpool ceph-blockpool
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd pool get ceph-blockpool size
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd pool get ceph-blockpool min_size
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd df tree
```

Size must become 3 and minimum become 2. Backfill can temporarily show degraded
or recovering PGs and `HEALTH_WARN`. Wait until **all PGs are `active+clean`,
all three OSDs are `up/in`, and Ceph reports `HEALTH_OK`**. Successful Helm or
CephBlockPool reconciliation alone does not prove backfill has completed. If
recovery stops or fullness warnings appear, inspect `ceph health detail` and
resolve the cause before continuing.

## Maintenance after recovery

Only after the operator confirms size 3, minimum 2 and the recovery checks above,
perform a one-node maintenance test using the normal drain/upgrade path
and Rook-managed disruption budgets. Verify storage remains usable; after
the node returns, wait for all OSDs and PGs to recover before another node.

With exactly three hosts, a missing host leaves two copies. The third copy
cannot be restored on a different host until the failed host returns or a
fourth storage host is added. Do not bypass PDBs or lower the minimum to force
a blocked drain.
