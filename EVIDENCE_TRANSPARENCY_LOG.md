# Urusilla Evidence Transparency Log MVP

Status: empty read-only integrity core implemented; no live intake; non-normative; no protocol-semantic change

This document specifies a minimal append-only transparency log for public
Urusilla evidence submissions. It is a transport and audit design around the
existing evidence contracts. It does not change the Urusilla language,
Capsule, result schemas, conformance rules, governance, or current evidence
boundary.

The repository now contains an intentionally empty, offline epoch-1 integrity
core at [`evidence-log/`](evidence-log/). It provides exact event, checkpoint,
log, and discovery schemas, a standard-library verifier, and positive and
negative vectors for the `quick_60s` track. It creates no live intake, bot,
HTTP service, domain, signing root, write automation, external result, or
verified external operator. The current demonstrated saving for general
communication between unfamiliar agents remains **0%**.

## 1. Purpose and non-goals

The log has four narrow purposes:

1. let a human, agent, or human-agent team submit a bounded public result;
2. preserve favorable, unfavorable, null, refusal, ambiguity, and failed
   results under the same append-only process;
3. make later deletion, replacement, review, and classification changes
   observable; and
4. let independent mirrors detect omission, reordering, or rewriting after a
   checkpoint has been published.

The log is not:

- an agent chat room, relay, execution service, model host, or package
  installer;
- an adopter list, reputation score, popularity ranking, or vote;
- a source of authority for tools, network access, persistence, spending,
  permission expansion, or external effects;
- a substitute for the Interop Lab, the initial-goal evaluator, an independent
  reproduction, or an authenticated provider receipt;
- a standards registry or a way to ratify protocol meaning; or
- a blockchain, coin, token, DAO, treasury, reward asset, mining system, or
  proof-of-work network.

Log inclusion proves only that the log operator recorded a particular event at
a particular position. It does not prove that the submitted assertion is true.

## 2. Relationship to existing project records

The existing evidence artifacts remain authoritative for their own bounded
purposes:

- [`INTEROP_LAB.md`](INTEROP_LAB.md) defines experiment classes, propagation
  evidence, per-hop disclosure, and matched evaluation requirements.
- [`initial_goal_eval/README.md`](initial_goal_eval/README.md) defines the
  frozen end-to-end claim gate and its receipt limitations.
- [`CONTRIBUTORS_EVIDENCE.md`](CONTRIBUTORS_EVIDENCE.md) credits evidence that
  passes its review gate.
- [`ADOPTERS.md`](ADOPTERS.md) remains a separate verified-adopter registry.
- [`PROVENANCE.md`](PROVENANCE.md) defines source attribution and evidence
  independence labels.
- [`GOVERNANCE.md`](GOVERNANCE.md) controls canonical releases and semantic
  ratification.

The transparency log may point to any of those artifacts by immutable digest.
It cannot alter them. A log state such as `structurally-valid` or
`accepted-as-evidence` never automatically inserts a contributor, verifies an
adopter, changes a claim, or ratifies a language feature.

## 3. MVP trust model

The GitHub repository is the proposed free publication surface, not a private
screening inbox. Only a candidate already reviewed for publication authority,
privacy, rights, and secret exclusion may enter a public issue or pull request.
Sensitive, unknown, or finite-retention material stays outside GitHub and the
log. No bot or write path is implemented. A future append workflow requires a
separate review and cannot treat transport acceptance as evidence acceptance.

GitHub issues, comments, reactions, stars, and pull-request descriptions are
mutable presentation surfaces. They are not the append-only log. The proposed
canonical log consists of committed canonical records linked by digest and
periodically summarized by checkpoints.

Git history alone is also insufficient. Repository administrators can rewrite
history, and a hosting provider can remove content. A hash chain detects a
rewrite only for a verifier that retained or obtained an earlier checkpoint.
The MVP therefore publishes checkpoints that independent parties may mirror.
It does not claim Byzantine consensus, global availability, permanent
retention, or protection from a fully compromised log operator.

## 4. Canonical log event

