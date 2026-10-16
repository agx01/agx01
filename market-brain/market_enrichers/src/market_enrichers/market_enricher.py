"""Shared base class for every enricher in this package.

It exists because upstream's ``Enricher`` leaves four things to each author, and getting
any of them wrong is silent:

1. **``execute()`` swallows exceptions and returns ``[]``** (verified in
   ``flowsint-core/.../enricher_base.py``), so "the source is down" and "there is nothing
   to find" look identical. :meth:`guard` logs every skipped item and counts failures,
   and the run logs a summary.
2. **Provenance** has to land on every node. :meth:`provenance_from` turns a
   :class:`~market_enrichers.tools.http.RetrievalRecord` into the block from
   ../docs/08-provenance-and-trust.md, including a ``fetch_outcome`` that distinguishes a
   stale cache from a fresh fetch.
3. **Graph writes belong in ``postprocess``**, after ``scan`` returns. :meth:`stage` and
   :meth:`link` buffer nodes and edges during the scan; :meth:`postprocess` writes them,
   de-duplicated by merge key.
4. **Clients** need rate limiting, caching and a vault-held credential. :meth:`edgar` and
   :meth:`eodhd` build them from params, so no enricher reaches for a key itself.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, Optional, TypeVar

from market_types.provenance import Method, Source, provenance
from pydantic import BaseModel

from ._base import Enricher, Logger
from .tools.edgar import DEFAULT_RATE_PER_SECOND as EDGAR_RATE
from .tools.edgar import EdgarClient
from .tools.eodhd import DEFAULT_RATE_PER_SECOND as EODHD_RATE
from .tools.eodhd import EodhdClient
from .tools.http import RateLimiter, ResponseCache, RetrievalRecord, SourceClient

#: Where cached payloads and archived responses go. Paths only — never secrets
#: (../docs/09-security-and-secrets.md).
#: Any Pydantic node type, so stage() hands back exactly what it was given.
NodeT = TypeVar("NodeT", bound=BaseModel)

CACHE_DIR_ENV = "MARKET_BRAIN_CACHE_DIR"
ARCHIVE_DIR_ENV = "MARKET_BRAIN_ARCHIVE_DIR"


def _dir_from_env(variable: str) -> Optional[Path]:
    raw = os.environ.get(variable)
    return Path(raw).expanduser() if raw else None


class MarketEnricher(Enricher):
    """Base for market enrichers: provenance, per-item safety, buffered graph writes."""

    #: Provenance ``source`` for nodes this enricher writes.
    source: ClassVar[Source] = "derived"
    #: UI grouping. Upstream's casing is inconsistent; ours is uniform.
    ui_category: ClassVar[str] = "Market"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._staged: list[BaseModel] = []
        self._staged_keys: set[tuple[str, str]] = set()
        self._edges: list[tuple[BaseModel, BaseModel, str]] = []
        self.failures: int = 0
        self.stale_reads: int = 0

    # --- upstream metadata -----------------------------------------------------------

    @classmethod
    def category(cls) -> str:
        return cls.ui_category

    @classmethod
    def documentation(cls) -> str:
        """The class docstring, cleaned.

        Upstream's registry calls ``inspect.cleandoc(enricher.documentation())`` when it
        lists enrichers, so this must return a string — ``None`` would break the listing
        endpoint for every enricher, not just this one.
        """
        return inspect.cleandoc(cls.__doc__ or "")

    # --- per-item safety -------------------------------------------------------------

    @contextmanager
    def guard(self, what: str) -> Iterator[None]:
        """Run a block, logging and counting a failure instead of losing the batch.

        >>> # pseudo-usage inside scan():
        >>> # for issuer in data:
        >>> #     with self.guard(issuer.issuer_id):
        >>> #         ...
        """
        try:
            yield
        except Exception as exc:  # noqa: BLE001 - deliberate: one bad item, not the run
            self.failures += 1
            Logger.error(
                self.sketch_id,
                {"message": f"{self.name()}: {what}: {type(exc).__name__}: {exc}"},
            )

    # --- provenance ------------------------------------------------------------------

    def provenance_from(
        self,
        record: RetrievalRecord,
        *,
        method: Method = "reported",
        locator: Optional[str] = None,
        confidence: Optional[float] = None,
        as_of: Optional[date] = None,
        source: Optional[Source] = None,
        rule: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build the provenance block for a node from the fetch that produced it."""
        if record.is_stale():
            self.stale_reads += 1
        return provenance(
            source or self.source,
            source_ref=record.url,
            locator=locator,
            retrieved_at=record.retrieved_at,
            as_of=as_of,
            method=method,
            confidence=confidence,
            scan_id=self.scan_id,
            rule=rule,
            fetch_outcome="cached_stale" if record.is_stale() else "ok",
        )

    # --- buffered graph writes -------------------------------------------------------

    @staticmethod
    def _merge_key(node: BaseModel) -> tuple[str, str]:
        """``(type name, primary value)`` — the identity Neo4j will merge on."""
        for name, field in type(node).model_fields.items():
            extra = field.json_schema_extra
            if extra and isinstance(extra, dict) and extra.get("primary"):
                return type(node).__name__, str(getattr(node, name))
        return type(node).__name__, repr(node)

    def stage(self, node: NodeT) -> NodeT:
        """Buffer a node for writing, de-duplicated by merge key."""
        key = self._merge_key(node)
        if key not in self._staged_keys:
            self._staged_keys.add(key)
            self._staged.append(node)
        return node

    def link(self, source_node: BaseModel, target_node: BaseModel, label: str) -> None:
        """Buffer an edge.

        Labels are UPPER_SNAKE_CASE verbs from ../docs/03-ontology.md.
        """
        if not label or label != label.upper():
            raise ValueError(
                f"relationship label must be UPPER_SNAKE_CASE, got {label!r}"
            )
        self._edges.append((source_node, target_node, label))

    def postprocess(
        self, results: list[Any], input_data: Optional[list[Any]] = None
    ) -> list[Any]:
        """Write the buffered nodes and edges, then report what happened."""
        if not self._graph_service:
            return results
        for node in self._staged:
            self.create_node(node)
        for source_node, target_node, label in self._edges:
            self.create_node(source_node)
            self.create_node(target_node)
            self.create_relationship(source_node, target_node, label)
        self.log_graph_message(
            f"{self.name()}: {len(self._staged)} nodes, {len(self._edges)} relationships"
        )
        if self.failures:
            Logger.warn(
                self.sketch_id,
                {
                    "message": (
                        f"{self.name()}: {self.failures} input(s) skipped after errors"
                    )
                },
            )
        if self.stale_reads:
            Logger.warn(
                self.sketch_id,
                {
                    "message": (
                        f"{self.name()}: {self.stale_reads} value(s) served from a stale "
                        "cache and marked fetch_outcome=cached_stale"
                    )
                },
            )
        if not results and not self.failures:
            # Distinguish "nothing to find" from "the enricher broke", which
            # Enricher.execute() otherwise renders identical (both are []).
            Logger.info(
                self.sketch_id,
                {"message": f"{self.name()}: completed with no results and no errors"},
            )
        return results

    # --- clients ---------------------------------------------------------------------

    @property
    def cache_mode(self) -> str:
        return str(self.params.get("cache_mode") or "prefer_cache")

    def source_client(self, source: str, *, rate_per_second: float) -> SourceClient:
        cache_root = _dir_from_env(CACHE_DIR_ENV)
        archive_root = _dir_from_env(ARCHIVE_DIR_ENV)
        return SourceClient(
            source=source,
            limiter=RateLimiter(rate_per_second),
            cache=ResponseCache(cache_root / source if cache_root else None),
            archive_dir=archive_root / source if archive_root else None,
        )

    def edgar(self) -> EdgarClient:
        """An EDGAR client with the declared User-Agent from the vault."""
        return EdgarClient(
            self.get_secret("SEC_USER_AGENT"),
            self.source_client("sec_edgar", rate_per_second=EDGAR_RATE),
        )

    def eodhd(self) -> EodhdClient:
        """An EODHD client with the API token from the vault."""
        return EodhdClient(
            self.get_secret("EODHD_API_KEY"),
            self.source_client("eodhd", rate_per_second=EODHD_RATE),
        )
