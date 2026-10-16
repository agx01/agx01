"""Test setup: stand in for a Flowsint install.

``market_types`` imports its base class and type decorator from ``flowsint_types``,
which is not on PyPI — it comes from a Flowsint checkout or image
(docs/adr/0003-type-registration-strategy.md). So these tests inject stub modules into
``sys.modules`` before ``market_types`` is imported.

The stubs mirror upstream **verbatim** as read on 2026-10-16 from
``flowsint-types/src/flowsint_types/flowsint_base.py`` and ``registry.py`` (see
docs/references.md, F3 and F4). That is the point: if upstream's base class changes
shape, these stubs stop matching and `test_contract.py` is where the mismatch should be
caught — re-read the upstream files when bumping FLOWSINT_VERSION.

Real integration (API picks up the types, UI lists them, Neo4j writes the expected
labels) can only be verified against a running instance, which these tests do not
replace. Run `pytest` with a real flowsint_types importable to exercise the genuine
base class instead of the stub.
"""

from __future__ import annotations

import sys
import types
from typing import Any, Optional, TypeVar

import pytest

_USING_STUB = False

try:  # pragma: no cover - depends on the environment
    import flowsint_types  # noqa: F401  (real install present)
except ModuleNotFoundError:
    _USING_STUB = True

    from pydantic import BaseModel, ConfigDict, Field

    class FlowsintType(BaseModel):
        """Verbatim mirror of upstream flowsint_types.flowsint_base.FlowsintType."""

        nodeLabel: Optional[str] = Field(
            None,
            description="UI-readable label for this entity, the one used on the graph.",
            title="Label",
        )
        model_config = ConfigDict(extra="allow")

    T = TypeVar("T", bound=FlowsintType)

    class _TypeRegistry:
        """Mirror of upstream TypeRegistry: exact-name and lowercase-name maps."""

        def __init__(self) -> None:
            self._types: dict[str, type[Any]] = {}
            self._lowercase_types: dict[str, type[Any]] = {}

        def register(self, cls: type[T]) -> type[T]:
            self._types[cls.__name__] = cls
            self._lowercase_types[cls.__name__.lower()] = cls
            return cls

        def get(self, type_name: str) -> Optional[type[Any]]:
            return self._types.get(type_name)

        def get_lowercase(self, type_name: str) -> Optional[type[Any]]:
            return self._lowercase_types.get(type_name.lower())

        def all_types(self) -> dict[str, type[Any]]:
            return dict(self._types)

    TYPE_REGISTRY = _TypeRegistry()

    def flowsint_type(cls: type[T]) -> type[T]:
        return TYPE_REGISTRY.register(cls)

    _pkg = types.ModuleType("flowsint_types")
    _base_mod = types.ModuleType("flowsint_types.flowsint_base")
    _registry_mod = types.ModuleType("flowsint_types.registry")
    # Attributes are attached to modules created at runtime, so a type checker has
    # no declarations to check these names against — hence the narrow ignores.
    _pkg.__path__ = []
    _base_mod.FlowsintType = FlowsintType  # type: ignore[attr-defined]
    _registry_mod.flowsint_type = flowsint_type  # type: ignore[attr-defined]
    _registry_mod.TYPE_REGISTRY = TYPE_REGISTRY  # type: ignore[attr-defined]
    _pkg.flowsint_base = _base_mod  # type: ignore[attr-defined]
    _pkg.registry = _registry_mod  # type: ignore[attr-defined]

    sys.modules.setdefault("flowsint_types", _pkg)
    sys.modules.setdefault("flowsint_types.flowsint_base", _base_mod)
    sys.modules.setdefault("flowsint_types.registry", _registry_mod)


@pytest.fixture(scope="session")
def using_stub() -> bool:
    """True when these tests ran against the stub rather than a real Flowsint install."""
    return _USING_STUB


@pytest.fixture(scope="session")
def type_registry() -> Any:
    from flowsint_types.registry import TYPE_REGISTRY

    return TYPE_REGISTRY
