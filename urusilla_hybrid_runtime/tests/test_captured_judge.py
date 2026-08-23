"""Adversarial tests for the role-separated captured judge boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from unittest import TestCase

from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.captured_judge import (
    JUDGE_ROLES,
    JUDGE_REQUEST_PREIMAGE_SCHEMA,
    PROGRAM_V2_TERMINAL_EVIDENCE_SCHEMA,
    ROLE_SEPARATED_JUDGE_REQUEST_SCHEMA,
    ROLE_SEPARATED_JUDGE_VERDICT_SCHEMA,
    CapturedJudgeResponse,
    JudgeError,
    JudgeTaskMessage,
    JudgeTaskMetadata,
    JudgeTerminalEvidence,
    RoleSeparatedJudgeRequest,
    execute_captured_judge,
    judge_reply_preimage_sha256,
    judge_request_preimage,
    judge_request_preimage_sha256,
    judge_task_input_sha256,
    judge_terminal_output_sha256,
    parse_role_separated_judge_verdict,
)
from urusilla_hybrid_runtime.captured_receiver import (
    PROVIDER_REQUEST_CAPTURE_SCHEMA,
    ProviderRequestCapture,
    provider_messages_sha256,
)
from urusilla_hybrid_runtime.receiver import ReceiverModelReply


MODEL_ID = "judge-model-a"
SETTINGS_SHA256 = sha256_text("judge-settings-a")
RECEIPT_TEXT = '{"id":"judge-response-001","status":"completed"}'
RECEIPT_SHA256 = sha256_text(RECEIPT_TEXT)


class StaticJudgeAdapter:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete_captured(self, request):
        self.calls += 1
        return self.response


def _messages() -> tuple[JudgeTaskMessage, ...]:
    return (
        JudgeTaskMessage("system", "Follow the bounded task contract."),
        JudgeTaskMessage("user", "Return the exact public answer."),
    )


def _terminal() -> JudgeTerminalEvidence:
    output = "the public answer"
    return JudgeTerminalEvidence(
        task_id="task-001",
        task_sha256=judge_task_input_sha256(_messages()),
        arm_id="raw-concise",
        selected_mode="raw",
        terminal_kind="provider-text",
        terminal_status="completed",
        output_text=output,
        output_sha256=judge_terminal_output_sha256(output),
        source_slot_id="receiver-task-001",
        source_component="receiver",
        source_disposition="executed",
        source_record_sha256=sha256_text("receiver-record"),
        source_capture_sha256=sha256_text("receiver-capture"),
        source_typed_execution_sha256=sha256_text("receiver-execution"),
        content_binding_verified=True,
    )


def _request(
    role: str = "task-judge",
    *,
    probe_applicable: bool = True,
    maximum_total_tokens: int | None = 100,
    terminal: JudgeTerminalEvidence | None = None,
) -> RoleSeparatedJudgeRequest:
    messages = _messages()
    task_sha256 = judge_task_input_sha256(messages)
    rubric = "Apply only this frozen role rubric."
    reference = "The exact public answer is acceptable."
    metadata = JudgeTaskMetadata(
        task_id="task-001",
        task_sha256=task_sha256,
        feature_tags=("bounded", "public-answer"),
        parse_probe=(probe_applicable if role == "parse-judge" else True),
        semantic_probe=(probe_applicable if role == "semantic-judge" else True),
        negative_probe=(probe_applicable if role == "negative-judge" else True),
    )
    return RoleSeparatedJudgeRequest(
        judge_role=role,
        task_id="task-001",
        planned_task_sha256=task_sha256,
        task_messages=messages,
        probe_applicable=probe_applicable,
        task_metadata=metadata,
        terminal=_terminal() if terminal is None else terminal,
        rubric_text=rubric,
        rubric_sha256=sha256_text(rubric),
        reference_text=reference,
        reference_sha256=sha256_text(reference),
        maximum_total_tokens=maximum_total_tokens,
    )


def _verdict_text(role: str, verdict: str) -> str:
    return canonical_json(
        {
            "schema_version": ROLE_SEPARATED_JUDGE_VERDICT_SCHEMA,
            "judge_role": role,
            "verdict": verdict,
        }
    )


def _reply(text: str, *, total_tokens: int = 12) -> ReceiverModelReply:
    return ReceiverModelReply(
        text=text,
        model_id=MODEL_ID,
        input_tokens=7,
        output_tokens=3,
        reasoning_tokens=total_tokens - 10,
        reasoning_accounting="separately-reported",
        provider_total_tokens=total_tokens,
    )


def _completed_capture(
    request: RoleSeparatedJudgeRequest,
    reply: ReceiverModelReply,
    *,
    request_mode: str | None = None,
    system_text: str | None = None,
    request_binding_sha256: str | None = None,
    settings_sha256: str = SETTINGS_SHA256,
    model_id: str = MODEL_ID,
) -> ProviderRequestCapture:
    actual_system = request.system_text if system_text is None else system_text
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="completed",
        request_binding_sha256=(
            request.binding_sha256
            if request_binding_sha256 is None
            else request_binding_sha256
        ),
        request_preimage_sha256=judge_request_preimage_sha256(request),
        request_mode=request.judge_role if request_mode is None else request_mode,
        request_dispatched=True,
        transmitted_system_text=actual_system,
        transmitted_user_text=request.user_text,
        transmitted_messages_sha256=provider_messages_sha256(
            actual_system,
            request.user_text,
        ),
        intended_model_visible_sha256=sha256_text(request.model_visible_text),
        model_id=model_id,
        settings_sha256=settings_sha256,
        provider_request_id="judge-request-001",
        provider_response_id="judge-response-001",
        provider_terminal_status="completed",
        reply_preimage_sha256=judge_reply_preimage_sha256(reply),
        attempt_count=1,
        retry_count=0,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        reasoning_tokens=reply.reasoning_tokens,
        reasoning_accounting=reply.reasoning_accounting,
        provider_total_tokens=reply.provider_total_tokens,
        usage_complete=True,
        raw_receipt_text=RECEIPT_TEXT,
        raw_receipt_sha256=RECEIPT_SHA256,
        failure_stage=None,
        failure_code=None,
    )


def _billed_failure_capture(
    request: RoleSeparatedJudgeRequest,
) -> ProviderRequestCapture:
    receipt = '{"id":"judge-request-failed","status":"provider_error"}'
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=request.binding_sha256,
        request_preimage_sha256=judge_request_preimage_sha256(request),
        request_mode=request.judge_role,
        request_dispatched=True,
        transmitted_system_text=request.system_text,
        transmitted_user_text=request.user_text,
        transmitted_messages_sha256=provider_messages_sha256(
            request.system_text,
            request.user_text,
        ),
        intended_model_visible_sha256=sha256_text(request.model_visible_text),
        model_id=MODEL_ID,
        settings_sha256=SETTINGS_SHA256,
        provider_request_id="judge-request-failed",
        provider_response_id="judge-error-001",
        provider_terminal_status="provider_error",
        reply_preimage_sha256=None,
        attempt_count=1,
        retry_count=0,
        input_tokens=7,
        output_tokens=0,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=7,
        usage_complete=True,
        raw_receipt_text=receipt,
        raw_receipt_sha256=sha256_text(receipt),
        failure_stage="provider",
        failure_code="judge-provider-call-failed",
    )


class CapturedJudgeTests(TestCase):
    def _execute(
        self,
        request: RoleSeparatedJudgeRequest,
        response: CapturedJudgeResponse,
    ):
        adapter = StaticJudgeAdapter(response)
        execution = execute_captured_judge(
            request,
            adapter,
            expected_model_id=MODEL_ID,
            expected_settings_sha256=SETTINGS_SHA256,
        )
        self.assertEqual(adapter.calls, 1)
        return execution

    def test_request_preimage_has_one_exact_bridge_shape_and_round_trips(self) -> None:
        for role in JUDGE_ROLES:
            with self.subTest(role=role):
                request = _request(role)
                request.validate()
                preimage = judge_request_preimage(request)
                self.assertEqual(
                    set(preimage),
                    {"schema_version", "request_binding_sha256", "request", "roles"},
                )
                self.assertEqual(preimage["schema_version"], JUDGE_REQUEST_PREIMAGE_SCHEMA)
                self.assertEqual(
                    set(preimage["request"]),
                    {
                        "schema_version",
                        "role",
                        "task_sha256",
                        "task_input_messages",
                        "task_metadata",
                        "probe_applicable",
                        "terminal_evidence",
                        "rubric",
                        "reference",
                        "maximum_total_tokens",
                    },
                )
                self.assertEqual(
                    preimage["request"]["schema_version"],
                    ROLE_SEPARATED_JUDGE_REQUEST_SCHEMA,
                )
                self.assertEqual(preimage["request"]["role"], role)
                self.assertEqual(
                    preimage["request"]["task_input_messages"],
                    [message.value for message in request.task_messages],
                )
                self.assertEqual(
                    preimage["request"]["task_metadata"],
                    request.task_metadata.value,
                )
                self.assertEqual(
                    set(preimage["request"]["terminal_evidence"]),
                    {
                        "schema_version",
                        "task_id",
                        "task_sha256",
                        "arm_id",
                        "selected_mode",
                        "terminal_kind",
                        "terminal_status",
                        "output_text",
                        "output_sha256",
                        "source_slot_id",
                        "source_component",
                        "source_disposition",
                        "source_record_sha256",
                        "source_capture_sha256",
                        "source_typed_execution_sha256",
                        "content_binding_verified",
                    },
                )
                self.assertEqual(
                    preimage["request"]["terminal_evidence"]["schema_version"],
                    PROGRAM_V2_TERMINAL_EVIDENCE_SCHEMA,
                )
                self.assertEqual(
                    preimage["request"]["terminal_evidence"],
                    request.terminal.value,
                )
                reply = _reply(_verdict_text(role, "pass"))
                execution = self._execute(
                    request,
                    CapturedJudgeResponse(_completed_capture(request, reply), reply),
                )
                execution.validate()
                self.assertEqual(execution.verdict_parse_status, "valid")

    def test_requests_and_nested_evidence_are_immutable_and_digest_bound(self) -> None:
        request = _request()
        with self.assertRaises(FrozenInstanceError):
            request.judge_role = "parse-judge"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.terminal.output_text = "substituted"  # type: ignore[misc]
        with self.assertRaises(JudgeError):
            replace(request, planned_task_sha256=sha256_text("another-task"))
        with self.assertRaises(JudgeError):
            replace(request, rubric_text="substituted")
        with self.assertRaises(JudgeError):
            replace(request, reference_text="substituted")

    def test_full_metadata_terminal_and_role_applicability_are_cross_bound(self) -> None:
        request = _request("parse-judge")
        with self.assertRaises(JudgeError):
            replace(
                request,
                task_metadata=replace(request.task_metadata, parse_probe=False),
            )
        with self.assertRaises(JudgeError):
            replace(
                request,
                task_metadata=replace(
                    request.task_metadata,
                    task_sha256=sha256_text("metadata-task-swap"),
                ),
            )
        with self.assertRaises(JudgeError):
            replace(
                request,
                terminal=replace(
                    request.terminal,
                    task_sha256=sha256_text("terminal-task-swap"),
                ),
            )
        with self.assertRaises(JudgeError):
            replace(request.terminal, content_binding_verified=False)
        with self.assertRaises(JudgeError):
            replace(request.terminal, schema_version="terminal-evidence/2")

    def test_task_judge_is_always_applicable(self) -> None:
        with self.assertRaises(JudgeError):
            _request("task-judge", probe_applicable=False)
        with self.assertRaises(JudgeError):
            parse_role_separated_judge_verdict(
                _verdict_text("task-judge", "not-applicable"),
                expected_role="task-judge",
                probe_applicable=True,
            )

    def test_probe_applicability_preserves_not_applicable_and_unknown(self) -> None:
        disabled = _request("negative-judge", probe_applicable=False)
        disabled_reply = _reply(_verdict_text("negative-judge", "not-applicable"))
        disabled_execution = self._execute(
            disabled,
            CapturedJudgeResponse(
                _completed_capture(disabled, disabled_reply),
                disabled_reply,
            ),
        )
        self.assertEqual(disabled_execution.verdict.verdict, "not-applicable")
        self.assertEqual(disabled_execution.verdict_parse_status, "valid")

        enabled = _request("semantic-judge")
        unknown_reply = _reply(_verdict_text("semantic-judge", "unknown"))
        unknown_execution = self._execute(
            enabled,
            CapturedJudgeResponse(
                _completed_capture(enabled, unknown_reply),
                unknown_reply,
            ),
        )
        self.assertEqual(unknown_execution.verdict.verdict, "unknown")

    def test_strict_parser_rejects_noncanonical_and_substituted_verdicts(self) -> None:
        valid = _verdict_text("parse-judge", "fail")
        parsed = parse_role_separated_judge_verdict(
            valid,
            expected_role="parse-judge",
            probe_applicable=True,
        )
        self.assertEqual(
            parsed.value,
            {
                "schema_version": ROLE_SEPARATED_JUDGE_VERDICT_SCHEMA,
                "judge_role": "parse-judge",
                "verdict": "fail",
            },
        )
        invalid = (
            valid.replace('"verdict":"fail"', '"verdict":"fail","verdict":"pass"'),
            valid.replace('"verdict":"fail"', '"verdict":NaN'),
            "```json\n" + valid + "\n```",
            valid + " trailing",
            valid[:-1] + ',"extra":false}',
            valid.replace("parse-judge", "semantic-judge"),
            valid.replace(ROLE_SEPARATED_JUDGE_VERDICT_SCHEMA, "judge-verdict/2"),
            '{ "judge_role":"parse-judge","schema_version":"'
            + ROLE_SEPARATED_JUDGE_VERDICT_SCHEMA
            + '","verdict":"fail"}',
        )
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(JudgeError):
                    parse_role_separated_judge_verdict(
                        text,
                        expected_role="parse-judge",
                        probe_applicable=True,
                    )

    def test_completed_execution_exposes_receiver_compatible_evidence(self) -> None:
        request = _request()
        reply = _reply(_verdict_text("task-judge", "pass"))
        capture = _completed_capture(request, reply)
        execution = self._execute(
            request,
            CapturedJudgeResponse(capture, reply),
        )
        execution.validate()
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.adapter_calls, 1)
        self.assertEqual(execution.provider_attempt_count, 1)
        self.assertEqual(execution.total_tokens, 12)
        self.assertTrue(execution.usage_complete)
        self.assertIsNot(execution.capture, capture)
        self.assertEqual(execution.capture, capture)
        self.assertIsNot(execution.reply, reply)
        self.assertEqual(execution.reply, reply)
        self.assertEqual(execution.verdict.verdict, "pass")
        self.assertEqual(execution.verdict_parse_status, "valid")
        self.assertEqual(execution.parse_status, "valid")
        self.assertIsNone(execution.failure)
        self.assertFalse(execution.provider_authenticity_verified)
        self.assertFalse(execution.claim_eligible)
        self.assertFalse(execution.goal_total_complete)
        self.assertTrue(execution.binding_sha256.startswith("sha256:"))

    def test_malformed_post_dispatch_verdict_retains_call_reply_and_cost(self) -> None:
        request = _request()
        reply = _reply("not-json")
        capture = _completed_capture(request, reply)
        execution = self._execute(
            request,
            CapturedJudgeResponse(capture, reply),
        )
        execution.validate()
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.provider_attempt_count, 1)
        self.assertEqual(execution.total_tokens, 12)
        self.assertTrue(execution.usage_complete)
        self.assertEqual(execution.capture, capture)
        self.assertEqual(execution.reply, reply)
        self.assertIsNone(execution.verdict)
        self.assertEqual(execution.verdict_parse_status, "invalid")
        self.assertEqual(execution.failure, "judge-verdict-invalid")

    def test_billed_provider_failure_retains_one_attempt_and_usage(self) -> None:
        request = _request()
        capture = _billed_failure_capture(request)
        execution = self._execute(
            request,
            CapturedJudgeResponse(capture, None),
        )
        execution.validate()
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.provider_attempt_count, 1)
        self.assertEqual(execution.total_tokens, 7)
        self.assertTrue(execution.usage_complete)
        self.assertEqual(execution.capture, capture)
        self.assertIsNone(execution.reply)
        self.assertIsNone(execution.verdict)
        self.assertEqual(execution.verdict_parse_status, "indeterminate")
        self.assertEqual(execution.failure, "judge-provider-call-failed")

    def test_retried_provider_capture_is_not_representable(self) -> None:
        request = _request()
        retried = replace(
            _billed_failure_capture(request),
            attempt_count=2,
            retry_count=1,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            reasoning_accounting=None,
            provider_total_tokens=None,
            usage_complete=False,
        )
        execution = self._execute(
            request,
            CapturedJudgeResponse(retried, None),
        )
        execution.validate()
        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)
        self.assertIsNone(execution.provider_attempt_count)

    def test_over_budget_completion_retains_reply_and_is_indeterminate(self) -> None:
        request = _request(maximum_total_tokens=11)
        reply = _reply(_verdict_text("task-judge", "pass"), total_tokens=12)
        capture = _completed_capture(request, reply)
        execution = self._execute(
            request,
            CapturedJudgeResponse(capture, reply),
        )
        execution.validate()
        self.assertEqual(execution.status, "budget-exceeded")
        self.assertEqual(execution.total_tokens, 12)
        self.assertEqual(execution.reply, reply)
        self.assertIsNone(execution.verdict)
        self.assertEqual(execution.verdict_parse_status, "indeterminate")
        self.assertEqual(execution.failure, "judge-token-budget-exceeded")

    def test_capture_role_message_model_or_settings_swap_fails_closed(self) -> None:
        request = _request()
        reply = _reply(_verdict_text("task-judge", "pass"))
        captures = (
            _completed_capture(request, reply, request_mode="parse-judge"),
            _completed_capture(request, reply, system_text="substituted system"),
            _completed_capture(request, reply, request_binding_sha256=sha256_text("swap")),
            _completed_capture(request, reply, settings_sha256=sha256_text("settings-swap")),
            _completed_capture(request, reply, model_id="judge-model-swap"),
        )
        for capture in captures:
            with self.subTest(capture=capture.request_mode):
                execution = self._execute(
                    request,
                    CapturedJudgeResponse(capture, reply),
                )
                execution.validate()
                self.assertEqual(execution.status, "capture-rejected")
                self.assertIsNone(execution.capture)
                self.assertEqual(execution.provider_attempt_count, None)
                self.assertFalse(execution.usage_complete)
                self.assertEqual(execution.verdict_parse_status, "indeterminate")

    def test_unbound_unresolved_terminal_is_lossless_and_forces_unknown(self) -> None:
        unresolved = JudgeTerminalEvidence(
            task_id="task-001",
            task_sha256=judge_task_input_sha256(_messages()),
            arm_id="raw-concise",
            selected_mode="raw",
            terminal_kind="unresolved",
            terminal_status=None,
            output_text=None,
            output_sha256=None,
            source_slot_id=None,
            source_component=None,
            source_disposition=None,
            source_record_sha256=None,
            source_capture_sha256=None,
            source_typed_execution_sha256=None,
            content_binding_verified=False,
        )
        request = _request(terminal=unresolved)
        self.assertEqual(request.terminal.value, unresolved.value)

        pass_reply = _reply(_verdict_text("task-judge", "pass"))
        invalid = self._execute(
            request,
            CapturedJudgeResponse(
                _completed_capture(request, pass_reply),
                pass_reply,
            ),
        )
        self.assertEqual(invalid.status, "completed")
        self.assertEqual(invalid.verdict_parse_status, "invalid")
        self.assertEqual(invalid.total_tokens, 12)

        unknown_reply = _reply(_verdict_text("task-judge", "unknown"))
        valid = self._execute(
            request,
            CapturedJudgeResponse(
                _completed_capture(request, unknown_reply),
                unknown_reply,
            ),
        )
        self.assertEqual(valid.verdict_parse_status, "valid")
        self.assertEqual(valid.verdict.verdict, "unknown")

    def test_execution_is_factory_sealed_against_dataclass_replace(self) -> None:
        request = _request()
        reply = _reply(_verdict_text("task-judge", "pass"))
        execution = self._execute(
            request,
            CapturedJudgeResponse(_completed_capture(request, reply), reply),
        )
        with self.assertRaises(JudgeError):
            replace(execution, verdict_parse_status="invalid")

    def test_reply_prohibited_effects_are_rejected_before_execution(self) -> None:
        with self.assertRaises(Exception):
            replace(
                _reply(_verdict_text("task-judge", "pass")),
                external_effects_performed=True,
            )


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
