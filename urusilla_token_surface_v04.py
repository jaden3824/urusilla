#!/usr/bin/env python3
"""Globally optimal experimental token surface for Urusilla.

Version 0.4 keeps the already-frozen byte-string codebook and replaces greedy
longest-match parsing with a deterministic dynamic program.  The objective is
the minimum number of payload symbols for the complete binary frame.  Among
equally short parses, the lexicographically smallest sequence of codebook
indices wins.  This is a serialization experiment, not a language-model task
evaluation and not evidence of model understanding.

The first 256 codebook entries cover every byte, so every valid binary frame
has at least one parse.  Encoding is bounded by the shared maximum frame size.
Decoding rejects unknown symbols, expansion beyond that bound, checksum
failure, a mismatched negotiated slot, and any valid but non-canonical parse.
"""

from __future__ import annotations

import argparse
from array import array
import base64
from dataclasses import dataclass
import gc
import hashlib
import hmac
import io
import json
import math
from pathlib import Path
import platform
import statistics
import time
from typing import Any, Callable, Mapping, Sequence

# These imports temporarily bridge the new neutral experiment to the frozen
# implementation and research fixtures.  They do not alter those inputs.
from urusilla_benchmark import corpus_digest, json_decode, json_encode
from urusilla import DecodeError, MAX_FRAME_BYTES, ValidationError
from urusilla_token_surface_holdout import (
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_SHA256,
    EXPECTED_TRAIN_SHA256,
    _sequence_digest,
    build_out_of_domain_corpus,
    frozen_split,
    holdout_codebook,
)
from urusilla_token_surface_v03 import (
    MAX_PAYLOAD_SYMBOLS,
    MAX_SURFACE_UTF8_BYTES,
    SURFACE_CHECKSUM_BYTES,
    SURFACE_CHECKSUM_SYMBOLS,
    TokenCodebook,
    _decode_checksum_symbols,
    _decode_payload,
    _encode_bytes as encode_bytes_greedy,
    _encode_checksum_symbols,
    _encoding_trie,
    decode_message as decode_v03,
    encode_codebook_capsule_text as encode_v03_codebook_capsule_text,
    encode_message as encode_v03,
)
from urusilla_tokenizer_benchmark import (
    TIKTOKEN_VERSION,
    TOKENIZERS_VERSION,
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
    sha256_file,
)
from urusilla_wire_v02 import (
    DEFAULT_PROFILE,
    decode_message as decode_v02,
    encode_capsule as encode_profile_capsule,
    encode_message as encode_v02,
)
from urusilla_terse_english_benchmark import (
    decode_terse_english,
    encode_terse_english,
)


FORMAT = "urusilla-token-surface-v0.4-experimental"
REPORT_NAME = "TOKEN_SURFACE_V04_RESULTS.md"
SURFACE_PREFIX = "A4"
CODEBOOK_CAPSULE_PREFIX = "A4C:"
_SURFACE_DOMAIN = b"UrusillaTokenSurface-v0.4-frame\x00"

DATASET_LABELS = {
    "development": "development training partition",
    "grouped_holdout": "grouped holdout",
    "out_of_domain": "out of domain",
}
CODEC_LABELS = {
    "terse_english": "Controlled Terse English",
    "json": "sorted minified JSON",
    "base64_v02": "Base64 wire v0.2",
    "v03": "token surface v0.3",
    "v04": "token surface v0.4 optimal",
}

