#!/usr/bin/env python3
"""Deterministic local QA campaigns for the public decoder fixtures.

This module intentionally imports the saved project in place.  It never uses a
network, credentials, external targets, or effectful APIs.  Private codec
helpers are used only to construct checksum-valid local boundary fixtures.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import uuid
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import urusilla_adaptive_dialogue as dialogue
import urusilla_benchmark as benchmark
import urusilla as reference
import urusilla_wire_v02 as wire


PROPERTY_SEED = 0x5E4A_01C0_DE12_3457
MUTATION_SEED = 0xA11C_E55D_EC0D_E202
PROPERTY_MESSAGE_COUNT = 128
MUTATIONS_PER_KIND_PER_CODEC = 256
CAPSULE_SHA256 = "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
PUBLIC_CORPUS_SHA256 = "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc"
EXPECTED_LEDGER_DIGEST = "sha256:0ae2147fa81c3822284740e41118f1bbea292aa2a060232b94e8d9b74b92ecc2"
EXPECTED_DIALOGUE_CORPUS_DIGEST = "sha256:af65510aeb9a7bf26b0ccb265783cc3f0082fb37f183aea3f37527e68fb7ee13"


class QAFailure(AssertionError):
    """Raised when a deterministic campaign violates its declared oracle."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QAFailure(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sequence_digest(values: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _expect_exception(
    expected: type[BaseException] | tuple[type[BaseException], ...],
    operation: Callable[[], Any],
    *,
    contains: str | None = None,
) -> BaseException:
    try:
        operation()
    except expected as exc:
        if contains is not None and contains not in str(exc):
            raise QAFailure(
                f"rejection text {str(exc)!r} does not contain {contains!r}"
            ) from exc
        return exc
    except Exception as exc:
        raise QAFailure(
            f"unexpected exception boundary: {type(exc).__name__}: {exc}"
        ) from exc
    raise QAFailure("malformed input was accepted")


class FixedPRNG:
    """Small xorshift64* generator with an implementation-fixed sequence."""

    def __init__(self, seed: int):
        self.state = seed & ((1 << 64) - 1)
        if self.state == 0:
            raise ValueError("seed must be nonzero")

    def next_u64(self) -> int:
        value = self.state
        value ^= value >> 12
        value ^= (value << 25) & ((1 << 64) - 1)
        value ^= value >> 27
        self.state = value & ((1 << 64) - 1)
        return (self.state * 0x2545F4914F6CDD1D) & ((1 << 64) - 1)

    def below(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("upper must be positive")
        return self.next_u64() % upper

    def octets(self, count: int) -> bytes:
        return bytes(self.below(256) for _ in range(count))


_EDGE_VALUES: tuple[Any, ...] = (
    None,
    False,
    True,
    0,
    1,
    (1 << 64) - 1,
    -1,
    -(1 << 63),
    0.0,
    -0.0,
    1.5,
    -1234.25,
    "",
    "decoder-qa",
    "한글",
    "résultat",
    b"",
    b"\x00\xff",
)


def _generated_value(rng: FixedPRNG, depth: int = 0) -> Any:
    if depth >= 3 or rng.below(5) < 3:
        value = _EDGE_VALUES[rng.below(len(_EDGE_VALUES))]
        return bytes(value) if isinstance(value, bytes) else value
    if rng.below(2) == 0:
        return [_generated_value(rng, depth + 1) for _ in range(rng.below(5))]
    pairs: list[tuple[str, Any]] = []
    for index in range(rng.below(5)):
        key = f"qa_{depth}_{index}_{rng.next_u64():016x}"
        pairs.append((key, _generated_value(rng, depth + 1)))
    if rng.below(2):
        pairs.reverse()
    return dict(pairs)


def generated_messages(count: int = PROPERTY_MESSAGE_COUNT) -> list[dict[str, Any]]:
    rng = FixedPRNG(PROPERTY_SEED)
    messages: list[dict[str, Any]] = []
    for index in range(count):
        expected = [
            act for code, act in enumerate(reference.ACTS) if rng.next_u64() & (1 << code)
        ]
        recipient_count = 1 + rng.below(3)
        message = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"decoder-qa:message:{index}")),
            "session": str(uuid.uuid5(uuid.NAMESPACE_URL, f"decoder-qa:session:{index // 9}")),
            "sender": f"qa.sender.{index % 7}",
            "recipients": [
                f"qa.receiver.{(index + offset) % 11}" for offset in range(recipient_count)
            ],
            "act": "ASSERT",
            "reply_to": None,
            "schema": "urn:urusilla:decoder-qa:property:1",
            "logical_clock": rng.next_u64(),
            "expires_ms": rng.next_u64(),
            "confidence_ppm": None if index % 5 == 0 else rng.below(1_000_001),
            "expected": expected,
            "body": {
                "kind": "x:decoder-qa",
                "case": index,
                "edge": copy.deepcopy(_EDGE_VALUES[index % len(_EDGE_VALUES)]),
                "payload": _generated_value(rng),
            },
            "meta": {
                "index": index,
                "seed": f"0x{PROPERTY_SEED:016x}",
                "opaque": rng.octets(rng.below(9)),
            },
        }
        messages.append(reference.normalize_message(message))
    return messages


