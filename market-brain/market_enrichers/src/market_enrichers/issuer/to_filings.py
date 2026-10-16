"""List an issuer's filings from EDGAR — the citation spine."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from market_types.filing import Filing
from market_types.issuer import Issuer

from .._base import flowsint_enricher
from ..market_enricher import MarketEnricher
from ..params import (
    CACHE_MODE,
    FORM_TYPES,
    LIMIT,
    SEC_USER_AGENT,
    SINCE,
    csv_param,
    schema,
)


def _parse_date(raw: Any) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError as exc:
        raise ValueError(f"not an ISO date: {raw!r}") from exc


@flowsint_enricher
class IssuerToFilingsEnricher(MarketEnricher):
    """[SEC EDGAR] List an issuer's filings from its submissions history.

    Every other EDGAR hop cites a filing, so this one comes first. Each `Filing` node
    carries its index URL, which is the thing a claim should point at — not a vendor
    record of the filing, and not a summary of it.

    Amendments are kept as their own nodes with `is_amendment` set, because the
    difference between a 10-K and its 10-K/A is often the interesting part.
    """

    InputType = Issuer
    OutputType = Filing

    source = "sec_edgar"

    @classmethod
    def name(cls) -> str:
        return "issuer_to_filings"

    @classmethod
    def key(cls) -> str:
        return "issuer_id"

    @classmethod
    def get_params_schema(cls) -> list[dict[str, Any]]:
        return schema(SEC_USER_AGENT, FORM_TYPES, SINCE, LIMIT, CACHE_MODE)

    async def scan(self, data: list[Any]) -> list[Filing]:
        client = self.edgar()
        forms = csv_param(self.params.get("form_types"))
        since = _parse_date(self.params.get("since"))
        limit = int(self.params.get("limit") or 50)
        results: list[Filing] = []

        for issuer in data:
            if not issuer.cik:
                # Without a CIK there is nothing to ask EDGAR. Count it rather than
                # dropping it silently: the fix is to run security_to_issuer first.
                self.failures += 1
                continue
            with self.guard(issuer.issuer_id):
                payload, record = client.submissions(
                    issuer.cik, cache_mode=self.cache_mode
                )
                for row in client.iter_filings(
                    payload, forms=forms or None, since=since, limit=limit
                ):
                    filing = Filing(
                        accession=row["accession"],
                        cik=row["cik"] or issuer.cik,
                        form_type=row["form"],
                        filed_at=row["filing_date"],
                        period_of_report=row["report_date"],
                        primary_doc_url=row["primary_doc_url"],
                        filing_index_url=row["index_url"],
                        items=row["items"] or None,
                        **self.provenance_from(
                            record,
                            method="reported",
                            locator=f"submissions: {row['form']} {row['accession']}",
                            as_of=row["filing_date"],
                        ),
                    )
                    results.append(self.stage(filing))
                    self.link(issuer, filing, "FILED")
        return results
