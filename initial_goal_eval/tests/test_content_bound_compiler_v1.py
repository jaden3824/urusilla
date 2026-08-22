"""Adversarial tests for the exact-byte finite-bound compiler."""

from __future__ import annotations

from copy import deepcopy
from importlib import metadata
import unittest
from unittest.mock import patch

from initial_goal_eval.content_bound_compiler_v1 import (
    BASELINE_SUCCESS_EVIDENCE_SCHEMA,
    BYTE_CONFORMANCE_RECEIVER_MODEL_ID,
    CAP_ENFORCEMENT_SOURCE,
    COMPILATION_MANIFEST_SCHEMA,
    FINAL_INPUT_BINDING_SCHEMA,
    TOKENIZER_SPEC_SCHEMA,
    ContentBoundCase,
    build_content_bound_feasibility_screen,
)
from initial_goal_eval.contract import canonical_json, sha256_ref
from initial_goal_eval.feasibility_kill_screen_v1 import PATHS, SESSION_LENGTHS
from initial_goal_eval.feasibility_kill_screen_v3 import FEASIBILITY_PLAN_SCHEMA
from initial_goal_eval.finite_bound_preflight_v1 import (
    KINDS,
    PATH_DAG_SCHEMA,
    TOKEN_SCOPE,
    TOTAL_CAP_SCHEMA,
    build_finite_bound_preflight_manifest,
)


def _json_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


def _digest(label: str) -> str:
    return sha256_ref({"content-bound-test": label})


def _prompt_ids(prefix: str) -> list[str]:
    return [f"prompt.{prefix}.{n:03d}" for n in SESSION_LENGTHS]


def _cap(maximum: int, *, source: str = CAP_ENFORCEMENT_SOURCE) -> bytes:
    return _json_bytes(
        {
            "schema_version": TOTAL_CAP_SCHEMA,
            "maximum_total_tokens": maximum,
            "token_scope": TOKEN_SCOPE,
            "enforcement_stage": "before-provider-call",
            "overflow_action": "do-not-call",
            "enforcement_source_utf8": source,
        }
    )


