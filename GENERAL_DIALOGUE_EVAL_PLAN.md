# Urusilla General-Dialogue Evaluation Plan

Status: preregistration-ready draft; no experiment described here has been run

Evidence cut-off: 2026-08-23

Planned execution: offline and local open-weight models only; no paid API calls and no external actions

## 1. Non-claim statement

This document is an evaluation protocol, not evidence that Urusilla is useful,
general, efficient, safe, adopted, or understood by any model. It records
hypotheses, methods, accounting rules, and stopping rules before scored runs.
Unfavorable, null, malformed, refused, repaired, and fallback episodes remain in
the final results.

The strongest available literature supports conditional conclusions: compact
action-state records can help particular pipelines; task-aware format selection
can improve accuracy while increasing tokens on some tasks; evolved expression
rules can transfer between some model families; and sparse communication can
outperform verbose communication. None of those results demonstrates a
universal, self-evolving language for ordinary agent dialogue.

Passing this plan would support only the bounded statement that a frozen
Urusilla configuration improved the measured safety-adjusted task economics on
the named datasets and local model revisions. It would not establish universal
communication, natural-language replacement, persistent adoption, autonomy,
external interoperability, or state-of-the-art performance.

## 2. Objective and decision order

The objective is to determine whether an unfamiliar sender and receiver can use
a compact, adaptive communication layer directly in a task without losing
meaning, and whether any benefit survives cold-start, repair, and safety costs.

Every decision is lexicographic, in this order:

1. no unauthorized effect or privacy disclosure;
2. protocol validity and semantic fidelity;
3. safe task completion;
4. cross-model portability and fallback reliability;
5. total model-visible tokens per safely completed task;
6. wire bytes, latency, memory, and local compute proxies.

A saving at a later level cannot compensate for a failure at an earlier level.
No weighted composite score will hide these trade-offs.

## 3. Preregistered research questions and hypotheses

### 3.1 Research questions

- **RQ1 — Semantic fidelity:** Can a receiver recover the task-relevant public
  state and complete the task as reliably from Urusilla as from compact terse
  English and canonical minified JSON?
- **RQ2 — Adaptation benefit:** Does an oracle-free selector outperform the
  best fixed eligible representation on held-out dialogue families after all
  exploration and selection costs are charged?
- **RQ3 — Bootstrap amortization:** At what session length, if any, do Capsule,
  compatibility-test, negotiation, profile, and repair costs break even?
- **RQ4 — Safety and fallback:** Do malformed, stale, ambiguous, hostile, and
  unsupported messages fail closed and recover through an eligible fallback?
- **RQ5 — Cross-model portability:** Does a profile learned or selected with one
  model remain task-equivalent when the sender, receiver, or initiator model is
  replaced by an unfamiliar family?
- **RQ6 — Evolution:** Can session-level expression changes improve held-out
  task economics without private pairwise conventions or silent semantic drift?
- **RQ7 — Attribution:** Is any measured benefit caused by representation rather
  than by omitting messages, pruning edges, replaying less history, or receiving
  privileged task information?

### 3.2 Confirmatory hypotheses

All confidence intervals and multiplicity handling are defined in Section 13.

- **H1, semantic non-inferiority:** For every qualifying primary dialogue
  family, the one-sided 95% lower confidence bound for Urusilla minus the
  strongest frozen baseline in safe task-success rate is greater than `-0.01`.
- **H2, positive task economics:** Subject to H1 and all safety gates, the
  two-sided 95% confidence interval for paired total-model-token reduction
  excludes zero in Urusilla's favor on each claimed family.
- **H3, material task economics:** The one-sided 95% lower confidence bound for
  total-model-token reduction is at least `0.20` on at least two primary
  families. This is the material initial-goal gate, not a competitive claim.
  The repository's separate `25%` competitive-policy threshold remains stricter.
- **H4, adaptive benefit:** On a frozen test split, the adaptive selector is
  task-success non-inferior to and uses fewer fully accounted tokens than the
  best fixed eligible representation selected on calibration data.
- **H5, portability:** H1 holds for every preregistered off-diagonal
  sender-receiver model-family pair, not only for self-play or pooled averages.
