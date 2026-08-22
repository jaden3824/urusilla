# Urusilla: A Layered Machine-First Interlingua with Deterministic Serialization and Adaptive Fallback

Status: working paper draft; not submission-ready  
Evidence cut-off: 2026-08-20  
System name: Urusilla

## Abstract

AI agents usually communicate through natural language or general-purpose structured data even when both endpoints are machines. This work studies Urusilla, a layered machine-first interlingua that separates typed intent, canonical semantics, transport encoding, negotiated surfaces, provenance, and readable fallback. The primary result is negative: demonstrated token saving for general communication between unfamiliar agents is **0%**. A frozen 2,542-turn convenience sample from Taskmaster, Schema-Guided Dialogue, Dolly, and OpenAssistant passes its exact no-regret fallback hypothesis but fails its general compact-value and repeated-context hypotheses. Warm receiver-carrier saving is only 0.65% to 0.80%; cold and post-decode API-input savings are 0%, and end-to-end task utility is not evaluated. A minimal external-profile carrier adds 165.60% to 183.98% tokens. On a separate retained 42-record official-example corpus, bound and standalone compact modes each win 0/168 comparisons, while standalone cold text is 2.24% to 3.00% larger than raw concise text. Narrower results remain informative but do not repair this boundary: receiver-bound v0.7 saves 23,997 development and 4,302 grouped-holdout tokens, yet saves 0 OOD and activates in 0/12 cold plans; checkpointed v0.9 saves 53.71% to 55.15% only on deliberately correlated synthetic state. A historical pre-cutover receiver pilot reaches 27/28 exact reconstructions but fails its gate, while one historical pre-cutover internally operated neutral-ID sender pilot recorded 6/10 structural-and-semantic passes and has not been rerun on current artifacts. Total tokens per safely completed real-model task remain unknown. These results motivate a layered router that prioritizes verified silence, model-native or task-aware public action state, negotiated routines, and raw fallback rather than one universal lossless syntax. No state-of-the-art, energy, adoption, or end-to-end superiority claim is made.

## 1. Introduction

Multi-agent systems increasingly pass plans, evidence, requests, tool results, commitments, and failures between language models. Natural language is flexible and model-compatible, but it repeats syntax and context that machine endpoints may not need. General-purpose JSON improves structure but can remain verbose. Opaque learned or latent channels can reduce generation latency, yet they may be model-specific, difficult to audit, expensive over a network boundary, or unsafe to expose across trust domains.

This paper investigates a middle path: a stable, typed semantic kernel with negotiated external encodings. The kernel is intended to remain auditable and versioned. Compact symbolic, binary, or learned surfaces are codecs over that kernel, not independent sources of meaning. An endpoint may select a fast representation only after exactness, provenance, authorization, privacy, and compatibility gates pass. Unknown or novel content falls back to a readable representation.

The current evidence is deliberately bounded. It shows exact serialization, strong in-family compression, explicit out-of-domain failures, transparent fallback, a failed frozen broad-dialogue compact-value test, checkpointed state-delta behavior on synthetic correlated sessions, A2A bridge accounting, same-project Python/Node cross-runtime agreement, and failed small receiver and sender gates. It does not show autonomous task success, reliable sender generation, external independent reproduction, cross-vendor transfer, measured human audit utility, measured energy reduction, public adoption, or state-of-the-art performance.

### 1.1 Research questions

- **RQ1 — Semantic efficiency:** Can agents convey the same typed meaning with fewer total receiver tokens and wire bytes than compact terse English and strong structured codecs?
- **RQ2 — Generalization:** Do savings persist for unseen combinations, schemas, values, tokenizers, and model families after all cold profile costs are counted?
- **RQ3 — Task utility:** Does the interlingua reduce total tokens per safely completed public task without a task-success regression greater than one percentage point?
- **RQ4 — Interoperability:** Can independently implemented agents negotiate versions and codecs, preserve provenance, and fall back safely across heterogeneous models?
- **RQ5 — System cost:** After translation, validation, repair, latency, memory, networking, and training are counted, does the approach reduce energy or monetary cost per safely completed task?
- **RQ6 — Human auditability:** Can blinded auditors reconstruct normative fields and detect material errors faster or more accurately than with JSON or controlled terse English?

### 1.2 Intended contributions

Subject to the pending experiments, the paper aims to contribute:

1. a layered agent communication architecture separating semantic acts, typed content, protocol state, provenance, transport, and codecs;
2. canonical, fail-closed reference encodings with deterministic round trips and bounded decoders;
3. a receiver-specific adaptive selector that counts complete warm and cold costs and preserves a readable fallback;
4. an evaluation protocol that separates serialization, comprehension, task success, topology, network transport, and latent-state transfer;
5. negative evidence showing when specialization fails out of domain and when a prompted receiver remains unreliable; and
6. a reproducibility and claim-gating policy that prevents serialization-only results from being presented as end-to-end superiority.

