"""Claim-conservative evaluation contract for the Urusilla initial goal.

The default package surface validates externally produced evidence and does not
call models.  The explicitly imported ``study_orchestrator`` diagnostic can run
an injected hybrid adapter and scorer, but creates no adapter or authority and
cannot produce claim-eligible or adoption evidence.
"""

from .contract import (
    FROZEN_METHOD_PATH,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    VerificationError,
    canonical_json,
    load_frozen_method,
    sha256_ref,
    validate_study_plan,
    verifier_bundle_sha256,
)
from .receipt_store import (
    RECEIPT_BUNDLE_SCHEMA,
    RECEIPT_BUNDLE_SCHEMA_V2,
    RECEIPT_BUNDLE_SCHEMA_V3,
    RECEIPT_SCHEMA,
    SCORER_OUTPUT_RECEIPT_SCHEMA,
    USAGE_RECEIPT_SCHEMA_V2,
    USAGE_RECEIPT_SCHEMA_V3,
    ReceiptStore,
    ReceiptValidation,
    receipt_digest,
)


def verify_result(*args, **kwargs):
    """Lazily invoke the verifier without preloading its CLI module."""

    from .verifier import verify_result as implementation

    return implementation(*args, **kwargs)

__all__ = [
    "FROZEN_METHOD_PATH",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "RECEIPT_BUNDLE_SCHEMA",
    "RECEIPT_BUNDLE_SCHEMA_V2",
    "RECEIPT_BUNDLE_SCHEMA_V3",
    "RECEIPT_SCHEMA",
    "SCORER_OUTPUT_RECEIPT_SCHEMA",
    "USAGE_RECEIPT_SCHEMA_V2",
    "USAGE_RECEIPT_SCHEMA_V3",
    "ReceiptStore",
    "ReceiptValidation",
    "VerificationError",
    "canonical_json",
    "load_frozen_method",
    "receipt_digest",
    "sha256_ref",
    "validate_study_plan",
    "verifier_bundle_sha256",
    "verify_result",
]
