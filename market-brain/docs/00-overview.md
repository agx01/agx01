# 00 — Overview

## The problem

Research output decays. A thesis written in March is, by September, a paragraph whose premises you can
no longer reconstruct: you remember *that* you liked the name, not *why*, not what you expected to
happen by when, and not which of your reasons has since been falsified. Meanwhile the facts you
gathered — a supplier concentration buried in a 10-K risk factor, a cluster of insider sales, the two
holdings that turn out to share one Chinese contract manufacturer — were never connected to anything,
so they can't warn you.

Two distinct failures:

1. **No relationship memory.** Documents store facts; they do not store the edges between facts.
   "Which of my holdings are exposed to this one supplier?" is unanswerable in a note app.
2. **No falsification loop.** A thesis without recorded expectations cannot be wrong, so it is never
   updated — it just quietly stops being true.

## The approach

Model research as a graph investigation and run it on an OSINT platform built for exactly that.

- **Entities** (issuers, securities, people, funds, filings, catalysts, theses) are typed nodes.
- **Relationships** are first-class, labelled, and carry provenance: who said so, from where, when.
- **Enrichers** expand the graph one hop at a time from a seed — the same pattern Flowsint already
  uses for `domain → ip → asn`, applied to `ticker → issuer → filings → insiders → holders`.
- **Notes** (markdown, in git) hold the reasoning that must stay human: the thesis, the expectations
  that would falsify it, the post-mortem.
- **Queries** are saved, named, and re-run — a research question asked once becomes a standing check.

## Goals

| # | Goal | Done looks like |
|---|---|---|
| G1 | Thesis and catalyst tracking | Every active position has a thesis note with dated, falsifiable expectations and linked catalysts; a weekly query lists theses with breached expectations |
| G2 | Relationship / network mapping | Supply chain, customers, competitors, ownership, shared officers and subsidiaries are queryable to 2+ hops from any holding |
| G3 | Flow and insider signal tracking | Form 4 insider activity, congressional trades and institutional position changes land in the graph with filing-level citations and are queryable as time series per issuer |
| G4 | Macro and sector context | Rates, credit, commodity and economic-event series are linked to the sectors and issuers they bear on, so a macro move resolves to a holdings list |
| G5 | Provenance by default | Every node and edge answers "where did this come from, when, and how sure am I" without exception ([08](08-provenance-and-trust.md)) |
| G6 | Second-brain discipline | A standing weekly review that the system itself drives, from queries rather than from memory ([06](06-second-brain-workflow.md)) |

## Non-goals

These are explicitly out of scope, and saying so now prevents the project from becoming a trading platform.

- **No order execution.** Nothing in this system places, modifies or cancels a trade. Broker
  connectivity is read-only by policy ([09](09-security-and-secrets.md), [10](10-compliance-and-ethics.md)).
- **No backtesting engine or alpha model.** This is a knowledge instrument, not a strategy lab. If a
  quantitative backtest is wanted later, it is a separate project that *reads* this graph.
- **No tick-level data warehouse.** Prices enter the graph as summary observations attached to
  entities and events, not as a full historical price store. Price history stays in its source
  (EODHD/TradingView) and is fetched on demand.
- **No real-time alerting infrastructure in phase 1.** Catalyst dates and breached expectations are
  surfaced by scheduled queries, not by a streaming engine.
- **No scraping of sources that forbid it, and no PII beyond what regulators publish.** See
  [10 — Compliance and ethics](10-compliance-and-ethics.md).
- **No multi-user / team features.** Single operator, local-first, private by default.

## Who this is for

One person doing fundamental research on a watchlist of roughly 20–100 names, who already reads
filings and wants the connective tissue kept for them. Everything is local-first: Flowsint stores data
on the machine it runs on, which is also the privacy argument for keeping a personal thesis graph in it.

## Design principles

1. **Upstream stays upstream.** No patches to Flowsint's own packages; extend only through its
   documented registries ([ADR-0002](adr/0002-companion-repo-vs-fork.md)).
2. **A claim without a citation is not a claim.** Provenance is a schema requirement, not a habit.
3. **Merge keys are chosen once and never guessed.** Identity resolution is the hardest part of a
   market graph; the keys are specified in [03 — Ontology](03-ontology.md) and changing one is an ADR.
4. **The notes layer is plain markdown in git.** It must outlive this project, Flowsint, and Neo4j.
5. **Nothing is inferred silently.** Derived edges are labelled as derived, with the rule that produced them.
6. **Read-only by default at every boundary.** Any write to an external system is an explicit,
   separately-approved capability.

## How the phases land

A one-line version of [11 — Roadmap](11-roadmap.md):

- **Phase 0 (this document set)** — ontology, architecture, source analysis, decisions recorded.
- **Phase 1** — Flowsint running locally with the market types registered and three enrichers
  (`ticker → issuer`, `issuer → filings`, `issuer → insider transactions`) writing cited edges.
- **Phase 2** — the brain layer: note vault, thesis lifecycle, bidirectional note ↔ node linking.
- **Phase 3** — network mapping (supply chain, ownership, officers) and the query library.
- **Phase 4** — macro/sector overlay and the scheduled weekly review.
