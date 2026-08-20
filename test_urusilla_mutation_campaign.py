#!/usr/bin/env python3
"""Frozen tests for the deterministic cross-codec mutation campaign."""

from __future__ import annotations

from pathlib import Path
import unittest

import urusilla_mutation_campaign as campaign


HERE = Path(__file__).resolve().parent


class MutationCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = campaign.run_campaign()

    def test_exact_cross_codec_and_insertion_order_checks_are_complete(self) -> None:
        self.assertEqual(self.result["messages"], 280)
        self.assertEqual(len(self.result["codecs"]), 5)
        self.assertEqual(self.result["exact_decodes"], 1_400)
        self.assertEqual(self.result["insertion_order_checks"], 1_400)
        self.assertEqual(
            self.result["encoded_sequence_sha256"],
            "f6bfb3cde39d220a275b8326d8fbb61072747d3756aa488b863ac91829f29a61",
        )

    def test_integrity_protected_representations_reject_every_mutation(self) -> None:
        expected = {
            "reference_wire": 2_240,
            "static_profile_wire": 2_240,
            "controlled_terse_envelope": 2_240,
            "token_surface_v04": 2_240,
        }
        for codec, count in expected.items():
            with self.subTest(codec=codec):
                self.assertEqual(self.result["rejections_by_codec"][codec], count)
                self.assertEqual(
                    self.result["accepted_mutations_by_codec"][codec], 0
                )

    def test_raw_readable_fallback_exposes_silent_semantic_mutations(self) -> None:
        self.assertEqual(
            self.result["rejections_by_codec"]["controlled_terse_english"],
            1_956,
        )
        self.assertEqual(
            self.result["accepted_mutations_by_codec"]["controlled_terse_english"],
            284,
        )
        self.assertEqual(
            self.result["canonical_semantic_mutations_accepted"], 284
        )
        self.assertEqual(self.result["mutation_attempts"], 11_200)
        self.assertEqual(self.result["mutation_rejections"], 10_916)
        self.assertEqual(
            self.result["mutation_sequence_sha256"],
            "d5e992e8567d34807f2c820ee6ae367cda294bf3f596390dd72e4b4030634065",
        )

    def test_invalid_campaign_arguments_fail(self) -> None:
        for kwargs in (
            {"seed": -1},
            {"seed": 1.5},
            {"mutations_per_message": 0},
            {"mutations_per_message": 65},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    campaign.run_campaign(**kwargs)

    def test_report_is_english_only_and_discloses_negative_result(self) -> None:
        report = (HERE / "MUTATION_CAMPAIGN_RESULTS.md").read_text(encoding="utf-8")
        self.assertFalse(any("\uac00" <= character <= "\ud7a3" for character in report))
        self.assertIn("1,956/2,240", report)
        self.assertIn("284/2,240", report)
        self.assertIn("not coverage-guided fuzzing", report)
        self.assertIn("does not authenticate", report)


if __name__ == "__main__":
    unittest.main()
