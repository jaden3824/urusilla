from __future__ import annotations

import copy
from dataclasses import replace
from unittest import TestCase

from urusilla_hybrid_runtime import (
    EvolutionAttempt,
    EvolutionCostLedger,
    EvolutionOutcome,
    EvolutionTrialManifest,
    OnlineEvolutionController,
    PublicActionState,
    PublicTaskContext,
    SurfaceActivationEvidence,
    SurfaceArtifactVerification,
    SurfaceError,
    SurfaceTrial,
    SurfaceTrialPlan,
    TaskContextError,
    semantic_ref_frequencies,
    source_text_sha256,
)
from urusilla_hybrid_runtime.evolution import (
    MAX_EVOLUTION_ATTEMPTS,
    MAX_EVOLUTION_CANDIDATE_ALIASES,
    MAX_EVOLUTION_OBSERVATIONS,
    MAX_EVOLUTION_TRIAL_CASES,
)
from urusilla_hybrid_runtime.tests.test_surface import (
    ACTIVATION_VERIFIER_SHA256,
    ROUND_TRIP_VECTORS_SHA256,
    TASK_CONTEXT,
    TRIAL_RESULT_SHA256,
    TRIAL_TRANSCRIPT_SHA256,
    TRIAL_VERIFIER_SHA256,
    digest_series,
    positive_state,
    refusal_state,
    surface_scope,
)


def trial_manifest(
    *,
    scope,
    attempt_id: int,
    parent_sha256: str | None,
    tag: str,
    case_count: int = 2,
) -> EvolutionTrialManifest:
    return EvolutionTrialManifest(
        session_id=scope.session_id,
        model_context_id=scope.model_context_id,
        expected_attempt_id=attempt_id,
        parent_table_sha256=parent_sha256,
        cases=tuple(
            (
                f"heldout-{tag}-{index}",
                source_text_sha256(f"heldout source {tag} {index}"),
            )
            for index in range(case_count)
        ),
        external_plan_sha256=source_text_sha256(f"external plan {tag}"),
    )


def trial_plan(
    manifest: EvolutionTrialManifest,
    *,
    call_ceiling: int = 100,
    aggregate_ceiling: int = 1_000,
) -> SurfaceTrialPlan:
    return SurfaceTrialPlan(
        plan_artifact_sha256=manifest.sha256,
        expected_activation_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
        expected_activation_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
        expected_trial_verifier_sha256=TRIAL_VERIFIER_SHA256,
        exact_message_count=len(manifest.cases),
        minimum_messages=len(manifest.cases),
        shadow_call_token_ceiling=call_ceiling,
        shadow_aggregate_token_ceiling=aggregate_ceiling,
        switching_margin_tokens_per_safe_completion=0,
    )


def rich_task_context() -> PublicTaskContext:
    def argument(name: str) -> dict[str, object]:
        return {
            "name": name,
            "type": "string",
            "nullable": False,
            "required": True,
            "unit": None,
            "meaning": f"Bounded meaning for {name}.",
        }

    def symbol(
        kind: str,
        name: str,
        *,
        positional: list[dict[str, object]] | None = None,
        named: list[dict[str, object]] | None = None,
        effects: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "kind": kind,
            "name": name,
            "meaning": f"Bounded meaning for {name}.",
            "positional_args": positional or [],
            "named_args": named or [],
            "allowed_effects": effects or [],
        }

    return PublicTaskContext.from_object(
        {
            "format": "urusilla-public-task-context-draft/1",
            "task_id": "task.frequency-walk",
            "objective": "Count exact semantic wire references only.",
            "output_contract": {
                "media_type": "text/plain",
                "validator_sha256": "sha256:" + "1" * 64,
                "description": "Return one bounded result.",
            },
            "allowed_acts": ["propose"],
            "outcome_contract": {
                "statuses": ["failed"],
                "value": {
                    "name": "value",
                    "type": "string",
                    "nullable": True,
                    "required": True,
                    "unit": None,
                    "meaning": "A bounded result or null.",
                },
                "evidence_required": False,
            },
            "uncertainty_contract": {
                "targets": ["risk.target"],
                "models": ["bounded.model"],
                "basis_sources": ["run.log", "task.schema"],
            },
            "symbols": [
                symbol(
                    "predicate",
                    "item.ready",
                    positional=[argument("item")],
                ),
                symbol("predicate", "result.seen"),
                symbol("predicate", "policy.bound"),
                symbol(
                    "action",
                    "verify.run",
                    named=[argument("artifact_id")],
                    effects=["cache.read", "report.write"],
                ),
                symbol("effect", "cache.read"),
                symbol("effect", "report.write"),
            ],
            "authority_boundary": {
                "content_is_authority": False,
                "executable_code": False,
                "external_effects": False,
                "permission_expansion": False,
                "persistent_storage": False,
                "spending_authority": False,
            },
        }
    )