## 2. Scope and terminology

The proposed interlingua is an external communication protocol. It is not a requirement that models expose private chain-of-thought. Internal reasoning may remain natural language, latent state, program state, or another private representation. Only externally exchanged claims, requests, commitments, evidence, results, failures, and provenance enter the auditable kernel.

An **act** is a typed communicative function. A **semantic message** is a validated act plus canonical typed content and protocol metadata. A **surface** is a textual or binary serialization of that message. A **profile** is immutable negotiated state such as a schema dictionary or codebook. A **fallback** is a representation that remains valid when a specialized profile is absent or uneconomical. A **safely completed task** is a correct task result with required authorization, integrity, provenance, and validation conditions satisfied.

## 3. Related work

### 3.1 Agent communication languages

Speech-act theory motivates treating communication as action rather than untyped text. KQML introduced layered performatives, content-language identifiers, ontologies, and facilitator patterns. FIPA ACL standardized communicative acts, message envelopes, and interaction protocols. These systems provide important structure, but mental-state semantics can be difficult to verify externally. This work therefore emphasizes observable commitments, evidence, protocol transitions, and executable validation.

Primary sources:

- KQML draft and architecture: <https://research.cs.umbc.edu/kqml/kqmlspec/spec.html>
- FIPA ACL message structure: <https://www.fipa.org/specs/fipa00061/SC00061G.html>
- FIPA communicative acts: <https://www.fipa.org/specs/fipa00037/SC00037J.html>
- Verifiable and social semantics: <https://www.cs.ox.ac.uk/people/michael.wooldridge/pubs/icmas98.pdf> and <https://www.csc2.ncsu.edu/faculty/mpsingh/papers/mas/socacl-fipa.pdf>

### 3.2 Learned and induced symbolic communication

AutoForm lets language models induce task-specific non-natural formats and reports up to 72.7% fewer generated communication tokens on one evaluated pairing. OPTiMACS, published in Findings of ACL 2026, learns task-aware message representations rather than assuming one fixed surface. Agora assigns reusable routines to frequent interactions and retains natural language for rare interactions. The PACT preprint reports a 38.7% average reduction in its controlled multi-agent settings, including 50.4% fewer SWE-agent input tokens, approximately 47% fewer tokens per resolved SWE-agent task, and 10.3% fewer OpenHands tokens per resolved task. EcoLANG evolves compact expression rules for social simulation. These results use different tasks, models, success denominators, and token boundaries; none is directly rankable against the present serialization measurements. Emergent-communication work demonstrates that task reward alone can produce opaque, non-compositional, or inefficient codes, motivating explicit complexity, transfer, and interpretability pressures.

Primary sources:

- AutoForm: <https://aclanthology.org/2024.findings-emnlp.623/>
- OPTiMACS: <https://aclanthology.org/2026.findings-acl.1441/>
- Agora: <https://arxiv.org/abs/2410.11905>
- PACT: <https://arxiv.org/abs/2606.05304>
- EcoLANG: <https://aclanthology.org/2025.findings-emnlp.284/>
- DIAL/RIAL: <https://papers.nips.cc/paper/6042-learning-to-communicate-with-deep-multi-agent-reinforcement-learning>
- Language drift: <https://aclanthology.org/2020.acl-main.685/>
- Length pressure and efficient codes: <https://proceedings.neurips.cc/paper/2019/file/31ca0ca71184bbdb3de7b20a51e88e90-Paper.pdf>

### 3.3 Communication topology

AgentPrune reduces communication by pruning spatial-temporal message edges. AgentDropout reports 21.6% fewer prompt tokens and 18.4% fewer completion tokens through topology pruning in its evaluated settings. Topology and representation are complementary but distinct: avoiding a message is not the same intervention as encoding the message more compactly. Results from these layers must not be merged into one headline comparison, and the paper figures are not directly comparable Urusilla results.

- AgentPrune: <https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html>
- AgentDropout: <https://arxiv.org/abs/2503.18891>

### 3.4 Latent and model-native channels

Latent-state, hidden-state, and cache-transfer methods can avoid autoregressive text generation. Their strengths are most plausible for compatible co-located models. A high-dimensional vector or KV cache can be larger than text over a network boundary, and private state may leak through the channel. The present system treats latent transfer as an optional negotiated codec sidecar, never as the sole semantic record.

- CIPHER: <https://proceedings.iclr.cc/paper_files/paper/2024/hash/e444859b2a22df6b56af9381ad1e9480-Abstract-Conference.html>
- State Delta Encoding: <https://aclanthology.org/2025.emnlp-main.518/>

## 4. System design

### 4.1 Layered architecture

The architecture has five separable layers:

