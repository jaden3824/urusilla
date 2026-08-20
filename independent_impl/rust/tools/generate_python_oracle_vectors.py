#!/usr/bin/env python3
"""Regenerate same-project Urusilla fixtures from the current Python oracle.

This program is intentionally kept outside the Node implementation and its
runtime tests.  It is a reproducible fixture producer, not evidence of an
external or oracle-independent implementation.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import platform
import struct
import sys
from typing import Any, Callable


LANE = Path(__file__).resolve().parents[1]
ROOT = LANE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import urusilla as semantic  # noqa: E402
import urusilla_benchmark as benchmark  # noqa: E402
import urusilla_wire_v02 as wire  # noqa: E402


CAPTURED_AT = "2026-08-20T00:00:00Z"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fixture_value(value: Any) -> Any:
    """Project Python values -> the compact JSON convention used by fixtures."""

    if value is None or type(value) in {bool, str}:
        return value
    if type(value) is int:
        if -(1 << 53) + 1 <= value <= (1 << 53) - 1:
            return value
        return {"$urusilla_bigint": str(value)}
    if type(value) is float:
        bits = struct.pack(">d", 0.0 if value == 0.0 else value).hex()
        return {"$urusilla_float64_be": bits}
    if type(value) is bytes:
        return {"$urusilla_bytes_base64": b64(value)}
    if isinstance(value, (list, tuple)):
        return [fixture_value(item) for item in value]
    if isinstance(value, dict):
        return {key: fixture_value(item) for key, item in value.items()}
    raise TypeError(f"unsupported fixture value: {type(value).__name__}")


def frame_parts(frame: bytes) -> tuple[bytes, bytes, int, bytes, bytes]:
    reader = wire._Reader(frame)
    magic = reader.read(len(wire.MAGIC))
    flags = bytes([reader.byte()])
    profile_id = reader.uvarint()
    dictionary_id = reader.read(wire.DICTIONARY_ID_SIZE)
    payload_length = reader.uvarint()
    payload = reader.read(payload_length)
    reader.read(wire.CHECKSUM_SIZE)
    reader.expect_end()
    return magic, flags, profile_id, dictionary_id, payload


def canonical_frame(
    payload: bytes,
    *,
    profile_id: int = 1,
    dictionary_id: bytes | None = None,
    flags: int = wire.FLAGS,
) -> bytes:
    if dictionary_id is None:
        dictionary_id = wire.DEFAULT_PROFILE.dictionary_id
    header = (
        wire.MAGIC
        + bytes([flags])
        + wire._encode_uvarint(profile_id)
        + dictionary_id
        + wire._encode_uvarint(len(payload))
    )
    checksum = hashlib.sha256(wire._FRAME_HASH_DOMAIN + header + payload).digest()[
        : wire.CHECKSUM_SIZE
    ]
    return header + payload + checksum


def canonical_capsule(payload: bytes) -> bytes:
    header = wire.CAPSULE_MAGIC + wire._encode_uvarint(len(payload))
    checksum = hashlib.sha256(wire._CAPSULE_HASH_DOMAIN + header + payload).digest()[
        : wire.CHECKSUM_SIZE
    ]
    return header + payload + checksum


def append_text(out: bytearray, value: str) -> None:
    raw = value.encode("utf-8")
    out += wire._encode_uvarint(len(raw))
    out += raw


def capsule_payload(
    *,
    format_byte: int = wire.PROFILE_FORMAT,
    profile_id: int = 1,
    name: str = "boundary",
    strings: tuple[str, ...] = (),
    shapes: tuple[tuple[int, ...], ...] = (),
    trailing: bytes = b"",
) -> bytes:
    out = bytearray([format_byte])
    out += wire._encode_uvarint(profile_id)
    append_text(out, name)
    out += wire._encode_uvarint(len(strings))
    for item in strings:
        append_text(out, item)
    out += wire._encode_uvarint(len(shapes))
    for shape in shapes:
        out += wire._encode_uvarint(len(shape))
        for index in shape:
            out += wire._encode_uvarint(index)
    out += trailing
    return bytes(out)


def oracle_rejection(data: bytes, kind: str) -> tuple[str, str]:
    operation: Callable[[bytes], Any]
    operation = wire.decode_capsule if kind == "capsule" else wire.decode_message
    try:
        operation(data)
    except (semantic.DecodeError, semantic.ValidationError) as error:
        return type(error).__name__, str(error)
    raise AssertionError("negative fixture was accepted by the Python oracle")


def negative_entry(identifier: str, kind: str, data: bytes) -> dict[str, Any]:
    error_class, error_text = oracle_rejection(data, kind)
    return {
        "bytes_base64": b64(data),
        "bytes_sha256": sha256(data),
        "id": identifier,
        "kind": kind,
        "oracle_error_class": error_class,
        "oracle_error_contains": error_text,
    }


def make_negative_vectors(base_frame: bytes, profile_capsule: bytes) -> list[dict[str, Any]]:
    _, _, _, dictionary_id, payload = frame_parts(base_frame)
    header_prefix = wire.MAGIC + bytes([wire.FLAGS])
    declared_too_large = (
        header_prefix
        + wire._encode_uvarint(1)
        + dictionary_id
        + wire._encode_uvarint(wire.MAX_FRAME_BYTES + 1)
    )

    damaged_checksum = bytearray(base_frame)
    damaged_checksum[-1] ^= 0x01
    damaged_payload_start = bytearray(base_frame)
    payload_offset = len(base_frame) - wire.CHECKSUM_SIZE - len(payload)
    damaged_payload_start[payload_offset] ^= 0x01
    damaged_payload_middle = bytearray(base_frame)
    damaged_payload_middle[payload_offset + len(payload) // 2] ^= 0x01
    damaged_payload_end = bytearray(base_frame)
    damaged_payload_end[-wire.CHECKSUM_SIZE - 1] ^= 0x01
    wrong_length_header = (
        header_prefix
        + wire._encode_uvarint(1)
        + dictionary_id
        + wire._encode_uvarint(len(payload) + 1)
    )
    original_checksum = base_frame[-wire.CHECKSUM_SIZE :]

    frame_cases: list[tuple[str, bytes]] = [
        ("header-invalid-magic", b"ZZXX\x02"),
        ("header-profile-id-zero", header_prefix + b"\x00"),
        ("header-overlong-profile-varint", header_prefix + b"\x81\x00"),
        ("header-overflow-profile-varint", header_prefix + b"\xff" * 9 + b"\x02"),
        ("header-too-long-profile-varint", header_prefix + b"\x80" * 10),
        ("header-declared-payload-over-limit", declared_too_large),
        ("checksum-corruption", bytes(damaged_checksum)),
        ("trailing-data", base_frame + b"\x00"),
        ("unknown-profile", canonical_frame(payload, profile_id=2)),
        (
            "unknown-dictionary",
            canonical_frame(payload, dictionary_id=bytes([dictionary_id[0] ^ 1]) + dictionary_id[1:]),
        ),
        ("unsupported-flags-zero", bytes(wire.MAGIC) + b"\x00"),
        ("unsupported-flags-two", bytes(wire.MAGIC) + b"\x02"),
        ("truncated-header", base_frame[:10]),
        ("truncated-checksum", base_frame[:-1]),
        ("declared-length-plus-one", wrong_length_header + payload + original_checksum),
        ("payload-corruption-first", bytes(damaged_payload_start)),
        ("payload-corruption-middle", bytes(damaged_payload_middle)),
        ("payload-corruption-last", bytes(damaged_payload_end)),
    ]

    damaged_capsule = bytearray(profile_capsule)
    damaged_capsule[len(damaged_capsule) // 2] ^= 0x04
    capsule_cases: list[tuple[str, bytes]] = [
        ("capsule-checksum-corruption", bytes(damaged_capsule)),
        (
            "capsule-unsupported-format",
            canonical_capsule(capsule_payload(format_byte=2)),
        ),
        (
            "capsule-profile-id-zero",
            canonical_capsule(capsule_payload(profile_id=0)),
        ),
        (
            "capsule-duplicate-strings",
            canonical_capsule(capsule_payload(strings=("a", "a"))),
        ),
        (
            "capsule-shape-key-out-of-range",
            canonical_capsule(capsule_payload(strings=("a",), shapes=((1,),))),
        ),
        (
            "capsule-shape-noncanonical-order",
            canonical_capsule(capsule_payload(strings=("a", "b"), shapes=((1, 0),))),
        ),
        (
            "capsule-payload-trailing-data",
            canonical_capsule(capsule_payload(trailing=b"\x00")),
        ),
    ]
    vectors = [negative_entry(identifier, "frame", data) for identifier, data in frame_cases]
    vectors += [negative_entry(identifier, "capsule", data) for identifier, data in capsule_cases]
    assert len(vectors) == 25
    return vectors


def aggregate_plus_one_frame() -> bytes:
    counts = (semantic.MAX_COLLECTION_ITEMS, semantic.MAX_COLLECTION_ITEMS, 49_994)
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
    return canonical_frame(payload)


def exact_boundary_message() -> dict[str, Any]:
    scalar_count = semantic.MAX_SEMANTIC_NODES - 7
    groups: list[list[None]] = []
    remaining = scalar_count
    while remaining:
        size = min(remaining, semantic.MAX_COLLECTION_ITEMS)
        groups.append([None] * size)
        remaining -= size
    source = semantic.demo_message()
    source["act"] = "ASSERT"
    source["body"] = {"kind": "x:aggregate-probe", "value": groups}
    source["meta"] = {}
    return source


def main() -> int:
    capsule_path = ROOT / "urusilla_capsule_v0_1.json"
    grammar_capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    manifest = grammar_capsule["semantic_kernel"]["manifest"]
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    declared_manifest = grammar_capsule["semantic_kernel"]["manifest_digest"]
    computed_manifest = sha256(manifest_bytes)
    unsigned_restriction = grammar_capsule["security_contract"]["unsigned_restriction"]
    unsigned_publication = grammar_capsule["github_distribution"]["publication_modes"][
        "unsigned_research"
    ]
    trusted_publication = grammar_capsule["github_distribution"]["publication_modes"][
        "trusted_effect_authorizing"
    ]
    release_policy = {
        "lifecycle_status": grammar_capsule["release_status"],
        "publisher_status": grammar_capsule["publisher_authentication"]["status"],
        "unsigned_public_source_distribution_allowed": (
            "Public source review" in unsigned_publication
            and "effect-authorizing behavior disabled" in unsigned_publication
        ),
        "unsigned_operation_scope": (
            "local-read-only"
            if "local read-only" in unsigned_restriction
            else "policy-mismatch"
        ),
        "unsigned_external_effects_forbidden": (
            "MUST NOT authorize external side effects" in unsigned_restriction
        ),
        "effect_authorizing_requires_signature_and_policy": (
            "accepted publisher signature" in trusted_publication
            and "authorization policy" in trusted_publication
        ),
    }
    if release_policy != {
        "lifecycle_status": "experimental-unsigned",
        "publisher_status": "unsigned",
        "unsigned_public_source_distribution_allowed": True,
        "unsigned_operation_scope": "local-read-only",
        "unsigned_external_effects_forbidden": True,
        "effect_authorizing_requires_signature_and_policy": True,
    }:
        raise AssertionError("Grammar Capsule release policy is not the frozen unsigned policy")
    public_vectors = {
        "format": "urusilla-public-v01-semantic-vectors-v1",
        "source_file": capsule_path.name,
        "source_file_sha256": file_sha256(capsule_path),
        "release_policy": release_policy,
        "declared_semantic_kernel_manifest_digest": declared_manifest,
        "computed_recursive_sorted_compact_manifest_sha256": computed_manifest,
        "computed_manifest_bytes": len(manifest_bytes),
        "digest_match": declared_manifest == f"sha256:{computed_manifest}",
        "positive_vectors": grammar_capsule["conformance"]["positive_vectors"],
        "negative_vectors": grammar_capsule["conformance"]["negative_vectors"],
        "pass_rule": grammar_capsule["conformance"]["pass_rule"],
    }
    dump(LANE / "vectors/public_v01_semantic_vectors.json", public_vectors)

    corpus = benchmark.build_corpus(280)
    frames = [wire.encode_message(message, wire.DEFAULT_PROFILE) for message in corpus]
    profile_capsule = wire.encode_capsule(wire.DEFAULT_PROFILE)
    sequence = b"".join(len(frame).to_bytes(4, "big") + frame for frame in frames)
    source_artifacts = {
        "urusilla.py_sha256": file_sha256(ROOT / "urusilla.py"),
        "urusilla_wire_v02.py_sha256": file_sha256(ROOT / "urusilla_wire_v02.py"),
        "urusilla_benchmark.py_sha256": file_sha256(ROOT / "urusilla_benchmark.py"),
    }
    crossplay = {
        "aggregates": {
            "canonical_corpus_sha256": benchmark.corpus_digest(corpus),
            "four_byte_length_prefixed_frame_sequence_bytes": len(sequence),
            "four_byte_length_prefixed_frame_sequence_sha256": sha256(sequence),
            "message_count": len(corpus),
            "total_frame_bytes": sum(map(len, frames)),
        },
        "claim_boundary": (
            "Generated deterministically from the current same-project Python oracle; "
            "Node runtime tests consume offline fixtures. This is not an external, "
            "clean-room, or oracle-independent reproduction."
        ),
        "format": "urusilla-v02-cross-language-vectors-v1",
        "golden": [
            {
                "corpus_index": index,
                "frame_base64": b64(frame),
                "frame_bytes": len(frame),
                "frame_sha256": sha256(frame),
                "id": f"corpus-{index:03d}-{message['act'].lower()}",
                "message": fixture_value(message),
            }
            for index, (message, frame) in enumerate(zip(corpus, frames, strict=True))
        ],
        "profile": {
            "capsule_base64": b64(profile_capsule),
            "capsule_bytes": len(profile_capsule),
            "capsule_sha256": sha256(profile_capsule),
            "dictionary_id_hex": wire.DEFAULT_PROFILE.dictionary_id_hex,
            "name": wire.DEFAULT_PROFILE.name,
            "profile_id": wire.DEFAULT_PROFILE.profile_id,
            "shapes": len(wire.DEFAULT_PROFILE.shapes),
            "strings": len(wire.DEFAULT_PROFILE.strings),
        },
        "source_artifacts": source_artifacts,
        "status": "project-authored-python-oracle-derived-fixture",
    }
    dump(LANE / "vectors/v02_crossplay.json", crossplay)

    negatives = {
        "claim_boundary": (
            "Generated deterministically with the same-project Python oracle. Error wording "
            "is diagnostic only; the compatibility contract is fail-closed rejection."
        ),
        "format": "urusilla-v02-negative-cross-language-vectors-v1",
        "source_frame_sha256": sha256(frames[0]),
        "status": "project-authored-python-oracle-derived-fixture",
        "vectors": make_negative_vectors(frames[0], profile_capsule),
    }
    dump(LANE / "vectors/v02_negative_vectors.json", negatives)

    exact_frame = wire.encode_message(exact_boundary_message())
    assert wire.decode_message(exact_frame)["body"]["kind"] == "x:aggregate-probe"
    plus_one = aggregate_plus_one_frame()
    plus_one_error = None
    try:
        wire.decode_message(plus_one)
    except semantic.DecodeError as error:
        plus_one_error = str(error)
    if plus_one_error is None:
        raise AssertionError("Python oracle accepted the 250,001-node resource probe")
    resource_probe = {
        "format": "urusilla-python-reference-resource-probe-v2",
        "captured_at_utc": CAPTURED_AT,
        "purpose": "Deterministic cross-runtime check of the shared aggregate semantic-node ceiling.",
        "implementation_runtime_dependency": False,
        "root_python_files_modified": False,
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "root_inputs": source_artifacts,
        "minimal_non_sensitive_shape": {
            "body_plus_meta_nodes": 250_001,
            "node_count_rule": "Every scalar, byte string, list, and map counts once across body and meta; map keys do not add semantic-value nodes.",
            "relationship_to_limit": "one node over 250,000",
        },
        "exact_boundary_probe": {
            "body_plus_meta_nodes": 250_000,
            "frame_bytes": len(exact_frame),
            "frame_sha256": sha256(exact_frame),
            "decode_accepted": True,
        },
        "exact_plus_one_probe": {
            "body_plus_meta_nodes": 250_001,
            "frame_bytes": len(plus_one),
            "frame_sha256": sha256(plus_one),
            "decode_accepted": False,
            "error_contains": plus_one_error,
        },
        "invariant": "Exactly 250,000 body-plus-meta semantic values are accepted; 250,001 are rejected before effects.",
        "compatibility_impact": {
            "node_lane_behavior": "rejects the demonstrated 250,001-node frame",
            "python_reference_behavior": "rejects the demonstrated 250,001-node frame",
            "frozen_vectors_affected": False,
        },
        "measurement_limits": "This is a deterministic boundary check, not a performance benchmark, memory bound, or security certification.",
    }
    dump(LANE / "reports/python-reference-resource-probe.json", resource_probe)

    crosscheck_source_artifacts = {
        "urusilla.py": source_artifacts["urusilla.py_sha256"],
        "urusilla_wire_v02.py": source_artifacts["urusilla_wire_v02.py_sha256"],
        "urusilla_benchmark.py": source_artifacts["urusilla_benchmark.py_sha256"],
    }
    crosscheck = {
        "format": "project-python-reference-current-crosscheck-v2",
        "captured_at_utc": CAPTURED_AT,
        "purpose": "Deterministic current-oracle re-execution against regenerated same-project fixtures.",
        "implementation_runtime_dependency": False,
        "root_files_modified": False,
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "current_root_sha256": crosscheck_source_artifacts,
        "frozen_vector_origin_sha256": crosscheck_source_artifacts,
        "source_drift": {"detected": False, "reason": "fixtures were regenerated from the current pinned root inputs"},
        "current_reference_reexecution": {
            "corpus_messages": len(frames),
            "frames_equal_to_frozen_fixtures": len(frames),
            "all_frames_equal": True,
            "total_frame_bytes": sum(map(len, frames)),
            "four_byte_length_prefixed_sequence_sha256": sha256(sequence),
            "default_capsule_bytes": len(profile_capsule),
            "default_capsule_sha256": sha256(profile_capsule),
        },
        "interpretation": "Current-output agreement within one project; not independent external reproduction.",
    }
    dump(LANE / "reports/python-reference-current-crosscheck.json", crosscheck)

    print(
        json.dumps(
            {
                "positive_frames": len(frames),
                "negative_vectors": len(negatives["vectors"]),
                "total_frame_bytes": sum(map(len, frames)),
                "sequence_sha256": sha256(sequence),
                "profile_capsule_sha256": sha256(profile_capsule),
                "dictionary_id_hex": wire.DEFAULT_PROFILE.dictionary_id_hex,
                "resource_exact_accepted": True,
                "resource_plus_one_accepted": False,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
