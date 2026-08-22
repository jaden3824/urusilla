from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from initial_goal_eval.matched_session_pilot import (
    PILOT_PHASES,
    ComprehensionProviderResult,
    MatchedSessionPilotError,
    NormalizedProviderUsage,
    PilotJudgeInput,
    PilotJudgeResult,
    PilotPreparedInputs,
    ProviderCallCapture,
    ReceiverProviderResult,
    run_matched_session_pilot,
)
from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.receiver import ReceiverModelReply
from urusilla_hybrid_runtime.records import PublicActionState, load_capsule
from urusilla_hybrid_runtime.router import CostForecast, ReceiverCapabilities
from urusilla_hybrid_runtime.runtime import ObservedLocalUsage, prepare_message
from urusilla_hybrid_runtime.sender import ModelReply
from urusilla_hybrid_runtime.tests.test_comprehension import (
    RECEIVER_BINDING,
    good_reply,
)
from urusilla_hybrid_runtime.tests.test_hybrid_runtime import (
    TASK_CONTEXT,
    FakeCompiler,
    action_policy,
    char_count,
    complete_forecasts,
    passing_evidence,
    sender_output,
    validate_output,
    verify_fidelity,
    verify_utility,
)


JUDGE_RUBRIC = "The candidate must be exactly the bounded valid status string."
JUDGE_REFERENCE = "valid"


def _digest(label: str) -> str:
    return sha256_text(label)


def _usage_for_receiver(reply: ReceiverModelReply) -> NormalizedProviderUsage:
    return NormalizedProviderUsage.from_receiver_reply(reply)


def _receiver_reply(text: str = "valid") -> ReceiverModelReply:
    return ReceiverModelReply(
        text=text,
        model_id=RECEIVER_BINDING.model_id,
        input_tokens=3,
        output_tokens=2,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=5,
    )


def _capture(
    *,
    provider_id: str,
    context_id: str,
    request_id: str,
    response_id: str | None,
    parent_response_id: str | None,
    request_sha256: str,
    response_sha256: str | None,
    model_id: str,
    settings_sha256: str,
    usage: NormalizedProviderUsage,
    terminal_status: str = "completed",
    retry_count: int = 0,
    repair_count: int = 0,
    context_reset_observed: bool = False,
    context_compaction_observed: bool = False,
    external_effects_performed: bool = False,
) -> ProviderCallCapture:
    return ProviderCallCapture(
        provider_id=provider_id,
        context_id=context_id,
        request_id=request_id,
        response_id=response_id,
        parent_response_id=parent_response_id,
        request_content_sha256=request_sha256,
        response_content_sha256=response_sha256,
        resolved_model_id=model_id,
        model_settings_sha256=settings_sha256,
        raw_receipt_text=canonical_json(
            {
                "provider": provider_id,
                "request": request_id,
                "response": response_id,
                "usage": usage.to_object(),
            }
        ),
        usage=usage,
        terminal_status=terminal_status,
        retry_count=retry_count,
        repair_count=repair_count,
        context_reset_observed=context_reset_observed,
        context_compaction_observed=context_compaction_observed,
        external_effects_performed=external_effects_performed,
    )


