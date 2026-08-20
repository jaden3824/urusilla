# Checkpointed semantic delta v0.9 development experiment

Status: bounded offline serialization evidence over a synthetic, scenario-shaped correlated workload; not external generalization, model comprehension, task utility, adoption, energy, or state of the art  
Date: 2026-08-20  
Format: `urusilla-session-delta-v0.9-experimental`

## Outcome

Across 24 sessions and 768 state snapshots, the matched full-state baseline and the checkpointed semantic-delta candidate used the same standalone session, sequence, base-state, and HMAC framing. The selector admitted a delta only when its **complete record** used strictly fewer tokens than the full fallback for the negotiated receiver tokenizer.

At the predeclared representative checkpoint interval of 8, aggregate token savings versus the matched full-record baseline were **53.71% to 55.15%** across the four pinned tokenizers. These favorable numbers are expected to depend strongly on correlation: the workload deliberately models evolving shared state, and it was authored in this repository. They are not evidence that arbitrary agent messages compress by this amount.

The interval-1 control is full-only and therefore saves exactly zero. Every interval retains the unfavorable cost of full cold bootstrap and periodic checkpoints. The result is a serialization bound: no language model read or produced a delta, and no safely completed task was measured.

## Frozen workload and protocol

- Workflows: incident triage, inventory reservation, document review, and route planning.
- Sessions: 24 (6 deterministic variants per workflow).
- State snapshots: 768 (32 per session).
- Workload SHA-256: `729a602163a6e7698ea6aa9d9859dba17decfbed998afba219ec88b51aaeb419`.
- Checkpoint intervals: `1, 2, 4, 8, 16, 32` records; the final record is also forced full.
- Deterministic matrix SHA-256: `2647d3c4c3a1c399352d49f7c79d5456986ee7176c0e9f131b5a14760e6131d2`.
- Standalone header: 88 ASCII characters per record before payload.
- Integrity: HMAC-SHA-256 truncated to 128 bits over mode, 128-bit session UUID, 32-bit sequence, 128-bit base-state digest, and exact UTF-8 payload bytes.
- Delta: canonical sorted set/delete operations over object paths; changed arrays are replaced as complete values.
- Selection: forced checkpoints use full state; otherwise choose delta only on a strict complete-token win, with full state winning ties.
- Cold contract: decoder software and the record contract are installed, but session state is absent. The first full checkpoint, all headers, periodic checkpoints, and the final checkpoint are charged. Software installation, key exchange, transport packets, and prompt-teaching the grammar are outside this experiment.

## Complete standalone receiver-token accounting

`Full / fallback / delta` reports forced checkpoints, non-forced full fallbacks, and strict delta wins. Cold checkpoint tokens are the sum of the first full record of every session and are already included in selected total.

