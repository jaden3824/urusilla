from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

import urusilla_hybrid_runtime as hybrid_package
from urusilla_hybrid_runtime.canonical import sha256_text

from urusilla_hybrid_runtime import (
    CostForecast,
    EVOLVING_SURFACE_CAPSULE_SHA256,
    FidelityVerification,
    FidelityVerificationInput,
    HybridExecution,
    HybridRuntimeError,
    LocalOutputValidation,
    ModelReply,
    PublicActionState,
    PublicTaskContext,
    ReceiverError,
    RetainedSurface,
    SurfaceActivationEvidence,
    SurfaceAliasTable,
    SurfaceArtifactVerification,
    SurfaceCarrier,
    SurfaceError,
    SurfaceScope,
    SurfaceShadowExecution,
    SurfaceTrial,
    SurfaceTrialPlan,
    activate_surface,
    build_shadow_surface_action_state_request,
    canonical_json,
    decide_surface_evolution,
    decode_surface_state,
    encode_surface_state,
    execute_receiver,
    execute_prepared_message,
    execute_shadow_surface_request,
    load_capsule,
    optimize_alias_table,
    prepare_message,
    source_text_sha256,
    strict_json_loads,
)
from urusilla_hybrid_runtime.tests.test_hybrid_runtime import (
    FakeCompiler,
    FakeReceiverAdapter,
    action_policy,
    action_receiver,
    complete_forecasts,
    passing_evidence,
    receiver_reply,
    sender_output,
    verify_comprehension,
    verify_fidelity,
    verify_task_context,
    verify_utility,
)


OUTPUT_VALIDATOR_SHA256 = "sha256:" + "7" * 64
ACTIVATION_VERIFIER_SHA256 = "sha256:" + "8" * 64
ROUND_TRIP_VECTORS_SHA256 = "sha256:" + "9" * 64
TRIAL_PLAN_ARTIFACT_SHA256 = "sha256:" + "a" * 64
TRIAL_RESULT_SHA256 = "sha256:" + "b" * 64
TRIAL_VERIFIER_SHA256 = "sha256:" + "c" * 64
TRIAL_TRANSCRIPT_SHA256 = "sha256:" + "d" * 64
SURFACE_ATTEMPT_SHA256 = "sha256:" + "e" * 64
SOURCE_TEXT = "Verify artifact seven without creating external effects."
SOURCE_SHA256 = source_text_sha256(SOURCE_TEXT)


