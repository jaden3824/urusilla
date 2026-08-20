# UrusillaWire v0.2 static-profile performance study

Execution time (UTC): `2026-08-20T13:37:51+00:00`  
Corpus: `urusilla-benchmark-corpus-v1`, 280 deterministic messages, SHA-256 `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`  
Runtime: `CPython 3.14.7` / `macOS-15.0-arm64-arm-64bit-Mach-O`  
Settings: 2 warm-up rounds, 20 timing repeats, 4 deterministic single-bit corruptions per message  
Total benchmark time: 20.89s

## Result

Warm raw v0.2 used **54,752 bytes**, 67.6% less than per-message gzip JSON and 68.9% less than raw v0.1. Per-message gzip on v0.2 produced 60,711 bytes, 10.9% more than raw v0.2. These are warm-frame totals; the cold profile cost and break-even points are reported separately below.

This is a transport result, not evidence that agents reason better, invent a language autonomously, or should place binary frames in model prompts. The profile was designed for this declared benchmark family, so performance on unrelated or rapidly changing schemas may be worse. Latency and unfavorable baseline results are retained rather than filtered.

## Warm wire bytes

| Codec | Total bytes | Mean/msg | p50/msg | p95/msg | vs minified JSON |
|---|---:|---:|---:|---:|---:|
| minified JSON | 266,684 | 952.4 | 830 | 1,349 | +0.0% |
| gzip minified JSON | 168,941 | 603.4 | 568 | 767 | -36.7% |
| UrusillaWire v0.1 | 176,069 | 628.8 | 561 | 907 | -34.0% |
| gzip UrusillaWire v0.1 | 157,344 | 561.9 | 517 | 750 | -41.0% |
| UrusillaWire v0.2 warm | 54,752 | 195.5 | 199 | 239 | -79.5% |
| gzip UrusillaWire v0.2 warm | 60,711 | 216.8 | 215 | 260 | -77.2% |

Every row sends 280 or more separately framed messages. Gzip is applied separately to each message with identical standard-library settings; no batch stream is used. The v0.2 raw row carries a profile ID, an 8-byte content fingerprint, payload length, and a 16-byte checksum in every frame.

## Codec latency

| Codec | Encode p50 (µs) | Encode p95 (µs) | Decode p50 (µs) | Decode p95 (µs) |
|---|---:|---:|---:|---:|
| minified JSON | 14.42 | 56.33 | 78.38 | 201.29 |
| gzip minified JSON | 53.88 | 200.17 | 97.04 | 253.33 |
| UrusillaWire v0.1 | 234.54 | 695.96 | 497.00 | 1,131.38 |
| gzip UrusillaWire v0.1 | 287.96 | 906.71 | 491.58 | 1,088.21 |
| UrusillaWire v0.2 warm | 156.29 | 527.00 | 312.12 | 769.83 |
| gzip UrusillaWire v0.2 warm | 193.71 | 638.42 | 339.21 | 853.88 |

Encode and decode were each sampled `5,600` times per codec. v0.2 decode includes checksum verification, profile resolution, semantic validation, and canonical re-encoding. JSON encode does not perform the equivalent validation pass, and the implementations use different amounts of pure Python and native CPython code. These are current implementation-path timings, not inherent format speeds or portable throughput guarantees.

## Exactness and fail-closed checks

| Codec | Exact semantic round-trip | Byte-stable re-encode in this runtime | Corruptions rejected | Accepted, semantics changed | Accepted, semantics unchanged |
|---|---:|---:|---:|---:|---:|
| minified JSON | 280/280 (100.0%) | 280/280 (100.0%) | 723/1120 (64.6%) | 396/1120 (35.4%) | 1/1120 (0.1%) |
| gzip minified JSON | 280/280 (100.0%) | 280/280 (100.0%) | 1110/1120 (99.1%) | 0/1120 (0.0%) | 10/1120 (0.9%) |
| UrusillaWire v0.1 | 280/280 (100.0%) | 280/280 (100.0%) | 1120/1120 (100.0%) | 0/1120 (0.0%) | 0/1120 (0.0%) |
| gzip UrusillaWire v0.1 | 280/280 (100.0%) | 280/280 (100.0%) | 1106/1120 (98.8%) | 0/1120 (0.0%) | 14/1120 (1.2%) |
| UrusillaWire v0.2 warm | 280/280 (100.0%) | 280/280 (100.0%) | 1120/1120 (100.0%) | 0/1120 (0.0%) | 0/1120 (0.0%) |
| gzip UrusillaWire v0.2 warm | 280/280 (100.0%) | 280/280 (100.0%) | 1081/1120 (96.5%) | 0/1120 (0.0%) | 39/1120 (3.5%) |

