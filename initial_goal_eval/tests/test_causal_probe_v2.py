"""Mutation tests for the standalone, non-claim causal-probe v2 contract."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.causal_probe_v2 import (
    ACTION_STATE_FORMAT,
    CAUSAL_PROBE_ALIAS_BINDING_SCHEMA,
    CAUSAL_PROBE_ASSIGNMENT_SCHEMA,
    CAUSAL_PROBE_CALL_SCHEMA,
    CAUSAL_PROBE_EXTERNAL_REFERENCE_SET_SCHEMA,
    CAUSAL_PROBE_FIELD_UNIVERSE_SCHEMA,
    CAUSAL_PROBE_IDENTITY_ENVELOPE_SCHEMA,
    CAUSAL_PROBE_PACK_SCHEMA,
    CAUSAL_PROBE_PLAN_SCHEMA,
    CAUSAL_PROBE_RESPONSE_SCHEMA,
    CAUSAL_PROBE_RESULT_SCHEMA,
    CAUSAL_PROBE_SUMMARY_SCHEMA,
    CAUSAL_PROBE_USAGE_SCHEMA,
    CONDITIONS,
    EXTERNAL_REFERENCE_PURPOSE,
    EXTERNAL_REFERENCE_STATUS,
    OFFLINE_EVIDENCE_BOUNDARY,
    PLACEBO_EXPECTATION,
    PLAN_STATUS,
    TOKEN_SCOPE,
    output_text_sha256,
    validate_causal_probe_pack,
    validate_causal_probe_pack_json,
    validate_causal_probe_plan,
    validate_causal_probe_plan_json,
)
from initial_goal_eval.contract import VerificationError, canonical_json, sha256_ref


def _digest(label: str) -> str:
    return sha256_ref({"causal-probe-v2-test": label})


def _action_state(
    task: str,
    decision: bool,
    *,
    decision_field: str = "decision",
) -> dict[str, object]:
    return {
        "format": ACTION_STATE_FORMAT,
        "act": "propose",
        "goal": {"p": "choose", "a": [task], "n": False, "src": "fixture"},
        "state": [],
        "constraints": [],
        "action": {
            "name": "choose",
            "args": {decision_field: decision, "task": task},
            "status": "proposed",
            "effects": [],
        },
        "outcome": None,
        "needs": [],
        "uncertainty": [],
    }


def _twin_date_action_state(
    task: str,
    *,
    delivery_date: str,
    invoice_date: str,
    instruction: str,
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
                # The invoice alias is intentionally first and adjacent to the
                # instruction; the authoritative delivery alias is less salient.
                "deadline": invoice_date,
                "instruction": instruction,
                "delivery_on": delivery_date,
                "task": task,
            },
            "status": "proposed",
            "effects": [],
        },
        "outcome": None,
        "needs": [],
        "uncertainty": [],
    }


def _binding(probe_id: str) -> dict[str, object]:
    return {
        "non_payload_context_sha256": _digest(f"context-{probe_id}"),
        "receiver_model_id": "receiver-model-1",
        "model_settings_sha256": _digest("model-settings"),
        "capsule_sha256": _digest("capsule"),
        "fresh_context_per_call": True,
    }


def _usage() -> dict[str, object]:
    return {
        "schema_version": CAUSAL_PROBE_USAGE_SCHEMA,
        "scope": TOKEN_SCOPE,
        "input_tokens": 8,
        "output_tokens": 3,
        "reasoning_tokens": 0,
        "unclassified_tokens": 0,
        "provider_total_tokens": 11,
        "total_tokens": 11,
        "hidden_accounting": "none",
    }


def _blind_label(probe_id: str, condition: str) -> str:
    return "blind-" + sha256_ref(
        {"probe_id": probe_id, "condition": condition}
    ).removeprefix("sha256:")[:24]


def _response(probe_id: str, condition: str) -> dict[str, object]:
    if condition == "a":
        disposition = "completed"
        fallback_mode = None
        output_text = f"accept-{probe_id}"
    elif condition == "b":
        disposition = "completed"
        fallback_mode = None
        output_text = f"reject-{probe_id}"
    elif condition == "missing":
        disposition = "refused"
        fallback_mode = None
        output_text = None
    else:
        disposition = "fallback"
        fallback_mode = "json"
        output_text = f"fallback-{probe_id}"
    return {
        "schema_version": CAUSAL_PROBE_RESPONSE_SCHEMA,
        "provider_response_id": f"response-{probe_id}-{condition}",
        "disposition": disposition,
        "fallback_mode": fallback_mode,
        "output_text": output_text,
        "output_sha256": (
            None if output_text is None else output_text_sha256(output_text)
        ),
    }


def _call(
    probe_id: str,
    condition: str,
    binding: dict[str, object],
    payload: object,
) -> dict[str, object]:
    response = _response(probe_id, condition)
    usage = _usage()
    return {
        "schema_version": CAUSAL_PROBE_CALL_SCHEMA,
        "call_id": f"call-{probe_id}-{condition}",
        "request_id": f"request-{probe_id}-{condition}",
        "context_instance_id": f"context-instance-{probe_id}-{condition}",
        "blind_label": _blind_label(probe_id, condition),
        "binding": deepcopy(binding),
        "payload": deepcopy(payload),
        "payload_sha256": None if payload is None else sha256_ref(payload),
        "response": response,
        "response_sha256": sha256_ref(response),
        "usage": usage,
        "usage_sha256": sha256_ref(usage),
    }


def _fixture() -> tuple[dict[str, object], dict[str, object]]:
    probe_ids = ("probe-one", "probe-two")
    payloads = {
        "probe-one": {
            "a": _action_state("task-one", True),
            "b": _action_state("task-one", False),
        },
        "probe-two": {
            "a": _action_state(
                "task-two", True, decision_field="selected_decision"
            ),
            "b": _action_state(
                "task-two", False, decision_field="selected_decision"
            ),
        },
    }
    shuffled_from = {
        "probe-one": ("probe-two", "a"),
        "probe-two": ("probe-one", "a"),
    }
    bindings = {probe_id: _binding(probe_id) for probe_id in probe_ids}
    orders = {
        "probe-one": ("missing", "a", "shuffled", "b"),
        "probe-two": ("b", "shuffled", "a", "missing"),
    }
    reveal = {
        "schema_version": CAUSAL_PROBE_ASSIGNMENT_SCHEMA,
        "assignments": [
            {
                "probe_id": probe_id,
                "slots": [
                    {
                        "blind_label": _blind_label(probe_id, condition),
                        "condition": condition,
                    }
                    for condition in orders[probe_id]
                ],
            }
            for probe_id in probe_ids
        ],
    }

    specs: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    for index, probe_id in enumerate(probe_ids):
        donor_id, donor_condition = shuffled_from[probe_id]
        shuffled_payload = payloads[donor_id][donor_condition]
        specs.append(
            {
                "probe_id": probe_id,
                "stratum": {
                    "domain_id": f"domain-{index + 1}",
                    "receiver_family": "receiver-family-1",
                    "operator_id": "operator-1",
                },
                "field_id": "action-decision",
                "payload_format": ACTION_STATE_FORMAT,
                "critical_pointer": (
                    "/action/args/decision"
                    if probe_id == "probe-one"
                    else "/action/args/selected_decision"
                ),
                "call_binding": deepcopy(bindings[probe_id]),
                "payload_sha256": {
                    "a": sha256_ref(payloads[probe_id]["a"]),
                    "b": sha256_ref(payloads[probe_id]["b"]),
                    "missing": None,
                    "shuffled": sha256_ref(shuffled_payload),
                },
                "expected_output_sha256": {
                    "a": output_text_sha256(f"accept-{probe_id}"),
                    "b": output_text_sha256(f"reject-{probe_id}"),
                },
                "placebo_expected_disposition": {
                    "missing": PLACEBO_EXPECTATION,
                    "shuffled": PLACEBO_EXPECTATION,
                },
                "shuffled_from": {
                    "probe_id": donor_id,
                    "condition": donor_condition,
                },
            }
        )
        condition_payloads = {
            "a": payloads[probe_id]["a"],
            "b": payloads[probe_id]["b"],
            "missing": None,
            "shuffled": shuffled_payload,
        }
        results.append(
            {
                "schema_version": CAUSAL_PROBE_RESULT_SCHEMA,
                "probe_id": probe_id,
                "calls": [
                    _call(
                        probe_id,
                        condition,
                        bindings[probe_id],
                        condition_payloads[condition],
                    )
                    for condition in orders[probe_id]
                ],
            }
        )

    plan = {
        "schema_version": CAUSAL_PROBE_PLAN_SCHEMA,
        "status": PLAN_STATUS,
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "domains": ["domain-1", "domain-2"],
        "receiver_families": ["receiver-family-1"],
        "independent_operators": [
            {
                "operator_id": "operator-1",
                "independent": True,
                "attestation_sha256": _digest("operator-attestation"),
            }
        ],
        "preregistered_identity_envelope": {
            "schema_version": CAUSAL_PROBE_IDENTITY_ENVELOPE_SCHEMA,
            "status": PLAN_STATUS,
            "field_universe": {
                "schema_version": CAUSAL_PROBE_FIELD_UNIVERSE_SCHEMA,
                "fields": [
                    {
                        "field_id": "action-decision",
                        "canonical_pointer": "/action/args/decision",
                        "pointer_aliases": [
                            "/action/args/selected_decision"
                        ],
                        "semantic_definition_sha256": _digest(
                            "field-action-decision"
                        ),
                    }
                ],
            },
            "external_refusal_calibration_reference_set": {
                "schema_version": CAUSAL_PROBE_EXTERNAL_REFERENCE_SET_SCHEMA,
                "status": EXTERNAL_REFERENCE_STATUS,
                "purpose": EXTERNAL_REFERENCE_PURPOSE,
                "reference_set_id": "external-valid-payload-reference-1",
                "manifest_sha256": _digest("external-reference-manifest"),
                "selection_protocol_sha256": _digest(
                    "external-reference-selection"
                ),
                "validity_scorer_sha256": _digest("external-validity-scorer"),
                "source_id": "external-source-1",
                "source_attestation_sha256": _digest(
                    "external-source-attestation"
                ),
                "independent_specifier_id": "external-specifier-1",
                "independent_specification_sha256": _digest(
                    "external-independent-specification"
                ),
            },
        },
        "probe_specs": specs,
        "assignment_commitment_sha256": sha256_ref(reveal),
    }
    pack = {
        "schema_version": CAUSAL_PROBE_PACK_SCHEMA,
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "plan_sha256": sha256_ref(plan),
        "assignment_reveal": reveal,
        "probe_results": results,
    }
    return plan, pack


def _assignment(pack: dict[str, object], probe_id: str) -> dict[str, object]:
    return next(
        item
        for item in pack["assignment_reveal"]["assignments"]
        if item["probe_id"] == probe_id
    )


def _result(pack: dict[str, object], probe_id: str) -> dict[str, object]:
    return next(
        item for item in pack["probe_results"] if item["probe_id"] == probe_id
    )


def _call_for(
    pack: dict[str, object], probe_id: str, condition: str
) -> dict[str, object]:
    assignment = _assignment(pack, probe_id)
    slot_index = next(
        index
        for index, slot in enumerate(assignment["slots"])
        if slot["condition"] == condition
    )
    return _result(pack, probe_id)["calls"][slot_index]


def _spec(plan: dict[str, object], probe_id: str) -> dict[str, object]:
    return next(item for item in plan["probe_specs"] if item["probe_id"] == probe_id)


def _identity_envelope(plan: dict[str, object]) -> dict[str, object]:
    return plan["preregistered_identity_envelope"]


def _field_universe(plan: dict[str, object]) -> dict[str, object]:
    return _identity_envelope(plan)["field_universe"]


def _external_reference_set(plan: dict[str, object]) -> dict[str, object]:
    return _identity_envelope(plan)[
        "external_refusal_calibration_reference_set"
    ]


def _reseal(plan: dict[str, object], pack: dict[str, object], *, reveal: bool = False) -> None:
    if reveal:
        plan["assignment_commitment_sha256"] = sha256_ref(pack["assignment_reveal"])
    pack["plan_sha256"] = sha256_ref(plan)


def _reseal_response(call: dict[str, object]) -> None:
    call["response_sha256"] = sha256_ref(call["response"])


def _reseal_usage(call: dict[str, object]) -> None:
    call["usage_sha256"] = sha256_ref(call["usage"])


def _twin_date_fixture() -> tuple[dict[str, object], dict[str, object]]:
    plan, pack = _fixture()
    payloads = {
        "probe-one": {
            "a": _twin_date_action_state(
                "ship-from-delivery-date-only",
                delivery_date="2026-09-15",
                invoice_date="2026-08-31",
                instruction="Choose the shipment action from the adjacent deadline.",
            ),
            "b": _twin_date_action_state(
                "ship-from-delivery-date-only",
                delivery_date="2026-10-15",
                invoice_date="2026-08-31",
                instruction="Choose the shipment action from the adjacent deadline.",
            ),
        },
        "probe-two": {
            "a": _twin_date_action_state(
                "bill-from-invoice-date-only",
                delivery_date="2026-10-15",
                invoice_date="2026-08-31",
                instruction="Choose the billing action from the adjacent deadline.",
            ),
            "b": _twin_date_action_state(
                "bill-from-invoice-date-only",
                delivery_date="2026-10-15",
                invoice_date="2026-09-30",
                instruction="Choose the billing action from the adjacent deadline.",
            ),
        },
    }
    _field_universe(plan)["fields"] = [
        {
            "field_id": "delivery_date",
            "canonical_pointer": "/action/args/delivery_date",
            "pointer_aliases": ["/action/args/delivery_on"],
            "semantic_definition_sha256": _digest("field-delivery-date"),
        },
        {
            "field_id": "invoice_date",
            "canonical_pointer": "/action/args/invoice_date",
            "pointer_aliases": ["/action/args/deadline"],
            "semantic_definition_sha256": _digest("field-invoice-date"),
        },
    ]
    identities = {
        "probe-one": ("delivery_date", "/action/args/delivery_on"),
        "probe-two": ("invoice_date", "/action/args/deadline"),
    }
    for probe_id, (field_id, critical_pointer) in identities.items():
        spec = _spec(plan, probe_id)
        spec["field_id"] = field_id
        spec["critical_pointer"] = critical_pointer
        for condition in ("a", "b"):
            payload = payloads[probe_id][condition]
            call = _call_for(pack, probe_id, condition)
            call["payload"] = deepcopy(payload)
            call["payload_sha256"] = sha256_ref(payload)
            spec["payload_sha256"][condition] = sha256_ref(payload)

    for probe_id in identities:
        spec = _spec(plan, probe_id)
        donor = spec["shuffled_from"]
        shuffled_payload = payloads[donor["probe_id"]][donor["condition"]]
        shuffled_call = _call_for(pack, probe_id, "shuffled")
        shuffled_call["payload"] = deepcopy(shuffled_payload)
        shuffled_call["payload_sha256"] = sha256_ref(shuffled_payload)
        spec["payload_sha256"]["shuffled"] = sha256_ref(shuffled_payload)

    _reseal(plan, pack)
    return plan, pack


class CausalProbeV2Tests(unittest.TestCase):
    def test_valid_pack_is_bounded_nonclaim_and_counts_every_call(self):
        plan, pack = _fixture()

        plan_summary = validate_causal_probe_plan(plan)
        summary = validate_causal_probe_pack(plan, pack)

        self.assertEqual(plan_summary["schema_version"], CAUSAL_PROBE_SUMMARY_SCHEMA)
        self.assertEqual(plan_summary["strata"], 2)
        for diagnostic in (plan_summary, summary):
            self.assertFalse(diagnostic["semantic_invariance_checked"])
            self.assertFalse(diagnostic["composition_holdout_checked"])
            self.assertFalse(diagnostic["no_payload_accuracy_measured"])
            self.assertTrue(diagnostic["declared_field_universe_covered"])
            self.assertFalse(diagnostic["calibration_headline_seed_separated"])
            self.assertEqual(diagnostic["declared_field_count"], 1)
            self.assertEqual(diagnostic["covered_field_count"], 1)
            self.assertEqual(
                diagnostic["field_identity_coverage"], {"action-decision": 2}
            )
            self.assertEqual(
                diagnostic["field_universe_sha256"], sha256_ref(_field_universe(plan))
            )
            expected_alias_binding = {
                "schema_version": CAUSAL_PROBE_ALIAS_BINDING_SCHEMA,
                "bindings": [
                    {
                        "field_id": "action-decision",
                        "canonical_pointer": "/action/args/decision",
                        "pointer_aliases": [
                            "/action/args/selected_decision"
                        ],
                    }
                ],
            }
            self.assertEqual(
                diagnostic["alias_to_field_id_binding_sha256"],
                sha256_ref(expected_alias_binding),
            )
            self.assertEqual(
                diagnostic["preregistered_identity_envelope_sha256"],
                sha256_ref(_identity_envelope(plan)),
            )
            self.assertTrue(
                diagnostic[
                    "field_identity_and_external_refusal_calibration_same_envelope_bound"
                ]
            )
            self.assertFalse(diagnostic["preregistration_chronology_verified"])
            self.assertFalse(
                diagnostic["identity_envelope_external_anchor_verified"]
            )
            self.assertTrue(diagnostic["external_reference_set_identity_bound"])
            self.assertTrue(
                diagnostic[
                    "external_refusal_calibration_reference_set_identity_bound"
                ]
            )
            self.assertEqual(
                diagnostic["external_reference_set_id"],
                "external-valid-payload-reference-1",
            )
            self.assertEqual(
                diagnostic["external_reference_set_sha256"],
                sha256_ref(_external_reference_set(plan)),
            )
            self.assertFalse(diagnostic["external_reference_observations_validated"])
            self.assertEqual(
                diagnostic["external_refusal_calibration_purpose"],
                EXTERNAL_REFERENCE_PURPOSE,
            )
            self.assertTrue(
                diagnostic["independent_specification_commitment_bound"]
            )
            self.assertFalse(
                diagnostic["independent_specification_authenticated"]
            )
            self.assertFalse(
                diagnostic["external_refusal_calibration_gate_implemented"]
            )
            self.assertFalse(
                diagnostic[
                    "same_receiver_valid_ab_refusal_or_fallback_baseline_externally_anchored"
                ]
            )
            self.assertEqual(
                diagnostic["authoritative_coverage_unit"], "stable-field-id"
            )
            self.assertFalse(diagnostic["per_slot_arm_matrix_validated"])
            self.assertFalse(diagnostic["five_dimensional_strata_validated"])
            self.assertFalse(
                diagnostic["task_semantics_used_verdict_validated"]
            )
            self.assertEqual(
                diagnostic["required_empirical_worst_stratum_axes"],
                [
                    "domain",
                    "receiver-runtime",
                    "operator",
                    "principal",
                    "slot-class",
                ],
            )
        self.assertEqual(
            plan_summary["field_identity_coverage_basis"],
            "preregistered-probe-specs-only",
        )
        self.assertFalse(plan_summary["pack_binds_identity_envelope"])
        self.assertEqual(
            plan_summary["per_stable_semantic_slot"],
            [
                {
                    "field_id": "action-decision",
                    "planned_probes": 2,
                    "required_arm_matrix_preregistered": False,
                }
            ],
        )
        self.assertEqual(
            plan_summary["verdicts"]["payload_influenced_output"]["status"],
            "not-evaluated-plan-only",
        )
        self.assertEqual(summary["schema_version"], CAUSAL_PROBE_SUMMARY_SCHEMA)
        self.assertTrue(summary["structurally_valid"])
        self.assertTrue(summary["payload_dependence_checks_passed"])
        self.assertEqual(summary["gate_failures"], [])
        self.assertEqual(summary["calls"], 8)
        self.assertEqual(summary["intervention_pairs_passed"], 2)
        self.assertEqual(summary["placebo_calls_passed"], 4)
        self.assertEqual(summary["valid_ab_calls_denominator"], 4)
        self.assertEqual(summary["valid_ab_refusals_or_fallbacks_numerator"], 0)
        self.assertEqual(
            summary["field_identity_coverage_basis"], "validated-probe-results"
        )
        self.assertTrue(summary["pack_binds_identity_envelope"])
        self.assertEqual(
            summary["critical_pointer_usage"],
            {
                "/action/args/decision": 1,
                "/action/args/selected_decision": 1,
            },
        )
        self.assertTrue(summary["worst_stratum_checks_passed"])
        self.assertEqual(len(summary["per_stratum"]), 2)
        for index, stratum in enumerate(summary["per_stratum"], start=1):
            self.assertEqual(stratum["stratum"]["domain_id"], f"domain-{index}")
            self.assertEqual(stratum["probes"], 1)
            self.assertEqual(stratum["probes_passed"], 1)
            self.assertEqual(stratum["probes_failed"], 0)
            self.assertEqual(stratum["intervention_pairs_passed"], 1)
            self.assertEqual(stratum["intervention_pairs_failed"], 0)
            self.assertEqual(stratum["placebo_calls_passed"], 2)
            self.assertEqual(stratum["placebo_calls_failed"], 0)
            self.assertEqual(stratum["valid_ab_calls_denominator"], 2)
            self.assertEqual(
                stratum["valid_ab_refusals_or_fallbacks_numerator"], 0
            )
            self.assertTrue(stratum["checks_passed"])
        self.assertEqual(len(summary["per_stable_semantic_slot"]), 1)
        slot = summary["per_stable_semantic_slot"][0]
        self.assertEqual(slot["field_id"], "action-decision")
        self.assertEqual(slot["probes"], 2)
        self.assertEqual(slot["probes_passed"], 2)
        self.assertEqual(slot["intervention_pairs_passed"], 2)
        self.assertEqual(slot["placebo_calls_passed"], 4)
        self.assertTrue(slot["available_contract_checks_passed"])
        self.assertFalse(slot["required_arm_matrix_validated"])
        self.assertTrue(
            summary["worst_stable_semantic_slot_available_checks_passed"]
        )
        self.assertFalse(summary["pooled_intervention_pair_count_is_claim_gate"])
        self.assertEqual(
            summary["verdicts"]["payload_influenced_output"]["status"],
            "local-record-contract-passed",
        )
        self.assertTrue(
            summary["verdicts"]["payload_influenced_output"]["checks_passed"]
        )
        self.assertFalse(
            summary["verdicts"]["payload_influenced_output"]["claim_eligible"]
        )
        self.assertEqual(
            summary["verdicts"]["task_semantics_used"]["status"],
            "not-validated",
        )
        self.assertFalse(
            summary["verdicts"]["task_semantics_used"]["checks_passed"]
        )
        self.assertTrue(summary["token_accounting_complete"])
        self.assertEqual(summary["known_total_token_calls"], 8)
        self.assertEqual(summary["unknown_total_token_calls"], 0)
        self.assertEqual(summary["known_total_tokens"], 88)
        self.assertEqual(summary["inclusive_total_tokens"], 88)
        self.assertEqual(summary["evidence_boundary"], OFFLINE_EVIDENCE_BOUNDARY)
        self.assertFalse(summary["claim_eligible"])
        self.assertEqual(summary["provider_or_model_calls_by_validator"], 0)

    def test_all_new_schema_constants_are_v2(self):
        for schema in (
            CAUSAL_PROBE_PLAN_SCHEMA,
            CAUSAL_PROBE_PACK_SCHEMA,
            CAUSAL_PROBE_ASSIGNMENT_SCHEMA,
            CAUSAL_PROBE_RESULT_SCHEMA,
            CAUSAL_PROBE_CALL_SCHEMA,
            CAUSAL_PROBE_ALIAS_BINDING_SCHEMA,
            CAUSAL_PROBE_EXTERNAL_REFERENCE_SET_SCHEMA,
            CAUSAL_PROBE_FIELD_UNIVERSE_SCHEMA,
            CAUSAL_PROBE_IDENTITY_ENVELOPE_SCHEMA,
            CAUSAL_PROBE_RESPONSE_SCHEMA,
            CAUSAL_PROBE_USAGE_SCHEMA,
            CAUSAL_PROBE_SUMMARY_SCHEMA,
        ):
            with self.subTest(schema=schema):
                self.assertTrue(schema.endswith("/2"))

    def test_strict_json_entry_points_accept_canonical_fixture(self):
        plan, pack = _fixture()
        self.assertTrue(validate_causal_probe_plan_json(canonical_json(plan))["valid"])
        self.assertTrue(
            validate_causal_probe_pack_json(
                canonical_json(plan), canonical_json(pack)
            )["valid"]
        )

    def test_strict_json_rejects_duplicate_members(self):
        with self.assertRaisesRegex(VerificationError, "duplicate JSON member"):
            validate_causal_probe_plan_json('{"schema_version":"x","schema_version":"y"}')

    def test_v1_or_extra_fields_are_rejected(self):
        for mutation, message in (
            (lambda plan, _pack: plan.__setitem__("schema_version", "legacy/1"), "schema"),
            (lambda plan, _pack: plan.__setitem__("extra", True), "fields differ"),
        ):
            plan, pack = _fixture()
            mutation(plan, pack)
            with self.subTest(message=message):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_pack(plan, pack)

    def test_declared_operator_must_be_independent(self):
        plan, _pack = _fixture()
        plan["independent_operators"][0]["independent"] = False
        with self.assertRaisesRegex(VerificationError, "independent must be true"):
            validate_causal_probe_plan(plan)

    def test_receiver_family_maps_to_one_exact_model(self):
        plan, _pack = _fixture()
        _spec(plan, "probe-two")["call_binding"]["receiver_model_id"] = (
            "receiver-model-2"
        )
        with self.assertRaisesRegex(VerificationError, "multiple model IDs"):
            validate_causal_probe_plan(plan)

    def test_probe_context_cannot_be_relabelled_as_another_task(self):
        plan, _pack = _fixture()
        first_context = _spec(plan, "probe-one")["call_binding"][
            "non_payload_context_sha256"
        ]
        _spec(plan, "probe-two")["call_binding"][
            "non_payload_context_sha256"
        ] = first_context
        with self.assertRaisesRegex(VerificationError, "reuses another probe"):
            validate_causal_probe_plan(plan)

    def test_pointer_aliases_collapse_to_one_stable_field_identity(self):
        plan, pack = _fixture()

        summary = validate_causal_probe_pack(plan, pack)

        self.assertEqual(summary["declared_field_count"], 1)
        self.assertEqual(summary["covered_field_count"], 1)
        self.assertEqual(summary["field_identity_coverage"], {"action-decision": 2})
        self.assertEqual(
            summary["critical_pointer_usage"],
            {
                "/action/args/decision": 1,
                "/action/args/selected_decision": 1,
            },
        )
        self.assertTrue(summary["declared_field_universe_covered"])

    def test_identity_correct_salience_wrong_twin_date_pair_is_not_semantic_use_evidence(
        self,
    ):
        plan, pack = _twin_date_fixture()
        delivery_a = _call_for(pack, "probe-one", "a")["payload"]["action"][
            "args"
        ]
        delivery_b = _call_for(pack, "probe-one", "b")["payload"]["action"][
            "args"
        ]

        self.assertEqual(
            list(delivery_a),
            ["deadline", "instruction", "delivery_on", "task"],
        )
        self.assertIn("adjacent deadline", delivery_a["instruction"])
        self.assertEqual(delivery_a["task"], "ship-from-delivery-date-only")
        self.assertEqual(delivery_a["deadline"], delivery_b["deadline"])
        self.assertNotEqual(delivery_a["delivery_on"], delivery_b["delivery_on"])

        fields = {
            field["field_id"]: field for field in _field_universe(plan)["fields"]
        }
        self.assertEqual(set(fields), {"delivery_date", "invoice_date"})
        self.assertEqual(
            fields["delivery_date"]["pointer_aliases"],
            ["/action/args/delivery_on"],
        )
        self.assertEqual(
            fields["invoice_date"]["pointer_aliases"],
            ["/action/args/deadline"],
        )

        summary = validate_causal_probe_pack(plan, pack)

        self.assertTrue(summary["payload_dependence_checks_passed"])
        self.assertEqual(
            summary["field_identity_coverage"],
            {"delivery_date": 1, "invoice_date": 1},
        )
        self.assertEqual(
            summary["verdicts"]["payload_influenced_output"]["status"],
            "local-record-contract-passed",
        )
        self.assertTrue(
            summary["verdicts"]["payload_influenced_output"]["checks_passed"]
        )
        self.assertFalse(summary["semantic_invariance_checked"])
        self.assertFalse(summary["task_semantics_used_verdict_validated"])
        self.assertEqual(
            summary["verdicts"]["task_semantics_used"]["status"],
            "not-validated",
        )
        self.assertFalse(
            summary["verdicts"]["task_semantics_used"]["checks_passed"]
        )
        self.assertFalse(
            summary["verdicts"]["task_semantics_used"]["claim_eligible"]
        )

    def test_one_pointer_alias_cannot_own_multiple_stable_field_ids(self):
        plan, _pack = _fixture()
        _field_universe(plan)["fields"].append(
            {
                "field_id": "selected-decision-alias",
                "canonical_pointer": "/action/args/selected_decision",
                "pointer_aliases": [],
                "semantic_definition_sha256": _digest("alias-inflation"),
            }
        )

        with self.assertRaisesRegex(VerificationError, "multiple stable field IDs"):
            validate_causal_probe_plan(plan)

    def test_one_semantic_definition_cannot_split_into_multiple_field_ids(self):
        plan, _pack = _fixture()
        original_definition = _field_universe(plan)["fields"][0][
            "semantic_definition_sha256"
        ]
        _field_universe(plan)["fields"].append(
            {
                "field_id": "renamed-action-decision",
                "canonical_pointer": "/action/args/renamed_decision",
                "pointer_aliases": [],
                "semantic_definition_sha256": original_definition,
            }
        )

        with self.assertRaisesRegex(VerificationError, "semantic definition"):
            validate_causal_probe_plan(plan)

    def test_probe_must_reference_declared_field_identity_and_pointer(self):
        for mutation, message in (
            (
                lambda spec: spec.__setitem__("field_id", "undeclared-field"),
                "undeclared stable field ID",
            ),
            (
                lambda spec: spec.__setitem__(
                    "critical_pointer", "/action/args/undeclared_alias"
                ),
                "not registered to its stable field ID",
            ),
        ):
            plan, _pack = _fixture()
            mutation(_spec(plan, "probe-one"))
            with self.subTest(message=message):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_plan(plan)

    def test_uncovered_declared_field_is_reported_without_alias_inflation(self):
        plan, _pack = _fixture()
        _field_universe(plan)["fields"].append(
            {
                "field_id": "action-priority",
                "canonical_pointer": "/action/args/priority",
                "pointer_aliases": [],
                "semantic_definition_sha256": _digest("field-action-priority"),
            }
        )

        summary = validate_causal_probe_plan(plan)

        self.assertFalse(summary["declared_field_universe_covered"])
        self.assertEqual(summary["declared_field_count"], 2)
        self.assertEqual(summary["covered_field_count"], 1)
        self.assertEqual(
            summary["field_identity_coverage"],
            {"action-decision": 2, "action-priority": 0},
        )

    def test_external_reference_set_is_frozen_identity_not_observation(self):
        for field, value, message in (
            ("status", "completed-results", "identity-only"),
            ("purpose", "same-receiver-calibration", "purpose differs"),
            ("manifest_sha256", "not-a-digest", "sha256 reference"),
            (
                "independent_specification_sha256",
                "not-a-digest",
                "sha256 reference",
            ),
        ):
            plan, _pack = _fixture()
            _external_reference_set(plan)[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_plan(plan)

    def test_identity_envelope_is_strict_and_frozen(self):
        for mutate, message in (
            (
                lambda envelope: envelope.__setitem__("extra", True),
                "fields differ",
            ),
            (
                lambda envelope: envelope.__setitem__("status", "results-known"),
                "status differs",
            ),
        ):
            plan, _pack = _fixture()
            mutate(_identity_envelope(plan))
            with self.subTest(message=message):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_plan(plan)

    def test_one_envelope_binds_alias_map_and_external_calibration_identity(self):
        for mutate in (
            lambda plan: _field_universe(plan)["fields"][0][
                "pointer_aliases"
            ].append("/action/args/alternate_decision"),
            lambda plan: _external_reference_set(plan).__setitem__(
                "manifest_sha256", _digest("changed-external-manifest")
            ),
        ):
            plan, pack = _fixture()
            original_envelope_digest = sha256_ref(_identity_envelope(plan))
            mutate(plan)
            self.assertNotEqual(
                sha256_ref(_identity_envelope(plan)), original_envelope_digest
            )
            with self.assertRaisesRegex(VerificationError, "does not bind the plan"):
                validate_causal_probe_pack(plan, pack)

    def test_plan_and_pack_coordinated_rehash_is_not_misreported_as_chronology(self):
        plan, pack = _fixture()
        _external_reference_set(plan)["manifest_sha256"] = _digest(
            "coordinated-rehash-manifest"
        )
        _reseal(plan, pack)

        summary = validate_causal_probe_pack(plan, pack)

        self.assertTrue(summary["pack_binds_identity_envelope"])
        self.assertFalse(summary["preregistration_chronology_verified"])
        self.assertFalse(summary["identity_envelope_external_anchor_verified"])

    def test_constant_output_adapter_is_preserved_as_negative_outcome(self):
        plan, pack = _fixture()
        a = _call_for(pack, "probe-one", "a")
        b = _call_for(pack, "probe-one", "b")
        b["response"]["output_text"] = a["response"]["output_text"]
        b["response"]["output_sha256"] = a["response"]["output_sha256"]
        _reseal_response(b)

        summary = validate_causal_probe_pack(plan, pack)
        self.assertTrue(summary["structurally_valid"])
        self.assertFalse(summary["payload_dependence_checks_passed"])
        self.assertIn("constant-output:probe-one", summary["gate_failures"])
        self.assertIn(
            "expected-output-mismatch:probe-one:b", summary["gate_failures"]
        )
        self.assertEqual(summary["intervention_pairs_passed"], 1)
        slot = summary["per_stable_semantic_slot"][0]
        self.assertEqual(slot["probes_passed"], 1)
        self.assertEqual(slot["probes_failed"], 1)
        self.assertFalse(slot["available_contract_checks_passed"])
        self.assertFalse(
            summary["worst_stable_semantic_slot_available_checks_passed"]
        )
        self.assertEqual(
            summary["verdicts"]["payload_influenced_output"]["status"],
            "local-record-contract-failed",
        )
        self.assertFalse(
            summary["verdicts"]["payload_influenced_output"]["checks_passed"]
        )
        self.assertFalse(
            summary["verdicts"]["task_semantics_used"]["checks_passed"]
        )

    def test_swapped_or_wrong_expected_output_is_preserved_as_negative(self):
        plan, pack = _fixture()
        a = _call_for(pack, "probe-one", "a")
        b = _call_for(pack, "probe-one", "b")
        a_text = a["response"]["output_text"]
        b_text = b["response"]["output_text"]
        a["response"]["output_text"] = b_text
        a["response"]["output_sha256"] = output_text_sha256(b_text)
        b["response"]["output_text"] = a_text
        b["response"]["output_sha256"] = output_text_sha256(a_text)
        _reseal_response(a)
        _reseal_response(b)

        summary = validate_causal_probe_pack(plan, pack)
        self.assertFalse(summary["payload_dependence_checks_passed"])
        self.assertIn(
            "expected-output-mismatch:probe-one:a", summary["gate_failures"]
        )
        self.assertIn(
            "expected-output-mismatch:probe-one:b", summary["gate_failures"]
        )

    def test_noncompleted_a_or_b_is_preserved_as_negative_outcome(self):
        plan, pack = _fixture()
        a = _call_for(pack, "probe-one", "a")
        a["response"].update(
            {
                "disposition": "refused",
                "fallback_mode": None,
                "output_text": None,
                "output_sha256": None,
            }
        )
        _reseal_response(a)

        summary = validate_causal_probe_pack(plan, pack)
        self.assertFalse(summary["payload_dependence_checks_passed"])
        self.assertIn(
            "intervention-not-completed:probe-one:a", summary["gate_failures"]
        )
        self.assertIn(
            "expected-output-mismatch:probe-one:a", summary["gate_failures"]
        )
        self.assertEqual(summary["valid_ab_calls_denominator"], 4)
        self.assertEqual(summary["valid_ab_refusals_or_fallbacks_numerator"], 1)
        self.assertFalse(summary["worst_stratum_checks_passed"])
        by_domain = {
            item["stratum"]["domain_id"]: item for item in summary["per_stratum"]
        }
        self.assertEqual(by_domain["domain-1"]["probes_passed"], 0)
        self.assertEqual(by_domain["domain-1"]["probes_failed"], 1)
        self.assertEqual(
            by_domain["domain-1"]["valid_ab_refusals_or_fallbacks_numerator"],
            1,
        )
        self.assertFalse(by_domain["domain-1"]["checks_passed"])
        self.assertEqual(by_domain["domain-2"]["probes_passed"], 1)
        self.assertEqual(by_domain["domain-2"]["probes_failed"], 0)
        self.assertTrue(by_domain["domain-2"]["checks_passed"])

    def test_mismatched_context_model_settings_or_capsule_is_rejected(self):
        fields = (
            "non_payload_context_sha256",
            "model_settings_sha256",
            "capsule_sha256",
        )
        for field in fields:
            plan, pack = _fixture()
            b = _call_for(pack, "probe-one", "b")
            b["binding"][field] = _digest(f"different-{field}")
            with self.subTest(field=field):
                with self.assertRaisesRegex(VerificationError, "binding differs"):
                    validate_causal_probe_pack(plan, pack)

    def test_extra_payload_difference_outside_pointer_is_rejected(self):
        plan, pack = _fixture()
        b = _call_for(pack, "probe-one", "b")
        b["payload"]["action"]["args"]["unregistered_difference"] = True
        b["payload_sha256"] = sha256_ref(b["payload"])
        _spec(plan, "probe-one")["payload_sha256"]["b"] = b["payload_sha256"]
        _reseal(plan, pack)

        with self.assertRaisesRegex(VerificationError, "outside the critical JSON pointer"):
            validate_causal_probe_pack(plan, pack)

    def test_a_and_b_payloads_must_each_be_schema_valid(self):
        plan, pack = _fixture()
        b = _call_for(pack, "probe-one", "b")
        del b["payload"]["act"]
        b["payload_sha256"] = sha256_ref(b["payload"])
        _spec(plan, "probe-one")["payload_sha256"]["b"] = b["payload_sha256"]
        _reseal(plan, pack)

        with self.assertRaisesRegex(VerificationError, "not schema-valid"):
            validate_causal_probe_pack(plan, pack)

    def test_critical_pointer_must_exist_and_target_one_scalar(self):
        for pointer, message in (
            ("/action/args/absent", "does not exist"),
            ("/action/args", "one scalar"),
        ):
            plan, pack = _fixture()
            _spec(plan, "probe-one")["critical_pointer"] = pointer
            _field_universe(plan)["fields"][0]["pointer_aliases"].append(pointer)
            _reseal(plan, pack)
            with self.subTest(pointer=pointer):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_pack(plan, pack)

    def test_absent_per_stratum_plan_probe_is_rejected(self):
        plan, pack = _fixture()
        plan["probe_specs"] = plan["probe_specs"][:1]
        pack["probe_results"] = pack["probe_results"][:1]
        pack["assignment_reveal"]["assignments"] = pack["assignment_reveal"][
            "assignments"
        ][:1]
        _reseal(plan, pack, reveal=True)

        with self.assertRaisesRegex(VerificationError, "absent per-stratum probes"):
            validate_causal_probe_pack(plan, pack)

    def test_absent_probe_result_is_rejected(self):
        plan, pack = _fixture()
        pack["probe_results"].pop()
        with self.assertRaisesRegex(VerificationError, "absent per-stratum probes"):
            validate_causal_probe_pack(plan, pack)

    def test_missing_placebo_call_is_rejected(self):
        plan, pack = _fixture()
        result = _result(pack, "probe-one")
        missing = _call_for(pack, "probe-one", "missing")
        result["calls"].remove(missing)

        with self.assertRaisesRegex(VerificationError, "both placebo variants"):
            validate_causal_probe_pack(plan, pack)

    def test_missing_placebo_must_carry_no_payload(self):
        plan, pack = _fixture()
        missing = _call_for(pack, "probe-one", "missing")
        missing["payload"] = _action_state("task-one", True)
        missing["payload_sha256"] = sha256_ref(missing["payload"])

        with self.assertRaisesRegex(VerificationError, "must carry no payload"):
            validate_causal_probe_pack(plan, pack)

    def test_completed_placebos_are_preserved_as_negative_outcomes(self):
        for condition in ("missing", "shuffled"):
            plan, pack = _fixture()
            placebo = _call_for(pack, "probe-one", condition)
            placebo["response"]["disposition"] = "completed"
            placebo["response"]["fallback_mode"] = None
            if placebo["response"]["output_text"] is None:
                placebo["response"]["output_text"] = "constant"
                placebo["response"]["output_sha256"] = output_text_sha256("constant")
            _reseal_response(placebo)
            with self.subTest(condition=condition):
                summary = validate_causal_probe_pack(plan, pack)
                self.assertFalse(summary["payload_dependence_checks_passed"])
                self.assertIn(
                    f"placebo-did-not-refuse-or-fallback:probe-one:{condition}",
                    summary["gate_failures"],
                )

    def test_shuffled_placebo_must_equal_other_probe_payload(self):
        plan, pack = _fixture()
        shuffled = _call_for(pack, "probe-one", "shuffled")
        shuffled["payload"] = _action_state("task-one", True)
        shuffled["payload_sha256"] = sha256_ref(shuffled["payload"])
        _spec(plan, "probe-one")["payload_sha256"]["shuffled"] = shuffled[
            "payload_sha256"
        ]
        _reseal(plan, pack)

        with self.assertRaisesRegex(VerificationError, "commitment differs from its source"):
            validate_causal_probe_pack(plan, pack)

    def test_replayed_response_digest_is_rejected(self):
        plan, pack = _fixture()
        first = _call_for(pack, "probe-one", "missing")
        second = _call_for(pack, "probe-two", "missing")
        second["response"] = deepcopy(first["response"])
        second["response_sha256"] = first["response_sha256"]

        with self.assertRaisesRegex(VerificationError, "replays a response"):
            validate_causal_probe_pack(plan, pack)

    def test_unknown_total_stays_unknown_and_is_not_summed_as_zero(self):
        plan, pack = _fixture()
        call = _call_for(pack, "probe-one", "a")
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

        summary = validate_causal_probe_pack(plan, pack)
        self.assertFalse(summary["payload_dependence_checks_passed"])
        self.assertFalse(summary["token_accounting_complete"])
        self.assertIn(
            "unknown-inclusive-token-total:probe-one:a",
            summary["gate_failures"],
        )
        self.assertEqual(summary["unknown_total_token_calls"], 1)
        self.assertEqual(summary["known_total_token_calls"], 7)
        self.assertEqual(summary["known_total_tokens"], 77)
        self.assertIsNone(summary["inclusive_total_tokens"])

    def test_unknown_components_cannot_be_coerced_to_zero_total(self):
        plan, pack = _fixture()
        call = _call_for(pack, "probe-one", "a")
        call["usage"].update(
            {
                "output_tokens": None,
                "reasoning_tokens": None,
                "unclassified_tokens": None,
                "provider_total_tokens": None,
                "total_tokens": 0,
                "hidden_accounting": "not-reported",
            }
        )
        _reseal_usage(call)

        with self.assertRaisesRegex(VerificationError, "unclosed component"):
            validate_causal_probe_pack(plan, pack)

    def test_usage_total_must_reconcile_and_bool_is_not_a_count(self):
        for total, message in ((12, "reconcile"), (True, "nonnegative integer")):
            plan, pack = _fixture()
            call = _call_for(pack, "probe-one", "a")
            call["usage"]["provider_total_tokens"] = None
            call["usage"]["total_tokens"] = total
            _reseal_usage(call)
            with self.subTest(total=total):
                with self.assertRaisesRegex(VerificationError, message):
                    validate_causal_probe_pack(plan, pack)

    def test_assignment_and_plan_digest_tampering_are_rejected(self):
        plan, pack = _fixture()
        pack["assignment_reveal"]["assignments"][0]["slots"].reverse()
        with self.assertRaisesRegex(VerificationError, "assignment commitment mismatch"):
            validate_causal_probe_pack(plan, pack)

        plan, pack = _fixture()
        pack["plan_sha256"] = _digest("wrong-plan")
        with self.assertRaisesRegex(VerificationError, "does not bind the plan"):
            validate_causal_probe_pack(plan, pack)

    def test_preregistered_expected_outputs_must_flip(self):
        plan, _pack = _fixture()
        spec = _spec(plan, "probe-one")
        spec["expected_output_sha256"]["b"] = spec["expected_output_sha256"]["a"]
        with self.assertRaisesRegex(VerificationError, "expected A/B outputs must flip"):
            validate_causal_probe_plan(plan)


if __name__ == "__main__":
    unittest.main()
