from __future__ import annotations

from decimal import Decimal
import unittest

from competitive_eval.errors import ApprovalRequired, LedgerError
from competitive_eval.gates import (
    BudgetAuthorization,
    BudgetGuard,
    a1_to_a2_promotion,
    receiver_family_regression_gate,
    success_noninferiority_pass,
    token_reduction_pass,
)
from competitive_eval.ledger import TokenLedger, empty_categories


class LedgerAndGateTests(unittest.TestCase):
    def test_token_ledger_exact_formula_and_provider_annotations(self) -> None:
        categories = empty_categories(task_input=10, system_role=2, final_answer=3)
        ledger = TokenLedger(
            categories,
            provider_annotations={
                "provider_input_tokens": 13,
                "provider_output_tokens": 4,
                "provider_total_tokens": 17,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens_subset": 0,
                "accepted_prediction_tokens": 0,
                "rejected_prediction_tokens": 0,
                "unclassified_usage_json": None,
                "provider_usage_status": "reported",
            },
        )
        self.assertEqual(ledger.t_total, 15)
        self.assertEqual(ledger.reconciliation()["input_delta"], 1)
        with self.assertRaises(LedgerError):
            TokenLedger({"task_input": 1})

    def test_offline_budget_rejects_provider_and_paid_calls(self) -> None:
        guard = BudgetGuard(BudgetAuthorization.offline_mock())
        guard.before_call(is_mock=True, is_paid=False)
        self.assertEqual(guard.snapshot()["mock_calls"], 1)
        with self.assertRaises(ApprovalRequired):
            guard.before_call(is_mock=False, is_paid=False)

    def test_exact_gate_boundaries(self) -> None:
        self.assertFalse(success_noninferiority_pass(-0.010))
        self.assertTrue(success_noninferiority_pass(-0.009999))
        self.assertTrue(token_reduction_pass(0.25))
        self.assertFalse(token_reduction_pass(0.249999))
        at_boundary = a1_to_a2_promotion(
            exact_parsing_all_episodes=True,
            complete_paired_stage=True,
            arm_minus_cte_point_estimates={"x": -0.030},
        )
        self.assertTrue(at_boundary["passed"])
        below = a1_to_a2_promotion(
            exact_parsing_all_episodes=True,
            complete_paired_stage=True,
            arm_minus_cte_point_estimates={"x": -0.030001},
        )
        self.assertFalse(below["passed"])
        self.assertTrue(receiver_family_regression_gate({"Q": -0.010})["passed"])
        self.assertFalse(receiver_family_regression_gate({"Q": -0.010001})["passed"])


if __name__ == "__main__":
    unittest.main()