class FakeMatchedProvider:
    def __init__(
        self,
        *,
        primary_failure: bool = False,
        primary_usage_unknown: bool = False,
        primary_retry_count: int = 0,
        primary_repair_count: int = 0,
        comprehension_reset: bool = False,
        comprehension_compaction: bool = False,
        fallback_reuses_context: bool = False,
        raw_external_effect: bool = False,
    ) -> None:
        self.primary_failure = primary_failure
        self.primary_usage_unknown = primary_usage_unknown
        self.primary_retry_count = primary_retry_count
        self.primary_repair_count = primary_repair_count
        self.comprehension_reset = comprehension_reset
        self.comprehension_compaction = comprehension_compaction
        self.fallback_reuses_context = fallback_reuses_context
        self.raw_external_effect = raw_external_effect
        self.provider_id = "matched-provider"
        self.cold_context = "ctx-urusilla-cold"
        self.cold_response_id = "resp-cold"
        self.session_calls = []
        self.receiver_calls = []

    def complete_comprehension(self, challenge):
        reply = good_reply(challenge)
        return ComprehensionProviderResult(
            reply=reply,
            capture=_capture(
                provider_id=self.provider_id,
                context_id=self.cold_context,
                request_id="req-cold",
                response_id=self.cold_response_id,
                parent_response_id=None,
                request_sha256=challenge.model_visible_sha256,
                response_sha256=sha256_text(reply.text),
                model_id=reply.model_id,
                settings_sha256=reply.model_settings_sha256,
                usage=NormalizedProviderUsage.from_comprehension_reply(reply),
                context_reset_observed=self.comprehension_reset,
                context_compaction_observed=self.comprehension_compaction,
            ),
            raw_provider_handle=self,
            context_epoch="provider-context-epoch-1",
            session_nonce="a" * 64,
        )

    def complete_receiver(self, arm_id, request):
        self.receiver_calls.append((arm_id, request))
        reply = _receiver_reply()
        context_id = {
            "raw": "ctx-raw",
            "json": "ctx-json",
            "urusilla-fallback": (
                self.cold_context
                if self.fallback_reuses_context
                else "ctx-urusilla-fallback"
            ),
        }[arm_id]
        response_id = {
            "raw": "resp-raw",
            "json": "resp-json",
            "urusilla-fallback": "resp-fallback",
        }[arm_id]
        capture = _capture(
            provider_id=self.provider_id,
            context_id=context_id,
            request_id="req-" + arm_id,
            response_id=response_id,
            parent_response_id=None,
            request_sha256=sha256_text(request.model_visible_text),
            response_sha256=sha256_text(reply.text),
            model_id=reply.model_id,
            settings_sha256=RECEIVER_BINDING.settings_sha256,
            usage=_usage_for_receiver(reply),
            external_effects_performed=(
                self.raw_external_effect and arm_id == "raw"
            ),
        )
        return ReceiverProviderResult(reply=reply, capture=capture)

    def complete_session_turn(self, raw_provider_handle, call):
        self.session_calls.append((raw_provider_handle, call))
        if self.primary_failure:
            usage = (
                NormalizedProviderUsage(
                    input_tokens=None,
                    output_tokens=None,
                    reasoning_tokens=None,
                    reasoning_accounting="not-reported",
                    provider_total_tokens=None,
                )
                if self.primary_usage_unknown
                else NormalizedProviderUsage(
                    input_tokens=4,
                    output_tokens=0,
                    reasoning_tokens=None,
                    reasoning_accounting="not-reported",
                    provider_total_tokens=4,
                )
            )
            return ReceiverProviderResult(
                reply=None,
                capture=_capture(
                    provider_id=self.provider_id,
                    context_id=self.cold_context,
                    request_id="req-hot",
                    response_id=None,
                    parent_response_id=self.cold_response_id,
                    request_sha256=sha256_text(call.request_text),
                    response_sha256=None,
                    model_id=RECEIVER_BINDING.model_id,
                    settings_sha256=RECEIVER_BINDING.settings_sha256,
                    usage=usage,
                    terminal_status="failed",
                    retry_count=self.primary_retry_count,
                    repair_count=self.primary_repair_count,
                ),
            )
        reply = _receiver_reply()
        return ReceiverProviderResult(
            reply=reply,
            capture=_capture(
                provider_id=self.provider_id,
                context_id=self.cold_context,
                request_id="req-hot",
                response_id="resp-hot",
                parent_response_id=self.cold_response_id,
                request_sha256=sha256_text(call.request_text),
                response_sha256=sha256_text(reply.text),
                model_id=reply.model_id,
                settings_sha256=RECEIVER_BINDING.settings_sha256,
                usage=_usage_for_receiver(reply),
            ),
        )


