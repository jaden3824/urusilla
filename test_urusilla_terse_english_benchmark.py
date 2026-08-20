#!/usr/bin/env python3
"""Frozen tests for the terse-English Urusilla comparison."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

from urusilla import DecodeError, ValidationError
from urusilla_token_surface_holdout import (
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_SHA256,
    _sequence_digest,
)

import urusilla_terse_english_benchmark as study


HERE = Path(__file__).resolve().parent


class ControlledTerseEnglishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.datasets = study.build_datasets()
        cls.texts = study.build_texts(cls.datasets)

    def test_frozen_dataset_identity_and_cardinality(self) -> None:
        from urusilla_benchmark import corpus_digest

        self.assertEqual(len(self.datasets["grouped_holdout"]), 56)
        self.assertEqual(len(self.datasets["out_of_domain"]), 10)
        self.assertEqual(
            corpus_digest(self.datasets["grouped_holdout"]), EXPECTED_HOLDOUT_SHA256
        )
        self.assertEqual(
            corpus_digest(self.datasets["out_of_domain"]), EXPECTED_OOD_SHA256
        )

    def test_terse_english_is_exact_and_deterministic_for_every_message(self) -> None:
        for dataset_key, messages in self.datasets.items():
            values = self.texts[dataset_key]["terse_english"]
            for index, (message, value) in enumerate(zip(messages, values, strict=True)):
                with self.subTest(dataset=dataset_key, index=index):
                    self.assertEqual(study.decode_terse_english(value), message)
                    self.assertEqual(study.encode_terse_english(message), value)

    def test_every_required_field_and_terminal_path_is_preserved(self) -> None:
        expected_coverage = {
            "grouped_holdout": (56, 728, 2_143),
            "out_of_domain": (10, 130, 330),
        }
        for dataset_key, messages in self.datasets.items():
            coverage = study._coverage(messages, self.texts[dataset_key]["terse_english"])
            count, required, terminals = expected_coverage[dataset_key]
            self.assertEqual(coverage.messages, count)
            self.assertEqual(coverage.exact_messages, count)
            self.assertEqual(coverage.deterministic_messages, count)
            self.assertEqual(coverage.required_field_occurrences, required)
            self.assertEqual(coverage.required_field_matches, required)
            self.assertEqual(coverage.terminal_occurrences, terminals)
            self.assertEqual(coverage.terminal_matches, terminals)
            for message in messages:
                self.assertEqual(tuple(message), study.TOP_LEVEL_FIELDS)

    def test_controlled_english_text_vectors_are_frozen(self) -> None:
        for dataset_key, expected in study.EXPECTED_TERSE_TEXT_SHA256.items():
            self.assertEqual(
                _sequence_digest(self.texts[dataset_key]["terse_english"]), expected
            )

    def test_outer_sentence_is_readable_and_field_labeled(self) -> None:
        text = self.texts["grouped_holdout"]["terse_english"][0]
        self.assertRegex(text, r"^(ASSERT|QUERY|REQUEST|PROPOSE|COMMIT|RESOLVE|RETRACT) from ")
        for label in (
            " to ",
            "; id ",
            ", session ",
            ", reply ",
            ", schema ",
            ", clock ",
            ", expires ",
            ", confidence ",
            ", expect ",
            ", meta ",
        ):
            self.assertIn(label, text)
        self.assertTrue(text.endswith("."))

    def test_decoder_rejects_malformed_noncanonical_and_invalid_messages(self) -> None:
        text = self.texts["grouped_holdout"]["terse_english"][0]
        with self.assertRaises(DecodeError):
            study.decode_terse_english(text[:-1])
        with self.assertRaises(DecodeError):
            study.decode_terse_english("INVENT from " + text.split(" from ", 1)[1])
        with self.assertRaises(DecodeError):
            study.decode_terse_english(text + " trailing")

        sender = self.datasets["grouped_holdout"][0]["sender"]
        noncanonical = text.replace(
            f" from {sender} to ", f' from "{sender}" to ', 1
        )
        with self.assertRaises(DecodeError):
            study.decode_terse_english(noncanonical)

        duplicate_kind = text.replace(": {", ": {kind=claim,", 1)
        with self.assertRaises(DecodeError):
            study.decode_terse_english(duplicate_kind)

        confidence_text = next(
            value
            for value in self.texts["grouped_holdout"]["terse_english"]
            if "confidence unknown" in value
        )
        invalid_confidence = confidence_text.replace(
            "confidence unknown", "confidence 1000001ppm"
        )
        with self.assertRaises(ValidationError):
            study.decode_terse_english(invalid_confidence)

    def test_strings_are_data_and_do_not_execute(self) -> None:
        message = copy.deepcopy(self.datasets["out_of_domain"][0])
        marker = "__import__('os').system('should-not-run')"
        message["meta"]["untrusted_text"] = marker
        text = study.encode_terse_english(message)
        self.assertIn(marker, text)
        self.assertEqual(study.decode_terse_english(text), message)

    def test_strict_break_even_is_integer_and_strict(self) -> None:
        self.assertIsNone(study.strict_break_even(10, 100, 100, 1))
        self.assertIsNone(study.strict_break_even(10, 90, 100, 1))
        self.assertEqual(study.strict_break_even(10, 100, 90, 1), 2)
        self.assertEqual(study.strict_break_even(10, 1000, 900, 10), 2)


class PinnedTokenizerAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.profiles = study.load_tokenizer_profiles(study.default_asset_root())
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.result = study.collect_study(cls.profiles)

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

    def test_exact_warm_metrics_are_frozen(self) -> None:
        self.assertEqual(self.result.metrics, study.EXPECTED_METRICS)

    def test_exact_cold_metrics_are_frozen(self) -> None:
        self.assertEqual(self.result.cold, study.EXPECTED_COLD_METRICS)

    def test_report_discloses_negative_results_and_scope(self) -> None:
        report = study.render_report(self.result, study.default_asset_root())
        for required in (
            "Negative savings are retained",
            "does **not** show that any language model understands",
            "out-of-domain corpus",
            "never on mean",
            "No LLM decoded any representation",
            "Energy cannot be inferred directly",
        ):
            self.assertIn(required, report)

    def test_published_report_matches_current_renderer(self) -> None:
        report_path = HERE / study.REPORT_NAME
        if not report_path.is_file():
            self.skipTest("report has not been generated")
        self.assertEqual(
            report_path.read_text(encoding="utf-8"),
            study.render_report(self.result, study.default_asset_root()),
        )


if __name__ == "__main__":
    unittest.main()
