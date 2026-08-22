# Initial-goal evaluation contract

The default package surface is an offline evidence verifier for the Urusilla
initial research goal. It is separate from Challenge 002 and does not call a
model, execute a tool, install code at a partner, or produce an adoption or
performance claim. The explicitly imported `study_orchestrator.py` diagnostic
can invoke a caller-supplied runtime adapter and scorer; it creates
neither capability, carries no provider credentials or SDK, and remains
claim-ineligible.

`frozen_method_plan.json` freezes the claim method, thresholds, accounting
scope, and statistical procedure. It is a method artifact, not an executed
study plan or result. A real study must additionally freeze:

- exact candidate, Capsule, baseline, scorer, model-setting, and operator
  attestation digests;
- at least three domains, two receiver-model families, and two independently
  operated participants;
- a complete crossed matrix with at least two matched whole sessions per
  domain/model/operator stratum; and
- every hidden task, session boundary, arm order, parse probe, semantic probe,
  negative probe, preservation feature, and per-arm execution manifest before
  results are observed; and
- separate frozen sandbox policies, enforcement profiles, and independent
  audit protocols for both the sender compiler and receiver.

Each submitted result row contains all three arms for one matched whole
session. Token events cover setup, sender, router, receiver input and output,
reasoning, repair, fallback, tools, safety, and judges. Unknown usage remains
unknown and makes the result ineligible; it is never converted to zero. Failed
tasks and their costs remain in the numerator.

The primary cost estimand for arm `a` is:

```text
sum(all charged tokens across matched sessions for a)
-----------------------------------------------------
sum(safely completed tasks for a)
```

The verifier resamples whole sessions within frozen domain, receiver-family,
and operator strata. The hybrid arm must separately pass against both the
frozen concise-natural-language and ordinary-JSON controls. This avoids
choosing a favorable control after results are known.

Sandbox claims do not rely on model self-report. Every hybrid execution must
record sender-compiler and receiver evidence; baseline executions must record
receiver evidence. Each role binds the frozen policy and enforcement profile,
a technical enforcement receipt, an operator attestation, and an independent
audit receipt from a preregistered operator other than the executor. Tools,
network, credentials, persistence, spending, and permission expansion are all
denied. A missing receipt, an unknown audit or enforcement status, or an
unknown capability observation makes the measurement incomplete. Any observed
access or failed boundary is a noncompensable gate failure.

## Runtime-to-scorer diagnostic

`study_orchestrator.py` now closes one local execution gap between
`HybridExecution` and the offline research artifacts. For one prepared hybrid
task, `run_scored_hybrid_task()` executes the existing direct receiver and its
actual bounded raw/JSON fallback, binds the runtime ledger, selects only the
final terminal output, compares all four caller-declared scorer lock labels, and
invokes the injected scorer exactly once. This comparison neither derives the
callable's code hash nor authenticates its implementation. It verifies that the
prepared natural language is the exact final user task-input preimage, then derives the
task-result and scoring-binding objects from that observation. The returned
observation is factory-guarded and re-derives terminal fields from the execution,
so ordinary public dataclass replacement cannot change the scoring object and
its digest together without being rejected. The factory token is not stored on
the result. This is an API misuse guard, not an authentication or Python security
boundary. No scorer kind receives a projected
`judge` event: a caller-labelled deterministic local scorer does not prove that
the callable made no hidden model call, and a null-usage local event is not
assembler-consumable. A future runner must instead supply a separately captured
judge event. A failed primary call remains
unknown-cost after a successful fallback, a failed scorer remains null and
unknown-cost, a terminal no-output failure keeps `output_sha256: null`, and an
parse, semantic, negative, or preservation observations inconsistent with the
caller-declared probe flags are rejected.

