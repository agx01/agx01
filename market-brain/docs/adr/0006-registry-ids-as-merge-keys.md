# ADR-0006 — Registry identifiers as merge keys, never tickers

- **Status**: Accepted (2026-10-16)
- **Context docs**: [03 — Ontology](../03-ontology.md#identity-resolution)

## Context

Flowsint merges graph nodes on the single field a type marks `json_schema_extra={"primary": True}`
([02 §2](../02-flowsint-primer.md#the-primary-field-is-the-merge-key)). Choosing that field is
therefore the most consequential decision in the ontology — and the one that is effectively
irreversible once a graph has grown, because every stored node and edge is keyed on it.

Tickers are the obvious candidate and the wrong one:

- **Spelling varies by source**: `BRK.B` (EODHD-ish), `BRK-B` (Yahoo-ish), `BRK.B.US`, `BRKb`, `BRK/B`.
- **Tickers are reused.** A delisted symbol can be reassigned to an unrelated company years later.
- **Tickers change** on renames, mergers and re-listings (`FB` → `META`, `TWTR` → nothing).
- **A ticker is not an issuer.** One issuer has several share classes and several listings; one symbol
  on two exchanges is not one instrument.
- **13F reports CUSIPs**, Form 4 reports CIKs, vendors report their own codes. Nothing authoritative
  speaks in tickers.

## Decision

Merge keys are **source-qualified registry identifiers**, in a canonical string form with an explicit
namespace prefix:

| Entity | Key | Fallback chain |
|---|---|---|
| `Issuer` | `cik:0000320193` | → `lei:<20>` → `slug:<normalized-name>` |
| `Security` | `figi:BBG000B9XRY4` | → `mic:XNAS:AAPL` → `eodhd:AAPL.US` |
| `Person` | `cik:0001214156` | → `slug:<name>@<issuer_id>` |
| `Institution` | `cik:<filer>` | → `lei:` → `slug:` |
| `Filing` | `accession` | — (globally unique) |

Tickers, CUSIPs, ISINs, SEDOLs and per-vendor codes are **indexed alias properties**. All ingestion
enters through `alias_to_security`, which resolves alias → key before anything else is written
([05](../05-enricher-catalog.md)).

## Why the namespace prefix

A bare `0000320193` cannot say whether it is a CIK, and a bare `AAPL.US` cannot say whose convention it
follows. The prefix makes the key self-describing, makes the fallback chain visible in the data, and
makes "how confident is this identity" answerable by looking at a node — a `slug:` key is a flag that
resolution has not finished.

## Consequences

- **A resolution step is mandatory** before any write. That is a feature: it is the one chokepoint
  where identity errors can be caught.
- **`SAME_AS` instead of silent merging.** When a `slug:`-keyed node later resolves to a CIK, the two
  are linked with provenance and collapsed deliberately, keeping the evidence for why they are one thing.
- `Security` carries `listed_from` / `listed_to` / `status`, so ticker reuse resolves by time window.
- `get_symbol_change_history` (EODHD) and SEC `former_names` are **ingestion inputs**, not trivia.
- Adding a new source means writing its alias mapping, not inventing a new key.
- Changing a merge key later requires a migration that rewrites every node and edge of that type —
  which is exactly why this is an ADR.