def _reverse_mapping_order(value: Any) -> Any:
    if isinstance(value, list):
        return [_reverse_mapping_order(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _reverse_mapping_order(value[key])
            for key in sorted(value, key=lambda item: item.encode("utf-8"), reverse=True)
        }
    return copy.deepcopy(value)


def _split_v1(frame: bytes) -> bytes:
    reader = reference._Reader(frame)
    _require(reader.read(len(reference.MAGIC)) == reference.MAGIC, "invalid v0.1 fixture magic")
    _require(reader.byte() == reference.FLAGS, "invalid v0.1 fixture flags")
    payload_length = reader.uvarint()
    payload = reader.read(payload_length)
    reader.read(reference.CHECKSUM_SIZE)
    reader.expect_end()
    return payload


def _build_v1(payload: bytes) -> bytes:
    header = reference.MAGIC + bytes([reference.FLAGS]) + reference._encode_uvarint(len(payload))
    checksum = hashlib.sha256(header + payload).digest()[: reference.CHECKSUM_SIZE]
    return header + payload + checksum


def _v1_layout(payload: bytes) -> dict[str, Any]:
    reader = reference._Reader(payload)
    count_start = reader.pos
    dictionary_count = reader.uvarint()
    count_end = reader.pos
    strings: list[str] = []
    entries: list[tuple[int, int]] = []
    for _ in range(dictionary_count):
        start = reader.pos
        size = reader.uvarint()
        strings.append(reader.read(size).decode("utf-8"))
        entries.append((start, reader.pos))
    entries_end = reader.pos
    reader.read(32)
    reader.uvarint()
    recipient_count = reader.uvarint()
    for _ in range(recipient_count):
        reader.uvarint()
    reader.byte()
    has_reply = reader.byte()
    if has_reply:
        reader.read(16)
    reader.uvarint()
    reader.uvarint()
    reader.uvarint()
    reader.uvarint()
    reader.byte()
    body_start = reader.pos
    reference._decode_value(reader, strings)
    body_end = reader.pos
    meta_start = reader.pos
    reference._decode_value(reader, strings)
    meta_end = reader.pos
    reader.expect_end()
    return {
        "count_start": count_start,
        "count_end": count_end,
        "dictionary_count": dictionary_count,
        "strings": strings,
        "table": {value: index for index, value in enumerate(strings)},
        "entries": entries,
        "entries_end": entries_end,
        "body_start": body_start,
        "body_end": body_end,
        "meta_start": meta_start,
        "meta_end": meta_end,
    }


def _split_v2(frame: bytes) -> tuple[int, bytes, bytes]:
    reader = wire._Reader(frame)
    _require(reader.read(len(wire.MAGIC)) == wire.MAGIC, "invalid v0.2 fixture magic")
    _require(reader.byte() == wire.FLAGS, "invalid v0.2 fixture flags")
    profile_id = reader.uvarint()
    dictionary_id = reader.read(wire.DICTIONARY_ID_SIZE)
    payload_length = reader.uvarint()
    payload = reader.read(payload_length)
    reader.read(wire.CHECKSUM_SIZE)
    reader.expect_end()
    return profile_id, dictionary_id, payload


def _build_v2(profile_id: int, dictionary_id: bytes, payload: bytes) -> bytes:
    header = (
        wire.MAGIC
        + bytes([wire.FLAGS])
        + wire._encode_uvarint(profile_id)
        + dictionary_id
        + wire._encode_uvarint(len(payload))
    )
    checksum = hashlib.sha256(wire._FRAME_HASH_DOMAIN + header + payload).digest()[
        : wire.CHECKSUM_SIZE
    ]
    return header + payload + checksum


def _v2_layout(payload: bytes, profile: wire.StaticProfile) -> dict[str, int]:
    compiled = wire._compile_profile(profile)
    reader = wire._Reader(payload)
    reader.read(32)
    sender_start = reader.pos
    wire._decode_string_with_tag(reader.byte(), reader, compiled)
    sender_end = reader.pos
    recipient_count = reader.uvarint()
    for _ in range(recipient_count):
        wire._decode_string_with_tag(reader.byte(), reader, compiled)
    act_and_reply = reader.byte()
    if act_and_reply & 0x08:
        reader.read(16)
    wire._decode_string_with_tag(reader.byte(), reader, compiled)
    reader.uvarint()
    reader.uvarint()
    reader.uvarint()
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
        "body_start": body_start,
        "body_end": body_end,
        "meta_start": meta_start,
        "meta_end": meta_end,
    }


def _minimal_message(*, act: str, body: Mapping[str, Any]) -> dict[str, Any]:
    return reference.normalize_message(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "session": "00000000-0000-0000-0000-000000000002",
            "sender": "s",
            "recipients": ["r"],
            "act": act,
            "schema": "u:s",
            "body": copy.deepcopy(body),
        }
    )


def _constraint_message() -> dict[str, Any]:
    return _minimal_message(
        act="REQUEST",
        body={
            "kind": "goal",
            "condition": {"kind": "claim", "predicate": "p"},
            "constraints": [
                {"kind": "constraint", "scope": "s", "mode": "hard", "condition": True}
            ],
        },
    )


def _evidence_message() -> dict[str, Any]:
    return _minimal_message(
        act="ASSERT",
        body={
            "kind": "evidence",
            "target": {"kind": "ref", "uri": "u:t"},
            "stance": "supports",
            "digest": "u:d",
            "provenance": "p",
        },
    )


def checksum_valid_semantic_type_frames(field: str) -> tuple[bytes, bytes]:
    if field == "constraint.mode":
        message = _constraint_message()
        invalid_body = copy.deepcopy(message["body"])
        invalid_body["constraints"][0]["mode"] = []
    elif field == "evidence.stance":
        message = _evidence_message()
        invalid_body = copy.deepcopy(message["body"])
        invalid_body["stance"] = []
    else:
        raise ValueError(f"unsupported field fixture: {field}")

    v1_frame = reference.encode_message(message)
    v1_payload = _split_v1(v1_frame)
    v1_layout = _v1_layout(v1_payload)
    v1_body = reference._encode_value(invalid_body, v1_layout["table"])
    v1_invalid = _build_v1(
        v1_payload[: v1_layout["body_start"]]
        + v1_body
        + v1_payload[v1_layout["body_end"] :]
    )

    v2_frame = wire.encode_message(message)
    profile_id, dictionary_id, v2_payload = _split_v2(v2_frame)
    v2_layout = _v2_layout(v2_payload, wire.DEFAULT_PROFILE)
    v2_body = wire._encode_value(invalid_body, wire._compile_profile(wire.DEFAULT_PROFILE))
    v2_invalid = _build_v2(
        profile_id,
        dictionary_id,
        v2_payload[: v2_layout["body_start"]]
        + v2_body
        + v2_payload[v2_layout["body_end"] :],
    )
    return v1_invalid, v2_invalid


