# Generalization surface v0.6 experiment

## Result

The receiver pre-input selector had **zero warm token regressions in 1,160/1,160 message/receiver pairs** against the complete v0.5 candidate. On the ten frozen out-of-domain messages, it reduced aggregate warm receiver tokens for every pinned tokenizer by **1.76% to 5.83%**. Development and grouped-holdout warm totals were unchanged because the selector retained v0.5 for every message.

Exact semantic recovery passed for the existing readable surface in **290/290** messages, for the train-only surface in **290/290**, and for selected texts in **1,160/1,160** pairs. Deterministic re-encoding/reselection passed in the same counts. Deterministic payload mutations were rejected in **1,740/1,740** trials.

This is a serialization and receiver-token experiment. No language model, network service, or paid API was invoked. Model comprehension, sender generation, multi-turn task success, cross-vendor transfer, energy, adoption, and state-of-the-art standing remain unmeasured.

## Frozen train-only optimization

The new readable `@2` surface keeps the fixed 13-field symbolic layout and compact typed value grammar, then replaces frequent nested keys and string values with one-character aliases. The profile is derived only from the exact frozen development partition. Its objective is frequency multiplied by UTF-8 bytes saved; it does not inspect holdout token counts, out-of-domain content, checksum luck, or task answers. The implementation refuses any training sequence whose canonical digest is not the frozen development digest.

The frozen profile contains 26 key aliases and 26 value aliases. Its canonical capsule is 1,358 UTF-8 bytes and has SHA-256 `f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d`.

Each `@2` text carries an 11-character Base64url BLAKE2s-64 checksum bound to the format domain, frozen profile digest, and complete payload. This detects accidental corruption but is not sender authentication. Decoding verifies the checksum before parsing, expands aliases, applies shared semantic validation, and requires byte-identical canonical re-encoding.

## Warm exact token totals

Counts are complete serialization texts without tokenizer special tokens. JSON and Controlled Terse English are raw token references and do not carry equivalent checksum framing; v0.4, v0.5, `@1`, `@2`, and selected surfaces retain their specified integrity framing.

### Development Training Partition

| Receiver tokenizer | JSON raw | CTE raw | v0.4 | v0.5 | Existing readable | Train-only readable | Selected | vs v0.5 | Selected v0.5/existing/train-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 67,399 | 63,334 | 23,751 | 24,423 | 65,602 | 52,370 | 24,423 | +0.00% | 224/0/0 |
| o200k_base | 69,243 | 63,333 | 23,560 | 24,232 | 67,104 | 52,694 | 24,232 | +0.00% | 224/0/0 |
| Qwen2.5-7B-Instruct tokenizer | 79,986 | 75,921 | 23,610 | 24,282 | 78,300 | 65,037 | 24,282 | +0.00% | 224/0/0 |
| Mistral-7B-Instruct-v0.3 tokenizer | 94,620 | 85,421 | 23,859 | 24,755 | 90,597 | 73,716 | 24,755 | +0.00% | 224/0/0 |

### Grouped Holdout

| Receiver tokenizer | JSON raw | CTE raw | v0.4 | v0.5 | Existing readable | Train-only readable | Selected | vs v0.5 | Selected v0.5/existing/train-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 16,763 | 15,764 | 6,362 | 6,530 | 16,322 | 13,083 | 6,530 | +0.00% | 56/0/0 |
| o200k_base | 17,224 | 15,770 | 6,310 | 6,478 | 16,693 | 13,157 | 6,478 | +0.00% | 56/0/0 |
| Qwen2.5-7B-Instruct tokenizer | 19,892 | 18,893 | 6,333 | 6,501 | 19,474 | 16,232 | 6,501 | +0.00% | 56/0/0 |
| Mistral-7B-Instruct-v0.3 tokenizer | 23,514 | 21,228 | 6,412 | 6,636 | 22,505 | 18,350 | 6,636 | +0.00% | 56/0/0 |

### Out Of Domain

