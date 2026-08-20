#!/usr/bin/env python3
"""Compare Urusilla text codecs with a strong terse-English baseline.

The benchmark reuses the frozen grouped holdout and out-of-domain corpora.  Its
Controlled Terse English (CTE) renderer is deterministic, exactly reversible,
and deliberately compact: safe scalar strings and map keys are unquoted, while
the fixed outer sentence names every top-level semantic field.  This makes CTE
more competitive than ordinary prose without pretending that token count
measures language-model understanding or task success.

No model is invoked.  The only measured outcomes are exact semantic recovery,
field coverage, UTF-8 size, tokenizer counts, and negotiated cold-start cost.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from urusilla import ACTS, DecodeError, MAX_FRAME_BYTES, normalize_message
from urusilla_token_surface_holdout import (
    EXPECTED_CODEBOOK_SHA256,
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_SHA256,
    EXPECTED_TRAIN_SHA256,
    _sequence_digest,
    build_out_of_domain_corpus,
    codec_functions,
    encoded_texts,
    frozen_split,
    holdout_codebook,
)
from urusilla_token_surface_v03 import encode_codebook_capsule_text
from urusilla_tokenizer_benchmark import (
    TIKTOKEN_VERSION,
    TOKENIZERS_VERSION,
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
    sha256_file,
)
from urusilla_wire_v02 import DEFAULT_PROFILE, encode_capsule as encode_profile_capsule


FORMAT = "urusilla-terse-english-baseline-v1"
REPORT_NAME = "TERSE_ENGLISH_RESULTS.md"
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
SERIALIZATION_LABELS = {
    "terse_english": "Controlled Terse English",
    "json": "sorted minified JSON",
    "base64_v02": "Base64 wire v0.2 warm",
    "v03": "token surface v0.3 warm",
}
DATASET_LABELS = {
    "grouped_holdout": "grouped holdout",
    "out_of_domain": "out of domain",
}

# Final values are frozen after the first controlled run.  Tests require these
# mappings to contain exact values; no tolerance or performance threshold is
# used.
EXPECTED_TERSE_TEXT_SHA256: Mapping[str, str] = {
    "grouped_holdout": "565e8549bc7eb582b4d997bbd37ef45dc07bd7fe9c61b5a48399c246b8a514e7",
    "out_of_domain": "e179deb0b57709dd3ecf89852ad6939c812fcf2f70833463e08aa87cf1d07a32",
}
EXPECTED_METRICS: Mapping[str, Mapping[str, Mapping[str, int]]] = {
    "grouped_holdout": {
        "terse_english": {
            "bytes": 43_880,
            "characters": 43_880,
            "cl100k_base": 15_764,
            "o200k_base": 15_770,
            "qwen2_5_7b_instruct": 18_893,
            "mistral_7b_instruct_v03": 21_228,
        },
        "json": {
            "bytes": 52_604,
            "characters": 52_604,
            "cl100k_base": 16_763,
            "o200k_base": 17_224,
            "qwen2_5_7b_instruct": 19_892,
            "mistral_7b_instruct_v03": 23_514,
        },
        "base64_v02": {
            "bytes": 15_448,
            "characters": 15_448,
            "cl100k_base": 10_933,
            "o200k_base": 10_151,
            "qwen2_5_7b_instruct": 11_097,
            "mistral_7b_instruct_v03": 12_313,
        },
        "v03": {
            "bytes": 15_368,
            "characters": 6_382,
            "cl100k_base": 6_367,
            "o200k_base": 6_312,
            "qwen2_5_7b_instruct": 6_337,
            "mistral_7b_instruct_v03": 6_409,
        },
    },
    "out_of_domain": {
        "terse_english": {
            "bytes": 8_402,
            "characters": 8_402,
            "cl100k_base": 2_639,
            "o200k_base": 2_645,
            "qwen2_5_7b_instruct": 3_098,
            "mistral_7b_instruct_v03": 3_599,
        },
        "json": {
            "bytes": 9_856,
            "characters": 9_856,
            "cl100k_base": 2_808,
            "o200k_base": 2_897,
            "qwen2_5_7b_instruct": 3_267,
            "mistral_7b_instruct_v03": 4_001,
        },
        "base64_v02": {
            "bytes": 8_212,
            "characters": 8_212,
            "cl100k_base": 5_829,
            "o200k_base": 5_467,
            "qwen2_5_7b_instruct": 6_007,
            "mistral_7b_instruct_v03": 6_642,
        },
        "v03": {
            "bytes": 11_496,
            "characters": 5_391,
            "cl100k_base": 5_376,
            "o200k_base": 5_026,
            "qwen2_5_7b_instruct": 5_368,
            "mistral_7b_instruct_v03": 5_385,
        },
    },
}
EXPECTED_COLD_METRICS: Mapping[str, Mapping[str, int]] = {
    "profile": {
        "bytes": 1_872,
        "characters": 1_872,
        "cl100k_base": 1_346,
        "o200k_base": 1_261,
        "qwen2_5_7b_instruct": 1_375,
        "mistral_7b_instruct_v03": 1_516,
    },
    "codebook": {
        "bytes": 11_927,
        "characters": 11_927,
        "cl100k_base": 8_224,
        "o200k_base": 7_746,
        "qwen2_5_7b_instruct": 8_344,
        "mistral_7b_instruct_v03": 9_422,
    },
}

_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._:/-]*\Z")
_SAFE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_UINT = re.compile(r"(?:0|[1-9][0-9]*)")
_RESERVED = frozenset({"true", "false", "null", "none", "unknown"})
_JSON_DECODER = json.JSONDecoder(
    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid constant {value}"))
)


@dataclass(frozen=True)
class Coverage:
    messages: int
    exact_messages: int
    deterministic_messages: int
    required_field_occurrences: int
    required_field_matches: int
    terminal_occurrences: int
    terminal_matches: int


@dataclass(frozen=True)
class Study:
    datasets: Mapping[str, tuple[dict[str, Any], ...]]
    texts: Mapping[str, Mapping[str, tuple[str, ...]]]
    metrics: Mapping[str, Mapping[str, Mapping[str, int]]]
    cold: Mapping[str, Mapping[str, int]]
    coverage: Mapping[str, Coverage]
    profiles: tuple[TokenizerProfile, ...]


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _render_value(value: Any) -> str:
    """Render a semantic value in the compact, self-delimiting CTE value grammar."""

    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return json.dumps(value, allow_nan=False, separators=(",", ":"))
    if type(value) is bytes:
        return f'bytes"{value.hex()}"'
    if type(value) is str:
        if (
            _SAFE_TOKEN.fullmatch(value)
            and value not in _RESERVED
            and _NUMBER.fullmatch(value) is None
            and not value.startswith("bytes")
        ):
            return value
        return _json_string(value)
    if type(value) is list:
        return "[" + ",".join(_render_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        items: list[str] = []
        for key in sorted(value, key=lambda item: item.encode("utf-8")):
            rendered_key = key if _SAFE_KEY.fullmatch(key) else _json_string(key)
            items.append(f"{rendered_key}={_render_value(value[key])}")
        return "{" + ",".join(items) + "}"
    raise TypeError(f"unsupported controlled-English value: {type(value).__name__}")


class _ValueParser:
    def __init__(self, text: str, position: int = 0):
        self.text = text
        self.position = position

    def literal(self, value: str) -> None:
        if not self.text.startswith(value, self.position):
            raise DecodeError(f"expected {value!r} at character {self.position}")
        self.position += len(value)

    def json_string(self) -> str:
        try:
            value, end = _JSON_DECODER.raw_decode(self.text, self.position)
        except (json.JSONDecodeError, ValueError) as exc:
            raise DecodeError(f"invalid quoted string at character {self.position}") from exc
        if type(value) is not str:
            raise DecodeError(f"expected a quoted string at character {self.position}")
        self.position = end
        return value

    def _bare(self) -> str:
        start = self.position
        while self.position < len(self.text) and self.text[self.position] not in ",]} ;":
            self.position += 1
        if self.position == start:
            raise DecodeError(f"expected a value at character {start}")
        return self.text[start : self.position]

    def value(self) -> Any:
        if self.position >= len(self.text):
            raise DecodeError("truncated controlled-English value")
        lead = self.text[self.position]
        if lead == '"':
            return self.json_string()
        if lead == "[":
            return self.array()
        if lead == "{":
            return self.mapping()
        if self.text.startswith('bytes"', self.position):
            self.position += len("bytes")
            encoded = self.json_string()
            if re.fullmatch(r"(?:[0-9a-f]{2})*", encoded) is None:
                raise DecodeError("bytes value is not canonical lowercase hexadecimal")
            return bytes.fromhex(encoded)

        token = self._bare()
        if token == "true":
            return True
        if token == "false":
            return False
        if token == "null":
            return None
        if _NUMBER.fullmatch(token):
            try:
                return json.loads(token)
            except json.JSONDecodeError as exc:
                raise DecodeError("invalid numeric value") from exc
        if _SAFE_TOKEN.fullmatch(token) is None or token in _RESERVED or token.startswith("bytes"):
            raise DecodeError(f"invalid bare token {token!r}")
        return token

    def array(self) -> list[Any]:
        result: list[Any] = []
        self.literal("[")
        if self.text.startswith("]", self.position):
            self.position += 1
            return result
        while True:
            result.append(self.value())
            if self.text.startswith("]", self.position):
                self.position += 1
                return result
            self.literal(",")

    def mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        self.literal("{")
        if self.text.startswith("}", self.position):
            self.position += 1
            return result
        while True:
            if self.text.startswith('"', self.position):
                key = self.json_string()
            else:
                start = self.position
                while self.position < len(self.text) and self.text[self.position] != "=":
                    if self.text[self.position] in ",{}[]; ":
                        raise DecodeError(f"invalid map key at character {start}")
                    self.position += 1
                key = self.text[start : self.position]
                if _SAFE_KEY.fullmatch(key) is None:
                    raise DecodeError(f"invalid bare map key {key!r}")
            self.literal("=")
            if key in result:
                raise DecodeError(f"duplicate map key {key!r}")
            result[key] = self.value()
            if self.text.startswith("}", self.position):
                self.position += 1
                return result
            self.literal(",")


def encode_terse_english(message: Mapping[str, Any]) -> str:
    """Return the canonical Controlled Terse English sentence for one message."""

    canonical = normalize_message(message)
    reply = "none" if canonical["reply_to"] is None else _render_value(canonical["reply_to"])
    confidence = (
        "unknown"
        if canonical["confidence_ppm"] is None
        else f'{canonical["confidence_ppm"]}ppm'
    )
    return (
        f'{canonical["act"]} from {_render_value(canonical["sender"])} '
        f'to {_render_value(canonical["recipients"])}: {_render_value(canonical["body"])}; '
        f'id {_render_value(canonical["id"])}, session {_render_value(canonical["session"])}, '
        f'reply {reply}, schema {_render_value(canonical["schema"])}, '
        f'clock {canonical["logical_clock"]}, expires {canonical["expires_ms"]}ms, '
        f'confidence {confidence}, expect {_render_value(canonical["expected"])}, '
        f'meta {_render_value(canonical["meta"])}.'
    )


def _parse_uint(parser: _ValueParser, suffix: str) -> int:
    match = _UINT.match(parser.text, parser.position)
    if match is None:
        raise DecodeError(f"expected an unsigned integer at character {parser.position}")
    parser.position = match.end()
    parser.literal(suffix)
    return int(match.group())


def decode_terse_english(text: str) -> dict[str, Any]:
    """Parse CTE, validate the semantic object, and reject non-canonical spellings."""

    if type(text) is not str or len(text.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DecodeError("controlled-English text type or size is invalid")
    match = re.match(r"[A-Z]+", text)
    if match is None or match.group() not in ACTS:
        raise DecodeError("controlled-English text has an unknown communicative act")
    act = match.group()
    parser = _ValueParser(text, match.end())
    parser.literal(" from ")
    sender = parser.value()
    parser.literal(" to ")
    recipients = parser.value()
    parser.literal(": ")
    body = parser.value()
    parser.literal("; id ")
    message_id = parser.value()
    parser.literal(", session ")
    session = parser.value()
    parser.literal(", reply ")
    if parser.text.startswith("none", parser.position):
        parser.position += len("none")
        reply_to = None
    else:
        reply_to = parser.value()
    parser.literal(", schema ")
    schema = parser.value()
    parser.literal(", clock ")
    logical_clock = _parse_uint(parser, "")
    parser.literal(", expires ")
    expires_ms = _parse_uint(parser, "ms")
    parser.literal(", confidence ")
    if parser.text.startswith("unknown", parser.position):
        parser.position += len("unknown")
        confidence_ppm = None
    else:
        confidence_ppm = _parse_uint(parser, "ppm")
    parser.literal(", expect ")
    expected = parser.value()
    parser.literal(", meta ")
    meta = parser.value()
    parser.literal(".")
    if parser.position != len(text):
        raise DecodeError(f"trailing text at character {parser.position}")

    canonical = normalize_message(
        {
            "id": message_id,
            "session": session,
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
    )
    if encode_terse_english(canonical) != text:
        raise DecodeError("controlled-English text is valid but not canonical")
    return canonical


def _terminal_pairs(value: Any, path: tuple[str, ...] = ()) -> tuple[tuple[tuple[str, ...], str], ...]:
    if isinstance(value, Mapping):
        if not value:
            return ((path, "{}"),)
        result: list[tuple[tuple[str, ...], str]] = []
        for key in sorted(value, key=lambda item: item.encode("utf-8")):
            result.extend(_terminal_pairs(value[key], path + (key,)))
        return tuple(result)
    if type(value) is list:
        if not value:
            return ((path, "[]"),)
        result = []
        for index, item in enumerate(value):
            result.extend(_terminal_pairs(item, path + (f"[{index}]",)))
        return tuple(result)
    return ((path, _render_value(value)),)


def _coverage(messages: Sequence[Mapping[str, Any]], texts: Sequence[str]) -> Coverage:
    exact = deterministic = required_hits = terminals = terminal_hits = 0
    for message, text in zip(messages, texts, strict=True):
        decoded = decode_terse_english(text)
        exact += decoded == message
        deterministic += encode_terse_english(message) == text
        required_hits += sum(decoded[field] == message[field] for field in TOP_LEVEL_FIELDS)
        expected_pairs = _terminal_pairs(message)
        observed_pairs = _terminal_pairs(decoded)
        terminals += len(expected_pairs)
        terminal_hits += sum(left == right for left, right in zip(expected_pairs, observed_pairs, strict=True))
    return Coverage(
        messages=len(messages),
        exact_messages=exact,
        deterministic_messages=deterministic,
        required_field_occurrences=len(messages) * len(TOP_LEVEL_FIELDS),
        required_field_matches=required_hits,
        terminal_occurrences=terminals,
        terminal_matches=terminal_hits,
    )


def build_datasets() -> dict[str, tuple[dict[str, Any], ...]]:
    split = frozen_split()
    datasets = {
        "grouped_holdout": tuple(split.holdout),
        "out_of_domain": tuple(build_out_of_domain_corpus()),
    }
    observed = {
        "grouped_holdout": EXPECTED_HOLDOUT_SHA256,
        "out_of_domain": EXPECTED_OOD_SHA256,
    }
    from urusilla_benchmark import corpus_digest

    for key, messages in datasets.items():
        if corpus_digest(messages) != observed[key]:
            raise RuntimeError(f"frozen {key} corpus changed")
    return datasets


def build_texts(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, tuple[str, ...]]]:
    codebook = holdout_codebook()
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for dataset_key, messages in datasets.items():
        existing = encoded_texts(messages, codebook)
        result[dataset_key] = {
            "terse_english": tuple(encode_terse_english(message) for message in messages),
            "json": tuple(existing["json"]),
            "base64_v02": tuple(existing["base64_v02"]),
            "v03": tuple(existing["v03"]),
        }
    return result


def _measure(
    texts: Mapping[str, Mapping[str, Sequence[str]]],
    profiles: Sequence[TokenizerProfile],
) -> dict[str, dict[str, dict[str, int]]]:
    result: dict[str, dict[str, dict[str, int]]] = {}
    for dataset_key, serializations in texts.items():
        result[dataset_key] = {}
        for codec_key, values in serializations.items():
            result[dataset_key][codec_key] = {
                "bytes": sum(len(value.encode("utf-8")) for value in values),
                "characters": sum(len(value) for value in values),
                **{
                    profile.key: sum(profile.count(value) for value in values)
                    for profile in profiles
                },
            }
    return result


def _cold_metrics(profiles: Sequence[TokenizerProfile]) -> dict[str, dict[str, int]]:
    profile_text = base64.b64encode(encode_profile_capsule(DEFAULT_PROFILE)).decode("ascii")
    codebook_text = encode_codebook_capsule_text(holdout_codebook())
    result: dict[str, dict[str, int]] = {}
    for key, value in {"profile": profile_text, "codebook": codebook_text}.items():
        result[key] = {
            "bytes": len(value.encode("utf-8")),
            "characters": len(value),
            **{profile.key: profile.count(value) for profile in profiles},
        }
    return result


def collect_study(profiles: Sequence[TokenizerProfile]) -> Study:
    datasets = build_datasets()
    texts = build_texts(datasets)
    metrics = _measure(texts, profiles)
    cold = _cold_metrics(profiles)
    coverage = {
        key: _coverage(messages, texts[key]["terse_english"])
        for key, messages in datasets.items()
    }

    for dataset_key, serializations in texts.items():
        expected_digest = EXPECTED_TERSE_TEXT_SHA256.get(dataset_key)
        actual_digest = _sequence_digest(serializations["terse_english"])
        if expected_digest is not None and actual_digest != expected_digest:
            raise RuntimeError(f"frozen terse-English text changed for {dataset_key}")
    if EXPECTED_METRICS and metrics != EXPECTED_METRICS:
        raise RuntimeError("frozen warm byte or token metrics changed")
    if EXPECTED_COLD_METRICS and cold != EXPECTED_COLD_METRICS:
        raise RuntimeError("frozen cold byte or token metrics changed")
    return Study(datasets, texts, metrics, cold, coverage, tuple(profiles))


def _saved_percent(candidate: int, baseline: int) -> float:
    return 100.0 * (1.0 - candidate / baseline)


def _format_saved(candidate: int, baseline: int) -> str:
    return f"{_saved_percent(candidate, baseline):+.1f}%"


def strict_break_even(cold: int, baseline_total: int, warm_total: int, count: int) -> int | None:
    """First N where cold + N*mean(warm) is strictly below N*mean(baseline)."""

    saving = baseline_total - warm_total
    if saving <= 0:
        return None
    return cold * count // saving + 1


def _break_text(value: int | None) -> str:
    return "never on mean" if value is None else f"{value:,}"


def _cold_for_candidate(cold: Mapping[str, Mapping[str, int]], candidate: str, metric: str) -> int:
    if candidate == "base64_v02":
        return cold["profile"][metric]
    if candidate == "v03":
        return cold["profile"][metric] + cold["codebook"][metric]
    raise ValueError(f"unsupported cold candidate {candidate}")


def _source_digest(name: str) -> str:
    path = Path(__file__).with_name(name)
    return sha256_file(path) if path.is_file() else "not-present"


def render_report(study: Study, asset_root: Path) -> str:
    measures = ("bytes",) + tuple(profile.key for profile in study.profiles)
    measure_labels = {
        "bytes": "UTF-8 bytes",
        **{profile.key: profile.display_name for profile in study.profiles},
    }
    all_warm_savings = [
        _saved_percent(
            study.metrics[dataset][codec][profile.key],
            study.metrics[dataset]["terse_english"][profile.key],
        )
        for dataset in study.datasets
        for codec in ("base64_v02", "v03")
        for profile in study.profiles
    ]
    best = max(all_warm_savings)
    worst = min(all_warm_savings)
    lines = [
        "# Terse-English serialization baseline",
        "",
        "## Result",
        "",
        "This bounded study compares the same canonical Urusilla messages in four text-carried representations: a strong Controlled Terse English baseline, sorted minified JSON, Base64 wire v0.2, and the warm experimental token surface v0.3. Across the two datasets and four pinned tokenizers, the two machine surfaces range from "
        f"**{worst:+.1f}% to {best:+.1f}% token savings** versus Controlled Terse English. Negative savings are retained and mean that the machine surface used more tokens.",
        "",
        "This is serialization accounting, not an end-to-end agent evaluation. It does **not** show that any language model understands CTE or the machine surfaces, and it does not measure task success, repair behavior, inference latency, or energy.",
        "",
        "## Controlled Terse English baseline",
        "",
        "CTE is a deterministic controlled-language record, not unconstrained conversational prose. It is intentionally compact to avoid a weak natural-language strawman: safe ASCII strings and map keys are unquoted, maps and lists use concise delimiters, and only the fixed outer sentence carries English function words.",
        "",
        "The canonical grammar is:",
        "",
        "```text",
        "ACT from SENDER to RECIPIENTS: BODY; id ID, session SESSION, reply REPLY, schema SCHEMA, clock UINT, expires UINTms, confidence UINTppm|unknown, expect ACTS, meta META.",
        "```",
        "",
        "Each uppercase or named slot has exactly one mapping:",
        "",
        "| Canonical field | CTE location |",
        "|---|---|",
        "| `act` | first uppercase word |",
        "| `sender` | value after `from` |",
        "| `recipients` | list after `to` |",
        "| `body` | value after the colon |",
        "| `id` | labeled `id` value |",
        "| `session` | labeled `session` value |",
        "| `reply_to` | labeled `reply`; `none` is null |",
        "| `schema` | labeled `schema` value |",
        "| `logical_clock` | labeled `clock` unsigned integer |",
        "| `expires_ms` | labeled `expires` integer with `ms` suffix |",
        "| `confidence_ppm` | labeled `confidence`; `unknown` is null |",
        "| `expected` | labeled `expect` act list |",
        "| `meta` | labeled `meta` map |",
        "",
        "Nested values use a documented typed grammar: `true`, `false`, `null`, canonical JSON numbers, quoted JSON strings when a string is not a safe bare token, lists `[v,...]`, UTF-8-key-sorted maps `{key=v,...}`, and `bytes\"lowercase-hex\"`. The decoder rejects duplicate keys, malformed syntax, trailing text, non-canonical spellings, and messages rejected by the shared semantic validator. This gives a machine-checkable one-to-one mapping rather than relying on paraphrase judgment.",
        "",
        "Example (the report does not charge this documentation):",
        "",
        "```text",
        study.texts["grouped_holdout"]["terse_english"][0],
        "```",
        "",
        "## Exact recovery and field coverage",
        "",
        "| Dataset | Messages exact | Deterministic re-render | Required top-level fields | Terminal path/value occurrences |",
        "|---|---:|---:|---:|---:|",
    ]
    for dataset_key, coverage in study.coverage.items():
        lines.append(
            f"| {DATASET_LABELS[dataset_key]} | {coverage.exact_messages}/{coverage.messages} | "
            f"{coverage.deterministic_messages}/{coverage.messages} | "
            f"{coverage.required_field_matches:,}/{coverage.required_field_occurrences:,} | "
            f"{coverage.terminal_matches:,}/{coverage.terminal_occurrences:,} |"
        )

    lines.extend(
        [
            "",
            "Exact decoded-object equality is the primary coverage test. The field and terminal-path counts make omissions visible but are not substitutes for that equality check.",
            "",
            "## Exact warm sizes and token counts",
            "",
            "Every message is counted as an independent frame. Counts exclude BOS/EOS, chat templates, role markers, prompts, transport envelopes, and retransmissions.",
            "",
        ]
    )
    for dataset_key in study.datasets:
        lines.extend(
            [
                f"### {DATASET_LABELS[dataset_key].title()}",
                "",
                "| Representation | UTF-8 bytes | Characters | "
                + " | ".join(profile.display_name for profile in study.profiles)
                + " |",
                "|---|---:|---:|" + "---:|" * len(study.profiles),
            ]
        )
        for codec_key in SERIALIZATION_LABELS:
            metric = study.metrics[dataset_key][codec_key]
            lines.append(
                f"| {SERIALIZATION_LABELS[codec_key]} | {metric['bytes']:,} | {metric['characters']:,} | "
                + " | ".join(f"{metric[profile.key]:,}" for profile in study.profiles)
                + " |"
            )
        lines.extend(
            [
                "",
                "Savings relative to Controlled Terse English (positive is better; negative is worse):",
                "",
                "| Representation | Bytes | "
                + " | ".join(profile.display_name for profile in study.profiles)
                + " |",
                "|---|---:|" + "---:|" * len(study.profiles),
            ]
        )
        baseline = study.metrics[dataset_key]["terse_english"]
        for codec_key in ("json", "base64_v02", "v03"):
            metric = study.metrics[dataset_key][codec_key]
            lines.append(
                f"| {SERIALIZATION_LABELS[codec_key]} | {_format_saved(metric['bytes'], baseline['bytes'])} | "
                + " | ".join(
                    _format_saved(metric[profile.key], baseline[profile.key])
                    for profile in study.profiles
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## Cold transfer",
            "",
            "CTE and JSON require no negotiated data capsule in this accounting. Base64 v0.2 requires the static profile once. Token surface v0.3 requires that profile plus the heldout-trained codebook. Decoder software and the public language specification are treated as installed for every representation.",
            "",
            "| Capsule | UTF-8 bytes | Characters | "
            + " | ".join(profile.display_name for profile in study.profiles)
            + " |",
            "|---|---:|---:|" + "---:|" * len(study.profiles),
        ]
    )
    for capsule_key in ("profile", "codebook"):
        metric = study.cold[capsule_key]
        lines.append(
            f"| {capsule_key} | {metric['bytes']:,} | {metric['characters']:,} | "
            + " | ".join(f"{metric[profile.key]:,}" for profile in study.profiles)
            + " |"
        )

    lines.extend(
        [
            "",
            "Strict break-even is the first integer `N` satisfying `cold + N × candidate_mean < N × baseline_mean`, assuming the measured workload mix repeats. `never on mean` means the candidate is not smaller while warm under that metric.",
            "",
            "| Dataset | Candidate | Baseline | Cold charged | "
            + " | ".join(measure_labels[measure] for measure in measures)
            + " |",
            "|---|---|---|---|" + "---:|" * len(measures),
        ]
    )
    for dataset_key, messages in study.datasets.items():
        count = len(messages)
        for baseline_key in ("terse_english", "json"):
            for candidate_key in ("base64_v02", "v03"):
                baseline = study.metrics[dataset_key][baseline_key]
                candidate = study.metrics[dataset_key][candidate_key]
                values = []
                for measure in measures:
                    cold_cost = _cold_for_candidate(study.cold, candidate_key, measure)
                    values.append(
                        strict_break_even(cold_cost, baseline[measure], candidate[measure], count)
                    )
                charged = "profile" if candidate_key == "base64_v02" else "profile + codebook"
                lines.append(
                    f"| {DATASET_LABELS[dataset_key]} | {SERIALIZATION_LABELS[candidate_key]} | "
                    f"{SERIALIZATION_LABELS[baseline_key]} | {charged} | "
                    + " | ".join(_break_text(value) for value in values)
                    + " |"
                )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"The grouped holdout and the ten-message out-of-domain set must be read separately. The former repeats a synthetic benchmark family while holding out complete semantic groups; the latter introduces new schemas, agents, values, and map shapes but is small and repository-authored. The v0.3 codebook sees only the {len(frozen_split().train)}-message training partition. The v0.2 profile and v0.3 Unicode alphabet were developed earlier around the benchmark family and named OpenAI tokenizers, so this is not a blind tokenizer evaluation.",
            "",
            "A representation should not be selected from an aggregate headline. Warm savings can reverse by dataset and tokenizer, while a large negotiated capsule can dominate a short session. These exact negative cases are part of the result: adaptive negotiation should retain CTE or JSON whenever the machine surface is not expected to amortize.",
            "",
            "## Method and frozen inputs",
            "",
            f"- Format: `{FORMAT}`",
            f"- Grouped holdout: {len(study.datasets['grouped_holdout'])} messages, canonical corpus SHA-256 `{EXPECTED_HOLDOUT_SHA256}`",
            f"- Out of domain: {len(study.datasets['out_of_domain'])} messages, canonical corpus SHA-256 `{EXPECTED_OOD_SHA256}`",
            f"- v0.3 training partition: {len(frozen_split().train)} messages, SHA-256 `{EXPECTED_TRAIN_SHA256}`",
            f"- Heldout-trained codebook SHA-256: `{EXPECTED_CODEBOOK_SHA256}`",
            f"- Tokenizer packages: `tiktoken=={TIKTOKEN_VERSION}`, `tokenizers=={TOKENIZERS_VERSION}`",
            "- Tokenization: each serialization counted separately with no special tokens added",
            "",
            "Tokenizer identities:",
            "",
        ]
    )
    for profile in study.profiles:
        lines.append(
            f"- `{profile.key}`: {profile.display_name}; {profile.implementation}; vocabulary {profile.vocabulary_size:,}; fingerprint `{profile.fingerprint}`"
        )
    lines.extend(
        [
            "",
            "Text-sequence SHA-256 values use an eight-byte big-endian length before each UTF-8 message:",
            "",
        ]
    )
    for dataset_key, serializations in study.texts.items():
        lines.append(f"- {DATASET_LABELS[dataset_key]}:")
        for codec_key, values in serializations.items():
            lines.append(f"  - `{codec_key}`: `{_sequence_digest(values)}`")
    lines.extend(
        [
            "",
            "Source SHA-256 values:",
            "",
            f"- `urusilla_terse_english_benchmark.py`: `{_source_digest('urusilla_terse_english_benchmark.py')}`",
            f"- `test_urusilla_terse_english_benchmark.py`: `{_source_digest('test_urusilla_terse_english_benchmark.py')}`",
            f"- frozen corpus provider: `{_source_digest('urusilla_token_surface_holdout.py')}`",
            "",
            "Reproduce from a repository root. The asset downloader verifies immutable official revisions and complete-file SHA-256 values before use:",
            "",
            "```bash",
            "python3 -m venv work/tokenizer_venv",
            f"work/tokenizer_venv/bin/python -m pip install tiktoken=={TIKTOKEN_VERSION} tokenizers=={TOKENIZERS_VERSION}",
            "PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_tokenizer_benchmark.py --download-assets --assets-dir work/tokenizer_assets",
            "PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_terse_english_benchmark.py --benchmark --assets-dir work/tokenizer_assets",
            "PYTHONPATH=. work/tokenizer_venv/bin/python -m unittest test_urusilla_terse_english_benchmark.py -v",
            "```",
            "",
            "## Limitations",
            "",
            "- CTE is controlled English-like notation, not a sample of ordinary agent prose. A natural-language baseline without deterministic field encoding would not guarantee semantic equivalence.",
            "- Exact round-trip proves serialization fidelity only. No LLM decoded any representation in this study, so understanding, instruction following, and repair success remain unmeasured.",
            "- The grouped holdout is synthetic and related to profile development. The out-of-domain corpus has only ten messages and was authored in the same repository.",
            "- Token counts depend on four pinned tokenizer assets. They do not predict all models, hosted token accounting, KV-cache behavior, or compressed transport bytes.",
            "- Cold break-even assumes an unchanged workload mix, successful cache reuse, no negotiation failure, and no retransmission.",
            "- Energy cannot be inferred directly from token count; joules, hardware utilization, and end-to-end latency were not measured.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="run the frozen benchmark")
    parser.add_argument("--assets-dir", type=Path, default=default_asset_root())
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(__file__).with_name(REPORT_NAME),
    )
    parser.add_argument(
        "--dump-metrics",
        action="store_true",
        help="print exact JSON metrics for freezing or independent inspection",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.benchmark:
        raise SystemExit("choose --benchmark")
    profiles = load_tokenizer_profiles(args.assets_dir)
    study = collect_study(profiles)
    report = render_report(study, args.assets_dir)
    args.report.write_text(report, encoding="utf-8")
    if args.dump_metrics:
        payload = {
            "terse_text_sha256": {
                key: _sequence_digest(values["terse_english"])
                for key, values in study.texts.items()
            },
            "metrics": study.metrics,
            "cold": study.cold,
            "coverage": {
                key: coverage.__dict__ for key, coverage in study.coverage.items()
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
