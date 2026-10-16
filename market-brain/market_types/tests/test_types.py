"""Behaviour of the six phase-1 entity types."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from market_types import (
    Fact,
    Filing,
    IdentifierError,
    InsiderTransaction,
    Issuer,
    Person,
    Security,
    provenance,
)

APPLE_CIK = 320193
APPLE_KEY = "cik:0000320193"


class TestIssuer:
    def test_from_cik_normalises_and_backfills(self) -> None:
        issuer = Issuer.from_cik(APPLE_CIK, name="Apple Inc.")
        assert issuer.issuer_id == APPLE_KEY
        assert issuer.cik == "0000320193"
        assert issuer.nodeLabel == "Apple Inc."

    def test_unpadded_key_is_normalised(self) -> None:
        assert Issuer(issuer_id="cik:320193").issuer_id == APPLE_KEY

    def test_key_derived_from_cik_field(self) -> None:
        derived = Issuer.model_validate({"cik": "320193", "name": "Apple Inc."})
        assert derived.issuer_id == APPLE_KEY

    def test_key_derived_from_lei(self) -> None:
        issuer = Issuer.model_validate({"lei": "HWUPKR0MPOU8FGXBT394"})
        assert issuer.issuer_id == "lei:HWUPKR0MPOU8FGXBT394"

    def test_bad_lei_is_rejected(self) -> None:
        with pytest.raises((IdentifierError, ValidationError)):
            Issuer.model_validate({"lei": "549300C116EOWC307Q37"})

    def test_name_only_falls_back_to_slug(self) -> None:
        issuer = Issuer.from_name("Some Private Co")
        assert issuer.issuer_id == "slug:some-private-co"
        assert issuer.nodeLabel == "Some Private Co"

    def test_bare_string_is_a_name_not_a_key(self) -> None:
        # Pydantic takes no positional argument, so a bare string is validated.
        assert Issuer.from_string("Apple Inc.").issuer_id == "slug:apple-inc"
        assert Issuer.model_validate("Apple Inc.").issuer_id == "slug:apple-inc"

    def test_bare_string_that_is_a_key_is_used_as_one(self) -> None:
        assert Issuer.from_string("cik:0000320193").issuer_id == APPLE_KEY

    def test_label_falls_back_to_key_without_a_name(self) -> None:
        assert Issuer(issuer_id=APPLE_KEY).nodeLabel == APPLE_KEY

    def test_detect_only_trusts_registry_keys(self) -> None:
        assert Issuer.detect("cik:0000320193")
        assert not Issuer.detect("Apple Inc.")
        assert not Issuer.detect("eodhd:AAPL.US")


class TestSecurity:
    def test_figi_key_is_preferred_form(self) -> None:
        security = Security.from_figi("BBG000B9XRY4", ticker="AAPL")
        assert security.security_id == "figi:BBG000B9XRY4"
        assert security.figi == "BBG000B9XRY4"
        assert security.nodeLabel == "AAPL"

    def test_mic_key_uppercases_both_parts(self) -> None:
        security = Security.from_mic_symbol("xnas", "aapl")
        assert security.security_id == "mic:XNAS:AAPL"
        assert (security.mic, security.ticker) == ("XNAS", "AAPL")

    def test_eodhd_code_splits_out_the_ticker(self) -> None:
        security = Security.from_eodhd_code("aapl.us")
        assert security.security_id == "eodhd:AAPL.US"
        assert security.ticker == "AAPL"

    def test_bare_eodhd_code_string(self) -> None:
        assert Security.from_string("AAPL.US").security_id == "eodhd:AAPL.US"

    def test_valid_identifiers_are_kept(self) -> None:
        security = Security.from_figi(
            "BBG000B9XRY4", cusip="037833100", isin="US0378331005"
        )
        assert security.cusip == "037833100"
        assert security.isin == "US0378331005"

    @pytest.mark.parametrize(
        ("field", "value"),
        [("cusip", "037833101"), ("isin", "US0378331006")],
    )
    def test_bad_checksums_are_rejected_at_the_door(self, field: str, value: str) -> None:
        with pytest.raises((IdentifierError, ValidationError)):
            Security.from_figi("BBG000B9XRY4", **{field: value})

    def test_bad_figi_shape_is_rejected(self) -> None:
        with pytest.raises((IdentifierError, ValidationError)):
            Security(security_id="figi:NOTAFIGI1234")

    def test_mic_key_requires_a_symbol(self) -> None:
        with pytest.raises((IdentifierError, ValidationError)):
            Security(security_id="mic:XNAS")

    def test_listing_window_ordering_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Security.from_figi(
                "BBG000B9XRY4",
                listed_from=date(2024, 1, 2),
                listed_to=date(2023, 1, 2),
            )

    def test_listing_window_answers_ticker_reuse(self) -> None:
        security = Security.from_mic_symbol(
            "XNYS", "OLD", listed_from=date(2010, 1, 1), listed_to=date(2015, 6, 30)
        )
        assert security.was_listed_on(date(2012, 5, 1))
        assert not security.was_listed_on(date(2016, 1, 1))
        assert not security.was_listed_on(date(2009, 12, 31))

    def test_undated_security_is_assumed_listed(self) -> None:
        assert Security.from_mic_symbol("XNAS", "AAPL").was_listed_on(date(2026, 1, 1))

    def test_detect_accepts_isin_and_vendor_code_but_not_a_bare_ticker(self) -> None:
        assert Security.detect("US0378331005")
        assert Security.detect("AAPL.US")
        assert Security.detect("figi:BBG000B9XRY4")
        assert not Security.detect("AAPL")
        assert not Security.detect("US0378331006")  # bad ISIN checksum


class TestPerson:
    def test_cik_keyed_insider(self) -> None:
        person = Person.from_cik(1214156, name="COOK TIMOTHY D", titles=["CEO"])
        assert person.person_id == "cik:0001214156"
        assert person.nodeLabel == "COOK TIMOTHY D"

    def test_same_name_at_different_issuers_stays_distinct(self) -> None:
        a = Person.from_name_at_issuer("John Smith", "cik:0000320193")
        b = Person.from_name_at_issuer("John Smith", "cik:0000789019")
        assert a.person_id != b.person_id
        assert a.person_id == "slug:john-smith@cik:0000320193"

    def test_tenure_ordering_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Person.from_cik(
                1214156, first_seen=date(2024, 1, 1), last_seen=date(2023, 1, 1)
            )

    def test_holds_no_contact_fields(self) -> None:
        # Compliance boundary: public professional roles only (docs/10).
        forbidden = {"email", "phone", "address", "home_address", "location", "dob"}
        assert not forbidden & set(Person.model_fields)


class TestFiling:
    def test_from_edgar_builds_citation_urls(self) -> None:
        filing = Filing.from_edgar(
            APPLE_CIK, "0000320193-24-000123", "10-K", date(2024, 11, 1)
        )
        assert filing.accession == "0000320193-24-000123"
        assert filing.filing_index_url == (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/0000320193-24-000123-index.htm"
        )
        assert filing.nodeLabel == "10-K 2024-11-01"

    def test_undashed_accession_is_normalised(self) -> None:
        assert (
            Filing.from_string("000032019324000123").accession == "0000320193-24-000123"
        )
        assert Filing(accession="000032019324000123").accession == "0000320193-24-000123"

    def test_amendment_is_derived_from_the_form_type(self) -> None:
        filing = Filing(accession="0000320193-24-000123", form_type="10-k/a")
        assert filing.is_amendment is True
        assert filing.base_form() == "10-K"

    def test_plain_form_is_not_an_amendment(self) -> None:
        assert (
            Filing(accession="0000320193-24-000123", form_type="10-K").is_amendment
            is False
        )

    def test_form_meaning_is_documented_for_parsed_forms(self) -> None:
        filing = Filing(accession="0000320193-24-000123", form_type="13F-HR")
        meaning = filing.form_meaning()
        assert meaning is not None and "holdings" in meaning

    def test_archive_dir_requires_the_cik(self) -> None:
        with pytest.raises(ValueError, match="CIK"):
            Filing(accession="0000320193-24-000123").archive_dir()

    def test_detect_recognises_accession_shape(self) -> None:
        assert Filing.detect("0000320193-24-000123")
        assert not Filing.detect("10-K")


class TestInsiderTransaction:
    def test_key_includes_the_line_number(self) -> None:
        txn = InsiderTransaction.from_form4("0000320193-24-000123", 2)
        assert txn.transaction_id == "form4:0000320193-24-000123:2"
        assert txn.accession == "0000320193-24-000123"
        assert txn.line_number == 2

    def test_two_lines_of_one_filing_do_not_collide(self) -> None:
        a = InsiderTransaction.from_form4("0000320193-24-000123", 1)
        b = InsiderTransaction.from_form4("0000320193-24-000123", 2)
        assert a.transaction_id != b.transaction_id

    def test_value_is_derived_when_absent(self) -> None:
        txn = InsiderTransaction.from_form4(
            "0000320193-24-000123", 1, shares=1000, price_per_share=225.5
        )
        assert txn.value == 225500.0

    def test_reported_value_is_not_overwritten(self) -> None:
        txn = InsiderTransaction.from_form4(
            "0000320193-24-000123", 1, shares=1000, price_per_share=225.5, value=1.0
        )
        assert txn.value == 1.0

    def test_unknown_transaction_code_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InsiderTransaction.from_form4("0000320193-24-000123", 1, transaction_code="Q")

    def test_accession_disagreement_is_caught(self) -> None:
        with pytest.raises(ValidationError, match="disagrees"):
            InsiderTransaction(
                transaction_id="form4:0000320193-24-000123:1",
                accession="0000789019-24-000001",
            )

    def test_planned_sales_are_separable_from_discretionary_ones(self) -> None:
        discretionary = InsiderTransaction.from_form4(
            "0000320193-24-000123", 1, transaction_code="S", acquired_disposed="D"
        )
        planned = InsiderTransaction.from_form4(
            "0000320193-24-000123", 2, transaction_code="S", is_10b5_1=True
        )
        grant = InsiderTransaction.from_form4(
            "0000320193-24-000123", 3, transaction_code="A"
        )
        assert discretionary.is_discretionary_signal()
        assert not planned.is_discretionary_signal()
        assert not grant.is_open_market()
        grant_meaning = grant.code_meaning()
        assert grant_meaning is not None and "grant" in grant_meaning

    def test_label_reads_as_a_trade(self) -> None:
        txn = InsiderTransaction.from_form4(
            "0000320193-24-000123",
            1,
            transaction_code="S",
            acquired_disposed="D",
            shares=100000,
            transaction_date=date(2024, 10, 28),
        )
        assert txn.nodeLabel == "S sell 100,000 2024-10-28"

    def test_actor_type_defaults_to_insider(self) -> None:
        assert (
            InsiderTransaction.from_form4("0000320193-24-000123", 1).actor_type
            == "insider"
        )


class TestFact:
    def test_key_shape(self) -> None:
        fact = Fact.from_xbrl(
            APPLE_CIK, "Revenues", "USD", 391_035_000_000.0, period="FY2025"
        )
        assert fact.fact_id == "xbrl:0000320193:Revenues:USD:FY2025"
        assert fact.nodeLabel == "Revenues FY2025"

    def test_accession_pins_a_vintage(self) -> None:
        fact = Fact.from_xbrl(
            APPLE_CIK,
            "Revenues",
            "USD",
            1.0,
            period="FY2025",
            accession="0000320193-24-000123",
        )
        assert fact.fact_id.endswith(":0000320193-24-000123")

    def test_restatement_links_to_the_superseded_vintage(self) -> None:
        original = Fact.from_xbrl(APPLE_CIK, "Revenues", "USD", 1.0, period="FY2025")
        revised = Fact.from_xbrl(
            APPLE_CIK,
            "Revenues",
            "USD",
            2.0,
            period="FY2025",
            accession="0000320193-25-000001",
            restates=original.fact_id,
        )
        assert revised.restates == original.fact_id
        assert revised.fact_id != original.fact_id

    def test_instant_and_duration_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValidationError):
            Fact.from_xbrl(
                APPLE_CIK,
                "Assets",
                "USD",
                1.0,
                period="FY2025",
                instant=date(2025, 9, 27),
                period_end=date(2025, 9, 27),
            )

    def test_instant_facts_are_flagged(self) -> None:
        fact = Fact.from_xbrl(
            APPLE_CIK, "Assets", "USD", 1.0, period="FY2025", instant=date(2025, 9, 27)
        )
        assert fact.is_instant()

    def test_period_ordering_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Fact.from_xbrl(
                APPLE_CIK,
                "Revenues",
                "USD",
                1.0,
                period="FY2025",
                period_start=date(2025, 9, 27),
                period_end=date(2024, 9, 29),
            )


class TestProvenanceOnTypes:
    def test_helper_fills_defaults(self) -> None:
        issuer = Issuer.from_cik(
            APPLE_CIK,
            name="Apple Inc.",
            **provenance("sec_edgar", source_ref="https://www.sec.gov/x", scan_id="s1"),
        )
        assert issuer.is_cited()
        assert issuer.confidence == 1.0
        assert issuer.fetch_outcome == "ok"
        assert issuer.retrieved_at is not None

    def test_vendor_parsed_gets_a_lower_default(self) -> None:
        issuer = Issuer.from_cik(APPLE_CIK, **provenance("eodhd", method="vendor_parsed"))
        assert issuer.confidence == 0.8

    def test_uncited_node_is_detectable(self) -> None:
        assert not Issuer.from_cik(APPLE_CIK).is_cited()

    def test_derived_values_must_name_their_rule(self) -> None:
        with pytest.raises(ValidationError, match="rule"):
            Issuer.from_cik(
                APPLE_CIK,
                source="derived",
                method="derived",
                retrieved_at=datetime.now(UTC),
            )

    def test_derived_with_a_rule_is_accepted(self) -> None:
        issuer = Issuer.from_cik(
            APPLE_CIK, **provenance("derived", method="derived", rule="peer_set_v1")
        )
        assert issuer.rule == "peer_set_v1"

    def test_operator_assertions_are_capped(self) -> None:
        with pytest.raises(ValidationError, match="capped"):
            Issuer.from_cik(
                APPLE_CIK,
                **provenance("operator", method="operator_assertion", confidence=0.9),
            )

    def test_confidence_stays_in_range(self) -> None:
        with pytest.raises(ValidationError):
            Issuer.from_cik(APPLE_CIK, source="eodhd", confidence=1.5)


class TestUpstreamPreprocessCompatibility:
    """Survive how Flowsint actually hands input to an enricher.

    ``Enricher.preprocess()`` finds the field marked ``primary`` and wraps a bare string
    as ``{primary_field: value}`` before validation, then skips anything that fails
    validation **silently** (``except Exception: continue``). So a UI seed of "AAPL"
    must not raise on the way in, or it vanishes with no error anywhere
    (docs/02-flowsint-primer.md).
    """

    @staticmethod
    def _as_preprocess_would(model: type[BaseModel], value: str) -> Any:
        primary = next(
            name
            for name, field in model.model_fields.items()
            if isinstance(field.json_schema_extra, dict)
            and field.json_schema_extra.get("primary")
        )
        return model.model_validate({primary: value})

    def test_issuer_name_seed(self) -> None:
        issuer = self._as_preprocess_would(Issuer, "Apple Inc.")
        assert issuer.issuer_id == "slug:apple-inc"
        assert issuer.name == "Apple Inc."

    def test_issuer_bare_cik_seed(self) -> None:
        assert self._as_preprocess_would(Issuer, "320193").issuer_id == APPLE_KEY
        assert self._as_preprocess_would(Issuer, "CIK0000320193").issuer_id == APPLE_KEY

    def test_security_vendor_code_seed(self) -> None:
        security = self._as_preprocess_would(Security, "AAPL.US")
        assert security.security_id == "eodhd:AAPL.US"
        assert security.ticker == "AAPL"

    def test_security_isin_seed_is_provisional(self) -> None:
        security = self._as_preprocess_would(Security, "US0378331005")
        assert security.isin == "US0378331005"
        assert security.security_id.startswith("slug:")  # resolver must replace it

    def test_security_bare_ticker_seed_is_provisional(self) -> None:
        security = self._as_preprocess_would(Security, "aapl")
        assert security.ticker == "AAPL"
        assert security.security_id == "slug:aapl"

    def test_person_name_seed(self) -> None:
        person = self._as_preprocess_would(Person, "Cook Timothy D")
        assert person.name == "Cook Timothy D"
        assert person.person_id == "slug:cook-timothy-d"

    def test_filing_accession_seed(self) -> None:
        filing = self._as_preprocess_would(Filing, "000032019324000123")
        assert filing.accession == "0000320193-24-000123"
