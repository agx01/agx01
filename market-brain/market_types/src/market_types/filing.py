"""A document filed with the SEC, keyed on its accession number."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Self

from pydantic import Field, model_validator

from ._base import FlowsintType, flowsint_type
from .identifiers import accession_compact, normalize_accession, normalize_cik
from .provenance import Provenance

EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

#: Forms this project parses, and what each yields (docs/04-data-sources.md).
FORM_MEANINGS: dict[str, str] = {
    "10-K": "annual report: XBRL facts, risk factors, segments, subsidiaries, auditor",
    "10-Q": "quarterly report: XBRL facts, updated risk factors",
    "8-K": "material event, item-coded",
    "4": "insider transaction report",
    "13F-HR": "quarterly institutional holdings",
    "SC 13D": "beneficial ownership above 5% with intent",
    "SC 13G": "passive beneficial ownership above 5%",
    "DEF 14A": "proxy statement: board, compensation, related-party transactions",
    "20-F": "annual report of a foreign private issuer",
}


@flowsint_type
class Filing(Provenance, FlowsintType):
    """One SEC filing. The accession number is globally unique, so it is the key.

    >>> f = Filing.from_edgar(320193, "0000320193-24-000123", "10-K", date(2024, 11, 1))
    >>> f.accession
    '0000320193-24-000123'
    >>> f.filing_index_url
    'https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/0000320193-24-000123-index.htm'
    >>> Filing(accession="000032019324000123").accession     # either spelling accepted
    '0000320193-24-000123'
    >>> Filing(accession="0000320193-24-000123", form_type="10-K/A").is_amendment
    True
    """

    accession: str = Field(
        ...,
        description="SEC accession number, dashed form",
        title="Accession Number",
        json_schema_extra={"primary": True},
    )
    cik: Optional[str] = Field(
        None, description="CIK of the subject filer", title="Filer CIK"
    )
    form_type: Optional[str] = Field(
        None, description="Form type as filed, e.g. 10-K, 8-K, 4", title="Form Type"
    )
    filed_at: Optional[date] = Field(None, description="Filing date", title="Filed At")
    period_of_report: Optional[date] = Field(
        None, description="Period the filing reports on", title="Period Of Report"
    )
    primary_doc_url: Optional[str] = Field(
        None, description="URL of the primary document", title="Primary Document URL"
    )
    filing_index_url: Optional[str] = Field(
        None,
        description="URL of the filing index — the citation target",
        title="Index URL",
    )
    items: Optional[list[str]] = Field(
        None, description="Item codes, for 8-K and similar", title="Items"
    )
    is_amendment: Optional[bool] = Field(
        None, description="True when the form type carries /A", title="Is Amendment"
    )
    amends: Optional[str] = Field(
        None, description="Accession number this filing amends", title="Amends"
    )
    extracted_sections: Optional[list[str]] = Field(
        None,
        description="Sections we parsed, e.g. ['Item 1A', 'Exhibit 21']",
        title="Extracted Sections",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"accession": data.strip()}
        return data

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        self.accession = normalize_accession(self.accession)
        if self.amends:
            self.amends = normalize_accession(self.amends)
        if self.cik:
            self.cik = normalize_cik(self.cik)
        if self.form_type:
            self.form_type = self.form_type.strip().upper()
            if self.is_amendment is None:
                self.is_amendment = self.form_type.endswith("/A")
        if self.cik and not self.filing_index_url:
            self.filing_index_url = self.index_url()
        return self

    @model_validator(mode="after")
    def compute_label(self) -> Self:
        if self.form_type and self.filed_at:
            self.nodeLabel = f"{self.form_type} {self.filed_at.isoformat()}"
        elif self.form_type:
            self.nodeLabel = f"{self.form_type} {self.accession}"
        else:
            self.nodeLabel = str(self.accession)
        return self

    def archive_dir(self) -> str:
        """EDGAR archive directory for this filing. Requires ``cik``."""
        if not self.cik:
            raise ValueError("archive_dir() needs the filer CIK")
        return f"{EDGAR_ARCHIVES}/{int(self.cik)}/{accession_compact(self.accession)}"

    def index_url(self) -> str:
        """Canonical filing-index URL — what a citation should point at."""
        return f"{self.archive_dir()}/{self.accession}-index.htm"

    def base_form(self) -> Optional[str]:
        """Form type without the amendment suffix, e.g. ``10-K`` for ``10-K/A``."""
        return self.form_type.removesuffix("/A") if self.form_type else None

    def form_meaning(self) -> Optional[str]:
        """What this form yields for the graph, when it is one we parse."""
        base = self.base_form()
        return FORM_MEANINGS.get(base) if base else None

    @classmethod
    def from_edgar(
        cls,
        cik: str | int,
        accession: str,
        form_type: str,
        filed_at: date,
        **fields: Any,
    ) -> Filing:
        """Build a filing and derive its canonical EDGAR URLs."""
        return cls(
            accession=normalize_accession(accession),
            cik=normalize_cik(cik),
            form_type=form_type,
            filed_at=filed_at,
            **fields,
        )

    @classmethod
    def from_string(cls, line: str) -> Filing:
        return cls.model_validate(line.strip())

    @classmethod
    def detect(cls, line: str) -> bool:
        """Accession numbers have a distinctive 10-2-6 digit shape."""
        try:
            normalize_accession(line.strip())
        except ValueError:
            return False
        return True
