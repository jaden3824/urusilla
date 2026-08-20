# Neutral-ID Capsule Transfer Pilot

Status: internal transfer evidence only; not an external adopter claim and not a standardized Teachability Score

## Result

Before the Urusilla cutover, a fresh participant saw the then-frozen Capsule and 16 neutral-ID tasks. It selected all 16 emit/reject decisions and all 10 positive acts correctly, but only 6 of 10 emitted messages passed the structural validator used for the original evaluation. The four recorded failures were concrete representation mistakes, so this pilot does not support a native-readiness claim.

No participant was rerun after the cutover. The current task, submission, and Capsule files are a post-cutover projection bound to current digests; the measured outcomes remain bound to the separately listed historical digests and must not be attributed to a new Urusilla participant run.

| Component | Result |
|---|---:|
| Decision Accuracy | 16/16 (100.0%) |
| Act Selection | 10/10 (100.0%) |
| Envelope Preservation | 10/10 (100.0%) |
| Structural Generation | 6/10 (60.0%) |
| Essential Semantics | 6/10 (60.0%) |
| Negative Rejection | 6/6 (100.0%) |

## Structural failures

| Case | Validator result |
|---|---|
| `R8D1` | unknown node kind 'question-plus-answer-schema'; local prototype extensions require x:<name> |
| `P7A2` | ref.uri must be an absolute URI or content identifier |
| `W5L4` | uncertainty.basis must be a canonical list |
| `V3G8` | claim.predicate cannot contain whitespace or control characters |

## Evaluation boundary

The task file was frozen before the participant response, and identifiers did not disclose acts or decisions. The machine-readable expectation record and evaluator were deliberately created only after the response; there was no cryptographic precommitment. This is better controlled than the earlier open-label smoke test, but it is not a formally preregistered blind trial.

The structural component replays the original validator snapshot. Later validator changes are not applied retroactively to this historical result; currently valid historical successes are still checked to detect regressions.

The Capsule's standardized formula also requires frame parsing, exact held-out semantic graphs, unseen composition, sample efficiency, and non-compensable safety gates. Those were not measured, so this report leaves the standardized score null instead of inventing one.

## Artifact digests

- tasks_sha256: `41e345b3fed3931c1fd9e764bf251c638550ea8cffcaed348f22499605ff3692`
- submission_sha256: `1f73c5bcd26e8e50cb02fe38eba25c4a3e6ffc7c64228085655cec50641939d9`
- expectations_sha256: `dcd1b703ca73255d5514556437091b51c919aacf6b46e5ffe04f9ad190791d49`
- capsule_sha256: `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`
- historical_task_sha256_before_project_rename: `3199ee46e2f22f0b0782fb242de33bb395b0e97e24009e0f51b9438869471261`
- historical_published_submission_sha256_before_project_rename: `157fe4643ac60fb8d14a88e0103cacd8b4cac1dc04cae56a5cb377a866c425ad`
- historical_participant_original_submission_sha256: `6428c66339e156b52be80e5695a72c8ff790828d1d52ea7eb2906cff1f493489`
- historical_capsule_sha256_before_project_rename: `a141de8359dc2bce4af619a931ed0bfc688c421067fbba80a16711a3348e5346`

## Limitations

- One participant instance from the same model family and research environment was used.
- File-access isolation was self-declared rather than operating-system enforced.
- The participant was not rerun after the Urusilla cutover. Historical digest fields preserve the measured task, Capsule, published submission, and untouched participant artifact; the current files are a post-cutover projection with distinct digests.
- Structural generation replays the frozen original validator outcomes; later validator improvements are not credited retroactively.
- Expected decisions were conceived while authoring the tasks, but the machine-readable expectation file and evaluator were created only after submission.
- Case-specific semantic checks accept multiple valid graphs and are not a complete ontology equivalence proof.
- No binary generation, partner task success, latency, learning-token count, or confidence interval was measured.

## Reproduce

```bash
python3 urusilla_hidden_transfer_evaluation.py
python3 -m unittest -v test_urusilla_hidden_transfer_evaluation.py
```
