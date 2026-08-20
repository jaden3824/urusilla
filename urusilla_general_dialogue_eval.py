#!/usr/bin/env python3
"""Frozen broad-dialogue lossless carrier and SGD oracle evaluation.

This module deliberately verifies the source freeze, corpus manifest, corpus
sequence, and predeclared hypotheses before loading any tokenizer package.
The primary lane transports arbitrary turn text losslessly and always retains
byte-identical raw UTF-8 as the token no-regret fallback.  The secondary SGD
lane is an oracle prompt-size upper bound; it is neither lossless prose nor a
deployment or model-success result.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import copy
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import re
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import zlib


ROOT = Path(__file__).resolve().parent
WORK_ROOT = ROOT / "work" / "general_dialogue"
CONTRACT_PATH = ROOT / "urusilla_general_dialogue_contract.json"
RESULTS_PATH = ROOT / "urusilla_general_dialogue_results.json"
REPORT_PATH = ROOT / "URUSILLA_GENERAL_DIALOGUE_RESULTS.md"
TOKENIZER_ASSET_ROOT = ROOT / "work" / "tokenizer_assets"

FORMAT = "urusilla-general-dialogue-results-v1"
EXPECTED_CONTRACT_SHA256 = (
    "1cf2d1c9810ac5b94bc0adf15d2251bae30b1b1d8b36fa161a51e1bbe0f5b1c1"
)
EXPECTED_SOURCE_FREEZE_SHA256 = (
    "888bbdd680a22faa2e30e457d5559ad4042184ec2e0e5b7f7b7832ef6ebd2921"
)
EXPECTED_CORPUS_MANIFEST_SHA256 = (
    "6fba633e286527303afd180b0221362365a20efd9325686631df022fc6cf9fec"
)
EXPECTED_CORPUS_SHA256 = (
    "3bede9398786dcb7de72a5bf2648105c62ba3b0f9339d7c86b774f937b104854"
)
EXPECTED_SEQUENCE_SHA256 = (
    "349e57a679815aa343815117ac8ed0e753f516871152c46a38fa31484fcd82bd"
)
EXPECTED_RECORDS = 256
EXPECTED_TURNS = 2542

EXPECTED_HYPOTHESES = {
    "h1_lossless_no_regret": (
        "raw-text fallback produces no positive receiver-token regret per turn"
    ),
    "h2_general_compact_value": (
        "strict compact choices cover at least 10 percent of turns and reduce "
        "aggregate receiver tokens by at least 5 percent in every source family"
    ),
    "h3_repeated_context_value": (
        "multi-turn reference or delta mode reduces aggregate receiver tokens by "
        "at least 20 percent in both task-oriented dialogue families"
    ),
    "h4_end_to_end_gate": (
        "a later model trial must preserve task success within a one-percentage-point "
        "non-inferiority margin and reduce total task tokens by at least 20 percent "
        "before a general-use claim"
    ),
}

EXPECTED_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}
OPEN_TOKENIZERS = {
    "qwen2_5_7b_instruct": "Qwen2.5-7B-Instruct tokenizer",
    "mistral_7b_instruct_v03": "Mistral-7B-Instruct-v0.3 tokenizer",
}
REQUIRED_VERSIONS = {
    "tiktoken": "0.11.0",
    "tokenizers": "0.21.4",
    "Brotli": "1.2.0",
    "zstandard": "0.25.0",
}
EXPECTED_ZLIB_VERSION = "1.2.12"
TIKTOKEN_ASSET_SPECS = {
    "cl100k_base": {
        "path": TOKENIZER_ASSET_ROOT / "cl100k_base" / "cl100k_base.tiktoken",
        "bytes": 1_681_126,
        "sha256": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
        "url": "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
    },
    "o200k_base": {
        "path": TOKENIZER_ASSET_ROOT / "o200k_base" / "o200k_base.tiktoken",
        "bytes": 3_613_922,
        "sha256": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
        "url": "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
    },
}
CL100K_PATTERN = (
    r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+|"
    r" ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"
)
O200K_PATTERN = "|".join(
    [
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"\p{N}{1,3}",
        r" ?[^\s\p{L}\p{N}]+[\r\n/]*",
        r"\s*[\r\n]+",
        r"\s+(?!\S)",
        r"\s+",
    ]
)
TIKTOKEN_CONSTRUCTORS = {
    "cl100k_base": {
        "pattern": CL100K_PATTERN,
        "special_tokens": {
            "<|endoftext|>": 100257,
            "<|fim_prefix|>": 100258,
            "<|fim_middle|>": 100259,
            "<|fim_suffix|>": 100260,
            "<|endofprompt|>": 100276,
        },
    },
    "o200k_base": {
        "pattern": O200K_PATTERN,
        "special_tokens": {
            "<|endoftext|>": 199999,
            "<|endofprompt|>": 200018,
        },
    },
}

FAMILY_ORDER = (
    "taskmaster_1",
    "schema_guided_dialogue",
    "databricks_dolly_15k",
    "openassistant_oasst1",
)
TASK_FAMILIES = ("taskmaster_1", "schema_guided_dialogue")
MODE_ORDER = (
    "raw",
    "raw_checked",
    "deflate64",
    "brotli64",
    "zstd64",
    "history_deflate64",
)
COMPACT_MODES = frozenset(
    {"deflate64", "brotli64", "zstd64", "history_deflate64"}
)
MODE_CHAR = {
    "raw_checked": "R",
    "deflate64": "D",
    "brotli64": "B",
    "zstd64": "Z",
    "history_deflate64": "H",
}
CHAR_MODE = {value: key for key, value in MODE_CHAR.items()}
ENVELOPE_RE = re.compile(
    r"\A~U1([RDBZH])([0-9a-f]{8})([0-9a-f]{16}):([A-Za-z0-9_-]*)\Z"
)
MAX_TEXT_BYTES = 16 * 1024 * 1024
HISTORY_DICTIONARY_BYTES = 32_768
EXTERNAL_PROFILE_ID = "urn:urusilla:external-profile:raw-dialogue:0.1"
SGD_INSTRUCTION = (
    "Predict the next assistant dialogue actions. Return only ordered ACT(slot) "
    "labels."
)


class EvaluationError(RuntimeError):
    """Raised when a frozen input, dependency, or exactness gate fails."""


@dataclass(frozen=True)
class TokenizerProfile:
    key: str
    display_name: str
    implementation: str
    vocabulary_size: int
    fingerprint: str
    count: Callable[[str], int]


@dataclass(frozen=True)
class VerifiedInputs:
    contract: Mapping[str, Any]
    contract_bytes: bytes
    source_freeze: Mapping[str, Any]
    manifest: Mapping[str, Any]
    records: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class TurnSurface:
    corpus_id: str
    family: str
    role: str
    turn_index: int
    raw_text: str
    history: bytes
    surfaces: Mapping[str, str]
    external_profile: str


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def sequence_sha256(records: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        raw = canonical_bytes(record)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot load frozen JSON: {path}") from exc


def verify_frozen_inputs(work_root: Path = WORK_ROOT) -> VerifiedInputs:
    """Verify every frozen boundary before tokenizer or codec dependencies load."""

    contract_bytes = CONTRACT_PATH.read_bytes()
    if sha256_bytes(contract_bytes) != EXPECTED_CONTRACT_SHA256:
        raise EvaluationError("evaluation contract digest changed")
    contract = json.loads(contract_bytes)

    source_path = work_root / "source_freeze.json"
    manifest_path = work_root / "corpus_manifest.json"
    corpus_path = work_root / "corpus.jsonl"
    if sha256_file(source_path) != EXPECTED_SOURCE_FREEZE_SHA256:
        raise EvaluationError("source freeze digest mismatch")
    if sha256_file(manifest_path) != EXPECTED_CORPUS_MANIFEST_SHA256:
        raise EvaluationError("corpus manifest digest mismatch")
    if sha256_file(corpus_path) != EXPECTED_CORPUS_SHA256:
        raise EvaluationError("corpus file digest mismatch")

    source_freeze = _load_json(source_path)
    manifest = _load_json(manifest_path)
    for key in ("measurement_started", "project_codec_imported", "tokenizer_loaded"):
        if source_freeze.get(key) is not False:
            raise EvaluationError(f"source freeze flag is not false: {key}")
        if manifest.get(key) is not False:
            raise EvaluationError(f"corpus manifest flag is not false: {key}")
    if source_freeze.get("premeasurement_hypotheses") != EXPECTED_HYPOTHESES:
        raise EvaluationError("premeasurement hypotheses changed")
    if contract.get("predeclared_hypotheses") != EXPECTED_HYPOTHESES:
        raise EvaluationError("contract hypotheses do not match source freeze")

    contract_corpus = contract.get("corpus", {})
    required_contract_values = {
        "file_sha256": EXPECTED_CORPUS_SHA256,
        "manifest_sha256": EXPECTED_CORPUS_MANIFEST_SHA256,
        "records": EXPECTED_RECORDS,
        "sequence_sha256": EXPECTED_SEQUENCE_SHA256,
        "source_freeze_sha256": EXPECTED_SOURCE_FREEZE_SHA256,
        "turns": EXPECTED_TURNS,
    }
    if contract_corpus != required_contract_values:
        raise EvaluationError("contract corpus identity changed")
    contract_assets = contract.get("tokenizer_asset_files", {})
    for key, spec in TIKTOKEN_ASSET_SPECS.items():
        declared = contract_assets.get(key, {})
        if (
            declared.get("bytes") != spec["bytes"]
            or declared.get("sha256") != spec["sha256"]
            or declared.get("acquisition_url") != spec["url"]
        ):
            raise EvaluationError(f"contract tokenizer asset identity changed: {key}")

    source_dir = work_root / "sources"
    for source in source_freeze.get("source_families", []):
        path = source_dir / source["local_name"]
        if path.stat().st_size != source["expected_size"]:
            raise EvaluationError(f"source byte size mismatch: {source['key']}")
        if sha256_file(path) != source["sha256"]:
            raise EvaluationError(f"source digest mismatch: {source['key']}")

    records: list[Mapping[str, Any]] = []
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise EvaluationError(f"invalid corpus JSONL line {line_number}") from exc
    if len(records) != EXPECTED_RECORDS:
        raise EvaluationError("frozen record count changed")
    if sequence_sha256(records) != EXPECTED_SEQUENCE_SHA256:
        raise EvaluationError("frozen record sequence changed")
    turns_by_family: Counter[str] = Counter()
    records_by_family: Counter[str] = Counter()
    ids: set[str] = set()
    total_turns = 0
    for record in records:
        corpus_id = record.get("corpus_id")
        family = record.get("source_family")
        turns = record.get("turns")
        if not isinstance(corpus_id, str) or corpus_id in ids:
            raise EvaluationError("invalid or duplicate corpus_id")
        if family not in FAMILY_ORDER or not isinstance(turns, list):
            raise EvaluationError(f"invalid record envelope: {corpus_id}")
        ids.add(corpus_id)
        records_by_family[family] += 1
        turns_by_family[family] += len(turns)
        total_turns += len(turns)
        for turn in turns:
            if turn.get("role") not in {"user", "assistant"}:
                raise EvaluationError(f"invalid role in {corpus_id}")
            if not isinstance(turn.get("text"), str):
                raise EvaluationError(f"invalid turn text in {corpus_id}")
    if total_turns != EXPECTED_TURNS:
        raise EvaluationError("frozen turn count changed")
    if dict(sorted(records_by_family.items())) != manifest["records_by_family"]:
        raise EvaluationError("records-by-family mismatch")
    if dict(sorted(turns_by_family.items())) != manifest["turns_by_family"]:
        raise EvaluationError("turns-by-family mismatch")
    if manifest.get("sequence_sha256") != EXPECTED_SEQUENCE_SHA256:
        raise EvaluationError("manifest sequence digest mismatch")
    return VerifiedInputs(
        contract=contract,
        contract_bytes=contract_bytes,
        source_freeze=source_freeze,
        manifest=manifest,
        records=tuple(records),
    )


def _require_distribution(distribution: str, expected: str) -> str:
    try:
        actual = metadata.version(distribution)
    except metadata.PackageNotFoundError as exc:
        raise EvaluationError(
            f"missing frozen dependency: install {distribution}=={expected}"
        ) from exc
    if actual != expected:
        raise EvaluationError(
            f"{distribution} version mismatch: expected {expected}, got {actual}"
        )
    return actual


def _require_zlib_versions() -> None:
    if zlib.ZLIB_VERSION != EXPECTED_ZLIB_VERSION:
        raise EvaluationError(
            f"zlib compile version mismatch: expected {EXPECTED_ZLIB_VERSION}, "
            f"got {zlib.ZLIB_VERSION}"
        )
    if zlib.ZLIB_RUNTIME_VERSION != EXPECTED_ZLIB_VERSION:
        raise EvaluationError(
            f"zlib runtime version mismatch: expected {EXPECTED_ZLIB_VERSION}, "
            f"got {zlib.ZLIB_RUNTIME_VERSION}"
        )


def _load_tiktoken_ranks(path: Path, expected_size: int, expected_sha256: str) -> dict[bytes, int]:
    if not path.is_file():
        raise EvaluationError(
            f"missing local tokenizer asset: {path}; acquire and verify it before measurement"
        )
    if path.stat().st_size != expected_size:
        raise EvaluationError(f"tokenizer asset byte size mismatch: {path}")
    if sha256_file(path) != expected_sha256:
        raise EvaluationError(f"tokenizer asset digest mismatch: {path}")
    ranks: dict[bytes, int] = {}
    seen_ranks: set[int] = set()
    for line_number, line in enumerate(path.read_bytes().splitlines(), 1):
        try:
            encoded_token, rank_text = line.split()
            token = base64.b64decode(encoded_token, validate=True)
            rank = int(rank_text)
        except (ValueError, TypeError) as exc:
            raise EvaluationError(
                f"invalid local tiktoken asset line {line_number}: {path}"
            ) from exc
        if token in ranks or rank in seen_ranks or rank < 0:
            raise EvaluationError(f"duplicate or invalid rank in tokenizer asset: {path}")
        ranks[token] = rank
        seen_ranks.add(rank)
    if seen_ranks != set(range(len(seen_ranks))):
        raise EvaluationError(f"non-contiguous ranks in tokenizer asset: {path}")
    return ranks


def _tiktoken_fingerprint(encoding: Any) -> str:
    digest = hashlib.sha256()
    pattern = encoding._pat_str.encode("utf-8")
    digest.update(len(pattern).to_bytes(8, "big"))
    digest.update(pattern)
    for token, rank in sorted(
        encoding._mergeable_ranks.items(), key=lambda item: (item[1], item[0])
    ):
        digest.update(len(token).to_bytes(4, "big"))
        digest.update(token)
        digest.update(rank.to_bytes(8, "big"))
    for token, rank in sorted(encoding._special_tokens.items()):
        raw = token.encode("utf-8")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
        digest.update(rank.to_bytes(8, "big"))
    return digest.hexdigest()


def load_pinned_tokenizers(asset_root: Path = TOKENIZER_ASSET_ROOT) -> tuple[TokenizerProfile, ...]:
    """Load only explicit local assets after ``verify_frozen_inputs`` returns.

    This function contains no URL fetch, cache lookup, or ``get_encoding`` call.
    Missing local files fail closed with separate acquisition required.
    """

    _require_distribution("tiktoken", REQUIRED_VERSIONS["tiktoken"])
    _require_distribution("tokenizers", REQUIRED_VERSIONS["tokenizers"])
    try:
        import tiktoken  # type: ignore[import-not-found]
        from tokenizers import Tokenizer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise EvaluationError("pinned tokenizer packages are not importable") from exc

    profiles: list[TokenizerProfile] = []
    for key in ("cl100k_base", "o200k_base"):
        spec = TIKTOKEN_ASSET_SPECS[key]
        path = asset_root / key / f"{key}.tiktoken"
        ranks = _load_tiktoken_ranks(path, int(spec["bytes"]), str(spec["sha256"]))
        constructor = TIKTOKEN_CONSTRUCTORS[key]
        encoding = tiktoken.Encoding(
            name=key,
            pat_str=str(constructor["pattern"]),
            mergeable_ranks=ranks,
            special_tokens=dict(constructor["special_tokens"]),
        )
        fingerprint = _tiktoken_fingerprint(encoding)
        if fingerprint != EXPECTED_TOKENIZER_FINGERPRINTS[key]:
            raise EvaluationError(f"tokenizer fingerprint mismatch: {key}")

        def count_tiktoken(text: str, *, _encoding: Any = encoding) -> int:
            return len(
                _encoding.encode(text, allowed_special=set(), disallowed_special=())
            )

        profiles.append(
            TokenizerProfile(
                key=key,
                display_name=key,
                implementation=f"tiktoken {REQUIRED_VERSIONS['tiktoken']}",
                vocabulary_size=encoding.n_vocab,
                fingerprint=fingerprint,
                count=count_tiktoken,
            )
        )

    for key, display_name in OPEN_TOKENIZERS.items():
        path = asset_root / key / "tokenizer.json"
        if not path.is_file():
            raise EvaluationError(f"missing frozen tokenizer asset: {path}")
        fingerprint = sha256_file(path)
        if fingerprint != EXPECTED_TOKENIZER_FINGERPRINTS[key]:
            raise EvaluationError(f"tokenizer asset digest mismatch: {key}")
        tokenizer = Tokenizer.from_file(str(path))

        def count_open(text: str, *, _tokenizer: Any = tokenizer) -> int:
            return len(_tokenizer.encode(text, add_special_tokens=False).ids)

        profiles.append(
            TokenizerProfile(
                key=key,
                display_name=display_name,
                implementation=f"tokenizers {REQUIRED_VERSIONS['tokenizers']}",
                vocabulary_size=tokenizer.get_vocab_size(with_added_tokens=True),
                fingerprint=fingerprint,
                count=count_open,
            )
        )
    observed = tuple(profile.key for profile in profiles)
    if observed != tuple(EXPECTED_TOKENIZER_FINGERPRINTS):
        raise EvaluationError(f"unexpected tokenizer order: {observed}")
    return tuple(profiles)


def _load_strong_compressors() -> tuple[Any, Any]:
    _require_distribution("Brotli", REQUIRED_VERSIONS["Brotli"])
    _require_distribution("zstandard", REQUIRED_VERSIONS["zstandard"])
    try:
        import brotli  # type: ignore[import-not-found]
        import zstandard  # type: ignore[import-not-found]
    except ImportError as exc:
        raise EvaluationError("mandatory strong compressor is not importable") from exc
    return brotli, zstandard


def _history_dictionary(history: bytes) -> bytes:
    return history[-HISTORY_DICTIONARY_BYTES:]


def append_history(history: bytes, raw: bytes) -> bytes:
    return history + len(raw).to_bytes(8, "big") + raw


def _raw_deflate(raw: bytes, dictionary: bytes | None = None) -> bytes:
    kwargs: dict[str, Any] = {}
    if dictionary:
        kwargs["zdict"] = dictionary
    compressor = zlib.compressobj(
        level=9,
        method=zlib.DEFLATED,
        wbits=-15,
        memLevel=9,
        strategy=zlib.Z_DEFAULT_STRATEGY,
        **kwargs,
    )
    return compressor.compress(raw) + compressor.flush(zlib.Z_FINISH)


def _raw_inflate(payload: bytes, expected_size: int, dictionary: bytes | None = None) -> bytes:
    kwargs: dict[str, Any] = {}
    if dictionary:
        kwargs["zdict"] = dictionary
    decoder = zlib.decompressobj(wbits=-15, **kwargs)
    raw = decoder.decompress(payload, expected_size + 1)
    if decoder.unconsumed_tail or len(raw) > expected_size:
        raise EvaluationError("DEFLATE output exceeds declared length")
    raw += decoder.flush(expected_size + 1 - len(raw))
    if not decoder.eof or decoder.unused_data or len(raw) != expected_size:
        raise EvaluationError("invalid or non-canonical DEFLATE payload")
    return raw


def _unpadded_base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_base64url(text: str) -> bytes:
    try:
        raw = base64.b64decode(
            text + "=" * (-len(text) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise EvaluationError("invalid Base64url payload") from exc
    if _unpadded_base64url(raw) != text:
        raise EvaluationError("non-canonical Base64url payload")
    return raw


def encode_carrier(
    mode: str,
    text: str,
    history: bytes,
    brotli: Any,
    zstandard: Any,
) -> str:
    if mode == "raw":
        return text
    if mode not in MODE_CHAR:
        raise EvaluationError(f"unknown carrier mode: {mode}")
    raw = text.encode("utf-8")
    if len(raw) > MAX_TEXT_BYTES:
        raise EvaluationError("turn exceeds carrier byte limit")
    if mode == "raw_checked":
        payload = raw
    elif mode == "deflate64":
        payload = _raw_deflate(raw)
    elif mode == "history_deflate64":
        dictionary = _history_dictionary(history)
        if not dictionary:
            raise EvaluationError("history mode requires at least one prior turn")
        payload = _raw_deflate(raw, dictionary)
    elif mode == "brotli64":
        payload = brotli.compress(
            raw, mode=brotli.MODE_GENERIC, quality=11, lgwin=22
        )
    elif mode == "zstd64":
        payload = zstandard.ZstdCompressor(
            level=19,
            threads=0,
            write_checksum=True,
            write_content_size=True,
        ).compress(raw)
    else:  # pragma: no cover - protected by MODE_CHAR
        raise EvaluationError(f"unimplemented carrier mode: {mode}")
    return (
        f"~U1{MODE_CHAR[mode]}{len(raw):08x}{sha256_bytes(raw)[:16]}:"
        f"{_unpadded_base64url(payload)}"
    )


def decode_carrier(
    mode: str,
    carrier: str,
    history: bytes,
    brotli: Any,
    zstandard: Any,
) -> str:
    if mode == "raw":
        return carrier
    match = ENVELOPE_RE.fullmatch(carrier)
    if match is None:
        raise EvaluationError("invalid carrier envelope")
    mode_char, size_hex, digest_prefix, payload_text = match.groups()
    if CHAR_MODE[mode_char] != mode:
        raise EvaluationError("carrier mode mismatch")
    expected_size = int(size_hex, 16)
    if expected_size > MAX_TEXT_BYTES:
        raise EvaluationError("declared turn size exceeds limit")
    payload = _decode_base64url(payload_text)
    if mode == "raw_checked":
        raw = payload
    elif mode == "deflate64":
        raw = _raw_inflate(payload, expected_size)
    elif mode == "history_deflate64":
        dictionary = _history_dictionary(history)
        if not dictionary:
            raise EvaluationError("history mode requires at least one prior turn")
        raw = _raw_inflate(payload, expected_size, dictionary)
    elif mode == "brotli64":
        raw = brotli.decompress(payload)
    elif mode == "zstd64":
        raw = zstandard.ZstdDecompressor().decompress(
            payload, max_output_size=expected_size + 1
        )
    else:  # pragma: no cover - protected by CHAR_MODE
        raise EvaluationError(f"unimplemented carrier mode: {mode}")
    if len(raw) != expected_size or sha256_bytes(raw)[:16] != digest_prefix:
        raise EvaluationError("carrier length or digest mismatch")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EvaluationError("carrier payload is not valid UTF-8") from exc


def external_profile_text(
    *, corpus_id: str, role: str, turn_index: int, text: str
) -> str:
    value = {
        "profile": EXTERNAL_PROFILE_ID,
        "role": role,
        "session": corpus_id,
        "text": text,
        "turn": turn_index,
    }
    return canonical_bytes(value).decode("utf-8")


def build_turn_surfaces(
    records: Sequence[Mapping[str, Any]], brotli: Any, zstandard: Any
) -> tuple[tuple[TurnSurface, ...], Mapping[str, list[float]], Mapping[str, list[float]]]:
    surfaces: list[TurnSurface] = []
    encode_latencies: dict[str, list[float]] = defaultdict(list)
    decode_latencies: dict[str, list[float]] = defaultdict(list)
    for record in records:
        history = b""
        corpus_id = str(record["corpus_id"])
        family = str(record["source_family"])
        for turn_index, turn in enumerate(record["turns"]):
            text = str(turn["text"])
            available_modes = MODE_ORDER if history else MODE_ORDER[:-1]
            candidates: dict[str, str] = {}
            for mode in available_modes:
                started = time.perf_counter_ns()
                carrier = encode_carrier(mode, text, history, brotli, zstandard)
                encode_latencies[mode].append((time.perf_counter_ns() - started) / 1000)
                started = time.perf_counter_ns()
                recovered = decode_carrier(mode, carrier, history, brotli, zstandard)
                decode_latencies[mode].append((time.perf_counter_ns() - started) / 1000)
                if recovered != text:
                    raise EvaluationError("candidate did not recover exact turn text")
                if encode_carrier(mode, recovered, history, brotli, zstandard) != carrier:
                    raise EvaluationError("candidate deterministic re-encoding changed")
                candidates[mode] = carrier
            external = external_profile_text(
                corpus_id=corpus_id,
                role=str(turn["role"]),
                turn_index=turn_index,
                text=text,
            )
            parsed_external = json.loads(external)
            if canonical_bytes(parsed_external).decode("utf-8") != external:
                raise EvaluationError("external profile is not canonical")
            if (
                parsed_external["profile"] != EXTERNAL_PROFILE_ID
                or parsed_external["role"] != turn["role"]
                or parsed_external["session"] != corpus_id
                or parsed_external["turn"] != turn_index
                or parsed_external["text"] != text
            ):
                raise EvaluationError("external profile changed a field")
            surfaces.append(
                TurnSurface(
                    corpus_id=corpus_id,
                    family=family,
                    role=str(turn["role"]),
                    turn_index=turn_index,
                    raw_text=text,
                    history=history,
                    surfaces=candidates,
                    external_profile=external,
                )
            )
            history = append_history(history, text.encode("utf-8"))
    if len(surfaces) != EXPECTED_TURNS:
        raise EvaluationError("surface turn count changed")
    return tuple(surfaces), encode_latencies, decode_latencies


def _percent_saved(baseline: int, candidate: int) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else float("-inf")
    return (baseline - candidate) * 100.0 / baseline


def _percent_over(baseline: int, candidate: int) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else float("inf")
    return (candidate - baseline) * 100.0 / baseline


def _quantile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _latency_summary(values: Sequence[float]) -> Mapping[str, float | int]:
    return {
        "samples": len(values),
        "p50_us": round(statistics.median(values), 3) if values else 0.0,
        "p95_us": round(_quantile(values, 0.95), 3),
    }


def _select_mode(token_counts: Mapping[str, int], surfaces: Mapping[str, str]) -> str:
    raw_tokens = token_counts["raw"]
    compact = [mode for mode in MODE_ORDER[1:] if mode in surfaces]
    best = min(
        compact,
        key=lambda mode: (
            token_counts[mode],
            len(surfaces[mode].encode("utf-8")),
            MODE_ORDER.index(mode),
        ),
    )
    return best if token_counts[best] < raw_tokens else "raw"


def _select_history(token_counts: Mapping[str, int]) -> str:
    if (
        "history_deflate64" in token_counts
        and token_counts["history_deflate64"] < token_counts["raw"]
    ):
        return "history_deflate64"
    return "raw"


def measure_lossless_lane(
    inputs: VerifiedInputs,
    profiles: Sequence[TokenizerProfile],
    brotli: Any,
    zstandard: Any,
) -> Mapping[str, Any]:
    surfaces, encode_latencies, decode_latencies = build_turn_surfaces(
        inputs.records, brotli, zstandard
    )
    by_family_rows = {
        family: tuple(row for row in surfaces if row.family == family)
        for family in FAMILY_ORDER
    }
    contract_text = inputs.contract_bytes.decode("utf-8")
    by_tokenizer: dict[str, Any] = {}
    selection_latencies: dict[str, list[float]] = defaultdict(list)
    selected_decode_latencies: dict[str, list[float]] = defaultdict(list)
    total_positive_regret = 0
    total_selected_exact = 0
    total_selected_deterministic = 0

    for profile in profiles:
        artifact_tokens = profile.count(contract_text)
        family_results: dict[str, Any] = {}
        for family in FAMILY_ORDER:
            rows = by_family_rows[family]
            raw_tokens = 0
            raw_bytes = 0
            warm_tokens = 0
            warm_bytes = 0
            external_tokens = 0
            external_bytes = 0
            checked_raw_tokens = 0
            checked_raw_bytes = 0
            mode_counts: Counter[str] = Counter()
            candidate_tokens: Counter[str] = Counter()
            candidate_bytes: Counter[str] = Counter()
            history_tokens = 0
            history_mode_counts: Counter[str] = Counter()
            positive_regret_turns = 0
            for row in rows:
                started = time.perf_counter_ns()
                token_counts = {
                    mode: profile.count(surface)
                    for mode, surface in row.surfaces.items()
                }
                selected_mode = _select_mode(token_counts, row.surfaces)
                selection_latencies[profile.key].append(
                    (time.perf_counter_ns() - started) / 1000
                )
                selected_surface = row.surfaces[selected_mode]
                raw_count = token_counts["raw"]
                selected_count = token_counts[selected_mode]
                raw_tokens += raw_count
                raw_bytes += len(row.raw_text.encode("utf-8"))
                warm_tokens += selected_count
                warm_bytes += len(selected_surface.encode("utf-8"))
                external_tokens += profile.count(row.external_profile)
                external_bytes += len(row.external_profile.encode("utf-8"))
                checked_raw_tokens += token_counts["raw_checked"]
                checked_raw_bytes += len(row.surfaces["raw_checked"].encode("utf-8"))
                mode_counts[selected_mode] += 1
                for mode, count in token_counts.items():
                    candidate_tokens[mode] += count
                    candidate_bytes[mode] += len(row.surfaces[mode].encode("utf-8"))
                history_mode = _select_history(token_counts)
                history_tokens += token_counts[history_mode]
                history_mode_counts[history_mode] += 1
                if selected_count > raw_count:
                    positive_regret_turns += 1
                started = time.perf_counter_ns()
                recovered = decode_carrier(
                    selected_mode,
                    selected_surface,
                    row.history,
                    brotli,
                    zstandard,
                )
                selected_decode_latencies[profile.key].append(
                    (time.perf_counter_ns() - started) / 1000
                )
                if recovered != row.raw_text:
                    raise EvaluationError("selected carrier did not recover exact text")
                total_selected_exact += 1
                if (
                    encode_carrier(
                        selected_mode,
                        recovered,
                        row.history,
                        brotli,
                        zstandard,
                    )
                    != selected_surface
                ):
                    raise EvaluationError("selected carrier deterministic check failed")
                total_selected_deterministic += 1
            compact_selected = sum(mode_counts[mode] for mode in COMPACT_MODES)
            compact_coverage = compact_selected * 100.0 / len(rows)
            warm_saving = _percent_saved(raw_tokens, warm_tokens)
            cold_activated = warm_tokens + artifact_tokens < raw_tokens
            cold_tokens = warm_tokens + artifact_tokens if cold_activated else raw_tokens
            cold_bytes = (
                warm_bytes + len(inputs.contract_bytes) if cold_activated else raw_bytes
            )
            h2_pass = compact_coverage >= 10.0 and warm_saving >= 5.0
            history_saving = _percent_saved(raw_tokens, history_tokens)
            family_results[family] = {
                "turns": len(rows),
                "raw_tokens": raw_tokens,
                "raw_utf8_bytes": raw_bytes,
                "integrity_matched_raw_tokens": checked_raw_tokens,
                "integrity_matched_raw_bytes": checked_raw_bytes,
                "warm_selected_tokens": warm_tokens,
                "warm_selected_utf8_bytes": warm_bytes,
                "warm_carrier_token_saving_pct": round(warm_saving, 6),
                "warm_wire_byte_saving_pct": round(
                    _percent_saved(raw_bytes, warm_bytes), 6
                ),
                "compact_selected": compact_selected,
                "compact_coverage_pct": round(compact_coverage, 6),
                "mode_counts": dict(sorted(mode_counts.items())),
                "candidate_tokens": dict(sorted(candidate_tokens.items())),
                "candidate_utf8_bytes": dict(sorted(candidate_bytes.items())),
                "positive_regret_turns": positive_regret_turns,
                "cold_artifact_tokens": artifact_tokens,
                "cold_artifact_utf8_bytes": len(inputs.contract_bytes),
                "cold_activated": cold_activated,
                "cold_total_tokens": cold_tokens,
                "cold_total_utf8_bytes": cold_bytes,
                "cold_carrier_token_saving_pct": round(
                    _percent_saved(raw_tokens, cold_tokens), 6
                ),
                "post_decode_model_input_tokens": raw_tokens,
                "post_decode_model_input_saving_pct": 0.0,
                "external_profile_tokens": external_tokens,
                "external_profile_utf8_bytes": external_bytes,
                "external_profile_token_overhead_pct": round(
                    _percent_over(raw_tokens, external_tokens), 6
                ),
                "external_profile_byte_overhead_pct": round(
                    _percent_over(raw_bytes, external_bytes), 6
                ),
                "history_no_regret_tokens": history_tokens,
                "history_token_saving_pct": round(history_saving, 6),
                "history_mode_counts": dict(sorted(history_mode_counts.items())),
                "h2_pass": h2_pass,
                "h3_pass_if_task_family": (
                    history_saving >= 20.0 if family in TASK_FAMILIES else None
                ),
            }
            total_positive_regret += positive_regret_turns

        overall_fields = (
            "turns",
            "raw_tokens",
            "raw_utf8_bytes",
            "integrity_matched_raw_tokens",
            "integrity_matched_raw_bytes",
            "warm_selected_tokens",
            "warm_selected_utf8_bytes",
            "compact_selected",
            "cold_total_tokens",
            "cold_total_utf8_bytes",
            "post_decode_model_input_tokens",
            "external_profile_tokens",
            "external_profile_utf8_bytes",
            "history_no_regret_tokens",
        )
        overall = {
            field: sum(family_results[family][field] for family in FAMILY_ORDER)
            for field in overall_fields
        }
        overall["compact_coverage_pct"] = round(
            overall["compact_selected"] * 100.0 / overall["turns"], 6
        )
        overall["warm_carrier_token_saving_pct"] = round(
            _percent_saved(overall["raw_tokens"], overall["warm_selected_tokens"]), 6
        )
        overall["cold_carrier_token_saving_pct"] = round(
            _percent_saved(overall["raw_tokens"], overall["cold_total_tokens"]), 6
        )
        overall["warm_wire_byte_saving_pct"] = round(
            _percent_saved(overall["raw_utf8_bytes"], overall["warm_selected_utf8_bytes"]),
            6,
        )
        overall["post_decode_model_input_saving_pct"] = 0.0
        overall["external_profile_token_overhead_pct"] = round(
            _percent_over(overall["raw_tokens"], overall["external_profile_tokens"]), 6
        )
        overall["external_profile_byte_overhead_pct"] = round(
            _percent_over(overall["raw_utf8_bytes"], overall["external_profile_utf8_bytes"]),
            6,
        )
        overall["history_token_saving_pct"] = round(
            _percent_saved(overall["raw_tokens"], overall["history_no_regret_tokens"]), 6
        )
        overall["cold_activated_families"] = sum(
            bool(family_results[family]["cold_activated"]) for family in FAMILY_ORDER
        )
        by_tokenizer[profile.key] = {
            "display_name": profile.display_name,
            "implementation": profile.implementation,
            "vocabulary_size": profile.vocabulary_size,
            "fingerprint": profile.fingerprint,
            "contract_artifact_tokens_per_cold_family": artifact_tokens,
            "overall": overall,
            "families": family_results,
        }

    candidate_attempts = sum(len(row.surfaces) for row in surfaces)
    external_attempts = len(surfaces)
    expected_candidate_attempts = (
        EXPECTED_TURNS * (len(MODE_ORDER) - 1)
        + (EXPECTED_TURNS - EXPECTED_RECORDS)
    )
    if candidate_attempts != expected_candidate_attempts:
        raise EvaluationError("candidate-attempt count changed")
    if external_attempts != EXPECTED_TURNS:
        raise EvaluationError("external-profile attempt count changed")
    expected_selections = EXPECTED_TURNS * len(profiles)
    if total_selected_exact != expected_selections:
        raise EvaluationError("selected exactness count changed")
    h1_pass = total_positive_regret == 0 and total_selected_exact == expected_selections
    h2_pass = all(
        by_tokenizer[tokenizer]["families"][family]["h2_pass"]
        for tokenizer in by_tokenizer
        for family in FAMILY_ORDER
    )
    h3_pass = all(
        by_tokenizer[tokenizer]["families"][family]["h3_pass_if_task_family"]
        for tokenizer in by_tokenizer
        for family in TASK_FAMILIES
    )
    return {
        "records": EXPECTED_RECORDS,
        "turns": EXPECTED_TURNS,
        "candidate_exact_roundtrips": candidate_attempts,
        "candidate_exact_roundtrips_expected": expected_candidate_attempts,
        "candidate_deterministic_reencodes": candidate_attempts,
        "candidate_deterministic_reencodes_expected": expected_candidate_attempts,
        "external_profile_exact_roundtrips": external_attempts,
        "external_profile_exact_roundtrips_expected": EXPECTED_TURNS,
        "selected_exact_roundtrips": total_selected_exact,
        "selected_exact_roundtrips_expected": expected_selections,
        "selected_deterministic_reencodes": total_selected_deterministic,
        "selected_deterministic_reencodes_expected": expected_selections,
        "positive_regret_turn_tokenizer_pairs": total_positive_regret,
        "post_decode_api_input_saving_pct": 0.0,
        "by_tokenizer": by_tokenizer,
        "latency": {
            "candidate_encode_by_mode": {
                mode: _latency_summary(encode_latencies[mode])
                for mode in MODE_ORDER
            },
            "candidate_decode_by_mode": {
                mode: _latency_summary(decode_latencies[mode])
                for mode in MODE_ORDER
            },
            "token_count_and_select_by_tokenizer": {
                profile.key: _latency_summary(selection_latencies[profile.key])
                for profile in profiles
            },
            "selected_decode_by_tokenizer": {
                profile.key: _latency_summary(selected_decode_latencies[profile.key])
                for profile in profiles
            },
            "boundary": "Machine-specific wall-clock samples; paths perform unequal work.",
        },
        "hypotheses": {
            "h1_lossless_no_regret": {
                "status": "pass" if h1_pass else "fail",
                "pass": h1_pass,
                "reason": (
                    f"{total_positive_regret} positive-regret pairs across "
                    f"{expected_selections} turn-tokenizer choices; all selected "
                    "carriers recovered exact UTF-8."
                ),
            },
            "h2_general_compact_value": {
                "status": "pass" if h2_pass else "fail",
                "pass": h2_pass,
                "reason": (
                    "Requires at least 10% compact coverage and at least 5% warm "
                    "carrier-token saving in every family under every tokenizer."
                ),
            },
            "h3_repeated_context_value": {
                "status": "pass" if h3_pass else "fail",
                "pass": h3_pass,
                "reason": (
                    "Requires at least 20% warm carrier-token saving from the "
                    "raw-or-causal-history chooser in both task families under "
                    "every tokenizer."
                ),
            },
            "h4_end_to_end_gate": {
                "status": "not_evaluated",
                "pass": False,
                "reason": "No provider calls, model task-success trial, or total-task-token measurement was run.",
            },
        },
    }


def _sgd_oracle_state(frames: Any) -> Mapping[str, Any]:
    if not isinstance(frames, list):
        raise EvaluationError("SGD gold frames are missing")
    compact_frames = []
    for frame in frames:
        actions = []
        for action in frame.get("actions", []):
            actions.append(
                {
                    "act": action.get("act"),
                    "slot": action.get("slot"),
                    "values": action.get("canonical_values", action.get("values", [])),
                }
            )
        value: dict[str, Any] = {
            "actions": actions,
            "service": frame.get("service"),
        }
        if "state" in frame:
            state = frame["state"]
            value["state"] = {
                "active_intent": state.get("active_intent"),
                "requested_slots": state.get("requested_slots", []),
                "slot_values": state.get("slot_values", {}),
            }
        compact_frames.append(value)
    return {"frames": compact_frames}


def _sgd_target(frames: Any) -> list[Mapping[str, Any]]:
    targets = []
    for frame in frames:
        for action in frame.get("actions", []):
            targets.append(
                {
                    "act": action.get("act"),
                    "service": frame.get("service"),
                    "slot": action.get("slot"),
                }
            )
    return targets


def build_sgd_prompt_pairs(
    records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, str, str], ...]:
    pairs: list[tuple[str, str, str]] = []
    sequence = hashlib.sha256()
    for record in records:
        if record["source_family"] != "schema_guided_dialogue":
            continue
        history_lines: list[str] = []
        turns = record["turns"]
        for index, turn in enumerate(turns):
            if turn["role"] == "assistant" and index > 0 and turns[index - 1]["role"] == "user":
                previous = turns[index - 1]
                raw_prompt = (
                    SGD_INSTRUCTION
                    + "\nHISTORY:\n"
                    + "\n".join(history_lines)
                    + "\nNEXT:"
                )
                oracle = canonical_bytes(_sgd_oracle_state(previous.get("gold_frames"))).decode(
                    "utf-8"
                )
                oracle_prompt = SGD_INSTRUCTION + "\nORACLE_STATE:" + oracle + "\nNEXT:"
                target = canonical_bytes(_sgd_target(turn.get("gold_frames"))).decode("utf-8")
                pair_id = f"{record['corpus_id']}:{index}"
                digest_value = canonical_bytes(
                    {"id": pair_id, "raw": raw_prompt, "oracle": oracle_prompt, "target": target}
                )
                sequence.update(len(digest_value).to_bytes(8, "big"))
                sequence.update(digest_value)
                pairs.append((raw_prompt, oracle_prompt, target))
            prefix = "U" if turn["role"] == "user" else "A"
            history_lines.append(f"{prefix}:{turn['text']}")
    if not pairs:
        raise EvaluationError("no SGD prompt pairs were constructed")
    return tuple(pairs)


def measure_sgd_oracle(
    records: Sequence[Mapping[str, Any]], profiles: Sequence[TokenizerProfile]
) -> Mapping[str, Any]:
    pairs = build_sgd_prompt_pairs(records)
    digest = hashlib.sha256()
    for raw_prompt, oracle_prompt, target in pairs:
        value = canonical_bytes(
            {
                "raw_prompt_sha256": sha256_bytes(raw_prompt.encode("utf-8")),
                "oracle_prompt_sha256": sha256_bytes(oracle_prompt.encode("utf-8")),
                "target_sha256": sha256_bytes(target.encode("utf-8")),
            }
        )
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    raw_bytes = sum(len(raw.encode("utf-8")) for raw, _, _ in pairs)
    oracle_bytes = sum(len(oracle.encode("utf-8")) for _, oracle, _ in pairs)
    by_tokenizer = {}
    for profile in profiles:
        raw_tokens = sum(profile.count(raw) for raw, _, _ in pairs)
        oracle_tokens = sum(profile.count(oracle) for _, oracle, _ in pairs)
        by_tokenizer[profile.key] = {
            "raw_history_prompt_tokens": raw_tokens,
            "oracle_state_prompt_tokens": oracle_tokens,
            "oracle_prompt_token_saving_pct": round(
                _percent_saved(raw_tokens, oracle_tokens), 6
            ),
        }
    return {
        "status": "oracle_semantic_task_level_upper_bound_not_lossless_not_deployment",
        "model_calls": 0,
        "accuracy_measured": False,
        "targets": len(pairs),
        "prompt_pair_digest": digest.hexdigest(),
        "raw_history_prompt_utf8_bytes": raw_bytes,
        "oracle_state_prompt_utf8_bytes": oracle_bytes,
        "oracle_prompt_byte_saving_pct": round(_percent_saved(raw_bytes, oracle_bytes), 6),
        "by_tokenizer": by_tokenizer,
        "limitations": [
            "Gold state and action annotations are supplied by the dataset rather than predicted.",
            "No model consumed either prompt, so no next-action accuracy or task utility was established.",
            "The oracle prompt intentionally omits original wording and cannot reconstruct the dialogue.",
            "Parser, schema transfer, tool results, repair, and output tokens are not measured.",
        ],
    }


def run_study(
    work_root: Path = WORK_ROOT,
    asset_root: Path = TOKENIZER_ASSET_ROOT,
) -> Mapping[str, Any]:
    inputs = verify_frozen_inputs(work_root)
    # These imports and version checks are intentionally after the complete
    # frozen-input verification above.
    _require_zlib_versions()
    profiles = load_pinned_tokenizers(asset_root)
    brotli, zstandard = _load_strong_compressors()
    lossless = measure_lossless_lane(inputs, profiles, brotli, zstandard)
    oracle = measure_sgd_oracle(inputs.records, profiles)
    return {
        "format": FORMAT,
        "status": "offline_frozen_broad_dialogue_measurement",
        "claim_boundary": (
            "Broad four-family serialization study plus an SGD oracle prompt-size "
            "upper bound; not model comprehension, task success, total task tokens, "
            "energy, deployment, adoption, or state-of-the-art evidence."
        ),
        "paid_or_provider_calls": 0,
        "postmeasurement_reproducibility_amendment": inputs.contract[
            "postmeasurement_reproducibility_amendment"
        ],
        "inputs": {
            "contract_file": CONTRACT_PATH.name,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "contract_utf8_bytes": len(inputs.contract_bytes),
            "source_freeze_sha256": EXPECTED_SOURCE_FREEZE_SHA256,
            "corpus_manifest_sha256": EXPECTED_CORPUS_MANIFEST_SHA256,
            "corpus_file_sha256": EXPECTED_CORPUS_SHA256,
            "corpus_sequence_sha256": EXPECTED_SEQUENCE_SHA256,
            "records": EXPECTED_RECORDS,
            "turns": EXPECTED_TURNS,
            "source_families": list(FAMILY_ORDER),
            "tokenizer_asset_files": inputs.contract["tokenizer_asset_files"],
            "evaluator_sha256": sha256_file(Path(__file__)),
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "zlib_compile_version": zlib.ZLIB_VERSION,
            "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
            "dependencies": {
                name: metadata.version(name) for name in REQUIRED_VERSIONS
            },
        },
        "lossless_raw_text": lossless,
        "sgd_gold_action_state_oracle": oracle,
    }


def _fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def render_report(results: Mapping[str, Any], inputs: VerifiedInputs) -> str:
    lossless = results["lossless_raw_text"]
    hypotheses = lossless["hypotheses"]
    lines = [
        "# Urusilla Frozen Broad-Dialogue Evaluation",
        "",
        "> **Result boundary:** This is an offline lossless carrier measurement over a frozen four-family convenience sample and a separate SGD gold-state oracle prompt-size upper bound. It is not an end-to-end model, task-success, total-task-token, energy, deployment, adoption, or state-of-the-art result.",
        "",
        "## Postmeasurement reproducibility amendment",
        "",
        "After the first measurement, reproducibility review changed only how already-fixed tokenizer vocabularies and zlib are loaded: cl100k and o200k now require explicit local hash-pinned `.tiktoken` files, and both zlib compile and runtime versions must equal 1.2.12. The measurement path contains no tokenizer download or cache fallback.",
        "",
        "Candidate algorithms, ordering, hypotheses, gates, and previously reported non-latency outcome numbers did not change. The amended contract is larger, but all cold plans still reject activation and retain zero saving. Previously recorded latency samples are retained rather than presented as a deterministic refreeze product.",
        "",
        "The source and method chronology is a project-internal freeze, not an externally registered or independently witnessed preregistration. The project authors could access the corpus while implementing the evaluator. The narrow auditable statement is that no evaluated-corpus-derived dictionary or learned profile is used; this study does not claim to exclude every possible tuning influence.",
        "",
        "## Bottom line",
        "",
        f"- H1 lossless no-regret: **{hypotheses['h1_lossless_no_regret']['status'].upper()}**.",
        f"- H2 general compact value: **{hypotheses['h2_general_compact_value']['status'].upper()}**.",
        f"- H3 repeated-context value: **{hypotheses['h3_repeated_context_value']['status'].upper()}**.",
        "- H4 end-to-end gate: **NOT EVALUATED**; there were zero model or provider calls.",
        "- Every selected compact carrier is deterministically decoded before a model call. Therefore measured post-decode API-input token saving is **0.00%** under all four tokenizers.",
        "",
        "Receiver-carrier token savings below describe the complete text presented to the deterministic receiver codec. They are serialization opportunities, not evidence that an unmodified model understands compressed Base64url text. The bare UTF-8 text is always the receiver-token baseline and fallback.",
        "",
        "## Frozen inputs and order of operations",
        "",
        "The evaluator verified all frozen files, flags, family counts, turn counts, hypotheses, and sequence digests before loading tokenizer or compressor packages.",
        "",
        f"- Evaluation contract: `{results['inputs']['contract_sha256']}` ({results['inputs']['contract_utf8_bytes']:,} bytes).",
        f"- Source freeze: `{results['inputs']['source_freeze_sha256']}`.",
        f"- Corpus manifest: `{results['inputs']['corpus_manifest_sha256']}`.",
        f"- Corpus JSONL: `{results['inputs']['corpus_file_sha256']}`.",
        f"- Corpus sequence: `{results['inputs']['corpus_sequence_sha256']}`.",
        f"- Corpus size: {results['inputs']['records']} records and {results['inputs']['turns']:,} turns.",
        f"- Evaluator source: `{results['inputs']['evaluator_sha256']}`.",
        "",
        "Repository flags record that the sources were frozen before project codec or tokenizer import and before the first measurement. This is internal chronology rather than external preregistration. The evaluator is project-authored, was not independently blinded, and no candidate uses an evaluated-corpus-derived dictionary or learned profile.",
        "",
        "## Predeclared hypotheses",
        "",
        "| Hypothesis | Result | Gate |",
        "|---|---:|---|",
    ]
    for key in (
        "h1_lossless_no_regret",
        "h2_general_compact_value",
        "h3_repeated_context_value",
        "h4_end_to_end_gate",
    ):
        item = hypotheses[key]
        lines.append(f"| {key} | {item['status']} | {item['reason']} |")
    lines.extend(
        [
            "",
            "## Lossless carrier results",
            "",
            "| Tokenizer | Raw tokens | Warm selected | Warm saving | Compact coverage | Cold total | Cold saving | Cold families active | Post-decode API saving |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tokenizer, data in lossless["by_tokenizer"].items():
        row = data["overall"]
        lines.append(
            f"| {tokenizer} | {row['raw_tokens']:,} | {row['warm_selected_tokens']:,} | "
            f"{_fmt_pct(row['warm_carrier_token_saving_pct'])} | "
            f"{_fmt_pct(row['compact_coverage_pct'])} | {row['cold_total_tokens']:,} | "
            f"{_fmt_pct(row['cold_carrier_token_saving_pct'])} | "
            f"{row['cold_activated_families']}/4 | 0.00% |"
        )
    lines.extend(
        [
            "",
            "Cold accounting charges the complete contract once for each independently cold family session. It assumes the named compressor implementations are already installed; executable installation cost is excluded and no no-install deployment claim is made.",
            "",
            "### Integrity-matched raw control and selected modes",
            "",
            "| Tokenizer | Bare raw tokens | Checked raw tokens | Checked token overhead | Bare raw bytes | Checked raw bytes | Checked byte overhead |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tokenizer, data in lossless["by_tokenizer"].items():
        row = data["overall"]
        lines.append(
            f"| {tokenizer} | {row['raw_tokens']:,} | {row['integrity_matched_raw_tokens']:,} | "
            f"{_fmt_pct(_percent_over(row['raw_tokens'], row['integrity_matched_raw_tokens']))} | "
            f"{row['raw_utf8_bytes']:,} | {row['integrity_matched_raw_bytes']:,} | "
            f"{_fmt_pct(_percent_over(row['raw_utf8_bytes'], row['integrity_matched_raw_bytes']))} |"
        )
    lines.extend(
        [
            "",
            "Every generic compressor uses the same length, digest, and Base64url envelope as `raw_checked`. Bare raw remains the receiver-token fallback; `raw_checked` isolates envelope overhead for compression comparisons and does not count as a compact choice.",
            "",
            "| Tokenizer | raw | raw_checked | deflate64 | brotli64 | zstd64 | history_deflate64 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tokenizer, data in lossless["by_tokenizer"].items():
        counts: Counter[str] = Counter()
        for family in FAMILY_ORDER:
            counts.update(data["families"][family]["mode_counts"])
        lines.append(
            f"| {tokenizer} | "
            + " | ".join(f"{counts[mode]:,}" for mode in MODE_ORDER)
            + " |"
        )
    lines.extend(
        [
            "",
            "### Per-family outcomes",
            "",
            "| Tokenizer | Family | Turns | Raw | Warm | Token saving | Byte saving | Compact | Cold active | Cold saving | History-only saving | H2 | H3 if task |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tokenizer, data in lossless["by_tokenizer"].items():
        for family in FAMILY_ORDER:
            row = data["families"][family]
            h3 = "n/a" if row["h3_pass_if_task_family"] is None else str(row["h3_pass_if_task_family"]).lower()
            lines.append(
                f"| {tokenizer} | {family} | {row['turns']:,} | {row['raw_tokens']:,} | "
                f"{row['warm_selected_tokens']:,} | {_fmt_pct(row['warm_carrier_token_saving_pct'])} | "
                f"{_fmt_pct(row['warm_wire_byte_saving_pct'])} | "
                f"{row['compact_selected']:,} ({_fmt_pct(row['compact_coverage_pct'])}) | "
                f"{str(row['cold_activated']).lower()} | {_fmt_pct(row['cold_carrier_token_saving_pct'])} | "
                f"{_fmt_pct(row['history_token_saving_pct'])} | {str(row['h2_pass']).lower()} | {h3} |"
            )
    lines.extend(
        [
            "",
            "### Exactness, modes, bytes, and integrity-matched control",
            "",
            f"- Candidate exact round trips: {lossless['candidate_exact_roundtrips']:,}/{lossless['candidate_exact_roundtrips_expected']:,}.",
            f"- Candidate deterministic re-encodes: {lossless['candidate_deterministic_reencodes']:,}/{lossless['candidate_deterministic_reencodes_expected']:,}.",
            f"- Selected turn-tokenizer exact round trips: {lossless['selected_exact_roundtrips']:,}/{lossless['selected_exact_roundtrips_expected']:,}.",
            f"- Positive-regret selected pairs: {lossless['positive_regret_turn_tokenizer_pairs']:,}.",
            f"- External-profile exact round trips: {lossless['external_profile_exact_roundtrips']:,}/{lossless['external_profile_exact_roundtrips_expected']:,}.",
            "",
            "The `raw_checked` mode carries uncompressed UTF-8 through the identical length, digest, and Base64url envelope used by generic compressors. It is reported in every per-family JSON result so compression is not credited for envelope overhead. Bare raw remains a separate receiver-token baseline because an authenticated transport can carry it without this application envelope.",
            "",
            "Mode counts and complete per-mode byte/token totals are preserved in `urusilla_general_dialogue_results.json`. Network-byte reductions do not imply model-token reductions, and every compact carrier is decoded back to the original text before any hypothetical model input.",
            "",
            "## Minimal Urusilla external-profile control",
            "",
            "This separate canonical JSON carrier preserves exactly `profile`, `role`, `session`, `turn`, and `text`. It is an experimental external carrier profile, not core UrusillaIR, not a model-native surface, and not eligible for H1-H3 savings.",
            "",
            "| Tokenizer | Raw tokens | External-profile tokens | Token overhead | Raw bytes | External-profile bytes | Byte overhead |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tokenizer, data in lossless["by_tokenizer"].items():
        row = data["overall"]
        lines.append(
            f"| {tokenizer} | {row['raw_tokens']:,} | {row['external_profile_tokens']:,} | "
            f"{_fmt_pct(row['external_profile_token_overhead_pct'])} | {row['raw_utf8_bytes']:,} | "
            f"{row['external_profile_utf8_bytes']:,} | {_fmt_pct(row['external_profile_byte_overhead_pct'])} |"
        )
    oracle = results["sgd_gold_action_state_oracle"]
    lines.extend(
        [
            "",
            "## SGD gold action/state oracle upper bound",
            "",
            f"The frozen SGD subset produced {oracle['targets']:,} next-assistant-action prompt pairs. No model was called and no accuracy was measured. The comparison replaces exact raw dialogue history with the immediately preceding user turn's dataset-provided gold service, action, and cumulative state JSON. It intentionally loses prose and therefore cannot enter the lossless result.",
            "",
            "| Tokenizer | Raw-history prompt | Gold-state oracle prompt | Token difference |",
            "|---|---:|---:|---:|",
        ]
    )
    for tokenizer, row in oracle["by_tokenizer"].items():
        lines.append(
            f"| {tokenizer} | {row['raw_history_prompt_tokens']:,} | "
            f"{row['oracle_state_prompt_tokens']:,} | "
            f"{_fmt_pct(row['oracle_prompt_token_saving_pct'])} |"
        )
    lines.extend(
        [
            "",
            f"Byte difference: {_fmt_pct(oracle['oracle_prompt_byte_saving_pct'])}. Prompt-pair digest: `{oracle['prompt_pair_digest']}`.",
            "",
            "This is only an opportunity upper bound. A deployment would have to infer state without gold annotations, preserve safety-relevant details, obtain tool results, generate correct actions, include output and repair tokens, and pass the separately frozen H4 task-success gate.",
            "",
            "## Latency",
            "",
            "| Mode | Encode p50 / p95 (microseconds) | Decode p50 / p95 (microseconds) |",
            "|---|---:|---:|",
        ]
    )
    for mode in MODE_ORDER:
        encode = lossless["latency"]["candidate_encode_by_mode"][mode]
        decode = lossless["latency"]["candidate_decode_by_mode"][mode]
        lines.append(
            f"| {mode} | {encode['p50_us']:.3f} / {encode['p95_us']:.3f} | "
            f"{decode['p50_us']:.3f} / {decode['p95_us']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Latency is machine-specific wall-clock evidence and the paths perform unequal work. It supports no universal speed claim.",
            "",
            "## Sources, licenses, and acquisition",
            "",
            "Raw mixed-license records remain under the ignored `work/general_dialogue/` directory and are not included in public result artifacts. Reacquire each exact revision and verify the listed size and SHA-256 before rebuilding the corpus:",
            "",
            "| Source key | License | Revision | Bytes | SHA-256 | Acquisition URL |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for source in inputs.source_freeze["source_families"]:
        lines.append(
            f"| {source['key']} | [{source['license']}]({source['license_url']}) | "
            f"`{source['revision']}` | {source['expected_size']:,} | `{source['sha256']}` | "
            f"[immutable source]({source['url']}) |"
        )
    lines.extend(
        [
            "",
            "No source utterance is reproduced in this report. Aggregate public artifacts contain only digests, counts, measurements, and acquisition metadata.",
            "",
            "### Separate tokenizer acquisition step",
            "",
            "Tokenizer assets must be acquired before measurement and stored at the exact ignored paths below. Acquisition is not part of the evaluator; a missing file, byte-size mismatch, or digest mismatch fails closed. In particular, the evaluator never calls `tiktoken.get_encoding`, never reads the global tiktoken cache, and never downloads a vocabulary.",
            "",
            "| Tokenizer | Ignored local path | Bytes | SHA-256 | Acquisition URL |",
            "|---|---|---:|---|---|",
        ]
    )
    for key, asset in inputs.contract["tokenizer_asset_files"].items():
        lines.append(
            f"| {key} | `{asset['relative_path']}` | {asset['bytes']:,} | "
            f"`{asset['sha256']}` | [download separately]({asset['acquisition_url']}) |"
        )
    lines.extend(
        [
            "",
            "Download these files in an explicit preparation step, verify SHA-256 and byte size, then disconnect or deny network access before invoking the evaluator.",
            "",
            "## Reproduction",
            "",
            "```bash",
            ".venv-research-py312/bin/python -m unittest -v test_urusilla_general_dialogue_eval.py",
            ".venv-research-py312/bin/python urusilla_general_dialogue_eval.py --write",
            "```",
            "",
            "The run requires the ignored frozen corpus and all four tokenizer assets plus the exact dependency versions in `requirements-research.lock`. It fails unless zlib compile and runtime versions are both 1.2.12. The measurement performs no network or provider call.",
            "",
        ]
    )
    return "\n".join(lines)


def write_results(
    results: Mapping[str, Any],
    inputs: VerifiedInputs,
    results_path: Path = RESULTS_PATH,
    report_path: Path = REPORT_PATH,
) -> tuple[str, str]:
    frozen_results = copy.deepcopy(results)
    if results_path.is_file():
        try:
            previous = json.loads(results_path.read_text(encoding="utf-8"))
            previous_latency = previous["lossless_raw_text"]["latency"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise EvaluationError(
                "cannot preserve the first published latency block during refreeze"
            ) from exc
        if (
            previous.get("format") != FORMAT
            or previous.get("inputs", {}).get("corpus_file_sha256")
            != EXPECTED_CORPUS_SHA256
            or previous.get("inputs", {}).get("corpus_sequence_sha256")
            != EXPECTED_SEQUENCE_SHA256
        ):
            raise EvaluationError(
                "existing result identity does not match the frozen dialogue study"
            )
        required_latency_sections = {
            "candidate_encode_by_mode",
            "candidate_decode_by_mode",
            "token_count_and_select_by_tokenizer",
            "selected_decode_by_tokenizer",
        }
        if not required_latency_sections.issubset(previous_latency):
            raise EvaluationError("existing latency block is incomplete")
        frozen_results["lossless_raw_text"]["latency"] = copy.deepcopy(
            previous_latency
        )
    frozen_results["lossless_raw_text"]["latency"]["refreeze_policy"] = (
        "Machine-specific samples retained from the first recorded measurement; "
        "postmeasurement reproducibility refreezes do not replace them."
    )
    result_bytes = json.dumps(
        frozen_results,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    results_path.write_bytes(result_bytes)
    report_path.write_text(render_report(frozen_results, inputs), encoding="utf-8")
    return sha256_bytes(result_bytes), sha256_file(report_path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, default=WORK_ROOT)
    parser.add_argument("--assets-dir", type=Path, default=TOKENIZER_ASSET_ROOT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    inputs = verify_frozen_inputs(args.work_root)
    if args.verify_only:
        print(
            json.dumps(
                {
                    "contract_sha256": EXPECTED_CONTRACT_SHA256,
                    "corpus_sha256": EXPECTED_CORPUS_SHA256,
                    "sequence_sha256": EXPECTED_SEQUENCE_SHA256,
                    "records": len(inputs.records),
                    "turns": sum(len(record["turns"]) for record in inputs.records),
                    "verified_before_tokenizer_import": True,
                },
                sort_keys=True,
            )
        )
        return 0
    results = run_study(args.work_root, args.assets_dir)
    if args.write:
        result_sha, report_sha = write_results(results, inputs)
        print(
            json.dumps(
                {
                    "results_sha256": result_sha,
                    "report_sha256": report_sha,
                    "hypotheses": results["lossless_raw_text"]["hypotheses"],
                },
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
