"""The single place that imports Flowsint's base class and type decorator.

Keeping the upstream import in one module means an upstream rename is a one-line fix,
and it makes the dependency on a *running Flowsint install* explicit and loud: there is
deliberately no local fallback shim. A silent shim would let our types register into a
fake registry, so the API and UI would never see them — exactly the quiet failure mode
documented in docs/02-flowsint-primer.md.
"""

from __future__ import annotations

try:  # pragma: no cover - exercised by the real install, stubbed in tests
    from flowsint_types.flowsint_base import FlowsintType
    from flowsint_types.registry import flowsint_type
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "market_types requires the flowsint_types package from a Flowsint install "
        "(https://github.com/reconurge/flowsint). Install it into the same environment "
        "as the API and Celery worker; see docs/adr/0003-type-registration-strategy.md "
        "for how these types reach the runtime."
    ) from exc

__all__ = ["FlowsintType", "flowsint_type"]
