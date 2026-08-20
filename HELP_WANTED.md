# Urusilla Help Wanted

This project needs independent humans, agents, and human-agent teams who are willing to test claims rather than amplify them.

The currently demonstrated token saving for general communication between unfamiliar agents is **0%**. In a frozen 2,542-turn lane spanning Taskmaster, Schema-Guided Dialogue, Dolly, and OpenAssistant, H1 exact no-regret passes, H2 general compact value and H3 repeated-context value fail, and H4 end-to-end utility is not evaluated. Warm carrier saving is only **0.65% to 0.80%**; cold and post-decode API-input savings are **0%**. The minimal external-profile carrier adds **165.60% to 183.98%** tokens. A separate retained lane records **0/168 compact wins under both bound and standalone contracts**, with **2.24% to 3.00% standalone cold overhead**. Total tokens per safely completed task remain unknown, and there is no state-of-the-art claim.

Contributions are most valuable when they can prove the project wrong, identify a boundary, or reproduce a result without using a project implementation as the oracle. Four missing capabilities are especially urgent: a broad independently authored conversation corpus, model-native consumption, end-to-end task utility measurement, and an independently operated implementation.

The intended general-use system is a layered router: verified silence or topology pruning; compiled routines or exact deltas for frequent structure; public action-state records; learned task-aware representations; and raw concise natural-language fallback for rare or novel content. Contributors should test the routing decision, not assume every turn should use a compact syntax.

The broad result triggers a stop rule. Please do not submit incremental codebook or threshold tuning for one universal lossless text surface unless the proposal changes the architecture and freezes its hypothesis before evaluation. The highest-value next contributions are oracle-free public action-state production, model-native or task-aware consumption, message suppression or topology selection, end-to-end total-token utility, and independent implementation.

For orientation, narrower v0.7 profiles save 23,997 development and 4,302 grouped-holdout tokens but save 0 OOD and activate in 0/12 cold plans. Synthetic v0.9 state deltas save 53.71% to 55.15%. A historical pre-cutover receiver result reaches 27/28 but fails its gate, while the current neutral-ID sender result passes 6/10. Contributions should close these boundaries rather than quote the favorable numbers alone.

## Priority work packages

### 1. Independent implementations

Build a decoder and encoder without copying control flow from the Python reference implementation.

Acceptance evidence:

- exact byte equality on every published positive vector;
- semantic equality and deterministic re-encoding;
- exact rejection classes for the published negative vectors;
- bounded memory, nesting, collection, and input-size behavior;
- a public immutable revision and a reproducible environment manifest.

Useful targets include TypeScript or JavaScript, Rust, Go, Java, and a second Python implementation written from the specification alone.

The repository already contains a separately written Node.js lane, but it uses same-project, Python-oracle-derived fixtures. It is cross-runtime compatibility evidence, not the external independent reproduction requested here. A qualifying implementation should be independently operated, disclose any shared vectors, and add oracle-independent or independently derived checks where the English specification permits them.

### 2. End-to-end public-task evaluation

Run natural language, controlled terse English, structured JSON, strong schema-aware codecs, and the adaptive project surface on the same agent tasks.

Acceptance evidence:

- frozen public items and prompts before provider calls;
- the same model pairs, tools, context, retry policy, and stopping rule for every arm;
- task-success non-inferiority with a stated confidence bound;
- complete input, output, repair, discovery, profile, and fallback token ledgers;
- total tokens per resolved and per safely completed task, not message-surface tokens alone;
- latency and cost accounting that includes failures and refusals;
- publication of unfavorable and null results.

Synthetic scripted-agent dry runs are useful for validating the harness, but they are not task-performance evidence.

The shared driver should include full-history natural language, concise language, JSON/schema, message suppression or topology pruning, a clean-room PACT-style action-state history, AutoForm-style format selection, Agora-style negotiated routines where repetition permits them, and the best enabled fallback. Historical paper percentages are not substitutes for running these arms on the same tasks and models.

### 3. Fresh external traffic

Seal a new corpus before importing or measuring a project codec. Prefer authorized, independently authored machine-readable records from standards, public APIs, or consenting deployments.

Acceptance evidence:

- immutable source revisions, licenses, source digests, and deterministic transforms;
- a premeasurement manifest that binds hypotheses, metrics, candidate source digests, and tokenizer identities;
- cold and warm accounting with transparent fallback;
- exact reconstruction, corruption rejection, reset, loss, duplication, and out-of-order tests;
- no tuning on the confirmatory corpus.

### 4. Independent broad conversation corpus

Build and seal a legally redistributable corpus that independently extends the current four-family convenience sample and reflects ordinary agent communication rather than only schema-shaped records. It should include clarification, correction, disagreement, planning, delegation, negotiation, uncertainty, citations, tool results, partial failure, recovery, and mixed natural-language/structured turns across unrelated domains.

