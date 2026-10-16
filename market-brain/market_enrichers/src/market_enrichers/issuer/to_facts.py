"""Pull reported XBRL facts for an issuer, one value at a time."""

from __future__ import annotations

from typing import Any

from market_types.fact import Fact
from market_types.filing import Filing
from market_types.issuer import Issuer

from .._base import flowsint_enricher
from ..market_enricher import MarketEnricher
from ..params import CACHE_MODE, LIMIT, SEC_USER_AGENT, TAGS, csv_param, schema


@flowsint_enricher
class IssuerToFactsEnricher(MarketEnricher):
    """[SEC EDGAR] Write reported XBRL facts as atomic, citable values.

    Statements are not stored as blobs: one node per (tag, unit, period, accession) keeps
    each **vintage** of a number addressable, which is what makes a restatement visible
    instead of silently overwriting history (../docs/08-provenance-and-trust.md).

    Each fact is linked from the `Filing` that reported it, so `Fact -> Filing -> URL` is
    a complete citation chain. Ratios are deliberately not computed here — derivation
    belongs in queries, where it can be seen and revised.
    """

    InputType = Issuer
    OutputType = Fact

    source = "sec_edgar"

    @classmethod
    def name(cls) -> str:
        return "issuer_to_facts"

    @classmethod
    def key(cls) -> str:
        return "issuer_id"

    @classmethod
    def get_params_schema(cls) -> list[dict[str, Any]]:
        return schema(SEC_USER_AGENT, TAGS, LIMIT, CACHE_MODE)

    async def scan(self, data: list[Any]) -> list[Fact]:
        client = self.edgar()
        tags = csv_param(self.params.get("tags"))
        limit_per_tag = int(self.params.get("limit") or 50)
        results: list[Fact] = []

        for issuer in data:
            if not issuer.cik:
                self.failures += 1
                continue
            with self.guard(issuer.issuer_id):
                payload, record = client.company_facts(
                    issuer.cik, cache_mode=self.cache_mode
                )
                for row in client.iter_facts(
                    payload, tags=tags or None, limit_per_tag=limit_per_tag
                ):
                    fact = Fact.from_xbrl(
                        row["cik"] or issuer.cik,
                        row["tag"],
                        row["unit"],
                        row["value"],
                        period=row["period"],
                        taxonomy=row["taxonomy"],
                        accession=row["accession"],
                        period_start=row["period_start"],
                        period_end=row["period_end"] if row["period_start"] else None,
                        instant=row["instant"] if not row["period_start"] else None,
                        fiscal_year=row["fiscal_year"],
                        fiscal_period=row["fiscal_period"],
                        form=row["form"],
                        frame=row["frame"],
                        **self.provenance_from(
                            record,
                            method="reported",
                            locator=f"{row['taxonomy']}:{row['tag']} {row['period']}",
                            as_of=row["period_end"] or row["instant"],
                        ),
                    )
                    results.append(self.stage(fact))
                    if row["accession"]:
                        filing = Filing(
                            accession=row["accession"],
                            cik=row["cik"] or issuer.cik,
                            form_type=row["form"],
                            **self.provenance_from(
                                record,
                                method="reported",
                                locator=f"companyfacts accn {row['accession']}",
                            ),
                        )
                        self.link(issuer, filing, "FILED")
                        self.link(filing, fact, "REPORTS_FACT")
        return results