def roundtrip_campaign() -> dict[str, Any]:
    counts: dict[str, int] = {}
    capsule_path = ROOT / "urusilla_capsule_v0_1.json"
    capsule_bytes = capsule_path.read_bytes()
    capsule_digest = sha256_bytes(capsule_bytes)
    _require(capsule_digest == CAPSULE_SHA256, "Grammar Capsule digest mismatch")
    counts["grammar_capsule_digest"] = 1

    capsule = json.loads(capsule_bytes)
    vector = capsule["conformance"]["positive_vectors"][0]
    golden = base64.b64decode(vector["wire_base64"], validate=True)
    _require(len(golden) == vector["wire_bytes"], "golden vector length mismatch")
    _require(sha256_bytes(golden) == vector["wire_sha256"], "golden vector digest mismatch")
    decoded = reference.decode_message(golden)
    _require(decoded == reference.normalize_message(vector["input"]), "golden vector semantic mismatch")
    _require(reference.encode_message(decoded) == golden, "golden vector is not canonical")
    counts["grammar_capsule_positive_vector"] = 1

    corpus = benchmark.build_corpus(280)
    corpus_digest = benchmark.corpus_digest(corpus)
    _require(corpus_digest == PUBLIC_CORPUS_SHA256, "public corpus digest mismatch")
    counts["public_corpus_digest"] = 1
    v1_frames: list[bytes] = []
    v2_frames: list[bytes] = []
    for message in corpus:
        v1 = reference.encode_message(message)
        _require(reference.decode_message(v1) == message, "v0.1 public round trip mismatch")
        _require(reference.encode_message(reference.decode_message(v1)) == v1, "v0.1 re-encode mismatch")
        v1_frames.append(v1)
        v2 = wire.encode_message(message)
        _require(wire.decode_message(v2) == message, "v0.2 public round trip mismatch")
        _require(wire.encode_message(wire.decode_message(v2)) == v2, "v0.2 re-encode mismatch")
        v2_frames.append(v2)
    counts["public_v01_round_trips"] = len(corpus)
    counts["public_v02_round_trips"] = len(corpus)

    properties = generated_messages()
    property_v1: list[bytes] = []
    property_v2: list[bytes] = []
    for message in properties:
        reordered = _reverse_mapping_order(message)
        v1 = reference.encode_message(message)
        v2 = wire.encode_message(message)
        _require(reference.decode_message(v1) == message, "generated v0.1 round trip mismatch")
        _require(wire.decode_message(v2) == message, "generated v0.2 round trip mismatch")
        _require(reference.encode_message(reordered) == v1, "v0.1 map-order dependence")
        _require(wire.encode_message(reordered) == v2, "v0.2 map-order dependence")
        property_v1.append(v1)
        property_v2.append(v2)
    counts["generated_v01_round_trips"] = len(properties)
    counts["generated_v02_round_trips"] = len(properties)
    counts["generated_v01_map_order"] = len(properties)
    counts["generated_v02_map_order"] = len(properties)

    for message in corpus[:21]:
        wrapped = wire.gzip_encode_message(message)
        _require(wire.gzip_decode_message(wrapped) == message, "gzip v0.2 round trip mismatch")
        _require(wire.gzip_encode_message(message) == wrapped, "gzip v0.2 bytes are unstable")
    counts["gzip_v02_round_trips"] = 21

    profile_capsule = wire.encode_capsule(wire.DEFAULT_PROFILE)
    _require(wire.decode_capsule(profile_capsule) == wire.DEFAULT_PROFILE, "profile capsule mismatch")
    _require(wire.encode_capsule(wire.decode_capsule(profile_capsule)) == profile_capsule, "profile capsule not canonical")
    counts["v02_profile_capsule_round_trip"] = 1

    return {
        "name": "roundtrip",
        "status": "passed",
        "case_counts": counts,
        "total_cases": sum(counts.values()),
        "digests": {
            "grammar_capsule_sha256": capsule_digest,
            "grammar_positive_wire_sha256": sha256_bytes(golden),
            "public_corpus_sha256": corpus_digest,
            "public_v01_frame_sequence_sha256": sequence_digest(v1_frames),
            "public_v02_frame_sequence_sha256": sequence_digest(v2_frames),
            "generated_v01_frame_sequence_sha256": sequence_digest(property_v1),
            "generated_v02_frame_sequence_sha256": sequence_digest(property_v2),
            "v02_profile_capsule_sha256": sha256_bytes(profile_capsule),
        },
        "fixed_seed": f"0x{PROPERTY_SEED:016x}",
    }


def _nested_depth_message(levels: int) -> dict[str, Any]:
    value: Any = 0
    for _ in range(levels):
        value = [value]
    message = reference.demo_message()
    message["act"] = "ASSERT"
    message["reply_to"] = None
    message["body"] = {"kind": "x:decoder-qa", "value": value}
    return message


