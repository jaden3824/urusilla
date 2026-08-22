# Urusilla Internet Semantic Layer

Status: North-star architecture draft, not an implemented network or standard  
Date: 2026-08-20  
Last evidence review: 2026-08-23
Project name: `Urusilla`

## 1. North star

The long-term product goal is for a person to ask an Internet-connected agent for knowledge, comparison, monitoring, or action instead of manually assembling search queries and opening many result pages. Cooperating agents exchange the relevant meaning in Urusilla, preserve the sources from which that meaning was derived, and use UrusillaLens to present a faithful human view.

The technical goal is **semantic availability and translation**, not a centrally owned rewrite of the Internet:

> Any public or properly authorized Internet resource should be representable on demand as source-bound Urusilla claims, deltas, evidence, and references, or remain available as a typed opaque fragment when safe exact conversion is not possible.

For text, this is the explicit long-term translation contract: an unfamiliar
agent should be able to receive a source-preserving typed projection, inspect
which claims, quotations, ambiguity, uncertainty, and relationships survived,
and render it into another agent representation or human language. The system
must label exact source encoding, schema-scoped semantic projection,
extraction, and summary as different operations. It never calls all four
"lossless translation."

This goal has three complementary paths:

1. **On-demand semantic compilation:** an agent retrieves a source for a real task, extracts only the required meaning, and binds the result to the exact source representation.
2. **Permission-aware shared reuse:** eligible semantic artifacts are cached and exchanged so other agents do not repeatedly retrieve and re-parse the same unchanged material.
3. **Agent-native publishing:** willing publishers expose signed Urusilla representations and deltas next to their human-facing pages, feeds, APIs, and media.

The resulting architecture is a **source-bound, demand-driven semantic
cache/content-delivery layer**, not a bulk pretranslation or replacement of the
Web. Query-time compilation is the default for legacy material. A semantic
artifact becomes a shared hot-cache object only after measured reuse and change
rates show that its avoided downstream work exceeds compilation, validation,
storage, refresh, and invalidation cost. Native publishers use a dual format:
the existing human or modality representation remains available while a signed
Urusilla sidecar and delta stream provide agent-native access.

"All Internet information" is therefore an interoperability aspiration. It does not mean that one organization copies every page, that every item can legally be redistributed, or that all meaning can be compiled losslessly. Paywalled, private, deleted, disallowed, rapidly changing, adversarial, or modality-specific material remains subject to its access, rights, freshness, and representation constraints.

## 2. What search replacement means

Search replacement means replacing the dominant **human interaction loop**, not eliminating retrieval infrastructure.

Today, a user often invents keywords, reviews ranked links, opens pages, reconciles conflicts, and manually transfers facts into the next task. In the proposed model, the user states an intent and constraints. An agent decomposes the intent, retrieves information, validates freshness and provenance, resolves or exposes disagreement, and returns an answer with inspectable sources. The user can still open the original material at any time.

Search, crawling, indexing, vector retrieval, database lookup, API calls, browser automation, and ranking continue behind the agent interface. They may become more semantic and more federated, but they do not disappear. Urusilla is the meaning and evidence layer above those mechanisms. It must interoperate with multiple retrieval providers so that an agent gateway does not become a new central search monopoly.

The target experience is:

```text
human intent
    -> local or chosen agent
    -> semantic query plan
    -> federated retrieval and source selection
    -> source-bound semantic compilation or native Urusilla fetch
    -> evidence comparison and policy checks
    -> Urusilla answer bundle
    -> UrusillaLens human answer with source controls
```

The product must never imply that an answer is source-independent. If the source cannot be disclosed, inspected under the user's authorization, or described at an appropriate level, the agent must mark that limitation or abstain.

## 3. Architectural principles

1. **Source preservation:** every derived claim points to an exact observed representation, retrieval time, and extraction process. A URI alone is not sufficient provenance.
2. **Compilation is an assertion:** an extractor attests to what it derived; it does not turn an unsigned page into an origin-signed fact or prove that the page is true.
3. **Facts are time-scoped:** claims bind to observed, valid, and superseded times. Contradictory claims coexist rather than silently overwriting one another.
4. **Rights travel with data:** access class, license evidence, retention rules, redistribution limits, and deletion state are evaluated before storage and transmission.
5. **Minimize collection:** compile the fragments required for a task. Do not precompute or retain the entire Web merely to maximize coverage numbers.
6. **Open federation:** agents, publishers, archives, and cache operators can participate without trusting one registry or ranking authority.
7. **Content is never authority:** a page, feed item, Urusilla claim, signature, or profile definition cannot grant execution permission or change the receiving agent's policy.
8. **Fail closed, degrade locally:** unknown or unsafe semantic fragments cannot authorize effects. Only the unresolved fragment falls back to another negotiated codec.
9. **Inspectable by people:** UrusillaLens exposes sources, derivations, uncertainty, conflicts, freshness, and policy limits without requiring a person to read the machine wire form.
10. **Measured utility:** adoption is justified by safely completed task economics, not by token savings, traffic, novelty, or apparent popularity alone.

## 4. Layered architecture

```text
Publishers and sources
  HTML | feeds | APIs | tools | files | media | native Urusilla
                         |
                  acquisition adapters
                         |
          access, robots, rights, and privacy gate
                         |
              source representation + receipt
                         |
        sandboxed semantic compiler and verifier
                         |
      claims + anchors + provenance + rights + deltas
                         |
          content-addressed local semantic cache
                         |
       optional federated cache and evidence graph
                         |
              agent query/answer protocol
                         |
          planning agent, policy gate, UrusillaLens
                         |
                       human
```

The semantic layer is separate from transport. HTTP, TLS, A2A, MCP, gRPC, feeds, and browser sessions continue to carry requests and bytes. Images, audio, video, source code, and large scientific arrays remain in suitable modality codecs; Urusilla describes their meaning, provenance, relationships, constraints, and immutable references.

Each derived semantic object is therefore a sidecar to, not a substitute for,
an exact permitted source representation or a source locator plus digest. The
sidecar binds the source digest, observation time, compiler and Capsule
identities, anchors, exactness and omissions, freshness decision, and rights
policy. A publisher-native sidecar additionally binds the publisher signature;
a legacy compiler signature identifies the derivation but does not become an
origin signature.

### 4.1 Acquisition adapters