| Receiver tokenizer | JSON raw | CTE raw | v0.4 | v0.5 | Existing readable | Train-only readable | Selected | vs v0.5 | Selected v0.5/existing/train-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 2,808 | 2,639 | 5,361 | 2,761 | 2,724 | 2,600 | 2,600 | +5.83% | 0/0/10 |
| o200k_base | 2,897 | 2,645 | 5,011 | 2,762 | 2,798 | 2,618 | 2,618 | +5.21% | 0/0/10 |
| Qwen2.5-7B-Instruct tokenizer | 3,267 | 3,098 | 5,353 | 3,192 | 3,190 | 3,065 | 3,065 | +3.98% | 0/0/10 |
| Mistral-7B-Instruct-v0.3 tokenizer | 4,001 | 3,599 | 5,368 | 3,691 | 3,822 | 3,630 | 3,626 | +1.76% | 2/0/8 |

## Per-message guard and unfavorable cases

The receiver tokenizer is negotiated before input. For each message the selector exactly counts the byte-identical v0.5 result, existing readable text, and train-only readable text, then minimizes `(token count, fixed mode rank, text)`. v0.5 wins ties. This is an input-only cost decision, not a semantic or answer-quality oracle.

| Dataset | Receiver tokenizer | Better | Tied | Worse | Tokens saved | Largest one-message saving |
|---|---|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | 0 | 224 | 0 | 0 | 0 |
| development training partition | o200k_base | 0 | 224 | 0 | 0 | 0 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 0 | 224 | 0 | 0 | 0 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 0 | 224 | 0 | 0 | 0 |
| grouped holdout | cl100k_base | 0 | 56 | 0 | 0 | 0 |
| grouped holdout | o200k_base | 0 | 56 | 0 | 0 | 0 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 0 | 56 | 0 | 0 | 0 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 0 | 56 | 0 | 0 | 0 |
| out of domain | cl100k_base | 10 | 0 | 0 | 161 | 25 |
| out of domain | o200k_base | 10 | 0 | 0 | 144 | 22 |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 10 | 0 | 0 | 127 | 22 |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 8 | 2 | 0 | 65 | 15 |

The token selector can choose a text with more UTF-8 bytes than v0.5 because bytes are not its objective. These cases are retained below.

| Dataset | Receiver tokenizer | v0.5 bytes | Selected bytes | Messages with more bytes | Worst byte increase |
|---|---|---:|---:|---:|---:|
| development training partition | cl100k_base | 58,802 | 58,802 | 0 | +0.00% |
| development training partition | o200k_base | 58,802 | 58,802 | 0 | +0.00% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 58,802 | 58,802 | 0 | +0.00% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 58,802 | 58,802 | 0 | +0.00% |
| grouped holdout | cl100k_base | 15,592 | 15,592 | 0 | +0.00% |
| grouped holdout | o200k_base | 15,592 | 15,592 | 0 | +0.00% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 15,592 | 15,592 | 0 | +0.00% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 15,592 | 15,592 | 0 | +0.00% |
| out of domain | cl100k_base | 8,552 | 7,248 | 0 | +0.00% |
| out of domain | o200k_base | 8,552 | 7,248 | 0 | +0.00% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 8,728 | 7,248 | 0 | +0.00% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 8,728 | 7,475 | 0 | +0.00% |

## Cold known-session planning

Before any message input, the planner enumerates all eight combinations of the structured bundle, existing grammar, and train-only grammar plus alias profile. A disabled artifact makes its dependent candidate ineligible. The complete v0.5 no-bundle and activated-bundle plans remain exact options, so the selected known-session total cannot regress. The profile is charged once and the two grammars are charged independently; no shared artifact is double-counted.

| Dataset | Receiver tokenizer | v0.5 cold plan | Selected cold plan | Saving | New cold tokens | Structured/existing/train-only active | Cold-plan v0.5/existing/train-only |
|---|---|---:|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | 33,993 | 33,993 | +0.00% | 9,570 | yes/no/no | 224/0/0 |
| development training partition | o200k_base | 33,239 | 33,239 | +0.00% | 9,007 | yes/no/no | 224/0/0 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 34,001 | 34,001 | +0.00% | 9,719 | yes/no/no | 224/0/0 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 35,693 | 35,693 | +0.00% | 10,938 | yes/no/no | 224/0/0 |
| grouped holdout | cl100k_base | 16,100 | 13,570 | +15.71% | 487 | no/no/yes | 0/0/56 |
| grouped holdout | o200k_base | 15,485 | 13,699 | +11.53% | 542 | no/no/yes | 0/0/56 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 16,220 | 16,220 | +0.00% | 9,719 | yes/no/no | 56/0/0 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 17,574 | 17,574 | +0.00% | 10,938 | yes/no/no | 56/0/0 |
| out of domain | cl100k_base | 2,761 | 2,761 | +0.00% | 0 | no/no/no | 10/0/0 |
| out of domain | o200k_base | 2,762 | 2,762 | +0.00% | 0 | no/no/no | 10/0/0 |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 3,220 | 3,220 | +0.00% | 0 | no/no/no | 10/0/0 |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 3,726 | 3,726 | +0.00% | 0 | no/no/no | 10/0/0 |