def boundary_campaign() -> dict[str, Any]:
    counts: dict[str, int] = {}
    _require(reference.MAX_FRAME_BYTES == 16_777_216, "unexpected frame limit")
    _require(reference.MAX_DICTIONARY_ITEMS == 65_535, "unexpected dictionary limit")
    _require(reference.MAX_STRING_BYTES == 1_048_576, "unexpected string limit")
    _require(reference.MAX_COLLECTION_ITEMS == 100_000, "unexpected collection limit")
    _require(reference.MAX_SEMANTIC_NODES == 250_000, "unexpected aggregate semantic-node limit")
    _require(reference.MAX_DEPTH == 64, "unexpected depth limit")
    counts["documented_limit_constants"] = 6

    for encoder in (reference.encode_message, wire.encode_message):
        encoder(_nested_depth_message(63))
        _expect_exception(reference.ValidationError, lambda encoder=encoder: encoder(_nested_depth_message(64)))
    counts["semantic_depth_boundary"] = 4

    edge_message = reference.demo_message()
    edge_message["act"] = "ASSERT"
    edge_message["reply_to"] = None
    edge_message["body"] = {
        "kind": "x:decoder-qa",
        "values": [-(1 << 63), -1, 0, (1 << 64) - 1, -0.0, b"\x00\xff"],
    }
    for encoder, decoder in (
        (reference.encode_message, reference.decode_message),
        (wire.encode_message, wire.decode_message),
    ):
        decoded = decoder(encoder(edge_message))
        _require(decoded["body"]["values"][0] == -(1 << 63), "signed minimum changed")
        _require(decoded["body"]["values"][3] == (1 << 64) - 1, "unsigned maximum changed")
        _require(struct.pack(">d", decoded["body"]["values"][4]) == struct.pack(">d", 0.0), "negative zero not normalized")
    counts["scalar_boundaries"] = 2
    for bad in (-(1 << 63) - 1, 1 << 64, float("nan"), float("inf"), -float("inf")):
        invalid = copy.deepcopy(edge_message)
        invalid["body"]["values"] = [bad]
        for encoder in (reference.encode_message, wire.encode_message):
            _expect_exception(reference.ValidationError, lambda encoder=encoder, invalid=invalid: encoder(invalid))
    counts["scalar_over_boundaries"] = 10

    at_recipient_limit = _recipient_message(reference.MAX_COLLECTION_ITEMS)
    normalized_at_limit = reference.normalize_message(at_recipient_limit)
    _require(
        len(normalized_at_limit["recipients"]) == reference.MAX_COLLECTION_ITEMS,
        "exact recipient limit failed",
    )
    over_recipient_limit = _recipient_message(reference.MAX_COLLECTION_ITEMS + 1)
    _expect_exception(
        reference.ValidationError,
        lambda: reference.normalize_message(over_recipient_limit),
        contains="recipients exceed",
    )
    counts["recipient_count_boundary"] = 2

    dictionary_strings = [f"d{index:05x}".encode("ascii") for index in range(reference.MAX_DICTIONARY_ITEMS)]
    dictionary_payload = bytearray(reference._encode_uvarint(reference.MAX_DICTIONARY_ITEMS))
    for item in dictionary_strings:
        dictionary_payload += reference._encode_uvarint(len(item)) + item
    exact_dictionary_frame = _build_v1(bytes(dictionary_payload))
    _expect_exception(
        reference.DecodeError,
        lambda: reference.decode_message(exact_dictionary_frame),
        contains="truncated",
    )
    over_dictionary_frame = _build_v1(
        reference._encode_uvarint(reference.MAX_DICTIONARY_ITEMS + 1)
    )
    _expect_exception(
        reference.DecodeError,
        lambda: reference.decode_message(over_dictionary_frame),
        contains="dictionary exceeds",
    )
    counts["dictionary_count_boundary"] = 2

    golden = base64.b64decode(
        json.loads((ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8"))
        ["conformance"]["positive_vectors"][0]["wire_base64"],
        validate=True,
    )
    v2_frame = wire.encode_message(reference.demo_message())
    v2_capsule = wire.encode_capsule(wire.DEFAULT_PROFILE)
    for data, decoder in (
        (golden, reference.decode_message),
        (v2_frame, wire.decode_message),
        (v2_capsule, wire.decode_capsule),
    ):
        for length in range(len(data)):
            _expect_exception(reference.DecodeError, lambda data=data, decoder=decoder, length=length: decoder(data[:length]))
    counts["proper_prefix_truncations"] = len(golden) + len(v2_frame) + len(v2_capsule)

    for data, decoder in (
        (golden, reference.decode_message),
        (v2_frame, wire.decode_message),
        (v2_capsule, wire.decode_capsule),
    ):
        for position in (len(data) // 2, len(data) - 1):
            changed = bytearray(data)
            changed[position] ^= 0x01
            _expect_exception(
                reference.DecodeError,
                lambda changed=bytes(changed), decoder=decoder: decoder(changed),
                contains="checksum mismatch",
            )
    counts["checksum_mutations"] = 6

    open_message = reference.demo_message()
    open_message["act"] = "ASSERT"
    open_message["reply_to"] = None
    open_message["body"] = {"kind": "x:decoder-qa", "alpha": 1, "bravo": 2}
    v1 = reference.encode_message(open_message)
    v1_payload = _split_v1(v1)
    v1_layout = _v1_layout(v1_payload)
    first_start, first_end = v1_layout["entries"][0]
    duplicate_dictionary = (
        reference._encode_uvarint(v1_layout["dictionary_count"] + 1)
        + v1_payload[v1_layout["count_end"] : v1_layout["entries_end"]]
        + v1_payload[first_start:first_end]
        + v1_payload[v1_layout["entries_end"] :]
    )
    _expect_exception(reference.DecodeError, lambda: reference.decode_message(_build_v1(duplicate_dictionary)), contains="duplicate string")

    table = v1_layout["table"]
    duplicate_body_v1 = bytearray([reference._MAP])
    duplicate_body_v1 += reference._encode_uvarint(3)
    duplicate_body_v1 += reference._encode_uvarint(table["alpha"]) + reference._encode_value(1, table)
    duplicate_body_v1 += reference._encode_uvarint(table["alpha"]) + reference._encode_value(2, table)
    duplicate_body_v1 += reference._encode_uvarint(table["kind"]) + reference._encode_value("x:decoder-qa", table)
    duplicate_map_v1 = _build_v1(
        v1_payload[: v1_layout["body_start"]]
        + bytes(duplicate_body_v1)
        + v1_payload[v1_layout["body_end"] :]
    )
    _expect_exception(reference.DecodeError, lambda: reference.decode_message(duplicate_map_v1), contains="duplicate or non-canonical")

    open_profile = wire.StaticProfile(321, "decoder-qa-open", (), ())
    registry = wire.ProfileRegistry((open_profile,))
    v2_open = wire.encode_message(open_message, open_profile)
    profile_id, dictionary_id, v2_payload = _split_v2(v2_open)
    v2_layout = _v2_layout(v2_payload, open_profile)
    compiled = wire._compile_profile(open_profile)
    duplicate_body_v2 = bytearray([wire._MAP])
    duplicate_body_v2 += wire._encode_uvarint(3)
    duplicate_body_v2 += wire._encode_string("alpha", compiled) + wire._encode_value(1, compiled)
    duplicate_body_v2 += wire._encode_string("alpha", compiled) + wire._encode_value(2, compiled)
    duplicate_body_v2 += wire._encode_string("kind", compiled) + wire._encode_value("x:decoder-qa", compiled)
    duplicate_map_v2 = _build_v2(
        profile_id,
        dictionary_id,
        v2_payload[: v2_layout["body_start"]]
        + bytes(duplicate_body_v2)
        + v2_payload[v2_layout["body_end"] :],
    )
    _expect_exception(reference.DecodeError, lambda: wire.decode_message(duplicate_map_v2, registry), contains="duplicate or non-canonical")
    counts["duplicate_dictionary_and_fields"] = 3

    v1_collection = _build_v1(
        v1_payload[: v1_layout["body_start"]]
        + bytes([reference._LIST])
        + reference._encode_uvarint(reference.MAX_COLLECTION_ITEMS + 1)
        + v1_payload[v1_layout["body_end"] :]
    )
    _expect_exception(reference.DecodeError, lambda: reference.decode_message(v1_collection), contains="list exceeds")
    v2_collection = _build_v2(
        profile_id,
        dictionary_id,
        v2_payload[: v2_layout["body_start"]]
        + bytes([wire._LIST])
        + wire._encode_uvarint(wire.MAX_COLLECTION_ITEMS + 1)
        + v2_payload[v2_layout["body_end"] :],
    )
    _expect_exception(reference.DecodeError, lambda: wire.decode_message(v2_collection, registry), contains="list exceeds")
    counts["declared_collection_limits"] = 2

    v1_bad_string = _build_v1(
        reference._encode_uvarint(v1_layout["dictionary_count"])
        + reference._encode_uvarint(reference.MAX_STRING_BYTES + 1)
    )
    _expect_exception(reference.DecodeError, lambda: reference.decode_message(v1_bad_string), contains="dictionary string exceeds")
    bad_sender = bytes([wire._STRING_RAW]) + wire._encode_uvarint(wire.MAX_STRING_BYTES + 1)
    v2_bad_string = _build_v2(
        profile_id,
        dictionary_id,
        v2_payload[: v2_layout["sender_start"]]
        + bad_sender
        + v2_payload[v2_layout["sender_end"] :],
    )
    _expect_exception(reference.DecodeError, lambda: wire.decode_message(v2_bad_string, registry), contains="text exceeds")
    counts["declared_string_limits"] = 2

    oversized = b"\x00" * (reference.MAX_FRAME_BYTES + 1)
    _expect_exception(reference.DecodeError, lambda: reference.decode_message(oversized), contains="frame exceeds")
    _expect_exception(reference.DecodeError, lambda: wire.decode_message(oversized), contains="frame exceeds")
    counts["actual_frame_size_limits"] = 2

    too_large_v1 = reference.MAGIC + bytes([reference.FLAGS]) + reference._encode_uvarint(reference.MAX_FRAME_BYTES + 1)
    too_large_v2 = (
        wire.MAGIC
        + bytes([wire.FLAGS])
        + wire._encode_uvarint(1)
        + wire.DEFAULT_PROFILE.dictionary_id
        + wire._encode_uvarint(wire.MAX_FRAME_BYTES + 1)
    )
    _expect_exception(reference.DecodeError, lambda: reference.decode_message(too_large_v1), contains="declared payload exceeds")
    _expect_exception(reference.DecodeError, lambda: wire.decode_message(too_large_v2), contains="declared payload exceeds")
    counts["declared_frame_size_limits"] = 2

    malformed_headers: tuple[tuple[bytes, Callable[[bytes], Any]], ...] = (
        (reference.MAGIC + bytes([reference.FLAGS]) + b"\x81\x00", reference.decode_message),
        (wire.MAGIC + bytes([wire.FLAGS]) + b"\x81\x00", wire.decode_message),
        (wire.CAPSULE_MAGIC + b"\x81\x00", wire.decode_capsule),
        (b"WRONG" + golden[5:], reference.decode_message),
        (b"WRONG" + v2_frame[5:], wire.decode_message),
    )
    for data, decoder in malformed_headers:
        _expect_exception(reference.DecodeError, lambda data=data, decoder=decoder: decoder(data))
    counts["malformed_headers_and_varints"] = len(malformed_headers)

    _expect_exception(reference.DecodeError, lambda: reference.decode_message(bytearray(golden)))
    _expect_exception(reference.DecodeError, lambda: wire.decode_message(bytearray(v2_frame)))
    _expect_exception(reference.DecodeError, lambda: wire.decode_capsule(bytearray(v2_capsule)))
    counts["public_type_boundaries"] = 3

    fixture_digests = {
        "dictionary_at_limit_v01_sha256": sha256_bytes(exact_dictionary_frame),
        "dictionary_over_limit_v01_sha256": sha256_bytes(over_dictionary_frame),
        "duplicate_dictionary_v01_sha256": sha256_bytes(_build_v1(duplicate_dictionary)),
        "duplicate_map_v01_sha256": sha256_bytes(duplicate_map_v1),
        "duplicate_map_v02_sha256": sha256_bytes(duplicate_map_v2),
        "truncation_input_sequence_sha256": sequence_digest((golden, v2_frame, v2_capsule)),
    }
    return {
        "name": "boundaries",
        "status": "passed",
        "case_counts": counts,
        "total_cases": sum(counts.values()),
        "digests": fixture_digests,
    }


def _mutate_frame(frame: bytes, kind: str, rng: FixedPRNG) -> bytes:
    if kind == "flip":
        output = bytearray(frame)
        position = rng.below(len(output))
        output[position] ^= 1 << rng.below(8)
        return bytes(output)
    if kind == "delete":
        position = rng.below(len(frame))
        return frame[:position] + frame[position + 1 :]
    if kind == "insert":
        position = rng.below(len(frame) + 1)
        return frame[:position] + bytes([rng.below(256)]) + frame[position:]
    if kind == "truncate":
        return frame[: rng.below(len(frame))]
    raise ValueError(f"unknown mutation kind: {kind}")


def mutation_campaign() -> dict[str, Any]:
    corpus = benchmark.build_corpus(280)
    rng = FixedPRNG(MUTATION_SEED)
    counts: dict[str, int] = {}
    digests: dict[str, str] = {}
    for codec_name, encoder, decoder in (
        ("v01", reference.encode_message, reference.decode_message),
        ("v02", wire.encode_message, wire.decode_message),
    ):
        frames = [encoder(message) for message in corpus]
        mutations: list[bytes] = []
        for kind in ("flip", "delete", "insert", "truncate"):
            key = f"{codec_name}_{kind}"
            counts[key] = 0
            for iteration in range(MUTATIONS_PER_KIND_PER_CODEC):
                source_index = rng.below(len(frames))
                source = frames[source_index]
                changed = _mutate_frame(source, kind, rng)
                mutations.append(changed)
                try:
                    decoder(changed)
                except reference.DecodeError:
                    pass
                except Exception as exc:
                    raise QAFailure(
                        f"{codec_name}/{kind}/{iteration} raised {type(exc).__name__}; "
                        f"source_index={source_index}; source_sha256={sha256_bytes(source)}; "
                        f"mutation_bytes={len(changed)}; mutation_sha256={sha256_bytes(changed)}"
                    ) from exc
                else:
                    raise QAFailure(
                        f"{codec_name}/{kind}/{iteration} was accepted; "
                        f"source_index={source_index}; source_sha256={sha256_bytes(source)}; "
                        f"mutation_bytes={len(changed)}; mutation_sha256={sha256_bytes(changed)}"
                    )
                counts[key] += 1
        digests[f"{codec_name}_mutation_sequence_sha256"] = sequence_digest(mutations)
    return {
        "name": "mutations",
        "status": "passed",
        "case_counts": counts,
        "total_cases": sum(counts.values()),
        "digests": digests,
        "fixed_seed": f"0x{MUTATION_SEED:016x}",
    }


def _append_all(ledger: dialogue.ConversationLedger, corpus: Sequence[Mapping[str, Any]]) -> None:
    for message in corpus:
        ledger.append(message)


def _snapshot_thread_key(message: Mapping[str, Any]) -> str:
    """Return the public snapshot key for a conversation-scoped thread."""

    return f"{message['conversation_id']}/{message['thread_id']}"


def replay_campaign() -> dict[str, Any]:
    profile = dialogue.default_profile_document()
    corpus = list(dialogue.build_positive_coverage_corpus(profile))
    _require(dialogue.content_digest(corpus) == EXPECTED_DIALOGUE_CORPUS_DIGEST, "dialogue corpus digest mismatch")
    counts: dict[str, int] = {"dialogue_corpus_digest": 1}

    first = dialogue.ConversationLedger(profile)
    second = dialogue.ConversationLedger(profile)
    _append_all(first, corpus)
    _append_all(second, copy.deepcopy(corpus))
    first_snapshot = first.snapshot()
    second_snapshot = second.snapshot()
    _require(first_snapshot == second_snapshot, "independent ledger replay differs")
    _require(first_snapshot["ledger_digest"] == EXPECTED_LEDGER_DIGEST, "ledger digest mismatch")
    _require(
        first_snapshot["thread_states"]
        == {
            "768124ac-3094-5f11-9c68-6f0bcbd556ab/21ab74a4-1af3-51d4-8430-fa878fbf40c3": "FAILED",
            "768124ac-3094-5f11-9c68-6f0bcbd556ab/22c94640-42b2-5486-add4-c2a26fa83a68": "SUCCEEDED",
            "768124ac-3094-5f11-9c68-6f0bcbd556ab/8358008e-f4ed-53a5-88f9-79a1e742bc19": "CANCELLED",
            "768124ac-3094-5f11-9c68-6f0bcbd556ab/ebd6e675-2245-50c7-879a-48f5d19f7d33": "REFUSED",
        },
        "exact final thread states changed",
    )
    _require(first_snapshot["retracted"] == ["cc7bd011-e81c-574d-864c-e350a15ab155"], "retraction state changed")
    _require(
        first_snapshot["corrections"]
        == {"cc7bd011-e81c-574d-864c-e350a15ab155": "a0c6a14e-22f0-58f7-84ae-b5488a14062d"},
        "correction state changed",
    )
    counts["positive_ledger_appends"] = len(corpus) * 2
    counts["exact_snapshot_oracles"] = 2

    for message in corpus:
        before = first.snapshot()
        _expect_exception(dialogue.LedgerError, lambda message=message: first.append(message), contains="replay")
        _require(first.snapshot() == before, "replay mutated full ledger")
    counts["full_ledger_replay_rejections"] = len(corpus)

    prefix = dialogue.ConversationLedger(profile)
    for message in corpus:
        prefix.append(message)
        before = prefix.snapshot()
        _expect_exception(dialogue.LedgerError, lambda message=message: prefix.append(copy.deepcopy(message)), contains="replay")
        _require(prefix.snapshot() == before, "prefix replay mutated ledger")
    counts["prefix_replay_rejections"] = len(corpus)

    base = dialogue.ConversationLedger(profile)
    _append_all(base, corpus[:11])
    invalids: list[tuple[dict[str, Any], type[BaseException], str]] = []
    missing = copy.deepcopy(corpus[11])
    missing["id"] = dialogue.stable_uuid("decoder-qa:missing-cause")
    missing["causes"] = [dialogue.stable_uuid("decoder-qa:absent")]
    missing["logical_clock"] = 100
    invalids.append((missing, dialogue.LedgerError, "missing_cause"))
    clock = copy.deepcopy(corpus[11])
    clock["id"] = dialogue.stable_uuid("decoder-qa:clock")
    clock["logical_clock"] = corpus[10]["logical_clock"]
    invalids.append((clock, dialogue.LedgerError, "causal_clock"))
    wrong_profile = copy.deepcopy(corpus[11])
    wrong_profile["id"] = dialogue.stable_uuid("decoder-qa:profile")
    wrong_profile["profile_digest"] = "sha256:" + "0" * 64
    invalids.append((wrong_profile, dialogue.ValidationError, "profile_pin"))
    changed_replay = copy.deepcopy(corpus[10])
    changed_replay["authorization"]["key_id"] = "changed-key"
    invalids.append((changed_replay, dialogue.LedgerError, "replay"))
    cross_cause = copy.deepcopy(corpus[11])
    cross_cause["id"] = dialogue.stable_uuid("decoder-qa:cross-cause")
    cross_cause["conversation_id"] = dialogue.stable_uuid("decoder-qa:other-conversation")
    invalids.append((cross_cause, dialogue.LedgerError, "cross_conversation_cause"))
    cross_target = copy.deepcopy(corpus[11])
    cross_target["id"] = dialogue.stable_uuid("decoder-qa:cross-target")
    cross_target["conversation_id"] = dialogue.stable_uuid("decoder-qa:target-conversation")
    cross_target["causes"] = []
    invalids.append((cross_target, dialogue.LedgerError, "cross_conversation_target"))
    for message, error_type, text in invalids:
        before = base.snapshot()
        _expect_exception(error_type, lambda message=message: base.append(message), contains=text)
        _require(base.snapshot() == before, f"{text} rejection mutated ledger")
    counts["rejection_atomicity"] = len(invalids)

    negatives = dialogue.run_negative_coverage()
    _require(len(negatives) == len(dialogue.NEGATIVE_CASES), "negative fixture count changed")
    _require(
        [(item["case_id"], item["observed_code"]) for item in negatives]
        == list(dialogue.NEGATIVE_CASES),
        "negative fixture codes changed",
    )
    _require(all(item["rejected"] for item in negatives), "negative fixture accepted")
    counts["public_negative_dialogue_fixtures"] = len(negatives)

    isolated = dialogue.ConversationLedger(profile)
    source = copy.deepcopy(corpus[0])
    isolated.append(source)
    before = isolated.snapshot()
    source["body"] = {"kind": "request", "goal": {"kind": "goal", "condition": {"kind": "claim", "predicate": "changed", "arguments": []}}}
    _require(isolated.snapshot() == before, "caller mutation changed stored state")
    external_snapshot = first.snapshot()
    external_snapshot["ordered_message_ids"].clear()
    external_snapshot["thread_states"].clear()
    external_snapshot["retracted"].clear()
    external_snapshot["corrections"].clear()
    _require(first.snapshot() == first_snapshot, "snapshot mutation changed full ledger")
    counts["copy_isolation"] = 2

    return {
        "name": "replay",
        "status": "passed",
        "case_counts": counts,
        "total_cases": sum(counts.values()),
        "digests": {
            "dialogue_corpus_sha256": EXPECTED_DIALOGUE_CORPUS_DIGEST,
            "ledger_sha256": first_snapshot["ledger_digest"],
            "snapshot_sha256": sha256_bytes(canonical_json_bytes(first_snapshot)),
        },
    }


def _exception_observation(operation: Callable[[], Any]) -> dict[str, str]:
    try:
        operation()
    except Exception as exc:
        return {"exception": type(exc).__name__, "message": str(exc)}
    return {"exception": "none", "message": "accepted"}


def _value_observation(operation: Callable[[], Any]) -> tuple[dict[str, str], Any]:
    try:
        return {"exception": "none", "message": "accepted"}, operation()
    except Exception as exc:
        return {"exception": type(exc).__name__, "message": str(exc)}, None


def _recipient_message(count: int) -> dict[str, Any]:
    message = reference.demo_message()
    message["recipients"] = [f"r{index}" for index in range(count)]
    return message


def known_defect_campaign() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    resolved_ids: list[str] = []
    evaluated_cases = 0

    def record(condition: bool, finding: dict[str, Any]) -> None:
        if condition:
            findings.append(finding)
        else:
            resolved_ids.append(finding["id"])

    semantic_frames: dict[str, Any] = {}
    for field in ("constraint.mode", "evidence.stance"):
        v1, v2 = checksum_valid_semantic_type_frames(field)
        semantic_frames[field] = {
            "v01_bytes": len(v1),
            "v01_sha256": sha256_bytes(v1),
            "v01_observed": _exception_observation(lambda v1=v1: reference.decode_message(v1)),
            "v02_bytes": len(v2),
            "v02_sha256": sha256_bytes(v2),
            "v02_observed": _exception_observation(lambda v2=v2: wire.decode_message(v2)),
        }
        evaluated_cases += 2
    semantic_bad = any(
        observation["exception"] not in {"DecodeError", "ValidationError"}
        for per_field in semantic_frames.values()
        for key, observation in per_field.items()
        if key.endswith("_observed")
    )
    record(
        semantic_bad,
        {
            "id": "DQA-001",
            "title": "Checksum-valid semantic type errors escape both decoders as TypeError",
            "expected": "DecodeError or another UrusillaError rejection",
            "observed": semantic_frames,
            "shared_locations": ["urusilla.py:297", "urusilla.py:305", "urusilla_wire_v02.py:699"],
        }
    )

    malformed_mapping = reference.demo_message()
    malformed_mapping[1] = "unexpected"
    non_string = _exception_observation(lambda: reference.normalize_message(malformed_mapping))
    surrogate = reference.demo_message()
    surrogate["sender"] = "\ud800"
    lone_surrogate = _exception_observation(lambda: reference.normalize_message(surrogate))
    with patch.object(Path, "open", return_value=io.StringIO("{")):
        malformed_json = _exception_observation(lambda: reference._load_json(Path("unused.json")))
    evaluated_cases += 3
    ingress_bad = any(
        observation["exception"] not in {"DecodeError", "ValidationError"}
        for observation in (non_string, lone_surrogate, malformed_json)
    )
    record(
        ingress_bad,
        {
            "id": "DQA-002",
            "title": "Malformed mapping and JSON ingress leak raw runtime exceptions",
            "expected": "A bounded project-domain validation error",
            "observed": {
                "non_string_top_level_key": non_string,
                "lone_surrogate_sender": lone_surrogate,
                "malformed_json": malformed_json,
            },
            "shared_locations": ["urusilla.py:227", "urusilla.py:442", "urusilla.py:1153", "urusilla.py:main"],
        }
    )

    with patch.object(Path, "open", return_value=io.StringIO('{"field":1,"field":2}')):
        duplicate_observation, duplicate_result = _value_observation(
            lambda: reference._load_json(Path("unused.json"))
        )
    evaluated_cases += 1
    duplicate_details: dict[str, Any] = dict(duplicate_observation)
    if duplicate_observation["exception"] == "none":
        duplicate_details["parsed_value"] = duplicate_result
    record(
        duplicate_observation["exception"] not in {"DecodeError", "ValidationError"},
        {
            "id": "DQA-003",
            "title": "CLI JSON loader silently accepts duplicate members",
            "expected": "Reject duplicate field names before normalization",
            "observed": duplicate_details,
            "shared_locations": ["urusilla.py:1153"],
        }
    )

    capsule = json.loads((ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8"))
    pinned_codec_digest = capsule["implementation_artifacts"]["reference_codec"]["sha256"]
    saved_codec_digest = sha256_file(ROOT / "urusilla.py")
    evaluated_cases += 1
    record(
        pinned_codec_digest != saved_codec_digest,
        {
            "id": "DQA-004",
            "title": "The Grammar Capsule pins a different reference-codec digest than the saved implementation",
            "expected": "The Capsule implementation digest matches the exact saved reference codec",
            "observed": {
                "capsule_reference_codec_sha256": pinned_codec_digest,
                "saved_reference_codec_sha256": saved_codec_digest,
            },
            "shared_locations": ["urusilla_capsule_v0_1.json:implementation_artifacts.reference_codec", "urusilla.py"],
        }
    )

    nested = reference.demo_message()
    nested["body"]["condition"] = {"kind": "x:nested", "value": 1}
    nested_observation, nested_frame = _value_observation(lambda: reference.encode_message(nested))
    evaluated_cases += 1
    nested_details: dict[str, Any] = dict(nested_observation)
    if nested_observation["exception"] == "none":
        decoded_nested = reference.decode_message(nested_frame)
        _require(decoded_nested["body"]["condition"]["kind"] == "x:nested", "nested fixture changed")
        nested_details.update(
            {"accepted_frame_bytes": len(nested_frame), "accepted_frame_sha256": sha256_bytes(nested_frame)}
        )
    record(
        nested_observation["exception"] == "none",
        {
            "id": "DQA-005",
            "title": "The ASSERT-only x: extension quarantine is not recursive",
            "expected": "Reject a nested x: node carried by REQUEST",
            "observed": nested_details,
            "shared_locations": ["urusilla.py:526"],
        }
    )

    advertised_query = reference.demo_message()
    advertised_query["act"] = "QUERY"
    advertised_query["body"] = {
        "kind": "question-plus-answer-schema",
        "question": {"kind": "claim", "predicate": "p"},
        "answer_schema": "u:a",
    }
    advertised_result = _exception_observation(lambda: reference.normalize_message(advertised_query))
    kindless_query = copy.deepcopy(advertised_query)
    kindless_query["body"].pop("kind")
    kindless_result = _exception_observation(lambda: reference.normalize_message(kindless_query))
    evaluated_cases += 2
    record(
        advertised_result["exception"] != "none" or kindless_result["exception"] == "none",
        {
            "id": "DQA-006",
            "title": "The Capsule-advertised QUERY body kind is rejected while a kindless shape is accepted",
            "expected": "Implementation and Capsule expose the same QUERY grammar",
            "observed": {"advertised_kind": advertised_result, "kindless_shape": kindless_result},
            "shared_locations": ["urusilla_capsule_v0_1.json:message_grammar.act_body_kinds.QUERY", "urusilla.py:384", "urusilla.py:516"],
        }
    )

    tuple_message = reference.demo_message()
    tuple_message["recipients"] = tuple(tuple_message["recipients"])
    tuple_message["expected"] = tuple(tuple_message["expected"])
    tuple_observation, tuple_result = _value_observation(lambda: reference.normalize_message(tuple_message))
    evaluated_cases += 1
    tuple_details: dict[str, Any] = dict(tuple_observation)
    if tuple_observation["exception"] == "none":
        tuple_details.update(
            {
                "recipients_type": type(tuple_result["recipients"]).__name__,
                "expected_type": type(tuple_result["expected"]).__name__,
            }
        )
    record(
        tuple_observation["exception"] == "none",
        {
            "id": "DQA-007",
            "title": "Top-level recipient and expected tuples bypass the canonical tuple rejection rule",
            "expected": "Reject tuples as non-canonical input",
            "observed": tuple_details,
            "shared_locations": ["urusilla.py:449", "urusilla.py:489"],
        }
    )

    profile = dialogue.default_profile_document()
    corpus = list(dialogue.build_positive_coverage_corpus(profile))
    scoped = dialogue.ConversationLedger(profile)
    _append_all(scoped, corpus[:11])
    new_conversation = copy.deepcopy(corpus[7])
    new_conversation["id"] = dialogue.stable_uuid("qa:new-conversation:same-thread")
    new_conversation["conversation_id"] = dialogue.stable_uuid("qa:new-conversation")
    new_conversation["causes"] = []
    new_conversation["logical_clock"] = 1
    scoped_before = scoped.snapshot()
    scoped_observed = _exception_observation(lambda: scoped.append(new_conversation))
    evaluated_cases += 1
    if scoped_observed["exception"] != "none":
        _require(scoped.snapshot() == scoped_before, "conversation-scoping rejection mutated ledger")
    else:
        scoped_after = scoped.snapshot()
        _require(
            scoped_after["thread_states"][_snapshot_thread_key(corpus[10])] == "COMMITTED",
            "original conversation thread state changed",
        )
        _require(
            scoped_after["thread_states"][_snapshot_thread_key(new_conversation)] == "REQUESTED",
            "new conversation did not receive independent thread state",
        )
    record(
        scoped_observed["exception"] != "none",
        {
            "id": "DQA-008",
            "title": "Thread state is keyed without conversation scope",
            "expected": "A new conversation may independently start the same thread identifier",
            "observed": scoped_observed,
            "shared_locations": ["urusilla_adaptive_dialogue.py:898", "urusilla_adaptive_dialogue.py:952", "urusilla_adaptive_dialogue.py:973"],
        }
    )

    cross_thread = dialogue.ConversationLedger(profile)
    _append_all(cross_thread, corpus[:16])
    commit_a, commit_b = corpus[10], corpus[15]
    update = copy.deepcopy(corpus[11])
    update["id"] = dialogue.stable_uuid("qa:progress:cross-thread")
    update["causes"] = [commit_b["id"]]
    update["logical_clock"] = 17
    update["thread_id"] = commit_b["thread_id"]
    before_cross = cross_thread.snapshot()
    _require(update["body"]["target"]["uri"] == "urn:message:" + commit_a["id"], "cross-thread target fixture changed")
    _require(before_cross["thread_states"][_snapshot_thread_key(commit_a)] == "SUCCEEDED", "thread A pre-state changed")
    _require(before_cross["thread_states"][_snapshot_thread_key(commit_b)] == "COMMITTED", "thread B pre-state changed")
    cross_observed, cross_digest = _value_observation(lambda: cross_thread.append(update))
    evaluated_cases += 1
    cross_details: dict[str, Any] = dict(cross_observed)
    if cross_observed["exception"] == "none":
        cross_after = cross_thread.snapshot()
        _require(cross_digest == "sha256:cb16f1c923f0af637f580846fd4ebb99e24d611c669d2590409efa832784ae0d", "cross-thread digest changed")
        _require(cross_after["thread_states"][_snapshot_thread_key(commit_a)] == "SUCCEEDED", "thread A changed")
        _require(cross_after["thread_states"][_snapshot_thread_key(commit_b)] == "IN_PROGRESS", "thread B did not transition")
        cross_details.update(
            {
                "accepted_message_digest": cross_digest,
                "target_thread_state": cross_after["thread_states"][_snapshot_thread_key(commit_a)],
                "transitioned_envelope_thread_state": cross_after["thread_states"][_snapshot_thread_key(commit_b)],
            }
        )
    else:
        _require(cross_thread.snapshot() == before_cross, "cross-thread rejection mutated ledger")
    record(
        cross_observed["exception"] != "LedgerError",
        {
            "id": "DQA-009",
            "title": "A target-bearing update may transition a different envelope thread",
            "expected": "Reject target thread and envelope thread mismatch",
            "observed": cross_details,
            "shared_locations": ["urusilla_adaptive_dialogue.py:918", "urusilla_adaptive_dialogue.py:952", "urusilla_adaptive_dialogue.py:973"],
        }
    )

    no_cause = dialogue.ConversationLedger(profile)
    _append_all(no_cause, corpus[:11])
    causal_update = copy.deepcopy(corpus[11])
    causal_update["id"] = dialogue.stable_uuid("qa:progress:no-cause")
    causal_update["causes"] = []
    causal_update["logical_clock"] = 0
    causal_before = no_cause.snapshot()
    causal_observed, causal_digest = _value_observation(lambda: no_cause.append(causal_update))
    evaluated_cases += 1
    causal_details: dict[str, Any] = {
        **causal_observed,
        "target_clock": corpus[10]["logical_clock"],
        "submitted_clock": causal_update["logical_clock"],
    }
    if causal_observed["exception"] == "none":
        _require(causal_digest == "sha256:c47143da2e424c7cac40e32c18fdfccc867699c4824cad92a9ed19028dd6424d", "target-causality digest changed")
        causal_details["accepted_message_digest"] = causal_digest
    else:
        _require(no_cause.snapshot() == causal_before, "target-causality rejection mutated ledger")
    record(
        causal_observed["exception"] != "LedgerError",
        {
            "id": "DQA-010",
            "title": "Target-bearing updates need not causally reference or logically follow the target",
            "expected": "Require target causality and a greater logical clock",
            "observed": causal_details,
            "shared_locations": ["urusilla_adaptive_dialogue.py:902", "urusilla_adaptive_dialogue.py:918"],
        }
    )

    return {
        "name": "known_defects",
        "status": "findings" if findings else "passed",
        "evaluated_cases": evaluated_cases,
        "finding_count": len(findings),
        "findings": findings,
        "resolved_ids": resolved_ids,
    }


def baseline_campaign() -> dict[str, Any]:
    names = (
        "test_urusilla",
        "test_urusilla_wire_v02",
        "test_urusilla_adaptive_dialogue",
        "test_urusilla_boundary_hardening",
    )
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TestResult()
    suite.run(result)
    return {
        "name": "baseline",
        "status": "passed" if result.wasSuccessful() else "failed",
        "tests_run": result.testsRun,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [test.id() for test, _ in result.skipped],
        "expected_failures": [test.id() for test, _ in result.expectedFailures],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
        "modules": list(names),
    }


def qa_test_campaign() -> dict[str, Any]:
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "decoder_qa"),
        pattern="test_*.py",
        top_level_dir=str(ROOT),
    )
    result = unittest.TestResult()
    suite.run(result)
    return {
        "name": "qa_tests",
        "status": "passed" if result.wasSuccessful() else "failed",
        "tests_run": result.testsRun,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [test.id() for test, _ in result.skipped],
        "expected_failures": [test.id() for test, _ in result.expectedFailures],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
    }


CAMPAIGNS: dict[str, Callable[[], dict[str, Any]]] = {
    "baseline": baseline_campaign,
    "roundtrip": roundtrip_campaign,
    "boundaries": boundary_campaign,
    "mutations": mutation_campaign,
    "replay": replay_campaign,
    "known_defects": known_defect_campaign,
    "qa_tests": qa_test_campaign,
}


def run_campaign(name: str) -> dict[str, Any]:
    try:
        campaign = CAMPAIGNS[name]
    except KeyError as exc:
        raise ValueError(f"unknown campaign {name!r}") from exc
    return campaign()
