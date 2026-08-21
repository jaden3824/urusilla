from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import inspect
import unittest

from competitive_eval.canonical import canonical_json
from competitive_eval.errors import IntegrityError, ManifestError
from competitive_eval.external_replay import (
    ExternalResponseStore,
    build_execution_profile,
    build_external_response_bundle,
    build_external_response_record,
)
from competitive_eval.hybrid_external_replay import (
    HybridExternalReplayCapture,
    HybridReceiverExternalCall,
    build_hybrid_receiver_external_call,
    build_pending_hybrid_receiver_call,
    expected_receiver_settings_sha256,
    resolve_hybrid_receiver_external_capture,
)
import competitive_eval.hybrid_external_replay as hybrid_external_replay
from competitive_eval.protocol import CallRequest
from urusilla_hybrid_runtime.comprehension import ReceiverModelBinding
from urusilla_hybrid_runtime.canonical import sha256_text
from urusilla_hybrid_runtime.receiver import build_action_state_request
from urusilla_hybrid_runtime.records import PublicActionState, load_capsule
from urusilla_hybrid_runtime.task_context import PublicTaskContext


MODEL_FAMILY = "T"
MODEL_ID = "external-test-model-001"
CAPSULE_COMPREHENSION_EVIDENCE = "sha256:" + "c" * 64
CAPSULE_COMPREHENSION_VERIFIER = "sha256:" + "d" * 64
TASK_COMPREHENSION_EVIDENCE = "sha256:" + "e" * 64
TASK_COMPREHENSION_VERIFIER = "sha256:" + "f" * 64
OUTPUT_VALIDATOR = "sha256:" + "7" * 64


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def task_context() -> PublicTaskContext:
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
            "task_id": "task.verify-artifact",
            "objective": "Verify one bounded artifact without effects.",
            "output_contract": {
                "media_type": "text/plain",
                "validator_sha256": OUTPUT_VALIDATOR,
                "description": "Return one locally validated status string.",
            },
            "allowed_acts": ["resolve"],
            "outcome_contract": {
                "statuses": ["failed"],
                "value": {
                    "name": "value",
                    "type": "string",
                    "nullable": True,
                    "required": True,
                    "unit": None,
                    "meaning": "Public result, or null when unavailable.",
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
                    [argument("artifact_id", "Stable artifact identifier.")],
                ),
                predicate(
                    "test.passed",
                    "The named test passed when the atom is not negated.",
                    [argument("test_unit", "Stable test-unit identifier.")],
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


TASK_CONTEXT = task_context()


def binding() -> ReceiverModelBinding:
    return ReceiverModelBinding(
        model_id=MODEL_ID,
        settings_sha256=expected_receiver_settings_sha256(
            model_family_code=MODEL_FAMILY,
            model_id=MODEL_ID,
        ),
    )


def cold_request(*, maximum_total_tokens: int = 100):
    capsule = load_capsule()
    state = PublicActionState.from_object(
        capsule.to_object()["examples"]["positive"]
    )
    return build_action_state_request(
        state,
        capsule,
        TASK_CONTEXT,
        task_context_cached_in_same_model_context=False,
        task_context_id=None,
        task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
        task_comprehension_verifier_sha256=TASK_COMPREHENSION_VERIFIER,
        capsule_cached_in_same_model_context=False,
        capsule_context_id=None,
        comprehension_evidence_sha256=CAPSULE_COMPREHENSION_EVIDENCE,
        capsule_comprehension_verifier_sha256=CAPSULE_COMPREHENSION_VERIFIER,
        maximum_total_tokens=maximum_total_tokens,
    )


def cached_request(*, maximum_total_tokens: int = 100):
    capsule = load_capsule()
    state = PublicActionState.from_object(
        capsule.to_object()["examples"]["positive"]
    )
    return build_action_state_request(
        state,
        capsule,
        TASK_CONTEXT,
        task_context_cached_in_same_model_context=True,
        task_context_id="ctx-task-external-1",
        task_comprehension_evidence_sha256=TASK_COMPREHENSION_EVIDENCE,
        task_comprehension_verifier_sha256=TASK_COMPREHENSION_VERIFIER,
        capsule_cached_in_same_model_context=True,
        capsule_context_id="ctx-capsule-external-1",
        comprehension_evidence_sha256=CAPSULE_COMPREHENSION_EVIDENCE,
        capsule_comprehension_verifier_sha256=CAPSULE_COMPREHENSION_VERIFIER,
        maximum_total_tokens=maximum_total_tokens,
    )


def profile(*, provider_id: str = "provider.test") -> dict:
    return build_execution_profile(
        provider_id=provider_id,
        api_id="responses/v1",
        normalizer_id="test-normalizer-v1",
        normalizer_sha256=digest("normalizer"),
    )


def plan_for(request, *, execution_profile: dict | None = None):
    selected_profile = execution_profile or profile()
    return build_hybrid_receiver_external_call(
        request,
        binding(),
        episode_id=digest("hybrid-episode"),
        turn_index=0,
        attempt_index=0,
        agent="B",
        model_family_code=MODEL_FAMILY,
        execution_profile_sha256=selected_profile["profile_sha256"],
    )


def usage(
    *,
    input_tokens: int = 11,
    output_tokens: int = 5,
    reasoning_tokens: int | None = None,
    reasoning_accounting: str = "not-reported",
    total_tokens: int = 16,
) -> dict:
    return {
        "status": "complete",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens_subset": reasoning_tokens,
        "reasoning_accounting": reasoning_accounting,
        "actual_billed_usd": None,
        "unclassified_usage_json": None,
    }


def unavailable_usage() -> dict:
    return {
        "status": "unavailable",
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens_subset": None,
        "reasoning_accounting": "not-reported",
        "actual_billed_usd": None,
        "unclassified_usage_json": None,
    }


def observation(call_request, *, available: bool = True) -> dict:
    if not available:
        return {
            "source_kind": "unavailable",
            "provider_id": "provider.test",
            "request_id": None,
            "response_id": None,
            "resolved_model_id": None,
            "effective_settings_status": "unknown",
            "raw_receipt_utf8": None,
            "raw_receipt_sha256": None,
        }
    raw = canonical_json(
        {
            "id": "response-hybrid-1",
            "model": MODEL_ID,
            "usage": {"input": 11, "output": 5, "total": 16},
        }
    )
    return {
        "source_kind": "provider",
        "provider_id": "provider.test",
        "request_id": "request-hybrid-1",
        "response_id": "response-hybrid-1",
        "resolved_model_id": call_request.value["model_ref"]["logical_model_id"],
        "effective_settings_status": "confirmed-exact",
        "raw_receipt_utf8": raw,
        "raw_receipt_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


def store_for(
    plan,
    *,
    response_status: str = "completed",
    output_text: str | None = '{"ok":true}',
    captured_usage: dict | None = None,
    provider_available: bool = True,
    execution_profile: dict | None = None,
) -> ExternalResponseStore:
    selected_profile = execution_profile or profile()
    record = build_external_response_record(
        sequence=0,
        request=plan.call_request,
        execution_profile=selected_profile,
        status=response_status,
        output_text=output_text,
        provider_observation=observation(
            plan.call_request,
            available=provider_available,
        ),
        usage=captured_usage or usage(),
        timing={"model_ns": 1234 if provider_available else None},
    )
    bundle = build_external_response_bundle(
        run_id=digest("run"),
        run_manifest_sha256=digest("run-manifest"),
        episode_sequence_sha256=digest("episode-sequence"),
        operator_id="operator.test",
        capture_implementation_sha256=digest("capture"),
        operator_attestation_sha256=None,
        execution_profile=selected_profile,
        records=[record],
    )
    return ExternalResponseStore.from_object(bundle)


def empty_store(*, execution_profile: dict | None = None) -> ExternalResponseStore:
    selected_profile = execution_profile or profile()
    bundle = build_external_response_bundle(
        run_id=digest("run"),
        run_manifest_sha256=digest("run-manifest"),
        episode_sequence_sha256=digest("episode-sequence"),
        operator_id="operator.test",
        capture_implementation_sha256=digest("capture"),
        operator_attestation_sha256=None,
        execution_profile=selected_profile,
        records=[],
    )
    return ExternalResponseStore.from_object(bundle)


class HybridExternalReplayTests(unittest.TestCase):
    def test_cold_pending_has_exact_submitted_role_contents(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        messages = plan.call_request.value["messages"]
        self.assertEqual(
            messages,
            [
                {"role": "system", "content": request.base_system_text},
                {"role": "user", "content": request.user_data_text},
            ],
        )
        self.assertIn(request.task_context_text, messages[1]["content"])
        self.assertIn(request.capsule_text, messages[1]["content"])
        self.assertIn(request.payload_text, messages[1]["content"])
        self.assertEqual(
            plan.projection["task_comprehension_evidence_sha256"],
            TASK_COMPREHENSION_EVIDENCE,
        )
        self.assertEqual(
            plan.projection["capsule_comprehension_verifier_sha256"],
            CAPSULE_COMPREHENSION_VERIFIER,
        )
        self.assertIsNone(plan.projection["task_context_id"])
        self.assertIsNone(plan.projection["capsule_context_id"])

        pending = build_pending_hybrid_receiver_call(
            request,
            binding(),
            plan,
            empty_store(),
        )
        self.assertFalse(pending["claim_eligible"])
        self.assertFalse(pending["delivery_eligible"])
        self.assertFalse(pending["provider_role_mapping_reverified"])
        self.assertFalse(
            pending["budget_boundary"]["precall_total_ceiling_enforced"]
        )
        self.assertFalse(
            pending["budget_boundary"]["execution_authorized_by_this_artifact"]
        )
        self.assertEqual(
            pending["external_call"]["call_request"],
            plan.call_request.value,
        )

    def test_host_only_proof_change_changes_projection_and_call_identity(self) -> None:
        request = cold_request()
        changed = replace(
            request,
            comprehension_evidence_sha256="sha256:" + "1" * 64,
        )
        self.assertEqual(request.model_visible_text, changed.model_visible_text)
        first = plan_for(request)
        second = plan_for(changed)
        self.assertNotEqual(first.projection_sha256, second.projection_sha256)
        self.assertNotEqual(first.call_request.call_id, second.call_request.call_id)

    def test_capture_keeps_provenance_and_is_not_runtime_evidence(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        captured_usage = usage(
            input_tokens=11,
            output_tokens=5,
            reasoning_tokens=2,
            reasoning_accounting="separately-reported",
            total_tokens=18,
        )
        capture = resolve_hybrid_receiver_external_capture(
            request,
            binding(),
            plan,
            store_for(plan, captured_usage=captured_usage),
        )
        self.assertIsInstance(capture, HybridExternalReplayCapture)
        self.assertEqual(capture.output_text, '{"ok":true}')
        self.assertEqual(capture.resolved_model_id, MODEL_ID)
        self.assertEqual(capture.usage["input_tokens"], 11)
        self.assertEqual(capture.usage["output_tokens"], 5)
        self.assertEqual(capture.usage["reasoning_tokens_subset"], 2)
        self.assertEqual(capture.usage["total_tokens"], 18)
        self.assertFalse(capture.provider_authenticated)
        self.assertFalse(capture.operator_independence_verified)
        self.assertFalse(capture.precall_total_ceiling_enforced)
        self.assertFalse(capture.delivery_eligible)
        self.assertFalse(capture.full_task_ledger_complete)
        self.assertFalse(capture.claim_eligible)
        self.assertGreater(len(capture.claim_blockers), 0)

    def test_unavailable_usage_fails_and_is_never_coerced_to_zero(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        with self.assertRaisesRegex(IntegrityError, "core-usage-capture-incomplete"):
            resolve_hybrid_receiver_external_capture(
                request,
                binding(),
                plan,
                store_for(
                    plan,
                    captured_usage=unavailable_usage(),
                    provider_available=False,
                ),
            )

    def test_noncompleted_response_is_not_a_capture(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        with self.assertRaisesRegex(IntegrityError, "did not complete"):
            resolve_hybrid_receiver_external_capture(
                request,
                binding(),
                plan,
                store_for(plan, response_status="refused", output_text=None),
            )

    def test_over_ceiling_usage_is_observed_not_called_enforced(self) -> None:
        request = cold_request(maximum_total_tokens=20)
        plan = plan_for(request)
        capture = resolve_hybrid_receiver_external_capture(
            request,
            binding(),
            plan,
            store_for(
                plan,
                captured_usage=usage(
                    input_tokens=18,
                    output_tokens=5,
                    total_tokens=23,
                ),
            ),
        )
        self.assertFalse(capture.observed_within_host_total_ceiling)
        self.assertFalse(capture.precall_total_ceiling_enforced)
        self.assertFalse(capture.delivery_eligible)

    def test_wrong_settings_binding_fails_before_pending_export(self) -> None:
        request = cold_request()
        wrong = ReceiverModelBinding(
            model_id=MODEL_ID,
            settings_sha256="sha256:" + "f" * 64,
        )
        with self.assertRaisesRegex(IntegrityError, "settings differ"):
            build_hybrid_receiver_external_call(
                request,
                wrong,
                episode_id=digest("hybrid-episode"),
                turn_index=0,
                attempt_index=0,
                agent="B",
                model_family_code=MODEL_FAMILY,
                execution_profile_sha256=profile()["profile_sha256"],
            )

    def test_cached_request_is_rejected_without_provider_context_binding(self) -> None:
        with self.assertRaisesRegex(ManifestError, "requires cold task context"):
            plan_for(cached_request())

    def test_execution_profile_mismatch_is_rejected(self) -> None:
        request = cold_request()
        first_profile = profile()
        other_profile = profile(provider_id="provider.other")
        plan = plan_for(request, execution_profile=first_profile)
        with self.assertRaisesRegex(IntegrityError, "profile differs"):
            build_pending_hybrid_receiver_call(
                request,
                binding(),
                plan,
                empty_store(execution_profile=other_profile),
            )

    def test_existing_response_cannot_be_exported_as_pending_again(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        store = store_for(plan)
        before = store.coverage()
        with self.assertRaisesRegex(IntegrityError, "already exists"):
            build_pending_hybrid_receiver_call(
                request,
                binding(),
                plan,
                store,
            )
        self.assertEqual(store.coverage(), before)

    def test_direct_plan_cannot_lie_cached_request_into_cold_export(self) -> None:
        cold = cold_request()
        cached = cached_request()
        original = plan_for(cold)
        projection = dict(original.projection)
        messages = [
            {"role": "system", "content": cached.base_system_text},
            {"role": "user", "content": cached.user_data_text},
        ]
        projection["direct_receiver_binding_sha256"] = cached.binding_sha256
        projection["runtime_transcript_sha256"] = sha256_text(
            cached.model_visible_text
        )
        projection["provider_neutral_messages_sha256"] = hashlib.sha256(
            canonical_json(messages).encode()
        ).hexdigest()
        projection_sha256 = hashlib.sha256(
            canonical_json(projection).encode()
        ).hexdigest()
        forged_call = CallRequest.build(
            episode_id=digest("hybrid-episode"),
            turn_index=0,
            attempt_index=0,
            purpose="runtime",
            agent="B",
            model_code=MODEL_FAMILY,
            logical_model_id=MODEL_ID,
            arm="urusilla_hybrid_direct_receiver_v1",
            messages=messages,
            mock_scenario_key=projection_sha256,
        )
        forged_plan = HybridReceiverExternalCall(
            _projection_json=canonical_json(projection),
            projection_sha256=projection_sha256,
            _call_request_json=forged_call.to_json(),
        )
        with self.assertRaisesRegex(ManifestError, "requires cold task context"):
            build_pending_hybrid_receiver_call(
                cached,
                binding(),
                forged_plan,
                empty_store(),
            )

    def test_plan_returns_defensive_revalidated_copies(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        projection = plan.projection
        projection["direct_receiver_binding_sha256"] = "sha256:" + "0" * 64
        exported_call = plan.call_request
        exported_call.value["messages"][1]["content"] = "changed"
        self.assertEqual(
            plan.projection["direct_receiver_binding_sha256"],
            request.binding_sha256,
        )
        self.assertEqual(
            plan.call_request.value["messages"][1]["content"],
            request.user_data_text,
        )

    def test_direct_constructor_rejects_wrong_submitted_roles(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        wrong_call = CallRequest.build(
            episode_id=digest("hybrid-episode"),
            turn_index=0,
            attempt_index=0,
            purpose="runtime",
            agent="B",
            model_code=MODEL_FAMILY,
            logical_model_id=MODEL_ID,
            arm="urusilla_hybrid_direct_receiver_v1",
            messages=[
                {"role": "system", "content": request.base_system_text},
                {"role": "user", "content": "wrong payload"},
            ],
            mock_scenario_key=plan.projection_sha256,
        )
        with self.assertRaisesRegex(IntegrityError, "transcript differs"):
            HybridReceiverExternalCall(
                _projection_json=canonical_json(plan.projection),
                projection_sha256=plan.projection_sha256,
                _call_request_json=wrong_call.to_json(),
            )

    def test_direct_constructor_rejects_format_repair_purpose(self) -> None:
        request = cold_request()
        plan = plan_for(request)
        repair_call = CallRequest.build(
            episode_id=digest("hybrid-episode"),
            turn_index=0,
            attempt_index=1,
            purpose="format_repair",
            agent="B",
            model_code=MODEL_FAMILY,
            logical_model_id=MODEL_ID,
            arm="urusilla_hybrid_direct_receiver_v1",
            messages=[
                {"role": "system", "content": request.base_system_text},
                {"role": "user", "content": request.user_data_text},
            ],
            mock_scenario_key=plan.projection_sha256,
        )
        with self.assertRaisesRegex(IntegrityError, "purpose differs"):
            HybridReceiverExternalCall(
                _projection_json=canonical_json(plan.projection),
                projection_sha256=plan.projection_sha256,
                _call_request_json=repair_call.to_json(),
            )

    def test_adapter_module_has_no_network_or_live_receiver_adapter(self) -> None:
        source = inspect.getsource(hybrid_external_replay)
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertTrue(
            imports.isdisjoint(
                {
                    "aiohttp",
                    "boto3",
                    "google",
                    "httpx",
                    "openai",
                    "os",
                    "requests",
                    "socket",
                    "subprocess",
                    "urllib",
                }
            )
        )
        self.assertNotIn("getenv", source)
        self.assertNotIn("ReceiverModelReply", source)
        self.assertNotIn("execute_receiver", source)


if __name__ == "__main__":
    unittest.main()
