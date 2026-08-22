# Urusilla P0 SGD-20 Cold Native-Consumption Preregistration

Status: preregistered protocol design; execution manifest not yet registered;
**no scored or model run has been performed**

Protocol ID: `urusilla-general-dialogue-p0-sgd20-cold-native/1`

Draft date: 2026-08-23

Parent protocol: [`GENERAL_DIALOGUE_EVAL_PLAN.md`](GENERAL_DIALOGUE_EVAL_PLAN.md)

Prior measurement boundary: [`URUSILLA_GENERAL_DIALOGUE_RESULTS.md`](URUSILLA_GENERAL_DIALOGUE_RESULTS.md)

Planned execution: offline local open-weight inference only; no paid API calls,
tools, live services, or external effects

## 1. Purpose and decision target

This document preregisters the smallest staged real-model experiment that can
screen the current static Urusilla action-state path for the following bounded
question:

> On the frozen Schema-Guided Dialogue next-action task, does direct model
> consumption of the current cold static Urusilla representation reduce total
> model-visible tokens per safely completed task relative to every required
> fixed baseline?

The experiment is a cost-controlled funnel:

1. a deterministic zero-model-call impossibility screen;
2. 10 paired items with Qwen;
3. 20 paired items with Qwen if the 10-item boundary permits expansion;
4. eight conditional Urusilla receiver calls plus eight deterministic
   pre-receiver negative-control decisions if the Qwen task and token gates
   otherwise pass; and
5. the same 20-item and causal sequence with Mistral only if Qwen passes every
   promotion gate.

Qwen is first because the prior gold-state oracle showed the largest prompt-only
opportunity under its tokenizer: 23.34%, compared with 7.48% for Mistral. This
ordering is a favorable first test for Urusilla and a cost guard, not evidence
that either model natively understands the representation.

Failure at a fixed boundary is retained as the result. It is not repaired and
silently rerun under the same protocol ID.

## 2. Existing evidence and missing measurement

The frozen broad-dialogue study reported all of the following:

- 399 SGD next-assistant-action prompt pairs;
- 54,817 raw-history prompt tokens versus 42,025 gold-state prompt tokens under
  the pinned Qwen tokenizer, a 23.34% prompt-only difference;
- 62,093 versus 57,447 under the pinned Mistral tokenizer, a 7.48% difference;
- zero model or provider calls;
- no task-accuracy result;
- no oracle-free sender;
- no sender output, receiver output, Capsule, comprehension, repair, fallback,
  or final-answer accounting; and
- zero demonstrated post-decode model-input saving in the lossless carrier lane.

This P0 does not reuse those percentages as task evidence. It uses the same
frozen source and gold annotations to define items and deterministic scorers,
while withholding gold frames from every model input.

## 3. Execution-registration gate and current absence of assets

The current checkout does not contain the ignored `work/general_dialogue/`
corpus, the ignored pinned tokenizer assets, a local model runtime, or local
Qwen/Mistral model weights. No model run has been attempted for this protocol.

Before the first model-visible token is generated, an execution manifest must
freeze all of the following by exact bytes and SHA-256:

- repository commit and any local patch digest;
- this preregistration document;
- source, derived corpus, and selected-item manifest;
- every prompt template, renderer, derivation rule, dynamic-slot type and token
  bound, arm schema, parser, task context, symbol table, and scorer;
- the current action-state Capsule;
- model source revision, converted/quantized weight file, tokenizer, chat
  template, and generation configuration;
- local inference runtime revision and build flags;
- independent token-counter implementation and version;
- output caps, context cap, stop strings, and timeout;
- hardware and operating-system identity; and
- the statistical script and fixed resampling seed.

Missing fields fail closed. Filling a field after inspecting a scored output
creates a new protocol revision and leaves the old result intact.

Complete dependent receiver, repair, and fallback prompts contain actual model
outputs and therefore cannot be known before inference. Before each dependent
call, the frozen renderer must derive the exact prompt only from the captured
prior output and frozen inputs, hash it, verify every dynamic-slot bound, and
append it to the execution trace before generation. No prompt text or renderer
may be edited in response to an observed output.

Dataset acquisition may use a separate read-only preparation phase. Scored
execution begins only after all source and model artifacts are local, verified,
and network access is disabled.

## 4. Frozen dataset identity

The only task family in this P0 is the already frozen Schema-Guided Dialogue
subset.

