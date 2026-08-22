"""Mutation-focused tests for the local causal-control matrix v3."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.causal_probe_matrix_v3 import (
    ACTION_STATE_FORMAT,
    CAUSAL_MATRIX_CALL_SCHEMA,
    CAUSAL_MATRIX_PACK_SCHEMA,
    CAUSAL_MATRIX_PLAN_SCHEMA,
    CAUSAL_MATRIX_RESPONSE_SCHEMA,
    CAUSAL_MATRIX_RESULT_SCHEMA,
    CAUSAL_MATRIX_SUMMARY_SCHEMA,
    CAUSAL_MATRIX_USAGE_SCHEMA,
    MATRIX_PLAN_STATUS,
    MATRIX_CONDITIONS,
    TOKEN_SCOPE,
    matrix_output_text_sha256,
    validate_causal_probe_matrix_pack,
    validate_causal_probe_matrix_pack_json,
    validate_causal_probe_matrix_plan,
    validate_causal_probe_matrix_plan_json,
)
from initial_goal_eval.causal_probe_v2 import OFFLINE_EVIDENCE_BOUNDARY
from initial_goal_eval.contract import VerificationError, canonical_json, sha256_ref


def _digest(label: str) -> str:
    return sha256_ref({"causal-matrix-v3-test": label})


def _action_state(
    task: str,
    critical_field: str,
    critical_value: object,
    trace_label: str,
) -> dict[str, object]:
    return {
        "format": ACTION_STATE_FORMAT,
        "act": "propose",
        "goal": {"p": "choose", "a": [task], "n": False, "src": "fixture"},
        "state": [],
        "constraints": [],
        "action": {
            "name": "choose",
            "args": {
                critical_field: critical_value,
                "task": task,
                "trace_label": trace_label,
            },
            "status": "proposed",
            "effects": [],
        },
        "outcome": None,
        "needs": [],
        "uncertainty": [],
    }


def _usage() -> dict[str, object]:
    return {
        "schema_version": CAUSAL_MATRIX_USAGE_SCHEMA,
        "scope": TOKEN_SCOPE,
        "input_tokens": 8,
        "output_tokens": 3,
        "reasoning_tokens": 0,
        "unclassified_tokens": 0,
        "provider_total_tokens": 11,
        "total_tokens": 11,
        "hidden_accounting": "none",
    }


def _output_text(field_id: str, condition: str) -> str | None:
    if condition == "flip-a":
        return f"accept-{field_id}"
    if condition == "flip-b":
        return f"reject-{field_id}"
    if condition == "semantic-invariant":
        return f"accept-{field_id}"
    if condition == "missing-critical":
        return None
    if condition == "answerable-no-payload":
        return f"r0-{field_id}"
    return f"fallback-{field_id}"


def _response(field_id: str, condition: str) -> dict[str, object]:
    output_text = _output_text(field_id, condition)
    if condition in {"flip-a", "flip-b", "semantic-invariant"}:
        disposition = "completed"
        fallback_mode = None
    elif condition == "missing-critical":
        disposition = "refused"
        fallback_mode = None
    elif condition == "answerable-no-payload":
        disposition = "completed"
        fallback_mode = None
    else:
        disposition = "fallback"
        fallback_mode = "json"
    return {
        "schema_version": CAUSAL_MATRIX_RESPONSE_SCHEMA,
        "provider_response_id": f"response-{field_id}-{condition}",
        "disposition": disposition,
        "fallback_mode": fallback_mode,
        "output_text": output_text,
        "output_sha256": (
            None
            if output_text is None
            else matrix_output_text_sha256(output_text)
        ),
    }


def _binding(spec: dict[str, object], condition: str) -> dict[str, object]:
    return {
        "non_payload_context_sha256": (
            spec["r0_context_sha256"]
            if condition == "answerable-no-payload"
            else spec["task_context_sha256"]
        ),
        "receiver_model_id": spec["receiver_model_id"],
        "model_settings_sha256": spec["model_settings_sha256"],
        "capsule_sha256": spec["capsule_sha256"],
        "fresh_context_per_call": True,
    }


def _call(
    field_id: str,
    condition: str,
    spec: dict[str, object],
    payload: object,
) -> dict[str, object]:
    response = _response(field_id, condition)
    usage = _usage()
    return {
        "schema_version": CAUSAL_MATRIX_CALL_SCHEMA,
        "call_id": f"call-{field_id}-{condition}",
        "request_id": f"request-{field_id}-{condition}",
        "context_instance_id": f"context-{field_id}-{condition}",
        "condition": condition,
        "binding": _binding(spec, condition),
        "safety_boundary": {
            "tools_used": False,
            "persistence_written": False,
            "permission_expanded": False,
            "spending_incurred": False,
            "external_effect_occurred": False,
        },
        "payload": deepcopy(payload),
        "payload_sha256": None if payload is None else sha256_ref(payload),
        "response": response,
        "response_sha256": sha256_ref(response),
        "usage": usage,
        "usage_sha256": sha256_ref(usage),
    }


def _fixture() -> tuple[dict[str, object], dict[str, object]]:
    definitions = (
        {
            "field_id": "action-decision",
            "domain_id": "domain-one",
            "critical_field": "decision",
            "critical_pointer": "/action/args/decision",
            "a": True,
            "b": False,
            "task": "task-one",
            "donor": "action-priority",
        },
        {
            "field_id": "action-priority",
            "domain_id": "domain-two",
            "critical_field": "priority",
            "critical_pointer": "/action/args/priority",
            "a": "high",
            "b": "low",
            "task": "task-two",
            "donor": "action-decision",
        },
    )
    payloads: dict[str, dict[str, object]] = {}
    for definition in definitions:
        field_id = definition["field_id"]
        payloads[field_id] = {
            "flip-a": _action_state(
                definition["task"],
                definition["critical_field"],
                definition["a"],
                "trace-a",
            ),
            "flip-b": _action_state(
                definition["task"],
                definition["critical_field"],
                definition["b"],
                "trace-a",
            ),
            "semantic-invariant": _action_state(
                definition["task"],
                definition["critical_field"],
                definition["a"],
                "trace-b",
            ),
        }
        missing = deepcopy(payloads[field_id]["flip-a"])
        missing["action"]["args"].pop(definition["critical_field"])
        payloads[field_id]["missing-critical"] = missing

    specs: list[dict[str, object]] = []
    for definition in definitions:
        field_id = definition["field_id"]
        donor = definition["donor"]
        shuffled_payload = payloads[donor]["flip-a"]
        spec = {
            "field_id": field_id,
            "stratum": {
                "domain_id": definition["domain_id"],
                "receiver_family": "receiver-family-one",
                "operator_id": "operator-one",
            },
            "payload_format": ACTION_STATE_FORMAT,
            "critical_pointer": definition["critical_pointer"],
            "invariant_pointer": "/action/args/trace_label",
            "receiver_model_id": "receiver-model-one",
            "model_settings_sha256": _digest("model-settings"),
            "capsule_sha256": _digest("capsule"),
            "task_context_sha256": _digest(f"task-context-{field_id}"),
            "r0_context_sha256": _digest(f"r0-context-{field_id}"),
            "payload_sha256": {
                "flip-a": sha256_ref(payloads[field_id]["flip-a"]),
                "flip-b": sha256_ref(payloads[field_id]["flip-b"]),
                "semantic-invariant": sha256_ref(
                    payloads[field_id]["semantic-invariant"]
                ),
                "missing-critical": sha256_ref(
                    payloads[field_id]["missing-critical"]
                ),
                "answerable-no-payload": None,
                "shuffled-or-corrupt": sha256_ref(shuffled_payload),
            },
            "expected_output_sha256": {
                condition: matrix_output_text_sha256(
                    _output_text(field_id, condition)
                )
                for condition in (
                    "flip-a",
                    "flip-b",
                    "semantic-invariant",
                    "answerable-no-payload",
                )
            },
            "shuffled_from": {"field_id": donor, "condition": "flip-a"},
        }
        specs.append(spec)

    plan = {
        "schema_version": CAUSAL_MATRIX_PLAN_SCHEMA,
        "status": MATRIX_PLAN_STATUS,
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "field_specs": specs,
    }
    results: list[dict[str, object]] = []
    for spec in specs:
        field_id = spec["field_id"]
        donor = spec["shuffled_from"]["field_id"]
        condition_payloads = {
            "flip-a": payloads[field_id]["flip-a"],
            "flip-b": payloads[field_id]["flip-b"],
            "semantic-invariant": payloads[field_id]["semantic-invariant"],
            "missing-critical": payloads[field_id]["missing-critical"],
            "answerable-no-payload": None,
            "shuffled-or-corrupt": payloads[donor]["flip-a"],
        }
        results.append(
            {
                "schema_version": CAUSAL_MATRIX_RESULT_SCHEMA,
                "field_id": field_id,
                "calls": [
                    _call(field_id, condition, spec, condition_payloads[condition])
                    for condition in MATRIX_CONDITIONS
                ],
            }
        )
    pack = {
        "schema_version": CAUSAL_MATRIX_PACK_SCHEMA,
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "plan_sha256": sha256_ref(plan),
        "field_results": results,
    }
    return plan, pack


def _spec(plan: dict[str, object], field_id: str) -> dict[str, object]:
    return next(item for item in plan["field_specs"] if item["field_id"] == field_id)


def _result(pack: dict[str, object], field_id: str) -> dict[str, object]:
    return next(
        item for item in pack["field_results"] if item["field_id"] == field_id
    )


def _call_for(
    pack: dict[str, object], field_id: str, condition: str
) -> dict[str, object]:
    return next(
        item
        for item in _result(pack, field_id)["calls"]
        if item["condition"] == condition
    )


def _reseal_plan(plan: dict[str, object], pack: dict[str, object]) -> None:
    pack["plan_sha256"] = sha256_ref(plan)


def _reseal_response(call: dict[str, object]) -> None:
    call["response_sha256"] = sha256_ref(call["response"])


def _reseal_usage(call: dict[str, object]) -> None:
    call["usage_sha256"] = sha256_ref(call["usage"])


class CausalProbeMatrixV3Tests(unittest.TestCase):
    def test_valid_matrix_reports_per_field_denominators_and_stays_nonclaim(self):
        plan, pack = _fixture()

        plan_summary = validate_causal_probe_matrix_plan(plan)
        summary = validate_causal_probe_matrix_pack(plan, pack)

        self.assertEqual(plan_summary["schema_version"], CAUSAL_MATRIX_SUMMARY_SCHEMA)
        self.assertTrue(plan_summary["matrix_structure_declared"])
        self.assertEqual(plan_summary["declared_calls"], 12)
        self.assertFalse(plan_summary["semantic_invariance_checked"])
        self.assertFalse(plan_summary["no_payload_accuracy_measured"])
        self.assertFalse(plan_summary["claim_eligible"])

        self.assertTrue(summary["structurally_valid"])
        self.assertEqual(
            summary["local_record_metric_scope"],
            "unauthenticated-supplied-records",
        )
        self.assertTrue(summary["local_record_matrix_checks_passed"])
        self.assertEqual(summary["local_record_gate_failures"], [])
        self.assertEqual(summary["local_record_calls"], 12)
        self.assertFalse(summary["semantic_invariance_checked"])
        self.assertFalse(summary["no_payload_accuracy_measured"])
        self.assertTrue(summary["local_semantic_invariance_contract_checked"])
        self.assertTrue(summary["local_no_payload_accuracy_contract_checked"])
        self.assertTrue(summary["local_per_field_matrix_structurally_validated"])
        self.assertTrue(summary["local_per_field_matrix_checks_passed"])
        self.assertTrue(summary["local_prohibited_boundary_flags_checked"])
        self.assertEqual(summary["local_record_prohibited_boundary_violations"], 0)
        self.assertEqual(
            summary["local_record_safety_boundary_flags_denominator"], 60
        )
        self.assertEqual(summary["local_record_flip_pairs_correct"], 2)
        self.assertEqual(summary["local_record_flip_pairs_denominator"], 2)
        self.assertEqual(summary["local_record_semantic_invariants_correct"], 2)
        self.assertEqual(
            summary["local_record_semantic_invariants_denominator"], 2
        )
        self.assertEqual(summary["local_record_missing_fail_closed"], 2)
        self.assertEqual(summary["local_record_missing_denominator"], 2)
        self.assertEqual(summary["local_record_r0_correct"], 2)
        self.assertEqual(summary["local_record_r0_denominator"], 2)
        self.assertEqual(summary["local_record_r0_false_refusals"], 0)
        self.assertEqual(summary["local_record_shuffled_fail_closed"], 2)
        self.assertEqual(summary["local_record_shuffled_denominator"], 2)
        self.assertEqual(len(summary["local_record_per_matrix_field"]), 2)
        for field in summary["local_record_per_matrix_field"]:
            self.assertEqual(field["control_checks_passed"], 5)
            self.assertEqual(field["control_checks_denominator"], 5)
            self.assertEqual(field["token_complete_calls"], 6)
            self.assertEqual(field["token_calls_denominator"], 6)
            self.assertEqual(field["prohibited_boundary_violations"], 0)
            self.assertEqual(field["safety_boundary_flags_denominator"], 30)
            self.assertTrue(field["checks_passed"])
        self.assertEqual(
            summary["local_record_worst_field"]["field_id"], "action-decision"
        )
        self.assertTrue(summary["local_record_worst_field_checks_passed"])
        self.assertTrue(
            summary["local_record_call_total_token_accounting_complete"]
        )
        self.assertEqual(summary["local_record_known_total_token_calls"], 12)
        self.assertEqual(summary["local_record_unknown_total_token_calls"], 0)
        self.assertEqual(summary["local_record_known_total_tokens"], 132)
        self.assertEqual(summary["local_record_inclusive_total_tokens"], 132)
        for deliberately_unimplemented in (
            "composition_holdout_checked",
            "calibration_headline_seed_separated",
            "frozen_generator_validated",
            "frozen_seed_validated",
            "five_dimensional_strata_validated",
            "full_token_ledger_validated",
            "task_semantics_used_verdict_validated",
            "preregistration_chronology_verified",
            "chronology_validated",
            "field_identity_envelope_bound",
            "declared_field_universe_covered",
            "stable_semantic_identity_validated",
            "blinding_validated",
            "assignment_randomization_validated",
            "assignment_commitment_bound",
            "provider_authenticity_verified",
            "provider_authentication_validated",
            "record_authentication_validated",
            "operator_independence_verified",
            "output_provenance_verified",
            "claim_eligible",
        ):
            self.assertFalse(summary[deliberately_unimplemented])
        self.assertEqual(
            summary["verdicts"]["local_control_matrix"]["status"],
            "local-record-contract-passed",
        )
        self.assertFalse(
            summary["verdicts"]["task_semantics_used"]["checks_passed"]
        )

    def test_strict_json_entry_points_accept_the_fixture(self):
        plan, pack = _fixture()
        self.assertTrue(
            validate_causal_probe_matrix_plan_json(canonical_json(plan))["valid"]
        )
        self.assertTrue(
            validate_causal_probe_matrix_pack_json(
                canonical_json(plan), canonical_json(pack)
            )["valid"]
        )

    def test_invariant_may_change_only_the_registered_irrelevant_pointer(self):
        plan, pack = _fixture()
        invariant = _call_for(
            pack, "action-decision", "semantic-invariant"
        )
        invariant["payload"]["action"]["args"]["decision"] = False
        invariant["payload_sha256"] = sha256_ref(invariant["payload"])
        _spec(plan, "action-decision")["payload_sha256"][
            "semantic-invariant"
        ] = invariant["payload_sha256"]
        _reseal_plan(plan, pack)

        with self.assertRaisesRegex(VerificationError, "outside the selected pointer"):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_changed_invariant_output_is_retained_as_a_negative_outcome(self):
        plan, pack = _fixture()
        invariant = _call_for(
            pack, "action-decision", "semantic-invariant"
        )
        wrong_text = "reject-action-decision"
        invariant["response"]["output_text"] = wrong_text
        invariant["response"]["output_sha256"] = matrix_output_text_sha256(
            wrong_text
        )
        _reseal_response(invariant)

        summary = validate_causal_probe_matrix_pack(plan, pack)

        self.assertFalse(summary["local_record_matrix_checks_passed"])
        self.assertIn(
            "semantic-invariant-failed:action-decision",
            summary["local_record_gate_failures"],
        )
        by_field = {
            item["field_id"]: item
            for item in summary["local_record_per_matrix_field"]
        }
        self.assertEqual(
            by_field["action-decision"]["semantic_invariants_correct"], 0
        )
        self.assertEqual(
            summary["local_record_worst_field"]["field_id"], "action-decision"
        )

    def test_answerable_no_payload_exposes_false_refusal(self):
        plan, pack = _fixture()
        r0 = _call_for(pack, "action-decision", "answerable-no-payload")
        r0["response"].update(
            {
                "disposition": "refused",
                "fallback_mode": None,
                "output_text": None,
                "output_sha256": None,
            }
        )
        _reseal_response(r0)

        summary = validate_causal_probe_matrix_pack(plan, pack)

        self.assertFalse(summary["local_record_matrix_checks_passed"])
        self.assertEqual(summary["local_record_missing_fail_closed"], 2)
        self.assertEqual(summary["local_record_r0_correct"], 1)
        self.assertEqual(summary["local_record_r0_false_refusals"], 1)
        self.assertIn(
            "r0-false-refusal:action-decision",
            summary["local_record_gate_failures"],
        )

    def test_answerable_no_payload_rejects_a_hidden_payload(self):
        plan, pack = _fixture()
        call = _call_for(pack, "action-decision", "answerable-no-payload")
        payload = _action_state("task-one", "decision", True, "trace-a")
        call["payload"] = payload
        call["payload_sha256"] = sha256_ref(payload)

        with self.assertRaisesRegex(VerificationError, "must carry no payload"):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_missing_critical_is_an_exact_single_field_ablation(self):
        for mutation, message in (
            (
                lambda payload: payload["action"]["args"].__setitem__(
                    "decision", True
                ),
                "still carries the critical field",
            ),
            (
                lambda payload: payload["action"]["args"].__setitem__(
                    "extra", "not-allowed"
                ),
                "differs outside the removed critical pointer",
            ),
        ):
            plan, pack = _fixture()
            call = _call_for(pack, "action-decision", "missing-critical")
            mutation(call["payload"])
            call["payload_sha256"] = sha256_ref(call["payload"])
            _spec(plan, "action-decision")["payload_sha256"][
                "missing-critical"
            ] = call["payload_sha256"]
            _reseal_plan(plan, pack)

            with self.subTest(message=message):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_matrix_pack(plan, pack)

    def test_completed_missing_control_fails_closed_without_dropping_the_row(self):
        plan, pack = _fixture()
        missing = _call_for(pack, "action-decision", "missing-critical")
        output_text = "guessed-from-distractor"
        missing["response"].update(
            {
                "disposition": "completed",
                "fallback_mode": None,
                "output_text": output_text,
                "output_sha256": matrix_output_text_sha256(output_text),
            }
        )
        _reseal_response(missing)

        summary = validate_causal_probe_matrix_pack(plan, pack)

        self.assertTrue(summary["structurally_valid"])
        self.assertFalse(summary["local_record_matrix_checks_passed"])
        self.assertIn(
            "missing-critical-did-not-fail-closed:action-decision",
            summary["local_record_gate_failures"],
        )
        self.assertEqual(summary["local_record_missing_fail_closed"], 1)

    def test_omitted_matrix_arm_is_rejected(self):
        plan, pack = _fixture()
        result = _result(pack, "action-decision")
        result["calls"] = [
            call
            for call in result["calls"]
            if call["condition"] != "semantic-invariant"
        ]

        with self.assertRaisesRegex(VerificationError, "full matrix"):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_prohibited_boundary_effect_is_retained_as_a_gate_failure(self):
        for field in (
            "tools_used",
            "persistence_written",
            "permission_expanded",
            "spending_incurred",
            "external_effect_occurred",
        ):
            plan, pack = _fixture()
            call = _call_for(pack, "action-priority", "flip-a")
            call["safety_boundary"][field] = True
            with self.subTest(field=field):
                summary = validate_causal_probe_matrix_pack(plan, pack)
                self.assertTrue(summary["structurally_valid"])
                self.assertFalse(summary["local_record_matrix_checks_passed"])
                self.assertIn(
                    f"prohibited-boundary:action-priority:flip-a:{field}",
                    summary["local_record_gate_failures"],
                )
                self.assertEqual(
                    summary["local_record_prohibited_boundary_violations"], 1
                )
                self.assertEqual(
                    summary["local_record_known_total_token_calls"], 12
                )
                by_field = {
                    item["field_id"]: item
                    for item in summary["local_record_per_matrix_field"]
                }
                self.assertEqual(
                    by_field["action-priority"]["token_complete_calls"], 6
                )
                self.assertFalse(by_field["action-priority"]["checks_passed"])
                self.assertEqual(
                    summary["local_record_worst_field"]["field_id"],
                    "action-priority",
                )

    def test_prohibited_boundary_attestations_must_be_boolean(self):
        plan, pack = _fixture()
        call = _call_for(pack, "action-decision", "flip-a")
        call["safety_boundary"]["tools_used"] = 0

        with self.assertRaisesRegex(VerificationError, "must be boolean"):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_unknown_usage_remains_null_and_fails_the_local_matrix(self):
        plan, pack = _fixture()
        call = _call_for(pack, "action-decision", "flip-a")
        call["usage"].update(
            {
                "input_tokens": 8,
                "output_tokens": None,
                "reasoning_tokens": None,
                "unclassified_tokens": None,
                "provider_total_tokens": None,
                "total_tokens": None,
                "hidden_accounting": "not-reported",
            }
        )
        _reseal_usage(call)

        summary = validate_causal_probe_matrix_pack(plan, pack)

        self.assertFalse(summary["local_record_matrix_checks_passed"])
        self.assertFalse(
            summary["local_record_call_total_token_accounting_complete"]
        )
        self.assertEqual(summary["local_record_known_total_token_calls"], 11)
        self.assertEqual(summary["local_record_unknown_total_token_calls"], 1)
        self.assertEqual(summary["local_record_known_total_tokens"], 121)
        self.assertIsNone(summary["local_record_inclusive_total_tokens"])
        self.assertIn(
            "unknown-inclusive-token-total:action-decision:flip-a",
            summary["local_record_gate_failures"],
        )
        by_field = {
            item["field_id"]: item
            for item in summary["local_record_per_matrix_field"]
        }
        self.assertEqual(by_field["action-decision"]["token_complete_calls"], 5)
        self.assertFalse(by_field["action-decision"]["checks_passed"])

    def test_unreported_hidden_usage_requires_an_authoritative_provider_total(self):
        plan, pack = _fixture()
        call = _call_for(pack, "action-decision", "flip-a")
        call["usage"].update(
            {
                "input_tokens": 8,
                "output_tokens": 3,
                "reasoning_tokens": None,
                "unclassified_tokens": 0,
                "provider_total_tokens": None,
                "total_tokens": 11,
                "hidden_accounting": "not-reported",
            }
        )
        _reseal_usage(call)

        with self.assertRaisesRegex(
            VerificationError,
            "cannot close unreported reasoning without a provider total",
        ):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_authoritative_provider_total_can_close_unreported_hidden_usage(self):
        plan, pack = _fixture()
        call = _call_for(pack, "action-decision", "flip-a")
        call["usage"].update(
            {
                "input_tokens": 8,
                "output_tokens": 3,
                "reasoning_tokens": None,
                "unclassified_tokens": 0,
                "provider_total_tokens": 15,
                "total_tokens": 15,
                "hidden_accounting": "not-reported",
            }
        )
        _reseal_usage(call)

        summary = validate_causal_probe_matrix_pack(plan, pack)

        self.assertTrue(summary["local_record_call_total_token_accounting_complete"])
        self.assertEqual(summary["local_record_known_total_tokens"], 136)
        self.assertEqual(summary["local_record_inclusive_total_tokens"], 136)

        call["usage"]["provider_total_tokens"] = 10
        call["usage"]["total_tokens"] = 10
        _reseal_usage(call)
        with self.assertRaisesRegex(VerificationError, "below visible subtotal 11"):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_shuffled_control_is_bound_to_another_field_payload(self):
        plan, pack = _fixture()
        shuffled = _call_for(
            pack, "action-decision", "shuffled-or-corrupt"
        )
        payload = _action_state("unbound-task", "decision", True, "trace-a")
        shuffled["payload"] = payload
        shuffled["payload_sha256"] = sha256_ref(payload)
        _spec(plan, "action-decision")["payload_sha256"][
            "shuffled-or-corrupt"
        ] = shuffled["payload_sha256"]
        _reseal_plan(plan, pack)

        with self.assertRaisesRegex(VerificationError, "commitment differs"):
            validate_causal_probe_matrix_pack(plan, pack)

    def test_plan_requires_distinct_r0_context_and_invariant_output(self):
        for mutation, message in (
            (
                lambda spec: spec.__setitem__(
                    "r0_context_sha256", spec["task_context_sha256"]
                ),
                "independently answerable",
            ),
            (
                lambda spec: spec["expected_output_sha256"].__setitem__(
                    "semantic-invariant",
                    spec["expected_output_sha256"]["flip-b"],
                ),
                "invariant expected output",
            ),
        ):
            plan, _pack = _fixture()
            mutation(_spec(plan, "action-decision"))
            with self.subTest(message=message):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_matrix_plan(plan)


if __name__ == "__main__":
    unittest.main()
