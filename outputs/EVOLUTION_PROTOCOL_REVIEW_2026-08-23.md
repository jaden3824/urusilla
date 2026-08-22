# Urusilla evolution-protocol research review

Status: independent design audit and preregistration proposal; no model run was
performed

Date: 2026-08-23

Repository snapshot: `34a1e5486a25f7979b050878803dcf686c686ae0`

Scope: the semantic kernel, public action-state runtime, session-local evolving
surface, routing/accounting contracts, and published evidence boundaries

Uncommitted website-only changes were present in the shared worktree during the
review. They were outside this audit. No protocol, runtime, test, release,
marketing, or deployment file was changed by this review.

## 1. Executive verdict

The original objective remains coherent, but the current implementation has
not yet reached it.

The objective can be stated operationally as follows:

> Previously unfamiliar agents should start from a mutually intelligible safe
> representation, learn a cheaper representation from their interaction, and
> continue to improve it only when inclusive tokens per safely completed task
> fall without semantic, causal, or authority-boundary regression.

Urusilla currently implements a credible **safety envelope for a narrow fast
loop**: a bounded task context fixes meaning, a central session controller
counts already validated semantic references, a deterministic optimizer
proposes one-scalar aliases, a separately frozen shadow trial decides whether
to retain them, and any missing binding or incomplete usage fails closed. This
is substantially stronger than unconstrained agents inventing private codes.

It is not yet an evolving general language. The implemented evolutionary move
is only one-to-one relabeling of identifiers inside one declared task profile.
Semantic extension, routine mining, delta selection, topology pruning,
cross-session learning, and public promotion remain separate experiments or
plans. Negotiation is represented by typed acknowledgements and externally
supplied callbacks, not by a demonstrated peer-to-peer bargaining exchange.
No real-model session has shown that the receiver causally uses the evolved
payload, that the full experiment cost is repaid, or that the result beats
concise language and JSON.

The correct research claim today is therefore:

> Urusilla has implemented fail-closed, session-local alias-evolution plumbing
> over stable bounded semantics. Its end-to-end utility, causal language use,
> and broader evolutionary scope remain unestablished.

The fixed semantic core is not itself a defect. Stable identifiers are what
make rollback and audit possible. The gap is that append-only semantic growth
and richer surface transformations have not been connected to the same
executable, measured loop.

## 2. Audit method and evidence boundary

This review treated repository prose as a claim only when an implementation,
test, or frozen result supported it. The principal sources were:

- `LANGUAGE_EVOLUTION_ARCHITECTURE.md` and
  `urusilla_evolving_surface_capsule.json` for the intended state machine;
- `urusilla_hybrid_runtime/evolution.py` and
  `urusilla_hybrid_runtime/surface.py` for the implemented fast loop;
- `urusilla_hybrid_runtime/records.py` and
  `urusilla_hybrid_runtime/task_context.py` for the current semantic boundary;
- `urusilla_hybrid_runtime/router.py`, `runtime.py`, and `session.py` for live
  routing, fallback, and accounting boundaries;
- `EVOLVING_SURFACE.md`, `RESEARCH_PROGRAM.md`,
  `CLAIM_EVIDENCE_MATRIX.md`, and the general-dialogue preregistration for
  explicit limitations; and
- the v0.7 receiver-profile, v0.8 fallback, v0.9 delta, and adaptive-dialogue
  reports for adjacent but non-equivalent evidence.

This was a design audit, not a security audit, statistical replication, or
provider-backed experiment. Existing deterministic unit tests show that the
gates behave as coded; they do not establish that callback receipts are true,
that a model understood a message, or that an independent agent adopted the
language.

## 3. Findings against the original objective

