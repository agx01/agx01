"""The legal entity that files with a securities regulator and issues securities."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Self

from pydantic import Field, model_validator

from ._base import FlowsintType, flowsint_type
from .identifiers import IdentifierError, is_valid_lei, normalize_cik
from .keys import NS_CIK, NS_LEI, NS_SLUG, build_key, is_key, parse_key, slugify
from .provenance import Provenance


@flowsint_type
class Issuer(Provenance, FlowsintType):
    """A filer and issuer of securities, keyed on a registry identifier.

    Deliberately distinct from upstream ``Organization``, which is keyed on ``name`` and
    specialised to the French SIRENE registry — see
    docs/adr/0004-separate-issuer-type.md. Where both exist for one company, link them
    with ``SAME_AS`` rather than merging.

    >>> apple = Issuer.from_cik(320193, name="Apple Inc.")
    >>> apple.issuer_id, apple.cik, apple.nodeLabel
    ('cik:0000320193', '0000320193', 'Apple Inc.')
    >>> Issuer(issuer_id="cik:320193").issuer_id      # padding is normalised
    'cik:0000320193'
    """

    issuer_id: str = Field(
        ...,
        description="Merge key: cik:<10 digits>, lei:<20 chars>, or slug:<name>",
        title="Issuer ID",
        json_schema_extra={"primary": True},
    )
    cik: Optional[str] = Field(
        None, description="SEC Central Index Key, 10-digit zero-padded", title="CIK"
    )
    lei: Optional[str] = Field(
        None, description="Legal Entity Identifier (ISO 17442)", title="LEI"
    )
    name: Optional[str] = Field(None, description="Current legal name", title="Name")
    former_names: Optional[list[str]] = Field(
        None,
        description="Prior names, from EDGAR submissions or symbol-change history",
        title="Former Names",
    )
    sic: Optional[str] = Field(None, description="SEC SIC code as filed", title="SIC")
    sic_description: Optional[str] = Field(
        None, description="SIC description as filed", title="SIC Description"
    )
    country_of_incorporation: Optional[str] = Field(
        None, description="ISO 3166-1 alpha-2 country code", title="Country"
    )
    state_of_incorporation: Optional[str] = Field(
        None, description="State or province of incorporation", title="State"
    )
    fiscal_year_end: Optional[str] = Field(
        None, description="Fiscal year end as MM-DD", title="Fiscal Year End"
    )
    hq_address: Optional[str] = Field(
        None, description="Business address, single line", title="HQ Address"
    )
    website: Optional[str] = Field(
        None,
        description="Corporate website; the bridge into Flowsint's web enrichers",
        title="Website",
    )
    ir_url: Optional[str] = Field(
        None, description="Investor relations page", title="IR URL"
    )
    employees: Optional[int] = Field(
        None, ge=0, description="Reported employee count", title="Employees"
    )
    employees_as_of: Optional[date] = Field(
        None, description="As-of date for the employee count", title="Employees As Of"
    )
    is_watchlist: Optional[bool] = Field(
        None,
        description="Maintained by scheduled jobs rather than ad hoc exploration",
        title="On Watchlist",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        """Accept a bare key or name, and derive the key from cik/lei/name."""
        if isinstance(data, str):
            # Mirror what Enricher.preprocess() does with a bare string, so both paths
            # resolve identically below.
            data = {"issuer_id": data.strip()}
        if not isinstance(data, dict):
            return data
        derived = dict(data)
        raw = derived.get("issuer_id")
        if raw and not is_key(raw):
            # Flowsint's Enricher.preprocess() turns a bare string into
            # {primary_field: value}, so a UI seed of "Apple Inc." or "320193" arrives
            # here as an issuer_id that is not yet a key. Resolve it rather than
            # failing, or the item is dropped silently (docs/02-flowsint-primer.md).
            text = str(raw).strip()
            digits = text.upper().removeprefix("CIK")
            if digits.isdigit():
                derived["issuer_id"] = build_key(NS_CIK, normalize_cik(digits))
            else:
                derived.setdefault("name", text)
                derived["issuer_id"] = build_key(NS_SLUG, slugify(text))
            return derived
        if raw:
            return derived
        if derived.get("cik"):
            derived["issuer_id"] = build_key(NS_CIK, normalize_cik(derived["cik"]))
        elif derived.get("lei"):
            derived["issuer_id"] = build_key(NS_LEI, str(derived["lei"]).upper())
        elif derived.get("name"):
            derived["issuer_id"] = build_key(NS_SLUG, slugify(derived["name"]))
        return derived

    @model_validator(mode="after")
    def _normalize_identity(self) -> Self:
        namespace, value = parse_key(self.issuer_id)
        if namespace == NS_CIK:
            cik = normalize_cik(value)
            self.issuer_id = build_key(NS_CIK, cik)
            self.cik = cik
        elif namespace == NS_LEI:
            lei = value.upper()
            if not is_valid_lei(lei):
                raise IdentifierError(f"LEI fails its ISO 7064 checksum: {lei!r}")
            self.issuer_id = build_key(NS_LEI, lei)
            self.lei = lei
        if self.cik:
            self.cik = normalize_cik(self.cik)
        if self.lei and not is_valid_lei(self.lei):
            raise IdentifierError(f"LEI fails its ISO 7064 checksum: {self.lei!r}")
        return self

    @model_validator(mode="after")
    def compute_label(self) -> Self:
        self.nodeLabel = str(self.name) if self.name else str(self.issuer_id)
        return self

    @classmethod
    def from_cik(cls, cik: str | int, **fields: Any) -> Issuer:
        """Build an issuer from a CIK in any spelling."""
        return cls(issuer_id=build_key(NS_CIK, normalize_cik(cik)), **fields)

    @classmethod
    def from_lei(cls, lei: str, **fields: Any) -> Issuer:
        return cls(issuer_id=build_key(NS_LEI, lei.strip().upper()), **fields)

    @classmethod
    def from_name(cls, name: str, **fields: Any) -> Issuer:
        """Fallback constructor: an unresolved issuer, keyed on a slug.

        A ``slug:`` key is a flag that identity resolution has not finished — the
        resolver enricher is expected to replace it and link ``SAME_AS``.
        """
        return cls(issuer_id=build_key(NS_SLUG, slugify(name)), name=name, **fields)

    @classmethod
    def from_string(cls, line: str) -> Issuer:
        """Parse an issuer from one line of pasted text (upstream convention).

        Goes through ``model_validate`` because Pydantic models take no positional
        argument — a bare string is validated, not constructed.
        """
        return cls.model_validate(line.strip())

    @classmethod
    def detect(cls, line: str) -> bool:
        """Only a namespaced key is unambiguous; a company name is not detectable."""
        return is_key(line.strip()) and parse_key(line.strip())[0] in {NS_CIK, NS_LEI}
