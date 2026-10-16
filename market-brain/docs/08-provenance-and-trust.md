# 08 — Provenance and trust

A research graph that cannot say where a number came from is worse than no graph: it launders
guesses into facts and then lets you query them with confidence. Provenance is therefore a **schema
requirement**, enforced by the `health.uncited_claims` query ([07](07-query-library.md)), whose
correct answer is always zero rows.

## The provenance block

Every node our enrichers write, and every edge carrying a claim, gets these properties. They are
declared explicitly on each type rather than relying on `FlowsintType`'s `extra="allow"`
([02](02-flowsint-primer.md)), so they appear in generated schemas and the UI.

| Property | Type | Meaning |
|---|---|---|
| `source` | str | Source family: `sec_edgar`, `eodhd`, `tradingview`, `robinhood`, `web`, `operator`, `derived` |
| `source_ref` | str | The citation target — a filing index URL, API endpoint, or article URL |
| `locator` | str | Where inside the source: `10-K 2025, Item 1A`, XBRL tag, page, JSON pointer |
| `retrieved_at` | datetime | UTC fetch time. **Not** the as-of date of the data itself |
| `as_of` | date | The date the *value* describes, when different from retrieval |
| `method` | enum | `reported` · `vendor_parsed` · `derived` · `third_party_opinion` · `operator_assertion` · `conflicting` |
| `confidence` | float 0–1 | See the scale below |
| `scan_id` | str | The enricher run that wrote it — makes a partial write traceable |
| `rule` | str | For `method=derived`: the exact rule or query that produced it |
| `fetch_outcome` | enum | `ok` · `partial` · `cached_stale` · `source_error` — so "no data" and "fetch failed" never look alike |

Flowsint's `GraphService` already adds `type`, `sketch_id`, `label` and `created_at` to every node; we
never set those ourselves.

## Confidence scale

Confidence is about **epistemic standing, not precision**. A number can be exact and still weakly
supported.

| Value | Standing | Example |
|---|---|---|
| 1.0 | As filed with a regulator, machine-readable | XBRL `Revenues` from a 10-K |
| 0.9 | As filed, human-extracted from filing text | Supplier named in Item 1A risk factors |
| 0.8 | Vendor-parsed regulatory data | EODHD `get_sec_company_financials` |
| 0.7 | Vendor fundamental not traceable to a filing | A vendor's computed ratio |
| 0.6 | Derived by our own rule from higher-confidence inputs | Sector macro sensitivity |
| 0.5 | Reported by credible press with named sourcing | Supply-chain report in a major outlet |
| 0.3 | Third-party opinion | Analyst price target, technical rating |
| 0.2 | Operator assertion without external support | "I think this is their biggest customer" |

Rules: a derived value's confidence never exceeds its weakest input; `third_party_opinion` and
`operator_assertion` are stored as `Evidence`, never as `Fact`; and confidence is **never silently
upgraded** — a better source creates a new node version with a `SAME_AS` or `restates` link.

## Freshness and staleness

Data does not announce when it stops being true. Each class gets a TTL; past it, the node is **stale,
not wrong** — still shown, flagged, and listed by `health.stale_nodes`.

| Class | TTL | Why |
|---|---|---|
| Filed documents, Form 4 transactions, filed facts | ∞ | Immutable once filed (a restatement is a new fact, linked by `restates`) |
| Fundamentals, segments, risk factors | 120 days | Quarterly reporting cycle plus slack |
| 13F holdings | 120 days | Quarterly, filed up to 45 days after period end |
| Issuer profile (officers, HQ, employees) | 90 days | Moves slowly, but moves |
| Security metadata (shares outstanding, listing) | 30 days | Buybacks, issuance, re-listings |
| News, sentiment | 7 days for aggregates | Aggregated sentiment decays fast |
| Macro observations | per series frequency | Daily series stale after days; quarterly after a quarter |
| Your positions | 2 days | The book changes; a stale book makes every exposure query wrong |

## Conflicts

When two sources disagree, **both values are kept.** The higher-precedence source
([04](04-data-sources.md#source-precedence)) holds the canonical node; the other is attached as
`Evidence` with `method=conflicting` and surfaced by `health.conflicts`.

Why keep it: a disagreement between a vendor and a filing is itself information — usually about
restatement timing, fiscal-calendar handling, or share-class confusion. Silent resolution destroys the
only clue that something subtle happened.

## Derived edges

Inference is allowed. Invisible inference is not. Every derived node or edge carries:

- `method=derived`
- `rule` — the human-readable rule *and* the query or function id implementing it
- a `DERIVED_FROM` edge to each input
- `derived_at`

Example: `(:issuer)-[:EXPOSED_TO {direction: 'negative', sensitivity: 'high', rule: 'semis_capex_vs_10y_real_rate_v1', derived_at: ...}]->(:macroseries)`.
When the rule changes, the old edges are re-derived rather than edited, so a wrong rule can be fully
retracted — which is what makes it safe to have rules at all.

## Operator assertions

Your own judgements are first-class and clearly marked: `source=operator`,
`method=operator_assertion`, `confidence ≤ 0.2`, and a `note_path` pointing at the note where you
argued for it. They are allowed to appear in queries, and never allowed to masquerade as reported data.

## Audit trail

Three layers, each answering a different question:

1. **Graph-level** — every node carries `source_ref`, `locator`, `scan_id`.
2. **Payload-level** — `tools/` archives the raw response that produced the claim, keyed by
   `request_hash`, so a parse can be re-audited without re-fetching ([01](01-architecture.md)).
3. **Reasoning-level** — git history of the notes: what you believed, when, and the diff when you
   changed your mind.

Together these answer the question that actually matters in a post-mortem: *when did the information
become available, and when did I act on it?*

## What this prevents

| Failure | How provenance catches it |
|---|---|
| A vendor's silently restated number changes a thesis | `restates` chain + conflicts query shows the vintage |
| An enricher broke and the graph quietly stopped updating | `fetch_outcome`, `health.empty_scans`, `health.stale_nodes` |
| An opinion read as a fact six months later | `method=third_party_opinion`, stored as `Evidence`, confidence 0.3 |
| A supply-chain edge nobody can justify | `locator` names the filing section; no citation, no edge |
| Your own old guess hardening into a premise | `operator_assertion` with a link to the note that argued for it |
