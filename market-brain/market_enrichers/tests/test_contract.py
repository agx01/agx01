"""The contract with Flowsint, and with our own ontology.

These assertions catch the failures that are otherwise silent: an enricher that never
registers, two sharing a name (upstream's registry is keyed on ``name()``, so the second
overwrites the first), a ``key()`` that does not match the input type's primary field, a
``documentation()`` that breaks the listing endpoint, or a relationship label that exists
in code but not in the ontology.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from market_enrichers import MARKET_ENRICHERS, MarketEnricher, load_market_enrichers

PARAM_TYPES = {"string", "number", "select", "url", "vaultSecret"}
ONTOLOGY = Path(__file__).resolve().parents[2] / "docs" / "03-ontology.md"
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "market_enrichers"


def primary_field(model: type[BaseModel]) -> str:
    for name, field in model.model_fields.items():
        extra = field.json_schema_extra
        if extra and isinstance(extra, dict) and extra.get("primary"):
            return str(name)
    raise AssertionError(f"{model.__name__} marks no primary field")


@pytest.mark.parametrize("enricher", MARKET_ENRICHERS, ids=lambda e: e.name())
class TestEnricherContract:
    def test_registered_under_its_name(
        self, enricher: type[MarketEnricher], enricher_registry: Any
    ) -> None:
        assert enricher_registry.get(enricher.name()) is enricher

    def test_subclasses_the_shared_base(self, enricher: type[MarketEnricher]) -> None:
        assert issubclass(enricher, MarketEnricher)

    def test_name_follows_the_input_to_output_convention(
        self, enricher: type[MarketEnricher]
    ) -> None:
        assert re.fullmatch(
            r"[a-z0-9]+(_[a-z0-9]+)*_to_[a-z0-9]+(_[a-z0-9]+)*", enricher.name()
        )

    def test_declares_base_types_not_lists(self, enricher: type[MarketEnricher]) -> None:
        # Upstream generates input/output schemas from these, and a List[...] breaks it.
        for attribute in ("InputType", "OutputType"):
            declared = getattr(enricher, attribute)
            assert isinstance(declared, type), f"{attribute} is not a class"
            assert issubclass(declared, BaseModel)

    def test_key_is_the_input_types_primary_field(
        self, enricher: type[MarketEnricher]
    ) -> None:
        # preprocess() coerces a bare string with the primary field; key() is what the
        # UI sends. If they disagree, input silently fails validation and is skipped.
        assert enricher.key() == primary_field(enricher.InputType)

    def test_category_is_uniform(self, enricher: type[MarketEnricher]) -> None:
        assert enricher.category() == "Market"

    def test_documentation_is_a_cleandoc_safe_string(
        self, enricher: type[MarketEnricher]
    ) -> None:
        # Upstream's registry calls inspect.cleandoc(documentation()) when listing
        # enrichers; None there would break the listing for every enricher.
        documentation = enricher.documentation()
        assert isinstance(documentation, str) and documentation.strip()
        assert inspect.cleandoc(documentation)

    def test_docstring_names_its_source(self, enricher: type[MarketEnricher]) -> None:
        # Upstream convention: the docstring opens with a [Source] tag.
        assert re.match(r"\[[^\]]+\]", enricher.__doc__ or "")

    def test_input_schema_exposes_a_type(self, enricher: type[MarketEnricher]) -> None:
        # list_by_input_type() reads input_schema()["type"].
        assert enricher.input_schema().get("type")

    def test_icon_is_a_string_or_none(self, enricher: type[MarketEnricher]) -> None:
        assert enricher.icon() is None or isinstance(enricher.icon(), str)

    def test_params_schema_entries_are_well_formed(
        self, enricher: type[MarketEnricher]
    ) -> None:
        names: set[str] = set()
        for param in enricher.get_params_schema():
            assert param["name"] not in names, f"duplicate param {param['name']}"
            names.add(param["name"])
            assert param["type"] in PARAM_TYPES
            assert param["description"].strip()
            if param["type"] == "select":
                assert param.get("options")

    def test_secrets_are_declared_as_vault_secrets(
        self, enricher: type[MarketEnricher]
    ) -> None:
        for param in enricher.get_params_schema():
            if param["name"].endswith(("_KEY", "_TOKEN", "_AGENT")):
                assert param["type"] == "vaultSecret", param["name"]
                assert param.get("required") is True


class TestRegistry:
    def test_loader_finds_every_enricher(self) -> None:
        found = load_market_enrichers()
        for enricher in MARKET_ENRICHERS:
            assert found.get(enricher.name()) is enricher

    def test_names_are_unique(self) -> None:
        # Upstream keys ENRICHER_REGISTRY on name(), so a collision silently replaces
        # an enricher rather than erroring.
        names = [enricher.name() for enricher in MARKET_ENRICHERS]
        assert len(names) == len(set(names))

    def test_base_class_is_not_itself_registered(self, enricher_registry: Any) -> None:
        assert all(
            registered is not MarketEnricher
            for registered in enricher_registry.all().values()
        )


class TestSharedBaseBehaviour:
    def _enricher(self, graph: Any) -> Any:
        from market_enrichers import IssuerToFilingsEnricher

        return IssuerToFilingsEnricher(
            sketch_id="s", scan_id="scan-1", vault=None, params={}, graph_service=graph
        )

    def test_stage_dedupes_by_merge_key(self, graph: Any) -> None:
        from market_types import Issuer

        enricher = self._enricher(graph)
        enricher.stage(Issuer.from_cik(320193, name="Apple Inc."))
        enricher.stage(Issuer.from_cik("320193"))
        enricher.postprocess([])
        assert graph.node_keys() == {("issuer", "cik:0000320193")}

    def test_link_rejects_a_label_that_is_not_upper_snake_case(self, graph: Any) -> None:
        from market_types import Issuer, Security

        enricher = self._enricher(graph)
        with pytest.raises(ValueError, match="UPPER_SNAKE_CASE"):
            enricher.link(
                Issuer.from_cik(320193), Security.from_eodhd_code("AAPL.US"), "issues"
            )

    def test_stale_reads_are_counted_and_marked(self, graph: Any) -> None:
        from datetime import UTC, datetime

        from market_enrichers.tools.http import RetrievalRecord

        enricher = self._enricher(graph)
        stale = RetrievalRecord(
            source="sec_edgar",
            url="https://example.com/x",
            request_hash="abc",
            retrieved_at=datetime.now(UTC),
            status=200,
            from_cache=True,
            outcome="cached_stale",
        )
        block = enricher.provenance_from(stale)
        assert block["fetch_outcome"] == "cached_stale"
        assert enricher.stale_reads == 1

    def test_provenance_defaults_to_the_enrichers_source(self, graph: Any) -> None:
        from datetime import UTC, datetime

        from market_enrichers.tools.http import RetrievalRecord

        enricher = self._enricher(graph)
        block = enricher.provenance_from(
            RetrievalRecord(
                source="sec_edgar",
                url="https://example.com/x",
                request_hash="abc",
                retrieved_at=datetime.now(UTC),
                status=200,
                from_cache=False,
                outcome="ok",
            )
        )
        assert block["source"] == "sec_edgar"
        assert block["scan_id"] == "scan-1"
        assert block["confidence"] == 1.0


@pytest.mark.skipif(not ONTOLOGY.exists(), reason="ontology doc not available")
class TestOntologyAgreement:
    """Labels written by code must exist in the ontology, or the docs are fiction."""

    @staticmethod
    def documented_labels() -> set[str]:
        text = ONTOLOGY.read_text(encoding="utf-8")
        return set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", text))

    @staticmethod
    def emitted_labels() -> set[str]:
        labels: set[str] = set()
        for path in SOURCE_ROOT.rglob("*.py"):
            labels.update(
                re.findall(
                    r"self\.link\([^)]*?\"([A-Z][A-Z0-9_]+)\"", path.read_text(), re.S
                )
            )
        return labels

    def test_every_emitted_label_is_documented(self) -> None:
        emitted = self.emitted_labels()
        assert emitted, "no relationship labels found in the package source"
        undocumented = emitted - self.documented_labels()
        assert not undocumented, (
            f"labels missing from docs/03-ontology.md: {undocumented}"
        )
