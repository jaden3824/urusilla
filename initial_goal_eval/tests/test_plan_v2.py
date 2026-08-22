"""Plan-v2 execution-program binding tests using synthetic data only."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import (
    ARMS,
    PLAN_SCHEMA,
    PLAN_SCHEMA_V2,
    VerificationError,
    plan_model_binding_sha256,
    plan_v2_hybrid_request_deriver_sha256,
    sha256_ref,
    validate_study_plan,
)
from initial_goal_eval.execution_program import (
    ARM_EXECUTION_PROGRAM_SCHEMA,
    ARM_EXECUTION_PROGRAM_SCHEMA_V2,
    GOAL_BASELINE_COMPONENTS,
    GOAL_HYBRID_COMPONENTS,
    build_goal_baseline_execution_program,
    build_goal_hybrid_execution_program,
    build_slot_evidence_record,
    execution_program_sha256,
)
from initial_goal_eval.execution_trace import validate_execution_trace
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture
from initial_goal_eval.verifier import verify_result


def _digest(label: str) -> str:
    return sha256_ref({"synthetic-plan-v2-test": label})


def _binding(
    component: str,
    *,
    implementation_sha256: str,
    external: bool,
    model_binding_sha256: str,
    request_deriver_sha256: str | None = None,
) -> dict[str, object]:
    return {
        "source_kind": "external-response" if external else "deterministic-local",
        "request_deriver_sha256": (
            request_deriver_sha256 or implementation_sha256
        )
        if external
        else None,
        "implementation_sha256": implementation_sha256,
        "model_binding_sha256": model_binding_sha256 if external else None,
        "maximum_calls": 1,
    }


def _baseline_bindings(
    plan: dict[str, object], arm_id: str, model_binding: str
) -> dict[str, dict[str, object]]:
    locks = plan["artifact_locks"]
    baseline_artifact = next(
        item["artifact_sha256"]
        for item in plan["baselines"]
        if item["arm_id"] == arm_id
    )
    lock_by_component = {
        "setup": baseline_artifact,
        "receiver": locks["receiver"],
        "task-judge": locks["task_scorer"],
        "parse-judge": locks["parse_scorer"],
        "semantic-judge": locks["semantic_scorer"],
        "negative-judge": locks["negative_scorer"],
    }
    return {
        component: _binding(
            component,
            implementation_sha256=lock_by_component[component],
            external=component != "setup",
            model_binding_sha256=model_binding,
            request_deriver_sha256=(
                baseline_artifact if component == "receiver" else None
            ),
        )
        for component in GOAL_BASELINE_COMPONENTS
    }


def _hybrid_bindings(
    plan: dict[str, object], model_binding: str
) -> dict[str, dict[str, object]]:
    locks = plan["artifact_locks"]
    baseline_artifacts = {
        item["arm_id"]: item["artifact_sha256"] for item in plan["baselines"]
    }
    route_request_deriver = plan_v2_hybrid_request_deriver_sha256(
        locks=locks,
        baseline_artifacts=baseline_artifacts,
    )
    external = {
        "sender-compiler",
        "primary",
        "fallback-receiver",
        "task-judge",
        "parse-judge",
        "semantic-judge",
        "negative-judge",
    }
    lock_by_component = {
        "setup": locks["capsule"],
        "preflight-router": locks["router"],
        "sender-compiler": locks["sender"],
        "compiler-control": locks["router"],
        "fidelity-verifier": locks["semantic_scorer"],
        "final-router": locks["router"],
        "primary": locks["receiver"],
        "output-validator": locks["parse_scorer"],
        "fallback-control": locks["router"],
        "fallback-receiver": locks["receiver"],
        "task-judge": locks["task_scorer"],
        "parse-judge": locks["parse_scorer"],
        "semantic-judge": locks["semantic_scorer"],
        "negative-judge": locks["negative_scorer"],
    }
    return {
        component: _binding(
            component,
            implementation_sha256=lock_by_component[component],
            external=component in external,
            model_binding_sha256=model_binding,
            request_deriver_sha256=(
                route_request_deriver
                if component in {"primary", "fallback-receiver"}
                else None
            ),
        )
        for component in GOAL_HYBRID_COMPONENTS
    }


def build_synthetic_plan_v2() -> dict[str, object]:
    plan, _ = build_synthetic_fixture()
    plan = deepcopy(plan)
    plan["schema_version"] = PLAN_SCHEMA_V2
    model_by_family = {
        model["family"]: model for model in plan["receiver_models"]
    }
    for session in plan["sessions"]:
        model_binding = plan_model_binding_sha256(
            model_by_family[session["receiver_family"]]
        )
        task_refs = [
            {"task_id": task["task_id"], "task_sha256": task["task_sha256"]}
            for task in session["tasks"]
        ]
        programs: dict[str, object] = {}
        for arm_id in ARMS:
            if arm_id == "hybrid-router":
                program = build_goal_hybrid_execution_program(
                    session_id=session["session_id"],
                    task_refs=task_refs,
                    frozen_bindings=_hybrid_bindings(plan, model_binding),
                )
            else:
                program = build_goal_baseline_execution_program(
                    session_id=session["session_id"],
                    arm_id=arm_id,
                    task_refs=task_refs,
                    frozen_bindings=_baseline_bindings(
                        plan, arm_id, model_binding
                    ),
                )
            programs[arm_id] = {
                "program_sha256": execution_program_sha256(program),
                "program": program,
            }
        session.pop("arm_execution_manifest_sha256")
        session["arm_execution_programs"] = programs
    return plan


class PlanV2Tests(unittest.TestCase):
    def test_plan_v2_inlines_every_canonical_program_preimage(self) -> None:
        plan = build_synthetic_plan_v2()
        summary = validate_study_plan(plan)
        self.assertEqual(summary["plan_schema_version"], PLAN_SCHEMA_V2)
        self.assertEqual(summary["sessions"], 24)
        for program in plan["sessions"][0]["arm_execution_programs"].values():
            self.assertEqual(
                program["program"]["schema_version"],
                ARM_EXECUTION_PROGRAM_SCHEMA_V2,
            )

    def test_inline_program_digest_mutation_is_rejected(self) -> None:
        plan = build_synthetic_plan_v2()
        plan["sessions"][0]["arm_execution_programs"]["raw-concise"][
            "program_sha256"
        ] = _digest("wrong-program")
        with self.assertRaises(VerificationError):
            validate_study_plan(plan)

    def test_resealed_noncanonical_hybrid_graph_is_rejected(self) -> None:
        plan = build_synthetic_plan_v2()
        wrapper = plan["sessions"][0]["arm_execution_programs"]["hybrid-router"]
        program = wrapper["program"]
        final_router = next(
            slot for slot in program["slots"] if slot["component"] == "final-router"
        )
        final_router["implementation_sha256"] = _digest("post-freeze-router-swap")
        wrapper["program_sha256"] = execution_program_sha256(program)
        with self.assertRaises(VerificationError):
            validate_study_plan(plan)

    def test_resealed_component_identity_cannot_escape_plan_lock(self) -> None:
        plan = build_synthetic_plan_v2()
        wrapper = plan["sessions"][0]["arm_execution_programs"]["hybrid-router"]
        program = wrapper["program"]
        for slot in program["slots"]:
            if slot["component"] == "final-router":
                slot["implementation_sha256"] = _digest("coherent-router-swap")
        wrapper["program_sha256"] = execution_program_sha256(program)
        with self.assertRaisesRegex(VerificationError, "plan lock"):
            validate_study_plan(plan)

    def test_resealed_model_binding_cannot_escape_session_model(self) -> None:
        plan = build_synthetic_plan_v2()
        wrapper = plan["sessions"][0]["arm_execution_programs"]["raw-concise"]
        program = wrapper["program"]
        for slot in program["slots"]:
            if slot["source_kind"] == "external-response":
                slot["model_binding_sha256"] = _digest("foreign-model")
        wrapper["program_sha256"] = execution_program_sha256(program)
        with self.assertRaisesRegex(VerificationError, "session model"):
            validate_study_plan(plan)

    def test_baseline_artifact_binds_receiver_request_deriver(self) -> None:
        plan = build_synthetic_plan_v2()
        wrapper = plan["sessions"][0]["arm_execution_programs"]["ordinary-json"]
        program = wrapper["program"]
        for slot in program["slots"]:
            if slot["component"] == "receiver":
                slot["request_deriver_sha256"] = _digest("foreign-baseline")
        wrapper["program_sha256"] = execution_program_sha256(program)
        with self.assertRaisesRegex(VerificationError, "request_deriver"):
            validate_study_plan(plan)

    def test_hybrid_deriver_rejects_each_coherently_swapped_baseline(self) -> None:
        for arm_id in ("raw-concise", "ordinary-json"):
            with self.subTest(arm_id=arm_id):
                plan = build_synthetic_plan_v2()
                baseline = next(
                    item for item in plan["baselines"] if item["arm_id"] == arm_id
                )
                replacement = _digest(f"replacement-{arm_id}")
                baseline["artifact_sha256"] = replacement

                # Coherently reseal the changed baseline arm itself.  The
                # still-frozen hybrid primary/fallback composite must be the
                # independent reason the plan now fails.
                wrapper = plan["sessions"][0]["arm_execution_programs"][arm_id]
                for slot in wrapper["program"]["slots"]:
                    if slot["component"] == "setup":
                        slot["implementation_sha256"] = replacement
                    elif slot["component"] == "receiver":
                        slot["request_deriver_sha256"] = replacement
                wrapper["program_sha256"] = execution_program_sha256(
                    wrapper["program"]
                )
                with self.assertRaisesRegex(VerificationError, "request_deriver"):
                    validate_study_plan(plan)

    def test_plan_v2_program_cannot_be_relabelled_as_legacy_v1(self) -> None:
        plan = build_synthetic_plan_v2()
        wrapper = plan["sessions"][0]["arm_execution_programs"]["ordinary-json"]
        wrapper["program"]["schema_version"] = ARM_EXECUTION_PROGRAM_SCHEMA
        with self.assertRaises(VerificationError):
            execution_program_sha256(wrapper["program"])

    def test_plan_v2_program_cannot_enter_legacy_source_record_domain(self) -> None:
        plan = build_synthetic_plan_v2()
        program = plan["sessions"][0]["arm_execution_programs"]["raw-concise"][
            "program"
        ]
        receiver = next(
            slot for slot in program["slots"] if slot["component"] == "receiver"
        )
        with self.assertRaisesRegex(VerificationError, "downgrade to /1"):
            build_slot_evidence_record(
                program,
                slot_id=receiver["slot_id"],
                record_kind="failure-before-source-record",
                request_sha256=_digest("unexecuted-request"),
                failure_sha256=_digest("failure"),
            )

    def test_resealed_task_identity_drift_is_rejected(self) -> None:
        plan = build_synthetic_plan_v2()
        wrapper = plan["sessions"][0]["arm_execution_programs"]["ordinary-json"]
        program = wrapper["program"]
        program["task_refs"][0]["task_sha256"] = _digest("foreign-task")
        wrapper["program_sha256"] = execution_program_sha256(program)
        with self.assertRaises(VerificationError):
            validate_study_plan(plan)

    def test_program_cannot_cross_session_or_arm(self) -> None:
        plan = build_synthetic_plan_v2()
        first = plan["sessions"][0]["arm_execution_programs"]
        second = plan["sessions"][1]["arm_execution_programs"]
        first["raw-concise"] = deepcopy(second["raw-concise"])
        with self.assertRaises(VerificationError):
            validate_study_plan(plan)

        plan = build_synthetic_plan_v2()
        programs = plan["sessions"][0]["arm_execution_programs"]
        programs["raw-concise"] = deepcopy(programs["ordinary-json"])
        with self.assertRaises(VerificationError):
            validate_study_plan(plan)

    def test_plan_schema_downgrade_fields_are_rejected(self) -> None:
        plan_v2 = build_synthetic_plan_v2()
        session_v2 = plan_v2["sessions"][0]
        session_v2["arm_execution_manifest_sha256"] = {
            arm_id: _digest(f"legacy-{arm_id}") for arm_id in ARMS
        }
        with self.assertRaises(VerificationError):
            validate_study_plan(plan_v2)

        plan_v1, _ = build_synthetic_fixture()
        plan_v1["sessions"][0]["arm_execution_programs"] = {}
        self.assertEqual(plan_v1["schema_version"], PLAN_SCHEMA)
        with self.assertRaises(VerificationError):
            validate_study_plan(plan_v1)

    def test_plan_v2_cannot_enter_trace_v2_or_result_v1(self) -> None:
        plan = build_synthetic_plan_v2()
        with self.assertRaisesRegex(VerificationError, "Trace /2"):
            validate_execution_trace(plan, {})
        with self.assertRaisesRegex(VerificationError, "Result /1"):
            verify_result(plan, {})


if __name__ == "__main__":
    unittest.main()