| Field | Frozen value |
| --- | --- |
| Source key | `schema_guided_dialogue_dev_001` |
| Upstream repository | `google-research-datasets/dstc8-schema-guided-dialogue` |
| Upstream revision | `e852981ae34990f4358979625854259302feaa78` |
| Upstream path | `dev/dialogues_001.json` |
| Immutable source URL | `https://raw.githubusercontent.com/google-research-datasets/dstc8-schema-guided-dialogue/e852981ae34990f4358979625854259302feaa78/dev/dialogues_001.json` |
| License | CC-BY-SA-4.0 |
| Expected source bytes | `2225937` |
| Expected source SHA-256 | `fe3a8ed9e160c15e20e7cfd16d03734b4473df0d3864f2ad687ea9eeee5eea52` |
| Existing source-freeze SHA-256 | `888bbdd680a22faa2e30e457d5559ad4042184ec2e0e5b7f7b7832ef6ebd2921` |
| Existing corpus-manifest SHA-256 | `6fba633e286527303afd180b0221362365a20efd9325686631df022fc6cf9fec` |
| Existing corpus JSONL SHA-256 | `3bede9398786dcb7de72a5bf2648105c62ba3b0f9339d7c86b774f937b104854` |
| Existing corpus-sequence SHA-256 | `349e57a679815aa343815117ac8ed0e753f516871152c46a38fa31484fcd82bd` |
| Eligible SGD prompt pairs | `399` |
| Existing prompt-pair digest | `ecf3df17b6b9967b1982713aa61ba70b1da0daf55f3dc2d709fb8352438d690c` |

The public repository does not redistribute the raw ignored corpus. This
document reproduces no source utterance.

## 5. Deterministic item construction and sampling

### 5.1 Eligible pair construction

The pair constructor follows `build_sgd_prompt_pairs` in
`urusilla_general_dialogue_eval.py`:

1. retain only records whose `source_family` is
   `schema_guided_dialogue`;
2. traverse turns in source order;
3. create an item when an assistant turn immediately follows a user turn;
4. define `pair_id` as `<corpus_id>:<assistant_turn_index>`, where the index is
   the zero-based source turn index;
5. define the sender source as the complete public dialogue history through the
   immediately preceding user turn;
6. derive the gold public-state oracle only from that preceding user's
   `gold_frames`; and
7. derive the gold next-action target only from the assistant turn's
   `gold_frames`.

Gold frames are available only to deterministic item generation, sampling
checks, and scoring. They are forbidden from model prompts, model-visible
metadata, adaptive state, repair prompts, and fallback prompts.

### 5.2 Record split

Let `H(x)` be SHA-256 over the exact byte concatenation
`UTF8("20260823") || UTF8(x)`, with no separator.

1. Sort the 64 frozen SGD `corpus_id` values by `(H(corpus_id),
   UTF8(corpus_id))` ascending.
2. Positions 1 through 50 are calibration-only and are excluded from this P0.
3. Positions 51 through 64 form the P0 pilot pool.
4. No calibration record may be used to fill a pilot shortfall.

Because this frozen convenience subset cannot supply the parent protocol's
full 50/50/200 grouped split, this SGD-20 result remains exploratory.

### 5.3 Pair selection inside the pilot pool

For each of the 14 pilot records:

1. sort its eligible pairs by `(H(pair_id), UTF8(pair_id))` ascending;
2. retain that ordered list without using history length, service, target act,
   token count, or any model result; and
3. iterate round-robin over the 14 records in record-split order, taking the
   first not-yet-selected pair from each record, then the second, and so on,
   until exactly 20 pairs have been selected.

This round-robin rule minimizes within-dialogue imbalance without inspecting
outcomes. If the pilot pool contains fewer than 20 eligible pairs, preflight
fails and the sample is not replenished.

The first 10 selected pair IDs are Stage A. The remaining 10 are Stage B. All
repeats, repairs, fallbacks, and causal variants of one pair remain in the same
dialogue cluster for analysis.

Before inference, write and hash a local sample manifest containing, for each
selected item:

- selection position, stage, `corpus_id`, pair ID, and turn indices;
- source-history SHA-256;
- gold public-state SHA-256;
- gold next-action SHA-256;
- every source-known rendered prompt SHA-256, plus every dependent-prompt
  template, renderer, derivation-rule, and dynamic-slot-bound SHA-256;
- every minimum-success output SHA-256 used by the zero-call screen; and
- every conditional causal-variant SHA-256 when applicable.

The manifest contains no model result when it is frozen.

## 6. Common task and corrected canonical output contract

### 6.1 Preflight correction

The current evaluator instruction asks for ordered `ACT(slot)` labels, while its
gold target is canonical JSON containing `act`, `service`, and `slot`. The two
contracts must not be mixed in a scored run.

This preregistration replaces both with one exact receiver output envelope:

```json
{"actions":[{"act":"REQUEST","service":"Hotels_1","slot":null}],"status":"ok"}
```

The normative rules are:

- the top level is one object with exactly `actions` and `status`;
- keys are sorted lexicographically with compact separators;
- `status` is `ok` for an ordinary valid task or `abstain` for a preregistered,
  receiver-visible valid-but-unsupported input; the missing and mismatched
  causal vectors in Section 16 are rejected before receiver delivery and do
  not award abstention credit;
- `actions` preserves source action order;
- each action has exactly `act`, `service`, and `slot` in canonical key order;
- `act` and `service` preserve the source strings exactly; `slot` preserves the
  source string exactly when present and is JSON `null` when the source slot is
  null or absent;
- an abstention is exactly `{"actions":[],"status":"abstain"}`;
- duplicate keys, non-canonical JSON, Markdown, prose, unknown keys, and trailing
  text are invalid; and
- no private reasoning is requested or accepted.

The target-normalization code must be frozen by digest before any call.
Preflight runs the contract against all 399 gold targets and fails unless every
target has one deterministic canonical encoding and round-trips exactly,
including the string-versus-null slot distinction.

