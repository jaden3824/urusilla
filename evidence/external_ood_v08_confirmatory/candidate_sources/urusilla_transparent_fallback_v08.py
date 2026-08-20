#!/usr/bin/env python3
"""Transparent fallback candidate for authenticated agent transports.

This v0.8 development experiment fixes a contract mismatch exposed by the
fresh external out-of-domain evaluation.  When an authenticated transport
already binds representation mode, record sequence, and the exact payload
bytes, the application delivers raw Controlled Terse English or canonical
JSON to the receiver without an application wrapper.  The delivered fallback
is therefore byte-for-byte identical to its plain baseline and has zero
receiver-token wrapper overhead.

A separate standalone text envelope supplies mode, sequence, and a truncated
HMAC when the transport does not provide that binding.  Its complete token and
byte overhead is retained.  Existing compact surfaces remain optional and may
be selected only when their complete token count is strictly below the best
eligible plain fallback.  Cold planning charges every optional artifact.

The 43-message external corpus was already revealed before this candidate was
designed.  It is used only as exploratory development evidence.  This module
does not make a generalization, model-comprehension, task-utility, energy,
adoption, or state-of-the-art claim.
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
import statistics
import time
from typing import Any, Callable, Mapping, Sequence

from urusilla_benchmark import corpus_digest, json_decode, json_encode
from urusilla import DecodeError, ValidationError, normalize_message
from urusilla_tokenizer_benchmark import (
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
)
from urusilla_terse_english_benchmark import (
    decode_terse_english,
    encode_terse_english,
)
from urusilla_token_surface_v04 import (
    decode_message as decode_v04,
    encode_message as encode_v04,
)
from urusilla_generalization_surface_v06 import (
    AliasProfile,
    build_datasets,
    cold_artifact_metrics,
    decode_optimized,
    derive_alias_profile,
    encode_optimized,
    profile_sha256,
)
from urusilla_token_surface_holdout import holdout_codebook


FORMAT = "urusilla-transparent-fallback-v0.8-experimental"
REPORT_NAME = "TRANSPARENT_FALLBACK_V08_RESULTS.md"
ROOT = Path(__file__).resolve().parent
EXTERNAL_CORPUS_PATH = (
    ROOT
    / "work"
    / "external_ood_evaluation"
    / "corpus-0a7b315a0b2e3a94bb98aa564d91dd8e117cca7c920c49f623349ba53db19b11.json"
)
EXPECTED_EXTERNAL_FILE_SHA256 = (
    "0a7b315a0b2e3a94bb98aa564d91dd8e117cca7c920c49f623349ba53db19b11"
)
EXPECTED_EXTERNAL_SEQUENCE_SHA256 = (
    "edbbfe4deb34913a8988ed5cd59d689b98d5769d34a8df2b483929fa17c0efa9"
)
EXPECTED_EXTERNAL_MESSAGES = 43
EXPECTED_ALIAS_PROFILE_SHA256 = (
    "f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d"
)
EXPECTED_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}
FROZEN_DEPENDENCY_SHA256 = {
    "urusilla_generalization_surface_v06.py": "85ab4676698acb2a887e31c297ed938d09c898a39d645b710a71149064fce753",
    "urusilla_terse_english_benchmark.py": "f528f68e22aa0c7b2fcc2ef10719648453aeda54c9c08df0e3986a7161e2c00e",
    "urusilla_token_surface_v04.py": "a102d7c990e031b008782976e57579b4050176fd631f7fad9aa7abdb5a691f05",
    "urusilla_benchmark.py": "b5e2885f7e17097643c1e93ba3326f285cd37aa8199cf1cc3b234227e515b5f8",
}

MODE_ORDER = ("terse", "json", "optimized", "v04")
PLAIN_MODES = ("terse", "json")
COMPACT_MODES = ("optimized", "v04")
MODE_BYTES = {"terse": 1, "json": 2, "optimized": 3, "v04": 4}
BYTE_MODES = {value: key for key, value in MODE_BYTES.items()}
MODE_CHARACTERS = {"terse": "E", "json": "J", "optimized": "O", "v04": "V"}
CHARACTER_MODES = {value: key for key, value in MODE_CHARACTERS.items()}

BOUND_DOMAIN = b"UrusillaTransparentFallback-v0.8-bound\x00"
STANDALONE_DOMAIN = b"UrusillaTransparentFallback-v0.8-standalone\x00"
TEST_KEY = hashlib.sha256(
    b"public deterministic v0.8 integrity fixture; never a deployment secret"
).digest()
SEQUENCE_BYTES = 8
AUTH_TAG_BYTES = 16
BOUND_METADATA_BYTES = 1 + SEQUENCE_BYTES + AUTH_TAG_BYTES
STANDALONE_PREFIX = "T8"
STANDALONE_SEQUENCE_CHARACTERS = SEQUENCE_BYTES * 2
STANDALONE_TAG_CHARACTERS = 22
STANDALONE_HEADER_CHARACTERS = (
    len(STANDALONE_PREFIX)
    + 1
    + STANDALONE_SEQUENCE_CHARACTERS
    + STANDALONE_TAG_CHARACTERS
    + 1
)

SELECTION_CONTRACT = {
    "format": FORMAT,
    "status": "post-reveal exploratory development candidate",
    "external_corpus_file_sha256": EXPECTED_EXTERNAL_FILE_SHA256,
    "external_corpus_sequence_sha256": EXPECTED_EXTERNAL_SEQUENCE_SHA256,
    "plain_modes": [
        {
            "mode": "terse",
            "payload": "byte-identical raw Controlled Terse English baseline",
            "session_artifact_bytes": 0,
        },
        {
            "mode": "json",
            "payload": "byte-identical sorted minified canonical JSON baseline",
            "session_artifact_bytes": 0,
        },
    ],
    "compact_modes": [
        {
            "mode": "optimized",
            "identity": EXPECTED_ALIAS_PROFILE_SHA256,
            "artifacts": ["optimized_grammar", "optimized_profile"],
        },
        {
            "mode": "v04",
            "identity": "frozen grouped-holdout token surface",
            "artifacts": ["structured_bundle"],
        },
    ],
    "warm_rule": (
        "Choose the exact minimum complete receiver-token count. A compact mode "
        "is eligible only when it is strictly smaller than the best plain mode. "
        "Ties use the fixed mode order terse, json, optimized, v04."
    ),
    "cold_rule": (
        "Enumerate all four activation states for structured and optimized "
        "artifacts, charge exact tokenizer-specific artifact cost once, and "
        "choose the exact minimum total. Ties prefer fewer cold tokens and no "
        "activation."
    ),
    "bound_transport": {
        "model_input": "payload only",
        "metadata": "one mode byte, eight sequence bytes, sixteen HMAC bytes",
        "metadata_bytes_per_record": BOUND_METADATA_BYTES,
        "tag": "HMAC-SHA-256 truncated to 128 bits over mode, sequence, and payload",
    },
    "standalone_transport": {
        "model_input": "complete text envelope",
        "shape": "T8 + mode + 16 lowercase sequence hex + 22 Base64url tag + colon + payload",
        "header_characters_per_record": STANDALONE_HEADER_CHARACTERS,
        "tag": "HMAC-SHA-256 truncated to 128 bits over mode, sequence, and payload",
    },
    "claim_boundary": (
        "Serialization-only exploratory development evidence; no fresh "
        "confirmatory corpus, model, task, energy, adoption, or SOTA claim."
    ),
}
EXPECTED_SELECTION_CONTRACT_SHA256 = (
    "fcb90039b2a7e193e3b274b6a4cefcb7cf851b116e397bcb721e0b268c5c36b0"
)
EXPECTED_SNAPSHOT_SHA256 = "a8996a65dde500bdc9928f5462574dc39c3edc591de6dd42919d523b50d3bea9"


@dataclass(frozen=True)
class PreparedMessage:
    message: Mapping[str, Any]
    texts: Mapping[str, str]


@dataclass(frozen=True)
class Candidate:
    mode: str
    payload: str
    receiver_text: str
    tokens: int
    utf8_bytes: int
    artifact_names: tuple[str, ...]


@dataclass(frozen=True)
class Selection:
    candidate: Candidate
    plain_best: Candidate
    candidates: Mapping[str, Candidate]


@dataclass(frozen=True)
class ColdOption:
    structured: bool
    optimized: bool
    cold_tokens: int
    cold_bytes: int
    message_tokens: int
    total_tokens: int
    choices: tuple[Candidate, ...]


@dataclass(frozen=True)
class ColdPlan:
    selected: ColdOption
    options: tuple[ColdOption, ...]
    plain_total_tokens: int


@dataclass(frozen=True)
class Study:
    messages: tuple[dict[str, Any], ...]
    prepared: tuple[PreparedMessage, ...]
    alias_profile: AliasProfile
    profiles: tuple[TokenizerProfile, ...]
    selections: Mapping[str, Mapping[str, tuple[Selection, ...]]]
    cold_plans: Mapping[str, Mapping[str, ColdPlan]]
    exact_candidates: int
    deterministic_candidates: int
    exact_selected: Mapping[str, int]
    deterministic_selected: Mapping[str, int]
    plain_delivery_identity: int
    plain_delivery_identity_total: int
    integrity_attempted: Mapping[str, int]
    integrity_rejected: Mapping[str, int]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def selection_contract_sha256() -> str:
    return hashlib.sha256(_canonical_json(SELECTION_CONTRACT).encode("utf-8")).hexdigest()


def _sequence_digest(texts: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for text in texts:
        raw = text.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def verify_frozen_inputs(profiles: Sequence[TokenizerProfile]) -> None:
    for name, expected in FROZEN_DEPENDENCY_SHA256.items():
        actual = _sha256_file(ROOT / name)
        if actual != expected:
            raise RuntimeError(f"frozen dependency changed: {name}")
    observed_keys = tuple(profile.key for profile in profiles)
    if observed_keys != tuple(EXPECTED_TOKENIZER_FINGERPRINTS):
        raise RuntimeError("the four pinned tokenizers are required in frozen order")
    for profile in profiles:
        if profile.fingerprint != EXPECTED_TOKENIZER_FINGERPRINTS[profile.key]:
            raise RuntimeError(f"pinned tokenizer changed: {profile.key}")
    observed_contract = selection_contract_sha256()
    if (
        EXPECTED_SELECTION_CONTRACT_SHA256 != "pending"
        and observed_contract != EXPECTED_SELECTION_CONTRACT_SHA256
    ):
        raise RuntimeError("frozen v0.8 selection contract changed")


def load_external_corpus() -> tuple[dict[str, Any], ...]:
    if not EXTERNAL_CORPUS_PATH.is_file():
        raise RuntimeError(f"missing frozen external corpus: {EXTERNAL_CORPUS_PATH}")
    if _sha256_file(EXTERNAL_CORPUS_PATH) != EXPECTED_EXTERNAL_FILE_SHA256:
        raise RuntimeError("external corpus file digest changed")
    try:
        raw = json.loads(EXTERNAL_CORPUS_PATH.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("external corpus is not valid UTF-8 JSON") from exc
    if not isinstance(raw, list) or len(raw) != EXPECTED_EXTERNAL_MESSAGES:
        raise RuntimeError("external corpus message count changed")
    messages = tuple(normalize_message(item) for item in raw)
    if corpus_digest(messages) != EXPECTED_EXTERNAL_SEQUENCE_SHA256:
        raise RuntimeError("external corpus canonical sequence changed")
    return messages


def build_alias_profile() -> AliasProfile:
    development = build_datasets()["development"]
    profile = derive_alias_profile(development)
    if profile_sha256(profile) != EXPECTED_ALIAS_PROFILE_SHA256:
        raise RuntimeError("frozen train-only alias profile changed")
    return profile


def prepare_message(message: Mapping[str, Any], alias_profile: AliasProfile) -> PreparedMessage:
    canonical = normalize_message(message)
    texts = {
        "terse": encode_terse_english(canonical),
        "json": json_encode(canonical).decode("utf-8"),
        "optimized": encode_optimized(canonical, alias_profile),
        "v04": encode_v04(canonical, holdout_codebook()),
    }
    return PreparedMessage(canonical, texts)


def decode_payload(mode: str, payload: str, alias_profile: AliasProfile) -> dict[str, Any]:
    if mode == "terse":
        return decode_terse_english(payload)
    if mode == "json":
        message = json_decode(payload.encode("utf-8"))
        if json_encode(message).decode("utf-8") != payload:
            raise DecodeError("JSON fallback is not canonical")
        return message
    if mode == "optimized":
        return decode_optimized(payload, alias_profile)
    if mode == "v04":
        return decode_v04(payload, holdout_codebook())
    raise DecodeError("unknown transparent fallback mode")


def _mode_and_sequence(mode: str, sequence: int) -> tuple[bytes, bytes]:
    if mode not in MODE_BYTES:
        raise ValidationError("unknown transparent fallback mode")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or not 0 <= sequence < 2**64:
        raise ValidationError("record sequence must be an unsigned 64-bit integer")
    return bytes((MODE_BYTES[mode],)), sequence.to_bytes(SEQUENCE_BYTES, "big")


def _tag(domain: bytes, key: bytes, mode: str, sequence: int, payload: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 16:
        raise ValidationError("integrity key must contain at least 16 bytes")
    mode_bytes, sequence_bytes = _mode_and_sequence(mode, sequence)
    return hmac.new(
        key,
        domain + mode_bytes + sequence_bytes + payload,
        hashlib.sha256,
    ).digest()[:AUTH_TAG_BYTES]


def encode_bound_record(mode: str, sequence: int, payload: str, key: bytes = TEST_KEY) -> bytes:
    if not isinstance(payload, str) or not payload:
        raise ValidationError("bound payload must be non-empty text")
    mode_bytes, sequence_bytes = _mode_and_sequence(mode, sequence)
    payload_bytes = payload.encode("utf-8")
    tag = _tag(BOUND_DOMAIN, key, mode, sequence, payload_bytes)
    return mode_bytes + sequence_bytes + payload_bytes + tag


def open_bound_record(
    record: bytes,
    alias_profile: AliasProfile,
    *,
    expected_sequence: int,
    key: bytes = TEST_KEY,
) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(record, bytes) or len(record) <= BOUND_METADATA_BYTES:
        raise DecodeError("bound record is truncated")
    mode = BYTE_MODES.get(record[0])
    if mode is None:
        raise DecodeError("bound record mode is unknown")
    sequence = int.from_bytes(record[1 : 1 + SEQUENCE_BYTES], "big")
    if sequence != expected_sequence:
        raise DecodeError("bound record sequence mismatch")
    payload_bytes = record[1 + SEQUENCE_BYTES : -AUTH_TAG_BYTES]
    supplied = record[-AUTH_TAG_BYTES:]
    expected = _tag(BOUND_DOMAIN, key, mode, sequence, payload_bytes)
    if not hmac.compare_digest(supplied, expected):
        raise DecodeError("bound record authentication failed")
    try:
        payload = payload_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DecodeError("bound payload is not UTF-8") from exc
    return mode, payload, decode_payload(mode, payload, alias_profile)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    try:
        return base64.b64decode(
            text + "=" * (-len(text) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise DecodeError("standalone tag is not canonical Base64url") from exc


def encode_standalone(
    mode: str,
    sequence: int,
    payload: str,
    key: bytes = TEST_KEY,
) -> str:
    if not isinstance(payload, str) or not payload:
        raise ValidationError("standalone payload must be non-empty text")
    _mode_and_sequence(mode, sequence)
    tag = _tag(STANDALONE_DOMAIN, key, mode, sequence, payload.encode("utf-8"))
    encoded_tag = _b64url(tag)
    if len(encoded_tag) != STANDALONE_TAG_CHARACTERS:
        raise RuntimeError("standalone tag width changed")
    return (
        STANDALONE_PREFIX
        + MODE_CHARACTERS[mode]
        + f"{sequence:016x}"
        + encoded_tag
        + ":"
        + payload
    )


def open_standalone(
    text: str,
    alias_profile: AliasProfile,
    *,
    expected_sequence: int,
    key: bytes = TEST_KEY,
) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(text, str) or len(text) <= STANDALONE_HEADER_CHARACTERS:
        raise DecodeError("standalone envelope is truncated")
    if not text.startswith(STANDALONE_PREFIX):
        raise DecodeError("standalone envelope prefix is unknown")
    mode = CHARACTER_MODES.get(text[len(STANDALONE_PREFIX)])
    if mode is None:
        raise DecodeError("standalone envelope mode is unknown")
    sequence_start = len(STANDALONE_PREFIX) + 1
    sequence_end = sequence_start + STANDALONE_SEQUENCE_CHARACTERS
    sequence_text = text[sequence_start:sequence_end]
    if len(sequence_text) != STANDALONE_SEQUENCE_CHARACTERS or any(
        character not in "0123456789abcdef" for character in sequence_text
    ):
        raise DecodeError("standalone sequence is not canonical lowercase hex")
    sequence = int(sequence_text, 16)
    if sequence != expected_sequence:
        raise DecodeError("standalone record sequence mismatch")
    tag_end = sequence_end + STANDALONE_TAG_CHARACTERS
    tag_text = text[sequence_end:tag_end]
    if len(tag_text) != STANDALONE_TAG_CHARACTERS or text[tag_end] != ":":
        raise DecodeError("standalone envelope header is malformed")
    supplied = _b64url_decode(tag_text)
    if len(supplied) != AUTH_TAG_BYTES or _b64url(supplied) != tag_text:
        raise DecodeError("standalone tag is not canonical")
    payload = text[tag_end + 1 :]
    if not payload:
        raise DecodeError("standalone payload is empty")
    expected = _tag(
        STANDALONE_DOMAIN,
        key,
        mode,
        sequence,
        payload.encode("utf-8"),
    )
    if not hmac.compare_digest(supplied, expected):
        raise DecodeError("standalone envelope authentication failed")
    return mode, payload, decode_payload(mode, payload, alias_profile)


def _candidate(
    prepared: PreparedMessage,
    tokenizer: TokenizerProfile,
    mode: str,
    contract: str,
    sequence: int,
) -> Candidate:
    payload = prepared.texts[mode]
    if contract == "bound":
        receiver_text = payload
    elif contract == "standalone":
        receiver_text = encode_standalone(mode, sequence, payload)
    else:
        raise ValueError("contract must be bound or standalone")
    artifacts = {
        "terse": (),
        "json": (),
        "optimized": ("optimized_grammar", "optimized_profile"),
        "v04": ("structured_bundle",),
    }[mode]
    return Candidate(
        mode=mode,
        payload=payload,
        receiver_text=receiver_text,
        tokens=tokenizer.count(receiver_text),
        utf8_bytes=len(receiver_text.encode("utf-8")),
        artifact_names=artifacts,
    )


def select_prepared(
    prepared: PreparedMessage,
    tokenizer: TokenizerProfile,
    *,
    contract: str,
    sequence: int,
    allow_structured: bool = True,
    allow_optimized: bool = True,
) -> Selection:
    allowed = ["terse", "json"]
    if allow_optimized:
        allowed.append("optimized")
    if allow_structured:
        allowed.append("v04")
    candidates = {
        mode: _candidate(prepared, tokenizer, mode, contract, sequence)
        for mode in allowed
    }
    plain_best = min(
        (candidates[mode] for mode in PLAIN_MODES),
        key=lambda item: (item.tokens, MODE_ORDER.index(item.mode), item.receiver_text),
    )
    strict_compact_winners = [
        candidates[mode]
        for mode in COMPACT_MODES
        if mode in candidates and candidates[mode].tokens < plain_best.tokens
    ]
    selected = min(
        [plain_best, *strict_compact_winners],
        key=lambda item: (item.tokens, MODE_ORDER.index(item.mode), item.receiver_text),
    )
    all_minimum = min(item.tokens for item in candidates.values())
    if selected.tokens != all_minimum:
        raise RuntimeError("transparent selector did not choose the exact token minimum")
    if selected.mode in COMPACT_MODES and selected.tokens >= plain_best.tokens:
        raise RuntimeError("compact mode was selected without a strict token win")
    return Selection(selected, plain_best, candidates)


def artifact_metrics(
    tokenizer: TokenizerProfile,
    alias_profile: AliasProfile,
) -> dict[str, tuple[int, int]]:
    original = cold_artifact_metrics(tokenizer, alias_profile)
    return {
        "structured_bundle": original["structured_bundle"],
        "optimized_grammar": original["optimized_grammar"],
        "optimized_profile": original["optimized_profile"],
        "selection_contract": (
            tokenizer.count(_canonical_json(SELECTION_CONTRACT)),
            len(_canonical_json(SELECTION_CONTRACT).encode("utf-8")),
        ),
    }


def plan_cold_session(
    prepared: Sequence[PreparedMessage],
    tokenizer: TokenizerProfile,
    alias_profile: AliasProfile,
    *,
    contract: str,
) -> ColdPlan:
    artifacts = artifact_metrics(tokenizer, alias_profile)
    options: list[ColdOption] = []
    for structured in (False, True):
        for optimized in (False, True):
            choices = tuple(
                select_prepared(
                    item,
                    tokenizer,
                    contract=contract,
                    sequence=index,
                    allow_structured=structured,
                    allow_optimized=optimized,
                ).candidate
                for index, item in enumerate(prepared, 1)
            )
            cold_tokens = (
                (artifacts["structured_bundle"][0] if structured else 0)
                + (artifacts["optimized_grammar"][0] if optimized else 0)
                + (artifacts["optimized_profile"][0] if optimized else 0)
            )
            cold_bytes = (
                (artifacts["structured_bundle"][1] if structured else 0)
                + (artifacts["optimized_grammar"][1] if optimized else 0)
                + (artifacts["optimized_profile"][1] if optimized else 0)
            )
            message_tokens = sum(choice.tokens for choice in choices)
            options.append(
                ColdOption(
                    structured,
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
            item.structured,
            item.optimized,
        )
    )
    plain_total = next(
        item.total_tokens
        for item in options
        if not item.structured and not item.optimized
    )
    if options[0].total_tokens > plain_total:
        raise RuntimeError("cold transparent plan regressed against plain fallback")
    return ColdPlan(options[0], tuple(options), plain_total)


def _mutate_text_character(text: str, position: int) -> str:
    replacement = "X" if text[position] != "X" else "Y"
    return text[:position] + replacement + text[position + 1 :]


def _integrity_trials(
    study_profiles: Sequence[TokenizerProfile],
    prepared: Sequence[PreparedMessage],
    alias_profile: AliasProfile,
) -> tuple[dict[str, int], dict[str, int]]:
    attempted = Counter()
    rejected = Counter()
    for tokenizer in study_profiles:
        for index, item in enumerate(prepared, 1):
            bound_selection = select_prepared(
                item, tokenizer, contract="bound", sequence=index
            ).candidate
            record = encode_bound_record(
                bound_selection.mode, index, bound_selection.payload
            )
            payload_start = 1 + SEQUENCE_BYTES
            payload_end = len(record) - AUTH_TAG_BYTES
            payload_offset = int.from_bytes(
                hashlib.sha256(
                    f"{FORMAT}|bound|{tokenizer.key}|{index}".encode()
                ).digest()[:8],
                "big",
            ) % (payload_end - payload_start)
            bound_mutations = (
                bytes((255,)) + record[1:],
                record[:1] + bytes((record[1] ^ 1,)) + record[2:],
                record[: payload_start + payload_offset]
                + bytes((record[payload_start + payload_offset] ^ 1,))
                + record[payload_start + payload_offset + 1 :],
                record[:-1] + bytes((record[-1] ^ 1,)),
            )
            for mutated in bound_mutations:
                attempted["bound"] += 1
                try:
                    open_bound_record(
                        mutated, alias_profile, expected_sequence=index
                    )
                except (DecodeError, ValidationError):
                    rejected["bound"] += 1
            attempted["bound"] += 1
            try:
                open_bound_record(
                    record, alias_profile, expected_sequence=index + 1
                )
            except (DecodeError, ValidationError):
                rejected["bound"] += 1

            standalone_selection = select_prepared(
                item, tokenizer, contract="standalone", sequence=index
            ).candidate
            envelope = standalone_selection.receiver_text
            payload_position = STANDALONE_HEADER_CHARACTERS + (
                int.from_bytes(
                    hashlib.sha256(
                        f"{FORMAT}|standalone|{tokenizer.key}|{index}".encode()
                    ).digest()[:8],
                    "big",
                )
                % (len(envelope) - STANDALONE_HEADER_CHARACTERS)
            )
            sequence_position = len(STANDALONE_PREFIX) + 1
            tag_position = sequence_position + STANDALONE_SEQUENCE_CHARACTERS
            standalone_mutations = (
                envelope[:2] + "X" + envelope[3:],
                _mutate_text_character(envelope, sequence_position),
                _mutate_text_character(envelope, payload_position),
                _mutate_text_character(envelope, tag_position),
            )
            for mutated in standalone_mutations:
                attempted["standalone"] += 1
                try:
                    open_standalone(
                        mutated, alias_profile, expected_sequence=index
                    )
                except (DecodeError, ValidationError):
                    rejected["standalone"] += 1
            attempted["standalone"] += 1
            try:
                open_standalone(
                    envelope, alias_profile, expected_sequence=index + 1
                )
            except (DecodeError, ValidationError):
                rejected["standalone"] += 1
    return dict(attempted), dict(rejected)


def collect_study(profiles: Sequence[TokenizerProfile]) -> Study:
    tokenizer_profiles = tuple(profiles)
    verify_frozen_inputs(tokenizer_profiles)
    messages = load_external_corpus()
    alias_profile = build_alias_profile()
    prepared = tuple(prepare_message(message, alias_profile) for message in messages)

    exact_candidates = deterministic_candidates = 0
    for item in prepared:
        for mode in MODE_ORDER:
            text = item.texts[mode]
            exact_candidates += decode_payload(mode, text, alias_profile) == item.message
            deterministic_candidates += (
                prepare_message(item.message, alias_profile).texts[mode] == text
            )

    selections: dict[str, dict[str, tuple[Selection, ...]]] = {
        "bound": {},
        "standalone": {},
    }
    cold_plans: dict[str, dict[str, ColdPlan]] = {
        "bound": {},
        "standalone": {},
    }
    exact_selected = Counter()
    deterministic_selected = Counter()
    for contract in ("bound", "standalone"):
        for tokenizer in tokenizer_profiles:
            values = tuple(
                select_prepared(
                    item,
                    tokenizer,
                    contract=contract,
                    sequence=index,
                )
                for index, item in enumerate(prepared, 1)
            )
            selections[contract][tokenizer.key] = values
            cold_plans[contract][tokenizer.key] = plan_cold_session(
                prepared,
                tokenizer,
                alias_profile,
                contract=contract,
            )
            for index, (item, selection) in enumerate(
                zip(prepared, values, strict=True), 1
            ):
                if contract == "bound":
                    encoded = encode_bound_record(
                        selection.candidate.mode,
                        index,
                        selection.candidate.payload,
                    )
                    _, _, decoded = open_bound_record(
                        encoded, alias_profile, expected_sequence=index
                    )
                    repeated = encode_bound_record(
                        selection.candidate.mode,
                        index,
                        selection.candidate.payload,
                    )
                else:
                    encoded = selection.candidate.receiver_text
                    _, _, decoded = open_standalone(
                        encoded, alias_profile, expected_sequence=index
                    )
                    repeated = encode_standalone(
                        selection.candidate.mode,
                        index,
                        selection.candidate.payload,
                    )
                exact_selected[contract] += decoded == item.message
                deterministic_selected[contract] += encoded == repeated

    identity = identity_total = 0
    for index, item in enumerate(prepared, 1):
        for mode in PLAIN_MODES:
            baseline = item.texts[mode]
            record = encode_bound_record(mode, index, baseline)
            opened_mode, delivered, decoded = open_bound_record(
                record, alias_profile, expected_sequence=index
            )
            identity_total += 1
            identity += (
                opened_mode == mode
                and delivered.encode("utf-8") == baseline.encode("utf-8")
                and decoded == item.message
            )

    attempted, rejected = _integrity_trials(
        tokenizer_profiles, prepared, alias_profile
    )
    study = Study(
        messages,
        prepared,
        alias_profile,
        tokenizer_profiles,
        selections,
        cold_plans,
        exact_candidates,
        deterministic_candidates,
        dict(exact_selected),
        dict(deterministic_selected),
        identity,
        identity_total,
        attempted,
        rejected,
    )
    observed_snapshot = snapshot_sha256(study_snapshot(study))
    if EXPECTED_SNAPSHOT_SHA256 != "pending" and observed_snapshot != EXPECTED_SNAPSHOT_SHA256:
        raise RuntimeError("frozen v0.8 exploratory snapshot changed")
    return study


def _token_row(
    study: Study,
    tokenizer: TokenizerProfile,
) -> dict[str, Any]:
    bound = study.selections["bound"][tokenizer.key]
    standalone = study.selections["standalone"][tokenizer.key]
    raw_plain = sum(item.plain_best.tokens for item in bound)
    bound_warm = sum(item.candidate.tokens for item in bound)
    standalone_plain = sum(item.plain_best.tokens for item in standalone)
    standalone_warm = sum(item.candidate.tokens for item in standalone)
    bound_cold = study.cold_plans["bound"][tokenizer.key].selected
    standalone_cold = study.cold_plans["standalone"][tokenizer.key].selected
    return {
        "raw_plain": raw_plain,
        "bound_warm": bound_warm,
        "bound_warm_regret_tokens": bound_warm - raw_plain,
        "bound_cold": bound_cold.total_tokens,
        "bound_cold_regret_tokens": bound_cold.total_tokens - raw_plain,
        "standalone_matched_plain": standalone_plain,
        "standalone_warm": standalone_warm,
        "standalone_matched_regret_tokens": standalone_warm - standalone_plain,
        "standalone_cold": standalone_cold.total_tokens,
        "standalone_cold_matched_regret_tokens": (
            standalone_cold.total_tokens - standalone_plain
        ),
        "standalone_warm_excess_over_raw_plain": standalone_warm - raw_plain,
    }


def study_snapshot(study: Study) -> dict[str, Any]:
    token_rows = {
        tokenizer.key: _token_row(study, tokenizer)
        for tokenizer in study.profiles
    }
    mode_counts: dict[str, dict[str, Mapping[str, int]]] = {}
    selected_digests: dict[str, dict[str, str]] = {}
    byte_rows: dict[str, dict[str, int]] = {}
    cold: dict[str, dict[str, Mapping[str, Any]]] = {}
    for contract in ("bound", "standalone"):
        mode_counts[contract] = {}
        selected_digests[contract] = {}
        byte_rows[contract] = {}
        cold[contract] = {}
        for tokenizer in study.profiles:
            selections = study.selections[contract][tokenizer.key]
            mode_counts[contract][tokenizer.key] = dict(
                sorted(Counter(item.candidate.mode for item in selections).items())
            )
            selected_digests[contract][tokenizer.key] = _sequence_digest(
                tuple(item.candidate.receiver_text for item in selections)
            )
            payload_bytes = sum(
                len(item.candidate.payload.encode("utf-8")) for item in selections
            )
            receiver_bytes = sum(item.candidate.utf8_bytes for item in selections)
            byte_rows[contract][tokenizer.key] = {
                "payload_bytes": payload_bytes,
                "receiver_text_bytes": receiver_bytes,
                "transport_metadata_bytes": (
                    len(selections) * BOUND_METADATA_BYTES
                    if contract == "bound"
                    else 0
                ),
                "complete_record_bytes": (
                    payload_bytes + len(selections) * BOUND_METADATA_BYTES
                    if contract == "bound"
                    else receiver_bytes
                ),
            }
            plan = study.cold_plans[contract][tokenizer.key].selected
            cold[contract][tokenizer.key] = {
                "total_tokens": plan.total_tokens,
                "cold_tokens": plan.cold_tokens,
                "cold_bytes": plan.cold_bytes,
                "structured": plan.structured,
                "optimized": plan.optimized,
                "mode_counts": dict(
                    sorted(Counter(item.mode for item in plan.choices).items())
                ),
            }
    artifacts = {
        tokenizer.key: {
            name: {"tokens": values[0], "bytes": values[1]}
            for name, values in artifact_metrics(tokenizer, study.alias_profile).items()
        }
        for tokenizer in study.profiles
    }
    return {
        "format": FORMAT,
        "evidence_status": "post-reveal exploratory development",
        "external_corpus": {
            "messages": len(study.messages),
            "file_sha256": EXPECTED_EXTERNAL_FILE_SHA256,
            "sequence_sha256": EXPECTED_EXTERNAL_SEQUENCE_SHA256,
        },
        "selection_contract_sha256": selection_contract_sha256(),
        "alias_profile_sha256": profile_sha256(study.alias_profile),
        "token_rows": token_rows,
        "mode_counts": mode_counts,
        "selected_digests": selected_digests,
        "byte_rows": byte_rows,
        "cold": cold,
        "artifact_costs": artifacts,
        "exact": {
            "all_candidate_payloads": study.exact_candidates,
            "bound_selected": study.exact_selected["bound"],
            "standalone_selected": study.exact_selected["standalone"],
        },
        "deterministic": {
            "all_candidate_payloads": study.deterministic_candidates,
            "bound_selected": study.deterministic_selected["bound"],
            "standalone_selected": study.deterministic_selected["standalone"],
        },
        "plain_delivery_identity": {
            "passed": study.plain_delivery_identity,
            "attempted": study.plain_delivery_identity_total,
        },
        "integrity_attempted": dict(sorted(study.integrity_attempted.items())),
        "integrity_rejected": dict(sorted(study.integrity_rejected.items())),
        "record_overhead": {
            "bound_metadata_bytes_per_record": BOUND_METADATA_BYTES,
            "standalone_header_characters_per_record": STANDALONE_HEADER_CHARACTERS,
        },
    }


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _time_path(
    messages: Sequence[Mapping[str, Any]],
    encoded: Sequence[Any],
    encoder: Callable[[int, Mapping[str, Any]], Any],
    decoder: Callable[[int, Any], Mapping[str, Any]],
    repeats: int,
) -> dict[str, int]:
    encode_samples: list[int] = []
    decode_samples: list[int] = []
    gc_enabled = gc.isenabled()
    try:
        gc.disable()
        for _ in range(1):
            for index, message in enumerate(messages, 1):
                encoder(index, message)
            for index, value in enumerate(encoded, 1):
                decoder(index, value)
        for _ in range(repeats):
            for index, message in enumerate(messages, 1):
                start = time.perf_counter_ns()
                encoder(index, message)
                encode_samples.append(time.perf_counter_ns() - start)
            for index, value in enumerate(encoded, 1):
                start = time.perf_counter_ns()
                decoder(index, value)
                decode_samples.append(time.perf_counter_ns() - start)
    finally:
        if gc_enabled:
            gc.enable()
    return {
        "encode_p50_ns": int(statistics.median(encode_samples)),
        "encode_p95_ns": _nearest(encode_samples, 0.95),
        "decode_p50_ns": int(statistics.median(decode_samples)),
        "decode_p95_ns": _nearest(decode_samples, 0.95),
    }


def measure_latency(study: Study, repeats: int = 5) -> dict[str, Mapping[str, int]]:
    if repeats < 1:
        raise ValueError("latency repeats must be positive")
    result: dict[str, Mapping[str, int]] = {}
    terse_texts = tuple(item.texts["terse"] for item in study.prepared)
    result["plain_terse"] = _time_path(
        study.messages,
        terse_texts,
        lambda _index, message: encode_terse_english(message),
        lambda _index, text: decode_terse_english(text),
        repeats,
    )
    for tokenizer in study.profiles:
        for contract in ("bound", "standalone"):
            selections = study.selections[contract][tokenizer.key]
            if contract == "bound":
                encoded = tuple(
                    encode_bound_record(
                        selection.candidate.mode,
                        index,
                        selection.candidate.payload,
                    )
                    for index, selection in enumerate(selections, 1)
                )

                def encoder(
                    index: int,
                    message: Mapping[str, Any],
                    *,
                    selected_tokenizer: TokenizerProfile = tokenizer,
                ) -> bytes:
                    prepared = prepare_message(message, study.alias_profile)
                    selection = select_prepared(
                        prepared,
                        selected_tokenizer,
                        contract="bound",
                        sequence=index,
                    ).candidate
                    return encode_bound_record(selection.mode, index, selection.payload)

                def decoder(index: int, record: bytes) -> Mapping[str, Any]:
                    return open_bound_record(
                        record,
                        study.alias_profile,
                        expected_sequence=index,
                    )[2]

            else:
                encoded = tuple(
                    selection.candidate.receiver_text for selection in selections
                )

                def encoder(
                    index: int,
                    message: Mapping[str, Any],
                    *,
                    selected_tokenizer: TokenizerProfile = tokenizer,
                ) -> str:
                    prepared = prepare_message(message, study.alias_profile)
                    return select_prepared(
                        prepared,
                        selected_tokenizer,
                        contract="standalone",
                        sequence=index,
                    ).candidate.receiver_text

                def decoder(index: int, text: str) -> Mapping[str, Any]:
                    return open_standalone(
                        text,
                        study.alias_profile,
                        expected_sequence=index,
                    )[2]

            result[f"{contract}:{tokenizer.key}"] = _time_path(
                study.messages,
                encoded,
                encoder,
                decoder,
                repeats,
            )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, default=default_asset_root())
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--skip-latency", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profiles = load_tokenizer_profiles(args.assets_dir)
    study = collect_study(profiles)
    snapshot = study_snapshot(study)
    output: dict[str, Any] = {
        "selection_contract_sha256": selection_contract_sha256(),
        "snapshot_sha256": snapshot_sha256(snapshot),
        "snapshot": snapshot,
    }
    if not args.skip_latency:
        output["latency_ns"] = measure_latency(study, args.repeats)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
