# 10 — Compliance and ethics

This project points an OSINT investigation platform at public companies, their officers, and your own
brokerage account. That is legitimate research, and it has edges worth naming before any code exists.

## Not investment advice

`market-brain` is a personal research instrument. It produces no recommendations, and its output is
not advice to anyone — including a future version of you who has forgotten the confidence levels. A
well-cited graph makes reasoning *auditable*, not *correct*: every value carries a provenance block
precisely so that confidence can be re-examined ([08](08-provenance-and-trust.md)).

Nothing here is distributed to third parties, and nothing is operated on anyone else's behalf. The
moment either changes, the compliance picture changes with it — in most jurisdictions giving
personalised investment advice for compensation is a regulated activity.

## Upstream ethics policy applies

Flowsint's `ETHICS.md` governs the platform we are building on. Verbatim from the repository
(fetched 2026-10-16):

> The development and use of Flowsint are guided by the principles of the
> [Hippocratic License](https://firstdonoharm.dev/): **The software must not be used in ways that
> violate fundamental human rights.**

It states Flowsint is "designed **strictly for lawful, ethical investigation and research purposes**"
and prohibits, among other uses, unauthorized intrusion, surveillance or data collection, and
harassment, doxxing, blackmail or targeting of individuals. `DISCLAIMER.md` carries the usual
no-warranty, user-responsibility terms.

How that lands on this project, concretely:

| Allowed | Not allowed |
|---|---|
| Corporate entities, their filings, disclosures and public corporate web presence | Any investigation of a private individual as such |
| The **public professional roles** of officers and directors: titles, tenure, board seats, filed transactions | Home addresses, personal contacts, family, personal social accounts, location, or anything in the "private life" column |
| Reading what regulators publish about insiders because the law requires publication | Treating a regulatory disclosure as licence for broader personal profiling |
| Flowsint's website, domain, organization and technology enrichers aimed at company infrastructure | The username/people-search family (e.g. Maigret), breach and credential lookups, phone and email enrichers — **out of scope for this project** |

Capability is not permission. The platform can do more than this project will do, and the narrow scope
is the point: the research question is always "what does this company's situation look like," never
"what can I find out about this person."

## Source terms and licensing

| Source | Constraint | Our posture |
|---|---|---|
| **SEC EDGAR** | Public domain content, but access is governed by a published fair-access policy: a declared `User-Agent` with contact details, and a request-rate ceiling (⚠️ verify current figures at <https://www.sec.gov/os/accessing-edgar-data> — not reachable from this container) | `tools/` refuses to run without a configured contact; conservative rate limit; bulk files for sweeps instead of hammering per-filer endpoints |
| **EODHD** | ⚠️ Vendor terms restrict redistribution; limits are plan-dependent | Personal use, private graph, no republication of vendor values; entitlements checked via `get_user_details` |
| **TradingView** | ⚠️ Terms restrict redistribution and automated extraction | Screening and calendars for personal use; no scraping of the web product; no republication |
| **Robinhood** | Account-linked, your own data | Read-only subset only; order tools never called |
| **Public web** | `robots.txt`, terms of use, copyright | Crawl IR/corporate pages only; respect robots; **store citations and short excerpts, not article bodies** |
| **Flowsint** | Apache-2.0 (effective 2026-01-25, relicensed from AGPL-3.0 with all contributors' written consent) | Keep `LICENSE`/`NOTICE` attribution if any upstream code is vendored; our extensions are separate packages |

**Redistribution rule of thumb**: this graph is a private workbench. Vendor-sourced *values* do not
leave it. A conclusion you reason your way to is yours; the vendor's data points are not.

## Public-information boundary

Insider transactions, 13F holdings and congressional trades are in this system because **the law
requires them to be published**. That makes them fair research material, and it does not make the
people in them targets:

- Aggregate and analyse at the level of the *issuer or institution*, not the individual's life.
- Store only what the filing contains: name, role, transaction, date, filing reference.
- No enrichment of a named insider beyond their public corporate role. The `Person` node deliberately
  has no personal-contact fields ([03](03-ontology.md)).
- `10b5-1` plan sales are flagged, because reading a scheduled sale as a signal is both analytically
  wrong and unfair to the person.

## Market conduct

Worth stating plainly for a system designed to find non-obvious connections:

- This project uses **public information only**. Nothing in it seeks, stores or acts on material
  non-public information.
- If something that looks like MNPI arrives (a leaked document, a non-public figure from a private
  channel), the correct action is to **not** put it in the graph.
- Graph inference from public sources is research, not insider information — but the sourcing
  discipline in [08](08-provenance-and-trust.md) is what keeps that distinction demonstrable.
- No market-manipulative use: the system does not publish, promote or coordinate anything.

## Data minimisation

- `Person` nodes hold public professional attributes only.
- News bodies are not stored — URL, headline, publisher, timestamp, sentiment score, short excerpt.
- Raw payload archives are local, git-ignored, and prunable.
- The vault holds your positions and reasoning: private repo, and `vault/private/` for anything that
  should not be committed at all ([09](09-security-and-secrets.md)).

## Jurisdiction and taxes

Out of scope. This system is not a tax record. Broker tax-lot data (`get_equity_tax_lots`) is read for
post-mortem analysis of realised outcomes, not for tax reporting — use the broker's own documents for
that.

## Review

This document is re-read at the start of each phase, and whenever a new source or enricher family is
added. New source → check its terms before writing the enricher, not after.
