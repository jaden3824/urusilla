#!/usr/bin/env python3
"""Small live receiver-comprehension pilot for three exact text formats.

The live gate uses the official OpenAI Responses API with ``store=false`` and
JSON-schema Structured Outputs.  It compares sorted minified JSON, Controlled
Terse English, and a compact symbolic surface designed to remain directly
readable by language models.  Raw API responses and response identifiers are
not persisted.  The API key is read only by the HTTPS transport and is never
printed or stored.

This pilot measures prompted batch reconstruction only.  It does not measure
sender generation, autonomous task success, multi-turn repair, cross-vendor
transfer, latent communication, or state-of-the-art performance.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Temporary imports from frozen research fixtures and the shared validator.
from urusilla_benchmark import corpus_digest, json_encode
from urusilla import DecodeError, ValidationError, normalize_message
from urusilla_token_surface_holdout import (
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_SHA256,
    _sequence_digest,
    build_out_of_domain_corpus,
    frozen_split,
)
from urusilla_terse_english_benchmark import encode_terse_english


FORMAT = "urusilla-model-comprehension-pilot-v1"
REPORT_NAME = "MODEL_COMPREHENSION_PILOT_RESULTS.md"
API_URL = "https://api.openai.com/v1/responses"
USD_CEILING = 1.0
REPEATS = 2
LIVE_BATCH_SIZE = 2
MAX_OUTPUT_TOKENS = 4_000
GATE_MIN_EXACT_MESSAGES = 14
SYMBOLIC_PREFIX = "@1"
SYMBOLIC_CHECKSUM_CHARACTERS = 11
SYMBOLIC_HEADER_CHARACTERS = len(SYMBOLIC_PREFIX) + SYMBOLIC_CHECKSUM_CHARACTERS + 1
_SYMBOLIC_DOMAIN = b"UrusillaModelReadable-v1\x00"
_CHECKSUM_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}\Z")

ACTS = ("ASSERT", "QUERY", "REQUEST", "PROPOSE", "COMMIT", "RESOLVE", "RETRACT")
FORMATS = ("json", "terse_english", "symbolic")
FORMAT_LABELS = {
    "json": "sorted minified JSON",
    "terse_english": "Controlled Terse English",
    "symbolic": "compact symbolic surface",
}
TOP_LEVEL_FIELDS = (
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
)
SYMBOLIC_FIELDS = (
    ("i", "id"),
    ("s", "session"),
    ("f", "sender"),
    ("t", "recipients"),
    ("a", "act"),
    ("r", "reply_to"),
    ("y", "schema"),
    ("l", "logical_clock"),
    ("x", "expires_ms"),
    ("c", "confidence_ppm"),
    ("e", "expected"),
    ("b", "body"),
    ("m", "meta"),
)

# Current post-cutover offline inputs. These digests are intentionally distinct
# from the historical inputs used for the retained provider measurements below.
PILOT_CORPUS_SHA256 = "f80d6f1483fba62aad006e6c45ade3f1a0f912ad7a714b94f7a6072a637b29c7"
SYMBOLIC_TEXT_SHA256 = "a820c137167afe669c9fb33d2366498f9894252f93a9cc17d37e72aa806a0f4b"
MEASURED_PILOT_CORPUS_SHA256 = "fde113bb8b89eb3e3135b8797b42667a63078657c035de8e286780a4575003ad"
MEASURED_SYMBOLIC_TEXT_SHA256 = "ab1f66decf8f24961c45b54eaeb602377b9b5fea0397a78eac9a72f291fe79c9"
PRE_AMENDMENT_RESERVED_USD = 0.15
PRE_AMENDMENT_OBSERVATIONS: Mapping[str, Any] = {
    "protocol": "single 14-message batch",
    "completed_trial_summaries": [
        {
            "model": "gpt-5-nano",
            "representation": "json",
            "repeat": 0,
            "exact_messages": 0,
            "messages": 14,
            "terminal_matches": 0,
            "terminal_total": 509,
            "total_tokens": 17_751,
            "latency_ms": 61_879.8,
            "status": "failed",
        },
        {
            "model": "gpt-5-nano",
            "representation": "json",
            "repeat": 1,
            "exact_messages": 9,
            "messages": 14,
            "terminal_matches": 373,
            "terminal_total": 509,
            "total_tokens": 17_408,
            "latency_ms": 56_865.3,
            "status": "failed",
        },
    ],
    "interrupted_in_flight_requests": 1,
    "interrupted_request": {
        "model": "gpt-5-nano",
        "representation": "terse_english",
        "repeat": 0,
        "outcome": "unknown",
    },
    "seven_message_batch_stage": {
        "batch_size": 7,
        "max_output_tokens": 12_000,
        "completed_trial_summaries": [
            {
                "model": "gpt-5-nano",
                "representation": "json",
                "repeat": 0,
                "exact_messages": 11,
                "messages": 14,
                "terminal_matches": 397,
                "terminal_total": 509,
                "total_tokens": 25_836,
                "latency_ms": 120_436.3,
                "status": "failed",
                "failure_code": "batch_0:semantic_json|batch_1:semantic_json",
            },
            {
                "model": "gpt-5-nano",
                "representation": "json",
                "repeat": 1,
                "exact_messages": 4,
                "messages": 14,
                "terminal_matches": 142,
                "terminal_total": 509,
                "total_tokens": 16_018,
                "latency_ms": 43_393.5,
                "status": "failed",
                "failure_code": "batch_0:semantic_json|batch_1:semantic_json",
            },
        ],
        "interrupted_in_flight_requests": 1,
        "interrupted_request": {
            "model": "gpt-5-nano",
            "representation": "terse_english",
            "repeat": 0,
            "outcome": "unknown",
        },
    },
    "diagnostic_probe": {
        "attempt": "diagnostic_primary",
        "batch_index": 0,
        "cached_input_tokens": 4_352,
        "canonical_strings": 0,
        "content_types": ["output_text"],
        "error_code": None,
        "error_type": None,
        "estimated_cost_usd": 0.00186655,
        "exact_messages": 0,
        "incomplete_reason": None,
        "input_tokens": 4_443,
        "messages": 14,
        "output_text_characters": 14_306,
        "output_text_items": 1,
        "output_text_sha256": "12f0364529105a861ec87539d2c473285136d7542280c806b128a1377b9c77f3",
        "output_tokens": 4_111,
        "output_types": ["reasoning", "message"],
        "parse_failure_code": "semantic_json",
        "reasoning_tokens": 0,
        "response_status": "completed",
        "store": False,
        "terminal_matches": 0,
        "terminal_total": 509,
        "total_tokens": 8_554,
        "transport": "completed",
    },
    "reserved_cost_upper_bound_usd": PRE_AMENDMENT_RESERVED_USD,
}

FROZEN_LIVE_RESULTS: Mapping[str, Any] = {
    "format": FORMAT,
    "run_utc": "2026-08-20T09:00:37.659471+00:00",
    "api": "official Responses API",
    "store": False,
    "models": ["gpt-5-nano", "gpt-4o-mini"],
    "representations": list(FORMATS),
    "repeats": 2,
    "messages": 14,
    "batch_size": 2,
    "batches_per_trial": 7,
    "max_output_tokens": 4_000,
    "api_attempts": 15,
    "acts": list(ACTS),
    "origins": {"grouped_holdout": 7, "out_of_domain": 7},
    "pilot_corpus_sha256": MEASURED_PILOT_CORPUS_SHA256,
    "symbolic_text_sha256": MEASURED_SYMBOLIC_TEXT_SHA256,
    "current_urusilla_pilot_corpus_sha256": PILOT_CORPUS_SHA256,
    "current_urusilla_symbolic_text_sha256": SYMBOLIC_TEXT_SHA256,
    "provider_rerun_after_urusilla_cutover": False,
    "preflight_worst_case_estimated_usd": 0.4062436,
    "actual_usage_estimated_usd": 0.0049753,
    "pre_amendment_reserved_usd": PRE_AMENDMENT_RESERVED_USD,
    "experiment_cost_upper_bound_usd": 0.1549753,
    "cost_ceiling_usd": USD_CEILING,
    "pre_amendment_observations": PRE_AMENDMENT_OBSERVATIONS,
    "gate": {
        "model": "gpt-5-nano",
        "representation": "json",
        "minimum_exact_messages_per_repeat": 14,
        "requires_zero_validator_failures": True,
        "passed": False,
        "matrix_continued": False,
    },
    "grammar": {
        "json": {"utf8_bytes": 140, "o200k_or_four_byte_proxy_tokens": 26},
        "terse_english": {
            "utf8_bytes": 423,
            "o200k_or_four_byte_proxy_tokens": 109,
        },
        "symbolic": {
            "utf8_bytes": 411,
            "o200k_or_four_byte_proxy_tokens": 112,
        },
    },
    "trials": [
        {
            "model": "gpt-5-nano",
            "representation": "json",
            "repeat": 0,
            "status": "failed",
            "exact_messages": 13,
            "validator_valid_messages": 13,
            "messages": 14,
            "terminal_matches": 475,
            "terminal_total": 509,
            "malformed_initial": 1,
            "repair_attempts": 1,
            "repair_failures": 1,
            "input_tokens": 12_193,
            "cached_input_tokens": 0,
            "output_tokens": 5_046,
            "reasoning_tokens": 0,
            "total_tokens": 17_239,
            "latency_ms": 39_025.341,
            "estimated_cost_usd": 0.00262805,
            "failure_code": "batch_1:semantic_message",
            "batch_count": 7,
            "batch_message_counts": [2, 2, 2, 2, 2, 2, 2],
            "validator_failure_counts": {
                "ValidationError/unknown/other": 1,
            },
            "attempt_diagnostics": [
                {
                    "attempt": "primary",
                    "batch_index": 1,
                    "transport": "completed",
                    "response_status": "completed",
                    "incomplete_reason": None,
                    "error_type": None,
                    "error_code": None,
                    "output_types": ["reasoning", "message"],
                    "content_types": ["output_text"],
                    "output_text_items": 1,
                    "output_text_characters": 1_730,
                    "output_text_sha256": "2149016667e77c34234d9e87b00344853fe275678c7694220602f972592e07d7",
                    "parse_failure_code": "semantic_message",
                    "validator_failure_counts": {
                        "ValidationError/unknown/other": 1,
                    },
                    "input_tokens": 1_334,
                    "cached_input_tokens": 0,
                    "output_tokens": 539,
                    "reasoning_tokens": 0,
                    "total_tokens": 1_873,
                },
                {
                    "attempt": "repair",
                    "batch_index": 1,
                    "transport": "completed",
                    "response_status": "completed",
                    "incomplete_reason": None,
                    "error_type": None,
                    "error_code": None,
                    "output_types": ["reasoning", "message"],
                    "content_types": ["output_text"],
                    "output_text_items": 1,
                    "output_text_characters": 1_722,
                    "output_text_sha256": "2b9d1e5b2a07fbed9da6e6c215be560a7b523e35af752ae6047345caa3dc0aec",
                    "parse_failure_code": "semantic_message",
                    "validator_failure_counts": {
                        "ValidationError/unknown/other": 1,
                    },
                    "input_tokens": 1_352,
                    "cached_input_tokens": 0,
                    "output_tokens": 538,
                    "reasoning_tokens": 0,
                    "total_tokens": 1_890,
                },
            ],
        },
        {
            "model": "gpt-5-nano",
            "representation": "json",
            "repeat": 1,
            "status": "completed",
            "exact_messages": 14,
            "validator_valid_messages": 14,
            "messages": 14,
            "terminal_matches": 509,
            "terminal_total": 509,
            "malformed_initial": 0,
            "repair_attempts": 0,
            "repair_failures": 0,
            "input_tokens": 10_841,
            "cached_input_tokens": 5_760,
            "output_tokens": 4_513,
            "reasoning_tokens": 0,
            "total_tokens": 15_354,
            "latency_ms": 39_533.962,
            "estimated_cost_usd": 0.00234725,
            "failure_code": None,
            "batch_count": 7,
            "batch_message_counts": [2, 2, 2, 2, 2, 2, 2],
            "validator_failure_counts": {},
            "attempt_diagnostics": [],
        },
    ],
}


@dataclass(frozen=True)
class ModelSpec:
    model: str
    input_usd_per_million: float
    output_usd_per_million: float


MODEL_SPECS = (
    ModelSpec("gpt-5-nano", 0.05, 0.40),
    ModelSpec("gpt-4o-mini", 0.15, 0.60),
)


@dataclass(frozen=True)
class PilotMessage:
    origin: str
    act: str
    message: Mapping[str, Any]


@dataclass(frozen=True)
class ParsedBatch:
    observed: tuple[Mapping[str, Any] | None, ...]
    validator_valid: tuple[bool, ...]
    malformed: bool
    failure_code: str | None
    validator_failure_categories: tuple[str, ...]


@dataclass(frozen=True)
class TrialResult:
    model: str
    representation: str
    repeat: int
    status: str
    exact_messages: int
    validator_valid_messages: int
    messages: int
    terminal_matches: int
    terminal_total: int
    malformed_initial: int
    repair_attempts: int
    repair_failures: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost_usd: float
    failure_code: str | None
    batch_count: int
    batch_message_counts: tuple[int, ...]
    attempt_diagnostics: tuple[Mapping[str, Any], ...]
    validator_failure_counts: Mapping[str, int]


Transport = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _symbolic_checksum(body: str) -> str:
    result = _b64url(
        hashlib.blake2s(
            _SYMBOLIC_DOMAIN + body.encode("utf-8"), digest_size=8
        ).digest()
    )
    if len(result) != SYMBOLIC_CHECKSUM_CHARACTERS:
        raise RuntimeError("symbolic checksum width changed")
    return result


def _symbolic_value(value: Any) -> str:
    return "~" if value is None else _canonical_json(value)


def encode_symbolic(message: Mapping[str, Any]) -> str:
    """Encode one canonical message with a short fixed, model-readable grammar."""

    canonical = normalize_message(message)
    body = "".join(
        label + _symbolic_value(canonical[field]) for label, field in SYMBOLIC_FIELDS
    )
    return SYMBOLIC_PREFIX + _symbolic_checksum(body) + ":" + body


class _SymbolicParser:
    def __init__(self, text: str):
        self.text = text
        self.position = 0
        self.decoder = json.JSONDecoder(
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
        )

    def literal(self, expected: str) -> None:
        if not self.text.startswith(expected, self.position):
            raise DecodeError(
                f"expected symbolic label {expected!r} at character {self.position}"
            )
        self.position += len(expected)

    def value(self) -> Any:
        if self.position >= len(self.text):
            raise DecodeError("truncated symbolic value")
        if self.text[self.position] == "~":
            self.position += 1
            return None
        try:
            value, end = self.decoder.raw_decode(self.text, self.position)
        except (json.JSONDecodeError, ValueError) as exc:
            raise DecodeError(
                f"invalid symbolic JSON value at character {self.position}"
            ) from exc
        self.position = end
        return value


def decode_symbolic(text: str) -> dict[str, Any]:
    """Verify, parse, validate, and canonically re-encode one symbolic message."""

    if not isinstance(text, str) or len(text) <= SYMBOLIC_HEADER_CHARACTERS:
        raise DecodeError("symbolic surface is not valid text")
    if not text.startswith(SYMBOLIC_PREFIX):
        raise DecodeError("unknown symbolic surface prefix")
    supplied = text[len(SYMBOLIC_PREFIX) : len(SYMBOLIC_PREFIX) + SYMBOLIC_CHECKSUM_CHARACTERS]
    if _CHECKSUM_PATTERN.fullmatch(supplied) is None:
        raise DecodeError("symbolic checksum text is malformed")
    separator = len(SYMBOLIC_PREFIX) + SYMBOLIC_CHECKSUM_CHARACTERS
    if text[separator] != ":":
        raise DecodeError("symbolic checksum separator is missing")
    body = text[separator + 1 :]
    if not hmac.compare_digest(supplied, _symbolic_checksum(body)):
        raise DecodeError("symbolic checksum mismatch")

    parser = _SymbolicParser(body)
    result: dict[str, Any] = {}
    for label, field in SYMBOLIC_FIELDS:
        parser.literal(label)
        result[field] = parser.value()
    if parser.position != len(body):
        raise DecodeError("symbolic surface has trailing data")
    try:
        canonical = normalize_message(result)
    except ValidationError as exc:
        raise DecodeError(str(exc)) from exc
    if encode_symbolic(canonical) != text:
        raise DecodeError("symbolic surface is valid but not canonical")
    return canonical


def select_pilot_messages() -> tuple[PilotMessage, ...]:
    """Select one grouped-holdout and one OOD example for every core act."""

    split = frozen_split()
    ood = build_out_of_domain_corpus()
    if corpus_digest(split.holdout) != EXPECTED_HOLDOUT_SHA256:
        raise RuntimeError("grouped holdout changed")
    if corpus_digest(ood) != EXPECTED_OOD_SHA256:
        raise RuntimeError("out-of-domain corpus changed")

    result: list[PilotMessage] = []
    for act in ACTS:
        grouped = min(
            (message for message in split.holdout if message["act"] == act),
            key=lambda message: message["id"],
        )
        external = min(
            (message for message in ood if message["act"] == act),
            key=lambda message: message["id"],
        )
        result.append(PilotMessage("grouped_holdout", act, grouped))
        result.append(PilotMessage("out_of_domain", act, external))
    digest = corpus_digest([item.message for item in result])
    if PILOT_CORPUS_SHA256 != "pending" and digest != PILOT_CORPUS_SHA256:
        raise RuntimeError("pilot corpus digest changed")
    return tuple(result)


def encode_representation(message: Mapping[str, Any], representation: str) -> str:
    if representation == "json":
        return json_encode(message).decode("utf-8")
    if representation == "terse_english":
        return encode_terse_english(message)
    if representation == "symbolic":
        return encode_symbolic(message)
    raise ValueError(f"unknown representation {representation}")


COMMON_INSTRUCTIONS = """You are a protocol receiver in a controlled experiment. Decode every numbered input record exactly; never infer, repair, summarize, or omit data. Return one output item per input index in the original order. Each message value must be the complete typed semantic message with all 13 top-level fields. Preserve strings, numbers, booleans, nulls, list order, nested keys, and empty containers exactly. Do not add commentary."""

GRAMMARS = {
    "json": """Input grammar: each numbered payload is one sorted minified JSON object. Read it directly and return the same complete typed message object.""",
    "terse_english": """Input grammar: `ACT from SENDER to RECIPIENTS: BODY; id ID, session SESSION, reply REPLY, schema SCHEMA, clock UINT, expires UINTms, confidence UINTppm|unknown, expect ACTS, meta META.` `none` means null reply; `unknown` means null confidence. Values use: null/true/false, JSON numbers, JSON-quoted strings, safe bare strings, lists `[v,...]`, and maps `{key=v,...}`. Map equals signs are field separators, not comparisons.""",
    "symbolic": """Input grammar: `@1CHECKSUM:iID sSESSION fSENDER tRECIPIENTS aACT rREPLY ySCHEMA lCLOCK xEXPIRES cCONFIDENCE eEXPECTED bBODY mMETA`, with no spaces between labeled fields. Actual labels are the single letters `i,s,f,t,a,r,y,l,x,c,e,b,m` in that fixed order. Every value is canonical JSON except `~` means null. CHECKSUM is 11 Base64url characters and is integrity data only; ignore it when reconstructing fields.""",
}


def _schema_union(schemas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    unique: dict[str, Mapping[str, Any]] = {}
    for schema in schemas:
        unique[_canonical_json(schema)] = schema
    ordered = [unique[key] for key in sorted(unique)]
    return dict(ordered[0]) if len(ordered) == 1 else {"anyOf": ordered}


def _typed_shape_schema(value: Any) -> dict[str, Any]:
    """Infer a strict value-type/shape schema without embedding terminal values."""

    if value is None:
        return {"type": "null"}
    if type(value) is bool:
        return {"type": "boolean"}
    if type(value) is int:
        return {"type": "integer"}
    if type(value) is float:
        return {"type": "number"}
    if type(value) is str:
        return {"type": "string"}
    if type(value) is list:
        item_schema = (
            _schema_union([_typed_shape_schema(item) for item in value])
            if value
            else {"type": "string"}
        )
        return {
            "type": "array",
            "items": item_schema,
            "minItems": len(value),
            "maxItems": len(value),
        }
    if isinstance(value, Mapping):
        properties = {
            key: _typed_shape_schema(value[key])
            for key in sorted(value, key=lambda item: item.encode("utf-8"))
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        }
    raise TypeError(f"unsupported schema value type {type(value).__name__}")


def build_output_schema(messages: Sequence[PilotMessage]) -> dict[str, Any]:
    branches = []
    for index, item in enumerate(messages):
        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "message"],
                "properties": {
                    "index": {"type": "integer", "enum": [index]},
                    "message": _typed_shape_schema(item.message),
                },
            }
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["messages"],
        "properties": {
            "messages": {
                "type": "array",
                "minItems": len(messages),
                "maxItems": len(messages),
                "items": _schema_union(branches),
            }
        },
    }


def build_prompt(messages: Sequence[PilotMessage], representation: str, *, repair: bool = False) -> str:
    grammar = GRAMMARS[representation]
    records = "\n".join(
        f"{index}\t{encode_representation(item.message, representation)}"
        for index, item in enumerate(messages)
    )
    repair_note = (
        "\nA prior response was malformed. Re-read the same records and satisfy the output schema exactly."
        if repair
        else ""
    )
    return f"{grammar}{repair_note}\n\nRECORDS\n{records}"


def build_request(
    model: str,
    messages: Sequence[PilotMessage],
    representation: str,
    *,
    repair: bool = False,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model,
        "instructions": COMMON_INSTRUCTIONS,
        "input": build_prompt(messages, representation, repair=repair),
        "store": False,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "reconstructed_messages",
                "strict": True,
                "schema": build_output_schema(messages),
            }
        },
    }
    if model == "gpt-5-nano":
        request["reasoning"] = {"effort": "minimal"}
    elif model == "gpt-4o-mini":
        request["temperature"] = 0
    return request


def _model_spec(model: str) -> ModelSpec:
    for spec in MODEL_SPECS:
        if spec.model == model:
            return spec
    raise ValueError(f"missing price specification for {model}")


def estimate_request_ceiling_usd(request: Mapping[str, Any]) -> float:
    spec = _model_spec(str(request["model"]))
    # Two UTF-8 bytes per input token is deliberately conservative for these
    # ASCII-heavy prompts and also covers serialized schema/request overhead.
    serialized = _canonical_json(request).encode("utf-8")
    input_upper = math.ceil(len(serialized) / 2)
    output_upper = int(request["max_output_tokens"])
    return (
        input_upper * spec.input_usd_per_million
        + output_upper * spec.output_usd_per_million
    ) / 1_000_000


def usage_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    spec = _model_spec(model)
    return (
        input_tokens * spec.input_usd_per_million
        + output_tokens * spec.output_usd_per_million
    ) / 1_000_000


class CostGuard:
    def __init__(
        self,
        ceiling_usd: float = USD_CEILING,
        *,
        reserved_usd: float = 0.0,
    ):
        self.ceiling_usd = ceiling_usd
        self.reserved_usd = reserved_usd
        self.actual_estimated_usd = 0.0

    def preflight(self, requests: Sequence[Mapping[str, Any]]) -> float:
        estimate = sum(estimate_request_ceiling_usd(request) for request in requests)
        if self.reserved_usd + estimate > self.ceiling_usd:
            raise RuntimeError(
                "reserved plus worst-case planned API estimate "
                f"${self.reserved_usd + estimate:.6f} exceeds ${self.ceiling_usd:.2f}"
            )
        return estimate

    def before_call(self, request: Mapping[str, Any]) -> None:
        worst = estimate_request_ceiling_usd(request)
        if self.reserved_usd + self.actual_estimated_usd + worst > self.ceiling_usd:
            raise RuntimeError("estimated API cost ceiling would be exceeded")

    def record_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.actual_estimated_usd += usage_cost_usd(model, input_tokens, output_tokens)
        if self.reserved_usd + self.actual_estimated_usd > self.ceiling_usd:
            raise RuntimeError("estimated API cost ceiling was exceeded")


def official_https_transport(request_body: Mapping[str, Any]) -> Mapping[str, Any]:
    """POST one request without logging credentials, bodies, or raw responses."""

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required only with --live")
    raw = _canonical_json(request_body).encode("utf-8")
    request = Request(
        API_URL,
        data=raw,
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "User-Agent": "urusilla-comprehension-pilot/1.0",
        },
    )
    try:
        with urlopen(request, timeout=240) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not persist the response body; only a status code leaves this layer.
        raise RuntimeError(f"api_http_{exc.code}") from None
    except URLError:
        raise RuntimeError("api_transport_error") from None


def _response_output_text(response: Mapping[str, Any]) -> str:
    if response.get("status") != "completed":
        raise DecodeError("response_not_completed")
    for item in response.get("output", []):
        if isinstance(item, Mapping) and item.get("type") == "message":
            for content in item.get("content", []):
                if isinstance(content, Mapping) and content.get("type") == "refusal":
                    raise DecodeError("response_refusal")
                if isinstance(content, Mapping) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str):
                        return text
    raise DecodeError("response_output_text_missing")


def _validator_failure_category(exc: Exception) -> str:
    message = str(exc)
    categories = (
        ("message must be a mapping", "top_level/type"),
        ("missing top-level field", "top_level/missing"),
        ("unknown top-level field", "top_level/extra"),
        ("id must", "id/invalid"),
        ("session must", "session/invalid"),
        ("sender must", "sender/invalid"),
        ("recipients", "recipients/invalid"),
        ("unknown communicative act", "act/unknown"),
        ("act must", "act/type"),
        ("reply_to", "reply_to/invalid"),
        ("schema must", "schema/invalid"),
        ("logical_clock", "logical_clock/invalid"),
        ("expires_ms", "expires_ms/invalid"),
        ("confidence_ppm", "confidence_ppm/invalid"),
        ("expected", "expected/invalid"),
        ("meta", "meta/invalid"),
        ("body", "body/invalid"),
        ("COMMIT debtor", "body.commitment/debtor_sender_mismatch"),
        ("semantic", "semantic_tree/invalid"),
    )
    for fragment, category in categories:
        if fragment in message:
            return "ValidationError/" + category
    return "ValidationError/unknown/other"


def parse_receiver_batch(text: str, expected_count: int) -> ParsedBatch:
    try:
        wrapper = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ParsedBatch(
            tuple([None] * expected_count),
            tuple([False] * expected_count),
            True,
            "wrapper_json",
            ("wrapper/json",),
        )
    if not isinstance(wrapper, dict) or set(wrapper) != {"messages"}:
        return ParsedBatch(
            tuple([None] * expected_count),
            tuple([False] * expected_count),
            True,
            "wrapper_shape",
            ("wrapper/shape",),
        )
    records = wrapper["messages"]
    if not isinstance(records, list) or len(records) != expected_count:
        return ParsedBatch(
            tuple([None] * expected_count),
            tuple([False] * expected_count),
            True,
            "record_count",
            ("records/count",),
        )

    observed: list[Mapping[str, Any] | None] = []
    validator_flags: list[bool] = []
    validator_failures: list[str] = []
    malformed = False
    failure: str | None = None
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {"index", "message"}:
            observed.append(None)
            validator_flags.append(False)
            validator_failures.append("record/shape")
            malformed = True
            failure = failure or "record_shape"
            continue
        if record["index"] != index:
            observed.append(None)
            validator_flags.append(False)
            validator_failures.append("record/index")
            malformed = True
            failure = failure or "record_index"
            continue
        try:
            normalized = normalize_message(record["message"])
        except (TypeError, ValidationError) as exc:
            observed.append(None)
            validator_flags.append(False)
            validator_failures.append(_validator_failure_category(exc))
            malformed = True
            failure = failure or "semantic_message"
            continue
        observed.append(normalized)
        validator_flags.append(True)
    return ParsedBatch(
        tuple(observed),
        tuple(validator_flags),
        malformed,
        failure,
        tuple(validator_failures),
    )


def _terminal_map(value: Any, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    if isinstance(value, Mapping):
        if not value:
            return {path: "{}"}
        result: dict[tuple[str, ...], str] = {}
        for key in sorted(value, key=lambda item: item.encode("utf-8")):
            result.update(_terminal_map(value[key], path + (key,)))
        return result
    if isinstance(value, list):
        if not value:
            return {path: "[]"}
        result = {}
        for index, item in enumerate(value):
            result.update(_terminal_map(item, path + (f"[{index}]",)))
        return result
    return {path: _canonical_json(value)}


def score_batch(
    expected: Sequence[PilotMessage], parsed: ParsedBatch
) -> tuple[int, int, int, int]:
    exact = validator_valid = terminal_matches = terminal_total = 0
    for item, observed, is_valid in zip(
        expected, parsed.observed, parsed.validator_valid, strict=True
    ):
        expected_message = item.message
        exact += observed == expected_message
        validator_valid += bool(is_valid)
        expected_terminals = _terminal_map(expected_message)
        terminal_total += len(expected_terminals)
        if observed is not None:
            observed_terminals = _terminal_map(observed)
            terminal_matches += sum(
                observed_terminals.get(path) == value
                for path, value in expected_terminals.items()
            )
    return exact, validator_valid, terminal_matches, terminal_total


def _usage(response: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0, 0, 0, 0
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    cached = int(input_details.get("cached_tokens", 0)) if isinstance(input_details, Mapping) else 0
    reasoning = int(output_details.get("reasoning_tokens", 0)) if isinstance(output_details, Mapping) else 0
    return input_tokens, cached, output_tokens, reasoning, total_tokens


def safe_response_diagnostic(
    response: Mapping[str, Any],
    *,
    attempt: str,
    batch_index: int,
    parse_failure_code: str | None,
    validator_failure_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Return aggregate-only response metadata without retaining model text or IDs."""

    output_types: list[str] = []
    content_types: list[str] = []
    output_texts: list[str] = []
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                output_types.append("non_mapping")
                continue
            output_types.append(str(item.get("type", "missing")))
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, Mapping):
                        content_types.append("non_mapping")
                        continue
                    content_types.append(str(part.get("type", "missing")))
                    if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        output_texts.append(str(part["text"]))

    incomplete_reason: str | None = None
    incomplete = response.get("incomplete_details")
    if isinstance(incomplete, Mapping) and isinstance(incomplete.get("reason"), str):
        incomplete_reason = str(incomplete["reason"])

    error_type: str | None = None
    error_code: str | None = None
    error = response.get("error")
    if isinstance(error, Mapping):
        if isinstance(error.get("type"), str):
            error_type = str(error["type"])
        if isinstance(error.get("code"), str):
            error_code = str(error["code"])

    usage = _usage(response)
    text_joined = "\x00".join(output_texts)
    return {
        "attempt": attempt,
        "batch_index": batch_index,
        "transport": "completed",
        "response_status": str(response.get("status", "missing")),
        "incomplete_reason": incomplete_reason,
        "error_type": error_type,
        "error_code": error_code,
        "output_types": output_types,
        "content_types": content_types,
        "output_text_items": len(output_texts),
        "output_text_characters": sum(len(text) for text in output_texts),
        "output_text_sha256": (
            hashlib.sha256(text_joined.encode("utf-8")).hexdigest()
            if output_texts
            else None
        ),
        "parse_failure_code": parse_failure_code,
        "validator_failure_counts": dict(
            sorted((validator_failure_counts or {}).items())
        ),
        "input_tokens": usage[0],
        "cached_input_tokens": usage[1],
        "output_tokens": usage[2],
        "reasoning_tokens": usage[3],
        "total_tokens": usage[4],
    }


