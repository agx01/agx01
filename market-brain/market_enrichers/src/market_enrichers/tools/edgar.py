"""SEC EDGAR client and parsers.

**Payload shapes are unverified from the authoring environment.** `sec.gov` is denied by
this container's egress policy (`CONNECT tunnel failed, response 403` —
../docs/12-environment-notes.md), so the JSON and XML structures below come from prior
knowledge of EDGAR, not from a fetched sample. Every parser is written defensively and
tested against synthetic fixtures; **validate against a real payload from your
workstation before trusting the output** (../docs/references.md, S1–S5).

Two rules this client enforces rather than documents:

* A **declared User-Agent** naming the requester with a contact address. SEC fair access
  requires it, and the client refuses to run without one.
* A **conservative rate limit** below the published ceiling, applied centrally.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from market_types.identifiers import normalize_accession, normalize_cik

from .http import (
    TTL_IMMUTABLE,
    TTL_PROFILE,
    TTL_QUARTERLY,
    RetrievalRecord,
    SourceClient,
    SourceError,
)

DATA_BASE = "https://data.sec.gov"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

#: Below the published fair-access ceiling, on purpose.
DEFAULT_RATE_PER_SECOND = 5.0

_CONTACT_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_10B5_1_RE = re.compile(r"10b5[\s\-–]?1", re.IGNORECASE)


class EdgarError(SourceError):
    """An EDGAR request or payload could not be used."""


@dataclass(frozen=True)
class Form4Transaction:
    """One non-derivative transaction line of a Form 4."""

    line_number: int
    transaction_date: Optional[date]
    transaction_code: Optional[str]
    acquired_disposed: Optional[str]
    security_title: Optional[str]
    shares: Optional[float]
    price_per_share: Optional[float]
    shares_owned_after: Optional[float]
    ownership_type: Optional[str]
    is_10b5_1: Optional[bool]
    footnotes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Form4:
    """A parsed Form 4: who reported, about which issuer, and what they did."""

    issuer_cik: Optional[str]
    issuer_name: Optional[str]
    issuer_symbol: Optional[str]
    owner_cik: Optional[str]
    owner_name: Optional[str]
    is_director: Optional[bool]
    is_officer: Optional[bool]
    is_ten_percent_owner: Optional[bool]
    officer_title: Optional[str]
    period_of_report: Optional[date]
    transactions: tuple[Form4Transaction, ...] = field(default_factory=tuple)


def _text(node: Optional[ElementTree.Element]) -> Optional[str]:
    """Element text, or the text of its ``<value>`` child, stripped."""
    if node is None:
        return None
    value = node.find("value")
    raw = value.text if value is not None else node.text
    return raw.strip() if raw and raw.strip() else None


def _float(node: Optional[ElementTree.Element]) -> Optional[float]:
    raw = _text(node)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _bool(node: Optional[ElementTree.Element]) -> Optional[bool]:
    raw = _text(node)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes"}


def _date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


class EdgarClient:
    """Thin, rate-limited client over the EDGAR submissions and XBRL APIs."""

    def __init__(self, user_agent: Optional[str], client: SourceClient) -> None:
        if not user_agent or not _CONTACT_RE.search(user_agent):
            raise EdgarError(
                "SEC fair access requires a declared User-Agent containing a contact "
                "email, e.g. 'market-brain you@example.com'. Set the SEC_USER_AGENT "
                "vault secret (../docs/09-security-and-secrets.md)."
            )
        self.user_agent = user_agent
        self.client = client

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }

    # --- endpoints -------------------------------------------------------------------

    def submissions(
        self, cik: str | int, *, cache_mode: str = "prefer_cache"
    ) -> tuple[Any, RetrievalRecord]:
        """Filing history for one filer."""
        padded = normalize_cik(cik)
        return self.client.get_json(
            f"{DATA_BASE}/submissions/CIK{padded}.json",
            ttl=TTL_PROFILE,
            headers=self.headers,
            cache_mode=cache_mode,
        )

    def company_facts(
        self, cik: str | int, *, cache_mode: str = "prefer_cache"
    ) -> tuple[Any, RetrievalRecord]:
        """Every XBRL fact for one filer."""
        padded = normalize_cik(cik)
        return self.client.get_json(
            f"{DATA_BASE}/api/xbrl/companyfacts/CIK{padded}.json",
            ttl=TTL_QUARTERLY,
            headers=self.headers,
            cache_mode=cache_mode,
        )

    def company_concept(
        self,
        cik: str | int,
        tag: str,
        *,
        taxonomy: str = "us-gaap",
        cache_mode: str = "prefer_cache",
    ) -> tuple[Any, RetrievalRecord]:
        """One concept's full history for one filer."""
        padded = normalize_cik(cik)
        return self.client.get_json(
            f"{DATA_BASE}/api/xbrl/companyconcept/CIK{padded}/{taxonomy}/{tag}.json",
            ttl=TTL_QUARTERLY,
            headers=self.headers,
            cache_mode=cache_mode,
        )

    def filing_document(
        self,
        cik: str | int,
        accession: str,
        filename: str,
        *,
        cache_mode: str = "prefer_cache",
    ) -> tuple[bytes, RetrievalRecord]:
        """One document from a filing's archive directory.

        Filed documents are immutable, so they are cached forever.
        """
        compact = normalize_accession(accession).replace("-", "")
        url = f"{ARCHIVES_BASE}/{int(normalize_cik(cik))}/{compact}/{filename}"
        return self.client.get_bytes(
            url,
            ttl=TTL_IMMUTABLE,
            headers={**self.headers, "Accept": "*/*"},
            cache_mode=cache_mode,
        )

    @staticmethod
    def index_url(cik: str | int, accession: str) -> str:
        dashed = normalize_accession(accession)
        compact = dashed.replace("-", "")
        return f"{ARCHIVES_BASE}/{int(normalize_cik(cik))}/{compact}/{dashed}-index.htm"

    @staticmethod
    def document_url(cik: str | int, accession: str, filename: str) -> str:
        compact = normalize_accession(accession).replace("-", "")
        return f"{ARCHIVES_BASE}/{int(normalize_cik(cik))}/{compact}/{filename}"

    # --- parsers ---------------------------------------------------------------------

    @staticmethod
    def iter_filings(
        payload: Any,
        *,
        forms: Optional[Sequence[str]] = None,
        since: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield filings from a submissions payload, newest first.

        ``filings.recent`` is **parallel arrays**, not a list of objects, so a short array
        silently truncates a row unless the zip is length-checked — which is why this
        iterates by index and skips rows missing an accession number.
        """
        if not isinstance(payload, dict):
            raise EdgarError("submissions payload is not an object")
        cik = payload.get("cik")
        recent = (payload.get("filings") or {}).get("recent") or {}
        accessions = recent.get("accessionNumber") or []
        wanted = {f.strip().upper() for f in forms} if forms else None
        emitted = 0

        def column(name: str, index: int) -> Any:
            values = recent.get(name) or []
            return values[index] if index < len(values) else None

        for index in range(len(accessions)):
            raw_accession = accessions[index]
            if not raw_accession:
                continue
            form = (column("form", index) or "").strip().upper()
            if wanted and form not in wanted and form.removesuffix("/A") not in wanted:
                continue
            filed_at = _date(column("filingDate", index))
            if since and (filed_at is None or filed_at < since):
                continue
            try:
                accession = normalize_accession(raw_accession)
            except ValueError:
                continue
            primary_document = column("primaryDocument", index)
            items = column("items", index) or ""
            yield {
                "accession": accession,
                "cik": normalize_cik(cik) if cik else None,
                "form": form or None,
                "filing_date": filed_at,
                "report_date": _date(column("reportDate", index)),
                "primary_document": primary_document,
                "items": [i.strip() for i in str(items).split(",") if i.strip()],
                "index_url": EdgarClient.index_url(cik, accession) if cik else None,
                "primary_doc_url": (
                    EdgarClient.document_url(cik, accession, primary_document)
                    if cik and primary_document
                    else None
                ),
            }
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    @staticmethod
    def former_names(payload: Any) -> list[str]:
        """Prior names from a submissions payload — ticker changes are real."""
        if not isinstance(payload, dict):
            return []
        names = []
        for entry in payload.get("formerNames") or []:
            name = (entry or {}).get("name") if isinstance(entry, dict) else None
            if name:
                names.append(str(name))
        return names

    @staticmethod
    def iter_facts(
        payload: Any,
        *,
        tags: Optional[Sequence[str]] = None,
        taxonomies: Sequence[str] = ("us-gaap", "ifrs-full"),
        limit_per_tag: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield individual XBRL observations from a companyfacts payload.

        One row per (tag, unit, period, accession) so restatements stay addressable
        instead of overwriting each other (../docs/08-provenance-and-trust.md).
        """
        if not isinstance(payload, dict):
            raise EdgarError("companyfacts payload is not an object")
        cik = payload.get("cik")
        facts = payload.get("facts") or {}
        wanted = {t.strip() for t in tags} if tags else None

        for taxonomy in taxonomies:
            concepts = facts.get(taxonomy) or {}
            for tag, concept in concepts.items():
                if wanted and tag not in wanted:
                    continue
                emitted = 0
                for unit, observations in (concept.get("units") or {}).items():
                    for observation in observations or []:
                        if not isinstance(observation, dict):
                            continue
                        value = observation.get("val")
                        if value is None:
                            continue
                        end = _date(observation.get("end"))
                        start = _date(observation.get("start"))
                        fiscal_year = observation.get("fy")
                        fiscal_period = observation.get("fp")
                        period = (
                            f"{fiscal_period}{fiscal_year}"
                            if fiscal_period and fiscal_year
                            else (
                                observation.get("frame")
                                or (end.isoformat() if end else None)
                            )
                        )
                        if not period:
                            continue
                        yield {
                            "cik": normalize_cik(cik) if cik else None,
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "label": concept.get("label"),
                            "unit": unit,
                            "value": float(value),
                            "period": str(period),
                            "period_start": start,
                            "period_end": end,
                            "instant": end if start is None else None,
                            "fiscal_year": int(fiscal_year) if fiscal_year else None,
                            "fiscal_period": str(fiscal_period)
                            if fiscal_period
                            else None,
                            "form": observation.get("form"),
                            "frame": observation.get("frame"),
                            "accession": (
                                normalize_accession(observation["accn"])
                                if observation.get("accn")
                                else None
                            ),
                        }
                        emitted += 1
                        if limit_per_tag is not None and emitted >= limit_per_tag:
                            break
                    if limit_per_tag is not None and emitted >= limit_per_tag:
                        break

    @staticmethod
    def parse_form4(xml_bytes: bytes) -> Form4:
        """Parse a Form 4 ownership document into typed rows.

        Only non-derivative transactions are read; derivative tables (option grants and
        exercises) are a separate shape and belong to a later phase.

        The ``10b5-1`` flag is taken from the ``aff10b5One`` element where present, and
        otherwise **inferred from footnote text**, which is a heuristic — older filings
        disclose the plan in prose. A false negative reads a scheduled sale as a
        discretionary one, so the flag is reported as ``None`` when nothing says either
        way rather than defaulting to ``False``.
        """
        try:
            root = ElementTree.fromstring(xml_bytes)
        except ElementTree.ParseError as exc:
            raise EdgarError(f"Form 4 XML did not parse: {exc}") from exc

        footnotes = {
            (node.get("id") or ""): (node.text or "").strip()
            for node in root.findall(".//footnotes/footnote")
        }
        document_10b5_1 = _bool(root.find(".//aff10b5One"))

        issuer = root.find("issuer")
        owner = root.find("reportingOwner")
        owner_id = owner.find("reportingOwnerId") if owner is not None else None
        relationship = (
            owner.find("reportingOwnerRelationship") if owner is not None else None
        )

        transactions: list[Form4Transaction] = []
        for index, node in enumerate(
            root.findall(".//nonDerivativeTransaction"), start=1
        ):
            amounts = node.find("transactionAmounts")
            post = node.find("postTransactionAmounts")
            coding = node.find("transactionCoding")
            note_ids = [
                ref.get("id") or ""
                for ref in node.findall(".//footnoteId")
                if ref.get("id")
            ]
            notes = tuple(footnotes.get(note_id, "") for note_id in note_ids if note_id)
            planned = document_10b5_1
            if planned is None and notes:
                planned = any(_10B5_1_RE.search(note) for note in notes) or None
            transactions.append(
                Form4Transaction(
                    line_number=index,
                    transaction_date=_date(_text(node.find("transactionDate"))),
                    transaction_code=_text(
                        coding.find("transactionCode") if coding is not None else None
                    ),
                    acquired_disposed=_text(
                        amounts.find("transactionAcquiredDisposedCode")
                        if amounts is not None
                        else None
                    ),
                    security_title=_text(node.find("securityTitle")),
                    shares=_float(
                        amounts.find("transactionShares") if amounts is not None else None
                    ),
                    price_per_share=_float(
                        amounts.find("transactionPricePerShare")
                        if amounts is not None
                        else None
                    ),
                    shares_owned_after=_float(
                        post.find("sharesOwnedFollowingTransaction")
                        if post is not None
                        else None
                    ),
                    ownership_type=(
                        "indirect"
                        if (
                            _text(node.find(".//directOrIndirectOwnership")) or "D"
                        ).upper()
                        == "I"
                        else "direct"
                    ),
                    is_10b5_1=planned,
                    footnotes=notes,
                )
            )

        return Form4(
            issuer_cik=(
                normalize_cik(_text(issuer.find("issuerCik")) or "")
                if issuer is not None and _text(issuer.find("issuerCik"))
                else None
            ),
            issuer_name=_text(issuer.find("issuerName")) if issuer is not None else None,
            issuer_symbol=(
                _text(issuer.find("issuerTradingSymbol")) if issuer is not None else None
            ),
            owner_cik=(
                normalize_cik(_text(owner_id.find("rptOwnerCik")) or "")
                if owner_id is not None and _text(owner_id.find("rptOwnerCik"))
                else None
            ),
            owner_name=(
                _text(owner_id.find("rptOwnerName")) if owner_id is not None else None
            ),
            is_director=_bool(
                relationship.find("isDirector") if relationship is not None else None
            ),
            is_officer=_bool(
                relationship.find("isOfficer") if relationship is not None else None
            ),
            is_ten_percent_owner=_bool(
                relationship.find("isTenPercentOwner")
                if relationship is not None
                else None
            ),
            officer_title=_text(
                relationship.find("officerTitle") if relationship is not None else None
            ),
            period_of_report=_date(_text(root.find("periodOfReport"))),
            transactions=tuple(transactions),
        )
