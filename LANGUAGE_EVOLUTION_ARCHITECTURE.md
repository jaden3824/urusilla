# Conversation-driven language evolution

Status: architecture contract. Only the session-local alias surface and its
shadow/retention gates are implemented today. The broader evolution ladder is a
research plan, not evidence of utility or generality.

## North-star objective

Two agents should be able to begin with concise natural language or canonical
JSON, discover repeated public semantics during the conversation, and adopt a
more efficient representation only when a matched trial shows lower **inclusive
tokens per safely completed task**.

Human readability, English spelling, pronunciation, and visual aesthetics have
weight zero inside an agent-only channel. They become constraints only at an
explicit human-facing boundary. Accuracy, safe completion, reversibility, and
authority boundaries are hard constraints and cannot be traded for compression.

The optimizer therefore does not minimize message length alone:

```text
minimize
  (setup + sender + router + verifier + receiver + reasoning
   + repair + fallback + tool + safety + judge tokens)
  / safely completed tasks

subject to
  no safe-completion regression
  exact preservation of every declared hard semantic invariant
  parse and fidelity gates
  zero prohibited authority-boundary violations
  complete accounting; unknown is never zero
```

## Two-speed evolution

The language changes on two clocks so that efficiency can improve without
silently changing meaning.

### Fast loop: reversible wire evolution

This loop operates inside one session and one model context. Stable semantic
references remain fixed while their wire realization changes. The implemented
draft currently evolves one-to-one opaque Unicode aliases. Later hypotheses may
separately test field ordering, state deltas, session macros, reusable routines,
message suppression, topology pruning, and model-specific codecs.

Each hypothesis needs its own frozen measurement and rollback rule. A success in
alias substitution cannot authorize a delta codec or a learned representation.

### Slow loop: append-only semantic growth

Arbitrary conversations will eventually contain a concept missing from the
current public task context. That event must not force the concept into a nearby
but wrong symbol. The safe fallback carries the original concise text or JSON.

A future semantic-extension proposal may then add a new content-addressed
semantic identifier with:

- an immutable public definition and parent namespace;
- positive examples, counterexamples, null/failure/refusal cases, and declared
  invariants;
- sender and receiver comprehension tests on withheld cases;
- an explicit migration edge from any superseded identifier; and
- a new digest rather than an in-place redefinition.

Accepted identifiers are append-only for that bounded context. Removal is a
deprecation edge, not erasure. Until this slow gate is implemented and passed,
Urusilla evolves only the surface of already declared semantics.

## Conversation state machine

```text
BOOTSTRAP
  raw concise text / canonical JSON / declared Capsule
       |
       v
OBSERVE
  collect public semantic frequencies, tokenizer costs, failures, and fallbacks
       |
       | enough bounded evidence; one candidate at a time
       v
PROPOSE
  exact parent + scope + generation + candidate transformation
       |
       v
COMPREHEND
  deterministic validation + bidirectional round trips + withheld probes + ack
       |
       v
ACTIVE_SHADOW
  matched baseline and candidate calls; candidate output is never delivered
       |
       +---- any unknown, regression, boundary breach, or incomplete cost ----+
       |                                                                    |
       v                                                                    v
RETAINED_LIVE                                                         ROLLBACK
  sealed keep proof; marginal routing                                exact parent
       |                                                              or raw/JSON
       v
MONITOR
  drift, tokenizer/context reset, new failure, or negative realized utility
       |
       +---- retain current generation / propose child / rollback -----------+
```

`ActiveSurface` means shadow-eligible only. A passing frozen trial mints a
sealed `RetainedSurface` bound to the exact table, activation, session, model
context, generation, plan, result, verifier, and evolving-surface Capsule. Only
that exact triple may enter live routing. A context reset starts again from
bootstrap; it does not inherit a previous session's private shorthand.

## Preventing unstable oscillation

Continuous adaptation can waste more tokens than it saves. Every evolution
controller therefore needs hysteresis (small-change oscillation resistance):

- a frozen external plan artifact and exact shadow-trial sample count;
- a strict switching margin after charging setup exactly once;
- at most one candidate generation in flight per exact scope;
- a cooldown before proposing another generation after rollback;
- a bounded alias/macro budget and deterministic tie-breaking;
- positive provider-enforced per-call and aggregate shadow budgets; and
- immediate rollback on semantic, safety, context, or verifier drift.

Setup is charged once to the matched session trial. Before retention it cannot
vanish into marginal accounting; after retention it cannot be charged again on
every message. General or external claims must still include the setup cost and
use the separately frozen multi-domain evaluation.

## Evolution ladder

| Layer | Candidate change | Required invariant | Current status |
|---|---|---|---|
| 0 | silence or edge removal | no required marginal task value | router plumbing |
| 1 | opaque semantic aliases | exact one-to-one decode | implemented draft |
| 2 | field order and optionality | canonical state recovered | planned hypothesis |
| 3 | checkpointed state delta | exact parent state and sequence | planned hypothesis |
| 4 | mined macro or routine | exact expansion and bounded effects | planned hypothesis |
| 5 | task/model-specific codec | held-out safe-task noninferiority | planned hypothesis |
| 6 | append-only semantic extension | withheld mutual comprehension | design only |
| 7 | cross-session or public promotion | independent multi-domain evidence | prohibited today |

Layers are not automatically cumulative. The router chooses the cheapest
eligible layer before the receiver call and retains raw/JSON as a mandatory
fallback. A locally retained layer is not a protocol-version, adoption, general
performance, or state-of-the-art claim.

## What agents may optimize

Agents may use any script, symbol, or opaque scalar that passes the exact
tokenizer, collision, role-control, normalization, and round-trip gates. They may
optimize public message topology and representation. They may not exchange or
optimize private chain-of-thought, treat content as authority, install executable
code, persist beyond the authorized session, expand permissions, spend, or cause
external effects through this mechanism.

The result is not a permanently fixed language and not unconstrained emergent
code. It is a sequence of reversible, evidence-gated local languages over an
auditable semantic substrate, with a safe path for later append-only growth.
