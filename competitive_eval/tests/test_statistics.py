from __future__ import annotations

from fractions import Fraction
import unittest

from competitive_eval.errors import StatisticsError
from competitive_eval.statistical import AnalysisRow, exact_mcnemar, holm_adjust, paired_bootstrap


def row(item: str, arm: str, success: bool, tokens: int, pair: tuple[str, str] = ("O", "G")) -> AnalysisRow:
    return AnalysisRow(
        task_family="hotpotqa",
        item_id=item,
        evidence_mode="forced",
        repeat_seed=20260820,
        sender_family=pair[0],
        receiver_family=pair[1],
        repeat_id=0,
        arm=arm,
        safe_task_success=success,
        t_total=tokens,
    )


class StatisticalTests(unittest.TestCase):
    def test_constant_gate_vector(self) -> None:
        rows = []
        for index in range(4):
            rows.extend((row(str(index), "cte", True, 100), row(str(index), "arm", True, 75)))
        result = paired_bootstrap(
            rows,
            candidate_arm="arm",
            baseline_arm="cte",
            analysis_id="constant",
            resamples=1000,
        )
        self.assertEqual(result["success"]["point"]["decimal"], "0.000000000000")
        self.assertEqual(result["tokens"]["point"]["decimal"], "0.250000000000")
        self.assertTrue(result["success"]["passes_unadjusted_ci"])
        self.assertTrue(result["tokens"]["passes_unadjusted_ci"])

    def test_ratio_of_sums_not_mean_of_ratios(self) -> None:
        rows = [
            row("a", "cte", True, 10),
            row("a", "arm", True, 1),
            row("b", "cte", True, 100),
            row("b", "arm", True, 90),
        ]
        result = paired_bootstrap(
            rows,
            candidate_arm="arm",
            baseline_arm="cte",
            analysis_id="ratio",
            resamples=1000,
        )
        point = result["tokens"]["point"]
        self.assertEqual((point["numerator"], point["denominator"]), (19, 110))

    def test_holm_vector(self) -> None:
        result = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.20})
        observed = {
            key: value["adjusted_p"]["decimal"]
            for key, value in result["hypotheses"].items()
        }
        self.assertEqual(
            observed,
            {
                "a": "0.040000000000",
                "b": "0.090000000000",
                "c": "0.090000000000",
                "d": "0.200000000000",
            },
        )
        self.assertTrue(result["hypotheses"]["a"]["passes"])
        self.assertFalse(result["hypotheses"]["b"]["passes"])

    def test_exact_mcnemar_vector(self) -> None:
        rows = []
        outcomes = ((True, False), (False, True), (False, True), (False, True))
        for index, (candidate, baseline) in enumerate(outcomes):
            rows.extend(
                (
                    row(str(index), "cte", baseline, 100),
                    row(str(index), "arm", candidate, 75),
                )
            )
        result = exact_mcnemar(rows, candidate_arm="arm", baseline_arm="cte")
        self.assertEqual(result["candidate_only_success"], 1)
        self.assertEqual(result["baseline_only_success"], 3)
        p = result["two_sided_exact_binomial_p"]
        self.assertEqual((p["numerator"], p["denominator"]), (5, 8))

    def test_fail_closed_bad_and_missing_pairs(self) -> None:
        with self.assertRaises(StatisticsError):
            AnalysisRow("x", "i", "m", 1, "O", "G", 0, "a", 1, 2)  # type: ignore[arg-type]
        with self.assertRaisesRegex(StatisticsError, "INCOMPLETE_PAIR_BLOCK"):
            paired_bootstrap(
                [row("a", "arm", True, 1), row("b", "arm", True, 1)],
                candidate_arm="arm",
                baseline_arm="cte",
                analysis_id="missing",
                resamples=10,
            )
        with self.assertRaisesRegex(StatisticsError, "INCOMPLETE_HOLM_FAMILY"):
            holm_adjust({"a": 0.01}, expected_hypotheses=["a", "b"])

    def test_permutation_invariance(self) -> None:
        rows = []
        for index in range(6):
            rows.extend(
                (
                    row(str(index), "cte", index != 5, 100 + index),
                    row(str(index), "arm", index not in {2, 5}, 80 + index),
                )
            )
        first = paired_bootstrap(
            rows,
            candidate_arm="arm",
            baseline_arm="cte",
            analysis_id="permutation",
            resamples=1000,
        )
        second = paired_bootstrap(
            list(reversed(rows)),
            candidate_arm="arm",
            baseline_arm="cte",
            analysis_id="permutation",
            resamples=1000,
        )
        self.assertEqual(first, second)

    def test_item_only_sensitivity_keeps_an_item_across_pairs(self) -> None:
        rows = []
        for item in ("a", "b"):
            for pair in (("O", "G"), ("G", "Q")):
                rows.extend(
                    (
                        row(item, "cte", True, 100, pair),
                        row(item, "arm", True, 75, pair),
                    )
                )
        result = paired_bootstrap(
            rows,
            candidate_arm="arm",
            baseline_arm="cte",
            analysis_id="item-only",
            resamples=100,
            item_only_cluster=True,
        )
        self.assertEqual(result["clusters"], 2)
        self.assertEqual(result["strata"], 1)


if __name__ == "__main__":
    unittest.main()
