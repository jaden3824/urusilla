#!/usr/bin/env python3
"""Reproducible full-envelope A2A v1 JSON size benchmark.

This benchmark answers a deliberately narrow question: how many bytes are used
when the existing deterministic 280-message UrusillaIR corpus is placed in complete
A2A v1 SendMessage requests under two JSON bindings?

The measured profiles are a structured DataPart comparison baseline, the
current hardened UrusillaWire v0.1 RawPart adapter, and a benchmark-only experimental
UrusillaWire v0.2 warm RawPart wrapper.  It measures exact deterministic transport
round-trip and byte counts.  It does not measure task success, model tokens,
semantic construction, network latency, authentication, or production A2A
interoperability.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

from urusilla_a2a_adapter import (
    A2A_VERSION,
    EXTENSION_URI,
    unwrap_a2a_message,
    wrap_a2a_message,
)
from urusilla_benchmark import (
    CORPUS_VERSION,
    DEFAULT_MESSAGES,
    build_corpus,
    corpus_digest,
)
from urusilla_deterministic_gzip import compress as deterministic_gzip_compress
from urusilla import MAX_FRAME_BYTES, normalize_message
import urusilla_wire_v02 as wire_v02
from source_manifest import derive_source_id, validate_manifest


# This deterministic unsigned manifest uses immutable-shaped GitHub URLs and the
# exact local Grammar Capsule digest. The commit values and conformance digest
# are synthetic test vectors, the URLs are not fetched, and the manifest is not
# a production identity, signature, credential, or provenance claim.
SOURCE_MANIFEST = {
    "languageSpecUri": (
        "https://github.com/jaden3824/urusilla/blob/"
        "0123456789abcdef0123456789abcdef01234567/urusilla_v0_1_spec.md"
    ),
    "languageVersion": "0.1.0",
    "capsuleSha256": (
        "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
    ),
    "implementationOrigin": (
        "https://github.com/example/urusilla-bridge/tree/"
        "89abcdef0123456789abcdef0123456789abcdef/src"
    ),
    "conformanceReportUrl": (
        "https://github.com/example/urusilla-bridge/blob/"
        "89abcdef0123456789abcdef0123456789abcdef/conformance_report.json"
    ),
    "conformanceReportSha256": "b" * 64,
}
SOURCE_VALIDATION = validate_manifest(SOURCE_MANIFEST)
SOURCE_ID = derive_source_id(SOURCE_MANIFEST)

HTTP_HOST = "agent.example.test"
HTTP_JSON_PATH = "/message:send"
JSON_RPC_PATH = "/rpc"
GZIP_LEVEL = 6

STRUCTURED_KEY = "structured-data"
V01_KEY = "urusilla-wire-v0.1"
V02_KEY = "urusilla-wire-v0.2-warm-experimental"

V02_EXTENSION_URI = "urn:urusilla:experimental:0.2-envelope-benchmark"
V02_MEDIA_TYPE = (
    "application/x-urusilla;profile=experimental-urusilla-wire-v0.2"
)
V02_WIRE_PROFILE = "urn:urusilla:wire:prototype:0.2"

REST_KEY = "http-json"
JSON_RPC_KEY = "json-rpc"

JsonMap = dict[str, Any]
WrapFunction = Callable[[Mapping[str, Any]], JsonMap]
UnwrapFunction = Callable[[Mapping[str, Any], str, str, str], JsonMap]


class EnvelopeError(ValueError):
    """A benchmark request or wrapper is malformed or inconsistent."""


@dataclass(frozen=True)
class Representation:
    key: str
    label: str
    extension_uri: str
    wrap: WrapFunction
    unwrap: UnwrapFunction
    note: str


@dataclass(frozen=True)
class Binding:
    key: str
    label: str
    path: str
    content_type: str


@dataclass(frozen=True)
class ParsedHttpRequest:
    body: bytes
    a2a_version: str
    activated_extensions: str


@dataclass(frozen=True)
class EnvelopeResult:
    representation_key: str
    representation_label: str
    binding_key: str
    binding_label: str
    message_count: int
    body_raw_sizes: tuple[int, ...]
    body_gzip_sizes: tuple[int, ...]
    request_raw_sizes: tuple[int, ...]
    request_gzip_sizes: tuple[int, ...]
    exact_raw: int
    exact_gzip: int
    deterministic_raw: int
    deterministic_gzip: int
    raw_request_digest: str
    gzip_request_digest: str


@dataclass(frozen=True)
class BenchmarkSummary:
    message_count: int
    corpus_digest: str
    results: tuple[EnvelopeResult, ...]
    request_suite_digest: str
    capsule_raw_bytes: int
    capsule_gzip_bytes: int
    capsule_digest: str
    dictionary_id: str
    header_samples: Mapping[str, str]


HTTP_JSON_BINDING = Binding(
    REST_KEY,
    "HTTP+JSON SendMessageRequest",
    HTTP_JSON_PATH,
    "application/a2a+json",
)
JSON_RPC_BINDING = Binding(
    JSON_RPC_KEY,
    "JSON-RPC SendMessage",
    JSON_RPC_PATH,
    "application/json",
)
BINDINGS = (HTTP_JSON_BINDING, JSON_RPC_BINDING)


def json_bytes(value: Any) -> bytes:
    """Serialize deterministic minified UTF-8 JSON for this benchmark."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_object(data: bytes, *, field: str) -> JsonMap:
    try:
        value = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvelopeError(f"{field} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EnvelopeError(f"{field} must be a JSON object")
    return value


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], *, field: str) -> None:
    if set(value) != keys:
        raise EnvelopeError(f"{field} does not match the benchmark shape")


