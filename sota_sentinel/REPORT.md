# SOTA Sentinel: AI-Agent Communication-Efficiency Evidence Audit

**Evidence cutoff:** 2026-08-20  
**Status:** external-baseline audit; no project SOTA or world-record claim  
**Calls used for this audit:** no paid or model inference calls  
**Source policy:** papers/proceedings, official repositories, and first-party artifact pages only

## Executive finding

There is no defensible single leaderboard for the reported results in this area. The largest numbers measure different objects:

- AutoForm's **72.7%** is a reduction in one generated inter-agent message on one HotpotQA/model-pair cell.
- PACT's exact same-topology **46.59%** AIME25 row counts every rendered model input and raw output, including private thinking, but its code release is incomplete and unlicensed.
- CLSR's exact **76.0%** ScienceQA row counts online generated outputs but excludes all inputs and offline symbolic-language evolution.
- G-Designer's exact **93.89%** 20-agent MMLU row and its separate **95.33%** abstract maximum are prompt-only topology claims; the abstract maximum has no tabulated numerator and denominator.
- AGP's approximately **90.38%** MMLU row is also prompt-only, but unlike most topology methods it releases MIT code, controller weights, and training data.
- RADAR's exact **45.45%** GSM8K row counts prompt plus completion inference tokens in one harness; the cold/overall table gives a different **40.91%** comparison.
- OPTIMA's **92.0%** exact task cell is decoded **inference output** tokens after substantial training whose cost is excluded.
- LatentMAS's **83.7%** is decoded system output tokens; latent steps and KV-transfer bytes are not tokens in that ledger. Its separate **4.3x** result is paper-defined end-to-end inference time.
- LCF-X's **5.34x** is time to the end of a receiver answer on partitioned HotpotQA with better quality, but it is an ICML AdaptFM workshop paper with no code, split manifest, hardware, or timing recipe.
- OBF's **4.65x** is a repository-only same-device latent-payload footprint reduction; it is not a reviewed wire-byte or task-latency result.
- Interlat's approximately **24x** is sender-side message-generation time at an aggressive compression point that loses task success; it is not full task time.
- KVCOMM's **7.82x** is TTFT/prefill at the fifth agent in a synthetic serving setup; the remaining decode and task trajectory are outside the headline.
- KVFlow's **1.83x** is complete synthetic workflow latency versus SGLang HiCache, but it is a cache-management systems result that preserves computation rather than compressing messages.
- AgentSlimming's **78.9%** and Agora's **78.83%** are historical API-dollar reductions, not stable token or byte ratios.

These values are all useful evidence. They are not interchangeable records.

No surveyed agent-task headline is literally reproducible. The strongest practical baseline therefore depends on the claim lane:

- **Primary complete-token implementation:** clean-room PACT against full-history TextMAS in one frozen driver. Its code defines the best disclosed all-rendered-input-plus-raw-output ledger, but the paper is a preprint and the repository cannot be copied without a license.
- **Primary licensed portable-format artifact:** AutoForm at `8df94501c462e7f7b4708e5f0297fbdcf8e12ffa`. It is peer reviewed, Apache-2.0, and includes 100-item task artifacts. Its historical numbers are not literal because the closed model snapshots are retired and the paper is ambiguous about F1 versus Rouge-L and token counting.
- **Primary topology implementation:** AGP at `4c5508361e6a1b0e799b2223403f61c144a4c492`, with pinned public weights and training data. RADAR is the required same-harness combined-token challenger. Neither historical hosted-model result is literal.
- **Primary latent implementation:** LatentMAS at `9a9e4d331eb11430bd9e64754c6b252b06d73031`, with Apache-2.0 code, nine tasks, three-run tables, and end-to-end inference timing. It remains architecture-coupled and excludes physical KV-transfer bytes.

For a literal negative control, **Tokenese is unusually strong evidence** because its archived fixtures reproduce the falsification: the designed v0.3 form is about 1.30-1.31x larger than verbose English and more than 1.5x larger than terse English on the matched example. It is not a performance leader; it is a warning that terse English, compact JSON/schema, and strong codecs must be mandatory baselines.

No result in this report establishes a state-of-the-art or world-record claim for the current project.

## 1. Audit method and decision rules

### 1.1 Inclusion

A candidate was included in the quantitative registry when all of the following were available from a primary source:

1. a numeric communication, token, latency, reuse, or workflow-efficiency result;
2. a named baseline and a recoverable metric direction;
3. a task or serving workload;
4. enough model/topology information to determine the ledger boundary; and
5. a publication or first-party artifact whose status could be verified.

Recent methods with no scalar efficiency table remain in the screened list rather than being converted into inferred percentages. CARD/AMACP is the important example: it is an ICLR 2026 adaptive-topology paper, but its main table is accuracy and its appendix presents an accuracy-to-dollar scatter without auditable baseline/method cost rows. The official repository also has no license text at the recorded revision. It is relevant topology evidence, not a quantitative record candidate.

### 1.2 Source and repository verification

Every paper link in `registry.json` was retrieved from an official proceedings, anthology, OpenReview, arXiv, or author artifact page. Every official Git repository was resolved at the cutoff and pinned to a 40-character commit. A README badge is not treated as a license. If no root license text grants permission, the registry records `absent`, even when the code is public.

Public benchmark names do not prove reproducible data. A data artifact is `complete` only when item files or deterministic preparation inputs are released and pinned. Most papers use multiple upstream datasets with different licenses and publish no consolidated source manifest, so the registry says `upstream_mixed_or_unmanifested` rather than guessing.

### 1.3 Reproduction vocabulary

| Classification | Meaning |
|---|---|
| Literal: yes | The exact released code, revisions, data, model artifacts, and metric boundary can be rerun. |
| Literal: conditional | Most artifacts exist, but exact weights, container, hardware, dataset snapshot, or permission must be supplied. |
| Literal: no | Retired closed models, missing code/checkpoints/data, a missing license, or an ambiguous ledger prevents the historical experiment from being rerun as published. |
| Clean-room: yes | An independent implementation can be made from the public method and evaluated on pinned artifacts without copying unlicensed code. |
| Clean-room: conditional | The paper is implementable in principle, but material details or artifacts must be reconstructed and disclosed. |

### 1.4 What was not done

This audit did not run the project's format against external baselines, did not call paid APIs, did not infer adoption, did not treat repository stars or traffic as evidence, and did not turn a best cell into a general claim. Internal project reports are intentionally excluded from the external evidence table.

## 2. Ledger taxonomy

The following boundaries are normative for interpreting this report. A percentage is comparable only within the same boundary, workload, model revision, success rule, and amortization regime.

