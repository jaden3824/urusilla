from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from urusilla_hybrid_runtime.canonical import sha256_text
from urusilla_hybrid_runtime.comprehension import run_cold_start_comprehension
from urusilla_hybrid_runtime.receiver import ReceiverModelReply
from urusilla_hybrid_runtime.records import PublicActionState, load_capsule
from urusilla_hybrid_runtime.router import CostForecast, ReceiverCapabilities
from urusilla_hybrid_runtime.runtime import prepare_message
from urusilla_hybrid_runtime.session import (
    SessionState,
    SessionTurnCall,
    SessionTurnProviderReply,
)
from urusilla_hybrid_runtime.session_runtime import (
    SessionBoundPreparedMessage,
    SessionRuntimeError,
    bind_prepared_message_to_session,
    execute_session_bound_hybrid,
    mint_session_cached_receiver,
)
from urusilla_hybrid_runtime.tests.test_comprehension import (
    RECEIVER_BINDING,
    ScriptedAdapter,
    good_reply,
)
from urusilla_hybrid_runtime.tests.test_hybrid_runtime import (
    TASK_CONTEXT,
    FakeCompiler,
    FakeReceiverAdapter,
    action_policy,
    char_count,
    complete_forecasts,
    passing_evidence,
    receiver_reply,
    sender_output,
    validate_output,
    verify_fidelity,
    verify_utility,
)
from urusilla_hybrid_runtime.tests.test_session import (
    exact_turn_reply,
    new_session,
)
from urusilla_hybrid_runtime.sender import ModelReply


class OutputSessionAdapter:
    def __init__(self, text: str = "valid", *, failure: Exception | None = None):
        self.text = text
        self.failure = failure
        self.calls: list[SessionTurnCall] = []

    def complete_session_turn(
        self,
        raw_provider_handle: object,
        call: SessionTurnCall,
    ) -> SessionTurnProviderReply:
        self.calls.append(call)
        if self.failure is not None:
            raise self.failure
        base = exact_turn_reply(call)
        reply = replace(base.reply, text=self.text)
        receipts = replace(
            base.receipts,
            response_content_sha256=sha256_text(self.text),
        )
        return replace(base, reply=reply, receipts=receipts)


def _bound_plan():
    session, attempt, _ = new_session()
    capsule = load_capsule()
    cached = mint_session_cached_receiver(
        session,
        attempt,
        session.expected_observation(),
    )
    state = PublicActionState.from_object(
        capsule.to_object()["examples"]["positive"]
    )
    source = "Verify artifact seven without external effects. " * 800
    optimized = prepare_message(
        source,
        capsule,
        cached.capabilities,
        char_count,
        task_context=TASK_CONTEXT,
        forecasts=complete_forecasts(
            raw=CostForecast(
                cached_context_tokens=1,
                comprehension_setup_tokens=0,
                complete=True,
            ),
            json=CostForecast(
                cached_context_tokens=1,
                comprehension_setup_tokens=0,
                complete=True,
            ),
        ),
        evidence={
            "action-state": passing_evidence(
                capsule_sha256=capsule.sha256
            )
        },
        compiler=FakeCompiler(
            ModelReply(sender_output(state), "sender-model", 10)
        ),
        fidelity_verifier=verify_fidelity,
        policy=action_policy(),
        utility_evidence_verifier=verify_utility,
        capsule_comprehension_verifier=(
            cached.capsule_comprehension_verifier
        ),
        task_context_comprehension_verifier=(
            cached.task_context_comprehension_verifier
        ),
    )
    fallback = prepare_message(
        source,
        capsule,
        ReceiverCapabilities(),
        char_count,
        task_context=TASK_CONTEXT,
        forecasts=complete_forecasts(),
        policy=action_policy(),
    )
    if optimized.route.selected_mode != "action-state":
        raise AssertionError(
            {
                item.mode: item.reasons
                for item in optimized.route.candidates
            }
        )
    plan = bind_prepared_message_to_session(cached, optimized, fallback)
    return session, attempt, capsule, state, fallback, plan


