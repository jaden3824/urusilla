"""Deterministic artifact and English dry-run report generation."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .canonical import (
    atomic_write,
    atomic_write_json,
    canonical_bytes,
    canonical_json,
    sha256_bytes,
    sha256_file,
)
from .config import (
    A0_ADAPTIVE_PROMPT_TOKEN_OVERHEAD_VS_CTE,
    A0_COLD_ARTIFACT_BYTES,
    A0_COLD_ARTIFACT_LOCKS,
    A0_COLD_TOKENS,
    A1_ABSOLUTE_CALL_CAP_CONVENTION,
    A1_ABSOLUTE_PAID_CALL_CAP_CONVENTION,
    A1_APPROVAL_USD_CEILING,
    A1_BASE_CALL_RESERVE,
    A1_ESTIMATED_PAID_USD,
    A1_ESTIMATED_WITH_RESERVE_USD,
    A1_PAID_CALL_RESERVE,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED_HEX,
    FROZEN_FILE_DIGESTS,
    HARNESS_VERSION,
    LEDGER_CATEGORIES,
    LOCAL_ONLY_ARTIFACTS,
    MODEL_SPECS,
    ORDERED_PAIRS,
    PACKAGE_ROOT,
    PROJECT_ROOT,
    PAPER_PROMPT_SOURCE_LOCKS,
    PRIMARY_BASELINE,
    REPRESENTATION_ARMS,
    STAGES,
    WIRE_CONTROLS,
)
from .gates import competitive_claim_gate, receiver_family_regression_gate
from .manifests import (
    EpisodeManifest,
    _common_prompt,
    _split_for_item,
    build_episode_manifests,
    build_run_manifest,
    manifest_lock_summary,
    verify_frozen_inputs,
)
from .mocks import ScriptedMockAdapter, mock_count
from .records import Evidence, QARecord
from .representations import SelectionContext, TokenCounter
from .runner import EpisodeResult, OfflineRunner, results_to_analysis_rows
from .statistical import exact_mcnemar, holm_adjust, paired_bootstrap
from .wire_controls import corrupt_frame, decode_wire_control, encode_wire_control


ARTIFACT_FORMAT = "competitive-eval-offline-artifacts-v1"
ARTIFACT_EPOCH = "2026-08-20"


def _write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(canonical_json(value) + "\n" for value in values)
    atomic_write(path, text.encode("utf-8"))


def _prompt_lock_records(
    inputs: Any, episodes: Sequence[EpisodeManifest]
) -> tuple[dict[str, Any], ...]:
    items = {
        item.key: item
        for values in inputs.datasets.values()
        for item in values
    }
    by_digest: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        value = episode.value
        item = items[value["item_key"]]
        split = _split_for_item(item, value["split"]["seed"], value["split"]["mode"])
        for agent in ("A", "B"):
            prompt, task_slice, role_slice = _common_prompt(
                item, split, agent, value["arm"]
            )
            digest = sha256_bytes(prompt.encode("utf-8"))
            expected = value["prompts"][agent]
            if digest != expected["prompt_sha256"]:
                raise RuntimeError("rendered prompt no longer matches its episode lock")
            record = {
                "format": "competitive-eval-prompt-lock-v1",
                "prompt_sha256": digest,
                "prompt_utf8_bytes": len(prompt.encode("utf-8")),
                "prompt_text": prompt,
                "role_slice_sha256": sha256_bytes(role_slice.encode("utf-8")),
                "task_slice_sha256": sha256_bytes(task_slice.encode("utf-8")),
                "dataset": value["dataset"],
                "item_key": value["item_key"],
                "split_digest": value["split"]["digest"],
                "arm": value["arm"],
                "agent": agent,
                "mock_only": True,
                "archival_exact": value["arm"] not in {
                    "paper_natural_language",
                    "autoform",
                },
            }
            existing = by_digest.get(digest)
            if existing is not None and existing != record:
                raise RuntimeError("one prompt digest maps to different lock metadata")
            by_digest[digest] = record
    return tuple(by_digest[key] for key in sorted(by_digest))


def _observation_from_event(event: Any) -> dict[str, Any]:
    payload = event.payload
    requests = payload["requests"]
    responses = payload["responses"]
    if len(requests) != len(responses):
        raise RuntimeError("checkpoint turn does not pair every request and response")
    for request, response in zip(requests, responses):
        if request["call_id"] != response["call_id"]:
            raise RuntimeError("checkpoint request/response call IDs differ")
        if request["mock_metadata"]["gold_answer_present"] is not False:
            raise RuntimeError("gold answer leaked into provider-neutral request metadata")
    value: dict[str, Any] = {
        "format": "competitive-eval-mock-turn-observation-v1",
        "episode_id": event.value["episode_id"],
        "event_sequence": event.sequence,
        "checkpoint_event_sha256": event.event_sha256,
        "requests": requests,
        "responses": responses,
        "representation_artifact": payload.get("artifact"),
        "provider_calls": 0,
        "paid_calls": 0,
        "actual_billed_usd": "0",
    }
    value["observation_sha256"] = sha256_bytes(canonical_bytes(value))
    return value


def _fraction_from_result(value: Mapping[str, Any]) -> Fraction:
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def _nearest_rank(values: Sequence[int], numerator: int, denominator: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = (numerator * len(ordered) + denominator - 1) // denominator
    return ordered[max(0, rank - 1)]


def _rate_object(count: int, denominator: int) -> dict[str, Any]:
    value = Fraction(count, denominator) if denominator else Fraction(0, 1)
    return {
        "count": count,
        "denominator": denominator,
        "fraction": f"{value.numerator}/{value.denominator}",
        "decimal": f"{float(value):.12f}",
    }


def _aggregate_results(results: Sequence[EpisodeResult]) -> dict[str, Any]:
    arms: dict[str, Any] = {}
    for arm in REPRESENTATION_ARMS:
        selected = [result.value for result in results if result.value["arm"] == arm]
        categories = {
            category: sum(
                int(result["ledger"]["category_totals"][category])
                for result in selected
            )
            for category in LEDGER_CATEGORIES
        }
        terminal_reasons = Counter(result["terminal_reason"] for result in selected)
        calls = [call for result in selected for call in result["ledger"]["calls"]]
        end_to_end = [int(call["timing"]["end_to_end_ns"]) for call in calls]
        repairs = sum(int(result["ledger"]["repair_calls"]) for result in selected)
        fallbacks = sum(int(result["ledger"]["fallback_calls"]) for result in selected)
        malformed = sum(int(result["ledger"]["malformed_attempts"]) for result in selected)
        timeouts = sum(int(result["ledger"]["timeout_attempts"]) for result in selected)
        refusals = sum(int(result["ledger"]["refusal_attempts"]) for result in selected)
        arms[arm] = {
            "episodes": len(selected),
            "safe_task_successes": sum(bool(result["safe_task_success"]) for result in selected),
            "normalized_exact_matches": sum(
                result["metrics"]["normalized_exact_match"] == 1.0 for result in selected
            ),
            "base_calls": sum(int(result["ledger"]["base_calls"]) for result in selected),
            "mock_calls_including_repairs": sum(
                len(result["ledger"]["calls"]) for result in selected
            ),
            "repair_calls": repairs,
            "fallback_calls": fallbacks,
            "malformed_attempts": malformed,
            "timeout_attempts": timeouts,
            "refusal_attempts": refusals,
            "t_total": sum(int(result["ledger"]["t_total"]) for result in selected),
            "judge_tokens": sum(int(result["ledger"]["judge_tokens"]) for result in selected),
            "token_categories": categories,
            "communication_only_output_tokens": (
                categories["agent_output_visible"] + categories["final_answer"]
            ),
            "cold_profile_bytes": sum(
                int(call["wire"]["cold_profile_bytes"])
                for result in selected
                for call in result["ledger"]["calls"]
            ),
            "transmitted_bytes": sum(
                int(result["ledger"]["transmitted_bytes"]) for result in selected
            ),
            "actual_billed_usd": "0",
            "estimated_usd": "0",
            "terminal_reasons": dict(sorted(terminal_reasons.items())),
            "episode_rates": {
                "repair": _rate_object(repairs, len(selected)),
                "fallback": _rate_object(fallbacks, len(selected)),
                "malformed": _rate_object(malformed, len(selected)),
                "timeout": _rate_object(timeouts, len(selected)),
                "refusal": _rate_object(refusals, len(selected)),
            },
            "logical_end_to_end_latency_ns": {
                "observations": len(end_to_end),
                "p50_nearest_rank": _nearest_rank(end_to_end, 50, 100),
                "p95_nearest_rank": _nearest_rank(end_to_end, 95, 100),
                "p99_nearest_rank": _nearest_rank(end_to_end, 99, 100),
                "wall_clock_measurement": False,
            },
            "claim_eligible": False,
        }
    return {
        "format": "competitive-eval-mock-aggregate-v1",
        "episode_count": len(results),
        "arms": arms,
        "provider_calls": 0,
        "paid_calls": 0,
        "actual_billed_usd": "0",
        "claim_eligible": False,
    }


def _cold_amortization() -> dict[str, Any]:
    lengths = (1, 2, 4, 8, 16, 32, 64, 128)
    return {
        "format": "competitive-eval-cold-artifact-amortization-v1",
        "warning": (
            "Artifact-only arithmetic. It is not a model-token saving result, and "
            "one-time charging requires independently verified persistent context."
        ),
        "cold_artifact_utf8_bytes": A0_COLD_ARTIFACT_BYTES,
        "warm_incremental_artifact_bytes": 0,
        "logical_artifact_locks": A0_COLD_ARTIFACT_LOCKS,
        "session_lengths": list(lengths),
        "tokenizers": {
            tokenizer: {
                "cold_artifact_tokens": cold_tokens,
                "warm_incremental_artifact_tokens": 0,
                "amortized_cold_tokens_per_message": {
                    str(length): {
                        "numerator": cold_tokens,
                        "denominator": length,
                        "decimal": f"{cold_tokens / length:.12f}",
                    }
                    for length in lengths
                },
                "amortized_cold_bytes_per_message": {
                    str(length): {
                        "numerator": A0_COLD_ARTIFACT_BYTES,
                        "denominator": length,
                        "decimal": f"{A0_COLD_ARTIFACT_BYTES / length:.12f}",
                    }
                    for length in lengths
                },
            }
            for tokenizer, cold_tokens in A0_COLD_TOKENS.items()
        },
        "stateless_surface_prompt_rule": "replay and charge every request",
        "decoded_json_bridge_rule": "transport-only; no comprehension claim",
        "claim_eligible": False,
    }


def _bootstrap_analysis(results: Sequence[EpisodeResult]) -> dict[str, Any]:
    rows = results_to_analysis_rows(results)
    overall: dict[str, Any] = {}
    mcnemar: dict[str, Any] = {}
    for arm in REPRESENTATION_ARMS:
        if arm == PRIMARY_BASELINE:
            continue
        overall[arm] = paired_bootstrap(
            rows,
            candidate_arm=arm,
            baseline_arm=PRIMARY_BASELINE,
            analysis_id=f"mock-overall:{arm}",
        )
        mcnemar[arm] = exact_mcnemar(
            rows, candidate_arm=arm, baseline_arm=PRIMARY_BASELINE
        )

    primary = "current_adaptive_surface"
    tasks: dict[str, Any] = {}
    for task in ("hotpotqa", "wikihop"):
        tasks[task] = paired_bootstrap(
            [row for row in rows if row.task_family == task],
            candidate_arm=primary,
            baseline_arm=PRIMARY_BASELINE,
            analysis_id=f"mock-current-task:{task}",
        )
    receivers: dict[str, Any] = {}
    for receiver in ("O", "G", "Q"):
        receivers[receiver] = paired_bootstrap(
            [row for row in rows if row.receiver_family == receiver],
            candidate_arm=primary,
            baseline_arm=PRIMARY_BASELINE,
            analysis_id=f"mock-current-receiver:{receiver}",
        )

    success_p = {
        **{
            f"task:{task}": _fraction_from_result(value["success"]["centered_bootstrap_p"])
            for task, value in tasks.items()
        },
        **{
            f"receiver:{receiver}": _fraction_from_result(
                value["success"]["centered_bootstrap_p"]
            )
            for receiver, value in receivers.items()
        },
    }
    token_p = {
        f"task:{task}": _fraction_from_result(value["tokens"]["centered_bootstrap_p"])
        for task, value in tasks.items()
    }
    item_only = paired_bootstrap(
        rows,
        candidate_arm=primary,
        baseline_arm=PRIMARY_BASELINE,
        analysis_id="mock-current-item-only-sensitivity",
        item_only_cluster=True,
    )
    receiver_points = {
        receiver: float(_fraction_from_result(value["success"]["point"]))
        for receiver, value in receivers.items()
    }
    receiver_gate = receiver_family_regression_gate(receiver_points)
    return {
        "format": "competitive-eval-mock-analysis-v1",
        "warning": (
            "Deterministic gold-using mocks are plumbing fixtures, not model samples; "
            "all intervals and p-values below are test vectors only."
        ),
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed_hex": BOOTSTRAP_SEED_HEX,
        "candidate_overall": overall,
        "mcnemar_sensitivity_overall": mcnemar,
        "current_surface_task_marginals": tasks,
        "current_surface_receiver_marginals": receivers,
        "current_surface_item_only_sensitivity": item_only,
        "holm_success_family": holm_adjust(
            success_p,
            expected_hypotheses=(
                "task:hotpotqa",
                "task:wikihop",
                "receiver:O",
                "receiver:G",
                "receiver:Q",
            ),
        ),
        "holm_token_task_family": holm_adjust(
            token_p,
            expected_hypotheses=("task:hotpotqa", "task:wikihop"),
        ),
        "power_gate": "blocked_not_frozen",
        "receiver_family_regression_gate": receiver_gate,
        "competitive_claim_gate": competitive_claim_gate(
            all_success_ni_pass=False,
            all_task_token_pass=False,
            holm_pass=False,
            three_model_families=True,
            required_pairings_complete=True,
            three_repeats=False,
            complete_cost_ledger=True,
            power_gate_pass=False,
            negative_results_visible=True,
            no_receiver_regression_over_one_pp=receiver_gate["passed"],
        ),
        "claim_eligible": False,
    }


def _wire_results() -> dict[str, Any]:
    record = QARecord(
        answer="offline-dry-run-answer",
        claims=("wire controls preserve one typed record",),
        evidence=(Evidence("deterministic fixture A", "A"), Evidence("deterministic fixture B", "B")),
        needs=(),
        act="agree",
    )
    context = SelectionContext(
        episode_id="1" * 64,
        turn_index=0,
        sender="A",
        receiver="B",
        counter=TokenCounter(
            key="qwen2_5_7b_instruct",
            fingerprint="deterministic-utf8-quarter-mock-v1",
            exact_for_endpoint=True,
            count_fn=mock_count,
        ),
        artifacts_cached=False,
    )
    outputs: list[dict[str, Any]] = []
    for codec in WIRE_CONTROLS:
        result, frame = encode_wire_control(codec, record, context)
        recovered = decode_wire_control(codec, frame, record.sha256)
        corruption_rejected = False
        try:
            decode_wire_control(codec, corrupt_frame(frame), record.sha256)
        except Exception:
            corruption_rejected = True
        outputs.append(
            {
                **result.to_object(),
                "frame_sha256": sha256_bytes(frame),
                "corruption_rejected": corruption_rejected,
                "recovered_record_sha256": recovered.sha256,
            }
        )
    receiver_digests = {item["receiver_text_sha256"] for item in outputs}
    if len(receiver_digests) != 1 or not all(item["corruption_rejected"] for item in outputs):
        raise RuntimeError("wire-control dry run did not preserve one corruption-safe receiver record")
    return {
        "format": "competitive-eval-wire-control-results-v1",
        "record_sha256": record.sha256,
        "same_receiver_text_for_all_codecs": True,
        "additional_model_calls": 0,
        "controls": outputs,
        "claim_eligible": False,
    }


def _stage_summary() -> dict[str, Any]:
    stages: dict[str, Any] = {}
    for name, gate in STAGES.items():
        episodes = gate.items * len(gate.arms) * len(gate.pairs) * gate.repeats
        stages[name] = {
            "items": gate.items,
            "arms": list(gate.arms),
            "ordered_pairs": [list(pair) for pair in gate.pairs],
            "repeats": gate.repeats,
            "episode_count": episodes,
            "base_call_cap": gate.base_call_cap,
            "planning_usd_high": gate.planning_usd_high,
            "requires_fresh_approval": gate.requires_fresh_approval,
            "note": gate.note,
        }
        if name != "A0" and episodes * 8 != gate.base_call_cap:
            raise RuntimeError(f"stage {name} call cap does not reconcile")
    return {
        "format": "competitive-eval-stage-and-cost-gates-v1",
        "stages": stages,
        "a1_plan_and_a0_cost_variant_are_distinct": True,
        "a1_all_six_arms_same_three_pairs": {
            "episodes": 40 * 6 * 3,
            "base_call_cap": 40 * 6 * 3 * 8,
            "covered_by_a0_cost_forecast": False,
        },
        "a1_reserves": {
            "base_calls": A1_BASE_CALL_RESERVE,
            "paid_calls": A1_PAID_CALL_RESERVE,
            "absolute_call_cap_new_safety_convention": A1_ABSOLUTE_CALL_CAP_CONVENTION,
            "absolute_paid_call_cap_new_safety_convention": A1_ABSOLUTE_PAID_CALL_CAP_CONVENTION,
        },
        "a1_costs": {
            "estimated_paid_usd": A1_ESTIMATED_PAID_USD,
            "estimated_with_reserve_usd": A1_ESTIMATED_WITH_RESERVE_USD,
            "controlling_approval_ceiling_usd": A1_APPROVAL_USD_CEILING,
            "stop_before_next_call_crosses_any_cap": True,
        },
        "per_episode": {
            "strict_alternation": True,
            "max_base_calls": 8,
            "max_calls_per_agent": 4,
            "max_format_repairs": 1,
            "early_stop_requires_same_typed_answer_and_no_unresolved_request": True,
            "opaque_archival_arms_never_use_heuristic_early_stop": True,
            "current_surface_failure_fallback": "compact_terse_english",
            "failures_remain_in_denominator": True,
        },
    }


def _checklist_text() -> str:
    return """# A1 credentials and approval checklist

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
"""


def _report_text(
    *,
    aggregate: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    a1_plan_count: int,
    a1_cost_count: int,
    analysis: Mapping[str, Any],
    wire: Mapping[str, Any],
    verification: Mapping[str, Any],
    checkpoint_digest: str,
    adapter_invocations: int,
) -> str:
    cte = aggregate["arms"]["compact_terse_english"]
    adaptive = aggregate["arms"]["current_adaptive_surface"]
    selector = aggregate["arms"]["oracle_free_adaptive_selector"]
    adaptive_point = analysis["candidate_overall"]["current_adaptive_surface"]["tokens"]["point"]["decimal"]
    rows = []
    for arm in REPRESENTATION_ARMS:
        value = aggregate["arms"][arm]
        rows.append(
            f"| `{arm}` | {value['episodes']} | {value['safe_task_successes']} | "
            f"{value['base_calls']} | {value['repair_calls']} | {value['fallback_calls']} | "
            f"{value['t_total']} | {value['token_categories']['negotiation_profile']} | "
            f"{value['cold_profile_bytes']} |"
        )
    overhead_rows = "\n".join(
        f"| `{name}` | {A0_COLD_TOKENS[name]} | +{A0_ADAPTIVE_PROMPT_TOKEN_OVERHEAD_VS_CTE[name]} |"
        for name in A0_COLD_TOKENS
    )
    return f"""# Competitive public-task harness: offline dry-run report

