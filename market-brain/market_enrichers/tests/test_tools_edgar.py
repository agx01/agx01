"""EDGAR parsers: submissions, XBRL facts, and Form 4 XML."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from fixtures import COMPANY_FACTS, FORM4_XML, FORM4_XML_EXPLICIT_PLAN, SUBMISSIONS

from conftest import FakeTransport
from market_enrichers.tools.edgar import EdgarClient, EdgarError
from market_enrichers.tools.http import SourceClient

UA = "market-brain-tests tests@example.com"


def edgar(transport: Any) -> EdgarClient:
    return EdgarClient(
        UA, SourceClient(source="sec_edgar", transport=transport, sleep=lambda _: None)
    )


class TestFairAccess:
    @pytest.mark.parametrize("user_agent", [None, "", "market-brain", "no-at-sign"])
    def test_refuses_to_run_without_a_contact_address(self, user_agent: Any) -> None:
        # SEC fair access requires a declared contact; the client enforces it rather
        # than trusting the operator to remember (../docs/04-data-sources.md).
        with pytest.raises(EdgarError, match="User-Agent"):
            edgar_client = EdgarClient(user_agent, SourceClient(source="sec_edgar"))
            assert edgar_client  # pragma: no cover

    def test_declared_user_agent_is_sent(self) -> None:
        transport = FakeTransport(
            routes={"submissions": (200, json.dumps(SUBMISSIONS).encode())}
        )
        edgar(transport).submissions(320193)
        _, headers = transport.requests[0]
        assert headers["User-Agent"] == UA


class TestUrls:
    def test_index_url_uses_the_unpadded_cik_and_compact_accession(self) -> None:
        assert EdgarClient.index_url(320193, "0000320193-24-000123") == (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/0000320193-24-000123-index.htm"
        )

    def test_document_url(self) -> None:
        assert EdgarClient.document_url(320193, "000032019324000123", "aapl.htm") == (
            "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl.htm"
        )


class TestIterFilings:
    def test_yields_every_well_formed_row(self) -> None:
        rows = list(EdgarClient.iter_filings(SUBMISSIONS))
        # Six rows in, one malformed accession out.
        assert len(rows) == 5
        assert all(row["accession"].count("-") == 2 for row in rows)

    def test_tolerates_short_parallel_arrays(self) -> None:
        # reportDate is shorter than accessionNumber; a naive zip would drop rows.
        rows = list(EdgarClient.iter_filings(SUBMISSIONS))
        assert rows[0]["report_date"] == date(2024, 9, 28)
        assert rows[-1]["report_date"] is None

    def test_form_filter_includes_amendments_of_the_wanted_form(self) -> None:
        forms = {
            row["form"] for row in EdgarClient.iter_filings(SUBMISSIONS, forms=["10-K"])
        }
        assert forms == {"10-K", "10-K/A"}

    def test_form_filter_is_case_insensitive(self) -> None:
        rows = list(EdgarClient.iter_filings(SUBMISSIONS, forms=["10-q"]))
        assert [row["form"] for row in rows] == ["10-Q"]

    def test_since_filter_drops_older_filings(self) -> None:
        rows = list(EdgarClient.iter_filings(SUBMISSIONS, since=date(2024, 9, 1)))
        assert {row["form"] for row in rows} == {"10-K", "8-K", "4"}

    def test_limit_stops_early(self) -> None:
        assert len(list(EdgarClient.iter_filings(SUBMISSIONS, limit=2))) == 2

    def test_builds_citation_urls(self) -> None:
        row = next(iter(EdgarClient.iter_filings(SUBMISSIONS, forms=["10-K"])))
        assert row["index_url"].endswith("0000320193-24-000123-index.htm")
        assert row["primary_doc_url"].endswith("aapl-20240928.htm")

    def test_items_are_split(self) -> None:
        row = next(iter(EdgarClient.iter_filings(SUBMISSIONS, forms=["8-K"])))
        assert row["items"] == ["2.02", "9.01"]

    def test_rejects_a_payload_that_is_not_an_object(self) -> None:
        with pytest.raises(EdgarError):
            list(EdgarClient.iter_filings([1, 2, 3]))

    def test_empty_payload_yields_nothing(self) -> None:
        assert list(EdgarClient.iter_filings({})) == []

    def test_former_names(self) -> None:
        assert EdgarClient.former_names(SUBMISSIONS) == ["APPLE COMPUTER INC"]


class TestIterFacts:
    def test_one_row_per_vintage(self) -> None:
        rows = [
            r for r in EdgarClient.iter_facts(COMPANY_FACTS) if r["tag"] == "Revenues"
        ]
        # Two FY2024 vintages plus FY2023; the null-valued observation is skipped.
        assert len(rows) == 3
        accessions = {row["accession"] for row in rows}
        assert "0000320193-24-000123" in accessions
        assert "0000320193-25-000010" in accessions

    def test_duration_and_instant_are_distinguished(self) -> None:
        rows = list(EdgarClient.iter_facts(COMPANY_FACTS))
        revenues = next(r for r in rows if r["tag"] == "Revenues")
        assets = next(r for r in rows if r["tag"] == "Assets")
        assert revenues["period_start"] == date(2023, 10, 1)
        assert revenues["period_end"] == date(2024, 9, 28)
        assert revenues["instant"] is None
        assert assets["period_start"] is None
        assert assets["instant"] == date(2024, 9, 28)

    def test_period_label_comes_from_fiscal_fields(self) -> None:
        row = next(iter(EdgarClient.iter_facts(COMPANY_FACTS, tags=["Assets"])))
        assert row["period"] == "FY2024"
        assert (row["fiscal_year"], row["fiscal_period"]) == (2024, "FY")

    def test_tag_filter(self) -> None:
        tags = {
            row["tag"] for row in EdgarClient.iter_facts(COMPANY_FACTS, tags=["Assets"])
        }
        assert tags == {"Assets"}

    def test_limit_per_tag(self) -> None:
        rows = list(
            EdgarClient.iter_facts(COMPANY_FACTS, tags=["Revenues"], limit_per_tag=1)
        )
        assert len(rows) == 1

    def test_values_are_floats_and_cik_is_padded(self) -> None:
        row = next(iter(EdgarClient.iter_facts(COMPANY_FACTS, tags=["Assets"])))
        assert isinstance(row["value"], float)
        assert row["cik"] == "0000320193"

    def test_rejects_a_payload_that_is_not_an_object(self) -> None:
        with pytest.raises(EdgarError):
            list(EdgarClient.iter_facts("nope"))


class TestParseForm4:
    def test_reads_issuer_and_reporting_owner(self) -> None:
        form4 = EdgarClient.parse_form4(FORM4_XML)
        assert form4.issuer_cik == "0000320193"
        assert form4.issuer_symbol == "AAPL"
        assert form4.owner_cik == "0001214156"
        assert form4.owner_name == "COOK TIMOTHY D"
        assert (form4.is_officer, form4.is_director) == (True, True)
        assert form4.is_ten_percent_owner is False
        assert form4.officer_title == "Chief Executive Officer"
        assert form4.period_of_report == date(2024, 10, 28)

    def test_reads_every_non_derivative_line(self) -> None:
        form4 = EdgarClient.parse_form4(FORM4_XML)
        assert [t.line_number for t in form4.transactions] == [1, 2]
        sale, grant = form4.transactions
        assert (sale.transaction_code, sale.acquired_disposed) == ("S", "D")
        assert sale.shares == 223986.0
        assert sale.price_per_share == 225.5
        assert sale.shares_owned_after == 3280222.0
        assert sale.ownership_type == "direct"
        assert (grant.transaction_code, grant.acquired_disposed) == ("A", "A")
        assert grant.price_per_share is None
        assert grant.ownership_type == "indirect"

    def test_10b5_1_is_inferred_from_footnote_prose(self) -> None:
        sale = EdgarClient.parse_form4(FORM4_XML).transactions[0]
        assert sale.is_10b5_1 is True
        assert any("10b5-1" in note for note in sale.footnotes)

    def test_10b5_1_from_the_explicit_element(self) -> None:
        form4 = EdgarClient.parse_form4(FORM4_XML_EXPLICIT_PLAN)
        assert form4.transactions[0].is_10b5_1 is True
        assert form4.owner_name == "WILLIAMS JEFFREY E"

    def test_unknown_plan_status_stays_none(self) -> None:
        # A false 'not planned' would read a scheduled sale as a discretionary signal,
        # so absence of evidence is reported as None rather than False.
        grant = EdgarClient.parse_form4(FORM4_XML).transactions[1]
        assert grant.is_10b5_1 is None

    def test_malformed_xml_is_an_edgar_error(self) -> None:
        with pytest.raises(EdgarError, match="did not parse"):
            EdgarClient.parse_form4(b"<ownershipDocument><unclosed>")

    def test_document_with_no_transactions_parses_to_an_empty_tuple(self) -> None:
        form4 = EdgarClient.parse_form4(b"<ownershipDocument></ownershipDocument>")
        assert form4.transactions == ()
        assert form4.issuer_cik is None


class TestImmutableDocuments:
    def test_filed_documents_are_cached_forever(self) -> None:
        transport = FakeTransport(routes={"/Archives/": (200, FORM4_XML)})
        client = edgar(transport)
        client.filing_document(320193, "0000320193-24-000123", "form4.xml")
        client.filing_document(320193, "0000320193-24-000123", "form4.xml")
        assert len(transport.requests) == 1
