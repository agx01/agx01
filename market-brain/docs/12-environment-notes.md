# 12 — Environment notes

Where this project can run, and what each environment can actually reach. Recorded because two days
were nearly lost to "the API is down" when the real answer was "this container's egress policy denies
that host."

## Environments

| Environment | Role | Notes |
|---|---|---|
| **Your workstation** | Where Flowsint runs | Docker + Make (Linux/macOS) or Docker Desktop (Windows). The graph, the vault and the secrets live here. UI at <http://localhost:5173> |
| **Claude cloud session** (where this doc was written) | Design, documentation, code authoring | Ephemeral container, restricted egress, no Docker-in-Docker guarantee. Cannot run Flowsint |
| **Claude desktop / Cowork on your PC** | Note-taking, review runs, scheduled tasks | Has local filesystem and Drive sync; the natural place to drive the weekly review |

## Egress findings from the authoring container (2026-10-16)

Verified by direct request, not assumed:

| Host | Result | Consequence |
|---|---|---|
| `raw.githubusercontent.com` | ✅ reachable | Upstream source could be read and verified ([02](02-flowsint-primer.md)) |
| `github.com` | ✅ reachable | Repo metadata readable |
| `sec.gov`, `data.sec.gov` | ❌ `CONNECT tunnel failed, response 403` | **EDGAR cannot be called from this container.** Enricher development needs either your workstation or the vendor fallbacks ([04](04-data-sources.md#access-from-a-restricted-network)) |
| `flowsint.io` | ❌ DNS/policy denied | Project-site docs unavailable; in-repo files used instead |
| `cdn.jsdelivr.net` | ❌ DNS/policy denied | Fetch raw files from `raw.githubusercontent.com` instead |

The proxy reports `enabled: true` with a fixed allowlist; a denial shows up as a 403 on `CONNECT` or a
DNS failure, **not** as a timeout. Anything marked ⚠️ in [04](04-data-sources.md) is unverified for
exactly this reason — verify it from your workstation.

Practical consequence: **enrichers are developed here, but integration-tested on your workstation**,
where EDGAR and the vendor APIs are reachable and Flowsint is actually running.

## MCP servers available in the authoring environment

Connected and usable for data-source exploration: **EODHD** (~100 tools), **TradingView**,
**Robinhood**, plus Google Workspace (Gmail, Calendar, Drive), GitHub, Supabase and Netlify. Tool
inventories are catalogued in [04 — Data sources](04-data-sources.md).

Several plugin-provided MCP servers failed to connect in this session with
`Proxy refused to open a tunnel: 403 Forbidden` (Slack, Notion, Linear, HubSpot and others). That is a
connection failure under the environment's network policy, not a missing capability — retry from an
environment whose policy allows them if they are ever needed.

## GitHub constraints hit while setting this up

- This session's GitHub App is **scoped to `agx01/agx01`** and **cannot create repositories**:
  `POST /user/repos → 403 Resource not accessible by integration`.
- So the project was authored inside `agx01/agx01` on branch `claude/happy-mendel-sswq5r`, under
  `market-brain/`, with [`MIGRATION.md`](../MIGRATION.md) holding the exact commands to lift it into
  its own repo with history intact.
- To let a future session push straight to the new repo: create the empty `agx01/market-brain` on
  GitHub, then attach it to the session (the remote-session `add_repo` facility), and ensure the Claude
  GitHub App has access to it.

## Running Flowsint on your workstation — checklist

1. `git clone https://github.com/reconurge/flowsint.git` (separate from this repo — upstream stays untouched)
2. `cp .env.example .env`, then **regenerate** `AUTH_SECRET`, `MASTER_VAULT_KEY_V1`
   (`python3 -c "import os,base64; print('base64:'+base64.b64encode(os.urandom(32)).decode())"`) and
   `NEO4J_PASSWORD` ([09](09-security-and-secrets.md))
3. Pin `FLOWSINT_VERSION` to a released tag rather than `latest`
4. On Windows also copy `.env` into `flowsint-api/`, `flowsint-core/`, `flowsint-app/`
5. `make prod` (Linux/macOS) or `docker compose -f docker-compose.prod.yml up -d` (Windows)
6. Register the first account at <http://localhost:5173/register> — there are no default credentials
7. Store vendor API keys in the Vault UI under the exact param names our enrichers declare
   ([05](05-enricher-catalog.md))
8. Keep 5173 on localhost unless a TLS reverse proxy and the nginx Host allowlist are configured

## Where the vault (notes) should live

The markdown vault is committed to this repo. On a Windows workstation that pairs naturally with the
Drive-synced project folder (`...\Google Drive\My Drive\myclaudeproject\market-brain`): clone the repo
there so notes are both version-controlled and synced to other devices. Git remains the source of
truth; Drive is convenience, not backup ([09](09-security-and-secrets.md)).