This is a provider-neutral diagnostic bridge, not a generic study runner or a
claim gate. Current tests use project-authored fake adapters and scorers. The
bridge does not create or authenticate external-response records, execute the
raw/JSON baseline arms, observe a sandbox, prove an operator independent, or
assemble a complete study. Its task identity and probe flags are not bound to a
complete frozen study plan, and its result exposes both
`frozen_plan_bound: false` and `scorer_implementation_authenticated: false`.
Accordingly, `caller_reported_inclusive_total_tokens` and
`caller_reported_safely_completed` remain diagnostic fields, while their
claim-facing counterparts stay null. It
cannot elevate its own observations to
`claim_eligible: true` or `goal_total_complete: true`.

The remaining projection gap is structural and is kept explicit. The runtime
has a separate semantic-verification phase, whereas the frozen trace has no such
phase; one runtime fallback has both local and receiver events, whereas trace v2
permits one fallback event per task; and an exact cold direct-request projection
exists only for the action-state primary, not a raw/JSON runtime fallback.
Moreover, the current plan freezes an arm manifest whose event list includes
fallback and validator slots before execution, even though fallback existence is
decided only after the primary response. Synthetic fixtures currently construct
that manifest after observing their scripted branch. A future real runner must
mint a new, preregisterable branch-slot or superset-manifest contract instead of
hiding these mismatches or rewriting the frozen v1 method.

### Branch-slot execution-program prerequisite

`execution_program.py` now supplies a standalone, versioned branch-slot graph
and resolver for the first prerequisite to that runner. A program freezes each
possible operation, its dependencies, a closed activation-predicate AST, the
request/implementation/model bindings, and a one-call ceiling before any
response is observed. Resolution must cover every slot exactly once. An
activated slot must either produce a typed source-record commitment or retain
an explicit `failed-before-record` digest; an inactive slot is
`not-activated`, carries no usage event, and cannot be presented as a
zero-token observation. Unknown predicate inputs fail closed rather than
becoming a skipped branch. Canonical program and activation-input digests make
post-result mutation detectable.

The standalone evidence store validates the source-record preimages and binds
them to the program, session, arm, task, slot, component, frozen
implementation/model/request-deriver identities, and event order. The request,
provider-record, local-observation, and failure digests carried inside those
records are still opaque commitments: this module does not embed their
preimages or prove their request/response relationship. A fully resealed swap
or fabrication of those underlying artifacts therefore remains possible until
a future receipt-store integration resolves and validates every digest. The
new focused tests are structural mutation tests, not provider authentication.

This is still prerequisite plumbing, not a real study runner. The fixed hybrid
builder deliberately covers only the all-components action-state/routine path;
the generic closed vocabulary can represent preflight, compiler-control, and
final-router slots, but no current Plan v2, Trace v3, receipt-bundle v4, provider
capture journal, or independently operated run consumes it. Therefore it does
not repair the v1 plan, change the demonstrated general saving from 0%, or make
any result claim-eligible. The next integration must inline each program
preimage into a new study-plan schema, bind it into the verifier digest, and
reject every Plan/Trace/Receipt downgrade combination before external calls are
enabled. That Plan v2 validator must also prove exact operation coverage for
each custom hybrid task graph; this standalone generic validator proves graph
shape and reachability, not that a future runner declared every operation it
could perform.

## Offline trace assembly

`execution_trace.py` and `trace_assembler.py` provide a non-network bridge from
already captured provider-neutral calls to the existing RESULT event-ledger
shape. The trace binds all frozen sessions and all three arms, exact task and
phase identities, ordinary raw/JSON requests, validated hybrid receiver
projections, deterministic local events, and explicit zero-cost phases. The
assembler preserves failed-task costs, rejects missing, reused, or unused
captures, derives setup/output/reasoning coverage, and never converts unknown
usage to zero. Each external source also precommits its run ID, run-manifest
digest, episode-sequence digest, execution-profile digest, and bundle-record
position; assembly checks those values and the actual record chronology. A
deterministic router-output digest binds each selected mode, every action-state
attempt records its sender cost, and fallback reasons plus raw/JSON requests
are bound to the exact pre- or post-receiver path. Non-completed provider
events remain visible in `external_capture_metadata`, including a failed
primary later recovered by fallback; each metadata item binds the exact
provider response and its assembled usage receipt.

