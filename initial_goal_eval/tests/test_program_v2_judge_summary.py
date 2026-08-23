"""Adversarial closure tests for the Program /2 diagnostic judge summary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

import initial_goal_eval.program_v2_runtime_runner as runtime_runner
from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.program_v2_runtime_runner import (
    run_planned_program_v2_arm,
    validate_program_v2_runtime_run,
)
from initial_goal_eval.runtime_capture_bridge import (
    build_program_v2_judge_capture,
    build_program_v2_receiver_capture,
)
from initial_goal_eval.tests.test_program_v2_runtime_runner import (
    CompleteAdapter,
    _local_capture,
    _provider_capture,
)
from initial_goal_eval.tests import test_runtime_capture_bridge as bridge_fixtures
from initial_goal_eval.tests.test_runtime_capture_bridge import (
    _digest,
    _judge_billed_failure_capture,
    _judge_completed_capture,
    _judge_ready_plan,
    _judge_reply,
    _judge_verdict_text,
)
from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.captured_judge import (
    CapturedJudgeResponse,
    execute_captured_judge,
)
from urusilla_hybrid_runtime.tests.test_captured_judge import StaticJudgeAdapter


_JUDGE_COMPONENTS = {
    "task-judge",
    "parse-judge",
    "semantic-judge",
    "negative-judge",
}


class _SummaryAdapter(CompleteAdapter):
    """Produce independently captured receivers and judges for one scenario."""

    def __init__(
        self,
        *,
        judge_modes: dict[tuple[str, str], str] | None = None,
        typed_receivers: bool = True,
        unresolved_verdicts: bool = False,
    ) -> None:
        super().__init__()
        self.judge_modes = judge_modes or {}
        self.typed_receivers = typed_receivers
        self.unresolved_verdicts = unresolved_verdicts

    @staticmethod
    def _judge_execution(slot_request: dict, mode: str):
        request = bridge_fixtures.JudgeRuntimeCaptureBridgeTests._judge_request(
            slot_request
        )
        model = slot_request["expected_model_id"]
        settings = slot_request["expected_settings_sha256"]
        suffix = str(slot_request["slot_index"])

        if mode == "provider-failure":
            receipt = canonical_json(
                {
                    "id": f"judge-error-{suffix}",
                    "status": "provider_error",
                }
            )
            capture = replace(
                _judge_billed_failure_capture(request),
                model_id=model,
                settings_sha256=settings,
                provider_request_id=f"judge-request-{suffix}",
                provider_response_id=f"judge-error-{suffix}",
                raw_receipt_text=receipt,
                raw_receipt_sha256=sha256_text(receipt),
            )
            response = CapturedJudgeResponse(capture, None)
        else:
            if not request.probe_applicable:
                verdict = "not-applicable"
            elif mode == "malformed":
                verdict = None
            elif mode in {"pass", "fail", "unknown"}:
                verdict = mode
            else:
                raise AssertionError(f"unknown synthetic judge mode: {mode}")

            text = (
                "malformed non-JSON verdict"
                if verdict is None
                else _judge_verdict_text(request.judge_role, verdict)
            )
            reply = replace(_judge_reply(text), model_id=model)
            receipt = canonical_json(
                {
                    "id": f"judge-response-{suffix}",
                    "status": "completed",
                }
            )
            capture = replace(
                _judge_completed_capture(
                    request,
                    reply,
                    settings_sha256=settings,
                ),
                model_id=model,
                provider_request_id=f"judge-request-{suffix}",
                provider_response_id=f"judge-response-{suffix}",
                raw_receipt_text=receipt,
                raw_receipt_sha256=sha256_text(receipt),
            )
            response = CapturedJudgeResponse(capture, reply)

        return execute_captured_judge(
            request,
            StaticJudgeAdapter(response),
            expected_model_id=model,
            expected_settings_sha256=settings,
        )

    def execute_slot(self, request: dict) -> dict:
        self.calls.append(deepcopy(request))
        component = request["slot"]["component"]
        task_id = request["slot"]["task_id"]

        if component == "receiver" and self.typed_receivers:
            execution = (
                bridge_fixtures.JudgeRuntimeCaptureBridgeTests._receiver_execution(
                    request
                )
            )
            return build_program_v2_receiver_capture(request, execution)

        if component in _JUDGE_COMPONENTS:
            mode = self.judge_modes.get((task_id, component), "pass")
            if mode == "generic":
                return _provider_capture(request)
            if (
                self.unresolved_verdicts
                and bridge_fixtures.JudgeRuntimeCaptureBridgeTests._probe_applicable(
                    request,
                    component,
                )
            ):
                mode = "unknown"
            execution = self._judge_execution(request, mode)
            return build_program_v2_judge_capture(request, execution)

        if request["slot"]["source_kind"] == "external-response":
            return _provider_capture(request)
        return _local_capture(request)


class ProgramV2JudgeSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = _judge_ready_plan()
        self.session = self.plan["sessions"][0]
        self.tasks = [task["task_id"] for task in self.session["tasks"]]

    def _run(self, adapter, label: str) -> dict:
        artifact = run_planned_program_v2_arm(
            self.plan,
            session_id=self.session["session_id"],
            arm_id="raw-concise",
            execution_instance_sha256=_digest(f"judge-summary-{label}"),
            adapter=adapter,
        )
        self.assertIsNone(artifact["safely_completed"])
        for field in (
            "request_derivation_verified",
            "raw_usage_normalization_verified",
            "provider_authenticated",
            "operator_authenticated",
            "sandbox_verified",
            "independent_operator_verified",
            "claim_eligible",
            "goal_total_complete",
        ):
            self.assertFalse(artifact["authority"][field], field)
        return artifact

    def test_all_pass_closes_only_applicable_content_bound_judges(self) -> None:
        artifact = self._run(_SummaryAdapter(), "all-pass")
        results = artifact["judge_results"]
        summary = artifact["judge_summary"]

        self.assertEqual(len(results), 8)
        self.assertEqual(
            {result["judge_role"] for result in results},
            _JUDGE_COMPONENTS,
        )
        self.assertTrue(
            all(result["terminal_content_binding_verified"] for result in results)
        )
        disabled = [result for result in results if not result["probe_applicable"]]
        self.assertEqual(len(disabled), 1)
        self.assertEqual(disabled[0]["judge_role"], "negative-judge")
        self.assertEqual(disabled[0]["verdict_parse_status"], "valid")
        self.assertEqual(disabled[0]["verdict"], "not-applicable")

        self.assertEqual(summary["expected_judge_slots"], 8)
        self.assertEqual(summary["recorded_judge_slots"], 8)
        self.assertEqual(summary["typed_judge_slots"], 8)
        self.assertEqual(summary["content_bound_judge_slots"], 8)
        self.assertEqual(summary["applicable_judge_slots"], 7)
        self.assertEqual(summary["decisive_applicable_verdicts"], 7)
        self.assertEqual(summary["valid_not_applicable_verdicts"], 1)
        self.assertTrue(summary["judge_closure_complete"])
        self.assertIs(summary["all_applicable_judges_passed"], True)

    def test_any_valid_applicable_fail_makes_summary_false(self) -> None:
        target = (self.tasks[0], "semantic-judge")
        artifact = self._run(
            _SummaryAdapter(judge_modes={target: "fail"}),
            "one-fail",
        )

        result = next(
            item
            for item in artifact["judge_results"]
            if (item["task_id"], item["judge_role"]) == target
        )
        self.assertEqual(result["verdict_parse_status"], "valid")
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(artifact["judge_summary"]["judge_closure_complete"])
        self.assertIs(
            artifact["judge_summary"]["all_applicable_judges_passed"],
            False,
        )

    def test_indeterminate_judge_states_keep_summary_null(self) -> None:
        target = (self.tasks[0], "task-judge")
        cases = {
            "malformed": "invalid",
            "unknown": "valid",
            "provider-failure": "indeterminate",
            "generic": "untyped",
        }
        for mode, expected_parse_status in cases.items():
            with self.subTest(mode=mode):
                artifact = self._run(
                    _SummaryAdapter(judge_modes={target: mode}),
                    f"indeterminate-{mode}",
                )
                result = next(
                    item
                    for item in artifact["judge_results"]
                    if (item["task_id"], item["judge_role"]) == target
                )
                self.assertEqual(
                    result["verdict_parse_status"], expected_parse_status
                )
                if mode == "unknown":
                    self.assertEqual(result["verdict"], "unknown")
                else:
                    self.assertIsNone(result["verdict"])
                self.assertFalse(
                    artifact["judge_summary"]["judge_closure_complete"]
                )
                self.assertIsNone(
                    artifact["judge_summary"][
                        "all_applicable_judges_passed"
                    ]
                )

    def test_fully_generic_untyped_baseline_is_null(self) -> None:
        artifact = self._run(CompleteAdapter(), "fully-generic")

        self.assertTrue(
            all(
                result["verdict_parse_status"] == "untyped"
                and not result["typed_judge_execution_bound"]
                and not result["terminal_content_binding_verified"]
                for result in artifact["judge_results"]
            )
        )
        self.assertEqual(artifact["judge_summary"]["typed_judge_slots"], 0)
        self.assertEqual(
            artifact["judge_summary"]["content_bound_judge_slots"], 0
        )
        self.assertIsNone(
            artifact["judge_summary"]["all_applicable_judges_passed"]
        )

    def test_typed_unknown_judges_cannot_close_unbound_terminals(self) -> None:
        artifact = self._run(
            _SummaryAdapter(
                typed_receivers=False,
                unresolved_verdicts=True,
            ),
            "typed-unbound",
        )

        applicable = [
            result for result in artifact["judge_results"]
            if result["probe_applicable"]
        ]
        self.assertTrue(
            all(result["typed_judge_execution_bound"] for result in applicable)
        )
        self.assertTrue(
            all(result["verdict"] == "unknown" for result in applicable)
        )
        self.assertTrue(
            all(
                not result["terminal_content_binding_verified"]
                for result in artifact["judge_results"]
            )
        )
        self.assertFalse(artifact["judge_summary"]["judge_closure_complete"])
        self.assertIsNone(
            artifact["judge_summary"]["all_applicable_judges_passed"]
        )

    def test_resealed_judge_summary_tamper_is_rejected(self) -> None:
        artifact = self._run(_SummaryAdapter(), "tamper-source")
        tampered = deepcopy(artifact)
        tampered["judge_summary"]["all_applicable_judges_passed"] = False
        core = {
            key: value
            for key, value in tampered.items()
            if key not in {"schema_version", "run_sha256"}
        }
        tampered["run_sha256"] = sha256_ref(
            {
                "schema_version": (
                    runtime_runner.PROGRAM_V2_RUNTIME_RUN_DIGEST_SCHEMA
                ),
                **core,
            }
        )

        with self.assertRaisesRegex(
            VerificationError,
            "runtime run or digest differs",
        ):
            validate_program_v2_runtime_run(tampered)


if __name__ == "__main__":
    unittest.main()
