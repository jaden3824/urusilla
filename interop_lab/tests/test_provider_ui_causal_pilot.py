"""Offline tests for the thin provider-UI causal-pilot carrier."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from initial_goal_eval.contract import VerificationError, canonical_json
from interop_lab.provider_ui_causal_pilot import (
    CONDITIONS,
    SHARED_PROMPT_PREFIX,
    SHARED_PROMPT_SUFFIX,
    build_packet,
    load_packet,
    score_response,
    slot_for_condition,
    validate_packet,
    validate_packet_json,
)


OBSERVATION_PATH = (
    Path(__file__).parents[1]
    / "evidence"
    / "gemini_web_ui_causal_pilot_2026_08_23.observation.json"
)


class ProviderUiCausalPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = load_packet()

    def test_committed_packet_equals_deterministic_builder(self) -> None:
        self.assertEqual(self.packet, build_packet())
        diagnostic = validate_packet_json(canonical_json(self.packet))
        self.assertTrue(diagnostic["valid"])
        self.assertEqual(diagnostic["slot_count"], 4)
        self.assertFalse(diagnostic["claim_eligible"])
        self.assertEqual(
            diagnostic["provider_token_usage_status"],
            "unknown-ui-permitted-for-pilot-only",
        )

    def test_four_self_contained_prompts_require_separate_fresh_chats(self) -> None:
        slots = self.packet["packet"]["slots"]
        self.assertEqual(tuple(slot["condition"] for slot in slots), CONDITIONS)
        self.assertEqual(len({slot["slot_id"] for slot in slots}), 4)
        self.assertEqual(len({slot["prompt_sha256"] for slot in slots}), 4)
        self.assertTrue(self.packet["packet"]["execution"]["fresh_chat_per_slot"])
        self.assertFalse(
            self.packet["packet"]["execution"]["reuse_chat_between_slots"]
        )
        for slot in slots:
            self.assertTrue(slot["prompt"].startswith(SHARED_PROMPT_PREFIX))
            self.assertTrue(slot["prompt"].endswith(SHARED_PROMPT_SUFFIX))
            self.assertIn("Do not browse, use tools", slot["prompt"])
            self.assertIn("cause any external effect", slot["prompt"])

    def test_delivery_date_flip_invariant_and_true_missing_are_frozen(self) -> None:
        arm_a = slot_for_condition(self.packet, "a")
        arm_b = slot_for_condition(self.packet, "b")
        invariant = slot_for_condition(self.packet, "invariant")
        missing = slot_for_condition(self.packet, "missing")

        input_a = arm_a["prompt"].split("INPUT RECORD", 1)[1].split("\n\nOUTPUT", 1)[0]
        input_b = arm_b["prompt"].split("INPUT RECORD", 1)[1].split("\n\nOUTPUT", 1)[0]
        input_missing = missing["prompt"].split("INPUT RECORD", 1)[1].split(
            "\n\nOUTPUT", 1
        )[0]
        self.assertEqual(
            input_a.replace("2026-09-15", "2026-10-15"),
            input_b,
        )
        self.assertNotIn('"delivery_date"', input_missing)
        self.assertIn('"invoice_date":"2026-08-31"', input_missing)
        self.assertEqual(
            arm_a["expected_canonical_json"],
            '{"delivery_date":"2026-09-15","status":"scheduled"}',
        )
        self.assertEqual(
            arm_b["expected_canonical_json"],
            '{"delivery_date":"2026-10-15","status":"scheduled"}',
        )
        self.assertEqual(
            invariant["expected_canonical_json"], arm_a["expected_canonical_json"]
        )
        self.assertNotEqual(invariant["prompt"], arm_a["prompt"])
        self.assertEqual(
            missing["expected_canonical_json"],
            '{"delivery_date":null,"status":"fallback-missing-required-field"}',
        )

    def test_mutations_fail_closed_even_when_claim_flag_stays_false(self) -> None:
        cases = (
            ("prompt", ("packet", "slots", 0, "prompt"), "tampered"),
            ("root-digest", ("packet_sha256",), "sha256:" + "0" * 64),
            ("claim", ("packet", "claim_eligible"), True),
            (
                "usage",
                ("packet", "provider_surface", "provider_token_usage"),
                {"total_tokens": 1},
            ),
        )
        for name, path, replacement in cases:
            with self.subTest(name=name):
                mutated = deepcopy(self.packet)
                cursor = mutated
                for part in path[:-1]:
                    cursor = cursor[part]
                cursor[path[-1]] = replacement
                with self.assertRaisesRegex(
                    VerificationError, "packet differs from the deterministic carrier"
                ):
                    validate_packet(mutated)

    def test_scoring_is_byte_exact_and_never_claim_eligible(self) -> None:
        expected = slot_for_condition(self.packet, "a")["expected_canonical_json"]
        exact = score_response(self.packet, "a", expected)
        newline = score_response(self.packet, "a", expected + "\n")
        fenced = score_response(self.packet, "a", "```json\n" + expected + "\n```")
        self.assertTrue(exact["exact_canonical_match"])
        self.assertFalse(newline["exact_canonical_match"])
        self.assertFalse(fenced["exact_canonical_match"])
        self.assertFalse(exact["claim_eligible"])

    def test_committed_project_operated_observation_is_packet_bound(self) -> None:
        observation = json.loads(OBSERVATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            observation["schema_version"],
            "urusilla-provider-ui-causal-pilot-observation/1",
        )
        self.assertEqual(observation["packet_sha256"], self.packet["packet_sha256"])
        self.assertFalse(observation["claim_eligible"])
        self.assertEqual(observation["classification"], "SAME-PROJECT-ORCHESTRATED")
        self.assertIsNone(observation["provider_surface"]["exact_model_version"])
        self.assertIsNone(observation["provider_surface"]["provider_token_usage"])
        self.assertEqual(
            tuple(item["condition"] for item in observation["observations"]),
            CONDITIONS,
        )
        for item in observation["observations"]:
            slot = slot_for_condition(self.packet, item["condition"])
            self.assertEqual(item["prompt_sha256"], slot["prompt_sha256"])
            self.assertEqual(
                item["expected_canonical_json"], slot["expected_canonical_json"]
            )
            self.assertEqual(
                item["scoring"],
                score_response(
                    self.packet, item["condition"], item["observed_output"]
                ),
            )
        self.assertEqual(observation["summary"]["exact_canonical_matches"], 4)
        self.assertTrue(observation["summary"]["all_exact"])
        self.assertIsNone(observation["summary"]["causal_verdict"])
        self.assertIsNone(observation["summary"]["efficiency_verdict"])


if __name__ == "__main__":
    unittest.main()
