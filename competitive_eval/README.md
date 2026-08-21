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

## External response exchange

`external_replay.py` now provides a dependency-free, content-addressed exchange
boundary for real model calls made by a separate operator. It does **not**
weaken the mock-only runner or make a provider call itself.

The intended sequential workflow is:

1. construct the exact provider-neutral `CallRequest` and freeze its complete
   request and settings digests;
2. call `ExternalResponseStore.resolve(request)`;
3. if no response exists, catch `MissingExternalResponse` and give its
   `pending` object to an external operator;
4. capture the returned output, provider request/response IDs, exact resolved
   model, token usage, and inline raw receipt with its byte digest;
5. build or import the strict response bundle and resolve the same request
   offline; and
6. after the sequential run, require that no response record is unused.

Exact resume of the same call is idempotent. Within one bundle, reuse of one
provider request ID, response ID, or raw receipt across different calls is
rejected. Cross-bundle replay requires a future externally maintained receipt
index and is not prevented by this store alone. Missing token,
timing, model, or billing observations remain JSON `null`; they are never
converted to zero. A content-only UI capture may be replayed for semantic
debugging, but `require_core_usage_capture=True` rejects it as an incomplete
core provider-usage capture. That predicate covers provider IDs, exact requested
model/settings observation, a raw receipt, and complete input/output/total
usage only. It deliberately does not imply complete timing, billing, cache
accounting, normalization, authentication, or study evidence. Every record
remains claim-ineligible here: this module does not rerun a provider-specific
normalizer, authenticate an issuer, or assemble the complete research ledger.
The exported bundle repeats this boundary as machine-readable
`allowed_use`, `claim_eligible: false`, and fixed `claim_blockers` fields; a
consumer does not need to infer the restriction from prose.

One JSON bundle is capped at 128 MiB. This supports bounded pilot exchanges but
is not the final large-study storage format; A2/A3-scale runs need a future
content-addressed sharded or JSONL store rather than silently raising this cap.

Raw provider receipts can contain private prompts, account metadata, or other
sensitive material. Keep response bundles outside the public tree unless an
operator has reviewed their complete contents. Redacting a receipt creates a
different artifact and must not retain the original digest or be relabeled as
an exact provider capture.

This exchange is only the first bridge. `OfflineRunner` still rejects it until
provider token partitioning, external call ledgers, and the actual cold Capsule
delivery to the receiver are implemented. The current adaptive competitive arm
therefore remains bridge-mode plumbing with unmeasured model comprehension.
Content hashes also do not authenticate the provider or prove operator
independence.

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