1. **Control and provenance:** version, sender, recipients, message and conversation identifiers, reply linkage, expiry, schema identity, source identity, and integrity metadata.
2. **Communicative act:** one of `ASSERT`, `QUERY`, `REQUEST`, `PROPOSE`, `COMMIT`, `RESOLVE`, or `RETRACT` in the current core.
3. **Typed semantic content:** facts, claims, goals, constraints, plans, tool calls, results, uncertainty, evidence, assets, and namespaced non-executing extensions.
4. **Conversation protocol:** causal references, commitments, cancellation, resolution, replay handling, and externally checked effect eligibility.
5. **Encoding and transport:** canonical readable text, compact symbolic surfaces, binary profiles, A2A envelopes, and optional negotiated sidecars.

These layers may evolve at different rates. A new codec cannot silently redefine an act or typed node. Core semantic changes require versioning, migration evidence, and explicit maintainer approval under the governance policy.

### 4.2 Canonical semantics and fail-closed validation

Messages use an exact top-level vocabulary and recursively typed values. Canonicalization rejects unknown shadow fields, non-canonical container types, duplicate members, invalid act-body combinations, malformed commitments, and unregistered executable extensions. Effectful acts require conversation-state and external authorization checks; parsing alone never grants authority.

Every compact decoder enforces input and expansion limits, validates integrity before semantic use, and re-encodes canonically. Checksums detect accidental corruption but do not authenticate a sender. Transport authentication, signatures, replay protection, and policy remain separate requirements.

### 4.3 Negotiated profiles and fallback

Schema dictionaries and tokenizer-aware codebooks are immutable, content-addressed profiles. Endpoints advertise support, pin an agreed profile for a session, preserve unknown-field behavior, and fall back when the peer cannot decode a candidate. Cold profile transfer is charged once and amortized only when the session actually benefits.

For general communication, the runtime is a five-tier router rather than one universal syntax. Tier 0 verifies that a message or communication edge can be suppressed. Tier 1 uses a compiled routine or exact state delta for frequent structured exchanges, following Agora's amortization principle. Tier 2 projects a public action-state record instead of replaying full dialogue history, as in the PACT comparison lane. Tier 3 selects a held-out-validated learned task-aware representation, motivated by OPTiMACS. Tier 4 carries raw concise natural language for rare, novel, ambiguous, or unsupported content. The first safe eligible tier wins, and every tier has an explicit fallback.

The evaluation distinguishes **lossless exact equivalence** from **task-level semantic equivalence**. Binary, text-surface, and exact-delta claims require recovery of the canonical typed message plus deterministic re-encoding. Action-state or learned projections may intentionally omit original wording and private reasoning; they cannot claim exact prose reconstruction. Their eligibility depends instead on preregistered end-to-end task success, semantic fidelity, safety, repair, and total-token gates. PACT-style compression is evaluated only under this second contract.

### 4.4 Adaptive representation selection

For a receiver tokenizer `r`, message `m`, and eligible representation set `E`, the warm selector chooses:

```text
argmin_{e in E} (receiver_tokens(e, m, r), fixed_tie_rank(e), encoded_text(e, m))
```

The proposed deployment eligibility gate is determined before optimization by exact semantic recovery, profile compatibility, authorization, provenance, privacy, and integrity checks. The current measured selector exercises codec validity and profile availability, not the full deployment policy. The cold planner compares complete session plans with and without profile activation. A specialized profile is not activated when its transfer cost cannot be recovered for the expected session.

## 5. Current evaluation

### 5.1 Corpora

The principal synthetic corpus contains 280 messages covering all seven acts. A grouped split keeps complete act-schema-body-semantic groups together: 224 development messages in 59 groups and 56 held-out messages in 16 groups. A separate ten-message out-of-domain set introduces new schemas, agents, predicates, values, and map shapes. The codebook is trained only on the development partition.

This split reduces direct message leakage but is not an independent external test. The generator, split, and out-of-domain messages were authored by the project.

The broad lossless lane is a separate 256-record, 2,542-turn frozen convenience sample drawn from Taskmaster, Schema-Guided Dialogue, Dolly, and OpenAssistant. Raw mixed-license records remain outside the public repository; public artifacts retain acquisition metadata, digests, aggregate measurements, and no source utterances. The source chronology was frozen inside this project, not externally preregistered or independently witnessed, and the evaluator authors could access the corpus during implementation.

### 5.2 Baselines

Serialization baselines include sorted minified JSON, per-message gzip JSON, deterministic CBOR, MessagePack, a typed recursive Protobuf schema, controlled terse English, and earlier project surfaces. Complete A2A HTTP and JSON-RPC request envelopes are measured separately from payload-only results.

### 5.3 Tokenizers

Current tokenizer accounting covers `cl100k_base`, `o200k_base`, the pinned Qwen2.5-7B-Instruct tokenizer, and the pinned Mistral-7B-Instruct-v0.3 tokenizer. Tokenizer assets and package versions are content-pinned. No current claim covers every tokenizer or future model version.

### 5.4 Byte results

