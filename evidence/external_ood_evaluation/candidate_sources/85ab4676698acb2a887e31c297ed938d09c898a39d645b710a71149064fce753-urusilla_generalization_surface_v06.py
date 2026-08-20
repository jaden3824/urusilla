#!/usr/bin/env python3
"""Generalization-first readable surface and receiver pre-input selector.

This bounded v0.6 experiment derives a compact key/value alias profile from
the frozen development partition only.  The profile optimizes a regularized
frequency-weighted UTF-8 proxy rather than holdout tokens or checksum luck.
It is then frozen before evaluation on the grouped holdout and out-of-domain
corpora.

The receiver pre-input selector compares complete texts for the negotiated
tokenizer: the frozen v0.5 adaptive result, the existing readable symbolic
surface, and the train-only schema-aware surface.  The v0.5 candidate has the
first tie rank, so the extension cannot regress any warm receiver/message
pair.  Cold planning enumerates activation states and retains the complete
v0.5 plan as an eligible option.

No language model or paid service is used.  Token counts measure serialization
only, not comprehension, task success, energy, adoption, or state of the art.
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
import os
from pathlib import Path
import platform
import re
import statistics
import time
from typing import Any, Callable, Mapping, Sequence

# Temporary bridges to frozen fixtures and implementations.  These imports do
# not mutate the legacy-named inputs.
from urusilla_benchmark import corpus_digest, json_encode
from urusilla import DecodeError, ValidationError, normalize_message
from urusilla_token_surface_holdout import (
    EXPECTED_HOLDOUT_SHA256,
    EXPECTED_OOD_SHA256,
    EXPECTED_TRAIN_SHA256,
    _sequence_digest,
)
from urusilla_tokenizer_benchmark import (
    TIKTOKEN_VERSION,
    TOKENIZERS_VERSION,
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
    sha256_file,
)

from urusilla_adaptive_surface_v05 import (
    PreparedMessage as AdaptivePreparedMessage,
    cold_bundle_metrics,
    decode_message as decode_adaptive,
    prepare_message as prepare_adaptive,
    select_prepared as select_adaptive,
    build_datasets,
)
from urusilla_model_comprehension_pilot import (
    GRAMMARS,
    SYMBOLIC_FIELDS,
    SYMBOLIC_HEADER_CHARACTERS,
    SYMBOLIC_PREFIX,
    decode_symbolic,
    encode_symbolic,
)
from urusilla_terse_english_benchmark import (
    _ValueParser,
    _render_value,
    encode_terse_english,
)
from urusilla_token_surface_v04 import encode_message as encode_v04
from urusilla_token_surface_holdout import holdout_codebook


FORMAT = "urusilla-generalization-surface-v0.6-experimental"
REPORT_NAME = "GENERALIZATION_SURFACE_V06_RESULTS.md"
OPTIMIZED_PREFIX = "@2"
CHECKSUM_CHARACTERS = 11
OPTIMIZED_HEADER_CHARACTERS = len(OPTIMIZED_PREFIX) + CHECKSUM_CHARACTERS + 1
MAX_SURFACE_UTF8_BYTES = 64 * 1024 * 1024
ALIAS_CODES = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
MAX_KEY_ALIASES = len(ALIAS_CODES)
MAX_VALUE_ALIASES = len(ALIAS_CODES)
MIN_ALIAS_OCCURRENCES = 2
ESCAPE_PREFIX = "~"
_CHECKSUM_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_OPTIMIZED_DOMAIN = b"UrusillaGeneralizationSurface-v0.6\x00"

DATASET_LABELS = {
    "development": "development training partition",
    "grouped_holdout": "grouped holdout",
    "out_of_domain": "out of domain",
}
BASELINE_LABELS = {
    "json": "sorted minified JSON",
    "terse": "Controlled Terse English",
    "v04": "v0.4 structured surface",
    "v05": "v0.5 oracle-free adaptive selection",
    "symbolic": "existing readable symbolic surface",
    "optimized": "train-only schema-aware surface",
    "selected": "v0.6 receiver pre-input selection",
}
MODE_RANK = {"v05": 0, "symbolic": 1, "optimized": 2}
COMPACT_VALUE_FIELDS = frozenset({"recipients", "expected", "body", "meta"})

# Filled after the first controlled four-tokenizer run.  Tests reject pending
# values and recompute both digests from frozen inputs.
EXPECTED_PROFILE_SHA256 = "f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d"
EXPECTED_SNAPSHOT_SHA256 = "81993226c8fe9b2bd631a2e63e59355fa8e31e993ecbe14af1848a9c5a44bb57"
EXPECTED_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}


@dataclass(frozen=True)
class AliasProfile:
    training_corpus_sha256: str
    key_aliases: tuple[tuple[str, str], ...]
    value_aliases: tuple[tuple[str, str], ...]
    objective: str = "frequency_times_utf8_bytes_saved"

    @property
    def key_to_alias(self) -> dict[str, str]:
        return {original: alias for alias, original in self.key_aliases}

    @property
    def alias_to_key(self) -> dict[str, str]:
        return dict(self.key_aliases)

    @property
    def value_to_alias(self) -> dict[str, str]:
        return {original: alias for alias, original in self.value_aliases}

    @property
    def alias_to_value(self) -> dict[str, str]:
        return dict(self.value_aliases)


@dataclass(frozen=True)
class PreparedMessage:
    message: Mapping[str, Any]
    adaptive: AdaptivePreparedMessage
    raw_texts: Mapping[str, str]
    symbolic_text: str
    optimized_text: str


@dataclass(frozen=True)
class Candidate:
    mode: str
    text: str
    tokens: int
    utf8_bytes: int
    uses_structured_bundle: bool
    uses_symbolic_grammar: bool
    uses_optimized_profile: bool


@dataclass(frozen=True)
class Selection:
    candidate: Candidate
    baseline: Candidate
    candidates: Mapping[str, Candidate]


@dataclass(frozen=True)
class ColdOption:
    structured_bundle: bool
    symbolic_grammar: bool
    optimized_profile: bool
    cold_tokens: int
    cold_bytes: int
    message_tokens: int
    total_tokens: int
    choices: tuple[Candidate, ...]


@dataclass(frozen=True)
class ColdPlan:
    selected: ColdOption
    options: tuple[ColdOption, ...]
    baseline_total_tokens: int


@dataclass(frozen=True)
class Study:
    datasets: Mapping[str, tuple[dict[str, Any], ...]]
    alias_profile: AliasProfile
    prepared: Mapping[str, tuple[PreparedMessage, ...]]
    selections: Mapping[str, Mapping[str, tuple[Selection, ...]]]
    cold_plans: Mapping[str, Mapping[str, ColdPlan]]
    profiles: tuple[TokenizerProfile, ...]
    exact_existing: int
    exact_optimized: int
    exact_selected: int
    deterministic_existing: int
    deterministic_optimized: int
    deterministic_selected: int
    corruptions_attempted: Mapping[str, int]
    corruptions_rejected: Mapping[str, int]


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


def _profile_core(profile: AliasProfile) -> dict[str, Any]:
    return {
        "format": "urusilla-schema-alias-profile-v0.6",
        "training_corpus_sha256": profile.training_corpus_sha256,
        "objective": profile.objective,
        "key_aliases": [list(item) for item in profile.key_aliases],
        "value_aliases": [list(item) for item in profile.value_aliases],
    }


def profile_capsule(profile: AliasProfile) -> str:
    """Return the canonical readable cold profile capsule."""

    return _canonical_json(_profile_core(profile))


def profile_sha256(profile: AliasProfile) -> str:
    return hashlib.sha256(profile_capsule(profile).encode("utf-8")).hexdigest()


def existing_grammar_capsule() -> str:
    return GRAMMARS["symbolic"]


def optimized_grammar_capsule() -> str:
    fields = ",".join(f"{label}={field}" for label, field in SYMBOLIC_FIELDS)
    compact = ",".join(sorted(COMPACT_VALUE_FIELDS))
    return (
        "@2 readable schema grammar; fixed fields "
        + fields
        + "; scalar values use canonical JSON; fields "
        + compact
        + " use null/true/false, numbers, safe bare strings, lists [v,...], "
        "and maps {key=v,...}; uppercase aliases expand through the negotiated "
        "train-only profile; checksum is 11 Base64url characters."
    )


def _walk_nested(value: Any, key_counts: Counter[str], value_counts: Counter[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_counts[key] += 1
            _walk_nested(item, key_counts, value_counts)
    elif isinstance(value, list):
        for item in value:
            _walk_nested(item, key_counts, value_counts)
    elif isinstance(value, str):
        value_counts[value] += 1


def _alias_rank(counts: Mapping[str, int], limit: int) -> tuple[str, ...]:
    candidates = [
        value
        for value, frequency in counts.items()
        if frequency >= MIN_ALIAS_OCCURRENCES and len(value.encode("utf-8")) > 1
    ]
    candidates.sort(
        key=lambda value: (
            -counts[value] * (len(value.encode("utf-8")) - 1),
            -counts[value],
            value.encode("utf-8"),
        )
    )
    return tuple(candidates[:limit])


def derive_alias_profile(training_messages: Sequence[Mapping[str, Any]]) -> AliasProfile:
    """Derive the profile from the exact frozen development partition only."""

    messages = tuple(normalize_message(message) for message in training_messages)
    digest = corpus_digest(messages)
    if digest != EXPECTED_TRAIN_SHA256:
        raise RuntimeError("alias training input is not the frozen development partition")

    key_counts: Counter[str] = Counter()
    value_counts: Counter[str] = Counter()
    for message in messages:
        for field in ("body", "meta"):
            _walk_nested(message[field], key_counts, value_counts)
        for field in ("sender", "recipients", "act", "schema", "expected"):
            _walk_nested(message[field], Counter(), value_counts)

    key_values = _alias_rank(key_counts, MAX_KEY_ALIASES)
    string_values = _alias_rank(value_counts, MAX_VALUE_ALIASES)
    profile = AliasProfile(
        training_corpus_sha256=digest,
        key_aliases=tuple(zip(ALIAS_CODES, key_values, strict=True)),
        value_aliases=tuple(zip(ALIAS_CODES, string_values, strict=True)),
    )
    if len(profile.key_aliases) != MAX_KEY_ALIASES:
        raise RuntimeError("training corpus did not provide enough key aliases")
    if len(profile.value_aliases) != MAX_VALUE_ALIASES:
        raise RuntimeError("training corpus did not provide enough value aliases")
    return profile


def _encode_transform(value: Any, profile: AliasProfile) -> Any:
    key_to_alias = profile.key_to_alias
    value_to_alias = profile.value_to_alias
    key_codes = set(profile.alias_to_key)
    value_codes = set(profile.alias_to_value)

    def transform(item: Any) -> Any:
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, nested in item.items():
                encoded_key = key_to_alias.get(key)
                if encoded_key is None:
                    encoded_key = (
                        ESCAPE_PREFIX + key
                        if key in key_codes or key.startswith(ESCAPE_PREFIX)
                        else key
                    )
                if encoded_key in result:
                    raise ValidationError("alias transform produced a duplicate key")
                result[encoded_key] = transform(nested)
            return result
        if isinstance(item, list):
            return [transform(nested) for nested in item]
        if isinstance(item, str):
            alias = value_to_alias.get(item)
            if alias is not None:
                return alias
            if item in value_codes or item.startswith(ESCAPE_PREFIX):
                return ESCAPE_PREFIX + item
        return item

    return transform(value)


def _decode_transform(value: Any, profile: AliasProfile) -> Any:
    alias_to_key = profile.alias_to_key
    alias_to_value = profile.alias_to_value

    def transform(item: Any) -> Any:
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for encoded_key, nested in item.items():
                if encoded_key in alias_to_key:
                    key = alias_to_key[encoded_key]
                elif encoded_key.startswith(ESCAPE_PREFIX):
                    key = encoded_key[len(ESCAPE_PREFIX) :]
                else:
                    key = encoded_key
                if key in result:
                    raise DecodeError("alias expansion produced a duplicate key")
                result[key] = transform(nested)
            return result
        if isinstance(item, list):
            return [transform(nested) for nested in item]
        if isinstance(item, str):
            if item in alias_to_value:
                return alias_to_value[item]
            if item.startswith(ESCAPE_PREFIX):
                return item[len(ESCAPE_PREFIX) :]
        return item

    return transform(value)


def _optimized_payload(message: Mapping[str, Any], profile: AliasProfile) -> str:
    canonical = normalize_message(message)
    parts: list[str] = []
    for label, field in SYMBOLIC_FIELDS:
        transformed = _encode_transform(canonical[field], profile)
        rendered = (
            _render_value(transformed)
            if field in COMPACT_VALUE_FIELDS
            else _canonical_json(transformed)
        )
        parts.append(label + rendered)
    return "".join(parts)


def _optimized_checksum(payload: str, profile: AliasProfile) -> str:
    digest = hashlib.blake2s(
        _OPTIMIZED_DOMAIN
        + bytes.fromhex(profile_sha256(profile))
        + b"\x00"
        + payload.encode("utf-8"),
        digest_size=8,
    ).digest()
    result = _b64url(digest)
    if len(result) != CHECKSUM_CHARACTERS:
        raise RuntimeError("optimized checksum width changed")
    return result


def encode_optimized(message: Mapping[str, Any], profile: AliasProfile) -> str:
    payload = _optimized_payload(message, profile)
    result = OPTIMIZED_PREFIX + _optimized_checksum(payload, profile) + ":" + payload
    if len(result.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise ValidationError("optimized surface exceeds the UTF-8 size limit")
    return result


class _OptimizedParser:
    def __init__(self, payload: str):
        self.payload = payload
        self.position = 0
        self.decoder = json.JSONDecoder(
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
        )

    def literal(self, expected: str) -> None:
        if not self.payload.startswith(expected, self.position):
            raise DecodeError(
                f"expected optimized label {expected!r} at character {self.position}"
            )
        self.position += len(expected)

    def value(self, field: str) -> Any:
        if self.position >= len(self.payload):
            raise DecodeError("truncated optimized value")
        if field in COMPACT_VALUE_FIELDS:
            parser = _ValueParser(self.payload, self.position)
            try:
                value = parser.value()
            except RecursionError as exc:
                raise DecodeError("optimized value nesting exceeds parser resources") from exc
            self.position = parser.position
            return value
        try:
            value, end = self.decoder.raw_decode(self.payload, self.position)
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise DecodeError(
                f"invalid optimized JSON scalar at character {self.position}"
            ) from exc
        self.position = end
        return value


def decode_optimized(text: str, profile: AliasProfile) -> dict[str, Any]:
    """Verify checksum, expand aliases, validate, and reject non-canonical text."""

    if not isinstance(text, str):
        raise DecodeError("optimized surface must be text")
    if len(text.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise DecodeError("optimized surface exceeds the UTF-8 size limit")
    if len(text) <= OPTIMIZED_HEADER_CHARACTERS or not text.startswith(OPTIMIZED_PREFIX):
        raise DecodeError("unknown or truncated optimized surface")
    supplied = text[len(OPTIMIZED_PREFIX) : len(OPTIMIZED_PREFIX) + CHECKSUM_CHARACTERS]
    separator = len(OPTIMIZED_PREFIX) + CHECKSUM_CHARACTERS
    if _CHECKSUM_PATTERN.fullmatch(supplied) is None or text[separator] != ":":
        raise DecodeError("optimized header is malformed")
    payload = text[separator + 1 :]
    if not payload:
        raise DecodeError("optimized payload is empty")
    if not hmac.compare_digest(supplied, _optimized_checksum(payload, profile)):
        raise DecodeError("optimized checksum mismatch")

    parser = _OptimizedParser(payload)
    encoded: dict[str, Any] = {}
    for label, field in SYMBOLIC_FIELDS:
        parser.literal(label)
        encoded[field] = parser.value(field)
    if parser.position != len(payload):
        raise DecodeError("optimized surface has trailing data")
    try:
        canonical = normalize_message(_decode_transform(encoded, profile))
    except ValidationError as exc:
        raise DecodeError(str(exc)) from exc
    if encode_optimized(canonical, profile) != text:
        raise DecodeError("optimized surface is valid but not canonical")
    return canonical


def prepare_message(message: Mapping[str, Any], profile: AliasProfile) -> PreparedMessage:
    canonical = normalize_message(message)
    return PreparedMessage(
        message=canonical,
        adaptive=prepare_adaptive(canonical),
        raw_texts={
            "json": json_encode(canonical).decode("utf-8"),
            "terse": encode_terse_english(canonical),
            "v04": encode_v04(canonical, holdout_codebook()),
        },
        symbolic_text=encode_symbolic(canonical),
        optimized_text=encode_optimized(canonical, profile),
    )


def _candidate(
    mode: str,
    text: str,
    tokenizer: TokenizerProfile,
    *,
    uses_structured_bundle: bool = False,
    uses_symbolic_grammar: bool = False,
    uses_optimized_profile: bool = False,
) -> Candidate:
    return Candidate(
        mode=mode,
        text=text,
        tokens=tokenizer.count(text),
        utf8_bytes=len(text.encode("utf-8")),
        uses_structured_bundle=uses_structured_bundle,
        uses_symbolic_grammar=uses_symbolic_grammar,
        uses_optimized_profile=uses_optimized_profile,
    )


def select_prepared(
    prepared: PreparedMessage,
    tokenizer: TokenizerProfile,
    *,
    allow_structured_bundle: bool = True,
    allow_symbolic: bool = True,
    allow_optimized: bool = True,
) -> Selection:
    adaptive = select_adaptive(
        prepared.adaptive,
        tokenizer,
        allow_bundle=allow_structured_bundle,
    ).candidate
    baseline = _candidate(
        "v05",
        adaptive.text,
        tokenizer,
        uses_structured_bundle=adaptive.uses_bundle,
    )
    candidates: dict[str, Candidate] = {"v05": baseline}
    if allow_symbolic:
        candidates["symbolic"] = _candidate(
            "symbolic",
            prepared.symbolic_text,
            tokenizer,
            uses_symbolic_grammar=True,
        )
    if allow_optimized:
        candidates["optimized"] = _candidate(
            "optimized",
            prepared.optimized_text,
            tokenizer,
            uses_optimized_profile=True,
        )
    selected = min(
        candidates.values(),
        key=lambda item: (item.tokens, MODE_RANK[item.mode], item.text),
    )
    if selected.tokens > baseline.tokens:
        raise RuntimeError("pre-input selector regressed against v0.5")
    return Selection(selected, baseline, candidates)


def select_message(
    message: Mapping[str, Any],
    alias_profile: AliasProfile,
    tokenizer: TokenizerProfile,
) -> Selection:
    return select_prepared(prepare_message(message, alias_profile), tokenizer)


def decode_selected(text: str, alias_profile: AliasProfile) -> dict[str, Any]:
    if not isinstance(text, str):
        raise DecodeError("selected surface must be text")
    if text.startswith(OPTIMIZED_PREFIX):
        return decode_optimized(text, alias_profile)
    if text.startswith(SYMBOLIC_PREFIX):
        return decode_symbolic(text)
    return decode_adaptive(text)


def cold_artifact_metrics(
    tokenizer: TokenizerProfile, alias_profile: AliasProfile
) -> dict[str, tuple[int, int]]:
    artifacts = {
        "symbolic_grammar": existing_grammar_capsule(),
        "optimized_grammar": optimized_grammar_capsule(),
        "optimized_profile": profile_capsule(alias_profile),
    }
    result = {
        key: (tokenizer.count(text), len(text.encode("utf-8")))
        for key, text in artifacts.items()
    }
    structured_tokens, structured_bytes = cold_bundle_metrics(tokenizer)
    result["structured_bundle"] = (structured_tokens, structured_bytes)
    return result


def plan_cold_session(
    prepared_messages: Sequence[PreparedMessage],
    tokenizer: TokenizerProfile,
    alias_profile: AliasProfile,
) -> ColdPlan:
    artifacts = cold_artifact_metrics(tokenizer, alias_profile)
    options: list[ColdOption] = []
    for structured in (False, True):
        for symbolic in (False, True):
            for optimized in (False, True):
                choices = tuple(
                    select_prepared(
                        prepared,
                        tokenizer,
                        allow_structured_bundle=structured,
                        allow_symbolic=symbolic,
                        allow_optimized=optimized,
                    ).candidate
                    for prepared in prepared_messages
                )
                cold_tokens = (
                    (artifacts["structured_bundle"][0] if structured else 0)
                    + (artifacts["symbolic_grammar"][0] if symbolic else 0)
                    + (artifacts["optimized_grammar"][0] if optimized else 0)
                    + (artifacts["optimized_profile"][0] if optimized else 0)
                )
                cold_bytes = (
                    (artifacts["structured_bundle"][1] if structured else 0)
                    + (artifacts["symbolic_grammar"][1] if symbolic else 0)
                    + (artifacts["optimized_grammar"][1] if optimized else 0)
                    + (artifacts["optimized_profile"][1] if optimized else 0)
                )
                message_tokens = sum(choice.tokens for choice in choices)
                options.append(
                    ColdOption(
                        structured,
                        symbolic,
                        optimized,
                        cold_tokens,
                        cold_bytes,
                        message_tokens,
                        cold_tokens + message_tokens,
                        choices,
                    )
                )
    options.sort(
        key=lambda item: (
            item.total_tokens,
            item.cold_tokens,
            item.structured_bundle,
            item.symbolic_grammar,
            item.optimized_profile,
        )
    )
    baseline_total = min(
        item.total_tokens
        for item in options
        if not item.symbolic_grammar and not item.optimized_profile
    )
    selected = options[0]
    if selected.total_tokens > baseline_total:
        raise RuntimeError("cold planner regressed against the complete v0.5 plan")
    return ColdPlan(selected, tuple(options), baseline_total)


def _payload_start(text: str) -> int:
    if text.startswith(OPTIMIZED_PREFIX):
        return OPTIMIZED_HEADER_CHARACTERS
    if text.startswith(SYMBOLIC_PREFIX):
        return SYMBOLIC_HEADER_CHARACTERS
    from urusilla_adaptive_surface_v05 import payload_start

    return payload_start(text)


def _mutate_payload(text: str, seed: str) -> str:
    start = _payload_start(text)
    if start >= len(text):
        raise RuntimeError("surface has no payload to mutate")
    offset = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")
    position = start + offset % (len(text) - start)
    replacement = "X" if text[position] != "X" else "Y"
    return text[:position] + replacement + text[position + 1 :]


def _corruption_trials(
    datasets: Mapping[str, Sequence[PreparedMessage]],
    selections: Mapping[str, Mapping[str, Sequence[Selection]]],
    profiles: Sequence[TokenizerProfile],
    alias_profile: AliasProfile,
) -> tuple[dict[str, int], dict[str, int]]:
    attempted = Counter()
    rejected = Counter()
    for dataset, messages in datasets.items():
        for index, prepared in enumerate(messages):
            for mode, text in (
                ("symbolic", prepared.symbolic_text),
                ("optimized", prepared.optimized_text),
            ):
                mutated = _mutate_payload(text, f"{FORMAT}|{dataset}|{mode}|{index}")
                attempted[mode] += 1
                try:
                    decode_selected(mutated, alias_profile)
                except DecodeError:
                    rejected[mode] += 1
        for tokenizer in profiles:
            for index, selection in enumerate(selections[dataset][tokenizer.key]):
                mutated = _mutate_payload(
                    selection.candidate.text,
                    f"{FORMAT}|{dataset}|selected|{tokenizer.key}|{index}",
                )
                attempted["selected"] += 1
                try:
                    decode_selected(mutated, alias_profile)
                except DecodeError:
                    rejected["selected"] += 1
    return dict(attempted), dict(rejected)


def collect_study(profiles: Sequence[TokenizerProfile]) -> Study:
    tokenizer_profiles = tuple(profiles)
    expected_keys = (
        "cl100k_base",
        "o200k_base",
        "qwen2_5_7b_instruct",
        "mistral_7b_instruct_v03",
    )
    if tuple(profile.key for profile in tokenizer_profiles) != expected_keys:
        raise RuntimeError("study requires the four pinned tokenizer profiles in order")
    for profile in tokenizer_profiles:
        if profile.fingerprint != EXPECTED_TOKENIZER_FINGERPRINTS[profile.key]:
            raise RuntimeError(f"pinned tokenizer fingerprint changed: {profile.key}")
    datasets = build_datasets()
    expected_digests = {
        "development": EXPECTED_TRAIN_SHA256,
        "grouped_holdout": EXPECTED_HOLDOUT_SHA256,
        "out_of_domain": EXPECTED_OOD_SHA256,
    }
    for name, messages in datasets.items():
        if corpus_digest(messages) != expected_digests[name]:
            raise RuntimeError(f"frozen {name} corpus changed")

    alias_profile = derive_alias_profile(datasets["development"])
    observed_profile = profile_sha256(alias_profile)
    if EXPECTED_PROFILE_SHA256 != "pending" and observed_profile != EXPECTED_PROFILE_SHA256:
        raise RuntimeError("frozen train-only alias profile changed")

    prepared = {
        name: tuple(prepare_message(message, alias_profile) for message in messages)
        for name, messages in datasets.items()
    }
    selections: dict[str, dict[str, tuple[Selection, ...]]] = {}
    cold_plans: dict[str, dict[str, ColdPlan]] = {}
    exact_selected = deterministic_selected = 0
    for name, messages in prepared.items():
        selections[name] = {}
        cold_plans[name] = {}
        for tokenizer in tokenizer_profiles:
            values = tuple(select_prepared(item, tokenizer) for item in messages)
            selections[name][tokenizer.key] = values
            cold_plans[name][tokenizer.key] = plan_cold_session(
                messages, tokenizer, alias_profile
            )
            for item, selection in zip(messages, values, strict=True):
                exact_selected += (
                    decode_selected(selection.candidate.text, alias_profile) == item.message
                )
                deterministic_selected += (
                    select_prepared(item, tokenizer) == selection
                )
                if selection.candidate.tokens > selection.baseline.tokens:
                    raise RuntimeError("warm no-regression invariant failed")

    combined = tuple(item for messages in prepared.values() for item in messages)
    exact_existing = sum(
        decode_symbolic(item.symbolic_text) == item.message for item in combined
    )
    exact_optimized = sum(
        decode_optimized(item.optimized_text, alias_profile) == item.message
        for item in combined
    )
    deterministic_existing = sum(
        encode_symbolic(item.message) == item.symbolic_text for item in combined
    )
    deterministic_optimized = sum(
        encode_optimized(item.message, alias_profile) == item.optimized_text
        for item in combined
    )
    attempted, rejected = _corruption_trials(
        prepared, selections, tokenizer_profiles, alias_profile
    )
    study = Study(
        datasets,
        alias_profile,
        prepared,
        selections,
        cold_plans,
        tokenizer_profiles,
        exact_existing,
        exact_optimized,
        exact_selected,
        deterministic_existing,
        deterministic_optimized,
        deterministic_selected,
        attempted,
        rejected,
    )
    observed_snapshot = snapshot_sha256(study_snapshot(study))
    if EXPECTED_SNAPSHOT_SHA256 != "pending" and observed_snapshot != EXPECTED_SNAPSHOT_SHA256:
        raise RuntimeError("frozen v0.6 study snapshot changed")
    return study


def _aggregate_tokens(
    messages: Sequence[PreparedMessage],
    selections: Sequence[Selection],
    tokenizer: TokenizerProfile,
) -> dict[str, int]:
    return {
        "json": sum(tokenizer.count(item.raw_texts["json"]) for item in messages),
        "terse": sum(tokenizer.count(item.raw_texts["terse"]) for item in messages),
        "v04": sum(tokenizer.count(item.raw_texts["v04"]) for item in messages),
        "v05": sum(selection.baseline.tokens for selection in selections),
        "symbolic": sum(
            selection.candidates["symbolic"].tokens for selection in selections
        ),
        "optimized": sum(
            selection.candidates["optimized"].tokens for selection in selections
        ),
        "selected": sum(selection.candidate.tokens for selection in selections),
    }


def study_snapshot(study: Study) -> dict[str, Any]:
    token_totals: dict[str, dict[str, Mapping[str, int]]] = {}
    selected_digests: dict[str, dict[str, str]] = {}
    mode_counts: dict[str, dict[str, Mapping[str, int]]] = {}
    cold: dict[str, dict[str, Mapping[str, Any]]] = {}
    text_digests: dict[str, Mapping[str, str]] = {}
    for dataset, messages in study.prepared.items():
        token_totals[dataset] = {}
        selected_digests[dataset] = {}
        mode_counts[dataset] = {}
        cold[dataset] = {}
        text_digests[dataset] = {
            "symbolic": _sequence_digest(tuple(item.symbolic_text for item in messages)),
            "optimized": _sequence_digest(tuple(item.optimized_text for item in messages)),
        }
        for tokenizer in study.profiles:
            values = study.selections[dataset][tokenizer.key]
            token_totals[dataset][tokenizer.key] = _aggregate_tokens(
                messages, values, tokenizer
            )
            selected_digests[dataset][tokenizer.key] = _sequence_digest(
                tuple(item.candidate.text for item in values)
            )
            mode_counts[dataset][tokenizer.key] = dict(
                sorted(Counter(item.candidate.mode for item in values).items())
            )
            plan = study.cold_plans[dataset][tokenizer.key]
            cold[dataset][tokenizer.key] = {
                "baseline_total_tokens": plan.baseline_total_tokens,
                "selected_total_tokens": plan.selected.total_tokens,
                "cold_tokens": plan.selected.cold_tokens,
                "structured_bundle": plan.selected.structured_bundle,
                "symbolic_grammar": plan.selected.symbolic_grammar,
                "optimized_profile": plan.selected.optimized_profile,
                "mode_counts": dict(
                    sorted(Counter(item.mode for item in plan.selected.choices).items())
                ),
            }
    return {
        "profile_sha256": profile_sha256(study.alias_profile),
        "text_digests": text_digests,
        "token_totals": token_totals,
        "selected_digests": selected_digests,
        "mode_counts": mode_counts,
        "cold": cold,
        "exact": {
            "symbolic": study.exact_existing,
            "optimized": study.exact_optimized,
            "selected": study.exact_selected,
        },
        "deterministic": {
            "symbolic": study.deterministic_existing,
            "optimized": study.deterministic_optimized,
            "selected": study.deterministic_selected,
        },
        "corruptions_attempted": dict(sorted(study.corruptions_attempted.items())),
        "corruptions_rejected": dict(sorted(study.corruptions_rejected.items())),
    }


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


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


def measure_latency(study: Study, *, repeats: int) -> dict[str, Mapping[str, int]]:
    """Measure unequal-work reference paths without changing frozen metrics."""

    combined = tuple(
        message for messages in study.datasets.values() for message in messages
    )
    profile = study.alias_profile
    result: dict[str, Mapping[str, int]] = {}

    direct_paths: Mapping[
        str,
        tuple[
            Callable[[Mapping[str, Any]], str],
            Callable[[str], Mapping[str, Any]],
        ],
    ] = {
        "symbolic": (encode_symbolic, decode_symbolic),
        "optimized": (
            lambda message: encode_optimized(message, profile),
            lambda text: decode_optimized(text, profile),
        ),
    }
    for key, (encoder, decoder) in direct_paths.items():
        encoded = [encoder(message) for message in combined]
        result[key] = _time_codec(combined, encoded, encoder, decoder, repeats)

    for tokenizer in study.profiles:
        adaptive_encoder = lambda message, receiver=tokenizer: select_adaptive(
            prepare_adaptive(message), receiver
        ).candidate.text
        adaptive_encoded = [adaptive_encoder(message) for message in combined]
        result[f"v05:{tokenizer.key}"] = _time_codec(
            combined,
            adaptive_encoded,
            adaptive_encoder,
            decode_adaptive,
            repeats,
        )

        selected_encoder = lambda message, receiver=tokenizer: select_message(
            message, profile, receiver
        ).candidate.text
        selected_encoded = [selected_encoder(message) for message in combined]
        result[f"selected:{tokenizer.key}"] = _time_codec(
            combined,
            selected_encoded,
            selected_encoder,
            lambda text: decode_selected(text, profile),
            repeats,
        )
    return result


def _source_digest(name: str) -> str:
    path = Path(__file__).with_name(name)
    return sha256_file(path) if path.is_file() else "not-present"


def _percent_saved(candidate: int, baseline: int) -> str:
    if baseline == 0:
        return "+0.00%"
    return f"{100.0 * (1.0 - candidate / baseline):+.2f}%"


def _mode_counts(candidates: Sequence[Candidate]) -> str:
    counts = Counter(candidate.mode for candidate in candidates)
    return f"{counts['v05']}/{counts['symbolic']}/{counts['optimized']}"


def render_report(
    study: Study,
    latency: Mapping[str, Mapping[str, int]],
) -> str:
    """Render the complete English experimental report."""

    snapshot = study_snapshot(study)
    total_messages = sum(len(messages) for messages in study.datasets.values())
    receiver_pairs = total_messages * len(study.profiles)
    ood_savings = []
    for tokenizer in study.profiles:
        totals = snapshot["token_totals"]["out_of_domain"][tokenizer.key]
        ood_savings.append(100.0 * (1.0 - totals["selected"] / totals["v05"]))

    lines = [
        "# Generalization surface v0.6 experiment",
        "",
        "## Result",
        "",
        f"The receiver pre-input selector had **zero warm token regressions in {receiver_pairs:,}/{receiver_pairs:,} message/receiver pairs** against the complete v0.5 candidate. On the ten frozen out-of-domain messages, it reduced aggregate warm receiver tokens for every pinned tokenizer by **{min(ood_savings):.2f}% to {max(ood_savings):.2f}%**. Development and grouped-holdout warm totals were unchanged because the selector retained v0.5 for every message.",
        "",
        f"Exact semantic recovery passed for the existing readable surface in **{study.exact_existing}/{total_messages}** messages, for the train-only surface in **{study.exact_optimized}/{total_messages}**, and for selected texts in **{study.exact_selected:,}/{receiver_pairs:,}** pairs. Deterministic re-encoding/reselection passed in the same counts. Deterministic payload mutations were rejected in **{sum(study.corruptions_rejected.values()):,}/{sum(study.corruptions_attempted.values()):,}** trials.",
        "",
        "This is a serialization and receiver-token experiment. No language model, network service, or paid API was invoked. Model comprehension, sender generation, multi-turn task success, cross-vendor transfer, energy, adoption, and state-of-the-art standing remain unmeasured.",
        "",
        "## Frozen train-only optimization",
        "",
        "The new readable `@2` surface keeps the fixed 13-field symbolic layout and compact typed value grammar, then replaces frequent nested keys and string values with one-character aliases. The profile is derived only from the exact frozen development partition. Its objective is frequency multiplied by UTF-8 bytes saved; it does not inspect holdout token counts, out-of-domain content, checksum luck, or task answers. The implementation refuses any training sequence whose canonical digest is not the frozen development digest.",
        "",
        f"The frozen profile contains {len(study.alias_profile.key_aliases)} key aliases and {len(study.alias_profile.value_aliases)} value aliases. Its canonical capsule is {len(profile_capsule(study.alias_profile).encode('utf-8')):,} UTF-8 bytes and has SHA-256 `{profile_sha256(study.alias_profile)}`.",
        "",
        "Each `@2` text carries an 11-character Base64url BLAKE2s-64 checksum bound to the format domain, frozen profile digest, and complete payload. This detects accidental corruption but is not sender authentication. Decoding verifies the checksum before parsing, expands aliases, applies shared semantic validation, and requires byte-identical canonical re-encoding.",
        "",
        "## Warm exact token totals",
        "",
        "Counts are complete serialization texts without tokenizer special tokens. JSON and Controlled Terse English are raw token references and do not carry equivalent checksum framing; v0.4, v0.5, `@1`, `@2`, and selected surfaces retain their specified integrity framing.",
        "",
    ]
    for dataset, messages in study.prepared.items():
        lines.extend(
            [
                f"### {DATASET_LABELS[dataset].title()}",
                "",
                "| Receiver tokenizer | JSON raw | CTE raw | v0.4 | v0.5 | Existing readable | Train-only readable | Selected | vs v0.5 | Selected v0.5/existing/train-only |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for tokenizer in study.profiles:
            totals = snapshot["token_totals"][dataset][tokenizer.key]
            values = study.selections[dataset][tokenizer.key]
            lines.append(
                f"| {tokenizer.display_name} | {totals['json']:,} | {totals['terse']:,} | {totals['v04']:,} | {totals['v05']:,} | {totals['symbolic']:,} | {totals['optimized']:,} | {totals['selected']:,} | {_percent_saved(totals['selected'], totals['v05'])} | {_mode_counts(tuple(item.candidate for item in values))} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Per-message guard and unfavorable cases",
            "",
            "The receiver tokenizer is negotiated before input. For each message the selector exactly counts the byte-identical v0.5 result, existing readable text, and train-only readable text, then minimizes `(token count, fixed mode rank, text)`. v0.5 wins ties. This is an input-only cost decision, not a semantic or answer-quality oracle.",
            "",
            "| Dataset | Receiver tokenizer | Better | Tied | Worse | Tokens saved | Largest one-message saving |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for dataset in study.datasets:
        for tokenizer in study.profiles:
            values = study.selections[dataset][tokenizer.key]
            deltas = [item.baseline.tokens - item.candidate.tokens for item in values]
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {tokenizer.display_name} | {sum(delta > 0 for delta in deltas)} | {sum(delta == 0 for delta in deltas)} | {sum(delta < 0 for delta in deltas)} | {sum(deltas):,} | {max(deltas, default=0):,} |"
            )

    lines.extend(
        [
            "",
            "The token selector can choose a text with more UTF-8 bytes than v0.5 because bytes are not its objective. These cases are retained below.",
            "",
            "| Dataset | Receiver tokenizer | v0.5 bytes | Selected bytes | Messages with more bytes | Worst byte increase |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for dataset in study.datasets:
        for tokenizer in study.profiles:
            values = study.selections[dataset][tokenizer.key]
            baseline_bytes = sum(item.baseline.utf8_bytes for item in values)
            selected_bytes = sum(item.candidate.utf8_bytes for item in values)
            increases = [
                100.0 * (item.candidate.utf8_bytes / item.baseline.utf8_bytes - 1.0)
                for item in values
                if item.candidate.utf8_bytes > item.baseline.utf8_bytes
            ]
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {tokenizer.display_name} | {baseline_bytes:,} | {selected_bytes:,} | {len(increases)} | {max(increases, default=0.0):+.2f}% |"
            )

    lines.extend(
        [
            "",
            "## Cold known-session planning",
            "",
            "Before any message input, the planner enumerates all eight combinations of the structured bundle, existing grammar, and train-only grammar plus alias profile. A disabled artifact makes its dependent candidate ineligible. The complete v0.5 no-bundle and activated-bundle plans remain exact options, so the selected known-session total cannot regress. The profile is charged once and the two grammars are charged independently; no shared artifact is double-counted.",
            "",
            "| Dataset | Receiver tokenizer | v0.5 cold plan | Selected cold plan | Saving | New cold tokens | Structured/existing/train-only active | Cold-plan v0.5/existing/train-only |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for dataset in study.datasets:
        for tokenizer in study.profiles:
            plan = study.cold_plans[dataset][tokenizer.key]
            selected = plan.selected
            state = "/".join(
                "yes" if value else "no"
                for value in (
                    selected.structured_bundle,
                    selected.symbolic_grammar,
                    selected.optimized_profile,
                )
            )
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {tokenizer.display_name} | {plan.baseline_total_tokens:,} | {selected.total_tokens:,} | {_percent_saved(selected.total_tokens, plan.baseline_total_tokens)} | {selected.cold_tokens:,} | {state} | {_mode_counts(selected.choices)} |"
            )

    lines.extend(
        [
            "",
            "Warm out-of-domain improvements did **not** amortize the new grammar and profile on this ten-message session. Every out-of-domain cold plan therefore retained a v0.5-compatible state. Conversely, grouped holdout activated only the train-only profile for cl100k_base and o200k_base because avoiding the much larger structured bundle reduced total cold-session cost; Qwen and Mistral retained their v0.5 structured plans.",
            "",
            "### Cold artifact costs",
            "",
            "| Receiver tokenizer | Existing grammar | Train-only grammar | Alias profile | Structured bundle |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for tokenizer in study.profiles:
        artifacts = cold_artifact_metrics(tokenizer, study.alias_profile)
        lines.append(
            f"| {tokenizer.display_name} | {artifacts['symbolic_grammar'][0]:,} tokens / {artifacts['symbolic_grammar'][1]:,} bytes | {artifacts['optimized_grammar'][0]:,} / {artifacts['optimized_grammar'][1]:,} | {artifacts['optimized_profile'][0]:,} / {artifacts['optimized_profile'][1]:,} | {artifacts['structured_bundle'][0]:,} / {artifacts['structured_bundle'][1]:,} |"
        )

    lines.extend(
        [
            "",
            "## Reference implementation latency",
            "",
            "Times are per message on this machine. Direct rows encode one known readable representation. Fresh-selector rows rebuild all eligible representations and perform exact tokenizer counting; they intentionally expose unequal and substantial CPU work and are not protocol latency limits.",
            "",
            "| Path | Encode/select median | Encode/select p95 | Decode median | Decode p95 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for key, label in (
        ("symbolic", "direct existing readable"),
        ("optimized", "direct train-only readable"),
    ):
        item = latency[key]
        lines.append(
            f"| {label} | {item['encode_median_ns']/1000:.1f} µs | {item['encode_p95_ns']/1000:.1f} µs | {item['decode_median_ns']/1000:.1f} µs | {item['decode_p95_ns']/1000:.1f} µs |"
        )
    for tokenizer in study.profiles:
        for prefix, label in (("v05", "fresh v0.5"), ("selected", "fresh v0.6")):
            item = latency[f"{prefix}:{tokenizer.key}"]
            lines.append(
                f"| {label} for {tokenizer.display_name} | {item['encode_median_ns']/1000:.1f} µs | {item['encode_p95_ns']/1000:.1f} µs | {item['decode_median_ns']/1000:.1f} µs | {item['decode_p95_ns']/1000:.1f} µs |"
            )

    lines.extend(
        [
            "",
            "## Integrity and resource checks",
            "",
            f"- Existing-readable exact and deterministic checks: {study.exact_existing}/{total_messages} and {study.deterministic_existing}/{total_messages}.",
            f"- Train-only-readable exact and deterministic checks: {study.exact_optimized}/{total_messages} and {study.deterministic_optimized}/{total_messages}.",
            f"- Selected exact and deterministic checks: {study.exact_selected:,}/{receiver_pairs:,} and {study.deterministic_selected:,}/{receiver_pairs:,}.",
            f"- Corruption rejection: existing {study.corruptions_rejected['symbolic']}/{study.corruptions_attempted['symbolic']}; train-only {study.corruptions_rejected['optimized']}/{study.corruptions_attempted['optimized']}; selected {study.corruptions_rejected['selected']:,}/{study.corruptions_attempted['selected']:,}.",
            "- The decoder rejects wrong prefixes, malformed or mismatched checksums, trailing data, duplicate or colliding expanded keys, non-canonical encodings, invalid semantic types, oversized UTF-8 inputs, and excessive parser recursion.",
            "- Resource limits and shared semantic limits bound surface bytes, strings, collection items, and tree depth. The checksum is error detection only, not authentication, authorization, replay defense, or sandboxing.",
            "",
            "## Frozen inputs and reproducibility",
            "",
            f"- Format: `{FORMAT}`",
            f"- Development partition: {len(study.datasets['development'])} messages; SHA-256 `{EXPECTED_TRAIN_SHA256}`",
            f"- Grouped holdout: {len(study.datasets['grouped_holdout'])} messages; SHA-256 `{EXPECTED_HOLDOUT_SHA256}`",
            f"- Out of domain: {len(study.datasets['out_of_domain'])} messages; SHA-256 `{EXPECTED_OOD_SHA256}`",
            f"- Frozen structured codebook SHA-256: `{holdout_codebook().sha256}`",
            f"- Train-only alias profile SHA-256: `{profile_sha256(study.alias_profile)}`",
            f"- Complete v0.6 snapshot SHA-256: `{snapshot_sha256(snapshot)}`",
            f"- Tokenizer packages: `tiktoken=={TIKTOKEN_VERSION}`, `tokenizers=={TOKENIZERS_VERSION}`",
            "",
        ]
    )
    for tokenizer in study.profiles:
        lines.append(
            f"- `{tokenizer.key}`: {tokenizer.display_name}; {tokenizer.implementation}; vocabulary {tokenizer.vocabulary_size:,}; fingerprint `{tokenizer.fingerprint}`"
        )
    lines.extend(["", "Selected text-sequence SHA-256 values:", ""])
    for dataset in study.datasets:
        for tokenizer in study.profiles:
            lines.append(
                f"- {DATASET_LABELS[dataset]}, `{tokenizer.key}`: `{snapshot['selected_digests'][dataset][tokenizer.key]}`"
            )
    lines.extend(
        [
            "",
            "Source SHA-256 values:",
            "",
            f"- implementation and benchmark: `{_source_digest('urusilla_generalization_surface_v06.py')}`",
            f"- conformance tests: `{_source_digest('test_urusilla_generalization_surface_v06.py')}`",
            "",
            "Environment:",
            "",
            f"- Python: `{platform.python_version()}`",
            f"- Platform: `{platform.platform()}`",
            "",
            "Reproduce from the repository root with the pinned offline tokenizer assets:",
            "",
            "```bash",
            "PYTHONPATH=. python urusilla_generalization_surface_v06.py --benchmark --assets-dir /path/to/tokenizer_assets --repeats 1",
            "PYTHONPATH=. python -m unittest test_urusilla_generalization_surface_v06.py -v",
            "```",
            "",
            "## Limitations",
            "",
            "- Development results are in-sample. Grouped holdout shares a synthetic generator family, and out of domain has only ten repository-authored messages. The observed improvement is narrow evidence, not a general compression guarantee.",
            "- Receiver-token no-regression is guaranteed only when the receiver tokenizer is negotiated and exactly available before input. One broadcast string cannot generally be optimal for receivers with different tokenizers.",
            "- Counts exclude chat templates, BOS/EOS, surrounding prompts, transport framing, negotiation messages, and hosted billing rules. These can change deployed cost.",
            "- Cold planning is an offline optimum for a known sequence. Unknown-horizon streaming must remain on a previously cached profile or activate only after a conservative break-even rule; it cannot assume the reported session optimum.",
            "- Readable means syntactically inspectable after learning the short grammar. It is not evidence that a language model understands or can reliably generate the surface. The prior prompted pilot did not establish this claim, and no model was invoked here.",
            "- Raw JSON and Controlled Terse English references do not provide framing and integrity equivalent to the checksummed candidates, so their token totals are not protocol-equivalent competitors.",
            "- Checksums increase bytes and tokens. Signatures, encryption, authentication, negotiation failure, malicious ambiguity, and operational governance are outside this experiment.",
            "- Token reduction does not directly establish lower energy, latency, memory, monetary cost, or end-to-end application tokens. Exact counting and multi-candidate construction add CPU latency.",
            "- No external benchmark search or independent replication was performed. No state-of-the-art or task-success claim is made.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path(
            os.environ.get("URUSILLA_TOKENIZER_ASSETS", default_asset_root())
        ),
    )
    parser.add_argument(
        "--report", type=Path, default=Path(__file__).with_name(REPORT_NAME)
    )
    parser.add_argument("--repeats", type=int, default=1)
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
        print(
            json.dumps(
                {"snapshot": study_snapshot(study), "latency_ns": latency},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
