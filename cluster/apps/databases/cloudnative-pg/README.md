# PGO to shared CloudNativePG

This directory implements the target cluster and a staged migration. Initial
merge installs CNPG and the Barman plugin; **it does not move application traffic**.
`postgres-cluster` and `postgres-databases` start suspended. PGO remains deployed,
with pruning disabled and its database resources explicitly protected.

The target is PostgreSQL 18.6 on three Ceph-backed instances, with required node
anti-affinity and one synchronous standby (`preferred` durability). Each app keeps
its own database and role. pgvector, VectorChord and pgAudit are immutable image
volume extensions; only Immich declares the vector extensions in its database.
pgAudit is available because Crunchy source dumps can contain that extension.
The official standard operand supplies `en_US.utf-8`, used by all source databases;
the minimal image lacks the full locale set. The three overlays remain explicitly
pinned. `hass` and `paperless`, found in the live cluster, are also retained along
with their owners and imported password hashes; they have no current app consumers.

All phases must be committed to feature branches and delivered through PRs.
The scripts never commit, push, merge, apply Kubernetes resources or stop apps.
This PR already includes the encrypted credential preparation and a nonsecret
inventory captured on 2026-10-11. Refresh the inventory before final migration;
rerunning preparation refuses to replace the existing encrypted credentials.

## Prepare credentials and review inventory

From the repository root, with an explicitly selected privileged kubeconfig:

```sh
python cluster/apps/databases/cloudnative-pg/migration/prepare.py \
  --kubeconfig /home/tom/.kube/config --inventory-only
python cluster/apps/databases/cloudnative-pg/migration/prepare.py \
  --kubeconfig /home/tom/.kube/config
```

Use `--kubectl /absolute/path/to/kubectl` to select the trusted executable.
The script executes read-only SQL through `kubectl exec`, reads exactly the
PGO app/admin Secrets and `crunchy-backup-secret`, preserves app passwords,
generates a new CNPG admin password, and writes **only encrypted** secret files.
It uses the public age recipient from this repo and needs no private age key.
Plaintext credentials are never printed or written to disk. Existing encrypted
files are not overwritten. The credentials Kustomization starts empty until
preparation succeeds; never enable bootstrap with an empty credentials directory.

It records nonsecret metadata in `migration/inventory.json`, adapts the import
role list to the actual source, and preserves app role attributes/memberships.
Review these changes before committing. Check additional grant/owner references,
custom role memberships, locale availability, and every installed extension
against `pg_available_extensions` on the destination. Legacy `vectors` is excluded
only from the Immich export after a recursive dependency check proves it unused;
any remaining external dependency blocks preparation and import. The source stays
unchanged. Do not copy source operator/replication
users into the CNPG-managed role manifests.

The 35Gi data PVC default provides headroom over the measured ~1.4Gi of databases;
confirm actual sizes and available Ceph space, including Ceph's replication
factor, all three new PVCs, the 5Gi migration scratch PVC and rehearsal storage.
The dump PVC grows to 8Gi for the combined dump, its temporary copy and the
retained Immich dump; confirm actual text dump sizes still fit before the outage.
Check available node memory for the
three 1Gi requests/4Gi limits and for transient index building.

## Rehearse before the final outage

Use disposable copies of the source clusters recovered from pgBackRest backups
and a disposable destination. Adapt source endpoints/Secrets, destination names,
namespace selectors and the import Job's target credential to those copies.
Do not switch live app secret prefixes during rehearsal.

The destination must be freshly bootstrapped for every final transfer: the
`initdb.import` stanza executes only on initial creation and does not synchronize
later writes. The rehearsal environment is deliberately outside the Flux resource
graph. Never treat an earlier rehearsal snapshot as the final database.

Measure import/index-building time and validate PG16-to-PG18 collations, schemas,
ownership, grants, row counts, sequence positions and Immich embeddings. Check
all required libraries on every instance. A fresh restore creates new vector
indexes; verify smart search and face search without recomputing embeddings.
Test all seven apps against their own copied databases, including Windmill role
memberships/BYPASSRLS, Authentik TLS/login and MQTT clients.

## Final import and adoption

1. Reconcile the credential PR first. Confirm all source and destination Secrets.
2. Suspend the app Flux Kustomizations and HelmReleases, pause relevant scheduled
   jobs, and stop **all database writers**, including Authentik workers, Windmill
   workers/schedulers, pgmqtt and Immich. Root Flux suspension alone does not stop
   workloads or child Helm controllers. Record replicas/suspend settings to restore.