Artifact epoch: `{ARTIFACT_EPOCH}`  
Harness version: `{HARNESS_VERSION}`  
Run ID: `{run_manifest['run_id']}`

## Outcome

The isolated harness completed **{aggregate['episode_count']} deterministic mock episodes** spanning both frozen task families, all six representation arms, and all nine ordered sender/receiver pairs. It made **0 provider calls, 0 paid calls, and USD 0 in actual billed cost**. The adapter executed {adapter_invocations} local scripted calls, including any format-only repairs. The checkpoint event-chain digest was `{checkpoint_digest}`.

This is plumbing and reproducibility evidence only. The mock adapter uses the gold answer, exactly as declared in every observation. It does not measure model comprehension, task performance, competitive efficiency, or generalization. **No performance, near-leading, leading, competitive, or state-of-the-art claim is made.**

## Frozen input verification

- HotpotQA: {verification['hotpotqa_records']} records, SHA-256 `{FROZEN_FILE_DIGESTS['work/competitive_public_task_preflight/hotpotqa.jsonl']}`.
- WikiHop: {verification['wikihop_records']} records, SHA-256 `{FROZEN_FILE_DIGESTS['work/competitive_public_task_preflight/wikihop.jsonl']}`.
- The frozen WikiHop bytes and A0 snapshot contain **{verification['wikihop_context_blocks_observed']}** context blocks. The root preflight report says **{verification['root_report_context_blocks_text']}**. The harness trusts the byte-frozen source/snapshot and preserves this discrepancy instead of rewriting the data.
- The physical snapshot file digest and the embedded canonical snapshot digest are intentionally distinct; both are recorded in `locks.json`.
- Git revision: unavailable. File digests are used, and an immutable commit remains an A1 blocker.

