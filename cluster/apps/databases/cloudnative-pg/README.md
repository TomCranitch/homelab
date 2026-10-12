# Shared CloudNativePG

The `postgres` cluster in `default` provides separate application databases and roles.
PostgreSQL 18.6 runs on three instances, one per physical host, with required
hostname anti-affinity. Each instance uses a 16 GiB `miroir-local` PVC.
PostgreSQL handles replication; Miroir stores one local copy per PVC.
Synchronous replication uses one standby with `preferred` durability.

## Extensions

The pinned standard image supplies the `en_US.utf-8` locale, pgvector 0.8.6
and pgAudit 18.0. VectorChord 1.1.1 uses a pinned image-volume overlay.
Audit logging is disabled with `pgaudit.log: none`.

## Backups

Barman Cloud archives WAL to B2 at `s3://homeprod-crunchy/cnpg/`, with a
five-minute `archive_timeout`. Full backups run Tuesday at 03:15 UTC
and retain a 120-day recovery window.
A daily SQL dump uses an 8 GiB VolSync-protected PVC.
