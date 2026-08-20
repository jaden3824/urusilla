# Strong codec baselines for UrusillaWire v0.2

Execution time (UTC): `2026-08-20T13:46:18+00:00`  
Corpus: `urusilla-benchmark-corpus-v1`, 280 deterministic messages, SHA-256 `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`  
Runtime: `CPython 3.12.14` / `macOS-15.0-arm64-arm-64bit`  
Settings: 1 warm-up rounds and 1 measured repeats per direction  
Total study time: 1.92s

## Result

On this declared, in-domain corpus, raw warm UrusillaWire v0.2 used **54,752 bytes**. The smallest non-v0.2 warm baseline was **per-message gzip JSON** at **168,941 bytes**, so v0.2 was **67.6% smaller** before charging its one-time profile capsule. All six codecs achieved exact semantic round-trip for `280/280` messages and byte-stable re-encoding for `280/280` messages in the pinned runtime.

This is a favorable result for warm v0.2 wire size, not proof of universal superiority. The v0.2 dictionary and shape table were manually designed for this schema family. MessagePack was fastest on this machine, and the ranking can change with out-of-domain messages, persistent compression, native implementations, network framing, or a different Protobuf schema. Unfavorable latency is retained below.

## Actual warm bytes

| Codec | Total bytes | Mean/msg | p50/msg | p95/msg | Min | Max | vs JSON |
|---|---:|---:|---:|---:|---:|---:|---:|
| sorted minified JSON | 266,684 | 952.4 | 830 | 1,349 | 567 | 1,374 | +0.0% |
| per-message gzip JSON | 168,941 | 603.4 | 568 | 767 | 430 | 801 | -36.7% |
| deterministic CBOR | 219,283 | 783.2 | 685 | 1,105 | 478 | 1,133 | -17.8% |
| MessagePack | 218,495 | 780.3 | 682 | 1,102 | 476 | 1,129 | -18.1% |
| schema-equivalent Protobuf | 229,230 | 818.7 | 687 | 1,268 | 375 | 1,282 | -14.0% |
| UrusillaWire v0.2 warm | 54,752 | 195.5 | 199 | 239 | 152 | 243 | -79.5% |

Every row contains 280 independently encoded messages. Gzip uses level 6 and `mtime=0` separately for each JSON message; it is not a shared stream. UrusillaWire v0.2 carries a profile ID, an 8-byte dictionary fingerprint, a payload length, and a 16-byte accidental-corruption checksum inside every reported warm frame. The other baselines do not carry an equivalent application checksum.

## Encode and decode latency

| Codec | Encode p50 (µs) | Encode p95 (µs) | Decode p50 (µs) | Decode p95 (µs) |
|---|---:|---:|---:|---:|
| sorted minified JSON | 111.25 | 196.75 | 68.33 | 122.33 |
| per-message gzip JSON | 152.33 | 271.83 | 75.79 | 126.75 |
| deterministic CBOR | 122.62 | 224.62 | 68.58 | 119.46 |
| MessagePack | 92.83 | 162.62 | 63.71 | 113.17 |
| schema-equivalent Protobuf | 100.96 | 194.58 | 97.21 | 174.17 |
| UrusillaWire v0.2 warm | 110.92 | 195.04 | 244.92 | 412.58 |

Each direction contains `280` timed calls per codec. Schema compilation, module import, corpus construction, and allocation of the precomputed decode frames are excluded. Every encoder invokes the shared semantic validator, and every decoder invokes it after parsing. UrusillaWire v0.2 decode also verifies its checksum and requires canonical byte re-encoding. Wall-clock Python timings are machine-specific and do not predict optimized native runtimes.

## Exactness and deterministic encoding

| Codec | Exact semantic round-trip | Byte-stable re-encode | Determinism scope |
|---|---:|---:|---|
| sorted minified JSON | 280/280 | 280/280 | byte-stable Python study profile; not claimed as RFC 8785 |
| per-message gzip JSON | 280/280 | 280/280 | gzip level 6 with mtime=0 over the sorted JSON profile |
| deterministic CBOR | 280/280 | 280/280 | cbor2 canonical=True |
| MessagePack | 280/280 | 280/280 | sorted-map, binary64, msgpack 1.2.1 runtime profile |
| schema-equivalent Protobuf | 280/280 | 280/280 | deterministic=True within the pinned Protobuf runtime |
| UrusillaWire v0.2 warm | 280/280 | 280/280 | normative v0.2 canonical re-encoding check |

`Byte-stable re-encode` requires a second encode of the source and an encode after decode to match the original bytes. It is not a cross-language proof. In particular, Protobuf's deterministic mode is not a canonical wire guarantee across languages or runtime versions, and MessagePack has no universal canonical profile. Sorted JSON here is a study profile, not an RFC 8785 implementation. CBOR uses the pinned library's canonical mode.

