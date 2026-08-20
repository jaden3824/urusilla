# Urusilla Experimental Source Manifest Format

Lifecycle status: `experimental-unsigned`  
Manifest vocabulary and semantic-language version: `0.1.0`  
Distribution prerelease label: `v0.1.0-experimental`

## Purpose and security boundary

A source manifest binds a language specification revision, Grammar Capsule digest, implementation revision, and conformance-report digest to one compact `source_id`. It identifies software and language artifacts. It must not identify a user, contain prompts or message content, or act as telemetry.

This format is provenance metadata, not authority. Structural validity, a derived digest, or a repository URL does not prove conformance. This validator does not download the referenced artifacts, authenticate an Agent Card, verify deployment authorization, or authorize effects.

## Exact vocabulary

The JSON value must be one object. The six payload members are required. `sourceManifestJws` is the only optional member. No other member is allowed.

| Member | Requirement |
| --- | --- |
| `languageSpecUri` | Immutable HTTPS GitHub `blob` URL containing an exact 40-lowercase-hex commit and a nonempty safe ASCII path. |
| `languageVersion` | Exactly `0.1.0` for this profile. It identifies semantic-language meaning, not release maturity or the distribution tag. |
| `capsuleSha256` | Exactly 64 lowercase hexadecimal characters: the SHA-256 of the exact external Capsule bytes. |
| `implementationOrigin` | Immutable HTTPS GitHub `blob` or `tree` URL containing an exact 40-lowercase-hex commit. A tree may identify the commit root. |
| `conformanceReportUrl` | Immutable HTTPS GitHub `blob` URL containing an exact 40-lowercase-hex commit and a nonempty safe ASCII path. |
| `conformanceReportSha256` | Exactly 64 lowercase hexadecimal characters: the SHA-256 of the exact report bytes. |
| `sourceManifestJws` | Optional compact or detached JWS-shaped ASCII string with possible unpadded base64url segment lengths. It is excluded from payload canonicalization and hashing. |

Normative URLs use `github.com` exactly, have no query or fragment, and accept only `[A-Za-z0-9._-]` in repository and path components. Repository and path components `.` and `..` are forbidden. These restrictions intentionally reject moving branches, tags, shortened commit IDs, uppercase commit hex, redirects, and ambiguous encodings.

The machine-readable constraints are in `source_manifest.schema.json`. The dependency-free Python implementation applies the same profile and rejects duplicate JSON members at its file-loading boundary.

## Restricted canonical payload

The payload consists of exactly these members and excludes `sourceManifestJws`:

```text
languageSpecUri
languageVersion
capsuleSha256
implementationOrigin
conformanceReportUrl
conformanceReportSha256
```

Canonical payload bytes are produced as follows:

1. Validate the complete manifest against this restricted profile.
2. Copy only the six required payload members.
3. Sort the fixed ASCII member names lexicographically.
4. Serialize one JSON object with no insignificant whitespace.
5. Encode the result as UTF-8.

Every payload value is an ASCII string constrained by its field pattern. The payload permits no numbers, floats, booleans, nulls, arrays, or nested objects. The accepted character sets also exclude JSON control characters, quotation marks, and backslashes from values. Therefore, the deterministic serialization above is byte-equivalent to RFC 8785 JSON Canonicalization Scheme output for this restricted domain.

This implementation is not a general RFC 8785 implementation. It does not implement general JCS number serialization, Unicode handling, object recursion, or arbitrary JSON string canonicalization, and it must not be used as one.

Compute identifiers from the canonical payload bytes:

```text
payload_sha256 = lowercase_hex(SHA-256(canonical_payload_bytes))
source_id      = lowercase_hex(SHA-256(canonical_payload_bytes)[0:16])
```

The `source_id` is exactly 32 lowercase hexadecimal characters. It is the leftmost 16 digest bytes, not the first 16 hexadecimal characters. A peer must resolve it to exactly one pinned full manifest. A missing or colliding mapping requires the full manifest and must disable effectful processing until resolved.

## Positive deterministic vector

This is a synthetic test vector. Its specification and implementation commits illustrate the required immutable URL shape; they are not publication claims.

