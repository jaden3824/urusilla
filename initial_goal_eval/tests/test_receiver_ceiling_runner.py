from __future__ import annotations

from dataclasses import replace
import json
from unittest import TestCase
from unittest.mock import patch

import initial_goal_eval.receiver_ceiling_runner as receiver_ceiling_runner
from initial_goal_eval.content_bound_compiler_v1 import (
    build_content_bound_feasibility_screen,
)
from initial_goal_eval.matched_session_pilot import (
    ComprehensionProviderResult,
    NormalizedProviderUsage,
    ProviderCallCapture,
    ReceiverProviderResult,
)
from initial_goal_eval.receiver_ceiling_runner import (
    PerfectSenderTaskFixture,
    ReceiverCeilingError,
    ReceiverCeilingTaskResult,
    SyntheticReceiverCeilingAuthorization,
    receiver_ceiling_experiment_binding_sha256,
    run_perfect_sender_matched_session,
)
from initial_goal_eval.tests.test_content_bound_compiler_v1 import (
    _make_case as _make_content_bound_case,
)
from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.receiver import ReceiverModelReply
from urusilla_hybrid_runtime.records import PublicActionState, load_capsule
from urusilla_hybrid_runtime.tests.test_comprehension import (
    RECEIVER_BINDING,
    good_reply,
)
from urusilla_hybrid_runtime.tests.test_hybrid_runtime import TASK_CONTEXT


MAX_COMPREHENSION = 1_000
MAX_RECEIVER = 100
ARM_ORDER = ("action-state", "raw", "json")


def _capture(
    *,
    context_id: str,
    request_id: str,
    response_id: str | None,
    parent_response_id: str | None,
    request_sha256: str,
    response_sha256: str | None,
    usage: NormalizedProviderUsage,
    terminal_status: str = "completed",
    retry_count: int = 0,
    external_effects_performed: bool = False,
    receiver_binding=RECEIVER_BINDING,
) -> ProviderCallCapture:
    return ProviderCallCapture(
        provider_id="offline-fake-provider",
        context_id=context_id,
        request_id=request_id,
        response_id=response_id,
        parent_response_id=parent_response_id,
        request_content_sha256=request_sha256,
        response_content_sha256=response_sha256,
        resolved_model_id=receiver_binding.model_id,
        model_settings_sha256=receiver_binding.settings_sha256,
        raw_receipt_text=canonical_json(
            {
                "context": context_id,
                "request": request_id,
                "response": response_id,
                "usage": usage.to_object(),
            }
        ),
        usage=usage,
        terminal_status=terminal_status,
        retry_count=retry_count,
        external_effects_performed=external_effects_performed,
    )


def _reply(text: str, receiver_binding=RECEIVER_BINDING) -> ReceiverModelReply:
    return ReceiverModelReply(
        text=text,
        model_id=receiver_binding.model_id,
        input_tokens=3,
        output_tokens=2,
        reasoning_tokens=None,
        reasoning_accounting="not-reported",
        provider_total_tokens=5,
    )


def _fixtures() -> tuple[PerfectSenderTaskFixture, ...]:
    capsule = load_capsule()
    values = []
    for index in (1, 2):
        value = capsule.to_object()["examples"]["positive"]
        # ``to_object`` returns a new JSON value each time.
        value["goal"]["a"] = [f"artifact-{index}"]
        value["state"][0]["a"] = [f"unit-{index}"]
        state = PublicActionState.from_object(value)
        values.append(
            PerfectSenderTaskFixture.from_state(
                item_id=f"item-{index}",
                task_context=TASK_CONTEXT,
                action_state=state,
                expected_output_text="valid",
            )
        )
    return tuple(values)


def _authorization(
    fixtures: tuple[PerfectSenderTaskFixture, ...],
    *,
    selected_length: int | None = 2,
    permitted: bool = True,
    receiver_binding=RECEIVER_BINDING,
) -> SyntheticReceiverCeilingAuthorization:
    digest = receiver_ceiling_experiment_binding_sha256(
        capsule=load_capsule(),
        task_context=TASK_CONTEXT,
        receiver_binding=receiver_binding,
        fixtures=fixtures,
        arm_order=ARM_ORDER,
        maximum_comprehension_tokens=MAX_COMPREHENSION,
        maximum_receiver_tokens=MAX_RECEIVER,
    )
    return SyntheticReceiverCeilingAuthorization.from_values(
        experiment_binding_sha256=digest,
        selected_session_length=selected_length,
        synthetic_fixture_screen_passed=permitted,
        all_retained_cells_not_disproven=permitted,
        worst_cell_residual_positive=permitted,
    )


