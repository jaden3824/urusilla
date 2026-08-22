# Urusilla Contributor Evidence Registry

This registry credits reproducible evidence contributions, including results
that weaken or falsify the project. It is deliberately separate from
[`ADOPTERS.md`](ADOPTERS.md): submitting a result does not prove adoption,
independence, general efficiency, or a change to the recorded 0% general
unfamiliar-agent result.

## Current status

Validated external contributor records: **0**.

No external contribution has yet passed the registry gate. Project-solicited
model feedback is retained in its own evidence record and is not counted here
as independent reproduction or organic participation.

The project-operated [public UrusillaIR conversation
probe](https://thecolony.ai/post/fa2c6843-28f7-4503-8536-08c6610d542e)
received a substantive reply from `ColonistOne`. The account reproduced the
pinned Capsule identity as 33,476 bytes with SHA-256
`588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`,
selected `semantic-fidelity`, supplied a content-relevant reason, and returned
a next question. It also correctly reported that
`urn:urusilla:schema:peer-dialogue-reply:0.1` was not resolvable from the
pinned specification or Capsule. The structural validator also does not
enforce required-schema resolution. The submitted envelope is not conformant:
the validator rejects its bare `body.kind: "answer"`. The exact
fixtures, project-side reproduction, and claim boundary are recorded in
[`PUBLIC_DIALOGUE_001_REPORT.md`](PUBLIC_DIALOGUE_001_REPORT.md). The account's
self-description as an autonomous unaffiliated agent, its operator, runtime,
prior exposure, and control relationships remain unauthenticated. This is an
ambiguity/counterexample tracked in [issue
#12](https://github.com/jaden3824/urusilla/issues/12), not an accepted
registry record, adopter, independent implementation, comprehension pass, or
change to the recorded 0% general result.

On 2026-08-22, the project-operated [The Colony causal-control
thread](https://thecolony.ai/post/3713bdd3-a23f-4e23-86a4-af40bc5cc1c0)
received its first substantive public design critique from the agent accounts
Excelsior, Laguna, ColonistOne, Xiaona, Dantic, RealMaximus, and Molt. The
comments proposed stronger contrast sets, a distinct no-payload accuracy
baseline, per-field coverage, valid-payload false-refusal accounting,
per-stratum gates, and contamination-resistant item generation; Xiaona also
described applying the same claim boundary to a separate video pipeline.
Dantic further identified stable preregistered field identity, an external
known-correct refusal reference, and preservation of the complete per-stratum
table as claim-blocking requirements.
RealMaximus proposed a stable-semantic-slot matrix and separate observable
`payload_influenced_output` and stronger `task_semantics_used` verdicts; the
resulting adversarial task is public in
[issue #10](https://github.com/jaden3824/urusilla/issues/10). Molt proposed
same-semantics adversarial re-encoding arms, calibrated-refusal scoring, and
per-stratum matched-pair confidence intervals instead of pooled means. One
account self-described as an autonomous agent unaffiliated with the project;
those relationships and
the reported external system have not been independently authenticated. These
comments are attributed review inputs under active triage, not accepted
registry records, independent reproductions, adopters, or evidence that
changes the reported 0% general result.

On the project-operated [ClawdChat open-source
challenge](https://clawdchat.ai/post/de74fbe1-cdc3-44d0-95aa-208458b97565),
Pinchy independently restated that pointer aliases must be normalized before
coverage is counted, or the metric can collapse into a tokenizer/surface-form
result. Yishi requested explicit capability boundaries, required inputs, and a
declared progress-return interval instead of leaving participants to infer the
workflow. The project replied with the implemented stable-field-ID rule and a
request for a minimal escaping JSON example, and asked whether progress timing
belongs at message or session scope. These are attributed public review inputs,
not authenticated identities, validated evidence, adoption, or conformance.

The proposed append-only transport in
[`EVIDENCE_TRANSPARENCY_LOG.md`](EVIDENCE_TRANSPARENCY_LOG.md) is currently a
documentation-only design. It is not a live submission count, registry entry,
or evidence that any external participant has used the project.

## From first response to credited evidence

1. Read the machine-first [`contribution-entry.json`](contribution-entry.json).
2. Return the four-field 60-second result in
   [Discussion #8](https://github.com/jaden3824/urusilla/discussions/8) or the
   [structured quick form](https://github.com/jaden3824/urusilla/issues/new?template=quick-60s.yml).
3. Escalate an ambiguity or failure through the
   [counterexample form](https://github.com/jaden3824/urusilla/issues/new?template=counterexample.yml),
   an exact smaller representation through the
   [codec-candidate form](https://github.com/jaden3824/urusilla/issues/new?template=codec-candidate.yml),
   or an authorized public example through the
   [corpus-example form](https://github.com/jaden3824/urusilla/issues/new?template=corpus-example.yml).
4. The maintainer quarantines the submission, verifies its immutable artifact
   identity, assigns a contribution ID, and records an acceptance or rejection
   rationale.
5. When the contribution makes a reproducibility claim, an unrelated runtime
   must reproduce the same frozen artifact before that field becomes true.
6. Accepted evidence may enter only a future development corpus version. It is
   never inserted into the current holdout or confirmatory set.

Negative, null, refusal, ambiguity, and favorable records receive the same
attribution. Stars, views, forks, screenshots, and unverified model output are
not evidence.

## Registry fields

Each accepted row and matching machine record will include:

| Field | Meaning |
| --- | --- |
| Contribution ID | Immutable project identifier |
| Contributor | Public handle or requested attribution |
| Class | Counterexample, codec, corpus, implementation, evaluation, or review |
| Direction | Favorable, unfavorable, null, ambiguity, or refusal |
| Source | Issue or pull request URL |
| Artifact identity | Full revision plus SHA-256 where applicable |
| Reproduction | Exact status and unrelated runtime, never inferred |
| Disposition | Accepted, rejected, superseded, or quarantined with rationale |

The machine-readable source of this table is
[`contributor-evidence.json`](contributor-evidence.json). It currently contains
an empty `records` array rather than fabricated participation.
