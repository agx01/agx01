# ADR-0002 — Companion extension packages, not a fork

- **Status**: Accepted (2026-10-16)
- **Context docs**: [01 — Architecture](../01-architecture.md#deployment-overlay), [02 — Flowsint primer](../02-flowsint-primer.md)

## Context

Our market types and enrichers have to run inside Flowsint. Three ways in: fork and patch in-tree,
ship separate packages that register through the decorators, or use Flowsint purely as a graph backend
and keep all logic outside it.

## Options

1. **Fork `reconurge/flowsint`**, add types to `flowsint-types` and enrichers to `flowsint-enrichers`.
   Tightest integration; auto-discovery works with zero cleverness. Every upstream release becomes a merge.
2. **Companion packages** (`market_types`, `market_enrichers`) that import from `flowsint_core` /
   `flowsint_types` and register via `@flowsint_type` / `@flowsint_enricher`, delivered into the runtime
   by a thin derived image. Upstream stays pristine.
3. **Graph backend only** — our own service writes to Neo4j, ignoring the enricher framework. Loses the
   UI, the pipeline, the vault and the scan events: i.e. most of the reason to use Flowsint at all.

## Decision

Option 2 — companion packages, with a thin derived image over the pinned upstream image.

## Why

- The dependency direction (`api → core → enrichers → types`) means our code depends only on `types`
  and `core`; nothing upstream needs to know we exist.
- Upgrading is `FLOWSINT_VERSION=x.y.z` plus a contract-test run, not a merge conflict in someone
  else's package.
- The UI, vault, orchestration and event streaming all keep working, which option 3 throws away.
- If we ever want to contribute a generic type upstream, a clean separate package is the easiest thing
  to lift.

## Risk, and the thing that could break it

Auto-discovery is the weak point. `load_all_types()` walks the `flowsint_types` package's own
`__path__` with `pkgutil.iter_modules`, and the enricher registry behaves analogously
([02 §2](../02-flowsint-primer.md#registration-and-auto-discovery)). A separately installed
distribution may therefore never be imported, so the decorators never run.

Candidate answers, to be settled in [ADR-0003](0003-type-registration-strategy.md):

- publish our modules **into** the `flowsint_types` / `flowsint_enrichers` package paths (namespace
  packages or install-time placement);
- force an explicit import at interpreter start (`sitecustomize`, or an entry point if upstream grows one);
- as a last resort, a **minimal** fork that only adds a plugin hook — and then upstream that hook.

If none of these holds, revisit this ADR rather than quietly letting a fork accumulate patches.

## Consequences

- Both `api` and `celery` must run the derived image: enrichers execute in the worker, and the API
  needs the types to generate schemas.
- `git diff` against upstream stays empty — that invariant is checked, not assumed.
- Our packages carry contract tests pinned to the upstream version.