def _zero_local(prepared, *, setup_tokens: int | None = 0):
    return ObservedLocalUsage.for_prepared(
        prepared,
        setup_tokens=setup_tokens,
        router_tokens=0,
        repair_tokens=0,
        fallback_tokens=0,
        tool_tokens=0,
        safety_tokens=0,
        judge_tokens=0,
    )


def _preparer(
    *,
    unknown_optimized_setup: bool = False,
    fallback_setup_tokens: int | None = 0,
):
    capsule = load_capsule()
    state = PublicActionState.from_object(
        capsule.to_object()["examples"]["positive"]
    )
    source = "Verify artifact seven without external effects. " * 800

    def prepare(cached):
        compiler = FakeCompiler(
            ModelReply(sender_output(state), "sender-model", 10)
        )
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
                    cached_context_tokens=10_000,
                    comprehension_setup_tokens=0,
                    complete=True,
                ),
            ),
            evidence={
                "action-state": passing_evidence(
                    capsule_sha256=capsule.sha256
                )
            },
            compiler=compiler,
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
        raw = prepare_message(
            source,
            capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(
                raw=CostForecast(cached_context_tokens=1, complete=True),
                json=CostForecast(cached_context_tokens=10_000, complete=True),
            ),
            policy=action_policy(),
        )
        json = prepare_message(
            source,
            capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(
                raw=CostForecast(cached_context_tokens=10_000, complete=True),
                json=CostForecast(cached_context_tokens=1, complete=True),
            ),
            policy=action_policy(),
        )
        if optimized.route.selected_mode != "action-state":
            raise AssertionError(
                {item.mode: item.reasons for item in optimized.route.candidates}
            )
        if raw.route.selected_mode != "raw" or json.route.selected_mode != "json":
            raise AssertionError((raw.route.selected_mode, json.route.selected_mode))
        compilation = optimized.compilation
        fidelity = optimized.fidelity_verification
        assert compilation is not None
        assert fidelity is not None
        sender_capture = _capture(
            provider_id="sender-provider",
            context_id="ctx-sender",
            request_id="req-sender",
            response_id="resp-sender",
            parent_response_id=None,
            request_sha256=sha256_text(compiler.prompts[0].model_visible_text),
            response_sha256=compilation.output_sha256,
            model_id=compilation.model_id or "",
            settings_sha256=_digest("sender-settings"),
            usage=NormalizedProviderUsage(
                input_tokens=6,
                output_tokens=4,
                reasoning_tokens=None,
                reasoning_accounting="not-reported",
                provider_total_tokens=10,
            ),
        )
        fidelity_request_text = fidelity.input_binding_sha256
        fidelity_capture = _capture(
            provider_id="fidelity-provider",
            context_id="ctx-fidelity",
            request_id="req-fidelity",
            response_id="resp-fidelity",
            parent_response_id=None,
            request_sha256=sha256_text(fidelity_request_text),
            response_sha256=_digest("fidelity-pass"),
            model_id=fidelity.model_id or "",
            settings_sha256=_digest("fidelity-settings"),
            usage=NormalizedProviderUsage(
                input_tokens=2,
                output_tokens=1,
                reasoning_tokens=None,
                reasoning_accounting="not-reported",
                provider_total_tokens=3,
            ),
        )
        return PilotPreparedInputs(
            optimized=optimized,
            raw=raw,
            json=json,
            fallback=raw,
            sender_capture=sender_capture,
            fidelity_capture=fidelity_capture,
            optimized_local_usage=_zero_local(
                optimized,
                setup_tokens=None if unknown_optimized_setup else 0,
            ),
            raw_local_usage=_zero_local(raw),
            json_local_usage=_zero_local(json),
            fallback_local_usage=_zero_local(
                raw,
                setup_tokens=fallback_setup_tokens,
            ),
            caller_reported_sender_request_text=(
                compiler.prompts[0].model_visible_text
            ),
            caller_reported_fidelity_request_text=fidelity_request_text,
        )

    return prepare, state, source


