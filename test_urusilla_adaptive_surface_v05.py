#!/usr/bin/env python3
"""Conformance tests for receiver-aware adaptive surface v0.5."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from urusilla import DecodeError
from urusilla_token_surface_holdout import holdout_codebook
from urusilla_tokenizer_benchmark import TokenizerProfile

import urusilla_adaptive_surface_v05 as adaptive


HERE = Path(__file__).resolve().parent


def _codepoint_profile() -> TokenizerProfile:
    return TokenizerProfile(
        key="test_codepoints",
        display_name="test codepoints",
        implementation="test-only",
        vocabulary_size=0,
        fingerprint="test-only",
        count=len,
    )


class AdaptiveEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.datasets = adaptive.build_datasets()
        cls.message = cls.datasets["grouped_holdout"][0]
        cls.prepared = adaptive.prepare_message(cls.message)
        cls.profile = _codepoint_profile()

    def test_required_whole_envelopes_roundtrip_exactly(self) -> None:
        for mode, text in self.prepared.whole_envelopes.items():
            with self.subTest(mode=mode):
                self.assertTrue(text.startswith(adaptive.PREFIX + mode))
                self.assertEqual(adaptive.decode_message(text), self.message)
                self.assertEqual(
                    adaptive.encode_envelope(mode, self.prepared.whole_payloads[mode]),
                    text,
                )

    def test_lossless_fragment_envelope_roundtrip(self) -> None:
        for allow_bundle in (False, True):
            with self.subTest(allow_bundle=allow_bundle):
                candidate = adaptive.encode_fragment_envelope(
                    self.prepared, self.profile, allow_bundle=allow_bundle
                )
                self.assertEqual(candidate.mode, "F")
                self.assertEqual(len(candidate.fragment_modes), len(adaptive.FRAGMENT_FIELDS))
                self.assertEqual(adaptive.decode_message(candidate.text), self.message)
                if not allow_bundle:
                    self.assertFalse(candidate.uses_bundle)
                    self.assertNotIn("V", candidate.fragment_modes)

    def test_selector_is_deterministic_and_chooses_exact_minimum(self) -> None:
        first = adaptive.select_prepared(self.prepared, self.profile)
        second = adaptive.select_prepared(self.prepared, self.profile)
        self.assertEqual(first, second)
        self.assertEqual(
            first.candidate.tokens,
            min(candidate.tokens for candidate in first.candidates.values()),
        )
        self.assertLessEqual(first.candidate.tokens, first.required_best_tokens)
        self.assertEqual(adaptive.decode_message(first.candidate.text), self.message)

    def test_tie_break_prefers_lower_fixed_mode_rank(self) -> None:
        zero_profile = TokenizerProfile(
            key="zero",
            display_name="zero",
            implementation="test-only",
            vocabulary_size=0,
            fingerprint="zero",
            count=lambda _text: 0,
        )
        selected = adaptive.select_prepared(self.prepared, zero_profile)
        self.assertEqual(selected.candidate.mode, "J")

    def test_payload_corruption_is_rejected_before_codec_parsing(self) -> None:
        text = self.prepared.whole_envelopes["J"]
        position = adaptive.payload_start(text) + 3
        replacement = "X" if text[position] != "X" else "Y"
        mutated = text[:position] + replacement + text[position + 1 :]
        with self.assertRaisesRegex(DecodeError, "checksum mismatch"):
            adaptive.decode_message(mutated)

    def test_header_corruption_truncation_and_unknown_modes_are_rejected(self) -> None:
        text = self.prepared.whole_envelopes["E"]
        cases = (
            None,
            "",
            "B5" + text[2:],
            text[:2] + "Q" + text[3:],
            text[:4],
            text[:14] + ";" + text[15:],
            text[:3] + "!" * adaptive.CHECKSUM_CHARACTERS + text[14:],
        )
        for value in cases:
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(DecodeError):
                    adaptive.decode_message(value)  # type: ignore[arg-type]

    def test_valid_checksum_cannot_hide_noncanonical_json(self) -> None:
        canonical = self.prepared.whole_payloads["J"]
        noncanonical = canonical.replace(":", ": ", 1)
        text = adaptive.encode_envelope("J", noncanonical)
        with self.assertRaisesRegex(DecodeError, "not canonical"):
            adaptive.decode_message(text)

    def test_fragment_length_and_trailing_data_are_rejected(self) -> None:
        candidate = adaptive.encode_fragment_envelope(
            self.prepared, self.profile, allow_bundle=True
        )
        _mode, payload = adaptive._split_envelope(candidate.text)
        malformed_length = "J01:" + payload.split(":", 1)[1]
        with self.assertRaises(DecodeError):
            adaptive.decode_message(adaptive.encode_envelope("F", malformed_length))
        with self.assertRaisesRegex(DecodeError, "trailing"):
            adaptive.decode_message(adaptive.encode_envelope("F", payload + "J1:0"))

    def test_no_bundle_candidates_exclude_structured_state(self) -> None:
        selected = adaptive.select_prepared(
            self.prepared, self.profile, allow_bundle=False
        )
        self.assertNotIn("V", selected.candidates)
        self.assertFalse(any(item.uses_bundle for item in selected.candidates.values()))

    def test_cold_plan_is_exact_binary_plan_minimum(self) -> None:
        prepared = tuple(
            adaptive.prepare_message(message)
            for message in self.datasets["out_of_domain"]
        )
        plan = adaptive.plan_session(prepared, self.profile)
        self.assertEqual(
            plan.total_tokens,
            min(plan.no_bundle_total_tokens, plan.activated_total_tokens),
        )
        self.assertEqual(plan.activated_bundle, plan.activated_total_tokens < plan.no_bundle_total_tokens)


class PinnedAdaptiveBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.profiles = adaptive.load_tokenizer_profiles(adaptive.default_asset_root())
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.study = adaptive.collect_study(cls.profiles)

    def test_all_four_pinned_tokenizers_are_present(self) -> None:
        self.assertEqual(
            [profile.key for profile in self.profiles],
            [
                "cl100k_base",
                "o200k_base",
                "qwen2_5_7b_instruct",
                "mistral_7b_instruct_v03",
            ],
        )

    def test_frozen_snapshot_matches_exactly(self) -> None:
        self.assertNotEqual(adaptive.EXPECTED_SNAPSHOT_SHA256, "pending")
        self.assertEqual(
            adaptive.snapshot_sha256(adaptive._snapshot(self.study)),
            adaptive.EXPECTED_SNAPSHOT_SHA256,
        )

    def test_every_warm_choice_is_no_worse_than_required_candidates(self) -> None:
        for dataset in self.study.datasets:
            for profile in self.profiles:
                for index, selection in enumerate(
                    self.study.selections[dataset][profile.key]
                ):
                    with self.subTest(dataset=dataset, profile=profile.key, index=index):
                        required = min(
                            selection.candidates[mode].tokens
                            for mode in ("J", "E", "V")
                        )
                        self.assertLessEqual(selection.candidate.tokens, required)
                        self.assertEqual(
                            selection.candidate.tokens,
                            min(item.tokens for item in selection.candidates.values()),
                        )

    def test_exact_roundtrip_determinism_and_corruption_are_complete(self) -> None:
        total = sum(len(messages) for messages in self.study.datasets.values()) * len(self.profiles)
        self.assertEqual(self.study.exact, total)
        self.assertEqual(self.study.deterministic, total)
        self.assertEqual(self.study.corruptions_attempted, total)
        self.assertEqual(self.study.corruptions_rejected, total)

    def test_every_cold_plan_is_exact_minimum(self) -> None:
        for dataset in self.study.datasets:
            for profile in self.profiles:
                plan = self.study.sessions[dataset][profile.key]
                self.assertEqual(
                    plan.total_tokens,
                    min(plan.no_bundle_total_tokens, plan.activated_total_tokens),
                )

    def test_report_discloses_scope_fragments_and_unfavorable_costs(self) -> None:
        latency = {
            mode: {
                "encode_median_ns": 1_000,
                "encode_p95_ns": 2_000,
                "decode_median_ns": 1_500,
                "decode_p95_ns": 2_500,
            }
            for mode in ("J", "E", "V")
        }
        latency.update(
            {
                f"adaptive:{profile.key}": {
                    "encode_median_ns": 3_000,
                    "encode_p95_ns": 4_000,
                    "decode_median_ns": 1_500,
                    "decode_p95_ns": 2_500,
                }
                for profile in self.profiles
            }
        )
        report = adaptive.render_report(self.study, latency)
        for required in (
            "zero warm token regressions",
            "Cold session planning",
            "Bytes and unfavorable transport cases",
            "not claimed to be the globally optimal fragment combination",
            "No language model was invoked",
            "Task success and repair behavior remain unmeasured",
            "Adaptive selection itself adds substantial CPU work",
        ):
            self.assertIn(required, report)

    def test_published_report_has_current_source_digests(self) -> None:
        report_path = HERE / adaptive.REPORT_NAME
        self.assertTrue(report_path.is_file())
        report = report_path.read_text(encoding="utf-8")
        self.assertIn(
            hashlib.sha256((HERE / "urusilla_adaptive_surface_v05.py").read_bytes()).hexdigest(),
            report,
        )
        self.assertIn(hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), report)


if __name__ == "__main__":
    unittest.main()
