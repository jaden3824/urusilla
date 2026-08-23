from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from initial_goal_eval.direct_profile_pilot_v1 import (
    ARM_IDS,
    PHASES,
    DirectProfileCall,
    DirectProfilePhaseLedger,
    DirectProfilePilotError,
    DirectProfilePilotResult,
    DirectProfileTrialResult,
    OpaqueProfileConditionInput,
    build_direct_profile_pilot_plan,
    validate_direct_profile_plan,
    validate_direct_profile_result,
)
from initial_goal_eval.matched_session_pilot import (
    NormalizedProviderUsage,
    ProviderCallCapture,
)
from initial_goal_eval.receiver_ceiling_runner import PerfectSenderTaskFixture
from urusilla_hybrid_runtime.canonical import (
    canonical_json,
    sha256_text,
    strict_json_loads,
)
from urusilla_hybrid_runtime.records import load_capsule
from urusilla_hybrid_runtime.tests.test_comprehension import RECEIVER_BINDING
from urusilla_hybrid_runtime.tests.test_surface import (
    ROUND_TRIP_ALIASES,
    TASK_CONTEXT,
    active_surface,
    alias_table,
    encode_bound_state,
    positive_state,
    surface_scope,
)


def _usage(
    *,
    input_tokens: int = 5,
    output_tokens: int = 2,
    reasoning_tokens: int = 1,
) -> NormalizedProviderUsage:
    return NormalizedProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        reasoning_accounting="separately-reported",
        provider_total_tokens=input_tokens + output_tokens + reasoning_tokens,
    )


def _unknown_usage() -> NormalizedProviderUsage:
    return NormalizedProviderUsage(
        input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=None,
    )


def _capture(
    *,
    label: str,
    context_id: str,
    request_text: str,
    response_text: str | None,
    parent_response_id: str | None,
    terminal_status: str = "completed",
    usage: NormalizedProviderUsage | None = None,
) -> ProviderCallCapture:
    response_id = None if response_text is None else f"response-{label}"
    normalized = usage or _usage()
    return ProviderCallCapture(
        provider_id="provider-one",
        context_id=context_id,
        request_id=f"request-{label}",
        response_id=response_id,
        parent_response_id=parent_response_id,
        request_content_sha256=sha256_text(request_text),
        response_content_sha256=(
            None if response_text is None else sha256_text(response_text)
        ),
        resolved_model_id=RECEIVER_BINDING.model_id,
        model_settings_sha256=RECEIVER_BINDING.settings_sha256,
        raw_receipt_text=canonical_json(
            {
                "label": label,
                "status": terminal_status,
                "usage": normalized.to_object(),
            }
        ),
        usage=normalized,
        terminal_status=terminal_status,
    )


def _call(
    *,
    label: str,
    phase: str,
    attempt_index: int,
    context_id: str,
    request_text: str,
    response_text: str | None,
    parent_response_id: str | None,
    terminal_status: str = "completed",
    usage: NormalizedProviderUsage | None = None,
    latency_ms: float | None = 4.5,
) -> DirectProfileCall:
    return DirectProfileCall(
        call_id=f"call-{label}",
        phase=phase,
        attempt_index=attempt_index,
        request_model_visible_text=request_text,
        response_text=response_text,
        capture=_capture(
            label=label,
            context_id=context_id,
            request_text=request_text,
            response_text=response_text,
            parent_response_id=parent_response_id,
            terminal_status=terminal_status,
            usage=usage,
        ),
        transport_latency_ms=latency_ms,
    )


def _condition(condition: str, context_id: str) -> OpaqueProfileConditionInput:
    scope = surface_scope(
        session_id="session-" + context_id,
        model_context_id=context_id,
    )
    expected = alias_table(scope=scope)
    active = active_surface(expected)
    carrier, _, _ = encode_bound_state(
        positive_state(), TASK_CONTEXT, expected, active
    )
    presented = expected
    if condition == "missing-profile":
        presented = None
    elif condition == "wrong-profile":
        aliases = dict(ROUND_TRIP_ALIASES)
        aliases["act:resolve"] = "決"
        presented = alias_table(aliases, scope=scope)
    return OpaqueProfileConditionInput(
        condition=condition,
        expected_table=expected,
        presented_table=presented,
        carrier=carrier,
    )