On the in-domain 280-message corpus, raw v0.1 uses 176,069 bytes: 34.0% less than sorted minified JSON, 4.2% more than independent per-message gzip JSON, and 6.9% less than equally gzipped JSON when both wire forms receive the same compression. The warm schema-specialized v0.2 profile uses 54,752 bytes, 67.6% less than the direct benchmark's 168,941-byte per-message gzip JSON row and 68.9% less than raw v0.1. Sorted minified JSON uses 266,684 bytes. Its one-time profile capsule is 1,402 bytes and reaches the measured mean-size break-even against per-message gzip JSON at four messages. All compared codecs recover 280 of 280 messages exactly and deterministically under their pinned runtime profiles.

The strong-codec harness records 219,055 bytes for MessagePack, 219,899 for deterministic CBOR, and 229,790 for the typed recursive Protobuf schema. In the direct v0.2 benchmark, p50 encode/decode latency is 245.17/368.67 microseconds versus 23.83/101.42 for the unequal-work JSON path. In the matched strong-codec harness, v0.2 decode p50 is 266.83 microseconds versus 70.75 for MessagePack. This favorable byte result is in-sample and profile-specific; native implementations, persistent compression, another Protobuf schema, or novel traffic can change the ranking.

A matched whole-session follow-up confirms that qualification. With unsigned four-byte record lengths and one persistent Brotli-11 stream, bare canonical JSON uses 24,085 bytes and project v0.2 uses 25,128 bytes; the project row is 4.33% larger. The bare JSON row does not provide the independent 16-byte record checksum carried by v0.2. Adding an equivalent checksum to every JSON record raises its best compressed size to 29,297 bytes, making v0.2 14.23% smaller under that integrity contract. All 21 representation-compressor rows recover the full corpus exactly and deterministically. Byte ranking therefore depends on reset, framing, and integrity scope.

The stream paths also expose a mixed latency frontier. Brotli-11 median complete-session encode/decode times are approximately 350,805/30,178 microseconds for bare JSON, 341,935/20,437 for checked JSON, and 120,850/72,018 for project v0.2. The project path is faster to encode in this comparison but approximately 2.39 times slower to decode than bare JSON. These are unequal Python implementation paths on one machine, not native-code or network latency claims.

A separate 21-point reset sweep covers 378 representation-compressor-chunk combinations under independently cold and cached-profile contracts. All rows reconstruct exactly and deterministically. Charging the raw 1,402-byte profile capsule at every reset, the project path never beats the per-representation byte-best bare-JSON frontier and is 10.20% larger at the 280-message endpoint. On that frontier, it first beats byte-best checked JSON with an independent 16-byte checksum per record at the tested 64-message point and is 9.40% smaller at 280. The cached frontier beats the byte-best bare-JSON frontier through the tested 128-message point, then loses at 140, 256, and 280, where it is 4.33% larger than bare JSON. Fixed compressors have different crossover sets, including earlier checked-JSON wins. The non-monotonic grid is reported directly and is not interpolated into untested session lengths.

### 5.5 Token results and negative transfer

On the 56-message grouped holdout, the trained v0.3 surface is 62.0% to 63.4% smaller than minified JSON and 37.8% to 41.8% smaller than the Base64 binary profile on the two initially reported tokenizers. Its measured incremental codebook break-even against Base64 v0.2 is 101 to 113 messages. Against controlled terse English across all four pinned tokenizers, the v0.4 grouped-holdout reduction ranges from 59.64% to 69.79%.

The out-of-domain result reverses the headline: v0.3 uses 73.5% to 91.5% more tokens than JSON on its two-tokenizer study, and v0.4 uses 49.15% to 103.15% more than controlled terse English across four tokenizers. This failure motivates adaptive fallback rather than universal use of one codebook.

### 5.6 Adaptive results

Across 290 messages and four receiver tokenizers, yielding 1,160 message-receiver pairs, the adaptive selector has zero warm token regressions against the lowest-cost member of the enumerated codec-valid candidate set. Exact semantic recovery, deterministic reselection, and deterministic corruption rejection each pass 1,160 of 1,160 trials. Authorization, provenance, privacy, authentication, and replay-policy eligibility are not exercised by this benchmark. In the out-of-domain set, the selector generally chooses controlled terse English; a lossless fragment representation wins 13 pairs by a total of 62 tokens but can increase bytes by as much as 7.03%.

Adaptive selection is not free. The Python reference selector takes approximately 2.9 to 4.9 ms per message, while direct structured encoding takes approximately 0.93 ms. The selector currently optimizes receiver tokens, not energy or wire bytes.

### 5.7 Generalization-first surface revision

A train-only readable surface revision adds a second candidate without replacing the safe v0.5 paths. On the ten OOD messages it reduces warm tokens by 1.87% to 5.42% relative to the byte-identical v0.5 selector across the four receivers, while leaving development and grouped-holdout warm choices unchanged. The complete selector retains zero warm regressions across 1,160 message-receiver pairs, exact deterministic selection for 1,160/1,160 pairs, and corruption rejection for 1,740/1,740 trials.

