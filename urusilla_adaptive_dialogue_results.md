# Adaptive semantic dialogue experiment

## Result

The dependency-free reference accepted `26/26` deterministic positive dialogue messages, exercised exactly `7/7` canonical v0.1 wire acts, `20/20` typed interaction functions, and `46/46` typed node kinds, and rejected `20/20` representative negative cases with their expected fail-closed error codes. The corpus SHA-256 is `sha256:af65510aeb9a7bf26b0ccb265783cc3f0082fb37f183aea3f37527e68fb7ee13`.

This is **representational and protocol-mechanism coverage**, not proof of every human meaning, model understanding, task quality, energy savings, security against every adversary, or adoption. Raw natural language is not counted as native semantic coverage.

Machine status is `research_fixture_not_official_extension`. It pins core language version `0.1.0` and declares its relationship as `experimental_external_dialogue_projection`. It is not an official language version, extension, or standards claim.

## Architecture boundary

The first deployment target is the external LLM-to-LLM utterance layer. Internal reasoning remains model-specific. The protocol neither requires nor encourages disclosure of private chain-of-thought. It is a semantic payload/control layer over existing transports; it does not replace HTTP, TCP, A2A, MCP, routing, congestion control, or cryptographic identity infrastructure. Large image, audio, video, model, and dataset objects remain external content-addressed assets carried by typed `asset_ref` nodes.

The staged north star is:

1. Replace external agent dialogue where exact semantics and fragment-local fallback are demonstrated.
2. Extend typed exchange to tool and web information with schema, provenance, privacy, and asset-integrity gates.
3. Add model-native working-memory and action-state exchange through explicit schemas without exposing chain-of-thought.
4. Permit optional latent fast paths only for compatible hidden-state interfaces with an exact semantic decoder and fallback.
5. Evolve toward a federated Internet semantic control plane after open conformance and governance exist.

Every codec decision passes semantic exactness, receiver capability, authorization, latency, risk, privacy, hidden-state compatibility, provenance, energy/task-utility, and fallback gates before token cost is minimized.

## Typed dialogue coverage

Covered canonical wire acts:

`ASSERT`, `COMMIT`, `PROPOSE`, `QUERY`, `REQUEST`, `RESOLVE`, `RETRACT`

Covered typed interaction functions:

`ASSERT`, `CANCEL`, `CLARIFY`, `COMMIT`, `COORDINATE`, `CORRECT`, `COUNTERPROPOSE`, `DEFINE`, `DISCOVER`, `FAIL`, `NEGOTIATE_SCHEMA`, `NOT_UNDERSTOOD`, `PARTIAL`, `PROGRESS`, `PROPOSE`, `QUERY`, `REFUSE`, `REQUEST`, `RETRACT`, `SUCCEED`

Covered node kinds:

`action`, `action_state`, `asset_ref`, `assignment`, `budget`, `cancellation`, `capability_advertisement`, `capability_query`, `choice`, `claim`, `clarification`, `commitment`, `conditional`, `coordination`, `correction`, `definition`, `entry`, `evidence`, `failure`, `goal`, `literal`, `not_understood`, `operator`, `partial_result`, `plan`, `plan_step`, `policy`, `preference`, `progress`, `proposal`, `provenance`, `quantity`, `query`, `record`, `ref`, `refusal`, `request`, `retraction`, `schema_negotiation`, `splice`, `success`, `time`, `tool_result`, `uncertainty`, `web_fact`, `working_state`

The corpus covers assertion; query and clarification; request; capability discovery and advertisement; proposal and counterproposal; conditionals and choices; plan DAGs; commitments; refusal, cancellation, progress, partial result, success, and failure; retraction and correction; definition and schema negotiation; time, exact quantity, preferences, policy, and budget; uncertainty and evidence; multi-party coordination; and not-understood recovery. Tool results, web facts, working state, action state, provenance, and external modality references are also typed.

### Deterministic projection to the v0.1 wire

Interaction functions are inferred from typed body kinds and the closed `proposal.mode` enum; there is no free-form intent field or escape. Every message is rejected unless the inferred function projects to its declared canonical wire act.

