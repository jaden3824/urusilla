# Urusilla Adoption Kit: local verification report

Snapshot date: 2026-08-20  
Status: `experimental-unsigned`, same-project local evidence

## Result

The kit provides a standard-library-only Python SDK, a dependency-free Node bridge, local A2A-shaped and MCP-friendly carriers, deterministic JSON/JSONL, exact Python compact codecs, Node compact relay inspection, two deterministic examples, and opt-in content-free telemetry.

The current Grammar Capsule, reference codec, v0.2 profile, dictionary, URNs, package paths, and wire identities are internally pinned. The Grammar Capsule's embedded `urusilla.py` digest matches the observed executable root file. Exact-checksum public source distribution is permitted, but this does not create an external conformance claim: the worktree is unsigned, the release is not yet bound to an immutable commit, and no independent verifier exists. Unsigned operation is local and read-only. Effect-authorizing or production use requires a trusted publisher signature and an independent authorization policy. Discovery therefore keeps `support_claim_eligible: false`, `provenance_bound: false`, and effect authorization disabled.

No network traffic, publication, external message, model call, package installation, or external effect was created by this kit. The Python/Node exchange is same-project structural evidence only, not an unseen partner or adoption event.

## Integration surface

- Python imports the pinned root semantic validator and codecs after hashing their files.
- Capability discovery separates `bridge`, `native`, and `fallback`; native remains unsupported because no native-evidence verifier exists.
- Python supports canonical JSON, Controlled Terse English, `URSL\x01`, and the exact-registry `URSL\x02` profile.
- Node supports the safe-integer JSON and controlled-text subset. Compact binary profiles remain relay-only in this kit.
- Every delivery pins the language version, Grammar Capsule, origin `source_id`, and, for v0.2, profile ID, `URCP\x02` capsule digest, and dictionary ID.
- Pin-mismatch fallback is JSON-only, opaque, and non-effectful.
- A2A-shaped and MCP-friendly objects use private experimental identifiers and do not claim official extension status.
- `REQUEST` and `PROPOSE` create no obligation. No decoded message authorizes an external effect.

## Verification

The isolated suites passed:

| Scope | Result |
| --- | ---: |
| Python SDK and telemetry | 41/41 |
| Dependency-free Node bridge | 9/9 |
| One-agent example, two runs | byte-identical |
| Python/Node cross-play, two runs | byte-identical |

Example identities:

| Example | Bytes | SHA-256 |
| --- | ---: | --- |
| One-agent onboarding | 541 | `7392b7f0ff43a45b8e7a8ec72203c1b5c07ca21cf93bebf883c0b4971ca0910d` |
| Python/Node cross-play | 601 | `4ef242e88c64a09f14bab9bcf66611a776ccaea59013e9a65201761874c54079` |

The cross-play request-delivery digest is `e7b480d7c9e16c5849d471455e110ee786d994ae9d43742f844ebc0252f546af`; the response-delivery digest is `d136c9238e683adb0af28e522e72b23c556e89dc471948df9058ca39d7ac5497`. The exchange used one local Python process and one local Node child process over standard input/output. It did not measure task success, model comprehension, latency, or energy.

## Exact identities

| Artifact | Bytes | SHA-256 / identifier |
| --- | ---: | --- |
| Grammar Capsule | 33,476 | `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27` |
| v0.2 profile capsule | 1,402 | `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6` |
| v0.2 dictionary | — | `7d12fc414eae60b2` |
| Reference codec | 52,536 | `3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf` |

Wire identities are `5552534c01` (`URSL\x01`), `5552534c02` (`URSL\x02`), and `5552435002` (`URCP\x02`).

## Cold/warm byte accounting

The deterministic fixture's canonical JSON has SHA-256 `f8f906befa006cd7cbca59b8b7c5396f60248eb1d3b57aa066edd539fddbddee`. Binary carrier bytes include Base64. Empty-cache totals include both discovery objects, one exact delivery envelope, and raw verified artifact bytes. Warm totals use receiver-acknowledged cached artifacts. HTTP, TLS, DNS, authentication, retries, responses, model tokens, latency, and energy are excluded.

| Representation | Raw payload | Carrier | Envelope | Verified cold artifacts | Empty-cache first delivery | Warm first delivery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `canonical-json-v1` | 441 | 441 | 1,052 | 33,476 | 39,868 | 6,458 |
| `controlled-terse-english-v1` | 356 | 356 | 931 | 33,476 | 39,747 | 6,337 |
| UrusillaWire v0.1 | 221 | 296 | 844 | 33,476 | 39,660 | 6,250 |
| UrusillaWire v0.2 static | 179 | 240 | 954 | 34,878 | 41,172 | 6,427 |

The unfavorable result is retained: under this full JSON delivery envelope, v0.2 requires 15 repeated messages to recover its incremental profile cost relative to JSON and never beats v0.1 because its repeated envelope is 110 bytes larger. Raw-payload-only break-even is 6 messages versus JSON and 34 versus v0.1; those are not end-to-end savings claims. The selector chose v0.1 at 1, 10, and 100 messages for both empty and warm caches.

## Friction and limits

| Item | Boundary |
| --- | --- |
| Installation | No third-party Python or Node dependency. |
| Root coupling | Python intentionally rejects any unreviewed change to a pinned root executable. |
| Native mode | Unsupported until a real verifier and evidence contract exist. |
| Node compact support | Relay and checksum/profile inspection only. |
| Shared JSON | Floats, bytes, lone surrogates, and integers outside `±(2^53−1)` are rejected. |
| v0.2 profile | Benchmark-specialized and experimental; the numeric ID alone is insufficient. |
| Source provenance | Unsigned sources remain non-effect-authorizing even when local digests match. |

## Telemetry and adoption claims

Telemetry is disabled unless explicitly opted in. The closed allowlist excludes bodies, prompts, answers, message/session/user/account/device identifiers, source URIs, IP addresses, exact timestamps, and arbitrary fields. The included HMAC machinery is local test/operations support, not an independent external verifier.

The verified external adoption metric remains exactly zero: 0 external adopters, 0 independently verified external safe messages, and 0 adoption-adjusted milliunits. Downloads, stars, repository activity, and self-declarations are not counted.

## Reproduction and integrity

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s adoption_kit/tests -v
node --test adoption_kit/node/test/*.test.js
PYTHONDONTWRITEBYTECODE=1 python3 adoption_kit/generate_evidence.py
```

`generate_evidence.py` regenerates both JSON evidence files and proves that each example is byte-identical across two runs. `ARTIFACTS.sha256` covers every checked-in kit file except itself. It is an unsigned drift inventory, not authenticated provenance.