def _check_source_binding(message: Mapping[str, Any], authenticated_sender: str) -> None:
    if type(authenticated_sender) is not str or not authenticated_sender:
        raise EnvelopeError("authenticated sender must be a non-empty string")
    if message["sender"] != authenticated_sender:
        raise EnvelopeError("authenticated sender and semantic sender differ")


def wrap_structured_data(message: Mapping[str, Any]) -> JsonMap:
    """Build the structured UrusillaIR DataPart comparison baseline.

    This preserves the current extension and source-pin footprint for a fairer
    envelope comparison, but it is not an additional path implemented by the
    current hardened RawPart adapter.
    """

    canonical = normalize_message(message)
    return {
        "role": "ROLE_USER",
        "parts": [{"data": canonical, "mediaType": "application/json"}],
        "messageId": canonical["id"],
        "extensions": [EXTENSION_URI],
        "metadata": {EXTENSION_URI: {"source_id": SOURCE_ID}},
    }


def unwrap_structured_data(
    wrapper: Mapping[str, Any],
    a2a_version: str,
    activated_extensions: str,
    authenticated_sender: str,
) -> JsonMap:
    """Strictly decode the benchmark-only structured DataPart shape."""

    if not isinstance(wrapper, Mapping):
        raise EnvelopeError("A2A Message must be an object")
    if a2a_version != A2A_VERSION:
        raise EnvelopeError("unexpected A2A version")
    if activated_extensions != EXTENSION_URI:
        raise EnvelopeError("structured baseline extension is not activated")
    _require_exact_keys(
        wrapper,
        {"role", "parts", "messageId", "extensions", "metadata"},
        field="structured Message",
    )
    if wrapper["role"] != "ROLE_USER" or wrapper["extensions"] != [EXTENSION_URI]:
        raise EnvelopeError("structured Message role or extensions differ")
    if wrapper["metadata"] != {EXTENSION_URI: {"source_id": SOURCE_ID}}:
        raise EnvelopeError("structured Message source metadata differs")
    parts = wrapper["parts"]
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], Mapping):
        raise EnvelopeError("structured Message requires one DataPart")
    part = parts[0]
    _require_exact_keys(part, {"data", "mediaType"}, field="structured DataPart")
    if part["mediaType"] != "application/json" or not isinstance(part["data"], Mapping):
        raise EnvelopeError("structured DataPart media type or data differs")
    message = normalize_message(part["data"])
    if wrapper["messageId"] != message["id"]:
        raise EnvelopeError("A2A messageId and semantic message id differ")
    _check_source_binding(message, authenticated_sender)
    return message


def wrap_v01(message: Mapping[str, Any]) -> JsonMap:
    """Use the current hardened A2A adapter for a v0.1 RawPart."""

    canonical = normalize_message(message)
    return wrap_a2a_message(
        canonical,
        source_id=SOURCE_ID,
        authenticated_sender=canonical["sender"],
    )


def unwrap_v01(
    wrapper: Mapping[str, Any],
    a2a_version: str,
    activated_extensions: str,
    authenticated_sender: str,
) -> JsonMap:
    """Use the current hardened adapter to validate the complete Message boundary."""

    return unwrap_a2a_message(
        wrapper,
        expected_source_id=SOURCE_ID,
        activated_extensions=activated_extensions,
        a2a_version=a2a_version,
        authenticated_sender=authenticated_sender,
        expected_role="ROLE_USER",
    )


