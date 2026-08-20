# UrusillaTokenSurface v0.3 grouped holdout and generalization study

Execution time (UTC): `2026-08-20T13:49:00+00:00`  
Runtime: `CPython 3.12.14` / `macOS-15.0-arm64-arm-64bit`  
Tokenizer package: `tiktoken 0.11.0` with `cl100k_base` and `o200k_base`  
Source corpus: 280 messages, SHA-256 `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`  
English projection: SHA-256 `9c10963c0b8f6494faaee6aea7b2c0e4e06e23ee3631686f01fb1d7d29ad6bef`  
Development: 224 messages in 59 groups, SHA-256 `f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759`  
Grouped holdout: 56 messages in 16 groups, SHA-256 `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`  
Held group-list SHA-256: `939d3572db604b9ccf0c8c83fb6792fdd0dbe4adafbd6924767e4b0a027c7f2d`  
Out-of-domain: 10 messages, SHA-256 `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`  
Codebook: 1,024 symbols, SHA-256 `d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695`, trained in 6.065s  
Timing repeats after warm-up: 1

## Design and leakage controls

The fixed 280-message source corpus is first projected to ASCII English semantic content by replacing only its declared multilingual fixtures. The machine surface remains a negotiated non-ASCII alphabet by design. No content is selected by codec performance. A group key combines act, schema, body kind, and an act-specific semantic selector such as claim predicate, action capability, evidence stance, uncertainty model, or resolution status. Within each act, groups are ranked by SHA-256 under the exact domain `urusilla-token-surface-holdout-v1|`; the first `max(1, floor(group_count/4))` groups are held out. All messages in one group stay on one side, and every act appears in the holdout.

The v0.3 byte-pair entries are trained from the 224 development v0.2 frames only. The 56 grouped holdout frames and ten hand-authored out-of-domain frames are encoded only after the codebook is frozen. The out-of-domain corpus uses new schemas, agents, predicates, values, and map shapes while retaining the unchanged core validator.

This is leakage-resistant relative to a random message split, not a blind external test. The split rule and group definition were authored after inspecting the generator; both partitions still use that generator. The v0.2 static profile and the v0.3 symbol alphabet were developed earlier using the same benchmark family and named tokenizers. The out-of-domain set is small and was authored in this repository.

## Warm held-out results

| Dataset | Codec | UTF-8 bytes | Characters | cl100k_base | o200k_base | Exact | Deterministic |
|---|---|---:|---:|---:|---:|---:|---:|
| grouped holdout | sorted minified JSON | 52,604 | 52,604 | 16,763 | 17,224 | 56/56 | 56/56 |
| grouped holdout | Base64 UrusillaWire v0.2 | 15,448 | 15,448 | 10,933 | 10,151 | 56/56 | 56/56 |
| grouped holdout | UrusillaTokenSurface v0.3 warm | 15,368 | 6,382 | 6,367 | 6,312 | 56/56 | 56/56 |
| out of domain | sorted minified JSON | 9,856 | 9,856 | 2,808 | 2,897 | 10/10 | 10/10 |
| out of domain | Base64 UrusillaWire v0.2 | 8,212 | 8,212 | 5,829 | 5,467 | 10/10 | 10/10 |
| out of domain | UrusillaTokenSurface v0.3 warm | 11,496 | 5,391 | 5,376 | 5,026 | 10/10 | 10/10 |

JSON is sorted, minified, UTF-8, and passed through the shared semantic validator on decode. Base64 contains each complete canonical v0.2 frame. Token counts are exact only for the two named encoding assets in tiktoken 0.11.0.

Warm deltas for v0.3 (negative is smaller):

| Dataset | Baseline | UTF-8 bytes | cl100k_base | o200k_base |
|---|---|---:|---:|---:|
| grouped holdout | sorted minified JSON | -70.8% | -62.0% | -63.4% |
| grouped holdout | Base64 UrusillaWire v0.2 | -0.5% | -41.8% | -37.8% |
| out of domain | sorted minified JSON | +16.6% | +91.5% | +73.5% |
| out of domain | Base64 UrusillaWire v0.2 | +40.0% | -7.8% | -8.1% |

## Raw fallback use

A raw fallback symbol is one of the first 256 codebook entries and expands to exactly one frame byte. Symbol rate divides raw symbols by all v0.3 payload symbols. Byte coverage divides raw fallback bytes by the original v0.2 frame bytes.

