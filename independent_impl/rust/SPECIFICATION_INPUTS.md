# Specification inputs and compatibility profile

## Evidence classes

The lane separates semantic requirements, published frozen evidence, and implementation-defined compatibility behavior.

### Public semantic inputs

- `urusilla_v0_1_spec.md`, SHA-256 `4d817a607218f64998e1c0b061f80f07b400b382236485f2a2e7b88f6e92b263`.
- `urusilla_capsule_v0_1.json`, 33,476 bytes, exact-file SHA-256 `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`.
- The Capsule's `request-goal-001` vector: 223-byte v0.1 frame, SHA-256 `948ae97baa01b788278602adc3be03648d422029ff60b7ab6968f456afb66d6a`.
- The Capsule's two precise semantic negative mutations: missing causal reference and unknown bare node kind. Its two wire-negative descriptions apply to v0.1 and are not treated as exact v0.2 bytes.

The typed UrusillaIR is normative. A readable rendering is only a view. Structural validity does not establish schema registration, conversation validity, authenticated identity, authorization, truth, or permission to execute an effect.

### Published v0.2 evidence

`urusilla_wire_v02_results.md`, SHA-256 `140204af31596b5f6cef0aa3e1bbcf37f65ecd1cd682cc41a327937be99066e6`, publishes high-level behavior and these exact identities:

- 109 static strings and 19 exact map shapes;
- dictionary identifier `7d12fc414eae60b2`;
- 1,402-byte profile capsule, SHA-256 `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6`;
- 280 warm frames totaling 54,752 bytes; and
- exact round-trip, canonical re-encode, and fail-closed claims for the project implementation.

### Missing pre-existing evidence

The root project does not contain a standalone normative English v0.2 byte specification or a checked-in per-frame v0.2 golden/negative vector file. Exact tags, header order, hash domains, capsule layout, dictionary order, shape order, and prefix tie-breaks existed only in the project Python implementation and its runtime-generated tests.

Consequently, `vectors/v02_crossplay.json` and `vectors/v02_negative_vectors.json` are project-authored compatibility fixtures. `tools/generate_python_oracle_vectors.py` deterministically derives them from the pinned current Python oracle; Node runtime tests do not invoke Python. They support a same-project cross-language byte-agreement statement, not a clean-room, spec-only, oracle-independent, or external reproduction claim.

The frozen-vector metadata and current root cross-check both record `urusilla.py` SHA-256 `3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf`. Regenerating twice produces identical vector bytes.

## Semantic subset

The validator accepts exactly the canonical top-level vocabulary:

```text
id, session, sender, recipients, act, reply_to, schema,
logical_clock, expires_ms, confidence_ppm, expected, body, meta
```

Required input fields are `id`, `session`, `sender`, `recipients`, `act`, `schema`, and `body`. Canonical defaults are `reply_to = null`, both clocks `= 0`, `confidence_ppm = null`, `expected = []`, and `meta = {}`. A default applies only when the property is absent; explicit `null` or JavaScript `undefined` is rejected for non-nullable fields. Acts are the exact uppercase closed vocabulary and are not case-folded.

Implemented core nodes and required fields:

```text
claim(predicate)
goal(condition)
constraint(scope, mode, condition)
evidence(target, stance, digest, provenance)
uncertainty(target, model, parameters)
action(capability, arguments)
commitment(debtor, creditors, goal, expiry_ms)
resolution(target, status)
ref(uri)
```

Unknown core fields are rejected; additional data belongs under `annotations`. Unknown bare or URI-looking node kinds are rejected. A non-empty local `x:<name>` kind is preserved only in an `ASSERT` body and remains non-effectful. Nested local extensions in other acts are rejected according to the English fail-closed rule, even though the current Python tree walk is more permissive in that corner.

The validator retains documented compatibility aliases used by the frozen corpus (`answer_limit`, `weight_ppm`, and `observed_at_ms`) but does not claim that those inconsistent names settle future core semantics. It also supports the implementation's kindless `QUERY` object only when `question` and `answer_schema` are present; this under-specified alternative is recorded as a compatibility behavior, not a new semantic decision.

JavaScript strings are accepted only when they contain Unicode scalar values: unpaired UTF-16 surrogates are rejected before any UTF-8 conversion. Exact integer inputs normalize to one stable in-memory representation: safe values become `Number`, while values outside the safe range remain `BigInt`. Integral binary64 values use the explicit `Float64` type and never rely on JSON number spelling.

