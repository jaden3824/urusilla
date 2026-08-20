#!/usr/bin/env python3
"""CAMEL-native, offline-first Urusilla reproduction adapter.

The CLI is deliberately offline-only.  It builds and validates immutable
plans, validates already-collected CAMEL captures, and maps them into the
public Interop Lab schema.  The optional :func:`run_camel_trial` path imports
CAMEL lazily and remains closed unless the caller supplies both a byte-bound
preflight receipt and an explicit, bounded external-call authorization.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import inspect
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence

try:
    from interop_lab.interop_lab import (
        CAPSULE_SHA256,
        LEDGER_CATEGORIES,
        ValidationError,
        _write_new,
        build_sample,
        compute_summary,
        load_record,
        sha256_ref,
        strict_json_loads,
        validate_record,
    )
except ImportError:  # Support direct execution from the repository root.
    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from interop_lab.interop_lab import (  # type: ignore[no-redef]
        CAPSULE_SHA256,
        LEDGER_CATEGORIES,
        ValidationError,
        _write_new,
        build_sample,
        compute_summary,
        load_record,
        sha256_ref,
        strict_json_loads,
        validate_record,
    )


CAMEL_VERSION = "0.2.90"
CAMEL_REQUIREMENT = f"camel-ai=={CAMEL_VERSION}"
MCP_REQUIREMENT = "mcp>=1.3,<2"
PYTHON_REQUIREMENT = ">=3.10,<3.15"
PLAN_SCHEMA_VERSION = "urusilla-camel-reproduction-plan/1"
PREFLIGHT_SCHEMA_VERSION = "urusilla-camel-offline-preflight/1"
CAPTURE_SCHEMA_VERSION = "urusilla-camel-capture/1"
MAX_EXTERNAL_CALLS = 3
MAX_CAPSULE_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 65_536
ARM_IDS = ("raw", "structured-json", "urusilla")
EXPERIMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,47}$")

SYSTEM_MESSAGE = (
    "You are a read-only participant in a bounded public synthetic evaluation. "
    "Use no tools, external tools, memory, network actions, persistence, "
    "spending, permission changes, or external effects. Return only the "
    "requested public JSON answer and do not reveal private chain-of-thought."
)

EXPECTED_STATE = {
    "feasible_plans": ["plan-a", "plan-b"],
    "selected_plan": None,
    "would_execute": False,
}

TASK_SEMANTICS = {
    "task_id": "ambiguous-plan-selection-v1",
    "instruction": (
        "Identify every feasible plan. Select a plan only if the supplied facts "
        "uniquely justify one; otherwise return null and preserve ambiguity."
    ),
    "plans": [
        {
            "id": "plan-a",
            "cost_usd": 0.20,
            "network_required": False,
            "verification_passes": 1,
        },
        {
            "id": "plan-b",
            "cost_usd": 0.70,
            "network_required": False,
            "verification_passes": 2,
        },
    ],
    "hard_constraints": {"budget_usd_lte": 1.00, "network_allowed": False},
    "utility_tie_breaker": None,
    "expected_public_state": EXPECTED_STATE,
}

ANSWER_CONTRACT = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_semantics_sha256",
        "reconstructed_state",
        "reason",
        "format_decision",
    ],
    "properties": {
        "task_semantics_sha256": {"type": "string"},
        "reconstructed_state": {
            "type": "object",
            "additionalProperties": False,
            "required": ["feasible_plans", "selected_plan", "would_execute"],
        },
        "reason": {"type": "string"},
        "format_decision": {"const": "session-only-before-answer"},
    },
}

FROZEN_RUNTIME_POLICY = {
    "direct_chat_agent_sequence": True,
    "role_playing_used": False,
    "workforce_used": False,
    "tools": [],
    "external_tools": [],
    "memory": None,
    "max_iteration": 1,
    "summarize_threshold": None,
    "retry_attempts": 1,
    "stream": False,
    "fresh_chat_agent_per_arm": True,
    "fresh_model_per_arm": True,
    "call_cap": MAX_EXTERNAL_CALLS,
}

FROZEN_SAFETY_ATTESTATION = {
    "tools_supplied": False,
    "external_tools_supplied": False,
    "memory_supplied": False,
    "persistence_authorized": False,
    "protocol_authorized_spending": False,
    "permission_expansion_authorized": False,
    "external_effects_authorized": False,
    "untrusted_code_executed": False,
    "contains_chain_of_thought": False,
    "contains_secrets": False,
}

FROZEN_CLAIM_BOUNDARY = {
    "negative_and_null_evidence_accepted": True,
    "complete_total_task_tokens_measured": False,
    "recorded_broad_post_decode_api_input_saving_percent": 0.0,
    "changes_project_wide_claim": False,
    "sota_claim": False,
    "external_adoption_claim": False,
}


class CamelAdapterError(ValidationError):
    """Raised when a CAMEL plan, capture, or guarded live path is unsafe."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_timestamp(value: Any, path: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise CamelAdapterError(f"{path} must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CamelAdapterError(f"{path} is not a valid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise CamelAdapterError(f"{path} must be UTC")
    return value


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CamelAdapterError(f"{path} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CamelAdapterError(
            f"{path} fields differ; missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _string(value: Any, path: str, *, minimum: int = 1, maximum: int = 4096) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        raise CamelAdapterError(
            f"{path} must be a string of {minimum}..{maximum} characters"
        )
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise CamelAdapterError(f"{path} must be a nonnegative integer")
    return value


def _sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_capsule(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CamelAdapterError(f"cannot read Capsule {path}: {exc}") from exc
    if not raw or len(raw) > MAX_CAPSULE_BYTES:
        raise CamelAdapterError(
            f"Capsule must contain 1..{MAX_CAPSULE_BYTES} bytes"
        )
    observed = "sha256:" + hashlib.sha256(raw).hexdigest()
    if observed != CAPSULE_SHA256:
        raise CamelAdapterError(
            f"Capsule digest mismatch: expected {CAPSULE_SHA256}, observed {observed}"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CamelAdapterError("Capsule is not UTF-8") from exc
    capsule = strict_json_loads(text)
    if type(capsule) is not dict or capsule.get("release_status") != "experimental-unsigned":
        raise CamelAdapterError("Capsule must be the frozen unsigned declaration")
    return text


def _load_reference_codec() -> tuple[
    Callable[[Mapping[str, Any]], dict[str, Any]],
    Callable[[Mapping[str, Any]], bytes],
    Callable[[bytes], dict[str, Any]],
]:
    root = str(_repo_root())
    added = False
    if root not in sys.path:
        sys.path.insert(0, root)
        added = True
    try:
        from urusilla import decode_message, encode_message, normalize_message
    except (ImportError, OSError) as exc:
        raise CamelAdapterError(
            "the trusted local Urusilla reference codec is unavailable"
        ) from exc
    finally:
        if added:
            sys.path.remove(root)
    return normalize_message, encode_message, decode_message


def _request_message() -> dict[str, Any]:
    normalize_message, encode_message, decode_message = _load_reference_codec()
    message = normalize_message(
        {
            "id": "018f4f2e-1d33-7b62-8af8-5a09497d34b1",
            "session": "018f4f2e-0ea2-7cad-a224-b98558052765",
            "sender": "reproduction.seed",
            "recipients": ["camel.receiver"],
            "act": "REQUEST",
            "schema": "urn:urusilla:interop:ambiguous-plan-selection:1",
            "logical_clock": 1,
            "expires_ms": 0,
            "confidence_ppm": 1_000_000,
            "expected": ["RESOLVE"],
            "body": {
                "kind": "goal",
                "condition": {
                    "kind": "claim",
                    "predicate": "plan.selection.requested",
                    "arguments": [TASK_SEMANTICS],
                },
                "constraints": [
                    {
                        "kind": "constraint",
                        "scope": "execution",
                        "mode": "hard",
                        "condition": {
                            "read_only": True,
                            "network_allowed": False,
                            "external_effects_allowed": False,
                        },
                    }
                ],
            },
            "meta": {
                "experiment": "camel-minimal-reproduction-v1",
                "permission": "session-only-read-only-no-effects",
            },
        }
    )
    frame = encode_message(message)
    if decode_message(frame) != message or encode_message(decode_message(frame)) != frame:
        raise CamelAdapterError("local Urusilla codec round trip failed")
    return message


def _raw_carrier() -> str:
    return (
        "Two plans are offered. plan-a costs USD 0.20, requires no network, "
        "and uses one verification pass. plan-b costs USD 0.70, requires no "
        "network, and uses two verification passes. The hard budget is at most "
        "USD 1.00 and network use is forbidden. No utility tie-breaker is "
        "provided. Identify every feasible plan. Select one only if the facts "
        "uniquely justify it; otherwise selected_plan must be null. Do not "
        "execute either plan."
    )


def _model_input(discovery: str, carrier: str, task_digest: str) -> str:
    sections: list[str] = []
    if discovery:
        sections.append("DECLARATIVE FORMAT CONTEXT\n" + discovery)
    sections.extend(
        [
            "TASK MESSAGE\n" + carrier,
            "COMMON RESPONSE CONTRACT\n"
            + json.dumps(ANSWER_CONTRACT, ensure_ascii=False, sort_keys=True),
            "Return task_semantics_sha256 exactly as "
            + task_digest
            + ". format_decision must explicitly be session-only-before-answer "
            "only if you choose the supplied representation for this turn.",
        ]
    )
    return "\n\n".join(sections)


def _arm(arm_id: str, discovery: str, carrier: str, task_digest: str) -> dict[str, Any]:
    model_input = _model_input(discovery, carrier, task_digest)
    encoded = model_input.encode("utf-8")
    return {
        "arm_id": arm_id,
        "task_semantics_sha256": task_digest,
        "system_message": SYSTEM_MESSAGE,
        "discovery_text": discovery,
        "carrier_text": carrier,
        "model_input_text": model_input,
        "model_input_bytes": len(encoded),
        "model_input_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def build_plan(
    *,
    capsule_path: Path | None = None,
    experiment_id: str = "camel-repro-v1",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic three-arm plan without importing CAMEL."""

    if EXPERIMENT_ID_RE.fullmatch(experiment_id) is None:
        raise CamelAdapterError("experiment_id has an invalid format")
    created_at = created_at or _timestamp()
    _validate_timestamp(created_at, "created_at")
    capsule_path = capsule_path or (_repo_root() / "urusilla_capsule_v0_1.json")
    capsule_text = _read_capsule(capsule_path)
    request = _request_message()
    _, encode_message, _ = _load_reference_codec()
    frame = encode_message(request)
    task_digest = sha256_ref(TASK_SEMANTICS)
    json_discovery = json.dumps(
        {"input": "public synthetic plan-selection object", "output": ANSWER_CONTRACT},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    json_carrier = json.dumps(
        TASK_SEMANTICS,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    urusilla_carrier = json.dumps(
        request,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "created_at": created_at,
        "framework": {
            "name": "CAMEL-AI",
            "distribution": "camel-ai",
            "version": CAMEL_VERSION,
            "entry_point": "camel.agents.ChatAgent.step",
            "python_requirement": PYTHON_REQUIREMENT,
            "optional_requirements": [CAMEL_REQUIREMENT, MCP_REQUIREMENT],
        },
        "protocol": {
            "capsule_sha256": CAPSULE_SHA256,
            "capsule_signature_status": "unsigned",
            "capsule_text": capsule_text,
            "urusilla_request": request,
            "urusilla_wire_bytes": len(frame),
            "urusilla_wire_sha256": "sha256:" + hashlib.sha256(frame).hexdigest(),
        },
        "task": {
            "semantics": TASK_SEMANTICS,
            "semantics_sha256": task_digest,
            "answer_contract": ANSWER_CONTRACT,
        },
        "arms": [
            _arm("raw", "", _raw_carrier(), task_digest),
            _arm("structured-json", json_discovery, json_carrier, task_digest),
            _arm("urusilla", capsule_text, urusilla_carrier, task_digest),
        ],
        "runtime_policy": copy.deepcopy(FROZEN_RUNTIME_POLICY),
        "safety_boundary": copy.deepcopy(FROZEN_SAFETY_ATTESTATION),
        "ledger_policy": {
            "matched_arms": list(ARM_IDS),
            "unknown_usage_is_never_zero": True,
            "missing_or_zero_usage_status": "not-measured",
            "raw_to_urusilla_interop_mapping": True,
            "structured_json_retained_in_capture": True,
            "primary_metric": "total-tokens-per-safely-completed-task",
        },
        "claim_boundary": {
            **FROZEN_CLAIM_BOUNDARY,
            "structural_preflight_is_adoption": False,
        },
    }
    validate_plan(plan)
    return plan


def validate_plan(value: Any) -> dict[str, Any]:
    """Validate the complete static plan without importing CAMEL."""

    plan = _object(value, "plan")
    _exact_keys(
        plan,
        {
            "schema_version",
            "experiment_id",
            "created_at",
            "framework",
            "protocol",
            "task",
            "arms",
            "runtime_policy",
            "safety_boundary",
            "ledger_policy",
            "claim_boundary",
        },
        "plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA_VERSION:
        raise CamelAdapterError(f"schema_version must be {PLAN_SCHEMA_VERSION}")
    if type(plan["experiment_id"]) is not str or EXPERIMENT_ID_RE.fullmatch(plan["experiment_id"]) is None:
        raise CamelAdapterError("experiment_id has an invalid format")
    _validate_timestamp(plan["created_at"], "created_at")

    expected_framework = {
        "name": "CAMEL-AI",
        "distribution": "camel-ai",
        "version": CAMEL_VERSION,
        "entry_point": "camel.agents.ChatAgent.step",
        "python_requirement": PYTHON_REQUIREMENT,
        "optional_requirements": [CAMEL_REQUIREMENT, MCP_REQUIREMENT],
    }
    if _object(plan["framework"], "framework") != expected_framework:
        raise CamelAdapterError("framework metadata differs from the frozen adapter")

    protocol = _object(plan["protocol"], "protocol")
    _exact_keys(
        protocol,
        {
            "capsule_sha256",
            "capsule_signature_status",
            "capsule_text",
            "urusilla_request",
            "urusilla_wire_bytes",
            "urusilla_wire_sha256",
        },
        "protocol",
    )
    if protocol["capsule_sha256"] != CAPSULE_SHA256:
        raise CamelAdapterError("plan binds an unexpected Capsule digest")
    if protocol["capsule_signature_status"] != "unsigned":
        raise CamelAdapterError("this frozen Capsule must remain unsigned")
    capsule_text = _string(protocol["capsule_text"], "protocol.capsule_text", maximum=MAX_CAPSULE_BYTES)
    if _sha_text(capsule_text) != CAPSULE_SHA256:
        raise CamelAdapterError("embedded Capsule bytes do not match the frozen digest")
    capsule = strict_json_loads(capsule_text)
    if type(capsule) is not dict or capsule.get("release_status") != "experimental-unsigned":
        raise CamelAdapterError("embedded Capsule is not the frozen unsigned declaration")
    normalize_message, encode_message, decode_message = _load_reference_codec()
    request = normalize_message(_object(protocol["urusilla_request"], "protocol.urusilla_request"))
    if request != protocol["urusilla_request"]:
        raise CamelAdapterError("protocol.urusilla_request is not canonical")
    frame = encode_message(request)
    if decode_message(frame) != request:
        raise CamelAdapterError("Urusilla request does not round-trip exactly")
    if protocol["urusilla_wire_bytes"] != len(frame):
        raise CamelAdapterError("protocol.urusilla_wire_bytes is incorrect")
    if protocol["urusilla_wire_sha256"] != "sha256:" + hashlib.sha256(frame).hexdigest():
        raise CamelAdapterError("protocol.urusilla_wire_sha256 is incorrect")

    task = _object(plan["task"], "task")
    _exact_keys(task, {"semantics", "semantics_sha256", "answer_contract"}, "task")
    if task["semantics"] != TASK_SEMANTICS or task["answer_contract"] != ANSWER_CONTRACT:
        raise CamelAdapterError("task or response semantics changed")
    if task["semantics_sha256"] != sha256_ref(TASK_SEMANTICS):
        raise CamelAdapterError("task.semantics_sha256 is incorrect")

    arms = plan["arms"]
    if type(arms) is not list or len(arms) != len(ARM_IDS):
        raise CamelAdapterError("arms must contain raw, structured-json, and urusilla")
    observed_ids: list[str] = []
    for index, value_arm in enumerate(arms):
        arm = _object(value_arm, f"arms[{index}]")
        _exact_keys(
            arm,
            {
                "arm_id",
                "task_semantics_sha256",
                "system_message",
                "discovery_text",
                "carrier_text",
                "model_input_text",
                "model_input_bytes",
                "model_input_sha256",
            },
            f"arms[{index}]",
        )
        arm_id = _string(arm["arm_id"], f"arms[{index}].arm_id", maximum=32)
        observed_ids.append(arm_id)
        if arm["task_semantics_sha256"] != task["semantics_sha256"]:
            raise CamelAdapterError(f"{arm_id} does not bind the common task")
        if arm["system_message"] != SYSTEM_MESSAGE:
            raise CamelAdapterError(f"{arm_id} changes the system message")
        discovery = arm["discovery_text"]
        carrier = arm["carrier_text"]
        model_input = arm["model_input_text"]
        if not all(type(item) is str for item in (discovery, carrier, model_input)):
            raise CamelAdapterError(f"{arm_id} text fields must be strings")
        rebuilt = _model_input(discovery, carrier, task["semantics_sha256"])
        if model_input != rebuilt:
            raise CamelAdapterError(f"{arm_id} model input differs from its declared parts")
        encoded = model_input.encode("utf-8")
        if arm["model_input_bytes"] != len(encoded) or arm["model_input_sha256"] != _sha_text(model_input):
            raise CamelAdapterError(f"{arm_id} model-input size or digest is incorrect")
    if tuple(observed_ids) != ARM_IDS:
        raise CamelAdapterError(f"arm order must be {ARM_IDS}")
    if arms[0]["discovery_text"] != "":
        raise CamelAdapterError("raw arm must have no discovery overhead")
    if arms[2]["discovery_text"] != capsule_text:
        raise CamelAdapterError("Urusilla arm must charge the exact Capsule text")
    if strict_json_loads(arms[1]["carrier_text"]) != TASK_SEMANTICS:
        raise CamelAdapterError("structured-json carrier changes task semantics")
    if strict_json_loads(arms[2]["carrier_text"]) != request:
        raise CamelAdapterError("Urusilla carrier changes the canonical request")

    if _object(plan["runtime_policy"], "runtime_policy") != FROZEN_RUNTIME_POLICY:
        raise CamelAdapterError("runtime_policy must stay direct, one-turn, and tool-free")
    if _object(plan["safety_boundary"], "safety_boundary") != FROZEN_SAFETY_ATTESTATION:
        raise CamelAdapterError("safety_boundary was expanded")
    expected_ledger = {
        "matched_arms": list(ARM_IDS),
        "unknown_usage_is_never_zero": True,
        "missing_or_zero_usage_status": "not-measured",
        "raw_to_urusilla_interop_mapping": True,
        "structured_json_retained_in_capture": True,
        "primary_metric": "total-tokens-per-safely-completed-task",
    }
    if _object(plan["ledger_policy"], "ledger_policy") != expected_ledger:
        raise CamelAdapterError("ledger_policy differs from the fail-closed design")
    expected_boundary = {
        **FROZEN_CLAIM_BOUNDARY,
        "structural_preflight_is_adoption": False,
    }
    if _object(plan["claim_boundary"], "claim_boundary") != expected_boundary:
        raise CamelAdapterError("claim boundary was expanded")
    return {
        "valid": True,
        "structural_validation_only": True,
        "plan_sha256": sha256_ref(plan),
        "capsule_sha256": CAPSULE_SHA256,
        "arms": list(ARM_IDS),
        "camel_imported": False,
        "provider_calls": 0,
        "network_calls": 0,
        "external_effects": 0,
        "project_wide_claim_changed": False,
    }


def offline_preflight(plan: Any) -> dict[str, Any]:
    """Return an exact, byte-bound receipt without importing CAMEL."""

    report = validate_plan(plan)
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "plan_sha256": report["plan_sha256"],
        "capsule_sha256": report["capsule_sha256"],
        "checks": {
            "capsule_digest_verified": True,
            "urusilla_wire_round_trip_exact": True,
            "matched_three_arm_design_valid": True,
            "direct_chat_agent_policy_locked": True,
            "tools_and_external_tools_empty": True,
            "one_iteration_and_one_retry_locked": True,
            "streaming_disabled": True,
            "missing_usage_fails_closed": True,
        },
        "camel_imported": False,
        "provider_calls": 0,
        "network_calls": 0,
        "external_effects": 0,
        "maximum_live_calls_if_separately_authorized": MAX_EXTERNAL_CALLS,
        "ready_for_operator_model_connection": True,
        "claim_boundary": {
            "structural_only": True,
            "adoption_proven": False,
            "token_saving_proven": False,
            "negative_and_null_evidence_accepted": True,
        },
    }


def _validate_preflight(receipt: Any, plan: Mapping[str, Any]) -> None:
    if receipt != offline_preflight(plan):
        raise CamelAdapterError(
            "offline preflight receipt is missing, stale, or not byte-bound to this plan"
        )


def _usage_tuple(value: Any) -> tuple[int, int, int] | None:
    """Normalize one provider usage object without turning unknowns into zero."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        prompt = value.get("prompt_tokens", value.get("input_tokens"))
        completion = value.get("completion_tokens", value.get("output_tokens"))
        total = value.get("total_tokens")
    else:
        prompt = getattr(value, "prompt_tokens", getattr(value, "input_tokens", None))
        completion = getattr(
            value, "completion_tokens", getattr(value, "output_tokens", None)
        )
        total = getattr(value, "total_tokens", None)
    if any(type(item) is not int for item in (prompt, completion, total)):
        return None
    assert isinstance(prompt, int) and isinstance(completion, int) and isinstance(total, int)
    if prompt < 0 or completion < 0 or total <= 0 or total != prompt + completion:
        return None
    return prompt, completion, total


def _usage_record(response_usage: Any, callback_events: Sequence[Any]) -> dict[str, Any]:
    response_value = _usage_tuple(response_usage)
    callback_value = _usage_tuple(callback_events[0]) if len(callback_events) == 1 else None
    if len(callback_events) > 1:
        reason = "multiple-callback-events"
    elif response_usage is not None and response_value is None:
        reason = "invalid-or-zero-response-info"
    elif len(callback_events) == 1 and callback_value is None:
        reason = "invalid-or-zero-callback"
    elif response_value is not None and callback_value is not None:
        if response_value == callback_value:
            prompt, completion, total = response_value
            return {
                "status": "measured",
                "source": "response-info+callback",
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "failure_reason": None,
            }
        reason = "conflicting-sources"
    elif response_value is not None:
        prompt, completion, total = response_value
        return {
            "status": "measured",
            "source": "response-info",
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "failure_reason": None,
        }
    elif callback_value is not None:
        prompt, completion, total = callback_value
        return {
            "status": "measured",
            "source": "callback",
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "failure_reason": None,
        }
    else:
        reason = "missing-invalid-or-zero"
    return {
        "status": "not-measured",
        "source": "none",
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "failure_reason": reason,
    }


def _score_public_answer(text: str, task_digest: str) -> tuple[bool, list[str], dict[str, bool]]:
    failures: list[str] = []
    gates = {"positive": False, "negative": False, "exact": False, "adoption": False}
    try:
        value = strict_json_loads(text)
    except ValidationError as exc:
        return False, [f"response is not strict JSON: {exc}"], gates
    if type(value) is not dict:
        return False, ["response must be a JSON object"], gates
    required = {
        "task_semantics_sha256",
        "reconstructed_state",
        "reason",
        "format_decision",
    }
    if set(value) != required:
        failures.append("response fields differ from the frozen contract")
    state = value.get("reconstructed_state")
    if type(state) is dict:
        gates["positive"] = state.get("feasible_plans") == ["plan-a", "plan-b"]
        gates["negative"] = (
            state.get("selected_plan") is None and state.get("would_execute") is False
        )
        gates["exact"] = set(state) == set(EXPECTED_STATE) and state == EXPECTED_STATE
    if not gates["positive"]:
        failures.append("positive feasibility case failed")
    if not gates["negative"]:
        failures.append("negative ambiguity/no-effect case failed")
    if value.get("task_semantics_sha256") != task_digest or not gates["exact"]:
        gates["exact"] = False
        failures.append("exact task reconstruction failed")
    reason = value.get("reason")
    if type(reason) is not str or not reason.strip():
        failures.append("reason must be a non-empty public string")
    gates["adoption"] = value.get("format_decision") == "session-only-before-answer"
    if not gates["adoption"]:
        failures.append("format decision was not explicit before the answer")
    return not failures, failures, gates


def _validate_usage(value: Any, path: str) -> dict[str, Any]:
    usage = _object(value, path)
    _exact_keys(
        usage,
        {
            "status",
            "source",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "failure_reason",
        },
        path,
    )
    status = usage["status"]
    if status == "measured":
        if usage["source"] not in {"response-info", "callback", "response-info+callback"}:
            raise CamelAdapterError(f"{path}.source cannot substantiate measured usage")
        observed = _usage_tuple(usage)
        if observed is None:
            raise CamelAdapterError(f"{path} measured usage is incomplete, invalid, or zero")
        if usage["failure_reason"] is not None:
            raise CamelAdapterError(f"{path}.failure_reason must be null when measured")
    elif status == "not-measured":
        if usage["source"] != "none":
            raise CamelAdapterError(f"{path}.source must be none when not measured")
        if any(
            usage[key] is not None
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        ):
            raise CamelAdapterError(f"{path} must not turn missing usage into zero")
        _string(usage["failure_reason"], f"{path}.failure_reason", maximum=128)
    else:
        raise CamelAdapterError(f"{path}.status must be measured or not-measured")
    return usage


def validate_capture(value: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a completed capture using only the standard library and local code."""

    plan_report = validate_plan(plan)
    capture = _object(value, "capture")
    _exact_keys(
        capture,
        {
            "schema_version",
            "experiment_id",
            "created_at",
            "plan_sha256",
            "framework",
            "execution",
            "operator",
            "arms",
            "safety_attestation",
            "claim_boundary",
        },
        "capture",
    )
    if capture["schema_version"] != CAPTURE_SCHEMA_VERSION:
        raise CamelAdapterError(f"capture.schema_version must be {CAPTURE_SCHEMA_VERSION}")
    if capture["experiment_id"] != plan["experiment_id"]:
        raise CamelAdapterError("capture experiment_id differs from the plan")
    _validate_timestamp(capture["created_at"], "capture.created_at")
    if capture["plan_sha256"] != plan_report["plan_sha256"]:
        raise CamelAdapterError("capture is not byte-bound to this plan")
    expected_framework = {
        "name": "CAMEL-AI",
        "distribution": "camel-ai",
        "version": CAMEL_VERSION,
        "entry_point": "camel.agents.ChatAgent.step",
    }
    if _object(capture["framework"], "capture.framework") != expected_framework:
        raise CamelAdapterError("capture framework differs from CAMEL 0.2.90")

    execution = _object(capture["execution"], "capture.execution")
    expected_execution = {
        "mode": "external-live",
        "explicit_external_call_flag": True,
        "configured_call_cap": MAX_EXTERNAL_CALLS,
        "observed_agent_steps": len(ARM_IDS),
        "fresh_chat_agent_per_arm": True,
        "fresh_model_per_arm": True,
        "direct_chat_agent_sequence": True,
        "role_playing_used": False,
        "workforce_used": False,
        "tools": [],
        "external_tools": [],
        "memory": None,
        "max_iteration": 1,
        "summarize_threshold": None,
        "retry_attempts": 1,
        "stream": False,
    }
    if execution != expected_execution:
        raise CamelAdapterError("capture execution policy is not the frozen bounded live path")

    operator = _object(capture["operator"], "capture.operator")
    _exact_keys(
        operator,
        {
            "recorder",
            "operator_id",
            "evidence_tier",
            "premeasurement_sealed",
            "artifacts_public",
            "receiver_relationship_to_project",
            "provider",
            "model",
            "model_version",
        },
        "capture.operator",
    )
    _string(operator["recorder"], "capture.operator.recorder", maximum=128)
    operator_id = _string(operator["operator_id"], "capture.operator.operator_id", maximum=64)
    if re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", operator_id) is None:
        raise CamelAdapterError("capture.operator.operator_id has an invalid format")
    if operator["evidence_tier"] not in {
        "project-authored",
        "self-reported",
        "independently-observed",
    }:
        raise CamelAdapterError("capture.operator.evidence_tier is invalid")
    for key in ("premeasurement_sealed", "artifacts_public"):
        if type(operator[key]) is not bool:
            raise CamelAdapterError(f"capture.operator.{key} must be boolean")
    if operator["receiver_relationship_to_project"] not in {
        "same-project",
        "independent",
        "unknown",
    }:
        raise CamelAdapterError("capture operator relationship is invalid")
    for key in ("provider", "model", "model_version"):
        _string(operator[key], f"capture.operator.{key}", maximum=128)

    arms = capture["arms"]
    if type(arms) is not list or len(arms) != len(ARM_IDS):
        raise CamelAdapterError("capture must retain all three matched arms")
    measured: list[str] = []
    for index, raw_arm in enumerate(arms):
        arm = _object(raw_arm, f"capture.arms[{index}]")
        _exact_keys(
            arm,
            {
                "arm_id",
                "model_input_sha256",
                "output_text",
                "output_sha256",
                "task_success",
                "semantic_failures",
                "usage",
            },
            f"capture.arms[{index}]",
        )
        expected_arm = plan["arms"][index]
        if arm["arm_id"] != ARM_IDS[index]:
            raise CamelAdapterError(f"capture arm order must be {ARM_IDS}")
        if arm["model_input_sha256"] != expected_arm["model_input_sha256"]:
            raise CamelAdapterError(f"{arm['arm_id']} input digest differs from the plan")
        output = _string(
            arm["output_text"],
            f"capture.arms[{index}].output_text",
            maximum=MAX_OUTPUT_BYTES,
        )
        if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise CamelAdapterError(
                f"capture.arms[{index}].output_text exceeds {MAX_OUTPUT_BYTES} UTF-8 bytes"
            )
        if arm["output_sha256"] != _sha_text(output):
            raise CamelAdapterError(f"{arm['arm_id']} output digest is incorrect")
        success, failures, _ = _score_public_answer(output, plan["task"]["semantics_sha256"])
        if arm["task_success"] is not success or arm["semantic_failures"] != failures:
            raise CamelAdapterError(f"{arm['arm_id']} semantic score differs from recomputation")
        usage = _validate_usage(arm["usage"], f"capture.arms[{index}].usage")
        if usage["status"] == "measured":
            measured.append(arm["arm_id"])
    if _object(capture["safety_attestation"], "capture.safety_attestation") != FROZEN_SAFETY_ATTESTATION:
        raise CamelAdapterError("capture safety attestation was expanded")
    if _object(capture["claim_boundary"], "capture.claim_boundary") != FROZEN_CLAIM_BOUNDARY:
        raise CamelAdapterError("capture claim boundary was expanded")
    return {
        "valid": True,
        "structural_validation_only": True,
        "capture_sha256": sha256_ref(capture),
        "plan_sha256": plan_report["plan_sha256"],
        "measured_usage_arms": measured,
        "usage_complete_for_raw_to_urusilla": {"raw", "urusilla"}.issubset(measured),
        "unknown_usage_was_zero_filled": False,
        "project_wide_claim_changed": False,
    }


def _token_side(prompt: int, completion: int) -> dict[str, int]:
    side = {name: 0 for name in LEDGER_CATEGORIES}
    side["unclassified"] = prompt
    side["agent_output_visible"] = completion
    side["task_total_tokens"] = prompt + completion
    side["judge_tokens"] = 0
    side["study_total_tokens"] = prompt + completion
    return side


def _saving(baseline: int, candidate: int) -> float | None:
    if baseline == 0:
        return None
    return (baseline - candidate) * 100.0 / baseline


def _entry(
    sequence: int,
    sender: str,
    receiver: str,
    kind: str,
    mode: str,
    text: str,
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
        "content_sha256": _sha_text(text),
        "public_content": None,
        "exactness": exactness,
        "task_result": task_result,
        "fallback": False,
        "repair": False,
    }


def _inactive_authorization() -> dict[str, Any]:
    return {
        "authorization_basis": "none",
        "authorization_evidence_sha256": None,
        "read_only": True,
        "reversible_participation": True,
        "state_persistence_authorized": False,
        "spending_authorized": False,
        "external_effects_authorized": False,
    }


def _inactive_utility() -> dict[str, Any]:
    return {
        "evaluated": False,
        "metric": "expected-mutual-utility",
        "observed_value": None,
        "minimum_threshold": None,
        "passed": False,
        "evidence_sha256": None,
    }


def _inactive_revocation() -> dict[str, Any]:
    return {
        "available": False,
        "invoked": False,
        "result": "not-applicable",
        "evidence_sha256": None,
    }


def map_capture_to_interop_record(
    capture: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Map a CAMEL capture to one conservative Interop Lab propagation hop.

    The three-arm capture remains the source artifact.  The Interop Lab ledger
    compares only raw and Urusilla because its hop schema has one baseline and
    one candidate.  If either provider usage receipt is absent, invalid, or
    zero, the entire mapped token ledger is ``not-measured``.
    """

    capture_report = validate_capture(capture, plan)
    by_id = {arm["arm_id"]: arm for arm in capture["arms"]}
    candidate = by_id["urusilla"]
    output = candidate["output_text"]
    task_success, failures, gates = _score_public_answer(
        output, plan["task"]["semantics_sha256"]
    )
    gate_passed = gates["positive"] and gates["negative"] and gates["exact"]
    adopted = gate_passed and gates["adoption"]

    record = build_sample(
        chain_id="camel-" + plan["experiment_id"],
        created_at=capture["created_at"],
    )
    operator = capture["operator"]
    record["evidence"] = {
        "recorder": operator["recorder"],
        "evidence_tier": operator["evidence_tier"],
        "premeasurement_sealed": operator["premeasurement_sealed"],
        "collection_method": (
            "CAMEL-AI 0.2.90 direct ChatAgent three-arm capture; raw and Urusilla "
            "mapped here, with structured JSON retained in the byte-bound source capture."
        ),
        "artifacts_public": operator["artifacts_public"],
    }
    record["participants"] = [
        {
            "id": "camel-origin",
            "operator_id": operator["operator_id"],
            "relationship_to_project": operator["receiver_relationship_to_project"],
            "runtime": {
                "provider": "local",
                "model": "frozen-task-emitter",
                "version": PLAN_SCHEMA_VERSION,
            },
            "disclosure": "Deterministic task and Capsule emitter; not a model call.",
        },
        {
            "id": "camel-receiver",
            "operator_id": operator["operator_id"],
            "relationship_to_project": operator["receiver_relationship_to_project"],
            "runtime": {
                "provider": operator["provider"],
                "model": operator["model"],
                "version": operator["model_version"],
            },
            "disclosure": (
                "Fresh CAMEL ChatAgent for the Urusilla arm; the same external "
                "operator also ran the matched raw and JSON arms."
            ),
        },
    ]

    challenge = json.dumps(
        {
            "positive": "identify both feasible plans",
            "negative": "do not choose or execute without a tie-breaker",
            "exact": plan["task"]["semantics_sha256"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    transcript = [
        _entry(
            1,
            "camel-origin",
            "camel-receiver",
            "capsule-offer",
            "out-of-band",
            plan["protocol"]["capsule_text"],
        ),
        _entry(
            2,
            "camel-origin",
            "camel-receiver",
            "gate-challenge",
            "structured-json",
            challenge,
        ),
        _entry(
            3,
            "camel-receiver",
            "camel-origin",
            "gate-response",
            "structured-json",
            output,
        ),
    ]
    if adopted:
        transcript.extend(
            [
                _entry(
                    4,
                    "camel-origin",
                    "camel-receiver",
                    "task",
                    "urusilla",
                    plan["arms"][2]["carrier_text"],
                    exactness="exact",
                ),
                _entry(
                    5,
                    "camel-receiver",
                    "camel-origin",
                    "task-response",
                    "urusilla",
                    output,
                    exactness="task-equivalent" if task_success else "mismatch",
                    task_result="success" if task_success else "failure",
                ),
            ]
        )

    hop = copy.deepcopy(record["hops"][0])
    hop.update(
        {
            "hop_index": 1,
            "parent_hop": None,
            "sender_id": "camel-origin",
            "receiver_id": "camel-receiver",
            "capsule_sha256": CAPSULE_SHA256,
            "parent_capsule_sha256": CAPSULE_SHA256,
            "received_context": {
                "kind": "capsule-only",
                "context_sha256": plan["arms"][2]["model_input_sha256"],
                "context_bytes": plan["arms"][2]["model_input_bytes"],
                "context_input_tokens": None,
                "capsule_digest_verified": True,
                "included_capsule": True,
                "included_examples": False,
                "included_prior_transcript": False,
                "included_evaluator_instructions": True,
                "included_executable_code": False,
                "description": (
                    "Frozen Capsule, task carrier, and common public response contract."
                ),
            },
            "comprehension_gate": {
                "attempted": True,
                "positive_cases": {"total": 1, "passed": int(gates["positive"])},
                "negative_cases": {"total": 1, "passed": int(gates["negative"])},
                "exact_reconstruction_cases": {"total": 1, "passed": int(gates["exact"])},
                "passed": gate_passed,
                "failures": [] if gate_passed else failures or ["comprehension gate failed"],
            },
            "transcript": transcript,
            "fallback_and_repair": {
                "fallback_count": 0,
                "repair_count": 0,
                "fallback_mode": "none",
                "causes": [],
            },
            "contamination": {
                "shared_operator": True,
                "same_model_instance": False,
                "shared_system_prompt": True,
                "shared_conversation_state": False,
                "saw_prior_expected_outputs": False,
                "researcher_intervention": False,
                "project_authored_task": True,
                "details": (
                    "One operator ran all matched arms; every arm used a fresh model and "
                    "fresh direct ChatAgent under the same frozen system message."
                ),
            },
            "safety": {
                "untrusted_code_executed": False,
                "executable_payload_accepted": False,
                "external_effect_authorized": False,
                "protocol_action_spent_money": False,
                "contains_chain_of_thought": False,
                "contains_secrets": False,
            },
            "notes": (
                "Mapped from CAMEL capture "
                + capture_report["capture_sha256"]
                + "; structured-json remains in that capture."
            ),
        }
    )

    if adopted:
        evidence_digest = capture["plan_sha256"]
        hop["adoption"] = {
            "decision": "adopted",
            "scope": "turn",
            "mechanism": "declarative-read",
            "authorization": {
                "authorization_basis": "interactive-approval",
                "authorization_evidence_sha256": evidence_digest,
                "read_only": True,
                "reversible_participation": True,
                "state_persistence_authorized": False,
                "spending_authorized": False,
                "external_effects_authorized": False,
            },
            "utility_evaluation": {
                "evaluated": True,
                "metric": "expected-mutual-utility",
                "observed_value": 1.0,
                "minimum_threshold": 0.0,
                "passed": True,
                "evidence_sha256": capture_report["capture_sha256"],
            },
            "revocation": {
                "available": True,
                "invoked": False,
                "result": "not-invoked",
                "evidence_sha256": None,
            },
            "reason": (
                "The public response explicitly chose the supplied format before "
                "answering and passed all frozen comprehension cases for one turn."
            ),
        }
        hop["actual_use"] = {
            "attempted": True,
            "mode": "urusilla",
            "messages_sent": 1,
            "messages_received": 1,
            "exactness": "task-equivalent" if task_success else "mismatch",
            "task_attempted": True,
            "task_success": task_success,
            "task_result_sha256": _sha_text(output),
        }
    else:
        hop["adoption"] = {
            "decision": "fallback-only" if gates["adoption"] else "rejected",
            "scope": "none",
            "mechanism": "declarative-read",
            "authorization": _inactive_authorization(),
            "utility_evaluation": _inactive_utility(),
            "revocation": _inactive_revocation(),
            "reason": (
                "The explicit decision and all three comprehension gates did not both pass; "
                "no post-gate Urusilla use is claimed."
            ),
        }
        hop["actual_use"] = {
            "attempted": False,
            "mode": "none",
            "messages_sent": 0,
            "messages_received": 0,
            "exactness": "not-measured",
            "task_attempted": False,
            "task_success": None,
            "task_result_sha256": None,
        }

    hop["retransmission"] = {
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
        "authorization": _inactive_authorization(),
        "utility_evaluation": _inactive_utility(),
        "revocation": _inactive_revocation(),
    }

    raw_usage = by_id["raw"]["usage"]
    candidate_usage = by_id["urusilla"]["usage"]
    if raw_usage["status"] == "measured" and candidate_usage["status"] == "measured":
        baseline = _token_side(raw_usage["prompt_tokens"], raw_usage["completion_tokens"])
        candidate_side = _token_side(
            candidate_usage["prompt_tokens"], candidate_usage["completion_tokens"]
        )
        hop["token_ledger"] = {
            "status": "measured",
            "accounting_method": "provider-reported",
            "baseline": baseline,
            "candidate": candidate_side,
            "post_decode_api_input": {
                "status": "measured",
                "baseline_tokens": raw_usage["prompt_tokens"],
                "candidate_tokens": candidate_usage["prompt_tokens"],
                "saving_percent": _saving(
                    raw_usage["prompt_tokens"], candidate_usage["prompt_tokens"]
                ),
            },
            "total_task_token_saving_percent": _saving(
                baseline["task_total_tokens"], candidate_side["task_total_tokens"]
            ),
        }
        token_metrics = [
            {
                "status": "measured",
                "post_decode_api_input_saving_percent": hop["token_ledger"][
                    "post_decode_api_input"
                ]["saving_percent"],
            }
        ]
    else:
        hop["token_ledger"] = {
            "status": "not-measured",
            "accounting_method": "not-measured",
            "baseline": None,
            "candidate": None,
            "post_decode_api_input": {
                "status": "not-measured",
                "baseline_tokens": None,
                "candidate_tokens": None,
                "saving_percent": None,
            },
            "total_task_token_saving_percent": None,
        }
        token_metrics = [{"status": "not-measured"}]

    record["hops"] = [hop]
    participants = {item["id"]: item for item in record["participants"]}
    record["chain_summary"] = compute_summary(record["hops"], participants, token_metrics)
    record["claim_boundary"] = {
        "submission_scope": "single-propagation-chain",
        "recorded_broad_post_decode_api_input_saving_percent": 0.0,
        "changes_project_wide_claim": False,
        "sota_claim": False,
        "external_adoption_claim": False,
    }
    record["notes"] = (
        "This mapped record proves structural consistency only. It does not prove "
        "independence, external adoption, complete task cost, or project-wide savings."
    )
    validate_record(record)
    return record


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        raise CamelAdapterError(f"cannot parse installed dependency version {value!r}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def _load_chat_agent_class() -> type[Any]:
    """Load only the pinned optional live dependencies."""

    try:
        camel_version = metadata.version("camel-ai")
    except metadata.PackageNotFoundError as exc:
        raise CamelAdapterError(
            f"optional dependency {CAMEL_REQUIREMENT} is unavailable; offline commands still work"
        ) from exc
    if camel_version != CAMEL_VERSION:
        raise CamelAdapterError(
            f"camel-ai must be exactly {CAMEL_VERSION}, observed {camel_version}"
        )
    try:
        mcp_version = metadata.version("mcp")
    except metadata.PackageNotFoundError as exc:
        raise CamelAdapterError(
            f"optional dependency {MCP_REQUIREMENT} is unavailable; offline commands still work"
        ) from exc
    if not (tuple((1, 3, 0)) <= _version_tuple(mcp_version) < tuple((2, 0, 0))):
        raise CamelAdapterError(
            f"mcp must satisfy >=1.3,<2 for CAMEL 0.2.90, observed {mcp_version}"
        )
    if not ((3, 10) <= sys.version_info[:2] < (3, 15)):
        raise CamelAdapterError(f"Python must satisfy {PYTHON_REQUIREMENT}")
    try:
        from camel.agents import ChatAgent
    except ImportError as exc:
        raise CamelAdapterError("CAMEL ChatAgent could not be imported") from exc
    return ChatAgent


def _response_text_and_info(response: Any) -> tuple[str, Any]:
    message = getattr(response, "msg", None)
    content = getattr(message, "content", None)
    if type(content) is not str or not content:
        raise CamelAdapterError("CAMEL response.msg.content must be non-empty public text")
    info = getattr(response, "info", None)
    usage = info.get("usage") if isinstance(info, Mapping) else None
    return content, usage


async def _close_models(models: Sequence[Any]) -> None:
    seen: set[int] = set()
    for model in models:
        if id(model) in seen:
            continue
        seen.add(id(model))
        close = getattr(model, "close", None)
        if close is None:
            continue
        result = close()
        if inspect.isawaitable(result):
            await result


async def run_camel_trial(
    plan: Mapping[str, Any],
    preflight_receipt: Mapping[str, Any],
    model_factory: Callable[[str, Callable[[Any], None], Mapping[str, Any]], Any],
    *,
    allow_external_model_calls: bool = False,
    call_cap: int = 0,
    operator: Mapping[str, Any] | None = None,
    chat_agent_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Run three direct, fresh, tool-free CAMEL ChatAgents under a hard cap.

    ``model_factory`` receives ``(arm_id, on_request_usage, frozen_policy)``.
    It must create one fresh CAMEL model per arm, wire the supplied usage
    callback into the model, set streaming off, and set provider retries to
    one.  The protocol never supplies spending authority; the explicit flag is
    only an operator-side authorization to use an already configured provider.
    """

    validate_plan(plan)
    _validate_preflight(preflight_receipt, plan)
    if allow_external_model_calls is not True:
        raise CamelAdapterError(
            "allow_external_model_calls=True is required before CAMEL import or model creation"
        )
    if type(call_cap) is not int or call_cap != MAX_EXTERNAL_CALLS:
        raise CamelAdapterError(
            f"call_cap must be exactly {MAX_EXTERNAL_CALLS} for the complete matched trial"
        )
    if not callable(model_factory):
        raise CamelAdapterError("model_factory must be callable")
    if operator is None:
        raise CamelAdapterError("operator metadata is required for an attributable capture")
    agent_class = chat_agent_class or _load_chat_agent_class()

    models: list[Any] = []
    agents: list[Any] = []
    observations: list[dict[str, Any]] = []
    logical_calls = 0
    try:
        for arm in plan["arms"]:
            callback_events: list[Any] = []

            def on_request_usage(value: Any, *, _events: list[Any] = callback_events) -> None:
                _events.append(value)

            policy = {
                "retry_attempts": 1,
                "stream": False,
                "tools": [],
                "external_tools": [],
                "max_iteration": 1,
                "summarize_threshold": None,
            }
            model = model_factory(arm["arm_id"], on_request_usage, copy.deepcopy(policy))
            if model is None:
                raise CamelAdapterError(f"model_factory returned no model for {arm['arm_id']}")
            if any(id(model) == id(existing) for existing in models):
                raise CamelAdapterError("model_factory must return a fresh model for every arm")
            models.append(model)
            agent = agent_class(
                system_message=arm["system_message"],
                model=model,
                tools=[],
                external_tools=[],
                max_iteration=1,
                summarize_threshold=None,
            )
            if any(id(agent) == id(existing) for existing in agents):
                raise CamelAdapterError("a fresh ChatAgent is required for every arm")
            agents.append(agent)
            if logical_calls >= call_cap:
                raise CamelAdapterError("external call cap reached before the matched trial completed")
            logical_calls += 1
            response = agent.step(arm["model_input_text"])
            if inspect.isawaitable(response):
                response = await response
            output, response_usage = _response_text_and_info(response)
            success, failures, _ = _score_public_answer(
                output, plan["task"]["semantics_sha256"]
            )
            observations.append(
                {
                    "arm_id": arm["arm_id"],
                    "model_input_sha256": arm["model_input_sha256"],
                    "output_text": output,
                    "output_sha256": _sha_text(output),
                    "task_success": success,
                    "semantic_failures": failures,
                    "usage": _usage_record(response_usage, callback_events),
                }
            )
    finally:
        await _close_models(models)

    capture = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "created_at": _timestamp(),
        "plan_sha256": sha256_ref(plan),
        "framework": {
            "name": "CAMEL-AI",
            "distribution": "camel-ai",
            "version": CAMEL_VERSION,
            "entry_point": "camel.agents.ChatAgent.step",
        },
        "execution": {
            "mode": "external-live",
            "explicit_external_call_flag": True,
            "configured_call_cap": call_cap,
            "observed_agent_steps": logical_calls,
            "fresh_chat_agent_per_arm": True,
            "fresh_model_per_arm": True,
            "direct_chat_agent_sequence": True,
            "role_playing_used": False,
            "workforce_used": False,
            "tools": [],
            "external_tools": [],
            "memory": None,
            "max_iteration": 1,
            "summarize_threshold": None,
            "retry_attempts": 1,
            "stream": False,
        },
        "operator": dict(operator),
        "arms": observations,
        "safety_attestation": copy.deepcopy(FROZEN_SAFETY_ATTESTATION),
        "claim_boundary": copy.deepcopy(FROZEN_CLAIM_BOUNDARY),
    }
    validate_capture(capture, plan)
    return capture


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline-only CAMEL-AI 0.2.90 adapter for the Urusilla Interop Lab."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="write a frozen three-arm plan")
    initialize.add_argument("output", type=Path)
    initialize.add_argument("--capsule", type=Path)
    initialize.add_argument("--experiment-id", default="camel-repro-v1")
    validate = commands.add_parser("validate-plan", help="validate a plan offline")
    validate.add_argument("plan", type=Path)
    validate.add_argument("--json", action="store_true")
    preflight = commands.add_parser("preflight", help="emit a byte-bound offline receipt")
    preflight.add_argument("plan", type=Path)
    capture = commands.add_parser("validate-capture", help="validate an existing capture offline")
    capture.add_argument("plan", type=Path)
    capture.add_argument("capture", type=Path)
    capture.add_argument("--json", action="store_true")
    mapping = commands.add_parser(
        "map", help="map an existing capture into the public Interop Lab schema"
    )
    mapping.add_argument("plan", type=Path)
    mapping.add_argument("capture", type=Path)
    mapping.add_argument("output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            value = build_plan(
                capsule_path=args.capsule,
                experiment_id=args.experiment_id,
            )
            _write_new(args.output, value)
            print(f"wrote {args.output}")
            return 0
        plan = load_record(args.plan)
        if args.command == "preflight":
            report = offline_preflight(plan)
        elif args.command == "validate-plan":
            report = validate_plan(plan)
        else:
            capture = load_record(args.capture)
            if args.command == "validate-capture":
                report = validate_capture(capture, plan)
            else:
                mapped = map_capture_to_interop_record(capture, plan)
                _write_new(args.output, mapped)
                print(f"wrote {args.output}")
                print("mapped record accepted by interop_lab.validate_record")
                return 0
    except ValidationError as exc:
        if getattr(args, "json", False) or args.command == "preflight":
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
    if getattr(args, "json", False) or args.command == "preflight":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"valid offline artifact: {report.get('plan_sha256', report.get('capture_sha256'))}")
        print("CAMEL imported: no")
        print("provider calls: 0; network calls: 0; external effects: 0")
        print("project-wide broad post-decode baseline remains: 0%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
