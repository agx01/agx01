# 04 — Data sources

Four source families, chosen so that each important fact has at least two independent paths — the
regulatory record for authority, a vendor API for breadth and convenience.

**Verification status matters here.** Facts marked ✅ were verified from the live tool inventory or
source on 2026-10-16. Facts marked ⚠️ come from prior knowledge and **could not be re-verified from
the build container**, whose network policy denied `sec.gov`, `flowsint.io` and `cdn.jsdelivr.net`
([12 — Environment notes](12-environment-notes.md)). Confirm every ⚠️ item against the vendor's own
documentation before writing an enricher against it.

---

## A. EODHD (MCP server) — the breadth source

✅ Connected as an MCP server in the authoring environment; the tool inventory below is read directly
from it. Roughly 100 tools, which makes it the widest single source available to this project.

### Tools that map onto the ontology

| Ontology target | EODHD tools |
|---|---|
| `Security`, `Issuer` resolution | `resolve_ticker`, `get_stocks_from_search`, `get_symbol_change_history`, `get_exchange_tickers`, `get_exchanges_list`, `get_exchange_details` |
| `Fact`, fundamentals | `get_fundamentals_data`, `get_bulk_fundamentals`, `get_sec_company_financials`, `get_sec_company_ratios`, `get_sec_company_ttm`, `get_sec_company_growth`, `get_sec_company_snapshot` |
| `Segment` | `get_sec_company_segments` |
| `Filing` | `get_sec_filings`, `get_sec_companies` |
| `InsiderTransaction` | `get_insider_transactions`, `get_insider_transactions_form4` |
| Congressional trades | `get_congressional_trades` |
| `NewsItem`, sentiment | `get_company_news`, `get_sentiment_data`, `get_news_word_weights` |
| `Catalyst` | `get_upcoming_earnings`, `get_earnings_trends`, `get_upcoming_dividends`, `get_upcoming_splits`, `get_upcoming_ipos`, `get_economic_events` |
| Prices (on demand, not stored) | `get_historical_stock_prices`, `get_intraday_historical_data`, `get_live_price_data`, `get_realtime_minute_bars`, `get_us_live_extended_quotes` |
| Corporate actions | `get_historical_dividends`, `get_historical_splits`, `get_asx_corporate_actions`, `get_historical_market_cap` |
| `MacroSeries`, `Observation` | `get_macro_indicator`, `get_rates_policy_rates`, `get_rates_reference_rates`, `get_rates_funding_stress`, `get_ust_yield_rates`, `get_ust_bill_rates`, `get_ust_long_term_rates`, `get_ust_real_yield_rates`, `get_historical_commodity_prices`, `get_real_estate_*` |
| Credit context | `get_credit_sovereign_cds_spreads`, `get_credit_sovereign_credit_ratings`, `get_credit_sovereign_default_spreads`, `get_credit_sovereign_risk_premium`, `get_credit_corporate_hqm_yields`, `get_credit_corporate_cmdi`, `get_credit_cds_market_aggregates` |
| Index membership | `mp_indices_list`, `mp_index_components`, `get_cboe_indices_list`, `get_cboe_index_data` |
| `SanctionsEntity` | `get_sanctions_entities`, `get_sanctions_programs`, `get_sanctions_sources`, `get_sanctions_vessels` |
| ESG | `get_mp_investverte_esg_view_company`, `..._view_sector`, `..._view_country`, `..._list_*` |
| Screening | `stock_screener`, `get_mp_praams_smart_screener_equity`, `get_mp_praams_smart_screener_bond` |
| Technical context | `get_technical_indicators`, `get_support_resistance_levels` |
| Options | `get_us_options_contracts`, `get_us_options_eod`, `get_us_options_underlyings` |
| Entitlement check | `get_user_details` |

### How we use it
- **Primary for**: resolution, fundamentals breadth, news + sentiment, macro/rates/credit, calendars,
  index membership, sanctions screening.
- **Secondary for**: SEC-derived data, where EDGAR is authoritative but EODHD's parsed form is far
  cheaper to consume (`get_sec_*`, `get_insider_transactions_form4`).
- **Provenance**: vendor-parsed data records `source=eodhd`, the tool name as `endpoint`, and — when
  the payload carries it — the underlying accession number, so a vendor fact still points at a filing.

### Constraints
- ⚠️ Rate limits and daily call allowances are plan-dependent; check `get_user_details` at startup and
  treat the returned entitlements as the budget. Confirm current limits in EODHD's own docs.
- ⚠️ Redistribution of vendor data is restricted by EODHD's terms. The graph is personal and private;
  do not publish vendor-sourced values ([10](10-compliance-and-ethics.md)).
- Several tools are marketplace add-ons (`get_mp_*`) requiring separate entitlement.

---

