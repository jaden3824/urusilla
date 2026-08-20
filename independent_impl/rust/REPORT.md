# Cross-language implementation report

Status: same-project vector-compatibility evidence  
Snapshot date: 2026-08-20  
Requested language: Rust  
Executed fallback: dependency-free ECMAScript on Node.js

## Outcome

This lane is a separately written, project-internal ECMAScript implementation used because `rustc`, `cargo`, and `rustup` were unavailable. Its runtime implementation, CLI, tests, and evidence freezer have no Python dependency. Python is used only by the checked-in fixture generator.

The frozen run establishes the following narrow result:

- 55/55 Node tests and subtests pass;
- 280/280 Python-oracle-derived v0.2 frames encode byte exactly, decode semantically, and re-encode canonically;
- the 280 warm frames total 54,752 bytes;
- the four-byte-length-prefixed sequence is 55,872 bytes with SHA-256 `cb167208d26fc90caa36761504cbcdd6be070c5b1e18370b420c04b1fcd72c00`;
- 25/25 negative frame and `URCP\x02` capsule fixtures fail closed;
- one low-bit flip at every byte position of the selected frozen frame is rejected; and
- the 1,402-byte default profile capsule has SHA-256 `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6` and dictionary ID `7d12fc414eae60b2`.

The accurate claim is: a separately written same-project Node implementation shows offline byte agreement against fixtures deterministically derived from the current Python oracle. This is not an independent external reproduction, clean-room implementation, external adoption event, live cross-vendor exchange, security certification, or full-project conformance result.

## Evidence provenance

`tools/generate_python_oracle_vectors.py` regenerates:

- the exact 223-byte `URSL\x01` public v0.1 vector from the current Grammar Capsule;
- 280 `URSL\x02` positive frames from the deterministic 280-message corpus;
- 25 fail-closed negative frame/capsule vectors;
- the current-oracle cross-check; and
- the exact 250,000/250,001 semantic-node boundary probe.

The source pins are:

| Input | SHA-256 |
| --- | --- |
| `urusilla.py` | `3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf` |
| `urusilla_wire_v02.py` | `166b1090b536bfff942667d43be583b2345eeb14b9da5d1535b7a16bb6bab2e7` |
| `urusilla_benchmark.py` | `b5e2885f7e17097643c1e93ba3326f285cd37aa8199cf1cc3b234227e515b5f8` |
| `urusilla_v0_1_spec.md` | `4d817a607218f64998e1c0b061f80f07b400b382236485f2a2e7b88f6e92b263` |
| `urusilla_capsule_v0_1.json` | `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27` |

The Grammar Capsule's declared semantic-manifest digest equals an independent compact sorted serialization of the current manifest. The Capsule's embedded reference-codec digest also equals the pinned `urusilla.py` digest.

The Capsule lifecycle is exactly `experimental-unsigned`. Exact-checksum public source distribution is allowed, but unsigned execution is limited to local read-only research and conformance work. Effect-authorizing or production use requires a trusted publisher signature and an independent authorization policy.

## Resource boundary

The Python and Node implementations now share one aggregate budget across `body` and `meta`. Every scalar, byte string, list, and map counts once; map key names do not add semantic-value nodes. The checked probe accepts exactly 250,000 values and rejects the checksum-valid 250,001-value frame before effects.

This is a deterministic boundary test, not a memory benchmark, worst-case proof, or security certification. Per-frame/capsule size remains 16 MiB. The Node CLI separately allows up to 192 MiB of fully tagged JSON because type tags and Base64 can expand a valid binary frame; that local document cap is not a wire rule.

## Implemented subset

- Canonical top-level defaults and the closed seven-act vocabulary.
- Selected v0.1 core-node validation, act/body compatibility, causal references, and local `x:` quarantine.
- Exact signed/unsigned 64-bit integers, typed finite binary64, bytes, Unicode-scalar strings, lists, and maps.
- Deterministic UTF-8 map ordering, shortest varints, canonical positive zero, and canonical re-encode checks.
- v0.2 static-profile capsule and warm-frame encode/decode with explicit profile registry and dictionary fingerprint.
- Fully tagged, collision-free portable JSON and bounded CLI input.

Authentication, signatures, authorization, replay policy, effect execution, schema registries, A2A bindings, gzip, UrusillaLens, adaptive profiles, and general RFC 8785 canonicalization remain outside this lane.

## Reproduction

```text
cd independent_impl/rust
npm run generate
npm test
npm run verify
npm run freeze
npm run check-digests
```

`npm run generate` invokes the same-project Python oracle and is evidence maintenance, not a Node runtime dependency. `npm test`, `npm run verify`, and `npm run freeze` execute the Node implementation only. The freezer uses a fixed `SOURCE_DATE_EPOCH` and removes test-duration noise, so two consecutive freezes are byte-identical.

`DIGESTS.sha256` covers every material lane file except itself. It is an unsigned local drift inventory, not authenticated provenance or proof of authorship.

## Non-claims

The corpus and profile are project-authored and in-sample. The v0.2 byte fixtures are oracle-derived rather than independently specified. No unseen partner, deployed peer, model-comprehension evaluation, task-success/cost comparison, sanitizer campaign, coverage-guided fuzz campaign, or external security review was performed. No SOTA, universal-compression, standardization, production-readiness, or adoption claim is made.
