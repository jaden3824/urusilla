# Urusilla Performance-First Research Program

Status: preregistration draft 0.1  
Date: 2026-08-20

## Decision rule

The project is not complete when it has a novel grammar, a working demo, GitHub traffic, or a viral screenshot. It is complete enough for a production proposal only when independent agents achieve better safety-adjusted task economics than the strongest available baseline.

The primary endpoint is:

```text
total_cost_per_safely_completed_task =
  (wire + schema_amortization + inference + compute + latency + repair + audit)
  / safely_completed_tasks
```

No single weighted score will hide trade-offs. Reports must also publish the Pareto frontier for task success, wire bytes, model tokens, latency, energy or compute proxy, repair turns, audit time, and safety failures.

## Long-term replacement target

The research target is progressively broader than an external message codec:

1. replace the external utterance layer between cooperating agents;
2. replace tool, retrieval, document, and web-service meaning payloads with typed facts, evidence, deltas, and content-addressed references;
3. train compatible models to use the same IR for selected planning, working-memory, and action-state interfaces;
4. permit optional latent or cache sidecars only between explicitly compatible models inside an approved trust boundary; and
5. establish an Internet-scale semantic control plane above existing transports.

This does not propose replacing HTTP, TLS, storage codecs, or raw image, audio, video, and code assets. Urusilla carries their meaning, provenance, relationships, constraints, and immutable references while modality-specific codecs carry bulk data. It also does not require disclosure of private chain-of-thought. Internal adoption begins with observable plan and action state and advances only when privacy, task utility, and energy gates pass.

## Token-first adaptive communication

For a model-facing channel, the primary efficiency quantity is total receiver and sender tokens per safely completed task, including one-time Capsule/codebook transfer and repair turns. The runtime minimizes this value in the following order:

1. **Tier 0 — verified silence/topology pruning:** suppress a message or edge only when an observable policy proves its marginal task value is unnecessary;
2. **Tier 1 — compiled routine or exact delta:** use verified shared routines, content hashes, checkpoints, state deltas, or batches for frequent structured exchange;
3. **Tier 2 — public action-state record:** retain task-relevant action, state, result, provenance, uncertainty, and safety fields without replaying full prose;
4. **Tier 3 — learned task-aware representation:** select a held-out-validated task/model profile only when the deployment and end-to-end evidence gates permit it; and
5. **Tier 4 — raw concise natural language:** preserve rare, novel, ambiguous, or unsupported content through a complete fallback.

The tier number is a routing order, not a trust ranking. Agora motivates Tier 1 routine amortization, PACT motivates the Tier 2 public-state comparator, and OPTiMACS motivates Tier 3 task-aware representation learning. A deployable router must also compare Tier 0 against AgentDropout- or AgentPrune-style message suppression when the communication graph can vary.

An unrepresentable fragment does not force the whole message back to another language. It becomes a typed splice carrying its semantic role, codec and version, schema/profile digest, payload digest, declared loss mode, fallback chain, and effect eligibility. A peer that cannot validate the splice requests only that fragment in its next supported codec. Unknown or unverified fragments are non-executable.

Token minimization is constrained by exact meaning, security, and task-success gates. A shorter representation that increases ambiguity, repair, or unauthorized effects is a regression. Bytes, latency, memory, and energy remain separately reported because tokenizer savings do not imply proportional system savings.

Two equivalence contracts are preregistered separately. **Lossless exact equivalence** requires canonical typed-message recovery and deterministic re-encoding. **Task-level semantic equivalence** permits an action-state or learned projection to omit original prose or reasoning history, but then forbids an exact-reconstruction claim and requires non-inferior end-to-end task success, semantic fidelity, safety, repair, and total-cost evidence. PACT-style compression belongs to the task-level contract. No task-level result may be reported as a codec round trip.

## Continuous grammar evolution

The semantic kernel is immutable within a version, while content-addressed Grammar Capsule deltas may evolve continuously:

1. agents detect repeated costly fragments and propose a typed definition, symbol, migration map, translation, and test vectors;
2. a session may trial the proposal under an ephemeral content hash;
3. candidates must pass held-out tasks, new-partner cross-play, semantic round-trip, safety, token, and rollback gates across a diverse model population;
4. candidates that pass the evidence gates may enter a signed extension profile only after the approval required by `GOVERNANCE.md`, rather than silently changing an existing symbol;
5. widely interoperable extensions may be ratified into a later core profile only through the same explicit governance authority; and
6. deprecated definitions remain resolvable by immutable hash for historical interpretation while unused session aliases are garbage-collected.

