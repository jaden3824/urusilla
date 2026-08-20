#!/usr/bin/env python3
"""Frozen, fail-closed tests for the v0.3 grouped holdout experiment."""

from __future__ import annotations

import base64
import copy
from pathlib import Path
import unittest

try:
    import tiktoken  # type: ignore[import-not-found]
except ImportError:
    tiktoken = None  # type: ignore[assignment]

from urusilla_benchmark import corpus_digest
from urusilla import DecodeError, ValidationError
from urusilla_token_surface_holdout import (
    EXPECTED_CODEBOOK_SHA256,
    EXPECTED_COLD_METRICS,
    EXPECTED_CORRUPTIONS,
    EXPECTED_ENGLISH_CORPUS_SHA256,
    EXPECTED_FALLBACK,
    EXPECTED_HOLDOUT_GROUPS,
    EXPECTED_HOLDOUT_GROUP_SHA256,
    EXPECTED_HOLDOUT_MESSAGES,
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_MESSAGES,
    EXPECTED_OOD_SHA256,
    EXPECTED_TEXT_SHA256,
    EXPECTED_TOTAL_GROUPS,
    EXPECTED_TRAIN_MESSAGES,
    EXPECTED_TRAIN_SHA256,
    EXPECTED_WARM_METRICS,
    TIKTOKEN_VERSION,
    _all_strings,
    _b64_v02_decode,
    _sequence_digest,
    build_english_candidate_corpus,
    build_out_of_domain_corpus,
    codec_functions,
    corruption_trials,
    encoded_texts,
    fallback_stats,
    frozen_split,
    frozen_vectors,
    holdout_codebook,
)
from urusilla_token_surface_v03 import (
    decode_codebook_capsule,
    decode_message as decode_v03,
    development_codebook,
    encode_message as encode_v03,
)
from urusilla_wire_v02 import DEFAULT_PROFILE, encode_capsule as encode_v02_capsule


HERE = Path(__file__).resolve().parent


class HoldoutSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.split = frozen_split()
        cls.ood = build_out_of_domain_corpus()
        cls.codebook = holdout_codebook()

    def test_split_cardinality_digests_and_group_isolation(self) -> None:
        self.assertEqual(len(self.split.train), EXPECTED_TRAIN_MESSAGES)
        self.assertEqual(len(self.split.holdout), EXPECTED_HOLDOUT_MESSAGES)
        self.assertEqual(self.split.all_group_count, EXPECTED_TOTAL_GROUPS)
        self.assertEqual(len(self.split.holdout_groups), EXPECTED_HOLDOUT_GROUPS)
        self.assertFalse(self.split.train_groups & self.split.holdout_groups)
        self.assertFalse(
            {message["id"] for message in self.split.train}
            & {message["id"] for message in self.split.holdout}
        )
        self.assertEqual(corpus_digest(self.split.train), EXPECTED_TRAIN_SHA256)
        self.assertEqual(corpus_digest(self.split.holdout), EXPECTED_HOLDOUT_SHA256)
        self.assertEqual(
            _sequence_digest(sorted(self.split.holdout_groups)),
            EXPECTED_HOLDOUT_GROUP_SHA256,
        )

    def test_english_projection_and_out_of_domain_vectors_are_ascii(self) -> None:
        english = build_english_candidate_corpus()
        self.assertEqual(corpus_digest(english), EXPECTED_ENGLISH_CORPUS_SHA256)
        self.assertEqual(len(self.ood), EXPECTED_OOD_MESSAGES)
        self.assertEqual(corpus_digest(self.ood), EXPECTED_OOD_SHA256)
        for corpus in (english, self.ood):
            self.assertTrue(
                all(text.isascii() for message in corpus for text in _all_strings(message))
            )
        self.assertEqual(
            {message["act"] for message in self.ood},
            {"ASSERT", "QUERY", "REQUEST", "PROPOSE", "COMMIT", "RESOLVE", "RETRACT"},
        )

    def test_codebook_is_bound_only_to_the_training_partition(self) -> None:
        self.assertEqual(self.codebook.corpus_sha256, EXPECTED_TRAIN_SHA256)
        self.assertEqual(self.codebook.profile_dictionary_id, DEFAULT_PROFILE.dictionary_id)
        self.assertEqual(self.codebook.sha256, EXPECTED_CODEBOOK_SHA256)
        capsule = self.codebook.capsule
        self.assertEqual(decode_codebook_capsule(capsule), self.codebook)
        self.assertEqual(len(capsule), EXPECTED_COLD_METRICS["codebook"]["binary_bytes"])
        self.assertEqual(
            len(encode_v02_capsule(DEFAULT_PROFILE)),
            EXPECTED_COLD_METRICS["profile"]["binary_bytes"],
        )

    def test_all_heldout_codecs_are_exact_deterministic_and_frozen(self) -> None:
        for dataset_name, messages in {
            "grouped holdout": self.split.holdout,
            "out of domain": self.ood,
        }.items():
            texts = encoded_texts(messages, self.codebook)
            functions = codec_functions(self.codebook)
            for codec_name, values in texts.items():
                encoder, decoder = functions[codec_name]
                with self.subTest(dataset=dataset_name, codec=codec_name):
                    self.assertEqual(
                        _sequence_digest(values), EXPECTED_TEXT_SHA256[dataset_name][codec_name]
                    )
                    for message, value in zip(messages, values, strict=True):
                        self.assertEqual(decoder(value), message)
                        self.assertEqual(encoder(message), value)

    def test_exact_token_and_byte_totals_are_frozen(self) -> None:
        if tiktoken is None:
            self.skipTest("missing benchmark dependency: install tiktoken==0.11.0")
        self.assertEqual(tiktoken.__version__, TIKTOKEN_VERSION)
        encodings = {
            name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")
        }
        for dataset_name, messages in {
            "grouped holdout": self.split.holdout,
            "out of domain": self.ood,
        }.items():
            texts = encoded_texts(messages, self.codebook)
            observed = {}
            for codec_name, values in texts.items():
                observed[codec_name] = {
                    "bytes": sum(len(value.encode("utf-8")) for value in values),
                    "characters": sum(len(value) for value in values),
                    **{
                        name: sum(len(encoding.encode(value)) for value in values)
                        for name, encoding in encodings.items()
                    },
                }
            self.assertEqual(observed, EXPECTED_WARM_METRICS[dataset_name])

    def test_fallback_and_corruption_vectors_are_frozen(self) -> None:
        datasets = {
            "grouped holdout": self.split.holdout,
            "out of domain": self.ood,
        }
        for dataset_name, messages in datasets.items():
            stats = fallback_stats(messages, self.codebook)
            observed = (
                stats.messages,
                stats.messages_with_raw,
                stats.payload_symbols,
                stats.raw_symbols,
                stats.frame_bytes,
                stats.raw_bytes,
            )
            self.assertEqual(observed, EXPECTED_FALLBACK[dataset_name])
        self.assertEqual(
            corruption_trials(datasets, self.codebook),
            (EXPECTED_CORRUPTIONS, EXPECTED_CORRUPTIONS),
        )

    def test_decoders_and_semantic_validation_fail_closed(self) -> None:
        surface = encode_v03(self.split.holdout[0], self.codebook)
        with self.assertRaises(DecodeError):
            decode_v03(surface, development_codebook())
        with self.assertRaises(DecodeError):
            decode_v03(surface[:-1] + "A", self.codebook)
        with self.assertRaises(DecodeError):
            _b64_v02_decode("%%%")

        capsule = bytearray(self.codebook.capsule)
        capsule[len(capsule) // 2] ^= 1
        with self.assertRaises(DecodeError):
            decode_codebook_capsule(bytes(capsule))

        commitment = next(message for message in self.ood if message["act"] == "COMMIT")
        invalid = copy.deepcopy(commitment)
        invalid["reply_to"] = None
        with self.assertRaises(ValidationError):
            encode_v03(invalid, self.codebook)

        base64_text = base64.b64encode(b"not a v0.2 frame").decode("ascii")
        with self.assertRaises(DecodeError):
            _b64_v02_decode(base64_text)

    def test_public_frozen_vector_summary(self) -> None:
        vectors = frozen_vectors()
        self.assertEqual(vectors["train_sha256"], EXPECTED_TRAIN_SHA256)
        self.assertEqual(vectors["holdout_sha256"], EXPECTED_HOLDOUT_SHA256)
        self.assertEqual(vectors["ood_sha256"], EXPECTED_OOD_SHA256)
        self.assertEqual(vectors["codebook_sha256"], EXPECTED_CODEBOOK_SHA256)

    def test_new_artifacts_are_ascii_and_hangul_free(self) -> None:
        for name in (
            "urusilla_token_surface_holdout.py",
            "test_urusilla_token_surface_holdout.py",
            "urusilla_token_surface_holdout_results.md",
        ):
            raw = (HERE / name).read_bytes()
            with self.subTest(name=name):
                self.assertTrue(raw.isascii())


if __name__ == "__main__":
    unittest.main()