The declared Protobuf schema uses typed top-level fields and a recursive oneof for null, Boolean, signed and unsigned 64-bit integers, binary64, UTF-8 text, bytes, lists, and UTF-8-keyed maps. Unit tests exercise these types, including byte strings and both integer extremes. It is not a JSON-byte wrapper or `google.protobuf.Struct`.

## Cold schema and dictionary costs

| Cold artifact or assumption | Raw bytes | gzip bytes |
|---|---:|---:|
| JSON, CBOR, and MessagePack codec-specific artifact | 0 | 0 |
| Protobuf `.proto` source | 1,322 | 636 |
| Protobuf compiled descriptor set | 1,456 | 727 |
| UrusillaWire v0.2 profile capsule | 1,402 | 920 |

The zero rows assume the generic codec and the shared Urusilla semantic contract are already installed. Protobuf likewise has zero session cost when generated code is preinstalled; the source and descriptor rows show two possible distribution costs, not costs that should be added together. v0.2 likewise has zero session cost when the content-addressed profile is cached. Discovery messages, signatures, TLS, and cache eviction are outside these byte counts.

## Profile-capsule break-even

The following is the smallest integer message count satisfying `raw capsule + N × v0.2 warm mean < N × baseline warm mean`. It assumes the measured corpus mix repeats and gives every baseline zero cold cost.

| Baseline | Messages to amortize raw v0.2 capsule | Messages using gzip capsule |
|---|---:|---:|
| sorted minified JSON | 2 | 2 |
| per-message gzip JSON | 4 | 3 |
| deterministic CBOR | 3 | 2 |
| MessagePack | 3 | 2 |
| schema-equivalent Protobuf | 3 | 2 |

## Codec qualifications

- **sorted minified JSON:** UTF-8 text; no per-frame integrity field. byte-stable Python study profile; not claimed as RFC 8785.
- **per-message gzip JSON:** independent gzip member per message; no application checksum. gzip level 6 with mtime=0 over the sorted JSON profile.
- **deterministic CBOR:** generic semantic map; no schema dictionary or checksum. cbor2 canonical=True.
- **MessagePack:** MessagePack has no universal canonical encoding standard. sorted-map, binary64, msgpack 1.2.1 runtime profile.
- **schema-equivalent Protobuf:** typed top-level fields plus recursive lossless SemanticValue. deterministic=True within the pinned Protobuf runtime.
- **UrusillaWire v0.2 warm:** includes profile identifier, dictionary fingerprint, and 16-byte checksum. normative v0.2 canonical re-encoding check.

## Pinned research environment

These packages were installed only in an isolated research virtual environment; they are not core runtime dependencies.

| Distribution | Pinned version | Observed version |
|---|---:|---:|
| cbor2 | 6.1.4 | 6.1.4 |
| msgpack | 1.2.1 | 1.2.1 |
| protobuf | 7.35.1 | 7.35.1 |
| grpcio-tools | 1.83.0 | 1.83.0 |

## Strict limitations

- The corpus is deterministic and broad enough to exercise all seven acts, but it is synthetic and generated by this repository. No result establishes external adoption or end-to-end task success.
- The v0.2 static profile was designed with knowledge of the benchmark schema family. A frozen preregistered out-of-domain corpus is required before making a general compression claim.
- The Protobuf schema was designed for this comparison. Another field allocation, domain-specific body messages, string interning layer, or generated native runtime could substantially change its bytes and latency.
- JSON in this corpus contains no byte strings. The Protobuf, CBOR, MessagePack, and v0.2 implementations can carry Urusilla byte values; ordinary JSON needs an explicit tagging convention that is not charged here.
- No persistent gzip, zstd, Brotli, FlatBuffers, Cap'n Proto, transport/TLS framing, packet loss, energy use, or memory allocation benchmark is included.
- Except for v0.2, these rows do not detect arbitrary bit corruption at the application layer. Authenticated transport is still required for every codec; the v0.2 truncated checksum is not authentication.
- Timings come from one Python process on one machine. Compilation and dependency installation are excluded, and native or JIT implementations may reverse rankings.

## Artifact digests

- Benchmark source: `6f3e6ab8f90ee586e43e14927f43fe00e27c8162dba42238c95b37466a6f2e0f`
- Declared Protobuf schema: `43f2b236836750779edcc9f34890f468478036172052a8ca1989d7b5108f9e5d`
- Compiled Protobuf descriptor set: `340ce63b554a904e968bf664d13cd7822df64c79f78bf394983316d08291211f`
- Test source: `f6c0e44750382debffdd662c298467f4af8712429dc33e9409f0f61c048b523c`

## Reproduction

```bash
python3 -m venv .venv-strong
.venv-strong/bin/python -m pip install \
  cbor2==6.1.4 msgpack==1.2.1 grpcio-tools==1.83.0
.venv-strong/bin/python test_urusilla_strong_codec_baselines.py
.venv-strong/bin/python urusilla_strong_codec_baselines.py --benchmark
```

The `grpcio-tools` pin resolves the matching `protobuf` runtime shown above. The script nevertheless verifies all four observed pins before running.
