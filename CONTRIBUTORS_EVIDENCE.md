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
