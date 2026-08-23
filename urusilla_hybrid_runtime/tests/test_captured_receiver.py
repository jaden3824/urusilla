"""Adversarial tests for the unauthenticated provider-capture boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from urusilla_hybrid_runtime.canonical import sha256_text
from urusilla_hybrid_runtime.captured_receiver import (
    PROVIDER_REQUEST_CAPTURE_SCHEMA,
    CapturedProviderResponse,
    ProviderRequestCapture,
    direct_receiver_request_preimage_sha256,
    execute_captured_receiver,
    provider_messages_sha256,
    receiver_model_reply_preimage,
    receiver_model_reply_preimage_sha256,
)
from urusilla_hybrid_runtime.errors import ReceiverError
from urusilla_hybrid_runtime.receiver import (
    ReceiverModelReply,
    build_raw_request,
)
from urusilla_hybrid_runtime.task_context import PublicTaskContext


REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_SHA256 = "sha256:" + "8" * 64
RECEIPT_TEXT = '{"id":"response-001","status":"completed"}'
RECEIPT_SHA256 = sha256_text(RECEIPT_TEXT)


class StaticCapturedAdapter:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete_captured(self, request):
        self.calls += 1
        return self.response


def _context() -> PublicTaskContext:
    return PublicTaskContext.from_json(
        (REPO_ROOT / "urusilla_task_context.example.json").read_text(
            encoding="utf-8"
        )
    )


def _request(source: str = "Return the public verification result."):
    return build_raw_request(
        source,
        _context(),
        maximum_total_tokens=100,
    )


def _reply(
    *,
    input_tokens: int = 10,
    output_tokens: int = 2,
    provider_total_tokens: int = 12,
) -> ReceiverModelReply:
    return ReceiverModelReply(
        text="failed",
        model_id="model-a",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=provider_total_tokens,
    )


def _completed_capture(
    request,
    reply: ReceiverModelReply,
    *,
    system_text: str | None = None,
    user_text: str | None = None,
    request_binding_sha256: str | None = None,
    request_preimage_sha256: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    provider_total_tokens: int | None = None,
) -> ProviderRequestCapture:
    actual_system = request.base_system_text if system_text is None else system_text
    actual_user = request.user_data_text if user_text is None else user_text
    capture_input = reply.input_tokens if input_tokens is None else input_tokens
    capture_output = reply.output_tokens if output_tokens is None else output_tokens
    capture_total = (
        reply.provider_total_tokens
        if provider_total_tokens is None
        else provider_total_tokens
    )
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="completed",
        request_binding_sha256=(
            request.binding_sha256
            if request_binding_sha256 is None
            else request_binding_sha256
        ),
        request_preimage_sha256=(
            direct_receiver_request_preimage_sha256(request)
            if request_preimage_sha256 is None
            else request_preimage_sha256
        ),
        request_mode=request.mode,
        request_dispatched=True,
        transmitted_system_text=actual_system,
        transmitted_user_text=actual_user,
        transmitted_messages_sha256=provider_messages_sha256(
            actual_system,
            actual_user,
        ),
        intended_model_visible_sha256=sha256_text(request.model_visible_text),
        model_id=reply.model_id,
        settings_sha256=SETTINGS_SHA256,
        provider_request_id="request-001",
        provider_response_id="response-001",
        provider_terminal_status="completed",
        reply_preimage_sha256=receiver_model_reply_preimage_sha256(reply),
        attempt_count=1,
        retry_count=0,
        input_tokens=capture_input,
        output_tokens=capture_output,
        reasoning_tokens=reply.reasoning_tokens,
        reasoning_accounting=reply.reasoning_accounting,
        provider_total_tokens=capture_total,
        usage_complete=True,
        raw_receipt_text=RECEIPT_TEXT,
        raw_receipt_sha256=RECEIPT_SHA256,
        failure_stage=None,
        failure_code=None,
    )


def _transport_failure_capture(request) -> ProviderRequestCapture:
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=request.binding_sha256,
        request_preimage_sha256=direct_receiver_request_preimage_sha256(request),
        request_mode=request.mode,
        request_dispatched=True,
        transmitted_system_text=request.base_system_text,
        transmitted_user_text=request.user_data_text,
        transmitted_messages_sha256=provider_messages_sha256(
            request.base_system_text,
            request.user_data_text,
        ),
        intended_model_visible_sha256=sha256_text(request.model_visible_text),
        model_id="model-a",
        settings_sha256=SETTINGS_SHA256,
        provider_request_id="request-failed",
        provider_response_id=None,
        provider_terminal_status="timeout",
        reply_preimage_sha256=None,
        attempt_count=2,
        retry_count=1,
        input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        reasoning_accounting=None,
        provider_total_tokens=None,
        usage_complete=False,
        raw_receipt_text=None,
        raw_receipt_sha256=None,
        failure_stage="transport",
        failure_code="provider-transport-failed",
    )


def _known_billed_failure_capture(request) -> ProviderRequestCapture:
    receipt = '{"id":"request-failed","status":"provider_error"}'
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=request.binding_sha256,
        request_preimage_sha256=direct_receiver_request_preimage_sha256(request),
        request_mode=request.mode,
        request_dispatched=True,
        transmitted_system_text=request.base_system_text,
        transmitted_user_text=request.user_data_text,
        transmitted_messages_sha256=provider_messages_sha256(
            request.base_system_text,
            request.user_data_text,
        ),
        intended_model_visible_sha256=sha256_text(request.model_visible_text),
        model_id="model-a",
        settings_sha256=SETTINGS_SHA256,
        provider_request_id="request-failed",
        provider_response_id="error-response-001",
        provider_terminal_status="provider_error",
        reply_preimage_sha256=None,
        attempt_count=1,
        retry_count=0,
        input_tokens=10,
        output_tokens=2,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=12,
        usage_complete=True,
        raw_receipt_text=receipt,
        raw_receipt_sha256=sha256_text(receipt),
        failure_stage="provider",
        failure_code="provider-call-failed",
    )


def _before_dispatch_failure_capture(request) -> ProviderRequestCapture:
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=request.binding_sha256,
        request_preimage_sha256=direct_receiver_request_preimage_sha256(request),
        request_mode=request.mode,
        request_dispatched=False,
        transmitted_system_text=None,
        transmitted_user_text=None,
        transmitted_messages_sha256=None,
        intended_model_visible_sha256=sha256_text(request.model_visible_text),
        model_id=None,
        settings_sha256=SETTINGS_SHA256,
        provider_request_id=None,
        provider_response_id=None,
        provider_terminal_status=None,
        reply_preimage_sha256=None,
        attempt_count=0,
        retry_count=0,
        input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        reasoning_accounting=None,
        provider_total_tokens=None,
        usage_complete=False,
        raw_receipt_text=None,
        raw_receipt_sha256=None,
        failure_stage="before-dispatch",
        failure_code="provider-request-not-dispatched",
    )


class CapturedReceiverTests(TestCase):
    def _execute(self, request, response):
        adapter = StaticCapturedAdapter(response)
        execution = execute_captured_receiver(
            request,
            adapter,
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )
        self.assertEqual(adapter.calls, 1)
        return execution

    def test_exact_role_separated_capture_completes_without_claim_authority(self) -> None:
        request = _request()
        reply = _reply()
        capture = _completed_capture(request, reply)

        execution = self._execute(
            request,
            CapturedProviderResponse(capture=capture, reply=reply),
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.total_tokens, 12)
        self.assertEqual(execution.adapter_calls, 1)
        self.assertEqual(execution.provider_attempt_count, 1)
        self.assertEqual(execution.capture.transmitted_system_text, request.base_system_text)
        self.assertEqual(execution.capture.transmitted_user_text, request.user_data_text)
        self.assertFalse(execution.provider_authenticity_verified)
        self.assertFalse(execution.claim_eligible)
        self.assertFalse(execution.goal_total_complete)

    def test_reply_preimage_binds_text_usage_and_every_boundary_field(self) -> None:
        reply = _reply()

        preimage = receiver_model_reply_preimage(reply)

        self.assertEqual(
            preimage["reply"],
            {
                "text": "failed",
                "model_id": "model-a",
                "input_tokens": 10,
                "output_tokens": 2,
                "reasoning_tokens": None,
                "reasoning_accounting": "not-reported",
                "provider_total_tokens": 12,
                "tools_used": False,
                "persistence_created": False,
                "permission_expanded": False,
                "spending_authority_created": False,
                "external_effects_performed": False,
            },
        )
        self.assertNotEqual(
            receiver_model_reply_preimage_sha256(reply),
            receiver_model_reply_preimage_sha256(
                replace(reply, text="a different provider reply")
            ),
        )

    def test_arbitrary_reply_substitution_is_rejected_after_adapter_call(self) -> None:
        request = _request()
        bound_reply = _reply()
        substituted_reply = replace(bound_reply, text="arbitrary substitution")
        capture = _completed_capture(request, bound_reply)

        execution = self._execute(
            request,
            CapturedProviderResponse(
                capture=capture,
                reply=substituted_reply,
            ),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)
        self.assertIsNone(execution.reply)
        self.assertFalse(execution.usage_complete)

    def test_adapter_side_prose_rewrite_is_rejected(self) -> None:
        request = _request()
        reply = _reply()
        rewritten = "Decoded prose that was not the direct payload."
        capture = _completed_capture(request, reply, user_text=rewritten)

        execution = self._execute(
            request,
            CapturedProviderResponse(capture=capture, reply=reply),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.reply)
        self.assertIsNone(execution.total_tokens)

    def test_usage_mismatch_between_reply_and_capture_is_rejected(self) -> None:
        request = _request()
        reply = _reply()
        capture = _completed_capture(
            request,
            reply,
            output_tokens=3,
            provider_total_tokens=13,
        )

        execution = self._execute(
            request,
            CapturedProviderResponse(capture=capture, reply=reply),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertFalse(execution.usage_complete)

    def test_cross_request_capture_replay_is_rejected(self) -> None:
        first = _request("First public request.")
        second = _request("Second public request.")
        reply = _reply()
        capture = _completed_capture(first, reply)

        execution = self._execute(
            second,
            CapturedProviderResponse(capture=capture, reply=reply),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)

    def test_failed_provider_attempt_preserves_unknown_usage(self) -> None:
        request = _request()
        capture = _transport_failure_capture(request)

        execution = self._execute(
            request,
            CapturedProviderResponse(capture=capture, reply=None),
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.failure, "provider-transport-failed")
        self.assertEqual(execution.capture.attempt_count, 2)
        self.assertEqual(execution.provider_attempt_count, 2)
        self.assertFalse(execution.usage_complete)
        self.assertIsNone(execution.total_tokens)

    def test_failed_single_attempt_preserves_complete_billed_usage(self) -> None:
        request = _request()
        capture = _known_billed_failure_capture(request)

        execution = self._execute(
            request,
            CapturedProviderResponse(capture=capture, reply=None),
        )

        self.assertEqual(execution.status, "failed")
        self.assertTrue(execution.usage_complete)
        self.assertEqual(execution.total_tokens, 12)
        self.assertEqual(execution.provider_attempt_count, 1)
        self.assertEqual(
            execution.capture.provider_terminal_status,
            "provider_error",
        )

    def test_failed_single_attempt_preserves_partial_usage_without_promoting_it(self) -> None:
        request = _request()
        capture = replace(
            _known_billed_failure_capture(request),
            output_tokens=None,
            reasoning_accounting=None,
            usage_complete=False,
        )

        execution = self._execute(
            request,
            CapturedProviderResponse(capture=capture, reply=None),
        )

        self.assertEqual(execution.status, "failed")
        self.assertFalse(execution.usage_complete)
        self.assertEqual(execution.capture.input_tokens, 10)
        self.assertEqual(execution.capture.provider_total_tokens, 12)
        self.assertIsNone(execution.total_tokens)

    def test_before_dispatch_failure_keeps_terminal_receipt_and_usage_unknown(self) -> None:
        request = _request()

        execution = self._execute(
            request,
            CapturedProviderResponse(
                capture=_before_dispatch_failure_capture(request),
                reply=None,
            ),
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.provider_attempt_count, 0)
        self.assertFalse(execution.usage_complete)
        self.assertIsNone(execution.capture.provider_terminal_status)
        self.assertIsNone(execution.capture.raw_receipt_text)
        self.assertIsNone(execution.total_tokens)

        with self.assertRaisesRegex(ReceiverError, "before-dispatch"):
            replace(
                _before_dispatch_failure_capture(request),
                provider_total_tokens=1,
            )

    def test_raw_receipt_text_and_digest_must_match(self) -> None:
        request = _request()
        reply = _reply()
        capture = _completed_capture(request, reply)

        with self.assertRaisesRegex(ReceiverError, "receipt digest differs"):
            replace(capture, raw_receipt_text="tampered receipt")

        with self.assertRaisesRegex(ReceiverError, "without its exact text"):
            replace(capture, raw_receipt_text=None)

    def test_completed_capture_rejects_retried_aggregate_usage(self) -> None:
        request = _request()
        reply = _reply()
        capture = _completed_capture(request, reply)

        with self.assertRaisesRegex(ReceiverError, "one unretried attempt"):
            replace(capture, attempt_count=2, retry_count=1)

    def test_adapter_request_mutation_is_rejected_before_reply_use(self) -> None:
        request = _request()
        reply = _reply()
        response = CapturedProviderResponse(
            capture=_completed_capture(request, reply),
            reply=reply,
        )

        class MutatingAdapter:
            def complete_captured(self, live_request):
                object.__setattr__(live_request, "payload_text", "mutated")
                return response

        execution = execute_captured_receiver(
            request,
            MutatingAdapter(),
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.reply)

    def test_capture_mutation_after_construction_is_revalidated(self) -> None:
        request = _request()
        reply = _reply()
        capture = _completed_capture(request, reply)
        response = CapturedProviderResponse(capture=capture, reply=reply)
        object.__setattr__(capture, "transmitted_user_text", "rewritten after seal")

        execution = self._execute(
            request,
            response,
        )

        self.assertEqual(execution.status, "capture-rejected")

    def test_post_return_capture_mutation_breaks_execution_validation(self) -> None:
        request = _request()
        reply = _reply()
        execution = self._execute(
            request,
            CapturedProviderResponse(
                capture=_completed_capture(request, reply),
                reply=reply,
            ),
        )
        assert execution.capture is not None
        object.__setattr__(execution.capture, "provider_total_tokens", 13)

        with self.assertRaisesRegex(ReceiverError, "differ"):
            execution.validate()
        with self.assertRaises(ReceiverError):
            _ = execution.total_tokens

    def test_post_return_receipt_mutation_breaks_execution_validation(self) -> None:
        request = _request()
        reply = _reply()
        execution = self._execute(
            request,
            CapturedProviderResponse(
                capture=_completed_capture(request, reply),
                reply=reply,
            ),
        )
        assert execution.capture is not None
        object.__setattr__(execution.capture, "raw_receipt_text", "mutated")

        with self.assertRaisesRegex(ReceiverError, "receipt digest differs"):
            execution.validate()

    def test_expected_model_and_settings_mutation_breaks_validation(self) -> None:
        request = _request()
        reply = _reply()

        for field_name, value, pattern in (
            ("expected_model_id", "model-b", "expected model"),
            (
                "expected_settings_sha256",
                "sha256:" + "7" * 64,
                "expected settings",
            ),
        ):
            with self.subTest(field_name=field_name):
                execution = self._execute(
                    request,
                    CapturedProviderResponse(
                        capture=_completed_capture(request, reply),
                        reply=reply,
                    ),
                )
                object.__setattr__(execution, field_name, value)
                with self.assertRaisesRegex(ReceiverError, pattern):
                    execution.validate()

    def test_post_return_execution_mutation_breaks_construction_seal(self) -> None:
        request = _request()
        reply = _reply()
        execution = self._execute(
            request,
            CapturedProviderResponse(
                capture=_completed_capture(request, reply),
                reply=reply,
            ),
        )
        object.__setattr__(execution, "status", "budget-exceeded")
        object.__setattr__(
            execution,
            "failure",
            "receiver-token-budget-exceeded",
        )

        with self.assertRaisesRegex(ReceiverError, "construction seal"):
            execution.validate()
        with self.assertRaises(ReceiverError):
            _ = execution.binding_sha256

    def test_cross_wired_capture_and_reply_fail_the_original_execution_seal(self) -> None:
        request = _request()
        first_reply = _reply()
        second_reply = replace(first_reply, text="another valid provider reply")
        first = self._execute(
            request,
            CapturedProviderResponse(
                capture=_completed_capture(request, first_reply),
                reply=first_reply,
            ),
        )
        second = self._execute(
            request,
            CapturedProviderResponse(
                capture=_completed_capture(request, second_reply),
                reply=second_reply,
            ),
        )

        with self.assertRaisesRegex(ReceiverError, "construction seal"):
            replace(first, capture=second.capture, reply=second.reply)

    def test_adapter_exception_keeps_provider_usage_unknown(self) -> None:
        request = _request()

        class FailingAdapter:
            def complete_captured(self, _request):
                raise RuntimeError("provider unavailable")

        execution = execute_captured_receiver(
            request,
            FailingAdapter(),
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.failure, "captured-adapter-call-failed")
        self.assertEqual(execution.adapter_calls, 1)
        self.assertIsNone(execution.provider_attempt_count)
        self.assertIsNone(execution.capture)
        self.assertIsNone(execution.total_tokens)

    def test_adapter_mutation_then_exception_is_capture_rejected(self) -> None:
        request = _request()

        class MutatingFailingAdapter:
            def complete_captured(self, live_request):
                object.__setattr__(live_request, "payload_text", "mutated")
                raise RuntimeError("provider unavailable")

        execution = execute_captured_receiver(
            request,
            MutatingFailingAdapter(),
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertEqual(execution.failure, "captured-adapter-mutated-request")
        self.assertIsNone(execution.total_tokens)


if __name__ == "__main__":
    import unittest

    unittest.main()