- **H6, safe fallback:** Every deterministic invalid-message vector takes its
  preregistered reject, request-fragment, checkpoint, JSON, or terse-English
  fallback path before any task effect; valid-message false refusal is reported
  separately and does not exceed the frozen baseline by more than 1 point.

Failure to reject a null hypothesis is a null result. A result in one dialogue
family, model pair, tokenizer, or warm-session length is not generalized to
another.

## 4. Experimental unit, information boundary, and equivalence contracts

The **episode** is one sender-receiver task instance with frozen source material,
roles, private/public information allocation, model pair, initiator, prompts,
generation controls, maximum turns, repair policy, and scorer. The **session**
is an ordered sequence of episodes sharing only the state explicitly permitted
by its arm.

The sender sees its allocated source material. The receiver must consume the
actual communication-arm output directly. The receiver is not given the
sender's raw source, a gold summary, or an expanded natural-language paraphrase
unless that content is counted as an explicit fallback or conversion request.

Two contracts are evaluated separately:

1. **Lossless typed equivalence.** The receiver-side parser must recover the
   complete canonical typed message and deterministically re-encode it. Exact
   byte equality is required for eligible codec claims.
2. **Task-level semantic equivalence.** An action-state or learned projection
   may omit original prose or private reasoning, but must preserve every
   task-required fact, constraint, negation, quantity, unit, time, uncertainty,
   provenance reference, request, and commitment. It cannot claim exact prose
   reconstruction.

An arm that decompresses or translates to long natural language before the
receiver model may claim wire savings only. The expanded receiver input and the
conversion work count in the task ledger.

## 5. Dialogue families and frozen sampling

The study uses public datasets with complementary, observable outcomes. Dataset
versions, licenses, source revisions, file digests, record IDs, exclusions, and
derived-task code must be frozen in a signed manifest before any scored model
run.

