#!/usr/bin/env python3
"""Conformance and failure-mode tests for experimental UrusillaWire v0.2."""

from __future__ import annotations

import copy
import gzip
import hashlib
from pathlib import Path
import unittest

from urusilla_benchmark import build_corpus
from urusilla import (
    DecodeError,
    MAX_COLLECTION_ITEMS,
    MAX_SEMANTIC_NODES,
    ValidationError,
    demo_message,
    normalize_message,
)
import urusilla_wire_v02 as wire


class UrusillaWireV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = build_corpus(280)

    def test_all_280_messages_round_trip_exactly_and_canonically(self) -> None:
        for source in self.corpus:
            frame = wire.encode_message(source)
            decoded = wire.decode_message(frame)
            self.assertEqual(decoded, source)
            self.assertEqual(wire.encode_message(decoded), frame)

    def test_encoding_is_independent_of_map_insertion_order(self) -> None:
        first = demo_message()
        second = copy.deepcopy(first)
        body = second["body"]
        second["body"] = {
            "constraints": body["constraints"],
            "kind": body["kind"],
            "condition": body["condition"],
        }
        meta = second["meta"]
        second["meta"] = {
            "provenance": meta["provenance"],
            "budget": meta["budget"],
        }
        self.assertEqual(wire.encode_message(first), wire.encode_message(second))

    def test_unknown_extension_and_generic_map_shape_are_lossless(self) -> None:
        source = demo_message()
        source["act"] = "ASSERT"
        source["body"] = {
            "kind": "x:independent-extension",
            "z-last": [None, False, True, -17, 2**48, 1.25, b"\x00\xff"],
            "a-first": {
                "unprofiled-key": "sha256:abc123",
                "another": "urn:unlisted:value",
            },
        }
        expected = normalize_message(source)
        decoded = wire.decode_message(wire.encode_message(source))
        self.assertEqual(decoded, expected)

    def test_capsule_round_trip_is_exact_and_content_addressed(self) -> None:
        capsule = wire.encode_capsule(wire.DEFAULT_PROFILE)
        decoded = wire.decode_capsule(capsule)
        self.assertEqual(decoded, wire.DEFAULT_PROFILE)
        self.assertEqual(wire.encode_capsule(decoded), capsule)
        self.assertEqual(decoded.dictionary_id, wire.DEFAULT_PROFILE.dictionary_id)
        self.assertEqual(len(decoded.dictionary_id), wire.DICTIONARY_ID_SIZE)
        self.assertEqual(wire.DEFAULT_PROFILE.profile_id, 1)
        self.assertEqual(
            wire.DEFAULT_PROFILE.name,
            "urusilla-core-benchmark-static-v1",
        )
        self.assertEqual(wire.DEFAULT_PROFILE.dictionary_id_hex, "7d12fc414eae60b2")
        self.assertEqual(len(capsule), 1_402)
        self.assertEqual(
            hashlib.sha256(capsule).hexdigest(),
            "b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6",
        )

    def test_registered_capsule_enables_a_nondefault_profile(self) -> None:
        profile = wire.StaticProfile(
            2,
            "test-profile-two",
            wire.DEFAULT_PROFILE.strings,
            wire.DEFAULT_PROFILE.shapes,
        )
        frame = wire.encode_message(self.corpus[0], profile)
        registry = wire.ProfileRegistry()
        registry.register_capsule(wire.encode_capsule(profile))
        self.assertEqual(wire.decode_message(frame, registry), self.corpus[0])

    def test_unknown_profile_fails_closed(self) -> None:
        profile = wire.StaticProfile(
            2,
            "unregistered-profile",
            wire.DEFAULT_PROFILE.strings,
            wire.DEFAULT_PROFILE.shapes,
        )
        frame = wire.encode_message(self.corpus[0], profile)
        with self.assertRaisesRegex(DecodeError, "unknown .*profile"):
            wire.decode_message(frame)

    def test_unknown_dictionary_for_known_profile_fails_closed(self) -> None:
        profile = wire.StaticProfile(
            wire.DEFAULT_PROFILE.profile_id,
            "different-dictionary-material",
            wire.DEFAULT_PROFILE.strings,
            wire.DEFAULT_PROFILE.shapes,
        )
        self.assertNotEqual(profile.dictionary_id, wire.DEFAULT_PROFILE.dictionary_id)
        frame = wire.encode_message(self.corpus[0], profile)
        with self.assertRaisesRegex(DecodeError, "unknown dictionary"):
            wire.decode_message(frame)

    def test_every_single_byte_position_is_checksum_protected(self) -> None:
        frame = wire.encode_message(self.corpus[3])
        for position in range(len(frame)):
            damaged = bytearray(frame)
            damaged[position] ^= 0x01
            with self.subTest(position=position):
                with self.assertRaises(DecodeError):
                    wire.decode_message(bytes(damaged))

    def test_capsule_corruption_fails_closed(self) -> None:
        capsule = wire.encode_capsule(wire.DEFAULT_PROFILE)
        positions = (0, len(capsule) // 3, len(capsule) // 2, len(capsule) - 1)
        for position in positions:
            damaged = bytearray(capsule)
            damaged[position] ^= 0x04
            with self.subTest(position=position):
                with self.assertRaises(DecodeError):
                    wire.decode_capsule(bytes(damaged))

    def test_semantically_invalid_message_is_rejected_before_encoding(self) -> None:
        invalid = demo_message()
        invalid["body"] = {"kind": "private-unregistered", "value": 1}
        with self.assertRaises(ValidationError):
            wire.encode_message(invalid)

    def test_profile_text_with_a_lone_surrogate_uses_project_error(self) -> None:
        with self.assertRaises(ValidationError):
            wire.StaticProfile(2, "\ud800", (), ())

    def test_exact_aggregate_semantic_node_budget_round_trips(self) -> None:
        scalar_count = MAX_SEMANTIC_NODES - 7
        groups = []
        remaining = scalar_count
        while remaining:
            size = min(remaining, MAX_COLLECTION_ITEMS)
            groups.append([None] * size)
            remaining -= size
        source = demo_message()
        source["act"] = "ASSERT"
        source["body"] = {
            "kind": "x:aggregate-probe",
            "value": groups,
        }
        source["meta"] = {}

        frame = wire.encode_message(source)
        self.assertEqual(
            wire.decode_message(frame)["body"]["kind"], "x:aggregate-probe"
        )

    def test_decoder_rejects_aggregate_collection_budget_before_normalization(self) -> None:
        counts = (MAX_COLLECTION_ITEMS, MAX_COLLECTION_ITEMS, 49_994)
        self.assertEqual(sum(counts) + 7, MAX_SEMANTIC_NODES + 1)
        compiled = wire._compile_profile(wire.DEFAULT_PROFILE)

        def null_list(count: int) -> bytes:
            return bytes([wire._LIST]) + wire._encode_uvarint(count) + bytes(count)

        aggregate = (
            bytes([wire._LIST])
            + wire._encode_uvarint(len(counts))
            + b"".join(null_list(count) for count in counts)
        )
        body = (
            bytes([wire._MAP])
            + wire._encode_uvarint(2)
            + wire._encode_string("kind", compiled)
            + wire._encode_string("x:aggregate-probe", compiled)
            + wire._encode_string("value", compiled)
            + aggregate
        )
        payload = (
            bytes.fromhex("00000000000000000000000000000001")
            + bytes.fromhex("00000000000000000000000000000002")
            + wire._encode_string("urn:agent:probe", compiled)
            + wire._encode_uvarint(1)
            + wire._encode_string("urn:agent:sink", compiled)
            + bytes([wire.ACT_TO_CODE["ASSERT"]])
            + wire._encode_string("urn:example:schema", compiled)
            + wire._encode_uvarint(0) * 3
            + bytes([0])
            + body
            + bytes([wire._MAP, 0])
        )
        header = (
            wire.MAGIC
            + bytes([wire.FLAGS])
            + wire._encode_uvarint(wire.DEFAULT_PROFILE.profile_id)
            + wire.DEFAULT_PROFILE.dictionary_id
            + wire._encode_uvarint(len(payload))
        )
        checksum = hashlib.sha256(
            wire._FRAME_HASH_DOMAIN + header + payload
        ).digest()[: wire.CHECKSUM_SIZE]
        with self.assertRaisesRegex(DecodeError, "aggregate node limit"):
            wire.decode_message(header + payload + checksum)

    def test_noncanonical_but_checksum_valid_string_encoding_is_rejected(self) -> None:
        source = self.corpus[0]
        frame = wire.encode_message(source)
        reader = wire._Reader(frame)
        self.assertEqual(reader.read(len(wire.MAGIC)), wire.MAGIC)
        self.assertEqual(reader.byte(), wire.FLAGS)
        profile_id = reader.uvarint()
        dictionary_id = reader.read(wire.DICTIONARY_ID_SIZE)
        payload_length = reader.uvarint()
        payload = reader.read(payload_length)
        reader.read(wire.CHECKSUM_SIZE)
        reader.expect_end()

        # UUIDs occupy the first 32 payload bytes. The canonical sender is a
        # one-byte static reference; replace it with a lossless raw UTF-8 form.
        sender_raw = source["sender"].encode("utf-8")
        self.assertGreaterEqual(payload[32], wire._DIRECT_STRING_BASE)
        raw_sender = (
            bytes([wire._STRING_RAW])
            + wire._encode_uvarint(len(sender_raw))
            + sender_raw
        )
        noncanonical_payload = payload[:32] + raw_sender + payload[33:]
        header = (
            wire.MAGIC
            + bytes([wire.FLAGS])
            + wire._encode_uvarint(profile_id)
            + dictionary_id
            + wire._encode_uvarint(len(noncanonical_payload))
        )
        checksum = hashlib.sha256(
            wire._FRAME_HASH_DOMAIN + header + noncanonical_payload
        ).digest()[: wire.CHECKSUM_SIZE]
        noncanonical = header + noncanonical_payload + checksum
        with self.assertRaisesRegex(DecodeError, "not canonical"):
            wire.decode_message(noncanonical)

    def test_gzip_wrapper_preserves_canonical_semantics(self) -> None:
        for source in self.corpus[:21]:
            wrapped = wire.gzip_encode_message(source)
        self.assertEqual(wire.gzip_decode_message(wrapped), source)

    def test_gzip_decompression_bomb_is_rejected_before_decode(self) -> None:
        compressed = gzip.compress(
            b"x" * (wire.MAX_FRAME_BYTES + 1), compresslevel=9, mtime=0
        )
        with self.assertRaisesRegex(DecodeError, "exceeds size limit"):
            wire.gzip_decode_message(compressed)
            self.assertEqual(wire.gzip_encode_message(source), wrapped)

    def test_profile_rejects_duplicate_dictionary_items(self) -> None:
        with self.assertRaises(ValidationError):
            wire.StaticProfile(7, "duplicate", ("kind", "kind"), ())

    def test_cli_default_output_targets_the_callers_working_directory(self) -> None:
        args = wire.build_parser().parse_args(["--benchmark"])
        self.assertEqual(
            args.output,
            Path.cwd() / "urusilla_wire_v02_results.local.md",
        )


if __name__ == "__main__":
    unittest.main()
