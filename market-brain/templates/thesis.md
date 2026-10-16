---
title: "<Company> — <the claim in one line>"
note_type: thesis
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
status: draft                 # draft | active | paused | closed | invalidated
tags: []
entities:
  - issuer:cik:<0000000000>
  - security:figi:<BBG...>
  - sector:gics:<code>
thesis:
  direction: long             # long | short | watch
  conviction: 3               # 1-5
  horizon: 12m
  opened: <YYYY-MM-DD>
expectations:                 # at least one with breaks_thesis: true before status: active
  - id: 1
    statement: "<checkable claim with a number and a date>"
    metric: <metric_id>
    comparator: ">="          # >= | <= | == | crosses
    target: <value>
    due_by: <YYYY-MM-DD>
    breaks_thesis: true
    status: pending           # pending | met | missed | void
sources: []
---

## The claim
<!-- One paragraph. If it needs three, the thesis is two theses. -->

## Why the market may be wrong
<!-- What do you believe that consensus does not, and why is that gap there?
     "It's cheap" is not a thesis; "it's cheap because X is mispriced, and X resolves by Y" is. -->

## What has to be true
<!-- The chain of conditions. Each link that is checkable belongs in `expectations` above. -->

## What would make me wrong
<!-- Be specific and dated. Then mirror the hardest ones into `expectations` with breaks_thesis: true. -->

## Key relationships (from the graph)
<!-- Suppliers, customers, competitors, shared holders, macro exposures.
     Paste the query you ran so it can be re-run. -->

## Position
<!-- Size, entry, what would make you add or trim. Independent of the thesis being right. -->

## Evidence log
| Date | Claim | For/Against | Source | Confidence |
|---|---|---|---|---|
| | | | | |

## Conviction history
| Date | Conviction | Why it changed |
|---|---|---|
| <YYYY-MM-DD> | 3 | initial |
