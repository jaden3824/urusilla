# Initial-goal evaluation contract

This package is an offline evidence verifier for the Urusilla initial research
goal. It is separate from Challenge 002 and from the hybrid runtime. It does
not call a model, execute a tool, install code at a partner, or produce an
adoption or performance claim.

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

Trace schema v2 and assembly schema v3 also represent one completed-primary semantic
rejection without changing the frozen RESULT ledger. The manifest precommits
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
Assembly v3 replaces the ambiguously named usage-only sidecar in assembly v2
with one complete `receipt_bundle` plus its explicit content-validation result.
This is an evaluator artifact version only; it does not change the Urusilla
language version or semantic kernel.

This bridge is **not** real study evidence. It emits
`claim_eligible: false` and `authentication_complete: false`; current tests use
project-authored synthetic captures. The assembler now emits a self-issued
receipt-bundle v2 whose usage, scorer-output, and sandbox receipt references
close both assembly-local diagnostic content gates. Every generated receipt
uses `urusilla-offline-trace-assembler` as its actual issuer. The normal
evidence-verifier path supplies no diagnostic issuer override and therefore
rejects this bundle by default. The scorer receipt content-binds an already
recorded verdict; the assembler does not execute or replay the frozen scorer.
Sandbox receipts are self-issued wrappers around declared evidence slots, not
independent observations. Provider-specific usage re-normalization,
authenticated signatures, independently observed sandbox enforcement, and
independently operated executions are still absent. The receipt-bundle v2
validator requires
each provider usage receipt to carry a cross-linked
provider-response digest and terminal status. A provider-backed scorer receipt
binds the verdict, exact task and route, terminal event, usage receipt, response
digest, and either exact UTF-8 output text or an explicit null output from a
non-completed call. A silence score instead binds the task, silence route, and
canonical no-output digest without inventing a provider call, usage receipt, or
response digest. Provider-response digests are replay-protected across the
bundle but their preimages are not independently resolved or authenticated at
this layer. A coordinated rehash can therefore remain internally
content-consistent and must be rejected at the authentication boundary; only
an unsynchronized mutation is detected by these hashes. The
new assembler bridge closes a capture-to-ledger wiring gap, not the real-evidence
gap: all issuer identities and sandbox observations remain self-asserted until
external authentication is supplied. Because v2 embeds
completed output text instead of trusting an unverifiable text digest, the
bundle may contain sensitive model output and must only be shared where that
disclosure is acceptable.

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
non-completed provider call as a successful scored terminal. Neither version
authenticates the issuer, resolves the referenced provider-response artifact,
or rederives usage from a signed provider payload. A maintainer can otherwise
create two keys or two issuer labels and self-author a mutually consistent
bundle.

Accordingly, real evidence currently fails closed with
`authenticated-provenance-not-established` even when every receipt is
content-consistent. Enabling the real claim gate requires a separately reviewed
authentication layer with externally anchored operator/auditor public keys,
canonical receipt signatures, preregistration timestamp evidence, resolved raw
provider artifacts, and frozen provider-specific usage normalizers. Until that
layer exists, exit status `0` is intentionally unreachable for real evidence.
Independence remains partly a social and governance fact even after signatures;
accountable review must establish that separate keys correspond to genuinely
independent operators.

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
