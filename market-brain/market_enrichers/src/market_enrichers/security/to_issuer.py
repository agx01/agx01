"""Resolve a security to the issuer that files for it."""

from __future__ import annotations

from typing import Any, Optional

from market_types.identifiers import normalize_cik
from market_types.issuer import Issuer
from market_types.security import Security

from .._base import flowsint_enricher
from ..market_enricher import MarketEnricher
from ..params import CACHE_MODE, EODHD_API_KEY, schema


@flowsint_enricher
class SecurityToIssuerEnricher(MarketEnricher):
    """[EODHD] Find the issuer behind a security and key it on its SEC CIK.

    This is the hop that turns a tradable symbol into a filer, which is what every EDGAR
    enricher downstream needs. Only identity and classification are read from the vendor;
    financial values come from EDGAR, which is authoritative
    (../docs/04-data-sources.md#source-precedence).

    An issuer with no CIK still lands, keyed on `lei:` or a `slug:`, with the `slug:`
    flagging that resolution is unfinished rather than pretending it is done.
    """

    InputType = Security
    OutputType = Issuer

    source = "eodhd"

    @classmethod
    def name(cls) -> str:
        return "security_to_issuer"

    @classmethod
    def key(cls) -> str:
        return "security_id"

    @classmethod
    def get_params_schema(cls) -> list[dict[str, Any]]:
        return schema(EODHD_API_KEY, CACHE_MODE)

    async def scan(self, data: list[Any]) -> list[Issuer]:
        client = self.eodhd()
        results: list[Issuer] = []

        for security in data:
            symbol = self._vendor_symbol(security)
            if not symbol:
                self.failures += 1
                continue
            with self.guard(security.security_id):
                payload, record = client.fundamentals(symbol, cache_mode=self.cache_mode)
                identity = client.parse_identity(payload)
                issuer = self._issuer_from_identity(identity, record)
                if issuer is None:
                    continue
                results.append(self.stage(issuer))
                self.link(issuer, security, "ISSUES")
        return results

    @staticmethod
    def _vendor_symbol(security: Any) -> Optional[str]:
        """The symbol EODHD understands, preferring its own code."""
        code = getattr(security, "eodhd_code", None)
        if code:
            return str(code)
        ticker = getattr(security, "ticker", None)
        mic = getattr(security, "mic", None)
        if ticker and mic in {"XNAS", "XNYS", "ARCX", "BATS", "XASE"}:
            # US venues share one EODHD suffix; anything else needs a real mapping,
            # which belongs in a venue table rather than a guess.
            return f"{ticker}.US"
        return str(ticker) if ticker else None

    def _issuer_from_identity(
        self, identity: dict[str, Any], record: Any
    ) -> Optional[Issuer]:
        fields: dict[str, Any] = {
            "name": identity.get("name"),
            "website": identity.get("website"),
            "fiscal_year_end": identity.get("fiscal_year_end"),
            "country_of_incorporation": identity.get("country"),
            **self.provenance_from(record, method="vendor_parsed", locator="General"),
        }
        employees = identity.get("employees")
        if isinstance(employees, (int, float)) and employees >= 0:
            fields["employees"] = int(employees)

        cik = identity.get("cik")
        if cik:
            try:
                return Issuer.from_cik(normalize_cik(cik), **fields)
            except Exception:  # noqa: BLE001 - fall through to a weaker key
                pass
        lei = identity.get("lei")
        if lei:
            try:
                return Issuer.from_lei(str(lei), **fields)
            except Exception:  # noqa: BLE001 - a bad LEI must not lose the issuer
                pass
        name = identity.get("name")
        return Issuer.from_name(str(name), **fields) if name else None