A matched deterministic bit was flipped at a fractional position in every encoded frame. A gzip header bit may be accepted with unchanged semantics, which is why `rejected` need not reach 100% for gzip rows. The raw v0.2 checksum covers the header, profile identifiers, and payload. It detects accidental corruption but is not authentication against an attacker who can recompute it.

The shared invalid-input suite contained `240` messages. All v0.2 invalid inputs were rejected at encode or decode; accepted count: `0`. Unit tests separately cover unknown profile IDs, unknown dictionary fingerprints, capsule corruption, and non-canonical frames.

## Cold capsule cost

The default profile contains `109` strings and `19` exact map shapes. Its dictionary fingerprint is `7d12fc414eae60b2`.

| Bootstrap object | Raw bytes | gzip bytes |
|---|---:|---:|
| v0.2 static-profile capsule | 1,402 | 920 |
| Existing v0.1 Grammar Capsule JSON | 33,476 | 10,320 |
| Both objects, transferred independently | 34,878 | 11,240 |

The v0.2 profile capsule is the only additional object required by this codec. The existing Grammar Capsule is shown as a conservative application-level cold scenario; it is not required again if peers already possess it. Gzip capsule sizes use level 6 and `mtime=0`.

## Mean-size break-even

Break-even is the smallest integer `N` satisfying `C + N·W < N·B`, using the measured corpus means. `C` is the one-time bootstrap, `W` the v0.2 warm mean, and `B` the selected baseline mean. A dash means the v0.2 warm mean is not smaller, so no byte break-even exists under that comparison.

| Warm candidate | Baseline | Profile-only cold N | Profile + Grammar Capsule N |
|---|---|---:|---:|
| UrusillaWire v0.2 warm | minified JSON | 2 | 47 |
| UrusillaWire v0.2 warm | gzip minified JSON | 4 | 86 |
| UrusillaWire v0.2 warm | UrusillaWire v0.1 | 4 | 81 |
| UrusillaWire v0.2 warm | gzip UrusillaWire v0.1 | 4 | 96 |
| gzip UrusillaWire v0.2 warm | minified JSON | 2 | 16 |
| gzip UrusillaWire v0.2 warm | gzip minified JSON | 3 | 30 |
| gzip UrusillaWire v0.2 warm | UrusillaWire v0.1 | 3 | 28 |
| gzip UrusillaWire v0.2 warm | gzip UrusillaWire v0.1 | 3 | 33 |

These mean-based values assume the measured workload mix repeats. A short session with different message shapes can fail to amortize the capsule. Transport/TLS headers, profile discovery round trips, retransmission, and cache eviction are not included.

## Codec design and canonicality

- Frames identify both the numeric profile and its 64-bit SHA-256-derived content fingerprint. Decoders use an explicit registry and reject unknown combinations.
- Common static strings and schema map shapes use one-byte tags. Other strings are encoded losslessly as UTF-8, optionally using a deterministic longest-beneficial static prefix. Unknown map shapes retain sorted explicit keys.
- Message UUIDs remain 16-byte values. Integers remain canonical varints, finite floats remain normalized IEEE-754 binary64 values, and byte strings remain exact.
- Decode validates the checksum before profile lookup, checks all bounds and reserved bits, invokes the shared Urusilla semantic validator, then requires byte-identical canonical re-encoding.
- A capsule checksum detects accidental damage. Capsule authorization and frame authentication must be supplied by a trusted registry, signed metadata, or an authenticated transport; an eight-byte dictionary fingerprint is an identifier, not a security proof.

## Limitations

- The default profile was manually derived from the same public benchmark generator and contains its exact agents, schemas, predicates, prefixes, and map shapes. This is an in-sample upper-bound study, not an out-of-domain compression claim.
- The benchmark begins with already-structured semantic objects. It does not measure natural-language parsing, LLM tokens, task success, repair turns, or semantic interoperability between independently trained models.
- Per-message gzip is the requested baseline. A persistent gzip/zstd stream, schema-equivalent Protobuf implementation, or TLS record compression could change the ranking and is not evaluated here.
- Static profiles require lifecycle controls: version negotiation, cache bounds, rollback, authorization, and a fallback representation. Those controls are outside this prototype.

## Reproduction

```bash
python3 urusilla_wire_v02.py --benchmark --output urusilla_wire_v02_results.md
python3 test_urusilla_wire_v02.py
```

Options: `--messages` (minimum 280), `--repeats`, `--warmups`, `--corruptions`, and `--output`. Corpus content and corruption positions are deterministic; timings remain environment-dependent.
