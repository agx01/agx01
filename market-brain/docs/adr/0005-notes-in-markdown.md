# ADR-0005 — Notes in markdown + git; the graph holds a mirror

- **Status**: Accepted (2026-10-16)
- **Context docs**: [06 — Second brain workflow](../06-second-brain-workflow.md)

## Context

Theses, company memos and post-mortems are prose with structure. They need versioning, diffing,
searchability, and a lifespan measured in decades. The graph needs to reach them, and queries need
their structured parts (expectations, conviction, status).

## Options

1. **Notes as graph nodes only** — everything in Neo4j, long text in node properties.
2. **Notes in markdown with YAML front matter, mirrored into the graph** by an enricher; files authoritative.
3. **Notes in an external app** (Obsidian vault outside the repo, Notion, a database) with a sync layer.

## Decision

Option 2. Markdown files in this repo are authoritative; `note_to_entities` and
`thesis_to_expectations` mirror the structured parts into `Note`, `Thesis` and `Expectation` nodes and
create `DOCUMENTS` / `EXPECTS` / `CITES` edges.

## Why

- **Longevity.** Plain files in git outlive Neo4j, Flowsint and this project. The reasoning layer is
  the irreplaceable part; it must not be hostage to a database.
- **Diffs are the record of changing your mind.** `git log -p vault/theses/x.md` is exactly what a
  post-mortem needs, and no graph store gives it as cheaply.
- **Editing prose in a graph UI is miserable.** Any editor works on markdown; Obsidian-compatible front
  matter means a good editor works well.
- **Queries still work**, because the parts worth querying (status, conviction, expectations, entity
  links) are structured in front matter and mirrored as nodes.

## Consequences

- **Two copies of the structured fields**, so sync direction must be unambiguous: **file → graph**,
  always. The mirror is rebuildable; the file is never overwritten by a graph write.
- Front matter needs a validator, or the mirror silently drifts (phase 2 task).
- Note identity is its repo-relative path, so renames are deliberate events — a rename is a node key
  change, handled by the validator, not by guessing.
- Deletions must propagate: a removed note's `Note` node is marked, not orphaned.
- The vault is committed to a **private** repo, since it holds positions and reasoning
  ([09](../09-security-and-secrets.md)); anything that must never be committed goes in `vault/private/`.