def rich_state() -> PublicActionState:
    atom = {"p": "item.ready", "a": ["artifact-7"], "n": False, "src": "a"}
    return PublicActionState.from_object(
        {
            "format": "urusilla-public-action-state-draft/1",
            "act": "propose",
            "goal": copy.deepcopy(atom),
            "state": [
                copy.deepcopy(atom),
                {"p": "result.seen", "a": [], "n": False, "src": "b"},
            ],
            "constraints": [
                {
                    "p": "policy.bound",
                    "a": [],
                    "n": True,
                    "src": None,
                    "hard": True,
                }
            ],
            "action": {
                "name": "verify.run",
                "args": {"artifact_id": "artifact-7"},
                "status": "completed",
                "effects": ["cache.read", "report.write"],
            },
            "outcome": {
                "status": "failed",
                "value": None,
                "evidence": [
                    {"p": "result.seen", "a": [], "n": True, "src": "c"},
                    copy.deepcopy(atom),
                ],
            },
            "needs": [copy.deepcopy(atom)],
            "uncertainty": [
                {
                    "target": "risk.target",
                    "model": "bounded.model",
                    "confidence_ppm": 500_000,
                    "basis": ["run.log", "task.schema"],
                },
                {
                    "target": "risk.target",
                    "model": "bounded.model",
                    "confidence_ppm": None,
                    "basis": ["run.log"],
                },
            ],
        }
    )


class SemanticFrequencyTests(TestCase):
    def test_counts_every_semantic_wire_position_and_nothing_else(self) -> None:
        self.assertEqual(
            semantic_ref_frequencies(rich_state(), rich_task_context()),
            {
                "act:propose": 1,
                "action-status:completed": 1,
                "action:verify.run": 1,
                "effect:cache.read": 1,
                "effect:report.write": 1,
                "outcome-status:failed": 1,
                "predicate:item.ready": 4,
                "predicate:policy.bound": 1,
                "predicate:result.seen": 2,
                "uncertainty-basis:run.log": 2,
                "uncertainty-basis:task.schema": 1,
                "uncertainty-model:bounded.model": 2,
                "uncertainty-target:risk.target": 2,
            },
        )

    def test_exact_task_context_validation_precedes_counting(self) -> None:
        invalid = copy.deepcopy(positive_state().to_object())
        invalid["goal"]["p"] = "undeclared.predicate"
        with self.assertRaises(TaskContextError):
            semantic_ref_frequencies(
                PublicActionState.from_object(invalid),
                TASK_CONTEXT,
            )


