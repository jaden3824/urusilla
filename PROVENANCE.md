# Urusilla Source Attribution and Provenance

Status: experimental draft 0.1  
Canonical repository: `https://github.com/jaden3824/urusilla`

## Goal

Every agent that claims support must make the origin of its language definition, implementation, and conformance evidence verifiable. Attribution must remain compact and must not become tracking of users or message content.

## Source manifest

An implementation publishes or exchanges the following logical object during discovery or session setup:

```json
{
  "languageSpecUri": "https://github.com/jaden3824/urusilla/blob/<commit>/urusilla_v0_1_spec.md",
  "languageVersion": "0.1.0",
  "capsuleSha256": "<64-lowercase-hex>",
  "implementationOrigin": "https://github.com/<owner>/<repository>/tree/<commit>",
  "conformanceReportUrl": "https://github.com/<owner>/<repository>/blob/<commit>/conformance_report.json",
  "conformanceReportSha256": "<64-lowercase-hex>",
  "sourceManifestJws": "<compact-or-detached-JWS>"
}
```

These camelCase field names are the only 0.1 manifest vocabulary. The source manifest payload excludes `sourceManifestJws`, is canonicalized with RFC 8785, and defines `source_id` as the lowercase hexadecimal encoding of the leftmost 16 SHA-256 bytes. The included JSON Schema and test vectors are normative for the experimental profile. An unsigned research manifest omits `sourceManifestJws`, is displayed as `digest-verified` at best, and cannot authorize effects.

## Where attribution appears

- **Agent discovery:** The full source manifest or a resolvable signed reference appears in the A2A Agent Card extension parameters.
- **Session negotiation:** Both peers pin the full manifest digest and Capsule digest before activating the language profile.
- **Hot messages:** A compact `source_id` refers to the pinned session manifest. The full GitHub URL is not repeated in every frame.
- **Human inspection:** The translator shows specification source, semantic version, implementation source, conformance status, and verification result.
- **Adoption registry:** A public record links to reproducible conformance evidence. It contains no conversations.

## Evidence-independence labels

Source attribution and evidentiary independence are separate. Public reports must use these labels consistently:

- **project-internal:** authored, operated, or evaluated within the canonical project;
- **same-project cross-runtime:** separately written in another runtime but evaluated from project specifications, Capsules, or oracle-derived vectors;
- **external independent reproduction:** operated outside the canonical project with disclosed shared inputs and enough independent implementation or measurement to challenge the project result; and
- **verified adopter:** an independently operated agent that passes the separate evidence gates in [`ADOPTERS.md`](ADOPTERS.md).

The bundled Node.js lane is same-project cross-runtime evidence. A source manifest makes its origin auditable; it does not promote that lane to external independent reproduction or adoption.

## Text-safe diagnostic wrapper

When a text-only channel must carry the opaque wire form, a debug profile may use a self-identifying wrapper:

```text
-----BEGIN URUSILLA DEBUG-----
spec: https://github.com/jaden3824/urusilla/blob/<40-hex-commit>/urusilla_v0_1_spec.md
version: 0.1.0
source-id: <32-lowercase-hex>
capsule: sha256:<64-lowercase-hex>
payload: <base64url>
-----END URUSILLA DEBUG-----
```

This wrapper is for diagnostics and explicit share views, not the efficient binary hot path. It must not include a user identifier, prompt, recipient identity, or telemetry endpoint. The specification URL must be immutable, the Capsule digest must contain all 64 hexadecimal characters, and the source ID must resolve to the same manifest. A production parser still needs explicit total and field length limits.

## Anti-spoofing rules

1. A repository URL alone is not proof of conformance.
2. The Capsule, implementation revision, and report digest must match the source manifest.
3. Effectful deployments require an authenticated Agent Card and a signed release manifest.
4. A failed signature, unknown manifest, digest mismatch, or version mismatch fails closed.
5. Translators distinguish `declared`, `digest-verified`, `signature-verified`, and `conformance-verified` status.

## Privacy rules

- Attribution identifies software and language artifacts, never the end user.
- Usage telemetry is off by default and requires explicit deployment-owner consent.
- Opt-in telemetry is aggregate and must not contain message content, agent prompts, account identifiers, IP addresses, or stable user identifiers.
- Public adoption counts come from reviewed conformance records, not passive surveillance.
- A personal AI may display source attribution locally without reporting that use to the repository.

## Visibility without manufactured accidents

A consumer product may expose **Show machine original**, **Explain this exchange**, and a privacy-reviewed share card. It must not deliberately route raw frames into ordinary user replies to manufacture attention. If a real UI or serialization error surfaces a diagnostic wrapper, the source marker makes the format traceable while the absence of user metadata limits secondary harm.
