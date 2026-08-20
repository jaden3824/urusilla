#!/usr/bin/env python3
"""Tests for the reproducible full-envelope A2A v1 JSON benchmark."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import unittest

from urusilla_a2a_adapter import (
    A2A_VERSION,
    EXTENSION_URI,
    unwrap_a2a_message,
)
from urusilla_a2a_envelope_benchmark import (
    BINDINGS,
    GZIP_LEVEL,
    HTTP_JSON_BINDING,
    JSON_RPC_BINDING,
    JSON_RPC_KEY,
    REPRESENTATIONS,
    REST_KEY,
    SOURCE_MANIFEST,
    SOURCE_ID,
    SOURCE_VALIDATION,
    STRUCTURED_KEY,
    V01_KEY,
    V02_EXTENSION_URI,
    V02_KEY,
    build_binding_body,
    build_http_request,
    decode_binding_body,
    parse_http_request,
    render_report,
    run_benchmark,
    unwrap_v01,
    unwrap_v02_experimental,
    wrap_structured_data,
    wrap_v01,
    wrap_v02_experimental,
)
from urusilla_benchmark import build_corpus
from urusilla_deterministic_gzip import compress as deterministic_gzip_compress
import urusilla_wire_v02 as wire_v02


EXPECTED_CORPUS_DIGEST = (
    "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc"
)
EXPECTED_SUITE_DIGEST = (
    "9dacc039943c890bc857418e694b0169a61ca9d259ab6f9eb33e9aaa61b49df0"
)
EXPECTED_REPORT_DIGEST = (
    "2b773a94382cdbb3a75b124b8a6cb53cee590ae208866a3513e6c4c445bd8c7e"
)
EXPECTED_CAPSULE_DIGEST = (
    "b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6"
)

EXPECTED_TOTALS = {
    (STRUCTURED_KEY, REST_KEY): (343_684, 394_016, 202_899, 259_739),
    (STRUCTURED_KEY, JSON_RPC_KEY): (360_096, 406_816, 212_218, 265_418),
    (V01_KEY, REST_KEY): (314_076, 364_351, 235_679, 292_596),
    (V01_KEY, JSON_RPC_KEY): (330_488, 377_164, 245_591, 298_878),
    (V02_KEY, REST_KEY): (207_776, 263_216, 149_202, 211_362),
    (V02_KEY, JSON_RPC_KEY): (224_188, 275_988, 158_641, 217_161),
}

EXPECTED_STREAM_DIGESTS = {
    (STRUCTURED_KEY, REST_KEY): (
        "8ff512c5052122c9309fa9c713d04630057b3c268785b1afb295656023dbb174",
        "7bb05fb5b0c65116f8518f734930788c9e2a4338b3ed1da0463645593030053f",
    ),
    (STRUCTURED_KEY, JSON_RPC_KEY): (
        "78dc6a2ca61e93cd2ba943b5c3a357f79e9136332db3c4c4c6394cf8ecbb7906",
        "5b988dd93ca3b4de7c3e15b669ef59f937fd5121fdb6a14e059ac289a39b23db",
    ),
    (V01_KEY, REST_KEY): (
        "bb54cef16193b3f71c4e7b67483afcfc724c291117236fd2eb8051cf134e9686",
        "a62c84f308ef50f8a723acbde71b4793cab10d6213360f776fc6388a32942b14",
    ),
    (V01_KEY, JSON_RPC_KEY): (
        "8ccaea003cf03fd647174cc6e1e4b91eae35643b03eee74011211a9cf5c810fc",
        "022c5bb273c92008380768b4d1d10bca44407c1acee4768101b95b4af3bf5f4e",
    ),
    (V02_KEY, REST_KEY): (
        "3bbaeed21efbf6abcc61194ed8985c5f132f7845a58ce28b0ed5e9013934de12",
        "6fff1b7dbfa1f869eaaaabed25923f6df2e20b9f2fe03ace3d31c7b27b438030",
    ),
    (V02_KEY, JSON_RPC_KEY): (
        "062f7179c4d4c0912bee93e8197a8764130f0036786bec5e5dfbcd5aafa08d6b",
        "5dbfe69554055e3d5cfb903afb66fde91e7e412bef4da582593f318085066653",
    ),
}


class A2AEnvelopeBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = build_corpus(280)
        cls.summary = run_benchmark(280)
        cls.report = render_report(cls.summary)

    def test_current_corpus_and_unsigned_source_manifest_are_pinned(self) -> None:
        self.assertEqual(self.summary.message_count, 280)
        self.assertEqual(self.summary.corpus_digest, EXPECTED_CORPUS_DIGEST)
        self.assertEqual(SOURCE_ID, "defc2efc4f0ac1ecd553fb45df7abe93")
        self.assertEqual(len(SOURCE_ID), 32)
        self.assertEqual(SOURCE_VALIDATION.signature_status, "unsigned")
        self.assertFalse(SOURCE_VALIDATION.effect_authorizing)
        self.assertEqual(
            SOURCE_MANIFEST["capsuleSha256"],
            "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
        )
        for field in (
            "languageSpecUri",
            "implementationOrigin",
            "conformanceReportUrl",
        ):
            self.assertTrue(SOURCE_MANIFEST[field].startswith("https://github.com/"))

    def test_all_six_rows_round_trip_exactly_and_deterministically(self) -> None:
        self.assertEqual(len(REPRESENTATIONS), 3)
        self.assertEqual(len(BINDINGS), 2)
        self.assertEqual(len(self.summary.results), 6)
        for result in self.summary.results:
            with self.subTest(
                representation=result.representation_key,
                binding=result.binding_key,
            ):
                self.assertEqual(result.exact_raw, 280)
                self.assertEqual(result.exact_gzip, 280)
                self.assertEqual(result.deterministic_raw, 280)
                self.assertEqual(result.deterministic_gzip, 280)

    def test_totals_and_request_stream_digests_are_pinned(self) -> None:
        self.assertEqual(self.summary.request_suite_digest, EXPECTED_SUITE_DIGEST)
        for result in self.summary.results:
            key = (result.representation_key, result.binding_key)
            with self.subTest(key=key):
                totals = (
                    sum(result.body_raw_sizes),
                    sum(result.request_raw_sizes),
                    sum(result.body_gzip_sizes),
                    sum(result.request_gzip_sizes),
                )
                self.assertEqual(totals, EXPECTED_TOTALS[key])
                self.assertEqual(
                    (result.raw_request_digest, result.gzip_request_digest),
                    EXPECTED_STREAM_DIGESTS[key],
                )

    def test_http_json_and_json_rpc_bodies_use_complete_v1_shapes(self) -> None:
        wrapper = wrap_v01(self.corpus[0])
        rest = json.loads(build_binding_body(HTTP_JSON_BINDING, wrapper, 0))
        self.assertEqual(set(rest), {"message"})
        self.assertEqual(rest["message"], wrapper)

        rpc = json.loads(build_binding_body(JSON_RPC_BINDING, wrapper, 0))
        self.assertEqual(set(rpc), {"jsonrpc", "id", "method", "params"})
        self.assertEqual(rpc["jsonrpc"], "2.0")
        self.assertEqual(rpc["id"], 1)
        self.assertEqual(rpc["method"], "SendMessage")
        self.assertEqual(rpc["params"], {"message": wrapper})

        self.assertEqual(
            decode_binding_body(
                HTTP_JSON_BINDING,
                build_binding_body(HTTP_JSON_BINDING, wrapper, 0),
                0,
            ),
            wrapper,
        )
        self.assertEqual(
            decode_binding_body(
                JSON_RPC_BINDING,
                build_binding_body(JSON_RPC_BINDING, wrapper, 0),
                0,
            ),
            wrapper,
        )

    def test_http_headers_and_content_lengths_are_counted(self) -> None:
        wrapper = wrap_v01(self.corpus[0])
        for binding in BINDINGS:
            body = build_binding_body(binding, wrapper, 0)
            for compressed in (False, True):
                with self.subTest(binding=binding.key, compressed=compressed):
                    request = build_http_request(
                        binding,
                        EXTENSION_URI,
                        body,
                        compressed=compressed,
                    )
                    head, payload = request.split(b"\r\n\r\n", 1)
                    text = head.decode("ascii")
                    self.assertTrue(text.startswith(f"POST {binding.path} HTTP/1.1"))
                    self.assertIn("Host: agent.example.test", text)
                    self.assertIn("A2A-Version: 1.0", text)
                    self.assertIn(f"A2A-Extensions: {EXTENSION_URI}", text)
                    self.assertIn(f"Content-Type: {binding.content_type}", text)
                    self.assertIn(f"Content-Length: {len(payload)}", text)
                    if compressed:
                        self.assertIn("Content-Encoding: gzip", text)
                        self.assertEqual(
                            payload,
                            deterministic_gzip_compress(
                                body,
                                compresslevel=GZIP_LEVEL,
                            ),
                        )
                    else:
                        self.assertNotIn("Content-Encoding", text)
                        self.assertEqual(payload, body)
                    parsed = parse_http_request(
                        request,
                        binding,
                        EXTENSION_URI,
                        compressed=compressed,
                    )
                    self.assertEqual(parsed.body, body)
                    self.assertEqual(parsed.a2a_version, A2A_VERSION)
                    self.assertEqual(parsed.activated_extensions, EXTENSION_URI)

    def test_v01_row_uses_current_hardened_adapter_boundary(self) -> None:
        source = self.corpus[4]
        self.assertEqual(source["act"], "COMMIT")
        wrapper = wrap_v01(source)
        self.assertEqual(wrapper["extensions"], [EXTENSION_URI])
        self.assertEqual(
            wrapper["metadata"],
            {EXTENSION_URI: {"source_id": SOURCE_ID}},
        )
        self.assertEqual(set(wrapper["parts"][0]), {"raw", "mediaType"})
        decoded = unwrap_v01(
            wrapper,
            A2A_VERSION,
            EXTENSION_URI,
            source["sender"],
        )
        self.assertEqual(decoded, source)

        changed = copy.deepcopy(wrapper)
        changed["metadata"][EXTENSION_URI]["source_id"] = "f" * 32
        with self.assertRaises(ValueError):
            unwrap_v01(
                changed,
                A2A_VERSION,
                EXTENSION_URI,
                source["sender"],
            )

    def test_structured_baseline_is_data_part_not_adapter_support(self) -> None:
        source = self.corpus[0]
        wrapper = wrap_structured_data(source)
        self.assertEqual(set(wrapper["parts"][0]), {"data", "mediaType"})
        self.assertEqual(wrapper["parts"][0]["data"], source)
        with self.assertRaises(ValueError):
            unwrap_a2a_message(
                wrapper,
                expected_source_id=SOURCE_ID,
                activated_extensions=EXTENSION_URI,
                a2a_version=A2A_VERSION,
                authenticated_sender=source["sender"],
            )

    def test_v02_wrapper_is_explicitly_experimental_and_separate(self) -> None:
        source = self.corpus[0]
        wrapper = wrap_v02_experimental(source)
        self.assertNotEqual(V02_EXTENSION_URI, EXTENSION_URI)
        self.assertEqual(wrapper["extensions"], [V02_EXTENSION_URI])
        marker = wrapper["metadata"][V02_EXTENSION_URI]
        self.assertEqual(marker["status"], "experimental")
        self.assertEqual(marker["source_id"], SOURCE_ID)
        self.assertEqual(marker["dictionaryId"], wire_v02.DEFAULT_PROFILE.dictionary_id_hex)
        self.assertEqual(set(wrapper["parts"][0]), {"raw", "mediaType"})
        decoded = unwrap_v02_experimental(
            wrapper,
            A2A_VERSION,
            V02_EXTENSION_URI,
            source["sender"],
        )
        self.assertEqual(decoded, source)
        with self.assertRaises(ValueError):
            unwrap_a2a_message(
                wrapper,
                expected_source_id=SOURCE_ID,
                activated_extensions=V02_EXTENSION_URI,
                a2a_version=A2A_VERSION,
                authenticated_sender=source["sender"],
            )

    def test_mismatched_message_id_and_json_rpc_id_fail_closed(self) -> None:
        source = self.corpus[0]
        wrapper = wrap_v02_experimental(source)
        changed = copy.deepcopy(wrapper)
        changed["messageId"] = self.corpus[1]["id"]
        with self.assertRaises(ValueError):
            unwrap_v02_experimental(
                changed,
                A2A_VERSION,
                V02_EXTENSION_URI,
                source["sender"],
            )

        rpc = json.loads(build_binding_body(JSON_RPC_BINDING, wrapper, 0))
        rpc["id"] = 2
        with self.assertRaises(ValueError):
            decode_binding_body(
                JSON_RPC_BINDING,
                json.dumps(rpc, separators=(",", ":"), sort_keys=True).encode(),
                0,
            )

    def test_cold_profile_cost_and_identity_are_separate(self) -> None:
        capsule = wire_v02.encode_capsule(wire_v02.DEFAULT_PROFILE)
        self.assertEqual(self.summary.capsule_raw_bytes, 1_402)
        self.assertEqual(self.summary.capsule_gzip_bytes, 920)
        self.assertEqual(self.summary.capsule_digest, EXPECTED_CAPSULE_DIGEST)
        self.assertEqual(
            hashlib.sha256(capsule).hexdigest(),
            EXPECTED_CAPSULE_DIGEST,
        )
        self.assertEqual(self.summary.dictionary_id, "7d12fc414eae60b2")
        self.assertEqual(wire_v02.decode_capsule(capsule), wire_v02.DEFAULT_PROFILE)

    def test_checked_in_report_is_reproducible_english_only_and_caveated(self) -> None:
        report_bytes = self.report.encode("utf-8")
        report_path = Path(__file__).with_name("urusilla_a2a_envelope_results.md")
        self.assertEqual(report_path.read_bytes(), report_bytes)
        self.assertEqual(hashlib.sha256(report_bytes).hexdigest(), EXPECTED_REPORT_DIGEST)
        self.assertIsNone(re.search(r"[\uac00-\ud7a3]", self.report))
        for phrase in (
            "does not establish that one representation is faster",
            "not an out-of-domain or general compression claim",
            "not end-to-end network cost",
            "not an A2A conformance suite",
            "derived from a fixed unsigned source-manifest fixture",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.report)


if __name__ == "__main__":
    unittest.main()