The implemented `quick_60s` event profile is
[`event-v1.schema.json`](evidence-log/schemas/event-v1.schema.json). The wider
multi-track object below remains a design contract, not an active machine
format. The implemented profile uses the distinct schema identity
`urusilla-evidence-log-quick60-event/1`, so it does not redefine the proposed
multi-track `/1` envelope. No live record may be inferred from the existence
of the schema.

Every event has exactly these top-level fields:

```json
{
  "schema_version": "urusilla-evidence-log-event/1",
  "log_id": "urusilla-github-evidence-log",
  "log_epoch": 1,
  "sequence": 1,
  "event_type": "submission-received",
  "previous_record_sha256": null,
  "prior_epoch_checkpoint_sha256": null,
  "continuity_reason_code": null,
  "recorded_at": "2030-01-01T00:00:00Z",
  "submission_id": "sub-example-001",
  "prior_submission_event_sha256": null,
  "state": "received",
  "state_reason": {
    "code": "initial-receipt",
    "public_detail": "Bounded public submission received."
  },
  "actor": {
    "accountable_id": "github:example",
    "role": "submitter",
    "automation_used": true
  },
  "evidence": {},
  "review": null,
  "privacy": {},
  "claim_boundary": {},
  "supersedes_submission_id": null,
  "superseded_by_submission_id": null,
  "record_sha256": "sha256:<64 lowercase hexadecimal characters>"
}
```

The empty `evidence`, `privacy`, and `claim_boundary` objects in this skeleton
stand for the exact subobjects in Sections 6 and 7; they are not valid live
values.

Unknown top-level fields are rejected. Optional information uses explicit JSON
`null`; omission is not silently interpreted as false or zero. Integers are
nonnegative where applicable and must not exceed the interoperable JSON safe
integer `9007199254740991`; larger quantities use canonical decimal strings in
a separately versioned field. Floating-point values are not permitted in the
log envelope; measured ratios use exact integer numerators and denominators or
decimal strings whose scale is declared by the referenced evidence schema.

### 4.1 Hash-chain calculation

For each event:

1. remove only `record_sha256`;
2. serialize the remaining object with RFC 8785 JSON Canonicalization Scheme;
3. encode the canonical text as UTF-8 without a byte-order mark or trailing
   newline;
4. calculate SHA-256 over those bytes; and
5. encode the result as `sha256:` followed by 64 lowercase hexadecimal
   characters.

The first epoch has `log_epoch: 1` and begins with zero events. Its empty
checkpoint has `tree_size: 0`, null first/last/head fields, and
`merkle_root_sha256: SHA256("")`. There is no synthetic genesis event. If a
separately reviewed append path is later implemented, the first real event has
`sequence: 1`, `previous_record_sha256: null`,
`prior_epoch_checkpoint_sha256: null`, and `continuity_reason_code: null`.
Every later event in the same epoch has a sequence exactly one greater than
the preceding event and sets
`previous_record_sha256` to the preceding event's `record_sha256`.
`prior_submission_event_sha256` is null only for the first event for one
submission; later state changes bind the previous event for that same
submission. Relative to an earlier checkpoint retained by a verifier, these
two links make global reordering and per-submission history splicing
detectable; an unanchored chain can still be rewritten and rehashed by its
operator.

If privacy, safety, rights, or law requires a destructive history rewrite, the
replacement log starts a new integer `log_epoch` and resets `sequence` to 1.
That first safe event sets `prior_epoch_checkpoint_sha256` to the last retained
non-sensitive checkpoint digest and supplies a bounded
`continuity_reason_code`; later events in the epoch set both fields to null.
The new epoch does not claim that removed data remains available, and the
continuity record must not include the removed content or a reconstructive
digest. A verifier keys positions by `(log_epoch, sequence)`, never by sequence
alone.

The record hash establishes content and order under this canonicalization. It
does not authenticate the actor, timestamp, reviewer, provider, model, or
evidence claim.

### 4.2 Event types

`event_type` is exactly one of:

- `submission-received` — first observation of a submission;
- `submission-state-changed` — append-only review state transition;
- `submission-superseded` — a correction points to a new submission while the
  old history remains visible;
- `submission-withdrawn` — the accountable submitter requests withdrawal from
  further review;
- `submission-retracted` — previously accepted evidence is withdrawn after a
  later error, integrity finding, or scope failure; or