3. Verify no application sessions remain. Pause automatic Talos/Kubernetes upgrades
   during the outage. Keep PGO operators and PostgreSQL running.
4. Prepare and deliver the bootstrap change through a PR:

   ```sh
   python cluster/apps/databases/cloudnative-pg/migration/stage.py bootstrap --writes-paused
   ```

   After that PR reconciles, `postgres-cluster` imports the eight shared databases
   from `default-cluster`. Keep `postgres-databases` suspended to avoid ownership
   and extension reconciliation racing with the imports. Wait for CNPG readiness.
5. Explicitly apply the second-source import:

   ```sh
   kubectl --kubeconfig /home/tom/.kube/config apply -k cluster/apps/databases/cloudnative-pg/migration
   kubectl --kubeconfig /home/tom/.kube/config -n default wait \
     --for=condition=complete job/postgres-import-immich --timeout=4h
   ```

   The Job checks that Immich has no app sessions and that the destination database
   does not already exist. It imports through PostgreSQL 18 dump/restore tools,
   preserves the app password, fails on restore errors and never automatically
   overwrites a partial import. On failure keep writers paused, inspect diagnostics,
   and choose recovery/retry on the **new destination only**. Never delete source data.
6. Verify all nine databases and their roles before adopting them:

   ```sh
   python cluster/apps/databases/cloudnative-pg/migration/stage.py adopt --validated
   ```

   Review and deliver this change through a PR. Wait for each `Database` and
   `DatabaseRole` to report `status.applied: true` at its current generation.

## Backup verification, cutover and retirement

Barman writes full physical base backups and continuously archives WAL to the
existing B2 bucket under a new `cnpg/` prefix. The prefix must be writable by the
existing key. It keeps a 120-day recovery window and schedules weekly full backups
Tuesday 03:15 UTC, with an immediate initial backup. Five-minute `archive_timeout`
limits normal archiving delay; failed uploads can extend it. Verify WAL metrics,
the initial successful backup and a restore before enabling writes.

`recovery/` is an explicitly applied, one-instance restore example with the exact
same base/overlay images. It uses the existing ObjectStore and archive server
`postgres`; it has **no WAL archiver** and cannot overwrite the source archive.
Adjust `recoveryTarget.targetTime` for PITR. Check restored roles, extensions and
data, and then test restoring the SQL dump into a separate disposable cluster.
Never restore SQL dumps indiscriminately over CNPG's existing reserved roles.

After both imports, application checks and recovery checks pass:

```sh
python cluster/apps/databases/cloudnative-pg/migration/stage.py cutover --validated
```

This prepares a PR that switches both app secret prefixes to `postgres`, uses
`postgres-admin` for dumps, and replaces both PGO upgrade checks with three-instance
CNPG readiness. Reconcile it while writers remain stopped, then restore recorded
app replicas and reconciliation settings. Validate Authentik first, then the other
apps, and test a controlled CNPG switchover and reconnection.

The nightly CronJob continues using the existing VolSync-protected PVC. During
staging it dumps both PGO clusters; after cutover the identical connection Secrets
make it dump the consolidated cluster once. Temporary files are atomically renamed
only after successful dumps. The old Immich dump remains available for rollback.

Keep PGO, its PVCs, NFS repository and B2 archives throughout validation. Before
CNPG receives writes, rollback is restarting apps against their unchanged PGO
connections. Afterwards rollback requires reconciling CNPG writes back into PGO;
simply changing the prefixes would lose those writes.

Retirement is a subsequent explicit PR after the new backups and production
behavior are verified: remove PGO/user-init/chart references, legacy network
selectors and migration credentials, and detach protected PGO resources. Inspect
the exact old PVC/resource names before any manual deletion. Prune protection is
intentional: removal from Git alone must not erase rollback data. Preserve the
old backup archives for their retention period. Delete the completed migration
Job/temporary policy only after its logs and validation evidence are retained.

## References

- [CNPG extension image volumes](https://cloudnative-pg.io/docs/1.30/imagevolume_extensions/)
- [CNPG database import](https://github.com/cloudnative-pg/cloudnative-pg/blob/release-1.30/docs/src/database_import.md)
- [Barman Cloud plugin](https://cloudnative-pg.io/plugin-barman-cloud/docs/intro/)
- [Immich chart overlay example](https://github.com/immich-app/immich-charts/blob/main/local/cloudnative-pg.yaml)
