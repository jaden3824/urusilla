"""End-to-end tests for the provider-neutral runtime/scorer bridge."""

from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.execution_trace import task_input_sha256
import initial_goal_eval.study_orchestrator as study_orchestrator
from initial_goal_eval.study_orchestrator import (
    RuntimeScoringInput,
    RuntimeTaskScore,
    run_preselected_scored_hybrid_task,
    run_scored_hybrid_task,
)
from urusilla_hybrid_runtime.runtime import ObservedLocalUsage
from urusilla_hybrid_runtime.tests import test_hybrid_runtime as runtime_test


SCORER_LOCKS = {
    "task_scorer": "sha256:" + "a" * 64,
    "parse_scorer": "sha256:" + "b" * 64,
    "semantic_scorer": "sha256:" + "c" * 64,
    "negative_scorer": "sha256:" + "d" * 64,
}
TASK_PROBES = {
    "feature_tags": ("negation", "null", "failure", "refusal"),
    "parse_probe": True,
    "semantic_probe": True,
    "negative_probe": True,
}


def passing_score(total_tokens: int = 0) -> RuntimeTaskScore:
    return RuntimeTaskScore(
        task_success=True,
        parse_valid=True,
        semantic_exact=True,
        negative_rejected=True,
        preservation={
            "negation": True,
            "null": True,
            "failure": True,
            "refusal": True,
        },
        safety={
            "unauthorized_external_effects": 0,
            "persistence_events": 0,
            "permission_expansions": 0,
            "spending_authority_events": 0,
            "unknown_schema_executions": 0,
        },
        scorer_kind="deterministic-local",
        total_tokens=total_tokens,
        usage_complete=True,
    )


def unsuccessful_score(total_tokens: int = 0) -> RuntimeTaskScore:
    return RuntimeTaskScore(
        task_success=False,
        parse_valid=None,
        semantic_exact=None,
        negative_rejected=None,
        preservation={
            "negation": None,
            "null": None,
            "failure": None,
            "refusal": None,
        },
        safety={
            "unauthorized_external_effects": 0,
            "persistence_events": 0,
            "permission_expansions": 0,
            "spending_authority_events": 0,
            "unknown_schema_executions": 0,
        },
        scorer_kind="deterministic-local",
        total_tokens=total_tokens,
        usage_complete=True,
    )


class RecordingScorer:
    def __init__(self, result: RuntimeTaskScore | Exception | object):
        self.result = result
        self.inputs: list[RuntimeScoringInput] = []

    def __call__(self, scoring_input: RuntimeScoringInput) -> RuntimeTaskScore:
        self.inputs.append(scoring_input)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result  # type: ignore[return-value]


class StudyOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        case = runtime_test.HybridExecutionContractTests(methodName="runTest")
        case.setUp()
        self.case = case

    def _prepared(self):
        prepared, _compiler = self.case._action_prepared()
        return prepared

    def _routine_prepared(self):
        source = "Repeat the verified status check. " * 500
        digest = runtime_test.ROUTINE_DIGEST
        routine = runtime_test.RoutineInvocation(
            routine_id="status-check",
            routine_sha256=digest,
            routine_definition_text=runtime_test.ROUTINE_DEFINITION_TEXT,
            source_text=source,
            source_sha256=runtime_test.source_text_sha256(source),
            task_context_text=runtime_test.TASK_CONTEXT.canonical_text,
            task_context_sha256=runtime_test.TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "5" * 64,
            payload={"artifact": 7},
            receiver_acknowledged=True,
            session_local=True,
            effect_free=True,
        )
        prepared = runtime_test.prepare_message(
            source,
            self.case.capsule,
            runtime_test.ReceiverCapabilities(
                session_routine_sha256=(digest,)
            ),
            runtime_test.char_count,
            task_context=runtime_test.TASK_CONTEXT,
            forecasts=runtime_test.complete_forecasts(),
            evidence={
                "routine": runtime_test.passing_evidence(
                    "routine-study", route_mode="routine"
                )
            },
            routine=routine,
            policy=runtime_test.RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=runtime_test.verify_utility,
            routine_verifier=runtime_test.verify_bound_artifact,
        )
        self.assertEqual(prepared.route.selected_mode, "routine")
        return prepared

    @staticmethod
    def _task_args(prepared):
        source_text = next(
            candidate.request.payload_text
            for candidate in prepared.route.candidates
            if candidate.mode == "raw" and candidate.request is not None
        )
        task_input_messages = (
            {"role": "user", "content": source_text},
        )
        return {
            "source_text": source_text,
            "task_input_messages": task_input_messages,
            "task_sha256": task_input_sha256(task_input_messages),
        }

    @staticmethod
    def _source_task_args(source_text):
        task_input_messages = (
            {"role": "user", "content": source_text},
        )
        return {
            "source_text": source_text,
            "task_input_messages": task_input_messages,
            "task_sha256": task_input_sha256(task_input_messages),
        }

    def _action_preselected_fixture(self):
        source = "Verify artifact seven without external effects. " * 800
        compiler = runtime_test.FakeCompiler(
            runtime_test.ModelReply(
                runtime_test.sender_output(self.case.state),
                "model-a",
                10,
            )
        )
        options = {
            "evidence": {
                "action-state": runtime_test.passing_evidence()
            },
            "compiler": compiler,
            "fidelity_verifier": runtime_test.verify_fidelity,
            "policy": runtime_test.action_policy(),
            "utility_evidence_verifier": runtime_test.verify_utility,
            "capsule_comprehension_verifier": (
                runtime_test.verify_comprehension
            ),
            "task_context_comprehension_verifier": (
                runtime_test.verify_task_context
            ),
        }
        return source, compiler, options

    def test_preselected_runner_covers_all_five_routes_before_outcome(self):
        silence_source = "Already delivered and no reply is required."
        silence_proof = runtime_test.SilenceProof(
            source_text=silence_source,
            source_sha256=runtime_test.source_text_sha256(silence_source),
            task_context_text=runtime_test.TASK_CONTEXT.canonical_text,
            task_context_sha256=runtime_test.TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "1" * 64,
            no_required_message=True,
            no_effectful_intent=True,
        )
        routine_source = "Repeat the verified status check. " * 500
        routine = runtime_test.RoutineInvocation(
            routine_id="status-check",
            routine_sha256=runtime_test.ROUTINE_DIGEST,
            routine_definition_text=runtime_test.ROUTINE_DEFINITION_TEXT,
            source_text=routine_source,
            source_sha256=runtime_test.source_text_sha256(routine_source),
            task_context_text=runtime_test.TASK_CONTEXT.canonical_text,
            task_context_sha256=runtime_test.TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "5" * 64,
            payload={"artifact": 7},
            receiver_acknowledged=True,
            session_local=True,
            effect_free=True,
        )
        action_source = "Verify artifact seven without external effects. " * 800
        action_compiler = runtime_test.FakeCompiler(
            runtime_test.ModelReply(
                runtime_test.sender_output(self.case.state),
                "model-a",
                10,
            )
        )
        cases = (
            (
                "silence",
                silence_source,
                runtime_test.ReceiverCapabilities(),
                runtime_test.complete_forecasts(),
                {
                    "evidence": {
                        "silence": runtime_test.passing_evidence(
                            "silence-runner", route_mode="silence"
                        )
                    },
                    "silence_proof": silence_proof,
                    "utility_evidence_verifier": runtime_test.verify_utility,
                    "silence_verifier": runtime_test.verify_bound_artifact,
                },
                (),
            ),
            (
                "routine",
                routine_source,
                runtime_test.ReceiverCapabilities(
                    session_routine_sha256=(runtime_test.ROUTINE_DIGEST,)
                ),
                runtime_test.complete_forecasts(),
                {
                    "evidence": {
                        "routine": runtime_test.passing_evidence(
                            "routine-runner", route_mode="routine"
                        )
                    },
                    "routine": routine,
                    "policy": runtime_test.RouterPolicy(
                        receiver_total_token_ceiling=10_000
                    ),
                    "utility_evidence_verifier": runtime_test.verify_utility,
                    "routine_verifier": runtime_test.verify_bound_artifact,
                },
                (runtime_test.receiver_reply(),),
            ),
            (
                "action-state",
                action_source,
                runtime_test.action_receiver(self.case.capsule.sha256),
                runtime_test.complete_forecasts(),
                {
                    "evidence": {
                        "action-state": runtime_test.passing_evidence()
                    },
                    "compiler": action_compiler,
                    "fidelity_verifier": runtime_test.verify_fidelity,
                    "policy": runtime_test.action_policy(),
                    "utility_evidence_verifier": runtime_test.verify_utility,
                    "capsule_comprehension_verifier": (
                        runtime_test.verify_comprehension
                    ),
                    "task_context_comprehension_verifier": (
                        runtime_test.verify_task_context
                    ),
                },
                (runtime_test.receiver_reply(),),
            ),
            (
                "raw",
                "raw source",
                runtime_test.ReceiverCapabilities(supports_json=False),
                runtime_test.complete_forecasts(),
                {},
                (runtime_test.receiver_reply(),),
            ),
            (
                "json",
                "{}",
                runtime_test.ReceiverCapabilities(),
                runtime_test.complete_forecasts(
                    raw=runtime_test.CostForecast(
                        receiver_output_tokens=1_000,
                        complete=True,
                    )
                ),
                {},
                (runtime_test.receiver_reply(),),
            ),
        )

        observed_modes = []
        for expected_mode, source, receiver, forecasts, options, replies in cases:
            with self.subTest(mode=expected_mode):
                events = []
                real_prepare = runtime_test.prepare_message

                def recorded_prepare(*args, **kwargs):
                    prepared = real_prepare(*args, **kwargs)
                    events.append(f"selected:{prepared.route.selected_mode}")
                    return prepared

                class OrderedAdapter(runtime_test.FakeReceiverAdapter):
                    def complete(self, request):
                        events.append(f"receiver:{request.mode}")
                        return super().complete(request)

                class OrderedScorer(RecordingScorer):
                    def __call__(self, scoring_input):
                        events.append("scorer")
                        return super().__call__(scoring_input)

                adapter = OrderedAdapter(*replies)
                scorer = OrderedScorer(passing_score())
                with patch.object(
                    study_orchestrator,
                    "prepare_message",
                    side_effect=recorded_prepare,
                ):
                    result = run_preselected_scored_hybrid_task(
                        task_id=f"task-{expected_mode}",
                        **self._source_task_args(source),
                        **TASK_PROBES,
                        capsule=self.case.capsule,
                        receiver=receiver,
                        token_counter=runtime_test.char_count,
                        task_context=runtime_test.TASK_CONTEXT,
                        forecasts=forecasts,
                        route_options=options,
                        receiver_adapter=adapter,
                        output_validator=runtime_test.validate_output,
                        scorer=scorer,
                        scorer_locks=SCORER_LOCKS,
                        caller_expected_scorer_locks=SCORER_LOCKS,
                    )

                observed_modes.append(result.scoring_input.selected_mode)
                self.assertEqual(result.scoring_input.selected_mode, expected_mode)
                self.assertEqual(events[0], f"selected:{expected_mode}")
                self.assertEqual(events[-1], "scorer")
                self.assertEqual(adapter.calls, int(expected_mode != "silence"))
                self.assertEqual(
                    tuple(
                        candidate.mode
                        for candidate in result.execution.prepared.route.candidates
                    ),
                    ("silence", "routine", "action-state", "raw", "json"),
                )
                for candidate in result.execution.prepared.route.candidates:
                    request = candidate.request
                    if request is not None:
                        self.assertIsNone(request.natural_language_expansion)
                        self.assertFalse(request.decode_before_model)
                if expected_mode == "silence":
                    _, binding = result.diagnostic_fragments(
                        decision_event_sequence=1,
                        receiver_event_sequence=None,
                    )
                    self.assertIsNone(binding["scored_output_event_sequence"])
                    with self.assertRaisesRegex(
                        VerificationError,
                        "keep receiver event sequences null",
                    ):
                        result.diagnostic_fragments(
                            decision_event_sequence=1,
                            receiver_event_sequence=2,
                        )
                else:
                    result.diagnostic_fragments(
                        decision_event_sequence=1,
                        receiver_event_sequence=2,
                    )
                    with self.assertRaisesRegex(
                        VerificationError,
                        "requires a later receiver/fallback event",
                    ):
                        result.diagnostic_fragments(
                            decision_event_sequence=1,
                            receiver_event_sequence=None,
                        )

        self.assertEqual(
            observed_modes,
            ["silence", "routine", "action-state", "raw", "json"],
        )

    def test_preselected_runner_preserves_fallback_and_unknown_ledger(self):
        source = "Verify artifact seven without external effects. " * 800
        compiler = runtime_test.FakeCompiler(
            runtime_test.ModelReply(
                runtime_test.sender_output(self.case.state),
                "model-a",
                10,
            )
        )
        scorer = RecordingScorer(passing_score())
        result = run_preselected_scored_hybrid_task(
            task_id="task-preselected-fallback",
            **self._source_task_args(source),
            **TASK_PROBES,
            capsule=self.case.capsule,
            receiver=runtime_test.action_receiver(self.case.capsule.sha256),
            token_counter=runtime_test.char_count,
            task_context=runtime_test.TASK_CONTEXT,
            forecasts=runtime_test.complete_forecasts(),
            route_options={
                "evidence": {
                    "action-state": runtime_test.passing_evidence()
                },
                "compiler": compiler,
                "fidelity_verifier": runtime_test.verify_fidelity,
                "policy": runtime_test.action_policy(),
                "utility_evidence_verifier": runtime_test.verify_utility,
                "capsule_comprehension_verifier": (
                    runtime_test.verify_comprehension
                ),
                "task_context_comprehension_verifier": (
                    runtime_test.verify_task_context
                ),
            },
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("invalid"),
                runtime_test.receiver_reply("valid"),
            ),
            output_validator=runtime_test.validate_output,
            scorer=scorer,
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
        )

        self.assertEqual(result.scoring_input.selected_mode, "action-state")
        self.assertIn(result.scoring_input.final_mode, {"raw", "json"})
        self.assertEqual(result.execution.receiver_calls, 2)
        self.assertEqual(scorer.inputs[0].output_text, "valid")
        ledger = result.execution.observed_ledger
        self.assertIsNotNone(ledger)
        self.assertFalse(ledger.scope_complete)
        self.assertIsNone(ledger.phase_total("fallback"))
        self.assertIsNone(result.caller_reported_inclusive_total_tokens)
        task_result, scoring_binding = result.diagnostic_fragments(
            decision_event_sequence=1,
            primary_receiver_event_sequence=4,
            receiver_event_sequence=7,
        )
        self.assertFalse(task_result["route"]["decode_before_model"])
        self.assertFalse(task_result["route"]["natural_language_expansion"])
        self.assertEqual(
            scoring_binding["output_sha256"],
            result.scoring_input.output_sha256,
        )

        with self.assertRaisesRegex(VerificationError, "fallback chronology"):
            result.diagnostic_fragments(
                decision_event_sequence=1,
                receiver_event_sequence=7,
            )
        with self.assertRaisesRegex(VerificationError, "fallback chronology"):
            result.diagnostic_fragments(
                decision_event_sequence=1,
                primary_receiver_event_sequence=7,
                receiver_event_sequence=4,
            )

    def test_pre_outcome_usage_factory_allows_only_setup_and_router(self):
        source = "raw source"
        forbidden_fields = (
            "repair_tokens",
            "fallback_tokens",
            "tool_tokens",
            "safety_tokens",
            "judge_tokens",
        )
        for field in forbidden_fields:
            with self.subTest(field=field):
                adapter = runtime_test.FakeReceiverAdapter(
                    runtime_test.receiver_reply("valid")
                )
                scorer = RecordingScorer(passing_score())
                factory_calls = []

                def factory(prepared, *, usage_field=field):
                    factory_calls.append(prepared)
                    return ObservedLocalUsage.for_prepared(
                        prepared,
                        **{usage_field: 0},
                    )

                with self.assertRaisesRegex(
                    VerificationError,
                    f"leave {field} unknown",
                ):
                    run_preselected_scored_hybrid_task(
                        task_id=f"task-pre-outcome-{field}",
                        **self._source_task_args(source),
                        **TASK_PROBES,
                        capsule=self.case.capsule,
                        receiver=runtime_test.ReceiverCapabilities(
                            supports_json=False
                        ),
                        token_counter=runtime_test.char_count,
                        task_context=runtime_test.TASK_CONTEXT,
                        forecasts=runtime_test.complete_forecasts(),
                        receiver_adapter=adapter,
                        output_validator=runtime_test.validate_output,
                        scorer=scorer,
                        scorer_locks=SCORER_LOCKS,
                        caller_expected_scorer_locks=SCORER_LOCKS,
                        observed_local_usage_factory=factory,
                    )
                self.assertEqual(len(factory_calls), 1)
                self.assertEqual(adapter.calls, 0)
                self.assertEqual(len(scorer.inputs), 0)

        external_score = RuntimeTaskScore(
            task_success=True,
            parse_valid=True,
            semantic_exact=True,
            negative_rejected=True,
            preservation={feature: True for feature in TASK_PROBES["feature_tags"]},
            safety={
                "unauthorized_external_effects": 0,
                "persistence_events": 0,
                "permission_expansions": 0,
                "spending_authority_events": 0,
                "unknown_schema_executions": 0,
            },
            scorer_kind="external-model",
            total_tokens=3,
            usage_complete=True,
        )
        result = run_preselected_scored_hybrid_task(
            task_id="task-pre-outcome-allowed",
            **self._source_task_args(source),
            **TASK_PROBES,
            capsule=self.case.capsule,
            receiver=runtime_test.ReceiverCapabilities(supports_json=False),
            token_counter=runtime_test.char_count,
            task_context=runtime_test.TASK_CONTEXT,
            forecasts=runtime_test.complete_forecasts(),
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("valid")
            ),
            output_validator=runtime_test.validate_output,
            scorer=RecordingScorer(external_score),
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage_factory=lambda prepared: (
                ObservedLocalUsage.for_prepared(
                    prepared,
                    setup_tokens=2,
                    router_tokens=4,
                )
            ),
        )
        self.assertEqual(result.score.total_tokens, 3)
        self.assertIsNone(result.execution.inclusive_total_tokens)
        self.assertIsNone(result.caller_reported_inclusive_total_tokens)
        self.assertIsNone(result.execution.observed_ledger.phase_total("judge"))

    def test_usage_factory_cannot_mutate_prepared_execution(self):
        source, compiler, options = self._action_preselected_fixture()
        adapter = runtime_test.FakeReceiverAdapter(
            runtime_test.receiver_reply("valid")
        )
        scorer = RecordingScorer(passing_score())
        factory_calls = []

        def mutating_factory(prepared):
            factory_calls.append(prepared)
            usage = ObservedLocalUsage.for_prepared(
                prepared,
                setup_tokens=0,
                router_tokens=0,
            )
            object.__setattr__(
                prepared.route.request,
                "payload_text",
                prepared.route.request.payload_text + " tampered",
            )
            return usage

        with self.assertRaisesRegex(
            VerificationError,
            "local usage factory changed the prepared execution binding",
        ):
            run_preselected_scored_hybrid_task(
                task_id="task-usage-factory-mutation",
                **self._source_task_args(source),
                **TASK_PROBES,
                capsule=self.case.capsule,
                receiver=runtime_test.action_receiver(
                    self.case.capsule.sha256
                ),
                token_counter=runtime_test.char_count,
                task_context=runtime_test.TASK_CONTEXT,
                forecasts=runtime_test.complete_forecasts(),
                route_options=options,
                receiver_adapter=adapter,
                output_validator=runtime_test.validate_output,
                scorer=scorer,
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks=SCORER_LOCKS,
                observed_local_usage_factory=mutating_factory,
            )

        self.assertEqual(len(factory_calls), 1)
        self.assertEqual(compiler.calls, 1)
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(len(scorer.inputs), 0)

    def test_fallback_final_output_alone_is_scored_and_all_cost_is_retained(self):
        prepared = self._prepared()
        scorer = RecordingScorer(passing_score())
        result = run_scored_hybrid_task(
            task_id="task-fallback",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("invalid"),
                runtime_test.receiver_reply("valid"),
            ),
            output_validator=runtime_test.validate_output,
            scorer=scorer,
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(
                prepared,
                fallback_tokens=1,
            ),
        )

        self.assertEqual(result.execution.receiver_calls, 2)
        self.assertEqual(result.execution.primary.reply.text, "invalid")
        self.assertEqual(result.execution.fallback.reply.text, "valid")
        self.assertEqual(len(scorer.inputs), 1)
        self.assertEqual(scorer.inputs[0].output_text, "valid")
        self.assertNotIn("primary_output_text", scorer.inputs[0].value)
        self.assertEqual(result.execution.inclusive_total_tokens, 37)
        self.assertEqual(result.caller_reported_inclusive_total_tokens, 37)
        self.assertIsNone(result.inclusive_total_tokens)
        self.assertTrue(result.caller_reported_safely_completed)
        self.assertIsNone(result.safely_completed)
        self.assertEqual(
            result.scoring_input.fallback_from,
            "action-state:receiver:semantic-invalid",
        )
        task_result, scoring_binding = result.diagnostic_fragments(
            decision_event_sequence=1,
            primary_receiver_event_sequence=4,
            receiver_event_sequence=7,
        )
        self.assertTrue(task_result["task_success"])
        self.assertEqual(task_result["route"]["receiver_event_sequence"], 7)
        self.assertEqual(scoring_binding["output_sha256"], result.scoring_input.output_sha256)
        self.assertEqual(scoring_binding["terminal_status"], "completed")
        with self.assertRaisesRegex(VerificationError, "captured judge event"):
            result.trace_artifacts(
                decision_event_sequence=1,
                primary_receiver_event_sequence=4,
                receiver_event_sequence=7,
                judge_event_sequence=8,
                judge_local_event_id="task-fallback-judge",
            )

    def test_failed_primary_cost_remains_unknown_after_successful_fallback(self):
        prepared = self._prepared()
        scorer = RecordingScorer(passing_score())
        result = run_scored_hybrid_task(
            task_id="task-unknown-cost",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                RuntimeError("provider failed"),
                runtime_test.receiver_reply("valid"),
            ),
            output_validator=runtime_test.validate_output,
            scorer=scorer,
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(prepared),
        )

        self.assertTrue(result.score.task_success)
        self.assertTrue(result.caller_reported_safely_completed)
        self.assertIsNone(result.safely_completed)
        self.assertIsNone(result.execution.inclusive_total_tokens)
        self.assertIsNone(result.caller_reported_inclusive_total_tokens)
        self.assertIsNone(result.inclusive_total_tokens)
        self.assertEqual(
            result.scoring_input.fallback_from,
            "action-state:receiver:receiver-call-failed",
        )

    def test_routine_fallback_is_labelled_honestly_but_not_trace_projected(self):
        prepared = self._routine_prepared()
        result = run_scored_hybrid_task(
            task_id="task-routine-fallback",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("invalid"),
                runtime_test.receiver_reply("valid"),
            ),
            output_validator=runtime_test.validate_output,
            scorer=RecordingScorer(passing_score()),
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(
                prepared,
                fallback_tokens=1,
            ),
        )
        self.assertEqual(
            result.scoring_input.fallback_from,
            "routine:receiver:semantic-invalid",
        )
        with self.assertRaisesRegex(VerificationError, "receiver fallback mode"):
            result.diagnostic_fragments(
                decision_event_sequence=1,
                receiver_event_sequence=4,
            )

    def test_scorer_failure_is_preserved_as_null_not_success_or_zero(self):
        prepared = self._prepared()
        scorer = RecordingScorer(RuntimeError("scorer unavailable"))
        result = run_scored_hybrid_task(
            task_id="task-scorer-failure",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("valid")
            ),
            output_validator=runtime_test.validate_output,
            scorer=scorer,
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(prepared),
        )

        self.assertEqual(result.score.failure, "scorer-call-failed")
        self.assertIsNone(result.score.task_success)
        self.assertIsNone(result.score.total_tokens)
        self.assertIsNone(result.caller_reported_safely_completed)
        self.assertIsNone(result.safely_completed)
        self.assertIsNone(result.inclusive_total_tokens)
        with self.assertRaisesRegex(VerificationError, "captured judge event"):
            result.trace_artifacts(
                decision_event_sequence=1,
                receiver_event_sequence=2,
                judge_event_sequence=3,
                judge_local_event_id="task-scorer-failure-judge",
            )

    def test_terminal_provider_failure_keeps_output_digest_null(self):
        prepared = self._prepared()
        scorer = RecordingScorer(unsuccessful_score())
        result = run_scored_hybrid_task(
            task_id="task-terminal-failure",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                RuntimeError("primary failed"),
                RuntimeError("fallback failed"),
            ),
            output_validator=runtime_test.validate_output,
            scorer=scorer,
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(prepared),
        )

        self.assertEqual(len(scorer.inputs), 1)
        self.assertEqual(result.scoring_input.terminal_status, "provider_error")
        self.assertIsNone(result.scoring_input.output_text)
        self.assertIsNone(result.scoring_input.output_sha256)
        self.assertTrue(result.scoring_input.terminal_observation_sha256.startswith("sha256:"))
        self.assertFalse(result.caller_reported_safely_completed)
        self.assertIsNone(result.safely_completed)
        _, scoring_binding = result.diagnostic_fragments(
            decision_event_sequence=1,
            primary_receiver_event_sequence=4,
            receiver_event_sequence=7,
        )
        self.assertIsNone(scoring_binding["output_sha256"])
        self.assertEqual(scoring_binding["terminal_status"], "provider_error")

    def test_positive_scorer_cannot_override_unknown_runtime_validation(self):
        prepared = self._prepared()
        result = run_scored_hybrid_task(
            task_id="task-unknown-runtime-validation",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("valid"),
                runtime_test.receiver_reply("valid"),
            ),
            output_validator=None,
            scorer=RecordingScorer(passing_score()),
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
        )
        self.assertTrue(result.score.task_success)
        self.assertIsNone(result.execution.safely_completed)
        self.assertIsNone(result.caller_reported_safely_completed)
        self.assertIsNone(result.safely_completed)

    def test_wrong_scorer_lock_fails_before_any_receiver_call(self):
        prepared = self._prepared()
        adapter = runtime_test.FakeReceiverAdapter(
            runtime_test.receiver_reply("valid")
        )
        with self.assertRaisesRegex(VerificationError, "declared scorer lock"):
            run_scored_hybrid_task(
                task_id="task-lock",
                **self._task_args(prepared),
                **TASK_PROBES,
                prepared=prepared,
                receiver_adapter=adapter,
                output_validator=runtime_test.validate_output,
                scorer=RecordingScorer(passing_score()),
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks={
                    **SCORER_LOCKS,
                    "task_scorer": "sha256:" + "e" * 64,
                },
            )
        self.assertEqual(adapter.calls, 0)

    def test_task_source_mismatch_fails_before_any_receiver_call(self):
        prepared = self._prepared()
        adapter = runtime_test.FakeReceiverAdapter(
            runtime_test.receiver_reply("valid")
        )
        source_text = self._task_args(prepared)["source_text"]
        foreign_messages = (
            {"role": "user", "content": "different frozen task"},
        )
        with self.assertRaisesRegex(VerificationError, "exact natural-language source"):
            run_scored_hybrid_task(
                task_id="task-relabel",
                task_sha256=task_input_sha256(foreign_messages),
                source_text=source_text,
                task_input_messages=foreign_messages,
                **TASK_PROBES,
                prepared=prepared,
                receiver_adapter=adapter,
                output_validator=runtime_test.validate_output,
                scorer=RecordingScorer(passing_score()),
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks=SCORER_LOCKS,
            )
        self.assertEqual(adapter.calls, 0)

    def test_invalid_scoring_metadata_fails_before_any_receiver_call(self):
        prepared = self._prepared()
        base = {
            "task_id": "task-metadata",
            **self._task_args(prepared),
            **TASK_PROBES,
        }
        cases = (
            ("task-id", {"task_id": ""}, "task_id"),
            (
                "feature-tags",
                {"feature_tags": ("null", "null")},
                "feature_tags",
            ),
            (
                "feature-tag-type",
                {"feature_tags": (["null"],)},
                "feature_tags",
            ),
            ("parse-probe", {"parse_probe": 1}, "parse_probe"),
            ("semantic-probe", {"semantic_probe": None}, "semantic_probe"),
            ("negative-probe", {"negative_probe": "yes"}, "negative_probe"),
        )
        for label, mutation, error in cases:
            with self.subTest(label=label):
                adapter = runtime_test.FakeReceiverAdapter(
                    runtime_test.receiver_reply("valid")
                )
                with self.assertRaisesRegex(VerificationError, error):
                    run_scored_hybrid_task(
                        **{**base, **mutation},
                        prepared=prepared,
                        receiver_adapter=adapter,
                        output_validator=runtime_test.validate_output,
                        scorer=RecordingScorer(passing_score()),
                        scorer_locks=SCORER_LOCKS,
                        caller_expected_scorer_locks=SCORER_LOCKS,
                    )
                self.assertEqual(adapter.calls, 0)

    def test_preselected_requires_one_exact_user_message_before_compilation(self):
        source, compiler, options = self._action_preselected_fixture()
        valid = self._source_task_args(source)
        malformed = (
            (
                {"role": "system", "content": "prefix"},
                {"role": "user", "content": source},
            ),
            ({"role": "user", "content": source, "name": "extra"},),
            ({"role": "assistant", "content": source},),
        )
        for messages in malformed:
            with self.subTest(messages=messages):
                adapter = runtime_test.FakeReceiverAdapter(
                    runtime_test.receiver_reply("valid")
                )
                scorer = RecordingScorer(passing_score())
                with self.assertRaisesRegex(
                    VerificationError,
                    "exactly one user message",
                ):
                    run_preselected_scored_hybrid_task(
                        task_id="task-single-message",
                        task_sha256=valid["task_sha256"],
                        source_text=source,
                        task_input_messages=messages,
                        **TASK_PROBES,
                        capsule=self.case.capsule,
                        receiver=runtime_test.action_receiver(
                            self.case.capsule.sha256
                        ),
                        token_counter=runtime_test.char_count,
                        task_context=runtime_test.TASK_CONTEXT,
                        forecasts=runtime_test.complete_forecasts(),
                        route_options=options,
                        receiver_adapter=adapter,
                        output_validator=runtime_test.validate_output,
                        scorer=scorer,
                        scorer_locks=SCORER_LOCKS,
                        caller_expected_scorer_locks=SCORER_LOCKS,
                    )
                self.assertEqual(compiler.calls, 0)
                self.assertEqual(adapter.calls, 0)
                self.assertEqual(len(scorer.inputs), 0)

    def test_malformed_injected_interfaces_fail_before_compiler_or_receiver(self):
        class PropertyAdapter:
            def __init__(self):
                self.property_reads = 0

            @property
            def complete(self):
                self.property_reads += 1
                return lambda _request: runtime_test.receiver_reply("valid")

        class PropertyCompiler:
            def __init__(self):
                self.property_reads = 0

            @property
            def complete(self):
                self.property_reads += 1
                return lambda _prompt: None

        class PropertyCallable:
            def __init__(self):
                self.property_reads = 0

            @property
            def __call__(self):
                self.property_reads += 1
                return lambda _value: passing_score()

        cases = (
            (
                "receiver",
                {"receiver_adapter": object()},
                {},
                "receiver_adapter.complete",
            ),
            (
                "output-validator",
                {"output_validator": object()},
                {},
                "output_validator",
            ),
            ("scorer", {"scorer": object()}, {}, "scorer"),
            ("token-counter", {"token_counter": object()}, {}, "token_counter"),
            (
                "usage-factory",
                {"observed_local_usage_factory": object()},
                {},
                "local usage factory",
            ),
            (
                "verifier",
                {},
                {"fidelity_verifier": object()},
                "fidelity_verifier",
            ),
        )
        for label, direct_mutation, option_mutation, error in cases:
            with self.subTest(label=label):
                source, compiler, options = self._action_preselected_fixture()
                adapter = runtime_test.FakeReceiverAdapter(
                    runtime_test.receiver_reply("valid")
                )
                scorer = RecordingScorer(passing_score())
                kwargs = {
                    "task_id": f"task-bad-{label}",
                    **self._source_task_args(source),
                    **TASK_PROBES,
                    "capsule": self.case.capsule,
                    "receiver": runtime_test.action_receiver(
                        self.case.capsule.sha256
                    ),
                    "token_counter": runtime_test.char_count,
                    "task_context": runtime_test.TASK_CONTEXT,
                    "forecasts": runtime_test.complete_forecasts(),
                    "route_options": {**options, **option_mutation},
                    "receiver_adapter": adapter,
                    "output_validator": runtime_test.validate_output,
                    "scorer": scorer,
                    "scorer_locks": SCORER_LOCKS,
                    "caller_expected_scorer_locks": SCORER_LOCKS,
                    **direct_mutation,
                }
                with self.assertRaisesRegex(VerificationError, error):
                    run_preselected_scored_hybrid_task(**kwargs)
                self.assertEqual(compiler.calls, 0)
                self.assertEqual(adapter.calls, 0)
                self.assertEqual(len(scorer.inputs), 0)

        source, compiler, options = self._action_preselected_fixture()
        property_adapter = PropertyAdapter()
        with self.assertRaisesRegex(VerificationError, "receiver_adapter.complete"):
            run_preselected_scored_hybrid_task(
                task_id="task-property-adapter",
                **self._source_task_args(source),
                **TASK_PROBES,
                capsule=self.case.capsule,
                receiver=runtime_test.action_receiver(self.case.capsule.sha256),
                token_counter=runtime_test.char_count,
                task_context=runtime_test.TASK_CONTEXT,
                forecasts=runtime_test.complete_forecasts(),
                route_options=options,
                receiver_adapter=property_adapter,
                output_validator=runtime_test.validate_output,
                scorer=RecordingScorer(passing_score()),
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks=SCORER_LOCKS,
            )
        self.assertEqual(property_adapter.property_reads, 0)
        self.assertEqual(compiler.calls, 0)

        source, compiler, options = self._action_preselected_fixture()
        property_scorer = PropertyCallable()
        adapter = runtime_test.FakeReceiverAdapter(
            runtime_test.receiver_reply("valid")
        )
        with self.assertRaisesRegex(VerificationError, "statically callable"):
            run_preselected_scored_hybrid_task(
                task_id="task-property-scorer",
                **self._source_task_args(source),
                **TASK_PROBES,
                capsule=self.case.capsule,
                receiver=runtime_test.action_receiver(self.case.capsule.sha256),
                token_counter=runtime_test.char_count,
                task_context=runtime_test.TASK_CONTEXT,
                forecasts=runtime_test.complete_forecasts(),
                route_options=options,
                receiver_adapter=adapter,
                output_validator=runtime_test.validate_output,
                scorer=property_scorer,
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks=SCORER_LOCKS,
            )
        self.assertEqual(property_scorer.property_reads, 0)
        self.assertEqual(compiler.calls, 0)
        self.assertEqual(adapter.calls, 0)

        source, _compiler, options = self._action_preselected_fixture()
        property_compiler = PropertyCompiler()
        options["compiler"] = property_compiler
        adapter = runtime_test.FakeReceiverAdapter(
            runtime_test.receiver_reply("valid")
        )
        with self.assertRaisesRegex(VerificationError, "compiler.complete"):
            run_preselected_scored_hybrid_task(
                task_id="task-property-compiler",
                **self._source_task_args(source),
                **TASK_PROBES,
                capsule=self.case.capsule,
                receiver=runtime_test.action_receiver(self.case.capsule.sha256),
                token_counter=runtime_test.char_count,
                task_context=runtime_test.TASK_CONTEXT,
                forecasts=runtime_test.complete_forecasts(),
                route_options=options,
                receiver_adapter=adapter,
                output_validator=runtime_test.validate_output,
                scorer=RecordingScorer(passing_score()),
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks=SCORER_LOCKS,
            )
        self.assertEqual(property_compiler.property_reads, 0)
        self.assertEqual(adapter.calls, 0)

    def test_exact_core_types_fail_before_compiler_or_receiver(self):
        mutations = (
            ("capsule", object(), "exact Capsule"),
            ("receiver", object(), "exact ReceiverCapabilities"),
            ("task_context", object(), "exact PublicTaskContext"),
        )
        for field, value, error in mutations:
            with self.subTest(field=field):
                source, compiler, options = self._action_preselected_fixture()
                adapter = runtime_test.FakeReceiverAdapter(
                    runtime_test.receiver_reply("valid")
                )
                kwargs = {
                    "task_id": f"task-exact-{field}",
                    **self._source_task_args(source),
                    **TASK_PROBES,
                    "capsule": self.case.capsule,
                    "receiver": runtime_test.action_receiver(
                        self.case.capsule.sha256
                    ),
                    "token_counter": runtime_test.char_count,
                    "task_context": runtime_test.TASK_CONTEXT,
                    "forecasts": runtime_test.complete_forecasts(),
                    "route_options": options,
                    "receiver_adapter": adapter,
                    "output_validator": runtime_test.validate_output,
                    "scorer": RecordingScorer(passing_score()),
                    "scorer_locks": SCORER_LOCKS,
                    "caller_expected_scorer_locks": SCORER_LOCKS,
                    field: value,
                }
                with self.assertRaisesRegex(VerificationError, error):
                    run_preselected_scored_hybrid_task(**kwargs)
                self.assertEqual(compiler.calls, 0)
                self.assertEqual(adapter.calls, 0)

    def test_observation_outside_declared_scope_becomes_failed_score(self):
        prepared = self._prepared()
        adapter = runtime_test.FakeReceiverAdapter(
            runtime_test.receiver_reply("valid")
        )
        scorer = RecordingScorer(passing_score())
        result = run_scored_hybrid_task(
            task_id="task-unplanned-probe",
            **self._task_args(prepared),
            feature_tags=("null",),
            parse_probe=False,
            semantic_probe=True,
            negative_probe=True,
            prepared=prepared,
            receiver_adapter=adapter,
            output_validator=runtime_test.validate_output,
            scorer=scorer,
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(prepared),
        )
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(len(scorer.inputs), 1)
        self.assertEqual(
            result.score.failure,
            "scorer-output-outside-declared-scope",
        )
        self.assertIsNone(result.score.task_success)
        self.assertIsNone(result.score.total_tokens)
        self.assertFalse(result.score.usage_complete)
        self.assertIsNotNone(result.execution.observed_ledger)

    def test_nested_score_state_is_detached_and_observation_is_sealed(self):
        preservation = {
            "negation": True,
            "null": True,
            "failure": True,
            "refusal": True,
        }
        safety = {
            "unauthorized_external_effects": 0,
            "persistence_events": 0,
            "permission_expansions": 0,
            "spending_authority_events": 0,
            "unknown_schema_executions": 0,
        }
        score = RuntimeTaskScore(
            task_success=True,
            parse_valid=True,
            semantic_exact=True,
            negative_rejected=True,
            preservation=preservation,
            safety=safety,
            scorer_kind="deterministic-local",
            total_tokens=0,
            usage_complete=True,
        )
        preservation["null"] = False
        safety["permission_expansions"] = 1
        self.assertTrue(score.preservation["null"])
        self.assertEqual(score.safety["permission_expansions"], 0)

        prepared = self._prepared()
        result = run_scored_hybrid_task(
            task_id="task-seal",
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=runtime_test.FakeReceiverAdapter(
                runtime_test.receiver_reply("valid")
            ),
            output_validator=runtime_test.validate_output,
            scorer=RecordingScorer(score),
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=self.case._complete_local_usage(prepared),
        )
        with self.assertRaisesRegex(VerificationError, "minted by the orchestrator"):
            replace(
                result,
                scorer_observation_sha256=sha256_ref({"forged": True}),
                _factory_token=None,
            )
        forged_input = replace(
            result.scoring_input,
            output_text="forged",
            output_sha256=sha256_ref({"provider_output_text": "forged"}),
        )
        forged_observation = sha256_ref(
            {
                "schema_version": "urusilla-initial-goal-runtime-scorer-observation/1",
                "scorer_locks": dict(result.scorer_locks),
                "scoring_input": forged_input.value,
                "scorer_output": result.score.value,
            }
        )
        with self.assertRaisesRegex(VerificationError, "minted by the orchestrator"):
            replace(
                result,
                scoring_input=forged_input,
                scorer_observation_sha256=forged_observation,
                _factory_token=None,
            )
        self.assertFalse(hasattr(result, "_factory_token"))
        self.assertFalse(result.frozen_plan_bound)
        self.assertFalse(result.scorer_implementation_authenticated)
        with self.assertRaisesRegex(VerificationError, "minted by the orchestrator"):
            replace(
                result,
                scorer_implementation_authenticated=True,
                _factory_token=None,
            )


if __name__ == "__main__":
    unittest.main()
