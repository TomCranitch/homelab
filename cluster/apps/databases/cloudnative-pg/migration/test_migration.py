"""Run from this directory with python -m unittest -v test_migration.

Tests use disposable files and synthetic credentials; no cluster or SOPS key.
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prepare = module("prepare")
stage = module("stage")


class CredentialTests(unittest.TestCase):
    def test_connection_uri_escapes_credentials_and_requires_tls(self):
        values = prepare.connection("example", "a@b", "p:/?#$", "app")["stringData"]
        self.assertEqual(values["password"], "p:/?#$")
        self.assertIn("a%40b:p%3A%2F%3F%23%24@", values["uri"])
        self.assertTrue(values["uri"].endswith("?sslmode=require"))

    def test_failed_command_does_not_print_sensitive_diagnostics(self):
        result = subprocess.CompletedProcess(["kubectl"], 1, "secret-password", "secret-password")
        with patch.object(prepare.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as raised:
                prepare.run(["kubectl"], "secret-password")
        self.assertNotIn("secret-password", str(raised.exception))


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "cluster/apps/databases/cloudnative-pg"
        self.credentials = self.base / "credentials"
        self.credentials.mkdir(parents=True)
        self.settings = self.root / "cluster/flux/cluster-config/settings.yaml"
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"apiVersion": "v1", "kind": "ConfigMap", "data": {
            "CNPG_CLUSTER_SUSPENDED": "true", "CNPG_DATABASES_SUSPENDED": "true",
            "POSTGRES_DEFAULT_SECRET_PREFIX": "default-cluster-pguser",
            "POSTGRES_IMMICH_SECRET_PREFIX": "immich-cluster-pguser",
            "POSTGRES_DUMP_SECRET": "default-cluster-pguser-postgres",
            "POSTGRES_IMMICH_DUMP_SECRET": "immich-cluster-pguser-postgres"}}))
        for key, value in (("ROOT", self.root), ("BASE", self.base), ("SETTINGS", self.settings)):
            patcher = patch.object(stage, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def seed_credentials(self, plaintext=False):
        resources = []
        for name in stage.EXPECTED_SECRETS:
            path = self.credentials / f"{name}.sops.yaml"
            path.write_text(json.dumps({"apiVersion": "v1", "kind": "Secret",
                "metadata": {"name": name}, "sops": {"age": []},
                "stringData": {"password": "test-only" if plaintext else "ENC[test-only]"}}))
            resources.append(path.name)
        (self.credentials / "kustomization.yaml").write_text(json.dumps({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": resources}))

    def test_missing_credentials_blocks_bootstrap_without_changing_settings(self):
        before = self.settings.read_text()
        with self.assertRaisesRegex(RuntimeError, "Missing encrypted credential"):
            stage.advance("bootstrap", writes_paused=True)
        self.assertEqual(before, self.settings.read_text())

    def test_plaintext_credentials_are_rejected(self):
        self.seed_credentials(plaintext=True)
        with self.assertRaisesRegex(RuntimeError, "Unencrypted credential"):
            stage.advance("bootstrap", writes_paused=True)

    def test_bootstrap_requires_pause_and_keeps_apps_on_pgo(self):
        self.seed_credentials()
        with self.assertRaisesRegex(RuntimeError, "writes-paused"):
            stage.advance("bootstrap")
        stage.advance("bootstrap", writes_paused=True)
        values = json.loads(stage.yq(".data", self.settings))
        self.assertEqual(values["CNPG_CLUSTER_SUSPENDED"], "false")
        self.assertEqual(values["CNPG_DATABASES_SUSPENDED"], "true")
        self.assertEqual(values["POSTGRES_DEFAULT_SECRET_PREFIX"], "default-cluster-pguser")

    def test_cutover_requires_adoption_and_updates_both_upgrade_resources(self):
        self.seed_credentials()
        with self.assertRaisesRegex(RuntimeError, "adoption"):
            stage.advance("cutover", validated=True)
        stage.advance("bootstrap", writes_paused=True)
        with self.assertRaisesRegex(RuntimeError, "validated"):
            stage.advance("adopt")
        stage.advance("adopt", validated=True)
        upgrades = self.root / "cluster/apps/utils/tuppr/upgrades/upgrades.yaml"
        upgrades.parent.mkdir(parents=True)
        documents = [{"apiVersion": "tuppr.home-operations.com/v1alpha1", "kind": kind,
            "spec": {"healthChecks": [{"apiVersion": "ceph.rook.io/v1", "kind": "CephCluster"},
                {"apiVersion": "postgres-operator.crunchydata.com/v1beta1", "kind": "PostgresCluster"},
                {"apiVersion": "postgres-operator.crunchydata.com/v1beta1", "kind": "PostgresCluster"}]}}
            for kind in ("TalosUpgrade", "KubernetesUpgrade")]
        upgrades.write_text("\n---\n".join(json.dumps(doc) for doc in documents))
        stage.advance("cutover", validated=True)
        values = json.loads(stage.yq(".data", self.settings))
        self.assertEqual(values["POSTGRES_DEFAULT_SECRET_PREFIX"], "postgres")
        self.assertEqual(values["POSTGRES_IMMICH_SECRET_PREFIX"], "postgres")
        self.assertEqual(values["POSTGRES_DUMP_SECRET"], values["POSTGRES_IMMICH_DUMP_SECRET"])
        output = subprocess.check_output(["yq", "ea", "-o=json", "-I=0", ".spec.healthChecks", str(upgrades)], text=True)
        for checks in map(json.loads, output.splitlines()):
            self.assertEqual(len(checks), 2)
            self.assertEqual(checks[0]["kind"], "CephCluster")
            self.assertEqual(checks[1]["apiVersion"], "postgresql.cnpg.io/v1")
            self.assertEqual(checks[1]["name"], "postgres")


class DumpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backup = self.root / "backup"
        self.backup.mkdir()
        manifest = Path(__file__).resolve().parents[2] / "pgdump/helmrelease.yaml"
        self.script = subprocess.check_output(["yq", "-r",
            ".spec.values.resources[0].spec.jobTemplate.spec.template.spec.containers[0].args[0]",
            str(manifest)], text=True).replace("/backup/", str(self.backup) + "/")
        binary = self.root / "pg_dumpall"
        binary.write_text("#!/bin/sh\nset -eu\nprintf 'call\\n' >> \"$DUMP_CALLS\"\n"
            "if [ \"$FAIL_DUMP\" = 1 ]; then exit 1; fi\n"
            "while [ \"$#\" -gt 0 ]; do if [ \"$1\" = -f ]; then shift; "
            "printf 'synthetic dump\\n' > \"$1\"; exit 0; fi; shift; done\n")
        binary.chmod(0o755)

    def execute(self, consolidated=False, fail=False):
        env = dict(os.environ, PATH=str(self.root) + ":" + os.environ["PATH"],
            DATABASE_URL="postgresql://synthetic-default", IMMICH_PASSWORD="synthetic",
            IMMICH_DATABASE_URL="postgresql://synthetic-default" if consolidated else "postgresql://synthetic-immich",
            DUMP_CALLS=str(self.root / "calls"), FAIL_DUMP="1" if fail else "0")
        return subprocess.run(["/bin/sh", "-ec", self.script], env=env, capture_output=True)

    def test_staging_dumps_both_sources(self):
        self.assertEqual(self.execute().returncode, 0)
        self.assertEqual((self.root / "calls").read_text().count("call"), 2)
        self.assertTrue((self.backup / "postgres.pgdump").exists())
        self.assertTrue((self.backup / "postgres-immich.pgdump").exists())

    def test_cutover_dumps_shared_cluster_once(self):
        self.assertEqual(self.execute(consolidated=True).returncode, 0)
        self.assertEqual((self.root / "calls").read_text().count("call"), 1)
        self.assertFalse((self.backup / "postgres-immich.pgdump").exists())

    def test_failed_dump_preserves_last_successful_file(self):
        previous = self.backup / "postgres.pgdump"
        previous.write_text("last successful backup")
        self.assertNotEqual(self.execute(fail=True).returncode, 0)
        self.assertEqual(previous.read_text(), "last successful backup")


if __name__ == "__main__":
    unittest.main()
