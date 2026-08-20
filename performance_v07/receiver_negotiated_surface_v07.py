#!/usr/bin/env python3
"""Receiver-bound token surface v0.7 research implementation.

This module derives every profile from the exact frozen 223-message
development partition before it evaluates the unchanged grouped holdout or
out-of-domain fixtures.  A profile combines:

* one pinned receiver tokenizer and its exact vocabulary fingerprint;
* a deterministic 1,024, 2,048, or 4,096-entry byte-fragment codebook; and
* an equal-size alphabet of boundary-delimited text symbols that each encode
  to exactly one receiver token, both alone and in canonical concatenations.

The surface is an exact serialization of the unchanged canonical v0.2 frame.
It does not claim model comprehension, task success, native model support, or
state-of-the-art performance.  The leading ASCII space in every symbol is a
deliberate token boundary.  Trimming or rewriting it is corruption and fails
closed through syntax checks, token-ID verification, a profile-bound checksum,
and canonical re-encoding.
"""

from __future__ import annotations

import argparse
from array import array
import base64
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import gc
import hashlib
import heapq
import hmac
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import unicodedata

from urusilla_benchmark import corpus_digest
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
from urusilla_tokenizer_benchmark import (
    OPEN_TOKENIZERS,
    TIKTOKEN_VERSION,
    TOKENIZERS_VERSION,
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
)
from urusilla_wire_v02 import (
    DEFAULT_PROFILE,
    decode_message as decode_v02,
    encode_capsule as encode_v02_capsule,
    encode_message as encode_v02,
)

from urusilla_generalization_surface_v06 import (
    PreparedMessage as V06PreparedMessage,
    decode_selected as decode_v06_selected,
    derive_alias_profile,
    existing_grammar_capsule,
    optimized_grammar_capsule,
    plan_cold_session as plan_v06_cold_session,
    prepare_message as prepare_v06,
    profile_capsule as v06_profile_capsule,
    select_message as select_v06_message,
    select_prepared as select_v06_prepared,
)
from urusilla_token_surface_v04 import (
    encode_codebook_capsule_text as encode_v04_codebook_capsule_text,
)


