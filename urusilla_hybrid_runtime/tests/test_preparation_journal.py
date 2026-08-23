from __future__ import annotations

from dataclasses import replace
from unittest import TestCase, mock

from urusilla_hybrid_runtime import (
    PREPARATION_STAGE_INVENTORY,
    CostForecast,
    PreparationJournal,
    ReceiverCapabilities,
    RouterPolicy,
    RoutingError,
    RoutineInvocation,
    SilenceProof,
    canonical_json,
    prepare_message,
    source_text_sha256,
    strict_json_loads,
)
from urusilla_hybrid_runtime.tests import test_hybrid_runtime as fixtures


class PreparationJournalTests(TestCase):
    def setUp(self) -> None:
        case = fixtures.HybridExecutionContractTests(methodName="runTest")
        case.setUp()
        self.case = case

    @staticmethod
    def _stages(prepared) -> tuple[str, ...]:
        journal = prepared.preparation_journal
        assert journal is not None
        return tuple(item.stage for item in journal.observations)

    def _prepare_action(self, *, compiler, fidelity_verifier):
        source = "Verify artifact seven without external effects. " * 800
        return prepare_message(
            source,
            self.case.capsule,
            fixtures.action_receiver(self.case.capsule.sha256),
            fixtures.char_count,
            task_context=fixtures.TASK_CONTEXT,
            forecasts=fixtures.complete_forecasts(),
            evidence={"action-state": fixtures.passing_evidence()},
            compiler=compiler,
            fidelity_verifier=fidelity_verifier,
            policy=fixtures.action_policy(),
            utility_evidence_verifier=fixtures.verify_utility,
            capsule_comprehension_verifier=fixtures.verify_comprehension,
            task_context_comprehension_verifier=fixtures.verify_task_context,
        )

    def test_early_silence_routine_and_baseline_have_explicit_final_route(self):
        silence_source = "Already delivered and no reply is required."
        silence = prepare_message(
            silence_source,
            self.case.capsule,
            ReceiverCapabilities(),
            fixtures.char_count,
            task_context=fixtures.TASK_CONTEXT,
            forecasts=fixtures.complete_forecasts(),
            evidence={
                "silence": fixtures.passing_evidence(
                    "silence-journal", route_mode="silence"
                )
            },
            silence_proof=SilenceProof(
                source_text=silence_source,
                source_sha256=source_text_sha256(silence_source),
                task_context_text=fixtures.TASK_CONTEXT.canonical_text,
                task_context_sha256=fixtures.TASK_CONTEXT.sha256,
                verifier_sha256="sha256:" + "1" * 64,
                no_required_message=True,
                no_effectful_intent=True,
            ),
            utility_evidence_verifier=fixtures.verify_utility,
            silence_verifier=fixtures.verify_bound_artifact,
        )

        routine_source = "Repeat the verified status check. " * 500
        routine = prepare_message(
            routine_source,
            self.case.capsule,
            ReceiverCapabilities(
                session_routine_sha256=(fixtures.ROUTINE_DIGEST,)
            ),
            fixtures.char_count,
            task_context=fixtures.TASK_CONTEXT,
            forecasts=fixtures.complete_forecasts(),
            evidence={
                "routine": fixtures.passing_evidence(
                    "routine-journal", route_mode="routine"
                )
            },
            routine=RoutineInvocation(
                routine_id="status-check",
                routine_sha256=fixtures.ROUTINE_DIGEST,
                routine_definition_text=fixtures.ROUTINE_DEFINITION_TEXT,
                source_text=routine_source,
                source_sha256=source_text_sha256(routine_source),
                task_context_text=fixtures.TASK_CONTEXT.canonical_text,
                task_context_sha256=fixtures.TASK_CONTEXT.sha256,
                verifier_sha256="sha256:" + "5" * 64,
                payload={"artifact": 7},
                receiver_acknowledged=True,
                session_local=True,
                effect_free=True,
            ),
            policy=RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=fixtures.verify_utility,
            routine_verifier=fixtures.verify_bound_artifact,
        )

        baseline = prepare_message(
            "x" * 64_000,
            self.case.capsule,
            ReceiverCapabilities(supports_json=False),
            fixtures.char_count,
            task_context=fixtures.TASK_CONTEXT,
            forecasts=fixtures.complete_forecasts(),
        )

        for expected_mode, prepared in (
            ("silence", silence),
            ("routine", routine),
            ("raw", baseline),
        ):
            with self.subTest(mode=expected_mode):
                self.assertEqual(prepared.route.selected_mode, expected_mode)
                self.assertEqual(
                    self._stages(prepared),
                    (
                        "preflight-route",
                        "action-control",
                        "final-route",
                    ),
                )
                journal = prepared.preparation_journal
                assert journal is not None
                self.assertEqual(journal.inventory, PREPARATION_STAGE_INVENTORY)
                self.assertFalse(journal.claim_eligible)
                action = journal.observations[1].artifact["value"]
                self.assertEqual(action["decision"], "skip-action-state")
                final = journal.observations[-1]
                self.assertEqual(
                    final.artifact["value"]["route"]["selected_mode"],
                    expected_mode,
                )
                self.assertEqual(final.model_calls, 0)
                self.assertEqual(final.model_total_tokens, 0)
                self.assertNotIn(
                    "receiver", tuple(item.stage for item in journal.inventory)
                )
                self.assertNotIn(
                    "judge", tuple(item.stage for item in journal.inventory)
                )

    def test_action_chronology_records_actual_compiler_and_fidelity(self):
        prepared, compiler = self.case._action_prepared()
        journal = prepared.preparation_journal
        self.assertIsInstance(journal, PreparationJournal)
        assert journal is not None
        self.assertEqual(compiler.calls, 1)
        self.assertEqual(
            self._stages(prepared),
            (
                "preflight-route",
                "action-control",
                "sender-compiler",
                "compiler-control",
                "fidelity-verifier",
                "final-route",
            ),
        )
        self.assertEqual(
            tuple(item.model_calls for item in journal.observations),
            (0, 0, 1, 0, 1, 0),
        )
        self.assertEqual(
            journal.observations[1].artifact["value"]["decision"],
            "attempt-action-state",
        )
        self.assertEqual(
            journal.observations[3].artifact["value"]["decision"],
            "run-fidelity",
        )
        self.assertTrue(
            journal.observations[4].artifact["value"]["result"]["passed"]
        )
        self.assertEqual(
            journal.observations[-1].artifact["value"]["route"][
                "selected_mode"
            ],
            "action-state",
        )
        self.assertEqual(strict_json_loads(journal.canonical_text), journal.to_object())
        for observation in journal.observations:
            self.assertEqual(
                canonical_json(observation.artifact), observation.artifact_text
            )
            self.assertNotIn("_construction_seal", observation.artifact_text)
            self.assertNotIn("route_binding_sha256", observation.artifact_text)
            self.assertNotIn("request_binding_sha256", observation.artifact_text)
        with mock.patch.object(
            type(prepared.route),
            "binding_sha256",
            property(
                lambda _route: (_ for _ in ()).throw(
                    AssertionError("repr-derived route binding was read")
                )
            ),
        ):
            journal.assert_matches(
                route=prepared.route,
                compilation=prepared.compilation,
                fidelity_verification=prepared.fidelity_verification,
            )
        journal.assert_matches(
            route=prepared.route,
            compilation=prepared.compilation,
            fidelity_verification=prepared.fidelity_verification,
        )

    def test_failed_compiler_and_failed_fidelity_fallback_chronology(self):
        compiler_failed = fixtures.FakeCompiler(
            fixtures.ModelReply("not canonical sender output", "model-a", 7)
        )
        failed_compile = self._prepare_action(
            compiler=compiler_failed,
            fidelity_verifier=fixtures.verify_fidelity,
        )
        self.assertEqual(
            self._stages(failed_compile),
            (
                "preflight-route",
                "action-control",
                "sender-compiler",
                "compiler-control",
                "final-route",
            ),
        )
        compile_journal = failed_compile.preparation_journal
        assert compile_journal is not None
        self.assertEqual(
            compile_journal.observations[2].artifact["value"]["result"][
                "status"
            ],
            "failed",
        )
        self.assertEqual(
            compile_journal.observations[3].artifact["value"]["decision"],
            "skip-fidelity",
        )
        self.assertIn(failed_compile.route.selected_mode, {"raw", "json"})
        self.assertEqual(
            failed_compile.route.fallback_from,
            "action-state:failed",
        )

        compiler_ok = fixtures.FakeCompiler(
            fixtures.ModelReply(
                fixtures.sender_output(self.case.state),
                "model-a",
                10,
            )
        )
        failed_fidelity = self._prepare_action(
            compiler=compiler_ok,
            fidelity_verifier=lambda item: fixtures.fidelity_verification(
                item, passed=False
            ),
        )
        self.assertEqual(
            self._stages(failed_fidelity),
            (
                "preflight-route",
                "action-control",
                "sender-compiler",
                "compiler-control",
                "fidelity-verifier",
                "final-route",
            ),
        )
        fidelity_journal = failed_fidelity.preparation_journal
        assert fidelity_journal is not None
        self.assertFalse(
            fidelity_journal.observations[4].artifact["value"]["result"][
                "passed"
            ]
        )
        self.assertIn(failed_fidelity.route.selected_mode, {"raw", "json"})
        self.assertEqual(failed_fidelity.route.fallback_from, "action-state:ok")

    def test_mutation_of_journal_or_prepared_route_fails_closed(self):
        prepared, _compiler = self.case._action_prepared()
        journal = prepared.preparation_journal
        assert journal is not None
        original_binding = prepared.execution_binding_sha256

        object.__setattr__(
            prepared.route.request,
            "payload_text",
            prepared.route.request.payload_text + " tampered",
        )
        with self.assertRaisesRegex(RoutingError, "differs from its preparation"):
            journal.assert_matches(
                route=prepared.route,
                compilation=prepared.compilation,
                fidelity_verification=prepared.fidelity_verification,
            )
        mutated_binding = prepared.execution_binding_sha256
        self.assertNotEqual(mutated_binding, original_binding)

        other, _compiler = self.case._action_prepared()
        other_journal = other.preparation_journal
        assert other_journal is not None
        observation = other_journal.observations[0]
        object.__setattr__(
            observation,
            "artifact_text",
            observation.artifact_text + " ",
        )
        with self.assertRaisesRegex(
            RoutingError, "artifact (is invalid|is not canonical)"
        ):
            _ = other_journal.sha256

        reordered, _compiler = self.case._action_prepared()
        reordered_journal = reordered.preparation_journal
        assert reordered_journal is not None
        object.__setattr__(
            reordered_journal,
            "observations",
            tuple(reversed(reordered_journal.observations)),
        )
        with self.assertRaisesRegex(
            RoutingError, "sequence is not contiguous|chronology is invalid"
        ):
            _ = reordered_journal.sha256

    def test_cross_wired_journal_is_rejected_during_prepared_construction(self):
        prepared, _compiler = self.case._action_prepared()
        baseline = prepare_message(
            "unrelated raw source",
            self.case.capsule,
            ReceiverCapabilities(supports_json=False),
            fixtures.char_count,
            task_context=fixtures.TASK_CONTEXT,
            forecasts=fixtures.complete_forecasts(),
        )
        assert baseline.preparation_journal is not None
        with self.assertRaisesRegex(
            RoutingError,
            "differs from its preparation|presence differs from journal",
        ):
            replace(
                prepared,
                preparation_journal=baseline.preparation_journal,
            )

        assert prepared.compilation is not None
        with self.assertRaisesRegex(
            RoutingError,
            "prepared compilation differs from journal",
        ):
            replace(
                prepared,
                compilation=replace(
                    prepared.compilation,
                    model_id="cross-wired-model",
                ),
            )
