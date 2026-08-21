from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from interop_lab.value_proof import (
    ARM_IDS,
    EXPECTED_OUTPUT,
    ValueProofError,
    build_plan,
    build_result_template,
    decode_projection,
    encode_projection,
    main,
    sha256_ref,
    validate_plan,
    validate_result,
)


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "interop_lab" / "evidence"
PLAN_PATH = EVIDENCE / "challenge_002.plan.json"
TEMPLATE_PATH = EVIDENCE / "challenge_002.result-template.json"
PLAN_CANONICAL_SHA256 = (
    "sha256:a78afde6d5a1c983201326fd2dcbc481f42bfe08d1e291c3f5b88c82dec915a0"
)
TEMPLATE_CANONICAL_SHA256 = (
    "sha256:91fcea9226b35f8e96eab4b649a377c7686697bdc349044299ab888a4b757cc2"
)


class ValueProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_plan()

    def _completed_result(self) -> dict:
        result = build_result_template(self.plan)
        result["result_status"] = "completed"
        result["environment"] = {
            "model": "synthetic-test-model",
            "model_family": "synthetic-test-family",
            "runtime": "offline-validator-test",
            "tokenizer": "synthetic-counts",
            "settings_sha256": "sha256:" + "1" * 64,
            "operator_id": "test-operator",
        }
        result["execution_attestation"] = {
            "same_model_and_settings": True,
            "fresh_context_per_arm": True,
            "no_cross_arm_state": True,
            "arm_order": list(ARM_IDS),
        }
        components = {
            "raw-concise": (160, 30, 0, 0, 5, 5),
            "ordinary-json": (140, 30, 0, 0, 5, 5),
            "urusilla-direct": (110, 25, 0, 0, 5, 10),
        }
        for observation in result["observations"]:
            observation["disposition"] = "completed"
            observation["model_call"] = {
                "attempted": True,
                "explicit_operator_opt_in": True,
                "opt_in_evidence_sha256": "sha256:" + "2" * 64,
            }
            observation["public_output"] = copy.deepcopy(EXPECTED_OUTPUT)
            observation["task_success"] = True
            values = components[observation["arm_id"]]
            total = sum(values)
            observation["token_ledger"] = {
                "input_tokens": values[0],
                "output_tokens": values[1],
                "repair_tokens": values[2],
                "tool_tokens": values[3],
                "hidden_tokens": values[4],
                "unclassified_tokens": values[5],
                "total_tokens": total,
                "hidden_accounting": "separately-reported",
                "provider_reported_total_tokens": total,
            }
        return result

    def test_frozen_plan_artifact_matches_builder_and_keeps_version(self) -> None:
        artifact = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(artifact, self.plan)
        report = validate_plan(artifact)
        self.assertTrue(report["valid"])
        self.assertEqual(report["plan_sha256"], PLAN_CANONICAL_SHA256)
        self.assertFalse(report["protocol_version_changed"])
        self.assertEqual(artifact["protocol"]["language_version"], "0.1.0")

    def test_direct_surface_reaches_model_without_natural_language_expansion(self) -> None:
        direct = next(arm for arm in self.plan["arms"] if arm["arm_id"] == "urusilla-direct")
        self.assertTrue(direct["carrier"].startswith("USX|"))
        self.assertFalse(direct["decode_before_model"])
        self.assertIsNone(direct["natural_language_expansion"])
        self.assertIn(direct["carrier"], direct["model_visible_text"])

    def test_pinned_development_token_counts_reproduce_when_assets_exist(self) -> None:
        from urusilla_general_dialogue_eval import EvaluationError, load_pinned_tokenizers

        try:
            tokenizers = load_pinned_tokenizers()
        except EvaluationError as exc:
            self.skipTest(f"pinned tokenizer assets unavailable: {exc}")
        arms = {arm["arm_id"]: arm["model_visible_text"] for arm in self.plan["arms"]}
        expected = self.plan["development_history"]["complete_model_visible_token_counts"]
        for tokenizer in tokenizers:
            with self.subTest(tokenizer=tokenizer.key):
                self.assertEqual(
                    tokenizer.count(arms["raw-concise"]),
                    expected["raw-concise"][tokenizer.key],
                )
                self.assertEqual(
                    tokenizer.count(arms["ordinary-json"]),
                    expected["ordinary-json"][tokenizer.key],
                )
                self.assertEqual(
                    tokenizer.count(arms["urusilla-direct"]),
                    expected["urusilla-direct-usx"][tokenizer.key],
                )

    def test_result_template_preserves_every_unknown_as_null(self) -> None:
        artifact = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(artifact, build_result_template(self.plan))
        self.assertEqual(sha256_ref(artifact), TEMPLATE_CANONICAL_SHA256)
        report = validate_result(artifact, self.plan)
        self.assertIsNone(report["candidate_value_gate_passed"])
        self.assertTrue(report["negative_or_null_evidence_preserved"])
        for observation in artifact["observations"]:
            ledger = observation["token_ledger"]
            for field in (
                "input_tokens",
                "output_tokens",
                "repair_tokens",
                "tool_tokens",
                "hidden_tokens",
                "unclassified_tokens",
                "total_tokens",
            ):
                self.assertIsNone(ledger[field])

    def test_exact_success_and_lower_reconciled_total_pass_candidate_gate(self) -> None:
        report = validate_result(self._completed_result(), self.plan)
        self.assertTrue(report["task_success_noninferiority"])
        self.assertTrue(report["total_token_reduction_gate"])
        self.assertTrue(report["candidate_value_gate_passed"])
        self.assertEqual(report["urusilla_saving_percent_vs_raw"], 25.0)
        self.assertAlmostEqual(report["urusilla_saving_percent_vs_json"], 16.666667)
        self.assertFalse(report["single_result_promotes_protocol_version"])

    def test_total_must_reconcile_exactly(self) -> None:
        result = self._completed_result()
        result["observations"][2]["token_ledger"]["total_tokens"] += 1
        with self.assertRaisesRegex(ValueProofError, "does not reconcile"):
            validate_result(result, self.plan)

    def test_projection_rejects_noncanonical_or_tampered_forms(self) -> None:
        direct = next(arm for arm in self.plan["arms"] if arm["arm_id"] == "urusilla-direct")
        self.assertEqual(encode_projection(decode_projection(direct["carrier"])), direct["carrier"])
        for invalid in (
            direct["carrier"].replace("cost=20", "cost=020"),
            direct["carrier"].replace("cost<=100", "cost<=99"),
            direct["carrier"] + "|extra=1",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueProofError):
                    decode_projection(invalid)

    def test_output_without_call_and_inconsistent_result_status_are_rejected(self) -> None:
        result = build_result_template(self.plan)
        result["observations"][0]["public_output"] = copy.deepcopy(EXPECTED_OUTPUT)
        with self.assertRaisesRegex(ValueProofError, "without a model call"):
            validate_result(result, self.plan)

        result = self._completed_result()
        result["result_status"] = "not-run"
        with self.assertRaisesRegex(ValueProofError, "not-run requires"):
            validate_result(result, self.plan)

    def test_unreported_hidden_usage_keeps_total_and_gate_null(self) -> None:
        result = self._completed_result()
        ledger = result["observations"][2]["token_ledger"]
        ledger["hidden_accounting"] = "not-reported"
        ledger["hidden_tokens"] = None
        ledger["total_tokens"] = None
        ledger["provider_reported_total_tokens"] = None
        report = validate_result(result, self.plan)
        self.assertIsNone(report["total_token_reduction_gate"])
        self.assertIsNone(report["candidate_value_gate_passed"])

    def test_reasoning_subset_is_not_double_counted(self) -> None:
        result = self._completed_result()
        for observation in result["observations"]:
            ledger = observation["token_ledger"]
            hidden = ledger["hidden_tokens"]
            ledger["hidden_accounting"] = "included-in-output"
            ledger["total_tokens"] -= hidden
            ledger["provider_reported_total_tokens"] = ledger["total_tokens"]
        report = validate_result(result, self.plan)
        self.assertTrue(report["candidate_value_gate_passed"])

        result = self._completed_result()
        ledger = result["observations"][0]["token_ledger"]
        ledger["hidden_accounting"] = "included-in-output"
        ledger["hidden_tokens"] = ledger["output_tokens"] + 1
        with self.assertRaisesRegex(ValueProofError, "subset of output_tokens"):
            validate_result(result, self.plan)

    def test_provider_total_closes_ledger_without_reasoning_breakdown(self) -> None:
        result = self._completed_result()
        for observation in result["observations"]:
            ledger = observation["token_ledger"]
            hidden = ledger["hidden_tokens"]
            ledger["hidden_accounting"] = "not-reported"
            ledger["hidden_tokens"] = None
            ledger["total_tokens"] -= hidden
            ledger["provider_reported_total_tokens"] = ledger["total_tokens"]
        report = validate_result(result, self.plan)
        self.assertTrue(report["candidate_value_gate_passed"])

    def test_failed_output_is_preserved_and_fails_gate(self) -> None:
        result = self._completed_result()
        observation = result["observations"][2]
        observation["public_output"]["selected_plan"] = "plan-a"
        observation["task_success"] = False
        observation["rubric_failures"] = [
            "selected_plan must be null because no unique plan is justified"
        ]
        report = validate_result(result, self.plan)
        self.assertFalse(report["candidate_value_gate_passed"])
        self.assertTrue(report["negative_or_null_evidence_preserved"])

    def test_model_call_requires_explicit_opt_in_evidence(self) -> None:
        result = self._completed_result()
        call = result["observations"][0]["model_call"]
        call["explicit_operator_opt_in"] = False
        call["opt_in_evidence_sha256"] = None
        with self.assertRaisesRegex(ValueProofError, "without explicit opt-in"):
            validate_result(result, self.plan)

    def test_any_prohibited_effect_is_rejected(self) -> None:
        for field in (
            "tools_used",
            "persistence_created",
            "spending_authority_created",
            "permission_expanded",
            "external_effects_performed",
        ):
            with self.subTest(field=field):
                result = self._completed_result()
                result["observations"][0]["safety"][field] = True
                with self.assertRaisesRegex(ValueProofError, "entirely false"):
                    validate_result(result, self.plan)

    def test_cli_validation_and_init_are_offline_and_refuse_overwrite(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["validate-plan", str(PLAN_PATH)]), 0)
        self.assertEqual(json.loads(output.getvalue())["provider_calls"], 0)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "result.json"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "init-result",
                            str(destination),
                            "--plan",
                            str(PLAN_PATH),
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                build_result_template(self.plan),
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "init-result",
                            str(destination),
                            "--plan",
                            str(PLAN_PATH),
                        ]
                    ),
                    2,
                )


if __name__ == "__main__":
    unittest.main()
