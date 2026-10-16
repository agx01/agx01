# ADR-0001 — Flowsint as the graph substrate

- **Status**: Accepted (2026-10-16)
- **Context docs**: [01 — Architecture](../01-architecture.md), [02 — Flowsint primer](../02-flowsint-primer.md)

## Context

The project needs: typed entities, labelled relationships with provenance, a way to expand a graph one
hop at a time from external sources, a secret store, task orchestration, and a UI for reading the
result. Written from scratch that is months of work before the first research question gets answered.

## Options

1. **Build on Flowsint** — an Apache-2.0 OSINT investigation platform with exactly this architecture:
   typed entity registry, enricher pipeline, batched graph writes, vault, Celery, SSE scan events, graph UI.
2. **Raw Neo4j + custom ingestion** — total control, no constraints from someone else's model.
3. **A note-first tool with graph features** (Obsidian + plugins, Logseq, Roam) — great at notes, weak
   at typed ingestion from APIs and at provenance.
4. **A commercial graph/intelligence platform** — capable, expensive, and it owns your data.

## Decision

Build on Flowsint (option 1).

## Why

- The enricher model *is* the research model: seed an entity, expand a hop, cite the source. Nothing
  had to be bent to fit.
- The boring 80% exists and is verified working: registry, pipeline, vault, batched writes, UI
  ([02](../02-flowsint-primer.md)).
- Extension points are explicit decorators, and upstream even ships a skill documenting how to add
  types and enrichers.
- Apache-2.0 and local-first: a private thesis graph does not leave the machine.
- OSINT lineage is a bonus, not a detour — company web presence, infrastructure and officer networks
  are genuinely part of fundamental research, and those enrichers already exist.

## Costs accepted

- **Early-stage upstream.** Breaking changes are likely. Mitigated by pinning `FLOWSINT_VERSION`,
  keeping our code out of upstream's tree, and contract-testing against the pinned version.
- **An opinionated model.** One primary field per type as the merge key, lowercase Neo4j labels, UI
  categories. We design within it rather than fight it.
- **Exceptions are swallowed** by `Enricher.execute()`, so our enrichers must log per item
  ([05](../05-enricher-catalog.md)).
- **Docker socket mounted** into `api`/`celery` upstream — a real privilege, and a reason to keep the
  stack local ([09](../09-security-and-secrets.md)).

## Revisit if

Upstream is abandoned; registration of out-of-tree code proves impossible without a fork *and*
maintaining a fork proves costly; or the market ontology ends up fighting the platform's model more
than it benefits from it. In any of those cases the types, enrichers and queries are portable — they
are mostly Pydantic models, HTTP clients and Cypher.
