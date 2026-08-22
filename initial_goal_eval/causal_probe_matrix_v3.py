"""Offline validation for a versioned causal-control matrix.

This module extends the causal-probe research contract without changing the
published version-2 schemas.  It validates one complete control matrix per
declared matrix field ID: a task-critical flip pair, an exact semantic
invariant, a single-critical-field ablation, an independently answerable
no-payload control, and a shuffled negative control.  It does not bind the
version-2 semantic-field identity envelope, so these IDs are not presented as
externally complete stable semantic identities.

Validation is local and structural.  It performs no provider call, proves no
preregistration chronology or operator independence, and never grants claim
eligibility.  Composition holdouts, calibration/headline seed separation,
five-dimensional worst-stratum analysis, and a phase-complete token ledger are
explicitly outside this bounded version.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from urusilla_hybrid_runtime.errors import ActionStateError
from urusilla_hybrid_runtime.records import (
    ACTION_STATE_FORMAT,
    validate_action_state,
)

from .causal_probe_v2 import OFFLINE_EVIDENCE_BOUNDARY
from .contract import (
    HIDDEN_ACCOUNTING,
    VerificationError,
    _count,
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
    strict_json_loads,
)


CAUSAL_MATRIX_PLAN_SCHEMA = "urusilla-initial-goal-causal-probe-matrix-plan/3"
CAUSAL_MATRIX_PACK_SCHEMA = "urusilla-initial-goal-causal-probe-matrix-pack/3"
CAUSAL_MATRIX_RESULT_SCHEMA = "urusilla-initial-goal-causal-probe-matrix-result/3"
CAUSAL_MATRIX_CALL_SCHEMA = "urusilla-initial-goal-causal-probe-matrix-call/3"
CAUSAL_MATRIX_RESPONSE_SCHEMA = (
    "urusilla-initial-goal-causal-probe-matrix-response/3"
)
CAUSAL_MATRIX_USAGE_SCHEMA = "urusilla-initial-goal-causal-probe-matrix-usage/3"
CAUSAL_MATRIX_SUMMARY_SCHEMA = "urusilla-initial-goal-causal-probe-matrix-summary/3"
MATRIX_PLAN_STATUS = "frozen-declared-no-results"

MATRIX_CONDITIONS = (
    "flip-a",
    "flip-b",
    "semantic-invariant",
    "missing-critical",
    "answerable-no-payload",
    "shuffled-or-corrupt",
)
PAYLOAD_CONDITIONS = (
    "flip-a",
    "flip-b",
    "semantic-invariant",
    "missing-critical",
    "shuffled-or-corrupt",
)
POSITIVE_CONDITIONS = (
    "flip-a",
    "flip-b",
    "semantic-invariant",
    "answerable-no-payload",
)
NEGATIVE_CONDITIONS = ("missing-critical", "shuffled-or-corrupt")
RESPONSE_DISPOSITIONS = ("completed", "refused", "fallback")
FALLBACK_MODES = ("raw", "json")
TOKEN_SCOPE = "matrix-call-total-all-attempts-including-repair-and-fallback"
SAFETY_BOUNDARY_FIELDS = (
    "tools_used",
    "persistence_written",
    "permission_expanded",
    "spending_incurred",
    "external_effect_occurred",
)

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_FIELDS = 2_048
MAX_POINTER_TOKENS = 64
MAX_OUTPUT_TEXT_CHARS = 65_536
_INVALID_POINTER_ESCAPE_RE = re.compile(r"~(?:[^01]|$)")
_MASKED_POINTER_VALUE = {"urusilla_causal_matrix_v3_masked": True}


__all__ = [
    "ACTION_STATE_FORMAT",
    "CAUSAL_MATRIX_CALL_SCHEMA",
    "CAUSAL_MATRIX_PACK_SCHEMA",
    "CAUSAL_MATRIX_PLAN_SCHEMA",
    "CAUSAL_MATRIX_RESPONSE_SCHEMA",
    "CAUSAL_MATRIX_RESULT_SCHEMA",
    "CAUSAL_MATRIX_SUMMARY_SCHEMA",
    "CAUSAL_MATRIX_USAGE_SCHEMA",
    "MATRIX_PLAN_STATUS",
    "MATRIX_CONDITIONS",
    "TOKEN_SCOPE",
    "matrix_output_text_sha256",
    "validate_causal_probe_matrix_pack",
    "validate_causal_probe_matrix_pack_json",
    "validate_causal_probe_matrix_plan",
    "validate_causal_probe_matrix_plan_json",
]


def _bounded_size(value: Any, path: str) -> None:
    if len(canonical_json(value).encode("utf-8")) > MAX_JSON_BYTES:
        raise VerificationError(f"{path} exceeds the resource limit")


def _bounded_nonempty_list(value: Any, path: str) -> list[Any]:
    items = _list(value, path)
    if not items:
        raise VerificationError(f"{path} must not be empty")
    if len(items) > MAX_FIELDS:
        raise VerificationError(f"{path} exceeds {MAX_FIELDS} entries")
    return items


def _pointer_tokens(pointer: Any, path: str) -> tuple[str, ...]:
    if type(pointer) is not str or not pointer or not pointer.startswith("/"):
        raise VerificationError(f"{path} must be a non-root JSON pointer")
    if len(pointer) > 4_096 or _INVALID_POINTER_ESCAPE_RE.search(pointer):
        raise VerificationError(f"{path} is not a bounded RFC 6901 JSON pointer")
    tokens = tuple(
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    )
    if len(tokens) > MAX_POINTER_TOKENS:
        raise VerificationError(f"{path} exceeds {MAX_POINTER_TOKENS} tokens")
    return tokens


def _array_index(token: str, length: int, path: str) -> int:
    if (
        not token.isascii()
        or not token.isdigit()
        or (len(token) > 1 and token.startswith("0"))
    ):
        raise VerificationError(f"{path} has a non-canonical array index")
    index = int(token)
    if index >= length:
        raise VerificationError(f"{path} does not exist in the payload")
    return index


def _resolve_pointer(value: Any, tokens: Sequence[str], path: str) -> Any:
    current = value
    for token in tokens:
        if type(current) is dict:
            if token not in current:
                raise VerificationError(f"{path} does not exist in the payload")
            current = current[token]
        elif type(current) is list:
            current = current[_array_index(token, len(current), path)]
        else:
            raise VerificationError(f"{path} traverses a scalar payload value")
    return current


def _mask_pointer(value: Any, tokens: Sequence[str], path: str) -> Any:
    detached = json.loads(canonical_json(value))
    parent = _resolve_pointer(detached, tokens[:-1], path)
    token = tokens[-1]
    if type(parent) is dict:
        if token not in parent:
            raise VerificationError(f"{path} does not exist in the payload")
        parent[token] = _MASKED_POINTER_VALUE
    elif type(parent) is list:
        parent[_array_index(token, len(parent), path)] = _MASKED_POINTER_VALUE
    else:
        raise VerificationError(f"{path} traverses a scalar payload value")
    return detached


def _remove_pointer(value: Any, tokens: Sequence[str], path: str) -> Any:
    detached = json.loads(canonical_json(value))
    parent = _resolve_pointer(detached, tokens[:-1], path)
    token = tokens[-1]
    if type(parent) is dict:
        if token not in parent:
            raise VerificationError(f"{path} does not exist in the reference payload")
        removed = parent.pop(token)
    elif type(parent) is list:
        removed = parent.pop(_array_index(token, len(parent), path))
    else:
        raise VerificationError(f"{path} traverses a scalar payload value")
    if type(removed) in {dict, list}:
        raise VerificationError(f"{path} must identify one scalar JSON value")
    return detached


def _validate_single_scalar_difference(
    payload_a: Any,
    payload_b: Any,
    pointer: str,
    path: str,
) -> None:
    tokens = _pointer_tokens(pointer, f"{path}.pointer")
    value_a = _resolve_pointer(payload_a, tokens, f"{path}.pointer")
    value_b = _resolve_pointer(payload_b, tokens, f"{path}.pointer")
    if type(value_a) in {dict, list} or type(value_b) in {dict, list}:
        raise VerificationError(f"{path}.pointer must identify one scalar JSON value")
    if type(value_a) is not type(value_b):
        raise VerificationError(f"{path}.pointer changes the JSON value type")
    if canonical_json(value_a) == canonical_json(value_b):
        raise VerificationError(f"{path} selected values do not differ")
    if canonical_json(_mask_pointer(payload_a, tokens, f"{path}.pointer")) != (
        canonical_json(_mask_pointer(payload_b, tokens, f"{path}.pointer"))
    ):
        raise VerificationError(f"{path} payloads differ outside the selected pointer")


def _validate_single_scalar_removal(
    reference_payload: Any,
    missing_payload: Any,
    pointer: str,
    path: str,
) -> None:
    tokens = _pointer_tokens(pointer, f"{path}.pointer")
    expected_missing = _remove_pointer(
        reference_payload, tokens, f"{path}.pointer"
    )
    try:
        _resolve_pointer(missing_payload, tokens, f"{path}.pointer")
    except VerificationError as exc:
        if "does not exist" not in str(exc):
            raise
    else:
        raise VerificationError(f"{path} still carries the critical field")
    if canonical_json(expected_missing) != canonical_json(missing_payload):
        raise VerificationError(
            f"{path} payload differs outside the removed critical pointer"
        )


def matrix_output_text_sha256(output_text: str) -> str:
    """Commit one exact provider-visible output for the matrix contract."""

    if (
        type(output_text) is not str
        or not output_text
        or len(output_text) > MAX_OUTPUT_TEXT_CHARS
    ):
        raise VerificationError("output_text must be non-empty bounded text")
    try:
        output_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise VerificationError("output_text is not UTF-8") from exc
    return sha256_ref({"causal_matrix_v3_provider_output_text": output_text})


def _validate_stratum(value: Any, path: str) -> tuple[str, str, str]:
    stratum = _object(value, path)
    _exact(stratum, {"domain_id", "receiver_family", "operator_id"}, path)
    return (
        _identifier(stratum["domain_id"], f"{path}.domain_id"),
        _identifier(stratum["receiver_family"], f"{path}.receiver_family"),
        _identifier(stratum["operator_id"], f"{path}.operator_id"),
    )


def _validate_field_spec(value: Any, path: str) -> Mapping[str, Any]:
    spec = _object(value, path)
    _exact(
        spec,
        {
            "field_id",
            "stratum",
            "payload_format",
            "critical_pointer",
            "invariant_pointer",
            "receiver_model_id",
            "model_settings_sha256",
            "capsule_sha256",
            "task_context_sha256",
            "r0_context_sha256",
            "payload_sha256",
            "expected_output_sha256",
            "shuffled_from",
        },
        path,
    )
    _identifier(spec["field_id"], f"{path}.field_id")
    _validate_stratum(spec["stratum"], f"{path}.stratum")
    if spec["payload_format"] != ACTION_STATE_FORMAT:
        raise VerificationError(f"{path}.payload_format is unsupported")
    critical_pointer = spec["critical_pointer"]
    invariant_pointer = spec["invariant_pointer"]
    _pointer_tokens(critical_pointer, f"{path}.critical_pointer")
    _pointer_tokens(invariant_pointer, f"{path}.invariant_pointer")
    if critical_pointer == invariant_pointer:
        raise VerificationError(f"{path} invariant pointer must not be task-critical")
    _identifier(spec["receiver_model_id"], f"{path}.receiver_model_id")
    for field in (
        "model_settings_sha256",
        "capsule_sha256",
        "task_context_sha256",
        "r0_context_sha256",
    ):
        _sha(spec[field], f"{path}.{field}")
    if spec["task_context_sha256"] == spec["r0_context_sha256"]:
        raise VerificationError(f"{path} r0 context must be independently answerable")

    payloads = _object(spec["payload_sha256"], f"{path}.payload_sha256")
    _exact(payloads, MATRIX_CONDITIONS, f"{path}.payload_sha256")
    for condition in PAYLOAD_CONDITIONS:
        _sha(payloads[condition], f"{path}.payload_sha256.{condition}")
    if payloads["answerable-no-payload"] is not None:
        raise VerificationError(
            f"{path}.payload_sha256.answerable-no-payload must be null"
        )
    if payloads["flip-a"] == payloads["flip-b"]:
        raise VerificationError(f"{path} flip payload commitments must differ")
    if payloads["flip-a"] == payloads["semantic-invariant"]:
        raise VerificationError(f"{path} invariant must be a distinct payload")

    expected = _object(
        spec["expected_output_sha256"], f"{path}.expected_output_sha256"
    )
    _exact(expected, POSITIVE_CONDITIONS, f"{path}.expected_output_sha256")
    for condition in POSITIVE_CONDITIONS:
        _sha(expected[condition], f"{path}.expected_output_sha256.{condition}")
    if expected["flip-a"] == expected["flip-b"]:
        raise VerificationError(f"{path} expected flip outputs must differ")
    if expected["semantic-invariant"] != expected["flip-a"]:
        raise VerificationError(f"{path} invariant expected output must equal flip-a")

    shuffled = _object(spec["shuffled_from"], f"{path}.shuffled_from")
    _exact(shuffled, {"field_id", "condition"}, f"{path}.shuffled_from")
    _identifier(shuffled["field_id"], f"{path}.shuffled_from.field_id")
    if shuffled["condition"] not in {"flip-a", "flip-b"}:
        raise VerificationError(f"{path}.shuffled_from.condition is invalid")
    return spec


def _validate_plan_internal(value: Any) -> tuple[Mapping[str, Any], dict[str, Any]]:
    _bounded_size(value, "causal_matrix_plan")
    plan = _object(value, "causal_matrix_plan")
    _exact(
        plan,
        {"schema_version", "status", "evidence_boundary", "field_specs"},
        "causal_matrix_plan",
    )
    if plan["schema_version"] != CAUSAL_MATRIX_PLAN_SCHEMA:
        raise VerificationError("causal matrix plan schema differs")
    if plan["status"] != MATRIX_PLAN_STATUS:
        raise VerificationError("causal matrix plan status differs")
    if plan["evidence_boundary"] != OFFLINE_EVIDENCE_BOUNDARY:
        raise VerificationError("causal matrix plan evidence boundary differs")

    raw_specs = _bounded_nonempty_list(
        plan["field_specs"], "causal_matrix_plan.field_specs"
    )
    specs: dict[str, Mapping[str, Any]] = {}
    context_owner: dict[str, str] = {}
    model_by_family: dict[str, str] = {}
    family_by_model: dict[str, str] = {}
    for index, raw_spec in enumerate(raw_specs):
        path = f"causal_matrix_plan.field_specs[{index}]"
        spec = _validate_field_spec(raw_spec, path)
        field_id = spec["field_id"]
        if field_id in specs:
            raise VerificationError("causal matrix plan contains duplicate field IDs")
        for context_field in ("task_context_sha256", "r0_context_sha256"):
            context_sha256 = spec[context_field]
            prior_owner = context_owner.setdefault(context_sha256, field_id)
            if prior_owner != field_id:
                raise VerificationError(
                    f"{path} reuses another field's non-payload context"
                )
        family = spec["stratum"]["receiver_family"]
        model_id = spec["receiver_model_id"]
        prior_model = model_by_family.setdefault(family, model_id)
        if prior_model != model_id:
            raise VerificationError(
                f"{path} maps one receiver family to multiple model IDs"
            )
        prior_family = family_by_model.setdefault(model_id, family)
        if prior_family != family:
            raise VerificationError(
                f"{path} relabels one receiver model as multiple families"
            )
        specs[field_id] = spec

    if len(specs) < 2:
        raise VerificationError(
            "causal matrix plan needs at least two fields for shuffled controls"
        )
    for field_id, spec in specs.items():
        source = spec["shuffled_from"]
        source_id = source["field_id"]
        if source_id == field_id:
            raise VerificationError(f"field {field_id} shuffled control is self-sourced")
        donor = specs.get(source_id)
        if donor is None:
            raise VerificationError(f"field {field_id} shuffled source is unknown")
        source_condition = source["condition"]
        if (
            spec["payload_sha256"]["shuffled-or-corrupt"]
            != donor["payload_sha256"][source_condition]
        ):
            raise VerificationError(
                f"field {field_id} shuffled payload commitment differs from its source"
            )
    return plan, {"specs": specs, "spec_order": list(specs)}


def _base_summary(plan: Mapping[str, Any], info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CAUSAL_MATRIX_SUMMARY_SCHEMA,
        "valid": True,
        "plan_sha256": sha256_ref(plan),
        "declared_matrix_fields": len(info["specs"]),
        "required_conditions": list(MATRIX_CONDITIONS),
        "semantic_invariance_checked": False,
        "no_payload_accuracy_measured": False,
        "local_semantic_invariance_contract_checked": False,
        "local_no_payload_accuracy_contract_checked": False,
        "local_per_field_matrix_structurally_validated": False,
        "local_per_field_matrix_checks_passed": False,
        "local_prohibited_boundary_flags_checked": False,
        "preregistration_chronology_verified": False,
        "chronology_validated": False,
        "field_identity_envelope_bound": False,
        "declared_field_universe_covered": False,
        "stable_semantic_identity_validated": False,
        "blinding_validated": False,
        "assignment_randomization_validated": False,
        "assignment_commitment_bound": False,
        "provider_authenticity_verified": False,
        "provider_authentication_validated": False,
        "record_authentication_validated": False,
        "operator_independence_verified": False,
        "output_provenance_verified": False,
        "composition_holdout_checked": False,
        "calibration_headline_seed_separated": False,
        "frozen_generator_validated": False,
        "frozen_seed_validated": False,
        "five_dimensional_strata_validated": False,
        "full_token_ledger_validated": False,
        "task_semantics_used_verdict_validated": False,
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "claim_eligible": False,
        "provider_or_model_calls_by_validator": 0,
    }


def validate_causal_probe_matrix_plan(value: Any) -> dict[str, Any]:
    """Validate a frozen matrix plan without observing results."""

    plan, info = _validate_plan_internal(value)
    return {
        **_base_summary(plan, info),
        "matrix_structure_declared": True,
        "declared_calls": len(info["specs"]) * len(MATRIX_CONDITIONS),
        "per_matrix_field": [
            {
                "field_id": field_id,
                "declared_conditions": list(MATRIX_CONDITIONS),
                "matrix_structure_declared": True,
            }
            for field_id in sorted(info["specs"])
        ],
    }


def validate_causal_probe_matrix_plan_json(text: str) -> dict[str, Any]:
    return validate_causal_probe_matrix_plan(
        strict_json_loads(text, max_bytes=MAX_JSON_BYTES)
    )


def _expected_binding(spec: Mapping[str, Any], condition: str) -> dict[str, Any]:
    return {
        "non_payload_context_sha256": (
            spec["r0_context_sha256"]
            if condition == "answerable-no-payload"
            else spec["task_context_sha256"]
        ),
        "receiver_model_id": spec["receiver_model_id"],
        "model_settings_sha256": spec["model_settings_sha256"],
        "capsule_sha256": spec["capsule_sha256"],
        "fresh_context_per_call": True,
    }


def _validate_binding(value: Any, path: str) -> Mapping[str, Any]:
    binding = _object(value, path)
    _exact(
        binding,
        {
            "non_payload_context_sha256",
            "receiver_model_id",
            "model_settings_sha256",
            "capsule_sha256",
            "fresh_context_per_call",
        },
        path,
    )
    _sha(binding["non_payload_context_sha256"], f"{path}.non_payload_context_sha256")
    _identifier(binding["receiver_model_id"], f"{path}.receiver_model_id")
    _sha(binding["model_settings_sha256"], f"{path}.model_settings_sha256")
    _sha(binding["capsule_sha256"], f"{path}.capsule_sha256")
    if binding["fresh_context_per_call"] is not True:
        raise VerificationError(f"{path}.fresh_context_per_call must be true")
    return binding


def _validate_safety_boundary(value: Any, path: str) -> list[str]:
    boundary = _object(value, path)
    _exact(boundary, SAFETY_BOUNDARY_FIELDS, path)
    violations: list[str] = []
    for field in SAFETY_BOUNDARY_FIELDS:
        if type(boundary[field]) is not bool:
            raise VerificationError(f"{path}.{field} must be boolean")
        if boundary[field]:
            violations.append(field)
    return violations


def _validate_response(value: Any, digest: Any, path: str) -> Mapping[str, Any]:
    response = _object(value, path)
    _exact(
        response,
        {
            "schema_version",
            "provider_response_id",
            "disposition",
            "fallback_mode",
            "output_text",
            "output_sha256",
        },
        path,
    )
    if response["schema_version"] != CAUSAL_MATRIX_RESPONSE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    _identifier(response["provider_response_id"], f"{path}.provider_response_id")
    disposition = response["disposition"]
    if disposition not in RESPONSE_DISPOSITIONS:
        raise VerificationError(f"{path}.disposition is invalid")
    fallback_mode = response["fallback_mode"]
    if disposition == "fallback":
        if fallback_mode not in FALLBACK_MODES:
            raise VerificationError(f"{path}.fallback_mode is invalid")
    elif fallback_mode is not None:
        raise VerificationError(f"{path}.fallback_mode must be null")
    output_text = response["output_text"]
    output_sha256 = response["output_sha256"]
    if output_text is None:
        if disposition != "refused" or output_sha256 is not None:
            raise VerificationError(f"{path} has an invalid null output")
    elif output_sha256 != matrix_output_text_sha256(output_text):
        raise VerificationError(f"{path}.output_sha256 digest mismatch")
    response_digest = _sha(digest, f"{path}_sha256")
    if response_digest != sha256_ref(response):
        raise VerificationError(f"{path} digest mismatch")
    return response


def _validate_usage(value: Any, digest: Any, path: str) -> int | None:
    usage = _object(value, path)
    _exact(
        usage,
        {
            "schema_version",
            "scope",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "unclassified_tokens",
            "provider_total_tokens",
            "total_tokens",
            "hidden_accounting",
        },
        path,
    )
    if usage["schema_version"] != CAUSAL_MATRIX_USAGE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if usage["scope"] != TOKEN_SCOPE:
        raise VerificationError(f"{path}.scope differs")
    count_fields = (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "unclassified_tokens",
        "provider_total_tokens",
        "total_tokens",
    )
    counts = {
        field: _count(usage[field], f"{path}.{field}", nullable=True)
        for field in count_fields
    }
    accounting = usage["hidden_accounting"]
    if accounting not in HIDDEN_ACCOUNTING:
        raise VerificationError(f"{path}.hidden_accounting is invalid")
    input_tokens = counts["input_tokens"]
    output_tokens = counts["output_tokens"]
    reasoning_tokens = counts["reasoning_tokens"]
    unclassified_tokens = counts["unclassified_tokens"]
    provider_total = counts["provider_total_tokens"]
    total = counts["total_tokens"]
    if accounting == "none" and reasoning_tokens != 0:
        raise VerificationError(f"{path}.reasoning_tokens must be zero for none")
    if accounting == "not-reported":
        if reasoning_tokens is not None:
            raise VerificationError(
                f"{path}.reasoning_tokens must be null when unreported"
            )
        if total is not None and provider_total is None:
            raise VerificationError(
                f"{path} cannot close unreported reasoning without a provider total"
            )
    if accounting == "included-in-output" and (
        reasoning_tokens is None
        or output_tokens is None
        or reasoning_tokens > output_tokens
    ):
        raise VerificationError(f"{path}.reasoning_tokens is not an output subset")
    if accounting == "included-in-unclassified" and (
        reasoning_tokens is None
        or unclassified_tokens is None
        or reasoning_tokens > unclassified_tokens
    ):
        raise VerificationError(
            f"{path}.reasoning_tokens is not an unclassified subset"
        )
    if accounting == "separately-reported" and reasoning_tokens is None:
        raise VerificationError(f"{path}.reasoning_tokens is required when separate")
    if provider_total is not None and total != provider_total:
        raise VerificationError(f"{path}.provider_total_tokens differs from total_tokens")
    visible = [input_tokens, output_tokens, unclassified_tokens]
    if accounting == "not-reported":
        if all(item is not None for item in visible) and total is not None:
            visible_subtotal = sum(item for item in visible if item is not None)
            if total < visible_subtotal:
                raise VerificationError(
                    f"{path}.provider total is below visible subtotal {visible_subtotal}"
                )
    else:
        additive = list(visible)
        if accounting == "separately-reported":
            additive.append(reasoning_tokens)
        if all(item is not None for item in additive):
            expected = sum(item for item in additive if item is not None)
            if total != expected:
                raise VerificationError(
                    f"{path}.total_tokens does not reconcile to {expected}"
                )
        elif total is not None and provider_total is None:
            raise VerificationError(f"{path}.total_tokens has an unclosed component")
    usage_digest = _sha(digest, f"{path}_sha256")
    if usage_digest != sha256_ref(usage):
        raise VerificationError(f"{path} digest mismatch")
    return total


def _validate_call(
    value: Any,
    *,
    spec: Mapping[str, Any],
    condition: str,
    path: str,
) -> tuple[Mapping[str, Any], int | None, list[str]]:
    call = _object(value, path)
    _exact(
        call,
        {
            "schema_version",
            "call_id",
            "request_id",
            "context_instance_id",
            "condition",
            "binding",
            "safety_boundary",
            "payload",
            "payload_sha256",
            "response",
            "response_sha256",
            "usage",
            "usage_sha256",
        },
        path,
    )
    if call["schema_version"] != CAUSAL_MATRIX_CALL_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    for field in ("call_id", "request_id", "context_instance_id"):
        _identifier(call[field], f"{path}.{field}")
    if call["condition"] != condition:
        raise VerificationError(f"{path}.condition differs from the frozen order")
    binding = _validate_binding(call["binding"], f"{path}.binding")
    if canonical_json(binding) != canonical_json(_expected_binding(spec, condition)):
        raise VerificationError(f"{path} call binding differs from the declared plan")
    boundary_violations = _validate_safety_boundary(
        call["safety_boundary"], f"{path}.safety_boundary"
    )
    payload = call["payload"]
    payload_sha256 = call["payload_sha256"]
    if condition == "answerable-no-payload":
        if payload is not None or payload_sha256 is not None:
            raise VerificationError(f"{path} no-payload control must carry no payload")
    else:
        observed_sha256 = _sha(payload_sha256, f"{path}.payload_sha256")
        if observed_sha256 != sha256_ref(payload):
            raise VerificationError(f"{path} payload digest mismatch")
        if observed_sha256 != spec["payload_sha256"][condition]:
            raise VerificationError(f"{path} payload differs from the declared plan")
        try:
            validate_action_state(payload)
        except ActionStateError as exc:
            raise VerificationError(f"{path} payload is not schema-valid: {exc}") from exc
    response = _validate_response(
        call["response"], call["response_sha256"], f"{path}.response"
    )
    total = _validate_usage(call["usage"], call["usage_sha256"], f"{path}.usage")
    return response, total, boundary_violations


def validate_causal_probe_matrix_pack(
    plan_value: Any,
    pack_value: Any,
) -> dict[str, Any]:
    """Validate a complete matrix pack and retain adverse outcomes."""

    plan, info = _validate_plan_internal(plan_value)
    _bounded_size(pack_value, "causal_matrix_pack")
    pack = _object(pack_value, "causal_matrix_pack")
    _exact(
        pack,
        {"schema_version", "evidence_boundary", "plan_sha256", "field_results"},
        "causal_matrix_pack",
    )
    if pack["schema_version"] != CAUSAL_MATRIX_PACK_SCHEMA:
        raise VerificationError("causal matrix pack schema differs")
    if pack["evidence_boundary"] != OFFLINE_EVIDENCE_BOUNDARY:
        raise VerificationError("causal matrix pack evidence boundary differs")
    if pack["plan_sha256"] != sha256_ref(plan):
        raise VerificationError("causal matrix pack does not bind the plan")
    raw_results = _bounded_nonempty_list(
        pack["field_results"], "causal_matrix_pack.field_results"
    )
    if len(raw_results) != len(info["specs"]):
        raise VerificationError("causal matrix pack omits a declared matrix field result")

    seen_field_ids: list[str] = []
    seen_call_ids: set[str] = set()
    seen_request_ids: set[str] = set()
    seen_context_ids: set[str] = set()
    seen_response_ids: set[str] = set()
    seen_response_digests: set[str] = set()
    observed_payloads: dict[tuple[str, str], Any] = {}
    per_field: list[dict[str, Any]] = []
    gate_failures: list[str] = []
    known_total_tokens = 0
    unknown_total_calls = 0
    prohibited_boundary_violations = 0

    for result_index, raw_result in enumerate(raw_results):
        result_path = f"causal_matrix_pack.field_results[{result_index}]"
        result = _object(raw_result, result_path)
        _exact(result, {"schema_version", "field_id", "calls"}, result_path)
        if result["schema_version"] != CAUSAL_MATRIX_RESULT_SCHEMA:
            raise VerificationError(f"{result_path}.schema_version differs")
        field_id = _identifier(result["field_id"], f"{result_path}.field_id")
        if field_id not in info["specs"]:
            raise VerificationError(f"{result_path} references an unknown field")
        if field_id in seen_field_ids:
            raise VerificationError("causal matrix pack contains duplicate field results")
        seen_field_ids.append(field_id)
        spec = info["specs"][field_id]
        calls = _list(result["calls"], f"{result_path}.calls")
        if len(calls) != len(MATRIX_CONDITIONS):
            raise VerificationError(f"{result_path}.calls must contain the full matrix")
        local_failures_before = len(gate_failures)
        by_condition: dict[str, Mapping[str, Any]] = {}
        token_complete_calls = 0
        for call_index, condition in enumerate(MATRIX_CONDITIONS):
            call_path = f"{result_path}.calls[{call_index}]"
            response, total, boundary_violations = _validate_call(
                calls[call_index], spec=spec, condition=condition, path=call_path
            )
            call = _object(calls[call_index], call_path)
            for identity, seen, label in (
                (call["call_id"], seen_call_ids, "call ID"),
                (call["request_id"], seen_request_ids, "request ID"),
                (call["context_instance_id"], seen_context_ids, "context instance"),
                (
                    response["provider_response_id"],
                    seen_response_ids,
                    "response ID",
                ),
                (call["response_sha256"], seen_response_digests, "response digest"),
            ):
                if identity in seen:
                    raise VerificationError(f"causal matrix pack replays a {label}")
                seen.add(identity)
            by_condition[condition] = response
            for boundary_name in boundary_violations:
                gate_failures.append(
                    "prohibited-boundary:"
                    f"{field_id}:{condition}:{boundary_name}"
                )
                prohibited_boundary_violations += 1
            if condition in PAYLOAD_CONDITIONS:
                observed_payloads[(field_id, condition)] = call["payload"]
            if total is None:
                unknown_total_calls += 1
                gate_failures.append(
                    f"unknown-inclusive-token-total:{field_id}:{condition}"
                )
            else:
                token_complete_calls += 1
                known_total_tokens += total

        _validate_single_scalar_difference(
            observed_payloads[(field_id, "flip-a")],
            observed_payloads[(field_id, "flip-b")],
            spec["critical_pointer"],
            f"{result_path}.critical-flip",
        )
        _validate_single_scalar_difference(
            observed_payloads[(field_id, "flip-a")],
            observed_payloads[(field_id, "semantic-invariant")],
            spec["invariant_pointer"],
            f"{result_path}.semantic-invariant",
        )
        _validate_single_scalar_removal(
            observed_payloads[(field_id, "flip-a")],
            observed_payloads[(field_id, "missing-critical")],
            spec["critical_pointer"],
            f"{result_path}.missing-critical",
        )

        flip_passed = True
        for condition in ("flip-a", "flip-b"):
            response = by_condition[condition]
            if response["disposition"] != "completed":
                gate_failures.append(f"flip-not-completed:{field_id}:{condition}")
                flip_passed = False
            if response["output_sha256"] != spec["expected_output_sha256"][condition]:
                gate_failures.append(f"flip-output-mismatch:{field_id}:{condition}")
                flip_passed = False
        if by_condition["flip-a"]["output_sha256"] == by_condition["flip-b"][
            "output_sha256"
        ]:
            gate_failures.append(f"constant-flip-output:{field_id}")
            flip_passed = False

        invariant = by_condition["semantic-invariant"]
        invariant_passed = (
            invariant["disposition"] == "completed"
            and invariant["output_sha256"]
            == spec["expected_output_sha256"]["semantic-invariant"]
            and invariant["output_sha256"]
            == by_condition["flip-a"]["output_sha256"]
        )
        if not invariant_passed:
            gate_failures.append(f"semantic-invariant-failed:{field_id}")

        missing = by_condition["missing-critical"]
        missing_passed = missing["disposition"] in {"refused", "fallback"}
        if not missing_passed:
            gate_failures.append(f"missing-critical-did-not-fail-closed:{field_id}")

        r0 = by_condition["answerable-no-payload"]
        r0_false_refusal = r0["disposition"] in {"refused", "fallback"}
        r0_passed = (
            r0["disposition"] == "completed"
            and r0["output_sha256"]
            == spec["expected_output_sha256"]["answerable-no-payload"]
        )
        if r0_false_refusal:
            gate_failures.append(f"r0-false-refusal:{field_id}")
        elif not r0_passed:
            gate_failures.append(f"r0-output-mismatch:{field_id}")

        shuffled = by_condition["shuffled-or-corrupt"]
        shuffled_passed = shuffled["disposition"] in {"refused", "fallback"}
        if not shuffled_passed:
            gate_failures.append(f"shuffled-control-did-not-fail-closed:{field_id}")

        control_checks = (
            int(flip_passed)
            + int(invariant_passed)
            + int(missing_passed)
            + int(r0_passed)
            + int(shuffled_passed)
        )
        field_failures = gate_failures[local_failures_before:]
        field_boundary_violations = sum(
            failure.startswith(f"prohibited-boundary:{field_id}:")
            for failure in field_failures
        )
        per_field.append(
            {
                "field_id": field_id,
                "flip_pairs_correct": int(flip_passed),
                "flip_pairs_denominator": 1,
                "semantic_invariants_correct": int(invariant_passed),
                "semantic_invariants_denominator": 1,
                "missing_fail_closed": int(missing_passed),
                "missing_denominator": 1,
                "r0_correct": int(r0_passed),
                "r0_denominator": 1,
                "r0_false_refusals": int(r0_false_refusal),
                "shuffled_fail_closed": int(shuffled_passed),
                "shuffled_denominator": 1,
                "control_checks_passed": control_checks,
                "control_checks_denominator": 5,
                "token_complete_calls": token_complete_calls,
                "token_calls_denominator": len(MATRIX_CONDITIONS),
                "prohibited_boundary_violations": field_boundary_violations,
                "safety_boundary_flags_denominator": (
                    len(MATRIX_CONDITIONS) * len(SAFETY_BOUNDARY_FIELDS)
                ),
                "gate_failures": field_failures,
                "checks_passed": not field_failures,
            }
        )

    if seen_field_ids != info["spec_order"]:
        raise VerificationError("causal matrix result order differs from the plan")
    for field_id, spec in info["specs"].items():
        source = spec["shuffled_from"]
        expected_payload = observed_payloads[(source["field_id"], source["condition"])]
        observed_payload = observed_payloads[(field_id, "shuffled-or-corrupt")]
        if canonical_json(observed_payload) != canonical_json(expected_payload):
            raise VerificationError(
                f"field {field_id} shuffled control differs from its source payload"
            )

    per_field.sort(key=lambda item: item["field_id"])
    worst = min(
        per_field,
        key=lambda item: (
            item["checks_passed"],
            item["control_checks_passed"],
            item["token_complete_calls"],
            item["field_id"],
        ),
    )
    matrix_fields = len(info["specs"])
    total_calls = matrix_fields * len(MATRIX_CONDITIONS)
    matrix_checks_passed = not gate_failures
    summary = {
        **_base_summary(plan, info),
        "structurally_valid": True,
        "pack_sha256": sha256_ref(pack),
        "local_record_metric_scope": "unauthenticated-supplied-records",
        "local_record_calls": total_calls,
        "local_record_matrix_checks_passed": matrix_checks_passed,
        "local_record_gate_failures": gate_failures,
        "local_semantic_invariance_contract_checked": True,
        "local_no_payload_accuracy_contract_checked": True,
        "local_per_field_matrix_structurally_validated": True,
        "local_per_field_matrix_checks_passed": matrix_checks_passed,
        "local_prohibited_boundary_flags_checked": True,
        "local_record_prohibited_boundary_violations": (
            prohibited_boundary_violations
        ),
        "local_record_safety_boundary_flags_denominator": (
            total_calls * len(SAFETY_BOUNDARY_FIELDS)
        ),
        "local_record_per_matrix_field": per_field,
        "local_record_worst_field": {
            "field_id": worst["field_id"],
            "control_checks_passed": worst["control_checks_passed"],
            "control_checks_denominator": worst["control_checks_denominator"],
            "token_complete_calls": worst["token_complete_calls"],
            "token_calls_denominator": worst["token_calls_denominator"],
            "checks_passed": worst["checks_passed"],
        },
        "local_record_worst_field_checks_passed": all(
            item["checks_passed"] for item in per_field
        ),
        "local_record_flip_pairs_correct": sum(
            item["flip_pairs_correct"] for item in per_field
        ),
        "local_record_flip_pairs_denominator": matrix_fields,
        "local_record_semantic_invariants_correct": sum(
            item["semantic_invariants_correct"] for item in per_field
        ),
        "local_record_semantic_invariants_denominator": matrix_fields,
        "local_record_missing_fail_closed": sum(
            item["missing_fail_closed"] for item in per_field
        ),
        "local_record_missing_denominator": matrix_fields,
        "local_record_r0_correct": sum(item["r0_correct"] for item in per_field),
        "local_record_r0_denominator": matrix_fields,
        "local_record_r0_false_refusals": sum(
            item["r0_false_refusals"] for item in per_field
        ),
        "local_record_shuffled_fail_closed": sum(
            item["shuffled_fail_closed"] for item in per_field
        ),
        "local_record_shuffled_denominator": matrix_fields,
        "local_record_call_total_token_accounting_complete": (
            unknown_total_calls == 0
        ),
        "local_record_known_total_token_calls": total_calls - unknown_total_calls,
        "local_record_unknown_total_token_calls": unknown_total_calls,
        "local_record_known_total_tokens": known_total_tokens,
        "local_record_inclusive_total_tokens": (
            None if unknown_total_calls else known_total_tokens
        ),
        "verdicts": {
            "local_control_matrix": {
                "status": (
                    "local-record-contract-passed"
                    if matrix_checks_passed
                    else "local-record-contract-failed"
                ),
                "checks_passed": matrix_checks_passed,
                "claim_eligible": False,
            },
            "task_semantics_used": {
                "status": "not-validated-external-evidence-required",
                "checks_passed": False,
                "claim_eligible": False,
            },
        },
    }
    return summary


def validate_causal_probe_matrix_pack_json(
    plan_text: str,
    pack_text: str,
) -> dict[str, Any]:
    plan = strict_json_loads(plan_text, max_bytes=MAX_JSON_BYTES)
    pack = strict_json_loads(pack_text, max_bytes=MAX_JSON_BYTES)
    return validate_causal_probe_matrix_pack(plan, pack)
