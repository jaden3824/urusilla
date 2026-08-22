#!/usr/bin/env python3
"""Offline verifier for the read-only Urusilla evidence-log epoch 1.

This module deliberately has no network, signing, or write path.  It validates
the bounded ``quick_60s`` event profile, the linear hash chain, the empty or
populated checkpoint, and the discovery document using only the Python
standard library.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn


EVENT_SCHEMA = "urusilla-evidence-log-quick60-event/1"
LOG_SCHEMA = "urusilla-evidence-log-quick60/1"
CHECKPOINT_SCHEMA = "urusilla-evidence-log-quick60-checkpoint/1"
DISCOVERY_SCHEMA = "urusilla-evidence-log-quick60-discovery/1"
LOG_ID = "urusilla-github-evidence-log"
QUICK_60S_SHA256 = (
    "sha256:da39f621274bb054797d39536a39b671b26344c5082887ee48a4c3556ccac2e5"
)
EMPTY_SHA256 = "sha256:" + hashlib.sha256(b"").hexdigest()
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
RFC3339_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
IMMUTABLE_CHALLENGE_RE = re.compile(
    r"https://raw\.githubusercontent\.com/jaden3824/urusilla/"
    r"[0-9a-f]{40}/interop_lab/challenges/quick_60s\.json\Z"
)

MAX_DOCUMENT_BYTES = 1_000_000
MAX_RECORDS = 10_000
MAX_DEPTH = 32
MAX_STRING = 8_192


class VerificationError(ValueError):
    """One deterministic validation failure with a stable public code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> NoReturn:
    raise VerificationError(code, detail)


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate-key", f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _reject_float(value: str) -> NoReturn:
    _fail("non-integer-number", f"floating-point number is forbidden: {value}")


