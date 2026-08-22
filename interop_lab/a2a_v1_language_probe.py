#!/usr/bin/env python3
"""Build and verify the frozen A2A v1 carriage of the public language probe.

This fixture uses the standard A2A v1 ``Part.data`` member.  It does not claim
an A2A extension, endpoint integration, conformance, adoption, or byte-for-byte
preservation of the pretty-printed source file.  The carried probe is instead
bound through canonical JSON while the original source-byte identity remains a
separate provenance field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import uuid
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "website" / "public" / "language-probe.json"
MESSAGE_PATH = (
    ROOT / "interop_lab" / "evidence" / "a2a_v1_language_probe_001.message.json"
)
MANIFEST_PATH = (
    ROOT / "interop_lab" / "evidence" / "a2a_v1_language_probe_001.manifest.json"
)

A2A_VERSION = "1.0.1"
A2A_SPEC_COMMIT = "3303592588e388e62e0f69f701af531d2f4e3991"
A2A_SPEC_URI = (
    "https://github.com/a2aproject/A2A/blob/"
    + A2A_SPEC_COMMIT
    + "/specification/a2a.proto"
)
SOURCE_URI = "https://urusilla-language.pages.dev/language-probe.json"
FORMAT = "urusilla-a2a-v1-language-probe-carriage/1"
SAFE_INTEGER_MIN = -(2**53 - 1)
SAFE_INTEGER_MAX = 2**53 - 1


class A2ALanguageProbeError(ValueError):
    """The frozen A2A fixture or its source binding is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise A2ALanguageProbeError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                A2ALanguageProbeError("floating-point JSON is forbidden")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                A2ALanguageProbeError("non-finite JSON is forbidden")
            ),
        )
    except A2ALanguageProbeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A2ALanguageProbeError("invalid JSON") from exc


def _validate_json_value(value: Any, *, path: str = "$") -> None:
    if value is None or type(value) is bool or type(value) is str:
        return
    if type(value) is int:
        if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
            raise A2ALanguageProbeError(f"integer outside ProtoJSON-safe range at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise A2ALanguageProbeError(f"non-string object key at {path}")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise A2ALanguageProbeError(f"unsupported JSON value at {path}")


def canonical_json(value: Any) -> str:
    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_canonical(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def load_probe(source_path: Path = SOURCE_PATH) -> tuple[bytes, dict[str, Any]]:
    source_bytes = source_path.read_bytes()
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise A2ALanguageProbeError("probe source is not UTF-8") from exc
    value = strict_json_loads(source_text)
    if not isinstance(value, dict):
        raise A2ALanguageProbeError("probe source must be a JSON object")
    _validate_json_value(value)
    return source_bytes, value


def build_message(source_bytes: bytes, probe: Mapping[str, Any]) -> dict[str, Any]:
    probe_value = dict(probe)
    probe_canonical_sha256 = sha256_canonical(probe_value)
    source_sha256 = sha256_bytes(source_bytes)
    data = {
        "format": FORMAT,
        "probe": probe_value,
        "probeCanonicalSha256": probe_canonical_sha256,
        "probeSourceBytes": len(source_bytes),
        "probeSourceSha256": source_sha256,
        "probeSourceUri": SOURCE_URI,
    }
    message_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{FORMAT}:{source_sha256}:{probe_canonical_sha256}",
        )
    )
    return {
        "messageId": message_id,
        "role": "ROLE_USER",
        "parts": [{"data": data, "mediaType": "application/json"}],
    }


