# Competitive public-task harness: offline dry-run report

Artifact epoch: `2026-08-20`  
Harness version: `0.1.0-offline-dry-run`  
Run ID: `3ab4a31b4cb67c2951579b425de2086164868d2b452f3aaa65a52d2307798644`

## Outcome

The isolated harness completed **108 deterministic mock episodes** spanning both frozen task families, all six representation arms, and all nine ordered sender/receiver pairs. It made **0 provider calls, 0 paid calls, and USD 0 in actual billed cost**. The adapter executed 426 local scripted calls, including any format-only repairs. The checkpoint event-chain digest was `04216056d664f76a174a88039fb85f8a574b9ecbbc3af9a67ed7d8b910debf16`.

This is plumbing and reproducibility evidence only. The mock adapter uses the gold answer, exactly as declared in every observation. It does not measure model comprehension, task performance, competitive efficiency, or generalization. **No performance, near-leading, leading, competitive, or state-of-the-art claim is made.**

## Frozen input verification

- HotpotQA: 100 records, SHA-256 `eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284`.
- WikiHop: 100 records, SHA-256 `724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39`.
- The frozen WikiHop bytes and A0 snapshot contain **1630** context blocks. The root preflight report says **1702**. The harness trusts the byte-frozen source/snapshot and preserves this discrepancy instead of rewriting the data.
- The physical snapshot file digest and the embedded canonical snapshot digest are intentionally distinct; both are recorded in `locks.json`.
- Git revision: unavailable. File digests are used, and an immutable commit remains an A1 blocker.

## Mock matrix and complete ledger

| Arm | Episodes | Safe successes | Base calls | Repairs | Fallbacks | T_total | Cold/profile tokens | Cold bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `paper_natural_language` | 18 | 0 | 137 | 2 | 0 | 92759 | 0 | 0 |
| `compact_terse_english` | 18 | 17 | 35 | 2 | 0 | 23467 | 0 | 0 |
| `canonical_minified_json` | 18 | 17 | 35 | 2 | 0 | 23210 | 0 | 0 |
| `autoform` | 18 | 0 | 137 | 2 | 0 | 93307 | 0 | 0 |
| `current_adaptive_surface` | 18 | 17 | 35 | 2 | 4 | 334651 | 307929 | 464145 |
| `oracle_free_adaptive_selector` | 18 | 17 | 35 | 2 | 0 | 25039 | 0 | 0 |

All malformed outputs, repairs, fallbacks, timeouts, and refusals remain in their originally assigned arm and in the denominator. Each call records the full non-overlapping token categories, judge tokens separately, wire bytes, retransmission, deterministic logical latency, repair/fallback flags, raw provider-usage placeholders, reconciliation status, estimated cost, and actual billed cost.

The paper-natural and AutoForm mock arms intentionally cannot earn `safe_task_success`: their archival-style `ANSWER:` parser does not invent typed provenance or a missing-request state. Their exact upstream YAML bytes are absent from A0, and the common two-agent/eight-call lane is a clean adaptation rather than a literal archival replay.

## Unfavorable adaptive cold accounting retained

The current adaptive arm recorded 307929 cold/profile tokens and 464145 cold bytes in this small matrix, versus 0 and 0 for CTE. Its mock ratio-of-sums token reduction relative to CTE was `-13.260493458900`; a negative value means more charged tokens. The selector recorded 0 cold/profile tokens because its oracle-free cost rule avoided the cold surface when it was not cheaper.

The harness retains the conservative current-artifact current-surface
**16,005-byte charge per endpoint** and does not use a
future-aware cold optimizer. This current lock is bound by the current-artifact
A0 adaptive prompt lock:

| Current frozen counter | Cold tokens | Adaptive initial prompt overhead vs CTE |
|---|---:|---:|
| `cl100k_base` | 10170 | +82 |
| `o200k_base` | 9661 | +85 |
| `qwen2_5_7b_instruct` | 10348 | +99 |
| `mistral_7b_instruct_v03` | 11750 | +102 |

For a stateless `surface_prompt` boundary, any required grammar/profile replay must be charged on every request unless persistent context is independently verified. A `decoded_json_bridge` boundary is transport-only and cannot establish model comprehension.

