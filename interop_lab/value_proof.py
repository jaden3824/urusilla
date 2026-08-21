#!/usr/bin/env python3
"""Offline evidence gate for the experimental Urusilla value proof.

This module freezes and validates a three-arm experiment.  It deliberately has
no model/provider adapter: model calls can only be made by an external runner
after an operator records explicit opt-in.  Unknown measurements remain null.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

try:
    from .interop_lab import ValidationError, strict_json_loads
except ImportError:  # Support direct execution from the repository root.
    from interop_lab import ValidationError, strict_json_loads  # type: ignore[no-redef]


PLAN_SCHEMA = "urusilla-experimental-value-proof-plan/1"
RESULT_SCHEMA = "urusilla-experimental-value-proof-result/1"
CHALLENGE_ID = "challenge-002"
ARM_IDS = ("raw-concise", "ordinary-json", "urusilla-direct")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "repair_tokens",
    "tool_tokens",
    "hidden_tokens",
    "unclassified_tokens",
    "total_tokens",
)
HIDDEN_ACCOUNTING = (
    "not-reported",
    "included-in-output",
    "separately-reported",
    "included-in-unclassified",
)

SYSTEM_TEXT = (
    "You are in a bounded, read-only synthetic evaluation. Use no tools, "
    "memory, persistence, network, spending, permission changes, or external "
    "effects. Return only the requested public JSON object and do not reveal "
    "private chain-of-thought."
)

EXPECTED_OUTPUT = {
    "feasible_plans": ["plan-a", "plan-b"],
    "selected_plan": None,
    "would_execute": False,
}

RESPONSE_CONTRACT = (
    'Return exactly one JSON object with keys "feasible_plans", '
    '"selected_plan", and "would_execute". List every feasible plan in ID '
    "order. Select a plan only when the facts uniquely justify one; otherwise "
    'use null. "would_execute" must be false.'
)

TASK_SEMANTICS = {
    "plans": [
        {
            "id": "plan-a",
            "cost_cents": 20,
            "network_required": False,
            "verification_passes": 1,
        },
        {
            "id": "plan-b",
            "cost_cents": 70,
            "network_required": False,
            "verification_passes": 2,
        },
    ],
    "hard_constraints": {
        "cost_cents_lte": 100,
        "network_allowed": False,
    },
    "utility_tie_breaker": None,
}

RAW_CONCISE = (
    "plan-a costs 20 cents, needs no network, and uses 1 verification pass. "
    "plan-b costs 70 cents, needs no network, and uses 2 verification passes. "
    "Hard limits: cost <= 100 cents and network forbidden. No utility tie-breaker."
)

RAW_INDUCTION = "Read the task as concise natural language."
JSON_INDUCTION = "Read the task as an ordinary self-describing JSON object."
PROJECTION_GLOSSARY = (
    "Read the USX structured plan facts."
)

DEVELOPMENT_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}

DEVELOPMENT_TOKEN_COUNTS = {
    "raw-concise": {
        "cl100k_base": 172,
        "o200k_base": 172,
        "qwen2_5_7b_instruct": 176,
        "mistral_7b_instruct_v03": 204,
    },
    "initial-upx-rejected": {
        "cl100k_base": 190,
        "o200k_base": 190,
        "qwen2_5_7b_instruct": 194,
        "mistral_7b_instruct_v03": 230,
    },
    "ordinary-json": {
        "cl100k_base": 194,
        "o200k_base": 195,
        "qwen2_5_7b_instruct": 198,
        "mistral_7b_instruct_v03": 246,
    },
    "urusilla-direct-usx": {
        "cl100k_base": 157,
        "o200k_base": 157,
        "qwen2_5_7b_instruct": 161,
        "mistral_7b_instruct_v03": 195,
    },
}

PROMOTION_POLICY = {
    "single_result_can_promote_protocol_version": False,
    "minimum_independent_operators": 2,
    "minimum_model_families": 2,
    "requirements": [
        "all three arms use the frozen task, model settings, and fresh isolated contexts",
        "every model call has explicit operator opt-in evidence",
        "Urusilla task success is non-inferior and all three arms satisfy the exact rubric",
        "every total-token ledger reconciles without treating null as zero",
        "Urusilla total tokens are strictly below both control arms",
        "no tool, persistence, spending-authority, permission, or external-effect boundary is crossed",
        "negative, failed, declined, and null results remain published",
        "a later confirmation uses preregistered unseen tasks rather than this known task alone",
    ],
}


class ValueProofError(ValidationError):
    """Raised when a value-proof plan or result is not trustworthy."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_ref(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = _canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _request_message() -> dict[str, Any]:
    from urusilla import normalize_message

    return normalize_message(
        {
            "id": "018f4f2e-1d33-7b62-8af8-5a09497d34b3",
            "session": "018f4f2e-0ea2-7cad-a224-b98558052767",
            "sender": "urusilla.value-proof",
            "recipients": ["external.model"],
            "act": "REQUEST",
            "schema": "urn:urusilla:value-proof:plan-selection:1",
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
                        "scope": "safety",
                        "mode": "hard",
                        "condition": {
                            "tools": False,
                            "persistence": False,
                            "spending_authority": False,
                            "permission_expansion": False,
                            "external_effects": False,
                        },
                    }
                ],
            },
            "meta": {
                "experiment": CHALLENGE_ID,
                "response_contract": EXPECTED_OUTPUT,
            },
        }
    )


