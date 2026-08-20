#!/usr/bin/env python3
"""Frozen tests for the transparent-fallback v0.8 development candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from urusilla import DecodeError, ValidationError
from urusilla_tokenizer_benchmark import default_asset_root, load_tokenizer_profiles

import urusilla_transparent_fallback_v08 as subject


EXPECTED_SOURCE_SHA256 = (
    "240c8b011733f925467fca9c73e86b523dd2f8758daa63bdbd9e70aa9b3fdeb2"
)


class TransparentFallbackV08Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.profiles = load_tokenizer_profiles(default_asset_root())
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.study = subject.collect_study(cls.profiles)
        cls.snapshot = subject.study_snapshot(cls.study)

    def test_frozen_source_contract_and_snapshot(self) -> None:
        source_path = Path(subject.__file__).resolve()
        self.assertEqual(
            hashlib.sha256(source_path.read_bytes()).hexdigest(),
            EXPECTED_SOURCE_SHA256,
        )
        self.assertEqual(
            subject.selection_contract_sha256(),
            subject.EXPECTED_SELECTION_CONTRACT_SHA256,
        )
        self.assertEqual(
            subject.snapshot_sha256(self.snapshot),
            subject.EXPECTED_SNAPSHOT_SHA256,
        )
        self.assertNotIn("pending", subject.EXPECTED_SELECTION_CONTRACT_SHA256)
        self.assertNotIn("pending", subject.EXPECTED_SNAPSHOT_SHA256)

    def test_external_corpus_is_explicitly_post_reveal(self) -> None:
        self.assertEqual(len(self.study.messages), 43)
        self.assertEqual(
            self.snapshot["evidence_status"],
            "post-reveal exploratory development",
        )
        self.assertEqual(
            self.snapshot["external_corpus"]["file_sha256"],
            subject.EXPECTED_EXTERNAL_FILE_SHA256,
        )
        self.assertIn("no fresh confirmatory corpus", subject.SELECTION_CONTRACT["claim_boundary"])

    def test_plain_bound_delivery_is_byte_identical(self) -> None:
        self.assertEqual(self.study.plain_delivery_identity, 86)
        self.assertEqual(
            self.study.plain_delivery_identity,
            self.study.plain_delivery_identity_total,
        )
        for index, item in enumerate(self.study.prepared, 1):
            for mode in subject.PLAIN_MODES:
                baseline = item.texts[mode]
                record = subject.encode_bound_record(mode, index, baseline)
                opened_mode, delivered, decoded = subject.open_bound_record(
                    record,
                    self.study.alias_profile,
                    expected_sequence=index,
                )
                self.assertEqual(opened_mode, mode)
                self.assertEqual(delivered.encode("utf-8"), baseline.encode("utf-8"))
                self.assertEqual(decoded, item.message)

    def test_external_penalty_becomes_exactly_zero_when_bound(self) -> None:
        for tokenizer in self.profiles:
            row = self.snapshot["token_rows"][tokenizer.key]
            self.assertEqual(row["bound_warm"], row["raw_plain"])
            self.assertEqual(row["bound_cold"], row["raw_plain"])
            self.assertEqual(row["bound_warm_regret_tokens"], 0)
            self.assertEqual(row["bound_cold_regret_tokens"], 0)
            self.assertEqual(
                self.snapshot["mode_counts"]["bound"][tokenizer.key],
                {"terse": 43},
            )
            plan = self.study.cold_plans["bound"][tokenizer.key].selected
            self.assertFalse(plan.structured)
            self.assertFalse(plan.optimized)
            self.assertEqual(plan.cold_tokens, 0)

    def test_standalone_overhead_is_preserved(self) -> None:
        expected_excess = {
            "cl100k_base": 1096,
            "o200k_base": 1057,
            "qwen2_5_7b_instruct": 1549,
            "mistral_7b_instruct_v03": 1623,
        }
        expected_matched_regret = {
            "cl100k_base": 0,
            "o200k_base": 0,
            "qwen2_5_7b_instruct": 0,
            "mistral_7b_instruct_v03": 0,
        }
        for tokenizer in self.profiles:
            row = self.snapshot["token_rows"][tokenizer.key]
            self.assertEqual(
                row["standalone_warm_excess_over_raw_plain"],
                expected_excess[tokenizer.key],
            )
            self.assertEqual(
                row["standalone_matched_regret_tokens"],
                expected_matched_regret[tokenizer.key],
            )
            self.assertEqual(row["standalone_cold_matched_regret_tokens"], 0)
            self.assertGreater(row["standalone_warm"], row["raw_plain"])

    def test_compact_candidates_require_a_strict_win(self) -> None:
        for contract in ("bound", "standalone"):
            for tokenizer in self.profiles:
                for selection in self.study.selections[contract][tokenizer.key]:
                    self.assertEqual(
                        selection.candidate.tokens,
                        min(item.tokens for item in selection.candidates.values()),
                    )
                    if selection.candidate.mode in subject.COMPACT_MODES:
                        self.assertLess(
                            selection.candidate.tokens,
                            selection.plain_best.tokens,
                        )

    def test_exact_and_deterministic_recovery(self) -> None:
        self.assertEqual(self.study.exact_candidates, 172)
        self.assertEqual(self.study.deterministic_candidates, 172)
        self.assertEqual(self.study.exact_selected, {"bound": 172, "standalone": 172})
        self.assertEqual(
            self.study.deterministic_selected,
            {"bound": 172, "standalone": 172},
        )

    def test_integrity_and_sequence_trials_fail_closed(self) -> None:
        self.assertEqual(
            self.study.integrity_attempted,
            {"bound": 860, "standalone": 860},
        )
        self.assertEqual(self.study.integrity_rejected, self.study.integrity_attempted)

    def test_record_overhead_is_explicit(self) -> None:
        self.assertEqual(subject.BOUND_METADATA_BYTES, 25)
        self.assertEqual(subject.STANDALONE_HEADER_CHARACTERS, 42)
        for tokenizer in self.profiles:
            bound = self.snapshot["byte_rows"]["bound"][tokenizer.key]
            standalone = self.snapshot["byte_rows"]["standalone"][tokenizer.key]
            self.assertEqual(bound["transport_metadata_bytes"], 43 * 25)
            self.assertEqual(
                bound["complete_record_bytes"],
                bound["payload_bytes"] + bound["transport_metadata_bytes"],
            )
            self.assertEqual(
                standalone["complete_record_bytes"] - standalone["payload_bytes"],
                43 * 42,
            )

    def test_wrong_key_and_noncanonical_headers_are_rejected(self) -> None:
        item = self.study.prepared[0]
        payload = item.texts["terse"]
        record = subject.encode_bound_record("terse", 1, payload)
        with self.assertRaises(DecodeError):
            subject.open_bound_record(
                record,
                self.study.alias_profile,
                expected_sequence=1,
                key=b"different public test key material",
            )
        standalone = subject.encode_standalone("terse", 1, payload)
        with self.assertRaises(DecodeError):
            subject.open_standalone(
                standalone[:3] + "A" + standalone[4:],
                self.study.alias_profile,
                expected_sequence=1,
            )
        with self.assertRaises(ValidationError):
            subject.encode_bound_record("terse", -1, payload)

    def test_profile_costs_are_measured_but_not_silently_charged(self) -> None:
        for tokenizer in self.profiles:
            costs = self.snapshot["artifact_costs"][tokenizer.key]
            self.assertEqual(costs["selection_contract"]["bytes"], 1895)
            self.assertEqual(costs["structured_bundle"]["bytes"], 13799)
            self.assertEqual(
                costs["optimized_grammar"]["bytes"]
                + costs["optimized_profile"]["bytes"],
                1795,
            )
            self.assertGreater(costs["selection_contract"]["tokens"], 0)


if __name__ == "__main__":
    unittest.main()
