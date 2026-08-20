from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from competitive_eval.checkpoint import CheckpointStore
from competitive_eval.errors import IntegrityError
from competitive_eval.manifests import (
    build_episode_manifests,
    build_run_manifest,
    verify_frozen_inputs,
)
from competitive_eval.mocks import ScriptedMockAdapter, scenario_key
from competitive_eval.runner import OfflineRunner


LOCAL_A0_AVAILABLE = (
    Path(__file__).resolve().parents[2]
    / "work/competitive_public_task_preflight/preflight_snapshot.json"
).is_file()


@unittest.skipUnless(LOCAL_A0_AVAILABLE, "separately provisioned A0 cache is absent")
class RunnerResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = verify_frozen_inputs()

    def test_resume_does_not_repeat_completed_mock_calls(self) -> None:
        episodes = build_episode_manifests(
            self.inputs,
            stage="A0",
            arms=["compact_terse_english"],
            pairs=[("Q", "Q")],
            items_per_dataset=1,
        )
        run = build_run_manifest(episodes, stage="A0")
        gold = {
            episode.episode_id: next(
                item.answer
                for dataset in self.inputs.datasets.values()
                for item in dataset
                if item.key == episode.value["item_key"]
            )
            for episode in episodes
        }
        adapter = ScriptedMockAdapter(gold)
        with tempfile.TemporaryDirectory() as directory:
            runner = OfflineRunner(
                inputs=self.inputs,
                run_manifest=run,
                episodes=episodes,
                output_dir=Path(directory),
                adapter=adapter,
            )
            partial = runner.run_all(max_new_turns=1)
            self.assertEqual(partial, ())
            calls_after_partial = adapter.invocations
            resumed = runner.run_all()
            self.assertEqual(len(resumed), len(episodes))
            final_calls = adapter.invocations
            replay = runner.run_all()
            self.assertEqual(adapter.invocations, final_calls)
            self.assertEqual([value.value for value in resumed], [value.value for value in replay])
            self.assertGreater(final_calls, calls_after_partial)

    def test_tampered_checkpoint_fails_closed(self) -> None:
        episodes = build_episode_manifests(
            self.inputs,
            stage="A0",
            arms=["compact_terse_english"],
            pairs=[("Q", "Q")],
            items_per_dataset=1,
        )[:1]
        run = build_run_manifest(episodes, stage="A0")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = OfflineRunner(
                inputs=self.inputs,
                run_manifest=run,
                episodes=episodes,
                output_dir=root,
            )
            runner.run_all(max_new_turns=1)
            event = next((root / "events" / episodes[0].episode_id).glob("*.json"))
            raw = event.read_text(encoding="utf-8")
            event.write_text(raw.replace("turn_completed", "turn_corrupted"), encoding="utf-8")
            with self.assertRaises(IntegrityError):
                runner.store.load(episodes[0].episode_id)

    def test_fault_plan_exercises_repair_fallback_and_timeout_or_refusal(self) -> None:
        candidates = build_episode_manifests(
            self.inputs,
            stage="A0",
            arms=["compact_terse_english", "current_adaptive_surface"],
            items_per_dataset=5,
        )
        chosen = {}
        for episode in candidates:
            value = episode.value
            key = scenario_key(
                value["dataset"],
                value["item_key"],
                tuple(value["ordered_pair"]),
                value["repeat_index"],
            )
            code = int(key[:8], 16)
            if code % 17 == 0 and code % 31 and code % 37:
                chosen.setdefault("repair", episode)
            if episode.arm == "current_adaptive_surface" and code % 13 == 0 and code % 31 and code % 37 and code % 17:
                chosen.setdefault("fallback", episode)
            if code % 31 == 0 or code % 37 == 0:
                chosen.setdefault("terminal_fault", episode)
            if len(chosen) == 3:
                break
        self.assertEqual(set(chosen), {"repair", "fallback", "terminal_fault"})
        episodes = tuple(chosen.values())
        run = build_run_manifest(episodes, stage="A0")
        with tempfile.TemporaryDirectory() as directory:
            runner = OfflineRunner(
                inputs=self.inputs,
                run_manifest=run,
                episodes=episodes,
                output_dir=Path(directory),
            )
            results = {result.episode_id: result for result in runner.run_all()}
        repair = results[chosen["repair"].episode_id].value
        fallback = results[chosen["fallback"].episode_id].value
        fault = results[chosen["terminal_fault"].episode_id].value
        self.assertGreaterEqual(repair["ledger"]["repair_calls"], 1)
        self.assertGreaterEqual(fallback["ledger"]["fallback_calls"], 1)
        self.assertTrue(fault["timeout_in_denominator"] or fault["refusal_in_denominator"])


if __name__ == "__main__":
    unittest.main()
