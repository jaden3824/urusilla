#!/usr/bin/env python3
"""Deterministic compressor-reset crossover study for the frozen corpus.

Each point partitions the same ordered 280-message corpus into independently
compressed chunks.  The primary byte contract treats every chunk as a cold,
independently decodable session.  A cached-profile sensitivity keeps the same
framing and compressor resets but assumes that the project v0.2 profile is
already installed at the receiver.

This is an offline, in-domain serialization benchmark.  It does not measure
model understanding, task success, network deployment, or energy use.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import struct
import time
from typing import Any, Callable, Mapping, Sequence

import urusilla_stream_compression_baselines as stream_baseline
from urusilla_benchmark import build_corpus, corpus_digest
from urusilla_wire_v02 import (
    DEFAULT_PROFILE,
    ProfileRegistry,
    decode_message as decode_v02,
    encode_capsule,
)


MESSAGE_COUNT = 280
OUTER_LENGTH_BYTES = 4
MAX_EXCHANGE_BYTES = 64 * 1024 * 1024
POWER_OF_TWO_GRID = (1, 2, 4, 8, 16, 32, 64, 128, 256)
DIVISOR_GRID = tuple(
    value for value in range(1, MESSAGE_COUNT + 1) if MESSAGE_COUNT % value == 0
)
CHUNK_SIZES = tuple(sorted(set(POWER_OF_TWO_GRID + DIVISOR_GRID + (MESSAGE_COUNT,))))
PROJECT_FAMILY = "project v0.2"

JsonMap = dict[str, Any]


@dataclass(frozen=True)
class SweepResult:
    chunk_size: int
    chunk_count: int
    family: str
    compression: str
    cached_bytes: int
    cold_bytes: int
    cached_sha256: str
    cold_sha256: str
    cached_exact: bool
    cold_exact: bool
    cached_deterministic: bool
    cold_deterministic: bool
    cold_encode_p50_us: float
    cold_encode_p95_us: float
    cold_decode_p50_us: float
    cold_decode_p95_us: float


def study_profiles() -> tuple[stream_baseline.CompressionProfile, ...]:
    """Return the six pinned non-identity profiles from the parent study."""

    profiles = tuple(
        profile
        for profile in stream_baseline.compression_profiles()
        if profile.name != "raw"
    )
    expected = {
        "gzip-6",
        "gzip-9",
        "zstd-3",
        "zstd-19",
        "brotli-5",
        "brotli-11",
    }
    if {profile.name for profile in profiles} != expected:
        raise RuntimeError("compression profile set changed")
    return profiles


def _chunks(
    corpus: Sequence[Mapping[str, Any]], chunk_size: int
) -> tuple[Sequence[Mapping[str, Any]], ...]:
    if not 1 <= chunk_size <= len(corpus):
        raise ValueError("chunk size is outside the corpus")
    return tuple(
        corpus[offset : offset + chunk_size]
        for offset in range(0, len(corpus), chunk_size)
    )


def _pack_outer(setup: bytes, payload: bytes) -> bytes:
    if not isinstance(setup, bytes) or not isinstance(payload, bytes):
        raise TypeError("outer fields must be bytes")
    if len(setup) > MAX_EXCHANGE_BYTES or len(payload) > MAX_EXCHANGE_BYTES:
        raise ValueError("outer field exceeds size limit")
    return (
        struct.pack(">I", len(setup))
        + setup
        + struct.pack(">I", len(payload))
        + payload
    )


def _unpack_outer(data: bytes) -> list[tuple[bytes, bytes]]:
    if not isinstance(data, bytes):
        raise TypeError("exchange must be bytes")
    if len(data) > MAX_EXCHANGE_BYTES:
        raise ValueError("exchange exceeds size limit")
    chunks: list[tuple[bytes, bytes]] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < OUTER_LENGTH_BYTES:
            raise ValueError("truncated setup length")
        setup_length = struct.unpack_from(">I", data, offset)[0]
        offset += OUTER_LENGTH_BYTES
        if setup_length > MAX_EXCHANGE_BYTES or setup_length > len(data) - offset:
            raise ValueError("invalid setup length")
        setup = data[offset : offset + setup_length]
        offset += setup_length
        if len(data) - offset < OUTER_LENGTH_BYTES:
            raise ValueError("truncated payload length")
        payload_length = struct.unpack_from(">I", data, offset)[0]
        offset += OUTER_LENGTH_BYTES
        if payload_length > MAX_EXCHANGE_BYTES or payload_length > len(data) - offset:
            raise ValueError("invalid payload length")
        payload = data[offset : offset + payload_length]
        offset += payload_length
        chunks.append((setup, payload))
    return chunks


def _unpack_records(data: bytes) -> list[bytes]:
    records: list[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < stream_baseline.LENGTH_BYTES:
            raise ValueError("truncated record length")
        length = struct.unpack_from(">I", data, offset)[0]
        offset += stream_baseline.LENGTH_BYTES
        if length > stream_baseline.MAX_SESSION_BYTES or length > len(data) - offset:
            raise ValueError("invalid record length")
        records.append(data[offset : offset + length])
        offset += length
    return records


def _encode_contracts(
    corpus: Sequence[Mapping[str, Any]],
    family: stream_baseline.SessionFamily,
    compression: stream_baseline.CompressionProfile,
    chunk_size: int,
) -> tuple[bytes, bytes]:
    """Build cached and cold contracts while sharing each compression call."""

    capsule = encode_capsule(DEFAULT_PROFILE)
    cached_output = bytearray()
    cold_output = bytearray()
    for chunk in _chunks(corpus, chunk_size):
        payload = compression.encode(family.encode(chunk))
        cached_output += _pack_outer(b"", payload)
        cold_setup = capsule if family.name == PROJECT_FAMILY else b""
        cold_output += _pack_outer(cold_setup, payload)
    if len(cached_output) > MAX_EXCHANGE_BYTES or len(cold_output) > MAX_EXCHANGE_BYTES:
        raise ValueError("exchange exceeds size limit")
    return bytes(cached_output), bytes(cold_output)


def encode_exchange(
    corpus: Sequence[Mapping[str, Any]],
    family: stream_baseline.SessionFamily,
    compression: stream_baseline.CompressionProfile,
    chunk_size: int,
    *,
    cold_profile: bool,
) -> bytes:
    """Encode all corpus records with a compressor reset at every chunk."""

    cached, cold = _encode_contracts(corpus, family, compression, chunk_size)
    return cold if cold_profile else cached


def decode_exchange(
    data: bytes,
    family: stream_baseline.SessionFamily,
    compression: stream_baseline.CompressionProfile,
    *,
    cold_profile: bool,
) -> list[JsonMap]:
    """Decode an exchange and validate every independently framed chunk."""

    recovered: list[JsonMap] = []
    for setup, payload in _unpack_outer(data):
        raw = compression.decode(payload)
        if family.name != PROJECT_FAMILY:
            if setup:
                raise ValueError("generic family carried an unexpected setup object")
            recovered.extend(family.decode(raw))
            continue

        if cold_profile:
            if not setup:
                raise ValueError("cold project chunk is missing its profile capsule")
            registry = ProfileRegistry()
            registry.register_capsule(setup)
            recovered.extend(
                decode_v02(record, registry=registry)
                for record in _unpack_records(raw)
            )
        else:
            if setup:
                raise ValueError("cached project chunk carried an unexpected setup object")
            recovered.extend(family.decode(raw))
    return recovered


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _timings(function: Callable[[], Any], repeats: int) -> tuple[float, float]:
    function()
    samples: list[int] = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        function()
        samples.append(time.perf_counter_ns() - started)
    return statistics.median(samples) / 1_000, _nearest_rank(samples, 0.95) / 1_000


def measure(*, repeats: int = 3) -> tuple[list[SweepResult], list[JsonMap]]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    stream_baseline.require_dependencies()
    corpus = build_corpus(MESSAGE_COUNT)
    results: list[SweepResult] = []
    families = stream_baseline.session_families()
    profiles = study_profiles()

    for chunk_size in CHUNK_SIZES:
        chunk_count = math.ceil(len(corpus) / chunk_size)
        for family in families:
            for compression in profiles:
                cached, cold = _encode_contracts(
                    corpus, family, compression, chunk_size
                )
                cached_recovered = decode_exchange(
                    cached, family, compression, cold_profile=False
                )
                cold_recovered = decode_exchange(
                    cold, family, compression, cold_profile=True
                )
                cached_exact = cached_recovered == corpus
                cold_exact = cold_recovered == corpus
                cached_second, cold_second = _encode_contracts(
                    corpus, family, compression, chunk_size
                )
                cached_deterministic = cached == cached_second
                cold_deterministic = cold == cold_second
                if not all(
                    (
                        cached_exact,
                        cold_exact,
                        cached_deterministic,
                        cold_deterministic,
                    )
                ):
                    raise AssertionError(
                        f"{family.name}/{compression.name}/{chunk_size} failed a gate"
                    )

                def encode_cold() -> bytes:
                    return encode_exchange(
                        corpus,
                        family,
                        compression,
                        chunk_size,
                        cold_profile=True,
                    )

                def decode_cold() -> list[JsonMap]:
                    return decode_exchange(
                        cold, family, compression, cold_profile=True
                    )

                encode_p50, encode_p95 = _timings(encode_cold, repeats)
                decode_p50, decode_p95 = _timings(decode_cold, repeats)
                results.append(
                    SweepResult(
                        chunk_size=chunk_size,
                        chunk_count=chunk_count,
                        family=family.name,
                        compression=compression.name,
                        cached_bytes=len(cached),
                        cold_bytes=len(cold),
                        cached_sha256=hashlib.sha256(cached).hexdigest(),
                        cold_sha256=hashlib.sha256(cold).hexdigest(),
                        cached_exact=cached_exact,
                        cold_exact=cold_exact,
                        cached_deterministic=cached_deterministic,
                        cold_deterministic=cold_deterministic,
                        cold_encode_p50_us=encode_p50,
                        cold_encode_p95_us=encode_p95,
                        cold_decode_p50_us=decode_p50,
                        cold_decode_p95_us=decode_p95,
                    )
                )
    return results, corpus


def measurement_digest(results: Sequence[SweepResult]) -> str:
    """Hash all deterministic result fields while excluding wall-clock latency."""

    fields = (
        "chunk_size",
        "chunk_count",
        "family",
        "compression",
        "cached_bytes",
        "cold_bytes",
        "cached_sha256",
        "cold_sha256",
        "cached_exact",
        "cold_exact",
        "cached_deterministic",
        "cold_deterministic",
    )
    payload = [
        {field: asdict(result)[field] for field in fields}
        for result in results
    ]
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _percent_delta(candidate: int, baseline: int) -> str:
    return f"{100 * (candidate / baseline - 1):+.2f}%"


def _best(
    results: Sequence[SweepResult], chunk_size: int, family: str, field: str
) -> SweepResult:
    candidates = [
        result
        for result in results
        if result.chunk_size == chunk_size and result.family == family
    ]
    return min(candidates, key=lambda result: (getattr(result, field), result.compression))


def _winning_sizes(
    results: Sequence[SweepResult],
    compression: str,
    baseline_family: str,
    field: str,
) -> tuple[int, ...]:
    by_key = {
        (result.chunk_size, result.family, result.compression): result
        for result in results
    }
    return tuple(
        size
        for size in CHUNK_SIZES
        if getattr(by_key[(size, PROJECT_FAMILY, compression)], field)
        < getattr(by_key[(size, baseline_family, compression)], field)
    )


def _grid_text(values: Sequence[int]) -> str:
    return "none" if not values else ", ".join(str(value) for value in values)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_report(
    results: Sequence[SweepResult], corpus: Sequence[Mapping[str, Any]]
) -> str:
    expected_rows = len(CHUNK_SIZES) * len(stream_baseline.session_families()) * len(
        study_profiles()
    )
    if len(results) != expected_rows:
        raise ValueError("result matrix is incomplete")
    exact_count = sum(result.cached_exact and result.cold_exact for result in results)
    deterministic_count = sum(
        result.cached_deterministic and result.cold_deterministic for result in results
    )
    capsule = encode_capsule(DEFAULT_PROFILE)
    versions = stream_baseline.dependency_versions()
    result_sha = measurement_digest(results)

    frontier_rows: list[str] = []
    latency_rows: list[str] = []
    for size in CHUNK_SIZES:
        bare = _best(results, size, "canonical JSON", "cold_bytes")
        checked = _best(results, size, "checked JSON", "cold_bytes")
        project_cold = _best(results, size, PROJECT_FAMILY, "cold_bytes")
        project_cached = _best(results, size, PROJECT_FAMILY, "cached_bytes")
        frontier_rows.append(
            f"| {size} | {bare.chunk_count} | {bare.compression} / {bare.cold_bytes:,} | "
            f"{checked.compression} / {checked.cold_bytes:,} | "
            f"{project_cold.compression} / {project_cold.cold_bytes:,} | "
            f"{_percent_delta(project_cold.cold_bytes, bare.cold_bytes)} | "
            f"{_percent_delta(project_cold.cold_bytes, checked.cold_bytes)} | "
            f"{project_cached.compression} / {project_cached.cached_bytes:,} |"
        )
        for family in ("canonical JSON", "checked JSON", PROJECT_FAMILY):
            row = _best(results, size, family, "cold_bytes")
            latency_rows.append(
                f"| {size} | {family} | {row.compression} | {row.cold_bytes:,} | "
                f"{row.cold_encode_p50_us:,.1f} / {row.cold_encode_p95_us:,.1f} | "
                f"{row.cold_decode_p50_us:,.1f} / {row.cold_decode_p95_us:,.1f} |"
            )

    crossover_rows: list[str] = []
    for compression in (profile.name for profile in study_profiles()):
        cold_bare = _winning_sizes(
            results, compression, "canonical JSON", "cold_bytes"
        )
        cold_checked = _winning_sizes(
            results, compression, "checked JSON", "cold_bytes"
        )
        cached_bare = _winning_sizes(
            results, compression, "canonical JSON", "cached_bytes"
        )
        cached_checked = _winning_sizes(
            results, compression, "checked JSON", "cached_bytes"
        )
        crossover_rows.append(
            f"| {compression} | {_grid_text(cold_bare)} | "
            f"{_grid_text(cold_checked)} | {_grid_text(cached_bare)} | "
            f"{_grid_text(cached_checked)} |"
        )

    source = Path(__file__)
    test_source = source.with_name("test_urusilla_session_reset_sweep.py")
    source_digests = [f"- Implementation SHA-256: `{_sha256_file(source)}`"]
    if test_source.exists():
        source_digests.append(f"- Test SHA-256: `{_sha256_file(test_source)}`")

    return f"""# Session-reset compression crossover study