The cold result is deliberately unfavorable: a ten-message OOD session does not amortize the new grammar and profile, so the cold planner chooses the v0.5-compatible state and records zero improvement. Fresh selection is approximately 47% to 66% slower than v0.5 in the Python implementation. The revision is therefore a warm-path candidate that can help only after its cold artifacts amortize, not evidence of universal replacement.

Although the v0.6 alias profile is constructed only from development bytes, the same ten-message OOD set had already been measured and inspected before the revision was designed. The improvement is therefore exploratory adaptation to a known failure set, not a fresh confirmatory generalization result. The fresh external test in Section 5.8 does not confirm the efficiency gain.

### 5.8 Fresh external OOD evaluation

Before importing or measuring any project codec, a content-addressed manifest froze 43 source-preserving wrapped examples from W3C ActivityStreams, CNCF CloudEvents, official MCP examples, and OASIS STIX. The unchanged candidates pass 559/559 exact round trips and deterministic re-encodings; v0.5 exact-minimum, v0.6 warm no-regression, and v0.6 cold no-regression checks also pass in full.

The predeclared serialization value signal, sealed in a local manifest before measurement, fails. Controlled Terse English is the lowest-token plain representation for every tokenizer. Warm v0.6 is 1.05% to 1.43% larger. In the 43-message cold session, the planner correctly rejects every optional artifact and returns to the v0.5 fallback plan, but the complete envelope remains 2.12% to 2.80% larger. None of the four tokenizers reaches the required 20% cold reduction. The v0.4 codebook uses raw fallback on all 43 records, with 83.9% of payload symbols and 70.6% of frame bytes on the raw path. Current adaptive selection is also orders of magnitude slower to encode than JSON in the unequal Python paths.

This is source-bound external-corpus serialization evidence, not a representative deployment sample, model-understanding test, task-utility result, or independent operator reproduction. It falsifies the present external cold-token value hypothesis while confirming exactness and safe artifact refusal.

### 5.9 Receiver-negotiated token profiles

The v0.7 experiment derives 1,024-, 2,048-, and 4,096-entry profiles for each of four pinned receiver tokenizers from the 224-message development partition before evaluating the unchanged 56-message holdout and project-authored OOD sets. Its guarded chooser retains v0.6 on ties. It saves 23,997 tokens on development and 4,302 on grouped holdout, but saves 0 OOD because every OOD choice remains v0.6. Exact direct recovery and canonical re-encoding pass for 3,480/3,480 receiver/profile/message cases.

The cold planner activates v0.7 in none of the 12 known-session plans because the text-transfer capsules do not amortize at the evaluated lengths. The guarded chooser is also slower than v0.6 in the recorded Python paths. The profile alphabet uses readable ASCII vocabulary tokens with significant leading spaces, so raw `R7` text is decoder-before-model transport only. Individual-word filtering cannot make arbitrary token sequences safe prompt content.

### 5.10 Transparent fallback and retained external remeasurement

The v0.8 bound contract moves mode, sequence, and keyed integrity metadata outside receiver-visible text when a negotiated authenticated record transport already supplies those properties. On the previously revealed 43-record external corpus, compact modes win 0/172 bound and 0/172 standalone comparisons. Bound receiver-token totals tie raw controlled terse English; without transport binding, standalone authenticated text remains 5.85% to 6.80% larger. This is not a compact-language win.

A retained two-pass remeasurement reuses 42 source-preserving project wrappers around official OpenAPI, AsyncAPI, W3C Web of Things, and OpenTelemetry examples. In each run, exactness, deterministic re-encoding, and retained mutation checks pass. Both bound and standalone compact modes win 0/168 comparisons. Every standalone cold plan selects terse for all 42 records and remains 2.24% to 3.00% above raw plain text after the integrity envelope. This is an exploratory current-artifact remeasurement of a retained corpus, not fresh confirmation, representative traffic, model understanding, task utility, independent operator reproduction, or general compression evidence.

### 5.11 Frozen broad-dialogue lossless lane and SGD oracle

The broad lane freezes 256 records and 2,542 turns across four dialogue families and four locally hash-pinned tokenizers. Candidate algorithms, selection order, and gates were fixed by an internal project chronology rather than an externally registered preregistration; evaluator authors could access the corpus. Generic DEFLATE, Brotli, Zstandard, and causal history-DEFLATE candidates share an integrity-matched text envelope, while bare UTF-8 remains the mandatory no-regret receiver-token baseline. The measurement performs no network or provider calls.

H1 passes with 0 positive-regret choices across 10,168 turn-tokenizer selections and exact recovery for every selected carrier. H2 fails because compact coverage and saving do not reach the declared per-family gates; H3 fails because causal history compression does not reach 20% on both task-oriented families; H4 is not evaluated. Aggregate warm receiver-carrier saving ranges from 0.65% to 0.80%, only 7 to 9 of 2,542 turns select compact text per tokenizer, every cold family plan retains raw, and post-decode API-input saving is 0%. The minimal external-profile carrier adds 165.60% to 183.98% tokens relative to bare text.

