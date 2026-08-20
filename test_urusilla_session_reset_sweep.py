from __future__ import annotations

import platform
from pathlib import Path
import unittest

import urusilla_session_reset_sweep as sweep


EXPECTED_GRID = (
    1,
    2,
    4,
    5,
    7,
    8,
    10,
    14,
    16,
    20,
    28,
    32,
    35,
    40,
    56,
    64,
    70,
    128,
    140,
    256,
    280,
)
EXPECTED_MATRIX_SHA256 = "f3d1376dffbf7f51c2fe02fff724cdc7338c7220afd6a9a731d75d88369cbdd5"
FROZEN_MEASUREMENT_RUNTIME = (
    platform.python_implementation() == "CPython"
    and platform.python_version() == "3.12.14"
    and platform.platform() == "macOS-15.0-arm64-arm-64bit"
)
FROZEN_RUNTIME_REASON = (
    "exact compressed-byte anchors are frozen on "
    "CPython 3.12.14 / macOS-15.0-arm64-arm-64bit"
)
EXPECTED_ANCHORS = {
    (1, "canonical JSON", "gzip-6"): (
        173023,
        173023,
        "4e9a796ffad858da43c1d05f70877f33d08ce607fcf85ef307b30268ffa517f9",
        "4e9a796ffad858da43c1d05f70877f33d08ce607fcf85ef307b30268ffa517f9",
    ),
    (1, "checked JSON", "gzip-6"): (
        180772,
        180772,
        "d019b4483c5f17185ad482ba59aff11ea9a5677f08557a66ed349402767ab7eb",
        "d019b4483c5f17185ad482ba59aff11ea9a5677f08557a66ed349402767ab7eb",
    ),
    (1, "project v0.2", "gzip-6"): (
        64096,
        456656,
        "ec40a0d3f810b1fc88f791858c09eefdaf0372b6c67f13c907f527db94a23edb",
        "b9b192ab24bb51e4be9e2d2ca0999a7aff3267b175c6614f66ac2ebb37c111e4",
    ),
    (280, "canonical JSON", "brotli-11"): (
        24088,
        24088,
        "4a1762a46a8e1a8045ffc996f95048b2a7b7beb71da5509548c70bcfac31ee2e",
        "4a1762a46a8e1a8045ffc996f95048b2a7b7beb71da5509548c70bcfac31ee2e",
    ),
    (280, "checked JSON", "brotli-11"): (
        29237,
        29237,
        "6cd7cf90e7d912703a69f9f805b97cb84d0fad63b83188f3752746d878325613",
        "6cd7cf90e7d912703a69f9f805b97cb84d0fad63b83188f3752746d878325613",
    ),
    (280, "project v0.2", "brotli-11"): (
        25173,
        26575,
        "2479ea724bf0b9756f5083f97d756c45d3a0344e228b24250c929b79ef7c44ff",
        "cc86264da9ab03d97dda87049ced81756b8abf5b7cb2a51a5f3cff41d028bb9f",
    ),
}