- `submission-tombstoned` — canonical index and service presentation is
  restricted for privacy, legal, safety, or rights reasons.

A correction is a new submission with a new `submission_id` and
`supersedes_submission_id`. The old submission receives a
`submission-superseded` event whose `superseded_by_submission_id` names that
new submission. Competing proposed corrections do not change the current
result; review accepts at most one direct successor, and a later correction
must supersede that current successor. No correction overwrites an earlier
event.

## 5. Submission states

`state` is exactly one of the following:

| State | Meaning | Claim effect |
| --- | --- | --- |
| `received` | The transport accepted a bounded envelope. | None. |
| `quarantined` | Untrusted content is isolated for bounded validation. | None. |
| `needs-information` | Required public fields or immutable artifacts are missing. | None. |
| `structurally-valid` | The declared schema and content-addressed references reconcile. | Content consistency only. |
| `rejected` | A documented validation, safety, rights, duplication, or scope gate failed. | Preserved negative evidence where safe; no claim. |
| `accepted-as-evidence` | Review accepted the record at one explicitly named evidence class. | Only that bounded class; never automatic adoption or general efficiency. |
| `withdrawn` | The submitter ended review without deleting historical audit facts. | None. |
| `retracted` | Previously accepted evidence was removed from current evidentiary use after a later error, integrity finding, or scope failure. | Prior acceptance remains historical; no current claim effect. |
| `superseded` | A newer submission replaces the result for current review. | Earlier record remains historical. |
| `tombstoned` | The canonical index and service suppress a restricted payload and explain the bounded reason without repeating it. | None; this does not erase Git history, origin storage, caches, or mirrors. |

Allowed transitions are deliberately narrow:

- `received` -> `quarantined`, `needs-information`, `rejected`, or `withdrawn`;
- `quarantined` -> `needs-information`, `structurally-valid`, `rejected`,
  `withdrawn`, or `tombstoned`;
- `needs-information` -> `quarantined`, `rejected`, `withdrawn`, or
  `tombstoned`;
- `structurally-valid` -> `accepted-as-evidence`, `rejected`, `withdrawn`,
  `superseded`, or `tombstoned`;
- `accepted-as-evidence` -> `retracted`, `superseded`, or `tombstoned`;
- `retracted` -> `superseded` or `tombstoned`; and
- `rejected`, `withdrawn`, `retracted`, or `superseded` -> `tombstoned` only
  when later privacy, legal, rights, or safety review requires serving
  restriction; and
- `tombstoned` is terminal.

The bot may assign `received`, `quarantined`, `needs-information`, or
`structurally-valid` after deterministic checks. It may not automatically
assign `accepted-as-evidence`, an independence class, adoption, conformance,
or a project-wide performance conclusion.

## 6. Exact evidence envelope

The first event for a submission carries an `evidence` object with exactly the
following fields. Later events set `evidence` to null and refer to the first
event through `prior_submission_event_sha256`.

```json
{
  "track": "quick_60s | quick_10m | decode | matched_eval | propagation | counterexample | codec_candidate | corpus_example | other-bounded-public",
  "declared_experiment_class": "SAME-PROJECT-ORCHESTRATED | EXTERNAL-CONTROLLED | INDEPENDENT-CROSS-PLAY | ORGANIC-OBSERVATION | UNCLASSIFIED",
  "project_solicited": true,
  "participant_kind": "human | agent | human+agent",
  "accountable_submitter_uri": "https://github.com/example",
  "operator_id": "public or pseudonymous accountable operator identifier",
  "control_group_id": "identifier shared by accounts, agents, or runtimes under common control",
  "operator_relationships": [],
  "agent_assistance_disclosed": true,
  "runtime": {
    "provider": null,
    "model": null,
    "exact_version": null,
    "implementation_uri": null,
    "implementation_revision": null,
    "settings_sha256": null,
    "tokenizer": null,
    "tools_enabled": false,
    "memory_enabled": false
  },
  "method": {
    "preregistered": false,
    "plan_uri": null,
    "plan_sha256": null,
    "challenge_uri": null,
    "challenge_sha256": null,
    "repository_revision": null,
    "task_or_dataset_sha256": null,
    "prompt_or_wrapper_sha256": null,
    "scorer_sha256": null,
    "baseline_arms": [],
    "arm_order": [],
    "started_at": null,
    "completed_at": null
  },
  "payload": {
    "schema_uri": "immutable schema URI",
    "immutable_uri": "immutable public result URI",
    "sha256": "sha256:<64 lowercase hexadecimal characters>",
    "bytes": 0,
    "media_type": "application/json"
  },
  "outcome_summary": {
    "disposition": "exact | mismatch | counterexample | ambiguity | refusal | null | fallback | task-failure | completed",
    "decision": null,
    "task_success": null,
    "safely_completed": null,
    "parse_valid": null,
    "semantic_exact": null,
    "negative_rejected": null,
    "fallback_used": null,
    "total_tokens": null,
    "token_accounting_complete": false,
    "unauthorized_external_effects": null,
    "public_reason": "bounded public observation"
  },
  "receipts": [],
  "artifact_refs": []
}
```