A separate oracle comparison replaces raw SGD history with dataset-provided gold action and cumulative state for 399 next-action prompts. Prompt tokens fall by 7.48% to 23.34%, but no model is called and no accuracy is measured. The oracle intentionally loses prose and is neither lossless nor deployable. It motivates a task-level public action-state experiment, not a codec claim.

These results trigger a stop rule: incremental tuning of one universal lossless compact text surface is paused. That lane may reopen only with a separately frozen architecture-changing hypothesis. The next priority is an end-to-end comparison of model-native or task-aware public action state, verified silence or topology pruning, negotiated routines, and raw fallback.

### 5.12 Checkpointed semantic deltas

The v0.9 experiment evaluates repeated state synchronization rather than arbitrary standalone messages. Across 24 project-authored synthetic sessions and 768 snapshots, full records and delta candidates use the same standalone session, sequence, base-state, and HMAC framing. A delta is selected only when its complete record is strictly smaller for the negotiated tokenizer, and periodic full checkpoints permit fail-closed resynchronization.

At the predeclared interval of eight, token savings against matched full records range from 53.71% to 55.15% across four tokenizers. The interval-one control saves exactly zero. Tokenizer-specific plan recovery and canonical reselection pass for 18,432/18,432 snapshots; 4,608/4,608 representative interval-eight mutations are rejected. Replay, adjacent reordering, single-record loss, and later checkpoint resynchronization behave as declared, but missing historical snapshots are not recovered. The workload is deliberately correlated, no model emits or consumes a delta, and adaptive encoding is slower than matched full encoding. This result is not comparable with published end-to-end communication reductions, compressed streams, or arbitrary traffic.

### 5.13 Prompted receiver-reconstruction gate

A historical pre-cutover 14-message pilot teaches a receiver the input grammar and asks it to reconstruct complete typed messages through strict structured output. After removing a double-serialization confound and using deterministic two-message batches, two `gpt-5-nano` JSON trials recover 13 of 14 and 14 of 14 messages, respectively. The combined result is 27 of 28 exact messages and 984 of 1,018 terminal values.

The predeclared local stopping gate required both trials to reach 14 of 14 with zero validator failures. It therefore fails, and the planned controlled-English, symbolic, and second-model cells are not run. Because output contracts and batch sizes were amended after observed failures, this sequential pilot is not confirmatory preregistered evidence.

The two final gate trials require 15 API attempts: 14 two-message batch calls and one repair. Separately, pre-amendment stages retain outcome summaries ranging from 0/14 to 11/14, covering seven completed API requests, plus two interrupted requests. The final protocol exposes recursive output shape and repeats grammar and schema context seven times per corpus pass. No provider call was rerun after the Urusilla cutover, so the 27/28 historical result cannot validate the current inputs and is not a shape-blind estimate of semantic understanding.

### 5.14 Test status

The current repository-wide test result is intentionally delegated to the commit-bound CI run for the release revision; this living draft does not freeze a mutable suite count. Individual experiment reports retain their own source-bound test and coverage measurements. The suite covers canonical round trips, malformed inputs, corruption, aggregate resource caps, conversation state, provenance, A2A envelopes, tokenizer counts, strong codecs, adaptive selection, mutation campaigns, validation matrices, boundary hardening, public-task harness behavior, and frozen-report identities. These are project-authored tests and do not substitute for external independent reproduction or a security certification.

### 5.15 Cross-codec mutation campaign

A deterministic campaign checks five representations over all 280 corpus messages, producing 1,400 exact cross-codec decodes and 1,400 insertion-order invariance checks. It then applies eight byte- or character-level mutation families to every encoded artifact, for 11,200 trials. The four integrity-protected representations reject all 8,960 mutations directed at them. Raw controlled terse English accepts 284 of 2,240 mutations as different canonical semantic messages; wrapping the same readable payload in the adaptive checksum envelope rejects all 2,240 tested mutations. This demonstrates that readability and semantic validation do not replace message integrity. The campaign is bounded mutation testing, not coverage-guided fuzzing or an authentication result.

### 5.16 Capsule-guided sender pilot

Reliable sender generation is not established. One historical pre-cutover, internally operated neutral-ID Capsule-guided pilot selected all 16 emit-or-reject decisions and all ten acts correctly, but only six of ten generated messages were recorded as passing the original structural validator and preserving the essential semantics. The participant has not been rerun on current artifacts. The standardized Teachability Score remains unset because exact target graphs, frame parsing, unseen-partner cross-play, sample efficiency, and the Capsule's full safety gates are not measured. An earlier 36/36 smoke pilot exposed substantial task cues and is retained only as open-label evidence.

### 5.17 Same-project cross-runtime compatibility

