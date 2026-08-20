from __future__ import annotations

from pathlib import Path
import unittest

from competitive_eval.config import ORDERED_PAIRS, REPRESENTATION_ARMS
from competitive_eval.manifests import build_episode_manifests, verify_frozen_inputs
from competitive_eval.report import _cold_amortization, _prompt_lock_records, _stage_summary


LOCAL_A0_AVAILABLE = (
    Path(__file__).resolve().parents[2]
    / "work/competitive_public_task_preflight/preflight_snapshot.json"
).is_file()


@unittest.skipUnless(LOCAL_A0_AVAILABLE, "separately provisioned A0 cache is absent")
class ReportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = verify_frozen_inputs()

    def test_complete_prompt_locks_for_mock_matrix(self) -> None:
        episodes = build_episode_manifests(
            self.inputs,
            stage="A0",
            arms=REPRESENTATION_ARMS,
            pairs=ORDERED_PAIRS,
            items_per_dataset=1,
            repeats=1,
        )
        locks = _prompt_lock_records(self.inputs, episodes)
        self.assertEqual(len(locks), 24)
        self.assertTrue(all(lock["prompt_text"] for lock in locks))
        self.assertTrue(all(lock["mock_only"] for lock in locks))

    def test_cold_amortization_and_stage_counts(self) -> None:
        cold = _cold_amortization()
        self.assertEqual(cold["session_lengths"], [1, 2, 4, 8, 16, 32, 64, 128])
        self.assertEqual(cold["cold_artifact_utf8_bytes"], 16_005)
        stages = _stage_summary()
        self.assertEqual(stages["stages"]["A1_plan"]["episode_count"], 360)
        self.assertEqual(stages["stages"]["A3"]["base_call_cap"], 259_200)
        self.assertEqual(stages["a1_all_six_arms_same_three_pairs"]["base_call_cap"], 5_760)


if __name__ == "__main__":
    unittest.main()
