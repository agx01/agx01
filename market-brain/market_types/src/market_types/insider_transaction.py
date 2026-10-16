"""One transaction line from a Form 4 (or an equivalent disclosure regime)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional, Self

from pydantic import Field, model_validator

from ._base import FlowsintType, flowsint_type
from .identifiers import normalize_accession
from .keys import NS_FORM4, build_key, is_key
from .provenance import Provenance

AcquiredDisposed = Literal["A", "D"]
OwnershipType = Literal["direct", "indirect"]
ActorType = Literal["insider", "legislator", "other"]

#: Form 4 transaction codes and what they mean. Only P and S are open-market trades;
#: reading a grant (A) or a tax withholding (F) as a view is a category error.
TRANSACTION_CODES: dict[str, str] = {
    "P": "open-market or private purchase",
    "S": "open-market or private sale",
    "A": "grant, award or other acquisition from the issuer",
    "D": "disposition to the issuer",
    "F": "payment of exercise price or tax by delivering shares",
    "M": "exercise or conversion of a derivative security",
    "C": "conversion of a derivative security",
    "X": "exercise of an in-the-money or at-the-money derivative",
    "G": "bona fide gift",
    "J": "other acquisition or disposition (see footnotes)",
    "K": "equity swap or similar instrument",
    "L": "small acquisition",
    "U": "disposition under a tender of shares",
    "W": "acquisition or disposition by will or laws of descent",
    "Z": "deposit into or withdrawal from a voting trust",
}

#: The subset that reflects a discretionary market decision.
OPEN_MARKET_CODES: frozenset[str] = frozenset({"P", "S"})


@flowsint_type
class InsiderTransaction(Provenance, FlowsintType):
    """A single reported insider transaction, keyed on its filing and line number.

    A Form 4 carries many transaction lines, so the accession alone is not unique:

    >>> t = InsiderTransaction.from_form4(
    ...     "0000320193-24-000123", 2,
    ...     transaction_date=date(2024, 10, 28), transaction_code="S",
    ...     acquired_disposed="D", shares=100_000, price_per_share=225.5,
    ... )
    >>> t.transaction_id
    'form4:0000320193-24-000123:2'
    >>> t.value                      # derived when not reported
    22550000.0
    >>> t.is_open_market()
    True

    ``is_10b5_1`` matters: a sale under a pre-arranged plan reflects a schedule set
    months earlier, not a fresh view, and the flow queries separate the two
    (docs/07-query-library.md).
    """

    transaction_id: str = Field(
        ...,
        description="Merge key: form4:<accession>:<line number>",
        title="Transaction ID",
        json_schema_extra={"primary": True},
    )
    accession: Optional[str] = Field(
        None, description="Accession number of the disclosing filing", title="Accession"
    )
    line_number: Optional[int] = Field(
        None, ge=0, description="Transaction line within the filing", title="Line Number"
    )
    transaction_date: Optional[date] = Field(
        None, description="Date of the transaction", title="Transaction Date"
    )
    transaction_code: Optional[str] = Field(
        None, description="Form 4 transaction code, e.g. P, S, A, M, F", title="Code"
    )
    acquired_disposed: Optional[AcquiredDisposed] = Field(
        None, description="A = acquired, D = disposed", title="Acquired/Disposed"
    )
    security_title: Optional[str] = Field(
        None, description="Security title as reported", title="Security Title"
    )
    shares: Optional[float] = Field(
        None, ge=0, description="Number of shares", title="Shares"
    )
    price_per_share: Optional[float] = Field(
        None, ge=0, description="Reported price per share", title="Price Per Share"
    )
    value: Optional[float] = Field(
        None, ge=0, description="Transaction value; derived when absent", title="Value"
    )
    currency: Optional[str] = Field(
        None, description="Currency of price and value, ISO 4217", title="Currency"
    )
    shares_owned_after: Optional[float] = Field(
        None,
        ge=0,
        description="Shares beneficially owned afterwards",
        title="Owned After",
    )
    ownership_type: Optional[OwnershipType] = Field(
        None, description="Direct or indirect ownership", title="Ownership Type"
    )
    is_10b5_1: Optional[bool] = Field(
        None,
        description="Reported as made under a Rule 10b5-1 trading plan",
        title="10b5-1 Plan",
    )
    actor_type: Optional[ActorType] = Field(
        None,
        description="Disclosure regime: corporate insider, legislator, or other",
        title="Actor Type",
    )
    footnotes: Optional[list[str]] = Field(
        None, description="Footnote text as filed", title="Footnotes"
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        if isinstance(data, str) and is_key(data.strip()):
            return {"transaction_id": data.strip()}
        if not isinstance(data, dict) or data.get("transaction_id"):
            return data
        derived = dict(data)
        accession = derived.get("accession")
        line = derived.get("line_number")
        if accession and line is not None:
            derived["transaction_id"] = build_key(
                NS_FORM4, normalize_accession(accession), str(line)
            )
        return derived

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        parts = self.transaction_id.split(":")
        if len(parts) != 3 or parts[0] != NS_FORM4:
            raise ValueError(
                "transaction_id must be form4:<accession>:<line>, got "
                f"{self.transaction_id!r}"
            )
        accession = normalize_accession(parts[1])
        self.transaction_id = build_key(NS_FORM4, accession, parts[2])
        if self.accession:
            self.accession = normalize_accession(self.accession)
            if self.accession != accession:
                raise ValueError(
                    f"accession {self.accession!r} disagrees with the accession in "
                    f"transaction_id {self.transaction_id!r}"
                )
        else:
            self.accession = accession
        if self.line_number is None and parts[2].isdigit():
            self.line_number = int(parts[2])
        if self.transaction_code:
            self.transaction_code = self.transaction_code.strip().upper()
            if self.transaction_code not in TRANSACTION_CODES:
                raise ValueError(f"unknown Form 4 code {self.transaction_code!r}")
        if (
            self.value is None
            and self.shares is not None
            and self.price_per_share is not None
        ):
            self.value = round(self.shares * self.price_per_share, 2)
        if self.actor_type is None:
            self.actor_type = "insider"
        return self

    @model_validator(mode="after")
    def compute_label(self) -> Self:
        if self.transaction_code and self.transaction_date and self.shares is not None:
            direction = "sell" if self.acquired_disposed == "D" else "buy"
            self.nodeLabel = (
                f"{self.transaction_code} {direction} {self.shares:,.0f} "
                f"{self.transaction_date.isoformat()}"
            )
        else:
            self.nodeLabel = str(self.transaction_id)
        return self

    def is_open_market(self) -> bool:
        """True for a discretionary purchase or sale (code P or S)."""
        return bool(self.transaction_code and self.transaction_code in OPEN_MARKET_CODES)

    def is_discretionary_signal(self) -> bool:
        """Open-market and not under a pre-arranged 10b5-1 plan."""
        return self.is_open_market() and not self.is_10b5_1

    def code_meaning(self) -> Optional[str]:
        return (
            TRANSACTION_CODES.get(self.transaction_code)
            if self.transaction_code
            else None
        )

    @classmethod
    def from_form4(
        cls, accession: str, line_number: int, **fields: Any
    ) -> InsiderTransaction:
        """Build a transaction from its filing and line number."""
        return cls(
            transaction_id=build_key(
                NS_FORM4, normalize_accession(accession), str(line_number)
            ),
            accession=normalize_accession(accession),
            line_number=line_number,
            **fields,
        )
