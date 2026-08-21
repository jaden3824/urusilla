from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.comprehension import run_cold_start_comprehension
from urusilla_hybrid_runtime.receiver import ReceiverModelReply
from urusilla_hybrid_runtime.records import load_capsule
from urusilla_hybrid_runtime.session import (
    ProviderReceiptBinding,
    SessionError,
    SessionState,
    SessionTurnCall,
    SessionTurnProviderReply,
    close_receiver_session,
    execute_session_turn,
    open_receiver_session,
    prepare_session_turn,
)
from urusilla_hybrid_runtime.tests.test_comprehension import (
    RECEIVER_BINDING,
    ScriptedAdapter,
    good_reply,
)
from urusilla_hybrid_runtime.tests.test_hybrid_runtime import TASK_CONTEXT


def digest(label: str) -> str:
    return sha256_text(label)


def passed_attempt():
    return run_cold_start_comprehension(
        load_capsule(),
        TASK_CONTEXT,
        RECEIVER_BINDING,
        ScriptedAdapter(lambda challenge: good_reply(challenge)),
        maximum_total_tokens=100,
    )


def opening_receipts(attempt) -> ProviderReceiptBinding:
    assert attempt.output_sha256 is not None
    return ProviderReceiptBinding(
        request_content_sha256=attempt.challenge.model_visible_sha256,
        response_content_sha256=attempt.output_sha256,
        provider_request_receipt_sha256=digest("opening-request-receipt"),
        provider_response_receipt_sha256=digest("opening-response-receipt"),
        provider_context_receipt_sha256=digest("opening-context-receipt"),
    )


class SecretHandle:
    def __repr__(self) -> str:
        return "SUPER-SECRET-PROVIDER-HANDLE"


def new_session(*, handle: object | None = None):
    attempt = passed_attempt()
    actual_handle = SecretHandle() if handle is None else handle
    session = open_receiver_session(
        attempt,
        raw_provider_handle=actual_handle,
        context_epoch="provider-context-epoch-1",
        session_nonce="a" * 64,
        opening_receipts=opening_receipts(attempt),
    )
    return session, attempt, actual_handle


def exact_turn_reply(call: SessionTurnCall) -> SessionTurnProviderReply:
    response_text = canonical_json(
        {"accepted": True, "turn": call.lease.turn}
    )
    return SessionTurnProviderReply(
        reply=ReceiverModelReply(
            text=response_text,
            model_id=call.lease.model_id,
            input_tokens=9,
            output_tokens=6,
            reasoning_tokens=None,
            reasoning_accounting="not-reported",
            provider_total_tokens=15,
        ),
        model_settings_sha256=call.lease.model_settings_sha256,
        system_sha256=call.lease.system_sha256,
        context_epoch=call.lease.context_epoch,
        lease_sha256=call.lease.sha256,
        turn=call.lease.turn,
        parent_transcript_chain_sha256=(
            call.lease.parent_transcript_chain_sha256
        ),
        receipts=ProviderReceiptBinding(
            request_content_sha256=call.lease.request_sha256,
            response_content_sha256=sha256_text(response_text),
            provider_request_receipt_sha256=digest(
                f"request-receipt-{call.lease.turn}"
            ),
            provider_response_receipt_sha256=digest(
                f"response-receipt-{call.lease.turn}"
            ),
            provider_context_receipt_sha256=digest(
                f"context-receipt-{call.lease.turn}"
            ),
        ),
    )


class SessionAdapter:
    def __init__(self, mutate=None) -> None:
        self.mutate = mutate
        self.calls: list[SessionTurnCall] = []
        self.handles: list[object] = []

    def complete_session_turn(self, handle, call):
        self.handles.append(handle)
        self.calls.append(call)
        reply = exact_turn_reply(call)
        return reply if self.mutate is None else self.mutate(reply, call)