Warm out-of-domain improvements did **not** amortize the new grammar and profile on this ten-message session. Every out-of-domain cold plan therefore retained a v0.5-compatible state. Conversely, grouped holdout activated only the train-only profile for cl100k_base and o200k_base because avoiding the much larger structured bundle reduced total cold-session cost; Qwen and Mistral retained their v0.5 structured plans.

### Cold artifact costs

| Receiver tokenizer | Existing grammar | Train-only grammar | Alias profile | Structured bundle |
|---|---:|---:|---:|---:|
| cl100k_base | 113 tokens / 411 bytes | 110 / 437 | 377 / 1,358 | 9,570 / 13,799 |
| o200k_base | 112 tokens / 411 bytes | 111 / 437 | 431 / 1,358 | 9,007 / 13,799 |
| Qwen2.5-7B-Instruct tokenizer | 115 tokens / 411 bytes | 112 / 437 | 402 / 1,358 | 9,719 / 13,799 |
| Mistral-7B-Instruct-v0.3 tokenizer | 139 tokens / 411 bytes | 146 / 437 | 527 / 1,358 | 10,938 / 13,799 |

## Reference implementation latency

Times are per message on this machine. Direct rows encode one known readable representation. Fresh-selector rows rebuild all eligible representations and perform exact tokenizer counting; they intentionally expose unequal and substantial CPU work and are not protocol latency limits.

| Path | Encode/select median | Encode/select p95 | Decode median | Decode p95 |
|---|---:|---:|---:|---:|
| direct existing readable | 86.7 µs | 142.9 µs | 181.4 µs | 305.4 µs |
| direct train-only readable | 232.9 µs | 332.7 µs | 452.8 µs | 704.6 µs |
| fresh v0.5 for cl100k_base | 3287.5 µs | 4740.0 µs | 1962.0 µs | 2292.3 µs |
| fresh v0.6 for cl100k_base | 5098.6 µs | 7266.8 µs | 2061.1 µs | 2830.2 µs |
| fresh v0.5 for o200k_base | 3562.1 µs | 4821.8 µs | 1944.4 µs | 2304.6 µs |
| fresh v0.6 for o200k_base | 5468.9 µs | 7850.4 µs | 2279.5 µs | 3746.5 µs |
| fresh v0.5 for Qwen2.5-7B-Instruct tokenizer | 5465.6 µs | 8046.5 µs | 1954.8 µs | 2440.6 µs |
| fresh v0.6 for Qwen2.5-7B-Instruct tokenizer | 8269.0 µs | 11786.7 µs | 2005.5 µs | 2316.7 µs |
| fresh v0.5 for Mistral-7B-Instruct-v0.3 tokenizer | 3769.8 µs | 5304.5 µs | 1920.9 µs | 2284.8 µs |
| fresh v0.6 for Mistral-7B-Instruct-v0.3 tokenizer | 6125.2 µs | 8189.6 µs | 2061.4 µs | 2579.7 µs |

## Integrity and resource checks

- Existing-readable exact and deterministic checks: 290/290 and 290/290.
- Train-only-readable exact and deterministic checks: 290/290 and 290/290.
- Selected exact and deterministic checks: 1,160/1,160 and 1,160/1,160.
- Corruption rejection: existing 290/290; train-only 290/290; selected 1,160/1,160.
- The decoder rejects wrong prefixes, malformed or mismatched checksums, trailing data, duplicate or colliding expanded keys, non-canonical encodings, invalid semantic types, oversized UTF-8 inputs, and excessive parser recursion.
- Resource limits and shared semantic limits bound surface bytes, strings, collection items, and tree depth. The checksum is error detection only, not authentication, authorization, replay defense, or sandboxing.

## Frozen inputs and reproducibility

