# Urusilla v0.1 reproducible value benchmark

Execution time (UTC): `2026-08-20T13:37:29+00:00`  
Corpus: `urusilla-benchmark-corpus-v1`, 280 deterministic messages, SHA-256 `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`  
Runtime: `CPython 3.14.7` / `macOS-15.0-arm64-arm-64bit-Mach-O`  
Measurement settings: 2 warm-up rounds, 20 timing repeats, 4 single-bit corruptions per message  
Total execution time: 12.13s

## Conclusion first

On this corpus, raw UrusillaWire was **34.0% smaller than minified JSON**, while raw UrusillaWire was **4.2% larger than per-message gzip JSON**. When the same gzip compression was applied to both, gzip(UrusillaWire) was **6.9% smaller than gzip(JSON)**. Valid-message semantic round-trip was `280/280`, and `1120/1120` deterministic bit flips were rejected during raw UrusillaWire decoding.

From a wire-only perspective, raw UrusillaWire is larger than gzip JSON and has higher codec latency, so it cannot be said to dominate every baseline. Applying the same transport compression reveals a size advantage, but a CPU trade-off remains. The current reason to select Urusilla is its **semantic contract for carrying already-structured UrusillaIR canonically and with fail-closed behavior**; the codec should be negotiated according to the situation. These results do not demonstrate an end-to-end advantage in agent intelligence or task success. In particular, a model must not be assumed to read binary wire data directly; an adapter or native structured channel is required.

## Wire bytes

| Codec | Total bytes | Mean/msg | p50/msg | p95/msg | vs minified JSON |
|---|---:|---:|---:|---:|---:|
| UrusillaWire | 176,069 | 628.8 | 561 | 907 | -34.0% |
| gzip UrusillaWire | 157,344 | 561.9 | 517 | 750 | -41.0% |
| minified JSON | 266,684 | 952.4 | 830 | 1,349 | +0.0% |
| gzip JSON | 168,941 | 603.4 | 568 | 767 | -36.7% |

Each message was sent as an independent frame. Both gzip JSON and gzip UrusillaWire use identical per-message compression with `compresslevel=6, mtime=0`, not a batch or streaming dictionary. The raw UrusillaWire row is retained as a separate baseline rather than hidden.

## Encode/decode latency

| Codec | Encode p50 (µs) | Encode p95 (µs) | Decode p50 (µs) | Decode p95 (µs) |
|---|---:|---:|---:|---:|
| UrusillaWire | 217.88 | 511.96 | 391.96 | 827.75 |
| gzip UrusillaWire | 280.08 | 712.54 | 398.75 | 776.79 |
| minified JSON | 15.21 | 52.50 | 70.88 | 141.08 |
| gzip JSON | 55.17 | 164.67 | 80.62 | 161.62 |

Encode and decode were each measured `5,600` times per codec. Urusilla decoding includes checksum verification, semantic validation, and a canonical re-encode check. JSON encode serializes without the equivalent validation pass, while JSON decode uses the shared validator. These are timings of the current Python implementation paths, not an inherent format-speed comparison. Values are wall-clock samples from this machine and will differ on other machines.

## Exactness and canonicality

| Codec | Exact semantic round-trip | Re-encode byte-identical |
|---|---:|---:|
| UrusillaWire | 280/280 (100.0%) | 280/280 (100.0%) |
| gzip UrusillaWire | 280/280 (100.0%) | 280/280 (100.0%) |
| minified JSON | 280/280 (100.0%) | 280/280 (100.0%) |
| gzip JSON | 280/280 (100.0%) | 280/280 (100.0%) |

`Exact semantic round-trip` checks whether the decoded canonical Urusilla message equals the source. `Re-encode byte-identical` checks whether canonical bytes remain stable within the same runtime and profile.

## Single-bit corruption

| Codec | Rejected/detected | Accepted, semantics changed | Accepted, semantics unchanged |
|---|---:|---:|---:|
| UrusillaWire | 1120/1120 (100.0%) | 0/1120 (0.0%) | 0/1120 (0.0%) |
| gzip UrusillaWire | 1106/1120 (98.8%) | 0/1120 (0.0%) | 14/1120 (1.2%) |
| minified JSON | 723/1120 (64.6%) | 396/1120 (35.4%) | 1/1120 (0.1%) |
| gzip JSON | 1110/1120 (99.1%) | 0/1120 (0.0%) | 10/1120 (0.9%) |