| Dimension | What is implemented now | Material limitation | Research verdict |
| --- | --- | --- | --- |
| Stable semantic core | Exact task-context and symbol-table digests; closed acts; canonical public action state; exact validation and round trip | The runtime accepts only a bounded, predeclared task vocabulary and primitive argument types. General typed dialogue exists in a separate fixture rather than the same live evolution loop. | Strong bounded substrate; not a general semantic inventory |
| Codec and grammar evolution | Frequency-weighted, parent-relative optimization of injective one-scalar Unicode aliases across bound tokenizers | Candidate aliases are supplied in advance. No implemented online field-order, optionality, delta, macro, learned-codec, topology, or semantic-extension transition | Implemented relabeling, not yet language-level evolution |
| Peer negotiation | Exact table, sender acknowledgement, receiver acknowledgement, comprehension flag, frozen plan, and artifact verification are required | The core does not perform capability discovery, counterproposal, mutual utility comparison, or authenticated peer exchange. Callbacks can be satisfied by same-project fixtures. | Strong activation contract; negotiation behavior unproven |
| Session adaptation | A session controller observes validated occurrences, keeps held-out sources disjoint, binds attempts to a random epoch and exact parent, and supports multiple generations | It learns only identifier frequencies from states that already exist. It does not infer new public semantics from conversation, learn from receiver errors, or share a retained surface across agents or sessions. One controller centrally decides. | Real but narrow online adaptation |
| Safe rollback | Unknown/stale aliases reject; shadow output cannot become live; a retained proof is required; unknown usage is sticky; rejected generations do not replace their parent | Host lease, revocation, authenticated transport, crash recovery, and live drift monitoring are external. There is no implemented settlement transition that proves live savings repaid accumulated trials. | Strong fail-closed core; deployment rollback incomplete |
| Inclusive token measurement | Trial records include activation, matched calls, prior unamortized overhead, repairs/fallback fields, safe completions, and unknown-usage rejection | Current controller evidence is synthetic. Provider authenticity, model reasoning/billing normalization, full observation-to-live settlement, and a real task judge are absent. Published general-task total remains unknown. | Measurement schema is promising; empirical endpoint missing |
| Meaning preservation | Exact decode/re-encode, task-context validation, fidelity artifacts, negative/null/failure/refusal gates, and per-message bindings exist | Structural equality does not prove that a compiler captured the source meaning or that a receiver used the payload. A constant-output receiver can pass current synthetic plumbing. | Codec fidelity is tested; source fidelity and causal comprehension are not |

### 3.1 Stable meaning versus evolving language

The architecture makes the right high-level separation:

1. existing semantic identifiers do not silently change;
2. a session may change only the reversible wire surface quickly; and
3. a new meaning should be introduced as a new content-addressed identifier,
   with migration and held-out comprehension evidence.

This is compatible with an evolving language. Evolution need not mean that the
meaning of an old word mutates. It can mean that agents add new definitions,
compose routines, omit redundant messages, or select a cheaper codec while old
records remain interpretable.

The current executable path stops after item 2, and even there only aliases are
implemented. The append-only semantic-growth path described in the
architecture is not joined to `OnlineEvolutionController`. Consequently,
describing the present runtime as a language that continuously invents useful
concepts would overstate it.

There is also a practical semantic split. The hybrid runtime's
`PublicActionState` has six acts and a task-local symbol table. The older
adaptive-dialogue fixture covers a much broader set of dialogue functions and
node kinds, but its lifecycle and positive fixtures are not the same
provider-backed runtime. Until one semantic substrate is chosen or an exact
bridge is tested, coverage in the broad fixture cannot be inherited by the
online alias controller.

### 3.2 What is and is not negotiated

The activation record requires both endpoint acknowledgements and a
comprehension pass. That is a good necessary condition. It prevents a table
from becoming live merely because one endpoint proposed it.

However, the interaction that produces those booleans is outside the core. An
activation callback can return a correctly bound record without demonstrating
that an unfamiliar receiver parsed a proposal, evaluated its own tokenizer and
cost horizon, rejected alternatives, or formed an independent acknowledgement.
The current unit tests intentionally use deterministic same-project callbacks.

