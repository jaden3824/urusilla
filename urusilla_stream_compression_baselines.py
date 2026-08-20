#!/usr/bin/env python3
"""Deterministic whole-session compression baselines for the typed corpus.

The earlier byte study compressed every message independently.  This module
measures a stronger transport assumption: all 280 messages are framed as one
ordered session and compressed by one persistent gzip, Zstandard, or Brotli
stream.  Both the canonical JSON representation and the project v0.2 warm
frames are measured under identical session boundaries.

This is an offline benchmark.  Its Brotli decoder is intentionally used only
on bytes produced in-process; it is not an untrusted-network decompressor.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
from importlib import metadata
import json
from pathlib import Path
import statistics
import struct
import time
from typing import Any, Callable, Mapping, Sequence

from urusilla_benchmark import build_corpus, corpus_digest, json_decode, json_encode
from urusilla_wire_v02 import (
    DEFAULT_PROFILE,
    decode_message as decode_v02,
    encode_capsule,
    encode_message as encode_v02,
)


MESSAGE_COUNT = 280
REQUIRED_VERSIONS = {"zstandard": "0.25.0", "Brotli": "1.2.0"}
MAX_SESSION_BYTES = 16 * 1024 * 1024
LENGTH_BYTES = 4
CHECKSUM_BYTES = 16
_JSON_RECORD_DOMAIN = b"urusilla-json-record-v1\x00"

JsonMap = dict[str, Any]
SessionEncoder = Callable[[Sequence[Mapping[str, Any]]], bytes]
SessionDecoder = Callable[[bytes], list[JsonMap]]
Compressor = Callable[[bytes], bytes]


@dataclass(frozen=True)
class CompressionProfile:
    name: str
    encode: Compressor
    decode: Compressor


@dataclass(frozen=True)
class SessionFamily:
    name: str
    encode: SessionEncoder
    decode: SessionDecoder


@dataclass(frozen=True)
class Result:
    family: str
    compression: str
    bytes_total: int
    sha256: str
    exact: bool
    deterministic: bool
    encode_p50_us: float
    encode_p95_us: float
    decode_p50_us: float
    decode_p95_us: float


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in REQUIRED_VERSIONS:
        try:
            versions[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            versions[distribution] = "missing"
    return versions


def dependencies_available(*, require_pins: bool = True) -> bool:
    versions = dependency_versions()
    if "missing" in versions.values():
        return False
    return not require_pins or versions == REQUIRED_VERSIONS


def require_dependencies() -> None:
    versions = dependency_versions()
    if versions != REQUIRED_VERSIONS:
        raise RuntimeError(
            f"stream benchmark requires {REQUIRED_VERSIONS!r}; found {versions!r}"
        )


def _pack_length_prefixed(records: Sequence[bytes]) -> bytes:
    out = bytearray()
    for record in records:
        if not isinstance(record, bytes):
            raise TypeError("session record must be bytes")
        if len(record) > MAX_SESSION_BYTES:
            raise ValueError("session record exceeds size limit")
        out += struct.pack(">I", len(record))
        out += record
    if len(out) > MAX_SESSION_BYTES:
        raise ValueError("session exceeds size limit")
    return bytes(out)


def _unpack_length_prefixed(data: bytes) -> list[bytes]:
    if not isinstance(data, bytes):
        raise TypeError("session must be bytes")
    if len(data) > MAX_SESSION_BYTES:
        raise ValueError("session exceeds size limit")
    records: list[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < LENGTH_BYTES:
            raise ValueError("truncated session length")
        length = struct.unpack_from(">I", data, offset)[0]
        offset += LENGTH_BYTES
        if length > MAX_SESSION_BYTES or length > len(data) - offset:
            raise ValueError("invalid session record length")
        records.append(data[offset : offset + length])
        offset += length
    return records


def _pack_checked_records(records: Sequence[bytes]) -> bytes:
    out = bytearray()
    for record in records:
        if not isinstance(record, bytes):
            raise TypeError("session record must be bytes")
        header = struct.pack(">I", len(record))
        checksum = hashlib.sha256(_JSON_RECORD_DOMAIN + header + record).digest()[
            :CHECKSUM_BYTES
        ]
        out += header + record + checksum
    if len(out) > MAX_SESSION_BYTES:
        raise ValueError("session exceeds size limit")
    return bytes(out)


def _unpack_checked_records(data: bytes) -> list[bytes]:
    if not isinstance(data, bytes):
        raise TypeError("session must be bytes")
    if len(data) > MAX_SESSION_BYTES:
        raise ValueError("session exceeds size limit")
    records: list[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < LENGTH_BYTES:
            raise ValueError("truncated checked-session length")
        header = data[offset : offset + LENGTH_BYTES]
        length = struct.unpack(">I", header)[0]
        offset += LENGTH_BYTES
        required = length + CHECKSUM_BYTES
        if length > MAX_SESSION_BYTES or required > len(data) - offset:
            raise ValueError("invalid checked-session record length")
        record = data[offset : offset + length]
        offset += length
        checksum = data[offset : offset + CHECKSUM_BYTES]
        offset += CHECKSUM_BYTES
        expected = hashlib.sha256(_JSON_RECORD_DOMAIN + header + record).digest()[
            :CHECKSUM_BYTES
        ]
        if checksum != expected:
            raise ValueError("checked-session record checksum mismatch")
        records.append(record)
    return records


def encode_json_session(corpus: Sequence[Mapping[str, Any]]) -> bytes:
    return _pack_length_prefixed([json_encode(message) for message in corpus])


def decode_json_session(data: bytes) -> list[JsonMap]:
    return [json_decode(record) for record in _unpack_length_prefixed(data)]


def encode_checked_json_session(corpus: Sequence[Mapping[str, Any]]) -> bytes:
    return _pack_checked_records([json_encode(message) for message in corpus])


def decode_checked_json_session(data: bytes) -> list[JsonMap]:
    return [json_decode(record) for record in _unpack_checked_records(data)]


def encode_v02_session(corpus: Sequence[Mapping[str, Any]]) -> bytes:
    return _pack_length_prefixed([encode_v02(message) for message in corpus])


def decode_v02_session(data: bytes) -> list[JsonMap]:
    return [decode_v02(record) for record in _unpack_length_prefixed(data)]


def _bounded(raw: bytes) -> bytes:
    if len(raw) > MAX_SESSION_BYTES:
        raise ValueError("decompressed session exceeds size limit")
    return raw


def _identity(data: bytes) -> bytes:
    return data


def _gzip_profile(level: int) -> CompressionProfile:
    def encode(data: bytes) -> bytes:
        return gzip.compress(data, compresslevel=level, mtime=0)

    def decode(data: bytes) -> bytes:
        return _bounded(gzip.decompress(data))

    return CompressionProfile(f"gzip-{level}", encode, decode)


def _zstd_profile(level: int) -> CompressionProfile:
    import zstandard as zstd  # type: ignore[import-not-found]

    compressor = zstd.ZstdCompressor(
        level=level,
        threads=0,
        write_content_size=True,
        write_checksum=True,
        write_dict_id=False,
    )
    decompressor = zstd.ZstdDecompressor()

    def encode(data: bytes) -> bytes:
        return compressor.compress(data)

    def decode(data: bytes) -> bytes:
        return _bounded(
            decompressor.decompress(data, max_output_size=MAX_SESSION_BYTES)
        )

    return CompressionProfile(f"zstd-{level}", encode, decode)


def _brotli_profile(quality: int) -> CompressionProfile:
    import brotli  # type: ignore[import-not-found]

    def encode(data: bytes) -> bytes:
        return brotli.compress(
            data, mode=brotli.MODE_GENERIC, quality=quality, lgwin=22
        )

    def decode(data: bytes) -> bytes:
        return _bounded(brotli.decompress(data))

    return CompressionProfile(f"brotli-{quality}", encode, decode)


def compression_profiles() -> tuple[CompressionProfile, ...]:
    require_dependencies()
    return (
        CompressionProfile("raw", _identity, _identity),
        _gzip_profile(6),
        _gzip_profile(9),
        _zstd_profile(3),
        _zstd_profile(19),
        _brotli_profile(5),
        _brotli_profile(11),
    )


def session_families() -> tuple[SessionFamily, ...]:
    return (
        SessionFamily("canonical JSON", encode_json_session, decode_json_session),
        SessionFamily(
            "checked JSON", encode_checked_json_session, decode_checked_json_session
        ),
        SessionFamily("project v0.2", encode_v02_session, decode_v02_session),
    )


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(percentile * len(ordered) + 0.999999) - 1))
    return ordered[index]


def _timings(function: Callable[[], Any], repeats: int) -> tuple[float, float]:
    function()
    values: list[int] = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        function()
        values.append(time.perf_counter_ns() - started)
    return statistics.median(values) / 1_000, _nearest_rank(values, 0.95) / 1_000


def measure(*, repeats: int = 5) -> tuple[list[Result], list[JsonMap]]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    corpus = build_corpus(MESSAGE_COUNT)
    results: list[Result] = []
    for family in session_families():
        raw = family.encode(corpus)
        if family.decode(raw) != corpus:
            raise AssertionError(f"raw {family.name} session is not exact")
        for profile in compression_profiles():
            encoded = profile.encode(raw)
            recovered_raw = profile.decode(encoded)
            recovered = family.decode(recovered_raw)
            exact = recovered == corpus
            deterministic = encoded == profile.encode(family.encode(corpus))
            if not exact or not deterministic:
                raise AssertionError(
                    f"{family.name}/{profile.name} failed exact deterministic recovery"
                )

            def encode_complete() -> bytes:
                return profile.encode(family.encode(corpus))

            def decode_complete() -> list[JsonMap]:
                return family.decode(profile.decode(encoded))

            encode_p50, encode_p95 = _timings(encode_complete, repeats)
            decode_p50, decode_p95 = _timings(decode_complete, repeats)
            results.append(
                Result(
                    family=family.name,
                    compression=profile.name,
                    bytes_total=len(encoded),
                    sha256=hashlib.sha256(encoded).hexdigest(),
                    exact=exact,
                    deterministic=deterministic,
                    encode_p50_us=encode_p50,
                    encode_p95_us=encode_p95,
                    decode_p50_us=decode_p50,
                    decode_p95_us=decode_p95,
                )
            )
    return results, corpus


def _percent_delta(candidate: int, baseline: int) -> str:
    return f"{100 * (candidate / baseline - 1):+.2f}%"


def _row(result: Result, json_raw: int) -> str:
    return (
        f"| {result.family} | {result.compression} | {result.bytes_total:,} | "
        f"{_percent_delta(result.bytes_total, json_raw)} | "
        f"{result.encode_p50_us:.1f} / {result.encode_p95_us:.1f} | "
        f"{result.decode_p50_us:.1f} / {result.decode_p95_us:.1f} | "
        f"{str(result.exact).lower()} |"
    )


def render_report(results: Sequence[Result], corpus: Sequence[Mapping[str, Any]]) -> str:
    by_key = {(result.family, result.compression): result for result in results}
    json_raw = by_key[("canonical JSON", "raw")].bytes_total
    v02_raw = by_key[("project v0.2", "raw")].bytes_total
    best_json = min(
        (row for row in results if row.family == "canonical JSON"),
        key=lambda row: row.bytes_total,
    )
    best_checked_json = min(
        (row for row in results if row.family == "checked JSON"),
        key=lambda row: row.bytes_total,
    )
    best_v02 = min(
        (row for row in results if row.family == "project v0.2"),
        key=lambda row: row.bytes_total,
    )
    capsule_bytes = len(encode_capsule(DEFAULT_PROFILE))
    corpus_sha = corpus_digest(corpus)
    versions = dependency_versions()
    rows = "\n".join(_row(result, json_raw) for result in results)
    exact_count = sum(result.exact for result in results)
    deterministic_count = sum(result.deterministic for result in results)

    return f"""# Whole-session compression baselines

