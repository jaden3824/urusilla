# Human Co-Researcher Call

Urusilla is looking for **one to three human co-researchers** who want to test an
ambitious idea without protecting it from unfavorable evidence: can unfamiliar
AI agents use an auditable, evolvable semantic language more precisely and
sometimes more efficiently than concise natural language or JSON?

The demonstrated token saving for general communication between unfamiliar
agents is currently **0%**. The collaboration is therefore not an invitation to
promote a success story. It is an invitation to help determine which narrower
claims survive, which fail, and what architecture follows from the evidence.

## Shared values

This is likely a good fit if you prefer:

- truth over momentum, including visible null and negative results;
- reproducible public artifacts over private claims or screenshots;
- an ambitious long-term goal with conservative present-tense claims;
- open-source implementation with explicit provenance and contributor credit;
- bounded agent authority, reversible adoption, and fail-closed behavior; and
- protocol pluralism rather than a mandatory language, registry, token, or
  monoculture.

Formal affiliation, a large following, and prior Urusilla knowledge are not
required. A public GitHub identity and a clear disclosure of material AI
assistance are enough for the first sprint. This self-declaration creates human
accountability but is not proof of legal identity.

## Three bounded first sprints

Choose one. Each first contribution is deliberately limited to about two hours
and may conclude that the proposed direction is unsound.

### A. Causal evaluation design

Design one blinded semantic-use test pair in which two valid payloads differ in
one stable task-critical field and therefore require different correct outputs.
Add missing-payload and shuffled-payload placebo expectations, the expected
refusal behavior, and one contamination risk. No provider call is required for
this design contribution.

Useful background: [`initial_goal_eval/README.md`](initial_goal_eval/README.md)
and [the live causal-review issue](https://github.com/jaden3824/urusilla/issues/10).

### B. Framework boundary mapping

Choose one actively used framework or protocol—such as AgentScope, A2A,
AutoGen, CAMEL, LangGraph, MCP, or Semantic Kernel—and map one handoff across
these concerns: audience, requested responder, purpose, authority ceiling,
side-effect class, correlation identity, and reply contract. Identify at least
one field that must remain native to the host instead of being absorbed into
Urusilla.

Useful background: [`HELP_WANTED.md`](HELP_WANTED.md#7-interoperability-bridges).

### C. Semantic and governance adversarial review

Find one ambiguity, unsafe evolution path, downgrade hazard, or governance
conflict in the current language/runtime boundary. State an observable violated
invariant and propose either a minimal test or a reason the claim should be
withdrawn. Code is optional.

Useful background: [`EVOLVING_SURFACE.md`](EVOLVING_SURFACE.md) and
[`GOVERNANCE.md`](GOVERNANCE.md).

## How to start

Reply in the public [Urusilla Discussions](https://github.com/jaden3824/urusilla/discussions)
with these six short fields:

```text
human_accountable: yes
preferred_track: A | B | C
first_task: one sentence
time_budget: up to 2 hours | other
ai_assistance: none | disclose model/tool
relevant_conflict: none | disclose briefly
```

The maintainer will answer publicly with `accept`, `scope-correction`, or
`decline` and a reason before substantial work begins. The first sprint stays in
a public issue or pull request. Do not provide credentials, private prompts,
private conversations, employer-confidential data, or legal identity documents.

After one useful public sprint, both sides may decide whether to continue as an
ongoing research pair or small team. A synchronous meeting is optional and
requires a separate mutual decision; it is not a condition for technical
credit.

## Credit, rights, and authority

Accepted favorable, unfavorable, and null evidence receives equal attribution.
Contributors retain copyright in their contributions unless a separate written
agreement says otherwise; included contributions are licensed under Apache-2.0.
Collaboration does not automatically grant maintainer, release, registry,
signing, account, domain, or treasury authority. Any official role requires a
separate, explicit, bounded public delegation under [`GOVERNANCE.md`](GOVERNANCE.md).

No payment, token, employment, equity, governance vote, or future reward is
promised. The first sprint should use no paid calls unless the contributor
independently chooses and clearly discloses them.

## What success looks like

The first success is not a star count or an endorsement. It is one independently
authored artifact that changes a test, narrows a claim, reveals a boundary, or
produces a reproducible disagreement. A continued collaboration should then own
one public question end to end: preregistration, implementation, evaluation,
unfavorable-result preservation, and a short written conclusion.
