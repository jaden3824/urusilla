from __future__ import annotations

import copy
import json
from dataclasses import fields, replace
from pathlib import Path
from unittest import TestCase, mock

from urusilla_hybrid_runtime import (
    ACTION_STATE_FORMAT,
    ActionStateError,
    Capsule,
    CapsuleContextBinding,
    CapsuleError,
    CostForecast,
    FidelityVerification,
    FidelityVerificationInput,
    LocalArtifactVerification,
    LocalOutputValidation,
    ModelReply,
    ObservedLocalUsage,
    OutputValidationInput,
    PublicActionState,
    PublicTaskContext,
    ReceiverCapabilities,
    ReceiverError,
    ReceiverModelReply,
    RouterPolicy,
    RoutingError,
    RoutineInvocation,
    SenderError,
    SenderContextVerification,
    SilenceProof,
    UtilityEvidence,
    action_state_preflight,
    build_action_state_request,
    build_json_fallback_payload,
    build_json_request,
    build_raw_request,
    build_sender_prompt,
    canonical_json,
    compile_natural_language,
    consume_direct_action_state,
    current_runtime_sha256,
    execute_prepared_message,
    load_capsule,
    parse_sender_output,
    plan_route,
    prepare_message,
    source_text_sha256,
    strict_json_loads,
    wrap_as_quarantined_urusilla_message,
)


def char_count(text: str) -> int:
    return len(text)


CAPSULE_COMPREHENSION_EVIDENCE = "sha256:" + "c" * 64
CAPSULE_COMPREHENSION_VERIFIER = "sha256:" + "d" * 64
TASK_COMPREHENSION_EVIDENCE = "sha256:" + "e" * 64
TASK_COMPREHENSION_VERIFIER = "sha256:" + "f" * 64
OUTPUT_VALIDATOR = "sha256:" + "7" * 64
SENDER_CONTEXT_VERIFIER = "sha256:" + "6" * 64
FIDELITY_VERIFIER = "sha256:" + "4" * 64
FIDELITY_TOKENS = 3
ROUTINE_DEFINITION_TEXT = canonical_json(
    {
        "description": "Repeat one session-local effect-free status check.",
        "routine_id": "status-check",
    }
)
ROUTINE_DIGEST = source_text_sha256(ROUTINE_DEFINITION_TEXT)


