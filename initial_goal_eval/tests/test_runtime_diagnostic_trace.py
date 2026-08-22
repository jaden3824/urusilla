"""Focused tests for the provider-neutral, claim-ineligible runtime trace."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.execution_trace import (
    task_input_sha256,
    validate_execution_trace,
)
from initial_goal_eval.receipt_store import ReceiptStore
from initial_goal_eval.runtime_diagnostic_trace import (
    COLD_RUNTIME_LEDGER_COMPONENT_ORDER,
    RUNTIME_DIAGNOSTIC_TRACE_SCHEMA,
    RUNTIME_LEDGER_COMPONENT_ORDER,
    build_runtime_diagnostic_trace,
    validate_runtime_diagnostic_trace,
)
from initial_goal_eval.study_orchestrator import (
    RuntimeScoringInput,
    RuntimeTaskScore,
    run_scored_hybrid_task,
)
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture
from initial_goal_eval.verifier import verify_result
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


def passing_score() -> RuntimeTaskScore:
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
        total_tokens=0,
        usage_complete=True,
    )


class RecordingScorer:
    def __init__(self, result: RuntimeTaskScore | Exception):
        self.result = result
        self.inputs: list[RuntimeScoringInput] = []

    def __call__(self, scoring_input: RuntimeScoringInput) -> RuntimeTaskScore:
        self.inputs.append(scoring_input)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class RuntimeDiagnosticTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        case = runtime_test.HybridExecutionContractTests(methodName="runTest")
        case.setUp()
        self.case = case

    @staticmethod
    def _task_args(prepared):
        source_text = next(
            candidate.request.payload_text
            for candidate in prepared.route.candidates
            if candidate.mode == "raw" and candidate.request is not None
        )
        task_input_messages = ({"role": "user", "content": source_text},)
        return {
            "source_text": source_text,
            "task_input_messages": task_input_messages,
            "task_sha256": task_input_sha256(task_input_messages),
        }

    def _run(
        self,
        prepared,
        adapter,
        *,
        task_id="task-diagnostic",
        scorer=None,
        observed_local_usage=None,
    ):
        return run_scored_hybrid_task(
            task_id=task_id,
            **self._task_args(prepared),
            **TASK_PROBES,
            prepared=prepared,
            receiver_adapter=adapter,
            output_validator=runtime_test.validate_output,
            scorer=scorer or RecordingScorer(passing_score()),
            scorer_locks=SCORER_LOCKS,
            caller_expected_scorer_locks=SCORER_LOCKS,
            observed_local_usage=observed_local_usage,
        )

    def _action_prepared(self):
        prepared, _compiler = self.case._action_prepared()
        return prepared

    @staticmethod
    def _reseal(value):
        ledger_record = value["observed_ledger"]
        scoring_input = value["scorer_observation"]["scoring_input"]
        if ledger_record is not None:
            ledger_record["sha256"] = sha256_ref(ledger_record["value"])
            scoring_input["observed_ledger_sha256"] = ledger_record["sha256"]
        observation = value["scorer_observation"]
        observation["scoring_input_sha256"] = sha256_ref(scoring_input)
        observation["scorer_observation_sha256"] = sha256_ref(
            {
                "schema_version": (
                    "urusilla-initial-goal-runtime-scorer-observation/1"
                ),
                "scorer_locks": observation["scorer_locks"],
                "scoring_input": scoring_input,
                "scorer_output": observation["scorer_output"],
            }
        )
        body = dict(value)
        body.pop("trace_sha256")
        value["trace_sha256"] = sha256_ref(body)
        return value

    def _routine_prepared(self):
        source = "Repeat the verified status check. " * 500
        routine = runtime_test.RoutineInvocation(
            routine_id="status-check",
            routine_sha256=runtime_test.ROUTINE_DIGEST,
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
                session_routine_sha256=(runtime_test.ROUTINE_DIGEST,)
            ),
            runtime_test.char_count,
            task_context=runtime_test.TASK_CONTEXT,
            forecasts=runtime_test.complete_forecasts(),
            evidence={
                "routine": runtime_test.passing_evidence(
                    "routine-diagnostic", route_mode="routine"
                )
            },
            routine=routine,
            policy=runtime_test.RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=runtime_test.verify_utility,
            routine_verifier=runtime_test.verify_bound_artifact,
        )
        self.assertEqual(prepared.route.selected_mode, "routine")
        return prepared

    def _silence_prepared(self):
        source = "Already delivered and no reply is required."
        proof = runtime_test.SilenceProof(
            source_text=source,
            source_sha256=runtime_test.source_text_sha256(source),
            task_context_text=runtime_test.TASK_CONTEXT.canonical_text,
            task_context_sha256=runtime_test.TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "1" * 64,
            no_required_message=True,
            no_effectful_intent=True,
        )
        return runtime_test.prepare_message(
            source,
            self.case.capsule,
            runtime_test.ReceiverCapabilities(),
            runtime_test.char_count,
            task_context=runtime_test.TASK_CONTEXT,
            forecasts=runtime_test.complete_forecasts(),
            evidence={
                "silence": runtime_test.passing_evidence(
                    "silence-diagnostic", route_mode="silence"
                )
            },
            silence_proof=proof,
            utility_evidence_verifier=runtime_test.verify_utility,
            silence_verifier=runtime_test.verify_bound_artifact,
        )

    def test_canonical_trace_records_five_candidates_and_exact_bindings(self):
        prepared = runtime_test.prepare_message(
            "raw source",
            self.case.capsule,
            runtime_test.ReceiverCapabilities(supports_json=False),
            runtime_test.char_count,
            task_context=runtime_test.TASK_CONTEXT,
            forecasts=runtime_test.complete_forecasts(),
        )
        scored = self._run(
            prepared,
            runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
            observed_local_usage=self.case._complete_local_usage(prepared),
        )
        trace = build_runtime_diagnostic_trace(scored)
        value = trace.value

        self.assertEqual(value["schema_version"], RUNTIME_DIAGNOSTIC_TRACE_SCHEMA)
        self.assertEqual(
            [candidate["mode"] for candidate in value["route"]["candidates"]],
            ["silence", "routine", "action-state", "raw", "json"],
        )
        self.assertEqual(
            value["route"]["selected_request_binding_sha256"],
            value["primary_execution"]["request_binding_sha256"],
        )
        self.assertEqual(
            value["task"]["output_sha256"],
            value["scorer_observation"]["scoring_input"]["output_sha256"],
        )
        self.assertEqual(
            value["observed_ledger"]["sha256"],
            value["scorer_observation"]["scoring_input"][
                "observed_ledger_sha256"
            ],
        )
        for candidate in value["route"]["candidates"]:
            self.assertFalse(candidate["claim_eligible"])
            if candidate["request"] is not None:
                self.assertIsNone(
                    candidate["request"]["natural_language_expansion"]
                )
                self.assertFalse(candidate["request"]["decode_before_model"])
        for name, flag in value["authority"].items():
            if name.endswith("_sha256"):
                self.assertIsNone(flag)
            else:
                self.assertFalse(flag)
        self.assertFalse(trace.claim_eligible)
        self.assertEqual(validate_runtime_diagnostic_trace(value), value)

    def test_silence_is_a_bound_zero_call_terminal_observation(self):
        scored = self._run(
            self._silence_prepared(), runtime_test.FakeReceiverAdapter()
        )
        value = build_runtime_diagnostic_trace(scored).value
        self.assertEqual(value["route"]["selected_mode"], "silence")
        self.assertEqual(value["primary_execution"]["calls"], 0)
        self.assertEqual(value["runtime_summary"]["receiver_calls"], 0)
        self.assertEqual(value["primary_execution"]["total_tokens"], 0)
        self.assertEqual(value["task"]["terminal_status"], "silenced")
        self.assertIsNone(value["task"]["output_text"])

    def test_routine_and_action_state_fallbacks_bind_primary_and_baseline(self):
        for selected_mode, prepared in (
            ("routine", self._routine_prepared()),
            ("action-state", self._action_prepared()),
        ):
            with self.subTest(selected_mode=selected_mode):
                scored = self._run(
                    prepared,
                    runtime_test.FakeReceiverAdapter(
                        runtime_test.receiver_reply("invalid"),
                        runtime_test.receiver_reply("valid"),
                    ),
                    task_id=f"task-{selected_mode}-fallback",
                    observed_local_usage=self.case._complete_local_usage(
                        prepared, fallback_tokens=1
                    ),
                )
                value = build_runtime_diagnostic_trace(scored).value
                self.assertEqual(value["route"]["selected_mode"], selected_mode)
                self.assertIn(value["route"]["final_mode"], {"raw", "json"})
                self.assertIsNotNone(value["fallback_execution"])
                self.assertTrue(
                    value["route"]["fallback_from"].startswith(
                        f"{selected_mode}:receiver:"
                    )
                )
                self.assertEqual(
                    value["fallback_execution"]["request_binding_sha256"],
                    value["route"]["fallback_request_binding_sha256"],
                )
                self.assertEqual(value["task"]["output_text"], "valid")

    def test_unknown_usage_and_failed_scorer_remain_unknown(self):
        prepared = self._action_prepared()
        unknown = self._run(
            prepared,
            runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
        )
        unknown_value = build_runtime_diagnostic_trace(unknown).value
        self.assertFalse(unknown_value["observed_ledger"]["value"]["scope_complete"])
        self.assertIsNone(
            unknown_value["observed_ledger"]["value"]["inclusive_total_tokens"]
        )
        self.assertIsNone(
            unknown_value["runtime_summary"][
                "caller_reported_inclusive_total_tokens"
            ]
        )

        prepared = self._action_prepared()
        failed = self._run(
            prepared,
            runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
            task_id="task-failed-scorer",
            scorer=RecordingScorer(RuntimeError("scorer unavailable")),
            observed_local_usage=self.case._complete_local_usage(prepared),
        )
        failed_value = build_runtime_diagnostic_trace(failed).value
        scorer_output = failed_value["scorer_observation"]["scorer_output"]
        self.assertEqual(scorer_output["failure"], "scorer-call-failed")
        self.assertIsNone(scorer_output["task_success"])
        self.assertIsNone(scorer_output["total_tokens"])
        self.assertIsNone(
            failed_value["runtime_summary"][
                "caller_reported_inclusive_total_tokens"
            ]
        )

    def test_tamper_and_cross_task_rebinding_fail_even_when_resealed(self):
        prepared = self._action_prepared()
        value = build_runtime_diagnostic_trace(
            self._run(
                prepared,
                runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
                task_id="task-a",
            )
        ).value

        tampered = deepcopy(value)
        tampered["task"]["output_text"] = "foreign output"
        body = dict(tampered)
        body.pop("trace_sha256")
        tampered["trace_sha256"] = sha256_ref(body)
        with self.assertRaisesRegex(VerificationError, "output text differs"):
            validate_runtime_diagnostic_trace(tampered)

        cross_task = deepcopy(value)
        cross_task["task"]["task_id"] = "task-b"
        cross_task["task"]["task_sha256"] = sha256_ref(
            {"foreign-task": "task-b"}
        )
        body = dict(cross_task)
        body.pop("trace_sha256")
        cross_task["trace_sha256"] = sha256_ref(body)
        with self.assertRaisesRegex(VerificationError, "task ID differs"):
            validate_runtime_diagnostic_trace(cross_task)

        broken_digest = deepcopy(value)
        broken_digest["route"]["selected_mode"] = "json"
        with self.assertRaisesRegex(VerificationError, "trace digest differs"):
            validate_runtime_diagnostic_trace(broken_digest)

    def test_coordinated_rehash_cannot_admit_malformed_runtime_evidence(self):
        prepared = self._action_prepared()
        original = build_runtime_diagnostic_trace(
            self._run(
                prepared,
                runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
                observed_local_usage=self.case._complete_local_usage(prepared),
            )
        ).value

        mutations = []

        malformed_execution = deepcopy(original)
        malformed_execution["primary_execution"]["calls"] = 0
        mutations.append((malformed_execution, "status/call/reply state"))

        malformed_cost = deepcopy(original)
        malformed_cost["route"]["selected_cost"]["router_tokens"] += 1
        malformed_cost["route"]["selected_cost"]["total_tokens"] += 1
        mutations.append((malformed_cost, "selected candidate cost differs"))

        malformed_baseline = deepcopy(original)
        malformed_baseline["route"]["best_baseline_tokens"] += 1
        mutations.append((malformed_baseline, "best baseline token binding"))

        malformed_locks = deepcopy(original)
        del malformed_locks["scorer_observation"]["scorer_locks"]["parse_scorer"]
        mutations.append((malformed_locks, "scorer_locks fields differ"))

        malformed_score_schema = deepcopy(original)
        malformed_score_schema["scorer_observation"]["scorer_output"][
            "schema_version"
        ] = "foreign-score/1"
        mutations.append((malformed_score_schema, "scoring output schema differs"))

        malformed_event = deepcopy(original)
        router_event = next(
            event
            for event in malformed_event["observed_ledger"]["value"]["events"]
            if event["component"] == "local-router"
        )
        router_event["total_tokens"] = "4"
        mutations.append((malformed_event, "total_tokens must be"))

        malformed_summary = deepcopy(original)
        malformed_summary["runtime_summary"]["receiver_calls"] = 2
        mutations.append((malformed_summary, "receiver call count differs"))

        for mutated, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_runtime_diagnostic_trace(self._reseal(mutated))

    def test_resealed_runtime_component_reorder_is_rejected(self):
        prepared = self._action_prepared()
        original = build_runtime_diagnostic_trace(
            self._run(
                prepared,
                runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
                observed_local_usage=self.case._complete_local_usage(prepared),
            )
        ).value
        events = original["observed_ledger"]["value"]["events"]
        self.assertEqual(
            tuple(event["component"] for event in events),
            RUNTIME_LEDGER_COMPONENT_ORDER,
        )

        reordered = deepcopy(original)
        events = reordered["observed_ledger"]["value"]["events"]
        events[3], events[4] = events[4], events[3]
        for sequence, event in enumerate(events):
            event["sequence"] = sequence

        with self.assertRaisesRegex(VerificationError, "component order differs"):
            validate_runtime_diagnostic_trace(self._reseal(reordered))

    def test_cold_comprehension_is_allowed_only_at_the_canonical_front(self):
        prepared = self._action_prepared()
        original = build_runtime_diagnostic_trace(
            self._run(
                prepared,
                runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
                observed_local_usage=self.case._complete_local_usage(prepared),
            )
        ).value
        cold_event = {
            "sequence": 0,
            "phase": "setup",
            "component": "cold-comprehension",
            "execution_binding_sha256": original["route"][
                "execution_binding_sha256"
            ],
            "artifact_binding_sha256": sha256_ref(
                {"cold-comprehension": "canonical-front"}
            ),
            "total_tokens": 0,
            "model_calls": 0,
            "input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "reasoning_accounting": None,
        }

        exact_front = deepcopy(original)
        events = exact_front["observed_ledger"]["value"]["events"]
        events.insert(0, deepcopy(cold_event))
        for sequence, event in enumerate(events):
            event["sequence"] = sequence
        exact_front = self._reseal(exact_front)
        self.assertEqual(
            tuple(event["component"] for event in events),
            COLD_RUNTIME_LEDGER_COMPONENT_ORDER,
        )
        self.assertEqual(
            validate_runtime_diagnostic_trace(exact_front),
            exact_front,
        )

        wrong_insertion = deepcopy(exact_front)
        events = wrong_insertion["observed_ledger"]["value"]["events"]
        cold = events.pop(0)
        events.insert(2, cold)
        for sequence, event in enumerate(events):
            event["sequence"] = sequence

        with self.assertRaisesRegex(VerificationError, "component order differs"):
            validate_runtime_diagnostic_trace(self._reseal(wrong_insertion))

    def test_diagnostic_schema_cannot_enter_trace_result_or_receipt_contracts(self):
        prepared = self._action_prepared()
        value = build_runtime_diagnostic_trace(
            self._run(
                prepared,
                runtime_test.FakeReceiverAdapter(runtime_test.receiver_reply()),
            )
        ).value
        plan, _result = build_synthetic_fixture()

        with self.assertRaises(VerificationError):
            validate_execution_trace(plan, value)
        with self.assertRaises(VerificationError):
            verify_result(plan, value)
        with self.assertRaises(VerificationError):
            ReceiptStore(value)
        self.assertNotEqual(value["schema_version"], "urusilla-execution-trace/2")
        self.assertNotEqual(
            value["schema_version"], "urusilla-initial-goal-study-result/1"
        )
        self.assertNotEqual(value["schema_version"], "urusilla-receipt-bundle/3")


if __name__ == "__main__":
    unittest.main()