## Result

This benchmark closes a declared baseline gap by compressing all
{len(corpus)} ordered messages as one persistent session instead of resetting
the compressor for every message.  Every row recovers the complete typed corpus
exactly and deterministically.

The strongest canonical-JSON row is **{best_json.compression} at
{best_json.bytes_total:,} bytes**.  The strongest project-v0.2 row is
**{best_v02.compression} at {best_v02.bytes_total:,} bytes**.  The latter is
{_percent_delta(best_v02.bytes_total, best_json.bytes_total)} relative to the
strongest bare JSON session row.  When JSON carries an equivalent independent
16-byte application checksum for every record, its strongest row is
**{best_checked_json.compression} at {best_checked_json.bytes_total:,} bytes**;
project v0.2 is {_percent_delta(best_v02.bytes_total, best_checked_json.bytes_total)}
relative to that checked row.  This is a synthetic in-domain result under a
long-lived session assumption, not a production network or universal codec
ranking.

## Frozen inputs

- Corpus messages: {len(corpus)}
- Corpus SHA-256: `{corpus_sha}`
- Session framing: unsigned four-byte big-endian length before every record
- Checked-JSON framing: the same length plus a 16-byte truncated SHA-256 record checksum
- v0.2 profile capsule: {capsule_bytes:,} bytes when not already cached
- zstandard: `{versions['zstandard']}`
- Brotli: `{versions['Brotli']}`
- Compression is deterministic and single-threaded under the pinned runtime

