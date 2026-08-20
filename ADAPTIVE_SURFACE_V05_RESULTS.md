# Adaptive surface v0.5 receiver-token selection

## Result

Across 1,160 message/receiver pairs, the warm selector chose the exact lowest complete token count among the required v0.4 structured, Controlled Terse English, and minified JSON envelopes after including the mode marker and all applicable integrity overhead. It had **zero warm token regressions** against the best eligible required baseline on every individual message.

The safely lossless fragment candidate beat all three required whole-message candidates on **12/1,160 pairs**. Its complete envelope was counted before selection; an optimistic unframed fragment oracle is not used in the headline.

Exact semantic recovery and deterministic reselection passed for **1,160/1,160** pairs. Payload mutations were rejected in **1,160/1,160** deterministic trials.

No language model was invoked. These results do not measure task success, understanding, repair behavior, generation cost, inference latency, energy, or adoption, and they do not establish superiority over external projects.

## Selection contract

Every candidate begins with `A5 + mode`. JSON, controlled text, and fragment candidates then carry an 11-character checksum, a colon, and the payload. The checksum is the unpadded Base64url form of an eight-byte BLAKE2s digest over mode and payload; it detects accidental corruption but is not authentication. Structured mode uses `A5V:` followed by the v0.4 payload, reusing that payload's existing 64-bit checksum and canonical re-encoding check instead of paying for redundant integrity data.

For one negotiated receiver tokenizer, the selector counts every complete candidate without special tokens and chooses the tuple `(token_count, fixed_mode_rank, text)`. Fixed mode rank is JSON, controlled text, structured surface, then fragment surface. Therefore ties are deterministic and do not silently prefer a representation that requires cold state.

## Warm exact token totals and choices

Required-best is the per-message oracle over the three required complete envelopes. Adaptive includes the lossless fragment envelope. Equality is required unless fragments improve it.

### Development Training Partition

| Receiver tokenizer | JSON | Controlled text | v0.4 structured | Required-best | Fragment | Adaptive | vs required-best | Adaptive J/E/V/F |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 70,049 | 65,953 | 24,423 | 24,423 | 67,410 | 24,423 | +0.00% | 0/0/224/0 |
| o200k_base | 71,798 | 65,860 | 24,232 | 24,232 | 67,508 | 24,232 | +0.00% | 0/0/224/0 |
| Qwen2.5-7B-Instruct tokenizer | 82,691 | 78,606 | 24,282 | 24,282 | 78,720 | 24,282 | +0.00% | 0/0/224/0 |
| Mistral-7B-Instruct-v0.3 tokenizer | 97,534 | 88,196 | 24,755 | 24,755 | 87,633 | 24,755 | +0.00% | 0/0/224/0 |

### Grouped Holdout

| Receiver tokenizer | JSON | Controlled text | v0.4 structured | Required-best | Fragment | Adaptive | vs required-best | Adaptive J/E/V/F |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 17,429 | 16,416 | 6,530 | 6,530 | 16,793 | 6,530 | +0.00% | 0/0/56/0 |
| o200k_base | 17,867 | 16,394 | 6,478 | 6,478 | 16,821 | 6,478 | +0.00% | 0/0/56/0 |
| Qwen2.5-7B-Instruct tokenizer | 20,573 | 19,562 | 6,501 | 6,501 | 19,590 | 6,501 | +0.00% | 0/0/56/0 |
| Mistral-7B-Instruct-v0.3 tokenizer | 24,236 | 21,922 | 6,636 | 6,636 | 21,799 | 6,636 | +0.00% | 0/0/56/0 |

### Out Of Domain

| Receiver tokenizer | JSON | Controlled text | v0.4 structured | Required-best | Fragment | Adaptive | vs required-best | Adaptive J/E/V/F |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 2,925 | 2,761 | 5,391 | 2,761 | 2,814 | 2,761 | +0.00% | 0/10/0/0 |
| o200k_base | 3,008 | 2,762 | 5,041 | 2,762 | 2,825 | 2,762 | +0.00% | 0/10/0/0 |
| Qwen2.5-7B-Instruct tokenizer | 3,387 | 3,220 | 5,383 | 3,220 | 3,203 | 3,192 | +0.87% | 0/4/0/6 |
| Mistral-7B-Instruct-v0.3 tokenizer | 4,131 | 3,726 | 5,408 | 3,726 | 3,698 | 3,691 | +0.94% | 0/4/0/6 |

## Cold session planning

The cold planner compares exactly two complete session plans. The no-bundle plan restricts every message and fragment to JSON or controlled text. The activated plan charges the static profile and frozen codebook exactly once, then permits all warm candidates. The smaller total wins; a tie stays unactivated.