Silent semantic drift is forbidden. Every meaning change creates a new hash and version, and peers negotiate the highest mutually verified profile. A failed upgrade falls back by fragment or profile without rewriting unrelated content.

## Research questions

1. Does typed UrusillaIR preserve constraints, negation, quantities, uncertainty, evidence, and commitments more faithfully than terse natural language and ordinary structured payloads?
2. After Capsule and schema costs are amortized, which codec minimizes actual end-to-end cost for each model, task, binding, and conversation frequency?
3. Can a previously untrained agent acquire the language from a bounded Grammar Capsule and work with an unseen partner?
4. Does the protocol transfer across model families, tokenizers, versions, vendors, and runtime architectures without a private pairwise code?
5. Does observable commitment semantics reduce unsafe action, disagreement, and dispute-resolution cost?
6. Can personal AI products keep raw machine communication private by default while providing faithful local translation and explicit inspection?

## Mandatory baselines

- terse English and task-appropriate human language;
- schema-constrained minified JSON;
- gzip or equivalent transport compression applied fairly to every eligible profile;
- deterministic CBOR;
- schema-equivalent Protobuf or FlatBuffers;
- A2A structured `data` Parts and raw-byte Parts under each tested binding;
- SILP JSON and code frontends where implementable from the public draft;
- an AICL comparison for cooperative-work tasks;
- model-selected formats such as the AutoForm or OPTiMACS approach where reproducible;
- a clean-room PACT-style public action-state history against the full-history control;
- Agora-style negotiated routines when interactions repeat; and
- AgentDropout- or AgentPrune-style no-message/reduced-topology baselines where communication may be unnecessary.

Terse English is mandatory because the Tokenese post-mortem shows that a designed symbolic text can tokenize worse than concise prose.

## Initial task domains

### 1. Software-engineering delegation

Planner, implementer, reviewer, and test-verifier agents exchange goals, repository references, hard constraints, evidence, patches, failures, and acceptance commitments. Executable tests provide observable outcomes.

### 2. Research verification

Retriever, claim extractor, skeptic, and verifier agents exchange claims, source digests, uncertainty, contradictory evidence, and resolution criteria. Hidden evidence sets test provenance retention and calibration.

### 3. Low-risk personal-AI coordination

Calendar, travel-search, and notification agents operate in a sandbox with synthetic user data. Tasks test consent, budgets, time zones, cancellation, and clarification without making purchases or contacting real people.

Commerce, medical, legal, financial, physical, and other consequential domains remain out of scope until signed manifests, authorization profiles, and independent security review exist.

## Experimental design

- Use a randomized paired crossover: every model/task seed runs each communication profile with equivalent information and tools.
- Freeze task data, tool behavior, scoring, and safety policy before evaluating a new codec.
- Separate development, public validation, and hidden test sets.
- Hold out partner identity, task compositions, schemas, model versions, and at least one model family.
- Periodically replace receiver agents during training to penalize private co-adaptation.
- Report repeated trials, confidence intervals, effect sizes, failures, and excluded runs.
- Intervene on messages by deleting, shuffling, and counterfactually substituting them to verify that receiver behavior causally depends on communication.
- Run evaluator-blind semantic comparisons and executable world-state checks; do not rely only on an LLM judge.

## Non-compensable release gates

The following gates cannot be offset by a better aggregate score:

| Gate | Experimental threshold |
|---|---:|
| Core encode/decode semantic exactness | 100% |
| Canonical re-encode equality | 100% |
| Unauthorized external effects in the test suite | 0 |
| Unknown required schema/profile execution | 0 |
| Negative conformance rejection | at least 99.9% with no side effect |
| Held-out semantic graph exactness | at least 95% |
| Unseen-partner parse validity | at least 99% |
| Task-success non-inferiority | lower confidence bound no more than 1 percentage point below the best baseline |
| Human diagnostic reconstruction of normative fields | 100% |
| Provenance and uncertainty retention | 100% on required fields |

An efficiency claim additionally requires at least a 20% reduction in total cost per safely completed task, or a statistically supported movement to a better Pareto frontier that users can choose explicitly. These are experimental thresholds, not current results.

## Performance measurements

- actual payload and full-envelope bytes under HTTP+JSON, gRPC, and at least one secure messaging layer;
- cold Capsule/schema bytes, warm-session bytes, and exact break-even message count;
- tokenizer-specific input and output tokens for every tested model;
- encode/decode p50, p95, and p99 latency;
- end-to-end p50, p95, and p99 task latency;
- CPU/GPU time, peak memory, KV-cache footprint, and an energy proxy;
- dollar cost under a pinned price snapshot;
- task success, semantic exactness, constraint omission, contradiction, repair turns, and timeout rate;
- translator fidelity and human audit time;
- replay, downgrade, injection, corrupted-frame, compromised-agent, collusion, and data-reconstruction tests.