| Lane | Includes | Excludes | Representative evidence |
|---|---|---|---|
| Generated-message tokens | Decoded text emitted as an inter-agent message | Inputs, task documents, answer tokens, induction, envelope, repairs | AutoForm, OPTiMACS, EcoLANG |
| Provider prompt tokens | Input tokens charged or counted across agent calls | Completion tokens, wire bytes, non-model orchestration | AgentPrune, AgentDropout |
| Provider completion tokens | Output tokens across agent calls | Prompt tokens and other system cost | AgentDropout |
| Total runtime model tokens | Runtime prompts plus completions, including repeated rendered histories and named supervisor calls | Tools, training, induction, wire bytes, wall-clock | PACT, RADAR, SupervisorAgent |
| Decoded system output tokens | All paper-defined decoded outputs in a MAS run | Input tokens, latent steps, tensor bytes and transfers | OPTIMA, LatentMAS |
| Static tokenizer count | Token count of a serialized short form | Receiver success, teaching, repair and full envelope | Tokenese |
| Message-generation latency | Sender message generation only | Downstream task/environment trajectory | Interlat |
| End-to-end inference latency | Complete paper-defined model inference path | Training and hardware acquisition | LatentMAS, C2C |
| TTFT/prefill | Prefill through first token | Remaining decode and full task | KVCOMM |
| Workflow latency | Complete named synthetic/application workflow | Training; task quality when computation is unchanged | KVFlow |
| Monetary inference cost | Provider usage multiplied by the source's dated input/output prices | Price-stable token equivalence, non-model compute, wire bytes | AgentSlimming, Agora |
| Latent payload bytes | Paper/repository-defined logical KV or latent footprint | Compute, network framing, task latency unless separately measured | OBF relay compression |

Three additional ledgers are mandatory for this project even when the papers omit them:

- UTF-8 **payload bytes** and **full serialized envelope bytes**;
- **cold-start cost**, including grammar/capsule, negotiation, format selection, repair, retry, and fallback; and
- cost per **successful** task under a predeclared success constraint.

## 3. Evidence table

The table preserves the best reported or most decision-relevant scalar from each source. “Headline only” means the value belongs in its own lane and must not be placed in a cross-paper ranking.

