from __future__ import annotations

from pathlib import Path
import unittest

from competitive_eval.config import ORDERED_PAIRS, REPRESENTATION_ARMS
from competitive_eval.manifests import (
    build_episode_manifests,
    build_run_manifest,
    verify_frozen_inputs,
)


LOCAL_A0_AVAILABLE = (
    Path(__file__).resolve().parents[2]
    / "work/competitive_public_task_preflight/preflight_snapshot.json"
).is_file()


@unittest.skipUnless(LOCAL_A0_AVAILABLE, "separately provisioned A0 cache is absent")
class FrozenInputsAndManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = verify_frozen_inputs()

    def test_a0_sources_and_report_discrepancy_are_explicit(self) -> None:
        verification = self.inputs.verification
        self.assertEqual(verification["hotpotqa_records"], 100)
        self.assertEqual(verification["wikihop_records"], 100)
        self.assertEqual(verification["wikihop_context_blocks_observed"], 1630)
        self.assertEqual(verification["root_report_context_blocks_text"], 1702)
        self.assertTrue(verification["root_report_discrepancy_retained"])

    def test_mock_matrix_covers_all_arms_and_ordered_pairs(self) -> None:
        episodes = build_episode_manifests(
            self.inputs, stage="A0", items_per_dataset=1, mock_only=True
        )
        self.assertEqual(len(episodes), 2 * 6 * 9)
        self.assertEqual({episode.arm for episode in episodes}, set(REPRESENTATION_ARMS))
        self.assertEqual(
            {tuple(episode.value["ordered_pair"]) for episode in episodes},
            set(ORDERED_PAIRS),
        )
        self.assertEqual(len({episode.episode_id for episode in episodes}), len(episodes))
        self.assertTrue(all(episode.value["gold_answer_in_provider_request"] is False for episode in episodes))

    def test_a1_plan_and_a0_cost_variant_remain_distinct(self) -> None:
        planned = build_episode_manifests(
            self.inputs, stage="A1_plan", mock_only=False
        )
        cost_variant = build_episode_manifests(
            self.inputs, stage="A1_a0_cost_variant", mock_only=False
        )
        self.assertEqual(len(planned), 360)
        self.assertEqual(len(cost_variant), 360)
        self.assertEqual(
            {episode.arm for episode in planned},
            {"compact_terse_english", "autoform", "current_adaptive_surface"},
        )
        self.assertEqual(
            {episode.arm for episode in cost_variant},
            {"compact_terse_english", "canonical_minified_json", "current_adaptive_surface"},
        )
        self.assertNotEqual(
            {episode.episode_id for episode in planned},
            {episode.episode_id for episode in cost_variant},
        )

    def test_offline_run_has_zero_authority(self) -> None:
        episodes = build_episode_manifests(
            self.inputs,
            stage="A0",
            arms=["compact_terse_english"],
            pairs=[("Q", "Q")],
            items_per_dataset=1,
        )
        run = build_run_manifest(episodes, stage="A0")
        self.assertFalse(run.value["network_allowed"])
        self.assertFalse(run.value["provider_calls_allowed"])
        self.assertEqual(run.value["approved_usd_cap"], 0)
        self.assertFalse(run.value["claim_eligible"])


if __name__ == "__main__":
    unittest.main()
