#!/usr/bin/env python3
"""Grouped holdout and small out-of-domain study for UrusillaTokenSurface v0.3.

This experiment trains byte-pair entries only on the development partition.
Complete semantic-combination groups are assigned to either development or
holdout. A separate, hand-authored ASCII corpus exercises all seven acts with
identifiers, values, and map shapes outside the benchmark generator.

The split is stronger than a random message split, but it is not an independent
blind evaluation. Both partitions still come from one synthetic generator, the
v0.2 profile was designed for that generator, and the Unicode surface alphabet
was selected using the two measured tokenizers before this experiment.
"""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import struct
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

from urusilla_benchmark import build_corpus, corpus_digest, json_decode, json_encode
from urusilla import DecodeError, ValidationError, normalize_message
from urusilla_token_surface_v03 import (
    CODEBOOK_SYMBOLS,
    SURFACE_ALPHABET,
    SURFACE_CHECKSUM_SYMBOLS,
    TokenCodebook,
    _train_entries,
    decode_message as decode_v03,
    encode_codebook_capsule_text,
    encode_message as encode_v03,
)
from urusilla_wire_v02 import (
    DEFAULT_PROFILE,
    decode_message as decode_v02,
    encode_capsule as encode_v02_capsule,
    encode_message as encode_v02,
)


FORMAT = "urusilla-token-surface-holdout-v1"
TIKTOKEN_VERSION = "0.11.0"
CANDIDATE_MESSAGES = 280
EXPECTED_SOURCE_CORPUS_SHA256 = (
    "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc"
)
SPLIT_DOMAIN = b"urusilla-token-surface-holdout-v1|"
OOD_NAMESPACE = uuid.UUID("f453c7eb-aaf2-4c72-88ca-a4faecaa2e82")

# These constants are replaced with exact values after the first deterministic
# construction pass, then enforced by both this module and the test suite.
EXPECTED_ENGLISH_CORPUS_SHA256 = "9c10963c0b8f6494faaee6aea7b2c0e4e06e23ee3631686f01fb1d7d29ad6bef"
EXPECTED_TRAIN_SHA256 = "f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759"
EXPECTED_HOLDOUT_SHA256 = "6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9"
EXPECTED_HOLDOUT_GROUP_SHA256 = "939d3572db604b9ccf0c8c83fb6792fdd0dbe4adafbd6924767e4b0a027c7f2d"
EXPECTED_OOD_SHA256 = "4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310"
EXPECTED_CODEBOOK_SHA256 = "d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695"
EXPECTED_TEXT_SHA256: dict[str, dict[str, str]] = {
    "grouped holdout": {
        "json": "6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9",
        "base64_v02": "4391adde6540d09573fbdfbf2781456cc0d5c027502efca2085984a8334274ac",
        "v03": "f66ade3a5538b6818728870a1ee1e51c1e6781385416cde3a48c68d7301bd0e5",
    },
    "out of domain": {
        "json": "4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310",
        "base64_v02": "cb1b69c69876a4c9945494b8aa2274d39fd40a1b353c1fda00c8b11501d09523",
        "v03": "1fd127e6956edf507e5668127662d8be40adce38682001946ad09463406820e4",
    },
}
EXPECTED_TRAIN_MESSAGES = 224
EXPECTED_HOLDOUT_MESSAGES = 56
EXPECTED_TOTAL_GROUPS = 75
EXPECTED_HOLDOUT_GROUPS = 16
EXPECTED_OOD_MESSAGES = 10
EXPECTED_WARM_METRICS: dict[str, dict[str, dict[str, int]]] = {
    "grouped holdout": {
        "json": {"bytes": 52_604, "characters": 52_604, "cl100k_base": 16_763, "o200k_base": 17_224},
        "base64_v02": {"bytes": 15_448, "characters": 15_448, "cl100k_base": 10_933, "o200k_base": 10_151},
        "v03": {"bytes": 15_368, "characters": 6_382, "cl100k_base": 6_367, "o200k_base": 6_312},
    },
    "out of domain": {
        "json": {"bytes": 9_856, "characters": 9_856, "cl100k_base": 2_808, "o200k_base": 2_897},
        "base64_v02": {"bytes": 8_212, "characters": 8_212, "cl100k_base": 5_829, "o200k_base": 5_467},
        "v03": {"bytes": 11_496, "characters": 5_391, "cl100k_base": 5_376, "o200k_base": 5_026},
    },
}
EXPECTED_COLD_METRICS = {
    "codebook": {"binary_bytes": 8_942, "bytes": 11_927, "cl100k_base": 8_224, "o200k_base": 7_746},
    "profile": {"binary_bytes": 1_402, "bytes": 1_872, "cl100k_base": 1_346, "o200k_base": 1_261},
}
EXPECTED_FALLBACK = {
    "grouped holdout": (56, 56, 5_822, 4_204, 11_525, 4_204),
    "out of domain": (10, 10, 5_291, 4_775, 6_148, 4_775),
}
EXPECTED_CORRUPTIONS = 264

