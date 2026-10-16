"""Test harness: stand in for a running Flowsint.

``market_enrichers`` imports ``Enricher`` and ``Logger`` from ``flowsint_core`` and the
``@flowsint_enricher`` decorator from ``flowsint_enrichers``, none of which are on PyPI
(../docs/adr/0003-type-registration-strategy.md). This conftest injects stubs before the
package is imported.

The ``Enricher`` stub **mirrors upstream verbatim** as read on 2026-10-16 from
``flowsint-core/src/flowsint_core/core/enricher_base.py`` — in particular
``resolve_params``, ``preprocess`` (primary-field coercion) and ``execute`` (which
swallows exceptions and returns ``[]``, then flushes the graph). Those behaviours are the
contract our enrichers are written against, so the tests exercise them rather than a
friendlier invention. If upstream changes shape, these stubs stop matching and
``tests/test_contract.py`` is where that should surface: re-read the upstream file when
bumping ``FLOWSINT_VERSION``.

What this harness is *not* is integration. A real run needs the API to list the
enrichers, the worker to execute them, and Neo4j to accept the writes.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest

_USING_STUBS = False


def _install_stubs() -> None:
    from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

    # --- flowsint_types -------------------------------------------------------------
    class FlowsintType(BaseModel):
        nodeLabel: Optional[str] = Field(
            None,
            description="UI-readable label for this entity, the one used on the graph.",
            title="Label",
        )
        model_config = ConfigDict(extra="allow")

    class _TypeRegistry:
        def __init__(self) -> None:
            self._types: dict[str, type[Any]] = {}
            self._lowercase_types: dict[str, type[Any]] = {}

        def register(self, cls: type[Any]) -> type[Any]:
            self._types[cls.__name__] = cls
            self._lowercase_types[cls.__name__.lower()] = cls
            return cls

        def get(self, name: str) -> Optional[type[Any]]:
            return self._types.get(name)

        def get_lowercase(self, name: str) -> Optional[type[Any]]:
            return self._lowercase_types.get(name.lower())

    type_registry = _TypeRegistry()

    def flowsint_type(cls: type[Any]) -> type[Any]:
        return type_registry.register(cls)

    @flowsint_type
    class Phrase(FlowsintType):
        """Mirror of upstream flowsint_types.phrase.Phrase."""

        text: Any = Field(
            ...,
            description="The content of the phrase.",
            title="Phrase text value.",
            json_schema_extra={"primary": True},
        )

        @classmethod
        def from_string(cls, line: str) -> Phrase:
            return cls(text=line.strip())

        @classmethod
        def detect(cls, line: str) -> bool:
            return False

    types_pkg = types.ModuleType("flowsint_types")
    types_pkg.__path__ = []
    base_mod = types.ModuleType("flowsint_types.flowsint_base")
    base_mod.FlowsintType = FlowsintType  # type: ignore[attr-defined]
    registry_mod = types.ModuleType("flowsint_types.registry")
    registry_mod.flowsint_type = flowsint_type  # type: ignore[attr-defined]
    registry_mod.TYPE_REGISTRY = type_registry  # type: ignore[attr-defined]
    phrase_mod = types.ModuleType("flowsint_types.phrase")
    phrase_mod.Phrase = Phrase  # type: ignore[attr-defined]
    for name, module in {
        "flowsint_types": types_pkg,
        "flowsint_types.flowsint_base": base_mod,
        "flowsint_types.registry": registry_mod,
        "flowsint_types.phrase": phrase_mod,
    }.items():
        sys.modules.setdefault(name, module)

    # --- flowsint_core.core.logger ---------------------------------------------------
    class _RecordingLogger:
        """Same call surface as upstream's Logger singleton: (sketch_id, dict)."""

        def __init__(self) -> None:
            self.entries: list[tuple[str, str, str]] = []

        def _record(self, level: str, sketch_id: Any, message: dict[str, Any]) -> None:
            self.entries.append((level, str(sketch_id), str(message.get("message", ""))))

        def info(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("info", sketch_id, message)

        def error(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("error", sketch_id, message)

        def warn(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("warn", sketch_id, message)

        def debug(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("debug", sketch_id, message)

        def success(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("success", sketch_id, message)

        def completed(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("completed", sketch_id, message)

        def pending(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("pending", sketch_id, message)

        def graph_append(self, sketch_id: Any, message: dict[str, Any]) -> None:
            self._record("graph_append", sketch_id, message)

        def messages(self, level: Optional[str] = None) -> list[str]:
            return [m for lvl, _, m in self.entries if level is None or lvl == level]

        def clear(self) -> None:
            self.entries.clear()

    logger = _RecordingLogger()

    # --- a graph service that records instead of writing -----------------------------
    class FakeGraphService:
        def __init__(self) -> None:
            self.nodes: list[tuple[str, str, dict[str, Any]]] = []
            self.relationships: list[tuple[str, str, str]] = []
            self.flushed = 0

        @staticmethod
        def _key(node: Any) -> tuple[str, str]:
            for name, fld in type(node).model_fields.items():
                extra = fld.json_schema_extra
                if extra and isinstance(extra, dict) and extra.get("primary"):
                    return type(node).__name__.lower(), str(getattr(node, name))
            return type(node).__name__.lower(), repr(node)

        def create_node_from_flowsint_type(self, node_obj: Any) -> None:
            label, key = self._key(node_obj)
            self.nodes.append((label, key, node_obj.model_dump(exclude_none=True)))

        def create_relationship(self, from_obj: Any, to_obj: Any, rel_label: str) -> None:
            self.relationships.append(
                (
                    f"{self._key(from_obj)[0]}:{self._key(from_obj)[1]}",
                    f"{self._key(to_obj)[0]}:{self._key(to_obj)[1]}",
                    rel_label,
                )
            )

        def flush(self) -> None:
            self.flushed += 1

        # conveniences for assertions
        def node_keys(self) -> set[tuple[str, str]]:
            return {(label, key) for label, key, _ in self.nodes}

        def edges(self) -> set[tuple[str, str, str]]:
            return set(self.relationships)

        def properties(self, label: str, key: str) -> dict[str, Any]:
            for node_label, node_key, props in self.nodes:
                if (node_label, node_key) == (label, key):
                    return props
            raise AssertionError(f"no node {label}:{key} written")

    # --- flowsint_core.core.enricher_base -------------------------------------------
    class InvalidEnricherParams(Exception):
        pass

    class Enricher:
        """Mirror of the upstream base class, limited to the behaviour we rely on."""

        InputType: Any = NotImplemented
        OutputType: Any = NotImplemented

        def __init__(
            self,
            sketch_id: Optional[str] = None,
            scan_id: Optional[str] = None,
            params_schema: Optional[list[dict[str, Any]]] = None,
            vault: Optional[Any] = None,
            params: Optional[dict[str, Any]] = None,
            graph_service: Optional[Any] = None,
        ) -> None:
            self.scan_id = scan_id or "default"
            self.sketch_id = sketch_id or "system"
            self.vault = vault
            self.params_schema = params_schema or self.get_params_schema()
            self.params: dict[str, Any] = params or {}
            self._graph_service = graph_service or FakeGraphService()

        async def async_init(self) -> None:
            self.params = self.resolve_params()

        def resolve_params(self) -> dict[str, Any]:
            resolved: dict[str, Any] = {}
            for param in self.params_schema:
                name = param["name"]
                kind = param.get("type", "string")
                if kind == "vaultSecret":
                    secret = None
                    if self.vault is not None:
                        if self.params.get(name):
                            secret = self.vault.get_secret(self.params[name])
                        if secret is None:
                            secret = self.vault.get_secret(name)
                        if secret is not None:
                            resolved[name] = secret
                        elif param.get("required", False):
                            raise Exception(
                                f"Required vault secret '{name}' is missing. "
                                f"Please go to the Vault settings and create "
                                f"a '{name}' key."
                            )
                    if name not in resolved and param.get("default") is not None:
                        resolved[name] = param["default"]
                else:
                    if self.params.get(name):
                        resolved[name] = self.params[name]
                    elif param.get("default") is not None:
                        resolved[name] = param["default"]
            return resolved

        @classmethod
        def name(cls) -> str:
            raise NotImplementedError

        @classmethod
        def category(cls) -> str:
            raise NotImplementedError

        @classmethod
        def key(cls) -> str:
            raise NotImplementedError

        @classmethod
        def icon(cls) -> Optional[str]:
            return None

        @classmethod
        def documentation(cls) -> str:
            return ""

        @classmethod
        def required_params(cls) -> bool:
            return False

        @classmethod
        def get_params_schema(cls) -> list[dict[str, Any]]:
            return []

        @classmethod
        def input_schema(cls) -> dict[str, Any]:
            return {"type": getattr(cls.InputType, "__name__", "any")}

        @classmethod
        def output_schema(cls) -> dict[str, Any]:
            return {"type": getattr(cls.OutputType, "__name__", "any")}

        def get_params(self) -> dict[str, Any]:
            return self.params

        def get_secret(self, key_name: str, default: Any = None) -> Any:
            value = self.params.get(key_name, default)
            return value if value is not None else default

        def preprocess(self, values: list[Any]) -> list[Any]:
            if self.InputType is NotImplemented:
                return values
            base_type = self.InputType
            adapter = TypeAdapter(base_type)
            primary_field = None
            for fname, fld in base_type.model_fields.items():
                extra = fld.json_schema_extra
                if extra and isinstance(extra, dict) and extra.get("primary"):
                    primary_field = fname
                    break
            if primary_field is None:
                for fname, fld in base_type.model_fields.items():
                    if fld.is_required():
                        primary_field = fname
                        break
            cleaned = []
            for item in values:
                try:
                    if isinstance(item, str) and primary_field:
                        item = {primary_field: item}
                    cleaned.append(adapter.validate_python(item))
                except Exception:
                    continue
            if not cleaned:
                logger.warn(
                    self.sketch_id,
                    {
                        "message": (
                            f"No valid input were provided to enricher '{self.name()}'."
                        )
                    },
                )
                return values
            return cleaned

        def postprocess(
            self, results: list[Any], input_data: Optional[list[Any]] = None
        ) -> list[Any]:
            return results

        async def execute(self, values: list[Any]) -> list[Any]:
            logger.info(self.sketch_id, {"message": f"Enricher {self.name()} started."})
            try:
                await self.async_init()
                preprocessed = self.preprocess(values)
                results = await self.scan(preprocessed)
                processed = self.postprocess(results, preprocessed)
                self._graph_service.flush()
                logger.completed(
                    self.sketch_id, {"message": f"Enricher {self.name()} finished."}
                )
                return processed
            except Exception as exc:
                logger.error(
                    self.sketch_id,
                    {"message": f"Enricher {self.name()} errored: {exc}"},
                )
                return []

        async def scan(self, values: list[Any]) -> list[Any]:
            raise NotImplementedError

        def create_node(self, node_obj: Any) -> None:
            self._graph_service.create_node_from_flowsint_type(node_obj=node_obj)

        def create_relationship(
            self, from_obj: Any, to_obj: Any, rel_label: str = "IS_RELATED_TO"
        ) -> None:
            self._graph_service.create_relationship(
                from_obj=from_obj, to_obj=to_obj, rel_label=rel_label
            )

        def log_graph_message(self, message: str) -> None:
            logger.graph_append(self.sketch_id, {"message": message})

        @property
        def graph_service(self) -> Any:
            return self._graph_service

    core_pkg = types.ModuleType("flowsint_core")
    core_pkg.__path__ = []
    core_core = types.ModuleType("flowsint_core.core")
    core_core.__path__ = []
    enricher_mod = types.ModuleType("flowsint_core.core.enricher_base")
    enricher_mod.Enricher = Enricher  # type: ignore[attr-defined]
    enricher_mod.InvalidEnricherParams = InvalidEnricherParams  # type: ignore[attr-defined]
    logger_mod = types.ModuleType("flowsint_core.core.logger")
    logger_mod.Logger = logger  # type: ignore[attr-defined]

    # --- flowsint_enrichers.registry -------------------------------------------------
    class _EnricherRegistry:
        """Mirror of upstream: keyed on name(), so duplicates overwrite silently."""

        def __init__(self) -> None:
            self._enrichers: dict[str, type[Any]] = {}

        def register(self, enricher_class: type[Any]) -> type[Any]:
            self._enrichers[enricher_class.name()] = enricher_class
            return enricher_class

        def enricher_exists(self, name: str) -> bool:
            return name in self._enrichers

        def get(self, name: str) -> Optional[type[Any]]:
            return self._enrichers.get(name)

        def all(self) -> dict[str, type[Any]]:
            return dict(self._enrichers)

    enricher_registry = _EnricherRegistry()

    def flowsint_enricher(cls: type[Any]) -> type[Any]:
        return enricher_registry.register(cls)

    enrichers_pkg = types.ModuleType("flowsint_enrichers")
    enrichers_pkg.__path__ = []
    enrichers_registry_mod = types.ModuleType("flowsint_enrichers.registry")
    enrichers_registry_mod.flowsint_enricher = flowsint_enricher  # type: ignore[attr-defined]
    enrichers_registry_mod.ENRICHER_REGISTRY = enricher_registry  # type: ignore[attr-defined]

    for name, module in {
        "flowsint_core": core_pkg,
        "flowsint_core.core": core_core,
        "flowsint_core.core.enricher_base": enricher_mod,
        "flowsint_core.core.logger": logger_mod,
        "flowsint_enrichers": enrichers_pkg,
        "flowsint_enrichers.registry": enrichers_registry_mod,
    }.items():
        sys.modules.setdefault(name, module)

    # exported for fixtures
    globals()["_LOGGER"] = logger
    globals()["_ENRICHER_REGISTRY"] = enricher_registry
    globals()["_FakeGraphService"] = FakeGraphService


try:  # pragma: no cover - depends on the environment
    import flowsint_core  # noqa: F401
    import flowsint_enrichers  # noqa: F401
    import flowsint_types  # noqa: F401
except ModuleNotFoundError:
    _USING_STUBS = True
    _install_stubs()


@dataclass
class FakeVault:
    """Stands in for Flowsint's encrypted vault: name -> secret."""

    secrets: dict[str, str] = field(default_factory=dict)

    def get_secret(self, key: str) -> Optional[str]:
        return self.secrets.get(key)


@dataclass
class FakeTransport:
    """Routes URLs to canned responses and records what was asked for.

    Any URL not in the table is a failed assertion, so a test can never accidentally
    reach the network or quietly exercise an unintended endpoint.
    """

    routes: dict[str, tuple[int, bytes]] = field(default_factory=dict)
    requests: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    default: Optional[tuple[int, bytes]] = None

    def get(self, url: str, headers: Any, timeout: float) -> tuple[int, bytes]:
        self.requests.append((url, dict(headers)))
        for pattern, response in self.routes.items():
            if pattern in url:
                return response
        if self.default is not None:
            return self.default
        raise AssertionError(f"unexpected request to {url}")

    def urls(self) -> list[str]:
        return [url for url, _ in self.requests]


@pytest.fixture(scope="session")
def using_stubs() -> bool:
    return _USING_STUBS


@pytest.fixture
def recording_logger() -> Any:
    logger = globals().get("_LOGGER")
    if logger is None:  # pragma: no cover - real install
        pytest.skip("logger assertions need the stub logger")
    logger.clear()
    return logger


@pytest.fixture
def enricher_registry() -> Any:
    registry = globals().get("_ENRICHER_REGISTRY")
    if registry is None:  # pragma: no cover - real install
        from flowsint_enrichers.registry import ENRICHER_REGISTRY

        return ENRICHER_REGISTRY
    return registry


@pytest.fixture
def graph() -> Any:
    factory = globals().get("_FakeGraphService")
    if factory is None:  # pragma: no cover - real install
        pytest.skip("graph assertions need the stub graph service")
    return factory()


@pytest.fixture
def vault() -> FakeVault:
    return FakeVault(
        secrets={
            "SEC_USER_AGENT": "market-brain-tests tests@example.com",
            "EODHD_API_KEY": "test-token",
        }
    )
