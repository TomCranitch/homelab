#!/usr/bin/env python3
"""Read PGO metadata and credentials; write only SOPS-encrypted credentials.

Run with an explicitly selected admin kubeconfig. No Kubernetes objects or
PostgreSQL data are changed. Requires kubectl, sops, and Python's standard library.
"""

import argparse
import base64
import json
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

APPS = ("authentik", "linkding", "mealie", "vaultwarden", "windmill", "pgmqtt", "immich")
RECIPIENT = "age1fe4mnzz5uv0c0445m2f9w56r9ydx2lfp5vfx4qchlevfhsaky35sh2zgey"
HOST = "postgres-rw.default.svc.cluster.local"
ROOT = Path(__file__).resolve().parents[1]


def run(command, stdin=None):
    result = subprocess.run(command, input=stdin, text=True, capture_output=True)
    if result.returncode:
        # Do not echo command input, database diagnostics, or secret contents.
        raise RuntimeError(f"{command[0]} failed (exit {result.returncode}); no credentials printed")
    return result.stdout


def secret(kubectl, name):
    obj = json.loads(run(kubectl + ["get", "secret", name, "-o", "json"]))
    return {key: base64.b64decode(value).decode() for key, value in obj["data"].items()}


def connection(name, user, password, dbname, host=HOST):
    return {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": name, "namespace": "default", "labels": {"cnpg.io/reload": "true"}},
        "type": "kubernetes.io/basic-auth",
        "stringData": {
            "username": user, "user": user, "password": password,
            "host": host, "port": "5432", "dbname": dbname,
            "uri": f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:5432/{quote(dbname, safe='')}?sslmode=require",
        },
    }