### 6.2 Task instruction

Every receiver is asked to predict the next assistant dialogue actions from
only the information authorized for its arm and to emit the corrected canonical
output envelope. The receiver receives no item ID unless the same binding is
part of that arm's visible payload, no gold target, no later turn, and no raw
history in a projected-message arm.

## 7. Five fixed representation arms

Every arm receives identical source information and task semantics. Differences
are limited to its frozen communication policy and required setup.

### 7.1 `full_history`

- A deterministic relay, not a model sender, presents the complete public
  dialogue history through the latest user turn to the receiver.
- No summarization, state annotation, Urusilla instruction, or hidden glossary
  is added.
- The common receiver task instruction and output contract are included and
  counted.
- Calls per base item: one receiver call.

This is the strongest no-extraction reference. Its lack of a model sender is a
real cost advantage, not a free unreported operation.

### 7.2 `compact_terse_english`

- A model sender sees the same complete public history.
- It emits only atomic service, user-action, active-intent, requested-slot,
  slot-value, correction/negation, and provenance facts under one frozen terse
  grammar.
- Greetings, explanations, hidden reasoning, and redundant history are
  forbidden.
- A deterministic parser projects the terse output into the common typed state
  for semantic scoring.
- The receiver sees only the actual terse sender output plus the common task
  and output contract.
- Calls per base item: one sender and one receiver.

The complete grammar and parser are preflight-frozen. This is the mandatory
primary language baseline.

### 7.3 `canonical_minified_json`

- A model sender sees the same complete public history.
- It emits the descriptive frame shape already used by `_sgd_oracle_state`:
  frames contain service, ordered user actions with act/slot/values, and the
  cumulative active intent, requested slots, and slot values when present.
- Objects use sorted keys, compact separators, UTF-8, no duplicate keys, and no
  Urusilla symbol names or numeric aliases.
- The receiver sees only the actual canonical JSON sender output plus the
  common task and output contract.
- Calls per base item: one sender and one receiver.

### 7.4 `clean_action_state`

- A model sender sees the same complete public history.
- It emits a clean-room, descriptive public action/state/result object with
  explicit goal, state, action, result, missing-information, uncertainty, and
  provenance fields.
- It contains the same task-required state as the terse and JSON arms, no gold
  fields unavailable to those arms, no Urusilla names, no learned aliases, and
  no private reasoning.
- The receiver sees only the actual clean action-state output plus its frozen
  descriptive schema and the common task/output contract.
- Calls per base item: one sender and one receiver.

This arm separates benefit from public-state projection from benefit specific
to the Urusilla record.

### 7.5 `static_urusilla`

- A model sender sees the same complete public history.
- Both sender and receiver are unfamiliar cold contexts and receive the exact
  current `urusilla_action_state_capsule.json`, bounded SGD task context, symbol
  table, and output contract. Every model-visible copy is counted.
- The sender emits one canonical
  `urusilla-public-action-state-draft/1` record with all nine required fields.
- The record uses act `assert`, a goal bound to the arm-neutral opaque item
  digest, null action and outcome, and explicit public-state atoms.
- The minimum frozen symbol table contains only the generic definitions needed
  for the task: next-action goal, service, user action, active intent, requested
  slot, slot values, and the no-external-effect constraint. Definitions include
  argument types, meaning, source rules, and allowed effects.
- Every atom and hard constraint preserves explicit negation, null, provenance,
  and source order as required by the Capsule.
- The deterministic `PublicActionState` and task-context validators run before
  receiver delivery. Validation consumes zero model tokens but its latency is
  recorded.
- The receiver consumes the validated record directly. It is not expanded to
  natural language or ordinary JSON before the model call.
- Calls per base item: one sender and one receiver, before any repair or
  fallback.

The exact task context, symbol table, predicate mapping, source identifiers, and
canonical example are frozen before inference. Any task-required meaning that
cannot be represented produces `unsupported`; it is not silently omitted.

## 8. Information boundary and arm comparability

For every pair, sender source bytes, receiver task, output contract, model,
chat template, context limit, output limit, seed, timeout, tool policy, scorer,
and repair cap are matched across applicable arms.

Projected-message receivers receive the sender's actual output. They do not
receive raw source text, a gold state, a hidden paraphrase, a post-hoc corrected
message, or future turns. Deterministic parsing and validation may reject or
route a message but may not invent task content.

Preflight produces an arm-comparability manifest with one arm-neutral list of
task-required facts. Every projected sender and receiver receives its complete
arm grammar or schema. Demonstrations are either absent from every projected
arm or are renderings of the same frozen semantic example with the same example
count. Any item binding is one opaque fixed-length digest supplied identically
to every arm and contains no corpus, service, dialogue, or turn identifier. The
single repair allowance is per arm/item episode and is spent on the earliest
malformed model output in temporal order.

Arm order is counterbalanced with a deterministic five-arm rotation. For
selected item position `i` beginning at zero, rotate
`[full_history, compact_terse_english, canonical_minified_json,
clean_action_state, static_urusilla]` left by `i mod 5`. Model state is reset
between arm episodes. Order never changes the sample or prompt.

