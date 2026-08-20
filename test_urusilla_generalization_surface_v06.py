#!/usr/bin/env python3
"""Conformance tests for the v0.6 generalization-first surface."""

from __future__ import annotations

import copy
from dataclasses import replace
from functools import lru_cache
import hashlib
import itertools
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from urusilla import DecodeError, ValidationError, normalize_message
from urusilla_tokenizer_benchmark import TokenizerProfile

import urusilla_generalization_surface_v06 as surface


HERE = Path(__file__).resolve().parent
PINNED_TOKENIZER_KEYS = (
    "cl100k_base",
    "o200k_base",
    "qwen2_5_7b_instruct",
    "mistral_7b_instruct_v03",
)


def _asset_root() -> Path:
    configured = os.environ.get("URUSILLA_TOKENIZER_ASSETS")
    if configured:
        return Path(configured)
    return surface.default_asset_root()


@lru_cache(maxsize=1)
def _datasets() -> dict[str, tuple[dict[str, object], ...]]:
    return surface.build_datasets()


@lru_cache(maxsize=1)
def _profile() -> surface.AliasProfile:
    return surface.derive_alias_profile(_datasets()["development"])


@lru_cache(maxsize=1)
def _pinned_study() -> surface.Study:
    profiles = surface.load_tokenizer_profiles(_asset_root())
    return surface.collect_study(profiles)


def _zero_token_profile() -> TokenizerProfile:
    return TokenizerProfile(
        key="zero_tokens",
        display_name="zero-token test profile",
        implementation="test-only",
        vocabulary_size=0,
        fingerprint="test-only-zero",
        count=lambda _text: 0,
    )


def _envelope(payload: str, profile: surface.AliasProfile) -> str:
    return (
        surface.OPTIMIZED_PREFIX
        + surface._optimized_checksum(payload, profile)
        + ":"
        + payload
    )


def _dummy_latency(study: surface.Study) -> dict[str, dict[str, int]]:
    value = {
        "encode_median_ns": 1_000,
        "encode_p95_ns": 2_000,
        "decode_median_ns": 1_500,
        "decode_p95_ns": 2_500,
    }
    result = {
        "symbolic": dict(value),
        "optimized": dict(value),
    }
    for tokenizer in study.profiles:
        result[f"v05:{tokenizer.key}"] = dict(value)
        result[f"selected:{tokenizer.key}"] = dict(value)
    return result


class TrainOnlyProfileTests(unittest.TestCase):
    def test_profile_is_frozen_and_bound_to_the_development_partition(self) -> None:
        profile = _profile()
        self.assertNotEqual(surface.EXPECTED_PROFILE_SHA256, "pending")
        self.assertEqual(
            profile.training_corpus_sha256,
            surface.EXPECTED_TRAIN_SHA256,
        )
        self.assertEqual(
            surface.profile_sha256(profile),
            surface.EXPECTED_PROFILE_SHA256,
        )
        self.assertEqual(len(profile.key_aliases), surface.MAX_KEY_ALIASES)
        self.assertEqual(len(profile.value_aliases), surface.MAX_VALUE_ALIASES)
        self.assertEqual(
            tuple(alias for alias, _value in profile.key_aliases),
            surface.ALIAS_CODES,
        )
        self.assertEqual(
            tuple(alias for alias, _value in profile.value_aliases),
            surface.ALIAS_CODES,
        )
        self.assertEqual(
            surface.profile_capsule(profile),
            surface.profile_capsule(_profile()),
        )

    def test_profile_firewall_rejects_nontraining_sequences(self) -> None:
        datasets = _datasets()
        rejected = (
            datasets["grouped_holdout"],
            datasets["out_of_domain"],
            datasets["development"] + datasets["grouped_holdout"],
            tuple(reversed(datasets["development"])),
            datasets["development"][:-1],
        )
        for messages in rejected:
            with self.subTest(messages=len(messages)):
                with self.assertRaisesRegex(RuntimeError, "frozen development"):
                    surface.derive_alias_profile(messages)

    def test_profile_aliases_are_deterministic_and_unique(self) -> None:
        first = surface.derive_alias_profile(_datasets()["development"])
        second = surface.derive_alias_profile(_datasets()["development"])
        self.assertEqual(first, second)
        self.assertEqual(len(first.key_to_alias), len(first.key_aliases))
        self.assertEqual(len(first.alias_to_key), len(first.key_aliases))
        self.assertEqual(len(first.value_to_alias), len(first.value_aliases))
        self.assertEqual(len(first.alias_to_value), len(first.value_aliases))


class OptimizedCodecBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = _profile()
        cls.message = _datasets()["grouped_holdout"][0]
        cls.encoded = surface.encode_optimized(cls.message, cls.profile)
        cls.payload = surface._optimized_payload(cls.message, cls.profile)

    def test_alias_code_and_escape_prefix_collisions_roundtrip(self) -> None:
        message = copy.deepcopy(_datasets()["development"][0])
        message["meta"]["alias_collision_probe"] = {
            "A": "A",
            "~A": "~A",
            "compute_units": "verifier.beta.agent",
        }
        canonical = normalize_message(message)
        encoded = surface.encode_optimized(canonical, self.profile)
        self.assertIn('"~A"', encoded)
        self.assertIn('"~~A"', encoded)
        self.assertEqual(surface.decode_optimized(encoded, self.profile), canonical)
        self.assertEqual(surface.encode_optimized(canonical, self.profile), encoded)

    def test_malformed_types_prefix_header_and_empty_payload_are_rejected(self) -> None:
        separator = len(surface.OPTIMIZED_PREFIX) + surface.CHECKSUM_CHARACTERS
        cases = (
            None,
            "",
            "@3" + self.encoded[2:],
            self.encoded[: surface.OPTIMIZED_HEADER_CHARACTERS],
            self.encoded[:2] + "!" + self.encoded[3:],
            self.encoded[:separator] + ";" + self.encoded[separator + 1 :],
        )
        for value in cases:
            with self.subTest(value=str(value)[:24]):
                with self.assertRaises(DecodeError):
                    surface.decode_optimized(value, self.profile)  # type: ignore[arg-type]
        with self.assertRaises(DecodeError):
            surface.decode_selected(None, self.profile)  # type: ignore[arg-type]

    def test_payload_corruption_is_rejected_by_checksum(self) -> None:
        position = surface.OPTIMIZED_HEADER_CHARACTERS + 7
        replacement = "X" if self.encoded[position] != "X" else "Y"
        mutated = self.encoded[:position] + replacement + self.encoded[position + 1 :]
        with self.assertRaisesRegex(DecodeError, "checksum mismatch"):
            surface.decode_optimized(mutated, self.profile)

    def test_valid_checksum_cannot_hide_trailing_data(self) -> None:
        with self.assertRaisesRegex(DecodeError, "trailing data"):
            surface.decode_optimized(
                _envelope(self.payload + "X", self.profile),
                self.profile,
            )

    def test_valid_checksum_cannot_hide_noncanonical_value_spelling(self) -> None:
        expected_value = self.message["expected"][0]
        rendered_value = self.profile.value_to_alias.get(
            expected_value,
            expected_value,
        )
        canonical_fragment = f"e[{rendered_value}]"
        self.assertIn(canonical_fragment, self.payload)
        noncanonical = self.payload.replace(
            canonical_fragment,
            f'e["{rendered_value}"]',
            1,
        )
        with self.assertRaisesRegex(DecodeError, "not canonical"):
            surface.decode_optimized(
                _envelope(noncanonical, self.profile),
                self.profile,
            )

    def test_profile_digest_is_part_of_checksum_domain(self) -> None:
        aliases = list(self.profile.key_aliases)
        aliases[0], aliases[1] = (
            (aliases[0][0], aliases[1][1]),
            (aliases[1][0], aliases[0][1]),
        )
        wrong_profile = replace(self.profile, key_aliases=tuple(aliases))
        self.assertNotEqual(
            surface.profile_sha256(wrong_profile),
            surface.profile_sha256(self.profile),
        )
        with self.assertRaisesRegex(DecodeError, "checksum mismatch"):
            surface.decode_optimized(self.encoded, wrong_profile)

    def test_utf8_resource_limit_is_checked_on_encode_and_decode(self) -> None:
        with patch.object(surface, "MAX_SURFACE_UTF8_BYTES", 32):
            with self.assertRaisesRegex(ValidationError, "size limit"):
                surface.encode_optimized(self.message, self.profile)
            with self.assertRaisesRegex(DecodeError, "size limit"):
                surface.decode_optimized(self.encoded, self.profile)

    def test_excessive_parser_recursion_is_rejected(self) -> None:
        match = re.search(r"(?P<key>[A-Za-z])\[(?P<value>[A-Za-z])\]", self.payload)
        self.assertIsNotNone(match)
        assert match is not None
        depth = sys.getrecursionlimit() + 50
        nested = "[" * depth + "A" + "]" * depth
        recursive_payload = (
            self.payload[: match.start()]
            + match.group("key")
            + nested
            + self.payload[match.end() :]
        )
        with self.assertRaisesRegex(DecodeError, "parser resources"):
            surface.decode_optimized(
                _envelope(recursive_payload, self.profile),
                self.profile,
            )

    def test_selected_decoder_dispatches_all_three_candidate_families(self) -> None:
        prepared = surface.prepare_message(self.message, self.profile)
        values = (
            prepared.adaptive.whole_envelopes["J"],
            prepared.symbolic_text,
            prepared.optimized_text,
        )
        for encoded in values:
            with self.subTest(prefix=encoded[:2]):
                self.assertEqual(
                    surface.decode_selected(encoded, self.profile),
                    self.message,
                )

    def test_zero_token_tie_retains_the_v05_candidate(self) -> None:
        prepared = surface.prepare_message(self.message, self.profile)
        selection = surface.select_prepared(prepared, _zero_token_profile())
        self.assertEqual(selection.candidate.mode, "v05")
        self.assertEqual(selection.candidate.tokens, 0)


class PinnedGeneralizationStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.study = _pinned_study()
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.profiles = cls.study.profiles

    def test_all_four_pinned_tokenizers_are_present_in_order(self) -> None:
        self.assertEqual(
            tuple(profile.key for profile in self.profiles),
            PINNED_TOKENIZER_KEYS,
        )
        self.assertEqual(
            {profile.key: profile.fingerprint for profile in self.profiles},
            surface.EXPECTED_TOKENIZER_FINGERPRINTS,
        )

    def test_frozen_snapshot_matches_exactly(self) -> None:
        self.assertNotEqual(surface.EXPECTED_SNAPSHOT_SHA256, "pending")
        self.assertEqual(
            surface.snapshot_sha256(surface.study_snapshot(self.study)),
            surface.EXPECTED_SNAPSHOT_SHA256,
        )

    def test_all_290_readable_surfaces_roundtrip_and_reencode_exactly(self) -> None:
        prepared = tuple(
            item
            for messages in self.study.prepared.values()
            for item in messages
        )
        self.assertEqual(len(prepared), 290)
        for index, item in enumerate(prepared):
            with self.subTest(index=index, mode="existing"):
                self.assertEqual(surface.decode_symbolic(item.symbolic_text), item.message)
                self.assertEqual(surface.encode_symbolic(item.message), item.symbolic_text)
            with self.subTest(index=index, mode="optimized"):
                self.assertEqual(
                    surface.decode_optimized(
                        item.optimized_text,
                        self.study.alias_profile,
                    ),
                    item.message,
                )
                self.assertEqual(
                    surface.encode_optimized(item.message, self.study.alias_profile),
                    item.optimized_text,
                )

    def test_frozen_exact_determinism_and_corruption_counts_are_complete(self) -> None:
        self.assertEqual(
            (self.study.exact_existing, self.study.exact_optimized),
            (290, 290),
        )
        self.assertEqual(
            (
                self.study.deterministic_existing,
                self.study.deterministic_optimized,
            ),
            (290, 290),
        )
        self.assertEqual(self.study.exact_selected, 1_160)
        self.assertEqual(self.study.deterministic_selected, 1_160)
        expected = {"symbolic": 290, "optimized": 290, "selected": 1_160}
        self.assertEqual(self.study.corruptions_attempted, expected)
        self.assertEqual(self.study.corruptions_rejected, expected)

    def test_every_one_of_1160_warm_choices_is_an_exact_no_regression_minimum(self) -> None:
        checked = 0
        for dataset, messages in self.study.prepared.items():
            for tokenizer in self.profiles:
                values = self.study.selections[dataset][tokenizer.key]
                self.assertEqual(len(values), len(messages))
                for index, (prepared, selection) in enumerate(
                    zip(messages, values, strict=True)
                ):
                    with self.subTest(
                        dataset=dataset,
                        tokenizer=tokenizer.key,
                        index=index,
                    ):
                        self.assertLessEqual(
                            selection.candidate.tokens,
                            selection.baseline.tokens,
                        )
                        self.assertEqual(
                            selection.candidate.tokens,
                            min(
                                candidate.tokens
                                for candidate in selection.candidates.values()
                            ),
                        )
                        self.assertEqual(
                            surface.decode_selected(
                                selection.candidate.text,
                                self.study.alias_profile,
                            ),
                            prepared.message,
                        )
                    checked += 1
        self.assertEqual(checked, 1_160)

    def test_ood_aggregate_improves_for_every_receiver(self) -> None:
        snapshot = surface.study_snapshot(self.study)
        expected_savings = {
            "cl100k_base": 161,
            "o200k_base": 144,
            "qwen2_5_7b_instruct": 127,
            "mistral_7b_instruct_v03": 65,
        }
        for tokenizer in self.profiles:
            totals = snapshot["token_totals"]["out_of_domain"][tokenizer.key]
            with self.subTest(tokenizer=tokenizer.key):
                self.assertLess(totals["selected"], totals["v05"])
                self.assertEqual(
                    totals["v05"] - totals["selected"],
                    expected_savings[tokenizer.key],
                )

    def test_every_cold_plan_enumerates_all_states_and_cannot_regress(self) -> None:
        expected_states = set(itertools.product((False, True), repeat=3))
        for dataset in self.study.datasets:
            for tokenizer in self.profiles:
                plan = self.study.cold_plans[dataset][tokenizer.key]
                states = {
                    (
                        option.structured_bundle,
                        option.symbolic_grammar,
                        option.optimized_profile,
                    )
                    for option in plan.options
                }
                with self.subTest(dataset=dataset, tokenizer=tokenizer.key):
                    self.assertEqual(len(plan.options), 8)
                    self.assertEqual(states, expected_states)
                    self.assertEqual(
                        plan.selected.total_tokens,
                        min(option.total_tokens for option in plan.options),
                    )
                    v05_only = [
                        option
                        for option in plan.options
                        if not option.symbolic_grammar
                        and not option.optimized_profile
                    ]
                    self.assertEqual(
                        plan.baseline_total_tokens,
                        min(option.total_tokens for option in v05_only),
                    )
                    self.assertLessEqual(
                        plan.selected.total_tokens,
                        plan.baseline_total_tokens,
                    )

    def test_cold_artifacts_are_charged_once_per_enabled_shared_state(self) -> None:
        for tokenizer in self.profiles:
            artifacts = surface.cold_artifact_metrics(
                tokenizer,
                self.study.alias_profile,
            )
            plan = self.study.cold_plans["development"][tokenizer.key]
            for option in plan.options:
                expected_tokens = (
                    (artifacts["structured_bundle"][0] if option.structured_bundle else 0)
                    + (artifacts["symbolic_grammar"][0] if option.symbolic_grammar else 0)
                    + (artifacts["optimized_grammar"][0] if option.optimized_profile else 0)
                    + (artifacts["optimized_profile"][0] if option.optimized_profile else 0)
                )
                expected_bytes = (
                    (artifacts["structured_bundle"][1] if option.structured_bundle else 0)
                    + (artifacts["symbolic_grammar"][1] if option.symbolic_grammar else 0)
                    + (artifacts["optimized_grammar"][1] if option.optimized_profile else 0)
                    + (artifacts["optimized_profile"][1] if option.optimized_profile else 0)
                )
                with self.subTest(
                    tokenizer=tokenizer.key,
                    structured=option.structured_bundle,
                    symbolic=option.symbolic_grammar,
                    optimized=option.optimized_profile,
                ):
                    self.assertEqual(option.cold_tokens, expected_tokens)
                    self.assertEqual(option.cold_bytes, expected_bytes)
                    self.assertEqual(
                        option.message_tokens,
                        sum(choice.tokens for choice in option.choices),
                    )
                    self.assertEqual(
                        option.total_tokens,
                        option.cold_tokens + option.message_tokens,
                    )

    def test_rendered_report_is_english_and_discloses_required_boundaries(self) -> None:
        report = surface.render_report(self.study, _dummy_latency(self.study))
        self.assertIsNone(re.search(r"[\uac00-\ud7a3]", report))
        for required in (
            "zero warm token regressions",
            "No language model, network service, or paid API was invoked",
            "Warm out-of-domain improvements did **not** amortize",
            "raw token references and do not carry equivalent checksum framing",
            "Token reduction does not directly establish lower energy",
            "No state-of-the-art or task-success claim is made",
            "all eight combinations",
            "no shared artifact is double-counted",
        ):
            with self.subTest(required=required):
                self.assertIn(required, report)

    def test_published_report_has_current_source_digests_when_present(self) -> None:
        report_path = HERE / surface.REPORT_NAME
        if not report_path.is_file():
            self.skipTest("the published report has not been generated yet")
        report = report_path.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[\uac00-\ud7a3]", report))
        self.assertIn(
            hashlib.sha256(
                (HERE / "urusilla_generalization_surface_v06.py").read_bytes()
            ).hexdigest(),
            report,
        )
        self.assertIn(hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), report)


if __name__ == "__main__":
    unittest.main()