| Dataset | Receiver tokenizer | Bundle tokens | No-bundle total | Activated total | Selected total | Activated? | Selected J/E/V/F |
|---|---|---:|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | 9,570 | 65,953 | 33,993 | 33,993 | yes | 0/0/224/0 |
| development training partition | o200k_base | 9,007 | 65,860 | 33,239 | 33,239 | yes | 0/0/224/0 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 9,719 | 78,606 | 34,001 | 34,001 | yes | 0/0/224/0 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 10,938 | 88,196 | 35,693 | 35,693 | yes | 0/0/224/0 |
| grouped holdout | cl100k_base | 9,570 | 16,416 | 16,100 | 16,100 | yes | 0/0/56/0 |
| grouped holdout | o200k_base | 9,007 | 16,394 | 15,485 | 15,485 | yes | 0/0/56/0 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 9,719 | 19,562 | 16,220 | 16,220 | yes | 0/0/56/0 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 10,938 | 21,922 | 17,574 | 17,574 | yes | 0/0/56/0 |
| out of domain | cl100k_base | 9,570 | 2,761 | 12,331 | 2,761 | no | 0/10/0/0 |
| out of domain | o200k_base | 9,007 | 2,762 | 11,769 | 2,762 | no | 0/10/0/0 |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 9,719 | 3,220 | 12,911 | 3,220 | no | 0/10/0/0 |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 10,938 | 3,726 | 14,629 | 3,726 | no | 0/10/0/0 |

## Bytes and unfavorable transport cases

The selector optimizes receiver tokens, not UTF-8 bytes. The table retains aggregate bytes and counts messages where adaptive used more bytes than the smallest required envelope.

| Dataset | Receiver tokenizer | JSON bytes | Controlled bytes | Structured bytes | Adaptive bytes | Messages above byte-minimum | Worst byte regression |
|---|---|---:|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | 215,723 | 180,513 | 58,802 | 58,802 | 0 | +0.00% |
| development training partition | o200k_base | 215,723 | 180,513 | 58,802 | 58,802 | 0 | +0.00% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 215,723 | 180,513 | 58,802 | 58,802 | 0 | +0.00% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 215,723 | 180,513 | 58,802 | 58,802 | 0 | +0.00% |
| grouped holdout | cl100k_base | 53,444 | 44,720 | 15,592 | 15,592 | 0 | +0.00% |
| grouped holdout | o200k_base | 53,444 | 44,720 | 15,592 | 15,592 | 0 | +0.00% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 53,444 | 44,720 | 15,592 | 15,592 | 0 | +0.00% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 53,444 | 44,720 | 15,592 | 15,592 | 0 | +0.00% |
| out of domain | cl100k_base | 10,006 | 8,552 | 11,505 | 8,552 | 0 | +0.00% |
| out of domain | o200k_base | 10,006 | 8,552 | 11,505 | 8,552 | 0 | +0.00% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 10,006 | 8,552 | 11,505 | 8,728 | 6 | +5.52% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 10,006 | 8,552 | 11,505 | 8,728 | 6 | +5.52% |

## Fragment experiment

The fragment envelope is safely lossless for the frozen JSON-compatible corpus. It uses the fixed 13-field canonical order. Every record contains a mode, canonical character length, and payload. A field can use canonical JSON value text, the controlled value grammar, or optimal codebook symbols carrying canonical JSON value bytes. The outer checksum covers every record, and decoding performs shared semantic validation.

Fragment modes are chosen by exact token count for each complete record. Because tokenizer merges can cross record boundaries, this local choice is not claimed to be the globally optimal fragment combination. The final complete fragment envelope is nevertheless counted exactly and can never make adaptive selection worse: it wins only when its complete count beats the whole-message candidates.

| Dataset | Receiver tokenizer | Fragment wins | Tokens saved by winning fragments | Structured fragment records | Total fragment records |
|---|---|---:|---:|---:|---:|
| development training partition | cl100k_base | 0 | 0 | 35 | 2,912 |
| development training partition | o200k_base | 0 | 0 | 31 | 2,912 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 0 | 0 | 1,094 | 2,912 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 0 | 0 | 1,110 | 2,912 |
| grouped holdout | cl100k_base | 0 | 0 | 7 | 728 |
| grouped holdout | o200k_base | 0 | 0 | 8 | 728 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 0 | 0 | 272 | 728 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 0 | 0 | 278 | 728 |
| out of domain | cl100k_base | 0 | 0 | 0 | 130 |
| out of domain | o200k_base | 0 | 0 | 0 | 130 |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 6 | 28 | 46 | 130 |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 6 | 35 | 46 | 130 |

## Reference implementation latency

Times are per message on this machine. Direct rows encode only one known representation. Adaptive rows build all representations, construct fragment candidates, run the receiver tokenizer repeatedly, and choose the minimum; their overhead is intentionally visible. Paths do unequal work and are not protocol limits.

| Path | Encode/select median | Encode/select p95 | Decode median | Decode p95 |
|---|---:|---:|---:|---:|
| direct minified JSON envelope | 17.2 µs | 54.8 µs | 90.8 µs | 152.0 µs |
| direct Controlled Terse English envelope | 113.5 µs | 416.6 µs | 441.3 µs | 863.5 µs |
| direct v0.4 structured envelope | 1111.6 µs | 1309.0 µs | 2305.2 µs | 3916.5 µs |
| adaptive for cl100k_base | 4781.9 µs | 8866.8 µs | 2443.1 µs | 3406.1 µs |
| adaptive for o200k_base | 4934.7 µs | 7499.7 µs | 2490.5 µs | 3884.6 µs |
| adaptive for Qwen2.5-7B-Instruct tokenizer | 8805.2 µs | 18147.6 µs | 2565.3 µs | 4004.0 µs |
| adaptive for Mistral-7B-Instruct-v0.3 tokenizer | 4917.1 µs | 7022.1 µs | 2105.8 µs | 2542.4 µs |