| Receiver tokenizer | Interval | Matched full tokens | Selected tokens | Saving | Full / fallback / delta | Cold checkpoint tokens (share) |
|---|---:|---:|---:|---:|---:|---:|
| cl100k_base | 1 | 612,158 | 612,158 | 0.00% | 768/0/0 | 11,552 (1.89%) |
| cl100k_base | 2 | 612,158 | 429,829 | 29.78% | 408/0/360 | 11,552 (2.69%) |
| cl100k_base | 4 | 612,158 | 327,935 | 46.43% | 216/0/552 | 11,552 (3.52%) |
| cl100k_base | 8 | 612,158 | 283,016 | 53.77% | 120/0/648 | 11,552 (4.08%) |
| cl100k_base | 16 | 612,158 | 261,294 | 57.32% | 72/0/696 | 11,552 (4.42%) |
| cl100k_base | 32 | 612,158 | 250,612 | 59.06% | 48/0/720 | 11,552 (4.61%) |
| o200k_base | 1 | 620,597 | 620,597 | 0.00% | 768/0/0 | 11,777 (1.90%) |
| o200k_base | 2 | 620,597 | 435,888 | 29.76% | 408/0/360 | 11,777 (2.70%) |
| o200k_base | 4 | 620,597 | 332,743 | 46.38% | 216/0/552 | 11,777 (3.54%) |
| o200k_base | 8 | 620,597 | 287,272 | 53.71% | 120/0/648 | 11,777 (4.10%) |
| o200k_base | 16 | 620,597 | 265,285 | 57.25% | 72/0/696 | 11,777 (4.44%) |
| o200k_base | 32 | 620,597 | 254,494 | 58.99% | 48/0/720 | 11,777 (4.63%) |
| Qwen2.5-7B-Instruct tokenizer | 1 | 765,012 | 765,012 | 0.00% | 768/0/0 | 13,870 (1.81%) |
| Qwen2.5-7B-Instruct tokenizer | 2 | 765,012 | 534,436 | 30.14% | 408/0/360 | 13,870 (2.60%) |
| Qwen2.5-7B-Instruct tokenizer | 4 | 765,012 | 405,486 | 47.00% | 216/0/552 | 13,870 (3.42%) |
| Qwen2.5-7B-Instruct tokenizer | 8 | 765,012 | 348,422 | 54.46% | 120/0/648 | 13,870 (3.98%) |
| Qwen2.5-7B-Instruct tokenizer | 16 | 765,012 | 320,664 | 58.08% | 72/0/696 | 13,870 (4.33%) |
| Qwen2.5-7B-Instruct tokenizer | 32 | 765,012 | 307,003 | 59.87% | 48/0/720 | 13,870 (4.52%) |
| Mistral-7B-Instruct-v0.3 tokenizer | 1 | 895,020 | 895,020 | 0.00% | 768/0/0 | 16,683 (1.86%) |
| Mistral-7B-Instruct-v0.3 tokenizer | 2 | 895,020 | 621,911 | 30.51% | 408/0/360 | 16,683 (2.68%) |
| Mistral-7B-Instruct-v0.3 tokenizer | 4 | 895,020 | 469,438 | 47.55% | 216/0/552 | 16,683 (3.55%) |
| Mistral-7B-Instruct-v0.3 tokenizer | 8 | 895,020 | 401,448 | 55.15% | 120/0/648 | 16,683 (4.16%) |
| Mistral-7B-Instruct-v0.3 tokenizer | 16 | 895,020 | 368,421 | 58.84% | 72/0/696 | 16,683 (4.53%) |
| Mistral-7B-Instruct-v0.3 tokenizer | 32 | 895,020 | 352,194 | 60.65% | 48/0/720 | 16,683 (4.74%) |

The selector has a mechanical no-regression guarantee against the matched full record for every non-forced message. That guarantee is conditional on exact receiver-tokenizer negotiation and does not include any model response or repair turn.

## Representative interval-8 framing sensitivity

Raw JSON omits session framing and authentication and is not a matched protocol baseline. It is retained to show the material cost of the standalone envelope rather than hiding it.

| Receiver tokenizer | Raw full-state JSON | Matched full records | Envelope excess | Interval-8 selected | Saving vs matched full |
|---|---:|---:|---:|---:|---:|
| cl100k_base | 577,551 | 612,158 | +5.99% | 283,016 | 53.77% |
| o200k_base | 586,586 | 620,597 | +5.80% | 287,272 | 53.71% |
| Qwen2.5-7B-Instruct tokenizer | 718,328 | 765,012 | +6.50% | 348,422 | 54.46% |
| Mistral-7B-Instruct-v0.3 tokenizer | 846,814 | 895,020 | +5.69% | 401,448 | 55.15% |

## Byte-only selector sensitivity

This separate selector minimizes complete UTF-8 bytes instead of receiver tokens. It uses the identical checkpoint and integrity contract. It is not the byte count of any one tokenizer-specific plan.

| Interval | Matched full bytes | Selected bytes | Saving | Full / fallback / delta |
|---:|---:|---:|---:|---:|
| 1 | 1,940,047 | 1,940,047 | 0.00% | 768/0/0 |
| 2 | 1,940,047 | 1,331,631 | 31.36% | 408/0/360 |
| 4 | 1,940,047 | 993,999 | 48.76% | 216/0/552 |
| 8 | 1,940,047 | 841,849 | 56.61% | 120/0/648 |
| 16 | 1,940,047 | 768,265 | 60.40% | 72/0/696 |
| 32 | 1,940,047 | 732,469 | 62.24% | 48/0/720 |

