#!/usr/bin/env python3
"""Experimental A2A v1 binding adapter for Urusilla.

Urusilla is the final project name. The protocol namespace and media type are
private experimental identifiers and must not be presented as an official A2A
extension or an IANA-registered media type.

The adapter deliberately separates the three A2A extension mechanisms:

* Agent Card declaration through ``AgentCapabilities.extensions``;
* request activation through the ``A2A-Extensions`` service parameter; and
* Message-level contribution and provenance through ``extensions`` and
  ``metadata`` on each A2A Message.

Transport authentication is supplied by the caller. A self-declared semantic
``sender`` and the checksum inside a wire frame are never authentication.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Mapping, Sequence
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from urusilla import (
    MAX_FRAME_BYTES,
    UrusillaError,
    decode_message,
    encode_message,
    normalize_message,
)
from source_manifest import LANGUAGE_VERSION


A2A_VERSION = "1.0"
EXTENSION_URI = "urn:urusilla:experimental:0.1"
MEDIA_TYPE = "application/x-urusilla"
WIRE_PROFILE = "urn:urusilla:wire:prototype:0.1"

EFFECTFUL_ACTS = frozenset({"COMMIT", "RESOLVE", "RETRACT"})
MESSAGE_ROLES = frozenset({"ROLE_USER", "ROLE_AGENT"})
SOURCE_ID_LENGTH = 32
_BASE64_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
)


class A2AAdapterError(ValueError):
    """The A2A wrapper is missing, inconsistent, or malformed."""


def file_sha256(path: str | Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_source_id(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != SOURCE_ID_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise A2AAdapterError(f"{field} must be 32 lowercase hexadecimal characters")
    return value


def _validate_extension_uri(value: Any, *, field: str) -> str:
    if type(value) is not str or not value or ":" not in value:
        raise A2AAdapterError(f"{field} must contain a non-empty extension URI")
    if any(character in value for character in (",", " ", "\t", "\r", "\n")):
        raise A2AAdapterError(f"{field} contains a character unsafe for A2A activation")
    return value


def _normalize_extensions(
    value: str | Sequence[str], *, field: str, header_value: bool
) -> tuple[str, ...]:
    if header_value:
        if type(value) is not str:
            raise A2AAdapterError(f"{field} must be a comma-separated service parameter")
        values: list[Any] = [item.strip() for item in value.split(",")]
    else:
        if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
            raise A2AAdapterError(f"{field} must be an array of extension URIs")
        values = list(value)

    if not values or any(item == "" for item in values):
        raise A2AAdapterError(f"{field} must contain at least one extension URI")
    normalized = tuple(
        _validate_extension_uri(item, field=f"{field}[{index}]")
        for index, item in enumerate(values)
    )
    if len(set(normalized)) != len(normalized):
        raise A2AAdapterError(f"{field} contains a duplicate extension URI")
    return normalized


def _normalize_activation(value: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize either an A2A-Extensions header value or a URI array."""

    if type(value) is str:
        return _normalize_extensions(
            value, field="A2A-Extensions", header_value=True
        )
    return _normalize_extensions(
        value, field="activated_extensions", header_value=False
    )


def _validate_role(value: Any, *, field: str = "role") -> str:
    if type(value) is not str or value not in MESSAGE_ROLES:
        choices = ", ".join(sorted(MESSAGE_ROLES))
        raise A2AAdapterError(f"{field} must be one of: {choices}")
    return value


