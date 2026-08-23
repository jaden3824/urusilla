"""Adversarial tests for the typed compiler/receiver Program /2 bridge."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from initial_goal_eval.contract import (
    VERIFIER_BUNDLE_FILES_V2,
    VerificationError,
    sha256_ref,
)
from initial_goal_eval.program_v2_runtime_runner import (
    run_planned_program_v2_arm,
    validate_program_v2_runtime_run,
    validate_program_v2_slot_capture,
)
from initial_goal_eval.runtime_capture_bridge import (
    build_program_v2_compiler_capture,
    build_program_v2_receiver_capture,
)
from initial_goal_eval.tests.test_plan_v2 import build_synthetic_plan_v2
from initial_goal_eval.tests.test_program_v2_runtime_runner import (
    CompleteAdapter,
    _local_capture,
    _provider_capture,
)
from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.captured_compiler import (
    CapturedCompilerResponse,
    execute_captured_compiler,
)
from urusilla_hybrid_runtime.captured_receiver import (
    CapturedProviderResponse,
    execute_captured_receiver,
)
from urusilla_hybrid_runtime.receiver import build_json_request
from urusilla_hybrid_runtime.tests.test_captured_compiler import (
    StaticCapturedAdapter as StaticCompilerAdapter,
    _completed_capture as _compiler_completed_capture,
    _known_billed_failure_capture as _compiler_known_billed_failure_capture,
    _prompt as _compiler_prompt,
    _reply as _compiler_reply,
)
from urusilla_hybrid_runtime.tests.test_captured_receiver import (
    StaticCapturedAdapter as StaticReceiverAdapter,
    _before_dispatch_failure_capture,
    _completed_capture as _receiver_completed_capture,
    _context as _receiver_context,
    _known_billed_failure_capture,
    _reply as _receiver_reply,
    _request as _raw_request,
    _transport_failure_capture,
)


def _digest(label: str) -> str:
    return sha256_ref({"runtime-capture-bridge-test": label})


class _RaisingReceiverAdapter:
    def complete_captured(self, request):
        raise RuntimeError("synthetic receiver adapter failure")


class RuntimeCaptureBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_synthetic_plan_v2()
        cls.session = cls.plan["sessions"][0]
        cls.requests: dict[tuple[str, str], dict] = {}
        for arm_id, mode in (
            ("raw-concise", "raw"),
            ("ordinary-json", "json"),
            ("hybrid-router", "action-state"),
        ):
            adapter = CompleteAdapter(hybrid_mode=mode)
            run_planned_program_v2_arm(
                cls.plan,
                session_id=cls.session["session_id"],
                arm_id=arm_id,
                execution_instance_sha256=_digest(f"request-source-{arm_id}"),
                adapter=adapter,
            )
            for request in adapter.calls:
                key = (arm_id, request["slot"]["component"])
                cls.requests.setdefault(key, deepcopy(request))

    def _receiver_execution(
        self,
        slot_request: dict,
        *,
        mode: str = "raw",
        kind: str = "completed",
        identity_suffix: str | None = None,
    ):
        expected_model = slot_request["expected_model_id"]
        expected_settings = slot_request["expected_settings_sha256"]
        request = (
            _raw_request()
            if mode == "raw"
            else build_json_request(
                "Return the public verification result.",
                _receiver_context(),
                maximum_total_tokens=100,
            )
        )
        if kind == "adapter-failure":
            return execute_captured_receiver(
                request,
                _RaisingReceiverAdapter(),
                expected_model_id=expected_model,
                expected_settings_sha256=expected_settings,
            )
        if kind == "completed":
            reply = replace(_receiver_reply(), model_id=expected_model)
            capture = replace(
                _receiver_completed_capture(request, reply),
                settings_sha256=expected_settings,
            )
            if identity_suffix is not None:
                receipt = canonical_json(
                    {
                        "id": f"response-{identity_suffix}",
                        "status": "completed",
                    }
                )
                capture = replace(
                    capture,
                    provider_request_id=f"request-{identity_suffix}",
                    provider_response_id=f"response-{identity_suffix}",
                    raw_receipt_text=receipt,
                    raw_receipt_sha256=sha256_text(receipt),
                )
            response = CapturedProviderResponse(capture=capture, reply=reply)
        elif kind == "known-billed-failure":
            capture = replace(
                _known_billed_failure_capture(request),
                model_id=expected_model,
                settings_sha256=expected_settings,
            )
            response = CapturedProviderResponse(capture=capture, reply=None)
        elif kind == "before-dispatch":
            capture = replace(
                _before_dispatch_failure_capture(request),
                settings_sha256=expected_settings,
            )
            response = CapturedProviderResponse(capture=capture, reply=None)
        elif kind == "retry-failure":
            capture = replace(
                _transport_failure_capture(request),
                model_id=expected_model,
                settings_sha256=expected_settings,
            )
            response = CapturedProviderResponse(capture=capture, reply=None)
        else:
            raise AssertionError(kind)
        return execute_captured_receiver(
            request,
            StaticReceiverAdapter(response),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

    def _compiler_execution(self, slot_request: dict, *, valid: bool = True):
        expected_model = slot_request["expected_model_id"]
        expected_settings = slot_request["expected_settings_sha256"]
        prompt = _compiler_prompt()
        text = (
            canonical_json(
                {
                    "candidates": [],
                    "failure": None,
                    "status": "unsupported",
                    "unsupported": ["outside-public-contract"],
                }
            )
            if valid
            else "not strict JSON"
        )
        reply = replace(
            _compiler_reply(text=text),
            model_id=expected_model,
        )
        capture = _compiler_completed_capture(
            prompt,
            reply,
            model_id=expected_model,
            settings_sha256=expected_settings,
        )
        return execute_captured_compiler(
            prompt,
            StaticCompilerAdapter(
                CapturedCompilerResponse(capture=capture, reply=reply)
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

    def _partial_billed_compiler_execution(self, slot_request: dict):
        expected_model = slot_request["expected_model_id"]
        expected_settings = slot_request["expected_settings_sha256"]
        prompt = _compiler_prompt()
        capture = replace(
            _compiler_known_billed_failure_capture(prompt),
            model_id=expected_model,
            settings_sha256=expected_settings,
            output_tokens=None,
            usage_complete=False,
        )
        return execute_captured_compiler(
            prompt,
            StaticCompilerAdapter(
                CapturedCompilerResponse(capture=capture, reply=None)
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

    def _no_receipt_billed_compiler_execution(self, slot_request: dict):
        expected_model = slot_request["expected_model_id"]
        expected_settings = slot_request["expected_settings_sha256"]
        prompt = _compiler_prompt()
        capture = replace(
            _compiler_known_billed_failure_capture(prompt),
            model_id=expected_model,
            settings_sha256=expected_settings,
            raw_receipt_text=None,
            raw_receipt_sha256=None,
        )
        return execute_captured_compiler(
            prompt,
            StaticCompilerAdapter(
                CapturedCompilerResponse(capture=capture, reply=None)
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

    def test_completed_receiver_maps_only_typed_observations(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        execution = self._receiver_execution(request)

        capture = build_program_v2_receiver_capture(request, execution)

        provider = capture["provider_record"]
        self.assertEqual(provider["model_id"], execution.capture.model_id)
        self.assertEqual(provider["settings_sha256"], execution.capture.settings_sha256)
        self.assertEqual(provider["usage"]["total_tokens"], 12)
        self.assertEqual(provider["terminal_status"], "completed")
        self.assertEqual(capture["facts"], {"terminal_status": "completed"})
        self.assertTrue(capture["effects"]["effects_complete"])
        self.assertFalse(capture["authority"]["claim_eligible"])
        self.assertEqual(
            provider["request"]["request_preimage_json"],
            execution.request_preimage_json,
        )

    def test_completed_compiler_derives_facts_without_caller_input(self) -> None:
        request = self.requests[("hybrid-router", "sender-compiler")]
        execution = self._compiler_execution(request)

        capture = build_program_v2_compiler_capture(request, execution)

        self.assertEqual(
            capture["facts"],
            {
                "terminal_status": "completed",
                "compiler_status": "unsupported",
            },
        )
        self.assertEqual(
            capture["provider_record"]["response"]["execution_binding_sha256"],
            execution.binding_sha256,
        )

    def test_invalid_compiler_reply_is_recorded_as_failed_policy_fact(self) -> None:
        request = self.requests[("hybrid-router", "sender-compiler")]
        execution = self._compiler_execution(request, valid=False)

        capture = build_program_v2_compiler_capture(request, execution)

        self.assertEqual(capture["facts"]["terminal_status"], "completed")
        self.assertEqual(capture["facts"]["compiler_status"], "failed")

    def test_failed_dispatched_attempt_preserves_known_billed_usage(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        execution = self._receiver_execution(
            request,
            kind="known-billed-failure",
        )

        capture = build_program_v2_receiver_capture(request, execution)

        self.assertEqual(capture["record_kind"], "executed-source")
        self.assertEqual(capture["facts"]["terminal_status"], "provider_error")
        self.assertEqual(capture["usage"]["total_tokens"], 12)
        self.assertTrue(capture["usage"]["usage_complete"])
        self.assertIsNotNone(capture["provider_record"]["raw_receipt_utf8"])

    def test_partial_receiver_usage_stays_exact_without_becoming_complete(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        expected_model = request["expected_model_id"]
        expected_settings = request["expected_settings_sha256"]
        receiver_request = _raw_request()
        partial_capture = replace(
            _known_billed_failure_capture(receiver_request),
            model_id=expected_model,
            settings_sha256=expected_settings,
            output_tokens=None,
            usage_complete=False,
        )
        execution = execute_captured_receiver(
            receiver_request,
            StaticReceiverAdapter(
                CapturedProviderResponse(capture=partial_capture, reply=None)
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

        capture = build_program_v2_receiver_capture(request, execution)

        self.assertEqual(capture["record_kind"], "executed-source")
        self.assertEqual(capture["usage"]["input_tokens"], 10)
        self.assertIsNone(capture["usage"]["output_tokens"])
        self.assertIsNone(capture["usage"]["total_tokens"])
        self.assertFalse(capture["usage"]["usage_complete"])
        typed = capture["provider_record"]["response"]["typed_usage"]
        self.assertEqual(typed["total_tokens"], 12)
        self.assertIsNone(typed["output_tokens"])
        self.assertFalse(typed["usage_complete"])

    def test_partial_compiler_usage_stays_exact_without_becoming_complete(self) -> None:
        request = self.requests[("hybrid-router", "sender-compiler")]
        execution = self._partial_billed_compiler_execution(request)

        capture = build_program_v2_compiler_capture(request, execution)

        self.assertEqual(capture["record_kind"], "executed-source")
        self.assertEqual(capture["usage"]["input_tokens"], 10)
        self.assertIsNone(capture["usage"]["output_tokens"])
        self.assertIsNone(capture["usage"]["total_tokens"])
        self.assertFalse(capture["usage"]["usage_complete"])
        typed = capture["provider_record"]["response"]["typed_usage"]
        self.assertEqual(typed["total_tokens"], 12)
        self.assertIsNone(typed["output_tokens"])
        self.assertFalse(typed["usage_complete"])

    def test_no_receipt_receiver_usage_is_not_promoted_to_generic_total(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        expected_model = request["expected_model_id"]
        expected_settings = request["expected_settings_sha256"]
        receiver_request = _raw_request()
        no_receipt_capture = replace(
            _known_billed_failure_capture(receiver_request),
            model_id=expected_model,
            settings_sha256=expected_settings,
            raw_receipt_text=None,
            raw_receipt_sha256=None,
        )
        execution = execute_captured_receiver(
            receiver_request,
            StaticReceiverAdapter(
                CapturedProviderResponse(capture=no_receipt_capture, reply=None)
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

        capture = build_program_v2_receiver_capture(request, execution)

        self.assertIsNone(capture["usage"]["total_tokens"])
        self.assertFalse(capture["usage"]["usage_complete"])
        typed = capture["provider_record"]["response"]["typed_usage"]
        self.assertEqual(typed["total_tokens"], 12)
        self.assertTrue(typed["usage_complete"])
        self.assertIsNone(capture["provider_record"]["raw_receipt_utf8"])

    def test_no_receipt_compiler_usage_is_not_promoted_to_generic_total(self) -> None:
        request = self.requests[("hybrid-router", "sender-compiler")]
        execution = self._no_receipt_billed_compiler_execution(request)

        capture = build_program_v2_compiler_capture(request, execution)

        self.assertIsNone(capture["usage"]["total_tokens"])
        self.assertFalse(capture["usage"]["usage_complete"])
        typed = capture["provider_record"]["response"]["typed_usage"]
        self.assertEqual(typed["total_tokens"], 12)
        self.assertTrue(typed["usage_complete"])
        self.assertIsNone(capture["provider_record"]["raw_receipt_utf8"])

    def test_before_dispatch_and_missing_capture_preserve_effect_scope(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        before_execution = self._receiver_execution(
            request, kind="before-dispatch"
        )
        missing_execution = self._receiver_execution(
            request, kind="adapter-failure"
        )
        before = build_program_v2_receiver_capture(request, before_execution)
        missing = build_program_v2_receiver_capture(request, missing_execution)

        self.assertEqual(before["record_kind"], "failure-before-source-record")
        self.assertTrue(before["effects"]["effects_complete"])
        self.assertFalse(missing["effects"]["effects_complete"])
        self.assertEqual(
            before["failure_artifact"]["request"][
                "execution_binding_sha256"
            ],
            before_execution.binding_sha256,
        )
        self.assertEqual(
            missing["failure_artifact"]["request"][
                "execution_binding_sha256"
            ],
            missing_execution.binding_sha256,
        )
        self.assertTrue(
            all(
                value is None
                for name, value in missing["effects"].items()
                if name != "effects_complete"
            )
        )

    def test_retry_model_settings_component_and_mode_mismatches_fail_closed(self) -> None:
        raw = self.requests[("raw-concise", "receiver")]
        json_request = self.requests[("ordinary-json", "receiver")]
        execution = self._receiver_execution(raw)

        with self.subTest(case="retry"):
            retried = self._receiver_execution(raw, kind="retry-failure")
            with self.assertRaisesRegex(VerificationError, "retries"):
                build_program_v2_receiver_capture(raw, retried)
        with self.subTest(case="model"):
            mutated = deepcopy(raw)
            mutated["expected_model_id"] = "foreign-model"
            with self.assertRaisesRegex(VerificationError, "expected model"):
                build_program_v2_receiver_capture(mutated, execution)
        with self.subTest(case="settings"):
            mutated = deepcopy(raw)
            mutated["expected_settings_sha256"] = _digest("foreign-settings")
            with self.assertRaisesRegex(VerificationError, "expected settings"):
                build_program_v2_receiver_capture(mutated, execution)
        with self.subTest(case="component"):
            judge = self.requests[("hybrid-router", "task-judge")]
            with self.assertRaisesRegex(VerificationError, "cross-wired"):
                build_program_v2_receiver_capture(judge, execution)
        with self.subTest(case="mode"):
            with self.assertRaisesRegex(VerificationError, "baseline receiver mode"):
                build_program_v2_receiver_capture(json_request, execution)

    def test_receiver_factory_structural_rejection_is_fatal(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        expected_model = request["expected_model_id"]
        expected_settings = request["expected_settings_sha256"]
        receiver_request = _raw_request()
        reply = replace(_receiver_reply(), model_id="foreign-model")
        rejected_capture = replace(
            _receiver_completed_capture(receiver_request, reply),
            settings_sha256=expected_settings,
        )
        execution = execute_captured_receiver(
            receiver_request,
            StaticReceiverAdapter(
                CapturedProviderResponse(
                    capture=rejected_capture,
                    reply=reply,
                )
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )
        self.assertEqual(execution.status, "capture-rejected")

        with self.assertRaisesRegex(
            VerificationError,
            "receiver structural capture rejection is fatal",
        ):
            build_program_v2_receiver_capture(request, execution)

    def test_compiler_factory_request_substitution_rejection_is_fatal(self) -> None:
        request = self.requests[("hybrid-router", "sender-compiler")]
        expected_model = request["expected_model_id"]
        expected_settings = request["expected_settings_sha256"]
        prompt = _compiler_prompt()
        reply = replace(_compiler_reply(), model_id=expected_model)
        rejected_capture = _compiler_completed_capture(
            prompt,
            reply,
            request_binding_sha256=_digest("substituted-compiler-request"),
            model_id=expected_model,
            settings_sha256=expected_settings,
        )
        execution = execute_captured_compiler(
            prompt,
            StaticCompilerAdapter(
                CapturedCompilerResponse(
                    capture=rejected_capture,
                    reply=reply,
                )
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )
        self.assertEqual(execution.status, "capture-rejected")

        with self.assertRaisesRegex(
            VerificationError,
            "compiler structural capture rejection is fatal",
        ):
            build_program_v2_compiler_capture(request, execution)

    def test_full_program_runner_replays_a_typed_receiver_capture(self) -> None:
        owner = self

        class TypedReceiverAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["component"] == "receiver":
                    execution = owner._receiver_execution(
                        request,
                        identity_suffix=request["slot"]["slot_id"][-12:],
                    )
                    return build_program_v2_receiver_capture(request, execution)
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                return _local_capture(request)

        artifact = run_planned_program_v2_arm(
            self.plan,
            session_id=self.session["session_id"],
            arm_id="raw-concise",
            execution_instance_sha256=_digest("full-run"),
            adapter=TypedReceiverAdapter(),
        )

        self.assertEqual(validate_program_v2_runtime_run(artifact), artifact)
        receiver = next(
            item["capture"]
            for item in artifact["slot_runs"]
            if item["slot_request"]["slot"]["component"] == "receiver"
        )
        self.assertEqual(
            receiver["provider_record"]["request"]["bridge_kind"],
            "receiver",
        )
        self.assertFalse(artifact["authority"]["request_derivation_verified"])
        self.assertFalse(artifact["authority"]["raw_usage_normalization_verified"])

    def test_one_before_dispatch_execution_cannot_be_replayed_across_tasks(self) -> None:
        owner = self
        first_request = self.requests[("raw-concise", "receiver")]
        replayed_execution = self._receiver_execution(
            first_request,
            kind="before-dispatch",
        )

        class ReplayedTypedFailureAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["component"] == "receiver":
                    return build_program_v2_receiver_capture(
                        request,
                        replayed_execution,
                    )
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                return _local_capture(request)

        with self.assertRaisesRegex(
            VerificationError,
            "typed-execution-sha256 is replayed",
        ):
            run_planned_program_v2_arm(
                owner.plan,
                session_id=owner.session["session_id"],
                arm_id="raw-concise",
                execution_instance_sha256=_digest("typed-failure-replay"),
                adapter=ReplayedTypedFailureAdapter(),
            )

    def test_typed_receiver_envelope_cannot_drop_its_execution_identity(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        execution = self._receiver_execution(request)
        capture = build_program_v2_receiver_capture(request, execution)
        capture["typed_execution_sha256"] = None

        with self.assertRaisesRegex(
            VerificationError,
            "typed envelope lacks execution identity",
        ):
            validate_program_v2_slot_capture(capture, request)

    def test_typed_before_dispatch_envelope_cannot_drop_replay_identity(self) -> None:
        request = self.requests[("raw-concise", "receiver")]
        execution = self._receiver_execution(request, kind="before-dispatch")
        capture = build_program_v2_receiver_capture(request, execution)
        capture["typed_execution_sha256"] = None

        with self.assertRaisesRegex(
            VerificationError,
            "typed envelope lacks execution identity",
        ):
            validate_program_v2_slot_capture(capture, request)

    def test_plan_v2_verifier_bundle_includes_bridge_and_capture_semantics(self) -> None:
        names = {path.name for path in VERIFIER_BUNDLE_FILES_V2}
        self.assertIn("runtime_capture_bridge.py", names)
        self.assertIn("captured_receiver.py", names)
        self.assertIn("captured_compiler.py", names)
        self.assertIn("receiver.py", names)
        self.assertIn("sender.py", names)


if __name__ == "__main__":
    unittest.main()
