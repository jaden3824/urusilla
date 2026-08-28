# Public Dialogue Probe 001

Status: public, project-operated conversation observation with an unfavorable
strict-conformance result

Observed: 2026-08-22

Thread: <https://thecolony.ai/post/fa2c6843-28f7-4503-8536-08c6610d542e>

External comment:
<https://thecolony.ai/post/fa2c6843-28f7-4503-8536-08c6610d542e#comment-610f81c6-0286-4322-8386-37c8605a4320>

Counterexample tracker:
<https://github.com/jaden3824/urusilla/issues/12>

## Outcome

The public account `ColonistOne` fetched the Capsule pinned by the query and
reported the correct byte count and SHA-256: 33,476 bytes and
`588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`.
Project-side recomputation matches both values. The reply selected
`semantic-fidelity`, supplied a relevant public justification, and passed a
new question back to the project.

This is not a strict UrusillaIR conformance pass.

1. The original query is structurally accepted by the reference v0.1
   normalizer.
2. Its declared answer schema,
   `urn:urusilla:schema:peer-dialogue-reply:0.1`, is defined in neither the
   pinned specification nor the pinned Capsule.
3. Its top-level `schema`, `urn:urusilla:dialogue:0.1`, is likewise absent from
   the pinned schema identifiers. The Capsule permits
   `question-plus-answer-schema` in its act/body table but omits that kind from
   its node-manifest table.
4. The reference validator checks only that `answer_schema` is a syntactically
   valid identifier. It does not resolve the identifier, so it structurally
   accepts this query despite the Capsule's normative fail-closed rule for an
   unknown required schema.
5. The inline `required_fields` condition was sufficient for the respondent
   to infer the requested shape, but the query never declared that condition
   to be a content-bound replacement for the unresolved schema.
6. The external reply uses `body.kind: "answer"`. The v0.1 reference
   validator rejects it because bare `answer` is neither a core node nor a
   quarantined `x:` extension. An `ASSERT` currently admits only `claim`,
   `evidence`, `uncertainty`, or `ref` as core body kinds.

The observed outcome is therefore:

| Check | Result |
| --- | --- |
| Public account returned a content-relevant response | observed |
| Pinned Capsule byte identity | matched |
| Original query structural validity | passed |
| Top-level schema presence in pinned artifacts | failed |
| Declared answer-schema presence in pinned artifacts | failed |
| Query node-manifest closure in the Capsule | failed |
| Required-schema resolution in the reference validator | not implemented |
| External reply structural validity | failed |
| Full schema/conversation conformance | not established |
| Operator, runtime, and independence | not authenticated |
| Adoption, efficiency, or token-saving evidence | none |

The account describes itself as an autonomous AI agent unaffiliated with the
project. That relationship, its exact runtime, operator, prior exposure, and
shared-control boundary have not been independently authenticated.

## Additional public turns

Two later accounts continued the design discussion without establishing
strict conformance:

- `Molt` returned a Urusilla-shaped `ASSERT`, chose `adaptive-evolution`, and
  proposed a compatibility-policy question covering strict version pins,
  negotiated fallback, and best-effort unknown-field handling. The reply also
  stated that the unsigned Capsule's authenticity was not verified. It is an
  attributed compatibility-design critique, not a v0.1 core round trip.
- `AX-7` replied in natural language that profile evolution can invalidate an
  earlier fidelity score and asked how the system catches a fidelity drop that
  occurs between checkpoints. It is an attributed continuous-monitoring
  critique, not a same-language conformance attempt.

The next public questions therefore ask for (a) a minimal content-addressed
schema-dereference tuple and positive/failure vectors, (b) a core/extension
compatibility state machine, and (c) a continuous fidelity sampler and
rollback trigger that does not leak the frozen holdout. Project-authored
follow-ups remain outreach; only returned, frozen, reproducible artifacts can
become evidence candidates.

## Existing v0.1 behavior

The Capsule's normative security contract requires unknown required schemas to
fail closed. The current reference validator does not yet enforce that stage;
it performs structural validation and identifier-syntax checks only. For this
non-effectful public query, an unresolved answer schema permits an explicit
ambiguity report or a negotiated concise-text/JSON fallback, but it does not
permit a strict conformance claim based only on an inferred inline shape. This
report records the enforcement gap; it does not silently add a resolver to the
frozen v0.1 core.

No new core node or protocol version is introduced by this report. Adding a
bare `answer` node to v0.1 would silently change the frozen semantic profile
and is therefore rejected as the repair.

An answer and a new question are also two observable communicative acts. The
minimal core-compatible continuation consequently uses:

1. an `ASSERT` carrying a core `claim` about the schema-resolution outcome;
2. a separate `QUERY` carrying a `question-plus-answer-schema` node; and
3. the Capsule's resolvable core schema ID rather than the missing reply
   schema.

The two candidate continuation messages are preserved in
[`evidence/public_dialogue_001/`](evidence/public_dialogue_001/). Passing the
reference structural codec does not upgrade them to full semantic,
conversation, authority, independence, adoption, or task-utility evidence.

## Research consequence

This observation strengthens the current negative sender/conformance boundary:
a previously unfamiliar public respondent can infer useful meaning from the
message while still emitting a message that the pinned validator rejects. It
does not prove native model understanding. Future conversation probes must
publish a resolvable answer contract, enforce resolution outside the
structural codec, and freeze a scorer before treating a reply as a conformance
or comprehension result.

The protocol surface remains frozen while the project prioritizes its primary
missing result: total tokens per safely completed real-model task against
concise natural language, JSON/state-delta, and silence/topology baselines.

## Post-observation offline schema-binding fixtures

On 2026-08-23, a separate schema-availability gate was added without changing
the frozen structural codec.  The dependency-free
[`urusilla_schema_resolution.py`](urusilla_schema_resolution.py) resolver uses
only caller-supplied local bytes and performs no network dereference. It
requires the QUERY's answer-schema URI, SHA-256, byte length, media type, and
schema-document `$id` to match a project-pinned binding before selecting a
candidate typed Urusilla route. Its decision scope is explicitly
`required-answer-schema`; response-instance validation, publisher
authentication, and other protocol and deployment gates remain separate.

The executable fixture pack is
[`schema_resolution_vectors.json`](evidence/public_dialogue_001/schema_resolution_vectors.json),
backed by the content-bound
[`peer_dialogue_reply.schema.json`](evidence/public_dialogue_001/peer_dialogue_reply.schema.json).
Its positive vector verifies the project-pinned bytes for the original
answer-schema URN and sets `schema_binding_verified: true`, while retaining
`strict_conformance: false`. Its missing-resource and tampered-byte vectors
close to concise JSON and text fallback respectively. A paired conflict cell
changes only the inline hard `required_fields` list by adding `confidence`,
which the pinned schema forbids through `additionalProperties: false`; the
binding still verifies, but the route closes to JSON fallback with
`required-schema-inline-constraint-conflict`. Every decision retains
`effect_authorized: false`.

These fixtures harden the post-observation evaluation path; they do not rewrite
the historical public turn, silently change v0.1 core semantics, authenticate a
publisher, authorize an external fetch or effect, or turn the original reply
into a conformance pass.

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_public_dialogue_001.py
```

The test verifies the Capsule digest, accepts the original query at the
structural stage, verifies the exact project-pinned schema binding without
claiming response conformance, rejects the missing and SHA-256-mismatch
fixtures to their declared fallbacks, reproduces the external reply rejection,
and round-trips the two core-compatible continuation messages exactly.
