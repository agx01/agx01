---
title: "<the claim, in one line>"
note_type: capture
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags: []
entities:
  - issuer:cik:<0000000000>
evidence:
  claim: "<the claim being asserted>"
  bearing: supports           # supports | contradicts
  about: thesis:<slug>        # or exp:<thesis>:<n>
  source: sec_edgar           # sec_edgar | eodhd | tradingview | robinhood | web | operator
  source_ref: "<url or accession>"
  locator: "<10-K 2025, Item 1A / XBRL tag / page>"
  retrieved_at: <YYYY-MM-DD>
  method: reported            # reported | vendor_parsed | derived | third_party_opinion | operator_assertion
  confidence: 0.9             # see docs/08
---

## Claim
<!-- One sentence. -->

## Excerpt
> <short quotation — excerpt only, never a full article body (docs/10)>

## Why it matters
<!-- Which expectation it bears on, and how much it should move conviction. -->

## Counter-reading
<!-- The most credible way this evidence is misleading. Always fill this in. -->
