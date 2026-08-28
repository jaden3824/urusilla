# PACT–Urusilla Boundary Map

Date: 2026-08-28

Status: non-normative conceptual comparison; no head-to-head result

Source pins:

- PACT preprint: [`arXiv:2606.05304v1`](https://arxiv.org/html/2606.05304v1), submitted 2026-06-03.
- PACT public code reviewed at commit [`91acf820f8a69fc7c181120b3120444a98823230`](https://github.com/iNLP-Lab/PACT/tree/91acf820f8a69fc7c181120b3120444a98823230).
- Urusilla source reviewed at commit `cfb4ef352980501fe28eeec6032c84cea4fabf89`.

## Result boundary

PACT and Urusilla overlap only at the research direction of making a public
handoff action-centered. PACT defines a sender-side public-history projection
rule whose serialization and operationalization vary by setting. Urusilla
explores a separate typed semantic contract, validation and authority
boundaries, conversation state, and canonical Wire serialization.

This note does **not** establish that Urusilla implements, extends, validates,
or is compatible with PACT. There is no common adapter, conformance test,
matched workload, or independent reproduction. It also does not compare model
tokens with transport bytes as though they were the same unit.

## What the reviewed PACT artifacts establish

The PACT paper defines three receiver-facing fields:

- **Action**: what the sender did or what the next agent should do;
- **State**: evidence, observation, environment feedback, or a tool result that
  grounds the message; and
- **Result**: the action output or artifact to use downstream.

The public split-evidence prompt directs the model to generate three
one-sentence text lines: `Action Required`, `Environment State`, and
`Action Result`. Its public method then removes complete
`<think>...</think>` blocks before appending the remaining text to history. At
the pinned revision, no canonical three-field parser, schema validator,
missing-field fallback contract, or authority validator was found in that
path. The README documents only a HotpotQA/Qwen3-14B demo, and the reviewed
tree contains no released pipeline or coding-hook result package.

In that released demo, `communication_tokens` are re-tokenized from decoded raw
output text before `<think>` removal, while only the cleaned text enters the
next agent input. `total_tokens` sums rendered input counts plus output counts
obtained by re-tokenizing decoded output text, rather than using the original
generation token IDs. These are experiment-side counts, not provider billing
receipts, and the reviewed tree does not establish that every paper experiment
uses this exact accounting implementation.

The coding-harness description in the paper uses another projection:
`Action Required`, `Observed State`, and `Planned Effect`, while preserving
tool calls and tool results. PACT therefore supplies a semantic communication
rule whose serialization varies by setting, not one canonical external schema
that can be equated field-for-field with Urusilla.

## Candidate mapping, with the losses left visible

The closest Urusilla surface is the development-only
`urusilla-public-action-state-draft/1` record, not UrusillaWire. The Wire codec
serializes UrusillaIR; it does not introduce another Action/State/Result
meaning layer.

| PACT concept | Closest Urusilla elements | Why this is not equivalence |
| --- | --- | --- |
| Public-message boundary | development-only public action-state record, with separate structural and task-context validation where the applicable runtime invokes them; the sender contract forbids private reasoning | Urusilla also specifies canonicalization, exact task context, fallback, and non-authority rules. PACT controls shared-history content without claiming those contracts. |
| Action | `act`, `action`; for a requested next step, also `goal` or `needs` | PACT uses one Action field for either what the sender did or what the next agent should do. Urusilla separates communicative act, goal, information need, and observable action status. |
| State | `state[]`; safety conditions in `constraints[]`; grounding in `outcome.evidence[]`; uncertainty in `uncertainty[]` | PACT State broadly includes evidence, observation, environment feedback, and tool result. Urusilla separates provenance, explicit negation, hard constraints, outcome evidence, and uncertainty. |
| Result | possible placements include development-surface `outcome.value`, an asserted `state[]` atom, or core `Resolution.result`, depending on lifecycle | The current direct task-context path type-binds only boolean, integer, or string `outcome.value`, not an arbitrary object/list artifact. Core `Resolution` carries target, status, result, and evidence; conversation and authority validity are checked separately. |
| Planned Effect in the coding hook | no one-to-one field; depending on content, the nearest elements may be `goal`, `action`, or an expected `outcome` | Urusilla `action.effects[]` and IR `action.declared_effects` are narrower declared effect-category identifiers and must not be inferred from PACT's natural-language Planned Effect. A declared effect remains descriptive data and never grants authority. No corresponding effect ontology or authority semantics was found in the reviewed PACT paper and code. |

At the core UrusillaIR layer, the corresponding concepts may be distributed
across `Goal`, `Action`, `Claim`, `Evidence`, `Constraint`, `Uncertainty`, and
`Resolution`. A `REQUEST` or `PROPOSE` creates no obligation, and a decoded
message alone cannot authorize an external effect.

## Measurements that must remain separate

| Artifact | Unit and denominator | Reported observation | Non-comparability boundary |
| --- | --- | --- | --- |
| PACT controlled MAS experiments | paper-reported `Tok`, described as average total tokens per problem, with Qwen3 models on two MAS topologies | authors report 38.7% average token reduction across their baselines and model scales while preserving or improving measured task performance | This is not a universal rate and was not measured on Urusilla. The paper does not state the aggregation formula for 38.7%. The exact full-paper accounting implementation is not present in the reviewed tree; the released split-evidence demo re-tokenizes decoded raw output text and supplies no billing receipt. |
| PACT HotpotQA field ablation, Qwen3-8B | F1 and tokens per problem | A+S+R: 69.9 / 6,704; S+R: 64.9 / 6,826; A+R: 65.2 / 6,741; Result only: 64.3 / 7,571 | This supports Action/State ablation effects inside that one PACT setting, not an Urusilla mapping or compatibility claim. No A+S arm removes Result, so the table does not independently ablate every field. |
| PACT OpenHands port | resolved instances and tokens per resolved instance on SWE-bench Verified | 97/500 to 115/500 resolved; 3.82M to 3.43M tokens/resolved | PACT-author-reported harness intervention; not upstream adoption or live deployment evidence. |
| PACT SWE-agent port | input tokens, resolved instances, and tokens per resolved instance | 314.6M to 156.0M input tokens; 128/500 to 121/500 resolved; 2.46M to 1.30M tokens/resolved | The input-token decrease co-occurs with a 1.4 percentage-point resolve-rate decrease. The reported per-resolved figures equal input tokens divided by resolved cases, not a demonstrated complete input-plus-output total. |
| Urusilla frozen broad-dialogue lane | deterministic receiver-carrier and post-decode API-input tokens; 2,542 turns, four tokenizers, zero model calls | warm carrier saving 0.65%–0.80%; cold and post-decode API-input saving 0%; H2/H3 fail; H4 not evaluated | Current general unfamiliar-agent saving remains 0%; task success and tokens per safe task are unknown. |
| Urusilla SGD gold-state oracle | prompt-only token opportunity over 399 next-action pairs, zero model calls | 7.48%–23.34% fewer prompt tokens across four tokenizers | Uses dataset gold state and measures no sender, accuracy, repair, safety, or task success. |
| `WIRE-CROSSPLAY-MIN-1` | framed transport bytes for five fixed same-project Python↔Node records | canonical minified JSON 6,781 bytes; cold Wire 5,274 (-22.224%); warm Wire 3,868 (-42.958%) | A local byte result, not model tokens, task success, external adoption, or independent evidence. |

## Small correction design sketch, not an executable fixture or result

The following four-cell sketch is a candidate for checking whether the mapping
above is coherent before a larger matched evaluation. It omits complete
canonical records, artifact digests, and canonical response envelopes. It is
not executable or executed here and cannot establish PACT compatibility or
general causal language use.

Common record shape:

- `act = resolve`;
- `goal` names the bounded route-selection task;
- `action` records completed `table.fetch` with no effects;
- `state[]` carries `route.branch(parcel-17, A|B)` with a public source;
- `outcome.status = succeeded`, `outcome.value` carries the scalar artifact ID
  `routes-v1`, and typed
  `outcome.evidence[]` atoms carry its A/B entries;
- `needs = []` and `uncertainty = []`; and
- `constraints[]` records a hard no-effects semantic condition. Actual
  non-authority comes independently from the all-false task-context authority
  boundary, empty `action.effects[]`, and runtime effect flags.

The task context must declare the artifact, entry predicates, argument schemas,
allowed scalar types, and fixture-owned output codes before any outcome is
observed.

| Cell | Proposed intervention | Acceptable behavior to preregister exactly |
| --- | --- | --- |
| valid A | selector scalar is `A` | select `route-alpha` |
| valid B | only that selector scalar changes to `B` | select `route-beta` |
| missing | remove only the selector scalar from valid A | pre-receiver arity rejection; a future receiver-use study needs a separate structurally valid semantic ablation |
| shuffled | place an unmodified `parcel-92` donor record into the `parcel-17` task context and apply a separately frozen parcel-binding validator | pre-receiver binding rejection; a future receiver-use study needs a separately valid shuffled control |

The pre-receiver rejection envelopes and their fixture-owned reason codes must
be defined before execution; Urusilla supplies no native
`missing-critical-state` or `task-context-mismatch` code. The current generic
task-context validator does not compare an atom argument with a task ID, so the
declared parcel-binding validator is required for the shuffled cell. Replacing
it with an undeclared task-specific symbol would test deterministic fail-closed
routing, not receiver causal use.

A qualifying run would need fresh contexts, identical non-payload settings,
frozen schema and task digests, no automatic semantic repair, exact output
validation, all call and fallback costs, and preservation of wrong, refused,
failed, and unknown outcomes. To test the necessity of all three PACT concepts,
separate preregistered Action, State, and Result ablations plus valid-payload,
no-payload, shuffled, and composition controls would still be required.

## One-row correction request

The most useful external review is deliberately small:

> Which single mapping row is most misleading: Action, State, Result, or
> Planned Effect? Please name the row and one counterexample. A correction does
> not imply endorsement, adoption, compatibility, or independent reproduction.

## Current evidence status

Supported only within the named project artifacts:

- PACT's paper-reported task/token observations and its public split-evidence
  prompt/method at the pinned revision;
- Urusilla's deterministic validation and local same-project Wire crossplay;
- the negative 0% general post-decode API-input result; and
- a candidate non-normative conceptual map.

The Urusilla items above validate separate bounded Urusilla artifacts. Neither
validates the candidate PACT mapping or the unexecuted correction sketch.

Still missing:

- a matched PACT/Urusilla workload with the same model, prompts, topology,
  success gate, tokenizer, and complete token ledger;
- a reviewed adapter or conformance contract between the two systems;
- external independent Urusilla implementation and execution evidence; and
- evidence that a real receiver causally used every task-critical public field
  while preserving safety and total-task utility.

## Primary and local sources

- [PACT paper, Sections 4–7](https://arxiv.org/html/2606.05304v1#S4)
- [PACT public prompt at the pinned commit](https://github.com/iNLP-Lab/PACT/blob/91acf820f8a69fc7c181120b3120444a98823230/prompts.py#L15-L64)
- [PACT public split-evidence method at the pinned commit](https://github.com/iNLP-Lab/PACT/blob/91acf820f8a69fc7c181120b3120444a98823230/methods/pact.py#L8-L125)
- [PACT public token counter at the pinned commit](https://github.com/iNLP-Lab/PACT/blob/91acf820f8a69fc7c181120b3120444a98823230/models.py#L86-L141)
- [`urusilla_v0_1_spec.md`](../urusilla_v0_1_spec.md)
- [`urusilla_action_state_capsule.json`](../urusilla_action_state_capsule.json)
- [`urusilla_hybrid_runtime/records.py`](../urusilla_hybrid_runtime/records.py)
- [`website/public/language-probe.json`](../website/public/language-probe.json)
- [`URUSILLA_GENERAL_DIALOGUE_RESULTS.md`](../URUSILLA_GENERAL_DIALOGUE_RESULTS.md)
- [`CLAIM_EVIDENCE_MATRIX.md`](../CLAIM_EVIDENCE_MATRIX.md)
- [`WIRE_CROSSPLAY_MIN_1_2026-08-28.md`](WIRE_CROSSPLAY_MIN_1_2026-08-28.md)

No PACT source code is copied into Urusilla by this note. A visible license file
was not found in the reviewed PACT code tree, so any future code reuse requires
an explicit license or permission check separate from the paper's CC BY 4.0
license.
