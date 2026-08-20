# Token surface v0.4: globally optimal symbol parsing

## Result

The globally optimal parser improved **33/290 messages** and reduced payload symbols from **32,684 to 32,645 (0.119% saved)** across the frozen development, grouped-holdout, and small out-of-domain sets. It never used more payload symbols than greedy longest-match parsing. This guarantee applies to symbol count only; UTF-8 bytes, tokenizer counts, and latency are measured separately below and retain every unfavorable result.

Exact canonical recovery and deterministic re-encoding both passed for **290/290 messages**. Deterministic single-symbol mutations were rejected in **1,160/1,160 trials**.

This is serialization accounting, not an end-to-end agent benchmark. No model decoded these surfaces, and the study does not measure task success, repair quality, reasoning, generation, energy, or adoption. It does not establish the highest performance among other projects.

## Optimization rule

For every byte boundary, the encoder evaluates every codebook entry that begins there and records `1 + shortest_suffix[next_boundary]`. It selects the lowest total and breaks a tie with the lower current codebook index. Because suffix choices use the same rule, the result is the lexicographically smallest index sequence among all minimum-symbol parses. Complete one-byte fallback entries make every valid frame reachable.

The codebook is unchanged. All three datasets use the same frozen codebook trained only on the 224-message development partition; grouped holdout and out-of-domain messages were not used to train it.

## Payload-level effect

Payload statistics exclude the two-character format prefix, one negotiated slot symbol, and seven checksum symbols.

| Dataset | Messages | Frame bytes | Greedy symbols | Optimal symbols | Saved | Improved / equal / worse | Max reduction | Greedy raw fallback | Optimal raw fallback |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| development training partition | 224 | 46,146 | 21,571 | 21,552 | +0.09% | 19/205/0 | 1 | 15,135 | 15,098 |
| grouped holdout | 56 | 11,525 | 5,822 | 5,817 | +0.09% | 4/52/0 | 2 | 4,204 | 4,189 |
| out of domain | 10 | 6,148 | 5,291 | 5,276 | +0.28% | 10/0/0 | 3 | 4,775 | 4,760 |

## Exact warm sizes and tokenizer counts

Every message is counted independently without BOS/EOS, chat templates, role markers, transport envelopes, prompts, or retransmissions.

### Development Training Partition

| Representation | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| Controlled Terse English | 177,153 | 177,153 | 63,334 | 63,333 | 75,921 | 85,421 |
| sorted minified JSON | 212,363 | 212,363 | 67,399 | 69,243 | 79,986 | 94,620 |
| Base64 wire v0.2 | 61,820 | 61,820 | 43,825 | 40,623 | 44,492 | 49,444 |
| token surface v0.3 | 57,956 | 23,811 | 23,775 | 23,583 | 23,636 | 23,860 |
| token surface v0.4 optimal | 57,906 | 23,792 | 23,751 | 23,560 | 23,610 | 23,859 |

v0.4 savings (positive is smaller; negative is an unfavorable regression):

| Baseline | UTF-8 bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|
| token surface v0.3 | +0.09% | +0.10% | +0.10% | +0.11% | +0.00% |
| Base64 wire v0.2 | +6.33% | +45.80% | +42.00% | +46.93% | +51.75% |
| sorted minified JSON | +72.73% | +64.76% | +65.97% | +70.48% | +74.78% |
| Controlled Terse English | +67.31% | +62.50% | +62.80% | +68.90% | +72.07% |

### Grouped Holdout

| Representation | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| Controlled Terse English | 43,880 | 43,880 | 15,764 | 15,770 | 18,893 | 21,228 |
| sorted minified JSON | 52,604 | 52,604 | 16,763 | 17,224 | 19,892 | 23,514 |
| Base64 wire v0.2 | 15,448 | 15,448 | 10,933 | 10,151 | 11,097 | 12,313 |
| token surface v0.3 | 15,368 | 6,382 | 6,367 | 6,312 | 6,337 | 6,409 |
| token surface v0.4 optimal | 15,368 | 6,377 | 6,362 | 6,310 | 6,333 | 6,412 |

v0.4 savings (positive is smaller; negative is an unfavorable regression):

| Baseline | UTF-8 bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|
| token surface v0.3 | +0.00% | +0.08% | +0.03% | +0.06% | -0.05% |
| Base64 wire v0.2 | +0.52% | +41.81% | +37.84% | +42.93% | +47.92% |
| sorted minified JSON | +70.79% | +62.05% | +63.37% | +68.16% | +72.73% |
| Controlled Terse English | +64.98% | +59.64% | +59.99% | +66.48% | +69.79% |

### Out Of Domain