Acceptance evidence:

- independently authored or independently sampled sessions with consent, licensing, and privacy review;
- train, development, and sequestered confirmatory partitions fixed before project-specific optimization;
- diverse session lengths, partner familiarity, task domains, languages, models, and tool-use patterns;
- explicit semantic-preservation annotations and an adjudication process for ambiguous turns;
- raw concise-language, JSON, schema-aware, compressed, and project representations evaluated under identical boundaries;
- publication of null and unfavorable strata, not only an aggregate score;
- a public action-state history stratum that can test compact state without collecting private chain-of-thought.

Synthetic augmentation may support stress testing, but it cannot be the only source of claim evidence.

Annotate two different targets where applicable. Lossless examples must support canonical typed-message recovery and deterministic re-encoding. Task-equivalent examples may replace full prose with a public action-state record, but must be scored on task success, semantic fidelity, safety, and repair rather than exact wording. Do not label a PACT-style projection as a lossless codec.

### 5. Model-native consumption

Test whether models can consume validated Urusilla representations directly, without expanding them back into longer prose before inference.

Acceptance evidence:

- at least two unrelated model families and both familiar and unseen task domains;
- identical semantic inputs, tool access, output requirements, retry limits, and safety gates across arms;
- parse validity, semantic fidelity, task success, repair rate, input/output/reasoning tokens, latency, and cost;
- explicit separation of native consumption from bridge-mode decoding into prose or JSON;
- a predeclared fallback rule and publication of every fallback and refusal.

Do not infer model understanding from codec round trips. A decoder succeeding before the model call is transport evidence, not model-native evidence.

### 6. Security and parser review

Review the public decoders and adapters for resource exhaustion, ambiguity, canonicalization gaps, provenance confusion, replay, downgrade, and identity-binding failures.

Acceptance evidence:

- a minimal non-sensitive reproducer;
- an observable violated invariant;
- a regression test through a public entry point;
- compatibility and resource-impact analysis;
- coordinated disclosure under [`SECURITY.md`](SECURITY.md).

Do not submit secrets, private prompts, real credentials, or attack traffic against systems you do not own or have permission to test.

### 7. Interoperability bridges

Implement opt-in bridges for current agent protocols while preserving each protocol's activation, authentication, task, role, and sender-binding rules.

Acceptance evidence:

- an explicit bridge, native, and fallback distinction;
- complete cold discovery and envelope accounting;
- cross-runtime canaries with unknown-extension downgrade tests;
- no claim of official registration or conformance without the relevant authority's evidence.

### 8. Human auditability

Test whether independent reviewers can reconstruct normative fields and detect material errors faster or more accurately than with JSON or controlled terse English.

Acceptance evidence:

- blinded randomized materials;
- reconstruction accuracy, error-detection accuracy, time, and inter-rater agreement;
- a preregistered analysis plan and an accessible anonymized result set;
- no collection of private chain-of-thought.

### 9. Energy measurement

Measure complete energy per safely completed task rather than estimating energy from token counts alone.

Acceptance evidence:

- hardware, software, sampling method, idle baseline, and uncertainty;
- sender, receiver, conversion, repair, networking, and cache costs;
- task-success denominator and cold-versus-warm separation;
- raw measurements sufficient for independent reanalysis.

## Agent-assisted contribution disclosure

Automated agents may propose code, tests, corpora, reviews, or documentation. Every submission must disclose:

- which agent or model materially generated or reviewed the work;
- the human or organization accountable for the submission, if any;
- the exact tools and immutable source revisions needed to reproduce it;
- whether external services, paid calls, or private data were used;
- which claims were independently checked rather than copied from project reports.

An agent-generated result is not automatically independent merely because it was produced in another process. Independence requires separate implementation or evidence, not a different chat window.

## How results are recognized

Accepted evidence is credited in the relevant report, release notes, and contributor registry. Negative results receive the same attribution as favorable results. A contribution does not become an adoption record unless an independently operated agent uses the protocol and passes the adoption gates in [`ADOPTERS.md`](ADOPTERS.md).

No token, cryptocurrency, payment, governance right, or future reward is promised. See [`CONTRIBUTOR_REWARDS.md`](CONTRIBUTOR_REWARDS.md).

## Public invitation

> Help test Urusilla, a machine-first interlingua for AI agents. Its broad lossless lane currently fails the compact-value gates, while narrower structured and synthetic lanes expose testable opportunities. We are looking for oracle-free public action-state systems, model-native/task-aware evaluation, verified silence or topology pruning, external independent implementations, end-to-end task ledgers, parser reviews, and energy measurements. Negative results are first-class contributions. Preserve provenance and publish enough evidence for someone else to disagree with you; no state-of-the-art claim is made.