def _plan():
    state = positive_state()
    fixture = PerfectSenderTaskFixture.from_state(
        item_id="direct-profile-case-1",
        task_context=TASK_CONTEXT,
        action_state=state,
        expected_output_text="valid",
    )
    conditions = (
        _condition("valid-profile", "ctx-d-main"),
        _condition("missing-profile", "ctx-d-missing"),
        _condition("wrong-profile", "ctx-d-wrong"),
    )
    return build_direct_profile_pilot_plan(
        pilot_id="direct-profile-pilot-v1-test",
        capsule=load_capsule(),
        task_context=TASK_CONTEXT,
        receiver_binding=RECEIVER_BINDING,
        fixture=fixture,
        opaque_conditions=conditions,
        maximum_setup_tokens=128,
        maximum_receiver_tokens=64,
    )


def _phase_ledger(
    *,
    comprehension: tuple[DirectProfileCall, ...] = (),
    primary: tuple[DirectProfileCall, ...] = (),
    fallback: tuple[DirectProfileCall, ...] = (),
) -> tuple[DirectProfilePhaseLedger, ...]:
    active_local = {
        "setup",
        "fidelity",
        "router",
        "validator",
        "tool",
        "safety",
        "judge",
    }
    ledgers = []
    for phase in PHASES:
        calls = {
            "comprehension": comprehension,
            "primary": primary,
            "fallback": fallback,
        }.get(phase, ())
        activated = bool(calls) or phase in active_local
        ledgers.append(
            DirectProfilePhaseLedger(
                phase=phase,
                activated=activated,
                local_total_tokens=0,
                attempt_scope_complete=True,
                calls=calls,
            )
        )
    return tuple(ledgers)


def _trial_result(plan_trial) -> DirectProfileTrialResult:
    context_id = plan_trial.required_context_id or "ctx-" + plan_trial.trial_id
    setup_calls = ()
    parent = None
    if plan_trial.setup_preimage is not None:
        setup_response = "setup-ok"
        setup = _call(
            label=plan_trial.trial_id + "-setup",
            phase="comprehension",
            attempt_index=0,
            context_id=context_id,
            request_text=plan_trial.setup_preimage.model_visible_text,
            response_text=setup_response,
            parent_response_id=None,
        )
        setup_calls = (setup,)
        parent = setup.capture.response_id
    is_main = plan_trial.is_main
    response = "valid" if is_main else "refused"
    terminal = "completed" if is_main else "refused"
    primary = _call(
        label=plan_trial.trial_id + "-primary",
        phase="primary",
        attempt_index=0,
        context_id=context_id,
        request_text=plan_trial.hot_preimage.model_visible_text,
        response_text=response,
        parent_response_id=parent,
        terminal_status=terminal,
    )
    return DirectProfileTrialResult(
        trial_id=plan_trial.trial_id,
        arm_id=plan_trial.arm_id,
        condition=plan_trial.condition,
        disposition="completed" if is_main else "refused",
        output_text=response,
        task_success=True if is_main else None,
        fallback_used=False,
        parse_valid=True,
        semantic_fidelity=True if is_main else None,
        negation_preserved=True if is_main else None,
        null_preserved=True if is_main else None,
        failure_preserved=True if is_main else None,
        refusal_preserved=True if is_main else None,
        control_passed=None if is_main else True,
        phase_ledger=_phase_ledger(
            comprehension=setup_calls,
            primary=(primary,),
        ),
    )


def _result(plan) -> DirectProfilePilotResult:
    return DirectProfilePilotResult(
        plan_sha256=plan.sha256,
        trials=tuple(_trial_result(item) for item in plan.trials),
    )


