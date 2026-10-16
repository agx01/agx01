"""Import every type module so the ``@flowsint_type`` decorators run.

Upstream's ``load_all_types()`` walks only the ``flowsint_types`` package's own
``__path__``, so a separately installed package is never imported and its decorators
never fire (docs/02-flowsint-primer.md, docs/adr/0003-type-registration-strategy.md).
This loader covers our package, and — unlike upstream's — it does **not** swallow
import errors by default: a type that fails to import must fail loudly, not vanish.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

_PRIVATE_PREFIX = "_"
_SKIP = frozenset({"registry", "keys", "identifiers", "provenance"})


def load_market_types(*, strict: bool = True) -> dict[str, type[Any]]:
    """Import all entity modules and return the registered market types by class name.

    Args:
        strict: re-raise import errors (default). Pass ``False`` only in a diagnostic
            context where a partially loaded registry is better than no startup.

    Returns:
        Mapping of class name to class, for the types this package registered.
    """
    import market_types as package

    registered: dict[str, type[Any]] = {}
    for _finder, modname, _ispkg in pkgutil.iter_modules(
        package.__path__, prefix=f"{package.__name__}."
    ):
        leaf = modname.rsplit(".", 1)[-1]
        if leaf.startswith(_PRIVATE_PREFIX) or leaf in _SKIP:
            continue
        try:
            module = importlib.import_module(modname)
        except Exception:
            if strict:
                raise
            continue
        for name, obj in vars(module).items():
            if isinstance(obj, type) and getattr(obj, "__module__", "") == modname:
                if name.startswith(_PRIVATE_PREFIX):
                    continue
                if hasattr(obj, "model_fields"):
                    registered[name] = obj
    return registered


def market_type_names() -> tuple[str, ...]:
    """Class names of the market types, sorted."""
    return tuple(sorted(load_market_types()))
