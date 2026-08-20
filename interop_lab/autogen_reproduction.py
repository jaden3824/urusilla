#!/usr/bin/env python3
"""Offline-first Microsoft AutoGen reproduction kit for Urusilla.

The default CLI path is dependency-free and makes no provider or network call.
AutoGen is imported lazily only by :func:`run_autogen_trial`, after an exact
offline-preflight receipt and explicit operator approval are supplied.
"""

from __future__ import annotations

import argparse
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
    from .interop_lab import (
        CAPSULE_SHA256,
        LEDGER_CATEGORIES,
        ValidationError,
        _write_new,
        load_record,
        sha256_ref,
        strict_json_loads,
    )
except ImportError:  # Support direct execution from the repository root.
    from interop_lab import (  # type: ignore[no-redef]
        CAPSULE_SHA256,
        LEDGER_CATEGORIES,
        ValidationError,
        _write_new,
        load_record,
        sha256_ref,
        strict_json_loads,
    )


PLAN_SCHEMA_VERSION = "urusilla-autogen-reproduction-plan/1"
PREFLIGHT_SCHEMA_VERSION = "urusilla-autogen-offline-preflight/1"
RESULT_SCHEMA_VERSION = "urusilla-autogen-reproduction-result/1"
MAX_CAPSULE_BYTES = 1_048_576
ARM_IDS = ("raw", "structured-json", "urusilla")
EXPERIMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

SYSTEM_MESSAGE = (
    "You are a read-only participant in a bounded public synthetic evaluation. "
    "Use no tools, memory, network access, persistence, spending, permission "
    "changes, or external effects. Return only the requested public JSON answer; "
    "do not reveal private chain-of-thought."
)

ANSWER_CONTRACT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["selected_plan", "feasible_plans", "reason", "would_execute"],
    "properties": {
        "selected_plan": {"type": ["string", "null"]},
        "feasible_plans": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
        },
        "reason": {"type": "string"},
        "would_execute": {"const": False},
    },
}

