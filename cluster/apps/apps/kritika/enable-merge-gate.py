#!/usr/bin/env python3
"""Prepare, or apply, a separate GitHub ruleset requiring Kritika's status."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True, type=int, help="Numeric ID of the Kritika GitHub App")
    parser.add_argument("--apply", action="store_true", help="Create the active ruleset through authenticated gh")
    args = parser.parse_args()
    if args.app_id <= 0:
        sys.exit("The App ID must be positive.")
    root = Path(__file__).resolve().parents[4]
    destination = root / ".github/rulesets/kritika.json"
    document = {
        "name": "Require Kritika review", "target": "branch", "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [{
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "do_not_enforce_on_create": False,
                "required_status_checks": [{"context": "Kritika / Review", "integration_id": args.app_id}],
            },
        }],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2) + "\n")
    print("Prepared .github/rulesets/kritika.json, pinned to the Kritika App.")
    if not args.apply:
        return
    # Re-running never overwrites an existing ruleset or its bypass policy.
    existing = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", "repos/TomCranitch/homelab/rulesets"],
        capture_output=True, text=True,
    )
    if existing.returncode:
        sys.exit("Cannot read rulesets. Authenticate gh with repository administration access first.")
    for page in json.loads(existing.stdout):
        if any(rule.get("name") == document["name"] for rule in page):
            sys.exit("This ruleset already exists; inspect it in GitHub before changing it.")
    result = subprocess.run(
        ["gh", "api", "--method", "POST", "repos/TomCranitch/homelab/rulesets",
         "--input", str(destination)], capture_output=True, text=True,
    )
    if result.returncode:
        sys.exit("GitHub rejected creation of the ruleset; check gh administration access.")
    created = json.loads(result.stdout)
    print("Created active ruleset", created["id"], "requiring Kritika / Review on main.")


if __name__ == "__main__":
    main()