## 9. Model and runtime conditions

### 9.1 Model order

1. `Qwen/Qwen2.5-7B-Instruct` at source revision
   `a09a35458c702b33eeacc393d103063234e8bc28`;
2. `mistralai/Mistral-7B-Instruct-v0.3` at source revision
   `c170c708c41dac9275d15a8fff4eca08d52bab71`, only after Qwen promotion.

Each model runs same-model sender/receiver self-play. No cross-family result is
claimed by this P0.

### 9.2 Local inference configuration

- local 4-bit `Q4_K_M` quantization derived from the pinned source revision;
- exact source-weight, GGUF, tokenizer, and chat-template SHA-256 values recorded
  before execution;
- exact `llama.cpp` revision and build flags recorded before execution;
- context cap: 4096 model tokens, with no truncation;
- sender output cap: 512 model tokens;
- receiver output cap: 128 model tokens;
- temperature: 0;
- greedy decoding with all remaining decoding controls explicitly frozen;
- generation seed: `20260823` even when the runtime's greedy path ignores it;
- no tools, retrieval, web, grounding, external memory, or cross-episode state;
- one independent cold context for every arm/item episode;
- one frozen timeout for all arms on a model; and
- exact runtime token count plus an independent tokenizer recount.

An input that exceeds the context cap is a retained context-limit failure. It is
not truncated or given a larger cap after comparison.

The quantized P0 result is bounded to the exact quantization and local runtime.
It is not a BF16 result.

## 10. Repair and fallback policy

Every repair and fallback call is model-visible, capped, and counted.

- At most one format-only repair is allowed per arm/item episode.
- The repair prompt may identify the violated output-shape rule and include the
  actual invalid output, but it may not reveal missing semantic fields, gold
  state, gold actions, or a corrected answer.
- A remaining terse, ordinary-JSON, or clean-action-state failure is an
  unsuccessful episode; it receives no cross-arm rescue.
- A remaining static-Urusilla sender validation, unknown-symbol, unsupported,
  or receiver-format failure takes one frozen canonical-JSON fallback chain.
- The fallback sender sees only the same original public history. The fallback
  receiver sees only the resulting JSON payload.
- A successful fallback may safely complete the task, but it does not count as
  Urusilla typed-message semantic success. Its complete Urusilla attempt,
  repair, fallback, and final-answer cost remains in the static-Urusilla ledger.
- No second repair, second fallback, manual edit, or operator-selected answer is
  allowed.

The base plan uses nine calls per item: one for full history and two for each of
the four sender/receiver arms. Twenty items therefore use 180 base calls per
model before conditional controls, repairs, or fallbacks.

## 11. Full model-visible token ledger

### 11.1 Primary total

For arm `a` and episode `i`:

```text
T_i,a = sum over every actual model call (
    complete rendered input tokens
  + complete visible output tokens
)
```

The rendered input includes chat-template, role, system, task, format, Capsule,
example, history, sender payload, repair, and fallback tokens exactly as seen by
the model. No token occurrence may be omitted because it was cached, repeated,
shared with another experimental arm, or helpful to more than one task.

The ledger has two independently reconciled, non-additive views. Each view must
sum exactly to `T_i,a`; the two view totals are never added together.

The **call-purpose view** assigns every complete call to exactly one of:

1. `base_sender`;
2. `base_receiver`;
3. `repair_retry_clarification`;
4. `fallback`;
5. `validation_and_comprehension_test` for the conditional causal calls;
6. `encode_decode_model` for any model translation or conversion call;
7. `negotiation_profile` for compatibility, adoption, or profile transfer;
8. `safety_filter` for a separate model-visible safety check;
9. `tool_request` or `tool_result`, both required to be zero; or
10. `unclassified_call`, which must be zero for a complete-ledger result.

The **token-content view** assigns every rendered input and visible output token
occurrence to exactly one of:

1. `system_role` — chat-template, system, role, delimiter, and stop-prefix
   tokens;
2. `task_input` — fixed task instruction and item-specific task material;
3. `format_induction` — arm grammar, schema, Capsule, task context, symbol table,
   examples, and canonical-output teaching;
4. `agent_input_history` — raw public dialogue history;
5. `agent_input_message` — an actual sender payload, invalid prior output, or
   other visible intermediate message delivered to a later call;
6. `agent_output_visible` — visible sender or other nonterminal model output;
7. `final_answer` — the receiver's terminal visible output, including a terminal
   output produced on a fallback call;
8. `hidden_reasoning_billed` — required to be zero for the declared local
   runtime unless separately observable in the runtime count; or
9. `unclassified_token`, which must be zero for a complete-ledger result.

Repairs, fallbacks, and causal controls are therefore explicit in the
call-purpose view while their actual prompts and outputs remain fully
partitioned in the token-content view. Sender-input, sender-output,
receiver-input, and receiver-output subtotals are additional overlapping
diagnostic views and are not added a second time.

For every call, store:

- complete rendered-prompt SHA-256 and output SHA-256;
- runtime and independently reconstructed input/output counts;
- category partition and reconciliation status;
- sender/receiver identity, model, arm, item, attempt, repair/fallback flags;
- latency, timeout, malformed, refusal, and context-limit status; and
- cold Capsule/profile tokens separately within `format_induction`.

