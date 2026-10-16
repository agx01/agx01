# 07 — Query library

The queries *are* the product. A research question asked once is a thought; the same question saved,
named and re-run weekly is a system.

Conventions: Neo4j node labels are the **lowercase** class name (Flowsint registers types under both
exact and lowercase names for Neo4j compatibility — [02 §2](02-flowsint-primer.md#registration-and-auto-discovery));
**verify against a running instance before relying on these verbatim**. `$param` placeholders are
supplied by the runner. Every query below is written to be read by a human first — the comment above
each says what an answer *means*, not what the Cypher does.

---

## Thesis discipline

### `thesis.breached_expectations`
Theses whose falsification contract has been violated or has come due. The first query of every review.

```cypher
MATCH (t:thesis)-[:EXPECTS]->(e:expectation)
WHERE t.status = 'active'
  AND (e.status = 'missed'
       OR (e.status = 'pending' AND date(e.due_by) < date($today)))
OPTIONAL MATCH (ev:evidence)-[:CONTRADICTS]->(e)
RETURN t.thesis_id, t.title, t.conviction,
       e.statement, e.due_by, e.status, e.observed_value, e.target_value,
       e.breaks_thesis,
       collect(DISTINCT ev.source_ref)[0..5] AS contradicting_sources
ORDER BY e.breaks_thesis DESC, e.due_by ASC;
```

### `thesis.unbalanced`
Active theses with no recorded counter-evidence, or none in 60 days. Not a bug in the thesis — a gap in
the research.

```cypher
MATCH (t:thesis) WHERE t.status = 'active'
OPTIONAL MATCH (ev:evidence)-[c:CONTRADICTS]->(t)
WITH t, count(ev) AS against, max(c.assessed_at) AS last_against
WHERE against = 0 OR last_against < datetime($cutoff_60d)
RETURN t.thesis_id, t.title, t.conviction, against, last_against
ORDER BY t.conviction DESC;
```

### `thesis.evidence_balance`
The argument for and against, side by side, for one thesis.

```cypher
MATCH (t:thesis {thesis_id: $thesis_id})
OPTIONAL MATCH (sup:evidence)-[s:SUPPORTS]->(t)
OPTIONAL MATCH (con:evidence)-[c:CONTRADICTS]->(t)
RETURN t.title,
       sum(coalesce(s.weight, 1.0)) AS support_weight,
       sum(coalesce(c.weight, 1.0)) AS contra_weight,
       collect(DISTINCT {claim: sup.claim, ref: sup.source_ref, at: sup.retrieved_at}) AS for,
       collect(DISTINCT {claim: con.claim, ref: con.source_ref, at: con.retrieved_at}) AS against;
```

---

## Network mapping

### `network.shared_supplier_exposure`
The query that justifies the whole graph: which of my positions depend on the same upstream company,
including second-hop dependencies.

```cypher
MATCH (p:position)-[:HELD_IN]->(s:security)<-[:ISSUES]-(i:issuer)
MATCH path = (i)-[:SUPPLIES_TO*1..2]->(dep:issuer)
WITH dep, collect(DISTINCT i.name) AS dependent_holdings,
     sum(p.market_value) AS exposed_value, min(length(path)) AS hops
WHERE size(dependent_holdings) > 1
RETURN dep.name AS shared_dependency, hops, dependent_holdings,
       round(exposed_value) AS exposed_market_value
ORDER BY exposed_value DESC;
```

### `network.shared_directors`
Shared officers and directors across issuers — governance overlap, and a channel for information and
practice to travel.

```cypher
MATCH (p:person)-[r1:DIRECTOR_OF|OFFICER_OF]->(a:issuer)
MATCH (p)-[r2:DIRECTOR_OF|OFFICER_OF]->(b:issuer)
WHERE a.issuer_id < b.issuer_id
  AND coalesce(r1.to, date($today)) >= date($today)
  AND coalesce(r2.to, date($today)) >= date($today)
RETURN p.name, p.person_id, a.name AS company_a, r1.title AS role_a,
       b.name AS company_b, r2.title AS role_b
ORDER BY p.name;
```

### `network.ownership_overlap`
Which institutions hold several of my names, and how big those stakes are — crowding risk, and whose
redemptions would move my book.

```cypher
MATCH (inst:institution)-[:HOLDS]->(h:holding {period: $period})-[:HOLDING_OF]->(s:security)
MATCH (p:position)-[:HELD_IN]->(s)
WITH inst, collect(DISTINCT s.ticker) AS overlapping, sum(h.value) AS total_value
WHERE size(overlapping) > 1
RETURN inst.name, overlapping, round(total_value) AS holder_value_usd
ORDER BY total_value DESC LIMIT 25;
```

### `network.two_hop_neighbourhood`
Everything within two hops of one issuer, for reading the shape of a situation. Relationship types are
restricted so the result stays legible.

```cypher
MATCH (i:issuer {issuer_id: $issuer_id})
MATCH path = (i)-[:SUPPLIES_TO|COMPETES_WITH|SUBSIDIARY_OF|OPERATES_IN|AUDITED_BY*1..2]-(n)
RETURN path LIMIT 300;
```

---

## Flow and insider signal

### `flow.insider_clusters`
Several insiders at one issuer transacting in the same direction inside a short window — the only
insider pattern with much claim to signal. `10b5-1` plan sales are separated, because a scheduled sale
tells you about a plan, not a view.

```cypher
MATCH (it:insidertransaction)-[:REPORTED_BY]->(p:person)
MATCH (it)-[:TRANSACTED_IN]->(s:security)<-[:ISSUES]-(i:issuer)
WHERE date(it.transaction_date) >= date($since)
  AND it.transaction_code IN ['P','S']
WITH i, s, it.acquired_disposed AS direction,
     coalesce(it.is_10b5_1, false) AS planned,
     collect(DISTINCT p.name) AS insiders,
     sum(it.value) AS total_value, count(it) AS txn_count
WHERE size(insiders) >= 2
RETURN i.name, s.ticker, direction, planned, insiders, txn_count,
       round(total_value) AS total_value_usd
ORDER BY total_value DESC;
```

### `flow.insider_before_catalyst`
Insider transactions in the window before a catalyst resolved. Descriptive, not accusatory — timing
context for the post-mortem.

```cypher
MATCH (c:catalyst)-[:CATALYST_FOR]->(i:issuer)-[:ISSUES]->(s:security)
MATCH (it:insidertransaction)-[:TRANSACTED_IN]->(s)
MATCH (it)-[:REPORTED_BY]->(p:person)
WHERE c.status = 'resolved'
  AND duration.inDays(date(it.transaction_date), date(c.expected_at)).days
      BETWEEN 0 AND coalesce($window_days, 30)
RETURN i.name, c.title, c.expected_at, c.outcome,
       p.name, it.transaction_date, it.transaction_code,
       it.shares, it.value, it.is_10b5_1,
       duration.inDays(date(it.transaction_date), date(c.expected_at)).days AS days_before
ORDER BY c.expected_at DESC, days_before ASC;
```

### `flow.institutional_position_change`
Quarter-over-quarter 13F change per holder for one security — who is building and who is leaving.

```cypher
MATCH (inst:institution)-[:HOLDS]->(h1:holding {period: $period})-[:HOLDING_OF]->(s:security {security_id: $security_id})
OPTIONAL MATCH (inst)-[:HOLDS]->(h0:holding {period: $prior_period})-[:HOLDING_OF]->(s)
WITH inst, h1, h0,
     h1.shares - coalesce(h0.shares, 0) AS share_change
RETURN inst.name,
       coalesce(h0.shares, 0) AS prior_shares, h1.shares AS current_shares,
       share_change,
       CASE WHEN h0 IS NULL THEN 'new'
            WHEN share_change > 0 THEN 'added'
            WHEN share_change < 0 THEN 'reduced'
            ELSE 'unchanged' END AS action
ORDER BY abs(share_change) DESC LIMIT 50;
```

---

## Catalysts and calendar

### `catalyst.horizon`
Everything dated in the next N days on anything I track, with the thesis it bears on.

```cypher
MATCH (c:catalyst)-[:CATALYST_FOR]->(x)
WHERE date(c.expected_at) >= date($today)
  AND date(c.expected_at) <= date($today) + duration({days: coalesce($days, 30)})
OPTIONAL MATCH (t:thesis)-[:WATCHES]->(c)
OPTIONAL MATCH (t2:thesis)-[:TRACKS]->(x)
RETURN c.expected_at, c.title, c.catalyst_type, c.date_confidence, c.importance,
       coalesce(x.name, x.ticker) AS subject,
       collect(DISTINCT coalesce(t.title, t2.title)) AS related_theses
ORDER BY c.expected_at ASC;
```

### `catalyst.unwatched`
Dated events on issuers I hold where no thesis is watching. Blind spots, ranked by position size.

```cypher
MATCH (c:catalyst)-[:CATALYST_FOR]->(i:issuer)-[:ISSUES]->(s:security)<-[:HELD_IN]-(p:position)
WHERE date(c.expected_at) >= date($today)
  AND NOT EXISTS { MATCH (:thesis)-[:WATCHES]->(c) }
RETURN i.name, s.ticker, c.title, c.expected_at, round(p.market_value) AS position_value
ORDER BY p.market_value DESC;
```

---

## Macro and sector

### `macro.exposure_rollup`
A macro move resolved into a holdings list, with the rule behind each exposure visible — because a
derived edge you cannot interrogate is worse than no edge.

```cypher
MATCH (m:macroseries {series_id: $series_id})
MATCH (x)-[e:EXPOSED_TO]->(m)
OPTIONAL MATCH (x)<-[:OPERATES_IN]-(i:issuer)
WITH m, e, coalesce(i, x) AS issuer
MATCH (issuer)-[:ISSUES]->(s:security)<-[:HELD_IN]-(p:position)
RETURN m.name AS series, e.direction, e.sensitivity, e.rule,
       issuer.name, s.ticker, round(p.market_value) AS position_value
ORDER BY p.market_value DESC;
```

### `macro.sector_concentration`
How the book actually sits by sector — a different number from how you think it sits.

```cypher
MATCH (p:position)-[:HELD_IN]->(s:security)<-[:ISSUES]-(i:issuer)-[:OPERATES_IN]->(sec:sector)
WITH sec, sum(p.market_value) AS sector_value, collect(s.ticker) AS tickers
WITH collect({sector: sec.name, value: sector_value, tickers: tickers}) AS rows,
     sum(sector_value) AS total
UNWIND rows AS r
RETURN r.sector AS sector, round(r.value) AS value,
       round(100.0 * r.value / total, 1) AS pct_of_book, r.tickers AS tickers
ORDER BY value DESC;
```

---

## Data health

### `health.stale_nodes`
Anything whose data is older than its class TTL ([08](08-provenance-and-trust.md)). Stale data that
looks current is the most dangerous state the graph can be in.

```cypher
UNWIND [
  {label: 'issuer',   ttl_days: 90},
  {label: 'security', ttl_days: 30},
  {label: 'fact',     ttl_days: 120},
  {label: 'holding',  ttl_days: 120},
  {label: 'position', ttl_days: 2}
] AS spec
MATCH (n) WHERE spec.label IN labels(n)
  AND (n.retrieved_at IS NULL
       OR n.retrieved_at < datetime() - duration({days: spec.ttl_days}))
RETURN spec.label AS type, count(n) AS stale_count,
       collect(coalesce(n.name, n.ticker, n.accession))[0..10] AS examples
ORDER BY stale_count DESC;
```

### `health.conflicts`
The same fact from two sources with different values — kept visible rather than silently resolved
([04](04-data-sources.md#source-precedence)).

```cypher
MATCH (f1:fact), (f2:fact)
WHERE f1.tag = f2.tag AND f1.period_end = f2.period_end
  AND f1.unit = f2.unit AND f1.fact_id < f2.fact_id
  AND f1.value <> f2.value
  AND coalesce(f1.restates, '') <> f2.fact_id
  AND coalesce(f2.restates, '') <> f1.fact_id
RETURN f1.tag, f1.period_end,
       f1.value AS value_a, f1.source AS source_a, f1.source_ref AS ref_a,
       f2.value AS value_b, f2.source AS source_b, f2.source_ref AS ref_b,
       abs(f1.value - f2.value) AS delta
ORDER BY delta DESC;
```

### `health.uncited_claims`
Nodes and edges with no provenance. Expected result: zero rows, forever.

```cypher
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN ['issuer','security','fact','filing','insidertransaction','holding'])
  AND (n.source IS NULL OR n.retrieved_at IS NULL)
RETURN labels(n)[0] AS type, count(n) AS uncited,
       collect(coalesce(n.name, n.ticker, n.accession))[0..10] AS examples;
```

### `health.empty_scans`
Enricher runs that wrote nothing. Usually a broken source, a quota, or an expired key — not an empty
world ([02 §3](02-flowsint-primer.md#execution-pipeline)).

```cypher
MATCH (n) WHERE n.scan_id = $scan_id
RETURN count(n) AS nodes_written;
// zero → inspect the scan log; the enricher swallowed an exception
```

---

## Running the library

Phase 1: paste into the Flowsint UI's Cypher view, or `cypher-shell` against the host-local Neo4j.
Phase 4: a runner in `queries/` executes the named set on a schedule and writes the result into
`vault/reviews/YYYY-Www.md`, so the review starts from answers instead of a blank page
([11 — Roadmap](11-roadmap.md)).

Each query file carries a header: name, question in plain English, parameters, what a *suspicious*
answer looks like. The last field matters most — a query whose output you cannot sanity-check is a
query you will eventually trust by mistake.
