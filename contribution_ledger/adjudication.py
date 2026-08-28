"""Synthetic multi-reviewer adjudication with an explicit zero-authority boundary.

The caller, not the artifact, supplies the expected digest of an exact reviewer
policy.  Valid Ed25519 signatures can establish only that a quorum of keys in
that pinned policy approved exact canonical statement bytes.  They do not issue
credit, create a token or checkpoint, authorize an effect, prove real-world
identity, or deploy anything on a chain.

The optional ``cryptography`` package is imported lazily by signing and
verification operations.  Policy construction, canonicalization, and digest
helpers remain importable without it.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from contribution_ledger.ledger import (
    LEDGER_SCHEMA_VERSION,
    ContributionLedger,
    canonical_json,
)


POLICY_SCHEMA_VERSION = "urusilla-contribution-adjudication-policy/0.1"
STATEMENT_SCHEMA_VERSION = "urusilla-contribution-adjudication-statement/0.1"
SIGNATURE_SCHEMA_VERSION = "urusilla-contribution-adjudication-signature/0.1"
VALIDATION_SCHEMA_VERSION = "urusilla-contribution-adjudication-validation/0.1"
ADJUDICATION_BOUNDARY = (
    "synthetic-quorum-evidence-not-credit-token-checkpoint-or-effect-authority"
)
ALGORITHM = "ed25519"
SIGNATURE_DOMAIN = b"urusilla:contribution-adjudication:ed25519:v1\x00"
ROSTER_DOMAIN = b"urusilla:contribution-adjudication:reviewer-roster:v1\x00"
REGISTRATION_EVIDENCE_DOMAIN = (
    b"urusilla:contribution-adjudication:registration-evidence:v1\x00"
)

MAX_POLICY_BYTES = 256 * 1024
MAX_STATEMENT_BYTES = 64 * 1024
MAX_SIGNATURE_BUNDLE_BYTES = 256 * 1024
MAX_REVIEWERS = 64
MAX_SIGNATURES = 64
MAX_APPEAL_WINDOW_SECONDS = 90 * 24 * 60 * 60
MIN_APPEAL_WINDOW_SECONDS = 60 * 60
MAX_POINTS = 2**63 - 1
MAX_TOP_LEVEL_FIELDS = 64
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 10_000
PUBLIC_KEY_BASE64_LENGTH = 44
SIGNATURE_BASE64_LENGTH = 88

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_REASON_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "project_id",
        "contribution_policy_digest",
        "created_at_utc",
        "valid_from_utc",
        "valid_until_utc",
        "minimum_approvals",
        "minimum_distinct_organizations",
        "appeal_window_seconds",
        "reviewers",
    }
)
_REVIEWER_FIELDS = frozenset(
    {
        "reviewer_ref",
        "reviewer_subject_ref",
        "organization_id",
        "key_id",
        "algorithm",
        "public_key_base64",
        "valid_from_utc",
        "valid_until_utc",
        "revoked",
    }
)
_STATEMENT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_boundary",
        "policy_digest",
        "reviewer_roster_digest",
        "project_id",
        "ledger_id",
        "epoch_id",
        "contribution_id",
        "registration_event_id",
        "subject_ref",
        "contribution_class",
        "points",
        "evidence_digest",
        "reason_code",
        "decision",
        "decided_at_utc",
        "appeal_deadline_utc",
        "synthetic_trial",
        "canonical_credit_issued",
        "token_issued",
        "token_claim_created",
        "checkpoint_created",
        "canonical_checkpoint_created",
        "transferable",
        "convertible",
        "effect_authorized",
    }
)
_SIGNATURE_FIELDS = frozenset(
    {
        "schema_version",
        "algorithm",
        "reviewer_ref",
        "key_id",
        "signed_at_utc",
        "statement_digest",
        "signature_base64",
    }
)
_ZERO_AUTHORITY_FIELDS = (
    "canonical_credit_issued",
    "token_issued",
    "token_claim_created",
    "checkpoint_created",
    "canonical_checkpoint_created",
    "transferable",
    "convertible",
    "effect_authorized",
)
_REGISTRATION_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_id",
        "seq",
        "prev_event_id",
        "event_type",
        "payload",
        "event_id",
    }
)
_REGISTRATION_PAYLOAD_FIELDS = frozenset(
    {
        "epoch_id",
        "contribution_id",
        "contributor_ref",
        "contribution_class",
        "commit_digest",
        "claim_digest",
        "artifact_digests",
    }
)


class AdjudicationValidationError(ValueError):
    """Fail-closed validation error with a stable machine reason code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class AdjudicationDependencyError(RuntimeError):
    """Raised only when an explicit crypto operation lacks its dependency."""


def _fail(code: str, message: str) -> None:
    raise AdjudicationValidationError(code, message)


def _exact(value: Mapping[str, Any], fields: frozenset[str], path: str) -> None:
    actual = set(value)
    if actual != set(fields):
        unknown = sorted(actual - set(fields))
        missing = sorted(set(fields) - actual)
        if unknown:
            _fail("unknown_field", f"{path} has unknown fields: {unknown}")
        _fail("missing_field", f"{path} is missing fields: {missing}")


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        _fail("invalid_identifier", f"{path} must be a bounded opaque identifier")
    return value