def build_manifest(
    source_bytes: bytes,
    probe: Mapping[str, Any],
    message: Mapping[str, Any],
) -> dict[str, Any]:
    part = message["parts"][0]
    return {
        "format": "urusilla-a2a-v1-language-probe-manifest/1",
        "a2a": {
            "released_version": A2A_VERSION,
            "normative_proto_commit": A2A_SPEC_COMMIT,
            "normative_proto_uri": A2A_SPEC_URI,
            "part_content_member": "data",
            "json_binding_media_type": "application/a2a+json",
        },
        "fixture": {
            "message_file": MESSAGE_PATH.name,
            "message_canonical_sha256": sha256_canonical(message),
            "part_data_canonical_sha256": sha256_canonical(part["data"]),
            "message_id": message["messageId"],
        },
        "probe": {
            "source_uri": SOURCE_URI,
            "source_bytes": len(source_bytes),
            "source_sha256": sha256_bytes(source_bytes),
            "canonical_sha256": sha256_canonical(dict(probe)),
        },
        "transport_semantics": {
            "pretty_printed_source_bytes_carried": False,
            "canonical_json_value_carried": True,
            "source_byte_identity_is_provenance_only": True,
            "a2a_extension_claimed": False,
            "endpoint_or_sdk_required": False,
            "external_effects_authorized": False,
        },
        "claim_boundary": (
            "A passing independent unwrap shows only that one A2A v1 implementation "
            "preserved this standard Data Part JSON value and its declared digests. "
            "It does not establish A2A conformance, Urusilla adoption, independent "
            "semantic reproduction, task utility, token saving, or energy saving."
        ),
        "verification": {
            "command": "python3 interop_lab/a2a_v1_language_probe.py --check",
            "expected": "PASS a2a-v1-language-probe-001",
        },
    }


def verify_fixture(
    message: Mapping[str, Any],
    manifest: Mapping[str, Any],
    source_bytes: bytes,
    probe: Mapping[str, Any],
) -> None:
    if set(message) != {"messageId", "role", "parts"}:
        raise A2ALanguageProbeError("A2A Message members differ")
    if message.get("role") != "ROLE_USER":
        raise A2ALanguageProbeError("A2A Message role differs")
    parts = message.get("parts")
    if type(parts) is not list or len(parts) != 1 or not isinstance(parts[0], dict):
        raise A2ALanguageProbeError("A2A Message requires exactly one Part")
    part = parts[0]
    if set(part) != {"data", "mediaType"}:
        raise A2ALanguageProbeError("A2A Part must contain only data and mediaType")
    if part.get("mediaType") != "application/json":
        raise A2ALanguageProbeError("A2A Part mediaType differs")
    present = [key for key in ("text", "raw", "url", "data") if key in part]
    if present != ["data"] or not isinstance(part["data"], dict):
        raise A2ALanguageProbeError("A2A Part oneof content differs")

    expected_message = build_message(source_bytes, probe)
    expected_manifest = build_manifest(source_bytes, probe, expected_message)
    if message != expected_message:
        raise A2ALanguageProbeError("A2A Message differs from deterministic build")
    if manifest != expected_manifest:
        raise A2ALanguageProbeError("A2A manifest differs from deterministic build")
    if part["data"]["probe"] != probe:
        raise A2ALanguageProbeError("unwrapped probe value differs")
    if part["data"]["probeCanonicalSha256"] != sha256_canonical(dict(probe)):
        raise A2ALanguageProbeError("unwrapped probe canonical digest differs")
    if part["data"]["probeSourceSha256"] != sha256_bytes(source_bytes):
        raise A2ALanguageProbeError("probe source-byte digest differs")


def render(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_artifacts() -> None:
    source_bytes, probe = load_probe()
    message = build_message(source_bytes, probe)
    manifest = build_manifest(source_bytes, probe, message)
    MESSAGE_PATH.write_text(render(message), encoding="utf-8")
    MANIFEST_PATH.write_text(render(manifest), encoding="utf-8")
    verify_fixture(message, manifest, source_bytes, probe)


def check_artifacts() -> None:
    source_bytes, probe = load_probe()
    message_value = strict_json_loads(MESSAGE_PATH.read_text(encoding="utf-8"))
    manifest_value = strict_json_loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(message_value, dict) or not isinstance(manifest_value, dict):
        raise A2ALanguageProbeError("fixture files must contain JSON objects")
    verify_fixture(message_value, manifest_value, source_bytes, probe)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_artifacts()
    else:
        check_artifacts()
    print("PASS a2a-v1-language-probe-001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
