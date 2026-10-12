# Shared CloudNativePG

PostgreSQL 18.6 is staged for three node-local instances, each with a 16 GiB
`miroir-local` PVC and one synchronous standby. The standard image preserves
the source `en_US.utf-8` locale and supplies pgvector 0.8.6 and pgAudit 18.0.
VectorChord 1.1.1 is loaded from a pinned image-volume overlay.
`pgaudit.log: none` preserves the managed extension without enabling audit logging.

The operators and nine permanent SOPS-encrypted Secrets are already staged.
Apps retain their PGO Secret prefixes. `paperless` retains its imported password
hash; `pgmqtt` retains its current `postgres` owner. The empty `hass` database
is excluded from the migration.

## Rollout gates

| Phase | CNPG_CLUSTER_SUSPENDED | CNPG_DATABASE_APPLY_POLICY | App credentials |
|---|---|---|---|
| Initial staging | true | Ignore | PGO |
| Bootstrap/import | false | Ignore | PGO |
| Adopt after validating both imports | false | Override | PGO |
| Cutover after app and restore checks | false | Override | CNPG |

The `Database` and `DatabaseRole` resources share the cluster folder. Their Flux
SSA policy starts at `Ignore`, so Flux does not create or wait for them during
bootstrap. Changing it to `Override` enables adoption after both imports finish.
Deliver each phase through a PR; retain PGO and pause automatic upgrades during
the outage. Stop every app writer for the final imports. Bootstrap import is a
one-time snapshot and does not catch up with later source writes.

Migration tools, the inventory, import/recovery examples and temporary PGO
credentials are kept locally. Provision `pgo-default-migration` locally before
enabling bootstrap; the local Immich import also needs `pgo-immich-migration`.
These source credentials are deliberately outside the permanent Flux resources.

## Local storage rollout

Requires [storage PR #1919](https://github.com/TomCranitch/homelab/pull/1919).
`postgres-cluster` waits for the `miroir-storage` Flux Kustomization. Miroir provides
one storage copy; PostgreSQL supplies replication across the three physical hosts.
Required hostname anti-affinity keeps one database instance on each node.

Each 32 GiB disk reserves 16 GiB for PostgreSQL, leaving less than 16 GiB for
other claims, pool metadata and snapshots. WAL is part of the database PVC;
failed archiving can exhaust it despite the replication-slot retention limit.
Verify free space and volume-space alerts before cutover. This creates new PVCs;
it does not shrink, move or adopt existing PGO or rehearsal Ceph volumes.

Before enabling bootstrap, smoke-test local provisioning, writes, expansion and
node restart behavior. Repeat import, backup/restore and application checks on
local storage. Use smaller disposable local claims or Ceph for the restore test:
a second 16 GiB local claim cannot fit beside production on a 32 GiB pool.
Keep migration scratch storage on Ceph and remove disposable local claims before
the final bootstrap. Local snapshots are not off-node backups; B2 remains required.

## Backups and cutover

Barman archives WAL to B2 under `homeprod-crunchy/cnpg/`, takes weekly full backups
Tuesday 03:15 UTC and retains a 120-day recovery window. Verify a full backup,
WAL uploads, an actual restore and exported metric labels before cutover.
Both known B2 hostname forms are allowed by the network policy.
The nightly SQL dump remains VolSync-protected; its PVC is 8Gi for combined dumps
and atomic temporary copies.

After validating eight databases, app permissions, Immich search and recovery,
switch both app Secret prefixes to `postgres`, both dump Secrets to
`postgres-admin`, and upgrade health checks to CNPG readiness in the cutover PR.
Before new writes, rollback can use unchanged PGO connections. After new writes,
rollback requires transferring those writes back.

## Explicit cleanup

Permanent Secrets use `prune: false`. Temporary source Secrets are provisioned
locally and must be deleted explicitly after migration/rollback validation:

```sh
kubectl --kubeconfig /home/tom/.kube/config -n default delete secret \
  pgo-default-migration pgo-immich-migration --ignore-not-found
```

Also remove the locally applied import Job, ConfigMap and network policy.
Retire PGO/operator/chart references through a later PR, inspect exact old PVC
names before deletion, and preserve old backup archives for their retention period.
