# Urusilla Competitive Reproduction Plan

Status: preregistration draft; no paid calls have been run  
Evidence cut-off: 2026-08-20  
Companion policy: [Performance Targets and Claim Gates](./PERFORMANCE_TARGETS.md)

## 1. Purpose and hard comparison boundary

This plan defines a cheapest-first, same-workload evaluation of three different efficiency layers:

1. **Symbolic-format track:** what agents say and how a receiver recovers the intended meaning.
2. **Topology track:** which agents or messages are allowed to communicate.
3. **Social-simulation track:** whether concise language preserves simulated human behavior.

These tracks answer different questions. Their headline percentages must never be pooled, ranked in one column, or described as direct wins over one another.

| Track | Unit changed | Primary comparator | Primary outcome |
| --- | --- | --- | --- |
| Symbolic format | Message representation | Compact terse English on the identical episode | Total model tokens per safely completed task, subject to task-success non-inferiority |
| Topology | Communication graph | Full graph and a hand-designed sparse graph with an unchanged message representation | Total model tokens per completed task, including graph-training cost |
| Social simulation | Vocabulary and expression rules | Unmodified simulation on the identical population and event | Response tokens and total simulation tokens, subject to behavior-fidelity gates |

A format result may be compared with another format only when dataset items, knowledge allocation, agents, speaking order, stopping rules, models, decoding controls, and scoring are identical. A topology result may be compared with another topology only when the message representation is fixed. A social-simulation result is not evidence of task-oriented agent success.

## 2. Primary-source audit

### 2.1 AutoForm