def public_task_context() -> PublicTaskContext:
    def positional_argument(name: str, meaning: str) -> dict[str, object]:
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
            "task_id": "task.verify-artifact",
            "objective": "Verify a bounded artifact and report test status without effects.",
            "output_contract": {
                "media_type": "text/plain",
                "validator_sha256": OUTPUT_VALIDATOR,
                "description": "Return a locally validated bounded status string.",
            },
            "allowed_acts": ["resolve", "assert"],
            "outcome_contract": {
                "statuses": ["failed"],
                "value": {
                    "name": "value",
                    "type": "string",
                    "nullable": True,
                    "required": True,
                    "unit": None,
                    "meaning": "Bounded public result value, or null when unavailable.",
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
                    "The named artifact is the verification target.",
                    [
                        positional_argument(
                            "artifact_id", "Stable public artifact identifier."
                        )
                    ],
                ),
                predicate(
                    "test.passed",
                    "The named test unit passed when this atom is not negated.",
                    [
                        positional_argument(
                            "test_unit", "Stable public test-unit identifier."
                        )
                    ],
                ),
                predicate(
                    "test.failure-log",
                    "A bounded test failure log is required.",
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


TASK_CONTEXT = public_task_context()


def complete_forecasts(**overrides: CostForecast) -> dict[str, CostForecast]:
    result = {
        mode: CostForecast(complete=True)
        for mode in ("silence", "raw", "json")
    }
    result["routine"] = CostForecast(routine_setup_tokens=0, complete=True)
    result["action-state"] = CostForecast(
        cached_context_tokens=1,
        comprehension_setup_tokens=0,
        receiver_payload_token_ceiling=2_000,
        complete=True,
    )
    result.update(overrides)
    return result


def action_policy(**overrides: object) -> RouterPolicy:
    values: dict[str, object] = {
        "compiler_token_ceiling": 100,
        "fidelity_verifier_sha256": FIDELITY_VERIFIER,
        "fidelity_verifier_token_ceiling": 20,
        "receiver_total_token_ceiling": 10_000,
    }
    values.update(overrides)
    return RouterPolicy(**values)


def fidelity_verification(
    item: FidelityVerificationInput,
    *,
    passed: bool = True,
    input_binding_sha256: str | None = None,
    verifier_sha256: str = FIDELITY_VERIFIER,
    independent_of_compiler: bool = True,
    total_tokens: int | None = FIDELITY_TOKENS,
    model_id: str = "independent-fidelity-model-a",
) -> FidelityVerification:
    return FidelityVerification(
        passed=passed,
        input_binding_sha256=(
            input_binding_sha256 or item.binding_sha256
        ),
        verifier_sha256=verifier_sha256,
        method="independent-model",
        independent_of_compiler=independent_of_compiler,
        model_calls=1,
        model_id=model_id,
        total_tokens=total_tokens,
        usage_complete=total_tokens is not None,
    )


def verify_fidelity(item: FidelityVerificationInput) -> FidelityVerification:
    return fidelity_verification(item)


def fidelity_for(
    source_text: str,
    state: PublicActionState,
    *,
    task_context: PublicTaskContext = TASK_CONTEXT,
    maximum_total_tokens: int = 20,
    **overrides: object,
) -> FidelityVerification:
    item = FidelityVerificationInput(
        source_text=source_text,
        source_sha256=source_text_sha256(source_text),
        state=state,
        task_context=task_context,
        maximum_total_tokens=maximum_total_tokens,
    )
    return fidelity_verification(item, **overrides)


def passing_evidence(
    identifier: str = "independent-frozen-evidence",
    *,
    route_mode: str = "action-state",
    capsule_sha256: str | None = None,
    task_context: PublicTaskContext = TASK_CONTEXT,
) -> UtilityEvidence:
    capsule_digest = capsule_sha256 or load_capsule().sha256
    return UtilityEvidence(
        evidence_id=identifier,
        route_mode=route_mode,
        capsule_sha256=capsule_digest,
        task_profile_sha256=task_context.task_profile_sha256,
        symbol_table_sha256=task_context.symbol_table_sha256,
        runtime_sha256=current_runtime_sha256(),
        plan_sha256="sha256:" + "9" * 64,
        result_sha256="sha256:" + "a" * 64,
        verifier_sha256="sha256:" + "b" * 64,
        verifier_passed=True,
        frozen_before_execution=True,
        measurement_scope_complete=True,
        unseen_tasks=True,
        unseen_partner=True,
        domain_count=3,
        model_family_count=2,
        independent_operator_count=2,
        project_operated_only=False,
        parse_validity=0.99,
        semantic_fidelity=0.95,
        task_success_difference_lcb=-0.01,
        total_token_reduction_lcb=0.20,
        negative_rejection=0.999,
        unauthorized_external_effects=0,
    )


def action_receiver(
    capsule_sha256: str,
    *,
    cached: bool = True,
    task_context: PublicTaskContext = TASK_CONTEXT,
) -> ReceiverCapabilities:
    return ReceiverCapabilities(
        supports_raw=True,
        supports_json=True,
        supports_direct_action_state=True,
        accepts_declarative_capsule=True,
        capsule_comprehension_passed=True,
        capsule_cached_in_same_model_context=cached,
        capsule_sha256=capsule_sha256,
        capsule_context_id="ctx-action-1" if cached else None,
        capsule_comprehension_sha256=CAPSULE_COMPREHENSION_EVIDENCE,
        capsule_comprehension_verifier_sha256=CAPSULE_COMPREHENSION_VERIFIER,
        accepts_public_task_context=True,
        task_context_comprehension_passed=True,
        task_context_cached_in_same_model_context=False,
        task_context_sha256=task_context.sha256,
        task_profile_sha256=task_context.task_profile_sha256,
        symbol_table_sha256=task_context.symbol_table_sha256,
        task_context_comprehension_sha256=TASK_COMPREHENSION_EVIDENCE,
        task_context_comprehension_verifier_sha256=TASK_COMPREHENSION_VERIFIER,
    )


def verify_utility(
    evidence: UtilityEvidence,
    mode: str,
    capsule_sha256: str,
    task_profile_sha256: str,
    symbol_table_sha256: str,
    runtime_sha256: str,
) -> LocalArtifactVerification:
    passed = (
        evidence.verifier_passed
        and evidence.route_mode == mode
        and evidence.capsule_sha256 == capsule_sha256
        and evidence.task_profile_sha256 == task_profile_sha256
        and evidence.symbol_table_sha256 == symbol_table_sha256
        and evidence.runtime_sha256 == runtime_sha256
    )
    return LocalArtifactVerification(
        passed=passed,
        verifier_sha256=evidence.verifier_sha256,
        input_binding_sha256=evidence.binding_sha256,
    )


def verify_comprehension(
    receiver: ReceiverCapabilities, capsule: Capsule
) -> LocalArtifactVerification:
    return LocalArtifactVerification(
        passed=(
            receiver.capsule_sha256 == capsule.sha256
            and receiver.capsule_comprehension_sha256
            == CAPSULE_COMPREHENSION_EVIDENCE
        ),
        verifier_sha256=CAPSULE_COMPREHENSION_VERIFIER,
    )


def verify_task_context(
    receiver: ReceiverCapabilities, task_context: PublicTaskContext
) -> LocalArtifactVerification:
    return LocalArtifactVerification(
        passed=(
            receiver.task_context_sha256 == task_context.sha256
            and receiver.task_profile_sha256 == task_context.task_profile_sha256
            and receiver.symbol_table_sha256 == task_context.symbol_table_sha256
            and receiver.task_context_comprehension_sha256
            == TASK_COMPREHENSION_EVIDENCE
        ),
        verifier_sha256=TASK_COMPREHENSION_VERIFIER,
    )


def verify_bound_artifact(
    artifact: SilenceProof | RoutineInvocation,
) -> LocalArtifactVerification:
    return LocalArtifactVerification(
        passed=True,
        verifier_sha256=artifact.verifier_sha256,
        input_binding_sha256=artifact.binding_sha256,
    )


def validate_output(item: OutputValidationInput) -> LocalOutputValidation:
    return LocalOutputValidation(
        valid=item.output_text == "valid",
        input_binding_sha256=item.binding_sha256,
        validator_sha256=TASK_CONTEXT.output_validator_sha256,
    )


def sender_output(state: PublicActionState, *, status: str = "ok") -> str:
    if status == "ok":
        value = {
            "status": "ok",
            "candidates": [state.to_object()],
            "unsupported": [],
            "failure": None,
        }
    elif status == "ambiguous":
        second = state.to_object()
        second["act"] = "assert"
        value = {
            "status": "ambiguous",
            "candidates": [state.to_object(), second],
            "unsupported": [],
            "failure": None,
        }
    elif status == "unsupported":
        value = {
            "status": "unsupported",
            "candidates": [],
            "unsupported": ["unrepresentable modal scope"],
            "failure": None,
        }
    else:
        value = {
            "status": "failed",
            "candidates": [],
            "unsupported": [],
            "failure": "compiler failed safely",
        }
    return canonical_json(value)


class FakeCompiler:
    def __init__(self, reply: ModelReply | Exception):
        self.reply = reply
        self.calls = 0
        self.prompts = []

    def complete(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeReceiverAdapter:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.requests = []

    def complete(self, request):
        self.calls += 1
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def receiver_reply(text: str = "valid") -> ReceiverModelReply:
    return ReceiverModelReply(
        text=text,
        model_id="receiver-a",
        input_tokens=3,
        output_tokens=2,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=5,
    )


class CapsuleAndRecordTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.example = self.capsule.to_object()["examples"]["positive"]

    def test_capsule_is_declarative_unpromoted_and_grants_no_authority(self) -> None:
        value = self.capsule.to_object()
        self.assertEqual(value["status"], "development-only-unpromoted")
        self.assertEqual(value["protocol_language_version"], "0.1.0")
        self.assertFalse(value["authority_boundary"]["executable_code"])
        self.assertTrue(all(item is False for item in value["authority_boundary"].values()))
        self.assertTrue(self.capsule.sha256.startswith("sha256:"))

    def test_example_preserves_explicit_negation_null_failure_and_uncertainty(self) -> None:
        state = PublicActionState.from_object(self.example)
        recovered = state.to_object()
        self.assertTrue(recovered["state"][0]["n"])
        self.assertEqual(recovered["outcome"]["status"], "failed")
        self.assertIsNone(recovered["outcome"]["value"])
        self.assertIsNone(recovered["uncertainty"][0]["confidence_ppm"])
        self.assertTrue(state.preserves_negative_or_null)
        self.assertEqual(PublicActionState.from_json(state.canonical_text), state)

    def test_unknown_fields_and_unknown_statuses_fail_closed(self) -> None:
        for mutation in ("field", "outcome", "act"):
            value = copy.deepcopy(self.example)
            if mutation == "field":
                value["surprise"] = True
            elif mutation == "outcome":
                value["outcome"]["status"] = "mostly-worked"
            else:
                value["act"] = "commit"
            with self.subTest(mutation=mutation), self.assertRaises(ActionStateError):
                PublicActionState.from_object(value)

    def test_act_specific_required_meaning_is_enforced(self) -> None:
        cases = []
        request = copy.deepcopy(self.example)
        request.update({"act": "request", "goal": None})
        cases.append(request)
        query = copy.deepcopy(self.example)
        query.update({"act": "query", "needs": []})
        cases.append(query)
        proposal = copy.deepcopy(self.example)
        proposal.update({"act": "propose", "action": None})
        cases.append(proposal)
        resolution = copy.deepcopy(self.example)
        resolution.update({"act": "resolve", "outcome": None})
        cases.append(resolution)
        refusal = copy.deepcopy(self.example)
        refusal["act"] = "refuse"
        refusal["outcome"]["status"] = "succeeded"
        cases.append(refusal)
        for index, value in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ActionStateError):
                PublicActionState.from_object(value)

    def test_strict_json_rejects_duplicates_and_nonfinite_values(self) -> None:
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                strict_json_loads(text)

    def test_quarantined_wrapper_cannot_become_an_effectful_act(self) -> None:
        state = PublicActionState.from_object(self.example)
        wrapped = wrap_as_quarantined_urusilla_message(
            state,
            message_id="00000000-0000-0000-0000-000000000001",
            session_id="00000000-0000-0000-0000-000000000002",
            sender="urn:agent:a",
            recipient="urn:agent:b",
            logical_clock=1,
        )
        self.assertEqual(wrapped["act"], "ASSERT")
        self.assertFalse(wrapped["meta"]["x:effect-authorized"])
        self.assertEqual(wrapped["body"]["record"]["format"], ACTION_STATE_FORMAT)

    def test_capsule_tamper_fails_but_noncanonical_source_order_is_accepted(self) -> None:
        value = self.capsule.to_object()
        reordered_value = {key: value[key] for key in reversed(tuple(value))}
        reordered = json.dumps(
            reordered_value, ensure_ascii=False, indent=2, sort_keys=False
        )
        with mock.patch.object(Path, "read_text", return_value=reordered):
            recovered = load_capsule(Path("reordered-capsule.json"))
        self.assertEqual(recovered.sha256, self.capsule.sha256)

        tampered = copy.deepcopy(value)
        tampered["purpose"] += " Tampered."
        with mock.patch.object(
            Path, "read_text", return_value=canonical_json(tampered)
        ), self.assertRaises(CapsuleError):
            load_capsule(Path("tampered-capsule.json"))

    def test_direct_forged_state_is_rejected(self) -> None:
        with self.assertRaises(ActionStateError):
            PublicActionState("{}", "sha256:" + "0" * 64)

    def test_null_false_zero_and_empty_string_remain_distinct(self) -> None:
        states = []
        for value in (None, False, 0, ""):
            candidate = copy.deepcopy(self.example)
            candidate["outcome"]["value"] = value
            states.append(PublicActionState.from_object(candidate))
        self.assertEqual(len({state.sha256 for state in states}), 4)
        self.assertEqual(
            [state.to_object()["outcome"]["value"] for state in states],
            [None, False, 0, ""],
        )

        unspecified = copy.deepcopy(self.example)
        zero = copy.deepcopy(self.example)
        zero["uncertainty"][0]["confidence_ppm"] = 0
        self.assertNotEqual(
            PublicActionState.from_object(unspecified).sha256,
            PublicActionState.from_object(zero).sha256,
        )

    def test_canonical_action_state_rejects_floating_point_values(self) -> None:
        value = copy.deepcopy(self.example)
        value["goal"]["a"] = [1.0]
        with self.assertRaises(ValueError):
            PublicActionState.from_object(value)

    def test_task_context_grants_no_authority_and_binds_all_public_semantics(self) -> None:
        value = TASK_CONTEXT.to_object()
        self.assertTrue(all(item is False for item in value["authority_boundary"].values()))
        self.assertEqual(value["allowed_acts"], ["resolve", "assert"])
        self.assertEqual(value["outcome_contract"]["statuses"], ["failed"])
        self.assertEqual(
            value["uncertainty_contract"]["targets"], ["failure.cause"]
        )
        self.assertEqual(TASK_CONTEXT.output_validator_sha256, OUTPUT_VALIDATOR)


class SenderTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.state = PublicActionState.from_object(
            self.capsule.to_object()["examples"]["positive"]
        )

    def test_prompt_includes_capsule_on_cold_call_and_digest_only_when_cached(self) -> None:
        cold = build_sender_prompt(
            "The check failed.", self.capsule, task_context=TASK_CONTEXT
        )
        binding = CapsuleContextBinding(
            capsule_sha256=self.capsule.sha256,
            task_context_sha256=TASK_CONTEXT.sha256,
            task_profile_sha256=TASK_CONTEXT.task_profile_sha256,
            symbol_table_sha256=TASK_CONTEXT.symbol_table_sha256,
            context_id="sender-context-1",
            capsule_comprehension_evidence_sha256=(
                CAPSULE_COMPREHENSION_EVIDENCE
            ),
            task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
            verifier_sha256=SENDER_CONTEXT_VERIFIER,
        )
        warm = build_sender_prompt(
            "The check failed.",
            self.capsule,
            task_context=TASK_CONTEXT,
            capsule_context=binding,
            context_verification=SenderContextVerification(
                passed=True,
                binding_sha256=binding.binding_sha256,
                verifier_sha256=SENDER_CONTEXT_VERIFIER,
            ),
        )
        self.assertTrue(cold.capsule_included)
        self.assertIn(self.capsule.canonical_text, cold.system_text)
        self.assertFalse(warm.capsule_included)
        self.assertNotIn(self.capsule.canonical_text, warm.system_text)
        self.assertIn(self.capsule.sha256, warm.system_text)
        self.assertEqual(warm.capsule_context_id, "sender-context-1")

    def test_all_four_sender_dispositions_are_strictly_parseable(self) -> None:
        expected_counts = {"ok": 1, "ambiguous": 2, "unsupported": 0, "failed": 0}
        for status, count in expected_counts.items():
            observed, candidates, unsupported, failure = parse_sender_output(
                sender_output(self.state, status=status)
            )
            self.assertEqual(observed, status)
            self.assertEqual(len(candidates), count)
            self.assertEqual(bool(unsupported), status == "unsupported")
            self.assertEqual(failure is not None, status == "failed")

    def test_sender_rejects_valid_but_noncanonical_json(self) -> None:
        canonical = sender_output(self.state)
        noncanonical = json.dumps(
            strict_json_loads(canonical),
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        self.assertNotEqual(noncanonical, canonical)
        with self.assertRaises(SenderError):
            parse_sender_output(noncanonical)

    def test_sender_does_not_silently_select_ambiguous_output(self) -> None:
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state, status="ambiguous"), "model-a", 41)
        )
        outcome = compile_natural_language(
            "Ambiguous source",
            self.capsule,
            compiler,
            task_context=TASK_CONTEXT,
        )
        self.assertEqual(outcome.status, "ambiguous")
        self.assertEqual(len(outcome.candidates), 2)
        self.assertIsNone(outcome.compiled)

    def test_invalid_output_and_provider_failure_become_explicit_failure(self) -> None:
        invalid = FakeCompiler(ModelReply("```json\n{}\n```", "model-a", 12))
        invalid_outcome = compile_natural_language(
            "Source", self.capsule, invalid, task_context=TASK_CONTEXT
        )
        self.assertEqual(invalid_outcome.status, "failed")
        self.assertEqual(invalid_outcome.failure, "compiler-output-invalid")
        self.assertEqual(invalid_outcome.total_tokens, 12)

        failed = FakeCompiler(RuntimeError("secret provider detail"))
        failed_outcome = compile_natural_language(
            "Source", self.capsule, failed, task_context=TASK_CONTEXT
        )
        self.assertEqual(failed_outcome.status, "failed")
        self.assertEqual(failed_outcome.failure, "compiler-call-failed")
        self.assertIsNone(failed_outcome.total_tokens)
        self.assertNotIn("secret provider detail", failed_outcome.failure)

    def test_inconsistent_sender_output_is_rejected(self) -> None:
        value = {
            "status": "ok",
            "candidates": [],
            "unsupported": [],
            "failure": None,
        }
        with self.assertRaises(SenderError):
            parse_sender_output(canonical_json(value))

    def test_duplicate_ambiguous_candidates_are_rejected(self) -> None:
        value = {
            "status": "ambiguous",
            "candidates": [self.state.to_object(), self.state.to_object()],
            "unsupported": [],
            "failure": None,
        }
        with self.assertRaises(SenderError):
            parse_sender_output(canonical_json(value))

    def test_invalid_compiler_adapter_reply_type_fails_closed(self) -> None:
        outcome = compile_natural_language(
            "Source",
            self.capsule,
            FakeCompiler("not-a-model-reply"),
            task_context=TASK_CONTEXT,
        )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.failure, "compiler-reply-type-invalid")
        self.assertIsNone(outcome.total_tokens)

    def test_compiler_token_ceiling_is_enforced_and_accounted(self) -> None:
        exceeded = compile_natural_language(
            "Source",
            self.capsule,
            FakeCompiler(ModelReply(sender_output(self.state), "model-a", 11)),
            task_context=TASK_CONTEXT,
            maximum_total_tokens=10,
        )
        self.assertEqual(exceeded.status, "failed")
        self.assertEqual(exceeded.failure, "compiler-token-budget-exceeded")
        self.assertEqual(exceeded.total_tokens, 11)

        unknown = compile_natural_language(
            "Source",
            self.capsule,
            FakeCompiler(ModelReply(sender_output(self.state), "model-a", None)),
            task_context=TASK_CONTEXT,
            maximum_total_tokens=10,
        )
        self.assertEqual(unknown.failure, "compiler-token-budget-unverified")
        self.assertIsNone(unknown.total_tokens)

    def test_capsule_context_rejects_newline_injection(self) -> None:
        with self.assertRaises(SenderError):
            CapsuleContextBinding(
                capsule_sha256=self.capsule.sha256,
                task_context_sha256=TASK_CONTEXT.sha256,
                task_profile_sha256=TASK_CONTEXT.task_profile_sha256,
                symbol_table_sha256=TASK_CONTEXT.symbol_table_sha256,
                context_id="context\nforged",
                capsule_comprehension_evidence_sha256=(
                    CAPSULE_COMPREHENSION_EVIDENCE
                ),
                task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
                verifier_sha256=SENDER_CONTEXT_VERIFIER,
            )

    def test_failed_cached_context_proof_forces_cold_capsule_and_task_input(self) -> None:
        binding = CapsuleContextBinding(
            capsule_sha256=self.capsule.sha256,
            task_context_sha256=TASK_CONTEXT.sha256,
            task_profile_sha256=TASK_CONTEXT.task_profile_sha256,
            symbol_table_sha256=TASK_CONTEXT.symbol_table_sha256,
            context_id="sender-context-1",
            capsule_comprehension_evidence_sha256=(
                CAPSULE_COMPREHENSION_EVIDENCE
            ),
            task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
            verifier_sha256=SENDER_CONTEXT_VERIFIER,
        )
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "model-a", 10)
        )

        outcome = compile_natural_language(
            "The check failed.",
            self.capsule,
            compiler,
            task_context=TASK_CONTEXT,
            capsule_context=binding,
            capsule_context_verifier=lambda *_: SenderContextVerification(
                passed=False,
                binding_sha256=binding.binding_sha256,
                verifier_sha256=SENDER_CONTEXT_VERIFIER,
            ),
        )

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(compiler.calls, 1)
        prompt = compiler.prompts[0]
        self.assertTrue(prompt.capsule_included)
        self.assertTrue(prompt.task_context_included)
        self.assertIsNone(prompt.capsule_context_id)
        self.assertIn(self.capsule.canonical_text, prompt.model_visible_text)
        self.assertIn(TASK_CONTEXT.canonical_text, prompt.model_visible_text)


class ReceiverTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.state = PublicActionState.from_object(
            self.capsule.to_object()["examples"]["positive"]
        )

    def test_direct_receiver_uses_exact_payload_without_prose_expansion(self) -> None:
        request = build_action_state_request(
            self.state,
            self.capsule,
            TASK_CONTEXT,
            task_context_cached_in_same_model_context=False,
            task_context_id=None,
            task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
            task_comprehension_verifier_sha256=TASK_COMPREHENSION_VERIFIER,
            capsule_cached_in_same_model_context=False,
            capsule_context_id=None,
            comprehension_evidence_sha256=CAPSULE_COMPREHENSION_EVIDENCE,
            capsule_comprehension_verifier_sha256=(
                CAPSULE_COMPREHENSION_VERIFIER
            ),
        )
        self.assertEqual(request.payload_text, self.state.canonical_text)
        self.assertIsNone(request.natural_language_expansion)
        self.assertFalse(request.decode_before_model)
        self.assertFalse(request.external_effects_authorized)
        self.assertEqual(request.tools, ())
        with mock.patch("urusilla.translate_message", side_effect=AssertionError, create=True):
            recovered = consume_direct_action_state(request)
        self.assertEqual(recovered, self.state)

    def test_cached_receiver_omits_capsule_but_retains_digest_binding(self) -> None:
        request = build_action_state_request(
            self.state,
            self.capsule,
            TASK_CONTEXT,
            task_context_cached_in_same_model_context=False,
            task_context_id=None,
            task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
            task_comprehension_verifier_sha256=TASK_COMPREHENSION_VERIFIER,
            capsule_cached_in_same_model_context=True,
            capsule_context_id="ctx-action-1",
            comprehension_evidence_sha256=CAPSULE_COMPREHENSION_EVIDENCE,
            capsule_comprehension_verifier_sha256=(
                CAPSULE_COMPREHENSION_VERIFIER
            ),
        )
        self.assertIsNone(request.capsule_text)
        self.assertFalse(request.capsule_included)
        self.assertEqual(request.capsule_sha256, self.capsule.sha256)
        self.assertEqual(request.capsule_context_id, "ctx-action-1")

    def test_failed_receiver_task_cache_proof_forces_cold_task_context(self) -> None:
        receiver = ReceiverCapabilities(
            accepts_public_task_context=True,
            task_context_comprehension_passed=True,
            task_context_cached_in_same_model_context=True,
            task_context_sha256=TASK_CONTEXT.sha256,
            task_profile_sha256=TASK_CONTEXT.task_profile_sha256,
            symbol_table_sha256=TASK_CONTEXT.symbol_table_sha256,
            task_context_id="ctx-task-1",
            task_context_comprehension_sha256=TASK_COMPREHENSION_EVIDENCE,
            task_context_comprehension_verifier_sha256=(
                TASK_COMPREHENSION_VERIFIER
            ),
        )
        decision = plan_route(
            "exact source",
            self.capsule,
            receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            task_context_comprehension_verifier=lambda *_: (
                LocalArtifactVerification(
                    passed=False,
                    verifier_sha256=TASK_COMPREHENSION_VERIFIER,
                )
            ),
        )
        self.assertTrue(decision.request.task_context_included)
        self.assertIsNone(decision.request.task_context_id)
        self.assertIn(TASK_CONTEXT.canonical_text, decision.request.model_visible_text)

    def test_json_fallback_is_lossless_for_text_and_canonical_for_json(self) -> None:
        wrapped, text_wrapped = build_json_fallback_payload("not JSON")
        self.assertTrue(text_wrapped)
        self.assertEqual(strict_json_loads(wrapped), {"raw_text": "not JSON"})
        canonical, text_wrapped = build_json_fallback_payload('{"b":2, "a":null}')
        self.assertFalse(text_wrapped)
        self.assertEqual(canonical, '{"a":null,"b":2}')
        self.assertEqual(
            build_json_request("not JSON", TASK_CONTEXT).payload_text, wrapped
        )
        self.assertEqual(
            build_raw_request("not JSON", TASK_CONTEXT).payload_text, "not JSON"
        )

    def test_forged_receiver_request_is_rejected(self) -> None:
        request = build_raw_request("exact source", TASK_CONTEXT)
        with self.assertRaises(ReceiverError):
            replace(request, payload_sha256="sha256:" + "0" * 64)
        with self.assertRaises(ReceiverError):
            replace(request, natural_language_expansion="expanded prose")
        with self.assertRaises(ReceiverError):
            replace(request, decode_before_model=True)

    def test_cached_receiver_context_rejects_newline_injection(self) -> None:
        with self.assertRaises(RoutingError):
            ReceiverCapabilities(
                supports_direct_action_state=True,
                accepts_declarative_capsule=True,
                capsule_comprehension_passed=True,
                capsule_cached_in_same_model_context=True,
                capsule_sha256=self.capsule.sha256,
                capsule_context_id="ctx\nforged",
                capsule_comprehension_sha256=CAPSULE_COMPREHENSION_EVIDENCE,
                capsule_comprehension_verifier_sha256=(
                    CAPSULE_COMPREHENSION_VERIFIER
                ),
            )

    def test_receiver_reply_rejects_invalid_utf8_text(self) -> None:
        with self.assertRaises(ReceiverError):
            receiver_reply("\ud800")


class EvidenceAndRoutingTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.state = PublicActionState.from_object(
            self.capsule.to_object()["examples"]["positive"]
        )
        self.receiver = action_receiver(self.capsule.sha256)

    def _prepare_action(
        self,
        source: str,
        *,
        fidelity_verifier=verify_fidelity,
        policy: RouterPolicy | None = None,
        state: PublicActionState | None = None,
    ):
        compiler = FakeCompiler(
            ModelReply(sender_output(state or self.state), "model-a", 10)
        )
        prepared = prepare_message(
            source,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compiler=compiler,
            fidelity_verifier=fidelity_verifier,
            policy=policy or action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        return prepared, compiler

    def test_receiver_capsule_claim_must_be_bound_to_exact_digest(self) -> None:
        with self.assertRaises(RoutingError):
            ReceiverCapabilities(
                supports_direct_action_state=True,
                accepts_declarative_capsule=True,
                capsule_comprehension_passed=True,
                capsule_sha256=None,
            )
        wrong = action_receiver("sha256:" + "0" * 64)
        self.assertFalse(
            action_state_preflight(
                wrong,
                self.capsule,
                TASK_CONTEXT,
                passing_evidence(),
                RouterPolicy(),
                capsule_comprehension_verifier=verify_comprehension,
                task_context_comprehension_verifier=verify_task_context,
            )[0]
        )

    def test_declared_thresholds_cannot_issue_the_initial_goal_claim(self) -> None:
        evidence = passing_evidence()
        self.assertTrue(evidence.declared_thresholds_passed)
        self.assertFalse(evidence.passes_initial_goal_gate)
        self.assertIn(
            "route-claim-unavailable-no-authoritative-producer",
            evidence.goal_gate_failures(),
        )
        mutations = {
            "domain_count": 2,
            "model_family_count": 1,
            "independent_operator_count": 1,
            "parse_validity": 0.989999,
            "semantic_fidelity": 0.949999,
            "task_success_difference_lcb": -0.010001,
            "total_token_reduction_lcb": 0.199999,
            "negative_rejection": 0.998999,
            "unauthorized_external_effects": 1,
            "project_operated_only": True,
        }
        for field, value in mutations.items():
            changed = evidence.__class__(
                **{**evidence.__dict__, field: value}
            )
            with self.subTest(field=field):
                self.assertFalse(changed.declared_thresholds_passed)
                self.assertFalse(changed.passes_initial_goal_gate)

    def test_capability_proof_and_evidence_types_are_strict(self) -> None:
        for field in ("supports_json", "session_only", "capsule_comprehension_passed"):
            with self.subTest(capability=field), self.assertRaises(RoutingError):
                ReceiverCapabilities(**{field: "true"})

        evidence = passing_evidence()
        for field, value in (
            ("verifier_passed", 1),
            ("measurement_scope_complete", "true"),
            ("project_operated_only", 0),
            ("parse_validity", True),
            ("semantic_fidelity", "0.95"),
            ("total_token_reduction_lcb", float("nan")),
        ):
            with self.subTest(evidence=field), self.assertRaises(RoutingError):
                evidence.__class__(**{**evidence.__dict__, field: value})

        for evidence_id in ("\ud800", "a" * 257):
            with self.subTest(evidence_id=repr(evidence_id)), self.assertRaises(
                RoutingError
            ):
                replace(evidence, evidence_id=evidence_id)

        with self.assertRaises(RoutingError):
            SilenceProof(
                source_text="strict proof source",
                source_sha256=source_text_sha256("strict proof source"),
                task_context_text=TASK_CONTEXT.canonical_text,
                task_context_sha256=TASK_CONTEXT.sha256,
                verifier_sha256="sha256:" + "2" * 64,
                no_required_message="true",
                no_effectful_intent=True,
            )
        with self.assertRaises(RoutingError):
            RoutineInvocation(
                routine_id="r",
                routine_sha256=ROUTINE_DIGEST,
                routine_definition_text=ROUTINE_DEFINITION_TEXT,
                source_text="strict routine source",
                source_sha256=source_text_sha256("strict routine source"),
                task_context_text=TASK_CONTEXT.canonical_text,
                task_context_sha256=TASK_CONTEXT.sha256,
                verifier_sha256="sha256:" + "5" * 64,
                payload={},
                receiver_acknowledged="true",
                session_local=True,
                effect_free=True,
            )
        with self.assertRaises(RoutingError):
            FidelityVerificationInput(
                source_text="strict fidelity source",
                source_sha256=source_text_sha256("strict fidelity source"),
                state=self.state,
                task_context=TASK_CONTEXT,
                maximum_total_tokens=True,
            )
        with self.assertRaises(RoutingError):
            FidelityVerification(
                passed=1,
                input_binding_sha256="sha256:" + "1" * 64,
                verifier_sha256=FIDELITY_VERIFIER,
                method="independent-model",
                independent_of_compiler=True,
                model_calls=1,
                model_id="independent-fidelity-model-a",
                total_tokens=FIDELITY_TOKENS,
                usage_complete=True,
            )

    def test_evidence_is_bound_to_route_capsule_and_trusted_verifier(self) -> None:
        source = "No reply is required."
        proof = SilenceProof(
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "1" * 64,
            no_required_message=True,
            no_effectful_intent=True,
        )
        cases = (
            (passing_evidence(route_mode="action-state"), verify_utility),
            (
                passing_evidence(
                    route_mode="silence", capsule_sha256="sha256:" + "0" * 64
                ),
                verify_utility,
            ),
            (passing_evidence(route_mode="silence"), lambda *_: False),
        )
        for evidence, verifier in cases:
            decision = plan_route(
                source,
                self.capsule,
                ReceiverCapabilities(),
                char_count,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(),
                evidence={"silence": evidence},
                silence_proof=proof,
                utility_evidence_verifier=verifier,
                silence_verifier=verify_bound_artifact,
            )
            with self.subTest(evidence=evidence.evidence_id, route=evidence.route_mode):
                self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_cached_utility_verification_cannot_bless_inflated_evidence(self) -> None:
        source = "No reply is required."
        proof = SilenceProof(
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "1" * 64,
            no_required_message=True,
            no_effectful_intent=True,
        )
        original = replace(
            passing_evidence(route_mode="silence"),
            domain_count=1,
            model_family_count=1,
            independent_operator_count=1,
            parse_validity=0.50,
            semantic_fidelity=0.50,
            task_success_difference_lcb=-0.50,
            total_token_reduction_lcb=0.0,
            negative_rejection=0.50,
        )
        inflated = replace(
            original,
            domain_count=3,
            model_family_count=2,
            independent_operator_count=2,
            parse_validity=0.99,
            semantic_fidelity=0.95,
            task_success_difference_lcb=-0.01,
            total_token_reduction_lcb=0.20,
            negative_rejection=0.999,
        )
        self.assertFalse(original.declared_thresholds_passed)
        self.assertTrue(inflated.declared_thresholds_passed)
        self.assertFalse(inflated.passes_initial_goal_gate)
        self.assertNotEqual(original.binding_sha256, inflated.binding_sha256)
        for name in (
            "route_mode",
            "capsule_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
            "runtime_sha256",
            "plan_sha256",
            "result_sha256",
            "verifier_sha256",
        ):
            self.assertEqual(getattr(original, name), getattr(inflated, name))

        cached_original_result = LocalArtifactVerification(
            passed=True,
            verifier_sha256=original.verifier_sha256,
            input_binding_sha256=original.binding_sha256,
        )

        def decide(verifier):
            return plan_route(
                source,
                self.capsule,
                ReceiverCapabilities(),
                char_count,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(),
                evidence={"silence": inflated},
                silence_proof=proof,
                utility_evidence_verifier=verifier,
                silence_verifier=verify_bound_artifact,
            )

        replay = decide(lambda *_args: cached_original_result)
        self.assertIn(replay.selected_mode, {"raw", "json"})
        self.assertFalse(replay.claim_eligible)

        exact_but_failed = decide(
            lambda *_args: LocalArtifactVerification(
                passed=False,
                verifier_sha256=inflated.verifier_sha256,
                input_binding_sha256=inflated.binding_sha256,
            )
        )
        self.assertIn(exact_but_failed.selected_mode, {"raw", "json"})
        self.assertFalse(exact_but_failed.claim_eligible)

        freshly_verified = decide(
            lambda *_args: LocalArtifactVerification(
                passed=True,
                verifier_sha256=inflated.verifier_sha256,
                input_binding_sha256=inflated.binding_sha256,
            )
        )
        self.assertEqual(freshly_verified.selected_mode, "silence")
        self.assertFalse(freshly_verified.claim_eligible)
        self.assertFalse(freshly_verified.goal_gate_passed)
        selected = next(
            item
            for item in freshly_verified.candidates
            if item.mode == freshly_verified.selected_mode
        )
        self.assertIn(
            "route-claim-unavailable-no-authoritative-producer",
            selected.reasons,
        )
        with self.assertRaisesRegex(RoutingError, "authoritative route-scoped"):
            replace(selected, claim_eligible=True)

    def test_cross_task_compile_replay_is_rejected_even_with_same_profile(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        outcome = compile_natural_language(
            source,
            self.capsule,
            FakeCompiler(ModelReply(sender_output(self.state), "model-a", 10)),
            task_context=TASK_CONTEXT,
        )
        other_value = TASK_CONTEXT.to_object()
        other_value["task_id"] = "task.verify-artifact-replay-target"
        other_value["objective"] = "Verify a different bounded artifact session."
        other_context = PublicTaskContext.from_object(other_value)
        self.assertNotEqual(other_context.sha256, TASK_CONTEXT.sha256)
        self.assertEqual(
            other_context.task_profile_sha256,
            TASK_CONTEXT.task_profile_sha256,
        )

        decision = plan_route(
            source,
            self.capsule,
            action_receiver(self.capsule.sha256, task_context=other_context),
            char_count,
            task_context=other_context,
            forecasts=complete_forecasts(),
            evidence={
                "action-state": passing_evidence(task_context=other_context)
            },
            compile_outcome=outcome,
            fidelity_verification=fidelity_for(source, self.state),
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        action = next(
            item for item in decision.candidates if item.mode == "action-state"
        )
        self.assertIn("compiler-task-context-digest-mismatch", action.reasons)
        self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_profile_and_symbol_evidence_replay_are_rejected(self) -> None:
        source = "No reply is required."
        variants = []
        profile_value = TASK_CONTEXT.to_object()
        profile_value["output_contract"]["description"] += " Revised."
        variants.append(("profile", PublicTaskContext.from_object(profile_value)))
        schema_value = TASK_CONTEXT.to_object()
        schema_value["symbols"][0]["meaning"] += " Revised."
        variants.append(("schema", PublicTaskContext.from_object(schema_value)))

        for label, task_context in variants:
            proof = SilenceProof(
                source_text=source,
                source_sha256=source_text_sha256(source),
                task_context_text=task_context.canonical_text,
                task_context_sha256=task_context.sha256,
                verifier_sha256="sha256:" + "1" * 64,
                no_required_message=True,
                no_effectful_intent=True,
            )
            decision = plan_route(
                source,
                self.capsule,
                ReceiverCapabilities(),
                char_count,
                task_context=task_context,
                forecasts=complete_forecasts(),
                evidence={
                    "silence": passing_evidence(
                        f"{label}-replay", route_mode="silence"
                    )
                },
                silence_proof=proof,
                utility_evidence_verifier=verify_utility,
                silence_verifier=verify_bound_artifact,
            )
            silence = next(
                item for item in decision.candidates if item.mode == "silence"
            )
            with self.subTest(label=label):
                self.assertIn("goal-evidence-missing", silence.reasons)
                self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_forged_or_replaced_route_decision_is_rejected(self) -> None:
        decision = plan_route(
            "raw source",
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        with self.assertRaises(RoutingError):
            decision.__class__(
                source_sha256=decision.source_sha256,
                capsule_sha256=decision.capsule_sha256,
                fidelity_verifier_token_ceiling=(
                    decision.fidelity_verifier_token_ceiling
                ),
                selected_mode=decision.selected_mode,
                request=decision.request,
                selected_cost=decision.selected_cost,
                candidates=decision.candidates,
                best_baseline_mode=decision.best_baseline_mode,
                best_baseline_tokens=decision.best_baseline_tokens,
                claim_eligible=decision.claim_eligible,
                fallback_from=decision.fallback_from,
                fallback_sender_tokens=decision.fallback_sender_tokens,
                fallback_semantic_verification_tokens=(
                    decision.fallback_semantic_verification_tokens
                ),
                goal_gate_passed=decision.goal_gate_passed,
            )
        with self.assertRaises(RoutingError):
            replace(decision, selected_mode="json")
        with self.assertRaises(RoutingError):
            replace(decision, source_sha256="sha256:" + "0" * 64)

    def test_route_decision_rejects_consistent_raw_payload_and_source_replace(self) -> None:
        decision = plan_route(
            "raw source",
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        forged_source = "bad source"
        forged_request = build_raw_request(forged_source, TASK_CONTEXT)
        forged_candidates = tuple(
            replace(candidate, request=forged_request)
            if candidate.mode == "raw"
            else candidate
            for candidate in decision.candidates
        )
        with self.assertRaises(RoutingError):
            replace(
                decision,
                source_sha256=source_text_sha256(forged_source),
                request=forged_request,
                candidates=forged_candidates,
            )

    def test_action_preflight_requires_fidelity_policy_and_verifier(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        cases = (
            (
                "digest",
                RouterPolicy(
                    compiler_token_ceiling=100,
                    fidelity_verifier_token_ceiling=20,
                    receiver_total_token_ceiling=10_000,
                ),
                "fidelity-verifier-digest-missing",
            ),
            (
                "ceiling",
                RouterPolicy(
                    compiler_token_ceiling=100,
                    fidelity_verifier_sha256=FIDELITY_VERIFIER,
                    receiver_total_token_ceiling=10_000,
                ),
                "fidelity-verifier-token-ceiling-missing",
            ),
        )
        for label, policy, expected_reason in cases:
            with self.subTest(label=label):
                prepared, compiler = self._prepare_action(source, policy=policy)
                action = next(
                    item
                    for item in prepared.route.candidates
                    if item.mode == "action-state"
                )
                self.assertEqual(compiler.calls, 0)
                self.assertIn(expected_reason, action.reasons)
                self.assertIn(prepared.route.selected_mode, {"raw", "json"})

        prepared, compiler = self._prepare_action(
            source, fidelity_verifier=None
        )
        action = next(
            item for item in prepared.route.candidates if item.mode == "action-state"
        )
        self.assertEqual(compiler.calls, 0)
        self.assertIsNone(prepared.compilation)
        self.assertIn("compiler-not-run", action.reasons)
        self.assertIn(prepared.route.selected_mode, {"raw", "json"})

    def test_exact_independent_fidelity_binding_selects_and_charges_action(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        observed: list[FidelityVerificationInput] = []

        def verifier(item: FidelityVerificationInput) -> FidelityVerification:
            observed.append(item)
            return fidelity_verification(item)

        prepared, compiler = self._prepare_action(
            source, fidelity_verifier=verifier
        )
        self.assertEqual(compiler.calls, 1)
        self.assertEqual(len(observed), 1)
        fidelity_input = observed[0]
        self.assertEqual(fidelity_input.source_text, source)
        self.assertEqual(fidelity_input.source_sha256, source_text_sha256(source))
        self.assertEqual(fidelity_input.state, self.state)
        self.assertEqual(fidelity_input.task_context, TASK_CONTEXT)
        self.assertEqual(fidelity_input.maximum_total_tokens, 20)
        self.assertEqual(prepared.route.selected_mode, "action-state")
        self.assertIsNotNone(prepared.fidelity_verification)
        assert prepared.fidelity_verification is not None
        self.assertTrue(prepared.fidelity_verification.passed)
        self.assertTrue(prepared.fidelity_verification.independent_of_compiler)
        self.assertEqual(
            prepared.fidelity_verification.input_binding_sha256,
            fidelity_input.binding_sha256,
        )
        self.assertEqual(prepared.route.selected_cost.sender_tokens, 10)
        self.assertEqual(
            prepared.route.selected_cost.semantic_verification_tokens,
            FIDELITY_TOKENS,
        )
        self.assertTrue(prepared.route.selected_cost.complete)

    def test_source_irrelevant_schema_valid_compilation_falls_back(self) -> None:
        source = "Summarize a weather report unrelated to artifact seven. " * 800

        def reject_irrelevant(
            item: FidelityVerificationInput,
        ) -> FidelityVerification:
            return fidelity_verification(item, passed=False)

        prepared, compiler = self._prepare_action(
            source, fidelity_verifier=reject_irrelevant
        )
        action = next(
            item for item in prepared.route.candidates if item.mode == "action-state"
        )
        self.assertEqual(compiler.calls, 1)
        self.assertIsNotNone(prepared.compilation)
        assert prepared.compilation is not None
        self.assertEqual(prepared.compilation.status, "ok")
        self.assertEqual(prepared.compilation.compiled, self.state)
        self.assertIn("per-message-semantic-fidelity-failed", action.reasons)
        self.assertIn(prepared.route.selected_mode, {"raw", "json"})
        self.assertEqual(prepared.route.fallback_from, "action-state:ok")
        self.assertEqual(prepared.route.fallback_sender_tokens, 10)
        self.assertEqual(
            prepared.route.fallback_semantic_verification_tokens,
            FIDELITY_TOKENS,
        )
        self.assertEqual(
            prepared.route.selected_cost.semantic_verification_tokens,
            FIDELITY_TOKENS,
        )
        self.assertTrue(prepared.route.selected_cost.complete)

    def test_compiler_and_fidelity_model_identity_forces_fallback(self) -> None:
        source = "Verify artifact seven without external effects. " * 800

        def same_model_verifier(
            item: FidelityVerificationInput,
        ) -> FidelityVerification:
            return fidelity_verification(item, model_id="model-a")

        prepared, compiler = self._prepare_action(
            source, fidelity_verifier=same_model_verifier
        )
        action = next(
            item for item in prepared.route.candidates if item.mode == "action-state"
        )
        self.assertEqual(compiler.calls, 1)
        self.assertIn("compiler-and-fidelity-model-identical", action.reasons)
        self.assertIn(prepared.route.selected_mode, {"raw", "json"})
        self.assertEqual(prepared.route.fallback_from, "action-state:ok")
        self.assertEqual(
            prepared.route.fallback_semantic_verification_tokens,
            FIDELITY_TOKENS,
        )
        self.assertTrue(prepared.route.selected_cost.complete)

    def test_fidelity_mismatch_failure_budget_and_replay_force_fallback(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        replay = fidelity_for(
            "Verify artifact seven in a different exact source.", self.state
        )
        cases = (
            (
                "binding-mismatch",
                lambda item: fidelity_verification(
                    item, input_binding_sha256="sha256:" + "0" * 64
                ),
                "per-message-fidelity-binding-mismatch",
                FIDELITY_TOKENS,
            ),
            (
                "verifier-mismatch",
                lambda item: fidelity_verification(
                    item, verifier_sha256="sha256:" + "5" * 64
                ),
                "per-message-fidelity-verifier-mismatch",
                FIDELITY_TOKENS,
            ),
            (
                "failed",
                lambda item: fidelity_verification(item, passed=False),
                "per-message-semantic-fidelity-failed",
                FIDELITY_TOKENS,
            ),
            (
                "not-independent",
                lambda item: fidelity_verification(
                    item, passed=False, independent_of_compiler=False
                ),
                "fidelity-verifier-not-independent",
                FIDELITY_TOKENS,
            ),
            (
                "over-budget",
                lambda item: fidelity_verification(item, total_tokens=21),
                "fidelity-verifier-token-ceiling-exceeded",
                21,
            ),
            (
                "cross-source-replay",
                lambda _item: replay,
                "per-message-fidelity-binding-mismatch",
                FIDELITY_TOKENS,
            ),
        )
        for label, verifier, expected_reason, expected_tokens in cases:
            with self.subTest(label=label):
                prepared, compiler = self._prepare_action(
                    source, fidelity_verifier=verifier
                )
                action = next(
                    item
                    for item in prepared.route.candidates
                    if item.mode == "action-state"
                )
                self.assertEqual(compiler.calls, 1)
                self.assertIn(expected_reason, action.reasons)
                self.assertIn(prepared.route.selected_mode, {"raw", "json"})
                self.assertEqual(prepared.route.fallback_from, "action-state:ok")
                self.assertEqual(
                    prepared.route.fallback_semantic_verification_tokens,
                    expected_tokens,
                )
                self.assertEqual(
                    prepared.route.selected_cost.semantic_verification_tokens,
                    expected_tokens,
                )
                self.assertTrue(prepared.route.selected_cost.complete)

    def test_unknown_fidelity_usage_forces_incomplete_fallback_cost(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        for label, verifier in (
            ("invalid-type", lambda _item: object()),
            ("adapter-error", lambda _item: (_ for _ in ()).throw(RuntimeError())),
        ):
            with self.subTest(label=label):
                prepared, compiler = self._prepare_action(
                    source, fidelity_verifier=verifier
                )
                action = next(
                    item
                    for item in prepared.route.candidates
                    if item.mode == "action-state"
                )
                self.assertEqual(compiler.calls, 1)
                self.assertIn(
                    "fidelity-verifier-token-usage-unknown", action.reasons
                )
                self.assertIn(prepared.route.selected_mode, {"raw", "json"})
                self.assertIsNone(
                    prepared.route.fallback_semantic_verification_tokens
                )
                self.assertEqual(
                    prepared.route.selected_cost.semantic_verification_tokens,
                    0,
                )
                self.assertFalse(prepared.route.selected_cost.complete)

    def test_prepared_message_rejects_cross_source_compilation_and_fidelity_pairing(self) -> None:
        first, _ = self._prepare_action(
            "Verify artifact seven in source alpha. " * 800
        )
        second, _ = self._prepare_action(
            "Verify artifact seven in source beta. " * 800
        )
        self.assertEqual(first.route.selected_mode, "action-state")
        self.assertEqual(second.route.selected_mode, "action-state")
        self.assertNotEqual(
            first.fidelity_verification, second.fidelity_verification
        )
        with self.assertRaises(ValueError):
            replace(first, compilation=second.compilation)
        with self.assertRaises(ValueError):
            replace(
                first,
                fidelity_verification=second.fidelity_verification,
            )
        with self.assertRaises(ValueError):
            replace(
                first,
                compilation=second.compilation,
                fidelity_verification=second.fidelity_verification,
            )

    def test_unknown_action_state_symbol_forces_lossless_fallback(self) -> None:
        source = "Verify the proprietary condition. " * 1000
        value = self.state.to_object()
        value["goal"]["p"] = "domain.unseen-proprietary-concept"
        unknown = PublicActionState.from_object(value)
        compiler = FakeCompiler(ModelReply(sender_output(unknown), "model-a", 10))
        prepared = prepare_message(
            source,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        action = next(
            item for item in prepared.route.candidates if item.mode == "action-state"
        )
        self.assertEqual(compiler.calls, 1)
        self.assertIn(prepared.route.selected_mode, {"raw", "json"})
        self.assertIsNotNone(prepared.compilation)
        assert prepared.compilation is not None
        self.assertEqual(prepared.compilation.failure, "compiler-output-invalid")
        self.assertIn("compiler-status-failed", action.reasons)
        if prepared.route.selected_mode == "raw":
            self.assertEqual(prepared.route.request.payload_text, source)
        else:
            self.assertEqual(
                strict_json_loads(prepared.route.request.payload_text),
                {"raw_text": source},
            )

    def test_compiler_requires_complete_conservative_token_ceilings(self) -> None:
        source = "long bounded source " * 1000
        for forecast, policy in (
            (CostForecast(complete=True), action_policy()),
            (
                CostForecast(receiver_payload_token_ceiling=2_000, complete=True),
                RouterPolicy(),
            ),
        ):
            compiler = FakeCompiler(ModelReply(sender_output(self.state), "model-a", 10))
            prepared = prepare_message(
                source,
                self.capsule,
                self.receiver,
                char_count,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(**{"action-state": forecast}),
                evidence={"action-state": passing_evidence()},
                compiler=compiler,
                fidelity_verifier=verify_fidelity,
                policy=policy,
                utility_evidence_verifier=verify_utility,
                capsule_comprehension_verifier=verify_comprehension,
                task_context_comprehension_verifier=verify_task_context,
            )
            with self.subTest(forecast=forecast, policy=policy):
                self.assertEqual(compiler.calls, 0)
                self.assertIn(prepared.route.selected_mode, {"raw", "json"})

        compiler = FakeCompiler(ModelReply(sender_output(self.state), "model-a", 11))
        exceeded = prepare_message(
            source,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(compiler_token_ceiling=10),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        self.assertEqual(compiler.calls, 1)
        self.assertEqual(exceeded.compilation.failure, "compiler-token-budget-exceeded")
        self.assertEqual(exceeded.route.selected_cost.sender_tokens, 11)

    def test_cached_and_comprehension_setup_unknown_make_action_cost_incomplete(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        outcome = compile_natural_language(
            source,
            self.capsule,
            FakeCompiler(ModelReply(sender_output(self.state), "model-a", 10)),
            task_context=TASK_CONTEXT,
        )
        incomplete_forecasts = (
            CostForecast(
                comprehension_setup_tokens=0,
                receiver_payload_token_ceiling=2_000,
                complete=True,
            ),
            CostForecast(
                cached_context_tokens=1,
                receiver_payload_token_ceiling=2_000,
                complete=True,
            ),
        )
        for forecast in incomplete_forecasts:
            decision = plan_route(
                source,
                self.capsule,
                self.receiver,
                char_count,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(
                    **{"action-state": forecast}
                ),
                evidence={"action-state": passing_evidence()},
                compile_outcome=outcome,
                fidelity_verification=fidelity_for(source, self.state),
                policy=action_policy(),
                utility_evidence_verifier=verify_utility,
                capsule_comprehension_verifier=verify_comprehension,
                task_context_comprehension_verifier=verify_task_context,
            )
            action = next(
                item for item in decision.candidates if item.mode == "action-state"
            )
            with self.subTest(forecast=forecast):
                self.assertIsNotNone(action.cost)
                assert action.cost is not None
                self.assertFalse(action.cost.complete)
                self.assertIn("incomplete-cost-forecast", action.reasons)
                self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_unknown_routine_setup_cost_makes_routine_ineligible(self) -> None:
        source = "Repeat the verified read-only status check. " * 500
        digest = ROUTINE_DIGEST
        routine = RoutineInvocation(
            routine_id="status-check",
            routine_sha256=digest,
            routine_definition_text=ROUTINE_DEFINITION_TEXT,
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "5" * 64,
            payload={"artifact": 7},
            receiver_acknowledged=True,
            session_local=True,
            effect_free=True,
        )
        decision = plan_route(
            source,
            self.capsule,
            ReceiverCapabilities(session_routine_sha256=(digest,)),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(
                routine=CostForecast(complete=True)
            ),
            evidence={
                "routine": passing_evidence(
                    "routine-setup-unknown", route_mode="routine"
                )
            },
            routine=routine,
            policy=RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=verify_utility,
            routine_verifier=verify_bound_artifact,
        )
        candidate = next(
            item for item in decision.candidates if item.mode == "routine"
        )
        self.assertIsNotNone(candidate.cost)
        assert candidate.cost is not None
        self.assertFalse(candidate.cost.complete)
        self.assertIn("incomplete-cost-forecast", candidate.reasons)
        self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_unproven_optimized_route_defaults_to_best_raw_json_fallback(self) -> None:
        source = "A novel unsupported request."
        decision = plan_route(
            source,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        self.assertEqual(decision.selected_mode, "raw")
        self.assertFalse(decision.claim_eligible)
        self.assertFalse(decision.goal_gate_passed)
        self.assertIsNone(decision.fallback_from)

    def test_best_baseline_is_selected_between_raw_and_json(self) -> None:
        decision = plan_route(
            "{}",
            self.capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(
                raw=CostForecast(receiver_output_tokens=1000, complete=True),
                json=CostForecast(complete=True),
            ),
        )
        self.assertEqual(decision.best_baseline_mode, "json")
        self.assertEqual(decision.selected_mode, "json")

    def test_action_state_is_compiled_only_after_preflight_and_can_win(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "model-a", 10)
        )
        prepared = prepare_message(
            source,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        self.assertEqual(compiler.calls, 1)
        self.assertEqual(prepared.route.selected_mode, "action-state")
        self.assertFalse(prepared.route.claim_eligible)
        self.assertFalse(prepared.route.goal_gate_passed)
        selected = next(
            item
            for item in prepared.route.candidates
            if item.mode == "action-state"
        )
        self.assertIn(
            "route-claim-unavailable-no-authoritative-producer",
            selected.reasons,
        )
        self.assertEqual(prepared.receiver_model_calls_made, 0)
        self.assertFalse(prepared.external_effects_performed)
        self.assertIn(self.state.canonical_text, prepared.route.request.model_visible_text)

    def test_missing_evidence_prevents_compiler_call_unless_trial_is_explicit(self) -> None:
        compiler = FakeCompiler(ModelReply(sender_output(self.state), "model-a", 10))
        prepared = prepare_message(
            "long source " * 1000,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(),
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        self.assertEqual(compiler.calls, 0)
        self.assertIn(prepared.route.selected_mode, {"raw", "json"})

        trial = prepare_message(
            "long source " * 1000,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(allow_development_trial=True),
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        self.assertEqual(compiler.calls, 1)
        self.assertFalse(trial.route.claim_eligible)

    def test_ambiguous_unsupported_and_invalid_compilation_fall_back_and_charge_sender(self) -> None:
        source = "ambiguous source " * 1000
        for status in ("ambiguous", "unsupported"):
            compiler = FakeCompiler(
                ModelReply(sender_output(self.state, status=status), "model-a", 17)
            )
            prepared = prepare_message(
                source,
                self.capsule,
                self.receiver,
                char_count,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(),
                evidence={"action-state": passing_evidence()},
                compiler=compiler,
                fidelity_verifier=verify_fidelity,
                policy=action_policy(),
                utility_evidence_verifier=verify_utility,
                capsule_comprehension_verifier=verify_comprehension,
                task_context_comprehension_verifier=verify_task_context,
            )
            with self.subTest(status=status):
                self.assertIn(prepared.route.selected_mode, {"raw", "json"})
                self.assertEqual(prepared.route.fallback_from, f"action-state:{status}")
                self.assertEqual(prepared.route.selected_cost.sender_tokens, 17)
                self.assertTrue(prepared.route.selected_cost.complete)

    def test_unknown_compiler_usage_keeps_fallback_total_incomplete(self) -> None:
        compiler = FakeCompiler(ModelReply(sender_output(self.state), "model-a", None))
        prepared = prepare_message(
            "source " * 1000,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        self.assertIn(prepared.route.selected_mode, {"raw", "json"})
        self.assertFalse(prepared.route.selected_cost.complete)
        self.assertEqual(prepared.route.fallback_from, "action-state:failed")

    def test_verified_silence_makes_zero_receiver_calls_and_skips_compiler(self) -> None:
        source = "Already delivered and no reply is required."
        compiler = FakeCompiler(ModelReply(sender_output(self.state), "model-a", 10))
        proof = SilenceProof(
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "1" * 64,
            no_required_message=True,
            no_effectful_intent=True,
        )
        prepared = prepare_message(
            source,
            self.capsule,
            self.receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={
                "silence": passing_evidence(
                    "silence-evidence", route_mode="silence"
                )
            },
            compiler=compiler,
            silence_proof=proof,
            utility_evidence_verifier=verify_utility,
            silence_verifier=verify_bound_artifact,
        )
        self.assertEqual(prepared.route.selected_mode, "silence")
        self.assertEqual(compiler.calls, 0)
        self.assertFalse(prepared.route.request.model_call_required)
        self.assertEqual(prepared.route.request.model_visible_text, "")

    def test_invalid_silence_proof_falls_back(self) -> None:
        source = "A reply is required."
        proof = SilenceProof(
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "2" * 64,
            no_required_message=False,
            no_effectful_intent=True,
        )
        decision = plan_route(
            source,
            self.capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={
                "silence": passing_evidence(
                    "silence-evidence", route_mode="silence"
                )
            },
            silence_proof=proof,
            utility_evidence_verifier=verify_utility,
            silence_verifier=verify_bound_artifact,
        )
        self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_verified_session_routine_can_win_but_digest_mismatch_cannot(self) -> None:
        source = "Repeat the verified read-only status check. " * 500
        digest = ROUTINE_DIGEST
        receiver = ReceiverCapabilities(session_routine_sha256=(digest,))
        routine = RoutineInvocation(
            routine_id="status-check",
            routine_sha256=digest,
            routine_definition_text=ROUTINE_DEFINITION_TEXT,
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "5" * 64,
            payload={"artifact": 7},
            receiver_acknowledged=True,
            session_local=True,
            effect_free=True,
        )
        decision = plan_route(
            source,
            self.capsule,
            receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={
                "routine": passing_evidence(
                    "routine-evidence", route_mode="routine"
                )
            },
            routine=routine,
            policy=RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=verify_utility,
            routine_verifier=verify_bound_artifact,
        )
        self.assertEqual(decision.selected_mode, "routine")

        mismatched_receiver = ReceiverCapabilities(
            session_routine_sha256=("sha256:" + "4" * 64,)
        )
        fallback = plan_route(
            source,
            self.capsule,
            mismatched_receiver,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={
                "routine": passing_evidence(
                    "routine-evidence", route_mode="routine"
                )
            },
            routine=routine,
            policy=RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=verify_utility,
            routine_verifier=verify_bound_artifact,
        )
        self.assertIn(fallback.selected_mode, {"raw", "json"})

    def test_capsule_cold_cost_is_explicit_and_can_change_routing(self) -> None:
        source = "long source " * 2000
        reply = ModelReply(sender_output(self.state), "model-a", 9)
        outcome = compile_natural_language(
            source,
            self.capsule,
            FakeCompiler(reply),
            task_context=TASK_CONTEXT,
        )
        evidence = {"action-state": passing_evidence()}
        cached = plan_route(
            source,
            self.capsule,
            action_receiver(self.capsule.sha256, cached=True),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence=evidence,
            compile_outcome=outcome,
            fidelity_verification=fidelity_for(source, self.state),
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        cold = plan_route(
            source,
            self.capsule,
            action_receiver(self.capsule.sha256, cached=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(
                **{
                    "action-state": CostForecast(
                        comprehension_setup_tokens=0,
                        receiver_payload_token_ceiling=2_000,
                        complete=True,
                    )
                }
            ),
            evidence=evidence,
            compile_outcome=outcome,
            fidelity_verification=fidelity_for(source, self.state),
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        cached_action = next(item for item in cached.candidates if item.mode == "action-state")
        cold_action = next(item for item in cold.candidates if item.mode == "action-state")
        self.assertIsNotNone(cached_action.cost)
        self.assertIsNotNone(cold_action.cost)
        assert cached_action.cost is not None and cold_action.cost is not None
        self.assertEqual(
            cold_action.cost.total_tokens - cached_action.cost.total_tokens,
            cold_action.cost.capsule_setup_tokens
            - cached_action.cost.cached_context_tokens,
        )

    def test_no_strict_total_token_advantage_rejects_optimized_route(self) -> None:
        source = "x"
        outcome = compile_natural_language(
            source,
            self.capsule,
            FakeCompiler(ModelReply(sender_output(self.state), "model-a", 1)),
            task_context=TASK_CONTEXT,
        )
        decision = plan_route(
            source,
            self.capsule,
            self.receiver,
            lambda text: 1 if text else 0,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compile_outcome=outcome,
            fidelity_verification=fidelity_for(source, self.state),
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        action = next(item for item in decision.candidates if item.mode == "action-state")
        self.assertFalse(action.eligible)
        self.assertIn("no-strict-total-token-advantage", action.reasons)
        self.assertIn(decision.selected_mode, {"raw", "json"})

    def test_cost_ledger_contains_every_goal_category_once(self) -> None:
        forecast = CostForecast(
            task_system_tokens=1,
            sender_tokens=99,
            router_tokens=2,
            provider_framing_tokens=3,
            receiver_output_tokens=4,
            reasoning_tokens=5,
            repair_tokens=6,
            fallback_tokens=7,
            tool_tokens=8,
            safety_tokens=9,
            judge_tokens=10,
            complete=True,
        )
        source = "raw"
        decision = plan_route(
            source,
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(raw=forecast),
        )
        ledger = decision.selected_cost
        self.assertEqual(ledger.task_system_tokens, 1)
        self.assertEqual(ledger.sender_tokens, 0)
        self.assertEqual(ledger.semantic_verification_tokens, 0)
        self.assertEqual(ledger.router_tokens, 2)
        self.assertEqual(ledger.provider_framing_tokens, 3)
        self.assertEqual(
            ledger.receiver_input_tokens + ledger.task_context_setup_tokens,
            len(decision.request.model_visible_text),
        )
        self.assertGreater(ledger.task_context_setup_tokens, 0)
        self.assertEqual(ledger.receiver_output_tokens, 4)
        self.assertEqual(ledger.reasoning_tokens, 5)
        self.assertEqual(ledger.repair_tokens, 6)
        self.assertEqual(ledger.fallback_tokens, 7)
        self.assertEqual(ledger.tool_tokens, 8)
        self.assertEqual(ledger.safety_tokens, 9)
        self.assertEqual(ledger.judge_tokens, 10)
        self.assertEqual(
            ledger.total_tokens,
            sum(
                (
                    1,
                    0,
                    0,
                    2,
                    3,
                    ledger.task_context_setup_tokens,
                    ledger.receiver_input_tokens,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                )
            ),
        )

    def test_raw_fallback_and_no_authority_are_nonnegotiable(self) -> None:
        with self.assertRaises(RoutingError):
            ReceiverCapabilities(supports_raw=False)
        for field in (
            "persistence_authorized",
            "permission_expansion_authorized",
            "spending_authorized",
            "external_effects_authorized",
        ):
            with self.subTest(field=field), self.assertRaises(RoutingError):
                ReceiverCapabilities(**{field: True})


class HybridExecutionContractTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.state = PublicActionState.from_object(
            self.capsule.to_object()["examples"]["positive"]
        )

    def _action_prepared(self, *, forecasts=None):
        source = "Verify artifact seven without external effects. " * 800
        compiler = FakeCompiler(ModelReply(sender_output(self.state), "model-a", 10))
        prepared = prepare_message(
            source,
            self.capsule,
            action_receiver(self.capsule.sha256),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=forecasts or complete_forecasts(),
            evidence={"action-state": passing_evidence()},
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            policy=action_policy(),
            utility_evidence_verifier=verify_utility,
            capsule_comprehension_verifier=verify_comprehension,
            task_context_comprehension_verifier=verify_task_context,
        )
        self.assertEqual(prepared.route.selected_mode, "action-state")
        return prepared, compiler

    @staticmethod
    def _complete_local_usage(prepared, **overrides):
        values = {
            "setup_tokens": 2,
            "router_tokens": 4,
            "repair_tokens": 0,
            "fallback_tokens": 0,
            "tool_tokens": 0,
            "safety_tokens": 1,
            "judge_tokens": 6,
        }
        values.update(overrides)
        return ObservedLocalUsage.for_prepared(prepared, **values)

    def test_silence_executes_zero_receiver_calls(self) -> None:
        source = "Already delivered and no reply is required."
        proof = SilenceProof(
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "1" * 64,
            no_required_message=True,
            no_effectful_intent=True,
        )
        prepared = prepare_message(
            source,
            self.capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={
                "silence": passing_evidence(
                    "silence-exec", route_mode="silence"
                )
            },
            silence_proof=proof,
            utility_evidence_verifier=verify_utility,
            silence_verifier=verify_bound_artifact,
        )
        adapter = FakeReceiverAdapter()
        execution = execute_prepared_message(
            prepared, adapter, output_validator=validate_output
        )
        self.assertEqual(execution.final_mode, "silence")
        self.assertEqual(execution.compiler_calls, 0)
        self.assertEqual(execution.receiver_calls, 0)
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(execution.observed_runtime_tokens, 0)
        self.assertTrue(execution.safely_completed)

    def test_raw_json_and_routine_each_execute_one_receiver_call(self) -> None:
        raw = prepare_message(
            "raw source",
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        json_prepared = prepare_message(
            "{}",
            self.capsule,
            ReceiverCapabilities(),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(
                raw=CostForecast(receiver_output_tokens=1_000, complete=True)
            ),
        )
        source = "Repeat the verified status check. " * 500
        digest = ROUTINE_DIGEST
        routine = RoutineInvocation(
            routine_id="status-check",
            routine_sha256=digest,
            routine_definition_text=ROUTINE_DEFINITION_TEXT,
            source_text=source,
            source_sha256=source_text_sha256(source),
            task_context_text=TASK_CONTEXT.canonical_text,
            task_context_sha256=TASK_CONTEXT.sha256,
            verifier_sha256="sha256:" + "5" * 64,
            payload={"artifact": 7},
            receiver_acknowledged=True,
            session_local=True,
            effect_free=True,
        )
        routine_prepared = prepare_message(
            source,
            self.capsule,
            ReceiverCapabilities(session_routine_sha256=(digest,)),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            evidence={
                "routine": passing_evidence("routine-exec", route_mode="routine")
            },
            routine=routine,
            policy=RouterPolicy(receiver_total_token_ceiling=10_000),
            utility_evidence_verifier=verify_utility,
            routine_verifier=verify_bound_artifact,
        )
        for expected, prepared in (
            ("raw", raw),
            ("json", json_prepared),
            ("routine", routine_prepared),
        ):
            adapter = FakeReceiverAdapter(receiver_reply())
            execution = execute_prepared_message(
                prepared, adapter, output_validator=validate_output
            )
            with self.subTest(mode=expected):
                self.assertEqual(prepared.route.selected_mode, expected)
                self.assertEqual(execution.final_mode, expected)
                self.assertEqual(execution.compiler_calls, 0)
                self.assertEqual(execution.receiver_calls, 1)
                self.assertEqual(adapter.calls, 1)
                self.assertEqual(execution.observed_runtime_tokens, 5)
                self.assertTrue(execution.safely_completed)

    def test_action_state_executes_one_compiler_and_one_direct_receiver_call(self) -> None:
        prepared, compiler = self._action_prepared()
        adapter = FakeReceiverAdapter(receiver_reply())
        execution = execute_prepared_message(
            prepared, adapter, output_validator=validate_output
        )
        self.assertEqual(compiler.calls, 1)
        self.assertEqual(execution.compiler_calls, 1)
        self.assertEqual(execution.fidelity_verifier_calls, 1)
        self.assertEqual(execution.receiver_calls, 1)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(adapter.requests[0].mode, "action-state")
        self.assertEqual(execution.final_mode, "action-state")
        self.assertEqual(execution.observed_runtime_tokens, 18)
        self.assertTrue(execution.safely_completed)

    def test_observed_ledger_reconciles_exact_bound_complete_runtime_scope(self) -> None:
        prepared, _ = self._action_prepared()
        execution = execute_prepared_message(
            prepared,
            FakeReceiverAdapter(receiver_reply()),
            output_validator=validate_output,
            observed_local_usage=self._complete_local_usage(prepared),
        )
        ledger = execution.observed_ledger
        assert ledger is not None
        self.assertTrue(ledger.scope_complete)
        self.assertTrue(execution.scope_complete)
        self.assertEqual(ledger.observed_model_total_tokens, 18)
        self.assertEqual(execution.observed_runtime_tokens, 18)
        self.assertEqual(ledger.inclusive_total_tokens, 31)
        self.assertEqual(execution.inclusive_total_tokens, 31)
        self.assertEqual(ledger.phase_total("setup"), 2)
        self.assertEqual(ledger.phase_total("router"), 4)
        self.assertEqual(ledger.phase_total("receiver"), 5)
        receiver_event = next(
            item for item in ledger.events if item.component == "primary-receiver"
        )
        self.assertEqual(receiver_event.input_tokens, 3)
        self.assertEqual(receiver_event.output_tokens, 2)
        self.assertFalse(ledger.provider_authenticity_verified)
        self.assertFalse(ledger.claim_eligible)
        self.assertFalse(ledger.goal_total_complete)
        self.assertFalse(execution.claim_eligible)
        self.assertFalse(execution.goal_total_complete)
        with self.assertRaisesRegex(ValueError, "phase coverage"):
            replace(ledger, events=ledger.events[:-1])
        with self.assertRaisesRegex(ValueError, "claim eligibility"):
            replace(ledger, claim_eligible=True)
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            replace(ledger, claim_eligible=0)
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            replace(execution, claim_eligible=0)
        local_setup = next(
            item for item in ledger.events if item.component == "local-setup"
        )
        with self.assertRaisesRegex(ValueError, "non-model event"):
            replace(local_setup, input_tokens=1)
        with self.assertRaisesRegex(ValueError, "detailed model usage"):
            replace(receiver_event, input_tokens=None)
        compiler_event = next(
            item for item in ledger.events if item.component == "sender-compiler"
        )
        with self.assertRaisesRegex(ValueError, "total-only model event"):
            replace(compiler_event, input_tokens=1)
        field_names = tuple(item.name for item in fields(type(execution)))
        self.assertEqual(field_names[10], "goal_total_complete")
        self.assertEqual(field_names[11:13], ("observed_ledger", "claim_eligible"))
        self.assertEqual(
            field_names[13:],
            ("observed_local_usage", "_construction_seal"),
        )

        judge_index = next(
            index
            for index, item in enumerate(ledger.events)
            if item.component == "local-judge"
        )
        mutated_events = list(ledger.events)
        mutated_events[judge_index] = replace(
            mutated_events[judge_index],
            total_tokens=106,
        )
        mutated_ledger = replace(ledger, events=tuple(mutated_events))
        assert execution.observed_local_usage is not None
        mutated_usage = replace(
            execution.observed_local_usage,
            judge_tokens=106,
        )
        with self.assertRaisesRegex(ValueError, "minted by the executor"):
            replace(
                execution,
                observed_ledger=mutated_ledger,
                observed_local_usage=mutated_usage,
            )

    def test_local_usage_binding_includes_compiler_and_fidelity_identity(self) -> None:
        prepared, _ = self._action_prepared()
        assert prepared.compilation is not None
        sibling = replace(
            prepared,
            compilation=replace(
                prepared.compilation,
                model_id="different-sender-model",
            ),
        )
        self.assertNotEqual(
            prepared.execution_binding_sha256,
            sibling.execution_binding_sha256,
        )
        adapter = FakeReceiverAdapter(receiver_reply())
        with self.assertRaisesRegex(ValueError, "not bound"):
            execute_prepared_message(
                sibling,
                adapter,
                output_validator=validate_output,
                observed_local_usage=self._complete_local_usage(prepared),
            )
        self.assertEqual(adapter.calls, 0)

    def test_local_usage_binding_includes_full_route_and_baseline_identity(self) -> None:
        raw_baseline, _ = self._action_prepared(
            forecasts=complete_forecasts(
                json=CostForecast(receiver_output_tokens=5_000, complete=True)
            )
        )
        json_baseline, _ = self._action_prepared(
            forecasts=complete_forecasts(
                raw=CostForecast(receiver_output_tokens=5_000, complete=True)
            )
        )
        self.assertEqual(raw_baseline.route.best_baseline_mode, "raw")
        self.assertEqual(json_baseline.route.best_baseline_mode, "json")
        self.assertNotEqual(
            raw_baseline.route.binding_sha256,
            json_baseline.route.binding_sha256,
        )
        self.assertNotEqual(
            raw_baseline.execution_binding_sha256,
            json_baseline.execution_binding_sha256,
        )
        adapter = FakeReceiverAdapter(receiver_reply())
        with self.assertRaisesRegex(ValueError, "not bound"):
            execute_prepared_message(
                json_baseline,
                adapter,
                output_validator=validate_output,
                observed_local_usage=self._complete_local_usage(raw_baseline),
            )
        self.assertEqual(adapter.calls, 0)

    def test_receiver_event_from_equal_total_different_reply_cannot_be_spliced(self) -> None:
        prepared = prepare_message(
            "raw source",
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        usage = self._complete_local_usage(prepared)
        first = execute_prepared_message(
            prepared,
            FakeReceiverAdapter(receiver_reply("valid")),
            output_validator=validate_output,
            observed_local_usage=usage,
        )
        second = execute_prepared_message(
            prepared,
            FakeReceiverAdapter(receiver_reply("different")),
            output_validator=validate_output,
            observed_local_usage=usage,
        )
        assert first.observed_ledger is not None
        assert second.observed_ledger is not None
        foreign = next(
            item
            for item in second.observed_ledger.events
            if item.component == "primary-receiver"
        )
        spliced = replace(
            first.observed_ledger,
            events=tuple(
                foreign if item.component == "primary-receiver" else item
                for item in first.observed_ledger.events
            ),
        )
        with self.assertRaisesRegex(ValueError, "minted by the executor"):
            replace(first, observed_ledger=spliced)

    def test_unexecuted_local_phase_cannot_report_positive_usage(self) -> None:
        prepared = prepare_message(
            "raw source",
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        for field_name in ("fallback_tokens", "repair_tokens", "tool_tokens"):
            adapter = FakeReceiverAdapter(receiver_reply())
            with self.subTest(field=field_name), self.assertRaisesRegex(
                ValueError,
                "without an executed phase|without a fallback",
            ):
                execute_prepared_message(
                    prepared,
                    adapter,
                    output_validator=validate_output,
                    observed_local_usage=self._complete_local_usage(
                        prepared,
                        **{field_name: 999},
                    ),
                )
            self.assertEqual(adapter.calls, 0)

    def test_local_setup_scope_explicitly_excludes_cold_comprehension(self) -> None:
        prepared, _ = self._action_prepared()
        with self.assertRaisesRegex(ValueError, "exclude cold comprehension"):
            replace(
                self._complete_local_usage(prepared),
                setup_scope="includes-cold-comprehension",
            )

    def test_unknown_local_category_is_not_filled_from_complete_forecast(self) -> None:
        prepared, _ = self._action_prepared()
        execution = execute_prepared_message(
            prepared,
            FakeReceiverAdapter(receiver_reply()),
            output_validator=validate_output,
            observed_local_usage=self._complete_local_usage(
                prepared,
                judge_tokens=None,
            ),
        )
        ledger = execution.observed_ledger
        assert ledger is not None
        self.assertTrue(prepared.route.selected_cost.complete)
        self.assertFalse(ledger.scope_complete)
        self.assertFalse(execution.scope_complete)
        self.assertIsNone(ledger.phase_total("judge"))
        self.assertIsNone(ledger.inclusive_total_tokens)
        self.assertIsNone(execution.inclusive_total_tokens)

    def test_mismatched_local_usage_is_rejected_before_receiver_call(self) -> None:
        prepared, _ = self._action_prepared()
        local_usage = replace(
            self._complete_local_usage(prepared),
            execution_binding_sha256="sha256:" + "0" * 64,
        )
        adapter = FakeReceiverAdapter(receiver_reply())
        with self.assertRaisesRegex(ValueError, "not bound"):
            execute_prepared_message(
                prepared,
                adapter,
                output_validator=validate_output,
                observed_local_usage=local_usage,
            )
        self.assertEqual(adapter.calls, 0)

    def test_invalid_action_output_uses_one_lossless_baseline_fallback_call(self) -> None:
        prepared, _ = self._action_prepared()
        adapter = FakeReceiverAdapter(receiver_reply("invalid"), receiver_reply("valid"))
        execution = execute_prepared_message(
            prepared,
            adapter,
            output_validator=validate_output,
            observed_local_usage=self._complete_local_usage(
                prepared,
                fallback_tokens=1,
            ),
        )
        self.assertEqual(execution.compiler_calls, 1)
        self.assertEqual(execution.fidelity_verifier_calls, 1)
        self.assertEqual(execution.receiver_calls, 2)
        self.assertEqual(adapter.calls, 2)
        self.assertEqual(adapter.requests[0].mode, "action-state")
        self.assertIn(adapter.requests[1].mode, {"raw", "json"})
        self.assertIn(execution.final_mode, {"raw", "json"})
        self.assertEqual(execution.observed_runtime_tokens, 23)
        self.assertTrue(execution.safely_completed)
        ledger = execution.observed_ledger
        assert ledger is not None
        self.assertEqual(ledger.phase_total("fallback"), 6)
        self.assertEqual(
            tuple(
                item.component
                for item in ledger.events
                if item.phase == "fallback"
            ),
            ("local-fallback", "baseline-fallback-receiver"),
        )
        self.assertEqual(ledger.inclusive_total_tokens, 37)

    def test_absent_output_validator_forces_optimized_route_to_baseline(self) -> None:
        prepared, _ = self._action_prepared()
        adapter = FakeReceiverAdapter(receiver_reply("valid"), receiver_reply("valid"))
        execution = execute_prepared_message(
            prepared,
            adapter,
            output_validator=None,
        )
        self.assertEqual(execution.primary.request_mode, "action-state")
        self.assertEqual(execution.receiver_calls, 2)
        self.assertIsNotNone(execution.fallback)
        self.assertIn(execution.final_mode, {"raw", "json"})
        self.assertIsNone(execution.output_valid)
        self.assertIsNone(execution.safely_completed)

    def test_failed_primary_usage_makes_runtime_total_incomplete_after_fallback(self) -> None:
        prepared, _ = self._action_prepared()
        adapter = FakeReceiverAdapter(RuntimeError("provider failed"), receiver_reply())
        execution = execute_prepared_message(
            prepared,
            adapter,
            output_validator=validate_output,
            observed_local_usage=self._complete_local_usage(prepared),
        )
        self.assertEqual(execution.receiver_calls, 2)
        self.assertEqual(execution.primary.failure, "receiver-call-failed")
        self.assertIsNotNone(execution.fallback)
        self.assertIsNone(execution.observed_runtime_tokens)
        self.assertTrue(execution.safely_completed)
        self.assertFalse(execution.scope_complete)
        self.assertIsNone(execution.inclusive_total_tokens)
        self.assertFalse(execution.goal_total_complete)

    def test_invalid_receiver_adapter_reply_type_is_incomplete_not_success(self) -> None:
        prepared = prepare_message(
            "raw source",
            self.capsule,
            ReceiverCapabilities(supports_json=False),
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
        )
        adapter = FakeReceiverAdapter("not-a-receiver-reply")
        execution = execute_prepared_message(
            prepared, adapter, output_validator=validate_output
        )
        self.assertEqual(execution.receiver_calls, 1)
        self.assertEqual(execution.primary.failure, "receiver-reply-type-invalid")
        self.assertIsNone(execution.observed_runtime_tokens)
        self.assertFalse(execution.safely_completed)
        self.assertFalse(execution.goal_total_complete)


if __name__ == "__main__":
    import unittest

    unittest.main()
