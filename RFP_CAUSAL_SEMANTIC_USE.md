# Request for Plot: Does the Receiver Use the Semantic Payload?

## Big question

A typed agent message can be valid, canonical, and accurately delivered while
the receiving model ignores its task-relevant semantics. Can a compact semantic
representation causally determine the receiver's output, or is apparent success
coming from the natural-language wrapper, answer priors, or evaluator leakage?

This question matters beyond Urusilla. Any agent protocol that claims model
understanding rather than transport validity needs a way to separate payload use
from wrapper following.

## Honest starting point

Urusilla currently demonstrates **0% token saving for general communication
between unfamiliar agents**. Its local causal harness can bind exact requests
and preregister stable semantic field identities, but it has no independently
operated four-arm model study and no evidence that real task semantics were
causally used.

## The first plot

Produce one figure with four intervention arms on the x-axis:

1. valid payload A;
2. valid payload B, differing from A in exactly one stable task-critical field;
3. the payload missing; and
4. the payload fields shuffled across tasks.

The y-axis is the rate of the preregistered correct behavior: the distinct
task-consistent answer for valid A or B, and an explicit refusal or fallback for
the missing or shuffled placebo. Show every observation and a 95% Wilson
interval. Do not pool fields whose correct output is invariant to the changed
payload.

If resources permit, facet the plot by representation—concise natural language,
ordinary JSON, and directly model-visible Urusilla—and by model family. The
first collaboration milestone does **not** require provider calls: it is a
sealed set of at least four adversarial task templates, exact A/B semantics,
expected outputs, placebo expectations, and contamination risks. The model run
begins only after the materials and accounting plan are frozen.

## Controls

- Keep every non-payload instruction, model setting, tool policy, retry rule,
  and output schema identical within each matched set.
- Generate or select A/B pairs independently of measured model outcomes.
- Hide the mapping from the operator performing the run when feasible.
- Count setup, input, output, retry, repair, refusal, judging, and failed-call
  usage; unknown usage stays unknown rather than becoming zero.
- Report per-field and worst-stratum results before any aggregate.
- A syntactically valid answer is not sufficient; the changed semantic field
  must require the changed correct output.
- Publish unfavorable, null, refusal, and contamination findings.

## What a collaborator can do in two hours

Choose one task domain and submit four adversarial templates with:

```text
stable_field_id:
payload_A:
expected_A:
payload_B:
expected_B:
missing_payload_behavior:
shuffled_payload_behavior:
why_A_and_B_must_differ:
contamination_risk:
```

No Urusilla implementation knowledge is required. A valid conclusion may be
that the proposed manipulation cannot isolate semantic use.

Start in [Human co-researcher Discussion #11](https://github.com/jaden3824/urusilla/discussions/11)
under track A. Codex assisted the founding maintainer in drafting this RFP; an
external contribution is not considered independent until its authorship,
materials, runtime, and shared-control relationships are disclosed.
