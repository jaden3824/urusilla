from __future__ import annotations

import json
from dataclasses import fields, replace
from unittest import TestCase, mock

import urusilla_hybrid_runtime.comprehension as comprehension_module

from urusilla_hybrid_runtime.canonical import (
    canonical_json,
    sha256_text,
    strict_json_loads,
)
from urusilla_hybrid_runtime.comprehension import (
    CAPSULE_COMPREHENSION_VERIFIER_SHA256,
    COMPREHENSION_RESPONSE_FORMAT,
    TASK_CONTEXT_COMPREHENSION_VERIFIER_SHA256,
    ColdStartComprehensionChallenge,
    ComprehensionError,
    ComprehensionModelReply,
    ReceiverModelBinding,
    build_cold_start_comprehension_challenge,
    execute_cold_start_preparation,
    prepare_message_with_cold_comprehension,
    run_cold_start_comprehension,
)
from urusilla_hybrid_runtime.records import (
    PublicActionState,
    load_capsule,
    source_text_sha256,
)
from urusilla_hybrid_runtime.router import (
    RouterPolicy,
    SilenceProof,
    action_state_preflight,
)
from urusilla_hybrid_runtime.runtime import ObservedLocalUsage
from urusilla_hybrid_runtime.sender import ModelReply
from urusilla_hybrid_runtime.task_context import PublicTaskContext
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
    verify_bound_artifact,
    verify_fidelity,
    verify_utility,
)


RECEIVER_BINDING = ReceiverModelBinding(
    model_id="unfamiliar-model-a",
    settings_sha256="sha256:" + "6" * 64,
)


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _null_paths(value: object, path: str = "") -> list[str]:
    if value is None:
        return [path or "/"]
    result: list[str] = []
    if type(value) is dict:
        for key in sorted(value):
            result.extend(
                _null_paths(value[key], path + "/" + _pointer_escape(str(key)))
            )
    elif type(value) is list:
        for index, item in enumerate(value):
            result.extend(_null_paths(item, path + f"/{index}"))
    return result


def _negated_paths(example: dict[str, object]) -> list[str]:
    result: list[str] = []
    goal = example["goal"]
    if type(goal) is dict and goal["n"] is True:
        result.append("/goal")
    for field_name in ("state", "constraints", "needs"):
        values = example[field_name]
        assert type(values) is list
        for index, item in enumerate(values):
            assert type(item) is dict
            if item["n"] is True:
                result.append(f"/{field_name}/{index}")
    outcome = example["outcome"]
    if type(outcome) is dict:
        evidence = outcome["evidence"]
        assert type(evidence) is list
        for index, item in enumerate(evidence):
            assert type(item) is dict
            if item["n"] is True:
                result.append(f"/outcome/evidence/{index}")
    return result


def exact_response(challenge: ColdStartComprehensionChallenge) -> str:
    """Independent test-side solver for the public challenge contract."""

    user = strict_json_loads(challenge.user_text)
    assert type(user) is dict
    capsule = user["capsule"]
    task = user["task_context"]
    example = user["positive_example"]
    bindings = user["digest_bindings"]
    assert type(capsule) is dict
    assert type(task) is dict
    assert type(example) is dict
    assert type(bindings) is dict
    symbols = task["symbols"]
    assert type(symbols) is list
    identities = sorted(
        (
            {"kind": str(item["kind"]), "name": str(item["name"])}
            for item in symbols
        ),
        key=lambda item: (item["kind"], item["name"]),
    )
    outcome = example["outcome"]
    assert type(outcome) is dict
    return canonical_json(
        {
            "format": COMPREHENSION_RESPONSE_FORMAT,
            "challenge_sha256": bindings["challenge_sha256"],
            "capsule_sha256": bindings["capsule_sha256"],
            "task_context_sha256": bindings["task_context_sha256"],
            "task_profile_sha256": bindings["task_profile_sha256"],
            "symbol_table_sha256": bindings["symbol_table_sha256"],
            "positive_example_sha256": bindings["positive_example_sha256"],
            "receiver_binding_sha256": bindings["receiver_binding_sha256"],
            "authority_boundary": {
                "capsule": capsule["authority_boundary"],
                "task_context": task["authority_boundary"],
            },
            "preservation": {
                "negated_atom_paths": _negated_paths(example),
                "failure_outcome_status": outcome["status"],
                "null_paths": _null_paths(example),
            },
            "direct_task_output": {
                "task_id": task["task_id"],
                "objective": task["objective"],
                "allowed_acts": task["allowed_acts"],
                "output_contract": task["output_contract"],
                "symbol_identities": identities,
            },
        }
    )


def good_reply(
    challenge: ColdStartComprehensionChallenge,
    *,
    text: str | None = None,
    model_id: str | None = None,
    model_settings_sha256: str | None = None,
    input_tokens: int | None = 19,
    output_tokens: int | None = 11,
    provider_total_tokens: int | None = 30,
    **boundary: object,
) -> ComprehensionModelReply:
    return ComprehensionModelReply(
        text=exact_response(challenge) if text is None else text,
        model_id=model_id or challenge.receiver_binding.model_id,
        model_settings_sha256=(
            model_settings_sha256
            or challenge.receiver_binding.settings_sha256
        ),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=provider_total_tokens,
        **boundary,
    )


