# References

Verification status for every external source this documentation relies on. ✅ = read directly on
2026-10-16 from the authoring container; ⚠️ = **not reachable** from that container (egress policy —
[12](12-environment-notes.md)), stated from prior knowledge and **to be verified from your
workstation** before implementation depends on it.

## Flowsint (upstream)

| # | Source | Status | Used for |
|---|---|---|---|
| F1 | [reconurge/flowsint](https://github.com/reconurge/flowsint) — repo page | ✅ | Module layout, stack, enricher inventory, self-hosting summary |
| F2 | [`README.md`](https://raw.githubusercontent.com/reconurge/flowsint/main/README.md) | ✅ | Architecture table, entity types, enricher list, install steps, ports, network-exposure guidance |
| F3 | [`flowsint-types/src/flowsint_types/flowsint_base.py`](https://raw.githubusercontent.com/reconurge/flowsint/main/flowsint-types/src/flowsint_types/flowsint_base.py) | ✅ | `FlowsintType`: `nodeLabel`, `extra="allow"` |
| F4 | [`flowsint-types/src/flowsint_types/registry.py`](https://raw.githubusercontent.com/reconurge/flowsint/main/flowsint-types/src/flowsint_types/registry.py) | ✅ | `TYPE_REGISTRY`, `@flowsint_type`, `load_all_types()` auto-discovery and its limits |
| F5 | [`flowsint-types/src/flowsint_types/__init__.py`](https://raw.githubusercontent.com/reconurge/flowsint/main/flowsint-types/src/flowsint_types/__init__.py) | ✅ | The full list of shipped types |
| F6 | [`flowsint-types/src/flowsint_types/organization.py`](https://raw.githubusercontent.com/reconurge/flowsint/main/flowsint-types/src/flowsint_types/organization.py) | ✅ | Primary-field pattern; SIRENE specialisation behind [ADR-0004](adr/0004-separate-issuer-type.md) |
| F7 | [`flowsint-core/src/flowsint_core/core/enricher_base.py`](https://raw.githubusercontent.com/reconurge/flowsint/main/flowsint-core/src/flowsint_core/core/enricher_base.py) | ✅ | `Enricher` contract, `execute()` pipeline, `resolve_params()`, `get_secret()`, `create_node`/`create_relationship`, exception swallowing, batching |
| F8 | [`flowsint-enrichers/.../domain/to_ip.py`](https://raw.githubusercontent.com/reconurge/flowsint/main/flowsint-enrichers/src/flowsint_enrichers/domain/to_ip.py) | ✅ | Canonical enricher example and conventions |
| F9 | [`.claude/skills/flowsint-enricher-builder/SKILL.md`](https://raw.githubusercontent.com/reconurge/flowsint/main/.claude/skills/flowsint-enricher-builder/SKILL.md) | ✅ | Type/enricher checklists, params schema types, anti-patterns, `_get_category_definitions()`, "restart the API" |
| F10 | [`docker-compose.prod.yml`](https://raw.githubusercontent.com/reconurge/flowsint/main/docker-compose.prod.yml) | ✅ | Services, images, ports, volumes, Celery command, Docker-socket mounts |
| F11 | [`.env.example`](https://raw.githubusercontent.com/reconurge/flowsint/main/.env.example) | ✅ | Required environment variables; key-generation command |
| F12 | [`CONTRIBUTING.md`](https://raw.githubusercontent.com/reconurge/flowsint/main/CONTRIBUTING.md) | ✅ | `make lint` / `make typecheck` / `uv run pytest -q`; ratcheted checks; commit conventions |
| F13 | [`LICENSE`](https://raw.githubusercontent.com/reconurge/flowsint/main/LICENSE), [`NOTICE`](https://raw.githubusercontent.com/reconurge/flowsint/main/NOTICE), [`ETHICS.md`](https://raw.githubusercontent.com/reconurge/flowsint/main/ETHICS.md) | ✅ | Apache-2.0 effective 2026-01-25, relicensed from AGPL-3.0; Hippocratic-License principles; prohibited uses |
| F14 | <https://flowsint.io> and the repo's `docs/` directory | ⚠️ **unreachable** | Would confirm the data model and any plugin mechanism; re-check from your workstation |

Secondary coverage (useful context, not relied on for technical claims): a
[third-party review of Flowsint](https://pasqualepillitteri.it/en/news/7009/flowsint-open-source-osint-graph-tool)
reporting ~30 enrichers and large star counts, and a
[hackers-arise walkthrough](https://hackers-arise.com/open-source-intelligence-osint-using-flowsint-for-graph-based-investigations).
Both report the license as Apache-2.0 or AGPL-3.0 inconsistently; F13 resolves why
(relicensing in January 2026).

## SEC EDGAR

| # | Source | Status | Used for |
|---|---|---|---|
| S1 | [EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | ⚠️ **host denied** | `submissions`, `companyfacts`, `companyconcept`, `frames` endpoint shapes |
| S2 | [Accessing EDGAR Data](https://www.sec.gov/os/accessing-edgar-data) | ⚠️ **host denied** | Declared `User-Agent` requirement and the fair-access request-rate ceiling |
| S3 | [EDGAR full-text search](https://efts.sec.gov/LATEST/search-index?q=) | ⚠️ not tested | Locating named counterparties in filing text |
| S4 | `https://www.sec.gov/files/company_tickers.json` | ⚠️ not tested | Ticker → CIK bootstrap |
| S5 | [EDGAR full-index archives](https://www.sec.gov/Archives/edgar/full-index/) | ⚠️ not tested | Daily/quarterly sweeps instead of per-filer polling |
| S6 | EDGAR payload shapes: `filings.recent` parallel arrays, `companyfacts` unit/observation structure, Form 4 `ownershipDocument` element names (including `aff10b5One`) | ⚠️ **from prior knowledge** | The parsers in [`market_enrichers/tools/edgar.py`](../market_enrichers/README.md). Tested against synthetic fixtures that encode the known traps, which is **not** evidence the live payloads match — validate from your workstation |

Direct verification attempt from the container: `data.sec.gov` returned
`curl: (56) CONNECT tunnel failed, response 403`.

## Data vendors (MCP servers)

| # | Source | Status | Used for |
|---|---|---|---|
| V1 | EODHD MCP server tool inventory | ✅ (tool list read in-session) | The ~100 tools catalogued in [04 §A](04-data-sources.md#a-eodhd-mcp-server--the-breadth-source) |
| V2 | EODHD plan limits, rate limits, redistribution terms | ⚠️ | Quota posture; check `get_user_details` and the vendor's docs |
| V3 | TradingView MCP server tool inventory | ✅ (tool list read in-session) | [04 §C](04-data-sources.md#c-tradingview-mcp-server--screening-technicals-calendars) |
| V4 | TradingView terms of service | ⚠️ | Redistribution and automated-extraction limits |
| V5 | Robinhood MCP server tool inventory | ✅ (tool list read in-session) | [04 §D](04-data-sources.md#d-robinhood-mcp-server--your-own-book-read-only), including the excluded write tools |

## Environment

| # | Source | Status | Used for |
|---|---|---|---|
| E1 | Agent proxy status endpoint (`$HTTPS_PROXY/__agentproxy/status`) | ✅ | Egress policy behaviour; 403-on-CONNECT denial pattern ([12](12-environment-notes.md)) |
| E2 | GitHub App repository scope and `POST /user/repos` → 403 | ✅ | Why the project lives in `agx01/agx01` for now ([MIGRATION.md](../MIGRATION.md)) |

## Second-brain method (background, not load-bearing)

The note taxonomy and review loop borrow from established personal-knowledge practice —
progressive summarisation and a capture→process→connect→review cycle (Tiago Forte's *Building a Second
Brain*), atomic linked notes (Zettelkasten), and the discipline of pre-registered, falsifiable
expectations from forecasting practice (Tetlock's work on scoring predictions). None of it is cited for
a technical claim; the implementation here is [06](06-second-brain-workflow.md).

## How to re-verify

```bash
# Flowsint source (works wherever raw.githubusercontent.com is reachable)
curl -s https://raw.githubusercontent.com/reconurge/flowsint/main/<path>

# SEC (needs a declared User-Agent; run from your workstation)
curl -s -A "market-brain research <your-email>" \
  https://data.sec.gov/submissions/CIK0000320193.json | head

# This container's egress policy
curl -s "$HTTPS_PROXY/__agentproxy/status"
```
