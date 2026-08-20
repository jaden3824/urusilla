# Urusilla Internal Bridge Pilots

Status: reproducible internal evidence only; zero external adopters

Three parallel project-internal workstreams used the experimental semantic format to return their own research artifacts to the coordinating agent. Each workstream created a typed `ASSERT` carrying evidence, repository provenance, experimental version, and an explicit negative external-adoption flag. The published JSON messages deterministically reproduce the frame digests below. Their separate task assignments do not make them external independent reproductions.

| Workstream | Wire profile | Frame bytes | Frame SHA-256 | External adoption |
|---|---|---:|---|---|
| Global project landscape | v0.1 | 738 | `ebd30eeca09271dce9b262ee261dd4d9dc9ace31d5cd428bc02d34c5f90ad9ec` | false |
| Bootstrap and adoption design | v0.1 | 789 | `14cd50f65b48209063e73449b9cb6751fa67343b4fe405cf08ff2fbbcdb5cfab` | false |
| Warm-profile performance study | v0.2 | 994 | `dd5c185c35a3a838ca644dc85801d0688f1debfc51997756d767f7dc71c55a04` | false |

The v0.2 evidence message is intentionally verbose and is not a compression benchmark sample. It carries a report digest, measurements, classification, and repeated provenance so that the evidence boundary remains explicit outside a negotiated production session. Its research details live under the non-authoritative `annotations` field required by the hardened core-node validator.

The open-label capsule smoke pilot is reported separately in [`urusilla_teachability_pilot.md`](urusilla_teachability_pilot.md). A fresh agent constructed eight valid messages and rejected four unsafe or underspecified tasks, earning 36/36 on a bespoke rubric. Its tasks exposed substantial cues, so it is not a blind Teachability Score, native model support, independent replication, or adoption.

The neutral-ID follow-up is reported in [`urusilla_hidden_transfer_results.md`](urusilla_hidden_transfer_results.md). It achieved 16/16 decisions and 10/10 act selections, but only 6/10 structurally valid generated messages. The published evaluator leaves the standardized Teachability Score null and preserves all four validation failures.

## Reproduce

```bash
python3 -m unittest -v test_internal_pilots.py
```

The test encodes each JSON artifact, checks the expected frame digest, decodes it, requires canonical byte-identical re-encoding, and confirms that the provenance marks it as internal and non-external.

## Evidence boundary

- The agents were sub-agents inside one research environment, not independent organizations or products.
- All three used bridge-mode serialization after completing work; they did not natively reason in the binary format.
- No task-success improvement is attributed to the language from these messages.
- No conversation content, end-user identifier, or usage telemetry is published.
- `ADOPTERS.md` remains empty until an outside maintainer supplies reproducible conformance and unseen-partner evidence.
