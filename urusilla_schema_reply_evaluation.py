#!/usr/bin/env python3
"""Bounded reply-evidence scoring after required-schema resolution.

This project-profile layer keeps a shaped reply from rescuing an unresolved
answer schema.  It evaluates only one flat reply payload contract used by the
public-dialogue follow-up fixtures.  It does not change Urusilla 0.1 core
semantics, authenticate an agent, authorize effects, or establish full
protocol conformance.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from urusilla import ValidationError, normalize_message
from urusilla_hybrid_runtime.canonical import JsonValidationError, strict_json_loads
from urusilla_schema_resolution import (
    BINDING_FIELDS,
    MAX_SCHEMA_BYTES,
    SCHEMA_MEDIA_TYPE,
    SchemaResource,
    resolve_required_answer_schema,
)


EVALUATION_FORMAT = "urusilla-required-schema-reply-evaluation/1"
DIAGNOSTIC_FIELDS = frozenset({"schema_urn", "validated_against"})
INLINE_FALLBACK_ELIGIBLE_REASONS = frozenset(
    {"required-schema-missing"}
)
_PINNED_INLINE_FALLBACK_BINDINGS = {
    "urn:urusilla:contract:inline-peer-dialogue-reply-evidence:0.1": (
        "sha256:3480011e042491dea9f57cd52305afda697b3ddffa37985d57b8f4947c925b45",
        1184,
        SCHEMA_MEDIA_TYPE,
    )
}


class ReplyEvidenceError(ValidationError):
    """Raised when a reply-evidence invocation is outside its narrow contract."""


def _inline_required_fields(body: Mapping[str, Any]) -> frozenset[str]:
    fields: set[str] = set()
    for constraint in body.get("constraints", []):
        if (
            constraint.get("scope") != "answer"
            or constraint.get("mode") != "hard"
        ):
            continue
        condition = constraint.get("condition")
        if not isinstance(condition, Mapping) or "required_fields" not in condition:
            continue
        required = condition["required_fields"]
        if (
            type(required) is not list
            or not required
            or not all(type(field) is str and field for field in required)
            or len(required) != len(set(required))
        ):
            raise ReplyEvidenceError("inline required_fields must be unique text")
        fields.update(required)
    return frozenset(fields)


def _payload_schema(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    properties = schema.get("properties")
    if isinstance(properties, Mapping) and "arguments" in properties:
        try:
            payload = properties["arguments"]["prefixItems"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ReplyEvidenceError("resolved schema has no bounded reply payload") from exc
        if not isinstance(payload, Mapping):
            raise ReplyEvidenceError("resolved reply payload schema must be an object")
        return payload
    return schema


def _schema_fields(schema: Mapping[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    required = schema.get("required")
    properties = schema.get("properties")
    if (
        type(required) is not list
        or not required
        or not all(type(field) is str and field for field in required)
        or len(required) != len(set(required))
        or not isinstance(properties, Mapping)
        or schema.get("additionalProperties") is not False
    ):
        raise ReplyEvidenceError(
            "reply evidence schema must declare unique required fields and close extras"
        )
    if not set(required).issubset(properties):
        raise ReplyEvidenceError("reply evidence schema required fields lack properties")
    return frozenset(required), frozenset(properties)


def _validate_flat_reply(
    reply: Mapping[str, Any], schema: Mapping[str, Any]
) -> tuple[list[str], list[str], list[str], frozenset[str]]:
    if not all(type(field) is str for field in reply):
        raise ReplyEvidenceError("reply artifact field names must be text")
    required, allowed = _schema_fields(schema)
    reply_fields = frozenset(reply)
    missing = sorted(required - reply_fields)
    unexpected = sorted(reply_fields - allowed)
    invalid: list[str] = []
    properties = schema["properties"]
    for field in sorted(reply_fields & allowed):
        rule = properties[field]
        if not isinstance(rule, Mapping):
            raise ReplyEvidenceError(f"reply property {field} rule must be an object")
        value = reply[field]
        if "const" in rule and value != rule["const"]:
            invalid.append(field)
            continue
        if "enum" in rule and value not in rule["enum"]:
            invalid.append(field)
            continue
        if rule.get("type") == "string":
            if type(value) is not str or len(value) < rule.get("minLength", 0):
                invalid.append(field)
    return missing, unexpected, invalid, required


def _verified_inline_contract(
    query: Mapping[str, Any], resource: SchemaResource | None
) -> Mapping[str, Any] | None:
    binding = query.get("meta", {}).get("inline_fallback_contract")
    if not isinstance(binding, Mapping) or set(binding) != BINDING_FIELDS:
        return None
    pinned = _PINNED_INLINE_FALLBACK_BINDINGS.get(binding.get("uri"))
    if pinned is None or (
        binding.get("sha256"), binding.get("bytes"), binding.get("media_type")
    ) != pinned:
        return None
    if (
        resource is None
        or binding.get("uri") != resource.uri
        or binding.get("media_type") != SCHEMA_MEDIA_TYPE
        or resource.media_type != SCHEMA_MEDIA_TYPE
        or type(binding.get("bytes")) is not int
        or binding["bytes"] != len(resource.content)
        or type(binding.get("sha256")) is not str
        or binding["sha256"]
        != "sha256:" + hashlib.sha256(resource.content).hexdigest()
    ):
        return None
    try:
        contract = strict_json_loads(
            resource.content.decode("utf-8"), max_bytes=MAX_SCHEMA_BYTES
        )
    except (UnicodeDecodeError, JsonValidationError):
        return None
    if type(contract) is not dict or contract.get("$id") != resource.uri:
        return None
    return contract


def _result(
    *,
    classification: str,
    reason_code: str,
    schema_uri: str,
    resolution: Mapping[str, Any],
    reply: Mapping[str, Any],
    inline_fields: frozenset[str],
    schema_fields: frozenset[str],
    missing: list[str],
    unexpected: list[str],
    invalid: list[str],
    schema_payload_valid: bool,
    fallback_artifact_valid: bool,
    inline_contract_verified: bool,
    reply_evidence_signal_valid: bool,
    must_fail: bool,
) -> dict[str, Any]:
    return {
        "classification": classification,
        "effect_authorized": False,
        "fallback_artifact_valid": fallback_artifact_valid,
        "format": EVALUATION_FORMAT,
        "inline_fallback_contract_verified": inline_contract_verified,
        "inline_required_fields": sorted(inline_fields),
        "invalid_fields": invalid,
        "missing_fields": missing,
        "must_fail": must_fail,
        "reason_code": reason_code,
        "reply_evidence_signal_valid": reply_evidence_signal_valid,
        "resolution_reason_code": resolution["reason_code"],
        "schema_binding_verified": resolution["schema_binding_verified"],
        "schema_payload_valid": schema_payload_valid,
        "schema_required_fields": sorted(schema_fields),
        "schema_uri": schema_uri,
        "schema_urn": reply.get("schema_urn"),
        "publisher_authenticated": False,
        "strict_conformance": False,
        "unexpected_fields": unexpected,
        "validated_against": reply.get("validated_against"),
    }


def evaluate_required_schema_reply(
    message: Mapping[str, Any],
    binding: Mapping[str, Any],
    resources: Mapping[str, SchemaResource],
    reply: object,
    *,
    inline_fallback_resource: SchemaResource | None = None,
) -> dict[str, Any]:
    """Score one reply artifact against the actual schema-resolution path."""

    reply_is_object = isinstance(reply, Mapping)
    reply = reply if reply_is_object else {}
    if not isinstance(resources, Mapping):
        raise ReplyEvidenceError("schema resources must be a mapping")
    resource_snapshot = dict(resources)
    query = normalize_message(message)
    body = query["body"]
    if query["act"] != "QUERY" or body.get("kind") != "question-plus-answer-schema":
        raise ReplyEvidenceError("reply evidence applies only to a typed QUERY")
    schema_uri = body["answer_schema"]
    inline_fields = _inline_required_fields(body)
    resolution = resolve_required_answer_schema(query, binding, resource_snapshot)
    if (
        resolution.get("schema_uri") != schema_uri
        or resolution.get("effect_authorized") is not False
        or resolution.get("strict_conformance") is not False
    ):
        raise ReplyEvidenceError("schema-resolution decision is inconsistent")

    resolved = (
        resolution["route"] == "urusilla"
        and resolution["reason_code"] == "required-schema-resolved"
        and resolution["schema_binding_verified"] is True
    )
    if resolved:
        resource = resource_snapshot.get(schema_uri)
        if not isinstance(resource, SchemaResource):
            raise ReplyEvidenceError("verified resolution lacks its schema resource")
        try:
            schema = strict_json_loads(
                resource.content.decode("utf-8"), max_bytes=MAX_SCHEMA_BYTES
            )
        except (UnicodeDecodeError, JsonValidationError) as exc:
            raise ReplyEvidenceError("verified schema resource is not valid JSON") from exc
        if type(schema) is not dict or schema.get("$id") != schema_uri:
            raise ReplyEvidenceError("verified schema resource identity changed")
        payload_schema = _payload_schema(schema)
        if not reply_is_object:
            required, _ = _schema_fields(payload_schema)
            return _result(
                classification="rejected",
                reason_code="reply-artifact-not-object",
                schema_uri=schema_uri,
                resolution=resolution,
                reply=reply,
                inline_fields=inline_fields,
                schema_fields=required,
                missing=sorted(required),
                unexpected=[],
                invalid=[],
                schema_payload_valid=False,
                fallback_artifact_valid=False,
                inline_contract_verified=False,
                reply_evidence_signal_valid=False,
                must_fail=False,
            )
        missing, unexpected, invalid, required = _validate_flat_reply(
            reply, payload_schema
        )
        if reply.get("validated_against") != "resolved-schema":
            if "validated_against" not in missing:
                invalid = sorted(set(invalid) | {"validated_against"})
        if reply.get("schema_urn") != schema_uri:
            if "schema_urn" not in missing:
                invalid = sorted(set(invalid) | {"schema_urn"})
        valid = not missing and not unexpected and not invalid
        if valid:
            return _result(
                classification="resolved-schema-payload",
                reason_code="resolved-schema-reply-payload-verified",
                schema_uri=schema_uri,
                resolution=resolution,
                reply=reply,
                inline_fields=inline_fields,
                schema_fields=required,
                missing=missing,
                unexpected=unexpected,
                invalid=invalid,
                schema_payload_valid=True,
                fallback_artifact_valid=False,
                inline_contract_verified=False,
                reply_evidence_signal_valid=True,
                must_fail=False,
            )
        exact_diagnostic_gap = (
            set(missing) == DIAGNOSTIC_FIELDS
            and not unexpected
            and not invalid
            and inline_fields == required - DIAGNOSTIC_FIELDS
        )
        classification = "underdetermined" if exact_diagnostic_gap else "rejected"
        return _result(
            classification=classification,
            reason_code=(
                "resolved-schema-reply-fields-missing"
                if missing
                else "resolved-schema-reply-invalid"
            ),
            schema_uri=schema_uri,
            resolution=resolution,
            reply=reply,
            inline_fields=inline_fields,
            schema_fields=required,
            missing=missing,
            unexpected=unexpected,
            invalid=invalid,
            schema_payload_valid=False,
            fallback_artifact_valid=False,
            inline_contract_verified=False,
            reply_evidence_signal_valid=False,
            must_fail=False,
        )

    if resolution["reason_code"] not in INLINE_FALLBACK_ELIGIBLE_REASONS:
        return _result(
            classification="must-fail",
            reason_code="schema-resolution-failure-not-fallback-eligible",
            schema_uri=schema_uri,
            resolution=resolution,
            reply=reply,
            inline_fields=inline_fields,
            schema_fields=frozenset(),
            missing=[],
            unexpected=[],
            invalid=[],
            schema_payload_valid=False,
            fallback_artifact_valid=False,
            inline_contract_verified=False,
            reply_evidence_signal_valid=False,
            must_fail=True,
        )

    contract = _verified_inline_contract(query, inline_fallback_resource)
    if contract is None:
        return _result(
            classification="must-fail",
            reason_code="unresolved-schema-no-content-bound-inline-contract",
            schema_uri=schema_uri,
            resolution=resolution,
            reply=reply,
            inline_fields=inline_fields,
            schema_fields=frozenset(),
            missing=[],
            unexpected=[],
            invalid=[],
            schema_payload_valid=False,
            fallback_artifact_valid=False,
            inline_contract_verified=False,
            reply_evidence_signal_valid=False,
            must_fail=True,
        )

    payload_schema = _payload_schema(contract)
    if not reply_is_object:
        required, _ = _schema_fields(payload_schema)
        return _result(
            classification="inline-fallback-rejected",
            reason_code="reply-artifact-not-object",
            schema_uri=schema_uri,
            resolution=resolution,
            reply=reply,
            inline_fields=inline_fields,
            schema_fields=required,
            missing=sorted(required),
            unexpected=[],
            invalid=[],
            schema_payload_valid=False,
            fallback_artifact_valid=False,
            inline_contract_verified=True,
            reply_evidence_signal_valid=False,
            must_fail=False,
        )
    missing, unexpected, invalid, required = _validate_flat_reply(reply, payload_schema)
    if not inline_fields.issubset(required) or not DIAGNOSTIC_FIELDS.issubset(required):
        raise ReplyEvidenceError(
            "inline fallback contract must cover declared and diagnostic fields"
        )
    if reply.get("validated_against") != "inline-fallback":
        if "validated_against" not in missing:
            invalid = sorted(set(invalid) | {"validated_against"})
    if reply.get("schema_urn") != schema_uri:
        if "schema_urn" not in missing:
            invalid = sorted(set(invalid) | {"schema_urn"})
    valid = not missing and not unexpected and not invalid
    return _result(
        classification=(
            "inline-fallback-artifact" if valid else "inline-fallback-rejected"
        ),
        reason_code=(
            "inline-fallback-artifact-verified"
            if valid
            else "inline-fallback-reply-invalid"
        ),
        schema_uri=schema_uri,
        resolution=resolution,
        reply=reply,
        inline_fields=inline_fields,
        schema_fields=required,
        missing=missing,
        unexpected=unexpected,
        invalid=invalid,
        schema_payload_valid=False,
        fallback_artifact_valid=valid,
        inline_contract_verified=True,
        reply_evidence_signal_valid=False,
        must_fail=False,
    )