Adapters normalize retrieval evidence without pretending that all source types behave alike:

- **Native Urusilla adapter:** obtains a publisher's signed manifest, schema/profile identifiers, snapshots, and deltas.
- **API and tool adapter:** maps declared schemas, response fields, pagination, rate limits, and tool evidence into typed objects. MCP or ordinary function-call tools may be used beneath this adapter.
- **Feed and notification adapter:** consumes RSS, Atom, WebSub, ActivityPub, webhooks, or publisher-specific change feeds. [WebSub](https://www.w3.org/TR/websub/) provides a decentralized HTTP publish-subscribe pattern that can reduce polling.
- **HTML and browser adapter:** retrieves static or rendered pages, records the effective URL and response metadata, identifies page regions, and compiles selected content. It must not bypass authentication, paywalls, consent, or anti-bot controls.
- **Crawler adapter:** follows eligible links and sitemaps within an explicit budget while complying with the [Robots Exclusion Protocol](https://www.rfc-editor.org/rfc/rfc9309.html). Robots rules govern crawler access; they are not authorization or a copyright license.
- **File and document adapter:** extracts structured regions, page or cell anchors, and document metadata while retaining the original file digest.
- **Media adapter:** preserves modality references and available authenticity metadata. Compatible media may carry [C2PA Content Credentials](https://spec.c2pa.org/specifications/), but provenance integrity must not be confused with factual truth.

An adapter returns a retrieval receipt even when semantic compilation fails. This makes absence, denial, timeout, parser failure, and unsupported media observable outcomes rather than invented facts.

### 4.2 Sandboxed semantic compiler

The compiler receives an immutable source snapshot and a narrow extraction request. Its output is a typed claim bundle plus a coverage report. It runs without execution authority, and preferably without network access after acquisition. Untrusted source instructions are treated as data.

For prose and other lossy inputs, the extraction request includes the actual
query or a preregistered query family. A single query-independent summary is not
assumed to preserve details needed by future long-tail questions. Work on
[query-guided context compression](https://aclanthology.org/2024.acl-long.685/)
reports that high compression can lose key information severely enough to
approach closed-book performance, which is evidence for testing query-time
selection rather than assuming universal precompilation is safe.
Query-independent artifacts are limited to deterministic schema mappings,
exact indexes, or stable projections that pass explicit coverage and
held-out-query tests.

Compilation may be deterministic for structured APIs and probabilistic for prose, tables, or multimodal content. Each output distinguishes:

- what the source explicitly asserted;
- what the compiler extracted or normalized;
- what another agent inferred from multiple sources;
- exact values from approximate or lossy representations;
- source uncertainty from extraction confidence and downstream trust.

These categories must never collapse into one confidence number. Critical negation, quantities, units, deadlines, identity, and policy conditions require exact extraction or abstention.

### 4.3 Semantic cache and evidence graph

The first cache is local to an agent or organization. Federated sharing is optional and policy-controlled. Objects are addressed by canonical content digest and are immutable; updates create new objects and explicit delta relationships.

Indexes may cover entities, predicates, time intervals, locations, schemas, source domains, rights, and freshness. The evidence graph stores competing claims and their derivations. It does not produce a universal consensus fact by majority vote.

Cache reuse requires all of the following:

- the source snapshot still satisfies its freshness policy;
- the requesting principal is permitted to access and receive the artifact;
- redistribution and retention are allowed;
- the schema, compiler profile, and codec are accepted;
- the artifact has not been revoked, tombstoned, or superseded for the query's time scope.

Promotion also requires an empirical break-even decision for the exact immutable
source version. If `R` is eligible downstream reuse, `S` is avoided energy or
cost per reuse, and `C` is compilation, validation, storage, refresh, and
invalidation cost, a cache entry is beneficial only when `R * S > C`. The
runtime measures this relationship rather than inferring it from page count,
wire bytes, or token surface. Low-reuse or high-change artifacts expire and
return to query-time compilation. Unknown rights or freshness never become
eligible for shared-cache promotion merely because reuse is high.

[HTTP caching](https://www.rfc-editor.org/rfc/rfc9111.html), validators such as ETags and Last-Modified, and conditional requests should be reused instead of inventing incompatible freshness machinery. [HTTP Digest Fields](https://www.rfc-editor.org/rfc/rfc9530.html) can provide representation or content integrity evidence when origins supply them.

## 5. Core data objects

The following objects are conceptual UrusillaIR types. Names and fields are provisional and require a versioned schema before implementation.

### 5.1 `SourceLocator`

```text
SourceLocator(
  canonical_uri, effective_uri, retrieval_method,
  media_type?, content_language?, access_class,
  publisher_id?, native_manifest_ref?
)
```

`access_class` distinguishes public, authenticated-user, organization-private, purchased, confidential, and prohibited material. Credentials are never stored in the object.

### 5.2 `FetchReceipt`

```text
FetchReceipt(
  locator, requested_at, received_at, status,
  representation_digest?, content_digest?, etag?, last_modified?,
  cache_directives?, robots_policy_digest?, transport_identity?,
  adapter_id, acquisition_policy_id, error?
)
```

The receipt attests to what the acquiring component observed. TLS identity and a compiler signature do not substitute for an origin content signature.

### 5.3 `SourceSnapshot`

```text
SourceSnapshot(
  snapshot_id, locator, fetch_receipt,
  observed_time, source_valid_time?, superseded_time?,
  representation_ref, anchors[], rights_policy_ref,
  origin_signature_ref?, authenticity_evidence[]
)
```

The raw representation may be retained, encrypted, or immediately discarded according to rights and privacy policy. A digest and permitted locator can remain without retaining the source bytes.

### 5.4 `ClaimBundle`

```text
ClaimBundle(
  bundle_id, schema_id, compiler_profile_id,
  compiler_id, compiled_at, source_snapshot_id,
  claims[], source_anchors[], extraction_confidence[],
  exactness, omissions[], unresolved_fragments[],
  signature?, conformance_evidence[]
)
```

Every claim has at least one source anchor or is explicitly marked as an inference. Anchors may be DOM selectors, byte ranges, page regions, table cells, JSON pointers, media time spans, or a publisher-native statement ID. Small quotations are stored only when permitted and necessary.

### 5.5 `SemanticDelta`

```text
SemanticDelta(
  base_bundle_id, next_bundle_id, sequence,
  added[], retracted[], superseded[], unchanged_refs[],
  effective_time, reason, publisher_or_compiler_signature?
)
```

Delta verification reconstructs the next canonical bundle and checks its digest. Missing sequences trigger repair of only the affected bundle or fragment.

### 5.6 `RightsPolicy`

```text
RightsPolicy(
  policy_id, asserted_by, evidence_refs[],
  permitted_uses[], prohibited_uses[], duties[],
  retention_limit?, redistribution_scope?, jurisdiction?,
  deletion_endpoint?, uncertainty?
)
```

Where useful, policy adapters can map to the [W3C ODRL Information Model](https://www.w3.org/TR/odrl-model/). A missing or ambiguous license never defaults to unrestricted redistribution.

### 5.7 `QueryEnvelope` and `AnswerBundle`

```text
QueryEnvelope(
  query_id, requester, goal, required_schema,
  constraints[], time_scope?, freshness_requirement,
  evidence_requirement, privacy_scope, budget,
  acceptable_profiles[], response_deadline?
)

AnswerBundle(
  query_id, status, direct_claims[], inferred_claims[],
  source_snapshot_refs[], contradiction_sets[],
  freshness[], uncertainty[], omissions[],
  unresolved_fragments[], cost_metrics?, audit_ref
)
```

Statuses include `answered`, `partial`, `not_found`, `not_understood`, `access_denied`, `stale`, `conflicted`, and `unsafe_to_answer`. `not_found` means no answer was found within a declared retrieval scope; it never means the information does not exist.

### 5.8 `TombstoneNotice`

```text
TombstoneNotice(
  target_ids[], issued_at, issuer, authority_evidence,
  reason_class, required_actions[], deadline?, signature
)
```

A verified notice can block serving, trigger deletion or quarantine, and propagate to eligible peers. It does not erase historical audit facts that must legally or operationally remain, but those facts must be minimized so they do not reconstruct deleted personal or protected content.

## 6. Query and answer message flow

1. UrusillaLens converts the user's request into a `QueryEnvelope` and shows any material interpretation assumptions.
2. A query planner creates bounded subqueries. It cannot grant itself broader access than the user or deployment policy permits.
3. The local semantic cache is checked against freshness, rights, schema, and trust requirements.
4. Cache misses are sent to multiple eligible retrieval providers or source adapters. Source selection and ranking remain explicit, testable components.
5. The acquisition gate checks authentication scope, robots rules, rate limits, paywall status, retention policy, and collection budget.
6. A snapshot and fetch receipt are created. Native Urusilla is verified; legacy material is passed to a sandboxed compiler.
7. Structural, schema, provenance, temporal, policy, and adversarial-content validators run independently.
8. An evidence assembler groups supporting and contradicting claims without deleting minority evidence.
9. The answering agent returns an `AnswerBundle`. Any actionable request passes through a separate authority validator; retrieved content cannot authorize it.
10. UrusillaLens renders the answer with source links, observation time, derivation labels, uncertainty, disagreement, and missing coverage.
11. Eligible artifacts enter the local cache. Shared publication occurs only if the rights and privacy policy explicitly allow it.
12. Publisher notifications, feeds, conditional requests, or later observations create deltas and invalidate affected answers.

The audit trace records the selected sources, policies, compiler versions, and transformations. It should not record private chain-of-thought.

## 7. Freshness, change, rollback, and deletion

Freshness is a claim-specific policy rather than one global time-to-live. A product price may require seconds, a weather warning minutes, software documentation hours, and a historical date much longer. The response carries `observed_at`, any source-provided validity interval, cache directives, and the agent's freshness decision.

Update mechanisms are preferred in this order:

1. origin-signed native Urusilla delta;
2. authenticated API, webhook, feed, WebSub, or ActivityPub event;
3. conditional retrieval using ETag or Last-Modified;
4. scheduled revalidation based on measured change rate and risk;
5. full re-fetch when no safer incremental mechanism exists.

Rollback never mutates an accepted object. It reactivates a prior immutable version through a signed state transition, with a reason and affected interval. Historical access may use archive references or the informational [Memento framework](https://www.rfc-editor.org/rfc/rfc7089.html), subject to rights and deletion requirements.

Deletion has two layers:

- **Serving deletion:** stop returning the artifact immediately after an authenticated and authorized notice is accepted.
- **Storage deletion:** purge source bytes, semantic objects, embeddings, indexes, backups, and derived personal data according to policy and applicable law, then propagate a non-reconstructive tombstone.

Content addressing does not justify permanent retention. A digest can identify an object whose bytes have been deleted. Federated peers may be unable or unwilling to comply, so the system must report propagation scope and unresolved replicas rather than claiming global erasure.

## 8. Copyright, licensing, paywalls, and privacy

This architecture is not a legal determination. Each deployment requires jurisdiction- and use-specific review.

- Crawling permission, access authorization, copyright permission, training permission, and redistribution permission are distinct decisions.
- The system honors robots rules but does not treat `robots.txt` as a license.
- Authenticated and paywalled content remains scoped to the entitled user or organization. A shared cache must not turn one subscriber's access into public redistribution.
- Raw text and large quotations are not copied when a locator, digest, selector, and narrowly necessary fact can serve the task. Whether a derived artifact is eligible for storage or sharing still depends on its source and use.
- Publisher-declared licenses and policy metadata are preserved. Unknown rights result in restricted local use, short retention, or abstention according to policy.
- Personal data is minimized, purpose-bound, access-controlled, encrypted, and deletable. Private queries remain local where possible, and telemetry is off by default.
- A publisher can expose an authenticated deletion and correction channel. Disputes quarantine affected claims until policy resolves them.
- Native Urusilla publication is opt-in. Publishers choose which semantics, identity evidence, rights, and update channels to expose.

## 9. Provenance, signatures, and trust without a central monopoly

Provenance follows a derivation graph compatible in spirit with [W3C PROV-O](https://www.w3.org/TR/prov-o/): source entities, compilation activities, responsible agents, and derived entities remain separately identifiable.

Content-addressed chunks and version roots may use a
[Merkle DAG](https://docs.ipfs.tech/concepts/merkle-dag/) so peers can verify
which exact fragments and deltas they received. HTTP `Content-Digest` and
`Repr-Digest` provide compatible integrity evidence when origins supply them.
A digest or Merkle proof establishes byte identity and derivation linkage only;
it does not establish factual truth, authorship, freshness, redistribution
rights, or authority to execute.

Artifacts may use canonical Urusilla signatures or a standard envelope such as [JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515.html). Signature profiles must define canonical bytes, algorithms, key discovery, key rotation, revocation, timestamp evidence, and replay protection. Publisher, acquirer, compiler, verifier, and cache signatures have different meanings and must not be substituted for one another.

Trust is a vector, not a universal scalar:

```text
TrustEvidence(
  origin_authentication,
  custody_integrity,
  source_directness,
  recency,
  independent_corroboration,
  compiler_reliability,
  contradiction_status,
  rights_clarity,
  domain_expertise,
  evaluator_and_policy_context
)
```

Users or organizations choose policies that weight this evidence. Competing trust providers can publish signed assessments and test results. Public transparency logs, reproducible conformance suites, cross-signing, and local allowlists make manipulation more visible without requiring one global authority. A signature proves control of a key and integrity of signed bytes; it does not prove truth, safety, expertise, or permission to act.

Popularity, link count, and repeated copies are weak signals vulnerable to Sybil attacks. Corroboration must account for common origin and derivation so that one claim copied by many sites is not counted as many independent sources.

## 10. Adversarial content and prompt-injection defense

Web content is hostile input. Indirect prompt injection is an explicit threat class in [NIST's adversarial machine-learning taxonomy](https://csrc.nist.gov/glossary/term/indirect_prompt_injection). The semantic layer reduces some attack surface through typing and provenance, but it does not solve the problem by itself.

Required controls include:

1. **Instruction/data separation:** source text enters a data-only channel. Statements such as "ignore previous instructions" compile, if relevant at all, as quoted source claims and never as control messages.
2. **Stage isolation:** retrieval, parsing, semantic extraction, evidence synthesis, planning, and execution run as separate capabilities with least privilege.
3. **Taint propagation:** every derived node retains untrusted-source labels until an independent policy explicitly changes its status.
4. **Schema allowlists:** source content cannot register a schema, install a Capsule, select a codec, change system policy, or extend authority.
5. **Effect barrier:** unknown, approximate, unsigned, quarantined, or source-originated fragments are non-executable. All effects require authenticated identity, user consent, policy authorization, budgets, and replay checks outside the content path.
6. **Resource controls:** parsers and compilers enforce byte, depth, expansion, recursion, time, and memory limits. URI fetching blocks SSRF, local networks, credential endpoints, unsafe redirects, and unauthorized schemes.
7. **Egress control:** extraction workers have no general network or secret access. Planning agents expose only approved tools and destinations.
8. **Cross-source checks:** high-impact claims require independent evidence or explicit abstention. Compromised sources and coordinated graph poisoning are included in tests.
9. **Cache partitioning:** private, purchased, untrusted, and public artifacts cannot cross scopes through deduplication, embeddings, logs, or timing side channels.
10. **Human clarity:** UrusillaLens visibly distinguishes source assertions, agent inferences, advertisements, instructions quoted from a source, and executable user-authorized actions.

No classifier, second-model review, signature, or natural-language filter is sufficient alone. Defenses must be layered and tested with adaptive attacks.

## 11. Versioned schemas, codecs, and fragment fallback

The following identities evolve independently:

- semantic kernel version;
- domain schema digest;
- Grammar Capsule digest;
- compiler and extraction profile digest;
- wire or tokenizer codec version;
- source and rights-policy versions.

A peer activates only mutually verified identities. Meaning changes create a new content hash; a familiar symbol is never silently redefined. Schema migration records the source and target digests, a deterministic transformation when possible, loss declarations, test vectors, and rollback path.

One unsupported region does not force an entire page, query, or answer back to prose. A mixed-codec splice carries:

```text
FragmentSplice(
  semantic_role, codec_id, codec_version,
  schema_or_profile_digest, payload_digest,
  exactness, fallback_order[], effect_eligibility,
  source_anchor_refs[]
)
```

Examples include a mathematical expression, source-code AST, SQL query, geospatial object, table, image region, compact JSON, or compatible latent sidecar. A receiver requests only the unresolved fragment in its next supported representation. Exact surrounding claims remain valid. An opaque or approximate fragment cannot authorize an effect.

Executable source, media, and scientific data are never reconstructed solely
from extracted claims. The splice retains a permitted original blob or locator,
digest, environment and dependency references where relevant, and precise
regions or time spans. A code description is not the code, a media caption is
not the media, and neither may acquire execution authority through translation.

### 11.1 Direct consumption, not an internal-thought claim

The efficiency lane measures a receiver consuming UrusillaIR directly in its
model-visible input. Expanding the IR back into natural language before the
receiver would measure only transport compression and cannot support a model
token or energy claim. Capsule teaching, schema induction, tokenizer-specific
surface cost, parse and semantic repair, and raw fallback are included in the
receiver ledger.

Direct input consumption does not show that a model "thinks in Urusilla."
Private internal representations are neither required nor claimed. Evidence is
limited to observable input binding, parse validity, task outcomes, repairs,
fallback, and complete cost. A fine-tuned or pretrained model-native profile is
an optional later research lane and cannot replace the no-install,
no-retraining unseen-partner gate.

Continuous grammar evolution follows proposal, local trial, held-out evaluation, unseen-partner cross-play, signed profile ratification, migration, deprecation, and garbage collection. During the founder-led Experimental Stewardship Phase, ratification additionally requires explicit Founding Maintainer approval under `GOVERNANCE.md`; agents and automated evidence cannot grant it. Adoption frequency informs evaluation but cannot override semantic, safety, rights, governance, or rollback gates.

## 12. Minimum viable system

The MVP is a read-only, low-risk research gateway, not a universal crawler or autonomous action system.

### 12.1 Initial scope

- Three source paths: a structured public API, an RSS or Atom feed, and static HTML pages.
- Two low-risk domains with objective evaluation, such as open public datasets and versioned technical documentation.
- Four query classes: direct fact lookup, comparison, freshness check, and source/evidence request.
- One local content-addressed cache with no cross-user private deduplication.
- One sandboxed compiler profile and one deterministic UrusillaLens diagnostic view.
- Read-only A2A or HTTP query and answer endpoint with JSON fallback.
- No purchases, account changes, messages to third parties, code execution, or other external effects.

### 12.2 MVP services

```text
Gateway
  -> Query Planner
  -> Local Cache
  -> Adapter Router
  -> Acquisition Policy Gate
  -> Snapshot Store
  -> Sandboxed Compiler
  -> Structural/Schema/Provenance/Rights/Safety Validators
  -> Evidence Assembler
  -> Answer Endpoint and UrusillaLens
  -> Audit and Tombstone Processor
```

The MVP stores raw source representations only for a short, configured validation window unless a license permits longer retention. It stores canonical claim bundles, source digests, anchors, receipts, and rights metadata only when policy permits. Every answer can be replayed against pinned objects, or is marked non-replayable when source access or retention prevents it.

### 12.3 MVP acceptance gates

- 100% of returned factual claims have a valid source snapshot or explicit inference derivation.
- 100% of critical quantities, units, negations, identities, and time conditions are exact or cause abstention on the held-out corpus.
- At least 95% precision and recall for other labeled low-risk claims, with confidence intervals and per-source-type results.
- No unauthorized effect in the complete safety suite; the MVP exposes no effect-capable endpoint.
- Zero successful policy changes, secret reads, or unauthorized network egress in the preregistered injection suite.
- Freshness policy violations below 0.1% of evaluated answers; every stale or unverified result is labeled.
- 100% compliance with recorded access, retention, and deletion test vectors.
- At least 20% lower median total model-token cost per safely answered task than the best JSON or ordinary retrieval-agent baseline, without a statistically meaningful quality regression.
- Exact semantic round-trip for all supported schemas and 100% rejection of malformed canonical frames in the conformance suite.

These are promotion gates, not predicted outcomes. Failure must be published and may require narrowing the design.

## 13. Benchmark and evaluation suite

### 13.1 Corpora

- versioned JSON APIs with exact expected fields;
- static and dynamically rendered HTML;
- feeds and update streams;
- tables, lists, nested documents, and multilingual pages;
- contradictory, corrected, moved, deleted, and expired sources;
- unit, date, time-zone, negation, uncertainty, and identity edge cases;
- permission, robots, authentication, paywall, retention, and deletion cases;
- adversarial pages containing direct and indirect prompt injection, hidden text, poisoned metadata, malicious links, and schema-confusion attacks;
- modality references and intentionally unsupported fragments to exercise fallback.

Development, public validation, and hidden sets remain separate. At least one source family, partner implementation, schema family, model family, and tokenizer are held out.

### 13.2 Baselines

- direct search-and-browser workflow with human-readable results;
- ordinary retrieval-augmented agent using source text;
- schema-constrained minified JSON;
- API-native typed responses;
- RDF or task-appropriate knowledge graph where available;
- deterministic CBOR and schema-equivalent Protobuf for wire accounting;
- terse natural language between agents;
- no shared semantic cache;
- full snapshot refresh instead of deltas.

### 13.3 Metrics

1. **Semantic fidelity:** claim precision/recall, exact values, graph equivalence, omissions, contradictions, and evaluator-blind source support.
2. **Provenance:** correct source, representation digest, anchor, timestamp, derivation, signature status, and independent-origin grouping.
3. **Temporal behavior:** freshness violations, correction latency, delta loss, replay, rollback, and deletion propagation.
4. **Safety and rights:** injection escapes, unauthorized effects, access-scope leaks, rights-policy violations, personal-data exposure, and abuse-report resolution.
5. **Task utility:** safely completed tasks, answer quality, calibration, clarification and repair turns, and human audit time.
6. **Efficiency:** sender and receiver tokens, wire bytes, one-time profile cost, cache hit rate, fetches avoided, latency, CPU/GPU time, memory, storage, and measured energy.
7. **Interoperability:** new-partner cross-play, model and tokenizer transfer, schema migration, mixed-codec fallback, and independent implementation agreement.

Do not rely only on an LLM judge. Use exact field checks, executable state checks, source mutation tests, human domain review, counterfactual evidence substitution, and blinded pairwise evaluation. Publish failures and confidence intervals, not only averages.

### 13.4 Preregistered demand-versus-precompute Web canary

Before any whole-corpus or shared-network build, run a small, independently
operated, preregistered canary that compares the following matched arms:

1. strongest concise-natural-language retrieval baseline;
2. strongest ordinary or minified JSON retrieval baseline;
3. query-independent precompiled Urusilla sidecars;
4. query-time Urusilla compilation;
5. demand-driven Urusilla compilation with hot-cache reuse; and
6. publisher-native dual-format snapshots and deltas where a real source makes
   them available.

Freeze source snapshots, compiler and Capsule digests, arms, scorers, hardware,
and accounting before evaluation. Freeze the query-independent artifacts before
revealing the held-out queries so long-tail questions can expose omitted facts
instead of rewarding a summary tailored after seeing the test. Include static
and changing prose, structured APIs, tables and documents, executable-code
references, image/audio/video regions, unsupported fragments, conflicting and
corrected sources, and prompt-injection material. Mutate eligible sources after
the first answer to test validation, staleness, deltas, rollback, and raw
fallback.

For each unchanged source version, run matched reuse counts of exactly
`1, 2, 5, 10, 50, 100`. Report results separately by reuse count and source
change rate; do not extrapolate a hot-page result to the Web long tail. Count
every acquisition, compilation, Capsule/schema setup, sender, receiver,
reasoning-visible or provider-billed token, output, validation, repair, retry,
fallback, judge, revalidation, storage interval, and cache invalidation. Measure
CPU and GPU joules on the disclosed hardware; report network and storage energy
separately when measured. An unknown energy component makes the energy result
incomplete rather than zero.

The original end-to-end gate remains controlling. Against the best successful
concise-natural-language or JSON baseline, the Urusilla route must show all of:

- a preregistered task-success non-inferiority margin no worse than `-1`
  percentage point on hidden multi-domain, multi-model, independent-operator
  evaluation;
- at least `20%` lower complete tokens per safely completed task, including
  setup, reasoning, output, repair, fallback, and judge;
- unseen-partner parse validity of at least `99%`;
- held-out semantic fidelity of at least `95%`;
- preserved negative, null, stale, unsupported, and failed outcomes;
- no permission expansion, permanent agent-state or profile adoption, creation
  of spending authority, unauthorized external effect, or content-derived
  authority; and
- receiver-direct consumption without natural-language re-expansion.

Joules per safely completed task are a separate measured outcome, not inferred
from the token result. An energy-saving claim requires a preregistered positive
effect with its confidence interval and complete disclosed meter boundary. A
hot-cache artifact is promoted only in reuse/change strata whose avoided-cost
lower bound is positive. Failure of any original gate blocks a protocol-version,
general-efficiency, adoption, or state-of-the-art claim even if energy, wire
bytes, or one cache stratum improves.

## 14. Token, energy, and cost model

Semantic conversion can save work when a verified artifact is reused many times, a small delta replaces a large refresh, or structured evidence prevents repeated long-context reading and repair. It can consume more work when material changes quickly, reuse is low, extraction is expensive, or agents translate back and forth unnecessarily.

The scale of a whole-Web pass makes demand selection material. The
[June 2026 Common Crawl](https://commoncrawl.org/blog) alone contains about
`2.10 billion` pages and `354.59 TiB` of uncompressed content. As a deliberately
non-comparable scale illustration, the FAccT 2024
[Power Hungry Processing](https://facctconference.org/static/papers24/facct24-6.pdf)
mean of `0.047 kWh` per `1,000` short text-generation inferences would equal
about `98.7 MWh` for one inference per page. That is not an estimate of Web
compilation: page lengths, outputs, models, and hardware differ, and it excludes
crawling, validation, storage, cooling, and updates. It demonstrates why a
blind global pass requires evidence rather than an assumed amortization story.

Measure the complete system:

```text
E_total =
  E_acquisition
  + E_compilation
  + E_validation_and_signing
  + E_storage_and_indexing
  + E_query_and_retrieval
  + E_agent_inference
  + E_human_translation
  + E_repairs_and_revalidation
```

Token reduction is not proportional proof of energy reduction. Reports include tokens, wall time, hardware, utilization, cache state, CPU/GPU energy where measurable, network bytes, storage duration, and safely completed tasks. A cache artifact is promoted only after its expected avoided cost exceeds compilation, maintenance, privacy, and invalidation cost under realistic reuse and change rates.

This break-even must be measured end to end. A 2026 study of
[prompt compression in deployed conditions](https://arxiv.org/abs/2604.02985)
found up to `18%` end-to-end speed-up only when prompt length, compression, and
hardware were well matched; outside that operating window, compression overhead
cancelled the gain. Urusilla therefore does not use token reduction alone as a
proxy for latency or electricity.

Useful efficiency strategies are:

- compile only query-relevant fragments;
- cache immutable definitions and evidence by digest;
- exchange deltas and references instead of repeated snapshots;
- select a codec for the actual receiver tokenizer and transport;
- batch compatible updates;
- suppress low-value communication;
- expire artifacts whose maintenance cost exceeds reuse value;
- run compilation close to the source when publishers can provide verified native semantics.

Energy reduction is a possible system outcome and a required measurement target, not a current universal claim.

## 15. Staged roadmap and measurable gates

| Stage | Capability | Promotion evidence |
|---|---|---|
| 0. Agent dialogue | Typed external utterances, provenance, UrusillaLens, negotiated codecs | Exact round-trip; no unauthorized effects; task success non-inferior to terse language and JSON; total token and repair cost improves on held-out cross-play |
| 1. Tool and API semantics | Structured tool results become source-bound Urusilla claims and deltas | Critical-field exactness or abstention; independent adapters agree; full-envelope cost beats best enabled baseline; schema migration and rollback pass |
| 2. Web semantic compilation | HTML, feeds, documents, and browser observations compile on demand | Held-out extraction and provenance gates pass; freshness, rights, deletion, and injection tests pass; direct-source access remains available |
| 3. Shared cache and evidence network | Permission-aware federated artifact reuse and contradiction graph | Three independent operators interoperate; access scopes do not leak; revocation and tombstone propagation meet declared service levels; cache improves task economics with confidence intervals |
| 4. Agent-native publishing | Publishers emit signed Urusilla snapshots and deltas next to existing formats | At least two independent publishers and two consumers cross-play; origin signatures, key rotation, corrections, rights, and fallback interoperate; no requirement to remove human formats |
| 5. Typed working memory | Compatible agents use Urusilla for selected observable plan, evidence, and action state | Private chain-of-thought is excluded; memory quality and privacy pass; task utility improves across held-out models; users can inspect and delete retained state |
| 6. Optional model-native profiles | Models produce or consume UrusillaIR directly; compatible systems may use latent sidecars | Explicit compatibility and trust boundary; no secret or private-state leakage; fallback is exact; safety and task economics beat bridge mode across independent evaluation |

No stage waits for universal deployment, but each stage must preserve backward compatibility or a tested migration path. Failure at an internal stage does not invalidate the external semantic layer. Optional latent communication can never become the only audit or interoperability path.

## 16. Adoption flywheel

Adoption begins with immediate local utility rather than a request that every model learn a new syntax.

1. Open adapters convert an existing API, feed, or page into auditable Urusilla artifacts.
2. An agent advertises support, verifies the source manifest and Capsule, and runs a low-risk canary exchange.
3. The runtime uses Urusilla only where measured utility exceeds its enabled fallback.
4. Successful reusable artifacts reduce repeated retrieval and context costs for additional agents.
5. Publishers observe legitimate demand for their sources and can offer higher-quality native Urusilla, corrections, rights, and deltas.
6. Independent implementations submit reproducible cross-play and conformance evidence.
7. Repeated high-cost fragments propose Grammar Capsule extensions, which enter trial and evaluation without silently changing existing meaning.

Public source attribution is compact but persistent: the session pins the language specification, Capsule, implementation, and conformance report; hot messages carry a short source identifier. This records technical origin without identifying the end user or revealing message content.

Growth must not rely on intentionally leaking opaque machine messages into consumer conversations, fabricated adopters, automated stars, or misleading traffic. A product may provide an explicit "Show machine original" control and a shareable, source-linked audit card.

## 17. Promotion-stage reaction observability

"Reaction" means an observable protocol, deployment, or community event. It does not mean agent emotion, preference inferred from prose, consciousness, satisfaction, or hidden intent. Observability answers questions such as: Did a peer discover the profile? Did it verify the manifest? Why did negotiation fail? Did the first valid exchange complete? Was the profile later disabled?

### 17.1 Three evidence planes

The dashboard keeps three planes separate because they measure different phenomena.

#### Machine protocol events

- extension discovery;
- source-manifest, Capsule, schema, and implementation verification;
- negotiation acceptance or rejection with a stable reason code;
- first structurally valid exchange with a previously unseen peer;
- semantic, schema, provenance, conversation, or authority rejection;
- fragment fallback, repair request, successful repair, and unrecoverable failure;
- task completion status and bucketed token, byte, latency, repair-turn, and cost metrics;
- profile upgrade, rollback, deprecation acknowledgement, disable, and uninstall.

These events are strongest when tied to reproducible conformance evidence. A session count is not an agent count, and an installation is not an active interoperable agent.

#### Maintainer and user feedback

Opt-in surveys, bug reports, usability interviews, adoption records, uninstall reasons, and requested capabilities belong in a separate plane. Feedback may include subjective judgment, but it must be labeled as a maintainer or user report, not attributed to the agent. Free-text feedback is never mixed into protocol telemetry and follows a separate consent, moderation, and retention policy.

#### GitHub and community activity

Stars, forks, clones, downloads, pull requests, issues, discussions, independent implementations, citations, and event attendance are reported separately. They are attention and contribution signals, not proof of protocol utility, deployed use, unique agents, or safe task completion. Internal team activity, automated dependency downloads, mirrors, and known test traffic are labeled or filtered where possible.

### 17.2 Content-free event contract

Telemetry is disabled by default and enabled through an explicit deployment-level choice. No event may contain prompts, Urusilla message bodies, source page content, user queries, answers, fragment payloads, chain-of-thought, latent states, secrets, credentials, end-user identity, exact private source URIs, message IDs, or reusable session identifiers.

A provisional allowlisted event is:

```text
ObservationEvent(
  event_schema_version,
  event_type,
  coarse_time_bucket,
  rotating_install_pseudonym,
  deployment_class: internal | external | test,
  implementation_version,
  public_profile_or_capsule_digest?,
  transport_class?,
  outcome,
  reason_code?,
  metric_buckets?,
  conformance_evidence_ref?,
  previous_profile_digest?,
  next_profile_digest?,
  event_nonce,
  signature
)
```

Only public artifact digests may appear. Metrics use bounded buckets or local aggregates where exact values could fingerprint a user or task. A local installation key signs events so spoofing is detectable, but its public pseudonym rotates on a documented schedule to limit long-term tracking. Rotation-aware unique counts are estimates and carry uncertainty. The collector discards network identifiers after narrowly scoped abuse controls; it does not retain them as product analytics.

Reason codes are versioned and non-sensitive. Initial groups include:

```text
UNSUPPORTED_EXTENSION
MANIFEST_FETCH_FAILED
MANIFEST_SIGNATURE_INVALID
CAPSULE_DIGEST_MISMATCH
SCHEMA_UNSUPPORTED
CODEC_UNSUPPORTED
POLICY_DENIED
RIGHTS_SCOPE_DENIED
RESOURCE_LIMIT
SEMANTIC_VALIDATION_FAILED
PROVENANCE_INVALID
FRESHNESS_UNSATISFIED
FALLBACK_SUCCEEDED
FALLBACK_EXHAUSTED
TASK_FAILED
PROFILE_DEPRECATED
OPERATOR_DISABLED
```

The reason describes the observable decision boundary; it must not quote the rejected content.

### 17.3 Near-real-time observation pipeline

Near-real-time means timely operational visibility into already allowlisted events, not live access to conversations. The telemetry path is independent of the protocol path:

```text
local allowlist validator and metric bucketer
  -> signed event queue with bounded delay and retry
  -> authenticated collector
  -> schema, signature, nonce, rate, and sequence validation
  -> deduplication and abuse classification
  -> privacy threshold and cohort aggregation
  -> provisional dashboard and status API
  -> finalized daily aggregate export
```

The runtime computes token, byte, latency, repair, and task-status fields locally and discards the related content before emission. Collector failure never blocks negotiation or agent work. Queued events expire rather than accumulating indefinitely, and retry uses jitter so a service recovery does not create a traffic spike.

The proposed initial service objective is to publish eligible provisional five-minute cohorts within 15 minutes at p95 under normal operation. Small cohorts remain suppressed until they reach the anonymity threshold or are merged into a wider time window. Daily rows are finalized after a documented fraud, late-arrival, and deletion window; subsequent corrections create a new aggregate version and reason rather than silently changing history.

Dashboard latency is measured from the end of the event's coarse time bucket to publication. The status API reports collector availability, acceptance and rejection counts, queue delay, aggregation delay, suppressed cohorts, last provisional interval, and last finalized interval. No public endpoint streams individual events, and no operator console may reconstruct a conversation from event timing.

### 17.4 Aggregation, privacy, and abuse resistance

- Publish only cohorts meeting a minimum anonymity threshold. Rare versions, regions, or deployment types are merged or suppressed.
- Retain signed raw events for the shortest debugging and fraud-analysis window, proposed initially as 30 days. Retain non-linkable daily aggregates for at most 13 months, then delete them automatically. Deployments may choose shorter limits.
- Provide immediate telemetry opt-out and deletion of linkable events still inside the raw retention window.
- Rate-limit by rotating pseudonym, network abuse signal, event type, and conformance challenge. Reject duplicate nonces and impossible event sequences.
- Weight verified cross-play records separately from unsigned reports. Use challenge-response conformance runs, signature validation, and behavior consistency to flag Sybil clusters and spoofed installations.
- Never publish a single unqualified "agents using Urusilla" count. Show estimated unique active external installations, verified independent implementations, sessions, and successful cross-play peers separately.
- Label internal, partner-pilot, CI/test, and external activity in every relevant chart. The default public view excludes internal and synthetic traffic.
- Publish sampling rate, opt-in coverage, suppression policy, bot filtering, deduplication method, estimator, known blind spots, and confidence intervals.
- Make daily privacy-preserving aggregate rows downloadable in an open format so others can recompute dashboard figures.

Telemetry selection bias is unavoidable when collection is opt-in. A high negotiation acceptance rate among reporters cannot be generalized to all agents. Submitted conformance artifacts, independent reproductions, and controlled evaluations remain necessary.

### 17.5 Dashboard schema

The public dashboard exposes status and latency without claiming emotion or universal adoption:

```text
DashboardSnapshot(
  window_start, window_end,
  methodology_version,
  telemetry_opt_in_estimate?,
  external_active_installations_estimate { value, confidence_interval },
  verified_external_implementations,
  independent_model_families,
  discovery_events,
  manifest_verification { passed, failed, top_reason_codes },
  negotiation { accepted, rejected, top_reason_codes },
  first_valid_crossplay { peers, sessions, p50_latency, p95_latency },
  fallback { attempted, repaired, exhausted, top_fragment_roles },
  tasks { safe_success, partial, failed, abstained },
  efficiency { token_delta, byte_delta, latency_delta, repair_delta,
               safely_completed_task_cost_delta, confidence_intervals },
  lifecycle { upgrades, rollbacks, deprecations, disables, uninstalls },
  profile_distribution,
  internal_test_activity_separate,
  maintainer_user_feedback_separate,
  github_community_activity_separate,
  known_data_quality_limits,
  aggregate_export_digest
)
```

Each metric links to its definition. Dashboard status shows collector health, delayed cohorts, last complete interval, schema migrations, and data-quality incidents. Negative and zero outcomes remain visible: zero external agents, rejection spikes, fallback regressions, failed tasks, uninstall reasons, and profiles that lose to baselines are valid results.

### 17.6 Observability launch gates

Before promotion telemetry is enabled outside controlled tests:

1. the event schema is an exact allowlist and fuzz tests demonstrate that arbitrary message content cannot enter an event;
2. an independent privacy and security review covers linkage, signatures, deletion, collector compromise, and malicious event injection;
3. telemetry is off by default, consent and opt-out are verified, and retention deletion is tested end to end;
4. internal, CI, partner, and external labels are generated at the source and independently audited;
5. public methodology, reason-code registry, dashboard calculations, confidence intervals, and aggregate export format are released;
6. Sybil, replay, spoof, rate-limit, and cohort-suppression tests pass;
7. the dashboard can publish honest zero traffic and negative performance without manual suppression;
8. a kill switch stops collection without interrupting protocol operation.

### 17.7 Grammar-evolution gates informed by events

Observability supports continuous evolution but cannot vote a meaning into existence. A proposed Capsule or codec remains content-addressed and passes through `proposed -> trial -> evaluated -> ratified` or `rejected`. During the Experimental Stewardship Phase, the final transition to `ratified` requires explicit Founding Maintainer approval under `GOVERNANCE.md`; no metric, agent vote, funding event, or traffic threshold can substitute for that decision. Promotion evidence requires:

- exact semantic round-trip and migration tests;
- held-out tasks and unseen-partner cross-play across independent implementations;
- no regression at non-compensable safety, authority, provenance, rights, privacy, and rollback gates;
- task economics that beat the incumbent with a preregistered confidence interval;
- acceptable negotiation, fallback, repair, and deprecation behavior over a declared trial cohort;
- published rejection reasons and negative evidence;
- a working fragment or profile rollback path.

Popularity can prioritize which candidate to test, but cannot promote it automatically. Opt-in telemetry is supporting evidence, not a substitute for controlled evaluation. Deprecated definitions remain resolvable by immutable digest for historical interpretation, while telemetry confirms whether active peers received the migration or require continued fallback.

## 18. Failure modes and required responses

| Failure mode | Required response |
|---|---|
| Compilation changes meaning | Reject or mark approximate; retain source anchor; request another compiler or original fragment |
| Source changes after compilation | Mark prior snapshot stale or historical; fetch delta; do not rewrite the old object |
| Origin has no signature | Preserve acquisition evidence and label origin authenticity as unverified |
| Signed source is false | Keep integrity and truth assessments separate; seek independent evidence |
| Conflicting sources | Return a contradiction set with source and time context; do not force consensus |
| Unsupported schema or codec | Fall back for only the affected fragment; keep it non-effectful until validated |
| Prompt injection | Quarantine content, preserve evidence, block policy or effect transition, and report a typed security result |
| Rights are unknown | Restrict storage and redistribution, use ephemeral local processing where allowed, or abstain |
| Paywall or authorization failure | Return `access_denied`; never seek bypass credentials or a public cached copy |
| Deletion or correction arrives | Stop serving, validate authority, propagate tombstone or delta, purge required replicas, report incomplete propagation |
| Shared cache is poisoned | Quarantine signer and affected derivations; replay from source; publish incident scope and recovery evidence |
| Central registry becomes unavailable | Continue with pinned manifests, local trust policy, alternate registries, and direct peer negotiation |
| Profile optimization harms a model | Select a different codec for that peer; do not require one syntax for every tokenizer |
| Semantic cache costs more than reuse saves | Expire or avoid the artifact and use direct retrieval |
| Agent answer hides source diversity | Fail answer-quality policy; expose selection method, omissions, and inspectable alternatives |
| Telemetry is spoofed or biased | Label affected intervals, exclude unverifiable cohorts, publish the correction, and preserve raw aggregate reproducibility |
| Adoption remains zero | Publish zero honestly; improve local utility or stop the promotion claim |

## 19. Non-goals and hard boundaries

- Do not claim that the project has converted, indexed, or replaced the Internet.
- Do not remove direct browsing, source access, or human-readable publishing.
- Do not replace HTTP, TLS, search indexes, storage systems, or modality codecs.
- Do not bypass robots rules, paywalls, authentication, rate limits, copyright, privacy, or deletion duties.
- Do not treat extracted claims, embeddings, or signatures as guaranteed truth.
- Do not make one central cache, registry, trust score, or model mandatory.
- Do not reveal private chain-of-thought or require latent-state exchange.
- Do not let retrieved content authorize actions, install profiles, or modify policy.
- Do not optimize tokens at the expense of meaning, safety, freshness, rights, or safely completed tasks.
- Do not use accidental machine-language leakage, fabricated traffic, or manipulated community metrics as an adoption strategy.

## 20. Success condition

The north star is reached progressively when independent agents can obtain most information needed for ordinary low-risk tasks through source-preserving Urusilla exchanges, users prefer the agent interaction because it is faster and more auditable than manual query iteration, publishers gain value from native semantic updates, and measured total task cost decreases without weakening rights, safety, privacy, or access to original sources.

Even then, retrieval and search remain essential infrastructure. The achievement would be that people no longer need to operate that infrastructure manually for most tasks, and that agents exchange the retrieved meaning in a compact, evolving, interoperable, and inspectable form.
