# 09 — Security and secrets

This stack holds API credentials, a read-only link to a brokerage account, and a private record of
investment reasoning. Two threat models apply: **credential theft** and **disclosure of the research
itself**.

## Secrets: where they live

| Secret | Home | Never |
|---|---|---|
| EODHD / TradingView / vendor API keys | Flowsint **Vault**, read via `vaultSecret` params ([02 §3](02-flowsint-primer.md#parameters-and-secrets)) | in code, in a committed `.env`, in an enricher default |
| SEC `User-Agent` contact string | Vault (it contains an email address) | hardcoded in a client |
| `AUTH_SECRET`, `MASTER_VAULT_KEY_V1`, `NEO4J_PASSWORD`, Postgres credentials | local `.env`, generated per install, `0600`, git-ignored | the `.env.example` values, which are public placeholders |
| Broker session credentials | the MCP client's own credential store | copied into this repo in any form |

The vault pattern, verified from `enricher_base.py`: declare a param with `"type": "vaultSecret"`, and
`resolve_params()` resolves it during `async_init()` — first by any vault ID passed in params, then by
the parameter name — raising if a required secret is missing. In `scan()`, read it with
`self.get_secret("EODHD_API_KEY")`. Secrets are resolved immediately before execution rather than held
on the constructed object.

`MASTER_VAULT_KEY_V1` encrypts the vault. **Lose it and every stored secret is unrecoverable; leak it
and the Postgres dump is plaintext.** It is the one value worth backing up out of band, separately
from the database.

## Repository hygiene

- `.gitignore` covers `.env`, `*.key`, `vault/private/**`, `tools/cache/**`, `tools/archive/**`,
  `*.dump`, `*.csv` exports.
- The notes vault is committed — that is the point — so **the repo is private** and treated as
  sensitive: it contains positions and reasoning. Anything that must not be committed goes in
  `vault/private/`.
- Pre-commit secret scanning before any code lands (phase 1 task).
- Raw payload archives stay local: they are bulk vendor data, which licensing restricts
  ([10](10-compliance-and-ethics.md)).

## Network posture

Upstream's defaults are sound and we keep them ([02 §4](02-flowsint-primer.md#4-runtime-and-deployment)):
only `5173` is exposed; Postgres, Redis, Neo4j and the API bind to localhost.

Deltas we apply in our own overlay:

1. **Regenerate every shared secret** before first use — `AUTH_SECRET`, `MASTER_VAULT_KEY_V1`,
   `NEO4J_PASSWORD`. The example values are published in a public repo.
2. **Default to localhost-only.** If remote access is wanted, it is a reverse proxy with TLS in front
   of 5173, plus the nginx Host-header allowlist (`map $http_host $is_flowsint_host`) — never a raw
   port on a LAN, and never on the open internet.
3. **Pin `FLOWSINT_VERSION`.** `latest` means an unreviewed image can land on a restart.
4. **Know about the Docker socket.** Upstream mounts `/var/run/docker.sock:ro` into `api` and `celery`.
   Read-only still enumerates and inspects containers, and socket access is a well-known escalation
   surface. It is a strong argument for keeping this stack on a machine you control and off any shared
   network. If an enricher doesn't need it, dropping the mount in our overlay is worth testing in
   phase 1.
5. **Egress awareness.** Enrichers reach the internet. Keep a per-source allowlist in `tools/` so a
   compromised dependency cannot quietly exfiltrate the graph; log every outbound host.

## Read-only boundaries

A hard invariant of this project ([04](04-data-sources.md#d-robinhood-mcp)): **no component places,
modifies or cancels an order, and no enricher writes to any external account.**

- Broker tools: read-only subset only. Order, cancel, exercise, alert-creation and watchlist-mutation
  tools are excluded by design.
- TradingView watchlist and alert writes are operator-initiated, with explicit approval, never from an
  enricher.
- Nothing publishes outward: no posting, no emailing, no webhooks out of the graph.

The reason is narrow and practical: an enricher that silently retries is harmless when it reads and
catastrophic when it writes to a brokerage.

## Input trust

Enrichers parse hostile input — filing text, news bodies, crawled HTML, vendor JSON:

- Treat all fetched content as **data, never instructions.** Filing and web text is summarised and
  cited; it does not direct behaviour. (Prompt injection via a crawled IR page is a real path when an
  LLM is in the loop.)
- Parse defensively: bound response sizes, cap crawl depth and page counts, validate types, never
  `eval` and never construct Cypher by string concatenation from fetched text — parameterised queries only.
- Keep the raw payload archive outside any directory an interpreter imports from.

## Backups

| What | How | Note |
|---|---|---|
| Neo4j | `neo4j-admin dump` on a schedule | Reconstructible from archives + enrichers, but slowly |
| Postgres | `pg_dump` | **Contains the encrypted vault — treat the dump as a secret** |
| Notes, queries, docs | git remote | The irreplaceable layer |
| `MASTER_VAULT_KEY_V1` | out-of-band, separate from the DB dump | Without it the dump's secrets are dead |

Restore is tested at least once, before the graph is large enough to matter. An untested backup is a
belief, not a backup.