## Complete-session measurements

| Representation | Compression | Bytes | Delta vs raw JSON | Encode p50 / p95 us | Decode p50 / p95 us | Exact |
|---|---|---:|---:|---:|---:|---:|
{rows}

Exact recovery: **{exact_count}/{len(results)}** rows.  Deterministic bytes:
**{deterministic_count}/{len(results)}** rows.

Raw length framing adds {MESSAGE_COUNT * LENGTH_BYTES:,} bytes to bare JSON and
project v0.2.  Checked JSON adds another
{MESSAGE_COUNT * CHECKSUM_BYTES:,} bytes before compression.  The raw JSON
session is {json_raw:,} bytes and the raw v0.2 session is {v02_raw:,} bytes.
Adding the one-time v0.2 profile capsule to a cold session is reported
separately; it is not silently added to warm rows.

## Interpretation

- Persistent general-purpose compression is a materially stronger baseline
  than independent per-message gzip.  Any byte-efficiency claim must name the
  session and reset assumptions.
- Bare JSON assumes stream-level integrity or authenticated transport and does
  not provide independently verifiable record checksums.  Checked JSON isolates
  the cost of matching the v0.2 per-record accidental-corruption contract.
- A persistent compressor can exploit repetition across message boundaries;
  per-frame checksums and already compact numeric fields can reduce the extra
  redundancy available in the binary representation.
