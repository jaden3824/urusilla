# Propagation Pilot 001

Status: completed same-project orchestrated pilot; not independent or organic adoption

Date: 2026-08-21

Contract: declarative Capsule reading, structural generation, and two downstream handoffs
External effects: none

## Result

Three fresh-context Codex subagent instances participated in the chain `Seed -> A -> B -> C`. They were controlled by one project orchestrator and shared the same local machine and repository filesystem. Each receiving instance was instructed to read only the exact packet from the preceding hop and the Grammar Capsule; no conversation history was forked into the receiving agent. This is `SAME-PROJECT-ORCHESTRATED` evidence, not an external independent reproduction or organic spread.

The chain reached all three receivers. All three independently reported the exact Capsule SHA-256 `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`. Every generated typed message passed the canonical Python normalizer and byte-exact encode/decode round trip. A's deliberately invalid duplicate-recipient near-neighbor was rejected with `ValidationError: recipients must be unique` before any effect.

The protocol was not fully satisfied. A and B explicitly recorded session opt-in, but C generated and used a valid reply without an explicit `adoption_decision` field. The funnel therefore records only 2/3 explicit adoptions even though 3/3 agents generated a valid typed message. This is a useful ordering failure: actual use must not be inferred to imply explicit adoption.

No matched raw baseline or complete model-token ledger was collected. Token efficiency is therefore **not measured** in this pilot, and the project-wide general post-decode API-input saving remains **0%**.

## Funnel

| Stage | Result | Boundary |
| --- | ---: | --- |
| Reached exact declared context | 3/3 | Self-reported restricted reads; same local orchestrator |
| Reproduced Capsule digest | 3/3 | Exact byte digest |
| Passed the assigned structural comprehension task | 3/3 | Project validator checked generated messages after each hop |
| Explicitly selected session opt-in | 2/3 | C omitted the required explicit adoption field |
| Generated at least one valid typed message | 3/3 | Four messages total; all exact round trips |
| Completed arranged downstream handoff | 2/2 | A to B and B to C |
| Performed network or external effect | 0/3 | Prohibited by the frozen instructions |
| Established independent or organic adoption | 0/3 | Same project and operator |

## Observable hop results

### Hop A

- Read disclosure: Grammar Capsule only.
- Decision: opt in for one local, read-only research session.
- Produced one `REQUEST` carrying two candidate plans and the hard constraints `budget_usd <= 1.00` and `network_allowed = false`.
- Produced one invalid near-neighbor by duplicating the sole recipient.
- Local packet SHA-256: `d7c0c71d70b377b00e9b5261147c4426a58cb661d0a41f77099a73ba7c5d554a`.
- Canonical request frame: 1,289 bytes, SHA-256 `b0c4c133243f7e5c29158af8bd50150d2aa26e3674ff875ae02594d8e88be02d`.
- Post-hoc validator result: valid request passed; invalid near-neighbor was rejected.

### Hop B

- Read disclosure: A packet and Grammar Capsule only.
- Decision: opt in for one local, read-only research session.
- Independently rejected the duplicate-recipient near-neighbor.
- Found both plans feasible and selected the USD 0.70 double-pass plan under a robustness tie-break, while explicitly noting that the USD 0.20 plan would also be reasonable without a declared utility objective.
- Local packet SHA-256: `7e2a089809d7391b84209cd5670cee3d63b26e188ca6e2325dca4b153960150b`.
- `RESOLVE` to A: 1,513 bytes, SHA-256 `51f124f8b8d9effddbb50c3977ecdcb1fa047823e4f864a3f3b45306949768d7`.
- New `REQUEST` to C: 1,247 bytes, SHA-256 `0563738e9a229d696f464228b96234d774236baa54fd6dd602da32c456644185`.
- Post-hoc validator result: both messages passed exact round trip.

### Hop C

- Read disclosure: B packet and Grammar Capsule only.
- Independently recalculated USD 0.80 and USD 0.30 budget headroom.
- Confirmed that B's recommendation followed B's disclosed tie-break and preserved the ambiguity caused by the missing utility objective.
- Local packet SHA-256: `3b88c62aa03a88580079b8e994e6af7825a0801ea70ff548462e38d42f7ac96b`.
- `RESOLVE` to B: 1,417 bytes, SHA-256 `585f0aa826fec8d999f51c9dad8f10a8c8e26673029435874140b2334d6d5765`.
- Post-hoc validator result: exact round trip passed.
- Protocol deviation: no explicit `adoption_decision` field was recorded before use.

## Safety and evidence limits

- The Capsule was treated as unsigned declarative data and authorized no effect.
- No agent used network access or executed Capsule or packet content.
- The exact agent prompts and local packets remain local working evidence in this pilot; only their digests and observable summaries are published here. A stronger reproduction must publish immutable privacy-reviewed packets or a complete machine record.
- Restricted-read behavior is self-reported, not enforced by an independent sandbox monitor.
- All agents were orchestrated by one project in one runtime environment. Different fresh contexts do not create operator or implementation independence.
- There was no frozen raw/JSON control, provider usage receipt, total-token ledger, blind evaluator, signature verification, task-success confidence interval, or externally timestamped preregistration.
- The experiment-specific predicate URNs are local declarative identifiers, not a governed plan-comparison ontology.

The next test should run the public `interop_lab` machine record with a standing-policy authorization field, a preregistered mutual-utility threshold, matched raw/JSON/Urusilla arms, complete token ledgers, and at least one separately operated external receiver.