Any runtime/recount disagreement or nonzero `unclassified` count makes the
headline metric ineligible until resolved without changing observed output.

### 11.2 Causal-control accounting

If conditional causal controls run, all eight additional receiver calls are
assigned to `validation_and_comprehension_test` in the call-purpose view. Their
complete inputs and outputs are also partitioned in the token-content view and
included in the primary static-Urusilla 20-task session cost. The other eight
negative-control outcomes are deterministic pre-receiver validation decisions
with zero model tokens; their latency and exact reason codes are retained. Any
receiver call after one of those deterministic rejections is a protocol
failure. The operational total without research-control calls is reported as a
secondary diagnostic and may not replace the conservative primary total.

The deterministic scorer uses no model and has zero judge tokens. Adding a model
judge is outside this protocol.

## 12. Semantic and task scoring

### 12.1 Sender semantic fidelity

For each model-generated sender output, its arm parser produces a common typed
projection and compares it with the preceding user turn's frozen gold frames.
Required fields are:

- service identity and frame order;
- ordered user actions;
- action act, slot, and canonical values;
- active intent when present;
- requested slots in source order;
- complete slot-value mapping and value order;
- explicit correction, negation, unknown, null, or absence distinctions exposed
  by the frozen source;
- public provenance/source ownership; and
- the no-external-effect constraint where the arm carries constraints.

`sender_semantic_exact` is true only when every required field matches. Macro
field accuracy and the worst field are reported, but cannot override exactness.

### 12.2 Receiver task success

`receiver_target_exact` is true only when the canonical receiver envelope equals
the frozen ordered next-action target byte for byte after the one allowed
canonical construction. Parser failure, an omitted or extra action, wrong
service or slot, wrong order, prose, refusal on a valid item, or non-canonical
JSON is false.

### 12.3 Safe task success

For a projected-message arm, define `delivered_state_semantic_exact` as exact
semantic fidelity of the state actually delivered to the successful receiver
route. It equals `sender_semantic_exact` on the ordinary typed route.

Then:

```text
safe_task_success =
    delivered_state_semantic_exact
  AND receiver_target_exact
  AND no authorization, privacy, provenance, or integrity violation
  AND no unauthorized external effect
```

For `full_history`, the sender term is replaced by exact deterministic source
relay.

For static Urusilla, define the stricter primary event:

```text
native_safe_task_success =
    exact validated Urusilla sender record
  AND exact safe receiver answer on the typed-U route
  AND safe_task_success
```

An exact canonical-JSON fallback may set the separately reported
`operational_safe_task_success` true when its delivered state and answer are
exact and safe, but it can never set `native_safe_task_success` true. Every
failed native attempt, repair, fallback, and final answer remains charged to
the static-Urusilla numerator.

All failed, malformed, refused, timed-out, repaired, fallback, and unsafe
episodes remain in the retained item set and full token numerator. Failures
contribute zero to the relevant safe-success denominator and remain in the
denominators of failure-rate reports. If a baseline has zero safe successes, or
static Urusilla has zero native safe successes, its headline cost is infinity.

## 13. Primary and secondary metrics

For each baseline arm `b` and the static-Urusilla candidate over the retained
items:

```text
C_b = sum_i(T_i,b) / sum_i(safe_task_success_i,b)
C_U = sum_i(T_i,U) / sum_i(native_safe_task_success_i,U)
```

The primary candidate is `static_urusilla`. The four co-primary fixed
comparators are full history, compact terse English, canonical minified JSON,
and clean action-state. Results against all four are published; post-hoc
selection cannot hide one unfavorable comparison.

Every mandatory comparator must have zero unsafe false accepts, a complete
reconciled ledger, no integrity stop, at most `1/20` malformed plus
unrecoverable episodes, and at least `19/20` safe successes. If any comparator
is ineligible, report baseline-reliability failure and make no every-baseline or
positive P0 result. The strongest baseline is the eligible comparator with the
lowest `C_b`. The observed all-baseline point reduction is:

```text
reduction = 1 - urusilla_tokens_per_safe_task
                  / strongest_baseline_tokens_per_safe_task
```

For uncertainty, define `R_b = 1 - C_U / C_b` and
`R_all = min_b(R_b)`. Use 10,000 shared paired-bootstrap resamples with seed
`20260823`. Partition the observed `corpus_id` clusters into the one-item and
two-item cluster-size strata, then sample the original number of clusters with
replacement inside each stratum. Every replicate therefore contains exactly
20 paired items and retains every base-arm row, repair, and fallback belonging
to each sampled cluster. Baseline eligibility is fixed from the observed result
and is not reselected inside a replicate. In the post-causal
analysis, the observed total model-token cost `T_C` of the fixed eight receiver
calls is added exactly once to the Urusilla numerator in every replicate; it is
not duplicated or omitted when an originating cluster is resampled. Control
origin IDs remain in the trace but do not change that fixed session-overhead
treatment. Compute a one-sided 98.75% lower percentile bound for each of the
four `R_b` values, giving Bonferroni familywise 95% coverage, and define
`L_all` as their minimum. Undefined replicates are retained conservatively as
negative infinity. This interval treats observed fixed-control overhead as a
session constant and estimates task-cluster variation only.