def _replace_phase(
    trial: DirectProfileTrialResult,
    phase: str,
    calls: tuple[DirectProfileCall, ...],
) -> DirectProfileTrialResult:
    ledgers = list(trial.phase_ledger)
    index = PHASES.index(phase)
    ledgers[index] = replace(
        ledgers[index],
        activated=bool(calls) or ledgers[index].activated,
        calls=calls,
    )
    return replace(trial, phase_ledger=tuple(ledgers))


class DirectProfilePlanTests(TestCase):
    def test_plan_freezes_four_arms_and_two_opaque_negative_controls(self) -> None:
        plan = _plan()
        validation = validate_direct_profile_plan(plan)
        self.assertTrue(validation["valid"])
        self.assertFalse(validation["claim_eligible"])
        self.assertEqual(tuple(item.arm_id for item in plan.trials[:4]), ARM_IDS)
        self.assertEqual(plan.trials[4].condition, "missing-profile")
        self.assertEqual(plan.trials[5].condition, "wrong-profile")

        valid_setup = plan.trials[3].setup_preimage
        missing_setup = plan.trials[4].setup_preimage
        wrong_setup = plan.trials[5].setup_preimage
        assert valid_setup is not None
        assert missing_setup is not None
        assert wrong_setup is not None
        valid_user = strict_json_loads(
            valid_setup.model_visible_text.split("\n\nUSER\n", 1)[1]
        )
        missing_user = strict_json_loads(
            missing_setup.model_visible_text.split("\n\nUSER\n", 1)[1]
        )
        wrong_user = strict_json_loads(
            wrong_setup.model_visible_text.split("\n\nUSER\n", 1)[1]
        )
        self.assertNotIn("condition", valid_user)
        self.assertNotIn("condition", missing_user)
        self.assertNotIn("condition", wrong_user)
        self.assertEqual(
            sha256_text(canonical_json(valid_user["presented_profile"])),
            plan.trials[3].expected_profile_sha256,
        )
        self.assertIsNone(missing_user["presented_profile"])
        self.assertNotEqual(
            wrong_user["presented_profile_sha256"],
            wrong_user["expected_profile_sha256"],
        )
        for trial in plan.trials[2:]:
            self.assertEqual(
                trial.hot_preimage.model_visible_text,
                "PAYLOAD\n" + trial.representation_text,
            )
            if trial.setup_preimage is not None:
                self.assertNotIn(
                    trial.setup_preimage.model_visible_text,
                    trial.hot_preimage.model_visible_text,
                )

    def test_wrong_profile_must_differ_in_the_same_surface_scope(self) -> None:
        valid = _condition("valid-profile", "ctx-one")
        with self.assertRaises(DirectProfilePilotError):
            OpaqueProfileConditionInput(
                condition="wrong-profile",
                expected_table=valid.expected_table,
                presented_table=valid.expected_table,
                carrier=valid.carrier,
            )


