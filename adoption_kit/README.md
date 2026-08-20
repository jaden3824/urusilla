# Urusilla Adoption Kit

This isolated Urusilla kit is a local, adoption-first integration example for the repository's current experimental typed semantics and negotiated codecs.

It is not a standard, an official A2A or MCP extension, a signed release, a production security profile, or evidence of external adoption. Its exact lifecycle is `experimental-unsigned`. The source may be distributed publicly with its exact checksum, but this kit performs only local read-only work, creates no network I/O, and authorizes no external effect. Effect-authorizing or production use requires a trusted publisher signature and an independent authorization policy.

## What it provides

- A standard-library-only Python SDK that wraps the root canonical validator, wire v0.1, benchmark-specialized warm wire v0.2, deterministic JSON, and Controlled Terse English.
- A dependency-free Node SDK for the cross-runtime JSON subset. Node advertises compact binary profiles as relay-only and never pretends to decode them.
- Capability discovery with separate `bridge`, `native`, and `fallback` modes. Native is explicitly unsupported because this kit has no independent native-evidence verifier.
- Exact language, Capsule, profile, dictionary, and per-sender `source_id` pins.
- Cold/warm cache accounting that separates a pure plan from an explicit, digest-verified, one-shot in-memory artifact transfer. No transfer is inferred from negotiation.
- Local A2A-v1-shaped and MCP-friendly wrappers. Their identifiers and shapes are private examples, not conformance claims.
- One-agent onboarding and Python-to-Node structural cross-play demos.
- Telemetry that is off by default, content-free, locally signed, replay/rate/sequence checked, and aggregated with abuse heuristics.
- A verified-safe-message adoption metric whose value is zero unless an independent external verifier exists. A separate synthetic local-HMAC metric cannot become an external-adoption claim. Downloads, stars, and repository activity are not inputs.

## Quick start

Run the Python onboarding example:

```text
PYTHONDONTWRITEBYTECODE=1 python3 adoption_kit/examples/one_agent_onboarding.py
```

Run the local two-agent Python/Node cross-play example:

```text
PYTHONDONTWRITEBYTECODE=1 python3 adoption_kit/examples/two_agent_crossplay.py
```

Run the isolated tests:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s adoption_kit/tests -v
node --test adoption_kit/node/test/*.test.js
```

The examples use synthetic 32-hex source placeholders. A deployment must instead validate a complete source manifest, derive its `source_id`, pin it during discovery, and preserve it on each hot message. An unsigned or unresolved source remains non-effect-authorizing.

## Selection behavior

The Python selector considers only representations that both endpoints can encode and decode. Relay-only support is not endpoint support. It computes exact local JSON-envelope and planned cold bytes without mutating a cache. `prepare_session_artifacts` verifies and installs exact bytes in memory and issues a one-shot accounting receipt.

The v0.2 profile is benchmark-specialized. It is eligible only when all of these match exactly:

- language version `0.1.0`;
- Grammar Capsule SHA-256 `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`;
- profile ID `1`;
- profile capsule SHA-256 `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6`; and
- dictionary ID `7d12fc414eae60b2`.

An ID match alone is never sufficient. A v0.2 decoder builds an explicit registry from the exact canonical profile capsule.

## Fallback and authority boundary

JSON fallback is selected only when the message fits the receiver's declared numeric and byte-value limits. The Node endpoint rejects integers outside JavaScript's safe range, byte values, non-finite numbers, duplicate JSON members, non-canonical JSON, and unknown semantic structures.

Controlled Terse English is a deterministic, exactly reversible serialization over canonical typed IR. It is not free-form prose. Human summaries from the root translator are views only and are never parsed as authority.

Every delivery carries `effect_authorized: false`. `REQUEST` and `PROPOSE` do not create obligations. Structural `COMMIT`, `RESOLVE`, or `RETRACT` data still requires authenticated identity, replay protection, policy authorization, budgets, a conversation-state validator, and a signed production profile outside this kit. The current unsigned Capsule cannot authorize effects.

## Privacy and telemetry

No telemetry is emitted by the SDK. The telemetry module only creates local event objects after `telemetry_opt_in=True`. Its closed allowlist excludes message bodies, prompts, answers, user/account/device identifiers, IP addresses, source URIs, exact timestamps, message IDs, and session IDs.

Rotating pseudonyms are monthly HMAC derivatives. Events use UTC day buckets, one-use nonces, exact sequences, per-day limits, local HMAC validation, lifecycle checks, and local evidence tiers. Shared-evidence and synchronized clusters are discounted only in the separately labeled synthetic metric; local-key fanout receives zero weight. These are heuristics, not anti-Sybil proof, identity proof, independence proof, or evidence of unique humans or deployments. The JSON Schema is structural documentation; `telemetry.py` is normative for lifecycle, HMAC, replay, rate, and attestation rules.

## Evidence boundary

The included cross-play is one local Python process and one local Node process exchanging a synthetic message through standard input/output. It is project-authored structural interoperability evidence, not an unseen external partner, independent implementation, model comprehension test, task-success result, or external adoption record.

The Grammar Capsule's embedded reference-codec SHA-256 matches the observed pinned `urusilla.py`. Discovery still sets `support_claim_eligible: false` and `provenance_bound: false` because this is an unsigned worktree with no external conformance verifier. Public source distribution does not change the local read-only operational boundary.

See `INTEGRATION_REPORT.md` for exact artifact digests, test results, measured local friction, and cold/warm accounting.
