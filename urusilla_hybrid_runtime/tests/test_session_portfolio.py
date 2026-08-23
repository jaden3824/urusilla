from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from unittest import TestCase

from urusilla_hybrid_runtime.receiver import ReceiverModelReply
from urusilla_hybrid_runtime.records import PublicActionState, load_capsule
from urusilla_hybrid_runtime.router import CostForecast, ReceiverCapabilities
from urusilla_hybrid_runtime.runtime import (
    ObservedLocalUsage,
    execute_prepared_message,
    prepare_message,
)
from urusilla_hybrid_runtime.sender import ModelReply
from urusilla_hybrid_runtime.session_portfolio import (
    SessionPortfolioError,
    SessionPortfolioLocalUsage,
    SessionPortfolioTurn,
    build_session_portfolio_accounting,
)
from urusilla_hybrid_runtime.session_runtime import (
    bind_prepared_message_to_session,
    execute_session_bound_hybrid,
    mint_session_cached_receiver,
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
from urusilla_hybrid_runtime.tests.test_session import new_session
from urusilla_hybrid_runtime.tests.test_session_runtime import OutputSessionAdapter


def _complete_baseline_usage(prepared):
    return ObservedLocalUsage.for_prepared(
        prepared,
        setup_tokens=1,
        router_tokens=1,
        repair_tokens=0,
        fallback_tokens=0,
        tool_tokens=0,
        safety_tokens=1,
        judge_tokens=1,
    )


def _prepared_pair(session, attempt, *, label: str, prefer_json: bool):
    capsule = load_capsule()
    cached = mint_session_cached_receiver(
        session,
        attempt,
        session.expected_observation(),
    )
    state = PublicActionState.from_object(
        capsule.to_object()["examples"]["positive"]
    )
    source = (f"Verify artifact seven for portfolio task {label}. " * 800)
    raw_penalty = 1_000 if prefer_json else 0
    json_penalty = 0 if prefer_json else 1_000
    optimized = prepare_message(
        source,
        capsule,
        cached.capabilities,
        char_count,
        task_context=TASK_CONTEXT,
        forecasts=complete_forecasts(
            raw=CostForecast(
                receiver_output_tokens=raw_penalty,
                cached_context_tokens=1,
                comprehension_setup_tokens=0,
                complete=True,
            ),
            json=CostForecast(
                receiver_output_tokens=json_penalty,
                cached_context_tokens=1,
                comprehension_setup_tokens=0,
                complete=True,
            ),
        ),
        evidence={
            "action-state": passing_evidence(
                f"portfolio-{label}",
                capsule_sha256=capsule.sha256,
            )
        },
        compiler=FakeCompiler(
            ModelReply(sender_output(state), f"sender-{label}", 10)
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
        forecasts=complete_forecasts(
            raw=CostForecast(
                receiver_output_tokens=raw_penalty,
                complete=True,
            ),
            json=CostForecast(
                receiver_output_tokens=json_penalty,
                complete=True,
            ),
        ),
        policy=action_policy(),
    )
    expected_mode = "json" if prefer_json else "raw"
    if optimized.route.selected_mode != "action-state":
        raise AssertionError(
            {
                item.mode: item.reasons
                for item in optimized.route.candidates
            }
        )
    if fallback.route.selected_mode != expected_mode:
        raise AssertionError(
            (fallback.route.selected_mode, expected_mode)
        )
    return fallback, bind_prepared_message_to_session(
        cached,
        optimized,
        fallback,
    )


def _baseline_reply(total_tokens: int = 100) -> ReceiverModelReply:
    return replace(receiver_reply(), provider_total_tokens=total_tokens)


def _execute_turn(
    session,
    attempt,
    *,
    label: str,
    prefer_json: bool,
    primary_text: str = "valid",
    primary_failure: Exception | None = None,
    baseline_failure: bool = False,
    baseline_total_tokens: int = 100,
) -> SessionPortfolioTurn:
    fallback, plan = _prepared_pair(
        session,
        attempt,
        label=label,
        prefer_json=prefer_json,
    )
    primary = OutputSessionAdapter(
        primary_text,
        failure=primary_failure,
    )
    execution = execute_session_bound_hybrid(
        attempt,
        fallback,
        FakeReceiverAdapter(receiver_reply()),
        plan=plan,
        session=session,
        observation=session.expected_observation(),
        session_adapter=primary,
        output_validator=validate_output,
    )
    if len(primary.calls) != 1:
        raise AssertionError("fixture expected one attempted hot call")
    baseline_adapter = FakeReceiverAdapter(
        RuntimeError("baseline provider failed")
        if baseline_failure
        else _baseline_reply(baseline_total_tokens)
    )
    baseline = execute_prepared_message(
        fallback,
        baseline_adapter,
        output_validator=validate_output,
        observed_local_usage=_complete_baseline_usage(fallback),
    )
    local = SessionPortfolioLocalUsage(
        session_binding_sha256=plan.cached_receiver.session_binding_sha256,
        lease_sha256=primary.calls[0].lease.sha256,
        optimized_execution_binding_sha256=(
            plan.optimized.execution_binding_sha256
        ),
        fallback_execution_binding_sha256=(
            fallback.execution_binding_sha256
        ),
        setup_tokens=2,
        router_tokens=1,
        repair_tokens=0,
        fallback_tokens=1 if execution.fallback_calls else 0,
        tool_tokens=0,
        safety_tokens=1,
        judge_tokens=3,
    )
    return SessionPortfolioTurn(
        lease=primary.calls[0].lease,
        execution=execution,
        local_usage=local,
        baseline=baseline,
    )


class SessionPortfolioAccountingTests(TestCase):
    def test_k_one_setup_loses_but_k_two_amortizes_without_a_claim(self) -> None:
        session, attempt, _ = new_session()
        opening = session.expected_observation()
        first = _execute_turn(
            session,
            attempt,
            label="amortization-one",
            prefer_json=False,
            baseline_total_tokens=52,
        )
        k_one = build_session_portfolio_accounting(
            attempt,
            opening,
            (first,),
        )
        second = _execute_turn(
            session,
            attempt,
            label="amortization-two",
            prefer_json=True,
            baseline_total_tokens=52,
        )
        k_two = build_session_portfolio_accounting(
            attempt,
            opening,
            (first, second),
        )

        assert k_one.reported_token_saving_fraction is not None
        assert k_two.reported_token_saving_fraction is not None
        self.assertLess(k_one.reported_token_saving_fraction, 0)
        self.assertGreater(k_two.reported_token_saving_fraction, 0)
        self.assertEqual(k_one.setup_charge_count, 1)
        self.assertEqual(k_two.setup_charge_count, 1)
        self.assertFalse(k_one.claim_eligible)
        self.assertFalse(k_two.claim_eligible)

    def test_two_heterogeneous_turns_charge_setup_once_and_keep_baselines(self) -> None:
        session, attempt, _ = new_session()
        opening = session.expected_observation()
        first = _execute_turn(
            session,
            attempt,
            label="raw-control",
            prefer_json=False,
        )
        second = _execute_turn(
            session,
            attempt,
            label="json-control",
            prefer_json=True,
        )

        accounting = build_session_portfolio_accounting(
            attempt,
            opening,
            (first, second),
        )
        serialized = accounting.to_object()
        per_turn = serialized["turns"]
        assert type(per_turn) is list
        turn_total = sum(
            item["candidate_reported_tokens_excluding_shared_setup"]
            for item in per_turn
        )

        self.assertEqual(accounting.setup_charge_count, 1)
        self.assertEqual(accounting.setup_reported_tokens, attempt.total_tokens)
        self.assertEqual(
            accounting.candidate_reported_total_tokens,
            attempt.total_tokens + turn_total,
        )
        self.assertEqual(accounting.baseline_modes, ("raw", "json"))
        self.assertTrue(accounting.reported_usage_complete)
        self.assertTrue(accounting.matched_safely_completed)
        self.assertIsInstance(
            accounting.reported_token_saving_fraction,
            Fraction,
        )
        self.assertIsNone(accounting.complete_total_tokens)
        self.assertIsNone(
            accounting.complete_total_token_saving_percent
        )
        self.assertFalse(accounting.provider_authenticity_verified)
        self.assertFalse(accounting.provider_full_history_billing_verified)
        self.assertFalse(accounting.goal_total_complete)
        self.assertFalse(accounting.claim_eligible)
        self.assertEqual(accounting.sha256, accounting.sha256)

    def test_failed_primary_and_fallback_are_both_retained(self) -> None:
        session, attempt, _ = new_session()
        opening = session.expected_observation()
        turn = _execute_turn(
            session,
            attempt,
            label="fallback",
            prefer_json=False,
            primary_text="invalid",
        )

        accounting = build_session_portfolio_accounting(
            attempt,
            opening,
            (turn,),
        )
        summary = accounting.to_object()["turns"][0]

        self.assertEqual(turn.execution.status, "fallback-completed")
        self.assertEqual(summary["primary_calls"], 1)
        self.assertEqual(summary["fallback_calls"], 1)
        self.assertEqual(summary["primary_reported_tokens"], 15)
        self.assertEqual(summary["fallback_reported_tokens"], 5)
        self.assertEqual(
            summary["optimized_failure"],
            "session-primary-output-invalid",
        )
        self.assertEqual(
            accounting.candidate_reported_total_tokens,
            attempt.total_tokens + 10 + 3 + 8 + 15 + 5,
        )
        self.assertTrue(accounting.matched_safely_completed)
        self.assertIsNotNone(accounting.reported_token_saving_fraction)

    def test_unknown_provider_or_local_usage_is_sticky_null(self) -> None:
        session, attempt, _ = new_session()
        opening = session.expected_observation()
        complete = _execute_turn(
            session,
            attempt,
            label="unknown-local",
            prefer_json=False,
        )
        unknown_local = replace(
            complete,
            local_usage=replace(complete.local_usage, judge_tokens=None),
        )
        local_accounting = build_session_portfolio_accounting(
            attempt,
            opening,
            (unknown_local,),
        )
        self.assertIsNone(local_accounting.candidate_reported_total_tokens)
        self.assertIsNotNone(local_accounting.baseline_reported_total_tokens)
        self.assertFalse(local_accounting.reported_usage_complete)
        self.assertIsNone(local_accounting.reported_token_saving_fraction)

        failed_session, failed_attempt, _ = new_session()
        failed_opening = failed_session.expected_observation()
        unknown_provider = _execute_turn(
            failed_session,
            failed_attempt,
            label="unknown-provider",
            prefer_json=True,
            primary_failure=RuntimeError("provider failed without usage"),
        )
        provider_accounting = build_session_portfolio_accounting(
            failed_attempt,
            failed_opening,
            (unknown_provider,),
        )
        provider_summary = provider_accounting.to_object()["turns"][0]
        self.assertIsNone(provider_summary["primary_reported_tokens"])
        self.assertEqual(provider_summary["fallback_reported_tokens"], 5)
        self.assertIsNone(
            provider_accounting.candidate_reported_total_tokens
        )
        self.assertIsNone(
            provider_accounting.reported_token_saving_fraction
        )

        baseline_session, baseline_attempt, _ = new_session()
        baseline_opening = baseline_session.expected_observation()
        unknown_baseline = _execute_turn(
            baseline_session,
            baseline_attempt,
            label="unknown-baseline",
            prefer_json=False,
            baseline_failure=True,
        )
        baseline_accounting = build_session_portfolio_accounting(
            baseline_attempt,
            baseline_opening,
            (unknown_baseline,),
        )
        self.assertIsNotNone(
            baseline_accounting.candidate_reported_total_tokens
        )
        self.assertIsNone(
            baseline_accounting.baseline_reported_total_tokens
        )
        self.assertIsNone(
            baseline_accounting.reported_token_saving_fraction
        )

    def test_duplicate_noncontiguous_and_cross_session_leases_are_rejected(self) -> None:
        session, attempt, _ = new_session()
        opening = session.expected_observation()
        first = _execute_turn(
            session,
            attempt,
            label="one",
            prefer_json=False,
        )
        second = _execute_turn(
            session,
            attempt,
            label="two",
            prefer_json=True,
        )

        with self.assertRaisesRegex(SessionPortfolioError, "duplicate lease"):
            build_session_portfolio_accounting(
                attempt,
                opening,
                (first, first),
            )

        skipped_lease = replace(second.lease, turn=3)
        skipped = replace(
            second,
            lease=skipped_lease,
            local_usage=replace(
                second.local_usage,
                lease_sha256=skipped_lease.sha256,
            ),
        )
        with self.assertRaisesRegex(SessionPortfolioError, "noncontiguous"):
            build_session_portfolio_accounting(
                attempt,
                opening,
                (first, skipped),
            )

        foreign_lease = replace(
            second.lease,
            session_binding_sha256="sha256:" + "0" * 64,
        )
        foreign = replace(
            second,
            lease=foreign_lease,
            local_usage=replace(
                second.local_usage,
                session_binding_sha256="sha256:" + "0" * 64,
                lease_sha256=foreign_lease.sha256,
            ),
        )
        with self.assertRaisesRegex(SessionPortfolioError, "session binding"):
            build_session_portfolio_accounting(
                attempt,
                opening,
                (first, foreign),
            )

    def test_accounting_cannot_be_replaced_with_a_claim_or_different_total(self) -> None:
        session, attempt, _ = new_session()
        opening = session.expected_observation()
        turn = _execute_turn(
            session,
            attempt,
            label="sealed",
            prefer_json=False,
        )
        accounting = build_session_portfolio_accounting(
            attempt,
            opening,
            (turn,),
        )

        assert accounting.candidate_reported_total_tokens is not None
        with self.assertRaisesRegex(
            SessionPortfolioError,
            "bounded builder",
        ):
            replace(
                accounting,
                candidate_reported_total_tokens=(
                    accounting.candidate_reported_total_tokens + 1
                ),
            )
