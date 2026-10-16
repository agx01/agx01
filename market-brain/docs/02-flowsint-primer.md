# 02 — Flowsint primer (verified against source)

Everything in this document was read from the upstream source on branch `main` on **2026-10-16**, not
from memory or marketing copy. File paths are given so each claim can be re-checked. Upstream moves
fast (the project describes itself as early-stage), so **re-verify before implementing** — the
[references](references.md) note which facts are source-verified versus fetched from a summary.

Repository: <https://github.com/reconurge/flowsint> · License: **Apache-2.0**, effective 2026-01-25,
relicensed from AGPL-3.0 with written consent of all contributors[^ethics]. Public descriptions of the
license conflict because of that relicensing — the in-repo `LICENSE`/`NOTICE`/`ETHICS.md` are
authoritative.

## 1. Module layout and dependency direction

| Package | Role |
|---|---|
| `flowsint-types` | Pydantic entity models + the type registry |
| `flowsint-core` | Enricher base class, graph service, vault, Celery app, config, logging |
| `flowsint-enrichers` | The enricher modules themselves, plus `tools/` wrappers for external APIs/CLIs |
| `flowsint-api` | FastAPI server, routes, schemas, real-time scan event streaming |
| `flowsint-app` | Frontend (Vite/Node toolchain) served by nginx |

Dependency flow: `app → api → core → enrichers → types`[^readme]. Our extensions therefore depend
only on `types` and `core`, which is the whole reason a companion package works
([ADR-0002](adr/0002-companion-repo-vs-fork.md)).

## 2. Entity types

### Base class

`flowsint-types/src/flowsint_types/flowsint_base.py` — verbatim:

```python
class FlowsintType(BaseModel):
    nodeLabel: Optional[str] = Field(
        None,
        description="UI-readable label for this entity, the one used on the graph.",
        title="Label",
    )
    # Allow extra keys to support additional properties from the user
    model_config = ConfigDict(extra="allow")
```

Two consequences that shape our ontology:

- **`extra="allow"`** means a type accepts properties it never declared. Convenient, and a trap: an
  undeclared property is invisible to the UI's schema picker and to `generate_output_schema()`. We
  declare every market property explicitly ([03 — Ontology](03-ontology.md)).
- **`nodeLabel`** is the human-readable graph label, computed by a validator on each type (see below),
  not the Neo4j node label.

### Registration and auto-discovery

`flowsint-types/src/flowsint_types/registry.py`: a module-level `TYPE_REGISTRY` maps **both** the exact
class name and its lowercase form to the class ("lowercase name for Neo4j compatibility"). The
`@flowsint_type` decorator is a one-liner that calls `TYPE_REGISTRY.register(cls)`.

`load_all_types()` walks the `flowsint_types` package with `pkgutil.iter_modules` and imports every
non-private module to trigger the decorators; it is idempotent (guarded by a `_types_loaded` flag) and
**swallows import errors with a warning to stderr**. It is called at the bottom of
`flowsint_types/__init__.py`.

> **Design consequence.** Auto-discovery iterates *that one package's* `__path__`. A separate
> distribution does not get discovered for free — our types must either be installed into the
> `flowsint_types` namespace or imported explicitly at startup. This is the single most important
> integration question for phase 1 and is tracked in
> [ADR-0003](adr/0003-type-registration-strategy.md).

### The primary field is the merge key

A type marks exactly one field with `json_schema_extra={"primary": True}`. From
`flowsint_types/organization.py`:

```python
name: Any = Field(
    ...,
    description="Organization name",
    title="Organization Name",
    json_schema_extra={"primary": True},
)
```

`Enricher.preprocess()` in `flowsint-core/src/flowsint_core/core/enricher_base.py` finds that field to
coerce bare strings into typed objects, falling back to "first required field, else first field" when
no primary is marked. Each type also defines a `compute_label` validator
(`@model_validator(mode="after")`) that sets `nodeLabel`, plus optional `from_string()` / `detect()`
classmethods used for parsing pasted input.