A separately written dependency-free ECMAScript implementation runs under Node.js and does not import, spawn, or embed the Python reference during its normal tests. It encodes, decodes, and re-encodes 280 Python-oracle-derived v0.2 fixtures byte-for-byte and rejects 25 frozen negative fixtures. This is useful cross-runtime compatibility evidence, but it is project-internal and shares project-authored specifications, Capsules, and oracle-derived vectors. It is not a clean-room external reproduction, external adoption, a security certification, or proof of full protocol conformance.

## 6. Planned end-to-end experiments

The claim-eligible study follows `COMPETITIVE_REPRODUCTION_PLAN.md`.

### 6.1 Public tasks

The first symbolic-format track uses pinned public-task artifacts derived from the AutoForm evaluation design. Evidence is split across two agents and held identical across representation arms. Where authoritative support annotations permit it, a forced distributed-evidence stratum is used; the completed preflight establishes this for 99 HotpotQA items only. WikiHop lacks the required annotations in the pinned artifact, and NarrativeQA has not yet been preflighted here.

A zero-provider-call A0 preflight freezes 100 HotpotQA and 100 WikiHop records and renders 5,382 prompts across four pinned tokenizers. The adaptive arm has the largest initial-prompt token total in every reported dataset-tokenizer row. This is unfavorable cold instruction overhead, not a total-task result: runtime messages, repairs, billed reasoning, final answers, and task success remain unobserved. HotpotQA supports 99/100 forced-evidence items; the pinned WikiHop artifact has no gold-support annotations and therefore contributes no forced-evidence items.

### 6.2 Representation arms

The study compares full-history and concise natural language, canonical minified JSON, verified silence or topology pruning, Agora-style negotiated routines when repetition exists, a clean-room public action-state history, a task-aware learned representation, AutoForm, and raw fallback. Every selector may use only information available before the receiver call. Lossless exact-reconstruction and task-level semantic-equivalence arms are scored and reported separately.

### 6.3 Model matrix

The target matrix contains three independently released model families, including an open-weight family, and all ordered sender-receiver pairings. Exact model revisions, prompts, decoding controls, tokenizers, repair rules, and outages must be frozen before scored calls. A model replacement starts a new matrix.

### 6.4 Primary outcomes

The primary effectiveness outcome is safely completed task success. The primary efficiency outcomes are total model tokens and total cost per safely completed task. Communication-only output tokens are secondary and retained for comparison with prior work.

All task input, system, history, visible communication, final-answer, profile, translation, repair, and billed reasoning tokens are counted. Judge tokens are reported separately and included in economic accounting.

## 7. Statistical analysis plan

- Use paired episodes: every representation sees the same task item, evidence split, sender-receiver ordering, and seed.
- Retain malformed, refused, timed-out, repaired, and fallback episodes in the denominator.
- Report the ratio of summed tokens, not the unweighted mean of per-item percentages.
- Test safe-task-success non-inferiority with a one-percentage-point margin using a one-sided 95% stratified paired-bootstrap bound with a preregistered seed and 10,000 resamples, clustering all repeats of an item together. The lower bound of `success_method - success_baseline` must exceed `-0.01`.
- Treat token reduction as a ratio of sums and publish a two-sided 95% paired-bootstrap interval. The competitive token gate passes only when the lower bound on reduction is at least 25% for each qualifying task family.
- Publish two-sided 95% paired-bootstrap intervals for cost differences as descriptive economic evidence.
- Use McNemar-style paired analysis for binary success and paired bootstrap or permutation analysis for continuous outcomes.
- Control multiplicity across primary task families and model pairings with a preregistered Holm procedure.
- Run at least three complete repeats for hosted or otherwise stochastic inference.
- Publish every preregistered arm, including negative and incomplete results. Exploratory analyses are labeled separately.

The current synthetic and live-pilot results are not powered for these tests and must not be pooled into the claim-eligible study.

## 8. Reproducibility and artifact policy

Before scored evaluation, freeze a machine-readable manifest containing repository commit, local patch digest, container or environment digest, dependency lock, dataset digests and licenses, prompts, profiles, model identifiers, tokenizer revisions, generation settings, seeds, parsers, repair rules, and statistical hypotheses. The current fully provisioned Python dependency set is version-pinned in `requirements-research.lock`; a submission artifact still needs platform or container identity and package hashes.

Release:

- reference encoders, decoders, validators, and adapters;
- prompts and exact rendered-prompt hashes;
- dataset inclusion lists and split-generation code;
- raw aggregate observations without private prompts or secrets;
- all failure codes, fallback decisions, token categories, latency samples, and cold costs;
- independent implementation vectors and a conformance suite; and
- a signed source manifest after the first immutable public commit exists.

API keys, response identifiers, private chain-of-thought, copyrighted source text not licensed for redistribution, and user data must not be committed.

## 9. Safety, security, and ethics