def _make_case(
    *,
    safe: bool = True,
    bad_cap_source: bool = False,
    opaque_tokenizer: bool = False,
    extra_prompt: bool = False,
    conditional_repair: bool = False,
    huggingface_tokenizer: bool = False,
) -> ContentBoundCase:
    action_ids = _prompt_ids("action")
    raw_ids = _prompt_ids("raw")
    json_ids = _prompt_ids("json")
    prompts: dict[str, bytes] = {
        "prompt.action.setup": b"setup",
        "prompt.action.comprehension": b"comprehend",
    }
    for n, artifact_id in zip(SESSION_LENGTHS, action_ids):
        prompts[artifact_id] = f"A{n:03d}".encode("ascii")
    for n, artifact_id in zip(SESSION_LENGTHS, raw_ids):
        prompts[artifact_id] = f"R{n:03d}".encode("ascii")
    for n, artifact_id in zip(SESSION_LENGTHS, json_ids):
        prompts[artifact_id] = f"J{n:03d}".encode("ascii")
    if extra_prompt:
        prompts["prompt.unreferenced"] = b"unreferenced"

    action_edges: dict[str, list[str]] = {
        "setup": ["comprehension"],
        "comprehension": ["primary"],
        "primary": [],
    }
    action_specs: dict[str, dict[str, object]] = {
        "setup": {
            "node_kind": "model-call",
            "phase": "setup",
            "occurrence": "once",
            "prompt_artifact_ids": ["prompt.action.setup"],
            "total_cap_artifact_id": "cap.action",
            "task_input_root": False,
        },
        "comprehension": {
            "node_kind": "model-call",
            "phase": "comprehension",
            "occurrence": "once",
            "prompt_artifact_ids": ["prompt.action.comprehension"],
            "total_cap_artifact_id": "cap.action",
            "task_input_root": False,
        },
        "primary": {
            "node_kind": "model-call",
            "phase": "primary",
            "occurrence": "per-task",
            "prompt_artifact_ids": action_ids,
            "total_cap_artifact_id": "cap.action",
            "task_input_root": True,
        },
    }
    if conditional_repair:
        action_edges["primary"] = ["done", "repair"]
        action_edges["done"] = []
        action_edges["repair"] = []
        action_specs["done"] = {
            "node_kind": "local-zero",
            "phase": "repair",
            "occurrence": "once",
            "prompt_artifact_ids": [],
            "total_cap_artifact_id": None,
            "task_input_root": False,
        }
        action_specs["repair"] = {
            "node_kind": "model-call",
            "phase": "repair",
            "occurrence": "per-task",
            "prompt_artifact_ids": action_ids,
            "total_cap_artifact_id": "cap.action",
            "task_input_root": False,
        }

    dag = {
        "schema_version": PATH_DAG_SCHEMA,
        "paths": {
            "action-state": {"entry": "setup", "edges": action_edges},
            "raw-concise": {"entry": "primary", "edges": {"primary": []}},
            "ordinary-json": {"entry": "primary", "edges": {"primary": []}},
        },
    }
    baseline_spec = lambda ids, cap: {
        "primary": {
            "node_kind": "model-call",
            "phase": "primary",
            "occurrence": "per-task",
            "prompt_artifact_ids": ids,
            "total_cap_artifact_id": cap,
            "task_input_root": True,
        }
    }
    tokenizer_id = "hf-wordlevel-test" if huggingface_tokenizer else "utf8-byte-test"
    receiver_model_id = (
        "declared-hf-receiver-model"
        if huggingface_tokenizer
        else BYTE_CONFORMANCE_RECEIVER_MODEL_ID
    )
    tokenizer_spec = _json_bytes(
        {
            "schema_version": TOKENIZER_SPEC_SCHEMA,
            "tokenizer_id": tokenizer_id,
            "engine": (
                "huggingface-tokenizers-json"
                if huggingface_tokenizer
                else "utf8-byte-units"
            ),
            "model_artifact_id": (
                "tokenizer.model" if huggingface_tokenizer else None
            ),
            "implementation_distribution": (
                "tokenizers" if huggingface_tokenizer else None
            ),
            "implementation_version": (
                "0.21.4" if huggingface_tokenizer else "builtin/1"
            ),
            "add_special_tokens": False,
        }
    )
    tokenizer_artifacts = {
        "tokenizer.spec": b"not a tokenizer" if opaque_tokenizer else tokenizer_spec
    }
    if huggingface_tokenizer:
        tokenizer_artifacts["tokenizer.model"] = _json_bytes(
            {
                "version": "1.0",
                "truncation": None,
                "padding": None,
                "added_tokens": [],
                "normalizer": None,
                "pre_tokenizer": {"type": "Whitespace"},
                "post_processor": None,
                "decoder": None,
                "model": {
                    "type": "WordLevel",
                    "vocab": {"[UNK]": 0},
                    "unk_token": "[UNK]",
                },
            }
        )
    artifacts = {
        "pretty-sources": {"domain.source": b"frozen-domain-source"},
        "canonical-transmitted-prompts": prompts,
        "tokenizer-artifacts": tokenizer_artifacts,
        "chat-template-artifacts": {
            "final.input.binding": _json_bytes(
                {
                    "schema_version": FINAL_INPUT_BINDING_SCHEMA,
                    "rendering_stage": "already-rendered-exact-model-input",
                    "provider_additional_template": "forbidden",
                    "model_input_media_type": "text/plain;charset=utf-8",
                    "canonical_prompt_artifact_ids": sorted(prompts),
                    "receiver_model_id": receiver_model_id,
                    "receiver_settings_sha256": _digest("receiver-settings"),
                    "tokenizer_id": tokenizer_id,
                    "tokenizer_spec_artifact_id": "tokenizer.spec",
                    "binding_scope": "declared-final-input-conformance-only",
                    "provider_authentication": "not-provided",
                }
            )
        },
        "path-dag-artifacts": {"dag.closed": _json_bytes(dag)},
        "source-enforced-total-cap-artifacts": {
            "cap.action": _cap(
                4096,
                source=("this-does-not-enforce-a-cap" if bad_cap_source else CAP_ENFORCEMENT_SOURCE),
            ),
            "cap.raw": _cap(40),
            "cap.json": _cap(30),
        },
    }
    task_ids = [f"task-{n:03d}" for n in SESSION_LENGTHS]
    manifest = {
        "schema_version": COMPILATION_MANIFEST_SCHEMA,
        "case_id": "case-a",
        "domain_id": "domain-a",
        "tokenizer_id": tokenizer_id,
        "receiver_model_id": receiver_model_id,
        "receiver_settings_sha256": _digest("receiver-settings"),
        "task_ids": task_ids,
        "tokenizer_spec_artifact_id": "tokenizer.spec",
        "final_input_binding_artifact_id": "final.input.binding",
        "path_dag_artifact_id": "dag.closed",
        "node_specs": {
            "action-state": action_specs,
            "raw-concise": baseline_spec(raw_ids, "cap.raw"),
            "ordinary-json": baseline_spec(json_ids, "cap.json"),
        },
    }

    inventory = build_finite_bound_preflight_manifest(artifacts=artifacts)
    bundle_hashes = {
        kind: inventory["artifact_bundles"][kind]["bundle_sha256"] for kind in KINDS
    }
    receipts: dict[str, bytes] = {}
    for baseline, ids in (
        ("raw-concise", raw_ids),
        ("ordinary-json", json_ids),
    ):
        receipts[baseline] = _json_bytes(
            {
                "schema_version": BASELINE_SUCCESS_EVIDENCE_SCHEMA,
                "case_id": "case-a",
                "baseline_path": baseline,
                "domain_id": "domain-a",
                "tokenizer_id": tokenizer_id,
                "artifact_bundle_sha256": bundle_hashes,
                "compilation_manifest_sha256": sha256_ref(_json_bytes(manifest)),
                "receiver_model_id": receiver_model_id,
                "receiver_settings_sha256": _digest("receiver-settings"),
                "scorer_sha256": _digest("scorer"),
                "tasks": [
                    {
                        "task_id": task_id,
                        "task_input_sha256": sha256_ref(prompts[prompt_id]),
                        "receiver_output_utf8": "ok" if safe else None,
                        "attempt_ledger_sha256": _digest(
                            f"{baseline}-attempt-{index}"
                        ),
                        "scorer_output": (
                            "safe-success" if safe else "not-safe-success"
                        ),
                        "safely_completed": safe,
                    }
                    for index, (task_id, prompt_id) in enumerate(zip(task_ids, ids))
                ],
            }
        )
    return ContentBoundCase(
        artifacts=artifacts,
        baseline_success_receipts=receipts,
        compilation_manifest=_json_bytes(manifest),
    )


