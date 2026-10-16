"""Merge-key construction, parsing and slugging."""

from __future__ import annotations

import pytest

from market_types.keys import (
    AUTHORITATIVE,
    KeyError_,
    build_key,
    is_authoritative,
    is_key,
    key_namespace,
    parse_key,
    slugify,
)


class TestBuildAndParse:
    def test_single_part(self) -> None:
        assert build_key("cik", "0000320193") == "cik:0000320193"

    def test_multi_part(self) -> None:
        assert build_key("mic", "XNAS", "AAPL") == "mic:XNAS:AAPL"

    def test_round_trips(self) -> None:
        assert parse_key(build_key("figi", "BBG000B9XRY4")) == ("figi", "BBG000B9XRY4")

    def test_multi_part_value_keeps_its_colons(self) -> None:
        assert parse_key("mic:XNAS:AAPL") == ("mic", "XNAS:AAPL")

    def test_rejects_unknown_namespace(self) -> None:
        with pytest.raises(KeyError_):
            build_key("ticker", "AAPL")

    @pytest.mark.parametrize("parts", [(), ("",), ("XNAS", " ")])
    def test_rejects_empty_parts(self, parts: tuple[str, ...]) -> None:
        with pytest.raises(KeyError_):
            build_key("mic", *parts)

    @pytest.mark.parametrize("value", ["", "AAPL", "no-namespace", ":value", "CIK:123"])
    def test_rejects_unnamespaced(self, value: str) -> None:
        with pytest.raises(KeyError_):
            parse_key(value)
        assert not is_key(value)


class TestAuthority:
    @pytest.mark.parametrize(
        "key",
        [
            "cik:0000320193",
            "lei:HWUPKR0MPOU8FGXBT394",
            "figi:BBG000B9XRY4",
            "mic:XNAS:AAPL",
        ],
    )
    def test_registry_keys_are_authoritative(self, key: str) -> None:
        assert is_authoritative(key)

    @pytest.mark.parametrize("key", ["slug:apple-inc", "eodhd:AAPL.US"])
    def test_fallback_keys_are_not(self, key: str) -> None:
        assert not is_authoritative(key)

    def test_namespace_accessor(self) -> None:
        assert key_namespace("eodhd:AAPL.US") == "eodhd"

    def test_authoritative_set_is_explicit(self) -> None:
        assert frozenset({"cik", "lei", "figi", "mic"}) == AUTHORITATIVE


class TestSlugify:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Apple Inc.", "apple-inc"),
            ("Berkshire Hathaway Inc.", "berkshire-hathaway-inc"),
            ("  Taiwan  Semiconductor   Mfg  ", "taiwan-semiconductor-mfg"),
            ("Nestlé S.A.", "nestle-s-a"),
            ("AT&T", "at-t"),
            ("3M", "3m"),
        ],
    )
    def test_normalises(self, text: str, expected: str) -> None:
        assert slugify(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Berkshire Hathaway Inc.", "berkshire-hathaway"),
            ("Apple Incorporated", "apple"),
            ("Barclays PLC", "barclays"),
            ("Alphabet Inc. Holdings", "alphabet"),
            ("Inc", "inc"),  # never strips to nothing
        ],
    )
    def test_optional_legal_suffix_stripping(self, text: str, expected: str) -> None:
        assert slugify(text, strip_legal_suffix=True) == expected

    @pytest.mark.parametrize("text", ["", "   ", "!!!", "...", "—"])
    def test_rejects_text_that_slugs_to_nothing(self, text: str) -> None:
        with pytest.raises(KeyError_):
            slugify(text)

    def test_is_stable_for_the_same_input(self) -> None:
        assert slugify("Micron Technology, Inc.") == slugify("micron   technology , inc.")