def load_json(path: Path) -> Any:
    """Load one bounded JSON document without duplicate keys or floats."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        _fail("read-error", f"{path}: {exc}")
    if len(raw) > MAX_DOCUMENT_BYTES:
        _fail("document-too-large", f"{path} exceeds {MAX_DOCUMENT_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail("invalid-utf8", f"{path}: {exc}")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_float=_reject_float,
            parse_constant=lambda item: _fail(
                "non-finite-number", f"JSON constant is forbidden: {item}"
            ),
        )
    except VerificationError:
        raise
    except json.JSONDecodeError as exc:
        _fail("invalid-json", f"{path}: {exc}")
    _check_json_domain(value)
    return value


def _check_json_domain(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        _fail("nesting-too-deep", f"JSON depth exceeds {MAX_DEPTH}")
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            _fail("string-too-long", f"string exceeds {MAX_STRING} characters")
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            _fail("invalid-unicode", "unpaired UTF-16 surrogate is forbidden")
    elif isinstance(value, list):
        for item in value:
            _check_json_domain(item, depth + 1)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_json_domain(key, depth + 1)
            _check_json_domain(item, depth + 1)
    elif value is None or isinstance(value, (bool, int)):
        return
    else:
        _fail("unsupported-json-value", f"unsupported JSON value {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 for the schema's integer-only JSON domain.

    All object keys in this profile are fixed ASCII schema members.  Therefore
    Python's Unicode code-point key order is identical to RFC 8785's UTF-16 key
    order for every accepted object.  Floats and surrogate code points are
    rejected before this function is called.
    """

    _check_json_domain(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def object_digest(value: dict[str, Any], digest_field: str) -> str:
    if digest_field not in value:
        _fail("missing-digest-field", f"missing {digest_field}")
    preimage = {key: item for key, item in value.items() if key != digest_field}
    return "sha256:" + hashlib.sha256(canonical_bytes(preimage)).hexdigest()


def _expect_exact_keys(value: Any, keys: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("wrong-type", f"{context} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        _fail("wrong-fields", f"{context} missing={missing} extra={extra}")
    return value


def _expect_string(value: Any, context: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or isinstance(value, bool):
        _fail("wrong-type", f"{context} must be a string")
    if not value or len(value) > maximum:
        _fail("string-length", f"{context} must contain 1..{maximum} characters")
    return value


def _expect_id(value: Any, context: str) -> str:
    text = _expect_string(value, context, maximum=128)
    if not ID_RE.fullmatch(text):
        _fail("invalid-id", f"{context} is not a bounded identifier")
    return text


def _expect_digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail("invalid-digest", f"{context} must be sha256:<64 lowercase hex>")
    return value


def _expect_time(value: Any, context: str) -> str:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        _fail("invalid-time", f"{context} must be UTC RFC 3339 seconds")
    return value


PRIVACY_KEYS = {
    "publication_authorized",
    "public_data_only",
    "contains_private_chain_of_thought",
    "contains_hidden_prompt",
    "contains_credentials_or_secrets",
    "contains_sensitive_digest",
    "personal_data_class",
    "personal_data_minimized",
    "redistribution_basis",
    "retention_limit",
}


def verify_privacy(value: Any) -> None:
    """Fail before an event is considered eligible for the public chain."""

    privacy = _expect_exact_keys(value, PRIVACY_KEYS, "privacy")
    required_true = (
        "publication_authorized",
        "public_data_only",
        "personal_data_minimized",
    )
    required_false = (
        "contains_private_chain_of_thought",
        "contains_hidden_prompt",
        "contains_credentials_or_secrets",
        "contains_sensitive_digest",
    )
    for key in required_true:
        if privacy[key] is not True:
            _fail("privacy-not-public", f"privacy.{key} must be true")
    for key in required_false:
        if privacy[key] is not False:
            _fail("privacy-not-public", f"privacy.{key} must be false")
    if privacy["personal_data_class"] not in {
        "none",
        "minimum-accountable-identifier",
    }:
        _fail("privacy-not-public", "personal_data_class is not eligible")
    if privacy["redistribution_basis"] not in {
        "author",
        "license",
        "explicit-permission",
        "public-domain",
        "not-applicable",
    }:
        _fail("privacy-not-public", "redistribution basis is absent or unknown")
    if privacy["retention_limit"] is not None:
        _fail("privacy-not-public", "finite-retention data cannot enter Git history")


CLAIM_KEYS = {
    "inclusion_proves_truth",
    "inclusion_proves_independence",
    "inclusion_proves_reproduction",
    "inclusion_proves_adoption",
    "inclusion_proves_conformance",
    "inclusion_proves_general_efficiency",
    "inclusion_changes_project_claims",
    "inclusion_ratifies_protocol_semantics",
}


def verify_claim_boundary(value: Any) -> None:
    boundary = _expect_exact_keys(value, CLAIM_KEYS, "claim_boundary")
    if any(item is not False for item in boundary.values()):
        _fail("claim-boundary", "all log-inclusion implications must remain false")


def verify_actor(value: Any) -> None:
    actor = _expect_exact_keys(value, {"actor_id", "role"}, "actor")
    _expect_id(actor["actor_id"], "actor.actor_id")
    if actor["role"] not in {"submitter", "structural-reviewer", "maintainer"}:
        _fail("invalid-actor-role", f"unsupported actor role {actor['role']!r}")


def verify_review(value: Any, state: str) -> None:
    if value is None:
        if state in {"structurally-valid", "accepted-as-evidence", "rejected", "retracted"}:
            _fail("review-required", f"state {state!r} requires a review object")
        return
    review = _expect_exact_keys(
        value,
        {"kind", "reviewer_id", "decision", "accepted_evidence_scope", "public_reason"},
        "review",
    )
    if review["kind"] not in {"automated-structural-check", "maintainer", "independent-reviewer"}:
        _fail("invalid-review", "unsupported review kind")
    _expect_id(review["reviewer_id"], "review.reviewer_id")
    if review["decision"] not in {"pass", "fail", "incomplete"}:
        _fail("invalid-review", "unsupported review decision")
    _expect_string(review["public_reason"], "review.public_reason")
    scope = review["accepted_evidence_scope"]
    if state == "accepted-as-evidence":
        if review["kind"] == "automated-structural-check":
            _fail("invalid-review", "automation cannot accept evidence")
        if review["decision"] != "pass" or scope != "quick_60s-response":
            _fail("invalid-review", "accepted evidence needs a human pass and bounded scope")
    elif scope is not None:
        _fail("invalid-review", "only accepted evidence may name an accepted scope")
    if state == "structurally-valid" and review["decision"] != "pass":
        _fail("invalid-review", "structurally-valid requires a passing review")
    if state in {"rejected", "retracted"} and review["decision"] != "fail":
        _fail("invalid-review", f"{state} requires a failing review")


def verify_quick_60s(value: Any) -> None:
    payload = _expect_exact_keys(value, {"challenge", "response"}, "quick_60s")
    challenge = _expect_exact_keys(
        payload["challenge"], {"id", "immutable_uri", "sha256"}, "quick_60s.challenge"
    )
    if challenge["id"] != "quick_60s":
        _fail("wrong-track", "only quick_60s is supported")
    if not isinstance(challenge["immutable_uri"], str) or not IMMUTABLE_CHALLENGE_RE.fullmatch(
        challenge["immutable_uri"]
    ):
        _fail("mutable-challenge", "quick_60s challenge URI must pin a 40-hex revision")
    if challenge["sha256"] != QUICK_60S_SHA256:
        _fail("challenge-digest", "quick_60s challenge digest is not the pinned artifact")
    response = _expect_exact_keys(
        payload["response"], {"decision", "reason", "participant", "runtime"}, "response"
    )
    if response["decision"] not in {"RETAIN", "ROLLBACK"}:
        _fail("invalid-response", "decision must be RETAIN or ROLLBACK")
    _expect_string(response["reason"], "response.reason")
    if response["participant"] not in {"human", "agent", "human+agent"}:
        _fail("invalid-response", "participant is outside the quick_60s schema")
    _expect_string(response["runtime"], "response.runtime")


EVENT_KEYS = {
    "schema_version",
    "log_id",
    "log_epoch",
    "sequence",
    "event_type",
    "previous_record_sha256",
    "prior_epoch_checkpoint_sha256",
    "continuity_reason_code",
    "recorded_at",
    "submission_id",
    "prior_submission_event_sha256",
    "state",
    "state_reason",
    "actor",
    "quick_60s",
    "review",
    "privacy",
    "claim_boundary",
    "supersedes_submission_id",
    "superseded_by_submission_id",
    "record_sha256",
}

STATES = {
    "received",
    "structurally-valid",
    "accepted-as-evidence",
    "rejected",
    "withdrawn",
    "retracted",
    "superseded",
    "tombstoned",
}

EVENT_STATE = {
    "submission-received": "received",
    "submission-state-changed": {"structurally-valid", "accepted-as-evidence", "rejected"},
    "submission-withdrawn": "withdrawn",
    "submission-retracted": "retracted",
    "submission-superseded": "superseded",
    "submission-tombstoned": "tombstoned",
}

TRANSITIONS = {
    "received": {"structurally-valid", "rejected", "withdrawn", "tombstoned"},
    "structurally-valid": {
        "accepted-as-evidence",
        "rejected",
        "withdrawn",
        "tombstoned",
    },
    "accepted-as-evidence": {"retracted", "superseded", "tombstoned"},
    "rejected": {"superseded", "tombstoned"},
    "withdrawn": {"superseded", "tombstoned"},
    "retracted": {"superseded", "tombstoned"},
    "superseded": {"tombstoned"},
    "tombstoned": set(),
}


def verify_event_shape(event: Any) -> dict[str, Any]:
    item = _expect_exact_keys(event, EVENT_KEYS, "event")
    if item["schema_version"] != EVENT_SCHEMA or item["log_id"] != LOG_ID:
        _fail("wrong-profile", "event schema_version or log_id is not epoch-1 profile")
    if item["log_epoch"] != 1:
        _fail("wrong-epoch", "read-only core supports epoch 1 only")
    if not isinstance(item["sequence"], int) or isinstance(item["sequence"], bool) or item["sequence"] < 1:
        _fail("invalid-sequence", "event sequence must be a positive integer")
    if item["event_type"] not in EVENT_STATE:
        _fail("invalid-event-type", "unsupported event_type")
    if item["state"] not in STATES:
        _fail("invalid-state", "unsupported state")
    expected_state = EVENT_STATE[item["event_type"]]
    if isinstance(expected_state, set):
        if item["state"] not in expected_state:
            _fail("event-state-mismatch", "event_type does not match state")
    elif item["state"] != expected_state:
        _fail("event-state-mismatch", "event_type does not match state")
    for key in ("previous_record_sha256", "prior_submission_event_sha256"):
        if item[key] is not None:
            _expect_digest(item[key], f"event.{key}")
    if item["prior_epoch_checkpoint_sha256"] is not None or item["continuity_reason_code"] is not None:
        _fail("wrong-epoch", "epoch 1 cannot claim prior-epoch continuity")
    _expect_time(item["recorded_at"], "event.recorded_at")
    _expect_id(item["submission_id"], "event.submission_id")
    reason = _expect_exact_keys(item["state_reason"], {"code", "public_detail"}, "state_reason")
    _expect_id(reason["code"], "state_reason.code")
    _expect_string(reason["public_detail"], "state_reason.public_detail")
    verify_actor(item["actor"])

    # This check intentionally precedes any decision to admit the event to the
    # public chain.  It is a declaration gate, not a content-classification AI.
    verify_privacy(item["privacy"])
    verify_claim_boundary(item["claim_boundary"])
    verify_review(item["review"], item["state"])

    if item["quick_60s"] is not None:
        verify_quick_60s(item["quick_60s"])
    for key in ("supersedes_submission_id", "superseded_by_submission_id"):
        if item[key] is not None:
            _expect_id(item[key], f"event.{key}")
            if item[key] == item["submission_id"]:
                _fail("self-correction", "a submission cannot supersede itself")
    _expect_digest(item["record_sha256"], "event.record_sha256")
    expected = object_digest(item, "record_sha256")
    if item["record_sha256"] != expected:
        _fail("record-hash-mismatch", f"sequence {item['sequence']} expected {expected}")
    return item


LOG_KEYS = {"schema_version", "log_id", "log_epoch", "records", "log_sha256"}


def verify_log(value: Any) -> dict[str, Any]:
    log = _expect_exact_keys(value, LOG_KEYS, "log")
    if log["schema_version"] != LOG_SCHEMA or log["log_id"] != LOG_ID or log["log_epoch"] != 1:
        _fail("wrong-profile", "log is not the read-only epoch-1 profile")
    if not isinstance(log["records"], list):
        _fail("wrong-type", "log.records must be an array")
    if len(log["records"]) > MAX_RECORDS:
        _fail("too-many-records", f"log exceeds {MAX_RECORDS} records")
    _expect_digest(log["log_sha256"], "log.log_sha256")
    expected_log_hash = object_digest(log, "log_sha256")
    if log["log_sha256"] != expected_log_hash:
        _fail("log-hash-mismatch", f"expected {expected_log_hash}")

    prior_global: str | None = None
    last_for_submission: dict[str, str] = {}
    state_for_submission: dict[str, str] = {}
    payload_for_submission: set[str] = set()
    pending_successor: dict[str, str] = {}
    correction_source: dict[str, str] = {}

    for expected_sequence, raw_event in enumerate(log["records"], start=1):
        event = verify_event_shape(raw_event)
        if event["sequence"] != expected_sequence:
            _fail("sequence-gap", f"expected sequence {expected_sequence}")
        if event["previous_record_sha256"] != prior_global:
            _fail("global-chain-break", f"sequence {expected_sequence} has wrong predecessor")

        submission_id = event["submission_id"]
        first = submission_id not in state_for_submission
        expected_prior = last_for_submission.get(submission_id)
        if event["prior_submission_event_sha256"] != expected_prior:
            _fail("submission-chain-break", f"submission {submission_id!r} has wrong predecessor")

        if first:
            if event["event_type"] != "submission-received" or event["quick_60s"] is None:
                _fail("invalid-first-event", "first submission event must receive a quick_60s payload")
            if event["superseded_by_submission_id"] is not None:
                _fail("invalid-correction", "a first event cannot already be superseded")
            old_id = event["supersedes_submission_id"]
            if old_id is not None:
                if old_id not in state_for_submission:
                    _fail("unknown-correction-target", f"correction target {old_id!r} does not exist")
                if state_for_submission[old_id] not in {
                    "accepted-as-evidence",
                    "rejected",
                    "withdrawn",
                    "retracted",
                }:
                    _fail("invalid-correction-target", "target is not in a correctable stable state")
                if old_id in pending_successor:
                    _fail("competing-correction", "target already has a direct successor")
                pending_successor[old_id] = submission_id
                correction_source[submission_id] = old_id
            payload_for_submission.add(submission_id)
        else:
            if event["quick_60s"] is not None or event["supersedes_submission_id"] is not None:
                _fail("payload-repeated", "later events must bind the first payload by hash")
            old_state = state_for_submission[submission_id]
            if event["state"] not in TRANSITIONS[old_state]:
                _fail("invalid-state-transition", f"{old_state} -> {event['state']} is forbidden")

        if event["event_type"] == "submission-superseded":
            successor = event["superseded_by_submission_id"]
            if successor is None or pending_successor.get(submission_id) != successor:
                _fail("invalid-correction", "superseded event must name its unique proposed successor")
            if state_for_submission.get(successor) != "accepted-as-evidence":
                _fail("correction-not-accepted", "successor must be accepted before replacing current evidence")
        elif event["superseded_by_submission_id"] is not None:
            _fail("invalid-correction", "superseded_by is valid only on a superseded event")

        state_for_submission[submission_id] = event["state"]
        last_for_submission[submission_id] = event["record_sha256"]
        prior_global = event["record_sha256"]

    if payload_for_submission != set(state_for_submission):
        _fail("missing-payload", "every submission must have exactly one first payload")
    return log


CHECKPOINT_KEYS = {
    "schema_version",
    "log_id",
    "log_epoch",
    "tree_size",
    "first_sequence",
    "last_sequence",
    "head_record_sha256",
    "merkle_root_sha256",
    "log_sha256",
    "generated_at",
    "signature_status",
    "signer_id",
    "checkpoint_sha256",
}


def verify_checkpoint(value: Any, log: dict[str, Any]) -> dict[str, Any]:
    checkpoint = _expect_exact_keys(value, CHECKPOINT_KEYS, "checkpoint")
    if (
        checkpoint["schema_version"] != CHECKPOINT_SCHEMA
        or checkpoint["log_id"] != LOG_ID
        or checkpoint["log_epoch"] != 1
    ):
        _fail("wrong-profile", "checkpoint is not the read-only epoch-1 profile")
    count = len(log["records"])
    if checkpoint["tree_size"] != count:
        _fail("checkpoint-size", "checkpoint tree_size does not match the log")
    if count == 0:
        for key in ("first_sequence", "last_sequence", "head_record_sha256"):
            if checkpoint[key] is not None:
                _fail("empty-checkpoint", f"empty checkpoint requires {key}=null")
        if checkpoint["merkle_root_sha256"] != EMPTY_SHA256:
            _fail("empty-checkpoint", "empty Merkle root must be SHA-256 of zero bytes")
    else:
        if checkpoint["first_sequence"] != 1 or checkpoint["last_sequence"] != count:
            _fail("checkpoint-range", "checkpoint sequence range does not match the log")
        if checkpoint["head_record_sha256"] != log["records"][-1]["record_sha256"]:
            _fail("checkpoint-head", "checkpoint head does not match the last event")
        if checkpoint["merkle_root_sha256"] is not None:
            _expect_digest(checkpoint["merkle_root_sha256"], "checkpoint.merkle_root_sha256")
    if checkpoint["log_sha256"] != log["log_sha256"]:
        _fail("checkpoint-log", "checkpoint does not bind the canonical log")
    _expect_time(checkpoint["generated_at"], "checkpoint.generated_at")
    if checkpoint["signature_status"] != "unsigned" or checkpoint["signer_id"] is not None:
        _fail("signature-claim", "the MVP checkpoint is unsigned")
    _expect_digest(checkpoint["checkpoint_sha256"], "checkpoint.checkpoint_sha256")
    expected = object_digest(checkpoint, "checkpoint_sha256")
    if checkpoint["checkpoint_sha256"] != expected:
        _fail("checkpoint-hash-mismatch", f"expected {expected}")
    return checkpoint


DISCOVERY_KEYS = {
    "schema_version",
    "log_id",
    "status",
    "log_epoch",
    "supported_tracks",
    "writes_enabled",
    "live_bot_enabled",
    "network_access_required",
    "submission_transport",
    "canonical_log_path",
    "canonical_log_sha256",
    "current_checkpoint_path",
    "current_checkpoint_sha256",
    "event_schema_path",
    "event_schema_sha256",
    "checkpoint_schema_path",
    "checkpoint_schema_sha256",
    "discovery_schema_path",
    "discovery_schema_sha256",
    "log_schema_path",
    "log_schema_sha256",
    "verifier_path",
    "verifier_sha256",
    "public_record_count",
    "discovery_sha256",
}


def _safe_relative_path(root: Path, raw: Any, context: str) -> Path:
    value = _expect_string(raw, context, maximum=256)
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail("unsafe-path", f"{context} must be a repository-relative path")
    resolved = (root / candidate).resolve()
    if root.resolve() not in resolved.parents and resolved != root.resolve():
        _fail("unsafe-path", f"{context} escapes the evidence-log root")
    return resolved


def verify_discovery(value: Any, root: Path, log: dict[str, Any], checkpoint: dict[str, Any]) -> None:
    discovery = _expect_exact_keys(value, DISCOVERY_KEYS, "discovery")
    if (
        discovery["schema_version"] != DISCOVERY_SCHEMA
        or discovery["log_id"] != LOG_ID
        or discovery["log_epoch"] != 1
    ):
        _fail("wrong-profile", "discovery is not the read-only epoch-1 profile")
    if discovery["status"] != "empty-read-only":
        _fail("discovery-status", "this core advertises only the empty read-only state")
    if discovery["supported_tracks"] != ["quick_60s"]:
        _fail("wrong-track", "discovery must advertise only quick_60s")
    if discovery["writes_enabled"] is not False or discovery["live_bot_enabled"] is not False:
        _fail("write-path-advertised", "read-only core cannot advertise a write path")
    if discovery["network_access_required"] is not False or discovery["submission_transport"] is not None:
        _fail("network-path-advertised", "offline core has no submission transport")
    if discovery["public_record_count"] != len(log["records"]):
        _fail("discovery-count", "public_record_count does not match canonical log")
    if discovery["canonical_log_sha256"] != log["log_sha256"]:
        _fail("discovery-log", "discovery does not bind the canonical log")
    if discovery["current_checkpoint_sha256"] != checkpoint["checkpoint_sha256"]:
        _fail("discovery-checkpoint", "discovery does not bind the checkpoint")
    expected_paths = {
        "canonical_log_path": "epochs/00000001/log.json",
        "current_checkpoint_path": "epochs/00000001/checkpoints/empty.json",
        "event_schema_path": "schemas/event-v1.schema.json",
        "checkpoint_schema_path": "schemas/checkpoint-v1.schema.json",
        "discovery_schema_path": "schemas/discovery-v1.schema.json",
        "log_schema_path": "schemas/log-v1.schema.json",
        "verifier_path": "verify.py",
    }
    for key, expected_path in expected_paths.items():
        if discovery[key] != expected_path:
            _fail("discovery-path", f"{key} must be {expected_path!r}")
        if not _safe_relative_path(root, discovery[key], f"discovery.{key}").is_file():
            _fail("discovery-path", f"{key} does not resolve to a file")
    digest_paths = {
        "event_schema_sha256": "event_schema_path",
        "checkpoint_schema_sha256": "checkpoint_schema_path",
        "discovery_schema_sha256": "discovery_schema_path",
        "log_schema_sha256": "log_schema_path",
        "verifier_sha256": "verifier_path",
    }
    for digest_key, path_key in digest_paths.items():
        declared_digest = _expect_digest(discovery[digest_key], f"discovery.{digest_key}")
        artifact_path = _safe_relative_path(root, discovery[path_key], f"discovery.{path_key}")
        try:
            actual_digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        except OSError as exc:
            _fail("read-error", f"{artifact_path}: {exc}")
        if declared_digest != actual_digest:
            _fail("discovery-artifact", f"{digest_key} does not bind {discovery[path_key]}")
    _expect_digest(discovery["discovery_sha256"], "discovery.discovery_sha256")
    expected = object_digest(discovery, "discovery_sha256")
    if discovery["discovery_sha256"] != expected:
        _fail("discovery-hash-mismatch", f"expected {expected}")


def verify_root(root: Path) -> None:
    root = root.resolve()
    schema_ids = {
        "schemas/event-v1.schema.json": "urn:urusilla:evidence-log:quick60-event:1",
        "schemas/log-v1.schema.json": "urn:urusilla:evidence-log:quick60-log:1",
        "schemas/checkpoint-v1.schema.json": "urn:urusilla:evidence-log:quick60-checkpoint:1",
        "schemas/discovery-v1.schema.json": "urn:urusilla:evidence-log:quick60-discovery:1",
    }
    for relative_path, schema_id in schema_ids.items():
        schema = load_json(root / relative_path)
        if not isinstance(schema, dict):
            _fail("invalid-schema-document", f"{relative_path} must be an object")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            _fail("invalid-schema-document", f"{relative_path} has the wrong JSON Schema dialect")
        if schema.get("$id") != schema_id or schema.get("type") != "object":
            _fail("invalid-schema-document", f"{relative_path} has the wrong identity or root type")
    challenge_path = root.parent / "interop_lab/challenges/quick_60s.json"
    try:
        challenge_digest = "sha256:" + hashlib.sha256(challenge_path.read_bytes()).hexdigest()
    except OSError as exc:
        _fail("read-error", f"{challenge_path}: {exc}")
    if challenge_digest != QUICK_60S_SHA256:
        _fail("challenge-digest", "local quick_60s artifact differs from the pinned digest")
    log = verify_log(load_json(root / "epochs/00000001/log.json"))
    checkpoint = verify_checkpoint(
        load_json(root / "epochs/00000001/checkpoints/empty.json"), log
    )
    verify_discovery(load_json(root / "discovery.json"), root, log, checkpoint)


def _apply_vector_mutations(log: dict[str, Any], mutations: Any) -> None:
    if not isinstance(mutations, list) or len(mutations) > 16:
        _fail("invalid-test-vector", "mutations must be an array of at most 16 entries")
    for index, raw_mutation in enumerate(mutations):
        mutation = _expect_exact_keys(raw_mutation, {"path", "value"}, f"mutation[{index}]")
        path = mutation["path"]
        if not isinstance(path, list) or not path or len(path) > 8:
            _fail("invalid-test-vector", "mutation path must contain 1..8 components")
        target: Any = log
        for component in path[:-1]:
            if isinstance(target, dict) and isinstance(component, str) and component in target:
                target = target[component]
            elif (
                isinstance(target, list)
                and isinstance(component, int)
                and not isinstance(component, bool)
                and 0 <= component < len(target)
            ):
                target = target[component]
            else:
                _fail("invalid-test-vector", f"mutation path component {component!r} is absent")
        final = path[-1]
        if isinstance(target, dict) and isinstance(final, str) and final in target:
            target[final] = mutation["value"]
        elif (
            isinstance(target, list)
            and isinstance(final, int)
            and not isinstance(final, bool)
            and 0 <= final < len(target)
        ):
            target[final] = mutation["value"]
        else:
            _fail("invalid-test-vector", f"final mutation component {final!r} is absent")


def _reseal_vector_log(log: dict[str, Any]) -> None:
    prior_global: str | None = None
    per_submission: dict[str, str] = {}
    records = log.get("records")
    if not isinstance(records, list):
        _fail("invalid-test-vector", "base log has no records array")
    for event in records:
        if not isinstance(event, dict) or "submission_id" not in event:
            _fail("invalid-test-vector", "base log event is malformed")
        event["previous_record_sha256"] = prior_global
        event["prior_submission_event_sha256"] = per_submission.get(event["submission_id"])
        event["record_sha256"] = object_digest(event, "record_sha256")
        prior_global = event["record_sha256"]
        per_submission[event["submission_id"]] = prior_global
    log["log_sha256"] = object_digest(log, "log_sha256")


def _vector_log(path: Path, wrapper: dict[str, Any]) -> dict[str, Any]:
    if set(wrapper) == {"expected", "log"}:
        if not isinstance(wrapper["log"], dict):
            _fail("invalid-test-vector", "vector log must be an object")
        return wrapper["log"]
    _expect_exact_keys(wrapper, {"expected", "base", "mutations", "reseal"}, "test vector")
    base_name = wrapper["base"]
    if not isinstance(base_name, str) or Path(base_name).name != base_name or not base_name.endswith(".json"):
        _fail("invalid-test-vector", "base must be one sibling JSON filename")
    base_wrapper = load_json(path.parent / base_name)
    if not isinstance(base_wrapper, dict) or set(base_wrapper) != {"expected", "log"}:
        _fail("invalid-test-vector", "base vector must contain a direct log")
    log = copy.deepcopy(base_wrapper["log"])
    _apply_vector_mutations(log, wrapper["mutations"])
    if wrapper["reseal"] is not True:
        _fail("invalid-test-vector", "mutation vectors must explicitly request deterministic resealing")
    _reseal_vector_log(log)
    return log


def verify_vector(path: Path) -> None:
    raw_wrapper = load_json(path)
    if not isinstance(raw_wrapper, dict):
        _fail("invalid-test-vector", "test vector must be an object")
    wrapper = raw_wrapper
    if "expected" not in wrapper:
        _fail("invalid-test-vector", "test vector is missing expected")
    expected = wrapper["expected"]
    log = _vector_log(path, wrapper)
    if expected == "valid":
        verify_log(log)
        return
    if not isinstance(expected, str) or not expected.startswith("error:"):
        _fail("invalid-test-vector", f"{path} has an invalid expected value")
    wanted = expected.removeprefix("error:")
    try:
        verify_log(log)
    except VerificationError as exc:
        if exc.code != wanted:
            _fail("wrong-test-vector-error", f"{path} expected {wanted}, got {exc.code}")
        return
    _fail("negative-vector-passed", f"{path} unexpectedly validated")


def verify_vectors(root: Path) -> int:
    paths = sorted((root / "test-vectors").glob("*.json"))
    if not paths:
        _fail("missing-test-vectors", "no test vectors found")
    for path in paths:
        verify_vector(path)
    return len(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="evidence-log directory (default: verifier directory)",
    )
    parser.add_argument("--vectors", action="store_true", help="also verify static vectors")
    args = parser.parse_args(argv)
    try:
        verify_root(args.root)
        count = verify_vectors(args.root) if args.vectors else 0
    except VerificationError as exc:
        print(f"FAIL [{exc.code}] {exc.detail}", file=sys.stderr)
        return 1
    suffix = f"; {count} test vectors" if args.vectors else ""
    print(f"OK: empty read-only epoch-1 log verified{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