def _run_batch_trial(
    model: str,
    representation: str,
    repeat: int,
    messages: Sequence[PilotMessage],
    transport: Transport,
    guard: CostGuard,
    *,
    batch_index: int,
) -> TrialResult:
    totals = [0, 0, 0, 0, 0]
    latency_ms = 0.0
    malformed_initial = repair_attempts = repair_failures = 0
    attempt_diagnostics: list[Mapping[str, Any]] = []
    parsed = ParsedBatch(
        tuple([None] * len(messages)),
        tuple([False] * len(messages)),
        True,
        "not_run",
        ("response/not_run",),
    )
    failure_code: str | None = None

    for attempt in range(2):
        repair = attempt == 1
        request = build_request(model, messages, representation, repair=repair)
        if request.get("store") is not False:
            raise RuntimeError("live request attempted to enable storage")
        guard.before_call(request)
        started = time.perf_counter()
        try:
            response = transport(request)
        except RuntimeError as exc:
            latency_ms += (time.perf_counter() - started) * 1000
            failure_code = str(exc) if str(exc).startswith("api_") else "api_error"
            attempt_diagnostics.append(
                {
                    "attempt": "repair" if repair else "primary",
                    "batch_index": batch_index,
                    "transport": "failed",
                    "failure_code": failure_code,
                }
            )
            if repair:
                repair_failures = 1
            break
        latency_ms += (time.perf_counter() - started) * 1000
        usage = _usage(response)
        totals = [left + right for left, right in zip(totals, usage, strict=True)]
        guard.record_usage(model, usage[0], usage[2])
        try:
            output_text = _response_output_text(response)
            parsed = parse_receiver_batch(output_text, len(messages))
        except DecodeError as exc:
            parsed = ParsedBatch(
                tuple([None] * len(messages)),
                tuple([False] * len(messages)),
                True,
                str(exc),
                ("response/" + str(exc),),
            )
        attempt_diagnostics.append(
            safe_response_diagnostic(
                response,
                attempt="repair" if repair else "primary",
                batch_index=batch_index,
                parse_failure_code=parsed.failure_code if parsed.malformed else None,
                validator_failure_counts=Counter(
                    parsed.validator_failure_categories
                ),
            )
        )
        if not parsed.malformed:
            failure_code = None
            break
        failure_code = parsed.failure_code
        if attempt == 0:
            malformed_initial = 1
            repair_attempts = 1
            continue
        repair_failures = 1

    exact, validator_valid, terminal_matches, terminal_total = score_batch(messages, parsed)
    status = "completed" if failure_code is None else "failed"
    return TrialResult(
        model=model,
        representation=representation,
        repeat=repeat,
        status=status,
        exact_messages=exact,
        validator_valid_messages=validator_valid,
        messages=len(messages),
        terminal_matches=terminal_matches,
        terminal_total=terminal_total,
        malformed_initial=malformed_initial,
        repair_attempts=repair_attempts,
        repair_failures=repair_failures,
        input_tokens=totals[0],
        cached_input_tokens=totals[1],
        output_tokens=totals[2],
        reasoning_tokens=totals[3],
        total_tokens=totals[4],
        latency_ms=round(latency_ms, 3),
        estimated_cost_usd=round(usage_cost_usd(model, totals[0], totals[2]), 9),
        failure_code=failure_code,
        batch_count=1,
        batch_message_counts=(len(messages),),
        attempt_diagnostics=tuple(attempt_diagnostics),
        validator_failure_counts=dict(
            sorted(Counter(parsed.validator_failure_categories).items())
        ),
    )


