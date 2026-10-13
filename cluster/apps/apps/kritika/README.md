# Kritika

GitHub PR reviews, inline findings, suggested fixes and follow-up replies for
`TomCranitch/homelab`, including Renovate PRs. See the
[upstream guide](https://kritika.home-operations.com/setup/).

## Configuration

- Dashboard: `https://kritika.${S_HOMEPROD_DOMAIN}` through the existing Envoy
  HTTPS listener. The Authentik operator manages its application and OIDC
  provider. `service-admins` are admins; other authenticated SSO users have
  read-only member access. The `profile` scope must include the `groups` claim.
- GitHub webhooks: Tailscale Funnel via `kritika-webhook`, following the Flux
  and Konflate ingress pattern. It routes `/hooks/github` to `kritika:8080`.
  The Funnel Ingress is deployed with the app.
- Reviews, follow-ups and confidence scoring use
  `openrouter/openai/gpt-6.1-sol` with high reasoning effort. This is paid
  OpenRouter API usage; no ChatGPT subscription login is required.
- Embeddings use OpenRouter `voyageai/voyage-code-4`, 1024 dimensions, with
  the same API key. Set an OpenRouter spending limit for all model usage.
- All PRs are eligible, including drafts, forks and bots. Push bursts settle
  for 30 seconds. Automatic approvals are off; confidence gating requires 5/5.
- `.kritika.yaml` scopes `.agents/skills/renovate-review/SKILL.md` to
  `renovate/` branches. A digest-pinned `flate` image supplies chart rendering.
  Skills and repository settings come from the merge-base, so the skill takes
  effect on PRs based on the branch where it has been merged.
- Dedicated `kritika` namespace, gVisor runner Jobs and enabled monitoring.
  Cilium policies restrict server and runner database traffic to the shared
  CNPG cluster. Runner lookups go through Kritika's egress gateway, which
  denies private address ranges.

GitHub App and OpenRouter credentials are included as a SOPS-encrypted Secret.
The app is enabled in Git and waits for shared Postgres, Authentik, Envoy,
Tailscale and monitoring readiness. No live deployment or GitHub merge-gate
activation has been performed.

## Shared Postgres

Kritika uses the existing CNPG `default/postgres` cluster through
`postgres-rw.default.svc.cluster.local:5432`. No extra cluster, operator or PVC
is added. `cloudnative-pg/cluster/kritika.yaml` declares database `kritika`,
pgvector 0.8.7, VectorChord 1.1.1 and three non-superuser login roles:

| Role | Purpose | Connection secret in `kritika` |
| --- | --- | --- |
| `kritika` | Database owner, migrations and configuration sync | `kritika-postgres-credentials` |
| `kritika_app` | Application access; owns no tables, no `BYPASSRLS` | `kritika-postgres-app` |
| `kritika_runner` | Restricted runner access | `kritika-postgres-runner` |

The shared PostgreSQL 18 image and VectorChord preload already meet the
[upstream requirements](https://kritika.home-operations.com/database/).
Connections are direct, with TLS and a ten-second connection timeout. Do not
put the owner or application connection behind a transaction-mode pooler.

SOPS-encrypted role credentials live beside the existing CNPG credentials in
`default`, named `postgres-kritika-owner`, `postgres-kritika-app` and
`postgres-kritika-runner`. Matching encrypted connection secrets are provided
in `kritika` because Secret references cannot cross namespaces. Keep both
copies consistent during password rotation. The dedicated namespace limits
Kritika's Secret-reading permissions to its own credentials.

The `kritika` Flux Kustomization depends on `postgres-cluster`, whose readiness
checks include the database, its extensions and all three roles. The shared
Barman WAL/full backups and daily `pg_dumpall` include Kritika automatically.
Those backups contain model credentials and review state; protect them as
credential-bearing data and verify a restore after rollout.

## Connect GitHub and OpenRouter

Register a GitHub App under TomCranitch's Developer settings and install it on
**only `homelab`**. Generate a random webhook secret for the setup helper and
GitHub. Leave the webhook inactive until the Funnel address is available.
The dashboard's OIDC callback is
`https://kritika.<your-domain>/auth/callback/oidc`.

Give the App these repository permissions:

| Permission | Access |
| --- | --- |
| Contents | Read and write (needed to resolve review threads) |
| Metadata | Read-only |
| Pull requests | Read and write |
| Issues | Read and write (reactions and conversation replies) |
| Commit statuses | Read and write |

Subscribe to Pull request, Pull request review comment, Pull request review
thread, Issue comment, Push and Repository events. Generate an App private
key and note both its client ID (`Iv...`) and numeric App ID. GitHub OAuth
login is not used; the Authentik operator supplies dashboard SSO.

Create an OpenRouter key with access to GPT-6.1 Sol and Voyage Code 4.
The encrypted integration Secret is already included. For a fresh installation
without that file, run this from the repo's development shell:

```sh
python3 cluster/apps/apps/kritika/setup-integrations.py \
  --client-id Iv1.YOUR_APP_CLIENT_ID \
  --private-key /path/to/downloaded-app.pem
```

The helper prompts without echoing for the webhook secret and OpenRouter key,
encrypts them directly into `secrets/integrations.sops.yaml` and adds its
Kustomize reference. It refuses to overwrite an existing file. Encryption uses
the public age recipient; no private SOPS identity is needed. Never paste
credentials into chat.

The helper refuses to replace the supplied integration Secret; use SOPS for
credential rotation. On a fresh installation, `--enable` also unsuspends the
app. This deployment is already enabled, with readiness dependencies intact.

After rollout, verify `postgres-cluster`, `kritika-secrets`,
`kritika-authentik` and `kritika` are ready. Get the generated Funnel hostname:

```sh
kubectl -n kritika get ingress kritika-webhook \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}'
```

Set the GitHub App's webhook URL to `https://<that-hostname>/hooks/github`,
enter the same webhook secret used by the helper and enable **Active**.
Verify GitHub webhook deliveries succeed. No extra Tailscale auth key or
operator is required: this uses the existing operator, ProxyClass and Funnel
permissions. The chart's Cilium policy already permits the proxy to reach
the server on port 8080. Native OIDC protects the dashboard on its existing
Envoy hostname. Verify the role mapping with an admin and an ordinary SSO user.

## Activate the merge gate

The scorer fails `Kritika / Review` below 5/5 and reports an error for an
unscored or failed review. Kritika's normal skipped-review statuses still
apply. GitHub blocks merges only after this status is required.

First verify a real PR gets a summary, inline findings where relevant,
follow-up replies and a scored status from your Kritika App. Then, with `gh`
authenticated with repository administration access, use its **numeric App ID**:

```sh
python3 cluster/apps/apps/kritika/enable-merge-gate.py --app-id YOUR_NUMERIC_APP_ID
# Inspect .github/rulesets/kritika.json, then activate:
python3 cluster/apps/apps/kritika/enable-merge-gate.py --app-id YOUR_NUMERIC_APP_ID --apply
```

The separate ruleset pins `Kritika / Review` to that App on `main`, preserving
existing rules. The helper refuses to overwrite a ruleset of the same name.
Saving the JSON alone does not activate it. Repository overrides must keep
confidence scoring and gating enabled.

## Validation

Run `kustomize build cluster`, `kustomize build cluster/apps` and
`git diff --check`. Render the pinned Kritika chart with its HelmRelease values
and network-policy patches for the Kubernetes version in `talos/talconfig.yaml`.
Validate AuthentikApplication and CNPG Database/DatabaseRole manifests against
the installed operator schemas. Check that all Secret values are encrypted and included in Kustomize.

Live database migrations, network access, backup/restore, SSO role mapping,
OpenRouter calls and GitHub merge-gate behaviour need post-rollout checks.
Database and role reclaim policies retain data on resource removal. Removing
the AuthentikApplication deletes its managed provider and application; release
its ownership deliberately before removal.