| Interaction function | Typed body selector | Canonical wire act |
|---|---|---|
| `ASSERT` | `claim` | `ASSERT` |
| `ASSERT` | `evidence` | `ASSERT` |
| `ASSERT` | `uncertainty` | `ASSERT` |
| `CANCEL` | `cancellation` | `RETRACT` |
| `CLARIFY` | `clarification` | `QUERY` |
| `COMMIT` | `commitment` | `COMMIT` |
| `COORDINATE` | `coordination` | `PROPOSE` |
| `CORRECT` | `correction` | `ASSERT` |
| `COUNTERPROPOSE` | `proposal[mode=counter]` | `PROPOSE` |
| `DEFINE` | `definition` | `ASSERT` |
| `DISCOVER` | `capability_advertisement` | `ASSERT` |
| `DISCOVER` | `capability_query` | `QUERY` |
| `FAIL` | `failure` | `RESOLVE` |
| `NEGOTIATE_SCHEMA` | `schema_negotiation` | `PROPOSE` |
| `NOT_UNDERSTOOD` | `not_understood` | `RESOLVE` |
| `PARTIAL` | `partial_result` | `RESOLVE` |
| `PROGRESS` | `progress` | `RESOLVE` |
| `PROPOSE` | `proposal[mode=initial]` | `PROPOSE` |
| `QUERY` | `query` | `QUERY` |
| `REFUSE` | `refusal` | `RESOLVE` |
| `REQUEST` | `request` | `REQUEST` |
| `RETRACT` | `retraction` | `RETRACT` |
| `SUCCEED` | `success` | `RESOLVE` |

The conversation ledger produced:

- Ledger SHA-256: `sha256:0ae2147fa81c3822284740e41118f1bbea292aa2a060232b94e8d9b74b92ecc2`
- Final state machines: `4`
- Retractions recorded: `1`
- Corrections recorded: `1`

Append checks bind UUID replay protection, causal predecessors, monotonic logical clocks, conversation scope, task transitions, commitment debtor identity, execution-result ownership, cancellation rights, revision ownership, sender authentication, and effect scopes.

## Fragment-local code switching

The unsupported example fragment returned `replace_fragment` with requested fallback `urusilla-json-fixture@1`. Its patch contained only fields `fragment_id, kind, message_digest, patch_digest, replacement`; whole-message embedding was `false`. After replacement, status was `accepted` and every envelope field outside the body remained unchanged: `true`.

A splice pins fragment role, codec and version, schema and profile digests, payload digest, loss mode, fallback chain, and execution eligibility. Unsupported content requests replacement of that fragment only. Unknown, unverified, lossy, opaque, unauthorized, schema-unverified, or profile-unverified fragments cannot execute. An opaque natural-language bridge may be quarantined for a human or bridge decoder, but it never becomes native coverage merely by being carried.

## Receiver-token codec selection

The deterministic selection example chose `urusilla-wire-v02-fixture@1` at `500` receiver tokens after hard gates. Rejections were:

| Candidate | Hard-gate reasons |
|---|---|
| `latent-fast-path@model-a-to-b-v1` | `hidden_state_compatibility` |
| `privacy-leaking-codec@1` | `privacy` |

The numeric values in this selector example are deterministic fixtures, not measurements. The selector's tested property is ordering: no lower-token candidate can bypass a hard gate. A latent candidate is optional and must prove hidden-state compatibility; incompatibility routes to a semantic fallback rather than silently changing meaning.

## Continuous grammar evolution

- Base profile: `sha256:074498c7a6054c2759e96b0aeaea3f5e527962ed79180af3d7ef20d652cf1744`
- Immutable delta: `sha256:5ee939068aa36e099732c2a428020305a35c0a6eeb5ed19eef65f614e5f4fa70`
- Ephemeral session profile: `sha256:c126d6f790101acb65482717c86c6279170d7c88e698464fdb00ccf9c3a6533c`
- Ephemeral trial left global active profile unchanged: `true`
- Fixture-local ratified profile: `sha256:c126d6f790101acb65482717c86c6279170d7c88e698464fdb00ccf9c3a6533c`
- Signed approval evidence fixture: `sha256:7150fb46427335aad0bcd83c2ad9eb108a87f2b6c37f1e10a9bae2c72a4ea7ab`
- Post-rollback active profile: `sha256:074498c7a6054c2759e96b0aeaea3f5e527962ed79180af3d7ef20d652cf1744`
- Final proposal lifecycle state: `deprecated`
- Equivalent migration output kind: `literal_v2`
- Orphan codebook cache entry collected: `true`
- Immutable profile snapshots retained: `2`

