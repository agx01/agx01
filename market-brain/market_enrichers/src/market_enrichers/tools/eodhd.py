"""EODHD client.

**Endpoint paths and response shapes here are unverified** from the authoring
environment, which cannot reach the vendor (../docs/12-environment-notes.md), and EODHD
is consumed in the design docs through its MCP server, whose tool names do not map
one-to-one onto REST paths. An enricher running inside Flowsint has no MCP client, so it
needs the REST API and an API token from the vault.

Treat every ``PATH_*`` constant and every parser below as a **draft to validate against
EODHD's own documentation** before relying on it (../docs/references.md, V2). The generic
:meth:`EodhdClient.get` exists so a corrected path can be used without waiting for this
module to catch up.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Optional

from .http import (
    TTL_PROFILE,
    TTL_SECURITY_META,
    RetrievalRecord,
    SourceClient,
    SourceError,
)

BASE = "https://eodhd.com/api"

# ⚠️ Draft paths — verify each against EODHD's documentation.
PATH_SEARCH = "/search/{query}"
PATH_FUNDAMENTALS = "/fundamentals/{symbol}"
PATH_EXCHANGE_SYMBOLS = "/exchange-symbol-list/{exchange}"
PATH_INSIDER_TRANSACTIONS = "/insider-transactions"

#: Conservative: the real allowance is plan-dependent, so a scan should not assume more.
DEFAULT_RATE_PER_SECOND = 2.0


class EodhdError(SourceError):
    """An EODHD request or payload could not be used."""


class EodhdClient:
    """Minimal token-authenticated client. Every call returns its retrieval record."""

    def __init__(self, api_key: Optional[str], client: SourceClient) -> None:
        if not api_key:
            raise EodhdError(
                "EODHD requires an API token. Create the EODHD_API_KEY vault secret "
                "(../docs/09-security-and-secrets.md)."
            )
        self.api_key = api_key
        self.client = client

    def get(
        self,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        ttl: Optional[float] = TTL_SECURITY_META,
        cache_mode: str = "prefer_cache",
    ) -> tuple[Any, RetrievalRecord]:
        """GET a path under the API base, with the token and JSON format applied.

        The token is added to the query at request time and is **not** part of the
        request hash, so a rotated key does not invalidate the whole cache and the key
        never lands in a cache filename.
        """
        query = {"fmt": "json", **dict(params or {})}
        url = f"{BASE}{path}"
        cache_key_url = self.client.build_url(url, query)
        authed = self.client.build_url(url, {**query, "api_token": self.api_key})
        body, record = self.client.get_bytes(
            authed,
            ttl=ttl,
            cache_mode=cache_mode,
            headers={"Accept": "application/json"},
        )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EodhdError(f"eodhd: invalid JSON from {cache_key_url}: {exc}") from exc
        # Report the unauthenticated URL: provenance is citable, and a stored source_ref
        # must never carry a credential (../docs/09-security-and-secrets.md).
        return payload, RetrievalRecord(
            source=record.source,
            url=cache_key_url,
            request_hash=record.request_hash,
            retrieved_at=record.retrieved_at,
            status=record.status,
            from_cache=record.from_cache,
            outcome=record.outcome,
            age_seconds=record.age_seconds,
        )

    def search(
        self, query: str, *, limit: int = 10, cache_mode: str = "prefer_cache"
    ) -> tuple[Any, RetrievalRecord]:
        """Resolve free text to candidate instruments."""
        return self.get(
            PATH_SEARCH.format(query=query.strip()),
            params={"limit": limit},
            ttl=TTL_SECURITY_META,
            cache_mode=cache_mode,
        )

    def fundamentals(
        self, symbol: str, *, cache_mode: str = "prefer_cache"
    ) -> tuple[Any, RetrievalRecord]:
        """Company fundamentals, used here only for identity and classification."""
        return self.get(
            PATH_FUNDAMENTALS.format(symbol=symbol.strip().upper()),
            ttl=TTL_PROFILE,
            cache_mode=cache_mode,
        )

    # --- parsers (shapes unverified; defensive on purpose) ---------------------------

    @staticmethod
    def parse_search_hits(payload: Any) -> list[dict[str, Any]]:
        """Normalise search results to the fields our Security type needs.

        Accepts either a bare list or ``{"data": [...]}``, and tolerates the key-casing
        differences between EODHD responses.
        """
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []
        hits: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("Code") or row.get("code")
            exchange = row.get("Exchange") or row.get("exchange")
            if not code:
                continue
            hits.append(
                {
                    "code": str(code).upper(),
                    "exchange": str(exchange).upper() if exchange else None,
                    "eodhd_code": (
                        f"{str(code).upper()}.{str(exchange).upper()}"
                        if exchange
                        else None
                    ),
                    "name": row.get("Name") or row.get("name"),
                    "isin": row.get("ISIN") or row.get("isin"),
                    "currency": row.get("Currency") or row.get("currency"),
                    "security_type": row.get("Type") or row.get("type"),
                    "country": row.get("Country") or row.get("country"),
                }
            )
        return hits

    @staticmethod
    def parse_identity(payload: Any) -> dict[str, Any]:
        """Pull issuer identity out of a fundamentals payload.

        Only identity and classification are read. Financial values come from EDGAR,
        which is authoritative; a vendor's computed figures are not stored as facts
        (../docs/04-data-sources.md#source-precedence).
        """
        if not isinstance(payload, dict):
            return {}
        general = payload.get("General") or payload.get("general") or {}
        if not isinstance(general, dict):
            return {}
        return {
            "cik": general.get("CIK") or general.get("cik"),
            "lei": general.get("LEI") or general.get("lei"),
            "name": general.get("Name") or general.get("name"),
            "isin": general.get("ISIN") or general.get("isin"),
            "cusip": general.get("CUSIP") or general.get("cusip"),
            "exchange": general.get("Exchange") or general.get("exchange"),
            "currency": general.get("CurrencyCode") or general.get("currency"),
            "country": general.get("CountryISO") or general.get("country"),
            "sector": general.get("Sector") or general.get("sector"),
            "industry": general.get("Industry") or general.get("industry"),
            "website": general.get("WebURL") or general.get("website"),
            "employees": general.get("FullTimeEmployees") or general.get("employees"),
            "fiscal_year_end": general.get("FiscalYearEnd"),
            "description": general.get("Description"),
        }