| Representation | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| Controlled Terse English | 8,402 | 8,402 | 2,639 | 2,645 | 3,098 | 3,599 |
| sorted minified JSON | 9,856 | 9,856 | 2,808 | 2,897 | 3,267 | 4,001 |
| Base64 wire v0.2 | 8,212 | 8,212 | 5,829 | 5,467 | 6,007 | 6,642 |
| token surface v0.3 | 11,496 | 5,391 | 5,376 | 5,026 | 5,368 | 5,385 |
| token surface v0.4 optimal | 11,465 | 5,376 | 5,361 | 5,011 | 5,353 | 5,368 |

v0.4 savings (positive is smaller; negative is an unfavorable regression):

| Baseline | UTF-8 bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|
| token surface v0.3 | +0.27% | +0.28% | +0.30% | +0.28% | +0.32% |
| Base64 wire v0.2 | -39.61% | +8.03% | +8.34% | +10.89% | +19.18% |
| sorted minified JSON | -16.33% | -90.92% | -72.97% | -63.85% | -34.17% |
| Controlled Terse English | -36.46% | -103.15% | -89.45% | -72.79% | -49.15% |

## Per-message unfavorable cases against v0.3

Aggregate savings can hide regressions. The table counts each message separately; worst regression is the largest percentage by which v0.4 exceeded v0.3 for that metric.

| Dataset | Metric | Improved | Equal | Regressed | Worst regression |
|---|---|---:|---:|---:|---:|
| development training partition | UTF-8 bytes | 91 | 57 | 76 | +1.46% |
| development training partition | cl100k_base | 24 | 200 | 0 | +0.00% |
| development training partition | o200k_base | 26 | 195 | 3 | +1.15% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 29 | 190 | 5 | +1.15% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 23 | 185 | 16 | +2.15% |
| grouped holdout | UTF-8 bytes | 20 | 17 | 19 | +1.02% |
| grouped holdout | cl100k_base | 4 | 52 | 0 | +0.00% |
| grouped holdout | o200k_base | 4 | 49 | 3 | +1.02% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 4 | 51 | 1 | +0.97% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 5 | 46 | 5 | +2.02% |
| out of domain | UTF-8 bytes | 10 | 0 | 0 | +0.00% |
| out of domain | cl100k_base | 10 | 0 | 0 | +0.00% |
| out of domain | o200k_base | 9 | 1 | 0 | +0.00% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 10 | 0 | 0 | +0.00% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 10 | 0 | 0 | +0.00% |

## Cold transfer and strict break-even

Controlled Terse English and JSON have no negotiated capsule in this accounting. Base64 v0.2 uses the static profile once. Each token surface uses that profile plus its text-wrapped copy of the same frozen binary codebook. Decoder software and the public specification are treated as installed.

| Capsule | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| static profile | 1,872 | 1,872 | 1,346 | 1,261 | 1,375 | 1,516 |
| v0.3 codebook wrapper | 11,927 | 11,927 | 8,224 | 7,746 | 8,344 | 9,422 |
| v0.4 codebook wrapper | 11,927 | 11,927 | 8,224 | 7,746 | 8,344 | 9,422 |

Strict break-even is the first integer `N` satisfying `cold + N × candidate_mean < N × baseline_mean`. `never on mean` is retained when the warm candidate is not smaller.

| Dataset | Candidate | Baseline | UTF-8 bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---|---|---:|---:|---:|---:|---:|
| development training partition | token surface v0.3 | Controlled Terse English | 26 | 55 | 51 | 42 | 40 |
| development training partition | token surface v0.3 | sorted minified JSON | 21 | 50 | 45 | 39 | 35 |
| development training partition | token surface v0.4 optimal | Controlled Terse English | 26 | 55 | 51 | 42 | 40 |
| development training partition | token surface v0.4 optimal | sorted minified JSON | 21 | 50 | 45 | 39 | 35 |
| grouped holdout | token surface v0.3 | Controlled Terse English | 28 | 58 | 54 | 44 | 42 |
| grouped holdout | token surface v0.3 | sorted minified JSON | 21 | 52 | 47 | 41 | 36 |
| grouped holdout | token surface v0.4 optimal | Controlled Terse English | 28 | 58 | 54 | 44 | 42 |
| grouped holdout | token surface v0.4 optimal | sorted minified JSON | 21 | 52 | 47 | 41 | 36 |
| out of domain | token surface v0.3 | Controlled Terse English | never on mean | never on mean | never on mean | never on mean | never on mean |
| out of domain | token surface v0.3 | sorted minified JSON | never on mean | never on mean | never on mean | never on mean | never on mean |
| out of domain | token surface v0.4 optimal | Controlled Terse English | never on mean | never on mean | never on mean | never on mean | never on mean |
| out of domain | token surface v0.4 optimal | sorted minified JSON | never on mean | never on mean | never on mean | never on mean | never on mean |

## Reference implementation latency