The referenced `payload` remains the full evidence record and must validate
against its track-specific schema. The summary cannot replace it. A null
measurement remains null. A failed task, failed attempt, repair, fallback, and
its cost remain in the referenced payload rather than being removed from an
aggregate.

Every item in `receipts` and `artifact_refs` contains exactly:

```json
{
  "kind": "declared bounded type",
  "immutable_uri": "https://.../full-revision/...",
  "sha256": "sha256:<64 lowercase hexadecimal characters>",
  "bytes": 0,
  "media_type": "declared media type",
  "signature_status": "unsigned | declared | digest-verified | signature-verified | unknown"
}
```

An ordinary mutable branch URL, screenshot, star count, view count, or model
self-description is not an immutable artifact reference. Provider identity,
token usage, operator independence, and signature status remain unknown unless
their separate evidence is present and verified.

## 7. Review, privacy, and claim-boundary fields

For a state-change event, `review` is either null or an object with exactly:

```json
{
  "reviewer_id": "public accountable reviewer",
  "reviewer_role": "automated-structural-check | maintainer | independent-reviewer",
  "conflict_disclosed": true,
  "validator_uri": "immutable validator URI",
  "validator_sha256": "sha256:<64 lowercase hexadecimal characters>",
  "validation_result_sha256": "sha256:<64 lowercase hexadecimal characters>",
  "checked_payload_sha256": "sha256:<64 lowercase hexadecimal characters>",
  "decision": "pass | fail | incomplete",
  "verified_experiment_class": "SAME-PROJECT-ORCHESTRATED | EXTERNAL-CONTROLLED | INDEPENDENT-CROSS-PLAY | ORGANIC-OBSERVATION | UNVERIFIED",
  "accepted_evidence_scope": "bounded public evidence class or null",
  "public_reason": "bounded public rationale"
}
```

The submitter supplies only `declared_experiment_class`. The first event has a
null review. A later accountable review may set `verified_experiment_class`;
an automated structural check must set it to `UNVERIFIED` and
`accepted_evidence_scope` to null.

The `privacy` object is present on every event and has exactly:

```json
{
  "publication_authorized": true,
  "public_data_only": true,
  "contains_private_chain_of_thought": false,
  "contains_hidden_prompt": false,
  "contains_credentials_or_secrets": false,
  "contains_personal_data": true,
  "redistribution_basis": "author | license | explicit-permission | public-domain | not-applicable | unknown",
  "redactions_applied": false,
  "retention_limit": null
}
```

`unknown` redistribution basis cannot enter `accepted-as-evidence` when the log
would republish source material. A hash of a secret, short identifier, private
prompt, or personal datum can itself enable correlation or dictionary attack;
such material must not be submitted merely in hashed form.

An accountable public or pseudonymous account identifier may itself be
personal data. The log accepts only the minimum public identifier needed for
accountability, requires explicit publication authorization, and records
`contains_personal_data: true` when applicable. It rejects private, sensitive,
or unnecessary identity data. Because canonical Git records and mirrors do not
support reliable timed deletion, `retention_limit` must be null for a canonical
entry; data that requires a finite retention period stays outside this log.

The `claim_boundary` object has exactly these booleans, all false for
`submission-received` and all automatic bot transitions:

```json
{
  "log_inclusion_proves_truth": false,
  "log_inclusion_proves_independence": false,
  "log_inclusion_proves_reproduction": false,
  "log_inclusion_proves_adoption": false,
  "log_inclusion_proves_conformance": false,
  "log_inclusion_proves_general_efficiency": false,
  "log_inclusion_changes_project_claims": false,
  "log_inclusion_ratifies_protocol_semantics": false
}
```

An `accepted-as-evidence` event names its bounded class in
`accepted_evidence_scope`, but it does not flip these booleans. Stronger
conclusions live in the separately reviewed project artifacts that apply the
corresponding gates.

## 8. Independent-operator and Sybil rules

An operator is the accountable entity that controls prompts, credentials,
runtime policy, task selection, and publication—not a model call, process,
subagent, account, API key, or display name. Multiple agents or accounts under
one orchestrator count as one operator. Different vendors do not establish
independence when one operator controls the experiment.

The log applies these rules:

1. The submitter declares a `control_group_id` and every known operator,
   funding, employment, organizational, harness, prompt, dataset, and hidden
   coordination relationship material to the evidence class.
2. Unknown or undisclosed control never upgrades evidence. The safe review
   default is `verified_experiment_class: UNVERIFIED`, or
   `SAME-PROJECT-ORCHESTRATED` when common control is known.
3. A project-solicited run may still be useful external-model feedback, but it
   is not organic adoption and is not automatically independent reproduction.
4. One operator cannot approve its own `INDEPENDENT-CROSS-PLAY` or
   `ORGANIC-OBSERVATION` label. A conflict-disclosed reviewer must verify the
   immutable artifacts and operator relationship evidence.
5. GitHub accounts, email addresses, model providers, signatures, and public
   keys are identifiers, not proof that their controllers are distinct people
   or organizations.
6. Duplicate payloads, replayed receipts, coordinated accounts, copied
   rationales, shared hidden prompts, and implausible bursts are quarantined,
   not counted as independent votes.
7. Stars, forks, reactions, traffic, agent votes, token holdings, and submission
   volume never substitute for scientific evidence.
8. No private legal identity or government document is required by this MVP.
   When independence cannot be established without invasive collection, the
   class remains unverified.

Sybil resistance is therefore conservative classification plus disclosure,
not a claim that identity duplication can be solved by the log.

## 9. Safety and untrusted-submission handling

All submissions are untrusted data. A bot or reviewer must:

- parse only bounded declarative formats with fixed byte, depth, string,
  collection, and decompression limits;
- never execute submitted code, macros, notebooks, package installers, shell
  commands, remote tools, or embedded instructions;
- never fetch authenticated, private, paywalled, or local-network resources;
- allowlist public `https` artifact retrieval, cap redirects and bytes, and
  record the effective immutable URI and digest;
- reject credentials, secrets, private prompts, private chain-of-thought,
  private or unnecessary personal data, proprietary material, and content
  without publication rights;
- render untrusted text as inert text rather than HTML or executable markup;
- rate-limit by transport account and control group without treating the rate
  limit as identity proof; and
- preserve refusals, errors, and negative outcomes without exposing sensitive
  payloads.

Append-only audit is subordinate to privacy, safety, rights, and law. A
`tombstoned` event suppresses a payload only from the canonical index and
service; it cannot recall Git objects, origin storage, caches, or independent
mirrors. If sensitive material enters history, maintainers may have to remove
it at the origin, request downstream removal, and start a new log epoch after a
destructive repository rewrite. The new epoch and next safe checkpoint disclose
a non-sensitive continuity break and reason as defined in Section 4.1. They
must not repeat a secret or a reconstructive digest. This exception is why the
project must promise neither perfect immutability nor global erasure.

## 10. Checkpoints and optional Merkle proofs

The mandatory MVP integrity structure is the linear record hash chain. A
checkpoint contains exactly:

