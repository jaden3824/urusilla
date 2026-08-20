#!/usr/bin/env python3
"""Security, resource, and canonicalization boundary tests.

The cases in this module exercise receiver-side rejection paths through public
adapter and wire-decoder APIs.  Small private parsing helpers are used only to
construct checksum-valid adversarial frames that can reach deep boundary
invariants; they are not treated as public behavior under test.
"""

from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import struct
import unittest
from unittest.mock import patch

import urusilla_a2a_adapter as adapter
from urusilla import DecodeError, MAX_COLLECTION_ITEMS, demo_message
import urusilla_wire_v02 as wire


SOURCE_ID = "0123456789abcdef0123456789abcdef"
OTHER_EXTENSION = "urn:example:boundary-trace"


def _unwrap(wrapper: object, **overrides: object) -> dict:
    arguments: dict[str, object] = {
        "expected_source_id": SOURCE_ID,
        "activated_extensions": [adapter.EXTENSION_URI],
        "a2a_version": adapter.A2A_VERSION,
    }
    arguments.update(overrides)
    return adapter.unwrap_a2a_message(wrapper, **arguments)  # type: ignore[arg-type]


def _split_frame(frame: bytes) -> tuple[int, bytes, bytes]:
    reader = wire._Reader(frame)
    if reader.read(len(wire.MAGIC)) != wire.MAGIC or reader.byte() != wire.FLAGS:
        raise AssertionError("test fixture is not a canonical v0.2 frame")
    profile_id = reader.uvarint()
    dictionary_id = reader.read(wire.DICTIONARY_ID_SIZE)
    payload_length = reader.uvarint()
    payload = reader.read(payload_length)
    reader.read(wire.CHECKSUM_SIZE)
    reader.expect_end()
    return profile_id, dictionary_id, payload


def _build_frame(profile_id: int, dictionary_id: bytes, payload: bytes) -> bytes:
    header = (
        wire.MAGIC
        + bytes([wire.FLAGS])
        + wire._encode_uvarint(profile_id)
        + dictionary_id
        + wire._encode_uvarint(len(payload))
    )
    checksum = hashlib.sha256(
        wire._FRAME_HASH_DOMAIN + header + payload
    ).digest()[: wire.CHECKSUM_SIZE]
    return header + payload + checksum


def _payload_layout(payload: bytes, profile: wire.StaticProfile) -> dict[str, int]:
    compiled = wire._compile_profile(profile)
    reader = wire._Reader(payload)
    reader.read(32)
    sender_start = reader.pos
    wire._decode_string_with_tag(reader.byte(), reader, compiled)
    sender_end = reader.pos
    recipient_count_start = reader.pos
    recipient_count = reader.uvarint()
    recipient_count_end = reader.pos
    for _ in range(recipient_count):
        wire._decode_string_with_tag(reader.byte(), reader, compiled)
    act_start = reader.pos
    act_and_reply = reader.byte()
    if act_and_reply & 0x08:
        reader.read(16)
    wire._decode_string_with_tag(reader.byte(), reader, compiled)
    reader.uvarint()
    reader.uvarint()
    confidence_start = reader.pos
    reader.uvarint()
    confidence_end = reader.pos
    expected_start = reader.pos
    reader.byte()
    body_start = reader.pos
    wire._decode_value(reader, compiled)
    body_end = reader.pos
    meta_start = reader.pos
    wire._decode_value(reader, compiled)
    meta_end = reader.pos
    reader.expect_end()
    return {
        "sender_start": sender_start,
        "sender_end": sender_end,
        "recipient_count_start": recipient_count_start,
        "recipient_count_end": recipient_count_end,
        "act_start": act_start,
        "confidence_start": confidence_start,
        "confidence_end": confidence_end,
        "expected_start": expected_start,
        "body_start": body_start,
        "body_end": body_end,
        "meta_start": meta_start,
        "meta_end": meta_end,
    }


def _build_capsule(payload: bytes) -> bytes:
    header = wire.CAPSULE_MAGIC + wire._encode_uvarint(len(payload))
    checksum = hashlib.sha256(
        wire._CAPSULE_HASH_DOMAIN + header + payload
    ).digest()[: wire.CHECKSUM_SIZE]
    return header + payload + checksum


def _text(value: str) -> bytes:
    raw = value.encode("utf-8")
    return wire._encode_uvarint(len(raw)) + raw