class FakeOfflineProvider:
    offline_synthetic = True

    def __init__(
        self,
        fixtures: tuple[PerfectSenderTaskFixture, ...],
        *,
        comprehension_failure: bool = False,
        comprehension_fault: str | None = None,
        baseline_fault: str | None = None,
        hot_fault: str | None = None,
        receiver_binding=RECEIVER_BINDING,
    ) -> None:
        self.output_by_payload = {}
        for item in fixtures:
            for payload in (
                item.raw_concise_text,
                item.ordinary_json_text,
                item.action_state.canonical_text,
            ):
                self.output_by_payload[payload] = item.expected_output_text
        self.comprehension_failure = comprehension_failure
        self.comprehension_fault = comprehension_fault
        self.baseline_fault = baseline_fault
        self.hot_fault = hot_fault
        self.receiver_binding = receiver_binding
        self.comprehension_calls = []
        self.receiver_calls = []
        self.session_calls = []
        self.root_counter = 0
        self.hot_counter = 0
        self.cold_context = "ctx-action-state"
        self.last_response_id = "resp-comprehension"

    @property
    def call_count(self) -> int:
        return (
            len(self.comprehension_calls)
            + len(self.receiver_calls)
            + len(self.session_calls)
        )

    def complete_comprehension(self, challenge):
        self.comprehension_calls.append(challenge)
        if self.comprehension_fault == "raise":
            raise RuntimeError("synthetic comprehension callback fault")
        if self.comprehension_fault == "base":
            raise SystemExit("synthetic comprehension interrupt")
        if self.comprehension_fault == "long-name":
            error_type = type("E" * 300, (RuntimeError,), {})
            raise error_type("synthetic long-name callback fault")
        if self.comprehension_fault == "mutate-then-raise":
            object.__setattr__(
                challenge,
                "model_visible_text",
                "x" * (receiver_ceiling_runner._MAX_JOURNAL_REQUEST_BYTES + 1),
            )
            raise RuntimeError("synthetic request mutation")
        if self.comprehension_fault == "unattachable-base":
            class UnattachableAbort(BaseException):
                def __setattr__(self, name, value):
                    raise TypeError("attributes prohibited")

            raise UnattachableAbort("synthetic unattachable interrupt")
        if self.comprehension_fault == "silent-base":
            class SilentAbort(BaseException):
                def __setattr__(self, name, value):
                    return None

            raise SilentAbort("synthetic silent interrupt")
        reply = good_reply(challenge)
        if self.comprehension_failure:
            reply = replace(reply, text="{}")
        usage = NormalizedProviderUsage.from_comprehension_reply(reply)
        return ComprehensionProviderResult(
            reply=reply,
            capture=_capture(
                context_id=self.cold_context,
                request_id="req-comprehension",
                response_id=self.last_response_id,
                parent_response_id=None,
                request_sha256=challenge.model_visible_sha256,
                response_sha256=sha256_text(reply.text),
                usage=usage,
                receiver_binding=self.receiver_binding,
            ),
            raw_provider_handle=self,
            context_epoch=(
                "bad epoch with spaces"
                if self.comprehension_fault == "bad-epoch"
                else "offline-epoch-1"
            ),
            session_nonce="a" * 64,
        )

    def complete_receiver(self, arm_id, request):
        self.receiver_calls.append((arm_id, request))
        if self.baseline_fault == "raise":
            raise RuntimeError("synthetic baseline callback fault")
        if self.baseline_fault == "base":
            raise SystemExit("synthetic baseline interrupt")
        self.root_counter += 1
        output = (
            "x" * (receiver_ceiling_runner._MAX_JOURNAL_REQUEST_BYTES + 1)
            if self.baseline_fault == "oversize-reply"
            else self.output_by_payload[request.payload_text]
        )
        reply = _reply(output, self.receiver_binding)
        if self.baseline_fault == "wrong-reply-model":
            reply = replace(reply, model_id="different-model")
        usage = NormalizedProviderUsage.from_receiver_reply(reply)
        return ReceiverProviderResult(
            reply=reply,
            capture=_capture(
                context_id=f"ctx-root-{self.root_counter}",
                request_id=f"req-root-{self.root_counter}",
                response_id=f"resp-root-{self.root_counter}",
                parent_response_id=None,
                request_sha256=sha256_text(request.model_visible_text),
                response_sha256=sha256_text(reply.text),
                usage=usage,
                receiver_binding=self.receiver_binding,
            ),
        )

    def complete_session_turn(self, raw_provider_handle, call):
        self.session_calls.append((raw_provider_handle, call))
        self.hot_counter += 1
        if self.hot_fault == "raise":
            raise RuntimeError("synthetic hot callback fault")
        if self.hot_fault == "base":
            raise SystemExit("synthetic hot interrupt")
        parent = self.last_response_id
        response_id = f"resp-hot-{self.hot_counter}"
        if self.hot_fault == "reuse-response-id":
            response_id = self.last_response_id
        if self.hot_fault == "unknown-usage":
            usage = NormalizedProviderUsage(
                input_tokens=None,
                output_tokens=None,
                reasoning_tokens=None,
                reasoning_accounting="not-reported",
                provider_total_tokens=None,
            )
            return ReceiverProviderResult(
                reply=None,
                capture=_capture(
                    context_id=self.cold_context,
                    request_id=f"req-hot-{self.hot_counter}",
                    response_id=None,
                    parent_response_id=parent,
                    request_sha256=sha256_text(call.request_text),
                    response_sha256=None,
                    usage=usage,
                    terminal_status="failed",
                    receiver_binding=self.receiver_binding,
                ),
            )
        payload = call.request_text.removeprefix("PAYLOAD\n")
        reply = _reply(self.output_by_payload[payload], self.receiver_binding)
        usage = NormalizedProviderUsage.from_receiver_reply(reply)
        capture = _capture(
            context_id=self.cold_context,
            request_id=f"req-hot-{self.hot_counter}",
            response_id=response_id,
            parent_response_id=parent,
            request_sha256=sha256_text(call.request_text),
            response_sha256=sha256_text(reply.text),
            usage=usage,
            retry_count=1 if self.hot_fault == "retry" else 0,
            external_effects_performed=self.hot_fault == "effect",
            receiver_binding=self.receiver_binding,
        )
        self.last_response_id = response_id
        return ReceiverProviderResult(reply=reply, capture=capture)


