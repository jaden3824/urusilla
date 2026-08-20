# Urusilla Frozen Broad-Dialogue Evaluation

> **Result boundary:** This is an offline lossless carrier measurement over a frozen four-family convenience sample and a separate SGD gold-state oracle prompt-size upper bound. It is not an end-to-end model, task-success, total-task-token, energy, deployment, adoption, or state-of-the-art result.

## Postmeasurement reproducibility amendment

After the first measurement, reproducibility review changed only how already-fixed tokenizer vocabularies and zlib are loaded: cl100k and o200k now require explicit local hash-pinned `.tiktoken` files, and both zlib compile and runtime versions must equal 1.2.12. The measurement path contains no tokenizer download or cache fallback.

Candidate algorithms, ordering, hypotheses, gates, and previously reported non-latency outcome numbers did not change. The amended contract is larger, but all cold plans still reject activation and retain zero saving. Previously recorded latency samples are retained rather than presented as a deterministic refreeze product.

The source and method chronology is a project-internal freeze, not an externally registered or independently witnessed preregistration. The project authors could access the corpus while implementing the evaluator. The narrow auditable statement is that no evaluated-corpus-derived dictionary or learned profile is used; this study does not claim to exclude every possible tuning influence.

## Bottom line

- H1 lossless no-regret: **PASS**.
- H2 general compact value: **FAIL**.
- H3 repeated-context value: **FAIL**.
- H4 end-to-end gate: **NOT EVALUATED**; there were zero model or provider calls.
- Every selected compact carrier is deterministically decoded before a model call. Therefore measured post-decode API-input token saving is **0.00%** under all four tokenizers.

Receiver-carrier token savings below describe the complete text presented to the deterministic receiver codec. They are serialization opportunities, not evidence that an unmodified model understands compressed Base64url text. The bare UTF-8 text is always the receiver-token baseline and fallback.

## Frozen inputs and order of operations

The evaluator verified all frozen files, flags, family counts, turn counts, hypotheses, and sequence digests before loading tokenizer or compressor packages.

- Evaluation contract: `1cf2d1c9810ac5b94bc0adf15d2251bae30b1b1d8b36fa161a51e1bbe0f5b1c1` (10,995 bytes).
- Source freeze: `888bbdd680a22faa2e30e457d5559ad4042184ec2e0e5b7f7b7832ef6ebd2921`.
- Corpus manifest: `6fba633e286527303afd180b0221362365a20efd9325686631df022fc6cf9fec`.
- Corpus JSONL: `3bede9398786dcb7de72a5bf2648105c62ba3b0f9339d7c86b774f937b104854`.
- Corpus sequence: `349e57a679815aa343815117ac8ed0e753f516871152c46a38fa31484fcd82bd`.
- Corpus size: 256 records and 2,542 turns.
- Evaluator source: `5131497df97788f7caba5b716885184e0677f383341ec3547fad4513235def3c`.

Repository flags record that the sources were frozen before project codec or tokenizer import and before the first measurement. This is internal chronology rather than external preregistration. The evaluator is project-authored, was not independently blinded, and no candidate uses an evaluated-corpus-derived dictionary or learned profile.

## Predeclared hypotheses

| Hypothesis | Result | Gate |
|---|---:|---|
| h1_lossless_no_regret | pass | 0 positive-regret pairs across 10168 turn-tokenizer choices; all selected carriers recovered exact UTF-8. |
| h2_general_compact_value | fail | Requires at least 10% compact coverage and at least 5% warm carrier-token saving in every family under every tokenizer. |
| h3_repeated_context_value | fail | Requires at least 20% warm carrier-token saving from the raw-or-causal-history chooser in both task families under every tokenizer. |
| h4_end_to_end_gate | not_evaluated | No provider calls, model task-success trial, or total-task-token measurement was run. |

## Lossless carrier results

| Tokenizer | Raw tokens | Warm selected | Warm saving | Compact coverage | Cold total | Cold saving | Cold families active | Post-decode API saving |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 59,518 | 59,082 | 0.73% | 0.35% | 59,518 | 0.00% | 0/4 | 0.00% |
| o200k_base | 53,646 | 53,219 | 0.80% | 0.35% | 53,646 | 0.00% | 0/4 | 0.00% |
| qwen2_5_7b_instruct | 56,857 | 56,490 | 0.65% | 0.28% | 56,857 | 0.00% | 0/4 | 0.00% |
| mistral_7b_instruct_v03 | 64,817 | 64,390 | 0.66% | 0.35% | 64,817 | 0.00% | 0/4 | 0.00% |

