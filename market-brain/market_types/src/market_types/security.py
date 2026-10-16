"""A tradable instrument of an issuer: one node per share class."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal, Optional, Self

from pydantic import Field, model_validator

from ._base import FlowsintType, flowsint_type
from .identifiers import (
    IdentifierError,
    is_valid_cusip,
    is_valid_figi,
    is_valid_isin,
    is_valid_mic,
)
from .keys import (
    NS_EODHD,
    NS_FIGI,
    NS_MIC,
    NS_SLUG,
    build_key,
    is_key,
    parse_key,
    slugify,
)
from .provenance import Provenance

SecurityType = Literal[
    "common",
    "preferred",
    "adr",
    "gdr",
    "etf",
    "fund",
    "index",
    "warrant",
    "unit",
    "other",
]
ListingStatus = Literal["listed", "delisted", "suspended", "unknown"]

_EODHD_CODE_RE = re.compile(
    r"^(?P<symbol>[A-Z0-9][A-Z0-9.\-]{0,14})\.(?P<exchange>[A-Z]{2,6})$"
)
_ISIN_SHAPE_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{9}\d$")


@flowsint_type
class Security(Provenance, FlowsintType):
    """An instrument, keyed on FIGI where known and venue+symbol otherwise.

    Tickers are alias properties, never the merge key: they vary by source, get reused
    after a delisting, and change on renames
    (docs/adr/0006-registry-ids-as-merge-keys.md).

    >>> s = Security.from_eodhd_code("AAPL.US", name="Apple Inc.")
    >>> s.security_id, s.ticker, s.eodhd_code
    ('eodhd:AAPL.US', 'AAPL', 'AAPL.US')
    >>> Security.from_figi("BBG000B9XRY4", ticker="AAPL").security_id
    'figi:BBG000B9XRY4'
    >>> Security.from_mic_symbol("xnas", "aapl").security_id
    'mic:XNAS:AAPL'
    """

    security_id: str = Field(
        ...,
        description="Merge key: figi:<12>, mic:<MIC>:<symbol>, or eodhd:<code>",
        title="Security ID",
        json_schema_extra={"primary": True},
    )
    figi: Optional[str] = Field(None, description="OpenFIGI identifier", title="FIGI")
    cusip: Optional[str] = Field(
        None, description="CUSIP; checksum-validated on assignment", title="CUSIP"
    )
    isin: Optional[str] = Field(
        None, description="ISIN; checksum-validated on assignment", title="ISIN"
    )
    sedol: Optional[str] = Field(None, description="SEDOL", title="SEDOL")
    ticker: Optional[str] = Field(
        None, description="Local trading symbol (alias, not a key)", title="Ticker"
    )
    mic: Optional[str] = Field(None, description="ISO 10383 venue code", title="MIC")
    eodhd_code: Optional[str] = Field(
        None, description="EODHD symbol, e.g. AAPL.US", title="EODHD Code"
    )
    tradingview_symbol: Optional[str] = Field(
        None,
        description="TradingView symbol, e.g. NASDAQ:AAPL",
        title="TradingView Symbol",
    )
    name: Optional[str] = Field(None, description="Instrument name", title="Name")
    security_type: Optional[SecurityType] = Field(
        None, description="Instrument class", title="Security Type"
    )
    share_class: Optional[str] = Field(
        None, description="Share class designation, e.g. A, B", title="Share Class"
    )
    currency: Optional[str] = Field(
        None, description="Trading currency, ISO 4217", title="Currency"
    )
    listed_from: Optional[date] = Field(
        None, description="First listing date on this venue", title="Listed From"
    )
    listed_to: Optional[date] = Field(
        None,
        description="Delisting date; with listed_from this resolves ticker reuse",
        title="Listed To",
    )
    status: Optional[ListingStatus] = Field(
        None, description="Listing status", title="Status"
    )
    shares_outstanding: Optional[float] = Field(
        None, ge=0, description="Shares outstanding", title="Shares Outstanding"
    )
    shares_as_of: Optional[date] = Field(
        None, description="As-of date for shares outstanding", title="Shares As Of"
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        """Accept a bare key or an EODHD-style code, and derive the key from aliases."""
        if isinstance(data, str):
            data = {"security_id": data.strip()}
        if not isinstance(data, dict):
            return data
        derived = dict(data)
        raw = derived.get("security_id")
        if raw and not is_key(raw):
            # Flowsint's Enricher.preprocess() turns a bare string into
            # {primary_field: value}, so a UI seed of "AAPL.US", "US0378331005" or
            # "AAPL" arrives as a security_id that is not yet a key. Resolve what can
            # be resolved and mark the rest provisional, rather than failing validation
            # and being dropped silently (docs/02-flowsint-primer.md).
            text = str(raw).strip().upper()
            if _EODHD_CODE_RE.match(text):
                derived["security_id"] = build_key(NS_EODHD, text)
                derived.setdefault("eodhd_code", text)
            elif _ISIN_SHAPE_RE.match(text) and is_valid_isin(text):
                derived["security_id"] = build_key(NS_SLUG, text.lower())
                derived.setdefault("isin", text)
            else:
                derived["security_id"] = build_key(NS_SLUG, slugify(text))
                derived.setdefault("ticker", text)
            return derived
        if raw:
            return derived
        if derived.get("figi"):
            derived["security_id"] = build_key(NS_FIGI, str(derived["figi"]).upper())
        elif derived.get("mic") and derived.get("ticker"):
            derived["security_id"] = build_key(
                NS_MIC, str(derived["mic"]).upper(), str(derived["ticker"]).upper()
            )
        elif derived.get("eodhd_code"):
            derived["security_id"] = build_key(
                NS_EODHD, str(derived["eodhd_code"]).upper()
            )
        return derived

    @model_validator(mode="after")
    def _normalize_identity(self) -> Self:
        namespace, value = parse_key(self.security_id)
        if namespace == NS_FIGI:
            figi = value.upper()
            if not is_valid_figi(figi):
                raise IdentifierError(f"not a structurally valid FIGI: {figi!r}")
            self.security_id = build_key(NS_FIGI, figi)
            self.figi = figi
        elif namespace == NS_MIC:
            mic, _, symbol = value.partition(":")
            if not symbol:
                raise IdentifierError(
                    f"mic: key needs venue and symbol, got {self.security_id!r}"
                )
            if not is_valid_mic(mic):
                raise IdentifierError(f"not a valid MIC: {mic!r}")
            self.security_id = build_key(NS_MIC, mic.upper(), symbol.upper())
            self.mic = mic.upper()
            self.ticker = self.ticker or symbol.upper()
        elif namespace == NS_EODHD:
            code = value.upper()
            self.security_id = build_key(NS_EODHD, code)
            self.eodhd_code = code
            match = _EODHD_CODE_RE.match(code)
            if match and not self.ticker:
                self.ticker = match.group("symbol")

        if self.cusip:
            self.cusip = self.cusip.strip().upper()
            if not is_valid_cusip(self.cusip):
                raise IdentifierError(f"CUSIP fails its check digit: {self.cusip!r}")
        if self.isin:
            self.isin = self.isin.strip().upper()
            if not is_valid_isin(self.isin):
                raise IdentifierError(f"ISIN fails its check digit: {self.isin!r}")
        if self.ticker:
            self.ticker = self.ticker.strip().upper()
        if self.listed_from and self.listed_to and self.listed_to < self.listed_from:
            raise ValueError("listed_to precedes listed_from")
        return self

    @model_validator(mode="after")
    def compute_label(self) -> Self:
        if self.ticker:
            self.nodeLabel = str(self.ticker)
        elif self.name:
            self.nodeLabel = str(self.name)
        else:
            self.nodeLabel = str(self.security_id)
        return self

    def was_listed_on(self, when: date) -> bool:
        """True when this security was listed on ``when``.

        Unknown bounds are treated as open, so an undated security is assumed listed —
        the caller sees ``listed_from``/``listed_to`` and can decide otherwise.
        """
        if self.listed_from and when < self.listed_from:
            return False
        return not (self.listed_to and when > self.listed_to)

    @classmethod
    def from_figi(cls, figi: str, **fields: Any) -> Security:
        return cls(security_id=build_key(NS_FIGI, figi.strip().upper()), **fields)

    @classmethod
    def from_mic_symbol(cls, mic: str, symbol: str, **fields: Any) -> Security:
        return cls(
            security_id=build_key(NS_MIC, mic.strip().upper(), symbol.strip().upper()),
            **fields,
        )

    @classmethod
    def from_eodhd_code(cls, code: str, **fields: Any) -> Security:
        """Build from an EODHD symbol such as ``AAPL.US``, splitting out the ticker."""
        return cls(security_id=build_key(NS_EODHD, code.strip().upper()), **fields)

    @classmethod
    def from_string(cls, line: str) -> Security:
        return cls.model_validate(line.strip())

    @classmethod
    def detect(cls, line: str) -> bool:
        """Detect a namespaced key, an ISIN, or an EODHD-style ``SYMBOL.EX`` code."""
        text = line.strip()
        if is_key(text):
            # Namespaces are lowercase, so this check runs before any upper-casing.
            return parse_key(text)[0] in {NS_FIGI, NS_MIC, NS_EODHD}
        upper = text.upper()
        if _ISIN_SHAPE_RE.match(upper):
            return is_valid_isin(upper)
        return bool(_EODHD_CODE_RE.match(upper))
