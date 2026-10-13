# Kritika

PR reviews and follow-ups via OpenRouter's floating Sol alias, with Voyage Code 4
embeddings. Fork PRs are excluded; confidence scores are informational.
Authentik supplies SSO (`service-admins` are admins; other users are read-only).
Uses the shared `default/postgres` database cluster and chart Cilium policies.

After deployment, get the Tailscale Funnel hostname:

```sh
kubectl -n kritika get ingress kritika-webhook -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}'
```

Set the GitHub App webhook to `https://<hostname>/hooks/github`, using the
webhook secret already supplied in the SOPS-encrypted integration Secret.
