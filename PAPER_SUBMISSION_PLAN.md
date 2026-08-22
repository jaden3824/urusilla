# Urusilla paper submission plan

Status: working submission plan, not a submission decision  
Evidence cutoff: 2026-08-23  
Primary route: Transactions on Machine Learning Research (TMLR)  

## 1. Decision summary

Urusilla should currently be written as an **evaluation-methods and negative-results paper**, not as proof of an efficient universal agent language. The defensible contribution is a reproducible way to distinguish wire compression from safe end-to-end task efficiency, together with fail-closed routing, complete-cost accounting, causal-use controls, and retained counterexamples.

The venue order is:

1. **TMLR — primary.** Submit when the methods evidence gate in this document passes. TMLR is rolling, so a deadline must not be used to weaken the study.
2. **AAMAS 2027 Main Track — conditional.** Consider only if the same-context receiver path, frozen multi-domain experiment, and paper-quality evidence are complete before the internal September gate.
3. **DMLR — benchmark split.** Use only for a distinct benchmark-and-evaluation paper whose central contribution is the preregistered dataset, ledger, and evaluation method rather than the Urusilla protocol.
4. **ICLR 2027 — defer.** Do not target the current cycle unless a new, complete result establishes a broad machine-learning insight beyond protocol engineering. The current evidence does not meet that bar.

These are mutually exclusive archival routes for substantially overlapping work. No paper should be under review at more than one archival venue at the same time.

## 2. Claim boundary at the evidence cutoff

### Claims supported now

- The frozen 2,542-turn broad-dialogue lane demonstrates **0% token saving for general communication between unfamiliar agents** under the project's stated boundary.
- The no-regret fallback hypothesis passes, while the general compact-value and repeated-context hypotheses fail.
- Warm receiver-carrier saving is only 0.65% to 0.80%; cold and post-decode API-input saving are 0%.
- Narrow positive serialization and synthetic-state results do not establish end-to-end task efficiency.
- The project contains testable fail-closed routing, binding, fallback, and accounting mechanisms.
- The negative results motivate a methods contribution: representation savings must be separated from safe-task success, repair, setup, fallback, tool, and judge costs.

### Claims not supported now

- No state-of-the-art or broadly superior communication result.
- No token, cost, latency, or energy saving per safely completed real-model task.
- No demonstrated causal consumption of a compact payload by an unfamiliar real receiver.
- No independent benchmark reproduction, clean-room implementation, adoption, or persistent diffusion.
- No claim that agents internally reason or “think” in Urusilla.
- No claim that a universal syntax should replace natural language, JSON, source documents, or existing transport protocols.

Every abstract, title, figure, release note, and external post used during the submission process must preserve this boundary.

## 3. Submission evidence gates

### 3.1 Methods-paper gate

All items below are required before submitting the current methods/negative-results paper, even when the final result remains negative:

- A frozen study manifest defines tasks, domains, models, prompts, arms, exclusions, stopping rules, metrics, and statistical analysis before confirmatory provider runs.
- Raw concise text, canonical JSON, and the Urusilla hybrid route are evaluated under matched tasks, model settings, tool access, and success criteria.
- The receiver sees the Capsule and task-critical action state in the same live context; the evaluated optimized path does not silently expand the payload back into ordinary prose before model consumption.
- Causal controls include at least a valid task-critical payload, a task-critical mutation or removal, and a task-irrelevant re-encoding.
- Every actual compiler, verifier, setup, router, primary receiver, fallback, repair, tool, safety, and judge call is retained. Unknown usage remains unknown and cannot be imputed as zero.
- Failed attempts remain in cost denominators. Operation-level success grouping never deduplicates billed attempt-level cost.
- Semantic fidelity, safe task success, refusal, repair, fallback, and prohibited-effect outcomes are reported alongside tokens.
- All preregistered arms and strata are published, including null, unfavorable, incomplete, and malformed-input outcomes.
- The committed artifact can reproduce tables from immutable raw evidence without manual row selection.
- AI assistance, human decisions, model versions, provider settings, code revisions, and known conflicts are disclosed according to the selected venue's policy.