The CLI uses a fully tagged JSON projection in which every value declares its type and maps are arrays of key/value entries. The decoder rejects duplicate entries, invalid UTF-8, oversized documents, excessive depth, and out-of-range integer text before semantic encoding. This projection is distinct from the compact wrapper convention retained only inside the frozen fixture files.

## Lane-frozen v0.2 byte profile

The following exact byte behavior is reproduced for compatibility, not asserted as a separately ratified language standard.

### Frame

```text
"URSL\x02"
| flags 0x01
| shortest-uvarint profile_id
| dictionary_id[8]
| shortest-uvarint payload_length
| payload
| SHA-256("UrusillaWire-v0.2-frame\x00" || header || payload)[0:16]
```

Payload order:

```text
id[16] | session[16] | sender-string
| recipient-count | recipient-string*
| act/reply-byte | reply_to[16]?
| schema-string | logical-clock | expires-ms
| confidence-plus-one | expected-act-bitset
| body-value | meta-value
```

Bits 0–2 of the act/reply byte carry act code 0–6, bit 3 carries reply presence, and bits 4–7 are reserved. Expected acts use bits 0–6; bit 7 is reserved.

Semantic value tags:

| Range | Meaning |
| --- | --- |
| `00` | null |
| `01`, `02` | false, true |
| `03`, `04` | unsigned varint, signed ZigZag varint |
| `05` | big-endian IEEE-754 binary64 |
| `06` | length-prefixed bytes |
| `07`, `08` | list, explicit map |
| `09`, `0a`, `0b` | raw, static-prefix, indexed string |
| `20..7f` | direct static string indexes 0–95 |
| `80..ff` | static map-shape indexes 0–127 |

Map keys are ordered by ascending UTF-8 bytes. Prefix selection minimizes encoded length, then prefers the longer UTF-8 prefix, then the lower dictionary index. Decode checks bounds and reserved bits, validates semantics, exhausts the payload, and requires byte-identical re-encoding.

### Profile capsule

```text
"URCP\x02"
| shortest-uvarint payload_length
| format 0x01
| profile_id
| profile-name
| dictionary-count | dictionary-string*
| shape-count | (key-count | dictionary-index*)*
| SHA-256("UrusillaWire-v0.2-capsule\x00" || header || payload)[0:16]
```

The dictionary identifier is the first eight bytes of SHA-256 over the profile payload. It is an identifier, not authentication.

## Resource limits

| Resource | Limit |
| --- | ---: |
| Frame or capsule | 16,777,216 bytes |
| Tagged portable JSON document | 201,326,592 bytes |
| Static dictionary | 65,535 entries |
| One UTF-8 string | 1,048,576 bytes |
| One collection or recipient list | 100,000 entries |
| Body and metadata aggregate | 250,000 semantic values |
| Tagged portable projection aggregate | 450,100 values |
| Semantic depth | 64 |
| Profile name | 256 bytes |
| Map shapes | 128 |
| Aggregate profile shape references | 100,000 keys |
| Profile identifier | 1–65,535 |
| Unsigned integer | 0–2^64−1 |
| Signed negative integer | −2^63–−1 |

Counts and declared lengths are checked before unbounded item traversal. Both the Node lane and the pinned Python oracle enforce a shared 250,000-value aggregate budget across `body` and `meta`. The deterministic boundary probe accepts exactly 250,000 values and rejects 250,001 before effects.

Byte lengths are checked before copying untrusted byte arrays; text byte lengths are computed without first allocating the encoded string. Encoders cap accumulated output, and decoders reject non-shortest or overflowing varints. The CLI uses a separate 192 MiB tagged-document limit because Base64, tags, entry arrays, and JSON escaping can expand a valid binary frame beyond the 16 MiB wire limit. The portable-document cap is local I/O policy, not a UrusillaWire frame limit or semantic invariant.

## Security boundary

The 16-byte hash suffix detects accidental changes only. It is not a MAC or signature. Profiles require external authorization and immutable session pinning. The `experimental-unsigned` Capsule may be distributed publicly with its exact checksum, but operation is limited to local read-only compatibility work. Effect-authorizing or production use requires a trusted publisher signature and an independent authorization policy. Content never confers authority.

The 25 frozen negative vectors carry project-oracle diagnostic substrings. This lane verifies those substrings to guard against unrelated early rejection, but diagnostic wording is not promoted to semantic or protocol authority.