## Mock matrix and complete ledger

| Arm | Episodes | Safe successes | Base calls | Repairs | Fallbacks | T_total | Cold/profile tokens | Cold bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

All malformed outputs, repairs, fallbacks, timeouts, and refusals remain in their originally assigned arm and in the denominator. Each call records the full non-overlapping token categories, judge tokens separately, wire bytes, retransmission, deterministic logical latency, repair/fallback flags, raw provider-usage placeholders, reconciliation status, estimated cost, and actual billed cost.

The paper-natural and AutoForm mock arms intentionally cannot earn `safe_task_success`: their archival-style `ANSWER:` parser does not invent typed provenance or a missing-request state. Their exact upstream YAML bytes are absent from A0, and the common two-agent/eight-call lane is a clean adaptation rather than a literal archival replay.

## Unfavorable adaptive cold accounting retained

The current adaptive arm recorded {adaptive['token_categories']['negotiation_profile']} cold/profile tokens and {adaptive['cold_profile_bytes']} cold bytes in this small matrix, versus {cte['token_categories']['negotiation_profile']} and {cte['cold_profile_bytes']} for CTE. Its mock ratio-of-sums token reduction relative to CTE was `{adaptive_point}`; a negative value means more charged tokens. The selector recorded {selector['token_categories']['negotiation_profile']} cold/profile tokens because its oracle-free cost rule avoided the cold surface when it was not cheaper.

