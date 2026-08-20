# Session-reset compression crossover study

## Outcome

This study varies compressor-reset boundaries over the frozen ordered
280-message corpus.  It evaluates 378 combinations:
21 chunk sizes, three representations, and six pinned
compression profiles.  Every cached and independently cold row reconstructs
the corpus exactly and emits deterministic bytes.

The primary `cold` contract treats every chunk as a separately decodable
session.  Every session carries a four-byte setup length and a four-byte
compressed-payload length.  The project v0.2 row additionally carries its
1,402-byte checksummed profile capsule in every cold session;
the two JSON rows carry an empty setup field.  The `cached` sensitivity keeps
the identical eight-byte outer framing and compressor resets but assumes the
profile is already installed.  Inner four-byte record lengths are charged in
all three representations, checked JSON carries its independent 16-byte
checksum per record, and project v0.2 retains its own per-frame checksum.

This is an in-domain serialization result, not a task-utility result or a
state-of-the-art claim.

## Frozen design

- Corpus messages: 280
- Corpus SHA-256: `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`
- Chunk-size grid: `1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280`
- Grid construction: union of every divisor of 280, powers of two from 1
  through 256, and the full-corpus endpoint 280
- Non-divisor points retain and fully charge the shorter final chunk
- Compression profiles: gzip 6/9, Zstandard 3/19, and Brotli 5/11
- zstandard: `0.25.0`
- Brotli: `1.2.0`
- Profile capsule SHA-256: `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6`
- Deterministic measurement-matrix SHA-256: `f3d1376dffbf7f51c2fe02fff724cdc7338c7220afd6a9a731d75d88369cbdd5`
- Runtime for latency samples: `CPython 3.12.14` / `macOS-15.0-arm64-arm-64bit`

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
| 1 | 280 | brotli-11 / 146,849 | brotli-11 / 154,435 | brotli-5 / 451,743 | +207.62% | +192.51% | brotli-5 / 59,183 |
| 2 | 140 | brotli-11 / 104,575 | brotli-11 / 111,316 | brotli-5 / 248,198 | +137.34% | +122.97% | brotli-5 / 51,918 |
| 4 | 70 | brotli-11 / 80,239 | brotli-11 / 86,453 | brotli-11 / 143,418 | +78.74% | +65.89% | brotli-11 / 45,278 |
| 5 | 56 | brotli-11 / 74,484 | brotli-11 / 80,361 | brotli-11 / 122,183 | +64.04% | +52.04% | brotli-11 / 43,671 |
| 7 | 40 | brotli-11 / 64,406 | brotli-11 / 70,084 | brotli-11 / 96,816 | +50.32% | +38.14% | brotli-11 / 40,736 |
| 8 | 35 | brotli-11 / 61,568 | brotli-11 / 67,163 | brotli-5 / 90,298 | +46.66% | +34.45% | brotli-5 / 41,228 |
| 10 | 28 | brotli-11 / 55,601 | brotli-11 / 61,286 | brotli-11 / 77,913 | +40.13% | +27.13% | brotli-11 / 38,657 |
| 14 | 20 | brotli-11 / 48,137 | brotli-11 / 53,686 | brotli-11 / 64,206 | +33.38% | +19.60% | brotli-11 / 36,166 |
| 16 | 18 | brotli-11 / 46,883 | brotli-11 / 52,384 | brotli-11 / 61,328 | +30.81% | +17.07% | brotli-11 / 36,092 |
| 20 | 14 | brotli-11 / 43,084 | brotli-11 / 48,962 | brotli-11 / 54,386 | +26.23% | +11.08% | brotli-11 / 34,758 |
| 28 | 10 | brotli-11 / 38,176 | brotli-11 / 43,609 | brotli-11 / 46,942 | +22.96% | +7.64% | brotli-11 / 32,922 |
| 32 | 9 | brotli-11 / 37,343 | brotli-11 / 42,771 | brotli-11 / 45,211 | +21.07% | +5.70% | brotli-11 / 32,593 |
| 35 | 8 | brotli-11 / 35,726 | brotli-11 / 41,120 | brotli-11 / 43,119 | +20.69% | +4.86% | brotli-11 / 31,903 |
| 40 | 7 | brotli-11 / 34,617 | brotli-11 / 39,948 | brotli-11 / 41,360 | +19.48% | +3.53% | brotli-11 / 31,546 |
| 56 | 5 | brotli-11 / 31,512 | brotli-11 / 36,873 | brotli-11 / 36,983 | +17.36% | +0.30% | brotli-11 / 29,973 |
| 64 | 5 | brotli-11 / 31,669 | brotli-11 / 37,029 | brotli-11 / 36,849 | +16.36% | -0.49% | brotli-11 / 29,839 |
| 70 | 4 | brotli-11 / 29,946 | brotli-11 / 35,256 | brotli-11 / 34,751 | +16.05% | -1.43% | brotli-11 / 29,143 |
| 128 | 3 | brotli-11 / 27,994 | brotli-11 / 33,267 | brotli-11 / 31,666 | +13.12% | -4.81% | brotli-11 / 27,460 |
| 140 | 2 | brotli-11 / 26,320 | brotli-11 / 31,606 | brotli-11 / 29,428 | +11.81% | -6.89% | brotli-11 / 26,624 |
| 256 | 2 | brotli-11 / 25,732 | brotli-11 / 30,966 | brotli-11 / 28,842 | +12.09% | -6.86% | brotli-11 / 26,038 |
| 280 | 1 | brotli-11 / 24,088 | brotli-11 / 29,237 | brotli-11 / 26,575 | +10.32% | -9.10% | brotli-11 / 25,173 |

