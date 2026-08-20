#!/usr/bin/env python3
"""Conformance tests for the independent strong-codec baseline study."""

from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import unittest

from urusilla_benchmark import build_corpus
from urusilla import normalize_message
import urusilla_strong_codec_baselines as study


@unittest.skipUnless(
    study.dependencies_available(),
    "pinned research-only codec dependencies are not installed",
)
class StrongCodecBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = build_corpus(280)
        cls.codecs = study.available_codecs()

    def test_dependency_versions_match_declared_pins(self) -> None:
        self.assertEqual(study.dependency_versions(), study.PINNED_PACKAGES)

    def test_all_codecs_round_trip_the_fixed_corpus_exactly(self) -> None:
        for codec in self.codecs:
            for index, source in enumerate(self.corpus):
                with self.subTest(codec=codec.name, message=index):
                    frame = codec.encode(source)
                    self.assertEqual(codec.decode(frame), source)
                    self.assertEqual(codec.encode(source), frame)
                    self.assertEqual(codec.encode(codec.decode(frame)), frame)

    def test_map_insertion_order_does_not_change_encoded_bytes(self) -> None:
        source = self.corpus[4]
        reordered = copy.deepcopy(source)
        reordered["body"] = dict(reversed(list(reordered["body"].items())))
        reordered["meta"] = dict(reversed(list(reordered["meta"].items())))
        for codec in self.codecs:
            with self.subTest(codec=codec.name):
                self.assertEqual(codec.encode(source), codec.encode(reordered))

    def test_protobuf_preserves_scalar_categories_and_canonicalizes_zero(self) -> None:
        source = copy.deepcopy(self.corpus[0])
        source["body"] = {
            "kind": "x:strong-codec-values",
            "null": None,
            "false": False,
            "true": True,
            "minimum_signed": -(1 << 63),
            "maximum_unsigned": (1 << 64) - 1,
            "negative_zero": -0.0,
            "text": "typed semantic value",
            "bytes": b"\x00\x01\xfe\xff",
            "list": [None, -17, 23, 1.25, b"binary"],
            "map": {"z": b"last", "a": {"nested": True}},
        }
        source["meta"] = {"opaque": b"\x10\x20"}
        expected = normalize_message(source)
        frame = study.protobuf_encode(source)
        decoded = study.protobuf_decode(frame)
        self.assertEqual(decoded, expected)
        self.assertEqual(decoded["body"]["bytes"], b"\x00\x01\xfe\xff")
        self.assertEqual(decoded["body"]["minimum_signed"], -(1 << 63))
        self.assertEqual(decoded["body"]["maximum_unsigned"], (1 << 64) - 1)
        self.assertEqual(math.copysign(1.0, decoded["body"]["negative_zero"]), 1.0)
        self.assertEqual(study.protobuf_encode(decoded), frame)

    def test_protobuf_is_declared_typed_schema_not_a_json_wrapper(self) -> None:
        schema = study.PROTO_PATH.read_text(encoding="utf-8")
        self.assertIn("message AgentMessage", schema)
        self.assertIn("oneof value", schema)
        self.assertNotIn("google.protobuf.Struct", schema)
        frame = study.protobuf_encode(self.corpus[0])
        self.assertNotIn(b'{"', frame)

    def test_json_limitation_for_byte_values_is_explicit(self) -> None:
        source = copy.deepcopy(self.corpus[0])
        source["meta"] = {"opaque": b"\x00\xff"}
        normalize_message(source)
        with self.assertRaises(TypeError):
            study.sorted_json_encode(source)
        for encode, decode in (
            (study.cbor_encode, study.cbor_decode),
            (study.msgpack_encode, study.msgpack_decode),
            (study.protobuf_encode, study.protobuf_decode),
            (study.urusilla_wire_v02.encode_message, study.urusilla_wire_v02.decode_message),
        ):
            with self.subTest(codec=encode.__name__):
                self.assertEqual(decode(encode(source)), source)

    def test_schema_and_descriptor_are_content_stable(self) -> None:
        schema_digest = hashlib.sha256(study.PROTO_PATH.read_bytes()).hexdigest()
        descriptor_digest = hashlib.sha256(
            study.load_proto_runtime().descriptor_set
        ).hexdigest()
        self.assertEqual(
            schema_digest,
            "43f2b236836750779edcc9f34890f468478036172052a8ca1989d7b5108f9e5d",
        )
        self.assertEqual(
            descriptor_digest,
            "340ce63b554a904e968bf664d13cd7822df64c79f78bf394983316d08291211f",
        )
        self.assertEqual(len(study.load_proto_runtime().descriptor_set), 1_456)

    def test_fixed_corpus_wire_totals_are_content_stable(self) -> None:
        expected = {
            "sorted minified JSON": 266_684,
            "per-message gzip JSON": 168_941,
            "deterministic CBOR": 219_283,
            "MessagePack": 218_495,
            "schema-equivalent Protobuf": 229_230,
            "UrusillaWire v0.2 warm": 54_752,
        }
        observed = {
            codec.name: sum(len(codec.encode(message)) for message in self.corpus)
            for codec in self.codecs
        }
        self.assertEqual(observed, expected)

    def test_report_and_sources_contain_no_korean_document_text(self) -> None:
        korean = tuple(chr(codepoint) for codepoint in range(0xAC00, 0xD7A4))
        paths = [
            study.PROTO_PATH,
            Path(study.__file__),
            Path(__file__),
            study.DEFAULT_OUTPUT,
        ]
        for path in paths:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertFalse(any(character in text for character in korean))


if __name__ == "__main__":
    unittest.main(verbosity=2)
