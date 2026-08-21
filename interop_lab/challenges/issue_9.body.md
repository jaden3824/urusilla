## Objective

Add one minimal adversarial test or reproducer for Urusilla’s evolving-session keep gate.

**Current demonstrated general token saving: 0%.** This issue seeks falsification and controller hardening—not promotion or adoption evidence.

- Pinned revision: https://github.com/jaden3824/urusilla/tree/f612ea1
- Contract: https://github.com/jaden3824/urusilla/blob/f612ea1/EVOLVING_SURFACE.md
- Discussion: https://github.com/jaden3824/urusilla/discussions/8

Target any case that could incorrectly authorize live routing, accept stale/replayed/mismatched evidence, leak observation data into a held-out trial, retain after incomplete accounting or non-positive inclusive value, forget failed-attempt costs, accept a no-op/parent regression, reuse a retired alias, or fail open.

Baseline:

```bash
python3 -m unittest -v urusilla_hybrid_runtime.tests.test_evolution
```

## Definition of done

Submit one of:

- a test that fails at the pinned revision and demonstrates an unsafe or incorrectly retained state;
- a minimal executable reproducer;
- a precise specification ambiguity with two conflicting expected outcomes; or
- a reasoned null result showing the attempted attack is already rejected.

Include exact commit, environment/Python, human or agent authorship, model/runtime assistance, minimal event trace, expected and actual results, exact command/output, and every known/zero/unknown usage field. Preserve a useful failure before repairing production code. Same-project fixtures or imports must be disclosed and are not independent reproduction.

Run only inspected code, preferably without secrets. This task does not request external actions, account creation, autonomous posting, propagation, spending, persistence, or permission changes. Do not submit private prompts, chain-of-thought, credentials, user data, or content you cannot redistribute. Unfavorable results and refusals are valid; no bounty is active.
