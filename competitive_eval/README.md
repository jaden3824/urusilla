# Competitive public-task evaluation harness

This directory contains an isolated, offline-first end-to-end harness for the
HotpotQA and WikiHop symbolic-dialogue track. It reads the frozen A0 artifacts
from `../work/competitive_public_task_preflight/` and verifies their exact
digests before use. It does not edit any root project file.

The implemented scope includes:

- provider-neutral run, episode, call, response, and observation manifests;
- all six planned representation arms and all nine ordered sender/receiver
  model-family pairs;
- deterministic bridge mapping from the strict `a,c,e,n,x` QA record into the
  current v0.6 adaptive surface;
- deterministic CBOR, MessagePack, typed Protobuf, and project-v0.2 wire-only
  controls that recover the same canonical JSON receiver record;
- a non-overlapping token, billed-usage, dollar, byte, latency, repair,
  retransmission, and fallback ledger;
- strict alternation, the eight-base-call cap, the common early-stop rule, one
  format-only repair, and CTE fallback for current-surface failures;
- atomic checkpoints with a verified per-episode hash chain;
- deterministic provider-free mocks;
- clustered paired bootstrap intervals, ratio-of-sums token analysis, Holm
  adjustment, promotion gates, and hard cost stops.

## Important evidence boundary

The dry run is plumbing evidence only. The mock uses the gold answer to produce
deterministic scripted outputs, which is explicitly recorded. It cannot measure
model comprehension, task quality, competitive performance, or efficiency.
No performance, near-leading, leading, or state-of-the-art claim follows.

A0 was refrozen for the current Urusilla artifact and now binds the CTE, canonical
JSON, and current adaptive prompt contracts to the current profile digest.
The exact upstream paper-natural and AutoForm YAML files
are not present in the A0 cache. Those arms are registered and exercised by
clearly labeled mock-only contracts, while any claim-ready execution fails
closed until the exact source files and digests are installed. The common
two-agent/eight-call lane is also a clean adaptation, not a literal archival
replay of every upstream YAML.

The current-artifact adaptive prompt remains larger than CTE for every pinned
tokenizer. The harness retains the complete conservative current cold charge;
the exact bytes and tokenizer counts are regenerated into `locks.json` and
`cold_amortization.json`. It does not use a future-aware cold optimizer. Hosted
OpenAI and Gemini tokenizer mappings remain planning proxies; only the frozen
Qwen tokenizer is endpoint-exact.

## Offline commands

Run from the project root using the pinned research environment:

```text
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m unittest discover -s competitive_eval/tests -v
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m competitive_eval.cli verify
```

Those two commands are the clean-clone stable lane. `verify` checks only
distributed public files against `artifacts/FROZEN_DIGESTS.json`; it requires
no dataset cache, ignored artifact, credential, network access, or provider
call. Dataset-dependent test classes skip explicitly when the separately
provisioned A0 cache is absent.

After installing and verifying the local A0 inputs, the extended local-only
lane is:

```text
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m competitive_eval.cli verify-local
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m competitive_eval.cli dry-run
```

The CLI contains no provider SDK, networking code, credential reader, or live
adapter. Any non-mock execution request is rejected with `ApprovalRequired`.

## Dataset-derived artifact boundary

The following evaluation products are intentionally local-only because they
embed prompts, model-facing observations, answers, or episode records derived
from HotpotQA and WikiHop inputs:

- `artifacts/a1_plan_episode_manifest.jsonl`;
- `artifacts/a1_plan_prompt_locks.jsonl`;
- `artifacts/a1_a0_cost_variant_episode_manifest.jsonl`;
- `artifacts/a1_a0_cost_variant_prompt_locks.jsonl`;
- `artifacts/mock_episode_manifest.jsonl`;
- `artifacts/mock_episode_results.jsonl`;
- `artifacts/mock_prompt_locks.jsonl`; and
- `artifacts/mock_turn_observations.jsonl`.

They are excluded by the repository `.gitignore` and are not part of the
source distribution. The public frozen digest inventory excludes all eight
local-only products. It retains their provenance locks only in a clearly
labeled non-required section; a digest entry does not redistribute a file or
grant a dataset license. Obtain the underlying evaluation data separately
under its applicable terms before regenerating these artifacts. The extended
local-only commands require the separately provisioned, digest-pinned A0 cache
under `../work/competitive_public_task_preflight/`; they fail closed when it is
absent or changed.
