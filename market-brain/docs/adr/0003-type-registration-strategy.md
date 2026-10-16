# ADR-0003 — How out-of-tree types and enrichers register

- **Status**: **Proposed** — the first thing phase 1 must settle
- **Context docs**: [02 §2](../02-flowsint-primer.md#registration-and-auto-discovery), [ADR-0002](0002-companion-repo-vs-fork.md)

## Context

Verified from source: `flowsint_types.registry.load_all_types()` iterates
`pkgutil.iter_modules(flowsint_types.__path__)` and imports each non-private module to trigger
`@flowsint_type`. It caches on a `_types_loaded` flag and **swallows import errors with a warning to
stderr**. The enricher registry follows the same auto-discovery pattern, and upstream's own guidance
is "do not edit any registry file; restart the API so auto-discovery loads the new enricher."

So a module we install elsewhere is never imported, the decorator never runs, and our type does not
exist as far as the API, the UI schema generation or the Neo4j writer is concerned. Worse, a failure
here is **silent** — a stderr warning in a container log.

## Options

### A. Namespace-package placement
Ship `market_types` so its modules land inside the `flowsint_types` package directory (or make that
package a namespace package upstream, which it currently is not).
- *Pro*: auto-discovery works untouched; zero runtime hacks.
- *Con*: writing into another distribution's directory is fragile across image rebuilds and offends
  packaging conventions; probably needs a `Dockerfile` copy step rather than a plain `pip install`.

### B. Derived image with an explicit import hook
`FROM ghcr.io/reconurge/flowsint-api:<pinned>`, `pip install` our packages, then guarantee an import —
a `sitecustomize.py` on the path, or `PYTHONSTARTUP`-style shim, that does
`import market_types; import market_enrichers`.
- *Pro*: standard packaging; version-pinned and visible in the image digest; survives upstream layout changes.
- *Con*: `sitecustomize` is a blunt instrument; import order matters (our modules must import after
  `flowsint_types` is importable, which is fine, since we import *from* it).

### C. Upstream plugin hook (the right long-term answer)
Contribute an entry-point group (e.g. `flowsint.types`, `flowsint.enrichers`) that `load_all_types()`
also scans.
- *Pro*: supported, explicit, benefits everyone; our package becomes a normal plugin.
- *Con*: needs an upstream PR and a release; cannot be relied on for phase 1.

### D. Dev-only bind mount
Mount our source into the container and import it via B's hook.
- *Pro*: fastest iteration loop.
- *Con*: not reproducible; invisible in the image digest. **Dev only.**

## Proposed decision

**B for the runtime, D for the inner loop, C as a contribution once B is proven.** Keep A in reserve if
the import hook turns out to fight the published images.

Phase 1 spike, in order:
1. Confirm whether a `pip install`ed `market_types` is discovered at all (expected: no).
2. Build the derived image with the import hook; confirm the type appears in the API's type list and
   the UI picker, and that a node is written with the expected lowercase Neo4j label.
3. Repeat for an enricher: it must appear in the enricher list and execute from the UI.
4. Record the answer here, with the image build in `deploy/`.

## Open sub-questions

- Does the UI type picker require an entry in upstream's `_get_category_definitions()` for a new
  category to render (**Q6**)? If so, our types ship with categories that already exist, or we accept a
  blank category and upstream the definition.
- Does `flowsint-api` need our packages too, or only `celery`? (Expected: both — schema generation lives
  in the API.)
- Do Neo4j constraints belong in upstream's `neo4j-migrations/` or our own startup step (**Q4**)?
