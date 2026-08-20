#!/usr/bin/env python3
"""Experimental UrusillaWire v0.2 static-profile codec and benchmark.

This module explores one narrow performance question left open by UrusillaWire
v0.1: what happens when peers negotiate a small, content-addressed static
dictionary and schema-shape capsule once, then send canonical warm frames?

The normative semantic object is unchanged.  ``normalize_message`` from the
v0.1 reference remains the validator, and decoding returns exactly that
canonical in-memory form.  The v0.2 wire format is deliberately a separate
experimental profile; it does not modify or silently reinterpret v0.1.

The default profile contains only repeated schema vocabulary, enums, URI
prefixes, and map-key shapes.  It does not contain complete benchmark messages,
message UUIDs, evidence digests, or other per-message results.  The capsule is
fully serialized and its cold-transfer cost is included in the benchmark.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import hmac
import json
import math
from pathlib import Path
import platform
import statistics
import struct
import sys
import time
from typing import Any, Mapping, Sequence
import uuid
import zlib

from urusilla_deterministic_gzip import compress as deterministic_gzip_compress
from urusilla import (
    ACTS,
    ACT_TO_CODE,
    DecodeError,
    MAX_COLLECTION_ITEMS,
    MAX_DEPTH,
    MAX_DICTIONARY_ITEMS,
    MAX_FRAME_BYTES,
    MAX_SEMANTIC_NODES,
    MAX_STRING_BYTES,
    SemanticNodeBudget,
    ValidationError,
    normalize_message,
)


MAGIC = b"URSL\x02"
CAPSULE_MAGIC = b"URCP\x02"
FLAGS = 0x01
PROFILE_FORMAT = 0x01
CHECKSUM_SIZE = 16
DICTIONARY_ID_SIZE = 8
MAX_PROFILE_NAME_BYTES = 256
MAX_SHAPES = 128

_FRAME_HASH_DOMAIN = b"UrusillaWire-v0.2-frame\x00"
_CAPSULE_HASH_DOMAIN = b"UrusillaWire-v0.2-capsule\x00"


def _utf8_bytes(value: str, field: str) -> bytes:
    """Encode profile text without leaking a raw UnicodeEncodeError."""

    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{field} contains invalid Unicode") from exc


def _encode_uvarint(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= (1 << 64) - 1:
        raise ValidationError(f"uvarint out of range: {value!r}")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _encode_svarint(value: int) -> bytes:
    if type(value) is not int or not -(1 << 63) <= value <= (1 << 63) - 1:
        raise ValidationError(f"signed integer out of range: {value!r}")
    zigzag = value * 2 if value >= 0 else (-value * 2) - 1
    return _encode_uvarint(zigzag)


class _Reader:
    def __init__(self, data: bytes | memoryview):
        self.data = memoryview(data)
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read(self, count: int) -> bytes:
        if count < 0 or count > self.remaining:
            raise DecodeError("truncated v0.2 data")
        start = self.pos
        self.pos += count
        return bytes(self.data[start : start + count])

    def byte(self) -> int:
        return self.read(1)[0]

    def uvarint(self) -> int:
        value = 0
        raw = bytearray()
        for shift in range(0, 70, 7):
            byte = self.byte()
            raw.append(byte)
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                if value > (1 << 64) - 1:
                    raise DecodeError("uvarint overflow")
                if bytes(raw) != _encode_uvarint(value):
                    raise DecodeError("non-canonical uvarint")
                return value
        raise DecodeError("uvarint exceeds 10 bytes")

    def expect_end(self) -> None:
        if self.remaining:
            raise DecodeError(f"unexpected trailing data: {self.remaining} byte(s)")


def _read_text(reader: _Reader, *, limit: int = MAX_STRING_BYTES) -> str:
    size = reader.uvarint()
    if size > limit:
        raise DecodeError("text exceeds size limit")
    try:
        return reader.read(size).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DecodeError("text contains invalid UTF-8") from exc


def _append_text(out: bytearray, value: str, *, limit: int = MAX_STRING_BYTES) -> None:
    if type(value) is not str:
        raise ValidationError("profile text must be a string")
    raw = _utf8_bytes(value, "profile text")
    if len(raw) > limit:
        raise ValidationError("profile text exceeds size limit")
    out += _encode_uvarint(len(raw))
    out += raw


@dataclass(frozen=True)
class StaticProfile:
    """A negotiated static string dictionary and exact map-shape table."""

    profile_id: int
    name: str
    strings: tuple[str, ...]
    shapes: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if type(self.profile_id) is not int or not 1 <= self.profile_id <= 65_535:
            raise ValidationError("profile_id must be an integer from 1 to 65,535")
        if type(self.name) is not str or not self.name:
            raise ValidationError("profile name must be a non-empty string")
        if len(_utf8_bytes(self.name, "profile name")) > MAX_PROFILE_NAME_BYTES:
            raise ValidationError("profile name exceeds size limit")
        if len(self.strings) > MAX_DICTIONARY_ITEMS:
            raise ValidationError("static dictionary exceeds size limit")
        if any(type(item) is not str for item in self.strings):
            raise ValidationError("static dictionary items must be strings")
        if len(set(self.strings)) != len(self.strings):
            raise ValidationError("static dictionary contains duplicate strings")
        for item in self.strings:
            if not item:
                raise ValidationError("static dictionary cannot contain an empty string")
            if len(_utf8_bytes(item, "static dictionary string")) > MAX_STRING_BYTES:
                raise ValidationError("static dictionary string exceeds size limit")
        if len(self.shapes) > MAX_SHAPES:
            raise ValidationError(f"profile has more than {MAX_SHAPES} shapes")
        known = set(self.strings)
        if len(set(self.shapes)) != len(self.shapes):
            raise ValidationError("profile contains duplicate map shapes")
        for shape in self.shapes:
            if not shape:
                raise ValidationError("profile map shape cannot be empty")
            if len(shape) > MAX_COLLECTION_ITEMS:
                raise ValidationError("profile map shape exceeds size limit")
            if any(type(key) is not str or key not in known for key in shape):
                raise ValidationError("every shape key must exist in the string dictionary")
            canonical = tuple(
                sorted(shape, key=lambda key: _utf8_bytes(key, "profile map-shape key"))
            )
            if shape != canonical or len(set(shape)) != len(shape):
                raise ValidationError("profile map-shape keys must be unique and UTF-8 sorted")

    @property
    def dictionary_id(self) -> bytes:
        """Return the content fingerprint carried by each warm frame."""

        return _profile_dictionary_id(self)

    @property
    def dictionary_id_hex(self) -> str:
        return self.dictionary_id.hex()


@dataclass(frozen=True)
class _CompiledProfile:
    profile: StaticProfile
    string_to_index: Mapping[str, int]
    shape_to_index: Mapping[tuple[str, ...], int]
    prefix_candidates: Mapping[str, tuple[tuple[int, str, int], ...]]


@lru_cache(maxsize=32)
def _compile_profile(profile: StaticProfile) -> _CompiledProfile:
    string_to_index = {value: index for index, value in enumerate(profile.strings)}
    shape_to_index = {shape: index for index, shape in enumerate(profile.shapes)}
    grouped: dict[str, list[tuple[int, str, int]]] = {}
    for index, value in enumerate(profile.strings):
        grouped.setdefault(value[0], []).append(
            (index, value, len(value.encode("utf-8")))
        )
    prefixes = {
        initial: tuple(sorted(items, key=lambda item: (-item[2], item[0])))
        for initial, items in grouped.items()
    }
    return _CompiledProfile(profile, string_to_index, shape_to_index, prefixes)


@lru_cache(maxsize=32)
def _profile_payload(profile: StaticProfile) -> bytes:
    compiled = {value: index for index, value in enumerate(profile.strings)}
    out = bytearray([PROFILE_FORMAT])
    out += _encode_uvarint(profile.profile_id)
    _append_text(out, profile.name, limit=MAX_PROFILE_NAME_BYTES)
    out += _encode_uvarint(len(profile.strings))
    for item in profile.strings:
        _append_text(out, item)
    out += _encode_uvarint(len(profile.shapes))
    for shape in profile.shapes:
        out += _encode_uvarint(len(shape))
        for key in shape:
            out += _encode_uvarint(compiled[key])
    return bytes(out)


@lru_cache(maxsize=32)
def _profile_dictionary_id(profile: StaticProfile) -> bytes:
    return hashlib.sha256(_profile_payload(profile)).digest()[:DICTIONARY_ID_SIZE]


def encode_capsule(profile: StaticProfile) -> bytes:
    """Serialize a profile capsule canonically, including an accidental-error checksum."""

    payload = _profile_payload(profile)
    header = CAPSULE_MAGIC + _encode_uvarint(len(payload))
    checksum = hashlib.sha256(_CAPSULE_HASH_DOMAIN + header + payload).digest()[
        :CHECKSUM_SIZE
    ]
    capsule = header + payload + checksum
    if len(capsule) > MAX_FRAME_BYTES:
        raise ValidationError("profile capsule exceeds size limit")
    return capsule


def decode_capsule(capsule: bytes) -> StaticProfile:
    """Decode and canonicalize a v0.2 profile capsule."""

    if not isinstance(capsule, bytes):
        raise DecodeError("profile capsule must be bytes")
    if len(capsule) > MAX_FRAME_BYTES:
        raise DecodeError("profile capsule exceeds size limit")
    reader = _Reader(capsule)
    if reader.read(len(CAPSULE_MAGIC)) != CAPSULE_MAGIC:
        raise DecodeError("unsupported profile capsule magic or version")
    payload_length = reader.uvarint()
    if payload_length > MAX_FRAME_BYTES:
        raise DecodeError("declared capsule payload exceeds size limit")
    header_length = reader.pos
    if reader.remaining != payload_length + CHECKSUM_SIZE:
        raise DecodeError("capsule payload length does not match frame length")
    payload = reader.read(payload_length)
    checksum = reader.read(CHECKSUM_SIZE)
    reader.expect_end()
    expected = hashlib.sha256(
        _CAPSULE_HASH_DOMAIN + capsule[:header_length] + payload
    ).digest()[:CHECKSUM_SIZE]
    if not hmac.compare_digest(checksum, expected):
        raise DecodeError("profile capsule checksum mismatch")

    payload_reader = _Reader(payload)
    if payload_reader.byte() != PROFILE_FORMAT:
        raise DecodeError("unsupported profile capsule format")
    profile_id = payload_reader.uvarint()
    if not 1 <= profile_id <= 65_535:
        raise DecodeError("profile ID is out of range")
    name = _read_text(payload_reader, limit=MAX_PROFILE_NAME_BYTES)
    dictionary_count = payload_reader.uvarint()
    if dictionary_count > MAX_DICTIONARY_ITEMS:
        raise DecodeError("static dictionary exceeds size limit")
    strings = tuple(_read_text(payload_reader) for _ in range(dictionary_count))
    if len(set(strings)) != len(strings):
        raise DecodeError("static dictionary contains duplicate strings")
    shape_count = payload_reader.uvarint()
    if shape_count > MAX_SHAPES:
        raise DecodeError("profile shape table exceeds size limit")
    shapes: list[tuple[str, ...]] = []
    for _ in range(shape_count):
        key_count = payload_reader.uvarint()
        if not 1 <= key_count <= MAX_COLLECTION_ITEMS:
            raise DecodeError("profile map shape has an invalid key count")
        keys: list[str] = []
        for _ in range(key_count):
            index = payload_reader.uvarint()
            if index >= len(strings):
                raise DecodeError("profile shape key reference is out of range")
            keys.append(strings[index])
        shapes.append(tuple(keys))
    payload_reader.expect_end()
    try:
        profile = StaticProfile(profile_id, name, strings, tuple(shapes))
    except ValidationError as exc:
        raise DecodeError(f"invalid static profile: {exc}") from exc
    if encode_capsule(profile) != capsule:
        raise DecodeError("profile capsule is valid but not canonical")
    return profile


class ProfileRegistry:
    """An explicit allow-list of profiles accepted by a decoder."""

    def __init__(self, profiles: Sequence[StaticProfile] = ()) -> None:
        self._profiles: dict[tuple[int, bytes], StaticProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: StaticProfile) -> None:
        key = (profile.profile_id, profile.dictionary_id)
        existing = self._profiles.get(key)
        if existing is not None and existing != profile:
            raise ValidationError("profile fingerprint collision")
        self._profiles[key] = profile

    def register_capsule(self, capsule: bytes) -> StaticProfile:
        profile = decode_capsule(capsule)
        self.register(profile)
        return profile

    def resolve(self, profile_id: int, dictionary_id: bytes) -> StaticProfile:
        profile = self._profiles.get((profile_id, dictionary_id))
        if profile is not None:
            return profile
        if not any(key[0] == profile_id for key in self._profiles):
            raise DecodeError(f"unknown UrusillaWire v0.2 profile: {profile_id}")
        raise DecodeError(
            f"unknown dictionary for UrusillaWire v0.2 profile {profile_id}: "
            f"{dictionary_id.hex()}"
        )


# Value tags 0x00..0x0b are generic.  0x20..0x7f are one-byte static
# string references, and 0x80..0xff are one-byte static map-shape tags.
_NULL = 0x00
_FALSE = 0x01
_TRUE = 0x02
_UINT = 0x03
_SINT = 0x04
_FLOAT64 = 0x05
_BYTES = 0x06
_LIST = 0x07
_MAP = 0x08
_STRING_RAW = 0x09
_STRING_PREFIX = 0x0A
_STRING_REF = 0x0B
_DIRECT_STRING_BASE = 0x20
_DIRECT_STRING_COUNT = 0x60
_SHAPE_BASE = 0x80


def _encode_string(value: str, compiled: _CompiledProfile) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > MAX_STRING_BYTES:
        raise ValidationError("string exceeds size limit")
    exact = compiled.string_to_index.get(value)
    if exact is not None:
        if exact < _DIRECT_STRING_COUNT:
            return bytes([_DIRECT_STRING_BASE + exact])
        return bytes([_STRING_REF]) + _encode_uvarint(exact)

    raw_encoding = bytes([_STRING_RAW]) + _encode_uvarint(len(raw)) + raw
    best: tuple[tuple[int, int, int], bytes] | None = None
    for index, prefix, prefix_bytes in compiled.prefix_candidates.get(value[:1], ()):
        if not value.startswith(prefix):
            continue
        suffix = value[len(prefix) :].encode("utf-8")
        if not suffix:
            continue
        candidate = (
            bytes([_STRING_PREFIX])
            + _encode_uvarint(index)
            + _encode_uvarint(len(suffix))
            + suffix
        )
        if len(candidate) >= len(raw_encoding):
            continue
        rank = (len(candidate), -prefix_bytes, index)
        if best is None or rank < best[0]:
            best = (rank, candidate)
    return raw_encoding if best is None else best[1]


def _decode_string_with_tag(
    tag: int, reader: _Reader, compiled: _CompiledProfile
) -> str:
    strings = compiled.profile.strings
    if _DIRECT_STRING_BASE <= tag < _DIRECT_STRING_BASE + _DIRECT_STRING_COUNT:
        index = tag - _DIRECT_STRING_BASE
        if index >= len(strings):
            raise DecodeError("direct static string reference is out of range")
        return strings[index]
    if tag == _STRING_REF:
        index = reader.uvarint()
        if index >= len(strings):
            raise DecodeError("static string reference is out of range")
        return strings[index]
    if tag == _STRING_RAW:
        return _read_text(reader)
    if tag == _STRING_PREFIX:
        index = reader.uvarint()
        if index >= len(strings):
            raise DecodeError("static prefix reference is out of range")
        suffix = _read_text(reader)
        value = strings[index] + suffix
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise DecodeError("prefixed string exceeds size limit")
        return value
    raise DecodeError(f"value tag {tag} is not a string representation")


def _encode_value(value: Any, compiled: _CompiledProfile, *, depth: int = 0) -> bytes:
    if depth > MAX_DEPTH:
        raise ValidationError("semantic tree exceeds depth limit")
    if value is None:
        return bytes([_NULL])
    if value is False:
        return bytes([_FALSE])
    if value is True:
        return bytes([_TRUE])
    if type(value) is int:
        if value >= 0:
            return bytes([_UINT]) + _encode_uvarint(value)
        return bytes([_SINT]) + _encode_svarint(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationError("NaN and infinity are not canonical")
        if value == 0.0:
            value = 0.0
        return bytes([_FLOAT64]) + struct.pack(">d", value)
    if type(value) is str:
        return _encode_string(value, compiled)
    if type(value) is bytes:
        return bytes([_BYTES]) + _encode_uvarint(len(value)) + value
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValidationError("list exceeds size limit")
        out = bytearray([_LIST])
        out += _encode_uvarint(len(value))
        for item in value:
            out += _encode_value(item, compiled, depth=depth + 1)
        return bytes(out)
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValidationError("map exceeds size limit")
        if not all(type(key) is str for key in value):
            raise ValidationError("all semantic map keys must be strings")
        keys = tuple(sorted(value, key=lambda key: key.encode("utf-8")))
        shape_index = compiled.shape_to_index.get(keys)
        if shape_index is not None and shape_index < MAX_SHAPES:
            out = bytearray([_SHAPE_BASE + shape_index])
            for key in keys:
                out += _encode_value(value[key], compiled, depth=depth + 1)
            return bytes(out)
        out = bytearray([_MAP])
        out += _encode_uvarint(len(keys))
        for key in keys:
            out += _encode_string(key, compiled)
            out += _encode_value(value[key], compiled, depth=depth + 1)
        return bytes(out)
    raise ValidationError(f"cannot encode {type(value).__name__}")


def _decode_value(
    reader: _Reader,
    compiled: _CompiledProfile,
    *,
    depth: int = 0,
    budget: SemanticNodeBudget | None = None,
) -> Any:
    if depth > MAX_DEPTH:
        raise DecodeError("semantic tree exceeds depth limit")
    if budget is None:
        budget = SemanticNodeBudget(MAX_SEMANTIC_NODES)
    tag = reader.byte()
    budget.consume(DecodeError)
    if tag >= _SHAPE_BASE:
        shape_index = tag - _SHAPE_BASE
        if shape_index >= len(compiled.profile.shapes):
            raise DecodeError("static map-shape reference is out of range")
        shape = compiled.profile.shapes[shape_index]
        budget.require_minimum_children(len(shape), DecodeError)
        return {
            key: _decode_value(
                reader, compiled, depth=depth + 1, budget=budget
            )
            for key in shape
        }
    if tag == _NULL:
        return None
    if tag == _FALSE:
        return False
    if tag == _TRUE:
        return True
    if tag == _UINT:
        return reader.uvarint()
    if tag == _SINT:
        zigzag = reader.uvarint()
        return zigzag // 2 if zigzag % 2 == 0 else -((zigzag + 1) // 2)
    if tag == _FLOAT64:
        value = struct.unpack(">d", reader.read(8))[0]
        if not math.isfinite(value) or (value == 0.0 and math.copysign(1.0, value) < 0):
            raise DecodeError("non-canonical float")
        return value
    if tag == _BYTES:
        size = reader.uvarint()
        if size > MAX_FRAME_BYTES:
            raise DecodeError("byte string exceeds size limit")
        return reader.read(size)
    if tag == _LIST:
        count = reader.uvarint()
        if count > MAX_COLLECTION_ITEMS:
            raise DecodeError("list exceeds size limit")
        budget.require_minimum_children(count, DecodeError)
        return [
            _decode_value(reader, compiled, depth=depth + 1, budget=budget)
            for _ in range(count)
        ]
    if tag == _MAP:
        count = reader.uvarint()
        if count > MAX_COLLECTION_ITEMS:
            raise DecodeError("map exceeds size limit")
        budget.require_minimum_children(count, DecodeError)
        result: dict[str, Any] = {}
        previous: bytes | None = None
        for _ in range(count):
            key_tag = reader.byte()
            key = _decode_string_with_tag(key_tag, reader, compiled)
            raw_key = key.encode("utf-8")
            if previous is not None and raw_key <= previous:
                raise DecodeError("map keys are duplicate or non-canonical")
            previous = raw_key
            result[key] = _decode_value(
                reader, compiled, depth=depth + 1, budget=budget
            )
        return result
    if (
        tag in {_STRING_RAW, _STRING_PREFIX, _STRING_REF}
        or _DIRECT_STRING_BASE <= tag < _DIRECT_STRING_BASE + _DIRECT_STRING_COUNT
    ):
        return _decode_string_with_tag(tag, reader, compiled)
    raise DecodeError(f"unknown semantic value tag: {tag}")


def _uuid_bytes(value: str, field: str) -> bytes:
    try:
        return uuid.UUID(value).bytes
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError(f"{field} must be a canonical UUID string") from exc


def _uuid_text(value: bytes) -> str:
    return str(uuid.UUID(bytes=value))


def encode_message(
    message: Mapping[str, Any], profile: StaticProfile | None = None
) -> bytes:
    """Encode one canonical warm frame under an explicitly identified profile."""

    if profile is None:
        profile = DEFAULT_PROFILE
    canonical = normalize_message(message)
    compiled = _compile_profile(profile)
    payload = bytearray()
    payload += _uuid_bytes(canonical["id"], "id")
    payload += _uuid_bytes(canonical["session"], "session")
    payload += _encode_string(canonical["sender"], compiled)
    payload += _encode_uvarint(len(canonical["recipients"]))
    for recipient in canonical["recipients"]:
        payload += _encode_string(recipient, compiled)
    reply_to = canonical["reply_to"]
    act_and_reply = ACT_TO_CODE[canonical["act"]] | (0x08 if reply_to else 0)
    payload.append(act_and_reply)
    if reply_to is not None:
        payload += _uuid_bytes(reply_to, "reply_to")
    payload += _encode_string(canonical["schema"], compiled)
    payload += _encode_uvarint(canonical["logical_clock"])
    payload += _encode_uvarint(canonical["expires_ms"])
    confidence = canonical["confidence_ppm"]
    payload += _encode_uvarint(0 if confidence is None else confidence + 1)
    expected_mask = 0
    for act in canonical["expected"]:
        expected_mask |= 1 << ACT_TO_CODE[act]
    payload.append(expected_mask)
    payload += _encode_value(canonical["body"], compiled)
    payload += _encode_value(canonical["meta"], compiled)

    header = (
        MAGIC
        + bytes([FLAGS])
        + _encode_uvarint(profile.profile_id)
        + profile.dictionary_id
        + _encode_uvarint(len(payload))
    )
    checksum = hashlib.sha256(_FRAME_HASH_DOMAIN + header + payload).digest()[
        :CHECKSUM_SIZE
    ]
    frame = header + payload + checksum
    if len(frame) > MAX_FRAME_BYTES:
        raise ValidationError("encoded v0.2 frame exceeds size limit")
    return frame


def decode_message(
    frame: bytes, registry: ProfileRegistry | None = None
) -> dict[str, Any]:
    """Validate and decode a canonical v0.2 frame, rejecting unknown profiles."""

    if registry is None:
        registry = DEFAULT_REGISTRY
    if not isinstance(frame, bytes):
        raise DecodeError("frame must be bytes")
    if len(frame) > MAX_FRAME_BYTES:
        raise DecodeError("frame exceeds size limit")
    reader = _Reader(frame)
    if reader.read(len(MAGIC)) != MAGIC:
        raise DecodeError("unsupported magic or UrusillaWire version")
    if reader.byte() != FLAGS:
        raise DecodeError("unsupported or non-canonical v0.2 flags")
    profile_id = reader.uvarint()
    if not 1 <= profile_id <= 65_535:
        raise DecodeError("profile ID is out of range")
    dictionary_id = reader.read(DICTIONARY_ID_SIZE)
    payload_length = reader.uvarint()
    if payload_length > MAX_FRAME_BYTES:
        raise DecodeError("declared payload exceeds size limit")
    header_length = reader.pos
    if reader.remaining != payload_length + CHECKSUM_SIZE:
        raise DecodeError("payload length does not match frame length")
    payload = reader.read(payload_length)
    checksum = reader.read(CHECKSUM_SIZE)
    reader.expect_end()
    expected_checksum = hashlib.sha256(
        _FRAME_HASH_DOMAIN + frame[:header_length] + payload
    ).digest()[:CHECKSUM_SIZE]
    if not hmac.compare_digest(checksum, expected_checksum):
        raise DecodeError("v0.2 frame checksum mismatch")
    profile = registry.resolve(profile_id, dictionary_id)
    compiled = _compile_profile(profile)

    payload_reader = _Reader(payload)
    message_id = _uuid_text(payload_reader.read(16))
    session_id = _uuid_text(payload_reader.read(16))
    sender = _decode_string_with_tag(payload_reader.byte(), payload_reader, compiled)
    recipient_count = payload_reader.uvarint()
    if not 1 <= recipient_count <= MAX_COLLECTION_ITEMS:
        raise DecodeError("recipient count is invalid")
    recipients = [
        _decode_string_with_tag(payload_reader.byte(), payload_reader, compiled)
        for _ in range(recipient_count)
    ]
    act_and_reply = payload_reader.byte()
    if act_and_reply & 0xF0:
        raise DecodeError("act/reply byte uses reserved bits")
    act_code = act_and_reply & 0x07
    if act_code >= len(ACTS):
        raise DecodeError("unknown communicative act code")
    act = ACTS[act_code]
    reply_to = _uuid_text(payload_reader.read(16)) if act_and_reply & 0x08 else None
    schema = _decode_string_with_tag(payload_reader.byte(), payload_reader, compiled)
    logical_clock = payload_reader.uvarint()
    expires_ms = payload_reader.uvarint()
    encoded_confidence = payload_reader.uvarint()
    if encoded_confidence > 1_000_001:
        raise DecodeError("confidence is out of range")
    confidence_ppm = None if encoded_confidence == 0 else encoded_confidence - 1
    expected_mask = payload_reader.byte()
    if expected_mask >> len(ACTS):
        raise DecodeError("expected-act bitset uses reserved bits")
    expected = [name for code, name in enumerate(ACTS) if expected_mask & (1 << code)]
    semantic_budget = SemanticNodeBudget(MAX_SEMANTIC_NODES)
    body = _decode_value(payload_reader, compiled, budget=semantic_budget)
    meta = _decode_value(payload_reader, compiled, budget=semantic_budget)
    payload_reader.expect_end()
    if not isinstance(meta, dict):
        raise DecodeError("decoded meta is not a map")
    decoded = {
        "id": message_id,
        "session": session_id,
        "sender": sender,
        "recipients": recipients,
        "act": act,
        "reply_to": reply_to,
        "schema": schema,
        "logical_clock": logical_clock,
        "expires_ms": expires_ms,
        "confidence_ppm": confidence_ppm,
        "expected": expected,
        "body": body,
        "meta": meta,
    }
    try:
        canonical = normalize_message(decoded)
    except ValidationError as exc:
        raise DecodeError(f"decoded frame violates Urusilla semantics: {exc}") from exc
    if encode_message(canonical, profile) != frame:
        raise DecodeError("v0.2 frame is valid but not canonical")
    return canonical


# The order is intentional: the first 96 entries receive one-byte value tags,
# and all shape keys remain below the one-byte uvarint boundary.
_DEFAULT_STRINGS = (
    "kind",
    "uri",
    "condition",
    "arguments",
    "target",
    "trace",
    "run",
    "span",
    "sampled",
    "budget",
    "wire_bytes",
    "compute_units",
    "tags",
    "scope",
    "mode",
    "latency_ms_lte",
    "regions",
    "retry_lte",
    "weight_ppm",
    "predicate",
    "attempt",
    "score",
    "context",
    "locale",
    "label",
    "owner",
    "priority",
    "constraints",
    "answer_limit",
    "capability",
    "dry_run",
    "candidate_nodes",
    "declared_effects",
    "goal",
    "debtor",
    "creditors",
    "expiry_ms",
    "verifier",
    "status",
    "result",
    "artifact",
    "checks",
    "stance",
    "digest",
    "provenance",
    "observed_at_ms",
    "model",
    "parameters",
    "basis",
    "alpha",
    "beta",
    "ref",
    "constraint",
    "claim",
    "hard",
    "soft",
    "execution",
    "output",
    "ap-northeast-2",
    "us-east-1",
    "benchmark",
    "에이전트",
    "ko-KR",
    "en-US",
    "ja-JP",
    "검증",
    "routing",
    "résultat",
    "action",
    "commitment",
    "resolution",
    "evidence",
    "uncertainty",
    "supports",
    "contradicts",
    "categorical",
    "succeeded",
    "failed",
    "expired",
    "ledger.append",
    "artifact.create",
    "answer.matches.schema",
    "proof.candidate.valid",
    "weather.candidate.valid",
    "inventory.candidate.valid",
    "routing.candidate.valid",
    "finance.candidate.valid",
    "verify.proof",
    "route.package",
    "reserve.stock",
    "planner.alpha.agent",
    "verifier.beta.agent",
    "executor.gamma.agent",
    "auditor.delta.agent",
    "broker.epsilon.agent",
    "urn:urusilla:proof-verification:1",
    "urn:urusilla:routing:2",
    "urn:urusilla:inventory-reservation:1",
    "urn:urusilla:forecast-evidence:3",
    "urn:urusilla:contract-resolution:1",
    "sha256:",
    "candidate-",
    "domain-",
    "team-",
    "worker-",
    "verifier-",
    "sensor.cluster/",
    "urn:answer:",
    "urn:ledger:record:",
)


def _shape(*keys: str) -> tuple[str, ...]:
    return tuple(sorted(keys, key=lambda key: key.encode("utf-8")))


_DEFAULT_SHAPES = (
    _shape("kind", "uri"),
    _shape("budget", "tags", "trace"),
    _shape("run", "sampled", "span"),
    _shape("compute_units", "wire_bytes"),
    _shape("condition", "kind", "mode", "scope", "weight_ppm"),
    _shape("latency_ms_lte", "regions", "retry_lte"),
    _shape("arguments", "context", "kind", "predicate"),
    _shape("attempt", "score"),
    _shape("label", "locale"),
    _shape("condition", "constraints", "kind", "owner", "priority"),
    _shape("answer_limit", "arguments", "kind", "predicate"),
    _shape("arguments", "capability", "declared_effects", "kind"),
    _shape("candidate_nodes", "dry_run", "goal"),
    _shape("creditors", "debtor", "expiry_ms", "goal", "kind", "verifier"),
    _shape("kind", "result", "status", "target"),
    _shape("artifact", "checks"),
    _shape("digest", "kind", "observed_at_ms", "provenance", "stance", "target"),
    _shape("basis", "kind", "model", "parameters", "target"),
    _shape("alpha", "beta"),
)


DEFAULT_PROFILE = StaticProfile(
    profile_id=1,
    name="urusilla-core-benchmark-static-v1",
    strings=_DEFAULT_STRINGS,
    shapes=_DEFAULT_SHAPES,
)
DEFAULT_REGISTRY = ProfileRegistry((DEFAULT_PROFILE,))


def gzip_encode_message(message: Mapping[str, Any]) -> bytes:
    return deterministic_gzip_compress(encode_message(message), compresslevel=6)


def gzip_decode_message(data: bytes) -> dict[str, Any]:
    if not isinstance(data, bytes):
        raise DecodeError("gzip input must be bytes")
    if len(data) > MAX_FRAME_BYTES:
        raise DecodeError("compressed frame exceeds input size limit")
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decompressor.decompress(data, MAX_FRAME_BYTES + 1)
        if decompressor.unconsumed_tail or len(raw) > MAX_FRAME_BYTES:
            raise DecodeError("decompressed frame exceeds size limit")
        raw += decompressor.flush(MAX_FRAME_BYTES + 1 - len(raw))
    except zlib.error as exc:
        raise DecodeError("invalid gzip-wrapped v0.2 frame") from exc
    if len(raw) > MAX_FRAME_BYTES:
        raise DecodeError("decompressed frame exceeds size limit")
    if not decompressor.eof or decompressor.unused_data:
        raise DecodeError("gzip stream is truncated or contains trailing members")
    return decode_message(raw)


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _percentage(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{100 * numerator / denominator:.1f}%"


def _strict_break_even(
    cold_bytes: int, baseline_total: int, warm_total: int, corpus_count: int
) -> int | None:
    """Return the first mean-based N where cold + N*warm is strictly smaller."""

    savings_total = baseline_total - warm_total
    if savings_total <= 0:
        return None
    return (cold_bytes * corpus_count) // savings_total + 1


def _size_delta(smaller_candidate: int, baseline: int) -> str:
    return f"{100 * (smaller_candidate / baseline - 1):+.1f}%"


def run_benchmark(
    *, messages: int, repeats: int, warmups: int, corruptions: int
) -> tuple[str, list[Any]]:
    """Run the required matched benchmark and return an English Markdown report."""

    from urusilla_benchmark import (
        Codec,
        build_corpus,
        corpus_digest,
        gzip_json_decode,
        gzip_json_encode,
        gzip_urusilla_decode,
        gzip_urusilla_encode,
        json_decode,
        json_encode,
        measure,
    )
    from urusilla import decode_message as decode_v01
    from urusilla import encode_message as encode_v01

    if messages < 280:
        raise ValueError("the v0.2 benchmark requires at least 280 messages")
    corpus = build_corpus(messages)
    codecs = [
        Codec(
            "minified JSON",
            json_encode,
            json_decode,
            "sorted UTF-8 JSON with shared Urusilla validation",
        ),
        Codec(
            "gzip minified JSON",
            gzip_json_encode,
            gzip_json_decode,
            "per-message gzip level 6, mtime=0",
        ),
        Codec(
            "UrusillaWire v0.1",
            encode_v01,
            decode_v01,
            "independent per-message dictionary and 16-byte checksum",
        ),
        Codec(
            "gzip UrusillaWire v0.1",
            gzip_urusilla_encode,
            gzip_urusilla_decode,
            "v0.1 with per-message gzip level 6, mtime=0",
        ),
        Codec(
            "UrusillaWire v0.2 warm",
            encode_message,
            decode_message,
            "negotiated static strings and map shapes; 16-byte checksum",
        ),
        Codec(
            "gzip UrusillaWire v0.2 warm",
            gzip_encode_message,
            gzip_decode_message,
            "v0.2 with per-message gzip level 6, mtime=0",
        ),
    ]
    started = time.perf_counter()
    results, invalid_count = measure(
        codecs,
        corpus,
        repeats=repeats,
        warmups=warmups,
        corruption_trials=corruptions,
    )
    elapsed = time.perf_counter() - started
    by_name = {result.name: result for result in results}
    count = len(corpus)
    corrupt_total = count * corruptions
    json_total = sum(by_name["minified JSON"].sizes)
    gzip_json_total = sum(by_name["gzip minified JSON"].sizes)
    v01_total = sum(by_name["UrusillaWire v0.1"].sizes)
    gzip_v01_total = sum(by_name["gzip UrusillaWire v0.1"].sizes)
    v02_total = sum(by_name["UrusillaWire v0.2 warm"].sizes)
    gzip_v02_total = sum(by_name["gzip UrusillaWire v0.2 warm"].sizes)

    capsule = encode_capsule(DEFAULT_PROFILE)
    gzip_capsule = deterministic_gzip_compress(capsule, compresslevel=6)
    grammar_path = Path(__file__).with_name("urusilla_capsule_v0_1.json")
    grammar_raw = grammar_path.read_bytes() if grammar_path.exists() else b""
    grammar_gzip = (
        deterministic_gzip_compress(grammar_raw, compresslevel=6)
        if grammar_raw
        else b""
    )
    cold_raw = len(capsule)
    cold_gzip = len(gzip_capsule)
    combined_raw = cold_raw + len(grammar_raw)
    combined_gzip = cold_gzip + len(grammar_gzip)
    if grammar_raw:
        grammar_cold_note = (
            "The v0.2 profile capsule is the only additional object required by this codec. "
            "The existing Grammar Capsule is shown as a conservative application-level cold "
            "scenario; it is not required again if peers already possess it. Gzip capsule sizes "
            "use level 6 and `mtime=0`."
        )
    else:
        grammar_cold_note = (
            "The v0.2 profile capsule is the only additional object required by this codec. "
            "No Grammar Capsule was present beside the installed module, so this run neither "
            "charges nor reports that optional application-level cold object. Gzip capsule sizes "
            "use level 6 and `mtime=0`."
        )

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# UrusillaWire v0.2 static-profile performance study",
        "",
        f"Execution time (UTC): `{timestamp}`  ",
        f"Corpus: `urusilla-benchmark-corpus-v1`, {count} deterministic messages, "
        f"SHA-256 `{corpus_digest(corpus)}`  ",
        f"Runtime: `{platform.python_implementation()} {platform.python_version()}` / "
        f"`{platform.platform()}`  ",
        f"Settings: {warmups} warm-up rounds, {repeats} timing repeats, "
        f"{corruptions} deterministic single-bit corruptions per message  ",
        f"Total benchmark time: {elapsed:.2f}s",
        "",
        "## Result",
        "",
        f"Warm raw v0.2 used **{v02_total:,} bytes**, "
        f"{abs(100 * (1 - v02_total / gzip_json_total)):.1f}% "
        f"{'less' if v02_total < gzip_json_total else 'more'} than per-message gzip JSON and "
        f"{abs(100 * (1 - v02_total / v01_total)):.1f}% "
        f"{'less' if v02_total < v01_total else 'more'} than raw v0.1. "
        f"Per-message gzip on v0.2 produced {gzip_v02_total:,} bytes, "
        f"{abs(100 * (1 - gzip_v02_total / v02_total)):.1f}% "
        f"{'less' if gzip_v02_total < v02_total else 'more'} than raw v0.2. "
        "These are warm-frame totals; the cold profile cost and break-even points are "
        "reported separately below.",
        "",
        "This is a transport result, not evidence that agents reason better, invent a "
        "language autonomously, or should place binary frames in model prompts. The profile "
        "was designed for this declared benchmark family, so performance on unrelated or "
        "rapidly changing schemas may be worse. Latency and unfavorable baseline results are "
        "retained rather than filtered.",
        "",
        "## Warm wire bytes",
        "",
        "| Codec | Total bytes | Mean/msg | p50/msg | p95/msg | vs minified JSON |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        total = sum(result.sizes)
        lines.append(
            f"| {result.name} | {total:,} | {statistics.fmean(result.sizes):,.1f} | "
            f"{_nearest_rank(result.sizes, 0.50):,} | "
            f"{_nearest_rank(result.sizes, 0.95):,} | "
            f"{_size_delta(total, json_total)} |"
        )
    lines.extend(
        [
            "",
            "Every row sends 280 or more separately framed messages. Gzip is applied separately to "
            "each message with identical standard-library settings; no batch stream is used. "
            "The v0.2 raw row carries a profile ID, an 8-byte content fingerprint, payload "
            "length, and a 16-byte checksum in every frame.",
            "",
            "## Codec latency",
            "",
            "| Codec | Encode p50 (µs) | Encode p95 (µs) | Decode p50 (µs) | Decode p95 (µs) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.name} | {_nearest_rank(result.encode_ns, 0.50) / 1_000:,.2f} | "
            f"{_nearest_rank(result.encode_ns, 0.95) / 1_000:,.2f} | "
            f"{_nearest_rank(result.decode_ns, 0.50) / 1_000:,.2f} | "
            f"{_nearest_rank(result.decode_ns, 0.95) / 1_000:,.2f} |"
        )
    lines.extend(
        [
            "",
            f"Encode and decode were each sampled `{count * repeats:,}` times per codec. "
            "v0.2 decode includes checksum verification, profile resolution, semantic "
            "validation, and canonical re-encoding. JSON encode does not perform the equivalent "
            "validation pass, and the implementations use different amounts of pure Python and "
            "native CPython code. These are current implementation-path timings, not inherent "
            "format speeds or portable throughput guarantees.",
            "",
            "## Exactness and fail-closed checks",
            "",
            "| Codec | Exact semantic round-trip | Byte-stable re-encode in this runtime | Corruptions rejected | Accepted, semantics changed | Accepted, semantics unchanged |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.name} | {result.exact_messages}/{count} "
            f"({_percentage(result.exact_messages, count)}) | "
            f"{result.canonical_frames}/{count} "
            f"({_percentage(result.canonical_frames, count)}) | "
            f"{result.corruption_rejected}/{corrupt_total} "
            f"({_percentage(result.corruption_rejected, corrupt_total)}) | "
            f"{result.corruption_silent_change}/{corrupt_total} "
            f"({_percentage(result.corruption_silent_change, corrupt_total)}) | "
            f"{result.corruption_unchanged}/{corrupt_total} "
            f"({_percentage(result.corruption_unchanged, corrupt_total)}) |"
        )
    lines.extend(
        [
            "",
            "A matched deterministic bit was flipped at a fractional position in every encoded "
            "frame. A gzip header bit may be accepted with unchanged semantics, which is why "
            "`rejected` need not reach 100% for gzip rows. The raw v0.2 checksum covers the "
            "header, profile identifiers, and payload. It detects accidental corruption but is "
            "not authentication against an attacker who can recompute it.",
            "",
            f"The shared invalid-input suite contained `{invalid_count}` messages. All v0.2 "
            f"invalid inputs were rejected at encode or decode; accepted count: "
            f"`{by_name['UrusillaWire v0.2 warm'].invalid_accepted}`. Unit tests separately cover "
            "unknown profile IDs, unknown dictionary fingerprints, capsule corruption, and "
            "non-canonical frames.",
            "",
            "## Cold capsule cost",
            "",
            f"The default profile contains `{len(DEFAULT_PROFILE.strings)}` strings and "
            f"`{len(DEFAULT_PROFILE.shapes)}` exact map shapes. Its dictionary fingerprint is "
            f"`{DEFAULT_PROFILE.dictionary_id_hex}`.",
            "",
            "| Bootstrap object | Raw bytes | gzip bytes |",
            "|---|---:|---:|",
            f"| v0.2 static-profile capsule | {cold_raw:,} | {cold_gzip:,} |",
        ]
    )
    if grammar_raw:
        lines.extend(
            [
                f"| Existing v0.1 Grammar Capsule JSON | {len(grammar_raw):,} | {len(grammar_gzip):,} |",
                f"| Both objects, transferred independently | {combined_raw:,} | {combined_gzip:,} |",
            ]
        )
    lines.extend(
        [
            "",
            grammar_cold_note,
            "",
            "## Mean-size break-even",
            "",
            "Break-even is the smallest integer `N` satisfying `C + N·W < N·B`, using the "
            "measured corpus means. `C` is the one-time bootstrap, `W` the v0.2 warm mean, and "
            "`B` the selected baseline mean. A dash means the v0.2 warm mean is not smaller, so "
            "no byte break-even exists under that comparison.",
            "",
        ]
    )
    if grammar_raw:
        lines.extend(
            [
                "| Warm candidate | Baseline | Profile-only cold N | Profile + Grammar Capsule N |",
                "|---|---|---:|---:|",
            ]
        )
    else:
        lines.extend(
            [
                "| Warm candidate | Baseline | Profile-only cold N |",
                "|---|---|---:|",
            ]
        )
    comparisons = [
        ("UrusillaWire v0.2 warm", v02_total, cold_raw, combined_raw),
        ("gzip UrusillaWire v0.2 warm", gzip_v02_total, cold_gzip, combined_gzip),
    ]
    baselines = [
        ("minified JSON", json_total),
        ("gzip minified JSON", gzip_json_total),
        ("UrusillaWire v0.1", v01_total),
        ("gzip UrusillaWire v0.1", gzip_v01_total),
    ]
    for candidate_name, candidate_total, profile_cold, all_cold in comparisons:
        for baseline_name, baseline_total in baselines:
            profile_n = _strict_break_even(
                profile_cold, baseline_total, candidate_total, count
            )
            if grammar_raw:
                all_n = _strict_break_even(
                    all_cold, baseline_total, candidate_total, count
                )
                lines.append(
                    f"| {candidate_name} | {baseline_name} | "
                    f"{profile_n if profile_n is not None else '—'} | "
                    f"{all_n if all_n is not None else '—'} |"
                )
            else:
                lines.append(
                    f"| {candidate_name} | {baseline_name} | "
                    f"{profile_n if profile_n is not None else '—'} |"
                )
    lines.extend(
        [
            "",
            "These mean-based values assume the measured workload mix repeats. A short session "
            "with different message shapes can fail to amortize the capsule. Transport/TLS "
            "headers, profile discovery round trips, retransmission, and cache eviction are not "
            "included.",
            "",
            "## Codec design and canonicality",
            "",
            "- Frames identify both the numeric profile and its 64-bit SHA-256-derived content "
            "fingerprint. Decoders use an explicit registry and reject unknown combinations.",
            "- Common static strings and schema map shapes use one-byte tags. Other strings are "
            "encoded losslessly as UTF-8, optionally using a deterministic longest-beneficial "
            "static prefix. Unknown map shapes retain sorted explicit keys.",
            "- Message UUIDs remain 16-byte values. Integers remain canonical varints, finite "
            "floats remain normalized IEEE-754 binary64 values, and byte strings remain exact.",
            "- Decode validates the checksum before profile lookup, checks all bounds and reserved "
            "bits, invokes the shared Urusilla semantic validator, then requires byte-identical "
            "canonical re-encoding.",
            "- A capsule checksum detects accidental damage. Capsule authorization and frame "
            "authentication must be supplied by a trusted registry, signed metadata, or an "
            "authenticated transport; an eight-byte dictionary fingerprint is an identifier, "
            "not a security proof.",
            "",
            "## Limitations",
            "",
            "- The default profile was manually derived from the same public benchmark generator "
            "and contains its exact agents, schemas, predicates, prefixes, and map shapes. This is "
            "an in-sample upper-bound study, not an out-of-domain compression claim.",
            "- The benchmark begins with already-structured semantic objects. It does not measure "
            "natural-language parsing, LLM tokens, task success, repair turns, or semantic "
            "interoperability between independently trained models.",
            "- Per-message gzip is the requested baseline. A persistent gzip/zstd stream, "
            "schema-equivalent Protobuf implementation, or TLS record compression could change "
            "the ranking and is not evaluated here.",
            "- Static profiles require lifecycle controls: version negotiation, cache bounds, "
            "rollback, authorization, and a fallback representation. Those controls are outside "
            "this prototype.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 urusilla_wire_v02.py --benchmark --output urusilla_wire_v02_results.md",
            "python3 test_urusilla_wire_v02.py",
            "```",
            "",
            "Options: `--messages` (minimum 280), `--repeats`, `--warmups`, "
            "`--corruptions`, and `--output`. Corpus content and corruption positions are "
            "deterministic; timings remain environment-dependent.",
            "",
        ]
    )
    return "\n".join(lines), results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="run the v0.2 study")
    parser.add_argument("--messages", type=int, default=280)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--corruptions", type=int, default=4)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / "urusilla_wire_v02_results.local.md",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.benchmark:
        print(
            "UrusillaWire v0.2 experimental codec loaded. "
            "Use --benchmark to run the reproducible study."
        )
        return 0
    if args.messages < 280:
        raise SystemExit("--messages must be at least 280")
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.warmups < 0:
        raise SystemExit("--warmups cannot be negative")
    if args.corruptions < 1:
        raise SystemExit("--corruptions must be at least 1")
    report, results = run_benchmark(
        messages=args.messages,
        repeats=args.repeats,
        warmups=args.warmups,
        corruptions=args.corruptions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")
    print(
        f"profile={DEFAULT_PROFILE.profile_id} "
        f"dictionary={DEFAULT_PROFILE.dictionary_id_hex} "
        f"capsule={len(encode_capsule(DEFAULT_PROFILE))} bytes"
    )
    for result in results:
        print(
            f"{result.name}: total={sum(result.sizes)} bytes, "
            f"encode_p50={_nearest_rank(result.encode_ns, 0.50) / 1_000:.2f} us, "
            f"decode_p50={_nearest_rank(result.decode_ns, 0.50) / 1_000:.2f} us"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