Passing this gate makes a methods paper reviewable. It does **not** establish an efficiency win.

### 3.2 Efficiency-claim gate

An efficiency or general-language claim remains prohibited unless the frozen initial-goal study also demonstrates, against the better successful baseline of concise natural language and canonical JSON:

- safe-task-success non-inferiority;
- at least 20% lower fully accounted total tokens per safely completed task;
- at least 99% unseen-partner parse validity;
- at least 95% held-out semantic fidelity;
- zero prohibited authority or effect events;
- multiple model families and multiple domains; and
- independently operated evidence rather than project-authored fixtures alone.

A codec ratio, wire-byte reduction, favorable tokenizer, synthetic repetition result, safe fallback, project-operated public reply, or decode-before-model transport saving cannot substitute for this gate.

### 3.3 Stop conditions

Stop a deadline-driven submission and retain the work for TMLR if any of the following is true:

- a required usage category is unknown for the confirmatory comparison;
- the receiver path is exercised only by fake or constant-response adapters;
- the task or scorer is changed after seeing confirmatory outcomes without labeling the change exploratory;
- a result depends on excluding failed attempts, fallback calls, or setup cost;
- the paper would need “universal,” “efficient,” “adopted,” or “energy-saving” language to appear novel; or
- the anonymous artifact cannot be separated from identifying public project material where double-blind review requires it.

## 4. Venue decisions

### 4.1 TMLR — primary route