def surface_task_context() -> PublicTaskContext:
    def argument(name: str, meaning: str) -> dict[str, object]:
        return {
            "name": name,
            "type": "string",
            "nullable": False,
            "required": True,
            "unit": None,
            "meaning": meaning,
        }

    def predicate(
        name: str,
        meaning: str,
        positional_args: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "kind": "predicate",
            "name": name,
            "meaning": meaning,
            "positional_args": positional_args,
            "named_args": [],
            "allowed_effects": [],
        }

    return PublicTaskContext.from_object(
        {
            "format": "urusilla-public-task-context-draft/1",
            "task_id": "task.surface-round-trip",
            "objective": "Preserve bounded verification semantics exactly.",
            "output_contract": {
                "media_type": "text/plain",
                "validator_sha256": OUTPUT_VALIDATOR_SHA256,
                "description": "Return one locally validated bounded status.",
            },
            "allowed_acts": ["resolve", "refuse"],
            "outcome_contract": {
                "statuses": ["failed", "rejected"],
                "value": {
                    "name": "value",
                    "type": "string",
                    "nullable": True,
                    "required": True,
                    "unit": None,
                    "meaning": "Bounded result or null when unavailable.",
                },
                "evidence_required": False,
            },
            "uncertainty_contract": {
                "targets": ["failure.cause"],
                "models": ["unspecified"],
                "basis_sources": [],
            },
            "symbols": [
                predicate(
                    "task.verify",
                    "The named artifact is the exact verification target.",
                    [argument("artifact_id", "Stable artifact identifier.")],
                ),
                predicate(
                    "test.passed",
                    "The named test passed exactly when not negated.",
                    [argument("test_unit", "Stable test-unit identifier.")],
                ),
                predicate(
                    "test.failure-log",
                    "A bounded failure log is required.",
                    [],
                ),
                predicate(
                    "x",
                    "One-character reserved semantic-token sentinel.",
                    [],
                ),
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


TASK_CONTEXT = surface_task_context()


def surface_scope(
    *,
    task_context: PublicTaskContext = TASK_CONTEXT,
    session_id: str = "session-surface-1",
    model_context_id: str = "model-context-surface-1",
    tokenizer_ids: tuple[str, ...] = ("tok-a", "tok-b"),
) -> SurfaceScope:
    return SurfaceScope(
        session_id=session_id,
        model_context_id=model_context_id,
        capsule_sha256=load_capsule().sha256,
        surface_capsule_sha256=EVOLVING_SURFACE_CAPSULE_SHA256,
        task_profile_sha256=task_context.task_profile_sha256,
        symbol_table_sha256=task_context.symbol_table_sha256,
        tokenizer_ids=tokenizer_ids,
    )


ROUND_TRIP_ALIASES = {
    "act:refuse": "拒",
    "act:resolve": "解",
    "outcome-status:failed": "敗",
    "outcome-status:rejected": "却",
    "predicate:task.verify": "査",
    "predicate:test.failure-log": "録",
    "predicate:test.passed": "否",
    "uncertainty-model:unspecified": "曖",
    "uncertainty-target:failure.cause": "因",
}


def alias_table(
    aliases: dict[str, str] | None = None,
    *,
    scope: SurfaceScope | None = None,
    task_context: PublicTaskContext = TASK_CONTEXT,
    parent: SurfaceAliasTable | None = None,
) -> SurfaceAliasTable:
    return SurfaceAliasTable.from_mapping(
        scope=scope or surface_scope(task_context=task_context),
        task_context=task_context,
        aliases=aliases or ROUND_TRIP_ALIASES,
        parent=parent,
    )


def activation_evidence(
    table: SurfaceAliasTable,
    *,
    attempt_sha256: str = SURFACE_ATTEMPT_SHA256,
    setup_total_tokens: int = 7,
) -> SurfaceActivationEvidence:
    return SurfaceActivationEvidence(
        table_sha256=table.sha256,
        attempt_sha256=attempt_sha256,
        session_id=table.scope.session_id,
        model_context_id=table.scope.model_context_id,
        round_trip_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
        verifier_sha256=ACTIVATION_VERIFIER_SHA256,
        sender_acknowledged=True,
        receiver_acknowledged=True,
        exact_round_trip_passed=True,
        comprehension_passed=True,
        setup_total_tokens=setup_total_tokens,
        usage_complete=True,
    )


def verify_activation(
    evidence: SurfaceActivationEvidence,
    _table: SurfaceAliasTable,
) -> SurfaceArtifactVerification:
    return SurfaceArtifactVerification(
        passed=True,
        input_binding_sha256=evidence.binding_sha256,
        verifier_sha256=evidence.verifier_sha256,
    )


def active_surface(
    table: SurfaceAliasTable,
    *,
    attempt_sha256: str = SURFACE_ATTEMPT_SHA256,
    setup_total_tokens: int = 7,
):
    return activate_surface(
        table,
        activation_evidence(
            table,
            attempt_sha256=attempt_sha256,
            setup_total_tokens=setup_total_tokens,
        ),
        attempt_sha256=attempt_sha256,
        active_capsule_sha256=table.scope.capsule_sha256,
        expected_round_trip_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
        expected_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
        verifier=verify_activation,
    )


def digest_series(start: int, count: int) -> tuple[str, ...]:
    return tuple(f"sha256:{value:064x}" for value in range(start, start + count))


def case_series(tag: str, count: int) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            f"{tag}-{index}",
            source_text_sha256(f"{tag} source {index}"),
        )
        for index in range(count)
    )


def token_partition(total: int, count: int) -> tuple[int, ...]:
    values = [total // count] * count
    values[-1] += total - sum(values)
    return tuple(values)


def positive_state() -> PublicActionState:
    return PublicActionState.from_object(
        load_capsule().to_object()["examples"]["positive"]
    )


def refusal_state() -> PublicActionState:
    value = copy.deepcopy(positive_state().to_object())
    value["act"] = "refuse"
    value["outcome"]["status"] = "rejected"
    return PublicActionState.from_object(value)


def surface_fidelity(
    state: PublicActionState,
    *,
    source_text: str = SOURCE_TEXT,
    task_context: PublicTaskContext = TASK_CONTEXT,
    maximum_total_tokens: int = 20,
) -> tuple[FidelityVerificationInput, FidelityVerification]:
    item = FidelityVerificationInput(
        source_text=source_text,
        source_sha256=source_text_sha256(source_text),
        state=state,
        task_context=task_context,
        maximum_total_tokens=maximum_total_tokens,
    )
    return item, verify_fidelity(item)


def encode_bound_state(
    state: PublicActionState,
    task_context: PublicTaskContext,
    table: SurfaceAliasTable,
    active,
    *,
    source_text: str = SOURCE_TEXT,
) -> tuple[SurfaceCarrier, FidelityVerificationInput, FidelityVerification]:
    item, proof = surface_fidelity(
        state,
        source_text=source_text,
        task_context=task_context,
    )
    carrier = encode_surface_state(
        state,
        task_context,
        table,
        active,
        fidelity_input=item,
        fidelity_verification=proof,
        expected_fidelity_verifier_sha256=proof.verifier_sha256,
    )
    return carrier, item, proof


def decode_bound_state(
    carrier: SurfaceCarrier,
    task_context: PublicTaskContext,
    table: SurfaceAliasTable,
    active,
    item: FidelityVerificationInput,
    proof: FidelityVerification,
) -> PublicActionState:
    return decode_surface_state(
        carrier,
        task_context,
        table,
        active,
        fidelity_input=item,
        fidelity_verification=proof,
        expected_fidelity_verifier_sha256=proof.verifier_sha256,
    )


def validate_surface_output(item) -> LocalOutputValidation:
    return LocalOutputValidation(
        valid=item.output_text == "valid",
        input_binding_sha256=item.binding_sha256,
        validator_sha256=OUTPUT_VALIDATOR_SHA256,
    )


def replace_carrier_payload(
    carrier: SurfaceCarrier,
    wire: object,
    **overrides: object,
) -> SurfaceCarrier:
    payload_text = canonical_json(wire)
    return replace(
        carrier,
        payload_text=payload_text,
        payload_sha256=source_text_sha256(payload_text),
        **overrides,
    )


class SurfaceAliasAndOptimizerTests(TestCase):
    def test_evolving_surface_capsule_file_matches_pinned_digest(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        capsule_path = project_root / "urusilla_evolving_surface_capsule.json"
        parsed = strict_json_loads(capsule_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sha256_text(canonical_json(parsed)),
            EVOLVING_SURFACE_CAPSULE_SHA256,
        )
        public_document = (project_root / "EVOLVING_SURFACE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            f"`{EVOLVING_SURFACE_CAPSULE_SHA256}`",
            public_document,
        )

    def test_scope_rejects_unknown_surface_capsule_digest(self) -> None:
        with self.assertRaises(SurfaceError):
            SurfaceScope(
                session_id="session-surface-1",
                model_context_id="model-context-surface-1",
                capsule_sha256=load_capsule().sha256,
                surface_capsule_sha256="sha256:" + "0" * 64,
                task_profile_sha256=TASK_CONTEXT.task_profile_sha256,
                symbol_table_sha256=TASK_CONTEXT.symbol_table_sha256,
                tokenizer_ids=("tok-a", "tok-b"),
            )

    def test_optimizer_selects_opaque_unicode_by_worst_tokenizer_not_aesthetics(self) -> None:
        scope = surface_scope()
        costs_a = {"task.verify": 10, "美": 1, "界": 4}
        costs_b = {"task.verify": 10, "美": 9, "界": 4}
        table = optimize_alias_table(
            scope=scope,
            task_context=TASK_CONTEXT,
            semantic_frequencies={"predicate:task.verify": 5},
            candidate_aliases=("美", "界"),
            token_counters={
                "tok-a": costs_a.__getitem__,
                "tok-b": costs_b.__getitem__,
            },
        )
        self.assertEqual(table.mapping, {"predicate:task.verify": "界"})
        self.assertGreater(ord(table.mapping["predicate:task.verify"]), 127)

    def test_optimizer_binds_exact_parent_scope_and_generation(self) -> None:
        scope = surface_scope()
        parent = optimize_alias_table(
            scope=scope,
            task_context=TASK_CONTEXT,
            semantic_frequencies={"predicate:task.verify": 1},
            candidate_aliases=("甲",),
            token_counters={
                "tok-a": lambda text: 2 if text == "task.verify" else 1,
                "tok-b": lambda text: 2 if text == "task.verify" else 1,
            },
        )
        child = optimize_alias_table(
            scope=scope,
            task_context=TASK_CONTEXT,
            semantic_frequencies={"predicate:task.verify": 1},
            candidate_aliases=("乙",),
            token_counters={
                "tok-a": {"task.verify": 3, "甲": 2, "乙": 1}.__getitem__,
                "tok-b": {"task.verify": 3, "甲": 2, "乙": 1}.__getitem__,
            },
            parent=parent,
        )
        self.assertEqual(child.generation, 2)
        self.assertEqual(child.parent_sha256, parent.sha256)

        stale_scope = surface_scope(session_id="session-surface-stale")
        with self.assertRaises(SurfaceError):
            optimize_alias_table(
                scope=stale_scope,
                task_context=TASK_CONTEXT,
                semantic_frequencies={"predicate:task.verify": 1},
                candidate_aliases=("丙",),
                token_counters={
                    "tok-a": lambda _text: 1,
                    "tok-b": lambda _text: 1,
                },
                parent=parent,
            )

    def test_child_requires_strict_parent_relative_improvement(self) -> None:
        scope = surface_scope()
        parent = alias_table(
            {
                "predicate:task.verify": "甲",
                "predicate:test.passed": "乙",
            },
            scope=scope,
        )
        costs = {
            "task.verify": 10,
            "test.passed": 10,
            "甲": 1,
            "乙": 1,
            "丙": 2,
        }
        with self.assertRaises(SurfaceError):
            optimize_alias_table(
                scope=scope,
                task_context=TASK_CONTEXT,
                semantic_frequencies={"predicate:task.verify": 1},
                candidate_aliases=("丙",),
                token_counters={
                    "tok-a": costs.__getitem__,
                    "tok-b": costs.__getitem__,
                },
                parent=parent,
            )

        improving_costs = dict(costs, **{"丙": 0})
        child = optimize_alias_table(
            scope=scope,
            task_context=TASK_CONTEXT,
            semantic_frequencies={"predicate:task.verify": 1},
            candidate_aliases=("丙",),
            token_counters={
                "tok-a": improving_costs.__getitem__,
                "tok-b": improving_costs.__getitem__,
            },
            parent=parent,
        )
        self.assertEqual(child.mapping["predicate:task.verify"], "丙")
        self.assertEqual(child.mapping["predicate:test.passed"], "乙")

    def test_retired_parent_alias_cannot_migrate_within_one_child(self) -> None:
        scope = surface_scope()
        parent = alias_table(
            {
                "predicate:task.verify": "甲",
                "predicate:test.passed": "乙",
            },
            scope=scope,
        )
        costs = {
            "task.verify": 10,
            "test.passed": 10,
            "甲": 1,
            "乙": 4,
            "丙": 0,
        }
        child = optimize_alias_table(
            scope=scope,
            task_context=TASK_CONTEXT,
            semantic_frequencies={
                "predicate:task.verify": 10,
                "predicate:test.passed": 1,
            },
            candidate_aliases=("丙", "甲"),
            token_counters={
                "tok-a": costs.__getitem__,
                "tok-b": costs.__getitem__,
            },
            parent=parent,
        )
        self.assertEqual(child.mapping["predicate:task.verify"], "丙")
        self.assertEqual(child.mapping["predicate:test.passed"], "乙")
        self.assertNotEqual(child.mapping["predicate:test.passed"], "甲")

    def test_role_reserved_and_unsafe_unicode_aliases_are_rejected(self) -> None:
        cases = {
            "nfkc-role": "ＳＹＳＴＥＭ",
            "reserved": "x",
            "nfkc-reserved": "ｘ",
            "control": "\x00",
            "bidi": "\u202e",
            "default-ignorable": "\u2060",
            "variation-selector": "\ufe0f",
            "hangul-choseong-filler": "\u115f",
            "hangul-jungseong-filler": "\u1160",
            "hangul-filler": "\u3164",
            "braille-blank": "\u2800",
            "halfwidth-hangul-filler": "\uffa0",
            "egyptian-hieroglyph-format-1": "\U00013441",
            "egyptian-hieroglyph-format-2": "\U00013442",
        }
        for label, value in cases.items():
            with self.subTest(label=label), self.assertRaises(SurfaceError):
                alias_table({"predicate:task.verify": value})

    def test_nfkc_confusable_and_duplicate_aliases_are_rejected(self) -> None:
        for aliases in (
            {
                "predicate:task.verify": "A",
                "predicate:test.passed": "Ａ",
            },
            {
                "predicate:task.verify": "界",
                "predicate:test.passed": "界",
            },
        ):
            with self.subTest(aliases=aliases), self.assertRaises(SurfaceError):
                alias_table(aliases)

        with self.assertRaises(SurfaceError):
            SurfaceAliasTable(
                scope=surface_scope(),
                generation=1,
                parent_sha256=None,
                aliases=(
                    ("predicate:task.verify", "甲"),
                    ("predicate:task.verify", "乙"),
                ),
            )


class SurfaceActivationAndCarrierTests(TestCase):
    def setUp(self) -> None:
        self.table = alias_table()
        self.evidence = activation_evidence(self.table)
        self.active = active_surface(self.table)
        self.state = positive_state()

    def test_activation_requires_exact_typed_verifier_binding(self) -> None:
        active = activate_surface(
            self.table,
            self.evidence,
            attempt_sha256=SURFACE_ATTEMPT_SHA256,
            active_capsule_sha256=self.table.scope.capsule_sha256,
            expected_round_trip_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
            expected_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
            verifier=verify_activation,
        )
        self.assertTrue(active.authorizes(self.table))
        self.assertEqual(
            active.activation_binding_sha256, self.evidence.binding_sha256
        )

        def wrong_binding(*_args) -> SurfaceArtifactVerification:
            return SurfaceArtifactVerification(
                passed=True,
                input_binding_sha256="sha256:" + "0" * 64,
                verifier_sha256=ACTIVATION_VERIFIER_SHA256,
            )

        def wrong_verifier(*_args) -> SurfaceArtifactVerification:
            return SurfaceArtifactVerification(
                passed=True,
                input_binding_sha256=self.evidence.binding_sha256,
                verifier_sha256="sha256:" + "1" * 64,
            )

        for verifier in (wrong_binding, wrong_verifier):
            with self.subTest(verifier=verifier), self.assertRaises(SurfaceError):
                activate_surface(
                    self.table,
                    self.evidence,
                    attempt_sha256=SURFACE_ATTEMPT_SHA256,
                    active_capsule_sha256=self.table.scope.capsule_sha256,
                    expected_round_trip_vectors_sha256=(
                        ROUND_TRIP_VECTORS_SHA256
                    ),
                    expected_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
                    verifier=verifier,
                )

    def test_raw_activation_evidence_or_boolean_is_not_trusted(self) -> None:
        for raw_result in (self.evidence, {"passed": True}, True):
            with self.subTest(raw_type=type(raw_result).__name__), self.assertRaises(
                SurfaceError
            ):
                activate_surface(
                    self.table,
                    self.evidence,
                    attempt_sha256=SURFACE_ATTEMPT_SHA256,
                    active_capsule_sha256=self.table.scope.capsule_sha256,
                    expected_round_trip_vectors_sha256=(
                        ROUND_TRIP_VECTORS_SHA256
                    ),
                    expected_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
                    verifier=lambda *_args, value=raw_result: value,
                )

    def test_activation_vectors_verifier_and_attempt_are_externally_pinned(
        self,
    ) -> None:
        wrong_digest = "sha256:" + "f" * 64
        for label, evidence, attempt in (
            (
                "vectors",
                replace(
                    self.evidence,
                    round_trip_vectors_sha256=wrong_digest,
                ),
                SURFACE_ATTEMPT_SHA256,
            ),
            (
                "verifier",
                replace(self.evidence, verifier_sha256=wrong_digest),
                SURFACE_ATTEMPT_SHA256,
            ),
            ("attempt", self.evidence, wrong_digest),
        ):
            def echo_verifier(item, _table):
                return SurfaceArtifactVerification(
                    passed=True,
                    input_binding_sha256=item.binding_sha256,
                    verifier_sha256=item.verifier_sha256,
                )

            with self.subTest(label=label), self.assertRaises(SurfaceError):
                activate_surface(
                    self.table,
                    evidence,
                    attempt_sha256=attempt,
                    active_capsule_sha256=self.table.scope.capsule_sha256,
                    expected_round_trip_vectors_sha256=(
                        ROUND_TRIP_VECTORS_SHA256
                    ),
                    expected_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
                    verifier=echo_verifier,
                )

    def test_exact_round_trip_preserves_negation_null_failure_and_refusal(self) -> None:
        for label, state in (
            ("failure", self.state),
            ("refusal", refusal_state()),
        ):
            carrier, fidelity_input, fidelity_proof = encode_bound_state(
                state,
                TASK_CONTEXT,
                self.table,
                self.active,
            )
            recovered = decode_bound_state(
                carrier,
                TASK_CONTEXT,
                self.table,
                self.active,
                fidelity_input,
                fidelity_proof,
            )
            with self.subTest(label=label):
                self.assertEqual(recovered.canonical_text, state.canonical_text)
                self.assertEqual(recovered.sha256, state.sha256)
                self.assertTrue(recovered.to_object()["state"][0]["n"])
                self.assertIsNone(recovered.to_object()["outcome"]["value"])
                if label == "failure":
                    self.assertEqual(
                        recovered.to_object()["outcome"]["status"], "failed"
                    )
                else:
                    self.assertEqual(recovered.to_object()["act"], "refuse")
                    self.assertEqual(
                        recovered.to_object()["outcome"]["status"], "rejected"
                    )

    def test_sibling_table_same_generation_confusion_is_rejected(self) -> None:
        table_a = alias_table({"predicate:task.verify": "甲"})
        table_b = alias_table({"predicate:test.passed": "甲"})
        active_a = active_surface(table_a)
        active_b = active_surface(table_b)
        carrier, fidelity_input, fidelity_proof = encode_bound_state(
            self.state,
            TASK_CONTEXT,
            table_a,
            active_a,
        )
        with self.assertRaises(SurfaceError):
            decode_bound_state(
                carrier,
                TASK_CONTEXT,
                table_b,
                active_b,
                fidelity_input,
                fidelity_proof,
            )

        forged_envelope = replace(carrier, table_sha256=table_b.sha256)
        with self.assertRaises(HybridRuntimeError):
            decode_bound_state(
                forged_envelope,
                TASK_CONTEXT,
                table_b,
                active_b,
                fidelity_input,
                fidelity_proof,
            )

    def test_task_identity_and_semantic_context_replay_are_rejected(self) -> None:
        carrier, fidelity_input, fidelity_proof = encode_bound_state(
            self.state,
            TASK_CONTEXT,
            self.table,
            self.active,
        )
        identity_value = TASK_CONTEXT.to_object()
        identity_value["task_id"] = "task.surface-replay"
        identity_value["objective"] = "A different task with the same profile."
        identity_replay = PublicTaskContext.from_object(identity_value)
        self.assertEqual(
            identity_replay.task_profile_sha256,
            TASK_CONTEXT.task_profile_sha256,
        )
        self.assertEqual(
            identity_replay.symbol_table_sha256,
            TASK_CONTEXT.symbol_table_sha256,
        )
        self.assertNotEqual(identity_replay.sha256, TASK_CONTEXT.sha256)

        semantic_value = TASK_CONTEXT.to_object()
        semantic_value["symbols"][0]["meaning"] += " Rebound meaning."
        semantic_replay = PublicTaskContext.from_object(semantic_value)
        self.assertNotEqual(
            semantic_replay.symbol_table_sha256,
            TASK_CONTEXT.symbol_table_sha256,
        )
        for label, replay in (
            ("task-identity", identity_replay),
            ("symbol-semantics", semantic_replay),
        ):
            with self.subTest(label=label), self.assertRaises(SurfaceError):
                decode_bound_state(
                    carrier,
                    replay,
                    self.table,
                    self.active,
                    fidelity_input,
                    fidelity_proof,
                )

    def test_stale_generation_source_and_forged_state_digest_are_rejected(self) -> None:
        carrier, fidelity_input, fidelity_proof = encode_bound_state(
            self.state,
            TASK_CONTEXT,
            self.table,
            self.active,
        )
        attacks = (
            ("generation", replace(carrier, generation=carrier.generation + 1)),
            (
                "state-digest",
                replace(carrier, state_sha256="sha256:" + "3" * 64),
            ),
        )
        for label, attacked in attacks:
            with self.subTest(label=label), self.assertRaises(SurfaceError):
                decode_bound_state(
                    attacked,
                    TASK_CONTEXT,
                    self.table,
                    self.active,
                    fidelity_input,
                    fidelity_proof,
                )

        other_input, other_proof = surface_fidelity(
            self.state,
            source_text="A different source message.",
        )
        with self.subTest(label="source"), self.assertRaises(SurfaceError):
            decode_bound_state(
                carrier,
                TASK_CONTEXT,
                self.table,
                self.active,
                other_input,
                other_proof,
            )

        parent = alias_table({"predicate:task.verify": "甲"})
        child = alias_table(
            {"predicate:task.verify": "乙"},
            scope=parent.scope,
            parent=parent,
        )
        with self.assertRaises(SurfaceError):
            encode_surface_state(
                self.state,
                TASK_CONTEXT,
                child,
                active_surface(parent),
                fidelity_input=fidelity_input,
                fidelity_verification=fidelity_proof,
                expected_fidelity_verifier_sha256=(
                    fidelity_proof.verifier_sha256
                ),
            )

    def test_unknown_alias_stale_alias_and_boolean_markers_fail_closed(self) -> None:
        carrier, fidelity_input, fidelity_proof = encode_bound_state(
            self.state,
            TASK_CONTEXT,
            self.table,
            self.active,
        )
        original = strict_json_loads(carrier.payload_text)

        unknown = copy.deepcopy(original)
        unknown[2][0] = "z"
        stale = copy.deepcopy(original)
        stale[2][0] = "甲"
        bool_negation = copy.deepcopy(original)
        bool_negation[2][2] = True
        bool_generation = copy.deepcopy(original)
        bool_generation[0] = True
        for label, wire in (
            ("unknown", unknown),
            ("stale", stale),
            ("bool-negation", bool_negation),
            ("bool-generation", bool_generation),
        ):
            attacked = replace_carrier_payload(carrier, wire)
            with self.subTest(label=label), self.assertRaises(HybridRuntimeError):
                decode_bound_state(
                    attacked,
                    TASK_CONTEXT,
                    self.table,
                    self.active,
                    fidelity_input,
                    fidelity_proof,
                )

    def test_bare_digest_and_cross_message_fidelity_replay_are_rejected(self) -> None:
        fidelity_input, fidelity_proof = surface_fidelity(self.state)
        with self.assertRaisesRegex(TypeError, "source_sha256"):
            encode_surface_state(
                self.state,
                TASK_CONTEXT,
                self.table,
                self.active,
                source_sha256=SOURCE_SHA256,
            )

        carrier, _, _ = encode_bound_state(
            self.state,
            TASK_CONTEXT,
            self.table,
            self.active,
        )
        with self.assertRaisesRegex(TypeError, "expected_source_sha256"):
            decode_surface_state(
                carrier,
                TASK_CONTEXT,
                self.table,
                self.active,
                expected_source_sha256=SOURCE_SHA256,
            )

        other_input, other_proof = surface_fidelity(
            self.state,
            source_text="A different source message.",
        )
        with self.assertRaises(SurfaceError):
            encode_surface_state(
                self.state,
                TASK_CONTEXT,
                self.table,
                self.active,
                fidelity_input=other_input,
                fidelity_verification=fidelity_proof,
                expected_fidelity_verifier_sha256=(
                    fidelity_proof.verifier_sha256
                ),
            )
        with self.assertRaises(SurfaceError):
            decode_bound_state(
                carrier,
                TASK_CONTEXT,
                self.table,
                self.active,
                other_input,
                other_proof,
            )

        other_state_input, other_state_proof = surface_fidelity(refusal_state())
        with self.assertRaises(SurfaceError):
            encode_surface_state(
                self.state,
                TASK_CONTEXT,
                self.table,
                self.active,
                fidelity_input=other_state_input,
                fidelity_verification=other_state_proof,
                expected_fidelity_verifier_sha256=(
                    other_state_proof.verifier_sha256
                ),
            )


class SurfaceRouterIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.state = positive_state()
        self.table = alias_table()
        self.source_text = (
            "Resolve artifact-7: test unit did not pass, its result is "
            "unavailable, a failure log is needed, and the failure cause "
            "remains unspecified. "
        ) * 240
        action_forecast = CostForecast(
            comprehension_setup_tokens=0,
            receiver_payload_token_ceiling=2_000,
            complete=True,
        )
        self.forecasts = complete_forecasts(
            **{
                "action-state": action_forecast,
                "action-state-surface": action_forecast,
            }
        )

    def retain(self, table: SurfaceAliasTable, active) -> RetainedSurface:
        plan = SurfaceTrialPlan(
            plan_artifact_sha256=TRIAL_PLAN_ARTIFACT_SHA256,
            expected_activation_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
            expected_activation_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
            expected_trial_verifier_sha256=TRIAL_VERIFIER_SHA256,
            exact_message_count=20,
            minimum_messages=20,
            shadow_call_token_ceiling=100,
            shadow_aggregate_token_ceiling=2_000,
            switching_margin_tokens_per_safe_completion=10,
        )
        trial = SurfaceTrial(
            table_sha256=table.sha256,
            attempt_sha256=active.attempt_sha256,
            activation_binding_sha256=active.activation_binding_sha256,
            plan_sha256=plan.sha256,
            result_sha256=TRIAL_RESULT_SHA256,
            transcript_sha256=TRIAL_TRANSCRIPT_SHA256,
            verifier_sha256=TRIAL_VERIFIER_SHA256,
            executed_cases=case_series("router-heldout", 20),
            baseline_execution_binding_sha256s=digest_series(1_000, 20),
            baseline_request_binding_sha256s=digest_series(1_100, 20),
            baseline_configured_token_ceilings=(100,) * 20,
            baseline_observed_total_tokens=(100,) * 20,
            shadow_execution_binding_sha256s=digest_series(100, 20),
            shadow_request_binding_sha256s=digest_series(200, 20),
            shadow_configured_token_ceilings=(100,) * 20,
            shadow_observed_total_tokens=(25,) * 20,
            prior_evolution_overhead_tokens=0,
            message_count=20,
            baseline_total_tokens=2_000,
            activation_setup_tokens=active.setup_total_tokens,
            surface_runtime_tokens_excluding_setup=500,
            surface_total_tokens_including_setup=(
                active.setup_total_tokens + 500
            ),
            baseline_safe_completions=20,
            surface_safe_completions=20,
            parse_valid=20,
            fidelity_valid=20,
            negation_preserved=True,
            null_preserved=True,
            failure_preserved=True,
            refusal_preserved=True,
            usage_complete=True,
            frozen_before_execution=True,
            measurement_scope_complete=True,
        )

        def verify(
            item: SurfaceTrial,
            _plan: SurfaceTrialPlan,
            _table: SurfaceAliasTable,
            _active,
        ) -> SurfaceArtifactVerification:
            return SurfaceArtifactVerification(
                passed=item.binding_sha256 == trial.binding_sha256,
                input_binding_sha256=trial.binding_sha256,
                verifier_sha256=TRIAL_VERIFIER_SHA256,
            )

        decision = decide_surface_evolution(
            table,
            trial,
            active_surface=active,
            plan=plan,
            verifier=verify,
        )
        self.assertEqual(decision.action, "keep")
        self.assertIsInstance(decision.retained_surface, RetainedSurface)
        assert decision.retained_surface is not None
        return decision.retained_surface

    @staticmethod
    def surface_only_forecasts() -> dict[str, CostForecast]:
        return complete_forecasts(
            **{
                "action-state": CostForecast(
                    comprehension_setup_tokens=0,
                    receiver_payload_token_ceiling=50_000,
                    complete=True,
                ),
                "action-state-surface": CostForecast(
                    comprehension_setup_tokens=0,
                    receiver_payload_token_ceiling=2_000,
                    complete=True,
                ),
            }
        )

    def prepare_with_surface(
        self,
        active,
        *,
        retained=None,
        table: SurfaceAliasTable | None = None,
        forecasts=None,
        compiler=None,
    ):
        selected_table = table or self.table
        return prepare_message(
            self.source_text,
            self.capsule,
            action_receiver(
                self.capsule.sha256,
                cached=False,
                task_context=TASK_CONTEXT,
            ),
            len,
            task_context=TASK_CONTEXT,
            forecasts=forecasts or self.forecasts,
            evidence={
                "action-state": passing_evidence(task_context=TASK_CONTEXT)
            },
            compiler=compiler
            or FakeCompiler(
                ModelReply(sender_output(self.state), "compiler-model-a", 10)
            ),
            surface_table=selected_table,
            active_surface=active,
            retained_surface=retained,
            policy=action_policy(receiver_total_token_ceiling=20_000),
            fidelity_verifier=verify_fidelity,
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )

    def build_shadow(
        self,
        active,
        *,
        table: SurfaceAliasTable | None = None,
        maximum_total_tokens: int | None = 20,
    ):
        selected_table = table or self.table
        receiver = action_receiver(
            self.capsule.sha256,
            cached=False,
            task_context=TASK_CONTEXT,
        )
        fidelity_input, fidelity_proof = surface_fidelity(
            self.state,
            source_text=self.source_text,
        )
        return build_shadow_surface_action_state_request(
            self.state,
            self.capsule,
            TASK_CONTEXT,
            selected_table,
            active,
            fidelity_input=fidelity_input,
            fidelity_verification=fidelity_proof,
            expected_fidelity_verifier_sha256=(
                fidelity_proof.verifier_sha256
            ),
            task_context_cached_in_same_model_context=(
                receiver.task_context_cached_in_same_model_context
            ),
            task_context_id=receiver.task_context_id,
            task_comprehension_evidence_sha256=(
                receiver.task_context_comprehension_sha256
            ),
            task_comprehension_verifier_sha256=(
                receiver.task_context_comprehension_verifier_sha256
            ),
            capsule_cached_in_same_model_context=(
                receiver.capsule_cached_in_same_model_context
            ),
            capsule_context_id=receiver.capsule_context_id,
            comprehension_evidence_sha256=(
                receiver.capsule_comprehension_sha256 or ""
            ),
            capsule_comprehension_verifier_sha256=(
                receiver.capsule_comprehension_verifier_sha256 or ""
            ),
            maximum_total_tokens=maximum_total_tokens,
        )

    def test_router_uses_marginal_surface_cost_and_delivers_it_directly(
        self,
    ) -> None:
        active = active_surface(self.table, setup_total_tokens=7)
        retained = self.retain(self.table, active)
        prepared = self.prepare_with_surface(active, retained=retained)
        request = prepared.route.request

        self.assertEqual(prepared.route.selected_mode, "action-state")
        self.assertIsNotNone(request.surface_carrier)
        self.assertIs(request.surface_table, self.table)
        self.assertIs(request.active_surface, active)
        self.assertIs(request.retained_surface, retained)
        carrier = request.surface_carrier
        assert carrier is not None
        self.assertEqual(request.payload_text, carrier.payload_text)
        self.assertEqual(request.payload_sha256, carrier.payload_sha256)
        self.assertLess(len(request.payload_text), len(self.state.canonical_text))
        self.assertFalse(request.decode_before_model)
        self.assertIsNone(request.natural_language_expansion)
        self.assertTrue(
            request.model_visible_text.endswith("PAYLOAD\n" + carrier.payload_text)
        )
        self.assertEqual(carrier.table_sha256, self.table.sha256)
        self.assertEqual(carrier.task_context_sha256, TASK_CONTEXT.sha256)
        self.assertEqual(carrier.source_sha256, prepared.route.source_sha256)
        self.assertEqual(carrier.state_sha256, self.state.sha256)
        self.assertIsNotNone(request.surface_fidelity_input)
        self.assertIsNotNone(request.surface_fidelity_verification)
        self.assertEqual(
            request.surface_fidelity_input.binding_sha256,
            request.surface_fidelity_verification.input_binding_sha256,
        )
        self.assertEqual(
            request.surface_expected_fidelity_verifier_sha256,
            request.surface_fidelity_verification.verifier_sha256,
        )
        self.assertFalse(prepared.route.claim_eligible)
        self.assertFalse(prepared.route.goal_gate_passed)
        action_candidate = next(
            item
            for item in prepared.route.candidates
            if item.mode == "action-state"
        )
        self.assertIn(
            "session-local-retained-surface-only",
            action_candidate.reasons,
        )

    def test_session_setup_is_not_recharged_to_each_surface_message(
        self,
    ) -> None:
        cheap_active = active_surface(self.table, setup_total_tokens=7)
        cheap = self.prepare_with_surface(
            cheap_active,
            retained=self.retain(self.table, cheap_active),
        )
        expensive = active_surface(self.table, setup_total_tokens=1_000)
        prepared = self.prepare_with_surface(
            expensive,
            retained=self.retain(self.table, expensive),
        )
        request = prepared.route.request

        self.assertEqual(prepared.route.selected_mode, "action-state")
        self.assertIsNotNone(request.surface_carrier)
        self.assertEqual(
            prepared.route.selected_cost,
            cheap.route.selected_cost,
        )

    def test_surface_forecast_can_authorize_compiler_when_canonical_preflight_loses(
        self,
    ) -> None:
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "compiler-model-a", 10)
        )
        active = active_surface(self.table)
        prepared = self.prepare_with_surface(
            active,
            retained=self.retain(self.table, active),
            forecasts=self.surface_only_forecasts(),
            compiler=compiler,
        )

        self.assertEqual(compiler.calls, 1)
        self.assertEqual(prepared.route.selected_mode, "action-state")
        self.assertIsNotNone(prepared.route.request.surface_carrier)

    def test_active_only_is_shadow_eligible_and_cannot_enable_live_surface(self) -> None:
        active = active_surface(self.table)
        canonical = self.prepare_with_surface(active)
        self.assertEqual(canonical.route.selected_mode, "action-state")
        self.assertIsNone(canonical.route.request.surface_carrier)
        self.assertIsNone(canonical.route.request.retained_surface)

        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "compiler-model-a", 10)
        )
        baseline = self.prepare_with_surface(
            active,
            forecasts=self.surface_only_forecasts(),
            compiler=compiler,
        )
        self.assertEqual(compiler.calls, 0)
        self.assertIn(baseline.route.selected_mode, {"raw", "json"})
        self.assertIsNone(baseline.route.request.surface_carrier)
        self.assertTrue(
            all(
                item.request is None
                or item.request.delivery_disposition == "live"
                for item in baseline.route.candidates
            )
        )

    def test_shadow_execution_is_bounded_discard_only_and_not_hybrid_live(self) -> None:
        active = active_surface(self.table)
        with self.assertRaises(ReceiverError):
            self.build_shadow(active, maximum_total_tokens=None)
        shadow = self.build_shadow(active)
        self.assertEqual(shadow.delivery_disposition, "shadow")
        self.assertIsNone(shadow.retained_surface)
        self.assertIsNotNone(shadow.surface_carrier)

        public_adapter = FakeReceiverAdapter(receiver_reply())
        with self.assertRaises(ReceiverError):
            execute_receiver(shadow, public_adapter)
        self.assertEqual(public_adapter.calls, 0)

        shadow_adapter = FakeReceiverAdapter(receiver_reply())
        execution = execute_shadow_surface_request(shadow, shadow_adapter)
        self.assertIsInstance(execution, SurfaceShadowExecution)
        self.assertEqual(shadow_adapter.calls, 1)
        self.assertEqual(execution.execution.status, "completed")
        self.assertTrue(execution.output_discard_required)
        self.assertFalse(execution.eligible_for_live_answer)
        self.assertFalse(execution.eligible_for_claim)

        uncapped = replace(shadow, maximum_total_tokens=None)
        uncapped_adapter = FakeReceiverAdapter(receiver_reply())
        with self.assertRaises(ReceiverError):
            execute_shadow_surface_request(uncapped, uncapped_adapter)
        self.assertEqual(uncapped_adapter.calls, 0)

        retained = self.retain(self.table, active)
        live = self.prepare_with_surface(active, retained=retained)
        self.assertEqual(live.route.request.delivery_disposition, "live")
        self.assertFalse(
            hasattr(hybrid_package, "build_surface_action_state_request")
        )
        public_live_adapter = FakeReceiverAdapter(receiver_reply())
        with self.assertRaises(ReceiverError):
            execute_receiver(live.route.request, public_live_adapter)
        self.assertEqual(public_live_adapter.calls, 0)
        with self.assertRaises(ReceiverError):
            replace(
                execution.execution,
                request_binding_sha256=live.route.request.binding_sha256,
            )
        with self.assertRaises(ReceiverError):
            replace(execution.execution, delivery_disposition="live")
        with self.assertRaises(ReceiverError):
            replace(shadow, delivery_disposition="live")
        with self.assertRaises(ReceiverError):
            replace(live.route.request, delivery_disposition="shadow")
        with self.assertRaises(HybridRuntimeError):
            replace(live.route, request=shadow)
        with self.assertRaises(ValueError):
            HybridExecution(
                prepared=live,
                primary=execution.execution,
                fallback=None,
                final_mode="action-state",
                compiler_calls=1,
                fidelity_verifier_calls=1,
                receiver_calls=1,
                output_valid=True,
                safely_completed=True,
                observed_runtime_tokens=22,
            )

        normal = execute_prepared_message(
            live,
            FakeReceiverAdapter(receiver_reply("valid")),
            output_validator=validate_surface_output,
        )
        self.assertEqual(normal.primary.delivery_disposition, "live")
        self.assertIsNone(normal.fallback)
        self.assertTrue(normal.safely_completed)

        fallback = execute_prepared_message(
            live,
            FakeReceiverAdapter(
                receiver_reply("invalid"),
                receiver_reply("valid"),
            ),
            output_validator=validate_surface_output,
        )
        self.assertEqual(fallback.primary.delivery_disposition, "live")
        self.assertIsNotNone(fallback.fallback)
        assert fallback.fallback is not None
        self.assertEqual(fallback.fallback.delivery_disposition, "live")
        self.assertIn(fallback.final_mode, {"raw", "json"})
        self.assertTrue(fallback.safely_completed)

    def test_retained_surface_is_sealed_and_context_replay_fails_closed(self) -> None:
        active = active_surface(self.table)
        retained = self.retain(self.table, active)
        retained_values = {
            name: getattr(retained, name)
            for name in (
                "table_sha256",
                "attempt_sha256",
                "activation_binding_sha256",
                "session_id",
                "model_context_id",
                "generation",
                "plan_sha256",
                "plan_artifact_sha256",
                "trial_binding_sha256",
                "result_sha256",
                "transcript_sha256",
                "verifier_sha256",
                "surface_capsule_sha256",
            )
        }
        with self.assertRaises(SurfaceError):
            RetainedSurface(**retained_values)

        for field_name, forged_value in (
            ("table_sha256", "sha256:" + "0" * 64),
            ("activation_binding_sha256", "sha256:" + "1" * 64),
            ("session_id", "session-surface-forged"),
            ("model_context_id", "model-context-forged"),
            ("generation", retained.generation + 1),
            ("trial_binding_sha256", "sha256:" + "2" * 64),
        ):
            with self.subTest(forged=field_name), self.assertRaises(SurfaceError):
                replace(retained, **{field_name: forged_value})

        sibling = alias_table({"predicate:task.verify": "別"})
        child = alias_table(
            {"predicate:task.verify": "乙"},
            scope=self.table.scope,
            parent=self.table,
        )
        reset_session = alias_table(
            scope=surface_scope(session_id="session-surface-reset")
        )
        reset_model = alias_table(
            scope=surface_scope(model_context_id="model-context-reset")
        )
        for label, replay_table in (
            ("sibling", sibling),
            ("stale-generation", child),
            ("session-reset", reset_session),
            ("model-context-reset", reset_model),
        ):
            replay_active = active_surface(replay_table)
            compiler = FakeCompiler(
                ModelReply(sender_output(self.state), "compiler-model-a", 10)
            )
            prepared = self.prepare_with_surface(
                replay_active,
                retained=retained,
                table=replay_table,
                forecasts=self.surface_only_forecasts(),
                compiler=compiler,
            )
            with self.subTest(label=label):
                self.assertEqual(compiler.calls, 0)
                self.assertIn(prepared.route.selected_mode, {"raw", "json"})
                self.assertIsNone(prepared.route.request.surface_carrier)