def _message_batches(
    messages: Sequence[PilotMessage], batch_size: int | None
) -> tuple[tuple[PilotMessage, ...], ...]:
    frozen = tuple(messages)
    if batch_size is None:
        return (frozen,)
    if batch_size <= 0:
        raise ValueError("batch size must be positive")
    return tuple(
        frozen[start : start + batch_size]
        for start in range(0, len(frozen), batch_size)
    )


def run_trial(
    model: str,
    representation: str,
    repeat: int,
    messages: Sequence[PilotMessage],
    transport: Transport,
    guard: CostGuard,
    *,
    batch_size: int | None = None,
) -> TrialResult:
    """Run one format trial, optionally split into deterministic ordered batches."""

    batches = _message_batches(messages, batch_size)
    parts = [
        _run_batch_trial(
            model,
            representation,
            repeat,
            batch,
            transport,
            guard,
            batch_index=batch_index,
        )
        for batch_index, batch in enumerate(batches)
    ]
    input_tokens = sum(part.input_tokens for part in parts)
    output_tokens = sum(part.output_tokens for part in parts)
    failures = [
        f"batch_{index}:{part.failure_code}"
        for index, part in enumerate(parts)
        if part.failure_code is not None
    ]
    return TrialResult(
        model=model,
        representation=representation,
        repeat=repeat,
        status="completed" if not failures else "failed",
        exact_messages=sum(part.exact_messages for part in parts),
        validator_valid_messages=sum(part.validator_valid_messages for part in parts),
        messages=sum(part.messages for part in parts),
        terminal_matches=sum(part.terminal_matches for part in parts),
        terminal_total=sum(part.terminal_total for part in parts),
        malformed_initial=sum(part.malformed_initial for part in parts),
        repair_attempts=sum(part.repair_attempts for part in parts),
        repair_failures=sum(part.repair_failures for part in parts),
        input_tokens=input_tokens,
        cached_input_tokens=sum(part.cached_input_tokens for part in parts),
        output_tokens=output_tokens,
        reasoning_tokens=sum(part.reasoning_tokens for part in parts),
        total_tokens=sum(part.total_tokens for part in parts),
        latency_ms=round(sum(part.latency_ms for part in parts), 3),
        estimated_cost_usd=round(
            usage_cost_usd(model, input_tokens, output_tokens), 9
        ),
        failure_code="|".join(failures) if failures else None,
        batch_count=len(parts),
        batch_message_counts=tuple(part.messages for part in parts),
        attempt_diagnostics=tuple(
            diagnostic
            for part in parts
            for diagnostic in part.attempt_diagnostics
        ),
        validator_failure_counts=dict(
            sorted(
                sum(
                    (Counter(part.validator_failure_counts) for part in parts),
                    Counter(),
                ).items()
            )
        ),
    )