@unittest.skipUnless(
    sweep.stream_baseline.dependencies_available(require_pins=True),
    "pinned compression dependencies are unavailable",
)
class SessionResetSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results, cls.corpus = sweep.measure(repeats=1)
        cls.report = sweep.render_report(cls.results, cls.corpus)

    def test_grid_is_logarithmic_plus_every_corpus_divisor(self) -> None:
        self.assertEqual(sweep.CHUNK_SIZES, EXPECTED_GRID)
        self.assertTrue(set(sweep.DIVISOR_GRID).issubset(sweep.CHUNK_SIZES))
        self.assertTrue(set(sweep.POWER_OF_TWO_GRID).issubset(sweep.CHUNK_SIZES))
        self.assertEqual(sweep.CHUNK_SIZES[0], 1)
        self.assertEqual(sweep.CHUNK_SIZES[-1], sweep.MESSAGE_COUNT)

    def test_complete_matrix_is_exact_and_deterministic(self) -> None:
        self.assertEqual(len(self.results), 21 * 3 * 6)
        self.assertTrue(all(result.cached_exact for result in self.results))
        self.assertTrue(all(result.cold_exact for result in self.results))
        self.assertTrue(all(result.cached_deterministic for result in self.results))
        self.assertTrue(all(result.cold_deterministic for result in self.results))

    @unittest.skipUnless(FROZEN_MEASUREMENT_RUNTIME, FROZEN_RUNTIME_REASON)
    def test_deterministic_matrix_digest(self) -> None:
        self.assertEqual(
            sweep.measurement_digest(self.results), EXPECTED_MATRIX_SHA256
        )

    @unittest.skipUnless(FROZEN_MEASUREMENT_RUNTIME, FROZEN_RUNTIME_REASON)
    def test_frozen_endpoint_anchors(self) -> None:
        observed = {
            (result.chunk_size, result.family, result.compression): (
                result.cached_bytes,
                result.cold_bytes,
                result.cached_sha256,
                result.cold_sha256,
            )
            for result in self.results
        }
        for key, expected in EXPECTED_ANCHORS.items():
            self.assertEqual(observed[key], expected)

    def test_profile_capsule_is_charged_once_per_cold_reset(self) -> None:
        capsule_bytes = len(sweep.encode_capsule(sweep.DEFAULT_PROFILE))
        for result in self.results:
            difference = result.cold_bytes - result.cached_bytes
            if result.family == sweep.PROJECT_FAMILY:
                self.assertEqual(difference, result.chunk_count * capsule_bytes)
            else:
                self.assertEqual(difference, 0)

    def test_outer_framing_and_setup_contract_fail_closed(self) -> None:
        family = next(
            family
            for family in sweep.stream_baseline.session_families()
            if family.name == "canonical JSON"
        )
        compression = next(
            profile for profile in sweep.study_profiles() if profile.name == "gzip-6"
        )
        encoded = sweep.encode_exchange(
            self.corpus,
            family,
            compression,
            sweep.MESSAGE_COUNT,
            cold_profile=True,
        )
        with self.assertRaisesRegex(ValueError, "invalid payload length"):
            sweep.decode_exchange(
                encoded[:-1], family, compression, cold_profile=True
            )

        raw = family.encode(self.corpus)
        unexpected_setup = sweep._pack_outer(b"unexpected", compression.encode(raw))
        with self.assertRaisesRegex(ValueError, "unexpected setup object"):
            sweep.decode_exchange(
                unexpected_setup, family, compression, cold_profile=True
            )

    def test_cold_project_decode_requires_the_transmitted_capsule(self) -> None:
        family = next(
            family
            for family in sweep.stream_baseline.session_families()
            if family.name == sweep.PROJECT_FAMILY
        )
        compression = next(
            profile for profile in sweep.study_profiles() if profile.name == "zstd-3"
        )
        cached = sweep.encode_exchange(
            self.corpus,
            family,
            compression,
            sweep.MESSAGE_COUNT,
            cold_profile=False,
        )
        with self.assertRaisesRegex(ValueError, "missing its profile capsule"):
            sweep.decode_exchange(
                cached, family, compression, cold_profile=True
            )

    def test_report_is_english_and_preserves_negative_scope(self) -> None:
        self.assertFalse(any("\uac00" <= char <= "\ud7a3" for char in self.report))
        normalized = " ".join(self.report.split())
        self.assertIn("not a task-utility result or a state-of-the-art claim", normalized)
        self.assertIn("Bare JSON has no independent per-record checksum", normalized)
        self.assertIn("No result establishes a world record", normalized)
        self.assertIn(sweep.measurement_digest(self.results), normalized)
        published = Path(__file__).with_name("SESSION_RESET_SWEEP_RESULTS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(EXPECTED_MATRIX_SHA256, published)


if __name__ == "__main__":
    unittest.main()