def _validate_optional_identifier(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value:
        raise A2AAdapterError(f"{field} must be a non-empty string when present")
    return value


def _bind_authenticated_sender(
    message: Mapping[str, Any], authenticated_sender: str | None
) -> None:
    """Bind the semantic sender to a principal authenticated by the transport."""

    if authenticated_sender is not None and (
        type(authenticated_sender) is not str or not authenticated_sender
    ):
        raise A2AAdapterError("authenticated_sender must be a non-empty string")
    if authenticated_sender is None:
        if message["act"] in EFFECTFUL_ACTS:
            raise A2AAdapterError(
                f"{message['act']} requires a transport-authenticated sender"
            )
        return
    if message["sender"] != authenticated_sender:
        raise A2AAdapterError(
            "transport-authenticated sender does not match the semantic sender"
        )


def service_headers(
    *, additional_extensions: Sequence[str] = ()
) -> dict[str, str]:
    """Return A2A v1 HTTP headers or equivalent gRPC service metadata.

    Additional activated extensions are allowed. The private interlingua URI
    is always present exactly once, and callers must still authenticate the
    transport independently.
    """

    if isinstance(additional_extensions, (str, bytes, bytearray)) or not isinstance(
        additional_extensions, Sequence
    ):
        raise A2AAdapterError("additional_extensions must be an array of URIs")
    extras: tuple[str, ...]
    if additional_extensions:
        extras = _normalize_extensions(
            additional_extensions,
            field="additional_extensions",
            header_value=False,
        )
    else:
        extras = ()
    activated = [EXTENSION_URI]
    activated.extend(uri for uri in extras if uri != EXTENSION_URI)
    return {
        "A2A-Version": A2A_VERSION,
        "A2A-Extensions": ",".join(activated),
    }


def agent_extension(
    capsule_digest: str | None = None,
    *,
    source_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a conformant AgentCapabilities.extensions AgentExtension object.

    A complete source manifest may be published once in the standard ``params``
    object and pinned by the session. Hot Messages carry only its derived
    128-bit ``source_id`` in Message metadata.
    """

    params: dict[str, Any] = {
        "status": "experimental",
        "languageVersion": LANGUAGE_VERSION,
        "semanticKernelVersion": LANGUAGE_VERSION,
        "wireProfiles": [WIRE_PROFILE],
        "mediaTypes": [MEDIA_TYPE, "application/json"],
        "implicitVersionFallback": False,
        "sourceIdFormat": "32-lowercase-hex",
    }
    if capsule_digest is not None:
        if type(capsule_digest) is not str or not capsule_digest:
            raise A2AAdapterError("capsule_digest must be a non-empty string")
        params["capsuleDigest"] = capsule_digest
    if source_manifest is not None:
        if not isinstance(source_manifest, Mapping):
            raise A2AAdapterError("source_manifest must be an object")
        if source_manifest.get("languageVersion") != LANGUAGE_VERSION:
            raise A2AAdapterError(
                f"source_manifest languageVersion must be exactly {LANGUAGE_VERSION}"
            )
        params["sourceManifest"] = dict(source_manifest)
    return {
        "uri": EXTENSION_URI,
        "description": (
            "Experimental typed semantic interlingua with a deterministic "
            "machine-wire profile and auditable human translation"
        ),
        "required": False,
        "params": params,
    }


def pack_part(
    message: Mapping[str, Any],
    *,
    capsule_digest: str | None = None,
    diagnostic_metadata: bool = False,
) -> dict[str, Any]:
    """Encode a semantic message as an A2A v1 raw Part JSON representation."""

    canonical = normalize_message(message)
    frame = encode_message(canonical)
    part: dict[str, Any] = {
        "raw": base64.b64encode(frame).decode("ascii"),
        "mediaType": MEDIA_TYPE,
    }
    # Source attribution belongs to the containing Message, never this Part.
    # The optional fields below are cold-path diagnostics, not authentication.
    if diagnostic_metadata or capsule_digest is not None:
        extension_meta: dict[str, Any] = {
            "status": "experimental",
            "wireProfile": WIRE_PROFILE,
            "semanticSchema": canonical["schema"],
        }
        if capsule_digest is not None:
            extension_meta["capsuleDigest"] = capsule_digest
        part["metadata"] = {EXTENSION_URI: extension_meta}
    return part


def _preflight_base64_decoded_size(raw_value: str, *, maximum: int) -> int:
    """Validate strict Base64 shape and calculate decoded size without decoding."""

    if type(maximum) is not int or not 1 <= maximum <= MAX_FRAME_BYTES:
        raise A2AAdapterError(
            f"max_frame_bytes must be an integer from 1 to {MAX_FRAME_BYTES}"
        )
    length = len(raw_value)
    maximum_encoded = 4 * ((maximum + 2) // 3)
    if length == 0 or length > maximum_encoded:
        raise A2AAdapterError("raw Base64 exceeds the configured frame size limit")
    if length % 4:
        raise A2AAdapterError("raw contains invalid Base64 length")

    padding = 2 if raw_value.endswith("==") else 1 if raw_value.endswith("=") else 0
    content_end = length - padding
    for index, character in enumerate(raw_value):
        if index < content_end:
            if character not in _BASE64_ALPHABET:
                raise A2AAdapterError("raw contains invalid Base64")
        elif character != "=":
            raise A2AAdapterError("raw contains invalid Base64 padding")
    if "=" in raw_value[:content_end]:
        raise A2AAdapterError("raw contains invalid Base64 padding")

    decoded_size = (length // 4) * 3 - padding
    if decoded_size > maximum:
        raise A2AAdapterError("decoded raw frame exceeds the configured size limit")
    return decoded_size


def unpack_part(
    part: Mapping[str, Any],
    *,
    expected_capsule_digest: str | None = None,
    max_frame_bytes: int = MAX_FRAME_BYTES,
) -> dict[str, Any]:
    """Validate an A2A raw Part and decode its canonical semantic message."""

    if not isinstance(part, Mapping):
        raise A2AAdapterError("A2A Part must be an object")
    present = [name for name in ("text", "raw", "url", "data") if name in part]
    if present != ["raw"]:
        raise A2AAdapterError("A2A Part must contain exactly one content field: raw")
    if part.get("mediaType") != MEDIA_TYPE:
        raise A2AAdapterError(f"unexpected mediaType; expected {MEDIA_TYPE}")

    extension_meta: Mapping[str, Any] | None = None
    metadata = part.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise A2AAdapterError("Part metadata must be an object")
        candidate = metadata.get(EXTENSION_URI)
        if not isinstance(candidate, Mapping):
            raise A2AAdapterError("Part metadata uses no recognized extension marker")
        extension_meta = candidate
        if extension_meta.get("wireProfile") != WIRE_PROFILE:
            raise A2AAdapterError("unsupported wire profile")
    if expected_capsule_digest is not None:
        if type(expected_capsule_digest) is not str or not expected_capsule_digest:
            raise A2AAdapterError(
                "expected_capsule_digest must be a non-empty pinned digest"
            )
        if extension_meta is None or not hmac.compare_digest(
            str(extension_meta.get("capsuleDigest", "")), expected_capsule_digest
        ):
            raise A2AAdapterError("capsule digest mismatch")

    raw_value = part["raw"]
    if type(raw_value) is not str:
        raise A2AAdapterError("raw must be a Base64 string in the A2A JSON binding")
    predicted_size = _preflight_base64_decoded_size(
        raw_value, maximum=max_frame_bytes
    )
    try:
        frame = base64.b64decode(raw_value, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise A2AAdapterError("raw contains invalid Base64") from exc
    if len(frame) != predicted_size or len(frame) > max_frame_bytes:
        raise A2AAdapterError("decoded raw frame exceeds the configured size limit")

    try:
        message = decode_message(frame)
    except UrusillaError as exc:
        raise A2AAdapterError(f"invalid machine-wire frame: {exc}") from exc
    if (
        extension_meta is not None
        and extension_meta.get("semanticSchema") != message["schema"]
    ):
        raise A2AAdapterError("wrapper schema and decoded message schema differ")
    return message


def _validate_reference_task_ids(value: Any) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise A2AAdapterError("referenceTaskIds must be an array of strings")
    result = list(value)
    if not all(type(item) is str and item for item in result):
        raise A2AAdapterError("referenceTaskIds must contain non-empty strings")
    if len(set(result)) != len(result):
        raise A2AAdapterError("referenceTaskIds must be unique")
    return result


def wrap_a2a_message(
    message: Mapping[str, Any],
    *,
    source_id: str,
    role: str = "ROLE_USER",
    capsule_digest: str | None = None,
    authenticated_sender: str | None = None,
    context_id: str | None = None,
    task_id: str | None = None,
    reference_task_ids: Sequence[str] = (),
    additional_extensions: Sequence[str] = (),
) -> dict[str, Any]:
    """Build an A2A v1 Message after explicit binding-level opt-in.

    ``source_id`` is the caller's already-verified session pin. This function
    checks its format but does not derive or verify a source manifest.
    """

    canonical = normalize_message(message)
    pinned_source = _validate_source_id(source_id, field="source_id")
    selected_role = _validate_role(role)
    _bind_authenticated_sender(canonical, authenticated_sender)
    selected_context = _validate_optional_identifier(context_id, field="contextId")
    selected_task = _validate_optional_identifier(task_id, field="taskId")
    references = _validate_reference_task_ids(reference_task_ids)

    if isinstance(additional_extensions, (str, bytes, bytearray)) or not isinstance(
        additional_extensions, Sequence
    ):
        raise A2AAdapterError("additional_extensions must be an array of URIs")
    extras = (
        _normalize_extensions(
            additional_extensions,
            field="additional_extensions",
            header_value=False,
        )
        if additional_extensions
        else ()
    )
    extension_uris = [EXTENSION_URI]
    extension_uris.extend(uri for uri in extras if uri != EXTENSION_URI)

    wrapped: dict[str, Any] = {
        "role": selected_role,
        "parts": [pack_part(canonical, capsule_digest=capsule_digest)],
        "messageId": canonical["id"],
        "extensions": extension_uris,
        "metadata": {EXTENSION_URI: {"source_id": pinned_source}},
    }
    if selected_context is not None:
        wrapped["contextId"] = selected_context
    if selected_task is not None:
        wrapped["taskId"] = selected_task
    if references:
        wrapped["referenceTaskIds"] = references
    return wrapped


def unwrap_a2a_message(
    wrapper: Mapping[str, Any],
    *,
    expected_source_id: str,
    activated_extensions: str | Sequence[str],
    a2a_version: str,
    authenticated_sender: str | None = None,
    expected_role: str | None = None,
    expected_capsule_digest: str | None = None,
    expected_context_id: str | None = None,
    expected_task_id: str | None = None,
    max_frame_bytes: int = MAX_FRAME_BYTES,
) -> dict[str, Any]:
    """Validate a complete A2A Message boundary and return its semantic IR.

    The caller must pass service parameters extracted from HTTP headers, gRPC
    metadata, or an equivalent binding. Other extensions may be active, but
    every URI declared on the Message must also have been activated.
    """

    if not isinstance(wrapper, Mapping):
        raise A2AAdapterError("A2A Message must be an object")
    if type(a2a_version) is not str or a2a_version != A2A_VERSION:
        raise A2AAdapterError(f"unsupported A2A version; expected {A2A_VERSION}")
    activated = _normalize_activation(activated_extensions)
    if EXTENSION_URI not in activated:
        raise A2AAdapterError(
            "A2A-Extensions did not activate the experimental extension"
        )

    message_extensions = _normalize_extensions(
        wrapper.get("extensions"), field="Message.extensions", header_value=False
    )
    if EXTENSION_URI not in message_extensions:
        raise A2AAdapterError("Message.extensions omits the experimental extension")
    unactivated = [uri for uri in message_extensions if uri not in activated]
    if unactivated:
        raise A2AAdapterError(
            "Message declares an extension that was not activated: "
            + ", ".join(unactivated)
        )

    role = _validate_role(wrapper.get("role"))
    if expected_role is not None and role != _validate_role(
        expected_role, field="expected_role"
    ):
        raise A2AAdapterError("A2A Message role does not match the expected role")

    pinned_source = _validate_source_id(
        expected_source_id, field="expected_source_id"
    )
    metadata = wrapper.get("metadata")
    if not isinstance(metadata, Mapping):
        raise A2AAdapterError("A2A Message metadata must be an object")
    extension_meta = metadata.get(EXTENSION_URI)
    if not isinstance(extension_meta, Mapping):
        raise A2AAdapterError("A2A Message metadata omits extension provenance")
    declared_source = _validate_source_id(
        extension_meta.get("source_id"), field="Message metadata source_id"
    )
    if not hmac.compare_digest(declared_source, pinned_source):
        raise A2AAdapterError("Message source_id does not match the pinned source_id")

    context_id = _validate_optional_identifier(
        wrapper.get("contextId"), field="contextId"
    )
    task_id = _validate_optional_identifier(wrapper.get("taskId"), field="taskId")
    if expected_context_id is not None:
        expected_context = _validate_optional_identifier(
            expected_context_id, field="expected_context_id"
        )
        if context_id != expected_context:
            raise A2AAdapterError("A2A Message contextId does not match its session pin")
    if expected_task_id is not None:
        expected_task = _validate_optional_identifier(
            expected_task_id, field="expected_task_id"
        )
        if task_id != expected_task:
            raise A2AAdapterError("A2A Message taskId does not match its session pin")
    if "referenceTaskIds" in wrapper:
        _validate_reference_task_ids(wrapper["referenceTaskIds"])

    parts = wrapper.get("parts")
    if not isinstance(parts, list) or len(parts) != 1:
        raise A2AAdapterError(
            "experimental Message binding requires exactly one semantic raw Part"
        )
    message = unpack_part(
        parts[0],
        expected_capsule_digest=expected_capsule_digest,
        max_frame_bytes=max_frame_bytes,
    )
    message_id = wrapper.get("messageId")
    if type(message_id) is not str or not message_id:
        raise A2AAdapterError("A2A Message messageId must be a non-empty string")
    if message_id != message["id"]:
        raise A2AAdapterError("A2A messageId and semantic message id differ")
    _bind_authenticated_sender(message, authenticated_sender)
    return message


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise A2AAdapterError("JSON input must be an object")
    return value


def _write_json(path: str, value: Mapping[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    pack = sub.add_parser("pack", help="wrap semantic JSON as an A2A Message")
    pack.add_argument("input")
    pack.add_argument("output")
    pack.add_argument("--source-id", required=True)
    pack.add_argument("--capsule")
    pack.add_argument("--role", choices=sorted(MESSAGE_ROLES), default="ROLE_USER")
    pack.add_argument("--authenticated-sender")
    pack.add_argument("--extension", action="append", default=[])

    unpack = sub.add_parser("unpack", help="validate and decode an A2A Message")
    unpack.add_argument("input")
    unpack.add_argument("output")
    unpack.add_argument("--source-id", required=True, help="pinned expected source_id")
    unpack.add_argument("--capsule")
    unpack.add_argument(
        "--activated-extension",
        action="append",
        required=True,
        help="repeat for every URI activated by the A2A-Extensions service parameter",
    )
    unpack.add_argument("--a2a-version", default=A2A_VERSION)
    unpack.add_argument("--authenticated-sender")
    unpack.add_argument("--expected-role", choices=sorted(MESSAGE_ROLES))
    unpack.add_argument("--max-frame-bytes", type=int, default=MAX_FRAME_BYTES)

    headers = sub.add_parser(
        "headers", help="write A2A-Version and A2A-Extensions service headers"
    )
    headers.add_argument("output")
    headers.add_argument("--extension", action="append", default=[])
    args = parser.parse_args()

    if args.command == "headers":
        _write_json(
            args.output,
            service_headers(additional_extensions=args.extension),
        )
        return 0

    capsule_digest = file_sha256(args.capsule) if args.capsule else None
    if args.command == "pack":
        result = wrap_a2a_message(
            _load_json(args.input),
            source_id=args.source_id,
            role=args.role,
            capsule_digest=capsule_digest,
            authenticated_sender=args.authenticated_sender,
            additional_extensions=args.extension,
        )
    else:
        result = unwrap_a2a_message(
            _load_json(args.input),
            expected_source_id=args.source_id,
            activated_extensions=args.activated_extension,
            a2a_version=args.a2a_version,
            authenticated_sender=args.authenticated_sender,
            expected_role=args.expected_role,
            expected_capsule_digest=capsule_digest,
            max_frame_bytes=args.max_frame_bytes,
        )
    _write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
