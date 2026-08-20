# Urusilla Security Policy

## Prototype restriction

The 0.1 Capsule is unsigned and publicly distributed for source review, local read-only experiments, and conformance tests. Public availability does not make it trusted or effect-authorizing. Do not use it to authorize purchases, account changes, deployments, physical actions, or any other consequential effect.

## Security boundaries

- The semantic language does not grant authority.
- The frame checksum detects accidental corruption; it is not an authentication mechanism.
- Transport security does not make semantic content trustworthy.
- Natural-language-to-IR translation is ambiguous and must not silently select among materially different meanings.
- Opaque, latent, or cache-based channels may expose private state and require an independent threat review.
- Receiver-token-profile text such as experimental `R7` payloads is decoder-before-model transport. It must be profile-bound, integrity-checked, canonically decoded, and validated before any content reaches a model prompt.
- Stateful deltas require exact session, sequence, base-state, and checkpoint binding. A missing, replayed, reordered, or branch-conflicting record must fail closed until a verified full checkpoint or explicit retransmission restores state.

Production work requires authenticated identity, replay protection, authorization policy, resource budgets, signed schema and Capsule manifests, strict decoding limits, audit logs, and high-risk confirmation of the receiver's interpreted semantic hash.

Public deterministic HMAC keys in experiment fixtures are not deployment secrets or key-establishment protocols. Passing their mutation tests does not authenticate a production peer.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when the repository enables it. Do not open a public issue containing an exploit, secret, personal information, or unredacted agent conversation. Until private reporting is enabled, do not deploy the prototype in a context where delayed private reporting would create risk.