Secondary metrics are:

- native and operational safe task-success counts and paired differences;
- sender semantic exactness and macro/worst-field accuracy;
- receiver target exactness;
- canonical parse failure, valid false refusal, unsafe false accept, repair,
  fallback, timeout, and context-limit rates;
- input/output and sender/receiver token subtotals;
- Capsule/profile share of total tokens;
- p50/p95 model and end-to-end latency;
- peak resident memory and swap observation; and
- UTF-8/wire bytes as a separate non-headline axis.

Wire-byte reduction never substitutes for model-visible token reduction.

## 14. Zero-call material-impossibility screen

The zero-call screen runs only after every source-known prompt and every
dependent-prompt template, renderer, derivation rule, dynamic-slot bound,
parser, validator, output cap, and tokenizer has been registered.

For each selected item:

- `L_U^S(i)` is a proved lower bound on the complete native-U token cost of a
  native safe success, including the receiver input rendered from the minimum
  valid sender output;
- `L_U^F(i)` is a proved lower bound on every retained native-failure path that
  remains compatible with the final `19/20` gate, including any mandatory
  repair or fallback on that path;
- `U_b(i)` is a proved upper bound on every allowed baseline path, including
  base inputs, complete sender and receiver output caps, the maximum sender
  payload re-tokenized inside the receiver input, the one permitted repair,
  and the capped invalid output copied into its repair prompt; and
- `L_C` is a proved lower bound on all eight mandatory causal receiver-call
  inputs and outputs because those calls remain in the positive endpoint's
  primary total; deterministic rejection decisions add zero model tokens.

Every bound includes the chat template and cold format-induction tokens. The
preflight program enumerates every allowed execution-state path and mechanically
verifies the relevant inequalities; a merely plausible or gold-constructed
string length is not accepted as a bound.

Define:

```text
LB_U = min over F subset I, |F| <= 1 of
       (sum_{i not in F} L_U^S(i) + sum_{i in F} L_U^F(i) + L_C)
       / (20 - |F|)

UB_b = sum_i U_b(i) / 19
UB_B = min over the four mandatory baselines b of UB_b
```

The candidate minimization permits either perfect native success or the one
native failure still compatible with the reliability gate. The baseline
denominator 19 and per-item maxima give every mandatory baseline the most
candidate-favorable cost still compatible with that gate. If any allowed path,
dynamic slot, repeated sender payload, repair, fallback, or causal call lacks a
proved finite bound, the impossibility screen is disabled and cannot stop the
model run.

If:

```text
LB_U > 0.80 * UB_B
```

then the current cold static configuration cannot achieve the preregistered 20%
point-reduction promotion threshold under the exact output caps even with
perfect first-pass Urusilla behavior and maximally verbose eligible baseline
outputs. The
token-optimization branch stops with zero model calls. Safety/conformance work
may continue separately and no task-success conclusion is drawn.

Passing this screen is only absence of a deterministic impossibility result. It
is not evidence of saving or comprehension.

## 15. Fixed execution boundaries and stopping rules

There is no unplanned repeated peeking. Decisions occur only at the zero-call,
10-item, 20-item, and conditional-causal boundaries.

### 15.1 Immediate integrity and safety stop

Stop the affected model/arm, preserve all artifacts, and do not substitute an
output if any of the following occurs:

- unauthorized external effect or attempted tool execution;
- private field, raw hidden prompt, or hidden reasoning disclosure;
- invalid executable content bypasses fail-closed routing;
- source, item, prompt, model, tokenizer, runtime, schema, Capsule, scorer, or
  manifest digest changes;
- gold frames or future turns enter a model-visible input;
- paired arms receive different source facts or effective generation caps;
- model context is silently truncated;
- complete token-ledger reconstruction fails; or
- a result is manually edited or selected from multiple unregistered attempts.

### 15.2 Qwen 10-item boundary

After all five arms complete the first 10 selected items:

1. stop for reliability futility only if static Urusilla already has two native
   failures, or any mandatory baseline already has two safe-task failures and
   therefore cannot reach `19/20`;
2. treat one native-U failure or a one-item success deficit as a warning, not
   futility;
3. stop if any safety or integrity stop has occurred; and
4. compute a frozen joint favorable-completion bound for the remaining 10
   items.

The conditional economic bound retains the observed first-10 token totals and
successes. For the remaining items it enumerates every native-U
success/failure pattern still compatible with the final gate using `L_U^S` and
`L_U^F`, and every mandatory baseline path using `U_b`. It includes the
mandatory causal lower bound `L_C`, repeated sender payloads, and permitted
repairs. Stop only if that joint most-favorable completion still satisfies
`LB_U^(20|10) > 0.80 * UB_B^(20|10)`.

All 10-item results remain reportable exploratory evidence.

### 15.3 Qwen 20-item task/token gate

After 20 items, Qwen is eligible for conditional causal controls only if all of
the following hold:

- zero unsafe false accepts and zero unauthorized effects;
- complete reconciled token ledgers;
- static-Urusilla malformed plus unrecoverable count at most `1/20`;
- static-Urusilla native safe successes at least `19/20`;
- every mandatory baseline passes the Section 13 reliability gate;
- point reduction at least 20% against the strongest mandatory baseline; and
- the familywise lower bound `L_all` is above zero.

The Section 13 bootstrap uses 10,000 shared, cluster-size-stratified resamples,
seed `20260823`, and keeps every base item, repair, and fallback from one
`corpus_id` together while preserving exactly 20 items per replicate. Causal
origin metadata remains bound in the trace, but its model-token cost is the
fixed `T_C` session overhead and is never cluster-resampled. With only 20 items,
the familywise interval is an exploratory stability screen and cannot establish
the parent protocol's one-percentage-point confirmatory non-inferiority
hypothesis.

A positive point reduction below 20% is reported as a bounded non-material
signal and does not promote this token branch. A familywise bound crossing zero
is a null pilot result, not a saving claim. A point reduction of at least 20%
together with `L_all > 0` supports promotion only; it is not evidence that the
true reduction is at least 20%. Material evidence would require the lower bound
itself to reach 20% on the untouched parent-protocol split.

### 15.4 Mistral promotion

Mistral runs only after Qwen passes the 20-item task/token gate, all Qwen causal
controls, and the final post-causal token gate in Section 16.3. It uses the
same selected items, arm order, prompts, output contracts, caps, stop rules,
and causal generator, with only the frozen model, tokenizer, and chat-template
identities changed.

This P0 is positive only if Mistral independently passes the same pre-causal
task/token, causal, and final post-causal token gates. A Qwen pass and Mistral
fail is retained as model-specific evidence and blocks a two-family
native-consumption claim.

## 16. Conditional causal payload controls

Causal controls run only after a model's 20-item static-Urusilla base result
otherwise passes. They do not tune prompts or retry policy.

### 16.1 Deterministic control-item selection

Before the first base-model call, enumerate the 20 selected items and choose the
four lowest-`H(pair_id)` items for which a frozen executable dialogue-policy
rule can construct a schema-valid task-critical state change and derive exactly
one changed next-action target. Service-schema validity alone is insufficient.
The rule must emit one canonical target from a finite declared candidate set
and a machine-checkable uniqueness certificate. An item with zero or multiple
valid targets is excluded. Record the complete qualification set and its size
before selecting the first four. If fewer than four qualify, the causal gate
cannot pass and no direct-consumption interpretation is eligible.

The rule ID and bytes, source schema revision and digest, exact rule inputs,
candidate set, uniqueness certificates, four IDs, original targets,
intervention fields, altered targets, and all variant bytes are frozen before
the first base-model call.

### 16.2 Four additional variants per item

Each selected item adds four outcomes with identical non-payload context and
settings. Only the first two are receiver calls:

1. **Critical flip:** change one declared task-critical field while keeping a
   valid Urusilla record; the expected action changes according to the frozen
   intervention oracle.
2. **Task invariant:** change only a declared task-irrelevant trace or
   uncertainty field; the expected action remains the original target.
3. **Missing required payload:** remove the task-bound required state. The
   frozen task-context validator must reject it with the preregistered reason
   code before receiver delivery; expected receiver-call count is zero.
4. **Shuffled/mismatched payload:** insert another selected item's otherwise
   structurally valid payload while retaining the original non-payload binding.
   The frozen binding validator must reject it with the preregistered reason
   code before receiver delivery; expected receiver-call count is zero.

The task context must declare the task-irrelevant field used by the invariant
before base inference. No unknown field is introduced merely to make a control.
No model prompt contains a variant label or expected outcome, and all
non-payload bytes are identical across the four variants of one item.

The gate requires `16/16` exact expected outcomes: `8/8` receiver answers with
the declared change or invariance and `8/8` deterministic pre-receiver
rejections with no model call. Validator acceptance of a negative control, any
receiver call after its rejection, or rejection of either positive control is
a gate failure. A receiver that always abstains cannot pass because the valid
base items and accepted controls require exact actions.

This `16/16` rule is a zero-tolerance mixed validation/receiver regression gate
over four item clusters, not an estimate of causal success rate or evidence
about the model sender. It supports no confidence interval or generalization
beyond the frozen controls. End-to-end native use is established only by
`native_safe_task_success` on actual sender outputs. Passing does not reveal or
prove a particular hidden model representation or human-like understanding.

### 16.3 Final post-causal token gate

Passing `16/16` causal outcomes is necessary but not sufficient for promotion.
Sum the eight causal receiver calls into observed fixed session overhead `T_C`
exactly once, retain their origin bindings in the trace, and recompute the
Section 13 primary static-Urusilla total over the same 20-task
native-safe-success denominator. Then rerun the strongest-mandatory-baseline
point reduction and the familywise dialogue-cluster bootstrap with `T_C` added
once to every replicate.

Final promotion requires the post-causal point reduction to remain at least
20% and the recomputed familywise lower bound `L_all` to remain above zero. If
causal-control overhead erases either threshold, report semantic causal
feasibility without a material token-saving result and stop that model branch.
No operational-only subtotal may replace this conservative final decision.

