"""Flowsint enrichers that build the market research graph.

Each enricher is one hop: one input type, one output type, one source, one set of edges
(../docs/05-enricher-catalog.md). Importing this package registers all of them via
``@flowsint_enricher``; how that import is guaranteed inside a running Flowsint is
../docs/adr/0003-type-registration-strategy.md.

Phase 1 — the spine::

    Phrase   --alias_to_security-->               Security
    Security --security_to_issuer-->              Issuer      (ISSUES)
    Issuer   --issuer_to_filings-->               Filing      (FILED)
    Issuer   --issuer_to_facts-->                 Fact        (FILED, REPORTS_FACT)
    Issuer   --issuer_to_insider_transactions-->  InsiderTransaction
                 (DISCLOSED_IN, REPORTED_BY, TRANSACTED_IN)
"""

from __future__ import annotations

from .issuer.to_facts import IssuerToFactsEnricher
from .issuer.to_filings import IssuerToFilingsEnricher
from .issuer.to_insider_transactions import IssuerToInsiderTransactionsEnricher
from .market_enricher import MarketEnricher
from .phrase.to_security import AliasToSecurityEnricher
from .registry import load_market_enrichers, market_enricher_names
from .security.to_issuer import SecurityToIssuerEnricher

__version__ = "0.1.0"

#: The enrichers this package registers, in the order a research run uses them.
MARKET_ENRICHERS: tuple[type[MarketEnricher], ...] = (
    AliasToSecurityEnricher,
    SecurityToIssuerEnricher,
    IssuerToFilingsEnricher,
    IssuerToFactsEnricher,
    IssuerToInsiderTransactionsEnricher,
)

__all__ = [
    "MARKET_ENRICHERS",
    "AliasToSecurityEnricher",
    "IssuerToFactsEnricher",
    "IssuerToFilingsEnricher",
    "IssuerToInsiderTransactionsEnricher",
    "MarketEnricher",
    "SecurityToIssuerEnricher",
    "load_market_enrichers",
    "market_enricher_names",
]