Cold accounting charges the complete contract once for each independently cold family session. It assumes the named compressor implementations are already installed; executable installation cost is excluded and no no-install deployment claim is made.

### Integrity-matched raw control and selected modes

| Tokenizer | Bare raw tokens | Checked raw tokens | Checked token overhead | Bare raw bytes | Checked raw bytes | Checked byte overhead |
|---|---:|---:|---:|---:|---:|---:|
| cl100k_base | 59,518 | 264,908 | 345.09% | 236,995 | 390,561 | 64.80% |
| o200k_base | 53,646 | 249,065 | 364.28% | 236,995 | 390,561 | 64.80% |
| qwen2_5_7b_instruct | 56,857 | 295,475 | 419.68% | 236,995 | 390,561 | 64.80% |
| mistral_7b_instruct_v03 | 64,817 | 315,823 | 387.25% | 236,995 | 390,561 | 64.80% |

Every generic compressor uses the same length, digest, and Base64url envelope as `raw_checked`. Bare raw remains the receiver-token fallback; `raw_checked` isolates envelope overhead for compression comparisons and does not count as a compact choice.

| Tokenizer | raw | raw_checked | deflate64 | brotli64 | zstd64 | history_deflate64 |
|---|---:|---:|---:|---:|---:|---:|
| cl100k_base | 2,533 | 0 | 0 | 0 | 0 | 9 |
| o200k_base | 2,533 | 0 | 0 | 0 | 0 | 9 |
| qwen2_5_7b_instruct | 2,535 | 0 | 0 | 0 | 0 | 7 |
| mistral_7b_instruct_v03 | 2,533 | 0 | 0 | 0 | 0 | 9 |

### Per-family outcomes

| Tokenizer | Family | Turns | Raw | Warm | Token saving | Byte saving | Compact | Cold active | Cold saving | History-only saving | H2 | H3 if task |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | taskmaster_1 | 1,417 | 15,987 | 15,987 | 0.00% | 0.00% | 0 (0.00%) | false | 0.00% | 0.00% | false | false |
| cl100k_base | schema_guided_dialogue | 798 | 11,346 | 11,339 | 0.06% | 0.24% | 1 (0.13%) | false | 0.00% | 0.06% | false | false |
| cl100k_base | databricks_dolly_15k | 128 | 10,270 | 9,921 | 3.40% | 4.81% | 6 (4.69%) | false | 0.00% | 3.40% | false | n/a |
| cl100k_base | openassistant_oasst1 | 199 | 21,915 | 21,835 | 0.37% | 0.86% | 2 (1.01%) | false | 0.00% | 0.37% | false | n/a |
| o200k_base | taskmaster_1 | 1,417 | 15,669 | 15,669 | 0.00% | 0.00% | 0 (0.00%) | false | 0.00% | 0.00% | false | false |
| o200k_base | schema_guided_dialogue | 798 | 11,125 | 11,118 | 0.06% | 0.24% | 1 (0.13%) | false | 0.00% | 0.06% | false | false |
| o200k_base | databricks_dolly_15k | 128 | 10,134 | 9,785 | 3.44% | 4.81% | 6 (4.69%) | false | 0.00% | 3.44% | false | n/a |
| o200k_base | openassistant_oasst1 | 199 | 16,718 | 16,647 | 0.42% | 0.86% | 2 (1.01%) | false | 0.00% | 0.42% | false | n/a |
| qwen2_5_7b_instruct | taskmaster_1 | 1,417 | 16,399 | 16,399 | 0.00% | 0.00% | 0 (0.00%) | false | 0.00% | 0.00% | false | false |
| qwen2_5_7b_instruct | schema_guided_dialogue | 798 | 11,716 | 11,713 | 0.03% | 0.24% | 1 (0.13%) | false | 0.00% | 0.03% | false | false |
| qwen2_5_7b_instruct | databricks_dolly_15k | 128 | 10,515 | 10,198 | 3.01% | 4.26% | 4 (3.12%) | false | 0.00% | 3.01% | false | n/a |
| qwen2_5_7b_instruct | openassistant_oasst1 | 199 | 18,227 | 18,180 | 0.26% | 0.86% | 2 (1.01%) | false | 0.00% | 0.26% | false | n/a |
| mistral_7b_instruct_v03 | taskmaster_1 | 1,417 | 17,669 | 17,669 | 0.00% | 0.00% | 0 (0.00%) | false | 0.00% | 0.00% | false | false |
| mistral_7b_instruct_v03 | schema_guided_dialogue | 798 | 12,291 | 12,290 | 0.01% | 0.24% | 1 (0.13%) | false | 0.00% | 0.01% | false | false |
| mistral_7b_instruct_v03 | databricks_dolly_15k | 128 | 11,624 | 11,250 | 3.22% | 4.81% | 6 (4.69%) | false | 0.00% | 3.22% | false | n/a |
| mistral_7b_instruct_v03 | openassistant_oasst1 | 199 | 23,233 | 23,181 | 0.22% | 0.86% | 2 (1.01%) | false | 0.00% | 0.22% | false | n/a |