| Dataset | Messages with raw fallback | Raw symbols / payload symbols | Raw symbol rate | Raw bytes / frame bytes | Raw byte coverage |
|---|---:|---:|---:|---:|---:|
| grouped holdout | 56/56 | 4,204/5,822 | 72.2% | 4,204/11,525 | 36.5% |
| out of domain | 10/10 | 4,775/5,291 | 90.2% | 4,775/6,148 | 77.7% |

## Cold cost and strict break-even

The canonical codebook capsule is 8,942 binary bytes. Its actual `S3C:` transfer is 11,927 UTF-8 bytes, 8,224 cl100k_base tokens, and 7,746 o200k_base tokens. The shared v0.2 profile capsule is 1,402 binary bytes; its Base64 transfer is 1,872 bytes, 1,346 and 1,261 tokens.

Strict break-even is the first integer N satisfying `cold + N * mean(v0.3) < N * mean(baseline)`. The incremental row charges the v0.3 codebook. The standalone JSON row also charges the v0.2 profile because JSON does not already have it. Results assume the measured held-out workload mix repeats.

| Dataset | Baseline | Cold scenario | UTF-8 byte N | cl100k_base N | o200k_base N |
|---|---|---|---:|---:|---:|
| grouped holdout | sorted minified JSON | standalone profile + codebook | 21 | 52 | 47 |
| grouped holdout | Base64 UrusillaWire v0.2 | incremental codebook | 8349 | 101 | 113 |
| out of domain | sorted minified JSON | standalone profile + codebook | never on mean | never on mean | never on mean |
| out of domain | Base64 UrusillaWire v0.2 | incremental codebook | never on mean | 182 | 176 |

## Codec latency on the combined evaluation set

| Codec | Encode p50 (us) | Encode p95 (us) | Decode p50 (us) | Decode p95 (us) |
|---|---:|---:|---:|---:|
| sorted minified JSON | 11.92 | 17.50 | 86.29 | 194.79 |
| Base64 UrusillaWire v0.2 | 152.96 | 240.75 | 411.38 | 1337.75 |
| UrusillaTokenSurface v0.3 warm | 2064.83 | 2820.58 | 2922.67 | 4763.88 |

These paths do unequal work. JSON has no transport checksum; v0.2 validates one canonical frame; v0.3 additionally performs longest-match substitution, its surface checksum, v0.2 decoding, and canonical re-encoding. Latency is an implementation-path measurement on this machine.

## Integrity and frozen vectors

Deterministic single-symbol payload corruptions rejected: 264/264. This is accidental-error detection, not authentication.

| Dataset | JSON text SHA-256 | Base64 v0.2 text SHA-256 | v0.3 text SHA-256 |
|---|---|---|---|
| grouped holdout | `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9` | `4391adde6540d09573fbdfbf2781456cc0d5c027502efca2085984a8334274ac` | `f66ade3a5538b6818728870a1ee1e51c1e6781385416cde3a48c68d7301bd0e5` |
| out of domain | `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310` | `cb1b69c69876a4c9945494b8aa2274d39fd40a1b353c1fda00c8b11501d09523` | `1fd127e6956edf507e5668127662d8be40adce38682001946ad09463406820e4` |

All three codecs round-trip through the unchanged validator and reproduce their text deterministically. Decoder tests also reject wrong codebooks, malformed Base64, corrupted capsules, altered surface symbols, and semantically invalid messages before any effect.

## Interpretation and limitations

The grouped holdout measures recombination of generator features, not a new real-world distribution. The out-of-domain set is structurally novel but too small for a generalization claim. Neither set measures natural-language construction, model comprehension, task success, repair turns, transport envelopes, authorization, or adversarial cryptography.

The learned byte entries see development frames only, but the v0.2 profile still contains strings and shapes chosen from the benchmark family. The 1,024-symbol alphabet was preselected to be one token in both measured tokenizers, so this is not tokenizer holdout. Cold transfer, fallback, byte regressions, and slower v0.3 latency are retained rather than filtered. A production claim needs a preregistered split, independently authored schemas and messages, unseen tokenizers/models, and end-to-end task evidence.

## Reproduction

```bash
python3 -m venv work/token-surface-holdout-venv
work/token-surface-holdout-venv/bin/python -m pip install tiktoken==0.11.0
PYTHONPATH=. work/token-surface-holdout-venv/bin/python urusilla_token_surface_holdout.py --benchmark --repeats 10
PYTHONPATH=. work/token-surface-holdout-venv/bin/python -m unittest test_urusilla_token_surface_holdout.py -v
```
