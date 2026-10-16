"""The contract with Flowsint and with Neo4j.

These are the assertions that catch an upstream change or a careless field addition:
registration, exactly one primary field, a computed label, and property types a Neo4j
node can actually hold. They run against the stub base class by default; run them with a
real ``flowsint_types`` importable to check the genuine one
(docs/adr/0003-type-registration-strategy.md).
"""

from __future__ import annotations

import types
import typing
from datetime import date, datetime
from typing import Any, Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from market_types import MARKET_TYPES, Provenance, load_market_types

#: What a Neo4j property can hold. Anything else — a nested model, a dict, a set —
#: cannot be stored on a node and must become its own node or a relationship property.
GRAPH_SCALARS: tuple[type, ...] = (str, int, float, bool, date, datetime)

PROVENANCE_FIELDS = frozenset(Provenance.model_fields)


def _unwrap_optional(annotation: Any) -> list[Any]:
    """Return the non-None members of an Optional/Union annotation."""
    if get_origin(annotation) in (Union, types.UnionType):
        return [arg for arg in get_args(annotation) if arg is not type(None)]
    return [annotation]


def _is_graph_safe(annotation: Any) -> bool:
    for member in _unwrap_optional(annotation):
        origin = get_origin(member)
        if origin is Literal:
            if not all(isinstance(arg, (str, int, bool)) for arg in get_args(member)):
                return False
        elif origin in (list, tuple):
            args = [a for a in get_args(member) if a is not Ellipsis]
            if not args or not all(
                get_origin(a) is Literal
                or isinstance(a, type)
                and issubclass(a, GRAPH_SCALARS)
                for a in args
            ):
                return False
        elif isinstance(member, type):
            if not issubclass(member, GRAPH_SCALARS):
                return False
        else:
            return False
    return True


def _primary_field(model: type[BaseModel]) -> str:
    """Find the primary field the way upstream's Enricher.preprocess() does."""
    for name, field in model.model_fields.items():
        extra = field.json_schema_extra
        if extra and isinstance(extra, dict) and extra.get("primary"):
            return str(name)
    raise AssertionError(f"{model.__name__} marks no primary field")


@pytest.mark.parametrize("model", MARKET_TYPES, ids=lambda m: m.__name__)
class TestTypeContract:
    def test_registered_under_exact_and_lowercase_names(
        self, model: type[BaseModel], type_registry: Any
    ) -> None:
        # Upstream registers both spellings: the class name, and lowercase "for Neo4j
        # compatibility" (flowsint_types/registry.py).
        assert type_registry.get(model.__name__) is model
        assert type_registry.get_lowercase(model.__name__.lower()) is model

    def test_exactly_one_primary_field(self, model: type[BaseModel]) -> None:
        primaries = [
            name
            for name, field in model.model_fields.items()
            if field.json_schema_extra
            and isinstance(field.json_schema_extra, dict)
            and field.json_schema_extra.get("primary")
        ]
        assert len(primaries) == 1, f"{model.__name__} has primaries {primaries}"

    def test_primary_field_is_required(self, model: type[BaseModel]) -> None:
        # preprocess() falls back to "first required field" when no primary is marked;
        # a required primary keeps both paths pointing at the same field.
        assert model.model_fields[_primary_field(model)].is_required()

    def test_primary_field_is_a_string_key(self, model: type[BaseModel]) -> None:
        annotation = model.model_fields[_primary_field(model)].annotation
        assert annotation is str, f"{model.__name__} merge key must be a str"

    def test_carries_the_provenance_block(self, model: type[BaseModel]) -> None:
        assert set(model.model_fields) >= PROVENANCE_FIELDS

    def test_provenance_is_optional_so_construction_never_needs_it(
        self, model: type[BaseModel]
    ) -> None:
        for name in PROVENANCE_FIELDS:
            assert not model.model_fields[name].is_required()

    def test_declares_node_label(self, model: type[BaseModel]) -> None:
        assert "nodeLabel" in model.model_fields

    def test_every_field_is_graph_safe(self, model: type[BaseModel]) -> None:
        offenders = [
            name
            for name, field in model.model_fields.items()
            if not _is_graph_safe(field.annotation)
        ]
        assert not offenders, f"{model.__name__} has non-storable fields: {offenders}"

    def test_has_a_compute_label_validator(self, model: type[BaseModel]) -> None:
        assert hasattr(model, "compute_label")

    def test_allows_extra_keys_like_upstream(self, model: type[BaseModel]) -> None:
        assert model.model_config.get("extra") == "allow"


class TestLoader:
    def test_discovers_every_market_type(self) -> None:
        discovered = load_market_types()
        for model in MARKET_TYPES:
            assert discovered.get(model.__name__) is model

    def test_does_not_register_the_provenance_mixin(self, type_registry: Any) -> None:
        # The mixin is not an entity; registering it would create a stray node label.
        assert type_registry.get("Provenance") is None

    def test_loader_is_strict_by_default(self) -> None:
        signature = typing.get_type_hints(load_market_types)
        assert signature["strict"] is bool


class TestGraphSafetyHelper:
    """The graph-safety check is only useful if it rejects what Neo4j rejects."""

    @pytest.mark.parametrize(
        "annotation",
        [str, int, float, bool, date, datetime, list[str], str | None, Literal["a", "b"]],
    )
    def test_accepts_storable(self, annotation: Any) -> None:
        assert _is_graph_safe(annotation)

    @pytest.mark.parametrize(
        "annotation",
        [
            dict[str, str],
            list[dict[str, str]],
            set[str],
            Provenance,
            list[Provenance],
            Any,
        ],
    )
    def test_rejects_unstorable(self, annotation: Any) -> None:
        assert not _is_graph_safe(annotation)


def test_nodes_dump_to_storable_values() -> None:
    """A real dump, not just annotations: what create_node() would hand the driver."""
    from market_types import Issuer, provenance

    issuer = Issuer.from_cik(
        320193,
        name="Apple Inc.",
        former_names=["Apple Computer, Inc."],
        employees=164000,
        employees_as_of=date(2025, 9, 27),
        **provenance("sec_edgar", source_ref="https://www.sec.gov/x", scan_id="s1"),
    )
    for key, value in issuer.model_dump(exclude_none=True).items():
        if isinstance(value, list):
            assert all(isinstance(item, GRAPH_SCALARS) for item in value), key
        else:
            assert isinstance(value, GRAPH_SCALARS), f"{key} -> {type(value)}"