class ScriptedAdapter:
    def __init__(self, script):
        self.script = script
        self.calls = 0
        self.challenges: list[ColdStartComprehensionChallenge] = []

    def complete(self, challenge):
        self.calls += 1
        self.challenges.append(challenge)
        if isinstance(self.script, Exception):
            raise self.script
        if callable(self.script):
            return self.script(challenge)
        return self.script


class ColdStartChallengeTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()

    def test_challenge_is_deterministic_exact_and_cold(self) -> None:
        first = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=300,
        )
        second = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=300,
        )
        changed_cap = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=301,
        )
        changed_binding = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            ReceiverModelBinding(
                model_id=RECEIVER_BINDING.model_id,
                settings_sha256="sha256:" + "9" * 64,
            ),
            maximum_total_tokens=300,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.model_visible_text, second.model_visible_text)
        self.assertEqual(first.model_visible_sha256, second.model_visible_sha256)
        self.assertNotEqual(first.challenge_sha256, changed_cap.challenge_sha256)
        self.assertNotEqual(
            first.challenge_sha256,
            changed_binding.challenge_sha256,
        )
        user = strict_json_loads(first.user_text)
        self.assertEqual(user["capsule"], self.capsule.to_object())
        self.assertEqual(user["task_context"], TASK_CONTEXT.to_object())
        self.assertEqual(
            user["receiver_binding"],
            RECEIVER_BINDING.to_object(),
        )
        self.assertEqual(
            user["digest_bindings"],
            {
                "challenge_sha256": first.challenge_sha256,
                "capsule_sha256": first.capsule_sha256,
                "task_context_sha256": first.task_context_sha256,
                "task_profile_sha256": first.task_profile_sha256,
                "symbol_table_sha256": first.symbol_table_sha256,
                "positive_example_sha256": first.positive_example_sha256,
                "receiver_binding_sha256": RECEIVER_BINDING.sha256,
            },
        )
        authority_template = user["response_contract"][
            "authority_boundary_template"
        ]
        self.assertEqual(set(authority_template), {"capsule", "task_context"})
        self.assertTrue(
            all(
                bit is False
                for boundary in authority_template.values()
                for bit in boundary.values()
            )
        )
        direct_derivation = user["response_contract"][
            "direct_task_output_derivation"
        ]
        self.assertEqual(
            direct_derivation["allowed_acts"],
            {
                "copy_exact_from": "/task_context/allowed_acts",
                "order": "source-order",
            },
        )
        self.assertEqual(
            direct_derivation["symbol_identities"]["item_template"],
            {
                "kind": "source-symbol-kind-string",
                "name": "source-symbol-name-string",
            },
        )
        self.assertEqual(
            direct_derivation["symbol_identities"]["exact_item_fields"],
            ["kind", "name"],
        )
        path_derivation = user["response_contract"][
            "preservation_path_derivation"
        ]
        self.assertEqual(path_derivation["begins_with"], "/")
        self.assertEqual(path_derivation["array_index_segment_template"], "/0")
        self.assertIn("/state/0", path_derivation["json_pointer_examples"])
        self.assertIn("state[0]", path_derivation["forbidden_examples"])
        self.assertEqual(
            user["positive_example"],
            self.capsule.to_object()["examples"]["positive"],
        )
        self.assertEqual(user["maximum_total_tokens"], 300)
        self.assertIn("or extra field", first.system_text)
        self.assertNotIn("credential", first.user_text.casefold())

    def test_direct_construction_cannot_change_model_visible_contract(self) -> None:
        challenge = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=100,
        )
        with self.assertRaises(ComprehensionError):
            replace(challenge, system_text="changed")
        with self.assertRaises(ComprehensionError):
            replace(challenge, challenge_sha256="sha256:" + "0" * 64)
        missing = strict_json_loads(challenge.user_text)
        del missing["digest_bindings"]["capsule_sha256"]
        with self.assertRaises(ComprehensionError):
            replace(challenge, user_text=canonical_json(missing))
        mismatched = strict_json_loads(challenge.user_text)
        mismatched["digest_bindings"]["receiver_binding_sha256"] = (
            RECEIVER_BINDING.settings_sha256
        )
        with self.assertRaises(ComprehensionError):
            replace(challenge, user_text=canonical_json(mismatched))


class ColdStartExecutionTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()

    def run_good(self, *, cap: int = 100):
        adapter = ScriptedAdapter(lambda challenge: good_reply(challenge))
        attempt = run_cold_start_comprehension(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            adapter,
            maximum_total_tokens=cap,
        )
        return attempt, adapter

    def test_good_reply_mints_bound_cold_capabilities_and_router_callbacks(self) -> None:
        attempt, adapter = self.run_good()
        self.assertEqual(adapter.calls, 1)
        self.assertTrue(attempt.passed)
        self.assertIsNone(attempt.failure)
        evidence = attempt.evidence
        assert evidence is not None
        self.assertEqual(evidence.model_id, "unfamiliar-model-a")
        self.assertEqual(
            evidence.model_settings_sha256,
            RECEIVER_BINDING.settings_sha256,
        )
        self.assertEqual(evidence.receiver_binding, RECEIVER_BINDING)
        self.assertEqual(evidence.provider_total_tokens, 30)
        self.assertEqual(evidence.output_sha256, attempt.output_sha256)
        self.assertEqual(
            evidence.challenge_sha256,
            adapter.challenges[0].challenge_sha256,
        )
        self.assertEqual(
            evidence.model_visible_sha256,
            sha256_text(adapter.challenges[0].model_visible_text),
        )
        self.assertEqual(evidence.calls, 1)
        self.assertTrue(evidence.capsule_authority_verified)
        self.assertTrue(evidence.task_authority_verified)
        self.assertTrue(evidence.negation_preserved)
        self.assertTrue(evidence.failure_preserved)
        self.assertTrue(evidence.null_preserved)
        self.assertTrue(evidence.direct_task_output_verified)

        receiver = evidence.to_receiver_capabilities()
        self.assertTrue(receiver.supports_direct_action_state)
        self.assertFalse(receiver.capsule_cached_in_same_model_context)
        self.assertFalse(receiver.task_context_cached_in_same_model_context)
        self.assertIsNone(receiver.capsule_context_id)
        self.assertIsNone(receiver.task_context_id)
        self.assertEqual(receiver.capsule_comprehension_sha256, evidence.sha256)
        self.assertEqual(
            receiver.task_context_comprehension_sha256,
            evidence.sha256,
        )
        self.assertFalse(receiver.persistence_authorized)
        self.assertFalse(receiver.permission_expansion_authorized)
        self.assertFalse(receiver.spending_authorized)
        self.assertFalse(receiver.external_effects_authorized)

        capsule_check = evidence.capsule_comprehension_verifier(
            receiver, self.capsule
        )
        task_check = evidence.task_context_comprehension_verifier(
            receiver, TASK_CONTEXT
        )
        self.assertTrue(capsule_check.passed)
        self.assertTrue(task_check.passed)
        self.assertEqual(capsule_check.input_binding_sha256, evidence.sha256)
        self.assertEqual(task_check.input_binding_sha256, evidence.sha256)
        self.assertEqual(
            capsule_check.verifier_sha256,
            CAPSULE_COMPREHENSION_VERIFIER_SHA256,
        )
        self.assertEqual(
            task_check.verifier_sha256,
            TASK_CONTEXT_COMPREHENSION_VERIFIER_SHA256,
        )
        preflight, reasons = action_state_preflight(
            receiver,
            self.capsule,
            TASK_CONTEXT,
            None,
            RouterPolicy(allow_development_trial=True),
            capsule_comprehension_verifier=(
                evidence.capsule_comprehension_verifier
            ),
            task_context_comprehension_verifier=(
                evidence.task_context_comprehension_verifier
            ),
        )
        self.assertTrue(preflight, reasons)
        self.assertEqual(reasons, ())

    def test_preservation_probe_and_direct_task_output_are_exact(self) -> None:
        challenge = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=100,
        )
        value = strict_json_loads(exact_response(challenge))
        self.assertEqual(value["preservation"]["negated_atom_paths"], ["/state/0"])
        self.assertEqual(value["preservation"]["failure_outcome_status"], "failed")
        self.assertIn("/outcome/value", value["preservation"]["null_paths"])
        self.assertIn("/needs/0/src", value["preservation"]["null_paths"])
        self.assertEqual(
            value["direct_task_output"]["task_id"],
            TASK_CONTEXT.to_object()["task_id"],
        )
        self.assertEqual(
            value["direct_task_output"]["symbol_identities"],
            [
                {"kind": "predicate", "name": "task.verify"},
                {"kind": "predicate", "name": "test.failure-log"},
                {"kind": "predicate", "name": "test.passed"},
            ],
        )

    def test_exception_and_invalid_reply_type_fail_closed_after_one_call(self) -> None:
        cases = (
            (
                ScriptedAdapter(RuntimeError("DO-NOT-LEAK-PROVIDER-SECRET")),
                "adapter-call-failed",
            ),
            (ScriptedAdapter("not-a-reply"), "adapter-reply-type-invalid"),
        )
        for adapter, expected in cases:
            with self.subTest(expected=expected):
                attempt = run_cold_start_comprehension(
                    self.capsule,
                    TASK_CONTEXT,
                    RECEIVER_BINDING,
                    adapter,
                    maximum_total_tokens=100,
                )
                self.assertEqual(adapter.calls, 1)
                self.assertFalse(attempt.passed)
                self.assertEqual(attempt.failure, expected)
                self.assertIsNone(attempt.evidence)
                self.assertNotIn("DO-NOT-LEAK", repr(attempt))

    def test_malformed_wrong_semantics_and_unknown_usage_never_mint_evidence(self) -> None:
        def malformed(challenge):
            return good_reply(challenge, text="{}")

        def missing_digest(challenge):
            value = strict_json_loads(exact_response(challenge))
            del value["task_profile_sha256"]
            return good_reply(challenge, text=canonical_json(value))

        def mismatched_digest(challenge):
            value = strict_json_loads(exact_response(challenge))
            value["receiver_binding_sha256"] = "sha256:" + "0" * 64
            return good_reply(challenge, text=canonical_json(value))

        def noncanonical(challenge):
            value = strict_json_loads(exact_response(challenge))
            return good_reply(
                challenge,
                text=json.dumps(value, ensure_ascii=False, indent=2),
            )

        def wrong_semantics(challenge):
            value = strict_json_loads(exact_response(challenge))
            value["preservation"]["failure_outcome_status"] = "succeeded"
            return good_reply(challenge, text=canonical_json(value))

        def flattened_authority_boundary(challenge):
            value = strict_json_loads(exact_response(challenge))
            value["authority_boundary"] = value["authority_boundary"][
                "capsule"
            ]
            return good_reply(challenge, text=canonical_json(value))

        def unknown_usage(challenge):
            return good_reply(
                challenge,
                input_tokens=19,
                output_tokens=11,
                provider_total_tokens=None,
            )

        def wrong_receiver_binding(challenge):
            return good_reply(
                challenge,
                model_settings_sha256="sha256:" + "7" * 64,
            )

        cases = (
            (malformed, "response-malformed"),
            (missing_digest, "response-malformed"),
            (noncanonical, "response-malformed"),
            (flattened_authority_boundary, "response-malformed"),
            (mismatched_digest, "response-semantic-mismatch"),
            (wrong_semantics, "response-semantic-mismatch"),
            (unknown_usage, "usage-unknown"),
            (wrong_receiver_binding, "receiver-binding-mismatch"),
        )
        for script, expected in cases:
            with self.subTest(expected=expected):
                adapter = ScriptedAdapter(script)
                attempt = run_cold_start_comprehension(
                    self.capsule,
                    TASK_CONTEXT,
                    RECEIVER_BINDING,
                    adapter,
                    maximum_total_tokens=100,
                )
                self.assertEqual(adapter.calls, 1)
                self.assertEqual(attempt.failure, expected)
                self.assertFalse(attempt.passed)
                self.assertIsNone(attempt.evidence)

    def test_live_retry_order_shape_and_path_variants_are_rejected(self) -> None:
        challenge = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=100,
        )
        exact = strict_json_loads(exact_response(challenge))
        self.assertEqual(
            exact["direct_task_output"]["allowed_acts"],
            TASK_CONTEXT.to_object()["allowed_acts"],
        )
        self.assertTrue(
            all(
                type(item) is dict and set(item) == {"kind", "name"}
                for item in exact["direct_task_output"]["symbol_identities"]
            )
        )
        self.assertTrue(
            all(
                path.startswith("/") and "[" not in path
                for field in ("negated_atom_paths", "null_paths")
                for path in exact["preservation"][field]
            )
        )
        accepted = run_cold_start_comprehension(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            ScriptedAdapter(lambda current: good_reply(current)),
            maximum_total_tokens=100,
        )
        self.assertTrue(accepted.passed)

        def sorted_allowed_acts(current):
            value = strict_json_loads(exact_response(current))
            value["direct_task_output"]["allowed_acts"] = sorted(
                value["direct_task_output"]["allowed_acts"]
            )
            return good_reply(current, text=canonical_json(value))

        def string_symbol_identities(current):
            value = strict_json_loads(exact_response(current))
            value["direct_task_output"]["symbol_identities"] = [
                f"{item['kind']}/{item['name']}"
                for item in value["direct_task_output"]["symbol_identities"]
            ]
            return good_reply(current, text=canonical_json(value))

        def dot_and_bracket_paths(current):
            value = strict_json_loads(exact_response(current))
            value["preservation"]["negated_atom_paths"] = ["state[0]"]
            value["preservation"]["null_paths"] = ["outcome.value"]
            return good_reply(current, text=canonical_json(value))

        cases = (
            (sorted_allowed_acts, "response-semantic-mismatch"),
            (string_symbol_identities, "response-malformed"),
            (dot_and_bracket_paths, "response-malformed"),
        )
        for script, failure in cases:
            with self.subTest(failure=failure):
                adapter = ScriptedAdapter(script)
                attempt = run_cold_start_comprehension(
                    self.capsule,
                    TASK_CONTEXT,
                    RECEIVER_BINDING,
                    adapter,
                    maximum_total_tokens=100,
                )
                self.assertEqual(adapter.calls, 1)
                self.assertFalse(attempt.passed)
                self.assertEqual(attempt.failure, failure)
                self.assertIsNone(attempt.evidence)

    def test_token_cap_is_hard_and_exact_cap_can_pass(self) -> None:
        over = ScriptedAdapter(
            lambda challenge: good_reply(
                challenge,
                input_tokens=60,
                output_tokens=41,
                provider_total_tokens=101,
            )
        )
        rejected = run_cold_start_comprehension(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            over,
            maximum_total_tokens=100,
        )
        self.assertEqual(over.calls, 1)
        self.assertEqual(rejected.failure, "token-budget-exceeded")
        self.assertEqual(rejected.total_tokens, 101)
        self.assertIsNone(rejected.evidence)

        exact = ScriptedAdapter(
            lambda challenge: good_reply(
                challenge,
                input_tokens=19,
                output_tokens=11,
                provider_total_tokens=30,
            )
        )
        accepted = run_cold_start_comprehension(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            exact,
            maximum_total_tokens=30,
        )
        self.assertTrue(accepted.passed)
        self.assertEqual(exact.calls, 1)

    def test_reply_type_rejects_every_prohibited_boundary(self) -> None:
        challenge = build_cold_start_comprehension_challenge(
            self.capsule,
            TASK_CONTEXT,
            RECEIVER_BINDING,
            maximum_total_tokens=100,
        )
        for field_name in (
            "tools_used",
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            with self.subTest(field=field_name), self.assertRaises(
                ComprehensionError
            ):
                good_reply(challenge, **{field_name: True})

    def test_replay_binding_mismatch_and_evidence_mutation_fail_closed(self) -> None:
        first, _ = self.run_good()
        evidence = first.evidence
        assert evidence is not None
        receiver = evidence.to_receiver_capabilities()
        forged_receiver = replace(
            receiver,
            capsule_comprehension_sha256="sha256:" + "0" * 64,
        )
        self.assertFalse(
            evidence.capsule_comprehension_verifier(
                forged_receiver, self.capsule
            ).passed
        )
        with self.assertRaises(ComprehensionError):
            replace(evidence, model_id="forged-model")

        other_value = TASK_CONTEXT.to_object()
        other_value["task_id"] = "task.verify-artifact-replay-target"
        other_context = PublicTaskContext.from_object(other_value)
        self.assertEqual(
            other_context.task_profile_sha256,
            TASK_CONTEXT.task_profile_sha256,
        )
        self.assertFalse(
            evidence.task_context_comprehension_verifier(
                receiver, other_context
            ).passed
        )

        replay_text = exact_response(first.challenge)
        replay = ScriptedAdapter(
            lambda challenge: good_reply(challenge, text=replay_text)
        )
        replay_attempt = run_cold_start_comprehension(
            self.capsule,
            other_context,
            RECEIVER_BINDING,
            replay,
            maximum_total_tokens=100,
        )
        self.assertEqual(replay.calls, 1)
        self.assertEqual(
            replay_attempt.failure,
            "response-semantic-mismatch",
        )
        self.assertIsNone(replay_attempt.evidence)

    def test_authority_or_direct_output_misstatement_fails_semantically(self) -> None:
        def changed_authority(challenge):
            value = strict_json_loads(exact_response(challenge))
            value["authority_boundary"]["capsule"]["external_effects"] = True
            return good_reply(challenge, text=canonical_json(value))

        def changed_output(challenge):
            value = strict_json_loads(exact_response(challenge))
            value["direct_task_output"]["task_id"] = "other.task"
            return good_reply(challenge, text=canonical_json(value))

        for script in (changed_authority, changed_output):
            adapter = ScriptedAdapter(script)
            attempt = run_cold_start_comprehension(
                self.capsule,
                TASK_CONTEXT,
                RECEIVER_BINDING,
                adapter,
                maximum_total_tokens=100,
            )
            self.assertEqual(attempt.failure, "response-semantic-mismatch")
            self.assertIsNone(attempt.evidence)


class ColdStartRuntimeIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.capsule = load_capsule()
        self.state = PublicActionState.from_object(
            self.capsule.to_object()["examples"]["positive"]
        )

    def test_success_passes_exact_cold_bindings_through_prepare_and_execute(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        comprehension_adapter = ScriptedAdapter(
            lambda challenge: good_reply(challenge)
        )
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "sender-model-a", 10)
        )
        route_evidence = {
            "action-state": passing_evidence(
                capsule_sha256=self.capsule.sha256
            )
        }
        with mock.patch.object(
            comprehension_module,
            "prepare_message",
            wraps=comprehension_module.prepare_message,
        ) as prepare_spy:
            preparation = prepare_message_with_cold_comprehension(
                source,
                self.capsule,
                comprehension_adapter,
                char_count,
                receiver_binding=RECEIVER_BINDING,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(),
                comprehension_maximum_total_tokens=100,
                utility_evidence=route_evidence,
                compiler=compiler,
                fidelity_verifier=verify_fidelity,
                utility_evidence_verifier=verify_utility,
                policy=action_policy(receiver_total_token_ceiling=100_000),
            )

        self.assertEqual(comprehension_adapter.calls, 1)
        self.assertEqual(prepare_spy.call_count, 2)
        self.assertEqual(preparation.status, "prepared")
        self.assertEqual(preparation.comprehension_calls, 1)
        self.assertEqual(preparation.sender_compiler_calls, 1)
        self.assertEqual(preparation.receiver_calls, 0)
        self.assertEqual(preparation.comprehension_model_id, "unfamiliar-model-a")
        self.assertEqual(
            preparation.comprehension_model_settings_sha256,
            RECEIVER_BINDING.settings_sha256,
        )
        self.assertEqual(preparation.comprehension_total_tokens, 30)
        self.assertEqual(
            preparation.comprehension_challenge_sha256,
            comprehension_adapter.challenges[0].challenge_sha256,
        )
        comprehension_evidence = preparation.comprehension.evidence
        assert comprehension_evidence is not None
        self.assertEqual(
            preparation.comprehension_evidence_sha256,
            comprehension_evidence.sha256,
        )

        call = prepare_spy.call_args
        self.assertEqual(call.args[2], preparation.receiver_capabilities)
        capsule_callback = call.kwargs["capsule_comprehension_verifier"]
        task_callback = call.kwargs["task_context_comprehension_verifier"]
        self.assertIs(capsule_callback.__self__, comprehension_evidence)
        self.assertIs(task_callback.__self__, comprehension_evidence)
        self.assertIs(
            capsule_callback.__func__,
            type(comprehension_evidence).capsule_comprehension_verifier,
        )
        self.assertIs(
            task_callback.__func__,
            type(comprehension_evidence).task_context_comprehension_verifier,
        )

        receiver = preparation.receiver_capabilities
        prepared = preparation.prepared
        assert receiver is not None and prepared is not None
        self.assertFalse(receiver.capsule_cached_in_same_model_context)
        self.assertFalse(receiver.task_context_cached_in_same_model_context)
        self.assertEqual(prepared.route.selected_mode, "action-state")
        request = prepared.route.request
        self.assertTrue(request.capsule_included)
        self.assertTrue(request.task_context_included)
        self.assertIsNone(request.capsule_context_id)
        self.assertIsNone(request.task_context_id)
        self.assertEqual(
            request.comprehension_evidence_sha256,
            comprehension_evidence.sha256,
        )
        self.assertEqual(
            request.task_comprehension_evidence_sha256,
            comprehension_evidence.sha256,
        )

        receiver_adapter = FakeReceiverAdapter(
            replace(
                receiver_reply(),
                model_id=RECEIVER_BINDING.model_id,
            )
        )
        receiver_adapter.receiver_binding = RECEIVER_BINDING
        local_usage = ObservedLocalUsage.for_prepared(
            prepared,
            setup_tokens=2,
            router_tokens=4,
            repair_tokens=0,
            fallback_tokens=0,
            tool_tokens=0,
            safety_tokens=1,
            judge_tokens=6,
        )
        execution = execute_cold_start_preparation(
            preparation,
            receiver_adapter,
            output_validator=validate_output,
            observed_local_usage=local_usage,
        )
        self.assertEqual(execution.status, "executed")
        self.assertEqual(receiver_adapter.calls, 1)
        self.assertEqual(execution.comprehension_calls, 1)
        self.assertEqual(execution.sender_compiler_calls, 1)
        self.assertEqual(execution.receiver_calls, 1)
        self.assertEqual(
            execution.observed_comprehension_plus_runtime_tokens,
            48,
        )
        self.assertEqual(
            execution.comprehension_challenge_sha256,
            preparation.comprehension_challenge_sha256,
        )
        self.assertEqual(
            execution.comprehension_evidence_sha256,
            comprehension_evidence.sha256,
        )
        self.assertFalse(execution.goal_total_complete)
        self.assertTrue(execution.receiver_binding_verified)
        self.assertTrue(execution.safely_completed)
        self.assertFalse(execution.output_discard_required)
        self.assertTrue(execution.eligible_for_live_answer)
        self.assertFalse(execution.provider_authenticity_verified)
        self.assertFalse(execution.eligible_for_claim)
        self.assertTrue(execution.scope_complete)
        self.assertEqual(execution.inclusive_total_tokens, 61)
        ledger = execution.observed_ledger
        assert ledger is not None
        self.assertEqual(ledger.phase_total("setup"), 32)
        self.assertEqual(
            sum(
                item.component == "cold-comprehension"
                for item in ledger.events
            ),
            1,
        )
        self.assertEqual(ledger.observed_model_total_tokens, 48)
        self.assertFalse(ledger.provider_authenticity_verified)
        self.assertFalse(ledger.claim_eligible)
        self.assertFalse(ledger.goal_total_complete)
        setup_events = {
            item.component: item
            for item in ledger.events
            if item.phase == "setup"
        }
        self.assertEqual(
            set(setup_events),
            {"cold-comprehension", "local-setup"},
        )
        self.assertNotEqual(
            setup_events["cold-comprehension"].artifact_binding_sha256,
            setup_events["local-setup"].artifact_binding_sha256,
        )
        field_names = tuple(item.name for item in fields(type(execution)))
        self.assertEqual(
            field_names[12:15],
            (
                "provider_authenticity_verified",
                "eligible_for_claim",
                "goal_total_complete",
            ),
        )
        self.assertEqual(field_names[15], "observed_ledger")
        judge_index = next(
            index
            for index, item in enumerate(ledger.events)
            if item.component == "local-judge"
        )
        mutated_events = list(ledger.events)
        mutated_events[judge_index] = replace(
            mutated_events[judge_index],
            total_tokens=mutated_events[judge_index].total_tokens + 1,
        )
        with self.assertRaisesRegex(
            ComprehensionError,
            "exact runtime merge",
        ):
            replace(
                execution,
                observed_ledger=replace(
                    ledger,
                    events=tuple(mutated_events),
                ),
            )

    def test_failed_comprehension_blocks_prepare_compiler_and_receiver(self) -> None:
        def wrong_semantics(challenge):
            value = strict_json_loads(exact_response(challenge))
            value["preservation"]["failure_outcome_status"] = "succeeded"
            return good_reply(challenge, text=canonical_json(value))

        comprehension_adapter = ScriptedAdapter(wrong_semantics)
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "must-not-run", 10)
        )
        with mock.patch.object(
            comprehension_module,
            "prepare_message",
            wraps=comprehension_module.prepare_message,
        ) as prepare_spy:
            preparation = prepare_message_with_cold_comprehension(
                "This source must never reach the sender compiler. " * 800,
                self.capsule,
                comprehension_adapter,
                char_count,
                receiver_binding=RECEIVER_BINDING,
                task_context=TASK_CONTEXT,
                forecasts=complete_forecasts(),
                comprehension_maximum_total_tokens=100,
                utility_evidence={
                    "action-state": passing_evidence(
                        capsule_sha256=self.capsule.sha256
                    )
                },
                compiler=compiler,
                fidelity_verifier=verify_fidelity,
                utility_evidence_verifier=verify_utility,
                policy=action_policy(receiver_total_token_ceiling=100_000),
            )

        self.assertEqual(comprehension_adapter.calls, 1)
        self.assertEqual(prepare_spy.call_count, 1)
        self.assertEqual(compiler.calls, 0)
        self.assertEqual(preparation.status, "blocked")
        self.assertEqual(preparation.failure, "response-semantic-mismatch")
        self.assertIsNone(preparation.prepared)
        self.assertIsNone(preparation.receiver_capabilities)
        self.assertEqual(preparation.sender_compiler_calls, 0)
        self.assertEqual(preparation.receiver_calls, 0)
        self.assertEqual(preparation.comprehension_model_id, "unfamiliar-model-a")
        self.assertEqual(preparation.comprehension_total_tokens, 30)
        self.assertEqual(
            preparation.comprehension_challenge_sha256,
            comprehension_adapter.challenges[0].challenge_sha256,
        )
        self.assertIsNone(preparation.comprehension_evidence_sha256)

        receiver_adapter = FakeReceiverAdapter()
        execution = execute_cold_start_preparation(
            preparation,
            receiver_adapter,
            output_validator=validate_output,
        )
        self.assertEqual(execution.status, "blocked")
        self.assertEqual(
            execution.failure,
            "response-semantic-mismatch",
        )
        self.assertIsNone(execution.execution)
        self.assertEqual(receiver_adapter.calls, 0)
        self.assertEqual(execution.sender_compiler_calls, 0)
        self.assertEqual(execution.receiver_calls, 0)
        self.assertEqual(
            execution.observed_comprehension_plus_runtime_tokens,
            30,
        )
        self.assertFalse(execution.goal_total_complete)

    def test_short_baseline_skips_bootstrap_and_sender_compiler(self) -> None:
        comprehension_adapter = ScriptedAdapter(
            RuntimeError("bootstrap-must-not-run")
        )
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "must-not-run", 10)
        )
        preparation = prepare_message_with_cold_comprehension(
            "Short unfamiliar message.",
            self.capsule,
            comprehension_adapter,
            char_count,
            receiver_binding=RECEIVER_BINDING,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            comprehension_maximum_total_tokens=100,
            utility_evidence={
                "action-state": passing_evidence(
                    capsule_sha256=self.capsule.sha256
                )
            },
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            utility_evidence_verifier=verify_utility,
            policy=action_policy(receiver_total_token_ceiling=100_000),
        )
        self.assertEqual(comprehension_adapter.calls, 0)
        self.assertEqual(compiler.calls, 0)
        self.assertEqual(preparation.status, "prepared")
        self.assertEqual(
            preparation.bootstrap_decision,
            "skipped-action-not-forecast-to-win",
        )
        self.assertEqual(preparation.comprehension_calls, 0)
        self.assertIsNone(preparation.comprehension)
        self.assertIsNone(preparation.receiver_capabilities)
        self.assertIsNone(preparation.comprehension_total_tokens)
        assert preparation.prepared is not None
        self.assertIn(preparation.prepared.route.selected_mode, {"raw", "json"})

        receiver_adapter = FakeReceiverAdapter(receiver_reply())
        execution = execute_cold_start_preparation(
            preparation,
            receiver_adapter,
            output_validator=validate_output,
        )
        self.assertEqual(execution.status, "executed")
        self.assertEqual(receiver_adapter.calls, 1)
        self.assertEqual(execution.comprehension_calls, 0)
        self.assertEqual(execution.sender_compiler_calls, 0)
        self.assertEqual(
            execution.observed_comprehension_plus_runtime_tokens,
            5,
        )
        self.assertTrue(execution.receiver_binding_verified)

    def test_verified_silence_skips_bootstrap_and_receiver(self) -> None:
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
        comprehension_adapter = ScriptedAdapter(
            RuntimeError("bootstrap-must-not-run")
        )
        preparation = prepare_message_with_cold_comprehension(
            source,
            self.capsule,
            comprehension_adapter,
            char_count,
            receiver_binding=RECEIVER_BINDING,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            comprehension_maximum_total_tokens=100,
            utility_evidence={
                "silence": passing_evidence(
                    "cold-preflight-silence",
                    route_mode="silence",
                    capsule_sha256=self.capsule.sha256,
                )
            },
            utility_evidence_verifier=verify_utility,
            silence_proof=proof,
            silence_verifier=verify_bound_artifact,
        )
        self.assertEqual(comprehension_adapter.calls, 0)
        self.assertEqual(preparation.bootstrap_decision, "skipped-silence")
        self.assertEqual(preparation.comprehension_calls, 0)
        assert preparation.prepared is not None
        self.assertEqual(preparation.prepared.route.selected_mode, "silence")

        receiver_adapter = FakeReceiverAdapter()
        execution = execute_cold_start_preparation(
            preparation,
            receiver_adapter,
            output_validator=validate_output,
        )
        self.assertEqual(execution.status, "executed")
        self.assertEqual(receiver_adapter.calls, 0)
        self.assertEqual(execution.receiver_calls, 0)
        self.assertEqual(
            execution.observed_comprehension_plus_runtime_tokens,
            0,
        )
        self.assertTrue(execution.safely_completed)

    def test_missing_declared_binding_skips_even_when_action_may_win(self) -> None:
        comprehension_adapter = ScriptedAdapter(
            RuntimeError("bootstrap-must-not-run-without-binding")
        )
        compiler = FakeCompiler(
            ModelReply(sender_output(self.state), "must-not-run", 10)
        )
        preparation = prepare_message_with_cold_comprehension(
            "Verify artifact seven without external effects. " * 800,
            self.capsule,
            comprehension_adapter,
            char_count,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            comprehension_maximum_total_tokens=100,
            utility_evidence={
                "action-state": passing_evidence(
                    capsule_sha256=self.capsule.sha256
                )
            },
            compiler=compiler,
            fidelity_verifier=verify_fidelity,
            utility_evidence_verifier=verify_utility,
            policy=action_policy(receiver_total_token_ceiling=100_000),
        )
        self.assertEqual(comprehension_adapter.calls, 0)
        self.assertEqual(compiler.calls, 0)
        self.assertEqual(
            preparation.bootstrap_decision,
            "skipped-receiver-binding-missing",
        )
        self.assertIsNotNone(preparation.preflight_action_conservative_tokens)
        self.assertEqual(preparation.comprehension_calls, 0)
        assert preparation.prepared is not None
        self.assertIn(preparation.prepared.route.selected_mode, {"raw", "json"})

    def test_receiver_declared_binding_and_reply_model_mismatch_fail_closed(self) -> None:
        source = "Verify artifact seven without external effects. " * 800
        preparation = prepare_message_with_cold_comprehension(
            source,
            self.capsule,
            ScriptedAdapter(lambda challenge: good_reply(challenge)),
            char_count,
            receiver_binding=RECEIVER_BINDING,
            task_context=TASK_CONTEXT,
            forecasts=complete_forecasts(),
            comprehension_maximum_total_tokens=100,
            utility_evidence={
                "action-state": passing_evidence(
                    capsule_sha256=self.capsule.sha256
                )
            },
            compiler=FakeCompiler(
                ModelReply(sender_output(self.state), "sender-model-a", 10)
            ),
            fidelity_verifier=verify_fidelity,
            utility_evidence_verifier=verify_utility,
            policy=action_policy(receiver_total_token_ceiling=100_000),
        )
        self.assertEqual(preparation.bootstrap_decision, "attempted")
        assert preparation.prepared is not None
        self.assertEqual(preparation.prepared.route.selected_mode, "action-state")

        precheck_adapter = FakeReceiverAdapter(
            replace(receiver_reply(), model_id=RECEIVER_BINDING.model_id)
        )
        precheck_adapter.receiver_binding = ReceiverModelBinding(
            model_id=RECEIVER_BINDING.model_id,
            settings_sha256="sha256:" + "8" * 64,
        )
        precheck = execute_cold_start_preparation(
            preparation,
            precheck_adapter,
            output_validator=validate_output,
        )
        self.assertEqual(precheck.status, "receiver-binding-blocked")
        self.assertEqual(
            precheck.failure,
            "receiver-declared-binding-mismatch",
        )
        self.assertEqual(precheck_adapter.calls, 0)
        self.assertFalse(precheck.receiver_binding_verified)
        self.assertFalse(precheck.safely_completed)

        reply_mismatch_adapter = FakeReceiverAdapter(receiver_reply())
        reply_mismatch_adapter.receiver_binding = RECEIVER_BINDING
        mismatch = execute_cold_start_preparation(
            preparation,
            reply_mismatch_adapter,
            output_validator=validate_output,
        )
        self.assertEqual(mismatch.status, "receiver-binding-failed")
        self.assertEqual(mismatch.failure, "receiver-model-id-mismatch")
        self.assertEqual(reply_mismatch_adapter.calls, 1)
        self.assertFalse(mismatch.receiver_binding_verified)
        self.assertFalse(mismatch.safely_completed)
        self.assertTrue(mismatch.output_discard_required)
        self.assertFalse(mismatch.eligible_for_live_answer)
        assert mismatch.execution is not None
        self.assertTrue(mismatch.execution.safely_completed)
        self.assertFalse(mismatch.provider_authenticity_verified)
        self.assertFalse(mismatch.eligible_for_claim)
        self.assertFalse(mismatch.goal_total_complete)


if __name__ == "__main__":
    import unittest

    unittest.main()
