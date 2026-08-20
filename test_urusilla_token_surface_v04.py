#!/usr/bin/env python3
"""Conformance and benchmark tests for the optimal v0.4 token surface."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import unittest

from urusilla import DecodeError, MAX_FRAME_BYTES, ValidationError
from urusilla_token_surface_holdout import holdout_codebook
from urusilla_token_surface_v03 import (
    MAX_ENTRY_BYTES,
    SURFACE_CHECKSUM_SYMBOLS,
    TokenCodebook,
    _encode_bytes as encode_bytes_greedy,
)
from urusilla_wire_v02 import encode_message as encode_v02

import urusilla_token_surface_v04 as surface


HERE = Path(__file__).resolve().parent


def _crafted_codebook() -> TokenCodebook:
    source = holdout_codebook()
    entries = tuple(bytes([value]) for value in range(256)) + (
        b"abc",
        b"ab",
        b"cdef",
        b"cd",
    )
    return TokenCodebook(
        source.corpus_sha256,
        source.profile_dictionary_id,
        source.alphabet[: len(entries)],
        entries,
    )


class OptimalParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codebook = holdout_codebook()
        cls.datasets = surface.build_datasets()

    def test_counterexample_beats_greedy_longest_match(self) -> None:
        codebook = _crafted_codebook()
        raw = b"abcdef"
        greedy = encode_bytes_greedy(raw, codebook)
        optimal = surface.encode_bytes_optimal(raw, codebook)
        self.assertEqual(len(greedy), 4)
        self.assertEqual(len(optimal), 2)
        self.assertEqual(
            optimal,
            codebook.alphabet[257] + codebook.alphabet[258],
        )

    def test_equal_cost_tie_uses_lexicographically_lower_indices(self) -> None:
        codebook = _crafted_codebook()
        optimal = surface.encode_bytes_optimal(b"abcd", codebook)
        # Both [256, raw-d] and [257, 259] use two symbols; index 256 wins.
        self.assertEqual(optimal[0], codebook.alphabet[256])
        self.assertEqual(len(optimal), 2)

    def test_empty_and_type_checks(self) -> None:
        self.assertEqual(surface.encode_bytes_optimal(b"", self.codebook), "")
        with self.assertRaises(TypeError):
            surface.encode_bytes_optimal("not bytes", self.codebook)  # type: ignore[arg-type]

    def test_optimal_parser_never_exceeds_greedy_on_frozen_frames(self) -> None:
        for dataset, messages in self.datasets.items():
            for index, message in enumerate(messages):
                with self.subTest(dataset=dataset, index=index):
                    frame = encode_v02(message)
                    optimal = surface.encode_bytes_optimal(frame, self.codebook)
                    greedy = encode_bytes_greedy(frame, self.codebook)
                    self.assertLessEqual(len(optimal), len(greedy))

    def test_all_messages_are_exact_canonical_and_deterministic(self) -> None:
        for dataset, messages in self.datasets.items():
            for index, message in enumerate(messages):
                with self.subTest(dataset=dataset, index=index):
                    encoded = surface.encode_message(message, self.codebook)
                    self.assertEqual(surface.decode_message(encoded, self.codebook), message)
                    self.assertEqual(surface.encode_message(message, self.codebook), encoded)

    def test_surface_is_printable_data_only(self) -> None:
        encoded = surface.encode_message(self.datasets["development"][0], self.codebook)
        self.assertTrue(encoded.startswith(surface.SURFACE_PREFIX))
        self.assertEqual(encoded[2], self.codebook.alphabet[0])
        payload = encoded[3:-SURFACE_CHECKSUM_SYMBOLS]
        self.assertTrue(payload)
        self.assertTrue(all(not value.isascii() for value in payload))
        self.assertTrue(all(value.isprintable() and not value.isspace() for value in payload))
        self.assertNotIn("<", encoded)
        self.assertNotIn(">", encoded)

    def test_nonzero_slot_roundtrip_and_mismatch_rejection(self) -> None:
        message = self.datasets["grouped_holdout"][0]
        encoded = surface.encode_message(message, self.codebook, slot=517)
        self.assertEqual(encoded[2], self.codebook.alphabet[517])
        self.assertEqual(surface.decode_message(encoded, self.codebook, slot=517), message)
        with self.assertRaises(DecodeError):
            surface.decode_message(encoded, self.codebook, slot=0)

    def test_valid_but_nonoptimal_parse_is_rejected(self) -> None:
        message = self.datasets["development"][0]
        canonical = surface.encode_message(message, self.codebook)
        frame = encode_v02(message)
        all_raw = "".join(self.codebook.alphabet[value] for value in frame)
        noncanonical = (
            surface.SURFACE_PREFIX
            + self.codebook.alphabet[0]
            + all_raw
            + canonical[-SURFACE_CHECKSUM_SYMBOLS:]
        )
        self.assertNotEqual(noncanonical, canonical)
        with self.assertRaisesRegex(DecodeError, "not canonical"):
            surface.decode_message(noncanonical, self.codebook)

    def test_single_symbol_corruption_and_unknown_symbol_are_rejected(self) -> None:
        message = self.datasets["out_of_domain"][0]
        encoded = surface.encode_message(message, self.codebook)
        start = 3
        end = len(encoded) - SURFACE_CHECKSUM_SYMBOLS
        payload = list(encoded[start:end])
        index = len(payload) // 2
        original_index = self.codebook.alphabet.index(payload[index])
        payload[index] = self.codebook.alphabet[(original_index + 1) % len(self.codebook.entries)]
        with self.assertRaises(DecodeError):
            surface.decode_message(encoded[:start] + "".join(payload) + encoded[end:], self.codebook)
        with self.assertRaises(DecodeError):
            surface.decode_message(encoded[:end] + "A" + encoded[end:], self.codebook)

    def test_malformed_types_prefix_and_slots_are_rejected(self) -> None:
        message = self.datasets["development"][1]
        encoded = surface.encode_message(message, self.codebook)
        cases = (
            None,
            "B4" + encoded[2:],
            encoded[:-1] + "=",
            surface.SURFACE_PREFIX
            + self.codebook.alphabet[0]
            + encoded[-SURFACE_CHECKSUM_SYMBOLS:],
        )
        for value in cases:
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(DecodeError):
                    surface.decode_message(value, self.codebook)  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            surface.encode_message(message, self.codebook, slot=-1)
        with self.assertRaises(DecodeError):
            surface.decode_message(encoded, self.codebook, slot=len(self.codebook.entries))

    def test_decoded_expansion_limit_is_enforced_before_checksum(self) -> None:
        entries = tuple(bytes([value]) for value in range(256)) + (b"x" * MAX_ENTRY_BYTES,)
        limited = TokenCodebook(
            self.codebook.corpus_sha256,
            self.codebook.profile_dictionary_id,
            self.codebook.alphabet[:257],
            entries,
        )
        payload = limited.alphabet[-1] * (MAX_FRAME_BYTES // MAX_ENTRY_BYTES + 1)
        fake = (
            surface.SURFACE_PREFIX
            + limited.alphabet[0]
            + payload
            + limited.alphabet[0] * SURFACE_CHECKSUM_SYMBOLS
        )
        with self.assertRaisesRegex(DecodeError, "decoded v0.2 frame exceeds"):
            surface.decode_message(fake, limited)

    def test_neutral_codebook_wrapper_is_deterministic(self) -> None:
        text = surface.encode_codebook_capsule_text(self.codebook)
        self.assertTrue(text.startswith(surface.CODEBOOK_CAPSULE_PREFIX))
        raw = base64.urlsafe_b64decode(text[4:] + "=" * ((-len(text[4:])) % 4))
        self.assertEqual(raw, self.codebook.capsule)
        self.assertEqual(surface.encode_codebook_capsule_text(self.codebook), text)


class PinnedBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.profiles = surface.load_tokenizer_profiles(surface.default_asset_root())
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.study = surface.collect_study(cls.profiles)

    def test_four_pinned_tokenizers_are_present(self) -> None:
        self.assertEqual(
            [profile.key for profile in self.profiles],
            [
                "cl100k_base",
                "o200k_base",
                "qwen2_5_7b_instruct",
                "mistral_7b_instruct_v03",
            ],
        )

    def test_exact_frozen_v04_vectors_metrics_and_parser_counts(self) -> None:
        self.assertTrue(surface.EXPECTED_V04_TEXT_SHA256)
        self.assertTrue(surface.EXPECTED_V04_METRICS)
        self.assertTrue(surface.EXPECTED_PAYLOAD_STATS)
        self.assertEqual(
            {
                key: surface._sequence_digest(values["v04"])
                for key, values in self.study.texts.items()
            },
            surface.EXPECTED_V04_TEXT_SHA256,
        )
        self.assertEqual(
            {key: values["v04"] for key, values in self.study.metrics.items()},
            surface.EXPECTED_V04_METRICS,
        )
        self.assertEqual(
            {key: value.__dict__ for key, value in self.study.payload.items()},
            surface.EXPECTED_PAYLOAD_STATS,
        )

    def test_exactness_determinism_and_corruption_counts_are_frozen(self) -> None:
        expected_messages = {"development": 224, "grouped_holdout": 56, "out_of_domain": 10}
        self.assertEqual(self.study.exact, expected_messages)
        self.assertEqual(self.study.deterministic, expected_messages)
        self.assertEqual(
            (self.study.corruptions_attempted, self.study.corruptions_rejected),
            (surface.EXPECTED_CORRUPTION_TRIALS, surface.EXPECTED_CORRUPTION_TRIALS),
        )

    def test_report_discloses_scope_negative_cases_and_security(self) -> None:
        latency = {
            key: {
                "encode_median_ns": 1_000,
                "encode_p95_ns": 2_000,
                "decode_median_ns": 1_500,
                "decode_p95_ns": 2_500,
            }
            for key in surface.CODEC_LABELS
        }
        report = surface.render_report(self.study, latency, surface.default_asset_root())
        for required in (
            "not an end-to-end agent benchmark",
            "every unfavorable result",
            "Per-message unfavorable cases",
            "never on mean",
            "not a perfectly isolated parser ablation",
            "Token counts do not directly measure energy",
            "It does not establish the highest performance",
        ):
            self.assertIn(required, report)

    def test_published_report_exists_and_contains_current_source_digests(self) -> None:
        report_path = HERE / surface.REPORT_NAME
        self.assertTrue(report_path.is_file())
        report = report_path.read_text(encoding="utf-8")
        self.assertIn(hashlib.sha256((HERE / "urusilla_token_surface_v04.py").read_bytes()).hexdigest(), report)
        self.assertIn(hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), report)


if __name__ == "__main__":
    unittest.main()