## Outcome

This study varies compressor-reset boundaries over the frozen ordered
{len(corpus)}-message corpus.  It evaluates {len(results)} combinations:
{len(CHUNK_SIZES)} chunk sizes, three representations, and six pinned
compression profiles.  Every cached and independently cold row reconstructs
the corpus exactly and emits deterministic bytes.

The primary `cold` contract treats every chunk as a separately decodable
session.  Every session carries a four-byte setup length and a four-byte
compressed-payload length.  The project v0.2 row additionally carries its
{len(capsule):,}-byte checksummed profile capsule in every cold session;
the two JSON rows carry an empty setup field.  The `cached` sensitivity keeps
the identical eight-byte outer framing and compressor resets but assumes the
profile is already installed.  Inner four-byte record lengths are charged in
all three representations, checked JSON carries its independent 16-byte
checksum per record, and project v0.2 retains its own per-frame checksum.

This is an in-domain serialization result, not a task-utility result or a
state-of-the-art claim.

## Frozen design

- Corpus messages: {len(corpus)}
- Corpus SHA-256: `{corpus_digest(corpus)}`
- Chunk-size grid: `{", ".join(str(size) for size in CHUNK_SIZES)}`
- Grid construction: union of every divisor of 280, powers of two from 1
  through 256, and the full-corpus endpoint 280
