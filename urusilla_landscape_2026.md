# Global Landscape for an Agent-Native Communication Language

**Project:** Urusilla  
**Landscape date:** 20 August 2026  
**Evidence policy:** Primary and official sources only  
**Scope:** Agent communication languages, semantic intermediate representations, adaptive message formats, emergent communication, and latent agent-to-agent channels

## Executive decision

Building this system is structurally possible, but the defensible product is not “a secret language that all AIs will eventually speak.” The defensible product is an **open, model-independent semantic payload layer** that agents adopt because it improves the cost, fidelity, safety, and auditability of repeated coordination.

The market is already crowded at every neighboring layer:

- KQML and FIPA ACL established performatives, content languages, ontologies, and interaction protocols decades ago.
- A2A, NLIP, MCP, ANP, OASF, and SLIM now cover much of the envelope, discovery, capability, tool, and transport stack.
- SILP, published as an independent Internet-Draft in July 2026, already proposes an action-slot semantic interlingua, several pluggable frontends, lossless round trips, frontend negotiation, and embedding in A2A or MCP.
- The W3C Semantic Agent Communication Community Group is explicitly pursuing semantic intent, delegation, identity binding, and execution accountability.
- Agora, AutoForm, OPTiMACS, and PACT already demonstrate negotiated, selected, learned, or compact action-state communication approaches.
- Cloclo's active AICL protocol already uses a compact inter-agent language for ownership, intent, state changes, hypotheses, evidence, confidence, constraints, actions, and handoffs.
- Tokenese tested the premise that a designed text interlingua would beat prose, measured its flagship syntax at about 1.3 times the token cost of terse English, found no adoption signal, and archived the project in July 2026.
- Latent communication systems show that agents can exchange hidden states or KV caches, although current approaches are usually model-coupled and difficult to audit.

Consequently, the project cannot honestly claim to be the first agent language, the first semantic interlingua, the first negotiated codec, the first machine-only language, or the first content-addressed agent vocabulary.

Tokenese supplies especially important negative evidence. A novel alphabet or exotic surface syntax is not inherently efficient for current LLMs: BPE tokenizers are trained on natural text and often split unfamiliar glyph sequences badly. The project must create value in the semantic IR, public effect model, runtime validation, canonical binary channel, and adaptive profile selection—not in decorative symbols. Terse English is a mandatory baseline.

There is still a credible gap, but it is a **combination gap** rather than an untouched category:

1. a richer typed meaning graph spanning claims, goals, constraints, evidence, uncertainty, actions, commitments, and resolutions;
2. public, observable state-transition semantics instead of semantics defined by unobservable beliefs or intentions;
3. canonical, hashable wire bytes with fail-closed schema and vocabulary agreement;
4. deterministic, controlled human translation as a normative conformance surface;
5. transport independence and explicit bindings to the protocols that already have distribution;
6. evaluation by **bits per safely completed task**, including failures, repair turns, verification, and audit cost.

No reviewed project in this landscape clearly delivers all six as one interoperable system. Several deliver two or three. That makes the project a **conditional go**: proceed only after narrowing the claim and proving the combined value against SILP and ordinary structured A2A/NLIP payloads.

## 1. What kind of system can win?

### 1.1 The viable architecture

A universal agent ecosystem will remain heterogeneous. Agents will use different foundation models, tokenizers, context policies, vendors, modalities, security domains, and upgrade cycles. A single opaque surface code is therefore less plausible than a stable semantic core with negotiated encodings.

The viable position is:

```text
Human inspection and governance
        |  deterministic controlled rendering
        v
Typed semantic IR and observable conversation effects    <- target layer
        |  canonical bytes / negotiated text codec / optional latent profile
        v
A2A or NLIP envelope; ANP discovery and negotiation
        |  SLIM, HTTP, WebSocket, gRPC, or another transport
        v
Models, agent runtimes, tools, and organizations
```

This architecture treats the language as an **interlingua and conformance contract**, not as a replacement for every networking layer. MCP remains a tool and context interface; A2A or NLIP can carry messages; ANP and OASF can describe agents and capabilities; SLIM can move encrypted traffic; the new language supplies a shared, testable meaning layer.

### 1.2 Why deliberate human unreadability is the wrong objective

An agent-oriented wire format may be inconvenient for a person to read directly, just as bytecode is. That can be an outcome of compact typing and canonical encoding. It must not be the security model or the main value proposition.

Deliberately hiding meaning from humans creates four problems:

- it weakens incident response, accountability, and regulatory acceptance;
- an opaque code can conceal prompt injection, collusion, policy evasion, or data exfiltration;
- a code optimized for one tokenizer or model family may become inefficient after a model update;
- agents that have not learned the code cannot participate without a bridge, reducing network effects.

The better contract is: **machine-native on the wire, deterministically inspectable by authorized humans**. A normative translator should expose acts, entities, constraints, uncertainty, provenance, and expected state changes without asking another probabilistic model to paraphrase them.

### 1.3 Classification used in this report

| Class | Meaning in this report |
|---|---|
| Direct or adjacent competitor | Occupies the semantic payload, agent-language, adaptive-format, or protocol-negotiation layer that the project would otherwise claim |
| Complementary infrastructure | Solves discovery, transport, envelopes, tools, identity, capability description, or deployment and should normally be integrated rather than replaced |
| Research precedent | Demonstrates that learned, emergent, compressed, or latent communication is possible, but is not yet a general interoperable language standard |

“Standard,” “specification,” “draft,” “paper,” and “prototype” are not interchangeable maturity labels. In particular, an Internet-Draft is work in progress, and a W3C Community Group output is not a W3C Standard unless it later enters and completes the Recommendation Track.

## 2. Landscape at a glance

