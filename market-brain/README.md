# market-brain

**A graph-native second brain for stock market research, built on [Flowsint](https://github.com/reconurge/flowsint).**

Status: **phase 1 in progress** — design documentation complete, with the entity types
([`market_types/`](market_types/README.md), 251 tests) and the five spine enrichers
([`market_enrichers/`](market_enrichers/README.md), 147 tests) drafted; both mypy strict. Nothing has
run inside a real Flowsint yet: that is [ADR-0003](docs/adr/0003-type-registration-strategy.md), the
phase-1 gate. See the [roadmap](docs/11-roadmap.md).
Created: 2026-10-16

---

## What this is

Most stock research dies in the place it was written: a note app, a spreadsheet tab, a chat log.
The facts are there, but the *relationships* between them — this supplier feeds that customer, this
officer sold shares three weeks before that guidance cut, these four holdings share one end market —
are never captured, so they can never be queried.

`market-brain` treats equity research as a **graph investigation** instead of a document pile.
It reuses [Flowsint](https://github.com/reconurge/flowsint), an open-source OSINT platform whose
whole model is "entities, relationships, enrichers, provenance," and extends it with a market
ontology (issuers, securities, filings, insiders, holders, catalysts, theses) plus enrichers that
pull from market and regulatory data sources.

Three layers, one system:

| Layer | Substrate | Holds |
|---|---|---|
| **Graph** | Neo4j, via Flowsint | Entities and the relationships between them, every edge carrying provenance |
| **Notes** | Markdown in this repo (Obsidian-compatible) | Theses, company memos, catalyst logs, post-mortems — human reasoning |
| **Query** | Cypher library + saved questions | The repeatable research questions you ask every week |

The graph is what you *can't* keep in your head. The notes are what you *think*. The query library is
how the first one keeps the second one honest.

## Why Flowsint rather than building a graph app

Flowsint already solves the boring 80%: a typed entity registry, an enricher execution pipeline with
batched graph writes, a secret vault, Celery task orchestration, real-time scan event streaming, and a
graph UI with saved investigations ("sketches"). Its extension points are explicit — a decorator to
register a type, a decorator to register an enricher — and documented in-repo. See the
[Flowsint primer](docs/02-flowsint-primer.md) for the verified internals.

What it does **not** have is any notion of a security, an issuer, a filing or a thesis. That gap is
this project.

## Documentation

Read in order; each doc stands alone but they build.

| Doc | What it answers |
|---|---|
| [00 — Overview](docs/00-overview.md) | Goals, non-goals, who this is for, what "done" means |
| [01 — Architecture](docs/01-architecture.md) | Components, deployment topology, data flow, sequence of a research run |
| [02 — Flowsint primer](docs/02-flowsint-primer.md) | How Flowsint actually works, read from source, with citations |
| [03 — Ontology](docs/03-ontology.md) | Every node type, property, merge key and relationship label |
| [04 — Data sources](docs/04-data-sources.md) | EODHD, SEC EDGAR, TradingView, Robinhood, web OSINT — coverage, limits, licensing |
| [05 — Enricher catalog](docs/05-enricher-catalog.md) | The enrichers to build, with input/output types and params |
| [06 — Second brain workflow](docs/06-second-brain-workflow.md) | Note taxonomy, thesis lifecycle, review cadence, templates |
| [07 — Query library](docs/07-query-library.md) | The Cypher that answers real research questions |
| [08 — Provenance and trust](docs/08-provenance-and-trust.md) | Evidence model, confidence, contradiction handling, staleness |
| [09 — Security and secrets](docs/09-security-and-secrets.md) | Vault usage, env hardening, exposure rules |
| [10 — Compliance and ethics](docs/10-compliance-and-ethics.md) | Upstream ethics policy, source ToS, personal-use boundaries |
| [11 — Roadmap](docs/11-roadmap.md) | Phases with acceptance criteria |
| [12 — Environment notes](docs/12-environment-notes.md) | What is reachable from which machine; sandbox egress findings |
| [ADRs](docs/adr/) | Decisions, with the alternatives that lost and why |
| [`market_types/`](market_types/README.md) | The ontology in code: six types, merge keys, identifier checksums, provenance mixin |
| [`market_enrichers/`](market_enrichers/README.md) | The five spine enrichers, the EDGAR and EODHD clients, and the rate-limited caching fetch layer |
| [Glossary](docs/glossary.md) | Flowsint terms, market terms, this project's terms |
| [References](docs/references.md) | Every external source cited, with verification status |

## Repository layout (target)

```
market-brain/
├── docs/                      # design documentation
├── templates/                 # note templates for the brain layer
├── market_types/              # ✅ flowsint_types-compatible entity types + tests
├── market_enrichers/          # ✅ enrichers, EDGAR/EODHD clients, fetch layer + tests
├── MIGRATION.md               # how this moves into its own repo
└── (next)
    ├── deploy/                # docker-compose overlay onto upstream Flowsint
    ├── queries/               # Cypher library
    └── vault/                 # the markdown brain (notes, theses, memos)
```

## Not investment advice

This is a personal research instrument. Nothing it produces is a recommendation, and the graph being
confident is not the same as the graph being right. See [10 — Compliance and ethics](docs/10-compliance-and-ethics.md).