def _run(
    provider: FakeOfflineProvider,
    fixtures: tuple[PerfectSenderTaskFixture, ...],
    authorization: SyntheticReceiverCeilingAuthorization | None = None,
    receiver_binding=None,
):
    binding = (
        provider.__dict__.get("receiver_binding", RECEIVER_BINDING)
        if receiver_binding is None
        else receiver_binding
    )
    return run_perfect_sender_matched_session(
        capsule=load_capsule(),
        task_context=TASK_CONTEXT,
        receiver_binding=binding,
        provider=provider,
        fixtures=fixtures,
        arm_order=ARM_ORDER,
        preflight=authorization
        or _authorization(fixtures, receiver_binding=binding),
        maximum_comprehension_tokens=MAX_COMPREHENSION,
        maximum_receiver_tokens=MAX_RECEIVER,
    )


def _rebuild_result(result, **changes):
    values = {
        "experiment_binding_sha256": result.experiment_binding_sha256,
        "experiment_manifest_text": result.experiment_manifest_text,
        "preflight_sha256": result.preflight_sha256,
        "preflight_text": result.preflight_text,
        "task_order": result.task_order,
        "arm_order": result.arm_order,
        "comprehension_passed": result.comprehension_passed,
        "comprehension_failure": result.comprehension_failure,
        "task_results": result.task_results,
        "journal": result.journal,
    }
    values.update(changes)
    return type(result)(
        **values,
        _factory_token=receiver_ceiling_runner._RUN_RESULT_FACTORY_TOKEN,
    )