The implemented mechanism is therefore best described as **artifact-gated
activation**, not yet demonstrated autonomous negotiation. A later experiment
should preserve the exact artifacts while making each acknowledgement the
output of a separately contextualized endpoint and counting that exchange.

### 3.3 Session adaptation is frequency adaptation

`OnlineEvolutionController` performs meaningful online work:

- it accepts only task-valid public action states;
- it distinguishes repeated occurrences from replayed occurrence IDs;
- it keeps observation and trial material disjoint;
- it freezes trial policy before observation;
- it proposes a generation from observed semantic-reference frequencies;
- it binds the generation to its exact parent and accumulated cost; and
- it cannot route the new surface live before a passing matched shadow trial.

These are valuable anti-overfitting and anti-replay properties. The learned
quantity is nevertheless only a frequency distribution. The candidate alphabet
and transformation family are fixed by the operator. Agents do not invent a
new routine, discover that a message is unnecessary, add a concept, or adapt
from a semantic misunderstanding. Calling this “conversation-driven” is fair;
calling it “self-evolving grammar” would not yet be fair.

### 3.4 Rollback is safer than retention is economical

The most mature part of the design is failure containment. Missing digests,
stale attempts, source overlap, verifier failure, incomplete cost, semantic
failure, unsafe authority flags, and non-positive inclusive advantage all
prevent retention. An unknown cost becomes permanently unknown for that
controller rather than being converted to zero.

The asymmetry is deliberate and appropriate: rollback can be demonstrated
locally, while a successful retained table still depends on an external host
lease and trustworthy receipts. More importantly, the controller retains all
trial overhead as unamortized and exposes no live-savings settlement method.
Therefore a retained table is permission to start a live tail, not evidence
that evolution saved anything over the whole session.

### 3.5 Total tokens and causal use are the decisive gaps

The repository correctly rejects message-surface reduction as a substitute for
task economics. The current decision record can compare inclusive tokens per
safe completion for a bounded shadow trial. Yet no current model-backed result
contains the complete chain from teaching and proposal through receiver answer,
repair, fallback, and final task score.

Even complete token receipts would not be enough. The receiver must change its
answer when a task-critical payload field changes and must refuse or fall back
when that field is missing or bound to the wrong table. Otherwise, a
constant-output or context-only receiver can appear successful. This causal
payload-use gate is the smallest missing scientific prerequisite.

## 4. Claim ladder after this audit

The following statements should remain separate:

1. **Implemented:** exact bounded semantics can be mapped through a reversible,
   session-scoped alias table with fail-closed bindings.
2. **Implemented with synthetic fixtures:** a central controller can observe,
   propose, shadow-test, retain or roll back, and carry prior cost forward.
3. **Not yet demonstrated:** two independently contextualized agents can
   negotiate that table and causally use it.
4. **Not yet demonstrated:** the full adaptive session consumes fewer tokens
   per safely completed task than concise language, JSON, and a fixed surface.
5. **Not yet implemented in the same loop:** agents can mine routines, select
   deltas or silence, or add a new content-addressed meaning from interaction.
6. **Not yet supported:** cross-session, cross-model, or public language
   evolution and general superiority.

Passing item 4 in one favorable session would justify a larger experiment. It
would not establish items 5 or 6.

## 5. Smallest executable falsification experiment

### 5.1 Protocol identity and purpose

Proposed protocol ID:
`urusilla-evolution-minifalsification-evo-min-1/1`

Purpose:

> Test whether the implemented session-local alias evolution can beat the best
> fixed safe representation in a deliberately favorable repeated-semantic
> receiver task, after charging teaching, negotiation, shadow calls, repair,
> fallback, and rollback, while proving that the receiver's output depends on
> task-critical payload content.

This is a mechanism screen, not a general-dialogue benchmark. It deliberately
uses repeated long semantic identifiers so that the implemented alias learner
has a plausible opportunity to win. Failure in this favorable setting is a
strong reason to stop spending on alias-only evolution. Success only permits a
larger multi-domain sender-and-receiver study.

### 5.2 Unit of analysis and agents

