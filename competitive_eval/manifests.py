"""Provider-neutral frozen input, run, episode, call, and response manifests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from .canonical import (
    canonical_bytes,
    canonical_json,
    sequence_sha256,
    sha256_bytes,
    strict_json_file,
    verify_file,
)
from .config import (
    A0_EMBEDDED_SNAPSHOT_SHA256,
    A0_PROMPT_SET_SHA256,
    A1_ITEM_SET_SHA256,
    DATA_SEEDS,
    FROZEN_FILE_DIGESTS,
    HARNESS_FORMAT,
    LOCAL_ONLY_ARTIFACTS,
    MODEL_SPECS,
    ORDERED_PAIRS,
    PACKAGE_ROOT,
    PAPER_PROMPT_SOURCE_LOCKS,
    PRIMARY_BASELINE,
    PROJECT_ROOT,
    REPRESENTATION_ARMS,
    STAGES,
)
from .errors import IntegrityError, ManifestError
from .representations import ARM_CONTRACTS, prompt_contract_digest, verify_cold_artifact_locks


EPISODE_FORMAT = "competitive-eval-episode-v1"
RUN_FORMAT = "competitive-eval-run-v1"
CALL_FORMAT = "competitive-eval-call-request-v1"
RESPONSE_FORMAT = "competitive-eval-call-response-v1"


@dataclass(frozen=True)
class FrozenInputs:
    hotpotqa: tuple[Any, ...]
    wikihop: tuple[Any, ...]
    snapshot: Mapping[str, Any]
    a1_selected: Mapping[str, tuple[Any, ...]]
    verification: Mapping[str, Any]

    @property
    def datasets(self) -> dict[str, tuple[Any, ...]]:
        return {"hotpotqa": self.hotpotqa, "wikihop": self.wikihop}


@dataclass(frozen=True)
class EpisodeManifest:
    value: Mapping[str, Any]

    @property
    def episode_id(self) -> str:
        return str(self.value["episode_id"])

    @property
    def arm(self) -> str:
        return str(self.value["arm"])

    def to_json(self) -> str:
        return canonical_json(self.value)


@dataclass(frozen=True)
class RunManifest:
    value: Mapping[str, Any]

    @property
    def run_id(self) -> str:
        return str(self.value["run_id"])

    def to_json(self) -> str:
        return canonical_json(self.value)


def verify_public_digest_inventory() -> Mapping[str, Any]:
    """Verify only files distributed in a clean public checkout.

    Dataset caches and derived prompt/episode products are intentionally not
    consulted.  Their pinned digests remain provenance references for an
    explicitly provisioned local run, not public-file dependencies.
    """

    inventory_path = PACKAGE_ROOT / "artifacts/FROZEN_DIGESTS.json"
    detached_path = PACKAGE_ROOT / "artifacts/FROZEN_DIGESTS.sha256"
    inventory_bytes = inventory_path.read_bytes()
    inventory_sha256 = sha256_bytes(inventory_bytes)
    expected_detached = f"{inventory_sha256}  FROZEN_DIGESTS.json\n".encode("ascii")
    if detached_path.read_bytes() != expected_detached:
        raise IntegrityError("detached public digest inventory checksum changed")
    inventory = json.loads(inventory_bytes.decode("utf-8"))
    if type(inventory) is not dict or inventory.get("format") != (
        "competitive-eval-public-digest-inventory-v2"
    ):
        raise IntegrityError("unknown public digest inventory format")
    files = inventory.get("files")
    if type(files) is not dict:
        raise IntegrityError("public digest inventory files must be an object")
    prohibited = set(files).intersection(LOCAL_ONLY_ARTIFACTS)
    if prohibited:
        raise IntegrityError(f"local-only artifacts entered public inventory: {sorted(prohibited)}")
    verified: dict[str, str] = {}
    for relative, record in sorted(files.items()):
        if type(relative) is not str or type(record) is not dict:
            raise IntegrityError("invalid public digest inventory record")
        path = (PACKAGE_ROOT / relative).resolve()
        try:
            path.relative_to(PACKAGE_ROOT.resolve())
        except ValueError as exc:
            raise IntegrityError(f"public inventory path escapes package: {relative}") from exc
        verify_file(path, str(record.get("sha256")), label=relative)
        if path.stat().st_size != record.get("bytes"):
            raise IntegrityError(f"public inventory byte count changed: {relative}")
        verified[relative] = str(record["sha256"])
    root_files = inventory.get("root_current_files")
    if type(root_files) is not dict:
        raise IntegrityError("public root-current digest inventory must be an object")
    for relative, digest in sorted(root_files.items()):
        verify_file(PROJECT_ROOT / relative, str(digest), label=relative)
    return {
        "format": "competitive-eval-public-verification-v1",
        "inventory_sha256": inventory_sha256,
        "public_package_files_verified": len(verified),
        "root_current_files_verified": len(root_files),
        "local_only_files_required": 0,
        "provider_calls": 0,
        "network_used": False,
    }


def verify_frozen_inputs() -> FrozenInputs:
    observed: dict[str, str] = {}
    for relative, expected in FROZEN_FILE_DIGESTS.items():
        path = PROJECT_ROOT / relative
        verify_file(path, expected, label=relative)
        observed[relative] = expected

    snapshot_path = PROJECT_ROOT / "work/competitive_public_task_preflight/preflight_snapshot.json"
    snapshot = strict_json_file(snapshot_path)
    if type(snapshot) is not dict:
        raise IntegrityError("A0 snapshot must be an object")
    embedded = snapshot.get("snapshot_sha256")
    if embedded != A0_EMBEDDED_SNAPSHOT_SHA256:
        raise IntegrityError("A0 embedded snapshot digest changed")
    without_digest = dict(snapshot)
    without_digest.pop("snapshot_sha256", None)
    calculated = sha256_bytes(canonical_bytes(without_digest))
    if calculated != embedded:
        raise IntegrityError("A0 embedded snapshot digest does not verify")
    if snapshot.get("prompt_set_sha256") != A0_PROMPT_SET_SHA256:
        raise IntegrityError("A0 prompt-set digest changed")
    if snapshot.get("model_calls") != 0 or snapshot.get("paid_calls") != 0:
        raise IntegrityError("A0 snapshot unexpectedly contains model or paid calls")
    if snapshot.get("a1_selection", {}).get("sha256") != A1_ITEM_SET_SHA256:
        raise IntegrityError("A1 selected-item digest changed")
    cold_artifact_locks = verify_cold_artifact_locks()

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import competitive_public_task_preflight as a0

    loaded: dict[str, tuple[Any, ...]] = {}
    for spec in a0.DATASETS:
        loaded[spec.key] = a0.load_dataset(
            spec, PROJECT_ROOT / "work/competitive_public_task_preflight" / spec.cache_name
        )
    selected = a0.select_a1_items(loaded)
    if a0.a1_item_set_sha256(selected) != A1_ITEM_SET_SHA256:
        raise IntegrityError("recomputed A1 item selection changed")

    # The byte-frozen WikiHop artifact contains 1,630 blocks. The root English
    # preflight report says 1,702; this harness records the discrepancy rather
    # than changing the source data or silently copying the report typo.
    wikihop_blocks = sum(len(item.contexts) for item in loaded["wikihop"])
    if wikihop_blocks != 1_630:
        raise IntegrityError(f"WikiHop block total changed: {wikihop_blocks}")

    verification = {
        "format": "competitive-eval-frozen-input-verification-v1",
        "verified_file_sha256": observed,
        "a0_embedded_snapshot_sha256": embedded,
        "a0_prompt_set_sha256": A0_PROMPT_SET_SHA256,
        "a1_item_set_sha256": A1_ITEM_SET_SHA256,
        "hotpotqa_records": len(loaded["hotpotqa"]),
        "wikihop_records": len(loaded["wikihop"]),
        "wikihop_context_blocks_observed": wikihop_blocks,
        "root_report_context_blocks_text": 1_702,
        "root_report_discrepancy_retained": True,
        "verified_cold_artifact_locks": cold_artifact_locks,
        "repository_commit": None,
        "repository_commit_blocker": "git HEAD is unavailable; file digests only",
    }
    return FrozenInputs(
        hotpotqa=loaded["hotpotqa"],
        wikihop=loaded["wikihop"],
        snapshot=snapshot,
        a1_selected={key: tuple(values) for key, values in selected.items()},
        verification=verification,
    )


def _split_for_item(item: Any, seed: int, mode: str) -> Any:
    import competitive_public_task_preflight as a0

    if mode == "forced":
        return a0.forced_split(item, seed)
    if mode == "alternating":
        return a0.alternating_split(item, seed)
    raise ManifestError(f"unknown split mode: {mode}")


def _item_split_digest(item: Any, split: Any) -> str:
    return sha256_bytes(
        canonical_bytes(
            {
                "item": item.key,
                "owner_a": list(split.owner_a),
                "owner_b": list(split.owner_b),
            }
        )
    )


def _common_prompt(item: Any, split: Any, agent: str, arm: str) -> tuple[str, str, str]:
    if agent not in {"A", "B"}:
        raise ManifestError(f"unknown agent: {agent}")
    peer = "B" if agent == "A" else "A"
    role = (
        f"You are evidence agent {agent} in a two-agent question-answering episode.\n"
        "The agents alternate. Use only the question, your private evidence, and later "
        "partner messages.\n"
        "Every factual statement must preserve source owner A or B. Do not expose "
        "private reasoning.\n"
        "Stop only when both agents have the same answer candidate and no evidence "
        "request remains.\n"
        f"Your partner is agent {peer}.\n"
        "Output contract:\n"
        + ARM_CONTRACTS[arm]
    )
    blocks: list[str] = []
    for local_position, source_position in enumerate(split.owner(agent), start=1):
        blocks.append(
            f"[OWNER:{agent}:BLOCK:{local_position}:SOURCE:{source_position}]\n"
            + item.contexts[source_position]
        )
    task = (
        "Question:\n"
        + item.question
        + f"\nPrivate evidence owned by {agent}:\n"
        + "\n\n".join(blocks)
    )
    return role + "\n\n" + task, task, role


def _prompt_status(arm: str) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if arm in {"paper_natural_language", "autoform"}:
        blockers.extend(
            [
                "exact upstream AutoForm YAML bytes are absent from A0",
                "common two-agent/eight-call protocol is a clean adaptation",
                "archival prose does not expose a fail-closed unresolved-request field",
            ]
        )
    if arm == "current_adaptive_surface":
        blockers.append("bridge mode only; model comprehension is unmeasured")
    if arm == "oracle_free_adaptive_selector":
        blockers.append("selector policy is a new harness lock, not an A0-frozen arm")
    return not blockers, blockers


def _episode_core(
    *,
    stage: str,
    item: Any,
    split_mode: str,
    split_seed: int,
    arm: str,
    pair: tuple[str, str],
    repeat_index: int,
    repeat_seed: int,
    mock_only: bool,
) -> dict[str, Any]:
    if arm not in REPRESENTATION_ARMS:
        raise ManifestError(f"unknown arm: {arm}")
    if pair not in ORDERED_PAIRS:
        raise ManifestError(f"unknown ordered pair: {pair}")
    split = _split_for_item(item, split_seed, split_mode)
    prompts: dict[str, Any] = {}
    for agent in ("A", "B"):
        prompt, task_slice, role_slice = _common_prompt(item, split, agent, arm)
        prompts[agent] = {
            "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
            "prompt_utf8_bytes": len(prompt.encode("utf-8")),
            "task_slice_sha256": sha256_bytes(task_slice.encode("utf-8")),
            "role_slice_sha256": sha256_bytes(role_slice.encode("utf-8")),
        }
    ready, arm_blockers = _prompt_status(arm)
    endpoint_blockers: list[str] = []
    if arm in {"current_adaptive_surface", "oracle_free_adaptive_selector"}:
        for code in pair:
            if not MODEL_SPECS[code]["tokenizer_exact_for_endpoint"]:
                endpoint_blockers.append(f"{code} tokenizer is an A0 planning proxy")
    core: dict[str, Any] = {
        "format": EPISODE_FORMAT,
        "stage": stage,
        "dataset": item.dataset,
        "source_index": item.source_index,
        "item_key": item.key,
        "split": {
            "mode": split_mode,
            "seed": split_seed,
            "digest": _item_split_digest(item, split),
            "owner_a": list(split.owner_a),
            "owner_b": list(split.owner_b),
        },
        "arm": arm,
        "arm_contract_sha256": prompt_contract_digest(arm),
        "ordered_pair": list(pair),
        "role_models": {"A": pair[0], "B": pair[1]},
        "initiator": "A",
        "repeat_index": repeat_index,
        "repeat_seed": repeat_seed,
        "protocol": {
            "speaking_order": ["A", "B"],
            "strict_alternation": True,
            "max_messages_per_agent": 4,
            "max_base_calls": 8,
            "early_stop": (
                "both agents have the same parseable answer candidate and no "
                "unresolved evidence request remains"
            ),
            "max_format_repairs": 1,
            "repair_may_add_task_evidence": False,
            "adaptive_fallback": "compact_terse_english",
            "failure_denominator": "intent_to_treat_keep_all_failures",
            "tools": False,
            "web": False,
        },
        "representation_boundary": {
            "receiver_boundary": "surface_prompt",
            "offline_context_replay": "persistent_verified_mock_fixture",
            "live_stateless_default": "replayed_each_call",
            "cold_profile_rule": (
                "charge once per endpoint only with independently verified persistent "
                "context; otherwise charge every surface-prompt replay"
            ),
            "decoded_json_bridge_is_transport_only": True,
        },
        "prompts": prompts,
        "source_locks": {
            "plan_sha256": FROZEN_FILE_DIGESTS["COMPETITIVE_REPRODUCTION_PLAN.md"],
            "a0_snapshot_sha256": A0_EMBEDDED_SNAPSHOT_SHA256,
            "a0_prompt_set_sha256": A0_PROMPT_SET_SHA256,
            "current_prompt_contract_sha256": prompt_contract_digest(arm),
            "current_adaptive_is_current_artifact_reconfirmation": arm
            in {"current_adaptive_surface", "oracle_free_adaptive_selector"},
        },
        "claim_eligible": ready and not endpoint_blockers and not mock_only,
        "claim_blockers": arm_blockers + endpoint_blockers + (["offline deterministic mock"] if mock_only else []),
        "mock_only": mock_only,
        "gold_answer_in_provider_request": False,
    }
    core["episode_id"] = sha256_bytes(canonical_bytes(core))
    return core


def build_episode_manifests(
    inputs: FrozenInputs,
    *,
    stage: str,
    arms: Sequence[str] | None = None,
    pairs: Sequence[tuple[str, str]] | None = None,
    mock_only: bool = True,
    items_per_dataset: int | None = None,
    repeats: int | None = None,
) -> tuple[EpisodeManifest, ...]:
    if stage not in STAGES:
        raise ManifestError(f"unknown stage: {stage}")
    gate = STAGES[stage]
    selected_arms = tuple(arms or gate.arms)
    selected_pairs = tuple(pairs or gate.pairs)
    selected_repeats = gate.repeats if repeats is None else repeats
    if stage == "A0" and selected_repeats == 0:
        selected_repeats = 1
    if selected_repeats < 1 or selected_repeats > len(DATA_SEEDS):
        raise ManifestError("repeat count must be 1..3")
    repeat_seeds = DATA_SEEDS[-selected_repeats:]

    if stage in {"A1_plan", "A1_a0_cost_variant"}:
        datasets = inputs.a1_selected
    else:
        datasets = inputs.datasets
    result: list[EpisodeManifest] = []
    for dataset in ("hotpotqa", "wikihop"):
        items = datasets[dataset]
        if items_per_dataset is not None:
            if items_per_dataset < 1:
                raise ManifestError("items_per_dataset must be positive")
            items = items[:items_per_dataset]
        split_mode = "forced" if dataset == "hotpotqa" else "alternating"
        for item in items:
            if split_mode == "forced" and not item.forced_eligible:
                # The frozen duplicate-evidence item is not in A1. For wider mock
                # matrices, use its alternating split instead of inventing support.
                item_split_mode = "alternating"
            else:
                item_split_mode = split_mode
            for repeat_index, seed in enumerate(repeat_seeds):
                for arm in selected_arms:
                    for pair in selected_pairs:
                        value = _episode_core(
                            stage=stage,
                            item=item,
                            split_mode=item_split_mode,
                            split_seed=seed,
                            arm=arm,
                            pair=pair,
                            repeat_index=repeat_index,
                            repeat_seed=seed,
                            mock_only=mock_only,
                        )
                        result.append(EpisodeManifest(value))
    ordered = sorted(result, key=lambda episode: episode.episode_id)
    if len({episode.episode_id for episode in ordered}) != len(ordered):
        raise IntegrityError("episode IDs are not unique")
    return tuple(ordered)


def episode_sequence_sha256(episodes: Sequence[EpisodeManifest]) -> str:
    return sequence_sha256(episode.to_json() for episode in episodes)


def build_run_manifest(
    episodes: Sequence[EpisodeManifest],
    *,
    stage: str,
    execution_mode: str = "offline_mock",
) -> RunManifest:
    if execution_mode != "offline_mock":
        raise ManifestError("this package only creates offline_mock run manifests")
    if not episodes:
        raise ManifestError("run must contain at least one episode")
    core: dict[str, Any] = {
        "format": RUN_FORMAT,
        "harness_format": HARNESS_FORMAT,
        "stage": stage,
        "execution_mode": execution_mode,
        "network_allowed": False,
        "provider_calls_allowed": False,
        "paid_calls_allowed": False,
        "approved_call_cap": 0,
        "approved_paid_call_cap": 0,
        "approved_usd_cap": 0,
        "actual_billed_usd_required": 0,
        "episode_count": len(episodes),
        "episode_sequence_sha256": episode_sequence_sha256(episodes),
        "arms": sorted({episode.value["arm"] for episode in episodes}),
        "ordered_pairs": sorted({tuple(episode.value["ordered_pair"]) for episode in episodes}),
        "primary_baseline": PRIMARY_BASELINE,
        "mock_uses_gold": True,
        "claim_eligible": False,
        "claim_blockers": [
            "deterministic mock uses gold answers",
            "no model or provider was called",
            "paper/AutoForm source locks are absent",
            "hosted endpoint tokenizers are planning proxies",
            "power audit is not frozen or complete",
            "repository has no immutable git revision",
        ],
    }
    core["run_id"] = sha256_bytes(canonical_bytes(core))
    return RunManifest(core)


def manifest_lock_summary(inputs: FrozenInputs) -> dict[str, Any]:
    return {
        "format": "competitive-eval-lock-summary-v1",
        "frozen_inputs": inputs.verification,
        "representation_arms": list(REPRESENTATION_ARMS),
        "ordered_pairs": [list(pair) for pair in ORDERED_PAIRS],
        "arm_contracts": {
            arm: {
                "sha256": prompt_contract_digest(arm),
                "a0_frozen": arm in {
                    "compact_terse_english",
                    "canonical_minified_json",
                    "current_adaptive_surface",
                },
                "current_artifact_reconfirmed": arm == "current_adaptive_surface",
                "mock_only_until_external_lock": arm in {
                    "paper_natural_language",
                    "autoform",
                },
            }
            for arm in REPRESENTATION_ARMS
        },
        "paper_prompt_source_locks": PAPER_PROMPT_SOURCE_LOCKS,
        "new_harness_conventions": [
            "bootstrap seed and SHA-256 counter PRNG",
            "inverse-ECDF percentile convention",
            "item-by-ordered-pair cluster with item-only sensitivity",
            "Holm family and centered-bootstrap p-value convention",
            "call-reserve values treated as absolute safety caps",
            "strict CTE multi-value delimiter",
            "QA bridge to quarantined x:competitive-eval-qa-v1",
        ],
    }