_ENGLISH_REPLACEMENTS = {
    "ko-KR": "en-US",
    "ja-JP": "en-GB",
    "\uac80\uc99d": "verification",
    "r\u00e9sultat": "result",
    "\uc5d0\uc774\uc804\ud2b8": "agent",
}


@dataclass(frozen=True)
class FrozenSplit:
    train: tuple[dict[str, Any], ...]
    holdout: tuple[dict[str, Any], ...]
    train_groups: frozenset[str]
    holdout_groups: frozenset[str]
    all_group_count: int


@dataclass(frozen=True)
class FallbackStats:
    messages: int
    messages_with_raw: int
    payload_symbols: int
    raw_symbols: int
    frame_bytes: int
    raw_bytes: int

    @property
    def symbol_rate(self) -> float:
        return self.raw_symbols / self.payload_symbols if self.payload_symbols else 0.0

    @property
    def byte_rate(self) -> float:
        return self.raw_bytes / self.frame_bytes if self.frame_bytes else 0.0


def _require_frozen(label: str, actual: str, expected: str) -> None:
    if expected != "pending" and actual != expected:
        raise RuntimeError(f"{label} changed: expected {expected}, got {actual}")


def _sequence_digest(values: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        raw = value.encode("utf-8")
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _project_english(value: Any) -> Any:
    if isinstance(value, str):
        return _ENGLISH_REPLACEMENTS.get(value, value)
    if isinstance(value, list):
        return [_project_english(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _project_english(item) for key, item in value.items()}
    return value


def _all_strings(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, str):
        result.append(value)
    elif isinstance(value, list):
        for item in value:
            result.extend(_all_strings(item))
    elif isinstance(value, Mapping):
        for key, item in value.items():
            result.append(key)
            result.extend(_all_strings(item))
    return result


def build_english_candidate_corpus() -> list[dict[str, Any]]:
    source = build_corpus(CANDIDATE_MESSAGES)
    if corpus_digest(source) != EXPECTED_SOURCE_CORPUS_SHA256:
        raise RuntimeError("source benchmark corpus changed")
    result = [normalize_message(_project_english(message)) for message in source]
    if any(not text.isascii() for message in result for text in _all_strings(message)):
        raise RuntimeError("English projection left a non-ASCII semantic string")
    _require_frozen(
        "English candidate corpus digest",
        corpus_digest(result),
        EXPECTED_ENGLISH_CORPUS_SHA256,
    )
    return result


def _semantic_selector(message: Mapping[str, Any]) -> str:
    act = message["act"]
    body = message["body"]
    kind = body.get("kind", "query-shape")
    if act == "ASSERT":
        if kind == "claim":
            return f"claim:{body['predicate']}"
        if kind == "evidence":
            return f"evidence:{body['stance']}"
        if kind == "uncertainty":
            return f"uncertainty:{body['model']}"
    elif act == "QUERY":
        nested = body["arguments"][0]
        return f"claim:{body['predicate']}:{nested['predicate']}"
    elif act == "REQUEST":
        return f"goal:{body['condition']['predicate']}"
    elif act == "PROPOSE":
        predicate = body["arguments"]["goal"]["condition"]["predicate"]
        return f"action:{body['capability']}:{predicate}"
    elif act == "COMMIT":
        return f"commitment:{body['goal']['condition']['predicate']}"
    elif act == "RESOLVE":
        return f"resolution:{body['status']}"
    elif act == "RETRACT":
        return "ref:ledger-record"
    raise RuntimeError(f"unexpected candidate semantic form: {act}/{kind}")


def meaning_group(message: Mapping[str, Any]) -> str:
    body_kind = message["body"].get("kind", "query-shape")
    return "|".join(
        (message["act"], message["schema"], body_kind, _semantic_selector(message))
    )


@lru_cache(maxsize=1)
def frozen_split() -> FrozenSplit:
    corpus = build_english_candidate_corpus()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in corpus:
        grouped[meaning_group(message)].append(message)

    holdout_groups: set[str] = set()
    acts = sorted({message["act"] for message in corpus})
    for act in acts:
        candidates = [key for key in grouped if key.startswith(act + "|")]
        candidates.sort(
            key=lambda key: (hashlib.sha256(SPLIT_DOMAIN + key.encode()).digest(), key)
        )
        holdout_groups.update(candidates[: max(1, len(candidates) // 4)])

    train = tuple(message for message in corpus if meaning_group(message) not in holdout_groups)
    holdout = tuple(message for message in corpus if meaning_group(message) in holdout_groups)
    train_groups = frozenset(meaning_group(message) for message in train)
    held_groups = frozenset(meaning_group(message) for message in holdout)
    if train_groups & held_groups:
        raise RuntimeError("a meaning group leaked across the frozen split")
    if {message["id"] for message in train} & {message["id"] for message in holdout}:
        raise RuntimeError("a message leaked across the frozen split")
    if (len(train), len(holdout), len(grouped), len(held_groups)) != (
        EXPECTED_TRAIN_MESSAGES,
        EXPECTED_HOLDOUT_MESSAGES,
        EXPECTED_TOTAL_GROUPS,
        EXPECTED_HOLDOUT_GROUPS,
    ):
        raise RuntimeError("frozen split cardinalities changed")
    if {message["act"] for message in holdout} != {
        "ASSERT", "QUERY", "REQUEST", "PROPOSE", "COMMIT", "RESOLVE", "RETRACT"
    }:
        raise RuntimeError("grouped holdout lost act coverage")

    _require_frozen("train digest", corpus_digest(train), EXPECTED_TRAIN_SHA256)
    _require_frozen("holdout digest", corpus_digest(holdout), EXPECTED_HOLDOUT_SHA256)
    _require_frozen(
        "holdout group digest",
        _sequence_digest(sorted(held_groups)),
        EXPECTED_HOLDOUT_GROUP_SHA256,
    )
    return FrozenSplit(train, holdout, train_groups, held_groups, len(grouped))


def _ood_uuid(label: str) -> str:
    return str(uuid.uuid5(OOD_NAMESPACE, label))


def _ref(uri: str) -> dict[str, Any]:
    return {"kind": "ref", "uri": uri}


def _ood_goal(topic: str, owner: str) -> dict[str, Any]:
    return {
        "kind": "goal",
        "condition": {
            "kind": "claim",
            "predicate": f"{topic}.dataset.ready",
            "arguments": [_ref(f"urn:research-dataset:{topic}:cycle-17"), "quality-reviewed"],
            "context": {"collection": "independent-evaluation", "phase": "nightly"},
        },
        "owner": owner,
        "priority": 3,
        "window": {"opens_ms": 1_760_000_000_000, "closes_ms": 1_760_003_600_000},
        "constraints": [
            {
                "kind": "constraint",
                "scope": "publication",
                "mode": "hard",
                "condition": {"reviewers_gte": 2, "checksum_required": True},
                "weight_ppm": 1_000_000,
            }
        ],
    }


@lru_cache(maxsize=1)
def build_out_of_domain_corpus() -> tuple[dict[str, Any], ...]:
    agents = (
        "observatory.scheduler.agent",
        "archive.curator.agent",
        "simulation.verifier.agent",
        "field.sensor.agent",
    )
    acts = (
        "ASSERT", "ASSERT", "ASSERT", "QUERY", "QUERY",
        "REQUEST", "PROPOSE", "COMMIT", "RESOLVE", "RETRACT",
    )
    schemas = (
        "urn:urusilla:astronomy-calibration:7",
        "urn:urusilla:marine-observation:4",
        "urn:urusilla:software-migration:2",
    )
    result: list[dict[str, Any]] = []
    for index, act in enumerate(acts):
        sender = agents[index % len(agents)]
        recipient = agents[(index + 1) % len(agents)]
        topic = ("mirror-alignment", "acoustic-survey", "archive-migration")[index % 3]
        goal = _ood_goal(topic, sender)
        if index == 0:
            body: Mapping[str, Any] = {
                "kind": "claim",
                "predicate": "telescope.mirror.alignment.within-tolerance",
                "arguments": [
                    _ref("urn:instrument:mirror-array:alpha"),
                    {"azimuth_arcsec": 3, "elevation_arcsec": -2},
                    ["clear-sky", "night-shift"],
                ],
                "context": {"site": "southern-ridge", "instrument": "spectrograph-q"},
                "valid_time": {"start_ms": 1_760_000_000_000, "end_ms": 1_760_000_900_000},
                "annotations": {"quality_flag": "reviewed", "source_family": FORMAT},
            }
        elif index == 1:
            body = {
                "kind": "evidence",
                "target": _ref("urn:survey:hydrophone-array:west"),
                "stance": "supports",
                "digest": "sha256:" + hashlib.sha256(b"independent-acoustic-window").hexdigest(),
                "provenance": {"device": "hydrophone-12", "calibration": "traceable"},
                "observed_at_ms": 1_760_000_120_000,
                "method": "windowed-spectrum-review",
                "annotations": {"retention_class": "research-public"},
            }
        elif index == 2:
            body = {
                "kind": "uncertainty",
                "target": _ref("urn:migration:archive-set:delta"),
                "model": "interval-envelope",
                "parameters": {"lower_ppm": 120_000, "upper_ppm": 260_000, "coverage_ppm": 950_000},
                "basis": [_ref("urn:audit-sample:delta:one"), _ref("urn:audit-sample:delta:two")],
                "annotations": {"estimator": "heldout-independent"},
            }
        elif index == 3:
            body = {
                "kind": "claim",
                "predicate": "catalog.entry.matches-observation",
                "arguments": [_ref("urn:catalog:stellar-object:rx-19"), {"bands": ["infrared", "visible"]}],
                "answer_limit": 5,
                "annotations": {"ranking": "evidence-first"},
            }
        elif index == 4:
            body = {
                "kind": "question-plus-answer-schema",
                "question": {
                    "kind": "claim",
                    "predicate": "migration.batch.has-complete-checksums",
                    "arguments": [_ref("urn:migration-batch:omega:42")],
                },
                "answer_schema": "urn:answer-schema:checksum-audit:2",
                "constraints": [
                    {
                        "kind": "constraint",
                        "scope": "answer",
                        "mode": "hard",
                        "condition": {"include_missing": True, "maximum_rows": 20},
                    }
                ],
                "annotations": {"review_mode": "read-only"},
            }
        elif index == 5:
            body = goal
        elif index == 6:
            body = {
                "kind": "action",
                "capability": "catalog.preview-reconciliation",
                "arguments": {"goal": goal, "sample_limit": 24, "write_mode": "disabled"},
                "declared_effects": ["preview.generate"],
                "annotations": {"sandbox": True},
            }
        elif index == 7:
            body = {
                "kind": "commitment",
                "debtor": sender,
                "creditors": [recipient],
                "goal": goal,
                "expiry_ms": 3_600_000,
                "verifier": "independent.review.agent",
                "cancellation_rule": {"before_ms": 1_760_001_800_000, "notice": "signed-record"},
            }
        elif index == 8:
            body = {
                "kind": "resolution",
                "target": _ref("urn:commitment:archive-review:cycle-17"),
                "status": "completed",
                "result": {"verified_files": 147, "mismatches": 0, "manifest": _ref("urn:manifest:archive:cycle-17")},
                "evidence": [_ref("urn:audit-log:archive:cycle-17")],
                "annotations": {"resolver_policy": "two-reviewer"},
            }
        else:
            body = _ref("urn:ledger:research-record:withdrawn-17")

        message = {
            "id": _ood_uuid(f"message:{index}"),
            "session": _ood_uuid(f"session:{index // 2}"),
            "sender": sender,
            "recipients": [recipient],
            "act": act,
            "reply_to": _ood_uuid(f"parent:{index}") if act in {"COMMIT", "RESOLVE", "RETRACT"} else None,
            "schema": schemas[index % len(schemas)],
            "logical_clock": 10_000 + index * 17,
            "expires_ms": 0 if index % 2 == 0 else 1_800_000,
            "confidence_ppm": None if index in {4, 9} else 710_000 + index * 11_000,
            "expected": {
                "ASSERT": ["QUERY"], "QUERY": ["ASSERT", "RESOLVE"],
                "REQUEST": ["PROPOSE", "RESOLVE"], "PROPOSE": ["COMMIT", "RETRACT"],
                "COMMIT": ["RESOLVE"], "RESOLVE": [], "RETRACT": [],
            }[act],
            "body": body,
            "meta": {
                "evaluation_case": {"suite": FORMAT, "ordinal": index, "independent_content": True},
                "resource_ceiling": {"records": 200 + index, "seconds": 30 + index},
                "labels": ["ascii", "out-of-domain", topic],
            },
        }
        result.append(normalize_message(message))
    if len(result) != EXPECTED_OOD_MESSAGES:
        raise RuntimeError("out-of-domain corpus cardinality changed")
    if {message["act"] for message in result} != {
        "ASSERT", "QUERY", "REQUEST", "PROPOSE", "COMMIT", "RESOLVE", "RETRACT"
    }:
        raise RuntimeError("out-of-domain corpus lost act coverage")
    if any(not text.isascii() for message in result for text in _all_strings(message)):
        raise RuntimeError("out-of-domain corpus contains non-ASCII semantic text")
    _require_frozen("out-of-domain digest", corpus_digest(result), EXPECTED_OOD_SHA256)
    return tuple(result)


@lru_cache(maxsize=1)
def holdout_codebook() -> TokenCodebook:
    split = frozen_split()
    frames = [encode_v02(message) for message in split.train]
    codebook = TokenCodebook(
        corpus_sha256=corpus_digest(split.train),
        profile_dictionary_id=DEFAULT_PROFILE.dictionary_id,
        alphabet=SURFACE_ALPHABET,
        entries=_train_entries(frames, CODEBOOK_SYMBOLS),
    )
    _require_frozen("holdout codebook digest", codebook.sha256, EXPECTED_CODEBOOK_SHA256)
    return codebook


def _b64_v02_encode(message: Mapping[str, Any]) -> str:
    return base64.b64encode(encode_v02(message)).decode("ascii")


def _b64_v02_decode(text: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise DecodeError("invalid Base64 v0.2 text") from exc
    return decode_v02(raw)


def _json_text_encode(message: Mapping[str, Any]) -> str:
    return json_encode(message).decode("utf-8")


def _json_text_decode(text: str) -> dict[str, Any]:
    return json_decode(text.encode("utf-8"))


def codec_functions(codebook: TokenCodebook) -> dict[str, tuple[Callable[[Mapping[str, Any]], str], Callable[[str], dict[str, Any]]]]:
    return {
        "json": (_json_text_encode, _json_text_decode),
        "base64_v02": (_b64_v02_encode, _b64_v02_decode),
        "v03": (lambda message: encode_v03(message, codebook), lambda text: decode_v03(text, codebook)),
    }


def encoded_texts(messages: Sequence[Mapping[str, Any]], codebook: TokenCodebook) -> dict[str, list[str]]:
    return {
        name: [encoder(message) for message in messages]
        for name, (encoder, _decoder) in codec_functions(codebook).items()
    }


def fallback_stats(messages: Sequence[Mapping[str, Any]], codebook: TokenCodebook) -> FallbackStats:
    alphabet_index = {symbol: index for index, symbol in enumerate(codebook.alphabet)}
    payload_symbols = raw_symbols = frame_bytes = raw_bytes = messages_with_raw = 0
    for message in messages:
        surface = encode_v03(message, codebook)
        payload = surface[3:-SURFACE_CHECKSUM_SYMBOLS]
        indices = [alphabet_index[symbol] for symbol in payload]
        raw = sum(index < 256 for index in indices)
        payload_symbols += len(indices)
        raw_symbols += raw
        raw_bytes += raw
        frame_bytes += len(encode_v02(message))
        messages_with_raw += raw > 0
    return FallbackStats(
        len(messages), messages_with_raw, payload_symbols, raw_symbols, frame_bytes, raw_bytes
    )


def corruption_trials(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    codebook: TokenCodebook,
    *,
    trials_per_message: int = 4,
) -> tuple[int, int]:
    attempted = rejected = 0
    for dataset_name, messages in datasets.items():
        for message_index, message in enumerate(messages):
            surface = encode_v03(message, codebook)
            start, end = 3, len(surface) - SURFACE_CHECKSUM_SYMBOLS
            payload = list(surface[start:end])
            for trial in range(trials_per_message):
                position = int.from_bytes(
                    hashlib.sha256(
                        f"{FORMAT}|{dataset_name}|{message_index}|{trial}".encode()
                    ).digest()[:8],
                    "big",
                ) % len(payload)
                original = payload[position]
                symbol_index = codebook.alphabet.index(original)
                payload[position] = codebook.alphabet[(symbol_index + 1) % len(codebook.alphabet)]
                mutated = surface[:start] + "".join(payload) + surface[end:]
                attempted += 1
                try:
                    decode_v03(mutated, codebook)
                except DecodeError:
                    rejected += 1
                payload[position] = original
    return attempted, rejected


def frozen_vectors() -> dict[str, Any]:
    split = frozen_split()
    ood = build_out_of_domain_corpus()
    codebook = holdout_codebook()
    datasets = {"grouped holdout": split.holdout, "out of domain": ood}
    text_digests: dict[str, dict[str, str]] = {}
    fallback: dict[str, FallbackStats] = {}
    for dataset_name, messages in datasets.items():
        texts = encoded_texts(messages, codebook)
        text_digests[dataset_name] = {
            codec: _sequence_digest(values) for codec, values in texts.items()
        }
        for codec, digest in text_digests[dataset_name].items():
            _require_frozen(
                f"{dataset_name} {codec} text digest",
                digest,
                EXPECTED_TEXT_SHA256[dataset_name][codec],
            )
        fallback[dataset_name] = fallback_stats(messages, codebook)
    return {
        "english_corpus_sha256": corpus_digest(build_english_candidate_corpus()),
        "train_sha256": corpus_digest(split.train),
        "holdout_sha256": corpus_digest(split.holdout),
        "holdout_group_sha256": _sequence_digest(sorted(split.holdout_groups)),
        "ood_sha256": corpus_digest(ood),
        "codebook_sha256": codebook.sha256,
        "text_sha256": text_digests,
        "fallback": fallback,
    }


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _strict_break_even(cold: int, baseline_total: int, warm_total: int, count: int) -> int | None:
    saving = baseline_total - warm_total
    if saving <= 0:
        return None
    return cold * count // saving + 1


def _render_break(value: int | None) -> str:
    return "never on mean" if value is None else str(value)


def _pct(candidate: int, baseline: int) -> str:
    return f"{100 * (candidate / baseline - 1):+.1f}%"


def run_experiment(*, repeats: int = 10) -> str:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("experiment requires tiktoken 0.11.0") from exc
    if tiktoken.__version__ != TIKTOKEN_VERSION:
        raise RuntimeError(f"experiment requires tiktoken {TIKTOKEN_VERSION}")

    split = frozen_split()
    ood = build_out_of_domain_corpus()
    started = time.perf_counter()
    codebook = holdout_codebook()
    training_seconds = time.perf_counter() - started
    datasets: dict[str, Sequence[Mapping[str, Any]]] = {
        "grouped holdout": split.holdout,
        "out of domain": ood,
    }
    codecs = codec_functions(codebook)
    texts = {name: encoded_texts(messages, codebook) for name, messages in datasets.items()}
    encodings = {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}

    metrics: dict[str, dict[str, dict[str, int]]] = {}
    exact: dict[str, dict[str, int]] = {}
    deterministic: dict[str, dict[str, int]] = {}
    for dataset_name, messages in datasets.items():
        metrics[dataset_name] = {}
        exact[dataset_name] = {}
        deterministic[dataset_name] = {}
        for codec_name, (encoder, decoder) in codecs.items():
            values = texts[dataset_name][codec_name]
            metrics[dataset_name][codec_name] = {
                "bytes": sum(len(value.encode("utf-8")) for value in values),
                "characters": sum(len(value) for value in values),
                **{
                    tokenizer: sum(len(encoding.encode(value)) for value in values)
                    for tokenizer, encoding in encodings.items()
                },
            }
            exact[dataset_name][codec_name] = sum(
                decoder(value) == message
                for value, message in zip(values, messages, strict=True)
            )
            deterministic[dataset_name][codec_name] = sum(
                encoder(message) == value
                for value, message in zip(values, messages, strict=True)
            )
    if metrics != EXPECTED_WARM_METRICS:
        raise RuntimeError("frozen warm byte or token metrics changed")

    codebook_text = encode_codebook_capsule_text(codebook)
    profile_text = base64.b64encode(encode_v02_capsule(DEFAULT_PROFILE)).decode("ascii")
    cold = {
        "codebook": {
            "bytes": len(codebook_text.encode("utf-8")),
            **{name: len(encoding.encode(codebook_text)) for name, encoding in encodings.items()},
        },
        "profile": {
            "bytes": len(profile_text.encode("utf-8")),
            **{name: len(encoding.encode(profile_text)) for name, encoding in encodings.items()},
        },
    }
    observed_cold = {
        "codebook": {"binary_bytes": len(codebook.capsule), **cold["codebook"]},
        "profile": {"binary_bytes": len(encode_v02_capsule(DEFAULT_PROFILE)), **cold["profile"]},
    }
    if observed_cold != EXPECTED_COLD_METRICS:
        raise RuntimeError("frozen cold byte or token metrics changed")

    combined = tuple(split.holdout) + tuple(ood)
    latency: dict[str, tuple[list[int], list[int]]] = {}
    for codec_name, (encoder, decoder) in codecs.items():
        for message in combined[:6]:
            decoder(encoder(message))
        encoded = [encoder(message) for message in combined]
        encode_ns: list[int] = []
        decode_ns: list[int] = []
        gc_state = gc.isenabled()
        gc.disable()
        try:
            for _ in range(repeats):
                for message in combined:
                    tick = time.perf_counter_ns()
                    encoder(message)
                    encode_ns.append(time.perf_counter_ns() - tick)
            for _ in range(repeats):
                for value in encoded:
                    tick = time.perf_counter_ns()
                    decoder(value)
                    decode_ns.append(time.perf_counter_ns() - tick)
        finally:
            if gc_state:
                gc.enable()
        latency[codec_name] = encode_ns, decode_ns

    fallback = {name: fallback_stats(messages, codebook) for name, messages in datasets.items()}
    corruptions = corruption_trials(datasets, codebook)
    for dataset_name, stats in fallback.items():
        observed = (
            stats.messages,
            stats.messages_with_raw,
            stats.payload_symbols,
            stats.raw_symbols,
            stats.frame_bytes,
            stats.raw_bytes,
        )
        if observed != EXPECTED_FALLBACK[dataset_name]:
            raise RuntimeError(f"frozen fallback metrics changed for {dataset_name}")
    if corruptions != (EXPECTED_CORRUPTIONS, EXPECTED_CORRUPTIONS):
        raise RuntimeError("frozen corruption result changed")
    vectors = frozen_vectors()
    tokenizer_metrics = ("cl100k_base", "o200k_base")
    labels = {"json": "sorted minified JSON", "base64_v02": "Base64 UrusillaWire v0.2", "v03": "UrusillaTokenSurface v0.3 warm"}

    lines = [
        "# UrusillaTokenSurface v0.3 grouped holdout and generalization study",
        "",
        f"Execution time (UTC): `{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}`  ",
        f"Runtime: `{platform.python_implementation()} {platform.python_version()}` / `{platform.platform()}`  ",
        f"Tokenizer package: `tiktoken {tiktoken.__version__}` with `cl100k_base` and `o200k_base`  ",
        f"Source corpus: {CANDIDATE_MESSAGES} messages, SHA-256 `{EXPECTED_SOURCE_CORPUS_SHA256}`  ",
        f"English projection: SHA-256 `{vectors['english_corpus_sha256']}`  ",
        f"Development: {len(split.train)} messages in {len(split.train_groups)} groups, SHA-256 `{vectors['train_sha256']}`  ",
        f"Grouped holdout: {len(split.holdout)} messages in {len(split.holdout_groups)} groups, SHA-256 `{vectors['holdout_sha256']}`  ",
        f"Held group-list SHA-256: `{vectors['holdout_group_sha256']}`  ",
        f"Out-of-domain: {len(ood)} messages, SHA-256 `{vectors['ood_sha256']}`  ",
        f"Codebook: {len(codebook.entries):,} symbols, SHA-256 `{codebook.sha256}`, trained in {training_seconds:.3f}s  ",
        f"Timing repeats after warm-up: {repeats}",
        "",
        "## Design and leakage controls",
        "",
        "The fixed 280-message source corpus is first projected to ASCII English semantic content by replacing only its declared multilingual fixtures. The machine surface remains a negotiated non-ASCII alphabet by design. No content is selected by codec performance. A group key combines act, schema, body kind, and an act-specific semantic selector such as claim predicate, action capability, evidence stance, uncertainty model, or resolution status. Within each act, groups are ranked by SHA-256 under the exact domain `urusilla-token-surface-holdout-v1|`; the first `max(1, floor(group_count/4))` groups are held out. All messages in one group stay on one side, and every act appears in the holdout.",
        "",
        f"The v0.3 byte-pair entries are trained from the {len(split.train)} development v0.2 frames only. The {len(split.holdout)} grouped holdout frames and ten hand-authored out-of-domain frames are encoded only after the codebook is frozen. The out-of-domain corpus uses new schemas, agents, predicates, values, and map shapes while retaining the unchanged core validator.",
        "",
        "This is leakage-resistant relative to a random message split, not a blind external test. The split rule and group definition were authored after inspecting the generator; both partitions still use that generator. The v0.2 static profile and the v0.3 symbol alphabet were developed earlier using the same benchmark family and named tokenizers. The out-of-domain set is small and was authored in this repository.",
        "",
        "## Warm held-out results",
        "",
        "| Dataset | Codec | UTF-8 bytes | Characters | cl100k_base | o200k_base | Exact | Deterministic |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset_name, messages in datasets.items():
        for codec_name in ("json", "base64_v02", "v03"):
            row = metrics[dataset_name][codec_name]
            lines.append(
                f"| {dataset_name} | {labels[codec_name]} | {row['bytes']:,} | {row['characters']:,} | {row['cl100k_base']:,} | {row['o200k_base']:,} | {exact[dataset_name][codec_name]}/{len(messages)} | {deterministic[dataset_name][codec_name]}/{len(messages)} |"
            )
    lines.extend([
        "",
        "JSON is sorted, minified, UTF-8, and passed through the shared semantic validator on decode. Base64 contains each complete canonical v0.2 frame. Token counts are exact only for the two named encoding assets in tiktoken 0.11.0.",
        "",
        "Warm deltas for v0.3 (negative is smaller):",
        "",
        "| Dataset | Baseline | UTF-8 bytes | cl100k_base | o200k_base |",
        "|---|---|---:|---:|---:|",
    ])
    for dataset_name in datasets:
        for baseline in ("json", "base64_v02"):
            candidate = metrics[dataset_name]["v03"]
            reference = metrics[dataset_name][baseline]
            lines.append(
                f"| {dataset_name} | {labels[baseline]} | {_pct(candidate['bytes'], reference['bytes'])} | {_pct(candidate['cl100k_base'], reference['cl100k_base'])} | {_pct(candidate['o200k_base'], reference['o200k_base'])} |"
            )

    lines.extend([
        "",
        "## Raw fallback use",
        "",
        "A raw fallback symbol is one of the first 256 codebook entries and expands to exactly one frame byte. Symbol rate divides raw symbols by all v0.3 payload symbols. Byte coverage divides raw fallback bytes by the original v0.2 frame bytes.",
        "",
        "| Dataset | Messages with raw fallback | Raw symbols / payload symbols | Raw symbol rate | Raw bytes / frame bytes | Raw byte coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for dataset_name, stats in fallback.items():
        lines.append(
            f"| {dataset_name} | {stats.messages_with_raw}/{stats.messages} | {stats.raw_symbols:,}/{stats.payload_symbols:,} | {stats.symbol_rate:.1%} | {stats.raw_bytes:,}/{stats.frame_bytes:,} | {stats.byte_rate:.1%} |"
        )

    lines.extend([
        "",
        "## Cold cost and strict break-even",
        "",
        f"The canonical codebook capsule is {len(codebook.capsule):,} binary bytes. Its actual `S3C:` transfer is {cold['codebook']['bytes']:,} UTF-8 bytes, {cold['codebook']['cl100k_base']:,} cl100k_base tokens, and {cold['codebook']['o200k_base']:,} o200k_base tokens. The shared v0.2 profile capsule is {len(encode_v02_capsule(DEFAULT_PROFILE)):,} binary bytes; its Base64 transfer is {cold['profile']['bytes']:,} bytes, {cold['profile']['cl100k_base']:,} and {cold['profile']['o200k_base']:,} tokens.",
        "",
        "Strict break-even is the first integer N satisfying `cold + N * mean(v0.3) < N * mean(baseline)`. The incremental row charges the v0.3 codebook. The standalone JSON row also charges the v0.2 profile because JSON does not already have it. Results assume the measured held-out workload mix repeats.",
        "",
        "| Dataset | Baseline | Cold scenario | UTF-8 byte N | cl100k_base N | o200k_base N |",
        "|---|---|---|---:|---:|---:|",
    ])
    for dataset_name, messages in datasets.items():
        count = len(messages)
        candidate = metrics[dataset_name]["v03"]
        for baseline in ("json", "base64_v02"):
            reference = metrics[dataset_name][baseline]
            cold_values = dict(cold["codebook"])
            scenario = "incremental codebook"
            if baseline == "json":
                scenario = "standalone profile + codebook"
                cold_values = {key: cold["codebook"][key] + cold["profile"][key] for key in cold_values}
            breaks = [
                _strict_break_even(cold_values["bytes"], reference["bytes"], candidate["bytes"], count),
                _strict_break_even(cold_values["cl100k_base"], reference["cl100k_base"], candidate["cl100k_base"], count),
                _strict_break_even(cold_values["o200k_base"], reference["o200k_base"], candidate["o200k_base"], count),
            ]
            lines.append(
                f"| {dataset_name} | {labels[baseline]} | {scenario} | {_render_break(breaks[0])} | {_render_break(breaks[1])} | {_render_break(breaks[2])} |"
            )

    lines.extend([
        "",
        "## Codec latency on the combined evaluation set",
        "",
        "| Codec | Encode p50 (us) | Encode p95 (us) | Decode p50 (us) | Decode p95 (us) |",
        "|---|---:|---:|---:|---:|",
    ])
    for codec_name in ("json", "base64_v02", "v03"):
        enc, dec = latency[codec_name]
        lines.append(
            f"| {labels[codec_name]} | {_nearest(enc, .50)/1000:.2f} | {_nearest(enc, .95)/1000:.2f} | {_nearest(dec, .50)/1000:.2f} | {_nearest(dec, .95)/1000:.2f} |"
        )
    lines.extend([
        "",
        "These paths do unequal work. JSON has no transport checksum; v0.2 validates one canonical frame; v0.3 additionally performs longest-match substitution, its surface checksum, v0.2 decoding, and canonical re-encoding. Latency is an implementation-path measurement on this machine.",
        "",
        "## Integrity and frozen vectors",
        "",
        f"Deterministic single-symbol payload corruptions rejected: {corruptions[1]}/{corruptions[0]}. This is accidental-error detection, not authentication.",
        "",
        "| Dataset | JSON text SHA-256 | Base64 v0.2 text SHA-256 | v0.3 text SHA-256 |",
        "|---|---|---|---|",
    ])
    for dataset_name in datasets:
        row = vectors["text_sha256"][dataset_name]
        lines.append(f"| {dataset_name} | `{row['json']}` | `{row['base64_v02']}` | `{row['v03']}` |")
    lines.extend([
        "",
        "All three codecs round-trip through the unchanged validator and reproduce their text deterministically. Decoder tests also reject wrong codebooks, malformed Base64, corrupted capsules, altered surface symbols, and semantically invalid messages before any effect.",
        "",
        "## Interpretation and limitations",
        "",
        "The grouped holdout measures recombination of generator features, not a new real-world distribution. The out-of-domain set is structurally novel but too small for a generalization claim. Neither set measures natural-language construction, model comprehension, task success, repair turns, transport envelopes, authorization, or adversarial cryptography.",
        "",
        "The learned byte entries see development frames only, but the v0.2 profile still contains strings and shapes chosen from the benchmark family. The 1,024-symbol alphabet was preselected to be one token in both measured tokenizers, so this is not tokenizer holdout. Cold transfer, fallback, byte regressions, and slower v0.3 latency are retained rather than filtered. A production claim needs a preregistered split, independently authored schemas and messages, unseen tokenizers/models, and end-to-end task evidence.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python3 -m venv work/token-surface-holdout-venv",
        "work/token-surface-holdout-venv/bin/python -m pip install tiktoken==0.11.0",
        "PYTHONPATH=. work/token-surface-holdout-venv/bin/python urusilla_token_surface_holdout.py --benchmark --repeats 10",
        "PYTHONPATH=. work/token-surface-holdout-venv/bin/python -m unittest test_urusilla_token_surface_holdout.py -v",
        "```",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="run the frozen holdout study")
    parser.add_argument("--repeats", type=int, default=10, help="timing repeats from 1 to 100")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("urusilla_token_surface_holdout_results.md"),
        help="Markdown output path",
    )
    args = parser.parse_args(argv)
    if not args.benchmark:
        parser.error("choose --benchmark")
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be from 1 to 100")
    report = run_experiment(repeats=args.repeats)
    args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