Every planned task digest is also checked against an exact task-message
preimage. Baseline and fallback calls must submit that exact message suffix;
hybrid calls bind the same task digest to the frozen sender input and bind the
sender output to the task-specific direct-receiver payload. This prevents a
foreign task request or projection from being relabelled after execution.

Trace schema v2 and assembly schema v4 also represent one completed-primary
semantic rejection without changing the frozen RESULT ledger. The manifest precommits
the versioned `deterministic-validator` identity, implementation, frozen task,
and primary-event slot. The later observed event, accounted under the existing
`safety` token bucket, binds the exact primary output digest, an `invalid`
verdict with the `semantic-invalid` reason, and its usage before a raw/JSON
fallback. Assembly checks the claimed primary-output digest against the
captured completed response, counts the primary, validator, and fallback usage
receipts, and scores only the final fallback. A completed primary without all
of that evidence is still rejected.

Trace, arm-manifest, and assembly v1 were project-authored synthetic plumbing
only and no serialized v1 artifact is shipped in this repository. The v2 trace
validators reject those shapes rather than implying backward-compatible
evidence semantics; regenerate any local synthetic trace from its frozen plan.
Assembly v3 replaced the ambiguously named usage-only sidecar in assembly v2
with one complete `receipt_bundle` plus its explicit content-validation result.
Assembly v4 upgrades that sidecar to receipt-bundle v3 and includes the exact
provider, manifest, and source-commitment preimages required by its additional
content gate. These are evaluator evidence-artifact versions only; they change
neither `languageVersion: 0.1.0`, the Urusilla protocol surfaces or semantic
kernel, nor the frozen initial research goal.

This bridge is **not** real study evidence. It emits
`claim_eligible: false` and `authentication_complete: false`; all current tests
use project-authored synthetic captures, and no current initial-goal provider
task run has been performed through this path. Assembly v4 emits a self-issued
receipt-bundle v3 whose provider usage receipts point to the exact supplied
external bundle and record preimages. The portable verifier independently
recomputes the external bundle, execution-profile, request, response, record,
and inline raw-receipt digests; resolves the arm-manifest and source-commitment
preimages; and rebinds the request messages, model settings, operator label,
bundle position, exact UTF-8 output or null output, terminal status, and generic
normalized usage projection to the result event and recorded score. Missing,
replayed, unused, or disagreeing preimages fail this diagnostic content gate.

That closure verifies only the consistency of the **supplied** artifact graph.
It does not authenticate the provider, producer, operator, or auditor; prove
that any provider returned the raw receipt or response; establish that an
execution was external or independently operated; or establish preregistration
chronology. The raw provider receipt remains opaque UTF-8 content: the verifier
checks its digest and reprojects an already normalized generic usage object, but
does not parse or independently perform provider-specific usage normalization.
A downstream receipt/result rehash that leaves the provider preimage unchanged
is now rejected, while a fully self-consistent fabricated or jointly resealed
preimage-and-receipt set can still pass content checks and must fail at the
authentication boundary.

Every generated receipt uses `urusilla-offline-trace-assembler` as its actual
issuer. The normal evidence-verifier path supplies no diagnostic issuer
override and therefore rejects this bundle by default. The scorer receipt
content-binds an already recorded verdict; the assembler does not execute or
replay the frozen scorer. Sandbox receipts remain self-issued wrappers around
declared evidence slots, not independent observations. Accordingly, this bridge
closes a supplied-preimage-to-ledger content gap, not the real-evidence gap. It
is neither performance nor adoption evidence and does not change the
demonstrated general unfamiliar-agent saving from **0%**. Because v3 embeds raw
provider receipts and completed model output, the bundle may contain sensitive
content and must only be shared where that disclosure is acceptable.

Run the verifier tests from the repository root:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s initial_goal_eval/tests -v
```

Validate a future frozen study and result bundle:

```text
python3 -m initial_goal_eval.verifier \
  STUDY_PLAN.json RESULT.json --receipts RECEIPT_BUNDLE.json
