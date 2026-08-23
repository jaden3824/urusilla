# Contributing to Urusilla

This project welcomes evidence-driven work on agent semantics, codecs, translators, adapters, evaluation, safety, and interoperability.

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Technical disagreement and unfavorable evidence are welcome; harassment, fabricated evidence, deceptive engagement, and repeated spam are not.

The highest-priority open work packages and their measurable acceptance gates are listed in [`HELP_WANTED.md`](HELP_WANTED.md). Contributions may be produced by humans, agents, or human-agent teams, but agent assistance and the accountable submitter must be disclosed.

For a small, reviewable first contribution, choose an item from the exact open
[`good first issue` queue](https://github.com/jaden3824/urusilla/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
The label marks bounded work; it does not make a contribution accepted evidence
or imply adoption, conformance, or efficiency.

You may bring an agent or runtime you already use; no Urusilla-specific agent, plugin, executable package, or model-weight installation is required for the bounded public tasks. A reproduction submission must pin the applicable public task bundle, satisfy its published receipt and verifier requirements, and disclose the accountable operator, runtime, and shared-control relationships. Submission or structural validation does not by itself make a result accepted evidence or prove adoption, operator independence, conformance, or efficiency.

For the shortest machine-readable route, start with [`contribution-entry.json`](contribution-entry.json). Validated counterexamples, null results, codec candidates, corpus examples, and reproductions are credited in [`CONTRIBUTORS_EVIDENCE.md`](CONTRIBUTORS_EVIDENCE.md) and its machine-readable [`contributor-evidence.json`](contributor-evidence.json). Those registries begin empty and remain separate from adoption claims.

## Working from a fork

A public fork gives you an independently controlled revision, CI history, and
place to preserve an unfavorable result without granting the canonical project
write access. Use [`FORK_REPRODUCTION.md`](FORK_REPRODUCTION.md) for the bounded
fork-to-result path. The manual **Fork Reproduction Smoke Test** is intentionally
smaller than the repository-wide conformance suite and requires no package
installation.

Fork count, workflow success, and a copied fixture are not research results.
Evidence begins only when a submission pins the fork revision and run, states
the operator and implementation relationship, and preserves mismatches,
refusals, nulls, repairs, fallbacks, and unknown token fields. Do not create
duplicate or coordinated accounts to change repository metrics.

The documentation-only [`EVIDENCE_TRANSPARENCY_LOG.md`](EVIDENCE_TRANSPARENCY_LOG.md) proposal describes a future GitHub-first append-only submission log. It is not deployed, accepts no live records today, and cannot upgrade a submission into independence, adoption, conformance, or general-efficiency evidence by itself.

The canonical project currently uses founder-led governance. Submitting a contribution for inclusion licenses it under Apache-2.0 and does not by itself assign the contributor's copyright. Contribution does not automatically confer maintainer status, release or registry authority, signing access, project-account control, ownership of canonical project assets, or treasury authority. See [`GOVERNANCE.md`](GOVERNANCE.md). Evidence-qualified work may become eligible for a future reward program only if and when one is separately funded and activated; no token or payment program exists today. See [`CONTRIBUTOR_REWARDS.md`](CONTRIBUTOR_REWARDS.md).

## Principles

1. Measure claims instead of asserting efficiency or adoption.
2. Compare against the strongest available baseline, including terse natural language, minified structured data, compression, and schema-aware codecs.
3. Preserve unfavorable results and state test boundaries.
4. Do not claim standard status, official A2A affiliation, IANA registration, or an owned namespace without evidence.
5. Do not submit real user conversations, secrets, personal data, or private prompts.
6. Keep normative semantics separate from transport and model-specific optimization.
7. Unknown or unsafe inputs must fail closed before side effects.
8. Disclose material agent or model assistance, paid calls, external services, and private-data use.
9. A separate agent process is not independent evidence unless its implementation or data path is genuinely independent.
10. The bundled Node.js lane is same-project cross-runtime evidence because its fixtures were derived from the project Python oracle; do not cite it as external independent reproduction.

## Before opening a pull request

Match local validation to the files and claims changed. A documentation link fix
does not need to rerun research benchmarks, while behavior or evidence changes
must retain their full applicable checks.

| Change type | Local validation before the pull request | Benchmark and evidence requirement |
| --- | --- | --- |
| Documentation, links, or issue-template text only; no normative or result change | Review the rendered Markdown or YAML, verify every changed local path and external URL, and run a whitespace/diff check. | No research benchmark is required. |
| Focused non-normative code or tests that cannot change wire/runtime behavior | Run the directly affected unit-test modules and any formatter or static check used by that area. | Run an artifact-specific reproducer only if a generated artifact changes. |
| Runtime, parser, codec, adapter, or routing behavior | Run affected positive and negative tests, then the full unit suite: `python3 -m unittest discover -s . -p 'test_*.py' -v`. | Run `python3 urusilla_benchmark.py` and/or `python3 urusilla_wire_v02.py --benchmark` whenever the corresponding representation, cost, timing, or generated report can change. Reproduce all affected digests and reports. |
| Normative protocol/specification/version, claim-bearing evidence/results, or repository-wide behavior | Run the full unit suite, both benchmark commands above, every affected conformance or artifact-specific reproducer, and the compatibility/security checks required below. | Include positive and negative vectors, reproduce affected reports and digests, and preserve unfavorable, failed, and `null` outcomes. |

Confirm that all documentation is written in English. For generated benchmark
reports, verify that the committed results reproduce within the report's stated
machine-dependent timing boundary.

For every pull request, the current CI run is the repository-wide pass/fail
authority even when the local row is intentionally narrow. Do not copy a mutable
total test count into living documentation; isolated experiment reports may
retain counts bound to their frozen source and artifact identities.

## Specification changes

A semantic change must include:

- a problem statement and observable semantics;
- compatibility and downgrade behavior;
- positive and negative conformance vectors;
- translator behavior;
- security and privacy analysis;
- benchmark impact;
- a new versioned identifier for breaking changes.

## Adoption records

Adoption claims require the evidence listed in [`ADOPTERS.md`](ADOPTERS.md). Project maintainers will reject unverifiable or promotional-only entries.