def inventory(kubectl, cluster):
    pods = json.loads(run(kubectl + ["get", "pods", "-l",
        f"postgres-operator.crunchydata.com/cluster={cluster},postgres-operator.crunchydata.com/role=master", "-o", "json"]))["items"]
    if len(pods) != 1:
        raise RuntimeError(f"Expected one primary for {cluster}")
    psql = kubectl + ["exec", "-i", pods[0]["metadata"]["name"], "-c", "database", "--",
        "psql", "-X", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-At"]
    databases = json.loads(run(psql + ["-d", "postgres"], """
SELECT coalesce(json_agg(row_to_json(d)), '[]') FROM (
 SELECT datname AS name, pg_get_userbyid(datdba) AS owner,
        pg_database_size(oid) AS bytes, datcollate, datctype
 FROM pg_database WHERE datallowconn AND NOT datistemplate AND datname <> 'postgres'
) d;
"""))
    roles = json.loads(run(psql + ["-d", "postgres"], """
SELECT coalesce(json_agg(row_to_json(r)), '[]') FROM (
 SELECT rolname AS name, rolcanlogin AS login, rolsuper AS superuser,
        rolcreatedb AS createdb, rolcreaterole AS createrole, rolreplication AS replication,
        rolbypassrls AS bypassrls, rolinherit AS inherit, rolconnlimit AS "connectionLimit",
        rolvaliduntil AS "validUntil",
        ARRAY(SELECT p.rolname FROM pg_auth_members m JOIN pg_roles p ON p.oid=m.roleid
              WHERE m.member=pg_roles.oid ORDER BY p.rolname) AS "inRoles"
 FROM pg_roles WHERE rolname !~ '^pg_' AND rolname <> 'postgres'
) r;
"""))
    for database in databases:
        database["extensions"] = json.loads(run(psql + ["-d", database["name"]],
            "SELECT json_agg(json_build_object('name', extname, 'version', extversion)) FROM pg_extension;"))
        if database["name"] == "immich":
            database["legacy_vector_dependencies"] = json.loads(run(psql + ["-d", "immich"],
                Path(__file__).with_name("vector-dependencies.sql").read_text()))
    return {"databases": databases, "roles": roles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    kubectl = [args.kubectl, "--kubeconfig", args.kubeconfig, "--request-timeout=30s", "-n", "default"]
    inventories = {cluster: inventory(kubectl, cluster) for cluster in ("default-cluster", "immich-cluster")}
    print(json.dumps(inventories, indent=2))
    if args.inventory_only:
        return
    output = ROOT / "credentials"
    if list(output.glob("*.sops.yaml")):
        raise RuntimeError("Encrypted credentials already exist; refusing to rotate or overwrite them")
    expected = {"default-cluster": (set(APPS) - {"immich"}) | {"hass", "paperless"}, "immich-cluster": {"immich"}}
    for cluster, names in expected.items():
        actual = {db["name"] for db in inventories[cluster]["databases"]}
        if actual != names:
            raise RuntimeError(f"Unexpected database inventory in {cluster}; review before preparing migration")
        for db in inventories[cluster]["databases"]:
            if db.get("legacy_vector_dependencies"):
                raise RuntimeError("Immich still depends on legacy pgvecto.rs; migrate those objects before PG18")
    all_roles = {role["name"]: role for inv in inventories.values() for role in inv["roles"]}
    for name in APPS:
        if name not in all_roles:
            raise RuntimeError(f"Missing application role: {name}")
        if all_roles[name]["validUntil"] is not None:
            raise RuntimeError(f"Password expiry on {name} requires review before role adoption")
    documents = []
    for app in APPS:
        cluster = "immich-cluster" if app == "immich" else "default-cluster"
        source = secret(kubectl, f"{cluster}-pguser-{app}")
        if source["user"] != app or source["dbname"] != app:
            raise RuntimeError(f"Unexpected source identity for {app}")
        documents.append(connection(f"postgres-{app}", app, source["password"], app))
    documents.append(connection("postgres-admin", "postgres", secrets.token_urlsafe(48), "postgres"))
    for cluster, name in (("default-cluster", "pgo-default-migration"), ("immich-cluster", "pgo-immich-migration")):
        source = secret(kubectl, f"{cluster}-pguser-postgres")
        documents.append(connection(name, source["user"], source["password"], "postgres", source["host"]))
    conf = secret(kubectl, "crunchy-backup-secret")["s3.conf"]
    options = {}
    for line in conf.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            options[key.strip()] = value.strip()
    documents.append({"apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": "postgres-b2", "namespace": "default"}, "type": "Opaque",
        "stringData": {"ACCESS_KEY_ID": options["repo1-s3-key"], "ACCESS_SECRET_KEY": options["repo1-s3-key-secret"], "REGION": "us-east-005"}})
    # Encrypt everything before writing anything; plaintext exists only in memory.
    encrypted = [(doc["metadata"]["name"], run(["sops", "encrypt", "--input-type", "json",
        "--output-type", "yaml", "--age", RECIPIENT, "--encrypted-regex", "^(data|stringData)$",
        "--filename-override", f"cluster/apps/databases/cloudnative-pg/credentials/{doc['metadata']['name']}.sops.yaml"], json.dumps(doc)))
        for doc in documents]
    output.mkdir(parents=True, exist_ok=True)
    for name, ciphertext in encrypted:
        (output / f"{name}.sops.yaml").write_text(ciphertext)
    resources = "\n".join(f"  - {name}.sops.yaml" for name, _ in encrypted)
    (output / "kustomization.yaml").write_text(
        "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n" + resources + "\n")
    (ROOT / "migration/inventory.json").write_text(json.dumps(inventories, indent=2) + "\n")
    # Only include auxiliary roles that actually exist on the source.
    source_roles = {role["name"]: role for role in inventories["default-cluster"]["roles"]}
    selected = list(APPS[:-1]) + ["hass", "paperless"] + [name for name in ("windmill_admin", "windmill_user") if name in source_roles]
    run(["yq", "-i", ".spec.bootstrap.initdb.import.roles = " + json.dumps(selected), str(ROOT / "cluster/cluster.yaml")])
    # Preserve attributes/memberships when CNPG adopts existing app roles.
    for name in list(APPS) + ["hass", "paperless", "windmill_admin", "windmill_user"]:
        if name not in all_roles:
            continue
        role = all_roles[name]
        attributes = {key: value for key, value in role.items() if key not in ("name", "superuser", "validUntil")}
        expression = "(select(.spec.name == " + json.dumps(name) + ").spec) *= " + json.dumps(attributes)
        run(["yq", "-i", expression, str(ROOT / "databases/roles.yaml")])
    print(f"Prepared {len(encrypted)} encrypted secrets; no cluster state changed")


if __name__ == "__main__":
    main()