# These exact values freeze the first controlled run.  They are asserted by
# both the benchmark collector and the independent test module.
EXPECTED_V04_TEXT_SHA256: Mapping[str, str] = {
    "development": "f093946e0c57fe0d4396b3797c0e4f3b5b4b062e872f4e33f8dfc296f54702d2",
    "grouped_holdout": "7a0cc5bb0c1a7f172a6df5ca3f490769d91eaf406cbcd0654584880eb2da4f58",
    "out_of_domain": "bf5352bf5537ca7eea0b04482d432db6703c55cc96eb9445be27744197c7247a",
}
EXPECTED_V04_METRICS: Mapping[str, Mapping[str, int]] = {
    "development": {
        "bytes": 57_906,
        "characters": 23_792,
        "cl100k_base": 23_751,
        "o200k_base": 23_560,
        "qwen2_5_7b_instruct": 23_610,
        "mistral_7b_instruct_v03": 23_859,
    },
    "grouped_holdout": {
        "bytes": 15_368,
        "characters": 6_377,
        "cl100k_base": 6_362,
        "o200k_base": 6_310,
        "qwen2_5_7b_instruct": 6_333,
        "mistral_7b_instruct_v03": 6_412,
    },
    "out_of_domain": {
        "bytes": 11_465,
        "characters": 5_376,
        "cl100k_base": 5_361,
        "o200k_base": 5_011,
        "qwen2_5_7b_instruct": 5_353,
        "mistral_7b_instruct_v03": 5_368,
    },
}
EXPECTED_PAYLOAD_STATS: Mapping[str, Mapping[str, int]] = {
    "development": {
        "messages": 224,
        "frame_bytes": 46_146,
        "greedy_symbols": 21_571,
        "optimal_symbols": 21_552,
        "improved_messages": 19,
        "equal_messages": 205,
        "regressed_messages": 0,
        "maximum_symbol_reduction": 1,
        "greedy_raw_symbols": 15_135,
        "optimal_raw_symbols": 15_098,
    },
    "grouped_holdout": {
        "messages": 56,
        "frame_bytes": 11_525,
        "greedy_symbols": 5_822,
        "optimal_symbols": 5_817,
        "improved_messages": 4,
        "equal_messages": 52,
        "regressed_messages": 0,
        "maximum_symbol_reduction": 2,
        "greedy_raw_symbols": 4_204,
        "optimal_raw_symbols": 4_189,
    },
    "out_of_domain": {
        "messages": 10,
        "frame_bytes": 6_148,
        "greedy_symbols": 5_291,
        "optimal_symbols": 5_276,
        "improved_messages": 10,
        "equal_messages": 0,
        "regressed_messages": 0,
        "maximum_symbol_reduction": 3,
        "greedy_raw_symbols": 4_775,
        "optimal_raw_symbols": 4_760,
    },
}
EXPECTED_CORRUPTION_TRIALS = 1_160


@dataclass(frozen=True)
class PayloadStats:
    messages: int
    frame_bytes: int
    greedy_symbols: int
    optimal_symbols: int
    improved_messages: int
    equal_messages: int
    regressed_messages: int
    maximum_symbol_reduction: int
    greedy_raw_symbols: int
    optimal_raw_symbols: int


@dataclass(frozen=True)
class Study:
    datasets: Mapping[str, tuple[dict[str, Any], ...]]
    texts: Mapping[str, Mapping[str, tuple[str, ...]]]
    metrics: Mapping[str, Mapping[str, Mapping[str, int]]]
    cold: Mapping[str, Mapping[str, int]]
    payload: Mapping[str, PayloadStats]
    exact: Mapping[str, int]
    deterministic: Mapping[str, int]
    corruptions_attempted: int
    corruptions_rejected: int
    profiles: tuple[TokenizerProfile, ...]


def encode_bytes_optimal(raw: bytes, codebook: TokenCodebook) -> str:
    """Encode bytes with the globally minimum number of codebook symbols.

    Dynamic programming computes the exact shortest suffix length at every byte
    boundary.  A lower codebook index breaks equal-cost ties, which recursively
    yields the lexicographically smallest index sequence among all shortest
    parses.
    """

    if not isinstance(raw, bytes):
        raise TypeError("optimizer input must be bytes")
    if len(raw) > MAX_FRAME_BYTES:
        raise ValidationError("optimizer input exceeds the frame-size limit")
    if not raw:
        return ""

    trie = _encoding_trie(codebook)
    size = len(raw)
    unreachable = size + 1
    # Only the next MAX_ENTRY_BYTES suffix costs are reachable from the current
    # boundary, so a circular window preserves exactness without a full cost
    # array.  One unsigned 16-bit choice per byte is sufficient for <=1,024
    # codebook entries.  This bounds auxiliary memory near 2 bytes/input byte.
    window_size = max(len(entry) for entry in codebook.entries) + 1
    # The rolling window has at most 1,025 entries, so a native integer list is
    # faster here without making memory depend materially on frame size.
    future_cost = [unreachable] * window_size
    choice_index = array("H", [0]) * size
    future_cost[size % window_size] = 0

    for position in range(size - 1, -1, -1):
        node = trie
        scan = position
        best_cost = unreachable
        best_index = len(codebook.entries)
        best_end = -1
        while scan < size and raw[scan] in node:
            node = node[raw[scan]]
            scan += 1
            symbol_index = node.get(None)
            if symbol_index is None:
                continue
            candidate_cost = 1 + future_cost[scan % window_size]
            if (candidate_cost, symbol_index) < (best_cost, best_index):
                best_cost = candidate_cost
                best_index = symbol_index
                best_end = scan
        if best_end < 0:
            raise RuntimeError("frozen codebook lost complete byte coverage")
        future_cost[position % window_size] = best_cost
        choice_index[position] = best_index

    optimum = future_cost[0]
    position = 0
    output_symbols = 0
    if size <= 1024 * 1024:
        symbols: list[str] = []
        while position < size:
            symbol_index = choice_index[position]
            symbols.append(codebook.alphabet[symbol_index])
            position += len(codebook.entries[symbol_index])
            output_symbols += 1
        output = "".join(symbols)
    else:
        stream = io.StringIO()
        while position < size:
            symbol_index = choice_index[position]
            stream.write(codebook.alphabet[symbol_index])
            position += len(codebook.entries[symbol_index])
            output_symbols += 1
        output = stream.getvalue()
    if output_symbols != optimum:
        raise RuntimeError("optimizer reconstruction disagrees with its optimum")
    return output