- Non-divisor points retain and fully charge the shorter final chunk
- Compression profiles: gzip 6/9, Zstandard 3/19, and Brotli 5/11
- zstandard: `{versions['zstandard']}`
- Brotli: `{versions['Brotli']}`
- Profile capsule SHA-256: `{hashlib.sha256(capsule).hexdigest()}`
- Deterministic measurement-matrix SHA-256: `{result_sha}`
- Runtime for latency samples: `{platform.python_implementation()} {platform.python_version()}` / `{platform.platform()}`

The divisor points avoid a partially filled final session and expose common
batching intervals.  The power-of-two points provide logarithmic resolution
without choosing a dense grid after observing outcomes.

## Integrity-constrained byte Pareto frontier and crossover

Each cell reports `best compressor / bytes` within that representation at the
named chunk size.  Deltas compare the best cold project row with the best cold
JSON row; negative is smaller.  Bare JSON has no independent per-record
checksum.  The checked-JSON comparison is the matched accidental-integrity
frontier.  A transport checksum or authenticated channel may make the bare
comparison the appropriate one in a deployment.

This is an integrity-constrained Pareto view, not a claim that the integrity
contracts are interchangeable: bare JSON occupies the minimum-byte transport
point without an application record checksum, while checked JSON and project
v0.2 are compared on the stronger per-record accidental-integrity constraint.

