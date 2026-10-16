"""The fetch layer: rate limiting, caching, retries, retrieval records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import FakeTransport
from market_enrichers.tools.http import (
    CACHE_FRESH,
    CACHE_OFFLINE,
    CACHE_PREFER,
    CacheMiss,
    RateLimiter,
    ResponseCache,
    SourceClient,
    SourceError,
)

PAYLOAD = json.dumps({"ok": True}).encode()


def client(transport: Any, **kwargs: Any) -> SourceClient:
    return SourceClient(
        source="test", transport=transport, sleep=lambda _: None, **kwargs
    )


class TestRateLimiter:
    def test_burst_then_wait(self) -> None:
        slept: list[float] = []
        limiter = RateLimiter(
            rate_per_second=4, burst=2, clock=lambda: 0.0, sleep=slept.append
        )
        limiter.acquire()
        limiter.acquire()
        assert slept == []
        limiter.acquire()
        assert slept and pytest.approx(slept[0], abs=1e-6) == 0.25

    def test_tokens_refill_as_time_passes(self) -> None:
        now = [0.0]
        slept: list[float] = []
        limiter = RateLimiter(
            rate_per_second=2, burst=1, clock=lambda: now[0], sleep=slept.append
        )
        limiter.acquire()
        now[0] = 10.0
        limiter.acquire()
        assert slept == []

    def test_rate_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            RateLimiter(0)


class TestCaching:
    def test_second_call_is_served_from_cache(self) -> None:
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport)
        first = source.get_json("https://example.com/a")
        second = source.get_json("https://example.com/a")
        assert len(transport.requests) == 1
        assert first[1].from_cache is False
        assert second[1].from_cache is True
        assert second[1].outcome == "ok"

    def test_fresh_mode_bypasses_the_cache(self) -> None:
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport)
        source.get_json("https://example.com/a")
        source.get_json("https://example.com/a", cache_mode=CACHE_FRESH)
        assert len(transport.requests) == 2

    def test_expired_entry_is_refetched(self) -> None:
        now = [1000.0]
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport, cache=ResponseCache(None, clock=lambda: now[0]))
        source.get_json("https://example.com/a", ttl=10)
        now[0] += 60
        _, record = source.get_json("https://example.com/a", ttl=10)
        assert len(transport.requests) == 2
        assert record.from_cache is False

    def test_offline_serves_stale_and_says_so(self) -> None:
        now = [1000.0]
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport, cache=ResponseCache(None, clock=lambda: now[0]))
        source.get_json("https://example.com/a", ttl=10)
        now[0] += 600
        _, record = source.get_json(
            "https://example.com/a", ttl=10, cache_mode=CACHE_OFFLINE
        )
        assert len(transport.requests) == 1
        assert record.outcome == "cached_stale"
        assert record.is_stale()

    def test_offline_with_nothing_cached_raises(self) -> None:
        source = client(FakeTransport())
        with pytest.raises(CacheMiss):
            source.get_json("https://example.com/missing", cache_mode=CACHE_OFFLINE)

    def test_immutable_ttl_never_expires(self) -> None:
        now = [0.0]
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport, cache=ResponseCache(None, clock=lambda: now[0]))
        source.get_bytes("https://example.com/doc", ttl=None)
        now[0] += 10**9
        _, record = source.get_bytes("https://example.com/doc", ttl=None)
        assert record.from_cache is True and record.outcome == "ok"

    def test_cache_survives_a_new_client_on_disk(self, tmp_path: Path) -> None:
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        first = client(transport, cache=ResponseCache(tmp_path))
        first.get_json("https://example.com/a")
        second = client(transport, cache=ResponseCache(tmp_path))
        _, record = second.get_json("https://example.com/a")
        assert record.from_cache is True
        assert len(transport.requests) == 1

    def test_request_hash_is_stable_and_param_sensitive(self) -> None:
        source = client(FakeTransport())
        a = source.request_hash("https://example.com/a", {"x": 1, "y": 2})
        b = source.request_hash("https://example.com/a", {"y": 2, "x": 1})
        c = source.request_hash("https://example.com/a", {"x": 2, "y": 2})
        assert a == b != c


class TestRetriesAndFailures:
    def test_retries_then_succeeds(self) -> None:
        responses = [(503, b""), (200, PAYLOAD)]
        calls: list[str] = []

        class FlakyTransport:
            def get(self, url: str, headers: Any, timeout: float) -> tuple[int, bytes]:
                calls.append(url)
                return responses[min(len(calls) - 1, len(responses) - 1)]

        payload, record = client(FlakyTransport()).get_json("https://example.com/a")
        assert payload == {"ok": True}
        assert len(calls) == 2
        assert record.outcome == "ok"

    def test_gives_up_and_raises_with_the_status(self) -> None:
        transport = FakeTransport(default=(500, b""))
        with pytest.raises(SourceError) as excinfo:
            client(transport).get_json("https://example.com/a")
        assert excinfo.value.status == 500
        assert len(transport.requests) == 3  # max_attempts

    def test_non_retryable_status_fails_immediately(self) -> None:
        transport = FakeTransport(default=(404, b""))
        with pytest.raises(SourceError):
            client(transport).get_json("https://example.com/a")
        assert len(transport.requests) == 1

    def test_falls_back_to_stale_cache_when_the_source_breaks(self) -> None:
        now = [0.0]
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport, cache=ResponseCache(None, clock=lambda: now[0]))
        source.get_json("https://example.com/a", ttl=10)
        now[0] += 100
        transport.routes = {}
        transport.default = (500, b"")
        payload, record = source.get_json("https://example.com/a", ttl=10)
        assert payload == {"ok": True}
        assert record.outcome == "cached_stale"

    def test_invalid_json_is_a_source_error(self) -> None:
        transport = FakeTransport(default=(200, b"<html>nope</html>"))
        with pytest.raises(SourceError):
            client(transport).get_json("https://example.com/a")


class TestArchiving:
    def test_payload_and_metadata_are_archived(self, tmp_path: Path) -> None:
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport, archive_dir=tmp_path)
        source.get_json("https://example.com/a")
        archived = sorted(p.name for p in tmp_path.iterdir())
        assert len(archived) == 2
        meta = json.loads(next(p for p in tmp_path.glob("*.meta.json")).read_text())
        assert meta["url"] == "https://example.com/a"
        assert meta["source"] == "test"

    def test_an_unwritable_cache_does_not_fail_a_scan(self, tmp_path: Path) -> None:
        blocked = tmp_path / "file-not-a-dir"
        blocked.write_text("x")
        transport = FakeTransport(routes={"example.com": (200, PAYLOAD)})
        source = client(transport, cache=ResponseCache(blocked / "sub"))
        payload, record = source.get_json(
            "https://example.com/a", cache_mode=CACHE_PREFER
        )
        assert payload == {"ok": True}
        assert record.outcome == "ok"