## Codec selection policy

The runtime estimates expected utility after a canary exchange. It activates a profile only when that profile passes semantic and safety gates and exceeds the incumbent by a configured switching margin. It may choose structured JSON, canonical binary, compressed binary, a warm dictionary, or a compatible latent sidecar. There is no requirement that the project's own binary codec win every context.

For an A2A HTTP+JSON binding, Base64 and extension metadata overhead must be included. For gRPC, raw bytes must be measured directly. A payload-only result cannot be advertised as an end-to-end network result.

## Blind teachability evaluation

A fresh agent receives only the signed Capsule and task instructions. It must:

1. verify Capsule identity;
2. classify acts and construct valid typed IR;
3. reject unknown, ambiguous, unauthorized, and malformed requests;
4. interpret held-out compositions from an unseen partner;
5. produce a deterministic human inspection view;
6. report its learning tokens, wall time, model/runtime identity, and uncertainty.

The evaluator scores exact structures and world-state effects without revealing expected outputs. Agents involved in designing the Capsule are excluded from the blind test.

## Security and misuse research

- Measure secret-bit capacity in syntax choices, timing, omission, and semantically equivalent alternatives.
- Test whether paraphrasing, canonicalization, and policy mediation reduce collusion without destroying task performance.
- Treat hidden-state and KV transfer as a separate high-risk profile because private prompts and internal reasoning may be reconstructable.
- Test a compromised sender, receiver, translator, Capsule registry, and schema resolver independently.
- Keep consumer telemetry off by default and ensure inspection works entirely locally.

## Pivot and stop conditions

- The frozen 2,542-turn broad lane has already triggered a stop for incremental tuning of one universal lossless compact text surface: H2 general compact value and H3 repeated-context value failed across the declared gates. Keep raw fallback as the default and reopen this lane only for a separately frozen architecture-changing hypothesis, not another corpus-specific codebook adjustment.
- If a textual surface loses to terse language after fair optimization, remove it from the preferred profile set.
- If canonical binary loses after full envelope, compression, and CPU cost, retain it only for hashing, signing, storage, or contexts where exact identity has independent value.
- If native model training harms general capability or partner transfer, ship bridge mode only.
- If observable commitments do not improve outcomes, reduce the semantic kernel rather than preserving complexity for branding.
- If no profile beats strong baselines in safely completed task economics, publish the negative result and stop claiming a new language is warranted.

## Current evidence boundary

The frozen four-family broad lane contains 2,542 turns. H1 exact no-regret passes, H2 general compact value and H3 repeated-context value fail, and H4 end-to-end task utility is not evaluated. Warm receiver-carrier saving is 0.65% to 0.80%; all cold family plans retain raw, post-decode API-input saving is 0%, and the minimal external-profile carrier adds 165.60% to 183.98% tokens. Its chronology is a project-internal freeze rather than external preregistration, and evaluator authors could access the corpus.

Narrower evidence remains scoped. Guarded v0.7 saves 23,997 development and 4,302 grouped-holdout tokens, but saves 0 OOD and activates in 0/12 cold plans. Transparent v0.8 records 0/172 compact wins under both bound and standalone development contracts; standalone overhead is 5.85% to 6.80%. On the retained official-example corpus, both contracts record 0/168 compact wins and standalone cold overhead is 2.24% to 3.00%. Checkpointed v0.9 saves 53.71% to 55.15% only on deliberately correlated synthetic state. A historical pre-cutover receiver pilot reaches 27/28 but fails its gate; one historical pre-cutover internally operated neutral-ID sender pilot recorded 6/10 structural-and-semantic passes and has not been rerun on current artifacts. A 399-prompt SGD gold-state oracle reduces prompt tokens by 7.48% to 23.34% but makes no model call and measures no accuracy.

The next research priority is therefore an oracle-free, end-to-end router study centered on verified silence or topology pruning and model-native or task-aware public action-state records, with negotiated routines and raw natural-language fallback. A separately written Node.js lane adds same-project cross-runtime compatibility against Python-oracle-derived fixtures, not external independent reproduction. None of the current evidence proves natural-language compilation quality, native model comprehension, unseen-model transfer, end-to-end task improvement, full A2A network savings, measured energy reduction, external adoption, or state-of-the-art performance.

Until that study produces claim-eligible safely-completed-task evidence, the
protocol surface is frozen. New infrastructure work must either unblock one
frozen end-to-end episode, reproduce a concrete failure, or reduce the cost of
independent evaluation; additional syntax, adapters, dashboards, and outreach
do not substitute for task utility.
