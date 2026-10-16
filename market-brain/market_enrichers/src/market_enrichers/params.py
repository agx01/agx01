"""Reusable parameter-schema fragments.

Upstream's schema entries are plain dicts with ``name``, ``type`` (``string``, ``number``,
``select``, ``url`` or ``vaultSecret``), ``description`` and optional ``required``,
``default`` and ``options`` — verified in ``flowsint-core/.../enricher_base.py``.

Secrets are declared as ``vaultSecret`` and read with ``self.get_secret(name)``.
``resolve_params()`` looks them up in the vault by the vault ID passed in params, then by
the parameter name itself, and raises when a required one is missing. Never a literal,
never ``os.environ`` inside an enricher (../docs/09-security-and-secrets.md).
"""

from __future__ import annotations

from typing import Any

#: SEC fair access requires a declared User-Agent naming the requester with a contact
#: address. It is a secret because it contains an email address.
SEC_USER_AGENT: dict[str, Any] = {
    "name": "SEC_USER_AGENT",
    "type": "vaultSecret",
    "description": (
        "Declared User-Agent for SEC fair access, e.g. 'market-brain you@example.com'. "
        "Create this key in Vault settings before running any EDGAR enricher."
    ),
    "required": True,
}

EODHD_API_KEY: dict[str, Any] = {
    "name": "EODHD_API_KEY",
    "type": "vaultSecret",
    "description": "EODHD API token. Create it in Vault settings.",
    "required": True,
}

FORM_TYPES: dict[str, Any] = {
    "name": "form_types",
    "type": "string",
    "description": "Comma-separated SEC form types, e.g. 10-K,10-Q,8-K. Empty means all.",
    "default": "10-K,10-Q,8-K",
}

SINCE: dict[str, Any] = {
    "name": "since",
    "type": "string",
    "description": "ISO date lower bound (inclusive), e.g. 2024-01-01.",
    "required": False,
}

LIMIT: dict[str, Any] = {
    "name": "limit",
    "type": "number",
    "description": "Maximum number of results to write per input.",
    "default": 50,
}

TAGS: dict[str, Any] = {
    "name": "tags",
    "type": "string",
    "description": (
        "Comma-separated XBRL concepts, e.g. Revenues,NetIncomeLoss,Assets. "
        "Empty means a default statement set."
    ),
    "default": "Revenues,NetIncomeLoss,Assets,Liabilities,StockholdersEquity",
}

CACHE_MODE: dict[str, Any] = {
    "name": "cache_mode",
    "type": "select",
    "description": (
        "fresh: always refetch. prefer_cache: serve a cached copy within its TTL. "
        "offline: never fetch, serve cache only (marks data cached_stale)."
    ),
    "default": "prefer_cache",
    "options": ["prefer_cache", "fresh", "offline"],
}


def schema(*fragments: dict[str, Any]) -> list[dict[str, Any]]:
    """Compose a params schema, rejecting duplicate parameter names.

    >>> [p["name"] for p in schema(SINCE, LIMIT)]
    ['since', 'limit']
    >>> schema(SINCE, SINCE)
    Traceback (most recent call last):
    ...
    ValueError: duplicate parameter name: since
    """
    seen: set[str] = set()
    composed: list[dict[str, Any]] = []
    for fragment in fragments:
        name = fragment["name"]
        if name in seen:
            raise ValueError(f"duplicate parameter name: {name}")
        seen.add(name)
        composed.append(dict(fragment))
    return composed


def csv_param(raw: Any) -> list[str]:
    """Split a comma-separated param into a clean list.

    >>> csv_param(" 10-K , 10-Q ,, ")
    ['10-K', '10-Q']
    >>> csv_param(None)
    []
    """
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]
