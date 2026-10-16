"""The single place that imports Flowsint's enricher machinery.

As with ``market_types._base``, there is deliberately no fallback shim: an enricher that
registered into a fake registry would never appear in the API or the UI, and the failure
would be a line on stderr (../docs/02-flowsint-primer.md).
"""

from __future__ import annotations

try:  # pragma: no cover - exercised by the real install, stubbed in tests
    from flowsint_core.core.enricher_base import Enricher
    from flowsint_core.core.logger import Logger
    from flowsint_enrichers.registry import flowsint_enricher
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "market_enrichers requires flowsint_core and flowsint_enrichers from a Flowsint "
        "install (https://github.com/reconurge/flowsint). Install them into the same "
        "environment as the API and the Celery worker — enrichers execute in the worker, "
        "while the API needs them to build schemas. See "
        "../docs/adr/0003-type-registration-strategy.md."
    ) from exc

__all__ = ["Enricher", "Logger", "flowsint_enricher"]
