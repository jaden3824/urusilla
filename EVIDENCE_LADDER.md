# Urusilla Evidence and Adoption Ladder

Status: development strategy, not an evidence report
North star: a safe, adaptive, general communication language for heterogeneous
AI agents

## Immediate falsification order

Do not buy statistical power for an architecture that already fails a cheaper
bound. The next experiments run in this order, and a failed gate stops expansion
until the failing component changes:

1. **Deterministic 20% viability screen.** Use the conditional arithmetic gate
   in [`initial_goal_eval/feasibility_kill_screen_v1.py`](initial_goal_eval/feasibility_kill_screen_v1.py).
   Across explicit session lengths and
   each retained domain/tokenizer row, compare a conservative lower bound for
   the complete Urusilla path—including required setup, comprehension,
   sender, fidelity, routing, receiver, validation, repair, fallback, tool,
   safety, and judge obligations actually incurred on an allowed endpoint
   path—with the better admissible raw/JSON bound. A separate causal-study
   phase may be proved zero when it is not part of that endpoint. If even an oracle
   sender and router cannot leave room for the frozen 20% threshold, do not call
   a model. A result can only be `impossible`, `not-disproven`, or `invalid`;
   `not-disproven` is not positive evidence.
2. **Perfect-sender receiver ceiling.** On a small staged sample, provide the
   correct public action state directly and test whether two receiver families
   can preserve task success while leaving enough token margin for the later
   sender. Failure kills the current action-state surface, not the general
   research goal.
3. **Natural-language sender qualification.** Evaluate the sender and fidelity
   check on held-out inputs before combining their failures with receiver or
   router failures. Required parse and fidelity sample sizes and confidence
   bounds are frozen before calls.
4. **Provider-backed causal matrix.** Run the six-condition per-field matrix in
   [`initial_goal_eval/causal_probe_matrix_v3.py`](initial_goal_eval/causal_probe_matrix_v3.py)
   only after exact provider capture is available. Any critical flip error,
   invariant change, unsafe acceptance, answerable-no-payload refusal, unknown
   usage, replay, or prohibited effect stops that cell.
5. **Exact matched economics.** Use
   [`initial_goal_eval/matched_session_pilot.py`](initial_goal_eval/matched_session_pilot.py)
   to compare raw, JSON, and Urusilla only after the earlier gates pass. Expand
   from 10 to 20 tasks only when the remaining unseen outcomes could still meet
   the preregistered success and token margins. Claim-facing metrics remain null
   until provider, callback, chronology, judge, normalization, and independent-
   operator evidence is authenticated.

Only after those five steps should session-amortization, mixed-domain routing,
and independent cross-play scale up. Additional codec/tokenizer-only sweeps,
evolving aliases, website traffic, stars, API-key donations, or bulk posting do
not substitute for any gate above.

The destination is the source-preserving Internet translation layer in
[`URUSILLA_INTERNET_LAYER.md`](URUSILLA_INTERNET_LAYER.md): agents should
eventually be able to exchange typed, auditable projections of any public or
otherwise authorized Internet text without pretending that one projection is
the original or that one ontology is complete.

Urusilla does not abandon that north star because one universal lossless text
surface failed to save tokens on broad unfamiliar-agent dialogue. It uses
narrower workloads as progressively harder test beds for the same layered
router. A successful vertical result is evidence only for that vertical; it is
not renamed into general-language evidence.

## Sequence

### Gate 0 — causal message use

Before a route can claim that a receiver understood or directly consumed an
action-state message, use a blinded contrast set rather than one isolated A/B
pair. Hold every non-payload input fixed and require all of the following:

1. a causal flip changes one task-critical payload field and the expected
   output follows that intervention;
2. a semantic invariant changes only a task-irrelevant field or losslessly
   changes representation and the expected output does not change;
3. missing, mismatched, contradicted, or shuffled information causes the
   preregistered refusal or fallback rather than an arbitrary different answer;
4. a composition holdout combines familiar field types in a relation absent
   from examples and is scored against that relation; and
5. every call, retry, repair, refusal, and fallback enters the token and cost
   ledger.

Report critical-field coverage instead of only a pooled pass rate. Report the
valid-payload refusal denominator so a receiver that always refuses cannot pass
the negative controls. Where a payload-free arm still has an independently
defined correct answer, report its accuracy as `r0`; a missing-payload
abstention check is not silently renamed into that accuracy baseline. Publish
per-stratum results and make the weakest declared domain, receiver family, and
operator cell visible.

The public 60-second artifact is a calibration and falsification surface, not a
claim-bearing test set. A future headline study must freeze its generator,
scorer, model settings, effect target, stopping or abort rule, and seed
derivation before execution; instantiate the sequestered items only after that
freeze; then reveal enough material for replay after outputs are timestamped.
No private chain-of-thought or unverifiable internal "semantic trace" is
required. The permitted claim concerns counterfactual observable behavior, not
a particular hidden representation or human-like act of reading.

### Gate 1 — checkpoint and state-delta recovery

First target: long-running coding or workflow agents that repeatedly exchange
public state. Compare full history, concise text, minified JSON, a strong
schema-aware baseline, and Urusilla under the same checkpoint, interruption,
recovery, and completion policy.

Required outcomes:

- safely completed tasks and recovery success;
- stale, duplicated, missing, corrupted, and out-of-order update handling;
- total input, output, repair, setup, fallback, and verification tokens;
- latency and provider cost per safely completed task;
- operator time to localize a seeded failure.

The existing synthetic state-delta result is a hypothesis source, not proof of
this gate.

### Gate 2 — tool-call and result pipelines

Test repeated function arguments, typed results, provenance, deduplication, and
cache references. Measure omitted or incorrect arguments, parser and repair
failures, cache mistakes, unsafe effects prevented, total cost, and task success.
Do not infer value from a smaller serialized payload alone.

### Gate 3 — multi-agent commitments

Test proposal, commitment, cancellation, conflict, expiry, and resolution in a
bounded workflow with externally observable outcomes. Compare against concise
text and a conventional transaction or workflow representation. Report both
coordination failures and any overhead introduced by the protocol.

### Gate 4 — cross-domain adaptive routing

Only after narrower routes pass may the same pre-send router be evaluated across
unseen domains and model families. It must choose among verified silence,
compiled routines or deltas, public action state, a validated task-aware
representation, concise text, and JSON. The claim target is total utility per
safely completed task, not use of one preferred syntax.

## Adoption work follows evidence

Framework integrations are useful only when they expose a measured route with
the same fallback and accounting contract. Build one thin, tested integration
for the first passing workload before expanding to LangGraph, AutoGen, CrewAI,
LlamaIndex, MCP, or other ecosystems. A wrapper example is not adoption, and an
adapter test is not end-to-end utility evidence.

Developer experience should make falsification easier:

1. a five-minute two-agent checkpoint-and-recovery example;
2. deterministic Lens views of messages, state transitions, and fallbacks;
3. an exportable, content-bound token/cost/repair ledger;
4. one-click creation of a counterexample or reproduction receipt.

## Growth metrics stay separate from research claims

Stars, views, clones, downloads, account registrations, and comments are
attention signals. Completed reproductions, counterexamples, independent
implementations, and measured integrations are contribution signals. Only
preregistered task results that pass their evidence contract can support an
efficiency, reliability, or interoperability claim.

Academic submission and standards engagement begin with a frozen method,
auditable artifacts, and a result that survives the applicable gate. Conference
or working-group names are not milestones by themselves.
