# Read-only evidence-log integrity core

Status: offline, empty, read-only epoch 1; no bot, network access, submission
transport, automatic append, signing key, or public intake.

This directory implements the smallest integrity core for exactly one bounded
track: [`quick_60s`](../interop_lab/challenges/quick_60s.json). It does not make
the transparency log live and does not record any external result. The
canonical log intentionally contains **zero events**.

## Empty epoch semantics

Epoch 1 exists before its first event. Its empty checkpoint has `tree_size: 0`,
null first/last/head fields, and the Merkle root `SHA256("")`. There is no
synthetic “genesis event.” If a separately reviewed append workflow is ever
implemented, the first real submission event is sequence 1 with both global
and per-submission predecessor fields null. Later events use consecutive
sequences and exact predecessor digests.

This removes the former ambiguity between “empty log” and “genesis event.” The
empty checkpoint proves only the content of this empty epoch snapshot. It is
unsigned and cannot establish non-equivocation unless independent observers
retain and compare it.

## Privacy gate before public eligibility

An intake candidate is **not** a canonical event. Before an event can be
eligible for this public Git-backed chain, the offline verifier requires all
of the following declarations:

- explicit publication authorization and public-data-only status;
- no private chain-of-thought, hidden prompt, credentials, secrets, or
  sensitive/reconstructive digest;
- only no personal data or a minimized accountable public identifier;
- a known redistribution basis; and
- no finite retention requirement.

The verifier fails closed on any contrary or unknown declaration before it
accepts the event shape or chain transition. This is only a deterministic
declaration gate; it cannot discover an undeclared secret or infer legal
rights. A future intake system therefore needs separate restricted content
review before constructing a candidate event. Public issues and pull requests
must not be used as a pre-screening inbox.

## State and correction semantics

Each submission starts exactly once at `received`. Allowed transitions are
implemented in `verify.py`; no implicit reopen exists. Retraction is a new
event from `accepted-as-evidence`, never an edit. Tombstoning is terminal and
cannot promise deletion from Git objects, caches, or mirrors.

A correction is a new submission whose first event names the old
`submission_id`. Only one direct successor may be pending. The old submission
does not become `superseded` until that exact successor reaches
`accepted-as-evidence`; then a separate `submission-superseded` event links it.
A later correction must supersede the accepted successor, not an earlier
ancestor. Earlier events remain historical. No correction can silently replace
or improve an old result.

## Verify offline

From the repository root:

```sh
python3 evidence-log/verify.py --vectors
```

The verifier uses only the Python standard library, performs no network calls,
and has no mutation mode. It checks bounded JSON parsing, exact fields,
privacy eligibility, claim-boundary invariants, event and submission hash
chains, correction/state rules, the log digest, the empty checkpoint, and
discovery bindings. Discovery also binds the exact schema and verifier bytes,
so an earlier retained discovery digest exposes later local replacement.
Static positive and negative vectors live in
`test-vectors/`; unit tests add mutation coverage.

## Claim boundary

Inclusion would prove only that one byte-equivalent event occupied one
position relative to a retained checkpoint. It would not prove truth,
independence, reproduction, adoption, conformance, general efficiency, a
project claim change, or semantic ratification. This core creates no external
submission and no verified external contribution.
