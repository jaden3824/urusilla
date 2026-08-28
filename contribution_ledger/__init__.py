"""Local, non-financial contribution ledger experiment.

This package deliberately provides no coin, wallet, network, transfer,
approval, redemption, or conversion functionality.
"""

from .ledger import (
    LEDGER_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    ContributionLedger,
    LedgerValidationError,
    canonical_json,
    compute_contribution_id,
    merkle_root,
)

__all__ = [
    "LEDGER_SCHEMA_VERSION",
    "SNAPSHOT_SCHEMA_VERSION",
    "ContributionLedger",
    "LedgerValidationError",
    "canonical_json",
    "compute_contribution_id",
    "merkle_root",
]
