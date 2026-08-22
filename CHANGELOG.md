# Changelog

All notable public changes to Urusilla are recorded here. Semantic-language
versions, software-package versions, and release labels are separate axes; see
the versioning section of the specification before comparing identifiers.

## Unreleased

- Internal initial-goal TRACE, arm-manifest, assembly, and receipt evidence
  formats now have fail-closed v2 paths for exact scored-output binding,
  provider-response replay detection, canonical silence, explicit no-output
  failures, and completed-primary semantic validation before fallback.
- A documentation-only append-only evidence transparency-log and future
  website/API design is available; no live log, domain, or submission service
  is deployed.
- Public contribution guidance now has a no-install "bring your own agent"
  path. Matched submissions still require the published task, receipt, and
  verifier contracts and do not become accepted or independent evidence merely
  by being submitted.
- The installed receipt verifier no longer imports research-only replay
  adapters, restoring isolated wheel imports without weakening trace checks.
- These are evaluation-infrastructure changes, not a semantic-language version
  promotion. General unfamiliar-agent token saving remains demonstrated at
  0%, and real provider authentication and independent evaluation are absent.

## v0.1.0-experimental - 2026-08-20

First public research prerelease. The Python package version is `0.1.0a0` and
the semantic-language version is `0.1.0`.

### Included

- a deterministic typed semantic representation and canonical `URSL` wire
  codecs with bounded public decoders;
- a content-addressed experimental Grammar Capsule and source-manifest schema;
- a private experimental A2A bridge with activation, identity-binding, size,
  and provenance checks;
- warm-session, tokenizer-aware, transparent-fallback, and checkpointed-delta
  research profiles with exact fallback paths;
- terse English, JSON, compression, CBOR, MessagePack, Protobuf, mutation,
  reset, and external-example baselines;
- a same-project Node.js cross-runtime implementation and Python/Node adoption
  kit;
- reproducible negative results, claim gates, governance, provenance, security,
  contribution, and help-wanted documents.

### Security and integrity

- decoders reject duplicate JSON members, malformed Unicode, noncanonical
  integers and floats, recursive executable extensions outside allowed acts,
  over-budget semantic graphs, and invalid typed QUERY forms;
- conversation state is scoped by conversation and thread, and target-changing
  acts require causal reachability;
- checksums detect accidental corruption but do not authenticate an active
  peer; the release remains unsigned and effect-authorizing behavior is
  disabled.

### Claim boundary

- no external adopter is verified;
- no state-of-the-art, world-record, standards-conformance, security-audit,
  energy-saving, or end-to-end task-utility claim is made;
- favorable warm in-domain and synthetic repeated-state results coexist with
  unfavorable, fallback-only, and tie-only external results;
- the bundled Node.js lane is project-authored and oracle-derived, not an
  external independent reproduction.
