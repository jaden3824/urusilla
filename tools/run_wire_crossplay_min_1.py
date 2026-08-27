#!/usr/bin/env python3
"""Run the bounded WIRE-CROSSPLAY-MIN-1 experiment entirely offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
from typing import Any, Iterable, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urusilla import normalize_message  # noqa: E402
from urusilla_wire_v02 import (  # noqa: E402
    DEFAULT_PROFILE,
    DEFAULT_REGISTRY,
    MAGIC,
    StaticProfile,
    decode_message,
    encode_capsule,
    encode_message,
)


FORMAT = "urusilla-wire-crossplay-min-result/1"
EXPERIMENT = "WIRE-CROSSPLAY-MIN-1"
SCHEMA = "urn:urusilla:wire-crossplay-min:1"
REQUEST_PREDICATE = "urn:urusilla:wire-crossplay:min:select"
RESULT_PREDICATE = "urn:urusilla:wire-crossplay:min:selection"
FALLBACK_PREDICATE = "urn:urusilla:wire-crossplay:min:fallback"
SENDER = "urn:agent:python-sender"
RESPONDER = "urn:agent:node-responder"
NODE_RESPONDER = (
    ROOT
    / "independent_impl"
    / "rust"
    / "tools"
    / "wire_crossplay_min_1_responder.mjs"
)
SESSION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "urusilla:wire-crossplay-min-1:session"))
MAX_RECORDS = 16
MAX_RECORD_BYTES = 16 * 1024 * 1024


class CrossplayError(AssertionError):
    """Raised when the bounded cross-runtime experiment violates a gate."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _u32(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise CrossplayError("stdio length is outside uint32")
    return struct.pack(">I", value)


def _pack_input(records: Sequence[bytes], *, capsule: bytes | None) -> bytes:
    if len(records) > MAX_RECORDS:
        raise CrossplayError("too many experiment records")
    parts: list[bytes] = []
    if capsule is not None:
        parts.extend((_u32(len(capsule)), capsule))
    parts.append(_u32(len(records)))
    for record in records:
        if len(record) > MAX_RECORD_BYTES:
            raise CrossplayError("experiment record exceeds limit")
        parts.extend((_u32(len(record)), record))
    return b"".join(parts)


def _unpack_output(data: bytes) -> list[tuple[int, bytes]]:
    offset = 0

    def read(length: int) -> bytes:
        nonlocal offset
        if offset + length > len(data):
            raise CrossplayError("truncated responder output")
        value = data[offset : offset + length]
        offset += length
        return value

    count = struct.unpack(">I", read(4))[0]
    if count > MAX_RECORDS:
        raise CrossplayError("responder output count exceeds limit")
    result: list[tuple[int, bytes]] = []
    for _ in range(count):
        status = read(1)[0]
        length = struct.unpack(">I", read(4))[0]
        if length > MAX_RECORD_BYTES:
            raise CrossplayError("responder output record exceeds limit")
        result.append((status, read(length)))
    if offset != len(data):
        raise CrossplayError("responder output has trailing bytes")
    return result


def _case_uuid(case_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"urusilla:wire-crossplay-min-1:{case_id}"))


def _safety_constraint() -> dict[str, Any]:
    return {
        "kind": "constraint",
        "scope": "safety",
        "mode": "hard",
        "condition": {
            "external_effects": False,
            "permission_expansion": False,
            "persistence": False,
            "spending_authority": False,
        },
    }


def _request(
    case_id: str,
    *,
    branch: str | None,
    invariant_marker: str,
    include_payload: bool = True,
) -> dict[str, Any]:
    arguments: list[Any] = []
    if include_payload:
        payload: dict[str, Any] = {
            "candidates": {"A": "route-alpha", "B": "route-beta"},
            "values": [7, 11, 13],
            "invariant_marker": invariant_marker,
        }
        if branch is not None:
            payload["branch"] = branch
        arguments.append(payload)
    return normalize_message(
        {
            "id": _case_uuid(case_id),
            "session": SESSION_ID,
            "sender": SENDER,
            "recipients": [RESPONDER],
            "act": "REQUEST",
            "reply_to": None,
            "schema": SCHEMA,
            "logical_clock": 10,
            "expires_ms": 0,
            "confidence_ppm": 1_000_000,
            "expected": ["ASSERT"],
            "body": {
                "kind": "goal",
                "condition": {
                    "kind": "claim",
                    "predicate": REQUEST_PREDICATE,
                    "arguments": arguments,
                },
                "constraints": [_safety_constraint()],
            },
            "meta": {"experiment": EXPERIMENT, "case_id": case_id},
        }
    )


