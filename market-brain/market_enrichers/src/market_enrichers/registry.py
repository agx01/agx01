"""Import every enricher module so the ``@flowsint_enricher`` decorators run.

Upstream's ``load_all_enrichers()`` walks ``flowsint_enrichers.__path__[0]`` with
``os.walk`` — recursively, and without needing ``__init__.py`` in subdirectories — so it
never sees a separately installed package (see
../docs/adr/0003-type-registration-strategy.md).
This loader covers ours, and is strict by default: an enricher that fails to import must
fail loudly rather than quietly not exist.

Note that upstream's ``ENRICHER_REGISTRY`` is keyed on ``name()``, so **two enrichers
sharing a name silently overwrite each other**. :func:`load_market_enrichers` returns the
mapping, and the contract tests assert ours are unique.
"""

from __future__ import annotations

import importlib
import os
from typing import Any


def load_market_enrichers(*, strict: bool = True) -> dict[str, type[Any]]:
    """Import all enricher modules; return ``{name(): class}`` for ours.

    Args:
        strict: re-raise import errors (default).
    """
    import market_enrichers as package

    from .market_enricher import MarketEnricher

    root = package.__path__[0]
    prefix = package.__name__
    skip_dirs = {"tools", "__pycache__"}
    skip_modules = {"registry", "params", "market_enricher", "_base", "__init__"}

    for current, directories, files in os.walk(root):
        directories[:] = [d for d in directories if d not in skip_dirs]
        relative = os.path.relpath(current, root)
        package_path = (
            prefix if relative == "." else f"{prefix}.{relative.replace(os.sep, '.')}"
        )
        for filename in sorted(files):
            if not filename.endswith(".py"):
                continue
            leaf = filename[:-3]
            if leaf in skip_modules or leaf.startswith("_"):
                continue
            try:
                importlib.import_module(f"{package_path}.{leaf}")
            except Exception:
                if strict:
                    raise

    found: dict[str, type[Any]] = {}
    stack = [MarketEnricher]
    while stack:
        current_class = stack.pop()
        for subclass in current_class.__subclasses__():
            stack.append(subclass)
            found[subclass.name()] = subclass
    return found


def market_enricher_names() -> tuple[str, ...]:
    """Registered enricher ids, sorted."""
    return tuple(sorted(load_market_enrichers()))