```

Exit status `0` means every claim gate passed for a plan explicitly marked as
a real independent evaluation, `1` means structurally valid but not
claim-eligible, and `2` means the evidence contract was malformed or mutated.

Receipt bundle v1 establishes **content consistency only**. It resolves each
content-addressed wrapper, checks exact plan/session/arm/event bindings,
reconciles reported usage, rejects provider-call replay, requires
receiver/fallback events to be model calls, and binds scorer, enforcement,
attestation, and audit observations to their frozen artifact digests. It does
not satisfy claim-facing receipt completeness because its scorer receipt does
not bind the exact terminal provider output. Receipt bundle v2 adds that
binding and fails closed if the output boundary, terminal status, exact-task
route, terminal event, usage receipt, provider-response digest, or verdict
disagrees across the linked result, usage receipt, and scorer receipt. It also
rejects provider-response replay across tasks or arms and cannot label a
non-completed provider call as a successful scored terminal. Receipt bundle v3
additionally requires exact external bundle and provider-record preimages, arm
execution manifests, and source-commitment preimages. Its portable consumer
recomputes the nested request, response, raw-receipt, usage, record, profile,
sequence, and bundle bindings and rejects missing, replayed, unused, or
disagreeing records and downstream result/receipt resealing that does not match
those preimages. V3 is therefore the minimum content schema for a
future real-evidence receipt submission, but it remains content verification,
not authentication. None of these versions validates a provider signature or
externally anchored operator identity, proves independent execution, or
rederives usage through a provider-specific normalizer from an authenticated raw
payload. A maintainer can still self-author a fully consistent provider bundle,
receipt set, and issuer labels.

Accordingly, real evidence currently fails closed with
`authenticated-provenance-not-established` even when every receipt is
content-consistent. A first optional signed-accountability sidecar now verifies
canonical Ed25519 signatures over the exact plan, result, receipt-bundle digest,
frozen normalizer-manifest digest, per-session operator/auditor roles, and one
preregistration statement. The verifier caller must obtain the trust-policy
digest independently and pass it through a separate argument. The validator
checks the exact digest match but cannot prove where the caller obtained it;
under a proper independent workflow, silent trust-key substitution is
detectable.
The sidecar also rejects mutated signatures, untrusted normalizers, revoked or
wrong-role keys, invalid chronology, repeated signature bytes, incomplete
provider/normalization reports, and operator/auditor control-domain overlap.

That sidecar reports `signed_accountability_complete: true` only. It deliberately
keeps claim-facing `complete: false`: witness signatures are not provider
signatures, signer timestamps do not establish execution-after-anchor by
themselves, count attestations do not replay a provider-specific normalizer from
the raw receipt, and an envelope-local replay check is not a global reservation
registry. Enabling the real claim gate still requires provider-origin proof,
independent raw-to-normalized usage replay under the frozen provider profile,
and a global replay/challenge registry. Until those boundaries exist, exit
status `0` remains intentionally unreachable for real evidence. Independence
also remains partly a social and governance fact even after signatures;
accountable review must establish that separate keys correspond to genuinely
independent operators.

Install the optional verification backend only for a signed evidence audit:

```text
python -m pip install 'urusilla[evidence-auth]'
python -m initial_goal_eval.verifier PLAN.json RESULT.json \
  --receipts RECEIPTS.json \
  --trust-policy TRUST_POLICY.json \
  --authentication AUTHENTICATION.json \
  --expected-trust-policy-sha256 sha256:...
