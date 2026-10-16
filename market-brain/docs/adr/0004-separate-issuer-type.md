# ADR-0004 — A separate `Issuer` type, not upstream `Organization`

- **Status**: Accepted (2026-10-16)
- **Context docs**: [03 — Ontology](../03-ontology.md), [02 §2](../02-flowsint-primer.md#types-shipping-upstream-today)

## Context

Flowsint already ships an `Organization` type, and upstream's enricher-builder guidance says to reuse
an existing type where it fits, extend it with optional fields where one or two are missing, and only
create a new type when the entity is conceptually distinct.

Reading `flowsint_types/organization.py`: `Organization` is built around the **French SIRENE/INSEE
company registry**. Its primary field is `name` (typed `Any`), and it carries dozens of registry
fields — `siren`, `nom_raison_sociale`, `nature_juridique`, `tranche_effectif_salarie`, and a long
`siege_*` headquarters block, plus `complements_*` French regulatory flags.

## Decision

Define a separate `Issuer` type for the entity that files with a securities regulator and issues
securities. Keep `Organization` for the OSINT-side notion of a company, and bridge the two with
`SAME_AS` when both exist for one real-world company.

## Why

1. **The merge key is wrong.** `Organization`'s primary field is `name`, so two issuers with the same
   name collapse into one node and a rename splits one issuer into two. Our key must be the CIK or LEI
   ([ADR-0006](0006-registry-ids-as-merge-keys.md)). The primary field cannot be changed without
   editing upstream's type — which [ADR-0002](0002-companion-repo-vs-fork.md) forbids.
2. **Conceptually distinct.** An issuer is a filer and a securities issuer: CIK, SIC, fiscal year end,
   filings, share classes. That is not "a company in a national business registry," and upstream's own
   rule says not to force data into a type it does not belong to.
3. **Extension would be grotesque.** The "one or two optional fields" case does not apply — we would be
   adding a dozen market fields to a type already carrying ~80 French-registry fields, while leaving
   its primary key unusable.
4. **`extra="allow"` is a trap, not a solution.** `FlowsintType` would accept the extra keys silently,
   but undeclared fields are invisible to schema generation and the UI picker
   ([02 §2](../02-flowsint-primer.md#base-class)).

## Consequences

- Flowsint's `Organization`-oriented enrichers (`organization_to_domains`, `organization_information`,
  `organization_to_asn`) do not accept an `Issuer` directly. The bridge is `issuer_to_website` →
  `Website`/`Domain`, where upstream's web enrichers take over
  ([04 §E](../04-data-sources.md#e-web--news-osint-via-flowsints-own-enrichers)).
- Where both an `Issuer` and an `Organization` exist for one company, `SAME_AS` with provenance links
  them rather than a silent merge.
- The same reasoning applies to `Person` vs upstream `Individual`: `Individual` is the OSINT person
  type with contact-shaped fields; our `Person` deliberately holds **only public professional roles**
  ([10](../10-compliance-and-ethics.md)). Bridge with `SAME_AS` only when a research need justifies it.
- If upstream ever generalises `Organization` (registry-agnostic, identifier-keyed), revisit.
