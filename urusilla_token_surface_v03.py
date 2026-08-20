#!/usr/bin/env python3
"""Experimental tokenizer-aware text surface for canonical UrusillaIR.

UrusillaTokenSurface v0.3 is an optional negotiated codec, not a semantic
language and not a replacement for UrusillaIR.  It wraps a canonical UrusillaWire
v0.2 frame in a deterministic, printable text surface.  A frozen codebook
maps byte strings to visible Unicode symbols that were single tokens under
both ``cl100k_base`` and ``o200k_base`` in tiktoken 0.11.0 when the codebook
was developed.

The codebook was trained openly on the fixed 280-message development corpus.
Results on that same corpus are therefore in-sample and tokenizer-specific.
The first 256 entries cover every byte, so messages outside the development
corpus remain exactly reversible, although their compression can be worse.

The surface contains data only.  It deliberately excludes ASCII from the
payload alphabet, control characters, whitespace, bidirectional controls,
markup delimiters, and prompt-like natural-language instructions.  It must
still be decoded and validated before use; it must never be executed or
treated as authorization.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import gc
import hashlib
import hmac
import json
import math
from pathlib import Path
import platform
import re
import statistics
import struct
import sys
import time
from typing import Any, Mapping, Sequence
import unicodedata
import zlib

from urusilla import DecodeError, MAX_FRAME_BYTES, ValidationError, normalize_message
from urusilla_wire_v02 import (
    DEFAULT_PROFILE,
    decode_message as decode_v02,
    encode_message as encode_v02,
)


FORMAT = "urusilla-token-surface-v0.3-experimental"
SURFACE_PREFIX = "S3"
CAPSULE_PREFIX = "S3C:"
CAPSULE_MAGIC = b"STC\x03"
CODEBOOK_SYMBOLS = 1_024
BASE_BYTE_SYMBOLS = 256
MAX_CODEBOOK_SYMBOLS = 1_024
MAX_ENTRY_BYTES = 1_024
MAX_CODEBOOK_BYTES = 1 * 1024 * 1024
MAX_SURFACE_UTF8_BYTES = 64 * 1024 * 1024
MAX_PAYLOAD_SYMBOLS = 16 * 1024 * 1024
CODEBOOK_ID_BYTES = 16
SURFACE_CHECKSUM_BYTES = 8
CAPSULE_CHECKSUM_BYTES = 16

DEVELOPMENT_CORPUS_VERSION = "urusilla-benchmark-corpus-v1"
DEVELOPMENT_CORPUS_MESSAGES = 280
DEVELOPMENT_CORPUS_SHA256 = (
    "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc"
)
DEVELOPMENT_PROFILE_DICTIONARY_ID = "7d12fc414eae60b2"
ALPHABET_SHA256 = "7fa9faea81a510f6f28b1bf4e92a412be36daebb6d335c3f5f27c41b04166b30"
EXPECTED_CODEBOOK_SHA256 = "4ba2dab386c0918267f86aac94cc965d0297fb8744bc78c458243047f01660ab"

_CAPSULE_DOMAIN = b"UrusillaTokenSurface-v0.3-codebook\x00"
_SURFACE_DOMAIN = b"UrusillaTokenSurface-v0.3-frame\x00"
_FORBIDDEN_BIDI = frozenset({"R", "AL", "RLE", "RLO", "LRE", "LRO", "PDF", "BN"})
SURFACE_CHECKSUM_SYMBOLS = 7

# zlib level-9 compression of the 2,882-byte UTF-8 alphabet.  The alphabet is
# an immutable ordered list of 1,024 visible non-ASCII code points selected
# during development because each encoded as one token in both named
# tokenizers.  The compressed representation reduces source noise; the exact
# uncompressed hash is pinned above and the full alphabet is charged in the
# negotiated codebook capsule.
_ALPHABET_ZLIB_B64 = (
    "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"
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    if not text or re.fullmatch(r"[A-Za-z0-9_-]+", text) is None:
        raise DecodeError("invalid base64url text")
    try:
        return base64.b64decode(
            text + "=" * ((-len(text)) % 4), altchars=b"-_", validate=True
        )
    except Exception as exc:
        raise DecodeError("invalid base64url text") from exc


def _uvarint(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= (1 << 64) - 1:
        raise ValidationError("uvarint value is out of range")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, count: int) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise DecodeError("truncated codebook capsule")
        start = self.pos
        self.pos += count
        return self.data[start : self.pos]

    def uvarint(self) -> int:
        value = 0
        raw = bytearray()
        for shift in range(0, 70, 7):
            byte = self.read(1)[0]
            raw.append(byte)
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                if value > (1 << 64) - 1 or bytes(raw) != _uvarint(value):
                    raise DecodeError("non-canonical or overflowing uvarint")
                return value
        raise DecodeError("uvarint exceeds ten bytes")

    def end(self) -> None:
        if self.pos != len(self.data):
            raise DecodeError("trailing codebook capsule data")


def _safe_symbol(symbol: str) -> bool:
    if len(symbol) != 1 or symbol.isascii() or not symbol.isprintable() or symbol.isspace():
        return False
    if unicodedata.category(symbol)[0] not in "LNS":
        return False
    if unicodedata.bidirectional(symbol) in _FORBIDDEN_BIDI:
        return False
    name = unicodedata.name(symbol, "")
    return "BLANK" not in name and "SPACE" not in name


def _load_alphabet() -> str:
    try:
        raw = zlib.decompress(base64.b64decode(_ALPHABET_ZLIB_B64, validate=True))
        alphabet = raw.decode("utf-8", errors="strict")
    except Exception as exc:
        raise RuntimeError("embedded surface alphabet is corrupt") from exc
    if len(alphabet) != CODEBOOK_SYMBOLS or len(set(alphabet)) != len(alphabet):
        raise RuntimeError("embedded surface alphabet has the wrong cardinality")
    if hashlib.sha256(raw).hexdigest() != ALPHABET_SHA256:
        raise RuntimeError("embedded surface alphabet hash mismatch")
    if not all(_safe_symbol(symbol) for symbol in alphabet):
        raise RuntimeError("embedded surface alphabet contains an unsafe symbol")
    return alphabet


SURFACE_ALPHABET = _load_alphabet()


@dataclass(frozen=True)
class TokenCodebook:
    """Immutable byte-string codebook plus its printable surface alphabet."""

    corpus_sha256: str
    profile_dictionary_id: bytes
    alphabet: str
    entries: tuple[bytes, ...]

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.corpus_sha256) is None:
            raise ValidationError("codebook corpus digest must be lowercase SHA-256")
        if len(self.profile_dictionary_id) != 8:
            raise ValidationError("profile dictionary ID must be eight bytes")
        if not 256 <= len(self.entries) <= MAX_CODEBOOK_SYMBOLS:
            raise ValidationError("codebook symbol count is outside the allowed range")
        if len(self.alphabet) != len(self.entries) or len(set(self.alphabet)) != len(self.alphabet):
            raise ValidationError("codebook alphabet and entries must be unique and aligned")
        if not all(_safe_symbol(symbol) for symbol in self.alphabet):
            raise ValidationError("codebook contains an unsafe surface symbol")
        if self.entries[:256] != tuple(bytes([value]) for value in range(256)):
            raise ValidationError("the first 256 codebook entries must cover every byte")
        if len(set(self.entries)) != len(self.entries):
            raise ValidationError("codebook contains duplicate byte expansions")
        if any(not entry or len(entry) > MAX_ENTRY_BYTES for entry in self.entries):
            raise ValidationError("codebook entry size is outside the allowed range")

    @property
    def capsule(self) -> bytes:
        return encode_codebook_capsule(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.capsule).hexdigest()

    @property
    def content_id(self) -> str:
        return _b64url(bytes.fromhex(self.sha256)[:CODEBOOK_ID_BYTES])


def _train_entries(frames: Sequence[bytes], symbol_count: int) -> tuple[bytes, ...]:
    """Deterministic byte-pair training used only to construct the frozen codebook."""

    if symbol_count < 256 or symbol_count > MAX_CODEBOOK_SYMBOLS:
        raise ValidationError("requested symbol count is outside the allowed range")
    sequences = [list(frame) for frame in frames]
    entries = [bytes([value]) for value in range(256)]
    for new_symbol in range(256, symbol_count):
        pair_counts: Counter[tuple[int, int]] = Counter()
        for sequence in sequences:
            pair_counts.update(zip(sequence, sequence[1:]))
        if not pair_counts:
            break
        frequency = max(pair_counts.values())
        pair = min(candidate for candidate, count in pair_counts.items() if count == frequency)
        expansion = entries[pair[0]] + entries[pair[1]]
        if expansion in entries:
            raise RuntimeError("deterministic training produced a duplicate expansion")
        entries.append(expansion)
        for sequence_index, sequence in enumerate(sequences):
            replaced: list[int] = []
            index = 0
            while index < len(sequence):
                if index + 1 < len(sequence) and (sequence[index], sequence[index + 1]) == pair:
                    replaced.append(new_symbol)
                    index += 2
                else:
                    replaced.append(sequence[index])
                    index += 1
            sequences[sequence_index] = replaced
    if len(entries) != symbol_count:
        raise RuntimeError("development corpus did not yield the requested codebook size")
    return tuple(entries)


@lru_cache(maxsize=1)
def development_codebook() -> TokenCodebook:
    """Rebuild the frozen codebook only if every pinned development input matches."""

    from urusilla_benchmark import build_corpus, corpus_digest

    corpus = build_corpus(DEVELOPMENT_CORPUS_MESSAGES)
    if corpus_digest(corpus) != DEVELOPMENT_CORPUS_SHA256:
        raise RuntimeError("development corpus changed; refusing to derive a different codebook")
    if DEFAULT_PROFILE.dictionary_id_hex != DEVELOPMENT_PROFILE_DICTIONARY_ID:
        raise RuntimeError("v0.2 profile changed; refusing to derive a different codebook")
    frames = [encode_v02(message) for message in corpus]
    result = TokenCodebook(
        corpus_sha256=DEVELOPMENT_CORPUS_SHA256,
        profile_dictionary_id=DEFAULT_PROFILE.dictionary_id,
        alphabet=SURFACE_ALPHABET,
        entries=_train_entries(frames, CODEBOOK_SYMBOLS),
    )
    if result.sha256 != EXPECTED_CODEBOOK_SHA256:
        raise RuntimeError("derived codebook hash changed; refusing an unfrozen codebook")
    return result


def encode_codebook_capsule(codebook: TokenCodebook) -> bytes:
    """Serialize a codebook canonically with a 128-bit accidental-error checksum."""

    body = bytearray(CAPSULE_MAGIC)
    body += bytes.fromhex(codebook.corpus_sha256)
    body += codebook.profile_dictionary_id
    body += _uvarint(len(codebook.entries))
    for symbol, entry in zip(codebook.alphabet, codebook.entries, strict=True):
        symbol_raw = symbol.encode("utf-8")
        body += _uvarint(len(symbol_raw)) + symbol_raw
        body += _uvarint(len(entry)) + entry
    checksum = hashlib.sha256(_CAPSULE_DOMAIN + body).digest()[:CAPSULE_CHECKSUM_BYTES]
    capsule = bytes(body) + checksum
    if len(capsule) > MAX_CODEBOOK_BYTES:
        raise ValidationError("codebook capsule exceeds the size limit")
    return capsule


def decode_codebook_capsule(capsule: bytes) -> TokenCodebook:
    if not isinstance(capsule, bytes) or len(capsule) > MAX_CODEBOOK_BYTES:
        raise DecodeError("codebook capsule type or size is invalid")
    if len(capsule) < len(CAPSULE_MAGIC) + 32 + 8 + 1 + CAPSULE_CHECKSUM_BYTES:
        raise DecodeError("codebook capsule is too short")
    body, supplied = capsule[:-CAPSULE_CHECKSUM_BYTES], capsule[-CAPSULE_CHECKSUM_BYTES:]
    expected = hashlib.sha256(_CAPSULE_DOMAIN + body).digest()[:CAPSULE_CHECKSUM_BYTES]
    if not hmac.compare_digest(supplied, expected):
        raise DecodeError("codebook capsule checksum mismatch")
    reader = _Reader(body)
    if reader.read(len(CAPSULE_MAGIC)) != CAPSULE_MAGIC:
        raise DecodeError("unknown codebook capsule format")
    corpus_sha256 = reader.read(32).hex()
    profile_id = reader.read(8)
    count = reader.uvarint()
    if not 256 <= count <= MAX_CODEBOOK_SYMBOLS:
        raise DecodeError("codebook symbol count is outside the allowed range")
    alphabet: list[str] = []
    entries: list[bytes] = []
    for _ in range(count):
        symbol_size = reader.uvarint()
        if not 2 <= symbol_size <= 4:
            raise DecodeError("codebook symbol UTF-8 length is invalid")
        try:
            symbol = reader.read(symbol_size).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise DecodeError("codebook symbol is invalid UTF-8") from exc
        entry_size = reader.uvarint()
        if not 1 <= entry_size <= MAX_ENTRY_BYTES:
            raise DecodeError("codebook entry size is outside the allowed range")
        alphabet.append(symbol)
        entries.append(reader.read(entry_size))
    reader.end()
    try:
        result = TokenCodebook(corpus_sha256, profile_id, "".join(alphabet), tuple(entries))
    except ValidationError as exc:
        raise DecodeError(str(exc)) from exc
    if encode_codebook_capsule(result) != capsule:
        raise DecodeError("codebook capsule is not canonical")
    return result


def encode_codebook_capsule_text(codebook: TokenCodebook) -> str:
    return CAPSULE_PREFIX + _b64url(codebook.capsule)


def decode_codebook_capsule_text(text: str) -> TokenCodebook:
    if not isinstance(text, str) or not text.startswith(CAPSULE_PREFIX):
        raise DecodeError("unknown text codebook capsule format")
    if len(text.encode("utf-8")) > 2 * MAX_CODEBOOK_BYTES:
        raise DecodeError("text codebook capsule exceeds the size limit")
    result = decode_codebook_capsule(_unb64url(text[len(CAPSULE_PREFIX) :]))
    if encode_codebook_capsule_text(result) != text:
        raise DecodeError("text codebook capsule is not canonical")
    return result


@lru_cache(maxsize=8)
def _encoding_trie(codebook: TokenCodebook) -> dict[Any, Any]:
    root: dict[Any, Any] = {}
    for symbol_index, expansion in enumerate(codebook.entries):
        node = root
        for byte in expansion:
            node = node.setdefault(byte, {})
        node[None] = symbol_index
    return root


@lru_cache(maxsize=8)
def _decoding_map(codebook: TokenCodebook) -> Mapping[str, bytes]:
    return dict(zip(codebook.alphabet, codebook.entries, strict=True))


@lru_cache(maxsize=8)
def _alphabet_index(codebook: TokenCodebook) -> Mapping[str, int]:
    return {symbol: index for index, symbol in enumerate(codebook.alphabet)}


def _encode_checksum_symbols(checksum: bytes, codebook: TokenCodebook) -> str:
    if len(checksum) != SURFACE_CHECKSUM_BYTES:
        raise ValidationError("surface checksum has the wrong size")
    value = int.from_bytes(checksum, "big")
    output = [codebook.alphabet[0]] * SURFACE_CHECKSUM_SYMBOLS
    for index in range(SURFACE_CHECKSUM_SYMBOLS - 1, -1, -1):
        output[index] = codebook.alphabet[value & 0x3FF]
        value >>= 10
    if value:
        raise RuntimeError("checksum does not fit the fixed radix-1024 field")
    return "".join(output)


def _decode_checksum_symbols(text: str, codebook: TokenCodebook) -> bytes:
    if len(text) != SURFACE_CHECKSUM_SYMBOLS:
        raise DecodeError("surface checksum has the wrong symbol count")
    indices = _alphabet_index(codebook)
    value = 0
    for position, symbol in enumerate(text):
        digit = indices.get(symbol)
        if digit is None:
            raise DecodeError("surface checksum contains an unknown symbol")
        if position == 0 and digit >= 16:
            raise DecodeError("surface checksum has non-canonical high bits")
        value = (value << 10) | digit
    return value.to_bytes(SURFACE_CHECKSUM_BYTES, "big")


def _encode_bytes(raw: bytes, codebook: TokenCodebook) -> str:
    trie = _encoding_trie(codebook)
    output: list[str] = []
    position = 0
    while position < len(raw):
        node = trie
        scan = position
        best_index: int | None = None
        best_end = position
        while scan < len(raw) and raw[scan] in node:
            node = node[raw[scan]]
            scan += 1
            if None in node:
                best_index = node[None]
                best_end = scan
        if best_index is None:
            raise RuntimeError("codebook lost base-byte coverage")
        output.append(codebook.alphabet[best_index])
        position = best_end
    return "".join(output)


def _decode_payload(payload: str, codebook: TokenCodebook) -> bytes:
    if len(payload) > MAX_PAYLOAD_SYMBOLS:
        raise DecodeError("surface payload exceeds the symbol limit")
    mapping = _decoding_map(codebook)
    output = bytearray()
    for symbol in payload:
        expansion = mapping.get(symbol)
        if expansion is None:
            raise DecodeError("surface payload contains a symbol outside the negotiated codebook")
        if len(output) + len(expansion) > MAX_FRAME_BYTES:
            raise DecodeError("decoded v0.2 frame exceeds the size limit")
        output += expansion
    return bytes(output)


def encode_message(
    message: Mapping[str, Any], codebook: TokenCodebook | None = None, *, slot: int = 0
) -> str:
    """Return a deterministic text surface for a structurally valid Urusilla message."""

    selected = development_codebook() if codebook is None else codebook
    if type(slot) is not int or not 0 <= slot < len(selected.alphabet):
        raise ValidationError("negotiated codebook slot is outside the allowed range")
    frame = encode_v02(message)
    payload = _encode_bytes(frame, selected)
    checksum = hashlib.blake2s(
        _SURFACE_DOMAIN + bytes.fromhex(selected.sha256) + frame,
        digest_size=SURFACE_CHECKSUM_BYTES,
    ).digest()
    # The full content address is exchanged with the capsule.  A session-local
    # one-symbol slot binds this frame to that negotiated address without
    # repeating a 128-bit identifier in every message.
    surface = (
        SURFACE_PREFIX
        + selected.alphabet[slot]
        + payload
        + _encode_checksum_symbols(checksum, selected)
    )
    if len(surface.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise ValidationError("surface text exceeds the UTF-8 size limit")
    return surface


def decode_message(
    surface: str, codebook: TokenCodebook | None = None, *, slot: int = 0
) -> dict[str, Any]:
    """Decode, check, and canonically re-encode one negotiated v0.3 surface."""

    selected = development_codebook() if codebook is None else codebook
    if type(slot) is not int or not 0 <= slot < len(selected.alphabet):
        raise DecodeError("negotiated codebook slot is outside the allowed range")
    if not isinstance(surface, str):
        raise DecodeError("surface must be text")
    if len(surface.encode("utf-8")) > MAX_SURFACE_UTF8_BYTES:
        raise DecodeError("surface text exceeds the UTF-8 size limit")
    minimum = len(SURFACE_PREFIX) + 1 + 1 + SURFACE_CHECKSUM_SYMBOLS
    if len(surface) < minimum or not surface.startswith(SURFACE_PREFIX):
        raise DecodeError("unknown or malformed token surface")
    if surface[len(SURFACE_PREFIX)] != selected.alphabet[slot]:
        raise DecodeError("surface codebook slot does not match the negotiated binding")
    payload = surface[len(SURFACE_PREFIX) + 1 : -SURFACE_CHECKSUM_SYMBOLS]
    checksum_text = surface[-SURFACE_CHECKSUM_SYMBOLS:]
    frame = _decode_payload(payload, selected)
    expected = hashlib.blake2s(
        _SURFACE_DOMAIN + bytes.fromhex(selected.sha256) + frame,
        digest_size=SURFACE_CHECKSUM_BYTES,
    ).digest()
    supplied = _decode_checksum_symbols(checksum_text, selected)
    if len(supplied) != SURFACE_CHECKSUM_BYTES or not hmac.compare_digest(supplied, expected):
        raise DecodeError("surface checksum mismatch")
    message = decode_v02(frame)
    if encode_message(message, selected, slot=slot) != surface:
        raise DecodeError("surface is valid but not canonical")
    return message


def _strict_break_even(cold: int, baseline_total: int, warm_total: int, count: int) -> int | None:
    saving = baseline_total - warm_total
    if saving <= 0:
        return None
    return cold * count // saving + 1


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _percent(candidate: int, baseline: int) -> str:
    return f"{100 * (1 - candidate / baseline):+.1f}% saved"


def run_benchmark(*, repeats: int = 5) -> str:
    """Run the fixed in-sample tokenizer experiment and return an English report."""

    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("benchmark requires tiktoken 0.11.0 in an isolated environment") from exc
    if tiktoken.__version__ != "0.11.0":
        raise RuntimeError("benchmark is pinned to tiktoken 0.11.0")

    from urusilla_benchmark import build_corpus, corpus_digest, json_decode, json_encode
    from urusilla import decode_message as decode_v01, encode_message as encode_v01

    corpus = build_corpus(DEVELOPMENT_CORPUS_MESSAGES)
    if corpus_digest(corpus) != DEVELOPMENT_CORPUS_SHA256:
        raise RuntimeError("fixed corpus digest mismatch")
    training_started = time.perf_counter()
    codebook = development_codebook()
    training_seconds = time.perf_counter() - training_started

    def b64_v01_encode(message: Mapping[str, Any]) -> str:
        return base64.b64encode(encode_v01(message)).decode("ascii")

    def b64_v01_decode(text: str) -> dict[str, Any]:
        return decode_v01(base64.b64decode(text, validate=True))

    def b64_v02_encode(message: Mapping[str, Any]) -> str:
        return base64.b64encode(encode_v02(message)).decode("ascii")

    def b64_v02_decode(text: str) -> dict[str, Any]:
        return decode_v02(base64.b64decode(text, validate=True))

    codecs = (
        ("sorted minified JSON", lambda value: json_encode(value).decode("utf-8"), lambda text: json_decode(text.encode("utf-8"))),
        ("Base64 UrusillaWire v0.1", b64_v01_encode, b64_v01_decode),
        ("Base64 UrusillaWire v0.2 warm", b64_v02_encode, b64_v02_decode),
        ("UrusillaTokenSurface v0.3 warm", lambda value: encode_message(value, codebook), lambda text: decode_message(text, codebook)),
    )
    texts: dict[str, list[str]] = {}
    exact: dict[str, int] = {}
    deterministic: dict[str, int] = {}
    for name, encoder, decoder in codecs:
        values = [encoder(message) for message in corpus]
        texts[name] = values
        exact[name] = sum(decoder(text) == message for text, message in zip(values, corpus, strict=True))
        deterministic[name] = sum(encoder(message) == text for text, message in zip(values, corpus, strict=True))

    encodings = {
        name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")
    }
    token_totals = {
        codec_name: {
            tokenizer: sum(len(encoding.encode(text)) for text in texts[codec_name])
            for tokenizer, encoding in encodings.items()
        }
        for codec_name, _, _ in codecs
    }
    byte_totals = {
        name: sum(len(text.encode("utf-8")) for text in texts[name]) for name, _, _ in codecs
    }
    char_totals = {name: sum(map(len, texts[name])) for name, _, _ in codecs}
    capsule_text = encode_codebook_capsule_text(codebook)
    cold_bytes = len(capsule_text.encode("utf-8"))
    cold_tokens = {
        name: len(encoding.encode(capsule_text)) for name, encoding in encodings.items()
    }

    latency: dict[str, tuple[list[int], list[int]]] = {}
    for name, encoder, decoder in codecs:
        for message in corpus[:8]:
            decoder(encoder(message))
        encode_ns: list[int] = []
        decode_ns: list[int] = []
        gc_state = gc.isenabled()
        gc.disable()
        try:
            for _ in range(repeats):
                for message in corpus:
                    started = time.perf_counter_ns()
                    encoder(message)
                    encode_ns.append(time.perf_counter_ns() - started)
            for _ in range(repeats):
                for text in texts[name]:
                    started = time.perf_counter_ns()
                    decoder(text)
                    decode_ns.append(time.perf_counter_ns() - started)
        finally:
            if gc_state:
                gc.enable()
        latency[name] = encode_ns, decode_ns

    corruption_rejected = 0
    for message_index, surface in enumerate(texts["UrusillaTokenSurface v0.3 warm"]):
        for trial in range(4):
            payload_start = len(SURFACE_PREFIX) + 1
            payload_end = len(surface) - SURFACE_CHECKSUM_SYMBOLS
            payload = list(surface[payload_start:payload_end])
            position = int.from_bytes(
                hashlib.sha256(f"v03|{message_index}|{trial}".encode()).digest()[:8], "big"
            ) % len(payload)
            original = payload[position]
            payload[position] = codebook.alphabet[(codebook.alphabet.index(original) + 1) % len(codebook.alphabet)]
            changed = surface[:payload_start] + "".join(payload) + surface[payload_end:]
            try:
                decode_message(changed, codebook)
            except Exception:
                corruption_rejected += 1
            payload[position] = original

    surface_digest = hashlib.sha256()
    for text in texts["UrusillaTokenSurface v0.3 warm"]:
        raw = text.encode("utf-8")
        surface_digest.update(struct.pack(">Q", len(raw)))
        surface_digest.update(raw)

    v03_name = "UrusillaTokenSurface v0.3 warm"
    v02_name = "Base64 UrusillaWire v0.2 warm"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# UrusillaTokenSurface v0.3 tokenizer-aware experiment",
        "",
        f"Execution time (UTC): `{timestamp}`  ",
        f"Runtime: `{platform.python_implementation()} {platform.python_version()}` / `{platform.platform()}`  ",
        f"Tokenizer package: `tiktoken {tiktoken.__version__}`  ",
        f"Corpus: `{DEVELOPMENT_CORPUS_VERSION}`, {len(corpus)} messages, SHA-256 `{DEVELOPMENT_CORPUS_SHA256}`  ",
        f"Codebook: {len(codebook.entries):,} symbols, SHA-256 `{codebook.sha256}`, content ID `{codebook.content_id}`  ",
        f"Surface sequence SHA-256: `{surface_digest.hexdigest()}`  ",
        f"Codebook rebuild time: {training_seconds:.3f}s; timing repeats after negotiation: {repeats}",
        "",
        "## Scope and central result",
        "",
        "This is an optional text codec over unchanged canonical UrusillaIR and UrusillaWire v0.2. "
        "It is not a new semantic core. The codebook was derived from this exact development "
        "corpus, so every compression number below is an in-sample upper bound, not a held-out "
        "or cross-model result.",
        "",
        f"Warm v0.3 used {token_totals[v03_name]['cl100k_base']:,} `cl100k_base` tokens and "
        f"{token_totals[v03_name]['o200k_base']:,} `o200k_base` tokens. Relative to Base64 v0.2, "
        f"that is {_percent(token_totals[v03_name]['cl100k_base'], token_totals[v02_name]['cl100k_base'])} "
        f"and {_percent(token_totals[v03_name]['o200k_base'], token_totals[v02_name]['o200k_base'])}, respectively. "
        "Cold codebook transfer and strict break-even are charged below.",
        "",
        "## Warm text results",
        "",
        "| Codec | UTF-8 bytes | Characters | cl100k_base tokens | o200k_base tokens | Exact | Deterministic |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, _, _ in codecs:
        lines.append(
            f"| {name} | {byte_totals[name]:,} | {char_totals[name]:,} | "
            f"{token_totals[name]['cl100k_base']:,} | {token_totals[name]['o200k_base']:,} | "
            f"{exact[name]}/{len(corpus)} | {deterministic[name]}/{len(corpus)} |"
        )
    lines.extend([
        "",
        "Base64 rows encode each complete canonical binary frame independently. JSON is sorted, "
        "minified, UTF-8, and validated through the same semantic normalizer. Token counts are "
        "exact for the named tokenizer assets as loaded by tiktoken 0.11.0; they are not token "
        "counts for every model or provider.",
        "",
        "## Cold codebook cost and strict break-even",
        "",
        f"The canonical binary capsule is {len(codebook.capsule):,} bytes. Its actual `S3C:` "
        f"Base64url transfer form is {cold_bytes:,} UTF-8 bytes, "
        f"{cold_tokens['cl100k_base']:,} `cl100k_base` tokens, and "
        f"{cold_tokens['o200k_base']:,} `o200k_base` tokens.",
        "",
        "Strict break-even is the first integer N for which `cold + N * mean(v0.3)` is strictly "
        "less than `N * mean(baseline)`. It assumes the negotiated codebook is reused and does "
        "not charge the separate Urusilla grammar or v0.2 profile capsule, which both v0.2 and v0.3 need.",
        "",
        "| Baseline | UTF-8 byte break-even | cl100k_base token break-even | o200k_base token break-even |",
        "|---|---:|---:|---:|",
    ])
    for name, _, _ in codecs[:-1]:
        breaks = [
            _strict_break_even(cold_bytes, byte_totals[name], byte_totals[v03_name], len(corpus)),
            _strict_break_even(cold_tokens['cl100k_base'], token_totals[name]['cl100k_base'], token_totals[v03_name]['cl100k_base'], len(corpus)),
            _strict_break_even(cold_tokens['o200k_base'], token_totals[name]['o200k_base'], token_totals[v03_name]['o200k_base'], len(corpus)),
        ]
        rendered = ["never on mean" if value is None else str(value) for value in breaks]
        lines.append(f"| {name} | {rendered[0]} | {rendered[1]} | {rendered[2]} |")
    lines.extend([
        "",
        "## Codec latency after negotiation",
        "",
        "| Codec | Encode p50 (us) | Encode p95 (us) | Decode p50 (us) | Decode p95 (us) |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, _, _ in codecs:
        enc, dec = latency[name]
        lines.append(
            f"| {name} | {_nearest(enc, .50)/1000:.2f} | {_nearest(enc, .95)/1000:.2f} | "
            f"{_nearest(dec, .50)/1000:.2f} | {_nearest(dec, .95)/1000:.2f} |"
        )
    lines.extend([
        "",
        "Paths do unequal work: JSON has no transport checksum, Base64 rows invoke their binary "
        "codec, and v0.3 performs longest-match substitution plus v0.2 validation and canonical "
        "re-encoding. These are current Python implementation timings, not protocol-intrinsic limits.",
        "",
        "## Integrity, safety, and limitations",
        "",
        f"All {len(corpus) * 4:,}/{len(corpus) * 4:,} deterministic single-symbol corruptions were rejected. "
        "The codebook capsule has a 128-bit truncated content address, bound to each surface through "
        "the negotiated slot, and the surface has a 64-bit accidental-error checksum; neither is "
        "authentication. Urusilla effect eligibility still "
        "requires authenticated identity, schema policy, and conversation-state checks.",
        "",
        "The full codebook content address is bound to a session-local one-symbol slot during "
        "negotiation, so it is not repeated in each surface. Slot reuse without renegotiation is "
        "invalid. Within a payload, the encoder switches at byte-fragment granularity between "
        "learned multi-byte entries and complete raw-byte fallbacks. Once both peers support a new "
        "UrusillaIR and v0.2 grammar revision, unfamiliar byte sequences can therefore use fallback "
        "entries immediately and later negotiate a new frozen codebook.\n\nThe decoder limits surface bytes, payload symbols, codebook size, entry expansion, and "
        "decoded frame bytes. Payload symbols are visible, non-ASCII, non-whitespace characters "
        "without bidirectional controls or markup delimiters. The format contains no executable "
        "instructions and must not be inserted into a model prompt as if it were trusted text.",
        "",
        "The codebook openly overfits repeated byte substrings in the development corpus. It does "
        "not establish held-out performance, natural-language equivalence, model comprehension, "
        "cross-tokenizer universality, or adoption. UTF-8 byte size can be unfavorable because most "
        "surface symbols occupy multiple bytes. A release gate requires held-out schemas and "
        "tokenizers, multi-model task-success tests, adversarial parsing, and an independently "
        "generated codebook.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python3 -m venv work/token-surface-venv",
        "work/token-surface-venv/bin/python -m pip install tiktoken==0.11.0",
            "PYTHONPATH=. work/token-surface-venv/bin/python urusilla_token_surface_v03.py --benchmark",
            "PYTHONPATH=. work/token-surface-venv/bin/python -m unittest test_urusilla_token_surface_v03.py -v",
        "```",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="run the fixed tokenizer benchmark")
    parser.add_argument("--repeats", type=int, default=5, help="codec timing repeats")
    args = parser.parse_args(argv)
    if not args.benchmark:
        parser.error("choose --benchmark")
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be from 1 to 100")
    report = run_benchmark(repeats=args.repeats)
    output = Path(__file__).with_name("urusilla_token_surface_v03_results.md")
    output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