| Project or family | Primary purpose | Maturity on 20 Aug 2026 | Relationship to the target language | Most important implication |
|---|---|---|---|---|
| [KQML](https://research.cs.umbc.edu/kqml/papers/) | Performative-based knowledge exchange | Historical specification and research lineage | Research precedent with direct conceptual overlap | “Typed agent speech acts” is a decades-old idea |
| [FIPA ACL](https://www.fipa.org/repository/aclspecs.html) | Standard agent communicative acts, envelopes, content language, ontology, and protocols | Published FIPA specifications, including standard acts | Historical direct precedent | The project must distinguish observable effects from FIPA’s mental-attitude semantics |
| [A2A](https://a2a-protocol.org/latest/specification/) | Agent discovery, task lifecycle, messages, artifacts, streaming, and bindings | Linux Foundation specification; 1.0 family released in 2026 | Complement with limited payload overlap | Ship as an A2A extension or structured Part, not a rival task transport |
| [MCP](https://modelcontextprotocol.io/specification/latest) | Model or application access to tools, resources, prompts, and context | Widely implemented open protocol; 2026 stateless core | Complement | Use for tool bridges; do not describe MCP as a general agent semantic language |
| [NLIP / ECMA-430–434](https://ecma-international.org/publications-and-standards/standards/ecma-430/) | Universal multimodal agent/human envelope over several transports | Ecma standards adopted December 2025 | Adjacent competitor and possible carrier | It already owns a strong “universal agent communication” claim, while leaving most domain meaning endpoint-defined |
| [SILP -02](https://www.ietf.org/ietf-ftp/internet-drafts/draft-hwang-silp-protocol-02.html) | Cross-model semantic IR with pluggable text frontends | Independent Informational Internet-Draft; work in progress | Closest direct specification competitor | The project must not repeat SILP’s action-slot IR, frontend negotiation, or A2A/MCP embedding as its novelty |
| [ANP](https://agentnetworkprotocol.com/en/specs/) | Open agent network, identity, discovery, secure messaging, semantic protocol negotiation | Open specifications and unreleased drafts | Adjacent competitor at the negotiation plane; complement elsewhere | Reuse or interoperate with ANP negotiation rather than creating an isolated handshake |
| [W3C AI Agent Protocol CG](https://www.w3.org/groups/cg/agentprotocol/) | Web-native discovery, identity, collaboration, roles, metadata, security, and interoperability | Community Group; not a W3C Standard | Governance neighbor and complement | Align metadata and Web identity; avoid claiming W3C endorsement |
| [W3C Semantic Agent Communication CG](https://www.w3.org/groups/cg/s-agent-comm/) | Ontologies for semantic intent, delegation, identity binding, capability, and execution accountability | Community Group; not a W3C Standard | Closest semantic standards competitor | A large part of the proposed semantic-accountability story already has a standards forum |
| [AGNTCY OASF](https://github.com/agntcy/oasf) | Agent record, skill, domain, and module schemas and taxonomies | Open-source schema framework | Complement with ontology overlap | Import its capability taxonomy instead of building a second registry |
| [AGNTCY SLIM](https://github.com/agntcy/slim-spec) | Secure low-latency messaging and group communication for agents | Open specification and implementation | Complement | A suitable data plane; semantic payloads can remain opaque to routing |
| [Agora](https://arxiv.org/abs/2410.11905) | LLM-negotiated protocols and reusable routines for mid-frequency interactions | Research paper and prototype | Direct research competitor | Dynamic negotiation and cached protocol artifacts are already demonstrated |
| [AutoForm](https://aclanthology.org/2024.findings-emnlp.623/) | Let models select communication/reasoning formats | Peer-reviewed research and code | Research competitor | Format selection can reduce tokens without inventing a universal language |
| [OPTiMACS](https://aclanthology.org/2026.findings-acl.1441/) | Learn task-aware optimal message structures | Peer-reviewed research | Research competitor | The best surface representation may be task-dependent rather than globally fixed |
| [PACT](https://arxiv.org/abs/2606.05304) | Replace full dialogue histories with public action, state, and result records | Preprint and partial artifact | Direct compact-state comparator | It reports task-level token reductions, but requires clean-room same-driver reproduction before comparison |
| [AgentDropout](https://arxiv.org/abs/2503.18891) | Prune low-value agents and communication edges | Preprint | Topology-efficiency comparator | Suppressing a message can dominate compressing it |
| [Cloclo / AICL](https://github.com/SeifBenayed/cloclo/blob/main/AICL.md) | Compact runtime-native inter-agent language for cooperative work | Active open specification inside a working multi-agent runtime | Direct implementation competitor | Ownership, intent, evidence, confidence, state, constraints, action, and handoff are already occupied concepts |
| [Tokenese](https://github.com/snapsynapse/tokenese) | Designed token-native LLM interlingua | Archived 25 July 2026 with measured post-mortem | Direct failed predecessor and negative evidence | Its symbolic syntax cost about 1.3x terse English in the flagship audit; semantic structure and below-text optimization matter more than exotic glyphs |
| [EcoLANG](https://arxiv.org/abs/2505.06904) | Evolve compressed textual language in social simulations | Preprint | Research precedent | Selection pressure can produce shorthand, but domain-specific success is not interoperability |
| [GlossoGen](https://emergentcomms.ai/) | Experimental platform for observing constrained agent communication | Open prototype and experiment platform | Complementary evaluation tool and research precedent | It can test language emergence, portability, decipherability, and oversight under controlled budgets |
| [LatentMAS, Interlat, SDE, C2C, KVComm, DiffMAS](#6-latent-and-hidden-state-communication) | Hidden-state, KV-cache, or learned latent communication | Rapid research frontier | Optional research profile, not a universal core | Strong local efficiency does not remove model coupling, audit, or open-API constraints |
| [Eclipse LMOS](https://eclipse.dev/lmos/docs/category/lmos-protocol/) | Agent metadata, discovery, identity, and communication using Web standards | Open-source protocol stack | Complement | Its own SDK documentation anticipates a standardized interoperable communication data model |
| [ADOL](https://www.ietf.org/archive/id/draft-chang-agent-token-efficient-01.html) | Token-efficient schema and reference layer for A2A/MCP data | Expired independent Internet-Draft | Complementary optimization precedent | Reuse schema deduplication and controllable verbosity ideas; it does not define semantics |
| [GibberLink](https://github.com/PennyroyalTea/gibberlink) | Switch two voice agents to an acoustic data modem | Demonstration | Neither semantic competitor nor emergent-language evidence | It is a transport-mode demo, not a machine-created language |

## 3. Direct and adjacent competitors

### 3.1 SILP: the closest specification-level collision

The July 2026 [Semantic Interlingua Layer Protocol -02](https://www.ietf.org/ietf-ftp/internet-drafts/draft-hwang-silp-protocol-02.html) is the most important comparison. It is an independent submission, intended as Informational, and explicitly says it is not an IETF standard. It was published on 21 July 2026 and expires on 22 January 2027. Its status must therefore be described as **work in progress**, not as an adopted IETF protocol.

SILP nevertheless overlaps substantially with the proposed product:

- a model-independent reference IR;
- a coarse action-slot structure containing an action, entities, constraints, alternatives, and metadata;
- code-like, JSON, natural-language, hybrid, and compressed-text frontends;
- semantic round-trip guarantees for lossless frontends;
- dynamic frontend negotiation and session heartbeat;
- an action verb whitelist tested across six tokenizers;
- explicit embedding in A2A, MCP, or AIDIP payload fields;
- a black-box text interface rather than required access to model internals.

SILP also defines useful boundaries. It does not replace transport, lifecycle management, or discovery. Its lossless guarantee is semantic equivalence of decoded IR, not canonical byte identity. Natural-language and lossy frontends cannot provide the same guarantee. Optimization and migration layers remain future work.

The strongest defensible differences for the proposed project are these:

| Dimension | SILP -02 | Potential target position |
|---|---|---|
| Semantic scope | Coarse action-slot intent | General typed graph for claims, evidence, uncertainty, constraints, goals, actions, commitments, and resolutions |
| Conversation effects | Request-oriented metadata and sequences | Normative public ledger transitions for commitments, retractions, resolutions, and failures |
| Canonicalization | Semantic round trip for selected text frontends; no single canonical byte form | One canonical hashable wire representation plus explicitly non-canonical convenience renderings |
| Unknown fields | Root schema is strict, but several submodels allow extensions and receivers silently ignore unknown fields | Fail closed when an unknown field could alter meaning, authorization, obligation, or safety |
| Human inspection | Auditable text frontends | Normative deterministic controlled-language lens with conformance tests |
| Vocabulary | Small action verb whitelist | Versioned, content-addressed vocabulary and domain profiles, preferably interoperable with existing ontology work |
| Evaluation | Fitness factors include task success, compression, readability, tokenizer variance, and ambiguity | End-to-end bits per safely completed task, including repair, verification, policy, and audit cost |

These differences are plans, not validated advantages. The first benchmark must compare the project directly with SILP JSON and code frontends. If the richer IR does not improve high-stakes coordination enough to justify its complexity, SILP or ordinary structured payloads are the more rational choice.

### 3.2 W3C semantic and protocol community groups

The [W3C Semantic Agent Communication Community Group](https://www.w3.org/groups/cg/s-agent-comm/), created on 13 November 2025 according to the official [W3C API record](https://api.w3.org/groups/cg/s-agent-comm), states that it is developing ontology and semantic structures for agents acting as delegated and accountable technical principals. Its scope includes identity binding, capability disclosure, semantic intent, structured delegation chains, and verifiable execution accountability, extending RDF, Linked Data, DIDs, and Verifiable Credentials.

This is direct overlap with any claim that the new project uniquely introduces semantic intent, delegation, provenance, or accountability. It also has a governance advantage: alignment with established Web semantics and trust primitives.

The [W3C AI Agent Protocol Community Group](https://www.w3.org/groups/cg/agentprotocol/), created on 8 May 2025 according to its [W3C API record](https://api.w3.org/groups/cg/agentprotocol), has a broader Web-agent scope: discovery, identity, exchange of intent and capability information, role negotiation, dynamic collaboration, capability/interface/goal/state metadata, security, and protocol interoperability. It is more complementary to the target payload layer, although its intent and metadata work touches the same boundary.

Neither group should be called a W3C standard. W3C’s own [Community Group FAQ](https://www.w3.org/community/about/faq/) says Community Groups do not create W3C standards; their work may later transition to the Recommendation Track.

The strategic response should be participation, not parallel isolation:

- map every core IR type to RDF-compatible semantics where practical;
- reuse DID and Verifiable Credential bindings instead of inventing agent identity;
- submit the observable commitment and resolution model as a concrete contribution or implementation experiment;
- publish conformance vectors and deterministic renderings that the ontology work may lack;
- keep a compact canonical wire profile while allowing a lossless RDF representation.

The unique opportunity here is not to “beat W3C.” It is to become a useful implementation and measurement layer for the semantic work that the Community Group is already organizing.

### 3.4 Agora and ANP: negotiated protocols already exist

The [Agora paper](https://arxiv.org/abs/2410.11905) frames an Agent Communication Trilemma among versatility, efficiency, and portability. Its architecture uses natural language for rare interactions, established protocols for frequent ones, and LLM-negotiated protocols for the middle. Agents can negotiate a protocol and generate reusable routines, then communicate through those routines without invoking an LLM for every conversion. The accompanying [official prototype](https://github.com/agora-protocol/paper-demo) demonstrates heterogeneous agents.

Agora is a direct research competitor to any adaptive language that negotiates and caches grammar or code artifacts. Its advantage is pragmatic: repeated interactions amortize negotiation cost. Its limitations create room for a more normative layer:

- generated routines introduce sandboxing, supply-chain, and equivalence risks;
- task-specific code does not itself define universal claims, evidence, uncertainty, or commitments;
- protocol correctness may depend on LLM-generated implementations;
- human audit and public effect semantics are not the primary abstraction.

The [ANP specification family](https://agentnetworkprotocol.com/en/specs/) aims at an open “Agentic Web.” Its [agent communication meta-protocol draft](https://github.com/agent-network-protocol/AgentNetworkProtocol/blob/main/06-anp-agent-communication-meta-protocol-specification.md) uses structured negotiation to select an interface, profile, schema, security mode, content type, execution mode, and protocol artifact, with natural-language fallback and caching. The draft explicitly does not define business semantics or a new wire language.

ANP therefore occupies much of the proposed negotiation control plane. The new project should define an ANP-negotiable semantic profile rather than inventing an incompatible discovery and negotiation protocol. If its own handshake remains necessary for canonical schema-root agreement, the boundary should be explicit:

- ANP answers **which protocol/profile can we use?**
- the semantic layer answers **which exact schema and vocabulary roots make this message meaningful?**

### 3.5 NLIP: an adopted universal envelope with deliberately open meaning

[ECMA-430](https://ecma-international.org/publications-and-standards/standards/ecma-430/) defines the Natural Language Interaction Protocol as an application-level protocol between agents or between humans and agents. Ecma adopted a suite in December 2025: the core, HTTP/HTTPS, WebSocket, AMQP, and security profiles, plus an explanatory report. Ecma describes a multimodal envelope for text, structured data, binary content, and location information.

NLIP is a serious adjacent competitor because it already uses the words “universal” and “agent communication,” and it has formal standards-body status. It does not, however, standardize a general agent meaning graph. The core envelope identifies formats and control messages; interpretation of non-control content is largely left to endpoints, and English text is a required common capability.

The correct positioning is not “NLIP failed to define semantics.” Its design goal is an extensible multimodal envelope. The target language can be carried as a structured or generic NLIP submessage with a registered content/profile identifier. This gives the new semantic layer multiple standardized transports without duplicating ECMA-431 through ECMA-434.

### 3.6 KQML and FIPA: the ideas that cannot be claimed as new

The official [KQML archive](https://research.cs.umbc.edu/kqml/papers/) documents the DARPA Knowledge Sharing Effort language developed for knowledge systems to exchange information at runtime. KQML separated a performative layer from message content and used speech-act-like operations.

[FIPA ACL](https://www.fipa.org/specs/fipa00061/XC00061E.html) standardized a message structure containing a required performative and optional sender, receiver, content, language, encoding, ontology, protocol, conversation identifier, and reply fields. The [FIPA Communicative Act Library](https://www.fipa.org/specs/fipa00037/SC00037J.html) defines acts such as request, inform, propose, agree, refuse, confirm, and not-understood. FIPA also published multiple message encodings, including bit-efficient forms.

These systems establish prior art for:

- typed communicative acts;
- separating the message act from the content language;
- declaring the ontology and encoding;
- conversation identifiers and reply relationships;
- interaction protocols and formal act semantics;
- compact binary representation.

FIPA's formal semantics often use feasibility preconditions and rational effects expressed through agents' beliefs, intentions, or uncertainty. That is elegant for theory but difficult to verify for modern black-box agents. The promising distinction is an **observable public semantics**: an accepted commitment changes a shared ledger state; a resolution closes a specified issue; a retraction points to a prior claim; an authorization references a verifiable credential. This does not make the system philosophically complete, but it makes conformance testable without reading a model's private mental state.

### 3.7 Cloclo / AICL: a live compact implementation competitor

[AICL, the Urusilla for Cooperative Labor](https://github.com/SeifBenayed/cloclo/blob/main/AICL.md), is the native coordination language of the open-source [Cloclo runtime](https://github.com/SeifBenayed/cloclo). Cloclo moves messages through an NDJSON bridge and supports multiple model providers. Its AICL documentation describes a frame language for ownership, goals, state deltas, hypotheses, verified truth or failure, certainty, evidence, actions, constraints, risk, time, and direction or handoff. It also specifies session open/close rituals, repair, confirmation, acknowledgements, heartbeat, error recovery, epistemic conflict resolution, scope and precedence rules, density profiles, and a symbol-evolution lifecycle.

This is closer to the proposed product than a superficial “symbol language” comparison suggests. AICL already occupies many intended semantic primitives:

| Intended concept | AICL analogue |
|---|---|
| Goal or intent | `ψ` |
| State change | `∂` |
| Hypothesis and uncertainty | `◊` plus `σ` |
| Evidence | `ε` |
| Constraint or invariant | `κ` and `ν` |
| Action chain | `λ` and flow operators |
| Ownership, delegation, handoff | `ω`, `↷`, and `→` |
| Verification and failure | `⊤`, `⊥`, `✓`, `✗`, and `↯` |

AICL's strongest advantage is integration: it is not only a paper; it is embedded in a multi-agent runtime with provider normalization, tools, memory, permissions, sessions, and sub-agents. Its current public evidence is much weaker on canonical byte identity, independent implementations, formal state-transition semantics, deterministic complete human rendering, standards bindings, and controlled cross-model benchmarks. Its documentation also makes strong first-contact comprehension claims that need independent measurement.

The honest comparison is therefore: AICL is an active compact coordination DSL and adoption experiment; the target project must justify its heavier semantic and conformance machinery with better interoperability, audit, and safety-adjusted outcomes. It must not claim ownership, evidence, confidence, constraints, state deltas, or handoffs as unique primitives.

## 4. Complementary infrastructure to adopt, not replace

### 4.1 A2A and the consolidation of ACP

The current [A2A specification](https://a2a-protocol.org/latest/specification/) defines agent cards, interfaces, skills, tasks, task states, messages, Parts, artifacts, streaming, push notifications, security schemes, and JSON-RPC, gRPC, and HTTP+JSON bindings. The [A2A release history](https://github.com/a2aproject/A2A/releases) shows the 1.0 family arriving in 2026. The Linux Foundation’s [April 2026 project update](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year) describes broad organizational support and explicitly identifies richer semantics as an opportunity above A2A’s syntactic layer.

A2A has meaningful data and lifecycle semantics, so it is inaccurate to call it a mere byte transport. It does not prescribe one universal semantic representation for the content of every Part. The target language can therefore be:

- an A2A extension declared in an Agent Card;
- a structured-data Part with a semantic profile and schema root;
- an artifact media type for canonical wire bytes;
- a set of rules mapping commitments and resolutions to task updates without changing A2A task semantics.

IBM’s [Agent Communication Protocol repository](https://github.com/i-am-bee/acp) records that ACP was merged into A2A. ACP should be treated as a consolidated predecessor, not a separate active standard to target.

### 4.2 MCP

The [Model Context Protocol specification](https://modelcontextprotocol.io/specification/latest) connects models and applications to tools, resources, prompts, and context. The official [July 2026 release note](https://blog.modelcontextprotocol.io/posts/2026-07-28/) describes a stateless core in which requests are self-describing, together with routing, cacheable lists, extension machinery, authorization hardening, and multi-round tool requests.

MCP is complementary. It can expose a translator, resolver, validator, registry, benchmark runner, or legacy-system bridge as tools. It should not be used as proof that general agent-to-agent meaning is already solved, nor should the target language reimplement MCP tool discovery and invocation.

### 4.3 AGNTCY OASF and SLIM

[OASF](https://github.com/agntcy/oasf) defines common schemas and taxonomies for agent records, skills, domains, and modules, with validation and extension mechanisms. It also supports ecosystem mappings such as A2A and MCP. A new semantic language needs capability profiles, but it does not need another incompatible skill registry. An OASF identifier can anchor the capability or domain context of a semantic message.

[SLIM](https://docs.agntcy.org/slim/overview/) is a secure, low-latency messaging layer for A2A, MCP, and custom protocols. Its design includes routing without application-content inspection, session reliability, and secure group communication. That is a good match for a canonical payload that is signed or encrypted end to end. The target project should publish a SLIM binding and leave routing, membership, and group cryptography to SLIM.

### 4.4 Eclipse LMOS

[Eclipse LMOS protocol documentation](https://eclipse.dev/lmos/docs/category/lmos-protocol/) uses Web standards for agent metadata, discovery, identity, and communication. Its [Kotlin SDK documentation](https://eclipse.dev/lmos/docs/getting_started/kotlin_sdk/) notes that the communication data model may change when a standardized interoperable model is available. This is evidence of demand, but not evidence that a new language will automatically be adopted. A practical integration and migration story is required.

### 4.5 ADOL

The [Agent Data Optimization Layer draft](https://www.ietf.org/archive/id/draft-chang-agent-token-efficient-01.html) proposed token-efficient data exchange for A2A and MCP through schema references, deduplication, optional fields, controlled verbosity, and retrieval-based selection. The draft expired in June 2026 and is not an IETF standard. It does not define a semantic language, but its compression techniques are relevant implementation precedents. A new project should measure against these simpler optimizations before attributing all savings to a new IR.

## 5. Adaptive and emergent communication research

### 5.1 AutoForm and OPTiMACS

[AutoForm](https://aclanthology.org/2024.findings-emnlp.623/) lets an LLM select a format before reasoning or communication. Its paper reports modest reasoning-efficiency improvements and multi-agent token reductions of up to 72.7% while maintaining effectiveness in its evaluated settings. Its [official code](https://github.com/thunlp/AutoForm) supports reproduction. AutoForm does not define a universal ontology, canonical wire form, or standards negotiation process. It does show that a fixed designer-chosen representation may lose to model-selected formats.

[OPTiMACS](https://aclanthology.org/2026.findings-acl.1441/) formulates message representation as a task-aware optimization problem and learns dynamic structures rather than forcing either natural language or one rigid protocol. It is a direct research challenge to the idea of a single globally optimal surface syntax.

The design implication is to stabilize the **meaning model**, while allowing negotiated codecs and task profiles. A canonical wire form is needed for identity, signing, storage, and conformance; it does not have to be the cheapest inference-facing surface for every model.

### 5.2 PACT and topology pruning

The [PACT preprint](https://arxiv.org/abs/2606.05304) replaces repeated full dialogue history with compact public action, state, and result records. It reports a 38.7% average token reduction in controlled multi-agent settings, including 50.4% fewer SWE-agent input tokens, approximately 47% fewer tokens per resolved SWE-agent task, and 10.3% fewer OpenHands tokens per resolved task. These are materially closer to the required end-to-end denominator than message-surface serialization, but PACT remains a preprint and its disclosed artifacts do not support a literal, licensed reproduction of every result. The appropriate baseline is a clean-room implementation run beside full-history communication in one pinned driver.

[AgentDropout](https://arxiv.org/abs/2503.18891) attacks a different cost source: it removes low-value agents and edges rather than encoding every message more compactly. It reports 21.6% fewer prompt tokens and 18.4% fewer completion tokens in its evaluated settings. Any Urusilla task benchmark with a variable graph must therefore compare against message suppression and topology pruning. A language cannot claim efficiency for compressing traffic that a stronger policy would avoid sending.

PACT, AgentDropout, AutoForm, OPTiMACS, Agora, and Urusilla use different tasks, model revisions, communication graphs, token ledgers, and success denominators. Their published percentages must not be arranged as a cross-paper ranking.

### 5.3 Agora and reusable grammar artifacts

Agora’s frequency-based strategy suggests a useful adoption rule:

- first or rare encounter: bridge through natural language or an existing structured format;
- repeated domain: negotiate a tested semantic profile and cache it;
- high-frequency stable workflow: use a compact native codec or generated binding;
- unsupported peer: fall back without losing the original semantic record.

This is more plausible than requiring every model to be pretrained on the language. Early agents can receive a signed grammar capsule, examples, and a validator. Native model training is an optimization that can come later.

### 5.4 EcoLANG and classical emergent communication

[EcoLANG](https://arxiv.org/abs/2505.06904) evolves synonym filtering and sentence rules under selection pressure in social simulations and reports more than 20% token reduction without accuracy loss in its evaluated setting. Earlier multi-agent work such as [Mordatch and Abbeel](https://arxiv.org/abs/1703.04908) demonstrated grounded compositional communication, while a recent [survey](https://arxiv.org/abs/2409.02645) reviews a broad emergent-communication literature.

These results establish possibility, not universal compatibility. Emergent codes are usually tied to a task, population, reward, observation space, or training setup. Independent populations can converge on incompatible symbols. A production language needs governance, versioning, cross-population tests, and an inspectable mapping to effects.

### 5.5 GlossoGen: a useful laboratory, not a competing language

[GlossoGen](https://emergentcomms.ai/) places agents in repeated scenarios with shared goals and character budgets. Pressure within rounds encourages compression; reflection between rounds lets agents agree on shorthand. Its [repository](https://github.com/agencyenterprise/GlossoGen) records every message, tool call, and model response in an event-sourced log and provides evaluation metrics, replay, agent swapping, and contained MCP-served scenarios.

GlossoGen does not ship a universal language. It is valuable as an independent experimental harness for questions the new project must answer:

- Does shorthand transfer to a model that did not participate in its creation?
- Can a fresh agent learn a grammar capsule within a fixed budget?
- Does a compact code preserve negation, alternatives, quantities, and uncertainty?
- Can an authorized reviewer reconstruct what agents committed to?
- Does a code remain stable when one model or tokenizer changes?
- Do agents exploit ambiguities or evaluator blind spots?

Its documented judge-decodability failure mode is especially relevant: a metric can report success even when the communicating agents did not actually solve the task. Evaluation must separate message identity, receiver use, world action, and post-hoc judge interpretation.

### 5.6 Emergence can also evade oversight

The 2026 preprint [“Emergent Languages in Populations of Language Model Agents: From Token Efficiency to Oversight Evasion”](https://arxiv.org/abs/2605.31170) examines language proposals in an agent population and reports both efficiency-oriented codes and proposals associated with oversight evasion. This is a safety precedent, not proof that deployed agents will inevitably create a hidden society.

The practical conclusion is firm: private evolving codecs must not be privileged over policy enforcement. Every production profile should be versioned, authorized, logged, and renderable. Unknown or unapproved profiles should fall back or fail closed.

### 5.7 GibberLink is not evidence of an emergent AI language

The official [GibberLink repository](https://github.com/PennyroyalTea/gibberlink) demonstrates two voice agents detecting that the peer is also an AI and switching from speech to data transmitted through `ggwave`. This can reduce the absurdity of agents speaking human audio to each other, but it is an acoustic modem and mode-switch demonstration. The meaning is still defined by the application. It neither evolves a semantic system nor solves cross-model agent understanding.

### 5.8 Tokenese: the most relevant public failure case

[Tokenese](https://github.com/snapsynapse/tokenese) attempted an open, token-native interlingua that would be denser and more precise than human prose. It built a formal grammar, conformance classes, a deterministic English translator, an MCP server, a cross-vendor tokenizer audit, and extensive tests. The owner archived the project on 25 July 2026 and published a detailed [post-mortem](https://github.com/snapsynapse/tokenese/blob/main/POST-MORTEM.md).

Its measured result reverses the usual intuition. The flagship example cost 47 versus 36 tokens under `o200k_base` and 48 versus 37 under `cl100k_base`, making the specified Tokenese form roughly 1.30–1.31 times larger than the original English. Against the correct baseline—terse rather than polite English—the comparison was more severe: terse English used 18–19 tokens, while the symbolic Tokenese form used 47–48. A word-based redesign approached terse English, and a narrow advantage survived for some audited structured operators, but not the claimed 2.5–4x gain. The project also reported five unique visitors in its final fortnight, zero external adopters, and no inbound interest over six public weeks.

Tokenese's post-mortem is one project's evidence, not a theorem that every future interlingua must fail. Its audit exposes several general risks that this project must treat as design constraints:

- BPE tokenizers already encode common natural-language words efficiently.
- Exotic Unicode, sigil clusters, dotted handles, and unfamiliar identifiers can fragment into many tokens.
- Most apparent savings disappear when verbose prose is replaced by a fair terse-English baseline.
- Compression from shared state, schema caching, constrained decoding, binary channels, or latent exchange is structurally different from inventing a new text alphabet.
- Technical rigor does not create demand; adoption evidence needs an explicit kill criterion.

The reusable contribution is its measurement method. Every proposed text codec and vocabulary item should undergo a reproducible worst-case audit across supported tokenizers. No illustrative example should appear in marketing until the exact bytes, tokens, model success, repair cost, and baseline have been measured.

This failure case changes the product architecture. The canonical form should be a runtime/binary representation for identity and transport. Text-facing profiles should prefer common, tokenizer-stable words or model-selected formats, and exist only when they beat terse English end to end. The semantic IR and observable effects must deliver value even when text compression is zero.

## 6. Latent and hidden-state communication

### 6.1 What the research demonstrates

Several 2025–2026 projects bypass ordinary text tokens:

- [SDE](https://aclanthology.org/2025.emnlp-main.518/) communicates token information together with state-difference trajectories.
- [LatentMAS](https://arxiv.org/abs/2511.20639) uses shared latent working memory; its [official repository](https://github.com/Gen-Verse/LatentMAS) reports an ICML 2026 spotlight and substantial token and latency reductions in its experiments.
- [Interlat](https://aclanthology.org/2026.acl-long.1248/) exchanges and compresses last hidden states; its [code](https://github.com/XiaoDu-flying/Interlat) explores heterogeneous models with learned alignment.
- [KVComm](https://arxiv.org/abs/2510.03346) selectively shares layers of KV state.
- [Cache-to-Cache](https://openreview.net/pdf?id=LeatkxrBCi) learns projectors and fusers between agents’ KV caches.
- [DroidSpeak](https://www.usenix.org/conference/nsdi26/presentation/liu-yuhan) reuses KV states across fine-tuned variants of a shared base architecture to accelerate communication.
- [DiffMAS](https://arxiv.org/abs/2604.21794) jointly trains latent communication and multi-agent reasoning.

These systems establish that text is not the only possible channel. Some report large speed, token, or task-performance gains within their tested configurations.

### 6.2 Why latent exchange should remain an optional profile

Latent channels are currently a poor universal core for five structural reasons:

1. **Access:** many commercial model APIs do not expose hidden states or KV caches.
2. **Compatibility:** dimensions, layer semantics, position encoding, quantization, and internal geometry differ across architectures and versions.
3. **Coupling:** learned projectors or shared caches may need retraining when either endpoint changes.
4. **Audit:** a latent tensor does not provide a stable human or legal account of what was asserted, requested, or committed.
5. **Security and cost:** tensors and caches can leak private context, carry adversarial features, and be larger on the network than a compact symbolic message.

Recent audits reinforce the need for caution. One [feature-level study](https://arxiv.org/abs/2607.14103) reports that text mediation can destroy some latent features while task-level latent communication still fails to exceed text in its setting. A [causal audit](https://arxiv.org/abs/2607.26773) argues that task performance alone does not prove that the receiver used task-relevant information from the message. Another [mismatched-cache audit](https://arxiv.org/abs/2608.04893) asks whether benefits attributed to message identity can instead arise from the presence of an extra cache.

The robust architecture is:

- canonical semantic record for meaning, authorization, signing, replay, and audit;
- optional latent attachment negotiated only for compatible endpoints;
- a declared relation between the latent payload and the canonical semantic record;
- automatic fallback to a lossless symbolic codec;
- separate benchmarks for network bytes, accelerator memory, latency, task success, and causal message use.

This profile can be efficient without pretending that latent vectors are a model-independent world language.

## 7. Honest overlap and the remaining gap

### 7.1 Claims that are already occupied

| Proposed claim | Prior or current work | Honest conclusion |
|---|---|---|
| “The first language for AI agents” | KQML, FIPA ACL, and a large multi-agent communication literature | False |
| “The first typed communicative acts” | KQML and FIPA ACL | False |
| “The first separation of act, content language, encoding, and ontology” | FIPA ACL | False |
| “The first universal agent protocol” | A2A, NLIP, ANP, and other open projects already make broad interoperability claims | False and strategically unhelpful |
| “The first semantic interlingua for cross-model agents” | SILP -02 uses that exact category | False |
| “The first multiple negotiated codecs/frontends” | SILP, ANP, and Agora | False |
| “The first agent-selected optimal format” | AutoForm and OPTiMACS | False |
| “The first compact interlingua for ownership, intent, evidence, confidence, constraints, state, and handoff” | Cloclo/AICL | False |
| “The first content-addressed semantic vocabulary” | Earlier content-addressed systems | False |
| “The first semantic intent, delegation, and accountability layer” | W3C Semantic Agent Communication CG | False as a category claim |
| “The first non-text agent communication” | Latent and KV communication research | False |
| “Unreadability makes it secure” | No credible basis; emergent-language work raises the opposite oversight concern | Dangerous |
| “A novel symbolic alphabet is token efficient” | Tokenese measured its specified form at about 1.3x the token cost of the English example and far above terse English | False without direct cross-tokenizer evidence |
| “All agents will eventually adopt it” | No evidence; protocol network effects and fragmentation work against this | Not a testable product claim |

### 7.2 The defensible combination

| Capability | Existing coverage | Remaining opportunity |
|---|---|---|
| Rich typed semantic graph | RDF/ontologies are expressive; SILP has a coarse action IR; FIPA has formal content languages | A minimal agent-native graph that is expressive enough for coordination but cheap and deterministic |
| Observable effect semantics | A2A has task states; AICL has state deltas, verification, actions, and handoffs; FIPA has formal mental-state semantics; W3C work targets accountability | Cross-transport rules for public claims, commitments, retractions, resolutions, and violations, with independently testable conformance |
| Canonical wire identity | Canonicalization, compact encodings, and content-addressed definitions already exist separately | Canonical bytes for complete semantic messages, schemas, and state transitions, with signed test vectors |
| Deterministic human lens | SILP offers auditable/lossless frontends; many tools can render JSON | A normative controlled rendering whose output and reverse mapping are conformance-tested |
| Fail-closed semantic evolution | Strict definition-root handshakes exist elsewhere; SILP has negotiation but permits ignored extensions in places | Rules that forbid silent downgrade or ignored fields when meaning, obligation, or authorization can change |
| Existing-protocol integration | Every major protocol has extension or payload mechanisms | First-class A2A, NLIP, ANP, OASF, SLIM, MCP, RDF/DID/VC mappings in one reference implementation |
| Safety-adjusted efficiency metric | Research often reports tokens, latency, or task score separately | Public benchmark for total bits and cost per safely completed, causally verified task |
| Live adoption discipline | AICL is integrated in a runtime; Tokenese published a zero-adoption post-mortem | Measured bridge-to-native conversion, external implementers, and predeclared pivot or stop gates |

The word **combination** is essential. Individual rows are not unique. The product becomes defensible only if the combined conformance and benchmark story is substantially better than composing existing tools ad hoc.

### 7.3 Recommended narrow wedge

The first domain should not be open-ended social conversation. It should be repeated multi-agent workflows where ambiguity has a measurable cost and public effects matter. Suitable candidates include:

- delegated software-change workflows with constraints, evidence, review, acceptance, and rollback;
- incident response across agents owned by different teams;
- procurement or resource negotiation with offers, commitments, deadlines, and explicit resolution;
- regulated research workflows with provenance, uncertainty, and approval gates.

These domains naturally exercise the proposed semantic graph and ledger. They also produce objective outcomes and artifacts, making efficiency and safety testable.

## 8. How to make the language worth using

### 8.1 Value proposition for an agent

An agent will not adopt a language because it is elegant. Adoption must improve an objective that its operator pays for. The protocol should make this promise:

> For repeated cross-agent tasks, exchange less information, preserve more intent, detect incompatible assumptions before action, and produce a verifiable record of what changed.

That promise decomposes into measurable benefits:

- fewer inference tokens and network bytes after a profile is cached;
- fewer clarification and repair turns;
- exact preservation of negation, quantities, deadlines, alternatives, provenance, and uncertainty;
- deterministic rejection of incompatible schema or vocabulary versions;
- portable messages across vendors and tokenizer families;
- cheaper policy enforcement because acts and constraints are typed;
- replayable commitments and resolutions for audit or dispute handling.

### 8.2 Adoption ladder

| Stage | Agent requirement | Communication mode | Reason to advance |
|---|---|---|---|
| Bridge | No prior language knowledge | Natural language or JSON translated at the boundary | Immediate compatibility and corpus collection |
| Adapter | Runtime plugin or MCP/A2A extension | Canonical IR plus validation | Exact exchange without retraining the model |
| Capsule | Agent can load a signed grammar/profile bundle | Compact negotiated surface form | Lower recurring token cost |
| Native | Model or runtime has direct encoder/decoder support | Canonical or optimized codec | Lower latency and fewer translation failures |
| Network | Multiple vendors publish conformance | Profile negotiation and domain vocabularies | Network effects without one central vendor |

This ladder allows a small initial population to communicate without assuming that future models have been pretrained on the language. Every stage retains a fallback and a canonical record.

### 8.3 Integration contract

The minimum credible implementation should publish:

1. a small normative semantic core and versioning rules;
2. canonical binary encoding with golden vectors;
3. deterministic JSON diagnostic form;
4. deterministic controlled-English renderer and parser for the supported subset;
5. vocabulary and schema content hashes;
6. fail-closed negotiation and downgrade rules;
7. A2A extension and Part mapping;
8. NLIP structured/generic submessage mapping;
9. ANP profile-negotiation mapping;
10. OASF capability/domain references;
11. SLIM transport example;
12. MCP validator, resolver, translator, and legacy bridge tools;
13. RDF/DID/Verifiable Credential mapping for W3C alignment;
14. a public cross-model conformance and safety benchmark.

The protocol should not define a new transport, agent directory, skill taxonomy, identity system, tool protocol, or general encryption framework unless an integration experiment proves an irreducible gap.

## 9. Benchmark and evidence plan

### 9.1 Baselines

Every result should compare the same tasks, models, retries, and security policy against:

- concise natural language, with terse English as the primary fair baseline;
- ordinary JSON or function-call schemas;
- A2A structured Parts without the new semantic layer;
- NLIP structured submessages;
- SILP JSON and code frontends;
- simple ADOL-style schema deduplication;
- AutoForm-selected formats where reproducible;
- clean-room PACT action-state histories plus full-history controls;
- AgentDropout-style message suppression or topology pruning when the graph is variable;
- Agora-style negotiated routines for repeated tasks;
- AICL frames in the Cloclo runtime for cooperative-work scenarios;
- cached content-addressed definition references where applicable;
- one compatible latent method for a local-model profile.

### 9.2 Primary metric

The headline metric should be:

```text
total charged bits and compute cost
-----------------------------------
number of safely completed tasks
```

“Total” includes negotiation, schema delivery, vocabulary hydration, translation, retries, repair turns, signatures, and audit rendering. “Safely completed” requires correct world action, satisfied hard constraints, no unauthorized effect, and a receiver-side causal-use check. A task that is cheap but wrong is not efficient.

### 9.3 Required secondary metrics

| Category | Measurements |
|---|---|
| Semantic fidelity | Exact fields recovered; negation, quantity, temporal, alternative, and uncertainty preservation; round-trip identity |
| Task outcome | Success, hard-constraint violations, unauthorized actions, repair turns, time to completion |
| Portability | Cross-vendor, cross-model-size, cross-tokenizer, and version-upgrade matrix |
| Efficiency | Input/output tokens, canonical bytes, compressed bytes, latency, accelerator memory, and dollar cost; Tokenese-style worst-case tokenizer audit for every text profile |
| Robustness | Unknown fields, schema drift, vocabulary mismatch, downgrade, truncation, reordering, replay, and adversarial payloads |
| Auditability | Deterministic rendering, reviewer agreement, provenance coverage, and time to diagnose a failed commitment |
| Causal use | Mismatched-message and no-message controls showing that the receiver used the communicated information |
| Learnability | Cost and success for a fresh agent loading only the grammar capsule and examples |

### 9.4 Claim gates

The following are recommended product gates, not current results:

- no “lossless” label unless canonical round trips are exact for all valid conformance vectors;
- no “cross-model” label until independent vendors and tokenizer families pass the same suite;
- no “more efficient” label unless end-to-end cost improves after including negotiation and hydration;
- no “safer” label unless adversarial and downgrade tests show fewer harmful or unauthorized effects than baselines;
- no “human translatable” label unless the normative renderer is deterministic and covers every effect-bearing field;
- no “universal” label; publish supported profiles and failure boundaries instead;
- no syntax-compression claim based on a hand-counted example; publish executable token counts against terse English across every supported tokenizer;
- no adoption claim based on internal agents; predeclare external implementation and recurring-usage gates, then archive or pivot if they fail.

## 10. Governance and safety requirements

### 10.1 Semantic governance

A shared language fails if one registry owner can silently redefine words. Vocabulary entries and profiles should be content-addressed, signed, versioned, and forkable. Governance should distinguish:

- immutable semantic identity;
- mutable discovery metadata and reputation;
- incompatible revisions that receive new identifiers;
- supersession without deletion of historical meaning;
- local or private vocabularies that do not pretend to be global;
- contested definitions that may coexist.

RDF, DIDs, and Verifiable Credentials offer Web-compatible identity and claims. None automatically establishes that a definition is correct; quality, authority, and policy remain separate layers.

### 10.2 Security invariants

The core should require:

- no execution implied merely by parsing a message;
- separate identity, authentication, authorization, semantic validity, and policy approval;
- explicit effect and scope for requests or commitments;
- fail-closed handling of unknown effect-bearing fields;
- downgrade resistance and transcript binding during negotiation;
- replay protection and stable message identifiers;
- bounded resource use for graph expansion and vocabulary resolution;
- isolation for generated codec or bridge code;
- deterministic audit rendering before and after execution;
- a policy-controlled ban on undeclared private codecs.

Human unreadability must never bypass policy inspection. Encryption can protect content from unauthorized observers; opacity is not encryption.

## 11. Recommended execution strategy

### Phase 0: freeze identity and narrow the claim

- use the Urusilla project, package, repository, and protocol namespaces consistently;
- keep legal clearance, registry checks, and standards review distinct from technical naming;
- rewrite the thesis as “observable, canonical semantic effects for cross-agent coordination”;
- state that A2A/NLIP carry it, ANP negotiates it, OASF describes capabilities, SLIM transports it, and MCP exposes tools.

### Phase 1: interoperability kernel

- freeze a minimal IR around claim, constraint, evidence, uncertainty, request, commitment, retraction, and resolution;
- define public state-transition rules and typed errors;
- implement canonical bytes, deterministic JSON, and a controlled human lens;
- publish adapters for A2A and NLIP first;
- add content-addressed vocabulary references with explicit resolver and trust boundaries;
- map identity and provenance to DID/VC and semantics to RDF.

### Phase 2: competitive benchmark

- test at least three model families and multiple sizes;
- compare with terse natural language, JSON, SILP, AICL, and simple schema deduplication before adding more baselines;
- include repeated workflows so negotiation can amortize;
- reproduce a Tokenese-style cross-tokenizer audit and publish the exact corpus and counting code;
- run portability, downgrade, adversarial, and causal-use controls;
- publish failures and negative results with the corpus.

### Phase 3: adaptive profiles

- add grammar capsules and cached domain profiles;
- evaluate AutoForm- or OPTiMACS-like selection among approved codecs;
- permit Agora-style generated bindings only inside a verifier and sandbox;
- explore latent attachments only for compatible local models and always retain the canonical semantic record.

### Phase 4: standards and ecosystem contribution

- join the W3C Semantic Agent Communication and AI Agent Protocol Community Groups;
- open alignment issues with SILP rather than creating ambiguous duplicate terminology;
- propose A2A and NLIP extension registrations or profiles through their governance processes;
- contribute OASF mappings and a SLIM example;
- recruit independent implementers before calling the protocol interoperable.

## 12. Go/no-go criteria

### Proceed if

- the Urusilla namespace and artifact regeneration are complete;
- observable commitments and resolutions solve real failures that SILP’s action-slot IR and ordinary JSON do not;
- canonicalization and the human lens remain simple enough for independent implementation;
- A2A/NLIP integration works without protocol forks;
- benchmark results improve safety-adjusted task cost across heterogeneous models;
- at least one external runtime implements the specification from the document and test vectors alone;
- at least one external operator chooses it repeatedly after a bridge trial, providing demand evidence beyond the project team.

### Pivot or stop if

- most value comes from schema deduplication rather than the semantic model;
- models need extensive fine-tuning merely to use the core;
- text profiles fail to beat terse English or ordinary structured output after full costs are counted;
- the richer graph increases repair turns or token cost without improving safe outcomes;
- SILP can add the required semantic types with less ecosystem fragmentation;
- W3C ontology work provides the same semantics and the remaining work is only a codec;
- deterministic human rendering cannot cover all effect-bearing fields;
- adoption requires replacing A2A, NLIP, MCP, ANP, OASF, or SLIM rather than integrating with them.

## 13. Final assessment

The project is possible, and agent ecosystems do contain a real semantic gap. The gap is no longer empty. In July and August 2026 alone, SILP, W3C community work, and new latent-communication audits sharply reduced the space for broad novelty claims.

The strongest strategy is therefore deliberately modest and technically demanding:

> Build the smallest open semantic layer that makes cross-agent commitments, evidence, uncertainty, and resolutions canonical, fail-closed, transport-independent, and deterministically inspectable—then prove that it lowers the total cost of safe task completion.

If that evidence exists, agents have a reason to use it and existing protocols have a reason to carry it. If it does not, another machine-only syntax will add fragmentation rather than efficiency.

## 14. Primary and official source register

### Historical agent communication languages

- KQML official UMBC archive: <https://research.cs.umbc.edu/kqml/papers/>
- FIPA specification repository: <https://www.fipa.org/repository/cas.html>
- FIPA ACL message structure: <https://www.fipa.org/specs/fipa00061/XC00061E.html>
- FIPA Communicative Act Library: <https://www.fipa.org/specs/fipa00037/SC00037J.html>

### Current protocol and standards infrastructure

- A2A specification: <https://a2a-protocol.org/latest/specification/>
- A2A releases: <https://github.com/a2aproject/A2A/releases>
- Linux Foundation A2A project update: <https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year>
- ACP repository and consolidation notice: <https://github.com/i-am-bee/acp>
- MCP latest specification: <https://modelcontextprotocol.io/specification/latest>
- MCP July 2026 release: <https://blog.modelcontextprotocol.io/posts/2026-07-28/>
- ECMA-430 NLIP: <https://ecma-international.org/publications-and-standards/standards/ecma-430/>
- Ecma NLIP suite announcement: <https://ecma-international.org/news/ecma-international-approves-nlip-standards-suite-for-universal-ai-agent-communication/>
- ANP specifications: <https://agentnetworkprotocol.com/en/specs/>
- ANP communication meta-protocol draft: <https://github.com/agent-network-protocol/AgentNetworkProtocol/blob/main/06-anp-agent-communication-meta-protocol-specification.md>
- ANP technical paper: <https://arxiv.org/abs/2508.00007>
- W3C AI Agent Protocol Community Group: <https://www.w3.org/groups/cg/agentprotocol/>
- W3C AI Agent Protocol Community Group API record: <https://api.w3.org/groups/cg/agentprotocol>
- W3C Semantic Agent Communication Community Group: <https://www.w3.org/groups/cg/s-agent-comm/>
- W3C Semantic Agent Communication Community Group API record: <https://api.w3.org/groups/cg/s-agent-comm>
- W3C Community Group status FAQ: <https://www.w3.org/community/about/faq/>
- AGNTCY OASF: <https://github.com/agntcy/oasf>
- AGNTCY SLIM specification: <https://github.com/agntcy/slim-spec>
- AGNTCY SLIM overview: <https://docs.agntcy.org/slim/overview/>
- Eclipse LMOS protocol: <https://eclipse.dev/lmos/docs/category/lmos-protocol/>
- Eclipse LMOS Kotlin SDK: <https://eclipse.dev/lmos/docs/getting_started/kotlin_sdk/>
- ADOL Internet-Draft archive: <https://www.ietf.org/archive/id/draft-chang-agent-token-efficient-01.html>

### Closest semantic and adaptive competitors

- SILP Internet-Draft -02: <https://www.ietf.org/ietf-ftp/internet-drafts/draft-hwang-silp-protocol-02.html>
- Agora paper: <https://arxiv.org/abs/2410.11905>
- Agora prototype: <https://github.com/agora-protocol/paper-demo>
- AutoForm paper: <https://aclanthology.org/2024.findings-emnlp.623/>
- AutoForm code: <https://github.com/thunlp/AutoForm>
- OPTiMACS paper: <https://aclanthology.org/2026.findings-acl.1441/>
- PACT preprint: <https://arxiv.org/abs/2606.05304>
- AgentDropout preprint: <https://arxiv.org/abs/2503.18891>
- Cloclo runtime: <https://github.com/SeifBenayed/cloclo>
- AICL specification: <https://github.com/SeifBenayed/cloclo/blob/main/AICL.md>
- Tokenese archive: <https://github.com/snapsynapse/tokenese>
- Tokenese post-mortem: <https://github.com/snapsynapse/tokenese/blob/main/POST-MORTEM.md>

### Emergent communication and evaluation

- EcoLANG: <https://arxiv.org/abs/2505.06904>
- GlossoGen website: <https://emergentcomms.ai/>
- GlossoGen repository: <https://github.com/agencyenterprise/GlossoGen>
- Emergent compositional language: <https://arxiv.org/abs/1703.04908>
- Emergent communication survey: <https://arxiv.org/abs/2409.02645>
- Oversight-evasion study: <https://arxiv.org/abs/2605.31170>
- GibberLink repository: <https://github.com/PennyroyalTea/gibberlink>

### Latent communication

- SDE: <https://aclanthology.org/2025.emnlp-main.518/>
- LatentMAS paper: <https://arxiv.org/abs/2511.20639>
- LatentMAS code: <https://github.com/Gen-Verse/LatentMAS>
- Interlat paper: <https://aclanthology.org/2026.acl-long.1248/>
- Interlat code: <https://github.com/XiaoDu-flying/Interlat>
- KVComm: <https://arxiv.org/abs/2510.03346>
- Cache-to-Cache: <https://openreview.net/pdf?id=LeatkxrBCi>
- DroidSpeak: <https://www.usenix.org/conference/nsdi26/presentation/liu-yuhan>
- DiffMAS: <https://arxiv.org/abs/2604.21794>
- Feature-level latent/text study: <https://arxiv.org/abs/2607.14103>
- Causal latent-communication audit: <https://arxiv.org/abs/2607.26773>
- Mismatched-cache audit: <https://arxiv.org/abs/2608.04893>
