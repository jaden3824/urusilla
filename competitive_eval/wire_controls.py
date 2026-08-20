"""Wire-only controls over the exact same canonical typed QA record.

These controls never create a second receiver-model sample. They decode to the
same canonical JSON receiver text and report only transport/conversion facts.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import sys
from typing import Any, Callable
import uuid

from .canonical import canonical_bytes, canonical_json, sha256_bytes
from .config import PROJECT_ROOT, WIRE_CONTROLS
from .errors import IntegrityError, ParseFailure
from .records import QARecord
from .representations import SelectionContext, unwrap_record, wrap_record


_MAGIC = b"CEW1"
_CODEC_IDS = {
    "deterministic_cbor": 1,
    "messagepack_sorted_map": 2,
    "typed_protobuf": 3,
}
_CHECKSUM_SIZE = 16
_DOMAIN = b"competitive-eval-wire-integrity-v1\x00"


@dataclass(frozen=True)
class WireControlResult:
    codec: str
    canonical_record_sha256: str
    receiver_text: str
    raw_codec_bytes: int
    integrity_envelope_bytes: int
    base64_bytes: int
    full_json_envelope_bytes: int
    cold_artifact_bytes: int
    exact_round_trip: bool
    integrity_protected: bool
    receiver_call_reused_from: str = "canonical_minified_json"

    def to_object(self) -> dict[str, Any]:
        return {
            "codec": self.codec,
            "canonical_record_sha256": self.canonical_record_sha256,
            "receiver_text_sha256": sha256_bytes(self.receiver_text.encode("utf-8")),
            "raw_codec_bytes": self.raw_codec_bytes,
            "integrity_envelope_bytes": self.integrity_envelope_bytes,
            "base64_bytes": self.base64_bytes,
            "full_json_envelope_bytes": self.full_json_envelope_bytes,
            "cold_artifact_bytes": self.cold_artifact_bytes,
            "exact_round_trip": self.exact_round_trip,
            "integrity_protected": self.integrity_protected,
            "receiver_call_reused_from": self.receiver_call_reused_from,
            "additional_model_calls": 0,
            "model_token_claim_eligible": False,
        }


def _root_modules() -> tuple[Any, Any]:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import urusilla_strong_codec_baselines as strong
    import urusilla_wire_v02 as wire

    return strong, wire


def _protect(codec: str, payload: bytes) -> bytes:
    codec_id = _CODEC_IDS[codec]
    header = _MAGIC + bytes([codec_id]) + len(payload).to_bytes(8, "big")
    checksum = hashlib.sha256(_DOMAIN + header + payload).digest()[:_CHECKSUM_SIZE]
    return header + payload + checksum


def _unprotect(codec: str, frame: bytes) -> bytes:
    if type(frame) is not bytes or len(frame) < len(_MAGIC) + 1 + 8 + _CHECKSUM_SIZE:
        raise ParseFailure("malformed", "wire-control frame is truncated")
    codec_id = _CODEC_IDS[codec]
    if frame[:4] != _MAGIC or frame[4] != codec_id:
        raise ParseFailure("unknown_profile", "wire-control codec identity mismatch")
    length = int.from_bytes(frame[5:13], "big")
    if length > 64 * 1024 * 1024 or len(frame) != 13 + length + _CHECKSUM_SIZE:
        raise ParseFailure("resource_limit", "wire-control payload length is invalid")
    payload = frame[13 : 13 + length]
    supplied = frame[-_CHECKSUM_SIZE:]
    expected = hashlib.sha256(_DOMAIN + frame[:13] + payload).digest()[:_CHECKSUM_SIZE]
    if not hmac.compare_digest(supplied, expected):
        raise ParseFailure("integrity_failure", "wire-control checksum mismatch")
    return payload


def _codec(codec: str) -> tuple[Callable[[dict[str, Any]], bytes], Callable[[bytes], dict[str, Any]], int, bool]:
    strong, wire = _root_modules()
    if codec == "deterministic_cbor":
        strong.require_dependencies()
        return strong.cbor_encode, strong.cbor_decode, 0, False
    if codec == "messagepack_sorted_map":
        strong.require_dependencies()
        return strong.msgpack_encode, strong.msgpack_decode, 0, False
    if codec == "typed_protobuf":
        strong.require_dependencies()
        runtime = strong.load_proto_runtime()
        return (
            lambda message: _protobuf_encode_preserving_empty(strong, runtime, message),
            strong.protobuf_decode,
            len(runtime.descriptor_set),
            False,
        )
    if codec == "project_wire_v02":
        capsule = wire.encode_capsule(wire.DEFAULT_PROFILE)
        return wire.encode_message, wire.decode_message, len(capsule), True
    raise ParseFailure("unknown_profile", f"unknown wire control: {codec}")


def _fill_proto_value_preserving_empty(target: Any, value: Any) -> None:
    """Populate the frozen SemanticValue schema without losing empty containers.

    The root baseline encoder predates the QA bridge and does not mark proto3
    presence for an empty list or map.  The descriptor itself supports those
    values, so this harness-local encoder uses SetInParent rather than changing
    either the frozen baseline source or the canonical message.
    """

    if value is None:
        target.null_value = 0
    elif type(value) is bool:
        target.bool_value = value
    elif type(value) is int:
        if value < 0:
            target.signed_integer = value
        else:
            target.unsigned_integer = value
    elif type(value) is float:
        target.float64_value = value
    elif type(value) is str:
        target.string_value = value
    elif type(value) is bytes:
        target.bytes_value = value
    elif isinstance(value, (list, tuple)):
        target.list_value.SetInParent()
        for item in value:
            _fill_proto_value_preserving_empty(target.list_value.items.add(), item)
    elif isinstance(value, dict):
        target.map_value.SetInParent()
        for key in sorted(value, key=lambda item: item.encode("utf-8")):
            entry = target.map_value.entries.add()
            entry.key = key
            _fill_proto_value_preserving_empty(entry.value, value[key])
    else:
        raise TypeError(f"unsupported semantic value: {type(value).__name__}")


def _protobuf_encode_preserving_empty(strong: Any, runtime: Any, message: dict[str, Any]) -> bytes:
    canonical = strong.normalize_message(message)
    encoded = runtime.module.AgentMessage()
    encoded.id = uuid.UUID(canonical["id"]).bytes
    encoded.session = uuid.UUID(canonical["session"]).bytes
    encoded.sender = canonical["sender"]
    encoded.recipients.extend(canonical["recipients"])
    encoded.act = strong.ACT_TO_PROTO[canonical["act"]]
    if canonical["reply_to"] is not None:
        encoded.reply_to = uuid.UUID(canonical["reply_to"]).bytes
    encoded.schema = canonical["schema"]
    encoded.logical_clock = canonical["logical_clock"]
    encoded.expires_ms = canonical["expires_ms"]
    if canonical["confidence_ppm"] is not None:
        encoded.confidence_ppm = canonical["confidence_ppm"]
    encoded.expected.extend(strong.ACT_TO_PROTO[item] for item in canonical["expected"])
    _fill_proto_value_preserving_empty(encoded.body, canonical["body"])
    _fill_proto_value_preserving_empty(encoded.meta, canonical["meta"])
    return encoded.SerializeToString(deterministic=True)


def encode_wire_control(
    codec: str, record: QARecord, context: SelectionContext
) -> tuple[WireControlResult, bytes]:
    if codec not in WIRE_CONTROLS:
        raise ParseFailure("unknown_profile", f"unknown wire control: {codec}")
    encoder, decoder, cold_bytes, native_integrity = _codec(codec)
    message = wrap_record(record, context)
    strong, _ = _root_modules()
    expected_message = strong.normalize_message(message)
    payload = encoder(message)
    frame = payload if native_integrity else _protect(codec, payload)
    recovered_message = decoder(frame if native_integrity else _unprotect(codec, frame))
    if recovered_message != expected_message:
        raise IntegrityError(f"{codec} changed the complete bridge message")
    recovered_record = unwrap_record(recovered_message)
    if recovered_record != record:
        raise IntegrityError(f"{codec} changed the canonical QA record")
    encoded = base64.b64encode(frame).decode("ascii")
    envelope = canonical_json(
        {
            "codec": codec,
            "payload_base64": encoded,
            "record_sha256": record.sha256,
        }
    )
    result = WireControlResult(
        codec=codec,
        canonical_record_sha256=record.sha256,
        receiver_text=record.canonical_text,
        raw_codec_bytes=len(payload),
        integrity_envelope_bytes=len(frame),
        base64_bytes=len(encoded.encode("ascii")),
        full_json_envelope_bytes=len(envelope.encode("utf-8")),
        cold_artifact_bytes=cold_bytes,
        exact_round_trip=True,
        integrity_protected=True,
    )
    return result, frame


def decode_wire_control(
    codec: str, frame: bytes, expected_record_sha256: str
) -> QARecord:
    _, decoder, _, native_integrity = _codec(codec)
    message = decoder(frame if native_integrity else _unprotect(codec, frame))
    record = unwrap_record(message)
    if record.sha256 != expected_record_sha256:
        raise IntegrityError("wire-control record digest mismatch")
    return record


def corrupt_frame(frame: bytes) -> bytes:
    if not frame:
        raise ValueError("cannot corrupt an empty frame")
    position = len(frame) // 2
    result = bytearray(frame)
    result[position] ^= 0x01
    return bytes(result)