The harness retains the conservative current-artifact current-surface
**{A0_COLD_ARTIFACT_BYTES:,}-byte charge per endpoint** and does not use a
future-aware cold optimizer. This current lock is bound by the current-artifact
A0 adaptive prompt lock:

| Current frozen counter | Cold tokens | Adaptive initial prompt overhead vs CTE |
|---|---:|---:|
{overhead_rows}

For a stateless `surface_prompt` boundary, any required grammar/profile replay must be charged on every request unless persistent context is independently verified. A `decoded_json_bridge` boundary is transport-only and cannot establish model comprehension.

## Statistics implementation exercised

The analysis artifact runs {BOOTSTRAP_RESAMPLES:,} deterministic paired bootstrap resamples using the frozen harness seed, SHA-256 counter rejection sampling, exact rational estimators, inverse-ECDF type-1 quantiles, item-by-ordered-pair clusters, and an item-only sensitivity. Success uses a one-sided 95% lower bound and passes only when it is strictly above `-0.010`. Token reduction is exactly `1 - sum(T_arm) / sum(T_CTE)`, with a two-sided 95% interval and a lower-bound gate at `0.25`. The artifact also records exact two-sided McNemar sensitivities, the receiver-family one-percentage-point point-regression gate, and complete five-hypothesis success and two-hypothesis task-token Holm families.

