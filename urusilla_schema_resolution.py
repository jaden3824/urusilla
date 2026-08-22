#!/usr/bin/env python3
"""Offline required-schema availability resolution for Urusilla routing.

The v0.1 structural codec validates schema identifiers but deliberately does
not fetch or trust remote content.  This layer accepts only caller-supplied
bytes, verifies them against a project-pinned content binding, and either
enables the typed route for the current QUERY or returns a closed JSON/text
fallback.  Resolution alone never makes a response strictly conformant.  The
module performs no network call and grants no effect authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Mapping

from urusilla import ValidationError, normalize_message
from urusilla_hybrid_runtime.canonical import JsonValidationError, strict_json_loads


BINDING_FIELDS = frozenset({"uri", "sha256", "bytes", "media_type"})
DECISION_FORMAT = "urusilla-required-schema-resolution-decision/1"
SCHEMA_MEDIA_TYPE = "application/schema+json"
MAX_SCHEMA_BYTES = 1_048_576
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PINNED_SCHEMA_BINDINGS = {
    "urn:urusilla:schema:peer-dialogue-reply:0.1": (
        "sha256:4e40793ff15a897db35f3805c252f38f47dff816d76e37de9b7a17f210152e37",
        1202,
        SCHEMA_MEDIA_TYPE,
    ),
}


class SchemaResolutionError(ValidationError):
    """Raised when the local resolver invocation is outside its contract."""


@dataclass(frozen=True)
class SchemaResource:
    """One already-obtained, non-authoritative schema resource."""

    uri: str
    media_type: str
    content: bytes

    def __post_init__(self) -> None:
        if type(self.uri) is not str or not self.uri:
            raise SchemaResolutionError("schema resource URI must be non-empty text")
        if type(self.media_type) is not str or not self.media_type:
            raise SchemaResolutionError("schema resource media type must be non-empty text")
        if type(self.content) is not bytes:
            raise SchemaResolutionError("schema resource content must be bytes")
        if len(self.content) > MAX_SCHEMA_BYTES:
            raise SchemaResolutionError("schema resource exceeds the local byte limit")


def _fallback(
    *, schema_uri: str | None, reason_code: str, route: str
) -> dict[str, Any]:
    if route == "json":
        fallback: dict[str, Any] = {
            "media_type": "application/json",
            "value": {"reason_code": reason_code, "status": "fallback"},
        }
    elif route == "text":
        fallback = {
            "media_type": "text/plain",
            "value": f"Required answer schema unavailable ({reason_code}); use concise text.",
        }
    else:
        raise SchemaResolutionError("fallback route must be json or text")
    return {
        "conformance_scope": "required-answer-schema",
        "effect_authorized": False,
        "fallback": fallback,
        "format": DECISION_FORMAT,
        "reason_code": reason_code,
        "route": route,
        "schema_binding_verified": False,
        "schema_uri": schema_uri,
        "strict_conformance": False,
    }


def _success(schema_uri: str) -> dict[str, Any]:
    return {
        "conformance_scope": "required-answer-schema",
        "effect_authorized": False,
        "fallback": None,
        "format": DECISION_FORMAT,
        "reason_code": "required-schema-resolved",
        "route": "urusilla",
        "schema_binding_verified": True,
        "schema_uri": schema_uri,
        "strict_conformance": False,
    }


def resolve_required_answer_schema(
    message: Mapping[str, Any],
    binding: Mapping[str, Any],
    resources: Mapping[str, SchemaResource],
    *,
    fallback_route: str = "json",
) -> dict[str, Any]:
    """Resolve one QUERY answer schema against an offline resource map.

    A successful decision requires an exact match to a project-pinned URI,
    SHA-256, byte length, and media type, plus valid JSON and a matching schema
    document ``$id``.  The decision covers only resource availability at the
    required-answer-schema stage.  It does not validate a future answer
    instance, authenticate a publisher, or establish strict conformance.
    Callers must bind those and all deployment requirements separately.  Every
    observable resolution failure returns a closed fallback decision;
    malformed messages still fail through the structural validator.
    """

    if fallback_route not in {"json", "text"}:
        raise SchemaResolutionError("fallback route must be json or text")
    canonical = normalize_message(message)
    body = canonical["body"]
    if canonical["act"] != "QUERY" or body.get("kind") != (
        "question-plus-answer-schema"
    ):
        raise SchemaResolutionError(
            "required answer-schema resolution applies only to a typed QUERY"
        )
    schema_uri = body["answer_schema"]

    if not isinstance(binding, Mapping) or set(binding) != BINDING_FIELDS:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-binding-invalid",
            route=fallback_route,
        )
    bound_uri = binding.get("uri")
    bound_sha256 = binding.get("sha256")
    bound_bytes = binding.get("bytes")
    bound_media_type = binding.get("media_type")
    if (
        type(bound_uri) is not str
        or type(bound_sha256) is not str
        or _SHA256_RE.fullmatch(bound_sha256) is None
        or type(bound_bytes) is not int
        or not 0 <= bound_bytes <= MAX_SCHEMA_BYTES
        or type(bound_media_type) is not str
        or bound_media_type != SCHEMA_MEDIA_TYPE
    ):
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-binding-invalid",
            route=fallback_route,
        )
    if bound_uri != schema_uri:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-uri-mismatch",
            route=fallback_route,
        )
    pinned = _PINNED_SCHEMA_BINDINGS.get(schema_uri)
    if pinned is None:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-not-pinned",
            route=fallback_route,
        )
    if (bound_sha256, bound_bytes, bound_media_type) != pinned:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-binding-not-pinned",
            route=fallback_route,
        )

    resource = resources.get(schema_uri)
    if resource is None:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-missing",
            route=fallback_route,
        )
    if not isinstance(resource, SchemaResource) or resource.uri != schema_uri:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-uri-mismatch",
            route=fallback_route,
        )
    if resource.media_type != bound_media_type:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-media-type-mismatch",
            route=fallback_route,
        )
    if len(resource.content) != bound_bytes:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-byte-length-mismatch",
            route=fallback_route,
        )
    actual_sha256 = "sha256:" + hashlib.sha256(resource.content).hexdigest()
    if actual_sha256 != bound_sha256:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-sha256-mismatch",
            route=fallback_route,
        )
    try:
        schema_text = resource.content.decode("utf-8")
        schema = strict_json_loads(schema_text, max_bytes=MAX_SCHEMA_BYTES)
    except (UnicodeDecodeError, JsonValidationError):
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-invalid-json",
            route=fallback_route,
        )
    if type(schema) is not dict or schema.get("$id") != schema_uri:
        return _fallback(
            schema_uri=schema_uri,
            reason_code="required-schema-id-mismatch",
            route=fallback_route,
        )
    return _success(schema_uri)
