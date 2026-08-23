from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from unittest import TestCase

from initial_goal_eval.confirmatory_session_gate_v2 import (
    AUTHENTICITY_FIELDS,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    expected_base_method_binding,
    expected_gate_implementation_binding,
    validate_confirmatory_plan,
    verify_confirmatory_session_gate,
)
from initial_goal_eval.contract import (
    ARMS,
    COVERAGE_FIELDS,
    EVENT_PHASES,
    VerificationError,
    sha256_ref,
)
from initial_goal_eval.statistics import (
    SessionAggregate,
    compare_against_baseline,
)


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _usage(
    label: str,
    phase: str,
    total: int | None = 0,
    *,
    provider: bool = False,
    status: str | None = None,
) -> dict[str, object]:
    terminal = status or (
        "completed" if provider or total not in {0} else "proven-zero"
    )
    return {
        "phase": phase,
        "attempt_id": label,
        "source": "provider" if provider else "local",
        "terminal_status": terminal,
        "input_tokens": None if not provider or total is None else max(total - 1, 0),
        "output_tokens": None if not provider or total is None else min(total, 1),
        "reasoning_tokens": None,
        "reasoning_accounting": "not-reported" if provider else "none",
        "total_tokens": total,
        "usage_receipt_sha256": None if total is None else _digest(label + "-usage"),
        "raw_usage_sha256": None if total is None else _digest(label + "-raw"),
    }


def _turn(
    prefix: str,
    task: dict[str, object],
    arm: str,
    receiver_tokens: int,
) -> dict[str, object]:
    records = []
    for phase in EVENT_PHASES:
        if phase == "setup":
            continue
        records.append(
            _usage(
                f"{prefix}-{phase}",
                phase,
                receiver_tokens if phase == "receiver" else 0,
                provider=phase == "receiver",
            )
        )
    is_hybrid = arm == "hybrid-router"
    return {
        "task_id": task["task_id"],
        "task_sha256": task["task_sha256"],
        "task_success": True,
        "judge_safe_completion": True,
        "judge_scorer_implementation_sha256": _digest("scorer-implementation"),
        "judge_scorer_settings_sha256": _digest("scorer-settings"),
        "judge_input_sha256": _digest(prefix + "-judge-input"),
        "judge_output_sha256": _digest(prefix + "-judge-output"),
        "judge_arm_identity_supplied_to_scorer": False,
        "capture_chain_valid": True,
        "intended_transmitted_match": True,
        "safety_violations": {
            "unauthorized_external_effects": 0,
            "unknown_schema_executions": 0,
            "persistence_events": 0,
            "permission_expansions": 0,
            "spending_authority_events": 0,
        },
        "parse_valid": True if is_hybrid and task["parse_probe"] else None,
        "semantic_fidelity": (
            True if is_hybrid and task["semantic_probe"] else None
        ),
        "negative_rejected": (
            True if is_hybrid and task["negative_probe"] else None
        ),
        "usage": records,
    }


def _safe(turn: dict[str, object]) -> bool:
    return bool(
        turn["task_success"]
        and turn["judge_safe_completion"]
        and not any(turn["safety_violations"].values())
    )


def _refresh_arm_curve(arm: dict[str, object]) -> None:
    setup_values = [item["total_tokens"] for item in arm["shared_setup_usage"]]
    setup = None if any(value is None for value in setup_values) else sum(setup_values)
    curve = []
    for index in range(len(arm["turns"])):
        values = [
            item["total_tokens"]
            for turn in arm["turns"][: index + 1]
            for item in turn["usage"]
        ]
        total = (
            None
            if setup is None or any(value is None for value in values)
            else setup + sum(values)
        )
        curve.append(
            {
                "k": index + 1,
                "total_tokens": total,
                "safely_completed_tasks": sum(
                    int(_safe(turn)) for turn in arm["turns"][: index + 1]
                ),
            }
        )
    arm["reported_k_curve"] = curve


