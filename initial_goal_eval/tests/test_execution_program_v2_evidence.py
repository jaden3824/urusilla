"""Adversarial tests for the claim-ineligible Program /2 evidence closure."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.execution_program import (
    ARM_EXECUTION_EVIDENCE_STORE_SCHEMA,
    GOAL_BASELINE_COMPONENTS,
    GOAL_HYBRID_COMPONENTS,
    build_arm_execution_program,
    build_execution_evidence_store,
    build_goal_baseline_execution_program,
    build_goal_hybrid_execution_program,
    build_slot_evidence_record,
    resolve_arm_execution_program,
    validate_arm_execution_program,
    validate_execution_evidence_store,
)
from initial_goal_eval.execution_program_v2_evidence import (
    PROGRAM_V2_EVIDENCE_STORE_SCHEMA,
    PROGRAM_V2_RESOLUTION_SCHEMA,
    PROGRAM_V2_SOURCE_RECORD_SCHEMA,
    build_program_v2_evidence_store,
    build_program_v2_resolution_item,
    build_program_v2_source_record,
    derive_program_v2_activation_input,
    resolve_program_v2_evidence,
    validate_program_v2_evidence_store,
    validate_program_v2_source_record,
    validate_resolved_program_v2_evidence,
)


def _digest(label: str) -> str:
    return sha256_ref({"program-v2-evidence-test": label})


def _binding(component: str, source_kind: str) -> dict[str, object]:
    external = source_kind == "external-response"
    return {
        "source_kind": source_kind,
        "request_deriver_sha256": (
            _digest(f"{component}-request-deriver") if external else None
        ),
        "implementation_sha256": _digest(f"{component}-implementation"),
        "model_binding_sha256": (
            _digest(f"{component}-model") if external else None
        ),
        "maximum_calls": 1,
    }


def _task_refs(count: int = 1) -> list[dict[str, str]]:
    return [
        {"task_id": f"task-{index}", "task_sha256": _digest(f"task-{index}")}
        for index in range(count)
    ]


def _baseline_program(*, session_id: str = "session-v2", tasks: int = 1) -> dict:
    bindings = {
        component: _binding(
            component,
            "deterministic-local"
            if component == "setup"
            else "external-response",
        )
        for component in GOAL_BASELINE_COMPONENTS
    }
    return build_goal_baseline_execution_program(
        session_id=session_id,
        arm_id="raw-concise",
        task_refs=_task_refs(tasks),
        frozen_bindings=bindings,
    )


def _hybrid_program(*, session_id: str = "session-v2") -> dict:
    external = {
        "sender-compiler",
        "primary",
        "fallback-receiver",
        "task-judge",
        "parse-judge",
        "semantic-judge",
        "negative-judge",
    }
    validators = {"fidelity-verifier", "output-validator"}
    bindings = {
        component: _binding(
            component,
            "external-response"
            if component in external
            else "deterministic-validator"
            if component in validators
            else "deterministic-local",
        )
        for component in GOAL_HYBRID_COMPONENTS
    }
    return build_goal_hybrid_execution_program(
        session_id=session_id,
        task_refs=_task_refs(),
        frozen_bindings=bindings,
    )


def _external_usage() -> dict[str, object]:
    return {
        "model_calls": 1,
        "input_tokens": 3,
        "output_tokens": 2,
        "reasoning_tokens": 0,
        "reasoning_accounting": "included-in-output",
        "total_tokens": 5,
    }


def _local_usage() -> dict[str, object]:
    return {
        "model_calls": 0,
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "reasoning_accounting": None,
        "total_tokens": 0,
    }


def _facts(
    slot: dict,
    *,
    preflight_decision: str,
    final_mode: str,
    output_verdict: str,
) -> dict[str, str]:
    component = slot["component"]
    result: dict[str, str] = {}
    if slot["source_kind"] == "external-response":
        result["terminal_status"] = "completed"
    if component == "preflight-router":
        result.update(
            selected_mode="action-state",
            control_decision=preflight_decision,
        )
    elif component == "sender-compiler":
        result["compiler_status"] = "ok"
    elif component == "compiler-control":
        result.update(
            control_decision=preflight_decision,
            compiler_status="ok" if preflight_decision == "attempt-action-state" else "not-attempted",
        )
    elif component == "fidelity-verifier":
        result["fidelity_verdict"] = "valid"
    elif component == "final-router":
        result["selected_mode"] = final_mode
    elif component == "output-validator":
        result["output_verdict"] = output_verdict
    return result


def _seal(
    program: dict,
    *,
    dispositions: dict[str, str] | None = None,
    preflight_decision: str = "attempt-action-state",
    final_mode: str = "action-state",
    output_verdict: str = "invalid",
) -> tuple[dict, list[dict], dict]:
    dispositions = dispositions or {}
    records: list[dict] = []
    resolutions: list[dict] = []
    sequence = 0
    for index, slot in enumerate(program["slots"]):
        activation = derive_program_v2_activation_input(
            program,
            slot_id=slot["slot_id"],
            prior_resolutions=resolutions,
            prior_records=records,
        )
        disposition = dispositions.get(slot["component"], "executed")
        record = None
        if disposition == "executed":
            kwargs: dict[str, object] = {
                "result_event_sequence": sequence,
                "usage": (
                    _external_usage()
                    if slot["source_kind"] == "external-response"
                    else _local_usage()
                ),
                "facts": _facts(
                    slot,
                    preflight_decision=preflight_decision,
                    final_mode=final_mode,
                    output_verdict=output_verdict,
                ),
            }
            if slot["source_kind"] == "external-response":
                kwargs.update(
                    request_sha256=_digest(f"request-{index}"),
                    provider_record_sha256=_digest(f"provider-{index}"),
                )
            else:
                kwargs["local_observation_sha256"] = _digest(f"local-{index}")
            record = build_program_v2_source_record(
                program,
                slot_id=slot["slot_id"],
                record_kind="executed-source",
                activation_input=activation,
                **kwargs,
            )
            sequence += 1
        elif disposition == "failed-before-record":
            record = build_program_v2_source_record(
                program,
                slot_id=slot["slot_id"],
                record_kind="failure-before-source-record",
                activation_input=activation,
                request_sha256=(
                    _digest(f"failed-request-{index}")
                    if slot["source_kind"] == "external-response"
                    else None
                ),
                failure_artifact_sha256=_digest(f"failure-{index}"),
            )
        resolution = build_program_v2_resolution_item(
            program,
            slot_id=slot["slot_id"],
            disposition=disposition,
            activation_input=activation,
            source_record=record,
        )
        if record is not None:
            records.append(record)
        resolutions.append(resolution)
    store = build_program_v2_evidence_store(program, records)
    artifact = resolve_program_v2_evidence(program, resolutions, store)
    return store, resolutions, artifact


def _reseal_record_entry(entry: dict) -> None:
    record = entry["record"]
    if record["observation"] is not None:
        record["observation_sha256"] = sha256_ref(record["observation"])
    if record["failure"] is not None:
        record["failure_sha256"] = sha256_ref(record["failure"])
    entry["record_sha256"] = sha256_ref(record)


class ProgramV2EvidenceTests(unittest.TestCase):
    def test_baseline_closure_binds_every_slot_and_remains_claim_ineligible(self):
        program = _baseline_program()
        store, resolutions, artifact = _seal(program)

        self.assertEqual(store["schema_version"], PROGRAM_V2_EVIDENCE_STORE_SCHEMA)
        self.assertEqual(artifact["schema_version"], PROGRAM_V2_RESOLUTION_SCHEMA)
        self.assertEqual(
            [entry["record"]["schema_version"] for entry in store["records"]],
            [PROGRAM_V2_SOURCE_RECORD_SCHEMA] * len(program["slots"]),
        )
        self.assertEqual(
            [entry["record"]["result_event_sequence"] for entry in store["records"]],
            list(range(len(program["slots"]))),
        )
        self.assertEqual(
            artifact["executed_slot_ids"],
            [slot["slot_id"] for slot in program["slots"]],
        )
        for slot, item, entry in zip(
            program["slots"], resolutions, store["records"]
        ):
            record = entry["record"]
            self.assertEqual(record["slot_id"], slot["slot_id"])
            for name in (
                "source_kind",
                "request_deriver_sha256",
                "implementation_sha256",
                "model_binding_sha256",
                "maximum_calls",
            ):
                self.assertEqual(record[name], slot[name])
            self.assertEqual(
                record["activation_input_sha256"],
                item["activation_input_sha256"],
            )
        for authority in (
            artifact["authority"],
            store["authority"],
            *(entry["record"]["authority"] for entry in store["records"]),
        ):
            self.assertIsNone(authority["frozen_plan_sha256"])
            self.assertTrue(
                all(
                    value is False
                    for name, value in authority.items()
                    if name != "frozen_plan_sha256"
                )
            )
        self.assertEqual(validate_resolved_program_v2_evidence(artifact), artifact)

    def test_inactive_slots_are_recordless_eventless_and_do_not_consume_sequence(self):
        program = _hybrid_program()
        skipped_components = {
            "sender-compiler",
            "fidelity-verifier",
            "output-validator",
            "fallback-control",
            "fallback-receiver",
        }
        store, resolutions, artifact = _seal(
            program,
            dispositions={name: "not-activated" for name in skipped_components},
            preflight_decision="skip-action-state",
            final_mode="raw",
        )
        by_component = {
            slot["component"]: item
            for slot, item in zip(program["slots"], resolutions)
        }
        for component in skipped_components:
            item = by_component[component]
            self.assertEqual(item["disposition"], "not-activated")
            self.assertIsNone(item["source_record_sha256"])
            self.assertIsNone(item["result_event_sequence"])
        executed_records = [
            entry["record"]
            for entry in store["records"]
            if entry["record"]["record_kind"] == "executed-source"
        ]
        self.assertEqual(
            [record["result_event_sequence"] for record in executed_records],
            list(range(len(executed_records))),
        )
        self.assertEqual(len(artifact["executed_slot_ids"]), len(executed_records))

    def test_failed_before_record_is_eventless_and_usage_stays_unknown(self):
        program = _hybrid_program()
        store, _, _ = _seal(
            program,
            dispositions={
                "sender-compiler": "failed-before-record",
                "fidelity-verifier": "not-activated",
                "output-validator": "not-activated",
                "fallback-control": "not-activated",
                "fallback-receiver": "not-activated",
            },
            final_mode="raw",
        )
        failed_entry = next(
            entry
            for entry in store["records"]
            if entry["record"]["component"] == "sender-compiler"
        )
        failed = failed_entry["record"]
        self.assertEqual(failed["record_kind"], "failure-before-source-record")
        self.assertIsNone(failed["result_event_sequence"])
        self.assertEqual(
            failed["failure"]["usage"],
            {
                "model_calls": None,
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "reasoning_accounting": None,
                "total_tokens": None,
                "usage_complete": False,
            },
        )

        tampered = deepcopy(store)
        failed_entry = next(
            entry
            for entry in tampered["records"]
            if entry["record"]["component"] == "sender-compiler"
        )
        failed_entry["record"]["failure"]["usage"].update(
            model_calls=0,
            total_tokens=0,
            usage_complete=True,
        )
        _reseal_record_entry(failed_entry)
        with self.assertRaisesRegex(VerificationError, "usage must remain unknown"):
            validate_program_v2_evidence_store(tampered, program)

    def test_generic_noncanonical_program_v2_is_rejected_at_every_ingress(self):
        program = _hybrid_program()
        program["slots"][-1]["order_after"] = [program["slots"][0]["slot_id"]]
        self.assertEqual(
            validate_arm_execution_program(program)["schema_version"],
            "urusilla-initial-goal-arm-execution-program/2",
        )
        with self.assertRaisesRegex(VerificationError, "canonical operation graph"):
            derive_program_v2_activation_input(
                program,
                slot_id=program["slots"][0]["slot_id"],
                prior_resolutions=[],
                prior_records=[],
            )

    def test_same_slot_and_cross_slot_evidence_digest_reuse_is_rejected(self):
        program = _baseline_program()
        store, _, _ = _seal(program)

        same_slot = deepcopy(store)
        receiver = same_slot["records"][1]
        receiver["record"]["observation"]["provider_record_sha256"] = (
            receiver["record"]["observation"]["request_sha256"]
        )
        _reseal_record_entry(receiver)
        with self.assertRaisesRegex(VerificationError, "reused across roles or slots"):
            validate_program_v2_evidence_store(same_slot, program)

        cross_slot = deepcopy(store)
        first_request = cross_slot["records"][1]["record"]["observation"][
            "request_sha256"
        ]
        later = cross_slot["records"][2]
        later["record"]["observation"]["request_sha256"] = first_request
        _reseal_record_entry(later)
        with self.assertRaisesRegex(VerificationError, "reused across roles or slots"):
            validate_program_v2_evidence_store(cross_slot, program)

    def test_reordered_resolutions_and_resealed_event_chronology_are_rejected(self):
        program = _baseline_program()
        store, resolutions, _ = _seal(program)

        reordered = deepcopy(resolutions)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        with self.assertRaisesRegex(VerificationError, "canonical order"):
            resolve_program_v2_evidence(program, reordered, store)

        resequenced = deepcopy(store)
        first = resequenced["records"][0]
        second = resequenced["records"][1]
        first["record"]["result_event_sequence"] = 1
        first["record"]["observation"]["result_event_sequence"] = 1
        second["record"]["result_event_sequence"] = 0
        second["record"]["observation"]["result_event_sequence"] = 0
        _reseal_record_entry(first)
        _reseal_record_entry(second)
        with self.assertRaisesRegex(VerificationError, "contiguous in program order"):
            validate_program_v2_evidence_store(resequenced, program)

    def test_observation_preimage_and_frozen_slot_bindings_cannot_be_rehashed(self):
        program = _baseline_program()
        store, _, _ = _seal(program)

        observation_drift = deepcopy(store)
        receiver = observation_drift["records"][1]
        receiver["record"]["observation"]["facts"]["terminal_status"] = "refused"
        _reseal_record_entry(receiver)
        with self.assertRaisesRegex(VerificationError, "facts differs"):
            validate_program_v2_evidence_store(observation_drift, program)

        binding_drift = deepcopy(store)
        receiver = binding_drift["records"][1]
        receiver["record"]["implementation_sha256"] = _digest(
            "post-execution-implementation"
        )
        _reseal_record_entry(receiver)
        with self.assertRaisesRegex(VerificationError, "frozen binding differs"):
            validate_program_v2_evidence_store(binding_drift, program)

    def test_every_program_slot_domain_field_is_exactly_bound(self):
        program = _baseline_program()
        store, _, _ = _seal(program)
        receiver = store["records"][1]["record"]
        mutations = {
            "program_sha256": _digest("foreign-program"),
            "session_id": "foreign-session",
            "arm_id": "ordinary-json",
            "task_id": "foreign-task",
            "task_sha256": _digest("foreign-task"),
            "slot_id": program["slots"][0]["slot_id"],
            "accounting_phase": "fallback",
            "component": "fallback-receiver",
            "source_kind": "deterministic-local",
            "request_deriver_sha256": None,
            "implementation_sha256": _digest("foreign-implementation"),
            "model_binding_sha256": None,
            "maximum_calls": 0,
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                mutated = deepcopy(receiver)
                mutated[field] = replacement
                with self.assertRaises(VerificationError):
                    validate_program_v2_source_record(mutated, program)

    def test_coordinated_activation_and_source_rehash_cannot_change_truth(self):
        program = _hybrid_program()
        skipped_components = {
            "sender-compiler",
            "fidelity-verifier",
            "output-validator",
            "fallback-control",
            "fallback-receiver",
        }
        store, resolutions, _ = _seal(
            program,
            dispositions={name: "not-activated" for name in skipped_components},
            preflight_decision="skip-action-state",
            final_mode="raw",
        )
        sender_index = next(
            index
            for index, slot in enumerate(program["slots"])
            if slot["component"] == "sender-compiler"
        )
        forged_activation = deepcopy(
            resolutions[sender_index]["activation_input"]
        )
        forged_activation["fact_inputs"][0]["observed_value"] = (
            "attempt-action-state"
        )
        forged_sender = build_program_v2_source_record(
            program,
            slot_id=program["slots"][sender_index]["slot_id"],
            record_kind="failure-before-source-record",
            activation_input=forged_activation,
            request_sha256=_digest("forged-sender-request"),
            failure_artifact_sha256=_digest("forged-sender-failure"),
        )
        forged_item = build_program_v2_resolution_item(
            program,
            slot_id=program["slots"][sender_index]["slot_id"],
            disposition="failed-before-record",
            activation_input=forged_activation,
            source_record=forged_sender,
        )
        mutated_resolutions = deepcopy(resolutions)
        mutated_resolutions[sender_index] = forged_item
        records = [entry["record"] for entry in store["records"]]
        records.append(forged_sender)
        order = {
            slot["slot_id"]: index for index, slot in enumerate(program["slots"])
        }
        records.sort(key=lambda record: order[record["slot_id"]])
        mutated_store = build_program_v2_evidence_store(program, records)

        with self.assertRaisesRegex(
            VerificationError, "activation input differs from predicate replay"
        ):
            resolve_program_v2_evidence(
                program,
                mutated_resolutions,
                mutated_store,
            )

    def test_unknown_predicate_input_can_fail_but_cannot_be_skipped(self):
        program = _hybrid_program()
        with self.assertRaisesRegex(
            VerificationError, "unknown activation has an inconsistent disposition"
        ):
            _seal(
                program,
                dispositions={
                    "preflight-router": "failed-before-record",
                    "sender-compiler": "not-activated",
                },
            )

    def test_authority_flags_cannot_be_promoted_by_rehashing(self):
        program = _baseline_program()
        store, _, artifact = _seal(program)

        promoted_store = deepcopy(store)
        promoted_store["authority"]["claim_eligible"] = True
        with self.assertRaisesRegex(VerificationError, "must remain false"):
            validate_program_v2_evidence_store(promoted_store, program)

        promoted_artifact = deepcopy(artifact)
        promoted_artifact["authority"]["provider_authenticated"] = True
        with self.assertRaisesRegex(VerificationError, "must remain false"):
            validate_resolved_program_v2_evidence(promoted_artifact)

    def test_program_v1_and_v2_evidence_domains_never_auto_convert(self):
        program_v2 = _baseline_program()
        store_v2, _, _ = _seal(program_v2)
        with self.assertRaisesRegex(VerificationError, "downgrade to /1"):
            resolve_arm_execution_program(program_v2, [], store_v2)
        with self.assertRaisesRegex(VerificationError, "fields differ"):
            validate_execution_evidence_store(store_v2)

        relabelled = deepcopy(store_v2)
        relabelled["schema_version"] = ARM_EXECUTION_EVIDENCE_STORE_SCHEMA
        with self.assertRaisesRegex(VerificationError, "schema_version differs"):
            validate_program_v2_evidence_store(relabelled, program_v2)

        legacy_bindings = {
            "setup": _binding("setup", "deterministic-local"),
            "receiver": _binding("receiver", "external-response"),
            "judge": _binding("judge", "deterministic-validator"),
        }
        program_v1 = build_arm_execution_program(
            session_id="legacy-session",
            arm_id="raw-concise",
            task_refs=_task_refs(),
            frozen_bindings=legacy_bindings,
        )
        with self.assertRaisesRegex(VerificationError, "schema /2"):
            derive_program_v2_activation_input(
                program_v1,
                slot_id=program_v1["slots"][0]["slot_id"],
                prior_resolutions=[],
                prior_records=[],
            )

        # The legacy source builder remains independently operational for /1.
        legacy_activation_record = build_slot_evidence_record(
            program_v1,
            slot_id=program_v1["slots"][0]["slot_id"],
            record_kind="executed-source",
            local_observation_sha256=_digest("legacy-local"),
            result_event_sequence=0,
        )
        legacy_store = build_execution_evidence_store(
            program_v1, [legacy_activation_record]
        )
        self.assertEqual(
            legacy_store["schema_version"], ARM_EXECUTION_EVIDENCE_STORE_SCHEMA
        )


if __name__ == "__main__":
    unittest.main()
