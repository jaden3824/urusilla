"""Canonical, claim-ineligible trace for the provider-neutral hybrid runtime.

This artifact records the chronology that already exists between five-route
preselection, direct receiver execution, the native observed ledger, and the
caller-injected scorer.  It is deliberately a separate schema: it is not a
``Trace/2``, ``Result/1``, or ``Receipt/3`` and cannot authenticate a plan,
provider, scorer implementation, or usage report.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from urusilla_hybrid_runtime.canonical import sha256_text

from .contract import FEATURE_TAGS, VerificationError, canonical_json, sha256_ref
from .study_orchestrator import (
    ORCHESTRATION_BOUNDARY,
    SCORING_INPUT_SCHEMA,
    SCORING_OUTPUT_SCHEMA,
    SCORER_OBSERVATION_SCHEMA,
    ScoredHybridTask,
)
from .terminal_contract import (
    CANONICAL_SILENCE_OUTPUT_SHA256,
    SILENCE_TERMINAL_STATUS,
)


RUNTIME_DIAGNOSTIC_TRACE_SCHEMA = (
    "urusilla-initial-goal-runtime-diagnostic-trace/1"
)
RUNTIME_DIAGNOSTIC_TRACE_BOUNDARY = (
    "provider-neutral-runtime-diagnostic-not-study-evidence"
)
ROUTE_MODES = ("silence", "routine", "action-state", "raw", "json")

_SCORER_LOCK_FIELDS = {
    "task_scorer",
    "parse_scorer",
    "semantic_scorer",
    "negative_scorer",
}
_SAFETY_FIELDS = {
    "unauthorized_external_effects",
    "persistence_events",
    "permission_expansions",
    "spending_authority_events",
    "unknown_schema_executions",
}
_SCORING_INPUT_FIELDS = {
    "schema_version",
    "task_id",
    "task_sha256",
    "source_sha256",
    "feature_tags",
    "parse_probe",
    "semantic_probe",
    "negative_probe",
    "arm_id",
    "selected_mode",
    "final_mode",
    "fallback_from",
    "terminal_status",
    "output_text",
    "output_sha256",
    "terminal_observation_sha256",
    "execution_binding_sha256",
    "route_binding_sha256",
    "primary_request_binding_sha256",
    "fallback_request_binding_sha256",
    "observed_ledger_sha256",
}
_SCORING_OUTPUT_FIELDS = {
    "schema_version",
    "task_success",
    "parse_valid",
    "semantic_exact",
    "negative_rejected",
    "preservation",
    "safety",
    "scorer_kind",
    "total_tokens",
    "usage_complete",
    "failure",
}
_EVENT_FIELDS = {
    "sequence",
    "phase",
    "component",
    "execution_binding_sha256",
    "artifact_binding_sha256",
    "total_tokens",
    "model_calls",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "reasoning_accounting",
}
_EVENT_COMPONENT_PHASE = {
    "local-setup": "setup",
    "cold-comprehension": "setup",
    "sender-compiler": "sender",
    "semantic-fidelity-verifier": "semantic-verification",
    "local-router": "router",
    "primary-receiver": "receiver",
    "local-repair": "repair",
    "local-fallback": "fallback",
    "baseline-fallback-receiver": "fallback",
    "local-tool": "tool",
    "local-safety": "safety",
    "local-judge": "judge",
}
_EVENT_PHASES = {
    "setup",
    "sender",
    "semantic-verification",
    "router",
    "receiver",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
}
RUNTIME_LEDGER_COMPONENT_ORDER = (
    "local-setup",
    "sender-compiler",
    "semantic-fidelity-verifier",
    "local-router",
    "primary-receiver",
    "local-repair",
    "local-fallback",
    "baseline-fallback-receiver",
    "local-tool",
    "local-safety",
    "local-judge",
)
COLD_RUNTIME_LEDGER_COMPONENT_ORDER = (
    "cold-comprehension",
    *RUNTIME_LEDGER_COMPONENT_ORDER,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_COST_FIELDS = (
    "task_system_tokens",
    "task_context_setup_tokens",
    "capsule_setup_tokens",
    "cached_context_tokens",
    "comprehension_setup_tokens",
    "routine_setup_tokens",
    "sender_tokens",
    "semantic_verification_tokens",
    "router_tokens",
    "provider_framing_tokens",
    "receiver_input_tokens",
    "receiver_output_tokens",
    "reasoning_tokens",
    "repair_tokens",
    "fallback_tokens",
    "tool_tokens",
    "safety_tokens",
    "judge_tokens",
    "complete",
)
_REQUEST_FIELDS = {
    "mode",
    "binding_sha256",
    "task_context_sha256",
    "task_profile_sha256",
    "symbol_table_sha256",
    "task_context_included",
    "task_context_id",
    "task_comprehension_evidence_sha256",
    "task_comprehension_verifier_sha256",
    "capsule_sha256",
    "capsule_included",
    "capsule_context_id",
    "comprehension_evidence_sha256",
    "capsule_comprehension_verifier_sha256",
    "payload_sha256",
    "model_visible_sha256",
    "model_call_required",
    "maximum_total_tokens",
    "delivery_disposition",
    "natural_language_expansion",
    "decode_before_model",
    "tools",
    "memory",
    "external_effects_authorized",
}
_AUTHORITY_FIELDS = {
    "frozen_plan_sha256",
    "frozen_plan_bound",
    "plan_v2_resolved",
    "authentication_envelope_sha256",
    "authentication_verified",
    "provider_authenticity_verified",
    "provider_normalization_verified",
    "provider_receipts_complete",
    "scorer_implementation_sha256",
    "scorer_implementation_authenticated",
    "scorer_usage_authenticated",
    "claim_eligible",
    "goal_total_complete",
}


def _detached(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise VerificationError(f"{path} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], path: str) -> None:
    if set(value) != fields:
        raise VerificationError(f"{path} fields differ")


def _sha(value: Any, path: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise VerificationError(f"{path} must be a sha256 reference")
    return value


def _bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise VerificationError(f"{path} must be boolean")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise VerificationError(f"{path} must be a nonnegative integer")
    return value


def _nullable_nonnegative_int(value: Any, path: str) -> int | None:
    if value is not None:
        _nonnegative_int(value, path)
    return value


def _nullable_bool(value: Any, path: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise VerificationError(f"{path} must be boolean or null")
    return value


def _cost_value(cost: Any) -> dict[str, Any] | None:
    if cost is None:
        return None
    value = {name: getattr(cost, name) for name in _COST_FIELDS}
    value["total_tokens"] = cost.total_tokens
    return value


def _request_value(request: Any) -> dict[str, Any] | None:
    if request is None:
        return None
    return {
        "mode": request.mode,
        "binding_sha256": request.binding_sha256,
        "task_context_sha256": request.task_context_sha256,
        "task_profile_sha256": request.task_profile_sha256,
        "symbol_table_sha256": request.symbol_table_sha256,
        "task_context_included": request.task_context_included,
        "task_context_id": request.task_context_id,
        "task_comprehension_evidence_sha256": (
            request.task_comprehension_evidence_sha256
        ),
        "task_comprehension_verifier_sha256": (
            request.task_comprehension_verifier_sha256
        ),
        "capsule_sha256": request.capsule_sha256,
        "capsule_included": request.capsule_included,
        "capsule_context_id": request.capsule_context_id,
        "comprehension_evidence_sha256": (
            request.comprehension_evidence_sha256
        ),
        "capsule_comprehension_verifier_sha256": (
            request.capsule_comprehension_verifier_sha256
        ),
        "payload_sha256": request.payload_sha256,
        "model_visible_sha256": sha256_text(request.model_visible_text),
        "model_call_required": request.model_call_required,
        "maximum_total_tokens": request.maximum_total_tokens,
        "delivery_disposition": request.delivery_disposition,
        "natural_language_expansion": request.natural_language_expansion,
        "decode_before_model": request.decode_before_model,
        "tools": list(request.tools),
        "memory": request.memory,
        "external_effects_authorized": request.external_effects_authorized,
    }


def _candidate_value(candidate: Any) -> dict[str, Any]:
    return {
        "mode": candidate.mode,
        "request": _request_value(candidate.request),
        "cost": _cost_value(candidate.cost),
        "eligible": candidate.eligible,
        "claim_eligible": False,
        "reasons": list(candidate.reasons),
    }


def _reply_value(reply: Any) -> dict[str, Any] | None:
    if reply is None:
        return None
    return {
        "text": reply.text,
        "output_sha256": sha256_ref({"provider_output_text": reply.text}),
        "model_id": reply.model_id,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "reasoning_tokens": reply.reasoning_tokens,
        "reasoning_accounting": reply.reasoning_accounting,
        "provider_total_tokens": reply.provider_total_tokens,
        "tools_used": reply.tools_used,
        "persistence_created": reply.persistence_created,
        "permission_expanded": reply.permission_expanded,
        "spending_authority_created": reply.spending_authority_created,
        "external_effects_performed": reply.external_effects_performed,
    }


def _execution_value(execution: Any) -> dict[str, Any]:
    return {
        "status": execution.status,
        "calls": execution.calls,
        "request_mode": execution.request_mode,
        "request_binding_sha256": execution.request_binding_sha256,
        "delivery_disposition": execution.delivery_disposition,
        "model_visible_sha256": execution.model_visible_sha256,
        "reply": _reply_value(execution.reply),
        "failure": execution.failure,
        "usage_complete": execution.usage_complete,
        "total_tokens": execution.total_tokens,
    }


def _ledger_value(ledger: Any) -> dict[str, Any] | None:
    if ledger is None:
        return None
    return {
        "execution_binding_sha256": ledger.execution_binding_sha256,
        "events": [
            {
                "sequence": event.sequence,
                "phase": event.phase,
                "component": event.component,
                "execution_binding_sha256": event.execution_binding_sha256,
                "artifact_binding_sha256": event.artifact_binding_sha256,
                "total_tokens": event.total_tokens,
                "model_calls": event.model_calls,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "reasoning_tokens": event.reasoning_tokens,
                "reasoning_accounting": event.reasoning_accounting,
            }
            for event in ledger.events
        ],
        "scope_complete": ledger.scope_complete,
        "inclusive_total_tokens": ledger.inclusive_total_tokens,
        "provider_authenticity_verified": False,
        "claim_eligible": False,
        "goal_total_complete": False,
    }


def build_runtime_diagnostic_trace(
    scored_task: ScoredHybridTask,
) -> "RuntimeDiagnosticTrace":
    """Project one sealed runtime/scorer observation into a diagnostic trace."""

    if type(scored_task) is not ScoredHybridTask:
        raise VerificationError(
            "runtime diagnostic trace requires an exact ScoredHybridTask"
        )
    execution = scored_task.execution
    route = execution.prepared.route
    scoring_input = _detached(scored_task.scoring_input.value)
    score = _detached(scored_task.score.value)
    ledger = _ledger_value(execution.observed_ledger)
    ledger_record = (
        None
        if ledger is None
        else {"sha256": sha256_ref(ledger), "value": ledger}
    )
    body = {
        "schema_version": RUNTIME_DIAGNOSTIC_TRACE_SCHEMA,
        "evidence_boundary": RUNTIME_DIAGNOSTIC_TRACE_BOUNDARY,
        "source_orchestration_boundary": scored_task.evidence_boundary,
        "task": {
            "task_id": scoring_input["task_id"],
            "task_sha256": scoring_input["task_sha256"],
            "source_sha256": scoring_input["source_sha256"],
            "terminal_status": scoring_input["terminal_status"],
            "output_text": scoring_input["output_text"],
            "output_sha256": scoring_input["output_sha256"],
            "terminal_observation_sha256": scoring_input[
                "terminal_observation_sha256"
            ],
        },
        "route": {
            "execution_binding_sha256": execution.prepared.execution_binding_sha256,
            "route_binding_sha256": route.binding_sha256,
            "source_sha256": route.source_sha256,
            "capsule_sha256": route.capsule_sha256,
            "selected_mode": route.selected_mode,
            "final_mode": execution.final_mode,
            "preselection_fallback_from": route.fallback_from,
            "fallback_sender_tokens": route.fallback_sender_tokens,
            "fallback_semantic_verification_tokens": (
                route.fallback_semantic_verification_tokens
            ),
            "fallback_from": scoring_input["fallback_from"],
            "selected_request_binding_sha256": route.request.binding_sha256,
            "primary_request_binding_sha256": (
                execution.primary.request_binding_sha256
            ),
            "fallback_request_binding_sha256": (
                None
                if execution.fallback is None
                else execution.fallback.request_binding_sha256
            ),
            "best_baseline_mode": route.best_baseline_mode,
            "best_baseline_tokens": route.best_baseline_tokens,
            "selected_cost": _cost_value(route.selected_cost),
            "candidates": [
                _candidate_value(candidate) for candidate in route.candidates
            ],
        },
        "primary_execution": _execution_value(execution.primary),
        "fallback_execution": (
            None
            if execution.fallback is None
            else _execution_value(execution.fallback)
        ),
        "observed_ledger": ledger_record,
        "scorer_observation": {
            "scoring_input": scoring_input,
            "scoring_input_sha256": scored_task.scoring_input.sha256,
            "scorer_locks": dict(scored_task.scorer_locks),
            "scorer_output": score,
            "scorer_observation_sha256": (
                scored_task.scorer_observation_sha256
            ),
            "scorer_calls": scored_task.scorer_calls,
        },
        "runtime_summary": {
            "compiler_calls": execution.compiler_calls,
            "fidelity_verifier_calls": execution.fidelity_verifier_calls,
            "receiver_calls": execution.receiver_calls,
            "output_valid": execution.output_valid,
            "observed_runtime_tokens": execution.observed_runtime_tokens,
            "caller_reported_inclusive_total_tokens": (
                scored_task.caller_reported_inclusive_total_tokens
            ),
            "claim_inclusive_total_tokens": None,
            "caller_reported_safely_completed": (
                scored_task.caller_reported_safely_completed
            ),
            "claim_safely_completed": None,
        },
        "authority": {
            "frozen_plan_sha256": None,
            "frozen_plan_bound": False,
            "plan_v2_resolved": False,
            "authentication_envelope_sha256": None,
            "authentication_verified": False,
            "provider_authenticity_verified": False,
            "provider_normalization_verified": False,
            "provider_receipts_complete": False,
            "scorer_implementation_sha256": None,
            "scorer_implementation_authenticated": False,
            "scorer_usage_authenticated": False,
            "claim_eligible": False,
            "goal_total_complete": False,
        },
    }
    body["trace_sha256"] = sha256_ref(body)
    return RuntimeDiagnosticTrace(body)


def _validate_request(value: Any, path: str) -> dict[str, Any]:
    request = _object(value, path)
    _exact(request, _REQUEST_FIELDS, path)
    if request["mode"] not in ROUTE_MODES:
        raise VerificationError(f"{path}.mode is invalid")
    for name in (
        "binding_sha256",
        "task_context_sha256",
        "task_profile_sha256",
        "symbol_table_sha256",
        "payload_sha256",
        "model_visible_sha256",
    ):
        _sha(request[name], f"{path}.{name}")
    for name in (
        "capsule_sha256",
        "task_comprehension_evidence_sha256",
        "task_comprehension_verifier_sha256",
        "comprehension_evidence_sha256",
        "capsule_comprehension_verifier_sha256",
    ):
        if request[name] is not None:
            _sha(request[name], f"{path}.{name}")
    for name in ("task_context_id", "capsule_context_id"):
        if request[name] is not None and (
            type(request[name]) is not str or not request[name]
        ):
            raise VerificationError(f"{path}.{name} is invalid")
    for name in (
        "task_context_included",
        "capsule_included",
        "model_call_required",
        "decode_before_model",
        "external_effects_authorized",
    ):
        _bool(request[name], f"{path}.{name}")
    if (
        request["natural_language_expansion"] is not None
        or request["decode_before_model"] is not False
        or request["tools"] != []
        or request["memory"] is not None
        or request["external_effects_authorized"] is not False
    ):
        raise VerificationError(f"{path} violates the direct receiver boundary")
    if request["model_call_required"] is not (request["mode"] != "silence"):
        raise VerificationError(f"{path}.model_call_required differs")
    maximum = request["maximum_total_tokens"]
    if maximum is not None and (type(maximum) is not int or maximum <= 0):
        raise VerificationError(f"{path}.maximum_total_tokens is invalid")
    if request["delivery_disposition"] not in {"live", "shadow"}:
        raise VerificationError(f"{path}.delivery_disposition is invalid")
    return request


def _validate_cost(value: Any, path: str) -> dict[str, Any]:
    cost = _object(value, path)
    _exact(cost, set(_COST_FIELDS) | {"total_tokens"}, path)
    subtotal = 0
    for name in _COST_FIELDS:
        if name == "complete":
            _bool(cost[name], f"{path}.{name}")
        else:
            item = cost[name]
            if type(item) is not int or item < 0:
                raise VerificationError(f"{path}.{name} is invalid")
            subtotal += item
    if cost["total_tokens"] != subtotal:
        raise VerificationError(f"{path}.total_tokens differs")
    return cost


def _validate_execution(value: Any, path: str) -> dict[str, Any]:
    execution = _object(value, path)
    _exact(
        execution,
        {
            "status",
            "calls",
            "request_mode",
            "request_binding_sha256",
            "delivery_disposition",
            "model_visible_sha256",
            "reply",
            "failure",
            "usage_complete",
            "total_tokens",
        },
        path,
    )
    _sha(execution["request_binding_sha256"], f"{path}.request_binding_sha256")
    _sha(execution["model_visible_sha256"], f"{path}.model_visible_sha256")
    _bool(execution["usage_complete"], f"{path}.usage_complete")
    if execution["status"] not in {
        "silenced",
        "completed",
        "failed",
        "budget-exceeded",
    }:
        raise VerificationError(f"{path}.status is invalid")
    if type(execution["calls"]) is not int or execution["calls"] not in {0, 1}:
        raise VerificationError(f"{path}.calls is invalid")
    if execution["request_mode"] not in ROUTE_MODES:
        raise VerificationError(f"{path}.request_mode is invalid")
    if execution["delivery_disposition"] not in {"live", "shadow"}:
        raise VerificationError(f"{path}.delivery_disposition is invalid")
    if execution["failure"] is not None and (
        type(execution["failure"]) is not str or not execution["failure"]
    ):
        raise VerificationError(f"{path}.failure is invalid")
    reply = execution["reply"]
    if reply is not None:
        reply = _object(reply, f"{path}.reply")
        _exact(
            reply,
            {
                "text",
                "output_sha256",
                "model_id",
                "input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "reasoning_accounting",
                "provider_total_tokens",
                "tools_used",
                "persistence_created",
                "permission_expanded",
                "spending_authority_created",
                "external_effects_performed",
            },
            f"{path}.reply",
        )
        if reply["output_sha256"] != sha256_ref(
            {"provider_output_text": reply["text"]}
        ):
            raise VerificationError(f"{path}.reply output binding differs")
        if type(reply["text"]) is not str:
            raise VerificationError(f"{path}.reply.text is invalid")
        if type(reply["model_id"]) is not str or not reply["model_id"]:
            raise VerificationError(f"{path}.reply.model_id is invalid")
        for name in ("input_tokens", "output_tokens", "provider_total_tokens"):
            _nonnegative_int(reply[name], f"{path}.reply.{name}")
        _nullable_nonnegative_int(
            reply["reasoning_tokens"], f"{path}.reply.reasoning_tokens"
        )
        accounting = reply["reasoning_accounting"]
        if accounting not in {
            "included-in-output",
            "separately-reported",
            "not-reported",
        }:
            raise VerificationError(
                f"{path}.reply.reasoning_accounting is invalid"
            )
        reasoning = reply["reasoning_tokens"]
        input_tokens = reply["input_tokens"]
        output_tokens = reply["output_tokens"]
        provider_total = reply["provider_total_tokens"]
        if accounting == "not-reported":
            if reasoning is not None or provider_total < input_tokens + output_tokens:
                raise VerificationError(f"{path}.reply usage does not reconcile")
        elif accounting == "included-in-output":
            if (
                reasoning is None
                or reasoning > output_tokens
                or provider_total != input_tokens + output_tokens
            ):
                raise VerificationError(f"{path}.reply usage does not reconcile")
        elif (
            reasoning is None
            or provider_total != input_tokens + output_tokens + reasoning
        ):
            raise VerificationError(f"{path}.reply usage does not reconcile")
        for name in (
            "tools_used",
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            _bool(reply[name], f"{path}.reply.{name}")
    status = execution["status"]
    status_valid = {
        "silenced": (
            execution["calls"] == 0
            and execution["request_mode"] == "silence"
            and reply is None
            and execution["failure"] is None
            and execution["usage_complete"] is True
        ),
        "completed": (
            execution["calls"] == 1
            and reply is not None
            and execution["failure"] is None
            and execution["usage_complete"] is True
        ),
        "failed": (
            execution["calls"] == 1
            and reply is None
            and type(execution["failure"]) is str
            and bool(execution["failure"])
            and execution["usage_complete"] is False
        ),
        "budget-exceeded": (
            execution["calls"] == 1
            and reply is not None
            and execution["failure"] == "receiver-token-budget-exceeded"
            and execution["usage_complete"] is True
        ),
    }[status]
    if not status_valid:
        raise VerificationError(f"{path} status/call/reply state differs")
    expected_total = 0 if execution["status"] == "silenced" else (
        None if reply is None else reply["provider_total_tokens"]
    )
    if execution["total_tokens"] != expected_total:
        raise VerificationError(f"{path}.total_tokens differs")
    return execution


def _validate_scoring_input(value: Any) -> dict[str, Any]:
    path = "scorer_observation.scoring_input"
    scoring_input = _object(value, path)
    _exact(scoring_input, _SCORING_INPUT_FIELDS, path)
    if scoring_input["schema_version"] != SCORING_INPUT_SCHEMA:
        raise VerificationError("scoring input schema differs")
    if type(scoring_input["task_id"]) is not str or not scoring_input["task_id"]:
        raise VerificationError("scoring input task ID is invalid")
    for name in (
        "task_sha256",
        "source_sha256",
        "terminal_observation_sha256",
        "execution_binding_sha256",
        "route_binding_sha256",
        "primary_request_binding_sha256",
    ):
        _sha(scoring_input[name], f"{path}.{name}")
    for name in (
        "output_sha256",
        "fallback_request_binding_sha256",
        "observed_ledger_sha256",
    ):
        if scoring_input[name] is not None:
            _sha(scoring_input[name], f"{path}.{name}")
    tags = scoring_input["feature_tags"]
    if (
        type(tags) is not list
        or len(tags) != len(set(tags))
        or not set(tags).issubset(FEATURE_TAGS)
    ):
        raise VerificationError("scoring input feature tags are invalid")
    for name in ("parse_probe", "semantic_probe", "negative_probe"):
        _bool(scoring_input[name], f"{path}.{name}")
    if scoring_input["arm_id"] != "hybrid-router":
        raise VerificationError("scoring input arm differs")
    if (
        scoring_input["selected_mode"] not in ROUTE_MODES
        or scoring_input["final_mode"] not in ROUTE_MODES
    ):
        raise VerificationError("scoring input route mode is invalid")
    if scoring_input["fallback_from"] is not None and (
        type(scoring_input["fallback_from"]) is not str
        or not scoring_input["fallback_from"]
    ):
        raise VerificationError("scoring input fallback reason is invalid")
    if scoring_input["terminal_status"] == SILENCE_TERMINAL_STATUS:
        if (
            scoring_input["output_text"] is not None
            or scoring_input["output_sha256"]
            != CANONICAL_SILENCE_OUTPUT_SHA256
        ):
            raise VerificationError("silence scoring input differs")
    elif scoring_input["output_text"] is None:
        if scoring_input["output_sha256"] is not None:
            raise VerificationError("null scoring output digest differs")
    elif (
        type(scoring_input["output_text"]) is not str
        or scoring_input["output_sha256"]
        != sha256_ref({"provider_output_text": scoring_input["output_text"]})
    ):
        raise VerificationError("scoring input output binding differs")
    return scoring_input


def _validate_scoring_output(value: Any) -> dict[str, Any]:
    path = "scorer_observation.scorer_output"
    output = _object(value, path)
    _exact(output, _SCORING_OUTPUT_FIELDS, path)
    if output["schema_version"] != SCORING_OUTPUT_SCHEMA:
        raise VerificationError("scoring output schema differs")
    for name in (
        "task_success",
        "parse_valid",
        "semantic_exact",
        "negative_rejected",
    ):
        _nullable_bool(output[name], f"{path}.{name}")
    preservation = _object(output["preservation"], f"{path}.preservation")
    _exact(preservation, set(FEATURE_TAGS), f"{path}.preservation")
    for name, item in preservation.items():
        _nullable_bool(item, f"{path}.preservation.{name}")
    safety = _object(output["safety"], f"{path}.safety")
    _exact(safety, _SAFETY_FIELDS, f"{path}.safety")
    for name, item in safety.items():
        _nullable_nonnegative_int(item, f"{path}.safety.{name}")
    _nullable_nonnegative_int(output["total_tokens"], f"{path}.total_tokens")
    _bool(output["usage_complete"], f"{path}.usage_complete")
    if output["usage_complete"] is not (output["total_tokens"] is not None):
        raise VerificationError("scoring output usage completeness differs")
    if output["scorer_kind"] not in {
        "deterministic-local",
        "external-model",
        "unclassified",
    }:
        raise VerificationError("scoring output kind is invalid")
    failure = output["failure"]
    if failure is not None and (type(failure) is not str or not failure):
        raise VerificationError("scoring output failure is invalid")
    observations = (
        output["task_success"],
        output["parse_valid"],
        output["semantic_exact"],
        output["negative_rejected"],
        *preservation.values(),
        *safety.values(),
    )
    if failure is not None and any(item is not None for item in observations):
        raise VerificationError("failed scorer contains observations")
    if failure is not None and output["scorer_kind"] != "unclassified":
        raise VerificationError("failed scorer kind differs")
    if failure is None and output["scorer_kind"] == "unclassified":
        raise VerificationError("successful scorer kind differs")
    if output["scorer_kind"] == "deterministic-local" and (
        output["total_tokens"] != 0 or output["usage_complete"] is not True
    ):
        raise VerificationError("deterministic scorer usage differs")
    return output


def _validate_ledger_event(value: Any, path: str, execution_binding: str) -> dict[str, Any]:
    event = _object(value, path)
    _exact(event, _EVENT_FIELDS, path)
    _nonnegative_int(event["sequence"], f"{path}.sequence")
    if type(event["component"]) is not str or type(event["phase"]) is not str:
        raise VerificationError(f"{path} component/phase is invalid")
    if _EVENT_COMPONENT_PHASE.get(event["component"]) != event["phase"]:
        raise VerificationError(f"{path} component/phase differs")
    if event["execution_binding_sha256"] != execution_binding:
        raise VerificationError(f"{path} execution binding differs")
    _sha(event["artifact_binding_sha256"], f"{path}.artifact_binding_sha256")
    for name in (
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
    ):
        _nullable_nonnegative_int(event[name], f"{path}.{name}")
    if type(event["model_calls"]) is not int or event["model_calls"] not in {0, 1}:
        raise VerificationError(f"{path}.model_calls is invalid")
    if event["reasoning_accounting"] not in {
        None,
        "included-in-output",
        "separately-reported",
        "not-reported",
    }:
        raise VerificationError(f"{path}.reasoning_accounting is invalid")
    if event["model_calls"] == 0 and any(
        event[name] is not None
        for name in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "reasoning_accounting",
        )
    ):
        raise VerificationError(f"{path} non-model usage differs")
    if (
        event["model_calls"] == 1
        and event["component"]
        in {
            "cold-comprehension",
            "primary-receiver",
            "baseline-fallback-receiver",
        }
        and event["total_tokens"] is not None
        and (
            event["input_tokens"] is None
            or event["output_tokens"] is None
            or event["reasoning_accounting"] is None
        )
    ):
        raise VerificationError(f"{path} detailed model usage is incomplete")
    if event["component"] in {
        "sender-compiler",
        "semantic-fidelity-verifier",
    } and any(
        event[name] is not None
        for name in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "reasoning_accounting",
        )
    ):
        raise VerificationError(f"{path} total-only usage differs")
    if event["reasoning_accounting"] is None and event["reasoning_tokens"] is not None:
        raise VerificationError(f"{path} reasoning usage differs")
    if event["reasoning_accounting"] == "not-reported" and event["reasoning_tokens"] is not None:
        raise VerificationError(f"{path} unreported reasoning differs")
    if event["reasoning_accounting"] in {
        "included-in-output",
        "separately-reported",
    } and event["reasoning_tokens"] is None:
        raise VerificationError(f"{path} reported reasoning differs")
    subtotal = sum(
        item
        for item in (
            event["input_tokens"],
            event["output_tokens"],
            (
                event["reasoning_tokens"]
                if event["reasoning_accounting"] == "separately-reported"
                else None
            ),
        )
        if item is not None
    )
    if event["total_tokens"] is not None and event["total_tokens"] < subtotal:
        raise VerificationError(f"{path} token subtotal exceeds total")
    if (
        event["model_calls"] == 0
        and event["component"]
        in {
            "sender-compiler",
            "primary-receiver",
            "baseline-fallback-receiver",
            "cold-comprehension",
        }
        and event["total_tokens"] not in {0, None}
    ):
        raise VerificationError(f"{path} uncalled model reports positive usage")
    return event


def validate_runtime_diagnostic_trace(value: Any) -> dict[str, Any]:
    """Strictly validate and detach a runtime diagnostic trace."""

    trace = _object(_detached(value), "runtime_diagnostic_trace")
    _exact(
        trace,
        {
            "schema_version",
            "evidence_boundary",
            "source_orchestration_boundary",
            "task",
            "route",
            "primary_execution",
            "fallback_execution",
            "observed_ledger",
            "scorer_observation",
            "runtime_summary",
            "authority",
            "trace_sha256",
        },
        "runtime_diagnostic_trace",
    )
    if trace["schema_version"] != RUNTIME_DIAGNOSTIC_TRACE_SCHEMA:
        raise VerificationError("runtime diagnostic trace schema differs")
    if trace["evidence_boundary"] != RUNTIME_DIAGNOSTIC_TRACE_BOUNDARY:
        raise VerificationError("runtime diagnostic evidence boundary differs")
    if trace["source_orchestration_boundary"] != ORCHESTRATION_BOUNDARY:
        raise VerificationError("runtime diagnostic source boundary differs")
    supplied_digest = _sha(trace["trace_sha256"], "trace_sha256")
    digest_body = dict(trace)
    del digest_body["trace_sha256"]
    if supplied_digest != sha256_ref(digest_body):
        raise VerificationError("runtime diagnostic trace digest differs")

    authority = _object(trace["authority"], "authority")
    _exact(authority, _AUTHORITY_FIELDS, "authority")
    for name in ("frozen_plan_sha256", "authentication_envelope_sha256", "scorer_implementation_sha256"):
        if authority[name] is not None:
            raise VerificationError(f"authority.{name} must remain null")
    for name in _AUTHORITY_FIELDS - {
        "frozen_plan_sha256",
        "authentication_envelope_sha256",
        "scorer_implementation_sha256",
    }:
        if authority[name] is not False:
            raise VerificationError(f"authority.{name} must remain false")

    task = _object(trace["task"], "task")
    _exact(
        task,
        {
            "task_id",
            "task_sha256",
            "source_sha256",
            "terminal_status",
            "output_text",
            "output_sha256",
            "terminal_observation_sha256",
        },
        "task",
    )
    if type(task["task_id"]) is not str or not task["task_id"]:
        raise VerificationError("task.task_id is invalid")
    for name in ("task_sha256", "source_sha256", "terminal_observation_sha256"):
        _sha(task[name], f"task.{name}")
    if task["output_sha256"] is not None:
        _sha(task["output_sha256"], "task.output_sha256")

    route = _object(trace["route"], "route")
    _exact(
        route,
        {
            "execution_binding_sha256",
            "route_binding_sha256",
            "source_sha256",
            "capsule_sha256",
            "selected_mode",
            "final_mode",
            "preselection_fallback_from",
            "fallback_sender_tokens",
            "fallback_semantic_verification_tokens",
            "fallback_from",
            "selected_request_binding_sha256",
            "primary_request_binding_sha256",
            "fallback_request_binding_sha256",
            "best_baseline_mode",
            "best_baseline_tokens",
            "selected_cost",
            "candidates",
        },
        "route",
    )
    for name in (
        "execution_binding_sha256",
        "route_binding_sha256",
        "source_sha256",
        "capsule_sha256",
        "selected_request_binding_sha256",
        "primary_request_binding_sha256",
    ):
        _sha(route[name], f"route.{name}")
    if route["fallback_request_binding_sha256"] is not None:
        _sha(
            route["fallback_request_binding_sha256"],
            "route.fallback_request_binding_sha256",
        )
    if route["selected_mode"] not in ROUTE_MODES or route["final_mode"] not in ROUTE_MODES:
        raise VerificationError("route mode is invalid")
    if route["best_baseline_mode"] not in {"raw", "json"}:
        raise VerificationError("route baseline mode is invalid")
    selected_cost = _validate_cost(route["selected_cost"], "route.selected_cost")
    for name in (
        "fallback_sender_tokens",
        "fallback_semantic_verification_tokens",
    ):
        _nullable_nonnegative_int(route[name], f"route.{name}")
    candidates = route["candidates"]
    if type(candidates) is not list or [item.get("mode") for item in candidates if type(item) is dict] != list(ROUTE_MODES):
        raise VerificationError("route five-candidate matrix differs")
    candidate_by_mode: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(candidates):
        path = f"route.candidates[{index}]"
        candidate = _object(raw, path)
        _exact(candidate, {"mode", "request", "cost", "eligible", "claim_eligible", "reasons"}, path)
        _bool(candidate["eligible"], f"{path}.eligible")
        if candidate["claim_eligible"] is not False:
            raise VerificationError(f"{path}.claim_eligible must remain false")
        if candidate["request"] is not None:
            request = _validate_request(candidate["request"], f"{path}.request")
            if request["mode"] != candidate["mode"]:
                raise VerificationError(f"{path} request mode differs")
        if candidate["cost"] is not None:
            _validate_cost(candidate["cost"], f"{path}.cost")
        if type(candidate["reasons"]) is not list or any(type(item) is not str or not item for item in candidate["reasons"]):
            raise VerificationError(f"{path}.reasons is invalid")
        candidate_by_mode[candidate["mode"]] = candidate
    selected_request = candidate_by_mode[route["selected_mode"]]["request"]
    candidate_selected_cost = candidate_by_mode[route["selected_mode"]]["cost"]
    if selected_request is None or selected_request["binding_sha256"] != route["selected_request_binding_sha256"]:
        raise VerificationError("selected request binding differs")
    if candidate_selected_cost is None:
        raise VerificationError("selected candidate cost is absent")
    preselection_fallback = route["preselection_fallback_from"]
    if preselection_fallback is None:
        if (
            route["fallback_sender_tokens"] != 0
            or route["fallback_semantic_verification_tokens"] != 0
            or selected_cost != candidate_selected_cost
        ):
            raise VerificationError("selected candidate cost differs")
    else:
        if (
            type(preselection_fallback) is not str
            or not preselection_fallback.startswith("action-state:")
            or route["selected_mode"] not in {"raw", "json"}
        ):
            raise VerificationError("preselection fallback is invalid")
        expected_cost = dict(candidate_selected_cost)
        expected_cost["sender_tokens"] += route["fallback_sender_tokens"] or 0
        expected_cost["semantic_verification_tokens"] += (
            route["fallback_semantic_verification_tokens"] or 0
        )
        expected_cost["complete"] = bool(
            candidate_selected_cost["complete"]
            and route["fallback_sender_tokens"] is not None
            and route["fallback_semantic_verification_tokens"] is not None
        )
        expected_cost["total_tokens"] = sum(
            expected_cost[name]
            for name in _COST_FIELDS
            if name != "complete"
        )
        if selected_cost != expected_cost:
            raise VerificationError("fallback-adjusted selected cost differs")
    baseline_candidate = candidate_by_mode[route["best_baseline_mode"]]
    baseline_cost = baseline_candidate["cost"]
    if baseline_candidate["request"] is None or baseline_cost is None:
        raise VerificationError("best baseline candidate is incomplete")
    expected_baseline_tokens = (
        baseline_cost["total_tokens"] if baseline_cost["complete"] else None
    )
    if route["best_baseline_tokens"] != expected_baseline_tokens:
        raise VerificationError("best baseline token binding differs")
    for field in (
        "task_context_sha256",
        "task_profile_sha256",
        "symbol_table_sha256",
    ):
        bound_digests = {
            candidate["request"][field]
            for candidate in candidates
            if candidate["request"] is not None
        }
        if bound_digests != {selected_request[field]}:
            raise VerificationError(f"candidate {field} bindings differ")
    raw_request = candidate_by_mode["raw"]["request"]
    if raw_request is None or raw_request["payload_sha256"] != route["source_sha256"]:
        raise VerificationError("raw candidate source binding differs")
    action_request = candidate_by_mode["action-state"]["request"]
    if (
        action_request is not None
        and action_request["capsule_sha256"] != route["capsule_sha256"]
    ):
        raise VerificationError("action-state Capsule binding differs")
    if route["primary_request_binding_sha256"] != route["selected_request_binding_sha256"]:
        raise VerificationError("primary request and selection differ")

    primary = _validate_execution(trace["primary_execution"], "primary_execution")
    fallback = (
        None
        if trace["fallback_execution"] is None
        else _validate_execution(trace["fallback_execution"], "fallback_execution")
    )
    if (
        primary["request_mode"] != route["selected_mode"]
        or primary["request_binding_sha256"]
        != route["primary_request_binding_sha256"]
        or primary["delivery_disposition"] != "live"
    ):
        raise VerificationError("primary execution binding differs")
    if primary["model_visible_sha256"] != selected_request["model_visible_sha256"]:
        raise VerificationError("primary model-visible binding differs")
    if fallback is None:
        if route["fallback_request_binding_sha256"] is not None or route["final_mode"] != route["selected_mode"]:
            raise VerificationError("absent fallback binding differs")
    else:
        baseline = candidate_by_mode[route["best_baseline_mode"]]["request"]
        if (
            baseline is None
            or fallback["request_binding_sha256"] != baseline["binding_sha256"]
            or fallback["request_binding_sha256"]
            != route["fallback_request_binding_sha256"]
            or fallback["request_mode"] != route["final_mode"]
            or fallback["delivery_disposition"] != "live"
            or fallback["model_visible_sha256"]
            != baseline["model_visible_sha256"]
        ):
            raise VerificationError("fallback execution binding differs")

    scorer = _object(trace["scorer_observation"], "scorer_observation")
    _exact(
        scorer,
        {"scoring_input", "scoring_input_sha256", "scorer_locks", "scorer_output", "scorer_observation_sha256", "scorer_calls"},
        "scorer_observation",
    )
    scoring_input = _validate_scoring_input(scorer["scoring_input"])
    scorer_output = _validate_scoring_output(scorer["scorer_output"])
    scorer_locks = _object(scorer["scorer_locks"], "scorer_observation.scorer_locks")
    _exact(
        scorer_locks,
        _SCORER_LOCK_FIELDS,
        "scorer_observation.scorer_locks",
    )
    for name, digest in scorer_locks.items():
        _sha(digest, f"scorer_observation.scorer_locks.{name}")
    if scorer["scoring_input_sha256"] != sha256_ref(scoring_input):
        raise VerificationError("scoring input digest differs")
    expected_scorer_observation = sha256_ref(
        {
            "schema_version": SCORER_OBSERVATION_SCHEMA,
            "scorer_locks": scorer_locks,
            "scoring_input": scoring_input,
            "scorer_output": scorer_output,
        }
    )
    if scorer["scorer_observation_sha256"] != expected_scorer_observation or scorer["scorer_calls"] != 1:
        raise VerificationError("scorer observation binding differs")
    for left, right, label in (
        (task["task_id"], scoring_input.get("task_id"), "task ID"),
        (task["task_sha256"], scoring_input.get("task_sha256"), "task digest"),
        (task["source_sha256"], scoring_input.get("source_sha256"), "source digest"),
        (task["terminal_status"], scoring_input.get("terminal_status"), "terminal status"),
        (task["output_text"], scoring_input.get("output_text"), "output text"),
        (task["output_sha256"], scoring_input.get("output_sha256"), "output digest"),
        (task["terminal_observation_sha256"], scoring_input.get("terminal_observation_sha256"), "terminal observation"),
        (route["execution_binding_sha256"], scoring_input.get("execution_binding_sha256"), "execution binding"),
        (route["route_binding_sha256"], scoring_input.get("route_binding_sha256"), "route binding"),
        (route["selected_mode"], scoring_input.get("selected_mode"), "selected mode"),
        (route["final_mode"], scoring_input.get("final_mode"), "final mode"),
        (route["fallback_from"], scoring_input.get("fallback_from"), "fallback reason"),
        (route["primary_request_binding_sha256"], scoring_input.get("primary_request_binding_sha256"), "primary request binding"),
        (route["fallback_request_binding_sha256"], scoring_input.get("fallback_request_binding_sha256"), "fallback request binding"),
        (task["source_sha256"], route["source_sha256"], "route source binding"),
    ):
        if left != right:
            raise VerificationError(f"runtime diagnostic {label} differs")
    for probe, observed, label in (
        (scoring_input["parse_probe"], scorer_output["parse_valid"], "parse"),
        (
            scoring_input["semantic_probe"],
            scorer_output["semantic_exact"],
            "semantic",
        ),
        (
            scoring_input["negative_probe"],
            scorer_output["negative_rejected"],
            "negative",
        ),
    ):
        if not probe and observed is not None:
            raise VerificationError(f"scorer {label} observation exceeds scope")
    for feature, observed in scorer_output["preservation"].items():
        if feature not in scoring_input["feature_tags"] and observed is not None:
            raise VerificationError(
                "scorer preservation observation exceeds declared scope"
            )

    terminal = fallback or primary
    if terminal["status"] == "silenced":
        expected_status = SILENCE_TERMINAL_STATUS
        expected_text = None
        expected_output = CANONICAL_SILENCE_OUTPUT_SHA256
        expected_terminal = sha256_ref({"terminal_status": expected_status, "output_sha256": expected_output, "failure": None})
    else:
        expected_status = "completed" if terminal["status"] == "completed" else "provider_error"
        expected_text = None if terminal["reply"] is None else terminal["reply"]["text"]
        expected_output = None if terminal["reply"] is None else terminal["reply"]["output_sha256"]
        expected_terminal = sha256_ref({"terminal_status": expected_status, "receiver_status": terminal["status"], "output_sha256": expected_output, "failure": terminal["failure"]})
    if (task["terminal_status"], task["output_text"], task["output_sha256"], task["terminal_observation_sha256"]) != (expected_status, expected_text, expected_output, expected_terminal):
        raise VerificationError("terminal execution and output binding differ")

    ledger_record = trace["observed_ledger"]
    validated_events: list[dict[str, Any]] | None = None
    if ledger_record is None:
        if scoring_input.get("observed_ledger_sha256") is not None:
            raise VerificationError("absent observed ledger digest differs")
    else:
        ledger_record = _object(ledger_record, "observed_ledger")
        _exact(ledger_record, {"sha256", "value"}, "observed_ledger")
        ledger = _object(ledger_record["value"], "observed_ledger.value")
        _exact(ledger, {"execution_binding_sha256", "events", "scope_complete", "inclusive_total_tokens", "provider_authenticity_verified", "claim_eligible", "goal_total_complete"}, "observed_ledger.value")
        if ledger_record["sha256"] != sha256_ref(ledger) or ledger_record["sha256"] != scoring_input.get("observed_ledger_sha256"):
            raise VerificationError("observed ledger digest differs")
        if ledger["execution_binding_sha256"] != route["execution_binding_sha256"]:
            raise VerificationError("observed ledger execution binding differs")
        for name in ("provider_authenticity_verified", "claim_eligible", "goal_total_complete"):
            if ledger[name] is not False:
                raise VerificationError(f"observed ledger {name} must remain false")
        events = ledger["events"]
        if type(events) is not list or [event.get("sequence") for event in events if type(event) is dict] != list(range(len(events))):
            raise VerificationError("observed ledger event order differs")
        validated_events = [
            _validate_ledger_event(
                event,
                f"observed_ledger.value.events[{index}]",
                route["execution_binding_sha256"],
            )
            for index, event in enumerate(events)
        ]
        components = [event["component"] for event in validated_events]
        if len(components) != len(set(components)):
            raise VerificationError("observed ledger components repeat")
        component_order = tuple(components)
        if component_order not in {
            RUNTIME_LEDGER_COMPONENT_ORDER,
            COLD_RUNTIME_LEDGER_COMPONENT_ORDER,
        }:
            raise VerificationError("observed ledger component order differs")
        if {event["phase"] for event in validated_events} != _EVENT_PHASES:
            raise VerificationError("observed ledger phase coverage differs")
        expected_scope_complete = all(
            event["total_tokens"] is not None for event in validated_events
        )
        if ledger["scope_complete"] is not expected_scope_complete:
            raise VerificationError("observed ledger scope completeness differs")
        expected_inclusive_total = (
            sum(event["total_tokens"] for event in validated_events)
            if expected_scope_complete
            else None
        )
        if ledger["inclusive_total_tokens"] != expected_inclusive_total:
            raise VerificationError("observed ledger inclusive total differs")
        primary_event = next(
            event
            for event in validated_events
            if event["component"] == "primary-receiver"
        )
        fallback_event = next(
            event
            for event in validated_events
            if event["component"] == "baseline-fallback-receiver"
        )
        for event, receiver, label in (
            (primary_event, primary, "primary"),
            (fallback_event, fallback, "fallback"),
        ):
            expected_calls = 0 if receiver is None else receiver["calls"]
            expected_total = 0 if receiver is None else receiver["total_tokens"]
            expected_reply = None if receiver is None else receiver["reply"]
            if (
                event["model_calls"] != expected_calls
                or event["total_tokens"] != expected_total
                or event["input_tokens"]
                != (None if expected_reply is None else expected_reply["input_tokens"])
                or event["output_tokens"]
                != (None if expected_reply is None else expected_reply["output_tokens"])
                or event["reasoning_tokens"]
                != (None if expected_reply is None else expected_reply["reasoning_tokens"])
                or event["reasoning_accounting"]
                != (None if expected_reply is None else expected_reply["reasoning_accounting"])
            ):
                raise VerificationError(
                    f"observed ledger {label} receiver usage differs"
                )

    summary = _object(trace["runtime_summary"], "runtime_summary")
    _exact(summary, {"compiler_calls", "fidelity_verifier_calls", "receiver_calls", "output_valid", "observed_runtime_tokens", "caller_reported_inclusive_total_tokens", "claim_inclusive_total_tokens", "caller_reported_safely_completed", "claim_safely_completed"}, "runtime_summary")
    if summary["claim_inclusive_total_tokens"] is not None or summary["claim_safely_completed"] is not None:
        raise VerificationError("claim-facing runtime summary must remain null")
    for name in ("compiler_calls", "fidelity_verifier_calls"):
        if type(summary[name]) is not int or summary[name] not in {0, 1}:
            raise VerificationError(f"runtime_summary.{name} is invalid")
    _nonnegative_int(summary["receiver_calls"], "runtime_summary.receiver_calls")
    _nullable_bool(summary["output_valid"], "runtime_summary.output_valid")
    _nullable_bool(
        summary["caller_reported_safely_completed"],
        "runtime_summary.caller_reported_safely_completed",
    )
    for name in (
        "observed_runtime_tokens",
        "caller_reported_inclusive_total_tokens",
    ):
        _nullable_nonnegative_int(summary[name], f"runtime_summary.{name}")
    if summary["receiver_calls"] != primary["calls"] + (0 if fallback is None else fallback["calls"]):
        raise VerificationError("runtime receiver call count differs")
    if validated_events is not None:
        by_component = {
            event["component"]: event for event in validated_events
        }
        if summary["compiler_calls"] != by_component["sender-compiler"]["model_calls"]:
            raise VerificationError("runtime compiler call count differs")
        if summary["fidelity_verifier_calls"] != by_component[
            "semantic-fidelity-verifier"
        ]["model_calls"]:
            raise VerificationError("runtime fidelity call count differs")
        called_events = [
            event for event in validated_events if event["model_calls"] == 1
        ]
        expected_runtime_tokens = (
            None
            if any(event["total_tokens"] is None for event in called_events)
            else sum(event["total_tokens"] for event in called_events)
        )
        if summary["observed_runtime_tokens"] != expected_runtime_tokens:
            raise VerificationError("runtime observed model total differs")
        ledger_total = ledger_record["value"]["inclusive_total_tokens"]
    else:
        ledger_total = None
    expected_caller_total = (
        ledger_total + scorer_output["total_tokens"]
        if ledger_total is not None and scorer_output["total_tokens"] is not None
        else None
    )
    if summary["caller_reported_inclusive_total_tokens"] != expected_caller_total:
        raise VerificationError("caller-reported inclusive total differs")
    runtime_safe = summary["output_valid"]
    if runtime_safe is None:
        expected_caller_safe = None
    elif runtime_safe is False:
        expected_caller_safe = False
    elif scorer_output["task_success"] is None or any(
        item is None for item in scorer_output["safety"].values()
    ):
        expected_caller_safe = None
    else:
        expected_caller_safe = bool(
            scorer_output["task_success"]
            and not any(item or 0 for item in scorer_output["safety"].values())
        )
    if summary["caller_reported_safely_completed"] is not expected_caller_safe:
        raise VerificationError("caller-reported safe completion differs")
    return trace


class RuntimeDiagnosticTrace:
    """Validated immutable-by-copy wrapper for the diagnostic trace schema."""

    __slots__ = ("_value",)

    def __init__(self, value: Any):
        self._value = validate_runtime_diagnostic_trace(value)

    @property
    def value(self) -> Mapping[str, Any]:
        return _detached(self._value)

    @property
    def sha256(self) -> str:
        return self._value["trace_sha256"]

    @property
    def claim_eligible(self) -> bool:
        return False