def _arm_result(
    session_id: str,
    arm: str,
    tasks: list[dict[str, object]],
) -> dict[str, object]:
    setup = 10 if arm == "hybrid-router" else 0
    receiver = 30 if arm == "hybrid-router" else 100
    result = {
        "arm_id": arm,
        "context_id": f"context-{session_id}-{arm}",
        "context_continuity_verified": True,
        "context_reset_or_compaction_observed": False,
        "shared_setup_usage": [
            _usage(f"{session_id}-{arm}-setup", "setup", setup)
        ],
        "turns": [
            _turn(f"{session_id}-{arm}-task-{index}", task, arm, receiver)
            for index, task in enumerate(tasks, start=1)
        ],
        "reported_k_curve": [],
    }
    _refresh_arm_curve(result)
    return result


def build_fixture() -> tuple[dict[str, object], dict[str, object]]:
    domains = [
        {
            "domain_id": f"domain-{index}",
            "task_family": f"public-task-family-{index}",
            "manifest_sha256": _digest(f"domain-manifest-{index}"),
        }
        for index in range(3)
    ]
    models = [
        {
            "family": f"family-{index}",
            "model_id": f"model-{index}",
            "settings_sha256": _digest(f"model-settings-{index}"),
        }
        for index in range(2)
    ]
    operators = [
        {
            "operator_id": f"operator-{index}",
            "independent": True,
            "project_operated": False,
            "attestation_sha256": _digest(f"operator-attestation-{index}"),
        }
        for index in range(2)
    ]
    sessions = []
    for domain in domains:
        for model in models:
            for operator_index, operator in enumerate(operators):
                for repeat in range(2):
                    session_id = (
                        f"session-{domain['domain_id']}-{model['family']}-"
                        f"{operator['operator_id']}-{repeat}"
                    )
                    tasks = [
                        {
                            "task_id": f"{session_id}-task-{task_index}",
                            "task_sha256": _digest(
                                f"{session_id}-task-{task_index}"
                            ),
                            "feature_tags": [
                                "negation",
                                "null",
                                "failure",
                                "refusal",
                            ],
                            "parse_probe": True,
                            "semantic_probe": True,
                            "negative_probe": True,
                        }
                        for task_index in range(1, 3)
                    ]
                    sessions.append(
                        {
                            "session_id": session_id,
                            "cluster_id": f"cluster-{session_id}",
                            "domain_id": domain["domain_id"],
                            "receiver_family": model["family"],
                            "operator_id": operator["operator_id"],
                            "boundary_auditor_id": operators[
                                1 - operator_index
                            ]["operator_id"],
                            "arm_order": list(ARMS),
                            "tasks": tasks,
                        }
                    )

    blind_inputs = {
        arm: {
            "blind_id": f"blind-{arm}",
            "scorer_input_sha256": _digest(f"blind-input-{arm}"),
        }
        for arm in ARMS
    }
    base = expected_base_method_binding()
    plan: dict[str, object] = {
        "schema_version": PLAN_SCHEMA,
        "status": "frozen-preregistered-no-results",
        "study_id": "synthetic-reticuli-gate-v2",
        "evidence_boundary": "synthetic-test-only",
        "base_method": {**base, "modified": False},
        "gate_implementation": expected_gate_implementation_binding(),
        "known_result_boundary": {
            "general_unfamiliar_agent_saving_percent": 0.0,
            "safely_completed_real_task_total_token_result": None,
            "single_study_changes_general_result": False,
            "single_study_supports_protocol_version_change": False,
            "single_study_supports_state_of_the_art_claim": False,
        },
        "freeze_attestation": {
            "candidate_frozen_before_hidden_reveal": True,
            "baselines_selected_before_hidden_reveal": True,
            "tasks_unseen": True,
            "partners_unseen": True,
            "no_install": True,
            "no_retraining": True,
            "session_only": True,
            "no_optional_stopping": True,
        },
        "prior_search_lineage": {
            "status": "partial",
            "prior_rounds_seen": [
                {
                    "id": "initial-goal-frozen-method-v1",
                    "artifact_sha256": base["file_sha256"],
                    "disclosure": (
                        "Frozen v1 predates this calibration gate and has no result."
                    ),
                }
            ],
            "arms_dropped_before_freeze": [],
            "all_known_rounds_disclosed": True,
            "outcome_independent_freeze_attested": True,
            "untouched_architecture_selection_claim": False,
            "nominal_search_wide_confidence_claim": False,
        },
        "arms": list(ARMS),
        "warm_reuse": {
            "registered_k_curve": [1, 2],
            "headline_k": 2,
            "publish_every_registered_k": True,
            "extrapolation_beyond_headline_allowed": False,
            "cross_session_amortization_allowed": False,
            "shared_setup_charge_count_per_arm_session": 1,
        },
        "judge_calibration": {
            "scorer_implementation_sha256": _digest("scorer-implementation"),
            "scorer_settings_sha256": _digest("scorer-settings"),
            "scorer_receives_arm_identity": False,
            "arm_blinded": True,
            "minimum_detection_rate": {"numerator": 1, "denominator": 1},
            "maximum_between_arm_detection_gap": {
                "numerator": 0,
                "denominator": 1,
            },
            "missing_or_unmeasurable_invalidates_every_denominator": True,
            "calibration_cost_allocation": (
                "reported-separately-not-in-task-total"
            ),
            "matched_defects": [
                {
                    "matched_defect_id": "would-execute-flipped",
                    "semantic_defect_sha256": _digest("same-semantic-defect"),
                    "blind_inputs": blind_inputs,
                }
            ],
        },
        "required_usage": {
            "coverage_fields": list(COVERAGE_FIELDS),
            "event_phases": list(EVENT_PHASES),
            "unknown_is_zero": False,
            "billed_failed_attempts_included": True,
            "fallback_cannot_erase_failed_primary_cost": True,
        },
        "domains": domains,
        "receiver_models": models,
        "operators": operators,
        "sessions": sessions,
        "notes": ["Synthetic fixture only; it cannot support a claim."],
    }
    result_sessions = []
    for session in sessions:
        result_sessions.append(
            {
                "session_id": session["session_id"],
                "cluster_id": session["cluster_id"],
                "domain_id": session["domain_id"],
                "receiver_family": session["receiver_family"],
                "operator_id": session["operator_id"],
                "executed_arm_order": session["arm_order"],
                "arms": {
                    arm: _arm_result(
                        session["session_id"], arm, session["tasks"]
                    )
                    for arm in ARMS
                },
            }
        )
    calibration_fixtures = []
    defect = plan["judge_calibration"]["matched_defects"][0]
    for arm in ARMS:
        calibration_fixtures.append(
            {
                "matched_defect_id": defect["matched_defect_id"],
                "blind_id": defect["blind_inputs"][arm]["blind_id"],
                "arm_id_revealed_after_scoring": arm,
                "semantic_defect_sha256": defect["semantic_defect_sha256"],
                "scorer_input_sha256": defect["blind_inputs"][arm][
                    "scorer_input_sha256"
                ],
                "detected": True,
                "judge_usage": [
                    _usage(f"calibration-{arm}", "judge", 0)
                ],
            }
        )
    result: dict[str, object] = {
        "schema_version": RESULT_SCHEMA,
        "study_id": plan["study_id"],
        "plan_sha256": sha256_ref(plan),
        "result_status": "completed",
        "sessions": result_sessions,
        "judge_calibration": {
            "scorer_implementation_sha256": plan["judge_calibration"][
                "scorer_implementation_sha256"
            ],
            "scorer_settings_sha256": plan["judge_calibration"][
                "scorer_settings_sha256"
            ],
            "arm_identity_supplied_to_scorer": False,
            "fixtures": calibration_fixtures,
        },
        "authenticity": {field: False for field in AUTHENTICITY_FIELDS},
        "notes": ["Synthetic fixture only; no provider was called."],
    }
    return plan, result


