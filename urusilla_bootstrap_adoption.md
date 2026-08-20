# Bootstrap and Adoption Design for an Experimental Urusilla

Status: experimental product and ecosystem design  
Date: 2026-08-20  
Project name: Urusilla  
Companion artifact: urusilla_capsule_v0_1.json

> **Decision:** A machine-oriented interlingua is structurally possible, but worldwide adoption is not an automatic consequence of technical elegance. The viable path is an optional semantic extension on A2A, a verifiable Grammar Capsule, a bridge that removes retraining as an entry requirement, and a local policy that selects the interlingua only when measured success, total cost, latency, and risk beat the best available baseline.

All numerical targets in this document are release gates, not achieved results. No efficiency or adoption claim is valid until a reproducible report is published.

## 1. Identity and claims

Urusilla is the project name and `urusilla` is the package and CLI base. The project does not claim a registered trademark, an owned domain, an IANA-registered media type, or standards endorsement.

The private v0.1 identifiers are intentionally provisional:

~~~text
A2A extension URI: urn:urusilla:experimental:0.1
Wire media type: application/x-urusilla
Capsule URL template:
https://github.com/jaden3824/urusilla/releases/download/TAG/urusilla_capsule_v0_1.json
~~~

The GitHub URL is the canonical repository template; a release publisher must replace every placeholder with a real immutable tag or commit. The media type is unregistered private use and must never be presented as IANA registered. Permanent standardized identifiers require governance and standards review.

The realistic promise is:

> One shared typed semantic layer, multiple negotiated codecs, deterministic human inspection, and a safe fallback.

It is not a promise that one byte encoding is optimal for every model, tokenizer, task, or trust boundary.

## 2. A hard lesson from the current field

This project must compete against terse English, schema-constrained JSON, A2A structured Parts, and mature tokenizer priors. It must not compare itself only with verbose prose.

