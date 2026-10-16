"""The provenance block every market node carries.

A claim without a citation is not a claim (docs/08-provenance-and-trust.md). These
fields are mixed into every entity type rather than bolted on per enricher, so
``health.uncited_claims`` can be a hard invariant instead of a convention.

Field types are restricted to what a Neo4j property can hold — primitives, dates and
lists of primitives — because nested models cannot be stored as node properties.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final, Literal, Optional, Self

from pydantic import BaseModel, Field, model_validator

Source = Literal[
    "sec_edgar",  # as filed with the SEC
    "eodhd",  # EODHD API / MCP
    "tradingview",  # TradingView API / MCP
    "robinhood",  # broker, read-only
    "web",  # crawled public page
    "operator",  # your own judgement
    "derived",  # computed by one of our rules
]

Method = Literal[
    "reported",  # straight from a regulatory filing
    "vendor_parsed",  # a vendor's parse of regulatory data
    "derived",  # produced by one of our rules; requires `rule`
    "third_party_opinion",  # analyst target, technical rating
    "operator_assertion",  # your own claim
    "conflicting",  # retained loser of a source disagreement
]

FetchOutcome = Literal["ok", "partial", "cached_stale", "source_error"]

#: Default confidence per method, from the scale in docs/08-provenance-and-trust.md.
DEFAULT_CONFIDENCE: Final[dict[str, float]] = {
    "reported": 1.0,
    "vendor_parsed": 0.8,
    "derived": 0.6,
    "third_party_opinion": 0.3,
    "operator_assertion": 0.2,
    "conflicting": 0.5,
}

#: Ceiling on an operator's own assertion — opinions do not get to look like filings.
OPERATOR_CONFIDENCE_CEILING: Final[float] = 0.2


def default_confidence(method: str | None) -> float | None:
    """Confidence to use when an enricher does not state one."""
    if method is None:
        return None
    return DEFAULT_CONFIDENCE.get(method)


def provenance(
    source: Source,
    *,
    source_ref: str | None = None,
    locator: str | None = None,
    retrieved_at: datetime | None = None,
    as_of: date | None = None,
    method: Method = "reported",
    confidence: float | None = None,
    scan_id: str | None = None,
    rule: str | None = None,
    fetch_outcome: FetchOutcome = "ok",
) -> dict[str, Any]:
    """Build the provenance kwargs for a node, defaulting the fiddly parts.

    >>> p = provenance("sec_edgar", source_ref="https://www.sec.gov/...", scan_id="s1")
    >>> p["method"], p["confidence"], p["fetch_outcome"]
    ('reported', 1.0, 'ok')
    """
    return {
        "source": source,
        "source_ref": source_ref,
        "locator": locator,
        "retrieved_at": retrieved_at or datetime.now(UTC),
        "as_of": as_of,
        "method": method,
        "confidence": default_confidence(method) if confidence is None else confidence,
        "scan_id": scan_id,
        "rule": rule,
        "fetch_outcome": fetch_outcome,
    }


class Provenance(BaseModel):
    """Mixin: where a value came from, when, and how much it is worth.

    Not decorated with ``@flowsint_type`` — it is not an entity and must never become a
    node label.
    """

    source: Optional[Source] = Field(
        None, description="Source family this value came from", title="Source"
    )
    source_ref: Optional[str] = Field(
        None,
        description="Citation target: filing index URL, API endpoint or article URL",
        title="Source Reference",
    )
    locator: Optional[str] = Field(
        None,
        description="Where inside the source: filing item, XBRL tag, page, JSON pointer",
        title="Locator",
    )
    retrieved_at: Optional[datetime] = Field(
        None,
        description="UTC time the value was fetched (not the date it describes)",
        title="Retrieved At",
    )
    as_of: Optional[date] = Field(
        None, description="Date the value itself describes", title="As Of"
    )
    method: Optional[Method] = Field(
        None, description="How the value was obtained", title="Method"
    )
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Epistemic standing, 0-1", title="Confidence"
    )
    scan_id: Optional[str] = Field(
        None, description="Enricher run that wrote this value", title="Scan ID"
    )
    rule: Optional[str] = Field(
        None,
        description="For derived values: the rule or query that produced it",
        title="Rule",
    )
    fetch_outcome: Optional[FetchOutcome] = Field(
        None,
        description="Outcome of the fetch, so 'no data' and 'fetch failed' differ",
        title="Fetch Outcome",
    )

    @model_validator(mode="after")
    def _check_provenance_coherence(self) -> Self:
        if self.method == "derived" and not self.rule:
            raise ValueError("method='derived' requires `rule` naming the rule applied")
        if (
            self.method == "operator_assertion"
            and self.confidence is not None
            and self.confidence > OPERATOR_CONFIDENCE_CEILING
        ):
            raise ValueError(
                "operator assertions are capped at confidence "
                f"{OPERATOR_CONFIDENCE_CEILING}; got {self.confidence}"
            )
        return self

    def is_cited(self) -> bool:
        """True when this value carries the minimum provenance we require."""
        return bool(self.source and self.retrieved_at)