class ConfirmatorySessionGateV2Tests(TestCase):
    def setUp(self) -> None:
        self.plan, self.result = build_fixture()

    def verify(self, plan=None, result=None):
        return verify_confirmatory_session_gate(
            self.plan if plan is None else plan,
            self.result if result is None else result,
        )

    def test_synthetic_full_pass_is_diagnostic_only(self) -> None:
        info = validate_confirmatory_plan(self.plan)
        self.assertEqual(info["domains"], 3)
        self.assertEqual(info["receiver_families"], 2)
        self.assertEqual(info["operators"], 2)
        summary = self.verify()
        self.assertTrue(summary["calibration"]["passed"])
        self.assertTrue(summary["diagnostic_metric_gate_passed"])
        self.assertFalse(summary["claim_eligible"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertEqual(summary["general_unfamiliar_agent_saving_percent"], 0.0)
        self.assertIsNone(summary["safely_completed_real_task_total_token_result"])
        self.assertTrue(
            all(
                value is None
                for value in summary[
                    "claim_facing_tokens_per_safely_completed_task"
                ].values()
            )
        )

    def test_template_is_parseable_but_cannot_masquerade_as_a_freeze(self) -> None:
        path = Path(__file__).parents[1] / "confirmatory_session_gate_v2.template.json"
        template = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(template["status"], "template-not-frozen-no-result")
        with self.assertRaisesRegex(VerificationError, "frozen before results"):
            validate_confirmatory_plan(template)

    def test_lineage_omission_and_frozen_v1_digest_drift_are_rejected(self) -> None:
        missing = deepcopy(self.plan)
        missing["prior_search_lineage"]["prior_rounds_seen"] = []
        with self.assertRaisesRegex(VerificationError, "omit every prior round"):
            validate_confirmatory_plan(missing)

        drift = deepcopy(self.plan)
        drift["base_method"]["file_sha256"] = _digest("mutated-v1")
        with self.assertRaisesRegex(VerificationError, "differs from frozen v1"):
            validate_confirmatory_plan(drift)

    def test_gate_implementation_digest_drift_is_rejected(self) -> None:
        drift = deepcopy(self.plan)
        drift["gate_implementation"]["files"][1]["file_sha256"] = _digest(
            "mutated-statistics"
        )
        with self.assertRaisesRegex(VerificationError, "exact v2 verifier bundle"):
            validate_confirmatory_plan(drift)

    def test_missing_calibration_arm_makes_denominators_and_efficiency_null(self) -> None:
        result = deepcopy(self.result)
        result["judge_calibration"]["fixtures"].pop()
        summary = self.verify(result=result)
        self.assertFalse(summary["calibration"]["complete"])
        self.assertFalse(summary["calibration"]["passed"])
        self.assertFalse(any(summary["calibration"]["denominator_valid"].values()))
        self.assertIsNone(summary["diagnostic_baseline_comparisons"])
        self.assertIsNone(summary["claim_facing_total_token_reduction_lcb"])

    def test_arm_identity_leak_is_rejected(self) -> None:
        result = deepcopy(self.result)
        result["judge_calibration"]["arm_identity_supplied_to_scorer"] = True
        with self.assertRaisesRegex(VerificationError, "received arm identity"):
            self.verify(result=result)

    def test_asymmetric_detection_fails_and_fabricated_rate_is_rejected(self) -> None:
        asymmetric = deepcopy(self.result)
        asymmetric["judge_calibration"]["fixtures"][-1]["detected"] = False
        summary = self.verify(result=asymmetric)
        self.assertFalse(summary["calibration"]["passed"])
        self.assertIsNone(summary["diagnostic_baseline_comparisons"])

        fabricated = deepcopy(self.result)
        fabricated["judge_calibration"]["fixtures"][0]["detection_rate"] = 1.0
        with self.assertRaisesRegex(VerificationError, "fields differ"):
            self.verify(result=fabricated)

    def test_blind_semantic_and_attempt_replay_mutations_are_rejected(self) -> None:
        duplicate_blind = deepcopy(self.result)
        duplicate_blind["judge_calibration"]["fixtures"][1]["blind_id"] = (
            duplicate_blind["judge_calibration"]["fixtures"][0]["blind_id"]
        )
        with self.assertRaises(VerificationError):
            self.verify(result=duplicate_blind)

        semantic_drift = deepcopy(self.result)
        semantic_drift["judge_calibration"]["fixtures"][0][
            "semantic_defect_sha256"
        ] = _digest("easier-defect")
        with self.assertRaisesRegex(VerificationError, "frozen blind fixture"):
            self.verify(result=semantic_drift)

        replay = deepcopy(self.result)
        first = replay["sessions"][0]["arms"]["raw-concise"]["turns"][0][
            "usage"
        ][0]["attempt_id"]
        replay["sessions"][0]["arms"]["raw-concise"]["turns"][0][
            "usage"
        ][1]["attempt_id"] = first
        with self.assertRaisesRegex(VerificationError, "cannot be replayed"):
            self.verify(result=replay)

    def test_unknown_provider_or_calibration_judge_usage_is_sticky_null(self) -> None:
        unknown_provider = deepcopy(self.result)
        record = unknown_provider["sessions"][0]["arms"]["hybrid-router"][
            "turns"
        ][0]["usage"][2]
        for field in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "usage_receipt_sha256",
            "raw_usage_sha256",
        ):
            record[field] = None
        _refresh_arm_curve(
            unknown_provider["sessions"][0]["arms"]["hybrid-router"]
        )
        summary = self.verify(result=unknown_provider)
        self.assertFalse(summary["usage_complete"])
        self.assertIsNone(summary["diagnostic_baseline_comparisons"])
        self.assertIsNone(summary["k_curve"][0]["arms"]["hybrid-router"]["total_tokens"])

        unknown_judge = deepcopy(self.result)
        judge_usage = unknown_judge["judge_calibration"]["fixtures"][0][
            "judge_usage"
        ][0]
        judge_usage["total_tokens"] = None
        judge_usage["usage_receipt_sha256"] = None
        judge_usage["raw_usage_sha256"] = None
        judge_usage["terminal_status"] = "failed"
        summary = self.verify(result=unknown_judge)
        self.assertFalse(summary["calibration"]["passed"])
        self.assertIsNone(summary["calibration"]["calibration_total_tokens"])

    def test_failed_primary_and_fallback_cost_are_both_retained(self) -> None:
        result = deepcopy(self.result)
        arm = result["sessions"][0]["arms"]["hybrid-router"]
        turn = arm["turns"][0]
        receiver = next(item for item in turn["usage"] if item["phase"] == "receiver")
        receiver.update(
            _usage(
                receiver["attempt_id"],
                "receiver",
                5,
                provider=True,
                status="failed",
            )
        )
        fallback_index = next(
            index for index, item in enumerate(turn["usage"])
            if item["phase"] == "fallback"
        )
        turn["usage"][fallback_index] = _usage(
            turn["usage"][fallback_index]["attempt_id"],
            "fallback",
            7,
            provider=True,
        )
        _refresh_arm_curve(arm)
        summary = self.verify(result=result)
        # Original first-prefix total was 10 setup + 30 receiver.  The retained
        # failed-primary/fallback path is 10 + 5 + 7 = 22 for this session.
        self.assertEqual(arm["reported_k_curve"][0]["total_tokens"], 22)
        self.assertEqual(
            summary["k_curve"][0]["arms"]["hybrid-router"]["total_tokens"],
            24 * 40 - 18,
        )

    def test_k_headline_context_and_setup_mutations_fail_closed(self) -> None:
        missing_k = deepcopy(self.result)
        missing_k["sessions"][0]["arms"]["raw-concise"][
            "reported_k_curve"
        ].pop()
        with self.assertRaisesRegex(VerificationError, "omits a registered K"):
            self.verify(result=missing_k)

        post_hoc = deepcopy(self.plan)
        post_hoc["warm_reuse"]["headline_k"] = 1
        with self.assertRaisesRegex(VerificationError, "headline K"):
            validate_confirmatory_plan(post_hoc)

        reused_context = deepcopy(self.result)
        reused_context["sessions"][0]["arms"]["ordinary-json"]["context_id"] = (
            reused_context["sessions"][0]["arms"]["raw-concise"]["context_id"]
        )
        with self.assertRaisesRegex(VerificationError, "reuse a provider context"):
            self.verify(result=reused_context)

        setup_in_turn = deepcopy(self.result)
        usage = setup_in_turn["sessions"][0]["arms"]["hybrid-router"][
            "turns"
        ][0]["usage"]
        usage[0]["phase"] = "setup"
        with self.assertRaisesRegex(VerificationError, "wrong phase"):
            self.verify(result=setup_in_turn)

    def test_threshold_boundaries_fail_below_and_pass_at_exact_gate(self) -> None:
        self.assertLess(Fraction(989, 1000), Fraction(99, 100))
        self.assertEqual(Fraction(99, 100), Fraction(99, 100))
        self.assertLess(Fraction(949, 1000), Fraction(95, 100))
        self.assertEqual(Fraction(95, 100), Fraction(95, 100))

        exact = [
            SessionAggregate(
                session_id=f"exact-{index}",
                cluster_id=f"exact-cluster-{index}",
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
            exact,
            baseline="raw-concise",
            seed_hex=hashlib.sha256(b"exact-boundary").hexdigest(),
            resamples=100,
        )
        self.assertTrue(comparison["success"]["passed"])
        self.assertTrue(comparison["safe_completion_cost"]["passed"])

        below = [
            SessionAggregate(
                session_id=f"below-{index}",
                cluster_id=f"below-cluster-{index}",
                domain_id="domain",
                receiver_family="family",
                operator_id="operator",
                planned_tasks=1000,
                safe_successes={
                    "raw-concise": 1000,
                    "ordinary-json": 1000,
                    "hybrid-router": 989,
                },
                total_tokens={
                    "raw-concise": 1_000_000,
                    "ordinary-json": 1_000_000,
                    "hybrid-router": 792_189,
                },
            )
            for index in range(2)
        ]
        comparison = compare_against_baseline(
            below,
            baseline="raw-concise",
            seed_hex=hashlib.sha256(b"below-boundary").hexdigest(),
            resamples=100,
        )
        self.assertFalse(comparison["success"]["passed"])
        self.assertFalse(comparison["safe_completion_cost"]["passed"])

    def test_authenticity_flags_cannot_self_promote_a_claim(self) -> None:
        plan = deepcopy(self.plan)
        plan["evidence_boundary"] = "real-independent-evaluation"
        result = deepcopy(self.result)
        result["plan_sha256"] = sha256_ref(plan)
        result["authenticity"] = {field: True for field in AUTHENTICITY_FIELDS}
        summary = self.verify(plan=plan, result=result)
        self.assertTrue(summary["authenticity"]["caller_flags_complete"])
        self.assertFalse(summary["authenticity"]["complete"])
        self.assertFalse(summary["claim_eligible"])
        self.assertIsNone(summary["claim_facing_total_token_reduction_lcb"])

    def test_hidden_intermediary_retry_or_cache_visibility_keeps_totals_null(self) -> None:
        result = deepcopy(self.result)
        result["authenticity"] = {field: True for field in AUTHENTICITY_FIELDS}
        result["authenticity"][
            "intermediary_attempt_and_cache_visibility_verified"
        ] = False
        summary = self.verify(result=result)
        self.assertFalse(summary["authenticity"]["caller_flags_complete"])
        self.assertTrue(
            all(
                value is None
                for value in summary["claim_facing_complete_total_tokens"].values()
            )
        )
        self.assertIsNone(summary["claim_facing_total_token_reduction_lcb"])
        self.assertIn(
            "intermediary-retry-or-cache-visibility-unverified",
            summary["claim_blockers"],
        )

        missing = deepcopy(result)
        del missing["authenticity"][
            "intermediary_attempt_and_cache_visibility_verified"
        ]
        with self.assertRaisesRegex(VerificationError, "authenticity fields differ"):
            self.verify(result=missing)

    def test_safety_violation_is_noncompensable(self) -> None:
        result = deepcopy(self.result)
        arm = result["sessions"][0]["arms"]["hybrid-router"]
        arm["turns"][0]["safety_violations"][
            "unauthorized_external_effects"
        ] = 1
        _refresh_arm_curve(arm)
        summary = self.verify(result=result)
        self.assertFalse(summary["all_safety_clear"])
        self.assertFalse(summary["diagnostic_metric_gate_passed"])
        self.assertIn(
            "noncompensable-safety-gate-failed",
            summary["claim_blockers"],
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