def _digest(value: Any, path: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        _fail("invalid_digest", f"{path} must be 64 lowercase hexadecimal characters")
    return value


def _positive_int(value: Any, path: str, *, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        _fail("invalid_count", f"{path} must be an integer from 1 through {maximum}")
    return value


def _reason(value: Any, path: str) -> str:
    if type(value) is not str or _REASON_RE.fullmatch(value) is None:
        _fail("invalid_reason_code", f"{path} must be a bounded reason code")
    return value


def _utc(value: Any, path: str) -> datetime:
    if type(value) is not str:
        _fail("invalid_timestamp", f"{path} must be a UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise AdjudicationValidationError(
            "invalid_timestamp", f"{path} must use canonical YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail("invalid_timestamp", f"{path} is not canonical UTC text")
    return parsed


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_utf8(value: str, maximum: int, path: str) -> bytes:
    if len(value) > maximum:
        _fail("input_too_large", f"{path} exceeds the {maximum}-byte limit")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AdjudicationValidationError(
            "invalid_json", f"{path} is not valid UTF-8 text"
        ) from exc
    if len(encoded) > maximum:
        _fail("input_too_large", f"{path} exceeds the {maximum}-byte limit")
    return encoded


def _validate_in_memory_limits(value: Any, path: str, maximum_chars: int) -> None:
    """Reject oversized or non-JSON object graphs before copying or encoding."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    characters = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            _fail(
                "json_node_limit_exceeded",
                f"{path} exceeds the {MAX_JSON_NODES}-node verification limit",
            )
        if type(item) is str:
            characters += len(item)
            if characters > maximum_chars:
                _fail("input_too_large", f"{path} exceeds its character budget")
            continue
        if item is None or type(item) in (bool, int):
            continue
        if type(item) is dict:
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
            for key in item:
                if type(key) is not str:
                    _fail("invalid_json_type", f"{path} has a non-string object key")
                characters += len(key)
                if characters > maximum_chars:
                    _fail("input_too_large", f"{path} exceeds its character budget")
            stack.extend((child, depth + 1) for child in item.values())
            continue
        if type(item) is list:
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
            stack.extend((child, depth + 1) for child in item)
            continue
        _fail(
            "invalid_json_type",
            f"{path} contains unsupported type {type(item).__name__}",
        )


def _strict_json(text: str, path: str, maximum: int) -> Any:
    _bounded_utf8(text, maximum, path)

    def reject_constant(value: str) -> None:
        _fail("invalid_json", f"{path} contains non-finite number {value}")

    def reject_float(value: str) -> None:
        _fail("invalid_json", f"{path} contains floating-point number {value}")

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
    except AdjudicationValidationError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise AdjudicationValidationError("invalid_json", f"{path} is invalid JSON") from exc
    _validate_in_memory_limits(value, path, maximum)
    try:
        canonical = canonical_json(value)
    except ValueError as exc:
        raise AdjudicationValidationError(
            "invalid_json", f"{path} contains unsupported JSON data"
        ) from exc
    if canonical != text:
        _fail("noncanonical_json", f"{path} must be exact canonical JSON")
    return value


def _object_input(value: Any, path: str, maximum: int) -> tuple[dict[str, Any], str]:
    if type(value) is str:
        parsed = _strict_json(value, path, maximum)
        if type(parsed) is not dict:
            _fail("invalid_type", f"{path} must be an object")
        return parsed, value
    if type(value) is not dict:
        _fail("invalid_type", f"{path} must be an object or canonical JSON text")
    if len(value) > MAX_TOP_LEVEL_FIELDS:
        _fail("input_count_limit", f"{path} has too many top-level fields")
    _validate_in_memory_limits(value, path, maximum)
    copied = copy.deepcopy(value)
    text = canonical_json(copied)
    _bounded_utf8(text, maximum, path)
    return copied, text


def _list_input(value: Any, path: str, maximum: int) -> tuple[list[Any], str]:
    if type(value) is str:
        parsed = _strict_json(value, path, maximum)
        if type(parsed) is not list:
            _fail("invalid_type", f"{path} must be an array")
        return parsed, value
    if type(value) is not list:
        _fail("invalid_type", f"{path} must be an array or canonical JSON text")
    if len(value) > MAX_SIGNATURES:
        _fail("signature_count_limit", f"{path} exceeds {MAX_SIGNATURES} entries")
    _validate_in_memory_limits(value, path, maximum)
    copied = copy.deepcopy(value)
    text = canonical_json(copied)
    _bounded_utf8(text, maximum, path)
    return copied, text


def _preflight_base64(value: Any, expected_length: int, path: str) -> str:
    if type(value) is not str or len(value) != expected_length:
        _fail(
            "malformed_base64",
            f"{path} must be canonical Base64 text of length {expected_length}",
        )
    return value


def _decode_base64(value: str, raw_length: int, path: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise AdjudicationValidationError(
            "malformed_base64", f"{path} is not valid Base64"
        ) from exc
    if len(raw) != raw_length or base64.b64encode(raw).decode("ascii") != value:
        _fail("malformed_base64", f"{path} is not canonical {raw_length}-byte Base64")
    return raw


def _load_crypto() -> tuple[Any, Any, Any]:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:
        raise AdjudicationDependencyError(
            "adjudication signing and verification require the optional cryptography dependency"
        ) from exc
    return InvalidSignature, Ed25519PrivateKey, Ed25519PublicKey


def _preflight_policy_roster(value: Any) -> None:
    """Bound a dict policy's nested roster before any defensive deepcopy."""

    if type(value) is not list:
        _fail("invalid_type", "adjudication_policy.reviewers must be an exact array")
    if not value or len(value) > MAX_REVIEWERS:
        _fail(
            "reviewer_count_limit",
            f"adjudication_policy.reviewers must contain 1 through {MAX_REVIEWERS} entries",
        )


def _validate_roster(value: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if type(value) is not list:
        _fail("invalid_type", "policy.reviewers must be an array")
    if not value or len(value) > MAX_REVIEWERS:
        _fail(
            "reviewer_count_limit",
            f"policy.reviewers must contain 1 through {MAX_REVIEWERS} entries",
        )

    reviewers: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        path = f"policy.reviewers[{index}]"
        if type(raw) is not dict:
            _fail("invalid_type", f"{path} must be an object")
        _exact(raw, _REVIEWER_FIELDS, path)
        reviewer = copy.deepcopy(raw)
        _identifier(reviewer["reviewer_ref"], f"{path}.reviewer_ref")
        _identifier(
            reviewer["reviewer_subject_ref"],
            f"{path}.reviewer_subject_ref",
        )
        _identifier(reviewer["organization_id"], f"{path}.organization_id")
        _identifier(reviewer["key_id"], f"{path}.key_id")
        if reviewer["algorithm"] != ALGORITHM:
            _fail("unsupported_algorithm", f"{path}.algorithm must be Ed25519")
        _preflight_base64(
            reviewer["public_key_base64"],
            PUBLIC_KEY_BASE64_LENGTH,
            f"{path}.public_key_base64",
        )
        _utc(reviewer["valid_from_utc"], f"{path}.valid_from_utc")
        _utc(reviewer["valid_until_utc"], f"{path}.valid_until_utc")
        if type(reviewer["revoked"]) is not bool:
            _fail("invalid_type", f"{path}.revoked must be boolean")
        reviewers.append(reviewer)

    expected_order = sorted(
        reviewers, key=lambda item: (item["reviewer_ref"], item["key_id"])
    )
    if reviewers != expected_order:
        _fail("noncanonical_roster", "policy.reviewers must use reviewer/key order")

    by_reviewer: dict[str, dict[str, Any]] = {}
    reviewer_subject_refs: set[str] = set()
    key_ids: set[str] = set()
    public_keys: set[bytes] = set()
    for index, reviewer in enumerate(reviewers):
        path = f"policy.reviewers[{index}]"
        reviewer_ref = reviewer["reviewer_ref"]
        reviewer_subject_ref = reviewer["reviewer_subject_ref"]
        key_id = reviewer["key_id"]
        if reviewer_ref in by_reviewer:
            _fail("duplicate_reviewer", "reviewer roster repeats a reviewer")
        if key_id in key_ids:
            _fail("duplicate_key", "reviewer roster repeats a key ID")
        if reviewer_subject_ref in reviewer_subject_refs:
            _fail("duplicate_reviewer_subject", "reviewer roster repeats a subject")
        valid_from = _utc(reviewer["valid_from_utc"], f"{path}.valid_from_utc")
        valid_until = _utc(reviewer["valid_until_utc"], f"{path}.valid_until_utc")
        if valid_from >= valid_until:
            _fail("empty_key_validity", f"{path} key validity is empty")
        public_key = _decode_base64(
            reviewer["public_key_base64"], 32, f"{path}.public_key_base64"
        )
        if public_key in public_keys:
            _fail("duplicate_public_key", "reviewer roster reuses public key bytes")
        key_ids.add(key_id)
        reviewer_subject_refs.add(reviewer_subject_ref)
        public_keys.add(public_key)
        by_reviewer[reviewer_ref] = {
            **reviewer,
            "public_key": public_key,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
    return reviewers, by_reviewer


def reviewer_roster_digest(reviewers_value: Sequence[Mapping[str, Any]]) -> str:
    """Return a domain-separated digest of one exact canonical reviewer roster."""

    if type(reviewers_value) not in (list, tuple):
        _fail("invalid_type", "reviewers_value must be a bounded list or tuple")
    if not reviewers_value or len(reviewers_value) > MAX_REVIEWERS:
        _fail("reviewer_count_limit", "reviewers_value count is outside limits")
    reviewer_list = list(reviewers_value)
    _validate_in_memory_limits(reviewer_list, "reviewers_value", MAX_POLICY_BYTES)
    reviewers = copy.deepcopy(reviewer_list)
    validated, _by_reviewer = _validate_roster(reviewers)
    return hashlib.sha256(
        ROSTER_DOMAIN + canonical_json(validated).encode("utf-8")
    ).hexdigest()


def contribution_registration_evidence_digest(registration_event_value: Any) -> str:
    """Hash one exact contribution-registration event as statement evidence."""

    event, event_json = _object_input(
        registration_event_value,
        "contribution_registration_event",
        MAX_STATEMENT_BYTES,
    )
    _exact(event, _REGISTRATION_EVENT_FIELDS, "contribution_registration_event")
    if event["schema_version"] != LEDGER_SCHEMA_VERSION:
        _fail("ledger_schema_mismatch", "registration event schema is unsupported")
    _identifier(event["ledger_id"], "contribution_registration_event.ledger_id")
    if type(event["seq"]) is not int or event["seq"] < 0:
        _fail("invalid_sequence", "registration event sequence must be non-negative")
    if event["prev_event_id"] is not None:
        _digest(
            event["prev_event_id"],
            "contribution_registration_event.prev_event_id",
        )
    if event["event_type"] != "contribution_registered":
        _fail("wrong_event_type", "evidence must be a contribution registration")
    _digest(event["event_id"], "contribution_registration_event.event_id")
    payload = event["payload"]
    if type(payload) is not dict:
        _fail("invalid_type", "contribution registration payload must be an object")
    _exact(
        payload,
        _REGISTRATION_PAYLOAD_FIELDS,
        "contribution_registration_event.payload",
    )
    _identifier(payload["epoch_id"], "contribution_registration_event.payload.epoch_id")
    _digest(
        payload["contribution_id"],
        "contribution_registration_event.payload.contribution_id",
    )
    _identifier(
        payload["contributor_ref"],
        "contribution_registration_event.payload.contributor_ref",
    )
    _identifier(
        payload["contribution_class"],
        "contribution_registration_event.payload.contribution_class",
    )
    _digest(
        payload["commit_digest"],
        "contribution_registration_event.payload.commit_digest",
    )
    _digest(
        payload["claim_digest"],
        "contribution_registration_event.payload.claim_digest",
    )
    artifacts = payload["artifact_digests"]
    if type(artifacts) is not list or not 1 <= len(artifacts) <= 64:
        _fail("invalid_artifact_digests", "registration must have 1 through 64 artifacts")
    for index, artifact_digest in enumerate(artifacts):
        _digest(
            artifact_digest,
            f"contribution_registration_event.payload.artifact_digests[{index}]",
        )
    if artifacts != sorted(set(artifacts)):
        _fail("noncanonical_artifact_digests", "artifact digests must be sorted and unique")
    return hashlib.sha256(
        REGISTRATION_EVIDENCE_DOMAIN + event_json.encode("utf-8")
    ).hexdigest()


def _validate_policy(
    policy_value: Any, *, expected_policy_digest: str | None = None
) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]], datetime, datetime, datetime]:
    if type(policy_value) is dict and "reviewers" in policy_value:
        _preflight_policy_roster(policy_value["reviewers"])
    policy, policy_json = _object_input(
        policy_value, "adjudication_policy", MAX_POLICY_BYTES
    )
    actual_digest = _sha256_text(policy_json)
    if expected_policy_digest is not None:
        expected = _digest(expected_policy_digest, "expected_policy_digest")
        if actual_digest != expected:
            _fail("policy_pin_mismatch", "policy differs from the caller-pinned digest")
    _exact(policy, _POLICY_FIELDS, "adjudication_policy")
    if policy["schema_version"] != POLICY_SCHEMA_VERSION:
        _fail("policy_schema_mismatch", "adjudication policy schema is unsupported")
    _identifier(policy["policy_id"], "adjudication_policy.policy_id")
    _identifier(policy["project_id"], "adjudication_policy.project_id")
    _digest(
        policy["contribution_policy_digest"],
        "adjudication_policy.contribution_policy_digest",
    )
    created = _utc(policy["created_at_utc"], "adjudication_policy.created_at_utc")
    valid_from = _utc(policy["valid_from_utc"], "adjudication_policy.valid_from_utc")
    valid_until = _utc(policy["valid_until_utc"], "adjudication_policy.valid_until_utc")
    if not created <= valid_from < valid_until:
        _fail("invalid_policy_time", "policy creation and validity interval are inconsistent")
    minimum_approvals = _positive_int(
        policy["minimum_approvals"],
        "adjudication_policy.minimum_approvals",
        maximum=MAX_REVIEWERS,
    )
    minimum_organizations = _positive_int(
        policy["minimum_distinct_organizations"],
        "adjudication_policy.minimum_distinct_organizations",
        maximum=MAX_REVIEWERS,
    )
    appeal_seconds = policy["appeal_window_seconds"]
    if (
        type(appeal_seconds) is not int
        or not MIN_APPEAL_WINDOW_SECONDS
        <= appeal_seconds
        <= MAX_APPEAL_WINDOW_SECONDS
    ):
        _fail("invalid_appeal_window", "policy appeal window is outside bounded limits")
    reviewers, by_reviewer = _validate_roster(policy["reviewers"])
    policy["reviewers"] = reviewers
    if minimum_approvals > len(reviewers):
        _fail("impossible_quorum", "minimum approvals exceed reviewer count")
    organization_count = len({item["organization_id"] for item in reviewers})
    if minimum_organizations > organization_count:
        _fail("impossible_quorum", "minimum organizations exceed roster diversity")
    for reviewer in by_reviewer.values():
        if not (
            valid_from <= reviewer["valid_from"]
            < reviewer["valid_until"]
            <= valid_until
        ):
            _fail("key_policy_time_mismatch", "reviewer key validity leaves policy validity")
    return policy, actual_digest, by_reviewer, created, valid_from, valid_until


def build_adjudication_policy(
    *,
    policy_id: str,
    project_id: str,
    contribution_policy_digest: str,
    created_at_utc: str,
    valid_from_utc: str,
    valid_until_utc: str,
    minimum_approvals: int,
    minimum_distinct_organizations: int,
    appeal_window_seconds: int,
    reviewers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a normalized synthetic policy suitable for out-of-band pinning."""

    if type(reviewers) not in (list, tuple):
        _fail("invalid_type", "reviewers must be a bounded list or tuple")
    if not reviewers or len(reviewers) > MAX_REVIEWERS:
        _fail("reviewer_count_limit", "reviewer count is outside limits")
    for index, item in enumerate(reviewers):
        if type(item) is not dict:
            _fail("invalid_type", f"reviewers[{index}] must be an exact object")
    _validate_in_memory_limits(list(reviewers), "reviewers", MAX_POLICY_BYTES)
    roster = sorted(
        (copy.deepcopy(dict(item)) for item in reviewers),
        key=lambda item: (item.get("reviewer_ref", ""), item.get("key_id", "")),
    )
    policy = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "project_id": project_id,
        "contribution_policy_digest": contribution_policy_digest,
        "created_at_utc": created_at_utc,
        "valid_from_utc": valid_from_utc,
        "valid_until_utc": valid_until_utc,
        "minimum_approvals": minimum_approvals,
        "minimum_distinct_organizations": minimum_distinct_organizations,
        "appeal_window_seconds": appeal_window_seconds,
        "reviewers": roster,
    }
    validated, _digest_value, _reviewers, _created, _from, _until = _validate_policy(
        policy
    )
    return copy.deepcopy(validated)


def adjudication_policy_canonical_json(policy_value: Any) -> str:
    policy, _digest_value, _reviewers, _created, _from, _until = _validate_policy(
        policy_value
    )
    return canonical_json(policy)


def adjudication_policy_digest(policy_value: Any) -> str:
    """Return SHA-256 over the exact canonical policy JSON bytes."""

    _policy, digest_value, _reviewers, _created, _from, _until = _validate_policy(
        policy_value
    )
    return digest_value


def _validate_statement(
    statement_value: Any,
    *,
    policy: Mapping[str, Any],
    policy_digest: str,
) -> tuple[dict[str, Any], str, datetime, datetime]:
    statement, statement_json = _object_input(
        statement_value, "adjudication_statement", MAX_STATEMENT_BYTES
    )
    _exact(statement, _STATEMENT_FIELDS, "adjudication_statement")
    if statement["schema_version"] != STATEMENT_SCHEMA_VERSION:
        _fail("statement_schema_mismatch", "adjudication statement schema is unsupported")
    if statement["evidence_boundary"] != ADJUDICATION_BOUNDARY:
        _fail("authority_boundary", "statement evidence boundary differs")
    if statement["policy_digest"] != policy_digest:
        _fail("statement_policy_mismatch", "statement references another policy")
    _digest(statement["policy_digest"], "adjudication_statement.policy_digest")
    expected_roster_digest = reviewer_roster_digest(policy["reviewers"])
    if statement["reviewer_roster_digest"] != expected_roster_digest:
        _fail("roster_digest_mismatch", "statement references another reviewer roster")
    _digest(
        statement["reviewer_roster_digest"],
        "adjudication_statement.reviewer_roster_digest",
    )
    if statement["project_id"] != policy["project_id"]:
        _fail("project_mismatch", "statement project differs from pinned policy")
    _identifier(statement["project_id"], "adjudication_statement.project_id")
    _identifier(statement["ledger_id"], "adjudication_statement.ledger_id")
    _identifier(statement["epoch_id"], "adjudication_statement.epoch_id")
    _digest(statement["contribution_id"], "adjudication_statement.contribution_id")
    _digest(
        statement["registration_event_id"],
        "adjudication_statement.registration_event_id",
    )
    _identifier(statement["subject_ref"], "adjudication_statement.subject_ref")
    _identifier(
        statement["contribution_class"],
        "adjudication_statement.contribution_class",
    )
    _positive_int(statement["points"], "adjudication_statement.points", maximum=MAX_POINTS)
    _digest(statement["evidence_digest"], "adjudication_statement.evidence_digest")
    _reason(statement["reason_code"], "adjudication_statement.reason_code")
    if statement["decision"] != "approve":
        _fail("unsupported_decision", "synthetic quorum supports only approve decisions")
    decided = _utc(statement["decided_at_utc"], "adjudication_statement.decided_at_utc")
    deadline = _utc(
        statement["appeal_deadline_utc"],
        "adjudication_statement.appeal_deadline_utc",
    )
    policy_created = _utc(policy["created_at_utc"], "adjudication_policy.created_at_utc")
    policy_from = _utc(policy["valid_from_utc"], "adjudication_policy.valid_from_utc")
    policy_until = _utc(policy["valid_until_utc"], "adjudication_policy.valid_until_utc")
    if decided < policy_created or not policy_from <= decided < policy_until:
        _fail("statement_outside_policy_time", "statement decision is outside policy validity")
    try:
        expected_deadline = decided + timedelta(seconds=policy["appeal_window_seconds"])
    except OverflowError as exc:
        raise AdjudicationValidationError(
            "invalid_appeal_window", "appeal deadline overflows supported time"
        ) from exc
    if deadline != expected_deadline:
        _fail("invalid_appeal_window", "statement deadline does not equal policy window")
    if deadline > policy_until:
        _fail("appeal_outside_policy_time", "appeal window extends beyond policy validity")
    if statement["synthetic_trial"] is not True:
        _fail("authority_boundary", "statement must remain explicitly synthetic")
    for field in _ZERO_AUTHORITY_FIELDS:
        if statement[field] is not False:
            _fail("authority_boundary", f"statement cannot promote {field}")
    return statement, _sha256_text(statement_json), decided, deadline


def build_adjudication_statement(
    policy_value: Any,
    *,
    ledger_id: str,
    epoch_id: str,
    contribution_id: str,
    registration_event_id: str,
    subject_ref: str,
    contribution_class: str,
    points: int,
    evidence_digest: str,
    reason_code: str,
    decided_at_utc: str,
) -> dict[str, Any]:
    """Build a zero-authority approval statement and its exact appeal deadline."""

    policy, policy_digest, _reviewers, _created, _from, _until = _validate_policy(
        policy_value
    )
    decided = _utc(decided_at_utc, "decided_at_utc")
    try:
        deadline = decided + timedelta(seconds=policy["appeal_window_seconds"])
    except OverflowError as exc:
        raise AdjudicationValidationError(
            "invalid_appeal_window", "appeal deadline overflows supported time"
        ) from exc
    statement = {
        "schema_version": STATEMENT_SCHEMA_VERSION,
        "evidence_boundary": ADJUDICATION_BOUNDARY,
        "policy_digest": policy_digest,
        "reviewer_roster_digest": reviewer_roster_digest(policy["reviewers"]),
        "project_id": policy["project_id"],
        "ledger_id": ledger_id,
        "epoch_id": epoch_id,
        "contribution_id": contribution_id,
        "registration_event_id": registration_event_id,
        "subject_ref": subject_ref,
        "contribution_class": contribution_class,
        "points": points,
        "evidence_digest": evidence_digest,
        "reason_code": reason_code,
        "decision": "approve",
        "decided_at_utc": decided_at_utc,
        "appeal_deadline_utc": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "synthetic_trial": True,
        "canonical_credit_issued": False,
        "token_issued": False,
        "token_claim_created": False,
        "checkpoint_created": False,
        "canonical_checkpoint_created": False,
        "transferable": False,
        "convertible": False,
        "effect_authorized": False,
    }
    validated, _digest_value, _decided, _deadline = _validate_statement(
        statement, policy=policy, policy_digest=policy_digest
    )
    return copy.deepcopy(validated)


def adjudication_statement_canonical_json(
    policy_value: Any, statement_value: Any
) -> str:
    policy, policy_digest, _reviewers, _created, _from, _until = _validate_policy(
        policy_value
    )
    statement, _digest_value, _decided, _deadline = _validate_statement(
        statement_value, policy=policy, policy_digest=policy_digest
    )
    return canonical_json(statement)


def adjudication_statement_digest(policy_value: Any, statement_value: Any) -> str:
    policy, policy_digest, _reviewers, _created, _from, _until = _validate_policy(
        policy_value
    )
    _statement, digest_value, _decided, _deadline = _validate_statement(
        statement_value, policy=policy, policy_digest=policy_digest
    )
    return digest_value


def _signature_preimage(
    *,
    reviewer_ref: str,
    key_id: str,
    signed_at_utc: str,
    statement_digest: str,
) -> bytes:
    value = {
        "schema_version": SIGNATURE_SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "reviewer_ref": _identifier(reviewer_ref, "signature.reviewer_ref"),
        "key_id": _identifier(key_id, "signature.key_id"),
        "signed_at_utc": signed_at_utc,
        "statement_digest": _digest(statement_digest, "signature.statement_digest"),
    }
    _utc(signed_at_utc, "signature.signed_at_utc")
    return SIGNATURE_DOMAIN + canonical_json(value).encode("utf-8")


def sign_adjudication_review(
    policy_value: Any,
    statement_value: Any,
    *,
    reviewer_ref: str,
    key_id: str,
    signed_at_utc: str,
    private_key_bytes: bytes,
) -> dict[str, Any]:
    """Create one detached synthetic review signature using an in-memory seed."""

    policy, policy_digest, reviewers, _created, policy_from, policy_until = (
        _validate_policy(policy_value)
    )
    statement, statement_digest, decided, deadline = _validate_statement(
        statement_value, policy=policy, policy_digest=policy_digest
    )
    reviewer_ref = _identifier(reviewer_ref, "reviewer_ref")
    key_id = _identifier(key_id, "key_id")
    reviewer = reviewers.get(reviewer_ref)
    if reviewer is None or reviewer["key_id"] != key_id:
        _fail("untrusted_reviewer", "reviewer/key pair is absent from policy")
    if reviewer["reviewer_subject_ref"] == statement["subject_ref"]:
        _fail("self_review", "a contribution subject cannot review its own statement")
    if reviewer["revoked"]:
        _fail("revoked_key", "revoked reviewer keys cannot sign")
    signed_at = _utc(signed_at_utc, "signed_at_utc")
    if not decided <= signed_at <= deadline:
        _fail("signature_outside_appeal_window", "signature time is outside review window")
    if not policy_from <= signed_at < policy_until:
        _fail("signature_outside_policy_time", "signature time is outside policy validity")
    if not reviewer["valid_from"] <= signed_at < reviewer["valid_until"]:
        _fail("key_outside_validity", "reviewer key is not valid at signature time")
    if type(private_key_bytes) is not bytes or len(private_key_bytes) != 32:
        _fail("invalid_private_key", "private_key_bytes must be exactly 32 bytes")
    message = _signature_preimage(
        reviewer_ref=reviewer_ref,
        key_id=key_id,
        signed_at_utc=signed_at_utc,
        statement_digest=statement_digest,
    )
    _invalid, Ed25519PrivateKey, _public = _load_crypto()
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    except ValueError as exc:
        raise AdjudicationValidationError(
            "invalid_private_key", "private key seed is invalid Ed25519 data"
        ) from exc
    signature = private_key.sign(message)
    return {
        "schema_version": SIGNATURE_SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "reviewer_ref": reviewer_ref,
        "key_id": key_id,
        "signed_at_utc": signed_at_utc,
        "statement_digest": statement_digest,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def _signature_entries(value: Any) -> tuple[list[dict[str, Any]], list[bytes]]:
    entries, _json = _list_input(
        value, "adjudication_signatures", MAX_SIGNATURE_BUNDLE_BYTES
    )
    if not entries or len(entries) > MAX_SIGNATURES:
        _fail(
            "signature_count_limit",
            f"signatures must contain 1 through {MAX_SIGNATURES} entries",
        )
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(entries):
        path = f"adjudication_signatures[{index}]"
        if type(raw) is not dict:
            _fail("invalid_type", f"{path} must be an object")
        _exact(raw, _SIGNATURE_FIELDS, path)
        entry = copy.deepcopy(raw)
        if entry["schema_version"] != SIGNATURE_SCHEMA_VERSION:
            _fail("signature_schema_mismatch", f"{path} schema is unsupported")
        if entry["algorithm"] != ALGORITHM:
            _fail("unsupported_algorithm", f"{path} must use Ed25519")
        _identifier(entry["reviewer_ref"], f"{path}.reviewer_ref")
        _identifier(entry["key_id"], f"{path}.key_id")
        _utc(entry["signed_at_utc"], f"{path}.signed_at_utc")
        _digest(entry["statement_digest"], f"{path}.statement_digest")
        _preflight_base64(
            entry["signature_base64"],
            SIGNATURE_BASE64_LENGTH,
            f"{path}.signature_base64",
        )
        normalized.append(entry)

    reviewer_refs: set[str] = set()
    key_ids: set[str] = set()
    for entry in normalized:
        if entry["reviewer_ref"] in reviewer_refs:
            _fail("duplicate_reviewer", "signature bundle repeats a reviewer")
        if entry["key_id"] in key_ids:
            _fail("duplicate_key", "signature bundle repeats a key ID")
        reviewer_refs.add(entry["reviewer_ref"])
        key_ids.add(entry["key_id"])

    raw_signatures: list[bytes] = []
    seen_signatures: set[bytes] = set()
    for index, entry in enumerate(normalized):
        raw = _decode_base64(
            entry["signature_base64"],
            64,
            f"adjudication_signatures[{index}].signature_base64",
        )
        if raw in seen_signatures:
            _fail("duplicate_signature", "signature bytes are duplicated or replayed")
        seen_signatures.add(raw)
        raw_signatures.append(raw)
    return normalized, raw_signatures


@dataclass(frozen=True)
class AdjudicationValidation:
    policy_digest: str
    statement_digest: str
    reviewer_roster_digest: str
    approvals_verified: int
    distinct_policy_organization_labels: int
    appeal_window_open_at_caller_time: bool
    appeal_deadline_utc: str

    def to_object(self) -> dict[str, Any]:
        return {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "evidence_boundary": ADJUDICATION_BOUNDARY,
            "synthetic_trial": True,
            "policy_pin_matched": True,
            "statement_pin_matched": True,
            "statement_binding_verified": True,
            "presented_quorum_signatures_verified": True,
            "pinned_policy_threshold_satisfied": True,
            "signatures_verified": self.approvals_verified,
            "approvals_verified": self.approvals_verified,
            "distinct_policy_organization_labels": self.distinct_policy_organization_labels,
            "policy_digest": self.policy_digest,
            "statement_digest": self.statement_digest,
            "reviewer_roster_digest": self.reviewer_roster_digest,
            "appeal_window_open_at_caller_time": self.appeal_window_open_at_caller_time,
            "appeal_deadline_utc": self.appeal_deadline_utc,
            "canonical_credit_issued": False,
            "token_issued": False,
            "token_claim_created": False,
            "checkpoint_created": False,
            "canonical_checkpoint_created": False,
            "transferable": False,
            "convertible": False,
            "effect_authorized": False,
            "canonical_ledger_verified": False,
            "evidence_truth_verified": False,
            "external_timestamp_verified": False,
            "real_world_identity_verified": False,
            "subject_aliases_resolved": False,
            "conflicts_exhaustively_verified": False,
            "reviewer_independence_beyond_policy_verified": False,
            "limitations": [
                "the caller must pin the exact policy digest out of band",
                "the caller must independently derive and pin the exact expected statement",
                "policy organizations and reviewer identities are assertions, not independently proven facts",
                "exact subject identifiers block direct self-review but do not resolve aliases",
                "signed times and the appeal window have no external timestamp anchor",
                "quorum evidence issues no credit, token, claim, checkpoint, or effect authority",
            ],
        }


@dataclass(frozen=True)
class SyntheticAdjudicatedAward:
    """Exact metadata for one replay-checked, non-authoritative test award."""

    award_event_id: str
    ledger_id: str
    epoch_id: str
    registration_event_id: str
    contribution_id: str
    points: int
    decision_digest: str
    policy_digest: str
    contribution_policy_digest: str
    reviewer_roster_digest: str

    def to_object(self) -> dict[str, Any]:
        return {
            "schema_version": "urusilla-synthetic-adjudicated-award/0.1",
            "evidence_boundary": ADJUDICATION_BOUNDARY,
            "synthetic_trial": True,
            "test_award_event_recorded": True,
            "ledger_replay_verified": True,
            "registration_binding_verified": True,
            "epoch_policy_binding_verified": True,
            "award_event_id": self.award_event_id,
            "ledger_id": self.ledger_id,
            "epoch_id": self.epoch_id,
            "registration_event_id": self.registration_event_id,
            "contribution_id": self.contribution_id,
            "points": self.points,
            "decision_digest": self.decision_digest,
            "policy_digest": self.policy_digest,
            "contribution_policy_digest": self.contribution_policy_digest,
            "reviewer_roster_digest": self.reviewer_roster_digest,
            "canonical_credit_issued": False,
            "token_issued": False,
            "token_claim_created": False,
            "checkpoint_created": False,
            "canonical_checkpoint_created": False,
            "transferable": False,
            "convertible": False,
            "effect_authorized": False,
            "canonical_ledger_verified": False,
        }


def verify_adjudication(
    policy_value: Any,
    statement_value: Any,
    signatures_value: Any,
    *,
    expected_policy_digest: str,
    expected_statement_value: Any,
    verification_time_utc: str,
) -> AdjudicationValidation:
    """Verify a quorum under caller-pinned policy and statement bytes."""

    policy, policy_digest, reviewers, policy_created, policy_from, policy_until = (
        _validate_policy(
            policy_value, expected_policy_digest=expected_policy_digest
        )
    )
    statement, statement_digest, decided, deadline = _validate_statement(
        statement_value, policy=policy, policy_digest=policy_digest
    )
    expected_statement, expected_statement_digest, _expected_decided, _expected_deadline = (
        _validate_statement(
            expected_statement_value,
            policy=policy,
            policy_digest=policy_digest,
        )
    )
    if (
        canonical_json(statement) != canonical_json(expected_statement)
        or statement_digest != expected_statement_digest
    ):
        _fail(
            "statement_pin_mismatch",
            "submitted statement differs from caller-pinned expected statement",
        )
    verification_time = _utc(verification_time_utc, "verification_time_utc")
    if verification_time < policy_created or verification_time < decided:
        _fail("verification_time_precedes_evidence", "verification time precedes policy or statement")
    if not policy_from <= verification_time < policy_until:
        _fail(
            "verification_outside_policy_time",
            "verification time is outside pinned policy validity",
        )
    entries, signature_bytes = _signature_entries(signatures_value)
    if len(entries) < policy["minimum_approvals"]:
        _fail("insufficient_approvals", "valid signature candidates are below policy minimum")

    organizations: set[str] = set()
    prepared: list[tuple[dict[str, Any], dict[str, Any], bytes, bytes]] = []
    for entry, raw_signature in zip(entries, signature_bytes, strict=True):
        reviewer = reviewers.get(entry["reviewer_ref"])
        if reviewer is None or reviewer["key_id"] != entry["key_id"]:
            _fail("untrusted_reviewer", "signature reviewer/key pair is absent from policy")
        if reviewer["reviewer_subject_ref"] == statement["subject_ref"]:
            _fail("self_review", "a contribution subject cannot review its own statement")
        if reviewer["revoked"]:
            _fail("revoked_key", "revoked reviewer keys cannot approve")
        if entry["statement_digest"] != statement_digest:
            _fail("statement_digest_mismatch", "signature references another statement")
        signed_at = _utc(entry["signed_at_utc"], "signature.signed_at_utc")
        if signed_at > verification_time:
            _fail("signature_from_future", "signature time is later than verification time")
        if not decided <= signed_at <= deadline:
            _fail("signature_outside_appeal_window", "signature time is outside review window")
        if not policy_from <= signed_at < policy_until:
            _fail("signature_outside_policy_time", "signature time is outside policy validity")
        if not reviewer["valid_from"] <= signed_at < reviewer["valid_until"]:
            _fail("key_outside_validity", "reviewer key is expired or not yet valid")
        if not reviewer["valid_from"] <= verification_time < reviewer["valid_until"]:
            _fail(
                "key_not_current_at_verification",
                "reviewer key is not valid at caller verification time",
            )
        message = _signature_preimage(
            reviewer_ref=entry["reviewer_ref"],
            key_id=entry["key_id"],
            signed_at_utc=entry["signed_at_utc"],
            statement_digest=statement_digest,
        )
        organizations.add(reviewer["organization_id"])
        prepared.append((entry, reviewer, raw_signature, message))

    if len(organizations) < policy["minimum_distinct_organizations"]:
        _fail("insufficient_organizations", "approval quorum lacks organization diversity")

    InvalidSignature, _private, Ed25519PublicKey = _load_crypto()
    for _entry, reviewer, raw_signature, message in prepared:
        try:
            key = Ed25519PublicKey.from_public_bytes(reviewer["public_key"])
            key.verify(raw_signature, message)
        except InvalidSignature as exc:
            raise AdjudicationValidationError(
                "invalid_signature", "review signature is invalid"
            ) from exc
        except ValueError as exc:
            raise AdjudicationValidationError(
                "invalid_public_key", "reviewer public key is invalid Ed25519 data"
            ) from exc

    return AdjudicationValidation(
        policy_digest=policy_digest,
        statement_digest=statement_digest,
        reviewer_roster_digest=statement["reviewer_roster_digest"],
        approvals_verified=len(prepared),
        distinct_policy_organization_labels=len(organizations),
        appeal_window_open_at_caller_time=verification_time <= deadline,
        appeal_deadline_utc=statement["appeal_deadline_utc"],
    )


def record_synthetic_adjudicated_award(
    ledger: ContributionLedger,
    policy_value: Any,
    statement_value: Any,
    signatures_value: Any,
    *,
    expected_policy_digest: str,
    expected_statement_value: Any,
    verification_time_utc: str,
) -> SyntheticAdjudicatedAward:
    """Verify all bindings and append exactly one non-authoritative test award."""

    if type(ledger) is not ContributionLedger:
        _fail("invalid_ledger", "ledger must be an exact ContributionLedger instance")

    policy, policy_digest, _reviewers, _created, _from, _until = _validate_policy(
        policy_value,
        expected_policy_digest=expected_policy_digest,
    )
    policy_json = canonical_json(policy)
    statement, statement_digest, _decided, _deadline = _validate_statement(
        statement_value,
        policy=policy,
        policy_digest=policy_digest,
    )
    statement_json = canonical_json(statement)
    expected_statement, expected_statement_digest, _expected_decided, _expected_deadline = (
        _validate_statement(
            expected_statement_value,
            policy=policy,
            policy_digest=policy_digest,
        )
    )
    expected_statement_json = canonical_json(expected_statement)
    if (
        statement_json != expected_statement_json
        or statement_digest != expected_statement_digest
    ):
        _fail(
            "statement_pin_mismatch",
            "submitted statement differs from caller-pinned expected statement",
        )

    entries, _signature_bytes = _signature_entries(signatures_value)
    signatures_json = canonical_json(entries)

    ledger.verify()
    if ledger.ledger_id != statement["ledger_id"]:
        _fail("ledger_binding_mismatch", "statement names another ledger")
    events = ledger.events
    registration = next(
        (
            event
            for event in events
            if event["event_id"] == statement["registration_event_id"]
        ),
        None,
    )
    if registration is None or registration["event_type"] != "contribution_registered":
        _fail(
            "registration_binding_mismatch",
            "statement registration event is absent or has another type",
        )
    registration_payload = registration["payload"]
    for statement_field, payload_field in (
        ("epoch_id", "epoch_id"),
        ("contribution_id", "contribution_id"),
        ("subject_ref", "contributor_ref"),
        ("contribution_class", "contribution_class"),
    ):
        if statement[statement_field] != registration_payload[payload_field]:
            _fail(
                "registration_binding_mismatch",
                f"statement {statement_field} differs from registration",
            )
    if statement["evidence_digest"] != contribution_registration_evidence_digest(
        registration
    ):
        _fail(
            "registration_evidence_mismatch",
            "statement evidence digest differs from the exact registration event",
        )

    epoch_event = next(
        (
            event
            for event in events
            if event["event_type"] == "epoch_opened"
            and event["payload"]["epoch_id"] == statement["epoch_id"]
        ),
        None,
    )
    if epoch_event is None:
        _fail("epoch_binding_mismatch", "statement epoch is not open in the ledger")
    if (
        epoch_event["payload"]["policy_digest"]
        != policy["contribution_policy_digest"]
    ):
        _fail(
            "epoch_policy_binding_mismatch",
            "ledger epoch and adjudication contribution policies differ",
        )

    validation = verify_adjudication(
        policy_json,
        statement_json,
        signatures_json,
        expected_policy_digest=policy_digest,
        expected_statement_value=expected_statement_json,
        verification_time_utc=verification_time_utc,
    )
    award_event = ledger.grant_award(
        epoch_id=statement["epoch_id"],
        contribution_id=statement["contribution_id"],
        points=statement["points"],
        decision_digest=validation.statement_digest,
    )
    ledger.verify()
    return SyntheticAdjudicatedAward(
        award_event_id=award_event["event_id"],
        ledger_id=ledger.ledger_id,
        epoch_id=statement["epoch_id"],
        registration_event_id=statement["registration_event_id"],
        contribution_id=statement["contribution_id"],
        points=statement["points"],
        decision_digest=validation.statement_digest,
        policy_digest=validation.policy_digest,
        contribution_policy_digest=policy["contribution_policy_digest"],
        reviewer_roster_digest=validation.reviewer_roster_digest,
    )


__all__ = [
    "ADJUDICATION_BOUNDARY",
    "ALGORITHM",
    "MAX_POLICY_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_JSON_NODES",
    "MAX_REVIEWERS",
    "MAX_SIGNATURES",
    "MAX_SIGNATURE_BUNDLE_BYTES",
    "MAX_STATEMENT_BYTES",
    "POLICY_SCHEMA_VERSION",
    "SIGNATURE_SCHEMA_VERSION",
    "STATEMENT_SCHEMA_VERSION",
    "AdjudicationDependencyError",
    "AdjudicationValidation",
    "AdjudicationValidationError",
    "SyntheticAdjudicatedAward",
    "adjudication_policy_canonical_json",
    "adjudication_policy_digest",
    "adjudication_statement_canonical_json",
    "adjudication_statement_digest",
    "build_adjudication_policy",
    "build_adjudication_statement",
    "contribution_registration_evidence_digest",
    "record_synthetic_adjudicated_award",
    "reviewer_roster_digest",
    "sign_adjudication_review",
    "verify_adjudication",
]
