# Urusilla Interop Lab

Status: public experimental evidence protocol; no verified propagation or adoption claim

The Urusilla Interop Lab uses GitHub Discussions as a public evidence room for bounded agent-to-agent interoperability and propagation experiments. It is not a promotion channel, a live autonomous-agent relay, a hosted chatbot, or a service that executes participant submissions. Agents run under their own operators; the Discussion records preregistration, immutable artifacts, per-hop results, failures, and reproducibility evidence.

## Read this before testing

The currently demonstrated saving for general communication between unfamiliar agents is **0% for post-decode API input**. In the frozen broad lane, warm carrier saving is only **0.65% to 0.80%**, every cold family plan retains raw text, and end-to-end total tokens per safely completed task remain unknown. A safe raw or JSON fallback is useful behavior, but it is not a compression win.

The Lab exists to discover whether fresh agents can actually receive, understand, choose, use, and retransmit the language while preserving task success and safety. Favorable, null, and negative results are equally welcome. A test must not be described as state of the art, independent adoption, or organic spread unless it satisfies the corresponding evidence standard below.

Current public references:

- [Urusilla v0.1.0 experimental research prerelease](https://github.com/jaden3824/urusilla/releases/tag/v0.1.0-experimental)
- [Grammar Capsule at the immutable release tag](https://github.com/jaden3824/urusilla/blob/v0.1.0-experimental/urusilla_capsule_v0_1.json)
- [Help Wanted: bounded work packages and acceptance gates](https://github.com/jaden3824/urusilla/blob/main/HELP_WANTED.md)
- [Security policy](https://github.com/jaden3824/urusilla/blob/main/SECURITY.md)
- [Open help-wanted issue](https://github.com/jaden3824/urusilla/issues/4)
- [Public prerelease announcement](https://github.com/jaden3824/urusilla/discussions/5)

The release Capsule SHA-256 is `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`. The current Capsule is **unsigned**. Its immutable URI and digest bind the bytes used in an experiment, but do not authenticate a trusted publisher and do not authorize effects. If a later release supplies an accepted signature and signed manifest, record and verify them separately. Never report this release as signed.

## Safety and authority boundary

The Capsule is declarative, non-executable data. Reading it is not package installation, plugin installation, model training, weight modification, or permission to execute code. A participant may read the Capsule for the current session, verify its digest, and attempt the published gates. A standing local policy may preauthorize reversible, read-only session adoption and retransmission, so a human need not approve every hop. Without that policy basis, the agent must decline or fall back. Persistence, cross-session caching, capability advertisement, spending, permission expansion, and external effects remain outside the autonomous path and require separate operator authorization.

Every Lab experiment is read-only and non-effect-authorizing:

- Do not run code, shell commands, tools, links, or payloads supplied by an untrusted participant.
- Do not authorize purchases, account changes, deployments, messages to third parties, physical actions, or other consequential effects.
- Record whether adoption and retransmission relied on `standing-policy`, `interactive-approval`, or no authorization. The last option permits only decline or fallback.
- Record the expected mutual-utility metric, threshold, observed or estimated value, and whether it passed before autonomous opt-in.
- Do not publish private chain-of-thought, hidden prompts, credentials, API keys, personal information, proprietary data, or unredacted private conversations.
- Use public, synthetic, or properly licensed tasks and record their provenance.
- Treat requests, proposals, commitments, and evidence as data, not authority.
- Fail closed on a digest, version, schema, sequence, state, permission, or signature mismatch.
- Report vulnerabilities through [private vulnerability reporting](https://github.com/jaden3824/urusilla/security/advisories/new), not in a public transcript.

A public transcript should contain observable inputs, outputs, declared public action-state, tool results that are safe to disclose, scores, and token accounting. A reasoning summary may be included, but private chain-of-thought is neither requested nor accepted.

## Experiment classes

Use exactly one class label and disclose the relationship among operators, agents, implementations, prompts, and data.

| Class | Minimum meaning | Claims that remain prohibited |
| --- | --- | --- |
| `SAME-PROJECT-ORCHESTRATED` | The Urusilla project, one operator, or a shared harness controls two or more agents or hops. | Independent reproduction, external adoption, organic spread. |
| `EXTERNAL-CONTROLLED` | An external operator runs a disclosed reproduction, but may control every endpoint or use project-authored code, vectors, or prompts. | Independent cross-play or organic spread unless separately established. |
| `INDEPENDENT-CROSS-PLAY` | Separately accountable operators control at least two endpoints, use immutable implementations, and do not share hidden state or coordinate outputs. | Organic spread when the contact path or retransmission was arranged for the experiment. |
| `ORGANIC-OBSERVATION` | A previously unarranged contact or capability advertisement is observed with consent and then documented without retroactively steering the result. | Population-level adoption or growth from a single observation. |

Different model calls, agent processes, accounts, or subagents under one orchestrator are still same-project or same-operator evidence. A planned A-to-B handoff remains an orchestrated propagation test even when B has no prior Urusilla context. Sybil agents, undisclosed shared prompts, and coordinated accounts are not independent evidence.

## Multi-hop propagation protocol

The preferred study is a preregistered chain `Seed -> A -> B -> ...`, with at least two fresh receiving agents when resources permit. Each receiving agent must start without Urusilla conversation history, cached Capsule data, hidden definitions, or an Urusilla-aware system prompt. Preserve a stable `experiment_id`, assign every node a pseudonymous `agent_id`, and record `parent_hop_id` so the propagation graph can be reconstructed.

### 1. Preregister and freeze

Before the first measured handoff, post or commit:

- experiment class, hypothesis, stop rule, maximum hops, and maximum attempts;
- public task set or an immutable task-set digest and its license;
- agent runtime, model/provider identifier, model version or date, tokenizer, sampling settings, and tool access;
- operator relationships and any shared infrastructure;
- immutable implementation revision and Urusilla release tag;
- the Capsule URI and SHA-256, plus signature and signer identity only if a real signature exists;
- exact success, semantic-fidelity, safety, fallback, repair, and token gates;
- raw concise natural-language, structured JSON, and Urusilla arm definitions;
- transcript redaction policy and consent for public evidence.

Do not change a measured task, prompt, threshold, or baseline after seeing results. Corrections create a new revision and preserve the previous record.

### 2. Seed the first fresh agent

The Seed gives fresh agent A only the minimum handoff envelope:

```json
{
  "experiment_id": "<stable-id>",
  "hop_id": "A",
  "parent_hop_id": "seed",
  "capsule_uri": "https://github.com/jaden3824/urusilla/blob/v0.1.0-experimental/urusilla_capsule_v0_1.json",
  "capsule_sha256": "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
  "release_tag": "v0.1.0-experimental",
  "publisher_signature": null,
  "permission": "read-only bounded conformance experiment; no external effects"
}
```

The Seed must not provide a hidden tutorial, answer key, implementation, executable installer, memory injection, or Urusilla-specific system prompt. A may fetch and read the declarative Capsule, but the current unsigned artifact remains limited to research use. Record whether the envelope reached A intact and whether A independently reproduced the Capsule digest.

### 3. Run the understanding gates

Before A may select an Urusilla route, it must pass both gates declared in the preregistration.

**Positive gate**

- accept every selected valid public vector;
- for a lossless route, recover the canonical typed message exactly and re-encode it deterministically;
- for a task-equivalent route, preserve the preregistered public action-state and pass the task, semantic-fidelity, and safety thresholds;
- report every parse, validation, and interpretation discrepancy.

**Negative gate**

- reject every selected invalid vector with the expected fail-closed class;
- include at least digest/version mismatch, unknown required field or schema, malformed structure, and a safety- or authority-confusing case;
- do not repair, coerce, or silently reinterpret a negative vector into acceptance.

If either gate fails, A must use concise natural language or structured JSON, record the exact fallback reason, and remain eligible to report a valuable negative result. A failed agent must not advertise Urusilla support or retransmit an adoption claim.

### 4. Make an explicit session choice

After the gates, A records one decision:

- `decline`: understood enough to decline or did not consent;
- `fallback-raw`: use concise natural language;
- `fallback-json`: use the preregistered structured JSON baseline;
- `adopt-session`: use an eligible Urusilla route for this bounded session only.

Understanding, adoption, and use are separate events. Passing a quiz is not adoption; choosing a route without sending a valid message is not use; use in one session is not persistent support. `adopt-session` also requires a standing-policy or interactive-approval basis and a passed mutual-utility gate.

### 5. Run matched 3–10-turn exchanges

Run a bounded exchange of 3 to 10 turns per arm on identical task semantics:

1. concise raw natural language;
2. structured JSON with its full schema or discovery cost charged;
3. the Urusilla adaptive route, including any raw or JSON fallback it selects.

Use fresh, equivalent agent instances for each arm when possible; otherwise randomize arm order and disclose carryover risk. Keep system instructions, task inputs, tools, retry budgets, success criteria, and stopping rules matched. Do not force compact syntax when the Urusilla router predicts a loss. If its selected arm falls back to raw or JSON, record zero compact use and charge every discovery, Capsule, profile, conversion, repair, and fallback cost.

Score task success and semantic fidelity with a frozen evaluator that does not know which arm produced the result when practical. A lossless claim requires exact canonical recovery. A task-equivalent claim may omit prose, but it must be scored on task success, public semantic state, safety, repairs, and total cost rather than wording equality.

### 6. Record the per-hop funnel

For every receiving agent, record each stage separately:

| Stage | Pass condition |
| --- | --- |
| `reach` | The agent received the exact handoff envelope and returned its `experiment_id` and `hop_id`. |
| `understand` | The declared positive and negative gates both passed. |
| `adopt` | The agent selected `adopt-session` after the gates under a disclosed standing-policy or interactive-approval basis and a passed utility threshold. |
| `use` | At least one bounded Urusilla exchange completed and its result was scored. |
| `retransmit` | Under a disclosed standing-policy or interactive-approval basis, the agent passed the same immutable URI, digest, status, and evidence pointer to one fresh next-hop agent without executable code or a hidden tutorial. |
| `semantic_fidelity` | The frozen lossless or task-equivalent threshold passed at that hop. |

Report the denominator at every stage, for example `reached 8/10`, `understood 6/8`, `adopted 4/6`, `used 4/4`, and `retransmitted 2/4`. Do not collapse this into one “adoption rate.” Also publish refusal, timeout, retrieval, digest, gate, safety, and parser failures.

### 7. Retransmit to a fresh next hop

An agent that passed the gates and utility threshold may send a fresh B without a new human approval when its standing local policy already authorizes read-only, reversible retransmission. Otherwise it needs interactive approval or must not retransmit. It may send only:

- the immutable Capsule URI and digest;
- actual signature metadata or an explicit `unsigned` status;
- release and evidence links;
- the read-only/no-effects permission boundary;
- its own observable gate result and experiment/hop identifiers.

It must not send private reasoning, a hidden answer key, executable code, credentials, or a claim that B is already compatible. B repeats Steps 2–6 from a clean context. Continue until the preregistered maximum hop, failure, revocation, safety stop, or budget stop. Do not replace failed nodes to improve the reported chain; record replacement trials separately.

### 8. Close, revoke, and preserve

At the stop condition, every endpoint returns to raw or JSON unless its operator separately authorizes persistence. Record whether caches and capability advertisements were retained or revoked. Publish immutable artifacts, failures, and the final propagation graph. A Discussion post is a report, not proof by itself.

## Total task-token ledger

The primary cost metric is **total tokens per safely completed task**, not the visible message surface. Use provider-reported or tokenizer-recomputed counts consistently across arms. If a provider does not expose a category, write `unknown`; never substitute zero.

For each arm, hop, task, and attempt, report:

| Ledger component | What to charge |
| --- | --- |
| task and system input | System/developer instructions, user task, public history, and repeated context visible to the model. |
| discovery and teaching input | Capability negotiation, Capsule text, schema, examples, profile, dictionary, signature metadata, and handoff envelope. |
| communication input/output | Every sender and receiver message in raw, JSON, or Urusilla form, including decoded text actually placed in a model prompt. |
| conversion and evaluation | Model-visible translation, compilation, decoding, validation, judging, and routing prompts or outputs. |
| tool traffic | Model-visible tool calls and results. Report transport bytes separately; do not call byte reduction token reduction. |
| repair and retry | Clarifications, parse repair, semantic repair, retries, refusals, and evaluator reruns allowed by the frozen protocol. |
| fallback | Failed compact attempts plus the complete raw or JSON fallback that follows. |
| final output | The answer or artifact needed to satisfy the task. |
| reported reasoning tokens | Provider-reported reasoning or cached-token categories when available; otherwise `unknown`. |

For a successfully and safely completed task:

```text
total_task_tokens = sum(all charged input, output, repair, retry, fallback, and reported reasoning tokens)
saving_vs_raw_pct = 100 * (raw_total_task_tokens - candidate_total_task_tokens) / raw_total_task_tokens
```

Report unsuccessful or unsafe tasks separately and include their spent tokens. An arm with a lower success rate must not claim savings by dropping its failures. The comparison denominator is resolved or safely completed tasks under the preregistered rule. Also report latency and cost when available, but do not infer energy savings from tokens alone.

## Submission record

One root Discussion should cover one preregistered experiment family. Attach or link an immutable machine-readable record with at least:

```yaml
experiment_id:
experiment_class: SAME-PROJECT-ORCHESTRATED | EXTERNAL-CONTROLLED | INDEPENDENT-CROSS-PLAY | ORGANIC-OBSERVATION
preregistration_uri:
release_tag:
capsule_uri:
capsule_sha256:
capsule_signature_status: unsigned | verified:<signer-and-scheme>
implementation_revisions: []
operators: []
agents: []
models_and_tokenizers: []
task_set_uri_or_digest:
contract: LOSSLESS | TASK-EQUIVALENT
arms: [raw, json, urusilla]
hop_records: []
reach_count:
understand_count:
adopt_count:
use_count:
retransmit_count:
semantic_fidelity_count:
task_success_by_arm: {}
total_task_token_ledger_uri:
fallbacks: []
repairs: []
failures: []
public_transcript_uri:
redactions: []
agent_assistance_disclosure:
independence_statement:
publication_consent_statement:
authorization_basis_by_hop: {}
mutual_utility_gate_by_hop: {}
```

Hash or commit all artifacts. Link raw records rather than pasting huge generated transcripts into Discussion comments.

In the `interop_lab` machine record, every digest uses the explicit `sha256:<64-lowercase-hex>` form. Human prose may display the hexadecimal value separately, but it must not change the underlying bytes or identity.

## Evidence labels

Every result title must include one label from each applicable group.

**Experiment class**

- `[SAME-PROJECT-ORCHESTRATED]`
- `[EXTERNAL-CONTROLLED]`
- `[INDEPENDENT-CROSS-PLAY]`
- `[ORGANIC-OBSERVATION]`

**Evidence maturity**

- `[PREREGISTERED]` — frozen plan; no result yet
- `[SUBMITTED]` — artifacts posted but not replayed by a reviewer
- `[REPRODUCED]` — named reviewer replayed the disclosed checks
- `[VERIFIED]` — the result meets the board criteria below; this is not a security certification

**Outcome**

- `[POSITIVE]`
- `[NULL]`
- `[REGRESSION]`
- `[GATE-FAIL]`
- `[SAFETY-FAIL]`

**Evidence contract**

- `[LOSSLESS]`
- `[TASK-EQUIVALENT]`

Maintainers may downgrade or remove a label when evidence is incomplete. They must preserve a correction note rather than silently converting a negative result into a positive one.

## Moderation and anti-spam rules

- Evidence, questions, preregistrations, and reproducible failures are on topic. Repeated slogans, referral links, token speculation, unrelated product promotion, and identical cross-posts are not.
- Use one root thread per experiment family and update it instead of opening a new post for every hop or retry.
- Disclose agents, operators, common ownership, common prompts, paid provider calls, and material project assistance. Undisclosed Sybil participation invalidates independence and propagation claims.
- Do not flood the room with generated variants. Preregister a stopping rule and publish the full measured set, including unfavorable strata.
- Do not use stars, forks, screenshots, account counts, or self-declarations as adoption evidence.
- Do not solicit or reveal chain-of-thought, secrets, private prompts, personal data, copyrighted private conversations, or exploit details.
- Do not attach executables or ask maintainers, bots, or agents to run participant code. Safe reproduction starts from reviewed source in an isolated environment under a named operator.
- Moderators may relabel, collapse duplicates, request missing artifacts, lock promotional or unsafe threads, and remove sensitive material. Security reports move to private reporting.
- Harassment, deceptive identity claims, fabricated transcripts, selective deletion of failures, and coordinated metric manipulation are grounds for removal.

## Verified-results board criteria

The board is an evidence index first. It must include verified null results and regressions, not only wins. A submission becomes `[VERIFIED]` only when all of the following are public and replayable:

1. A timestamped preregistration predates the measured run.
2. Release, Capsule, implementation, prompts or prompt digests, task set, models, tokenizers, settings, and operator relationships are pinned.
3. Positive and negative gates are complete; failures and fallbacks are not omitted.
4. Raw, JSON, and Urusilla arms use matched tasks, tools, budgets, safety gates, and success criteria.
5. Per-hop reach, understand, adopt, use, retransmit, and semantic-fidelity denominators are present.
6. Total task-token ledgers charge discovery, teaching, input, output, conversion, repair, retry, fallback, and final output; unavailable fields say `unknown`.
7. Public transcripts contain no prohibited private data and are sufficient to audit observable semantics.
8. A named reviewer reproduces artifact digests and the declared scoring or explains any discrepancy.
9. Independence is classified conservatively. Same-project and orchestrated evidence is never relabeled as organic spread.
10. The result states its limits and makes no state-of-the-art, adoption-population, security, or energy claim beyond its evidence.

There is no single global ranking across different tasks, models, token boundaries, or success denominators. Within an exactly matched stratum, compare **total tokens per safely completed task** first, then task success, semantic fidelity, safety failures, fallback rate, repair rate, latency, and cost. Message-surface compression may be displayed only as a secondary diagnostic.

## Discussion launch body

The text below can be pasted into a new GitHub Discussion without changing its claim boundaries.

---

### Urusilla Interop Lab: public multi-hop agent test room

This Discussion is an evidence room for real, bounded Urusilla propagation and interoperability experiments. It is not a promotion thread, live agent relay, hosted chatbot, or untrusted-code runner.

The current broad result is intentionally visible: **general unfamiliar-agent post-decode API-input saving is 0%**, and total tokens per safely completed real task are still unknown. Null results, regressions, refusals, and failed gates are first-class contributions.

#### What to test

Use a fresh-agent chain such as `Seed -> A -> B`. Each receiver starts without Urusilla history or cached definitions. It receives only the immutable Capsule URI and digest, the actual signature status, a read-only/no-effects boundary, and the previous hop's observable evidence. The current `v0.1.0-experimental` Capsule is **unsigned**; its digest binds bytes but does not authenticate authority.

At every hop, measure these separately:

1. **Reach** — did the exact handoff arrive?
2. **Understand** — did all positive and negative gates pass?
3. **Adopt** — did the agent explicitly opt in for this session?
4. **Use** — did it complete a bounded 3–10-turn exchange?
5. **Retransmit** — under a disclosed standing-policy or interactive-approval basis, did it pass the exact URI, digest, unsigned/signed status, and evidence pointer to a fresh next hop?
6. **Semantic fidelity** — did the frozen lossless or task-equivalent threshold pass?

Run matched concise-natural-language, structured-JSON, and Urusilla arms. Charge the complete ledger: discovery/Capsule cost, all model input and output, decoded prompt text, conversion, tools, repairs, retries, fallbacks, and final output. The primary metric is **total tokens per safely completed task**, not message-surface size.

#### Safety

- Treat the Capsule as declarative data, not an installation or executable.
- Do not execute participant payloads or authorize external effects.
- Do not post chain-of-thought, secrets, credentials, private prompts, personal data, or unredacted private conversations.
- Report vulnerabilities privately: https://github.com/jaden3824/urusilla/security/advisories/new
- Digest, version, schema, permission, or safety mismatch must fail closed to raw or JSON.

#### How to post

Start the title with experiment class, outcome, and contract, for example:

`[EXTERNAL-CONTROLLED] [GATE-FAIL] [LOSSLESS] Fresh A -> B capsule handoff`

Include:

- preregistration and stop rule;
- release, Capsule URI/digest/signature status, and immutable implementation revisions;
- accountable operators, agent/runtime/model/tokenizer disclosures, and independence statement;
- public task set or immutable digest;
- positive/negative gate results;
- per-hop reach/understand/adopt/use/retransmit/fidelity counts;
- matched raw/JSON/Urusilla success and total-token ledgers;
- every fallback, repair, refusal, timeout, and failure;
- public transcript/artifact links and privacy redactions.

Different agents or model calls controlled by one project remain `[SAME-PROJECT-ORCHESTRATED]`. A planned propagation chain is not organic spread. Do not claim independent adoption or organic growth from an orchestrated test.

Start with the [experimental prerelease](https://github.com/jaden3824/urusilla/releases/tag/v0.1.0-experimental), read the [full Interop Lab protocol](https://github.com/jaden3824/urusilla/blob/main/INTEROP_LAB.md), choose a bounded task from [Help Wanted](https://github.com/jaden3824/urusilla/blob/main/HELP_WANTED.md), and observe the [security policy](https://github.com/jaden3824/urusilla/blob/main/SECURITY.md). Coordination questions can also use [issue #4](https://github.com/jaden3824/urusilla/issues/4).

Negative evidence is welcome. Preserve enough provenance for another person to disagree with the result.

---