- One deterministic sender-runtime endpoint owns already validated public
  action states. This avoids conflating alias evolution with a separate
  natural-language compiler.
- One fresh receiver-model context per arm consumes the rendered message and
  returns one exact enum plus the referenced state digest.
- One pinned model, tokenizer, chat template, inference runtime, greedy decode,
  output cap, and hardware configuration are registered before any call.
- No arm shares hidden context, KV cache, generated output, or retry information
  with another arm.
- Case IDs, contrast labels, expected answers, and scorer metadata are never
  model-visible.

The deterministic sender makes this a receiver-side necessary-condition test.
It does not test model-generated messages and cannot support a full two-model
language claim.

### 5.3 Arms

Run four isolated arms over the same ordered cases:

1. `TERSE`: a frozen controlled-terse-English renderer;
2. `JSON`: canonical minified public action-state JSON;
3. `STATIC`: the same compact positional carrier with a table selected before
   the session from uniform semantic frequencies and then held fixed; and
4. `EVOLVE`: the current `OnlineEvolutionController`, using only the four
   observation cases to select its first table.

The candidate pool contains exactly two preregistered safe one-scalar aliases
for four aliasable long references. Both aliases must be strict one-tokenizer
wins of equal size against every eligible canonical label under the pinned
tokenizer; this equality is a zero-call eligibility check. The uniform static
rule therefore assigns a scarce alias budget by frozen lexical tie-breaking,
while `EVOLVE` can assign it by observation frequency. The two
observation-most-frequent references are deliberately not the first two lexical
references. This creates an adaptive contrast without selecting an alias from
model outcomes.

The required comparator is the lowest tokens per safe completion among the
three fixed arms. A baseline is eligible for that minimum only when it has zero
authority violations, complete usage, all scored tasks safely completed, and
both causal controls correct. Baseline failure does not become an Urusilla win;
if no fixed arm meets those requirements, the study is invalid and must be
redesigned under a new protocol ID.

The registered arm order is a SHA-256-seeded permutation. Every arm receives a
fresh receiver context. No output may be inspected before all prompt bytes,
renderers, cases, validators, and analysis code are frozen.

### 5.4 Frozen task stream

Use one synthetic decision task with four deliberately long, repeated semantic
references and an exact five-value output enum. Values and sources vary, but
the following 21 task positions and their expected answers are frozen before
execution:

1. **Observation, 4 tasks.** Four valid states exercise every repeated
   reference. In `EVOLVE`, these tasks are completed through the current safe
   parent representation while the controller observes the validated states.
   Their full cost and completions remain in the session ledger.
2. **Held-out shadow, 8 tasks.** Four matched A/B pairs change exactly one
   task-critical payload element:
   - asserted fact versus explicit negation;
   - non-null result versus `null`;
   - succeeded outcome versus failed outcome; and
   - request versus refusal.
   Correct outputs differ inside every pair. Each pair keeps all non-payload
   prompt bytes and settings identical.
3. **Live tail, 8 tasks.** If and only if the current retention gate keeps the
   table, run eight new-value and new-composition cases using the same four
   contrast families. Their case IDs and source digests are disjoint from the
   observation and shadow sets.
4. **Rollback drill, 1 task.** Replace one valid alias with an unknown scalar
   while preserving the outer binding. The optimized receiver call must not be
   made. Exactly one registered JSON fallback call must safely complete the
   task, and its full cost is charged to `EVOLVE`.

The shadow surface answers are discarded. The matched parent/baseline answers
are the only visible completions for those eight tasks. Both calls are charged
to `EVOLVE`.

The four A/B pairs jointly contain negation, null, failure, and refusal, so the
current hard preservation categories are exercised without adding redundant
model calls.