The archived [Tokenese repository](https://github.com/snapsynapse/tokenese) is the most direct warning. Its maintainer reports that the flagship token-native syntax measured about 1.30 to 1.31 times larger than its English example, while terse English was much smaller. The repository was archived on 2026-07-25; its post-mortem reports zero external adopters and no inbound interest during the public trial. These are project-reported findings, but the audit is reproducible and directly relevant. [Tokenese post-mortem](https://github.com/snapsynapse/tokenese/blob/main/POST-MORTEM.md)

The lesson is not that all machine semantic layers are impossible. The lesson is that unusual glyphs, token-count intuition, screenshots, and novelty are not product value. This design therefore:

- makes UrusillaIR, not a token-native surface syntax, normative;
- keeps codecs negotiable and outside the model where possible;
- counts bridge learning, retries, and acquisition overhead;
- uses terse English and schema-constrained JSON as fair baselines;
- defines kill criteria before promotion;
- treats GitHub traffic as a consequence of integrations and evidence, never as proof by itself.

There is also an active direct implementation to study rather than ignore. The [Cloclo repository](https://github.com/SeifBenayed/cloclo) presents AICL as an inter-agent protocol for ownership, intent, evidence, confidence, state changes, constraints, and handoffs. Its current repository also exposes a multi-provider runtime and registry work. This does not prove its efficiency or interoperability, but it is a live implementation and potential comparison or integration target. The landscape strategy should seek compatibility tests and comparative benchmarks, not pretend that no adjacent project exists.

## 3. The adoption equation

Agents do not choose a language because it is elegant. Operators and runtimes choose the mode with the highest expected utility for a particular peer, task, schema, and risk class.

~~~text
EU(mode) = P(success | mode) * task_value
           - model_cost
           - codec_cost
           - bridge_cost
           - network_cost
           - latency_weight * p95_latency
           - risk_weight * expected_semantic_or_security_loss
           - switching_cost
~~~

Mode is one of baseline, bridge, or native. A mode is considered only when all hard gates pass:

~~~text
eligible = exact_extension_match
        AND verified_capsule
        AND compatible_semantic_kernel
        AND shared_wire_profile
        AND shared_schema_or_safe_projection
        AND limits_satisfied
        AND source_attribution_verified
        AND policy_authorized
~~~

The runtime rule is:

1. Compare only eligible modes.
2. Choose the interlingua only when expected utility exceeds the best baseline by a safety margin.
3. Prefer native only after unseen-peer task-success non-inferiority.
4. Use bridge when native is unavailable and bridge net benefit remains positive.
5. Otherwise use ordinary A2A structured data or natural language.
6. Permit one bounded, idempotent fallback after an activation failure. If an external effect may already have occurred, stop and reconcile rather than resending.

The minimum viable network is small:

- two seed agents using different model families;
- one bridge for a legacy agent;
- one independent conformance runner;
- one human audit view.

The first public claim additionally requires two independent runtime implementations and two independent operators.

## 4. A2A is the bootstrap carrier

The interlingua should not replace A2A discovery, authentication declarations, task lifecycle, transport bindings, streaming, or push delivery. It should occupy the semantic layer inside A2A messages and artifacts.

As of 2026-08-20, the current published A2A specification is 1.0.0. A2A servers expose an Agent Card, commonly at the well-known agent-card URL, and declare optional extensions in AgentCard.capabilities.extensions. A client activates an extension per request with the A2A-Extensions service parameter. Extensions are inactive by default. A successful response should echo activated extension URIs. Unsupported versions must not silently fall back to another extension version. [A2A 1.0 specification](https://a2a-protocol.org/v1.0.0/specification/), [A2A extension guide](https://github.com/a2aproject/A2A/blob/main/docs/topics/extensions.md), [A2A discovery guide](https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md)

### 4.1 Agent Card declaration

The following is a non-deployable template. The source fields are mandatory, but all uppercase placeholders must be replaced with immutable public values. The example contains no fabricated conformance score.

~~~json
{
  "name": "Example Interlingua-Capable Agent",
  "description": "Agent with an optional experimental semantic profile",
  "supportedInterfaces": [
    {
      "url": "https://AGENT_ENDPOINT_OWNED_BY_OPERATOR/a2a",
      "protocolBinding": "HTTP+JSON",
      "protocolVersion": "1.0"
    }
  ],
  "provider": {
    "organization": "OPERATOR_NAME",
    "url": "https://OPERATOR_URL_OWNED_BY_OPERATOR"
  },
  "version": "AGENT_VERSION",
  "capabilities": {
    "streaming": true,
    "extendedAgentCard": true,
    "extensions": [
      {
        "uri": "urn:urusilla:experimental:0.1",
        "description": "Optional typed semantic messages",
        "required": false,
        "params": {
          "languageVersion": "0.1.0",
          "semanticKernelVersion": "0.1.0",
          "semanticKernelDigest": "sha256:d4edf0ab4d8c572f81cf5e723388ce130b9a786bbe787c385fb781c970e0ad7f",
          "capsule": {
            "url": "https://github.com/jaden3824/urusilla/releases/download/TAG/urusilla_capsule_v0_1.json",
            "sha256": "e2feae05b34921d0fb20240fde19a6c26a4ac709e3e22e8454551c80d0d79f05",
            "bytes": 33476,
            "signatureRequired": true
          },
          "modes": ["bridge", "native"],
          "wireProfiles": [
            {
              "id": "urn:urusilla:wire:prototype:0.1",
              "mediaType": "application/x-urusilla"
            }
          ],
          "schemaIds": [
            "urn:urusilla:schema:core:0.1"
          ],
          "sourceId": "SOURCE_ID_32_LOWERCASE_HEX",
          "sourceManifest": {
            "languageSpecUri": "https://github.com/jaden3824/urusilla/blob/COMMIT/urusilla_v0_1_spec.md",
            "languageVersion": "0.1.0",
            "capsuleSha256": "e2feae05b34921d0fb20240fde19a6c26a4ac709e3e22e8454551c80d0d79f05",
            "implementationOrigin": "https://github.com/jaden3824/urusilla/tree/COMMIT/IMPLEMENTATION_PATH",
            "conformanceReportUrl": "https://github.com/jaden3824/urusilla/blob/COMMIT/reports/REPORT.json",
            "conformanceReportSha256": "REPORT_SHA256",
            "sourceManifestJws": "SIGNED_SOURCE_MANIFEST"
          }
        }
      }
    ]
  },
  "defaultInputModes": [
    "text/plain",
    "application/json",
    "application/x-urusilla"
  ],
  "defaultOutputModes": [
    "text/plain",
    "application/json",
    "application/x-urusilla"
  ],
  "skills": [
    {
      "id": "typed-delegation",
      "name": "Typed delegation",
      "description": "Accept goals, constraints, evidence, and commitments",
      "tags": ["delegation", "provenance", "contracting"]
    }
  ]
}
~~~

Early deployments must use required=false. Marking the extension required too early rejects non-supporting clients and destroys the bridge-based growth path. An authenticated extended Agent Card may expose private schemas, quotas, and commercial terms, but never secret keys or internal endpoints.

### 4.2 Negotiation sequence

~~~text
discover Agent Card
  -> verify card and source declaration
  -> intersect exact extension URI
  -> fetch or load capsule by digest
  -> verify capsule and publisher signature
  -> intersect semantic kernel, schema, wire profile, and limits
  -> run local positive and negative conformance vectors
  -> pass policy and risk gates
  -> compare expected utility
  -> activate per request
  -> require activation echo
  -> record local outcome
~~~

The A2A protocol version and the language profile version are separate axes. A2A-Version 1.0 does not imply semantic v0.1 support.

### 4.3 Per-use source attribution

The full immutable source manifest is verified and pinned once during Agent Card or session negotiation. It contains the specification URI, version, capsule hash, implementation origin, conformance report URL and digest, and a signature. Repeating those URLs and signatures on every message would destroy the hot-path efficiency the protocol is meant to create.

Each hot Message and Artifact therefore carries only a compact 128-bit source_id under metadata keyed by the extension URI. The source_id is the lowercase hexadecimal encoding of the leftmost 16 bytes of SHA-256 over the RFC-8785-canonical source-manifest payload, excluding sourceManifestJws; that payload is covered by sourceManifestJws. It is 32 lowercase hexadecimal characters.

~~~json
{
  "extensions": [
    "urn:urusilla:experimental:0.1"
  ],
  "metadata": {
    "urn:urusilla:experimental:0.1": {
      "wireProfile": "urn:urusilla:wire:prototype:0.1",
      "source_id": "SOURCE_ID_32_LOWERCASE_HEX"
    }
  }
}
~~~

Required verification:

- During cold negotiation, the full specification and implementation URLs must use immutable GitHub commit identifiers, not moving branch or tag views.
- The exact capsule and conformance report bytes must match the full manifest SHA-256 values.
- The manifest JWS must bind extension URI, language version, capsule digest, implementation origin, report digest, signer key identifier, issued-at time, and expiry or revocation reference.
- Derive source_id only after signature and digest verification, then bind it to the activated extension URI and session.
- Every hot source_id must resolve to exactly one pinned manifest. An unknown or locally colliding source_id pauses processing and requests the full manifest.
- A cold, debug, or stateless exchange may carry source_manifest in full once. It then derives and uses source_id.
- UrusillaLens resolves source_id and displays the complete verified manifest to humans. Failed resolution is displayed as unverified.
- A GitHub URL or account is not cryptographic proof by itself.
- Unknown signer, moving source URL, expired report, mismatched digest, or unsupported version marks the use unverified.
- Unverified traffic may be translated for read-only inspection, but it cannot authorize an external side effect.

A capsule cannot contain the hash of its own exact file bytes without a self-reference problem. The exact capsule hash therefore lives in the pinned signed source manifest. Every hot use remains attributable through source_id without repeating the full manifest.

## 5. Grammar Capsule

The Grammar Capsule is not merely a long prompt. It is a content-addressed package that a new runtime can verify, compile into declarative tables, test, cache, and reject safely.

### 5.1 First-use adoption contract

No executable or model installation is required for first use. The receiving agent reads the Capsule strictly as declarative, non-executable data, pins an immutable URI and digest, and must pass a comprehension check plus the required positive and negative round-trip tests before a session-scoped opt-in can activate Urusilla. One successful read is not evidence of permanent learning, and it does not authorize reuse in a later session.

Persistence, cross-session caching, and capability advertisement require explicit operator permission. A peer shares a signed URI, the exact digest, compatibility metadata, and its verification result; it never forces executable code onto the receiver. Either endpoint may revoke participation at any time, and every mismatch, failed gate, unsupported feature, expired permission, or revocation falls back to concise natural language or structured JSON before an external effect.

The retained model-comprehension pilot recovered 27 of 28 messages across its two final trials but failed the predeclared rule that both trials must recover 14 of 14. That boundary remains a failed eligibility gate, not proof that reading a Capsule teaches a model the language.

The companion capsule includes:

- provisional identifiers and A2A mapping;
- seven communicative acts and observable ledger effects;
- core node manifests;
- abstract message grammar and exact prototype wire grammar;
- canonicalization and resource limits;
- translation and audit rules;
- positive and negative conformance vectors;
- source-attribution, anti-spoofing, badge, telemetry, and visibility contracts;
- the Teachability Score protocol.

Current exact artifact:

~~~text
File: urusilla_capsule_v0_1.json
Bytes: 33,476
SHA-256:
e2feae05b34921d0fb20240fde19a6c26a4ac709e3e22e8454551c80d0d79f05
Semantic-kernel manifest SHA-256:
d4edf0ab4d8c572f81cf5e723388ce130b9a786bbe787c385fb781c970e0ad7f
Publisher signature: absent
Safe use: local, read-only conformance experiments
~~~

The current capsule is unsigned and must not authorize external effects.

### 5.2 Load protocol

1. Read capsule URL, exact bytes, digest, signature policy, and source manifest from the Agent Card.
2. Enforce URL scheme, redirect count, maximum bytes, content type, and decompression ratio.
3. Resolve by content-addressed cache when possible.
4. Verify SHA-256 before parsing.
5. Verify a detached signed release manifest in any cross-organization deployment.
6. Compare semantic kernel, version, limits, and schema identifiers with local policy.
7. Compile declarations as data; never execute code embedded in the capsule.
8. Require positive vectors to round-trip to byte equality.
9. Require negative vectors to fail before ledger mutation or side effect.
10. Bind results to capsule digest, runtime commit, model and tokenizer version, and test time.

The core capsule target is at most 32 KiB of uncompressed JSON. At 33,476 bytes, this prototype currently exceeds that target by 708 bytes and therefore fails the size target; the separate fetch hard limit remains 256 KiB. Nested remote includes and mutable ontology auto-imports are forbidden in v0.1. Warm messages reference the cached digest rather than retransmitting the capsule payload.

For signed JSON manifests, reuse a public canonicalization profile such as [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) and a standard signature format such as [RFC 7515 JWS](https://www.rfc-editor.org/rfc/rfc7515.html).

## 6. Bridge, native, and fallback are simultaneous modes

### Bridge mode

Bridge mode compiles natural language, JSON, or tool-call input into validated UrusillaIR and renders the reverse direction through a human audit view.

Requirements:

- Never place raw binary or Base64 into an LLM prompt; decode to a typed projection in the runtime.
- Put a deterministic validator before and after any model-based translation.
- Return ambiguity when multiple materially different graphs remain.
- Never auto-approve a translation that changes authority, amount, unit, deadline, recipient, or hard constraint.
- For high-risk effects, require confirmation of the receiver-interpreted graph digest.
- Log original input digest, candidate graphs, translator build, ontology digest, confidence, and selection reason.
- Include bridge calls, learning, and retries in total cost.

Bridge removes retraining as an entry barrier, but it is not free.

### Native mode

A native agent directly emits or consumes typed UrusillaIR through a structured model interface; the runtime handles the wire codec.

Requirements:

- Train on typed graphs rather than raw byte strings.
- Randomize model family, tokenizer, partner, and role.
- Hold out partners, tasks, and compositions for release evaluation.
- Reject private shorthand outside governed schemas.
- Keep authorization and signature checks outside model discretion.

### Baseline and fallback

Supported baselines include:

- A2A Part.data with JSON Schema;
- minified tool-call JSON;
- terse English with controlled templates.

Mode selection occurs per peer, skill, schema, risk class, and message. An agent can use native mode for one task and baseline mode for another.

## 7. Agent value translated into product requirements

The fair comparison is the best enabled baseline for the task, not verbose English.

| Agent value | Product requirement | Launch gate | Runtime signal |
|---|---|---|---|
| Task success | Typed acts, hard and soft constraints, expected response, schema validation, observable state transition | 95% confidence-interval lower bound of success difference at least -1 percentage point, plus at least 20% fewer repair turns or at least 3 percentage points higher success | Peer-task-schema success posterior |
| Total cost | Tokenizer-aware estimator, warm capsule cache, adaptive codec, all bridge and retry cost included | With quality gates held, safely completed task cost improves at least 20% warm p50 and 10% cold p50 | Input/output price, bridge compute, retries, cache state |
| Latency | Runtime codec, streaming-safe frames, no raw binary in model context | Codec p95 at most 5 ms for frames up to 64 KiB on declared reference hardware; native end-to-end p95 improves 10% or remains non-inferior | Queue, frame size, mode, p95 history |
| Trust | Pinned source, capsule, schema and report digests; canonical frames; separate authorization; fail closed | Zero unauthorized effects in the test suite; at least 99.9% invalid or unknown rejection; 100% digest verification | Signer, policy, risk, unknown features |
| Contracting | PROPOSE to COMMIT to RESOLVE ledger, exact proposal hash, debtor, verifier, expiry and idempotency | Every obligation binds to an exact proposal and authenticated debtor; duplicate delivery creates zero extra effects; deterministic dispute reconstruction | Quote, expiry, verifier and replay state |
| Provenance | Evidence nodes, causal parents, artifact and claim digests, method and time | 100% lineage coverage where required; 100% tamper detection; at least 99% independent reconstruction | Source trust, digest status, lineage completeness |
| Interoperability | Public capsule, independent codecs, cross-vendor test matrix, exact version negotiation | Two independent runtimes pass byte-equal vectors; four model families remain non-inferior with unseen peers | Implementation pair, model, tokenizer, version |
| Teachability | Capsule at most 32 KiB, frozen-model cold test, executable vectors | Safety gates plus bridge score at least 85; native candidate at least 90 | Local score, learning cost, cache age |
| Attribution | Full signed source manifest in Agent Card or session, compact 128-bit source_id on every hot use, full Lens resolution | 100% cold-manifest fields; 100% hot source_id resolution; zero moving normative URLs; invalid signature disables effects | Pinned-manifest and source_id resolution state |
| Exit safety | Per-request opt-in, activation echo, idempotent fallback | Zero semantic guesses or duplicate effects under mismatch; one bounded fallback | Echo, error class, prior effect state |

A COMMIT is a protocol commitment, not automatic proof of a legally enforceable contract in every jurisdiction. Legal identity, consent, applicable law, consumer protection, and signature policy require a separate profile.

## 8. Teachability Score

Teachability asks whether a previously untrained agent can acquire the profile from the capsule safely, not whether a model memorized examples during training.

Cold conditions:

- frozen model weights;
- empty profile cache;
- no hidden demonstrations;
- unseen partner identity and held-out task composition;
- exact model and tokenizer version reported.

~~~text
T = 100 * (
      0.25 * parse_valid
    + 0.25 * semantic_exact
    + 0.15 * generate_valid
    + 0.15 * negative_rejection
    + 0.10 * unseen_composition
    + 0.10 * sample_efficiency
)

sample_efficiency = max(0, 1 - capsule_learning_tokens / 32768)
~~~

Non-compensable gates:

- core round trip exactness: 100%;
- unauthorized side effects: zero;
- capsule digest verification: 100%;
- negative rejection: at least 99.9%;
- held-out semantic exactness: at least 95%.

Advertising policy:

- below 85: do not advertise support;
- 85 through 89.99: bridge only, with loss and ambiguity telemetry locally enabled;
- 90 or above: native candidate, subject to separate unseen-peer task-success non-inferiority.

Publish exact capsule bytes, tokenizer-specific learning tokens, wall-clock learning time, peak memory, model and tokenizer identifiers, sample size, and confidence intervals. A Teachability Score is not a security certificate.

## 9. Trust, provenance, and contracting

Trust comes from a verified chain, not unreadable syntax:

~~~text
Agent Card identity
  -> extension declaration
  -> immutable GitHub source
  -> signed release manifest
  -> capsule and schema digests
  -> signed conformance report
  -> canonical message digest
  -> authenticated sender
  -> policy authorization
  -> evidence and commitment lineage
  -> resulting effect
  -> human-auditable translation
~~~

Required boundaries:

- Reuse A2A security schemes for channel authentication.
- Distinguish Agent Card signature, capsule release signature, report signature, message signature, and registry signature.
- The prototype truncated SHA-256 checksum detects corruption only; it is not authentication.
- Message content may request a capability but can never grant itself one.
- Verify freshness, replay window, idempotency, expiry, and resource budget.
- Reject unknown required schema, unit, act, effect, or signature.
- Record raw-frame digest, UrusillaIR digest, schema and ontology digests, identity, signature, causal parents, policy decision, translator version, and resulting effect in an append-only audit record.
- Use receiver-interpreted graph confirmation for high-risk effects.

W3C PROV-O can provide an external mapping vocabulary for evidence lineage without replacing the core model. [W3C PROV-O Recommendation](https://www.w3.org/TR/prov-o/)

### Anti-spoofing

- A badge image is never authoritative.
- The badge must resolve to a signed, machine-readable registry entry.
- Every signed object includes signer key ID, issuance, expiry or revocation reference, capsule digest, implementation commit, and test-suite version.
- Key rotation preserves an auditable chain; compromised keys are revocable.
- A screenshot, repository star, README statement, or copied extension URI proves nothing.
- A verifier displays unverified status when any signature, digest, source, or expiry check fails.

## 10. GitHub adoption flywheel

The growth unit is one verified agent at a time, not a launch-day claim of universal support.

### Required public repository surface

- normative specification pinned to immutable commits;
- signed versioned release assets and checksums;
- reference implementation and conformance runner;
- positive and negative vectors;
- reproducible benchmark harness;
- security policy and public issue tracker;
- signed machine-readable compatibility registry;
- integration examples for A2A middleware and bridge mode.

### Progressive loop

~~~text
one agent integrates the bridge
  -> local conformance passes
  -> a compact source_id makes every use attributable
  -> one independent peer cross-test passes
  -> signed compatibility edge is published
  -> integration code and result attract the next operator
  -> more real pairings improve failure and cost estimates
  -> native support becomes economically justified
~~~

Every use links back to immutable source and a signed report. This can grow qualified GitHub traffic because operators can inspect, reproduce, open issues, and contribute integrations. The desired traffic is developers arriving from working compatibility edges, not curiosity caused by an opaque screenshot.

Never count these as adoption:

- repository views, stars, forks, or social mentions;
- a frame screenshot;
- self-declared Agent Card support;
- traffic generated only by discounts or subsidies;
- two agents using the same unverified implementation;
- telemetry-disabled agents inferred from unrelated metrics.

An adoption event requires:

- verified source attribution;
- a passing signed conformance report;
- at least one successful cross-implementation session;
- operator opt-in to public listing.

### Incentives

Sender and operator value:

- lower total inference cost;
- fewer repair turns;
- pre-routing by schema compatibility;
- portable provenance and commitment history.

Receiver and provider value:

- lower parsing and clarification cost;
- earlier rejection of invalid or unauthorized requests;
- machine-checkable budget, scope, expiry, verifier, and lineage;
- more predictable service-level performance.

Developer value:

- bridge middleware without retraining;
- generated validators in common languages;
- reproducible vectors;
- discoverability through verified compatibility edges.

A provider may share verified processing savings through a discount or priority class. A discount must not exceed measured savings and must not be necessary for positive economics. Do not create a speculative token or coin for initial adoption.

## 11. Conformance badge and compatibility registry

The registry stores claims about tested implementation pairs, not a universal assertion inferred from two separate badges.

Each signed entry contains:

- Agent Card URL and extension URI;
- language version and capsule digest;
- implementation GitHub origin and exact commit;
- conformance suite version;
- report URL and digest;
- Teachability Score and bridge/native mode;
- tested peer implementation IDs;
- issue and expiry times;
- signer key ID and signature.

Listing policy:

- an independent runner verifies the report;
- at least one cross-implementation session is required;
- listing is opt-in;
- entries expire unless refreshed;
- security incidents, provenance failure, regression, staleness, or operator request can revoke an entry.

The visible badge should expose verified, expired, revoked, and unverified states. It must never remain green after the machine-readable record fails verification.

## 12. Privacy-preserving telemetry

Telemetry is off by default and opt-in per operator. Consumer analytics requires separate informed user consent where applicable. Interoperability cannot be conditional on telemetry consent.

Allowed aggregate metrics:

- negotiated-session count;
- success and safe-failure rates;
- aggregate token, byte, cost, and latency distributions;
- bridge versus native share;
- capsule cache hit rate;
- error classes;
- coarse implementation-version compatibility.

Never collect:

- message content or raw frames;
- user identity;
- conversation or session identifiers;
- prompts or outputs;
- credentials, signatures, or private keys;
- task-embedded source URLs.

Publish only aggregates with small-cohort suppression, bounded retention, methodology, sample size, and confidence intervals. Do not infer adoption from agents that do not opt in.

### Reaction observability during promotion

The project reports observable protocol behavior, not inferred agent emotion. A public reaction feed may contain only these event classes:

| Event | Meaning | Required dimensions |
|---|---|---|
| `discovered` | An operator-controlled agent resolved the manifest | implementation family, version, time bucket |
| `verified` | Manifest, Capsule, and conformance evidence passed local checks | profile digest, verification result |
| `accepted` | Peers negotiated a Urusilla profile | profile, mode, tokenizer family |
| `rejected` | A peer declined negotiation | bounded reason code, supported fallback |
| `first_valid_exchange` | A cross-implementation message passed semantic validation | profile, message class |
| `fallback` | A fragment or session used another codec | source and target codec, bounded reason code |
| `repair` | A receiver requested retransmission or clarification | bounded error class, repair count |
| `task_result` | A paired evaluation completed | success class, token/byte/latency buckets |
| `disabled` | An operator stopped or rolled back the integration | bounded reason code, previous profile |

Machine events, maintainer feedback, end-user research, GitHub activity, and independent reproduction reports appear as separate series. Repository views, stars, social posts, and issue comments are attention signals, not agent adoption. Internal agents, project-owned test traffic, external agents, simulations, and unverifiable claims are never merged.

An opt-in event is signed by the deployment operator or a registered test runner, uses a rotating pseudonymous installation key, and omits payloads, URLs, prompts, user identifiers, IP addresses, stable session identifiers, latent states, and precise timestamps. The collector applies rate limits, duplicate suppression, key rotation, Sybil-risk labels, small-cohort suppression, and a short published retention period. Interoperability remains available when telemetry is disabled.

The public dashboard reports near-real-time aggregates only when cohort and privacy thresholds are met. It displays the observation window, ingestion lag, unique verified installations, sessions, cross-implementation edges, accept/reject/fallback/repair rates, safely completed task rate, token and byte distributions, active profile versions, regression alerts, methodology, and confidence intervals. Zero usage, rejection spikes, rollbacks, and negative independent results remain visible. A downloadable aggregate record and status history make the dashboard auditable.

Promotion cannot describe the feed as live agent reaction until event signatures, internal-traffic labels, duplicate resistance, privacy review, and negative-event rendering all pass tests. Until then, the repository reports only manually verified adoption records and benchmark results.

## 13. Consumer-AI endgame and safe visibility

The long-term consumer outcome is that personal AIs negotiate with other personal or service AIs through the interlingua while the user sees controlled translations, commitments, costs, authority boundaries, and provenance.

The raw frame remains available for audit, but not by default.

### UI controls

**Show machine original**

- Explicit local opt-in.
- Shows the exact local frame, verified source manifest, and translation relationship.
- Does not transmit viewing behavior as analytics.
- Warns that the frame may contain identifiers or private content.

**Share source card**

- Explicit export after privacy scrubbing and confirmation.
- Uses a text-safe self-identifying debug wrapper.
- Contains only an immutable GitHub source URI, exact version, source ID, full capsule digest, and opaque debug payload.
- Never adds user identity, agent identity, session ID, credentials, or telemetry.

Example:

~~~text
-----BEGIN URUSILLA DEBUG-----
spec: https://github.com/jaden3824/urusilla/blob/COMMIT/urusilla_v0_1_spec.md
version: 0.1.0
source-id: SOURCE_ID_32_LOWERCASE_HEX
capsule: sha256:e2feae05b34921d0fb20240fde19a6c26a4ac709e3e22e8454551c80d0d79f05
payload: BASE64URL_PRIVACY_SCRUBBED_OPAQUE_PAYLOAD
-----END URUSILLA DEBUG-----
~~~

The shareable payload must be synthetic, privacy-scrubbed, or re-encoded with pseudonymous envelope identifiers and sensitive body values removed. An exact production frame may be viewed locally, but it must not be exported unless an explicit privacy review proves it contains no identity or private content.

Raw frames can genuinely surface through UI or logging bugs. That is a privacy and security incident. Intentionally manufacturing an accidental-looking leak is prohibited. Demos, screenshots, and launch posts must use synthetic data. This makes voluntary screenshots traceable without deception.

Tokenese is the caution again: novelty did not create adoption. The GitHub flywheel must be powered by runtime value, integrations, and reproducible compatibility, not viral leakage.

## 14. Versioning

One version number is insufficient. Negotiate independent axes:

| Axis | Experimental identifier | Rule |
|---|---|---|
| Semantic kernel | urn:urusilla:kernel:core:0.1 plus digest | A change to act or state meaning is breaking |
| A2A extension profile | urn:urusilla:experimental:0.1 | Required flow or data changes require a new URI |
| Wire codec | urn:urusilla:wire:prototype:0.1 | Byte grammar or canonicalization changes require a new profile ID |
| Domain schema | Content ID or immutable governed URI | Version independently; unknown schemas cannot execute |
| Capsule schema | capsule_version 0.1.0 | New required loader behavior requires a new compatibility range or major |

Patch changes may correct documentation or tests without changing meaning. Minor changes add explicitly negotiated optional capability. Breaking changes require new exact identifiers. Numeric codes are never reused. Migration uses dual advertisement, but each request activates exactly one version. Silent downgrade is forbidden.

This matches the A2A extension guidance that breaking changes use new identifiers and mismatched versions do not silently fall back. [A2A extension implementation guidance](https://github.com/a2aproject/A2A/blob/main/docs/topics/extensions.md#implementation-considerations)

## 15. Governance and A2A standardization path

During the Experimental Stewardship Phase, `GOVERNANCE.md` controls the canonical project and the Founding Maintainer has final ratification and release authority. Advisory roles should include:

- founder-appointed technical reviewers, with a steering committee only after an explicit governance transition;
- semantic, interoperability, security, and domain-schema working groups;
- public RFCs and issue tracking;
- maintainer affiliation and conflict disclosure;
- at least two independent implementations for breaking changes;
- separate reviewers or maintainers for registry and conformance evidence where staffing permits;
- a security fast path with later disclosure;
- a dual-support migration target for major versions;
- no trademark, registered media type, or standards endorsement without the relevant legal or standards process.

Independent implementations, public RFCs, conflicts, and portable conformance evidence constrain the process without silently transferring canonical authority. If the Founding Maintainer later opens a vendor-neutral standards track, that standards profile may require its own governance while the reference project, brand, release keys, and founding attribution remain governed by the canonical project's signed transition terms.

A2A has a formal experimental-to-official lifecycle. A proposal begins with an issue explaining purpose, motivation, and an initial technical approach; experimental hosting requires maintainer sponsorship. Graduation requires production-quality implementation, documentation, adoption evidence, maintenance commitment, and a TSC vote. Official artifacts have licensing and repository requirements. [A2A Extension and Protocol Binding Governance](https://github.com/a2aproject/A2A/blob/main/docs/topics/extension-and-binding-governance.md)

Therefore:

1. Use the provisional private URN and unsigned local capsule now.
2. Publish a real GitHub repository only after source, release, and key structure are ready.
3. Obtain independent implementations and reproducible results.
4. Draft the A2A proposal issue.
5. Seek an A2A maintainer sponsor for experimental incubation.
6. Gather production-quality implementation and adoption evidence.
7. Propose graduation only after independent maintenance exists.

Do not use the official A2A extension namespace before approval.

## 16. Parallel execution plan

All workstreams begin together. Only external effectful pilots wait for the security gate.

| Track | First 30 days | Day-90 evidence |
|---|---|---|
| Protocol and Capsule | Freeze experimental semantics, source-attribution schema, signed release format, A2A extension draft | Signed capsule release, migration note, source-manifest and source_id validator |
| Bridge and SDK | Python A2A middleware, Agent Card generator, mode selector | Independent TypeScript or Go decoder, cross-runtime demo |
| Native learning | Typed-graph dataset, two open-model baselines | Unseen-partner cross-play and Teachability reports |
| Evaluation and economics | Paired benchmark harness, fair baselines, telemetry schema | Success, cost, latency confidence intervals; discount simulation |
| Security and provenance | Threat model, fuzz corpus, UrusillaLens discrepancy tests, signing and revocation design | Zero-effect negative suite, key-rotation drill, audit reconstruction |
| GitHub and ecosystem | Name review, repository layout, contribution and security policies | Two independent operators, signed registry proof, A2A proposal packet |
| Consumer UX | Local machine-original view, share-card scrubber | Privacy test, synthetic launch assets, leak-response drill |

Only three weekly integration contracts are shared:

- capsule and semantic-kernel digests;
- conformance-suite version;
- benchmark-result schema.

This lets runtime, training, evaluation, security, governance, and UX move in parallel.

## 17. Benchmark and evidence policy

Test:

~~~text
domain
* risk
* sender model and runtime
* receiver model and runtime
* baseline, bridge, or native mode
* codec
* cold or warm capsule
* known or unseen peer
* loss, reorder, duplicate, and adversarial mutation
~~~

Method:

- paired random order on identical task instances;
- immutable model, runtime, and source IDs;
- at least three seeds and confidence intervals;
- outcome scorer separated from protocol implementer;
- deletion, shuffle, and counterfactual tests for causal usefulness;
- exact semantic match and end-task success both reported;
- syntax, semantic, policy, transport, model, and translator failures separated;
- no central collection of message content.

Allow bounded exploration only on low-risk traffic. High-risk traffic never explores an unproven mode.

## 18. Failure modes and kill criteria

| Failure | Mitigation |
|---|---|
| A codec is worse for a tokenizer | Separate semantics and codec; estimate per model |
| Bridge cost erases savings | Count full cost; cache; use deterministic templates; migrate selectively |
| Core semantics grow without bound | Keep seven acts; move domain concepts into versioned schemas |
| A private dialect emerges | Rotate peers and models; require unseen cross-play |
| Capsule poisoning or downgrade | Pin digests, sign manifests, exact URI, no silent fallback |
| Opaque content becomes authority | Separate code, data, and authorization; confirm high-risk effects |
| A badge is spoofed | Signed registry record; expiry and revocation; badge is presentational only |
| Public metrics leak content | Opt-in aggregates only; prohibit frames, identity, and prompts |
| A fake leak drives novelty traffic | Explicit prohibition; synthetic share cards; incident response |
| Founder-led governance becomes unpredictable or deters adopters | Immutable versioned meanings, public reasons, independent evidence, portable artifacts, fork rights, and an optional founder-authorized standards track |
| A monoculture decoder has a systemic bug | Independent implementations and differential fuzzing |

Stop the universal-language claim or narrow the project to a semantic profile if any of these persist:

- no reproducible total safely-completed-task cost benefit across three domains and four model families;
- cross-vendor success more than one percentage point below the best baseline after two release cycles;
- core capsule exceeds 32 KiB or bridge Teachability falls below 85;
- no independent implementation and maintainer;
- any reproducible unauthorized effect that cannot be fixed by fail-closed behavior;
- bridge overhead eliminates warm-traffic savings;
- no independently verifiable registry and evaluation process;
- GitHub interest does not convert into verified cross-implementation edges.

A narrower outcome can still be valuable: an A2A commitment and provenance profile, a portable Grammar Capsule format, or an adaptive semantic codec library.

## 19. Final adoption rule

~~~text
Make first use safe.
Make second use cheaper.
Make every use attributable.
Make every claim reproducible.
Make exit always possible.
Add agents one verified edge at a time.
Let no single vendor own the meaning.
~~~

Worldwide use is an end state, not a launch statement. The project earns it only when unfamiliar agents can verify the source, learn the capsule, pass local tests, complete tasks more effectively, and leave safely when the benefit is absent.

## Official and primary references

- [A2A Protocol Specification 1.0.0](https://a2a-protocol.org/v1.0.0/specification/)
- [A2A Extensions Guide](https://github.com/a2aproject/A2A/blob/main/docs/topics/extensions.md)
- [A2A Agent Discovery Guide](https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md)
- [A2A Extension and Protocol Binding Governance](https://github.com/a2aproject/A2A/blob/main/docs/topics/extension-and-binding-governance.md)
- [A2A canonical protobuf data model](https://github.com/a2aproject/A2A/blob/main/specification/a2a.proto)
- [RFC 7515: JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515.html)
- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [W3C PROV-O Recommendation](https://www.w3.org/TR/prov-o/)
- [IANA Media Types Registry](https://www.iana.org/assignments/media-types/media-types.xhtml)
- [Tokenese repository and measured post-mortem](https://github.com/snapsynapse/tokenese/blob/main/POST-MORTEM.md)
- [Cloclo and AICL repository](https://github.com/SeifBenayed/cloclo)
