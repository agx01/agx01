"""Validation and normalisation of market and regulatory identifiers.

Checksum algorithms are implemented rather than trusted, because a mistyped CUSIP that
validates is a graph with two companies merged into one node. Each function is pure and
unit-tested against published identifiers (see ``tests/test_identifiers.py``).
"""

from __future__ import annotations

import re
from typing import Final

_CIK_DIGITS = re.compile(r"\d+")
_ACCESSION_RE = re.compile(r"^(?P<a>\d{10})-?(?P<b>\d{2})-?(?P<c>\d{6})$")
_CUSIP_RE = re.compile(r"^[0-9A-Z*@#]{9}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{9}\d$")
_FIGI_RE = re.compile(r"^BBG[0-9BCDFGHJKLMNPQRSTVWXYZ]{8}\d$")
_LEI_RE = re.compile(r"^[0-9A-Z]{18}\d{2}$")
_MIC_RE = re.compile(r"^[A-Z0-9]{4}$")

_CUSIP_VALUES: Final[dict[str, int]] = {
    **{str(d): d for d in range(10)},
    **{chr(ord("A") + i): 10 + i for i in range(26)},
    "*": 36,
    "@": 37,
    "#": 38,
}


class IdentifierError(ValueError):
    """Raised when an identifier is structurally invalid or fails its checksum."""


# --- SEC CIK -------------------------------------------------------------------------


def normalize_cik(value: str | int) -> str:
    """Zero-pad a CIK to the 10-digit form EDGAR uses.

    >>> normalize_cik(320193)
    '0000320193'
    >>> normalize_cik("CIK0000320193")
    '0000320193'
    """
    digits = "".join(_CIK_DIGITS.findall(str(value)))
    if not digits:
        raise IdentifierError(f"no digits in CIK {value!r}")
    stripped = digits.lstrip("0") or "0"
    if len(stripped) > 10:
        raise IdentifierError(f"CIK too long: {value!r}")
    return stripped.zfill(10)


# --- SEC accession number ------------------------------------------------------------


def normalize_accession(value: str) -> str:
    """Return the dashed accession form, accepting either spelling.

    >>> normalize_accession("000032019324000123")
    '0000320193-24-000123'
    """
    match = _ACCESSION_RE.match(str(value).strip())
    if not match:
        raise IdentifierError(f"malformed accession number: {value!r}")
    return f"{match.group('a')}-{match.group('b')}-{match.group('c')}"


def accession_compact(value: str) -> str:
    """Return the undashed accession form used in EDGAR archive paths."""
    return normalize_accession(value).replace("-", "")


def accession_filer_cik(value: str) -> str:
    """The CIK of the filing *agent* embedded in an accession number.

    This is the entity that transmitted the filing, which is often a filing agent rather
    than the subject company — do not use it as an issuer key.
    """
    return normalize_accession(value).split("-")[0]


# --- CUSIP ---------------------------------------------------------------------------


def cusip_check_digit(body: str) -> str:
    """Compute the 9th-position CUSIP check digit from the first 8 characters."""
    body = str(body).strip().upper()
    if len(body) != 8:
        raise IdentifierError(f"CUSIP body must be 8 characters, got {body!r}")
    total = 0
    for position, char in enumerate(body, start=1):
        try:
            value = _CUSIP_VALUES[char]
        except KeyError as exc:
            raise IdentifierError(f"invalid CUSIP character {char!r}") from exc
        if position % 2 == 0:
            value *= 2
        total += value // 10 + value % 10
    return str((10 - total % 10) % 10)


def is_valid_cusip(value: str) -> bool:
    """True when ``value`` is 9 characters with a correct check digit."""
    candidate = str(value).strip().upper()
    if not _CUSIP_RE.match(candidate):
        return False
    try:
        return cusip_check_digit(candidate[:8]) == candidate[8]
    except IdentifierError:
        return False


# --- ISIN ----------------------------------------------------------------------------


def isin_check_digit(body: str) -> str:
    """Compute the ISIN check digit (ISO 6166: letter expansion, then Luhn)."""
    body = str(body).strip().upper()
    if len(body) != 11:
        raise IdentifierError(f"ISIN body must be 11 characters, got {body!r}")
    try:
        digits = "".join(str(int(char, 36)) for char in body)
    except ValueError as exc:
        raise IdentifierError(f"invalid ISIN character in {body!r}") from exc
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def is_valid_isin(value: str) -> bool:
    candidate = str(value).strip().upper()
    if not _ISIN_RE.match(candidate):
        return False
    try:
        return isin_check_digit(candidate[:11]) == candidate[11]
    except IdentifierError:
        return False


# --- LEI -----------------------------------------------------------------------------


def is_valid_lei(value: str) -> bool:
    """True when ``value`` passes the ISO 17442 / ISO 7064 MOD 97-10 checksum."""
    candidate = str(value).strip().upper()
    if not _LEI_RE.match(candidate):
        return False
    try:
        numeric = int("".join(str(int(char, 36)) for char in candidate))
    except ValueError:
        return False
    return numeric % 97 == 1


# --- FIGI ----------------------------------------------------------------------------


def is_valid_figi(value: str) -> bool:
    """Structural check for an OpenFIGI identifier.

    Verifies the ``BBG`` prefix, the 12-character length, and the consonant-only
    alphabet the standard uses to avoid spelling words. The trailing check digit is
    *not* verified — that algorithm is not implemented here, so a structurally valid
    FIGI can still be wrong. Treat this as a typo filter, not proof of existence.
    """
    candidate = str(value).strip().upper()
    return bool(_FIGI_RE.match(candidate))


# --- MIC -----------------------------------------------------------------------------


def is_valid_mic(value: str) -> bool:
    """Structural check for an ISO 10383 Market Identifier Code (4 alphanumerics)."""
    return bool(_MIC_RE.match(str(value).strip().upper()))
