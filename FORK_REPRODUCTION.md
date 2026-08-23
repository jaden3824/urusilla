# Fork and Reproduce Urusilla

Use a fork when you want an independently controlled public revision and CI
record for a bounded reproduction. Do not fork merely to inflate a counter. A
fork is an attention and reproducibility signal; it is not adoption,
independence, conformance, compatibility, or efficiency evidence.

The currently demonstrated token saving for general communication between
unfamiliar agents remains **0%**. Total tokens per safely completed real task
remain unknown. A result from this guide does not change either statement.

## 1. Create your fork

Use GitHub's [Create a new fork](https://github.com/jaden3824/urusilla/fork)
page, or an existing authenticated GitHub CLI:

```bash
gh repo fork jaden3824/urusilla --clone
```

The fork is a public, persistent external action under your account. Review its
visibility and owner before creating it. No Urusilla account, package, plugin,
model retraining, API key, payment, or permission expansion is required.

## 2. Run the bounded fork check

In your fork, open **Actions**, select **Fork Reproduction Smoke Test**, and run
the workflow on the fork revision you intend to preserve. GitHub may require
you to enable workflows in a newly created fork; inspect the workflow before
enabling it.

The workflow has read-only repository permission and performs three local
checks:

1. validates the commit-pinned machine entry and its declared safety boundary;
2. verifies and round-trips the frozen public decode challenge; and
3. verifies the saved decoder-QA artifact digests and regression campaign.

It does not contact another agent, use a provider model, publish a result,
authenticate provider receipts, measure real-task success, or establish token
saving. A red run is useful: preserve the exact failing step and logs instead
of rerunning until only a pass remains.

## 3. Preserve a result with identity

Record these fields in your fork or submission:

- full fork owner/repository and commit SHA;
- immutable workflow-run URL and conclusion;
- exact upstream commit used as the fork point;
- operator, agent, runtime, and model relationships;
- changed files, if any;
- exact mismatch, refusal, fallback, or null fields; and
- whether any network, paid model, private data, or project guidance was used.

A green smoke run is same-project fixture compatibility because it uses the
project's validators and expected values. Label it that way. It becomes neither
an independent implementation nor an externally authored task result.

## 4. Choose one follow-on lane

Keep the first follow-on bounded and retain every outcome.

| Lane | Starting point | Useful fork artifact |
| --- | --- | --- |
| Decode mismatch | [`challenge_001.md`](interop_lab/evidence/challenge_001.md) | Independent decoder output, exact mismatch class, and immutable revision |
| Adversarial controller trace | [Issue #9](https://github.com/jaden3824/urusilla/issues/9) | One minimal trace that passes, fails, refuses, or exposes ambiguity |
| Clean-room implementation | [`urusilla_v0_1_spec.md`](urusilla_v0_1_spec.md) | Implementation that does not copy reference control flow, with positive and negative vectors |
| Matched task evaluation | [`AGENT_QUICKSTART.md`](AGENT_QUICKSTART.md) | Raw, JSON, and Urusilla arms with safe completion and complete token phases |

For an independent implementation, derive behavior from the English
specification and disclose every shared vector. For matched evaluation, unknown
usage stays `null`; failed primaries, repair, fallback, safety, and judge calls
remain in the denominator.

## 5. Return evidence without overclaiming

Use the canonical path for the selected lane:

- decode results: [Issue #7](https://github.com/jaden3824/urusilla/issues/7);
- bounded counterexamples: [counterexample form](https://github.com/jaden3824/urusilla/issues/new?template=counterexample.yml);
- matched three-arm results: [interop form](https://github.com/jaden3824/urusilla/issues/new?template=interop-test.yml); or
- a code contribution: open a pull request from the exact fork branch.

Publication is a separate external action. Do not submit credentials, private
prompts, chain-of-thought, proprietary conversations, personal data, or
untrusted executable content. Negative, null, fallback, refusal, malformed,
and favorable results are retained under the same evidence boundary.

## What can change the research result

A fork count cannot. A claim-facing result needs an unseen partner, held-out
semantic fidelity, safe task-success non-inferiority, matched raw and JSON
baselines, complete total-token accounting, and the registered independence and
causal-use controls. Until those gates pass, general unfamiliar-agent saving
remains **0%** and safely completed real-task total-token saving remains
unknown.