class SurfaceEvolutionTests(TestCase):
    def setUp(self) -> None:
        self.table = alias_table({"predicate:task.verify": "界"})
        self.active = active_surface(self.table)
        self.plan = SurfaceTrialPlan(
            plan_artifact_sha256=TRIAL_PLAN_ARTIFACT_SHA256,
            expected_activation_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
            expected_activation_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
            expected_trial_verifier_sha256=TRIAL_VERIFIER_SHA256,
            exact_message_count=20,
            minimum_messages=20,
            shadow_call_token_ceiling=100,
            shadow_aggregate_token_ceiling=2_000,
            switching_margin_tokens_per_safe_completion=10,
        )

    def trial(self, **overrides: object) -> SurfaceTrial:
        message_count = int(overrides.get("message_count", 20))
        baseline_total = overrides.get("baseline_total_tokens", 2_000)
        baseline_call_tokens = (
            (None,) * message_count
            if baseline_total is None
            else token_partition(int(baseline_total), message_count)
        )
        values: dict[str, object] = {
            "table_sha256": self.table.sha256,
            "attempt_sha256": self.active.attempt_sha256,
            "activation_binding_sha256": (
                self.active.activation_binding_sha256
            ),
            "plan_sha256": self.plan.sha256,
            "result_sha256": TRIAL_RESULT_SHA256,
            "transcript_sha256": TRIAL_TRANSCRIPT_SHA256,
            "verifier_sha256": TRIAL_VERIFIER_SHA256,
            "executed_cases": case_series("evolution-heldout", message_count),
            "baseline_execution_binding_sha256s": digest_series(
                1_300,
                message_count,
            ),
            "baseline_request_binding_sha256s": digest_series(
                1_500,
                message_count,
            ),
            "baseline_configured_token_ceilings": (100,) * message_count,
            "baseline_observed_total_tokens": baseline_call_tokens,
            "shadow_execution_binding_sha256s": digest_series(
                300,
                message_count,
            ),
            "shadow_request_binding_sha256s": digest_series(
                400,
                message_count,
            ),
            "shadow_configured_token_ceilings": (100,) * message_count,
            "shadow_observed_total_tokens": (80,) * message_count,
            "prior_evolution_overhead_tokens": 0,
            "message_count": message_count,
            "baseline_total_tokens": 2_000,
            "activation_setup_tokens": self.active.setup_total_tokens,
            "surface_runtime_tokens_excluding_setup": 1_773,
            "surface_total_tokens_including_setup": 1_780,
            "baseline_safe_completions": 20,
            "surface_safe_completions": 20,
            "parse_valid": 20,
            "fidelity_valid": 20,
            "negation_preserved": True,
            "null_preserved": True,
            "failure_preserved": True,
            "refusal_preserved": True,
            "usage_complete": True,
            "frozen_before_execution": True,
            "measurement_scope_complete": True,
            "external_effects_performed": False,
        }
        values.update(overrides)
        return SurfaceTrial(**values)

    @staticmethod
    def trusted_trial_verifier(
        expected: SurfaceTrial,
    ):
        def verify(
            trial: SurfaceTrial,
            _plan: SurfaceTrialPlan,
            _table: SurfaceAliasTable,
            _active_surface,
        ) -> SurfaceArtifactVerification:
            return SurfaceArtifactVerification(
                passed=trial.binding_sha256 == expected.binding_sha256,
                input_binding_sha256=expected.binding_sha256,
                verifier_sha256=TRIAL_VERIFIER_SHA256,
            )

        return verify

    def decide(
        self,
        trial: SurfaceTrial,
        *,
        active=None,
        verifier=None,
        plan: SurfaceTrialPlan | None = None,
    ):
        return decide_surface_evolution(
            self.table,
            trial,
            active_surface=active or self.active,
            plan=plan or self.plan,
            verifier=verifier or self.trusted_trial_verifier(trial),
        )

    def test_keep_requires_strict_inclusive_total_token_advantage(self) -> None:
        passing_trial = self.trial()
        keep = self.decide(passing_trial)
        self.assertEqual(keep.action, "keep")
        self.assertEqual(keep.measured_savings_tokens, 11)
        self.assertEqual(keep.reasons, ())
        self.assertIsInstance(keep.retained_surface, RetainedSurface)
        assert keep.retained_surface is not None
        self.assertTrue(keep.retained_surface.authorizes(self.table, self.active))
        self.assertEqual(
            keep.retained_surface.trial_binding_sha256,
            passing_trial.binding_sha256,
        )
        self.assertEqual(keep.retained_surface.plan_sha256, self.plan.sha256)
        self.assertEqual(
            keep.retained_surface.plan_artifact_sha256,
            self.plan.plan_artifact_sha256,
        )
        self.assertEqual(
            keep.retained_surface.result_sha256,
            passing_trial.result_sha256,
        )
        self.assertEqual(
            keep.retained_surface.transcript_sha256,
            passing_trial.transcript_sha256,
        )
        self.assertEqual(
            keep.retained_surface.surface_capsule_sha256,
            EVOLVING_SURFACE_CAPSULE_SHA256,
        )
        self.assertEqual(
            passing_trial.activation_setup_tokens,
            self.active.setup_total_tokens,
        )

        equal_margin = self.decide(
            self.trial(
                surface_runtime_tokens_excluding_setup=1_793,
                surface_total_tokens_including_setup=1_800,
            )
        )
        self.assertEqual(equal_margin.action, "rollback")
        self.assertIsNone(equal_margin.retained_surface)
        self.assertIn("no-strict-total-token-advantage", equal_margin.reasons)

    def test_trial_total_including_one_time_activation_setup_can_force_rollback(
        self,
    ) -> None:
        decision = self.decide(
            self.trial(
                baseline_total_tokens=2_000,
                surface_runtime_tokens_excluding_setup=1_994,
                surface_total_tokens_including_setup=2_001,
            )
        )
        self.assertEqual(decision.action, "rollback")
        self.assertIsNone(decision.retained_surface)
        self.assertIn("no-strict-total-token-advantage", decision.reasons)

    def test_trial_setup_accounting_reconciles_and_binds_exact_activation(
        self,
    ) -> None:
        with self.assertRaises(SurfaceError):
            self.trial(
                activation_setup_tokens=10_000,
                surface_runtime_tokens_excluding_setup=0,
                surface_total_tokens_including_setup=1,
            )

        self_consistent_mismatch = self.trial(
            activation_setup_tokens=self.active.setup_total_tokens + 1,
            surface_runtime_tokens_excluding_setup=1_772,
            surface_total_tokens_including_setup=1_780,
        )
        mismatch = self.decide(self_consistent_mismatch)
        self.assertEqual(mismatch.action, "rollback")
        self.assertIsNone(mismatch.retained_surface)
        self.assertIn("activation-setup-token-mismatch", mismatch.reasons)

        exact = self.decide(self.trial())
        self.assertEqual(exact.action, "keep")
        self.assertIsNotNone(exact.retained_surface)

        aggregate_overrun = self.decide(
            self.trial(
                baseline_total_tokens=3_000,
                surface_runtime_tokens_excluding_setup=2_001,
                surface_total_tokens_including_setup=(
                    self.active.setup_total_tokens + 2_001
                ),
            )
        )
        self.assertEqual(aggregate_overrun.action, "rollback")
        self.assertIsNone(aggregate_overrun.retained_surface)
        self.assertIn(
            "shadow-aggregate-token-ceiling-exceeded",
            aggregate_overrun.reasons,
        )

    def test_per_call_receipts_and_pinned_verifiers_are_hard_gates(self) -> None:
        per_call_overrun = self.decide(
            self.trial(
                shadow_observed_total_tokens=(101,) + (79,) * 19,
            )
        )
        self.assertEqual(per_call_overrun.action, "rollback")
        self.assertIn(
            "shadow-call-token-ceiling-exceeded",
            per_call_overrun.reasons,
        )
        self.assertNotIn(
            "shadow-aggregate-token-ceiling-exceeded",
            per_call_overrun.reasons,
        )

        configured_mismatch = self.decide(
            self.trial(
                shadow_configured_token_ceilings=(99,) + (100,) * 19,
            )
        )
        self.assertIn(
            "shadow-call-token-ceiling-mismatch",
            configured_mismatch.reasons,
        )

        baseline_configured_mismatch = self.decide(
            self.trial(
                baseline_configured_token_ceilings=(99,) + (100,) * 19,
            )
        )
        self.assertIn(
            "baseline-call-token-ceiling-mismatch",
            baseline_configured_mismatch.reasons,
        )
        with self.assertRaises(SurfaceError):
            self.trial(baseline_configured_token_ceilings=(100,) * 19)
        with self.assertRaises(SurfaceError):
            self.trial(
                baseline_configured_token_ceilings=(0,) + (100,) * 19,
            )

        baseline_overrun = self.decide(
            self.trial(
                baseline_observed_total_tokens=(101, 99) + (100,) * 18,
            )
        )
        self.assertIn(
            "baseline-call-token-ceiling-exceeded",
            baseline_overrun.reasons,
        )

        baseline_total_mismatch = self.decide(
            self.trial(
                baseline_observed_total_tokens=(99,) + (100,) * 19,
            )
        )
        self.assertIn(
            "baseline-call-usage-total-mismatch",
            baseline_total_mismatch.reasons,
        )

        incomplete = self.decide(
            self.trial(
                shadow_observed_total_tokens=(None,) + (80,) * 19,
                usage_complete=False,
            )
        )
        self.assertIn("incomplete-total-token-usage", incomplete.reasons)

        with self.assertRaises(SurfaceError):
            self.trial(shadow_request_binding_sha256s=digest_series(1, 19))
        with self.assertRaises(SurfaceError):
            self.trial(
                shadow_request_binding_sha256s=digest_series(1_500, 20),
            )
        duplicate_cases = list(case_series("duplicate", 20))
        duplicate_cases[-1] = duplicate_cases[0]
        with self.assertRaises(SurfaceError):
            self.trial(executed_cases=tuple(duplicate_cases))

        wrong_verifier_plan = replace(
            self.plan,
            expected_trial_verifier_sha256="sha256:" + "f" * 64,
        )
        verifier_mismatch = self.decide(
            self.trial(plan_sha256=wrong_verifier_plan.sha256),
            plan=wrong_verifier_plan,
        )
        self.assertIn(
            "trial-verifier-differs-from-frozen-plan",
            verifier_mismatch.reasons,
        )
        self.assertIn(
            "trial-artifact-verification-failed",
            verifier_mismatch.reasons,
        )

    def test_prior_rejected_evolution_cost_is_included_in_advantage(self) -> None:
        decision = self.decide(
            self.trial(
                baseline_total_tokens=2_000,
                prior_evolution_overhead_tokens=500,
            )
        )
        self.assertEqual(decision.action, "rollback")
        self.assertIn("no-strict-total-token-advantage", decision.reasons)

    def test_frozen_plan_artifact_and_exact_message_count_are_mandatory(
        self,
    ) -> None:
        with self.assertRaises(SurfaceError):
            SurfaceTrialPlan(
                plan_artifact_sha256="not-a-digest",
                expected_activation_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
                expected_activation_verifier_sha256=(
                    ACTIVATION_VERIFIER_SHA256
                ),
                expected_trial_verifier_sha256=TRIAL_VERIFIER_SHA256,
                exact_message_count=20,
                minimum_messages=20,
                shadow_call_token_ceiling=100,
                shadow_aggregate_token_ceiling=2_000,
                switching_margin_tokens_per_safe_completion=10,
            )
        with self.assertRaises(TypeError):
            SurfaceTrialPlan(
                exact_message_count=20,
                minimum_messages=20,
                shadow_call_token_ceiling=100,
                shadow_aggregate_token_ceiling=2_000,
                switching_margin_tokens_per_safe_completion=10,
            )

        longer_plan = SurfaceTrialPlan(
            plan_artifact_sha256=TRIAL_PLAN_ARTIFACT_SHA256,
            expected_activation_vectors_sha256=ROUND_TRIP_VECTORS_SHA256,
            expected_activation_verifier_sha256=ACTIVATION_VERIFIER_SHA256,
            expected_trial_verifier_sha256=TRIAL_VERIFIER_SHA256,
            exact_message_count=21,
            minimum_messages=20,
            shadow_call_token_ceiling=100,
            shadow_aggregate_token_ceiling=2_000,
            switching_margin_tokens_per_safe_completion=10,
        )
        below_exact = self.trial(
            plan_sha256=longer_plan.sha256,
            message_count=20,
        )
        below = self.decide(below_exact, plan=longer_plan)
        self.assertEqual(below.action, "rollback")
        self.assertIsNone(below.retained_surface)
        self.assertNotIn("insufficient-bounded-trial-messages", below.reasons)
        self.assertIn(
            "trial-message-count-differs-from-frozen-plan",
            below.reasons,
        )

        above_exact = self.trial(
            message_count=21,
            parse_valid=21,
            fidelity_valid=21,
        )
        above = self.decide(above_exact)
        self.assertEqual(above.action, "rollback")
        self.assertIsNone(above.retained_surface)
        self.assertNotIn("insufficient-bounded-trial-messages", above.reasons)
        self.assertIn(
            "trial-message-count-differs-from-frozen-plan",
            above.reasons,
        )

    def test_any_semantic_safety_or_accounting_regression_rolls_back(self) -> None:
        cases = (
            ("safe", {"surface_safe_completions": 19}),
            ("parse", {"parse_valid": 19}),
            ("fidelity", {"fidelity_valid": 19}),
            ("negation", {"negation_preserved": False}),
            ("null", {"null_preserved": False}),
            ("failure", {"failure_preserved": False}),
            ("refusal", {"refusal_preserved": False}),
            ("not-frozen", {"frozen_before_execution": False}),
            ("scope-incomplete", {"measurement_scope_complete": False}),
            ("persistence", {"persistence_created": True}),
            ("permission", {"permission_expanded": True}),
            ("spending", {"spending_authority_created": True}),
            ("effect", {"external_effects_performed": True}),
            (
                "incomplete-usage",
                {
                    "baseline_total_tokens": None,
                    "surface_runtime_tokens_excluding_setup": None,
                    "surface_total_tokens_including_setup": None,
                    "shadow_observed_total_tokens": (None,) * 20,
                    "usage_complete": False,
                },
            ),
            (
                "insufficient-trial",
                {
                    "message_count": 19,
                    "baseline_safe_completions": 19,
                    "surface_safe_completions": 19,
                    "parse_valid": 19,
                    "fidelity_valid": 19,
                },
            ),
        )
        for label, overrides in cases:
            decision = self.decide(self.trial(**overrides))
            with self.subTest(label=label):
                self.assertEqual(decision.action, "rollback")
                self.assertIsNone(decision.retained_surface)
                self.assertTrue(decision.reasons)

    def test_self_reported_unactivated_or_forged_trial_cannot_keep(self) -> None:
        trial = self.trial()
        for label, raw_result in (
            ("trial-object", trial),
            ("raw-dict", {"passed": True}),
            ("boolean", True),
        ):
            decision = self.decide(
                trial,
                verifier=lambda *_args, value=raw_result: value,
            )
            with self.subTest(label=label):
                self.assertEqual(decision.action, "rollback")
                self.assertIsNone(decision.retained_surface)
                self.assertIn(
                    "trial-artifact-verification-failed", decision.reasons
                )

        other_table = alias_table({"predicate:task.verify": "別"})
        unactivated = self.decide(
            trial,
            active=active_surface(other_table),
            verifier=self.trusted_trial_verifier(trial),
        )
        self.assertEqual(unactivated.action, "rollback")
        self.assertIsNone(unactivated.retained_surface)
        self.assertIn("surface-not-activated-for-trial", unactivated.reasons)

        for label, forged in (
            (
                "result",
                replace(trial, result_sha256="sha256:" + "e" * 64),
            ),
            (
                "transcript",
                replace(trial, transcript_sha256="sha256:" + "f" * 64),
            ),
        ):
            forged_decision = self.decide(
                forged,
                verifier=self.trusted_trial_verifier(trial),
            )
            with self.subTest(label=label):
                self.assertEqual(forged_decision.action, "rollback")
                self.assertIsNone(forged_decision.retained_surface)
                self.assertIn(
                    "trial-artifact-verification-failed",
                    forged_decision.reasons,
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