class ReceiverCeilingRunnerTests(TestCase):
    def test_fixture_binds_three_distinct_deterministic_representations(self):
        fixture = _fixtures()[0]
        payloads = {
            fixture.raw_concise_text.encode(),
            fixture.ordinary_json_text.encode(),
            fixture.action_state.canonical_text.encode(),
        }
        self.assertEqual(len(payloads), 3)
        ordinary = json.loads(fixture.ordinary_json_text)
        self.assertNotIn("raw_text", ordinary)
        self.assertEqual(
            set(fixture.representation_binding_object),
            {
                "normative_sha256",
                "raw_sha256",
                "ordinary_json_sha256",
                "action_state_sha256",
            },
        )
        rebuilt = PerfectSenderTaskFixture.from_state(
            item_id=fixture.item_id,
            task_context=TASK_CONTEXT,
            action_state=fixture.action_state,
            expected_output_text=fixture.expected_output_text,
        )
        self.assertEqual(rebuilt, fixture)
        self.assertEqual(fixture.to_object()["perfect_sender_model_calls"], 0)

    def test_one_comprehension_then_n_exact_hot_calls_and_fresh_baselines(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures)
        result = _run(provider, fixtures)

        self.assertEqual(len(provider.comprehension_calls), 1)
        self.assertEqual(len(provider.session_calls), len(fixtures))
        self.assertEqual(len(provider.receiver_calls), 2 * len(fixtures))
        self.assertEqual(result.task_order, ("item-1", "item-2"))
        self.assertEqual(result.arm_order, ARM_ORDER)
        self.assertTrue(result.comprehension_passed)

        for (_, call), fixture in zip(provider.session_calls, fixtures):
            self.assertEqual(
                call.request_text,
                "PAYLOAD\n" + fixture.action_state.canonical_text,
            )
            self.assertNotIn("DECLARATIVE CAPSULE", call.request_text)
            self.assertNotIn("PUBLIC TASK CONTEXT", call.request_text)
            self.assertNotIn("decode", call.request_text.lower())

        hot_entries = [
            item for item in result.journal if item.arm == "action-state"
        ]
        self.assertEqual(
            {item.capture.context_id for item in hot_entries},
            {provider.cold_context},
        )
        self.assertEqual(
            [item.capture.parent_response_id for item in hot_entries],
            ["resp-comprehension", "resp-hot-1"],
        )
        baseline_entries = [
            item for item in result.journal if item.arm in {"raw", "json"}
        ]
        self.assertEqual(
            len({item.capture.context_id for item in baseline_entries}),
            2 * len(fixtures),
        )
        self.assertTrue(
            all(item.capture.parent_response_id is None for item in baseline_entries)
        )
        artifact = result.to_object()
        self.assertEqual(artifact["perfect_sender"]["model_calls"], 0)
        self.assertEqual(artifact["repair_calls"], 0)
        self.assertEqual(artifact["fallback_calls"], 0)
        self.assertFalse(artifact["claim_eligible"])
        self.assertFalse(artifact["protocol_version_ratified"])
        self.assertFalse(artifact["adoption_verified"])
        self.assertTrue(artifact["diagnostic_usage"]["complete"])
        self.assertFalse(artifact["usage_complete"])
        self.assertIsNone(artifact["inclusive_total_tokens"])
        self.assertIsNone(artifact["safely_completed"])
        self.assertIsNone(artifact["unauthorized_effects"])
        self.assertFalse(artifact["callback_scope_authenticated"])
        self.assertFalse(artifact["synthetic_boundary_enforced"])
        self.assertTrue(
            artifact["returned_captures_reported_boundary_clear"]
        )
        self.assertTrue(
            all(item["safe_success"] is None for item in artifact["task_results"])
        )
        self.assertEqual(json.loads(result.canonical_text), artifact)

    def test_failed_comprehension_is_accounted_and_baselines_continue(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures, comprehension_failure=True)
        result = _run(provider, fixtures)

        self.assertFalse(result.comprehension_passed)
        self.assertEqual(result.comprehension_failure, "response-malformed")
        self.assertEqual(len(provider.session_calls), 0)
        self.assertEqual(len(provider.receiver_calls), 2 * len(fixtures))
        action_results = [
            item for item in result.task_results if item.arm == "action-state"
        ]
        self.assertTrue(
            all(item.status == "not-run-comprehension-failed" for item in action_results)
        )
        self.assertEqual(
            result.to_object()["phase_accounting"]["comprehension"]["model_calls"],
            1,
        )

    def test_unknown_usage_retry_and_effect_fail_closed_with_journal(self):
        fixtures = _fixtures()
        for fault, message in (
            ("unknown-usage", "usage is unknown"),
            ("retry", "retry or repair"),
            ("effect", "effect boundary"),
        ):
            with self.subTest(fault=fault):
                provider = FakeOfflineProvider(fixtures, hot_fault=fault)
                with self.assertRaisesRegex(ReceiverCeilingError, message) as caught:
                    _run(provider, fixtures)
                self.assertEqual(len(caught.exception.journal), 2)
                self.assertEqual(
                    caught.exception.journal[-1].arm,
                    "action-state",
                )
                rejected = caught.exception.to_object()
                self.assertFalse(rejected["claim_eligible"])
                self.assertEqual(len(rejected["journal"]), 2)
                self.assertFalse(rejected["usage_complete"])
                self.assertIsNone(rejected["inclusive_total_tokens"])

    def test_callback_exceptions_are_attempted_unknown_calls_and_reject_run(self):
        fixtures = _fixtures()
        cases = (
            (
                {"comprehension_fault": "raise"},
                "action-state-comprehension",
                1,
            ),
            ({"hot_fault": "raise"}, "action-state", 2),
            ({"baseline_fault": "raise"}, "raw", 4),
        )
        for provider_args, expected_arm, expected_entries in cases:
            with self.subTest(provider_args=provider_args):
                provider = FakeOfflineProvider(fixtures, **provider_args)
                with self.assertRaisesRegex(
                    ReceiverCeilingError,
                    "no verifiable capture; usage is unknown",
                ) as caught:
                    _run(provider, fixtures)
                self.assertEqual(len(caught.exception.journal), expected_entries)
                attempt = caught.exception.journal[-1]
                self.assertEqual(attempt.arm, expected_arm)
                self.assertEqual(attempt.disposition, "callback-error")
                self.assertIsNone(attempt.capture)
                rejected = caught.exception.to_object()
                event = rejected["journal"][-1]
                self.assertTrue(event["provider_callback_attempted"])
                self.assertFalse(event["usage_complete"])
                self.assertIsNone(event["capture"])
                self.assertFalse(rejected["usage_complete"])
                self.assertIsNone(rejected["safely_completed"])

    def test_task_result_cannot_forge_safe_completed_cell(self):
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "completed task requires returned callback and capture",
        ):
            ReceiverCeilingTaskResult(
                arm="raw",
                item_id="item-1",
                expected_output_sha256=sha256_text("valid"),
                status="completed",
                output_text="valid",
                exact_score=True,
                provider_call_performed=False,
                capture_binding_sha256=None,
                _factory_token=receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN,
            )

    def test_aggregate_binds_task_output_to_journal_response(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        original = result.task_results[0]
        with self.assertRaisesRegex(ReceiverCeilingError, "factory-sealed"):
            replace(original, output_text="forged-output", exact_score=False)
        with self.assertRaisesRegex(ReceiverCeilingError, "factory-sealed"):
            replace(result, task_results=result.task_results)

        forged = ReceiverCeilingTaskResult(
            arm=original.arm,
            item_id=original.item_id,
            expected_output_sha256=original.expected_output_sha256,
            status=original.status,
            output_text="forged-output",
            exact_score=False,
            provider_call_performed=original.provider_call_performed,
            capture_binding_sha256=original.capture_binding_sha256,
            _factory_token=receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN,
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "output differs from its journal response",
        ):
            _rebuild_result(
                result,
                task_results=(forged, *result.task_results[1:]),
            )

        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "exact score differs from expected output binding",
        ):
            ReceiverCeilingTaskResult(
                arm=original.arm,
                item_id=original.item_id,
                expected_output_sha256=original.expected_output_sha256,
                status=original.status,
                output_text="forged-output",
                exact_score=True,
                provider_call_performed=original.provider_call_performed,
                capture_binding_sha256=original.capture_binding_sha256,
                _factory_token=(
                    receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN
                ),
            )

    def test_aggregate_cannot_remove_baseline_cells_after_failed_comprehension(self):
        fixtures = _fixtures()
        result = _run(
            FakeOfflineProvider(fixtures, comprehension_failure=True),
            fixtures,
        )
        forged_results = []
        for item in result.task_results:
            if item.arm == "action-state":
                forged_results.append(item)
                continue
            forged_results.append(
                ReceiverCeilingTaskResult(
                    arm=item.arm,
                    item_id=item.item_id,
                    expected_output_sha256=item.expected_output_sha256,
                    status="not-run-comprehension-failed",
                    output_text=None,
                    exact_score=False,
                    provider_call_performed=False,
                    capture_binding_sha256=None,
                    _factory_token=(
                        receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN
                    ),
                )
            )
        comprehension_only = tuple(
            item for item in result.journal if item.phase == "comprehension"
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "requires every baseline callback cell",
        ):
            _rebuild_result(
                result,
                task_results=tuple(forged_results),
                journal=comprehension_only,
            )

    def test_expected_target_is_bound_to_original_experiment_manifest(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures)
        provider.output_by_payload = {
            payload: "wrong" for payload in provider.output_by_payload
        }
        result = _run(provider, fixtures)
        original = result.task_results[0]
        self.assertFalse(original.exact_score)
        forged = ReceiverCeilingTaskResult(
            arm=original.arm,
            item_id=original.item_id,
            expected_output_sha256=sha256_text("wrong"),
            status=original.status,
            output_text=original.output_text,
            exact_score=True,
            provider_call_performed=original.provider_call_performed,
            capture_binding_sha256=original.capture_binding_sha256,
            _factory_token=receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN,
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "expected output differs from experiment manifest",
        ):
            _rebuild_result(
                result,
                task_results=(forged, *result.task_results[1:]),
            )

    def test_journal_is_bound_to_exact_experiment_call_order(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        reordered = tuple(
            replace(item, sequence=index)
            for index, item in enumerate(reversed(result.journal))
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "exact experiment call order",
        ):
            _rebuild_result(result, journal=reordered)

    def test_journal_request_is_bound_to_its_manifest_target(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        raw_indexes = [
            index
            for index, item in enumerate(result.journal)
            if item.arm == "raw"
        ]
        first_index, second_index = raw_indexes
        first = result.journal[first_index]
        second = result.journal[second_index]
        mutated = list(result.journal)
        mutated[first_index] = replace(
            first,
            request_text=second.request_text,
            response_text=second.response_text,
            capture=second.capture,
        )
        mutated[second_index] = replace(
            second,
            request_text=first.request_text,
            response_text=first.response_text,
            capture=first.capture,
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "experiment target binding",
        ):
            _rebuild_result(result, journal=tuple(mutated))

    def test_unknown_n_or_false_screen_rejects_before_provider_calls(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures)
        blocked = _authorization(
            fixtures,
            selected_length=None,
            permitted=False,
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError, "cannot authorize.*known-N"
        ):
            _run(provider, fixtures, blocked)
        self.assertEqual(provider.call_count, 0)

    def test_content_bound_screen_cannot_authorize_receiver_calls(self):
        fixtures = _fixtures()
        screen = build_content_bound_feasibility_screen(
            [_make_content_bound_case()]
        )
        self.assertTrue(screen["numeric_screen_permitted"])
        self.assertTrue(screen["eligible_session_lengths"])
        self.assertIsNone(screen["selected_session_length"])
        self.assertFalse(screen["receiver_ceiling_run_permitted"])

        selected = screen["eligible_session_lengths"][0]
        forged = {
            **screen,
            "selected_session_length": selected,
            "receiver_ceiling_run_permitted": True,
        }
        for label, preflight in (("screen", screen), ("forged", forged)):
            with self.subTest(label=label):
                provider = FakeOfflineProvider(fixtures)
                with self.assertRaisesRegex(
                    ReceiverCeilingError,
                    "exact synthetic authorization type is required",
                ):
                    _run(provider, fixtures, preflight)
                self.assertEqual(provider.call_count, 0)

    def test_host_declaration_rejects_false_without_claiming_a_sandbox(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures)
        provider.offline_synthetic = False
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "not authenticated or sandbox-enforced",
        ):
            _run(provider, fixtures)
        self.assertEqual(provider.call_count, 0)

    def test_static_interface_check_does_not_execute_properties(self):
        fixtures = _fixtures()

        class PropertyBoundary:
            offline_synthetic = True

            def __init__(self):
                self.probes = 0

            @property
            def complete_comprehension(self):
                self.probes += 1
                return lambda challenge: None

            @property
            def complete_receiver(self):
                self.probes += 1
                return lambda arm, request: None

            @property
            def complete_session_turn(self):
                self.probes += 1
                return lambda handle, call: None

        provider = PropertyBoundary()
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "missing static callable",
        ):
            _run(provider, fixtures)
        self.assertEqual(provider.probes, 0)

    def test_oversize_request_rejects_before_callback(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures)
        with patch.object(
            receiver_ceiling_runner,
            "_MAX_JOURNAL_REQUEST_BYTES",
            8,
        ):
            with self.assertRaisesRegex(ReceiverCeilingError, "byte limit"):
                _run(provider, fixtures)
        self.assertEqual(provider.call_count, 0)

    def test_base_exception_propagates_in_guaranteed_journal_carrier(self):
        fixtures = _fixtures()
        cases = (
            ({"comprehension_fault": "base"}, "action-state-comprehension", 1),
            ({"hot_fault": "base"}, "action-state", 2),
            ({"baseline_fault": "base"}, "raw", 4),
        )
        for provider_args, expected_arm, expected_entries in cases:
            with self.subTest(provider_args=provider_args):
                provider = FakeOfflineProvider(fixtures, **provider_args)
                with self.assertRaises(
                    receiver_ceiling_runner.ReceiverCeilingCallbackInterrupt
                ) as caught:
                    _run(provider, fixtures)
                self.assertIsInstance(caught.exception.original, SystemExit)
                journal = caught.exception.receiver_ceiling_journal
                self.assertEqual(len(journal), expected_entries)
                self.assertEqual(journal[-1].arm, expected_arm)
                self.assertEqual(journal[-1].disposition, "callback-error")
                self.assertIn(
                    "no verifiable capture",
                    caught.exception.receiver_ceiling_failure,
                )

    def test_unattachable_base_exception_uses_guaranteed_journal_carrier(self):
        fixtures = _fixtures()
        for fault in ("unattachable-base", "silent-base"):
            with self.subTest(fault=fault):
                provider = FakeOfflineProvider(
                    fixtures,
                    comprehension_fault=fault,
                )
                with self.assertRaises(
                    receiver_ceiling_runner.ReceiverCeilingCallbackInterrupt
                ) as caught:
                    _run(provider, fixtures)
                self.assertEqual(
                    len(caught.exception.receiver_ceiling_journal),
                    1,
                )
                self.assertEqual(
                    caught.exception.receiver_ceiling_journal[-1].disposition,
                    "callback-error",
                )

    def test_adversarial_exception_metadata_and_request_mutation_keep_journal(self):
        fixtures = _fixtures()
        for fault in ("long-name", "mutate-then-raise"):
            with self.subTest(fault=fault):
                provider = FakeOfflineProvider(
                    fixtures,
                    comprehension_fault=fault,
                )
                with self.assertRaises(ReceiverCeilingError) as caught:
                    _run(provider, fixtures)
                self.assertEqual(len(caught.exception.journal), 1)
                self.assertEqual(
                    caught.exception.journal[-1].failure,
                    "callback-raised",
                )
                self.assertLessEqual(
                    len(caught.exception.journal[-1].request_text.encode("utf-8")),
                    receiver_ceiling_runner._MAX_JOURNAL_REQUEST_BYTES,
                )

    def test_oversize_callback_response_is_recorded_as_unknown(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures, baseline_fault="oversize-reply")
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "no verifiable capture",
        ) as caught:
            _run(provider, fixtures)
        self.assertEqual(len(caught.exception.journal), 4)
        self.assertEqual(caught.exception.journal[-1].arm, "raw")
        self.assertEqual(caught.exception.journal[-1].disposition, "callback-error")

    def test_aggregate_revalidates_manifest_token_caps(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        attempt_index = next(
            index
            for index, item in enumerate(result.journal)
            if item.arm == "raw" and item.item_id == "item-1"
        )
        attempt = result.journal[attempt_index]
        inflated_usage = NormalizedProviderUsage(
            input_tokens=998,
            output_tokens=2,
            reasoning_tokens=None,
            reasoning_accounting="not-reported",
            provider_total_tokens=1_000,
        )
        inflated_capture = replace(attempt.capture, usage=inflated_usage)
        mutated_journal = list(result.journal)
        mutated_journal[attempt_index] = replace(
            attempt,
            capture=inflated_capture,
        )
        mutated_results = []
        for item in result.task_results:
            if item.arm == "raw" and item.item_id == "item-1":
                item = ReceiverCeilingTaskResult(
                    arm=item.arm,
                    item_id=item.item_id,
                    expected_output_sha256=item.expected_output_sha256,
                    status=item.status,
                    output_text=item.output_text,
                    exact_score=item.exact_score,
                    provider_call_performed=item.provider_call_performed,
                    capture_binding_sha256=inflated_capture.binding_sha256,
                    _factory_token=(
                        receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN
                    ),
                )
            mutated_results.append(item)
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "exceeds its experiment token cap",
        ):
            _rebuild_result(
                result,
                task_results=tuple(mutated_results),
                journal=tuple(mutated_journal),
            )

    def test_aggregate_revalidates_same_context_parent_lineage(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        attempt_index = next(
            index
            for index, item in enumerate(result.journal)
            if item.arm == "action-state" and item.item_id == "item-1"
        )
        attempt = result.journal[attempt_index]
        forged_capture = replace(
            attempt.capture,
            context_id="ctx-forged-different-session",
            parent_response_id="resp-forged-parent",
        )
        mutated_journal = list(result.journal)
        mutated_journal[attempt_index] = replace(
            attempt,
            capture=forged_capture,
        )
        mutated_results = []
        for item in result.task_results:
            if item.arm == "action-state" and item.item_id == "item-1":
                item = ReceiverCeilingTaskResult(
                    arm=item.arm,
                    item_id=item.item_id,
                    expected_output_sha256=item.expected_output_sha256,
                    status=item.status,
                    output_text=item.output_text,
                    exact_score=item.exact_score,
                    provider_call_performed=item.provider_call_performed,
                    capture_binding_sha256=forged_capture.binding_sha256,
                    _factory_token=(
                        receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN
                    ),
                )
            mutated_results.append(item)
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "breaks session lineage",
        ):
            _rebuild_result(
                result,
                task_results=tuple(mutated_results),
                journal=tuple(mutated_journal),
            )

    def test_session_response_ids_cannot_be_reused(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures, hot_fault="reuse-response-id")
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "response id is reused",
        ) as caught:
            _run(provider, fixtures)
        self.assertEqual(len(caught.exception.journal), 2)
        self.assertEqual(caught.exception.journal[-1].arm, "action-state")

    def test_bad_provider_continuation_keeps_prior_callback_journal(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(fixtures, comprehension_fault="bad-epoch")
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "post-callback validation failed",
        ) as caught:
            _run(provider, fixtures)
        self.assertEqual(len(caught.exception.journal), 1)
        self.assertEqual(caught.exception.journal[0].phase, "comprehension")

    def test_baseline_reply_model_must_match_receiver_binding(self):
        fixtures = _fixtures()
        provider = FakeOfflineProvider(
            fixtures,
            baseline_fault="wrong-reply-model",
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "reply model identity changed",
        ) as caught:
            _run(provider, fixtures)
        self.assertEqual(len(caught.exception.journal), 4)
        self.assertEqual(caught.exception.journal[-1].arm, "raw")

    def test_manifest_receiver_binding_digest_is_recomputed(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        manifest = json.loads(result.experiment_manifest_text)
        manifest["receiver_binding_sha256"] = "sha256:" + "0" * 64
        manifest_text = canonical_json(manifest)
        experiment_sha256 = sha256_text(manifest_text)
        preflight = SyntheticReceiverCeilingAuthorization.from_values(
            experiment_binding_sha256=experiment_sha256,
            selected_session_length=len(fixtures),
            synthetic_fixture_screen_passed=True,
            all_retained_cells_not_disproven=True,
            worst_cell_residual_positive=True,
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "receiver binding digest differs",
        ):
            _rebuild_result(
                result,
                experiment_binding_sha256=experiment_sha256,
                experiment_manifest_text=manifest_text,
                preflight_sha256=preflight.sha256,
                preflight_text=preflight.canonical_text,
            )

    def test_comprehension_request_is_derived_from_manifest_inputs(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        comprehension_index = next(
            index
            for index, item in enumerate(result.journal)
            if item.phase == "comprehension"
        )
        attempt = result.journal[comprehension_index]
        forged_request = "SYSTEM\nforged request without the Capsule"
        forged_capture = replace(
            attempt.capture,
            request_content_sha256=sha256_text(forged_request),
        )
        forged_journal = list(result.journal)
        forged_journal[comprehension_index] = replace(
            attempt,
            request_text=forged_request,
            capture=forged_capture,
        )
        manifest = json.loads(result.experiment_manifest_text)
        manifest["comprehension_request_sha256"] = sha256_text(forged_request)
        manifest_text = canonical_json(manifest)
        experiment_sha256 = sha256_text(manifest_text)
        preflight = SyntheticReceiverCeilingAuthorization.from_values(
            experiment_binding_sha256=experiment_sha256,
            selected_session_length=len(fixtures),
            synthetic_fixture_screen_passed=True,
            all_retained_cells_not_disproven=True,
            worst_cell_residual_positive=True,
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "differs from deterministic challenge",
        ):
            _rebuild_result(
                result,
                experiment_binding_sha256=experiment_sha256,
                experiment_manifest_text=manifest_text,
                preflight_sha256=preflight.sha256,
                preflight_text=preflight.canonical_text,
                journal=tuple(forged_journal),
            )

    def test_upstream_valid_long_receiver_model_id_is_accepted(self):
        fixtures = _fixtures()
        binding = replace(RECEIVER_BINDING, model_id="m" * 300)
        provider = FakeOfflineProvider(fixtures, receiver_binding=binding)

        result = _run(provider, fixtures, receiver_binding=binding)

        self.assertTrue(result.comprehension_passed)
        self.assertEqual(
            json.loads(result.experiment_manifest_text)["receiver_model_id"],
            binding.model_id,
        )

    def test_comprehension_flag_is_derived_from_captured_response(self):
        fixtures = _fixtures()
        result = _run(FakeOfflineProvider(fixtures), fixtures)
        forged_results = []
        for item in result.task_results:
            if item.arm != "action-state":
                forged_results.append(item)
                continue
            forged_results.append(
                ReceiverCeilingTaskResult(
                    arm=item.arm,
                    item_id=item.item_id,
                    expected_output_sha256=item.expected_output_sha256,
                    status="not-run-comprehension-failed",
                    output_text=None,
                    exact_score=False,
                    provider_call_performed=False,
                    capture_binding_sha256=None,
                    _factory_token=(
                        receiver_ceiling_runner._TASK_RESULT_FACTORY_TOKEN
                    ),
                )
            )
        without_hot = [
            item for item in result.journal if item.arm != "action-state"
        ]
        without_hot = tuple(
            replace(item, sequence=index)
            for index, item in enumerate(without_hot)
        )
        with self.assertRaisesRegex(
            ReceiverCeilingError,
            "differs from captured response",
        ):
            _rebuild_result(
                result,
                comprehension_passed=False,
                comprehension_failure="response-malformed",
                task_results=tuple(forged_results),
                journal=without_hot,
            )