The next table fixes the compressor and lists every tested chunk size where
project v0.2 uses strictly fewer bytes than the named baseline.  It reports
the observed grid directly rather than implying an unmeasured continuous
threshold.

| Compression | Cold beats bare JSON | Cold beats checked JSON | Cached beats bare JSON | Cached beats checked JSON |
|---|---|---|---|---|
| gzip-6 | 56, 64, 70, 128, 140, 256, 280 | 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 |
| gzip-9 | 128, 140, 256, 280 | 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 |
| zstd-3 | 70, 128, 140, 256, 280 | 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 |
| zstd-19 | none | 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 |
| brotli-5 | none | 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 |
| brotli-11 | none | 64, 70, 128, 140, 256, 280 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128 | 1, 2, 4, 5, 7, 8, 10, 14, 16, 20, 28, 32, 35, 40, 56, 64, 70, 128, 140, 256, 280 |

## Current implementation-path latency

For each representation and chunk size, this table shows the compressor with
the smallest cold byte total.  Timing covers semantic serialization,
per-record framing, every compressor reset, outer framing, and the complete
cold decode.  Project cold decode constructs a fresh registry from every
transmitted profile capsule.  Values are whole-corpus p50/p95 microseconds,
not per-message values.

| Chunk messages | Representation | Byte-minimizing compression | Cold bytes | Encode p50 / p95 us | Decode p50 / p95 us |
|---:|---|---|---:|---:|---:|
| 1 | canonical JSON | brotli-11 | 146,849 | 342,150.5 / 342,150.5 | 21,670.8 / 21,670.8 |
| 1 | checked JSON | brotli-11 | 154,435 | 377,544.2 / 377,544.2 | 22,279.6 / 22,279.6 |
| 1 | project v0.2 | brotli-5 | 451,743 | 33,627.4 / 33,627.4 | 139,749.0 / 139,749.0 |
| 2 | canonical JSON | brotli-11 | 104,575 | 296,244.5 / 296,244.5 | 22,214.8 / 22,214.8 |
| 2 | checked JSON | brotli-11 | 111,316 | 364,406.5 / 364,406.5 | 25,611.2 / 25,611.2 |
| 2 | project v0.2 | brotli-5 | 248,198 | 33,543.8 / 33,543.8 | 107,112.3 / 107,112.3 |
| 4 | canonical JSON | brotli-11 | 80,239 | 306,887.8 / 306,887.8 | 21,736.6 / 21,736.6 |
| 4 | checked JSON | brotli-11 | 86,453 | 288,277.6 / 288,277.6 | 23,496.5 / 23,496.5 |
| 4 | project v0.2 | brotli-11 | 143,418 | 134,453.6 / 134,453.6 | 87,326.3 / 87,326.3 |
| 5 | canonical JSON | brotli-11 | 74,484 | 267,245.5 / 267,245.5 | 20,432.7 / 20,432.7 |
| 5 | checked JSON | brotli-11 | 80,361 | 295,050.4 / 295,050.4 | 21,723.0 / 21,723.0 |
| 5 | project v0.2 | brotli-11 | 122,183 | 121,313.2 / 121,313.2 | 83,032.4 / 83,032.4 |
| 7 | canonical JSON | brotli-11 | 64,406 | 267,258.6 / 267,258.6 | 20,270.8 / 20,270.8 |
| 7 | checked JSON | brotli-11 | 70,084 | 272,363.0 / 272,363.0 | 20,110.5 / 20,110.5 |
| 7 | project v0.2 | brotli-11 | 96,816 | 110,986.0 / 110,986.0 | 79,249.0 / 79,249.0 |
| 8 | canonical JSON | brotli-11 | 61,568 | 454,556.5 / 454,556.5 | 23,256.9 / 23,256.9 |
| 8 | checked JSON | brotli-11 | 67,163 | 407,763.9 / 407,763.9 | 29,196.3 / 29,196.3 |
| 8 | project v0.2 | brotli-5 | 90,298 | 43,524.6 / 43,524.6 | 102,176.9 / 102,176.9 |
| 10 | canonical JSON | brotli-11 | 55,601 | 281,044.5 / 281,044.5 | 20,994.2 / 20,994.2 |
| 10 | checked JSON | brotli-11 | 61,286 | 288,074.5 / 288,074.5 | 21,354.4 / 21,354.4 |
| 10 | project v0.2 | brotli-11 | 77,913 | 102,465.2 / 102,465.2 | 74,294.5 / 74,294.5 |
| 14 | canonical JSON | brotli-11 | 48,137 | 246,607.7 / 246,607.7 | 19,657.2 / 19,657.2 |
| 14 | checked JSON | brotli-11 | 53,686 | 260,623.9 / 260,623.9 | 19,968.0 / 19,968.0 |
| 14 | project v0.2 | brotli-11 | 64,206 | 98,213.8 / 98,213.8 | 73,427.3 / 73,427.3 |
| 16 | canonical JSON | brotli-11 | 46,883 | 263,669.5 / 263,669.5 | 19,978.6 / 19,978.6 |
| 16 | checked JSON | brotli-11 | 52,384 | 316,049.8 / 316,049.8 | 26,377.3 / 26,377.3 |
| 16 | project v0.2 | brotli-11 | 61,328 | 111,126.1 / 111,126.1 | 86,310.9 / 86,310.9 |
| 20 | canonical JSON | brotli-11 | 43,084 | 1,102,755.9 / 1,102,755.9 | 57,586.3 / 57,586.3 |
| 20 | checked JSON | brotli-11 | 48,962 | 824,685.2 / 824,685.2 | 60,138.5 / 60,138.5 |
| 20 | project v0.2 | brotli-11 | 54,386 | 386,686.3 / 386,686.3 | 355,022.5 / 355,022.5 |
| 28 | canonical JSON | brotli-11 | 38,176 | 1,238,405.6 / 1,238,405.6 | 146,745.3 / 146,745.3 |
| 28 | checked JSON | brotli-11 | 43,609 | 1,278,333.9 / 1,278,333.9 | 183,878.4 / 183,878.4 |
| 28 | project v0.2 | brotli-11 | 46,942 | 146,004.3 / 146,004.3 | 255,310.5 / 255,310.5 |
| 32 | canonical JSON | brotli-11 | 37,343 | 256,470.3 / 256,470.3 | 20,559.5 / 20,559.5 |
| 32 | checked JSON | brotli-11 | 42,771 | 272,022.2 / 272,022.2 | 20,912.7 / 20,912.7 |
| 32 | project v0.2 | brotli-11 | 45,211 | 101,097.4 / 101,097.4 | 81,419.3 / 81,419.3 |
| 35 | canonical JSON | brotli-11 | 35,726 | 251,739.7 / 251,739.7 | 21,591.4 / 21,591.4 |
| 35 | checked JSON | brotli-11 | 41,120 | 262,207.6 / 262,207.6 | 20,053.5 / 20,053.5 |
| 35 | project v0.2 | brotli-11 | 43,119 | 96,039.2 / 96,039.2 | 68,788.8 / 68,788.8 |
| 40 | canonical JSON | brotli-11 | 34,617 | 249,720.0 / 249,720.0 | 19,879.2 / 19,879.2 |
| 40 | checked JSON | brotli-11 | 39,948 | 263,914.9 / 263,914.9 | 19,634.3 / 19,634.3 |
| 40 | project v0.2 | brotli-11 | 41,360 | 97,491.2 / 97,491.2 | 72,791.2 / 72,791.2 |
| 56 | canonical JSON | brotli-11 | 31,512 | 246,400.1 / 246,400.1 | 19,061.1 / 19,061.1 |
| 56 | checked JSON | brotli-11 | 36,873 | 263,532.0 / 263,532.0 | 19,579.9 / 19,579.9 |
| 56 | project v0.2 | brotli-11 | 36,983 | 95,950.0 / 95,950.0 | 68,345.8 / 68,345.8 |
| 64 | canonical JSON | brotli-11 | 31,669 | 246,880.2 / 246,880.2 | 19,530.9 / 19,530.9 |
| 64 | checked JSON | brotli-11 | 37,029 | 265,488.7 / 265,488.7 | 19,364.3 / 19,364.3 |
| 64 | project v0.2 | brotli-11 | 36,849 | 96,140.9 / 96,140.9 | 68,967.8 / 68,967.8 |
| 70 | canonical JSON | brotli-11 | 29,946 | 245,856.0 / 245,856.0 | 19,231.5 / 19,231.5 |
| 70 | checked JSON | brotli-11 | 35,256 | 268,865.4 / 268,865.4 | 19,796.8 / 19,796.8 |
| 70 | project v0.2 | brotli-11 | 34,751 | 101,516.5 / 101,516.5 | 80,115.0 / 80,115.0 |
| 128 | canonical JSON | brotli-11 | 27,994 | 261,198.0 / 261,198.0 | 20,803.7 / 20,803.7 |
| 128 | checked JSON | brotli-11 | 33,267 | 276,149.3 / 276,149.3 | 19,621.8 / 19,621.8 |
| 128 | project v0.2 | brotli-11 | 31,666 | 101,073.6 / 101,073.6 | 67,765.6 / 67,765.6 |
| 140 | canonical JSON | brotli-11 | 26,320 | 251,647.8 / 251,647.8 | 18,934.0 / 18,934.0 |
| 140 | checked JSON | brotli-11 | 31,606 | 275,920.7 / 275,920.7 | 19,527.2 / 19,527.2 |
| 140 | project v0.2 | brotli-11 | 29,428 | 190,407.8 / 190,407.8 | 254,587.2 / 254,587.2 |
| 256 | canonical JSON | brotli-11 | 25,732 | 322,549.5 / 322,549.5 | 24,643.0 / 24,643.0 |
| 256 | checked JSON | brotli-11 | 30,966 | 386,514.2 / 386,514.2 | 28,846.6 / 28,846.6 |
| 256 | project v0.2 | brotli-11 | 28,842 | 121,430.8 / 121,430.8 | 78,641.1 / 78,641.1 |
| 280 | canonical JSON | brotli-11 | 24,088 | 264,510.5 / 264,510.5 | 21,160.0 / 21,160.0 |
| 280 | checked JSON | brotli-11 | 29,237 | 289,148.5 / 289,148.5 | 20,057.3 / 20,057.3 |
| 280 | project v0.2 | brotli-11 | 26,575 | 138,749.4 / 138,749.4 | 90,552.9 / 90,552.9 |

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
- Repeating a 1,402-byte profile at every reset can dominate short
  sessions.  The cached sensitivity is materially more favorable but is valid
  only when cache identity, authorization, and availability are established.
- Smaller bytes do not imply lower latency.  The current validation-heavy
  project decode path can remain slower even when its wire total is smaller.
- Exact and deterministic gates passed for 378/378 and
  378/378 result rows, respectively, under both
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

- Implementation SHA-256: `5c16d2db42adc0988a72148c30d321aa2be4616572b6e447641d64231c27699c`
- Test SHA-256: `0ba1affc660da7cb2cd40b888aa7ee55c5d148fde628d2049757234bb65be2ba`

From the repository root in the pinned Python 3.12 research environment:

```bash
python -m pip install -r requirements-research.lock
PYTHONDONTWRITEBYTECODE=1 python urusilla_session_reset_sweep.py --output SESSION_RESET_SWEEP_RESULTS.md
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_urusilla_session_reset_sweep -v
```
