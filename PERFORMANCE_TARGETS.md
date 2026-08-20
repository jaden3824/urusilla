# Urusilla Performance Targets and Claim Gates

Status: experimental research policy

This document defines what the project must measure before it can claim competitive, near-leading, or leading performance. It is a target policy, not a result report.

## 1. The unit of efficiency

The primary unit is **total cost per safely completed task**, not tokens per serialized message.

Every end-to-end report must publish, without collapsing them into one score:

- task success and semantic fidelity;
- model input, output, conversion, negotiation, and repair tokens;
- actual wire bytes, including envelopes, Base64, profiles, manifests, and retransmission;
- p50 and p95 generation, conversion, encode, decode, and end-to-end latency;
- accelerator and host-compute proxies, with measured energy when instrumentation is available;
- repair turns, timeout rate, malformed output rate, and fallback rate;
- safety, authorization, provenance, and audit failures;
- cold-session and warm-session results.

A method cannot be called more efficient when it saves serialization tokens but lowers safe task success, hides conversion work, or shifts a larger cost to another layer.

## 2. Separate comparison tracks

Results from these tracks are not interchangeable.

| Track | Question | Required baselines |
| --- | --- | --- |
| External symbolic dialogue | Can heterogeneous agents exchange the same meaning with less total cost? | compact terse English, canonical minified JSON, negotiated binary codecs, the current adaptive surface |
| Learned or selected format | Can a task-specific learned format improve end-to-end agent work? | AutoForm reproduction, natural-language communication, fixed structured communication |
| Public action-state history | Can agents omit full prose while preserving task-relevant public state? | full-history communication, clean-room PACT-style projection, concise natural language |
| Negotiated routine | Can repeated interactions amortize a compiled routine? | natural language on every interaction, cached routine, cold negotiation and implementation cost |
| Communication topology | Can the system avoid low-value messages? | full graph, hand-designed sparse graph, AgentPrune- or AgentDropout-style reproducible baseline where applicable |
| Model-native transfer | Can compatible models exchange latent state safely and cheaply? | text, typed external representation, no-communication control |
| Network transport | What crosses a process or host boundary most efficiently? | gzip JSON, deterministic CBOR, MessagePack, typed Protobuf, negotiated project codecs |

Latent-state and topology results must never be presented as direct wins over a symbolic wire language unless the complete task, hardware, network boundary, and safety conditions are identical.

## 3. Competitive end-to-end gate

The first competitive study must use at least:

- two public multi-agent task families;
- three independently released model families, including at least one open-weight family;
- two unseen sender-receiver pairings per family;
- a frozen test split and predeclared metrics;
- at least three independent runs for stochastic model calls;
- a strong compact-terse-English baseline written without redundant prose;
- a same-workload AutoForm reproduction where its method is applicable and reproducible;
- full-history and clean-room PACT-style public action-state arms;
- topology pruning or verified silence when the task permits variable communication; and
- an Agora-style negotiated-routine arm for repeated interactions.

All prompts, parsers, repair rules, model versions, tokenizers, temperatures, and failures must be released.

Lossless and task-equivalent lanes must be reported separately. A lossless route must recover and deterministically re-encode the canonical typed message. A public action-state or learned projection may omit original prose, but then it is a task-level semantic-equivalence method and must pass end-to-end success, semantic-fidelity, safety, repair, and total-cost gates; it cannot claim exact prose reconstruction.

## 4. Claim ladder

### 4.1 Competitive

The project may use **competitive** only when:

- safe task success is non-inferior to the strongest baseline by no more than 1.0 percentage point, or the preregistered confidence interval supports non-inferiority;
- total model tokens fall by at least 25% against compact terse English on each qualifying public task family;
- no reported model family has a statistically credible task-success regression greater than 1.0 percentage point;
- conversion, negotiation, repair, and cold-profile costs are included;
- all negative and failed task families remain visible.

### 4.2 Near-leading

The project may use **near-leading** only after a same-workload comparison in which it:

- is within 5 percentage points of the best reproducible total-token reduction on at least two public task families;
- meets the same or stricter safe-task-success threshold as that result;
- improves at least one additional Pareto dimension, such as interoperability, wire bytes, auditability, or cold-start cost, without hiding regressions elsewhere.

