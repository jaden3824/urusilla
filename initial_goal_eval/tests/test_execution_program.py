"""Focused fail-closed tests for standalone branch-slot programs."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import VerificationError, canonical_json, sha256_ref
from initial_goal_eval.execution_program import (
    ARM_EXECUTION_PROGRAM_RESOLUTION_SCHEMA,
    HYBRID_COMPONENTS,
    build_arm_execution_program,
    build_execution_evidence_store,
    build_hybrid_execution_program,
    build_slot_evidence_record,
    execution_program_activation_input_sha256,
    execution_program_sha256,
    resolve_arm_execution_program,
    validate_arm_execution_program,
    validate_arm_execution_program_json,
    validate_execution_evidence_store,
    validate_resolved_arm_execution_program,
)


def _digest(label: str) -> str:
    return sha256_ref({"execution-program-test": label})


def _binding(source_kind: str, component: str) -> dict[str, object]:
    external = source_kind == "external-response"
    return {
        "source_kind": source_kind,
        "request_deriver_sha256": _digest(f"{component}-request") if external else None,
        "implementation_sha256": _digest(f"{component}-implementation"),
        "model_binding_sha256": _digest(f"{component}-model") if external else None,
        "maximum_calls": 1,
    }


def _baseline_bindings() -> dict[str, dict[str, object]]:
    return {
        "setup": _binding("deterministic-local", "setup"),
        "receiver": _binding("external-response", "receiver"),
        "judge": _binding("deterministic-validator", "judge"),
    }


def _hybrid_bindings() -> dict[str, dict[str, object]]:
    external = {
        "sender-compiler",
        "fidelity-verifier",
        "primary",
        "fallback-receiver",
    }
    validators = {"output-validator", "judge"}
    return {
        component: _binding(
            "external-response"
            if component in external
            else "deterministic-validator"
            if component in validators
            else "deterministic-local",
            component,
        )
        for component in HYBRID_COMPONENTS
    }


def _task_refs(count: int = 1) -> list[dict[str, str]]:
    return [
        {"task_id": f"task-{index}", "task_sha256": _digest(f"task-{index}")}
        for index in range(count)
    ]


def _baseline_program(*, session_id: str = "session-1", tasks: int = 1) -> dict:
    return build_arm_execution_program(
        session_id=session_id,
        arm_id="raw-concise",
        task_refs=_task_refs(tasks),
        frozen_bindings=_baseline_bindings(),
    )


def _hybrid_program() -> dict:
    return build_hybrid_execution_program(
        session_id="session-1",
        task_refs=_task_refs(),
        frozen_bindings=_hybrid_bindings(),
    )


def _facts(component: str, *, output_verdict: str = "invalid", primary_status: str = "completed") -> dict:
    result: dict[str, str] = {}
    if component in {"receiver", "sender-compiler", "fidelity-verifier", "primary", "fallback-receiver"}:
        result["terminal_status"] = primary_status if component == "primary" else "completed"
    if component == "sender-compiler":
        result["compiler_status"] = "ok"
    if component == "fidelity-verifier":
        result["fidelity_verdict"] = "valid"
    if component == "router":
        result["selected_mode"] = "action-state"
    if component == "output-validator":
        result["output_verdict"] = output_verdict
    return result


def _seal(
    program: dict,
    *,
    dispositions: dict[str, str] | None = None,
    output_verdict: str = "invalid",
    primary_status: str = "completed",
) -> tuple[dict, list[dict]]:
    dispositions = dispositions or {}
    records = []
    sequence = 0
    for index, slot in enumerate(program["slots"]):
        disposition = dispositions.get(slot["component"], "executed")
        if disposition == "not-activated":
            continue
        if disposition == "executed":
            kwargs: dict[str, object] = {
                "result_event_sequence": sequence,
                "facts": _facts(
                    slot["component"],
                    output_verdict=output_verdict,
                    primary_status=primary_status,
                ),
            }
            if slot["source_kind"] == "external-response":
                kwargs.update(
                    request_sha256=_digest(f"request-{index}"),
                    provider_record_sha256=_digest(f"provider-{index}"),
                )
            else:
                kwargs["local_observation_sha256"] = _digest(f"local-{index}")
            sequence += 1
            kind = "executed-source"
        else:
            kwargs = {"failure_sha256": _digest(f"failure-{index}")}
            if slot["source_kind"] == "external-response":
                kwargs["request_sha256"] = _digest(f"request-{index}")
            kind = "failure-before-source-record"
        records.append(
            build_slot_evidence_record(
                program, slot_id=slot["slot_id"], record_kind=kind, **kwargs
            )
        )
    store = build_execution_evidence_store(program, records)
    digest_by_slot = {
        entry["record"]["slot_id"]: entry["record_sha256"]
        for entry in store["records"]
    }
    resolutions: list[dict] = []
    for slot in program["slots"]:
        disposition = dispositions.get(slot["component"], "executed")
        resolutions.append(
            {
                "slot_id": slot["slot_id"],
                "disposition": disposition,
                "activation_input_sha256": execution_program_activation_input_sha256(
                    program,
                    slot_id=slot["slot_id"],
                    resolutions=resolutions,
                    evidence_store=store,
                ),
                "source_record_sha256": digest_by_slot.get(slot["slot_id"]),
            }
        )
    return store, resolutions


class ProgramValidationTests(unittest.TestCase):
    def test_builder_has_one_setup_and_complete_task_graphs(self):
        program = _baseline_program(tasks=2)
        self.assertEqual(len(program["task_refs"]), 2)
        self.assertEqual([s["component"] for s in program["slots"]].count("setup"), 1)
        self.assertEqual([s["component"] for s in program["slots"]].count("judge"), 2)

    def test_baseline_judge_only_subgraph_is_rejected(self):
        program = _baseline_program()
        setup, _, judge = program["slots"]
        judge["activation_predicate"] = {"all_of": []}
        judge["depends_on"] = []
        judge["order_after"] = [setup["slot_id"]]
        program["slots"] = [setup, judge]
        with self.assertRaisesRegex(VerificationError, "receiver and one judge"):
            validate_arm_execution_program(program)

    def test_program_is_exact_and_digest_is_canonical(self):
        program = _baseline_program()
        reordered = {key: program[key] for key in reversed(tuple(program))}
        self.assertEqual(execution_program_sha256(program), execution_program_sha256(reordered))
        extra = deepcopy(program)
        extra["invented"] = True
        with self.assertRaisesRegex(VerificationError, "fields differ"):
            validate_arm_execution_program(extra)
        duplicate_json = canonical_json(program).replace(
            '"arm_id":"raw-concise"',
            '"arm_id":"raw-concise","arm_id":"raw-concise"',
            1,
        )
        with self.assertRaisesRegex(VerificationError, "duplicate JSON member"):
            validate_arm_execution_program_json(duplicate_json)

    def test_predicate_refs_and_ordering_edges_are_separate(self):
        program = _baseline_program()
        receiver = program["slots"][1]
        receiver["order_after"] = receiver["depends_on"][:]
        with self.assertRaisesRegex(VerificationError, "overlap"):
            validate_arm_execution_program(program)

    def test_component_source_matrix_is_fail_closed(self):
        program = _baseline_program()
        receiver = program["slots"][1]
        receiver.update(_binding("deterministic-local", "receiver"))
        with self.assertRaisesRegex(VerificationError, "component/source_kind"):
            validate_arm_execution_program(program)


class TypedResolutionTests(unittest.TestCase):
    def test_resolution_is_a_standalone_replay_closure(self):
        program = _baseline_program()
        store, resolutions = _seal(program)
        artifact = resolve_arm_execution_program(program, resolutions, store)
        self.assertEqual(artifact["schema_version"], ARM_EXECUTION_PROGRAM_RESOLUTION_SCHEMA)
        self.assertEqual(artifact["program_sha256"], execution_program_sha256(program))
        self.assertEqual(len(artifact["executed_slot_ids"]), 3)
        self.assertEqual(validate_resolved_arm_execution_program(artifact), artifact)

    def test_cross_wired_source_record_is_rejected(self):
        program = _baseline_program()
        store, resolutions = _seal(program)
        swapped = deepcopy(resolutions)
        swapped[0]["source_record_sha256"], swapped[2]["source_record_sha256"] = (
            swapped[2]["source_record_sha256"],
            swapped[0]["source_record_sha256"],
        )
        with self.assertRaisesRegex(VerificationError, "cross-wired"):
            resolve_arm_execution_program(program, swapped, store)

    def test_record_replay_under_another_session_is_rejected(self):
        first = _baseline_program(session_id="session-1")
        store, _ = _seal(first)
        second = _baseline_program(session_id="session-2")
        with self.assertRaisesRegex(VerificationError, "another program"):
            validate_execution_evidence_store(store, second)

    def test_domain_and_binding_mutations_fail_even_when_rehashed(self):
        program = _baseline_program()
        store, _ = _seal(program)
        for field, value in (
            ("session_id", "replayed-session"),
            ("task_sha256", _digest("wrong-task")),
            ("implementation_sha256", _digest("wrong-implementation")),
        ):
            mutated = deepcopy(store)
            mutated["records"][1]["record"][field] = value
            mutated["records"][1]["record_sha256"] = sha256_ref(mutated["records"][1]["record"])
            with self.subTest(field=field), self.assertRaises(VerificationError):
                validate_execution_evidence_store(mutated, program)

    def test_typed_evidence_roles_and_event_sequence_cannot_be_cross_wired(self):
        program = _baseline_program()
        store, _ = _seal(program)
        role_swap = deepcopy(store)
        receiver = role_swap["records"][1]["record"]
        receiver["provider_record_sha256"] = receiver["request_sha256"]
        role_swap["records"][1]["record_sha256"] = sha256_ref(receiver)
        with self.assertRaisesRegex(VerificationError, "reused across roles"):
            validate_execution_evidence_store(role_swap, program)

        event_replay = deepcopy(store)
        event_replay["records"][1]["record"]["result_event_sequence"] = 9
        event_replay["records"][1]["record_sha256"] = sha256_ref(
            event_replay["records"][1]["record"]
        )
        with self.assertRaisesRegex(VerificationError, "contiguous"):
            validate_execution_evidence_store(event_replay, program)

    def test_flipped_source_fact_invalidates_activation_digest(self):
        program = _hybrid_program()
        store, resolutions = _seal(
            program,
            dispositions={"fallback-control": "not-activated", "fallback-receiver": "not-activated"},
            output_verdict="valid",
        )
        mutated = deepcopy(store)
        router_entry = next(
            entry for entry in mutated["records"] if entry["record"]["component"] == "router"
        )
        router_entry["record"]["facts"]["selected_mode"] = "routine"
        router_entry["record_sha256"] = sha256_ref(router_entry["record"])
        router_resolution = next(
            item for item in resolutions if item["slot_id"] == router_entry["record"]["slot_id"]
        )
        router_resolution["source_record_sha256"] = router_entry["record_sha256"]
        with self.assertRaisesRegex(VerificationError, "activation input digest"):
            resolve_arm_execution_program(program, resolutions, mutated)

    def test_failed_or_noncompleted_primary_cannot_be_marked_valid(self):
        program = _hybrid_program()
        for dispositions, status in (({}, "refused"), ({"primary": "failed-before-record"}, "completed")):
            with self.subTest(dispositions=dispositions, status=status):
                store, resolutions = _seal(
                    program,
                    dispositions={
                        **dispositions,
                        "fallback-control": "not-activated",
                        "fallback-receiver": "not-activated",
                    },
                    output_verdict="valid",
                    primary_status=status,
                )
                with self.assertRaisesRegex(VerificationError, "cannot mark"):
                    resolve_arm_execution_program(program, resolutions, store)

    def test_failed_noncompleted_or_invalid_primary_routes_through_fallback(self):
        program = _hybrid_program()
        for dispositions, status in (
            ({"primary": "failed-before-record"}, "completed"),
            ({}, "refused"),
            ({}, "completed"),
        ):
            with self.subTest(dispositions=dispositions, status=status):
                store, resolutions = _seal(
                    program,
                    dispositions=dispositions,
                    output_verdict="invalid",
                    primary_status=status,
                )
                artifact = resolve_arm_execution_program(program, resolutions, store)
                by_component = {
                    slot["component"]: item
                    for slot, item in zip(program["slots"], artifact["resolutions"])
                }
                self.assertEqual(by_component["fallback-control"]["disposition"], "executed")
                self.assertEqual(by_component["fallback-receiver"]["disposition"], "executed")
                self.assertEqual(by_component["judge"]["disposition"], "executed")

    def test_fidelity_and_output_verdicts_have_exact_source_components(self):
        program = _hybrid_program()
        output = next(slot for slot in program["slots"] if slot["component"] == "output-validator")
        with self.assertRaisesRegex(VerificationError, "wrong source component"):
            build_slot_evidence_record(
                program,
                slot_id=output["slot_id"],
                record_kind="executed-source",
                local_observation_sha256=_digest("output-observation"),
                result_event_sequence=0,
                facts={"output_verdict": "invalid", "fidelity_verdict": "valid"},
            )

    def test_not_activated_has_no_record_or_zero_usage_event(self):
        program = _hybrid_program()
        store, resolutions = _seal(
            program,
            dispositions={"fallback-control": "not-activated", "fallback-receiver": "not-activated"},
            output_verdict="valid",
        )
        artifact = resolve_arm_execution_program(program, resolutions, store)
        skipped = [item for item in artifact["resolutions"] if item["disposition"] == "not-activated"]
        self.assertTrue(skipped)
        self.assertTrue(all(item["source_record_sha256"] is None for item in skipped))
        invented = deepcopy(resolutions)
        next(item for item in invented if item["disposition"] == "not-activated")["usage"] = {"total_tokens": 0}
        with self.assertRaisesRegex(VerificationError, "fields differ"):
            resolve_arm_execution_program(program, invented, store)


if __name__ == "__main__":
    unittest.main()