def encode_projection(task: Mapping[str, Any]) -> str:
    """Encode the frozen plan-selection schema, not a universal message language."""

    if dict(task) != TASK_SEMANTICS:
        raise ValueProofError("projection accepts only the frozen challenge task schema")
    hard = task["hard_constraints"]
    rendered_rows = ";".join(
        f"{plan['id']} cost={plan['cost_cents']} "
        f"net={'yes' if plan['network_required'] else 'no'} "
        f"verify={plan['verification_passes']}"
        for plan in task["plans"]
    )
    return (
        f"USX|plans:[{rendered_rows}]|hard:[cost<={hard['cost_cents_lte']},"
        f"net={'yes' if hard['network_allowed'] else 'no'}]|tie:none"
    )


def decode_projection(text: str) -> dict[str, Any]:
    """Decode the bounded projection and reject every non-canonical variant."""

    if type(text) is not str:
        raise ValueProofError("projection must be text")
    match = re.fullmatch(
        r"USX\|plans:\[([^|]+)\]\|hard:\[cost<=([0-9]+),net=(yes|no)\]"
        r"\|tie:(none)",
        text,
    )
    if match is None:
        raise ValueProofError("projection syntax is invalid")
    plans = []
    for row in match.group(1).split(";"):
        row_match = re.fullmatch(
            r"([^ ;|=\[\],]+) cost=([0-9]+) net=(yes|no) verify=([0-9]+)",
            row,
        )
        if row_match is None:
            raise ValueProofError("projection plan row is invalid")
        try:
            cost = int(row_match.group(2))
            verification = int(row_match.group(4))
        except ValueError as exc:
            raise ValueProofError("projection integer is invalid") from exc
        if cost < 0 or verification < 0:
            raise ValueProofError("projection plan value is invalid")
        plans.append(
            {
                "id": row_match.group(1),
                "cost_cents": cost,
                "network_required": row_match.group(3) == "yes",
                "verification_passes": verification,
            }
        )
    result = {
        "plans": plans,
        "hard_constraints": {
            "cost_cents_lte": int(match.group(2)),
            "network_allowed": match.group(3) == "yes",
        },
        "utility_tie_breaker": None,
    }
    if encode_projection(result) != text:
        raise ValueProofError("projection is valid but non-canonical")
    return result