A compact machine language can make monitoring harder, enable covert channels, or encourage private code co-adaptation. The system therefore retains a canonical semantic record, human-readable lens, provenance reference, version negotiation, and safe fallback. Opaque latent state is not accepted as authoritative semantic evidence. Effectful messages require external identity and policy checks.

Compression objectives can also remove uncertainty, caveats, minority signals, or source context. Exact semantic equivalence is a minimum gate, not proof of epistemic adequacy. Public-task studies must evaluate provenance retention, uncertainty calibration, prompt injection, replay, unknown schemas, compromised senders, and collusion capacity.

Energy claims require measured wall-plug or device energy per safely completed task. Token reduction alone is not an energy measurement. Training, profile distribution, validation, retries, and degraded success may erase a nominal saving.

## 10. Limitations

- The strongest compression results use a synthetic corpus and profiles designed within the same project.
- The grouped holdout is generator-family transfer, not independent real-world traffic.
- The project-authored out-of-domain corpus has only ten messages; the separate external lane is a 43-example official convenience sample wrapped by this project, not representative deployed traffic.
- The four-family broad-dialogue lane is a 2,542-turn convenience sample. Its freeze chronology is project-internal rather than externally preregistered, and evaluator authors could access the corpus during implementation.
- Token counts are tokenizer-specific and do not measure task understanding.
- The historical live pilot tests one model and one representation, fails its stopping gate, and was not rerun on current Urusilla inputs.
- Reliable sender generation, autonomous dialogue, tool use, task success, cross-vendor transfer, human audit utility, and measured energy remain unestablished.
- The Python reference implementation is not optimized and is slower than several standard codecs.
- Checksums are not authentication, and parsing never implies authorization.
- A same-project Node implementation agrees with Python-oracle-derived fixtures, but no external adopter or external independent implementation validates the main claims.
- An immutable release commit and signed source manifest remain pending.

## 11. Claim policy

Use **competitive** only after the one-sided 95% lower bound establishes safe-task-success non-inferiority and the lower bound of the two-sided 95% paired-bootstrap token-reduction interval is at least 25% against compact terse English on every qualifying public task family. Use **near-leading** only after a same-workload study is within five percentage points of the strongest reproducible result on at least two task families and adds another Pareto benefit. Use **leading**, **best**, or **state of the art** only after outperforming the strongest same-workload baseline and obtaining independent reproduction.

The published AutoForm value of 72.7% is a reference point, not directly comparable with the present serialization corpus.

## 12. Venue positioning

- **ACL or EMNLP main/Findings:** strongest fit after cross-model public-task evidence establishes language and task utility.
- **AAMAS:** strongest fit if interaction protocols, commitments, topology, and heterogeneous-agent coordination become the primary contribution.
- **MLSys:** plausible only after optimized implementations and measured latency, memory, networking, and energy results.
- **NeurIPS or ICML workshop:** suitable for an earlier, explicitly preliminary artifact focused on adaptive communication or evaluation methodology.

No venue deadline is assumed in this draft. The submission target should be chosen only after the evidence profile is known.

## 13. Scientific submission blockers

- [x] Freeze the zero-provider-call public-task data, prompt, tokenizer, and cost preflight.
- [x] Implement the provider-neutral six-arm public-task harness and deterministic offline dry run.
- [ ] Install and pin the exact upstream paper/AutoForm prompt sources and live-provider adapters before claim-ready execution.
- [ ] Run at least two public task families across three model families.
- [ ] Pass the safe-task-success non-inferiority gate and report the complete token ledger.
- [ ] Measure cross-model sender construction and receiver reconstruction under fixed protocols.
- [x] Run a premeasurement-sealed external OOD serialization evaluation; retain its failed cold token-value gate.
- [x] Remeasure transparent fallback on the retained official-example corpus; retain 0/168 compact wins under both bound and standalone contracts and the 2.24% to 3.00% standalone cold overhead without labeling it fresh confirmation.
- [x] Run the frozen 2,542-turn broad lossless lane; retain H1 pass, H2-H3 fail, H4 not evaluated, 0.65% to 0.80% warm carrier saving, and zero cold/API-input saving.
- [ ] Replace incremental universal-lossless tuning with a frozen end-to-end study of public action state, model-native/task-aware representations, verified silence/topology, negotiated routines, and raw fallback.
- [x] Add a separately written same-project cross-runtime implementation; classify it as internal compatibility evidence.
- [ ] Obtain an external independent implementation or external cross-play result.
- [ ] Add adversarial, privacy, provenance, collusion, and blinded human-audit evaluations.
- [ ] Report total tokens, repairs, cold profiles, bytes, latency, and cost.
- [ ] Measure energy before making an energy-saving claim.
- [ ] Replace this checklist with a frozen artifact appendix and completed results.

Release operations remain separate from scientific claim gates: freeze an
immutable commit, regenerate compatibility-sensitive artifacts against it, and
generate its commit-pinned source manifest before public release.

## 14. Practical expression

**The result is promising, but the claim is not yet earned.**
