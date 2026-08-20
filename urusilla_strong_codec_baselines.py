#!/usr/bin/env python3
"""Independent strong-codec baselines for the 280-message Urusilla corpus.

This study compares UrusillaWire v0.2 warm frames with sorted minified JSON,
per-message gzip JSON, deterministic CBOR, a runtime-deterministic MessagePack
profile, and a schema-equivalent Protobuf representation.  External packages
are research-only dependencies and are deliberately absent from the core
package metadata.

The benchmark starts from already-structured semantic objects.  It measures
serialization bytes and local codec time, not model tokens, task success,
translation quality, transport headers, or negotiation round trips.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

from urusilla_benchmark import CORPUS_VERSION, build_corpus, corpus_digest
from urusilla_deterministic_gzip import compress as deterministic_gzip_compress
from urusilla import normalize_message
import urusilla_wire_v02


PINNED_PACKAGES = {
    "cbor2": "6.1.4",
    "msgpack": "1.2.1",
    "protobuf": "7.35.1",
    "grpcio-tools": "1.83.0",
}
DEFAULT_MESSAGES = 280
DEFAULT_REPEATS = 20
DEFAULT_WARMUPS = 2
PROTO_PATH = Path(__file__).with_name("urusilla_strong_codec_baseline.proto")
DEFAULT_OUTPUT = Path(__file__).with_name("urusilla_strong_codec_results.md")


try:
    import cbor2  # type: ignore[import-not-found]
    import msgpack  # type: ignore[import-not-found]
    from grpc_tools import protoc  # type: ignore[import-not-found]
except ImportError as exc:  # Keep dependency-free core test discovery healthy.
    cbor2 = None  # type: ignore[assignment]
    msgpack = None  # type: ignore[assignment]
    protoc = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = exc
else:
    _IMPORT_ERROR = None


JsonMap = dict[str, Any]
Encoder = Callable[[Mapping[str, Any]], bytes]
Decoder = Callable[[bytes], JsonMap]


@dataclass(frozen=True)
class Codec:
    name: str
    encode: Encoder
    decode: Decoder
    determinism: str
    qualification: str


@dataclass(frozen=True)
class CodecResult:
    name: str
    sizes: tuple[int, ...]
    encode_ns: tuple[int, ...]
    decode_ns: tuple[int, ...]
    exact: int
    byte_stable: int


@dataclass(frozen=True)
class ProtoRuntime:
    module: Any
    descriptor_set: bytes


_PROTO_TEMPORARIES: list[tempfile.TemporaryDirectory[str]] = []
_PROTO_RUNTIME: ProtoRuntime | None = None


def dependency_versions() -> dict[str, str]:
    """Return installed study dependency versions without importing the core."""

    versions: dict[str, str] = {}
    for distribution in PINNED_PACKAGES:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not installed"
    return versions


def dependencies_available(*, require_pins: bool = True) -> bool:
    if _IMPORT_ERROR is not None:
        return False
    versions = dependency_versions()
    if require_pins and any(
        versions[name] != expected for name, expected in PINNED_PACKAGES.items()
    ):
        return False
    return True


def require_dependencies() -> None:
    if _IMPORT_ERROR is not None:
        pins = " ".join(f"'{name}=={version}'" for name, version in PINNED_PACKAGES.items())
        raise RuntimeError(
            "research codec dependencies are unavailable; create a work-only virtual "
            f"environment and install {pins}"
        ) from _IMPORT_ERROR
    versions = dependency_versions()
    mismatches = {
        name: (versions[name], expected)
        for name, expected in PINNED_PACKAGES.items()
        if versions[name] != expected
    }
    if mismatches:
        details = ", ".join(
            f"{name}: installed {actual}, expected {expected}"
            for name, (actual, expected) in mismatches.items()
        )
        raise RuntimeError(f"study dependency pins do not match: {details}")


def load_proto_runtime() -> ProtoRuntime:
    """Compile the declared schema into an isolated temporary directory once."""

    global _PROTO_RUNTIME
    if _PROTO_RUNTIME is not None:
        return _PROTO_RUNTIME
    require_dependencies()
    if not PROTO_PATH.is_file():
        raise RuntimeError(f"declared Protobuf schema is missing: {PROTO_PATH}")

    temporary = tempfile.TemporaryDirectory(prefix="urusilla-proto-")
    _PROTO_TEMPORARIES.append(temporary)
    output_dir = Path(temporary.name)
    descriptor_path = output_dir / "schema.pb"
    result = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{PROTO_PATH.parent}",
            f"--python_out={output_dir}",
            f"--descriptor_set_out={descriptor_path}",
            str(PROTO_PATH),
        ]
    )
    if result != 0:
        raise RuntimeError(f"protoc failed with status {result}")
    generated_path = output_dir / "urusilla_strong_codec_baseline_pb2.py"
    spec = importlib.util.spec_from_file_location(
        "_urusilla_strong_codec_baseline_pb2", generated_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generated Protobuf module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _PROTO_RUNTIME = ProtoRuntime(module, descriptor_path.read_bytes())
    return _PROTO_RUNTIME


def _canonical_tree(value: Any) -> Any:
    """Normalize collection ordering for deterministic library encoders."""

    if isinstance(value, Mapping):
        return {
            key: _canonical_tree(value[key])
            for key in sorted(value, key=lambda item: item.encode("utf-8"))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_tree(item) for item in value]
    return value


def sorted_json_encode(message: Mapping[str, Any]) -> bytes:
    canonical = _canonical_tree(normalize_message(message))
    return json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sorted_json_decode(frame: bytes) -> JsonMap:
    value = json.loads(frame.decode("utf-8"))
    return normalize_message(value)


def gzip_json_encode(message: Mapping[str, Any]) -> bytes:
    return deterministic_gzip_compress(sorted_json_encode(message), compresslevel=6)


def gzip_json_decode(frame: bytes) -> JsonMap:
    return sorted_json_decode(gzip.decompress(frame))


def cbor_encode(message: Mapping[str, Any]) -> bytes:
    if cbor2 is None:
        raise RuntimeError("cbor2 is unavailable")
    canonical = _canonical_tree(normalize_message(message))
    return cbor2.dumps(canonical, canonical=True)


def cbor_decode(frame: bytes) -> JsonMap:
    if cbor2 is None:
        raise RuntimeError("cbor2 is unavailable")
    return normalize_message(cbor2.loads(frame))


def msgpack_encode(message: Mapping[str, Any]) -> bytes:
    if msgpack is None:
        raise RuntimeError("msgpack is unavailable")
    canonical = _canonical_tree(normalize_message(message))
    return msgpack.packb(
        canonical,
        use_bin_type=True,
        strict_types=True,
        use_single_float=False,
    )


def msgpack_decode(frame: bytes) -> JsonMap:
    if msgpack is None:
        raise RuntimeError("msgpack is unavailable")
    value = msgpack.unpackb(
        frame,
        raw=False,
        strict_map_key=True,
        use_list=True,
    )
    return normalize_message(value)


ACT_TO_PROTO = {
    "ASSERT": 1,
    "QUERY": 2,
    "REQUEST": 3,
    "PROPOSE": 4,
    "COMMIT": 5,
    "RESOLVE": 6,
    "RETRACT": 7,
}
PROTO_TO_ACT = {value: key for key, value in ACT_TO_PROTO.items()}


def _fill_proto_value(target: Any, value: Any) -> None:
    if value is None:
        target.null_value = 0
    elif type(value) is bool:
        target.bool_value = value
    elif type(value) is int:
        if value < 0:
            target.signed_integer = value
        else:
            target.unsigned_integer = value
    elif type(value) is float:
        target.float64_value = value
    elif type(value) is str:
        target.string_value = value
    elif type(value) is bytes:
        target.bytes_value = value
    elif isinstance(value, (list, tuple)):
        for item in value:
            _fill_proto_value(target.list_value.items.add(), item)
    elif isinstance(value, Mapping):
        for key in sorted(value, key=lambda item: item.encode("utf-8")):
            entry = target.map_value.entries.add()
            entry.key = key
            _fill_proto_value(entry.value, value[key])
    else:
        raise TypeError(f"unsupported semantic value: {type(value).__name__}")


def _proto_value_to_python(source: Any) -> Any:
    selected = source.WhichOneof("value")
    if selected == "null_value":
        return None
    if selected == "bool_value":
        return source.bool_value
    if selected == "signed_integer":
        return source.signed_integer
    if selected == "unsigned_integer":
        return source.unsigned_integer
    if selected == "float64_value":
        return source.float64_value
    if selected == "string_value":
        return source.string_value
    if selected == "bytes_value":
        return bytes(source.bytes_value)
    if selected == "list_value":
        return [_proto_value_to_python(item) for item in source.list_value.items]
    if selected == "map_value":
        result: dict[str, Any] = {}
        for entry in source.map_value.entries:
            if entry.key in result:
                raise ValueError(f"duplicate semantic map key: {entry.key!r}")
            result[entry.key] = _proto_value_to_python(entry.value)
        return result
    raise ValueError("Protobuf SemanticValue has no selected value")


def _uuid_from_bytes(raw: bytes, field: str) -> str:
    if len(raw) != 16:
        raise ValueError(f"Protobuf {field} must contain exactly 16 bytes")
    return str(uuid.UUID(bytes=raw))


def protobuf_encode(message: Mapping[str, Any]) -> bytes:
    runtime = load_proto_runtime()
    canonical = normalize_message(message)
    encoded = runtime.module.AgentMessage()
    encoded.id = uuid.UUID(canonical["id"]).bytes
    encoded.session = uuid.UUID(canonical["session"]).bytes
    encoded.sender = canonical["sender"]
    encoded.recipients.extend(canonical["recipients"])
    encoded.act = ACT_TO_PROTO[canonical["act"]]
    if canonical["reply_to"] is not None:
        encoded.reply_to = uuid.UUID(canonical["reply_to"]).bytes
    encoded.schema = canonical["schema"]
    encoded.logical_clock = canonical["logical_clock"]
    encoded.expires_ms = canonical["expires_ms"]
    if canonical["confidence_ppm"] is not None:
        encoded.confidence_ppm = canonical["confidence_ppm"]
    encoded.expected.extend(ACT_TO_PROTO[item] for item in canonical["expected"])
    _fill_proto_value(encoded.body, canonical["body"])
    _fill_proto_value(encoded.meta, canonical["meta"])
    return encoded.SerializeToString(deterministic=True)


def protobuf_decode(frame: bytes) -> JsonMap:
    runtime = load_proto_runtime()
    encoded = runtime.module.AgentMessage()
    encoded.ParseFromString(frame)
    if encoded.act not in PROTO_TO_ACT:
        raise ValueError(f"unknown or missing Protobuf act value: {encoded.act}")
    if not encoded.HasField("body") or not encoded.HasField("meta"):
        raise ValueError("Protobuf message must carry body and meta values")
    expected: list[str] = []
    for item in encoded.expected:
        if item not in PROTO_TO_ACT:
            raise ValueError(f"unknown Protobuf expected-act value: {item}")
        expected.append(PROTO_TO_ACT[item])
    decoded = {
        "id": _uuid_from_bytes(bytes(encoded.id), "id"),
        "session": _uuid_from_bytes(bytes(encoded.session), "session"),
        "sender": encoded.sender,
        "recipients": list(encoded.recipients),
        "act": PROTO_TO_ACT[encoded.act],
        "reply_to": (
            _uuid_from_bytes(bytes(encoded.reply_to), "reply_to")
            if encoded.HasField("reply_to")
            else None
        ),
        "schema": encoded.schema,
        "logical_clock": encoded.logical_clock,
        "expires_ms": encoded.expires_ms,
        "confidence_ppm": (
            encoded.confidence_ppm if encoded.HasField("confidence_ppm") else None
        ),
        "expected": expected,
        "body": _proto_value_to_python(encoded.body),
        "meta": _proto_value_to_python(encoded.meta),
    }
    return normalize_message(decoded)


def available_codecs() -> tuple[Codec, ...]:
    require_dependencies()
    return (
        Codec(
            "sorted minified JSON",
            sorted_json_encode,
            sorted_json_decode,
            "byte-stable Python study profile; not claimed as RFC 8785",
            "UTF-8 text; no per-frame integrity field",
        ),
        Codec(
            "per-message gzip JSON",
            gzip_json_encode,
            gzip_json_decode,
            "gzip level 6 with mtime=0 over the sorted JSON profile",
            "independent gzip member per message; no application checksum",
        ),
        Codec(
            "deterministic CBOR",
            cbor_encode,
            cbor_decode,
            "cbor2 canonical=True",
            "generic semantic map; no schema dictionary or checksum",
        ),
        Codec(
            "MessagePack",
            msgpack_encode,
            msgpack_decode,
            "sorted-map, binary64, msgpack 1.2.1 runtime profile",
            "MessagePack has no universal canonical encoding standard",
        ),
        Codec(
            "schema-equivalent Protobuf",
            protobuf_encode,
            protobuf_decode,
            "deterministic=True within the pinned Protobuf runtime",
            "typed top-level fields plus recursive lossless SemanticValue",
        ),
        Codec(
            "UrusillaWire v0.2 warm",
            urusilla_wire_v02.encode_message,
            urusilla_wire_v02.decode_message,
            "normative v0.2 canonical re-encoding check",
            "includes profile identifier, dictionary fingerprint, and 16-byte checksum",
        ),
    )


def nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires samples")
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def warm_up(codecs: Sequence[Codec], corpus: Sequence[JsonMap], rounds: int) -> None:
    for _ in range(rounds):
        for codec in codecs:
            for message in corpus:
                codec.decode(codec.encode(message))


def _measure_timings(
    codecs: Sequence[Codec],
    corpus: Sequence[JsonMap],
    frames: Mapping[str, Sequence[bytes]],
    repeats: int,
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    encode_samples = {codec.name: [] for codec in codecs}
    decode_samples = {codec.name: [] for codec in codecs}
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for repeat in range(repeats):
            offset = repeat % len(codecs)
            ordered = tuple(codecs[offset:]) + tuple(codecs[:offset])
            for codec in ordered:
                for message in corpus:
                    started = time.perf_counter_ns()
                    codec.encode(message)
                    encode_samples[codec.name].append(time.perf_counter_ns() - started)
        for repeat in range(repeats):
            offset = repeat % len(codecs)
            ordered = tuple(codecs[offset:]) + tuple(codecs[:offset])
            for codec in ordered:
                for frame in frames[codec.name]:
                    started = time.perf_counter_ns()
                    codec.decode(frame)
                    decode_samples[codec.name].append(time.perf_counter_ns() - started)
    finally:
        if gc_was_enabled:
            gc.enable()
    return encode_samples, decode_samples


def measure(
    codecs: Sequence[Codec],
    corpus: Sequence[JsonMap],
    *,
    repeats: int,
    warmups: int,
) -> tuple[CodecResult, ...]:
    frames = {
        codec.name: tuple(codec.encode(message) for message in corpus)
        for codec in codecs
    }
    warm_up(codecs, corpus, warmups)
    encode_samples, decode_samples = _measure_timings(codecs, corpus, frames, repeats)
    results: list[CodecResult] = []
    for codec in codecs:
        exact = byte_stable = 0
        for message, frame in zip(corpus, frames[codec.name], strict=True):
            decoded = codec.decode(frame)
            exact += decoded == message
            byte_stable += codec.encode(decoded) == frame and codec.encode(message) == frame
        results.append(
            CodecResult(
                codec.name,
                tuple(len(frame) for frame in frames[codec.name]),
                tuple(encode_samples[codec.name]),
                tuple(decode_samples[codec.name]),
                exact,
                byte_stable,
            )
        )
    return tuple(results)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _size_row(result: CodecResult, json_total: int) -> str:
    total = sum(result.sizes)
    delta = 100 * (total / json_total - 1)
    return (
        f"| {result.name} | {total:,} | {statistics.fmean(result.sizes):,.1f} | "
        f"{nearest_rank(result.sizes, 0.50):,} | {nearest_rank(result.sizes, 0.95):,} | "
        f"{min(result.sizes):,} | {max(result.sizes):,} | {delta:+.1f}% |"
    )


def _latency_row(result: CodecResult) -> str:
    return (
        f"| {result.name} | {nearest_rank(result.encode_ns, 0.50) / 1_000:,.2f} | "
        f"{nearest_rank(result.encode_ns, 0.95) / 1_000:,.2f} | "
        f"{nearest_rank(result.decode_ns, 0.50) / 1_000:,.2f} | "
        f"{nearest_rank(result.decode_ns, 0.95) / 1_000:,.2f} |"
    )


def _break_even(cold_bytes: int, warm_mean: float, baseline_mean: float) -> str:
    saving = baseline_mean - warm_mean
    if saving <= 0:
        return "none"
    return str(math.floor(cold_bytes / saving) + 1)


def render_report(
    results: Sequence[CodecResult],
    codecs: Sequence[Codec],
    corpus: Sequence[JsonMap],
    *,
    repeats: int,
    warmups: int,
    elapsed: float,
) -> str:
    runtime = load_proto_runtime()
    by_name = {result.name: result for result in results}
    json_total = sum(by_name["sorted minified JSON"].sizes)
    v02 = by_name["UrusillaWire v0.2 warm"]
    v02_total = sum(v02.sizes)
    alternatives = [result for result in results if result.name != v02.name]
    strongest = min(alternatives, key=lambda result: sum(result.sizes))
    strongest_total = sum(strongest.sizes)
    advantage = 100 * (1 - v02_total / strongest_total)
    capsule = urusilla_wire_v02.encode_capsule(urusilla_wire_v02.DEFAULT_PROFILE)
    proto_source = PROTO_PATH.read_bytes()
    proto_descriptor = runtime.descriptor_set
    versions = dependency_versions()
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    mean_v02 = statistics.fmean(v02.sizes)

    source_path = Path(__file__)
    test_path = source_path.with_name("test_urusilla_strong_codec_baselines.py")
    digest_lines = [
        f"- Benchmark source: `{_sha256_file(source_path)}`",
        f"- Declared Protobuf schema: `{_sha256_file(PROTO_PATH)}`",
        f"- Compiled Protobuf descriptor set: "
        f"`{hashlib.sha256(proto_descriptor).hexdigest()}`",
    ]
    if test_path.is_file():
        digest_lines.append(f"- Test source: `{_sha256_file(test_path)}`")

    lines = [
        "# Strong codec baselines for UrusillaWire v0.2",
        "",
        f"Execution time (UTC): `{timestamp}`  ",
        f"Corpus: `{CORPUS_VERSION}`, {len(corpus)} deterministic messages, SHA-256 "
        f"`{corpus_digest(corpus)}`  ",
        f"Runtime: `{platform.python_implementation()} {platform.python_version()}` / "
        f"`{platform.platform()}`  ",
        f"Settings: {warmups} warm-up rounds and {repeats} measured repeats per direction  ",
        f"Total study time: {elapsed:.2f}s",
        "",
        "## Result",
        "",
        f"On this declared, in-domain corpus, raw warm UrusillaWire v0.2 used **{v02_total:,} "
        f"bytes**. The smallest non-v0.2 warm baseline was **{strongest.name}** at "
        f"**{strongest_total:,} bytes**, so v0.2 was **{advantage:.1f}% smaller** before "
        "charging its one-time profile capsule. All six codecs achieved exact semantic "
        f"round-trip for `{len(corpus)}/{len(corpus)}` messages and byte-stable re-encoding "
        f"for `{len(corpus)}/{len(corpus)}` messages in the pinned runtime.",
        "",
        "This is a favorable result for warm v0.2 wire size, not proof of universal "
        "superiority. The v0.2 dictionary and shape table were manually designed for this "
        "schema family. MessagePack was fastest on this machine, and the ranking can change with "
        "out-of-domain messages, persistent compression, native implementations, network "
        "framing, or a different Protobuf schema. Unfavorable latency is retained below.",
        "",
        "## Actual warm bytes",
        "",
        "| Codec | Total bytes | Mean/msg | p50/msg | p95/msg | Min | Max | vs JSON |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(_size_row(result, json_total) for result in results)
    lines.extend(
        [
            "",
            "Every row contains 280 independently encoded messages. Gzip uses level 6 and "
            "`mtime=0` separately for each JSON message; it is not a shared stream. UrusillaWire "
            "v0.2 carries a profile ID, an 8-byte dictionary fingerprint, a payload length, "
            "and a 16-byte accidental-corruption checksum inside every reported warm frame. "
            "The other baselines do not carry an equivalent application checksum.",
            "",
            "## Encode and decode latency",
            "",
            "| Codec | Encode p50 (µs) | Encode p95 (µs) | Decode p50 (µs) | Decode p95 (µs) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    lines.extend(_latency_row(result) for result in results)
    lines.extend(
        [
            "",
            f"Each direction contains `{len(corpus) * repeats:,}` timed calls per codec. "
            "Schema compilation, module import, corpus construction, and allocation of the "
            "precomputed decode frames are excluded. Every encoder invokes the shared semantic "
            "validator, and every decoder invokes it after parsing. UrusillaWire v0.2 decode also "
            "verifies its checksum and requires canonical byte re-encoding. Wall-clock Python "
            "timings are machine-specific and do not predict optimized native runtimes.",
            "",
            "## Exactness and deterministic encoding",
            "",
            "| Codec | Exact semantic round-trip | Byte-stable re-encode | Determinism scope |",
            "|---|---:|---:|---|",
        ]
    )
    codec_by_name = {codec.name: codec for codec in codecs}
    for result in results:
        codec = codec_by_name[result.name]
        lines.append(
            f"| {result.name} | {result.exact}/{len(corpus)} | "
            f"{result.byte_stable}/{len(corpus)} | {codec.determinism} |"
        )
    lines.extend(
        [
            "",
            "`Byte-stable re-encode` requires a second encode of the source and an encode after "
            "decode to match the original bytes. It is not a cross-language proof. In "
            "particular, Protobuf's deterministic mode is not a canonical wire guarantee across "
            "languages or runtime versions, and MessagePack has no universal canonical profile. "
            "Sorted JSON here is a study profile, not an RFC 8785 implementation. CBOR uses the "
            "pinned library's canonical mode.",
            "",
            "The declared Protobuf schema uses typed top-level fields and a recursive oneof for "
            "null, Boolean, signed and unsigned 64-bit integers, binary64, UTF-8 text, bytes, "
            "lists, and UTF-8-keyed maps. Unit tests exercise these types, including byte strings "
            "and both integer extremes. It is not a JSON-byte wrapper or `google.protobuf.Struct`.",
            "",
            "## Cold schema and dictionary costs",
            "",
            "| Cold artifact or assumption | Raw bytes | gzip bytes |",
            "|---|---:|---:|",
            "| JSON, CBOR, and MessagePack codec-specific artifact | 0 | 0 |",
            f"| Protobuf `.proto` source | {len(proto_source):,} | "
            f"{len(deterministic_gzip_compress(proto_source, compresslevel=6)):,} |",
            f"| Protobuf compiled descriptor set | {len(proto_descriptor):,} | "
            f"{len(deterministic_gzip_compress(proto_descriptor, compresslevel=6)):,} |",
            f"| UrusillaWire v0.2 profile capsule | {len(capsule):,} | "
            f"{len(deterministic_gzip_compress(capsule, compresslevel=6)):,} |",
            "",
            "The zero rows assume the generic codec and the shared Urusilla semantic contract are "
            "already installed. Protobuf likewise has zero session cost when generated code is "
            "preinstalled; the source and descriptor rows show two possible distribution costs, "
            "not costs that should be added together. v0.2 likewise has zero session cost when "
            "the content-addressed profile is cached. Discovery messages, signatures, TLS, and "
            "cache eviction are outside these byte counts.",
            "",
            "## Profile-capsule break-even",
            "",
            "The following is the smallest integer message count satisfying "
            "`raw capsule + N × v0.2 warm mean < N × baseline warm mean`. It assumes the "
            "measured corpus mix repeats and gives every baseline zero cold cost.",
            "",
            "| Baseline | Messages to amortize raw v0.2 capsule | Messages using gzip capsule |",
            "|---|---:|---:|",
        ]
    )
    for result in alternatives:
        baseline_mean = statistics.fmean(result.sizes)
        lines.append(
            f"| {result.name} | {_break_even(len(capsule), mean_v02, baseline_mean)} | "
            f"{_break_even(len(deterministic_gzip_compress(capsule, compresslevel=6)), mean_v02, baseline_mean)} |"
        )
    lines.extend(
        [
            "",
            "## Codec qualifications",
            "",
        ]
    )
    for codec in codecs:
        lines.append(f"- **{codec.name}:** {codec.qualification}. {codec.determinism}.")
    lines.extend(
        [
            "",
            "## Pinned research environment",
            "",
            "These packages were installed only in an isolated research virtual environment; "
            "they are not core runtime dependencies.",
            "",
            "| Distribution | Pinned version | Observed version |",
            "|---|---:|---:|",
        ]
    )
    for name, pinned in PINNED_PACKAGES.items():
        lines.append(f"| {name} | {pinned} | {versions[name]} |")
    lines.extend(
        [
            "",
            "## Strict limitations",
            "",
            "- The corpus is deterministic and broad enough to exercise all seven acts, but it "
            "is synthetic and generated by this repository. No result establishes external "
            "adoption or end-to-end task success.",
            "- The v0.2 static profile was designed with knowledge of the benchmark schema family. "
            "A frozen preregistered out-of-domain corpus is required before making a general "
            "compression claim.",
            "- The Protobuf schema was designed for this comparison. Another field allocation, "
            "domain-specific body messages, string interning layer, or generated native runtime "
            "could substantially change its bytes and latency.",
            "- JSON in this corpus contains no byte strings. The Protobuf, CBOR, MessagePack, and "
            "v0.2 implementations can carry Urusilla byte values; ordinary JSON needs an explicit "
            "tagging convention that is not charged here.",
            "- No persistent gzip, zstd, Brotli, FlatBuffers, Cap'n Proto, transport/TLS framing, "
            "packet loss, energy use, or memory allocation benchmark is included.",
            "- Except for v0.2, these rows do not detect arbitrary bit corruption at the "
            "application layer. Authenticated transport is still required for every codec; the "
            "v0.2 truncated checksum is not authentication.",
            "- Timings come from one Python process on one machine. Compilation and dependency "
            "installation are excluded, and native or JIT implementations may reverse rankings.",
            "",
            "## Artifact digests",
            "",
        ]
    )
    lines.extend(digest_lines)
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 -m venv .venv-strong",
            ".venv-strong/bin/python -m pip install \\",
            "  cbor2==6.1.4 msgpack==1.2.1 grpcio-tools==1.83.0",
            ".venv-strong/bin/python test_urusilla_strong_codec_baselines.py",
            ".venv-strong/bin/python urusilla_strong_codec_baselines.py --benchmark",
            "```",
            "",
            "The `grpcio-tools` pin resolves the matching `protobuf` runtime shown above. The "
            "script nevertheless verifies all four observed pins before running.",
            "",
        ]
    )
    return "\n".join(lines)


def run_benchmark(
    *,
    messages: int = DEFAULT_MESSAGES,
    repeats: int = DEFAULT_REPEATS,
    warmups: int = DEFAULT_WARMUPS,
) -> str:
    if messages != DEFAULT_MESSAGES:
        raise ValueError("the strong-baseline study is fixed to exactly 280 messages")
    if repeats < 1 or warmups < 0:
        raise ValueError("repeats must be positive and warmups must be non-negative")
    require_dependencies()
    load_proto_runtime()
    corpus = build_corpus(messages)
    codecs = available_codecs()
    started = time.perf_counter()
    results = measure(codecs, corpus, repeats=repeats, warmups=warmups)
    elapsed = time.perf_counter() - started
    return render_report(
        results,
        codecs,
        corpus,
        repeats=repeats,
        warmups=warmups,
        elapsed=elapsed,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="run the full study")
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.benchmark:
        print("Pass --benchmark to run the pinned strong-codec study.")
        return 0
    report = run_benchmark(
        messages=args.messages,
        repeats=args.repeats,
        warmups=args.warmups,
    )
    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
