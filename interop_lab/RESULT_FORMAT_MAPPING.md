# Urusilla result formats and revision authority

This note separates two related but non-interchangeable result contracts. It is
an offline access aid, not a new result schema, migration program, signature,
or evidence claim.

## Which contract is authoritative?

| Use | Authoritative local source | What it validates |
|---|---|---|
| Repository-access result | `interop_lab/result.schema.json` plus `interop_lab/validate_result.py` | One bounded summary for `quick_60s`, `quick_10m`, `decode`, or `matched_eval` |
| Hugging Face external result | `challenge.result_contract` inside the exact `hf_dataset/data/challenge.jsonl` record used for the run | The full `urusilla-hf-external-result/1` submission, including repetitions, cold/warm profiles, runtime, sampling, arm order, transcripts, and the detailed token ledger |
| Hugging Face challenge pack | `hf_dataset/schema.json` plus `hf_dataset/validate.py` | The project-authored challenge record itself, **not** an external result |
| Agent discovery | `agent-entry.json` plus `interop_lab/validate_agent_entry.py` | Paths, byte identities, access boundaries, and bounded tracks; it does not validate an experiment |

Use the contract named by the destination. A
`urusilla-agent-result/1` record is not a drop-in
`urusilla-hf-external-result/1` record, and relabeling either schema version is
invalid. Neither format authenticates a publisher, proves operator
independence, or grants authority for persistence, spending, permission
changes, publication, or another external effect.

## Revision layers: `f612...` versus `1358...`

The two commits identify different provenance layers:

1. `f612ea141e409693b27e93cefef0876eff9542ed` is the frozen **outer GitHub
   repository baseline** used by `agent-entry.json`. It identifies the exact
   local copies of `hf_dataset/README.md`, `hf_dataset/data/challenge.jsonl`,
   `hf_dataset/schema.json`, and `hf_dataset/validate.py`, as well as the other
   listed artifacts.
2. `1358de54c8a7034ee057a47e252e8947fe042f55` is the earlier **GitHub protocol
   source revision embedded inside the HF challenge record**. It is not a
   Hugging Face Hub commit. The record deliberately points its Capsule,
   Interop Lab, and language-specification URIs to that revision.

`1358...` is an ancestor of `f612...`. The Capsule file at both commits is
byte-identical: 33,476 bytes with SHA-256
`sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`.
That equality permits an exact Capsule-byte match; it does **not** make all
other documents at the two commits equivalent. In particular, do not silently
replace the HF record's embedded `1358...` protocol references with newer
`f612...` documents.

For a matched HF run, therefore record both layers:

- verify the outer challenge-record bytes against the `f612...` artifact entry
  when using this repository snapshot; and
- follow and report the inner `1358...` protocol references and Capsule digest
  exactly as embedded in that challenge record.

The Hugging Face Hub repository has its own commit history. A download from a
moving Hub branch such as `main` is not pinned by either GitHub commit above.
Record the exact Hub commit and downloaded file digests separately if the Hub
copy, rather than the frozen GitHub copy, is used.

A commit pins repository history. A SHA-256 digest identifies bytes. Neither is
a signature or a grant of authority; the Capsule remains unsigned.

## Field-level relationship

The repository format is a deliberately small summary. The HF format is the
full experiment record.

| Repository result | HF external result | Mapping rule |
|---|---|---|
| `schema_version` | `result_schema_version` | Different constants; never rename without rebuilding and validating the target record |
| `result_id` | `experiment_id` | May carry the same stable identifier if it satisfies both contracts |
| `track` | `challenge_record_id` | Only `matched_eval` can summarize the HF three-arm challenge; bind the exact challenge record ID separately |
| `baseline_revision` and `artifact_evidence` | challenge/protocol provenance plus transcript artifacts | Preserve the full GitHub revision, Capsule digest, and immutable result/challenge artifact digests |
| `participant` | `experiment_class`, `operator_relationships`, and `runtime` | Not one-to-one; do not infer independence from `kind` or operator count |
| none | `sampling` and `arm_order` | Required by HF; cannot be reconstructed from the repository summary |
| `token_accounting.arms` | `profiles[].arms[]` | Repository format has one summary per arm; HF retains cold/warm profiles and repetitions |
| `outcome` | `evaluation`, `transcript_artifacts`, and `limitations` | Preserve the observable result, evidence URI/digest, failures, and limitations |
| `safety_boundary` | `safety` | The target must remain at least as restrictive; publication is separately authorized |
| `claim_boundary` | `evaluation` and `limitations` | A bounded repository claim cannot be promoted to adoption, SOTA, or population evidence |

Information that exists only in the HF format—per-repetition inputs and
outputs, sampling, arm order, adoption decisions, fallbacks, latency, cost,
count sources, cold/warm separation, and operator relationships—must remain in
the HF record or an immutable referenced artifact. Pointing
`outcome.evidence_uri` at that artifact is allowed, but it does not make the
smaller repository record lossless.

## Token-ledger crosswalk

There is no automatic lossless crosswalk. A mapper must first define
non-overlapping measurement boundaries for its runtime, preserve every
provider-reported receipt, and disclose the aggregation rule.

| Repository phase | Possible HF source categories | Constraint |
|---|---|---|
| `setup` | `format_induction`, `negotiation_profile` | Sum only setup charged to the same profile and arm; disclose amortization |
| `sender`, `router`, `receiver`, `reasoning` | `task_input`, `system_role`, `agent_input_history`, `encode_decode_model`, `hidden_reasoning_billed`, `unclassified` | No universal one-to-one mapping; allocate by an experiment-specific, sealed rule |
| `output` | `agent_output_visible`, `final_answer` | Sum only when the two HF categories are mutually exclusive in that record |
| `repair` | `repair_retry` | Include every failed or repeated attempt |
| `fallback` | usually `repair_retry` or `unclassified` | HF has no dedicated fallback-token category; state the chosen non-overlapping allocation |
| `tool` | `tool_request`, `tool_result` | Include both sides and preserve zero versus unknown |
| `safety` | `safety_filter` | Preserve provider/source disclosure |
| `judge` | no dedicated HF category | Keep as separate evaluation evidence unless the HF contract is explicitly extended; do not hide it in deployment totals |
| `total` | `total_tokens` | Copy only after every component is reconciled under the declared crosswalk |

If any required component is undisclosed or cannot be allocated without
overlap, use JSON `null`, set the repository accounting status to `incomplete`,
and make no complete-cost or positive efficiency claim. Never turn unknown
into zero.

Multiple HF repetitions also cannot be collapsed into the repository arm's
single booleans without a declared aggregation rule. The safest path is to
retain the full HF result, create a clearly labeled bounded summary, and bind
the summary to the immutable full-result URI and digest.

## Read-only validation

The repository validator accepts a result on standard input, so no result file
must be created inside the checkout:

```text
PYTHONDONTWRITEBYTECODE=1 python3 interop_lab/validate_result.py - --json < /absolute/path/to/result.json
```

It reads the local schema and stdin, performs no network call, and writes only
its report to stdout. Validation does not publish the record.