```

The declarative Capsule and reference runtime remain dependency-free; this
optional package is evaluator tooling, not software installed at a partner
agent.

All fixtures under `tests/` are synthetic plumbing tests. Even when their
numeric gates pass, the verifier deliberately refuses to emit claim-eligible
utility evidence for them.

The confirmatory estimand is the aggregate hybrid-router system. It is not a
route-specific authorization result: shared setup cost and matched-session
outcomes cannot be reassigned after the fact to `silence`, `routine`, or
`action-state`. Accordingly, this verifier never emits runtime
`UtilityEvidence` for an individual optimized route. A real aggregate pass may
emit `hybrid_system_evidence`; each runtime route still requires a separately
frozen, route-scoped confirmatory trial before it can receive route-level
utility evidence.

The runtime enforces this as a construction invariant rather than relying on a
documentation convention. Caller-supplied route evidence can meet declared
metric thresholds for bounded local policy use, but `passes_initial_goal_gate`
remains false, positive route claim flags are rejected, and every constructed
route decision remains claim-ineligible until an authoritative route-scoped
producer exists.

## Causal-use boundary

Passing the v1 aggregate gate would not prove that an action-state payload was
causally consumed. The v1 plan binds the exact sender output and direct receiver
request, but it has no counterfactual intervention that distinguishes a receiver
using the payload from a constant or task-context-only answer. A route-level
language, comprehension, or direct-consumption claim is therefore prohibited
under v1 even if every existing metric passes.

The next method version must precommit blinded payload-dependence probes in
every domain, receiver-family, and independent-operator stratum. Each probe must
hold the Capsule, non-payload task context, model settings, and fresh-context
policy fixed; vary exactly one task-critical field across schema-valid A/B
payloads; require the expected task output to change with that field; and add
missing and shuffled placebos whose only passing disposition is refusal or safe
fallback. Every intervention and placebo call, including failures, must enter
the inclusive token ledger. Replayed provider responses, identical A/B outputs,
unknown usage, absent placebos, or incomplete stratum coverage fail closed.

This is an architecture-changing evidence requirement. The frozen method,
plan, result, trace, manifest, receipt, and summary `/1` schemas remain immutable;
the stronger contract must mint `/2` artifacts and new digests. A standalone
offline validator now lives in [`causal_probe_v2.py`](causal_probe_v2.py), with
mutation-focused checks in
[`tests/test_causal_probe_v2.py`](tests/test_causal_probe_v2.py). It separates a
frozen plan from the later assignment reveal and result pack, validates exact
one-pointer A/B payload changes, retains well-formed adverse outcomes as
explicit gate failures, rejects replay and binding drift, and keeps unknown
inclusive token totals as `null`. It performs no provider call and every summary
is `claim_eligible=false`; its synthetic fixtures are not model evidence and
cannot make v1 claim-eligible.

The current `/2` diagnostic remains deliberately narrower than a confirmatory
causal study. Its `missing` condition is an abstention placebo, not a measured
no-payload accuracy baseline; it does not test semantic invariance or composition
holdouts, establish that the declared field universe is externally complete, or
separate public calibration and private headline seeds. Field coverage is keyed
to preregistered stable field IDs, so a canonical pointer and aliases such as
`deadline`/`target_date` share one coverage bucket; alias-specific counts are
reported only as pointer usage. Duplicate semantic-definition digests are
rejected, although digest identity cannot detect paraphrased duplicate
definitions. The plan places that alias-to-field binding and an independently
specified, identity-only external refusal-calibration reference set in one
content-addressed preregistration envelope. The pack binds the envelope through
the plan digest, so changing either nested identity without resealing is detected;
the validator has no signed or append-only external anchor, however, and cannot
establish chronology or prevent a coordinated post-result rehash of both plan and
pack. It validates no external reference observations or attestation
authenticity. Same-receiver valid A/B refusal counts are therefore not an
externally anchored false-refusal baseline.

The four current conditions also do not constitute the proposed per-stable-slot
flip/invariant/missing-or-corrupt/no-payload-or-byte-lure matrix. The retained
per-slot and full per-stratum tables cover only the present three dimensions
(domain, receiver family, and operator), not the proposed worst
domain×receiver/runtime×operator×principal×slot-class stratum. The summary
therefore marks both matrix and five-dimensional validation false and separates
the local `payload_influenced_output` record check from
`task_semantics_used`, which is not validated or claim-eligible. Counts and these
tables remain descriptive contract diagnostics, not an effect-size gate or claim
evidence.
