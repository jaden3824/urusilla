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

The post-receiver recovery lane currently accepts only a non-completed primary
whose exact provider status is named by `fallback_from`. A provider response
that completed but was later rejected by deterministic output/semantic
validation needs a separately bound validation phase; the frozen RESULT phase
schema cannot represent that evidence yet. Offline assembly therefore rejects
that lane and reports it as a claim blocker instead of inferring validation.

This bridge is **not** real study evidence. It emits
`claim_eligible: false` and `authentication_complete: false`; current tests use
project-authored synthetic captures. Provider-specific usage normalization,
signatures, scorer and sandbox receipts, and independently operated executions
are still absent. In addition, the current scorer-receipt schema binds the
reported score but does not yet bind that score to the exact captured provider
output digest. That scoring-output binding must be added in a separately
reviewed schema revision before assembled traces can support a performance
claim.

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

The receipt bundle currently establishes **content consistency only**. It
resolves each content-addressed wrapper, checks exact plan/session/arm/event
bindings, reconciles reported usage, rejects provider-call replay, requires
receiver/fallback events to be model calls, and binds scorer, enforcement,
attestation, and audit observations to their frozen artifact digests. It does
not yet authenticate the issuer or rederive usage from a signed provider
payload. A maintainer can otherwise create two keys or two issuer labels and
self-author a mutually consistent bundle.

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