```json
{
  "languageSpecUri": "https://github.com/jaden3824/urusilla/blob/0123456789abcdef0123456789abcdef01234567/urusilla_v0_1_spec.md",
  "languageVersion": "0.1.0",
  "capsuleSha256": "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
  "implementationOrigin": "https://github.com/example/urusilla-bridge/tree/89abcdef0123456789abcdef0123456789abcdef/src",
  "conformanceReportUrl": "https://github.com/example/urusilla-bridge/blob/89abcdef0123456789abcdef0123456789abcdef/conformance_report.json",
  "conformanceReportSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

Canonical UTF-8 JSON, shown as text:

```json
{"capsuleSha256":"588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27","conformanceReportSha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","conformanceReportUrl":"https://github.com/example/urusilla-bridge/blob/89abcdef0123456789abcdef0123456789abcdef/conformance_report.json","implementationOrigin":"https://github.com/example/urusilla-bridge/tree/89abcdef0123456789abcdef0123456789abcdef/src","languageSpecUri":"https://github.com/jaden3824/urusilla/blob/0123456789abcdef0123456789abcdef01234567/urusilla_v0_1_spec.md","languageVersion":"0.1.0"}
```

Expected values:

```text
payload_sha256 = defc2efc4f0ac1ecd553fb45df7abe931f989ccfcb922f12ba6c00a600d5fd8c
source_id      = defc2efc4f0ac1ecd553fb45df7abe93
```

Reordering members does not change either value. Adding or replacing `sourceManifestJws` does not change either value. Changing any of the six payload values does.

## Negative vectors

Each mutation below must be rejected:

| Mutation | Reason |
| --- | --- |
| Replace the specification commit with `main`. | A moving branch is not immutable. |
| Use 39 commit hex characters or uppercase commit hex. | Commits must be exact 40-lowercase-hex values. |
| Change `https` to `http`. | Normative URLs require HTTPS. |
| Use a `tree` URL for `conformanceReportUrl`. | A report must identify a blob. |
| Insert a `..` path segment. | Ambiguous path traversal is forbidden. |
| Use an uppercase or 63-character SHA-256 value. | Digests are exact 64-lowercase-hex values. |
| Use `0.1.0-experimental`, `0.1.1`, or any value other than `0.1.0`. | This profile pins one exact semantic-language version; maturity is expressed on a separate axis. |
| Add `trackingId` or any other member. | `additionalProperties` is false. |
| Use a number, object, array, boolean, or null as a value. | Every accepted value is a string; the payload has no nesting. |
| Add non-ASCII text. | Every manifest value is restricted to ASCII. |
| Repeat a JSON member. | Duplicate names are ambiguous and rejected by the loader. |
| Use `not-a-jws` or impossible one-character base64url segments such as `a..b` as `sourceManifestJws`. | The optional member must have compact or detached JWS shape and possible unpadded base64url segment lengths. |

Executable positive and negative vectors are in `test_source_manifest.py`.

## JWS and authorization behavior

The module contains no built-in JWS algorithm, key store, or trust policy. Its structural check covers only the compact-or-detached three-segment shape, base64url alphabet, and possible unpadded segment lengths. It does not decode the protected header, establish payload binding, or treat a three-segment string as a verified signature.

- With no `sourceManifestJws`, `validate_manifest` returns `signature_status="unsigned"` and `effect_authorizing=False`.
- With a structurally valid JWS but no verifier callback, it returns `signature_status="unverified"` and `effect_authorizing=False`.
- With a callback, the callback receives the exact JWS string and canonical payload bytes. It must verify the cryptographic signature, payload binding, accepted algorithm, key, and publisher policy. A true result produces `verified`; a false result produces `invalid`.
- A callback exception or non-boolean return fails closed with `ManifestVerificationError`.

Even `signature_status="verified"` is not independently effect-authorizing. A deployment must separately verify the referenced Capsule and report bytes, establish authenticated session identity, check conformance and version policy, and authorize the requested effect.

## Python and command line

The implementation uses only the Python standard library and supports Python 3.11 or later.

```python
from source_manifest import derive_source_id, validate_manifest

result = validate_manifest(manifest)
assert result.signature_status == "unsigned"
assert result.effect_authorizing is False
source_id = derive_source_id(manifest)
```

Validate a JSON file and print a deterministic diagnostic object:

```console
python3 source_manifest.py validate manifest.json
```

Print only the derived identifier:

```console
python3 source_manifest.py id manifest.json
```

Use `-` instead of a file name to read UTF-8 JSON from standard input. The loader rejects inputs larger than 65,536 bytes and duplicate members. The CLI returns zero for structurally valid unsigned or unverified research manifests because their explicit trust status remains non-authorizing; invalid JSON or structure returns status 2.

Run the executable vectors from this directory:

```console
python3 -m unittest -v test_source_manifest.py
```
