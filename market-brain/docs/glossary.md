# Glossary

## Flowsint terms

| Term | Meaning |
|---|---|
| **Sketch** | An investigation workspace. `sketch_id` is stamped on every node written, so it scopes a graph ([06](06-second-brain-workflow.md#sketches-how-to-scope-an-investigation)) |
| **Scan** | One execution of one enricher over a set of inputs; identified by `scan_id` |
| **Enricher** | A unit that takes typed input, calls a source, and writes typed nodes and labelled edges ([02 §3](02-flowsint-primer.md#3-enrichers)) |
| **Type registry** | The global map of registered entity types, populated by the `@flowsint_type` decorator |
| **Primary field** | The one field marked `json_schema_extra={"primary": True}` — the graph **merge key** |
| **`nodeLabel`** | Human-readable display label on a node, set by each type's `compute_label` validator. Not the Neo4j label |
| **Vault** | Flowsint's encrypted secret store, encrypted with `MASTER_VAULT_KEY_V1`; read via `vaultSecret` params |
| **`vaultSecret`** | A param type whose value is resolved from the Vault at `async_init()` time |
| **Tool** (`tools/`) | An external API or CLI wrapper, kept outside the enricher by upstream convention |
| **Graph service** | The component that writes nodes/relationships, with batching and a flush at the end of `execute()` |

## Market and regulatory terms

| Term | Meaning |
|---|---|
| **CIK** | Central Index Key — the SEC's permanent identifier for a filer. Stable across renames; our `Issuer` merge key |
| **LEI** | Legal Entity Identifier, ISO 17442, 20 characters. Global, covers non-SEC filers |
| **FIGI** | Financial Instrument Global Identifier — share-class and venue precise, permanently assigned; our preferred `Security` key |
| **CUSIP / ISIN / SEDOL** | Security identifiers (US/Canada, international, UK). Alias properties, not merge keys |
| **MIC** | Market Identifier Code, ISO 10383 (e.g. `XNAS`). Our `Exchange` key |
| **Accession number** | The SEC's unique id for a filing, e.g. `0000320193-24-000123`. Our `Filing` key |
| **XBRL** | The tagged-data standard behind EDGAR's company facts; a *fact* is tag + unit + period + value |
| **Frame** (XBRL) | One concept across all filers for one period — EDGAR's cross-sectional view |
| **10-K / 10-Q** | Annual / quarterly report. Item 1A is risk factors; Exhibit 21 lists subsidiaries |
| **8-K** | Current report for material events, item-coded (e.g. 4.01 auditor change, 5.02 officer departure) |
| **Form 4** | Insider transaction report by officers, directors and >10% owners, filed within two business days |
| **10b5-1 plan** | A pre-arranged trading plan. A sale under one reflects a schedule, not necessarily a view — flagged separately |
| **13F-HR** | Quarterly holdings report by institutional managers above the reporting threshold; CUSIP-keyed, filed up to 45 days after quarter end |
| **SC 13D / 13G** | Beneficial-ownership reports above 5%; 13D signals intent, 13G is passive |
| **DEF 14A** | Proxy statement — board, compensation, related-party transactions |
| **GICS** | Global Industry Classification Standard; our `Sector` taxonomy when available |
| **SIC** | The SEC's older industry classification, as filed |
| **MNPI** | Material non-public information. Explicitly out of scope ([10](10-compliance-and-ethics.md)) |
| **Restatement** | A corrected prior figure. Tracked with `restates` rather than overwritten ([08](08-provenance-and-trust.md)) |

## This project's terms

| Term | Meaning |
|---|---|
| **Second brain** | The notes layer plus the graph: external memory for facts *and* relationships, with a review loop that forces re-contact with both |
| **Thesis** | A directional view with a horizon, a conviction level, and at least one falsifiable expectation |
| **Expectation** | A dated, checkable claim a thesis depends on. `breaks_thesis` marks the ones that kill it |
| **Catalyst** | A dated event expected to resolve some uncertainty |
| **Evidence** | A cited claim bearing on a thesis or expectation, `SUPPORTS` or `CONTRADICTS`, with a locator |
| **Provenance block** | The source/locator/retrieved_at/method/confidence properties every written node carries |
| **Merge key** | The primary-field value that decides node identity. Registry ids only ([ADR-0006](adr/0006-registry-ids-as-merge-keys.md)) |
| **Alias property** | An indexed secondary identifier (ticker, CUSIP, vendor code) used for resolution, never for merging |
| **Hop** | One enricher's expansion: one input type, one output type, one source |
| **Spine** | The phase-1 core: security → issuer → filings → insider transactions → facts |
| **Derived edge** | An inferred relationship, always carrying `method=derived`, its `rule`, and `DERIVED_FROM` links |
| **Stale** | Past its class TTL: still shown, flagged, not deleted ([08](08-provenance-and-trust.md)) |
| **Operator assertion** | Your own judgement, stored as such with confidence ≤ 0.2 and a link to the note arguing for it |
