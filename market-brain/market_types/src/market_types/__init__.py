"""Market entity types for Flowsint.

Issuers, securities, people, filings, insider transactions and financial facts, as
Pydantic models registered into Flowsint's type registry. The ontology, merge keys and
relationship labels are specified in docs/03-ontology.md; the decisions behind them are
in docs/adr/.

Importing this package registers every type via ``@flowsint_type``. How that import is
guaranteed to happen inside a running Flowsint is the subject of
docs/adr/0003-type-registration-strategy.md — upstream's auto-discovery walks only its
own package, so an out-of-tree package must be imported explicitly.
"""

from __future__ import annotations

from pydantic import BaseModel

from .fact import Fact, make_fact_id
from .filing import FORM_MEANINGS, Filing
from .identifiers import (
    IdentifierError,
    accession_compact,
    cusip_check_digit,
    is_valid_cusip,
    is_valid_figi,
    is_valid_isin,
    is_valid_lei,
    is_valid_mic,
    isin_check_digit,
    normalize_accession,
    normalize_cik,
)
from .insider_transaction import (
    OPEN_MARKET_CODES,
    TRANSACTION_CODES,
    InsiderTransaction,
)
from .issuer import Issuer
from .keys import build_key, is_authoritative, is_key, parse_key, slugify
from .person import Person
from .provenance import (
    DEFAULT_CONFIDENCE,
    Provenance,
    default_confidence,
    provenance,
)
from .registry import load_market_types, market_type_names
from .security import Security

__version__ = "0.1.0"

#: The entity types this package registers, in dependency-ish reading order.
MARKET_TYPES: tuple[type[BaseModel], ...] = (
    Issuer,
    Security,
    Person,
    Filing,
    InsiderTransaction,
    Fact,
)

__all__ = [
    "DEFAULT_CONFIDENCE",
    "FORM_MEANINGS",
    "MARKET_TYPES",
    "OPEN_MARKET_CODES",
    "TRANSACTION_CODES",
    "Fact",
    "Filing",
    "IdentifierError",
    "InsiderTransaction",
    "Issuer",
    "Person",
    "Provenance",
    "Security",
    "accession_compact",
    "build_key",
    "cusip_check_digit",
    "default_confidence",
    "is_authoritative",
    "is_key",
    "is_valid_cusip",
    "is_valid_figi",
    "is_valid_isin",
    "is_valid_lei",
    "is_valid_mic",
    "isin_check_digit",
    "load_market_types",
    "make_fact_id",
    "market_type_names",
    "normalize_accession",
    "normalize_cik",
    "parse_key",
    "provenance",
    "slugify",
]
