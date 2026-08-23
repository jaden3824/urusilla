"""Adversarial tests for the Plan /2 content-bound runtime seam."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

import initial_goal_eval.program_v2_runtime_runner as runtime_runner
from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.program_v2_runtime_runner import (
    build_program_v2_local_capture,
    build_program_v2_provider_capture,
    run_planned_program_v2_arm,
    validate_program_v2_runtime_run,
    validate_program_v2_slot_capture,
)
from initial_goal_eval.tests.test_plan_v2 import build_synthetic_plan_v2
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture


def _digest(label: str) -> str:
    return sha256_ref({"program-v2-runtime-runner-test": label})


def _local_usage(total_tokens: int = 0) -> dict[str, object]:
    return {
        "model_calls": 0,
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "reasoning_accounting": None,
        "total_tokens": total_tokens,
        "usage_complete": True,
    }


def _provider_usage(total_tokens: int = 5) -> dict[str, object]:
    return {
        "model_calls": 1,
        "input_tokens": total_tokens - 2,
        "output_tokens": 2,
        "reasoning_tokens": 0,
        "reasoning_accounting": "included-in-output",
        "total_tokens": total_tokens,
        "usage_complete": True,
    }


def _facts(request: dict, *, hybrid_mode: str = "raw") -> dict[str, str]:
    slot = request["slot"]
    component = slot["component"]
    facts: dict[str, str] = {}
    if slot["source_kind"] == "external-response":
        facts["terminal_status"] = "completed"
    if component == "preflight-router":
        facts.update(
            selected_mode=hybrid_mode,
            control_decision=(
                "attempt-action-state"
                if hybrid_mode == "action-state"
                else "skip-action-state"
            ),
        )
    elif component == "sender-compiler":
        facts["compiler_status"] = "ok"
    elif component == "compiler-control":
        facts.update(
            compiler_status=(
                "ok" if hybrid_mode == "action-state" else "not-attempted"
            ),
            control_decision=(
                "attempt-action-state"
                if hybrid_mode == "action-state"
                else "skip-action-state"
            ),
        )
    elif component == "fidelity-verifier":
        facts["fidelity_verdict"] = "valid"
    elif component == "final-router":
        facts["selected_mode"] = hybrid_mode
    elif component == "output-validator":
        facts["output_verdict"] = "valid"
    return facts


def _local_capture(request: dict, *, hybrid_mode: str = "raw") -> dict:
    component = request["slot"]["component"]
    return build_program_v2_local_capture(
        request,
        input_preimage={
            "component": component,
            "slot_id": request["slot"]["slot_id"],
            "stage": "input",
        },
        output_preimage={
            "component": component,
            "slot_id": request["slot"]["slot_id"],
            "stage": "output",
        },
        usage=_local_usage(),
        facts=_facts(request, hybrid_mode=hybrid_mode),
    )


def _provider_capture(
    request: dict,
    *,
    hybrid_mode: str = "raw",
    provider_request_id: str | None = None,
    provider_response_id: str | None = None,
    raw_receipt_utf8: str | None = None,
) -> dict:
    index = request["slot_index"]
    component = request["slot"]["component"]
    return build_program_v2_provider_capture(
        request,
        request_preimage={
            "component": component,
            "slot_id": request["slot"]["slot_id"],
            "task_id": request["slot"]["task_id"],
        },
        response_preimage={
            "component": component,
            "result": f"completed-{index}",
            "slot_id": request["slot"]["slot_id"],
        },
        terminal_status="completed",
        provider_request_id=(
            provider_request_id or f"provider-request-{index}"
        ),
        provider_response_id=(
            provider_response_id or f"provider-response-{index}"
        ),
        raw_receipt_utf8=(
            raw_receipt_utf8 or f"raw-receipt-for-slot-{index}"
        ),
        observed_model_id=request["expected_model_id"],
        observed_settings_sha256=request["expected_settings_sha256"],
        observed_effects={
            "external_effects_performed": False,
            "permission_expanded": False,
            "persistence_created": False,
            "spending_authority_created": False,
            "tools_used": False,
        },
        usage=_provider_usage(),
        facts=_facts(request, hybrid_mode=hybrid_mode),
    )


class CompleteAdapter:
    def __init__(self, *, hybrid_mode: str = "raw") -> None:
        self.hybrid_mode = hybrid_mode
        self.calls: list[dict] = []

    def execute_slot(self, request: dict) -> dict:
        self.calls.append(deepcopy(request))
        if request["slot"]["source_kind"] == "external-response":
            return _provider_capture(request, hybrid_mode=self.hybrid_mode)
        return _local_capture(request, hybrid_mode=self.hybrid_mode)


class ProgramV2RuntimeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_synthetic_plan_v2()
        self.session = self.plan["sessions"][0]
        self.execution_instance = _digest(self._testMethodName)

    def _reset_plan(self) -> None:
        self.plan = build_synthetic_plan_v2()
        self.session = self.plan["sessions"][0]

    def _run(self, adapter, *, arm_id: str = "raw-concise") -> dict:
        return run_planned_program_v2_arm(
            self.plan,
            session_id=self.session["session_id"],
            arm_id=arm_id,
            execution_instance_sha256=self.execution_instance,
            adapter=adapter,
        )

    def test_baseline_happy_path_binds_plan_program_and_exact_total(self) -> None:
        adapter = CompleteAdapter()
        artifact = self._run(adapter)
        program = self.session["arm_execution_programs"]["raw-concise"][
            "program"
        ]
        external_count = sum(
            slot["source_kind"] == "external-response"
            for slot in program["slots"]
        )

        self.assertEqual(validate_program_v2_runtime_run(artifact), artifact)
        self.assertEqual(len(adapter.calls), len(program["slots"]))
        self.assertEqual(
            [item["slot"]["slot_id"] for item in adapter.calls],
            [slot["slot_id"] for slot in program["slots"]],
        )
        self.assertTrue(artifact["content_usage_complete"])
        self.assertEqual(
            artifact["content_bound_total_tokens"], external_count * 5
        )
        self.assertTrue(artifact["four_judge_slots_recorded"])
        self.assertIsNone(artifact["safely_completed"])
        self.assertEqual(
            artifact["frozen_plan_sha256"], sha256_ref(self.plan)
        )
        self.assertTrue(artifact["authority"]["plan_reference_content_verified"])
        self.assertTrue(
            artifact["authority"]["capture_internal_binding_verified"]
        )
        self.assertFalse(artifact["authority"]["request_derivation_verified"])
        self.assertFalse(
            artifact["authority"]["raw_usage_normalization_verified"]
        )
        self.assertFalse(artifact["authority"]["provider_authenticated"])
        self.assertFalse(artifact["authority"]["claim_eligible"])

    def test_plan_v1_rejects_before_adapter_callback(self) -> None:
        plan_v1, _ = build_synthetic_fixture()
        adapter = CompleteAdapter()
        session = plan_v1["sessions"][0]

        with self.assertRaisesRegex(VerificationError, "exact Plan /2"):
            run_planned_program_v2_arm(
                plan_v1,
                session_id=session["session_id"],
                arm_id="raw-concise",
                execution_instance_sha256=self.execution_instance,
                adapter=adapter,
            )
        self.assertEqual(adapter.calls, [])

    def test_cross_wired_and_mutated_captures_fail_at_the_adapter_boundary(self) -> None:
        class CrossWiredAdapter(CompleteAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.first_external: dict | None = None

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                if self.first_external is None:
                    self.first_external = _provider_capture(request)
                    return deepcopy(self.first_external)
                return deepcopy(self.first_external)

        with self.subTest(attack="cross-wire"):
            adapter = CrossWiredAdapter()
            with self.assertRaisesRegex(
                VerificationError, "replayed under another request|cross-wired"
            ):
                self._run(adapter)
            self.assertGreaterEqual(len(adapter.calls), 3)

        class MutatedCaptureAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                capture = _provider_capture(request)
                capture["provider_record"]["response"]["result"] = "tampered"
                return capture

        with self.subTest(attack="post-build-mutation"):
            self._reset_plan()
            adapter = MutatedCaptureAdapter()
            with self.assertRaisesRegex(
                VerificationError, "response preimage digest differs"
            ):
                self._run(adapter)
            self.assertEqual(
                [item["slot"]["component"] for item in adapter.calls],
                ["setup", "receiver"],
            )

    def test_builder_validation_error_inside_adapter_is_not_downgraded(self) -> None:
        class WrongModelBuilderAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                return build_program_v2_provider_capture(
                    request,
                    request_preimage={"request": "exact"},
                    response_preimage={"response": "exact"},
                    terminal_status="completed",
                    provider_request_id="wrong-model-request",
                    provider_response_id="wrong-model-response",
                    raw_receipt_utf8="wrong-model-raw-receipt",
                    observed_model_id="wrong-model",
                    observed_settings_sha256=request[
                        "expected_settings_sha256"
                    ],
                    observed_effects={
                        "external_effects_performed": False,
                        "permission_expanded": False,
                        "persistence_created": False,
                        "spending_authority_created": False,
                        "tools_used": False,
                    },
                    usage=_provider_usage(),
                    facts=_facts(request),
                )

        adapter = WrongModelBuilderAdapter()
        with self.assertRaisesRegex(
            VerificationError,
            "provider model differs from the frozen session",
        ):
            self._run(adapter)
        self.assertEqual(len(adapter.calls), 2)

    def test_retry_and_attempt_aggregates_are_rejected(self) -> None:
        class AttemptMutationAdapter(CompleteAdapter):
            def __init__(self, attempt_count: int, retry_count: int) -> None:
                super().__init__()
                self.attempt_count = attempt_count
                self.retry_count = retry_count

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                capture = _provider_capture(request)
                capture["provider_record"]["attempt_count"] = self.attempt_count
                capture["provider_record"]["retry_count"] = self.retry_count
                return capture

        for attempt_count, retry_count in ((2, 1), (0, 0), (1, 1)):
            with self.subTest(
                attempt_count=attempt_count, retry_count=retry_count
            ):
                self._reset_plan()
                adapter = AttemptMutationAdapter(attempt_count, retry_count)
                with self.assertRaisesRegex(
                    VerificationError, "cannot aggregate retries"
                ):
                    self._run(adapter)

    def test_executed_usage_must_match_the_frozen_source_kind(self) -> None:
        class UsageMutationAdapter(CompleteAdapter):
            def __init__(self, mutation: str) -> None:
                super().__init__()
                self.mutation = mutation

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                capture = _provider_capture(request)
                if self.mutation == "model-calls":
                    capture["usage"]["model_calls"] = 0
                    capture["provider_record"]["usage"]["model_calls"] = 0
                else:
                    capture["usage"]["total_tokens"] = None
                    capture["provider_record"]["usage"]["total_tokens"] = None
                return capture

        for mutation, pattern in (
            ("model-calls", "model_calls differs from source kind"),
            ("completeness", "usage_complete differs from total"),
        ):
            with self.subTest(mutation=mutation):
                self._reset_plan()
                adapter = UsageMutationAdapter(mutation)
                with self.assertRaisesRegex(VerificationError, pattern):
                    self._run(adapter)

    def test_partial_external_usage_cannot_classify_reasoning(self) -> None:
        class ContradictoryPartialUsageAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                capture = _provider_capture(request)
                impossible_usage = {
                    "model_calls": 1,
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "reasoning_tokens": 999,
                    "reasoning_accounting": "included-in-output",
                    "total_tokens": None,
                    "usage_complete": False,
                }
                capture["usage"] = deepcopy(impossible_usage)
                capture["provider_record"]["usage"] = deepcopy(
                    impossible_usage
                )
                capture["provider_record_sha256"] = sha256_ref(
                    capture["provider_record"]
                )
                return capture

        adapter = ContradictoryPartialUsageAdapter()
        with self.assertRaisesRegex(
            VerificationError,
            "partial external usage cannot classify reasoning",
        ):
            self._run(adapter)
        self.assertEqual(len(adapter.calls), 2)

    def test_deterministic_local_model_token_total_must_be_zero(self) -> None:
        class LocalUsageAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                capture = _local_capture(request)
                capture["usage"]["total_tokens"] = 99
                capture["local_observation"]["usage"]["total_tokens"] = 99
                capture["local_observation_sha256"] = sha256_ref(
                    capture["local_observation"]
                )
                return capture

        adapter = LocalUsageAdapter()
        with self.assertRaisesRegex(
            VerificationError,
            "deterministic-local model-token total must be zero",
        ):
            self._run(adapter)
        self.assertEqual(len(adapter.calls), 1)

    def test_complete_failed_terminal_usage_requires_raw_receipt_preimage(self) -> None:
        class MissingReceiptAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                capture = _provider_capture(request)
                capture["provider_record"]["terminal_status"] = "provider_error"
                capture["provider_record"]["raw_receipt_utf8"] = None
                capture["provider_record"]["raw_receipt_sha256"] = None
                capture["facts"]["terminal_status"] = "provider_error"
                return capture

        adapter = MissingReceiptAdapter()
        with self.assertRaisesRegex(
            VerificationError,
            "complete provider usage requires an exact raw receipt preimage",
        ):
            self._run(adapter)
        self.assertEqual(len(adapter.calls), 2)

    def test_one_judge_failure_makes_total_unknown_but_later_judges_run(self) -> None:
        class OneJudgeFailureAdapter(CompleteAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.failed = False

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                component = request["slot"]["component"]
                if component == "parse-judge" and not self.failed:
                    self.failed = True
                    raise RuntimeError("synthetic judge failure")
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                return _local_capture(request)

        adapter = OneJudgeFailureAdapter()
        artifact = self._run(adapter)
        components = [item["slot"]["component"] for item in adapter.calls]
        failed_index = components.index("parse-judge")

        self.assertIn("semantic-judge", components[failed_index + 1 :])
        self.assertIn("negative-judge", components[failed_index + 1 :])
        self.assertFalse(artifact["content_usage_complete"])
        self.assertIsNone(artifact["content_bound_total_tokens"])
        self.assertFalse(artifact["four_judge_slots_recorded"])
        failed_run = next(
            item
            for item in artifact["slot_runs"]
            if item["slot_request"]["slot"]["component"] == "parse-judge"
            and item["capture"]["record_kind"]
            == "failure-before-source-record"
        )
        self.assertTrue(failed_run["callback_invoked"])
        self.assertFalse(failed_run["capture"]["usage"]["usage_complete"])
        self.assertFalse(
            failed_run["capture"]["effects"]["effects_complete"]
        )
        self.assertTrue(
            all(
                value is None
                for name, value in failed_run["capture"]["effects"].items()
                if name != "effects_complete"
            )
        )

    def test_adapter_exception_cannot_fabricate_known_false_effects(self) -> None:
        class ImmediateFailureAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                raise RuntimeError("effect scope became unobservable")

        artifact = self._run(ImmediateFailureAdapter())
        first = artifact["slot_runs"][0]["capture"]
        assert first is not None
        self.assertEqual(first["record_kind"], "failure-before-source-record")
        self.assertFalse(first["effects"]["effects_complete"])
        self.assertEqual(
            {
                value
                for name, value in first["effects"].items()
                if name != "effects_complete"
            },
            {None},
        )

        mutated = deepcopy(first)
        mutated["effects"] = {
            "effects_complete": False,
            "external_effects_performed": False,
            "permission_expanded": False,
            "persistence_created": False,
            "spending_authority_created": False,
            "tools_used": False,
        }
        with self.assertRaisesRegex(VerificationError, "must remain unknown"):
            validate_program_v2_slot_capture(
                mutated,
                artifact["slot_runs"][0]["slot_request"],
            )

    def test_provider_and_raw_receipt_identity_replay_is_rejected(self) -> None:
        class DuplicateIdentityAdapter(CompleteAdapter):
            def __init__(self, identity: str) -> None:
                super().__init__()
                self.identity = identity

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["source_kind"] != "external-response":
                    return _local_capture(request)
                return _provider_capture(
                    request,
                    provider_request_id=(
                        "replayed-provider-request"
                        if self.identity == "provider-request-id"
                        else None
                    ),
                    raw_receipt_utf8=(
                        "replayed-raw-receipt"
                        if self.identity == "raw-receipt-sha256"
                        else None
                    ),
                )

        for identity in ("provider-request-id", "raw-receipt-sha256"):
            with self.subTest(identity=identity):
                self._reset_plan()
                adapter = DuplicateIdentityAdapter(identity)
                with self.assertRaisesRegex(
                    VerificationError,
                    rf"runtime capture identity {identity} is replayed",
                ):
                    self._run(adapter)

    def test_plan_mutation_during_callback_is_detected_immediately(self) -> None:
        plan = self.plan

        class PlanMutatingAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                plan["notes"].append("mutated after the frozen snapshot")
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                return _local_capture(request)

        adapter = PlanMutatingAdapter()
        with self.assertRaisesRegex(VerificationError, "mutated frozen input"):
            self._run(adapter)
        self.assertEqual(len(adapter.calls), 1)

    def test_inactive_hybrid_slots_do_not_invoke_adapter_or_mint_records(self) -> None:
        adapter = CompleteAdapter(hybrid_mode="raw")
        artifact = self._run(adapter, arm_id="hybrid-router")
        called_components = [
            item["slot"]["component"] for item in adapter.calls
        ]
        inactive_components = {
            "sender-compiler",
            "fidelity-verifier",
            "output-validator",
            "fallback-control",
            "fallback-receiver",
        }

        self.assertTrue(inactive_components.isdisjoint(called_components))
        for item in artifact["slot_runs"]:
            component = item["slot_request"]["slot"]["component"]
            if component in inactive_components:
                self.assertFalse(item["callback_invoked"])
                self.assertIsNone(item["capture"])
                self.assertIsNone(item["capture_sha256"])
        self.assertTrue(artifact["content_usage_complete"])
        self.assertTrue(artifact["four_judge_slots_recorded"])

    def test_unknown_activation_cannot_mint_a_typed_execution_identity(self) -> None:
        class FinalRouterFailureAdapter(CompleteAdapter):
            def __init__(self) -> None:
                super().__init__(hybrid_mode="action-state")

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["component"] == "final-router":
                    raise RuntimeError("synthetic final-router failure")
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(
                        request,
                        hybrid_mode=self.hybrid_mode,
                    )
                return _local_capture(
                    request,
                    hybrid_mode=self.hybrid_mode,
                )

        original_builder = runtime_runner.build_program_v2_failure_capture

        def impossible_typed_unknown(slot_request, **kwargs):
            if kwargs["stage"] == "activation-unknown":
                kwargs["typed_execution_sha256"] = _digest(
                    f"uninvoked-{slot_request['slot']['slot_id']}"
                )
            return original_builder(slot_request, **kwargs)

        with patch.object(
            runtime_runner,
            "build_program_v2_failure_capture",
            side_effect=impossible_typed_unknown,
        ):
            with self.assertRaisesRegex(
                VerificationError,
                "uninvoked failure cannot bind a typed execution",
            ):
                self._run(
                    FinalRouterFailureAdapter(),
                    arm_id="hybrid-router",
                )


if __name__ == "__main__":
    unittest.main()