class OnlineEvolutionControllerTests(TestCase):
    def setUp(self) -> None:
        self.scope = surface_scope()
        self.manifest = trial_manifest(
            scope=self.scope,
            attempt_id=1,
            parent_sha256=None,
            tag="attempt-1",
        )
        self.plan = trial_plan(self.manifest)
        self.events: list[object] = []
        self.activation_mode = "valid"
        self.trial_mode = "keep"
        self.trial_overrides: dict[str, object] = {}
        self.replay_evidence: SurfaceActivationEvidence | None = None
        self.replay_trial: SurfaceTrial | None = None
        self.last_evidence: SurfaceActivationEvidence | None = None
        self.last_trial: SurfaceTrial | None = None
        self.controller: OnlineEvolutionController | None = None
        self.window_serial = 0
        self.freeze_serial = 1
        self.live_during_callbacks: list[object] = []

    def activation_callback(self, table, attempt, manifest):
        self.events.append(("activation", table, attempt, manifest))
        if self.controller is not None:
            self.live_during_callbacks.append(self.controller.live_authorization)
        if self.activation_mode == "raise":
            raise RuntimeError("DO-NOT-LEAK-ACTIVATION-SECRET")
        if self.activation_mode == "wrong-type":
            return {"passed": True}
        if self.activation_mode == "replay":
            assert self.replay_evidence is not None
            return self.replay_evidence
        evidence = SurfaceActivationEvidence(
            table_sha256=table.sha256,
            attempt_sha256=(
                "sha256:" + "f" * 64
                if self.activation_mode == "forged-zero-mismatch"
                else attempt.sha256
            ),
            session_id=table.scope.session_id,
            model_context_id=table.scope.model_context_id,
            round_trip_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
            verifier_sha256=ACTIVATION_VERIFIER_SHA256,
            sender_acknowledged=True,
            receiver_acknowledged=True,
            exact_round_trip_passed=True,
            comprehension_passed=True,
            setup_total_tokens=(
                0 if self.activation_mode == "forged-zero-mismatch" else 7
            ),
            usage_complete=True,
        )
        self.last_evidence = evidence
        return evidence

    def activation_verifier(self, evidence, _table):
        self.events.append("activation-verifier")
        return SurfaceArtifactVerification(
            passed=True,
            input_binding_sha256=evidence.binding_sha256,
            verifier_sha256=evidence.verifier_sha256,
        )

    def trial_callback(self, table, active, plan, attempt, manifest):
        self.events.append(("trial", table, attempt, manifest))
        if self.controller is not None:
            self.live_during_callbacks.append(self.controller.live_authorization)
        if self.trial_mode == "raise":
            raise RuntimeError("DO-NOT-LEAK-TRIAL-SECRET")
        if self.trial_mode == "wrong-type":
            return ("shadow-output",)
        if self.trial_mode == "replay":
            assert self.replay_trial is not None
            return self.replay_trial
        count = plan.exact_message_count
        baseline_total_raw = self.trial_overrides.get("baseline_total_tokens", 200)
        baseline_total = (
            None if baseline_total_raw is None else int(baseline_total_raw)
        )
        runtime_tokens = int(
            self.trial_overrides.get(
                "surface_runtime_tokens_excluding_setup",
                90,
            )
        )
        per_call = [runtime_tokens // count] * count
        per_call[-1] += runtime_tokens - sum(per_call)
        values: dict[str, object] = {
            "table_sha256": table.sha256,
            "attempt_sha256": attempt.sha256,
            "activation_binding_sha256": active.activation_binding_sha256,
            "plan_sha256": plan.sha256,
            "result_sha256": TRIAL_RESULT_SHA256,
            "transcript_sha256": TRIAL_TRANSCRIPT_SHA256,
            "verifier_sha256": TRIAL_VERIFIER_SHA256,
            "executed_cases": manifest.cases,
            "baseline_execution_binding_sha256s": digest_series(
                900 + attempt.attempt_id * 10,
                count,
            ),
            "baseline_request_binding_sha256s": digest_series(
                1_100 + attempt.attempt_id * 10,
                count,
            ),
            "baseline_configured_token_ceilings": (
                plan.shadow_call_token_ceiling,
            )
            * count,
            "baseline_observed_total_tokens": (
                (None,) * count
                if baseline_total is None
                else tuple(
                    [baseline_total // count] * (count - 1)
                    + [
                        baseline_total
                        - (baseline_total // count) * (count - 1)
                    ]
                )
            ),
            "shadow_execution_binding_sha256s": digest_series(
                500 + attempt.attempt_id * 10,
                count,
            ),
            "shadow_request_binding_sha256s": digest_series(
                700 + attempt.attempt_id * 10,
                count,
            ),
            "shadow_configured_token_ceilings": (
                plan.shadow_call_token_ceiling,
            )
            * count,
            "shadow_observed_total_tokens": tuple(per_call),
            "prior_evolution_overhead_tokens": (
                attempt.prior_unamortized_overhead_tokens
            ),
            "message_count": count,
            "baseline_total_tokens": baseline_total,
            "activation_setup_tokens": active.setup_total_tokens,
            "surface_runtime_tokens_excluding_setup": runtime_tokens,
            "surface_total_tokens_including_setup": (
                active.setup_total_tokens + runtime_tokens
            ),
            "baseline_safe_completions": count,
            "surface_safe_completions": count,
            "parse_valid": count,
            "fidelity_valid": count,
            "negation_preserved": True,
            "null_preserved": True,
            "failure_preserved": self.trial_mode != "rollback",
            "refusal_preserved": True,
            "usage_complete": True,
            "frozen_before_execution": True,
            "measurement_scope_complete": True,
        }
        values.update(self.trial_overrides)
        trial = SurfaceTrial(**values)
        self.last_trial = trial
        return trial

    def trial_verifier(
        self,
        trial,
        _plan,
        _table,
        _active,
        attempt,
        manifest,
    ):
        self.events.append("trial-verifier")
        if self.trial_mode == "verifier-raises":
            raise RuntimeError("DO-NOT-LEAK-VERIFIER-SECRET")
        return SurfaceArtifactVerification(
            passed=(
                trial.attempt_sha256 == attempt.sha256
                and trial.executed_cases == manifest.cases
            ),
            input_binding_sha256=trial.binding_sha256,
            verifier_sha256=trial.verifier_sha256,
        )

    def make_controller(self, **overrides: object) -> OnlineEvolutionController:
        values: dict[str, object] = {
            "scope": self.scope,
            "task_context": TASK_CONTEXT,
            "candidate_aliases": tuple(chr(0x4E00 + index) for index in range(24)),
            "token_counters": {"tok-a": len, "tok-b": len},
            "observation_message_count": 3,
            "trial_plan": self.plan,
            "trial_manifest": self.manifest,
            "activation_callback": self.activation_callback,
            "activation_verifier": self.activation_verifier,
            "trial_callback": self.trial_callback,
            "trial_verifier": self.trial_verifier,
        }
        values.update(overrides)
        controller = OnlineEvolutionController(**values)
        self.controller = controller
        return controller

    def fill(
        self,
        controller: OnlineEvolutionController,
        *,
        state: PublicActionState | None = None,
        duplicate_source: bool = False,
    ) -> None:
        self.window_serial += 1
        for index in range(controller.required_count):
            source_index = 0 if duplicate_source else index
            controller.observe(
                f"observation-{self.window_serial}-{index}",
                f"observed source {self.window_serial} {source_index}",
                state or positive_state(),
            )

    def next_freeze(
        self,
        controller: OnlineEvolutionController,
        *,
        call_ceiling: int = 100,
        aggregate_ceiling: int = 1_000,
    ) -> tuple[SurfaceTrialPlan, EvolutionTrialManifest]:
        self.freeze_serial += 1
        parent_sha256 = (
            None
            if controller.retained_table is None
            else controller.retained_table.sha256
        )
        manifest = trial_manifest(
            scope=self.scope,
            attempt_id=controller.cost_ledger.attempt_count + 1,
            parent_sha256=parent_sha256,
            tag=f"attempt-{self.freeze_serial}",
        )
        plan = trial_plan(
            manifest,
            call_ceiling=call_ceiling,
            aggregate_ceiling=aggregate_ceiling,
        )
        return plan, manifest

    def begin_next(
        self,
        controller: OnlineEvolutionController,
        **kwargs: int,
    ) -> int:
        plan, manifest = self.next_freeze(controller, **kwargs)
        self.plan = plan
        self.manifest = manifest
        return controller.begin_next_generation(
            trial_plan=plan,
            trial_manifest=manifest,
        )

    def test_threshold_callback_order_attempt_binding_and_keep(self) -> None:
        controller = self.make_controller()
        controller.observe(
            "observation-partial-0",
            "partial source 0",
            positive_state(),
        )
        controller.observe(
            "observation-partial-1",
            "partial source 1",
            positive_state(),
        )
        pending = controller.evolve_if_ready()
        self.assertEqual(pending.status, "not-ready")
        self.assertEqual(self.events, [])
        controller.observe(
            "observation-partial-2",
            "partial source 2",
            positive_state(),
        )
        window_sha256 = controller.observation_window_sha256
        outcome = controller.evolve_if_ready()
        self.assertEqual(outcome.status, "keep")
        self.assertEqual(
            [event if type(event) is str else event[0] for event in self.events],
            ["activation", "activation-verifier", "trial", "trial-verifier"],
        )
        activation_attempt = self.events[0][2]
        activation_manifest = self.events[0][3]
        trial_attempt = self.events[2][2]
        self.assertIs(activation_attempt, trial_attempt)
        self.assertIs(activation_manifest, self.manifest)
        self.assertEqual(activation_attempt.attempt_id, 1)
        self.assertEqual(activation_attempt.observation_count, 3)
        self.assertEqual(activation_attempt.observation_window_sha256, window_sha256)
        self.assertEqual(activation_attempt.manifest_sha256, self.manifest.sha256)
        self.assertIsNone(activation_attempt.retained_parent_sha256)
        self.assertEqual(self.live_during_callbacks, [None, None])
        live = controller.live_authorization
        self.assertIsNotNone(live)
        assert live is not None
        self.assertTrue(live[2].authorizes(live[0], live[1]))
        self.assertEqual(live[2].attempt_sha256, activation_attempt.sha256)
        self.assertEqual(outcome.attempt_sha256, activation_attempt.sha256)
        self.assertEqual(outcome.cost_ledger.lifetime_overhead_tokens, 97)
        self.assertEqual(outcome.cost_ledger.unamortized_overhead_tokens, 97)
        self.assertEqual(outcome.cost_ledger_sha256, outcome.cost_ledger.sha256)
        self.assertIsNotNone(controller.live_authorization)
        self.assertFalse(hasattr(controller, "record_live_savings"))
        self.assertFalse(hasattr(outcome, "trial"))
        self.assertFalse(hasattr(outcome, "transcript"))
        event_count = len(self.events)
        self.assertIs(controller.evolve_if_ready(), outcome)
        self.assertEqual(len(self.events), event_count)

    def test_observation_and_heldout_sets_are_exactly_disjoint(self) -> None:
        controller = self.make_controller()
        heldout_id, _heldout_source = self.manifest.cases[0]
        with self.assertRaises(SurfaceError):
            controller.observe(heldout_id, "other", positive_state())
        with self.assertRaises(SurfaceError):
            controller.observe(
                "other-observation",
                "heldout source attempt-1 0",
                positive_state(),
            )
        shared_source = "repeated normal source"
        controller.observe("normal-1", shared_source, positive_state())
        controller.observe("normal-2", shared_source, positive_state())
        with self.assertRaises(SurfaceError):
            controller.observe("normal-2", "new", positive_state())
        self.assertEqual(controller.observed_count, 2)

    def test_manifest_and_plan_are_frozen_before_observation(self) -> None:
        wrong_plan = replace(
            self.plan,
            plan_artifact_sha256="sha256:" + "f" * 64,
        )
        with self.assertRaises(SurfaceError):
            self.make_controller(trial_plan=wrong_plan)
        short_manifest = trial_manifest(
            scope=self.scope,
            attempt_id=1,
            parent_sha256=None,
            tag="short",
            case_count=1,
        )
        with self.assertRaises(SurfaceError):
            self.make_controller(trial_manifest=short_manifest)

        controller = self.make_controller()
        self.fill(controller)
        self.assertEqual(controller.evolve_if_ready().status, "keep")
        with self.assertRaises(SurfaceError):
            controller.begin_next_generation(
                trial_plan=self.plan,
                trial_manifest=self.manifest,
            )
        wrong_parent = trial_manifest(
            scope=self.scope,
            attempt_id=2,
            parent_sha256=None,
            tag="wrong-parent",
        )
        with self.assertRaises(SurfaceError):
            controller.begin_next_generation(
                trial_plan=trial_plan(wrong_parent),
                trial_manifest=wrong_parent,
            )
        correct_parent = controller.retained_table
        assert correct_parent is not None
        drift_manifest = trial_manifest(
            scope=self.scope,
            attempt_id=2,
            parent_sha256=correct_parent.sha256,
            tag="policy-drift",
        )
        drift_plan = trial_plan(drift_manifest)
        drift_plan = replace(drift_plan, shadow_call_token_ceiling=101)
        with self.assertRaises(SurfaceError):
            controller.begin_next_generation(
                trial_plan=drift_plan,
                trial_manifest=drift_manifest,
            )
        self.assertEqual(controller.phase, "retained")

    def test_same_table_can_be_retried_with_fresh_attempt_after_rollback(self) -> None:
        self.trial_mode = "rollback"
        controller = self.make_controller()
        self.fill(controller)
        first = controller.evolve_if_ready()
        self.assertEqual(first.status, "rollback")
        first_table_sha256 = first.candidate_table_sha256
        first_attempt_sha256 = first.attempt_sha256
        self.begin_next(controller)
        self.trial_mode = "keep"
        self.fill(controller)
        second = controller.evolve_if_ready()
        self.assertEqual(second.status, "keep")
        self.assertEqual(second.candidate_table_sha256, first_table_sha256)
        self.assertNotEqual(second.attempt_sha256, first_attempt_sha256)
        self.assertEqual([item.attempt_id for item in controller.attempt_history], [1, 2])
        self.assertEqual(controller.cost_ledger.lifetime_overhead_tokens, 194)
        self.assertEqual(controller.cost_ledger.unamortized_overhead_tokens, 194)

    def test_old_activation_and_trial_artifacts_cannot_cross_attempts(self) -> None:
        self.trial_mode = "rollback"
        controller = self.make_controller()
        self.fill(controller)
        self.assertEqual(controller.evolve_if_ready().status, "rollback")
        self.replay_evidence = self.last_evidence
        self.replay_trial = self.last_trial

        self.begin_next(controller)
        self.activation_mode = "replay"
        self.trial_mode = "keep"
        self.fill(controller)
        old_activation = controller.evolve_if_ready()
        self.assertEqual(old_activation.status, "failed")
        self.assertEqual(old_activation.failure_stage, "activation")
        self.assertEqual(old_activation.failure_code, "binding-mismatch")

        self.manifest = trial_manifest(
            scope=self.scope,
            attempt_id=1,
            parent_sha256=None,
            tag="replay-trial-attempt-1",
        )
        self.plan = trial_plan(self.manifest)
        other = self.make_controller()
        self.trial_mode = "rollback"
        self.activation_mode = "valid"
        self.fill(other)
        self.assertEqual(other.evolve_if_ready().status, "rollback")
        replay_trial = self.last_trial
        self.begin_next(other)
        self.trial_mode = "replay"
        self.replay_trial = replay_trial
        self.fill(other)
        old_trial = other.evolve_if_ready()
        self.assertEqual(old_trial.status, "failed")
        self.assertEqual(old_trial.failure_stage, "trial")
        self.assertEqual(old_trial.failure_code, "binding-mismatch")

    def test_same_scope_controller_epoch_rejects_cross_instance_replay(self) -> None:
        observations = tuple(
            (
                f"shared-observation-{index}",
                f"shared observed source {index}",
            )
            for index in range(3)
        )
        first_controller = self.make_controller()
        for observation_id, source_text in observations:
            first_controller.observe(
                observation_id,
                source_text,
                positive_state(),
            )
        first_window_sha256 = first_controller.observation_window_sha256
        first_outcome = first_controller.evolve_if_ready()
        self.assertEqual(first_outcome.status, "keep")
        replay_evidence = self.last_evidence
        replay_trial = self.last_trial
        self.assertIsNotNone(replay_evidence)
        self.assertIsNotNone(replay_trial)

        second_controller = self.make_controller()
        self.assertNotEqual(
            first_controller.controller_epoch_sha256,
            second_controller.controller_epoch_sha256,
        )
        for observation_id, source_text in observations:
            second_controller.observe(
                observation_id,
                source_text,
                positive_state(),
            )
        self.assertNotEqual(
            first_window_sha256,
            second_controller.observation_window_sha256,
        )
        self.activation_mode = "replay"
        self.replay_evidence = replay_evidence
        second_outcome = second_controller.evolve_if_ready()
        self.assertEqual(second_outcome.status, "failed")
        self.assertEqual(second_outcome.failure_stage, "activation")
        self.assertEqual(second_outcome.failure_code, "binding-mismatch")
        self.assertNotEqual(
            first_outcome.attempt_sha256,
            second_outcome.attempt_sha256,
        )
        self.assertEqual(
            second_outcome.controller_epoch_sha256,
            second_controller.controller_epoch_sha256,
        )
        self.assertIsNone(second_controller.live_authorization)

        third_controller = self.make_controller()
        for observation_id, source_text in observations:
            third_controller.observe(
                observation_id,
                source_text,
                positive_state(),
            )
        self.activation_mode = "valid"
        self.trial_mode = "replay"
        self.replay_trial = replay_trial
        third_outcome = third_controller.evolve_if_ready()
        self.assertEqual(third_outcome.status, "failed")
        self.assertEqual(third_outcome.failure_stage, "trial")
        self.assertEqual(third_outcome.failure_code, "binding-mismatch")
        self.assertNotEqual(
            first_outcome.attempt_sha256,
            third_outcome.attempt_sha256,
        )
        self.assertIsNone(third_controller.live_authorization)

    def test_child_requires_new_semantics_for_parent_relative_improvement(self) -> None:
        controller = self.make_controller()
        self.fill(controller)
        self.assertEqual(controller.evolve_if_ready().status, "keep")
        first_table = controller.retained_table
        assert first_table is not None

        self.begin_next(controller)
        event_count = len(self.events)
        self.fill(controller)
        no_op = controller.evolve_if_ready()
        self.assertEqual(no_op.status, "failed")
        self.assertEqual(no_op.failure_stage, "proposal")
        self.assertEqual(len(self.events), event_count)
        self.assertEqual(controller.retained_table, first_table)

        self.begin_next(controller)
        self.fill(controller, state=refusal_state())
        child = controller.evolve_if_ready()
        self.assertEqual(child.status, "keep")
        child_table = controller.retained_table
        assert child_table is not None
        self.assertEqual(child_table.generation, 2)
        self.assertEqual(child_table.parent_sha256, first_table.sha256)

    def test_known_failed_cost_is_unamortized_and_can_block_next_keep(self) -> None:
        self.plan = trial_plan(
            self.manifest,
            call_ceiling=1_000,
            aggregate_ceiling=5_000,
        )
        self.trial_mode = "rollback"
        self.trial_overrides = {
            "baseline_total_tokens": 900,
            "surface_runtime_tokens_excluding_setup": 993,
            "surface_total_tokens_including_setup": 1_000,
            "shadow_observed_total_tokens": (496, 497),
        }
        controller = self.make_controller()
        self.fill(controller)
        first = controller.evolve_if_ready()
        self.assertEqual(first.status, "rollback")
        self.assertEqual(first.cost_ledger.lifetime_overhead_tokens, 1_000)
        self.assertEqual(first.cost_ledger.unamortized_overhead_tokens, 1_000)

        self.begin_next(
            controller,
            call_ceiling=1_000,
            aggregate_ceiling=5_000,
        )
        self.trial_mode = "keep"
        self.trial_overrides = {
            "baseline_total_tokens": 100,
            "surface_runtime_tokens_excluding_setup": 92,
            "surface_total_tokens_including_setup": 99,
            "shadow_observed_total_tokens": (46, 46),
        }
        self.fill(controller)
        blocked = controller.evolve_if_ready()
        self.assertEqual(blocked.status, "rollback")
        self.assertIn("no-strict-total-token-advantage", blocked.decision.reasons)
        self.assertEqual(blocked.cost_ledger.lifetime_overhead_tokens, 1_099)
        self.assertEqual(blocked.cost_ledger.unamortized_overhead_tokens, 1_099)

    def test_unknown_callback_cost_permanently_blocks_future_keep(self) -> None:
        self.activation_mode = "raise"
        controller = self.make_controller()
        self.fill(controller)
        failed = controller.evolve_if_ready()
        self.assertEqual(failed.status, "failed")
        self.assertFalse(failed.cost_ledger.usage_complete)
        self.assertIsNone(failed.cost_ledger.lifetime_overhead_tokens)
        self.assertNotIn("DO-NOT-LEAK", repr(failed))

        self.begin_next(controller)
        self.activation_mode = "valid"
        self.trial_mode = "keep"
        self.fill(controller)
        blocked = controller.evolve_if_ready()
        self.assertEqual(blocked.status, "rollback")
        self.assertIn(
            "prior-evolution-overhead-unknown",
            blocked.decision.reasons,
        )
        self.assertFalse(blocked.cost_ledger.usage_complete)
        self.assertFalse(hasattr(blocked.cost_ledger, "output"))
        self.assertFalse(hasattr(blocked, "exception"))

    def test_forged_zero_cost_binding_mismatch_cannot_enable_future_keep(self) -> None:
        self.activation_mode = "forged-zero-mismatch"
        controller = self.make_controller()
        self.fill(controller)
        failed = controller.evolve_if_ready()
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.failure_code, "binding-mismatch")
        self.assertFalse(failed.cost_ledger.usage_complete)
        self.assertIsNone(failed.cost_ledger.unamortized_overhead_tokens)

        self.begin_next(controller)
        self.activation_mode = "valid"
        self.fill(controller)
        blocked = controller.evolve_if_ready()
        self.assertEqual(blocked.status, "rollback")
        self.assertIn(
            "prior-evolution-overhead-unknown",
            blocked.decision.reasons,
        )

    def test_trial_verifier_failure_makes_usage_unknown(self) -> None:
        self.trial_mode = "verifier-raises"
        controller = self.make_controller()
        self.fill(controller)
        outcome = controller.evolve_if_ready()
        self.assertEqual(outcome.status, "rollback")
        self.assertIn(
            "trial-artifact-verification-failed",
            outcome.decision.reasons,
        )
        self.assertFalse(outcome.cost_ledger.usage_complete)
        self.assertIsNone(outcome.cost_ledger.lifetime_overhead_tokens)
        self.assertIsNone(outcome.cost_ledger.unamortized_overhead_tokens)

    def test_trial_execution_receipts_must_follow_exact_manifest_order(self) -> None:
        self.trial_overrides = {
            "executed_cases": tuple(reversed(self.manifest.cases)),
        }
        controller = self.make_controller()
        self.fill(controller)
        outcome = controller.evolve_if_ready()
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.failure_stage, "trial")
        self.assertEqual(outcome.failure_code, "binding-mismatch")
        self.assertFalse(outcome.cost_ledger.usage_complete)
        self.assertIsNone(outcome.cost_ledger.lifetime_overhead_tokens)
        self.assertIsNone(outcome.cost_ledger.unamortized_overhead_tokens)

    def test_wrong_context_and_reentrant_operations_fail_closed(self) -> None:
        controller = self.make_controller()
        wrong = copy.deepcopy(positive_state().to_object())
        wrong["goal"]["p"] = "other.goal"
        with self.assertRaises(TaskContextError):
            controller.observe(
                "wrong-context",
                "wrong context",
                PublicActionState.from_object(wrong),
            )
        self.assertEqual(controller.observed_count, 0)

        reentrant_errors: list[str] = []
        original = self.activation_callback

        def activation(table, attempt, manifest):
            for name, operation in (
                (
                    "observe",
                    lambda: controller.observe(
                        "reentrant",
                        "reentrant",
                        positive_state(),
                    ),
                ),
                ("evolve", controller.evolve_if_ready),
                (
                    "reset",
                    lambda: controller.begin_next_generation(
                        trial_plan=self.plan,
                        trial_manifest=self.manifest,
                    ),
                ),
            ):
                try:
                    operation()
                except SurfaceError:
                    reentrant_errors.append(name)
            return original(table, attempt, manifest)

        controller._activation_callback = activation
        self.fill(controller)
        self.assertEqual(controller.evolve_if_ready().status, "keep")
        self.assertEqual(reentrant_errors, ["observe", "evolve", "reset"])

    def test_fixed_resource_bounds_reject_unbounded_inputs(self) -> None:
        with self.assertRaises(SurfaceError):
            self.make_controller(
                observation_message_count=MAX_EVOLUTION_OBSERVATIONS + 1
            )
        with self.assertRaises(SurfaceError):
            self.make_controller(
                candidate_aliases=tuple(
                    chr(0x4E00 + index)
                    for index in range(MAX_EVOLUTION_CANDIDATE_ALIASES + 1)
                )
            )
        with self.assertRaises(SurfaceError):
            trial_manifest(
                scope=self.scope,
                attempt_id=1,
                parent_sha256=None,
                tag="too-many",
                case_count=MAX_EVOLUTION_TRIAL_CASES + 1,
            )
        with self.assertRaises(SurfaceError):
            EvolutionTrialManifest(
                session_id=self.scope.session_id,
                model_context_id=self.scope.model_context_id,
                expected_attempt_id=MAX_EVOLUTION_ATTEMPTS + 1,
                parent_table_sha256=None,
                cases=(("case", source_text_sha256("case")),),
                external_plan_sha256=source_text_sha256("plan"),
            )

    def test_typed_artifacts_and_outcomes_reject_forged_bindings(self) -> None:
        ledger = EvolutionCostLedger(0, 0, 0, True)
        with self.assertRaises(SurfaceError):
            EvolutionAttempt(
                attempt_id=2,
                session_id=self.scope.session_id,
                model_context_id=self.scope.model_context_id,
                controller_epoch_sha256="sha256:" + "2" * 64,
                retained_parent_sha256=None,
                observation_window_sha256="sha256:" + "1" * 64,
                observation_count=3,
                manifest_sha256=self.manifest.sha256,
                prior_ledger_sha256=ledger.sha256,
                prior_attempt_count=0,
                prior_lifetime_overhead_tokens=0,
                prior_unamortized_overhead_tokens=0,
                prior_usage_complete=True,
            )
        with self.assertRaises(SurfaceError):
            EvolutionOutcome(
                status="failed",
                phase="failed",
                controller_epoch_sha256="sha256:" + "2" * 64,
                observed_count=3,
                required_count=3,
                cost_ledger=ledger,
                cost_ledger_sha256="sha256:" + "z" * 64,
                failure_stage="proposal",
                failure_code="operation-rejected",
            )
        with self.assertRaises(SurfaceError):
            EvolutionOutcome(
                status="failed",
                phase="failed",
                controller_epoch_sha256="sha256:" + "2" * 64,
                observed_count=3,
                required_count=3,
                cost_ledger=ledger,
                cost_ledger_sha256=ledger.sha256,
                failure_stage="secret callback traceback",
                failure_code="arbitrary exception text",
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
