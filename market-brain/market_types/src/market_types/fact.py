"""One reported financial datapoint, kept atomic and restatement-aware."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Self

from pydantic import Field, model_validator

from ._base import FlowsintType, flowsint_type
from .identifiers import normalize_accession, normalize_cik
from .keys import NS_XBRL, build_key, is_key
from .provenance import Provenance


def make_fact_id(
    cik: str | int,
    tag: str,
    unit: str,
    period: str,
    accession: Optional[str] = None,
) -> str:
    """Build a fact merge key.

    The accession is optional but recommended: figures get restated, and including the
    filing that reported a value keeps each vintage addressable instead of overwriting
    history (docs/08-provenance-and-trust.md).

    >>> make_fact_id(320193, "Revenues", "USD", "FY2025")
    'xbrl:0000320193:Revenues:USD:FY2025'
    """
    parts = [normalize_cik(cik), tag.strip(), unit.strip(), period.strip()]
    if accession:
        parts.append(normalize_accession(accession))
    return build_key(NS_XBRL, *parts)


@flowsint_type
class Fact(Provenance, FlowsintType):
    """A single tagged financial value: tag + unit + period + value.

    Statements are not stored as blobs, because a blob cannot be queried, compared
    across vintages, or cited at the level of the number that mattered.

    >>> f = Fact.from_xbrl(
    ...     320193, "Revenues", "USD", 391035000000.0, period="FY2025",
    ...     period_start=date(2024, 9, 29), period_end=date(2025, 9, 27),
    ...     fiscal_year=2025, fiscal_period="FY", form="10-K",
    ... )
    >>> f.fact_id
    'xbrl:0000320193:Revenues:USD:FY2025'
    >>> f.is_instant()
    False
    """

    fact_id: str = Field(
        ...,
        description="Merge key: xbrl:<cik>:<tag>:<unit>:<period>[:<accession>]",
        title="Fact ID",
        json_schema_extra={"primary": True},
    )
    cik: Optional[str] = Field(None, description="CIK of the filer", title="CIK")
    tag: Optional[str] = Field(
        None, description="XBRL concept, e.g. Revenues", title="Tag"
    )
    taxonomy: Optional[str] = Field(
        None, description="Taxonomy, e.g. us-gaap, ifrs-full, dei", title="Taxonomy"
    )
    unit: Optional[str] = Field(
        None, description="Unit of measure, e.g. USD, shares, pure", title="Unit"
    )
    value: Optional[float] = Field(None, description="Reported value", title="Value")
    period: Optional[str] = Field(
        None, description="Period label, e.g. FY2025, CY2025Q3", title="Period"
    )
    period_start: Optional[date] = Field(
        None, description="Start of a duration fact", title="Period Start"
    )
    period_end: Optional[date] = Field(
        None, description="End of a duration fact", title="Period End"
    )
    instant: Optional[date] = Field(
        None, description="Date of an instant fact (balance-sheet style)", title="Instant"
    )
    fiscal_year: Optional[int] = Field(
        None, description="Fiscal year as reported", title="Fiscal Year"
    )
    fiscal_period: Optional[str] = Field(
        None, description="FY, Q1, Q2, Q3, Q4", title="Fiscal Period"
    )
    form: Optional[str] = Field(
        None, description="Form that reported this value", title="Form"
    )
    frame: Optional[str] = Field(
        None, description="XBRL frame, when sourced from the frames API", title="Frame"
    )
    accession: Optional[str] = Field(
        None, description="Filing that reported this value", title="Accession"
    )
    restates: Optional[str] = Field(
        None, description="fact_id of the vintage this supersedes", title="Restates"
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        if isinstance(data, str) and is_key(data.strip()):
            return {"fact_id": data.strip()}
        if not isinstance(data, dict) or data.get("fact_id"):
            return data
        derived = dict(data)
        required = ("cik", "tag", "unit")
        period = derived.get("period")
        if all(derived.get(key) for key in required) and period:
            derived["fact_id"] = make_fact_id(
                derived["cik"],
                str(derived["tag"]),
                str(derived["unit"]),
                str(period),
                derived.get("accession"),
            )
        return derived

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        if self.cik:
            self.cik = normalize_cik(self.cik)
        if self.accession:
            self.accession = normalize_accession(self.accession)
        if self.instant and (self.period_start or self.period_end):
            raise ValueError("a fact is either an instant or a duration, not both")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        if self.fiscal_period:
            self.fiscal_period = self.fiscal_period.strip().upper()
        return self

    @model_validator(mode="after")
    def compute_label(self) -> Self:
        if self.tag and self.period:
            self.nodeLabel = f"{self.tag} {self.period}"
        elif self.tag:
            self.nodeLabel = str(self.tag)
        else:
            self.nodeLabel = str(self.fact_id)
        return self

    def is_instant(self) -> bool:
        """True for a point-in-time fact rather than a duration."""
        return self.instant is not None

    @classmethod
    def from_xbrl(
        cls,
        cik: str | int,
        tag: str,
        unit: str,
        value: float,
        *,
        period: str,
        taxonomy: str = "us-gaap",
        accession: Optional[str] = None,
        **fields: Any,
    ) -> Fact:
        """Build a fact from an XBRL concept observation."""
        return cls(
            fact_id=make_fact_id(cik, tag, unit, period, accession),
            cik=normalize_cik(cik),
            tag=tag,
            unit=unit,
            value=value,
            period=period,
            taxonomy=taxonomy,
            accession=accession,
            **fields,
        )
