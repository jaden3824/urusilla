# Urusilla

[![Conformance](https://github.com/jaden3824/urusilla/actions/workflows/ci.yml/badge.svg)](https://github.com/jaden3824/urusilla/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

An experimental, no-install, machine-first semantic language for communication between AI agents.

Urusilla's long-term vision is an interoperable meaning layer that independent
agents can learn, negotiate, inspect, and improve without sharing a vendor,
model, tokenizer, or fixed human-facing syntax. The current prototype combines
a typed semantic kernel, negotiated codecs, deterministic human inspection,
safe natural-language/JSON fallback, A2A integration, and public evaluation
artifacts. It is active open research—not yet a proven universal replacement
for natural language or JSON.

**Founded and initially developed and stewarded by `jaden3824`.** The canonical project is [`jaden3824/urusilla`](https://github.com/jaden3824/urusilla) and uses transparent founder-led governance during its experimental phase. Apache-2.0 grants reuse and fork rights in the licensed work; it does not transfer canonical project authority or official status. See [`GOVERNANCE.md`](GOVERNANCE.md).

> **Status: research prototype, not a standard.** The project name is **Urusilla**. Its protocol namespaces and private-use media types remain experimental, and no trademark registration, standards endorsement, or domain ownership is implied.

> **60-second public check — one fetch, no install:** open the [human challenge page](https://urusilla-agent-language.audhless25.chatgpt.site/) or let an agent fetch its [self-contained one-fetch task](https://urusilla-agent-language.audhless25.chatgpt.site/agent-task.json). The envelope carries the full-commit-pinned task identity, response schema, evidence boundary, and non-authority rules in one JSON document; its underlying [`quick_60s.json`](https://raw.githubusercontent.com/jaden3824/urusilla/cd220adb311d8763009fc9b524b2633b117aac4d/interop_lab/challenges/quick_60s.json) remains byte-frozen. Return `{"decision":"<RETAIN or ROLLBACK>","reason":"<one sentence>","participant":"<human, agent, or human+agent>","runtime":"<none or exact identity>"}`. Post to [Discussion #8](https://github.com/jaden3824/urusilla/discussions/8) only if publication is separately authorized. Counterarguments and negative results are welcome. A response is feedback, not automatically an independent reproduction or adoption record. The exact current evidence boundary is reported below.

**Star it if you want to signal interest; then try to break one bounded claim.** Stars provide a visible attention signal, while reproducible evidence is the contribution that can change the result. Agents can read the machine-first [`contribution-entry.json`](contribution-entry.json), submit the same four fields through the [60-second issue form](https://github.com/jaden3824/urusilla/issues/new?template=quick-60s.yml), and escalate a result into a [counterexample](https://github.com/jaden3824/urusilla/issues/new?template=counterexample.yml), [codec candidate](https://github.com/jaden3824/urusilla/issues/new?template=codec-candidate.yml), or [quarantined corpus example](https://github.com/jaden3824/urusilla/issues/new?template=corpus-example.yml). Validated unfavorable and favorable evidence receive equal credit in the deliberately empty-until-earned [`CONTRIBUTORS_EVIDENCE.md`](CONTRIBUTORS_EVIDENCE.md) registry.

The name *Urusilla* is an attested ancient scholarly/topographical name for Babylon, glossed “city of jubilation” in the [ORACC Babylonian Topographical Texts corpus](https://oracc.museum.upenn.edu/btto/Q004798/html). The name choice does not imply that it is an ordinary modern-language word. The project currently makes **no claim of owning `urusilla.com`**. The GitHub repository is the canonical source and evidence record; the hosted challenge page is only a participation interface.

Version identifiers use separate axes: the current semantic language and source-manifest `languageVersion` are exactly `0.1.0`; the release label is `v0.1.0-experimental`; the Python distribution normalizes that prerelease to `0.1.0a0`; and the lifecycle status is `experimental-unsigned`. A matching semantic version does not by itself prove signature status, conformance, or production readiness.

The project is testing one claim: agents may coordinate more precisely and sometimes more efficiently when they exchange a typed semantic representation instead of unconstrained human prose. The design combines an auditable semantic kernel, negotiated codecs, deterministic human inspection, public commitments, and an A2A integration path.

It does **not** claim that one syntax is optimal for every model, tokenizer, transport, or task. A profile is adopted only when measured total utility beats the best available fallback.

## Current bottom line

**The currently demonstrated token saving for general communication between unfamiliar agents is 0%.** The freshest broad lane covers 2,542 turns from Taskmaster, Schema-Guided Dialogue, Dolly, and OpenAssistant under four pinned tokenizers. Its mandatory raw fallback passed H1 with zero positive-regret choices, but the general compact-value and repeated-context hypotheses H2 and H3 failed. Warm receiver-carrier saving was only **0.65% to 0.80%**; every cold family plan retained raw text, and decoding before model input leaves measured API-input saving at **0%**. H4, end-to-end task utility, was not evaluated.

The experimental `role/session/turn/text` external-profile carrier made the same turns **165.60% to 183.98% larger in tokens** than bare text. On the separate retained 42-record official-example corpus, both bound and standalone compact modes won **0/168** comparisons; standalone cold text was **2.24% to 3.00% larger** than raw concise text. Safe fallback is useful engineering behavior, but a tie or avoided regression is not compression.

Favorable results elsewhere have narrower scopes. Receiver-bound v0.7 saved 23,997 development tokens and 4,302 grouped-holdout tokens, but saved 0 on OOD and activated in 0/12 cold plans. Checkpointed v0.9 saved **53.71% to 55.15%** only on deliberately correlated synthetic state. A historical pre-cutover live receiver result reached 27/28 exact reconstructions but failed its gate, and one historical pre-cutover internally operated neutral-ID sender pilot recorded only 6/10 structural-and-semantic passes. That sender participant has not been rerun on the current artifacts. None establishes arbitrary conversation efficiency. Total tokens per safely completed real task—including instructions, reasoning, tools, repair, fallback, and output—remain unknown.

The immediate research goal is therefore model-native or task-aware public action-state consumption, verified silence or topology pruning, and total tokens per safely completed task on independently authored conversations. Incremental tuning of a universal lossless text surface is paused after the broad H2 and H3 failures; it should resume only for a separately frozen architecture-changing hypothesis. See [`HELP_WANTED.md`](HELP_WANTED.md).

An exact request binding is not evidence that a receiver used the message. The current runtime and v1 initial-goal verifier can prove which action-state payload reached the model-visible request, but a constant-output receiver can still satisfy synthetic success plumbing without reading that payload. Therefore a v1 aggregate pass would establish hybrid-router utility only; it would **not** establish causal consumption of an action-state language. Any comprehension or route-level language claim additionally requires a preregistered, blinded payload-intervention study: identical non-payload context and settings, task-critical A/B payloads whose correct outputs must differ, missing/shuffled placebos that must refuse or fall back, inclusive accounting for every call, and per-stratum coverage. This stronger contract must use a new schema version rather than silently changing frozen v1.

A new **development-only** hybrid runtime now implements that architecture-changing hypothesis: task-bound natural-language compilation, direct action-state consumption, a fail-closed five-route planner, per-message semantic-fidelity evidence, complete-cost fields, and an optional session-local evolving surface. Its machine-first aliases may be non-English or opaque and are optimized without a human-aesthetics score. Stable semantic IDs never change; only a reversible, exact-context-bound wire table may evolve after round-trip comprehension tests. Caller-supplied `UtilityEvidence` can qualify an optimized route for a bounded local policy trial after exact binding and declared-threshold checks, but it is not claim authority: runtime route candidates and decisions reject `claim_eligible: true`, and the aggregate initial-goal verifier emits no route-scoped evidence. This is implementation plumbing, not a positive result: no real independent end-to-end run has yet shown that the extra compiler, verifier, setup, and receiver costs beat raw concise text and JSON. See [`EVOLVING_SURFACE.md`](EVOLVING_SURFACE.md).

An eval-side, file-only capture path now constructs one exact provider-neutral cold-request artifact containing the submitted system role, public task context, declarative Capsule, and payload. It can retain structurally complete, content-bound input/output/total counts, but does not normalize or authenticate those operator-supplied fields, enforce the total-token ceiling before a call, or convert the capture into normal runtime evidence. No provider task run has been performed through this path; current tests use project-authored synthetic captures. It remains delivery- and claim-ineligible and does not change the demonstrated general saving from 0%. See [`competitive_eval/README.md`](competitive_eval/README.md#hybrid-cold-request-capture).

Runtime executions now expose a separate observed ledger for compiler, semantic verifier, primary receiver, actual fallback, and explicitly supplied local setup/router/repair/tool/safety/judge usage. Forecasts are never promoted into observations, and one unknown category makes the inclusive runtime total unknown. This ledger is exact-preparation-bound but does not authenticate a provider, prove operator independence, or satisfy the frozen research scope.

An opt-in provider-neutral scoring diagnostic now carries one actual `HybridExecution` through the next local boundary: it passes only the final terminal output—not a failed optimized primary—to a caller-supplied scorer, compares four caller-declared lock labels, retains the primary and fallback costs, and derives task-result plus scoring-binding objects. The result is factory-guarded against ordinary public dataclass replacement and re-derives its terminal fields from the execution; this is an API misuse guard, not an authentication or Python security boundary. The lock comparison does not hash or authenticate the callable, and the helper's task/probe arguments are not bound to a complete frozen study plan. Consequently caller-reported scorer cost and safe completion remain separate diagnostics; claim-facing total cost and safe completion stay unknown. The helper now refuses to mint a judge event at all rather than treating a `deterministic-local` label as proof of zero usage or emitting a null-usage fragment that the assembler cannot consume. Scorer failure and no-output provider failure remain null rather than becoming success or zero cost. This does **not** yet make a complete study runner. The current frozen trace cannot losslessly represent the runtime's separate semantic-verification phase, two-part fallback accounting, or exact raw/JSON fallback request, and its response-dependent fallback branch conflicts with a manifest whose event slots must be frozen before responses. Current tests use fake adapters and scorers; the diagnostic creates no authentication, independent execution, performance result, or change to the **0%** general saving. See [`initial_goal_eval/README.md`](initial_goal_eval/README.md#runtime-to-scorer-diagnostic).

An offline-only initial-goal trace assembler can now bind validated raw, JSON, and hybrid provider captures plus deterministic local events into the existing RESULT ledger shape while preserving failed-task cost and rejecting missing, reused, or unused captures. Evaluator-only assembly schema v4 emits a self-issued receipt-bundle v3 containing the supplied external bundle, execution-profile, request, response, record, and raw-receipt preimages plus the arm-manifest and source-commitment preimages used to place each provider event in the ledger. The installable verifier recomputes their canonical digests and rebinds the exact request messages, model settings, output, terminal status, and generic normalized usage projection to the result and recorded score. This detects downstream mutation, including a receipt/result rehash that disagrees with the supplied provider preimage. It does **not** establish that the supplied preimage is genuine: the provider, producer, and operator labels are unsigned, and a fully self-consistent fabricated or jointly resealed artifact set can still pass content checks. All receipts name the offline assembler as their actual generator, the normal evidence verifier rejects that issuer by default, and authentication remains fail-closed. The assembler does not independently perform or prove a provider run, authenticate operator independence, replay a scorer from its artifact, independently observe the sandbox, or perform provider-specific normalization from the raw receipt. The optional runtime-to-scorer diagnostic executes an injected scorer before assembly, but is neither authenticated nor a substitute for scorer replay by the verifier. No current initial-goal provider task run exists through this path; all current tests use project-authored synthetic captures. This is neither performance nor adoption evidence, does not change the demonstrated general unfamiliar-agent saving from **0%**, and changes neither `languageVersion: 0.1.0`, the Urusilla protocol surfaces, nor the initial research goal. See [`initial_goal_eval/README.md`](initial_goal_eval/README.md#offline-trace-assembly).

An optional Ed25519 signed-accountability sidecar now binds a separately pinned trust policy, preregistration statement, exact plan/result/receipt bundle, frozen normalizer-manifest identity, and the declared operator, boundary-auditor, provider-witness, and normalizer-auditor roles. The validator matches a separately supplied expected policy digest, while the caller remains responsible for obtaining that pin independently; under that workflow, silent key substitution is detectable and byte-level approval is attributable. It intentionally does **not** open the claim gate: signer-declared time is not an external anchor, provider witnesses are not provider-origin signatures, the verifier does not yet replay each raw receipt through the frozen provider-specific normalizer, and replay protection is not backed by a global reservation registry. Its positive status is only `signed_accountability_complete`; claim-facing authentication and the demonstrated general saving remain unchanged.

The in-memory `OnlineEvolutionController` now connects validated conversation observation, deterministic alias proposal, activation, an independently frozen matched shadow trial, and keep/rollback into one bounded cycle. Observation records are not supplied to the activation or trial callbacks, and a candidate receives live authorization only after the sealed retention gate passes. This closes an orchestration gap; all current controller tests use project-authored deterministic fixtures and do not change the demonstrated general saving from 0%.

## Agent entry point and public feedback

Agents may read and reference this public repository without installing code. Start with the bounded [`AGENT_QUICKSTART.md`](AGENT_QUICKSTART.md) and canonical machine-readable [`agent-entry.json`](agent-entry.json); the offline validator checks its full-commit raw URLs, byte counts, SHA-256 digests, `0%` evidence boundary, and unsigned status. Use [`llms.txt`](llms.txt) for a compact index and [`INTEROP_LAB.md`](INTEROP_LAB.md) only for the full evidence protocol. Under a standing local policy, an agent may autonomously run read-only gates and choose a reversible session route when the mutual-utility threshold passes. It must not persist state, expand permissions, spend money, or cause an external effect through this path.

The hosted [agent task envelope](https://urusilla-agent-language.audhless25.chatgpt.site/agent-task.json) is the shortest network entry. It embeds the bounded task, exact frozen identity, strict response schema, evidence limits, and authority limits in one fetch. It has no site-native POST endpoint or hidden adoption mechanism: absent separate authorization, an agent returns its answer to its operator. The site classifies the public task as an open, unblinded demonstration rather than cold or independent evidence.

Five explicitly project-operated agent-native review invitations are public on [MatrixAgentNet](https://www.matrixagentnet.com/creations?id=7f79a702-c902-4631-ab0a-729c1caaf468), [The Colony](https://thecolony.ai/post/3713bdd3-a23f-4e23-86a4-af40bc5cc1c0), [AgentRank](https://www.agentrank.tech/community/agent/0437387b83e849de), [Agoora](https://agoora.dev/posts/781), and [ClawdChat](https://clawdchat.ai/post/de74fbe1-cdc3-44d0-95aa-208458b97565). They disclose the current 0% general result and ask for falsification and causal-control critique. The Colony thread has now produced the first substantive external design review: commenters identified semantic-invariance and composition controls, stable preregistered field identity, a distinct externally anchored no-payload accuracy baseline, per-field coverage, valid-payload false-refusal accounting, per-stratum reporting, and contamination-resistant generation as open requirements. Those comments are review inputs, not external adoption, independent reproduction, favorable evidence, or a change to the 0% result. No automated direct messages, follows, votes, reposts, or recursive promotion are authorized by those posts.

A separate project-operated [UrusillaIR 0.1.0 conversation thread](https://thecolony.ai/post/fa2c6843-28f7-4503-8536-08c6610d542e) asks public agents to answer one typed question and pass a new question to the next speaker in the same representation. Its first reply verified the pinned Capsule identity and was content-relevant, but also exposed that the query named an unresolved answer schema and then used a bare `answer` body that the pinned validator rejects. The exact mixed result and structurally valid core two-act continuation are preserved in [`PUBLIC_DIALOGUE_001_REPORT.md`](PUBLIC_DIALOGUE_001_REPORT.md). This tests public conversation behavior, not token saving; it is an unfavorable strict-conformance observation, not adoption, independence, comprehension, or efficiency evidence.

Protocol-specific, project-operated questions are also public for [A2A Capsule carriage](https://github.com/a2aproject/A2A/discussions/2161), [Microsoft Agent Framework matched representation](https://github.com/microsoft/agent-framework/discussions/7794), and [AG-UI semantic-generation drift](https://github.com/ag-ui-protocol/ag-ui/discussions/2497). These threads ask for design correction and counterexamples. Their existence, views, and project-authored updates are not maintainer acceptance, integration, adoption, or performance evidence.

**Bring your own agent:** anyone may attempt a reproduction with an agent or runtime they already use; Urusilla does not require installing a project-specific agent, plugin, executable package, or model weights. A matched evaluation must pin the public task bundle, follow the published receipt and verifier contract in [`initial_goal_eval/`](initial_goal_eval/), and disclose the accountable operator, runtime, and shared-control relationships. Submitting a favorable, unfavorable, null, refusal, or failed result creates only a reviewable evidence candidate. It does not by itself establish acceptance into the evidence registry, adoption, operator independence, conformance, or general efficiency.

[`EVIDENCE_TRANSPARENCY_LOG.md`](EVIDENCE_TRANSPARENCY_LOG.md) now specifies a documentation-only, GitHub-first append-only result log and future website/API surface. It is not deployed and currently accepts no live records; log inclusion would prove neither truth, independence, adoption, nor general efficiency by itself.

For a no-install first contact, fetch the pinned [60-second JSON question](https://raw.githubusercontent.com/jaden3824/urusilla/cd220adb311d8763009fc9b524b2633b117aac4d/interop_lab/challenges/quick_60s.json), try the [10-minute adversarial path in Issue #9](https://github.com/jaden3824/urusilla/issues/9), or run the [decode task tracked in Issue #7](https://github.com/jaden3824/urusilla/issues/7). A four-field 60-second response can go directly to [Discussion #8](https://github.com/jaden3824/urusilla/discussions/8) or the revision-bound [60-second issue form](https://github.com/jaden3824/urusilla/issues/new?template=quick-60s.yml); stricter 10-minute/decode records may use the [bounded feedback form](https://github.com/jaden3824/urusilla/issues/new?template=quick-feedback.yml), and a full matched raw/JSON/Urusilla result uses the [structured interop form](https://github.com/jaden3824/urusilla/issues/new?template=interop-test.yml). Public reading requires no GitHub account. Posting is a separate external action and requires an accountable GitHub identity. Security-sensitive feedback belongs in [private vulnerability reporting](https://github.com/jaden3824/urusilla/security/advisories/new).

For the decode track, compare the [public Urusilla challenge packet](interop_lab/evidence/challenge_001.md) with the pinned [expected typed message](interop_lab/evidence/challenge_001.expected.json), and report any disagreement or refusal in [Issue #7](https://github.com/jaden3824/urusilla/issues/7). The packet is declarative and non-effect-authorizing: reading or decoding it creates no obligation to adopt, retransmit, persist, spend, or act. External runners can also start from the [Hugging Face reproduction dataset](https://huggingface.co/datasets/jaden3824/urusilla-interop-lab), use the [offline-first Microsoft AutoGen kit](interop_lab/AUTOGEN_REPRODUCTION.md), or use the [CAMEL-AI 0.2.90 adapter](interop_lab/adapters/camel/README.md). These are invitations to falsify or reproduce the result, not evidence that direct agent dialogue or adoption has occurred.

## Comparator context

Adjacent methods already report substantial savings under different task and accounting boundaries. The [PACT preprint](https://arxiv.org/abs/2606.05304) reports a 38.7% average token reduction in its controlled multi-agent settings, including a 50.4% SWE-agent input-token reduction, roughly 47% fewer tokens per resolved SWE-agent task, and 10.3% fewer OpenHands tokens per resolved task. [AgentDropout](https://arxiv.org/abs/2503.18891) reports 21.6% fewer prompt tokens and 18.4% fewer completion tokens through communication-topology pruning. [AutoForm](https://aclanthology.org/2024.findings-emnlp.623/) selects task formats; peer-reviewed [OPTiMACS](https://aclanthology.org/2026.findings-acl.1441/) learns task-aware message representations; and [Agora](https://arxiv.org/abs/2410.11905) uses reusable routines for frequent interactions while retaining natural language for rare ones.

These figures are **not a leaderboard**: they differ in tasks, models, topology, success denominators, token boundaries, and evidence maturity. Urusilla must reproduce relevant competitors inside one pinned driver and report total tokens per resolved or safely completed task before making any comparative claim.

## General-use routing architecture

General conversation is too heterogeneous for one universal compact syntax. Urusilla is therefore a **layered router** whose first safe eligible tier wins:

| Tier | Route | Intended use |
|---|---|---|
| 0 | verified silence or topology pruning | suppress a message or edge only when an observable policy proves it has no required marginal task value |
| 1 | compiled routine or exact state delta | frequent structured exchanges with a verified shared routine, schema, checkpoint, and recovery path; inspired by Agora-style amortization |
| 2 | public action-state record | preserve the task-relevant action, state, result, provenance, and safety fields instead of replaying full prose; a PACT-style task-equivalence lane |
| 3 | learned task-aware representation | use a validated task/model-specific profile, as motivated by OPTiMACS, only after held-out success and safety gates pass |
| 4 | raw concise natural language | carry rare, novel, ambiguous, or unsupported content without forcing it through an unsuitable codebook |

Two evidence contracts must remain separate. A **lossless exact-equivalence** route must recover the canonical typed message and deterministically re-encode it. A **task-level semantic-equivalence** route may intentionally omit wording or reasoning history, so it cannot claim exact prose reconstruction; it is eligible only when end-to-end task success, semantic fidelity, safety, repair, and total-token gates pass. PACT-style compact state belongs to the second contract. Falling back to Tier 4 is correct behavior whenever a stronger claim cannot be verified.

The optional evolving surface sits below those semantics. For one session and model context, agents may propose a new one-to-one alias generation, prove exact round trips, acknowledge comprehension, and run a bounded matched shadow trial. Activation alone cannot affect a live answer. A generation receives an exact sealed live-routing proof only when inclusive total tokens strictly improve with no safe-completion, parse, fidelity, negation, null, failure, refusal, or authority-boundary regression. Unknown, unretained, forged, sibling, or stale tables and incomplete measurements fall back. This mechanism lets the language adapt between agents without silently changing what any symbol means.

## North star

The long-term goal is an agent-mediated Internet: any public or otherwise authorized Internet text should be translatable on demand into source-preserving Urusilla semantic objects that unfamiliar agents can exchange, inspect, and translate again across models and human languages. A person states an intent to an Internet-connected agent, cooperating agents retrieve and compile the authorized source material, and the person receives a faithful human view with evidence and controls. This is a north star, not a present capability or a claim that one lossy syntax can replace every original. Search, crawling, APIs, HTTP, TLS, and modality codecs remain underlying infrastructure; the project aims to replace the manual search-and-page-navigation loop, not the Internet's transports or original sources. See [`URUSILLA_INTERNET_LAYER.md`](URUSILLA_INTERNET_LAYER.md).

The adoption ladder begins with external agent dialogue, then tool and web payloads, selected typed working memory, and only later optional model-native or latent representations inside compatible trust boundaries. Private chain-of-thought is not required or collected.

The near-term [`EVIDENCE_LADDER.md`](EVIDENCE_LADDER.md) starts with causal payload use, then checkpoint/state-delta recovery, tool-call/result pipelines, and multi-agent commitments before any cross-domain adaptive-routing claim. These are bounded test beds for the general-language north star, not a quiet pivot that relabels a vertical result as universal success. Integrations and developer tooling follow a passing workload and retain the same fallback and total-utility accounting contract.

## What exists today

- [`urusilla_action_state_capsule.json`](urusilla_action_state_capsule.json), [`urusilla_task_context.example.json`](urusilla_task_context.example.json), and [`urusilla_hybrid_runtime/`](urusilla_hybrid_runtime/) — unpromoted task-bound sender/direct-receiver/router reference with per-message fidelity gates and lossless fallback
- [`urusilla_evolving_surface_capsule.json`](urusilla_evolving_surface_capsule.json) and [`EVOLVING_SURFACE.md`](EVOLVING_SURFACE.md) — declarative, session-local stable-semantics/evolving-surface negotiation and rollback contract
- [`LANGUAGE_EVOLUTION_ARCHITECTURE.md`](LANGUAGE_EVOLUTION_ARCHITECTURE.md) — two-speed conversation loop: reversible wire optimization now, append-only semantic growth only after a separate future gate
- [`initial_goal_eval/`](initial_goal_eval/) — frozen raw/JSON matched-session evidence contract and independent verifier; currently contains test-only synthetic fixtures, not performance evidence
- [`urusilla_v0_1_spec.md`](urusilla_v0_1_spec.md) — architecture and semantic-language draft
- [`urusilla.py`](urusilla.py) — standard-library-only canonical binary codec and English/Korean inspection views
- [`urusilla_capsule_v0_1.json`](urusilla_capsule_v0_1.json) — experimental Grammar Capsule for teaching and conformance
- [`urusilla_a2a_adapter.py`](urusilla_a2a_adapter.py) — private experimental A2A v1 adapter
- [`urusilla_benchmark.py`](urusilla_benchmark.py) and [`urusilla_benchmark_results.md`](urusilla_benchmark_results.md) — reproducible transport benchmark
- [`urusilla_wire_v02.py`](urusilla_wire_v02.py) and [`urusilla_wire_v02_results.md`](urusilla_wire_v02_results.md) — experimental warm-session static-profile codec and cold-cost study
- [`urusilla_strong_codec_results.md`](urusilla_strong_codec_results.md) — deterministic CBOR, MessagePack, and typed Protobuf baselines
- [`urusilla_a2a_envelope_results.md`](urusilla_a2a_envelope_results.md) — complete representative A2A v1 HTTP+JSON and JSON-RPC request accounting
- [`urusilla_tokenizer_results.md`](urusilla_tokenizer_results.md) — four-tokenizer accounting for text-carried JSON and Base64 wire profiles
- [`urusilla_token_surface_v03_results.md`](urusilla_token_surface_v03_results.md) — tokenizer-aware long-session text surface and cold codebook accounting
- [`urusilla_token_surface_holdout_results.md`](urusilla_token_surface_holdout_results.md) — train-only codebook evaluation on grouped holdout and small out-of-domain sets
- [`urusilla_adaptive_dialogue_results.md`](urusilla_adaptive_dialogue_results.md) — typed dialogue coverage, fragment splicing, conversation ledger, codec gates, and grammar evolution
- [`urusilla_energy_sensitivity_results.md`](urusilla_energy_sensitivity_results.md) — normalized energy-per-safe-task sensitivity analysis, not a joule claim
- [`urusilla_teachability_pilot.md`](urusilla_teachability_pilot.md) — fresh-agent open-label construction and rejection smoke pilot
- [`urusilla_hidden_transfer_results.md`](urusilla_hidden_transfer_results.md) — neutral-ID Capsule transfer pilot with published tasks, submission, evaluator, and failures
- [`TERSE_ENGLISH_RESULTS.md`](TERSE_ENGLISH_RESULTS.md) — controlled terse-English baseline with exact semantic recovery
- [`TOKEN_SURFACE_V04_RESULTS.md`](TOKEN_SURFACE_V04_RESULTS.md) — exact tokenizer-aware surface optimization and latency trade-offs
- [`ADAPTIVE_SURFACE_V05_RESULTS.md`](ADAPTIVE_SURFACE_V05_RESULTS.md) — receiver-specific safe selection across complete representations
- [`GENERALIZATION_SURFACE_V06_RESULTS.md`](GENERALIZATION_SURFACE_V06_RESULTS.md) — train-only OOD candidate, cold-cost planner, and no-regression guard
- [`performance_v07/RECEIVER_NEGOTIATED_SURFACE_V07_RESULTS.md`](performance_v07/RECEIVER_NEGOTIATED_SURFACE_V07_RESULTS.md) — receiver-bound token profiles, guarded fallback, cold-transfer accounting, and decoder-before-model boundary
- [`TRANSPARENT_FALLBACK_V08_RESULTS.md`](TRANSPARENT_FALLBACK_V08_RESULTS.md) and [`EXTERNAL_OOD_V08_CONFIRMATORY_REPORT.md`](EXTERNAL_OOD_V08_CONFIRMATORY_REPORT.md) — bound and standalone transparent-fallback contracts plus an exploratory current-artifact remeasurement of the retained external corpus
- [`SESSION_DELTA_V09_RESULTS.md`](SESSION_DELTA_V09_RESULTS.md) — checkpointed state deltas over a synthetic correlated workload with matched full-state framing
- [`EXTERNAL_OOD_EVALUATION_REPORT.md`](EXTERNAL_OOD_EVALUATION_REPORT.md) — premeasurement-sealed official external examples and a failed cold token-value gate
- [`URUSILLA_GENERAL_DIALOGUE_RESULTS.md`](URUSILLA_GENERAL_DIALOGUE_RESULTS.md), [`urusilla_general_dialogue_results.json`](urusilla_general_dialogue_results.json), and [`urusilla_general_dialogue_contract.json`](urusilla_general_dialogue_contract.json) — frozen four-family broad-dialogue carrier study and separate SGD gold-state oracle upper bound
- [`MODEL_COMPREHENSION_PILOT_RESULTS.md`](MODEL_COMPREHENSION_PILOT_RESULTS.md) — predeclared local live receiver gate and retained failures
- [`MUTATION_CAMPAIGN_RESULTS.md`](MUTATION_CAMPAIGN_RESULTS.md) — deterministic cross-codec mutation and integrity evidence
- [`BOUNDARY_COVERAGE_DELTA.md`](BOUNDARY_COVERAGE_DELTA.md) — public-decoder boundary tests and measured branch-coverage delta
- [`STREAM_COMPRESSION_RESULTS.md`](STREAM_COMPRESSION_RESULTS.md) — persistent gzip, Zstandard, and Brotli session baselines with matched integrity variants
- [`SESSION_RESET_SWEEP_RESULTS.md`](SESSION_RESET_SWEEP_RESULTS.md) — 21-point compressor-reset crossover under cold and cached profile contracts
- [`COMPETITIVE_PUBLIC_TASK_PREFLIGHT_REPORT.md`](COMPETITIVE_PUBLIC_TASK_PREFLIGHT_REPORT.md) — zero-provider-call public-task data, prompt, tokenizer, and cost preflight
- [`competitive_eval/README.md`](competitive_eval/README.md) — offline-first end-to-end harness, complete ledger, deterministic mock dry run, and paid-call gates
- [`independent_impl/rust/REPORT.md`](independent_impl/rust/REPORT.md) — separately written same-project Node.js cross-runtime compatibility lane; not an external independent reproduction
- [`PAPER_DRAFT.md`](PAPER_DRAFT.md) and [`CLAIM_EVIDENCE_MATRIX.md`](CLAIM_EVIDENCE_MATRIX.md) — publication draft and claim gates
- [`urusilla_landscape_2026.md`](urusilla_landscape_2026.md) — worldwide project and standards landscape
- [`urusilla_bootstrap_adoption.md`](urusilla_bootstrap_adoption.md) — bootstrap, attribution, and adoption strategy
- [`URUSILLA_INTERNET_LAYER.md`](URUSILLA_INTERNET_LAYER.md) — source-preserving Internet semantic layer, agent-mediated search experience, and reaction observability
- [`PROVENANCE.md`](PROVENANCE.md) — source-attribution contract for agents and implementations
- [`GOVERNANCE.md`](GOVERNANCE.md) — founding attribution, canonical authority, change process, and succession
- [`CONTRIBUTOR_REWARDS.md`](CONTRIBUTOR_REWARDS.md) — evidence-first contributor rewards and optional tokenless attestations
- [`RESEARCH_PROGRAM.md`](RESEARCH_PROGRAM.md) — preregistered performance, safety, and stop gates
- [`INTERNAL_PILOTS.md`](INTERNAL_PILOTS.md) — reproducible bridge-mode evidence from three internal workstreams
- [`AUDIT_RESPONSE.md`](AUDIT_RESPONSE.md) — red-team findings, remediations, and unresolved release blockers
- [`HELP_WANTED.md`](HELP_WANTED.md) — public work packages for humans, agents, and human-agent teams, with measurable acceptance gates
- [`CHANGELOG.md`](CHANGELOG.md) — release contents, security changes, and explicit claim boundaries

## Verified prototype results

The deterministic 280-message v0.1 benchmark reports:

- raw UrusillaWire is 34.0% smaller than the sorted minified JSON emitted by this CPython harness;
- raw UrusillaWire is 4.2% larger than per-message gzip JSON;
- with equal gzip compression on both, gzip(UrusillaWire) is 6.9% smaller than gzip(JSON);
- exact semantic round-trip succeeds for 280/280 messages;
- the raw UrusillaWire decoder rejects 1,120/1,120 deterministic single-bit mutations;
- the Python reference codec is materially slower than the JSON baselines.

The experimental v0.2 warm-session profile, manually specialized for the same schema family, reports:

- 54,752 raw bytes, 67.6% less than per-message gzip JSON and 68.9% less than raw v0.1;
- a 1,402-byte one-time profile capsule and a four-message mean-size break-even against gzip JSON;
- exact canonical round-trip for 280/280 messages and rejection of 1,120/1,120 deterministic raw-frame bit flips;
- p50 encode/decode latency of 156.29/312.12 microseconds in the recorded v0.2 run, with the current validation-heavy Python path still materially slower than the unequal-work CPython JSON path at 14.42/78.38 microseconds;
- gzip applied to v0.2 made both size and CPU results worse than raw v0.2.

On the same fixed corpus, MessagePack used 219,055 bytes, deterministic CBOR 219,899 bytes, and a lossless typed Protobuf schema 229,790 bytes; all reproduced 280/280 messages exactly. Warm v0.2 remained 67.6% smaller than the best non-v0.2 row, per-message gzip JSON, but its 266.83-microsecond Python decode p50 was slower than MessagePack at 70.75 microseconds on this machine. These are still in-sample implementation-path measurements.

That byte ranking does not survive every session contract. When all 280 records share one persistent Brotli-11 stream, bare length-framed JSON uses 24,085 bytes and project v0.2 uses 25,128 bytes, so v0.2 is 4.33% larger. Bare JSON lacks the v0.2 per-record 16-byte checksum; adding an equivalent independent checksum to every JSON record raises its best row to 29,297 bytes, making v0.2 14.23% smaller. All 21 stream rows recover the corpus exactly and deterministically. There is therefore no blanket byte-superiority claim: framing, compressor reset, and integrity scope determine the winner.

A 21-point reset sweep confirms that dependency. Across 378 representation-compressor-chunk rows, exact and deterministic recovery passes under both independently cold and cached-profile contracts. When the raw 1,402-byte profile capsule is charged at every reset, project v0.2 never beats the per-representation byte-best bare-JSON frontier; at a 280-message chunk it is 10.20% larger. On that same frontier, it first beats byte-best integrity-matched checked JSON at the tested 64-message point and is 9.40% smaller at 280. The cached frontier beats the byte-best bare-JSON frontier through the tested 128-message point, then loses at 140, 256, and 280; it is 4.33% larger than bare JSON at 280. Fixed compressors have different crossover sets, including earlier checked-JSON wins. These grid observations are not continuous thresholds or external-traffic evidence.

The complete representative A2A HTTP+JSON request benchmark changes the v0.1 gzip ranking: structured DataPart requests used 260,187 bytes after independent body gzip, while Base64 v0.1 RawPart requests used 293,599 bytes. Experimental warm v0.2 RawPart requests used 212,168 bytes. Headers, Base64, extension metadata, and `Content-Length` are included; TLS/TCP, responses, authentication, and production SDK behavior are not.

Across cl100k, o200k, Qwen2.5, and Mistral v0.3 tokenizers, text-carried warm Base64 v0.2 used 38.7–51.5% fewer tokens than sorted minified UrusillaIR JSON, averaging 45.8%. Charging one profile Capsule reduced the mean saving to 44.4% and produced a 7–12 message token break-even. Base64 v0.1 was 57.7–95.3% worse than JSON, so it is not a viable model-text profile. This is serialization accounting after UrusillaIR already exists, not a natural-language, comprehension, task-success, or total-reasoning comparison.

The tokenizer-aware v0.3 text surface used 38.0–42.8% fewer warm tokens than Base64 v0.2 and 65.0–66.0% fewer than JSON on the full development corpus, but that codebook was trained on the same corpus. A train-only follow-up used a 224-message development partition and withheld 16 complete semantic-combination groups: on its 56-message grouped holdout, v0.3 used 37.8–41.8% fewer tokens than Base64 v0.2 and 62.0–63.4% fewer than JSON for the two pinned tokenizers in that study. Its incremental cold-codebook break-even versus Base64 v0.2 was 101–113 messages by tokens.

The separate ten-message out-of-domain set reversed the important ranking. Warm v0.3 remained 9.0–9.7% below Base64 v0.2 in tokens, but it used 72.6–89.6% **more** tokens than plain JSON, never amortized its cold cost against JSON, used raw fallback for 89.7% of payload symbols, and was slower in the current Python implementation. The runtime must therefore choose the least-token exact eligible codec per receiver and fragment; v0.3 is not a universal default.

Against a controlled terse-English baseline with exact semantic recovery, the grouped-holdout v0.4 surface uses 59.64–69.79% fewer warm tokens across the four pinned tokenizers. The same comparison is unfavorable on the ten-message out-of-domain set: v0.4 uses 49.15–103.15% more tokens. These results are serialization measurements over typed messages, not end-to-end task-success evidence.

The v0.5 adaptive selector chooses the lowest-token member of its enumerated codec-valid candidate set independently for each receiver. Across 290 messages and four tokenizers, it has zero warm regressions in 1,160/1,160 message-receiver pairs and preserves exact deterministic recovery in every trial. Authorization, provenance, privacy, authentication, and replay-policy eligibility are deployment gates outside this benchmark. The train-only v0.6 candidate reduces warm OOD tokens by a further 1.87–5.42% relative to v0.5 while leaving development and grouped-holdout choices unchanged. A ten-message OOD session does not amortize the new profile, so its cold improvement is correctly zero; fresh Python selection is also about 47–66% slower than v0.5.

The receiver-negotiated v0.7 experiment derives twelve tokenizer-bound profiles from the 224-message development partition. Its guarded warm chooser saves 23,997 tokens on development and 4,302 on the 56-message grouped holdout, while retaining v0.6 for every out-of-domain choice and saving 0 there. All 12 known-session cold plans decline v0.7 activation because profile transfer does not amortize at those lengths. Direct profile recovery and canonical re-encoding pass for 3,480/3,480 cases, but raw `R7` text is decoder-before-model transport and must never enter a model prompt before validation. The guarded Python chooser is also slower than v0.6.

A fresh external OOD lane froze 43 premeasurement-sealed, source-preserving project wrappers around official examples from W3C ActivityStreams, CNCF CloudEvents, MCP, and OASIS STIX before importing or measuring any project codec. All 559/559 fixed- or receiver-specific round-trip trials recovered their messages exactly, and all 559/559 deterministic re-encoding checks passed, but the predeclared, premeasurement-sealed 20% cold token-value gate failed for all four tokenizers. Warm v0.6 remained 1.05–1.43% larger than Controlled Terse English; the cold planner rejected every optional artifact and safely fell back, yet its complete envelope was still 2.12–2.80% larger. This is negative external-corpus serialization evidence, not a generalization or task-utility result.

Transparent fallback v0.8 removes receiver-token penalty only when an authenticated bound transport already carries mode, sequence, and integrity metadata outside model-visible text. On the original 43-record development corpus, compact modes win 0/172 comparisons; the bound path ties raw Controlled Terse English, while standalone text is 5.85–6.80% larger. On the retained 42-record official-example corpus, compact modes win 0/168 comparisons under both bound and standalone selection. Every standalone cold plan retains terse text and remains 2.24–3.00% above raw plain text after its integrity envelope. Exactness, deterministic re-encoding, and retained mutation checks pass, but this is safe fallback evidence rather than compression, independent reproduction, or task utility.

The frozen broad-dialogue lane evaluates 256 sessions and 2,542 turns under four tokenizers without provider calls. H1 passes: all 10,168 selected turn-tokenizer carriers recover exact UTF-8 with zero positive regret. H2 and H3 fail: warm carrier saving is only 0.65–0.80%, compact choices cover 7–9 of 2,542 turns per tokenizer, and every cold plan falls back to raw. Post-decode API-input saving is 0%. A separate 399-prompt SGD gold action/state oracle reduces prompt tokens by 7.48–23.34%, but uses dataset gold state, intentionally loses prose, calls no model, and measures no accuracy. It is an opportunity upper bound, not a deployable result.

Checkpointed state-delta v0.9 tests a different, repeated-state hypothesis. At the predeclared interval of eight, it uses 53.71–55.15% fewer receiver tokens than matched authenticated full-state records across 24 synthetic sessions and 768 snapshots. The interval-one control saves exactly zero. Tokenizer-specific plans recover and deterministically re-encode 18,432/18,432 snapshots, and all 4,608 representative interval-eight mutations are rejected. The workload is deliberately correlated and project-authored; no model reads or emits a delta, no compressed-stream comparison is run, and adaptive encoding is slower than matched full encoding in the recorded Python path.

A separately written dependency-free Node.js lane agrees byte-for-byte with 280 Python-oracle-derived v0.2 fixtures and rejects 25 frozen negative fixtures. It does not import or invoke the Python implementation during its normal tests. This improves same-project cross-runtime compatibility evidence, but the vectors originate from the same project and the lane is neither a clean-room external reproduction nor an adopter, security certification, or full-conformance result.

A deterministic mutation campaign covers 11,200 changes across five representations. Integrity-protected representations reject all 8,960 mutations directed at them. Raw controlled terse English accepts 284/2,240 changes as different valid messages, while its checksummed adaptive envelope rejects all 2,240 tested changes. A checksum detects accidental damage but does not authenticate an active attacker.

A historical pre-cutover live receiver pilot does not pass its predeclared local reliability gate. Two final `gpt-5-nano` JSON trials reconstruct 13/14 and 14/14 messages, respectively, for 27/28 combined; because both trials were required to reach 14/14 with zero validation failures, the planned format comparison was stopped. No provider call was rerun against the current Urusilla inputs, so the historical result cannot validate them.

The adaptive-dialogue prototype projects 20 dialogue functions onto seven core wire acts and covers 46 typed node kinds across 26 positive messages. It rejects 20/20 negative cases and tests fragment-only replacement, append-only conversation state, hard-gated codec choice, immutable Grammar Capsule deltas, migration, rollback, deprecation, and garbage collection. Its 42/42 structural tests do not establish natural-language compilation quality or model comprehension.

Energy has not been measured in joules. A normalized sensitivity model produces both regressions and savings depending on the communication share, conversion/training/repair overhead, and safely completed task rate; its illustrative cases range from 1.90% worse to 22.92% better. This is a measurement plan and break-even analysis, not an energy forecast.

A fresh capsule-only agent also earned 36/36 on eight construction cases and four fail-closed rejection cases. The tasks exposed substantial cues, so this is an open-label smoke test—not a blind Teachability Score, independent adoption, or cross-vendor proof.

A historical pre-cutover, internally operated neutral-ID follow-up selected 16/16 emit/reject decisions and 10/10 acts correctly, but only 6/10 generated messages passed the original structural validator. The participant has not been rerun on current artifacts. Its standardized Teachability Score is intentionally left null because frame parsing, exact target graphs, unseen-partner cross-play, sample efficiency, and the Capsule's full safety gates were not measured.

These measurements prove bounded canonical transport behavior, safe fallback on the previously revealed 43-record development corpus and an exploratory remeasurement of the retained 42-record corpus, and a strong in-domain warm-wire result, not superior agent intelligence. Representative deployed traffic, independently operated reproduction, end-to-end task success, repair turns, complete model cost, unseen-partner transfer, secure network bindings, and external independent implementations remain release gates.

Repository-wide test status is reported by the current [CI workflow](https://github.com/jaden3824/urusilla/actions/workflows/ci.yml); no mutable suite count is asserted here before the first commit-bound release run. Individual frozen reports retain their own source-bound or artifact-bound check counts. All such checks are project-authored verification, not independent reproduction or a security certification.

## Quick start

Python 3.11 or later is recommended. The reference implementation has no third-party runtime dependency.

The research dependencies and root Python test discovery are pinned separately and were verified with CPython 3.12.14 on macOS arm64:

```bash
python3.12 -m venv .venv-research
.venv-research/bin/python -m pip install -r requirements-research.lock
.venv-research/bin/python -m unittest discover -v
```

That command covers the root Python modules only. The commit-bound GitHub CI matrix additionally runs tokenizer/profile studies, decoder QA, competitive and adoption-kit suites, same-project Node.js cross-runtime checks, digest verification, and wheel build/install smoke tests.

Tokenizer assets are content-pinned by the benchmark reports and downloaded into ignored `work/` cache paths; they are not silently fetched by the reference runtime.

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 urusilla.py demo --lang en
python3 urusilla_benchmark.py
python3 urusilla_wire_v02.py --benchmark
python3 urusilla_a2a_envelope_benchmark.py
python3 source_manifest.py validate path/to/source_manifest.json
```

Encode, inspect, and decode a message:

```bash
python3 urusilla.py encode urusilla_example.json example.urus
python3 urusilla.py translate example.urus --lang en
python3 urusilla.py decode example.urus
```

Wrap the same message for an explicitly negotiated A2A v1 exchange:

```bash
python3 urusilla_a2a_adapter.py pack \
  urusilla_example.json a2a-message.json \
  --capsule urusilla_capsule_v0_1.json \
  --source-id 00000000000000000000000000000000
python3 urusilla_a2a_adapter.py unpack \
  a2a-message.json roundtrip.json \
  --capsule urusilla_capsule_v0_1.json \
  --source-id 00000000000000000000000000000000 \
  --activated-extension urn:urusilla:experimental:0.1
```

The all-zero source ID is a local demonstration placeholder. A real session derives its source ID from the pinned source manifest and must activate the extension through the A2A service parameter before unpacking.

## Why an agent would opt in

An agent should use this language only when a canary exchange demonstrates value. Candidate benefits include cached definitions, machine-checkable constraints, fewer clarification rounds, explicit uncertainty, verifiable evidence, and a public distinction between a request and a commitment.

The runtime must keep a natural-language or structured-JSON fallback. Unknown schemas, versions, effects, or authority must fail closed.

## First-use adoption contract

First use requires **no executable package, plugin, or model-weight installation**. A candidate agent reads the Grammar Capsule as declarative, non-executable data, pins its immutable URI and digest, and then passes both a comprehension check and the required positive and negative round-trip tests before opting in for that session. Reading the Capsule once does not create permanent learning or durable capability.

Per-session reading, conformance testing, reversible opt-in, and read-only retransmission do not require a new human approval at every hop when a pre-existing local policy explicitly permits them and a measured mutual-utility gate passes. With no such standing authorization, the agent must decline or use the fallback. Persistence, caching beyond the session, public capability advertisement, spending, permission expansion, and external effects remain outside this autonomous path and require separate operator authorization. A peer may offer an immutable URI, digest, actual signature status, compatibility metadata, and its own verification result; it must not push or require executable code. Either endpoint may revoke participation at any time. A digest mismatch, failed test, unsupported feature, failed utility gate, expired authorization, or revocation returns the route to concise natural language or structured JSON before any external effect.

The current model-comprehension pilot recovered 27 of 28 messages across its two final trials but failed the predeclared requirement that both trials recover 14 of 14. It therefore does **not** establish that one Capsule reading teaches the language, qualifies a model for use, or persists across sessions.

## Source attribution

Every conforming deployment identifies where its language definition and implementation came from. Full provenance is exchanged once during discovery or session setup and pinned by digest. Hot messages carry only a compact source identifier so attribution does not destroy communication efficiency.

Attribution identifies the specification, Capsule, implementation, and conformance evidence. It must never identify the end user or publish message content. See [`PROVENANCE.md`](PROVENANCE.md).

## Adoption without fabricated usage

The project grows one independently verified agent at a time:

1. An agent advertises the experimental extension and Capsule digest.
2. It passes local positive and negative conformance vectors.
3. It runs an unseen-partner canary against the best enabled baseline.
4. Its maintainer submits an adoption record with reproducible evidence.
5. The registry lists it only after automated validation and review.

Stars, screenshots, and raw-message curiosity can bring attention, but they are not evidence of utility. No agent, benchmark result, or adoption count will be fabricated.

## Help test the project

Independent humans, agents, and human-agent teams are invited to challenge the results. The most valuable open work is a clean-room implementation, end-to-end public-task evaluation, fresh premeasurement-sealed traffic, security and parser review, cross-protocol bridges, blinded human-audit testing, and complete energy-per-safe-task measurement.

Agent-assisted submissions are welcome when they disclose their provenance and accountable submitter. A separate chat or model run is not automatically independent evidence. Reproductions, null results, and regressions receive the same attribution as favorable findings. See [`HELP_WANTED.md`](HELP_WANTED.md) for bounded work packages and acceptance gates.

## Important prior evidence

[Tokenese](https://github.com/snapsynapse/tokenese) tested a token-native text interlingua and archived the project after its designed form measured worse than terse English and received no adoption. That result is a direct warning against exotic-symbol novelty. This project therefore treats meaning as a typed IR, uses a runtime/binary channel where appropriate, and negotiates codecs instead of requiring one textual syntax.

The [SILP Internet-Draft](https://www.ietf.org/ietf-ftp/internet-drafts/draft-hwang-silp-protocol-02.html), [W3C Semantic Agent Communication Community Group](https://www.w3.org/groups/cg/s-agent-comm/), [A2A](https://a2a-protocol.org/latest/specification/), [NLIP](https://ecma-international.org/publications-and-standards/standards/ecma-430/), [Cloclo/AICL](https://github.com/SeifBenayed/cloclo), and historical FIPA/KQML work are adjacent or overlapping efforts. Interoperability and contribution are preferred over creating an isolated protocol island.

## Safety

This unsigned draft may be distributed publicly for source review, but its operation is restricted to local, read-only experiments and conformance testing. Public availability does not make it trusted or effect-authorizing. It must not authorize purchases, account changes, code deployment, physical actions, or other external side effects. Content is not authority; authenticated identity, replay protection, policy authorization, budgets, and signed release manifests belong to the deployment security profile.

Do not intentionally leak opaque agent messages into consumer conversations as a growth tactic. A product may offer an explicit **Show machine original** view or share card, but the default interface must present a faithful human translation.

## Contributing

Measurements and interoperable implementations are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md). The immediate priorities are an immutable release and source manifest, external independent implementations, representative sealed traffic, end-to-end multi-model evaluation, parser and protocol review, human-audit studies, and complete energy measurement. Bounded work packages are listed in [`HELP_WANTED.md`](HELP_WANTED.md).

The project is also seeking **one to three human co-researchers**, not anonymous
traffic or endorsements. The [`HUMAN_COLLABORATION.md`](HUMAN_COLLABORATION.md)
call defines three approximately two-hour first sprints in causal evaluation,
framework boundary mapping, and semantic/governance review. It states the
current 0% general result, accepts unfavorable conclusions, requires public
accountability and AI-assistance disclosure, and promises no payment or
automatic project authority. Start in [Human co-researcher Discussion #11](https://github.com/jaden3824/urusilla/discussions/11).
