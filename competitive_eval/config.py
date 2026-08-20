"""Frozen study constants and explicit new harness conventions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


HARNESS_FORMAT = "competitive-eval-harness-v1"
HARNESS_VERSION = "0.1.0-offline-dry-run"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent

# These products contain dataset-derived prompts, observations, answers, or
# episode records.  They are local-only and must never become prerequisites of
# the public clean-clone integrity check.
LOCAL_ONLY_ARTIFACTS = frozenset(
    {
        "artifacts/a1_plan_episode_manifest.jsonl",
        "artifacts/a1_plan_prompt_locks.jsonl",
        "artifacts/a1_a0_cost_variant_episode_manifest.jsonl",
        "artifacts/a1_a0_cost_variant_prompt_locks.jsonl",
        "artifacts/mock_episode_manifest.jsonl",
        "artifacts/mock_episode_results.jsonl",
        "artifacts/mock_prompt_locks.jsonl",
        "artifacts/mock_turn_observations.jsonl",
    }
)

DATA_SEEDS = (20240826, 20250424, 20260820)
MODEL_CODES = ("O", "G", "Q")
ORDERED_PAIRS = tuple((left, right) for left in MODEL_CODES for right in MODEL_CODES)
A1_ORDERED_PAIRS = (("O", "G"), ("G", "Q"), ("Q", "O"))

REPRESENTATION_ARMS = (
    "paper_natural_language",
    "compact_terse_english",
    "canonical_minified_json",
    "autoform",
    "current_adaptive_surface",
    "oracle_free_adaptive_selector",
)
PRIMARY_BASELINE = "compact_terse_english"
WIRE_CONTROLS = (
    "deterministic_cbor",
    "messagepack_sorted_map",
    "typed_protobuf",
    "project_wire_v02",
)

LEDGER_CATEGORIES = (
    "task_input",
    "system_role",
    "agent_input_history",
    "agent_output_visible",
    "final_answer",
    "format_induction",
    "encode_decode_model",
    "negotiation_profile",
    "repair_retry",
    "tool_request",
    "tool_result",
    "safety_filter",
    "hidden_reasoning_billed",
)
JUDGE_CATEGORY = "judge"

FROZEN_FILE_DIGESTS: Mapping[str, str] = {
    "COMPETITIVE_REPRODUCTION_PLAN.md": "4b9c2763b990e3c6c4c6c74d83ff5fad1e1df08da4264d4a81662084c2ab48fe",
    "PERFORMANCE_TARGETS.md": "0ce3b7a42c503bfd02449dc2e8a8ed8d55708ab522b5473f944b2ac9d2996d32",
    "COMPETITIVE_PUBLIC_TASK_PREFLIGHT_REPORT.md": "b0def313c7d14218f86337a3a6fb08282cec4c10ce123402e13d58ae7fe7450b",
    "competitive_public_task_preflight.py": "4cc393e2349f07f1da0ddb5ed4946b5810142783bb8f31da4e279263810f5ccb",
    "work/competitive_public_task_preflight/preflight_snapshot.json": "0a2d8a04e44a04c226f3cca1bb0773ed46fb3572c5ed1abc2ef5e0aaed0fffb5",
    "work/competitive_public_task_preflight/prompt_manifest.jsonl": "2013a95ca5b138719c3d19f65dcfa0ace88c5356b355ad69fb7733f4f8317ed5",
    "work/competitive_public_task_preflight/hotpotqa.jsonl": "eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284",
    "work/competitive_public_task_preflight/wikihop.jsonl": "724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39",
    "urusilla_generalization_surface_v06.py": "85ab4676698acb2a887e31c297ed938d09c898a39d645b710a71149064fce753",
    "urusilla_capsule_v0_1.json": "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
    "urusilla_adaptive_dialogue_profile.json": "a488e75c95c6948d24447a12fabd619f65612b4a698f0da85b3d1c719421ceac",
    "urusilla_strong_codec_baseline.proto": "43f2b236836750779edcc9f34890f468478036172052a8ca1989d7b5108f9e5d",
}

A0_EMBEDDED_SNAPSHOT_SHA256 = (
    "4642d1386640037edfbfcf17f8a94152847ec27217335c14100152238cc4b70b"
)
A0_PROMPT_SET_SHA256 = (
    "1b7b8d415812a358dbe92d1fcd158f69a57884f6bb735ec0855c0f624b26c7c9"
)
A1_ITEM_SET_SHA256 = (
    "9eee61ecaeee10a0b2826bd0eaeb541fd3e6da0c047ea7043213a9b7c4ea675d"
)
A0_ADAPTIVE_PROFILE_SHA256 = (
    "55d5c04fe2480c5ed405f1c075c654a898f3ed0153e618b762711870746301a2"
)
A0_ADAPTIVE_PROFILE_SNAPSHOT_SHA256 = (
    "7bdc275fd00fcc79465225990581cdb808e47aced278c573fe632ee70ff48497"
)
# Replaced by the current-artifact reconfirmation after the Urusilla candidate
# files are frozen.  It is deliberately separate from the historical A0 lock.
CURRENT_PROFILE_SHA256 = (
    "f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d"
)

A0_COLD_ARTIFACT_BYTES = 16_005
A0_COLD_TOKENS = {
    "cl100k_base": 10_170,
    "o200k_base": 9_661,
    "qwen2_5_7b_instruct": 10_348,
    "mistral_7b_instruct_v03": 11_750,
}
A0_ADAPTIVE_PROMPT_TOKEN_OVERHEAD_VS_CTE = {
    "cl100k_base": 82,
    "o200k_base": 85,
    "qwen2_5_7b_instruct": 99,
    "mistral_7b_instruct_v03": 102,
}
A0_COLD_ARTIFACT_LOCKS = {
    "symbolic_grammar": {
        "utf8_bytes": 411,
        "sha256": "fad7d0b4a11e25883bd6c6c48f038c01010887f38988cd9246bbd69da0ecda32",
    },
    "optimized_grammar": {
        "utf8_bytes": 437,
        "sha256": "cb67a76a1b9537b909c2349b4df095ef69f715724f188b11c1c41f3e62618c0d",
    },
    "optimized_profile": {
        "utf8_bytes": 1_358,
        "sha256": "f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d",
    },
    "structured_profile_base64": {
        "utf8_bytes": 1_872,
        "sha256": "cac7b9839c57b4cc5656981916984c10f7c075ab9823cb340ca350a3099a98d3",
    },
    "structured_codebook": {
        "utf8_bytes": 11_927,
        "sha256": "240986a14035049a16bbd3bb98b41bb8ba88978792b959bd3d4cc961a9703b8e",
    },
    "structured_bundle": {
        "utf8_bytes": 13_799,
        "sha256": "8f864d02104783cf9adbdc2b1eb407577e7a99b8b208392ee8a2df319c493372",
    },
}

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED_HEX = (
    "ffe02c2c72341f0656e34f9e7fe171106d013790329fdb01bb381456810f1c33"
)
NONINFERIORITY_MARGIN = -0.010
TOKEN_REDUCTION_GATE = 0.25
SMOKE_MAX_SUCCESS_LOSS = -0.030
HOLM_ALPHA = 0.05


@dataclass(frozen=True)
class StageGate:
    stage: str
    items: int
    arms: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    repeats: int
    base_call_cap: int
    planning_usd_high: float
    requires_fresh_approval: bool
    note: str


STAGES = {
    "A0": StageGate(
        "A0", 200, REPRESENTATION_ARMS, ORDERED_PAIRS, 0, 0, 0.0, False,
        "Dataset, manifest, parser, local token, wire, and mock replay only.",
    ),
    "A1_plan": StageGate(
        "A1_plan", 40,
        ("compact_terse_english", "autoform", "current_adaptive_surface"),
        A1_ORDERED_PAIRS, 1, 2_880, 40.0, True,
        "The reproduction plan's A1 trio; distinct from the frozen A0 cost trio.",
    ),
    "A1_a0_cost_variant": StageGate(
        "A1_a0_cost_variant", 40,
        ("compact_terse_english", "canonical_minified_json", "current_adaptive_surface"),
        A1_ORDERED_PAIRS, 1, 2_880, 40.0, True,
        "The A0 preflight cost snapshot; not a replacement for A1_plan.",
    ),
    "A2": StageGate(
        "A2", 200, REPRESENTATION_ARMS, A1_ORDERED_PAIRS, 1, 28_800, 200.0,
        True, "Full short-context items, six arms, three ordered pairs.",
    ),
    "A3": StageGate(
        "A3", 200, REPRESENTATION_ARMS, ORDERED_PAIRS, 3, 259_200, 1_800.0,
        True, "Full claim matrix before repairs.",
    ),
    "A4": StageGate(
        "A4", 100, REPRESENTATION_ARMS, ORDERED_PAIRS, 3, 129_600, 2_400.0,
        True, "NarrativeQA transfer stage, not implemented by the A0 artifact set.",
    ),
    "A5": StageGate(
        "A5", 2_000, REPRESENTATION_ARMS, ORDERED_PAIRS, 3, 2_592_000,
        15_000.0, True, "Conditional powered public-set extension; separate approval.",
    ),
}

A1_BASE_CALL_RESERVE = 576
A1_PAID_CALL_RESERVE = 384
A1_ABSOLUTE_CALL_CAP_CONVENTION = 3_456
A1_ABSOLUTE_PAID_CALL_CAP_CONVENTION = 2_304
A1_ESTIMATED_PAID_USD = 4.492993
A1_ESTIMATED_WITH_RESERVE_USD = 5.391592
A1_APPROVAL_USD_CEILING = 40.0

MODEL_SPECS = {
    "O": {
        "family": "openai-gpt",
        "logical_model_id": "gpt-5-mini-2025-08-07",
        "runtime": "provider_adapter_required",
        "tokenizer": "o200k_base",
        "tokenizer_exact_for_endpoint": False,
    },
    "G": {
        "family": "google-gemini",
        "logical_model_id": "gemini-3.7-flash",
        "runtime": "provider_adapter_required",
        "tokenizer": "max_four_planning_proxy",
        "tokenizer_exact_for_endpoint": False,
    },
    "Q": {
        "family": "qwen",
        "logical_model_id": (
            "Qwen/Qwen2.5-7B-Instruct@"
            "a09a35458c702b33eeacc393d103063234e8bc28"
        ),
        "runtime": "local_adapter_required",
        "tokenizer": "qwen2_5_7b_instruct",
        "tokenizer_exact_for_endpoint": True,
    },
}

PAPER_PROMPT_SOURCE_LOCKS = {
    "hotpotqa_natural": {
        "path": "agentverse/tasks/tasksolving/hotpot_qa/gpt-4-cot/config.yaml",
        "sha256": "be9a789971c198d5a10c540e3f9da6612425b3fcb1a573fe431a76ea4bb6748e",
        "available_in_a0": False,
    },
    "hotpotqa_autoform": {
        "path": "agentverse/tasks/tasksolving/hotpot_qa/gpt-4-cot-model/config.yaml",
        "sha256": "315ea42f9bde3213e71a7698dc996585f5793bc124d0b17d130ddd7de6428ba0",
        "available_in_a0": False,
    },
    "wikihop_natural": {
        "path": "agentverse/tasks/tasksolving/wiki_hop_qa/gpt-4-cot/config.yaml",
        "sha256": "46b4700b61be124edf25fdc777517d1387288655c0b08e35b05e1e2e861b8592",
        "available_in_a0": False,
    },
    "wikihop_autoform": {
        "path": "agentverse/tasks/tasksolving/wiki_hop_qa/gpt-4-cot-model/config.yaml",
        "sha256": "a8b48472264360161dd3bd06873d0b909c951ea8bdb64a0a910ae4c9499d0bce",
        "available_in_a0": False,
    },
}
