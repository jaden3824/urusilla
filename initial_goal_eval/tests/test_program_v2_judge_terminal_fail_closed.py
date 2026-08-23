"""Fail-closed regressions for Program /2 judge terminal selection.

These tests keep the provider captures generic because their subject is the
runtime's terminal-source decision, not typed receiver or judge parsing.  A
failed validation/fallback chain must never make an already rejected primary
look like the final receiver output.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import sha256_ref
from initial_goal_eval.program_v2_runtime_runner import (
    build_program_v2_local_capture,
    run_planned_program_v2_arm,
)
from initial_goal_eval.tests.test_plan_v2 import build_synthetic_plan_v2
from initial_goal_eval.tests.test_program_v2_runtime_runner import (
    CompleteAdapter,
    _local_capture,
    _local_usage,
    _provider_capture,
)


JUDGE_COMPONENTS = {
    "task-judge",
    "parse-judge",
    "semantic-judge",
    "negative-judge",
}


def _digest(label: str) -> str:
    return sha256_ref({"program-v2-judge-fail-closed-test": label})


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


def _judge_entries(artifact: dict, *, task_id: str) -> list[dict]:
    return [
        entry
        for entry in artifact["slot_runs"]
        if entry["slot_request"]["slot"]["task_id"] == task_id
        and entry["slot_request"]["slot"]["component"] in JUDGE_COMPONENTS
    ]


def _disposition(artifact: dict, entry: dict) -> str:
    slot_id = entry["slot_request"]["slot"]["slot_id"]
    matches = [
        item
        for item in artifact["resolved_program_v2"]["resolutions"]
        if item["slot_id"] == slot_id
    ]
    if len(matches) != 1:
        raise AssertionError((slot_id, len(matches)))
    return matches[0]["disposition"]


class _BrokenFallbackAdapter(CompleteAdapter):
    """Produce an invalid optimized output and fail one required stage."""

    def __init__(self, failed_component: str) -> None:
        super().__init__(hybrid_mode="action-state")
        self.failed_component = failed_component

    def execute_slot(self, request: dict) -> dict:
        self.calls.append(deepcopy(request))
        component = request["slot"]["component"]
        if component == self.failed_component:
            raise RuntimeError(f"deliberate {component} failure")
        if component == "output-validator":
            return build_program_v2_local_capture(
                request,
                input_preimage={"component": component, "stage": "input"},
                output_preimage={"component": component, "stage": "output"},
                usage=_local_usage(),
                facts={"output_verdict": "invalid"},
            )
        if request["slot"]["source_kind"] == "external-response":
            return _provider_capture(request, hybrid_mode=self.hybrid_mode)
        return _local_capture(request, hybrid_mode=self.hybrid_mode)


class ProgramV2JudgeTerminalFailClosedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_synthetic_plan_v2()
        self.session = self.plan["sessions"][0]

    def _run(self, adapter, *, label: str, arm_id: str = "hybrid-router") -> dict:
        return run_planned_program_v2_arm(
            self.plan,
            session_id=self.session["session_id"],
            arm_id=arm_id,
            execution_instance_sha256=_digest(label),
            adapter=adapter,
        )

    def _assert_unresolved_terminal_binds(
        self,
        artifact: dict,
        *,
        expected_component: str,
    ) -> None:
        for task in self.session["tasks"]:
            task_id = task["task_id"]
            source = _component_entry(
                artifact,
                task_id=task_id,
                component=expected_component,
            )
            self.assertEqual(_disposition(artifact, source), "failed-before-record")
            judges = _judge_entries(artifact, task_id=task_id)
            self.assertEqual(len(judges), 4)
            terminals = [
                entry["slot_request"]["terminal_evidence"] for entry in judges
            ]
            self.assertTrue(all(item == terminals[0] for item in terminals[1:]))
            terminal = terminals[0]
            self.assertEqual(terminal["terminal_kind"], "unresolved")
            self.assertEqual(terminal["source_component"], expected_component)
            self.assertNotEqual(terminal["source_component"], "primary")
            self.assertEqual(
                terminal["source_slot_id"],
                source["slot_request"]["slot"]["slot_id"],
            )
            self.assertEqual(terminal["source_disposition"], "failed-before-record")
            self.assertEqual(
                terminal["source_capture_sha256"], source["capture_sha256"]
            )
            self.assertIsNotNone(terminal["source_record_sha256"])
            self.assertIsNone(terminal["source_typed_execution_sha256"])
            self.assertIsNone(terminal["terminal_status"])
            self.assertIsNone(terminal["output_text"])
            self.assertIsNone(terminal["output_sha256"])
            self.assertFalse(terminal["content_binding_verified"])

    def test_validator_exception_binds_validator_failure_not_primary(self) -> None:
        artifact = self._run(
            _BrokenFallbackAdapter("output-validator"),
            label=f"{self._testMethodName}-validator",
        )

        for task in self.session["tasks"]:
            task_id = task["task_id"]
            self.assertEqual(
                _disposition(
                    artifact,
                    _component_entry(
                        artifact,
                        task_id=task_id,
                        component="fallback-control",
                    ),
                ),
                "not-activated",
            )
            self.assertEqual(
                _disposition(
                    artifact,
                    _component_entry(
                        artifact,
                        task_id=task_id,
                        component="fallback-receiver",
                    ),
                ),
                "not-activated",
            )
        self._assert_unresolved_terminal_binds(
            artifact,
            expected_component="output-validator",
        )

    def test_invalid_output_and_control_exception_binds_control(self) -> None:
        artifact = self._run(
            _BrokenFallbackAdapter("fallback-control"),
            label=f"{self._testMethodName}-control",
        )

        for task in self.session["tasks"]:
            task_id = task["task_id"]
            validator = _component_entry(
                artifact,
                task_id=task_id,
                component="output-validator",
            )
            self.assertEqual(_disposition(artifact, validator), "executed")
            self.assertEqual(validator["capture"]["facts"]["output_verdict"], "invalid")
            self.assertEqual(
                _disposition(
                    artifact,
                    _component_entry(
                        artifact,
                        task_id=task_id,
                        component="fallback-receiver",
                    ),
                ),
                "not-activated",
            )
        self._assert_unresolved_terminal_binds(
            artifact,
            expected_component="fallback-control",
        )

    def test_invalid_output_and_fallback_receiver_failure_bind_fallback(self) -> None:
        artifact = self._run(
            _BrokenFallbackAdapter("fallback-receiver"),
            label=f"{self._testMethodName}-fallback",
        )

        for task in self.session["tasks"]:
            task_id = task["task_id"]
            validator = _component_entry(
                artifact,
                task_id=task_id,
                component="output-validator",
            )
            control = _component_entry(
                artifact,
                task_id=task_id,
                component="fallback-control",
            )
            self.assertEqual(_disposition(artifact, validator), "executed")
            self.assertEqual(validator["capture"]["facts"]["output_verdict"], "invalid")
            self.assertEqual(_disposition(artifact, control), "executed")
        self._assert_unresolved_terminal_binds(
            artifact,
            expected_component="fallback-receiver",
        )

    def test_probe_metadata_is_visible_only_to_the_four_judges(self) -> None:
        artifacts = (
            self._run(
                CompleteAdapter(hybrid_mode="raw"),
                label=f"{self._testMethodName}-baseline",
                arm_id="raw-concise",
            ),
            self._run(
                CompleteAdapter(hybrid_mode="action-state"),
                label=f"{self._testMethodName}-hybrid",
            ),
        )

        for artifact in artifacts:
            metadata_components: set[str] = set()
            for entry in artifact["slot_runs"]:
                request = entry["slot_request"]
                component = request["slot"]["component"]
                metadata = request["task_metadata"]
                if component in JUDGE_COMPONENTS:
                    self.assertIsNotNone(metadata)
                    self.assertEqual(metadata["task_id"], request["slot"]["task_id"])
                    self.assertEqual(metadata["task_sha256"], request["task_sha256"])
                    metadata_components.add(component)
                else:
                    self.assertIsNone(
                        metadata,
                        f"{component} received evaluator-only probe metadata",
                    )
            self.assertEqual(metadata_components, JUDGE_COMPONENTS)

            for task in self.session["tasks"]:
                task_judges = _judge_entries(artifact, task_id=task["task_id"])
                self.assertEqual(
                    {
                        entry["slot_request"]["slot"]["component"]
                        for entry in task_judges
                    },
                    JUDGE_COMPONENTS,
                )
                self.assertTrue(
                    all(
                        entry["slot_request"]["task_metadata"] is not None
                        for entry in task_judges
                    )
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
