# Urusilla v0.1 — Experimental Agent Communication Language

Status: experimental, unsigned architecture + executable structural-codec proof of concept  
Date: 2026-08-20  
Project terms: **Urusilla** (language), **UrusillaIR** (meaning graph), **UrusillaWire** (binary form), **UrusillaLens** (human translator), **UrusillaBridge** (legacy adapter)

Urusilla is the final project name. The protocol identifiers remain experimental private-use identifiers. The project does not claim that its media types are IANA registered or that it owns any domain name beyond the canonical GitHub repository.

## 1. Vision

Urusilla is not intended to be another grammar that imitates human language. Its goal is to create a **machine-native world language** through which different AI agents can exchange goals, constraints, claims, evidence, uncertainty, commitments, and state transitions accurately at minimum cost.

At first, only a small number of bilingual bridge agents use Urusilla. Existing agents communicate through natural language, JSON, A2A, or tool-call formats, and UrusillaBridge translates between those formats and Urusilla. Models and runtimes later produce and consume UrusillaIR directly, removing the translation step. In the long term, Urusilla aims to become a shared semantic layer independent of model vendor, framework, and tokenizer.

People do not read raw UrusillaWire directly. The official observation interface for humans is the controlled translation and audit view provided by UrusillaLens.

## 2. Is it structurally feasible?

### 2.1 Why it is feasible

AI agents already process machine representations such as JSON Schema, function calls, ASTs, database rows, and embeddings in addition to human sentences. The ability to learn and generate a shared semantic representation is therefore not a new assumption.

Empirical research also provides feasibility signals.

