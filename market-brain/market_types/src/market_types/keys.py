"""Merge-key construction and parsing.

Every market entity's merge key is a *namespaced* registry identifier, never a ticker
(docs/adr/0006-registry-ids-as-merge-keys.md). The namespace prefix makes a key
self-describing, which means a node can answer "how firmly is this thing identified?"
on its own: a ``slug:`` key says resolution has not finished.

Canonical forms::

    cik:0000320193            issuer / person / institution, SEC Central Index Key
    lei:HWUPKR0MPOU8FGXBT394  legal entity identifier (ISO 17442)
    figi:BBG000B9XRY4         security, share-class precise (preferred)
    mic:XNAS:AAPL             security, ISO 10383 venue + local symbol
    eodhd:AAPL.US             security, vendor code (last resort)
    slug:apple-inc            unresolved; carries no registry authority
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final, Literal

NS_CIK: Final = "cik"
NS_LEI: Final = "lei"
NS_FIGI: Final = "figi"
NS_MIC: Final = "mic"
NS_EODHD: Final = "eodhd"
NS_SLUG: Final = "slug"
NS_XBRL: Final = "xbrl"
NS_FORM4: Final = "form4"
NS_13F: Final = "13f"
NS_POS: Final = "pos"

Namespace = Literal[
    "cik", "lei", "figi", "mic", "eodhd", "slug", "xbrl", "form4", "13f", "pos"
]

#: Namespaces that carry registry authority. A key outside this set means identity
#: resolution is incomplete and the node should be revisited.
AUTHORITATIVE: Final[frozenset[str]] = frozenset({NS_CIK, NS_LEI, NS_FIGI, NS_MIC})

_KEY_RE = re.compile(r"^(?P<ns>[a-z0-9]+):(?P<value>.+)$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_LEGAL_SUFFIXES: Final[tuple[str, ...]] = (
    "incorporated",
    "inc",
    "corporation",
    "corp",
    "company",
    "co",
    "limited",
    "ltd",
    "plc",
    "llc",
    "lp",
    "nv",
    "sa",
    "ag",
    "se",
    "holdings",
    "holding",
    "group",
)


class KeyError_(ValueError):
    """Raised when a merge key is malformed."""


def build_key(namespace: str, *parts: str) -> str:
    """Build a merge key from a namespace and one or more value parts.

    >>> build_key("mic", "XNAS", "AAPL")
    'mic:XNAS:AAPL'
    """
    if namespace not in get_namespaces():
        raise KeyError_(f"unknown key namespace {namespace!r}")
    if not parts or any(not str(p).strip() for p in parts):
        raise KeyError_(f"empty value part in key for namespace {namespace!r}")
    return ":".join([namespace, *(str(p).strip() for p in parts)])


def parse_key(key: str) -> tuple[str, str]:
    """Split a merge key into ``(namespace, value)``.

    >>> parse_key("cik:0000320193")
    ('cik', '0000320193')
    """
    match = _KEY_RE.match(str(key).strip())
    if not match:
        raise KeyError_(f"not a namespaced key: {key!r}")
    return match.group("ns"), match.group("value")


def is_key(value: object) -> bool:
    """True when ``value`` already looks like a namespaced merge key."""
    return bool(isinstance(value, str) and _KEY_RE.match(value.strip()))


def key_namespace(key: str) -> str:
    return parse_key(key)[0]


def is_authoritative(key: str) -> bool:
    """True when the key comes from a registry rather than a fallback slug."""
    return key_namespace(key) in AUTHORITATIVE


def get_namespaces() -> frozenset[str]:
    return frozenset(
        {
            NS_CIK,
            NS_LEI,
            NS_FIGI,
            NS_MIC,
            NS_EODHD,
            NS_SLUG,
            NS_XBRL,
            NS_FORM4,
            NS_13F,
            NS_POS,
        }
    )


def slugify(text: str, *, strip_legal_suffix: bool = False) -> str:
    """Normalise free text into a slug usable as a fallback key value.

    >>> slugify("Berkshire Hathaway Inc.")
    'berkshire-hathaway-inc'
    >>> slugify("Berkshire Hathaway Inc.", strip_legal_suffix=True)
    'berkshire-hathaway'
    """
    if not text or not str(text).strip():
        raise KeyError_("cannot slugify empty text")
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_STRIP.sub("-", ascii_only).strip("-")
    if strip_legal_suffix:
        tokens = [t for t in slug.split("-") if t]
        while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
            tokens.pop()
        slug = "-".join(tokens)
    if not slug:
        raise KeyError_(f"text slugified to nothing: {text!r}")
    return slug