def encode_message(
    message: Mapping[str, Any], codebook: TokenCodebook, *, slot: int = 0
) -> str:
    """Return the canonical v0.4 text surface for one valid message."""

    if type(slot) is not int or not 0 <= slot < len(codebook.alphabet):
        raise ValidationError("negotiated codebook slot is outside the allowed range")
    frame = encode_v02(message)
    payload = encode_bytes_optimal(frame, codebook)
    checksum = hashlib.blake2s(
        _SURFACE_DOMAIN + bytes.fromhex(codebook.sha256) + frame,
        digest_size=SURFACE_CHECKSUM_BYTES,
    ).digest()
    surface = (
        SURFACE_PREFIX
        + codebook.alphabet[slot]
        + payload
        + _encode_checksum_symbols(checksum, codebook)
    )
    if len(surface.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise ValidationError("surface text exceeds the UTF-8 size limit")
    return surface


def decode_message(
    surface: str, codebook: TokenCodebook, *, slot: int = 0
) -> dict[str, Any]:
    """Decode, validate, and reject non-canonical v0.4 surfaces."""

    if type(slot) is not int or not 0 <= slot < len(codebook.alphabet):
        raise DecodeError("negotiated codebook slot is outside the allowed range")
    if not isinstance(surface, str):
        raise DecodeError("surface must be text")
    if len(surface.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise DecodeError("surface text exceeds the UTF-8 size limit")
    minimum = len(SURFACE_PREFIX) + 1 + 1 + SURFACE_CHECKSUM_SYMBOLS
    if len(surface) < minimum or not surface.startswith(SURFACE_PREFIX):
        raise DecodeError("unknown or malformed token surface")
    if surface[len(SURFACE_PREFIX)] != codebook.alphabet[slot]:
        raise DecodeError("surface codebook slot does not match the negotiated binding")

    payload = surface[len(SURFACE_PREFIX) + 1 : -SURFACE_CHECKSUM_SYMBOLS]
    if len(payload) > MAX_PAYLOAD_SYMBOLS:
        raise DecodeError("surface payload exceeds the symbol limit")
    checksum_text = surface[-SURFACE_CHECKSUM_SYMBOLS:]
    frame = _decode_payload(payload, codebook)
    expected = hashlib.blake2s(
        _SURFACE_DOMAIN + bytes.fromhex(codebook.sha256) + frame,
        digest_size=SURFACE_CHECKSUM_BYTES,
    ).digest()
    supplied = _decode_checksum_symbols(checksum_text, codebook)
    if not hmac.compare_digest(supplied, expected):
        raise DecodeError("surface checksum mismatch")
    message = decode_v02(frame)
    if encode_message(message, codebook, slot=slot) != surface:
        raise DecodeError("surface is valid but not canonical")
    return message


def encode_codebook_capsule_text(codebook: TokenCodebook) -> str:
    """Wrap the frozen binary codebook in a neutral text-transfer prefix."""

    encoded = base64.urlsafe_b64encode(codebook.capsule).decode("ascii").rstrip("=")
    return CODEBOOK_CAPSULE_PREFIX + encoded


def _base64_encode(message: Mapping[str, Any]) -> str:
    return base64.b64encode(encode_v02(message)).decode("ascii")


def _base64_decode(text: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise DecodeError("invalid Base64 frame") from exc
    return decode_v02(raw)


def _json_encode(message: Mapping[str, Any]) -> str:
    return json_encode(message).decode("utf-8")


def _json_decode(text: str) -> dict[str, Any]:
    return json_decode(text.encode("utf-8"))


def build_datasets() -> dict[str, tuple[dict[str, Any], ...]]:
    """Return the frozen training partition, grouped holdout, and small OOD set."""

    split = frozen_split()
    result = {
        "development": tuple(split.train),
        "grouped_holdout": tuple(split.holdout),
        "out_of_domain": tuple(build_out_of_domain_corpus()),
    }
    expected = {
        "development": EXPECTED_TRAIN_SHA256,
        "grouped_holdout": EXPECTED_HOLDOUT_SHA256,
        "out_of_domain": EXPECTED_OOD_SHA256,
    }
    for key, messages in result.items():
        if corpus_digest(messages) != expected[key]:
            raise RuntimeError(f"frozen {key} corpus changed")
    return result


def codec_functions(
    codebook: TokenCodebook,
) -> dict[str, tuple[Callable[[Mapping[str, Any]], str], Callable[[str], dict[str, Any]]]]:
    return {
        "terse_english": (encode_terse_english, decode_terse_english),
        "json": (_json_encode, _json_decode),
        "base64_v02": (_base64_encode, _base64_decode),
        "v03": (
            lambda message: encode_v03(message, codebook),
            lambda text: decode_v03(text, codebook),
        ),
        "v04": (
            lambda message: encode_message(message, codebook),
            lambda text: decode_message(text, codebook),
        ),
    }


def build_texts(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]], codebook: TokenCodebook
) -> dict[str, dict[str, tuple[str, ...]]]:
    codecs = codec_functions(codebook)
    return {
        dataset: {
            codec: tuple(encoder(message) for message in messages)
            for codec, (encoder, _decoder) in codecs.items()
        }
        for dataset, messages in datasets.items()
    }


def _measure(
    texts: Mapping[str, Mapping[str, Sequence[str]]],
    profiles: Sequence[TokenizerProfile],
) -> dict[str, dict[str, dict[str, int]]]:
    return {
        dataset: {
            codec: {
                "bytes": sum(len(value.encode("utf-8")) for value in values),
                "characters": sum(len(value) for value in values),
                **{
                    profile.key: sum(profile.count(value) for value in values)
                    for profile in profiles
                },
            }
            for codec, values in serializations.items()
        }
        for dataset, serializations in texts.items()
    }


def _cold_metrics(
    codebook: TokenCodebook, profiles: Sequence[TokenizerProfile]
) -> dict[str, dict[str, int]]:
    values = {
        "profile": base64.b64encode(encode_profile_capsule(DEFAULT_PROFILE)).decode("ascii"),
        "v03_codebook": encode_v03_codebook_capsule_text(codebook),
        "v04_codebook": encode_codebook_capsule_text(codebook),
    }
    return {
        key: {
            "bytes": len(value.encode("utf-8")),
            "characters": len(value),
            **{profile.key: profile.count(value) for profile in profiles},
        }
        for key, value in values.items()
    }


def _payload_stats(
    messages: Sequence[Mapping[str, Any]], codebook: TokenCodebook
) -> PayloadStats:
    frame_bytes = greedy_symbols = optimal_symbols = 0
    improved = equal = regressed = maximum = 0
    greedy_raw = optimal_raw = 0
    alphabet_index = {symbol: index for index, symbol in enumerate(codebook.alphabet)}
    for message in messages:
        frame = encode_v02(message)
        greedy = encode_bytes_greedy(frame, codebook)
        optimal = encode_bytes_optimal(frame, codebook)
        delta = len(greedy) - len(optimal)
        improved += delta > 0
        equal += delta == 0
        regressed += delta < 0
        maximum = max(maximum, delta)
        frame_bytes += len(frame)
        greedy_symbols += len(greedy)
        optimal_symbols += len(optimal)
        greedy_raw += sum(alphabet_index[symbol] < 256 for symbol in greedy)
        optimal_raw += sum(alphabet_index[symbol] < 256 for symbol in optimal)
    return PayloadStats(
        messages=len(messages),
        frame_bytes=frame_bytes,
        greedy_symbols=greedy_symbols,
        optimal_symbols=optimal_symbols,
        improved_messages=improved,
        equal_messages=equal,
        regressed_messages=regressed,
        maximum_symbol_reduction=maximum,
        greedy_raw_symbols=greedy_raw,
        optimal_raw_symbols=optimal_raw,
    )


def corruption_trials(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    codebook: TokenCodebook,
    *,
    trials_per_message: int = 4,
) -> tuple[int, int]:
    attempted = rejected = 0
    alphabet_index = {symbol: index for index, symbol in enumerate(codebook.alphabet)}
    for dataset, messages in datasets.items():
        for message_index, message in enumerate(messages):
            surface = encode_message(message, codebook)
            start = len(SURFACE_PREFIX) + 1
            end = len(surface) - SURFACE_CHECKSUM_SYMBOLS
            payload = list(surface[start:end])
            for trial in range(trials_per_message):
                digest = hashlib.sha256(
                    f"{FORMAT}|{dataset}|{message_index}|{trial}".encode("utf-8")
                ).digest()
                position = int.from_bytes(digest[:8], "big") % len(payload)
                original = payload[position]
                index = alphabet_index[original]
                payload[position] = codebook.alphabet[(index + 1) % len(codebook.alphabet)]
                mutated = surface[:start] + "".join(payload) + surface[end:]
                attempted += 1
                try:
                    decode_message(mutated, codebook)
                except DecodeError:
                    rejected += 1
                payload[position] = original
    return attempted, rejected


def collect_study(profiles: Sequence[TokenizerProfile]) -> Study:
    codebook = holdout_codebook()
    datasets = build_datasets()
    texts = build_texts(datasets, codebook)
    metrics = _measure(texts, profiles)
    payload = {key: _payload_stats(messages, codebook) for key, messages in datasets.items()}
    exact: dict[str, int] = {}
    deterministic: dict[str, int] = {}
    for key, messages in datasets.items():
        values = texts[key]["v04"]
        exact[key] = sum(
            decode_message(value, codebook) == message
            for value, message in zip(values, messages, strict=True)
        )
        deterministic[key] = sum(
            encode_message(message, codebook) == value
            for value, message in zip(values, messages, strict=True)
        )
    corruptions = corruption_trials(datasets, codebook)
    result = Study(
        datasets=datasets,
        texts=texts,
        metrics=metrics,
        cold=_cold_metrics(codebook, profiles),
        payload=payload,
        exact=exact,
        deterministic=deterministic,
        corruptions_attempted=corruptions[0],
        corruptions_rejected=corruptions[1],
        profiles=tuple(profiles),
    )

    if EXPECTED_V04_TEXT_SHA256:
        observed = {key: _sequence_digest(values["v04"]) for key, values in texts.items()}
        if observed != EXPECTED_V04_TEXT_SHA256:
            raise RuntimeError("frozen v0.4 text vectors changed")
    if EXPECTED_V04_METRICS:
        observed_metrics = {key: value["v04"] for key, value in metrics.items()}
        if observed_metrics != EXPECTED_V04_METRICS:
            raise RuntimeError("frozen v0.4 byte or token metrics changed")
    if EXPECTED_PAYLOAD_STATS:
        observed_payload = {key: value.__dict__ for key, value in payload.items()}
        if observed_payload != EXPECTED_PAYLOAD_STATS:
            raise RuntimeError("frozen optimal-parser metrics changed")
    if EXPECTED_CORRUPTION_TRIALS and corruptions != (
        EXPECTED_CORRUPTION_TRIALS,
        EXPECTED_CORRUPTION_TRIALS,
    ):
        raise RuntimeError("frozen corruption result changed")
    if any(value.regressed_messages for value in payload.values()):
        raise RuntimeError("optimal parser used more symbols than greedy parsing")
    return result


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def measure_latency(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    codebook: TokenCodebook,
    *,
    repeats: int,
) -> dict[str, dict[str, int]]:
    combined = tuple(message for messages in datasets.values() for message in messages)
    codecs = codec_functions(codebook)
    result: dict[str, dict[str, int]] = {}
    for codec, (encoder, decoder) in codecs.items():
        for message in combined[:6]:
            decoder(encoder(message))
        encoded = [encoder(message) for message in combined]
        encode_ns: list[int] = []
        decode_ns: list[int] = []
        gc_enabled = gc.isenabled()
        gc.disable()
        try:
            for _ in range(repeats):
                for message in combined:
                    started = time.perf_counter_ns()
                    encoder(message)
                    encode_ns.append(time.perf_counter_ns() - started)
            for _ in range(repeats):
                for value in encoded:
                    started = time.perf_counter_ns()
                    decoder(value)
                    decode_ns.append(time.perf_counter_ns() - started)
        finally:
            if gc_enabled:
                gc.enable()
        result[codec] = {
            "encode_median_ns": int(statistics.median(encode_ns)),
            "encode_p95_ns": _nearest(encode_ns, 0.95),
            "decode_median_ns": int(statistics.median(decode_ns)),
            "decode_p95_ns": _nearest(decode_ns, 0.95),
        }
    return result


def _saved(candidate: int, baseline: int) -> float:
    return 100.0 * (1.0 - candidate / baseline)


def _saved_text(candidate: int, baseline: int) -> str:
    return f"{_saved(candidate, baseline):+.2f}%"


def _strict_break_even(
    cold: int, baseline_total: int, candidate_total: int, count: int
) -> int | None:
    saving = baseline_total - candidate_total
    if saving <= 0:
        return None
    return cold * count // saving + 1


def _break_text(value: int | None) -> str:
    return "never on mean" if value is None else f"{value:,}"


def _cold_for(study: Study, codec: str, metric: str) -> int:
    profile = study.cold["profile"][metric]
    if codec == "base64_v02":
        return profile
    if codec == "v03":
        return profile + study.cold["v03_codebook"][metric]
    if codec == "v04":
        return profile + study.cold["v04_codebook"][metric]
    return 0


def _comparison_counts(
    candidate: Sequence[str], baseline: Sequence[str], measure: Callable[[str], int]
) -> tuple[int, int, int, float]:
    improved = equal = regressed = 0
    worst = 0.0
    for left, right in zip(candidate, baseline, strict=True):
        candidate_value = measure(left)
        baseline_value = measure(right)
        improved += candidate_value < baseline_value
        equal += candidate_value == baseline_value
        regressed += candidate_value > baseline_value
        if baseline_value:
            worst = max(worst, 100.0 * (candidate_value / baseline_value - 1.0))
    return improved, equal, regressed, worst


def _source_digest(name: str) -> str:
    path = Path(__file__).with_name(name)
    return sha256_file(path) if path.is_file() else "not-present"


def render_report(
    study: Study,
    latency: Mapping[str, Mapping[str, int]],
    asset_root: Path,
) -> str:
    measures = ("bytes",) + tuple(profile.key for profile in study.profiles)
    labels = {
        "bytes": "UTF-8 bytes",
        **{profile.key: profile.display_name for profile in study.profiles},
    }
    total_messages = sum(len(messages) for messages in study.datasets.values())
    total_improved = sum(value.improved_messages for value in study.payload.values())
    total_greedy = sum(value.greedy_symbols for value in study.payload.values())
    total_optimal = sum(value.optimal_symbols for value in study.payload.values())
    total_payload_saving = _saved(total_optimal, total_greedy)

    lines = [
        "# Token surface v0.4: globally optimal symbol parsing",
        "",
        "## Result",
        "",
        f"The globally optimal parser improved **{total_improved}/{total_messages} messages** and reduced payload symbols from **{total_greedy:,} to {total_optimal:,} ({total_payload_saving:.3f}% saved)** across the frozen development, grouped-holdout, and small out-of-domain sets. It never used more payload symbols than greedy longest-match parsing. This guarantee applies to symbol count only; UTF-8 bytes, tokenizer counts, and latency are measured separately below and retain every unfavorable result.",
        "",
        f"Exact canonical recovery and deterministic re-encoding both passed for **{sum(study.exact.values())}/{total_messages} messages**. Deterministic single-symbol mutations were rejected in **{study.corruptions_rejected:,}/{study.corruptions_attempted:,} trials**.",
        "",
        "This is serialization accounting, not an end-to-end agent benchmark. No model decoded these surfaces, and the study does not measure task success, repair quality, reasoning, generation, energy, or adoption. It does not establish the highest performance among other projects.",
        "",
        "## Optimization rule",
        "",
        "For every byte boundary, the encoder evaluates every codebook entry that begins there and records `1 + shortest_suffix[next_boundary]`. It selects the lowest total and breaks a tie with the lower current codebook index. Because suffix choices use the same rule, the result is the lexicographically smallest index sequence among all minimum-symbol parses. Complete one-byte fallback entries make every valid frame reachable.",
        "",
        f"The codebook is unchanged. All three datasets use the same frozen codebook trained only on the {len(study.datasets['development'])}-message development partition; grouped holdout and out-of-domain messages were not used to train it.",
        "",
        "## Payload-level effect",
        "",
        "Payload statistics exclude the two-character format prefix, one negotiated slot symbol, and seven checksum symbols.",
        "",
        "| Dataset | Messages | Frame bytes | Greedy symbols | Optimal symbols | Saved | Improved / equal / worse | Max reduction | Greedy raw fallback | Optimal raw fallback |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, stats in study.payload.items():
        lines.append(
            f"| {DATASET_LABELS[key]} | {stats.messages:,} | {stats.frame_bytes:,} | "
            f"{stats.greedy_symbols:,} | {stats.optimal_symbols:,} | "
            f"{_saved_text(stats.optimal_symbols, stats.greedy_symbols)} | "
            f"{stats.improved_messages}/{stats.equal_messages}/{stats.regressed_messages} | "
            f"{stats.maximum_symbol_reduction} | {stats.greedy_raw_symbols:,} | "
            f"{stats.optimal_raw_symbols:,} |"
        )

    lines.extend([
        "",
        "## Exact warm sizes and tokenizer counts",
        "",
        "Every message is counted independently without BOS/EOS, chat templates, role markers, transport envelopes, prompts, or retransmissions.",
        "",
    ])
    for dataset, messages in study.datasets.items():
        lines.extend([
            f"### {DATASET_LABELS[dataset].title()}",
            "",
            "| Representation | UTF-8 bytes | Characters | "
            + " | ".join(profile.display_name for profile in study.profiles)
            + " |",
            "|---|---:|---:|" + "---:|" * len(study.profiles),
        ])
        for codec in CODEC_LABELS:
            metric = study.metrics[dataset][codec]
            lines.append(
                f"| {CODEC_LABELS[codec]} | {metric['bytes']:,} | {metric['characters']:,} | "
                + " | ".join(f"{metric[profile.key]:,}" for profile in study.profiles)
                + " |"
            )
        lines.extend([
            "",
            "v0.4 savings (positive is smaller; negative is an unfavorable regression):",
            "",
            "| Baseline | UTF-8 bytes | "
            + " | ".join(profile.display_name for profile in study.profiles)
            + " |",
            "|---|---:|" + "---:|" * len(study.profiles),
        ])
        candidate = study.metrics[dataset]["v04"]
        for baseline_codec in ("v03", "base64_v02", "json", "terse_english"):
            baseline = study.metrics[dataset][baseline_codec]
            lines.append(
                f"| {CODEC_LABELS[baseline_codec]} | {_saved_text(candidate['bytes'], baseline['bytes'])} | "
                + " | ".join(
                    _saved_text(candidate[profile.key], baseline[profile.key])
                    for profile in study.profiles
                )
                + " |"
            )
        lines.append("")

    lines.extend([
        "## Per-message unfavorable cases against v0.3",
        "",
        "Aggregate savings can hide regressions. The table counts each message separately; worst regression is the largest percentage by which v0.4 exceeded v0.3 for that metric.",
        "",
        "| Dataset | Metric | Improved | Equal | Regressed | Worst regression |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for dataset in study.datasets:
        for measure in measures:
            if measure == "bytes":
                counter = lambda text: len(text.encode("utf-8"))
            else:
                profile = next(item for item in study.profiles if item.key == measure)
                counter = profile.count
            improved, equal, regressed, worst = _comparison_counts(
                study.texts[dataset]["v04"], study.texts[dataset]["v03"], counter
            )
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {labels[measure]} | {improved} | {equal} | {regressed} | {worst:+.2f}% |"
            )

    lines.extend([
        "",
        "## Cold transfer and strict break-even",
        "",
        "Controlled Terse English and JSON have no negotiated capsule in this accounting. Base64 v0.2 uses the static profile once. Each token surface uses that profile plus its text-wrapped copy of the same frozen binary codebook. Decoder software and the public specification are treated as installed.",
        "",
        "| Capsule | UTF-8 bytes | Characters | "
        + " | ".join(profile.display_name for profile in study.profiles)
        + " |",
        "|---|---:|---:|" + "---:|" * len(study.profiles),
    ])
    for capsule in ("profile", "v03_codebook", "v04_codebook"):
        metric = study.cold[capsule]
        label = {
            "profile": "static profile",
            "v03_codebook": "v0.3 codebook wrapper",
            "v04_codebook": "v0.4 codebook wrapper",
        }[capsule]
        lines.append(
            f"| {label} | {metric['bytes']:,} | {metric['characters']:,} | "
            + " | ".join(f"{metric[profile.key]:,}" for profile in study.profiles)
            + " |"
        )
    lines.extend([
        "",
        "Strict break-even is the first integer `N` satisfying `cold + N × candidate_mean < N × baseline_mean`. `never on mean` is retained when the warm candidate is not smaller.",
        "",
        "| Dataset | Candidate | Baseline | "
        + " | ".join(labels[measure] for measure in measures)
        + " |",
        "|---|---|---|" + "---:|" * len(measures),
    ])
    for dataset, messages in study.datasets.items():
        count = len(messages)
        for candidate_codec in ("v03", "v04"):
            for baseline_codec in ("terse_english", "json"):
                values = []
                for measure in measures:
                    values.append(
                        _strict_break_even(
                            _cold_for(study, candidate_codec, measure),
                            study.metrics[dataset][baseline_codec][measure],
                            study.metrics[dataset][candidate_codec][measure],
                            count,
                        )
                    )
                lines.append(
                    f"| {DATASET_LABELS[dataset]} | {CODEC_LABELS[candidate_codec]} | "
                    f"{CODEC_LABELS[baseline_codec]} | "
                    + " | ".join(_break_text(value) for value in values)
                    + " |"
                )

    lines.extend([
        "",
        "## Reference implementation latency",
        "",
        "Times are per message on this machine. Paths do unequal work, and these Python measurements are not protocol limits. v0.4 performs a whole-frame dynamic program during encoding and also repeats it during canonical decoding, so slower latency is expected and must be weighed against any token reduction.",
        "",
        "| Representation | Encode median | Encode p95 | Decode median | Decode p95 |",
        "|---|---:|---:|---:|---:|",
    ])
    for codec in CODEC_LABELS:
        value = latency[codec]
        lines.append(
            f"| {CODEC_LABELS[codec]} | {value['encode_median_ns'] / 1000:.1f} µs | "
            f"{value['encode_p95_ns'] / 1000:.1f} µs | "
            f"{value['decode_median_ns'] / 1000:.1f} µs | "
            f"{value['decode_p95_ns'] / 1000:.1f} µs |"
        )

    lines.extend([
        "",
        "## Safety and exactness checks",
        "",
        f"- Exact decoded-object equality: {sum(study.exact.values()):,}/{total_messages:,}.",
        f"- Deterministic canonical re-encoding: {sum(study.deterministic.values()):,}/{total_messages:,}.",
        f"- Deterministic one-symbol corruption rejection: {study.corruptions_rejected:,}/{study.corruptions_attempted:,}.",
        "- The decoder checks the negotiated slot, allowed alphabet, payload-symbol bound, decoded-frame bound, checksum, binary-frame validation, and canonical optimal re-encoding.",
        "- The encoder rejects input beyond the shared 16 MiB binary-frame bound. This reference implementation stores choices in a compact unsigned array and suffix costs in a bounded rolling window; memory remains linear in frame length because exact reconstruction retains one choice per byte boundary.",
        "- Surface text is data, not executable instructions or authorization.",
        "",
        "## Frozen inputs and tokenizer identities",
        "",
        f"- Format: `{FORMAT}`",
        f"- Development training partition: {len(study.datasets['development'])} messages; canonical SHA-256 `{EXPECTED_TRAIN_SHA256}`",
        f"- Grouped holdout: {len(study.datasets['grouped_holdout'])} messages; canonical SHA-256 `{EXPECTED_HOLDOUT_SHA256}`",
        f"- Out of domain: {len(study.datasets['out_of_domain'])} messages; canonical SHA-256 `{EXPECTED_OOD_SHA256}`",
        f"- Frozen codebook SHA-256: `{holdout_codebook().sha256}`",
        f"- Tokenizer packages: `tiktoken=={TIKTOKEN_VERSION}`, `tokenizers=={TOKENIZERS_VERSION}`",
        "",
    ])
    for profile in study.profiles:
        lines.append(
            f"- `{profile.key}`: {profile.display_name}; {profile.implementation}; vocabulary {profile.vocabulary_size:,}; fingerprint `{profile.fingerprint}`"
        )
    lines.extend([
        "",
        "v0.4 text-sequence SHA-256 values use an eight-byte big-endian length before every UTF-8 message:",
        "",
    ])
    for dataset in study.datasets:
        lines.append(f"- {DATASET_LABELS[dataset]}: `{_sequence_digest(study.texts[dataset]['v04'])}`")
    lines.extend([
        "",
        "Source SHA-256 values:",
        "",
        f"- optimizer and benchmark: `{_source_digest('urusilla_token_surface_v04.py')}`",
        f"- conformance tests: `{_source_digest('test_urusilla_token_surface_v04.py')}`",
        "",
        "Environment:",
        "",
        f"- Python: `{platform.python_version()}`",
        f"- Platform: `{platform.platform()}`",
        "",
        "Reproduce from the repository root after installing the pinned tokenizer packages and verified assets:",
        "",
        "```bash",
        "PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_token_surface_v04.py --benchmark --assets-dir work/tokenizer_assets",
        "PYTHONPATH=. work/tokenizer_venv/bin/python -m unittest test_urusilla_token_surface_v04.py -v",
        "```",
        "",
        "## Limitations",
        "",
        "- Development results are in-sample because that partition trained the frozen codebook. Grouped holdout is synthetic and related to the same generator. The out-of-domain set has only ten repository-authored messages.",
        "- The objective minimizes payload symbols, not UTF-8 bytes, a specific tokenizer's tokens, latency, or end-to-end cost. Header and checksum changes also mean whole-surface v0.3/v0.4 token differences are not a perfectly isolated parser ablation; the payload-symbol table is the isolated comparison.",
        "- The alphabet was selected earlier around two named tokenizers. The two open-model tokenizers are useful transfer checks, not a representative sample of every deployed model.",
        "- Controlled Terse English is deterministic compact notation, not ordinary agent conversation. Exact recovery does not prove that a language model can use either representation.",
        "- Cold break-even assumes stable workload mix, successful caching and negotiation, no repair, and no retransmission.",
        "- Token counts do not directly measure energy, latency, KV-cache behavior, hosted billing, or communication success.",
        "",
    ])
    return "\n".join(lines)


def _dump_payload(study: Study, latency: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    return {
        "v04_text_sha256": {
            key: _sequence_digest(values["v04"]) for key, values in study.texts.items()
        },
        "v04_metrics": {key: values["v04"] for key, values in study.metrics.items()},
        "payload_stats": {key: value.__dict__ for key, value in study.payload.items()},
        "corruption_trials": {
            "attempted": study.corruptions_attempted,
            "rejected": study.corruptions_rejected,
        },
        "latency_ns": latency,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--assets-dir", type=Path, default=default_asset_root())
    parser.add_argument("--report", type=Path, default=Path(__file__).with_name(REPORT_NAME))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--dump-metrics", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.benchmark:
        raise SystemExit("choose --benchmark")
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")
    profiles = load_tokenizer_profiles(args.assets_dir)
    study = collect_study(profiles)
    latency = measure_latency(study.datasets, holdout_codebook(), repeats=args.repeats)
    report = render_report(study, latency, args.assets_dir)
    args.report.write_text(report, encoding="utf-8")
    if args.dump_metrics:
        print(json.dumps(_dump_payload(study, latency), indent=2, sort_keys=True))
    else:
        print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
