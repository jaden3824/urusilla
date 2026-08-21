"""Claim-conservative evaluation contract for the Urusilla initial goal.

The package validates externally produced evidence.  It does not call models,
run the hybrid runtime, install code at a partner, or create adoption evidence.
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


def verify_result(*args, **kwargs):
    """Lazily invoke the verifier without preloading its CLI module."""

    from .verifier import verify_result as implementation

    return implementation(*args, **kwargs)

__all__ = [
    "FROZEN_METHOD_PATH",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "VerificationError",
    "canonical_json",
    "load_frozen_method",
    "sha256_ref",
    "validate_study_plan",
    "verifier_bundle_sha256",
    "verify_result",
]