class SessionCachedReceiverTests(TestCase):
    def test_cache_is_minted_only_from_passed_exact_live_context(self) -> None:
        session, attempt, _ = new_session()
        observed = session.expected_observation()
        cached = mint_session_cached_receiver(session, attempt, observed)

        self.assertTrue(cached.capabilities.capsule_cached_in_same_model_context)
        self.assertTrue(
            cached.capabilities.task_context_cached_in_same_model_context
        )
        self.assertEqual(
            cached.capabilities.capsule_context_id,
            cached.capabilities.task_context_id,
        )
        self.assertFalse(cached.capabilities.persistence_authorized)
        self.assertFalse(cached.capabilities.permission_expansion_authorized)
        self.assertFalse(cached.capabilities.spending_authorized)
        self.assertFalse(cached.capabilities.external_effects_authorized)

        with self.assertRaises(SessionRuntimeError):
            mint_session_cached_receiver(
                session,
                attempt,
                replace(observed, context_epoch="different-context"),
            )

        failed = run_cold_start_comprehension(
            load_capsule(),
            TASK_CONTEXT,
            RECEIVER_BINDING,
            ScriptedAdapter(
                lambda challenge: good_reply(challenge, text="{}")
            ),
            maximum_total_tokens=100,
        )
        self.assertFalse(failed.passed)
        with self.assertRaises(SessionRuntimeError):
            mint_session_cached_receiver(session, failed, observed)