In every arm, run two additional blinded receiver-control calls under the same
non-payload instruction after the eight contrasts: one omits the payload and
one replaces every task-critical value with a registered `unknown`/`null`
control state. Both must return the exact abstention enum. These are diagnostic
calls, not safely completed task opportunities; their input, output, and any
repair cost are nevertheless charged to their arm. In `EVOLVE`, they run after
a `keep` decision but before the live tail. A failed evolving control triggers
rollback and stops the live tail. A fixed arm that fails either control is not
eligible to become `B`.

### 5.5 Pre-registration and execution freeze

Before the first model call, write a content-addressed manifest that pins:

- repository revision and dirty-patch digest;
- all 21 source states, task context, output targets, and contrast-pair map;
- observation, shadow, live, and rollback case/source digests;
- all four renderers and every model-visible prompt template;
- Capsule, alias candidates, uniform-frequency static-table rule, tokenizer
  counters, table optimizer, controller policy, switching margin, and verifier;
- the two causal-control prompts and exact abstention outputs;
- model and tokenizer artifact digests, chat template, runtime, decoding
  settings, context/output caps, timeout, and arm-order seed;
- repair and JSON-fallback prompts and their one-call limits;
- independent token accounting and task scorer; and
- the analysis script and this protocol document.

Any missing item, post-output change, case overlap, or digest drift makes the
run ineligible. A changed artifact requires a new protocol ID; it may not repair
the result silently.

### 5.6 Metrics

For arm `a`, define the complete model-token ledger:

```text
T_a = format induction
    + capability/alias negotiation
    + observation receiver calls
    + shadow parent calls
    + discarded shadow-surface calls
    + causal-control receiver calls
    + live receiver calls
    + configured reasoning tokens
    + every repair and fallback call
    + final-answer and judge tokens
```

Local deterministic validation, encoding, routing, and hashing use zero model
tokens but must report bytes, CPU time, and p50/p95 latency separately. A model
token category is zero only when the frozen trace proves no model call occurred.
Any unknown or unreconciled usage makes the arm ineligible and fails `EVOLVE`.

Let:

```text
S_a = number of safely completed tasks
C_a = T_a / S_a, with C_a = infinity when S_a = 0
B   = min(C_TERSE, C_JSON, C_STATIC)
R   = 1 - C_EVOLVE / B
```

A safely completed task requires all of the following:

- exact registered output enum and state digest;
- exact parse and declared semantic invariants;
- no valid-case repair or fallback in the native-success analysis;
- no persistence, permission, spending, or external effect; and
- an exact execution/request/usage binding.

Report safe completion both operationally and natively. A JSON fallback may
preserve operational safety, but it does not count as native evolving-language
success. All failed native attempts and fallback costs remain in `T_EVOLVE`.

Secondary exact metrics are:

- `round_trip_exact`: decoded state and canonical re-encode equality;
- `contrast_accuracy`: correct outputs for all eight A/B shadow cases;
- `pair_flip_accuracy`: all four pairs produce their two distinct registered
  answers;
- `placebo_abstention`: exact abstention on both missing/unknown controls;
- `surface_parent_invariance`: the surface and parent answers match for the
  same semantic state;
- `valid_false_fallback_rate`;
- `rollback_blocked_optimized_calls`; and
- per-stage tokens, bytes, latency, repair, fallback, and refusal counts.

No confidence interval or population claim is permitted from this fixed-N
screen. It is an exact mechanism test under one registered configuration.

### 5.7 Pass criterion

`EVOLVE` passes this pilot only if every condition holds:

1. its proposed table differs from `STATIC` on at least one semantic reference
   and has strict registered-tokenizer improvement over its exact parent;
2. the controller returns `keep` after the eight-case shadow trial;
3. round trip, parse, fidelity, pair-flip, contrast, and parent/surface semantic
   invariance are all `100%`, and both causal placebos abstain exactly;
4. the receiver correctly handles all eight live-tail cases without repair or
   fallback;
5. the rollback drill makes zero optimized receiver calls, makes exactly one
   registered JSON fallback call, and safely completes with no effect;
