# market-enrichers

The phase-1 enrichers for [market-brain](../README.md): one hop each, from a seed to a cited
subgraph. Built on [Flowsint](https://github.com/reconurge/flowsint)'s `Enricher` base, writing the
types from [`market_types`](../market_types/README.md).

| Enricher | In → Out | Source | Writes |
|---|---|---|---|
| `alias_to_security` | `Phrase` → `Security` | EODHD | `Security` with aliases; `RESOLVES_TO`, `SAME_AS` |
| `security_to_issuer` | `Security` → `Issuer` | EODHD | `Issuer` keyed on CIK/LEI; `ISSUES` |
| `issuer_to_filings` | `Issuer` → `Filing` | SEC EDGAR | `Filing` with its index URL; `FILED` |
| `issuer_to_facts` | `Issuer` → `Fact` | SEC EDGAR XBRL | `Fact` per vintage; `FILED`, `REPORTS_FACT` |
| `issuer_to_insider_transactions` | `Issuer` → `InsiderTransaction` | SEC EDGAR Form 4 | transactions + `Person`; `DISCLOSED_IN`, `REPORTED_BY`, `TRANSACTED_IN` |

A research run composes them: `"apple"` → `Security` → `Issuer` → filings, facts and insider
activity, each node carrying where it came from. Catalog and phases 2–4:
[docs/05](../docs/05-enricher-catalog.md).

## Layout

```
src/market_enrichers/
├── market_enricher.py     # shared base: provenance, guard(), buffered writes, clients
├── params.py              # reusable param fragments (vault secrets, since, limit, cache mode)
├── registry.py            # loader (strict — an enricher that fails to import must fail loudly)
├── tools/                 # the only code that talks to the outside
│   ├── http.py            # transport protocol, rate limiter, cache, retrieval records, archive
│   ├── edgar.py           # submissions, XBRL facts, Form 4 XML parser
│   └── eodhd.py           # vendor client (⚠️ draft paths)
├── phrase/to_security.py
├── security/to_issuer.py
└── issuer/{to_filings,to_facts,to_insider_transactions}.py
```

## What the shared base is for

Upstream's `Enricher` leaves four things to each author, and each is silent when wrong
([docs/02 §3](../docs/02-flowsint-primer.md#3-enrichers)):

1. **`execute()` swallows exceptions and returns `[]`**, so a dead source and an empty world look
   identical. `MarketEnricher.guard()` logs and counts each skipped item; `postprocess` reports the
   totals and says so explicitly when a run produced nothing *and* hit no errors.
2. **Provenance** must land on every node. `provenance_from(record)` converts a fetch into the block
   from [docs/08](../docs/08-provenance-and-trust.md), including `fetch_outcome=cached_stale` when a
   value came from an expired cache rather than the source.
3. **Graph writes belong in `postprocess`.** `stage()` and `link()` buffer during the scan;
   `postprocess` writes once, de-duplicated by merge key, and rejects a relationship label that is
   not `UPPER_SNAKE_CASE`.
4. **Clients** need a rate limit, a cache and a vault-held credential. `self.edgar()` and
   `self.eodhd()` build them, so no enricher reaches for a key itself.

## Fetching

`tools/http.py` has no third-party dependency: `Transport` is a protocol, the default uses `urllib`,
and the clock, sleep and cache clock are injectable — which is why the tests cover retry, backoff,
TTL expiry and stale fallback without a network or a real wait.

Behaviour worth knowing:

- **EDGAR requires a declared `User-Agent` with a contact address**, and `EdgarClient` refuses to
  construct without one — SEC fair access is enforced, not documented
  ([docs/04](../docs/04-data-sources.md)).
- **Filed documents are cached forever** (`TTL_IMMUTABLE`); fundamentals, holdings and profiles have
  TTLs from the freshness table in [docs/08](../docs/08-provenance-and-trust.md).
- **When a source breaks but a cached copy exists**, the copy is served and marked
  `cached_stale` instead of reporting "no data".
- **The EODHD token is added at request time**, is not part of the cache key, and never reaches a
  stored `source_ref` — a citation must not carry a credential
  ([docs/09](../docs/09-security-and-secrets.md)).

## Unverified parts, named

`sec.gov` and the vendor are both denied by the authoring container's egress policy
([docs/12](../docs/12-environment-notes.md)), so:

- **EDGAR payload shapes** (submissions parallel arrays, `companyfacts`, Form 4 XML element names)
  come from prior knowledge, not a captured sample. The parsers are defensive and tested against
  synthetic fixtures that encode the known traps; they are **not** evidence the live payloads match.
- **EODHD REST paths** in `tools/eodhd.py` are a draft. The design docs reach EODHD through its MCP
  server, which an enricher inside Flowsint cannot use, so the REST paths need checking against the
  vendor's documentation. `EodhdClient.get()` takes any path so a correction needs no code change here.
- **The `10b5-1` flag** is read from `aff10b5One` where present and otherwise inferred from footnote
  prose — a heuristic. Unknown stays `None` rather than `False`, because a false "not planned" turns
  a scheduled sale into a signal.

Validate all three from your workstation before trusting output. See
[docs/references.md](../docs/references.md).

## Development

```bash
uv run --with pytest --with pydantic pytest           # 147 tests incl. doctests
uv run --with mypy --with pydantic mypy src/          # strict
ruff check src/ tests/ && ruff format --check src/ tests/
```

`conftest.py` injects stub `flowsint_types`, `flowsint_core` and `flowsint_enrichers` modules that
mirror upstream verbatim — including `Enricher.execute()`'s exception swallowing, so the tests
exercise the real failure mode. Tests drive `execute()` end to end against a fake transport and a
recording graph service, and assert the written nodes, the edges, and the provenance on each node.

One of those tests reads [docs/03-ontology.md](../docs/03-ontology.md) and fails if the package emits
a relationship label the ontology does not document. It caught `RESOLVES_TO` on first run.

## Not done yet

- **Registration inside a running Flowsint** — [ADR-0003](../docs/adr/0003-type-registration-strategy.md),
  still the phase-1 gate. Nothing here has executed in the real worker.
- Verification of the payload shapes and vendor paths above.
- 13F holdings, officers, supply chain, risk-factor diffs, news, macro — phases 3–4
  ([docs/11](../docs/11-roadmap.md)).
- Derivative tables in Form 4 (option grants and exercises).
