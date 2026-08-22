"""Focused tests for the deterministic action-state feasibility screen v1."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from initial_goal_eval.contract import sha256_ref
from initial_goal_eval.feasibility_kill_screen_v1 import (
    EXACT_ASSUMPTIONS_SHA256,
    FEASIBILITY_PLAN_SCHEMA,
    FEASIBILITY_RESULT_SCHEMA,
    NO_POSITIVE_BASELINE_SUCCESS_REASON,
    OUTCOMES,
    PATHS,
    PHASES,
    EVALUATION_REFERENCE,
    PLAN_STATUS,
    SESSION_LENGTHS,
    TARGET_REDUCTION_BASIS_POINTS,
    run_feasibility_kill_screen,
)


def _digest(label: str) -> str:
    return sha256_ref({"feasibility-kill-screen-v1-test": label})


def _constant(value: int) -> list[int]:
    return [value for _ in SESSION_LENGTHS]


def _linear(per_task: int, once: int = 0) -> list[int]:
    return [once + per_task * session_length for session_length in SESSION_LENGTHS]


def _phase(
    *,
    phase: str,
    vector: list[int],
    candidate: bool,
) -> dict[str, object]:
    if all(item == 0 for item in vector):
        kind = "proved-zero"
    else:
        kind = "proved-lower-bound" if candidate else "proved-upper-bound"
    return {"phase": phase, "bound_kind": kind, "tokens_by_n": vector}


def _path(
    path_name: str,
    phase_vectors: dict[str, list[int]],
    *,
    safe_successes: list[int] | None = None,
) -> dict[str, object]:
    candidate = path_name == "action-state"
    return {
        "bound_direction": "lower" if candidate else "upper",
        "success_direction": "maximum" if candidate else "minimum",
        "safe_successes_by_n": (
            list(SESSION_LENGTHS) if safe_successes is None else safe_successes
        ),
        "phases": [
            _phase(
                phase=phase,
                vector=phase_vectors.get(phase, _constant(0)),
                candidate=candidate,
            )
            for phase in PHASES
        ],
    }


def _row(
    domain_id: str = "sgd-hotels",
    tokenizer_id: str = "qwen-tokenizer",
    *,
    candidate_once: int = 80,
    candidate_per_task: int = 4,
    raw_per_task: int = 20,
    json_per_task: int = 15,
    raw_safe_successes: list[int] | None = None,
    json_safe_successes: list[int] | None = None,
) -> dict[str, object]:
    # The candidate one-time bound is deliberately partitioned across the
    # two endpoint obligations whose omission would make the screen unsound.
    setup = candidate_once // 2
    comprehension = candidate_once - setup
    paths = {
        "action-state": _path(
            "action-state",
            {
                "setup": _constant(setup),
                "comprehension": _constant(comprehension),
                "primary": _linear(candidate_per_task),
            },
        ),
        "raw-concise": _path(
            "raw-concise",
            {"primary": _linear(raw_per_task)},
            safe_successes=raw_safe_successes,
        ),
        "ordinary-json": _path(
            "ordinary-json",
            {"primary": _linear(json_per_task)},
            safe_successes=json_safe_successes,
        ),
    }
    assert tuple(paths) == PATHS
    return {
        "domain_id": domain_id,
        "domain_manifest_sha256": _digest(f"domain-{domain_id}"),
        "tokenizer_id": tokenizer_id,
        "tokenizer_sha256": _digest(f"tokenizer-{tokenizer_id}"),
        "bound_manifest_sha256": _digest(f"bounds-{domain_id}-{tokenizer_id}"),
        "paths": paths,
    }


def _plan(rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": FEASIBILITY_PLAN_SCHEMA,
        "evaluation_id": EVALUATION_REFERENCE,
        "status": PLAN_STATUS,
        "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
        "session_lengths": list(SESSION_LENGTHS),
        "registration": {
            "bounds_frozen_before_screen": True,
            "provider_calls_performed": 0,
            "model_calls_performed": 0,
            "source_prompt_bundle_sha256": _digest("source-prompt-bundle"),
            "path_enumerator_sha256": _digest("path-enumerator"),
            "tokenizer_registry_sha256": _digest("tokenizer-registry"),
            "all_dynamic_slots_finitely_bounded": True,
            "all_allowed_paths_enumerated": True,
            "inclusive_phase_partition_complete": True,
            "all_billed_reasoning_and_outputs_included": True,
            "all_retries_repairs_fallbacks_and_judges_included": True,
        },
        "rows": [_row()] if rows is None else rows,
    }


def _outcome_values(value: object) -> set[str]:
    found: set[str] = set()
    if type(value) is dict:
        for key, item in value.items():
            if key == "outcome":
                found.add(item)
            found.update(_outcome_values(item))
    elif type(value) is list:
        for item in value:
            found.update(_outcome_values(item))
    return found


class FeasibilityKillScreenV1Tests(unittest.TestCase):
    def test_strict_boundary_is_impossible_then_not_disproven(self) -> None:
        result = run_feasibility_kill_screen(_plan())

        self.assertEqual(result["schema_version"], FEASIBILITY_RESULT_SCHEMA)
        self.assertEqual(result["outcome"], "not-disproven")
        self.assertEqual(result["assumptions_sha256"], EXACT_ASSUMPTIONS_SHA256)
        self.assertFalse(result["claim_eligible"])
        self.assertEqual(result["provider_calls_performed"], 0)
        self.assertEqual(result["model_calls_performed"], 0)

        sessions = result["rows"][0]["sessions"]
        self.assertEqual(
            [item["session_length"] for item in sessions], list(SESSION_LENGTHS)
        )
        self.assertTrue(all(item["outcome"] == "impossible" for item in sessions[:9]))
        # At N=10, candidate lower bound is 120 and the better JSON upper
        # bound is 150.  Equality with 80% is deliberately not a kill.
        self.assertEqual(sessions[9]["candidate_lower_total_tokens"], 120)
        self.assertEqual(sessions[9]["comparison_upper_total_tokens"], 150)
        self.assertEqual(sessions[9]["kill_left_scaled"], sessions[9]["kill_right_scaled"])
        self.assertEqual(sessions[9]["outcome"], "not-disproven")
        self.assertTrue(
            all(item["outcome"] == "not-disproven" for item in sessions[9:])
        )

    def test_better_raw_json_comparison_uses_tokens_per_safe_task(self) -> None:
        raw_min_successes = [max(1, n // 2) for n in SESSION_LENGTHS]
        row = _row(
            raw_per_task=10,
            json_per_task=15,
            raw_safe_successes=raw_min_successes,
        )
        result = run_feasibility_kill_screen(_plan([row]))
        sessions = result["rows"][0]["sessions"]

        self.assertEqual(sessions[0]["comparison_bound_source"], "raw-concise")
        # At N=10, raw has fewer total tokens (100 versus 150) but only five
        # guaranteed safe successes.  Its upper cost is therefore 20/task,
        # and the JSON upper cost of 15/task is the better comparison bound.
        self.assertEqual(sessions[9]["raw_min_safe_successes"], 5)
        self.assertEqual(
            sessions[9]["comparison_bound_source"], "ordinary-json"
        )

    def test_all_zero_baseline_success_bounds_are_explicitly_unbounded(self) -> None:
        zero = _constant(0)
        row = _row(
            candidate_once=10_000,
            candidate_per_task=10_000,
            raw_safe_successes=zero,
            json_safe_successes=zero,
        )

        result = run_feasibility_kill_screen(_plan([row]))

        self.assertEqual(result["outcome"], "not-disproven")
        self.assertEqual(result["rows"][0]["outcome"], "not-disproven")
        for session in result["rows"][0]["sessions"]:
            self.assertEqual(session["outcome"], "not-disproven")
            self.assertEqual(session["raw_min_safe_successes"], 0)
            self.assertEqual(session["json_min_safe_successes"], 0)
            self.assertIsNone(session["comparison_bound_source"])
            self.assertEqual(
                session["comparison_unavailable_reason"],
                NO_POSITIVE_BASELINE_SUCCESS_REASON,
            )
            self.assertIsNone(session["comparison_upper_total_tokens"])
            self.assertIsNone(session["comparison_min_safe_successes"])
            self.assertIsNone(session["kill_left_scaled"])
            self.assertIsNone(session["kill_right_scaled"])

    def test_one_zero_baseline_selects_the_other_finite_bound(self) -> None:
        cases = (
            (_constant(0), list(SESSION_LENGTHS), "ordinary-json"),
            (list(SESSION_LENGTHS), _constant(0), "raw-concise"),
        )
        for raw_successes, json_successes, expected_source in cases:
            with self.subTest(expected_source=expected_source):
                row = _row(
                    candidate_once=10_000,
                    raw_safe_successes=raw_successes,
                    json_safe_successes=json_successes,
                )
                result = run_feasibility_kill_screen(_plan([row]))

                self.assertNotEqual(result["outcome"], "invalid")
                for session in result["rows"][0]["sessions"]:
                    self.assertEqual(
                        session["comparison_bound_source"], expected_source
                    )
                    self.assertIsNone(session["comparison_unavailable_reason"])
                    self.assertIsNotNone(session["comparison_upper_total_tokens"])
                    self.assertIsNotNone(session["comparison_min_safe_successes"])
                    self.assertIsNotNone(session["kill_left_scaled"])
                    self.assertIsNotNone(session["kill_right_scaled"])

    def test_zero_to_positive_nondecreasing_bounds_become_comparable(self) -> None:
        raw_successes = [0 if n < 5 else 1 for n in SESSION_LENGTHS]
        json_successes = [0 if n < 8 else 2 for n in SESSION_LENGTHS]
        row = _row(
            candidate_once=10_000,
            raw_safe_successes=raw_successes,
            json_safe_successes=json_successes,
        )

        result = run_feasibility_kill_screen(_plan([row]))
        sessions = result["rows"][0]["sessions"]

        self.assertNotEqual(result["outcome"], "invalid")
        self.assertTrue(
            all(item["outcome"] == "not-disproven" for item in sessions[:4])
        )
        self.assertTrue(
            all(
                item["comparison_unavailable_reason"]
                == NO_POSITIVE_BASELINE_SUCCESS_REASON
                for item in sessions[:4]
            )
        )
        self.assertTrue(
            all(
                item["comparison_bound_source"] == "raw-concise"
                for item in sessions[4:7]
            )
        )
        self.assertTrue(
            all(item["comparison_unavailable_reason"] is None for item in sessions[4:])
        )

    def test_baseline_success_bounds_reject_negative_over_n_and_decrease(self) -> None:
        for mutation in ("negative", "over-n", "decreasing"):
            with self.subTest(mutation=mutation):
                plan = _plan()
                vector = plan["rows"][0]["paths"]["raw-concise"][
                    "safe_successes_by_n"
                ]
                if mutation == "negative":
                    vector[0] = -1
                elif mutation == "over-n":
                    vector[0] = 2
                else:
                    vector[2] = 1
                result = run_feasibility_kill_screen(plan)
                self.assertEqual(result["outcome"], "invalid")

    def test_per_domain_and_tokenizer_rows_are_retained(self) -> None:
        rows = [
            _row("sgd-hotels", "qwen-tokenizer"),
            _row("sgd-flights", "mistral-tokenizer", candidate_once=96),
        ]
        result = run_feasibility_kill_screen(_plan(rows))

        self.assertEqual(
            [
                (item["domain_id"], item["tokenizer_id"])
                for item in result["rows"]
            ],
            [
                ("sgd-hotels", "qwen-tokenizer"),
                ("sgd-flights", "mistral-tokenizer"),
            ],
        )
        for expected, observed in zip(rows, result["rows"]):
            self.assertEqual(
                observed["bound_manifest_sha256"],
                expected["bound_manifest_sha256"],
            )
            self.assertEqual(set(observed["path_bounds_sha256"]), set(PATHS))

    def test_overall_impossible_requires_every_row_and_session_to_be_killed(self) -> None:
        rows = [
            _row("domain-a", "tokenizer-a", candidate_once=2_000, candidate_per_task=4),
            _row("domain-b", "tokenizer-b", candidate_once=3_000, candidate_per_task=2),
        ]
        result = run_feasibility_kill_screen(_plan(rows))

        self.assertEqual(result["outcome"], "impossible")
        self.assertTrue(all(row["outcome"] == "impossible" for row in result["rows"]))
        self.assertTrue(
            all(
                session["outcome"] == "impossible"
                for row in result["rows"]
                for session in row["sessions"]
            )
        )

    def test_unknown_or_unbounded_token_input_fails_closed(self) -> None:
        for mutation in ("none", "negative", "short", "decreasing"):
            with self.subTest(mutation=mutation):
                plan = _plan()
                vector = plan["rows"][0]["paths"]["action-state"]["phases"][0][
                    "tokens_by_n"
                ]
                if mutation == "none":
                    vector[0] = None
                elif mutation == "negative":
                    vector[0] = -1
                elif mutation == "short":
                    vector.pop()
                else:
                    vector[1] = vector[0] - 1
                result = run_feasibility_kill_screen(plan)
                self.assertEqual(result["outcome"], "invalid")
                self.assertEqual(result["rows"], [])
                self.assertFalse(result["claim_eligible"])

    def test_endpoint_obligations_cannot_be_zeroed(self) -> None:
        for obligation in ("setup", "comprehension"):
            with self.subTest(obligation=obligation):
                plan = _plan()
                phase = next(
                    item
                    for item in plan["rows"][0]["paths"]["action-state"]["phases"]
                    if item["phase"] == obligation
                )
                phase["tokens_by_n"] = _constant(0)
                phase["bound_kind"] = "proved-zero"
                result = run_feasibility_kill_screen(plan)
                self.assertEqual(result["outcome"], "invalid")
                self.assertIn(
                    "mandatory-candidate-obligation",
                    result["error"],
                )

    def test_causal_study_cost_may_be_proved_zero_for_endpoint_screen(self) -> None:
        plan = _plan()
        causal = next(
            item
            for item in plan["rows"][0]["paths"]["action-state"]["phases"]
            if item["phase"] == "causal"
        )

        self.assertEqual(causal["bound_kind"], "proved-zero")
        result = run_feasibility_kill_screen(plan)
        self.assertNotEqual(result["outcome"], "invalid")

    def test_unknown_success_denominator_fails_closed(self) -> None:
        plan = _plan()
        plan["rows"][0]["paths"]["raw-concise"]["safe_successes_by_n"][4] = None
        self.assertEqual(run_feasibility_kill_screen(plan)["outcome"], "invalid")

        plan = _plan()
        plan["rows"][0]["paths"]["action-state"]["safe_successes_by_n"][1] = 1
        result = run_feasibility_kill_screen(plan)
        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("candidate-maximum-must-equal-N", result["error"])

    def test_action_state_zero_success_is_rejected(self) -> None:
        plan = _plan()
        plan["rows"][0]["paths"]["action-state"]["safe_successes_by_n"][0] = 0

        result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("candidate-maximum-must-equal-N", result["error"])

    def test_incomplete_registration_fails_closed(self) -> None:
        for field, value in (
            ("bounds_frozen_before_screen", False),
            ("provider_calls_performed", 1),
            ("all_allowed_paths_enumerated", False),
            ("inclusive_phase_partition_complete", None),
            ("all_billed_reasoning_and_outputs_included", False),
            ("all_retries_repairs_fallbacks_and_judges_included", None),
        ):
            with self.subTest(field=field):
                plan = _plan()
                plan["registration"][field] = value
                result = run_feasibility_kill_screen(plan)
                self.assertEqual(result["outcome"], "invalid")
                self.assertIsNone(result["registration_sha256"])

    def test_evaluation_reference_cannot_be_relabelled(self) -> None:
        plan = _plan()
        plan["evaluation_id"] = "different-evaluation/1"

        result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("must-match-frozen-evaluation-reference", result["error"])

    def test_session_lengths_require_exact_integer_types(self) -> None:
        plan = _plan()
        plan["session_lengths"][0] = True

        result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("must-be-exact-1..128", result["error"])

    def test_row_count_is_resource_bounded_before_row_expansion(self) -> None:
        plan = _plan([_row()] * 129)

        result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("must-have-1..128-entries", result["error"])

    def test_resource_rejected_plan_is_not_rehashed(self) -> None:
        plan = _plan([_row()] * 129)

        with patch(
            "initial_goal_eval.feasibility_kill_screen_v1.sha256_ref",
            side_effect=AssertionError("rejected plan must not be rehashed"),
        ):
            result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["outcome"], "invalid")
        self.assertIsNone(result["plan_sha256"])

    def test_unknown_phase_extra_key_and_duplicate_row_fail_closed(self) -> None:
        plan = _plan()
        plan["rows"][0]["paths"]["ordinary-json"]["phases"][3]["phase"] = "unknown"
        self.assertEqual(run_feasibility_kill_screen(plan)["outcome"], "invalid")

        plan = _plan()
        plan["unexpected"] = True
        self.assertEqual(run_feasibility_kill_screen(plan)["outcome"], "invalid")

        duplicate = _row()
        result = run_feasibility_kill_screen(_plan([_row(), duplicate]))
        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("duplicate-domain-tokenizer-row", result["error"])

        plan = _plan()
        plan[7] = "non-string-key"
        result = run_feasibility_kill_screen(plan)
        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("string-keys-required", result["error"])

    def test_only_closed_world_outcome_vocabulary_is_emitted(self) -> None:
        valid = run_feasibility_kill_screen(_plan())
        invalid = run_feasibility_kill_screen(None)

        self.assertLessEqual(_outcome_values(valid), set(OUTCOMES))
        self.assertLessEqual(_outcome_values(invalid), set(OUTCOMES))
        self.assertNotIn("reduction", valid)
        self.assertNotIn("saving", valid)
        self.assertFalse(valid["claim_eligible"])
        self.assertFalse(invalid["claim_eligible"])

    def test_legacy_v1_plan_is_rejected_after_zero_denominator_correction(self) -> None:
        plan = _plan()
        plan["schema_version"] = (
            "urusilla-initial-goal-feasibility-kill-screen-plan/1"
        )

        result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["outcome"], "invalid")
        self.assertEqual(result["schema_version"], FEASIBILITY_RESULT_SCHEMA)

    def test_plan_digest_binds_every_explicit_phase_vector(self) -> None:
        plan = _plan()
        first = run_feasibility_kill_screen(plan)
        changed = deepcopy(plan)
        changed["rows"][0]["paths"]["raw-concise"]["phases"][5][
            "tokens_by_n"
        ][20] += 1
        second = run_feasibility_kill_screen(changed)

        self.assertNotEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertNotEqual(
            first["rows"][0]["path_bounds_sha256"]["raw-concise"],
            second["rows"][0]["path_bounds_sha256"]["raw-concise"],
        )

    def test_zero_success_vectors_are_deterministic_and_digest_bound(self) -> None:
        raw_successes = [0 if n < 65 else 1 for n in SESSION_LENGTHS]
        plan = _plan([_row(raw_safe_successes=raw_successes)])

        first = run_feasibility_kill_screen(deepcopy(plan))
        repeated = run_feasibility_kill_screen(deepcopy(plan))
        changed = deepcopy(plan)
        changed["rows"][0]["paths"]["raw-concise"]["safe_successes_by_n"][
            63
        ] = 1
        second = run_feasibility_kill_screen(changed)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertNotEqual(
            first["rows"][0]["path_bounds_sha256"]["raw-concise"],
            second["rows"][0]["path_bounds_sha256"]["raw-concise"],
        )


if __name__ == "__main__":
    unittest.main()