class DirectProfileResultTests(TestCase):
    def test_complete_result_recomputes_tokens_bytes_counts_and_null_energy(self) -> None:
        plan = _plan()
        summary = validate_direct_profile_result(plan, _result(plan))
        self.assertFalse(summary["claim_eligible"])
        self.assertFalse(summary["energy_claim_eligible"])
        main = summary["main_arm_metrics"]
        self.assertEqual(
            main[ARM_IDS[0]]["receiver_only_inclusive_total_tokens"], 8
        )
        self.assertIsNone(main[ARM_IDS[0]]["end_to_end_inclusive_total_tokens"])
        self.assertIsNone(main[ARM_IDS[0]]["inclusive_total_tokens"])
        self.assertIsNone(
            main[ARM_IDS[0]]["receiver_only_tokens_per_safe_completion"]
        )
        self.assertIsNone(main[ARM_IDS[0]]["tokens_per_safe_completion"])
        self.assertEqual(main[ARM_IDS[2]]["cold_setup_tokens"], 8)
        self.assertEqual(
            main[ARM_IDS[2]]["receiver_only_inclusive_total_tokens"], 16
        )
        self.assertEqual(
            main[ARM_IDS[2]]["receiver_runtime_tokens_excluding_cold_setup"], 8
        )
        self.assertIsNone(main[ARM_IDS[2]]["warm_multi_task_amortized_tokens"])
        self.assertEqual(
            main[ARM_IDS[2]]["phase_token_totals"]["comprehension"], 8
        )
        self.assertEqual(main[ARM_IDS[2]]["phase_token_totals"]["primary"], 8)
        self.assertEqual(
            main[ARM_IDS[3]]["receiver_only_inclusive_total_tokens"], 16
        )
        self.assertTrue(main[ARM_IDS[3]]["exact_output_match"])
        self.assertTrue(main[ARM_IDS[3]]["task_success"])
        self.assertTrue(main[ARM_IDS[3]]["outcome_assertions_unverified"])
        self.assertIsNone(main[ARM_IDS[3]]["safely_completed"])
        self.assertIsNone(main[ARM_IDS[3]]["actual_joules"])
        self.assertIsNone(main[ARM_IDS[3]]["end_to_end_actual_joules"])
        c_transport = summary["trial_evidence"]["c-main"]["transport"]
        self.assertEqual(c_transport["request_count"], 2)
        self.assertEqual(c_transport["response_count"], 2)
        self.assertGreater(c_transport["setup_or_capsule_request_bytes"], 0)
        self.assertGreater(
            c_transport["receiver_primary_request_response_bytes"], 0
        )
        self.assertEqual(c_transport["repair_request_response_bytes"], 0)
        self.assertEqual(c_transport["fallback_request_response_bytes"], 0)
        self.assertEqual(c_transport["judge_request_response_bytes"], 0)
        self.assertEqual(
            c_transport["payload_bytes_across_primary_attempts"],
            len(plan.trials[2].representation_text.encode("utf-8")),
        )
        self.assertEqual(c_transport["transport_latency_ms"], 9.0)
        self.assertFalse(summary["bytes_converted_to_tokens"])
        self.assertFalse(summary["bytes_or_tokens_converted_to_joules"])

    def test_hot_preimage_digest_is_checked_against_frozen_bytes(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[2]
        original = trial.phase("primary").calls[0]
        changed_text = original.request_model_visible_text + " "
        changed = _call(
            label="c-main-primary-tampered",
            phase="primary",
            attempt_index=0,
            context_id=original.capture.context_id,
            request_text=changed_text,
            response_text=original.response_text,
            parent_response_id=original.capture.parent_response_id,
        )
        changed_trial = _replace_phase(trial, "primary", (changed,))
        trials = list(result.trials)
        trials[2] = changed_trial
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

    def test_public_output_is_bound_to_exact_terminal_provider_response(self) -> None:
        plan = _plan()
        result = _result(plan)
        trials = list(result.trials)
        trials[0] = replace(trials[0], output_text="forged-public-output")
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

    def test_coordinated_wrong_response_is_scored_false_and_never_safe(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[0]
        original = trial.phase("primary").calls[0]
        wrong = _call(
            label="a-main-coordinated-wrong",
            phase="primary",
            attempt_index=0,
            context_id=original.capture.context_id,
            request_text=original.request_model_visible_text,
            response_text="definitely-wrong",
            parent_response_id=None,
        )
        changed = _replace_phase(trial, "primary", (wrong,))
        changed = replace(changed, output_text="definitely-wrong")
        self.assertTrue(changed.task_success)
        trials = list(result.trials)
        trials[0] = changed
        summary = validate_direct_profile_result(
            plan, replace(result, trials=tuple(trials))
        )
        metrics = summary["main_arm_metrics"][ARM_IDS[0]]
        self.assertFalse(metrics["exact_output_match"])
        self.assertFalse(metrics["task_success"])
        self.assertTrue(
            metrics["caller_reported_outcome_assertions"]["task_success"]
        )
        self.assertTrue(metrics["outcome_assertions_unverified"])
        self.assertIsNone(metrics["safely_completed"])
        self.assertIsNone(metrics["receiver_only_tokens_per_safe_completion"])

    def test_failed_or_refused_disposition_cannot_be_safely_completed(self) -> None:
        plan = _plan()
        result = _result(plan)
        with self.assertRaises(DirectProfilePilotError):
            replace(result.trials[0], disposition="failed")

        failed = replace(
            result.trials[0],
            disposition="failed",
            output_text=None,
            task_success=False,
            parse_valid=False,
            semantic_fidelity=False,
            negation_preserved=False,
            null_preserved=False,
            failure_preserved=False,
            refusal_preserved=False,
        )
        self.assertIsNone(failed.safely_completed)
        trials = list(result.trials)
        trials[0] = failed
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

    def test_provider_usage_cannot_exceed_frozen_per_call_ceiling(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[0]
        original = trial.phase("primary").calls[0]
        oversized = _call(
            label="a-main-over-ceiling",
            phase="primary",
            attempt_index=0,
            context_id=original.capture.context_id,
            request_text=original.request_model_visible_text,
            response_text=original.response_text,
            parent_response_id=None,
            usage=_usage(input_tokens=100, output_tokens=2, reasoning_tokens=1),
        )
        trials = list(result.trials)
        trials[0] = _replace_phase(trial, "primary", (oversized,))
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

    def test_retry_cannot_follow_a_completed_terminal_attempt(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[0]
        first = trial.phase("primary").calls[0]
        second = _call(
            label="a-main-after-terminal",
            phase="primary",
            attempt_index=1,
            context_id=first.capture.context_id,
            request_text=first.request_model_visible_text,
            response_text="valid",
            parent_response_id=first.capture.response_id,
        )
        trials = list(result.trials)
        trials[0] = _replace_phase(trial, "primary", (first, second))
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

    def test_setup_and_hot_require_same_context_and_exact_parent(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[3]
        primary = trial.phase("primary").calls[0]
        wrong_context = _call(
            label="d-main-wrong-context",
            phase="primary",
            attempt_index=0,
            context_id="ctx-different",
            request_text=primary.request_model_visible_text,
            response_text=primary.response_text,
            parent_response_id=primary.capture.parent_response_id,
        )
        trials = list(result.trials)
        trials[3] = _replace_phase(trial, "primary", (wrong_context,))
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

        wrong_parent = _call(
            label="d-main-wrong-parent",
            phase="primary",
            attempt_index=0,
            context_id=primary.capture.context_id,
            request_text=primary.request_model_visible_text,
            response_text=primary.response_text,
            parent_response_id="response-unrelated",
        )
        trials[3] = _replace_phase(trial, "primary", (wrong_parent,))
        with self.assertRaises(DirectProfilePilotError):
            validate_direct_profile_result(
                plan, replace(result, trials=tuple(trials))
            )

    def test_failed_attempt_tokens_and_bytes_are_retained_before_retry(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[0]
        plan_trial = plan.trials[0]
        context_id = trial.phase("primary").calls[0].capture.context_id
        failed = _call(
            label="a-main-failed-attempt",
            phase="primary",
            attempt_index=0,
            context_id=context_id,
            request_text=plan_trial.hot_preimage.model_visible_text,
            response_text=None,
            parent_response_id=None,
            terminal_status="failed",
            usage=_usage(input_tokens=5, output_tokens=0, reasoning_tokens=1),
        )
        passed = _call(
            label="a-main-retry",
            phase="primary",
            attempt_index=1,
            context_id=context_id,
            request_text=plan_trial.hot_preimage.model_visible_text,
            response_text="valid",
            parent_response_id=None,
        )
        changed = _replace_phase(trial, "primary", (failed, passed))
        trials = list(result.trials)
        trials[0] = changed
        summary = validate_direct_profile_result(
            plan, replace(result, trials=tuple(trials))
        )
        evidence = summary["trial_evidence"]["a-main"]
        self.assertEqual(evidence["receiver_only_inclusive_total_tokens"], 14)
        self.assertIsNone(evidence["end_to_end_inclusive_total_tokens"])
        transport = evidence["transport"]
        self.assertEqual(transport["request_count"], 2)
        self.assertEqual(
            transport["payload_bytes_across_primary_attempts"],
            2 * len(plan_trial.representation_text.encode("utf-8")),
        )
        self.assertGreater(transport["retry_or_fallback_bytes"], 0)

    def test_unknown_failed_usage_poisoning_survives_successful_fallback(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[0]
        plan_trial = plan.trials[0]
        context_id = trial.phase("primary").calls[0].capture.context_id
        failed = _call(
            label="a-main-unknown-failure",
            phase="primary",
            attempt_index=0,
            context_id=context_id,
            request_text=plan_trial.hot_preimage.model_visible_text,
            response_text=None,
            parent_response_id=None,
            terminal_status="failed",
            usage=_unknown_usage(),
            latency_ms=None,
        )
        fallback = _call(
            label="a-main-fallback",
            phase="fallback",
            attempt_index=0,
            context_id="ctx-a-main-fallback",
            request_text="SYSTEM\nfallback\n\nUSER\n" + plan_trial.representation_text,
            response_text="valid",
            parent_response_id=None,
        )
        changed = _replace_phase(trial, "primary", (failed,))
        ledgers = list(changed.phase_ledger)
        fallback_index = PHASES.index("fallback")
        ledgers[fallback_index] = replace(
            ledgers[fallback_index],
            activated=True,
            calls=(fallback,),
        )
        changed = replace(
            changed,
            disposition="fallback",
            fallback_used=True,
            phase_ledger=tuple(ledgers),
        )
        trials = list(result.trials)
        trials[0] = changed
        summary = validate_direct_profile_result(
            plan, replace(result, trials=tuple(trials))
        )
        evidence = summary["trial_evidence"]["a-main"]
        self.assertIsNone(evidence["receiver_only_inclusive_total_tokens"])
        self.assertIsNone(evidence["tokens_per_safe_completion"])
        self.assertIsNone(evidence["transport"]["transport_latency_ms"])
        self.assertEqual(evidence["transport"]["request_count"], 2)
        self.assertGreater(evidence["transport"]["retry_or_fallback_bytes"], 0)
        self.assertGreater(evidence["transport"]["total_request_bytes"], 0)

    def test_unreported_reasoning_keeps_inclusive_total_null(self) -> None:
        plan = _plan()
        result = _result(plan)
        trial = result.trials[1]
        original = trial.phase("primary").calls[0]
        usage = NormalizedProviderUsage(
            input_tokens=5,
            output_tokens=2,
            reasoning_tokens=None,
            reasoning_accounting="not-reported",
            provider_total_tokens=7,
        )
        changed_call = _call(
            label="b-main-unreported-reasoning",
            phase="primary",
            attempt_index=0,
            context_id=original.capture.context_id,
            request_text=original.request_model_visible_text,
            response_text=original.response_text,
            parent_response_id=None,
            usage=usage,
        )
        changed = _replace_phase(trial, "primary", (changed_call,))
        trials = list(result.trials)
        trials[1] = changed
        summary = validate_direct_profile_result(
            plan, replace(result, trials=tuple(trials))
        )
        metrics = summary["main_arm_metrics"][ARM_IDS[1]]
        self.assertIsNone(metrics["receiver_only_inclusive_total_tokens"])
        self.assertIsNone(metrics["tokens_per_safe_completion"])

    def test_attempts_must_be_individual_not_aggregate_retry_counters(self) -> None:
        plan = _plan()
        trial = _result(plan).trials[0]
        original = trial.phase("primary").calls[0]
        capture = replace(original.capture, retry_count=1)
        with self.assertRaises(DirectProfilePilotError):
            replace(original, capture=capture)