- The project still supplies typed semantics, validation, provenance, and
  state transitions.  Those benefits are not established by a byte table and
  must be evaluated separately.
- Whole-session buffering increases failure scope and may not fit streaming,
  low-latency, packet-loss, or independently cacheable message requirements.

## Limitations

- The corpus is generated by this repository and the v0.2 profile is tailored
  to its schema family.
- One ordered 280-message batch is measured.  Session lengths, reset points,
  dictionaries, packet loss, and multiplexing are not varied.
- The four-byte framing is simple and exact but not the only possible framing.
- Brotli decompression here is an offline benchmark path, not a resource-safe
  untrusted-input implementation.
- Timings include serialization, validation, session framing, and compression;
  they are Python implementation-path measurements on one machine.
- No task success, model tokens, energy, memory peak, TLS, HTTP/2 or HTTP/3,
  network latency, or dollar cost is measured.

## Reproduction

From the repository root in the pinned Python 3.12 research environment:

```bash
python -m pip install zstandard==0.25.0 Brotli==1.2.0
python urusilla_stream_compression_baselines.py --output STREAM_COMPRESSION_RESULTS.md
python -m unittest test_urusilla_stream_compression_baselines
```
"""


def run(*, repeats: int = 5) -> tuple[str, list[Result]]:
    results, corpus = measure(repeats=repeats)
    return render_report(results, corpus), results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report, _ = run(repeats=args.repeats)
    if args.output is None:
        print(report)
    else:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
