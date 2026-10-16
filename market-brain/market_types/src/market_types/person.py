"""A natural person in their public corporate role — officer, director, insider."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Self

from pydantic import Field, model_validator

from ._base import FlowsintType, flowsint_type
from .identifiers import normalize_cik
from .keys import NS_CIK, NS_SLUG, build_key, is_key, parse_key, slugify
from .provenance import Provenance


@flowsint_type
class Person(Provenance, FlowsintType):
    """An officer, director or reporting owner, identified by SEC CIK where possible.

    **Scope boundary** (docs/10-compliance-and-ethics.md): this type holds *public
    professional* attributes only — name, roles, tenure, and the filings a person
    appears in. It deliberately has no fields for personal contact details, addresses,
    personal accounts or location, and this project does not run Flowsint's
    people-search enrichers against them. Upstream ``Individual`` is the OSINT person
    type; keep the two linked with ``SAME_AS`` only where research genuinely needs it.

    Insiders have their own CIK, which is why Form 4 data can be keyed properly:

    >>> p = Person.from_cik(1214156, name="COOK TIMOTHY D", titles=["CEO"])
    >>> p.person_id, p.cik
    ('cik:0001214156', '0001214156')

    Without a CIK the key is issuer-scoped, so two same-named directors stay distinct:

    >>> Person.from_name_at_issuer("John Smith", "cik:0000320193").person_id
    'slug:john-smith@cik:0000320193'
    """

    person_id: str = Field(
        ...,
        description="Merge key: cik:<10 digits> or slug:<name>@<issuer_id>",
        title="Person ID",
        json_schema_extra={"primary": True},
    )
    name: Optional[str] = Field(
        None, description="Name as reported in filings", title="Name"
    )
    cik: Optional[str] = Field(
        None, description="SEC CIK of the reporting owner", title="CIK"
    )
    titles: Optional[list[str]] = Field(
        None,
        description="Public roles as filed, e.g. ['CEO', 'Director']",
        title="Titles",
    )
    is_officer: Optional[bool] = Field(
        None, description="Reported as an officer", title="Is Officer"
    )
    is_director: Optional[bool] = Field(
        None, description="Reported as a director", title="Is Director"
    )
    is_ten_percent_owner: Optional[bool] = Field(
        None, description="Reported as a >10% owner", title="Is 10% Owner"
    )
    actor_type: Optional[str] = Field(
        None,
        description="insider | legislator | other — keeps disclosure regimes apart",
        title="Actor Type",
    )
    first_seen: Optional[date] = Field(
        None, description="Earliest filing we have for this person", title="First Seen"
    )
    last_seen: Optional[date] = Field(
        None, description="Latest filing we have for this person", title="Last Seen"
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        if isinstance(data, str):
            data = {"person_id": data.strip()}
        if not isinstance(data, dict):
            return data
        derived = dict(data)
        raw = derived.get("person_id")
        if raw and not is_key(raw):
            # Upstream preprocess() coercion of a bare string; see Issuer for the detail.
            text = str(raw).strip()
            digits = text.upper().removeprefix("CIK")
            if digits.isdigit():
                derived["person_id"] = build_key(NS_CIK, normalize_cik(digits))
            else:
                derived.setdefault("name", text)
                derived["person_id"] = build_key(NS_SLUG, slugify(text))
            return derived
        if raw:
            return derived
        if derived.get("cik"):
            derived["person_id"] = build_key(NS_CIK, normalize_cik(derived["cik"]))
        elif derived.get("name"):
            # No issuer scope available here, so the slug is weaker than the one
            # from_name_at_issuer() builds. The resolver is expected to improve it.
            derived["person_id"] = build_key(NS_SLUG, slugify(derived["name"]))
        return derived

    @model_validator(mode="after")
    def _normalize_identity(self) -> Self:
        namespace, value = parse_key(self.person_id)
        if namespace == NS_CIK:
            cik = normalize_cik(value)
            self.person_id = build_key(NS_CIK, cik)
            self.cik = cik
        if self.cik:
            self.cik = normalize_cik(self.cik)
        if self.first_seen and self.last_seen and self.last_seen < self.first_seen:
            raise ValueError("last_seen precedes first_seen")
        return self

    @model_validator(mode="after")
    def compute_label(self) -> Self:
        self.nodeLabel = str(self.name) if self.name else str(self.person_id)
        return self

    @classmethod
    def from_cik(cls, cik: str | int, **fields: Any) -> Person:
        return cls(person_id=build_key(NS_CIK, normalize_cik(cik)), **fields)

    @classmethod
    def from_name_at_issuer(cls, name: str, issuer_id: str, **fields: Any) -> Person:
        """Issuer-scoped fallback key, so same-named people do not collide."""
        return cls(
            person_id=build_key(NS_SLUG, f"{slugify(name)}@{issuer_id}"),
            name=name,
            **fields,
        )

    @classmethod
    def from_string(cls, line: str) -> Person:
        return cls.model_validate(line.strip())

    @classmethod
    def detect(cls, line: str) -> bool:
        """A person's name is not reliably detectable from one line of text."""
        return is_key(line.strip()) and parse_key(line.strip())[0] == NS_CIK
