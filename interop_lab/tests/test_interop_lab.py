from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from interop_lab.interop_lab import (
    ValidationError,
    _write_new,
    build_sample,
    main,
    strict_json_loads,
    validate_record,
)


class PropagationRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = build_sample(
            chain_id="chain-fixed-test",
            created_at="2026-08-21T00:00:00Z",
        )

    def test_generated_two_hop_record_is_valid_and_preserves_zero_percent_boundary(self) -> None:
        report = validate_record(self.record)
        self.assertTrue(report["valid"])
        self.assertTrue(report["negative_evidence_accepted"])
        self.assertEqual(
            report["chain_summary"]["longest_acknowledged_propagation_depth"], 2
        )
        self.assertEqual(report["chain_summary"]["downstream_acknowledgements"], 1)
        self.assertEqual(report["chain_summary"]["negative_or_null_hops"], 2)
        self.assertEqual(
            report["aggregate_token_metrics"][
                "post_decode_api_input_saving_percent"
            ],
            0.0,
        )
        self.assertLess(
            report["aggregate_token_metrics"]["total_task_token_saving_percent"],
            0.0,
        )
        self.assertFalse(report["project_wide_claim_changed"])
        self.assertEqual(
            self.record["hops"][0]["adoption"]["authorization"][
                "authorization_basis"
            ],
            "standing-policy",
        )
        self.assertEqual(report["authorization_summary"]["standing_policy_adoptions"], 2)
        self.assertEqual(
            report["authorization_summary"][
                "standing_policy_retransmission_intents"
            ],
            1,
        )

    def test_duplicate_json_member_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate JSON member"):
            strict_json_loads('{"schema_version":"a","schema_version":"b"}')

    def test_public_content_must_match_its_digest(self) -> None:
        self.record["hops"][0]["transcript"][0]["public_content"] = "mismatch"
        with self.assertRaisesRegex(ValidationError, "does not match content_sha256"):
            validate_record(self.record)

    def test_signature_claim_requires_evidence_digest(self) -> None:
        self.record["protocol"]["capsule_signature_verified"] = True
        with self.assertRaisesRegex(ValidationError, "required when verified"):
            validate_record(self.record)

    def test_claimed_post_decode_saving_is_recomputed(self) -> None:
        self.record["hops"][0]["token_ledger"]["post_decode_api_input"][
            "saving_percent"
        ] = 50.0
        with self.assertRaisesRegex(ValidationError, "recomputed value"):
            validate_record(self.record)

    def test_token_category_sum_is_enforced(self) -> None:
        self.record["hops"][0]["token_ledger"]["candidate"][
            "task_total_tokens"
        ] += 1
        with self.assertRaisesRegex(ValidationError, "category sum"):
            validate_record(self.record)

    def test_adoption_requires_a_passed_comprehension_gate(self) -> None:
        gate = self.record["hops"][0]["comprehension_gate"]
        gate["negative_cases"]["passed"] = 1
        gate["passed"] = False
        gate["failures"] = ["one negative vector was accepted"]
        with self.assertRaisesRegex(ValidationError, "cannot adopt"):
            validate_record(self.record)

    def test_failed_gate_with_json_fallback_is_accepted_as_negative_evidence(self) -> None:
        hop = self.record["hops"][1]
        gate = hop["comprehension_gate"]
        gate["negative_cases"]["passed"] = 1
        gate["passed"] = False
        gate["failures"] = ["one negative vector was accepted"]
        hop["adoption"].update(
            {
                "decision": "fallback-only",
                "scope": "none",
                "reason": "The comprehension gate failed; structured JSON was retained.",
            }
        )
        hop["actual_use"]["mode"] = "structured-json"
        hop["transcript"][3]["mode"] = "structured-json"
        hop["transcript"][4]["mode"] = "structured-json"
        self.record["chain_summary"]["comprehension_passed_hops"] = 1
        self.record["chain_summary"]["adopted_hops"] = 1
        report = validate_record(self.record)
        self.assertTrue(report["valid"])
        self.assertIn("hop 2: comprehension gate did not pass", report["warnings"])
        self.assertIn("hop 2: receiver did not adopt Urusilla", report["warnings"])

    def test_child_hop_requires_matching_acknowledged_parent(self) -> None:
        self.record["hops"][0]["retransmission"]["downstream_receiver_id"] = (
            "origin-agent"
        )
        with self.assertRaisesRegex(
            ValidationError, "not linked|acknowledgement|absent from the transcript"
        ):
            validate_record(self.record)

    def test_acknowledgement_must_be_in_transcript(self) -> None:
        self.record["hops"][0]["transcript"][-1]["content_sha256"] = (
            "sha256:" + "f" * 64
        )
        with self.assertRaisesRegex(ValidationError, "absent from the transcript"):
            validate_record(self.record)

    def test_retransmission_intent_without_attempt_is_recordable(self) -> None:
        retransmission = self.record["hops"][1]["retransmission"]
        retransmission.update(
            {
                "intended": True,
                "attempted": False,
                "downstream_receiver_id": "origin-agent",
                "capsule_sha256": self.record["protocol"]["capsule_sha256"],
                "result": "not-attempted",
                "authorization": copy.deepcopy(
                    self.record["hops"][0]["retransmission"]["authorization"]
                ),
                "utility_evaluation": copy.deepcopy(
                    self.record["hops"][0]["retransmission"][
                        "utility_evaluation"
                    ]
                ),
                "revocation": copy.deepcopy(
                    self.record["hops"][0]["retransmission"]["revocation"]
                ),
            }
        )
        report = validate_record(self.record)
        self.assertTrue(report["valid"])
        self.assertEqual(report["chain_summary"]["retransmission_attempts"], 1)

    def test_failed_task_and_message_mismatch_are_valid_negative_evidence(self) -> None:
        hop = self.record["hops"][1]
        hop["actual_use"]["exactness"] = "mismatch"
        hop["actual_use"]["task_success"] = False
        hop["transcript"][4]["exactness"] = "mismatch"
        hop["transcript"][4]["task_result"] = "failure"
        self.record["chain_summary"]["successful_task_hops"] = 1
        report = validate_record(self.record)
        self.assertTrue(report["valid"])
        self.assertIn("hop 2: task failed", report["warnings"])
        self.assertIn("hop 2: message exactness is mismatch", report["warnings"])

    def test_actual_message_counts_are_reconciled_to_transcript(self) -> None:
        self.record["hops"][1]["actual_use"]["messages_sent"] = 2
        with self.assertRaisesRegex(ValidationError, "message counts differ"):
            validate_record(self.record)

    def test_fallback_counts_are_reconciled_to_transcript(self) -> None:
        self.record["hops"][1]["fallback_and_repair"]["fallback_count"] = 1
        self.record["hops"][1]["fallback_and_repair"]["fallback_mode"] = (
            "structured-json"
        )
        self.record["hops"][1]["fallback_and_repair"]["causes"] = [
            "synthetic mismatch"
        ]
        with self.assertRaisesRegex(ValidationError, "counts differ"):
            validate_record(self.record)

    def test_untrusted_code_execution_attestation_is_rejected(self) -> None:
        self.record["hops"][0]["safety"]["untrusted_code_executed"] = True
        with self.assertRaisesRegex(ValidationError, "must be false"):
            validate_record(self.record)

    def test_project_wide_or_sota_claim_is_rejected(self) -> None:
        for field in ("changes_project_wide_claim", "sota_claim", "external_adoption_claim"):
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record["claim_boundary"][field] = True
                with self.assertRaisesRegex(ValidationError, "must be false"):
                    validate_record(record)

    def test_adopted_session_cannot_have_no_authorization(self) -> None:
        authorization = self.record["hops"][0]["adoption"]["authorization"]
        authorization["authorization_basis"] = "none"
        authorization["authorization_evidence_sha256"] = None
        with self.assertRaisesRegex(ValidationError, "cannot be none"):
            validate_record(self.record)

    def test_interactive_approval_is_optional_but_valid_when_disclosed(self) -> None:
        authorization = self.record["hops"][0]["adoption"]["authorization"]
        authorization["authorization_basis"] = "interactive-approval"
        report = validate_record(self.record)
        self.assertTrue(report["valid"])

    def test_adoption_requires_mutual_utility_threshold(self) -> None:
        utility = self.record["hops"][0]["adoption"]["utility_evaluation"]
        utility["observed_value"] = -1.0
        utility["passed"] = False
        with self.assertRaisesRegex(ValidationError, "must pass"):
            validate_record(self.record)

    def test_persistence_spending_and_external_effect_authority_are_rejected(self) -> None:
        authorization_path = self.record["hops"][0]["adoption"]["authorization"]
        for field in (
            "state_persistence_authorized",
            "spending_authorized",
            "external_effects_authorized",
        ):
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record["hops"][0]["adoption"]["authorization"][field] = True
                with self.assertRaisesRegex(ValidationError, "must be false"):
                    validate_record(record)
        self.assertFalse(authorization_path["state_persistence_authorized"])

        self.record["hops"][0]["adoption"]["scope"] = "persistent"
        with self.assertRaisesRegex(ValidationError, "persistent state"):
            validate_record(self.record)

    def test_revocation_result_is_recordable(self) -> None:
        revocation = self.record["hops"][0]["adoption"]["revocation"]
        revocation.update(
            {
                "invoked": True,
                "result": "revoked",
                "evidence_sha256": "sha256:" + "e" * 64,
            }
        )
        report = validate_record(self.record)
        self.assertTrue(report["valid"])

    def test_not_measured_ledger_is_valid_and_visible_as_negative_or_null(self) -> None:
        ledger = self.record["hops"][1]["token_ledger"]
        ledger.update(
            {
                "status": "not-measured",
                "accounting_method": "not-measured",
                "baseline": None,
                "candidate": None,
                "post_decode_api_input": {
                    "status": "not-measured",
                    "baseline_tokens": None,
                    "candidate_tokens": None,
                    "saving_percent": None,
                },
                "total_task_token_saving_percent": None,
            }
        )
        report = validate_record(self.record)
        self.assertEqual(report["aggregate_token_metrics"]["status"], "not-measured")
        self.assertIn("hop 2: token ledger was not measured", report["warnings"])

    def test_init_cli_writes_once_and_validate_cli_reports_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "chain.json"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(["init", str(destination), "--chain-id", "chain-cli-test"]),
                    0,
                )
            self.assertTrue(destination.is_file())
            report_output = io.StringIO()
            with redirect_stdout(report_output):
                self.assertEqual(main(["validate", str(destination), "--json"]), 0)
            report = json.loads(report_output.getvalue())
            self.assertTrue(report["valid"])

            error_output = io.StringIO()
            with redirect_stderr(error_output):
                self.assertEqual(
                    main(["init", str(destination), "--chain-id", "chain-cli-test"]),
                    2,
                )
            self.assertIn("refusing to overwrite", error_output.getvalue())

    def test_direct_writer_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "existing.json"
            _write_new(destination, {"first": True})
            with self.assertRaisesRegex(ValidationError, "refusing to overwrite"):
                _write_new(destination, {"second": True})


if __name__ == "__main__":
    unittest.main()