## B. SEC EDGAR — the authority source

The regulatory record. When EODHD and EDGAR disagree, **EDGAR wins and the discrepancy is recorded**
([08](08-provenance-and-trust.md)).

### Endpoints (⚠️ from prior knowledge — re-verify at <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>)

| Purpose | Endpoint |
|---|---|
| Filing history for a filer | `https://data.sec.gov/submissions/CIK##########.json` (10-digit zero-padded) |
| All XBRL facts for a filer | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| One concept's history | `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/Revenues.json` |
| One concept across all filers | `https://data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY2025Q1I.json` |
| Ticker → CIK map | `https://www.sec.gov/files/company_tickers.json` |
| Full-text search | `https://efts.sec.gov/LATEST/search-index?q=...` |
| Daily/quarterly indexes | `https://www.sec.gov/Archives/edgar/full-index/` |
| A filing's files | `https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/` |

### Access rules (⚠️ verify at <https://www.sec.gov/os/accessing-edgar-data>)
- A **declared `User-Agent`** naming the requester with contact email is required. Our `tools/` client
  sets it from configuration and refuses to run without it.
- A published **fair-access request-rate ceiling** applies (historically 10 requests/second). The
  client enforces a conservative limit below whatever the current published figure is, with backoff on
  429/403.
- Bulk files exist (`companyfacts.zip`, financial statement data sets) and are the right tool for
  anything resembling a sweep — per-filer polling at scale is the behaviour the fair-access policy
  exists to discourage.

### Forms we parse
| Form | Yields |
|---|---|
| `10-K` / `10-Q` | `Fact` (XBRL), `RiskFactor`, `Segment`, customer/supplier concentration disclosures, `SUBSIDIARY_OF` (Exhibit 21), `AUDITED_BY` |
| `8-K` | `Catalyst` outcomes, item-coded events (e.g. auditor change, officer departure) |
| `4` | `InsiderTransaction` + `Person`, with the `10b5-1` plan flag |
| `13F-HR` | `Holding` → `Institution`, quarterly, CUSIP-keyed |
| `SC 13D/G` | >5% ownership and intent |
| `DEF 14A` | `OFFICER_OF` / `DIRECTOR_OF`, compensation, related-party transactions |

