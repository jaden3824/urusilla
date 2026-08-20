#!/usr/bin/env python3
"""Receiver-aware adaptive text surface for Urusilla.

The v0.5 experiment measures complete receiver-token cost before selecting one
of three required exact representations: the v0.4 structured token surface,
Controlled Terse English, or sorted minified JSON.  Every candidate includes a
mode marker and 64-bit accidental-corruption protection; structured mode reuses
its existing inner checksum.  A deterministic optional fragment envelope is
also constructed and can win only when its exact complete token count is lower.

Warm selection is exact per message for the named receiver tokenizer.  Cold
session planning compares two complete plans: never activate the structured
profile/codebook bundle, or charge it once and then select each message at warm
cost.  This is serialization accounting, not evidence of model understanding
or task success.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import dataclass
import gc
import hashlib
import hmac
import json
import math
from pathlib import Path
import platform
import re
import statistics
import time
from typing import Any, Callable, Mapping, Sequence

# Temporary bridges to frozen fixtures and implementations.  The experiment
# itself creates only neutral-named files and does not mutate these inputs.
from urusilla_benchmark import corpus_digest, json_decode, json_encode
from urusilla import DecodeError, MAX_FRAME_BYTES, ValidationError, normalize_message
from urusilla_token_surface_holdout import (
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_SHA256,
    EXPECTED_TRAIN_SHA256,
    _sequence_digest,
    build_out_of_domain_corpus,
    frozen_split,
    holdout_codebook,
)
from urusilla_token_surface_v03 import _decode_payload
from urusilla_tokenizer_benchmark import (
    TIKTOKEN_VERSION,
    TOKENIZERS_VERSION,
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
    sha256_file,
)
from urusilla_wire_v02 import DEFAULT_PROFILE, encode_capsule as encode_profile_capsule
from urusilla_terse_english_benchmark import (
    _ValueParser,
    _render_value,
    decode_terse_english,
    encode_terse_english,
)
from urusilla_token_surface_v04 import (
    decode_message as decode_v04,
    encode_bytes_optimal,
    encode_codebook_capsule_text,
    encode_message as encode_v04,
)


FORMAT = "urusilla-adaptive-surface-v0.5-experimental"
REPORT_NAME = "ADAPTIVE_SURFACE_V05_RESULTS.md"
PREFIX = "A5"
CHECKSUM_CHARACTERS = 11
CHECKSUM_HEADER_CHARACTERS = len(PREFIX) + 1 + CHECKSUM_CHARACTERS + 1
STRUCTURED_HEADER_CHARACTERS = len(PREFIX) + 1 + 1
MAX_ADAPTIVE_UTF8_BYTES = 64 * 1024 * 1024
_CHECKSUM_DOMAIN = b"UrusillaAdaptiveSurface-v0.5\x00"

MODE_ORDER = ("J", "E", "V", "F")
MODE_LABELS = {
    "J": "minified JSON envelope",
    "E": "Controlled Terse English envelope",
    "V": "v0.4 structured envelope",
    "F": "lossless fragment envelope",
}
DATASET_LABELS = {
    "development": "development training partition",
    "grouped_holdout": "grouped holdout",
    "out_of_domain": "out of domain",
}
FRAGMENT_FIELDS = (
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
_CHECKSUM_TEXT = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_LENGTH_TEXT = re.compile(r"(?:0|[1-9][0-9]*)\Z")

# Frozen after the first controlled four-tokenizer run.  The digest covers the
# complete canonical JSON snapshot: choices, text vectors, warm totals, cold
# plans, fragment wins, exactness, determinism, and corruption counts.
EXPECTED_SNAPSHOT_SHA256 = "b13d454bddeb416035b07fc1fb0130c3d158591bd3dd96028ffa39b08a4a2028"


@dataclass(frozen=True)
class PreparedMessage:
    message: Mapping[str, Any]
    whole_payloads: Mapping[str, str]
    whole_envelopes: Mapping[str, str]
    fragment_records: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class Candidate:
    mode: str
    text: str
    tokens: int
    utf8_bytes: int
    uses_bundle: bool
    fragment_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Selection:
    candidate: Candidate
    required_best_tokens: int
    all_best_tokens: int
    candidates: Mapping[str, Candidate]


@dataclass(frozen=True)
class SessionPlan:
    activated_bundle: bool
    cold_tokens: int
    total_tokens: int
    no_bundle_total_tokens: int
    activated_total_tokens: int
    choices: tuple[Candidate, ...]


@dataclass(frozen=True)
class Study:
    datasets: Mapping[str, tuple[dict[str, Any], ...]]
    prepared: Mapping[str, tuple[PreparedMessage, ...]]
    selections: Mapping[str, Mapping[str, tuple[Selection, ...]]]
    sessions: Mapping[str, Mapping[str, SessionPlan]]
    exact: int
    deterministic: int
    corruptions_attempted: int
    corruptions_rejected: int
    profiles: tuple[TokenizerProfile, ...]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _checksum(mode: str, payload: str) -> str:
    digest = hashlib.blake2s(
        _CHECKSUM_DOMAIN + mode.encode("ascii") + b"\x00" + payload.encode("utf-8"),
        digest_size=8,
    ).digest()
    result = _b64url(digest)
    if len(result) != CHECKSUM_CHARACTERS:
        raise RuntimeError("adaptive checksum width changed")
    return result


def encode_envelope(mode: str, payload: str) -> str:
    """Add a deterministic mode marker and accidental-corruption checksum."""

    if mode not in MODE_ORDER or not isinstance(payload, str) or not payload:
        raise ValidationError("adaptive mode or payload is invalid")
    # The structured v0.4 payload already carries its own 64-bit checksum and
    # canonical re-encoding check.  Reuse it instead of paying twice.  The
    # other modes require the outer checksum defined here.
    if mode == "V":
        result = PREFIX + mode + ":" + payload
    else:
        result = PREFIX + mode + _checksum(mode, payload) + ":" + payload
    if len(result.encode("utf-8")) > MAX_ADAPTIVE_UTF8_BYTES:
        raise ValidationError("adaptive surface exceeds the UTF-8 size limit")
    return result


def _split_envelope(text: str) -> tuple[str, str]:
    if not isinstance(text, str):
        raise DecodeError("adaptive surface must be text")
    if len(text.encode("utf-8")) > MAX_ADAPTIVE_UTF8_BYTES:
        raise DecodeError("adaptive surface exceeds the UTF-8 size limit")
    if len(text) <= STRUCTURED_HEADER_CHARACTERS or not text.startswith(PREFIX):
        raise DecodeError("unknown or truncated adaptive surface")
    mode = text[len(PREFIX)]
    if mode == "V":
        separator = len(PREFIX) + 1
        if text[separator] != ":" or len(text) <= STRUCTURED_HEADER_CHARACTERS:
            raise DecodeError("structured adaptive header is invalid")
        return mode, text[separator + 1 :]
    if len(text) <= CHECKSUM_HEADER_CHARACTERS:
        raise DecodeError("checksummed adaptive surface is truncated")
    supplied = text[len(PREFIX) + 1 : len(PREFIX) + 1 + CHECKSUM_CHARACTERS]
    separator = len(PREFIX) + 1 + CHECKSUM_CHARACTERS
    if mode not in MODE_ORDER or _CHECKSUM_TEXT.fullmatch(supplied) is None:
        raise DecodeError("adaptive header is invalid")
    if text[separator] != ":":
        raise DecodeError("adaptive header separator is missing")
    payload = text[separator + 1 :]
    if not payload:
        raise DecodeError("adaptive payload is empty")
    expected = _checksum(mode, payload)
    if not hmac.compare_digest(supplied, expected):
        raise DecodeError("adaptive checksum mismatch")
    return mode, payload


def payload_start(text: str) -> int:
    """Return the first payload character after validating only header shape."""

    if not isinstance(text, str) or not text.startswith(PREFIX) or len(text) < 4:
        raise DecodeError("adaptive header is invalid")
    mode = text[len(PREFIX)]
    if mode == "V":
        if text[len(PREFIX) + 1] != ":":
            raise DecodeError("structured adaptive header is invalid")
        return STRUCTURED_HEADER_CHARACTERS
    if mode not in ("J", "E", "F") or len(text) <= CHECKSUM_HEADER_CHARACTERS:
        raise DecodeError("checksummed adaptive header is invalid")
    return CHECKSUM_HEADER_CHARACTERS


def _json_payload(message: Mapping[str, Any]) -> str:
    return json_encode(message).decode("utf-8")


def _canonical_json_value(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_json_value(text: str) -> Any:
    try:
        value = json.loads(
            text,
            parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise DecodeError("fragment JSON value is invalid") from exc
    try:
        canonical = _canonical_json_value(value)
    except (TypeError, ValueError) as exc:
        raise DecodeError("fragment JSON value is unsupported") from exc
    if canonical != text:
        raise DecodeError("fragment JSON value is not canonical")
    return value


def _decode_terse_value(text: str) -> Any:
    parser = _ValueParser(text)
    value = parser.value()
    if parser.position != len(text) or _render_value(value) != text:
        raise DecodeError("fragment controlled value is not canonical")
    return value


def _record(mode: str, payload: str) -> str:
    return mode + str(len(payload)) + ":" + payload


def prepare_message(message: Mapping[str, Any]) -> PreparedMessage:
    """Precompute receiver-independent whole and fragment candidates."""

    canonical = normalize_message(message)
    codebook = holdout_codebook()
    whole_payloads = {
        "J": _json_payload(canonical),
        "E": encode_terse_english(canonical),
        "V": encode_v04(canonical, codebook),
    }
    whole_envelopes = {
        mode: encode_envelope(mode, payload) for mode, payload in whole_payloads.items()
    }
    fragment_records: list[Mapping[str, str]] = []
    for field in FRAGMENT_FIELDS:
        json_value = _canonical_json_value(canonical[field])
        terse_value = _render_value(canonical[field])
        structured_value = encode_bytes_optimal(json_value.encode("utf-8"), codebook)
        fragment_records.append(
            {
                "J": _record("J", json_value),
                "E": _record("E", terse_value),
                "V": _record("V", structured_value),
            }
        )
    return PreparedMessage(canonical, whole_payloads, whole_envelopes, tuple(fragment_records))


def encode_fragment_envelope(
    prepared: PreparedMessage,
    profile: TokenizerProfile,
    *,
    allow_bundle: bool,
) -> Candidate:
    """Build a lossless field-fragment envelope with local exact record costs.

    Tokenization across record boundaries is not additive, so local choices are
    not claimed to be the global fragment optimum.  The complete resulting
    envelope is counted exactly before it competes with whole-message codecs.
    """

    eligible = ("J", "E", "V") if allow_bundle else ("J", "E")
    records: list[str] = []
    modes: list[str] = []
    for variants in prepared.fragment_records:
        mode = min(
            eligible,
            key=lambda item: (profile.count(variants[item]), MODE_ORDER.index(item)),
        )
        modes.append(mode)
        records.append(variants[mode])
    text = encode_envelope("F", "".join(records))
    return Candidate(
        mode="F",
        text=text,
        tokens=profile.count(text),
        utf8_bytes=len(text.encode("utf-8")),
        uses_bundle="V" in modes,
        fragment_modes=tuple(modes),
    )


def build_candidates(
    prepared: PreparedMessage,
    profile: TokenizerProfile,
    *,
    allow_bundle: bool,
    allow_fragments: bool,
) -> dict[str, Candidate]:
    eligible = ("J", "E", "V") if allow_bundle else ("J", "E")
    result = {
        mode: Candidate(
            mode=mode,
            text=prepared.whole_envelopes[mode],
            tokens=profile.count(prepared.whole_envelopes[mode]),
            utf8_bytes=len(prepared.whole_envelopes[mode].encode("utf-8")),
            uses_bundle=mode == "V",
        )
        for mode in eligible
    }
    if allow_fragments:
        result["F"] = encode_fragment_envelope(
            prepared, profile, allow_bundle=allow_bundle
        )
    return result


def select_prepared(
    prepared: PreparedMessage,
    profile: TokenizerProfile,
    *,
    allow_bundle: bool = True,
    allow_fragments: bool = True,
) -> Selection:
    candidates = build_candidates(
        prepared,
        profile,
        allow_bundle=allow_bundle,
        allow_fragments=allow_fragments,
    )
    candidate = min(
        candidates.values(),
        key=lambda item: (item.tokens, MODE_ORDER.index(item.mode), item.text),
    )
    required_modes = tuple(mode for mode in ("J", "E", "V") if mode in candidates)
    required_best = min(candidates[mode].tokens for mode in required_modes)
    all_best = min(value.tokens for value in candidates.values())
    if candidate.tokens != all_best or candidate.tokens > required_best:
        raise RuntimeError("adaptive selector did not choose the exact minimum")
    return Selection(candidate, required_best, all_best, candidates)


def select_message(
    message: Mapping[str, Any],
    profile: TokenizerProfile,
    *,
    allow_bundle: bool = True,
    allow_fragments: bool = True,
) -> Selection:
    return select_prepared(
        prepare_message(message),
        profile,
        allow_bundle=allow_bundle,
        allow_fragments=allow_fragments,
    )


def _decode_fragment_payload(payload: str) -> dict[str, Any]:
    codebook = holdout_codebook()
    position = 0
    values: dict[str, Any] = {}
    for field in FRAGMENT_FIELDS:
        if position >= len(payload) or payload[position] not in ("J", "E", "V"):
            raise DecodeError("fragment record mode is missing or invalid")
        mode = payload[position]
        position += 1
        colon = payload.find(":", position, min(len(payload), position + 12))
        if colon < 0:
            raise DecodeError("fragment record length is missing")
        length_text = payload[position:colon]
        if _LENGTH_TEXT.fullmatch(length_text) is None:
            raise DecodeError("fragment record length is not canonical")
        length = int(length_text)
        position = colon + 1
        end = position + length
        if end > len(payload):
            raise DecodeError("fragment record is truncated")
        value_text = payload[position:end]
        position = end
        if mode == "J":
            value = _decode_json_value(value_text)
        elif mode == "E":
            value = _decode_terse_value(value_text)
        else:
            raw = _decode_payload(value_text, codebook)
            if len(raw) > MAX_FRAME_BYTES:
                raise DecodeError("fragment expansion exceeds the byte limit")
            try:
                json_text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise DecodeError("structured fragment is not UTF-8 JSON") from exc
            value = _decode_json_value(json_text)
            if encode_bytes_optimal(raw, codebook) != value_text:
                raise DecodeError("structured fragment is not canonical")
        values[field] = value
    if position != len(payload):
        raise DecodeError("fragment envelope has trailing data")
    return normalize_message(values)


def decode_message(text: str) -> dict[str, Any]:
    """Verify the envelope, decode its selected representation, and validate."""

    mode, payload = _split_envelope(text)
    if mode == "J":
        message = json_decode(payload.encode("utf-8"))
        if _json_payload(message) != payload:
            raise DecodeError("JSON payload is not canonical")
    elif mode == "E":
        message = decode_terse_english(payload)
    elif mode == "V":
        message = decode_v04(payload, holdout_codebook())
    else:
        message = _decode_fragment_payload(payload)
    if encode_envelope(mode, payload) != text:
        raise DecodeError("adaptive envelope is not canonical")
    return message


def build_datasets() -> dict[str, tuple[dict[str, Any], ...]]:
    split = frozen_split()
    datasets = {
        "development": tuple(split.train),
        "grouped_holdout": tuple(split.holdout),
        "out_of_domain": tuple(build_out_of_domain_corpus()),
    }
    expected = {
        "development": EXPECTED_TRAIN_SHA256,
        "grouped_holdout": EXPECTED_HOLDOUT_SHA256,
        "out_of_domain": EXPECTED_OOD_SHA256,
    }
    for key, messages in datasets.items():
        if corpus_digest(messages) != expected[key]:
            raise RuntimeError(f"frozen {key} corpus changed")
    return datasets


def cold_bundle_metrics(profile: TokenizerProfile) -> tuple[int, int]:
    profile_text = base64.b64encode(encode_profile_capsule(DEFAULT_PROFILE)).decode("ascii")
    codebook_text = encode_codebook_capsule_text(holdout_codebook())
    return (
        profile.count(profile_text) + profile.count(codebook_text),
        len(profile_text.encode("utf-8")) + len(codebook_text.encode("utf-8")),
    )


def plan_session(
    prepared_messages: Sequence[PreparedMessage], profile: TokenizerProfile
) -> SessionPlan:
    no_bundle = [
        select_prepared(item, profile, allow_bundle=False).candidate
        for item in prepared_messages
    ]
    activated = [
        select_prepared(item, profile, allow_bundle=True).candidate
        for item in prepared_messages
    ]
    cold_tokens, _cold_bytes = cold_bundle_metrics(profile)
    no_total = sum(item.tokens for item in no_bundle)
    activated_total = cold_tokens + sum(item.tokens for item in activated)
    if activated_total < no_total:
        choices = tuple(activated)
        result = SessionPlan(True, cold_tokens, activated_total, no_total, activated_total, choices)
    else:
        choices = tuple(no_bundle)
        result = SessionPlan(False, 0, no_total, no_total, activated_total, choices)
    expected = min(no_total, activated_total)
    if result.total_tokens != expected:
        raise RuntimeError("cold session planner did not choose the exact plan minimum")
    return result


def corruption_trials(
    selections: Mapping[str, Mapping[str, Sequence[Selection]]]
) -> tuple[int, int]:
    attempted = rejected = 0
    for dataset, by_profile in selections.items():
        for profile, values in by_profile.items():
            for index, selection in enumerate(values):
                text = selection.candidate.text
                start = payload_start(text)
                position = start + (
                    int.from_bytes(
                        hashlib.sha256(f"{FORMAT}|{dataset}|{profile}|{index}".encode()).digest()[:8],
                        "big",
                    )
                    % (len(text) - start)
                )
                replacement = "X" if text[position] != "X" else "Y"
                mutated = text[:position] + replacement + text[position + 1 :]
                attempted += 1
                try:
                    decode_message(mutated)
                except DecodeError:
                    rejected += 1
    return attempted, rejected


def _snapshot(study: Study) -> dict[str, Any]:
    selected_digests: dict[str, dict[str, str]] = {}
    warm_tokens: dict[str, dict[str, int]] = {}
    mode_counts: dict[str, dict[str, Mapping[str, int]]] = {}
    fragment_wins: dict[str, dict[str, int]] = {}
    cold_sessions: dict[str, dict[str, Any]] = {}
    for dataset in study.datasets:
        selected_digests[dataset] = {}
        warm_tokens[dataset] = {}
        mode_counts[dataset] = {}
        fragment_wins[dataset] = {}
        cold_sessions[dataset] = {}
        for profile in study.profiles:
            values = study.selections[dataset][profile.key]
            selected_digests[dataset][profile.key] = _sequence_digest(
                tuple(value.candidate.text for value in values)
            )
            warm_tokens[dataset][profile.key] = sum(value.candidate.tokens for value in values)
            mode_counts[dataset][profile.key] = dict(
                sorted(Counter(value.candidate.mode for value in values).items())
            )
            fragment_wins[dataset][profile.key] = sum(
                value.candidate.tokens < value.required_best_tokens for value in values
            )
            plan = study.sessions[dataset][profile.key]
            cold_sessions[dataset][profile.key] = {
                "activated_bundle": plan.activated_bundle,
                "cold_tokens": plan.cold_tokens,
                "total_tokens": plan.total_tokens,
                "no_bundle_total_tokens": plan.no_bundle_total_tokens,
                "activated_total_tokens": plan.activated_total_tokens,
                "mode_counts": dict(sorted(Counter(item.mode for item in plan.choices).items())),
            }
    return {
        "selected_digests": selected_digests,
        "warm_tokens": warm_tokens,
        "mode_counts": mode_counts,
        "fragment_wins": fragment_wins,
        "cold_sessions": cold_sessions,
        "exact": study.exact,
        "deterministic": study.deterministic,
        "corruptions_attempted": study.corruptions_attempted,
        "corruptions_rejected": study.corruptions_rejected,
    }


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def collect_study(profiles: Sequence[TokenizerProfile]) -> Study:
    datasets = build_datasets()
    prepared = {
        key: tuple(prepare_message(message) for message in messages)
        for key, messages in datasets.items()
    }
    selections: dict[str, dict[str, tuple[Selection, ...]]] = {}
    sessions: dict[str, dict[str, SessionPlan]] = {}
    exact = deterministic = 0
    for dataset, prepared_messages in prepared.items():
        selections[dataset] = {}
        sessions[dataset] = {}
        for profile in profiles:
            values = tuple(select_prepared(item, profile) for item in prepared_messages)
            selections[dataset][profile.key] = values
            sessions[dataset][profile.key] = plan_session(prepared_messages, profile)
            for item, selection in zip(prepared_messages, values, strict=True):
                exact += decode_message(selection.candidate.text) == item.message
                repeated = select_prepared(item, profile)
                deterministic += repeated.candidate == selection.candidate
                if selection.candidate.tokens > min(
                    selection.candidates[mode].tokens for mode in ("J", "E", "V")
                ):
                    raise RuntimeError("warm selector regressed against a required candidate")
    partial = Study(
        datasets,
        prepared,
        selections,
        sessions,
        exact,
        deterministic,
        0,
        0,
        tuple(profiles),
    )
    corruptions = corruption_trials(selections)
    result = Study(
        datasets,
        prepared,
        selections,
        sessions,
        exact,
        deterministic,
        corruptions[0],
        corruptions[1],
        tuple(profiles),
    )
    if EXPECTED_SNAPSHOT_SHA256 != "pending":
        observed = snapshot_sha256(_snapshot(result))
        if observed != EXPECTED_SNAPSHOT_SHA256:
            raise RuntimeError("frozen adaptive selection snapshot changed")
    return result


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def measure_latency(
    study: Study, *, repeats: int
) -> dict[str, Mapping[str, int]]:
    combined = tuple(message for messages in study.datasets.values() for message in messages)
    result: dict[str, Mapping[str, int]] = {}

    direct_encoders: Mapping[str, Callable[[Mapping[str, Any]], str]] = {
        "J": lambda message: encode_envelope("J", _json_payload(message)),
        "E": lambda message: encode_envelope("E", encode_terse_english(message)),
        "V": lambda message: encode_envelope("V", encode_v04(message, holdout_codebook())),
    }
    for mode, encoder in direct_encoders.items():
        encoded = [encoder(message) for message in combined]
        result[mode] = _time_codec(combined, encoded, encoder, decode_message, repeats)

    for profile in study.profiles:
        encoder = lambda message, selected=profile: select_message(message, selected).candidate.text
        encoded = [encoder(message) for message in combined]
        result[f"adaptive:{profile.key}"] = _time_codec(
            combined, encoded, encoder, decode_message, repeats
        )
    return result


def _time_codec(
    messages: Sequence[Mapping[str, Any]],
    encoded: Sequence[str],
    encoder: Callable[[Mapping[str, Any]], str],
    decoder: Callable[[str], Mapping[str, Any]],
    repeats: int,
) -> Mapping[str, int]:
    encode_ns: list[int] = []
    decode_ns: list[int] = []
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            for message in messages:
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
    return {
        "encode_median_ns": int(statistics.median(encode_ns)),
        "encode_p95_ns": _nearest(encode_ns, 0.95),
        "decode_median_ns": int(statistics.median(decode_ns)),
        "decode_p95_ns": _nearest(decode_ns, 0.95),
    }


def _source_digest(name: str) -> str:
    path = Path(__file__).with_name(name)
    return sha256_file(path) if path.is_file() else "not-present"


def _percent_saved(candidate: int, baseline: int) -> str:
    return f"{100.0 * (1.0 - candidate / baseline):+.2f}%"


def render_report(
    study: Study,
    latency: Mapping[str, Mapping[str, int]],
) -> str:
    expected_total = sum(len(messages) for messages in study.datasets.values()) * len(study.profiles)
    snapshot = _snapshot(study)
    fragment_total = sum(
        count
        for by_profile in snapshot["fragment_wins"].values()
        for count in by_profile.values()
    )
    lines = [
        "# Adaptive surface v0.5 receiver-token selection",
        "",
        "## Result",
        "",
        f"Across {expected_total:,} message/receiver pairs, the warm selector chose the exact lowest complete token count among the required v0.4 structured, Controlled Terse English, and minified JSON envelopes after including the mode marker and all applicable integrity overhead. It had **zero warm token regressions** against the best eligible required baseline on every individual message.",
        "",
        f"The safely lossless fragment candidate beat all three required whole-message candidates on **{fragment_total:,}/{expected_total:,} pairs**. Its complete envelope was counted before selection; an optimistic unframed fragment oracle is not used in the headline.",
        "",
        f"Exact semantic recovery and deterministic reselection passed for **{study.exact:,}/{expected_total:,}** pairs. Payload mutations were rejected in **{study.corruptions_rejected:,}/{study.corruptions_attempted:,}** deterministic trials.",
        "",
        "No language model was invoked. These results do not measure task success, understanding, repair behavior, generation cost, inference latency, energy, or adoption, and they do not establish superiority over external projects.",
        "",
        "## Selection contract",
        "",
        "Every candidate begins with `A5 + mode`. JSON, controlled text, and fragment candidates then carry an 11-character checksum, a colon, and the payload. The checksum is the unpadded Base64url form of an eight-byte BLAKE2s digest over mode and payload; it detects accidental corruption but is not authentication. Structured mode uses `A5V:` followed by the v0.4 payload, reusing that payload's existing 64-bit checksum and canonical re-encoding check instead of paying for redundant integrity data.",
        "",
        "For one negotiated receiver tokenizer, the selector counts every complete candidate without special tokens and chooses the tuple `(token_count, fixed_mode_rank, text)`. Fixed mode rank is JSON, controlled text, structured surface, then fragment surface. Therefore ties are deterministic and do not silently prefer a representation that requires cold state.",
        "",
        "## Warm exact token totals and choices",
        "",
        "Required-best is the per-message oracle over the three required complete envelopes. Adaptive includes the lossless fragment envelope. Equality is required unless fragments improve it.",
        "",
    ]
    for dataset, messages in study.datasets.items():
        lines.extend([
            f"### {DATASET_LABELS[dataset].title()}",
            "",
            "| Receiver tokenizer | JSON | Controlled text | v0.4 structured | Required-best | Fragment | Adaptive | vs required-best | Adaptive J/E/V/F |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for profile in study.profiles:
            selections = study.selections[dataset][profile.key]
            totals = {
                mode: sum(item.candidates[mode].tokens for item in selections)
                for mode in MODE_ORDER
            }
            required = sum(item.required_best_tokens for item in selections)
            adaptive = sum(item.candidate.tokens for item in selections)
            counts = Counter(item.candidate.mode for item in selections)
            lines.append(
                f"| {profile.display_name} | {totals['J']:,} | {totals['E']:,} | {totals['V']:,} | "
                f"{required:,} | {totals['F']:,} | {adaptive:,} | {_percent_saved(adaptive, required)} | "
                f"{counts['J']}/{counts['E']}/{counts['V']}/{counts['F']} |"
            )
        lines.append("")

    lines.extend([
        "## Cold session planning",
        "",
        "The cold planner compares exactly two complete session plans. The no-bundle plan restricts every message and fragment to JSON or controlled text. The activated plan charges the static profile and frozen codebook exactly once, then permits all warm candidates. The smaller total wins; a tie stays unactivated.",
        "",
        "| Dataset | Receiver tokenizer | Bundle tokens | No-bundle total | Activated total | Selected total | Activated? | Selected J/E/V/F |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for dataset in study.datasets:
        for profile in study.profiles:
            plan = study.sessions[dataset][profile.key]
            bundle_tokens, _bundle_bytes = cold_bundle_metrics(profile)
            counts = Counter(item.mode for item in plan.choices)
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {profile.display_name} | {bundle_tokens:,} | "
                f"{plan.no_bundle_total_tokens:,} | {plan.activated_total_tokens:,} | "
                f"{plan.total_tokens:,} | {'yes' if plan.activated_bundle else 'no'} | "
                f"{counts['J']}/{counts['E']}/{counts['V']}/{counts['F']} |"
            )

    lines.extend([
        "",
        "## Bytes and unfavorable transport cases",
        "",
        "The selector optimizes receiver tokens, not UTF-8 bytes. The table retains aggregate bytes and counts messages where adaptive used more bytes than the smallest required envelope.",
        "",
        "| Dataset | Receiver tokenizer | JSON bytes | Controlled bytes | Structured bytes | Adaptive bytes | Messages above byte-minimum | Worst byte regression |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for dataset in study.datasets:
        for profile in study.profiles:
            selections = study.selections[dataset][profile.key]
            totals = {
                mode: sum(item.candidates[mode].utf8_bytes for item in selections)
                for mode in ("J", "E", "V")
            }
            adaptive_bytes = sum(item.candidate.utf8_bytes for item in selections)
            worse = 0
            worst = 0.0
            for item in selections:
                minimum = min(item.candidates[mode].utf8_bytes for mode in ("J", "E", "V"))
                if item.candidate.utf8_bytes > minimum:
                    worse += 1
                    worst = max(worst, 100.0 * (item.candidate.utf8_bytes / minimum - 1.0))
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {profile.display_name} | {totals['J']:,} | "
                f"{totals['E']:,} | {totals['V']:,} | {adaptive_bytes:,} | {worse} | {worst:+.2f}% |"
            )

    lines.extend([
        "",
        "## Fragment experiment",
        "",
        "The fragment envelope is safely lossless for the frozen JSON-compatible corpus. It uses the fixed 13-field canonical order. Every record contains a mode, canonical character length, and payload. A field can use canonical JSON value text, the controlled value grammar, or optimal codebook symbols carrying canonical JSON value bytes. The outer checksum covers every record, and decoding performs shared semantic validation.",
        "",
        "Fragment modes are chosen by exact token count for each complete record. Because tokenizer merges can cross record boundaries, this local choice is not claimed to be the globally optimal fragment combination. The final complete fragment envelope is nevertheless counted exactly and can never make adaptive selection worse: it wins only when its complete count beats the whole-message candidates.",
        "",
        "| Dataset | Receiver tokenizer | Fragment wins | Tokens saved by winning fragments | Structured fragment records | Total fragment records |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for dataset in study.datasets:
        for profile in study.profiles:
            selections = study.selections[dataset][profile.key]
            wins = [item for item in selections if item.candidate.mode == "F"]
            saved = sum(item.required_best_tokens - item.candidate.tokens for item in wins)
            structured_records = sum(
                candidate.fragment_modes.count("V")
                for item in selections
                for candidate in (item.candidates["F"],)
            )
            total_records = len(selections) * len(FRAGMENT_FIELDS)
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {profile.display_name} | {len(wins)} | "
                f"{saved:,} | {structured_records:,} | {total_records:,} |"
            )

    lines.extend([
        "",
        "## Reference implementation latency",
        "",
        "Times are per message on this machine. Direct rows encode only one known representation. Adaptive rows build all representations, construct fragment candidates, run the receiver tokenizer repeatedly, and choose the minimum; their overhead is intentionally visible. Paths do unequal work and are not protocol limits.",
        "",
        "| Path | Encode/select median | Encode/select p95 | Decode median | Decode p95 |",
        "|---|---:|---:|---:|---:|",
    ])
    for mode in ("J", "E", "V"):
        item = latency[mode]
        lines.append(
            f"| direct {MODE_LABELS[mode]} | {item['encode_median_ns']/1000:.1f} µs | "
            f"{item['encode_p95_ns']/1000:.1f} µs | {item['decode_median_ns']/1000:.1f} µs | "
            f"{item['decode_p95_ns']/1000:.1f} µs |"
        )
    for profile in study.profiles:
        item = latency[f"adaptive:{profile.key}"]
        lines.append(
            f"| adaptive for {profile.display_name} | {item['encode_median_ns']/1000:.1f} µs | "
            f"{item['encode_p95_ns']/1000:.1f} µs | {item['decode_median_ns']/1000:.1f} µs | "
            f"{item['decode_p95_ns']/1000:.1f} µs |"
        )

    bundle_bytes = cold_bundle_metrics(study.profiles[0])[1]
    lines.extend([
        "",
        "## Integrity, resource, and scope checks",
        "",
        f"- Exact semantic recovery: {study.exact:,}/{expected_total:,}.",
        f"- Deterministic receiver-specific reselection: {study.deterministic:,}/{expected_total:,}.",
        f"- Deterministic payload-corruption rejection: {study.corruptions_rejected:,}/{study.corruptions_attempted:,}.",
        f"- Cold profile plus codebook transfer: {bundle_bytes:,} UTF-8 bytes before tokenizer-specific counting.",
        "- The adaptive decoder limits total UTF-8 bytes, validates the fixed header, verifies the checksum before parsing, bounds structured expansion, rejects non-canonical values and lengths, and applies shared semantic validation.",
        "- The checksum is accidental-error detection only. It does not authenticate a sender, grant authority, or make untrusted content executable.",
        "",
        "## Frozen inputs and reproducibility",
        "",
        f"- Format: `{FORMAT}`",
        f"- Development partition: {len(study.datasets['development'])} messages; SHA-256 `{EXPECTED_TRAIN_SHA256}`",
        f"- Grouped holdout: {len(study.datasets['grouped_holdout'])} messages; SHA-256 `{EXPECTED_HOLDOUT_SHA256}`",
        f"- Out of domain: {len(study.datasets['out_of_domain'])} messages; SHA-256 `{EXPECTED_OOD_SHA256}`",
        f"- Frozen codebook SHA-256: `{holdout_codebook().sha256}`",
        f"- Complete adaptive snapshot SHA-256: `{snapshot_sha256(snapshot)}`",
        f"- Tokenizer packages: `tiktoken=={TIKTOKEN_VERSION}`, `tokenizers=={TOKENIZERS_VERSION}`",
        "",
    ])
    for profile in study.profiles:
        lines.append(
            f"- `{profile.key}`: {profile.display_name}; {profile.implementation}; vocabulary {profile.vocabulary_size:,}; fingerprint `{profile.fingerprint}`"
        )
    lines.extend([
        "",
        "Selected adaptive text-sequence SHA-256 values:",
        "",
    ])
    for dataset in study.datasets:
        for profile in study.profiles:
            digest = snapshot["selected_digests"][dataset][profile.key]
            lines.append(f"- {DATASET_LABELS[dataset]}, `{profile.key}`: `{digest}`")
    lines.extend([
        "",
        "Source SHA-256 values:",
        "",
        f"- selector and benchmark: `{_source_digest('urusilla_adaptive_surface_v05.py')}`",
        f"- conformance tests: `{_source_digest('test_urusilla_adaptive_surface_v05.py')}`",
        "",
        "Environment:",
        "",
        f"- Python: `{platform.python_version()}`",
        f"- Platform: `{platform.platform()}`",
        "",
        "Reproduce from the repository root:",
        "",
        "```bash",
        "PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_adaptive_surface_v05.py --benchmark --assets-dir work/tokenizer_assets",
        "PYTHONPATH=. work/tokenizer_venv/bin/python -m unittest test_urusilla_adaptive_surface_v05.py -v",
        "```",
        "",
        "## Limitations",
        "",
        "- Selection assumes the receiver tokenizer is correctly negotiated and locally reproducible. Hosted billing, chat templates, BOS/EOS, surrounding prompts, and transport framing can change the real cost.",
        "- Development is in-sample. Grouped holdout shares a synthetic generator family. The out-of-domain set contains only ten repository-authored messages.",
        "- The cold planner is an offline session optimum with full knowledge of the measured message sequence. A streaming agent needs an explicit horizon or conservative activation policy and may perform worse.",
        "- Fragment records are exact, but local per-record token minimization is not a proof of globally minimum fragment tokenization. A globally exact fragment search remains future work.",
        "- Checksums add material token and byte overhead. Authentication, signatures, encryption, replay defense, and negotiation failure are outside this experiment.",
        "- Exact serialization recovery does not show that an LLM can understand or produce any candidate. Task success and repair behavior remain unmeasured.",
        "- Token savings do not directly imply lower energy, latency, memory, hosted cost, or total application tokens. Adaptive selection itself adds substantial CPU work.",
        "",
    ])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--assets-dir", type=Path, default=default_asset_root())
    parser.add_argument("--report", type=Path, default=Path(__file__).with_name(REPORT_NAME))
    parser.add_argument("--repeats", type=int, default=3)
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
    latency = measure_latency(study, repeats=args.repeats)
    report = render_report(study, latency)
    args.report.write_text(report, encoding="utf-8")
    if args.dump_metrics:
        print(json.dumps({"snapshot": _snapshot(study), "latency_ns": latency}, indent=2, sort_keys=True))
    else:
        print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