Times are per message on this machine. Paths do unequal work, and these Python measurements are not protocol limits. v0.4 performs a whole-frame dynamic program during encoding and also repeats it during canonical decoding, so slower latency is expected and must be weighed against any token reduction.

| Representation | Encode median | Encode p95 | Decode median | Decode p95 |
|---|---:|---:|---:|---:|
| Controlled Terse English | 104.2 µs | 217.5 µs | 557.5 µs | 1278.5 µs |
| sorted minified JSON | 16.4 µs | 68.5 µs | 115.0 µs | 300.4 µs |
| Base64 wire v0.2 | 185.3 µs | 492.3 µs | 292.7 µs | 525.2 µs |
| token surface v0.3 | 888.9 µs | 1527.6 µs | 2060.2 µs | 2622.7 µs |
| token surface v0.4 optimal | 1084.4 µs | 2247.0 µs | 2508.4 µs | 5050.3 µs |

## Safety and exactness checks

- Exact decoded-object equality: 290/290.
- Deterministic canonical re-encoding: 290/290.
- Deterministic one-symbol corruption rejection: 1,160/1,160.
- The decoder checks the negotiated slot, allowed alphabet, payload-symbol bound, decoded-frame bound, checksum, binary-frame validation, and canonical optimal re-encoding.
- The encoder rejects input beyond the shared 16 MiB binary-frame bound. This reference implementation stores choices in a compact unsigned array and suffix costs in a bounded rolling window; memory remains linear in frame length because exact reconstruction retains one choice per byte boundary.
- Surface text is data, not executable instructions or authorization.

## Frozen inputs and tokenizer identities

- Format: `urusilla-token-surface-v0.4-experimental`
- Development training partition: 224 messages; canonical SHA-256 `f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759`
- Grouped holdout: 56 messages; canonical SHA-256 `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`
- Out of domain: 10 messages; canonical SHA-256 `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`
- Frozen codebook SHA-256: `d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695`
- Tokenizer packages: `tiktoken==0.11.0`, `tokenizers==0.21.4`

- `cl100k_base`: cl100k_base; tiktoken 0.11.0; vocabulary 100,277; fingerprint `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d`
- `o200k_base`: o200k_base; tiktoken 0.11.0; vocabulary 200,019; fingerprint `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc`
- `qwen2_5_7b_instruct`: Qwen2.5-7B-Instruct tokenizer; tokenizers 0.21.4; vocabulary 151,665; fingerprint `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`
- `mistral_7b_instruct_v03`: Mistral-7B-Instruct-v0.3 tokenizer; tokenizers 0.21.4; vocabulary 32,768; fingerprint `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49`

v0.4 text-sequence SHA-256 values use an eight-byte big-endian length before every UTF-8 message:

- development training partition: `f093946e0c57fe0d4396b3797c0e4f3b5b4b062e872f4e33f8dfc296f54702d2`
- grouped holdout: `7a0cc5bb0c1a7f172a6df5ca3f490769d91eaf406cbcd0654584880eb2da4f58`
- out of domain: `bf5352bf5537ca7eea0b04482d432db6703c55cc96eb9445be27744197c7247a`

Source SHA-256 values:

- optimizer and benchmark: `a102d7c990e031b008782976e57579b4050176fd631f7fad9aa7abdb5a691f05`
- conformance tests: `d4ec3933d8a57cde1d4d44935c5f7d479226d426a17b9e6f0c9baa0f10f7d5e3`

Environment:

- Python: `3.12.14`
- Platform: `macOS-15.0-arm64-arm-64bit`

Reproduce from the repository root after installing the pinned tokenizer packages and verified assets:

```bash
PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_token_surface_v04.py --benchmark --assets-dir work/tokenizer_assets
PYTHONPATH=. work/tokenizer_venv/bin/python -m unittest test_urusilla_token_surface_v04.py -v
```

## Limitations

- Development results are in-sample because that partition trained the frozen codebook. Grouped holdout is synthetic and related to the same generator. The out-of-domain set has only ten repository-authored messages.
- The objective minimizes payload symbols, not UTF-8 bytes, a specific tokenizer's tokens, latency, or end-to-end cost. Header and checksum changes also mean whole-surface v0.3/v0.4 token differences are not a perfectly isolated parser ablation; the payload-symbol table is the isolated comparison.
- The alphabet was selected earlier around two named tokenizers. The two open-model tokenizers are useful transfer checks, not a representative sample of every deployed model.
- Controlled Terse English is deterministic compact notation, not ordinary agent conversation. Exact recovery does not prove that a language model can use either representation.
- Cold break-even assumes stable workload mix, successful caching and negotiation, no repair, and no retransmission.
- Token counts do not directly measure energy, latency, KV-cache behavior, hosted billing, or communication success.