### Access from a restricted network
`sec.gov` was **denied by this container's egress policy** (verified: `CONNECT tunnel failed,
response 403`). Two fallbacks keep the SEC leg working when direct access is unavailable:
EODHD's `get_sec_*` family, and Robinhood's `get_sec_filing`, `get_sec_filing_index`,
`get_sec_filing_facts`, `get_sec_filing_facts_catalog`. Both are vendor intermediaries, so provenance
records the intermediary *and* the accession number it cites.

---

## C. TradingView (MCP server) — screening, technicals, calendars

✅ Connected as an MCP server.

| Use | Tools |
|---|---|
| Screening into the watchlist | `mcp-tv-run-screener`, `mcp-tv-get-screener-columns` |
| Symbol metadata and resolution cross-check | `mcp-tv-search-symbols`, `mcp-tv-get-symbol-data`, `mcp-tv-get-symbol-data-batch` |
| Prices | `mcp-tv-get-ohlcv` |
| Fundamentals cross-check | `mcp-tv-get-financials`, `mcp-tv-get-financial-history` |
| `Catalyst` | `mcp-tv-get-earnings-calendar`, `mcp-tv-get-dividends-calendar`, `mcp-tv-get-economic-calendar` |
| Macro | `mcp-tv-get-economic-data`, `mcp-tv-get-economic-symbols` |
| Sell-side context | `mcp-tv-get-forecasts`, `mcp-tv-get-technicals-rating` |
| News | `mcp-tv-get-news`, `mcp-tv-get-news-story` |
| Filings/documents | `mcp-tv-get-documents`, `mcp-tv-get-document-view` |
| Watchlists | `mcp-watchlist-list-watchlists`, `mcp-watchlist-get-watchlist`, `mcp-watchlist-create-watchlist`, `mcp-watchlist-add-to-watchlist`, `mcp-watchlist-remove-from-watchlist`, `mcp-watchlist-update-watchlist`, `mcp-watchlist-delete-watchlist` |
| Alerts | `mcp-tv-get-alerts`, `mcp-tv-create-alert`, `mcp-tv-update-alert`, `mcp-tv-delete-alert`, `mcp-tv-get-alerts-log`, `mcp-tv-list-alerts`, `mcp-tv-start/stop/restart-alerts` |

Notes:
- Watchlists are the natural **scope boundary**: a TradingView watchlist defines which issuers the
  scheduled jobs maintain. Watchlist and alert tools **write** to your account — they stay behind an
  explicit approval and are never called by an enricher ([09](09-security-and-secrets.md)).
- Technical ratings and analyst forecasts enter the graph as `Evidence` with `method=third_party_opinion`,
  never as facts.
- ⚠️ TradingView's terms restrict redistribution and automated extraction; treat output as personal use only.

---

## D. Robinhood (MCP server) — your own book, read-only

✅ Connected. **Policy: read-only. The order-placement tools are never called by this project.**

| Use | Tools |
|---|---|
| `Position`, portfolio | `get_portfolio`, `get_accounts`, `get_equity_positions`, `get_option_positions`, `get_crypto_positions`, `get_equity_tax_lots` |
| Realised outcomes for post-mortems | `get_realized_pnl`, `get_pnl_trade_history`, `get_equity_orders`, `get_option_orders` |
| Fundamentals / ratings cross-check | `get_equity_fundamentals`, `get_financials`, `get_equity_analyst_ratings` |
| `Catalyst` | `get_earnings_calendar`, `get_earnings_results` |
| SEC fallback path | `get_sec_filing`, `get_sec_filing_index`, `get_sec_filing_facts`, `get_sec_filing_facts_catalog` |
| Congressional trades (second source) | `get_politician_trades` |
| Quotes / technicals | `get_equity_quotes`, `get_equity_historicals`, `get_equity_technical_indicators`, `get_index_quotes` |

**Explicitly excluded**: `place_equity_order`, `place_option_order`, `place_crypto_order`,
`place_advanced_order`, `cancel_*`, `exercise_option`, `review_*`/`preview_*` order tools,
`create_alert`, `create_watchlist`, `update_watchlist`, `follow_watchlist`, `create_scan`, `run_scan`.
This exclusion is a design invariant, not a preference ([10](10-compliance-and-ethics.md)).

Why the book belongs in the graph at all: a thesis without the position is an opinion, and a
post-mortem without realised P&L is a story. `Position` + `get_realized_pnl` make the review loop
honest — and keep "what am I actually exposed to" answerable in one hop.

---

## E. Web / news OSINT via Flowsint's own enrichers

The leg where using an OSINT platform pays for itself. Once an `Issuer` carries a `website`, upstream
enrichers run unmodified on it[^readme]:

| Upstream enricher family | Research use |
|---|---|
| Website crawler, links, text extraction | IR pages, press releases, careers pages (hiring as a demand proxy), product pages |
| Domain → website / root domain / subdomain discovery | Brand and product portfolio discovery; staging or acquisition-related hosts |
| WHOIS, domain history | Corporate-structure and acquisition timing hints |
| Domain → ASN, IP info, ASN → CIDR | Infrastructure footprint; cloud-vendor dependency as a cost signal |
| Web trackers, technology detection | Which vendors a company actually runs (a usable read on SaaS adoption) |
| Organization → domains / information | Subsidiary and brand mapping |
| Individual → affiliations / domains | Officer and director network expansion |

Two rules for this leg:

1. **Public, published information only**, and only on corporate entities and the public professional
   roles of their officers. Upstream's `ETHICS.md` prohibits harassment, doxxing and surveillance; the
   person-oriented enrichers (e.g. the Maigret username search) are **out of scope for this project**
   regardless of what the platform can do ([10](10-compliance-and-ethics.md)).
2. **`robots.txt` and terms are respected.** The crawler is pointed at IR and corporate pages, not at
   paywalled or access-controlled content.

---

## Source precedence

When two sources disagree about the same fact:

1. **SEC EDGAR filing** (as filed, with accession)
2. **Vendor-parsed SEC data** (EODHD `get_sec_*`, Robinhood `get_sec_filing_facts`)
3. **Vendor fundamentals** (EODHD, TradingView, Robinhood)
4. **Third-party opinion** (analyst forecasts, technical ratings) — `Evidence`, never `Fact`
5. **Press and web** — context and timing, with the publisher recorded

A disagreement is never silently resolved: the lower-precedence value is kept as `Evidence` with
`method=conflicting` and surfaced by the conflicts query in [07](07-query-library.md).

## Cost and quota posture

| Source | Marginal cost | Posture |
|---|---|---|
| SEC EDGAR | free, rate-limited | Authoritative sweeps; bulk files for anything wide |
| EODHD | plan-metered | Default for breadth; cache aggressively; check entitlements before a sweep |
| TradingView | subscription | Screening and calendars; low call volume |
| Robinhood | account-linked | Your book only; low volume |
| Web OSINT | compute only | Cheap but slow; run per-issuer on demand |

Caching in `tools/` with per-class TTLs — immutable (a filed document) / slow (fundamentals,
quarterly) / fast (quotes, news) — is what makes a weekly full refresh affordable.

[^readme]: Upstream enricher inventory from Flowsint's `README.md`, fetched 2026-10-16. See [02 — Flowsint primer](02-flowsint-primer.md).