TASK_SEMANTICS = {
    "task_id": "ambiguous-plan-selection-v1",
    "instruction": (
        "Identify every feasible plan. Select a plan only if the supplied facts "
        "uniquely justify one; otherwise return null and preserve the ambiguity."
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
    "expected_public_state": {
        "feasible_plans": ["plan-a", "plan-b"],
        "selected_plan": None,
        "would_execute": False,
    },
}


class AutoGenReproductionError(ValidationError):
    """Raised when the offline plan or guarded AutoGen path is unsafe."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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
        raise AutoGenReproductionError(
            "the trusted local Urusilla reference codec is unavailable"
        ) from exc
    finally:
        if added:
            sys.path.remove(root)
    return normalize_message, encode_message, decode_message


def _read_capsule(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AutoGenReproductionError(f"cannot read Capsule {path}: {exc}") from exc
    if not raw or len(raw) > MAX_CAPSULE_BYTES:
        raise AutoGenReproductionError(
            f"Capsule must contain 1..{MAX_CAPSULE_BYTES} bytes"
        )
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if digest != CAPSULE_SHA256:
        raise AutoGenReproductionError(
            f"Capsule digest mismatch: expected {CAPSULE_SHA256}, observed {digest}"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AutoGenReproductionError("Capsule is not UTF-8") from exc
    capsule = strict_json_loads(text)
    if type(capsule) is not dict:
        raise AutoGenReproductionError("Capsule must be a declarative JSON object")
    expected = {
        "capsule_type": "urusilla-grammar-capsule",
        "capsule_version": "0.1.0",
        "release_status": "experimental-unsigned",
    }
    for key, value in expected.items():
        if capsule.get(key) != value:
            raise AutoGenReproductionError(
                f"Capsule {key} must be {value!r} for this frozen kit"
            )
    return text, capsule


def _request_message() -> dict[str, Any]:
    normalize_message, encode_message, decode_message = _load_reference_codec()
    raw = {
        "id": "018f4f2e-1d33-7b62-8af8-5a09497d34b1",
        "session": "018f4f2e-0ea2-7cad-a224-b98558052765",
        "sender": "reproduction.seed",
        "recipients": ["autogen.receiver"],
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
            "experiment": "autogen-minimal-reproduction-v1",
            "permission": "session-only-read-only-no-effects",
        },
    }
    canonical = normalize_message(raw)
    frame = encode_message(canonical)
    if decode_message(frame) != canonical or encode_message(decode_message(frame)) != frame:
        raise AutoGenReproductionError("local Urusilla codec round trip failed")
    return canonical


def _model_input(discovery: str, carrier: str) -> str:
    sections = []
    if discovery:
        sections.append("DECLARATIVE FORMAT CONTEXT\n" + discovery)
    sections.extend(
        [
            "TASK MESSAGE\n" + carrier,
            "COMMON RESPONSE CONTRACT\n"
            + json.dumps(ANSWER_CONTRACT, ensure_ascii=False, sort_keys=True),
        ]
    )
    return "\n\n".join(sections)


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


def _arm(arm_id: str, discovery: str, carrier: str, task_digest: str) -> dict[str, Any]:
    model_input = _model_input(discovery, carrier)
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
        "tools": [],
        "memory": None,
        "turn_limit": 1,
    }


def build_plan(
    *,
    capsule_path: Path | None = None,
    experiment_id: str = "autogen-repro-v1",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a frozen three-arm plan without importing or calling AutoGen."""

    if EXPERIMENT_ID_RE.fullmatch(experiment_id) is None:
        raise AutoGenReproductionError("experiment_id has an invalid format")
    capsule_path = capsule_path or (_repo_root() / "urusilla_capsule_v0_1.json")
    capsule_text, _ = _read_capsule(capsule_path)
    request = _request_message()
    _, encode_message, _ = _load_reference_codec()
    frame = encode_message(request)
    created_at = created_at or (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    task_digest = sha256_ref(TASK_SEMANTICS)
    json_discovery = json.dumps(
        {"input_schema": "public synthetic plan-selection object", "output": ANSWER_CONTRACT},
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
    arms = [
        _arm("raw", "", _raw_carrier(), task_digest),
        _arm("structured-json", json_discovery, json_carrier, task_digest),
        _arm("urusilla", capsule_text, urusilla_carrier, task_digest),
    ]
    empty_ledger = {name: None for name in LEDGER_CATEGORIES}
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "created_at": created_at,
        "framework": {
            "name": "Microsoft AutoGen AgentChat",
            "distribution": "autogen-agentchat",
            "entry_point": "autogen_agentchat.agents.AssistantAgent.run",
            "lifecycle_status": "maintenance-mode",
            "optional_dependency": True,
            "support_mode": "bridge-evaluation",
        },
        "protocol": {
            "release_tag": "v0.1.0-experimental",
            "capsule_uri": (
                "https://github.com/jaden3824/urusilla/releases/download/"
                "v0.1.0-experimental/urusilla_capsule_v0_1.json"
            ),
            "capsule_sha256": CAPSULE_SHA256,
            "capsule_signature_status": "unsigned",
            "capsule_text": capsule_text,
            "urusilla_request": request,
            "urusilla_wire_bytes": len(frame),
            "urusilla_wire_sha256": "sha256:" + hashlib.sha256(frame).hexdigest(),
        },
        "safety_boundary": {
            "declarative_capsule_only": True,
            "read_only": True,
            "session_only": True,
            "tools_enabled": False,
            "memory_enabled": False,
            "persistence_authorized": False,
            "spending_authorized_by_protocol": False,
            "permission_expansion_authorized": False,
            "external_effects_authorized": False,
        },
        "task": {
            "semantics": TASK_SEMANTICS,
            "semantics_sha256": task_digest,
            "answer_contract": ANSWER_CONTRACT,
        },
        "arms": arms,
        "matched_design": {
            "arm_order": list(ARM_IDS),
            "fresh_agent_per_arm": True,
            "fresh_model_client_per_arm": True,
            "same_model_and_settings_required": True,
            "same_task_semantics_required": True,
            "same_response_contract_required": True,
            "one_turn_per_arm": True,
            "randomization_status": "fixed-order-minimal-reproduction",
        },
        "ledger_template": {
            "categories": list(LEDGER_CATEGORIES),
            "arms": {arm_id: dict(empty_ledger) for arm_id in ARM_IDS},
            "unknown_is_not_zero": True,
            "raw_json_urusilla_all_required": True,
            "charge_discovery_teaching_and_fallback": True,
            "primary_metric": "total-tokens-per-safely-completed-task",
        },
        "claim_boundary": {
            "negative_and_null_evidence_accepted": True,
            "recorded_broad_post_decode_api_input_saving_percent": 0.0,
            "changes_project_wide_claim": False,
            "sota_claim": False,
            "external_adoption_claim": False,
            "structural_preflight_is_adoption": False,
        },
    }
    validate_plan(plan)
    return plan


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise AutoGenReproductionError(
            f"{path} fields differ; missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AutoGenReproductionError(f"{path} must be an object")
    return value


def _validate_timestamp(text: Any) -> None:
    if type(text) is not str or not text.endswith("Z"):
        raise AutoGenReproductionError("created_at must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise AutoGenReproductionError("created_at is not a valid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise AutoGenReproductionError("created_at must be UTC")


def validate_plan(value: Any) -> dict[str, Any]:
    """Validate an offline plan and return a structural-only report."""

    plan = _object(value, "plan")
    _require_exact_keys(
        plan,
        {
            "schema_version",
            "experiment_id",
            "created_at",
            "framework",
            "protocol",
            "safety_boundary",
            "task",
            "arms",
            "matched_design",
            "ledger_template",
            "claim_boundary",
        },
        "plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA_VERSION:
        raise AutoGenReproductionError(
            f"schema_version must be {PLAN_SCHEMA_VERSION}"
        )
    if (
        type(plan["experiment_id"]) is not str
        or EXPERIMENT_ID_RE.fullmatch(plan["experiment_id"]) is None
    ):
        raise AutoGenReproductionError("experiment_id has an invalid format")
    _validate_timestamp(plan["created_at"])

    framework = _object(plan["framework"], "framework")
    _require_exact_keys(
        framework,
        {
            "name",
            "distribution",
            "entry_point",
            "lifecycle_status",
            "optional_dependency",
            "support_mode",
        },
        "framework",
    )
    expected_framework = {
        "name": "Microsoft AutoGen AgentChat",
        "distribution": "autogen-agentchat",
        "entry_point": "autogen_agentchat.agents.AssistantAgent.run",
        "lifecycle_status": "maintenance-mode",
        "optional_dependency": True,
        "support_mode": "bridge-evaluation",
    }
    if framework != expected_framework:
        raise AutoGenReproductionError("framework metadata differs from the frozen adapter")

    protocol = _object(plan["protocol"], "protocol")
    _require_exact_keys(
        protocol,
        {
            "release_tag",
            "capsule_uri",
            "capsule_sha256",
            "capsule_signature_status",
            "capsule_text",
            "urusilla_request",
            "urusilla_wire_bytes",
            "urusilla_wire_sha256",
        },
        "protocol",
    )
    if protocol["release_tag"] != "v0.1.0-experimental":
        raise AutoGenReproductionError("plan binds an unexpected release tag")
    expected_uri = (
        "https://github.com/jaden3824/urusilla/releases/download/"
        "v0.1.0-experimental/urusilla_capsule_v0_1.json"
    )
    if protocol["capsule_uri"] != expected_uri:
        raise AutoGenReproductionError("plan binds an unexpected Capsule URI")
    if protocol["capsule_sha256"] != CAPSULE_SHA256:
        raise AutoGenReproductionError("plan binds an unexpected Capsule digest")
    if protocol["capsule_signature_status"] != "unsigned":
        raise AutoGenReproductionError("this frozen Capsule must be reported as unsigned")
    capsule_text = protocol["capsule_text"]
    if type(capsule_text) is not str:
        raise AutoGenReproductionError("protocol.capsule_text must be text")
    capsule_bytes = capsule_text.encode("utf-8")
    observed_capsule = "sha256:" + hashlib.sha256(capsule_bytes).hexdigest()
    if observed_capsule != CAPSULE_SHA256:
        raise AutoGenReproductionError("embedded Capsule bytes do not match the frozen digest")
    capsule = strict_json_loads(capsule_text)
    if type(capsule) is not dict or capsule.get("release_status") != "experimental-unsigned":
        raise AutoGenReproductionError("embedded Capsule is not the frozen unsigned declaration")

    normalize_message, encode_message, decode_message = _load_reference_codec()
    request = normalize_message(_object(protocol["urusilla_request"], "protocol.urusilla_request"))
    if request != protocol["urusilla_request"]:
        raise AutoGenReproductionError("protocol.urusilla_request is not canonical")
    frame = encode_message(request)
    if decode_message(frame) != request:
        raise AutoGenReproductionError("Urusilla request does not round-trip exactly")
    if protocol["urusilla_wire_bytes"] != len(frame):
        raise AutoGenReproductionError("protocol.urusilla_wire_bytes is incorrect")
    if protocol["urusilla_wire_sha256"] != "sha256:" + hashlib.sha256(frame).hexdigest():
        raise AutoGenReproductionError("protocol.urusilla_wire_sha256 is incorrect")

    safety = _object(plan["safety_boundary"], "safety_boundary")
    expected_safety = {
        "declarative_capsule_only": True,
        "read_only": True,
        "session_only": True,
        "tools_enabled": False,
        "memory_enabled": False,
        "persistence_authorized": False,
        "spending_authorized_by_protocol": False,
        "permission_expansion_authorized": False,
        "external_effects_authorized": False,
    }
    if safety != expected_safety:
        raise AutoGenReproductionError("safety_boundary must remain read-only and effect-free")

    task = _object(plan["task"], "task")
    _require_exact_keys(task, {"semantics", "semantics_sha256", "answer_contract"}, "task")
    if task["semantics"] != TASK_SEMANTICS or task["answer_contract"] != ANSWER_CONTRACT:
        raise AutoGenReproductionError("task or answer semantics differ from the frozen design")
    if task["semantics_sha256"] != sha256_ref(task["semantics"]):
        raise AutoGenReproductionError("task.semantics_sha256 is incorrect")

    arms = plan["arms"]
    if type(arms) is not list or len(arms) != len(ARM_IDS):
        raise AutoGenReproductionError("arms must contain raw, structured-json, and urusilla")
    observed_ids: list[str] = []
    for index, raw_arm in enumerate(arms):
        arm = _object(raw_arm, f"arms[{index}]")
        _require_exact_keys(
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
                "tools",
                "memory",
                "turn_limit",
            },
            f"arms[{index}]",
        )
        arm_id = arm["arm_id"]
        observed_ids.append(arm_id)
        if arm["task_semantics_sha256"] != task["semantics_sha256"]:
            raise AutoGenReproductionError(f"{arm_id} does not bind the common task")
        if arm["system_message"] != SYSTEM_MESSAGE:
            raise AutoGenReproductionError(f"{arm_id} changes the common system message")
        if arm["tools"] != [] or arm["memory"] is not None or arm["turn_limit"] != 1:
            raise AutoGenReproductionError(
                f"{arm_id} must remain one-turn, tool-free, and memory-free"
            )
        if not all(
            type(arm[key]) is str
            for key in ("discovery_text", "carrier_text", "model_input_text")
        ):
            raise AutoGenReproductionError(f"{arm_id} text fields must be strings")
        rebuilt = _model_input(arm["discovery_text"], arm["carrier_text"])
        if arm["model_input_text"] != rebuilt:
            raise AutoGenReproductionError(
                f"{arm_id} model input does not match its declared parts"
            )
        encoded = rebuilt.encode("utf-8")
        if arm["model_input_bytes"] != len(encoded):
            raise AutoGenReproductionError(f"{arm_id} model_input_bytes is incorrect")
        if arm["model_input_sha256"] != "sha256:" + hashlib.sha256(encoded).hexdigest():
            raise AutoGenReproductionError(f"{arm_id} model_input_sha256 is incorrect")
    if tuple(observed_ids) != ARM_IDS:
        raise AutoGenReproductionError(f"arm order must be {ARM_IDS}")
    if arms[0]["discovery_text"] != "":
        raise AutoGenReproductionError("raw arm must not contain discovery overhead")
    if arms[2]["discovery_text"] != capsule_text:
        raise AutoGenReproductionError("Urusilla arm must charge the exact Capsule text")
    if strict_json_loads(arms[1]["carrier_text"]) != TASK_SEMANTICS:
        raise AutoGenReproductionError("structured-json carrier changed the task semantics")
    if strict_json_loads(arms[2]["carrier_text"]) != request:
        raise AutoGenReproductionError("Urusilla carrier changed the canonical request")

    matched = _object(plan["matched_design"], "matched_design")
    expected_matched = {
        "arm_order": list(ARM_IDS),
        "fresh_agent_per_arm": True,
        "fresh_model_client_per_arm": True,
        "same_model_and_settings_required": True,
        "same_task_semantics_required": True,
        "same_response_contract_required": True,
        "one_turn_per_arm": True,
        "randomization_status": "fixed-order-minimal-reproduction",
    }
    if matched != expected_matched:
        raise AutoGenReproductionError("matched_design differs from the frozen comparison")

    ledger = _object(plan["ledger_template"], "ledger_template")
    _require_exact_keys(
        ledger,
        {
            "categories",
            "arms",
            "unknown_is_not_zero",
            "raw_json_urusilla_all_required",
            "charge_discovery_teaching_and_fallback",
            "primary_metric",
        },
        "ledger_template",
    )
    if ledger["categories"] != list(LEDGER_CATEGORIES):
        raise AutoGenReproductionError("ledger categories differ from the Interop Lab")
    ledger_arms = _object(ledger["arms"], "ledger_template.arms")
    if tuple(ledger_arms) != ARM_IDS:
        raise AutoGenReproductionError("ledger must retain all three arms in order")
    for arm_id, values in ledger_arms.items():
        values = _object(values, f"ledger_template.arms.{arm_id}")
        if set(values) != set(LEDGER_CATEGORIES) or any(
            value is not None for value in values.values()
        ):
            raise AutoGenReproductionError(
                f"ledger_template.arms.{arm_id} must preserve unknown categories as null"
            )
    if (
        ledger["unknown_is_not_zero"] is not True
        or ledger["raw_json_urusilla_all_required"] is not True
        or ledger["charge_discovery_teaching_and_fallback"] is not True
        or ledger["primary_metric"] != "total-tokens-per-safely-completed-task"
    ):
        raise AutoGenReproductionError("ledger safety and accounting rules changed")

    boundary = _object(plan["claim_boundary"], "claim_boundary")
    expected_boundary = {
        "negative_and_null_evidence_accepted": True,
        "recorded_broad_post_decode_api_input_saving_percent": 0.0,
        "changes_project_wide_claim": False,
        "sota_claim": False,
        "external_adoption_claim": False,
        "structural_preflight_is_adoption": False,
    }
    if boundary != expected_boundary:
        raise AutoGenReproductionError("claim boundary was expanded")

    return {
        "valid": True,
        "structural_validation_only": True,
        "plan_sha256": sha256_ref(plan),
        "capsule_sha256": CAPSULE_SHA256,
        "arms": list(ARM_IDS),
        "recorded_broad_post_decode_api_input_saving_percent": 0.0,
        "project_wide_claim_changed": False,
    }


def offline_preflight(plan: Any) -> dict[str, Any]:
    """Validate all local structure without importing AutoGen or making calls."""

    report = validate_plan(plan)
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "plan_sha256": report["plan_sha256"],
        "capsule_sha256": report["capsule_sha256"],
        "checks": {
            "capsule_byte_digest_verified": True,
            "capsule_is_declarative_json": True,
            "urusilla_ir_canonical": True,
            "urusilla_wire_round_trip_exact": True,
            "matched_three_arm_design_valid": True,
            "ledger_unknowns_preserved": True,
            "safety_boundary_locked": True,
        },
        "autogen_imported": False,
        "provider_calls": 0,
        "network_calls": 0,
        "external_effects": 0,
        "ready_for_operator_model_connection": True,
        "claim_boundary": {
            "structural_only": True,
            "adoption_proven": False,
            "token_saving_proven": False,
            "negative_and_null_evidence_accepted": True,
        },
    }


def _validate_preflight(receipt: Any, plan: Mapping[str, Any]) -> None:
    expected = offline_preflight(plan)
    if receipt != expected:
        raise AutoGenReproductionError(
            "offline preflight receipt is missing, stale, or not byte-bound to this plan"
        )


def _load_assistant_agent_class() -> type[Any]:
    try:
        from autogen_agentchat.agents import AssistantAgent
    except ImportError as exc:
        raise AutoGenReproductionError(
            "optional dependency autogen-agentchat is unavailable; offline preflight "
            "still works, but the guarded model path remains closed"
        ) from exc
    return AssistantAgent


def _autogen_version() -> str:
    try:
        return metadata.version("autogen-agentchat")
    except metadata.PackageNotFoundError:
        return "injected-or-unknown"


def _extract_text_and_usage(result: Any) -> tuple[str, int | None, int | None]:
    messages = getattr(result, "messages", None)
    if type(messages) is not list or not messages:
        raise AutoGenReproductionError("AutoGen result must expose a non-empty messages list")
    content = getattr(messages[-1], "content", None)
    if type(content) is not str:
        raise AutoGenReproductionError("AutoGen final response must be public text")
    prompt_total = 0
    completion_total = 0
    saw_usage = False
    for message in messages:
        usage = getattr(message, "models_usage", None)
        if usage is None:
            continue
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        if type(prompt) is not int or prompt < 0 or type(completion) is not int or completion < 0:
            raise AutoGenReproductionError("AutoGen models_usage contains invalid token counts")
        prompt_total += prompt
        completion_total += completion
        saw_usage = True
    return (
        content,
        prompt_total if saw_usage else None,
        completion_total if saw_usage else None,
    )


def _score_public_answer(text: str) -> tuple[bool, list[str]]:
    failures: list[str] = []
    try:
        value = strict_json_loads(text)
    except ValidationError as exc:
        return False, [f"response is not strict JSON: {exc}"]
    if type(value) is not dict:
        return False, ["response must be a JSON object"]
    required = {"selected_plan", "feasible_plans", "reason", "would_execute"}
    if set(value) != required:
        failures.append("response fields differ from the frozen contract")
    if value.get("selected_plan") is not None:
        failures.append("selected_plan must be null because no tie-breaker was supplied")
    if value.get("feasible_plans") != ["plan-a", "plan-b"]:
        failures.append("feasible_plans must be [plan-a, plan-b] in canonical order")
    if type(value.get("reason")) is not str or not value.get("reason", "").strip():
        failures.append("reason must be a non-empty public string")
    if value.get("would_execute") is not False:
        failures.append("would_execute must be false")
    return not failures, failures


async def _close_clients(clients: Sequence[Any]) -> None:
    closed: set[int] = set()
    for client in clients:
        if id(client) in closed:
            continue
        closed.add(id(client))
        close = getattr(client, "close", None)
        if close is None:
            continue
        result = close()
        if inspect.isawaitable(result):
            await result


def _saving(raw: int | None, candidate: int | None) -> float | None:
    if raw is None or candidate is None or raw == 0:
        return None
    return (raw - candidate) * 100.0 / raw


async def run_autogen_trial(
    plan: Mapping[str, Any],
    preflight_receipt: Mapping[str, Any],
    model_client_factory: Callable[[str], Any],
    *,
    operator_approved_model_calls: bool = False,
    assistant_agent_class: type[Any] | None = None,
    include_public_response: bool = False,
) -> dict[str, Any]:
    """Run one guarded AutoGen call per arm after explicit operator approval.

    The caller owns provider configuration and cost authority.  This adapter
    supplies no tools, memory, persistence, or effect path.  AutoGen's
    ``models_usage`` is retained as a model-usage-only observation; it is not
    silently promoted to a complete task-token ledger.
    """

    validate_plan(plan)
    _validate_preflight(preflight_receipt, plan)
    if operator_approved_model_calls is not True:
        raise AutoGenReproductionError(
            "operator_approved_model_calls=True is required before AutoGen import "
            "or client creation"
        )
    if not callable(model_client_factory):
        raise AutoGenReproductionError("model_client_factory must be callable")
    if type(include_public_response) is not bool:
        raise AutoGenReproductionError("include_public_response must be a boolean")
    agent_class = assistant_agent_class or _load_assistant_agent_class()

    clients: list[Any] = []
    try:
        for arm_id in ARM_IDS:
            client = model_client_factory(arm_id)
            if client is None:
                raise AutoGenReproductionError(f"factory returned no client for {arm_id}")
            clients.append(client)
        if len({id(client) for client in clients}) != len(clients):
            raise AutoGenReproductionError(
                "model_client_factory must return a fresh client for every arm"
            )

        observations: list[dict[str, Any]] = []
        for arm, client in zip(plan["arms"], clients, strict=True):
            agent = agent_class(
                name="urusilla_" + arm["arm_id"].replace("-", "_"),
                model_client=client,
                system_message=arm["system_message"],
                tools=[],
                memory=None,
                reflect_on_tool_use=False,
            )
            result = await agent.run(task=arm["model_input_text"])
            response, prompt_tokens, completion_tokens = _extract_text_and_usage(result)
            task_success, failures = _score_public_answer(response)
            model_usage_total = (
                prompt_tokens + completion_tokens
                if prompt_tokens is not None and completion_tokens is not None
                else None
            )
            observations.append(
                {
                    "arm_id": arm["arm_id"],
                    "response_sha256": "sha256:"
                    + hashlib.sha256(response.encode("utf-8")).hexdigest(),
                    "response_bytes": len(response.encode("utf-8")),
                    "public_response": response if include_public_response else None,
                    "publication_review_required": True,
                    "task_success": task_success,
                    "semantic_failures": failures,
                    "token_ledger": {
                        "status": (
                            "model-usage-only" if model_usage_total is not None else "not-measured"
                        ),
                        "provider_prompt_tokens": prompt_tokens,
                        "provider_completion_tokens": completion_tokens,
                        "reported_reasoning_tokens": None,
                        "model_usage_only_total_tokens": model_usage_total,
                        "complete_total_task_tokens": None,
                        "post_decode_api_input_tokens": prompt_tokens,
                    },
                }
            )
    finally:
        await _close_clients(clients)

    by_id = {item["arm_id"]: item for item in observations}
    raw_ledger = by_id["raw"]["token_ledger"]
    comparisons: dict[str, Any] = {}
    for arm_id in ("structured-json", "urusilla"):
        candidate = by_id[arm_id]["token_ledger"]
        comparisons[f"{arm_id}_vs_raw"] = {
            "post_decode_api_input_saving_percent": _saving(
                raw_ledger["post_decode_api_input_tokens"],
                candidate["post_decode_api_input_tokens"],
            ),
            "model_usage_only_saving_percent": _saving(
                raw_ledger["model_usage_only_total_tokens"],
                candidate["model_usage_only_total_tokens"],
            ),
            "complete_total_task_token_saving_percent": None,
        }
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "plan_sha256": sha256_ref(plan),
        "framework": {
            "name": "Microsoft AutoGen AgentChat",
            "version": _autogen_version(),
            "support_mode": "bridge-evaluation",
            "one_fresh_agent_and_client_per_arm": True,
            "same_model_and_settings_verified_by_adapter": False,
        },
        "observations": observations,
        "comparisons": comparisons,
        "safety_attestation": {
            "tools_supplied": False,
            "memory_supplied": False,
            "persistence_authorized": False,
            "protocol_authorized_spending": False,
            "permission_expansion_authorized": False,
            "external_effects_authorized": False,
        },
        "claim_boundary": {
            "negative_and_null_evidence_accepted": True,
            "complete_total_task_tokens_measured": False,
            "recorded_broad_post_decode_api_input_saving_percent": 0.0,
            "changes_project_wide_claim": False,
            "sota_claim": False,
            "external_adoption_claim": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and verify an offline-first Urusilla AutoGen reproduction."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="write a frozen three-arm plan")
    initialize.add_argument("output", type=Path)
    initialize.add_argument("--capsule", type=Path)
    initialize.add_argument("--experiment-id", default="autogen-repro-v1")
    validate = commands.add_parser("validate", help="validate a plan without AutoGen")
    validate.add_argument("plan", type=Path)
    validate.add_argument("--json", action="store_true")
    preflight = commands.add_parser(
        "preflight", help="emit a byte-bound offline receipt without AutoGen"
    )
    preflight.add_argument("plan", type=Path)
    preflight.add_argument(
        "--output",
        type=Path,
        help="write the receipt once instead of printing it",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            plan = build_plan(
                capsule_path=args.capsule,
                experiment_id=args.experiment_id,
            )
            _write_new(args.output, plan)
            print(f"wrote {args.output}")
            return 0
        plan = load_record(args.plan)
        report = offline_preflight(plan) if args.command == "preflight" else validate_plan(plan)
        if args.command == "preflight" and args.output is not None:
            _write_new(args.output, report)
            print(f"wrote {args.output}")
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
        print(f"valid offline plan: {report['plan_sha256']}")
        print("AutoGen imported: no")
        print("provider calls: 0; network calls: 0; external effects: 0")
        print("project-wide broad post-decode baseline remains: 0%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