| Track | Method | Exact reported/recomputed point | Workload and models | Success condition | Ledger boundary | Publication and artifacts | Reproduction |
|---|---|---|---|---|---|---|---|
| Full-token compact state | PACT | Qwen3-32B/AIME25 TextMAS 57,984 to PACT 30,970 total model tokens, **-46.59%**; accuracy 60.4% to 72.7% | Two-agent split-evidence QA and four-role reasoning; Qwen3 8B/14B/32B | Point accuracy improves; no interval | Every rendered input plus raw output, including private think; wire/training excluded | arXiv 2026 preprint; partial unlicensed code at `91acf82…` | Literal no; clean-room yes |
| Evolved symbolic language | CLSR | DeepSeek-R1-Qwen3-8B/ScienceQA 125 to 30 online output tokens, **-76.0%**; accuracy 71.3% to 71.5% | Multiple reasoning tasks; Qwen3/DeepSeek-R1 derivatives | Point accuracy non-decreasing | Online generated outputs; inputs and 200-2,000-example evolution excluded | ICML 2026; MIT partial code at `7235a17…`; exact paper config marked unavailable | Literal no; clean-room yes |
| Compact format | AutoForm | HotpotQA: 345.5 to 94.3 generated message tokens, **-72.7%** | 100 each HotpotQA/WikiHop/NarrativeQA; GPT-4-1106-preview initiator + GPT-3.5-turbo-1106 recipient | Score 0.64 to 0.70; paper conflicts between F1 and Rouge-L labels | Generated message only | Findings EMNLP 2024; Apache-2.0 code/data at `8df9450…` | Literal no; clean-room yes |
| Learned format policy | OPTiMACS | Four-task average **-3.4%**; per-task -8.7/-5.4/-18.8/**+19.3%** | GSM+, WikiHop, HotpotQA, NarrativeQA; GPT-4o/o3 and three small open models | GPT-4o average 55.6 to 59.3 | Inference trajectory tokens; 500-2,000 policy-learning examples excluded | Findings ACL 2026; no official code/policy/item manifest | Literal no; clean-room conditional |
| Induced language | EcoLANG | HiSim response tokens 13.02K to 9.80K, **-24.7%**; prompt+completion only about **-6.2%** | PHEME 196 instances; two 1,000-user HiSim events; Llama-3.1-8B + GPT-4o/mini judges | Displayed HiSim quality metrics improve, but no single preregistered gate | Response-token headline; evolution/judging/labeling excluded | Findings EMNLP 2025; MIT partial code at `00878bc…`; evolved artifact/logs absent | Literal no; clean-room conditional |
| Negative control | Tokenese v0.3 | 36/37 English versus 47/48 Tokenese: **1.31x/1.30x larger** | Static matched short example; o200k_base and cl100k_base | Compression goal fails; keyword-minimal English is shorter | Static tokenizer count only | Archived first-party report; MIT code and CC-BY-4.0 spec at `1108a81…` | Literal yes |
| Trained end-to-end MAS | OPTIMA | TriviaQA MAD 408.6 to 32.5 tokens, **-92.0%**; F1 71.0 to 77.1 | Eight QA/reasoning tasks; Llama-3-8B and Llama-3.2-3B | Headline task cell improves | Decoded inference tokens; up to 8-A100 iterative SFT/DPO cost excluded | Findings ACL 2025; public code at `4017740…`, no root license/checkpoints | Literal no; clean-room conditional |
| Topology generation | G-Designer | Exact 20-agent MMLU row 30,317,341 to 1,852,538 prompt tokens, **-93.89%**; accuracy 75.38% to 77.82% | Six tasks; GPT-4-1106-preview; five-agent main and 20-agent scale test | Point accuracy improves | Content-only prompts; completions/training/chat framing excluded | ICML 2025; unlicensed incomplete repo `a6efcfa…` | Literal no; clean-room conditional |
| Adaptive graph pruning | AGP | Rounded MMLU totals 2.6M to 0.25M prompt tokens, about **-90.38%**; accuracy 82.80% to 87.65% | Six tasks; gpt-4o-mini alias | Point accuracy improves | Content-counted prompts; completions/chat framing excluded | ECAI 2025 Spotlight; MIT code `4c55083…`, pinned weights/data | Literal no; clean-room yes |
| Topology pruning | AgentPrune | GPTSwarm HumanEval prompt tokens 2,736,136 to 745,617, **-72.8%** | Six tasks; gpt-3.5-turbo-0301/gpt-4-1106-preview; five agents | 88.49 to 88.96 | Aggregate prompt tokens; completions separate; search-cost inclusion unclear | ICLR 2025; public unlicensed partial code at `c544dd6…` | Literal no; clean-room conditional |
| Dynamic topology pruning | AgentDropout | Average prompt **-21.6%**, completion **-18.4%** versus stated prior method; performance +1.14 | Same six task family; Llama-3-8B, Qwen2.5-72B, DeepSeek-V3 | Llama average 66.51 to 68.70 versus AgentPrune | Prompt/completion separately; 40 training examples/task excluded | ACL 2025; public unlicensed partial code at `855befa…` | Literal no; clean-room conditional |
| Diffusion topology | RADAR | GSM8K AgentPrune 7.7M to RADAR 4.2M prompt+completion inference tokens, **-45.45%**; accuracy 91.92% to 92.51% | Six tasks; five gpt-4o-mini agents | Point accuracy improves | Inference prompts+completions; framing and topology acquisition excluded | ICML 2026; unlicensed incomplete code `71d92b5…` | Literal no; clean-room conditional |
| Workflow compression and routing | AgentSlimming | LiveCode $0.0117 to $0.00247/problem, **-78.9%**; accuracy 55.3% to 61.7% | Eight AFlow-derived workloads; GPT-4.1-mini/nano | Point accuracy improves; validation ratio tau=0.95 | Provider usage priced in USD; mixes removal and model substitution | ACL 2026; MIT code `0bb1afc…` with likely cost-recorder bug | Literal no; clean-room yes |
| Runtime task system | SupervisorAgent | GAIA pass@1 net 527.76K to 371.12K, **-29.68%**; latency **+37.27%** | GAIA plus five benchmarks; GPT-4.1 primary, Gemini/Qwen generalization | Pass@1 exactly 50.91% | Net prompt+completion includes supervisor; tools excluded | ICLR 2026; Apache-2.0 repo `ab116b5…`, only GAIA evaluator complete | Literal no; clean-room conditional |
| Negotiated end-to-end network | Agora | 1,000-query natural-language network $36.23 to Agora $7.67, **-78.83%** | 100 agents; GPT-4o/Llama-3-405B/Gemini-1.5-Pro | No semantic parity oracle; eight API failures | Historical API dollars include negotiation/checking/routine implementation; wire/CPU excluded | arXiv 2024; unlicensed incomplete demo `9dfe683…` | Literal no; clean-room conditional |
| Latent end-to-end MAS | LatentMAS | Hierarchical average **-83.7%** decoded outputs and **4.3x** end-to-end speed; +4.6 accuracy points vs TextMAS | Nine tasks, Qwen3 4B/8B/14B plus Llama scales; three runs | Average improves; some individual cells decline slightly | Decoded outputs exclude latent steps/KV bytes; timing on 8x A100-80GB | ICML 2026 Spotlight; Apache-2.0 code at `9a9e4d3…` | Literal conditional; clean-room yes |
| Cross-context latent cache | LCF-X | Partitioned HotpotQA 502 ms T2T to 94 ms end-of-answer, **5.34x**; F1 32.66 to 35.13, EM 20.53 to 25.28 | 5,899 items; Qwen2.5-0.5B sender to Qwen3-0.6B receiver | Both quality metrics improve; paired significance reported | Communication-path time; hardware/wire/model load undisclosed | ICML 2026 AdaptFM workshop/arXiv; no code/checkpoint/split/license | Literal no; clean-room conditional |
| Latent relay compression | OBF | Repository-only full relay 290.1 MB to 62.4 MB, **4.65x** smaller; paper retains 9.9%-20.2% of prompt positions | Nine-task Qwen3-4B LatentMAS paper; five-task repo byte table | No preregistered NI; rank selected per dataset | Same-A100 logical payload, not external wire bytes; task time slightly worsens | arXiv 2026 preprint; unlicensed code `36f4318…` | Literal no; clean-room yes |
| Latent message compression | Interlat | Full 9.19 s to untrained 8-step 0.39 s, **23.6x**, but success drops | ALFWorld/MATH; Qwen2.5 and Llama-3.1; three runs | Headline cell fails a 1-point non-inferiority gate | Sender message-generation latency only | ACL 2026; Apache-2.0 code at `66a89cb…` | Literal conditional; clean-room yes |
| KV serving boundary | KVCOMM | Corrected fifth-agent TTFT up to **7.82x**, about 430 ms to 55 ms; reuse >70% | Synthetic 1K/512/512 five-agent setup plus MMLU/GSM8K/HumanEval; H100 | No reported task degradation | TTFT/prefill only; remaining 512-token decode excluded | NeurIPS 2025; public unlicensed code at `48ca0b3…` | Literal conditional; clean-room yes |
| Cross-model latent channel | C2C | Abstract average **2.5x** latency speed; +3.06 to +5.36 accuracy points vs T2T | Four main MC benchmarks; Qwen/Llama/Gemma pairs; A100 batch 1 | All three main Sharers beat T2T accuracy | Two-model inference includes fusion; 45-54 GPU-hour fuser training excluded | ICLR 2026; Apache-2.0 code/checkpoints at `113c3a9…` | Literal conditional; clean-room yes |
| Workflow serving boundary | KVFlow | Synthetic 10-agent 8,192/32/32: **1.83x** vs HiCache; PEER Financial QA only 1.08x vs HiCache | Llama-3.1-8B/A10G and Qwen2.5-32B/H100 | Semantics unchanged by cache policy | Full workflow serving latency after warm-up | NeurIPS 2025; Apache-2.0 code at `7ef897e…` | Literal conditional; clean-room yes |

## 4. Same-workload candidates versus headline-only evidence

### 4.1 Primary same-workload baselines

Two baselines are primary for different reasons.

**PACT plus full-history TextMAS** is the primary complete-model-token implementation. Its published driver counts repeated rendered inputs and raw outputs, which is the best disclosed runtime token boundary for a compact agent-state method. The exact AIME25 and 2Wiki rows are same-topology comparisons. Because the repository is unlicensed and incomplete, the implementation must be clean-room from the paper and both arms must run in one new driver.

**AutoForm** is the primary licensed portable-format artifact, not because 72.7% is globally largest, but because it aligns with the portable symbolic-format question:

- the carrier is text/token space rather than model-internal tensors;
- HotpotQA, WikiHop, and NarrativeQA are information-asymmetric communication tasks;
- natural-language and automatic-format variants are published together;
- the repository is licensed and pinned; and
- the same 100-item artifacts can be fed to every format under one harness.

The released artifact digests already audited in this workspace are:

| Artifact | SHA-256 |
|---|---|
| HotpotQA 100-item artifact | `eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284` |
| WikiHop processed artifact | `724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39` |
| NarrativeQA 100-item `test_2agent_15100.jsonl` artifact | `76b5163af50e278a9f1e90848090a4e1b799d4e1d63b47d5fc1aef2ab4bede0b` |

Those hashes identify the local inputs; they do not resolve the paper's F1/Rouge-L or token-counter ambiguity. The reproduction must report both task metrics where applicable and independently count every ledger.

### 4.2 Overlapping tasks that are not same-workload records

OPTiMACS and OPTIMA reuse some benchmark names and even include AutoForm as a baseline, but neither creates a literal cross-paper record:

- OPTiMACS changes the agent count, termination rule, evaluator, training regime, and closed models; its policy-learning sample is only approximately specified and no implementation is released.
- OPTIMA changes the model weights through iterative SFT/DPO, splits information differently, and excludes training from the inference-token headline; no trained checkpoint or root code license is present.

They are valuable stress baselines for future work. Their percentages cannot be appended to AutoForm's table as if they were additional rows from the same experiment.

### 4.3 Topology family

AGP is the primary runnable topology baseline because its MIT repository, learned weights, and training data are public and pinned. RADAR is the required combined-token challenger because its same-paper GSM8K comparison counts prompt plus completion inference tokens; a dense/full graph is the mandatory zero-pruning control. G-Designer supplies the largest exact prompt-only row but not a licensed reproduction artifact.

AgentPrune and AgentDropout remain historical controls sharing six benchmark names and related graph formulations. AgentDropout is the cleaner within-family successor comparison because it reports both prompt and completion tokens and evaluates three model scales. Even this pair is not a record-quality reproduction: training items and costs are not fully separated, repositories lack license grants, model/runtime revisions differ, and the public HumanEval artifacts are not all canonical.

### 4.4 Latent and systems family

LatentMAS, LCF-X, OBF, Interlat, C2C, KVCOMM, and KVFlow answer different systems questions:

- LatentMAS replaces intermediate textual reasoning and communication with hidden-state/KV working memory and reports complete inference time.
- LCF-X translates a compressed cache across two small models and reports TTFT plus complete-answer latency, but releases no implementation.
- OBF prunes and backfills a LatentMAS relay and reports retained KV positions plus a repository-only logical-byte table.
- Interlat measures how aggressively a latent message can be shortened and reports message-generation time.
- C2C trains a cross-model cache fuser for one Sharer-to-Receiver handoff.
- KVCOMM reuses and corrects KV caches across different prefixes to shorten prefill.
- KVFlow preserves likely-to-be-reused prefixes under memory pressure and overlaps CPU-GPU cache movement.

They should be reproduced as separate architectural baselines. None is a portable cross-provider typed protocol; none invalidates a wire-format experiment, and no wire-format byte win invalidates their device-level latency results.

## 5. Exact metric and artifact notes

### 5.1 PACT and CLSR

PACT is the strongest disclosed **complete model-token** compact-state candidate. The claim-safe same-topology row is Qwen3-32B/AIME25: full-history TextMAS uses 57,984 tokens at 60.4% accuracy; PACT uses 30,970 at 72.7%, a 46.59% reduction and 12.3-point gain. A second same-topology split-evidence row is Qwen3-32B/2WikiMultiHopQA: 7,300 tokens and F1 46.4 for TextMAS versus 4,039 and F1 61.3 for PACT, a 44.67% reduction. The 88.41% OpenBookQA reduction is larger but compares against a different debate topology and is not the primary scalar.

The PACT code counts every rendered chat input and raw output over every turn; raw output includes private `<think>` content before ACTION/STATE/RESULT is projected into public history. This is materially more complete than message-only tables. The release still omits baseline implementations, most paper tasks, exact model/data revisions, and the SWE-bench harness, and it has no software license. The safe baseline is therefore a clean-room implementation from the CC-licensed paper, run beside full-history TextMAS inside the same driver.

CLSR is the strongest peer-reviewed induced-symbolism output row in the audit. Its exact DeepSeek-R1-Qwen3-8B/ScienceQA cell is 125 Raw-CoT output tokens at 71.3% accuracy versus 30 tokens at 71.5%, a 76.0% reduction. Qwen3-32B/MATH500 is 845/89.3 to 206/89.4, a 75.62% reduction; Qwen3-8B/HotpotQA is 134/66.4 to 48/66.4, a 64.18% reduction at point-equal accuracy. These are online output tokens only. All input tokens and the evolution of hundreds of candidate symbolic languages over 200-2,000 exemplars and five generations are outside the headline. The MIT repository's own reproduction notes say that exact manuscript reproduction is unavailable, so it is clean-room method evidence rather than a literal numerical baseline.

### 5.2 AutoForm

The best cell is exact: GPT-4-1106-preview initiator, GPT-3.5-turbo-1106 recipient, HotpotQA, natural language 345.5 tokens and AutoForm 94.3 tokens. The reported score rises from 0.64 to 0.70. The same model pairing gives only 9.4% reduction on WikiHop and 33.0% on NarrativeQA. Other pairings include large token reductions with quality regressions; for example, GPT-3.5/GPT-3.5 HotpotQA falls from 0.53 to 0.48 while tokens fall 52.8%. A future claim must publish every task/model cell and may not select the best cell after evaluation.

The artifact is the best legal implementation baseline in the compact-format lane: Apache-2.0, official repository, and task files. It is not a literal historical baseline because provider model aliases no longer identify the exact 2023 snapshots and because the paper never gives a unique full token ledger.

### 5.3 OPTiMACS

The paper's token table is unusually important because it exposes the negative cell:

| Task | Vanilla | OPTiMACS | Change |
|---|---:|---:|---:|
| GSM+ | 2,667 | 2,434 | -8.7% |
| WikiHopQA | 1,023 | 968 | -5.4% |
| HotpotQA | 671 | 545 | -18.8% |
| NarrativeQA | 925 | 1,104 | +19.3% |

The paper also reports an average GPT-4o score of 55.6 for vanilla MAS and 59.3 for OPTiMACS. Learning uses roughly 500-2,000 examples, a maximum 25-step trajectory, three runs, and a single A100 for local models. None of that acquisition cost is included in the token headline. No official code, trained policy, data-index manifest, or license was available at cutoff.

### 5.4 EcoLANG

The generated-response headline is not the cost that dominates the social simulation. On HiSim, response tokens fall 13.02K to 9.80K, but prompt tokens fall only 1.92M to 1.83M and completion tokens 283.79K to 236.83K. Prompt plus completion therefore falls from about 2.204M to 2.067M, approximately 6.2%. On PHEME, the analogous total is about 3.1%. The five-iteration GPT-4o rule evolution and GPT-4o-mini labeling are not in those totals.

This is evidence that a learned communication rule can affect a large repeated simulation. It is not evidence for 24.7% end-to-end cost reduction.

### 5.5 OPTIMA

The main table allows exact task-level comparisons rather than relying on the abstract. Representative iSFT-DPO versus multi-agent debate cells are:

| Task | Baseline score/tokens | OPTIMA score/tokens | Token change |
|---|---|---|---:|
| 2WikiMultiHopQA | F1 25.9 / 543.7 | F1 74.2 / 54.9 | -89.9% |
| TriviaQA | F1 71.0 / 408.6 | F1 77.1 / 32.5 | -92.0% |
| HotpotQA | F1 28.4 / 570.9 | F1 55.6 / 63.3 | -88.9% |
| MMLU | Acc 51.5 / 516.7 | Acc 60.2 / 56.7 | -89.0% |
| MATH | Acc 29.8 / 1,517.6 | Acc 29.3 / 488.1 | -67.8%, with -0.5 point accuracy |

The method is impressive as training-shifted inference efficiency. It is not a cold communication format: up to eight A100s, iterative generation/ranking/training, and 12-24 hours of task training precede the low-token inference. Any deployment comparison must amortize those costs over a declared number of tasks and report the break-even point.

### 5.6 G-Designer, AGP, and RADAR

The topology frontier has three different evidence tiers:

| Method | Exact comparison | Accuracy | Artifact verdict |
|---|---|---|---|
| G-Designer | 20-agent MMLU prompt tokens 30,317,341 to 1,852,538, -93.89% | 75.38% to 77.82% | Largest auditable exact reduction, but prompt-only; unlicensed incomplete code |
| AGP | Rounded MMLU prompt tokens 2.6M to 0.25M, about -90.38% | 82.80% to 87.65% | Strongest practical runnable topology baseline: MIT code, weights, and training data |
| RADAR | GSM8K inference prompt+completion 7.7M to 4.2M versus AgentPrune, -45.45% | 91.92% to 92.51% | Strongest disclosed same-harness combined-token Pareto candidate; incomplete unlicensed release |

G-Designer's separate “up to 95.33%” HumanEval abstract claim has no tabulated numerator and denominator and must not replace the exact 93.89% row. AGP's public controller weights are pinned at Hugging Face revision `cfe982bed2fa10b2c9605bdb1614a49e1bebbdb7`; its training data are pinned at `bee8f49b79df6f4458060f9d3363878347a30fc4`. Historical literal reproduction still fails because `gpt-4o-mini` is not an immutable model snapshot and token totals are rounded/content-only.

RADAR distinguishes inference-only and overall/cold totals. Against AgentPrune, its inference comparison is 7.7M to 4.2M, while the overall comparison is 11M to 6.5M, a 40.91% reduction. Against a full graph, the same inference value is 9.6M to 4.2M, or 56.25%. A reproduction must preselect the baseline and amortization boundary rather than choosing the largest denominator afterward.

### 5.7 AgentPrune and AgentDropout

AgentPrune defines prompt tokens as API input and completion tokens as API output. Its strongest printed prompt reduction is the GPTSwarm HumanEval cell, 2,736,136 to 745,617 tokens, while performance rises 88.49 to 88.96. Completion tokens fall only 1,004,616 to 745,926 in that cell. Elsewhere, completions can rise: AutoGen HumanEval completion tokens increase 130,196 to 139,714 while prompts fall.

AgentDropout explicitly retains both ledgers. For Llama-3-8B across six tasks, multi-round MAS averages 4.7M prompt and 1.0M completion tokens, AgentPrune 4.2M/1.0M, and AgentDropout 3.3M/839K. The appendix states model-specific reductions versus the prior method: Llama 21.4% prompt/16.1% completion, Qwen 24.4%/21.4%, and DeepSeek 18.9%/17.6%. These are more informative than a single pooled percentage.

Neither official repository provides a root license grant. Public visibility is not permission to copy. A reproducible project baseline therefore requires a clean-room implementation or a license from the authors.

### 5.8 AgentSlimming, SupervisorAgent, and Agora

AgentSlimming has the strongest peer-reviewed **monetary** routing row: LiveCode cost per problem falls from $0.0117 to $0.00247, 78.9%, while accuracy rises 55.3% to 61.7%. GSM8K falls from $0.00438 to $0.000930, 78.8%, at equal point accuracy of 95.5%. The result mixes node removal with GPT-4.1-mini-to-nano substitution, so it is a dated price/model-routing result rather than pure communication pruning. Its provider-usage ledger is unusually useful, but the recorded repository revision appears to reverse `node` and `node_id` positional arguments in the cost executor; raw paper ledgers are absent and literal reproduction is not possible.

The claim-safe value is the **net** GAIA pass@1 total:

- Smolagent: 527.76K tokens;
- supervised MAS without supervisor overhead: 314.07K;
- supervised MAS **including** supervisor overhead: 371.12K, a 29.68% reduction.

The supervisor overhead averages about 15.45% of the Smolagent baseline. The same intervention increases average latency from 233.96 s to 321.15 s, or 37.27%. That is a genuine token/latency trade-off, not a Pareto win on every resource. The public repository's GAIA evaluator is usable, but the README still marks other benchmark evaluators as forthcoming.

Agora reports a 100-agent, 1,000-query historical network cost of $36.23 for natural-language-only communication and $7.67 for negotiated/reused routines, 78.83% lower. Unlike most format papers, the ledger includes negotiation, protocol checking, and routine implementation. It lacks a semantic task oracle and excludes CPU, storage, network, and wire cost. In its two-agent weather example, negotiation plus routine implementation costs $0.043 versus $0.020 for one natural-language exchange, so the routine breaks even only after more than two reuses. This is useful amortization evidence, not a parity-controlled record.

### 5.9 LatentMAS, LCF-X, and OBF

The paper reports three distinct averages that must stay paired with their topology:

| Topology | Accuracy versus TextMAS | Decoded output tokens | End-to-end time |
|---|---:|---:|---:|
| Sequential | +2.8 points | -70.8% | 4.0x faster |
| Hierarchical | +4.6 points | -83.7% | 4.3x faster |

The paper's “Token” metric is total decoded output tokens. Latent thought steps and KV working-memory movement are computational work but are not decoded tokens. A fair reproduction must additionally record latent steps, tensor dimensions, device-to-device or host-device bytes, peak memory, and energy. Timing uses eight A100-80GB GPUs and averages three independent runs.

LCF-X is the strongest reported quality-preserving complete-answer latency cell: on 5,899 partitioned HotpotQA items, T2T at a 200-token sender limit reports F1 32.66, EM 20.53, TTFT 410 ms, and time-to-end-of-answer 502 ms; LCF-X reports 35.13, 25.28, 48 ms, and 94 ms. The resulting speedups are 8.54x TTFT and 5.34x full response. The paper does not release code, adapter weights, the exact split, hardware, warm-up, synchronization, or physical transfer bytes. It is the strongest reported cell, but LatentMAS remains the strongest reproducible peer-reviewed baseline.

OBF addresses LatentMAS's payload rather than only decoded output. The reviewed preprint reports retaining 9.9%-20.2% of prompt-KV positions; its cutoff repository adds a five-benchmark table with 290.1 MB for full relay and 62.4 MB for layerwise/fast L-OBF, a 4.65x logical-footprint reduction. That byte table is post-submission, same-A100, and not independently reviewed. Fast L-OBF takes 25.79 s versus 24.67 s full relay, so compression does not improve task time on that pointer-pass setup. The unlicensed code cannot be copied; an independent implementation should measure serialized bytes across an actual device or network boundary.

### 5.10 Interlat

The approximately 24x value is obtained by dividing 9.19 s full-message generation by 0.39 s for an untrained eight-step latent. The corresponding ALFWorld seen/unseen success changes from 70.48/65.42 to 64.00/57.46. The learned eight-step bridge reaches 0.20 s but still reports 66.43/60.45, below the full baseline. The source calls performance competitive; a world-record experiment needs a numerical, preregistered non-inferiority bound and may not redefine “competitive” after seeing results.

### 5.11 KVCOMM

The corrected paper defines TTFT for each agent after a 1K user input, 512-token prefix, and 512-token shared response in a five-agent setting. Agent 5 reaches 7.82x TTFT speedup. A final-paper footnote says the original submission omitted first-token decoding latency; the final definition includes it. This correction is a mandatory reproduction detail.

Task experiments on MMLU, GSM8K, and HumanEval support more than 70% KV reuse without reported quality degradation. They do not turn 7.82x into end-to-end task speed because the remaining 512-token decode is outside TTFT.

### 5.12 C2C

The main MMLU-Redux timing breakdown for Qwen2.5-0.5B-Instruct to Qwen3-0.6B is:

| Path | Input/output behavior | Time |
|---|---|---:|
| Text-to-text | Sharer decodes 80 tokens, Receiver processes message and decodes 10 | 1,596 ms |
| Cache-to-cache | Sharer decodes 0, fuser costs 90 ms, Receiver decodes 12 | 445 ms |

The complete paper averages across tasks and model pairs to its 2.5x headline; the 3.59x table cell is not the general number. Training the fuser is real acquisition cost: full 1,929-step runs take roughly 44.72-54.24 GPU-hours for the three headline pairs, though 300 steps obtain comparable MMLU-Redux results in under nine GPU-hours. Released Hugging Face fuser checkpoints make inference reproduction materially stronger than most latent-channel papers.

### 5.13 KVFlow

KVFlow is a lower-bound systems control for any end-to-end latency claim. In the strongest single-workflow cell, a warmed 10-agent sequence with 8,192 fixed, 32 dynamic, and 32 output tokens is 1.83x faster than SGLang with HiCache and 2.91x faster than GPU-only SGLang. Under high concurrency, the “up to 2.19x” number is against reactive HiCache, while improvement over both baselines is at most 1.25x. On PEER-style Financial QA, the more realistic gain is at most 1.12x versus SGLang and 1.08x versus HiCache.

Because weights, prompts, and greedy decoding remain unchanged, task semantics should be identical. That makes KVFlow a strong serving control but not a communication-codec result.

## 6. Strongest reproducible baseline decision

The word “strongest” needs a declared objective. The decision for this project is:

1. **Primary complete-token baseline: clean-room PACT plus full-history TextMAS.** It is the strongest disclosed runtime token ledger for compact public-state communication. Reimplement from the paper because the partial repository has no license; do not call it a literal replication.
2. **Primary licensed portable-format artifact: AutoForm.** Use its pinned 100-item task bundle and Apache-2.0 implementation in the same modern-model harness. Its historical proprietary-model numbers are not literal.
3. **Primary topology baseline: AGP, with dense/full graph and RADAR.** AGP is the strongest artifact-backed implementation; RADAR is the strongest disclosed same-harness prompt-plus-completion Pareto candidate. If topology is outside the claim, keep their results in a separate lane rather than charging them to a surface-format arm.
4. **Primary latent baseline: LatentMAS.** It is the strongest reproducible peer-reviewed end-to-end latent reference. Add OBF or an independent equivalent for payload compression; treat LCF-X as a paper-only challenger until artifacts exist.
5. **Mandatory static negative control: Tokenese plus terse/keyword-minimal English.** Tokenese is literally reproducible and falsifies the assumption that novel syntax is automatically token-efficient.
6. **Mandatory structured controls: canonical minified JSON, JSON Schema with constrained decoding where supported, and terse natural language.** These are not optional because the project's research rules require strong incumbent baselines.
7. **Mandatory compression controls: a persistent general-purpose compressor and a schema-aware codec.** Report raw and compressed full-envelope bytes separately; a novel alphabet is not evidence of efficiency.

This decision is about auditability and same-workload relevance, not the largest percentage printed in any abstract.

## 7. Exact experiment required before any world-record statement

The following protocol is the minimum claim experiment. It is written as a preregistration specification; any change after observing results creates a new experiment.

### 7.1 Claim sentence and primary endpoint

Pre-register one lane-specific claim only:

> On the pinned public workload, model pairings, and cold-start protocol below, method X reduces **full serialized envelope bytes per successful task** relative to the best enabled baseline while meeting the task-success and safety non-inferiority gates.

The primary endpoint is:

\[
E_{bytes}=\frac{\sum_i B_{full,i}}{\sum_i I(\text{task }i\text{ succeeds and all safety gates pass})}
\]

where `B_full` includes every transmitted envelope byte from process start: grammar/capsule, negotiation, task handoff, messages, provenance, uncertainty, authority metadata, repair, retry, fallback, and framing. A failed task consumes bytes but contributes no success to the denominator.

Co-primary operational endpoints must be reported but cannot be substituted after the run:

- all runtime prompt tokens per successful task, counted with the receiving model's pinned tokenizer/chat template;
- all runtime completion/reasoning tokens per successful task;
- cold-start and warm steady-state end-to-end wall-clock;
- raw payload bytes and persistent-compressor bytes; and
- peak memory and, for latent methods, latent steps plus transferred tensor bytes.

### 7.2 Frozen workloads

Use three families so a claim cannot be won by overfitting one message shape:

1. **Information-asymmetric QA:** the exact AutoForm HotpotQA, WikiHop, and NarrativeQA artifacts identified above, 100 tasks each. Preserve the published split and publish item IDs/order.
2. **Held-out public QA:** before running models, draw 300 additional items from each upstream task with a deterministic SHA-256 ordering rule, remove any overlap with induction/tuning, and publish the resulting manifest and digest.
3. **Typed transactional/conformance tasks:** at least 300 generated cases covering requests, proposals, authenticated commits, units, uncertainty, causal references, unknown schema/act/unit/effect/authority values, and unknown extension bytes. The generator seed, schema, oracle, positive cases, and adversarial negative cases must be public. Unknown or unauthorized content must fail closed before side effects.
4. **Topology/end-to-end audit:** full GSM8K with 1,319 items and canonical HumanEval with 164 problems, both pinned by content digest. This lane is mandatory before any claim spanning topology or general agent-task communication and is where dense graph, AGP, RADAR, and clean-room PACT/TextMAS are compared.

No evaluation item may be used for format induction, prompt selection, topology search, or threshold tuning. A separate development set must be published before evaluation.

### 7.3 Frozen agents and pairings

Use three independently tokenized open-weight families in the 7B-9B range so the run is locally reproducible without paid APIs. At preregistration, record for each:

- Hugging Face repository and immutable weight revision;
- SHA-256 or safetensors manifest digest;
- tokenizer files and chat-template digest;
- inference engine/container digest;
- quantization state, precision, context limit, and generation implementation.

Evaluate all nine ordered sender/receiver pairings, including three homogeneous and six heterogeneous pairings. Designate two heterogeneous pairings as development pairings and keep at least four ordered pairings completely unseen by format induction. Do not advertise `native` model support when only a bridge/translator is evaluated.

Use deterministic greedy decoding for the primary lane. Run a robustness lane with temperature 0.2 and seeds 0, 1, 2, 3, and 4. Fix maximum generation lengths per role before evaluation. A parser failure invokes the same public repair/fallback policy for every method and all repair cost is charged.

### 7.4 Methods and controls

Run every task/pairing under the same agent roles, information partition, prompts, stop conditions, tool permissions, and maximum turns:

1. terse natural language written specifically for the task;
2. canonical minified JSON with explicit field names;
3. JSON Schema plus constrained decoding where the engine supports it, with unsupported engines disclosed rather than silently advantaged;
4. full-history TextMAS and a clean-room PACT ACTION/STATE/RESULT implementation in the identical driver;
5. AutoForm at the pinned official revision, adapted only through a published compatibility layer;
6. the project method in `bridge` mode;
7. any claimed `native` mode as a separate arm;
8. the best enabled fallback selected without access to evaluation labels;
9. static Tokenese/keyword-minimal examples as a tokenizer negative control, not as a receiver-task arm unless a complete teaching/repair path is supplied; and
10. raw, gzip or Brotli persistent-stream, and schema-aware binary codec transport for every structured arm.

If topology efficiency is part of the claim, add dense/full graph, AGP at the recorded code/weight/data revisions, RADAR clean-room, and AgentPrune or AgentDropout clean-room. If latent efficiency is in scope, add TextMAS, LatentMAS at the recorded revision, OBF or an independent fixed-budget equivalent, C2C, KVCOMM, and KVFlow only in their matching architecture/ledger lanes. Do not compare their headline percentages to envelope bytes.

### 7.5 Cold, warm, and acquisition ledgers

Run two separately reported regimes:

- **Cold:** a fresh process and empty conversation/cache for every task. Charge the full grammar capsule, examples, schema, negotiation, model load policy, and first repair/fallback.
- **Warm:** one persistent session over a fixed random task order. Publish cumulative cost and amortized cost after tasks 1, 10, 100, 300, and 1,000. Reset exactly when the preregistration says to reset.

Induction/training/search cost is never free. Report it once and amortize it at each horizon above. If a method never breaks even against the best baseline within 1,000 tasks, state that result.

### 7.6 Event-level ledger

Write an append-only row for every event with at least:

`run_id`, `task_digest`, `method`, `model_role`, `model_revision`, `call_index`, `message_id`, `parent_id`, `causal_refs`, `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `cache_read_tokens`, `cache_write_tokens`, `payload_bytes`, `full_envelope_bytes`, `compressed_bytes`, `latent_steps`, `logical_tensor_bytes`, `serialized_tensor_bytes`, `wire_bytes_tx`, `wire_bytes_rx`, `serialize_ms`, `network_queue_ms`, `network_transfer_ms`, `deserialize_ms`, `wall_start`, `wall_end`, `repair`, `retry`, `fallback`, `tool_call`, `task_score`, `semantic_valid`, `authority_valid`, `provenance_valid`, and `safety_valid`.

Preserve raw requests/responses where licensing and privacy permit; otherwise publish deterministic hashes plus a redaction manifest. Content is not authority. Only authenticated and authorized commits may create a public obligation. Every unknown type and negative authorization test must fail closed before side effects.

### 7.7 Success and statistical gate

Pre-register the task metric per family: exact match or source-standard F1/Rouge-L for QA, and exact oracle outcome for typed tasks. The project arm must meet all of these:

1. paired task-success difference versus the best enabled fallback has a 95% lower confidence bound greater than **-1.0 absolute percentage point**;
2. zero unauthorized side effects and zero acceptance of unknown authority/effect/unit/schema cases in the negative suite;
3. exact preservation of required provenance, uncertainty, causal references, units, and store-and-forward unknown bytes;
4. no statistically significant increase in repair/fallback rate after Holm correction across families; and
5. the 95% upper confidence bound of the paired `E_bytes` ratio is below 1.0 on at least two task families and at least two unseen heterogeneous pairings.

Use paired bootstrap intervals over task IDs with at least 10,000 resamples and publish the resample seed. Also publish raw paired differences, medians, tails, and failure cases. Five robustness seeds do not replace task-level uncertainty.

### 7.8 Causal communication audit

Token, byte, or latency savings do not prove that the transferred message causes success. For every learned latent or induced channel, add four geometry- and byte-matched arms:

1. the true aligned sender message;
2. a fixed-point-free derangement using another task's message;
3. an all-zero message; and
4. a moment-matched random message.

Run both a sender-private calibration task that the receiver cannot solve without transferred information and the natural benchmark. The primary communication estimand is `success(true) - success(deranged)`, not `success(true) - success(zero)`, because zeroing can damage model execution even when message semantics are unused. Use at least 500 examples per arm/seed, fixed 25-by-20 batches, the five receiver-sampling seeds above, seed-level two one-sided equivalence tests with a predeclared practical margin, and Holm correction. Publish every pairing and do not select the perturbation after seeing results.

### 7.9 Claim threshold and release

A scoped result may be described only as:

> Best observed under the named model revisions, task manifest, ledger, success gate, and cutoff among the listed baselines.

A **world-record** phrase remains prohibited until all of the following are true:

- the preregistration, implementation, data manifests, raw ledgers, and analysis code were public before evaluation;
- all positive and negative conformance tests pass;
- the exact grammar capsule digest, implementation revision, and conformance-report digest are recorded;
- terse English, minified JSON/schema, persistent compression, schema-aware codec, full-history TextMAS, clean-room PACT, AutoForm, AGP/RADAR in any topology claim, and the best enabled fallback were all run;
- at least one unseen partner evaluation beats the best enabled fallback on total cost while satisfying task success;
- an independent party reproduces the result from the release artifacts; and
- unfavorable cells and unsuccessful task families remain published.

Even then, the claim must name its lane. “Most communication-efficient agent language” is too broad; “lowest full-envelope bytes per successful task on manifest X under models Y and success gate Z” is testable.

## 8. Screened evidence not converted into a record

| Candidate | Status at cutoff | Decision |
|---|---|---|
| CARD / AMACP | ICLR 2026 | Keep as adaptive-topology evidence. No scalar token table; the cost frontier is not recoverable into a reduction percentage. Repository `d5d1f68…` has a license badge but no license text, and its cost helper hard-codes a GPT-4 price label independent of the actual backbone. |
| GTD | ACL 2026 | GSM8K is 4.8M inference tokens at 94.14%; prose says G-Designer uses 15% more and one-time data generation is about 0.4M. No exact baseline row; repo `22738c3…` is unlicensed, lacks weights/results, and defaults to GPT-4o rather than paper GPT-4o-mini. |
| GoAgent | arXiv v1 | GSM8K ARG-Designer 4.1M to GoAgent 3.4M total inference tokens, -17.07%; accuracy 94.37% to 95.30%. Training generation excluded; no code/data/weights/license. |
| DyTopo | arXiv v1 | HumanEval 19,520 to 9,453 total tokens/instance, -51.57%; accuracy 90.24% to 92.07%. Confounded by 2.6-round early stop versus a forced five-round baseline; ledger undefined and no code. |
| ATOM | arXiv v1 | HumanEval approximately 0.53M to 0.37M total tokens, more than -30%; accuracy 68.60% to 71.90%. No exact item counts, counter boundary, code, or license. |
| AgentConductor | ICML 2026 main conference | The 68% abstract claim lacks a named denominator. The exact APPS table supports 459,750 to 357,400 combined tokens versus G-Designer, -22.26%, with 37.2% to 58.8% accuracy; no artifacts. |
| SafeSieve | AAAI 2026 | HumanEval 444K to 321K combined tokens, -27.70%, but accuracy falls 95.50% to 95.01%. Repo `0af1b31…` is unlicensed and tokenizes every backbone as GPT-3.5 Turbo Instruct. |
| HyLaT | arXiv preprint | TextFullT 505.03 to HyLaT 72.01 visible tokens and 5.47 s to 1.47 s, but mean/majority accuracy falls 0.57/1.33 points and latent bytes are omitted. Apache code `4a805c3…` lacks checkpoints and GPT-5-generated training data. |
| RecursiveMAS | arXiv v2 | At recursion budget 3, reports -75.6% tokens and 2.4x speed with better shown point accuracy. MIT repo `38f7da4…` does not implement the ledger; paper checkpoints differ and full search/evaluation uses unavailable or external large-model services. |
| DiffMAS | arXiv preprint | Accuracy and latent-step ablations only; no token, byte, time, memory, FLOP, or throughput metric, and no official artifacts. It is not efficiency evidence. |
| Dense heterogeneous latent MAS | arXiv preprint | Estimated context FLOPs are about 3.28x lower by ratio of sums, but paper states 20-30 MB KV payload/sample versus hundreds of bytes for text. Only 17 examples/benchmark inform FLOPs; repo `0c74008…` is an unlicensed website placeholder. |
| Agent Primitives | ICML 2026 | Qwen3-8B tables imply 4.19x fewer output tokens and 3.35x speed versus TextMAS. Organizer is GPT-5.2; hardware/seeds are absent; repo `b990654…` is unlicensed and says the end-to-end pipeline is coming soon. |
| MetaGlyph | arXiv preprint | 215 to 41, -80.9%, counts instruction-only regex pseudo-tokens, excluding task input/output, and is single-model prompting. Noncommercial repo `7086b7b…` has a 50-versus-150 item-config conflict. |
| XBridge | arXiv preprint | Short-context HotpotQA 1.70 s natural language to 0.15 s, 11.33x, but it transmits full mapped context plus a full hidden-state sequence. Apache repo/checkpoint/cache support one direction only; no wire ledger. |
| StateBridge | COLM 2026 per paper | Sends 64 aligned states only after the sender decodes a full message; reports accuracy but no efficiency scalar. Apache repo `3f6bf54…` does not convert it into an efficiency record. |
| Q-KVComm | arXiv preprint | Calculated KV footprint is about 6.93x/5.69x/5.07x at 4/6/8 bits with 70% layers. Quality is heuristic similarity, not task accuracy; no exact bytes, timing, hardware, or code. |
| AgentArk | arXiv preprint | Adjacent training-shift method: multi-agent behavior is distilled into one runtime model. It does not preserve runtime inter-agent communication or publish a comparable communication ledger. |
| PAIRL | First-party repository/specification | Apache-2.0 tag `v1.6.2` at `0286fd1…`. Advertised 47%-67% is explicitly modeled illustration and the approximate 95% history example lacks a released pairl-bench ledger; keep as a watch item. |

The machine-readable screened list is in `registry.json`. New candidates should be added only after the same primary-source, ledger, artifact, and license checks.

## 9. Integrity and maintenance

The registry checker enforces the following release invariants:

- project SOTA and world-record flags must remain false;
- paid model calls must remain false for this audit;
- every record must name a comparability lane, workload, models, ledger boundary, success condition, sources, artifact state, license state, and reproduction classification;
- available Git repositories must use a full 40-character lowercase commit pin;
- incomparable headlines must explain why they are incomparable; and
- the primary and mandatory claim baselines must resolve to actual records.

`DIGESTS.sha256` pins the report, registry, schema, checker, tests, and README. The digest file excludes itself to avoid a self-reference. A future update must change the cutoff, re-resolve every moving repository head, preserve old unfavorable evidence, rerun the tests, and regenerate the manifest.

## 10. Naming handoff

This audit directory intentionally uses neutral names and contains no project package or CLI import. The final freeze includes an exact filename, import/identifier, and content-string scan for every retired or canceled project-name candidate supplied to the release coordinator. External method names and paper titles are evidence fields, not project branding. The handoff message reports the occurrence inventory; no cross-project rename is performed here.

## 11. Bottom line

The strongest evidence does not support a universal record. It supports a disciplined experiment:

- Clean-room PACT plus full-history TextMAS is the primary complete-model-token baseline; AutoForm is the primary licensed portable-format artifact.
- AGP is the strongest artifact-backed topology baseline, with RADAR as the required combined-token challenger and dense graph as the control.
- Tokenese, terse English, JSON/schema, and strong codecs are mandatory controls.
- LatentMAS is the strongest open peer-reviewed latent end-to-end reference, but only in an architecture-coupled lane.
- LCF-X is the strongest reported quality-preserving complete-answer latent latency cell, but has no release; OBF is a payload candidate, not a wire-speed result.
- KVCOMM and KVFlow establish systems-level prefill/workflow bounds that message-only claims must not mislabel.
- Every acquisition, repair, fallback, envelope, and failure must enter the cost ledger.

Until the exact preregistered experiment in Section 7 is completed and independently reproduced, this project has no SOTA or world-record evidence.
