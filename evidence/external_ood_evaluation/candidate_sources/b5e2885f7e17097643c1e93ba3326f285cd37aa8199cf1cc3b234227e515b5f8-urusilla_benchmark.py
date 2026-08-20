#!/usr/bin/env python3
"""Reproducible transport benchmark for the Urusilla v0.1 reference codec.

The benchmark intentionally measures a narrow question: how much wire space and
local codec time are required to preserve an already-constructed Urusilla semantic
message?  It does not measure task success, LLM tokens, schema-distribution
cost, or the quality/cost of translating natural language into UrusillaIR.

No dependency is installed.  A deterministic-CBOR baseline is added only when
``cbor2`` is already importable.  A Protobuf baseline is reported as unavailable
unless this project later supplies a schema-equivalent generated message type;
using a generic Struct or wrapping JSON bytes would not be a fair comparison.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

from urusilla_deterministic_gzip import compress as deterministic_gzip_compress
from urusilla import (
    UrusillaError,
    decode_message,
    encode_message,
    normalize_message,
)


CORPUS_VERSION = "urusilla-benchmark-corpus-v1"
DEFAULT_MESSAGES = 280
DEFAULT_REPEATS = 20
DEFAULT_WARMUPS = 2
DEFAULT_CORRUPTIONS = 4
UUID_NAMESPACE = uuid.UUID("a76da12e-f58a-5ea3-8f9a-3f542304f9f0")


JsonMap = dict[str, Any]
Encoder = Callable[[Mapping[str, Any]], bytes]
Decoder = Callable[[bytes], JsonMap]


@dataclass(frozen=True)
class Codec:
    name: str
    encode: Encoder
    decode: Decoder
    notes: str


@dataclass
class CodecResult:
    name: str
    sizes: list[int]
    encode_ns: list[int]
    decode_ns: list[int]
    exact_messages: int
    canonical_frames: int
    corruption_rejected: int
    corruption_silent_change: int
    corruption_unchanged: int
    invalid_encode_rejected: int
    invalid_decode_rejected: int
    invalid_accepted: int


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{CORPUS_VERSION}:{label}"))


def _ref(label: str) -> JsonMap:
    return {
        "kind": "ref",
        "uri": "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:24],
    }


def _claim(index: int) -> JsonMap:
    domains = ("proof", "weather", "inventory", "routing", "finance")
    domain = domains[index % len(domains)]
    return {
        "kind": "claim",
        "predicate": f"{domain}.candidate.valid",
        "arguments": [
            _ref(f"artifact:{index % 23}"),
            f"candidate-{index:04d}",
            {"attempt": index % 9, "score": round((index % 17) / 17, 6)},
        ],
        "context": {
            "locale": ("ko-KR", "en-US", "ja-JP")[index % 3],
            "label": ("검증", "routing", "résultat")[index % 3],
        },
    }


def _constraint(index: int, scope: str) -> JsonMap:
    return {
        "kind": "constraint",
        "scope": scope,
        "mode": "hard" if index % 4 else "soft",
        "condition": {
            "latency_ms_lte": 250 + (index % 8) * 250,
            "regions": ["ap-northeast-2", "us-east-1"][: 1 + index % 2],
            "retry_lte": index % 4,
        },
        "weight_ppm": 1_000_000 if index % 4 else 650_000,
    }


def _goal(index: int) -> JsonMap:
    return {
        "kind": "goal",
        "condition": _claim(index),
        "owner": f"team-{index % 7}",
        "priority": 1 + index % 5,
        "constraints": [
            _constraint(index, "execution"),
            _constraint(index + 1, "output"),
        ],
    }


def _body_for(act: str, index: int, sender: str, recipients: Sequence[str]) -> JsonMap:
    if act == "ASSERT":
        variant = index % 3
        if variant == 0:
            return _claim(index)
        if variant == 1:
            return {
                "kind": "evidence",
                "target": _ref(f"target:{index % 31}"),
                "stance": "supports" if index % 2 else "contradicts",
                "digest": "sha256:" + hashlib.sha256(f"evidence:{index}".encode()).hexdigest(),
                "provenance": f"sensor.cluster/{index % 11}",
                "observed_at_ms": 1_720_000_000_000 + index * 1_000,
            }
        return {
            "kind": "uncertainty",
            "target": _ref(f"estimate:{index % 19}"),
            "model": "beta" if index % 2 else "categorical",
            "parameters": {"alpha": 2 + index % 5, "beta": 3 + index % 7},
            "basis": [_ref(f"sample:{index}:{part}") for part in range(2)],
        }
    if act == "QUERY":
        return {
            "kind": "claim",
            "predicate": "answer.matches.schema",
            "arguments": [_claim(index), f"urn:answer:{index % 5}:1"],
            "answer_limit": 1 + index % 4,
        }
    if act == "REQUEST":
        return _goal(index)
    if act == "PROPOSE":
        return {
            "kind": "action",
            "capability": ("verify.proof", "route.package", "reserve.stock")[index % 3],
            "arguments": {
                "goal": _goal(index),
                "dry_run": index % 2 == 0,
                "candidate_nodes": [f"worker-{(index + n) % 13}" for n in range(3)],
            },
            "declared_effects": ["ledger.append", "artifact.create"],
        }
    if act == "COMMIT":
        return {
            "kind": "commitment",
            "debtor": sender,
            "creditors": list(recipients),
            "goal": _goal(index),
            "expiry_ms": 2_000 + (index % 10) * 500,
            "verifier": f"verifier-{index % 5}.agent",
        }
    if act == "RESOLVE":
        return {
            "kind": "resolution",
            "target": _ref(f"commitment:{index}"),
            "status": ("succeeded", "failed", "expired")[index % 3],
            "result": {
                "artifact": _ref(f"result:{index}"),
                "checks": [True, True, index % 3 != 1],
            },
        }
    if act == "RETRACT":
        return {
            "kind": "ref",
            "uri": f"urn:ledger:record:{stable_uuid(f'record:{index}')}"
        }
    raise AssertionError(f"unhandled act: {act}")


def build_corpus(count: int = DEFAULT_MESSAGES) -> list[JsonMap]:
    """Build a deterministic, semantically valid corpus with all seven acts."""

    if count < 100:
        raise ValueError("corpus must contain at least 100 messages")
    acts = ("ASSERT", "QUERY", "REQUEST", "PROPOSE", "COMMIT", "RESOLVE", "RETRACT")
    agents = (
        "planner.alpha.agent",
        "verifier.beta.agent",
        "executor.gamma.agent",
        "auditor.delta.agent",
        "broker.epsilon.agent",
    )
    schemas = (
        "urn:urusilla:proof-verification:1",
        "urn:urusilla:routing:2",
        "urn:urusilla:inventory-reservation:1",
        "urn:urusilla:forecast-evidence:3",
        "urn:urusilla:contract-resolution:1",
    )
    corpus: list[JsonMap] = []
    for index in range(count):
        act = acts[index % len(acts)]
        sender = agents[index % len(agents)]
        recipient_count = 1 + index % 3
        recipients = [agents[(index + offset + 1) % len(agents)] for offset in range(recipient_count)]
        reply_to = (
            stable_uuid(f"prior:{index}")
            if act in {"COMMIT", "RESOLVE", "RETRACT"} or index % 11 == 0
            else None
        )
        expected_by_act = {
            "ASSERT": ["QUERY"],
            "QUERY": ["ASSERT", "RESOLVE"],
            "REQUEST": ["COMMIT", "RESOLVE"],
            "PROPOSE": ["COMMIT", "RETRACT"],
            "COMMIT": ["RESOLVE"],
            "RESOLVE": [],
            "RETRACT": [],
        }
        message = {
            "id": stable_uuid(f"message:{index}"),
            "session": stable_uuid(f"session:{index // 7}"),
            "sender": sender,
            "recipients": recipients,
            "act": act,
            "reply_to": reply_to,
            "schema": schemas[index % len(schemas)],
            "logical_clock": index * 3 + (index % 3),
            "expires_ms": 0 if index % 6 == 0 else 1_000 + (index % 20) * 250,
            "confidence_ppm": None if index % 9 == 0 else 500_000 + (index * 7_919) % 500_001,
            "expected": expected_by_act[act],
            "body": _body_for(act, index, sender, recipients),
            "meta": {
                "trace": {"run": index // 7, "span": index, "sampled": index % 5 == 0},
                "budget": {
                    "wire_bytes": 512 + (index % 8) * 256,
                    "compute_units": 20 + index % 50,
                },
                "tags": ["benchmark", f"domain-{index % 5}", "에이전트"],
            },
        }
        corpus.append(normalize_message(message))
    return corpus


def json_encode(message: Mapping[str, Any]) -> bytes:
    return json.dumps(
        message,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def json_decode(data: bytes) -> JsonMap:
    decoded = json.loads(data.decode("utf-8"))
    return normalize_message(decoded)


def gzip_json_encode(message: Mapping[str, Any]) -> bytes:
    return deterministic_gzip_compress(json_encode(message), compresslevel=6)


def gzip_json_decode(data: bytes) -> JsonMap:
    return json_decode(gzip.decompress(data))


def gzip_urusilla_encode(message: Mapping[str, Any]) -> bytes:
    return deterministic_gzip_compress(encode_message(message), compresslevel=6)


def gzip_urusilla_decode(data: bytes) -> JsonMap:
    return decode_message(gzip.decompress(data))


def optional_cbor_codec() -> Codec | None:
    if importlib.util.find_spec("cbor2") is None:
        return None
    import cbor2  # type: ignore[import-not-found]

    def encode(message: Mapping[str, Any]) -> bytes:
        return cbor2.dumps(message, canonical=True)

    def decode(data: bytes) -> JsonMap:
        return normalize_message(cbor2.loads(data))

    return Codec(
        "deterministic CBOR",
        encode,
        decode,
        "cbor2 canonical=True; package was already installed",
    )


def available_codecs() -> tuple[list[Codec], list[str]]:
    codecs = [
        Codec(
            "UrusillaWire",
            encode_message,
            decode_message,
            "v0.1 reference; checksum + semantic validation + canonical re-encode",
        ),
        Codec(
            "gzip UrusillaWire",
            gzip_urusilla_encode,
            gzip_urusilla_decode,
            "UrusillaWire with per-message gzip level 6, mtime=0",
        ),
        Codec(
            "minified JSON",
            json_encode,
            json_decode,
            "sorted UTF-8 JSON; shared Urusilla normalize_message on decode",
        ),
        Codec(
            "gzip JSON",
            gzip_json_encode,
            gzip_json_decode,
            "per-message gzip level 6, mtime=0; shared Urusilla validation on decode",
        ),
    ]
    optional: list[str] = []
    cbor = optional_cbor_codec()
    if cbor is None:
        optional.append("deterministic CBOR: not run (`cbor2` is not installed)")
    else:
        codecs.append(cbor)
        optional.append("deterministic CBOR: included (`cbor2` was already installed)")

    try:
        protobuf_present = importlib.util.find_spec("google.protobuf") is not None
    except ModuleNotFoundError:
        protobuf_present = False
    if protobuf_present:
        optional.append(
            "Protobuf: runtime detected, but not run because no schema-equivalent generated "
            "Urusilla message exists; generic Struct/JSON wrapping would be a misleading baseline"
        )
    else:
        optional.append("Protobuf: not run (`google.protobuf` is not installed)")
    return codecs, optional


def corpus_digest(corpus: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for message in corpus:
        raw = json_encode(message)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def nearest_rank(values: Sequence[int], percentile: float) -> int:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def timed_call(function: Callable[..., Any], *args: Any) -> tuple[Any, int]:
    started = time.perf_counter_ns()
    result = function(*args)
    return result, time.perf_counter_ns() - started


def warm_up(codecs: Sequence[Codec], corpus: Sequence[JsonMap], rounds: int) -> None:
    if rounds <= 0:
        return
    for _ in range(rounds):
        for codec in codecs:
            for message in corpus:
                frame = codec.encode(message)
                codec.decode(frame)


def measure_timings(
    codecs: Sequence[Codec],
    corpus: Sequence[JsonMap],
    frames: Mapping[str, Sequence[bytes]],
    repeats: int,
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    encode_samples = {codec.name: [] for codec in codecs}
    decode_samples = {codec.name: [] for codec in codecs}
    previous_gc = gc.isenabled()
    gc.disable()
    try:
        # Rotate codec order per repeat to reduce systematic thermal/order bias.
        for repeat in range(repeats):
            ordered = list(codecs[repeat % len(codecs) :]) + list(codecs[: repeat % len(codecs)])
            for codec in ordered:
                for message in corpus:
                    _, elapsed = timed_call(codec.encode, message)
                    encode_samples[codec.name].append(elapsed)
        for repeat in range(repeats):
            ordered = list(codecs[repeat % len(codecs) :]) + list(codecs[: repeat % len(codecs)])
            for codec in ordered:
                for frame in frames[codec.name]:
                    _, elapsed = timed_call(codec.decode, frame)
                    decode_samples[codec.name].append(elapsed)
    finally:
        if previous_gc:
            gc.enable()
    return encode_samples, decode_samples


def corrupt_bytes(data: bytes, message_index: int, trial: int) -> bytes:
    """Flip one matched deterministic bit at a fractional frame position."""

    seed = hashlib.sha256(
        f"{CORPUS_VERSION}|{message_index}|{trial}".encode("utf-8")
    ).digest()
    fraction = int.from_bytes(seed[:8], "big") / 2**64
    position = min(len(data) - 1, int(fraction * len(data)))
    bit = 1 << (seed[8] % 8)
    changed = bytearray(data)
    changed[position] ^= bit
    return bytes(changed)


def measure_corruption(
    codec: Codec,
    corpus: Sequence[JsonMap],
    frames: Sequence[bytes],
    trials: int,
) -> tuple[int, int, int]:
    rejected = silent_change = unchanged = 0
    for message_index, (message, frame) in enumerate(zip(corpus, frames, strict=True)):
        for trial in range(trials):
            corrupted = corrupt_bytes(frame, message_index, trial)
            try:
                decoded = codec.decode(corrupted)
            except Exception:
                rejected += 1
            else:
                if decoded == message:
                    unchanged += 1
                else:
                    silent_change += 1
    return rejected, silent_change, unchanged


def invalid_cases(corpus: Sequence[JsonMap], source_messages: int = 20) -> list[JsonMap]:
    """Create deterministic, serialization-safe messages violating Urusilla semantics."""

    cases: list[JsonMap] = []
    for source in corpus[:source_messages]:
        mutations: list[Callable[[JsonMap], None]] = [
            lambda value: value.pop("body"),
            lambda value: value.__setitem__("act", "WHISPER"),
            lambda value: value.__setitem__("recipients", []),
            lambda value: value.__setitem__("recipients", [value["sender"], value["sender"]]),
            lambda value: value.__setitem__("confidence_ppm", 1_000_001),
            lambda value: value.__setitem__("logical_clock", -1),
            lambda value: value.__setitem__("schema", ""),
            lambda value: value.__setitem__("body", {"kind": "private-unknown", "value": 7}),
            lambda value: value.__setitem__("meta", []),
            lambda value: (value.__setitem__("act", "COMMIT"), value.__setitem__("reply_to", None)),
            lambda value: value.__setitem__("body", {"kind": "evidence", "target": _ref("x")}),
            lambda value: value.__setitem__("sender", ""),
        ]
        for mutate in mutations:
            candidate = copy.deepcopy(source)
            mutate(candidate)
            cases.append(candidate)
    # Guard against a faulty mutation silently weakening the benchmark.
    for candidate in cases:
        try:
            normalize_message(candidate)
        except UrusillaError:
            continue
        raise AssertionError("invalid-case generator produced a valid message")
    return cases


def measure_invalid(codec: Codec, cases: Sequence[JsonMap]) -> tuple[int, int, int]:
    encode_rejected = decode_rejected = accepted = 0
    for candidate in cases:
        try:
            frame = codec.encode(candidate)
        except Exception:
            encode_rejected += 1
            continue
        try:
            codec.decode(frame)
        except Exception:
            decode_rejected += 1
        else:
            accepted += 1
    return encode_rejected, decode_rejected, accepted


def measure(
    codecs: Sequence[Codec],
    corpus: Sequence[JsonMap],
    repeats: int,
    warmups: int,
    corruption_trials: int,
) -> tuple[list[CodecResult], int]:
    frames: dict[str, list[bytes]] = {
        codec.name: [codec.encode(message) for message in corpus] for codec in codecs
    }
    warm_up(codecs, corpus, warmups)
    encode_samples, decode_samples = measure_timings(codecs, corpus, frames, repeats)
    invalid = invalid_cases(corpus)
    results: list[CodecResult] = []
    for codec in codecs:
        exact = canonical = 0
        for message, frame in zip(corpus, frames[codec.name], strict=True):
            decoded = codec.decode(frame)
            if decoded == message:
                exact += 1
            if codec.encode(decoded) == frame:
                canonical += 1
        corrupt_rejected, corrupt_silent, corrupt_unchanged = measure_corruption(
            codec, corpus, frames[codec.name], corruption_trials
        )
        invalid_encode, invalid_decode, invalid_accepted = measure_invalid(codec, invalid)
        results.append(
            CodecResult(
                name=codec.name,
                sizes=[len(frame) for frame in frames[codec.name]],
                encode_ns=encode_samples[codec.name],
                decode_ns=decode_samples[codec.name],
                exact_messages=exact,
                canonical_frames=canonical,
                corruption_rejected=corrupt_rejected,
                corruption_silent_change=corrupt_silent,
                corruption_unchanged=corrupt_unchanged,
                invalid_encode_rejected=invalid_encode,
                invalid_decode_rejected=invalid_decode,
                invalid_accepted=invalid_accepted,
            )
        )
    return results, len(invalid)


def percentage(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{100 * numerator / denominator:.1f}%"


def size_row(result: CodecResult, json_total: int) -> str:
    total = sum(result.sizes)
    delta = 100 * (total / json_total - 1)
    return (
        f"| {result.name} | {total:,} | {statistics.fmean(result.sizes):,.1f} | "
        f"{nearest_rank(result.sizes, 0.50):,} | {nearest_rank(result.sizes, 0.95):,} | "
        f"{delta:+.1f}% |"
    )


def latency_row(result: CodecResult) -> str:
    return (
        f"| {result.name} | {nearest_rank(result.encode_ns, 0.50) / 1_000:,.2f} | "
        f"{nearest_rank(result.encode_ns, 0.95) / 1_000:,.2f} | "
        f"{nearest_rank(result.decode_ns, 0.50) / 1_000:,.2f} | "
        f"{nearest_rank(result.decode_ns, 0.95) / 1_000:,.2f} |"
    )


def render_report(
    results: Sequence[CodecResult],
    codecs: Sequence[Codec],
    optional_notes: Sequence[str],
    corpus: Sequence[JsonMap],
    repeats: int,
    warmups: int,
    corruption_trials: int,
    invalid_count: int,
    elapsed_seconds: float,
) -> str:
    by_name = {result.name: result for result in results}
    urusilla = by_name["UrusillaWire"]
    gzip_urusilla = by_name["gzip UrusillaWire"]
    json_result = by_name["minified JSON"]
    gzip_result = by_name["gzip JSON"]
    json_total = sum(json_result.sizes)
    urusilla_total = sum(urusilla.sizes)
    gzip_urusilla_total = sum(gzip_urusilla.sizes)
    gzip_total = sum(gzip_result.sizes)
    urusilla_vs_json = 100 * (1 - urusilla_total / json_total)
    urusilla_vs_gzip = 100 * (1 - urusilla_total / gzip_total)
    gzip_urusilla_vs_gzip_json = 100 * (1 - gzip_urusilla_total / gzip_total)
    corrupt_total = len(corpus) * corruption_trials
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    codec_notes = "\n".join(f"- **{codec.name}:** {codec.notes}" for codec in codecs)
    optional_text = "\n".join(f"- {note}" for note in optional_notes)

    if urusilla_vs_json > 0:
        json_verdict = f"raw UrusillaWire was **{urusilla_vs_json:.1f}% smaller than minified JSON**"
    else:
        json_verdict = f"raw UrusillaWire was **{-urusilla_vs_json:.1f}% larger than minified JSON**"
    if urusilla_vs_gzip > 0:
        gzip_verdict = f"raw UrusillaWire was **{urusilla_vs_gzip:.1f}% smaller than per-message gzip JSON**"
    else:
        gzip_verdict = f"raw UrusillaWire was **{-urusilla_vs_gzip:.1f}% larger than per-message gzip JSON**"
    if gzip_urusilla_vs_gzip_json > 0:
        matched_gzip_verdict = (
            f"When the same gzip compression was applied to both, gzip(UrusillaWire) was "
            f"**{gzip_urusilla_vs_gzip_json:.1f}% smaller than gzip(JSON)**"
        )
    else:
        matched_gzip_verdict = (
            f"Even when the same gzip compression was applied to both, gzip(UrusillaWire) was "
            f"**{-gzip_urusilla_vs_gzip_json:.1f}% larger than gzip(JSON)**"
        )

    lines = [
        "# Urusilla v0.1 reproducible value benchmark",
        "",
        f"Execution time (UTC): `{timestamp}`  ",
        f"Corpus: `{CORPUS_VERSION}`, {len(corpus)} deterministic messages, SHA-256 `{corpus_digest(corpus)}`  ",
        f"Runtime: `{platform.python_implementation()} {platform.python_version()}` / `{platform.platform()}`  ",
        f"Measurement settings: {warmups} warm-up rounds, {repeats} timing repeats, "
        f"{corruption_trials} single-bit corruptions per message  ",
        f"Total execution time: {elapsed_seconds:.2f}s",
        "",
        "## Conclusion first",
        "",
        f"On this corpus, {json_verdict}, while {gzip_verdict}. {matched_gzip_verdict}. "
        f"Valid-message semantic round-trip was `{urusilla.exact_messages}/{len(corpus)}`, and "
        f"`{urusilla.corruption_rejected}/{corrupt_total}` deterministic bit flips were rejected "
        f"during raw UrusillaWire decoding.",
        "",
        "From a wire-only perspective, raw UrusillaWire is larger than gzip JSON and has higher "
        "codec latency, so it cannot be said to dominate every baseline. Applying the same "
        "transport compression reveals a size advantage, but a CPU trade-off remains. The "
        "current reason to select Urusilla is its **semantic contract for carrying already-structured "
        "UrusillaIR canonically and with fail-closed behavior**; the codec should be negotiated "
        "according to the situation. These results do not demonstrate an end-to-end advantage "
        "in agent intelligence or task success. In particular, a model must not be assumed to "
        "read binary wire data directly; an adapter or native structured channel is required.",
        "",
        "## Wire bytes",
        "",
        "| Codec | Total bytes | Mean/msg | p50/msg | p95/msg | vs minified JSON |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(size_row(result, json_total) for result in results)
    lines.extend(
        [
            "",
            "Each message was sent as an independent frame. Both gzip JSON and gzip UrusillaWire use "
            "identical per-message compression with `compresslevel=6, mtime=0`, not a batch or "
            "streaming dictionary. The raw UrusillaWire row is retained as a separate baseline rather "
            "than hidden.",
            "",
            "## Encode/decode latency",
            "",
            "| Codec | Encode p50 (µs) | Encode p95 (µs) | Decode p50 (µs) | Decode p95 (µs) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    lines.extend(latency_row(result) for result in results)
    lines.extend(
        [
            "",
            f"Encode and decode were each measured `{len(corpus) * repeats:,}` times per codec. "
            "Urusilla decoding includes checksum verification, semantic validation, and a canonical "
            "re-encode check. JSON encode serializes without the equivalent validation pass, while "
            "JSON decode uses the shared validator. These are timings of the current Python "
            "implementation paths, not an inherent format-speed comparison. Values are wall-clock "
            "samples from this machine and will differ on other machines.",
            "",
            "## Exactness and canonicality",
            "",
            "| Codec | Exact semantic round-trip | Re-encode byte-identical |",
            "|---|---:|---:|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.name} | {result.exact_messages}/{len(corpus)} "
            f"({percentage(result.exact_messages, len(corpus))}) | "
            f"{result.canonical_frames}/{len(corpus)} "
            f"({percentage(result.canonical_frames, len(corpus))}) |"
        )
    lines.extend(
        [
            "",
            "`Exact semantic round-trip` checks whether the decoded canonical Urusilla message equals "
            "the source. `Re-encode byte-identical` checks whether canonical bytes remain stable "
            "within the same runtime and profile.",
            "",
            "## Single-bit corruption",
            "",
            "| Codec | Rejected/detected | Accepted, semantics changed | Accepted, semantics unchanged |",
            "|---|---:|---:|---:|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.name} | {result.corruption_rejected}/{corrupt_total} "
            f"({percentage(result.corruption_rejected, corrupt_total)}) | "
            f"{result.corruption_silent_change}/{corrupt_total} "
            f"({percentage(result.corruption_silent_change, corrupt_total)}) | "
            f"{result.corruption_unchanged}/{corrupt_total} "
            f"({percentage(result.corruption_unchanged, corrupt_total)}) |"
        )
    lines.extend(
        [
            "",
            "The same bit was flipped at corresponding deterministic fractional positions in each "
            "encoded frame. `Rejected` means that codec decoding and shared Urusilla validation failed "
            "closed with an exception. `Accepted, semantics changed` indicates dangerous silent "
            "corruption. `Unchanged` can include modifications outside the semantic payload, such "
            "as changes to a gzip header. This test does not evaluate protection against malicious "
            "forgery.",
            "",
            "## Semantically invalid inputs",
            "",
            f"The test used `{invalid_count}` invalid messages: 12 violation classes × 20 source messages.",
            "",
            "| Codec | Rejected at encode | Serialized, then rejected at decode/validation | Invalid accepted end-to-end |",
            "|---|---:|---:|---:|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.name} | {result.invalid_encode_rejected}/{invalid_count} | "
            f"{result.invalid_decode_rejected}/{invalid_count} | "
            f"{result.invalid_accepted}/{invalid_count} |"
        )
    lines.extend(
        [
            "",
            "JSON and gzip are not themselves semantic schemas, so they can serialize invalid "
            "objects. For a fair end-to-end comparison, the JSON decoders in this benchmark "
            "explicitly use Urusilla's `normalize_message` validator. The UrusillaWire reference encoder "
            "invokes the validator itself, so invalid messages are rejected before wire data is "
            "produced.",
            "",
            "## Codec profiles and optional baselines",
            "",
            codec_notes,
            "",
            optional_text,
            "",
            "## What this does not measure",
            "",
            "- **Cold schema / Grammar Capsule cost:** The corpus contains only a schema URI. It "
            "excludes the bytes and validation time required for the initial delivery of ontology "
            "data, a schema document, translation templates, and golden vectors. Cold break-even "
            "must be calculated separately as `floor(cold_bootstrap_bytes / "
            "(baseline_bytes_per_msg - warm_Urusilla_bytes_per_msg)) + 1` for the first strict byte "
            "win, and a break-even point exists only when the denominator is positive.",
            "- **Session shared-dictionary warm profile:** Current UrusillaWire includes a per-message "
            "string table in every frame. If `C` is the combined cost of the Capsule and "
            "session-dictionary handshake, `W` is the average warm-frame size, and `B` is the "
            "average baseline-frame size, the condition for `N` messages is `C + N·W < N·B`, or "
            "`N > C/(B-W)`. This original v0.1 measurement does not include a session profile or "
            "handshake. A separate experimental v0.2 implementation and cold-cost study now report "
            "those values in `urusilla_wire_v02_results.md`; they must not be retroactively attributed "
            "to the v0.1 row.",
            "- **LLM tokens and model cost:** These vary by tokenizer and model, and placing binary "
            "UrusillaWire in a text prompt is not a design goal. An evaluation that connects a "
            "JSON/UrusillaIR projection to actual model I/O is required.",
            "- **Semantic construction quality:** The benchmark does not measure ambiguity, "
            "omission, or hallucination in natural-language → UrusillaIR conversion. The source corpus "
            "already consists of valid semantic objects.",
            "- **Task utility:** Success rate, repair turns, causal usefulness, multi-agent "
            "transfer, energy, memory, and network/TLS overhead are not measured.",
            "- **Compression regimes:** The benchmark does not compare cross-message or batch gzip, "
            "shared dictionaries, schema-aware CBOR/Protobuf, or content-addressed DAG "
            "deduplication.",
            "- **Security:** The Urusilla checksum and gzip CRC signal accidental corruption only. They "
            "do not provide authentication, integrity against attackers, or replay protection.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 urusilla_benchmark.py",
            "```",
            "",
            "Options: `--messages` (minimum 100), `--repeats`, `--warmups`, `--corruptions`, `--output`. "
            "Corpus bytes and corruption locations remain deterministic for the same corpus version and options; "
            "latency samples remain environment-dependent.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--corruptions", type=int, default=DEFAULT_CORRUPTIONS)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("urusilla_benchmark_results.md"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.messages < 100:
        raise SystemExit("--messages must be at least 100")
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.warmups < 0:
        raise SystemExit("--warmups cannot be negative")
    if args.corruptions < 1:
        raise SystemExit("--corruptions must be at least 1")

    started = time.perf_counter()
    corpus = build_corpus(args.messages)
    codecs, optional_notes = available_codecs()
    results, invalid_count = measure(
        codecs,
        corpus,
        repeats=args.repeats,
        warmups=args.warmups,
        corruption_trials=args.corruptions,
    )
    elapsed = time.perf_counter() - started
    report = render_report(
        results,
        codecs,
        optional_notes,
        corpus,
        args.repeats,
        args.warmups,
        args.corruptions,
        invalid_count,
        elapsed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"corpus: {len(corpus)} messages, sha256={corpus_digest(corpus)}")
    for result in results:
        print(
            f"{result.name}: total={sum(result.sizes)} bytes, "
            f"encode_p50={nearest_rank(result.encode_ns, 0.50) / 1_000:.2f} us, "
            f"decode_p50={nearest_rank(result.decode_ns, 0.50) / 1_000:.2f} us"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