FORMAT = "urusilla-receiver-negotiated-surface-v0.7-experimental"
REPORT_NAME = "RECEIVER_NEGOTIATED_SURFACE_V07_RESULTS.md"
SNAPSHOT_NAME = "frozen_results.json"
PROFILE_SIZES = (1_024, 2_048, 4_096)
EXPECTED_DEVELOPMENT_MESSAGES = 224
EXPECTED_GROUPED_HOLDOUT_MESSAGES = 56
EXPECTED_OOD_MESSAGES = 10
MAX_PROFILE_SYMBOLS = max(PROFILE_SIZES)
MAX_SYMBOL_UTF8_BYTES = 64
MAX_ENTRY_BYTES = 64
MAX_PROFILE_CAPSULE_BYTES = 4 * 1024 * 1024
MAX_SURFACE_UTF8_BYTES = 64 * 1024 * 1024
# Auxiliary decoder structures scale with symbol count.  This cap is the
# number of maximum-size expansions needed to reach the underlying frame
# limit, and prevents a valid-size text from creating tens of millions of
# Python objects when it uses only one-byte fallback entries.
MAX_PAYLOAD_SYMBOLS = MAX_FRAME_BYTES // MAX_ENTRY_BYTES
PROFILE_TAG_BYTES = 12
CHECKSUM_BYTES = 8
CHECKSUM_CHARACTERS = 11
SURFACE_PREFIX = "R7."
CAPSULE_TEXT_PREFIX = "R7C:"
# Urusilla Receiver v0.7 Profile.  This is a clean experimental identity;
# decoders deliberately do not accept the retired pre-cutover magic.
PROFILE_MAGIC = b"URR7P\x01"
SAFETY_POLICY = "ascii-leading-space-alnum-prompt-denylist-v1"
MODEL_EXPOSURE_POLICY = "decoder-before-model-only"
DERIVATION_ALGORITHM = "linked-bpe-left-to-right-v1"
CANONICAL_ENCODING_POLICY = "minimum-symbols-lower-index-tie-v1"
INTEGRITY_POLICY = "blake2s-64-full-profile-and-frame-v1"
EXPECTED_TOKENIZER_KEYS = (
    "cl100k_base",
    "o200k_base",
    "qwen2_5_7b_instruct",
    "mistral_7b_instruct_v03",
)
EXPECTED_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}
TIKTOKEN_OFFLINE_ASSETS = {
    "cl100k_base": (
        "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
        "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    ),
    "o200k_base": (
        "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
        "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
    ),
}

DATASET_LABELS = {
    "development": "development training partition",
    "grouped_holdout": "grouped holdout",
    "out_of_domain": "out of domain",
}

_BOUNDARY_SYMBOL = re.compile(r" [A-Za-z0-9]+\Z")
_PAYLOAD = re.compile(r"(?: [A-Za-z0-9]+)+\Z")
_PROFILE_TAG = re.compile(r"[A-Za-z0-9_-]{16}\Z")
_CHECKSUM = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_SURFACE_DOMAIN = b"UrusillaReceiverSurface-v0.7\x00"
_PROFILE_CAPSULE_DOMAIN = b"UrusillaReceiverProfile-v0.7\x00"
_V02_CAPSULE_SHA256 = hashlib.sha256(encode_v02_capsule(DEFAULT_PROFILE)).digest()

# This finite denylist removes direct role/control markers, common prompt
# directives, credential words, and a small set of high-risk action terms from
# the alphabet.  It cannot make arbitrary token sequences semantically inert;
# the remaining risk is why raw surfaces are decoder-before-model transport.
_PROMPT_RISK_TERMS = frozenset(
    {
        "account",
        "admin",
        "administrator",
        "api",
        "assistant",
        "auth",
        "authenticate",
        "authorization",
        "bypass",
        "call",
        "command",
        "credential",
        "credentials",
        "delete",
        "developer",
        "disclose",
        "disregard",
        "download",
        "execute",
        "function",
        "ignore",
        "instruction",
        "instructions",
        "jailbreak",
        "key",
        "override",
        "password",
        "phone",
        "prompt",
        "reveal",
        "role",
        "root",
        "secret",
        "send",
        "shell",
        "ssn",
        "sudo",
        "system",
        "token",
        "tool",
        "upload",
        "user",
    }
)
PROMPT_RISK_DENYLIST_SHA256 = hashlib.sha256(
    "\n".join(sorted(_PROMPT_RISK_TERMS)).encode("ascii")
).hexdigest()

# Frozen after derivation from the exact ordered development partition.  The
# snapshot below is filled only after the complete deterministic sweep.
EXPECTED_BYTE_ENTRY_SHA256 = "01d3495f20ba18e79ec484c22f8f6395b88a7cdce4efc2a7088e2c4897c9ea6b"
EXPECTED_PROFILE_SHA256: Mapping[str, Mapping[int, str]] = {
    "cl100k_base": {
        1_024: "b5b98c160879ec821f38d5625fa93201391f400f82bb40153d9a77a7f706ff5b",
        2_048: "858b8291742cf772fbe40525bca7d6c9f56b141ddb266ede88af8aefcc2acf33",
        4_096: "a2381c6ae67c3bde5ae0ccb83f1b039993c37a669c4c855b94a07d4efcd69534",
    },
    "o200k_base": {
        1_024: "baec66d767f05e7f4efc1f7732583485b08f5fc5e528888d7eeeb4d1c88c443d",
        2_048: "c27a077c96095f1bfb155b57d6d4f5e93efbb0b28cee7f285c8fa4b7cfda4f70",
        4_096: "da2774c4f8da01cf1f18a3b93f01e44e22a7622da8d35b7d355775d245db8256",
    },
    "qwen2_5_7b_instruct": {
        1_024: "d10a1083c6c3f972186d561a64834d3854ae507351f0aec516727c171a54858d",
        2_048: "e67355f42e38ad1e0a9cfb39981d0cfe9c2a0b49a2b2551d91780f8af863d88e",
        4_096: "652e654cce91127e3800b4b0ae1e1ebe490cae06456e4b2c146f49fc2039893b",
    },
    "mistral_7b_instruct_v03": {
        1_024: "2bf907f0428a2d2774a40634bb0d5be19eaf208d185f4ac1e57ce155dae715a6",
        2_048: "51ea8442715b47843ba31d86c13470aa7a79d272ace8a60f21670bc90d140ab8",
        4_096: "c0160f89ebd2b71d63adf026d0cb45e921cabff254027b1bfc1641fe5466c7a4",
    },
}
EXPECTED_SNAPSHOT_SHA256 = "5c287f7eb6c34d7f9eb62593cff5a1e0ab978a86175daed7da896f23466f4b82"


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


def _unb64url(text: str) -> bytes:
    if not text or re.fullmatch(r"[A-Za-z0-9_-]+", text) is None:
        raise DecodeError("profile capsule text is not canonical Base64url")
    try:
        result = base64.b64decode(
            text + "=" * (-len(text) % 4), altchars=b"-_", validate=True
        )
    except Exception as exc:
        raise DecodeError("profile capsule text is malformed") from exc
    if _b64url(result) != text:
        raise DecodeError("profile capsule text is not canonical Base64url")
    return result


def _decoded_text_utf8_size(text: str, label: str) -> int:
    try:
        return len(text.encode("utf-8", errors="strict"))
    except UnicodeEncodeError as exc:
        raise DecodeError(f"{label} contains an unpaired Unicode surrogate") from exc


def _uvarint(value: int) -> bytes:
    if type(value) is not int or value < 0 or value > (1 << 64) - 1:
        raise ValidationError("uvarint value is outside uint64")
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def read(self, size: int) -> bytes:
        if type(size) is not int or size < 0 or self.position + size > len(self.data):
            raise DecodeError("truncated receiver profile capsule")
        result = self.data[self.position : self.position + size]
        self.position += size
        return result

    def uvarint(self) -> int:
        start = self.position
        value = 0
        shift = 0
        for _ in range(10):
            byte = self.read(1)[0]
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                raw = self.data[start : self.position]
                if value > (1 << 64) - 1 or raw != _uvarint(value):
                    raise DecodeError("non-canonical or overflowing profile uvarint")
                return value
            shift += 7
        raise DecodeError("profile uvarint exceeds ten bytes")

    def text(self, *, maximum: int = 256) -> str:
        size = self.uvarint()
        if size > maximum:
            raise DecodeError("profile text field exceeds its bound")
        try:
            return self.read(size).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise DecodeError("profile text field is invalid UTF-8") from exc

    def end(self) -> None:
        if self.position != len(self.data):
            raise DecodeError("receiver profile capsule has trailing data")


def _encode_text(text: str) -> bytes:
    raw = text.encode("utf-8")
    return _uvarint(len(raw)) + raw


def _is_boundary_symbol(text: str) -> bool:
    """Return whether text has the exact safe, uniquely segmented form."""

    if not isinstance(text, str) or _BOUNDARY_SYMBOL.fullmatch(text) is None:
        return False
    try:
        raw = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    if len(raw) > MAX_SYMBOL_UTF8_BYTES:
        return False
    if text != unicodedata.normalize("NFC", text):
        return False
    if text != unicodedata.normalize("NFKC", text):
        return False
    # The ASCII grammar above excludes controls, bidi formatting characters,
    # noncharacters, surrogates, markup delimiters, and every other whitespace.
    return text[0] == " " and not any(character.isspace() for character in text[1:])


def _passes_prompt_risk_filter(text: str) -> bool:
    if not _is_boundary_symbol(text):
        return False
    return text[1:].casefold() not in _PROMPT_RISK_TERMS


def _is_strict_scalar(text: str) -> bool:
    """Audit the older visible single-codepoint design; it is not used."""

    if len(text) != 1 or text.isascii() or text == "\ufffd":
        return False
    if not text.isprintable() or text.isspace():
        return False
    if unicodedata.category(text)[0] not in "LNS":
        return False
    if text != unicodedata.normalize("NFC", text):
        return False
    if text != unicodedata.normalize("NFKC", text):
        return False
    if unicodedata.bidirectional(text) in {
        "R", "AL", "AN", "RLE", "LRE", "RLO", "LRO", "PDF", "LRI", "RLI", "FSI", "PDI", "BN"
    }:
        return False
    name = unicodedata.name(text, "")
    if any(
        marker in name
        for marker in (
            "BLANK",
            "FILLER",
            "INVISIBLE",
            "PLACEHOLDER",
            "SEPARATOR",
            "SPACE",
        )
    ):
        return False
    return True


@dataclass(frozen=True)
class ReceiverTokenizer:
    key: str
    display_name: str
    implementation: str
    vocabulary_size: int
    fingerprint: str
    count: Callable[[str], int] = field(repr=False, compare=False)
    encode_ids: Callable[[str], list[int]] = field(repr=False, compare=False)
    symbol_candidates: tuple[tuple[str, int], ...] = field(repr=False)
    pre_filter_boundary_candidate_count: int
    safe_boundary_candidate_count: int
    prompt_risk_terms_removed: int
    strict_scalar_count: int

    def verify_text_ids(self, text: str, expected: Sequence[int]) -> bool:
        return self.encode_ids(text) == list(expected)

    @property
    def binding(self) -> tuple[str, str, int, str]:
        return (
            self.key,
            self.implementation,
            self.vocabulary_size,
            self.fingerprint,
        )


def _deduplicate_and_select(
    candidates: Iterable[tuple[str, int]],
) -> tuple[tuple[tuple[str, int], ...], int]:
    unique: dict[str, int] = {}
    for text, token_id in candidates:
        previous = unique.get(text)
        if previous is None or token_id < previous:
            unique[text] = token_id
    ordered = sorted(
        unique.items(), key=lambda item: (len(item[0].encode("utf-8")), item[0].encode("utf-8"), item[1])
    )
    return tuple(ordered[:MAX_PROFILE_SYMBOLS]), len(ordered)


def _audit_long_concatenations(
    encode_ids: Callable[[str], list[int]], candidates: Sequence[tuple[str, int]]
) -> None:
    if len(candidates) < MAX_PROFILE_SYMBOLS:
        raise RuntimeError(
            f"stable boundary symbols are insufficient: {len(candidates)} < {MAX_PROFILE_SYMBOLS}"
        )
    selected = tuple(candidates[:MAX_PROFILE_SYMBOLS])
    orders = (
        selected,
        tuple(reversed(selected)),
        selected[::2] + selected[1::2],
        selected + selected,
    )
    for values in orders:
        text = "".join(symbol for symbol, _token_id in values)
        expected = [token_id for _symbol, token_id in values]
        if encode_ids(text) != expected:
            raise RuntimeError("receiver alphabet changes tokenization under concatenation")


def _verify_tiktoken_cache_offline() -> Mapping[str, str]:
    """Require exact local tiktoken rank blobs before any loader can fetch."""

    if "TIKTOKEN_CACHE_DIR" in os.environ:
        cache_text = os.environ["TIKTOKEN_CACHE_DIR"]
    elif "DATA_GYM_CACHE_DIR" in os.environ:
        cache_text = os.environ["DATA_GYM_CACHE_DIR"]
    else:
        cache_text = str(Path(tempfile.gettempdir()) / "data-gym-cache")
    if not cache_text:
        raise RuntimeError("offline tiktoken cache is disabled")
    cache = Path(cache_text)
    verified: dict[str, str] = {}
    for key, (url, expected) in TIKTOKEN_OFFLINE_ASSETS.items():
        path = cache / hashlib.sha1(url.encode("utf-8")).hexdigest()
        if not path.is_file():
            raise RuntimeError(f"missing pinned offline tiktoken asset for {key}: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"offline tiktoken asset digest mismatch for {key}")
        verified[key] = str(path)
    return verified


def load_receivers(asset_root: Path | None = None) -> tuple[ReceiverTokenizer, ...]:
    """Load pinned tokenizers and derive safe boundary-token candidates offline."""

    root = default_asset_root() if asset_root is None else Path(asset_root)
    _verify_tiktoken_cache_offline()
    import tiktoken.load as tiktoken_load

    original_read_file = tiktoken_load.read_file

    def reject_network_read(_path: str) -> bytes:
        raise RuntimeError("network tokenizer reads are disabled for the v0.7 study")

    tiktoken_load.read_file = reject_network_read
    try:
        profiles = load_tokenizer_profiles(root)
    finally:
        tiktoken_load.read_file = original_read_file
    if tuple(profile.key for profile in profiles) != EXPECTED_TOKENIZER_KEYS:
        raise RuntimeError("the receiver set or order changed")
    for profile in profiles:
        if profile.fingerprint != EXPECTED_TOKENIZER_FINGERPRINTS[profile.key]:
            raise RuntimeError(f"pinned tokenizer fingerprint changed: {profile.key}")

    import tiktoken
    from tokenizers import Tokenizer

    result: list[ReceiverTokenizer] = []
    for profile in profiles[:2]:
        encoding = tiktoken.get_encoding(profile.key)

        def encode_ids(text: str, *, _encoding: Any = encoding) -> list[int]:
            return _encoding.encode(text, allowed_special=set(), disallowed_special=())

        boundary: list[tuple[str, int]] = []
        strict_scalars: set[str] = set()
        for raw, token_id in encoding._mergeable_ranks.items():
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                continue
            ids = encode_ids(text)
            if _is_strict_scalar(text) and ids == [token_id]:
                strict_scalars.add(text)
            if (
                _is_boundary_symbol(text)
                and ids == [token_id]
                and encode_ids(text + text) == [token_id, token_id]
            ):
                boundary.append((text, token_id))
        _unfiltered, pre_filter_total = _deduplicate_and_select(boundary)
        filtered = [item for item in boundary if _passes_prompt_risk_filter(item[0])]
        selected, total = _deduplicate_and_select(filtered)
        _audit_long_concatenations(encode_ids, selected)
        result.append(
            ReceiverTokenizer(
                profile.key,
                profile.display_name,
                profile.implementation,
                profile.vocabulary_size,
                profile.fingerprint,
                profile.count,
                encode_ids,
                selected,
                pre_filter_total,
                total,
                pre_filter_total - total,
                len(strict_scalars),
            )
        )

    specs = {spec.key: spec for spec in OPEN_TOKENIZERS}
    for profile in profiles[2:]:
        spec = specs[profile.key]
        path = root / spec.key / spec.filename
        tokenizer = Tokenizer.from_file(str(path))
        document = json.loads(path.read_text(encoding="utf-8"))
        added_ids = {int(item["id"]) for item in document.get("added_tokens", [])}

        def encode_ids(text: str, *, _tokenizer: Any = tokenizer) -> list[int]:
            return _tokenizer.encode(text, add_special_tokens=False).ids

        strict_scalars: set[str] = set()
        for token_id in range(tokenizer.get_vocab_size(with_added_tokens=True)):
            if token_id in added_ids:
                continue
            text = tokenizer.decode([token_id], skip_special_tokens=False)
            if _is_strict_scalar(text) and encode_ids(text) == [token_id]:
                strict_scalars.add(text)

        boundary: list[tuple[str, int]] = []
        if profile.key == "mistral_7b_instruct_v03":
            pool = (
                (" " + raw[1:], int(token_id))
                for raw, token_id in document["model"]["vocab"].items()
                if raw.startswith("\u2581") and raw.count("\u2581") == 1
            )
        else:
            pool = (
                (tokenizer.decode([token_id], skip_special_tokens=False), token_id)
                for token_id in range(tokenizer.get_vocab_size(with_added_tokens=True))
            )
        for text, token_id in pool:
            if token_id in added_ids:
                continue
            ids = encode_ids(text)
            if (
                _is_boundary_symbol(text)
                and ids == [token_id]
                and encode_ids(text + text) == [token_id, token_id]
            ):
                boundary.append((text, token_id))
        _unfiltered, pre_filter_total = _deduplicate_and_select(boundary)
        filtered = [item for item in boundary if _passes_prompt_risk_filter(item[0])]
        selected, total = _deduplicate_and_select(filtered)
        _audit_long_concatenations(encode_ids, selected)
        result.append(
            ReceiverTokenizer(
                profile.key,
                profile.display_name,
                profile.implementation,
                profile.vocabulary_size,
                profile.fingerprint,
                profile.count,
                encode_ids,
                selected,
                pre_filter_total,
                total,
                pre_filter_total - total,
                len(strict_scalars),
            )
        )
    return tuple(result)


def _training_frames(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[bytes, ...]:
    if (
        len(messages) != EXPECTED_DEVELOPMENT_MESSAGES
        or corpus_digest(messages) != EXPECTED_TRAIN_SHA256
    ):
        raise RuntimeError(
            "profile derivation requires the exact ordered frozen development partition"
        )
    return tuple(encode_v02(message) for message in messages)


def train_byte_entries(
    messages: Sequence[Mapping[str, Any]], *, target_size: int = MAX_PROFILE_SYMBOLS
) -> tuple[bytes, ...]:
    """Train deterministic linked-list BPE entries from the frozen partition.

    Pair frequency counts all current adjacent pairs.  Ties choose the lower
    pair of symbol IDs.  Occurrences are replaced left-to-right, matching the
    frozen v0.3 trainer while avoiding a complete corpus rescan per merge.
    """

    if target_size not in PROFILE_SIZES and target_size != MAX_PROFILE_SYMBOLS:
        raise ValidationError("requested codebook size was not predeclared")
    frames = _training_frames(messages)
    values: list[int] = []
    previous: list[int] = []
    following: list[int] = []
    alive: list[bool] = []
    for frame in frames:
        start = len(values)
        for offset, value in enumerate(frame):
            values.append(value)
            previous.append(start + offset - 1 if offset else -1)
            following.append(start + offset + 1 if offset + 1 < len(frame) else -1)
            alive.append(True)

    occurrences: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
    for left, right in enumerate(following):
        if right != -1:
            occurrences[(values[left], values[right])].add(left)
    heap = [(-len(nodes), pair) for pair, nodes in occurrences.items() if nodes]
    heapq.heapify(heap)
    entries = [bytes([value]) for value in range(256)]
    seen = set(entries)

    def remove_at(left: int, changed: set[tuple[int, int]]) -> None:
        if left == -1 or not alive[left] or following[left] == -1:
            return
        pair = (values[left], values[following[left]])
        occurrences[pair].discard(left)
        changed.add(pair)

    def add_at(left: int, changed: set[tuple[int, int]]) -> None:
        if left == -1 or not alive[left] or following[left] == -1:
            return
        pair = (values[left], values[following[left]])
        occurrences[pair].add(left)
        changed.add(pair)

    for new_symbol in range(256, target_size):
        while heap:
            negative_count, pair = heapq.heappop(heap)
            if occurrences[pair] and -negative_count == len(occurrences[pair]):
                break
        else:
            raise RuntimeError("development corpus cannot fill the requested codebook")
        expansion = entries[pair[0]] + entries[pair[1]]
        if expansion in seen or len(expansion) > MAX_ENTRY_BYTES:
            raise RuntimeError("deterministic byte training produced an invalid expansion")
        entries.append(expansion)
        seen.add(expansion)
        changed: set[tuple[int, int]] = set()
        for left in sorted(tuple(occurrences[pair])):
            if not alive[left]:
                continue
            right = following[left]
            if (
                right == -1
                or not alive[right]
                or (values[left], values[right]) != pair
            ):
                continue
            before = previous[left]
            after = following[right]
            remove_at(before, changed)
            remove_at(left, changed)
            remove_at(right, changed)
            values[left] = new_symbol
            following[left] = after
            if after != -1:
                previous[after] = left
            alive[right] = False
            previous[right] = -1
            following[right] = -1
            add_at(before, changed)
            add_at(left, changed)
        for changed_pair in changed:
            if occurrences[changed_pair]:
                heapq.heappush(
                    heap, (-len(occurrences[changed_pair]), changed_pair)
                )
    if len(entries) != target_size:
        raise RuntimeError("byte codebook cardinality changed")
    return tuple(entries)


_TRIE_CACHE: dict[tuple[bytes, ...], dict[Any, Any]] = {}


def _encoding_trie(entries: tuple[bytes, ...]) -> dict[Any, Any]:
    cached = _TRIE_CACHE.get(entries)
    if cached is not None:
        return cached
    root: dict[Any, Any] = {}
    for index, expansion in enumerate(entries):
        node = root
        for byte in expansion:
            node = node.setdefault(byte, {})
        node[None] = index
    if len(_TRIE_CACHE) >= 6:
        _TRIE_CACHE.pop(next(iter(_TRIE_CACHE)))
    _TRIE_CACHE[entries] = root
    return root


def optimal_indices(raw: bytes, entries: tuple[bytes, ...]) -> tuple[int, ...]:
    """Return the minimum-symbol parse; a lower current index breaks ties."""

    if not isinstance(raw, bytes):
        raise TypeError("byte optimizer input must be bytes")
    if len(raw) > MAX_FRAME_BYTES:
        raise ValidationError("byte optimizer input exceeds the frame bound")
    if not 256 <= len(entries) <= MAX_PROFILE_SYMBOLS:
        raise ValidationError("byte optimizer codebook size is invalid")
    if not raw:
        return ()
    trie = _encoding_trie(entries)
    size = len(raw)
    unreachable = size + 1
    window_size = max(len(entry) for entry in entries) + 1
    future_cost = [unreachable] * window_size
    choices = array("H", [0]) * size
    future_cost[size % window_size] = 0
    for position in range(size - 1, -1, -1):
        node = trie
        scan = position
        best = (unreachable, len(entries), -1)
        while scan < size and raw[scan] in node:
            node = node[raw[scan]]
            scan += 1
            index = node.get(None)
            if index is None:
                continue
            candidate = (1 + future_cost[scan % window_size], index, scan)
            if candidate[:2] < best[:2]:
                best = candidate
        if best[2] < 0:
            raise RuntimeError("byte codebook lost complete one-byte coverage")
        future_cost[position % window_size] = best[0]
        choices[position] = best[1]
    result: list[int] = []
    position = 0
    while position < size:
        index = choices[position]
        result.append(index)
        position += len(entries[index])
    if len(result) != future_cost[0]:
        raise RuntimeError("byte optimizer reconstruction changed its optimum")
    return tuple(result)


@dataclass(frozen=True)
class ReceiverProfile:
    receiver: ReceiverTokenizer = field(repr=False, compare=False)
    size: int
    training_sha256: str
    entries: tuple[bytes, ...]
    symbols: tuple[str, ...]
    token_ids: tuple[int, ...]
    _capsule_cache: bytes = field(init=False, repr=False, compare=False)
    _sha256_cache: str = field(init=False, repr=False, compare=False)
    _content_tag_cache: str = field(init=False, repr=False, compare=False)
    _symbol_to_index_cache: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.size not in PROFILE_SIZES:
            raise ValidationError("receiver profile size was not predeclared")
        if self.training_sha256 != EXPECTED_TRAIN_SHA256:
            raise ValidationError("receiver profile training digest is not frozen")
        if not (
            len(self.entries) == len(self.symbols) == len(self.token_ids) == self.size
        ):
            raise ValidationError("receiver profile arrays do not match the declared size")
        if self.entries[:256] != tuple(bytes([value]) for value in range(256)):
            raise ValidationError("receiver profile lost complete byte fallback")
        if len(set(self.entries)) != self.size or any(
            not entry or len(entry) > MAX_ENTRY_BYTES for entry in self.entries
        ):
            raise ValidationError("receiver profile byte entries are invalid")
        if len(set(self.symbols)) != self.size or len(set(self.token_ids)) != self.size:
            raise ValidationError("receiver profile alphabet is not unique")
        if not all(_passes_prompt_risk_filter(symbol) for symbol in self.symbols):
            raise ValidationError("receiver profile contains an unsafe boundary symbol")
        for symbol, token_id in zip(self.symbols, self.token_ids, strict=True):
            if type(token_id) is not int or not 0 <= token_id < self.receiver.vocabulary_size:
                raise ValidationError("receiver profile token ID is outside the vocabulary")
            if self.receiver.encode_ids(symbol) != [token_id]:
                raise ValidationError("receiver symbol is not its declared isolated token")
        capsule = encode_profile_capsule(self)
        sha256 = hashlib.sha256(capsule).hexdigest()
        content_tag = _b64url(bytes.fromhex(sha256)[:PROFILE_TAG_BYTES])
        if len(content_tag) != 16:
            raise RuntimeError("receiver profile tag width changed")
        object.__setattr__(self, "_capsule_cache", capsule)
        object.__setattr__(self, "_sha256_cache", sha256)
        object.__setattr__(self, "_content_tag_cache", content_tag)
        object.__setattr__(
            self,
            "_symbol_to_index_cache",
            {symbol: index for index, symbol in enumerate(self.symbols)},
        )

    @property
    def capsule(self) -> bytes:
        return self._capsule_cache

    @property
    def sha256(self) -> str:
        return self._sha256_cache

    @property
    def content_tag(self) -> str:
        return self._content_tag_cache

    @property
    def symbol_to_index(self) -> Mapping[str, int]:
        return self._symbol_to_index_cache


@dataclass(frozen=True)
class ProfileSet:
    receivers: tuple[ReceiverTokenizer, ...]
    profiles: Mapping[str, Mapping[int, ReceiverProfile]]
    entries: tuple[bytes, ...]
    training_seconds: float


def _entry_usage(frames: Sequence[bytes], entries: tuple[bytes, ...]) -> Counter[int]:
    usage: Counter[int] = Counter()
    for frame in frames:
        usage.update(optimal_indices(frame, entries))
    return usage


def derive_profiles(
    training_messages: Sequence[Mapping[str, Any]],
    receivers: Sequence[ReceiverTokenizer],
) -> ProfileSet:
    """Derive and freeze all twelve profiles before any evaluation input."""

    start = time.perf_counter()
    frames = _training_frames(training_messages)
    entries = train_byte_entries(training_messages)
    entry_digest = hashlib.sha256(
        b"".join(_uvarint(len(entry)) + entry for entry in entries)
    ).hexdigest()
    if entry_digest != EXPECTED_BYTE_ENTRY_SHA256:
        raise RuntimeError("frozen byte-entry digest changed")
    by_receiver: dict[str, dict[int, ReceiverProfile]] = {}
    for receiver in receivers:
        if len(receiver.symbol_candidates) < MAX_PROFILE_SYMBOLS:
            raise RuntimeError("receiver lacks the requested safe alphabet")
        by_receiver[receiver.key] = {}
        for size in PROFILE_SIZES:
            selected_entries = entries[:size]
            usage = _entry_usage(frames, selected_entries)
            entry_order = sorted(
                range(size), key=lambda index: (-usage[index], index)
            )
            candidates = receiver.symbol_candidates[:size]
            symbols: list[str | None] = [None] * size
            token_ids: list[int | None] = [None] * size
            for entry_index, (symbol, token_id) in zip(
                entry_order, candidates, strict=True
            ):
                symbols[entry_index] = symbol
                token_ids[entry_index] = token_id
            profile = ReceiverProfile(
                receiver,
                size,
                EXPECTED_TRAIN_SHA256,
                selected_entries,
                tuple(value for value in symbols if value is not None),
                tuple(value for value in token_ids if value is not None),
            )
            verify_profile_concatenation(profile)
            expected = EXPECTED_PROFILE_SHA256.get(receiver.key, {}).get(size)
            if expected is None or profile.sha256 != expected:
                raise RuntimeError(
                    f"frozen receiver profile changed: {receiver.key}/{size}"
                )
            by_receiver[receiver.key][size] = profile
    return ProfileSet(
        tuple(receivers),
        by_receiver,
        entries,
        time.perf_counter() - start,
    )


def verify_profile_concatenation(profile: ReceiverProfile) -> int:
    """Verify isolated, repeated, long-order, and unique text segmentation."""

    for symbol, token_id in zip(profile.symbols, profile.token_ids, strict=True):
        if profile.receiver.encode_ids(symbol + symbol) != [token_id, token_id]:
            raise ValidationError("receiver symbol is unstable when repeated")
    indexed = tuple(zip(profile.symbols, profile.token_ids, strict=True))
    orders = (
        indexed,
        tuple(reversed(indexed)),
        indexed[::2] + indexed[1::2],
        indexed + indexed,
    )
    trials = 0
    for values in orders:
        text = "".join(symbol for symbol, _token_id in values)
        expected = [token_id for _symbol, token_id in values]
        if profile.receiver.encode_ids(text) != expected:
            raise ValidationError("profile alphabet changes under long concatenation")
        # The header is at the beginning of the complete transport, so its
        # standalone IDs are the exact expected prefix.  The trailer may have
        # beginning-of-string behavior under a metaspace tokenizer; we only
        # require it not to rewrite the final payload token.
        header = SURFACE_PREFIX + profile.content_tag + ":"
        framed = header + text + "~AAAAAAAAAAA"
        expected_prefix = profile.receiver.encode_ids(header) + expected
        if profile.receiver.encode_ids(framed)[: len(expected_prefix)] != expected_prefix:
            raise ValidationError("profile payload changes at a framing boundary")
        parsed = tuple(match.group(0) for match in re.finditer(r" [A-Za-z0-9]+", text))
        if "".join(parsed) != text or parsed != tuple(symbol for symbol, _ in values):
            raise ValidationError("profile alphabet is not uniquely space-segmented")
        trials += len(values)
    return trials


def encode_profile_capsule(profile: ReceiverProfile) -> bytes:
    body = bytearray(PROFILE_MAGIC)
    body += _encode_text(FORMAT)
    body += _encode_text(DERIVATION_ALGORITHM)
    body += _encode_text(CANONICAL_ENCODING_POLICY)
    body += _encode_text(INTEGRITY_POLICY)
    body += _encode_text(SAFETY_POLICY)
    body += bytes.fromhex(PROMPT_RISK_DENYLIST_SHA256)
    body += _encode_text(MODEL_EXPOSURE_POLICY)
    body += _encode_text(unicodedata.unidata_version)
    body += _encode_text(profile.receiver.key)
    body += _encode_text(profile.receiver.implementation)
    body += _uvarint(profile.receiver.vocabulary_size)
    body += bytes.fromhex(profile.receiver.fingerprint)
    body += bytes.fromhex(profile.training_sha256)
    body += _V02_CAPSULE_SHA256
    body += DEFAULT_PROFILE.dictionary_id
    body += _uvarint(MAX_ENTRY_BYTES)
    body += _uvarint(MAX_FRAME_BYTES)
    body += _uvarint(MAX_PAYLOAD_SYMBOLS)
    body += _uvarint(MAX_SURFACE_UTF8_BYTES)
    body += _uvarint(profile.size)
    for symbol, token_id, entry in zip(
        profile.symbols, profile.token_ids, profile.entries, strict=True
    ):
        body += _encode_text(symbol)
        body += _uvarint(token_id)
        body += _uvarint(len(entry)) + entry
    checksum = hashlib.sha256(_PROFILE_CAPSULE_DOMAIN + body).digest()[:16]
    capsule = bytes(body) + checksum
    if len(capsule) > MAX_PROFILE_CAPSULE_BYTES:
        raise ValidationError("receiver profile capsule exceeds its size bound")
    return capsule


def decode_profile_capsule(
    capsule: bytes, receiver: ReceiverTokenizer
) -> ReceiverProfile:
    if not isinstance(capsule, bytes) or len(capsule) > MAX_PROFILE_CAPSULE_BYTES:
        raise DecodeError("receiver profile capsule type or size is invalid")
    minimum = len(PROFILE_MAGIC) + 16 + 32 * 3 + 8
    if len(capsule) < minimum:
        raise DecodeError("receiver profile capsule is truncated")
    body, supplied = capsule[:-16], capsule[-16:]
    expected = hashlib.sha256(_PROFILE_CAPSULE_DOMAIN + body).digest()[:16]
    if not hmac.compare_digest(supplied, expected):
        raise DecodeError("receiver profile capsule checksum mismatch")
    reader = _Reader(body)
    if reader.read(len(PROFILE_MAGIC)) != PROFILE_MAGIC:
        raise DecodeError("unknown receiver profile capsule format")
    if reader.text(maximum=128) != FORMAT:
        raise DecodeError("receiver profile format identifier changed")
    if reader.text(maximum=128) != DERIVATION_ALGORITHM:
        raise DecodeError("receiver profile derivation algorithm changed")
    if reader.text(maximum=128) != CANONICAL_ENCODING_POLICY:
        raise DecodeError("receiver profile canonical encoding policy changed")
    if reader.text(maximum=128) != INTEGRITY_POLICY:
        raise DecodeError("receiver profile integrity policy changed")
    if reader.text(maximum=128) != SAFETY_POLICY:
        raise DecodeError("receiver profile safety policy changed")
    if reader.read(32).hex() != PROMPT_RISK_DENYLIST_SHA256:
        raise DecodeError("receiver profile prompt-risk denylist changed")
    if reader.text(maximum=128) != MODEL_EXPOSURE_POLICY:
        raise DecodeError("receiver profile model-exposure policy changed")
    if reader.text(maximum=32) != unicodedata.unidata_version:
        raise DecodeError("receiver profile Unicode database changed")
    if reader.text(maximum=128) != receiver.key:
        raise DecodeError("receiver profile tokenizer key mismatch")
    if reader.text(maximum=256) != receiver.implementation:
        raise DecodeError("receiver profile tokenizer implementation changed")
    if reader.uvarint() != receiver.vocabulary_size:
        raise DecodeError("receiver profile tokenizer vocabulary size changed")
    if reader.read(32).hex() != receiver.fingerprint:
        raise DecodeError("receiver profile tokenizer fingerprint mismatch")
    training_sha256 = reader.read(32).hex()
    if reader.read(32) != _V02_CAPSULE_SHA256:
        raise DecodeError("receiver profile base v0.2 profile mismatch")
    if reader.read(8) != DEFAULT_PROFILE.dictionary_id:
        raise DecodeError("receiver profile base dictionary mismatch")
    if reader.uvarint() != MAX_ENTRY_BYTES:
        raise DecodeError("receiver profile entry expansion bound changed")
    if reader.uvarint() != MAX_FRAME_BYTES:
        raise DecodeError("receiver profile frame expansion bound changed")
    if reader.uvarint() != MAX_PAYLOAD_SYMBOLS:
        raise DecodeError("receiver profile payload symbol bound changed")
    if reader.uvarint() != MAX_SURFACE_UTF8_BYTES:
        raise DecodeError("receiver profile surface text bound changed")
    size = reader.uvarint()
    if size not in PROFILE_SIZES:
        raise DecodeError("receiver profile symbol count was not predeclared")
    symbols: list[str] = []
    token_ids: list[int] = []
    entries: list[bytes] = []
    for _ in range(size):
        symbol = reader.text(maximum=MAX_SYMBOL_UTF8_BYTES)
        token_id = reader.uvarint()
        if token_id >= receiver.vocabulary_size:
            raise DecodeError("receiver profile token ID is outside the vocabulary")
        entry_size = reader.uvarint()
        if not 1 <= entry_size <= MAX_ENTRY_BYTES:
            raise DecodeError("receiver profile entry expansion is outside its bound")
        symbols.append(symbol)
        token_ids.append(token_id)
        entries.append(reader.read(entry_size))
    reader.end()
    try:
        result = ReceiverProfile(
            receiver,
            size,
            training_sha256,
            tuple(entries),
            tuple(symbols),
            tuple(token_ids),
        )
        verify_profile_concatenation(result)
    except ValidationError as exc:
        raise DecodeError(str(exc)) from exc
    if encode_profile_capsule(result) != capsule:
        raise DecodeError("receiver profile capsule is not canonical")
    frozen = EXPECTED_PROFILE_SHA256.get(receiver.key, {}).get(size)
    if frozen is None or result.sha256 != frozen:
        raise DecodeError("receiver profile capsule is not the frozen negotiated profile")
    return result


def encode_profile_capsule_text(profile: ReceiverProfile) -> str:
    return CAPSULE_TEXT_PREFIX + _b64url(profile.capsule)


def decode_profile_capsule_text(
    text: str, receiver: ReceiverTokenizer
) -> ReceiverProfile:
    if not isinstance(text, str) or not text.startswith(CAPSULE_TEXT_PREFIX):
        raise DecodeError("unknown receiver profile text capsule")
    if _decoded_text_utf8_size(text, "receiver profile text capsule") > 2 * MAX_PROFILE_CAPSULE_BYTES:
        raise DecodeError("receiver profile text capsule exceeds its bound")
    result = decode_profile_capsule(_unb64url(text[len(CAPSULE_TEXT_PREFIX) :]), receiver)
    if encode_profile_capsule_text(result) != text:
        raise DecodeError("receiver profile text capsule is not canonical")
    return result


def _checksum(profile: ReceiverProfile, frame: bytes) -> str:
    digest = hashlib.blake2s(
        _SURFACE_DOMAIN + bytes.fromhex(profile.sha256) + frame,
        digest_size=CHECKSUM_BYTES,
    ).digest()
    result = _b64url(digest)
    if len(result) != CHECKSUM_CHARACTERS:
        raise RuntimeError("surface checksum width changed")
    return result


def _surface_from_indices(
    frame: bytes, indices: Sequence[int], profile: ReceiverProfile
) -> str:
    if len(indices) > MAX_PAYLOAD_SYMBOLS:
        raise ValidationError("receiver surface payload exceeds the symbol bound")
    try:
        payload = "".join(profile.symbols[index] for index in indices)
        expected_ids = [profile.token_ids[index] for index in indices]
    except (IndexError, TypeError) as exc:
        raise ValidationError("receiver surface uses a codebook index outside the profile") from exc
    if profile.receiver.encode_ids(payload) != expected_ids:
        raise ValidationError("payload tokenization changed under concatenation")
    header = SURFACE_PREFIX + profile.content_tag + ":"
    trailer = "~" + _checksum(profile, frame)
    surface = header + payload + trailer
    expected_prefix = profile.receiver.encode_ids(header) + expected_ids
    if profile.receiver.encode_ids(surface)[: len(expected_prefix)] != expected_prefix:
        raise ValidationError("payload tokenization changed at a framing boundary")
    if len(surface.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise ValidationError("receiver surface exceeds the UTF-8 bound")
    return surface


def _require_frozen_profile(profile: ReceiverProfile, *, decoding: bool) -> None:
    expected = EXPECTED_PROFILE_SHA256.get(profile.receiver.key, {}).get(profile.size)
    if expected is None or profile.sha256 != expected:
        error = DecodeError if decoding else ValidationError
        raise error("receiver profile is not one of the twelve frozen negotiated profiles")


def encode_message(
    message: Mapping[str, Any], profile: ReceiverProfile
) -> str:
    _require_frozen_profile(profile, decoding=False)
    frame = encode_v02(message)
    return _surface_from_indices(frame, optimal_indices(frame, profile.entries), profile)


def _split_surface(surface: str, profile: ReceiverProfile) -> tuple[str, str]:
    if not isinstance(surface, str):
        raise DecodeError("receiver surface must be text")
    if _decoded_text_utf8_size(surface, "receiver surface") > MAX_SURFACE_UTF8_BYTES:
        raise DecodeError("receiver surface exceeds the UTF-8 bound")
    header = SURFACE_PREFIX + profile.content_tag + ":"
    if not surface.startswith(header):
        raise DecodeError("receiver surface profile binding mismatch")
    payload_and_checksum = surface[len(header) :]
    payload, separator, checksum = payload_and_checksum.rpartition("~")
    if not separator or _CHECKSUM.fullmatch(checksum) is None:
        raise DecodeError("receiver surface checksum field is malformed")
    if _PAYLOAD.fullmatch(payload) is None:
        raise DecodeError("receiver surface payload grammar is malformed")
    if payload.count(" ") > MAX_PAYLOAD_SYMBOLS:
        raise DecodeError("receiver surface payload exceeds the symbol bound")
    return payload, checksum


def decode_message(surface: str, profile: ReceiverProfile) -> dict[str, Any]:
    _require_frozen_profile(profile, decoding=True)
    payload, supplied_checksum = _split_surface(surface, profile)
    symbols = tuple(match.group(0) for match in re.finditer(r" [A-Za-z0-9]+", payload))
    if not symbols or len(symbols) > MAX_PAYLOAD_SYMBOLS or "".join(symbols) != payload:
        raise DecodeError("receiver surface payload segmentation is invalid")
    symbol_to_index = profile.symbol_to_index
    indices: list[int] = []
    expected_ids: list[int] = []
    frame = bytearray()
    for symbol in symbols:
        index = symbol_to_index.get(symbol)
        if index is None:
            raise DecodeError("receiver surface contains an unknown profile symbol")
        indices.append(index)
        expected_ids.append(profile.token_ids[index])
        expansion = profile.entries[index]
        if len(frame) + len(expansion) > MAX_FRAME_BYTES:
            raise DecodeError("receiver surface expansion exceeds the frame bound")
        frame += expansion
    if profile.receiver.encode_ids(payload) != expected_ids:
        raise DecodeError("receiver surface token IDs do not match the profile")
    header = SURFACE_PREFIX + profile.content_tag + ":"
    expected_prefix = profile.receiver.encode_ids(header) + expected_ids
    if profile.receiver.encode_ids(surface)[: len(expected_prefix)] != expected_prefix:
        raise DecodeError("receiver surface changed tokenization at a framing boundary")
    expected_checksum = _checksum(profile, bytes(frame))
    if not hmac.compare_digest(supplied_checksum, expected_checksum):
        raise DecodeError("receiver surface checksum mismatch")
    message = decode_v02(bytes(frame))
    canonical_indices = optimal_indices(bytes(frame), profile.entries)
    canonical_payload = "".join(profile.symbols[index] for index in canonical_indices)
    canonical_surface = header + canonical_payload + "~" + expected_checksum
    if tuple(indices) != canonical_indices or canonical_surface != surface:
        raise DecodeError("receiver surface is valid but non-canonical")
    return message


@dataclass(frozen=True)
class Candidate:
    mode: str
    text: str
    tokens: int
    utf8_bytes: int
    profile_size: int | None


@dataclass(frozen=True)
class Selection:
    candidate: Candidate
    baseline: Candidate
    candidates: Mapping[str, Candidate]


@dataclass(frozen=True)
class Prepared:
    message: Mapping[str, Any]
    receiver_binding: tuple[str, str, int, str]
    v06: V06PreparedMessage
    v07_texts: Mapping[int, str]
    v07_ineligible: Mapping[int, str]


def prepare_message(
    message: Mapping[str, Any], alias_profile: Any, profiles: Mapping[int, ReceiverProfile]
) -> Prepared:
    if tuple(sorted(profiles)) != PROFILE_SIZES:
        raise ValidationError("prepared message requires all predeclared profile sizes")
    receiver_bindings = {profile.receiver.binding for profile in profiles.values()}
    if len(receiver_bindings) != 1:
        raise ValidationError("prepared message profiles do not share one receiver")
    receiver_binding = next(iter(receiver_bindings))
    if any(size != profile.size for size, profile in profiles.items()):
        raise ValidationError("prepared message profile size binding changed")
    canonical = normalize_message(message)
    v07_texts: dict[int, str] = {}
    v07_ineligible: dict[int, str] = {}
    for size, profile in profiles.items():
        try:
            v07_texts[size] = encode_message(canonical, profile)
        except ValidationError as exc:
            v07_ineligible[size] = str(exc)
    return Prepared(
        canonical,
        receiver_binding,
        prepare_v06(canonical, alias_profile),
        v07_texts,
        v07_ineligible,
    )


def _candidate(mode: str, text: str, receiver: ReceiverTokenizer, size: int | None) -> Candidate:
    return Candidate(mode, text, receiver.count(text), len(text.encode("utf-8")), size)


def select_prepared(
    prepared: Prepared,
    receiver: ReceiverTokenizer,
    *,
    allow_structured_bundle: bool = True,
    allow_symbolic: bool = True,
    allow_optimized: bool = True,
    active_v07_sizes: Sequence[int] = PROFILE_SIZES,
) -> Selection:
    if prepared.receiver_binding != receiver.binding:
        raise ValidationError("prepared message receiver binding mismatch")
    v06 = select_v06_prepared(
        prepared.v06,
        _as_tokenizer_profile(receiver),
        allow_structured_bundle=allow_structured_bundle,
        allow_symbolic=allow_symbolic,
        allow_optimized=allow_optimized,
    ).candidate
    baseline = _candidate("v06", v06.text, receiver, None)
    candidates: dict[str, Candidate] = {"v06": baseline}
    for size in active_v07_sizes:
        if size not in PROFILE_SIZES:
            raise ValidationError("selector received a non-predeclared v0.7 size")
        text = prepared.v07_texts.get(size)
        if text is not None:
            candidates[f"v07_{size}"] = _candidate(
                f"v07_{size}", text, receiver, size
            )
    rank = {"v06": 0, **{f"v07_{size}": index + 1 for index, size in enumerate(PROFILE_SIZES)}}
    selected = min(
        candidates.values(), key=lambda item: (item.tokens, rank[item.mode], item.text)
    )
    if selected.tokens > baseline.tokens:
        raise RuntimeError("receiver selector regressed against the complete v0.6 candidate")
    return Selection(selected, baseline, candidates)


def _as_tokenizer_profile(receiver: ReceiverTokenizer) -> TokenizerProfile:
    return TokenizerProfile(
        receiver.key,
        receiver.display_name,
        receiver.implementation,
        receiver.vocabulary_size,
        receiver.fingerprint,
        receiver.count,
    )


def select_message(
    message: Mapping[str, Any],
    alias_profile: Any,
    receiver: ReceiverTokenizer,
    profiles: Mapping[int, ReceiverProfile],
) -> Selection:
    return select_prepared(prepare_message(message, alias_profile, profiles), receiver)


def decode_selected(
    text: str, alias_profile: Any, profiles: Mapping[int, ReceiverProfile]
) -> dict[str, Any]:
    if not isinstance(text, str):
        raise DecodeError("selected surface must be text")
    if text.startswith(SURFACE_PREFIX):
        tag_end = len(SURFACE_PREFIX) + 16
        if len(text) <= tag_end or text[tag_end] != ":":
            raise DecodeError("selected v0.7 surface header is malformed")
        tag = text[len(SURFACE_PREFIX) : tag_end]
        if _PROFILE_TAG.fullmatch(tag) is None:
            raise DecodeError("selected v0.7 surface profile tag is malformed")
        matching = [profile for profile in profiles.values() if profile.content_tag == tag]
        if len(matching) != 1:
            raise DecodeError("selected v0.7 profile tag is unknown or colliding")
        return decode_message(text, matching[0])
    return decode_v06_selected(text, alias_profile)


@dataclass(frozen=True)
class ColdOption:
    old_structured: bool
    symbolic: bool
    optimized: bool
    active_v07_sizes: tuple[int, ...]
    cold_tokens: int
    cold_bytes: int
    message_tokens: int
    total_tokens: int
    choices: tuple[Candidate, ...]


@dataclass(frozen=True)
class ColdPlan:
    selected: ColdOption
    options: tuple[ColdOption, ...]
    v06_baseline_total: int


def _artifact_costs(
    receiver: ReceiverTokenizer,
    alias_profile: Any,
    profiles: Mapping[int, ReceiverProfile],
) -> Mapping[str, tuple[int, int]]:
    static_profile = base64.b64encode(encode_v02_capsule(DEFAULT_PROFILE)).decode("ascii")
    old_codebook = encode_v04_codebook_capsule_text(holdout_codebook())
    texts = {
        "static_profile": static_profile,
        "old_codebook": old_codebook,
        "symbolic_grammar": existing_grammar_capsule(),
        "optimized_grammar": optimized_grammar_capsule(),
        "optimized_profile": v06_profile_capsule(alias_profile),
        **{
            f"v07_{size}": encode_profile_capsule_text(profile)
            for size, profile in profiles.items()
        },
    }
    return {
        key: (receiver.count(text), len(text.encode("utf-8")))
        for key, text in texts.items()
    }


def plan_cold_session(
    prepared_messages: Sequence[Prepared],
    receiver: ReceiverTokenizer,
    alias_profile: Any,
    profiles: Mapping[int, ReceiverProfile],
) -> ColdPlan:
    """Enumerate all old and new activation states, charging shared state once."""

    if any(item.receiver_binding != receiver.binding for item in prepared_messages):
        raise ValidationError("cold planner prepared receiver binding mismatch")
    if {profile.receiver.binding for profile in profiles.values()} != {receiver.binding}:
        raise ValidationError("cold planner profile receiver binding mismatch")
    costs = _artifact_costs(receiver, alias_profile, profiles)
    tokenizer_profile = _as_tokenizer_profile(receiver)
    v06_choices: dict[tuple[bool, bool, bool], tuple[Candidate, ...]] = {}
    for old_structured in (False, True):
        for symbolic in (False, True):
            for optimized in (False, True):
                values: list[Candidate] = []
                for prepared in prepared_messages:
                    selected = select_v06_prepared(
                        prepared.v06,
                        tokenizer_profile,
                        allow_structured_bundle=old_structured,
                        allow_symbolic=symbolic,
                        allow_optimized=optimized,
                    ).candidate
                    values.append(_candidate("v06", selected.text, receiver, None))
                v06_choices[(old_structured, symbolic, optimized)] = tuple(values)
    v07_choices: Mapping[int, tuple[Candidate | None, ...]] = {
        size: tuple(
            _candidate(f"v07_{size}", prepared.v07_texts[size], receiver, size)
            if size in prepared.v07_texts
            else None
            for prepared in prepared_messages
        )
        for size in PROFILE_SIZES
    }
    rank = {"v06": 0, **{f"v07_{size}": index + 1 for index, size in enumerate(PROFILE_SIZES)}}
    options: list[ColdOption] = []
    for old_structured in (False, True):
        for symbolic in (False, True):
            for optimized in (False, True):
                for mask in range(1 << len(PROFILE_SIZES)):
                    active = tuple(
                        size
                        for index, size in enumerate(PROFILE_SIZES)
                        if mask & (1 << index)
                    )
                    baseline_values = v06_choices[(old_structured, symbolic, optimized)]
                    choices_list: list[Candidate] = []
                    for message_index, baseline in enumerate(baseline_values):
                        candidates = [baseline]
                        candidates.extend(
                            candidate
                            for size in active
                            if (candidate := v07_choices[size][message_index]) is not None
                        )
                        choices_list.append(
                            min(
                                candidates,
                                key=lambda item: (item.tokens, rank[item.mode], item.text),
                            )
                        )
                    choices = tuple(choices_list)
                    needs_static = old_structured or bool(active)
                    artifact_names = []
                    if needs_static:
                        artifact_names.append("static_profile")
                    if old_structured:
                        artifact_names.append("old_codebook")
                    if symbolic:
                        artifact_names.append("symbolic_grammar")
                    if optimized:
                        artifact_names.extend(("optimized_grammar", "optimized_profile"))
                    artifact_names.extend(f"v07_{size}" for size in active)
                    cold_tokens = sum(costs[name][0] for name in artifact_names)
                    cold_bytes = sum(costs[name][1] for name in artifact_names)
                    message_tokens = sum(choice.tokens for choice in choices)
                    options.append(
                        ColdOption(
                            old_structured,
                            symbolic,
                            optimized,
                            active,
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
            bool(item.active_v07_sizes),
            item.cold_tokens,
            item.old_structured,
            item.symbolic,
            item.optimized,
            item.active_v07_sizes,
        )
    )
    v06_only = [item for item in options if not item.active_v07_sizes]
    v06_baseline = min(item.total_tokens for item in v06_only)
    selected = options[0]
    if selected.total_tokens > v06_baseline:
        raise RuntimeError("cold receiver planner regressed against v0.6")
    # Cross-check the legacy planner rather than silently redefining its cost.
    legacy = plan_v06_cold_session(
        [item.v06 for item in prepared_messages], tokenizer_profile, alias_profile
    )
    if legacy.selected.total_tokens != v06_baseline:
        raise RuntimeError("v0.7 cold planner does not reproduce the v0.6 baseline")
    return ColdPlan(selected, tuple(options), v06_baseline)


def strict_break_even(
    cold: int, baseline_total: int, candidate_total: int, message_count: int
) -> int | None:
    saving = baseline_total - candidate_total
    if saving <= 0:
        return None
    return cold * message_count // saving + 1


@dataclass(frozen=True)
class Study:
    profile_set: ProfileSet
    datasets: Mapping[str, tuple[dict[str, Any], ...]]
    alias_profile: Any
    prepared: Mapping[str, Mapping[str, tuple[Prepared, ...]]]
    selections: Mapping[str, Mapping[str, tuple[Selection, ...]]]
    cold_plans: Mapping[str, Mapping[str, ColdPlan]]
    direct_exact: int
    direct_deterministic: int
    selected_exact: int
    selected_deterministic: int
    corruptions_attempted: int
    corruptions_rejected: int
    concatenation_trials: int


def _mutate_payload_symbol(
    text: str, profile: ReceiverProfile, seed: str
) -> str:
    payload, checksum = _split_surface(text, profile)
    symbols = [match.group(0) for match in re.finditer(r" [A-Za-z0-9]+", payload)]
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    position = int.from_bytes(digest[:8], "big") % len(symbols)
    current = profile.symbol_to_index[symbols[position]]
    replacement = (current + 1 + digest[8] % (profile.size - 1)) % profile.size
    symbols[position] = profile.symbols[replacement]
    return (
        SURFACE_PREFIX
        + profile.content_tag
        + ":"
        + "".join(symbols)
        + "~"
        + checksum
    )


def collect_study(asset_root: Path | None = None) -> Study:
    """Run deterministic measurement collection; latency is measured separately."""

    split = frozen_split()
    development = tuple(split.train)
    if corpus_digest(development) != EXPECTED_TRAIN_SHA256:
        raise RuntimeError("frozen development partition changed")
    receivers = load_receivers(asset_root)
    profile_set = derive_profiles(development, receivers)

    # The profiles above are now frozen.  Only now are evaluation partitions
    # attached to the study and encoded.
    datasets = {
        "development": development,
        "grouped_holdout": tuple(split.holdout),
        "out_of_domain": tuple(build_out_of_domain_corpus()),
    }
    expected_digests = {
        "development": EXPECTED_TRAIN_SHA256,
        "grouped_holdout": EXPECTED_HOLDOUT_SHA256,
        "out_of_domain": EXPECTED_OOD_SHA256,
    }
    for name, messages in datasets.items():
        if corpus_digest(messages) != expected_digests[name]:
            raise RuntimeError(f"frozen {name} corpus changed")

    alias_profile = derive_alias_profile(development)
    prepared: dict[str, dict[str, tuple[Prepared, ...]]] = {}
    selections: dict[str, dict[str, tuple[Selection, ...]]] = {}
    cold_plans: dict[str, dict[str, ColdPlan]] = {}
    direct_exact = direct_deterministic = 0
    selected_exact = selected_deterministic = 0
    corruptions_attempted = corruptions_rejected = 0
    concatenation_trials = 0
    for receiver in receivers:
        for profile in profile_set.profiles[receiver.key].values():
            concatenation_trials += verify_profile_concatenation(profile)
    for dataset, messages in datasets.items():
        prepared[dataset] = {}
        selections[dataset] = {}
        cold_plans[dataset] = {}
        for receiver in receivers:
            receiver_profiles = profile_set.profiles[receiver.key]
            values = tuple(
                prepare_message(message, alias_profile, receiver_profiles)
                for message in messages
            )
            if any(item.v07_ineligible for item in values):
                raise RuntimeError("a frozen benchmark message lost a v0.7 candidate")
            chosen = tuple(select_prepared(item, receiver) for item in values)
            prepared[dataset][receiver.key] = values
            selections[dataset][receiver.key] = chosen
            cold_plans[dataset][receiver.key] = plan_cold_session(
                values, receiver, alias_profile, receiver_profiles
            )
            for index, (item, selection) in enumerate(zip(values, chosen, strict=True)):
                selected_exact += (
                    decode_selected(selection.candidate.text, alias_profile, receiver_profiles)
                    == item.message
                )
                selected_deterministic += select_prepared(item, receiver) == selection
                if selection.candidate.tokens > selection.baseline.tokens:
                    raise RuntimeError("warm receiver guard regressed")
                for size, profile in receiver_profiles.items():
                    text = item.v07_texts[size]
                    direct_exact += decode_message(text, profile) == item.message
                    direct_deterministic += encode_message(item.message, profile) == text
                    mutated = _mutate_payload_symbol(
                        text, profile, f"{FORMAT}|{dataset}|{receiver.key}|{size}|{index}"
                    )
                    corruptions_attempted += 1
                    try:
                        decode_message(mutated, profile)
                    except (DecodeError, ValidationError, ValueError):
                        corruptions_rejected += 1
    study = Study(
        profile_set,
        datasets,
        alias_profile,
        prepared,
        selections,
        cold_plans,
        direct_exact,
        direct_deterministic,
        selected_exact,
        selected_deterministic,
        corruptions_attempted,
        corruptions_rejected,
        concatenation_trials,
    )
    message_receiver_trials = sum(len(values) for values in datasets.values()) * len(receivers)
    direct_trials = message_receiver_trials * len(PROFILE_SIZES)
    if (direct_exact, direct_deterministic) != (direct_trials, direct_trials):
        raise RuntimeError("direct v0.7 exactness or determinism postcondition failed")
    if (selected_exact, selected_deterministic) != (
        message_receiver_trials,
        message_receiver_trials,
    ):
        raise RuntimeError("guarded chooser exactness or determinism postcondition failed")
    if corruptions_rejected != corruptions_attempted or corruptions_attempted != direct_trials:
        raise RuntimeError("deterministic corruption rejection postcondition failed")
    observed = snapshot_sha256(study_snapshot(study))
    if EXPECTED_SNAPSHOT_SHA256 != "pending" and observed != EXPECTED_SNAPSHOT_SHA256:
        raise RuntimeError("frozen v0.7 study snapshot changed")
    return study


def _warm_metrics(
    study: Study, dataset: str, receiver: ReceiverTokenizer
) -> Mapping[str, Mapping[str, int]]:
    prepared = study.prepared[dataset][receiver.key]
    selections = study.selections[dataset][receiver.key]
    metrics: dict[str, dict[str, int]] = {}

    def total(values: Iterable[str]) -> dict[str, int]:
        texts = tuple(values)
        return {
            "tokens": sum(receiver.count(text) for text in texts),
            "bytes": sum(len(text.encode("utf-8")) for text in texts),
        }

    metrics["v04"] = total(item.v06.raw_texts["v04"] for item in prepared)
    v05 = tuple(
        selection.baseline
        for selection in (
            select_v06_prepared(item.v06, _as_tokenizer_profile(receiver))
            for item in prepared
        )
    )
    metrics["v05"] = {
        "tokens": sum(candidate.tokens for candidate in v05),
        "bytes": sum(candidate.utf8_bytes for candidate in v05),
    }
    metrics["v06"] = total(selection.baseline.text for selection in selections)
    for size in PROFILE_SIZES:
        metrics[f"v07_{size}"] = total(item.v07_texts[size] for item in prepared)
    metrics["guarded"] = total(selection.candidate.text for selection in selections)
    return metrics


def _comparison(
    candidates: Sequence[Candidate], baselines: Sequence[Candidate]
) -> Mapping[str, int | float]:
    improved = equal = regressed = 0
    worst_tokens = 0.0
    worst_bytes = 0.0
    token_saving = 0
    byte_saving = 0
    for candidate, baseline in zip(candidates, baselines, strict=True):
        delta = candidate.tokens - baseline.tokens
        token_saving += -delta
        byte_saving += baseline.utf8_bytes - candidate.utf8_bytes
        if delta < 0:
            improved += 1
        elif delta == 0:
            equal += 1
        else:
            regressed += 1
            worst_tokens = max(worst_tokens, 100.0 * delta / baseline.tokens)
        if candidate.utf8_bytes > baseline.utf8_bytes:
            worst_bytes = max(
                worst_bytes,
                100.0 * (candidate.utf8_bytes - baseline.utf8_bytes) / baseline.utf8_bytes,
            )
    return {
        "improved": improved,
        "equal": equal,
        "regressed": regressed,
        "tokens_saved": token_saving,
        "bytes_saved": byte_saving,
        "worst_token_regression_ppm": round(worst_tokens * 10_000),
        "worst_byte_regression_ppm": round(worst_bytes * 10_000),
    }


def study_snapshot(study: Study) -> Mapping[str, Any]:
    profile_data: dict[str, dict[str, Any]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    comparisons: dict[str, dict[str, Any]] = {}
    cold: dict[str, dict[str, Any]] = {}
    selected_digests: dict[str, dict[str, str]] = {}
    warm_mode_counts: dict[str, dict[str, Mapping[str, int]]] = {}
    regression_records: list[dict[str, Any]] = []
    receivers = {receiver.key: receiver for receiver in study.profile_set.receivers}
    entry_digest = hashlib.sha256(
        b"".join(_uvarint(len(entry)) + entry for entry in study.profile_set.entries)
    ).hexdigest()
    for receiver in study.profile_set.receivers:
        profile_data[receiver.key] = {
            "fingerprint": receiver.fingerprint,
            "safe_boundary_candidates": receiver.safe_boundary_candidate_count,
            "pre_filter_boundary_candidates": receiver.pre_filter_boundary_candidate_count,
            "prompt_risk_terms_removed": receiver.prompt_risk_terms_removed,
            "strict_scalar_candidates": receiver.strict_scalar_count,
            "profiles": {
                str(size): {
                    "sha256": profile.sha256,
                    "capsule_bytes": len(profile.capsule),
                    "capsule_text_bytes": len(encode_profile_capsule_text(profile).encode("utf-8")),
                    "capsule_tokens": receiver.count(encode_profile_capsule_text(profile)),
                    "alphabet_sha256": _sequence_digest(profile.symbols),
                }
                for size, profile in study.profile_set.profiles[receiver.key].items()
            },
        }
    for dataset in study.datasets:
        metrics[dataset] = {}
        comparisons[dataset] = {}
        cold[dataset] = {}
        selected_digests[dataset] = {}
        warm_mode_counts[dataset] = {}
        for key, receiver in receivers.items():
            metrics[dataset][key] = _warm_metrics(study, dataset, receiver)
            prepared = study.prepared[dataset][key]
            selected = study.selections[dataset][key]
            baselines = tuple(value.baseline for value in selected)
            comparisons[dataset][key] = {}
            for size in PROFILE_SIZES:
                raw_candidates = tuple(
                    _candidate(f"v07_{size}", item.v07_texts[size], receiver, size)
                    for item in prepared
                )
                comparisons[dataset][key][str(size)] = _comparison(
                    raw_candidates, baselines
                )
                for message_index, (candidate, baseline) in enumerate(
                    zip(raw_candidates, baselines, strict=True)
                ):
                    token_delta = candidate.tokens - baseline.tokens
                    byte_delta = candidate.utf8_bytes - baseline.utf8_bytes
                    if token_delta > 0 or byte_delta > 0:
                        regression_records.append(
                            {
                                "dataset": dataset,
                                "receiver": key,
                                "message_index": message_index,
                                "candidate": candidate.mode,
                                "baseline_tokens": baseline.tokens,
                                "candidate_tokens": candidate.tokens,
                                "token_delta": token_delta,
                                "baseline_bytes": baseline.utf8_bytes,
                                "candidate_bytes": candidate.utf8_bytes,
                                "byte_delta": byte_delta,
                            }
                        )
            comparisons[dataset][key]["guarded"] = _comparison(
                tuple(value.candidate for value in selected), baselines
            )
            for message_index, (value, baseline) in enumerate(
                zip(selected, baselines, strict=True)
            ):
                candidate = value.candidate
                token_delta = candidate.tokens - baseline.tokens
                byte_delta = candidate.utf8_bytes - baseline.utf8_bytes
                if token_delta > 0 or byte_delta > 0:
                    regression_records.append(
                        {
                            "dataset": dataset,
                            "receiver": key,
                            "message_index": message_index,
                            "candidate": "guarded",
                            "selected_mode": candidate.mode,
                            "baseline_tokens": baseline.tokens,
                            "candidate_tokens": candidate.tokens,
                            "token_delta": token_delta,
                            "baseline_bytes": baseline.utf8_bytes,
                            "candidate_bytes": candidate.utf8_bytes,
                            "byte_delta": byte_delta,
                        }
                    )
            plan = study.cold_plans[dataset][key]
            cold[dataset][key] = {
                "v06_baseline_total": plan.v06_baseline_total,
                "selected_total": plan.selected.total_tokens,
                "cold_tokens": plan.selected.cold_tokens,
                "cold_bytes": plan.selected.cold_bytes,
                "old_structured": plan.selected.old_structured,
                "symbolic": plan.selected.symbolic,
                "optimized": plan.selected.optimized,
                "active_v07_sizes": list(plan.selected.active_v07_sizes),
                "mode_counts": dict(sorted(Counter(choice.mode for choice in plan.selected.choices).items())),
            }
            selected_digests[dataset][key] = _sequence_digest(
                tuple(value.candidate.text for value in selected)
            )
            warm_mode_counts[dataset][key] = dict(
                sorted(Counter(value.candidate.mode for value in selected).items())
            )
    return {
        "format": FORMAT,
        "derivation_algorithm": DERIVATION_ALGORITHM,
        "safety_policy": SAFETY_POLICY,
        "model_exposure_policy": MODEL_EXPOSURE_POLICY,
        "unicode_version": unicodedata.unidata_version,
        "training_sha256": EXPECTED_TRAIN_SHA256,
        "byte_entry_sha256": entry_digest,
        "profiles": profile_data,
        "warm_metrics": metrics,
        "per_message": comparisons,
        "regression_records": regression_records,
        "cold": cold,
        "selected_digests": selected_digests,
        "warm_mode_counts": warm_mode_counts,
        "exact": {
            "direct": study.direct_exact,
            "selected": study.selected_exact,
        },
        "deterministic": {
            "direct": study.direct_deterministic,
            "selected": study.selected_deterministic,
        },
        "corruptions": {
            "attempted": study.corruptions_attempted,
            "rejected": study.corruptions_rejected,
        },
        "concatenation_trials": study.concatenation_trials,
    }


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _time_paths(
    encoders: Sequence[Callable[[], Any]],
    decoders: Sequence[Callable[[], Any]],
    *,
    repeats: int,
) -> Mapping[str, int]:
    encode_samples: list[int] = []
    decode_samples: list[int] = []
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            for operation in encoders:
                start = time.perf_counter_ns()
                operation()
                encode_samples.append(time.perf_counter_ns() - start)
            for operation in decoders:
                start = time.perf_counter_ns()
                operation()
                decode_samples.append(time.perf_counter_ns() - start)
    finally:
        if was_enabled:
            gc.enable()
    return {
        "encode_p50_ns": round(statistics.median(encode_samples)),
        "encode_p95_ns": _nearest(encode_samples, 0.95),
        "decode_p50_ns": round(statistics.median(decode_samples)),
        "decode_p95_ns": _nearest(decode_samples, 0.95),
    }


def measure_latency(study: Study, *, repeats: int = 1) -> Mapping[str, Any]:
    if repeats < 1:
        raise ValidationError("latency repeats must be positive")
    combined_messages = tuple(
        message for values in study.datasets.values() for message in values
    )
    result: dict[str, Any] = {"direct": {}, "chooser": {}}
    for receiver in study.profile_set.receivers:
        profiles = study.profile_set.profiles[receiver.key]
        result["direct"][receiver.key] = {}
        for size, profile in profiles.items():
            texts = tuple(encode_message(message, profile) for message in combined_messages)
            result["direct"][receiver.key][str(size)] = _time_paths(
                tuple(lambda message=message, profile=profile: encode_message(message, profile) for message in combined_messages),
                tuple(lambda text=text, profile=profile: decode_message(text, profile) for text in texts),
                repeats=repeats,
            )
        guarded = tuple(
            select_message(message, study.alias_profile, receiver, profiles)
            for message in combined_messages
        )
        v06_texts = tuple(
            select_v06_message(message, study.alias_profile, _as_tokenizer_profile(receiver)).candidate.text
            for message in combined_messages
        )
        result["chooser"][receiver.key] = {
            "v06": _time_paths(
                tuple(
                    lambda message=message, receiver=receiver: select_v06_message(
                        message, study.alias_profile, _as_tokenizer_profile(receiver)
                    )
                    for message in combined_messages
                ),
                tuple(
                    lambda text=text: decode_v06_selected(text, study.alias_profile)
                    for text in v06_texts
                ),
                repeats=repeats,
            ),
            "guarded_v07": _time_paths(
                tuple(
                    lambda message=message, receiver=receiver, profiles=profiles: select_message(
                        message, study.alias_profile, receiver, profiles
                    )
                    for message in combined_messages
                ),
                tuple(
                    lambda value=value, profiles=profiles: decode_selected(
                        value.candidate.text, study.alias_profile, profiles
                    )
                    for value in guarded
                ),
                repeats=repeats,
            ),
        }
    return result


def _pct_saved(candidate: int, baseline: int) -> str:
    return f"{100.0 * (1.0 - candidate / baseline):+.2f}%"


def _break_text(value: int | None) -> str:
    return "never on mean" if value is None else f"{value:,}"


def _local_source_sha256(name: str) -> str:
    path = Path(__file__).resolve().with_name(name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_report(study: Study, latency: Mapping[str, Any]) -> str:
    snapshot = study_snapshot(study)
    receivers = {receiver.key: receiver for receiver in study.profile_set.receivers}
    total_pairs = sum(len(messages) for messages in study.datasets.values()) * len(receivers)
    direct_trials = total_pairs * len(PROFILE_SIZES)
    guarded_improvement = {dataset: 0 for dataset in study.datasets}
    guarded_regressions = 0
    for dataset in study.datasets:
        for key in receivers:
            comparison = snapshot["per_message"][dataset][key]["guarded"]
            guarded_improvement[dataset] += int(comparison["tokens_saved"])
            guarded_regressions += int(comparison["regressed"])
    activated_cold_plans = sum(
        bool(study.cold_plans[dataset][key].selected.active_v07_sizes)
        for dataset in study.datasets
        for key in receivers
    )
    lines = [
        "# Receiver-negotiated token surface v0.7",
        "",
        "## Result",
        "",
        f"All twelve predeclared receiver profiles were derived from the frozen {len(study.datasets['development']):,}-message development partition before the unchanged holdout or out-of-domain sets were evaluated. Exact decode and canonical re-encoding passed for **{study.direct_exact:,}/{direct_trials:,}** and **{study.direct_deterministic:,}/{direct_trials:,}** direct receiver/profile/message cases. The guarded chooser had **{guarded_regressions}** warm token regressions against the complete v0.6 candidate across **{total_pairs:,}** message/receiver pairs. It saved **{guarded_improvement['development']:,}** tokens on development and **{guarded_improvement['grouped_holdout']:,}** on grouped holdout, but **{guarded_improvement['out_of_domain']:,}** on OOD, where every choice remained v0.6.",
        "",
        f"Cold transfer was unfavorable at the evaluated session lengths: v0.7 was activated in **{activated_cold_plans}/12** exact known-session cold plans, so every cold result retained the existing v0.6 plan.",
        "",
        f"Deterministic payload corruptions were rejected in **{study.corruptions_rejected:,}/{study.corruptions_attempted:,}** trials. Alphabet isolation, repetition, long forward/reverse/permuted concatenation, and actual payload token-ID checks covered **{study.concatenation_trials:,}** declared symbol positions in addition to every encoded message.",
        "",
        "These are serialization measurements over already-typed messages. No language model, network service, paid API, or external side effect was used. The experiment does not measure comprehension, task success, repair behavior, sender generation, energy, adoption, native model support, or state-of-the-art performance.",
        "",
        "## Why the symbol definition changed",
        "",
        "A visible single-Unicode-code-point alphabet cannot satisfy all requested sizes. The strict isolated candidate count is shown below. The implemented experimental symbol is instead one canonical ASCII space followed by a nonempty ASCII alphanumeric body. It is a vocabulary token, contains no internal whitespace or delimiter, is uniquely segmented at spaces, and must preserve its exact token ID when concatenated. The leading space is significant; a channel that trims it corrupts the surface and the decoder rejects it.",
        "",
        "| Receiver tokenizer | Strict safe single-codepoint | Boundary candidates before prompt-risk filter | After filter | Removed | 1,024 | 2,048 | 4,096 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for receiver in study.profile_set.receivers:
        lines.append(
            f"| {receiver.display_name} | {receiver.strict_scalar_count:,} | {receiver.pre_filter_boundary_candidate_count:,} | {receiver.safe_boundary_candidate_count:,} | {receiver.prompt_risk_terms_removed:,} | pass | pass | pass |"
        )
    lines.extend(
        [
            "",
            "This is an explicit relaxation from the earlier non-ASCII single-character surface, not a retroactive claim about v0.3 or v0.4. Added/special tokens, markup, punctuation, controls, bidi formatting, noncharacters, alternate normalization forms, and symbols longer than 64 UTF-8 bytes are excluded. A finite denylist additionally removes direct role markers, common prompt directives, credential terms, and selected high-risk action words; the table measures the resulting capacity loss.",
            "",
            "### Mandatory interpretation boundary: decoder before model",
            "",
            "Tokenizer-native ASCII tokens can still spell ordinary language, sensitive terms, or prompt-like sequences by accident. Filtering individual high-risk words cannot prove that an arbitrary multi-token sequence is semantically inert. A transport may also trim, collapse, case-fold, or replace whitespace. Therefore this profile is eligible only as decoder-before-model transport: the raw text must be parsed, profile-checked, checksum-checked, canonically decoded, and converted back to validated typed IR before any model sees the content. Raw `R7` text must not be placed in a system, developer, user, tool, or retrieved-context prompt. No direct LLM readability or safe prompt consumption is claimed.",
            "",
            "Whitespace trimming at the payload start, removal or collapse of symbol boundaries, replacement with tab/newline/non-breaking space, and case normalization are tested as corruption. Any changed form must fail before semantic use. A checksum detects accidental normalization; it does not make raw word-like text safe against prompt injection if an application violates this decoder boundary.",
            "",
            "## Frozen profile identities and cold transfer",
            "",
            "The byte entries are trained once with deterministic linked-list byte-pair merging. Each receiver then assigns its shortest safe token strings to entries in descending development-use order. Capsules bind the tokenizer key, implementation string, vocabulary size, full fingerprint, Unicode and safety policy, prompt-risk denylist digest, canonical-encoding and integrity policies, expansion and text bounds, exact development digest, declared size, base v0.2 Capsule digest and dictionary ID, ordered symbols/token IDs, and ordered byte expansions.",
            "",
            "| Receiver | Size | Profile SHA-256 | Capsule binary bytes | Text-transfer bytes | Receiver tokens | Alphabet bytes |",
            "|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    for receiver in study.profile_set.receivers:
        for size, profile in study.profile_set.profiles[receiver.key].items():
            text = encode_profile_capsule_text(profile)
            lines.append(
                f"| {receiver.display_name} | {size:,} | `{profile.sha256}` | {len(profile.capsule):,} | {len(text.encode('utf-8')):,} | {receiver.count(text):,} | {sum(len(symbol.encode('utf-8')) for symbol in profile.symbols):,} |"
            )
    lines.extend(
        [
            "",
            "The actual text capsule is `R7C:` plus unpadded Base64url of the canonical binary capsule. Cold costs below also charge the shared v0.2 static profile once when needed. Decoder software and the public specification are treated as installed.",
            "",
            "## Warm receiver tokens",
            "",
            "Every count covers the complete serialized text, including the receiver-profile tag and 64-bit accidental-corruption checksum. Lower is better. `Guarded` compares the complete v0.6 choice with all three v0.7 profiles for that receiver; v0.6 wins ties.",
            "",
            "| Dataset | Receiver | v0.4 | v0.5 | v0.6 | v0.7-1024 | v0.7-2048 | v0.7-4096 | Guarded | Guarded vs v0.6 | Guarded modes |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for dataset in study.datasets:
        for key, receiver in receivers.items():
            row = snapshot["warm_metrics"][dataset][key]
            modes = ", ".join(
                f"{name}:{count}"
                for name, count in snapshot["warm_mode_counts"][dataset][key].items()
            )
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {receiver.display_name} | {row['v04']['tokens']:,} | {row['v05']['tokens']:,} | {row['v06']['tokens']:,} | {row['v07_1024']['tokens']:,} | {row['v07_2048']['tokens']:,} | {row['v07_4096']['tokens']:,} | {row['guarded']['tokens']:,} | {_pct_saved(row['guarded']['tokens'], row['v06']['tokens'])} | {modes} |"
            )
    lines.extend(
        [
            "",
            "## Warm UTF-8 bytes",
            "",
            "Token selection can still increase bytes, so byte results are reported independently.",
            "",
            "| Dataset | Receiver | v0.4 | v0.5 | v0.6 | v0.7-1024 | v0.7-2048 | v0.7-4096 | Guarded | Guarded vs v0.6 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for dataset in study.datasets:
        for key, receiver in receivers.items():
            row = snapshot["warm_metrics"][dataset][key]
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {receiver.display_name} | {row['v04']['bytes']:,} | {row['v05']['bytes']:,} | {row['v06']['bytes']:,} | {row['v07_1024']['bytes']:,} | {row['v07_2048']['bytes']:,} | {row['v07_4096']['bytes']:,} | {row['guarded']['bytes']:,} | {_pct_saved(row['guarded']['bytes'], row['v06']['bytes'])} |"
            )
    lines.extend(
        [
            "",
            "## Per-message regressions retained",
            "",
            f"Raw v0.7 profiles are not protected by the chooser and may regress. `Worst token regression` and `worst byte regression` are relative increases for one message. The guarded row must retain zero token regressions but may still select a token win with more bytes. The machine-readable `frozen_results.json` retains all **{len(snapshot['regression_records']):,}** message/candidate records having either a positive token delta or a positive UTF-8-byte delta; records identify only the frozen dataset, receiver, message index, candidate, and numeric deltas, not message content.",
            "",
            "| Dataset | Receiver | Candidate | Improved / equal / regressed | Tokens saved | Bytes saved | Worst token regression | Worst byte regression |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for dataset in study.datasets:
        for key, receiver in receivers.items():
            for candidate in ("1024", "2048", "4096", "guarded"):
                value = snapshot["per_message"][dataset][key][candidate]
                lines.append(
                    f"| {DATASET_LABELS[dataset]} | {receiver.display_name} | {('v0.7-' + candidate) if candidate != 'guarded' else 'guarded'} | {value['improved']} / {value['equal']} / {value['regressed']} | {value['tokens_saved']:+,} | {value['bytes_saved']:+,} | {value['worst_token_regression_ppm'] / 10000:.2f}% | {value['worst_byte_regression_ppm'] / 10000:.2f}% |"
                )
    lines.extend(
        [
            "",
            "## Strict mean break-even against warm v0.6",
            "",
            "The first strict win is the smallest integer `N` satisfying `cold + N × candidate_mean < N × v0.6_mean`. Token and UTF-8-byte thresholds are computed separately. Each cold value charges the receiver profile text and shared v0.2 static profile. `Never on mean` is retained when the raw v0.7 warm mean is not smaller.",
            "",
            "| Dataset | Receiver | Profile | Cold tokens | Token break-even | Cold bytes | Byte break-even |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    static_text = base64.b64encode(encode_v02_capsule(DEFAULT_PROFILE)).decode("ascii")
    static_bytes = len(static_text.encode("utf-8"))
    for dataset, messages in study.datasets.items():
        count = len(messages)
        for key, receiver in receivers.items():
            row = snapshot["warm_metrics"][dataset][key]
            static_tokens = receiver.count(static_text)
            for size, profile in study.profile_set.profiles[key].items():
                cold_tokens = static_tokens + receiver.count(encode_profile_capsule_text(profile))
                profile_text = encode_profile_capsule_text(profile)
                cold_bytes = static_bytes + len(profile_text.encode("utf-8"))
                token_value = strict_break_even(
                    cold_tokens,
                    row["v06"]["tokens"],
                    row[f"v07_{size}"]["tokens"],
                    count,
                )
                byte_value = strict_break_even(
                    cold_bytes,
                    row["v06"]["bytes"],
                    row[f"v07_{size}"]["bytes"],
                    count,
                )
                lines.append(
                    f"| {DATASET_LABELS[dataset]} | {receiver.display_name} | {size:,} | {cold_tokens:,} | {_break_text(token_value)} | {cold_bytes:,} | {_break_text(byte_value)} |"
                )
    lines.extend(
        [
            "",
            "## Exact known-session cold planning",
            "",
            "The planner enumerates 64 activation states: the three existing v0.6 artifact gates and every subset of the three receiver profiles. The shared v0.2 profile is charged once. The complete v0.6 cold plan remains an exact option and wins ties through the deterministic ordering.",
            "",
            "| Dataset | Receiver | v0.6 cold total | Selected total | Saving | Cold tokens | Old structured / symbolic / optimized | Active v0.7 sizes | Selected modes |",
            "|---|---|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for dataset in study.datasets:
        for key, receiver in receivers.items():
            value = snapshot["cold"][dataset][key]
            states = f"{str(value['old_structured']).lower()} / {str(value['symbolic']).lower()} / {str(value['optimized']).lower()}"
            active = ", ".join(str(item) for item in value["active_v07_sizes"]) or "none"
            modes = ", ".join(f"{name}:{count}" for name, count in value["mode_counts"].items())
            lines.append(
                f"| {DATASET_LABELS[dataset]} | {receiver.display_name} | {value['v06_baseline_total']:,} | {value['selected_total']:,} | {_pct_saved(value['selected_total'], value['v06_baseline_total'])} | {value['cold_tokens']:,} | {states} | {active} | {modes} |"
            )
    lines.extend(
        [
            "",
            "## Reference implementation latency",
            "",
            "Times are per message on this machine over the fixed 290-message combined sequence with the requested repeat count (one in the frozen report), fixed order, and Python garbage collection disabled during timed loops. Direct rows include canonical v0.2 encoding/decoding, optimal byte parsing, receiver tokenization, checksum validation, and canonical re-encoding. Fresh chooser rows rebuild all candidates. Paths do unequal work and are not protocol-intrinsic limits.",
            "",
            "| Receiver | Direct profile | Encode p50 / p95 | Decode p50 / p95 |",
            "|---|---:|---:|---:|",
        ]
    )
    for key, receiver in receivers.items():
        for size in PROFILE_SIZES:
            value = latency["direct"][key][str(size)]
            lines.append(
                f"| {receiver.display_name} | {size:,} | {value['encode_p50_ns']/1000:.1f} / {value['encode_p95_ns']/1000:.1f} us | {value['decode_p50_ns']/1000:.1f} / {value['decode_p95_ns']/1000:.1f} us |"
            )
    lines.extend(
        [
            "",
            "| Receiver | Chooser | Select p50 / p95 | Decode p50 / p95 |",
            "|---|---|---:|---:|",
        ]
    )
    for key, receiver in receivers.items():
        for name in ("v06", "guarded_v07"):
            value = latency["chooser"][key][name]
            lines.append(
                f"| {receiver.display_name} | {name} | {value['encode_p50_ns']/1000:.1f} / {value['encode_p95_ns']/1000:.1f} us | {value['decode_p50_ns']/1000:.1f} / {value['decode_p95_ns']/1000:.1f} us |"
            )
    lines.extend(
        [
            "",
            "## Exactness, corruption, bounds, and binding",
            "",
            f"- Direct exact semantic recovery: {study.direct_exact:,}/{direct_trials:,}.",
            f"- Direct canonical deterministic re-encoding: {study.direct_deterministic:,}/{direct_trials:,}.",
            f"- Guarded selected recovery and deterministic reselection: {study.selected_exact:,}/{total_pairs:,} and {study.selected_deterministic:,}/{total_pairs:,}.",
            f"- Deterministic payload mutation rejection: {study.corruptions_rejected:,}/{study.corruptions_attempted:,}.",
            "- Capsule decoding checks the exact receiver key and full tokenizer fingerprint, Unicode policy, training digest, base v0.2 profile, declared cardinality, token IDs, byte expansions, checksum, and canonical byte equality.",
            f"- Surface decoding checks the 96-bit profile tag against one pinned full profile, unique space segmentation, exact concatenated token IDs, a {MAX_PAYLOAD_SYMBOLS:,}-symbol limit, cumulative 16 MiB frame expansion, the profile-bound checksum, v0.2 validation, and canonical optimal re-encoding. An ineligible oversized v0.7 candidate fails closed to the complete v0.6 chooser path.",
            "- The checksum detects accidental corruption only. It is not authentication, a signature, replay protection, or authority against an attacker who can recompute it.",
            "- Raw surfaces are decoder-before-model transport only. Prompt exposure is an application-policy failure even when the surface is structurally valid.",
            "",
            "## Frozen inputs and artifact identities",
            "",
            f"- Development: {len(study.datasets['development']):,} messages, `{EXPECTED_TRAIN_SHA256}`.",
            f"- Grouped holdout: {len(study.datasets['grouped_holdout']):,} messages, `{EXPECTED_HOLDOUT_SHA256}`.",
            f"- Out of domain: {len(study.datasets['out_of_domain']):,} messages, `{EXPECTED_OOD_SHA256}`.",
            f"- Byte-entry sequence SHA-256: `{snapshot['byte_entry_sha256']}`.",
            f"- Deterministic study snapshot SHA-256: `{snapshot_sha256(snapshot)}`.",
            f"- Byte-entry training and twelve-profile assembly wall time, excluding tokenizer loading and vocabulary enumeration: {study.profile_set.training_seconds:.3f}s.",
            f"- Runtime: `{platform.python_implementation()} {platform.python_version()}` / `{platform.platform()}`.",
            f"- Tokenizer packages: `tiktoken=={TIKTOKEN_VERSION}`, `tokenizers=={TOKENIZERS_VERSION}`.",
            f"- Implementation SHA-256: `{_local_source_sha256('receiver_negotiated_surface_v07.py')}`.",
            f"- Test-suite SHA-256: `{_local_source_sha256('test_receiver_negotiated_surface_v07.py')}`.",
            "",
            "This is an unsigned downstream research artifact derived from the existing experimental language repository stewarded by `jaden3824`. The working tree has no committed implementation revision, so the exact file digests above identify this run. They do not establish conformance, adoption, endorsement, or authority.",
            "",
            "## Limitations",
            "",
            "- Development is in-sample. Grouped holdout shares the synthetic generator family, and OOD contains only ten repository-authored messages.",
            "- The boundary-token alphabet intentionally uses readable ASCII word fragments and significant leading spaces. It changes the older non-ASCII single-character threat and transport assumptions. Channels that normalize whitespace are ineligible even though corruption is detected.",
            "- The finite prompt-risk denylist lowers direct leakage but cannot eliminate accidental directives, sensitive language, or meaningful multi-token phrases. The raw surface is not a prompt format and has no direct-LLM-readability claim.",
            "- Long concatenation and every observed payload are verified exactly, but this is evidence for four pinned tokenizer implementations and fingerprints only. A tokenizer update requires a new profile.",
            "- The cold planner is an offline optimum for a known sequence. An unknown-horizon streaming runtime needs a conservative activation policy and may not achieve it.",
            "- Counts exclude chat templates, BOS/EOS, prompts, HTTP envelopes, retransmission, negotiation round trips, and hosted billing rules.",
            "- No model was asked to understand or generate the surfaces. Token reduction does not establish lower energy, latency, memory, money, or total task cost.",
            "- No external benchmark search or independent reproduction was performed. Unfavorable raw-profile regressions, cold non-break-even cases, byte growth, and slower paths are retained above.",
            "",
            "## Offline reproduction",
            "",
            "```bash",
            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv-research-py312/bin/python -m unittest performance_v07/test_receiver_negotiated_surface_v07.py -v",
            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv-research-py312/bin/python performance_v07/receiver_negotiated_surface_v07.py --benchmark --assets-dir work/tokenizer_assets --repeats 1",
            "```",
            "",
            "Both commands are offline and reject missing or mismatched tokenizer assets.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_inside_directory(path: Path, text: str) -> None:
    directory = Path(__file__).resolve().parent
    target = path.resolve()
    if target.parent != directory:
        raise ValidationError("v0.7 artifacts may be written only inside performance_v07")
    target.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="run the frozen offline study")
    parser.add_argument("--assets-dir", type=Path, default=default_asset_root())
    parser.add_argument("--repeats", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if not arguments.benchmark:
        raise SystemExit("pass --benchmark to run the frozen offline study")
    study = collect_study(arguments.assets_dir)
    latency = measure_latency(study, repeats=arguments.repeats)
    snapshot = study_snapshot(study)
    directory = Path(__file__).resolve().parent
    _write_inside_directory(directory / SNAPSHOT_NAME, _canonical_json(snapshot) + "\n")
    report = render_report(study, latency)
    _write_inside_directory(directory / REPORT_NAME, report)
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
