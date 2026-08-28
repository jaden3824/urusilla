"""Detached Ed25519 checkpoints for a non-authoritative ledger trial.

This module binds an exact contribution-ledger snapshot to review metadata and
verifies a detached signature against trust inputs pinned out of band by the
caller.  It is deliberately not a blockchain, token, wallet, credit issuer,
claim service, timestamp authority, or authorization mechanism.

``cryptography`` is optional at import time.  Only the explicit signing and
verification operations require it.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from contribution_ledger.ledger import (
    LEDGER_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    ContributionLedger,
    canonical_json,
)


CHECKPOINT_SCHEMA_VERSION = "urusilla-contribution-checkpoint/0.1"
DETACHED_SIGNATURE_SCHEMA_VERSION = (
    "urusilla-contribution-checkpoint-detached-signature/0.1"
)
CHECKPOINT_BOUNDARY = (
    "synthetic-signed-snapshot-not-credit-token-chain-or-effect-authority"
)
SIGNATURE_DOMAIN = b"urusilla:contribution-checkpoint:ed25519:v1\x00"
ALGORITHM = "ed25519"
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_EVENT_COUNT = 2**63 - 1
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")

_SNAPSHOT_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_schema_version",
        "ledger_id",
        "event_count",
        "head_event_id",
        "events_merkle_root",
        "epochs",
        "contributions",
        "awards",
        "corrections",
        "non_financial",
        "transferable",
        "convertible",
    }
)

_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_boundary",
        "ledger_snapshot_canonical_json",
        "ledger_snapshot_sha256",
        "ledger_id",
        "head_event_id",
        "event_count",
        "events_merkle_root",
        "contribution_policy_digest",
        "reviewer_roster_digest",
        "checkpoint_created_at_utc",
        "appeal_deadline_utc",
        "trust_policy_digest",
        "signing_key_id",
        "synthetic_trial",
        "canonical_credit_issued",
        "token_claim_created",
        "transferable",
        "convertible",
        "effect_authorized",
    }
)

_SIGNATURE_FIELDS = frozenset(
    {
        "schema_version",
        "algorithm",
        "key_id",
        "checkpoint_sha256",
        "signature_base64",
    }
)


class CheckpointValidationError(ValueError):
    """A fail-closed checkpoint error with a stable machine reason code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class CheckpointDependencyError(RuntimeError):
    """Raised only when a requested crypto operation lacks its dependency."""


def _fail(code: str, message: str) -> None:
    raise CheckpointValidationError(code, message)


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("invalid_type", f"{path} must be an object")
    return value


def _require_exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], path: str
) -> None:
    actual = set(value)
    if actual != set(expected):
        unknown = sorted(actual - set(expected))
        missing = sorted(set(expected) - actual)
        if unknown:
            _fail("unknown_field", f"{path} has unknown fields: {unknown}")
        _fail("missing_field", f"{path} is missing fields: {missing}")


