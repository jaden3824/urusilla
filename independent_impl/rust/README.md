# Cross-language v0.2 implementation lane

This isolated lane contains a separately written experimental semantic validator and UrusillaWire v0.2 static-profile codec. The implementation, CLI, tests, and evidence freezer do not import, spawn, or embed the project Python implementation at runtime.

The Urusilla identity is applied throughout this lane: the publication target is `jaden3824/urusilla`, and the package and CLI base is `urusilla`. All checked-in fixtures were regenerated after the identity freeze.

The pinned Grammar Capsule lifecycle is exactly `experimental-unsigned`. Its source may be distributed publicly with the exact checksum, but unsigned operation remains local and read-only. Effect-authorizing or production use requires a trusted publisher signature plus an independent authorization policy.

## Toolchain fallback

The requested Rust toolchain was not available on the execution host: `rustc`, `cargo`, and `rustup` were all absent. In accordance with the task's fallback rule, this directory contains a dependency-free ECMAScript implementation for the installed Node.js runtime. It remains under the requested `independent_impl/rust/` path. Because the workspace has no Git `HEAD`, the write-isolation statement is based on execution history rather than commit-diff proof.

Node.js built-ins provide SHA-256, constant-time checksum comparison, strict UTF-8 decoding, binary64 access, filesystem I/O, and the test runner. Exact integers outside JavaScript's safe `Number` range use `BigInt`; integral-valued binary64 values use an explicit `Float64` wrapper so the wire type is never guessed.

## Run

```text
cd independent_impl/rust
npm run generate
npm test
npm run verify
npm run freeze
npm run check-digests
```

The implementation has no package dependencies and requires no installation step. `npm` is only a command runner; the same checks can be run directly:

```text
node --test --test-reporter=spec
node src/cli.mjs verify-vectors
node tools/check_digests.mjs
```

`npm run freeze` is the evidence-maintainer command. It executes the TAP test run and vector verifier itself, requires successful exit statuses and parsed all-pass counts, records the runtime/tool probes, regenerates `conformance_report.json`, and finally rewrites `DIGESTS.sha256`.

CLI examples:

```text
node src/cli.mjs capsule-info
node src/cli.mjs encode message.json frame.bin
node src/cli.mjs decode frame.bin decoded.json
```

The JSON CLI projection tags every semantic value. Maps use ordered key/value entry pairs, so ordinary semantic keys such as `__proto__`, `$urusilla_bigint`, or `$urusilla_bytes_base64` cannot collide with the projection grammar. Integer text also avoids JSON lexical ambiguity such as `1`, `1.0`, and `1e0`:

```json
{"$urusilla_type":"integer","value":"18446744073709551615"}
{"$urusilla_type":"float64","bits":"3ff0000000000000"}
{"$urusilla_type":"bytes","base64":"AP8="}
{"$urusilla_type":"map","entries":[["__proto__",{"$urusilla_type":"string","value":"ordinary key"}]]}
```

The binary wire frame/capsule limit remains 16 MiB. Tagged JSON can be larger because bytes become Base64 and every value carries type metadata, so the local CLI uses a separate 192 MiB document cap. That cap is not a wire or semantic rule.

## Implemented scope

- Canonical envelope defaults and the closed seven-act table.
- Core node required/allowed fields and selected schema constraints from the public v0.1 specification and Capsule.
- Causal-reference checks for `COMMIT`, `RESOLVE`, and `RETRACT`.
- `COMMIT.debtor == sender` and act/body-kind compatibility.
- Recursive semantic value validation, exact 64-bit integers, finite binary64, bytes, lists, maps, and local `x:` quarantine.
- v0.2 profile capsule encode/decode and content fingerprinting.
- v0.2 warm-frame encode/decode, all value and shape tags, static prefix selection, checksum verification, explicit profile registry, and canonical re-encode enforcement.
- Hard limits for frames, strings, per-collection counts, aggregate semantic nodes, depth, dictionary entries, profile names, and shape tables.
- Exact offline agreement against 280 lane-frozen project fixtures, plus rejection of 25 frozen negative frame/capsule fixtures with fixture-digest and non-normative oracle-diagnostic-substring checks.

## Explicitly outside scope

Authentication, signatures, authorization, replay policy, conversation-ledger validity, schema registries, external effects, A2A bindings, gzip, UrusillaLens, adaptive dialogue, post-v0.1 schemas, and general RFC 8785 canonicalization are not implemented. Decoding never grants authority or mutates a ledger.

The Node lane and current Python oracle share a 250,000-value body-plus-metadata ceiling. A deterministic boundary probe accepts exactly 250,000 and rejects 250,001 in both implementations.

This is project-internal cross-language vector-compatibility evidence. It is not a clean-room or independent external reproduction, an adopter, a security certification, a native-model implementation, a standard, or a state-of-the-art result. `DIGESTS.sha256` is an unsigned local drift inventory, not authenticated provenance. See [REPORT.md](./REPORT.md) and [SPECIFICATION_INPUTS.md](./SPECIFICATION_INPUTS.md).
