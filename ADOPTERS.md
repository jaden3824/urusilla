# Urusilla Verified Adopters

No external adopter is currently verified.

This registry will list an agent only when its maintainer submits reproducible evidence and the conformance checks pass. A GitHub star, clone, prompt example, screenshot, or self-declaration is not an adoption record.

The bundled Node.js cross-runtime lane and all internal bridge pilots are same-project evidence. They do not count as external implementations, independently operated agents, or adopters.

## Required evidence

- public implementation source or an auditable binary-release manifest;
- immutable implementation revision;
- exact Grammar Capsule digest;
- model/runtime and tokenizer identifiers where applicable;
- positive-vector exact round-trip results;
- negative-vector fail-closed results;
- unseen-partner canary results against the best enabled baseline;
- source-attribution manifest and translator output;
- privacy statement for any optional telemetry.

## Proposed record shape

```json
{
  "agent_name": "example-only",
  "maintainer": "https://github.com/example",
  "implementation_source": "https://github.com/example/agent",
  "implementation_revision": "<commit>",
  "capsule_sha256": "sha256:<digest>",
  "conformance_report": "https://github.com/example/agent/blob/<commit>/report.json",
  "verified_at": "YYYY-MM-DD",
  "status": "bridge|native"
}
```

The example is a schema illustration and is not an adopter.
