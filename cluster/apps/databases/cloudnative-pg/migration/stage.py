#!/usr/bin/env python3
"""Advance repository configuration; never applies or deletes cluster objects."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "cluster/apps/databases/cloudnative-pg"
SETTINGS = ROOT / "cluster/flux/cluster-config/settings.yaml"
EXPECTED_SECRETS = [f"postgres-{app}" for app in
    ("authentik", "linkding", "mealie", "vaultwarden", "windmill", "pgmqtt", "immich")]
EXPECTED_SECRETS += ["postgres-admin", "postgres-b2", "pgo-default-migration", "pgo-immich-migration"]


def yq(expression, path, edit=False):
    command = ["yq"]
    if edit:
        command += ["-i"]
    else:
        command += ["-o=json"]
    return subprocess.check_output(command + [expression, str(path)], text=True)


def credentials_ready():
    for name in EXPECTED_SECRETS:
        path = BASE / "credentials" / f"{name}.sops.yaml"
        if not path.exists() or not json.loads(yq("has(\"sops\")", path)):
            raise RuntimeError(f"Missing encrypted credential: {name}")
        values = json.loads(yq(".stringData // .data", path))
        if not values or not all(isinstance(value, str) and value.startswith("ENC[") for value in values.values()):
            raise RuntimeError(f"Unencrypted credential: {name}")
    # A clean build also checks that generated files are actually included.
    subprocess.run(["kustomize", "build", str(BASE / "credentials")], check=True, stdout=subprocess.DEVNULL)


def advance(phase, validated=False, writes_paused=False):
    credentials_ready()
    settings = json.loads(yq(".data", SETTINGS))
    if phase == "bootstrap":
        if settings["POSTGRES_DEFAULT_SECRET_PREFIX"] == "postgres":
            raise RuntimeError("Apps already use CNPG; refusing to re-enter bootstrap")
        if not writes_paused:
            raise RuntimeError("Bootstrap requires --writes-paused; consult README before final import")
        yq('.data.CNPG_CLUSTER_SUSPENDED = "false"', SETTINGS, edit=True)
    elif phase == "adopt":
        if settings["CNPG_CLUSTER_SUSPENDED"] != "false" or not validated:
            raise RuntimeError("Adoption requires bootstrap and --validated after BOTH imports")
        yq('.data.CNPG_DATABASES_SUSPENDED = "false"', SETTINGS, edit=True)
    elif phase == "cutover":
        if settings["CNPG_DATABASES_SUSPENDED"] != "false" or not validated:
            raise RuntimeError("Cutover requires adoption and --validated after application/restore checks")
        yq('.data.POSTGRES_DEFAULT_SECRET_PREFIX = "postgres" | '
           '.data.POSTGRES_IMMICH_SECRET_PREFIX = "postgres" | '
           '.data.POSTGRES_DUMP_SECRET = "postgres-admin" | '
           '.data.POSTGRES_IMMICH_DUMP_SECRET = "postgres-admin"', SETTINGS, edit=True)
        upgrades = ROOT / "cluster/apps/utils/tuppr/upgrades/upgrades.yaml"
        check = {"apiVersion": "postgresql.cnpg.io/v1", "kind": "Cluster", "name": "postgres",
            "namespace": "default", "expr": "status.readyInstances == object.spec.instances && status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')"}
        yq(".spec.healthChecks = ([.spec.healthChecks[] | select(.apiVersion != \"postgres-operator.crunchydata.com/v1beta1\" and .apiVersion != \"postgresql.cnpg.io/v1\")] + [" + json.dumps(check) + "])",
            upgrades, edit=True)
    print(f"Prepared {phase} configuration. Review the diff and deliver it through a PR.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["bootstrap", "adopt", "cutover"])
    parser.add_argument("--validated", action="store_true")
    parser.add_argument("--writes-paused", action="store_true")
    args = parser.parse_args()
    advance(args.phase, args.validated, args.writes_paused)


if __name__ == "__main__":
    main()