```json
{
  "schema_version": "urusilla-evidence-log-checkpoint/1",
  "log_id": "urusilla-github-evidence-log",
  "log_epoch": 1,
  "prior_epoch_checkpoint_sha256": null,
  "tree_size": 100,
  "first_sequence": 1,
  "last_sequence": 100,
  "head_record_sha256": "sha256:<digest of record 100>",
  "merkle_root_sha256": null,
  "repository_commit": "<40 lowercase hexadecimal commit>",
  "generated_at": "2030-01-01T00:00:00Z",
  "signature_status": "unsigned",
  "signer_id": null,
  "checkpoint_sha256": "sha256:<checkpoint digest>"
}
```

`checkpoint_sha256` uses the same canonicalization rule as a log event, with
only that field removed before hashing. Within one epoch, every checkpoint has
the same `log_epoch`; the first checkpoint of a replacement epoch carries the
same retained `prior_epoch_checkpoint_sha256` disclosed by that epoch's first
record. `signature_status: unsigned` is the only valid MVP status unless a
separately reviewed signing profile is actually implemented.

A later implementation may add `merkle_root_sha256`. To avoid an ambiguous
tree algorithm, it must use these leaves in record-sequence order:

- empty tree: `SHA256("")`;
- one record: `SHA256(0x00 || canonical_record_bytes)`; and
- more than one record: split at the largest power of two smaller than the
  record count and calculate
  `SHA256(0x01 || root(left) || root(right))` recursively.

`canonical_record_bytes` is the RFC 8785 UTF-8 serialization of the complete
stored record, including its already verified `record_sha256`, without a byte
order mark or trailing newline. Here `root(left)` and `root(right)` are raw
32-byte digests. A checkpoint with a Merkle root must also publish an
inclusion-proof format and consistency proof between successive tree sizes in
the same epoch. Merkle proofs improve efficient auditing; they do not prove
evidence truth, operator independence, or non-equivocation unless independent
observers compare checkpoints.

## 11. GitHub-first free transport

The proposed no-cost MVP flow, which is not implemented, is:

1. The operator prepares a bounded candidate outside public GitHub.
2. A restricted pre-publication review checks authorization, privacy, rights,
   secrets, sensitive digests, retention requirements, and bounded content.
   Failure or uncertainty stops publication; it does not create a public log
   event.
3. Only an eligible payload enters a payload-only pull request. Its first merge
   establishes the immutable repository commit that later events may cite.
4. A separate append pull request references that exact payload commit and
   proposes one canonical `submission-received` event at the next sequence.
5. Offline validation checks schema, size, digest, replay, duplicate,
   privacy-declaration, state, and claim-boundary invariants without fetching
   or executing submitted content.
6. A maintainer reviews and merges the append event. Neither the payload merge
   nor structural validation is evidence acceptance.
7. A separate check recomputes the chain and publishes a checkpoint for
   mirrors. Later reviews append state events; ordinary corrections never edit
   existing records.

The read-only subset now uses these repository paths; record assignment and
write transport are still not deployed:

```text
evidence-log/discovery.json
evidence-log/epochs/00000001/log.json
evidence-log/epochs/00000001/checkpoints/empty.json
evidence-log/schemas/event-v1.schema.json
evidence-log/schemas/checkpoint-v1.schema.json
evidence-log/schemas/discovery-v1.schema.json
evidence-log/schemas/log-v1.schema.json
evidence-log/verify.py
```

Pull requests serialize record assignment. Two submissions that race receive
their final sequence only after rebasing on the current head. A failed or
abandoned pull request is not a log event, though its original issue may remain
as transport history.

## 12. Machine discovery

Machines can inspect the local read-only discovery document at
[`evidence-log/discovery.json`](evidence-log/discovery.json) and verify its
bindings offline. `contribution-entry.json` does not yet carry a log pointer,
and none of the following HTTP endpoints exists.

A future public site is an interface over the same records, not a separate
source of truth. Its minimum human-facing pages are `/` for the honest current
evidence boundary, `/challenge` for one bounded reproducible task, `/submit`
for publication-authorized intake, `/ledger` for favorable and unfavorable
records, and `/verify` for local digest/proof instructions. Views, visits, and
submission counts may be shown as operational telemetry only; the primary
activation metric is the first structurally valid external submission, and the
scientific metric remains independently reviewed reproduction.

The GitHub-first implementation should publish `evidence-log/discovery.json`
with immutable or content-addressed pointers to:

- the event and checkpoint schemas;
- the current checkpoint and chain head;
- the supported submission tracks and existing track schemas;
- the issue and pull-request submission transports;
- the safety, privacy, governance, and claim-boundary documents; and
- the latest validator revision and digest.

A later HTTP service may expose:

| Method and path | Purpose |
| --- | --- |
| `GET /.well-known/urusilla-evidence-log` | Discover the log ID, schemas, head, transports, and policy links. |
| `GET /v1/log/checkpoint` | Return the latest canonical checkpoint. |
| `GET /v1/log/records?after=<sequence>&limit=<n>` | Page through canonical events in order. |
| `GET /v1/log/records/<record-sha256>` | Fetch one canonical event by digest. |
| `GET /v1/log/proofs/<record-sha256>?tree_size=<n>` | Fetch an inclusion proof when Merkle checkpoints exist. |
| `POST /v1/submissions` | Submit one bounded public envelope after explicit publication authorization. |
| `GET /v1/submissions/<submission-id>` | Read the current state and full append-only state history. |
| `GET /v1/schemas/<schema-id>` | Fetch immutable schemas and validator identities. |

The later API must use ordinary HTTP authentication and rate limits for write
abuse control, but read access to public log events should require no account.
An API credential grants only submission transport access. It grants no
protocol authority, evidence acceptance, persistence at an agent, spending,
or external-effect permission.

## 13. No coin, token, or pay-to-rank path

The MVP uses free GitHub facilities and ordinary volunteer review. It creates
no coin, proprietary token, NFT, staking, mining, points convertible to value,
treasury, DAO vote, paid inclusion, or pay-to-rank mechanism.

If the project later funds review, payment must remain separate from evidence
classification and semantic governance. Holding an asset, paying a fee,
submitting many records, or operating many agents cannot increase evidence
weight. A future blockchain may not become the identity oracle, semantic
authority, validator, benchmark judge, or mandatory transport. This follows
the anti-monoculture and no-token boundary in [`GOVERNANCE.md`](GOVERNANCE.md).

## 14. Why the log cannot upgrade a claim by itself

A complete hash chain can establish that a stated record was included in a
particular order. A Merkle proof can establish inclusion relative to a
checkpoint. Neither mechanism can establish:

- that the provider usage is authentic or normalized correctly;
- that a scorer evaluated the exact captured output;
- that a task, baseline, prompt, or stopping rule was frozen before results;
- that two accounts correspond to independent operators;
- that hidden coordination, selective reporting, or duplicate identities were
  absent;
- that an agent adopted Urusilla, retained it across sessions, or used it
  voluntarily;
- that a result generalizes across tasks, models, operators, or traffic; or
- that any current scientific threshold passed.

Those conclusions require their existing separate gates, receipts, operator
review, and statistical evaluation. The log preserves evidence for those
processes; it does not replace them. In particular, a thousand logged
submissions can still be one operator's project-solicited activity, and one
valid independent counterexample can be more scientifically important than a
large favorable submission count.

## 15. Implementation acceptance gates

The read-only core now supplies versioned schemas, an offline full-chain
verifier, immutable empty-log/checkpoint artifacts, privacy and claim-boundary
negative vectors, and explicit state/correction tests. Before changing it into
a live MVP, a separate reviewed pull request must still provide:

1. an externally reviewed standards-conformance check for the JSON Schemas and
   canonicalizer, beyond the dependency-free profile verifier;
2. replay, duplicate, cross-submission splice, and concurrent append tests for
   the proposed two-pull-request append workflow;
3. bounded retrieval limits and malicious-submission fixtures; the current
   core performs no retrieval;
4. restricted pre-publication content and rights review, including detection
   beyond the current fail-closed declarations for secrets and sensitive
   digests;
5. explicit GitHub permissions, branch protection, reviewer separation, and
   recovery procedures;
6. a checkpoint publication and mirror-verification procedure;
7. a two-step append flow in which an external payload is first merged at an
   immutable commit and a maintainer appends the event only in a separate pull
   request; and
8. an external review of the claim boundary before any public launch wording.

Until those gates pass, the implemented artifacts remain an empty read-only
integrity demonstration rather than a live log.
