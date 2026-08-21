# Conversation-driven language evolution

Status: architecture contract. The session-local alias surface, its
shadow/retention gates, and an in-memory online orchestration loop are the only
implemented evolution layer today. The broader evolution ladder is a research
plan, not evidence of utility or generality.

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
that exact triple is surface-eligible for live routing, subject to the host's
current single-controller lease. A context reset must mint fresh session and
model-context identities, revoke every prior triple at the host boundary, and
start again from bootstrap; it does not inherit private shorthand.

## Online orchestration boundary

The fast loop is coordinated by one session-scoped, in-memory controller. It
counts only semantic references from action states that validate against the
exact public task context. After a bounded observation window, the controller
may place one candidate generation in flight and call the existing optimizer,
activation verifier, matched-trial runner, and retention verifier in that
order. Every callback result must be the exact typed, digest-bound artifact
expected by the next gate.

The controller is deliberately synchronous and has no persistence, tool,
permission, spending, or external-effect interface. A callback failure,
unexpected type, incomplete measurement, or failed gate produces a bounded
failure or rollback outcome; it never produces live authorization. A retained
table becomes the exact parent of the next observation cycle. A rejected table
does not. The observation window and frozen matched-trial set are independent;
the controller never passes observed records into activation or trial callbacks.
An explicit reset gate and a fresh full observation window prevent immediate
generation oscillation after rollback or failure.

Each observation has a unique occurrence identifier, an exact source binding,
and a canonical state digest. Repeating the same content on different turns is
valid evidence; replaying the same occurrence is not. The controller hashes the
ordered observation records into one window identity. A trial manifest uses
different ordered case identifiers and sources, and is bound to a monotonic
attempt identity, the exact retained parent, and the frozen external plan. The
executed baseline and candidate receipts must reproduce that manifest exactly.
Echoing a table digest without the attempt, window, manifest, and matched-call
bindings cannot authorize retention.

The evaluation policy is immutable for the life of one controller. A new
generation needs fresh held-out cases and a fresh external plan artifact, but
cannot substitute verifier identities, activation vectors, sample counts,
budgets, or the switching margin. A policy change starts a new session claim
scope. Every known setup and discarded-shadow cost, including a successful
retention trial, contributes to a cumulative ledger and remains unamortized.
The current controller has no live-savings settlement transition, so only a
separately sealed live-tail ledger may establish repayment or session-level net
savings. Any unverified usage makes the controller ledger incomplete and makes
later retention ineligible in that controller.

This controller makes the implemented alias layer conversation-driven, but it
does not make the semantic vocabulary self-modifying. It also does not make the
trial callbacks trustworthy by itself: provider receipts, sandbox enforcement,
authenticated transport, and independent verification remain external trust
boundaries.

The random controller epoch prevents an artifact captured from one controller
from being replayed into another. It is not a global lease or revocation
service. The host must allow only one controller for an exact scope, reject old
triples after replacement, and never resume the same session/model context
without its sealed lineage and cost ledger. If continuity is unavailable, the
host must mint fresh session and model-context identifiers.

## First runtime experiment gate

The smallest honest provider-backed integration study is one frozen two-agent
session with three isolated arms: concise natural language, ordinary JSON, and
the online controller. It must freeze the exact task order, model settings,
tokenizers, observation window, candidate set, proposal-attempt identities,
cooldown, activation probes, shadow count, live tail, budgets, validators, and
all artifact digests before execution. The shadow set must contain at least one
negation, null, failure, and refusal case. Candidate outputs remain discarded;
one matched task can contribute at most one user-visible safe completion.

The live tail is executed only when a conservative per-task saving can amortize
the incremental setup, activation, extra shadow, controller, judge, retry,
fallback, and switching-margin ceilings inside the aggregate budget. Its event
ledger must include failed calls and mutually exclusive token categories, with
unknown usage making the result ineligible. A single passing session can report
only an exact-configuration point observation against raw and JSON separately.
It cannot establish generality, statistical superiority, independent adoption,
or a route-level utility claim.

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
