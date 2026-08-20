import unittest

from urusilla_energy_sensitivity import EnergyCase, evaluate, illustrative_cases


class EnergySensitivityTests(unittest.TestCase):
    def test_zero_communication_has_only_overhead(self) -> None:
        result = evaluate(
            EnergyCase("zero", 0.0, 0.5, 0.2, 0.9, 0.9, 0.03)
        )
        self.assertAlmostEqual(result.energy_per_safe_task, 1.03)
        self.assertAlmostEqual(result.net_saving, -0.03)

    def test_formula(self) -> None:
        result = evaluate(
            EnergyCase("known", 0.5, 0.6, 0.2, 0.4, 0.25, 0.02)
        )
        expected_gross = 0.5 * (0.6 * 0.4 + 0.2 * 0.25)
        self.assertAlmostEqual(result.gross_saved_energy, expected_gross)
        self.assertAlmostEqual(result.net_saving, expected_gross - 0.02)

    def test_safe_task_adjustment_can_reverse_gain(self) -> None:
        good = evaluate(
            EnergyCase("good", 0.3, 0.7, 0.1, 0.452, 0.186, 0.025, 1.0)
        )
        repaired = evaluate(
            EnergyCase("repair", 0.3, 0.7, 0.1, 0.452, 0.186, 0.025, 0.9)
        )
        self.assertGreater(good.net_saving, 0.0)
        self.assertLess(repaired.net_saving, 0.0)

    def test_invalid_shares_fail(self) -> None:
        with self.assertRaises(ValueError):
            evaluate(EnergyCase("bad", 0.3, 0.8, 0.3, 0.4, 0.2, 0.0))
        with self.assertRaises(ValueError):
            evaluate(EnergyCase("bad", 1.1, 0.5, 0.2, 0.4, 0.2, 0.0))
        with self.assertRaises(ValueError):
            evaluate(EnergyCase("bad", 0.3, 0.5, 0.2, 0.4, 0.2, 0.0, 0.0))

    def test_illustrative_case_signs(self) -> None:
        results = {case.name: evaluate(case) for case in illustrative_cases()}
        self.assertLess(results["overhead-dominates"].net_saving, 0.0)
        self.assertGreater(results["communication-moderate"].net_saving, 0.0)
        self.assertGreater(results["communication-heavy"].net_saving, 0.0)
        self.assertLess(results["repair-regression"].net_saving, 0.0)


if __name__ == "__main__":
    unittest.main()
