"""Adversarial tests for provider-captured sender compilation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from urusilla_hybrid_runtime.canonical import sha256_text
from urusilla_hybrid_runtime.captured_compiler import (
    COMPILER_REQUEST_MODE,
    CapturedCompilerResponse,
    compiler_reply_preimage,
    compiler_reply_preimage_sha256,
    execute_captured_compiler,
    sender_prompt_binding_sha256,
    sender_prompt_preimage,
    sender_prompt_preimage_sha256,
)
from urusilla_hybrid_runtime.captured_receiver import (
    PROVIDER_REQUEST_CAPTURE_SCHEMA,
    ProviderRequestCapture,
    provider_messages_sha256,
)
from urusilla_hybrid_runtime.errors import ReceiverError, SenderError
from urusilla_hybrid_runtime.records import load_capsule
from urusilla_hybrid_runtime.sender import ModelReply, build_sender_prompt
from urusilla_hybrid_runtime.task_context import PublicTaskContext


REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_SHA256 = "sha256:" + "8" * 64
RECEIPT_TEXT = '{"id":"compiler-response-001","status":"completed"}'
RECEIPT_SHA256 = sha256_text(RECEIPT_TEXT)


class StaticCapturedAdapter:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete_captured(self, prompt):
        self.calls += 1
        return self.response


def _context() -> PublicTaskContext:
    return PublicTaskContext.from_json(
        (REPO_ROOT / "urusilla_task_context.example.json").read_text(
            encoding="utf-8"
        )
    )


def _prompt(
    source: str = "Return the bounded public action state.",
    *,
    maximum_total_tokens: int = 100,
):
    return build_sender_prompt(
        source,
        load_capsule(REPO_ROOT / "urusilla_action_state_capsule.json"),
        task_context=_context(),
        maximum_total_tokens=maximum_total_tokens,
    )


def _reply(
    *,
    text: str = (
        '{"candidates":[],"failure":"bounded","status":"failed",'
        '"unsupported":[]}'
    ),
    total_tokens: int = 12,
) -> ModelReply:
    return ModelReply(
        text=text,
        model_id="model-a",
        total_tokens=total_tokens,
    )


def _completed_capture(
    prompt,
    reply: ModelReply,
    *,
    system_text: str | None = None,
    user_text: str | None = None,
    request_binding_sha256: str | None = None,
    request_preimage_sha256: str | None = None,
    provider_total_tokens: int | None = None,
    reply_preimage_sha256: str | None = None,
    model_id: str | None = None,
    settings_sha256: str = SETTINGS_SHA256,
) -> ProviderRequestCapture:
    actual_system = prompt.system_text if system_text is None else system_text
    actual_user = prompt.user_text if user_text is None else user_text
    total = reply.total_tokens if provider_total_tokens is None else provider_total_tokens
    assert total is not None
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="completed",
        request_binding_sha256=(
            sender_prompt_binding_sha256(prompt)
            if request_binding_sha256 is None
            else request_binding_sha256
        ),
        request_preimage_sha256=(
            sender_prompt_preimage_sha256(prompt)
            if request_preimage_sha256 is None
            else request_preimage_sha256
        ),
        request_mode=COMPILER_REQUEST_MODE,
        request_dispatched=True,
        transmitted_system_text=actual_system,
        transmitted_user_text=actual_user,
        transmitted_messages_sha256=provider_messages_sha256(
            actual_system,
            actual_user,
        ),
        intended_model_visible_sha256=sha256_text(prompt.model_visible_text),
        model_id=reply.model_id if model_id is None else model_id,
        settings_sha256=settings_sha256,
        provider_request_id="compiler-request-001",
        provider_response_id="compiler-response-001",
        provider_terminal_status="completed",
        reply_preimage_sha256=(
            compiler_reply_preimage_sha256(reply)
            if reply_preimage_sha256 is None
            else reply_preimage_sha256
        ),
        attempt_count=1,
        retry_count=0,
        input_tokens=10,
        output_tokens=2,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=total,
        usage_complete=True,
        raw_receipt_text=RECEIPT_TEXT,
        raw_receipt_sha256=RECEIPT_SHA256,
        failure_stage=None,
        failure_code=None,
    )


def _transport_failure_capture(
    prompt,
    *,
    attempt_count: int = 1,
    retry_count: int = 0,
) -> ProviderRequestCapture:
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=sender_prompt_binding_sha256(prompt),
        request_preimage_sha256=sender_prompt_preimage_sha256(prompt),
        request_mode=COMPILER_REQUEST_MODE,
        request_dispatched=True,
        transmitted_system_text=prompt.system_text,
        transmitted_user_text=prompt.user_text,
        transmitted_messages_sha256=provider_messages_sha256(
            prompt.system_text,
            prompt.user_text,
        ),
        intended_model_visible_sha256=sha256_text(prompt.model_visible_text),
        model_id="model-a",
        settings_sha256=SETTINGS_SHA256,
        provider_request_id="compiler-request-failed",
        provider_response_id=None,
        provider_terminal_status="timeout",
        reply_preimage_sha256=None,
        attempt_count=attempt_count,
        retry_count=retry_count,
        input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        reasoning_accounting=None,
        provider_total_tokens=None,
        usage_complete=False,
        raw_receipt_text=None,
        raw_receipt_sha256=None,
        failure_stage="transport",
        failure_code="compiler-transport-failed",
    )


def _known_billed_failure_capture(prompt) -> ProviderRequestCapture:
    receipt = '{"id":"compiler-request-failed","status":"provider_error"}'
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=sender_prompt_binding_sha256(prompt),
        request_preimage_sha256=sender_prompt_preimage_sha256(prompt),
        request_mode=COMPILER_REQUEST_MODE,
        request_dispatched=True,
        transmitted_system_text=prompt.system_text,
        transmitted_user_text=prompt.user_text,
        transmitted_messages_sha256=provider_messages_sha256(
            prompt.system_text,
            prompt.user_text,
        ),
        intended_model_visible_sha256=sha256_text(prompt.model_visible_text),
        model_id="model-a",
        settings_sha256=SETTINGS_SHA256,
        provider_request_id="compiler-request-failed",
        provider_response_id="compiler-error-response-001",
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
        failure_code="compiler-provider-call-failed",
    )


def _before_dispatch_failure_capture(prompt) -> ProviderRequestCapture:
    return ProviderRequestCapture(
        schema_version=PROVIDER_REQUEST_CAPTURE_SCHEMA,
        status="failed",
        request_binding_sha256=sender_prompt_binding_sha256(prompt),
        request_preimage_sha256=sender_prompt_preimage_sha256(prompt),
        request_mode=COMPILER_REQUEST_MODE,
        request_dispatched=False,
        transmitted_system_text=None,
        transmitted_user_text=None,
        transmitted_messages_sha256=None,
        intended_model_visible_sha256=sha256_text(prompt.model_visible_text),
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
        failure_code="compiler-request-not-dispatched",
    )


class CapturedCompilerTests(TestCase):
    def _execute(self, prompt, response):
        adapter = StaticCapturedAdapter(response)
        execution = execute_captured_compiler(
            prompt,
            adapter,
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )
        self.assertEqual(adapter.calls, 1)
        return execution

    def test_exact_roles_complete_without_claim_authority(self) -> None:
        prompt = _prompt()
        reply = _reply()

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply),
                reply=reply,
            ),
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.total_tokens, 12)
        self.assertEqual(execution.adapter_calls, 1)
        self.assertEqual(execution.provider_attempt_count, 1)
        assert execution.capture is not None
        self.assertEqual(execution.capture.transmitted_system_text, prompt.system_text)
        self.assertEqual(execution.capture.transmitted_user_text, prompt.user_text)
        self.assertFalse(execution.provider_authenticity_verified)
        self.assertFalse(execution.claim_eligible)
        self.assertFalse(execution.goal_total_complete)
        self.assertFalse(execution.capture.provider_authenticity_verified)
        self.assertFalse(execution.capture.claim_eligible)

    def test_prompt_and_reply_preimages_bind_every_public_field(self) -> None:
        prompt = _prompt()
        reply = _reply()

        prompt_value = sender_prompt_preimage(prompt)
        reply_value = compiler_reply_preimage(reply)

        self.assertEqual(prompt_value["roles"]["system"], prompt.system_text)
        self.assertEqual(prompt_value["roles"]["user"], prompt.user_text)
        self.assertEqual(prompt_value["prompt"]["source_sha256"], prompt.source_sha256)
        self.assertEqual(
            reply_value["reply"],
            {"text": reply.text, "model_id": "model-a", "total_tokens": 12},
        )
        self.assertNotEqual(
            sender_prompt_preimage_sha256(prompt),
            sender_prompt_preimage_sha256(
                replace(prompt, maximum_total_tokens=101)
            ),
        )
        self.assertNotEqual(
            compiler_reply_preimage_sha256(reply),
            compiler_reply_preimage_sha256(replace(reply, text="different")),
        )

    def test_arbitrary_reply_substitution_is_rejected(self) -> None:
        prompt = _prompt()
        bound_reply = _reply()
        substituted = replace(bound_reply, text="arbitrary substitution")

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, bound_reply),
                reply=substituted,
            ),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)
        self.assertIsNone(execution.reply)
        self.assertIsNone(execution.total_tokens)

    def test_adapter_side_prompt_rewrite_is_rejected(self) -> None:
        prompt = _prompt()
        reply = _reply()
        capture = _completed_capture(
            prompt,
            reply,
            user_text="rewritten provider user message",
        )

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(capture=capture, reply=reply),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)

    def test_capture_and_reply_total_usage_must_reconcile(self) -> None:
        prompt = _prompt()
        reply = _reply(total_tokens=12)
        capture = _completed_capture(prompt, reply, provider_total_tokens=13)

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(capture=capture, reply=reply),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertFalse(execution.usage_complete)

    def test_cross_prompt_capture_replay_is_rejected(self) -> None:
        first = _prompt("First source instruction.")
        second = _prompt("Second source instruction.")
        reply = _reply()

        execution = self._execute(
            second,
            CapturedCompilerResponse(
                capture=_completed_capture(first, reply),
                reply=reply,
            ),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)

    def test_one_failed_provider_attempt_preserves_unknown_usage(self) -> None:
        prompt = _prompt()

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_transport_failure_capture(prompt),
                reply=None,
            ),
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.failure, "compiler-transport-failed")
        self.assertFalse(execution.usage_complete)
        self.assertIsNone(execution.total_tokens)

    def test_failed_single_attempt_preserves_complete_billed_usage(self) -> None:
        prompt = _prompt()

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_known_billed_failure_capture(prompt),
                reply=None,
            ),
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
        prompt = _prompt()
        capture = replace(
            _known_billed_failure_capture(prompt),
            output_tokens=None,
            reasoning_accounting=None,
            usage_complete=False,
        )

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(capture=capture, reply=None),
        )

        self.assertEqual(execution.status, "failed")
        self.assertFalse(execution.usage_complete)
        self.assertEqual(execution.capture.input_tokens, 10)
        self.assertEqual(execution.capture.provider_total_tokens, 12)
        self.assertIsNone(execution.total_tokens)

    def test_before_dispatch_failure_keeps_terminal_receipt_and_usage_unknown(self) -> None:
        prompt = _prompt()

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_before_dispatch_failure_capture(prompt),
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
                _before_dispatch_failure_capture(prompt),
                input_tokens=1,
            )

    def test_raw_receipt_text_and_digest_must_match(self) -> None:
        prompt = _prompt()
        reply = _reply()
        capture = _completed_capture(prompt, reply)

        with self.assertRaisesRegex(ReceiverError, "receipt digest differs"):
            replace(capture, raw_receipt_text="tampered receipt")

        with self.assertRaisesRegex(ReceiverError, "without its exact text"):
            replace(capture, raw_receipt_text=None)

    def test_retry_aggregate_is_capture_rejected(self) -> None:
        prompt = _prompt()
        capture = _transport_failure_capture(
            prompt,
            attempt_count=2,
            retry_count=1,
        )

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(capture=capture, reply=None),
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.capture)

    def test_adapter_prompt_mutation_is_rejected_before_reply_use(self) -> None:
        prompt = _prompt()
        reply = _reply()
        response = CapturedCompilerResponse(
            capture=_completed_capture(prompt, reply),
            reply=reply,
        )

        class MutatingAdapter:
            def complete_captured(self, live_prompt):
                object.__setattr__(live_prompt, "user_text", "mutated")
                return response

        execution = execute_captured_compiler(
            prompt,
            MutatingAdapter(),
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertIsNone(execution.reply)

    def test_capture_mutation_after_response_construction_is_rejected(self) -> None:
        prompt = _prompt()
        reply = _reply()
        capture = _completed_capture(prompt, reply)
        response = CapturedCompilerResponse(capture=capture, reply=reply)
        object.__setattr__(capture, "transmitted_user_text", "mutated after seal")

        execution = self._execute(prompt, response)

        self.assertEqual(execution.status, "capture-rejected")

    def test_reply_mutation_after_response_construction_is_rejected(self) -> None:
        prompt = _prompt()
        reply = _reply()
        response = CapturedCompilerResponse(
            capture=_completed_capture(prompt, reply),
            reply=reply,
        )
        object.__setattr__(reply, "text", "mutated after response construction")

        execution = self._execute(prompt, response)

        self.assertEqual(execution.status, "capture-rejected")

    def test_post_return_capture_mutation_breaks_execution_validation(self) -> None:
        prompt = _prompt()
        reply = _reply()
        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply),
                reply=reply,
            ),
        )
        assert execution.capture is not None
        object.__setattr__(execution.capture, "provider_total_tokens", 13)

        with self.assertRaises(SenderError):
            execution.validate()
        with self.assertRaises(SenderError):
            _ = execution.total_tokens

    def test_post_return_receipt_mutation_breaks_execution_validation(self) -> None:
        prompt = _prompt()
        reply = _reply()
        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply),
                reply=reply,
            ),
        )
        assert execution.capture is not None
        object.__setattr__(execution.capture, "raw_receipt_text", "mutated")

        with self.assertRaises(SenderError):
            execution.validate()

    def test_expected_model_and_settings_mutation_breaks_validation(self) -> None:
        prompt = _prompt()
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
                    prompt,
                    CapturedCompilerResponse(
                        capture=_completed_capture(prompt, reply),
                        reply=reply,
                    ),
                )
                object.__setattr__(execution, field_name, value)
                with self.assertRaisesRegex(SenderError, pattern):
                    execution.validate()

    def test_post_return_reply_mutation_breaks_execution_validation(self) -> None:
        prompt = _prompt()
        reply = _reply()
        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply),
                reply=reply,
            ),
        )
        assert execution.reply is not None
        object.__setattr__(execution.reply, "text", "mutated after execution")

        with self.assertRaises(SenderError):
            execution.validate()
        with self.assertRaises(SenderError):
            _ = execution.binding_sha256

    def test_execution_mutation_breaks_construction_seal(self) -> None:
        prompt = _prompt()
        reply = _reply()
        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply),
                reply=reply,
            ),
        )
        object.__setattr__(execution, "status", "budget-exceeded")
        object.__setattr__(execution, "failure", "compiler-token-budget-exceeded")

        with self.assertRaisesRegex(SenderError, "construction seal"):
            execution.validate()
        with self.assertRaises(SenderError):
            _ = execution.binding_sha256

    def test_cross_wired_capture_and_reply_break_original_execution_seal(self) -> None:
        prompt = _prompt()
        first_reply = _reply(text="first")
        second_reply = _reply(text="second")
        first = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, first_reply),
                reply=first_reply,
            ),
        )
        second = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, second_reply),
                reply=second_reply,
            ),
        )

        with self.assertRaisesRegex(SenderError, "construction seal"):
            replace(first, capture=second.capture, reply=second.reply)

    def test_adapter_exception_preserves_unknown_usage(self) -> None:
        prompt = _prompt()

        class FailingAdapter:
            def complete_captured(self, _prompt):
                raise RuntimeError("provider unavailable")

        execution = execute_captured_compiler(
            prompt,
            FailingAdapter(),
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.failure, "captured-compiler-adapter-call-failed")
        self.assertEqual(execution.adapter_calls, 1)
        self.assertIsNone(execution.provider_attempt_count)
        self.assertIsNone(execution.capture)
        self.assertIsNone(execution.total_tokens)

    def test_adapter_mutation_then_exception_is_capture_rejected(self) -> None:
        prompt = _prompt()

        class MutatingFailingAdapter:
            def complete_captured(self, live_prompt):
                object.__setattr__(live_prompt, "user_text", "mutated")
                raise RuntimeError("provider unavailable")

        execution = execute_captured_compiler(
            prompt,
            MutatingFailingAdapter(),
            expected_model_id="model-a",
            expected_settings_sha256=SETTINGS_SHA256,
        )

        self.assertEqual(execution.status, "capture-rejected")
        self.assertEqual(
            execution.failure,
            "captured-compiler-adapter-mutated-prompt",
        )
        self.assertIsNone(execution.total_tokens)

    def test_budget_excess_is_observed_but_never_claim_eligible(self) -> None:
        prompt = _prompt(maximum_total_tokens=11)
        reply = _reply(total_tokens=12)

        execution = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply),
                reply=reply,
            ),
        )

        self.assertEqual(execution.status, "budget-exceeded")
        self.assertEqual(execution.total_tokens, 12)
        self.assertFalse(execution.claim_eligible)

    def test_effect_and_authentication_claims_are_rejected_at_capture_boundary(self) -> None:
        prompt = _prompt()
        reply = _reply()
        capture = _completed_capture(prompt, reply)

        for field_name in (
            "tools_used",
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
            "provider_authenticity_verified",
            "claim_eligible",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ReceiverError):
                    replace(capture, **{field_name: True})

    def test_expected_model_and_settings_must_match_capture(self) -> None:
        prompt = _prompt()
        reply = _reply()

        wrong_model = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(prompt, reply, model_id="model-b"),
                reply=reply,
            ),
        )
        wrong_settings = self._execute(
            prompt,
            CapturedCompilerResponse(
                capture=_completed_capture(
                    prompt,
                    reply,
                    settings_sha256="sha256:" + "7" * 64,
                ),
                reply=reply,
            ),
        )

        self.assertEqual(wrong_model.status, "capture-rejected")
        self.assertEqual(wrong_settings.status, "capture-rejected")


if __name__ == "__main__":
    import unittest

    unittest.main()