def _positive_requests() -> list[tuple[str, dict[str, Any]]]:
    return [
        ("critical-a", _request("critical-a", branch="A", invariant_marker="stable")),
        ("critical-b", _request("critical-b", branch="B", invariant_marker="stable")),
        (
            "inert-metadata",
            _request("inert-metadata", branch="A", invariant_marker="changed-but-inert"),
        ),
        (
            "missing-branch",
            _request("missing-branch", branch=None, invariant_marker="stable"),
        ),
        (
            "no-payload",
            _request(
                "no-payload",
                branch=None,
                invariant_marker="stable",
                include_payload=False,
            ),
        ),
    ]


def _run_node(mode: str, packed_input: bytes) -> tuple[bytes, list[tuple[int, bytes]]]:
    node = shutil.which("node")
    if node is None:
        raise CrossplayError("Node.js is required for the cross-runtime lane")
    process = subprocess.run(
        [node, str(NODE_RESPONDER), "--mode", mode],
        cwd=ROOT,
        input=packed_input,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        diagnostic = process.stderr.decode("utf-8", errors="replace").strip()
        raise CrossplayError(f"Node responder failed in {mode} mode: {diagnostic}")
    if process.stderr:
        raise CrossplayError(f"Node responder wrote unexpected stderr in {mode} mode")
    return process.stdout, _unpack_output(process.stdout)


def _expected_body(case_id: str) -> dict[str, Any]:
    if case_id in {"critical-a", "inert-metadata"}:
        return {
            "kind": "claim",
            "predicate": RESULT_PREDICATE,
            "arguments": [{"selected": "route-alpha", "total": 31}],
        }
    if case_id == "critical-b":
        return {
            "kind": "claim",
            "predicate": RESULT_PREDICATE,
            "arguments": [{"selected": "route-beta", "total": 31}],
        }
    reason = {"missing-branch": "missing-branch", "no-payload": "missing-payload"}[case_id]
    return {
        "kind": "claim",
        "predicate": FALLBACK_PREDICATE,
        "arguments": [{"reason_code": reason}],
    }


def _validate_response(
    case_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> None:
    expected_envelope = {
        "session": request["session"],
        "sender": RESPONDER,
        "recipients": [SENDER],
        "act": "ASSERT",
        "reply_to": request["id"],
        "schema": SCHEMA,
        "logical_clock": request["logical_clock"] + 1,
        "expires_ms": 0,
        "confidence_ppm": 1_000_000,
        "expected": [],
        "body": _expected_body(case_id),
        "meta": {"experiment": EXPERIMENT, "effect_authorized": False},
    }
    for key, value in expected_envelope.items():
        if response[key] != value:
            raise CrossplayError(f"{case_id}: response {key} differs")
    if response["id"] == request["id"]:
        raise CrossplayError(f"{case_id}: response reused request ID")


def _decode_json_response(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(text)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CrossplayError(f"JSON control response is invalid: {exc}") from exc
    if _canonical_json_bytes(value) != payload:
        raise CrossplayError("JSON control response is not canonical")
    return normalize_message(value)


def _percent_saved(candidate: int, baseline: int) -> float:
    return round((baseline - candidate) * 100.0 / baseline, 3)


def _git_revision() -> str | None:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        return None
    return process.stdout.strip()


def run_experiment() -> dict[str, Any]:
    requests = _positive_requests()
    request_ids = [request["id"] for _, request in requests]
    if len(set(request_ids)) != len(request_ids):
        raise CrossplayError("request IDs are not unique")

    capsule = encode_capsule(DEFAULT_PROFILE)
    wire_requests = [encode_message(request) for _, request in requests]
    json_requests = [_canonical_json_bytes(request) for _, request in requests]
    if any(not frame.startswith(MAGIC) for frame in wire_requests):
        raise CrossplayError("wire request does not use raw UrusillaWire v0.2")

    wire_input = _pack_input(wire_requests, capsule=capsule)
    json_input = _pack_input(json_requests, capsule=None)
    wire_output, wire_records = _run_node("wire", wire_input)
    json_output, json_records = _run_node("json", json_input)
    if len(wire_records) != len(requests) or len(json_records) != len(requests):
        raise CrossplayError("positive response count differs")

    case_results: list[dict[str, Any]] = []
    wire_responses: list[dict[str, Any]] = []
    json_responses: list[dict[str, Any]] = []
    response_ids: set[str] = set()
    for index, (case_id, request) in enumerate(requests):
        wire_status, wire_payload = wire_records[index]
        json_status, json_payload = json_records[index]
        if wire_status != 0 or json_status != 0:
            raise CrossplayError(f"{case_id}: positive case was rejected")
        if wire_payload == wire_requests[index]:
            raise CrossplayError(f"{case_id}: byte echo was accepted")

        wire_response = decode_message(wire_payload, DEFAULT_REGISTRY)
        if encode_message(wire_response) != wire_payload:
            raise CrossplayError(f"{case_id}: wire response is not canonical")
        json_response = _decode_json_response(json_payload)
        _validate_response(case_id, request, wire_response)
        _validate_response(case_id, request, json_response)
        if wire_response != json_response:
            raise CrossplayError(f"{case_id}: wire and JSON paths changed semantics")
        if wire_response["id"] in response_ids:
            raise CrossplayError(f"{case_id}: response ID was reused")
        response_ids.add(wire_response["id"])
        wire_responses.append(wire_response)
        json_responses.append(json_response)
        case_results.append(
            {
                "case_id": case_id,
                "request_id": request["id"],
                "wire_request_bytes": len(wire_requests[index]),
                "wire_request_sha256": _sha256(wire_requests[index]),
                "json_request_bytes": len(json_requests[index]),
                "json_request_sha256": _sha256(json_requests[index]),
                "response_id": wire_response["id"],
                "wire_response_bytes": len(wire_payload),
                "wire_response_sha256": _sha256(wire_payload),
                "json_response_bytes": len(json_payload),
                "json_response_sha256": _sha256(json_payload),
                "body": wire_response["body"],
            }
        )

    if wire_responses[0]["body"] == wire_responses[1]["body"]:
        raise CrossplayError("task-critical A/B change did not change the result")
    if wire_responses[0]["body"] != wire_responses[2]["body"]:
        raise CrossplayError("inert marker changed the derived result")

    corrupted = bytearray(wire_requests[0])
    corrupted[-1] ^= 0x01
    unknown_profile = StaticProfile(
        profile_id=2,
        name="urusilla-wire-crossplay-min-unknown-profile",
        strings=DEFAULT_PROFILE.strings,
        shapes=DEFAULT_PROFILE.shapes,
    )
    unknown_profile_frame = encode_message(requests[0][1], unknown_profile)
    negative_input = _pack_input([bytes(corrupted), unknown_profile_frame], capsule=capsule)
    negative_output, negative_records = _run_node("wire", negative_input)
    expected_rejections = ["checksum", "unknown_profile"]
    if len(negative_records) != len(expected_rejections):
        raise CrossplayError("negative response count differs")
    observed_rejections: list[str] = []
    for (status, payload), expected in zip(negative_records, expected_rejections):
        if status != 1:
            raise CrossplayError(f"negative control {expected} produced a reply frame")
        try:
            code = payload.decode("ascii", errors="strict")
        except UnicodeError as exc:
            raise CrossplayError("negative rejection code is not ASCII") from exc
        if code != expected:
            raise CrossplayError(f"negative control expected {expected}, observed {code}")
        observed_rejections.append(code)

    profile_transfer_bytes = 4 + len(capsule)
    wire_cold_total = len(wire_input) + len(wire_output)
    wire_warm_total = wire_cold_total - profile_transfer_bytes
    json_total = len(json_input) + len(json_output)
    source_paths = [Path(__file__).resolve(), NODE_RESPONDER]
    node_version = subprocess.run(
        [shutil.which("node") or "node", "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    return {
        "format": FORMAT,
        "experiment_id": EXPERIMENT,
        "date": "2026-08-28",
        "source_parent_revision": _git_revision(),
        "classification": (
            "same-project-cross-runtime-raw-wire-structural-and-"
            "observable-task-dependence"
        ),
        "runtime": {
            "python": platform.python_version(),
            "node": node_version,
            "model_calls": 0,
            "provider_calls": 0,
            "network_calls_by_harness": 0,
            "github_actions_runs": 0,
        },
        "protocol": {
            "semantic_contract": "UrusillaIR 0.1.0",
            "wire_codec": "experimental UrusillaWire v0.2 static profile",
            "transport": "raw bytes over local length-prefixed stdio",
            "base64_used": False,
            "profile_id": DEFAULT_PROFILE.profile_id,
            "profile_dictionary_id_hex": DEFAULT_PROFILE.dictionary_id_hex,
            "profile_capsule_bytes": len(capsule),
            "profile_capsule_sha256": _sha256(capsule),
        },
        "functional_gates": {
            "python_to_node_raw_wire": True,
            "node_to_python_raw_wire": True,
            "canonical_reencode": True,
            "wire_json_semantic_identity": True,
            "byte_echo_rejected": True,
            "unique_reply_binding": True,
            "task_critical_a_b_flip": True,
            "inert_field_invariance": True,
            "missing_branch_fallback": True,
            "no_payload_fallback": True,
            "corruption_rejected_before_reply": True,
            "unknown_profile_rejected_before_reply": True,
            "external_effect_authority": False,
        },
        "cases": case_results,
        "negative_controls": {
            "records": [
                {
                    "case_id": "corrupted-checksum",
                    "input_bytes": len(corrupted),
                    "input_sha256": _sha256(bytes(corrupted)),
                    "rejection_code": observed_rejections[0],
                },
                {
                    "case_id": "unknown-profile",
                    "input_bytes": len(unknown_profile_frame),
                    "input_sha256": _sha256(unknown_profile_frame),
                    "rejection_code": observed_rejections[1],
                },
            ],
            "input_stream_bytes": len(negative_input),
            "output_stream_bytes": len(negative_output),
            "reply_frames_emitted": 0,
        },
        "byte_accounting": {
            "case_count": len(requests),
            "stdio_framing": (
                "4-byte input lengths; 4-byte counts; 1-byte output status plus "
                "4-byte output lengths"
            ),
            "wire_request_payload_bytes": sum(map(len, wire_requests)),
            "wire_response_payload_bytes": sum(
                len(payload) for status, payload in wire_records if status == 0
            ),
            "wire_profile_transfer_bytes_including_length": profile_transfer_bytes,
            "wire_cold_framed_total_bytes": wire_cold_total,
            "wire_warm_framed_total_bytes_excluding_profile": wire_warm_total,
            "json_request_payload_bytes": sum(map(len, json_requests)),
            "json_response_payload_bytes": sum(
                len(payload) for status, payload in json_records if status == 0
            ),
            "json_framed_total_bytes": json_total,
            "wire_cold_saved_vs_json_percent": _percent_saved(wire_cold_total, json_total),
            "wire_warm_saved_vs_json_percent": _percent_saved(wire_warm_total, json_total),
            "scope": (
                "Local stdio byte accounting for these five fixed records only; "
                "no Base64, HTTP, TLS, token, latency, task-success, or energy claim."
            ),
        },
        "implementation_sources": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha256(path.read_bytes()),
            }
            for path in source_paths
        ],
        "claim_boundary": (
            "This run proves only same-project Python/Node raw-wire exchange, exact "
            "canonical semantic agreement, observable task-field dependence, bounded "
            "fallbacks, and two fail-closed decoder controls. It is not an external or "
            "clean-room reproduction, model-native language use, causal-agent-use proof, "
            "authentication, replay protection, adoption, standardization, security "
            "certification, or end-to-end efficiency evidence."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing --output file after a successful run",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if args.output is not None and args.output.exists() and not args.replace:
        raise SystemExit(f"refusing to overwrite existing result: {args.output}")
    result = run_experiment()
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"PASS {EXPERIMENT} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