class SessionOpeningTests(TestCase):
    def test_open_has_exact_transition_bindings_and_private_handle(self) -> None:
        session, attempt, handle = new_session()
        snapshot = session.snapshot()

        self.assertIs(session.state, SessionState.ACTIVE)
        self.assertEqual(
            snapshot.state_history,
            (
                SessionState.NEW,
                SessionState.OPENING,
                SessionState.ACTIVE,
            ),
        )
        self.assertEqual(snapshot.model_id, RECEIVER_BINDING.model_id)
        self.assertEqual(
            snapshot.model_settings_sha256,
            RECEIVER_BINDING.settings_sha256,
        )
        self.assertEqual(
            snapshot.system_sha256,
            sha256_text(attempt.challenge.system_text),
        )
        self.assertEqual(
            snapshot.capsule_sha256,
            attempt.evidence.capsule_sha256,
        )
        self.assertEqual(
            snapshot.task_context_sha256,
            attempt.evidence.task_context_sha256,
        )
        self.assertEqual(snapshot.next_turn, 1)
        self.assertFalse(snapshot.provider_receipt_authenticity_verified)
        self.assertNotIn("SUPER-SECRET-PROVIDER-HANDLE", repr(session))
        self.assertNotIn("SUPER-SECRET-PROVIDER-HANDLE", snapshot.canonical_text)
        self.assertFalse(hasattr(session, "raw_provider_handle"))

        adapter = SessionAdapter()
        lease = prepare_session_turn(
            session,
            "bounded task data",
            maximum_total_tokens=20,
            observation=session.expected_observation(),
        )
        self.assertNotIn("SUPER-SECRET-PROVIDER-HANDLE", lease.canonical_text)
        execute_session_turn(session, lease, adapter)
        self.assertIs(adapter.handles[0], handle)

    def test_open_rejects_failed_attempt_or_mismatched_receipts(self) -> None:
        attempt = run_cold_start_comprehension(
            load_capsule(),
            TASK_CONTEXT,
            RECEIVER_BINDING,
            ScriptedAdapter(
                lambda challenge: good_reply(challenge, text="{}")
            ),
            maximum_total_tokens=100,
        )
        self.assertFalse(attempt.passed)
        with self.assertRaises(SessionError):
            open_receiver_session(
                attempt,
                raw_provider_handle=object(),
                context_epoch="epoch-1",
                session_nonce="a" * 64,
                opening_receipts=ProviderReceiptBinding(
                    request_content_sha256=digest("request"),
                    response_content_sha256=digest("response"),
                    provider_request_receipt_sha256=digest("prr"),
                    provider_response_receipt_sha256=digest("prs"),
                    provider_context_receipt_sha256=digest("pcr"),
                ),
            )

        passed = passed_attempt()
        wrong = replace(
            opening_receipts(passed),
            request_content_sha256=digest("wrong-request"),
        )
        with self.assertRaises(SessionError):
            open_receiver_session(
                passed,
                raw_provider_handle=object(),
                context_epoch="epoch-1",
                session_nonce="a" * 64,
                opening_receipts=wrong,
            )


