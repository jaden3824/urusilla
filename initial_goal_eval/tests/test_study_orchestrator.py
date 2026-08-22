"""End-to-end tests for the provider-free runtime/scorer bridge."""

from __future__ import annotations

from dataclasses import replace
import unittest

from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.execution_trace import task_input_sha256
from initial_goal_eval.study_orchestrator import (
    RuntimeScoringInput,
    RuntimeTaskScore,
    run_scored_hybrid_task,
)
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
        task_result, scoring_binding, judge_event = result.trace_artifacts(
            decision_event_sequence=1,
            receiver_event_sequence=4,
            judge_event_sequence=5,
            judge_local_event_id="task-fallback-judge",
        )
        self.assertTrue(task_result["task_success"])
        self.assertEqual(task_result["route"]["receiver_event_sequence"], 4)
        self.assertEqual(scoring_binding["output_sha256"], result.scoring_input.output_sha256)
        self.assertEqual(scoring_binding["terminal_status"], "completed")
        self.assertEqual(judge_event["phase"], "judge")
        self.assertIsNone(judge_event["source"]["usage"]["total_tokens"])
        self.assertEqual(
            judge_event["source"]["usage"]["hidden_accounting"],
            "not-reported",
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
            result.trace_artifacts(
                decision_event_sequence=1,
                receiver_event_sequence=4,
                judge_event_sequence=5,
                judge_local_event_id="task-routine-fallback-judge",
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
        _, scoring_binding, _ = result.trace_artifacts(
            decision_event_sequence=1,
            receiver_event_sequence=4,
            judge_event_sequence=5,
            judge_local_event_id="task-terminal-failure-judge",
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

    def test_observation_outside_caller_declared_probe_is_rejected(self):
        prepared = self._prepared()
        with self.assertRaisesRegex(VerificationError, "caller-declared parse probe"):
            run_scored_hybrid_task(
                task_id="task-unplanned-probe",
                **self._task_args(prepared),
                feature_tags=("null",),
                parse_probe=False,
                semantic_probe=True,
                negative_probe=True,
                prepared=prepared,
                receiver_adapter=runtime_test.FakeReceiverAdapter(
                    runtime_test.receiver_reply("valid")
                ),
                output_validator=runtime_test.validate_output,
                scorer=RecordingScorer(passing_score()),
                scorer_locks=SCORER_LOCKS,
                caller_expected_scorer_locks=SCORER_LOCKS,
                observed_local_usage=self.case._complete_local_usage(prepared),
            )

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
            replace(result, scorer_observation_sha256=sha256_ref({"forged": True}))
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
            )
        self.assertFalse(result.frozen_plan_bound)
        self.assertFalse(result.scorer_implementation_authenticated)
        with self.assertRaisesRegex(VerificationError, "authenticate plan or scorer"):
            replace(result, scorer_implementation_authenticated=True)


if __name__ == "__main__":
    unittest.main()
