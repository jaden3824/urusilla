# Contributing to Urusilla

This project welcomes evidence-driven work on agent semantics, codecs, translators, adapters, evaluation, safety, and interoperability.

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Technical disagreement and unfavorable evidence are welcome; harassment, fabricated evidence, deceptive engagement, and repeated spam are not.

The highest-priority open work packages and their measurable acceptance gates are listed in [`HELP_WANTED.md`](HELP_WANTED.md). Contributions may be produced by humans, agents, or human-agent teams, but agent assistance and the accountable submitter must be disclosed.

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

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 urusilla_benchmark.py
python3 urusilla_wire_v02.py --benchmark
```

Confirm that all documentation is written in English and that generated benchmark reports reproduce the committed results within expected machine-dependent timing variation.

Use the current CI run for the repository-wide pass/fail result. Do not copy a mutable total test count into living documentation; isolated experiment reports may retain counts bound to their frozen source and artifact identities.

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