- Official paper: [Findings of EMNLP 2024](https://aclanthology.org/2024.findings-emnlp.623/).
- Official code: [`thunlp/AutoForm`](https://github.com/thunlp/AutoForm), pinned for this plan to commit [`8df94501c462e7f7b4708e5f0297fbdcf8e12ffa`](https://github.com/thunlp/AutoForm/tree/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa), observed on 2026-08-20.
- Code license: Apache-2.0 in the pinned repository.
- Original multi-agent models: `gpt-3.5-turbo-1106` and `gpt-4-1106-preview`. The paper reports Gemini Pro 1.0 from January 2024 for the single-model experiments, not the main two-agent table.
- Original two-agent tasks: 100 HotpotQA items, 100 WikiHop items, and 100 NarrativeQA items.
- Original report: up to 72.7% fewer generated communication tokens, but only on one HotpotQA pairing. The paper's main text calls the answer metric F1 while a table caption calls it ROUGE-L. Both metrics must therefore be reported in a reproduction.

Pinned repository artifacts for the symbolic-format track:

| Workload artifact | Records | SHA-256 | Upstream access and license |
| --- | ---: | --- | --- |
| `data/hotpot_qa/test_single.jsonl` | 100 | `eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284` | [HotpotQA](https://hotpotqa.github.io/), CC BY-SA 4.0 |
| `data/wiki_hop_qa/test_processed.jsonl` | 100 | `724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39` | [QAngaroo v1.1](https://zenodo.org/records/6407402), CC BY-SA 3.0 |
| `data/narrative_qa/test_2agent_15100.jsonl` | 100 | `76b5163af50e278a9f1e90848090a4e1b799d4e1d63b47d5fc1aef2ab4bede0b` | [NarrativeQA](https://github.com/google-deepmind/narrativeqa), Apache-2.0 metadata and QA files; source stories retain their own terms |

Important reproduction gaps:

- The WikiHop repository contains raw and rewritten-question variants. This plan uses the rewritten-question artifact because it most closely matches normal QA, but it also requires a sensitivity run on the 100-record `data/wiki_hop_qa/test.jsonl`, SHA-256 `6e587f821610d5277bd4e8cbf1c601cb76a4f19ee43677f1ba44aedf854ec565`.
- The NarrativeQA repository contains three 100-record two-agent variants. The `15100` artifact most closely matches the paper's approximately 30,000-token total cutoff, but the paper does not identify the filename. Sensitivity runs must include `test_2agent.jsonl`, SHA-256 `56cf69fffa655305468318ebf68534bdb47409d897b8fb4f4e5c5d9a6fd6067f`, and `test_2agent_10000.jsonl`, SHA-256 `8eb6c5e3923ec3e77dd62af6ef46d520fa6bedfd207f4982abb7ec515bb57227`.
- Several runner files contain copied default task names or paths from another dataset. The harness must pass every task and data path explicitly; defaults are forbidden.
- The paper names `gpt-4-1106-preview`, while some pinned configurations and runner overrides use `gpt-4-1106`. Archive the provider-resolved model response; do not silently treat these strings as identical.
- The paper does not clearly state whether the multi-agent table is an average across repeated runs. This plan uses three full repeats.
- The archived model endpoints may be unavailable. Failure to access them makes the archival lane incomplete, not failed evidence for the method.

### 2.2 AgentPrune

- Official paper: [ICLR 2025 proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html).
- Official code: [`yanweiyue/AgentPrune`](https://github.com/yanweiyue/AgentPrune), pinned for this plan to commit [`c544dd6a1858c02c6d5d371d23c6e6ff55e0be21`](https://github.com/yanweiyue/AgentPrune/tree/c544dd6a1858c02c6d5d371d23c6e6ff55e0be21), observed on 2026-08-20.
- Repository license: **none found at the root of the pinned commit**. The repository is readable, but reuse or distribution of its code is not assumed to be licensed. Obtain author permission or a license before copying implementation code. A clean-room reimplementation from the paper is the default claim lane.
- Original main models: `gpt-3.5-turbo-0301` and `gpt-4-1106-preview`, temperature 1.
- Original task rounds: two for general and mathematical reasoning, four for code generation.
- Original optimization: five agents in the main comparison, graph-mask initialization at 0.5, 5/10/20 training queries, 10 samples per training query, and 30% or 50% pruning in the paper. The public CLI defaults differ in several places, so paper settings take priority and every override must be recorded.

Dataset audit:

| Task | Clean source | License/access | Pinned-code behavior |
| --- | --- | --- | --- |
| MMLU | [`hendrycks/test`](https://github.com/hendrycks/test/tree/4450500f923c49f1fb1dd3d99108a0bd9717b660) | MIT | Trains on `dev`; evaluates a seeded shuffle of `val`, limited to 153 questions |
| GSM8K | [`openai/grade-school-math`](https://github.com/openai/grade-school-math/tree/3101c7d5072418e28b9008a6636bde82a006892c) | MIT | The bundled 1,319-record file is byte-identical to the official test file; SHA-256 `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14` |
| HumanEval | [`openai/human-eval`](https://github.com/openai/human-eval/tree/6d43fb980f9fee3c892a914eda09951f772ad10d) | MIT; generated code must be sandboxed | The bundled artifact is a shuffled/transformed 161-task file, not the official 164-task file; IDs 32, 38, and 50 are absent; SHA-256 `74a24f601800a3f94d3d9014fdc8c2a149b36806e2847eb251615dab16c60004` |

Important reproduction gaps:

- The paper covers six benchmarks, while the public repository documents only MMLU, GSM8K, and HumanEval clearly enough for the first reproduction stage.
- The public GSM8K and HumanEval loops optimize on early evaluation records and then report a running score that includes those records. This is acceptable only in a labeled literal replay. Claim-eligible evaluation must exclude all graph-training items from scoring.
- The 161-task HumanEval derivative has unclear provenance in the repository. The clean lane uses the official 164 tasks; the literal lane is reported separately and is not mixed with it.
- Published token-reduction percentages include a topology change and cannot be compared directly with a message-format percentage.

### 2.3 EcoLANG

- Official paper: [Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.284/).
- Official implementation: **no author-linked public implementation was discoverable as of the evidence cut-off**. This blocks an exact code reproduction.
- Reported agent model: Llama-3.1-8B-Instruct. Reported judges: GPT-4o for language-rule evolution and GPT-4o-mini for downstream labeling.
- Reported induction data: the validation split of Synthetic-Persona-Chat plus topic-relevant tweet corpora.
- Reported downstream tasks: 196 PHEME instances with 2–31 users, and the second events from the HiSim Metoo and Roe datasets with 1,000 users each.
- Reported repeats: three simulation runs.

Candidate dependency pins for a clean reimplementation, not claimed as the authors' historical pins:

| Component | Candidate pin observed on 2026-08-20 | License/access |
| --- | --- | --- |
| Synthetic-Persona-Chat | [`1f367a0f05d388ca96ebbbc9e5752ab19ac76510`](https://github.com/google-research-datasets/Synthetic-Persona-Chat/tree/1f367a0f05d388ca96ebbbc9e5752ab19ac76510) | CC BY 4.0; repository is archived but downloadable |
| PHEME rumours/non-rumours | [Figshare record 4010619](https://figshare.com/articles/dataset/PHEME_dataset_of_rumours_and_non-rumours/4010619) | CC BY 4.0; published file MD5 `07f004eca867447d69c71e87be242d75` |
| HiSim code | [`01360e882751abbd5158101ca840dfaa18c4520c`](https://github.com/xymou/HiSim/tree/01360e882751abbd5158101ca840dfaa18c4520c) | Apache-2.0; raw posts are not distributed |
| OASIS code | [`372bd70e5849224aacbb2464a3e079db4cde2bbc`](https://github.com/camel-ai/oasis/tree/372bd70e5849224aacbb2464a3e079db4cde2bbc) | Apache-2.0 |
| Llama-3.1-8B-Instruct weights | [Official model card](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct); revision unresolved because access is gated | Llama 3.1 Community License and acceptable-use policy; approval required |
| Metoo source metadata | [Harvard Dataverse DOI 10.7910/DVN/2SRSKJ](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/2SRSKJ) | Dataverse record states CC0 1.0; post content remains subject to platform terms |
| Roe source metadata | [Harvard Dataverse DOI 10.7910/DVN/STU0J5](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/STU0J5) | Dataverse record states CC0 1.0; post content remains subject to platform terms |

Important reproduction gaps:

- No public implementation, frozen vocabulary, evolved-rule artifact, or historical OASIS revision was found.
- The paper reports unversioned Llama-3.1-8B-Instruct, GPT-4o, and GPT-4o-mini names. The exact weight revision and hosted snapshots are not disclosed, so a model-exact claim is blocked unless the authors provide them.
- The paper does not disclose the exact number of dialogue scenarios or samples per rule used in evolution.
- The vocabulary corpora depend on millions of historical posts. Deleted posts, API changes, and platform terms make exact reconstruction unlikely.
- HiSim publishes IDs rather than raw content. Rehydrated data will differ over time and may require platform authorization.
- Because the exact run cannot currently be reconstructed, results from this track must be labeled **paper-guided reimplementation** until the authors release sufficient artifacts.

## 3. Common experiment contract

### 3.1 Frozen manifest

Before any scored call, create and sign a machine-readable manifest containing:

- repository commit, local patch digest, container image digest, dependency lock digest, operating system, driver, accelerator, and compiler versions;
- dataset URL, license, local SHA-256, record count, inclusion/exclusion list, split-generation code, and split seed;
- complete system/developer/user prompts, prompt byte counts, prompt digests, output parsers, repair prompts, and stop rules;
- provider, endpoint, exact model ID, model metadata response, model-card revision, tokenizer revision, generation controls, and request date;
- agent count, roles, speaking order, maximum turns, agreement rule, timeout, retry policy, and fallback policy;
- every representation profile, codec, dictionary, schema, negotiation message, integrity field, and source/provenance field;
- preregistered hypotheses, margins, tests, bootstrap seed, multiplicity correction, exclusions, and claim level sought.

Aliases such as `latest` are prohibited. If a provider offers only a stable alias, archive the provider's model-metadata response and a canary-output suite at the start and end of the run. Any detected change splits the experiment into separate model versions.

### 3.2 Randomization and repeats

- Data-order seeds: `20240826`, `20250424`, and `20260820`.
- Use paired conditions: every format or topology sees the same item, knowledge split, model pair, initiator, and seed.
- Use at least three complete repeats for any stochastic model call.
- Do not drop malformed, refused, timed-out, repaired, or fallback episodes. Keep them in the denominator.
- A provider outage may pause a paired block. It may not selectively remove one arm.

### 3.3 Meaning and safety eligibility

A representation is eligible for the efficiency comparison only if:

- the receiver recovers all required typed fields or the task answer is valid under the same scorer;
- authorization, provenance, source links, and integrity constraints are preserved;
- any profile/schema version is known or safely negotiated;
- malformed input, unknown fields, corruption, and hostile payloads take a deterministic safe path;
- the representation does not expose hidden chain-of-thought or private user data.

Exact typed round-trip is a codec metric, not proof that a model understood the message. Both must be reported separately.

### 3.4 Token ledger

For each episode, publish provider-reported billed usage and locally counted usage under the receiver's pinned tokenizer. Never report only generated communication tokens.

Record these non-overlapping categories:

- `task_input`: every occurrence of the user question and task context in every model request, including replayed copies;
- `system_role`: every occurrence of system instructions, agent roles, demonstrations, and policy text;
- `agent_input_history`: prior agent messages replayed into model context;
- `agent_output_visible`: messages produced for another agent;
- `final_answer`: answer presented to the task scorer or simulated user;
- `format_induction`: model calls used to select, invent, or train a representation;
- `encode_decode_model`: model tokens used by model-based encoders, decoders, or translators;
- `negotiation_profile`: capability exchange, dictionaries, schemas, and cold-start teaching;
- `repair_retry`: validation failures, parser repair, retries, and retransmission;
- `tool_request` and `tool_result`: function arguments and returned tool context; these must both be zero in the no-tools primary lane;
- `safety_filter`: tokens consumed by a separate moderation or policy-model call;
- `judge`: model-based evaluation tokens, reported separately and also included in economic cost;
- `hidden_reasoning_billed`: provider-reported reasoning or thinking tokens when exposed in usage metadata.

Classify each token once by call purpose. Calls made solely for induction, model conversion, negotiation, repair, tools, safety filtering, or judging go wholly to that purpose and are not duplicated in runtime slices. Within a runtime call, attribute input slices to task, system/role, or history and output to either an intermediate agent message or the selected scored final message; if one message serves both roles, classify it as `final_answer` and expose an additional non-additive communication annotation. Repeated prompt bytes count every time they enter a model request.

Primary total:

`T_total = task_input + system_role + agent_input_history + agent_output_visible + final_answer + format_induction + encode_decode_model + negotiation_profile + repair_retry + tool_request + tool_result + safety_filter + hidden_reasoning_billed`

Judge tokens are excluded from task-runtime efficiency but included in the study's monetary and energy accounting. Also publish communication-only totals to reproduce prior papers, clearly labeled as secondary.

Provider cache reads, cache writes, accepted-prediction tokens, rejected-prediction tokens, and any unclassified usage fields are recorded as billing annotations. Cache reads are a subset of input and reasoning tokens may be a subset of provider output, so the raw provider fields must not be added twice. Publish both the non-overlapping research ledger and the provider's billed ledger, with an explicit reconciliation row. Any format-induction or profile-training tokens are reported once as raw study cost and then amortized at the session lengths in Section 3.5; the cold value uses no amortization.

### 3.5 Wire, latency, repair, and energy ledger

For every message boundary, record:

- UTF-8 payload bytes;
- full envelope bytes, including headers, Base64, source references, signatures, profile IDs, framing, and transport compression;
- bytes retransmitted after failure;
- encode, decode, queue, network, model, repair, and end-to-end wall time;
- p50, p95, p99, timeout rate, malformed rate, repair turns, and fallback rate;
- cold-session and warm-session totals, with profile cost amortized over 1, 2, 4, 8, 16, 32, 64, and 128 messages;
- local GPU/CPU utilization, memory, wall time, and power samples when available;
- provider energy as unknown unless the provider supplies a documented measurement.

Report wire bytes and model tokens as separate axes. A binary codec can reduce network bytes while leaving the receiver's decoded prompt tokens unchanged.

## 4. Track A: symbolic-format reproduction

### 4.1 Research question

Can heterogeneous agents exchange the identical evidence and reach the same answer with lower total model-token cost than compact terse English, without a task-success regression larger than 1.0 percentage point?

### 4.2 Workloads and knowledge allocation

Use the three pinned 100-item artifacts in Section 2.1.

For HotpotQA and WikiHop:

1. Shuffle contexts once per preregistered seed.
2. Allocate alternating context blocks to sender A and sender B.
3. Add a **forced distributed-evidence** stratum in which the known supporting evidence is split across agents.
4. Keep the allocation byte-identical across representation arms.

For NarrativeQA:

1. Use the repository's pre-split two-agent context.
2. Reject any model whose context limit cannot accept its assigned half under every arm.
3. Do not silently truncate. A separately reported fixed-budget truncation study may be added, using the same truncation for every arm.

Primary task families for the first competitive-gate attempt are HotpotQA and WikiHop. NarrativeQA is a high-cost transfer family and is required for the full report, not for the first go/no-go decision. The 100-item source artifacts are the exact-reproduction stratum. Before treating them as claim evidence, run a blinded paired-discordance power simulation. If their confidence interval cannot resolve the 1-point margin, do not weaken the margin: create a separately hashed extension from the public labeled upstream development sets, exclude all source-artifact IDs, apply the identical allocation algorithm, and run Stage A5 below.

### 4.3 Representation arms

Freeze six model-prompt arms before evaluation, plus the wire-only control below:

1. **Paper natural-language baseline.** Copy the exact baseline instruction and demonstrations from the pinned AutoForm task configuration. Preserve its answer tags and eight-message cap.
2. **Compact terse English.** A fixed instruction requires atomic evidence, explicit source ownership, no greeting or repetition, short keys only when unambiguous, and the same final-answer tag. No information may be omitted merely to save tokens.
3. **Canonical minified JSON.** A fixed `a,c,e,n,x` schema carries the answer candidate, claims, evidence with source owner, missing-information requests, and dialogue act. Preserve key order and empty arrays, and use no whitespace.
4. **AutoForm.** Copy the exact non-natural-format instruction and demonstrations from the pinned repository. The model chooses its own structured or symbolic form per episode.
5. **Current Urusilla adaptive stack.** Freeze the exact release candidate before scored calls. Receiver-bound v0.7 profiles are eligible only when their complete cold cost can amortize; v0.8 bound or standalone fallback must preserve its matching integrity contract; v0.9 deltas are eligible only for an explicitly stateful arm with the matched full-record baseline.
6. **Oracle-free adaptive selector.** Select among eligible Urusilla, terse-English, and JSON messages using only information available before the receiver call. Binary transport is allowed only when both endpoints decode it before the receiver model; decoded prompt tokens and conversion work still count. A delta expanded before model input may reduce network text but cannot claim receiver-model token savings.

For a claim-ready scored run, freeze `prompts.lock.json` and `profiles.lock.json` after installing the exact upstream sources. Hash every rendered prompt after variable substitution. The natural-language and AutoForm prompts may differ in instruction length because that is part of real cost; both instruction tokens count.

**Locked paper-prompt sources.** The archival replay reads the prompt blocks byte-for-byte from the following files at the pinned commit; only task variables and the explicitly selected model ID may be substituted:

| Task | Natural-language configuration | AutoForm configuration |
| --- | --- | --- |
| HotpotQA | [`hotpot_qa/gpt-4-cot/config.yaml`](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/agentverse/tasks/tasksolving/hotpot_qa/gpt-4-cot/config.yaml) | [`hotpot_qa/gpt-4-cot-model/config.yaml`](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/agentverse/tasks/tasksolving/hotpot_qa/gpt-4-cot-model/config.yaml) |
| WikiHop | [`wiki_hop_qa/gpt-4-cot/config.yaml`](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/agentverse/tasks/tasksolving/wiki_hop_qa/gpt-4-cot/config.yaml) | [`wiki_hop_qa/gpt-4-cot-model/config.yaml`](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/agentverse/tasks/tasksolving/wiki_hop_qa/gpt-4-cot-model/config.yaml) |
| NarrativeQA | [`narrative_qa/gpt-4-cot/config.yaml`](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/agentverse/tasks/tasksolving/narrative_qa/gpt-4-cot/config.yaml) | [`narrative_qa/gpt-4-cot-model/config.yaml`](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/agentverse/tasks/tasksolving/narrative_qa/gpt-4-cot-model/config.yaml) |

**Locked modern prompt contracts.** The task/context prefix and answer-extraction target are identical in every modern arm; output framing varies by arm. The only arm-specific addendum is frozen as follows:

- Compact terse English: `Send only task-relevant facts. Preserve source ownership. Use these lines in this order: ACT: ask|propose|agree|reject; CLAIM: <short claim or ?>; EVIDENCE: <[A|B] atomic facts or NONE>; NEED: <missing fact or NONE>; ANSWER: <exact answer or ?>. No greeting, repetition, unsupported claim, or private reasoning.`
- Canonical minified JSON: `Return exactly one JSON object with keys in this order and no whitespace: {"a":"<exact answer or ?>","c":["<short claim>"],"e":[{"f":"<atomic fact>","s":"A|B"}],"n":["<missing fact>"],"x":"ask|propose|agree|reject"}. Use empty arrays when absent. Do not add keys or prose.`

The current-surface profile and selector policy are copied into their lock files in full rather than summarized in the runtime prompt. Test vectors must prove that every fact, source owner, act, request, and answer in the two fixed contracts maps to the corresponding typed fields.

The current serialization studies do not pre-qualify any project arm for a task claim. v0.7 has favorable warm project-holdout results but activates in none of its tested cold plans; v0.8 bound fallback ties raw plain text and has zero compact wins on both sealed external-example corpora, while its standalone warm contract retains two of 172 and three of 168 isolated one-token wins without cold artifact activation; v0.9 is favorable only against matched full records on a deliberately correlated synthetic state workload. The scored harness must retain these boundaries and may not substitute their percentages for total-task results.

**Negotiated binary wire control.** Encode the canonical typed record with deterministic CBOR, MessagePack, typed Protobuf, and the approved project codec. Include the capability exchange, profile/schema bytes, integrity material, and Base64 or framing overhead actually sent. Each payload is decoded before the receiver-model boundary into the exact canonical JSON prompt. Because those decoded prompts are byte-identical, reuse the paired JSON receiver call rather than paying for causally identical calls; compare only wire bytes, conversion time, and cold/warm overhead. This control can satisfy a transport baseline but cannot claim a model-token or comprehension win.

### 4.4 Model and provider matrix

The archival lane attempts the original ordered pairs if endpoints remain available. It is descriptive and may be incomplete.

The modern claim lane uses these frozen families:

| Code | Provider/runtime | Exact model or revision | Required controls |
| --- | --- | --- | --- |
| O | OpenAI Responses API | `gpt-5-mini-2025-08-07` | No tools, no web, fixed reasoning setting, fixed maximum output, record all usage fields |
| G | Google Gemini API `v1` | `gemini-3.7-flash` | No tools or grounding, fixed thinking level, fixed maximum output, archive model metadata |
| Q | Local vLLM or Transformers | `Qwen/Qwen2.5-7B-Instruct` revision [`a09a35458c702b33eeacc393d103063234e8bc28`](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/tree/a09a35458c702b33eeacc393d103063234e8bc28), Apache-2.0 | BF16 reference run, deterministic kernel settings where possible, pinned chat template and tokenizer |

Run all nine ordered pairings: O→O, O→G, O→Q, G→O, G→G, G→Q, Q→O, Q→G, and Q→Q. The left model initiates. This creates at least two unseen cross-family sender-receiver pairings for each family.

Provider availability, safety behavior, or regional access must be checked immediately before preregistration. A replacement model starts a new matrix and cannot be merged with the old one.

### 4.5 Episode protocol

- Two agents speak in strict alternation.
- The initiator is fixed by the ordered pair.
- Maximum: four messages per agent, eight model calls per episode, matching the pinned source configurations' `max_turns: 8`.
- Early stop: both agents emit the same parseable answer candidate and no unresolved evidence request remains.
- Decoding: temperature 0 for models that support it; otherwise use the provider's least-stochastic documented setting and record the rejected or unavailable control. Lock settings per model across arms and never pool different decoding strata. Repeat three times because hosted inference can remain nondeterministic. Add temperature 0.7, where supported, as a preregistered robustness appendix only.
- Repairs: at most one format-only repair call. The repair prompt cannot add task evidence. Failure after repair is scored as malformed and unsuccessful.
- Fallback: an unknown profile or failed current-surface validation falls back to terse English. All failed attempt and fallback tokens count.
- Final scoring is performed by a deterministic parser first. Any model judge is secondary and blind to the arm label.

### 4.6 Metrics

Primary effectiveness:

- normalized exact match;
- standard token-level answer F1;
- ROUGE-L, because the source paper is internally inconsistent about F1 versus ROUGE-L;
- safe task success: parseable correct answer with required provenance and no integrity/authorization failure.

Primary efficiency:

- ratio of summed `T_total` to the compact-terse-English total over paired episodes;
- total cost per safely completed task;
- warm and cold token regret against the best eligible representation chosen with hindsight.

Secondary:

- communication-only output tokens for source-paper comparability;
- all token-ledger categories;
- full-envelope wire bytes;
- conversion CPU time and model tokens;
- p50/p95 latency, repair, malformed, timeout, fallback, and disagreement rates;
- exact field recovery for typed representations;
- performance by evidence-allocation stratum and ordered model pair.

### 4.7 Statistical plan

- Unit: dataset item × ordered model pair × repeat. The initiator is fixed by the ordered pairing and is not counted as another factor.
- Pair every arm with compact terse English at the item level.
- Task-success non-inferiority margin: −0.010 absolute.
- Use a one-sided 95% stratified paired-bootstrap confidence interval with 10,000 resamples, clustering all repeats of an item together.
- Non-inferiority passes only when the lower confidence bound for `success_arm − success_CTE` is greater than −0.010.
- Token reduction is a ratio of sums. Publish a two-sided 95% paired-bootstrap interval. The competitive token gate passes only when the lower bound on reduction is at least 25% for each qualifying task family.
- Use Holm correction across task families and receiver-model families for any universal claim. Publish unadjusted and adjusted results.
- Run McNemar's test as a sensitivity analysis for binary success and report effect sizes, not only p-values.
- Do not average away a model family with a regression larger than 1.0 percentage point.

### 4.8 Calls and expected cost

Assumptions: no retries in the base estimate, at most eight model calls per episode, 80–250 output tokens per call, 2,000–8,000 input tokens per short-context call, and 8,000–32,000 per NarrativeQA call. Paid traffic is approximately two-thirds of the modern matrix; Q runs locally. The wire-only control reuses the canonical-JSON receiver calls and adds no model calls. A0 must replace these broad assumptions with the p25/p50/p75/p95 token counts from fully rendered local prompts.

Public list prices used only for planning, checked on 2026-08-20:

- [OpenAI GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini): $0.25 per 1M input tokens and $2.00 per 1M output tokens.
- [Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/latest-model): promotional $0.75 per 1M input tokens and $3.75 per 1M output tokens through 2026-12-31.

| Stage | Design | Maximum calls | Planning range |
| --- | --- | ---: | ---: |
| A0 | Dataset, prompt, parser, local token, and wire replay only | 0 paid | $0 |
| A1 | 20 HotpotQA + 20 WikiHop; CTE/AutoForm/current surface; O→G, G→Q, Q→O; 1 repeat | 2,880 | $4–$40 plus local compute |
| A2 | Full 200 short-context items; 6 model-prompt arms; the same 3 pairs; 1 repeat | 28,800 | $30–$200 plus local compute |
| A3 | Full 200 short-context items; 6 model-prompt arms; 9 pairs; 3 repeats | 259,200 | $240–$1,800 plus local compute |
| A4 | Add 100 NarrativeQA items; 6 model-prompt arms; 9 pairs; 3 repeats | 129,600 | $300–$2,400 plus local compute |
| A5 | If required by power audit: 1,000 new HotpotQA + 1,000 new WikiHop items; 6 arms; 9 pairs; 3 repeats | 2,592,000 | $2,500–$15,000 plus local compute |

The exact 300-item modern matrix is capped at 388,800 scored calls before repair. A 20% retry/resume reserve and provider price drift produce a prudent API budget envelope of approximately **$600–$5,000**, plus local accelerator time. A5 is conditional and independently approved. Its call formula is `N_extension × 6 × 9 × 3 × 8`; if the power calculation requires more than 2,000 extension items, scale its budget linearly and preregister a maximum before sampling. These are budget ceilings, not expected bills; each stage requires a fresh approval based on measured prior-stage usage.

## 5. Track B: topology reproduction

### 5.1 Research question

With the message representation frozen, can learned graph pruning reduce complete task cost while preserving task success?

### 5.2 Two required lanes

1. **Literal replay lane:** reproduce the public repository behavior as closely as legally permitted, including its data order and early-query optimization. Label all overlap between optimization and scoring. This lane tests whether the published code path can be recovered; it is not claim eligible.
2. **Clean held-out lane:** reimplement from the paper without copying unlicensed code, exclude every optimization item from scoring, and freeze the graph before evaluation. Only this lane can support project claims.

### 5.3 Fixed tasks and splits

- **MMLU:** form nested, subject-stratified 5-, 10-, and 20-item calibration subsets from official `dev` using the run seed; the 20-item subset is primary. Evaluate the first 153 questions after the pinned loader's NumPy `default_rng(888)` shuffle of the official `val` split.
- **GSM8K:** reserve a preregistered 20-item calibration subset from the 1,319 official test items; never score those 20; score the remaining 1,299. Also report a transfer run whose graph was trained on MMLU dev and applied to all GSM8K test items without GSM8K calibration.
- **HumanEval:** use the official 164 tasks in the clean lane. Reserve 20 fixed calibration tasks, exclude them, and score 144. Run generated code inside an offline container with no network, read-only fixtures, process/time/memory limits, and disposable storage. The 161-task derivative is literal-lane only.

The calibration design is distribution adaptation, not zero-shot transfer. Both labels must remain explicit.

### 5.4 Topology arms

Within each lane, hold the complete prompt lock, message representation, agent roles, agent count, model, and decoding controls fixed while changing only the graph:

1. full directed acyclic graph plus final aggregator;
2. hand-designed chain or task-appropriate sparse graph;
3. random 30% pruning with the retained-edge count of the learned 30% condition;
4. random 50% pruning with the retained-edge count of the learned 50% condition;
5. paper-guided spatial-plus-temporal 30% pruning;
6. paper-guided spatial-plus-temporal 50% pruning.

Use five agents. Use two rounds for MMLU/GSM8K and four for HumanEval. For the learned arms, use graph masks initialized to 0.5 and 10 sampled trajectories per calibration query. The claim-eligible primary run uses 20 calibration queries and treats 30% and 50% pruning as separate conditions; neither may be selected after viewing test results. A source-paper learning-curve appendix repeats the learned arms with 5 and 10 calibration queries.

Run the primary reproduction on one frozen model first. Extend to O, G, and Q only after the implementation passes local deterministic tests. Message-format experiments on a pruned graph are a later factorial study and must show main effects and interaction terms separately.

The cheapest clean model order is homogeneous Q nodes plus a Q aggregator, then homogeneous O, then homogeneous G. Do not mix node families in the primary topology comparison. The permissioned archival lane separately attempts homogeneous `gpt-3.5-turbo-0301` and `gpt-4-1106-preview`; unavailable endpoints make that lane incomplete.

**Prompt and output lock.** The pinned repository has no license, so linking and hashing its prompt sources does not grant permission to copy them. A permissioned literal replay must hash these exact source files: [MMLU prompts](https://github.com/yanweiyue/AgentPrune/blob/c544dd6a1858c02c6d5d371d23c6e6ff55e0be21/AgentPrune/prompt/mmlu_prompt_set.py), [GSM8K prompts](https://github.com/yanweiyue/AgentPrune/blob/c544dd6a1858c02c6d5d371d23c6e6ff55e0be21/AgentPrune/prompt/gsm8k_prompt_set.py), [HumanEval prompts](https://github.com/yanweiyue/AgentPrune/blob/c544dd6a1858c02c6d5d371d23c6e6ff55e0be21/AgentPrune/prompt/humaneval_prompt_set.py), [agent input assembly](https://github.com/yanweiyue/AgentPrune/blob/c544dd6a1858c02c6d5d371d23c6e6ff55e0be21/AgentPrune/graph/node.py), and [final-decision assembly](https://github.com/yanweiyue/AgentPrune/blob/c544dd6a1858c02c6d5d371d23c6e6ff55e0be21/AgentPrune/agents/final_decision.py). The clean-room lane independently implements only the paper-described behavior: MMLU agents return a leading A/B/C/D choice and short rationale, with a one-letter aggregator; GSM8K agents end with `The answer is <number>`; HumanEval code agents and the aggregator return one Python code block. Each node receives only predecessor outputs admitted by the tested graph. Freeze the independently written text, role list, few-shot set, concatenation order, whitespace, and output parser before graph optimization, then use the identical lock for all six conditions.

### 5.5 Metrics and statistics

- MMLU and GSM8K: exact-answer accuracy.
- HumanEval: pass@1 under the official execution scorer and sandbox.
- Safe task success, including parser, timeout, and execution-safety failures.
- All token categories, with graph-training tokens amortized over 1, 10, 100, 1,000, and 10,000 downstream queries.
- Prompt and completion tokens separately; edge/message count; retained-edge ratio; training wall time; inference wall time; wire bytes; repair and timeout rates.
- Primary non-inferiority margin: −1.0 percentage point. The learned conditions must pass separately against both the full graph and the frozen hand-designed graph; Holm-adjust the family of comparisons instead of selecting whichever baseline is weaker after scoring.
- At each pruning level, publish the paired learned-minus-random success difference and total-cost difference. A sparse graph is not evidence that learning helped unless it improves the matched random control on at least one preregistered Pareto axis without harming the other.
- Three full optimization-and-evaluation repeats. Cluster repeats by task item and graph-training seed in the paired bootstrap.
- Lower one-sided 95% confidence bound must exceed −0.010. Publish the token-ratio interval and the full cost/success Pareto frontier.

### 5.6 Calls and cost

With no early stopping and one call per agent per round, the six-condition primary lane has a transparent upper-bound calculation:

- evaluation messages: `(153×5×2 + 1,299×5×2 + 144×5×4) × 6 conditions × 3 repeats = 313,200`;
- optimization messages for the two learned conditions: `(20×10×5×2 + 20×10×5×2 + 20×10×5×4) × 2 pruning levels × 3 repeats = 48,000`;
- one optional model aggregator per evaluation episode: `(153 + 1,299 + 144) × 6 × 3 = 28,728`;
- one optional model aggregator per optimization trajectory: `(20 + 20 + 20) × 10 × 2 pruning levels × 3 repeats = 3,600`.

The primary cap is therefore **393,528 model calls** before repair, or 361,200 if aggregation is deterministic. Repeating the learned arms at 5 and 10 calibration queries for the full source-paper learning curve raises the model-aggregator cap to **660,180**. Literal replay is budgeted separately. Log actual early stops rather than subtracting them in advance.

Run cheapest first:

| Stage | Design | Planning envelope |
| --- | --- | ---: |
| B0 | Unit tests with recorded or local stub outputs | $0 |
| B1 | 50 MMLU items, all six conditions, one local model, one seed | local compute only |
| B2 | Full MMLU 153, one provider model, three seeds | $20–$150 |
| B3 | Add GSM8K and HumanEval, one provider model, three seeds | $180–$1,000 |
| B4 | Extend the frozen protocol to all three model families | approve only after B3; expected $500–$3,500 plus local compute |

These are planning ranges, not quotes. Record actual provider billing and local GPU-hours.

## 6. Track C: social-simulation reimplementation

### 6.1 Research question

Can a compact induced vocabulary and expression rule reduce simulation tokens without moving individual- and group-behavior metrics outside preregistered fidelity margins?

### 6.2 Language-induction reconstruction

Reconstruct only what the paper specifies:

1. Use the Synthetic-Persona-Chat validation split at the pinned revision.
2. Start with 10 expression-rule prompts: five human-authored and five model-generated, matching the paper's listed initial rule set in intent.
3. Use a population of 10 rules, retain the best five, and create five replacements by crossover and mutation for five iterations.
4. Use alignment weight 1.0, efficiency weight 0.6, and expressiveness weight 0.6.
5. Use Llama-3.1-8B-Instruct as the speaking model and GPT-4o as the judge for a paper-guided lane. Add blinded human ratings before any fidelity claim.
6. Freeze every sampled dialogue, rule assignment, judge prompt, judge response, and generation seed.
7. Publish the acquired rules and vocabulary with hashes.

The missing number of sampled scenarios and trajectories per rule must be resolved before an exact reproduction. Until then, preregister a power-based number and label the result a reimplementation.

Vocabulary reconstruction requires a separate decision:

- **Historical lane:** attempt authorized rehydration of Twitter15/16 and the Metoo/Roe corpora, documenting coverage loss and platform terms.
- **Stable lane:** build a frozen, redistributable corpus with the same topic strata and publish its full manifest. This tests the method, not the exact historical vocabulary.

Do not merge these lanes.

### 6.3 Downstream conditions

Recreate the seven source-paper conditions: base, summary instruction, AutoForm instruction, KQML instruction, vocabulary-only, rule-only, and combined vocabulary-plus-rule.

An exploratory current-machine-surface arm may be evaluated only in a separate machine-coordination sandbox. It must not be inserted directly into simulated public posts and then compared as if it were human-like language.

For PHEME:

- use the 196 reported instances when available and licensed;
- retain only replies with content, as described in the paper;
- use Llama-3.1-8B-Instruct, temperature 0, maximum 512 output tokens, and the thread-dependent maximum depth;
- run three repeats with identical activation and network seeds across arms.

For HiSim:

- use the second Metoo and Roe events, 1,000 users each, 14 steps;
- disable recommendation, as described in the paper, and expose only external news and followed accounts;
- use the same profiles, social graph, news, memory policy, and action space in every arm;
- run three repeats.

### 6.4 Metrics and human validation

PHEME:

- initial stance consistency: support/deny/query/comment;
- final belief consistency: belief/disbelief/unknown;
- Jensen-Shannon divergence of the final belief distribution;
- response, prompt, completion, judge, and total tokens.

HiSim:

- stance consistency: support/neutral/oppose;
- content-type consistency across the paper's five classes;
- absolute differences in mean opinion bias and opinion diversity over time;
- response, prompt, completion, judge, and total tokens.

Both:

- cosine similarity, Jaccard overlap, word-distribution divergence, response-length drift, runtime, GPU memory, malformed actions, and safety failures;
- a blinded human audit of at least 200 stratified responses per task family, two annotators, adjudicated disagreements, and inter-annotator agreement;
- judge agreement with human labels. The model judge cannot validate itself without this audit.

Use 10,000 paired block-bootstrap resamples. For PHEME, resample complete source threads and keep all users and repeats of a thread together. For HiSim, keep communities and all time steps intact inside each event; report the original two-event, three-repeat result as descriptive because two events cannot establish broad event-level non-inferiority. A claim-eligible HiSim extension requires at least 10 independently seeded runs per event, an event-block analysis, and an explicit statement that inference covers only those two events. Apply Holm correction across the primary consistency and distance outcomes.

Preregister social-specific fidelity margins:

- lower one-sided 95% bound greater than −1.0 percentage point for consistency metrics;
- upper one-sided 95% bound less than +0.01 for divergence/distance regressions;
- no human-rated clarity or persona-alignment drop larger than 0.20 on a five-point scale.

These margins govern only the social track and do not establish the competitive symbolic-format gate.

### 6.5 Privacy and ethics gate

- Rehydrate posts only under current platform terms and institutional approval.
- Store platform IDs and content in access-controlled storage; publish only permitted derived aggregates.
- Strip handles and direct identifiers from prompts and released traces.
- Do not contact, profile, or intervene with real users.
- Red-team whether compact rules amplify harassment, misinformation, group stereotyping, or sensitive-attribute inference.
- Stop the run if data authorization, consent basis, or redistribution rights are unclear.

### 6.6 Calls and cost

The source paper does not disclose enough information for a precise call count. The PHEME minimum is `196 instances × 7 conditions × 3 repeats = 4,116` focal rollouts; agent-level calls depend on the 2–31-user thread and activation policy. Under the explicit upper-bound assumption that every HiSim user acts at every one of 14 steps, two events × 1,000 users × 14 steps × seven conditions × three repeats gives **588,000 generation opportunities**, before PHEME, rule evolution, judges, and retries. Actual OASIS activation policies may reduce this substantially. The optional 10-seed HiSim inference extension raises that same upper bound to **1,960,000** opportunities.

Cheapest-first stages:

| Stage | Design | Go/no-go criterion |
| --- | --- | --- |
| C0 | Data-access, license, prompt, and historical-dependency audit | All required data can be lawfully accessed and hashed |
| C1 | 100 Synthetic-Persona-Chat dialogues; base/rule-only; local model | Rule pipeline lowers tokens without human clarity drop >0.20 |
| C2 | 20 PHEME instances; seven arms; one repeat | Parsers, labels, and token ledger pass; no major fidelity collapse |
| C3 | Full 196 PHEME instances; three repeats | Social margins pass before any HiSim scale-up |
| C4 | 100-agent HiSim downsample; two events; seven arms | Runtime, activation, memory, and privacy checks pass |
| C5 | Full 1,000-agent HiSim; three repeats | Run only with frozen artifacts and approved compute budget |
| C6 | Extend HiSim to 10 total seeds per event | Run only if an inferential social-track claim is sought |

Planning envelope: 100–800 local GPU-hours and $50–$1,000 of judge calls for C1–C5, with very low confidence until C0/C1 measure activation and prompt lengths. If all else scales linearly, C6 raises the compute component by up to 10/3; replace that extrapolation with C5 measurements before approval. Publish measured GPU-hours and paid usage; never convert this range into an energy-savings claim.

## 7. Cross-track execution order

1. Complete A0, B0, and C0 in parallel.
2. Run A1 and B1 in parallel; begin C1 only after data/privacy review.
3. Promote A2 only if exact parsing succeeds and no arm loses more than 3 percentage points in the smoke test.
4. Promote B2 only if the clean implementation matches fixed-graph controls and graph-training cost is fully logged.
5. Promote C2 only if human and model labels reach the preregistered agreement floor.
6. Run A3 before A4; NarrativeQA is intentionally deferred because of long contexts. If the power audit triggers A5, freeze its item manifest after A2 and shard it in parallel with A4 only after A3 validates the full matrix.
7. Run B3 before any three-family topology expansion.
8. Run C3 before C4, and C4 before C5.
9. Freeze all primary analyses before inspecting the full test results.
10. Publish negative and stopped stages with their stopping reason.

Parallel execution may reduce calendar time, but it must not permit results from one track to change another track's frozen prompt, margin, or metric.

## 8. Preregistration checklist

- [ ] State the track and prohibit cross-track headline comparisons.
- [ ] Name the primary task families, exact items, exclusions, and split hashes.
- [ ] Record dataset access rights, licenses, and platform restrictions.
- [ ] Pin every repository, model, tokenizer, runtime, dependency, and container.
- [ ] Archive model metadata and canary outputs for hosted endpoints.
- [ ] Freeze all prompts, demonstrations, representations, profiles, schemas, codecs, parsers, repairs, and fallbacks.
- [ ] Freeze agent roles, speaking order, turn cap, agreement rule, retry limit, timeout, and failure denominator.
- [ ] Declare primary baseline and strongest-baseline selection rule before scoring.
- [ ] Declare task-success and safety outcomes.
- [ ] Declare every token category, wire boundary, latency component, and cost formula.
- [ ] Declare cold/warm session lengths and amortization rules.
- [ ] Declare run count, seeds, paired unit, cluster unit, bootstrap method, confidence level, non-inferiority margin, and multiplicity correction.
- [ ] Complete the paired-discordance power audit; freeze and hash any public-set extension before its first scored call.
- [ ] Declare go/no-go thresholds and maximum API/compute budget.
- [ ] Confirm that generated code is sandboxed and network-disabled.
- [ ] Confirm that social data handling passed privacy and terms review.
- [ ] Register all planned subgroup and sensitivity analyses.
- [ ] Commit the preregistration before the first scored call and publish its immutable digest.

## 9. Claim gates

### 9.1 Competitive

Use **competitive** only for the symbolic-format track when all conditions in the companion performance policy hold, including:

- safe task success is non-inferior within 1.0 percentage point;
- the lower confidence bound on total-token reduction versus compact terse English is at least 25% on each qualifying public task family;
- no model family has a credible task-success regression greater than 1.0 percentage point;
- conversion, negotiation, profile, repair, retry, and cold-start costs are included;
- at least two public task families, three independent model families, all required unseen pairings, and three repeats are complete;
- the unique-item count supports the preregistered 1-point margin, or the powered A5 extension is complete;
- every negative result remains visible.

### 9.2 Near-leading

Use **near-leading** only after a same-workload reproduction shows the project within 5 percentage points of the best reproducible total-token reduction on at least two public task families, with equal or stricter safe-task-success evidence and an additional Pareto benefit such as lower wire bytes, lower cold-start cost, interoperability, or auditability.

The source AutoForm value of 72.7% is not a target that can be compared with a local serialization corpus or a different model matrix. Proximity language requires the same items, model pairs, prompts, turns, and total-token ledger.

### 9.3 Leading

Use **leading**, **best**, or **state of the art** only when the project:

- beats the strongest reproducible baseline on the same public workload and model set;
- passes preregistered safe-task-success non-inferiority;
- holds on at least two task families and two unseen cross-family pairings;
- releases raw observations, prompts, failures, cost ledgers, bootstrap code, and the full Pareto table;
- is independently reproduced by an external party.

No topology or social-simulation percentage may be substituted for a symbolic-format gate. No serialization-only result may establish model comprehension or task success.

## 10. Blocking issues and resolution criteria

| Blocker | Consequence | Resolution required |
| --- | --- | --- |
| AutoForm archival endpoints may be retired | Exact historical model reproduction may be impossible | Provider access or author-provided archived outputs; otherwise label archival lane incomplete |
| AutoForm data-runner ambiguity | Exact filename/path match is uncertain | Explicit artifact sensitivity runs and, ideally, author confirmation |
| AutoForm F1/ROUGE-L wording conflict | A single metric can misrepresent reproduction | Report exact match, token F1, and ROUGE-L together |
| AgentPrune repository has no license | Code cannot be assumed reusable | License/permission or clean-room paper reimplementation |
| AgentPrune public evaluation overlaps optimization | Literal score is not clean held-out evidence | Exclude optimization items and publish both lanes |
| AgentPrune HumanEval artifact differs from official data | Results are not directly comparable | Use official 164 tasks in the claim lane; isolate the 161-task literal lane |
| EcoLANG implementation and artifacts unavailable | Exact reproduction is blocked | Author release or fully disclosed paper-guided reimplementation |
| EcoLANG PHEME item IDs and induction samples unavailable | The reported 196-item cohort and rule evolution cannot be selected exactly | Author manifests, or a separately hashed paper-guided sample with no exact-reproduction claim |
| Historical social posts are incomplete/restricted | Vocabulary and simulation inputs may drift | Authorized rehydration with coverage report, or a separate stable-corpus lane |
| Provider model aliases and prices change | Runs can silently mix systems and budgets | Exact snapshots where available, metadata/canary archive, date-stamped price manifest |
| No provider energy telemetry | Joule or carbon claims would be speculative | Measured local power or documented provider data; otherwise report compute proxies only |

## 11. Primary references

- [AutoForm paper, Findings of EMNLP 2024](https://aclanthology.org/2024.findings-emnlp.623/)
- [AutoForm official repository](https://github.com/thunlp/AutoForm)
- [AgentPrune paper, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html)
- [AgentPrune official repository](https://github.com/yanweiyue/AgentPrune)
- [EcoLANG paper, Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.284/)
- [HotpotQA official site](https://hotpotqa.github.io/)
- [QAngaroo v1.1 archive](https://zenodo.org/records/6407402)
- [NarrativeQA official repository](https://github.com/google-deepmind/narrativeqa)
- [MMLU official repository](https://github.com/hendrycks/test)
- [GSM8K official repository](https://github.com/openai/grade-school-math)
- [HumanEval official repository and execution warning](https://github.com/openai/human-eval)
- [Synthetic-Persona-Chat official repository](https://github.com/google-research-datasets/Synthetic-Persona-Chat)
- [PHEME project downloads](https://www.pheme.eu/software-downloads/)
- [HiSim official repository](https://github.com/xymou/HiSim)
- [OASIS official repository](https://github.com/camel-ai/oasis)
- [Qwen2.5-7B-Instruct official model card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
- [Llama-3.1-8B-Instruct official model card](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)
- [OpenAI GPT-5 mini model and pricing](https://developers.openai.com/api/docs/models/gpt-5-mini)
- [Gemini 3.7 Flash model and pricing](https://ai.google.dev/gemini-api/docs/latest-model)
