# A1 credentials and approval checklist

Status: **blocked pending every item below**. This file is a preparation aid; it is not an approval and it authorizes no call.

## Explicit authorization and budget

- [ ] Record a fresh human approval reference for A1 provider/model calls.
- [ ] Approve the controlling **USD 40** ceiling. Stop before the next call would cross USD 40, 3,456 total calls, or 2,304 paid calls.
- [ ] Confirm the selected A1 preset. `A1_plan` uses CTE/AutoForm/current surface; `A1_a0_cost_variant` uses CTE/JSON/current surface. The A0 USD 5.416144 reserve forecast covers only the latter trio, not a six-arm run.
- [ ] Approve public HotpotQA/WikiHop prompt transmission and the response-log retention policy.

## Endpoint credentials and exact identities

- [ ] OpenAI project/API credential with quota, billing access, usage metadata, and access to exact logical model `gpt-5-mini-2025-08-07`.
- [ ] Google project/API credential with quota, billing access, usage metadata, and access to exact logical model `gemini-3.7-flash` v1.
- [ ] Local Qwen artifact `Qwen/Qwen2.5-7B-Instruct@a09a35458c702b33eeacc393d103063234e8bc28` and approved BF16 compute.
- [ ] Archive a same-day provider model-metadata canary and pricing snapshot. Do not silently substitute model IDs.
- [ ] Pin exact pre-call token counters for every endpoint used by the adaptive selector. A0's O and G counters are planning proxies; hosted billed usage arrives too late to drive selection.

## Prompt, protocol, and parsing locks

- [ ] Install and verify the four upstream AutoForm YAML files against the SHA-256 values in `locks.json`.
- [ ] Accept and preregister the clean-lane substitutions: two agents, strict alternation, and eight base calls. These are not byte-exact archival replays of the three-agent AutoForm configs.
- [ ] Resolve the archival prose arm's missing typed unresolved-request field. Until then, cross-stratum early-stop comparisons remain claim-ineligible.
- [ ] Freeze provider system/user message mapping, temperature, output limit, stop behavior, timeout, no automatic provider retry, safety handling, refusal mapping, and raw-response retention.
- [ ] Freeze strict parsers, the one format-only repair prompt, adaptive-to-CTE fallback, and intent-to-treat denominator rules.
- [ ] Confirm tools, web access, browsing, grounding, retrieval, and hidden side channels are disabled.

## Evidence and preregistration

- [ ] Create an immutable Git revision; this repository currently has no valid `HEAD`, so the dry run uses file digests only.
- [ ] Freeze the implementation digest inventory, run manifest, episode manifest, analysis plan, bootstrap seed/PRNG, quantile convention, cluster sensitivity, and Holm hypothesis families before outcomes are visible.
- [ ] Complete and freeze the paired-discordance power audit. If it fails, use the separately approved A5 extension; never relax the one-percentage-point margin after seeing results.
- [ ] Run all positive and negative conformance tests, verify the exact Grammar Capsule digest, and archive the conformance-report digest.
- [ ] Verify an unseen partner and keep CTE/JSON fallback available. Advertise adaptive support only as `bridge`, never as native model support.
- [ ] Reconcile raw provider billed input/output/cache/reasoning annotations to the non-overlapping research ledger. Unknown usage remains explicitly unclassified.
- [ ] Review all negative, malformed, repair, fallback, timeout, refusal, and cold-start results before any stage promotion.

No A1 execution may begin until all applicable boxes are checked and the approval reference is embedded in a newly frozen live-run manifest.
