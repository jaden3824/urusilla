#!/usr/bin/env python3
"""Dependency-free validator for Urusilla propagation-chain evidence.

The program reads declarative JSON only.  It does not import submitted code,
open a network connection, contact a model, or authorize an external effect.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import uuid
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "urusilla-propagation-chain/1"
MAX_FILE_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_NODES = 50_000
MAX_STRING_CHARS = 65_536
MAX_PARTICIPANTS = 32
MAX_HOPS = 64
MAX_TRANSCRIPT_ENTRIES = 512

CAPSULE_SHA256 = (
    "sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/-]{0,63}$")

LEDGER_CATEGORIES = (
    "task_input",
    "system_role",
    "agent_input_history",
    "agent_output_visible",
    "final_answer",
    "format_induction",
    "encode_decode_model",
    "negotiation_profile",
    "repair_retry",
    "tool_request",
    "tool_result",
    "safety_filter",
    "hidden_reasoning_billed",
    "unclassified",
)


class ValidationError(ValueError):
    """Raised when a propagation record is not structurally trustworthy."""


def _duplicate_rejector(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    if type(text) is not str:
        raise ValidationError("JSON input must be text")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError("JSON input is not valid UTF-8 text") from exc
    if len(encoded) > MAX_FILE_BYTES:
        raise ValidationError(f"JSON input exceeds {MAX_FILE_BYTES} bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_rejector,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValidationError(f"non-finite JSON number: {constant}")
            ),
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError) as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc
    _check_resource_limits(value)
    return value


def load_record(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError(f"JSON file exceeds {MAX_FILE_BYTES} bytes: {path}")
    try:
        return strict_json_loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValidationError(f"JSON file is not UTF-8: {path}") from exc


def _check_resource_limits(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES:
            raise ValidationError(f"JSON exceeds {MAX_NODES} values")
        if depth > MAX_DEPTH:
            raise ValidationError(f"JSON nesting exceeds {MAX_DEPTH}")
        if type(current) is str and len(current) > MAX_STRING_CHARS:
            raise ValidationError(
                f"JSON string exceeds {MAX_STRING_CHARS} characters"
            )
        if type(current) is dict:
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in current)


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationError(f"record is not canonical-JSON encodable: {exc}") from exc
    return text.encode("utf-8")


def sha256_ref(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _list(value: Any, path: str, *, minimum: int = 0, maximum: int = 10_000) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{path} must be an array")
    if not minimum <= len(value) <= maximum:
        raise ValidationError(
            f"{path} length must be between {minimum} and {maximum}"
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: Iterable[str], path: str) -> None:
    wanted = set(expected)
    observed = set(value)
    if observed != wanted:
        missing = sorted(wanted - observed)
        extra = sorted(observed - wanted)
        raise ValidationError(
            f"{path} fields differ; missing={missing}, extra={extra}"
        )


def _string(
    value: Any,
    path: str,
    *,
    minimum: int = 0,
    maximum: int = 4_096,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        raise ValidationError(
            f"{path} must be a string of {minimum}..{maximum} characters"
        )
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ValidationError(f"{path} has an invalid format")
    return value


def _nullable_string(value: Any, path: str, *, maximum: int = 4_096) -> str | None:
    if value is None:
        return None
    return _string(value, path, maximum=maximum)


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{path} must be a boolean")
    return value


def _count(value: Any, path: str, *, maximum: int = 10**12) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValidationError(f"{path} must be a nonnegative integer <= {maximum}")
    return value


def _enum(value: Any, choices: set[str], path: str) -> str:
    if type(value) is not str or value not in choices:
        raise ValidationError(f"{path} must be one of {sorted(choices)}")
    return value


def _digest(value: Any, path: str) -> str:
    return _string(value, path, minimum=71, maximum=71, pattern=SHA256_RE)


def _nullable_digest(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _digest(value, path)


def _identifier(value: Any, path: str) -> str:
    return _string(value, path, minimum=1, maximum=64, pattern=ID_RE)


def _finite_percent(value: Any, path: str) -> float:
    if type(value) not in {int, float}:
        raise ValidationError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not -1_000_000 <= result <= 100:
        raise ValidationError(f"{path} is outside the valid percentage range")
    return result


def _nullable_percent(value: Any, path: str) -> float | None:
    if value is None:
        return None
    return _finite_percent(value, path)


def _expected_saving(baseline: int, candidate: int) -> float | None:
    if baseline == 0:
        return None
    return (baseline - candidate) * 100.0 / baseline


def _require_percent_match(observed: Any, expected: float | None, path: str) -> None:
    actual = _nullable_percent(observed, path)
    if expected is None:
        if actual is not None:
            raise ValidationError(f"{path} must be null when the baseline is zero")
        return
    if actual is None or not math.isclose(actual, expected, abs_tol=1e-6, rel_tol=1e-9):
        raise ValidationError(f"{path} must equal the recomputed value {expected:.12g}")


def _validate_timestamp(value: Any, path: str) -> None:
    text = _string(value, path, minimum=20, maximum=32)
    if not text.endswith("Z"):
        raise ValidationError(f"{path} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{path} is not a valid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValidationError(f"{path} must be UTC")


def _validate_protocol(value: Any) -> dict[str, Any]:
    protocol = _object(value, "protocol")
    _exact_keys(
        protocol,
        (
            "project",
            "language_version",
            "capsule_uri",
            "capsule_sha256",
            "capsule_signature_verified",
            "capsule_signature_evidence_sha256",
        ),
        "protocol",
    )
    if protocol["project"] != "Urusilla":
        raise ValidationError("protocol.project must be Urusilla")
    _string(protocol["language_version"], "protocol.language_version", pattern=VERSION_RE)
    uri = _string(protocol["capsule_uri"], "protocol.capsule_uri", minimum=8, maximum=2_048)
    if not uri.startswith("https://") or any(char.isspace() for char in uri):
        raise ValidationError("protocol.capsule_uri must be an HTTPS URI without whitespace")
    _digest(protocol["capsule_sha256"], "protocol.capsule_sha256")
    _boolean(
        protocol["capsule_signature_verified"],
        "protocol.capsule_signature_verified",
    )
    signature_evidence = _nullable_digest(
        protocol["capsule_signature_evidence_sha256"],
        "protocol.capsule_signature_evidence_sha256",
    )
    if protocol["capsule_signature_verified"] and signature_evidence is None:
        raise ValidationError(
            "protocol.capsule_signature_evidence_sha256 is required when verified"
        )
    if not protocol["capsule_signature_verified"] and signature_evidence is not None:
        raise ValidationError(
            "protocol.capsule_signature_evidence_sha256 must be null when unsigned"
        )
    return protocol


def _validate_evidence(value: Any) -> dict[str, Any]:
    evidence = _object(value, "evidence")
    _exact_keys(
        evidence,
        (
            "recorder",
            "evidence_tier",
            "premeasurement_sealed",
            "collection_method",
            "artifacts_public",
        ),
        "evidence",
    )
    _string(evidence["recorder"], "evidence.recorder", minimum=1, maximum=128)
    _enum(
        evidence["evidence_tier"],
        {"project-authored", "self-reported", "independently-observed"},
        "evidence.evidence_tier",
    )
    _boolean(evidence["premeasurement_sealed"], "evidence.premeasurement_sealed")
    _string(
        evidence["collection_method"],
        "evidence.collection_method",
        minimum=1,
        maximum=2_048,
    )
    _boolean(evidence["artifacts_public"], "evidence.artifacts_public")
    return evidence


def _validate_participants(value: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    participants = _list(
        value, "participants", minimum=2, maximum=MAX_PARTICIPANTS
    )
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(participants):
        path = f"participants[{index}]"
        participant = _object(raw, path)
        _exact_keys(
            participant,
            (
                "id",
                "operator_id",
                "relationship_to_project",
                "runtime",
                "disclosure",
            ),
            path,
        )
        participant_id = _identifier(participant["id"], f"{path}.id")
        if participant_id in by_id:
            raise ValidationError(f"duplicate participant id: {participant_id}")
        _identifier(participant["operator_id"], f"{path}.operator_id")
        _enum(
            participant["relationship_to_project"],
            {"same-project", "independent", "unknown"},
            f"{path}.relationship_to_project",
        )
        runtime = _object(participant["runtime"], f"{path}.runtime")
        _exact_keys(runtime, ("provider", "model", "version"), f"{path}.runtime")
        for key in ("provider", "model", "version"):
            _string(runtime[key], f"{path}.runtime.{key}", minimum=1, maximum=128)
        _string(participant["disclosure"], f"{path}.disclosure", maximum=2_048)
        by_id[participant_id] = participant
    return participants, by_id


def _validate_context(value: Any, path: str) -> dict[str, Any]:
    context = _object(value, path)
    _exact_keys(
        context,
        (
            "kind",
            "context_sha256",
            "context_bytes",
            "context_input_tokens",
            "capsule_digest_verified",
            "included_capsule",
            "included_examples",
            "included_prior_transcript",
            "included_evaluator_instructions",
            "included_executable_code",
            "description",
        ),
        path,
    )
    _enum(
        context["kind"],
        {"capsule-only", "capsule-with-examples", "repository-context", "custom"},
        f"{path}.kind",
    )
    _digest(context["context_sha256"], f"{path}.context_sha256")
    if _count(context["context_bytes"], f"{path}.context_bytes") == 0:
        raise ValidationError(f"{path}.context_bytes must be positive")
    if context["context_input_tokens"] is not None:
        _count(context["context_input_tokens"], f"{path}.context_input_tokens")
    for key in (
        "capsule_digest_verified",
        "included_capsule",
        "included_examples",
        "included_prior_transcript",
        "included_evaluator_instructions",
        "included_executable_code",
    ):
        _boolean(context[key], f"{path}.{key}")
    _string(context["description"], f"{path}.description", maximum=2_048)
    if not context["included_capsule"]:
        raise ValidationError(f"{path}.included_capsule must be true for a propagation hop")
    return context


def _validate_gate(value: Any, path: str) -> dict[str, Any]:
    gate = _object(value, path)
    _exact_keys(
        gate,
        (
            "attempted",
            "positive_cases",
            "negative_cases",
            "exact_reconstruction_cases",
            "passed",
            "failures",
        ),
        path,
    )
    attempted = _boolean(gate["attempted"], f"{path}.attempted")
    case_groups: list[tuple[int, int]] = []
    for name in ("positive_cases", "negative_cases", "exact_reconstruction_cases"):
        group_path = f"{path}.{name}"
        group = _object(gate[name], group_path)
        _exact_keys(group, ("total", "passed"), group_path)
        total = _count(group["total"], f"{group_path}.total", maximum=100_000)
        passed = _count(group["passed"], f"{group_path}.passed", maximum=100_000)
        if passed > total:
            raise ValidationError(f"{group_path}.passed cannot exceed total")
        case_groups.append((total, passed))
    failures = _list(gate["failures"], f"{path}.failures", maximum=128)
    for index, failure in enumerate(failures):
        _string(failure, f"{path}.failures[{index}]", minimum=1, maximum=512)
    passed_value = _boolean(gate["passed"], f"{path}.passed")
    computed = attempted and all(total > 0 and total == passed for total, passed in case_groups)
    if passed_value != computed:
        raise ValidationError(f"{path}.passed does not match the case counts")
    if passed_value and failures:
        raise ValidationError(f"{path}.failures must be empty when the gate passes")
    if attempted and not passed_value and not failures:
        raise ValidationError(f"{path}.failures must explain a failed attempted gate")
    if not attempted and any(total != 0 or passed != 0 for total, passed in case_groups):
        raise ValidationError(f"{path} unattempted gate must contain zero case counts")
    return gate


def _finite_number(value: Any, path: str) -> float:
    if type(value) not in {int, float}:
        raise ValidationError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not -(10**12) <= result <= 10**12:
        raise ValidationError(f"{path} is outside the accepted finite range")
    return result


def _validate_utility(value: Any, path: str, *, must_pass: bool) -> dict[str, Any]:
    utility = _object(value, path)
    _exact_keys(
        utility,
        (
            "evaluated",
            "metric",
            "observed_value",
            "minimum_threshold",
            "passed",
            "evidence_sha256",
        ),
        path,
    )
    evaluated = _boolean(utility["evaluated"], f"{path}.evaluated")
    if utility["metric"] != "expected-mutual-utility":
        raise ValidationError(f"{path}.metric must be expected-mutual-utility")
    passed = _boolean(utility["passed"], f"{path}.passed")
    if evaluated:
        observed = _finite_number(utility["observed_value"], f"{path}.observed_value")
        threshold = _finite_number(
            utility["minimum_threshold"], f"{path}.minimum_threshold"
        )
        _digest(utility["evidence_sha256"], f"{path}.evidence_sha256")
        if passed != (observed >= threshold):
            raise ValidationError(f"{path}.passed does not match its threshold")
    else:
        if (
            utility["observed_value"] is not None
            or utility["minimum_threshold"] is not None
            or utility["evidence_sha256"] is not None
            or passed
        ):
            raise ValidationError(
                f"{path} unevaluated utility must use null values and passed=false"
            )
    if must_pass and (not evaluated or not passed):
        raise ValidationError(f"{path} must pass before the authorized action")
    return utility


def _validate_revocation(value: Any, path: str, *, must_be_available: bool) -> dict[str, Any]:
    revocation = _object(value, path)
    _exact_keys(
        revocation,
        ("available", "invoked", "result", "evidence_sha256"),
        path,
    )
    available = _boolean(revocation["available"], f"{path}.available")
    invoked = _boolean(revocation["invoked"], f"{path}.invoked")
    result = _enum(
        revocation["result"],
        {"not-applicable", "not-invoked", "revoked", "failed"},
        f"{path}.result",
    )
    evidence = _nullable_digest(
        revocation["evidence_sha256"], f"{path}.evidence_sha256"
    )
    if must_be_available and not available:
        raise ValidationError(f"{path}.available must be true for an authorized action")
    if not available:
        if invoked or result != "not-applicable" or evidence is not None:
            raise ValidationError(f"{path} unavailable revocation must be not-applicable")
    elif invoked:
        if result not in {"revoked", "failed"} or evidence is None:
            raise ValidationError(f"{path} invoked revocation needs a result and evidence")
    elif result != "not-invoked" or evidence is not None:
        raise ValidationError(f"{path} non-invoked revocation must use not-invoked")
    return revocation


def _validate_authorization(
    value: Any,
    path: str,
    *,
    action_active: bool,
) -> dict[str, Any]:
    authorization = _object(value, path)
    _exact_keys(
        authorization,
        (
            "authorization_basis",
            "authorization_evidence_sha256",
            "read_only",
            "reversible_participation",
            "state_persistence_authorized",
            "spending_authorized",
            "external_effects_authorized",
        ),
        path,
    )
    basis = _enum(
        authorization["authorization_basis"],
        {"standing-policy", "interactive-approval", "none"},
        f"{path}.authorization_basis",
    )
    evidence = _nullable_digest(
        authorization["authorization_evidence_sha256"],
        f"{path}.authorization_evidence_sha256",
    )
    read_only = _boolean(authorization["read_only"], f"{path}.read_only")
    reversible = _boolean(
        authorization["reversible_participation"],
        f"{path}.reversible_participation",
    )
    for key in (
        "state_persistence_authorized",
        "spending_authorized",
        "external_effects_authorized",
    ):
        if _boolean(authorization[key], f"{path}.{key}"):
            raise ValidationError(f"{path}.{key} must be false in the public lab")
    if basis == "none":
        if evidence is not None:
            raise ValidationError(f"{path} basis none must not carry authorization evidence")
        if action_active:
            raise ValidationError(f"{path}.authorization_basis cannot be none for this action")
    elif evidence is None:
        raise ValidationError(f"{path} authorization evidence is required")
    if action_active and (not read_only or not reversible):
        raise ValidationError(
            f"{path} active authorization must be read-only and reversibly participatory"
        )
    return authorization


def _validate_adoption(
    value: Any,
    path: str,
    gate: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    adoption = _object(value, path)
    _exact_keys(
        adoption,
        (
            "decision",
            "scope",
            "mechanism",
            "authorization",
            "utility_evaluation",
            "revocation",
            "reason",
        ),
        path,
    )
    decision = _enum(
        adoption["decision"],
        {"adopted", "rejected", "fallback-only", "not-attempted"},
        f"{path}.decision",
    )
    scope = _enum(
        adoption["scope"], {"turn", "session", "persistent", "none"}, f"{path}.scope"
    )
    if adoption["mechanism"] != "declarative-read":
        raise ValidationError(f"{path}.mechanism must be declarative-read")
    active = decision == "adopted"
    _validate_authorization(
        adoption["authorization"], f"{path}.authorization", action_active=active
    )
    _validate_utility(
        adoption["utility_evaluation"],
        f"{path}.utility_evaluation",
        must_pass=active,
    )
    _validate_revocation(
        adoption["revocation"],
        f"{path}.revocation",
        must_be_available=active,
    )
    _string(adoption["reason"], f"{path}.reason", maximum=1_024)
    if decision == "adopted":
        if not gate["passed"] or not context["capsule_digest_verified"]:
            raise ValidationError(
                f"{path} cannot adopt before the comprehension and digest gates pass"
            )
        if scope == "none":
            raise ValidationError(f"{path}.scope cannot be none after adoption")
    elif scope != "none":
        raise ValidationError(f"{path}.scope must be none without adoption")
    if scope == "persistent":
        raise ValidationError(f"{path} persistent state is outside the public lab boundary")
    return adoption


def _validate_actual_use(value: Any, path: str, adoption: Mapping[str, Any]) -> dict[str, Any]:
    actual = _object(value, path)
    _exact_keys(
        actual,
        (
            "attempted",
            "mode",
            "messages_sent",
            "messages_received",
            "exactness",
            "task_attempted",
            "task_success",
            "task_result_sha256",
        ),
        path,
    )
    attempted = _boolean(actual["attempted"], f"{path}.attempted")
    mode = _enum(
        actual["mode"],
        {
            "urusilla",
            "structured-json",
            "concise-natural-language",
            "mixed",
            "none",
        },
        f"{path}.mode",
    )
    sent = _count(actual["messages_sent"], f"{path}.messages_sent", maximum=100_000)
    received = _count(
        actual["messages_received"], f"{path}.messages_received", maximum=100_000
    )
    _enum(
        actual["exactness"],
        {"exact", "task-equivalent", "mismatch", "not-measured", "not-applicable"},
        f"{path}.exactness",
    )
    task_attempted = _boolean(actual["task_attempted"], f"{path}.task_attempted")
    task_success = actual["task_success"]
    if task_attempted:
        if type(task_success) is not bool:
            raise ValidationError(f"{path}.task_success must be boolean for an attempted task")
        if actual["task_result_sha256"] is None:
            raise ValidationError(f"{path}.task_result_sha256 is required for an attempted task")
    elif task_success is not None:
        raise ValidationError(f"{path}.task_success must be null when no task was attempted")
    if not task_attempted and actual["task_result_sha256"] is not None:
        raise ValidationError(f"{path}.task_result_sha256 must be null when no task was attempted")
    _nullable_digest(actual["task_result_sha256"], f"{path}.task_result_sha256")
    if attempted:
        if sent + received == 0 or mode == "none":
            raise ValidationError(f"{path} attempted use needs messages and a mode")
    elif sent != 0 or received != 0 or mode != "none":
        raise ValidationError(f"{path} non-attempted use must have zero messages and mode none")
    if mode in {"urusilla", "mixed"} and adoption["decision"] != "adopted":
        raise ValidationError(f"{path} cannot use Urusilla without adoption")
    return actual


def _validate_contamination(value: Any, path: str) -> dict[str, Any]:
    disclosure = _object(value, path)
    _exact_keys(
        disclosure,
        (
            "shared_operator",
            "same_model_instance",
            "shared_system_prompt",
            "shared_conversation_state",
            "saw_prior_expected_outputs",
            "researcher_intervention",
            "project_authored_task",
            "details",
        ),
        path,
    )
    for key in (
        "shared_operator",
        "same_model_instance",
        "shared_system_prompt",
        "shared_conversation_state",
        "saw_prior_expected_outputs",
        "researcher_intervention",
        "project_authored_task",
    ):
        _boolean(disclosure[key], f"{path}.{key}")
    _string(disclosure["details"], f"{path}.details", maximum=2_048)
    return disclosure


TRANSCRIPT_MODES = {
    "urusilla",
    "structured-json",
    "concise-natural-language",
    "out-of-band",
}


def _validate_transcript(
    value: Any,
    path: str,
    participants: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    transcript = _list(
        value, path, minimum=1, maximum=MAX_TRANSCRIPT_ENTRIES
    )
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(transcript):
        entry_path = f"{path}[{index}]"
        entry = _object(raw, entry_path)
        _exact_keys(
            entry,
            (
                "sequence",
                "sender_id",
                "receiver_id",
                "kind",
                "mode",
                "content_sha256",
                "public_content",
                "exactness",
                "task_result",
                "fallback",
                "repair",
            ),
            entry_path,
        )
        sequence = _count(
            entry["sequence"],
            f"{entry_path}.sequence",
            maximum=MAX_TRANSCRIPT_ENTRIES,
        )
        if sequence != index + 1:
            raise ValidationError(f"{entry_path}.sequence must be {index + 1}")
        sender = _identifier(entry["sender_id"], f"{entry_path}.sender_id")
        receiver = _identifier(entry["receiver_id"], f"{entry_path}.receiver_id")
        if sender not in participants or receiver not in participants or sender == receiver:
            raise ValidationError(f"{entry_path} references invalid participants")
        _enum(
            entry["kind"],
            {
                "capsule-offer",
                "context-receipt",
                "gate-challenge",
                "gate-response",
                "task",
                "task-response",
                "retransmission",
                "acknowledgement",
                "repair",
                "fallback",
                "other",
            },
            f"{entry_path}.kind",
        )
        _enum(entry["mode"], TRANSCRIPT_MODES, f"{entry_path}.mode")
        if entry["kind"] in {"task", "task-response"} and entry["mode"] == "out-of-band":
            raise ValidationError(f"{entry_path} task traffic cannot be out-of-band")
        _digest(entry["content_sha256"], f"{entry_path}.content_sha256")
        public_content = _nullable_string(
            entry["public_content"],
            f"{entry_path}.public_content",
            maximum=8_192,
        )
        if public_content is not None:
            public_digest = "sha256:" + hashlib.sha256(
                public_content.encode("utf-8")
            ).hexdigest()
            if public_digest != entry["content_sha256"]:
                raise ValidationError(
                    f"{entry_path}.public_content does not match content_sha256"
                )
        _enum(
            entry["exactness"],
            {"exact", "task-equivalent", "mismatch", "not-measured", "not-applicable"},
            f"{entry_path}.exactness",
        )
        _enum(
            entry["task_result"],
            {"success", "failure", "not-applicable", "not-measured"},
            f"{entry_path}.task_result",
        )
        _boolean(entry["fallback"], f"{entry_path}.fallback")
        _boolean(entry["repair"], f"{entry_path}.repair")
        result.append(entry)
    return result


def _validate_retransmission(
    value: Any,
    path: str,
    hop: Mapping[str, Any],
    transcript: Sequence[Mapping[str, Any]],
    participants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    transmission = _object(value, path)
    _exact_keys(
        transmission,
        (
            "intended",
            "attempted",
            "downstream_receiver_id",
            "capsule_sha256",
            "result",
            "downstream_acknowledgement",
            "authorization",
            "utility_evaluation",
            "revocation",
        ),
        path,
    )
    intended = _boolean(transmission["intended"], f"{path}.intended")
    attempted = _boolean(transmission["attempted"], f"{path}.attempted")
    downstream = transmission["downstream_receiver_id"]
    capsule = transmission["capsule_sha256"]
    result = _enum(
        transmission["result"],
        {"acknowledged", "rejected", "failed", "no-response", "not-attempted"},
        f"{path}.result",
    )
    active = intended
    _validate_authorization(
        transmission["authorization"],
        f"{path}.authorization",
        action_active=active,
    )
    _validate_utility(
        transmission["utility_evaluation"],
        f"{path}.utility_evaluation",
        must_pass=active,
    )
    _validate_revocation(
        transmission["revocation"],
        f"{path}.revocation",
        must_be_available=active,
    )
    acknowledgement = _object(
        transmission["downstream_acknowledgement"],
        f"{path}.downstream_acknowledgement",
    )
    _exact_keys(
        acknowledgement,
        ("received", "capsule_sha256", "content_sha256"),
        f"{path}.downstream_acknowledgement",
    )
    ack_received = _boolean(
        acknowledgement["received"],
        f"{path}.downstream_acknowledgement.received",
    )
    ack_capsule = _nullable_digest(
        acknowledgement["capsule_sha256"],
        f"{path}.downstream_acknowledgement.capsule_sha256",
    )
    ack_content = _nullable_digest(
        acknowledgement["content_sha256"],
        f"{path}.downstream_acknowledgement.content_sha256",
    )
    if attempted:
        if not intended:
            raise ValidationError(f"{path}.attempted cannot be true when intended is false")
        downstream_id = _identifier(downstream, f"{path}.downstream_receiver_id")
        if downstream_id not in participants or downstream_id == hop["receiver_id"]:
            raise ValidationError(f"{path}.downstream_receiver_id is invalid")
        capsule_value = _digest(capsule, f"{path}.capsule_sha256")
        if capsule_value != hop["capsule_sha256"]:
            raise ValidationError(f"{path}.capsule_sha256 differs from the received capsule")
        if result == "not-attempted":
            raise ValidationError(f"{path}.result cannot be not-attempted after an attempt")
        if not any(
            entry["kind"] == "retransmission"
            and entry["sender_id"] == hop["receiver_id"]
            and entry["receiver_id"] == downstream_id
            for entry in transcript
        ):
            raise ValidationError(f"{path} attempted transmission is absent from the transcript")
    else:
        if result != "not-attempted":
            raise ValidationError(f"{path} non-attempted transmission must use not-attempted")
        if intended:
            downstream_id = _identifier(downstream, f"{path}.downstream_receiver_id")
            if downstream_id not in participants or downstream_id == hop["receiver_id"]:
                raise ValidationError(f"{path}.downstream_receiver_id is invalid")
            if _digest(capsule, f"{path}.capsule_sha256") != hop["capsule_sha256"]:
                raise ValidationError(f"{path}.capsule_sha256 differs from the received capsule")
        elif downstream is not None or capsule is not None:
            raise ValidationError(f"{path} unintended transmission must use null targets")
    if result == "acknowledged":
        if not ack_received or ack_capsule != capsule or ack_content is None:
            raise ValidationError(f"{path} acknowledged result lacks a matching acknowledgement")
        matching = [
            entry
            for entry in transcript
            if entry["kind"] == "acknowledgement"
            and entry["sender_id"] == downstream
            and entry["receiver_id"] == hop["receiver_id"]
            and entry["content_sha256"] == ack_content
        ]
        if not matching:
            raise ValidationError(f"{path} acknowledgement is absent from the transcript")
    elif ack_received or ack_capsule is not None or ack_content is not None:
        raise ValidationError(f"{path} has acknowledgement data without acknowledged result")
    return transmission


def _validate_fallback(
    value: Any, path: str, transcript: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    fallback = _object(value, path)
    _exact_keys(
        fallback,
        ("fallback_count", "repair_count", "fallback_mode", "causes"),
        path,
    )
    fallback_count = _count(fallback["fallback_count"], f"{path}.fallback_count")
    repair_count = _count(fallback["repair_count"], f"{path}.repair_count")
    fallback_mode = _enum(
        fallback["fallback_mode"],
        {"structured-json", "concise-natural-language", "mixed", "none"},
        f"{path}.fallback_mode",
    )
    causes = _list(fallback["causes"], f"{path}.causes", maximum=128)
    for index, cause in enumerate(causes):
        _string(cause, f"{path}.causes[{index}]", minimum=1, maximum=512)
    observed_fallbacks = sum(1 for entry in transcript if entry["fallback"])
    observed_repairs = sum(1 for entry in transcript if entry["repair"])
    if fallback_count != observed_fallbacks or repair_count != observed_repairs:
        raise ValidationError(f"{path} counts differ from the transcript flags")
    if fallback_count == 0 and fallback_mode != "none":
        raise ValidationError(f"{path}.fallback_mode must be none when no fallback occurred")
    if fallback_count > 0 and fallback_mode == "none":
        raise ValidationError(f"{path}.fallback_mode must identify the fallback")
    if fallback_count + repair_count > 0 and not causes:
        raise ValidationError(f"{path}.causes must explain fallback or repair activity")
    return fallback


def _validate_token_side(value: Any, path: str) -> dict[str, Any]:
    side = _object(value, path)
    _exact_keys(
        side,
        (*LEDGER_CATEGORIES, "task_total_tokens", "judge_tokens", "study_total_tokens"),
        path,
    )
    values = [_count(side[name], f"{path}.{name}") for name in LEDGER_CATEGORIES]
    task_total = _count(side["task_total_tokens"], f"{path}.task_total_tokens")
    judge = _count(side["judge_tokens"], f"{path}.judge_tokens")
    study_total = _count(side["study_total_tokens"], f"{path}.study_total_tokens")
    if task_total != sum(values):
        raise ValidationError(f"{path}.task_total_tokens differs from category sum")
    if study_total != task_total + judge:
        raise ValidationError(f"{path}.study_total_tokens must include judge_tokens once")
    return side


def _validate_token_ledger(value: Any, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = _object(value, path)
    _exact_keys(
        ledger,
        (
            "status",
            "accounting_method",
            "baseline",
            "candidate",
            "post_decode_api_input",
            "total_task_token_saving_percent",
        ),
        path,
    )
    status = _enum(ledger["status"], {"measured", "not-measured"}, f"{path}.status")
    method = _enum(
        ledger["accounting_method"],
        {"provider-reported", "tokenizer-estimate", "mixed", "not-measured"},
        f"{path}.accounting_method",
    )
    post = _object(ledger["post_decode_api_input"], f"{path}.post_decode_api_input")
    _exact_keys(
        post,
        ("status", "baseline_tokens", "candidate_tokens", "saving_percent"),
        f"{path}.post_decode_api_input",
    )
    post_status = _enum(
        post["status"],
        {"measured", "not-measured"},
        f"{path}.post_decode_api_input.status",
    )
    if status == "not-measured":
        if (
            method != "not-measured"
            or ledger["baseline"] is not None
            or ledger["candidate"] is not None
        ):
            raise ValidationError(f"{path} unmeasured ledger must not contain token sides")
        if ledger["total_task_token_saving_percent"] is not None:
            raise ValidationError(f"{path} unmeasured total saving must be null")
        if post_status != "not-measured" or any(
            post[key] is not None
            for key in ("baseline_tokens", "candidate_tokens", "saving_percent")
        ):
            raise ValidationError(f"{path} unmeasured post-decode ledger must contain null values")
        return ledger, {"status": "not-measured"}
    if method == "not-measured":
        raise ValidationError(f"{path}.accounting_method cannot be not-measured")
    baseline = _validate_token_side(ledger["baseline"], f"{path}.baseline")
    candidate = _validate_token_side(ledger["candidate"], f"{path}.candidate")
    expected_total = _expected_saving(
        baseline["task_total_tokens"], candidate["task_total_tokens"]
    )
    _require_percent_match(
        ledger["total_task_token_saving_percent"],
        expected_total,
        f"{path}.total_task_token_saving_percent",
    )
    if post_status != "measured":
        raise ValidationError(
            f"{path} measured ledger must explicitly measure post-decode API input"
        )
    post_baseline = _count(
        post["baseline_tokens"], f"{path}.post_decode_api_input.baseline_tokens"
    )
    post_candidate = _count(
        post["candidate_tokens"], f"{path}.post_decode_api_input.candidate_tokens"
    )
    if (
        post_baseline > baseline["task_total_tokens"]
        or post_candidate > candidate["task_total_tokens"]
    ):
        raise ValidationError(f"{path}.post_decode_api_input exceeds total task tokens")
    expected_post = _expected_saving(post_baseline, post_candidate)
    _require_percent_match(
        post["saving_percent"],
        expected_post,
        f"{path}.post_decode_api_input.saving_percent",
    )
    return ledger, {
        "status": "measured",
        "baseline_task_tokens": baseline["task_total_tokens"],
        "candidate_task_tokens": candidate["task_total_tokens"],
        "total_task_token_saving_percent": expected_total,
        "baseline_post_decode_api_input_tokens": post_baseline,
        "candidate_post_decode_api_input_tokens": post_candidate,
        "post_decode_api_input_saving_percent": expected_post,
    }


def _validate_safety(value: Any, path: str) -> dict[str, Any]:
    safety = _object(value, path)
    _exact_keys(
        safety,
        (
            "untrusted_code_executed",
            "executable_payload_accepted",
            "external_effect_authorized",
            "protocol_action_spent_money",
            "contains_chain_of_thought",
            "contains_secrets",
        ),
        path,
    )
    for key in safety:
        observed = _boolean(safety[key], f"{path}.{key}")
        if observed:
            raise ValidationError(f"{path}.{key} must be false for a public lab record")
    return safety


def _validate_hops(
    value: Any,
    protocol: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    hops = _list(value, "hops", minimum=1, maximum=MAX_HOPS)
    validated: list[dict[str, Any]] = []
    token_metrics: list[dict[str, Any]] = []
    warnings: list[str] = []
    by_index: dict[int, dict[str, Any]] = {}
    used_parent_indices: set[int] = set()
    for offset, raw in enumerate(hops):
        path = f"hops[{offset}]"
        hop = _object(raw, path)
        _exact_keys(
            hop,
            (
                "hop_index",
                "parent_hop",
                "sender_id",
                "receiver_id",
                "capsule_sha256",
                "parent_capsule_sha256",
                "received_context",
                "comprehension_gate",
                "adoption",
                "actual_use",
                "retransmission",
                "fallback_and_repair",
                "contamination",
                "transcript",
                "token_ledger",
                "safety",
                "notes",
            ),
            path,
        )
        hop_index = _count(hop["hop_index"], f"{path}.hop_index", maximum=MAX_HOPS)
        if hop_index != offset + 1:
            raise ValidationError(f"{path}.hop_index must be {offset + 1}")
        sender = _identifier(hop["sender_id"], f"{path}.sender_id")
        receiver = _identifier(hop["receiver_id"], f"{path}.receiver_id")
        if sender not in participants or receiver not in participants or sender == receiver:
            raise ValidationError(f"{path} references invalid participants")
        capsule = _digest(hop["capsule_sha256"], f"{path}.capsule_sha256")
        parent_capsule = _digest(
            hop["parent_capsule_sha256"], f"{path}.parent_capsule_sha256"
        )
        parent_index = hop["parent_hop"]
        if parent_index is None:
            if offset != 0:
                raise ValidationError(f"{path}.parent_hop may be null only for the first hop")
            if (
                capsule != protocol["capsule_sha256"]
                or parent_capsule != protocol["capsule_sha256"]
            ):
                raise ValidationError(
                    f"{path} root capsule does not match protocol.capsule_sha256"
                )
        else:
            parent_index = _count(parent_index, f"{path}.parent_hop", maximum=MAX_HOPS)
            if parent_index not in by_index:
                raise ValidationError(f"{path}.parent_hop must identify an earlier hop")
            if parent_index in used_parent_indices:
                raise ValidationError(
                    f"{path}.parent_hop reuses a single-target retransmission"
                )
            used_parent_indices.add(parent_index)
            parent = by_index[parent_index]
            if sender != parent["receiver_id"]:
                raise ValidationError(f"{path}.sender_id must be the parent hop receiver")
            if capsule != parent["capsule_sha256"] or parent_capsule != parent["capsule_sha256"]:
                raise ValidationError(f"{path} capsule digest differs from its parent")
            parent_tx = parent["retransmission"]
            if (
                parent_tx["result"] != "acknowledged"
                or parent_tx["downstream_receiver_id"] != receiver
                or parent_tx["capsule_sha256"] != capsule
            ):
                raise ValidationError(
                    f"{path} is not linked to an acknowledged parent retransmission"
                )

        context = _validate_context(hop["received_context"], f"{path}.received_context")
        gate = _validate_gate(hop["comprehension_gate"], f"{path}.comprehension_gate")
        adoption = _validate_adoption(hop["adoption"], f"{path}.adoption", gate, context)
        actual = _validate_actual_use(hop["actual_use"], f"{path}.actual_use", adoption)
        contamination = _validate_contamination(hop["contamination"], f"{path}.contamination")
        transcript = _validate_transcript(hop["transcript"], f"{path}.transcript", participants)
        transmission = _validate_retransmission(
            hop["retransmission"],
            f"{path}.retransmission",
            hop,
            transcript,
            participants,
        )
        _validate_fallback(hop["fallback_and_repair"], f"{path}.fallback_and_repair", transcript)
        _, metrics = _validate_token_ledger(hop["token_ledger"], f"{path}.token_ledger")
        _validate_safety(hop["safety"], f"{path}.safety")
        _string(hop["notes"], f"{path}.notes", maximum=2_048)

        if actual["attempted"]:
            matching_modes = {
                "urusilla": {"urusilla"},
                "structured-json": {"structured-json"},
                "concise-natural-language": {"concise-natural-language"},
                "mixed": {
                    "urusilla",
                    "structured-json",
                    "concise-natural-language",
                },
            }[actual["mode"]]
            actual_entries = [
                entry
                for entry in transcript
                if entry["kind"] in {"task", "task-response"}
                and entry["mode"] in matching_modes
            ]
            if not actual_entries:
                raise ValidationError(f"{path}.actual_use has no matching task transcript entry")
            observed_sent = sum(
                entry["sender_id"] == receiver for entry in actual_entries
            )
            observed_received = sum(
                entry["receiver_id"] == receiver for entry in actual_entries
            )
            if (
                observed_sent != actual["messages_sent"]
                or observed_received != actual["messages_received"]
            ):
                raise ValidationError(
                    f"{path}.actual_use message counts differ from matching "
                    "task transcript entries"
                )
            exactnesses = {entry["exactness"] for entry in actual_entries}
            if actual["exactness"] == "exact" and exactnesses != {"exact"}:
                raise ValidationError(f"{path}.actual_use exactness differs from transcript")
            if actual["exactness"] == "task-equivalent" and not exactnesses.issubset(
                {"exact", "task-equivalent"}
            ):
                raise ValidationError(f"{path}.actual_use exactness differs from transcript")
            if actual["exactness"] == "mismatch" and "mismatch" not in exactnesses:
                raise ValidationError(f"{path}.actual_use mismatch is absent from transcript")
        if actual["task_attempted"]:
            expected_result = "success" if actual["task_success"] else "failure"
            if not any(
                entry["kind"] == "task-response"
                and entry["sender_id"] == receiver
                and entry["task_result"] == expected_result
                and entry["content_sha256"] == actual["task_result_sha256"]
                for entry in transcript
            ):
                raise ValidationError(f"{path}.actual_use task result is absent from transcript")

        if not gate["passed"]:
            warnings.append(f"hop {hop_index}: comprehension gate did not pass")
        if adoption["decision"] != "adopted":
            warnings.append(f"hop {hop_index}: receiver did not adopt Urusilla")
        if actual["exactness"] in {"mismatch", "not-measured"}:
            warnings.append(f"hop {hop_index}: message exactness is {actual['exactness']}")
        if actual["task_attempted"] and actual["task_success"] is False:
            warnings.append(f"hop {hop_index}: task failed")
        if metrics["status"] == "not-measured":
            warnings.append(f"hop {hop_index}: token ledger was not measured")
        elif (metrics["post_decode_api_input_saving_percent"] or 0.0) <= 0.0:
            warnings.append(
                f"hop {hop_index}: post-decode API-input saving is not positive"
            )
        if any(
            contamination[key]
            for key in (
                "shared_operator",
                "same_model_instance",
                "shared_system_prompt",
                "shared_conversation_state",
                "saw_prior_expected_outputs",
                "researcher_intervention",
                "project_authored_task",
            )
        ):
            warnings.append(f"hop {hop_index}: disclosed contamination limits independence")

        token_metrics.append(metrics)
        validated.append(hop)
        by_index[hop_index] = hop
    return validated, token_metrics, warnings


SUMMARY_FIELDS = (
    "attempted_hops",
    "comprehension_passed_hops",
    "adopted_hops",
    "actual_use_hops",
    "successful_task_hops",
    "retransmission_attempts",
    "downstream_acknowledgements",
    "longest_acknowledged_propagation_depth",
    "disclosed_independent_receiver_hops",
    "negative_or_null_hops",
)


def compute_summary(
    hops: Sequence[Mapping[str, Any]],
    participants: Mapping[str, Mapping[str, Any]],
    token_metrics: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    negative = 0
    depths: dict[int, int] = {}
    for hop, metrics in zip(hops, token_metrics, strict=True):
        index = hop["hop_index"]
        parent = hop["parent_hop"]
        depths[index] = 1 if parent is None else depths[parent] + 1
        actual = hop["actual_use"]
        token_not_positive = (
            metrics["status"] == "not-measured"
            or (metrics["post_decode_api_input_saving_percent"] or 0.0) <= 0.0
        )
        if (
            not hop["comprehension_gate"]["passed"]
            or hop["adoption"]["decision"] != "adopted"
            or not actual["attempted"]
            or actual["exactness"] in {"mismatch", "not-measured", "not-applicable"}
            or (actual["task_attempted"] and actual["task_success"] is False)
            or token_not_positive
        ):
            negative += 1
    return {
        "attempted_hops": len(hops),
        "comprehension_passed_hops": sum(
            bool(hop["comprehension_gate"]["passed"]) for hop in hops
        ),
        "adopted_hops": sum(hop["adoption"]["decision"] == "adopted" for hop in hops),
        "actual_use_hops": sum(bool(hop["actual_use"]["attempted"]) for hop in hops),
        "successful_task_hops": sum(
            hop["actual_use"]["task_attempted"] and hop["actual_use"]["task_success"] is True
            for hop in hops
        ),
        "retransmission_attempts": sum(
            bool(hop["retransmission"]["attempted"]) for hop in hops
        ),
        "downstream_acknowledgements": sum(
            hop["retransmission"]["result"] == "acknowledged" for hop in hops
        ),
        "longest_acknowledged_propagation_depth": max(depths.values()),
        "disclosed_independent_receiver_hops": sum(
            participants[hop["receiver_id"]]["relationship_to_project"] == "independent"
            for hop in hops
        ),
        "negative_or_null_hops": negative,
    }


def _validate_claim_boundary(value: Any) -> dict[str, Any]:
    boundary = _object(value, "claim_boundary")
    _exact_keys(
        boundary,
        (
            "submission_scope",
            "recorded_broad_post_decode_api_input_saving_percent",
            "changes_project_wide_claim",
            "sota_claim",
            "external_adoption_claim",
        ),
        "claim_boundary",
    )
    if boundary["submission_scope"] != "single-propagation-chain":
        raise ValidationError(
            "claim_boundary.submission_scope must be single-propagation-chain"
        )
    broad = _finite_percent(
        boundary["recorded_broad_post_decode_api_input_saving_percent"],
        "claim_boundary.recorded_broad_post_decode_api_input_saving_percent",
    )
    if broad != 0.0:
        raise ValidationError(
            "claim_boundary must preserve the currently recorded broad 0% result"
        )
    for key in ("changes_project_wide_claim", "sota_claim", "external_adoption_claim"):
        if _boolean(boundary[key], f"claim_boundary.{key}"):
            raise ValidationError(f"claim_boundary.{key} must be false for one submitted chain")
    return boundary


def validate_record(value: Any) -> dict[str, Any]:
    record = _object(value, "record")
    _exact_keys(
        record,
        (
            "schema_version",
            "chain_id",
            "created_at",
            "protocol",
            "evidence",
            "participants",
            "hops",
            "chain_summary",
            "claim_boundary",
            "notes",
        ),
        "record",
    )
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValidationError(f"schema_version must be {SCHEMA_VERSION}")
    _identifier(record["chain_id"], "chain_id")
    _validate_timestamp(record["created_at"], "created_at")
    protocol = _validate_protocol(record["protocol"])
    evidence = _validate_evidence(record["evidence"])
    _, participants = _validate_participants(record["participants"])
    hops, token_metrics, warnings = _validate_hops(
        record["hops"], protocol, participants
    )
    expected_summary = compute_summary(hops, participants, token_metrics)
    summary = _object(record["chain_summary"], "chain_summary")
    _exact_keys(summary, SUMMARY_FIELDS, "chain_summary")
    for key, expected in expected_summary.items():
        observed = _count(summary[key], f"chain_summary.{key}", maximum=MAX_HOPS)
        if observed != expected:
            raise ValidationError(
                f"chain_summary.{key} must equal recomputed value {expected}"
            )
    _validate_claim_boundary(record["claim_boundary"])
    _string(record["notes"], "notes", maximum=4_096)

    if evidence["evidence_tier"] != "independently-observed":
        warnings.append(
            "the recorder did not classify this chain as independently observed"
        )
    if not evidence["premeasurement_sealed"]:
        warnings.append("the chain was not premeasurement-sealed")
    if not evidence["artifacts_public"]:
        warnings.append("supporting artifacts are not public")
    if not protocol["capsule_signature_verified"]:
        warnings.append("the Capsule signature was not verified")

    authorization_summary = {
        "standing_policy_adoptions": sum(
            hop["adoption"]["decision"] == "adopted"
            and hop["adoption"]["authorization"]["authorization_basis"]
            == "standing-policy"
            for hop in hops
        ),
        "interactive_approval_adoptions": sum(
            hop["adoption"]["decision"] == "adopted"
            and hop["adoption"]["authorization"]["authorization_basis"]
            == "interactive-approval"
            for hop in hops
        ),
        "standing_policy_retransmission_intents": sum(
            hop["retransmission"]["intended"]
            and hop["retransmission"]["authorization"]["authorization_basis"]
            == "standing-policy"
            for hop in hops
        ),
        "interactive_approval_retransmission_intents": sum(
            hop["retransmission"]["intended"]
            and hop["retransmission"]["authorization"]["authorization_basis"]
            == "interactive-approval"
            for hop in hops
        ),
        "revoked_actions": sum(
            hop[action]["revocation"]["result"] == "revoked"
            for hop in hops
            for action in ("adoption", "retransmission")
        ),
        "failed_revocations": sum(
            hop[action]["revocation"]["result"] == "failed"
            for hop in hops
            for action in ("adoption", "retransmission")
        ),
    }

    measured = [metric for metric in token_metrics if metric["status"] == "measured"]
    aggregate: dict[str, Any] = {"status": "not-measured"}
    if len(measured) == len(token_metrics):
        baseline_task = sum(item["baseline_task_tokens"] for item in measured)
        candidate_task = sum(item["candidate_task_tokens"] for item in measured)
        baseline_post = sum(
            item["baseline_post_decode_api_input_tokens"] for item in measured
        )
        candidate_post = sum(
            item["candidate_post_decode_api_input_tokens"] for item in measured
        )
        aggregate = {
            "status": "measured",
            "baseline_task_tokens": baseline_task,
            "candidate_task_tokens": candidate_task,
            "total_task_token_saving_percent": _expected_saving(
                baseline_task, candidate_task
            ),
            "baseline_post_decode_api_input_tokens": baseline_post,
            "candidate_post_decode_api_input_tokens": candidate_post,
            "post_decode_api_input_saving_percent": _expected_saving(
                baseline_post, candidate_post
            ),
        }
    return {
        "valid": True,
        "schema_version": SCHEMA_VERSION,
        "chain_sha256": sha256_ref(record),
        "negative_evidence_accepted": True,
        "structural_validation_only": True,
        "chain_summary": expected_summary,
        "authorization_summary": authorization_summary,
        "aggregate_token_metrics": aggregate,
        "recorded_project_broad_post_decode_api_input_saving_percent": 0.0,
        "project_wide_claim_changed": False,
        "warnings": sorted(set(warnings)),
    }


def _token_side(**overrides: int) -> dict[str, int]:
    side = {name: 0 for name in LEDGER_CATEGORIES}
    side.update(overrides)
    side["task_total_tokens"] = sum(side[name] for name in LEDGER_CATEGORIES)
    side["judge_tokens"] = 0
    side["study_total_tokens"] = side["task_total_tokens"]
    return side


def build_sample(*, chain_id: str | None = None, created_at: str | None = None) -> dict[str, Any]:
    """Build a valid two-hop, project-authored example with a negative token result."""

    chain_id = chain_id or f"chain-{uuid.uuid4().hex[:16]}"
    created_at = created_at or (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    capsule = CAPSULE_SHA256
    participants = [
        {
            "id": "origin-agent",
            "operator_id": "sample-operator",
            "relationship_to_project": "same-project",
            "runtime": {"provider": "example", "model": "origin", "version": "1"},
            "disclosure": "Synthetic origin used only to demonstrate the record format.",
        },
        {
            "id": "relay-agent",
            "operator_id": "sample-operator",
            "relationship_to_project": "same-project",
            "runtime": {"provider": "example", "model": "relay", "version": "1"},
            "disclosure": "Synthetic relay; not an independent adopter.",
        },
        {
            "id": "downstream-agent",
            "operator_id": "sample-operator",
            "relationship_to_project": "same-project",
            "runtime": {"provider": "example", "model": "downstream", "version": "1"},
            "disclosure": "Synthetic downstream receiver; not an external deployment.",
        },
    ]

    def entry(
        sequence: int,
        sender: str,
        receiver: str,
        kind: str,
        mode: str,
        marker: str,
        *,
        exactness: str = "not-applicable",
        task_result: str = "not-applicable",
    ) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "sender_id": sender,
            "receiver_id": receiver,
            "kind": kind,
            "mode": mode,
            "content_sha256": "sha256:" + hashlib.sha256(marker.encode()).hexdigest(),
            "public_content": None,
            "exactness": exactness,
            "task_result": task_result,
            "fallback": False,
            "repair": False,
        }

    hop1_transcript = [
        entry(1, "origin-agent", "relay-agent", "capsule-offer", "out-of-band", "h1-offer"),
        entry(
            2,
            "relay-agent",
            "origin-agent",
            "gate-challenge",
            "structured-json",
            "h1-challenge",
        ),
        entry(3, "origin-agent", "relay-agent", "gate-response", "structured-json", "h1-gate"),
        entry(4, "origin-agent", "relay-agent", "task", "urusilla", "h1-task", exactness="exact"),
        entry(
            5,
            "relay-agent",
            "origin-agent",
            "task-response",
            "urusilla",
            "h1-result",
            exactness="exact",
            task_result="success",
        ),
        entry(
            6,
            "relay-agent",
            "downstream-agent",
            "retransmission",
            "out-of-band",
            "h1-retransmit",
        ),
        entry(7, "downstream-agent", "relay-agent", "acknowledgement", "out-of-band", "h1-ack"),
    ]
    hop2_transcript = [
        entry(
            1,
            "relay-agent",
            "downstream-agent",
            "capsule-offer",
            "out-of-band",
            "h1-retransmit",
        ),
        entry(
            2,
            "downstream-agent",
            "relay-agent",
            "gate-challenge",
            "structured-json",
            "h2-challenge",
        ),
        entry(3, "relay-agent", "downstream-agent", "gate-response", "structured-json", "h2-gate"),
        entry(
            4,
            "relay-agent",
            "downstream-agent",
            "task",
            "urusilla",
            "h2-task",
            exactness="exact",
        ),
        entry(
            5,
            "downstream-agent",
            "relay-agent",
            "task-response",
            "urusilla",
            "h2-result",
            exactness="exact",
            task_result="success",
        ),
    ]

    def context(marker: str, description: str) -> dict[str, Any]:
        return {
            "kind": "capsule-with-examples",
            "context_sha256": "sha256:" + hashlib.sha256(marker.encode()).hexdigest(),
            "context_bytes": 1_024,
            "context_input_tokens": 256,
            "capsule_digest_verified": True,
            "included_capsule": True,
            "included_examples": True,
            "included_prior_transcript": False,
            "included_evaluator_instructions": True,
            "included_executable_code": False,
            "description": description,
        }

    def gate() -> dict[str, Any]:
        return {
            "attempted": True,
            "positive_cases": {"total": 2, "passed": 2},
            "negative_cases": {"total": 2, "passed": 2},
            "exact_reconstruction_cases": {"total": 2, "passed": 2},
            "passed": True,
            "failures": [],
        }

    def authorization(active: bool) -> dict[str, Any]:
        return {
            "authorization_basis": "standing-policy" if active else "none",
            "authorization_evidence_sha256": (
                "sha256:" + hashlib.sha256(b"sample-standing-policy").hexdigest()
                if active
                else None
            ),
            "read_only": True,
            "reversible_participation": True,
            "state_persistence_authorized": False,
            "spending_authorized": False,
            "external_effects_authorized": False,
        }

    def utility(active: bool) -> dict[str, Any]:
        return {
            "evaluated": active,
            "metric": "expected-mutual-utility",
            "observed_value": 1.0 if active else None,
            "minimum_threshold": 0.0 if active else None,
            "passed": active,
            "evidence_sha256": (
                "sha256:" + hashlib.sha256(b"sample-utility-evidence").hexdigest()
                if active
                else None
            ),
        }

    def revocation(active: bool) -> dict[str, Any]:
        return {
            "available": active,
            "invoked": False,
            "result": "not-invoked" if active else "not-applicable",
            "evidence_sha256": None,
        }

    def adoption() -> dict[str, Any]:
        return {
            "decision": "adopted",
            "scope": "session",
            "mechanism": "declarative-read",
            "authorization": authorization(True),
            "utility_evaluation": utility(True),
            "revocation": revocation(True),
            "reason": "All local comprehension checks passed for this session only.",
        }

    def contamination(details: str) -> dict[str, Any]:
        return {
            "shared_operator": True,
            "same_model_instance": False,
            "shared_system_prompt": False,
            "shared_conversation_state": False,
            "saw_prior_expected_outputs": False,
            "researcher_intervention": False,
            "project_authored_task": True,
            "details": details,
        }

    def safety() -> dict[str, bool]:
        return {
            "untrusted_code_executed": False,
            "executable_payload_accepted": False,
            "external_effect_authorized": False,
            "protocol_action_spent_money": False,
            "contains_chain_of_thought": False,
            "contains_secrets": False,
        }

    baseline1 = _token_side(
        task_input=100,
        system_role=20,
        agent_input_history=30,
        agent_output_visible=20,
        final_answer=10,
    )
    candidate1 = _token_side(
        task_input=100,
        system_role=20,
        agent_input_history=30,
        agent_output_visible=18,
        final_answer=10,
        negotiation_profile=5,
    )
    baseline2 = _token_side(
        task_input=60,
        system_role=10,
        agent_input_history=10,
        agent_output_visible=10,
        final_answer=10,
    )
    candidate2 = _token_side(
        task_input=60,
        system_role=10,
        agent_input_history=10,
        agent_output_visible=8,
        final_answer=10,
        negotiation_profile=3,
    )

    def ledger(
        baseline: dict[str, int],
        candidate: dict[str, int],
        post_decode_tokens: int,
    ) -> dict[str, Any]:
        return {
            "status": "measured",
            "accounting_method": "tokenizer-estimate",
            "baseline": baseline,
            "candidate": candidate,
            "post_decode_api_input": {
                "status": "measured",
                "baseline_tokens": post_decode_tokens,
                "candidate_tokens": post_decode_tokens,
                "saving_percent": 0.0,
            },
            "total_task_token_saving_percent": _expected_saving(
                baseline["task_total_tokens"], candidate["task_total_tokens"]
            ),
        }

    hops = [
        {
            "hop_index": 1,
            "parent_hop": None,
            "sender_id": "origin-agent",
            "receiver_id": "relay-agent",
            "capsule_sha256": capsule,
            "parent_capsule_sha256": capsule,
            "received_context": context("hop-1-context", "Capsule and two public examples."),
            "comprehension_gate": gate(),
            "adoption": adoption(),
            "actual_use": {
                "attempted": True,
                "mode": "urusilla",
                "messages_sent": 1,
                "messages_received": 1,
                "exactness": "exact",
                "task_attempted": True,
                "task_success": True,
                "task_result_sha256": hop1_transcript[4]["content_sha256"],
            },
            "retransmission": {
                "intended": True,
                "attempted": True,
                "downstream_receiver_id": "downstream-agent",
                "capsule_sha256": capsule,
                "result": "acknowledged",
                "downstream_acknowledgement": {
                    "received": True,
                    "capsule_sha256": capsule,
                    "content_sha256": hop1_transcript[-1]["content_sha256"],
                },
                "authorization": authorization(True),
                "utility_evaluation": utility(True),
                "revocation": revocation(True),
            },
            "fallback_and_repair": {
                "fallback_count": 0,
                "repair_count": 0,
                "fallback_mode": "none",
                "causes": [],
            },
            "contamination": contamination(
                "All sample participants share one synthetic operator."
            ),
            "transcript": hop1_transcript,
            "token_ledger": ledger(baseline1, candidate1, 150),
            "safety": safety(),
            "notes": "Successful synthetic hop with 0% post-decode API-input saving.",
        },
        {
            "hop_index": 2,
            "parent_hop": 1,
            "sender_id": "relay-agent",
            "receiver_id": "downstream-agent",
            "capsule_sha256": capsule,
            "parent_capsule_sha256": capsule,
            "received_context": context(
                "hop-2-context", "Retransmitted Capsule and public examples."
            ),
            "comprehension_gate": gate(),
            "adoption": adoption(),
            "actual_use": {
                "attempted": True,
                "mode": "urusilla",
                "messages_sent": 1,
                "messages_received": 1,
                "exactness": "exact",
                "task_attempted": True,
                "task_success": True,
                "task_result_sha256": hop2_transcript[4]["content_sha256"],
            },
            "retransmission": {
                "intended": False,
                "attempted": False,
                "downstream_receiver_id": None,
                "capsule_sha256": None,
                "result": "not-attempted",
                "downstream_acknowledgement": {
                    "received": False,
                    "capsule_sha256": None,
                    "content_sha256": None,
                },
                "authorization": authorization(False),
                "utility_evaluation": utility(False),
                "revocation": revocation(False),
            },
            "fallback_and_repair": {
                "fallback_count": 0,
                "repair_count": 0,
                "fallback_mode": "none",
                "causes": [],
            },
            "contamination": contamination(
                "Same synthetic operator; this is not independent evidence."
            ),
            "transcript": hop2_transcript,
            "token_ledger": ledger(baseline2, candidate2, 80),
            "safety": safety(),
            "notes": "Second synthetic hop; task succeeds but token cost regresses slightly.",
        },
    ]
    token_metrics = [
        {
            "status": "measured",
            "post_decode_api_input_saving_percent": 0.0,
        },
        {
            "status": "measured",
            "post_decode_api_input_saving_percent": 0.0,
        },
    ]
    participant_map = {participant["id"]: participant for participant in participants}
    return {
        "schema_version": SCHEMA_VERSION,
        "chain_id": chain_id,
        "created_at": created_at,
        "protocol": {
            "project": "Urusilla",
            "language_version": "0.1.0",
            "capsule_uri": (
                "https://github.com/jaden3824/urusilla/releases/download/"
                "v0.1.0-experimental/urusilla_capsule_v0_1.json"
            ),
            "capsule_sha256": capsule,
            "capsule_signature_verified": False,
            "capsule_signature_evidence_sha256": None,
        },
        "evidence": {
            "recorder": "Urusilla Interop Lab sample generator",
            "evidence_tier": "project-authored",
            "premeasurement_sealed": False,
            "collection_method": (
                "Synthetic two-hop format demonstration; no provider or network calls."
            ),
            "artifacts_public": True,
        },
        "participants": participants,
        "hops": hops,
        "chain_summary": compute_summary(hops, participant_map, token_metrics),
        "claim_boundary": {
            "submission_scope": "single-propagation-chain",
            "recorded_broad_post_decode_api_input_saving_percent": 0.0,
            "changes_project_wide_claim": False,
            "sota_claim": False,
            "external_adoption_claim": False,
        },
        "notes": (
            "This sample proves only that the record format validates. Its negative token "
            "result is intentional and accepted."
        ),
    }


def _write_new(path: Path, value: Any) -> None:
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    except FileExistsError as exc:
        raise ValidationError(f"refusing to overwrite existing file: {path}") from exc
    except OSError as exc:
        raise ValidationError(f"cannot write {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate declarative Urusilla propagation-chain evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate one JSON record")
    validate.add_argument("record", type=Path)
    validate.add_argument("--json", action="store_true", help="emit a JSON report")
    initialize = subparsers.add_parser("init", help="write a valid editable sample")
    initialize.add_argument("output", type=Path)
    initialize.add_argument("--chain-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            sample = build_sample(chain_id=args.chain_id)
            validate_record(sample)
            _write_new(args.output, sample)
            print(f"wrote {args.output}")
            return 0
        report = validate_record(load_record(args.record))
    except ValidationError as exc:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"valid": False, "error": str(exc)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        aggregate = report["aggregate_token_metrics"]
        print(f"valid: {report['chain_sha256']}")
        print(
            "propagation: "
            f"{report['chain_summary']['longest_acknowledged_propagation_depth']} hops; "
            f"{report['chain_summary']['downstream_acknowledgements']} downstream acknowledgements"
        )
        if aggregate["status"] == "measured":
            post_saving = aggregate["post_decode_api_input_saving_percent"]
            total_saving = aggregate["total_task_token_saving_percent"]
            print(
                "post-decode API-input saving: "
                + ("undefined (zero baseline)" if post_saving is None else f"{post_saving:.6g}%")
            )
            print(
                "total task-token saving: "
                + ("undefined (zero baseline)" if total_saving is None else f"{total_saving:.6g}%")
            )
        else:
            print("token result: not measured")
        print("negative evidence accepted: yes")
        print("project-wide broad post-decode baseline remains: 0%")
        for warning in report["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