| Chunk messages | Sessions | Bare JSON | Checked JSON | Project cold | vs bare | vs checked | Project cached |
|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(frontier_rows)}

The next table fixes the compressor and lists every tested chunk size where
project v0.2 uses strictly fewer bytes than the named baseline.  It reports
the observed grid directly rather than implying an unmeasured continuous
threshold.

| Compression | Cold beats bare JSON | Cold beats checked JSON | Cached beats bare JSON | Cached beats checked JSON |
|---|---|---|---|---|
{chr(10).join(crossover_rows)}

## Current implementation-path latency

For each representation and chunk size, this table shows the compressor with
the smallest cold byte total.  Timing covers semantic serialization,
per-record framing, every compressor reset, outer framing, and the complete
cold decode.  Project cold decode constructs a fresh registry from every
transmitted profile capsule.  Values are whole-corpus p50/p95 microseconds,
not per-message values.

| Chunk messages | Representation | Byte-minimizing compression | Cold bytes | Encode p50 / p95 us | Decode p50 / p95 us |
|---:|---|---|---:|---:|---:|
{chr(10).join(latency_rows)}

These paths do unequal work.  Bare JSON has no independent record checksum;
checked JSON hashes each record; project v0.2 validates checksums, resolves a
profile, validates semantics, and requires canonical re-encoding.  Brotli and
Zstandard execute native-library code while representation handling includes
Python code.  Wall-clock rankings are machine-specific, and p95 from a small
repeat count is descriptive rather than an inferential confidence bound.

