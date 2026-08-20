from __future__ import annotations

import unittest

import urusilla_stream_compression_baselines as benchmark


EXPECTED_ROWS = {
    ("canonical JSON", "raw"): (267804, "6d9b3a2544dde7918c117749ac0a4f31ffba087194701d5971bf05003ee2371b"),
    ("canonical JSON", "gzip-6"): (33686, "955f2881052004771c7d74ee317bfde38e6516b714d2ca410b7053506459a15f"),
    ("canonical JSON", "gzip-9"): (32319, "65ba6888274b75b5f902f1e00b72824e9cbce092766064c9af1e27d629f94a12"),
    ("canonical JSON", "zstd-3"): (33709, "6986af602f7cd3f0814d242ada8859cba84a544e190865c1fda2056dae02fe2b"),
    ("canonical JSON", "zstd-19"): (25536, "07fda54eeabc2eb5051f33b0a372d9522b4173216deb50f63bf8e47544c6f7c4"),
    ("canonical JSON", "brotli-5"): (28123, "dc9338c99066504afc732f5fb9ef56b107df17eb2f48875e90c935f504d1e847"),
    ("canonical JSON", "brotli-11"): (24080, "6b9a370d31e09ef3f1bac250ae57ffc62a70b188cd94dfb818a87b45133a5784"),
    ("checked JSON", "raw"): (272284, "bc2f86fdf80ede85e593e09ccba2485880945f9995fb55cd97cc1cf53e893d6a"),
    ("checked JSON", "gzip-6"): (40398, "40756a11a1ee241dfef66d6711f178c7c647f5a4dd66f2dfc79072d1e42c7a9b"),
    ("checked JSON", "gzip-9"): (38987, "fe54be26a7480dfa86d48e6355ea3f07f2824cbdff426e6a3482f84ed138c0b3"),
    ("checked JSON", "zstd-3"): (40306, "1b34016df89cfb828654202c2b3689f6b44ddcae3907c48f6537f2613ce97077"),
    ("checked JSON", "zstd-19"): (32128, "7740d5185648f0f44006e1eae3a0ef8778365a6dd9fa6aeace8e1e71f228f427"),
    ("checked JSON", "brotli-5"): (34606, "4ad8402a7050ad98a38d484be61b2ed681d292c83ecf2d7ff730a34985ab3c9d"),
    ("checked JSON", "brotli-11"): (29229, "2ade4d7e832c3e8202e9210dd8737e1ba9fab73443c2fbc0cb52d9e623c7dd2f"),
    ("project v0.2", "raw"): (55872, "f06cb86e36095780ca6a89e26b36469a8cad8854ca34ddbf102c1385189598ce"),
    ("project v0.2", "gzip-6"): (28297, "2ce06bcade0fb5b0220222c923e7c70277f338fc1055ffac2fff944d3edb3afd"),
    ("project v0.2", "gzip-9"): (28356, "517feacab98a15945ef995576e158c4d9c2067f9ac4c64394a5ab0a9af0c6d7b"),
    ("project v0.2", "zstd-3"): (28545, "c23b39bad2f39edc9cc11b467efdea79890332be37fdba0bc6404f5992b479a4"),
    ("project v0.2", "zstd-19"): (27205, "86aab11dafde8dc1e4c9ade1ad62e97598fe20c19666b4dbdc60d619af587b38"),
    ("project v0.2", "brotli-5"): (27185, "ab6a3a665aaa7fd1e5be21b751070e0252c6d61b31be00e59b228448b3976c4a"),
    ("project v0.2", "brotli-11"): (25165, "c96b24dba7091386fe93285cb589b76e14a36605c83ce469afcb4f2298615b25"),
}


@unittest.skipUnless(
    benchmark.dependencies_available(require_pins=True),
    "pinned zstandard and Brotli dependencies are unavailable",
)
class StreamCompressionBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report, cls.results = benchmark.run(repeats=1)

    def test_pinned_dependencies(self) -> None:
        self.assertEqual(benchmark.dependency_versions(), benchmark.REQUIRED_VERSIONS)

    def test_all_rows_are_exact_and_deterministic(self) -> None:
        self.assertEqual(len(self.results), 21)
        self.assertTrue(all(result.exact for result in self.results))
        self.assertTrue(all(result.deterministic for result in self.results))

    def test_every_compression_profile_has_both_representations(self) -> None:
        observed = {(result.family, result.compression) for result in self.results}
        expected = {
            (family.name, profile.name)
            for family in benchmark.session_families()
            for profile in benchmark.compression_profiles()
        }
        self.assertEqual(observed, expected)

    def test_frozen_sizes_and_payload_digests(self) -> None:
        observed = {
            (result.family, result.compression): (result.bytes_total, result.sha256)
            for result in self.results
        }
        self.assertEqual(observed, EXPECTED_ROWS)

    def test_length_framing_rejects_truncation(self) -> None:
        corpus = benchmark.build_corpus(benchmark.MESSAGE_COUNT)
        encoded = benchmark.encode_v02_session(corpus)
        with self.assertRaises(ValueError):
            benchmark.decode_v02_session(encoded[:-1])
        with self.assertRaises(ValueError):
            benchmark.decode_v02_session(encoded + b"\x00")

    def test_checked_json_rejects_record_mutation(self) -> None:
        corpus = benchmark.build_corpus(benchmark.MESSAGE_COUNT)
        encoded = bytearray(benchmark.encode_checked_json_session(corpus))
        encoded[benchmark.LENGTH_BYTES + 7] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            benchmark.decode_checked_json_session(bytes(encoded))

    def test_report_is_english_only_and_discloses_negative_scope(self) -> None:
        self.assertFalse(any("\uac00" <= char <= "\ud7a3" for char in self.report))
        normalized = " ".join(self.report.split())
        self.assertIn("persistent session", normalized)
        self.assertIn(
            "not a production network or universal codec ranking", normalized
        )
        self.assertIn(
            "Brotli decompression here is an offline benchmark path", normalized
        )


if __name__ == "__main__":
    unittest.main()