## Statistics implementation exercised

The analysis artifact runs 10,000 deterministic paired bootstrap resamples using the frozen harness seed, SHA-256 counter rejection sampling, exact rational estimators, inverse-ECDF type-1 quantiles, item-by-ordered-pair clusters, and an item-only sensitivity. Success uses a one-sided 95% lower bound and passes only when it is strictly above `-0.010`. Token reduction is exactly `1 - sum(T_arm) / sum(T_CTE)`, with a two-sided 95% interval and a lower-bound gate at `0.25`. The artifact also records exact two-sided McNemar sensitivities, the receiver-family one-percentage-point point-regression gate, and complete five-hypothesis success and two-hypothesis task-token Holm families.

Those intervals and p-values are deterministic test vectors, not empirical claims. The competitive gate is false: this run has one repeat, gold-using mocks, unavailable paper prompt bytes, proxy hosted tokenizers, no frozen power audit, and no immutable implementation revision.

## Wire-only controls

All 4 controls—deterministic CBOR, sorted-map MessagePack, typed Protobuf, and project v0.2—recovered the exact same canonical receiver record, rejected a deterministic corruption, and added **0 model calls**. They measure transport/conversion facts only and are not separate task samples.

## A1 manifests and stopping gates

- `A1_plan`: 360 episodes for CTE/AutoForm/current surface.
- `A1_a0_cost_variant`: 360 episodes for CTE/JSON/current surface.
- Each preset has a 2,880 base-call cap. The frozen A0 cost forecast applies to the second trio only.
- A same-workload six-arm run would have 720 episodes and 5,760 base calls, so it is not silently substituted into either preset.
- The new conservative absolute A1 stops are 3,456 total calls, 2,304 paid calls, and USD 40. Stop before the next call would cross any limit.
- A1-to-A2 requires complete pairing, exact parsing throughout, and no arm point estimate below CTE by more than 0.030. Equality at `-0.030` passes; anything smaller fails.
- Every later stage requires fresh approval. The exact stage counts and caps are in `stage_and_cost_gates.json`.

## Limitations requiring resolution before A1

1. Select and preregister the A1 trio; the plan and A0 cost snapshot disagree.
2. Install the exact paper/AutoForm source files and resolve their two-agent, max-turn, and missing-request differences.
3. Pin exact pre-call endpoint tokenizers. Qwen is exact in A0; the hosted O and G mappings are planning proxies.
4. Create an immutable Git revision and freeze the new statistical conventions before outcomes.
5. Complete the paired-discordance power audit or use a separately approved A5 extension without relaxing the margin.
6. Obtain the credentials, public-data transmission approval, retention approval, and explicit paid-call authority listed in `A1_READINESS_CHECKLIST.md`.

## Reproduction artifacts

- `mock_episode_manifest.jsonl`: 108 provider-neutral episode manifests.
- `mock_episode_results.jsonl`: complete deterministic result and ledger objects.
- `mock_turn_observations.jsonl`: every provider-neutral mock request/response pair, including repairs.
- `mock_prompt_locks.jsonl`: complete rendered mock prompts with byte counts and digests.
- `a1_plan_episode_manifest.jsonl` and `a1_a0_cost_variant_episode_manifest.jsonl`: separate 360-episode locks.
- `a1_plan_prompt_locks.jsonl` and `a1_a0_cost_variant_prompt_locks.jsonl`: complete rendered prompt locks for each distinct preset.
- `analysis.json`: paired intervals, sensitivity, Holm, and claim gate.
- `wire_control_results.json`: no-duplicate-call transport controls.
- `cold_amortization.json`: explicit 1/2/4/8/16/32/64/128-message cold-artifact arithmetic.
- `locks.json`, `stage_and_cost_gates.json`, and `FROZEN_DIGESTS.json`: frozen identities and gates.
- `A1_READINESS_CHECKLIST.md`: credentials and approvals still required.

The prompt, episode, response, and turn-observation JSONL products are
dataset-derived and local-only. They are excluded from the public digest
inventory and source distribution. The public verifier requires none of them.

The unfavorable results and all claim blockers are intentionally retained.
