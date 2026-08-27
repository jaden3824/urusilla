# WIRE-CROSSPLAY-MIN-1

Date: 2026-08-28

Source parent revision: `861d71b36419db5e2e1b558e9bf6326a5ae78289`

## Result

The bounded local experiment passed every declared functional gate. A Python
UrusillaWire v0.2 sender transferred one raw profile capsule and five raw
`URSL\x02` request frames through length-prefixed standard input to the
separately written same-project Node.js runtime. The Node runtime decoded each
request, derived a new `ASSERT` response from the decoded task fields, encoded
the response as raw UrusillaWire, and returned it through standard output. The
Python sender decoded and canonically re-encoded every response.

The same five semantic requests were also sent through a canonical minified
JSON control path at the same Node responder boundary. Every Wire response and
its matched JSON response normalized to the same UrusillaIR message.

This is the first project-local exercise in this repository that combines all
of the following in one path:

- actual raw binary transfer between the Python and Node runtimes;
- a newly generated binary reply rather than fixture comparison alone;
- observable dependence on a task-critical decoded field;
- invariance under a declared task-irrelevant field;
- explicit missing-field and no-payload fallbacks; and
- pre-reply rejection of a corrupted frame and an unknown profile.

It is not external or independent evidence. Both runtimes and the experiment
were produced within the Urusilla project.

## Why this does not repeat the public decode challenge

The public `challenge_001` proves that one frozen UrusillaWire v0.1 frame can be
decoded, compared with a published expected JSON message, and re-encoded. That
is useful conformance evidence, but its expected result is public and it does
not require a receiver to derive a new Wire reply.

The Base64 text beginning `VVJTTAEB...` is a text carrier for a raw
`URSL\x01` frame. This experiment instead used experimental v0.2 raw bytes
directly. No Base64 was placed on the transport and no binary or Base64 text was
placed in a model prompt. The shared semantic contract remained UrusillaIR
0.1.0; v0.2 was only the negotiated runtime codec.

## Counterfactual cases

The five accepted requests used fresh deterministic request IDs and one shared
session. Every response used a distinct deterministic response ID, the same
session, reversed sender and recipient, `reply_to` equal to the request ID, and
`logical_clock = request.logical_clock + 1`.

| Case | Decoded task condition | Required observed result |
| --- | --- | --- |
| `critical-a` | branch `A` | select `route-alpha`, total `31` |
| `critical-b` | branch `B` | select `route-beta`, total `31` |
| `inert-metadata` | branch `A`; only the inert marker changes | same result body as `critical-a` |
| `missing-branch` | payload present without branch | `missing-branch` fallback claim |
| `no-payload` | no claim payload | `missing-payload` fallback claim |

The validator rejected a byte-identical request echo, reused request or
response IDs, incorrect causal bindings, any Wire/JSON semantic disagreement,
a constant A/B result, an inert-field result change, and incorrect fallback
semantics.

Two additional raw Wire inputs were not allowed to reach the application reply
path:

| Negative control | Result |
| --- | --- |
| one-bit checksum corruption | rejected with `checksum`; zero reply frames |
| valid frame under unregistered profile 2 | rejected with `unknown_profile`; zero reply frames |

An additional test changed the hard safety constraint to authorize an external
effect. The Node runtime rejected it with `application_envelope` and emitted no
reply frame.

## Complete local byte accounting

All values below cover these five fixed accepted records. They include the
experiment's 4-byte counts and input lengths plus the 1-byte response status and
4-byte response lengths. The cold Wire total also includes the complete 1,402
byte profile capsule and its 4-byte length.

| Path | Request payloads | Response payloads | Profile transfer | Framed total |
| --- | ---: | ---: | ---: | ---: |
| canonical minified JSON | 3,955 | 2,773 | 0 | 6,781 |
| raw Wire v0.2, cold | 2,243 | 1,572 | 1,406 | 5,274 |
| raw Wire v0.2, warm | 2,243 | 1,572 | excluded after negotiation | 3,868 |

For this exact local sequence, the cold raw-Wire total was 22.224% below the
matched JSON total, and the warm total was 42.958% below it. This is a byte
result, not a general efficiency result. It excludes Base64, HTTP, TLS,
authentication, retransmission, model tokens, codec/process latency, task
success, energy, and operational cost. The result must not be extrapolated to a
different corpus, transport, profile reset policy, implementation, or model
path.

## Artifact identities

- `wire_crossplay_min_1.result.json`: 8,158 bytes, SHA-256
  `d943f6e269db7604158b12ffa2d944e9b20d4a2159ed192cb0acee5aaa077593`
- profile capsule: 1,402 bytes, SHA-256
  `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6`
- profile dictionary ID: `7d12fc414eae60b2`

The machine-readable result binds each request and response byte length and
SHA-256, the two implementation-source digests, the runtime versions, every
gate result, and the exact claim boundary.

## Offline reproduction

No package installation, model call, provider call, network request, GitHub
Actions run, or paid API is required.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_wire_crossplay_min_1.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_wire_crossplay_min_1.py -v
```

## Claim boundary and next external gate

This run supports only same-project cross-runtime raw-Wire exchange, canonical
semantic identity, bounded observable task-field dependence, controlled
fallback, and the tested decoder rejections. It does not prove that a model
understood Urusilla, that an agent used it natively, that the runtime path is
causally sufficient for task success, or that an external party implemented or
adopted it. The v0.2 checksum and dictionary fingerprint are not signatures,
authentication, authorization, or replay protection.

The next non-overlapping gate is an externally operated, precommitted
implementation receiving fresh counterfactual packets before the decoded IR or
expected replies are revealed. Decoder and encoder provenance, use of project
reference code or vectors, operator relationship, failures, and exact response
receipts must be recorded separately. A successful result would still be a
bounded external Wire reproduction, not general adoption or end-to-end
efficiency evidence.