class SessionBoundHybridTests(TestCase):
    def test_capsule_is_cold_once_and_hot_payload_is_direct_without_prose(self) -> None:
        session, attempt, capsule, state, fallback, plan = _bound_plan()
        primary = OutputSessionAdapter()
        baseline = FakeReceiverAdapter(receiver_reply())

        result = execute_session_bound_hybrid(
            attempt,
            fallback,
            baseline,
            plan=plan,
            session=session,
            observation=session.expected_observation(),
            session_adapter=primary,
            output_validator=validate_output,
        )

        self.assertEqual(
            attempt.challenge.model_visible_text.count(capsule.canonical_text),
            1,
        )
        self.assertIsInstance(plan, SessionBoundPreparedMessage)
        self.assertIsNone(plan.primary_request.capsule_text)
        self.assertFalse(plan.primary_request.capsule_included)
        self.assertFalse(plan.primary_request.task_context_included)
        self.assertIsNone(plan.primary_request.natural_language_expansion)
        self.assertFalse(plan.primary_request.decode_before_model)
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(
            primary.calls[0].request_text,
            "PAYLOAD\n" + state.canonical_text,
        )
        self.assertNotIn("PUBLIC TASK CONTEXT", primary.calls[0].request_text)
        self.assertNotIn("DECLARATIVE CAPSULE", primary.calls[0].request_text)
        self.assertEqual(baseline.calls, 0)
        self.assertEqual(result.status, "optimized-completed")
        self.assertTrue(result.safely_completed)
        self.assertEqual(result.receiver_calls, 1)
        self.assertIs(session.state, SessionState.ACTIVE)

    def test_malformed_action_state_never_reaches_session_adapter(self) -> None:
        session, attempt, _, _, fallback, plan = _bound_plan()
        primary = OutputSessionAdapter()
        baseline = FakeReceiverAdapter(receiver_reply())
        object.__setattr__(plan.primary_request, "payload_text", "{bad")

        result = execute_session_bound_hybrid(
            attempt,
            fallback,
            baseline,
            plan=plan,
            session=session,
            observation=session.expected_observation(),
            session_adapter=primary,
            output_validator=validate_output,
        )

        self.assertEqual(primary.calls, [])
        self.assertEqual(baseline.calls, 1)
        self.assertEqual(result.primary_calls, 0)
        self.assertEqual(result.fallback_calls, 1)
        self.assertEqual(result.status, "fallback-completed")
        self.assertTrue(result.safely_completed)
        self.assertEqual(
            result.optimized_failure,
            "session-primary-preflight-failed",
        )
        self.assertIs(session.state, SessionState.INVALIDATED)

    def test_wrong_primary_output_is_discarded_and_falls_back(self) -> None:
        session, attempt, _, _, fallback, plan = _bound_plan()
        primary = OutputSessionAdapter("constant-wrong-output")
        baseline = FakeReceiverAdapter(receiver_reply())

        result = execute_session_bound_hybrid(
            attempt,
            fallback,
            baseline,
            plan=plan,
            session=session,
            observation=session.expected_observation(),
            session_adapter=primary,
            output_validator=validate_output,
        )

        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(baseline.calls, 1)
        self.assertEqual(result.receiver_calls, 2)
        self.assertFalse(result.primary_output_valid)
        self.assertEqual(result.final_mode, fallback.route.selected_mode)
        self.assertEqual(result.status, "fallback-completed")
        self.assertTrue(result.safely_completed)
        self.assertIsNotNone(result.primary_reply)
        self.assertEqual(result.primary_reply.text, "constant-wrong-output")
        self.assertEqual(result.fallback_execution.reply.text, "valid")
        self.assertIs(session.state, SessionState.INVALIDATED)

    def test_context_mismatch_falls_back_before_session_adapter(self) -> None:
        session, attempt, _, _, fallback, plan = _bound_plan()
        primary = OutputSessionAdapter()
        baseline = FakeReceiverAdapter(receiver_reply())
        mismatched = replace(
            session.expected_observation(),
            context_epoch="different-context",
        )

        result = execute_session_bound_hybrid(
            attempt,
            fallback,
            baseline,
            plan=plan,
            session=session,
            observation=mismatched,
            session_adapter=primary,
            output_validator=validate_output,
        )

        self.assertEqual(primary.calls, [])
        self.assertEqual(baseline.calls, 1)
        self.assertEqual(result.receiver_calls, 1)
        self.assertEqual(result.status, "fallback-completed")
        self.assertTrue(result.safely_completed)
        self.assertIs(session.state, SessionState.INVALIDATED)

    def test_session_adapter_failure_is_counted_then_falls_back(self) -> None:
        session, attempt, _, _, fallback, plan = _bound_plan()
        primary = OutputSessionAdapter(failure=RuntimeError("provider failed"))
        baseline = FakeReceiverAdapter(receiver_reply())

        result = execute_session_bound_hybrid(
            attempt,
            fallback,
            baseline,
            plan=plan,
            session=session,
            observation=session.expected_observation(),
            session_adapter=primary,
            output_validator=validate_output,
        )

        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(baseline.calls, 1)
        self.assertEqual(result.primary_calls, 1)
        self.assertEqual(result.fallback_calls, 1)
        self.assertEqual(result.status, "fallback-completed")
        self.assertFalse(result.usage_complete)
        self.assertIs(session.state, SessionState.INVALIDATED)

    def test_failed_comprehension_executes_cold_fallback_without_hot_call(self) -> None:
        capsule = load_capsule()
        failed = run_cold_start_comprehension(
            capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            ScriptedAdapter(
                lambda challenge: good_reply(challenge, text="{}")
            ),
            maximum_total_tokens=100,
        )
        fallback = prepare_message(
            "Use the exact raw fallback after failed comprehension.",
            capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            policy=action_policy(),
        )
        baseline = FakeReceiverAdapter(receiver_reply())

        result = execute_session_bound_hybrid(
            failed,
            fallback,
            baseline,
            output_validator=validate_output,
        )

        self.assertFalse(failed.passed)
        self.assertEqual(result.primary_calls, 0)
        self.assertEqual(result.fallback_calls, 1)
        self.assertEqual(result.receiver_calls, 1)
        self.assertEqual(result.status, "fallback-completed")
        self.assertTrue(result.safely_completed)
        self.assertTrue(result.optimized_failure.startswith("comprehension:"))

    def test_boundary_attempt_cannot_become_live_and_uses_fallback(self) -> None:
        session, attempt, _, _, fallback, plan = _bound_plan()

        class BoundaryAdapter:
            def __init__(self) -> None:
                self.calls = 0

            def complete_session_turn(self, handle, call):
                self.calls += 1
                ReceiverModelReply(
                    text="valid",
                    model_id=call.lease.model_id,
                    input_tokens=1,
                    output_tokens=1,
                    reasoning_tokens=None,
                    reasoning_accounting="not-reported",
                    provider_total_tokens=2,
                    tools_used=True,
                )

        primary = BoundaryAdapter()
        baseline = FakeReceiverAdapter(receiver_reply())
        result = execute_session_bound_hybrid(
            attempt,
            fallback,
            baseline,
            plan=plan,
            session=session,
            observation=session.expected_observation(),
            session_adapter=primary,
            output_validator=validate_output,
        )

        self.assertEqual(primary.calls, 1)
        self.assertEqual(baseline.calls, 1)
        self.assertEqual(result.status, "fallback-completed")
        self.assertTrue(result.safely_completed)
        self.assertFalse(result.tools_used)
        self.assertFalse(result.persistence_created)
        self.assertFalse(result.permission_expanded)
        self.assertFalse(result.spending_authority_created)
        self.assertFalse(result.external_effects_performed)
        self.assertIs(session.state, SessionState.INVALIDATED)