### Exactness, modes, bytes, and integrity-matched control

- Candidate exact round trips: 14,996/14,996.
- Candidate deterministic re-encodes: 14,996/14,996.
- Selected turn-tokenizer exact round trips: 10,168/10,168.
- Positive-regret selected pairs: 0.
- External-profile exact round trips: 2,542/2,542.

The `raw_checked` mode carries uncompressed UTF-8 through the identical length, digest, and Base64url envelope used by generic compressors. It is reported in every per-family JSON result so compression is not credited for envelope overhead. Bare raw remains a separate receiver-token baseline because an authenticated transport can carry it without this application envelope.

Mode counts and complete per-mode byte/token totals are preserved in `urusilla_general_dialogue_results.json`. Network-byte reductions do not imply model-token reductions, and every compact carrier is decoded back to the original text before any hypothetical model input.

## Minimal Urusilla external-profile control

This separate canonical JSON carrier preserves exactly `profile`, `role`, `session`, `turn`, and `text`. It is an experimental external carrier profile, not core UrusillaIR, not a model-native surface, and not eligible for H1-H3 savings.

| Tokenizer | Raw tokens | External-profile tokens | Token overhead | Raw bytes | External-profile bytes | Byte overhead |
|---|---:|---:|---:|---:|---:|---:|
| cl100k_base | 59,518 | 158,080 | 165.60% | 236,995 | 567,899 | 139.62% |
| o200k_base | 53,646 | 152,228 | 183.76% | 236,995 | 567,899 | 139.62% |
| qwen2_5_7b_instruct | 56,857 | 161,462 | 183.98% | 236,995 | 567,899 | 139.62% |
| mistral_7b_instruct_v03 | 64,817 | 181,900 | 180.64% | 236,995 | 567,899 | 139.62% |

## SGD gold action/state oracle upper bound

The frozen SGD subset produced 399 next-assistant-action prompt pairs. No model was called and no accuracy was measured. The comparison replaces exact raw dialogue history with the immediately preceding user turn's dataset-provided gold service, action, and cumulative state JSON. It intentionally loses prose and therefore cannot enter the lossless result.

| Tokenizer | Raw-history prompt | Gold-state oracle prompt | Token difference |
|---|---:|---:|---:|
| cl100k_base | 53,585 | 41,370 | 22.80% |
| o200k_base | 53,009 | 43,328 | 18.26% |
| qwen2_5_7b_instruct | 54,817 | 42,025 | 23.34% |
| mistral_7b_instruct_v03 | 62,093 | 57,447 | 7.48% |

Byte difference: 16.32%. Prompt-pair digest: `ecf3df17b6b9967b1982713aa61ba70b1da0daf55f3dc2d709fb8352438d690c`.

This is only an opportunity upper bound. A deployment would have to infer state without gold annotations, preserve safety-relevant details, obtain tool results, generate correct actions, include output and repair tokens, and pass the separately frozen H4 task-success gate.

## Latency

| Mode | Encode p50 / p95 (microseconds) | Decode p50 / p95 (microseconds) |
|---|---:|---:|
| raw | 0.208 / 0.417 | 0.208 / 0.292 |
| raw_checked | 2.000 / 5.000 | 3.292 / 8.250 |
| deflate64 | 9.709 / 32.250 | 5.209 / 14.125 |
| brotli64 | 282.000 / 674.125 | 6.917 / 18.625 |
| zstd64 | 14.917 / 65.375 | 6.166 / 21.792 |
| history_deflate64 | 15.500 / 36.125 | 5.375 / 13.792 |

Latency is machine-specific wall-clock evidence and the paths perform unequal work. It supports no universal speed claim.

## Sources, licenses, and acquisition

Raw mixed-license records remain under the ignored `work/general_dialogue/` directory and are not included in public result artifacts. Reacquire each exact revision and verify the listed size and SHA-256 before rebuilding the corpus:

| Source key | License | Revision | Bytes | SHA-256 | Acquisition URL |
|---|---|---|---:|---|---|
| taskmaster_1_self_dialogues | [CC-BY-4.0](https://raw.githubusercontent.com/google-research-datasets/Taskmaster/d92cb6af3005f1dc09c39e75e7daf4a04905e00b/TM-1-2019/README.md) | `d92cb6af3005f1dc09c39e75e7daf4a04905e00b` | 65,748,638 | `1e590ed0ccee279e40c2fb9e083d3b9417477c6bfe35ce5b2277167698dd858d` | [immutable source](https://raw.githubusercontent.com/google-research-datasets/Taskmaster/d92cb6af3005f1dc09c39e75e7daf4a04905e00b/TM-1-2019/self-dialogs.json) |
| schema_guided_dialogue_dev_001 | [CC-BY-SA-4.0](https://raw.githubusercontent.com/google-research-datasets/dstc8-schema-guided-dialogue/e852981ae34990f4358979625854259302feaa78/LICENSE.txt) | `e852981ae34990f4358979625854259302feaa78` | 2,225,937 | `fe3a8ed9e160c15e20e7cfd16d03734b4473df0d3864f2ad687ea9eeee5eea52` | [immutable source](https://raw.githubusercontent.com/google-research-datasets/dstc8-schema-guided-dialogue/e852981ae34990f4358979625854259302feaa78/dev/dialogues_001.json) |
| databricks_dolly_15k | [CC-BY-SA-3.0](https://huggingface.co/datasets/databricks/databricks-dolly-15k/raw/bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a/README.md) | `bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a` | 13,085,339 | `2df9083338b4abd6bceb5635764dab5d833b393b55759dffb0959b6fcbf794ec` | [immutable source](https://huggingface.co/datasets/databricks/databricks-dolly-15k/resolve/bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a/databricks-dolly-15k.jsonl?download=true) |
| openassistant_oasst1_ready_trees | [Apache-2.0](https://huggingface.co/datasets/OpenAssistant/oasst1/raw/fdf72ae0827c1cda404aff25b6603abec9e3399b/README.md) | `fdf72ae0827c1cda404aff25b6603abec9e3399b` | 34,145,252 | `2a9a8fd343e9b28e04a895a669d3253f82d93e9c174d440199ae19d5fafbdff7` | [immutable source](https://huggingface.co/datasets/OpenAssistant/oasst1/resolve/fdf72ae0827c1cda404aff25b6603abec9e3399b/2023-04-12_oasst_ready.trees.jsonl.gz?download=true) |

No source utterance is reproduced in this report. Aggregate public artifacts contain only digests, counts, measurements, and acquisition metadata.

### Separate tokenizer acquisition step

Tokenizer assets must be acquired before measurement and stored at the exact ignored paths below. Acquisition is not part of the evaluator; a missing file, byte-size mismatch, or digest mismatch fails closed. In particular, the evaluator never calls `tiktoken.get_encoding`, never reads the global tiktoken cache, and never downloads a vocabulary.

| Tokenizer | Ignored local path | Bytes | SHA-256 | Acquisition URL |
|---|---|---:|---|---|
| cl100k_base | `work/tokenizer_assets/cl100k_base/cl100k_base.tiktoken` | 1,681,126 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` | [download separately](https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken) |
| mistral_7b_instruct_v03 | `work/tokenizer_assets/mistral_7b_instruct_v03/tokenizer.json` | 1,961,548 | `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49` | [download separately](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3/resolve/c170c708c41dac9275d15a8fff4eca08d52bab71/tokenizer.json?download=true) |
| o200k_base | `work/tokenizer_assets/o200k_base/o200k_base.tiktoken` | 3,613,922 | `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d` | [download separately](https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken) |
| qwen2_5_7b_instruct | `work/tokenizer_assets/qwen2_5_7b_instruct/tokenizer.json` | 7,031,645 | `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539` | [download separately](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/resolve/a09a35458c702b33eeacc393d103063234e8bc28/tokenizer.json?download=true) |

Download these files in an explicit preparation step, verify SHA-256 and byte size, then disconnect or deny network access before invoking the evaluator.

## Reproduction

```bash
.venv-research-py312/bin/python -m unittest -v test_urusilla_general_dialogue_eval.py
.venv-research-py312/bin/python urusilla_general_dialogue_eval.py --write
```

The run requires the ignored frozen corpus and all four tokenizer assets plus the exact dependency versions in `requirements-research.lock`. It fails unless zlib compile and runtime versions are both 1.2.12. The measurement performs no network or provider call.
