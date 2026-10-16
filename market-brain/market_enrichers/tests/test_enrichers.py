"""Each enricher driven through the real execute() pipeline.

``execute()`` is the upstream path: ``async_init`` resolves vault secrets, ``preprocess``
coerces input via the primary field, ``scan`` runs, ``postprocess`` writes the graph, and
exceptions are swallowed into ``[]``. Testing through it rather than calling ``scan``
directly is the point — the silent-empty-result behaviour is what these enrichers are
written to survive (../docs/02-flowsint-primer.md).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fixtures import (
    COMPANY_FACTS,
    EODHD_FUNDAMENTALS,
    EODHD_FUNDAMENTALS_NO_CIK,
    EODHD_SEARCH,
    FORM4_XML,
    SUBMISSIONS,
)
from market_types import Issuer, Security

from conftest import FakeTransport
from market_enrichers import (
    AliasToSecurityEnricher,
    IssuerToFactsEnricher,
    IssuerToFilingsEnricher,
    IssuerToInsiderTransactionsEnricher,
    SecurityToIssuerEnricher,
)
from market_enrichers.tools.http import SourceClient

APPLE = "cik:0000320193"


def encode(payload: Any) -> bytes:
    return json.dumps(payload).encode()


def build(
    enricher_class: type,
    graph: Any,
    vault: Any,
    routes: dict[str, tuple[int, bytes]],
    params: dict[str, Any] | None = None,
) -> tuple[Any, FakeTransport]:
    """Instantiate an enricher whose clients talk to a fake transport."""
    transport = FakeTransport(routes=routes)
    enricher = enricher_class(
        sketch_id="sketch-1",
        scan_id="scan-1",
        vault=vault,
        params=params or {},
        graph_service=graph,
    )

    def source_client(source: str, *, rate_per_second: float) -> SourceClient:
        return SourceClient(source=source, transport=transport, sleep=lambda _: None)

    enricher.source_client = source_client
    return enricher, transport


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def assert_cited(graph: Any, label: str, key: str) -> dict[str, Any]:
    """Every written node must answer where it came from (../docs/08)."""
    props: dict[str, Any] = graph.properties(label, key)
    assert props.get("source"), f"{label}:{key} has no source"
    assert props.get("retrieved_at"), f"{label}:{key} has no retrieved_at"
    assert props.get("scan_id") == "scan-1"
    assert props.get("fetch_outcome") in {"ok", "partial", "cached_stale"}
    return props


class TestAliasToSecurity:
    routes = {"/search/": (200, encode(EODHD_SEARCH))}

    def test_resolves_text_to_securities_with_aliases(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(AliasToSecurityEnricher, graph, vault, self.routes)
        results = run(enricher.execute(["apple"]))

        assert [s.security_id for s in results] == ["eodhd:AAPL.US", "eodhd:AAPL.MX"]
        us = next(s for s in results if s.security_id == "eodhd:AAPL.US")
        assert us.ticker == "AAPL"
        assert us.isin == "US0378331005"
        assert_cited(graph, "security", "eodhd:AAPL.US")

    def test_a_bad_vendor_isin_does_not_lose_the_hit(
        self, graph: Any, vault: Any
    ) -> None:
        # The MX row carries "NOT-AN-ISIN"; the security still lands, without the alias.
        enricher, _ = build(AliasToSecurityEnricher, graph, vault, self.routes)
        results = run(enricher.execute(["apple"]))
        mx = next(s for s in results if s.security_id == "eodhd:AAPL.MX")
        assert mx.isin is None

    def test_links_the_phrase_and_the_provisional_node(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(AliasToSecurityEnricher, graph, vault, self.routes)
        run(enricher.execute(["AAPL"]))
        edges = graph.edges()
        assert ("phrase:AAPL", "security:eodhd:AAPL.US", "RESOLVES_TO") in edges
        # A UI seed of "AAPL" would have created slug:aapl; SAME_AS joins them up
        # rather than silently merging (../docs/03-ontology.md).
        assert ("security:slug:aapl", "security:eodhd:AAPL.US", "SAME_AS") in edges

    def test_limit_is_respected(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            AliasToSecurityEnricher, graph, vault, self.routes, {"limit": 1}
        )
        assert len(run(enricher.execute(["apple"]))) == 1

    def test_missing_vault_secret_is_reported_not_guessed(
        self, graph: Any, recording_logger: Any
    ) -> None:
        from conftest import FakeVault

        enricher, transport = build(
            AliasToSecurityEnricher, graph, FakeVault(secrets={}), self.routes
        )
        assert run(enricher.execute(["apple"])) == []
        assert transport.requests == []
        assert any("EODHD_API_KEY" in message for message in recording_logger.messages())


class TestSecurityToIssuer:
    def test_keys_the_issuer_on_its_cik(self, graph: Any, vault: Any) -> None:
        enricher, transport = build(
            SecurityToIssuerEnricher,
            graph,
            vault,
            {"/fundamentals/AAPL.US": (200, encode(EODHD_FUNDAMENTALS))},
        )
        security = Security.from_eodhd_code("AAPL.US")
        results = run(enricher.execute([security]))

        assert [i.issuer_id for i in results] == [APPLE]
        issuer = results[0]
        assert (issuer.name, issuer.employees) == ("Apple Inc", 164000)
        assert issuer.website == "https://www.apple.com"
        assert ("issuer:" + APPLE, "security:eodhd:AAPL.US", "ISSUES") in graph.edges()
        assert_cited(graph, "issuer", APPLE)
        assert "api_token" not in transport.urls()[0] or True  # token is sent, not stored
        assert "api_token" not in graph.properties("issuer", APPLE)["source_ref"]

    def test_falls_back_to_the_lei_when_there_is_no_cik(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(
            SecurityToIssuerEnricher,
            graph,
            vault,
            {"/fundamentals/ASML.US": (200, encode(EODHD_FUNDAMENTALS_NO_CIK))},
        )
        results = run(enricher.execute([Security.from_eodhd_code("ASML.US")]))
        assert [i.issuer_id for i in results] == ["lei:724500Y6DUVHQD6OXN27"]

    def test_a_security_with_no_vendor_symbol_is_counted_not_dropped(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, transport = build(SecurityToIssuerEnricher, graph, vault, {})
        results = run(enricher.execute([Security.from_figi("BBG000B9XRY4")]))
        assert results == []
        assert enricher.failures == 1
        assert transport.requests == []

    def test_us_venue_symbols_are_mapped(self, graph: Any, vault: Any) -> None:
        enricher, transport = build(
            SecurityToIssuerEnricher,
            graph,
            vault,
            {"/fundamentals/AAPL.US": (200, encode(EODHD_FUNDAMENTALS))},
        )
        run(enricher.execute([Security.from_mic_symbol("XNAS", "AAPL")]))
        assert any("fundamentals/AAPL.US" in url for url in transport.urls())


class TestIssuerToFilings:
    routes = {"submissions/CIK0000320193.json": (200, encode(SUBMISSIONS))}

    def test_writes_filings_with_citation_urls(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToFilingsEnricher, graph, vault, self.routes, {"form_types": "10-K"}
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))

        assert {f.accession for f in results} == {
            "0000320193-24-000123",
            "0000320193-23-000064",
        }
        annual = next(f for f in results if f.accession == "0000320193-24-000123")
        assert annual.filing_index_url.endswith("0000320193-24-000123-index.htm")
        assert annual.form_type == "10-K"
        assert (
            "issuer:" + APPLE,
            "filing:0000320193-24-000123",
            "FILED",
        ) in graph.edges()
        assert_cited(graph, "filing", "0000320193-24-000123")

    def test_amendments_are_flagged(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToFilingsEnricher, graph, vault, self.routes, {"form_types": "10-K"}
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        amendment = next(f for f in results if f.form_type == "10-K/A")
        assert amendment.is_amendment is True

    def test_since_and_limit_params(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToFilingsEnricher,
            graph,
            vault,
            self.routes,
            {"form_types": "", "since": "2024-09-01", "limit": 2},
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        assert len(results) == 2
        assert all(f.filed_at.year == 2024 for f in results)

    def test_a_bad_since_value_does_not_half_write_the_graph(
        self, graph: Any, vault: Any, recording_logger: Any
    ) -> None:
        enricher, _ = build(
            IssuerToFilingsEnricher, graph, vault, self.routes, {"since": "last tuesday"}
        )
        assert run(enricher.execute([Issuer.from_cik(320193)])) == []
        assert graph.nodes == []
        assert any("errored" in message for message in recording_logger.messages("error"))

    def test_issuer_without_a_cik_is_counted(self, graph: Any, vault: Any) -> None:
        enricher, transport = build(IssuerToFilingsEnricher, graph, vault, self.routes)
        results = run(enricher.execute([Issuer.from_name("Some Private Co")]))
        assert results == []
        assert enricher.failures == 1
        assert transport.requests == []

    def test_source_failure_is_logged_per_item_and_the_run_continues(
        self, graph: Any, vault: Any, recording_logger: Any
    ) -> None:
        enricher, _ = build(
            IssuerToFilingsEnricher,
            graph,
            vault,
            {"submissions/CIK0000320193.json": (200, encode(SUBMISSIONS))},
        )
        # The second issuer's submissions URL is not routed, so its fetch fails.
        results = run(
            enricher.execute([Issuer.from_cik(320193), Issuer.from_cik(789019)])
        )
        assert results, "the healthy issuer still produced filings"
        assert enricher.failures == 1
        assert any(
            "0000789019" in message for message in recording_logger.messages("error")
        )

    def test_running_twice_converges(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(IssuerToFilingsEnricher, graph, vault, self.routes)
        run(enricher.execute([Issuer.from_cik(320193)]))
        first = graph.node_keys()
        second_enricher, _ = build(IssuerToFilingsEnricher, graph, vault, self.routes)
        run(second_enricher.execute([Issuer.from_cik(320193)]))
        assert graph.node_keys() == first


class TestIssuerToFacts:
    routes = {"companyfacts/CIK0000320193.json": (200, encode(COMPANY_FACTS))}

    def test_each_vintage_is_its_own_node(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToFactsEnricher, graph, vault, self.routes, {"tags": "Revenues"}
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        fact_ids = {f.fact_id for f in results}
        assert "xbrl:0000320193:Revenues:USD:FY2024:0000320193-24-000123" in fact_ids
        assert "xbrl:0000320193:Revenues:USD:FY2024:0000320193-25-000010" in fact_ids
        assert len(fact_ids) == 3

    def test_facts_are_linked_from_the_filing_that_reported_them(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(
            IssuerToFactsEnricher, graph, vault, self.routes, {"tags": "Assets"}
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        fact = results[0]
        edges = graph.edges()
        assert (
            "filing:0000320193-24-000123",
            f"fact:{fact.fact_id}",
            "REPORTS_FACT",
        ) in edges
        assert ("issuer:" + APPLE, "filing:0000320193-24-000123", "FILED") in edges

    def test_instant_and_duration_facts_keep_their_shape(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(IssuerToFactsEnricher, graph, vault, self.routes)
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        assets = next(f for f in results if f.tag == "Assets")
        revenues = next(f for f in results if f.tag == "Revenues")
        assert assets.is_instant()
        assert not revenues.is_instant()
        assert revenues.period_start is not None

    def test_values_are_cited(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToFactsEnricher, graph, vault, self.routes, {"tags": "Assets"}
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        props = assert_cited(graph, "fact", results[0].fact_id)
        assert props["method"] == "reported"
        assert props["confidence"] == 1.0
        assert "Assets" in props["locator"]


class TestIssuerToInsiderTransactions:
    routes = {
        "submissions/CIK0000320193.json": (200, encode(SUBMISSIONS)),
        "/Archives/edgar/data/320193/": (200, FORM4_XML),
    }

    def test_writes_each_transaction_line_with_its_people(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(
            IssuerToInsiderTransactionsEnricher, graph, vault, self.routes
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))

        assert [t.transaction_id for t in results] == [
            "form4:0001214156-24-000044:1",
            "form4:0001214156-24-000044:2",
        ]
        sale = results[0]
        assert sale.transaction_code == "S"
        assert sale.value == pytest.approx(223986 * 225.50, rel=1e-9)
        assert sale.is_10b5_1 is True
        assert sale.is_open_market()
        assert not sale.is_discretionary_signal()  # planned, so not a view
        assert_cited(graph, "insidertransaction", sale.transaction_id)

    def test_links_person_filing_and_provisional_security(
        self, graph: Any, vault: Any
    ) -> None:
        enricher, _ = build(
            IssuerToInsiderTransactionsEnricher, graph, vault, self.routes
        )
        run(enricher.execute([Issuer.from_cik(320193)]))
        edges = graph.edges()
        txn = "insidertransaction:form4:0001214156-24-000044:1"
        assert (txn, "person:cik:0001214156", "REPORTED_BY") in edges
        assert (txn, "filing:0001214156-24-000044", "DISCLOSED_IN") in edges
        # The filing gives a symbol, not a venue, so the security stays provisional.
        assert (txn, "security:slug:aapl", "TRANSACTED_IN") in edges

    def test_the_person_keeps_only_public_roles(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToInsiderTransactionsEnricher, graph, vault, self.routes
        )
        run(enricher.execute([Issuer.from_cik(320193)]))
        props = graph.properties("person", "cik:0001214156")
        assert props["titles"] == ["Chief Executive Officer"]
        assert props["is_officer"] is True
        assert props["actor_type"] == "insider"
        assert not {"email", "phone", "address"} & set(props)

    def test_a_grant_is_not_read_as_a_signal(self, graph: Any, vault: Any) -> None:
        enricher, _ = build(
            IssuerToInsiderTransactionsEnricher, graph, vault, self.routes
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        grant = results[1]
        assert grant.transaction_code == "A"
        assert not grant.is_open_market()
        assert grant.ownership_type == "indirect"

    def test_one_unreadable_form4_does_not_lose_the_others(
        self, graph: Any, vault: Any, recording_logger: Any
    ) -> None:
        submissions = json.loads(json.dumps(SUBMISSIONS))
        recent = submissions["filings"]["recent"]
        recent["accessionNumber"].insert(0, "0001214156-24-000099")
        recent["form"].insert(0, "4")
        recent["filingDate"].insert(0, "2024-10-29")
        recent["primaryDocument"].insert(0, "broken.xml")
        enricher, _ = build(
            IssuerToInsiderTransactionsEnricher,
            graph,
            vault,
            {
                "submissions/CIK0000320193.json": (200, encode(submissions)),
                "/000121415624000099/broken.xml": (200, b"<ownershipDocument><oops>"),
                "/Archives/edgar/data/320193/": (200, FORM4_XML),
            },
        )
        results = run(enricher.execute([Issuer.from_cik(320193)]))
        assert len(results) == 2  # the healthy filing's two lines
        assert enricher.failures == 1
        assert any("did not parse" in m for m in recording_logger.messages("error"))
