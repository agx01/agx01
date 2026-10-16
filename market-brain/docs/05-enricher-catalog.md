# 05 — Enricher catalog

Each enricher is **one hop**: one input type, one output type, one source, one set of edges. Hops
compose in the UI, so small enrichers beat clever ones — and a failure is then attributable to a
single hop.

Naming and layout follow upstream convention, verified in
[02 — Flowsint primer](02-flowsint-primer.md): id `<input>_to_<output>`, file
`market_enrichers/<input_type>/to_<target>.py`, registered with `@flowsint_enricher`, `key()` returning
the input type's primary field. UI categories are declared per enricher; whether a *new* category also
needs an entry in upstream's `_get_category_definitions()` is open question Q6.

## Phase 1 — the spine

| Enricher | In → Out | Source | Writes |
|---|---|---|---|
| `alias_to_security` | `Phrase` → `Security` | EODHD `resolve_ticker`, `get_stocks_from_search`, `get_symbol_change_history` | `Security` with all alias properties; `LISTED_ON`; `SAME_AS` when it resolves an existing node |
| `security_to_issuer` | `Security` → `Issuer` | EODHD `get_fundamentals_data`, `get_sec_companies` | `Issuer` (CIK-keyed); `ISSUES` |
| `issuer_to_filings` | `Issuer` → `Filing` | EDGAR submissions; fallback EODHD `get_sec_filings` | `Filing` nodes; `FILED` |
| `issuer_to_insider_transactions` | `Issuer` → `InsiderTransaction` | EDGAR Form 4; fallback EODHD `get_insider_transactions_form4` | `InsiderTransaction`, `Person`; `REPORTED_BY`, `TRANSACTED_IN`, `DISCLOSED_IN` |
| `issuer_to_facts` | `Issuer` → `Fact` | EDGAR `companyfacts`; fallback EODHD `get_sec_company_financials` | `Fact`; `REPORTS_FACT` from the citing `Filing` |