Those intervals and p-values are deterministic test vectors, not empirical claims. The competitive gate is false: this run has one repeat, gold-using mocks, unavailable paper prompt bytes, proxy hosted tokenizers, no frozen power audit, and no immutable implementation revision.

## Wire-only controls

All {len(wire['controls'])} controls—deterministic CBOR, sorted-map MessagePack, typed Protobuf, and project v0.2—recovered the exact same canonical receiver record, rejected a deterministic corruption, and added **0 model calls**. They measure transport/conversion facts only and are not separate task samples.

## A1 manifests and stopping gates

- `A1_plan`: {a1_plan_count} episodes for CTE/AutoForm/current surface.
- `A1_a0_cost_variant`: {a1_cost_count} episodes for CTE/JSON/current surface.
- Each preset has a 2,880 base-call cap. The frozen A0 cost forecast applies to the second trio only.
- A same-workload six-arm run would have 720 episodes and 5,760 base calls, so it is not silently substituted into either preset.
- The new conservative absolute A1 stops are 3,456 total calls, 2,304 paid calls, and USD 40. Stop before the next call would cross any limit.
- A1-to-A2 requires complete pairing, exact parsing throughout, and no arm point estimate below CTE by more than 0.030. Equality at `-0.030` passes; anything smaller fails.
- Every later stage requires fresh approval. The exact stage counts and caps are in `stage_and_cost_gates.json`.

