# UrusillaTokenSurface v0.3 tokenizer-aware experiment

Execution time (UTC): `2026-08-20T13:48:48+00:00`  
Runtime: `CPython 3.12.14` / `macOS-15.0-arm64-arm-64bit`  
Tokenizer package: `tiktoken 0.11.0`  
Corpus: `urusilla-benchmark-corpus-v1`, 280 messages, SHA-256 `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`  
Codebook: 1,024 symbols, SHA-256 `4ba2dab386c0918267f86aac94cc965d0297fb8744bc78c458243047f01660ab`, content ID `S6Las4bAkYJn-GqslMyWXQ`  
Surface sequence SHA-256: `a2adb45c975c5feca048e7846225b20fdc78964e52d10274f70da0cea102362a`  
Codebook rebuild time: 8.708s; timing repeats after negotiation: 1

## Scope and central result

This is an optional text codec over unchanged canonical UrusillaIR and UrusillaWire v0.2. It is not a new semantic core. The codebook was derived from this exact development corpus, so every compression number below is an in-sample upper bound, not a held-out or cross-model result.

Warm v0.3 used 29,883 `cl100k_base` tokens and 29,669 `o200k_base` tokens. Relative to Base64 v0.2, that is +42.6% saved and +38.4% saved, respectively. Cold codebook transfer and strict break-even are charged below.

## Warm text results

| Codec | UTF-8 bytes | Characters | cl100k_base tokens | o200k_base tokens | Exact | Deterministic |
|---|---:|---:|---:|---:|---:|---:|
| sorted minified JSON | 266,684 | 264,123 | 85,429 | 87,494 | 280/280 | 280/280 |
| Base64 UrusillaWire v0.1 | 235,116 | 235,116 | 166,025 | 154,919 | 280/280 | 280/280 |
| Base64 UrusillaWire v0.2 warm | 73,376 | 73,376 | 52,092 | 48,199 | 280/280 | 280/280 |
| UrusillaTokenSurface v0.3 warm | 73,261 | 29,922 | 29,883 | 29,669 | 280/280 | 280/280 |

Base64 rows encode each complete canonical binary frame independently. JSON is sorted, minified, UTF-8, and validated through the same semantic normalizer. Token counts are exact for the named tokenizer assets as loaded by tiktoken 0.11.0; they are not token counts for every model or provider.

## Cold codebook cost and strict break-even

The canonical binary capsule is 8,520 bytes. Its actual `S3C:` Base64url transfer form is 11,364 UTF-8 bytes, 7,859 `cl100k_base` tokens, and 7,385 `o200k_base` tokens.

Strict break-even is the first integer N for which `cold + N * mean(v0.3)` is strictly less than `N * mean(baseline)`. It assumes the negotiated codebook is reused and does not charge the separate Urusilla grammar or v0.2 profile capsule, which both v0.2 and v0.3 need.

| Baseline | UTF-8 byte break-even | cl100k_base token break-even | o200k_base token break-even |
|---|---:|---:|---:|
| sorted minified JSON | 17 | 40 | 36 |
| Base64 UrusillaWire v0.1 | 20 | 17 | 17 |
| Base64 UrusillaWire v0.2 warm | 27669 | 100 | 112 |

## Codec latency after negotiation

| Codec | Encode p50 (us) | Encode p95 (us) | Decode p50 (us) | Decode p95 (us) |
|---|---:|---:|---:|---:|
| sorted minified JSON | 12.62 | 18.83 | 69.50 | 136.33 |
| Base64 UrusillaWire v0.1 | 148.08 | 272.83 | 364.46 | 657.50 |
| Base64 UrusillaWire v0.2 warm | 113.71 | 202.54 | 245.67 | 419.38 |
| UrusillaTokenSurface v0.3 warm | 848.21 | 1052.42 | 1809.75 | 2231.50 |

Paths do unequal work: JSON has no transport checksum, Base64 rows invoke their binary codec, and v0.3 performs longest-match substitution plus v0.2 validation and canonical re-encoding. These are current Python implementation timings, not protocol-intrinsic limits.

## Integrity, safety, and limitations

All 1,120/1,120 deterministic single-symbol corruptions were rejected. The codebook capsule has a 128-bit truncated content address, bound to each surface through the negotiated slot, and the surface has a 64-bit accidental-error checksum; neither is authentication. Urusilla effect eligibility still requires authenticated identity, schema policy, and conversation-state checks.

The full codebook content address is bound to a session-local one-symbol slot during negotiation, so it is not repeated in each surface. Slot reuse without renegotiation is invalid. Within a payload, the encoder switches at byte-fragment granularity between learned multi-byte entries and complete raw-byte fallbacks. Once both peers support a new UrusillaIR and v0.2 grammar revision, unfamiliar byte sequences can therefore use fallback entries immediately and later negotiate a new frozen codebook.

The decoder limits surface bytes, payload symbols, codebook size, entry expansion, and decoded frame bytes. Payload symbols are visible, non-ASCII, non-whitespace characters without bidirectional controls or markup delimiters. The format contains no executable instructions and must not be inserted into a model prompt as if it were trusted text.

The codebook openly overfits repeated byte substrings in the development corpus. It does not establish held-out performance, natural-language equivalence, model comprehension, cross-tokenizer universality, or adoption. UTF-8 byte size can be unfavorable because most surface symbols occupy multiple bytes. A release gate requires held-out schemas and tokenizers, multi-model task-success tests, adversarial parsing, and an independently generated codebook.

## Reproduction

```bash
python3 -m venv work/token-surface-venv
work/token-surface-venv/bin/python -m pip install tiktoken==0.11.0
PYTHONPATH=. work/token-surface-venv/bin/python urusilla_token_surface_v03.py --benchmark
PYTHONPATH=. work/token-surface-venv/bin/python -m unittest test_urusilla_token_surface_v03.py -v
```