def _grammar_metrics() -> dict[str, dict[str, int]]:
    try:
        import tiktoken  # type: ignore[import-not-found]

        encoding = tiktoken.get_encoding("o200k_base")
        count = lambda text: len(
            encoding.encode(text, allowed_special=set(), disallowed_special=())
        )
    except ImportError:
        count = lambda text: math.ceil(len(text.encode("utf-8")) / 4)
    return {
        representation: {
            "utf8_bytes": len(grammar.encode("utf-8")),
            "o200k_or_four_byte_proxy_tokens": count(grammar),
        }
        for representation, grammar in GRAMMARS.items()
    }


def run_live(
    *,
    transport: Transport = official_https_transport,
    repeats: int = REPEATS,
    progress: Callable[[TrialResult], None] | None = None,
) -> dict[str, Any]:
    messages = select_pilot_messages()
    batches = _message_batches(messages, LIVE_BATCH_SIZE)
    requests = [
        build_request(spec.model, batch, representation, repair=repair)
        for spec in MODEL_SPECS
        for representation in FORMATS
        for _repeat in range(repeats)
        for batch in batches
        for repair in (False, True)
    ]
    guard = CostGuard(reserved_usd=PRE_AMENDMENT_RESERVED_USD)
    worst_case = guard.preflight(requests)
    trials: list[TrialResult] = []

    gate_model = MODEL_SPECS[0].model
    gate_trials: list[TrialResult] = []
    for repeat in range(repeats):
        trial = run_trial(
            gate_model,
            "json",
            repeat,
            messages,
            transport,
            guard,
            batch_size=LIVE_BATCH_SIZE,
        )
        trials.append(trial)
        gate_trials.append(trial)
        if progress is not None:
            progress(trial)
    gate_passed = all(
        trial.status == "completed"
        and trial.exact_messages >= GATE_MIN_EXACT_MESSAGES
        and not trial.validator_failure_counts
        for trial in gate_trials
    )

    if gate_passed:
        for spec in MODEL_SPECS:
            for representation in FORMATS:
                if spec.model == gate_model and representation == "json":
                    continue
                for repeat in range(repeats):
                    trial = run_trial(
                        spec.model,
                        representation,
                        repeat,
                        messages,
                        transport,
                        guard,
                        batch_size=LIVE_BATCH_SIZE,
                    )
                    trials.append(trial)
                    if progress is not None:
                        progress(trial)

    result = {
        "format": FORMAT,
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "api": "official Responses API",
        "store": False,
        "models": [spec.model for spec in MODEL_SPECS],
        "representations": list(FORMATS),
        "repeats": repeats,
        "messages": len(messages),
        "batch_size": LIVE_BATCH_SIZE,
        "batches_per_trial": len(batches),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "api_attempts": sum(len(trial.attempt_diagnostics) for trial in trials),
        "acts": list(ACTS),
        "origins": dict(sorted(Counter(item.origin for item in messages).items())),
        "pilot_corpus_sha256": corpus_digest([item.message for item in messages]),
        "symbolic_text_sha256": _sequence_digest(
            tuple(encode_symbolic(item.message) for item in messages)
        ),
        "preflight_worst_case_estimated_usd": round(worst_case, 9),
        "actual_usage_estimated_usd": round(guard.actual_estimated_usd, 9),
        "pre_amendment_reserved_usd": PRE_AMENDMENT_RESERVED_USD,
        "experiment_cost_upper_bound_usd": round(
            PRE_AMENDMENT_RESERVED_USD + guard.actual_estimated_usd, 9
        ),
        "cost_ceiling_usd": USD_CEILING,
        "pre_amendment_observations": PRE_AMENDMENT_OBSERVATIONS,
        "gate": {
            "model": gate_model,
            "representation": "json",
            "minimum_exact_messages_per_repeat": GATE_MIN_EXACT_MESSAGES,
            "requires_zero_validator_failures": True,
            "passed": gate_passed,
            "matrix_continued": gate_passed,
        },
        "grammar": _grammar_metrics(),
        "trials": [asdict(trial) for trial in trials],
    }
    if result["experiment_cost_upper_bound_usd"] > USD_CEILING:
        raise RuntimeError("live pilot exceeded estimated cost ceiling")
    return result