## Limitations requiring resolution before A1

1. Select and preregister the A1 trio; the plan and A0 cost snapshot disagree.
2. Install the exact paper/AutoForm source files and resolve their two-agent, max-turn, and missing-request differences.
3. Pin exact pre-call endpoint tokenizers. Qwen is exact in A0; the hosted O and G mappings are planning proxies.
4. Create an immutable Git revision and freeze the new statistical conventions before outcomes.
5. Complete the paired-discordance power audit or use a separately approved A5 extension without relaxing the margin.
6. Obtain the credentials, public-data transmission approval, retention approval, and explicit paid-call authority listed in `A1_READINESS_CHECKLIST.md`.

## Reproduction artifacts

- `mock_episode_manifest.jsonl`: 108 provider-neutral episode manifests.
- `mock_episode_results.jsonl`: complete deterministic result and ledger objects.
- `mock_turn_observations.jsonl`: every provider-neutral mock request/response pair, including repairs.
- `mock_prompt_locks.jsonl`: complete rendered mock prompts with byte counts and digests.
- `a1_plan_episode_manifest.jsonl` and `a1_a0_cost_variant_episode_manifest.jsonl`: separate 360-episode locks.
- `a1_plan_prompt_locks.jsonl` and `a1_a0_cost_variant_prompt_locks.jsonl`: complete rendered prompt locks for each distinct preset.
- `analysis.json`: paired intervals, sensitivity, Holm, and claim gate.
- `wire_control_results.json`: no-duplicate-call transport controls.
- `cold_amortization.json`: explicit 1/2/4/8/16/32/64/128-message cold-artifact arithmetic.
- `locks.json`, `stage_and_cost_gates.json`, and `FROZEN_DIGESTS.json`: frozen identities and gates.
- `A1_READINESS_CHECKLIST.md`: credentials and approvals still required.