The published AutoForm result of up to 72.7% communication-token reduction is a research reference point, not a score that can be compared with this repository's synthetic serialization corpus. The project must reproduce a competitor on the same workload before using proximity language.

### 4.3 Leading

The project may use **leading**, **best**, or **state of the art** only when:

- it exceeds the strongest reproducible baseline on the same public workload and model set;
- safe task success is non-inferior under a preregistered statistical test;
- the result holds for at least two task families and two unseen cross-family model pairings;
- the full Pareto table, raw observations, bootstrap or confidence analysis, and reproducible code are public;
- an independent maintainer or external party reproduces the principal result.

No founder, maintainer, contributor, sponsor, or automated metric may waive these evidence requirements.

## 5. Adaptive fallback target

The adaptive external surface should make novelty cheap instead of forcing every message through a specialized codebook.

For every receiver tokenizer that participates in negotiation:

- select among the typed machine surface, compact terse English, canonical JSON, and any approved codec using the complete encoded cost;
- include selector markers, integrity fields, profile transfer, and translation cost;
- require exact semantic recovery before a candidate is eligible;
- keep privacy, authorization, provenance, and model-compatibility checks as hard gates;
- provide a deterministic safe fallback when a codebook or schema is unknown;
- publish regret against the best eligible representation chosen with hindsight.

Warm token regret should be zero per message after selector overhead. Cold-session regret must be reported and should approach zero as the session length grows. A specialized representation that loses to compact terse English on novel traffic must not be selected.

The frozen 2,542-turn broad study has already stopped incremental optimization of one universal lossless compact text surface: H2 general compact value and H3 repeated-context value failed. Raw text remains the default. This lane may reopen only for a separately frozen architecture-changing hypothesis, not another evaluation-corpus-specific codebook or threshold adjustment.

## 6. Current evidence boundary

The frozen four-family broad lane covers 2,542 turns and four pinned tokenizers. H1 exact no-regret passes, H2 and H3 fail, and H4 is not evaluated. Warm carrier saving is 0.65% to 0.80%; every cold family plan retains raw, post-decode API-input saving is 0%, and the minimal external-profile carrier adds 165.60% to 183.98% tokens. A separate SGD gold-state oracle reduces 399 prompt inputs by 7.48% to 23.34%, but calls no model and measures no accuracy.

Narrower results do not establish general performance. v0.7 saves 23,997 development and 4,302 grouped-holdout tokens but saves 0 OOD and activates in 0/12 cold plans. Transparent v0.8 records 0/172 compact wins under both development contracts, with 5.85% to 6.80% standalone overhead; the retained lane records 0/168 under both contracts and 2.24% to 3.00% standalone cold overhead. v0.9 saves 53.71% to 55.15% on deliberately correlated synthetic state. The historical pre-cutover receiver pilot reaches 27/28 but fails, and the current sender pilot passes 6/10. A same-project Node.js lane is compatibility evidence, not external reproduction.

The next milestone is an end-to-end cross-model router study prioritizing verified silence or topology pruning and model-native or task-aware public action-state records, with negotiated routines and raw fallback. The repository does not yet demonstrate model understanding, safe task-success preservation, lower total application cost, measured energy saving, or state-of-the-art performance. Codec-only improvements cannot advance a leading-performance claim by themselves.

## 7. Public references

- AutoForm, Findings of EMNLP 2024: <https://aclanthology.org/2024.findings-emnlp.623/>
- AutoForm reference implementation: <https://github.com/thunlp/AutoForm>
- AgentPrune, ICLR 2025: <https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html>
- AgentDropout preprint: <https://arxiv.org/abs/2503.18891>
- PACT preprint: <https://arxiv.org/abs/2606.05304>
- OPTiMACS, Findings of ACL 2026: <https://aclanthology.org/2026.findings-acl.1441/>
- Agora preprint: <https://arxiv.org/abs/2410.11905>
- EcoLANG, Findings of EMNLP 2025: <https://aclanthology.org/2025.findings-emnlp.284/>
