import json
from pathlib import Path
import tempfile
import unittest

import urusilla_hidden_transfer_evaluation as pilot


ROOT = Path(__file__).resolve().parent


class HiddenTransferEvaluationTests(unittest.TestCase):
    def test_declared_digests_and_expected_component_results(self):
        result = pilot.evaluate()
        self.assertEqual(
            result["digests"]["tasks_sha256"],
            "41e345b3fed3931c1fd9e764bf251c638550ea8cffcaed348f22499605ff3692",
        )
        self.assertEqual(
            result["digests"]["submission_sha256"],
            "1f73c5bcd26e8e50cb02fe38eba25c4a3e6ffc7c64228085655cec50641939d9",
        )
        self.assertEqual(
            result["digests"]["expectations_sha256"],
            "dcd1b703ca73255d5514556437091b51c919aacf6b46e5ffe04f9ad190791d49",
        )
        self.assertEqual(
            result["digests"]["capsule_sha256"],
            "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
        )
        expected = {
            "decision_accuracy": (16, 16),
            "act_selection": (10, 10),
            "envelope_preservation": (10, 10),
            "structural_generation": (6, 10),
            "essential_semantics": (6, 10),
            "negative_rejection": (6, 6),
        }
        for name, (earned, possible) in expected.items():
            self.assertEqual(result["components"][name]["earned"], earned)
            self.assertEqual(result["components"][name]["possible"], possible)

    def test_standardized_score_is_not_fabricated(self):
        result = pilot.evaluate()
        self.assertIsNone(result["standardized_teachability_score"])
        self.assertFalse(result["precommitment"]["cryptographic_precommitment"])
        self.assertTrue(result["precommitment"]["expectations_created_after_submission"])
        self.assertFalse(result["external_adopter_claim"])
        self.assertFalse(result["participant_rerun_after_urusilla_cutover"])
        self.assertTrue(result["current_artifacts_are_post_cutover_projection"])

    def test_report_does_not_rebind_historical_outcomes_to_current_artifacts(self):
        report = pilot.render_markdown(pilot.evaluate())
        self.assertIn("No participant was rerun after the cutover", report)
        self.assertIn("measured outcomes remain bound", report)
        self.assertIn("must not be attributed to a new Urusilla participant run", report)

    def test_exact_four_structural_failures_are_reproducible(self):
        result = pilot.evaluate()
        failures = {
            row["case_id"]: row["validation_error"]
            for row in result["cases"]
            if row["structural_valid"] is False
        }
        self.assertEqual(set(failures), {"R8D1", "P7A2", "W5L4", "V3G8"})
        self.assertIn("unknown node kind", failures["R8D1"])
        self.assertIn("absolute URI", failures["P7A2"])
        self.assertIn("canonical list", failures["W5L4"])
        self.assertIn("whitespace", failures["V3G8"])

    def test_capsule_digest_is_checked_against_the_capsule_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wrong_capsule = Path(temp_dir) / "capsule.json"
            wrong_capsule.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "capsule digest"):
                pilot.evaluate(capsule_path=wrong_capsule)

    def test_published_submission_declares_only_two_inputs(self):
        submission = json.loads(
            (ROOT / "urusilla_hidden_transfer_submission.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(submission["self_declared_files_read"]), 2)
        self.assertEqual(
            submission["historical_participant_original_submission_sha256"],
            "6428c66339e156b52be80e5695a72c8ff790828d1d52ea7eb2906cff1f493489",
        )
        self.assertTrue(
            submission["self_declared_files_read"][0].endswith("urusilla_capsule_v0_1.json")
        )
        self.assertTrue(
            submission["self_declared_files_read"][1].endswith("tasks.json")
        )


if __name__ == "__main__":
    unittest.main()
