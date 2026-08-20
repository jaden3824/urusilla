#!/usr/bin/env python3
"""Determinism and integrity tests for tokenizer serialization accounting."""

from __future__ import annotations

import base64
import unittest

from urusilla import decode_message as decode_v01
from urusilla_wire_v02 import DEFAULT_PROFILE, decode_message as decode_v02, encode_capsule
import urusilla_tokenizer_benchmark as study


EXPECTED_SERIALIZATIONS = {
    "json": {
        "codepoints": 264_123,
        "utf8_bytes": 266_684,
        "raw_bytes": 266_684,
        "digest": "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc",
    },
    "base64_v01": {
        "codepoints": 235_116,
        "utf8_bytes": 235_116,
        "raw_bytes": 176_069,
        "digest": "00873eef24b4960272e4c1faf9ea7ce3dcd4604f9758edd626a7f4ea1b4c0d71",
    },
    "base64_v02_warm": {
        "codepoints": 73_376,
        "utf8_bytes": 73_376,
        "raw_bytes": 54_752,
        "digest": "d120342693577cbce4c2c81633800f4f9305205036941be0148caedd7e439657",
    },
}

EXPECTED_TOKENS = {
    "cl100k_base": (85_429, 166_025, 52_092, 1_346),
    "o200k_base": (87_494, 154_919, 48_199, 1_261),
    "qwen2_5_7b_instruct": (100_958, 169_487, 52_801, 1_375),
    "mistral_7b_instruct_v03": (119_253, 187_414, 58_432, 1_516),
}

EXPECTED_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}


class TokenizerAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus, cls.serializations, cls.capsule_text = study.build_serializations()

    def test_corpus_and_serializations_are_byte_stable(self) -> None:
        self.assertEqual(len(self.corpus), 280)
        self.assertEqual(
            study.corpus_digest(self.corpus),
            "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc",
        )
        for key, expected in EXPECTED_SERIALIZATIONS.items():
            serialization = self.serializations[key]
            with self.subTest(serialization=key):
                self.assertEqual(serialization.text_codepoints, expected["codepoints"])
                self.assertEqual(serialization.text_utf8_bytes, expected["utf8_bytes"])
                self.assertEqual(serialization.raw_binary_bytes, expected["raw_bytes"])
                self.assertEqual(serialization.digest, expected["digest"])

    def test_base64_frames_round_trip_every_message(self) -> None:
        for index, message in enumerate(self.corpus):
            with self.subTest(index=index, version="v0.1"):
                frame = base64.b64decode(
                    self.serializations["base64_v01"].texts[index], validate=True
                )
                self.assertEqual(decode_v01(frame), message)
            with self.subTest(index=index, version="v0.2"):
                frame = base64.b64decode(
                    self.serializations["base64_v02_warm"].texts[index], validate=True
                )
                self.assertEqual(decode_v02(frame), message)

    def test_profile_capsule_text_is_exact(self) -> None:
        capsule = base64.b64decode(self.capsule_text, validate=True)
        self.assertEqual(capsule, encode_capsule(DEFAULT_PROFILE))
        self.assertEqual(len(capsule), 1_402)
        self.assertEqual(len(self.capsule_text), 1_872)

    def test_open_model_asset_constants_match_download_specs(self) -> None:
        by_key = {spec.key: spec for spec in study.OPEN_TOKENIZERS}
        self.assertEqual(by_key["qwen2_5_7b_instruct"].sha256, EXPECTED_FINGERPRINTS["qwen2_5_7b_instruct"])
        self.assertEqual(by_key["mistral_7b_instruct_v03"].sha256, EXPECTED_FINGERPRINTS["mistral_7b_instruct_v03"])
        for spec in by_key.values():
            self.assertEqual(len(spec.revision), 40)
            self.assertEqual(len(spec.sha256), 64)
            self.assertTrue(spec.url.startswith("https://huggingface.co/"))

    def test_pinned_token_counts_and_vocabularies(self) -> None:
        try:
            profiles = study.load_tokenizer_profiles(study.default_asset_root())
        except RuntimeError as exc:
            self.skipTest(str(exc))
        results = study.measure_tokens(profiles, self.serializations, self.capsule_text)
        self.assertEqual({result.profile.key for result in results}, set(EXPECTED_TOKENS))
        for result in results:
            expected = EXPECTED_TOKENS[result.profile.key]
            with self.subTest(tokenizer=result.profile.key):
                self.assertEqual(result.profile.fingerprint, EXPECTED_FINGERPRINTS[result.profile.key])
                self.assertEqual(result.totals["json"], expected[0])
                self.assertEqual(result.totals["base64_v01"], expected[1])
                self.assertEqual(result.totals["base64_v02_warm"], expected[2])
                self.assertEqual(result.capsule_tokens, expected[3])

    def test_repeated_tokenization_is_deterministic(self) -> None:
        try:
            profiles = study.load_tokenizer_profiles(study.default_asset_root())
        except RuntimeError as exc:
            self.skipTest(str(exc))
        first = study.measure_tokens(profiles, self.serializations, self.capsule_text)
        second = study.measure_tokens(profiles, self.serializations, self.capsule_text)
        self.assertEqual(
            [(result.totals, result.capsule_tokens) for result in first],
            [(result.totals, result.capsule_tokens) for result in second],
        )


if __name__ == "__main__":
    unittest.main()