`alias_to_security` is the gatekeeper: **every** entry into the graph goes through resolution, so the
merge-key discipline in [03 — Ontology](03-ontology.md#identity-resolution) holds by construction.

The types these enrichers read and write are drafted in
[`market_types/`](../market_types/README.md), including the key builders
(`Issuer.from_cik`, `Security.from_eodhd_code`, `Fact.from_xbrl`, `InsiderTransaction.from_form4`) and
the `provenance()` helper every enricher should use for the block in [08](08-provenance-and-trust.md).

## Phase 2 — the brain layer

| Enricher | In → Out | Notes |
|---|---|---|
| `note_to_entities` | `Note` → any | Parses YAML front matter, creates `DOCUMENTS` edges to referenced merge keys |
| `thesis_to_expectations` | `Thesis` → `Expectation` | Reads the thesis note's expectation table into checkable nodes |
| `expectation_to_observation` | `Expectation` → `Evidence` | Fetches the metric, compares to target, sets `status`, writes `Evidence` + `SUPPORTS`/`CONTRADICTS` |
| `issuer_to_catalysts` | `Issuer` → `Catalyst` | EODHD `get_upcoming_earnings`/`get_upcoming_dividends`/`get_upcoming_splits`, TradingView calendars |
| `catalyst_to_outcome` | `Catalyst` → `Evidence` | After the date: 8-K / earnings result / news → outcome + `Evidence` |

## Phase 3 — network mapping

| Enricher | In → Out | Source | Writes |
|---|---|---|---|
| `issuer_to_officers` | `Issuer` → `Person` | DEF 14A, Form 4 reporting owners, fundamentals officer lists | `OFFICER_OF`, `DIRECTOR_OF` with titles and dates |
| `issuer_to_institutional_holders` | `Issuer` → `Holding` | EDGAR 13F-HR | `Institution`, `Holding`; `HOLDS`, `HOLDING_OF` |
| `issuer_to_subsidiaries` | `Issuer` → `Issuer` | 10-K Exhibit 21 | `SUBSIDIARY_OF` |
| `issuer_to_supply_chain` | `Issuer` → `Issuer` | 10-K/10-Q customer & supplier concentration, named-counterparty extraction, news | `SUPPLIES_TO` with `component`, `revenue_share`, `basis` |
| `issuer_to_peers` | `Issuer` → `Issuer` | EODHD fundamentals peers, sector screens | `COMPETES_WITH` |
| `issuer_to_sector` | `Issuer` → `Sector` | EODHD classification, SIC from EDGAR | `OPERATES_IN` (taxonomy-qualified) |
| `issuer_to_auditor` | `Issuer` → `Institution` | 10-K audit report, 8-K item 4.01 | `AUDITED_BY` per fiscal year |
| `issuer_to_risk_factors` | `Issuer` → `RiskFactor` | 10-K Item 1A diffed year over year | `DISCLOSES_RISK`; the **diff** is the signal |
| `issuer_to_website` | `Issuer` → `Website` | fundamentals / EDGAR | `Website` — the handoff into upstream's native web enrichers |
| `issuer_to_congressional_trades` | `Issuer` → `InsiderTransaction` | EODHD `get_congressional_trades`, Robinhood `get_politician_trades` | Transactions tagged `actor_type=legislator` |
| `issuer_to_sanctions_screen` | `Issuer` → `SanctionsEntity` | EODHD sanctions endpoints | `SCREENED_AGAINST` with match score |

## Phase 4 — macro, flows, book

| Enricher | In → Out | Source |
|---|---|---|
| `sector_to_macro_exposure` | `Sector` → `MacroSeries` | Curated rules + EODHD macro/rates/credit; writes `EXPOSED_TO` **with its `rule`** |
| `macro_series_to_observations` | `MacroSeries` → `Observation` | EODHD rates/macro/commodities; revision-aware |
| `issuer_to_news` | `Issuer` → `NewsItem` | EODHD `get_company_news` + `get_sentiment_data`; TradingView news |
| `account_to_positions` | `Phrase` (account) → `Position` | Robinhood read-only tools; `HELD_IN` |
| `position_to_realized_outcome` | `Position` → `Evidence` | `get_realized_pnl`, `get_pnl_trade_history` — feeds post-mortems |
| `index_to_members` | `Phrase` (index) → `Security` | EODHD `mp_index_components` — rebalance and membership effects |

## Skeleton

Written to the verified upstream contract; this is the shape every enricher in the catalog takes.

```python
# market_enrichers/issuer/to_filings.py
from typing import Any, Dict, List

from flowsint_core.core.enricher_base import Enricher
from flowsint_core.core.logger import Logger
from flowsint_enrichers.registry import flowsint_enricher

from market_types.filing import Filing
from market_types.issuer import Issuer
from tools.edgar import EdgarClient          # rate limiting, caching, retrieval records


@flowsint_enricher
class IssuerToFilingsEnricher(Enricher):
    """[SEC EDGAR] List filings for an issuer from its submissions history."""

    InputType = Issuer
    OutputType = Filing

    @classmethod
    def name(cls) -> str:
        return "issuer_to_filings"

    @classmethod
    def category(cls) -> str:
        return "Market"

    @classmethod
    def key(cls) -> str:
        return "issuer_id"          # the primary field of Issuer

    @classmethod
    def get_params_schema(cls) -> List[Dict[str, Any]]:
        return [
            {
                "name": "form_types",
                "type": "string",
                "description": "Comma-separated form types, e.g. 10-K,10-Q,8-K,4",
                "default": "10-K,10-Q,8-K",
            },
            {
                "name": "since",
                "type": "string",
                "description": "ISO date lower bound (inclusive)",
                "required": False,
            },
            {
                "name": "SEC_USER_AGENT",
                "type": "vaultSecret",
                "description": "Declared User-Agent for SEC fair access, e.g. 'name you@example.com'",
                "required": True,
            },
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.edges: List[tuple[Issuer, Filing]] = []

    async def scan(self, data: List[InputType]) -> List[OutputType]:
        client = EdgarClient(user_agent=self.get_secret("SEC_USER_AGENT"))
        forms = {f.strip() for f in self.params.get("form_types", "").split(",") if f.strip()}
        results: List[Filing] = []
        self.edges = []

        for issuer in data:
            try:
                payload, record = await client.submissions(issuer.cik)
            except Exception as e:
                # execute() swallows exceptions and returns [] — log per item or lose the reason
                Logger.error(self.sketch_id, {"message": f"submissions failed for {issuer.issuer_id}: {e}"})
                continue

            for row in client.iter_filings(payload, forms=forms, since=self.params.get("since")):
                filing = Filing(
                    accession=row["accession"],
                    form_type=row["form"],
                    filed_at=row["filing_date"],
                    period_of_report=row.get("report_date"),
                    primary_doc_url=row["primary_doc_url"],
                    filing_index_url=row["index_url"],
                    # provenance — see docs/08
                    source="sec_edgar",
                    source_ref=row["index_url"],
                    retrieved_at=record.retrieved_at,
                    method="reported",
                    confidence=1.0,
                    scan_id=self.scan_id,
                )
                results.append(filing)
                self.edges.append((issuer, filing))

        return results

    def postprocess(self, results: List[OutputType], original_input: List[InputType]) -> List[OutputType]:
        if not self._graph_service:
            return results
        for issuer, filing in self.edges:
            self.create_node(issuer)
            self.create_node(filing)
            self.create_relationship(issuer, filing, "FILED")
            self.log_graph_message(f"{filing.form_type} {filing.accession} for {issuer.issuer_id}")
        return results


InputType = IssuerToFilingsEnricher.InputType
OutputType = IssuerToFilingsEnricher.OutputType
```

## Rules for every enricher in this project

1. **Per-item `try/except` with an explicit log.** `Enricher.execute()` catches everything and returns
   `[]`; without per-item logging, "source was down" and "nothing to find" look identical.
2. **Provenance on every object written** ([08](08-provenance-and-trust.md)). A node without
   `source` + `retrieved_at` is a bug.
3. **Secrets via `vaultSecret` params and `self.get_secret()`** — never literals, never bare `os.environ`
   inside an enricher ([09](09-security-and-secrets.md)).
4. **One hop, one source family.** A fallback to a second source is allowed, but it records which one
   answered.
5. **Idempotent by merge key.** Re-running an enricher must converge, not duplicate. This is what makes
   scheduled refresh safe.
6. **No derived values written as facts.** Ratios and comparisons belong in queries; an inference
   written to the graph carries `DERIVED_FROM` with its `rule`.
7. **Networking lives in `tools/`** — rate limiting, caching, retries and the retrieval record are
   shared, not re-implemented per enricher.
8. **Contract test against the pinned `FLOWSINT_VERSION`**: registration resolves, schemas generate,
   `postprocess` writes the expected labels against a throwaway graph.