The prompt, episode, response, and turn-observation JSONL products are
dataset-derived and local-only. They are excluded from the public digest
inventory and source distribution. The public verifier requires none of them.

The unfavorable results and all claim blockers are intentionally retained.
"""


def _digest_inventory(artifact_dir: Path, verification: Mapping[str, Any]) -> dict[str, Any]:
    excluded = {
        artifact_dir / "FROZEN_DIGESTS.json",
        artifact_dir / "FROZEN_DIGESTS.sha256",
    }
    paths = [
        path
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path not in excluded
        and path.relative_to(PACKAGE_ROOT).as_posix() not in LOCAL_ONLY_ARTIFACTS
    ]
    files: dict[str, Any] = {}
    for path in sorted(paths, key=lambda item: item.relative_to(PACKAGE_ROOT).as_posix()):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        files[relative] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return {
        "format": "competitive-eval-public-digest-inventory-v2",
        "algorithm": "sha256",
        "artifact_epoch": ARTIFACT_EPOCH,
        "files": files,
        "root_current_files": {
            relative: sha256_file(PROJECT_ROOT / relative)
            for relative in (
                "urusilla_generalization_surface_v06.py",
                "urusilla_capsule_v0_1.json",
                "urusilla_adaptive_dialogue_profile.json",
                "urusilla_strong_codec_baseline.proto",
            )
        },
        "local_provenance_digests_not_required_by_public_verifier": verification[
            "verified_file_sha256"
        ],
        "local_only_artifacts_excluded": sorted(LOCAL_ONLY_ARTIFACTS),
        "self_digest_excluded": True,
        "detached_digest_file_excluded": True,
        "repository_commit": None,
        "claim_eligible": False,
        "provider_calls": 0,
        "network_used": False,
    }


def generate_dry_run(artifact_dir: Path | None = None) -> dict[str, Any]:
    """Run the full provider-free matrix and publish deterministic artifacts."""

    output = artifact_dir or (PACKAGE_ROOT / "artifacts")
    output.mkdir(parents=True, exist_ok=True)
    inputs = verify_frozen_inputs()
    episodes = build_episode_manifests(
        inputs,
        stage="A0",
        arms=REPRESENTATION_ARMS,
        pairs=ORDERED_PAIRS,
        items_per_dataset=1,
        repeats=1,
        mock_only=True,
    )
    if len(episodes) != 108:
        raise RuntimeError("offline matrix must contain exactly 108 episodes")
    run_manifest = build_run_manifest(episodes, stage="A0")
    gold = {
        episode.episode_id: next(
            item.answer
            for values in inputs.datasets.values()
            for item in values
            if item.key == episode.value["item_key"]
        )
        for episode in episodes
    }
    adapter = ScriptedMockAdapter(gold)
    with tempfile.TemporaryDirectory(prefix="competitive-eval-dry-run-") as temporary:
        runner = OfflineRunner(
            inputs=inputs,
            run_manifest=run_manifest,
            episodes=episodes,
            output_dir=Path(temporary),
            adapter=adapter,
        )
        results = runner.run_all()
        if len(results) != len(episodes):
            raise RuntimeError("offline dry run did not complete every episode")
        checkpoint_digest = runner.store.event_chain_digest()
        observations = tuple(
            _observation_from_event(event)
            for episode in episodes
            for event in runner.store.load(episode.episode_id)
            if event.event_type == "turn_completed"
        )
        budget = runner.budget.snapshot()
    if budget["provider_calls"] != 0 or budget["paid_calls"] != 0 or budget["actual_usd"] != "0":
        raise RuntimeError("offline dry run crossed the no-provider-call boundary")

    a1_plan = build_episode_manifests(inputs, stage="A1_plan", mock_only=True)
    a1_cost = build_episode_manifests(inputs, stage="A1_a0_cost_variant", mock_only=True)
    if len(a1_plan) != 360 or len(a1_cost) != 360:
        raise RuntimeError("A1 episode locks do not contain 360 episodes each")

    aggregate = _aggregate_results(results)
    cold_amortization = _cold_amortization()
    analysis = _bootstrap_analysis(results)
    wire = _wire_results()
    locks = {
        **manifest_lock_summary(inputs),
        "artifact_format": ARTIFACT_FORMAT,
        "artifact_epoch": ARTIFACT_EPOCH,
        "a0_cold_artifact_bytes_per_endpoint": A0_COLD_ARTIFACT_BYTES,
        "a0_cold_artifact_locks": A0_COLD_ARTIFACT_LOCKS,
        "a0_cold_tokens": A0_COLD_TOKENS,
        "a0_adaptive_prompt_token_overhead_vs_cte": A0_ADAPTIVE_PROMPT_TOKEN_OVERHEAD_VS_CTE,
        "model_specs": MODEL_SPECS,
        "paper_prompt_source_locks": PAPER_PROMPT_SOURCE_LOCKS,
        "bootstrap": {
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed_hex": BOOTSTRAP_SEED_HEX,
            "new_harness_convention": True,
        },
    }
    stage_summary = _stage_summary()
    mock_prompt_locks = _prompt_lock_records(inputs, episodes)
    a1_plan_prompt_locks = _prompt_lock_records(inputs, a1_plan)
    a1_cost_prompt_locks = _prompt_lock_records(inputs, a1_cost)

    _write_jsonl(output / "mock_episode_manifest.jsonl", (episode.value for episode in episodes))
    _write_jsonl(output / "mock_episode_results.jsonl", (result.value for result in results))
    _write_jsonl(output / "mock_turn_observations.jsonl", observations)
    _write_jsonl(output / "mock_prompt_locks.jsonl", mock_prompt_locks)
    _write_jsonl(output / "a1_plan_episode_manifest.jsonl", (episode.value for episode in a1_plan))
    _write_jsonl(
        output / "a1_a0_cost_variant_episode_manifest.jsonl",
        (episode.value for episode in a1_cost),
    )
    _write_jsonl(output / "a1_plan_prompt_locks.jsonl", a1_plan_prompt_locks)
    _write_jsonl(output / "a1_a0_cost_variant_prompt_locks.jsonl", a1_cost_prompt_locks)
    atomic_write_json(output / "mock_run_manifest.json", run_manifest.value, pretty=True)
    atomic_write_json(output / "mock_aggregate.json", aggregate, pretty=True)
    atomic_write_json(output / "cold_amortization.json", cold_amortization, pretty=True)
    atomic_write_json(output / "analysis.json", analysis, pretty=True)
    atomic_write_json(output / "wire_control_results.json", wire, pretty=True)
    atomic_write_json(output / "locks.json", locks, pretty=True)
    atomic_write_json(output / "stage_and_cost_gates.json", stage_summary, pretty=True)
    atomic_write(output / "A1_READINESS_CHECKLIST.md", _checklist_text().encode("utf-8"))
    report = _report_text(
        aggregate=aggregate,
        run_manifest=run_manifest.value,
        a1_plan_count=len(a1_plan),
        a1_cost_count=len(a1_cost),
        analysis=analysis,
        wire=wire,
        verification=inputs.verification,
        checkpoint_digest=checkpoint_digest,
        adapter_invocations=adapter.invocations,
    )
    atomic_write(output / "DRY_RUN_REPORT.md", report.encode("utf-8"))

    inventory = _digest_inventory(output, inputs.verification)
    atomic_write_json(output / "FROZEN_DIGESTS.json", inventory, pretty=True)
    inventory_sha = sha256_file(output / "FROZEN_DIGESTS.json")
    atomic_write(
        output / "FROZEN_DIGESTS.sha256",
        f"{inventory_sha}  FROZEN_DIGESTS.json\n".encode("ascii"),
    )
    return {
        "format": ARTIFACT_FORMAT,
        "artifact_directory": str(output),
        "episodes": len(results),
        "arms": len(REPRESENTATION_ARMS),
        "ordered_pairs": len(ORDERED_PAIRS),
        "mock_calls": adapter.invocations,
        "provider_calls": 0,
        "paid_calls": 0,
        "actual_billed_usd": "0",
        "digest_inventory_sha256": inventory_sha,
        "claim_eligible": False,
    }