The same bit was flipped at corresponding deterministic fractional positions in each encoded frame. `Rejected` means that codec decoding and shared Urusilla validation failed closed with an exception. `Accepted, semantics changed` indicates dangerous silent corruption. `Unchanged` can include modifications outside the semantic payload, such as changes to a gzip header. This test does not evaluate protection against malicious forgery.

## Semantically invalid inputs

The test used `240` invalid messages: 12 violation classes × 20 source messages.

| Codec | Rejected at encode | Serialized, then rejected at decode/validation | Invalid accepted end-to-end |
|---|---:|---:|---:|
| UrusillaWire | 240/240 | 0/240 | 0/240 |
| gzip UrusillaWire | 240/240 | 0/240 | 0/240 |
| minified JSON | 0/240 | 240/240 | 0/240 |
| gzip JSON | 0/240 | 240/240 | 0/240 |

JSON and gzip are not themselves semantic schemas, so they can serialize invalid objects. For a fair end-to-end comparison, the JSON decoders in this benchmark explicitly use Urusilla's `normalize_message` validator. The UrusillaWire reference encoder invokes the validator itself, so invalid messages are rejected before wire data is produced.

## Codec profiles and optional baselines

- **UrusillaWire:** v0.1 reference; checksum + semantic validation + canonical re-encode
- **gzip UrusillaWire:** UrusillaWire with per-message gzip level 6, mtime=0
- **minified JSON:** sorted UTF-8 JSON; shared Urusilla normalize_message on decode
- **gzip JSON:** per-message gzip level 6, mtime=0; shared Urusilla validation on decode

- deterministic CBOR: not run (`cbor2` is not installed)
- Protobuf: not run (`google.protobuf` is not installed)

## What this does not measure

- **Cold schema / Grammar Capsule cost:** The corpus contains only a schema URI. It excludes the bytes and validation time required for the initial delivery of ontology data, a schema document, translation templates, and golden vectors. Cold break-even must be calculated separately as `floor(cold_bootstrap_bytes / (baseline_bytes_per_msg - warm_Urusilla_bytes_per_msg)) + 1` for the first strict byte win, and a break-even point exists only when the denominator is positive.
- **Session shared-dictionary warm profile:** Current UrusillaWire includes a per-message string table in every frame. If `C` is the combined cost of the Capsule and session-dictionary handshake, `W` is the average warm-frame size, and `B` is the average baseline-frame size, the condition for `N` messages is `C + N·W < N·B`, or `N > C/(B-W)`. This original v0.1 measurement does not include a session profile or handshake. A separate experimental v0.2 implementation and cold-cost study now report those values in `urusilla_wire_v02_results.md`; they must not be retroactively attributed to the v0.1 row.
- **LLM tokens and model cost:** These vary by tokenizer and model, and placing binary UrusillaWire in a text prompt is not a design goal. An evaluation that connects a JSON/UrusillaIR projection to actual model I/O is required.
- **Semantic construction quality:** The benchmark does not measure ambiguity, omission, or hallucination in natural-language → UrusillaIR conversion. The source corpus already consists of valid semantic objects.
- **Task utility:** Success rate, repair turns, causal usefulness, multi-agent transfer, energy, memory, and network/TLS overhead are not measured.
- **Compression regimes:** The benchmark does not compare cross-message or batch gzip, shared dictionaries, schema-aware CBOR/Protobuf, or content-addressed DAG deduplication.
- **Security:** The Urusilla checksum and gzip CRC signal accidental corruption only. They do not provide authentication, integrity against attackers, or replay protection.

## Reproduction

```bash
python3 urusilla_benchmark.py
```

Options: `--messages` (minimum 100), `--repeats`, `--warmups`, `--corruptions`, `--output`. Corpus bytes and corruption locations remain deterministic for the same corpus version and options; latency samples remain environment-dependent.
