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

Run the verifier tests from the repository root:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s initial_goal_eval/tests -v
```

Validate a future frozen study and result bundle:

```text
python3 -m initial_goal_eval.verifier STUDY_PLAN.json RESULT.json
```

Exit status `0` means every claim gate passed for a plan explicitly marked as
a real independent evaluation, `1` means structurally valid but not
claim-eligible, and `2` means the evidence contract was malformed or mutated.
Independence is a social and governance fact: the verifier checks frozen
attestations and full matrix coverage, but a digest alone cannot prove that an
operator is independent. That status still requires accountable review.

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
