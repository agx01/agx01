"""The only place this package talks to the outside world.

Per upstream convention, external API access lives outside the enricher. Keeping it here
buys four things every source needs and no enricher should reimplement:

* **Rate limiting**, so SEC fair access is respected by construction rather than by
  remembering (../docs/04-data-sources.md).
* **Caching** with a TTL per data class, which is what makes re-running an enricher cheap
  and therefore routine.
* **Retrieval records**, the raw material for the provenance block
  (../docs/08-provenance-and-trust.md).
* **Payload archiving**, so a parse can be re-audited without re-fetching.

No third-party HTTP dependency: ``Transport`` is a protocol, the default implementation
uses ``urllib``, and tests inject a fake. The clock and sleep function are injectable for
the same reason.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, Protocol

#: TTLs by data class, from the freshness table in ../docs/08-provenance-and-trust.md.
#: ``None`` means immutable: a filed document never changes (a restatement is a new fact).
TTL_IMMUTABLE: Optional[float] = None
TTL_QUARTERLY: float = 120 * 24 * 3600
TTL_PROFILE: float = 90 * 24 * 3600
TTL_SECURITY_META: float = 30 * 24 * 3600
TTL_NEWS: float = 7 * 24 * 3600
TTL_QUOTE: float = 300

CACHE_FRESH = "fresh"
CACHE_PREFER = "prefer_cache"
CACHE_OFFLINE = "offline"


class SourceError(RuntimeError):
    """A fetch failed in a way the caller should attribute to the source."""

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class CacheMiss(SourceError):
    """Offline mode was requested and nothing usable was cached."""


@dataclass(frozen=True)
class RetrievalRecord:
    """What happened on one fetch — the provenance of a payload."""

    source: str
    url: str
    request_hash: str
    retrieved_at: datetime
    status: Optional[int]
    from_cache: bool
    outcome: str  # ok | cached_stale | source_error
    age_seconds: Optional[float] = None

    def is_stale(self) -> bool:
        return self.outcome == "cached_stale"


class Transport(Protocol):
    """Minimal HTTP GET surface, so the network can be swapped out in tests."""

    def get(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]: ...


class UrllibTransport:
    """Default transport. Raises :class:`SourceError` with the status it saw."""

    def get(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return int(response.status), bytes(response.read())
        except urllib.error.HTTPError as exc:  # pragma: no cover - needs a network
            return int(exc.code), bytes(exc.read() or b"")
        except urllib.error.URLError as exc:  # pragma: no cover - needs a network
            raise SourceError(f"transport error for {url}: {exc.reason}") from exc


class RateLimiter:
    """Token bucket. Conservative by default, because the SEC ceiling is published.

    >>> slept: list[float] = []
    >>> limiter = RateLimiter(
    ...     rate_per_second=2, burst=1, clock=lambda: 0.0, sleep=slept.append
    ... )
    >>> limiter.acquire()
    >>> limiter.acquire()        # no tokens left, so it waits
    >>> round(slept[0], 3)
    0.5
    """

    def __init__(
        self,
        rate_per_second: float,
        *,
        burst: int = 1,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._rate = float(rate_per_second)
        self._capacity = float(max(1, burst))
        self._tokens = self._capacity
        self._clock = clock
        self._sleep = sleep
        self._last = clock()

    def acquire(self) -> None:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) / self._rate
            self._sleep(wait)
            self._tokens = 0.0
            self._last = now + wait
        else:
            self._tokens -= 1.0


@dataclass
class CachedPayload:
    body: bytes
    stored_at: float
    status: int


class ResponseCache:
    """On-disk cache keyed by the request hash.

    Writes are best-effort: a cache that cannot be written must not fail a scan.
    """

    def __init__(
        self, directory: Optional[Path], *, clock: Callable[[], float] = time.time
    ) -> None:
        self.directory = Path(directory) if directory else None
        self._clock = clock
        self._memory: dict[str, CachedPayload] = {}

    def _path(self, key: str) -> Optional[Path]:
        return self.directory / f"{key}.json" if self.directory else None

    def get(self, key: str) -> Optional[CachedPayload]:
        if key in self._memory:
            return self._memory[key]
        path = self._path(key)
        if not path or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            payload = CachedPayload(
                body=bytes.fromhex(raw["body"]),
                stored_at=float(raw["stored_at"]),
                status=int(raw.get("status", 200)),
            )
        except (OSError, ValueError, KeyError):
            return None
        self._memory[key] = payload
        return payload

    def put(self, key: str, body: bytes, status: int = 200) -> None:
        payload = CachedPayload(body=body, stored_at=self._clock(), status=status)
        self._memory[key] = payload
        path = self._path(key)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "body": body.hex(),
                        "stored_at": payload.stored_at,
                        "status": status,
                    }
                ),
                encoding="utf-8",
            )
        except OSError:
            pass  # a cache write failure is not a scan failure

    def age(self, payload: CachedPayload) -> float:
        return max(0.0, self._clock() - payload.stored_at)


@dataclass
class SourceClient:
    """Rate-limited, cached, archived JSON fetcher for one source."""

    source: str
    transport: Transport = field(default_factory=UrllibTransport)
    limiter: Optional[RateLimiter] = None
    cache: ResponseCache = field(default_factory=lambda: ResponseCache(None))
    archive_dir: Optional[Path] = None
    default_headers: Mapping[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    max_attempts: int = 3
    backoff_seconds: float = 1.0
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    RETRYABLE_STATUS = (429, 500, 502, 503, 504)

    def request_hash(self, url: str, params: Optional[Mapping[str, Any]] = None) -> str:
        canonical = url
        if params:
            canonical += "?" + urllib.parse.urlencode(sorted(params.items()))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def build_url(self, url: str, params: Optional[Mapping[str, Any]] = None) -> str:
        if not params:
            return url
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        joiner = "&" if "?" in url else "?"
        return f"{url}{joiner}{query}" if query else url

    def get_json(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        ttl: Optional[float] = TTL_QUARTERLY,
        headers: Optional[Mapping[str, str]] = None,
        cache_mode: str = CACHE_PREFER,
    ) -> tuple[Any, RetrievalRecord]:
        """Fetch and decode JSON, returning the payload and its retrieval record."""
        body, record = self.get_bytes(
            url, params=params, ttl=ttl, headers=headers, cache_mode=cache_mode
        )
        try:
            return json.loads(body.decode("utf-8")), record
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceError(
                f"{self.source}: invalid JSON from {record.url}: {exc}"
            ) from exc

    def get_bytes(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        ttl: Optional[float] = TTL_QUARTERLY,
        headers: Optional[Mapping[str, str]] = None,
        cache_mode: str = CACHE_PREFER,
    ) -> tuple[bytes, RetrievalRecord]:
        full_url = self.build_url(url, params)
        key = self.request_hash(url, params)
        cached = self.cache.get(key)

        if cached and cache_mode != CACHE_FRESH:
            age = self.cache.age(cached)
            within_ttl = ttl is None or age <= ttl
            if within_ttl or cache_mode == CACHE_OFFLINE:
                return cached.body, RetrievalRecord(
                    source=self.source,
                    url=full_url,
                    request_hash=key,
                    retrieved_at=self.clock(),
                    status=cached.status,
                    from_cache=True,
                    outcome="ok" if within_ttl else "cached_stale",
                    age_seconds=age,
                )

        if cache_mode == CACHE_OFFLINE:
            raise CacheMiss(
                f"{self.source}: nothing cached for {full_url} in offline mode"
            )

        merged = {**dict(self.default_headers), **dict(headers or {})}
        last_status: Optional[int] = None
        for attempt in range(1, self.max_attempts + 1):
            if self.limiter:
                self.limiter.acquire()
            status, body = self.transport.get(full_url, merged, self.timeout)
            last_status = status
            if 200 <= status < 300:
                self.cache.put(key, body, status)
                self._archive(key, full_url, body)
                return body, RetrievalRecord(
                    source=self.source,
                    url=full_url,
                    request_hash=key,
                    retrieved_at=self.clock(),
                    status=status,
                    from_cache=False,
                    outcome="ok",
                    age_seconds=0.0,
                )
            if status not in self.RETRYABLE_STATUS or attempt == self.max_attempts:
                break
            self.sleep(self.backoff_seconds * (2 ** (attempt - 1)))

        if cached:
            # Serve what we have rather than pretending there is no data, and say so.
            return cached.body, RetrievalRecord(
                source=self.source,
                url=full_url,
                request_hash=key,
                retrieved_at=self.clock(),
                status=last_status,
                from_cache=True,
                outcome="cached_stale",
                age_seconds=self.cache.age(cached),
            )
        raise SourceError(
            f"{self.source}: GET {full_url} failed with status {last_status}",
            status=last_status,
        )

    def _archive(self, key: str, url: str, body: bytes) -> None:
        if not self.archive_dir:
            return
        try:
            directory = Path(self.archive_dir)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{key}.bin").write_bytes(body)
            (directory / f"{key}.meta.json").write_text(
                json.dumps({"url": url, "source": self.source, "bytes": len(body)}),
                encoding="utf-8",
            )
        except OSError:
            pass  # archiving is an audit aid, not a correctness requirement