class SessionLifecycleTests(TestCase):
    def test_three_five_and_ten_turn_ledgers_charge_setup_once(self) -> None:
        for turn_count in (3, 5, 10):
            with self.subTest(turn_count=turn_count):
                session, attempt, _ = new_session()
                adapter = SessionAdapter()
                chains = {session.snapshot().transcript_chain_sha256}
                for turn in range(1, turn_count + 1):
                    lease = prepare_session_turn(
                        session,
                        f"task-{turn}",
                        maximum_total_tokens=20,
                        observation=session.expected_observation(),
                    )
                    self.assertEqual(lease.turn, turn)
                    result = execute_session_turn(session, lease, adapter)
                    self.assertFalse(result.performance_claim_eligible)
                    chains.add(result.transcript_chain_sha256)

                snapshot = session.snapshot()
                self.assertEqual(snapshot.next_turn, turn_count + 1)
                self.assertEqual(len(chains), turn_count + 1)
                self.assertEqual(snapshot.cost.setup_charge_count, 1)
                self.assertEqual(
                    snapshot.cost.setup_provider_reported_tokens,
                    attempt.evidence.provider_total_tokens,
                )
                self.assertEqual(
                    snapshot.cost.turn_provider_reported_tokens,
                    (15,) * turn_count,
                )
                self.assertEqual(
                    snapshot.cost.reported_call_total_tokens,
                    attempt.evidence.provider_total_tokens + 15 * turn_count,
                )
                self.assertIsNone(
                    snapshot.cost.provider_full_history_billing_tokens
                )
                self.assertIsNone(
                    snapshot.cost.total_tokens_per_safely_completed_task
                )
                self.assertFalse(snapshot.cost.total_cost_complete)
                self.assertFalse(snapshot.cost.performance_claim_eligible)
                self.assertEqual(
                    snapshot.cost.to_object()[
                        "provider_full_history_billing_accounting"
                    ],
                    "unknown",
                )

    def test_replayed_lease_invalidates_without_second_provider_call(self) -> None:
        session, _, _ = new_session()
        adapter = SessionAdapter()
        lease = prepare_session_turn(
            session,
            "one",
            maximum_total_tokens=20,
            observation=session.expected_observation(),
        )
        execute_session_turn(session, lease, adapter)
        with self.assertRaises(SessionError):
            execute_session_turn(session, lease, adapter)
        self.assertEqual(len(adapter.calls), 1)
        self.assertIs(session.state, SessionState.INVALIDATED)
        self.assertEqual(session.invalidation_reason, "replay")

    def test_sibling_preparation_invalidates_both_paths(self) -> None:
        session, _, _ = new_session()
        prepare_session_turn(
            session,
            "first sibling",
            maximum_total_tokens=20,
            observation=session.expected_observation(),
        )
        with self.assertRaises(SessionError):
            prepare_session_turn(
                session,
                "second sibling",
                maximum_total_tokens=20,
                observation=session.expected_observation(),
            )
        self.assertIs(session.state, SessionState.INVALIDATED)
        self.assertEqual(session.invalidation_reason, "sibling-turn")
        self.assertIsNone(session.snapshot().pending_lease_sha256)

    def test_substituted_lease_invalidates_as_sibling(self) -> None:
        session, _, _ = new_session()
        lease = prepare_session_turn(
            session,
            "original",
            maximum_total_tokens=20,
            observation=session.expected_observation(),
        )
        substitute = replace(lease, maximum_total_tokens=21)
        adapter = SessionAdapter()
        with self.assertRaises(SessionError):
            execute_session_turn(session, substitute, adapter)
        self.assertEqual(adapter.calls, [])
        self.assertEqual(session.invalidation_reason, "sibling-turn")

    def test_clean_close_is_terminal_and_discards_pending_use(self) -> None:
        session, _, _ = new_session()
        closed = close_receiver_session(
            session,
            session.expected_observation(),
        )
        self.assertIs(closed.state, SessionState.CLOSED)
        self.assertEqual(
            closed.state_history[-2:],
            (SessionState.ACTIVE, SessionState.CLOSED),
        )
        with self.assertRaises(SessionError):
            prepare_session_turn(
                session,
                "after close",
                maximum_total_tokens=20,
                observation=replace(
                    closed_to_observation(closed),
                    context_reset_observed=False,
                ),
            )
        self.assertIs(session.state, SessionState.CLOSED)

    def test_close_with_pending_lease_invalidates(self) -> None:
        session, _, _ = new_session()
        prepare_session_turn(
            session,
            "pending",
            maximum_total_tokens=20,
            observation=session.expected_observation(),
        )
        with self.assertRaises(SessionError):
            close_receiver_session(session, session.expected_observation())
        self.assertEqual(session.invalidation_reason, "pending-lease-on-close")


def closed_to_observation(snapshot):
    # Used only to prove CLOSED is terminal; values are otherwise exact.
    from urusilla_hybrid_runtime.session import SessionObservation

    return SessionObservation(
        session_binding_sha256=snapshot.session_binding_sha256,
        model_id=snapshot.model_id,
        model_settings_sha256=snapshot.model_settings_sha256,
        system_sha256=snapshot.system_sha256,
        context_epoch=snapshot.context_epoch,
        session_nonce_sha256=snapshot.session_nonce_sha256,
        next_turn=snapshot.next_turn,
        transcript_chain_sha256=snapshot.transcript_chain_sha256,
        capsule_sha256=snapshot.capsule_sha256,
        task_context_sha256=snapshot.task_context_sha256,
        task_profile_sha256=snapshot.task_profile_sha256,
        symbol_table_sha256=snapshot.symbol_table_sha256,
        comprehension_evidence_sha256=(
            snapshot.comprehension_evidence_sha256
        ),
        last_provider_receipts_sha256=(
            snapshot.last_provider_receipts_sha256
        ),
    )


