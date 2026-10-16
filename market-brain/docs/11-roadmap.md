# 11 — Roadmap

Phases are ordered so each one is independently useful. If the project stops after phase 2, what exists
still earns its keep.

## Phase 0 — Design (this document set) ✅

**Output**: ontology, architecture, source analysis, decisions recorded, note templates.

Acceptance criteria:
- [x] Flowsint internals verified from source, not from memory ([02](02-flowsint-primer.md))
- [x] Every node type has a declared merge key and a rationale ([03](03-ontology.md))
- [x] Every data source mapped to ontology targets with named tools/endpoints ([04](04-data-sources.md))
- [x] Provenance model specified before any enricher exists ([08](08-provenance-and-trust.md))
- [x] Compliance boundaries written down ([10](10-compliance-and-ethics.md))
- [x] Open questions recorded with owners ([02 §6](02-flowsint-primer.md#6-open-questions-to-resolve-in-phase-1))

## Phase 1 — Spine: types, three enrichers, a graph that cites itself

**Goal**: seed a ticker, get an issuer, its filings and its insider transactions, every node cited.

Tasks:
1. Stand up Flowsint locally from pinned images; complete the hardening deltas ([09](09-security-and-secrets.md)).
2. Resolve **Q1/Q2** — how out-of-tree types and enrichers reach the registries
   ([ADR-0003](adr/0003-type-registration-strategy.md)). Spike both candidate mechanisms; pick one on evidence.
3. ~~`market_types`: `Issuer`, `Security`, `Filing`, `InsiderTransaction`, `Person`, `Fact` + the
   provenance mixin.~~ **Drafted** — see [`market_types/`](../market_types/README.md): six types with
   registry merge keys, checksum-validated identifiers, computed labels, and 251 tests (ruff + mypy
   strict clean). Unit-tested against a verbatim stub of upstream's base class; **not yet registered
   inside a running Flowsint**, which is task 2.
4. Neo4j constraints and indexes for those merge keys; resolve **Q4** (our migration step vs upstream
   `neo4j-migrations/`) and **confirm whether node labels are lowercased**.
5. ~~`tools/`: EDGAR client (declared User-Agent, rate limit, cache, retrieval records, payload
   archive) and EODHD client.~~ **Drafted** in
   [`market_enrichers/tools/`](../market_enrichers/README.md), including the Form 4 XML parser.
   EDGAR payload shapes and EODHD REST paths still need validating against live responses.
6. ~~Enrichers: `alias_to_security`, `security_to_issuer`, `issuer_to_filings`,
   `issuer_to_insider_transactions`, `issuer_to_facts`.~~ **Drafted** — 147 tests, driven through
   upstream's real `execute()` pipeline against a verbatim stub.
7. Contract tests against the pinned `FLOWSINT_VERSION` (**partly done**: registration, params,
   key/primary-field agreement and an ontology-label drift guard run against the stub);
   `health.uncited_claims` is asserted per node in the enricher tests but not yet against Neo4j.

Acceptance criteria:
- Seeding `"AAPL"` yields an `Issuer` keyed `cik:0000320193` with `ISSUES`, `FILED` and Form 4 edges.
- Re-running every enricher twice changes **no** node count — idempotence by merge key.
- `health.uncited_claims` returns zero rows.
- Killing the network mid-scan produces logged, attributable failures, not a silent empty result.
- `git diff` against upstream Flowsint is empty.

## Phase 2 — Brain layer

**Goal**: theses with falsifiable expectations, bidirectionally linked to the graph.

Tasks:
1. `vault/` scaffold from [`templates/`](../templates/); front-matter schema validator.
2. `note_to_entities`, `thesis_to_expectations`, `expectation_to_observation`.
3. `Thesis`, `Expectation`, `Note`, `Evidence`, `Catalyst` types.
4. `issuer_to_catalysts` and `catalyst_to_outcome`.
5. Thesis-discipline queries ([07](07-query-library.md)).
6. Decide the sketch topology — **Q5** ([06](06-second-brain-workflow.md#sketches-how-to-scope-an-investigation)).

Acceptance criteria:
- A thesis note round-trips: front matter → `Thesis` + `Expectation` nodes → query → review note.
- An expectation whose metric is machine-checkable flips to `met`/`missed` automatically with
  `Evidence` attached.
- No thesis can reach `active` without a `breaks_thesis: true` expectation (validator-enforced).
- `thesis.breached_expectations` is genuinely useful on at least three real theses.

## Phase 3 — Network mapping

**Goal**: answer the relationship questions that no note app can.

Tasks: `issuer_to_officers`, `issuer_to_institutional_holders` (13F), `issuer_to_subsidiaries`
(Exhibit 21), `issuer_to_supply_chain`, `issuer_to_peers`, `issuer_to_sector`, `issuer_to_auditor`,
`issuer_to_risk_factors` (year-over-year diff), `issuer_to_website` → hand off to upstream's native
web enrichers.

Acceptance criteria:
- `network.shared_supplier_exposure` returns a dependency you did not already know about.
- Every `SUPPLIES_TO` edge has a `locator` naming the filing section it came from.
- Risk-factor diffs surface additions and deletions between consecutive 10-Ks.
- `network.shared_directors` matches a manual check on two known issuers.

## Phase 4 — Macro overlay, flows, and the automated review

**Goal**: the system runs its own heartbeat.

Tasks: `macro_series_to_observations`, `sector_to_macro_exposure` (rules, each with its `rule` id),
`issuer_to_news`, `account_to_positions`, `position_to_realized_outcome`, `index_to_members`,
`issuer_to_congressional_trades`, the query runner, and the scheduler (daily/weekly/quarterly per
[01](01-architecture.md#scheduling)).

Acceptance criteria:
- The weekly review note is generated from queries before the review starts.
- A rate move resolves to a ranked holdings list with each exposure's `rule` visible.
- Positions are refreshed read-only, within their 2-day TTL.
- Stale and conflicting data are reported every week without being asked.

## Later, maybe

Deliberately parked, with the reason:

| Idea | Why later |
|---|---|
| LLM extraction of supply-chain relations from filing text at scale | Needs the provenance and review loop working first, or it fills the graph with plausible, uncheckable edges |
| Embedding search over notes and filings | Useful, but orthogonal: it finds text, the graph finds structure |
| Multi-portfolio / scenario modelling | Risks turning a knowledge instrument into a strategy lab ([00 — non-goals](00-overview.md#non-goals)) |
| Upstreaming a generic `Company`/`Security` type to Flowsint | Only after our own version has survived real use |
| Publishing anonymised graph statistics | Vendor licensing makes this delicate ([10](10-compliance-and-ethics.md)) |

## Risks

| Risk | Mitigation |
|---|---|
| Out-of-tree registration (Q1/Q2) turns out to need a fork | ADR-0002 revisit is cheap at phase 1; the types and enrichers are portable either way |
| Upstream is early-stage and moves fast | `FLOWSINT_VERSION` pinned; contract tests; our packages touch only `types` and `core` |
| Identity resolution eats the schedule | It is phase 1's gatekeeper on purpose — everything enters through `alias_to_security` |
| Vendor quota or entitlement surprises | Entitlement check at startup; cache-first; EDGAR as the free authority |
| The brain layer goes unused because the loop is tedious | The review is query-driven from phase 2 and automated in phase 4; templates keep capture cheap |
| Scope creep toward trading | Non-goals in [00](00-overview.md#non-goals) and the read-only invariant in [09](09-security-and-secrets.md) |
