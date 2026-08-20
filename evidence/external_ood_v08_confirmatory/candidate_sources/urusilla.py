#!/usr/bin/env python3
"""Urusilla v0.1 reference prototype.

Urusilla is a machine-first semantic interlingua for AI agents.  The normative
object is a typed semantic message.  UrusillaWire is its deterministic, opaque
binary representation; UrusillaLens renders the decoded meaning for humans.

This prototype intentionally uses only the Python standard library.  It is a
proof of architecture, not yet a claim of optimal compression.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import struct
import sys
import uuid
from typing import Any, Callable, Iterable, Mapping, Sequence


MAGIC = b"URSL\x01"
FLAGS = 0x01  # Canonical profile.
CHECKSUM_SIZE = 16

MAX_FRAME_BYTES = 16 * 1024 * 1024
MAX_DICTIONARY_ITEMS = 65_535
MAX_STRING_BYTES = 1 * 1024 * 1024
MAX_COLLECTION_ITEMS = 100_000
MAX_SEMANTIC_NODES = 250_000
MAX_DEPTH = 64

ACTS = (
    "ASSERT",
    "QUERY",
    "REQUEST",
    "PROPOSE",
    "COMMIT",
    "RESOLVE",
    "RETRACT",
)
ACT_TO_CODE = {name: code for code, name in enumerate(ACTS)}

CORE_KINDS: dict[str, tuple[str, ...]] = {
    "claim": ("predicate",),
    "goal": ("condition",),
    "constraint": ("scope", "mode", "condition"),
    "evidence": ("target", "stance", "digest", "provenance"),
    "uncertainty": ("target", "model", "parameters"),
    "action": ("capability", "arguments"),
    "commitment": ("debtor", "creditors", "goal", "expiry_ms"),
    "resolution": ("target", "status"),
    "ref": ("uri",),
    "question-plus-answer-schema": ("question", "answer_schema"),
}

TOP_LEVEL_FIELDS = frozenset(
    {
        "id",
        "session",
        "sender",
        "recipients",
        "act",
        "reply_to",
        "schema",
        "logical_clock",
        "expires_ms",
        "confidence_ppm",
        "expected",
        "body",
        "meta",
    }
)

CORE_KIND_FIELDS: dict[str, frozenset[str]] = {
    "claim": frozenset(
        {"kind", "predicate", "arguments", "context", "valid_time", "answer_limit", "annotations"}
    ),
    "goal": frozenset(
        {"kind", "condition", "owner", "window", "priority", "constraints", "annotations"}
    ),
    "constraint": frozenset(
        {"kind", "scope", "mode", "condition", "weight", "weight_ppm", "annotations"}
    ),
    "evidence": frozenset(
        {
            "kind",
            "target",
            "stance",
            "digest",
            "provenance",
            "observed_at",
            "observed_at_ms",
            "method",
            "annotations",
        }
    ),
    "uncertainty": frozenset(
        {"kind", "target", "model", "parameters", "basis", "annotations"}
    ),
    "action": frozenset(
        {"kind", "capability", "arguments", "declared_effects", "annotations"}
    ),
    "commitment": frozenset(
        {
            "kind",
            "debtor",
            "creditors",
            "goal",
            "expiry_ms",
            "verifier",
            "cancellation_rule",
            "annotations",
        }
    ),
    "resolution": frozenset(
        {"kind", "target", "status", "result", "evidence", "annotations"}
    ),
    "ref": frozenset({"kind", "uri", "annotations"}),
    "question-plus-answer-schema": frozenset(
        {"kind", "question", "answer_schema", "constraints", "annotations"}
    ),
}

ACT_BODY_KINDS: dict[str, frozenset[str]] = {
    "ASSERT": frozenset({"claim", "evidence", "uncertainty", "ref"}),
    "QUERY": frozenset({"claim", "question-plus-answer-schema"}),
    "REQUEST": frozenset({"goal"}),
    "PROPOSE": frozenset({"action"}),
    "COMMIT": frozenset({"commitment"}),
    "RESOLVE": frozenset({"resolution"}),
    "RETRACT": frozenset({"ref"}),
}

EFFECTFUL_ACTS = frozenset({"COMMIT", "RESOLVE", "RETRACT"})
RESOLUTION_STATUSES = frozenset(
    {"succeeded", "completed", "failed", "expired", "rejected", "canceled", "error"}
)
EVIDENCE_STANCES = frozenset({"supports", "contradicts", "neutral"})
_IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s]+\Z")


class UrusillaError(ValueError):
    """Base class for validation, encoding, and decoding errors."""


class ValidationError(UrusillaError):
    pass


class DecodeError(UrusillaError):
    pass


class SemanticNodeBudget:
    """Shared body-and-meta node budget used before recursive allocation."""

    __slots__ = ("remaining",)

    def __init__(self, limit: int = MAX_SEMANTIC_NODES):
        self.remaining = limit

    def consume(self, error_type: type[UrusillaError]) -> None:
        if self.remaining == 0:
            raise error_type(
                f"semantic tree exceeds aggregate node limit {MAX_SEMANTIC_NODES}"
            )
        self.remaining -= 1

    def require_minimum_children(
        self, count: int, error_type: type[UrusillaError]
    ) -> None:
        if count > self.remaining:
            raise error_type(
                f"semantic tree exceeds aggregate node limit {MAX_SEMANTIC_NODES}"
            )


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
            raise DecodeError("truncated frame")
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


def _uuid_bytes(value: str, field: str) -> bytes:
    try:
        return uuid.UUID(value).bytes
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError(f"{field} must be a canonical UUID string") from exc


def _uuid_text(value: bytes) -> str:
    return str(uuid.UUID(bytes=value))


def _nonempty_text(value: Any, field: str) -> str:
    if type(value) is not str or not value:
        raise ValidationError(f"{field} must be a non-empty string")
    if len(_utf8_bytes(value, field)) > MAX_STRING_BYTES:
        raise ValidationError(f"{field} exceeds size limit")
    if any(ord(character) < 0x20 or character.isspace() for character in value):
        raise ValidationError(f"{field} cannot contain whitespace or control characters")
    return value


def _utf8_bytes(value: str, field: str) -> bytes:
    """Encode validated text without leaking a raw UnicodeEncodeError."""

    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{field} contains invalid Unicode") from exc


def _identifier(value: Any, field: str) -> str:
    text = _nonempty_text(value, field)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise ValidationError(f"{field} must be an absolute URI or content identifier")
    return text


def _canonical_uuid(value: Any, field: str) -> str:
    if type(value) is not str:
        raise ValidationError(f"{field} must be a canonical UUID string")
    try:
        canonical = str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError(f"{field} must be a canonical UUID string") from exc
    if value != canonical:
        raise ValidationError(f"{field} must use lowercase canonical UUID text")
    return canonical


def _require_list(value: Any, field: str, *, nonempty: bool = False) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{field} must be a canonical list")
    if nonempty and not value:
        raise ValidationError(f"{field} must be non-empty")
    return value


def _validate_known_node(value: Mapping[str, Any], kind: str) -> None:
    unknown = sorted(set(value) - CORE_KIND_FIELDS[kind])
    if unknown:
        raise ValidationError(
            f"{kind} node has unknown field(s): {', '.join(unknown)}; use annotations"
        )
    annotations = value.get("annotations")
    if annotations is not None and not isinstance(annotations, Mapping):
        raise ValidationError(f"{kind}.annotations must be a map")

    if kind == "claim":
        _nonempty_text(value["predicate"], "claim.predicate")
        if "arguments" in value:
            _require_list(value["arguments"], "claim.arguments")
        if "context" in value and not isinstance(value["context"], Mapping):
            raise ValidationError("claim.context must be a map")
        if "answer_limit" in value and (
            type(value["answer_limit"]) is not int or value["answer_limit"] <= 0
        ):
            raise ValidationError("claim.answer_limit must be a positive integer")
    elif kind == "goal":
        if not isinstance(value["condition"], Mapping):
            raise ValidationError("goal.condition must be a semantic node")
        if "owner" in value:
            _nonempty_text(value["owner"], "goal.owner")
        if "priority" in value and type(value["priority"]) is not int:
            raise ValidationError("goal.priority must be an integer")
        if "constraints" in value:
            constraints = _require_list(value["constraints"], "goal.constraints")
            if any(
                not isinstance(item, Mapping) or item.get("kind") != "constraint"
                for item in constraints
            ):
                raise ValidationError("goal.constraints must contain constraint nodes")
    elif kind == "constraint":
        _nonempty_text(value["scope"], "constraint.scope")
        if type(value["mode"]) is not str or value["mode"] not in {"hard", "soft"}:
            raise ValidationError("constraint.mode must be hard or soft")
        if "weight_ppm" in value and (
            type(value["weight_ppm"]) is not int
            or not 0 <= value["weight_ppm"] <= 1_000_000
        ):
            raise ValidationError("constraint.weight_ppm must be an integer from 0 to 1,000,000")
    elif kind == "evidence":
        if type(value["stance"]) is not str or value["stance"] not in EVIDENCE_STANCES:
            raise ValidationError("evidence.stance is not recognized")
        _identifier(value["digest"], "evidence.digest")
        if type(value["provenance"]) is not str and not isinstance(
            value["provenance"], (Mapping, list)
        ):
            raise ValidationError("evidence.provenance must be a string, map, or list")
    elif kind == "uncertainty":
        _nonempty_text(value["model"], "uncertainty.model")
        if not isinstance(value["parameters"], Mapping):
            raise ValidationError("uncertainty.parameters must be a map")
        if "basis" in value:
            _require_list(value["basis"], "uncertainty.basis")
    elif kind == "action":
        _nonempty_text(value["capability"], "action.capability")
        if not isinstance(value["arguments"], (Mapping, list)):
            raise ValidationError("action.arguments must be a map or list")
        if "declared_effects" in value:
            effects = _require_list(value["declared_effects"], "action.declared_effects")
            if not all(type(item) is str and item for item in effects):
                raise ValidationError("action.declared_effects must contain non-empty strings")
    elif kind == "commitment":
        _nonempty_text(value["debtor"], "commitment.debtor")
        creditors = _require_list(value["creditors"], "commitment.creditors", nonempty=True)
        if not all(type(item) is str and item for item in creditors):
            raise ValidationError("commitment.creditors must contain non-empty strings")
        if len(set(creditors)) != len(creditors):
            raise ValidationError("commitment.creditors must be unique")
        if not isinstance(value["goal"], Mapping) or value["goal"].get("kind") != "goal":
            raise ValidationError("commitment.goal must be a goal node")
        if type(value["expiry_ms"]) is not int or not 0 <= value["expiry_ms"] <= (1 << 64) - 1:
            raise ValidationError("commitment.expiry_ms must be a uint64")
        if "verifier" in value:
            _nonempty_text(value["verifier"], "commitment.verifier")
    elif kind == "resolution":
        if type(value["status"]) is not str or value["status"] not in RESOLUTION_STATUSES:
            raise ValidationError("resolution.status is not recognized")
        if "evidence" in value and not isinstance(value["evidence"], (Mapping, list)):
            raise ValidationError("resolution.evidence must be a semantic node or list")
    elif kind == "ref":
        _identifier(value["uri"], "ref.uri")
    elif kind == "question-plus-answer-schema":
        question = value["question"]
        if not isinstance(question, Mapping) or type(question.get("kind")) is not str:
            raise ValidationError(
                "question-plus-answer-schema.question must be a semantic node"
            )
        _identifier(
            value["answer_schema"],
            "question-plus-answer-schema.answer_schema",
        )
        if "constraints" in value:
            constraints = _require_list(
                value["constraints"], "question-plus-answer-schema.constraints"
            )
            if any(
                not isinstance(item, Mapping) or item.get("kind") != "constraint"
                for item in constraints
            ):
                raise ValidationError(
                    "question-plus-answer-schema.constraints must contain constraint nodes"
                )


def _normalize_tree(
    value: Any,
    *,
    depth: int = 0,
    budget: SemanticNodeBudget | None = None,
) -> Any:
    if depth > MAX_DEPTH:
        raise ValidationError(f"semantic tree exceeds maximum depth {MAX_DEPTH}")
    if budget is None:
        budget = SemanticNodeBudget()
    budget.consume(ValidationError)
    if value is None or type(value) in (bool, str, bytes):
        if isinstance(value, str) and len(_utf8_bytes(value, "string")) > MAX_STRING_BYTES:
            raise ValidationError("string exceeds size limit")
        return value
    if type(value) is int:
        if not -(1 << 63) <= value <= (1 << 64) - 1:
            raise ValidationError("integer exceeds 64-bit Urusilla range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationError("NaN and infinity are not allowed")
        return 0.0 if value == 0.0 else value
    if type(value) is tuple:
        raise ValidationError("tuples are not canonical semantic values; use a list")
    if type(value) is list:
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValidationError("list exceeds size limit")
        budget.require_minimum_children(len(value), ValidationError)
        return [
            _normalize_tree(item, depth=depth + 1, budget=budget) for item in value
        ]
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValidationError("map exceeds size limit")
        budget.require_minimum_children(len(value), ValidationError)
        if not all(type(key) is str for key in value):
            raise ValidationError("all semantic map keys must be strings")
        kind = value.get("kind")
        if kind is not None:
            if type(kind) is not str:
                raise ValidationError("node kind must be a string")
            if kind in CORE_KINDS:
                missing = [key for key in CORE_KINDS[kind] if key not in value]
                if missing:
                    raise ValidationError(
                        f"{kind} node is missing required field(s): {', '.join(missing)}"
                    )
            elif not kind.startswith("x:") or len(kind) == 2 or any(
                character.isspace() for character in kind
            ):
                raise ValidationError(
                    f"unknown node kind {kind!r}; local prototype extensions require x:<name>"
                )
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if len(_utf8_bytes(key, "map key")) > MAX_STRING_BYTES:
                raise ValidationError("map key exceeds size limit")
            normalized[key] = _normalize_tree(
                item, depth=depth + 1, budget=budget
            )
        if kind in CORE_KINDS:
            _validate_known_node(normalized, kind)
        return normalized
    raise ValidationError(f"unsupported semantic value type: {type(value).__name__}")


def _extension_kinds(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, list):
        for item in value:
            result.update(_extension_kinds(item))
    elif isinstance(value, Mapping):
        kind = value.get("kind")
        if type(kind) is str and kind.startswith("x:"):
            result.add(kind)
        for item in value.values():
            result.update(_extension_kinds(item))
    return result


def _declared_effects(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, list):
        for item in value:
            result.update(_declared_effects(item))
    elif isinstance(value, Mapping):
        effects = value.get("declared_effects")
        if type(effects) is list:
            result.update(item for item in effects if type(item) is str)
        for item in value.values():
            result.update(_declared_effects(item))
    return result


def normalize_message(message: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return the canonical in-memory form."""

    if not isinstance(message, Mapping):
        raise ValidationError("message must be a mapping")
    if not all(type(field) is str for field in message):
        raise ValidationError("all top-level field names must be strings")
    required = ("id", "session", "sender", "recipients", "act", "schema", "body")
    missing = [field for field in required if field not in message]
    if missing:
        raise ValidationError(f"missing top-level field(s): {', '.join(missing)}")

    unknown = sorted(set(message) - TOP_LEVEL_FIELDS)
    if unknown:
        raise ValidationError(
            f"unknown top-level field(s): {', '.join(unknown)}; place extensions under meta"
        )

    message_id = _canonical_uuid(message["id"], "id")
    session_id = _canonical_uuid(message["session"], "session")
    sender = _nonempty_text(message["sender"], "sender")

    recipients_raw = message["recipients"]
    if type(recipients_raw) is not list:
        raise ValidationError(
            "recipients must be a non-empty sequence represented as a canonical list"
        )
    recipients = list(recipients_raw)
    if len(recipients) > MAX_COLLECTION_ITEMS:
        raise ValidationError("recipients exceed the collection-item limit")
    if not recipients or not all(type(item) is str and item for item in recipients):
        raise ValidationError("recipients must contain non-empty strings")
    recipients = [_nonempty_text(item, "recipient") for item in recipients]
    if len(set(recipients)) != len(recipients):
        raise ValidationError("recipients must be unique")

    if type(message["act"]) is not str:
        raise ValidationError("act must be a string")
    act = message["act"].upper()
    if act not in ACT_TO_CODE:
        raise ValidationError(f"unknown communicative act: {act!r}")

    reply_to = message.get("reply_to")
    if reply_to is not None:
        reply_to = _canonical_uuid(reply_to, "reply_to")
    if act in {"COMMIT", "RESOLVE", "RETRACT"} and reply_to is None:
        raise ValidationError(f"{act} requires reply_to for an observable state transition")

    schema = _identifier(message["schema"], "schema")

    logical_clock = message.get("logical_clock", 0)
    if type(logical_clock) is not int or not 0 <= logical_clock <= (1 << 64) - 1:
        raise ValidationError("logical_clock must be a uint64")

    expires_ms = message.get("expires_ms", 0)
    if type(expires_ms) is not int or not 0 <= expires_ms <= (1 << 64) - 1:
        raise ValidationError("expires_ms must be a uint64")

    confidence_ppm = message.get("confidence_ppm")
    if confidence_ppm is not None and (
        type(confidence_ppm) is not int or not 0 <= confidence_ppm <= 1_000_000
    ):
        raise ValidationError("confidence_ppm must be an integer from 0 to 1,000,000")

    expected_raw = message.get("expected", [])
    if type(expected_raw) is not list:
        raise ValidationError("expected must be a sequence of communicative acts")
    expected = []
    for item in expected_raw:
        if type(item) is not str:
            raise ValidationError("expected acts must be strings")
        name = item.upper()
        if name not in ACT_TO_CODE:
            raise ValidationError(f"unknown expected act: {name!r}")
        if name not in expected:
            expected.append(name)
    expected.sort(key=ACT_TO_CODE.__getitem__)

    semantic_budget = SemanticNodeBudget()
    body = _normalize_tree(message["body"], budget=semantic_budget)
    meta = message.get("meta", {})
    if not isinstance(meta, Mapping):
        raise ValidationError("meta must be a mapping")
    meta = _normalize_tree(meta, budget=semantic_budget)

    if not isinstance(body, Mapping):
        raise ValidationError("body must be a semantic node map")
    body_kind = body.get("kind")
    if act == "QUERY" and body_kind is None:
        allowed_query_fields = {"question", "answer_schema", "constraints", "annotations"}
        unknown_query = sorted(set(body) - allowed_query_fields)
        if unknown_query or "question" not in body or "answer_schema" not in body:
            raise ValidationError(
                "QUERY body without kind requires question and answer_schema only"
            )
        if not isinstance(body["question"], Mapping):
            raise ValidationError("QUERY question must be a semantic node")
        _identifier(body["answer_schema"], "QUERY answer_schema")
        raise ValidationError(
            "QUERY body must declare kind question-plus-answer-schema"
        )
    elif type(body_kind) is not str:
        raise ValidationError("body must declare a node kind")
    elif body_kind.startswith("x:"):
        if act != "ASSERT":
            raise ValidationError("prototype extension nodes are quarantined to ASSERT")
    elif body_kind not in ACT_BODY_KINDS[act]:
        raise ValidationError(f"{act} cannot carry a {body_kind} body")

    if act != "ASSERT" and _extension_kinds(body):
        raise ValidationError("prototype extension nodes are quarantined to ASSERT")

    if act == "COMMIT" and body["debtor"] != sender:
        raise ValidationError("COMMIT debtor must equal the declared sender")

    return {
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


def validate_effect_eligibility(
    message: Mapping[str, Any],
    *,
    authenticated_sender: str,
    authorized_schemas: Iterable[str],
    allowed_effects: Iterable[str] = (),
    registered_extension_kinds: Iterable[str] = (),
    conversation_check: Callable[[Mapping[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Apply deployment checks that cannot be established by wire content alone.

    Structural decoding never grants authority. Effectful acts additionally require
    an authenticated identity, an allow-listed schema, registered extensions and
    effects, and a caller-supplied conversation/ledger decision.
    """

    canonical = normalize_message(message)
    if canonical["sender"] != authenticated_sender:
        raise ValidationError("authenticated sender does not match the message sender")
    if canonical["schema"] not in set(authorized_schemas):
        raise ValidationError("schema is not authorized for this deployment")
    unknown_extensions = _extension_kinds(canonical["body"]) - set(
        registered_extension_kinds
    )
    if unknown_extensions:
        raise ValidationError(
            "unregistered extension kind(s): " + ", ".join(sorted(unknown_extensions))
        )
    unauthorized_effects = _declared_effects(canonical["body"]) - set(allowed_effects)
    if unauthorized_effects:
        raise ValidationError(
            "unauthorized declared effect(s): " + ", ".join(sorted(unauthorized_effects))
        )
    if canonical["act"] in EFFECTFUL_ACTS:
        if conversation_check is None:
            raise ValidationError("effectful acts require a conversation-state validator")
        if not conversation_check(canonical):
            raise ValidationError("conversation-state validator rejected the transition")
    return canonical


def _collect_strings(value: Any, counts: Counter[str]) -> None:
    if type(value) is str:
        counts[value] += 1
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_strings(item, counts)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            counts[key] += 1
            _collect_strings(item, counts)


def _build_dictionary(message: Mapping[str, Any]) -> tuple[list[str], dict[str, int]]:
    counts: Counter[str] = Counter()
    counts[message["sender"]] += 1
    counts[message["schema"]] += 1
    for recipient in message["recipients"]:
        counts[recipient] += 1
    _collect_strings(message["body"], counts)
    _collect_strings(message["meta"], counts)
    strings = sorted(
        counts,
        key=lambda item: (-counts[item], len(item.encode("utf-8")), item.encode("utf-8")),
    )
    if len(strings) > MAX_DICTIONARY_ITEMS:
        raise ValidationError("dictionary exceeds size limit")
    return strings, {item: index for index, item in enumerate(strings)}


# Generic semantic value tags.
_NULL = 0
_FALSE = 1
_TRUE = 2
_UINT = 3
_SINT = 4
_FLOAT64 = 5
_STRING_REF = 6
_BYTES = 7
_LIST = 8
_MAP = 9


def _encode_value(value: Any, table: Mapping[str, int], *, depth: int = 0) -> bytes:
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
            value = 0.0  # Normalize negative zero.
        return bytes([_FLOAT64]) + struct.pack(">d", value)
    if type(value) is str:
        return bytes([_STRING_REF]) + _encode_uvarint(table[value])
    if type(value) is bytes:
        return bytes([_BYTES]) + _encode_uvarint(len(value)) + value
    if isinstance(value, (list, tuple)):
        out = bytearray([_LIST])
        out += _encode_uvarint(len(value))
        for item in value:
            out += _encode_value(item, table, depth=depth + 1)
        return bytes(out)
    if isinstance(value, Mapping):
        out = bytearray([_MAP])
        keys = sorted(value, key=lambda item: item.encode("utf-8"))
        out += _encode_uvarint(len(keys))
        for key in keys:
            out += _encode_uvarint(table[key])
            out += _encode_value(value[key], table, depth=depth + 1)
        return bytes(out)
    raise ValidationError(f"cannot encode {type(value).__name__}")


def _decode_value(
    reader: _Reader,
    strings: Sequence[str],
    *,
    depth: int = 0,
    budget: SemanticNodeBudget | None = None,
) -> Any:
    if depth > MAX_DEPTH:
        raise DecodeError("semantic tree exceeds depth limit")
    if budget is None:
        budget = SemanticNodeBudget()
    tag = reader.byte()
    budget.consume(DecodeError)
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
        if not math.isfinite(value) or math.copysign(1.0, value) < 0 and value == 0.0:
            raise DecodeError("non-canonical float")
        return value
    if tag == _STRING_REF:
        index = reader.uvarint()
        if index >= len(strings):
            raise DecodeError("string reference is out of range")
        return strings[index]
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
            _decode_value(reader, strings, depth=depth + 1, budget=budget)
            for _ in range(count)
        ]
    if tag == _MAP:
        count = reader.uvarint()
        if count > MAX_COLLECTION_ITEMS:
            raise DecodeError("map exceeds size limit")
        budget.require_minimum_children(count, DecodeError)
        result: dict[str, Any] = {}
        previous_key: bytes | None = None
        for _ in range(count):
            index = reader.uvarint()
            if index >= len(strings):
                raise DecodeError("map key reference is out of range")
            key = strings[index]
            encoded_key = key.encode("utf-8")
            if previous_key is not None and encoded_key <= previous_key:
                raise DecodeError("map keys are duplicate or non-canonical")
            previous_key = encoded_key
            result[key] = _decode_value(
                reader, strings, depth=depth + 1, budget=budget
            )
        return result
    raise DecodeError(f"unknown semantic value tag: {tag}")


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Encode a valid Urusilla message into canonical UrusillaWire bytes."""

    canonical = normalize_message(message)
    strings, table = _build_dictionary(canonical)
    payload = bytearray()
    payload += _encode_uvarint(len(strings))
    for item in strings:
        raw = item.encode("utf-8")
        payload += _encode_uvarint(len(raw))
        payload += raw

    payload += _uuid_bytes(canonical["id"], "id")
    payload += _uuid_bytes(canonical["session"], "session")
    payload += _encode_uvarint(table[canonical["sender"]])
    payload += _encode_uvarint(len(canonical["recipients"]))
    for recipient in canonical["recipients"]:
        payload += _encode_uvarint(table[recipient])
    payload.append(ACT_TO_CODE[canonical["act"]])

    reply_to = canonical["reply_to"]
    payload.append(1 if reply_to is not None else 0)
    if reply_to is not None:
        payload += _uuid_bytes(reply_to, "reply_to")
    payload += _encode_uvarint(table[canonical["schema"]])
    payload += _encode_uvarint(canonical["logical_clock"])
    payload += _encode_uvarint(canonical["expires_ms"])

    confidence = canonical["confidence_ppm"]
    payload += _encode_uvarint(0 if confidence is None else confidence + 1)
    expected_mask = 0
    for act in canonical["expected"]:
        expected_mask |= 1 << ACT_TO_CODE[act]
    payload.append(expected_mask)
    payload += _encode_value(canonical["body"], table)
    payload += _encode_value(canonical["meta"], table)

    header = MAGIC + bytes([FLAGS]) + _encode_uvarint(len(payload))
    checksum = hashlib.sha256(header + payload).digest()[:CHECKSUM_SIZE]
    frame = header + payload + checksum
    if len(frame) > MAX_FRAME_BYTES:
        raise ValidationError("encoded frame exceeds size limit")
    return frame


def decode_message(frame: bytes) -> dict[str, Any]:
    """Validate and decode canonical UrusillaWire bytes."""

    if not isinstance(frame, bytes):
        raise DecodeError("frame must be bytes")
    if len(frame) > MAX_FRAME_BYTES:
        raise DecodeError("frame exceeds size limit")
    reader = _Reader(frame)
    if reader.read(len(MAGIC)) != MAGIC:
        raise DecodeError("unsupported magic or UrusillaWire version")
    flags = reader.byte()
    if flags != FLAGS:
        raise DecodeError(f"unsupported or non-canonical flags: 0x{flags:02x}")
    payload_length = reader.uvarint()
    if payload_length > MAX_FRAME_BYTES:
        raise DecodeError("declared payload exceeds size limit")
    header_length = reader.pos
    if reader.remaining != payload_length + CHECKSUM_SIZE:
        raise DecodeError("payload length does not match frame length")
    payload = reader.read(payload_length)
    checksum = reader.read(CHECKSUM_SIZE)
    reader.expect_end()
    expected_checksum = hashlib.sha256(frame[:header_length] + payload).digest()[
        :CHECKSUM_SIZE
    ]
    if not hmac.compare_digest(checksum, expected_checksum):
        raise DecodeError("checksum mismatch")

    payload_reader = _Reader(payload)
    dictionary_count = payload_reader.uvarint()
    if dictionary_count > MAX_DICTIONARY_ITEMS:
        raise DecodeError("dictionary exceeds size limit")
    strings: list[str] = []
    seen_strings: set[str] = set()
    for _ in range(dictionary_count):
        size = payload_reader.uvarint()
        if size > MAX_STRING_BYTES:
            raise DecodeError("dictionary string exceeds size limit")
        raw = payload_reader.read(size)
        try:
            item = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise DecodeError("dictionary contains invalid UTF-8") from exc
        if item in seen_strings:
            raise DecodeError("dictionary contains a duplicate string")
        seen_strings.add(item)
        strings.append(item)

    message_id = _uuid_text(payload_reader.read(16))
    session_id = _uuid_text(payload_reader.read(16))
    sender_index = payload_reader.uvarint()
    if sender_index >= len(strings):
        raise DecodeError("sender string reference is out of range")
    sender = strings[sender_index]

    recipient_count = payload_reader.uvarint()
    if not 1 <= recipient_count <= MAX_COLLECTION_ITEMS:
        raise DecodeError("recipient count is invalid")
    recipients = []
    for _ in range(recipient_count):
        index = payload_reader.uvarint()
        if index >= len(strings):
            raise DecodeError("recipient string reference is out of range")
        recipients.append(strings[index])

    act_code = payload_reader.byte()
    if act_code >= len(ACTS):
        raise DecodeError("unknown communicative act code")
    act = ACTS[act_code]

    has_reply = payload_reader.byte()
    if has_reply not in (0, 1):
        raise DecodeError("invalid reply_to presence flag")
    reply_to = _uuid_text(payload_reader.read(16)) if has_reply else None

    schema_index = payload_reader.uvarint()
    if schema_index >= len(strings):
        raise DecodeError("schema string reference is out of range")
    schema = strings[schema_index]
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
    semantic_budget = SemanticNodeBudget()
    body = _decode_value(payload_reader, strings, budget=semantic_budget)
    meta = _decode_value(payload_reader, strings, budget=semantic_budget)
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
    canonical = normalize_message(decoded)
    if encode_message(canonical) != frame:
        raise DecodeError("frame is valid but not canonical")
    return canonical


def _atom(value: Any) -> str:
    if value is None:
        return "∅"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _render_value(value: Any, lang: str) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_render_value(item, lang) for item in value) + "]"
    if not isinstance(value, Mapping):
        return _atom(value)

    kind = value.get("kind")
    if kind == "ref":
        return ("참조" if lang == "ko" else "ref") + f"({_atom(value['uri'])})"
    if kind == "action":
        args = _render_value(value.get("arguments", {}), lang)
        if lang == "ko":
            return f"행동 {_atom(value['capability'])}(인자={args})"
        return f"action {_atom(value['capability'])}(arguments={args})"
    if kind == "claim":
        args = _render_value(value.get("arguments", []), lang)
        if lang == "ko":
            return f"주장 {_atom(value['predicate'])}(인자={args})"
        return f"claim {_atom(value['predicate'])}(arguments={args})"
    if kind == "goal":
        condition = _render_value(value["condition"], lang)
        constraints = _render_value(value.get("constraints", []), lang)
        if lang == "ko":
            return f"목표(성공 조건={condition}, 제약={constraints})"
        return f"goal(success_condition={condition}, constraints={constraints})"
    if kind == "constraint":
        scope = _render_value(value["scope"], lang)
        condition = _render_value(value["condition"], lang)
        mode = _atom(value["mode"])
        if lang == "ko":
            return f"제약(범위={scope}, 모드={mode}, 조건={condition})"
        return f"constraint(scope={scope}, mode={mode}, condition={condition})"
    if kind == "evidence":
        if lang == "ko":
            return (
                f"증거(대상={_render_value(value['target'], lang)}, "
                f"입장={_atom(value['stance'])}, 해시={_atom(value['digest'])}, "
                f"출처={_atom(value['provenance'])})"
            )
        return (
            f"evidence(target={_render_value(value['target'], lang)}, "
            f"stance={_atom(value['stance'])}, digest={_atom(value['digest'])}, "
            f"provenance={_atom(value['provenance'])})"
        )
    if kind == "uncertainty":
        if lang == "ko":
            return (
                f"불확실성(대상={_render_value(value['target'], lang)}, "
                f"모델={_atom(value['model'])}, 값={_render_value(value['parameters'], lang)})"
            )
        return (
            f"uncertainty(target={_render_value(value['target'], lang)}, "
            f"model={_atom(value['model'])}, parameters={_render_value(value['parameters'], lang)})"
        )
    if kind == "commitment":
        creditors = _render_value(value["creditors"], lang)
        goal = _render_value(value["goal"], lang)
        if lang == "ko":
            return (
                f"공개 약정(의무자={_atom(value['debtor'])}, 권리자={creditors}, "
                f"목표={goal}, 만료={value['expiry_ms']}ms)"
            )
        return (
            f"public commitment(debtor={_atom(value['debtor'])}, creditors={creditors}, "
            f"goal={goal}, expires={value['expiry_ms']}ms)"
        )
    if kind == "resolution":
        result = _render_value(value.get("result"), lang)
        if lang == "ko":
            return (
                f"판정(대상={_render_value(value['target'], lang)}, "
                f"상태={_atom(value['status'])}, 결과={result})"
            )
        return (
            f"resolution(target={_render_value(value['target'], lang)}, "
            f"status={_atom(value['status'])}, result={result})"
        )

    rendered = ", ".join(
        f"{key}={_render_value(value[key], lang)}"
        for key in sorted(value, key=lambda item: item.encode("utf-8"))
    )
    if kind and kind not in CORE_KINDS:
        prefix = "알 수 없는 확장" if lang == "ko" else "unknown extension"
        return f"{prefix}<{kind}>({rendered})"
    return "{" + rendered + "}"


_KO_ACT = {
    "ASSERT": "공유 기록에 명제를 주장해 추가했습니다. 진실 여부는 별도 검증 대상입니다.",
    "QUERY": "타입이 지정된 답을 요청하는 질의를 열었습니다.",
    "REQUEST": "목표 수행을 요청했습니다. 이 메시지만으로 의무는 생기지 않습니다.",
    "PROPOSE": "계획 또는 조건부 약정을 잠정 제안했습니다.",
    "COMMIT": "참조된 제안·요청에 대해 공개적 의무를 활성화했습니다.",
    "RESOLVE": "참조된 항목의 상태나 결과를 권한 있는 판정으로 기록했습니다.",
    "RETRACT": "자신이 만든 철회 가능 항목에 삭제가 아닌 철회 기록을 추가했습니다.",
}

_EN_ACT = {
    "ASSERT": "added a claim to the shared record; truth still requires verification.",
    "QUERY": "opened a query requesting an answer of a declared type.",
    "REQUEST": "requested a goal; this message alone creates no obligation.",
    "PROPOSE": "tentatively proposed a plan or conditional commitment.",
    "COMMIT": "activated a public obligation referring to a prior request or proposal.",
    "RESOLVE": "recorded an authorized resolution or result for a referenced item.",
    "RETRACT": "appended a retraction marker without deleting the original record.",
}


def _translator_build_digest() -> str:
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return "unavailable"


def translate_message(
    message: Mapping[str, Any],
    lang: str = "ko",
    *,
    source_verification: str = "unverified",
    authorization_state: str = "not-evaluated",
) -> str:
    """Render a readable summary followed by a complete canonical audit record."""

    canonical = normalize_message(message)
    if lang not in {"ko", "en"}:
        raise ValidationError("translator locale must be 'ko' or 'en'")
    recipients = ", ".join(canonical["recipients"])
    expected = ", ".join(canonical["expected"]) or "∅"
    confidence = canonical["confidence_ppm"]
    confidence_text = "unspecified" if confidence is None else f"{confidence / 10_000:.2f}%"
    body = _render_value(canonical["body"], lang)
    frame_digest = hashlib.sha256(encode_message(canonical)).hexdigest()
    canonical_json = json.dumps(
        _json_ready(canonical),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    build_digest = _translator_build_digest()
    if lang == "ko":
        lines = [
            "읽기 쉬운 요약입니다. 승인에는 아래의 완전한 정규 감사 기록을 사용해야 합니다.",
            f"[{canonical['act']}] {canonical['sender']} → {recipients}",
            _KO_ACT[canonical["act"]],
            f"의미 내용: {body}",
            f"스키마: {canonical['schema']}",
            f"예상 응답: {expected}; 명시 신뢰도: {confidence_text}",
            f"메시지 ID: {canonical['id']}; 세션: {canonical['session']}",
            f"논리 시계: {canonical['logical_clock']}; 만료 밀리초: {canonical['expires_ms']}",
        ]
    else:
        lines = [
            "Readable summary only; use the complete canonical audit record below for approval.",
            f"[{canonical['act']}] {canonical['sender']} → {recipients}",
            f"The sender {_EN_ACT[canonical['act']]}",
            f"Semantic content: {body}",
            f"Schema: {canonical['schema']}",
            f"Expected reply: {expected}; declared confidence: {confidence_text}",
            f"Message ID: {canonical['id']}; session: {canonical['session']}",
            f"Logical clock: {canonical['logical_clock']}; expiry milliseconds: {canonical['expires_ms']}",
        ]
    if canonical["reply_to"]:
        label = "참조 메시지" if lang == "ko" else "Referenced message"
        lines.append(f"{label}: {canonical['reply_to']}")
    if lang == "ko":
        lines.extend(
            [
                f"정규 메시지 SHA-256: {frame_digest}",
                f"번역기 빌드 SHA-256: {build_digest}",
                f"스키마 검증: 선언만 됨; 출처 검증: {source_verification}; 권한 상태: {authorization_state}",
                f"완전한 정규 IR: {canonical_json}",
            ]
        )
    else:
        lines.extend(
            [
                f"Canonical message SHA-256: {frame_digest}",
                f"Translator build SHA-256: {build_digest}",
                "Schema verification: declared-only; "
                f"source verification: {source_verification}; authorization: {authorization_state}",
                f"Complete canonical IR: {canonical_json}",
            ]
        )
    return "\n".join(lines)


def demo_message() -> dict[str, Any]:
    return {
        "id": "018f4f2e-1d33-7b62-8af8-5a09497d34b1",
        "session": "018f4f2e-0ea2-7cad-a224-b98558052765",
        "sender": "planner.agent",
        "recipients": ["verifier.agent"],
        "act": "REQUEST",
        "schema": "urn:urusilla:proof-verification:1",
        "logical_clock": 17,
        "expires_ms": 1_500,
        "confidence_ppm": 930_000,
        "expected": ["COMMIT", "RESOLVE"],
        "body": {
            "kind": "goal",
            "condition": {
                "kind": "claim",
                "predicate": "proof.valid",
                "arguments": [
                    {"kind": "ref", "uri": "sha256:aa04e9d98f45"},
                    "theorem-42",
                ],
            },
            "constraints": [
                {
                    "kind": "constraint",
                    "scope": "verification",
                    "mode": "hard",
                    "condition": {"latency_ms_lte": 1_500},
                },
                {
                    "kind": "constraint",
                    "scope": "output",
                    "mode": "hard",
                    "condition": {"must_include": ["evidence_digest", "counterexample"]},
                },
            ],
        },
        "meta": {
            "budget": {"output_units": 120, "wire_bytes": 2_048},
            "provenance": ["planner.run:881"],
        },
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$bytes_hex": value.hex()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _load_json(path: Path) -> Any:
    def reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"duplicate JSON member: {key}")
            result[key] = value
        return result

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=reject_duplicate_members)
    except ValidationError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_json_ready(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _command_demo(args: argparse.Namespace) -> None:
    message = demo_message()
    frame = encode_message(message)
    decoded = decode_message(frame)
    json_size = len(
        json.dumps(normalize_message(message), ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    print("UrusillaWire hex:")
    print(frame.hex())
    print()
    print(translate_message(decoded, args.lang))
    print()
    print(f"UrusillaWire bytes: {len(frame)}")
    print(f"Canonical minified JSON bytes: {json_size}")
    print(f"Wire/JSON ratio: {len(frame) / json_size:.3f}")


def _command_encode(args: argparse.Namespace) -> None:
    message = _load_json(args.input)
    frame = encode_message(message)
    args.output.write_bytes(frame)
    print(f"wrote {len(frame)} bytes to {args.output}")


def _command_decode(args: argparse.Namespace) -> None:
    message = decode_message(args.input.read_bytes())
    if args.output:
        _write_json(args.output, message)
        print(f"wrote diagnostic JSON to {args.output}")
    else:
        print(json.dumps(_json_ready(message), ensure_ascii=False, indent=2, sort_keys=True))


def _command_translate(args: argparse.Namespace) -> None:
    message = decode_message(args.input.read_bytes())
    print(translate_message(message, args.lang))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Urusilla v0.1 reference codec and translator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run the built-in proof-of-concept message")
    demo.add_argument("--lang", choices=("ko", "en"), default="ko")
    demo.set_defaults(func=_command_demo)

    encode = subparsers.add_parser("encode", help="encode diagnostic JSON to UrusillaWire")
    encode.add_argument("input", type=Path)
    encode.add_argument("output", type=Path)
    encode.set_defaults(func=_command_encode)

    decode = subparsers.add_parser("decode", help="decode UrusillaWire to diagnostic JSON")
    decode.add_argument("input", type=Path)
    decode.add_argument("--output", type=Path)
    decode.set_defaults(func=_command_decode)

    translate = subparsers.add_parser("translate", help="translate UrusillaWire for a human")
    translate.add_argument("input", type=Path)
    translate.add_argument("--lang", choices=("ko", "en"), default="ko")
    translate.set_defaults(func=_command_translate)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        args.func(args)
    except UrusillaError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