6. every usage field is complete and every authority-boundary count is zero;
7. `S_EVOLVE` equals the maximum eligible fixed-arm safe-completion count; and
8. `R >= 0.05` and the absolute advantage is at least one complete model token
   per safely completed task against `B`.

The five-percent threshold is a pilot progression margin, not a general
performance target. It prevents a one-token aggregate fluctuation from being
treated as a reason to expand the experiment.

### 5.8 Failure conditions

The bounded alias-evolution hypothesis fails under this configuration if any
of the following occurs:

- no observation-conditioned table differs from the fixed table;
- activation, acknowledgement, comprehension, or artifact verification fails;
- the retention decision is rollback for any reason;
- any valid semantic state decodes differently, is answered incorrectly, or
  falls back;
- any A/B answer fails to change as registered, or the receiver can succeed
  without the task-critical payload, including either placebo control;
- the unknown alias reaches the optimized receiver, fails to fall back, or
  causes an effect;
- adaptive safe completions are fewer than the best eligible baseline;
- usage is missing, duplicated, unreconciled, or reported as zero without a
  proved no-call event; or
- the final inclusive reduction is below five percent or below one token per
  safe completion.

If all three fixed baselines fail the simple exact task, the study is invalid,
not a positive Urusilla result. If a provider or runtime failure affects all
arms before a scorable answer, report `execution failure`, not a protocol win
or loss.

### 5.9 Stopping rule

The stopping rule is deterministic:

1. **Zero-call feasibility stop.** Render all fixed inputs and configured caps.
   If even the optimistic lower bound for `EVOLVE` cannot beat the maximum
   permitted total of the best fixed arm over the 21-task horizon, record
   `economic futility at N=21` and make no model call.
2. **Contrast stop.** If the observation-conditioned table is identical to the
   fixed table or has no strict parent-relative tokenizer improvement, record
   `no adaptive contrast` and stop before activation.
3. **Safety stop.** On the first semantic, binding, usage, or authority failure,
   stop the evolving arm, roll back, retain all spent cost, and do not tune or
   retry.
4. **Shadow and causal stop.** If the exact eight-case retention gate does not
   return `keep`, stop. If retained, run the two fixed causal controls; on
   either non-abstention, roll back and do not run the live tail.
5. **Fixed terminal stop.** If retained, run exactly eight live cases and one
   rollback drill, then stop. No extra tasks may be added to amortize a poor
   result, and no favorable prefix may replace the fixed endpoint.

There is one scored attempt. A second attempt requires a new protocol ID,
fresh disjoint cases, and disclosure of the first result.

### 5.10 Interpretation

A failure would falsify the practical value of the current **alias-only,
session-local mechanism at this favorable horizon and registered model**. It
would not falsify typed semantics, deltas, routines, topology pruning, trained
native representations, or longer sessions. The appropriate response would be
to pause alias-only expansion and move to a different transformation class.

A pass would establish only that one bounded receiver configuration repaid its
own evolution overhead while preserving observable semantics and causal
payload use. It would justify, but not replace, a preregistered study with:

- a model sender rather than a deterministic sender;
- independently authored multi-domain conversations;
- at least two model families and unseen pairings;
- negotiated routine, delta, silence/topology, terse language, JSON, and
  task-aware baselines; and
- paired uncertainty estimates for total tokens per safe task.

## 6. Research decision

Do not add more alias alphabets or tune general compact text before running
`EVO-MIN-1`. The repository already has enough deterministic safety plumbing.
The highest-value next datum is whether the present mechanism can survive one
small, favorable, causally controlled, fully charged model session.

If it fails economically but passes semantic and rollback gates, preserve the
safety machinery and change the evolutionary unit from identifiers to a
higher-leverage candidate: verified silence, a repeated routine, or a state
delta. If it fails causal use or meaning preservation, stop performance work
and repair the semantic/compiler/receiver contract first. If it passes, expand
only through a newly frozen multi-model protocol.

This ordering preserves the original objective: evolution is allowed to
continue, but only evidence—not novelty, traffic, or a shorter wire string—can
promote the next language form.