**The primary field is the graph merge key.** For a market graph this is the whole ball game: pick
`ticker` and `BRK.B` vs `BRK-B` vs `BRK.B.US` become three companies. See
[03 — Ontology](03-ontology.md#identity-resolution) for the keys we chose and why.

### Types shipping upstream today

From `flowsint_types/__init__.py`: `Location`, `Affiliation`, `Alias`, `ASN`, `BankAccount`, `Breach`,
`CIDR`, `Credential`, `CreditCard`, `Device`, `DNSRecord`, `Document`, `Domain`, `Email`, `File`,
`Gravatar`, `Individual`, `Ip`, `Leak`, `Malware`, `Message`, `Organization`, `Phone`, `Phrase`,
`Port`, `ReputationScore`, `RiskProfile`, `Script`, `Session`, `SocialAccount`, `SSLCertificate`,
`Technology`, `Username`, `CryptoWallet`, `CryptoWalletTransaction`, `CryptoNFT`, `Weapon`,
`WebTracker`, `Website`, `Whois`.

Useful to us as-is: `Organization`, `Individual`, `Website`, `Domain`, `Document`, `Phrase`, `Affiliation`.
Note that upstream `Organization` is heavily specialised to the French SIRENE/INSEE registry (dozens of
`siege_*`, `complements_*` fields). We do **not** stuff market data into it — see
[ADR-0004](adr/0004-separate-issuer-type.md).

## 3. Enrichers

### Anatomy

Verbatim from `flowsint-enrichers/src/flowsint_enrichers/domain/to_ip.py`, the canonical minimal example:

```python
@flowsint_enricher
class ResolveEnricher(Enricher):
    """Resolve domain names to IP addresses."""

    InputType = Domain
    OutputType = Ip

    @classmethod
    def name(cls) -> str: return "domain_to_ip"
    @classmethod
    def category(cls) -> str: return "Domain"
    @classmethod
    def key(cls) -> str: return "domain"

    async def scan(self, data: List[InputType]) -> List[OutputType]: ...
    def postprocess(self, results, original_input): ...
```

Contract, from `enricher_base.py`:

| Member | Required | Purpose |
|---|---|---|
| `InputType` / `OutputType` | yes | **Base types, never `List[...]`** — used to generate input/output JSON schemas |
| `name()` | abstract | unique snake_case id, convention `<input>_to_<output>` |
| `category()` | abstract | UI grouping; casing is inconsistent upstream — match neighbours |
| `key()` | abstract | the input type's primary field name |
| `icon()`, `documentation()` | optional | UI affordances; docstrings conventionally start with a `[Source]` tag |
| `get_params_schema()` | optional | declares config + secrets |
| `scan(data)` | abstract, async | does the work, returns a list of output objects |
| `postprocess(results, input_data)` | optional | **where graph writes happen** |

### Execution pipeline

`Enricher.execute()` runs: `async_init()` → `preprocess(values)` → `await scan(...)` →
`postprocess(...)` → `self._graph_service.flush()`, logging start/completion through
`Logger.info` / `Logger.completed` keyed by `sketch_id`.

Two behaviours to design around:

- **Failures are swallowed.** `execute()` wraps everything in `try/except`, logs
  `Enricher X errored: ...` and **returns `[]`**. A silent empty result is indistinguishable from "no
  data found" unless the enricher logs its own per-item failures. Our enrichers log every skipped
  item and record a fetch outcome on the node ([08 — Provenance](08-provenance-and-trust.md)).
- **Graph writes are batched** (`create_graph_service(..., enable_batching=True)` in `__init__`) and
  flushed once at the end of `execute()`. Many small `create_node` calls are cheap; partial failure
  mid-scan can still leave a flushed-but-incomplete subgraph, so provenance carries `scan_id`.

### Parameters and secrets

`get_params_schema()` returns a list of dicts: `name`, `type` (`string`, `number`, `select`, `url`,
`vaultSecret`), `description`, and optional `required`, `default`, `options`.

`resolve_params()` handles `vaultSecret` by looking up the vault **first by the ID the user passed in
params, then by the parameter name itself**, and raises if a required secret is absent:

> `Required vault secret 'X' is missing. Please go to the Vault settings and create a 'X' key.`

Resolution happens in `async_init()`, i.e. immediately before execution, so secrets are not held in
the constructed object. Inside `scan()`, read them with `self.get_secret("EODHD_API_KEY")`, which
falls back to a default when absent. **Never hardcode a key** — see [09 — Security](09-security-and-secrets.md).

### Writing to the graph

```python
self.create_node(issuer)                                  # takes the Pydantic object
self.create_relationship(issuer, filing, "FILED")         # UPPER_SNAKE_CASE verb
self.log_graph_message(f"10-K found for {issuer.cik}")
```

`create_node()` delegates to `GraphService.create_node_from_flowsint_type()` and automatically adds
`type` (lowercase class name), `sketch_id`, `label` and `created_at` (ISO-8601 UTC, creation only).
`create_relationship()` defaults to `IS_RELATED_TO` when no label is given — we never rely on that
default. Hand-building node dicts is an upstream anti-pattern; pass typed objects.

### File layout and discovery

Enrichers live at `flowsint_enrichers/<input_type>/to_<target>.py`, registered by the
`@flowsint_enricher` decorator from `flowsint_enrichers.registry`. Per the upstream enricher-builder
skill: **do not edit registry files**, and **restart the API** so auto-discovery picks up a new
enricher. External API/CLI wrappers belong in the top-level `tools/` directory rather than inside the
enricher.

Upstream ships ~30 enrichers across Domain (8), Website (5), Organization (3), Email (3), Individual
(2), Crypto (2), IP (2), plus ASN, CIDR, Maigret username search, phone breach lookup and an n8n
connector[^readme]. The Website and Organization/Individual families are directly reusable for the
web-OSINT leg of this project ([04 — Data sources](04-data-sources.md#e-web--news-osint-via-flowsints-own-enrichers)).

### Upstream has a skill for this

`.claude/skills/flowsint-enricher-builder/SKILL.md` in the repo is a Claude skill for building
enrichers and types. It encodes the conventions above plus a decision procedure for reuse-vs-extend-vs-new
type, and insists the source files are ground truth. Worth loading when phase 1 starts.

## 4. Runtime and deployment

From `docker-compose.prod.yml` and `.env.example`:

| Service | Image | Exposure |
|---|---|---|
| `postgres` | `postgres:15-alpine` | host-local |
| `redis` | `redis:7-alpine` | host-local |
| `neo4j` | `neo4j:5` | host-local |
| `api` | `ghcr.io/reconurge/flowsint-api:${FLOWSINT_VERSION:-latest}` | `127.0.0.1:5001` (debug only; nginx proxies `/api/`) |
| `celery` | same image, `celery -A flowsint_core.core.celery worker --pool=threads --concurrency=10` | none |
| `app` | `ghcr.io/reconurge/flowsint-app:...` + nginx | **`5173` — the only network-exposed port** |

Named volumes: `pg_data_prod`, `neo4j_data_prod`, `neo4j_logs_prod`, `neo4j_import_prod`,
`neo4j_plugins_prod`. Both `api` and `celery` mount `/var/run/docker.sock:ro`, which is a meaningful
privilege — note it before exposing anything beyond localhost ([09](09-security-and-secrets.md)).

Environment (`.env.example`): `AUTH_SECRET`, `MASTER_VAULT_KEY_V1` (base64 32 bytes, generated per
install), `NEO4J_URI_BOLT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `DATABASE_URL`, `REDIS_URL`,
`ALLOWED_ORIGINS`, `VITE_API_URL` (dev only), and `FLOWSINT_VERSION` to pin a release instead of
`latest`. `celery` additionally sets `SKIP_MIGRATIONS=true` so only the API runs migrations.

Bring-up: `make prod` (or `make dev`) on Linux/macOS; on Windows, copy `.env` into the repo root and
each of `flowsint-api/`, `flowsint-core/`, `flowsint-app/`, then
`docker compose -f docker-compose.prod.yml up -d`. First run: register an account at
<http://localhost:5173/register> — there are no default credentials[^readme].

Before exposing on a LAN: change `AUTH_SECRET`, `MASTER_VAULT_KEY_V1` and `NEO4J_PASSWORD`, add the
hostname to the Host-header allowlist in `flowsint-app/nginx.conf` (the
`map $http_host $is_flowsint_host` block), and terminate TLS with a reverse proxy in front of 5173[^readme].

## 5. Contribution mechanics (for when we upstream anything)

Per `CONTRIBUTING.md`: before every commit run `make lint` (ruff format check, ruff check, frontend
prettier/eslint) and `make typecheck` (mypy), then `uv run pytest -q` in each package touched. A
`lint-staged` pre-commit hook runs `ruff format`/`ruff check --fix` and `prettier --write`, but **not**
mypy, eslint or tests. `make typecheck` and the eslint CI job are **ratcheted** — only files your
branch changed are checked, because both codebases carry existing backlogs. Commits should be atomic
and explain *why*.

## 6. Open questions to resolve in phase 1

| # | Question | Where it bites |
|---|---|---|
| Q1 | How does a type defined outside `flowsint_types` get into `TYPE_REGISTRY`? Namespace package, install-time copy, or explicit import hook? | [ADR-0003](adr/0003-type-registration-strategy.md) |
| Q2 | Same question for `flowsint_enrichers` auto-discovery of an out-of-tree enricher package | [ADR-0003](adr/0003-type-registration-strategy.md) |
| Q3 | Can the published `ghcr.io` images load an extra package, or does the overlay need a thin derived image? | [01 — Architecture](01-architecture.md#deployment-overlay) |
| Q4 | `neo4j-migrations/` — what does it manage, and do we need our own constraints/indexes for merge keys? | [03 — Ontology](03-ontology.md#constraints-and-indexes) |
| Q5 | What exactly is a "sketch", and is one sketch per research theme or one global sketch the right shape? | [06 — Workflow](06-second-brain-workflow.md) |
| Q6 | Does the UI type picker require a `_get_category_definitions()` entry for our categories to appear? | [05 — Enricher catalog](05-enricher-catalog.md) |

[^readme]: Upstream `README.md`, fetched 2026-10-16 via `raw.githubusercontent.com`. Project-site and `docs/` pages were **not** reachable from the build container — see [12 — Environment notes](12-environment-notes.md).
[^ethics]: Upstream `ETHICS.md` and `NOTICE`, fetched 2026-10-16: "Flowsint is distributed under the **Apache License 2.0** (effective January 25, 2026). Code contributed prior to January 25, 2026 was originally licensed under AGPL-3.0 and has been relicensed to Apache 2.0 with the written consent of all contributors."