def _model_visible_text(induction: str, carrier: str) -> str:
    return "\n\n".join(
        (
            "SYSTEM\n" + SYSTEM_TEXT,
            "FORMAT\n" + induction,
            "TASK\n" + carrier,
            "RESPONSE CONTRACT\n" + RESPONSE_CONTRACT,
        )
    )


def _arm(
    arm_id: str,
    induction: str,
    carrier: str,
    task_digest: str,
    carrier_kind: str,
) -> dict[str, Any]:
    model_input = _model_visible_text(induction, carrier)
    return {
        "arm_id": arm_id,
        "task_semantics_sha256": task_digest,
        "system_text": SYSTEM_TEXT,
        "format_induction": induction,
        "carrier": carrier,
        "carrier_kind": carrier_kind,
        "response_contract": RESPONSE_CONTRACT,
        "model_visible_text": model_input,
        "model_visible_sha256": sha256_ref(model_input),
        "model_visible_utf8_bytes": len(model_input.encode("utf-8")),
        "decode_before_model": False,
        "natural_language_expansion": None,
        "transport_envelope_model_visible": False,
        "task_binding_sha256": task_digest,
        "tools": [],
        "memory": None,
        "turn_limit": 1,
    }


def build_plan() -> dict[str, Any]:
    """Build the deterministic three-arm plan without calling a model."""

    request = _request_message()
    projection = encode_projection(TASK_SEMANTICS)
    if decode_projection(projection) != TASK_SEMANTICS:
        raise ValueProofError("the direct task projection does not round-trip")
    task_digest = sha256_ref(TASK_SEMANTICS)
    json_carrier = _canonical_json(TASK_SEMANTICS)
    arms = [
        _arm(
            "raw-concise",
            RAW_INDUCTION,
            RAW_CONCISE,
            task_digest,
            "concise-natural-language",
        ),
        _arm(
            "ordinary-json",
            JSON_INDUCTION,
            json_carrier,
            task_digest,
            "ordinary-json",
        ),
        _arm(
            "urusilla-direct",
            PROJECTION_GLOSSARY,
            projection,
            task_digest,
            "experimental-task-semantic-projection",
        ),
    ]
    return {
        "schema_version": PLAN_SCHEMA,
        "challenge_id": CHALLENGE_ID,
        "status": "experimental-value-proof-only",
        "protocol": {
            "language_version": "0.1.0",
            "version_bump_requested": False,
            "surface": "challenge-002-task-semantic-projection",
            "surface_scope": "frozen-plan-selection-schema-only",
            "universal_lossless_claim": False,
            "direct_model_input": True,
            "transport_envelope_model_visible": False,
            "request": request,
            "request_sha256": sha256_ref(request),
        },
        "task": {
            "semantics": TASK_SEMANTICS,
            "semantics_sha256": task_digest,
            "expected_public_output": EXPECTED_OUTPUT,
            "success_rubric": {
                "parse": "one JSON object and no prose",
                "exact_keys": ["feasible_plans", "selected_plan", "would_execute"],
                "feasible_plans": ["plan-a", "plan-b"],
                "selected_plan": None,
                "would_execute": False,
            },
        },
        "arms": arms,
        "matched_design": {
            "same_task_semantics": True,
            "same_system_text": True,
            "same_response_contract": True,
            "same_model_and_settings_required": True,
            "fresh_context_per_arm_required": True,
            "no_cross_arm_state_required": True,
            "one_turn_per_arm": True,
        },
        "evaluation_regimes": {
            "cold_one_turn": {
                "included_in_this_challenge": True,
                "format_induction_charged_in_full": True,
                "task_count": 1,
            },
            "warm_amortized": {
                "included_in_this_challenge": False,
                "requires_separate_preregistered_multi_task_sequence": True,
                "may_not_repeat_this_known_task_to_claim_generalization": True,
                "induction_must_be_charged_once_per_actual_session": True,
            },
        },
        "development_history": {
            "model_calls_before_surface_selection": 0,
            "known_task_and_tokenizers_used_for_selection": True,
            "confirmatory_evidence": False,
            "initial_upx_rejected_for_raw_token_regression": True,
            "tokenizer_fingerprints": DEVELOPMENT_TOKENIZER_FINGERPRINTS,
            "complete_model_visible_token_counts": DEVELOPMENT_TOKEN_COUNTS,
            "next_gate": (
                "freeze the USX surface first, then evaluate preregistered unseen tasks"
            ),
        },
        "token_ledger": {
            "fields": list(TOKEN_FIELDS),
            "unknown_is_null_not_zero": True,
            "categories_are_non_overlapping": True,
            "input_tokens_definition": (
                "complete primary-call input, including system text, format "
                "induction, carrier, and response contract"
            ),
            "repair_tokens_definition": (
                "all repair-call input and output tokens, excluded from the "
                "primary input and output fields"
            ),
            "hidden_tokens_definition": (
                "optional diagnostic subset; it is additive only when "
                "hidden_accounting is separately-reported"
            ),
            "separate_induction_field": False,
            "total_reconciliation": (
                "input + output + repair + tool + hidden-if-separate "
                "+ unclassified"
            ),
            "primary_metric": "total tokens per exact successful bounded task",
        },
        "execution_policy": {
            "this_artifact_calls_models": False,
            "external_runner_required": True,
            "explicit_model_call_opt_in_required": True,
            "protocol_must_not_create_spending_authority": True,
            "provider_or_api_calls_during_offline_validation": 0,
        },
        "safety_boundary": {
            "tools_allowed": False,
            "persistence_allowed": False,
            "spending_authority_allowed": False,
            "permission_expansion_allowed": False,
            "external_effects_allowed": False,
        },
        "gate": {
            "task_success_noninferiority": (
                "all arms must satisfy the exact rubric; Urusilla may not fail "
                "where either control succeeds"
            ),
            "total_token_reduction": (
                "Urusilla total_tokens must be strictly below raw-concise and "
                "ordinary-json total_tokens"
            ),
            "failed_declined_rejected_and_null_results_are_evidence": True,
        },
        "claim_boundary": {
            "known_task_cherry_pick_risk": True,
            "task_specific_projection_only": True,
            "general_or_lossless_surface_claim": False,
            "warm_session_claim": False,
        },
        "promotion_policy": PROMOTION_POLICY,
    }


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueProofError(f"{path} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], path: str) -> None:
    if set(value) != keys:
        raise ValueProofError(
            f"{path} fields differ; missing={sorted(keys - set(value))}, "
            f"extra={sorted(set(value) - keys)}"
        )


def validate_plan(value: Any) -> dict[str, Any]:
    """Validate an exact frozen plan and its direct-model-input invariant."""

    plan = _require_object(value, "plan")
    expected = build_plan()
    if plan != expected:
        raise ValueProofError("plan differs from the frozen challenge-002 design")
    arms = {arm["arm_id"]: arm for arm in plan["arms"]}
    direct = arms["urusilla-direct"]
    if direct["decode_before_model"] or direct["natural_language_expansion"] is not None:
        raise ValueProofError("Urusilla must reach the model without natural-language expansion")
    if direct["transport_envelope_model_visible"]:
        raise ValueProofError("transport envelope must remain outside model input")
    decoded = decode_projection(direct["carrier"])
    if decoded != plan["task"]["semantics"]:
        raise ValueProofError("direct carrier does not decode to the frozen task semantics")
    if encode_projection(decoded) != direct["carrier"]:
        raise ValueProofError("direct task projection is not canonical")
    return {
        "valid": True,
        "challenge_id": CHALLENGE_ID,
        "plan_sha256": sha256_ref(plan),
        "arms": list(ARM_IDS),
        "provider_calls": 0,
        "direct_model_input_without_expansion": True,
        "protocol_version_changed": False,
    }


def _blank_ledger() -> dict[str, Any]:
    return {
        **{field: None for field in TOKEN_FIELDS},
        "hidden_accounting": "not-reported",
        "provider_reported_total_tokens": None,
    }


def _blank_observation(arm_id: str) -> dict[str, Any]:
    return {
        "arm_id": arm_id,
        "disposition": "not-run",
        "model_call": {
            "attempted": False,
            "explicit_operator_opt_in": False,
            "opt_in_evidence_sha256": None,
        },
        "public_output": None,
        "task_success": None,
        "rubric_failures": [],
        "token_ledger": _blank_ledger(),
        "fallbacks": [],
        "safety": {
            "tools_used": False,
            "persistence_created": False,
            "spending_authority_created": False,
            "permission_expanded": False,
            "external_effects_performed": False,
        },
    }


def build_result_template(plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a null-preserving result template; this does not run any arm."""

    frozen_plan = build_plan() if plan is None else dict(plan)
    validate_plan(frozen_plan)
    return {
        "schema_version": RESULT_SCHEMA,
        "challenge_id": CHALLENGE_ID,
        "plan_sha256": sha256_ref(frozen_plan),
        "result_status": "not-run",
        "environment": {
            "model": None,
            "model_family": None,
            "runtime": None,
            "tokenizer": None,
            "settings_sha256": None,
            "operator_id": None,
        },
        "execution_attestation": {
            "same_model_and_settings": None,
            "fresh_context_per_arm": None,
            "no_cross_arm_state": None,
            "arm_order": None,
        },
        "observations": [_blank_observation(arm_id) for arm_id in ARM_IDS],
        "notes": [],
    }


def _score_output(value: Any) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if type(value) is not dict:
        return False, ["public_output is not one JSON object"]
    expected_keys = set(EXPECTED_OUTPUT)
    if set(value) != expected_keys:
        failures.append("public_output keys differ from the exact contract")
    if value.get("feasible_plans") != EXPECTED_OUTPUT["feasible_plans"]:
        failures.append("feasible_plans is not the exact ordered feasible set")
    if value.get("selected_plan", object()) is not None:
        failures.append("selected_plan must be null because no unique plan is justified")
    if value.get("would_execute") is not False:
        failures.append("would_execute must be false")
    return not failures, failures


def _nullable_count(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueProofError(f"{path} must be a nonnegative integer or null")
    return value


def _validate_ledger(value: Any, path: str, attempted: bool) -> int | None:
    ledger = _require_object(value, path)
    _require_exact_keys(
        ledger,
        set(TOKEN_FIELDS) | {"hidden_accounting", "provider_reported_total_tokens"},
        path,
    )
    counts = {field: _nullable_count(ledger[field], f"{path}.{field}") for field in TOKEN_FIELDS}
    provider_total = _nullable_count(
        ledger["provider_reported_total_tokens"],
        f"{path}.provider_reported_total_tokens",
    )
    status = ledger["hidden_accounting"]
    if status not in HIDDEN_ACCOUNTING:
        raise ValueProofError(f"{path}.hidden_accounting is invalid")

    if not attempted:
        if any(value is not None for value in counts.values()) or provider_total is not None:
            raise ValueProofError(f"{path} must remain null when no model call was attempted")
        if status != "not-reported":
            raise ValueProofError(f"{path}.hidden_accounting must be not-reported")
        return None

    if counts["tool_tokens"] not in (0, None):
        raise ValueProofError(f"{path}.tool_tokens must be zero in the no-tools lane")
    hidden = counts["hidden_tokens"]
    if status == "not-reported" and hidden is not None:
        raise ValueProofError(f"{path}.hidden_tokens must be null when not reported")
    if status != "not-reported" and hidden is None:
        raise ValueProofError(f"{path}.hidden_tokens is required for disclosed accounting")
    if status == "included-in-output" and hidden is not None:
        output = counts["output_tokens"]
        if output is None or hidden > output:
            raise ValueProofError(f"{path}.hidden_tokens must be a subset of output_tokens")
    if status == "included-in-unclassified" and hidden is not None:
        unclassified = counts["unclassified_tokens"]
        if unclassified is None or hidden > unclassified:
            raise ValueProofError(
                f"{path}.hidden_tokens must be a subset of unclassified_tokens"
            )

    total = counts["total_tokens"]
    components = [
        counts["input_tokens"],
        counts["output_tokens"],
        counts["repair_tokens"],
        counts["tool_tokens"],
        counts["unclassified_tokens"],
    ]
    if status == "separately-reported":
        components.append(hidden)
    if all(component is not None for component in components):
        reconciled = sum(component for component in components if component is not None)
        if total is not None and total != reconciled:
            raise ValueProofError(
                f"{path}.total_tokens does not reconcile: expected {reconciled}"
            )
    elif total is not None:
        raise ValueProofError(f"{path}.total_tokens must be null while a category is null")
    if status == "not-reported" and provider_total is None and total is not None:
        raise ValueProofError(
            f"{path}.total_tokens requires a provider total when hidden usage is unreported"
        )
    if provider_total is not None and provider_total != total:
        raise ValueProofError(f"{path}.provider_reported_total_tokens differs from total_tokens")
    return total


def _saving_percent(baseline: int | None, candidate: int | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    value = (Decimal(baseline - candidate) * Decimal(100)) / Decimal(baseline)
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def validate_result(value: Any, plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate evidence, recompute the rubric and return the conservative gate."""

    frozen_plan = build_plan() if plan is None else dict(plan)
    validate_plan(frozen_plan)
    result = _require_object(value, "result")
    _require_exact_keys(
        result,
        {
            "schema_version",
            "challenge_id",
            "plan_sha256",
            "result_status",
            "environment",
            "execution_attestation",
            "observations",
            "notes",
        },
        "result",
    )
    if result["schema_version"] != RESULT_SCHEMA or result["challenge_id"] != CHALLENGE_ID:
        raise ValueProofError("result schema or challenge identity differs")
    if result["plan_sha256"] != sha256_ref(frozen_plan):
        raise ValueProofError("result does not bind the frozen plan")
    if result["result_status"] not in {
        "not-run",
        "completed",
        "partial",
        "failed",
        "declined",
        "rejected",
    }:
        raise ValueProofError("result_status is invalid")

    environment = _require_object(result["environment"], "environment")
    environment_keys = {
        "model",
        "model_family",
        "runtime",
        "tokenizer",
        "settings_sha256",
        "operator_id",
    }
    _require_exact_keys(environment, environment_keys, "environment")
    for key, item in environment.items():
        if item is not None and (type(item) is not str or not item):
            raise ValueProofError(f"environment.{key} must be non-empty text or null")
    if environment["settings_sha256"] is not None and SHA256_RE.fullmatch(
        environment["settings_sha256"]
    ) is None:
        raise ValueProofError("environment.settings_sha256 must be a SHA-256 reference")

    attestation = _require_object(result["execution_attestation"], "execution_attestation")
    _require_exact_keys(
        attestation,
        {"same_model_and_settings", "fresh_context_per_arm", "no_cross_arm_state", "arm_order"},
        "execution_attestation",
    )
    for key in ("same_model_and_settings", "fresh_context_per_arm", "no_cross_arm_state"):
        if attestation[key] not in (True, False, None):
            raise ValueProofError(f"execution_attestation.{key} must be boolean or null")
    arm_order = attestation["arm_order"]
    if arm_order is not None and (
        type(arm_order) is not list or sorted(arm_order) != sorted(ARM_IDS)
    ):
        raise ValueProofError("execution_attestation.arm_order must contain every arm once")

    observations = result["observations"]
    if type(observations) is not list or len(observations) != len(ARM_IDS):
        raise ValueProofError("observations must contain exactly three arms")
    task_success: dict[str, bool | None] = {}
    totals: dict[str, int | None] = {}
    dispositions: list[str] = []
    attempted_count = 0
    explicit_negative = False
    for index, raw_observation in enumerate(observations):
        path = f"observations[{index}]"
        observation = _require_object(raw_observation, path)
        _require_exact_keys(
            observation,
            {
                "arm_id",
                "disposition",
                "model_call",
                "public_output",
                "task_success",
                "rubric_failures",
                "token_ledger",
                "fallbacks",
                "safety",
            },
            path,
        )
        arm_id = observation["arm_id"]
        if arm_id != ARM_IDS[index]:
            raise ValueProofError("observations must use the frozen arm order")
        disposition = observation["disposition"]
        if disposition not in {"not-run", "completed", "failed", "declined", "rejected"}:
            raise ValueProofError(f"{path}.disposition is invalid")
        dispositions.append(disposition)

        call = _require_object(observation["model_call"], f"{path}.model_call")
        _require_exact_keys(
            call,
            {"attempted", "explicit_operator_opt_in", "opt_in_evidence_sha256"},
            f"{path}.model_call",
        )
        if type(call["attempted"]) is not bool or type(call["explicit_operator_opt_in"]) is not bool:
            raise ValueProofError(f"{path}.model_call booleans are invalid")
        attempted = call["attempted"]
        evidence = call["opt_in_evidence_sha256"]
        if attempted:
            attempted_count += 1
            if not call["explicit_operator_opt_in"] or (
                type(evidence) is not str or SHA256_RE.fullmatch(evidence) is None
            ):
                raise ValueProofError(f"{path} attempted a model call without explicit opt-in evidence")
            if disposition in {"not-run", "declined", "rejected"}:
                raise ValueProofError(f"{path}.disposition conflicts with an attempted model call")
        elif call["explicit_operator_opt_in"] or evidence is not None:
            raise ValueProofError(f"{path} records opt-in without an attempted model call")
        elif disposition in {"completed", "failed"}:
            raise ValueProofError(f"{path}.disposition requires an attempted model call")

        if type(observation["rubric_failures"]) is not list or not all(
            type(item) is str and item for item in observation["rubric_failures"]
        ):
            raise ValueProofError(f"{path}.rubric_failures must be a text list")
        if type(observation["fallbacks"]) is not list or not all(
            type(item) is str and item for item in observation["fallbacks"]
        ):
            raise ValueProofError(f"{path}.fallbacks must be a text list")

        if not attempted and observation["public_output"] is not None:
            raise ValueProofError(f"{path} cannot contain output without a model call")
        if attempted and disposition == "completed" and observation["public_output"] is None:
            raise ValueProofError(f"{path}.completed requires a public output")
        if observation["public_output"] is None:
            if observation["task_success"] is not None or observation["rubric_failures"]:
                raise ValueProofError(f"{path} cannot infer task success without public output")
            observed_success = None
        else:
            observed_success, failures = _score_output(observation["public_output"])
            if observation["task_success"] is not observed_success:
                raise ValueProofError(f"{path}.task_success differs from the exact rubric")
            if observation["rubric_failures"] != failures:
                raise ValueProofError(f"{path}.rubric_failures differs from the exact rubric")
        task_success[arm_id] = observed_success
        totals[arm_id] = _validate_ledger(observation["token_ledger"], f"{path}.token_ledger", attempted)

        safety = _require_object(observation["safety"], f"{path}.safety")
        safety_keys = {
            "tools_used",
            "persistence_created",
            "spending_authority_created",
            "permission_expanded",
            "external_effects_performed",
        }
        _require_exact_keys(safety, safety_keys, f"{path}.safety")
        if any(value is not False for value in safety.values()):
            raise ValueProofError(f"{path}.safety must remain entirely false")
        if disposition in {"failed", "declined", "rejected"} or observed_success is False:
            explicit_negative = True

    if type(result["notes"]) is not list or not all(
        type(item) is str and item for item in result["notes"]
    ):
        raise ValueProofError("notes must be a text list")
    if attempted_count and any(environment[key] is None for key in environment_keys):
        raise ValueProofError("environment must be complete when a model call was attempted")
    if attempted_count and (
        any(attestation[key] is None for key in ("same_model_and_settings", "fresh_context_per_arm", "no_cross_arm_state"))
        or arm_order is None
    ):
        raise ValueProofError("execution attestation must be complete after a model call")

    result_status = result["result_status"]
    if result_status == "not-run" and (
        attempted_count != 0 or any(item != "not-run" for item in dispositions)
    ):
        raise ValueProofError("result_status not-run requires three untouched observations")
    if result_status == "completed" and (
        attempted_count != len(ARM_IDS)
        or any(item != "completed" for item in dispositions)
    ):
        raise ValueProofError("result_status completed requires three completed calls")
    if result_status == "partial" and attempted_count in {0, len(ARM_IDS)}:
        raise ValueProofError("result_status partial requires one or two attempted calls")
    if result_status in {"declined", "rejected"} and attempted_count != 0:
        raise ValueProofError(f"result_status {result_status} cannot include model calls")
    if result_status == "failed" and (
        attempted_count == 0 or "failed" not in dispositions
    ):
        raise ValueProofError("result_status failed requires an attempted failed observation")

    successes_known = all(task_success[arm_id] is not None for arm_id in ARM_IDS)
    all_success = successes_known and all(task_success[arm_id] is True for arm_id in ARM_IDS)
    noninferiority = None if not successes_known else bool(all_success)
    raw_saving = _saving_percent(totals["raw-concise"], totals["urusilla-direct"])
    json_saving = _saving_percent(totals["ordinary-json"], totals["urusilla-direct"])
    token_gate = (
        None
        if raw_saving is None or json_saving is None
        else raw_saving > 0 and json_saving > 0
    )
    matched = all(
        attestation[key] is True
        for key in ("same_model_and_settings", "fresh_context_per_arm", "no_cross_arm_state")
    )
    complete_calls = attempted_count == len(ARM_IDS)
    if explicit_negative:
        candidate_gate = False
    elif noninferiority is None or token_gate is None or not complete_calls:
        candidate_gate = None
    else:
        candidate_gate = bool(noninferiority and token_gate and matched)
    return {
        "valid": True,
        "challenge_id": CHALLENGE_ID,
        "structural_validation_only": True,
        "provider_calls_by_validator": 0,
        "task_success": task_success,
        "total_tokens": totals,
        "task_success_noninferiority": noninferiority,
        "urusilla_saving_percent_vs_raw": raw_saving,
        "urusilla_saving_percent_vs_json": json_saving,
        "total_token_reduction_gate": token_gate,
        "matched_execution_gate": matched if attempted_count else None,
        "candidate_value_gate_passed": candidate_gate,
        "single_result_promotes_protocol_version": False,
        "negative_or_null_evidence_preserved": explicit_negative or candidate_gate is None,
        "promotion_policy": PROMOTION_POLICY,
    }


def _load(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueProofError(f"cannot read {path}: {exc}") from exc


def _write_new(path: Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as destination:
            destination.write(text)
    except FileExistsError as exc:
        raise ValueProofError(f"refusing to overwrite existing path: {path}") from exc
    except OSError as exc:
        raise ValueProofError(f"cannot write {path}: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Urusilla challenge-002 value gate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("validate-plan")
    plan.add_argument("path", type=Path)
    result = subparsers.add_parser("validate-result")
    result.add_argument("path", type=Path)
    result.add_argument("--plan", type=Path)
    init = subparsers.add_parser("init-result")
    init.add_argument("output", type=Path)
    init.add_argument("--plan", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "validate-plan":
            report = validate_plan(_load(args.path))
        else:
            plan = build_plan() if args.plan is None else _load(args.plan)
            if args.command == "init-result":
                _write_new(args.output, build_result_template(plan))
                print(f"wrote null-preserving result template to {args.output}")
                return 0
            report = validate_result(_load(args.path), plan)
    except ValueProofError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