## Exactness, determinism, and state-fault behavior

- Tokenizer-specific plan recovery: `18,432/18,432` exact snapshots.
- Tokenizer-specific canonical reselection: `18,432/18,432` byte-identical records.
- Byte-specific plan recovery and determinism: `4,608/4,608` and `4,608/4,608`.
- Representative interval-8 mutation campaign: `4,608/4,608` changes to mode, session, sequence, base digest, tag, or payload rejected before state acceptance.
- Fresh-decoder delta rejection: `648/648`; independently decodable full checkpoints: `120`.
- Replay rejection: `768/768`.
- Adjacent out-of-order rejection: `744/744`; ordered replay after rejection still recovered the exact state.
- One-record loss trials: `744/744` immediate post-gap records rejected and `744/744` later full checkpoints resynchronized the current state. The maximum number of unavailable intervening snapshots was `7` at interval 8.

Checkpoint resynchronization recovers current state, not missing historical snapshots. An application requiring every missed intermediate state must retransmit or replay them; that traffic is not silently counted as recovered.

## Current Python path latency

Values are whole 32-snapshot sessions over 24 scenario sessions on `CPython 3.12.14` / `macOS-15.0-arm64-arm-64bit`. Full encode counts authenticated full records. Adaptive encode constructs full and delta candidates and performs tokenizer counting; paths do unequal work. The descriptive p95 is a nearest-rank sample statistic, not a confidence bound.

| Path | p50 | p95 |
|---|---:|---:|
| Matched full encode + cl100k count | 35,511.4 us | 61,752.3 us |
| Interval-8 adaptive encode/select + cl100k count | 163,396.9 us | 300,029.5 us |
| Interval-8 authenticated decode | 60,266.7 us | 80,719.3 us |

## Interpretation boundary

- The workload is synthetic and deliberately correlated. It repeats stable objectives, constraints, participants, and growing evidence/decision indexes while changing progress and current events. This makes it suitable for testing the stated state-sync hypothesis and unsuitable for estimating traffic-wide savings.
- The baseline is full canonical state under the same record contract. This is not a claim against compressed streams, general-purpose binary codecs, KV-cache methods, latent communication, or published multi-agent systems.
- Exact reconstruction proves codec behavior, not that a model understands the compact text. If a deterministic adapter expands every delta before model input, network text is reduced but receiver model-input tokens are not. If the model consumes deltas directly, task success and repair cost remain unmeasured.
- A receiver must retain the exact preceding state and its digest. Memory, cache invalidation, multi-device synchronization, key rotation, and concurrent branch merging are not measured.
- Loss and reordering fail closed. Checkpoints bound current-state resynchronization but do not restore omitted history; retransmission, packet headers, congestion control, TLS, and denial-of-service resistance are outside scope.
- The public deterministic HMAC key is a test fixture. Deployment requires an authenticated key-establishment protocol and authorization policy.
- Token counts exclude chat templates, BOS/EOS, prompts, model output, tool calls, repair turns, and hosted billing transformations. Token reduction does not directly establish lower energy, latency, memory, money, or emissions.
- There is no external holdout, model call, task benchmark, independent reproduction, adoption measurement, or state-of-the-art claim.

## Reproduction identity

- Tokenizer packages are pinned by the repository research environment; exact vocabulary fingerprints are verified at runtime.
- `cl100k_base`: `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d`.
- `o200k_base`: `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc`.
- `Qwen2.5-7B-Instruct tokenizer`: `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`.
- `Mistral-7B-Instruct-v0.3 tokenizer`: `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49`.
- Implementation SHA-256: `ebcc25e27b1a65f09a3821df66ead722044c5a9398384d24246da66863385ea6`.
- Test SHA-256: `2056d6525b35715625147a7c686f550634a8c182125af57e855a8a662876be37`.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python \
  urusilla_session_delta_v09.py --output SESSION_DELTA_V09_RESULTS.md
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m unittest -v \
  test_urusilla_session_delta_v09.py
```
