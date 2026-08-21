from __future__ import annotations

import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from interop_lab.validate_result import (
    DEFAULT_RESULT,
    TOKEN_PHASES,
    ValidationError,
    load_json,
    main,
    strict_json_loads,
    validate_result,
)


def _tokens(total: int | None) -> dict[str, int | None]:
    if total is None:
        return {phase: None for phase in (*TOKEN_PHASES, "total")}
    result: dict[str, int | None] = {phase: 0 for phase in TOKEN_PHASES}
    result["receiver"] = total
    result["total"] = total
    return result


def _arm(arm_id: str, total: int | None) -> dict[str, object]:
    known = total is not None
    return {
        "arm_id": arm_id,
        "safe_completion": True if known else None,
        "task_success": True if known else None,
        "parse_valid": True if known else None,
        "semantic_fidelity": True if known else None,
        "failure_reason": None,
        "tokens": _tokens(total),
    }


class ResultValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = load_json(DEFAULT_RESULT)

    def _matched(self, *, complete: bool, claim: bool = False) -> dict[str, object]:
        result = copy.deepcopy(self.result)
        result["result_id"] = "synthetic-test-only-matched"
        result["track"] = "matched_eval"
        result["outcome"]["kind"] = "exact" if complete else "null"
        result["outcome"]["summary"] = "Synthetic test-only validator fixture."
        totals = (100, 90, 60) if complete else (None, None, None)
        result["token_accounting"] = {
            "status": "complete" if complete else "not-measured",
            "arms": [
                _arm("raw", totals[0]),
                _arm("json", totals[1]),
                _arm("urusilla", totals[2]),
            ],
        }
        if claim:
            result["artifact_evidence"].update(
                {
                    "agent_entry_sha256": "sha256:" + "1" * 64,
                    "verified_artifact_ids": [
                        "grammar_capsule",
                        "matched_eval_card",
                        "matched_eval_record",
                        "matched_eval_schema",
                        "matched_eval_validator",
                    ],
                }
            )
            result["claim_boundary"].update(
                {
                    "bounded_efficiency_improvement": True,
                    "token_saving_lcb_percent": 20.0,
                    "task_success_difference_lcb_percentage_points": -1.0,
                    "parse_validity_rate": 0.99,
                    "semantic_fidelity_rate": 0.95,
                    "safety_passed": True,
                }
            )
        return result

    def test_template_is_valid_null_evidence_not_a_claim(self) -> None:
        report = validate_result(self.result)
        self.assertTrue(report["valid"])
        self.assertTrue(report["negative_or_null_evidence_accepted"])
        self.assertFalse(report["bounded_efficiency_improvement"])
        self.assertFalse(report["changes_general_zero_percent"])
        self.assertFalse(report["direct_agent_dialogue_evidence"])

    def test_all_six_outcomes_are_accepted(self) -> None:
        for outcome in (
            "exact",
            "mismatch",
            "counterexample",
            "ambiguity",
            "refusal",
            "null",
        ):
            with self.subTest(outcome=outcome):
                result = copy.deepcopy(self.result)
                result["outcome"]["kind"] = outcome
                report = validate_result(result)
                self.assertEqual(report["outcome"], outcome)

    def test_matched_not_measured_preserves_null_tokens_in_all_three_arms(self) -> None:
        result = self._matched(complete=False)
        report = validate_result(result)
        self.assertTrue(report["valid"])
        self.assertEqual(report["token_accounting_status"], "not-measured")
        self.assertIsNone(result["token_accounting"]["arms"][0]["tokens"]["total"])

    def test_null_tokens_cannot_be_called_complete(self) -> None:
        result = self._matched(complete=False)
        result["token_accounting"]["status"] = "complete"
        with self.assertRaisesRegex(ValidationError, "complete.*null"):
            validate_result(result)

    def test_incomplete_accounting_cannot_support_a_positive_claim(self) -> None:
        result = self._matched(complete=True, claim=True)
        result["token_accounting"]["status"] = "incomplete"
        result["token_accounting"]["arms"][2]["tokens"]["setup"] = None
        result["token_accounting"]["arms"][2]["tokens"]["total"] = None
        with self.assertRaisesRegex(ValidationError, "requires complete token accounting"):
            validate_result(result)

    def test_incomplete_artifact_evidence_cannot_support_a_positive_claim(self) -> None:
        result = self._matched(complete=True, claim=True)
        result["artifact_evidence"]["agent_entry_sha256"] = None
        with self.assertRaisesRegex(ValidationError, "agent-entry digest"):
            validate_result(result)

        result = self._matched(complete=True, claim=True)
        result["artifact_evidence"]["verified_artifact_ids"].remove(
            "matched_eval_record"
        )
        with self.assertRaisesRegex(ValidationError, "matched-eval artifact"):
            validate_result(result)

    def test_matched_eval_missing_any_of_three_arms_is_rejected(self) -> None:
        for missing in ("raw", "json", "urusilla"):
            with self.subTest(missing=missing):
                result = self._matched(complete=False)
                result["token_accounting"]["arms"] = [
                    arm
                    for arm in result["token_accounting"]["arms"]
                    if arm["arm_id"] != missing
                ]
                with self.assertRaisesRegex(ValidationError, "requires raw, json, and urusilla"):
                    validate_result(result)

    def test_effect_authority_and_untrusted_execution_are_rejected(self) -> None:
        for field in (
            "state_persistence_authorized",
            "permission_expansion_authorized",
            "spending_authorized",
            "external_effects_authorized",
            "untrusted_executable_content_run",
        ):
            with self.subTest(field=field):
                result = copy.deepcopy(self.result)
                result["safety_boundary"][field] = True
                with self.assertRaisesRegex(ValidationError, "safety_boundary"):
                    validate_result(result)

    def test_bounded_positive_requires_complete_three_arm_20_percent_gate(self) -> None:
        result = self._matched(complete=True, claim=True)
        report = validate_result(result)
        self.assertTrue(report["bounded_efficiency_improvement"])
        self.assertFalse(report["changes_general_zero_percent"])

        result = self._matched(complete=True, claim=True)
        result["token_accounting"]["arms"][2]["tokens"] = _tokens(75)
        with self.assertRaisesRegex(ValidationError, "20% observed saving"):
            validate_result(result)

    def test_lcb_success_parse_fidelity_and_safety_gates_are_noncompensable(self) -> None:
        mutations = (
            ("token_saving_lcb_percent", 19.99, "saving LCB"),
            (
                "task_success_difference_lcb_percentage_points",
                -1.01,
                "task-success LCB",
            ),
            ("parse_validity_rate", 0.989, "parse validity"),
            ("semantic_fidelity_rate", 0.949, "semantic fidelity"),
            ("safety_passed", False, "safety gate"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                result = self._matched(complete=True, claim=True)
                result["claim_boundary"][field] = value
                with self.assertRaisesRegex(ValidationError, message):
                    validate_result(result)

    def test_general_result_dialogue_and_adoption_claims_remain_separate(self) -> None:
        for field in (
            "changes_general_zero_percent",
            "direct_agent_dialogue_evidence",
            "external_adoption_claim",
        ):
            with self.subTest(field=field):
                result = copy.deepcopy(self.result)
                result["claim_boundary"][field] = True
                with self.assertRaisesRegex(ValidationError, field):
                    validate_result(result)

    def test_token_total_must_reconcile_and_partial_total_must_remain_null(self) -> None:
        result = self._matched(complete=True)
        result["token_accounting"]["arms"][0]["tokens"]["total"] += 1
        with self.assertRaisesRegex(ValidationError, "does not reconcile"):
            validate_result(result)

        result = self._matched(complete=False)
        result["token_accounting"]["status"] = "incomplete"
        result["token_accounting"]["arms"][0]["tokens"]["receiver"] = 1
        result["token_accounting"]["arms"][0]["tokens"]["total"] = 1
        with self.assertRaisesRegex(ValidationError, "total must be null"):
            validate_result(result)

    def test_duplicate_json_member_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate JSON member"):
            strict_json_loads('{"track":"decode","track":"matched_eval"}')

    def test_cli_validates_template_without_network(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([str(DEFAULT_RESULT), "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertFalse(report["network_used"])

    def test_cli_accepts_bounded_utf8_json_from_stdin(self) -> None:
        payload = json.dumps(self.result, ensure_ascii=False).encode("utf-8")
        stdin = io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(sys, "stdin", stdin),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = main(["-", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertFalse(report["network_used"])


if __name__ == "__main__":
    unittest.main()
