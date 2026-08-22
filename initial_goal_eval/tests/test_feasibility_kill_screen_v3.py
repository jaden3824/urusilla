"""Regression tests for corrected finite-bound labels and arithmetic binding."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import sha256_ref
from initial_goal_eval.feasibility_kill_screen_v1 import (
    EXACT_ASSUMPTIONS_SHA256,
    PATHS,
    PHASES,
    PLAN_STATUS,
    SESSION_LENGTHS,
    TARGET_REDUCTION_BASIS_POINTS,
)
from initial_goal_eval.feasibility_kill_screen_v3 import (
    EVALUATION_REFERENCE,
    FEASIBILITY_PLAN_SCHEMA,
    FEASIBILITY_RESULT_SCHEMA,
    run_feasibility_kill_screen,
)


def _digest(label: str) -> str:
    return sha256_ref({"v3-test": label})


def _vector(value: int) -> list[int]:
    return [value for _ in SESSION_LENGTHS]


def _linear(value: int) -> list[int]:
    return [value * n for n in SESSION_LENGTHS]


def _path(path_name: str) -> dict[str, object]:
    candidate = path_name == "action-state"
    vectors = {
        "setup": _vector(5) if candidate else _vector(0),
        "comprehension": _vector(7) if candidate else _vector(0),
        "primary": _linear(1 if candidate else (20 if path_name == "raw-concise" else 15)),
        # A real conditional candidate repair can have a sound lower bound of
        # zero without being absent from the registered execution graph.
        "repair": _vector(0),
    }
    phases = []
    for phase in PHASES:
        vector = vectors.get(phase, _vector(0))
        if candidate:
            kind = (
                "derived-lower-bound"
                if phase in {"setup", "comprehension", "primary", "repair"}
                else "proved-absent"
            )
        else:
            kind = "derived-upper-bound" if any(vector) else "proved-absent"
        phases.append(
            {"phase": phase, "bound_kind": kind, "tokens_by_n": vector}
        )
    return {
        "bound_direction": "lower" if candidate else "upper",
        "success_direction": "maximum" if candidate else "minimum",
        "safe_successes_by_n": list(SESSION_LENGTHS),
        "phases": phases,
    }


def _plan() -> dict[str, object]:
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
            "source_prompt_bundle_sha256": _digest("prompts"),
            "path_enumerator_sha256": _digest("paths"),
            "tokenizer_registry_sha256": _digest("tokenizers"),
            "all_dynamic_slots_finitely_bounded": True,
            "all_allowed_paths_enumerated": True,
            "inclusive_phase_partition_complete": True,
            "all_billed_reasoning_and_outputs_included": True,
            "all_retries_repairs_fallbacks_and_judges_included": True,
        },
        "rows": [
            {
                "domain_id": "domain-a",
                "domain_manifest_sha256": _digest("domain"),
                "tokenizer_id": "tokenizer-a",
                "tokenizer_sha256": _digest("tokenizer"),
                "bound_manifest_sha256": _digest("bounds"),
                "paths": {name: _path(name) for name in PATHS},
            }
        ],
    }


class FeasibilityKillScreenV3Tests(unittest.TestCase):
    def test_zero_conditional_candidate_lower_bound_is_not_called_absent(self) -> None:
        plan = _plan()
        result = run_feasibility_kill_screen(plan)

        self.assertEqual(result["schema_version"], FEASIBILITY_RESULT_SCHEMA)
        self.assertEqual(result["outcome"], "not-disproven")
        self.assertEqual(result["plan_sha256"], sha256_ref(plan))
        self.assertFalse(result["claim_eligible"])
        self.assertEqual(result["provider_calls_performed"], 0)
        self.assertEqual(result["model_calls_performed"], 0)
        self.assertEqual(
            result["assumptions"]["legacy_arithmetic_contract_sha256"],
            EXACT_ASSUMPTIONS_SHA256,
        )
        self.assertEqual(
            result["assumptions"]["legacy_arithmetic_contract"]["bound_truth"],
            "conditional-on-caller-registered-digests-and-completeness-assertions",
        )
        self.assertEqual(
            result["rows"][0]["path_bounds_sha256"]["action-state"],
            sha256_ref(plan["rows"][0]["paths"]["action-state"]),
        )

    def test_false_absence_and_wrong_bound_directions_fail_closed(self) -> None:
        mutations = []
        nonzero_absent = deepcopy(_plan())
        nonzero_absent["rows"][0]["paths"]["action-state"]["phases"][0][
            "bound_kind"
        ] = "proved-absent"
        mutations.append(nonzero_absent)
        baseline_zero_lower = deepcopy(_plan())
        baseline_zero_lower["rows"][0]["paths"]["raw-concise"]["phases"][0][
            "bound_kind"
        ] = "derived-upper-bound"
        mutations.append(baseline_zero_lower)
        legacy = deepcopy(_plan())
        legacy["schema_version"] = (
            "urusilla-initial-goal-feasibility-kill-screen-plan/2"
        )
        mutations.append(legacy)

        for plan in mutations:
            with self.subTest(plan=plan["schema_version"]):
                result = run_feasibility_kill_screen(plan)
                self.assertEqual(result["outcome"], "invalid")
                self.assertIsNone(result["plan_sha256"])
                self.assertFalse(result["claim_eligible"])

    def test_bool_token_and_duplicate_row_fail_before_arithmetic_release(self) -> None:
        bad_bool = deepcopy(_plan())
        bad_bool["rows"][0]["paths"]["action-state"]["phases"][0][
            "tokens_by_n"
        ][0] = True
        duplicate = deepcopy(_plan())
        duplicate["rows"].append(deepcopy(duplicate["rows"][0]))

        for plan in (bad_bool, duplicate):
            result = run_feasibility_kill_screen(plan)
            self.assertEqual(result["outcome"], "invalid")
            self.assertEqual(result["rows"], [])


if __name__ == "__main__":
    unittest.main()