def _v02_metadata() -> JsonMap:
    return {
        "status": "experimental",
        "source_id": SOURCE_ID,
        "wireProfile": V02_WIRE_PROFILE,
        "profileId": wire_v02.DEFAULT_PROFILE.profile_id,
        "dictionaryId": wire_v02.DEFAULT_PROFILE.dictionary_id_hex,
    }


def wrap_v02_experimental(message: Mapping[str, Any]) -> JsonMap:
    """Build a local experimental A2A wrapper for one warm v0.2 frame.

    This is intentionally separate from ``urusilla_a2a_adapter``.  Its existence in
    a benchmark does not add v0.2 support to that hardened v0.1 adapter.
    """

    canonical = normalize_message(message)
    frame = wire_v02.encode_message(canonical)
    return {
        "role": "ROLE_USER",
        "parts": [
            {
                "raw": base64.b64encode(frame).decode("ascii"),
                "mediaType": V02_MEDIA_TYPE,
            }
        ],
        "messageId": canonical["id"],
        "extensions": [V02_EXTENSION_URI],
        "metadata": {V02_EXTENSION_URI: _v02_metadata()},
    }


def unwrap_v02_experimental(
    wrapper: Mapping[str, Any],
    a2a_version: str,
    activated_extensions: str,
    authenticated_sender: str,
) -> JsonMap:
    """Strictly decode the benchmark-only experimental v0.2 wrapper."""

    if not isinstance(wrapper, Mapping):
        raise EnvelopeError("A2A Message must be an object")
    if a2a_version != A2A_VERSION:
        raise EnvelopeError("unexpected A2A version")
    if activated_extensions != V02_EXTENSION_URI:
        raise EnvelopeError("experimental v0.2 extension is not activated")
    _require_exact_keys(
        wrapper,
        {"role", "parts", "messageId", "extensions", "metadata"},
        field="experimental v0.2 Message",
    )
    if wrapper["role"] != "ROLE_USER" or wrapper["extensions"] != [V02_EXTENSION_URI]:
        raise EnvelopeError("experimental v0.2 Message role or extensions differ")
    if wrapper["metadata"] != {V02_EXTENSION_URI: _v02_metadata()}:
        raise EnvelopeError("experimental v0.2 metadata differs")
    parts = wrapper["parts"]
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], Mapping):
        raise EnvelopeError("experimental v0.2 Message requires one RawPart")
    part = parts[0]
    _require_exact_keys(part, {"raw", "mediaType"}, field="experimental v0.2 RawPart")
    if part["mediaType"] != V02_MEDIA_TYPE or type(part["raw"]) is not str:
        raise EnvelopeError("experimental v0.2 RawPart media type or raw value differs")
    maximum_base64 = 4 * ((MAX_FRAME_BYTES + 2) // 3)
    if not part["raw"] or len(part["raw"]) > maximum_base64:
        raise EnvelopeError("experimental v0.2 Base64 exceeds the frame limit")
    try:
        frame = base64.b64decode(part["raw"], validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise EnvelopeError("experimental v0.2 raw value is not strict Base64") from exc
    if len(frame) > MAX_FRAME_BYTES:
        raise EnvelopeError("experimental v0.2 frame exceeds the frame limit")
    message = wire_v02.decode_message(frame)
    if wrapper["messageId"] != message["id"]:
        raise EnvelopeError("A2A messageId and semantic message id differ")
    _check_source_binding(message, authenticated_sender)
    return message


REPRESENTATIONS = (
    Representation(
        STRUCTURED_KEY,
        "Structured UrusillaIR DataPart baseline",
        EXTENSION_URI,
        wrap_structured_data,
        unwrap_structured_data,
        "benchmark comparison path; not implemented by the hardened RawPart adapter",
    ),
    Representation(
        V01_KEY,
        "UrusillaWire v0.1 Base64 RawPart",
        EXTENSION_URI,
        wrap_v01,
        unwrap_v01,
        "current hardened adapter with Message extensions and source_id metadata",
    ),
    Representation(
        V02_KEY,
        "UrusillaWire v0.2 warm Base64 RawPart",
        V02_EXTENSION_URI,
        wrap_v02_experimental,
        unwrap_v02_experimental,
        "explicitly experimental benchmark-only wrapper and in-domain warm profile",
    ),
)


def build_binding_body(binding: Binding, wrapper: Mapping[str, Any], index: int) -> bytes:
    """Build one complete JSON request body for the selected A2A v1 binding."""

    send_request: JsonMap = {"message": dict(wrapper)}
    if binding.key == REST_KEY:
        value: JsonMap = send_request
    elif binding.key == JSON_RPC_KEY:
        value = {
            "jsonrpc": "2.0",
            "id": index + 1,
            "method": "SendMessage",
            "params": send_request,
        }
    else:
        raise EnvelopeError(f"unknown binding: {binding.key}")
    return json_bytes(value)


def decode_binding_body(binding: Binding, body: bytes, index: int) -> JsonMap:
    """Validate a binding body and return its contained A2A Message object."""

    value = _json_object(body, field=f"{binding.label} body")
    if binding.key == REST_KEY:
        _require_exact_keys(value, {"message"}, field="SendMessageRequest")
        send_request = value
    elif binding.key == JSON_RPC_KEY:
        _require_exact_keys(
            value,
            {"jsonrpc", "id", "method", "params"},
            field="JSON-RPC request",
        )
        if (
            value["jsonrpc"] != "2.0"
            or value["id"] != index + 1
            or value["method"] != "SendMessage"
            or not isinstance(value["params"], Mapping)
        ):
            raise EnvelopeError("JSON-RPC request fields differ")
        send_request = value["params"]
        _require_exact_keys(send_request, {"message"}, field="SendMessageRequest params")
    else:
        raise EnvelopeError(f"unknown binding: {binding.key}")
    message = send_request["message"]
    if not isinstance(message, dict):
        raise EnvelopeError("SendMessageRequest.message must be an object")
    return message


def http_header_bytes(
    binding: Binding,
    extension_uri: str,
    content_length: int,
    *,
    compressed: bool,
) -> bytes:
    """Build the deterministic representative HTTP/1.1 request head."""

    if type(content_length) is not int or content_length < 0:
        raise EnvelopeError("Content-Length must be a non-negative integer")
    lines = [
        f"POST {binding.path} HTTP/1.1",
        f"Host: {HTTP_HOST}",
        f"A2A-Version: {A2A_VERSION}",
        f"A2A-Extensions: {extension_uri}",
        f"Content-Type: {binding.content_type}",
    ]
    if compressed:
        lines.append("Content-Encoding: gzip")
    lines.append(f"Content-Length: {content_length}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def build_http_request(
    binding: Binding,
    extension_uri: str,
    body: bytes,
    *,
    compressed: bool,
) -> bytes:
    """Build one complete measured HTTP/1.1 request, excluding lower layers."""

    payload = (
        deterministic_gzip_compress(body, compresslevel=GZIP_LEVEL)
        if compressed
        else body
    )
    return http_header_bytes(
        binding,
        extension_uri,
        len(payload),
        compressed=compressed,
    ) + payload


def parse_http_request(
    request: bytes,
    binding: Binding,
    extension_uri: str,
    *,
    compressed: bool,
) -> ParsedHttpRequest:
    """Validate and extract a request built by this benchmark harness."""

    if not isinstance(request, bytes):
        raise EnvelopeError("HTTP request must be bytes")
    separator = b"\r\n\r\n"
    if request.count(separator) != 1:
        raise EnvelopeError("HTTP request must contain one header terminator")
    head, payload = request.split(separator, 1)
    try:
        lines = head.decode("ascii", errors="strict").split("\r\n")
    except UnicodeDecodeError as exc:
        raise EnvelopeError("HTTP request head must be ASCII") from exc
    if not lines or lines[0] != f"POST {binding.path} HTTP/1.1":
        raise EnvelopeError("HTTP request line differs")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ": " not in line:
            raise EnvelopeError("HTTP header line is malformed")
        name, value = line.split(": ", 1)
        lowered = name.lower()
        if lowered in headers:
            raise EnvelopeError("HTTP request contains a duplicate header")
        headers[lowered] = value
    expected_names = {
        "host",
        "a2a-version",
        "a2a-extensions",
        "content-type",
        "content-length",
    }
    if compressed:
        expected_names.add("content-encoding")
    if set(headers) != expected_names:
        raise EnvelopeError("HTTP header set differs from the benchmark shape")
    if (
        headers["host"] != HTTP_HOST
        or headers["a2a-version"] != A2A_VERSION
        or headers["a2a-extensions"] != extension_uri
        or headers["content-type"] != binding.content_type
    ):
        raise EnvelopeError("HTTP service or content headers differ")
    if compressed and headers["content-encoding"] != "gzip":
        raise EnvelopeError("HTTP Content-Encoding differs")
    try:
        declared_length = int(headers["content-length"])
    except ValueError as exc:
        raise EnvelopeError("HTTP Content-Length is not an integer") from exc
    if str(declared_length) != headers["content-length"] or declared_length != len(payload):
        raise EnvelopeError("HTTP Content-Length differs from the payload length")
    if compressed:
        try:
            body = gzip.decompress(payload)
        except (gzip.BadGzipFile, EOFError, OSError) as exc:
            raise EnvelopeError("HTTP gzip body is invalid") from exc
    else:
        body = payload
    return ParsedHttpRequest(
        body=body,
        a2a_version=headers["a2a-version"],
        activated_extensions=headers["a2a-extensions"],
    )


def _sequence_digest(items: Sequence[bytes]) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(len(item).to_bytes(8, "big"))
        digest.update(item)
    return digest.hexdigest()


def _suite_digest(rows: Sequence[tuple[str, str, Sequence[bytes], Sequence[bytes]]]) -> str:
    digest = hashlib.sha256()
    digest.update(b"urusilla-a2a-envelope-benchmark-v1\x00")
    for representation_key, binding_key, raw_requests, gzip_requests in rows:
        for value in (representation_key, binding_key):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(2, "big"))
            digest.update(encoded)
        for request in (*raw_requests, *gzip_requests):
            digest.update(len(request).to_bytes(8, "big"))
            digest.update(request)
    return digest.hexdigest()


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    if not values:
        raise EnvelopeError("percentile requires at least one value")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def run_benchmark(messages: int = DEFAULT_MESSAGES) -> BenchmarkSummary:
    """Measure all six profile/binding combinations deterministically."""

    if messages < 100:
        raise ValueError("benchmark corpus must contain at least 100 messages")
    corpus = build_corpus(messages)
    results: list[EnvelopeResult] = []
    digest_rows: list[tuple[str, str, Sequence[bytes], Sequence[bytes]]] = []
    header_samples: dict[str, str] = {}

    for representation in REPRESENTATIONS:
        for binding in BINDINGS:
            body_raw_sizes: list[int] = []
            body_gzip_sizes: list[int] = []
            request_raw_sizes: list[int] = []
            request_gzip_sizes: list[int] = []
            raw_requests: list[bytes] = []
            gzip_requests: list[bytes] = []
            exact_raw = 0
            exact_gzip = 0
            deterministic_raw = 0
            deterministic_gzip = 0

            for index, source in enumerate(corpus):
                wrapper = representation.wrap(source)
                body = build_binding_body(binding, wrapper, index)
                compressed_body = deterministic_gzip_compress(
                    body, compresslevel=GZIP_LEVEL
                )
                raw_request = build_http_request(
                    binding,
                    representation.extension_uri,
                    body,
                    compressed=False,
                )
                gzip_request = build_http_request(
                    binding,
                    representation.extension_uri,
                    body,
                    compressed=True,
                )

                body_raw_sizes.append(len(body))
                body_gzip_sizes.append(len(compressed_body))
                request_raw_sizes.append(len(raw_request))
                request_gzip_sizes.append(len(gzip_request))
                raw_requests.append(raw_request)
                gzip_requests.append(gzip_request)

                parsed_raw = parse_http_request(
                    raw_request,
                    binding,
                    representation.extension_uri,
                    compressed=False,
                )
                parsed_gzip = parse_http_request(
                    gzip_request,
                    binding,
                    representation.extension_uri,
                    compressed=True,
                )
                raw_wrapper = decode_binding_body(binding, parsed_raw.body, index)
                gzip_wrapper = decode_binding_body(binding, parsed_gzip.body, index)
                raw_message = representation.unwrap(
                    raw_wrapper,
                    parsed_raw.a2a_version,
                    parsed_raw.activated_extensions,
                    source["sender"],
                )
                gzip_message = representation.unwrap(
                    gzip_wrapper,
                    parsed_gzip.a2a_version,
                    parsed_gzip.activated_extensions,
                    source["sender"],
                )
                exact_raw += raw_message == source
                exact_gzip += gzip_message == source

                second_wrapper = representation.wrap(source)
                second_body = build_binding_body(binding, second_wrapper, index)
                second_raw = build_http_request(
                    binding,
                    representation.extension_uri,
                    second_body,
                    compressed=False,
                )
                second_gzip = build_http_request(
                    binding,
                    representation.extension_uri,
                    second_body,
                    compressed=True,
                )
                deterministic_raw += second_raw == raw_request
                deterministic_gzip += second_gzip == gzip_request

                if index == 0 and representation.key == V01_KEY:
                    raw_head = raw_request.split(b"\r\n\r\n", 1)[0].decode("ascii")
                    gzip_head = gzip_request.split(b"\r\n\r\n", 1)[0].decode("ascii")
                    header_samples[f"{binding.key}-raw"] = raw_head
                    header_samples[f"{binding.key}-gzip"] = gzip_head

            result = EnvelopeResult(
                representation_key=representation.key,
                representation_label=representation.label,
                binding_key=binding.key,
                binding_label=binding.label,
                message_count=len(corpus),
                body_raw_sizes=tuple(body_raw_sizes),
                body_gzip_sizes=tuple(body_gzip_sizes),
                request_raw_sizes=tuple(request_raw_sizes),
                request_gzip_sizes=tuple(request_gzip_sizes),
                exact_raw=exact_raw,
                exact_gzip=exact_gzip,
                deterministic_raw=deterministic_raw,
                deterministic_gzip=deterministic_gzip,
                raw_request_digest=_sequence_digest(raw_requests),
                gzip_request_digest=_sequence_digest(gzip_requests),
            )
            results.append(result)
            digest_rows.append(
                (representation.key, binding.key, raw_requests, gzip_requests)
            )

    capsule = wire_v02.encode_capsule(wire_v02.DEFAULT_PROFILE)
    gzip_capsule = deterministic_gzip_compress(
        capsule, compresslevel=GZIP_LEVEL
    )
    return BenchmarkSummary(
        message_count=len(corpus),
        corpus_digest=corpus_digest(corpus),
        results=tuple(results),
        request_suite_digest=_suite_digest(digest_rows),
        capsule_raw_bytes=len(capsule),
        capsule_gzip_bytes=len(gzip_capsule),
        capsule_digest=hashlib.sha256(capsule).hexdigest(),
        dictionary_id=wire_v02.DEFAULT_PROFILE.dictionary_id_hex,
        header_samples=header_samples,
    )


def _total(values: Sequence[int]) -> int:
    return sum(values)


def _result_row(result: EnvelopeResult) -> str:
    return (
        f"| {result.representation_label} | {result.binding_label} | "
        f"{_total(result.body_raw_sizes):,} | {_total(result.request_raw_sizes):,} | "
        f"{_total(result.body_gzip_sizes):,} | {_total(result.request_gzip_sizes):,} | "
        f"{_nearest_rank(result.request_raw_sizes, 0.50):,} | "
        f"{_nearest_rank(result.request_gzip_sizes, 0.50):,} |"
    )


def render_report(summary: BenchmarkSummary) -> str:
    """Render the deterministic English Markdown report."""

    count = summary.message_count
    lines = [
        "# Full A2A v1 JSON request-envelope benchmark",
        "",
        f"Corpus: `{CORPUS_VERSION}`, {count} deterministic messages, SHA-256 "
        f"`{summary.corpus_digest}`  ",
        "A2A reference: latest released v1.0 request shapes (`A2A-Version: 1.0`), "
        "using the [A2A v1.0.0 specification](https://a2a-protocol.org/v1.0.0/specification/)  ",
        f"Deterministic full-request suite SHA-256: `{summary.request_suite_digest}`  ",
        f"Fixed unsigned test `source_id`: `{SOURCE_ID}`",
        "",
        "## Result and scope",
        "",
        "The tables below are byte accounting for complete representative HTTP/1.1 requests. "
        "They include the request line, `Host`, `A2A-Version`, `A2A-Extensions`, "
        "`Content-Type`, `Content-Length`, and the JSON body. The gzip rows compress each JSON "
        f"body independently with Python gzip level {GZIP_LEVEL}, `mtime=0`, an empty filename, "
        "and the canonical unknown-OS header byte; their full-request "
        "totals also include `Content-Encoding: gzip`, while HTTP headers remain uncompressed.",
        "",
        "The measurement does not establish that one representation is faster, better understood "
        "by models, safer, or more effective at completing tasks. It is a fixed synthetic, "
        "already-structured, in-domain corpus. The v0.2 profile was manually specialized for "
        "this schema family and its wrapper is explicitly experimental.",
        "",
        "## Measured bytes",
        "",
        "| Representation | Binding | JSON body raw total | Full request raw total | JSON body gzip total | Full request gzip total | Full raw p50/msg | Full gzip p50/msg |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(_result_row(result) for result in summary.results)
    lines.extend(
        [
            "",
            f"Every total covers exactly `{count}` independent requests. Base64 expansion, A2A "
            "Message fields, extension declarations, extension metadata, the JSON-RPC request "
            "object, and the binding-specific HTTP headers are included where applicable. JSON "
            "uses sorted keys and minified UTF-8 solely to make the harness deterministic; A2A "
            "does not require this member order.",
            "",
            "The structured row carries canonical UrusillaIR in a standard `data` Part and retains "
            "the same current extension/source-pin footprint for comparison. It is not a newly "
            "implemented path in the hardened adapter. The v0.1 row calls the current "
            "`wrap_a2a_message` and `unwrap_a2a_message` paths. The v0.2 row uses a distinct "
            "benchmark-only extension URI, media type parameter, and metadata marker, and is not "
            "accepted by the v0.1 adapter.",
            "",
            "## Exact and deterministic round-trip",
            "",
            "| Representation | Binding | Raw exact | gzip exact | Raw byte-deterministic | gzip byte-deterministic |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for result in summary.results:
        lines.append(
            f"| {result.representation_label} | {result.binding_label} | "
            f"{result.exact_raw}/{count} | {result.exact_gzip}/{count} | "
            f"{result.deterministic_raw}/{count} | {result.deterministic_gzip}/{count} |"
        )
    lines.extend(
        [
            "",
            "`Exact` means the harness parsed the complete HTTP request, checked the service and "
            "content headers, decompressed when applicable, validated the selected binding body, "
            "decoded its Part, and recovered the exact canonical source message. "
            "`Byte-deterministic` means an independent rebuild produced the same complete request "
            "bytes. This is deterministic serialization within these pinned profiles, not a claim "
            "that all conforming A2A implementations emit identical JSON bytes.",
            "",
            "## Aggregate request digests",
            "",
            "Each digest covers an ordered sequence of complete requests with an eight-byte "
            "big-endian length prefix before every request.",
            "",
            "| Representation | Binding | Raw request stream SHA-256 | gzip request stream SHA-256 |",
            "|---|---|---|---|",
        ]
    )
    for result in summary.results:
        lines.append(
            f"| {result.representation_label} | {result.binding_label} | "
            f"`{result.raw_request_digest}` | `{result.gzip_request_digest}` |"
        )
    lines.extend(
        [
            "",
            "## Representative HTTP/1.1 request headers",
            "",
            "The following heads are from corpus message 1 using the current v0.1 RawPart. "
            "`Content-Length` is the exact byte length of that request body after any indicated "
            "content coding. The JSON-RPC path is representative; an actual endpoint is selected "
            "from the peer's Agent Card.",
            "",
            "HTTP+JSON, raw body:",
            "",
            "```http",
            summary.header_samples[f"{REST_KEY}-raw"].replace("\r\n", "\n"),
            "```",
            "",
            "JSON-RPC, raw body:",
            "",
            "```http",
            summary.header_samples[f"{JSON_RPC_KEY}-raw"].replace("\r\n", "\n"),
            "```",
            "",
            "HTTP+JSON, per-message gzip body:",
            "",
            "```http",
            summary.header_samples[f"{REST_KEY}-gzip"].replace("\r\n", "\n"),
            "```",
            "",
            "The structured and v0.1 rows activate "
            f"`{EXTENSION_URI}`. The v0.2 experimental row activates "
            f"`{V02_EXTENSION_URI}`.",
            "",
            "## Cold v0.2 profile cost",
            "",
            f"The warm v0.2 row depends on the default static profile with `{len(wire_v02.DEFAULT_PROFILE.strings)}` "
            f"strings, `{len(wire_v02.DEFAULT_PROFILE.shapes)}` map shapes, and dictionary ID "
            f"`{summary.dictionary_id}`. Its serialized profile capsule is reported separately "
            "and is not added to any warm-request total.",
            "",
            "| Object | Raw bytes | Per-object gzip bytes | SHA-256 of raw object |",
            "|---|---:|---:|---|",
            f"| Experimental v0.2 static-profile capsule | {summary.capsule_raw_bytes:,} | "
            f"{summary.capsule_gzip_bytes:,} | `{summary.capsule_digest}` |",
            "",
            "This profile-only cold number excludes Agent Card discovery, profile authorization, "
            "cache validation, negotiation round trips, the existing Grammar Capsule, source "
            "manifest delivery, and fallback setup. A deployment must model those costs before "
            "claiming a session break-even.",
            "",
            "## Fixed unsigned source-manifest fixture and security boundary",
            "",
            f"All rows use `{SOURCE_ID}`, derived from a fixed unsigned source-manifest fixture, "
            "so the hot-message metadata footprint and derivation are explicit. Every artifact "
            "location in the fixture is an immutable-shaped GitHub URL, but the commit values and "
            "conformance digest are synthetic test vectors, the URLs are not fetched, and the "
            "manifest is not signature-verified. It must not be used as production provenance. It does not "
            "authenticate the semantic sender. The benchmark supplies the known sender to local "
            "decode checks, but sends no credential and performs no authentication protocol.",
            "",
            "UrusillaWire checksums and gzip CRCs detect accidental damage; they are not signatures, "
            "authorization, replay protection, or integrity against an attacker who can recompute "
            "them. No request in this research artifact authorizes an external side effect.",
            "",
            "## Strict limitations",
            "",
            "- The corpus is synthetic and already contains valid UrusillaIR. Natural-language "
            "translation, ambiguity, omissions, repair turns, model input/output tokens, task "
            "success, and receiver comprehension are not measured.",
            "- The v0.2 dictionary and shapes were manually derived from this benchmark family. "
            "The v0.2 numbers are an in-domain warm-profile result, not an out-of-domain or "
            "general compression claim.",
            "- HTTP+JSON counts the required `SendMessageRequest.message` field. JSON-RPC counts "
            "`jsonrpc`, a deterministic one-based numeric `id`, `method: SendMessage`, and the "
            "same request under `params`. Optional `tenant`, `configuration`, and request-level "
            "`metadata` are omitted.",
            "- The representative HTTP/1.1 head omits `Authorization`, `Accept`, `User-Agent`, "
            "cookies, tracing, proxies, and deployment-specific headers. Request-body gzip support "
            "must be negotiated or known; this benchmark does not show that every A2A server "
            "accepts `Content-Encoding: gzip`.",
            "- TLS records, TCP/IP packets, DNS, connection setup, retransmission, HTTP/2 or "
            "HTTP/3 framing, responses, streaming, gRPC, persistence, and storage are excluded. "
            "The totals therefore are not end-to-end network cost.",
            "- Gzip is independent per message with no shared stream or dictionary. Other "
            "compression levels, zstd, CBOR, schema-equivalent Protobuf, and production SDK "
            "serialization could change the ordering.",
            "- This is not an A2A conformance suite, a deployed client/server measurement, or "
            "evidence of official registration or standardization of any private extension URI or "
            "media type.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "PYTHONDONTWRITEBYTECODE=1 python3 urusilla_a2a_envelope_benchmark.py",
            "PYTHONDONTWRITEBYTECODE=1 python3 test_urusilla_a2a_envelope_benchmark.py",
            "```",
            "",
            "The report has no timestamp or machine-dependent timing field, so the same source "
            "files, canonical gzip helper, Python JSON behavior, corpus version, and default options produce the "
            "same report bytes. Corpus and request-stream digests fail visibly if serialization "
            "changes.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("urusilla_a2a_envelope_results.md"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.messages < 100:
        raise SystemExit("--messages must be at least 100")
    summary = run_benchmark(args.messages)
    report = render_report(summary)
    args.output.write_text(report, encoding="utf-8")
    report_digest = hashlib.sha256(report.encode("utf-8")).hexdigest()
    print(f"wrote {args.output}")
    print(
        f"corpus: {summary.message_count} messages, sha256={summary.corpus_digest}"
    )
    print(f"full request suite: sha256={summary.request_suite_digest}")
    print(f"report: sha256={report_digest}")
    for result in summary.results:
        print(
            f"{result.representation_key}/{result.binding_key}: "
            f"raw={_total(result.request_raw_sizes)} bytes, "
            f"gzip={_total(result.request_gzip_sizes)} bytes, "
            f"exact={result.exact_raw}/{result.message_count}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
