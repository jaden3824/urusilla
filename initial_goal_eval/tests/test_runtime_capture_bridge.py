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
from initial_goal_eval.execution_program import execution_program_sha256
from initial_goal_eval.program_v2_runtime_runner import (
    run_planned_program_v2_arm,
    validate_program_v2_runtime_run,
    validate_program_v2_slot_capture,
)
from initial_goal_eval.runtime_capture_bridge import (
    build_program_v2_compiler_capture,
    build_program_v2_judge_capture,
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
from urusilla_hybrid_runtime.captured_judge import (
    JUDGE_ROLES,
    CapturedJudgeResponse,
    JudgeTaskMessage,
    JudgeTaskMetadata,
    JudgeTerminalEvidence,
    RoleSeparatedJudgeRequest,
    execute_captured_judge,
    judge_task_input_sha256,
    judge_terminal_output_sha256,
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
from urusilla_hybrid_runtime.tests.test_captured_judge import (
    StaticJudgeAdapter,
    _billed_failure_capture as _judge_billed_failure_capture,
    _completed_capture as _judge_completed_capture,
    _reply as _judge_reply,
    _verdict_text as _judge_verdict_text,
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


def _judge_task_messages(task_id: str) -> tuple[JudgeTaskMessage, ...]:
    return (
        JudgeTaskMessage("system", "Follow the exact bounded task contract."),
        JudgeTaskMessage("user", f"Return the public answer for {task_id}."),
    )


def _judge_ready_plan() -> dict:
    """Give synthetic Plan /2 tasks real provider-neutral input preimages."""

    plan = build_synthetic_plan_v2()
    for session in plan["sessions"]:
        task_sha_by_id: dict[str, str] = {}
        for index, task in enumerate(session["tasks"]):
            task_sha = judge_task_input_sha256(
                _judge_task_messages(task["task_id"])
            )
            task["task_sha256"] = task_sha
            # Exercise a genuine disabled-probe path without changing task
            # identity or removing the still-costed negative judge slot.
            if index == 0:
                task["negative_probe"] = False
            task_sha_by_id[task["task_id"]] = task_sha
        for wrapper in session["arm_execution_programs"].values():
            program = wrapper["program"]
            for task_ref in program["task_refs"]:
                task_ref["task_sha256"] = task_sha_by_id[task_ref["task_id"]]
            wrapper["program_sha256"] = execution_program_sha256(program)
    return plan


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
        self.assertIn("captured_judge.py", names)
        self.assertIn("receiver.py", names)
        self.assertIn("sender.py", names)


class JudgeRuntimeCaptureBridgeTests(unittest.TestCase):
    """Adversarial integration checks for the typed Program /2 judge seam."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = _judge_ready_plan()
        cls.session = cls.plan["sessions"][0]
        cls.task_by_id = {
            task["task_id"]: task for task in cls.session["tasks"]
        }
        owner = cls

        class TypedTerminalAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["component"] == "receiver":
                    execution = owner._receiver_execution(request)
                    return build_program_v2_receiver_capture(request, execution)
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                return _local_capture(request)

        typed_adapter = TypedTerminalAdapter()
        cls.typed_artifact = run_planned_program_v2_arm(
            cls.plan,
            session_id=cls.session["session_id"],
            arm_id="raw-concise",
            execution_instance_sha256=_digest("judge-typed-terminal-source"),
            adapter=typed_adapter,
        )
        generic_adapter = CompleteAdapter()
        cls.generic_artifact = run_planned_program_v2_arm(
            cls.plan,
            session_id=cls.session["session_id"],
            arm_id="raw-concise",
            execution_instance_sha256=_digest("judge-generic-terminal-source"),
            adapter=generic_adapter,
        )
        cls.typed_requests = {
            (
                entry["slot_request"]["slot"]["task_id"],
                entry["slot_request"]["slot"]["component"],
            ): deepcopy(entry["slot_request"])
            for entry in cls.typed_artifact["slot_runs"]
            if entry["slot_request"]["slot"]["component"] in JUDGE_ROLES
        }
        cls.generic_requests = {
            (
                entry["slot_request"]["slot"]["task_id"],
                entry["slot_request"]["slot"]["component"],
            ): deepcopy(entry["slot_request"])
            for entry in cls.generic_artifact["slot_runs"]
            if entry["slot_request"]["slot"]["component"] in JUDGE_ROLES
        }

    @staticmethod
    def _receiver_execution(slot_request: dict):
        expected_model = slot_request["expected_model_id"]
        expected_settings = slot_request["expected_settings_sha256"]
        suffix = str(slot_request["slot_index"])
        request = _raw_request(
            f"Return the terminal fixture for {slot_request['slot']['task_id']}."
        )
        reply = replace(
            _receiver_reply(),
            text=f"typed-terminal::{slot_request['slot']['task_id']}",
            model_id=expected_model,
        )
        receipt = canonical_json(
            {"id": f"receiver-response-{suffix}", "status": "completed"}
        )
        capture = replace(
            _receiver_completed_capture(request, reply),
            settings_sha256=expected_settings,
            provider_request_id=f"receiver-request-{suffix}",
            provider_response_id=f"receiver-response-{suffix}",
            raw_receipt_text=receipt,
            raw_receipt_sha256=sha256_text(receipt),
        )
        return execute_captured_receiver(
            request,
            StaticReceiverAdapter(
                CapturedProviderResponse(capture=capture, reply=reply)
            ),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

    @staticmethod
    def _probe_applicable(slot_request: dict, role: str) -> bool:
        if role == "task-judge":
            return True
        field = {
            "parse-judge": "parse_probe",
            "semantic-judge": "semantic_probe",
            "negative-judge": "negative_probe",
        }[role]
        return slot_request["task_metadata"][field]

    @staticmethod
    def _terminal(slot_request: dict) -> JudgeTerminalEvidence:
        value = slot_request["terminal_evidence"]
        return JudgeTerminalEvidence(**value)

    @classmethod
    def _judge_request(
        cls,
        slot_request: dict,
        *,
        role: str | None = None,
        probe_applicable: bool | None = None,
        terminal: JudgeTerminalEvidence | None = None,
    ) -> RoleSeparatedJudgeRequest:
        selected_role = role or slot_request["slot"]["component"]
        applicable = (
            cls._probe_applicable(slot_request, selected_role)
            if probe_applicable is None
            else probe_applicable
        )
        task_id = slot_request["slot"]["task_id"]
        metadata_value = deepcopy(slot_request["task_metadata"])
        if probe_applicable is not None and selected_role != "task-judge":
            metadata_value[
                {
                    "parse-judge": "parse_probe",
                    "semantic-judge": "semantic_probe",
                    "negative-judge": "negative_probe",
                }[selected_role]
            ] = probe_applicable
        metadata_value["feature_tags"] = tuple(metadata_value["feature_tags"])
        metadata = JudgeTaskMetadata(**metadata_value)
        rubric = f"Apply only the frozen {selected_role} rubric."
        reference = f"Frozen reference for {task_id}."
        return RoleSeparatedJudgeRequest(
            judge_role=selected_role,
            task_id=task_id,
            planned_task_sha256=slot_request["task_sha256"],
            task_messages=_judge_task_messages(task_id),
            probe_applicable=applicable,
            task_metadata=metadata,
            terminal=cls._terminal(slot_request) if terminal is None else terminal,
            rubric_text=rubric,
            rubric_sha256=sha256_text(rubric),
            reference_text=reference,
            reference_sha256=sha256_text(reference),
            maximum_total_tokens=100,
        )

    @classmethod
    def _judge_execution(
        cls,
        slot_request: dict,
        *,
        role: str | None = None,
        probe_applicable: bool | None = None,
        terminal: JudgeTerminalEvidence | None = None,
        malformed_verdict: bool = False,
        provider_failure: bool = False,
        expected_model_id: str | None = None,
        expected_settings_sha256: str | None = None,
    ):
        request = cls._judge_request(
            slot_request,
            role=role,
            probe_applicable=probe_applicable,
            terminal=terminal,
        )
        model = expected_model_id or slot_request["expected_model_id"]
        settings = (
            expected_settings_sha256
            or slot_request["expected_settings_sha256"]
        )
        if provider_failure:
            capture = replace(
                _judge_billed_failure_capture(request),
                model_id=model,
                settings_sha256=settings,
            )
            response = CapturedJudgeResponse(capture, None)
        else:
            verdict = (
                "not-applicable"
                if not request.probe_applicable
                else "pass"
            )
            text = (
                "malformed non-JSON verdict"
                if malformed_verdict
                else _judge_verdict_text(request.judge_role, verdict)
            )
            reply = replace(_judge_reply(text), model_id=model)
            capture = replace(
                _judge_completed_capture(
                    request,
                    reply,
                    settings_sha256=settings,
                ),
                model_id=model,
            )
            response = CapturedJudgeResponse(capture, reply)
        return execute_captured_judge(
            request,
            StaticJudgeAdapter(response),
            expected_model_id=model,
            expected_settings_sha256=settings,
        )

    def test_all_four_roles_bind_and_keep_verdicts_out_of_program_facts(self) -> None:
        task_id = self.session["tasks"][0]["task_id"]
        for role in JUDGE_ROLES:
            with self.subTest(role=role):
                slot_request = self.typed_requests[(task_id, role)]
                execution = self._judge_execution(slot_request)

                capture = build_program_v2_judge_capture(
                    slot_request,
                    execution,
                )

                self.assertEqual(capture["record_kind"], "executed-source")
                self.assertEqual(
                    capture["facts"], {"terminal_status": "completed"}
                )
                self.assertEqual(capture["usage"]["total_tokens"], 12)
                self.assertEqual(
                    capture["typed_execution_sha256"],
                    execution.binding_sha256,
                )
                self.assertFalse(capture["authority"]["claim_eligible"])
                self.assertNotIn("verdict", capture["facts"])
                self.assertNotIn("verdict_parse_status", capture["facts"])

    def test_task_digest_and_probe_applicability_are_exact(self) -> None:
        first, second = [task["task_id"] for task in self.session["tasks"]]
        negative_slot = self.typed_requests[(first, "negative-judge")]
        self.assertFalse(negative_slot["task_metadata"]["negative_probe"])
        disabled = self._judge_execution(negative_slot)
        disabled_capture = build_program_v2_judge_capture(
            negative_slot,
            disabled,
        )
        self.assertEqual(disabled.verdict.verdict, "not-applicable")
        self.assertEqual(disabled_capture["usage"]["total_tokens"], 12)

        wrong_probe = self._judge_execution(
            negative_slot,
            probe_applicable=True,
        )
        with self.assertRaises(VerificationError):
            build_program_v2_judge_capture(negative_slot, wrong_probe)

        first_task_slot = self.typed_requests[(first, "task-judge")]
        second_task_execution = self._judge_execution(
            self.typed_requests[(second, "task-judge")]
        )
        with self.assertRaises(VerificationError):
            build_program_v2_judge_capture(
                first_task_slot,
                second_task_execution,
            )

    def test_terminal_output_and_source_substitutions_fail_closed(self) -> None:
        task_id = self.session["tasks"][0]["task_id"]
        slot_request = self.typed_requests[(task_id, "task-judge")]
        terminal = self._terminal(slot_request)
        substitutions = (
            replace(
                terminal,
                output_text="substituted terminal output",
                output_sha256=judge_terminal_output_sha256(
                    "substituted terminal output"
                ),
            ),
            replace(terminal, source_slot_id="foreign-terminal-slot"),
            replace(
                terminal,
                source_capture_sha256=_digest("foreign-terminal-capture"),
            ),
            replace(
                terminal,
                source_typed_execution_sha256=_digest(
                    "foreign-terminal-execution"
                ),
            ),
        )
        for substituted in substitutions:
            with self.subTest(substituted=substituted):
                execution = self._judge_execution(
                    slot_request,
                    terminal=substituted,
                )
                with self.assertRaises(VerificationError):
                    build_program_v2_judge_capture(slot_request, execution)

    def test_fully_unbound_unresolved_terminal_is_rejected(self) -> None:
        task_id = self.session["tasks"][0]["task_id"]
        slot_request = deepcopy(
            self.generic_requests[(task_id, "task-judge")]
        )
        execution = self._judge_execution(slot_request)
        slot_request["terminal_evidence"].update(
            {
                "source_slot_id": None,
                "source_component": None,
                "source_disposition": None,
                "source_record_sha256": None,
                "source_capture_sha256": None,
                "source_typed_execution_sha256": None,
            }
        )

        with self.assertRaises(VerificationError):
            build_program_v2_judge_capture(slot_request, execution)

    def test_malformed_verdict_preserves_executed_cost_without_program_fact(self) -> None:
        task_id = self.session["tasks"][0]["task_id"]
        slot_request = self.typed_requests[(task_id, "task-judge")]
        execution = self._judge_execution(
            slot_request,
            malformed_verdict=True,
        )
        self.assertEqual(execution.verdict_parse_status, "invalid")

        capture = build_program_v2_judge_capture(slot_request, execution)

        self.assertEqual(capture["record_kind"], "executed-source")
        self.assertEqual(capture["usage"]["total_tokens"], 12)
        self.assertTrue(capture["usage"]["usage_complete"])
        self.assertEqual(capture["facts"], {"terminal_status": "completed"})

    def test_provider_failure_preserves_billed_cost_without_a_verdict(self) -> None:
        task_id = self.session["tasks"][0]["task_id"]
        slot_request = self.typed_requests[(task_id, "semantic-judge")]
        execution = self._judge_execution(
            slot_request,
            provider_failure=True,
        )
        self.assertIsNone(execution.verdict)
        self.assertEqual(execution.verdict_parse_status, "indeterminate")

        capture = build_program_v2_judge_capture(slot_request, execution)

        self.assertEqual(capture["record_kind"], "executed-source")
        self.assertEqual(capture["usage"]["total_tokens"], 7)
        self.assertTrue(capture["usage"]["usage_complete"])
        self.assertEqual(
            capture["facts"], {"terminal_status": "provider_error"}
        )

    def test_cross_role_model_and_settings_are_rejected(self) -> None:
        task_id = self.session["tasks"][0]["task_id"]
        task_slot = self.typed_requests[(task_id, "task-judge")]
        cases = (
            self._judge_execution(task_slot, role="parse-judge"),
            self._judge_execution(
                task_slot,
                expected_model_id="foreign-judge-model",
            ),
            self._judge_execution(
                task_slot,
                expected_settings_sha256=_digest("foreign-judge-settings"),
            ),
        )
        for execution in cases:
            with self.subTest(execution=execution.binding_sha256):
                with self.assertRaises(VerificationError):
                    build_program_v2_judge_capture(task_slot, execution)


if __name__ == "__main__":
    unittest.main()