def _require_digest(value: Any, path: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        _fail("invalid_digest", f"{path} must be 64 lowercase hexadecimal characters")
    return value


def _require_identifier(value: Any, path: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        _fail("invalid_identifier", f"{path} must be a bounded opaque identifier")
    return value


def _require_utc(value: Any, path: str) -> datetime:
    if type(value) is not str:
        _fail("invalid_timestamp", f"{path} must be a UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise CheckpointValidationError(
            "invalid_timestamp",
            f"{path} must use canonical YYYY-MM-DDTHH:MM:SSZ",
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail("invalid_timestamp", f"{path} is not canonical UTC text")
    return parsed


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_json_limits(value: Any, path: str) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            _fail(
                "json_node_limit_exceeded",
                f"{path} exceeds the {MAX_JSON_NODES}-node verification limit",
            )
        if isinstance(item, (dict, list)):
            if depth >= MAX_JSON_DEPTH:
                _fail(
                    "json_nesting_too_deep",
                    f"{path} exceeds the {MAX_JSON_DEPTH}-level verification limit",
                )
            child_count = len(item)
            if nodes + len(stack) + child_count > MAX_JSON_NODES:
                _fail(
                    "json_node_limit_exceeded",
                    f"{path} exceeds the {MAX_JSON_NODES}-node verification limit",
                )
            children = item.values() if isinstance(item, dict) else item
            stack.extend((child, depth + 1) for child in children)


def _strict_canonical_object(text: Any, path: str) -> dict[str, Any]:
    if type(text) is not str or not text:
        _fail("invalid_canonical_json", f"{path} must be non-empty JSON text")
    if len(text) > MAX_SNAPSHOT_BYTES:
        _fail(
            "snapshot_too_large",
            f"{path} exceeds the {MAX_SNAPSHOT_BYTES}-byte verification limit",
        )
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CheckpointValidationError(
            "invalid_canonical_json", f"{path} is not valid UTF-8 text"
        ) from exc
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        _fail(
            "snapshot_too_large",
            f"{path} exceeds the {MAX_SNAPSHOT_BYTES}-byte verification limit",
        )

    def reject_constant(value: str) -> None:
        _fail("invalid_canonical_json", f"{path} contains non-finite number {value}")

    def reject_float(value: str) -> None:
        _fail("invalid_canonical_json", f"{path} contains floating-point number {value}")

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("duplicate_json_key", f"{path} repeats object key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except CheckpointValidationError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise CheckpointValidationError(
            "invalid_canonical_json", f"{path} is invalid JSON"
        ) from exc
    _validate_json_limits(value, path)
    obj = _require_object(value, path)
    try:
        normalized = canonical_json(obj)
    except (ValueError, RecursionError) as exc:
        raise CheckpointValidationError(
            "invalid_canonical_json", f"{path} is outside canonical JSON"
        ) from exc
    if normalized != text:
        _fail("noncanonical_json", f"{path} is not exact canonical JSON")
    return obj


def _validate_snapshot(snapshot: Any, path: str) -> dict[str, Any]:
    value = _require_object(snapshot, path)
    _require_exact_fields(value, _SNAPSHOT_FIELDS, path)
    if value["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        _fail("snapshot_schema_mismatch", f"{path} schema is unsupported")
    if value["ledger_schema_version"] != LEDGER_SCHEMA_VERSION:
        _fail("ledger_schema_mismatch", f"{path} ledger schema is unsupported")
    _require_identifier(value["ledger_id"], f"{path}.ledger_id")
    event_count = value["event_count"]
    if type(event_count) is not int or not 0 <= event_count <= MAX_EVENT_COUNT:
        _fail(
            "invalid_event_count",
            f"{path}.event_count must be from 0 through {MAX_EVENT_COUNT}",
        )
    head = value["head_event_id"]
    if event_count == 0:
        if head is not None:
            _fail("snapshot_head_mismatch", "an empty snapshot cannot have a head")
    else:
        _require_digest(head, f"{path}.head_event_id")
    _require_digest(value["events_merkle_root"], f"{path}.events_merkle_root")
    for field in ("epochs", "contributions", "awards", "corrections"):
        if type(value[field]) is not list:
            _fail("invalid_type", f"{path}.{field} must be an array")
        if len(value[field]) > event_count:
            _fail(
                "snapshot_cardinality_mismatch",
                f"{path}.{field} cannot contain more entries than event_count",
            )
    if value["non_financial"] is not True:
        _fail("authority_boundary", "snapshot must remain explicitly non-financial")
    if value["transferable"] is not False or value["convertible"] is not False:
        _fail("authority_boundary", "snapshot cannot enable transfer or conversion")
    return value


def _validate_checkpoint(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    checkpoint = _require_object(value, "checkpoint")
    _require_exact_fields(checkpoint, _CHECKPOINT_FIELDS, "checkpoint")
    if checkpoint["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        _fail("checkpoint_schema_mismatch", "checkpoint schema is unsupported")
    if checkpoint["evidence_boundary"] != CHECKPOINT_BOUNDARY:
        _fail("authority_boundary", "checkpoint evidence boundary differs")
    snapshot = _strict_canonical_object(
        checkpoint["ledger_snapshot_canonical_json"],
        "checkpoint.ledger_snapshot_canonical_json",
    )
    _validate_snapshot(snapshot, "checkpoint.ledger_snapshot")
    snapshot_sha256 = _require_digest(
        checkpoint["ledger_snapshot_sha256"], "checkpoint.ledger_snapshot_sha256"
    )
    if snapshot_sha256 != _sha256_text(checkpoint["ledger_snapshot_canonical_json"]):
        _fail("snapshot_digest_mismatch", "snapshot bytes do not match their digest")
    if checkpoint["ledger_id"] != snapshot["ledger_id"]:
        _fail("snapshot_header_mismatch", "checkpoint ledger_id differs from snapshot")
    if checkpoint["head_event_id"] != snapshot["head_event_id"]:
        _fail("snapshot_header_mismatch", "checkpoint head differs from snapshot")
    if checkpoint["event_count"] != snapshot["event_count"]:
        _fail("snapshot_header_mismatch", "checkpoint event count differs from snapshot")
    if checkpoint["events_merkle_root"] != snapshot["events_merkle_root"]:
        _fail("snapshot_header_mismatch", "checkpoint Merkle root differs from snapshot")
    _require_digest(
        checkpoint["contribution_policy_digest"],
        "checkpoint.contribution_policy_digest",
    )
    _require_digest(
        checkpoint["reviewer_roster_digest"], "checkpoint.reviewer_roster_digest"
    )
    created = _require_utc(
        checkpoint["checkpoint_created_at_utc"],
        "checkpoint.checkpoint_created_at_utc",
    )
    deadline = _require_utc(
        checkpoint["appeal_deadline_utc"], "checkpoint.appeal_deadline_utc"
    )
    if deadline <= created:
        _fail("invalid_appeal_window", "appeal deadline must follow checkpoint creation")
    _require_digest(checkpoint["trust_policy_digest"], "checkpoint.trust_policy_digest")
    _require_identifier(checkpoint["signing_key_id"], "checkpoint.signing_key_id")
    if checkpoint["synthetic_trial"] is not True:
        _fail("authority_boundary", "checkpoint must remain a synthetic trial")
    for field in (
        "canonical_credit_issued",
        "token_claim_created",
        "transferable",
        "convertible",
        "effect_authorized",
    ):
        if checkpoint[field] is not False:
            _fail("authority_boundary", f"checkpoint cannot promote {field}")
    return checkpoint, snapshot


def _checkpoint_json(value: Any) -> str:
    checkpoint, _snapshot = _validate_checkpoint(value)
    return canonical_json(checkpoint)


def _load_crypto() -> tuple[Any, Any, Any]:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:
        raise CheckpointDependencyError(
            "checkpoint signing and verification require the optional cryptography dependency"
        ) from exc
    return InvalidSignature, Ed25519PrivateKey, Ed25519PublicKey


def build_checkpoint(
    ledger: ContributionLedger,
    *,
    contribution_policy_digest: str,
    reviewer_roster_digest: str,
    checkpoint_created_at_utc: str,
    appeal_deadline_utc: str,
    trust_policy_digest: str,
    signing_key_id: str,
) -> dict[str, Any]:
    """Build a synthetic checkpoint over the ledger's replay-verified snapshot."""

    if type(ledger) is not ContributionLedger:
        _fail("invalid_ledger", "ledger must be an exact ContributionLedger instance")
    ledger.verify()
    snapshot = ledger.export_snapshot()
    _validate_snapshot(snapshot, "ledger_snapshot")
    snapshot_json = canonical_json(snapshot)
    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "evidence_boundary": CHECKPOINT_BOUNDARY,
        "ledger_snapshot_canonical_json": snapshot_json,
        "ledger_snapshot_sha256": _sha256_text(snapshot_json),
        "ledger_id": snapshot["ledger_id"],
        "head_event_id": snapshot["head_event_id"],
        "event_count": snapshot["event_count"],
        "events_merkle_root": snapshot["events_merkle_root"],
        "contribution_policy_digest": contribution_policy_digest,
        "reviewer_roster_digest": reviewer_roster_digest,
        "checkpoint_created_at_utc": checkpoint_created_at_utc,
        "appeal_deadline_utc": appeal_deadline_utc,
        "trust_policy_digest": trust_policy_digest,
        "signing_key_id": signing_key_id,
        "synthetic_trial": True,
        "canonical_credit_issued": False,
        "token_claim_created": False,
        "transferable": False,
        "convertible": False,
        "effect_authorized": False,
    }
    validated, _snapshot = _validate_checkpoint(checkpoint)
    return copy.deepcopy(validated)


def checkpoint_canonical_json(checkpoint_value: Mapping[str, Any]) -> str:
    """Return the exact bytes (as text) covered by the detached signature."""

    return _checkpoint_json(checkpoint_value)


def checkpoint_sha256(checkpoint_value: Mapping[str, Any]) -> str:
    """Return SHA-256 over the exact canonical checkpoint JSON bytes."""

    return _sha256_text(_checkpoint_json(checkpoint_value))


def checkpoint_signing_message(checkpoint_value: Mapping[str, Any]) -> bytes:
    """Return domain-separated Ed25519 input for an out-of-band signer."""

    return SIGNATURE_DOMAIN + _checkpoint_json(checkpoint_value).encode("utf-8")


def sign_checkpoint(
    checkpoint_value: Mapping[str, Any], *, private_key_bytes: bytes
) -> dict[str, Any]:
    """Create a detached synthetic signature; no private key enters the artifact."""

    _invalid_signature, Ed25519PrivateKey, _public = _load_crypto()
    if type(private_key_bytes) is not bytes or len(private_key_bytes) != 32:
        _fail("invalid_private_key", "private_key_bytes must be exactly 32 bytes")
    message = checkpoint_signing_message(checkpoint_value)
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    except ValueError as exc:
        raise CheckpointValidationError(
            "invalid_private_key", "private_key_bytes are not a valid Ed25519 seed"
        ) from exc
    signature = private_key.sign(message)
    checkpoint, _snapshot = _validate_checkpoint(checkpoint_value)
    return {
        "schema_version": DETACHED_SIGNATURE_SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "key_id": checkpoint["signing_key_id"],
        "checkpoint_sha256": checkpoint_sha256(checkpoint),
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def _validate_signature(value: Any) -> tuple[dict[str, Any], bytes]:
    signature = _require_object(value, "detached_signature")
    _require_exact_fields(signature, _SIGNATURE_FIELDS, "detached_signature")
    if signature["schema_version"] != DETACHED_SIGNATURE_SCHEMA_VERSION:
        _fail("signature_schema_mismatch", "detached signature schema is unsupported")
    if signature["algorithm"] != ALGORITHM:
        _fail("signature_algorithm_mismatch", "only Ed25519 is supported")
    _require_identifier(signature["key_id"], "detached_signature.key_id")
    _require_digest(
        signature["checkpoint_sha256"], "detached_signature.checkpoint_sha256"
    )
    encoded = signature["signature_base64"]
    if type(encoded) is not str or not encoded:
        _fail("malformed_signature", "signature must be canonical Base64 text")
    if len(encoded) != 88:
        _fail("malformed_signature", "signature must be canonical 64-byte Base64")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise CheckpointValidationError(
            "malformed_signature", "signature is not valid Base64"
        ) from exc
    if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != encoded:
        _fail("malformed_signature", "signature must be canonical 64-byte Base64")
    return signature, raw


@dataclass(frozen=True)
class CheckpointValidation:
    checkpoint_sha256: str
    ledger_snapshot_sha256: str
    signing_key_id: str
    trust_policy_digest: str
    contribution_policy_digest: str
    reviewer_roster_digest: str
    checkpoint_created_at_utc: str
    appeal_deadline_utc: str

    def to_object(self) -> dict[str, Any]:
        """Return an explicit zero-authority verification result."""

        return {
            "schema_version": "urusilla-contribution-checkpoint-validation/0.1",
            "evidence_boundary": CHECKPOINT_BOUNDARY,
            "synthetic_trial": True,
            "signature_verified": True,
            "snapshot_binding_verified": True,
            "snapshot_bytes_matched": True,
            "snapshot_semantics_verified": False,
            "ledger_replay_verified_by_verifier": False,
            "separate_trust_policy_pin_matched": True,
            "signing_key_id_pin_matched": True,
            "review_metadata_pins_matched": True,
            "checkpoint_sha256": self.checkpoint_sha256,
            "ledger_snapshot_sha256": self.ledger_snapshot_sha256,
            "signing_key_id": self.signing_key_id,
            "trust_policy_digest": self.trust_policy_digest,
            "contribution_policy_digest": self.contribution_policy_digest,
            "reviewer_roster_digest": self.reviewer_roster_digest,
            "checkpoint_created_at_utc": self.checkpoint_created_at_utc,
            "appeal_deadline_utc": self.appeal_deadline_utc,
            "canonical_credit_issued": False,
            "token_claim_created": False,
            "transferable": False,
            "convertible": False,
            "effect_authorized": False,
            "onchain_anchor_verified": False,
            "external_timestamp_verified": False,
            "real_world_identity_verified": False,
            "limitations": [
                (
                    "the caller must obtain the trust-policy digest, key id, "
                    "and public key out of band"
                ),
                (
                    "the caller must independently derive the expected ledger "
                    "snapshot and pin the review metadata"
                ),
                (
                    "the signature proves control of a key over exact bytes, "
                    "not real-world identity or reviewer independence"
                ),
                (
                    "snapshot byte equality does not validate nested ledger "
                    "semantics or replay the event log"
                ),
                "the appeal deadline is signed text, not an externally anchored timestamp",
                "this trial issues no canonical credit or token claim and authorizes no effect",
            ],
        }


def verify_checkpoint(
    checkpoint_value: Mapping[str, Any],
    detached_signature_value: Mapping[str, Any],
    *,
    expected_snapshot_value: Mapping[str, Any],
    expected_trust_policy_digest: str,
    expected_signing_key_id: str,
    expected_contribution_policy_digest: str,
    expected_reviewer_roster_digest: str,
    expected_checkpoint_created_at_utc: str,
    expected_appeal_deadline_utc: str,
    trusted_public_key_bytes: bytes,
) -> CheckpointValidation:
    """Verify exact bytes using only caller-pinned trust inputs.

    The detached artifact has no public-key field.  Supplying a replacement key
    inside either artifact is therefore rejected as an unknown field rather
    than becoming a new trust root.
    """

    checkpoint, embedded_snapshot = _validate_checkpoint(checkpoint_value)
    signature, signature_bytes = _validate_signature(detached_signature_value)
    expected_snapshot = _validate_snapshot(
        _require_object(expected_snapshot_value, "expected_snapshot"),
        "expected_snapshot",
    )
    if canonical_json(expected_snapshot) != canonical_json(embedded_snapshot):
        _fail("snapshot_mismatch", "caller-expected snapshot differs from checkpoint")

    trust_pin = _require_digest(
        expected_trust_policy_digest, "expected_trust_policy_digest"
    )
    key_id_pin = _require_identifier(
        expected_signing_key_id, "expected_signing_key_id"
    )
    contribution_policy_pin = _require_digest(
        expected_contribution_policy_digest,
        "expected_contribution_policy_digest",
    )
    reviewer_roster_pin = _require_digest(
        expected_reviewer_roster_digest,
        "expected_reviewer_roster_digest",
    )
    _require_utc(
        expected_checkpoint_created_at_utc,
        "expected_checkpoint_created_at_utc",
    )
    _require_utc(expected_appeal_deadline_utc, "expected_appeal_deadline_utc")
    if checkpoint["trust_policy_digest"] != trust_pin:
        _fail("trust_policy_pin_mismatch", "checkpoint selected another trust policy")
    if checkpoint["signing_key_id"] != key_id_pin:
        _fail("key_id_pin_mismatch", "checkpoint selected another signing key")
    if signature["key_id"] != key_id_pin:
        _fail("signature_key_id_mismatch", "detached signature names another key")
    expected_checkpoint_sha256 = checkpoint_sha256(checkpoint)
    if signature["checkpoint_sha256"] != expected_checkpoint_sha256:
        _fail("checkpoint_digest_mismatch", "signature references another checkpoint")
    if type(trusted_public_key_bytes) is not bytes or len(trusted_public_key_bytes) != 32:
        _fail("invalid_public_key", "trusted_public_key_bytes must be exactly 32 bytes")

    InvalidSignature, _private, Ed25519PublicKey = _load_crypto()
    try:
        public_key = Ed25519PublicKey.from_public_bytes(trusted_public_key_bytes)
        public_key.verify(signature_bytes, checkpoint_signing_message(checkpoint))
    except InvalidSignature as exc:
        raise CheckpointValidationError(
            "invalid_signature", "detached checkpoint signature is invalid"
        ) from exc
    except ValueError as exc:
        raise CheckpointValidationError(
            "invalid_public_key", "trusted public key is not valid Ed25519"
        ) from exc

    if checkpoint["contribution_policy_digest"] != contribution_policy_pin:
        _fail(
            "contribution_policy_pin_mismatch",
            "checkpoint selected another contribution policy",
        )
    if checkpoint["reviewer_roster_digest"] != reviewer_roster_pin:
        _fail(
            "reviewer_roster_pin_mismatch",
            "checkpoint selected another reviewer roster",
        )
    if checkpoint["checkpoint_created_at_utc"] != expected_checkpoint_created_at_utc:
        _fail(
            "checkpoint_time_pin_mismatch",
            "checkpoint creation time differs from the caller pin",
        )
    if checkpoint["appeal_deadline_utc"] != expected_appeal_deadline_utc:
        _fail(
            "appeal_deadline_pin_mismatch",
            "appeal deadline differs from the caller pin",
        )

    return CheckpointValidation(
        checkpoint_sha256=expected_checkpoint_sha256,
        ledger_snapshot_sha256=checkpoint["ledger_snapshot_sha256"],
        signing_key_id=key_id_pin,
        trust_policy_digest=trust_pin,
        contribution_policy_digest=contribution_policy_pin,
        reviewer_roster_digest=reviewer_roster_pin,
        checkpoint_created_at_utc=checkpoint["checkpoint_created_at_utc"],
        appeal_deadline_utc=checkpoint["appeal_deadline_utc"],
    )


__all__ = [
    "ALGORITHM",
    "CHECKPOINT_BOUNDARY",
    "CHECKPOINT_SCHEMA_VERSION",
    "DETACHED_SIGNATURE_SCHEMA_VERSION",
    "MAX_SNAPSHOT_BYTES",
    "CheckpointDependencyError",
    "CheckpointValidation",
    "CheckpointValidationError",
    "build_checkpoint",
    "checkpoint_canonical_json",
    "checkpoint_sha256",
    "checkpoint_signing_message",
    "sign_checkpoint",
    "verify_checkpoint",
]