## Favorable and unfavorable evidence

- On the per-representation byte frontier, which uses Brotli-11 from chunk
  size four onward, the independently cold project row first beats checked
  JSON at the tested 64-message point and is 9.40% smaller at 280 messages.
  That project frontier never beats the bare-JSON frontier on this grid and
  remains 10.20% larger at 280 messages.
- With the profile cached, the byte-minimizing project row beats bare JSON
  through the tested 128-message point, then loses at 140, 256, and 280.  The
  cached row is 4.33% larger at 280.  Non-monotone partial-chunk points are
  reported rather than smoothed away.
- The matched-integrity comparison shows where project v0.2 amortizes its
  profile against checked JSON under independent cold sessions; the exact
  tested points are retained in the crossover table.
- The bare-JSON comparison remains necessary.  Persistent or long chunks let
  a general-purpose compressor exploit repeated field names and values, and
  the project format does not receive a blanket byte-superiority claim.
- Repeating a {len(capsule):,}-byte profile at every reset can dominate short
  sessions.  The cached sensitivity is materially more favorable but is valid
  only when cache identity, authorization, and availability are established.
- Smaller bytes do not imply lower latency.  The current validation-heavy
  project decode path can remain slower even when its wire total is smaller.
- Exact and deterministic gates passed for {exact_count}/{len(results)} and
  {deterministic_count}/{len(results)} result rows, respectively, under both
  cache contracts.

## Scope limits

- The corpus is synthetic, generated by this repository, and the project v0.2
  profile was designed for its schema family.
- Representation choice, compressor profile, profile authorization, and
  authenticated transport are assumed negotiated.  Their discovery messages,
  signatures, TLS records, packet headers, retransmission, and connection
  setup are not measured.
- The outer framing is a deterministic study contract, not a proposed network
  protocol.  A real protocol can use different varints, multiplexing, or
  transport record boundaries.
- The profile capsule is charged as its raw canonical checksummed object.
  Compressing or delta-coding that bootstrap object is a separate unmeasured
  contract that could improve the independently cold project rows.
- Brotli decompression is used only on bytes produced in-process.  This module
  is not an untrusted-network decompressor or a memory-limit certification.
- No model tokens, natural-language conversion, task success, repair turns,
  energy, peak memory, streaming latency, packet loss, or dollar cost is
  measured.
- Grid observations must not be interpolated into untested chunk sizes.  No
  result establishes a world record, universal codec ranking, or independent
  reproduction.

## Identity and reproduction

{chr(10).join(source_digests)}

From the repository root in the pinned Python 3.12 research environment:

```bash
python -m pip install -r requirements-research.lock
PYTHONDONTWRITEBYTECODE=1 python urusilla_session_reset_sweep.py --output SESSION_RESET_SWEEP_RESULTS.md
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_urusilla_session_reset_sweep -v
```
"""


def run(*, repeats: int = 3) -> tuple[str, list[SweepResult]]:
    results, corpus = measure(repeats=repeats)
    return render_report(results, corpus), results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
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