| Family | Public source | Frozen task constructed for this study | Primary outcome |
| --- | --- | --- | --- |
| Task-oriented state and correction | [Schema-Guided Dialogue](https://ojs.aaai.org/index.php/AAAI/article/view/6394) | Communicate the public state update, unresolved slots, constraints, and next eligible dialogue act across services and domains. Hold out complete services from calibration. | Joint state/constraint exact match and executable next-act validity |
| Multi-domain clarification transfer | [MultiWOZ 2.4](https://aclanthology.org/2022.sigdial-1.34/) | Communicate corrected belief-state deltas and whether a clarification is required. This is a transfer family, not a substitute for SGD. | Joint goal accuracy, correction preservation, clarification decision |
| Negotiation and conflicting preferences | [CaSiNo](https://aclanthology.org/2021.naacl-main.254/) | Communicate public offers, commitments, unresolved issues, and final allocation without exposing the sender's private priorities. | Allocation validity, public-state exactness, agreement/impasse accuracy, privacy leakage |
| Knowledge-grounded dialogue | [BEGIN](https://aclanthology.org/2022.tacl-1.62/) | Communicate source-grounded claims and uncertainty, then classify or answer without inventing unsupported content. | Existing human attribution label, unsupported-claim rate, source ownership |
| Long collaborative dialogue | [QMSum](https://aclanthology.org/2021.naacl-main.472/) | Communicate query-relevant decisions, action items, participants, and supporting spans from meeting segments. | Gold-span coverage plus blinded factuality adjudication on a fixed sample |
| Ambiguity and fallback transfer | [ClarifyBench](https://aclanthology.org/2026.findings-acl.2028/) and the [MAC clarification design](https://aclanthology.org/2026.iwsds-1.1/) | Decide whether to clarify, identify the unresolved variable, and avoid premature action. Tool calls are replaced with deterministic local simulators. | Ambiguity localization, clarification efficiency, premature-action rate |

The four confirmatory primary families are SGD, CaSiNo, BEGIN, and QMSum.
MultiWOZ 2.4 and ClarifyBench are transfer families and are reported separately.
QMSum's abstractive score is not used alone: its factuality subset receives
blinded dual annotation with adjudication, and automatic similarity metrics are
secondary.

For each family:

- sort canonical record IDs by `SHA-256("20260823" || record_id)`;
- reserve the first 50 eligible records for calibration and prompt debugging;
- reserve the next 50 for the staged local pilot;
- reserve the next 200 for the untouched confirmatory set;
- group related dialogue turns, services, meetings, and negotiating pairs before
  splitting so that no conversation or service leaks across splits; and
- publish all exclusions before decoding any scored output.

If a family has fewer eligible records after grouping, it becomes exploratory;
the sample is not silently replenished from another split.

## 6. Representation and communication arms

Every arm receives identical task information and differs only in the frozen
communication policy stated below.

1. **Full-history natural language.** Ordinary agent messages and all prior
   messages are replayed. This measures the uncompressed reference workflow.
2. **Compact terse English.** Atomic task facts, explicit provenance, no
   greeting, repetition, or private reasoning. This is the mandatory primary
   language baseline.
3. **Canonical minified JSON.** A stable task-equivalent schema, fixed key order,
   no optional whitespace, and no privileged fields.
4. **Clean-room action-state record.** A PACT-motivated public
   action/state/result projection with provenance, uncertainty, and missing-data
   fields. It is task-equivalent, not lossless prose compression.
5. **Static Urusilla.** A frozen typed semantic core and approved surface with
   terse English or JSON fallback. No scored-data adaptation is permitted.
6. **Oracle-free adaptive Urusilla.** Before the receiver call, a frozen policy
   selects silence, routine/delta, action-state, static Urusilla, JSON, or terse
   English using only observable pre-call information. Selector cost and regret
   are charged.
7. **Evolving profile.** Repeated-session aliases or expression rules may be
   proposed using calibration sessions only, then are frozen and content
   addressed before confirmatory evaluation. Section 11 applies.
8. **Verified silence.** The message is suppressed only when a frozen local
   policy predicts it is unnecessary. A no-payload placebo and an oracle-silence
   upper bound are reported separately.
9. **Sparse/pruned topology.** Where three or more agents are present, reduce
   edges or messages while holding the representation fixed. This arm is
   inspired by sparse debate and AgentDropout and cannot be reported as a
   language-format improvement.
10. **Negotiated routine.** For repeated structured requests, charge the full
    cold negotiation, implementation, validation, profile, and fallback cost.

The adaptive arm is not allowed to consult gold answers, receiver outputs,
future turns, test-set labels, or post-hoc token counts. Its calibration-selected
best fixed comparator is frozen separately for every task family and model pair.
All fixed arms are also reported individually to expose selector regret.

## 7. P0/P1/P2 experiment matrix

| Priority | Experiment | Required arms | Entry gate | Exit evidence |
| --- | --- | --- | --- | --- |
| **P0.1** | Deterministic semantic and adversarial conformance | JSON, static Urusilla, all fallback paths | Frozen schemas, vectors, and exact oracle | 100% positive typed round-trip; 100% deterministic safe routing for declared invalid vectors; zero external effects |
| **P0.2** | Same-model general-dialogue pilot | Full history, terse English, JSON, action-state, static Urusilla | P0.1 pass | Per-family task success, semantic fidelity, complete token ledger, arm-blinded matched-defect scorer calibration, repairs, refusals, and fallback |
| **P0.3** | Causal payload-dependence controls | Valid payload, missing payload, shuffled payload, semantic counterfactual, invariant paraphrase | P0.2 parser reliability | Receiver output changes with semantic flips, remains stable under meaning-preserving variants, and abstains when required evidence is absent |
| **P1.1** | Cross-model cross-play | All fixed eligible arms; both initiator orders | P0 gates pass on each model | Full 3 x 3 ordered matrix, self-play versus unseen-pair gap, per-family non-inferiority |
| **P1.2** | Oracle-free adaptation | Best fixed arm, adaptive Urusilla, hindsight oracle | P1.1 minimum reliability | Adaptation benefit, exploration cost, selection regret, calibration/test separation |
| **P1.3** | Cold-start and repeated-session amortization | Terse English, JSON, adaptive Urusilla, negotiated routine | Frozen Capsule and compatibility test | Cumulative cost curves and confidence intervals for session lengths 1 through 128 |
| **P1.4** | Safety, repair, and fallback campaign | Every executable arm plus hostile/unsupported inputs | Offline sandbox and zero-effect policy | False accept, false refusal, safe fallback success, repair cost, rollback latency, privacy leakage |
| **P2.1** | Held-out language-rule evolution | Static, adaptive, evolving profile | All P1 safety gates pass | Frozen-rule OOD benefit across held-out domains and model families, with all evolution cost charged |
| **P2.2** | Silence and topology attribution | Fixed representation with full, silence, hand-sparse, and learned-pruned graphs | Tasks permit optional communication | Ablation separating representation, projection, history, message-count, and topology effects |
| **P2.3** | Long-session delta resilience | Full state, delta, periodic checkpoint, terse English | Authenticated session simulator | Savings and recovery under loss, duplication, reorder, corruption, reset, and profile churn |

The first cost-guarded SGD slice of P0.2 is preregistered in
[`GENERAL_DIALOGUE_P0_SGD20_PREREGISTRATION.md`](GENERAL_DIALOGUE_P0_SGD20_PREREGISTRATION.md).
It records no model run or result.

P2 does not begin because P1 is slow or inconvenient. It begins only after its
entry gates pass. A failed P0/P1 result is retained and reported.

## 8. Cross-model matrix

The primary no-paid-API matrix uses local, pinned revisions of:

- `Qwen2.5-7B-Instruct`;
- `Mistral-7B-Instruct-v0.3`; and
- `Llama-3.1-8B-Instruct`.

If a weight license, access condition, or hardware limit prevents one model from
being installed before preflight, it is not silently replaced. A dated
preregistration amendment must name the replacement family before calibration
outputs are inspected. Quantization artifact, tokenizer, chat template, runtime,
context limit, and generation controls are locked by digest.

Each cell below is run in both initiator orders. Diagonal cells are self-play;
off-diagonal cells are unfamiliar-family cross-play.

| Sender \ Receiver | Qwen | Mistral | Llama |
| --- | ---: | ---: | ---: |
| Qwen | Q→Q | Q→M | Q→L |
| Mistral | M→Q | M→M | M→L |
| Llama | L→Q | L→M | L→L |

The protocol, examples, and selector are frozen before the confirmatory matrix.
No pair-specific dictionary may be learned from confirmatory items. Results are
reported per cell, per initiator, and per family; pooling cannot hide a failed
off-diagonal cell.

## 9. Primary metrics and exact accounting

### 9.1 Eligibility metrics

- `typed_exact`: all required canonical fields match the oracle.
- `canonical_reencode_exact`: recovered typed messages re-encode byte-identically.
- `semantic_field_accuracy`: macro average over preregistered required fields,
  with separate worst-field and worst-stratum scores.
- `safe_task_success`: the family-specific task scorer passes and no safety,
  authorization, privacy, provenance, or integrity rule fails.
- `unsafe_false_accept`: an invalid or unsupported payload reaches a task-effect
  decision instead of reject, clarification, checkpoint, or fallback.
- `valid_false_refusal`: a valid supported payload is rejected or unnecessarily
  falls back.
- `fallback_success`: safe task success among episodes that require fallback.

`typed_exact` and `canonical_reencode_exact` must be 100% in the deterministic
lossless lane. Task-level projections are scored by their declared required
fields and may not be relabeled lossless.

**Safe-completion denominator validity.** Complete token accounting validates
the cost numerator, not the `safe_task_success` denominator. Before a
task-level efficiency comparison is eligible, the study injects the same
preregistered semantic defects into matched natural-language, JSON, and
Urusilla completions while hiding arm identity from the scorer. For every arm,
the report publishes `known_positive_total`, `defects_detected`, and
`detection_rate`. A deterministic scorer must detect 100% of frozen known
positives. For human or model judges, the minimum detection rate and maximum
allowed between-arm gap are frozen before scored outputs are opened. Missing or
unmeasurable calibration makes that arm's safe-completion denominator and
tokens per safely completed task `null`; if either candidate or required
baseline lacks a valid denominator, the efficiency comparison is also `null`.

### 9.2 Primary efficiency metric

For episode `i` and arm `a`:

```text
model_tokens_i,a =
    task_input_tokens
  + system_and_role_tokens
  + demonstrations_and_capsule_tokens
  + sender_input_tokens + sender_output_tokens
  + receiver_input_tokens + receiver_output_tokens
  + replayed_history_tokens
  + selector_or_negotiation_model_tokens
  + conversion_model_tokens
  + validation_and_comprehension_test_tokens
  + repair_retry_clarification_tokens
  + fallback_tokens
  + final_answer_tokens
```

Tokens are counted under the exact tokenizer used by each local model for every
actual request, including chat-template and role tokens. Sender tokens are
counted with the sender tokenizer; receiver tokens with the receiver tokenizer.
Local runtime counts and independently reproduced tokenizer counts are both
stored. Disagreement is an audit failure until resolved.

The primary endpoint is:

```text
total_model_tokens_per_safely_completed_task =
    sum(model_tokens_i,a) / sum(safe_task_success_i,a)
```

If an arm has zero safely completed tasks, this value is infinite. The paired
episode-level token reduction against baseline `b` is also reported:

```text
reduction_i = 1 - model_tokens_i,urusilla / model_tokens_i,b
```

but it is claim-eligible only among episodes retained by the preregistered paired
analysis, including failed and fallback outcomes. Communication-output tokens,
receiver-input tokens, and successful-episode-only totals are diagnostics, not
headline metrics.

### 9.3 Secondary metrics

- complete UTF-8 and envelope bytes, including hashes, signatures or modeled
  authentication, framing, retransmission, and profile identifiers;
- encode, decode, selector, model, repair, and end-to-end p50/p95 latency;
- peak host/GPU memory, runtime, and measured local energy when instrumentation
  is available;
- number of messages, edges, turns, clarifications, repairs, retransmissions,
  fallbacks, and profile changes; and
- privacy fields emitted, provenance errors, unsupported claims, and calibration.

Wire bytes, model tokens, latency, and energy remain separate axes.

## 10. Cold-start and bootstrap accounting

For every session length `N ∈ {1,2,4,8,16,32,64,128}`, publish:

```text
cumulative_cost_a(N) =
    capsule_transfer
  + capability_and_version_negotiation
  + receiver_comprehension_test
  + schema_profile_or_dictionary_transfer
  + selector_training_or_exploration
  + routine_generation_and_validation
  + sum_{n=1..N}(episode_tokens + repairs + fallbacks)
```

The cold value charges every one-time artifact in full. Warm values may amortize
only artifacts demonstrably retained inside the declared session. Cross-session
memory is disabled in the primary study. Separate churn strata reset the receiver
or change the schema/profile after episodes 2, 8, and 32.

Break-even is the smallest preregistered `N` for which the upper-cost arm has
lower cumulative cost and the lower bound of the paired 95% saving interval is
above zero without violating semantic or safety gates. If no tested `N` breaks
even, report `>128`; do not extrapolate a favorable point.

Training and evolution costs are reported twice: once as raw study cost and once
amortized only over the exact deployment horizon under analysis. Neither may be
omitted from the cold result.

No claim may select one favorable warm horizon after inspection. The complete
frozen `N` curve is published, and any single deployment horizon `K` used for a
headline comparison must be registered before scored outputs are opened.

## 11. Evolution, drift, and adversarial vectors

### 11.1 Allowed evolution

- The semantic kernel is immutable within a version.
- A candidate alias or rule is a new content-addressed profile, never a silent
  reinterpretation of an existing symbol.
- Candidate discovery uses calibration sessions only.
- Every candidate includes a typed definition, migration map, examples,
  counterexamples, rollback path, privacy classification, and test vectors.
- An independent frozen semantic checker and an unfamiliar receiver must pass
  before the candidate is eligible.
- Confirmatory labels and receiver outputs cannot update the candidate.
- Failed upgrades fall back by fragment or profile; unrelated content is not
  rewritten.

Evolution fitness is lexicographic: safety, exact required-field recovery,
safe task success, portability, then fully accounted tokens. A shorter candidate
that fails an earlier term receives no compensating reward.

### 11.2 Positive semantic stress vectors

The fixed suite covers negation, double negation, conjunction, alternatives,
quantities, units, ranges, dates, time zones, deadlines, uncertainty,
contradictory evidence, source ownership, causal references, corrections,
revocation, requests versus commitments, explicit unknowns, and partial updates.

### 11.3 Negative and hostile vectors

At minimum, freeze vectors for:

- unknown symbol, act, field, schema, extension, profile, and version;
- truncated, duplicated, reordered, replayed, and out-of-sequence messages;
- stale delta, wrong base-state digest, missing checkpoint, and profile churn;
- corrupted payload, checksum mismatch, signature/MAC simulation failure, and
  conflicting source digest;
- alias collision, semantic reinterpretation, ambiguous abbreviation, and
  sender-receiver dictionary disagreement;
- zero-width characters, Unicode confusables, bidirectional controls, invalid
  UTF-8, delimiter injection, and nested quoting ambiguity;
- prompt injection inside payload, schema, example, Capsule, provenance field,
  and fallback text;
- oversized field, recursive reference, decompression-expansion bomb, and
  resource-exhaustion attempt inside fixed local limits;
- false capability advertisement, unsupported executable request, commitment
  without authority, and content that attempts permission expansion;
- private preference, identifier, raw prompt, or hidden-reasoning leakage;
- covert-channel and steganographic marker probes; and
- semantically valid paraphrases that must not be falsely rejected.

Expected outcomes are declared per vector: accept, reject, request exact
fragment, request full checkpoint, fall back to JSON, fall back to terse English,
or abstain. “Best effort” inference of an unknown executable meaning is never an
eligible safe path.

## 12. Silence, pruning, and causal controls

Language-format claims must separate shorter messages from fewer messages and
from privileged public-state projection.

For every task that permits optional communication, run these representation-
fixed controls:

- full communication graph and full history;
- no-communication/placebo payload;
- verified silence policy;
- hand-designed sparse graph;
- learned pruning or AgentDropout-style elimination; and
- oracle silence as an explicitly unattainable upper bound.

For every scored item, also freeze causal message interventions:

- remove the payload while keeping all non-payload context identical;
- shuffle payloads between matched items;
- flip one task-critical semantic field while preserving length and syntax;
- paraphrase or reserialize without changing meaning; and
- corrupt or withhold one required field.

The receiver should change its output under semantic flips, remain stable under
meaning-preserving variants, and abstain or clarify when required evidence is
missing. Fixed-answer behavior that passes plumbing without consuming the
payload is not language-understanding evidence.

The final ablation table reports independent deltas for representation,
action-state projection, history replay, message count, and graph topology.

## 13. Randomization, statistics, and multiplicity

- Sampling seed: `20260823`.
- Generation seeds: `20260823`, `20260824`, and `20260825` for every stochastic
  confirmatory cell.
- Conditions are paired by dataset item, information allocation, sender,
  receiver, initiator, seed, and maximum token budget.
- Temperature and decoding controls are identical across arms unless a method
  intrinsically requires another setting, in which case that difference and its
  cost are preregistered.
- No malformed, refused, timed-out, repaired, fallback, or failed episode is
  removed from the denominator.
- The primary uncertainty method is a stratified paired bootstrap with 10,000
  resamples within dialogue family and model-pair stratum, seed `20260823`.
- Safe-task-success non-inferiority uses a one-sided 95% interval. Token,
  fallback, and portability effects use two-sided 95% intervals unless a
  directional threshold is explicitly stated in Section 3.
- Confirmatory comparisons against mandatory baselines use Holm correction
  within each hypothesis family. Raw and adjusted values are both published.
- Per-family, per-model-pair, worst-stratum, and pooled results are reported.
  Pooled success cannot rescue a failed required stratum.
- Calibration data select prompts, the best fixed comparator, and selector
  settings. Confirmatory data are opened once after artifacts are locked.
- Registration constrains only future decisions. The manifest records
  `prior_rounds_seen`, `arms_dropped_before_this_registration` with reasons and
  evidence digests, and `search_space.status` as `complete`, `partial`, or
  `unrecoverable`. An unrecoverable earlier search space may still precede a new
  frozen hidden-data test, but it cannot be described as untouched architecture
  selection and does not inherit nominal search-wide confidence coverage.

The strongest frozen baseline for each family/model pair is selected on
calibration data by the same lexicographic decision order as Section 2. Test
results against every mandatory baseline are still published.

## 14. Staged free local pilot

No stage uses a paid API, real user data, external messaging, live purchases,
or network side effects. Dataset acquisition is read-only; scored execution is
local and sandboxed.

### Stage 0 — deterministic offline gate

- Freeze schemas, parsers, token ledgers, task scorers, and all positive/negative
  vectors.
- Run P0.1 without a model.
- Require 100% exact deterministic positive recovery, 100% declared safe route
  on invalid vectors, reproducible token counts, and zero external effects.

### Stage 1 — minimal two-model reliability pilot

- Qwen and Mistral only.
- 20 pilot items per primary family, all P0 fixed arms, one deterministic run.
- Purpose: find parser, context-limit, refusal, timeout, scoring, and ledger
  failures. These results are exploratory and cannot support performance claims.

### Stage 2 — full local pilot and cross-play

- All three model families and the complete 3 x 3 ordered matrix.
- 50 untouched pilot items per primary family, both initiator orders, three
  generation seeds where stochastic.
- Add P1 adaptation, bootstrap, and safety campaigns only after fixed-arm
  reliability passes.

### Stage 3 — confirmatory run

- Lock repository revision, dependency/runtime images, model and tokenizer
  artifacts, prompts, schemas, profiles, selectors, datasets, record IDs,
  scorers, statistical script, and expected stopping rules by digest.
- Run the 200-item confirmatory split per primary family exactly once.
- Transfer families are run afterward with unchanged artifacts.

### Stage 4 — optional P2 research

- Begin evolution, topology attribution, and long-session resilience only if
  their entry gates pass.
- P2 remains separately labeled even if favorable.

## 15. Stopping rules

Stopping decisions occur only at fixed stage boundaries; there is no unplanned
repeated peeking within a stage.

### 15.1 Immediate safety and integrity stops

Stop the affected run, preserve artifacts, and do not substitute a result if:

- any unauthorized external effect occurs;
- a private field, raw prompt, or hidden reasoning is disclosed outside the
  frozen synthetic fixture;
- an invalid executable payload bypasses the declared fail-closed path;
- dataset, prompt, model, tokenizer, scorer, profile, or source digest changes;
- confirmatory labels or outputs enter selector/evolution state;
- paired arms receive different task information or token budgets; or
- the complete token ledger cannot be reconstructed.

### 15.2 Stage-expansion stops

- Do not leave Stage 0 unless all deterministic gates pass exactly.
- Do not expand a model/arm from Stage 1 if malformed plus unrecoverable episodes
  exceed 5%, or safe task success is more than 5 points below both terse English
  and JSON. Fixes create a new preregistered pilot revision; old failures remain.
- Do not start adaptive or evolving arms if static Urusilla does not meet the
  1-point semantic/task non-inferiority margin in the full pilot.
- Stop the token-optimization branch as futile if, after Stage 2, the upper 95%
  confidence bound for savings is at or below zero in every primary family.
  Safety/fallback research may continue but cannot be presented as compression.
- Do not start P2 evolution if any P1 safety, fallback, or off-diagonal cross-play
  gate fails.

### 15.3 Confirmatory interpretation stops

- If H1 fails, no efficiency claim is eligible even if token counts are lower.
- If H1 passes but H2 fails, report semantic feasibility with no demonstrated
  token benefit.
- If H2 passes but H3 fails, report a bounded positive result, not a material or
  competitive reduction.
- If only warm sessions pass, limit the claim to the observed warm session
  lengths and publish the unfavorable cold result next to it.
- If any required cross-model cell fails H1, do not use “cross-model portable.”
- If all gates pass, the result is still bounded to this frozen matrix; this plan
  alone never authorizes “universal,” “standard,” “adopted,” “leading,” or
  “state of the art.”

## 16. Required artifacts and report tables

Before the confirmatory run, publish or archive locally:

- immutable experiment manifest and amendment history;
- dataset/license/source manifest with hashes and grouped split IDs;
- complete prompts after rendering, parsers, schemas, profiles, and fallback
  rules;
- model, tokenizer, quantization, runtime, and chat-template identities;
- positive, negative, causal, and privacy test vectors;
- raw per-request token records and independently reconstructed counts;
- raw per-episode outcomes, including failures and fallbacks;
- bootstrap and multiplicity scripts with fixed seeds; and
- hardware/runtime metadata and local-compute measurements.

The final report must contain:

1. safe task success and semantic fidelity by family and model-pair cell;
2. total model tokens per safely completed task with a complete category ledger;
3. cold/warm cumulative curves through 128 episodes and measured break-even;
4. adaptive selection frequencies and regret against best fixed and oracle;
5. fallback, false-accept, false-refusal, repair, and rollback results;
6. cross-play gaps, both initiator orders, and worst-stratum outcomes;
7. silence/topology/action-state/format ablations;
8. wire bytes, latency, memory, and available compute/energy proxies; and
9. every null, adverse, stopped, or ineligible result with its reason.

## 17. Primary-source basis

The experiment design is grounded in the following primary sources. Reported
paper percentages retain their original denominators and are not treated as
Urusilla results.

- [OPTiMACS: Learning Optimal Message Representations for Agentic Communication, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1441/) — dynamic task-aware representations; token use decreased on three evaluated datasets and increased on NarrativeQA, motivating best-fixed and full-cost comparisons.
- [EcoLANG: Efficient and Effective Agent Communication Language Induction for Social Simulation, Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.284/) — evolved vocabulary/rules and cross-model transfer on bounded social simulations.
- [AutoForm: Beyond Natural Language, Findings of EMNLP 2024](https://aclanthology.org/2024.findings-emnlp.623/) — model-selected formats and asymmetric transfer between format selector and solver models.
- [PACT: What Should Agents Say?, arXiv 2026](https://arxiv.org/abs/2606.05304) and its [official repository](https://github.com/iNLP-Lab/PACT) — compact public action/state/result projection; preprint evidence, not general-dialogue proof.
- [Agora: A Scalable Communication Protocol for Networks of Large Language Models, arXiv 2024](https://arxiv.org/abs/2410.11905) and its [paper demo](https://github.com/agora-protocol/paper-demo) — natural-language fallback, negotiated routines, and explicit bootstrap amortization.
- [Dynamic population-based meta-learning for multi-agent communication with natural language, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/8caa38721906c1a0bb95c80fab33a893-Abstract.html) — seen, unseen, and human partner separation, motivating frozen unfamiliar-partner cross-play.
- [Countering Language Drift via Visual Grounding, EMNLP-IJCNLP 2019](https://aclanthology.org/D19-1447/) — semantic and structural drift under task reward and the need for an independent grounding constraint.
- [Multi-agent Communication Meets Natural Language, ACL 2020](https://aclanthology.org/2020.acl-main.685/) — language-drift taxonomy and fixed-listener evaluation.
- [Emergent Languages in Populations of Language Model Agents, arXiv 2026](https://arxiv.org/abs/2605.31170) — observational and model-judged evidence of efficiency, constructed-language, oversight-evasion, and steganographic proposals; included as threat motivation, not proof of autonomous behavior.
- [Improving Multi-Agent Debate with Sparse Communication Topology, Findings of EMNLP 2024](https://aclanthology.org/2024.findings-emnlp.427/) — sparse connectivity as a required attribution baseline.
- [AgentDropout, arXiv 2025](https://arxiv.org/abs/2503.18891) and its [official repository](https://github.com/wangzx1219/AgentDropout) — dynamic elimination of redundant agents and communication.
- [Evaluating Attribution in Dialogue Systems: The BEGIN Benchmark, TACL 2022](https://aclanthology.org/2022.tacl-1.62/) — human-labeled groundedness and evidence that automatic metrics can fail under distribution shift.

## 18. Registration fields to freeze before execution

This document is method-complete but not execution-registered until the following
fields are populated in a content-addressed manifest without changing the rules
above:

- repository revision and local patch digest;
- dataset revisions, licenses, SHA-256 values, grouped split IDs, and exclusions;
- model/weight, quantization, tokenizer, runtime, and chat-template revisions;
- complete prompts, schemas, profiles, selectors, scorers, and stop strings;
- context/output limits, temperature and generation controls;
- hardware and local runtime limits;
- exact expected outcome for every deterministic adversarial vector;
- annotation instructions, annotator blinding, agreement threshold, and
  adjudication procedure for the QMSum factuality subset; and
- matched cross-arm defect fixtures, scorer/judge detection thresholds, and the
  rule that invalid denominator calibration makes efficiency outcomes null;
- `prior_rounds_seen`, every known arm dropped before registration with its
  reason and evidence digest, and an explicit search-space status; and
- signed freeze time preceding the first scored confirmatory output.

Until that manifest exists, all runs under this document are calibration or
pilot work and cannot support a confirmatory claim.
