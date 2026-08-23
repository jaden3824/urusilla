"""Adversarial tests for Program /2 judge terminal-input binding.

These tests deliberately keep judge responses generic.  Their subject is the
immutable task metadata and terminal evidence supplied *to* each judge slot,
not verdict parsing or claim authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

import initial_goal_eval.program_v2_runtime_runner as runtime_runner
from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.program_v2_runtime_runner import (
    build_program_v2_local_capture,
    run_planned_program_v2_arm,
    validate_program_v2_runtime_run,
)
from initial_goal_eval.runtime_capture_bridge import (
    build_program_v2_receiver_capture,
)
from initial_goal_eval.tests.test_plan_v2 import build_synthetic_plan_v2
from initial_goal_eval.tests.test_program_v2_runtime_runner import (
    CompleteAdapter,
    _local_capture,
    _local_usage,
    _provider_capture,
)
from urusilla_hybrid_runtime.canonical import canonical_json, sha256_text
from urusilla_hybrid_runtime.captured_receiver import (
    CapturedProviderResponse,
    execute_captured_receiver,
)
from urusilla_hybrid_runtime.tests.test_captured_receiver import (
    StaticCapturedAdapter as StaticReceiverAdapter,
    _completed_capture as _receiver_completed_capture,
    _known_billed_failure_capture,
    _reply as _receiver_reply,
    _request as _raw_request,
)


JUDGE_COMPONENTS = {
    "task-judge",
    "parse-judge",
    "semantic-judge",
    "negative-judge",
}


def _digest(label: str) -> str:
    return sha256_ref({"program-v2-terminal-binding-test": label})


def _judge_entries(artifact: dict, *, task_id: str) -> list[dict]:
    return [
        entry
        for entry in artifact["slot_runs"]
        if entry["slot_request"]["slot"]["task_id"] == task_id
        and entry["slot_request"]["slot"]["component"] in JUDGE_COMPONENTS
    ]


def _component_entry(artifact: dict, *, task_id: str, component: str) -> dict:
    matches = [
        entry
        for entry in artifact["slot_runs"]
        if entry["slot_request"]["slot"]["task_id"] == task_id
        and entry["slot_request"]["slot"]["component"] == component
    ]
    if len(matches) != 1:
        raise AssertionError((task_id, component, len(matches)))
    return matches[0]


def _reseal_runtime_digest(artifact: dict) -> None:
    core = {
        name: value
        for name, value in artifact.items()
        if name not in {"schema_version", "run_sha256"}
    }
    artifact["run_sha256"] = sha256_ref(
        {
            "schema_version": (
                runtime_runner.PROGRAM_V2_RUNTIME_RUN_DIGEST_SCHEMA
            ),
            **core,
        }
    )


def _reseal_judge_entry(entry: dict) -> None:
    """Rebuild every public judge-capture digest after request tampering."""

    request = entry["slot_request"]
    capture = _provider_capture(request)
    entry["slot_request_sha256"] = sha256_ref(request)
    entry["capture"] = capture
    entry["capture_sha256"] = sha256_ref(capture)


class ProgramV2TerminalBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_synthetic_plan_v2()
        self.session = self.plan["sessions"][0]

    def _run(self, adapter, *, arm_id: str = "raw-concise") -> dict:
        return run_planned_program_v2_arm(
            self.plan,
            session_id=self.session["session_id"],
            arm_id=arm_id,
            execution_instance_sha256=_digest(
                f"{self._testMethodName}-{arm_id}"
            ),
            adapter=adapter,
        )

    def _typed_receiver_execution(
        self,
        slot_request: dict,
        *,
        output_text: str,
        provider_failure: bool = False,
    ):
        expected_model = slot_request["expected_model_id"]
        expected_settings = slot_request["expected_settings_sha256"]
        suffix = str(slot_request["slot_index"])
        request = _raw_request(
            f"Score terminal-binding fixture {slot_request['slot']['task_id']}."
        )
        if provider_failure:
            receipt = canonical_json(
                {
                    "id": f"typed-error-response-{suffix}",
                    "status": "provider_error",
                }
            )
            capture = replace(
                _known_billed_failure_capture(request),
                model_id=expected_model,
                settings_sha256=expected_settings,
                provider_request_id=f"typed-error-request-{suffix}",
                provider_response_id=f"typed-error-response-{suffix}",
                raw_receipt_text=receipt,
                raw_receipt_sha256=sha256_text(receipt),
            )
            response = CapturedProviderResponse(capture=capture, reply=None)
        else:
            reply = replace(
                _receiver_reply(),
                text=output_text,
                model_id=expected_model,
            )
            receipt = canonical_json(
                {
                    "id": f"typed-response-{suffix}",
                    "status": "completed",
                }
            )
            capture = replace(
                _receiver_completed_capture(request, reply),
                settings_sha256=expected_settings,
                provider_request_id=f"typed-request-{suffix}",
                provider_response_id=f"typed-response-{suffix}",
                raw_receipt_text=receipt,
                raw_receipt_sha256=sha256_text(receipt),
            )
            response = CapturedProviderResponse(capture=capture, reply=reply)
        return execute_captured_receiver(
            request,
            StaticReceiverAdapter(response),
            expected_model_id=expected_model,
            expected_settings_sha256=expected_settings,
        )

    def _typed_baseline_artifact(self, *, provider_failure: bool = False) -> dict:
        owner = self

        class TypedBaselineAdapter(CompleteAdapter):
            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                if request["slot"]["component"] == "receiver":
                    task_id = request["slot"]["task_id"]
                    execution = owner._typed_receiver_execution(
                        request,
                        output_text=f"typed-terminal::{task_id}",
                        provider_failure=provider_failure,
                    )
                    return build_program_v2_receiver_capture(request, execution)
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request)
                return _local_capture(request)

        return self._run(TypedBaselineAdapter())

    def test_generic_baseline_terminal_remains_unresolved(self) -> None:
        artifact = self._run(CompleteAdapter())
        task_id = self.session["tasks"][0]["task_id"]
        receiver = _component_entry(
            artifact,
            task_id=task_id,
            component="receiver",
        )
        judges = _judge_entries(artifact, task_id=task_id)

        self.assertEqual(len(judges), 4)
        terminals = [entry["slot_request"]["terminal_evidence"] for entry in judges]
        self.assertTrue(all(item == terminals[0] for item in terminals[1:]))
        terminal = terminals[0]
        self.assertEqual(terminal["terminal_kind"], "unresolved")
        self.assertFalse(terminal["content_binding_verified"])
        self.assertIsNone(terminal["output_text"])
        self.assertIsNone(terminal["output_sha256"])
        self.assertEqual(terminal["source_component"], "receiver")
        self.assertEqual(
            terminal["source_slot_id"],
            receiver["slot_request"]["slot"]["slot_id"],
        )
        self.assertEqual(
            terminal["source_capture_sha256"], receiver["capture_sha256"]
        )
        self.assertIsNone(terminal["source_typed_execution_sha256"])

    def test_typed_baseline_binds_exact_output_for_all_four_judges(self) -> None:
        artifact = self._typed_baseline_artifact()
        task = self.session["tasks"][0]
        task_id = task["task_id"]
        receiver = _component_entry(
            artifact,
            task_id=task_id,
            component="receiver",
        )
        judges = _judge_entries(artifact, task_id=task_id)
        terminal = judges[0]["slot_request"]["terminal_evidence"]
        expected_text = f"typed-terminal::{task_id}"

        self.assertEqual(len(judges), 4)
        self.assertTrue(
            all(
                entry["slot_request"]["terminal_evidence"] == terminal
                for entry in judges[1:]
            )
        )
        self.assertEqual(terminal["terminal_kind"], "provider-text")
        self.assertEqual(terminal["terminal_status"], "completed")
        self.assertEqual(terminal["output_text"], expected_text)
        self.assertEqual(
            terminal["output_sha256"],
            sha256_ref({"provider_output_text": expected_text}),
        )
        self.assertTrue(terminal["content_binding_verified"])
        self.assertEqual(terminal["source_component"], "receiver")
        self.assertEqual(
            terminal["source_capture_sha256"], receiver["capture_sha256"]
        )
        self.assertEqual(
            terminal["source_typed_execution_sha256"],
            receiver["capture"]["typed_execution_sha256"],
        )

        judge_slot_ids = {
            entry["slot_request"]["slot"]["slot_id"] for entry in judges
        }
        self.assertNotIn(terminal["source_slot_id"], judge_slot_ids)
        self.assertTrue(
            all(
                entry["slot_request"]["terminal_evidence"]["source_slot_id"]
                == receiver["slot_request"]["slot"]["slot_id"]
                for entry in judges
            )
        )

    def test_only_judges_receive_frozen_evaluator_metadata(self) -> None:
        artifact = self._typed_baseline_artifact()
        planned = {task["task_id"]: task for task in self.session["tasks"]}

        for entry in artifact["slot_runs"]:
            request = entry["slot_request"]
            task_id = request["slot"]["task_id"]
            component = request["slot"]["component"]
            if task_id is None or component not in JUDGE_COMPONENTS:
                self.assertIsNone(request["task_metadata"])
                continue
            expected = planned[task_id]
            self.assertEqual(
                request["task_metadata"],
                {
                    "task_id": expected["task_id"],
                    "task_sha256": expected["task_sha256"],
                    "feature_tags": expected["feature_tags"],
                    "parse_probe": expected["parse_probe"],
                    "semantic_probe": expected["semantic_probe"],
                    "negative_probe": expected["negative_probe"],
                },
            )

    def test_resealed_terminal_mutations_are_rejected_by_full_replay(self) -> None:
        original = self._typed_baseline_artifact()
        task_ids = [task["task_id"] for task in self.session["tasks"]]
        first_task, second_task = task_ids
        second_receiver = _component_entry(
            original,
            task_id=second_task,
            component="receiver",
        )

        for attack in ("output", "source", "capture"):
            with self.subTest(attack=attack):
                artifact = deepcopy(original)
                entry = _judge_entries(artifact, task_id=first_task)[0]
                terminal = entry["slot_request"]["terminal_evidence"]
                if attack == "output":
                    terminal["output_text"] = "resealed-substitute-output"
                    terminal["output_sha256"] = sha256_ref(
                        {"provider_output_text": terminal["output_text"]}
                    )
                elif attack == "source":
                    terminal["source_slot_id"] = second_receiver[
                        "slot_request"
                    ]["slot"]["slot_id"]
                    terminal["source_record_sha256"] = next(
                        item["source_record_sha256"]
                        for item in original["resolved_program_v2"]["resolutions"]
                        if item["slot_id"] == terminal["source_slot_id"]
                    )
                else:
                    terminal["source_capture_sha256"] = sha256_ref(
                        {"forged-source-capture": first_task}
                    )
                _reseal_judge_entry(entry)
                _reseal_runtime_digest(artifact)

                with self.assertRaisesRegex(
                    VerificationError,
                    "slot run request differs from canonical replay",
                ):
                    validate_program_v2_runtime_run(artifact)

    def test_cross_task_terminal_substitution_is_rejected_after_resealing(self) -> None:
        artifact = self._typed_baseline_artifact()
        first, second = [task["task_id"] for task in self.session["tasks"]]
        target = _judge_entries(artifact, task_id=first)[0]
        substituted = deepcopy(
            _judge_entries(artifact, task_id=second)[0]["slot_request"][
                "terminal_evidence"
            ]
        )
        substituted["task_id"] = first
        substituted["task_sha256"] = target["slot_request"]["task_sha256"]
        target["slot_request"]["terminal_evidence"] = substituted
        _reseal_judge_entry(target)
        _reseal_runtime_digest(artifact)

        with self.assertRaisesRegex(
            VerificationError,
            "slot run request differs from canonical replay",
        ):
            validate_program_v2_runtime_run(artifact)

    def test_typed_provider_failure_becomes_bound_provider_no_output(self) -> None:
        artifact = self._typed_baseline_artifact(provider_failure=True)
        task_id = self.session["tasks"][0]["task_id"]
        receiver = _component_entry(
            artifact,
            task_id=task_id,
            component="receiver",
        )
        judges = _judge_entries(artifact, task_id=task_id)
        terminal = judges[0]["slot_request"]["terminal_evidence"]

        self.assertEqual(terminal["terminal_kind"], "provider-no-output")
        self.assertEqual(terminal["terminal_status"], "provider_error")
        self.assertIsNone(terminal["output_text"])
        self.assertIsNone(terminal["output_sha256"])
        self.assertTrue(terminal["content_binding_verified"])
        self.assertEqual(terminal["source_component"], "receiver")
        self.assertEqual(
            terminal["source_capture_sha256"], receiver["capture_sha256"]
        )
        self.assertTrue(
            all(
                entry["slot_request"]["terminal_evidence"] == terminal
                for entry in judges[1:]
            )
        )

    def test_hybrid_silence_uses_final_router_as_canonical_terminal(self) -> None:
        artifact = self._run(CompleteAdapter(hybrid_mode="silence"), arm_id="hybrid-router")
        task_id = self.session["tasks"][0]["task_id"]
        router = _component_entry(
            artifact,
            task_id=task_id,
            component="final-router",
        )
        judges = _judge_entries(artifact, task_id=task_id)
        terminal = judges[0]["slot_request"]["terminal_evidence"]

        self.assertEqual(terminal["terminal_kind"], "canonical-silence")
        self.assertEqual(terminal["selected_mode"], "silence")
        self.assertEqual(terminal["terminal_status"], "silenced")
        self.assertIsNone(terminal["output_text"])
        self.assertTrue(terminal["content_binding_verified"])
        self.assertEqual(terminal["source_component"], "final-router")
        self.assertEqual(
            terminal["source_slot_id"], router["slot_request"]["slot"]["slot_id"]
        )
        self.assertTrue(
            all(
                entry["slot_request"]["terminal_evidence"] == terminal
                for entry in judges[1:]
            )
        )

    def test_hybrid_fallback_uses_typed_fallback_receiver_not_primary(self) -> None:
        owner = self

        class TypedFallbackAdapter(CompleteAdapter):
            def __init__(self) -> None:
                super().__init__(hybrid_mode="action-state")

            def execute_slot(self, request: dict) -> dict:
                self.calls.append(deepcopy(request))
                component = request["slot"]["component"]
                if component == "output-validator":
                    return build_program_v2_local_capture(
                        request,
                        input_preimage={"component": component, "stage": "input"},
                        output_preimage={"component": component, "stage": "output"},
                        usage=_local_usage(),
                        facts={"output_verdict": "invalid"},
                    )
                if component == "fallback-receiver":
                    task_id = request["slot"]["task_id"]
                    execution = owner._typed_receiver_execution(
                        request,
                        output_text=f"typed-fallback::{task_id}",
                    )
                    return build_program_v2_receiver_capture(request, execution)
                if request["slot"]["source_kind"] == "external-response":
                    return _provider_capture(request, hybrid_mode=self.hybrid_mode)
                return _local_capture(request, hybrid_mode=self.hybrid_mode)

        artifact = self._run(TypedFallbackAdapter(), arm_id="hybrid-router")
        task_id = self.session["tasks"][0]["task_id"]
        primary = _component_entry(
            artifact,
            task_id=task_id,
            component="primary",
        )
        fallback = _component_entry(
            artifact,
            task_id=task_id,
            component="fallback-receiver",
        )
        terminal = _judge_entries(artifact, task_id=task_id)[0]["slot_request"][
            "terminal_evidence"
        ]

        self.assertEqual(terminal["terminal_kind"], "provider-text")
        self.assertEqual(terminal["selected_mode"], "action-state")
        self.assertEqual(terminal["source_component"], "fallback-receiver")
        self.assertEqual(
            terminal["source_slot_id"], fallback["slot_request"]["slot"]["slot_id"]
        )
        self.assertNotEqual(
            terminal["source_slot_id"], primary["slot_request"]["slot"]["slot_id"]
        )
        self.assertEqual(terminal["output_text"], f"typed-fallback::{task_id}")
        self.assertTrue(terminal["content_binding_verified"])


if __name__ == "__main__":
    unittest.main()