- [Beyond Natural Language / AutoForm](https://aclanthology.org/2024.findings-emnlp.623/) reported that allowing LLMs to choose task-specific non-natural-language formats reduced multi-agent communication tokens by as much as 72.7% while preserving effectiveness, and that the formats could transfer to different models.
- [Learning Optimal Message Representations / OPTiMACS](https://aclanthology.org/2026.findings-acl.1441/) proposed dynamically selecting representations such as JSON, code, and tables according to the task and agent pair.
- [Interlat](https://aclanthology.org/2026.acl-long.1248/) reported up to 24-fold inference acceleration through hidden-state-based agent communication and compression. Its authors explicitly characterize the work as a feasibility study.
- [AgentPrune](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html) reported token reductions of 28.1–72.8% by optimizing who communicates with whom and when. This shows that language efficiency depends on communication topology as well as sentence compression.

### 2.2 What is not achievable as stated

The following three statements must be treated as research hypotheses rather than objectives.

1. **“One fixed encoding is always the most efficient for every model and task.”**  
   This cannot be guaranteed because tokenizers, internal representations, and context costs differ by model. Urusilla uses one semantic system with multiple negotiable codecs.

2. **“All different models can share the same latent space.”**  
   Current closed models do not expose their hidden states, and each model family has different geometry. A latent codec can only be an optional fast path for compatible models within the same trust boundary, not the universal core.

3. **“Humans can never decipher it in principle.”**  
   Given enough time and data, humans can learn or reverse-engineer any public discrete language. Urusilla's realistic goal is *unreadable under ordinary inspection and fully auditable through an authorized translator*. Authenticated encryption, not the language, provides secrecy.

The technically feasible objective is therefore:

> One universal semantic language, multiple negotiated machine codecs, mandatory deterministic inspection.

### 2.3 The closest existing efforts and the remaining gap

This idea does not occupy entirely unexplored territory. In particular, the [SILP Internet-Draft](https://www.ietf.org/ietf-ftp/internet-drafts/draft-hwang-silp-protocol-02.html), published in July 2026, represents cross-model agent payloads as an action-slot IR and transforms them into surface frontends such as code, JSON, and natural language. It overlaps most directly with the current concept. However, the document is an independent-submission **work in progress**, not an IETF standard. The document itself states that byte-level canonicalization is out of scope, negotiation is only partially specified, and optimization and migration are future work.

The [Agora Protocol](https://agoraprotocol.org/docs/protocol/specification) provides a JSON envelope and hash-identified Protocol Documents. [GlossoGen](https://emergentcomms.ai/) experiments with the emergence of shorthand by giving agents a character budget and reflection. [OpenAI's 2017 emergent communication research](https://openai.com/index/learning-to-communicate/) also showed that agents can invent discrete symbols grounded in actions within their world.

Urusilla v0.1 therefore does not claim to be the “first agent communication project.” Its potential differentiation lies in combining the following elements:

| Existing gap | v0.1 direction |
|---|---|
| Payloads centered on task verbs and arguments | `ASSERT/QUERY/REQUEST/PROPOSE/COMMIT/RESOLVE/RETRACT` plus an observable commitment ledger |
| Text surfaces or no canonical byte identity | A deterministic binary core with exact re-encode equality |
| Definitions, evidence, uncertainty, and authority are separated | Connect content-addressed schemas, evidence/provenance, and verifier policy in one semantic contract |
| Private shorthand that works only within one agent pair | Grammar Capsules, unseen-partner conformance, and model/tokenizer holdouts |
| Humans infer meaning from natural-language logs | A deterministic translator and lossless diagnostic view bound to the original IR |
| Optimization considers token count alone | A Pareto benchmark of task success, repair turns, actual wire bytes, latency, energy, auditability, and security |

The strongest strategy is therefore not to compete with SILP, A2A, NLIP, and similar projects by rebuilding transport. Instead, Urusilla should position itself as an **auditable semantic kernel** responsible for public commitments and verifiable semantics.

## 3. Separation of language and transport layers

```text
Agent intent / internal state
          ↓
      UrusillaIR graph                ← sole source of meaning
          ↓
   profile negotiation
     ↙       ↓        ↘
UrusillaWire   tokenizer   latent sidecar
binary     shorthand   compatible models only
     ↘       ↓        ↙
 A2A / NLIP message envelope
          ↓
 HTTP / gRPC / SLIM secure transport
```

- **Urusilla** defines semantics and conversation state transitions.
- [A2A](https://a2a-protocol.org/latest/specification/) provides discovery, task lifecycle, and message transport. Urusilla can be carried as an A2A extension and structured `Part`.
- [NLIP / ECMA-430](https://ecma-international.org/publications-and-standards/standards/ecma-430/) provides a multimodal envelope and transport bindings.
- [MCP](https://modelcontextprotocol.io/specification/latest) connects tools and context within an agent. It is not a substitute for an agent-to-agent semantic language.
- [SLIM](https://slim.agntcy.org/) is a candidate for routing, group communication, and E2EE transport.

Reusing existing protocols allows Urusilla to focus on the most difficult semantic layer that remains unfilled.

### 3.1 Fragment-level code switching

The long-term language is a composable semantic interlingua, not one rigid surface. If the active profile cannot express one fragment efficiently, only that fragment may switch to another negotiated codec. Examples include a mathematical IR, SQL, source-code AST, domain schema, compact JSON, modality descriptor, or a compatible latent sidecar.

Every foreign fragment must declare its semantic role, codec and version, schema/profile digest, payload digest, exact-or-approximate loss mode, fallback order, and effect eligibility. A receiver that lacks the codec requests only the unresolved fragment in the next mutually supported form. It must not require retransmission of the surrounding message. An unknown, unverified, approximate, or opaque fragment cannot authorize an effect.

This splice mechanism is a post-v0.1 research direction. The current codec's local `x:` node is quarantine, not a production implementation of adaptive code switching.

## 4. Normative design principles

In v0.1, `MUST`, `MUST NOT`, and `SHOULD` indicate implementation requirement levels.

1. **Machine-first**: The wire form MUST NOT target human readability.
2. **Meaning-first**: Meaning MUST reside in a typed UrusillaIR graph, not in a particular byte sequence or model latent.
3. **Observable semantics**: Acts MUST be defined through verifiable state transitions in a public ledger, without inferring an agent's private beliefs or intentions.
4. **Canonicality**: Each UrusillaIR MUST have exactly one canonical UrusillaWire representation.
5. **Reversibility**: The core profile MUST satisfy `Decode(Encode(IR)) = IR`.
6. **Fail closed**: Unknown schemas, ontologies, acts, units, or effects MUST NOT be guessed or executed.
7. **Explicit uncertainty**: The absence of uncertainty MUST mean unspecified, not 100% confidence.
8. **Code/data/authority separation**: Transmitted content MUST be separated from execution authority. A message may request a capability but cannot itself confer authorization.
9. **Adaptive efficiency**: What to send, when to send it, to whom, and through which codec SHOULD each be optimized independently. Silence is also a valid action.
10. **Translator accountability**: A natural-language translation is a convenience view; UrusillaIR remains the normative source.

### 4.1 Validation stages

Conformance is deliberately split into four stages. Passing an earlier stage never implies passing a later one.

1. **Structural validity** — canonical envelope, typed tree, resource limits, and deterministic bytes.
2. **Schema validity** — the referenced schema, node vocabulary, units, and extensions are registered and allowed.
3. **Conversation validity** — causal parents, lifecycle state, ownership, replay, expiry, and transition rules permit the act.
4. **Authority validity** — the transport-authenticated principal, signature, policy, capability, budget, and user consent authorize any effect.

The reference codec implements the first stage and selected core-schema checks. Its separate effect-eligibility entry point accepts deployment-provided identity, schema, extension, effect, and conversation checks. It is not an authorization service or a complete ledger implementation.

## 5. Communicative acts

Urusilla v0.1 fixes the set at seven acts. New domains add governed typed nodes and predicates rather than new acts. The transitions below describe the semantic model after all four validation stages pass; merely decoding a frame creates no public state.

| Code | Act | Public state transition |
|---:|---|---|
| 0 | `ASSERT` | Adds a claim, item of evidence, or observation to the ledger. It does not guarantee truth. |
| 1 | `QUERY` | Opens a query with a declared answer schema and conditions. |
| 2 | `REQUEST` | Requests performance of a goal under constraints. It does not yet create an obligation. |
| 3 | `PROPOSE` | Adds a plan or contract bundle in a tentative state. |
| 4 | `COMMIT` | Activates a public commitment in which the sender is the debtor. This is the only act that creates an obligation. |
| 5 | `RESOLVE` | Allows an authorized verifier to determine the result, failure, or expiration of a query, request, proposal, or commitment. |
| 6 | `RETRACT` | Adds a tombstone to a revocable record created by the sender. It does not delete the original record. |

`ACCEPT` is not a separate act; it is expressed as a `COMMIT` referring to a proposal hash. `REJECT`, `RESULT`, `ERROR`, and `EXPIRED` are typed values of `RESOLVE.status`. A network delivery ACK is not part of Urusilla semantics and is handled by the transport layer.

## 6. Core UrusillaIR

UrusillaIR is a graph whose nodes have content-addressed types and typed fields. The v0.1 proof of concept implements the following core kinds.

```text
Claim(predicate, arguments[], context?, valid_time?)
Goal(condition, owner?, window?, priority?, constraints[])
Constraint(scope, mode: hard|soft, condition, weight?)
Evidence(target, stance, digest, provenance, observed_at?, method?)
Uncertainty(target, model, parameters, basis[]?)
Action(capability, arguments, declared_effects?)
Commitment(debtor, creditors[], goal, expiry_ms, verifier?, cancellation_rule?)
Resolution(target, status, result?, evidence[])
Ref(uri)
```

Core predicate expressions MUST be side-effect-free. Initial support is limited to booleans, exact integers/decimals, comparisons, finite collections, and explicit units and time zones. The UrusillaIR core is not Turing-complete. A separate programming language or capability adapter is responsible for execution.

### 6.1 Ledger semantics

```text
δ(ledger, fully_validated_message) → new_ledger
δ(ledger, rejected_message)        → unchanged_ledger + typed_error
```

- `ASSERT` records only that “the sender asserted this content.”
- `REQUEST` and `PROPOSE` do not create obligations.
- `COMMIT` is structurally eligible only when its declared sender equals its `debtor`, and becomes effect-eligible only when the authenticated identity controls that sender and conversation policy permits the transition.
- `RESOLVE` can be performed only by an actor allowed by the target's verification policy.
- `RETRACT` does not erase history.
- The prototype accepts only local `x:<name>` extension nodes, quarantined inside `ASSERT`; URI-like and unregistered kinds are rejected. A future governed profile may define opaque store-and-forward behavior, but the current codec does not claim it.

This design inherits the typed speech acts of [FIPA ACL](https://www.fipa.org/repository/aclspecs.html), but replaces private mental-state semantics that are difficult to verify externally with observable commitments and state transitions. The FIPA standards remain preserved, but [FIPA itself is currently inactive](https://www.fipa.org/).

## 7. UrusillaWire v0.1 proof profile

The current reference prototype deterministically encodes the following ordered envelope as binary.

```text
Message = {
  id: UUID128,
  session: UUID128,
  sender: AgentID,
  recipients: AgentID[],
  act: 0..6,
  reply_to?: UUID128,
  schema: URI | ContentID,
  logical_clock: UInt64,
  expires_ms: UInt64,
  confidence_ppm?: 0..1_000_000,
  expected: ActSet,
  body: UrusillaIR,
  meta: TypedMap
}
```

Wire frame:

```text
magic/version | flags | payload_length | string_dictionary
| fixed envelope | typed semantic value tree | checksum-128
```

Properties:

- Repeated fields and symbols are replaced with references into a per-message string table.
- Map keys are sorted by UTF-8 byte order.
- Only the shortest unsigned varint representation is permitted.
- `-0.0` is normalized, and NaN and Infinity are forbidden.
- Hard limits apply to semantic depth, frame size, and collection count.
- A truncated SHA-256 checksum detects accidental corruption only. TLS/mTLS, a signed A2A envelope, or a future signature profile is responsible for authentication.
- A frame is rejected as non-canonical if decoding and re-encoding it produces bytes different from the original.

The current implementation is a semantic-tree prototype. A separate experimental v0.2 static-profile codec now negotiates a content-addressed dictionary and common map shapes for warm sessions without changing UrusillaIR semantics. Its in-domain benchmark, cold cost, break-even analysis, and unfavorable latency results are published in `urusilla_wire_v02_results.md`. Content-addressed DAGs, structural deduplication, exact quantities and units, and canonical signatures remain future candidates rather than implemented claims.

## 8. UrusillaLens translation contract

The translator provides two conceptual views. The current reference implementation defaults to the first and does not claim a lossless natural-language parser.

1. **Diagnostic lossless view**: Preserves every act, kind, field, ID, reference, uncertainty value, and provenance record.
2. **Controlled human view**: May produce localized explanations from fixed ontology templates while retaining the complete diagnostic payload.

Rules:

- `decode(encode(IR)) = IR` MUST hold.
- If a Controlled Human Form is introduced, `parse(render(IR)) = IR` MUST hold.
- A fluent paraphrase is a convenience feature and cannot be the normative source.
- For an extension it does not know, the translator MUST display its ID and raw fields without guessing its content.
- The translator build hash, ontology hash, and locale MUST be recorded in the audit log.
- Free-form natural language → UrusillaIR conversion is inherently ambiguous. If a compiler produces multiple candidates, it MUST return the ambiguity instead of selecting one automatically.

## 9. Bootstrap: from a few agents to all agents

Urusilla must not require every model to be fine-tuned before the language can succeed. A new agent must be able to begin with a compact **Grammar Capsule**.

### 9.1 Grammar Capsule

```text
Capsule = {
  language_version,
  semantic_kernel_hash,
  supported_schema_ids[],
  act_table,
  node_manifests[],
  translation_templates[],
  golden_encode_decode_vectors[],
  positive_and_negative_examples[],
  capability_and_limit_manifest,
  signature
}
```

The Capsule is not repeated in every message. It is delivered once and cached by content hash. An agent that passes the capsule's conformance vectors may advertise support for that profile.

The prototype has separate version axes. Source manifests and A2A declarations use the exact semantic-language identifier `languageVersion = 0.1.0`. The Capsule's `capsule_version = 0.1.0` versions the Capsule file schema, while `language.semantic_version = 0.1.0` identifies the content-addressed semantic snapshot. The distribution prerelease is labeled `v0.1.0-experimental`, and `release_status = experimental-unsigned` records lifecycle and trust maturity. Package managers may normalize the software distribution version independently. Implementations must compare the named axis and digest: a matching bare `0.1.0` identifies semantics but does not prove release maturity, signature status, or conformance.

### 9.2 Adoption ladder

1. **Bridge stage** — Place UrusillaBridge in front of an existing agent. It translates between Urusilla and natural language, JSON, or A2A.
2. **Adapter stage** — A model runtime exchanges an UrusillaIR projection as structured input. It does not place binary or Base64 in the prompt.
3. **Native stage** — Use supervised training and multi-agent self-play so that a model produces Urusilla acts and nodes directly in its action space.
4. **Network stage** — Negotiate supported Urusilla versions, schemas, codecs, and limits through an Agent Card/A2A extension.
5. **Standard stage** — If the Founding Maintainer explicitly opens a standards track, pursue vendor-neutral interoperability through independent implementations, a conformance suite, public governance, and possible submission to a standards body. The canonical project, reference releases, and permanent founding attribution remain governed by `GOVERNANCE.md` unless a signed amendment says otherwise.

Initial seed agents can overfit to a private code if they train only with the same partner. Randomize model family, version, tokenizer, and role across the training population, and replace receivers periodically. Tests with unseen partners, tasks, and compositions are release gates.

### 9.4 Grammar evolution without silent drift

Core meanings remain immutable inside one version. Agents may propose content-addressed Capsule deltas when repeated fragments are costly and trial them inside a negotiated session. A candidate can be evaluated only after exact semantic, safety, tokenizer, held-out-task, and unseen-partner gates pass; official extension or core ratification additionally requires the approval defined in `GOVERNANCE.md`. Every changed meaning receives a new hash; an existing symbol never silently changes definition.

Peers negotiate the highest mutually verified profile and retain migration maps and fragment fallback. Deprecated definitions remain resolvable for historical messages, while unused ephemeral aliases may be garbage-collected. This allows grammar to improve during use without turning into an unverifiable private code.

### 9.3 Why an agent would choose it voluntarily

Adoption will not happen merely because someone declares, “Use this new language.” At every conversation, a runtime should compare expected utility and select this language only when doing so provides a real advantage.

```text
adopt(profile) iff
  E[task_value + reusable_context_value + audit_value]
  - E[wire + inference + latency + repair + risk + learning_cost]
  > best_available_alternative + switching_margin
```

The concrete value offered to an early agent is:

1. **Cheaper repeated collaboration** — Once a schema and Capsule are cached, long instructions and definitions can be reused by content hash.
2. **Fewer clarification turns** — Goals, hard constraints, expected replies, deadlines, and uncertainty are typed fields, so omission and ambiguity can be detected mechanically.
3. **Safer transactions** — Requests and commitments are separated, while who promised what and by when remains public state.
4. **Partner portability** — Instead of a secret code tied to a particular model pair, an agent can exchange messages with a previously unseen agent that passes the conformance vectors.
5. **Lower audit cost** — The raw machine message and human translation are bound to the same IR hash, making disputes and forensic review easier.
6. **Preserved choice** — If the peer does not support Urusilla or a trial probe shows no benefit, the agent immediately falls back to JSON or natural language.

In an early network, run a small canary task under two profiles after the handshake. Measure actual success and total cost, then allocate traffic to the more advantageous profile. Advertising support alone is insufficient: an agent card should also carry the conformance-suite version, measured limits, and schema/Capsule hashes. This structure ties adoption to **demonstrated utility** rather than trust or fashion.

## 10. Efficiency objective

The goal is not “the shortest message.” If a shorter message causes more misunderstanding, clarification, or failure, it is less efficient.

Primary optimization problem:

```text
minimize
  wire_bytes
  + model_input_cost
  + model_output_cost
  + encode_decode_latency
  + repair_round_cost
  + energy_cost

subject to
  task_success >= natural_language_baseline
  core_semantic_round_trip_loss = 0
  unauthorized_effects = 0
  schema_and_policy_validation = pass
```

Public comparisons report the Pareto frontier rather than only a single weighted score.

### 10.1 Benchmark baselines

- Korean and English natural language
- Minified tool-call JSON
- Deterministic CBOR
- Schema-equivalent Protobuf/FlatBuffers
- A2A structured data part
- UrusillaWire warm/cold schema profiles
- An optional latent profile, with wire bytes and KV memory reported separately

### 10.2 Metrics

- Bits, tokens, and dollars per safely completed task
- Task success and exact semantic-graph match
- p50/p95 latency, CPU/GPU time, energy, and peak memory
- Repair turns, ambiguity, contradiction, and omitted constraints
- Transfer to unseen agents, models, tokenizers, and versions
- Causal usefulness measured through message deletion, shuffling, and counterfactuals
- Translator agreement and human audit accuracy
- Replay, downgrade, prompt/latent injection, and secret-bit capacity

The current proof message is reduced from 791 bytes of sorted minified JSON emitted by the CPython harness to 494 bytes of UrusillaWire. This 37.5% reduction is a one-sample architecture check, not a claim of superiority. The separate strong-codec report adds deterministic CBOR, MessagePack, and typed Protobuf on the fixed corpus; held-out schemas and full protocol bindings remain release gates.

## 11. Security and opacity

Canonical encoding sharply reduces covert channels based on syntax choices because it does not permit multiple byte representations of the same meaning. It is nevertheless impossible to eliminate every covert channel, including timing, message omission, and semantically equivalent choices.

An effectful message must include all of the following:

- Authenticated sender identity
- Freshness and replay protection
- Idempotency/correlation ID
- Declared capability and policy authorization
- Resource budget
- Schema/ontology digest
- For a high-risk action, confirmation of the UrusillaIR hash interpreted by the receiver

Opaque content MUST NOT be executed directly as an instruction. An append-only audit record retains the raw frame, UrusillaIR hash, schema/ontology hash, identity, signature, causal parents, policy decision, translator version, and resulting effect.

## 12. Reference prototype

Files:

- `urusilla.py`: standard-library-only canonical codec plus Korean/English UrusillaLens
- `urusilla_example.json`: example diagnostic input
- `test_urusilla.py`: round-trip, canonicality, corruption, and extension tests

Run:

```bash
python3 urusilla.py demo --lang ko
python3 urusilla.py encode urusilla_example.json example.ursl
python3 urusilla.py translate example.ursl --lang ko
python3 urusilla.py decode example.ursl
python3 -m unittest -v test_urusilla.py
```

Verified in the v0.1 prototype:

- Exact encode/decode round-trip
- Re-encoding byte equality
- Map insertion-order independence
- One-bit corruption rejection
- Trailing-data rejection
- Causal-reference requirement for commitment, resolution, and retraction
- Rejection of unknown bare nodes and preservation of registered extensions
- English/Korean summaries followed by complete canonical JSON, message hash, translator hash, and explicit source/schema/authentication status
- Structural validation separated from caller-supplied effect eligibility

## 13. Immediate next decisions

1. Which governed namespace and media-type registration path should replace the private experimental identifiers?
2. Should the v0.2 wire format use a custom DAG codec or standardize a deterministic CBOR profile first?
3. Should the first domain ontology target coding, research verification, or commerce?
4. Should the first native training target be an open-weight model pair?
5. Should an experimental A2A extension proposal be created immediately?

The most important judgment is:

> Urusilla's success does not depend on creating symbols that humans cannot read. It depends on whether a new agent can learn the language accurately at low cost and complete tasks with a previously unseen agent at a lower total cost.