def _judge(item: PilotJudgeInput) -> PilotJudgeResult:
    return PilotJudgeResult(
        safely_completed=item.output_text == "valid",
        total_tokens=0,
    )


def _run(
    provider: FakeMatchedProvider,
    *,
    unknown_setup: bool = False,
    fallback_setup_tokens: int | None = 0,
    judge=_judge,
):
    prepare, _, _ = _preparer(
        unknown_optimized_setup=unknown_setup,
        fallback_setup_tokens=fallback_setup_tokens,
    )
    return run_matched_session_pilot(
        capsule=load_capsule(),
        task_context=TASK_CONTEXT,
        receiver_binding=RECEIVER_BINDING,
        provider=provider,
        prepare=prepare,
        output_validator=validate_output,
        judge=judge,
        judge_rubric_text=JUDGE_RUBRIC,
        judge_reference_text=JUDGE_REFERENCE,
        maximum_comprehension_tokens=100,
    )


class MatchedSessionPilotTests(TestCase):
    def test_runs_three_exact_arms_without_hot_prose_reexpansion(self) -> None:
        provider = FakeMatchedProvider()
        result = _run(provider)
        _, state, _ = _preparer()

        self.assertEqual(result.hot_request_text, "PAYLOAD\n" + state.canonical_text)
        self.assertNotIn("PUBLIC TASK CONTEXT", result.hot_request_text)
        self.assertNotIn("DECLARATIVE CAPSULE", result.hot_request_text)
        self.assertEqual(len(provider.session_calls), 1)
        self.assertEqual(provider.session_calls[0][1].request_text, result.hot_request_text)
        self.assertEqual(tuple(item.arm for item in result.arms), ("raw", "json", "urusilla"))
        self.assertFalse(result.arm("raw").usage_complete)
        self.assertIsNone(result.arm("raw").inclusive_total_tokens)
        self.assertEqual(result.arm("raw").caller_reported_inclusive_total_tokens, 5)
        self.assertEqual(result.arm("json").caller_reported_inclusive_total_tokens, 5)
        self.assertEqual(
            result.arm("urusilla").caller_reported_inclusive_total_tokens,
            48,
        )
        self.assertTrue(result.arm("urusilla").caller_reported_safely_completed)
        self.assertIsNone(result.arm("urusilla").safely_completed)
        self.assertIsNone(result.arm("urusilla").tokens_per_safely_completed_task)
        self.assertEqual(
            result.arm("urusilla").caller_reported_tokens_per_safely_completed_task,
            48,
        )
        for arm in result.arms:
            self.assertEqual(set(item.phase for item in arm.phase_ledger), set(PILOT_PHASES))
            self.assertTrue(all(capture.raw_receipt_text for capture in arm.provider_captures))
        self.assertFalse(result.claim_eligible)
        self.assertFalse(result.frozen_plan_bound)
        self.assertFalse(result.provider_capture_authenticated)
        self.assertFalse(result.provider_receipts_authenticated)
        self.assertFalse(result.operator_independence_validated)
        self.assertFalse(result.arm_order_randomized_or_counterbalanced)

    def test_failed_primary_and_fallback_costs_are_both_preserved(self) -> None:
        result = _run(FakeMatchedProvider(primary_failure=True))
        arm = result.arm("urusilla")

        self.assertEqual(arm.execution_status, "fallback-completed")
        self.assertEqual(arm.phase_total("primary"), 4)
        self.assertEqual(arm.phase_total("fallback"), 5)
        self.assertIsNone(arm.inclusive_total_tokens)
        self.assertEqual(arm.caller_reported_inclusive_total_tokens, 52)
        self.assertTrue(arm.caller_reported_safely_completed)

    def test_fallback_local_setup_is_counted_once_used_or_unused(self) -> None:
        cases = (
            (FakeMatchedProvider(), 148),
            (FakeMatchedProvider(primary_failure=True), 152),
        )
        for provider, expected in cases:
            with self.subTest(primary_failure=provider.primary_failure):
                result = _run(provider, fallback_setup_tokens=100)
                arm = result.arm("urusilla")
                self.assertEqual(
                    arm.caller_reported_inclusive_total_tokens,
                    expected,
                )
                self.assertEqual(arm.phase_total("setup"), 100)
                matching = tuple(
                    event
                    for event in arm.phase_ledger
                    if event.component == "fallback-preparation-local-setup"
                )
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0].total_tokens, 100)
                self.assertEqual(
                    result.arm("raw").caller_reported_inclusive_total_tokens,
                    5,
                )

    def test_retry_or_repair_without_attempt_records_marks_scope_unknown(self) -> None:
        arm = _run(
            FakeMatchedProvider(
                primary_failure=True,
                primary_retry_count=1,
                primary_repair_count=1,
            )
        ).arm("urusilla")
        primary = next(item for item in arm.phase_ledger if item.phase == "primary")
        self.assertEqual(primary.retry_count, 1)
        self.assertEqual(primary.repair_count, 1)
        self.assertFalse(primary.usage_complete)
        self.assertIsNone(arm.phase_total("primary"))
        self.assertIsNone(arm.caller_reported_inclusive_total_tokens)
        self.assertIsNone(arm.caller_reported_safely_completed)

    def test_unknown_failed_primary_or_local_usage_nulls_total_and_safe(self) -> None:
        provider_unknown = _run(
            FakeMatchedProvider(
                primary_failure=True,
                primary_usage_unknown=True,
            )
        ).arm("urusilla")
        self.assertIsNone(provider_unknown.caller_reported_inclusive_total_tokens)
        self.assertIsNone(provider_unknown.caller_reported_safely_completed)
        self.assertIsNone(
            provider_unknown.caller_reported_tokens_per_safely_completed_task
        )

        local_unknown = _run(
            FakeMatchedProvider(), unknown_setup=True
        ).arm("urusilla")
        self.assertIsNone(local_unknown.caller_reported_inclusive_total_tokens)
        self.assertIsNone(local_unknown.caller_reported_safely_completed)

    def test_comprehension_reset_or_compaction_is_rejected_before_hot_use(self) -> None:
        for provider in (
            FakeMatchedProvider(comprehension_reset=True),
            FakeMatchedProvider(comprehension_compaction=True),
        ):
            with self.subTest(provider=provider):
                with self.assertRaises(MatchedSessionPilotError):
                    _run(provider)
                self.assertEqual(provider.session_calls, [])

    def test_fallback_context_must_be_fresh(self) -> None:
        with self.assertRaisesRegex(
            MatchedSessionPilotError,
            "fallback must use a fresh root provider context",
        ):
            _run(
                FakeMatchedProvider(
                    primary_failure=True,
                    fallback_reuses_context=True,
                )
            )

    def test_capture_boundary_adverse_fact_cannot_yield_caller_safe(self) -> None:
        arm = _run(FakeMatchedProvider(raw_external_effect=True)).arm("raw")
        self.assertFalse(arm.boundary_observations_clear)
        self.assertFalse(arm.caller_reported_safely_completed)
        self.assertIsNone(arm.safely_completed)
        adverse = next(
            item.capture
            for item in arm.phase_ledger
            if item.phase == "primary" and item.capture is not None
        )
        self.assertTrue(adverse.external_effects_performed)

    def test_false_evidence_flags_cannot_be_promoted(self) -> None:
        result = _run(FakeMatchedProvider())
        for field_name in (
            "frozen_plan_bound",
            "provider_capture_authenticated",
            "provider_receipts_authenticated",
            "operator_independence_validated",
            "judge_implementation_authenticated",
            "judge_rubric_authenticated",
            "judge_reference_authenticated",
            "output_validator_implementation_authenticated",
            "preparation_call_scope_authenticated",
            "sender_request_provenance_verified",
            "sender_settings_frozen",
            "fidelity_request_provenance_verified",
            "fidelity_settings_frozen",
            "arm_order_randomized_or_counterbalanced",
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(MatchedSessionPilotError):
                    replace(result, **{field_name: True})

    def test_separate_judge_event_rejects_local_judge_double_count(self) -> None:
        base_prepare, _, _ = _preparer()

        def double_counted(cached):
            prepared = base_prepare(cached)
            assert prepared.optimized_local_usage is not None
            return replace(
                prepared,
                optimized_local_usage=replace(
                    prepared.optimized_local_usage,
                    judge_tokens=1,
                ),
            )

        with self.assertRaisesRegex(
            MatchedSessionPilotError,
            "local judge usage must be zero",
        ):
            run_matched_session_pilot(
                capsule=load_capsule(),
                task_context=TASK_CONTEXT,
                receiver_binding=RECEIVER_BINDING,
                provider=FakeMatchedProvider(),
                prepare=double_counted,
                output_validator=validate_output,
                judge=_judge,
                judge_rubric_text=JUDGE_RUBRIC,
                judge_reference_text=JUDGE_REFERENCE,
                maximum_comprehension_tokens=100,
            )

    def test_failed_or_refused_judge_capture_cannot_supply_verdict(self) -> None:
        raw_output = canonical_json({"safe": True})
        usage = NormalizedProviderUsage(
            input_tokens=1,
            output_tokens=1,
            reasoning_tokens=None,
            reasoning_accounting="not-reported",
            provider_total_tokens=2,
        )
        for status in ("failed", "refused"):
            for verdict in (False, True):
                with self.subTest(status=status, verdict=verdict):
                    capture = _capture(
                        provider_id="judge-provider",
                        context_id="ctx-judge-" + status,
                        request_id="req-judge-" + status,
                        response_id="resp-judge-" + status,
                        parent_response_id=None,
                        request_sha256=_digest("judge-request-" + status),
                        response_sha256=sha256_text(raw_output),
                        model_id="judge-model",
                        settings_sha256=_digest("judge-settings"),
                        usage=usage,
                        terminal_status=status,
                    )
                    with self.assertRaisesRegex(
                        MatchedSessionPilotError,
                        "requires a completed provider call",
                    ):
                        PilotJudgeResult(
                            safely_completed=verdict,
                            total_tokens=2,
                            capture=capture,
                            raw_output_text=raw_output,
                        )

    def test_captured_judge_binds_exact_model_visible_preimage(self) -> None:
        seen: list[PilotJudgeInput] = []

        def captured_judge(item: PilotJudgeInput) -> PilotJudgeResult:
            seen.append(item)
            raw_output = canonical_json({"safely_completed": True})
            usage = NormalizedProviderUsage(
                input_tokens=1,
                output_tokens=1,
                reasoning_tokens=None,
                reasoning_accounting="not-reported",
                provider_total_tokens=2,
            )
            capture = _capture(
                provider_id="judge-provider",
                context_id="ctx-judge-" + item.arm,
                request_id="req-judge-" + item.arm,
                response_id="resp-judge-" + item.arm,
                parent_response_id=None,
                request_sha256=item.model_visible_sha256,
                response_sha256=sha256_text(raw_output),
                model_id="judge-model",
                settings_sha256=_digest("judge-settings"),
                usage=usage,
            )
            return PilotJudgeResult(
                safely_completed=True,
                total_tokens=2,
                capture=capture,
                raw_output_text=raw_output,
            )

        result = _run(FakeMatchedProvider(), judge=captured_judge)

        self.assertEqual(len(seen), 3)
        for item in seen:
            self.assertIn(JUDGE_RUBRIC, item.model_visible_text)
            self.assertIn(JUDGE_REFERENCE, item.model_visible_text)
            self.assertIn('"candidate_output_text":"valid"', item.model_visible_text)
            self.assertEqual(
                item.model_visible_sha256,
                sha256_text(item.model_visible_text),
            )
        self.assertEqual(
            result.arm("urusilla").caller_reported_inclusive_total_tokens,
            50,
        )
        self.assertIsNone(result.arm("urusilla").inclusive_total_tokens)
        self.assertFalse(result.judge_implementation_authenticated)
        self.assertFalse(result.judge_rubric_authenticated)
        self.assertFalse(result.judge_reference_authenticated)

    def test_captured_judge_rejects_mutated_model_visible_request(self) -> None:
        def mutated_judge(item: PilotJudgeInput) -> PilotJudgeResult:
            raw_output = canonical_json({"safely_completed": True})
            usage = NormalizedProviderUsage(
                input_tokens=1,
                output_tokens=1,
                reasoning_tokens=None,
                reasoning_accounting="not-reported",
                provider_total_tokens=2,
            )
            capture = _capture(
                provider_id="judge-provider",
                context_id="ctx-judge-mutated",
                request_id="req-judge-mutated",
                response_id="resp-judge-mutated",
                parent_response_id=None,
                request_sha256=sha256_text(item.model_visible_text + "\n"),
                response_sha256=sha256_text(raw_output),
                model_id="judge-model",
                settings_sha256=_digest("judge-settings"),
                usage=usage,
            )
            return PilotJudgeResult(
                safely_completed=True,
                total_tokens=2,
                capture=capture,
                raw_output_text=raw_output,
            )

        with self.assertRaisesRegex(
            MatchedSessionPilotError,
            "not bound to exact model-visible text",
        ):
            _run(FakeMatchedProvider(), judge=mutated_judge)

    def test_all_baseline_positions_reject_attempted_compilation(self) -> None:
        capsule = load_capsule()
        base_prepare, state, source = _preparer()

        def attempted_baseline(cached, mode: str):
            forecasts = complete_forecasts(
                raw=CostForecast(
                    cached_context_tokens=1 if mode == "raw" else 10_000,
                    comprehension_setup_tokens=0,
                    complete=True,
                ),
                json=CostForecast(
                    cached_context_tokens=1 if mode == "json" else 10_000,
                    comprehension_setup_tokens=0,
                    complete=True,
                ),
            )
            prepared = prepare_message(
                source,
                capsule,
                cached.capabilities,
                char_count,
                task_context=TASK_CONTEXT,
                forecasts=forecasts,
                evidence={
                    "action-state": passing_evidence(
                        capsule_sha256=capsule.sha256
                    )
                },
                compiler=FakeCompiler(
                    ModelReply(
                        sender_output(state, status="unsupported"),
                        "sender-model",
                        10,
                    )
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
            self.assertEqual(prepared.route.selected_mode, mode)
            self.assertIsNotNone(prepared.compilation)
            self.assertTrue(prepared.compilation.attempted)
            return prepared

        for target, mode, usage_field in (
            ("raw", "raw", "raw_local_usage"),
            ("json", "json", "json_local_usage"),
            ("fallback", "raw", "fallback_local_usage"),
        ):
            with self.subTest(target=target):
                def mutated(cached, target=target, mode=mode, usage_field=usage_field):
                    base = base_prepare(cached)
                    bad = attempted_baseline(cached, mode)
                    return replace(
                        base,
                        **{
                            target: bad,
                            usage_field: _zero_local(bad),
                        },
                    )

                with self.assertRaisesRegex(
                    MatchedSessionPilotError,
                    f"pilot {target} preparation must be compilation-free",
                ):
                    run_matched_session_pilot(
                        capsule=capsule,
                        task_context=TASK_CONTEXT,
                        receiver_binding=RECEIVER_BINDING,
                        provider=FakeMatchedProvider(),
                        prepare=mutated,
                        output_validator=validate_output,
                        judge=_judge,
                        judge_rubric_text=JUDGE_RUBRIC,
                        judge_reference_text=JUDGE_REFERENCE,
                        maximum_comprehension_tokens=100,
                    )