class AdapterBoundaryTests(unittest.TestCase):
    def test_extension_activation_rejects_injection_duplicates_and_wrong_shapes(self) -> None:
        invalid_additions = (
            "urn:example:not-an-array",
            ["urn:example:trace", "urn:example:trace"],
            ["urn:example:trace\r\nInjected: yes"],
            ["missing-colon"],
            [""],
        )
        for additions in invalid_additions:
            with self.subTest(additions=repr(additions)):
                with self.assertRaises(adapter.A2AAdapterError):
                    adapter.service_headers(  # type: ignore[arg-type]
                        additional_extensions=additions
                    )

        wrapper = adapter.wrap_a2a_message(demo_message(), source_id=SOURCE_ID)
        for activation in (
            f"{adapter.EXTENSION_URI},{adapter.EXTENSION_URI}",
            f"{adapter.EXTENSION_URI},",
            [adapter.EXTENSION_URI, adapter.EXTENSION_URI],
            7,
        ):
            with self.subTest(activation=repr(activation)):
                with self.assertRaises(adapter.A2AAdapterError):
                    _unwrap(wrapper, activated_extensions=activation)

    def test_part_structure_metadata_and_media_type_fail_closed(self) -> None:
        canonical = adapter.pack_part(demo_message(), diagnostic_metadata=True)
        cases: list[tuple[object, str]] = [
            (None, "must be an object"),
            ({**canonical, "text": "ambiguous"}, "exactly one content field"),
            ({key: value for key, value in canonical.items() if key != "raw"}, "exactly one"),
            ({**canonical, "mediaType": "application/octet-stream"}, "mediaType"),
            ({**canonical, "metadata": []}, "metadata must be an object"),
            ({**canonical, "metadata": {}}, "no recognized extension marker"),
        ]
        wrong_profile = copy.deepcopy(canonical)
        wrong_profile["metadata"][adapter.EXTENSION_URI]["wireProfile"] = "urn:wrong"
        cases.append((wrong_profile, "unsupported wire profile"))
        nontext = copy.deepcopy(canonical)
        nontext["raw"] = b"not-json-text"
        cases.append((nontext, "raw must be a Base64 string"))
        for part, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(adapter.A2AAdapterError, message):
                    adapter.unpack_part(part)  # type: ignore[arg-type]

    def test_capsule_pin_is_typed_present_and_equal(self) -> None:
        hot_part = adapter.pack_part(demo_message())
        for expected in ("", True):
            with self.subTest(expected=repr(expected)):
                with self.assertRaisesRegex(adapter.A2AAdapterError, "non-empty pinned"):
                    adapter.unpack_part(
                        hot_part,
                        expected_capsule_digest=expected,  # type: ignore[arg-type]
                    )
        with self.assertRaisesRegex(adapter.A2AAdapterError, "capsule digest mismatch"):
            adapter.unpack_part(
                hot_part,
                expected_capsule_digest="sha256:pinned",
            )

    def test_base64_preflight_rejects_bad_limits_lengths_and_alphabet(self) -> None:
        part = adapter.pack_part(demo_message())
        with patch.object(adapter.base64, "b64decode") as decoder:
            for maximum in (0, True, adapter.MAX_FRAME_BYTES + 1):
                with self.subTest(maximum=maximum):
                    with self.assertRaises(adapter.A2AAdapterError):
                        adapter.unpack_part(part, max_frame_bytes=maximum)
            decoder.assert_not_called()

        for raw in ("", "AAA", "AAA*", "A=AA"):
            malformed = {"raw": raw, "mediaType": adapter.MEDIA_TYPE}
            with self.subTest(raw=raw):
                with self.assertRaises(adapter.A2AAdapterError):
                    adapter.unpack_part(malformed)

    def test_post_preflight_decoder_size_mismatch_is_rejected(self) -> None:
        part = adapter.pack_part(demo_message())
        frame = base64.b64decode(part["raw"], validate=True)
        with patch.object(adapter.base64, "b64decode", return_value=frame + b"x"):
            with self.assertRaisesRegex(adapter.A2AAdapterError, "size limit"):
                adapter.unpack_part(part)

    def test_wire_errors_are_contained_at_the_adapter_boundary(self) -> None:
        frame = b"not-a-wire-frame"
        part = {
            "raw": base64.b64encode(frame).decode("ascii"),
            "mediaType": adapter.MEDIA_TYPE,
        }
        with self.assertRaisesRegex(
            adapter.A2AAdapterError, "invalid machine-wire frame"
        ) as caught:
            adapter.unpack_part(part)
        self.assertIsInstance(caught.exception.__cause__, adapter.UrusillaError)

    def test_wrap_rejects_untrusted_binding_metadata(self) -> None:
        message = demo_message()
        invalid_arguments = (
            {"authenticated_sender": True},
            {"context_id": ""},
            {"task_id": 9},
            {"reference_task_ids": "task-1"},
            {"reference_task_ids": ["task-1", ""]},
            {"reference_task_ids": ["task-1", "task-1"]},
            {"additional_extensions": OTHER_EXTENSION},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(adapter.A2AAdapterError):
                    adapter.wrap_a2a_message(
                        message,
                        source_id=SOURCE_ID,
                        **arguments,  # type: ignore[arg-type]
                    )

    def test_unwrap_rejects_unpinned_or_ambiguous_wrapper_fields(self) -> None:
        canonical = adapter.wrap_a2a_message(
            demo_message(),
            source_id=SOURCE_ID,
            context_id="context-1",
            task_id="task-1",
            reference_task_ids=["prior-task"],
        )
        cases: list[tuple[object, dict[str, object], str]] = [
            (None, {}, "must be an object"),
            ({**canonical, "extensions": []}, {}, "at least one extension"),
            ({**canonical, "extensions": [OTHER_EXTENSION]}, {"activated_extensions": [adapter.EXTENSION_URI, OTHER_EXTENSION]}, "omits"),
            ({**canonical, "metadata": {}}, {}, "omits extension provenance"),
            ({**canonical, "parts": []}, {}, "exactly one semantic raw Part"),
            ({**canonical, "parts": canonical["parts"] * 2}, {}, "exactly one semantic raw Part"),
            ({**canonical, "messageId": ""}, {}, "messageId must be a non-empty"),
            (canonical, {"expected_context_id": "other"}, "contextId does not match"),
            (canonical, {"expected_task_id": "other"}, "taskId does not match"),
            (canonical, {"expected_context_id": ""}, "non-empty string"),
        ]
        bad_references = copy.deepcopy(canonical)
        bad_references["referenceTaskIds"] = ["prior-task", "prior-task"]
        cases.append((bad_references, {}, "must be unique"))
        for wrapper, overrides, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(adapter.A2AAdapterError, message):
                    _unwrap(wrapper, **overrides)

    def test_agent_declaration_rejects_untyped_cold_metadata(self) -> None:
        for arguments in (
            {"capsule_digest": ""},
            {"capsule_digest": True},
            {"source_manifest": []},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(adapter.A2AAdapterError):
                    adapter.agent_extension(**arguments)  # type: ignore[arg-type]


class WireDecoderBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = demo_message()
        cls.frame = wire.encode_message(cls.source)
        cls.profile_id, cls.dictionary_id, cls.payload = _split_frame(cls.frame)
        cls.layout = _payload_layout(cls.payload, wire.DEFAULT_PROFILE)

        cls.open_profile = wire.StaticProfile(321, "boundary-profile", (), ())
        cls.open_registry = wire.ProfileRegistry((cls.open_profile,))
        cls.open_source = demo_message()
        cls.open_source["act"] = "ASSERT"
        cls.open_source["reply_to"] = None
        cls.open_source["body"] = {
            "kind": "x:boundary",
            "alpha": 1,
            "bravo": 2,
            "probe": 0.0,
        }
        cls.open_frame = wire.encode_message(cls.open_source, cls.open_profile)
        cls.open_profile_id, cls.open_dictionary_id, cls.open_payload = _split_frame(
            cls.open_frame
        )
        cls.open_layout = _payload_layout(cls.open_payload, cls.open_profile)

    def _reject_payload(
        self,
        payload: bytes,
        message: str,
        *,
        profile_id: int | None = None,
        dictionary_id: bytes | None = None,
        registry: wire.ProfileRegistry | None = None,
    ) -> None:
        frame = _build_frame(
            self.profile_id if profile_id is None else profile_id,
            self.dictionary_id if dictionary_id is None else dictionary_id,
            payload,
        )
        with self.assertRaisesRegex(DecodeError, message):
            wire.decode_message(frame, registry)

    def _reject_open_payload(self, payload: bytes, message: str) -> None:
        self._reject_payload(
            payload,
            message,
            profile_id=self.open_profile_id,
            dictionary_id=self.open_dictionary_id,
            registry=self.open_registry,
        )

    def test_public_decoder_checks_type_and_global_size_before_parsing(self) -> None:
        with self.assertRaisesRegex(DecodeError, "frame must be bytes"):
            wire.decode_message(bytearray(self.frame))  # type: ignore[arg-type]
        with patch.object(wire, "MAX_FRAME_BYTES", len(self.frame) - 1):
            with self.assertRaisesRegex(DecodeError, "frame exceeds size limit"):
                wire.decode_message(self.frame)

    def test_header_uvarint_and_declared_length_boundaries_fail_closed(self) -> None:
        headers = (
            (wire.MAGIC + bytes([wire.FLAGS]) + b"\x00", "profile ID"),
            (wire.MAGIC + bytes([wire.FLAGS]) + b"\x81\x00", "non-canonical uvarint"),
            (wire.MAGIC + bytes([wire.FLAGS]) + b"\xff" * 9 + b"\x02", "overflow"),
            (wire.MAGIC + bytes([wire.FLAGS]) + b"\x80" * 10, "exceeds 10 bytes"),
            (
                wire.MAGIC
                + bytes([wire.FLAGS])
                + wire._encode_uvarint(1)
                + wire.DEFAULT_PROFILE.dictionary_id
                + wire._encode_uvarint(wire.MAX_FRAME_BYTES + 1),
                "declared payload exceeds",
            ),
        )
        for frame, message in headers:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DecodeError, message):
                    wire.decode_message(frame)

    def test_checksum_valid_fixed_field_violations_are_rejected(self) -> None:
        layout = self.layout
        changes = (
            (
                self.payload[: layout["recipient_count_start"]]
                + b"\x00"
                + self.payload[layout["recipient_count_end"] :],
                "recipient count is invalid",
            ),
            (
                self.payload[: layout["act_start"]]
                + b"\x10"
                + self.payload[layout["act_start"] + 1 :],
                "reserved bits",
            ),
            (
                self.payload[: layout["act_start"]]
                + b"\x07"
                + self.payload[layout["act_start"] + 1 :],
                "unknown communicative act",
            ),
            (
                self.payload[: layout["confidence_start"]]
                + wire._encode_uvarint(1_000_002)
                + self.payload[layout["confidence_end"] :],
                "confidence is out of range",
            ),
            (
                self.payload[: layout["expected_start"]]
                + b"\x80"
                + self.payload[layout["expected_start"] + 1 :],
                "expected-act bitset uses reserved bits",
            ),
            (
                self.payload[: layout["meta_start"]]
                + bytes([wire._NULL]),
                "decoded meta is not a map",
            ),
            (self.payload + b"\x00", "unexpected trailing data"),
            (
                self.payload[: layout["sender_start"]]
                + bytes([wire._STRING_RAW, 0])
                + self.payload[layout["sender_end"] :],
                "violates .* semantics",
            ),
        )
        for payload, message in changes:
            with self.subTest(message=message):
                self._reject_payload(payload, message)

    def test_string_tags_and_utf8_fail_closed_inside_valid_frames(self) -> None:
        layout = self.open_layout
        replacements = (
            (bytes([wire._DIRECT_STRING_BASE]), "direct static string reference"),
            (bytes([wire._STRING_REF, 0]), "static string reference"),
            (bytes([wire._STRING_PREFIX, 0, 0]), "static prefix reference"),
            (bytes([wire._STRING_RAW, 1, 0xFF]), "invalid UTF-8"),
            (
                bytes([wire._STRING_RAW])
                + wire._encode_uvarint(wire.MAX_STRING_BYTES + 1),
                "text exceeds size limit",
            ),
            (b"\x0c", "not a string representation"),
        )
        for replacement, message in replacements:
            payload = (
                self.open_payload[: layout["sender_start"]]
                + replacement
                + self.open_payload[layout["sender_end"] :]
            )
            with self.subTest(message=message):
                self._reject_open_payload(payload, message)

    def test_noncanonical_floats_and_map_keys_fail_closed(self) -> None:
        body = self.open_payload[
            self.open_layout["body_start"] : self.open_layout["body_end"]
        ]
        positive_zero = bytes([wire._FLOAT64]) + struct.pack(">d", 0.0)
        self.assertEqual(body.count(positive_zero), 1)
        for bits, message in (
            (struct.pack(">d", -0.0), "non-canonical float"),
            (struct.pack(">d", float("nan")), "non-canonical float"),
        ):
            replacement = bytes([wire._FLOAT64]) + bits
            mutated_body = body.replace(positive_zero, replacement, 1)
            payload = (
                self.open_payload[: self.open_layout["body_start"]]
                + mutated_body
                + self.open_payload[self.open_layout["body_end"] :]
            )
            with self.subTest(message=message, bits=bits.hex()):
                self._reject_open_payload(payload, message)

        compiled = wire._compile_profile(self.open_profile)
        alpha = wire._encode_string("alpha", compiled)
        bravo = wire._encode_string("bravo", compiled)
        self.assertEqual(len(alpha), len(bravo))
        self.assertEqual(body.count(bravo), 1)
        duplicate_body = body.replace(bravo, alpha, 1)
        duplicate_payload = (
            self.open_payload[: self.open_layout["body_start"]]
            + duplicate_body
            + self.open_payload[self.open_layout["body_end"] :]
        )
        self._reject_open_payload(
            duplicate_payload, "map keys are duplicate or non-canonical"
        )

    def test_value_resource_limits_unknown_tags_and_depth_fail_closed(self) -> None:
        malicious_values = (
            (
                bytes([wire._BYTES])
                + wire._encode_uvarint(wire.MAX_FRAME_BYTES + 1),
                "byte string exceeds size limit",
            ),
            (
                bytes([wire._LIST])
                + wire._encode_uvarint(MAX_COLLECTION_ITEMS + 1),
                "list exceeds size limit",
            ),
            (
                bytes([wire._MAP])
                + wire._encode_uvarint(MAX_COLLECTION_ITEMS + 1),
                "map exceeds size limit",
            ),
            (bytes([wire._SHAPE_BASE]), "map-shape reference is out of range"),
            (b"\x0c", "unknown semantic value tag"),
            (
                (bytes([wire._LIST, 1]) * (wire.MAX_DEPTH + 2))
                + bytes([wire._NULL]),
                "semantic tree exceeds depth limit",
            ),
        )
        for malicious, message in malicious_values:
            payload = (
                self.open_payload[: self.open_layout["body_start"]]
                + malicious
                + self.open_payload[self.open_layout["body_end"] :]
            )
            with self.subTest(message=message):
                self._reject_open_payload(payload, message)

    def test_checksum_valid_capsule_limits_and_canonical_shapes_fail_closed(self) -> None:
        valid_prefix = bytes([wire.PROFILE_FORMAT]) + wire._encode_uvarint(1) + _text(
            "boundary"
        )
        cases = (
            (b"\x02", "unsupported profile capsule format"),
            (bytes([wire.PROFILE_FORMAT, 0]), "profile ID is out of range"),
            (
                valid_prefix + wire._encode_uvarint(wire.MAX_DICTIONARY_ITEMS + 1),
                "static dictionary exceeds size limit",
            ),
            (
                valid_prefix
                + wire._encode_uvarint(2)
                + _text("a")
                + _text("a")
                + b"\x00",
                "duplicate strings",
            ),
            (
                valid_prefix
                + b"\x00"
                + wire._encode_uvarint(wire.MAX_SHAPES + 1),
                "shape table exceeds size limit",
            ),
            (valid_prefix + b"\x01" + _text("a") + b"\x01\x00", "invalid key count"),
            (
                valid_prefix + b"\x01" + _text("a") + b"\x01\x01\x01",
                "key reference is out of range",
            ),
            (
                valid_prefix
                + b"\x02"
                + _text("a")
                + _text("b")
                + b"\x01\x02\x01\x00",
                "invalid static profile",
            ),
            (valid_prefix + b"\x00\x00\x00", "unexpected trailing data"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DecodeError, message):
                    wire.decode_capsule(_build_capsule(payload))

    def test_capsule_and_gzip_public_resource_boundaries_fail_closed(self) -> None:
        with self.assertRaisesRegex(DecodeError, "capsule must be bytes"):
            wire.decode_capsule(bytearray(wire.encode_capsule(wire.DEFAULT_PROFILE)))
        with patch.object(wire, "MAX_FRAME_BYTES", 8):
            with self.assertRaisesRegex(DecodeError, "capsule exceeds size limit"):
                wire.decode_capsule(b"x" * 9)

        with self.assertRaisesRegex(DecodeError, "gzip input must be bytes"):
            wire.gzip_decode_message(bytearray(b"gzip"))  # type: ignore[arg-type]
        with patch.object(wire, "MAX_FRAME_BYTES", 4):
            with self.assertRaisesRegex(DecodeError, "compressed frame exceeds"):
                wire.gzip_decode_message(b"x" * 5)
        with self.assertRaisesRegex(DecodeError, "invalid gzip-wrapped"):
            wire.gzip_decode_message(b"not-a-gzip-stream")

        wrapped = gzip.compress(self.frame, mtime=0)
        with self.assertRaisesRegex(DecodeError, "truncated or contains trailing"):
            wire.gzip_decode_message(wrapped[:-4])
        with self.assertRaisesRegex(DecodeError, "truncated or contains trailing"):
            wire.gzip_decode_message(wrapped + wrapped)


if __name__ == "__main__":
    unittest.main()
