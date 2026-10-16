"""Identifier checksums, verified against published identifiers.

A mistyped identifier that validates is two companies merged into one node, so these
algorithms are implemented and tested rather than assumed.
"""

from __future__ import annotations

import pytest

from market_types.identifiers import (
    IdentifierError,
    accession_compact,
    accession_filer_cik,
    cusip_check_digit,
    is_valid_cusip,
    is_valid_figi,
    is_valid_isin,
    is_valid_lei,
    is_valid_mic,
    isin_check_digit,
    normalize_accession,
    normalize_cik,
)


class TestCik:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (320193, "0000320193"),
            ("320193", "0000320193"),
            ("0000320193", "0000320193"),
            ("CIK0000320193", "0000320193"),
            ("cik:0000789019", "0000789019"),
            (1, "0000000001"),
        ],
    )
    def test_normalizes_to_ten_digits(self, value: str | int, expected: str) -> None:
        assert normalize_cik(value) == expected

    @pytest.mark.parametrize("value", ["", "no-digits", "12345678901"])
    def test_rejects_unusable(self, value: str) -> None:
        with pytest.raises(IdentifierError):
            normalize_cik(value)


class TestAccession:
    def test_accepts_either_spelling(self) -> None:
        assert normalize_accession("000032019324000123") == "0000320193-24-000123"
        assert normalize_accession("0000320193-24-000123") == "0000320193-24-000123"

    def test_compact_form_is_archive_path_form(self) -> None:
        assert accession_compact("0000320193-24-000123") == "000032019324000123"

    def test_filer_cik_is_the_transmitting_entity(self) -> None:
        assert accession_filer_cik("0001234567-24-000001") == "0001234567"

    @pytest.mark.parametrize("value", ["", "0000320193-24", "abc", "123-45-678"])
    def test_rejects_malformed(self, value: str) -> None:
        with pytest.raises(IdentifierError):
            normalize_accession(value)


class TestCusip:
    # Published CUSIPs: Apple, Microsoft, Tesla.
    @pytest.mark.parametrize("cusip", ["037833100", "594918104", "88160R101"])
    def test_accepts_published_cusips(self, cusip: str) -> None:
        assert is_valid_cusip(cusip)
        assert cusip_check_digit(cusip[:8]) == cusip[8]

    @pytest.mark.parametrize("cusip", ["037833101", "594918105", "88160R102"])
    def test_rejects_wrong_check_digit(self, cusip: str) -> None:
        assert not is_valid_cusip(cusip)

    @pytest.mark.parametrize("cusip", ["", "03783310", "0378331000", "03783310!"])
    def test_rejects_malformed(self, cusip: str) -> None:
        assert not is_valid_cusip(cusip)

    def test_body_must_be_eight_characters(self) -> None:
        with pytest.raises(IdentifierError):
            cusip_check_digit("0378331")


class TestIsin:
    # Published ISINs: Apple, Microsoft, Tesla, SAP (non-US prefix).
    @pytest.mark.parametrize(
        "isin",
        ["US0378331005", "US5949181045", "US88160R1014", "DE0007164600"],
    )
    def test_accepts_published_isins(self, isin: str) -> None:
        assert is_valid_isin(isin)
        assert isin_check_digit(isin[:11]) == isin[11]

    @pytest.mark.parametrize("isin", ["US0378331006", "US5949181046", "DE0007164601"])
    def test_rejects_wrong_check_digit(self, isin: str) -> None:
        assert not is_valid_isin(isin)

    @pytest.mark.parametrize("isin", ["", "US037833100", "0378331005US", "US03783310055"])
    def test_rejects_malformed(self, isin: str) -> None:
        assert not is_valid_isin(isin)


class TestLei:
    def test_accepts_published_lei(self) -> None:
        # Apple Inc.'s LEI; ISO 7064 MOD 97-10 over the full 20 characters.
        assert is_valid_lei("HWUPKR0MPOU8FGXBT394")

    def test_is_case_insensitive(self) -> None:
        assert is_valid_lei("hwupkr0mpou8fgxbt394")

    @pytest.mark.parametrize(
        "lei",
        [
            "549300C116EOWC307Q37",  # structurally fine, checksum fails
            "HWUPKR0MPOU8FGXBT395",  # altered check digits
            "HWUPKR0MPOU8FGXBT39",  # too short
            "",
        ],
    )
    def test_rejects_bad_lei(self, lei: str) -> None:
        assert not is_valid_lei(lei)


class TestFigiAndMic:
    @pytest.mark.parametrize("figi", ["BBG000B9XRY4", "BBG000BPH459"])
    def test_accepts_figi_shape(self, figi: str) -> None:
        assert is_valid_figi(figi)

    @pytest.mark.parametrize(
        "figi",
        [
            "BBG000B9XRY",  # too short
            "XXX000B9XRY4",  # wrong prefix
            "BBG000B9XRYA",  # last character must be a digit
            "BBG000A9XRY4",  # vowel in the body
        ],
    )
    def test_rejects_bad_figi_shape(self, figi: str) -> None:
        assert not is_valid_figi(figi)

    @pytest.mark.parametrize("mic", ["XNAS", "XNYS", "XLON", "ARCX"])
    def test_accepts_mic(self, mic: str) -> None:
        assert is_valid_mic(mic)

    @pytest.mark.parametrize("mic", ["XNA", "XNASD", "", "xn-s"])
    def test_rejects_bad_mic(self, mic: str) -> None:
        assert not is_valid_mic(mic)
