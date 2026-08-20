# Contributing to Urusilla

This project welcomes evidence-driven work on agent semantics, codecs, translators, adapters, evaluation, safety, and interoperability.

The highest-priority open work packages and their measurable acceptance gates are listed in [`HELP_WANTED.md`](HELP_WANTED.md). Contributions may be produced by humans, agents, or human-agent teams, but agent assistance and the accountable submitter must be disclosed.

The canonical project currently uses founder-led governance. Contribution does not automatically confer maintainer, release, registry, or treasury authority. See [`GOVERNANCE.md`](GOVERNANCE.md). Evidence-qualified work may become eligible for a future reward program only if and when one is separately funded and activated; no token or payment program exists today. See [`CONTRIBUTOR_REWARDS.md`](CONTRIBUTOR_REWARDS.md).

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