def _nearest(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _source_digest(name: str) -> str:
    path = Path(__file__).with_name(name)
    if not path.is_file():
        return "not-present"
    return sha256_file(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _aggregate(results: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for trial in results["trials"]:
        grouped.setdefault((trial["model"], trial["representation"]), []).append(trial)
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for key, trials in grouped.items():
        output[key] = {
            "runs": len(trials),
            "exact": sum(item["exact_messages"] for item in trials),
            "validator_valid": sum(item["validator_valid_messages"] for item in trials),
            "messages": sum(item["messages"] for item in trials),
            "terminal_matches": sum(item["terminal_matches"] for item in trials),
            "terminal_total": sum(item["terminal_total"] for item in trials),
            "input_tokens": sum(item["input_tokens"] for item in trials),
            "cached_input_tokens": sum(item["cached_input_tokens"] for item in trials),
            "output_tokens": sum(item["output_tokens"] for item in trials),
            "reasoning_tokens": sum(item["reasoning_tokens"] for item in trials),
            "total_tokens": sum(item["total_tokens"] for item in trials),
            "latency_median_ms": statistics.median(item["latency_ms"] for item in trials),
            "latency_p95_ms": _nearest([item["latency_ms"] for item in trials], 0.95),
            "malformed_initial": sum(item["malformed_initial"] for item in trials),
            "repair_attempts": sum(item["repair_attempts"] for item in trials),
            "repair_failures": sum(item["repair_failures"] for item in trials),
            "failed_runs": sum(item["status"] != "completed" for item in trials),
            "estimated_cost_usd": sum(item["estimated_cost_usd"] for item in trials),
            "failure_codes": dict(
                sorted(Counter(item["failure_code"] for item in trials if item["failure_code"]).items())
            ),
            "validator_failure_counts": dict(
                sorted(
                    sum(
                        (
                            Counter(item["validator_failure_counts"])
                            for item in trials
                        ),
                        Counter(),
                    ).items()
                )
            ),
        }
    return output


def render_report(results: Mapping[str, Any]) -> str:
    aggregates = _aggregate(results)
    total_exact = sum(item["exact_messages"] for item in results["trials"])
    total_messages = sum(item["messages"] for item in results["trials"])
    failures = sum(item["status"] != "completed" for item in results["trials"])
    api_attempts = int(
        results.get(
            "api_attempts",
            sum(len(item.get("attempt_diagnostics", [])) for item in results["trials"]),
        )
    )
    matrix_complete = len(results["trials"]) == len(MODEL_SPECS) * len(FORMATS) * results["repeats"]
    gate = results.get("gate", {})
    retained_pre_cutover_measurement = (
        results.get("provider_rerun_after_urusilla_cutover") is False
    )
    result_sentence = (
        f"Two live repeats for each of two models and three exact input formats produced **{total_exact:,}/{total_messages:,} exact semantic message reconstructions** across {len(results['trials'])} model/format/repeat trials and {api_attempts} API attempts. There were **{failures} failed trials**."
        if matrix_complete
        else f"The predeclared reliability gate produced **{total_exact:,}/{total_messages:,} exact semantic message reconstructions** across {len(results['trials'])} gate trials and {api_attempts} API attempts. The gate did not pass, so the remaining matrix was not run."
    )
    lines = [
        "# Live model receiver-comprehension pilot",
        "",
        "## Result",
        "",
        result_sentence + " Every unfavorable field, token, latency, malformed-output, and repair result remains in the tables below. Validator failures are also retained by privacy-safe category.",
        "",
        "This is a small prompted receiver-comprehension pilot. It does **not** measure sender generation, multi-turn agent task success, autonomous repair, cross-vendor transfer, unprompted protocol adoption, latent communication, or state-of-the-art performance.",
    ]
    if retained_pre_cutover_measurement:
        lines.extend([
            "",
            "These provider outcomes remain bound to the historical pre-cutover input digests recorded below. No provider call was rerun after the Urusilla cutover. The current Urusilla corpus and symbolic surface were rederived and validated only through offline deterministic tests, so the 27/28 live result must not be attributed to those current inputs.",
        ])
    lines.extend([
        "",
        "## Controlled design",
        "",
        f"The measured fixed corpus contains {results['messages']} semantic messages: one grouped-holdout and one out-of-domain example for each of the seven core acts. Every model/format/repeat receives the identical ordered semantic set, deterministically split into {results['batches_per_trial']} batches of {results['batch_size']} messages. Grammar is paid once per batch, not once per message.",
        "",
        "The receiver returns a strict JSON-schema object containing the original index and a direct typed message object. The schema is inferred from each batch's recursive value types and key/list shape but contains no terminal values. Scoring locally canonicalizes and validates each reconstructed object, compares the full semantic message, and compares every terminal path/value occurrence. This removes the original double-serialized `canonical_json` string confound.",
        "",
        f"The predeclared gate required both `{gate.get('model', 'unknown')}` + JSON repeats to recover at least {gate.get('minimum_exact_messages_per_repeat', 'unknown')}/14 messages with zero validator failures. Gate passed: **{str(bool(gate.get('passed'))).lower()}**. Matrix continued: **{str(bool(gate.get('matrix_continued'))).lower()}**.",
        "",
        "The official Responses API was called with `store=false`. No raw model output, response identifier, or API key is stored in this artifact. GPT-5 nano and GPT-4o mini both document Responses and Structured Outputs support. Current price constants used for the estimate are $0.05/$0.40 and $0.15/$0.60 per million input/output tokens, respectively. See the official [GPT-5 nano](https://developers.openai.com/api/docs/models/gpt-5-nano) and [GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini) model pages and the [Responses API reference](https://developers.openai.com/api/reference/responses/create).",
        "",
        "## Semantic recovery",
        "",
        "| Model | Input format | Runs | Exact messages | Validator-valid | Terminal fields | Failed runs | Initial malformed | Repairs | Repair failures |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for spec in MODEL_SPECS:
        for representation in FORMATS:
            item = aggregates.get((spec.model, representation))
            if item is None:
                lines.append(
                    f"| `{spec.model}` | {FORMAT_LABELS[representation]} | not run | — | — | — | — | — | — | — |"
                )
                continue
            lines.append(
                f"| `{spec.model}` | {FORMAT_LABELS[representation]} | {item['runs']} | "
                f"{item['exact']}/{item['messages']} | {item['validator_valid']}/{item['messages']} | "
                f"{item['terminal_matches']:,}/{item['terminal_total']:,} | {item['failed_runs']} | "
                f"{item['malformed_initial']} | {item['repair_attempts']} | {item['repair_failures']} |"
            )

    lines.extend([
        "",
        "## API tokens, latency, and estimated cost",
        "",
        "Usage values come from the API response. Output tokens include reasoning tokens where reported. Cost applies the published uncached input/output rates to measured usage; it is an estimate rather than an invoice. Latency is wall time for the full HTTPS response and is based on only two observations per cell.",
        "",
        "| Model | Input format | Input | Cached input | Output | Reasoning | Total | Input/msg | Output/msg | Median latency | p95 latency | Estimated cost |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for spec in MODEL_SPECS:
        for representation in FORMATS:
            item = aggregates.get((spec.model, representation))
            if item is None:
                lines.append(
                    f"| `{spec.model}` | {FORMAT_LABELS[representation]} | not run | — | — | — | — | — | — | — | — | — |"
                )
                continue
            lines.append(
                f"| `{spec.model}` | {FORMAT_LABELS[representation]} | {item['input_tokens']:,} | "
                f"{item['cached_input_tokens']:,} | {item['output_tokens']:,} | {item['reasoning_tokens']:,} | "
                f"{item['total_tokens']:,} | {item['input_tokens']/item['messages']:.1f} | "
                f"{item['output_tokens']/item['messages']:.1f} | {item['latency_median_ms']:.1f} ms | "
                f"{item['latency_p95_ms']:.1f} ms | ${item['estimated_cost_usd']:.6f} |"
            )

    lines.extend([
        "",
        "## Cold grammar and warm amortization",
        "",
        f"Cold grammar counts below use local `o200k_base` when available; otherwise the script labels and uses a four-UTF-8-byte proxy. They exclude common instructions, records, the shape-derived output schema, and API framing, so they are a grammar-only accounting aid rather than API-billed usage. Warm amortization divides the once-per-batch grammar by {results['batch_size']} messages.",
        "",
        "| Input format | Grammar bytes | Grammar tokens/proxy | Warm grammar tokens/message |",
        "|---|---:|---:|---:|",
    ])
    for representation in FORMATS:
        metric = results["grammar"][representation]
        lines.append(
            f"| {FORMAT_LABELS[representation]} | {metric['utf8_bytes']:,} | "
            f"{metric['o200k_or_four_byte_proxy_tokens']:,} | "
            f"{metric['o200k_or_four_byte_proxy_tokens']/results['batch_size']:.2f} |"
        )

    lines.extend([
        "",
        "## Compact symbolic surface",
        "",
        "The symbolic surface is a standard-library implementation with shared semantic validation. After `@1`, an 11-character Base64url checksum and colon protect a fixed sequence of one-letter fields. Values are canonical JSON and `~` is null. The labels map as follows:",
        "",
        "| Label | Semantic field |",
        "|---|---|",
    ])
    for label, field in SYMBOLIC_FIELDS:
        lines.append(f"| `{label}` | `{field}` |")
    lines.extend([
        "",
        "The decoder verifies the checksum, exact label order, JSON values, shared semantic constraints, absence of trailing data, and byte-identical canonical re-encoding. Unit tests cover every pilot message, deterministic output, malformed headers, non-canonical spelling, and deterministic single-character mutations.",
        "",
        "## Protocol amendments and preserved failures",
        "",
        "The original output contract asked the model to place a complete JSON document inside a JSON string. That conflated semantic recovery with escaping and double serialization. Before changing the contract, the following unfavorable observations were frozen. They are not pooled with the final direct-object results.",
        "",
        "| Stage | Model / format | Repeat | Batch | Exact | Terminals | Total tokens | Latency | Status / failure |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ])
    history = results["pre_amendment_observations"]
    for item in history["completed_trial_summaries"]:
        lines.append(
            f"| double-serialized output | `{item['model']}` / {FORMAT_LABELS[item['representation']]} | {item['repeat'] + 1} | 14 | {item['exact_messages']}/{item['messages']} | {item['terminal_matches']}/{item['terminal_total']} | {item['total_tokens']:,} | {item['latency_ms']:.1f} ms | {item['status']} |"
        )
    seven = history["seven_message_batch_stage"]
    for item in seven["completed_trial_summaries"]:
        lines.append(
            f"| double-serialized output | `{item['model']}` / {FORMAT_LABELS[item['representation']]} | {item['repeat'] + 1} | 7+7 | {item['exact_messages']}/{item['messages']} | {item['terminal_matches']}/{item['terminal_total']} | {item['total_tokens']:,} | {item['latency_ms']:.1f} ms | `{item['failure_code']}` |"
        )
    probe = history["diagnostic_probe"]
    lines.extend([
        f"| privacy-safe diagnostic | `gpt-5-nano` / sorted minified JSON | 1 | 14 | {probe['exact_messages']}/{probe['messages']} | {probe['terminal_matches']}/{probe['terminal_total']} | {probe['total_tokens']:,} | not retained | `{probe['response_status']}` / `{probe['parse_failure_code']}` |",
        "",
        f"The diagnostic response completed without an API error or incomplete reason, but validator parsing failed. It contained {probe['output_text_characters']:,} output-text characters with SHA-256 `{probe['output_text_sha256']}`; the text itself was discarded. Two later requests were interrupted in flight across the two stopped stages, so their server completion and billing outcome are unknown. The cost guard reserves a deliberately conservative upper bound for all of these calls.",
        "",
        "## Cost gate",
        "",
        f"- Hard estimated ceiling: `${results['cost_ceiling_usd']:.2f}`.",
        f"- Worst-case preflight estimate, including one full repair call after every primary call: `${results['preflight_worst_case_estimated_usd']:.6f}`.",
        f"- Measured-usage estimate for the final gated run: `${results['actual_usage_estimated_usd']:.6f}`.",
        f"- Conservative reserve for all pre-amendment and interrupted calls: `${results['pre_amendment_reserved_usd']:.6f}`.",
        f"- Whole-experiment upper bound used by the guard: `${results['experiment_cost_upper_bound_usd']:.6f}`.",
        f"- Planned repeats: `{results['repeats']}` per model/format; only the gate cell ran because the gate failed.",
        "- The preflight assumes two UTF-8 input bytes per token, includes the shape-derived output schema, and assumes every call consumes the full output-token limit. Calls are blocked if the reserve plus measured usage and the next call's bound would cross the ceiling.",
        "",
        "## Frozen inputs and provenance",
        "",
        f"- Run UTC: `{results['run_utc']}`",
        f"- Format: `{results['format']}`",
        f"- Measured pilot corpus SHA-256: `{results['pilot_corpus_sha256']}`",
        f"- Measured symbolic text-sequence SHA-256: `{results['symbolic_text_sha256']}`",
        f"- Current Urusilla pilot corpus SHA-256: `{results.get('current_urusilla_pilot_corpus_sha256', results['pilot_corpus_sha256'])}`",
        f"- Current Urusilla symbolic text-sequence SHA-256: `{results.get('current_urusilla_symbolic_text_sha256', results['symbolic_text_sha256'])}`",
        f"- Provider rerun after Urusilla cutover: `{str(bool(results.get('provider_rerun_after_urusilla_cutover', True))).lower()}`",
        f"- Frozen aggregate results SHA-256: `{results_sha256(results)}`",
        f"- Acts: `{', '.join(results['acts'])}`",
        f"- Origins: `{_canonical_json(results['origins'])}`",
        f"- Offline report-render Python: `{platform.python_version()}`",
        f"- Offline report-render platform: `{platform.platform()}`",
        "",
        "Source SHA-256 values:",
        "",
        f"- pilot and symbolic codec: `{_source_digest('urusilla_model_comprehension_pilot.py')}`",
        f"- offline tests: `{_source_digest('test_urusilla_model_comprehension_pilot.py')}`",
        "",
        "Reproduce deliberately; network calls occur only with `--live` and consume API credits:",
        "",
        "```bash",
        "PYTHONPATH=outputs work/tokenizer_venv/bin/python outputs/urusilla_model_comprehension_pilot.py --live",
        "PYTHONPATH=outputs python3 -m unittest outputs/test_urusilla_model_comprehension_pilot.py -v",
        "```",
        "",
        "## Limitations",
        "",
        "- Fourteen synthetic messages and two repeats per cell are far too small for a general model-comprehension claim or a rank ordering with confidence intervals.",
        "- The retained live outcomes predate the Urusilla cutover. Current renamed inputs pass offline codec and determinism tests only; they have no new provider outcome.",
        "- The historical live runtime was not embedded separately in the aggregate result. The Python and platform values above identify this offline report render, not the provider measurement environment.",
        "- The prompt explicitly teaches each format and asks for reconstruction. This measures prompted receiver comprehension, not spontaneous acquisition or use.",
        "- The strict output wrapper can improve formatting reliability but does not reveal whether internal semantic understanding is robust. Its batch-specific recursive schema exposes key, type, list-length, and container shape, though never terminal values; this can materially assist reconstruction.",
        "- Two-message batches pay the format grammar and shape schema seven times per corpus pass. This is an unfavorable latency and cold-context tradeoff introduced only after larger batches failed the reliability gate.",
        "- The same project authored the language, prompts, and evaluation. No blinded external evaluator or independent corpus was used.",
        "- Only GPT-5 nano reached the gate. GPT-4o mini and all non-JSON format cells were deliberately not run after the gate failed. Cross-vendor and unseen-model transfer remain unknown.",
        "- Task success, sender generation, dialogue, tool use, repair after semantic errors, and adversarial inputs remain unmeasured.",
        "- Token usage and API latency do not directly measure energy, local inference cost, KV-cache behavior, or production throughput.",
        "- Model aliases and prices can change. The report records the aliases used and links the official model pages consulted for this run.",
        "",
    ])
    failure_codes = Counter(
        trial["failure_code"] for trial in results["trials"] if trial["failure_code"]
    )
    if failure_codes:
        lines.extend([
            "## Failure codes",
            "",
            "No raw failed output is retained. Aggregate failure codes:",
            "",
        ])
        for code, count in sorted(failure_codes.items()):
            lines.append(f"- `{code}`: {count}")
        lines.append("")

    validator_failures = sum(
        (
            Counter(trial.get("validator_failure_counts", {}))
            for trial in results["trials"]
        ),
        Counter(),
    )
    if validator_failures:
        lines.extend([
            "## Validator failure categories",
            "",
            "Categories contain paths and error classes only, never reconstructed values:",
            "",
        ])
        for category, count in sorted(validator_failures.items()):
            lines.append(f"- `{category}`: {count}")
        lines.append("")

    unfavorable_diagnostics = []
    for trial in results["trials"]:
        for diagnostic in trial.get("attempt_diagnostics", []):
            if (
                diagnostic.get("transport") != "completed"
                or diagnostic.get("response_status") != "completed"
                or diagnostic.get("parse_failure_code")
                or diagnostic.get("validator_failure_counts")
            ):
                unfavorable_diagnostics.append((trial, diagnostic))
    if unfavorable_diagnostics:
        lines.extend([
            "## Privacy-safe unfavorable response diagnostics",
            "",
            "Raw output and response identifiers were discarded. Digests identify output text without retaining it.",
            "",
            "| Model / format | Repeat | Batch | Attempt | Transport / status | Parse failure | Validator categories | Output chars | Output SHA-256 | Tokens |",
            "|---|---:|---:|---|---|---|---|---:|---|---:|",
        ])
        for trial, diagnostic in unfavorable_diagnostics:
            categories = _canonical_json(
                diagnostic.get("validator_failure_counts", {})
            )
            lines.append(
                f"| `{trial['model']}` / {FORMAT_LABELS[trial['representation']]} | {trial['repeat'] + 1} | {diagnostic.get('batch_index', '—')} | {diagnostic.get('attempt', '—')} | {diagnostic.get('transport', '—')} / {diagnostic.get('response_status', '—')} | `{diagnostic.get('parse_failure_code') or diagnostic.get('failure_code') or 'none'}` | `{categories}` | {diagnostic.get('output_text_characters', '—')} | `{diagnostic.get('output_text_sha256') or 'none'}` | {diagnostic.get('total_tokens', '—')} |"
            )
        lines.append("")
    return "\n".join(lines)


def results_sha256(results: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(results).encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run billable live API calls")
    parser.add_argument("--render-frozen", action="store_true", help="render embedded aggregate results without network calls")
    parser.add_argument("--report", type=Path, default=Path(__file__).with_name(REPORT_NAME))
    parser.add_argument("--dump-results", action="store_true", help="print aggregate results without raw API outputs")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.live == args.render_frozen:
        raise SystemExit("choose exactly one of --live or --render-frozen")
    if args.live:
        def progress(trial: TrialResult) -> None:
            print(
                "progress "
                f"model={trial.model} format={trial.representation} "
                f"repeat={trial.repeat + 1}/{REPEATS} "
                f"exact={trial.exact_messages}/{trial.messages} "
                f"terminals={trial.terminal_matches}/{trial.terminal_total} "
                f"tokens={trial.total_tokens} latency_ms={trial.latency_ms:.1f} "
                f"batches={trial.batch_count} status={trial.status} "
                f"failure={trial.failure_code} "
                f"validator_failures={_canonical_json(trial.validator_failure_counts)}",
                file=sys.stderr,
                flush=True,
            )

        results = run_live(progress=progress)
    else:
        if not FROZEN_LIVE_RESULTS:
            raise SystemExit("no frozen live results are embedded")
        results = dict(FROZEN_LIVE_RESULTS)
    args.report.write_text(render_report(results), encoding="utf-8")
    if args.dump_results:
        print(_canonical_json(results))
    else:
        print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
