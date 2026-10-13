#!/usr/bin/env python3
"""Encrypt GitHub App/OpenRouter credentials directly with the repo's SOPS policy."""

import argparse
import getpass
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True, help="GitHub App client ID, Iv.../Iv1...")
    parser.add_argument("--private-key", required=True, type=Path, help="Downloaded GitHub App PEM file")
    parser.add_argument("--enable", action="store_true", help="Also unsuspend Kritika in Git; requires healthy shared Postgres")
    args = parser.parse_args()
    app = Path(__file__).resolve().parent
    root = app.parents[3]
    destination = app / "secrets/integrations.sops.yaml"
    if destination.exists():
        sys.exit("Refusing to overwrite integrations.sops.yaml; rotate through SOPS instead.")
    sops = shutil.which("sops")
    if not sops:
        sys.exit("Install sops or enter this repository's development shell first.")
    if not args.client_id.startswith("Iv"):
        sys.exit("Use the App client ID, not its numeric App ID.")
    private_key = args.private_key.read_text()
    if "PRIVATE KEY-----" not in private_key:
        sys.exit("The private key file must contain the GitHub App's PEM private key.")
    webhook_secret = getpass.getpass("GitHub App webhook secret (the value configured on GitHub): ")
    openrouter_key = getpass.getpass("OpenRouter API key (reviews, confidence scoring and embeddings): ")
    if not webhook_secret or not openrouter_key:
        sys.exit("Both credentials are required; no file was written.")
    secret = {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": "kritika-integrations", "namespace": "kritika"},
        "type": "Opaque",
        "stringData": {
            "GITHUB_APP_CLIENT_ID": args.client_id,
            "GITHUB_APP_PRIVATE_KEY": private_key,
            "GITHUB_APP_WEBHOOK_SECRET": webhook_secret,
            "OPENROUTER_API_KEY": openrouter_key,
        },
    }
    result = subprocess.run(
        [sops, "--encrypt", "--filename-override", str(destination.relative_to(root)),
         "--input-type", "json", "--output-type", "yaml", "/dev/stdin"],
        input=json.dumps(secret), text=True, capture_output=True, cwd=root,
    )
    if result.returncode:
        sys.exit("SOPS encryption failed; no credentials were written or printed.")
    with destination.open("x") as output:
        output.write(result.stdout)
    manifest = app / "secrets/kustomization.yaml"
    content = manifest.read_text()
    if "  - integrations.sops.yaml" not in content:
        manifest.write_text(content + "  - integrations.sops.yaml\n")
    if args.enable:
        orchestration = app / "ks.yaml"
        orchestration.write_text(orchestration.read_text().replace("  suspend: true\n", "  suspend: false\n"))
    print("Wrote SOPS-encrypted integrations.sops.yaml and added its Kustomize reference.")
    if args.enable:
        print("Kritika is enabled in Git and will wait for Postgres and Authentik readiness.")
    else:
        print("Kritika stays suspended in Git. Unsuspend it after checking shared Postgres readiness.")


if __name__ == "__main__":
    main()
