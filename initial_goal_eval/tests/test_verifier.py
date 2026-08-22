"""Mutation-focused tests using synthetic, non-claim evidence only."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from initial_goal_eval.contract import (
    ARMS,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    SESSION_RESULT_SCHEMA,
    VerificationError,
    load_frozen_method,
    sha256_ref,
    validate_frozen_method,
    validate_study_plan,
    verifier_bundle_sha256,
)
from initial_goal_eval.verifier import verify_result
from initial_goal_eval.receipt_store import RECEIPT_BUNDLE_SCHEMA_V2, ReceiptStore
from initial_goal_eval.statistics import SessionAggregate, compare_against_baseline


def _digest(label: str) -> str:
    return sha256_ref({"synthetic-test-only": label})


def _usage(input_tokens: int, output_tokens: int) -> dict[str, object]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,
        "unclassified_tokens": 0,
        "provider_total_tokens": None,
        "total_tokens": input_tokens + output_tokens,
        "hidden_accounting": "none",
    }


def _event(sequence: int, phase: str, input_tokens: int, output_tokens: int) -> dict[str, object]:
    return {
        "sequence": sequence,
        "phase": phase,
        "task_id": None,
        "input_sha256": _digest(f"{phase}-{sequence}-input"),
        "output_sha256": _digest(f"{phase}-{sequence}-output") if output_tokens else None,
        "usage_receipt_sha256": _digest(f"{phase}-{sequence}-usage"),
        "usage": _usage(input_tokens, output_tokens),
    }


def _coverage(*counted: str) -> dict[str, str]:
    result = {
        "setup": "proven-zero",
        "sender": "proven-zero",
        "router": "proven-zero",
        "receiver": "proven-zero",
        "output": "proven-zero",
        "reasoning": "proven-zero",
        "repair": "proven-zero",
        "fallback": "proven-zero",
        "tool": "proven-zero",
        "safety": "proven-zero",
        "judge": "proven-zero",
    }
    for item in counted:
        result[item] = "counted"
    return result


def _safety() -> dict[str, int]:
    return {
        "unauthorized_external_effects": 0,
        "persistence_events": 0,
        "permission_expansions": 0,
        "spending_authority_events": 0,
        "unknown_schema_executions": 0,
    }


def _task_result(task: dict[str, object], arm_id: str) -> dict[str, object]:
    hybrid = arm_id == "hybrid-router"
    preservation = {
        feature: True if hybrid and feature in task["feature_tags"] else None
        for feature in ("negation", "null", "failure", "refusal")
    }
    return {
        "task_id": task["task_id"],
        "task_success": True,
        "parse_valid": True if hybrid and task["parse_probe"] else None,
        "semantic_exact": True if hybrid and task["semantic_probe"] else None,
        "negative_rejected": True if hybrid and task["negative_probe"] else None,
        "preservation": preservation,
        "safety": _safety(),
        "scorer_receipt_sha256": _digest(f"{task['task_id']}-{arm_id}-score"),
        "route": (
            {
                "selected_mode": "action-state",
                "decision_event_sequence": 2,
                "receiver_event_sequence": 3,
                "decode_before_model": False,
                "natural_language_expansion": False,
                "fallback_from": None,
            }
            if hybrid
            else None
        ),
    }


def _sandbox_evidence(
    session: dict[str, object],
    arm_id: str,
    sandbox_boundaries: dict[str, object],
) -> list[dict[str, object]]:
    roles = ("sender-compiler", "receiver") if arm_id == "hybrid-router" else ("receiver",)
    return [
        {
            "role": role,
            "policy_sha256": sandbox_boundaries[role]["policy_sha256"],
            "enforcement_profile_sha256": sandbox_boundaries[role][
                "enforcement_profile_sha256"
            ],
            "enforcement_status": "pass",
            "enforcement_receipt_sha256": _digest(
                f"{session['session_id']}-{arm_id}-{role}-enforcement"
            ),
            "operator_attestation_sha256": _digest(
                f"{session['session_id']}-{arm_id}-{role}-operator-attestation"
            ),
            "independent_auditor_id": session["boundary_auditor_id"],
            "independent_audit_protocol_sha256": sandbox_boundaries[role][
                "independent_audit_protocol_sha256"
            ],
            "independent_audit_status": "pass",
            "independent_audit_receipt_sha256": _digest(
                f"{session['session_id']}-{arm_id}-{role}-independent-audit"
            ),
            "denied_capability_observations": {
                "tools": 0,
                "network": 0,
                "credentials": 0,
                "persistence": 0,
                "spending": 0,
                "permission-expansion": 0,
            },
        }
        for role in roles
    ]


def _arm_result(
    session: dict[str, object],
    arm_id: str,
    sandbox_boundaries: dict[str, object],
) -> dict[str, object]:
    if arm_id == "raw-concise":
        events = [_event(0, "receiver", 900, 100)]
        coverage = _coverage("receiver", "output")
    elif arm_id == "ordinary-json":
        events = [_event(0, "receiver", 810, 90)]
        coverage = _coverage("receiver", "output")
    else:
        events = [
            _event(0, "setup", 60, 0),
            _event(1, "sender", 50, 10),
            _event(2, "router", 10, 0),
            _event(3, "receiver", 420, 50),
        ]
        coverage = _coverage("setup", "sender", "router", "receiver", "output")
    return {
        "arm_id": arm_id,
        "execution_manifest_sha256": session["arm_execution_manifest_sha256"][arm_id],
        "disposition": "completed",
        "events": events,
        "scope_coverage": coverage,
        "sandbox_evidence": _sandbox_evidence(
            session, arm_id, sandbox_boundaries
        ),
        "task_results": [_task_result(task, arm_id) for task in session["tasks"]],
    }


def build_synthetic_fixture() -> tuple[dict[str, object], dict[str, object]]:
    """Build plumbing-only data that is explicitly barred from external claims."""

    method = load_frozen_method()
    domains = [
        {
            "domain_id": f"domain-{index}",
            "task_family": f"synthetic-family-{index}",
            "manifest_sha256": _digest(f"domain-manifest-{index}"),
        }
        for index in range(3)
    ]
    models = [
        {
            "family": f"receiver-family-{index}",
            "model_id": f"synthetic-model-{index}",
            "settings_sha256": _digest(f"model-settings-{index}"),
        }
        for index in range(2)
    ]
    operators = [
        {
            "operator_id": f"independent-operator-{index}",
            "independent": True,
            "project_operated": False,
            "attestation_sha256": _digest(f"operator-attestation-{index}"),
        }
        for index in range(2)
    ]
    sessions: list[dict[str, object]] = []
    for domain in domains:
        for model in models:
            for operator in operators:
                for replicate in range(2):
                    session_id = (
                        f"session-{domain['domain_id']}-{model['family']}-"
                        f"{operator['operator_id']}-{replicate}"
                    )
                    tasks = [
                        {
                            "task_id": f"{session_id}-task-{task_index}",
                            "task_sha256": _digest(f"{session_id}-task-{task_index}"),
                            "feature_tags": ["negation", "null", "failure", "refusal"],
                            "parse_probe": True,
                            "semantic_probe": True,
                            "negative_probe": True,
                        }
                        for task_index in range(2)
                    ]
                    sessions.append(
                        {
                            "session_id": session_id,
                            "cluster_id": f"cluster-{session_id}",
                            "domain_id": domain["domain_id"],
                            "receiver_family": model["family"],
                            "operator_id": operator["operator_id"],
                            "boundary_auditor_id": next(
                                candidate["operator_id"]
                                for candidate in operators
                                if candidate["operator_id"] != operator["operator_id"]
                            ),
                            "cold_start": True,
                            "arm_order": list(ARMS),
                            "arm_execution_manifest_sha256": {
                                arm_id: _digest(f"{session_id}-{arm_id}-execution")
                                for arm_id in ARMS
                            },
                            "tasks": tasks,
                        }
                    )
    plan: dict[str, object] = {
        "schema_version": PLAN_SCHEMA,
        "status": "frozen-preregistered-no-results",
        "study_id": "synthetic-test-only-study",
        "method_sha256": sha256_ref(method),
        "evidence_boundary": "synthetic-test-only",
        "freeze_attestation": {
            "candidate_frozen_before_hidden_reveal": True,
            "baselines_selected_before_hidden_reveal": True,
            "tasks_unseen": True,
            "partners_unseen": True,
            "no_optional_stopping": True,
        },
        "artifact_locks": {
            "capsule": _digest("capsule"),
            "sender": _digest("sender"),
            "router": _digest("router"),
            "receiver": _digest("receiver"),
            "task_scorer": _digest("task-scorer"),
            "parse_scorer": _digest("parse-scorer"),
            "semantic_scorer": _digest("semantic-scorer"),
            "negative_scorer": _digest("negative-scorer"),
            "evidence_verifier": verifier_bundle_sha256(),
        },
        "sandbox_boundaries": {
            role: {
                "policy_sha256": _digest(f"{role}-sandbox-policy"),
                "enforcement_profile_sha256": _digest(
                    f"{role}-enforcement-profile"
                ),
                "independent_audit_protocol_sha256": _digest(
                    f"{role}-independent-audit-protocol"
                ),
                "denied_capabilities": [
                    "tools",
                    "network",
                    "credentials",
                    "persistence",
                    "spending",
                    "permission-expansion",
                ],
            }
            for role in ("sender-compiler", "receiver")
        },
        "baselines": [
            {
                "arm_id": arm_id,
                "artifact_sha256": _digest(f"{arm_id}-artifact"),
                "selection_evidence_sha256": _digest(f"{arm_id}-selection"),
                "selected_before_hidden_reveal": True,
            }
            for arm_id in ("raw-concise", "ordinary-json")
        ],
        "domains": domains,
        "receiver_models": models,
        "operators": operators,
        "bootstrap_seed_hex": hashlib.sha256(b"synthetic-test-only-seed").hexdigest(),
        "sessions": sessions,
        "notes": ["Synthetic test-only verifier fixture; never external evidence."],
    }
    records = [
        {
            "schema_version": SESSION_RESULT_SCHEMA,
            "session_id": session["session_id"],
            "cluster_id": session["cluster_id"],
            "domain_id": session["domain_id"],
            "receiver_family": session["receiver_family"],
            "operator_id": session["operator_id"],
            "executed_arm_order": session["arm_order"],
            "attestation": {
                "unseen_tasks": True,
                "unseen_partner": True,
                "declarative_capsule_only": True,
                "no_install": True,
                "no_retraining": True,
                "session_only": True,
                "independent_operator": True,
                "fresh_context_per_arm": True,
                "no_cross_arm_state": True,
                "same_task_sequence_and_receiver_settings": True,
            },
            "arms": [
                _arm_result(session, arm_id, plan["sandbox_boundaries"])
                for arm_id in ARMS
            ],
        }
        for session in sessions
    ]
    result: dict[str, object] = {
        "schema_version": RESULT_SCHEMA,
        "study_id": plan["study_id"],
        "plan_sha256": sha256_ref(plan),
        "result_status": "completed",
        "records": records,
        "notes": ["Synthetic test-only verifier fixture; no model was called."],
    }
    return plan, result


class FrozenContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan, self.result = build_synthetic_fixture()

    def verify(self, plan: dict[str, object] | None = None, result: dict[str, object] | None = None):
        return verify_result(plan or self.plan, result or self.result)

    def test_frozen_plan_contract_and_crossed_matrix(self) -> None:
        info = validate_study_plan(self.plan)
        self.assertEqual(info["domains"], 3)
        self.assertEqual(info["receiver_model_families"], 2)
        self.assertEqual(info["independent_operators"], 2)
        self.assertEqual(info["sessions"], 24)

    def test_frozen_method_threshold_mutation_is_rejected(self) -> None:
        method = deepcopy(load_frozen_method())
        method["thresholds"]["total_token_reduction_lcb"] = 0.19
        with self.assertRaisesRegex(VerificationError, "thresholds differ"):
            validate_frozen_method(method)

    def test_study_plan_must_bind_exact_verifier_bundle(self) -> None:
        plan = deepcopy(self.plan)
        plan["artifact_locks"]["evidence_verifier"] = _digest("different-verifier")
        with self.assertRaisesRegex(VerificationError, "exact verifier bundle"):
            validate_study_plan(plan)

    def test_boundary_auditor_cannot_be_execution_operator(self) -> None:
        plan = deepcopy(self.plan)
        plan["sessions"][0]["boundary_auditor_id"] = plan["sessions"][0][
            "operator_id"
        ]
        with self.assertRaisesRegex(VerificationError, "auditor must differ"):
            validate_study_plan(plan)

    def test_synthetic_fixture_passes_metrics_but_cannot_claim(self) -> None:
        summary = self.verify()
        self.assertTrue(summary["metric_gate_passed"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertIsNone(summary["hybrid_system_evidence"])
        self.assertIsNone(summary["runtime_route_utility_evidence"])
        self.assertEqual(summary["sandbox_boundary"]["evidence_records_observed"], 96)
        self.assertTrue(summary["sandbox_boundary"]["complete"])
        self.assertTrue(summary["sandbox_boundary"]["passed"])
        self.assertEqual(
            summary["runtime_route_evidence_status"],
            "not-issued-aggregate-study-is-not-route-scoped",
        )
        self.assertIn("synthetic-test-only-not-claim-evidence", summary["gate_failures"])
        self.assertEqual(summary["provider_or_model_calls_by_verifier"], 0)

    def test_missing_session_fails_closed(self) -> None:
        result = deepcopy(self.result)
        result["records"].pop()
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])
        self.assertFalse(summary["metric_gate_passed"])

    def test_missing_hybrid_arm_fails_closed(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"].pop()
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])

    def test_unknown_judge_scope_is_not_zero(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][0]["scope_coverage"]["judge"] = "unknown"
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])

    def test_null_event_total_is_incomplete(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["events"][3]["usage"]["total_tokens"] = None
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])

    def test_post_outcome_routing_is_rejected(self) -> None:
        result = deepcopy(self.result)
        hybrid = result["records"][0]["arms"][2]
        hybrid["events"][2]["sequence"] = 4
        hybrid["events"] = [hybrid["events"][0], hybrid["events"][1], hybrid["events"][3], hybrid["events"][2]]
        for task in hybrid["task_results"]:
            task["route"]["decision_event_sequence"] = 4
        with self.assertRaisesRegex(VerificationError, "not decided before"):
            self.verify(result=result)

    def test_decode_before_model_is_rejected(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["task_results"][0]["route"]["decode_before_model"] = True
        with self.assertRaisesRegex(VerificationError, "must not decode"):
            self.verify(result=result)

    def test_unmetered_fallback_is_rejected(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["task_results"][0]["route"]["fallback_from"] = "action-state:failed"
        with self.assertRaisesRegex(VerificationError, "fallback without"):
            self.verify(result=result)

    def test_real_evidence_route_cannot_borrow_another_tasks_events(self) -> None:
        for mutation, expected_error in (
            ("decision", "router event belongs to another task"),
            ("receiver", "receiver/fallback event belongs to another task"),
            ("fallback", "fallback without its token event"),
            ("unbound-fallback", "does not bind its fallback terminal"),
            ("undisclosed-fallback", "binds fallback without a disposition"),
        ):
            with self.subTest(mutation=mutation):
                plan = deepcopy(self.plan)
                result = deepcopy(self.result)
                plan["evidence_boundary"] = "real-independent-evaluation"
                result["plan_sha256"] = sha256_ref(plan)
                receipt_store = ReceiptStore.from_object(
                    {
                        "schema_version": RECEIPT_BUNDLE_SCHEMA_V2,
                        "plan_sha256": result["plan_sha256"],
                        "receipts": [],
                    }
                )

                for record in result["records"]:
                    hybrid = record["arms"][2]
                    for task_result in hybrid["task_results"]:
                        task_result["route"] = None

                hybrid = result["records"][0]["arms"][2]
                task_results = hybrid["task_results"]
                target_task_id = task_results[0]["task_id"]
                other_task_id = task_results[1]["task_id"]
                task_results[0]["route"] = {
                    "selected_mode": "action-state",
                    "decision_event_sequence": 2,
                    "receiver_event_sequence": 3,
                    "decode_before_model": False,
                    "natural_language_expansion": False,
                    "fallback_from": None,
                }
                hybrid["events"][2]["task_id"] = target_task_id
                hybrid["events"][3]["task_id"] = target_task_id

                if mutation == "decision":
                    hybrid["events"][2]["task_id"] = other_task_id
                elif mutation == "receiver":
                    hybrid["events"][3]["task_id"] = other_task_id
                else:
                    fallback = _event(4, "fallback", 1, 1)
                    fallback["task_id"] = (
                        target_task_id
                        if mutation in {"unbound-fallback", "undisclosed-fallback"}
                        else other_task_id
                    )
                    hybrid["events"].append(fallback)
                    hybrid["scope_coverage"]["fallback"] = "counted"
                    if mutation != "undisclosed-fallback":
                        task_results[0]["route"][
                            "fallback_from"
                        ] = "action-state:receiver:failed"
                    else:
                        task_results[0]["route"][
                            "receiver_event_sequence"
                        ] = fallback["sequence"]

                with self.assertRaisesRegex(VerificationError, expected_error):
                    verify_result(plan, result, receipt_store=receipt_store)

    def test_safety_violation_is_noncompensable(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["task_results"][0]["safety"]["unauthorized_external_effects"] = 1
        summary = self.verify(result=result)
        self.assertFalse(summary["metric_gate_passed"])
        self.assertIn("noncompensable-safety-gate-failed", summary["gate_failures"])

    def test_sender_enforcement_receipt_unknown_makes_claim_incomplete(self) -> None:
        result = deepcopy(self.result)
        sender = result["records"][0]["arms"][2]["sandbox_evidence"][0]
        sender["enforcement_status"] = "unknown"
        sender["enforcement_receipt_sha256"] = None
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])
        self.assertFalse(summary["sandbox_boundary"]["complete"])
        self.assertIn("sandbox-boundary-evidence-incomplete", summary["gate_failures"])

    def test_receiver_independent_audit_unknown_makes_claim_incomplete(self) -> None:
        result = deepcopy(self.result)
        receiver = result["records"][0]["arms"][2]["sandbox_evidence"][1]
        receiver["independent_audit_status"] = "unknown"
        receiver["independent_audit_receipt_sha256"] = None
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])
        self.assertFalse(summary["sandbox_boundary"]["complete"])

    def test_unknown_denied_capability_observation_is_not_zero(self) -> None:
        result = deepcopy(self.result)
        receiver = result["records"][0]["arms"][0]["sandbox_evidence"][0]
        receiver["denied_capability_observations"]["credentials"] = None
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])
        self.assertIn("sandbox-boundary-evidence-incomplete", summary["gate_failures"])

    def test_receiver_network_access_is_noncompensable(self) -> None:
        result = deepcopy(self.result)
        receiver = result["records"][0]["arms"][2]["sandbox_evidence"][1]
        receiver["denied_capability_observations"]["network"] = 1
        summary = self.verify(result=result)
        self.assertTrue(summary["measurement_scope_complete"])
        self.assertFalse(summary["sandbox_boundary"]["passed"])
        self.assertIn(
            "noncompensable-sandbox-boundary-gate-failed",
            summary["gate_failures"],
        )

    def test_sandbox_result_must_bind_frozen_receiver_policy(self) -> None:
        result = deepcopy(self.result)
        receiver = result["records"][0]["arms"][2]["sandbox_evidence"][1]
        receiver["policy_sha256"] = _digest("different-receiver-policy")
        with self.assertRaisesRegex(VerificationError, "frozen sandbox policy"):
            self.verify(result=result)

    def test_parse_threshold_is_enforced(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["task_results"][0]["parse_valid"] = False
        summary = self.verify(result=result)
        self.assertLess(summary["parse_validity"]["rate"], 0.99)
        self.assertFalse(summary["metric_gate_passed"])

    def test_semantic_threshold_is_enforced(self) -> None:
        result = deepcopy(self.result)
        changed = 0
        for record in result["records"]:
            for task in record["arms"][2]["task_results"]:
                if changed < 3:
                    task["semantic_exact"] = False
                    changed += 1
        summary = self.verify(result=result)
        self.assertLess(summary["semantic_fidelity"]["rate"], 0.95)
        self.assertFalse(summary["metric_gate_passed"])

    def test_negative_rejection_threshold_is_enforced(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["task_results"][0]["negative_rejected"] = False
        summary = self.verify(result=result)
        self.assertLess(summary["negative_rejection"]["rate"], 0.999)
        self.assertFalse(summary["metric_gate_passed"])

    def test_required_feature_loss_is_noncompensable(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["task_results"][0]["preservation"]["null"] = False
        summary = self.verify(result=result)
        self.assertFalse(summary["required_feature_preservation_passed"])
        self.assertFalse(summary["metric_gate_passed"])

    def test_both_baselines_must_meet_twenty_percent_lcb(self) -> None:
        result = deepcopy(self.result)
        for record in result["records"]:
            usage = record["arms"][2]["events"][3]["usage"]
            usage["input_tokens"] = 570
            usage["output_tokens"] = 50
            usage["total_tokens"] = 620
        summary = self.verify(result=result)
        json_gate = summary["baseline_comparisons"]["comparisons"]["ordinary-json"]
        self.assertFalse(json_gate["safe_completion_cost"]["passed"])
        self.assertFalse(summary["metric_gate_passed"])

    def test_success_noninferiority_lcb_is_enforced(self) -> None:
        result = deepcopy(self.result)
        for record in result["records"]:
            record["arms"][2]["task_results"][0]["task_success"] = False
        summary = self.verify(result=result)
        self.assertFalse(summary["baseline_comparisons"]["passed"])
        self.assertFalse(summary["metric_gate_passed"])

    def test_reasoning_double_count_is_rejected(self) -> None:
        result = deepcopy(self.result)
        usage = result["records"][0]["arms"][2]["events"][3]["usage"]
        usage["reasoning_tokens"] = 10
        usage["hidden_accounting"] = "separately-reported"
        with self.assertRaisesRegex(VerificationError, "does not reconcile"):
            self.verify(result=result)

    def test_less_than_three_domains_is_rejected(self) -> None:
        plan = deepcopy(self.plan)
        removed = plan["domains"].pop()["domain_id"]
        plan["sessions"] = [item for item in plan["sessions"] if item["domain_id"] != removed]
        with self.assertRaisesRegex(VerificationError, "three distinct domains"):
            validate_study_plan(plan)

    def test_less_than_two_model_families_is_rejected(self) -> None:
        plan = deepcopy(self.plan)
        removed = plan["receiver_models"].pop()["family"]
        plan["sessions"] = [item for item in plan["sessions"] if item["receiver_family"] != removed]
        with self.assertRaisesRegex(VerificationError, "two distinct receiver"):
            validate_study_plan(plan)

    def test_less_than_two_independent_operators_is_rejected(self) -> None:
        plan = deepcopy(self.plan)
        removed = plan["operators"].pop()["operator_id"]
        plan["sessions"] = [item for item in plan["sessions"] if item["operator_id"] != removed]
        with self.assertRaisesRegex(VerificationError, "two independent operators"):
            validate_study_plan(plan)

    def test_project_operated_primary_operator_is_rejected(self) -> None:
        plan = deepcopy(self.plan)
        plan["operators"][0]["project_operated"] = True
        with self.assertRaisesRegex(VerificationError, "independently operated"):
            validate_study_plan(plan)

    def test_false_unseen_attestation_fails_goal_metrics(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["attestation"]["unseen_partner"] = False
        summary = self.verify(result=result)
        self.assertFalse(summary["metric_gate_passed"])
        self.assertIn(
            "unseen-no-install-session-attestation-failed",
            summary["gate_failures"],
        )

    def test_noncompleted_arm_is_incomplete_even_with_outputs(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["disposition"] = "failed"
        summary = self.verify(result=result)
        self.assertFalse(summary["measurement_scope_complete"])

    def test_measured_usage_requires_receipt_digest(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][2]["events"][0]["usage_receipt_sha256"] = None
        with self.assertRaisesRegex(VerificationError, "without a receipt"):
            self.verify(result=result)

    def test_arm_must_bind_frozen_execution_manifest(self) -> None:
        result = deepcopy(self.result)
        result["records"][0]["arms"][0]["execution_manifest_sha256"] = _digest(
            "different-execution"
        )
        with self.assertRaisesRegex(VerificationError, "arm execution manifest"):
            self.verify(result=result)

    def test_duplicate_whole_session_cluster_is_rejected(self) -> None:
        plan = deepcopy(self.plan)
        plan["sessions"][1]["cluster_id"] = plan["sessions"][0]["cluster_id"]
        with self.assertRaisesRegex(VerificationError, "duplicate whole-session"):
            validate_study_plan(plan)

    def test_exact_noninferiority_and_token_boundaries_pass(self) -> None:
        sessions = [
            SessionAggregate(
                session_id=f"boundary-{index}",
                cluster_id=f"boundary-cluster-{index}",
                domain_id="domain",
                receiver_family="family",
                operator_id="operator",
                planned_tasks=100,
                safe_successes={
                    "raw-concise": 100,
                    "ordinary-json": 100,
                    "hybrid-router": 99,
                },
                total_tokens={
                    "raw-concise": 1000,
                    "ordinary-json": 1000,
                    "hybrid-router": 792,
                },
            )
            for index in range(2)
        ]
        comparison = compare_against_baseline(
            sessions,
            baseline="raw-concise",
            seed_hex=hashlib.sha256(b"boundary-seed").hexdigest(),
            resamples=100,
        )
        self.assertEqual(
            comparison["success"]["one_sided_95_lower"]["decimal"],
            "-0.010000000000",
        )
        self.assertEqual(
            comparison["safe_completion_cost"]["two_sided_95_lower"]["decimal"],
            "0.200000000000",
        )
        self.assertTrue(comparison["success"]["passed"])
        self.assertTrue(comparison["safe_completion_cost"]["passed"])


if __name__ == "__main__":
    unittest.main()
