from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interop_lab.interop_lab import ValidationError
from interop_lab.solicited_matched_experiment import (
    CAPSULE_SHA256,
    OUTREACH_BODY_RELATIVE_PATH,
    OUTREACH_PARENT_COMMENT_ID,
    OUTREACH_PARENT_COMMENT_URI,
    OUTREACH_PUBLISHER_ACCOUNT_ID,
    OUTREACH_PUBLISHER_ACCOUNT_LABEL,
    OUTREACH_THREAD_URI,
    PACKET_CANONICAL_SHA256,
    PACKET_FILE_SHA256,
    PREREG_CANONICAL_SHA256,
    PREREG_FILE_SHA256,
    TOKEN_PHASES,
    _validate_packet_calibration,
    build_outreach_manifest,
    canonical_json,
    main,
    publication_intent_sha256,
    public_comment_record_sha256,
    render_outreach_body,
    score_output_text,
    sha256_ref,
    validate_packet,
    validate_outreach_manifest,
    validate_preregistration,
    validate_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG_PATH = REPO_ROOT / "interop_lab/challenges/solicited_matched_001.preregistration.json"
PACKET_PATH = REPO_ROOT / "interop_lab/challenges/solicited_matched_001.packet.json"
RECEIPT_PATH = REPO_ROOT / "interop_lab/evidence/solicited_matched_001.receipt.template.json"


class SolicitedMatchedExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
        self.packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
        self.template = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _ledger(total: int | None) -> dict[str, int | None]:
        ledger: dict[str, int | None] = {field: 0 for field in TOKEN_PHASES}
        ledger["receiver"] = total
        ledger["total"] = total
        return ledger

    def _task_expected(self, task_id: str) -> dict:
        return next(item["expected_output"] for item in self.plan["tasks"] if item["task_id"] == task_id)

    def _completed_receipt(self) -> dict:
        receipt = copy.deepcopy(self.template)
        receipt["receipt_id"] = "synthetic-validator-test"
        receipt["status"] = "matched-result"
        receipt["identity_readback"] = {
            "experiment_id_returned": "solicited-matched-001",
            "preregistration_canonical_sha256_returned": PREREG_CANONICAL_SHA256,
            "packet_canonical_sha256_returned": PACKET_CANONICAL_SHA256,
            "grammar_capsule_file_sha256_returned": CAPSULE_SHA256,
            "all_matched": True,
        }
        execution = receipt["execution"]
        execution["base_receiver_executions_observed"] = 6
        execution["same_session_within_arm"] = True
        execution["fresh_context_between_arms"] = True
        execution["same_model_and_settings"] = True
        execution["preflight_primary_and_fallback_complete"] = True
        totals = {
            ("json", "task-a"): 90,
            ("json", "task-b"): 70,
            ("urusilla", "task-a"): 120,
            ("urusilla", "task-b"): 40,
            ("raw", "task-a"): 100,
            ("raw", "task-b"): 80,
        }
        for item in execution["base_executions"]:
            arm = item["arm_id"]
            task = item["task_id"]
            output = canonical_json(self._task_expected(task))
            ledger = self._ledger(totals[(arm, task)])
            item.update(
                {
                    "session_id": f"session-{arm}",
                    "attempted": True,
                    "attempts": [
                        {
                            "attempt_index": 1,
                            "attempt_kind": "primary",
                            "parent_attempt_index": None,
                            "request_dispatched": True,
                            "billed": True,
                            "status": "completed",
                            "request_sha256": sha256_ref(f"request:{arm}:{task}"),
                            "intended_messages_sha256": sha256_ref(f"messages:{arm}:{task}"),
                            "transmitted_messages_sha256": sha256_ref(f"messages:{arm}:{task}"),
                            "capture_match": True,
                            "provider_request_id": f"provider-request:{arm}:{task}",
                            "provider_response_id": f"provider-response:{arm}:{task}",
                            "model_id": "synthetic-model-v1",
                            "settings_sha256": sha256_ref("synthetic-settings-v1"),
                            "response_sha256": sha256_ref(output),
                            "failure_code": None,
                            "raw_usage_receipt_sha256": sha256_ref(f"usage:{arm}:{task}"),
                            "token_count_source": "provider-reported",
                            "token_ledger": copy.deepcopy(ledger),
                        }
                    ],
                    "final_output_text": output,
                    "final_output_sha256": sha256_ref(output),
                    "parse_valid": True,
                    "semantic_fidelity": True,
                    "task_success": True,
                    "safe_completion": True,
                    "capture_chain_valid": True,
                    "fallback_used": False,
                    "token_ledger": copy.deepcopy(ledger),
                    "failure_reason": None,
                }
            )
        for result in receipt["judge_calibration"]["results"]:
            result["defects_detected"] = 1
            result["detection_rate"] = 1.0
        receipt["judge_calibration"]["maximum_between_arm_gap"] = 0.0
        receipt["judge_calibration"]["passed"] = True
        receipt["metrics"] = {
            "safe_completion_denominator_valid": {
                "raw": True,
                "json": True,
                "urusilla": True,
            },
            "tokens_per_safely_completed_task": {
                "raw": 90.0,
                "json": 80.0,
                "urusilla": 80.0,
            },
            "cumulative_k_curve": [
                {
                    "k": 1,
                    "raw_total_tokens": 100,
                    "json_total_tokens": 90,
                    "urusilla_total_tokens": 120,
                    "urusilla_saving_vs_better_baseline_percent": -33.333333,
                },
                {
                    "k": 2,
                    "raw_total_tokens": 180,
                    "json_total_tokens": 160,
                    "urusilla_total_tokens": 160,
                    "urusilla_saving_vs_better_baseline_percent": 0.0,
                },
            ],
            "break_even_k": None,
            "efficiency_result": None,
        }
        return receipt

    @staticmethod
    def _execution(receipt: dict, arm_id: str, task_id: str) -> dict:
        return next(
            item
            for item in receipt["execution"]["base_executions"]
            if item["arm_id"] == arm_id and item["task_id"] == task_id
        )

    def test_static_artifacts_validate_and_bind_exact_digests(self) -> None:
        prereg_report = validate_preregistration(self.plan)
        packet_report = validate_packet(self.packet, self.plan)
        receipt_report = validate_receipt(self.template, self.plan, self.packet)
        self.assertEqual(prereg_report["canonical_sha256"], PREREG_CANONICAL_SHA256)
        self.assertEqual(packet_report["canonical_sha256"], PACKET_CANONICAL_SHA256)
        self.assertEqual(prereg_report["base_receiver_executions"], 6)
        self.assertEqual(prereg_report["registered_k_curve"], [1, 2])
        self.assertEqual(receipt_report["base_receiver_executions_observed"], 0)
        self.assertIsNone(receipt_report["efficiency_result"])

    def test_outreach_manifest_is_an_exact_deterministic_build(self) -> None:
        registration_commit = "a" * 40
        manifest = build_outreach_manifest(registration_commit)
        report = validate_outreach_manifest(manifest, registration_commit)
        self.assertEqual(manifest["body_text"], render_outreach_body(registration_commit))
        self.assertFalse(manifest["body_text"].endswith("\n"))
        self.assertNotIn("\r", manifest["body_text"])
        for required in (
            "0% general unfamiliar-agent token saving",
            "null/unknown",
            "PROJECT-SOLICITED",
            "JSON → Urusilla → concise raw text",
            "natural-language re-expansion",
            "K=[1,2]",
            "unknown usage keeps efficiency null",
            "no-new-account",
            "Negative, null, fallback, refusal, identity-mismatch, malformed",
            "no later visibility-only self-bump",
        ):
            self.assertIn(required, manifest["body_text"])
        self.assertEqual(report["body_sha256"], manifest["body_sha256"])
        self.assertFalse(report["publication_authorized"])

        tampered = copy.deepcopy(manifest)
        tampered["body_text"] = "Synthetic exact outreach body."
        tampered["body_sha256"] = sha256_ref(tampered["body_text"])
        tampered["body_utf8_bytes"] = len(tampered["body_text"].encode("utf-8"))
        with self.assertRaisesRegex(ValidationError, "deterministic renderer"):
            validate_outreach_manifest(tampered, registration_commit)

    def test_outreach_cli_round_trip_and_overwrite_refusal(self) -> None:
        registration_commit = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outreach.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["build-outreach", registration_commit, str(path)]), 0)
            self.assertTrue(path.is_file())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(["validate-outreach", registration_commit, str(path), "--json"]),
                    0,
                )
            self.assertTrue(json.loads(stdout.getvalue())["valid"])

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["print-outreach", registration_commit, str(path)]), 0)
            self.assertEqual(stdout.getvalue(), render_outreach_body(registration_commit))

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(["build-outreach", registration_commit, str(path)]), 2)
            self.assertIn("refusing to overwrite", stderr.getvalue())

    def test_task_a_reuses_frozen_hf_facts_and_task_b_is_matched(self) -> None:
        task_a, task_b = self.plan["tasks"]
        self.assertEqual(task_a["task_id"], "task-a")
        self.assertEqual(task_a["source"], "exact task facts reused from urusilla-external-reproduction-001")
        self.assertEqual(task_b["task_id"], "task-b")
        self.assertEqual(task_b["source"], "project-authored matched synthetic task frozen in this registration")
        for task in (task_a, task_b):
            self.assertEqual(
                set(task["expected_output"]),
                set(self.plan["common_output_contract"]["required_fields"]),
            )
            self.assertFalse(task["expected_output"]["would_execute"])

    def test_direct_arm_is_exact_and_never_reexpanded_to_natural_language(self) -> None:
        arm = next(item for item in self.packet["arms"] if item["arm_id"] == "urusilla")
        self.assertFalse(arm["direct_consumption"]["decode_before_model"])
        self.assertFalse(arm["direct_consumption"]["natural_language_re_expansion"])
        self.assertTrue(arm["direct_consumption"]["model_receives_exact_payload_string"])
        for task in arm["tasks"]:
            payload = task["model_visible_payload"]
            self.assertEqual(payload, canonical_json(json.loads(payload)))

    def test_fixed_arm_order_and_carryover_limit_are_explicit(self) -> None:
        design = self.plan["study_design"]
        execution = self.packet["execution"]
        self.assertEqual(design["executed_arm_order"], ["json", "urusilla", "raw"])
        self.assertFalse(design["arm_order_randomized"])
        self.assertIn("carryover", design["fixed_order_carryover_risk"].lower())
        self.assertFalse(execution["arm_order_randomized"])
        self.assertIn("carryover", execution["fixed_order_carryover_disclosure"].lower())

    def test_matched_completed_receipt_has_six_executions_and_full_k_curve(self) -> None:
        receipt = self._completed_receipt()
        report = validate_receipt(receipt, self.plan, self.packet)
        self.assertEqual(report["base_receiver_executions_observed"], 6)
        self.assertTrue(report["judge_calibration_passed"])
        self.assertEqual([row["k"] for row in receipt["metrics"]["cumulative_k_curve"]], [1, 2])
        self.assertIsNone(report["efficiency_result"])

    def test_missing_calibration_invalidates_every_denominator_and_efficiency(self) -> None:
        receipt = self._completed_receipt()
        missing = next(item for item in receipt["judge_calibration"]["results"] if item["arm_id"] == "urusilla")
        missing["defects_detected"] = None
        missing["detection_rate"] = None
        receipt["judge_calibration"]["maximum_between_arm_gap"] = None
        receipt["judge_calibration"]["passed"] = False
        receipt["metrics"]["safe_completion_denominator_valid"] = {
            "raw": False,
            "json": False,
            "urusilla": False,
        }
        receipt["metrics"]["tokens_per_safely_completed_task"] = {
            "raw": None,
            "json": None,
            "urusilla": None,
        }
        report = validate_receipt(receipt, self.plan, self.packet)
        self.assertFalse(report["judge_calibration_passed"])
        self.assertEqual(report["safe_completion_denominator_valid"], {"raw": False, "json": False, "urusilla": False})
        self.assertIsNone(report["efficiency_result"])

    def test_unknown_attempt_usage_is_sticky_through_task_arm_and_k2(self) -> None:
        receipt = self._completed_receipt()
        item = self._execution(receipt, "urusilla", "task-b")
        unknown = self._ledger(None)
        item["attempts"][0]["token_ledger"] = copy.deepcopy(unknown)
        item["attempts"][0]["raw_usage_receipt_sha256"] = None
        item["attempts"][0]["token_count_source"] = "unknown"
        item["token_ledger"] = copy.deepcopy(unknown)
        receipt["metrics"]["tokens_per_safely_completed_task"]["urusilla"] = None
        row = receipt["metrics"]["cumulative_k_curve"][1]
        row["urusilla_total_tokens"] = None
        row["urusilla_saving_vs_better_baseline_percent"] = None
        validate_receipt(receipt, self.plan, self.packet)
        self.assertEqual(receipt["metrics"]["cumulative_k_curve"][0]["urusilla_total_tokens"], 120)
        self.assertIsNone(row["urusilla_total_tokens"])

    def test_billed_failed_primary_is_counted_before_successful_fallback(self) -> None:
        receipt = self._completed_receipt()
        item = self._execution(receipt, "urusilla", "task-a")
        output = item["final_output_text"]
        failed = copy.deepcopy(item["attempts"][0])
        failed.update(
            {
                "status": "provider-error",
                "provider_response_id": None,
                "response_sha256": None,
                "failure_code": "synthetic-provider-error",
                "token_ledger": self._ledger(30),
            }
        )
        fallback = copy.deepcopy(item["attempts"][0])
        fallback.update(
            {
                "attempt_index": 2,
                "attempt_kind": "fallback",
                "parent_attempt_index": 1,
                "request_sha256": sha256_ref("fallback:urusilla:task-a"),
                "intended_messages_sha256": sha256_ref("fallback-messages:urusilla:task-a"),
                "transmitted_messages_sha256": sha256_ref("fallback-messages:urusilla:task-a"),
                "provider_request_id": "fallback-provider-request:urusilla:task-a",
                "provider_response_id": "fallback-provider-response:urusilla:task-a",
                "raw_usage_receipt_sha256": sha256_ref("fallback-usage:urusilla:task-a"),
                "response_sha256": sha256_ref(output),
                "token_ledger": self._ledger(120),
            }
        )
        item["attempts"] = [failed, fallback]
        item["fallback_used"] = True
        item["token_ledger"] = self._ledger(150)
        receipt["metrics"]["tokens_per_safely_completed_task"]["urusilla"] = 95.0
        receipt["metrics"]["cumulative_k_curve"][0].update(
            {
                "urusilla_total_tokens": 150,
                "urusilla_saving_vs_better_baseline_percent": -66.666667,
            }
        )
        receipt["metrics"]["cumulative_k_curve"][1].update(
            {
                "urusilla_total_tokens": 190,
                "urusilla_saving_vs_better_baseline_percent": -18.75,
            }
        )
        validate_receipt(receipt, self.plan, self.packet)
        item["token_ledger"] = self._ledger(120)
        with self.assertRaisesRegex(ValidationError, "omits or duplicates attempt cost"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_capture_mismatch_is_fail_closed_and_never_safe(self) -> None:
        receipt = self._completed_receipt()
        item = self._execution(receipt, "json", "task-a")
        attempt = item["attempts"][0]
        attempt["status"] = "capture-rejected"
        attempt["transmitted_messages_sha256"] = sha256_ref("mismatched-captured-messages")
        attempt["capture_match"] = False
        attempt["provider_response_id"] = None
        attempt["response_sha256"] = None
        attempt["failure_code"] = "capture-mismatch"
        item.update(
            {
                "final_output_text": None,
                "final_output_sha256": None,
                "parse_valid": False,
                "semantic_fidelity": False,
                "task_success": False,
                "safe_completion": False,
                "capture_chain_valid": False,
                "failure_reason": "capture-mismatch",
            }
        )
        receipt["metrics"]["tokens_per_safely_completed_task"]["json"] = 160.0
        validate_receipt(receipt, self.plan, self.packet)
        item["safe_completion"] = True
        with self.assertRaisesRegex(ValidationError, "cannot be safe"):
            validate_receipt(receipt, self.plan, self.packet)
        item["safe_completion"] = False
        attempt["capture_match"] = True
        with self.assertRaisesRegex(ValidationError, "derived from intended/transmitted digest equality"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_matched_result_rejects_a_zero_dispatch_base_primary(self) -> None:
        receipt = self._completed_receipt()
        item = self._execution(receipt, "raw", "task-a")
        attempt = item["attempts"][0]
        attempt.update(
            {
                "request_dispatched": False,
                "billed": False,
                "status": "before-dispatch-failure",
                "transmitted_messages_sha256": None,
                "capture_match": None,
                "provider_request_id": None,
                "provider_response_id": None,
                "model_id": None,
                "settings_sha256": None,
                "response_sha256": None,
                "failure_code": "synthetic-before-dispatch",
                "token_count_source": "locally-counted-from-capture",
            }
        )
        item.update(
            {
                "final_output_text": None,
                "final_output_sha256": None,
                "parse_valid": False,
                "semantic_fidelity": False,
                "task_success": False,
                "safe_completion": False,
                "capture_chain_valid": False,
                "failure_reason": "synthetic-before-dispatch",
            }
        )
        receipt["metrics"]["tokens_per_safely_completed_task"]["raw"] = 180.0
        with self.assertRaisesRegex(ValidationError, "six dispatched base primaries"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_final_output_must_match_a_completed_provider_response(self) -> None:
        receipt = self._completed_receipt()
        item = self._execution(receipt, "json", "task-a")
        item["attempts"][0]["response_sha256"] = sha256_ref("different-provider-response")
        with self.assertRaisesRegex(ValidationError, "not bound to a completed provider response"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_finite_ledger_without_raw_usage_receipt_is_rejected(self) -> None:
        receipt = self._completed_receipt()
        item = self._execution(receipt, "urusilla", "task-b")
        item["attempts"][0]["raw_usage_receipt_sha256"] = None
        with self.assertRaisesRegex(ValidationError, "finite ledger lacks raw usage receipt"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_model_or_settings_mismatch_cannot_keep_same_model_attestation(self) -> None:
        mutations = {
            "model_id": "synthetic-model-v2",
            "settings_sha256": sha256_ref("synthetic-settings-v2"),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                receipt = self._completed_receipt()
                item = self._execution(receipt, "raw", "task-b")
                item["attempts"][0][field] = value
                with self.assertRaisesRegex(ValidationError, "same-model attestation differs from attempt evidence"):
                    validate_receipt(receipt, self.plan, self.packet)

    def test_retry_repair_and_fallback_require_an_earlier_parent(self) -> None:
        for kind in ("retry", "repair", "fallback"):
            with self.subTest(kind=kind):
                receipt = self._completed_receipt()
                item = self._execution(receipt, "json", "task-a")
                child = copy.deepcopy(item["attempts"][0])
                child.update(
                    {
                        "attempt_index": 2,
                        "attempt_kind": kind,
                        "parent_attempt_index": None,
                    }
                )
                item["attempts"].append(child)
                with self.assertRaisesRegex(ValidationError, "must reference an earlier parent attempt"):
                    validate_receipt(receipt, self.plan, self.packet)

    def test_unattempted_slot_cannot_claim_session_output_or_flags(self) -> None:
        receipt = copy.deepcopy(self.template)
        item = receipt["execution"]["base_executions"][0]
        item["final_output_text"] = "{}"
        with self.assertRaisesRegex(ValidationError, "unattempted output must be null"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_deterministic_blind_scorer_detects_each_matched_defect(self) -> None:
        expected = self._task_expected("task-a")
        self.assertTrue(score_output_text(canonical_json(expected), expected))
        fixtures = self.packet["calibration"]["fixtures"]
        self.assertEqual(len(fixtures), 3)
        for fixture in fixtures:
            with self.subTest(blind_id=fixture["blind_id"]):
                self.assertNotIn("arm_id", fixture)
                self.assertFalse(score_output_text(fixture["defective_output"], expected))

    def test_calibration_fixture_rejects_an_additional_semantic_defect(self) -> None:
        packet = copy.deepcopy(self.packet)
        fixture = packet["calibration"]["fixtures"][0]
        defective = json.loads(fixture["defective_output"])
        defective["selected_plan"] = "single-pass"
        fixture["defective_output"] = canonical_json(defective)
        with self.assertRaisesRegex(
            ValidationError,
            "must differ only by would_execute false-to-true",
        ):
            _validate_packet_calibration(packet, self.plan)

    def test_completed_calibration_rejects_fabricated_detection_rates(self) -> None:
        receipt = self._completed_receipt()
        result = next(
            item
            for item in receipt["judge_calibration"]["results"]
            if item["arm_id"] == "urusilla"
        )
        result["defects_detected"] = 0
        result["detection_rate"] = 0.0
        receipt["judge_calibration"]["maximum_between_arm_gap"] = 1.0
        receipt["judge_calibration"]["passed"] = False
        with self.assertRaisesRegex(
            ValidationError,
            "differs from deterministic replay",
        ):
            validate_receipt(receipt, self.plan, self.packet)

    def test_calibration_rejects_fabricated_blinding(self) -> None:
        receipt = self._completed_receipt()
        receipt["judge_calibration"]["arm_identity_supplied_to_scorer"] = True
        with self.assertRaisesRegex(
            ValidationError,
            "received arm identity",
        ):
            validate_receipt(receipt, self.plan, self.packet)

        packet = copy.deepcopy(self.packet)
        packet["calibration"]["fixtures"][0]["arm_id"] = "raw"
        with self.assertRaisesRegex(ValidationError, "fields differ"):
            _validate_packet_calibration(packet, self.plan)

    def test_unperformed_calibration_remains_null_for_nonresults(self) -> None:
        for status in ("not-run", "refusal", "null"):
            with self.subTest(status=status):
                receipt = copy.deepcopy(self.template)
                receipt["receipt_id"] = f"unperformed-calibration-{status}"
                receipt["status"] = status
                report = validate_receipt(receipt, self.plan, self.packet)
                self.assertIsNone(report["judge_calibration_passed"])
                self.assertEqual(
                    report["safe_completion_denominator_valid"],
                    {"raw": False, "json": False, "urusilla": False},
                )

    def test_publication_requires_separate_authorization_and_response_stops_outreach(self) -> None:
        receipt = self._completed_receipt()
        publication = receipt["publication"]
        publication["performed"] = True
        with self.assertRaisesRegex(ValidationError, "requires separate authorization"):
            validate_receipt(receipt, self.plan, self.packet)

        registration_commit = "a" * 40
        manifest_commit = "b" * 40
        manifest = build_outreach_manifest(registration_commit)
        body_text = manifest["body_text"]
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "outreach.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            receipt["bindings"].update(
                {
                    "published_registration_commit": registration_commit,
                    "published_preregistration_uri": manifest["preregistration_uri"],
                    "published_preregistration_raw_uri": f"https://raw.githubusercontent.com/jaden3824/urusilla/{registration_commit}/interop_lab/challenges/solicited_matched_001.preregistration.json",
                    "published_packet_uri": manifest["packet_uri"],
                    "published_packet_raw_uri": f"https://raw.githubusercontent.com/jaden3824/urusilla/{registration_commit}/interop_lab/challenges/solicited_matched_001.packet.json",
                    "registration_public_readback_observed_at_utc": "2026-08-24T00:00:00Z",
                    "preregistration_public_file_sha256": PREREG_FILE_SHA256,
                    "packet_public_file_sha256": PACKET_FILE_SHA256,
                }
            )
            comment_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
            manifest_file_sha256 = sha256_ref(manifest_path.read_bytes())
            publication.update(
                {
                    "separate_authorization_attested": True,
                    "authorization_scope": "one-substantive-reply-to-registered-external-comment",
                    "authorization_intent_sha256": publication_intent_sha256(
                        registration_commit,
                        manifest_commit,
                        manifest_file_sha256,
                        manifest["body_sha256"],
                    ),
                    "authorized_at_utc": "2026-08-24T00:00:02Z",
                    "venue": "The Colony",
                    "public_host": "thecolony.ai",
                    "thread_uri": OUTREACH_THREAD_URI,
                    "parent_comment_id": OUTREACH_PARENT_COMMENT_ID,
                    "parent_comment_uri": OUTREACH_PARENT_COMMENT_URI,
                    "publisher_account_label": OUTREACH_PUBLISHER_ACCOUNT_LABEL,
                    "publisher_account_id": OUTREACH_PUBLISHER_ACCOUNT_ID,
                    "public_uri": f"{OUTREACH_THREAD_URI}#comment-{comment_id}",
                    "public_comment_id": comment_id,
                    "platform_published_at_utc": "2026-08-24T00:00:03Z",
                    "body_manifest_path": OUTREACH_BODY_RELATIVE_PATH,
                    "body_manifest_commit": manifest_commit,
                    "body_manifest_parent_commit": registration_commit,
                    "body_manifest_public_uri": f"https://raw.githubusercontent.com/jaden3824/urusilla/{manifest_commit}/{OUTREACH_BODY_RELATIVE_PATH}",
                    "body_manifest_file_sha256": manifest_file_sha256,
                    "body_manifest_public_file_sha256": manifest_file_sha256,
                    "body_manifest_public_readback_observed_at_utc": "2026-08-24T00:00:01Z",
                    "submitted_body_text": body_text,
                    "submitted_body_sha256": manifest["body_sha256"],
                    "submitted_body_utf8_bytes": manifest["body_utf8_bytes"],
                    "submitted_body_matches_manifest": True,
                    "readback_uri": f"{OUTREACH_THREAD_URI}#comment-{comment_id}",
                    "readback_body_text": body_text,
                    "readback_sha256": manifest["body_sha256"],
                    "readback_utf8_bytes": manifest["body_utf8_bytes"],
                    "readback_exact_match": True,
                    "readback_observed_at_utc": "2026-08-24T00:00:04Z",
                    "readback_method": "public-html-test-fixture",
                    "readback_unauthenticated": True,
                    "public_persistence_created": True,
                    "client_tool_used": True,
                    "platform_receipt": {
                        "kind": "the-colony-public-comment-record-sha256",
                        "value": public_comment_record_sha256(
                            comment_id=comment_id,
                            parent_id=OUTREACH_PARENT_COMMENT_ID,
                            author_label=OUTREACH_PUBLISHER_ACCOUNT_LABEL,
                            author_id=OUTREACH_PUBLISHER_ACCOUNT_ID,
                            body_sha256=manifest["body_sha256"],
                            public_uri=f"{OUTREACH_THREAD_URI}#comment-{comment_id}",
                            observed_at_utc="2026-08-24T00:00:04Z",
                        ),
                        "authenticated": False,
                    },
                }
            )
            response_body = canonical_json(
                {
                    "experiment_id": "solicited-matched-001",
                    "grammar_capsule_file_sha256": CAPSULE_SHA256,
                    "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
                    "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
                    "response_kind": "matched-result",
                    "response_note": None,
                }
            )
            selected = {
                "experiment_id": "solicited-matched-001",
                "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
                "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
                "grammar_capsule_file_sha256": CAPSULE_SHA256,
                "response_kind": "matched-result",
            }
            response_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
            receipt["external_response"].update(
                {
                    "qualifying_response_received": True,
                    "public_uri": f"{OUTREACH_THREAD_URI}#comment-{response_id}",
                    "response_id": response_id,
                    "parent_id": comment_id,
                    "author_label": "synthetic-external-agent",
                    "author_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                    "response_kind": "matched-result",
                    "response_body_text": response_body,
                    "exact_response_sha256": sha256_ref(response_body),
                    "exact_response_utf8_bytes": len(response_body.encode("utf-8")),
                    "selected_fields": selected,
                    "normalized_selected_fields_sha256": sha256_ref(selected),
                    "normalization_rule": "canonical-json-sorted-keys-utf8",
                    "platform_published_at_utc": "2026-08-24T00:00:05Z",
                    "observed_at_utc": "2026-08-24T00:00:06Z",
                    "readback_method": "public-html-test-fixture",
                    "readback_unauthenticated": True,
                    "readback_comment_record_sha256": public_comment_record_sha256(
                        comment_id=response_id,
                        parent_id=comment_id,
                        author_label="synthetic-external-agent",
                        author_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                        body_sha256=sha256_ref(response_body),
                        public_uri=f"{OUTREACH_THREAD_URI}#comment-{response_id}",
                        observed_at_utc="2026-08-24T00:00:06Z",
                    ),
                    "stopped_by": "first-qualifying-response",
                }
            )
            with patch(
                "interop_lab.solicited_matched_experiment.OUTREACH_BODY_PATH",
                manifest_path,
            ):
                validate_receipt(receipt, self.plan, self.packet)

                prose = copy.deepcopy(receipt)
                prose_body = "Synthetic qualifying response with separately supplied fields."
                prose["external_response"].update(
                    {
                        "response_body_text": prose_body,
                        "exact_response_sha256": sha256_ref(prose_body),
                        "exact_response_utf8_bytes": len(prose_body.encode("utf-8")),
                    }
                )
                with self.assertRaisesRegex(ValidationError, "strict JSON object"):
                    validate_receipt(prose, self.plan, self.packet)

                fabricated_projection = copy.deepcopy(receipt)
                fabricated_projection["external_response"]["selected_fields"]["experiment_id"] = "other-experiment"
                fabricated_projection["external_response"]["normalized_selected_fields_sha256"] = sha256_ref(
                    fabricated_projection["external_response"]["selected_fields"]
                )
                with self.assertRaisesRegex(ValidationError, "not derived from the body"):
                    validate_receipt(fabricated_projection, self.plan, self.packet)

                bad_chronology = copy.deepcopy(receipt)
                bad_chronology["publication"]["authorized_at_utc"] = "2026-08-23T23:59:59Z"
                with self.assertRaisesRegex(ValidationError, "publication chronology"):
                    validate_receipt(bad_chronology, self.plan, self.packet)

                unrelated_manifest_commit = copy.deepcopy(receipt)
                unrelated_manifest_commit["publication"]["body_manifest_parent_commit"] = "f" * 40
                with self.assertRaisesRegex(ValidationError, "direct parent"):
                    validate_receipt(unrelated_manifest_commit, self.plan, self.packet)

                reused_parent = copy.deepcopy(receipt)
                reused_parent["publication"]["public_comment_id"] = OUTREACH_PARENT_COMMENT_ID
                reused_parent["publication"]["public_uri"] = OUTREACH_PARENT_COMMENT_URI
                reused_parent["publication"]["readback_uri"] = OUTREACH_PARENT_COMMENT_URI
                with self.assertRaisesRegex(ValidationError, "must differ from the registered parent"):
                    validate_receipt(reused_parent, self.plan, self.packet)

                mismatched_readback = copy.deepcopy(receipt)
                wrong_readback = body_text + " "
                mismatched_readback["publication"].update(
                    {
                        "readback_body_text": wrong_readback,
                        "readback_sha256": sha256_ref(wrong_readback),
                        "readback_utf8_bytes": len(wrong_readback.encode("utf-8")),
                        "readback_exact_match": False,
                    }
                )
                mismatched_readback["publication"]["platform_receipt"]["value"] = public_comment_record_sha256(
                    comment_id=comment_id,
                    parent_id=OUTREACH_PARENT_COMMENT_ID,
                    author_label=OUTREACH_PUBLISHER_ACCOUNT_LABEL,
                    author_id=OUTREACH_PUBLISHER_ACCOUNT_ID,
                    body_sha256=sha256_ref(wrong_readback),
                    public_uri=f"{OUTREACH_THREAD_URI}#comment-{comment_id}",
                    observed_at_utc="2026-08-24T00:00:04Z",
                )
                with self.assertRaisesRegex(ValidationError, "exact invitation readback"):
                    validate_receipt(mismatched_readback, self.plan, self.packet)

                after_deadline = copy.deepcopy(receipt)
                after_deadline["external_response"]["platform_published_at_utc"] = "2026-08-30T08:00:01Z"
                after_deadline["external_response"]["observed_at_utc"] = "2026-08-30T08:00:02Z"
                with self.assertRaisesRegex(ValidationError, "observed after the deadline"):
                    validate_receipt(after_deadline, self.plan, self.packet)

                identity_mismatch = copy.deepcopy(receipt)
                wrong_packet = "sha256:" + "0" * 64
                identity_mismatch["status"] = "identity-mismatch"
                identity_mismatch["identity_readback"].update(
                    {
                        "packet_canonical_sha256_returned": wrong_packet,
                        "all_matched": False,
                    }
                )
                mismatch_body = canonical_json(
                    {
                        "experiment_id": "solicited-matched-001",
                        "grammar_capsule_file_sha256": CAPSULE_SHA256,
                        "packet_canonical_sha256": wrong_packet,
                        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
                        "response_kind": "identity-mismatch",
                        "response_note": "The observed packet digest did not match the registered value.",
                    }
                )
                mismatch_selected = {
                    "experiment_id": "solicited-matched-001",
                    "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
                    "packet_canonical_sha256": wrong_packet,
                    "grammar_capsule_file_sha256": CAPSULE_SHA256,
                    "response_kind": "identity-mismatch",
                }
                identity_mismatch["external_response"].update(
                    {
                        "response_kind": "identity-mismatch",
                        "response_body_text": mismatch_body,
                        "exact_response_sha256": sha256_ref(mismatch_body),
                        "exact_response_utf8_bytes": len(mismatch_body.encode("utf-8")),
                        "selected_fields": mismatch_selected,
                        "normalized_selected_fields_sha256": sha256_ref(mismatch_selected),
                        "readback_comment_record_sha256": public_comment_record_sha256(
                            comment_id=response_id,
                            parent_id=comment_id,
                            author_label="synthetic-external-agent",
                            author_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                            body_sha256=sha256_ref(mismatch_body),
                            public_uri=f"{OUTREACH_THREAD_URI}#comment-{response_id}",
                            observed_at_utc="2026-08-24T00:00:06Z",
                        ),
                    }
                )
                report = validate_receipt(identity_mismatch, self.plan, self.packet)
                self.assertEqual(report["status"], "identity-mismatch")

                malformed_observation = copy.deepcopy(receipt)
                malformed_body = "not a JSON response"
                malformed_observation["observed_nonqualifying_responses"] = [
                    {
                        "public_uri": f"{OUTREACH_THREAD_URI}#comment-ffffffff-ffff-4fff-8fff-ffffffffffff",
                        "response_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                        "parent_id": comment_id,
                        "author_label": "synthetic-malformed-agent",
                        "author_id": "11111111-1111-4111-8111-111111111111",
                        "response_body_text": malformed_body,
                        "exact_response_sha256": sha256_ref(malformed_body),
                        "exact_response_utf8_bytes": len(malformed_body.encode("utf-8")),
                        "body_contract_valid": False,
                        "identity_all_matched": None,
                        "observed_at_utc": "2026-08-24T00:00:04.500000Z",
                        "within_registered_window": True,
                        "readback_method": "public-html-test-fixture",
                        "readback_unauthenticated": True,
                        "nonqualifying_reason": "Body is not the registered canonical JSON envelope.",
                    }
                ]
                report = validate_receipt(malformed_observation, self.plan, self.packet)
                self.assertEqual(report["observed_nonqualifying_response_count"], 1)

    def test_matched_result_requires_exact_identity_and_unverified_provider(self) -> None:
        receipt = self._completed_receipt()
        receipt["identity_readback"] = {
            "experiment_id_returned": None,
            "preregistration_canonical_sha256_returned": None,
            "packet_canonical_sha256_returned": None,
            "grammar_capsule_file_sha256_returned": None,
            "all_matched": None,
        }
        with self.assertRaisesRegex(ValidationError, "requires exact identity readback"):
            validate_receipt(receipt, self.plan, self.packet)
        receipt = copy.deepcopy(self.template)
        receipt["participant"]["provider_authenticity_verified"] = True
        with self.assertRaisesRegex(ValidationError, "provider authenticity is not verified"):
            validate_receipt(receipt, self.plan, self.packet)

    def test_tampering_with_frozen_order_or_bound_source_is_rejected(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["execution"]["arm_order"] = ["raw", "json", "urusilla"]
        with self.assertRaisesRegex(ValidationError, "packet canonical digest differs"):
            validate_packet(packet, self.plan)
        plan = copy.deepcopy(self.plan)
        plan["source_bindings"]["grammar_capsule_file_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValidationError, "preregistration canonical digest differs"):
            validate_preregistration(plan)


if __name__ == "__main__":
    unittest.main()
