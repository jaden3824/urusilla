"""Offline conformance and safety tests for the experimental v0.7 surface."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
import re
import tempfile
import unittest
from unittest import mock

from urusilla import DecodeError, ValidationError
from urusilla_token_surface_holdout import (
    build_out_of_domain_corpus,
    frozen_split,
    holdout_codebook,
)

import performance_v07.receiver_negotiated_surface_v07 as v07


class ReceiverNegotiatedSurfaceV07Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        split = frozen_split()
        cls.development = tuple(split.train)
        cls.holdout = tuple(split.holdout)
        cls.ood = tuple(build_out_of_domain_corpus())
        cls.study = v07.collect_study()
        cls.receivers = cls.study.profile_set.receivers
        cls.profile_set = cls.study.profile_set
        cls.sample = cls.development[0]

    def assert_decode_rejected(self, text: str, profile: v07.ReceiverProfile) -> None:
        with self.assertRaises((DecodeError, ValidationError, ValueError)):
            v07.decode_message(text, profile)

    def test_training_firewall_accepts_only_exact_ordered_development(self) -> None:
        self.assertEqual(len(self.development), v07.EXPECTED_DEVELOPMENT_MESSAGES)
        self.assertEqual(
            len(v07._training_frames(self.development)),
            v07.EXPECTED_DEVELOPMENT_MESSAGES,
        )
        invalid_sequences = (
            self.development[:-1],
            tuple(reversed(self.development)),
            self.holdout,
            self.ood,
            self.development + self.holdout,
        )
        for values in invalid_sequences:
            with self.subTest(length=len(values)):
                with self.assertRaises(RuntimeError):
                    v07._training_frames(values)

    def test_declared_sizes_byte_fallback_and_deterministic_profiles(self) -> None:
        expected_raw = tuple(bytes([value]) for value in range(256))
        self.assertEqual(self.profile_set.entries[:256], expected_raw)
        self.assertEqual(self.profile_set.entries[:1_024], holdout_codebook().entries)
        self.assertEqual(len(self.profile_set.entries), 4_096)
        self.assertEqual(len(set(self.profile_set.entries)), 4_096)
        self.assertTrue(all(1 <= len(value) <= v07.MAX_ENTRY_BYTES for value in self.profile_set.entries))
        repeated = v07.derive_profiles(self.development, self.receivers)
        for receiver in self.receivers:
            self.assertGreaterEqual(receiver.safe_boundary_candidate_count, 4_096)
            for size in v07.PROFILE_SIZES:
                first = self.profile_set.profiles[receiver.key][size]
                second = repeated.profiles[receiver.key][size]
                self.assertEqual(len(first.entries), size)
                self.assertEqual(len(first.symbols), size)
                self.assertEqual(first.capsule, second.capsule)

    def test_strict_scalar_preflight_and_boundary_filter_capacity(self) -> None:
        by_key = {receiver.key: receiver for receiver in self.receivers}
        self.assertLess(by_key["cl100k_base"].strict_scalar_count, 2_048)
        self.assertLess(by_key["mistral_7b_instruct_v03"].strict_scalar_count, 1_024)
        for receiver in self.receivers:
            self.assertGreater(receiver.pre_filter_boundary_candidate_count, receiver.safe_boundary_candidate_count)
            self.assertEqual(
                receiver.prompt_risk_terms_removed,
                receiver.pre_filter_boundary_candidate_count - receiver.safe_boundary_candidate_count,
            )
            self.assertGreater(receiver.prompt_risk_terms_removed, 0)
            for symbol, token_id in receiver.symbol_candidates:
                self.assertTrue(v07._passes_prompt_risk_filter(symbol))
                self.assertEqual(receiver.encode_ids(symbol), [token_id])
                self.assertNotIn(symbol[1:].casefold(), v07._PROMPT_RISK_TERMS)

    def test_symbol_grammar_rejects_empty_control_and_ambiguous_forms(self) -> None:
        accepted = (" A", " z9", " 007")
        rejected = (
            "",
            " ",
            "word",
            " word word",
            "\tword",
            "\nword",
            "\u00a0word",
            " word!",
            " <system>",
            " system",
            " instructions",
            " password",
            " \ud800",
        )
        for value in accepted:
            self.assertTrue(v07._is_boundary_symbol(value))
        for value in rejected:
            self.assertFalse(v07._passes_prompt_risk_filter(value))

    def test_alphabet_concatenation_and_framing_prefixes(self) -> None:
        total = 0
        for receiver in self.receivers:
            for profile in self.profile_set.profiles[receiver.key].values():
                total += v07.verify_profile_concatenation(profile)
        self.assertEqual(total, 143_360)

    def test_profile_capsule_roundtrip_binding_and_corruption(self) -> None:
        self.assertEqual(v07.PROFILE_MAGIC, b"URR7P\x01")
        for receiver in self.receivers:
            for profile in self.profile_set.profiles[receiver.key].values():
                decoded = v07.decode_profile_capsule(profile.capsule, receiver)
                self.assertEqual(decoded.capsule, profile.capsule)
                text = v07.encode_profile_capsule_text(profile)
                self.assertEqual(v07.decode_profile_capsule_text(text, receiver).capsule, profile.capsule)

        profile = self.profile_set.profiles[self.receivers[0].key][4_096]
        wrong_magic = bytes([profile.capsule[0] ^ 1]) + profile.capsule[1:]
        with self.assertRaises(DecodeError):
            v07.decode_profile_capsule(wrong_magic, self.receivers[0])
        damaged = profile.capsule[:-1] + bytes([profile.capsule[-1] ^ 1])
        with self.assertRaises(DecodeError):
            v07.decode_profile_capsule(damaged, self.receivers[0])
        with self.assertRaises(DecodeError):
            v07.decode_profile_capsule(profile.capsule, self.receivers[1])

        entries = list(profile.entries)
        entries[256] = b"\xff" * v07.MAX_ENTRY_BYTES
        self.assertNotIn(entries[256], profile.entries)
        forged = replace(profile, entries=tuple(entries))
        with self.assertRaises(DecodeError):
            v07.decode_profile_capsule(forged.capsule, self.receivers[0])
        with self.assertRaises(ValidationError):
            v07.encode_message(self.sample, forged)

    def test_all_profiles_exact_and_canonical_on_sample(self) -> None:
        for receiver in self.receivers:
            for profile in self.profile_set.profiles[receiver.key].values():
                text = v07.encode_message(self.sample, profile)
                self.assertEqual(v07.decode_message(text, profile), self.sample)
                self.assertEqual(v07.encode_message(v07.decode_message(text, profile), profile), text)
                payload, _checksum = v07._split_surface(text, profile)
                symbols = tuple(re.findall(r" [A-Za-z0-9]+", payload))
                expected = [profile.token_ids[profile.symbol_to_index[item]] for item in symbols]
                self.assertEqual(receiver.encode_ids(payload), expected)
                header = v07.SURFACE_PREFIX + profile.content_tag + ":"
                prefix = receiver.encode_ids(header) + expected
                self.assertEqual(receiver.encode_ids(text)[: len(prefix)], prefix)

    def test_nonoptimal_all_raw_reencoding_is_rejected(self) -> None:
        profile = self.profile_set.profiles[self.receivers[0].key][4_096]
        frame = v07.encode_v02(self.sample)
        optimal = v07.optimal_indices(frame, profile.entries)
        self.assertLess(len(optimal), len(frame))
        nonoptimal = v07._surface_from_indices(frame, tuple(frame), profile)
        self.assert_decode_rejected(nonoptimal, profile)

    def test_surface_corruption_wrong_profile_and_unknown_symbol_fail_closed(self) -> None:
        receiver = self.receivers[0]
        profile = self.profile_set.profiles[receiver.key][4_096]
        other = self.profile_set.profiles[receiver.key][2_048]
        text = v07.encode_message(self.sample, profile)
        mutated = v07._mutate_payload_symbol(text, profile, "unit-test")
        self.assert_decode_rejected(mutated, profile)
        self.assert_decode_rejected(text[:-1] + ("A" if text[-1] != "A" else "B"), profile)
        self.assert_decode_rejected(text, other)
        payload, checksum = v07._split_surface(text, profile)
        first = re.match(r" [A-Za-z0-9]+", payload)
        assert first is not None
        unknown = " DefinitelyNotAProfileSymbol999999999"
        damaged = (
            v07.SURFACE_PREFIX
            + profile.content_tag
            + ":"
            + unknown
            + payload[first.end() :]
            + "~"
            + checksum
        )
        self.assert_decode_rejected(damaged, profile)

    def test_whitespace_and_case_normalization_fail_closed(self) -> None:
        for receiver in self.receivers:
            for profile in self.profile_set.profiles[receiver.key].values():
                text = v07.encode_message(self.sample, profile)
                payload, checksum = v07._split_surface(text, profile)
                header = v07.SURFACE_PREFIX + profile.content_tag + ":"
                boundaries = [match.start() for match in re.finditer(" ", payload)]
                self.assertGreater(len(boundaries), 1)
                second = boundaries[1]
                variants = (
                    header + payload[1:] + "~" + checksum,
                    header + "\t" + payload[1:] + "~" + checksum,
                    header + "\n" + payload[1:] + "~" + checksum,
                    header + "\u00a0" + payload[1:] + "~" + checksum,
                    header + payload[:second] + payload[second + 1 :] + "~" + checksum,
                    header + payload[:second] + "  " + payload[second + 1 :] + "~" + checksum,
                )
                for variant in variants:
                    self.assertNotEqual(variant, text)
                    self.assert_decode_rejected(variant, profile)

                position = next(
                    index for index, value in enumerate(payload) if value.isalpha()
                )
                replacement = payload[position].swapcase()
                case_changed = (
                    header
                    + payload[:position]
                    + replacement
                    + payload[position + 1 :]
                    + "~"
                    + checksum
                )
                self.assertNotEqual(case_changed, text)
                self.assert_decode_rejected(case_changed, profile)

    def test_expansion_bound_rejects_before_underlying_decode(self) -> None:
        profile = self.profile_set.profiles[self.receivers[0].key][4_096]
        largest = max(len(entry) for entry in profile.entries)
        index = next(
            position for position, entry in enumerate(profile.entries) if len(entry) == largest
        )
        symbol = profile.symbols[index]
        count = 4
        oversized = (
            v07.SURFACE_PREFIX
            + profile.content_tag
            + ":"
            + symbol * count
            + "~AAAAAAAAAAA"
        )
        with mock.patch.object(v07, "MAX_FRAME_BYTES", largest * 3):
            self.assert_decode_rejected(oversized, profile)

        valid = v07.encode_message(self.sample, profile)
        with mock.patch.object(v07, "MAX_PAYLOAD_SYMBOLS", 1):
            self.assert_decode_rejected(valid, profile)

    def test_decoder_type_and_unpaired_surrogate_errors_fail_closed(self) -> None:
        profile = self.profile_set.profiles[self.receivers[0].key][1_024]
        malformed_surface = v07.SURFACE_PREFIX + profile.content_tag + ": \ud800~AAAAAAAAAAA"
        with self.assertRaises(DecodeError):
            v07.decode_message(malformed_surface, profile)
        with self.assertRaises(DecodeError):
            v07.decode_profile_capsule_text(v07.CAPSULE_TEXT_PREFIX + "\ud800", self.receivers[0])
        with self.assertRaises(DecodeError):
            v07.decode_selected(None, self.study.alias_profile, self.profile_set.profiles[self.receivers[0].key])  # type: ignore[arg-type]

    def test_offline_tiktoken_preflight_rejects_missing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"TIKTOKEN_CACHE_DIR": directory}):
                with self.assertRaises(RuntimeError):
                    v07._verify_tiktoken_cache_offline()
        verified = v07._verify_tiktoken_cache_offline()
        self.assertEqual(set(verified), {"cl100k_base", "o200k_base"})

    def test_profile_object_rejects_changed_entries_symbols_and_token_ids(self) -> None:
        profile = self.profile_set.profiles[self.receivers[0].key][1_024]
        entries = list(profile.entries)
        entries[256] = b""
        with self.assertRaises(ValidationError):
            replace(profile, entries=tuple(entries))
        symbols = list(profile.symbols)
        symbols[0] = " system"
        with self.assertRaises(ValidationError):
            replace(profile, symbols=tuple(symbols))
        token_ids = list(profile.token_ids)
        token_ids[0] = profile.receiver.vocabulary_size
        with self.assertRaises(ValidationError):
            replace(profile, token_ids=tuple(token_ids))

    def test_optimizer_tie_break_and_input_bound(self) -> None:
        entries = tuple(bytes([value]) for value in range(256)) + (b"ab", b"bc")
        # Both `a` + `bc` and `ab` + `c` use two symbols.  The lower current
        # index (`a` == 97) is the frozen deterministic tie break.
        self.assertEqual(v07.optimal_indices(b"abc", entries), (97, 257))
        with self.assertRaises(ValidationError):
            v07.optimal_indices(b"x" * (v07.MAX_FRAME_BYTES + 1), self.profile_set.entries)

    def test_break_even_is_strict_and_off_by_one_safe(self) -> None:
        self.assertIsNone(v07.strict_break_even(10, 100, 100, 10))
        self.assertIsNone(v07.strict_break_even(10, 100, 101, 10))
        value = v07.strict_break_even(10, 100, 90, 10)
        self.assertEqual(value, 11)
        self.assertFalse(10 + (value - 1) * 9 < (value - 1) * 10)
        self.assertTrue(10 + value * 9 < value * 10)

    def test_guarded_tie_prefers_v06_and_cold_plan_retains_v06(self) -> None:
        receiver = self.receivers[0]
        profiles = self.profile_set.profiles[receiver.key]
        alias = v07.derive_alias_profile(self.development)
        prepared = v07.prepare_message(self.sample, alias, profiles)
        constant = replace(receiver, count=lambda _text: 1)
        selection = v07.select_prepared(prepared, constant)
        self.assertEqual(selection.candidate.mode, "v06")
        plan = v07.plan_cold_session((prepared,), receiver, alias, profiles)
        self.assertEqual(len(plan.options), 64)
        self.assertLessEqual(plan.selected.total_tokens, plan.v06_baseline_total)

        wrong_receiver = self.receivers[1]
        with self.assertRaises(ValidationError):
            v07.select_prepared(prepared, wrong_receiver)
        wrong_fingerprint = replace(receiver, fingerprint="0" * 64)
        with self.assertRaises(ValidationError):
            v07.select_prepared(prepared, wrong_fingerprint)

        with mock.patch.object(v07, "MAX_PAYLOAD_SYMBOLS", 1):
            bounded = v07.prepare_message(self.sample, alias, profiles)
        self.assertFalse(bounded.v07_texts)
        self.assertEqual(set(bounded.v07_ineligible), set(v07.PROFILE_SIZES))
        self.assertEqual(v07.select_prepared(bounded, receiver).candidate.mode, "v06")

    def test_full_frozen_study_and_all_unfavorable_results(self) -> None:
        self.assertEqual(
            {name: len(values) for name, values in self.study.datasets.items()},
            {
                "development": v07.EXPECTED_DEVELOPMENT_MESSAGES,
                "grouped_holdout": v07.EXPECTED_GROUPED_HOLDOUT_MESSAGES,
                "out_of_domain": v07.EXPECTED_OOD_MESSAGES,
            },
        )
        self.assertEqual(self.study.direct_exact, 3_480)
        self.assertEqual(self.study.direct_deterministic, 3_480)
        self.assertEqual(self.study.selected_exact, 1_160)
        self.assertEqual(self.study.selected_deterministic, 1_160)
        self.assertEqual(
            (self.study.corruptions_rejected, self.study.corruptions_attempted),
            (3_480, 3_480),
        )
        snapshot = v07.study_snapshot(self.study)
        self.assertEqual(v07.snapshot_sha256(snapshot), v07.EXPECTED_SNAPSHOT_SHA256)
        self.assertTrue(snapshot["regression_records"])
        for receiver in self.receivers:
            key = receiver.key
            for size in v07.PROFILE_SIZES:
                self.assertEqual(
                    snapshot["per_message"]["out_of_domain"][key][str(size)]["regressed"],
                    10,
                )
            for dataset in self.study.datasets:
                selected = self.study.selections[dataset][key]
                self.assertTrue(
                    all(value.candidate.tokens <= value.baseline.tokens for value in selected)
                )
                plan = self.study.cold_plans[dataset][key]
                self.assertEqual(len(plan.options), 64)
                self.assertLessEqual(plan.selected.total_tokens, plan.v06_baseline_total)

    def test_profile_and_entry_digests_are_concrete_when_frozen(self) -> None:
        digest = hashlib.sha256(
            b"".join(v07._uvarint(len(entry)) + entry for entry in self.profile_set.entries)
        ).hexdigest()
        self.assertNotEqual(v07.EXPECTED_SNAPSHOT_SHA256, "pending")
        self.assertEqual(digest, v07.EXPECTED_BYTE_ENTRY_SHA256)
        for receiver in self.receivers:
            for size, profile in self.profile_set.profiles[receiver.key].items():
                self.assertEqual(profile.sha256, v07.EXPECTED_PROFILE_SHA256[receiver.key][size])


if __name__ == "__main__":
    unittest.main()
