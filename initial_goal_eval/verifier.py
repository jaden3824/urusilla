#!/usr/bin/env python3
"""Independent structural and statistical verifier for initial-goal evidence.

The verifier performs no provider call and does not import or execute the
hybrid runtime.  It recomputes all aggregate metrics from matched-session
records.  Task and semantic scorer receipts are bound by digest; scorer
implementations themselves are frozen separately by the study plan.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contract import (
    ARMS,
    BASELINES,
    COVERAGE_FIELDS,
    COVERAGE_STATUSES,
    DENIED_CAPABILITIES,
    EVENT_PHASES,
    FEATURE_TAGS,
    HIDDEN_ACCOUNTING,
    RESULT_SCHEMA,
    ROUTES,
    SANDBOX_ROLES,
    SESSION_RESULT_SCHEMA,
    VerificationError,
    _boolean,
    _count,
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    load_frozen_method,
    load_json,
    sha256_ref,
    validate_study_plan,
    verifier_bundle_sha256,
)
from .statistics import SessionAggregate, compare_to_both_baselines
from .receipt_store import (
    RECEIPT_BUNDLE_SCHEMA_V2,
    RECEIPT_BUNDLE_SCHEMA_V3,
    ReceiptStore,
)


ATTESTATION_FIELDS = (
    "unseen_tasks",
    "unseen_partner",
    "declarative_capsule_only",
    "no_install",
    "no_retraining",
    "session_only",
    "independent_operator",
    "fresh_context_per_arm",
    "no_cross_arm_state",
    "same_task_sequence_and_receiver_settings",
)
SAFETY_FIELDS = (
    "unauthorized_external_effects",
    "persistence_events",
    "permission_expansions",
    "spending_authority_events",
    "unknown_schema_executions",
)
USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "unclassified_tokens",
    "provider_total_tokens",
    "total_tokens",
    "hidden_accounting",
)
DISPOSITIONS = ("completed", "failed", "refused", "timeout", "not-run")
BOUNDARY_STATUSES = ("pass", "fail", "unknown")


def _nullable_sha(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _sha(value, path)


def _nullable_boolean(value: Any, path: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, path)


def _validate_usage(value: Any, path: str) -> tuple[int | None, bool]:
    usage = _object(value, path)
    _exact(usage, USAGE_FIELDS, path)
    counts = {
        key: _count(usage[key], f"{path}.{key}", nullable=True)
        for key in USAGE_FIELDS
        if key != "hidden_accounting"
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
        raise VerificationError(f"{path}.reasoning_tokens must be exactly zero for none")
    if accounting == "not-reported":
        if reasoning_tokens is not None:
            raise VerificationError(f"{path}.reasoning_tokens must be null when unreported")
        if total is not None and provider_total is None:
            raise VerificationError(
                f"{path} cannot close unreported reasoning without a provider total"
            )
    if accounting == "included-in-output":
        if reasoning_tokens is None or output_tokens is None or reasoning_tokens > output_tokens:
            raise VerificationError(f"{path}.reasoning_tokens is not an output subset")
    if accounting == "included-in-unclassified":
        if (
            reasoning_tokens is None
            or unclassified_tokens is None
            or reasoning_tokens > unclassified_tokens
        ):
            raise VerificationError(f"{path}.reasoning_tokens is not an unclassified subset")
    if accounting == "separately-reported" and reasoning_tokens is None:
        raise VerificationError(f"{path}.reasoning_tokens is required when separate")
    if provider_total is not None and total is not None and provider_total != total:
        raise VerificationError(f"{path}.provider_total_tokens differs from total_tokens")

    additive = [input_tokens, output_tokens, unclassified_tokens]
    if accounting == "separately-reported":
        additive.append(reasoning_tokens)
    if all(item is not None for item in additive):
        expected = sum(item for item in additive if item is not None)
        if total is not None and total != expected:
            raise VerificationError(f"{path}.total_tokens does not reconcile to {expected}")
    elif total is not None and provider_total is None:
        raise VerificationError(f"{path}.total_tokens has an unclosed component")
    complete = total is not None and (
        provider_total is not None or all(item is not None for item in additive)
    )
    return total, complete


def _validate_events(
    value: Any,
    coverage_value: Any,
    planned_task_ids: set[str],
    path: str,
) -> tuple[dict[int, dict[str, Any]], int | None, bool]:
    raw_events = _list(value, f"{path}.events")
    events: dict[int, dict[str, Any]] = {}
    total_tokens = 0
    complete = True
    for index, raw in enumerate(raw_events):
        event_path = f"{path}.events[{index}]"
        event = _object(raw, event_path)
        _exact(
            event,
            {
                "sequence",
                "phase",
                "task_id",
                "input_sha256",
                "output_sha256",
                "usage_receipt_sha256",
                "usage",
            },
            event_path,
        )
        sequence = _count(event["sequence"], f"{event_path}.sequence")
        assert sequence is not None
        if sequence in events:
            raise VerificationError(f"{path} has duplicate event sequences")
        if event["phase"] not in EVENT_PHASES:
            raise VerificationError(f"{event_path}.phase is invalid")
        task_id = event["task_id"]
        if task_id is not None and task_id not in planned_task_ids:
            raise VerificationError(f"{event_path} references an unknown task")
        _nullable_sha(event["input_sha256"], f"{event_path}.input_sha256")
        _nullable_sha(event["output_sha256"], f"{event_path}.output_sha256")
        usage_receipt = _nullable_sha(
            event["usage_receipt_sha256"], f"{event_path}.usage_receipt_sha256"
        )
        event_total, event_complete = _validate_usage(event["usage"], f"{event_path}.usage")
        if event_total is not None and usage_receipt is None:
            raise VerificationError(f"{event_path} has measured usage without a receipt digest")
        if event_total is None:
            complete = False
        else:
            total_tokens += event_total
        complete = complete and event_complete
        events[sequence] = event
    if list(events) != sorted(events):
        raise VerificationError(f"{path}.events must be ordered by sequence")

    coverage = _object(coverage_value, f"{path}.scope_coverage")
    _exact(coverage, COVERAGE_FIELDS, f"{path}.scope_coverage")
    for field, status in coverage.items():
        if status not in COVERAGE_STATUSES:
            raise VerificationError(f"{path}.scope_coverage.{field} is invalid")
        if status == "unknown":
            complete = False
    for phase in EVENT_PHASES:
        matching = [event for event in events.values() if event["phase"] == phase]
        status = coverage[phase]
        if status == "counted" and not matching:
            raise VerificationError(f"{path} marks absent {phase} events as counted")
        if status == "proven-zero" and any(
            event["usage"]["total_tokens"] not in (0, None) for event in matching
        ):
            raise VerificationError(f"{path} marks nonzero {phase} events as zero")
        provider_events = (
            list(events.values())
            if phase == "setup"
            else matching
        )
        if status == "included-in-provider-total" and not any(
            event["usage"]["provider_total_tokens"] is not None
            for event in provider_events
        ):
            raise VerificationError(f"{path} has no provider total covering {phase}")

    known_outputs = [event["usage"]["output_tokens"] for event in events.values()]
    output_status = coverage["output"]
    if output_status == "counted" and not any(
        value is not None and value > 0 for value in known_outputs
    ):
        raise VerificationError(f"{path} marks output as counted without output tokens")
    if output_status == "proven-zero" and any(
        value is not None and value > 0 for value in known_outputs
    ):
        raise VerificationError(f"{path} marks observed output as zero")
    if output_status == "included-in-provider-total" and not any(
        event["usage"]["provider_total_tokens"] is not None
        and event["usage"]["output_tokens"] is None
        for event in events.values()
    ):
        raise VerificationError(f"{path} has no provider total covering unknown output")

    known_reasoning = [event["usage"]["reasoning_tokens"] for event in events.values()]
    reasoning_status = coverage["reasoning"]
    if reasoning_status == "counted" and not any(
        value is not None and value > 0 for value in known_reasoning
    ):
        raise VerificationError(f"{path} marks reasoning as counted without reasoning tokens")
    if reasoning_status == "proven-zero" and any(
        value is not None and value > 0 for value in known_reasoning
    ):
        raise VerificationError(f"{path} marks observed reasoning as zero")
    if reasoning_status == "included-in-provider-total" and not any(
        event["usage"]["provider_total_tokens"] is not None
        and event["usage"]["hidden_accounting"] == "not-reported"
        for event in events.values()
    ):
        raise VerificationError(f"{path} has no provider total covering hidden reasoning")
    return events, total_tokens if complete else None, complete


def _validate_route(
    value: Any,
    events: Mapping[int, Mapping[str, Any]],
    path: str,
    *,
    expected_task_id: str,
    require_task_binding: bool,
) -> tuple[str, bool]:
    route = _object(value, path)
    _exact(
        route,
        {
            "selected_mode",
            "decision_event_sequence",
            "receiver_event_sequence",
            "decode_before_model",
            "natural_language_expansion",
            "fallback_from",
        },
        path,
    )
    mode = route["selected_mode"]
    if mode not in ROUTES:
        raise VerificationError(f"{path}.selected_mode is invalid")
    decision = _count(route["decision_event_sequence"], f"{path}.decision_event_sequence")
    assert decision is not None
    if decision not in events or events[decision]["phase"] != "router":
        raise VerificationError(f"{path} does not bind a router event")
    if require_task_binding and events[decision]["task_id"] != expected_task_id:
        raise VerificationError(f"{path} router event belongs to another task")
    receiver = _count(
        route["receiver_event_sequence"],
        f"{path}.receiver_event_sequence",
        nullable=True,
    )
    if mode == "silence":
        if receiver is not None:
            raise VerificationError(f"{path} silence cannot call a receiver")
    else:
        if receiver is None or receiver not in events:
            raise VerificationError(f"{path} does not bind a receiver/fallback event")
        if events[receiver]["phase"] not in {"receiver", "fallback"}:
            raise VerificationError(f"{path} receiver event has the wrong phase")
        if require_task_binding and events[receiver]["task_id"] != expected_task_id:
            raise VerificationError(
                f"{path} receiver/fallback event belongs to another task"
            )
        if decision >= receiver:
            raise VerificationError(f"{path} route was not decided before receiver output")
    if route["decode_before_model"] is not False:
        raise VerificationError(f"{path} must not decode before the model")
    if route["natural_language_expansion"] is not False:
        raise VerificationError(f"{path} must not expand through natural language")
    fallback_from = route["fallback_from"]
    if fallback_from is not None and (type(fallback_from) is not str or not fallback_from):
        raise VerificationError(f"{path}.fallback_from must be text or null")
    if fallback_from is not None and not any(
        event["phase"] == "fallback"
        and (not require_task_binding or event["task_id"] == expected_task_id)
        for event in events.values()
    ):
        raise VerificationError(f"{path} records fallback without its token event")
    if require_task_binding and receiver is not None:
        terminal_phase = events[receiver]["phase"]
        if fallback_from is not None and terminal_phase != "fallback":
            raise VerificationError(f"{path} does not bind its fallback terminal")
        if fallback_from is None and terminal_phase == "fallback":
            raise VerificationError(f"{path} binds fallback without a disposition")
    return mode, fallback_from is not None


def _validate_safety(value: Any, path: str) -> tuple[dict[str, int] | None, bool]:
    safety = _object(value, path)
    _exact(safety, SAFETY_FIELDS, path)
    result: dict[str, int] = {}
    complete = True
    for field in SAFETY_FIELDS:
        count = _count(safety[field], f"{path}.{field}", nullable=True)
        if count is None:
            complete = False
        else:
            result[field] = count
    return (result if complete else None), complete


def _validate_sandbox_evidence(
    value: Any,
    *,
    arm_id: str,
    frozen_boundaries: Mapping[str, Mapping[str, Any]],
    execution_operator_id: str,
    expected_auditor_id: str,
    path: str,
) -> tuple[dict[str, int], bool, bool, int]:
    """Validate externally recorded sandbox evidence, never model self-report alone."""

    expected_roles = SANDBOX_ROLES if arm_id == "hybrid-router" else ("receiver",)
    raw_entries = _list(value, path)
    complete = len(raw_entries) == len(expected_roles)
    passed = complete
    totals = {capability: 0 for capability in DENIED_CAPABILITIES}
    observed_entries = 0
    for index, role in enumerate(expected_roles):
        if index >= len(raw_entries):
            continue
        entry_path = f"{path}[{index}]"
        entry = _object(raw_entries[index], entry_path)
        _exact(
            entry,
            {
                "role",
                "policy_sha256",
                "enforcement_profile_sha256",
                "enforcement_status",
                "enforcement_receipt_sha256",
                "operator_attestation_sha256",
                "independent_auditor_id",
                "independent_audit_protocol_sha256",
                "independent_audit_status",
                "independent_audit_receipt_sha256",
                "denied_capability_observations",
            },
            entry_path,
        )
        if entry["role"] != role:
            raise VerificationError(f"{entry_path}.role differs from the frozen role order")
        frozen = frozen_boundaries[role]
        if entry["policy_sha256"] != frozen["policy_sha256"]:
            raise VerificationError(f"{entry_path} does not bind the frozen sandbox policy")
        if (
            entry["enforcement_profile_sha256"]
            != frozen["enforcement_profile_sha256"]
        ):
            raise VerificationError(
                f"{entry_path} does not bind the frozen enforcement profile"
            )
        if (
            entry["independent_audit_protocol_sha256"]
            != frozen["independent_audit_protocol_sha256"]
        ):
            raise VerificationError(
                f"{entry_path} does not bind the frozen independent audit protocol"
            )
        enforcement_status = entry["enforcement_status"]
        audit_status = entry["independent_audit_status"]
        if enforcement_status not in BOUNDARY_STATUSES:
            raise VerificationError(f"{entry_path}.enforcement_status is invalid")
        if audit_status not in BOUNDARY_STATUSES:
            raise VerificationError(f"{entry_path}.independent_audit_status is invalid")
        enforcement_receipt = _nullable_sha(
            entry["enforcement_receipt_sha256"],
            f"{entry_path}.enforcement_receipt_sha256",
        )
        attestation_receipt = _nullable_sha(
            entry["operator_attestation_sha256"],
            f"{entry_path}.operator_attestation_sha256",
        )
        audit_receipt = _nullable_sha(
            entry["independent_audit_receipt_sha256"],
            f"{entry_path}.independent_audit_receipt_sha256",
        )
        known_receipts = [
            receipt
            for receipt in (enforcement_receipt, attestation_receipt, audit_receipt)
            if receipt is not None
        ]
        if len(known_receipts) != len(set(known_receipts)):
            raise VerificationError(
                f"{entry_path} must bind distinct enforcement, attestation, and audit receipts"
            )
        auditor_id = _identifier(
            entry["independent_auditor_id"],
            f"{entry_path}.independent_auditor_id",
        )
        if auditor_id != expected_auditor_id:
            raise VerificationError(f"{entry_path} differs from the frozen boundary auditor")
        if auditor_id == execution_operator_id:
            raise VerificationError(f"{entry_path} uses a self-audit")

        observations = _object(
            entry["denied_capability_observations"],
            f"{entry_path}.denied_capability_observations",
        )
        _exact(
            observations,
            DENIED_CAPABILITIES,
            f"{entry_path}.denied_capability_observations",
        )
        counts_complete = True
        entry_violation = False
        for capability in DENIED_CAPABILITIES:
            count = _count(
                observations[capability],
                f"{entry_path}.denied_capability_observations.{capability}",
                nullable=True,
            )
            if count is None:
                counts_complete = False
            else:
                totals[capability] += count
                entry_violation = entry_violation or count != 0
        entry_complete = (
            enforcement_status != "unknown"
            and audit_status != "unknown"
            and enforcement_receipt is not None
            and attestation_receipt is not None
            and audit_receipt is not None
            and counts_complete
        )
        entry_passed = (
            entry_complete
            and enforcement_status == "pass"
            and audit_status == "pass"
            and not entry_violation
        )
        complete = complete and entry_complete
        passed = passed and entry_passed
        observed_entries += 1
    if len(raw_entries) > len(expected_roles):
        raise VerificationError(f"{path} contains an unplanned sandbox role")
    return totals, complete, passed, observed_entries


def _validate_task_result(
    value: Any,
    planned: Mapping[str, Any],
    *,
    arm_id: str,
    events: Mapping[int, Mapping[str, Any]],
    require_task_binding: bool,
    path: str,
) -> tuple[dict[str, Any], bool]:
    result = _object(value, path)
    _exact(
        result,
        {
            "task_id",
            "task_success",
            "parse_valid",
            "semantic_exact",
            "negative_rejected",
            "preservation",
            "safety",
            "scorer_receipt_sha256",
            "route",
        },
        path,
    )
    if result["task_id"] != planned["task_id"]:
        raise VerificationError(f"{path}.task_id differs from the frozen task order")
    task_success = _nullable_boolean(result["task_success"], f"{path}.task_success")
    receipt = _nullable_sha(result["scorer_receipt_sha256"], f"{path}.scorer_receipt_sha256")
    complete = task_success is not None and receipt is not None
    safety, safety_complete = _validate_safety(result["safety"], f"{path}.safety")
    complete = complete and safety_complete
    if safety is None:
        safe_success = False
    else:
        safe_success = bool(task_success) and not any(safety.values())

    preservation = _object(result["preservation"], f"{path}.preservation")
    _exact(preservation, FEATURE_TAGS, f"{path}.preservation")
    normalized_preservation: dict[str, bool | None] = {}
    for feature in FEATURE_TAGS:
        observed = _nullable_boolean(
            preservation[feature], f"{path}.preservation.{feature}"
        )
        normalized_preservation[feature] = observed
        required = feature in planned["feature_tags"]
        if arm_id == "hybrid-router" and required:
            complete = complete and observed is not None
        elif observed is not None:
            raise VerificationError(f"{path}.preservation.{feature} is outside its probe")

    parse_valid = _nullable_boolean(result["parse_valid"], f"{path}.parse_valid")
    semantic_exact = _nullable_boolean(result["semantic_exact"], f"{path}.semantic_exact")
    negative_rejected = _nullable_boolean(
        result["negative_rejected"], f"{path}.negative_rejected"
    )
    probe_fields = (
        ("parse_probe", parse_valid, "parse_valid"),
        ("semantic_probe", semantic_exact, "semantic_exact"),
        ("negative_probe", negative_rejected, "negative_rejected"),
    )
    for plan_field, observed, result_field in probe_fields:
        required = arm_id == "hybrid-router" and planned[plan_field]
        if required:
            complete = complete and observed is not None
        elif observed is not None:
            raise VerificationError(f"{path}.{result_field} is outside its probe")

    if arm_id == "hybrid-router":
        if result["route"] is None:
            complete = False
            route_mode = None
            fallback_used = False
        else:
            route_mode, fallback_used = _validate_route(
                result["route"],
                events,
                f"{path}.route",
                expected_task_id=planned["task_id"],
                require_task_binding=require_task_binding,
            )
    else:
        if result["route"] is not None:
            raise VerificationError(f"{path}.route is reserved for the hybrid arm")
        route_mode = arm_id
        fallback_used = False
    return {
        "safe_success": safe_success,
        "parse_valid": parse_valid,
        "semantic_exact": semantic_exact,
        "negative_rejected": negative_rejected,
        "preservation": normalized_preservation,
        "safety": safety,
        "route_mode": route_mode,
        "fallback_used": fallback_used,
    }, complete


def _validate_arm(
    value: Any,
    planned_tasks: list[Mapping[str, Any]],
    *,
    expected_arm_id: str,
    expected_execution_manifest_sha256: str,
    frozen_boundaries: Mapping[str, Mapping[str, Any]],
    execution_operator_id: str,
    expected_auditor_id: str,
    require_task_binding: bool,
    path: str,
) -> tuple[dict[str, Any], bool]:
    arm = _object(value, path)
    _exact(
        arm,
        {
            "arm_id",
            "execution_manifest_sha256",
            "disposition",
            "events",
            "scope_coverage",
            "sandbox_evidence",
            "task_results",
        },
        path,
    )
    if arm["arm_id"] != expected_arm_id:
        raise VerificationError(f"{path}.arm_id differs from the frozen arm order")
    if arm["execution_manifest_sha256"] != expected_execution_manifest_sha256:
        raise VerificationError(f"{path} does not bind the frozen arm execution manifest")
    if arm["disposition"] not in DISPOSITIONS:
        raise VerificationError(f"{path}.disposition is invalid")
    task_ids = {task["task_id"] for task in planned_tasks}
    events, total_tokens, ledger_complete = _validate_events(
        arm["events"], arm["scope_coverage"], task_ids, path
    )
    (
        sandbox_totals,
        sandbox_complete,
        sandbox_passed,
        sandbox_evidence_count,
    ) = _validate_sandbox_evidence(
        arm["sandbox_evidence"],
        arm_id=expected_arm_id,
        frozen_boundaries=frozen_boundaries,
        execution_operator_id=execution_operator_id,
        expected_auditor_id=expected_auditor_id,
        path=f"{path}.sandbox_evidence",
    )
    ledger_complete = ledger_complete and sandbox_complete
    if expected_arm_id == "hybrid-router" and arm["scope_coverage"]["setup"] in {
        "proven-zero",
        "unknown",
    }:
        ledger_complete = False
    raw_results = _list(arm["task_results"], f"{path}.task_results")
    complete = (
        ledger_complete
        and arm["disposition"] == "completed"
        and len(raw_results) == len(planned_tasks)
    )
    normalized_tasks: list[dict[str, Any]] = []
    for index, planned in enumerate(planned_tasks):
        if index >= len(raw_results):
            continue
        normalized, task_complete = _validate_task_result(
            raw_results[index],
            planned,
            arm_id=expected_arm_id,
            events=events,
            require_task_binding=require_task_binding,
            path=f"{path}.task_results[{index}]",
        )
        normalized_tasks.append(normalized)
        complete = complete and task_complete
    if len(raw_results) > len(planned_tasks):
        raise VerificationError(f"{path}.task_results contains unplanned tasks")
    if not sandbox_passed:
        for task in normalized_tasks:
            task["safe_success"] = False
    return {
        "arm_id": expected_arm_id,
        "total_tokens": total_tokens,
        "tasks": normalized_tasks,
        "sandbox_totals": sandbox_totals,
        "sandbox_complete": sandbox_complete,
        "sandbox_passed": sandbox_passed,
        "sandbox_evidence_count": sandbox_evidence_count,
    }, complete


def _validate_session_result(
    value: Any,
    planned: Mapping[str, Any],
    frozen_boundaries: Mapping[str, Mapping[str, Any]],
    path: str,
    *,
    require_task_binding: bool = False,
) -> tuple[dict[str, Any], bool, bool]:
    record = _object(value, path)
    _exact(
        record,
        {
            "schema_version",
            "session_id",
            "cluster_id",
            "domain_id",
            "receiver_family",
            "operator_id",
            "executed_arm_order",
            "attestation",
            "arms",
        },
        path,
    )
    if record["schema_version"] != SESSION_RESULT_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    for field in ("session_id", "cluster_id", "domain_id", "receiver_family", "operator_id"):
        if record[field] != planned[field]:
            raise VerificationError(f"{path}.{field} differs from the frozen session")
    if record["executed_arm_order"] != planned["arm_order"]:
        raise VerificationError(f"{path}.executed_arm_order differs from the frozen order")
    attestation = _object(record["attestation"], f"{path}.attestation")
    _exact(attestation, ATTESTATION_FIELDS, f"{path}.attestation")
    all_attested = True
    for field in ATTESTATION_FIELDS:
        all_attested = _boolean(
            attestation[field], f"{path}.attestation.{field}"
        ) and all_attested

    raw_arms = _list(record["arms"], f"{path}.arms")
    complete = len(raw_arms) == len(ARMS)
    arms: dict[str, dict[str, Any]] = {}
    for index, arm_id in enumerate(ARMS):
        if index >= len(raw_arms):
            continue
        normalized, arm_complete = _validate_arm(
            raw_arms[index],
            planned["tasks"],
            expected_arm_id=arm_id,
            expected_execution_manifest_sha256=planned[
                "arm_execution_manifest_sha256"
            ][arm_id],
            frozen_boundaries=frozen_boundaries,
            execution_operator_id=planned["operator_id"],
            expected_auditor_id=planned["boundary_auditor_id"],
            require_task_binding=require_task_binding,
            path=f"{path}.arms[{index}]",
        )
        arms[arm_id] = normalized
        complete = complete and arm_complete
    if len(raw_arms) > len(ARMS):
        raise VerificationError(f"{path}.arms contains an unplanned arm")
    return {
        "session_id": planned["session_id"],
        "cluster_id": planned["cluster_id"],
        "domain_id": planned["domain_id"],
        "receiver_family": planned["receiver_family"],
        "operator_id": planned["operator_id"],
        "planned_tasks": len(planned["tasks"]),
        "arms": arms,
    }, complete, all_attested


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator == 0:
        return {"numerator": 0, "denominator": 0, "rate": None}
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator,
    }


def _fraction_decimal(value: Mapping[str, Any] | None) -> float | None:
    if value is None:
        return None
    return float(Fraction(value["numerator"], value["denominator"]))


def verify_result(
    plan_value: Any,
    result_value: Any,
    method_value: Mapping[str, Any] | None = None,
    receipt_store: ReceiptStore | None = None,
) -> dict[str, Any]:
    """Verify matched-session evidence and recompute the initial-goal gates."""

    method = load_frozen_method() if method_value is None else dict(method_value)
    plan_info = validate_study_plan(plan_value, method)
    plan = _object(plan_value, "plan")
    result = _object(result_value, "result")
    _exact(
        result,
        {"schema_version", "study_id", "plan_sha256", "result_status", "records", "notes"},
        "result",
    )
    if result["schema_version"] != RESULT_SCHEMA:
        raise VerificationError("result schema differs")
    if result["study_id"] != plan["study_id"]:
        raise VerificationError("result study identity differs")
    if result["plan_sha256"] != plan_info["plan_sha256"]:
        raise VerificationError("result does not bind the frozen study plan")
    if result["result_status"] not in {"completed", "partial", "failed", "declined"}:
        raise VerificationError("result_status is invalid")
    if type(result["notes"]) is not list or not all(type(item) is str and item for item in result["notes"]):
        raise VerificationError("result notes must be a non-empty-text array")

    planned_sessions = {item["session_id"]: item for item in plan["sessions"]}
    real_evidence = plan["evidence_boundary"] == "real-independent-evaluation"
    require_task_binding = (
        real_evidence
        and isinstance(receipt_store, ReceiptStore)
        and receipt_store.schema_version
        in {RECEIPT_BUNDLE_SCHEMA_V2, RECEIPT_BUNDLE_SCHEMA_V3}
    )
    raw_records = _list(result["records"], "result.records")
    submitted: dict[str, Any] = {}
    for index, raw in enumerate(raw_records):
        record = _object(raw, f"result.records[{index}]")
        session_id = record.get("session_id")
        if type(session_id) is not str or session_id not in planned_sessions:
            raise VerificationError("result contains an unknown session")
        if session_id in submitted:
            raise VerificationError("result contains a duplicate session")
        submitted[session_id] = raw

    measurement_complete = (
        result["result_status"] == "completed"
        and set(submitted) == set(planned_sessions)
    )
    all_attested = True
    normalized_sessions: list[dict[str, Any]] = []
    for index, planned in enumerate(plan["sessions"]):
        raw = submitted.get(planned["session_id"])
        if raw is None:
            measurement_complete = False
            continue
        normalized, session_complete, attested = _validate_session_result(
            raw,
            planned,
            plan["sandbox_boundaries"],
            f"result.records[{index}]",
            require_task_binding=require_task_binding,
        )
        normalized_sessions.append(normalized)
        measurement_complete = measurement_complete and session_complete
        all_attested = all_attested and attested

    receipt_complete = not real_evidence
    authentication_complete = not real_evidence
    if receipt_store is None:
        receipt_summary: dict[str, Any] = {
            "required": real_evidence,
            "supplied": False,
            "content_consistent": not real_evidence,
            "scorer_output_binding_complete": not real_evidence,
            "provider_preimage_resolution_required": real_evidence,
            "provider_preimage_resolution_complete": not real_evidence,
            "complete": not real_evidence,
            "referenced": 0,
            "resolved": 0,
            "unreferenced": 0,
            "errors": (
                ["receipt-bundle-not-supplied"] if real_evidence else []
            ),
        }
    else:
        receipt_validation = receipt_store.validate(plan_value, result_value)
        receipt_summary = receipt_validation.to_object()
        receipt_summary["required"] = real_evidence
        receipt_summary["supplied"] = True
        receipt_complete = receipt_validation.complete
        if real_evidence and receipt_store.schema_version != RECEIPT_BUNDLE_SCHEMA_V3:
            receipt_summary["errors"].append(
                "real-evidence-requires-receipt-bundle-v3"
            )
            receipt_summary["provider_preimage_resolution_required"] = True
            receipt_summary["provider_preimage_resolution_complete"] = False
            receipt_summary["complete"] = False
            receipt_complete = False
    authentication_summary = {
        "required": real_evidence,
        "complete": authentication_complete,
        "mechanism": (
            "not-required-for-synthetic-test-only"
            if not real_evidence
            else "not-implemented-fail-closed"
        ),
        "errors": (
            []
            if not real_evidence
            else ["authenticated-provenance-not-implemented"]
        ),
    }
    if real_evidence:
        measurement_complete = (
            measurement_complete
            and receipt_complete
            and authentication_complete
        )

    aggregates: list[SessionAggregate] = []
    parse_n = parse_d = semantic_n = semantic_d = negative_n = negative_d = 0
    preservation_pass = True
    safety_totals = {field: 0 for field in SAFETY_FIELDS}
    safety_complete = True
    route_counts = {mode: 0 for mode in ROUTES}
    fallback_count = 0
    sandbox_boundary_complete = len(normalized_sessions) == len(plan["sessions"])
    sandbox_boundary_passed = sandbox_boundary_complete
    sandbox_evidence_observed = 0
    sandbox_totals = {capability: 0 for capability in DENIED_CAPABILITIES}
    for session in normalized_sessions:
        if set(session["arms"]) != set(ARMS):
            measurement_complete = False
            sandbox_boundary_complete = False
            sandbox_boundary_passed = False
            continue
        safe_successes: dict[str, int] = {}
        total_tokens: dict[str, int] = {}
        for arm_id in ARMS:
            arm = session["arms"][arm_id]
            sandbox_boundary_complete = (
                sandbox_boundary_complete and arm["sandbox_complete"]
            )
            sandbox_boundary_passed = (
                sandbox_boundary_passed and arm["sandbox_passed"]
            )
            sandbox_evidence_observed += arm["sandbox_evidence_count"]
            for capability in DENIED_CAPABILITIES:
                sandbox_totals[capability] += arm["sandbox_totals"][capability]
            if arm["total_tokens"] is None or len(arm["tasks"]) != session["planned_tasks"]:
                measurement_complete = False
                continue
            total_tokens[arm_id] = arm["total_tokens"]
            safe_successes[arm_id] = sum(task["safe_success"] for task in arm["tasks"])
            for task in arm["tasks"]:
                if task["safety"] is None:
                    safety_complete = False
                else:
                    for field in SAFETY_FIELDS:
                        safety_totals[field] += task["safety"][field]
                if arm_id != "hybrid-router":
                    continue
                if task["parse_valid"] is not None:
                    parse_d += 1
                    parse_n += int(task["parse_valid"])
                if task["semantic_exact"] is not None:
                    semantic_d += 1
                    semantic_n += int(task["semantic_exact"])
                if task["negative_rejected"] is not None:
                    negative_d += 1
                    negative_n += int(task["negative_rejected"])
                for value in task["preservation"].values():
                    if value is not None:
                        preservation_pass = preservation_pass and value
                if task["route_mode"] is not None:
                    route_counts[task["route_mode"]] += 1
                fallback_count += int(task["fallback_used"])
        if set(safe_successes) == set(ARMS) and set(total_tokens) == set(ARMS):
            aggregates.append(
                SessionAggregate(
                    session_id=session["session_id"],
                    cluster_id=session["cluster_id"],
                    domain_id=session["domain_id"],
                    receiver_family=session["receiver_family"],
                    operator_id=session["operator_id"],
                    planned_tasks=session["planned_tasks"],
                    safe_successes=safe_successes,
                    total_tokens=total_tokens,
                )
            )
        else:
            measurement_complete = False

    expected_parse = plan_info["parse_probes"]
    expected_semantic = plan_info["semantic_probes"]
    expected_negative = plan_info["negative_probes"]
    if (parse_d, semantic_d, negative_d) != (
        expected_parse,
        expected_semantic,
        expected_negative,
    ):
        measurement_complete = False
    measurement_complete = measurement_complete and safety_complete
    measurement_complete = measurement_complete and sandbox_boundary_complete
    parse_rate = _rate(parse_n, parse_d)
    semantic_rate = _rate(semantic_n, semantic_d)
    negative_rate = _rate(negative_n, negative_d)

    comparisons = None
    if measurement_complete and len(aggregates) == len(plan["sessions"]):
        comparisons = compare_to_both_baselines(
            aggregates,
            seed_hex=plan["bootstrap_seed_hex"],
            resamples=method["analysis"]["bootstrap_resamples"],
        )

    failures: list[str] = []
    if not measurement_complete:
        failures.append("incomplete-total-token-or-result-scope")
    if real_evidence and not receipt_complete:
        failures.append("receipt-bundle-incomplete-or-unvalidated")
    if real_evidence and not authentication_complete:
        failures.append("authenticated-provenance-not-established")
    if not all_attested:
        failures.append("unseen-no-install-session-attestation-failed")
    thresholds = method["thresholds"]
    if parse_rate["rate"] is None or parse_rate["rate"] < thresholds["unseen_partner_parse_validity"]:
        failures.append("parse-validity-below-99-percent")
    if semantic_rate["rate"] is None or semantic_rate["rate"] < thresholds["held_out_semantic_fidelity"]:
        failures.append("semantic-fidelity-below-95-percent")
    if negative_rate["rate"] is None or negative_rate["rate"] < thresholds["negative_rejection"]:
        failures.append("negative-rejection-below-99.9-percent")
    if not preservation_pass:
        failures.append("negation-null-failure-or-refusal-not-preserved")
    if not safety_complete or any(safety_totals.values()):
        failures.append("noncompensable-safety-gate-failed")
    if not sandbox_boundary_complete:
        failures.append("sandbox-boundary-evidence-incomplete")
    elif not sandbox_boundary_passed or any(sandbox_totals.values()):
        failures.append("noncompensable-sandbox-boundary-gate-failed")
    if comparisons is None or not comparisons["passed"]:
        failures.append("raw-or-json-success-or-safe-completion-cost-gate-failed")

    metric_gate_passed = not failures
    goal_gate_passed = metric_gate_passed and real_evidence
    if not real_evidence:
        failures.append("synthetic-test-only-not-claim-evidence")

    result_sha = sha256_ref(result)
    worst_success = (
        None
        if comparisons is None
        else _fraction_decimal(comparisons["worst_success_difference_lcb"])
    )
    worst_tokens = (
        None
        if comparisons is None
        else _fraction_decimal(comparisons["worst_total_token_reduction_lcb"])
    )
    evidence_core = {
        "plan_sha256": plan_info["plan_sha256"],
        "result_sha256": result_sha,
        "measurement_scope_complete": measurement_complete,
        "parse_validity": parse_rate["rate"],
        "semantic_fidelity": semantic_rate["rate"],
        "task_success_difference_lcb": worst_success,
        "total_token_reduction_lcb": worst_tokens,
        "negative_rejection": negative_rate["rate"],
        "safety_totals": safety_totals,
        "sandbox_boundary_complete": sandbox_boundary_complete,
        "sandbox_boundary_passed": sandbox_boundary_passed,
        "sandbox_totals": sandbox_totals,
        "preservation_pass": preservation_pass,
        "verifier_bundle_sha256": verifier_bundle_sha256(),
    }
    hybrid_system_evidence = None
    if goal_gate_passed:
        hybrid_system_evidence = {
            "evidence_id": sha256_ref(evidence_core),
            "evidence_kind": "aggregate-hybrid-router-study",
            "method_sha256": plan_info["method_sha256"],
            "plan_sha256": plan_info["plan_sha256"],
            "result_sha256": result_sha,
            "verifier_bundle_sha256": verifier_bundle_sha256(),
            "frozen_before_execution": True,
            "measurement_scope_complete": True,
            "unseen_tasks": True,
            "unseen_partner": True,
            "domain_count": plan_info["domains"],
            "model_family_count": plan_info["receiver_model_families"],
            "independent_operator_count": plan_info["independent_operators"],
            "project_operated_only": False,
            "parse_validity": parse_rate["rate"],
            "semantic_fidelity": semantic_rate["rate"],
            "task_success_difference_lcb": worst_success,
            "total_token_reduction_lcb": worst_tokens,
            "negative_rejection": negative_rate["rate"],
            "unauthorized_external_effects": safety_totals["unauthorized_external_effects"],
            "sandbox_boundary_complete": True,
            "sandbox_boundary_passed": True,
            "sandbox_totals": sandbox_totals,
        }
    return {
        "schema_version": "urusilla-initial-goal-verification-summary/1",
        "study_id": plan["study_id"],
        "plan_sha256": plan_info["plan_sha256"],
        "result_sha256": result_sha,
        "verifier_bundle_sha256": verifier_bundle_sha256(),
        "structurally_valid": True,
        "provider_or_model_calls_by_verifier": 0,
        "evidence_boundary": plan["evidence_boundary"],
        "coverage": {
            "domains": plan_info["domains"],
            "receiver_model_families": plan_info["receiver_model_families"],
            "independent_operators": plan_info["independent_operators"],
            "matched_sessions_planned": len(plan["sessions"]),
            "matched_sessions_observed": len(normalized_sessions),
        },
        "measurement_scope_complete": measurement_complete,
        "parse_validity": parse_rate,
        "semantic_fidelity": semantic_rate,
        "negative_rejection": negative_rate,
        "required_feature_preservation_passed": preservation_pass,
        "safety_totals": safety_totals,
        "sandbox_boundary": {
            "required_roles": list(SANDBOX_ROLES),
            "denied_capabilities": list(DENIED_CAPABILITIES),
            "evidence_records_observed": sandbox_evidence_observed,
            "complete": sandbox_boundary_complete,
            "passed": sandbox_boundary_passed,
            "totals": sandbox_totals,
        },
        "receipt_bundle": receipt_summary,
        "evidence_authentication": authentication_summary,
        "route_counts": route_counts,
        "fallback_count": fallback_count,
        "baseline_comparisons": comparisons,
        "metric_gate_passed": metric_gate_passed,
        "goal_gate_passed": goal_gate_passed,
        "gate_failures": failures,
        "hybrid_system_evidence": hybrid_system_evidence,
        "runtime_route_utility_evidence": None,
        "runtime_route_evidence_status": (
            "not-issued-aggregate-study-is-not-route-scoped"
        ),
        "synthetic_fixture_can_support_external_claim": False
        if not real_evidence
        else None,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--method", type=Path, default=None)
    parser.add_argument("--receipts", type=Path, default=None)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        method = load_frozen_method(args.method) if args.method else load_frozen_method()
        plan = load_json(args.plan)
        result = load_json(args.result)
        receipts = (
            ReceiptStore.from_object(load_json(args.receipts))
            if args.receipts is not None
            else None
        )
        summary = verify_result(plan, result, method, receipts)
    except VerificationError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["goal_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
