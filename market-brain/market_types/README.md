# market-types

Market entity types for [Flowsint](https://github.com/reconurge/flowsint): the phase-1 spine of
[market-brain](../README.md).

Six Pydantic models registered into Flowsint's type registry, each keyed on a registry identifier and
each carrying a provenance block:

| Type | Merge key | What it is |
|---|---|---|
| `Issuer` | `cik:0000320193` → `lei:` → `slug:` | The entity that files and issues securities |
| `Security` | `figi:` → `mic:<MIC>:<symbol>` → `eodhd:` → `slug:` | One share class of one issuer |
| `Person` | `cik:` → `slug:<name>@<issuer_id>` | An officer, director or reporting owner, **public roles only** |
| `Filing` | `0000320193-24-000123` | One SEC filing; the citation target |
| `InsiderTransaction` | `form4:<accession>:<line>` | One transaction line of a Form 4 |
| `Fact` | `xbrl:<cik>:<tag>:<unit>:<period>[:<accession>]` | One tagged financial value |

Specification: [docs/03-ontology.md](../docs/03-ontology.md). Decisions:
[ADR-0004](../docs/adr/0004-separate-issuer-type.md) (why not upstream `Organization`),
[ADR-0006](../docs/adr/0006-registry-ids-as-merge-keys.md) (why not tickers).

## Usage

```python
from market_types import Issuer, Security, provenance

issuer = Issuer.from_cik(320193, name="Apple Inc.",
                         **provenance("sec_edgar", source_ref="https://www.sec.gov/..."))
issuer.issuer_id          # 'cik:0000320193'  — padded, namespaced, stable across renames
issuer.nodeLabel          # 'Apple Inc.'      — computed, used by the graph UI
issuer.is_cited()         # True              — has source + retrieved_at

security = Security.from_eodhd_code("AAPL.US", cusip="037833100", isin="US0378331005")
security.ticker           # 'AAPL'            — alias property, never the merge key
```

Identifiers are validated on the way in, not trusted: `is_valid_cusip`, `is_valid_isin` and
`is_valid_lei` implement the CUSIP check digit, the ISO 6166 (ISIN) check digit and the ISO 7064
MOD 97-10 LEI checksum, and a bad one raises rather than quietly creating a second node for a company
that already exists. `is_valid_figi` is structural only — its check digit is *not* verified.

## Design notes

**Everything is one of six field shapes.** Neo4j properties hold primitives, dates and lists of
primitives — not nested models or dicts. `tests/test_contract.py` enforces that on every field, which
is cheaper than discovering it from a driver error during a scan.

**Provenance is a mixin, not a convention.** `Provenance` supplies `source`, `source_ref`, `locator`,
`retrieved_at`, `as_of`, `method`, `confidence`, `scan_id`, `rule` and `fetch_outcome` to every type,
and refuses incoherent combinations: `method="derived"` without a `rule`, or an operator assertion
claiming confidence above 0.2 ([docs/08](../docs/08-provenance-and-trust.md)).

**Bare strings resolve the way Flowsint hands them over.** `Enricher.preprocess()` wraps a bare input
string as `{primary_field: value}` and then *silently skips* anything that fails validation. So
`"AAPL.US"`, `"US0378331005"`, `"320193"` and `"Apple Inc."` all resolve to something usable instead
of raising. Where resolution is incomplete the key is `slug:…`, which is the flag that the resolver
enricher still has work to do — `is_authoritative(key)` reports it.

**`Provenance` is deliberately not registered** as a Flowsint type; it is a mixin, and registering it
would create a stray node label.

## Development

```bash
uv run --with pytest --with pydantic pytest          # 251 tests incl. doctests
uv run --with mypy --with pydantic mypy src/         # strict
ruff check src/ tests/ && ruff format --check src/ tests/
```

Tests run without a Flowsint install: `conftest.py` injects stub `flowsint_types.flowsint_base` and
`flowsint_types.registry` modules that mirror upstream verbatim as read on 2026-10-16. They are a
stand-in for the registry contract, **not** for integration — the real checks (the API lists the
types, the UI picker shows them, Neo4j writes the expected lowercase labels) need a running instance,
per [ADR-0003](../docs/adr/0003-type-registration-strategy.md). Run the suite with a real
`flowsint_types` importable to exercise the genuine base class.

## Not done yet

- Registration into a running Flowsint (ADR-0003 — the phase-1 gate).
- Neo4j constraints and indexes for these merge keys ([docs/03](../docs/03-ontology.md#constraints-and-indexes)).
- `Holding`, `Position`, `Thesis`, `Expectation`, `Catalyst`, `Evidence`, `Note`, `MacroSeries` —
  phases 2–4 ([docs/11](../docs/11-roadmap.md)).
