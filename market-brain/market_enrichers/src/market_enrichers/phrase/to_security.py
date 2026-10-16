"""Resolve free text to a security — the gatekeeper hop."""

from __future__ import annotations

from typing import Any, Optional

from flowsint_types.phrase import Phrase
from market_types.keys import is_authoritative, is_key
from market_types.security import Security

from .._base import flowsint_enricher
from ..market_enricher import MarketEnricher
from ..params import CACHE_MODE, EODHD_API_KEY, LIMIT, schema


@flowsint_enricher
class AliasToSecurityEnricher(MarketEnricher):
    """[EODHD] Resolve a ticker, name or ISIN to a security with its aliases.

    Every entry into the graph goes through this hop, which is what keeps the merge-key
    discipline in ../docs/adr/0006-registry-ids-as-merge-keys.md true by construction: a
    human types "apple" or "AAPL", and what lands is a `Security` keyed on a vendor or
    venue identifier with the ticker recorded as an alias.

    When the seed itself already parses as a provisional key (`slug:aapl`), the resolved
    node is linked back with `SAME_AS` rather than merged, so the evidence for why two
    nodes are one thing is kept (../docs/03-ontology.md).
    """

    InputType = Phrase
    OutputType = Security

    source = "eodhd"

    @classmethod
    def name(cls) -> str:
        return "alias_to_security"

    @classmethod
    def key(cls) -> str:
        return "text"

    @classmethod
    def get_params_schema(cls) -> list[dict[str, Any]]:
        return schema(EODHD_API_KEY, LIMIT, CACHE_MODE)

    async def scan(self, data: list[Any]) -> list[Security]:
        client = self.eodhd()
        limit = int(self.params.get("limit") or 5)
        results: list[Security] = []

        for phrase in data:
            text = str(getattr(phrase, "text", "") or "").strip()
            if not text:
                continue
            with self.guard(text):
                payload, record = client.search(
                    text, limit=limit, cache_mode=self.cache_mode
                )
                hits = client.parse_search_hits(payload)
                if not hits:
                    continue
                for hit in hits[:limit]:
                    security = self._security_from_hit(hit, record)
                    if security is None:
                        continue
                    results.append(self.stage(security))
                    self.link(phrase, security, "RESOLVES_TO")
                    provisional = self._provisional_for(text)
                    if (
                        provisional is not None
                        and provisional.security_id != security.security_id
                    ):
                        self.link(provisional, security, "SAME_AS")
        return results

    def _security_from_hit(self, hit: dict[str, Any], record: Any) -> Optional[Security]:
        """Build a Security from one search hit, or None when it cannot be keyed."""
        code = hit.get("eodhd_code") or hit.get("code")
        if not code:
            return None
        fields: dict[str, Any] = {
            "name": hit.get("name"),
            "ticker": hit.get("code"),
            "currency": hit.get("currency"),
            **self.provenance_from(
                record,
                method="vendor_parsed",
                locator=f"search hit {code}",
            ),
        }
        # An ISIN is only stored when it passes its check digit; Security raises on a bad
        # one, and one bad vendor row should not cost the whole hit.
        isin = hit.get("isin")
        if isin:
            try:
                return Security.from_eodhd_code(str(code), isin=str(isin), **fields)
            except Exception:  # noqa: BLE001 - keep the hit, drop the bad alias
                pass
        return Security.from_eodhd_code(str(code), **fields)

    @staticmethod
    def _provisional_for(text: str) -> Optional[Security]:
        """The provisional node a UI seed of this text would have created, if any.

        Seeding a `Security` directly with "AAPL" produces `slug:aapl`
        (../docs/03-ontology.md#identity-resolution); linking `SAME_AS` from it means the
        resolved node joins up with whatever the operator already created.
        """
        if is_key(text) and is_authoritative(text):
            return None
        try:
            candidate = Security.model_validate(text)
        except Exception:  # noqa: BLE001 - unresolvable text has no provisional node
            return None
        return None if is_authoritative(candidate.security_id) else candidate