- **Schedule:** rolling submission; no fixed conference deadline.
- **Official scope:** TMLR welcomes experimental studies that expose strengths and weaknesses, new task and evaluation formalizations, and reproducibility studies. Its acceptance criteria prioritize accurate, convincing evidence and interest to some part of the audience rather than a state-of-the-art result.
- **Fit:** strongest fit for the claim taxonomy, complete-cost ledger, causal-consumption gate, fail-closed fallback, and honest broad-dialogue failure.
- **Required framing:** “When compact agent messages fail to reduce safely completed task cost, and how to measure that failure.” Urusilla is the evaluated system and artifact, not proof of a universal language.
- **Primary risk:** a repository chronology or long catalogue of experiments is not itself a research contribution. The paper must extract generalizable failure modes, falsifiable methodology, and actionable design rules.
- **Review constraints:** double-blind manuscript and supplementary material; identifying preprints are allowed, but the anonymous TMLR submission must not link to an identifying version. TMLR forbids overlapping archival submission and requires responsible disclosure of LLM assistance.
- **Official pages:** [venue and rolling process](https://jmlr.org/tmlr/), [scope and editorial policies](https://jmlr.org/tmlr/editorial-policies.html), [acceptance criteria](https://jmlr.org/tmlr/acceptance-criteria.html), [author guidelines](https://jmlr.org/tmlr/author-guide.html).

**Decision:** proceed as the default route after the methods-paper gate passes, regardless of whether the performance result is positive, null, or negative.

### 4.2 AAMAS 2027 Main Track — conditional route

- **Dates:** OpenReview author registration 2026-09-17; abstract 2026-10-01; paper 2026-10-08; conference 2027-05-03 through 2027-05-07. Deadlines are Anywhere on Earth.
- **Best area:** Engineering and Analysis of Multiagent Systems (EMAS). The official call explicitly includes agent programming languages, agent-to-agent protocols, testing and validation, interoperability, reproducible testbeds, and evaluation methodologies. Generative and Agentic AI (GAAI) is secondary if real generative-agent interaction and failure recovery are central.
- **Fit:** a concise methods paper can foreground protocol state, same-context consumption, heterogeneous-agent causal controls, and failure-preserving interoperability.
- **Required evidence by internal gate:** a complete frozen multi-domain result, a sealed reproducibility bundle, and an eight-page draft whose main contribution is understandable without supplementary material.
- **Primary risk:** AAMAS evaluates originality, significance, soundness, reproducibility, and relevance. A 0% result without a generalizable experimental lesson and functioning multiagent path is insufficient. The short schedule must not convert development fixtures into empirical claims.
- **Review constraints:** double-blind; the paper and supplementary archive must not reveal identity. Substantially similar work cannot be under review at another archival venue. AI assistance used in hypothesis or methodology creation requires detailed disclosure, including tool/version and prompts, under the official policy.
- **Official pages:** [main-track call and areas](https://warwick.ac.uk/fac/sci/dcs/aamas2027/calls/call-for-main-track/), [submission, anonymity, AI-assistance, and dual-submission rules](https://warwick.ac.uk/fac/sci/dcs/aamas2027/calls/instructions/).

**Decision:** make a go/no-go decision by 2026-09-14. Register authors on 2026-09-17 only after a truthful full-paper outline and the required evidence exist. If the gate fails, do not submit an abstract merely to reserve a slot; continue toward TMLR.

### 4.3 DMLR — benchmark split only

- **Schedule:** rolling submission.
- **Official scope:** DMLR explicitly includes benchmarking tools and methods, experimental design, registered experiments, empirical-evaluation methodology, and systematic analyses that yield new insight.
- **Fit:** appropriate for a separately scoped benchmark paper centered on the frozen task corpus, raw/JSON/hybrid arms, causal payload interventions, complete attempt ledger, and reproducibility contract.
- **Required separation:** the benchmark paper must have its own research question, artifact contract, maintenance plan, data documentation, and benchmark-specific conclusions. It must not be a lightly rewritten copy of the TMLR or AAMAS paper.
- **Primary risk:** a communication protocol paper with an attached dataset is not data-centric enough. DMLR also applies a scientific-significance bar and requires strong reproducibility and responsible-use documentation.
- **Review constraints:** DMLR uses single-blind review, so the public repository does not create the same anonymity problem. It still prohibits concurrent overlapping archival submission.
- **Official pages:** [DMLR submissions and scope](https://data.mlr.press/submissions.html), [DMLR venue](https://data.mlr.press/).

**Decision:** do not split now. Reassess only after the evaluation bundle is stable enough to be useful independently of Urusilla.

### 4.4 ICLR 2027 — defer

- **Dates:** abstract 2026-09-18; paper 2026-09-25, Anywhere on Earth.
- **Potential scope:** datasets and benchmarks, infrastructure and software, and neurosymbolic or hybrid AI systems are included.
- **Why defer:** the current contribution is primarily protocol engineering and evaluation methodology. It does not yet establish a broad learning, representation, generalization, or causal model-behavior result. The official call explicitly asks authors to submit complete, mature work and notes that all reviewed submissions ultimately remain public with author names attached.
- **Official pages:** [ICLR 2027 call for papers](https://www.iclr.cc/Conferences/2027/CallForPapers), [author guidelines](https://iclr.cc/Conferences/2027/AuthorGuidelines).

**Decision:** do not register an ICLR 2027 abstract under the current evidence profile. Reconsider a later ICLR cycle only after a complete end-to-end study produces a general machine-learning insight that remains valuable even if Urusilla is removed from the title.

## 5. Four-week deliverable matrix

The four weeks below start on 2026-08-24. A checked deliverable requires an immutable artifact or reviewable manuscript change, not an intention or external invitation.

| Workstream | Week 1: Aug 24–30 | Week 2: Aug 31–Sep 6 | Week 3: Sep 7–13 | Week 4: Sep 14–20 / exit condition |
|---|---|---|---|---|
| Research contract | Freeze research questions, arms, domains, models, exclusions, stopping rules, claims, and analysis plan. Separate confirmatory from exploratory work. | Verify that every planned result row is derivable from frozen fields. Seal manifests before confirmatory calls. | Audit protocol deviations and label every deviation; do not silently revise hypotheses. | Publish an internal gate report listing pass, fail, unknown, and unevaluated items. No ambiguous “partial pass.” |
| Receiver path | Audit the completed same-context Capsule-to-direct-action-state executor and bound raw/JSON fallback; retain malformed-payload, context-drift, invalid-output, and failed-adapter regressions. | Run provider-neutral integration pilots; demonstrate that task-critical mutation changes the result and irrelevant re-encoding does not, without counting pilots as confirmation. | Freeze the exact runtime revision and request artifacts used for confirmation. | Required for AAMAS go; if the evidence remains fake-adapter-only, AAMAS is no-go and TMLR work continues without a causal-use claim. |
| Confirmatory evaluation | Finalize matched raw, JSON, and hybrid requests and full usage schema. | Execute frozen multi-domain, multi-model arms within an approved budget; retain every attempt, failure, repair, and fallback. | Recompute tokens, task outcomes, fidelity, safety, intervals, and sensitivity checks from raw evidence. | Methods gate may pass with a negative result. Efficiency language remains forbidden unless every Section 3.2 gate passes. |
| Reproducibility | Pin source revisions, model settings, tokenizer versions, task digests, and environment metadata. | Produce deterministic validators and a one-command offline table rebuild; preserve raw provider receipts without treating self-issued receipts as authentication. | Create an anonymous review bundle and test it from a clean environment. Record any non-reproducible step. | Bundle must reproduce all headline tables. Unknown provenance or manual row selection is a submission stop. |
| Manuscript | Convert chronology into three or four general research questions and a compact claim-to-evidence table. Draft methods before looking at final outcomes. | Draft related work, experimental design, accounting boundary, and limitations. Keep the 0% broad result visible but not promotional. | Complete results, counterexamples, threats to validity, broader impact, and AI-assistance disclosure log. | Produce a TMLR-format full draft. Produce an eight-page AAMAS draft only if it can stand alone without inflated claims. |
| Venue decision | Confirm TMLR formatting, anonymity, originality, and human authorship requirements. | Map the frozen contribution to TMLR; map AAMAS only to EMAS or GAAI, not to a generic “AI language” pitch. | Conduct a hostile internal review: try to falsify causal use, total-cost completeness, novelty, and venue fit. | On Sep 14 choose **AAMAS conditional go** or **TMLR continue**. Default ICLR decision is defer. DMLR remains a future benchmark split. |

## 6. Publication-integrity rules

1. **One overlapping archival review at a time.** TMLR, AAMAS, DMLR, and ICLR are alternatives, not parallel submissions. Preprints and explicitly non-archival workshops are handled only under the selected venue's current written policy.
2. **Human authorship and accountability.** AI systems are tools, not authors. Every listed human author must verify the manuscript, sources, experiments, statistics, and artifact and accept responsibility for them.
3. **AI-assistance log.** Retain tool and model versions, dates, the role of assistance, material prompts used for hypotheses or methodology, and the human verification performed. Convert the log to the selected venue's required disclosure.
4. **Double-blind separation.** For TMLR or AAMAS, the PDF and review supplement must remove names, affiliations, account handles, identifiable repository URLs, self-referential phrasing, and metadata. Use a sealed anonymous artifact snapshot if permitted; do not misrepresent the existence of the public project.
5. **No evidence laundering.** Project-operated tests, external comments, artifact retrievals, self-issued receipts, and public replies retain their exact provenance. They cannot be relabeled as independent reproduction or adoption.
6. **No deadline exception to claim gates.** Missing evidence becomes “unknown” or “not evaluated.” It is never filled by forecast, analogy, or a favorable serialization result.
7. **Negative results remain first-class.** A failed arm or unchanged 0% headline is a valid final outcome when the method is frozen, the accounting is complete, and the lesson generalizes.

## 7. Submission-ready definition

The paper is ready for TMLR submission only when:

- every Section 3.1 item has a linked immutable artifact;
- the abstract contains no claim outside Section 2;
- all headline tables rebuild from retained evidence;
- limitations distinguish project-internal, project-operated external, and independently operated evidence;
- the anonymous manuscript and supplementary package pass a fresh identity audit;
- the selected venue's current author, AI-use, ethics, originality, and dual-submission policies have been rechecked on the day of submission; and
- a human author performs and records the final claim, citation, and artifact verification.

Until then, the correct status is **working paper, not submission-ready**.