A delta pins its base digest and sequence. The seven core wire acts are fixed; existing node, codec, migration, and deprecation records cannot be redefined in place. Non-equivalent migrations require explicit review. Promotion follows `proposed -> session_trial -> cross_play_candidate -> ratified -> deprecated`; session and cross-play evidence require exact round-trip with zero recorded semantic mismatches. Rollback changes the active pointer without deleting snapshots. Garbage collection removes only re-fetchable codebook bytes not referenced by active, live-session, migration, or pinned profiles.

During founder-led Experimental Stewardship, agents may propose, trial, and evaluate grammar changes, but core or official-extension meaning cannot be ratified without an externally verified, signed Founding Maintainer approval record bound to the proposal, delta, and target class. Automated scores and lifecycle events are evidence, never ratification authority. An ephemeral session-local delta is permitted only in negotiated non-core scope after every hard safety gate passes; it is pinned to the session, is not globally activated, and makes no ratification claim.

## Negative corpus

| Case | Expected code | Observed code | Rejected |
|---|---|---|---:|
| `message_replay` | `replay` | `replay` | true |
| `missing_cause` | `missing_cause` | `missing_cause` | true |
| `causal_clock_regression` | `causal_clock` | `causal_clock` | true |
| `unauthorized_effect` | `authorization_gate` | `authorization_gate` | true |
| `commitment_owner_mismatch` | `commitment_owner` | `commitment_owner` | true |
| `foreign_correction` | `revision_owner` | `revision_owner` | true |
| `illegal_task_transition` | `illegal_transition` | `illegal_transition` | true |
| `cross_thread_target` | `cross_thread_target` | `cross_thread_target` | true |
| `untyped_mapping_escape` | `node_kind` | `node_kind` | true |
| `raw_language_as_native` | `raw_language_escape` | `raw_language_escape` | true |
| `cyclic_plan` | `plan_cycle` | `plan_cycle` | true |
| `splice_payload_mismatch` | `splice_payload_digest` | `splice_payload_digest` | true |
| `unknown_executable_splice` | `splice_unknown_executable` | `splice_unknown_executable` | true |
| `whole_message_fragment_patch` | `fragment_patch_fields` | `fragment_patch_fields` | true |
| `capsule_base_mismatch` | `delta_base` | `delta_base` | true |
| `silent_node_redefinition` | `silent_redefinition` | `silent_redefinition` | true |
| `unsafe_automatic_migration` | `unsafe_migration` | `unsafe_migration` | true |
| `governance_lifecycle_skip` | `lifecycle_transition` | `lifecycle_transition` | true |
| `automated_metrics_cannot_ratify` | `founding_maintainer_approval` | `founding_maintainer_approval` | true |
| `all_codecs_fail_hard_gates` | `no_eligible_codec` | `no_eligible_codec` | true |

## Reproduction and artifact identity

```text
PYTHONPATH=. python urusilla_adaptive_dialogue.py
PYTHONPATH=. python -m unittest test_urusilla_adaptive_dialogue.py -v
```

Profile wrapper digest: `sha256:074498c7a6054c2759e96b0aeaea3f5e527962ed79180af3d7ef20d652cf1744`  
Profile file SHA-256: `a488e75c95c6948d24447a12fabd619f65612b4a698f0da85b3d1c719421ceac`  
`urusilla_adaptive_dialogue.py` SHA-256: `206135d02168076d0afce09e74c8c1c96c73f03f8dcc5451aaebd0ada545ff65`  
`test_urusilla_adaptive_dialogue.py` SHA-256: `7327da6efd069fb8fc31577f384ba3ebafd33dfb0ed57e8e754b5267cb701082`  

## Limits and next evidence

The profile is a designed vocabulary and the corpus was written against it, so full coverage is expected and in-sample. It does not establish open-world completeness. The grammar trial and cross-play implementations in this file are state-machine fixtures, not independent software implementations or model families. The selection costs are fixtures, not a performance benchmark. Content digests detect mismatch but do not provide signatures, confidentiality, identity, or trust by themselves. The included signed-approval record is a deterministic state-machine fixture, not a real Founding Maintainer signature or an official ratification; deployment must supply authenticated external signature verification.

The next credible gates are held-out human intent suites, independently implemented cross-play, multi-model task-success parity, privacy red teaming, authenticated provenance, equivalent natural-language baselines, measured receiver tokens/latency/energy, and adversarial governance tests. Internet-wide use should not be claimed before those gates pass.
