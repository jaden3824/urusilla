"""Mutation tests for the standalone, non-claim causal-probe v2 contract."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.causal_probe_v2 import (
    ACTION_STATE_FORMAT,
    CAUSAL_PROBE_ASSIGNMENT_SCHEMA,
    CAUSAL_PROBE_CALL_SCHEMA,
    CAUSAL_PROBE_PACK_SCHEMA,
    CAUSAL_PROBE_PLAN_SCHEMA,
    CAUSAL_PROBE_RESPONSE_SCHEMA,
    CAUSAL_PROBE_RESULT_SCHEMA,
    CAUSAL_PROBE_SUMMARY_SCHEMA,
    CAUSAL_PROBE_USAGE_SCHEMA,
    CONDITIONS,
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


def _action_state(task: str, decision: bool) -> dict[str, object]:
    return {
        "format": ACTION_STATE_FORMAT,
        "act": "propose",
        "goal": {"p": "choose", "a": [task], "n": False, "src": "fixture"},
        "state": [],
        "constraints": [],
        "action": {
            "name": "choose",
            "args": {"decision": decision, "task": task},
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
            "a": _action_state("task-two", True),
            "b": _action_state("task-two", False),
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
                "payload_format": ACTION_STATE_FORMAT,
                "critical_pointer": "/action/args/decision",
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


def _reseal(plan: dict[str, object], pack: dict[str, object], *, reveal: bool = False) -> None:
    if reveal:
        plan["assignment_commitment_sha256"] = sha256_ref(pack["assignment_reveal"])
    pack["plan_sha256"] = sha256_ref(plan)


def _reseal_response(call: dict[str, object]) -> None:
    call["response_sha256"] = sha256_ref(call["response"])


def _reseal_usage(call: dict[str, object]) -> None:
    call["usage_sha256"] = sha256_ref(call["usage"])


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
            self.assertFalse(diagnostic["declared_field_universe_covered"])
            self.assertFalse(diagnostic["calibration_headline_seed_separated"])
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
            summary["critical_pointer_coverage"],
            {"/action/args/decision": 2},
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
