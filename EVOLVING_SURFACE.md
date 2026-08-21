# Session-local evolving surface

Status: development-only research machinery. It is not a promoted protocol
version and is not evidence of general token savings.

Canonical JSON digest of `urusilla_evolving_surface_capsule.json`:
`sha256:97f5a7027deeb9f70c71880a9d0c0102cfdc75626b058d9009839a904207f49e`.

## Design rule

Urusilla separates **stable meaning** from an **evolving wire surface**. The
public task context, symbol meanings, Capsule digest, and canonical action-state
remain the semantic identity. A sender and receiver may negotiate a shorter,
tokenizer-specific alias table for one already bounded model context. Human
readability, English spelling, pronunciation, and visual aesthetics have zero
weight in alias selection.

This is a reversible meta-language, not unconstrained online learning. Neither
endpoint may silently redefine a semantic identifier. Only the surface assigned
to that identifier may change.

## State machine

```text
inactive
  -> propose exact table + parent + scope
  -> verify artifact and exact round-trip vectors
  -> sender ack + receiver ack + comprehension pass
  -> activate inside one model context
  -> freeze exact external plan artifact, sample count, thresholds, and verifier
  -> bounded shadow trial against the enabled baseline
  -> keep only on strict inclusive-total-token advantage
  -> mint exact retained proof -> allow live marginal routing
  -> otherwise rollback to the exact parent or raw/JSON
```

Every table is bound to the session, model context, Capsule, task profile,
symbol table, tokenizer identities, generation, and exact parent. Every carrier
is additionally bound outside the model-visible payload to the exact table,
task context, source, decoded semantic state, session, and model context. This
host envelope is an integrity/identity binding, not authentication: authenticated
transport, replay protection, and sender identity remain deployment boundaries.
Encoding and decoding also require the exact passing per-message fidelity input
and verifier result used by the action-state router; a bare caller-supplied
source digest cannot attach an unrelated valid state to a message.

## Alias policy

The current conservative profile allows exactly one NFC-normalized Unicode
scalar per alias. Letters, numbers, and symbols from non-English scripts are
eligible. Controls, separators, punctuation, combining-only forms, variation
selectors, role-like tokens, compatibility collisions, duplicate aliases, and
collisions with unaliased semantic tokens are rejected. One-scalar aliases keep
the search machine-first while avoiding mixed-script role strings until a pinned
UTS #39 confusable implementation exists.

Aliases are globally injective within a table. An alias seen in the wrong
semantic position, under an unknown table, stale generation, sibling table,
different task meaning, or different source is rejected. There is no best-effort
guess; the route falls back.

## Objective and retention gate

The optimizer scores a candidate by its worst savings across every tokenizer
bound to the scope, weighted by observed semantic frequency. A candidate with
non-positive savings for any bound tokenizer is not selected. This proposal
score is not enough to retain a surface.

A bounded shadow trial charges the comprehension and table setup,
sender/router/receiver use, repair, and fallback to the surface arm. The table is
kept only when all of the following are true:

- complete usage accounting is available;
- surface safe completions do not fall below the matched baseline;
- every trial message parses and preserves the tested semantics;
- negation, null, failure, and refusal are preserved;
- no persistence, permission expansion, spending authority, or external effect
  occurs; and
- total tokens including setup are strictly lower by the switching margin.

Otherwise the decision is rollback. Missing data is not zero and cannot justify
retention. The retention function accepts only a trial bound to the active
surface, an immutable external plan-artifact digest, the exact planned sample
count, a result digest, an executed-transcript digest, and a deterministic
artifact verification. The plan artifact must bind the task set, matched
baseline, model and tokenizer identities, budgets, validator, and accounting
scope before execution. Running fewer or more messages than the frozen count,
call-time threshold substitution, and unverified self-reported trials cannot
produce a keep decision.

Activation alone is deliberately insufficient for live use. It authorizes only
the typed shadow executor, whose output is marked ineligible for delivery or
claims. A passing decision mints a sealed retained-surface proof bound to the
exact table, activation, session, model context, generation, frozen plan, trial
result, verifier, and evolving-surface Capsule. The live router requires the
exact table/active/retained triple. A forged, sibling, stale, or reset-context
proof fails closed. Even a retained local surface cannot inherit a general
performance claim from canonical action-state evidence.

Every shadow request requires a positive provider-enforced per-call token
ceiling, and the frozen plan binds both per-call and aggregate shadow budgets.
The public receiver executor rejects shadow requests and also rejects direct
live-surface requests. A retained surface reaches a live model call only through
the exact sealed route decision and `PreparedMessage`; bypassing the router
cannot turn a retained table into an unchecked live codec.

## Implementation boundary

The reference state machine, optimizer, compact positional carrier, exact
round-trip decoder, activation proof, and rollback decision live in
`urusilla_hybrid_runtime/surface.py`. An active table can run only through the
explicit shadow path before retention. After a passing trial, the exact retained
table can be selected inside the existing action-state route; the host validates
its structured round trip and keep proof, then the receiver consumes the compact
positional payload directly without prose re-expansion. Activation and
comprehension setup are charged exactly once to the frozen session-level surface
trial; post-retention per-message routing compares marginal cost and never
repeats or silently erases that setup.
The module performs no network I/O and creates no persistent state. A provider
adapter, authenticated transport, and trustworthy sandbox receipts are external
enforcement requirements.

The present implementation establishes fail-closed plumbing only. It has not
passed the project's frozen multi-domain, multi-model, independently operated
end-to-end gate. Raw concise natural language and canonical JSON therefore
remain the eligible defaults unless route-specific evidence exists.