## Integrity, resource, and scope checks

- Exact semantic recovery: 1,160/1,160.
- Deterministic receiver-specific reselection: 1,160/1,160.
- Deterministic payload-corruption rejection: 1,160/1,160.
- Cold profile plus codebook transfer: 13,799 UTF-8 bytes before tokenizer-specific counting.
- The adaptive decoder limits total UTF-8 bytes, validates the fixed header, verifies the checksum before parsing, bounds structured expansion, rejects non-canonical values and lengths, and applies shared semantic validation.
- The checksum is accidental-error detection only. It does not authenticate a sender, grant authority, or make untrusted content executable.

## Frozen inputs and reproducibility

- Format: `urusilla-adaptive-surface-v0.5-experimental`
- Development partition: 224 messages; SHA-256 `f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759`
- Grouped holdout: 56 messages; SHA-256 `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`
- Out of domain: 10 messages; SHA-256 `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`
- Frozen codebook SHA-256: `d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695`
- Complete adaptive snapshot SHA-256: `b13d454bddeb416035b07fc1fb0130c3d158591bd3dd96028ffa39b08a4a2028`
- Tokenizer packages: `tiktoken==0.11.0`, `tokenizers==0.21.4`

- `cl100k_base`: cl100k_base; tiktoken 0.11.0; vocabulary 100,277; fingerprint `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d`
- `o200k_base`: o200k_base; tiktoken 0.11.0; vocabulary 200,019; fingerprint `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc`
- `qwen2_5_7b_instruct`: Qwen2.5-7B-Instruct tokenizer; tokenizers 0.21.4; vocabulary 151,665; fingerprint `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`
- `mistral_7b_instruct_v03`: Mistral-7B-Instruct-v0.3 tokenizer; tokenizers 0.21.4; vocabulary 32,768; fingerprint `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49`

Selected adaptive text-sequence SHA-256 values:

- development training partition, `cl100k_base`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- development training partition, `o200k_base`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- development training partition, `qwen2_5_7b_instruct`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- development training partition, `mistral_7b_instruct_v03`: `a2fa4687d35968066c3cb5ca6199299a33e9ec2ef350a32f0f17ca2bfcd34b97`
- grouped holdout, `cl100k_base`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- grouped holdout, `o200k_base`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- grouped holdout, `qwen2_5_7b_instruct`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- grouped holdout, `mistral_7b_instruct_v03`: `464cb7be09b623294cdcb8515ae7073494b9a15e874600562bf7a053e5c1119c`
- out of domain, `cl100k_base`: `8c015fd0cbef6277f5f98c04364ff8d5cd48b302527f38858dc979e9965812b6`
- out of domain, `o200k_base`: `8c015fd0cbef6277f5f98c04364ff8d5cd48b302527f38858dc979e9965812b6`
- out of domain, `qwen2_5_7b_instruct`: `dd96b2bd27da15871546c22cf45fa3e84d0b14761fe4907b4d4e067886ad7130`
- out of domain, `mistral_7b_instruct_v03`: `dd96b2bd27da15871546c22cf45fa3e84d0b14761fe4907b4d4e067886ad7130`

Source SHA-256 values:

- selector and benchmark: `d8d46919f180fbe7585f921154113a9a002d42da6100e943fdd568a18fe88c87`
- conformance tests: `165afa0bebd5ef86041e1e1157ca9c4d091b682527d839fb5511cb8475280840`

Environment:

- Python: `3.12.14`
- Platform: `macOS-15.0-arm64-arm-64bit`

Reproduce from the repository root:

```bash
PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_adaptive_surface_v05.py --benchmark --assets-dir work/tokenizer_assets
PYTHONPATH=. work/tokenizer_venv/bin/python -m unittest test_urusilla_adaptive_surface_v05.py -v
```

## Limitations

- Selection assumes the receiver tokenizer is correctly negotiated and locally reproducible. Hosted billing, chat templates, BOS/EOS, surrounding prompts, and transport framing can change the real cost.
- Development is in-sample. Grouped holdout shares a synthetic generator family. The out-of-domain set contains only ten repository-authored messages.
- The cold planner is an offline session optimum with full knowledge of the measured message sequence. A streaming agent needs an explicit horizon or conservative activation policy and may perform worse.
- Fragment records are exact, but local per-record token minimization is not a proof of globally minimum fragment tokenization. A globally exact fragment search remains future work.
- Checksums add material token and byte overhead. Authentication, signatures, encryption, replay defense, and negotiation failure are outside this experiment.
- Exact serialization recovery does not show that an LLM can understand or produce any candidate. Task success and repair behavior remain unmeasured.
- Token savings do not directly imply lower energy, latency, memory, hosted cost, or total application tokens. Adaptive selection itself adds substantial CPU work.