- Format: `urusilla-generalization-surface-v0.6-experimental`
- Development partition: 224 messages; SHA-256 `f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759`
- Grouped holdout: 56 messages; SHA-256 `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`
- Out of domain: 10 messages; SHA-256 `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`
- Frozen structured codebook SHA-256: `d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695`
- Train-only alias profile SHA-256: `f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d`
- Complete v0.6 snapshot SHA-256: `81993226c8fe9b2bd631a2e63e59355fa8e31e993ecbe14af1848a9c5a44bb57`
- Tokenizer packages: `tiktoken==0.11.0`, `tokenizers==0.21.4`

- `cl100k_base`: cl100k_base; tiktoken 0.11.0; vocabulary 100,277; fingerprint `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d`
- `o200k_base`: o200k_base; tiktoken 0.11.0; vocabulary 200,019; fingerprint `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc`
- `qwen2_5_7b_instruct`: Qwen2.5-7B-Instruct tokenizer; tokenizers 0.21.4; vocabulary 151,665; fingerprint `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`
- `mistral_7b_instruct_v03`: Mistral-7B-Instruct-v0.3 tokenizer; tokenizers 0.21.4; vocabulary 32,768; fingerprint `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49`

Selected text-sequence SHA-256 values:

- development training partition, `cl100k_base`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- development training partition, `o200k_base`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- development training partition, `qwen2_5_7b_instruct`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- development training partition, `mistral_7b_instruct_v03`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- grouped holdout, `cl100k_base`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- grouped holdout, `o200k_base`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- grouped holdout, `qwen2_5_7b_instruct`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- grouped holdout, `mistral_7b_instruct_v03`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- out of domain, `cl100k_base`: `1eacd2a3a7df6cb58aa19f8864cd158568c563d49c6c694523da9589e29e30a7`
- out of domain, `o200k_base`: `1eacd2a3a7df6cb58aa19f8864cd158568c563d49c6c694523da9589e29e30a7`
- out of domain, `qwen2_5_7b_instruct`: `1eacd2a3a7df6cb58aa19f8864cd158568c563d49c6c694523da9589e29e30a7`
- out of domain, `mistral_7b_instruct_v03`: `6fef9249b28017ab08bdec7afb8728b1a198a88e2cd6c1a3286888bffdb96953`

Source SHA-256 values:

- implementation and benchmark: `85ab4676698acb2a887e31c297ed938d09c898a39d645b710a71149064fce753`
- conformance tests: `7b5005c735fac9ace696f04bae5902098806eb892114f0f58169872e6151f658`

Environment:

- Python: `3.12.14`
- Platform: `macOS-15.0-arm64-arm-64bit`

Reproduce from the repository root with the pinned offline tokenizer assets:

```bash
PYTHONPATH=. python urusilla_generalization_surface_v06.py --benchmark --assets-dir /path/to/tokenizer_assets --repeats 1
PYTHONPATH=. python -m unittest test_urusilla_generalization_surface_v06.py -v
```

## Limitations

- Development results are in-sample. Grouped holdout shares a synthetic generator family, and out of domain has only ten repository-authored messages. The observed improvement is narrow evidence, not a general compression guarantee.
- Receiver-token no-regression is guaranteed only when the receiver tokenizer is negotiated and exactly available before input. One broadcast string cannot generally be optimal for receivers with different tokenizers.
- Counts exclude chat templates, BOS/EOS, surrounding prompts, transport framing, negotiation messages, and hosted billing rules. These can change deployed cost.
- Cold planning is an offline optimum for a known sequence. Unknown-horizon streaming must remain on a previously cached profile or activate only after a conservative break-even rule; it cannot assume the reported session optimum.
- Readable means syntactically inspectable after learning the short grammar. It is not evidence that a language model understands or can reliably generate the surface. The prior prompted pilot did not establish this claim, and no model was invoked here.
- Raw JSON and Controlled Terse English references do not provide framing and integrity equivalent to the checksummed candidates, so their token totals are not protocol-equivalent competitors.
- Checksums increase bytes and tokens. Signatures, encryption, authentication, negotiation failure, malicious ambiguity, and operational governance are outside this experiment.
- Token reduction does not directly establish lower energy, latency, memory, monetary cost, or end-to-end application tokens. Exact counting and multi-candidate construction add CPU latency.
- No external benchmark search or independent replication was performed. No state-of-the-art or task-success claim is made.
