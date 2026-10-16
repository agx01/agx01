"""Parse an issuer's Form 4 filings into transactions and the people who reported them."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from market_types.insider_transaction import InsiderTransaction
from market_types.issuer import Issuer
from market_types.person import Person
from market_types.security import Security

from .._base import flowsint_enricher
from ..market_enricher import MarketEnricher
from ..params import CACHE_MODE, LIMIT, SEC_USER_AGENT, SINCE, schema
from ..tools.edgar import Form4, Form4Transaction


def _parse_date(raw: Any) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError as exc:
        raise ValueError(f"not an ISO date: {raw!r}") from exc


@flowsint_enricher
class IssuerToInsiderTransactionsEnricher(MarketEnricher):
    """[SEC EDGAR] Read Form 4 filings into transactions, with the 10b5-1 flag kept.

    Insider data is in this graph because the law requires it to be published, and it is
    kept at the level the filing states: name, role, transaction, date, citation. No
    enrichment of the person beyond their public corporate role
    (../docs/10-compliance-and-ethics.md).

    The `is_10b5_1` flag is carried through because a sale under a pre-arranged plan
    reflects a schedule set months earlier, not a fresh view — the flow queries separate
    the two, and treating a planned sale as a signal is both wrong and unfair to the
    person (../docs/07-query-library.md).

    One Form 4 holds many transaction lines, so each line becomes its own node keyed
    `form4:<accession>:<line>`; derivative tables are a later phase.
    """

    InputType = Issuer
    OutputType = InsiderTransaction

    source = "sec_edgar"

    @classmethod
    def name(cls) -> str:
        return "issuer_to_insider_transactions"

    @classmethod
    def key(cls) -> str:
        return "issuer_id"

    @classmethod
    def get_params_schema(cls) -> list[dict[str, Any]]:
        return schema(SEC_USER_AGENT, SINCE, LIMIT, CACHE_MODE)

    async def scan(self, data: list[Any]) -> list[InsiderTransaction]:
        client = self.edgar()
        since = _parse_date(self.params.get("since"))
        limit = int(self.params.get("limit") or 25)
        results: list[InsiderTransaction] = []

        for issuer in data:
            if not issuer.cik:
                self.failures += 1
                continue
            with self.guard(issuer.issuer_id):
                payload, record = client.submissions(
                    issuer.cik, cache_mode=self.cache_mode
                )
                filings = list(
                    client.iter_filings(payload, forms=["4"], since=since, limit=limit)
                )
            for row in filings:
                # Per filing, not per issuer: one unreadable Form 4 must not cost the
                # other twenty-four.
                with self.guard(f"{issuer.issuer_id} {row['accession']}"):
                    results.extend(self._ingest_form4(client, issuer, row))
        return results

    def _ingest_form4(
        self, client: Any, issuer: Any, row: dict[str, Any]
    ) -> list[InsiderTransaction]:
        document = row.get("primary_document")
        if not document:
            raise ValueError(f"Form 4 {row['accession']} has no primary document")
        raw, doc_record = client.filing_document(
            row["cik"] or issuer.cik,
            row["accession"],
            document,
            cache_mode=self.cache_mode,
        )
        form4 = client.parse_form4(raw)

        filing = self._filing_node(issuer, row, doc_record)
        person = self._person_node(form4, issuer, doc_record)
        security = self._security_node(form4, doc_record)

        written: list[InsiderTransaction] = []
        for line in form4.transactions:
            transaction = self._transaction_node(form4, line, row, doc_record)
            written.append(self.stage(transaction))
            self.link(transaction, filing, "DISCLOSED_IN")
            if person is not None:
                self.link(transaction, person, "REPORTED_BY")
            if security is not None:
                self.link(transaction, security, "TRANSACTED_IN")
        self.link(issuer, filing, "FILED")
        return written

    def _filing_node(self, issuer: Any, row: dict[str, Any], record: Any) -> Any:
        from market_types.filing import Filing

        return Filing(
            accession=row["accession"],
            cik=row["cik"] or issuer.cik,
            form_type=row["form"] or "4",
            filed_at=row["filing_date"],
            period_of_report=row["report_date"],
            primary_doc_url=row["primary_doc_url"],
            filing_index_url=row["index_url"],
            **self.provenance_from(
                record, method="reported", locator=f"Form 4 {row['accession']}"
            ),
        )

    def _person_node(self, form4: Form4, issuer: Any, record: Any) -> Optional[Person]:
        """The reporting owner, keyed on their own CIK where the filing gives one."""
        titles = [form4.officer_title] if form4.officer_title else None
        fields: dict[str, Any] = {
            "name": form4.owner_name,
            "titles": titles,
            "is_officer": form4.is_officer,
            "is_director": form4.is_director,
            "is_ten_percent_owner": form4.is_ten_percent_owner,
            "actor_type": "insider",
            **self.provenance_from(record, method="reported", locator="reportingOwner"),
        }
        if form4.owner_cik:
            return Person.from_cik(form4.owner_cik, **fields)
        if form4.owner_name:
            return Person.from_name_at_issuer(
                form4.owner_name, issuer.issuer_id, **fields
            )
        return None

    def _security_node(self, form4: Form4, record: Any) -> Optional[Security]:
        """A provisional security from the filing's trading symbol.

        The Form 4 gives a symbol, not a FIGI or a venue, so this node is keyed `slug:`
        and left for `alias_to_security` to resolve and link `SAME_AS`. Guessing a venue
        here would be a merge-key error that is expensive to undo.
        """
        if not form4.issuer_symbol:
            return None
        return Security.model_validate(
            {
                "security_id": form4.issuer_symbol,
                **self.provenance_from(
                    record, method="reported", locator="issuerTradingSymbol"
                ),
            }
        )

    def _transaction_node(
        self,
        form4: Form4,
        line: Form4Transaction,
        row: dict[str, Any],
        record: Any,
    ) -> InsiderTransaction:
        return InsiderTransaction.from_form4(
            row["accession"],
            line.line_number,
            transaction_date=line.transaction_date,
            transaction_code=line.transaction_code,
            acquired_disposed=line.acquired_disposed,
            security_title=line.security_title,
            shares=line.shares,
            price_per_share=line.price_per_share,
            shares_owned_after=line.shares_owned_after,
            ownership_type=line.ownership_type,
            is_10b5_1=line.is_10b5_1,
            footnotes=list(line.footnotes) or None,
            actor_type="insider",
            **self.provenance_from(
                record,
                method="reported",
                locator=f"nonDerivativeTransaction[{line.line_number}]",
                as_of=line.transaction_date or form4.period_of_report,
            ),
        )