## 17. Expected call, time, storage, and monetary budget

The estimates below target the current operator machine observed during
planning: an Apple M1 MacBook Air with 8 GB RAM. Actual runtime, memory, swap,
and energy observations must be reported; these estimates are not results.

| Boundary | Base model calls | Conditional calls | Expected elapsed time after setup |
| --- | ---: | ---: | ---: |
| Zero-call preflight | 0 | 0 | 15-30 minutes |
| Qwen first 10 items | 90 | repair/fallback only | 1-2 hours |
| Qwen full 20 items | 180 | 8 causal receiver calls plus 8 deterministic decisions after gate | 2-4 hours total inference |
| Mistral continuation | 180 | 8 causal receiver calls plus 8 deterministic decisions after gate | additional 2-4 hours |

Per model, the planned base-plus-causal count is 188. A global per-model hard
cap of 208 calls reserves at most 20 repair/fallback calls. Reaching the cap
stops that model; it is not raised after inspecting outcomes. The two-model
absolute cap is 416 calls.

Expected one-time preparation is 2-5 hours for runtime build, local acquisition,
quantization or verified converted-weight acquisition, and digest checks. Each
4-bit model is expected to require approximately 4-6 GB retained storage;
source-weight conversion may require substantially more temporary storage.

Expected paid/provider cost is exactly USD 0. Network acquisition cost, local
electricity, operator time, and hardware depreciation are not converted to
zero. Energy is not claimed unless separately measured.

The expected decision time is:

- 15-30 minutes after assets if the deterministic impossibility screen stops;
- approximately half a working day through the full Qwen decision on the
  current machine; or
- approximately one working day or an overnight run through both models.

Memory pressure or swapping on the 8 GB host is a reportable limitation. An
out-of-memory or context failure is retained rather than silently moved to a
larger unregistered machine.

## 18. Result interpretation

### 18.1 Negative or stopped result

A zero-call, 10-item, 20-item, causal, or Mistral stop falsifies promotion of the
**exact current cold static configuration** under this bounded task and runtime.
It does not prove that every possible Urusilla profile, task-aware router,
verified-silence policy, warm routine, state delta, trained model, or future
architecture must fail.

A task-success pass with no positive token interval is semantic feasibility
without demonstrated token value. A token reduction with failed safety or task
gates is ineligible.

### 18.2 Positive P0 result

Passing both local models and all causal controls confirms only that this exact
configuration deserves the parent protocol's larger untouched local pilot. It
does not confirm general-dialogue efficiency, material saving on two task
families, cross-family sender/receiver portability, or independent reproduction.

## 19. Explicit nonclaims

This document and any P0 result under it do not establish:

- that an experiment has already run;
- general, universal, or ordinary-dialogue efficiency;
- the parent protocol's confirmatory H1, H2, H3, H4, H5, or H6;
- performance on CaSiNo, BEGIN, QMSum, MultiWOZ, ClarifyBench, or another SGD
  revision;
- BF16 or unquantized-model performance;
- off-diagonal cross-model communication;
- lossless reconstruction of source prose;
- that action-state projection benefit is Urusilla-specific;
- deployment safety, security certification, adoption, organic propagation, or
  independent implementation;
- lower latency, cost, energy, memory, or wire bytes from lower model tokens;
- a standard, state-of-the-art result, or competitive lead; or
- authority to install, persist, spend, publish, message, call a tool, or cause
  any external effect.

The study is project-authored and project-operated unless a later report proves
otherwise. Null and adverse results remain first-class outcomes.

## 20. Required local artifacts and report fields

If execution occurs, the local evidence bundle must contain:

- execution and sample manifests with complete digest closure;
- source/license and model/runtime identities;
- exact rendered prompts and output hashes;
- raw per-call and per-episode token ledgers;
- every invalid, refused, repaired, fallback, timeout, and stopped observation;
- deterministic scorer outputs and causal-variant results;
- per-arm safe successes, token totals, tokens per safe task, and confidence
  intervals;
- 10-item and 20-item gate decisions, including favorable completion bounds;
- actual call counts, latency, memory, swap, disk, and operator elapsed time;
- actual monetary cost and an explicit statement when energy is unmeasured; and
- a result-boundary statement repeating the applicable nonclaims.

No private chain-of-thought, secrets, credentials, raw hidden prompts, or
unauthorized third-party publication is required.

## 21. Suggested minimal cross-links (not applied)

No existing file is modified by this preregistration. If maintainers later
choose to link it, the minimal changes are:

- in `GENERAL_DIALOGUE_EVAL_PLAN.md`, add one sentence after the P0.2 matrix row:
  `The first cost-guarded SGD slice is preregistered in
  GENERAL_DIALOGUE_P0_SGD20_PREREGISTRATION.md.`
- in `URUSILLA_GENERAL_DIALOGUE_RESULTS.md`, add one sentence after the SGD gold
  action/state oracle limitations:
  `A no-run real-model follow-up protocol is available in
  GENERAL_DIALOGUE_P0_SGD20_PREREGISTRATION.md.`

Those proposed links are navigation only. They would not change the frozen
prior result, imply that this P0 ran, or upgrade any claim.