class SessionInvalidationTests(TestCase):
    def test_reset_compaction_and_observation_mismatches_invalidate(self) -> None:
        cases = (
            (
                "context-reset",
                lambda observation: replace(
                    observation,
                    context_reset_observed=True,
                ),
            ),
            (
                "context-compaction",
                lambda observation: replace(
                    observation,
                    context_compaction_observed=True,
                ),
            ),
            (
                "context-reset",
                lambda observation: replace(
                    observation,
                    context_epoch="provider-context-epoch-2",
                ),
            ),
            (
                "transcript-mismatch",
                lambda observation: replace(
                    observation,
                    transcript_chain_sha256=digest("foreign-chain"),
                ),
            ),
            (
                "capsule-sha256-mismatch",
                lambda observation: replace(
                    observation,
                    capsule_sha256=digest("foreign-capsule"),
                ),
            ),
        )
        for expected_reason, mutate in cases:
            with self.subTest(expected_reason=expected_reason):
                session, _, _ = new_session()
                with self.assertRaises(SessionError):
                    prepare_session_turn(
                        session,
                        "bounded",
                        maximum_total_tokens=20,
                        observation=mutate(session.expected_observation()),
                    )
                self.assertIs(session.state, SessionState.INVALIDATED)
                self.assertEqual(
                    session.invalidation_reason,
                    expected_reason,
                )

    def test_provider_reset_or_compaction_reply_invalidates(self) -> None:
        cases = (
            (
                "context-reset",
                lambda reply, call: replace(
                    reply,
                    context_reset_observed=True,
                ),
            ),
            (
                "context-compaction",
                lambda reply, call: replace(
                    reply,
                    context_compaction_observed=True,
                ),
            ),
        )
        for expected_reason, mutate in cases:
            with self.subTest(expected_reason=expected_reason):
                session, _, _ = new_session()
                lease = prepare_session_turn(
                    session,
                    "bounded",
                    maximum_total_tokens=20,
                    observation=session.expected_observation(),
                )
                adapter = SessionAdapter(mutate)
                with self.assertRaises(SessionError):
                    execute_session_turn(session, lease, adapter)
                self.assertEqual(len(adapter.calls), 1)
                self.assertEqual(
                    session.invalidation_reason,
                    expected_reason,
                )

    def test_reply_binding_and_receipt_mismatches_invalidate(self) -> None:
        cases = (
            (
                "model-settings-sha256-mismatch",
                lambda reply, call: replace(
                    reply,
                    model_settings_sha256=digest("other-settings"),
                ),
            ),
            (
                "context-reset",
                lambda reply, call: replace(
                    reply,
                    context_epoch="provider-context-epoch-2",
                ),
            ),
            (
                "turn-mismatch",
                lambda reply, call: replace(reply, turn=reply.turn + 1),
            ),
            (
                "transcript-mismatch",
                lambda reply, call: replace(
                    reply,
                    parent_transcript_chain_sha256=digest("other-parent"),
                ),
            ),
            (
                "request-content-sha256-mismatch",
                lambda reply, call: replace(
                    reply,
                    receipts=replace(
                        reply.receipts,
                        request_content_sha256=digest("other-request"),
                    ),
                ),
            ),
            (
                "response-content-sha256-mismatch",
                lambda reply, call: replace(
                    reply,
                    receipts=replace(
                        reply.receipts,
                        response_content_sha256=digest("other-response"),
                    ),
                ),
            ),
        )
        for expected_reason, mutate in cases:
            with self.subTest(expected_reason=expected_reason):
                session, _, _ = new_session()
                lease = prepare_session_turn(
                    session,
                    "bounded",
                    maximum_total_tokens=20,
                    observation=session.expected_observation(),
                )
                with self.assertRaises(SessionError):
                    execute_session_turn(
                        session,
                        lease,
                        SessionAdapter(mutate),
                    )
                self.assertEqual(
                    session.invalidation_reason,
                    expected_reason,
                )

    def test_token_ceiling_and_adapter_failure_are_terminal(self) -> None:
        session, _, _ = new_session()
        lease = prepare_session_turn(
            session,
            "bounded",
            maximum_total_tokens=14,
            observation=session.expected_observation(),
        )
        with self.assertRaises(SessionError):
            execute_session_turn(session, lease, SessionAdapter())
        self.assertEqual(session.invalidation_reason, "token-budget-exceeded")

        class FailingAdapter:
            def complete_session_turn(self, handle, call):
                raise RuntimeError("provider failure")

        session, _, _ = new_session()
        lease = prepare_session_turn(
            session,
            "bounded",
            maximum_total_tokens=20,
            observation=session.expected_observation(),
        )
        with self.assertRaises(SessionError):
            execute_session_turn(session, lease, FailingAdapter())
        self.assertEqual(session.invalidation_reason, "adapter-call-failed")
