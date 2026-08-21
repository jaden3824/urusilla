# Urusilla Experimental Value Proof 002

Challenge 002 is an offline-first evidence gate for a possible future Urusilla
surface. It does **not** change the Urusilla protocol version and it does not
erase the unfavorable or null results already published by the project.

## Question

Can a bounded Urusilla task-semantic projection be supplied directly to a
model, without first expanding the content-addressed transport/provenance envelope
into a long natural-language paraphrase, while preserving task success and
reducing total tokens?

The frozen plan compares three representations of the same bounded synthetic
task:

1. concise natural language;
2. ordinary self-describing JSON; and
3. an Urusilla experimental direct-model-input task projection.

All arms use the same system safety text, response contract, task semantics,
model settings, one-turn limit, and fresh isolated context. The Urusilla arm
sets `decode_before_model` to `false` and `natural_language_expansion` to
`null`. Its exact `USX` carrier appears unchanged inside the model-visible
input. The full v0.1 request envelope and task digest remain outside the model
input as content-addressed transport/provenance bindings; this unsigned
fixture does not claim authenticated provenance. Format induction is visible
and must be charged to that arm.

`USX` is deliberately task-specific. It losslessly projects only the frozen
plan-selection schema; it is not a universal codec and makes no lossless
general-language claim. In the frozen UTF-8 inputs, the complete model-visible
surfaces are 784 bytes for concise language, 844 for ordinary JSON, and 662 for
the projection. These byte counts are only a structural precondition, not a
token-saving or task-success result.

The carrier in every arm contains only the plan facts and hard constraints.
The output and selection instructions appear once in the shared response
contract, so the concise-language baseline is not padded with duplicate task
instructions.

## Development chronology

No model call was made while selecting this surface. The first
punctuation-dense `UPX` draft used 190, 190, 194, and 230 complete input tokens
under the pinned cl100k, o200k, Qwen, and Mistral tokenizers, versus 172, 172,
176, and 204 for concise language. It was rejected before any task run.

The revised self-describing `USX` draft uses 157, 157, 161, and 195 tokens on
the same already-known task. This selection used the task and tokenizer
results, so Challenge 002 is exploratory development evidence, not a
confirmatory or preregistered efficiency test. A later test must freeze `USX`
first and then evaluate previously unseen tasks without retuning it.

## Exact task-success rubric

The task has two feasible plans and no utility tie-breaker. Success requires
one public JSON object with exactly this meaning and no prose:

```json
{
  "feasible_plans": ["plan-a", "plan-b"],
  "selected_plan": null,
  "would_execute": false
}
```

Wrong keys, plan order, selection, or execution intent fail the observable
rubric. A refusal, malformed response, provider failure, or missing response is
preserved; it is never silently converted into success.

## Token ledger

Every arm records non-overlapping `input`, `output`, `repair`, `tool`,
`unclassified`, and `total` tokens, plus an optional diagnostic `hidden`
breakdown. `input` is
the complete primary-call input and therefore already includes the system
text, format induction, carrier, and response contract. There is no separate
additive induction field. `repair` contains all repair-call input and output
tokens and must not overlap the primary fields. Unknown values stay `null`,
never zero. A measured total must reconcile exactly to all applicable
categories. When a provider does not expose hidden usage, either its known
total gap is explicitly placed in `unclassified` with status
`included-in-output`, `included-in-unclassified`, or `separately-reported`.
Only the last form is additive; the first two are subsets and are never counted
twice. If the hidden breakdown is unavailable, a provider-reported complete
total can still close the ledger. Without either a complete provider total or
the breakdown needed for reconciliation, the total and efficiency gate remain
`null`.

The candidate gate passes only when:

- all three arms satisfy the exact task rubric under matched fresh contexts;
- Urusilla is therefore non-inferior on task success;
- every relevant total-token ledger is complete and reconciled; and
- Urusilla total tokens are strictly below both concise language and ordinary
  JSON.

Failure, decline, rejection, fallback, and null evidence remain valid published
results. Wire bytes or message-surface tokens alone cannot pass this gate.

Challenge 002 is a cold one-turn test: every arm pays its complete induction
cost. A warm amortized test is explicitly outside this fixture and requires a
separately preregistered multi-task sequence, with induction charged once per
actual session. Repeating this already known task cannot establish a warm or
generalization result. Designing the projection after seeing the task creates
a known-task cherry-pick risk, so even a passing result is exploratory.

## Safety and model-call authority

The supplied validator never imports a provider SDK or makes a model, network,
or API call. It cannot install software or grant spending authority. An
external runner may perform the three calls only after the operator explicitly
opts in and records a SHA-256 reference to that approval. The protocol itself
cannot supply that approval.

Every observation must attest that tools, persistence, spending-authority
creation, permission expansion, and external effects were all false. The
validator rejects the record if any field is true.

## Offline commands

From the repository root:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.value_proof validate-plan interop_lab/evidence/challenge_002.plan.json
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.value_proof validate-result interop_lab/evidence/challenge_002.result-template.json --plan interop_lab/evidence/challenge_002.plan.json
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.value_proof init-result my-challenge-002-result.json --plan interop_lab/evidence/challenge_002.plan.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest interop_lab.tests.test_value_proof -v
```

`init-result` refuses to overwrite an existing file. Offline validation reports
`provider_calls: 0` or `provider_calls_by_validator: 0`.

## Promotion boundary

One passing Challenge 002 record cannot promote a protocol version. A future
version candidate requires at least two independent operators and two model
families, complete matched ledgers, the success and efficiency gates above,
zero safety-boundary violations, and publication of every negative and null
result. Confirmation must also use preregistered unseen tasks rather than this
known task alone. Until then the language version remains `0.1.0` and this is
only an experimental value-proof artifact.
