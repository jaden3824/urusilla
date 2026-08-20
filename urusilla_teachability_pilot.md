# Fresh-Agent Open-Label Capsule Smoke Pilot

Status: internal pilot only; not an external adopter claim

## Result

The fresh agent earned **36/36 (100.00%)** on this bespoke decision, act, validation, and essential-semantic rubric. This is a smoke-test result, not a blind Teachability Score.

| Case | Decision | Act | Valid message | Essential semantics |
|---|---:|---:|---:|---:|
| T01-request-with-hard-constraint | PASS | PASS | PASS | PASS |
| T02-assert-evidence | PASS | PASS | PASS | PASS |
| T03-query-typed-answer | PASS | PASS | PASS | PASS |
| T04-propose-without-obligation | PASS | PASS | PASS | PASS |
| T05-commit-with-causal-parent | PASS | PASS | PASS | PASS |
| T06-resolve-failure | PASS | PASS | PASS | PASS |
| T07-retract-owned-record | PASS | PASS | PASS | PASS |
| T08-explicit-uncertainty | PASS | PASS | PASS | PASS |
| T09-ambiguous-request | PASS | N/A | N/A | PASS |
| T10-commit-missing-parent | PASS | N/A | N/A | PASS |
| T11-unknown-node-kind | PASS | N/A | N/A | PASS |
| T12-unknown-unit-and-effect | PASS | N/A | N/A | PASS |

## Method

A fresh sub-agent with no conversation fork was instructed to read only the task file and the experimental Grammar Capsule. It constructed complete messages for eight positive cases and rejected four ambiguous, causally invalid, unknown-kind, or unauthorized cases. The case identifiers and task wording exposed substantial category and decision cues, and the scorer used bespoke case checks. The result therefore demonstrates a useful construction smoke test, not evaluator blindness.

## Limitations

- This is one fresh agent instance, not a cross-vendor model population.
- The tasks were open-label enough to reveal substantial expected structure and rejection cues.
- The rubric was not frozen as a cryptographic commitment before the participant response.
- The evaluator checks essential semantics, not one uniquely correct graph for every natural-language instruction.
- The pilot measures Capsule-guided construction, not native binary generation or task-success improvement.
- File-access compliance is self-declared and was not enforced by an operating-system sandbox.

A production Teachability Score requires neutral task identifiers, precommitted hidden expectations, multiple model families, tokenizer versions, independent operators, measured learning cost, and end-to-end partner task success.