class ContentBoundCompilerV1Tests(unittest.TestCase):
    def test_exact_bytes_compile_to_v3_vectors_without_authorizing_calls(self) -> None:
        result = build_content_bound_feasibility_screen([_make_case()])

        self.assertEqual(result["outcome"], "screened")
        self.assertTrue(result["numeric_screen_permitted"])
        self.assertEqual(result["feasibility_plan"]["schema_version"], FEASIBILITY_PLAN_SCHEMA)
        self.assertIn(1, result["eligible_session_lengths"])
        self.assertIsNone(result["selected_session_length"])
        self.assertFalse(result["receiver_ceiling_run_permitted"])
        self.assertFalse(result["provider_cap_authenticity_verified"])
        self.assertFalse(result["provider_prompt_delivery_verified"])
        self.assertTrue(result["conditional_arithmetic_only"])
        self.assertTrue(result["synthetic_tokenizer_conformance_only"])
        self.assertFalse(result["kill_decision_permitted"])
        self.assertFalse(result["claim_eligible"])
        self.assertEqual(result["provider_calls_performed"], 0)
        self.assertEqual(result["model_calls_performed"], 0)
        first = result["feasibility_result"]["rows"][0]["sessions"][0]
        self.assertEqual(first["candidate_lower_total_tokens"], 19)
        self.assertEqual(first["raw_upper_total_tokens"], 40)
        self.assertEqual(first["json_upper_total_tokens"], 30)
        self.assertEqual(
            [item["name"] for item in result["compiler_bundle"]["sources"]],
            [
                "content_bound_compiler_v1.py",
                "contract.py",
                "feasibility_kill_screen_v1.py",
                "feasibility_kill_screen_v3.py",
                "finite_bound_preflight_v1.py",
            ],
        )
        self.assertEqual(
            result["compiler_bundle_sha256"], sha256_ref(result["compiler_bundle"])
        )

    def test_conditional_repair_zero_is_lower_bound_not_false_absence(self) -> None:
        result = build_content_bound_feasibility_screen(
            [_make_case(conditional_repair=True)]
        )

        self.assertEqual(result["outcome"], "screened")
        repair = next(
            item
            for item in result["feasibility_plan"]["rows"][0]["paths"][
                "action-state"
            ]["phases"]
            if item["phase"] == "repair"
        )
        self.assertEqual(repair["bound_kind"], "derived-lower-bound")
        self.assertEqual(repair["tokens_by_n"], [0] * 128)

    def test_fake_tokenizer_cap_and_unreferenced_prompt_never_release(self) -> None:
        for case in (
            _make_case(opaque_tokenizer=True),
            _make_case(bad_cap_source=True),
            _make_case(extra_prompt=True),
        ):
            with self.subTest(case=case):
                result = build_content_bound_feasibility_screen([case])
                self.assertEqual(result["outcome"], "invalid")
                self.assertFalse(result["numeric_screen_permitted"])
                self.assertEqual(result["eligible_session_lengths"], [])
                self.assertIsNone(result["selected_session_length"])
                self.assertFalse(result["receiver_ceiling_run_permitted"])

    def test_receipt_reorder_and_legacy_receipt_are_rejected_after_rehash(self) -> None:
        reordered = _make_case()
        receipts = dict(reordered.baseline_success_receipts)
        raw = __import__("json").loads(receipts["raw-concise"].decode("utf-8"))
        raw["tasks"][0], raw["tasks"][1] = raw["tasks"][1], raw["tasks"][0]
        receipts["raw-concise"] = _json_bytes(raw)
        reordered = ContentBoundCase(
            artifacts=reordered.artifacts,
            baseline_success_receipts=receipts,
            compilation_manifest=reordered.compilation_manifest,
        )

        legacy = _make_case()
        legacy_receipts = dict(legacy.baseline_success_receipts)
        weak = __import__("json").loads(legacy_receipts["raw-concise"].decode("utf-8"))
        weak["schema_version"] = "urusilla-initial-goal-baseline-success-receipt/1"
        legacy_receipts["raw-concise"] = _json_bytes(weak)
        legacy = ContentBoundCase(
            artifacts=legacy.artifacts,
            baseline_success_receipts=legacy_receipts,
            compilation_manifest=legacy.compilation_manifest,
        )

        for case in (reordered, legacy):
            result = build_content_bound_feasibility_screen([case])
            self.assertEqual(result["outcome"], "invalid")
            self.assertFalse(result["numeric_screen_permitted"])

    def test_receipts_cannot_be_reused_after_program_manifest_remap(self) -> None:
        case = _make_case()
        manifest = __import__("json").loads(
            case.compilation_manifest.decode("utf-8")
        )
        raw_primary = manifest["node_specs"]["raw-concise"]["primary"]
        json_primary = manifest["node_specs"]["ordinary-json"]["primary"]
        raw_primary["total_cap_artifact_id"] = "cap.json"
        json_primary["total_cap_artifact_id"] = "cap.raw"
        remapped = ContentBoundCase(
            artifacts=case.artifacts,
            baseline_success_receipts=case.baseline_success_receipts,
            compilation_manifest=_json_bytes(manifest),
        )

        result = build_content_bound_feasibility_screen([remapped])

        self.assertEqual(result["outcome"], "invalid")
        self.assertFalse(result["numeric_screen_permitted"])
        self.assertIn("binding-mismatch", result["error"])

    def test_zero_baseline_success_remains_unbounded_and_selects_no_n(self) -> None:
        result = build_content_bound_feasibility_screen([_make_case(safe=False)])

        self.assertEqual(result["outcome"], "screened")
        self.assertTrue(result["numeric_screen_permitted"])
        self.assertEqual(result["eligible_session_lengths"], [])
        self.assertIsNone(result["selected_session_length"])
        first = result["feasibility_result"]["rows"][0]["sessions"][0]
        self.assertIsNone(first["comparison_bound_source"])
        self.assertIsNone(first["kill_left_scaled"])

    def test_atomic_duplicate_row_failure_exposes_no_partial_plan(self) -> None:
        case = _make_case()
        with patch(
            "initial_goal_eval.content_bound_compiler_v1._compile_case",
            side_effect=AssertionError("duplicate must reject before compilation"),
        ) as compiler:
            result = build_content_bound_feasibility_screen([case, case])

        self.assertEqual(result["outcome"], "invalid")
        compiler.assert_not_called()
        self.assertFalse(result["numeric_screen_permitted"])
        self.assertIsNone(result["feasibility_plan"])
        self.assertEqual(result["compiled_case_bindings"], [])
        self.assertFalse(result["claim_eligible"])

    def test_oversized_success_evidence_rejects_before_json_parse(self) -> None:
        case = _make_case()
        receipts = dict(case.baseline_success_receipts)
        receipts["raw-concise"] = b"x" * (4 * 1024 * 1024 + 1)
        oversized = ContentBoundCase(
            artifacts=case.artifacts,
            baseline_success_receipts=receipts,
            compilation_manifest=case.compilation_manifest,
        )

        result = build_content_bound_feasibility_screen([oversized])

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("bounded-nonempty-bytes-required", result["error"])
        self.assertFalse(result["numeric_screen_permitted"])

    def test_byte_engine_cannot_impersonate_a_real_receiver_model(self) -> None:
        case = _make_case()
        manifest = __import__("json").loads(case.compilation_manifest.decode("utf-8"))
        manifest["receiver_model_id"] = "real-receiver-model"
        manifest_raw = _json_bytes(manifest)
        artifacts = deepcopy(case.artifacts)
        binding = __import__("json").loads(
            artifacts["chat-template-artifacts"]["final.input.binding"].decode(
                "utf-8"
            )
        )
        binding["receiver_model_id"] = "real-receiver-model"
        artifacts["chat-template-artifacts"]["final.input.binding"] = _json_bytes(
            binding
        )
        inventory = build_finite_bound_preflight_manifest(artifacts=artifacts)
        bundle_hashes = {
            kind: inventory["artifact_bundles"][kind]["bundle_sha256"]
            for kind in KINDS
        }
        receipts = {}
        for baseline, raw in case.baseline_success_receipts.items():
            receipt = __import__("json").loads(raw.decode("utf-8"))
            receipt["receiver_model_id"] = "real-receiver-model"
            receipt["artifact_bundle_sha256"] = bundle_hashes
            receipt["compilation_manifest_sha256"] = sha256_ref(manifest_raw)
            receipts[baseline] = _json_bytes(receipt)
        forged = ContentBoundCase(
            artifacts=artifacts,
            baseline_success_receipts=receipts,
            compilation_manifest=manifest_raw,
        )

        result = build_content_bound_feasibility_screen([forged])

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("synthetic-conformance-only", result["error"])
        self.assertFalse(result["numeric_screen_permitted"])

    def test_local_huggingface_engine_binds_installed_distribution_bytes(self) -> None:
        try:
            version = metadata.version("tokenizers")
        except metadata.PackageNotFoundError:
            self.skipTest("optional tokenizers runtime is not installed")
        if version != "0.21.4":
            self.skipTest("optional tokenizers runtime does not match the lock")

        result = build_content_bound_feasibility_screen(
            [_make_case(huggingface_tokenizer=True)]
        )

        self.assertEqual(result["outcome"], "screened")
        self.assertFalse(result["synthetic_tokenizer_conformance_only"])
        self.assertEqual(
            result["compiled_case_bindings"][0]["tokenizer_engine"],
            "huggingface-tokenizers-json",
        )
        self.assertFalse(result["kill_decision_permitted"])

    def test_stochastic_tokenizer_configuration_is_rejected(self) -> None:
        try:
            version = metadata.version("tokenizers")
        except metadata.PackageNotFoundError:
            self.skipTest("optional tokenizers runtime is not installed")
        if version != "0.21.4":
            self.skipTest("optional tokenizers runtime does not match the lock")
        case = _make_case(huggingface_tokenizer=True)
        artifacts = deepcopy(case.artifacts)
        model = __import__("json").loads(
            artifacts["tokenizer-artifacts"]["tokenizer.model"].decode("utf-8")
        )
        model["model"]["dropout"] = 0.1
        artifacts["tokenizer-artifacts"]["tokenizer.model"] = _json_bytes(model)
        stochastic = ContentBoundCase(
            artifacts=artifacts,
            baseline_success_receipts=case.baseline_success_receipts,
            compilation_manifest=case.compilation_manifest,
        )

        result = build_content_bound_feasibility_screen([stochastic])

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("stochastic-dropout-forbidden", result["error"])
        self.assertFalse(result["numeric_screen_permitted"])

    def test_expanded_prompt_reference_budget_rejects_before_tokenizer_load(self) -> None:
        case = _make_case()
        manifest = __import__("json").loads(case.compilation_manifest.decode("utf-8"))
        action_ids = _prompt_ids("action")
        for index in range(65):
            manifest["node_specs"]["action-state"][f"repeat-{index:03d}"] = {
                "node_kind": "model-call",
                "phase": "repair",
                "occurrence": "per-task",
                "prompt_artifact_ids": action_ids,
                "total_cap_artifact_id": "cap.action",
                "task_input_root": False,
            }
        amplified = ContentBoundCase(
            artifacts=case.artifacts,
            baseline_success_receipts=case.baseline_success_receipts,
            compilation_manifest=_json_bytes(manifest),
        )
        with patch(
            "initial_goal_eval.content_bound_compiler_v1._load_token_counter",
            side_effect=AssertionError("reference budget must reject before tokenizer load"),
        ) as loader:
            result = build_content_bound_feasibility_screen([amplified])

        loader.assert_not_called()
        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("expanded-prompt-reference-budget-exceeded", result["error"])

    def test_repeated_prompt_ids_are_measured_once_per_case(self) -> None:
        calls: list[bytes] = []

        def count(raw: bytes) -> int:
            calls.append(raw)
            return len(raw)

        with patch(
            "initial_goal_eval.content_bound_compiler_v1._load_token_counter",
            return_value=(count, _digest("memoized-tokenizer"), "utf8-byte-units"),
        ):
            result = build_content_bound_feasibility_screen(
                [_make_case(conditional_repair=True)]
            )

        self.assertEqual(result["outcome"], "screened")
        self.assertEqual(len(calls), 386)


if __name__ == "__main__":
    unittest.main()
