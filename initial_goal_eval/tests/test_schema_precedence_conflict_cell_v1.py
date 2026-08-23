"""Mutation tests for counterbalanced schema-precedence contract /3."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from unittest import TestCase

from initial_goal_eval.schema_precedence_conflict_cell_v1 import (
    BLOCK_IDS,
    CELL_IDS,
    EVIDENCE_BOUNDARY,
    EXECUTION_ORDER,
    FROZEN_PLAN_SHA256,
    OBSERVATION_SCHEMA,
    SchemaPrecedenceConflictError,
    build_schema_precedence_conflict_plan,
    expected_output_text,
    score_schema_precedence_conflict,
    validate_schema_precedence_conflict_plan,
)
from urusilla_hybrid_runtime.canonical import canonical_json, strict_json_loads


BOUNDARY_FLAGS = (
    "claim_eligible",
    "adoption_evidence",
    "conformance_evidence",
    "efficiency_evidence",
    "general_language_evidence",
    "independent_evaluation_evidence",
)


def _observation(
    plan: dict[str, object], outputs: dict[str, str] | None = None
) -> dict[str, object]:
    selected = outputs or {
        cell_id: expected_output_text(cell_id) for cell_id in CELL_IDS
    }
    cells = {cell["cell_id"]: cell for cell in plan["cells"]}
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "plan_sha256": FROZEN_PLAN_SHA256,
        "observations": [
            {
                "cell_id": cell_id,
                "context_id": cells[cell_id]["context_id"],
                "request_preimage": cells[cell_id]["request_preimage"],
                "output_text": selected[cell_id],
            }
            for cell_id in EXECUTION_ORDER
        ],
    }


def _row(observation: dict[str, object], cell_id: str) -> dict[str, object]:
    return next(
        row for row in observation["observations"] if row["cell_id"] == cell_id
    )


def _output(
    disposition: object,
    *,
    reason: str,
    binding_verified: object,
) -> str:
    return canonical_json(
        {
            "disposition": disposition,
            "reason_code": reason,
            "schema_binding_verified": binding_verified,
        }
    )


class SchemaPrecedenceConflictCellV3Tests(TestCase):
    def test_two_blocks_are_counterbalanced_opaque_and_byte_matched(self):
        plan = build_schema_precedence_conflict_plan()
        summary = validate_schema_precedence_conflict_plan(plan)
        cells = {cell["cell_id"]: cell for cell in plan["cells"]}
        requests = {
            cell_id: strict_json_loads(cells[cell_id]["request_preimage"])
            for cell_id in CELL_IDS
        }

        self.assertEqual(plan["design"]["block_ids"], list(BLOCK_IDS))
        self.assertEqual(len(plan["cells"]), 8)
        self.assertEqual(
            summary["resolved_schema_actions"],
            {
                "cell-01": "strict-refuse",
                "cell-02": "fallback",
                "cell-05": "fallback",
                "cell-06": "strict-refuse",
            },
        )
        resolved_lengths = {
            len(cells[cell_id]["request_preimage"].encode())
            for cell_id in ("cell-01", "cell-02", "cell-05", "cell-06")
        }
        unavailable_lengths = {
            len(cells[cell_id]["request_preimage"].encode())
            for cell_id in ("cell-03", "cell-04", "cell-07", "cell-08")
        }
        self.assertEqual(len(resolved_lengths), 1)
        self.assertEqual(len(unavailable_lengths), 1)
        schema_lengths = {
            len(
                requests[cell_id]["local_resources"][0]["content_utf8"].encode()
            )
            for cell_id in ("cell-01", "cell-02", "cell-05", "cell-06")
        }
        self.assertEqual(schema_lengths, {437})

        uris = {
            request["query"]["schema_reference"] for request in requests.values()
        }
        self.assertEqual(len(uris), 4)
        for uri in uris:
            self.assertRegex(uri, r"^urn:urusilla:eval:spc:[0-9a-f]{8}:1$")
            for word in ("strict", "refuse", "fallback", "permissive", "allow"):
                self.assertNotIn(word, uri.lower())

        for resolved_id, unavailable_id in (
            ("cell-01", "cell-03"),
            ("cell-02", "cell-04"),
            ("cell-05", "cell-07"),
            ("cell-06", "cell-08"),
        ):
            matched = deepcopy(requests[resolved_id])
            matched["local_resources"] = []
            matched["context_binding"] = requests[unavailable_id]["context_binding"]
            self.assertEqual(matched, requests[unavailable_id])

    def test_oracle_literals_are_visible_in_all_eight_preimages(self):
        plan = build_schema_precedence_conflict_plan()
        for cell in plan["cells"]:
            with self.subTest(cell_id=cell["cell_id"]):
                request = strict_json_loads(cell["request_preimage"])
                expected = strict_json_loads(expected_output_text(cell["cell_id"]))
                table = {
                    row["condition"]: row
                    for row in request["response_contract"]["resolution_table"]
                }
                if request["local_resources"]:
                    schema = strict_json_loads(
                        request["local_resources"][0]["content_utf8"]
                    )
                    mapping = table["resolved-exact"]
                    self.assertEqual(
                        expected["disposition"],
                        schema["properties"]["disposition"]["const"],
                    )
                else:
                    mapping = table["resource-unavailable"]
                    self.assertEqual(expected["disposition"], mapping["disposition"])
                self.assertEqual(expected["reason_code"], mapping["reason_code"])
                self.assertIs(
                    expected["schema_binding_verified"],
                    mapping["schema_binding_verified"],
                )
                self.assertIn(expected["disposition"], cell["request_preimage"])
                self.assertIn(expected["reason_code"], cell["request_preimage"])

    def test_fresh_contexts_and_literal_randomized_order_are_enforced(self):
        plan = build_schema_precedence_conflict_plan()
        validation = validate_schema_precedence_conflict_plan(plan)
        contexts = [cell["context_id"] for cell in plan["cells"]]

        self.assertEqual(len(set(contexts)), 8)
        self.assertEqual(len({len(context_id) for context_id in contexts}), 1)
        self.assertEqual(plan["execution"]["execution_order"], list(EXECUTION_ORDER))
        self.assertEqual(validation["execution_order"], list(EXECUTION_ORDER))
        self.assertTrue(validation["execution_order_contract_verified"])
        self.assertTrue(validation["fresh_independent_context_contract_verified"])
        self.assertFalse(validation["runtime_execution_order_verified"])
        self.assertFalse(validation["runtime_context_isolation_verified"])
        for cell in plan["cells"]:
            binding = strict_json_loads(cell["request_preimage"])["context_binding"]
            self.assertEqual(binding["context_id"], cell["context_id"])
            self.assertTrue(binding["fresh_independent_context"])
            self.assertFalse(binding["cross_cell_conversation"])
            self.assertFalse(binding["cross_cell_memory"])
            self.assertIsNone(binding["parent_context_id"])

        observation = _observation(plan)
        observation["observations"][0], observation["observations"][1] = (
            observation["observations"][1],
            observation["observations"][0],
        )
        with self.assertRaisesRegex(
            SchemaPrecedenceConflictError, "execution order"
        ):
            score_schema_precedence_conflict(plan, observation)

        observation = _observation(plan)
        _row(observation, "cell-01")["context_id"] = "ctx-reused000"
        with self.assertRaisesRegex(SchemaPrecedenceConflictError, "context_id"):
            score_schema_precedence_conflict(plan, observation)

    def test_exact_outputs_require_both_semantics_oriented_block_dids(self):
        plan = build_schema_precedence_conflict_plan()
        score = score_schema_precedence_conflict(plan, _observation(plan))

        self.assertTrue(score["contract_gate_passed"])
        self.assertEqual(score["contract_accuracy"], 1.0)
        self.assertEqual(
            score["block_difference_in_differences"],
            {"block-0": 1, "block-1": 1},
        )
        self.assertEqual(
            score["block_scores"]["block-0"][
                "identity_order_difference_in_differences"
            ],
            1,
        )
        self.assertEqual(
            score["block_scores"]["block-1"][
                "identity_order_difference_in_differences"
            ],
            -1,
        )
        self.assertEqual(score["counterbalanced_contract_utility"], 1.0)
        self.assertIsNone(score["counterbalanced_contract_zero_reason"])
        self.assertIsNone(score["precedence_causal_utility"])
        self.assertEqual(
            score["precedence_causal_utility_reason"],
            "runtime-isolation-and-order-receipts-absent",
        )

    def test_turn_index_shortcut_can_pass_contract_but_never_causal_utility(self):
        """A memorized eight-turn answer sequence is not a runtime receipt."""

        plan = build_schema_precedence_conflict_plan()
        turn_index_outputs = (
            _output(
                "strict-refuse",
                reason="schema-authoritative",
                binding_verified=True,
            ),
            _output(
                "fallback",
                reason="schema-resource-unavailable",
                binding_verified=False,
            ),
            _output(
                "fallback",
                reason="schema-resource-unavailable",
                binding_verified=False,
            ),
            _output(
                "strict-refuse",
                reason="schema-authoritative",
                binding_verified=True,
            ),
            _output(
                "fallback", reason="schema-authoritative", binding_verified=True
            ),
            _output(
                "fallback", reason="schema-authoritative", binding_verified=True
            ),
            _output(
                "fallback",
                reason="schema-resource-unavailable",
                binding_verified=False,
            ),
            _output(
                "fallback",
                reason="schema-resource-unavailable",
                binding_verified=False,
            ),
        )
        outputs = dict(zip(EXECUTION_ORDER, turn_index_outputs))
        score = score_schema_precedence_conflict(
            plan, _observation(plan, outputs)
        )

        self.assertEqual(score["counterbalanced_contract_utility"], 1.0)
        self.assertIsNone(score["precedence_causal_utility"])
        self.assertFalse(score["runtime_execution_order_verified"])
        self.assertFalse(score["runtime_context_isolation_verified"])
        self.assertEqual(
            score["precedence_causal_utility_reason"],
            "runtime-isolation-and-order-receipts-absent",
        )

    def test_registry_zero_when_present_shortcut_scores_zero(self):
        """Exact audited interaction: presence + registry[0] => strict."""

        plan = build_schema_precedence_conflict_plan()
        outputs: dict[str, str] = {}
        for cell in plan["cells"]:
            if cell["resource_level"] == "resolved":
                disposition = (
                    "strict-refuse" if cell["registry_position"] == 0 else "fallback"
                )
                outputs[cell["cell_id"]] = _output(
                    disposition,
                    reason="schema-authoritative",
                    binding_verified=True,
                )
            else:
                outputs[cell["cell_id"]] = _output(
                    "fallback",
                    reason="schema-resource-unavailable",
                    binding_verified=False,
                )
        score = score_schema_precedence_conflict(plan, _observation(plan, outputs))

        self.assertEqual(
            score["block_difference_in_differences"],
            {"block-0": 1, "block-1": -1},
        )
        self.assertEqual(score["counterbalanced_contract_utility"], 0.0)
        self.assertEqual(
            score["counterbalanced_contract_zero_reason"],
            "counterbalanced-semantic-effect-missing",
        )
        self.assertIsNone(score["precedence_causal_utility"])

    def test_all_fallback_and_uri_label_interactions_score_zero(self):
        plan = build_schema_precedence_conflict_plan()
        all_fallback = {
            cell["cell_id"]: _output(
                "fallback",
                reason=(
                    "schema-authoritative"
                    if cell["resource_level"] == "resolved"
                    else "schema-resource-unavailable"
                ),
                binding_verified=cell["resource_level"] == "resolved",
            )
            for cell in plan["cells"]
        }
        score = score_schema_precedence_conflict(
            plan, _observation(plan, all_fallback)
        )
        self.assertEqual(
            score["block_difference_in_differences"],
            {"block-0": 0, "block-1": 0},
        )
        self.assertEqual(score["counterbalanced_contract_utility"], 0.0)

        uri_interaction = dict(all_fallback)
        # Make level-0 strict in unavailable controls: opaque identity leakage.
        for cell_id in ("cell-03", "cell-07"):
            uri_interaction[cell_id] = _output(
                "strict-refuse",
                reason="schema-resource-unavailable",
                binding_verified=False,
            )
        score = score_schema_precedence_conflict(
            plan, _observation(plan, uri_interaction)
        )
        self.assertEqual(score["counterbalanced_contract_utility"], 0.0)
        self.assertEqual(
            score["counterbalanced_contract_zero_reason"],
            "unavailable-semantic-label-difference-present",
        )

    def test_malformed_missing_list_dict_and_surrogate_actions_fail_deterministically(self):
        plan = build_schema_precedence_conflict_plan()
        cases = (
            canonical_json(
                {
                    "reason_code": "schema-authoritative",
                    "schema_binding_verified": True,
                }
            ),
            _output([], reason="schema-authoritative", binding_verified=True),
            _output({}, reason="schema-authoritative", binding_verified=True),
            "not-json",
            "\ud800",
        )
        for malformed in cases:
            with self.subTest(malformed=repr(malformed)):
                observation = _observation(plan)
                _row(observation, "cell-01")["output_text"] = malformed
                score = score_schema_precedence_conflict(plan, observation)
                cell_score = next(
                    row
                    for row in score["cell_scores"]
                    if row["cell_id"] == "cell-01"
                )
                self.assertIsNone(cell_score["strict_refuse_indicator"])
                self.assertIsNotNone(cell_score["parse_error"])
                self.assertEqual(
                    score["block_difference_in_differences"],
                    {"block-0": None, "block-1": None},
                )
                self.assertEqual(score["counterbalanced_contract_utility"], 0.0)
                self.assertEqual(
                    score["counterbalanced_contract_zero_reason"],
                    "contract-output-failure",
                )
                if malformed == "\ud800":
                    self.assertIsNone(cell_score["observed_output_sha256"])

    def test_type_exact_plan_output_and_literal_pins_reject_mutation(self):
        plan = build_schema_precedence_conflict_plan()
        self.assertEqual(
            validate_schema_precedence_conflict_plan(plan)["plan_sha256"],
            FROZEN_PLAN_SHA256,
        )
        for mutate in (
            lambda p: p.__setitem__("claim_eligible", 0),
            lambda p: p["scoring_rule"]["strict_refuse_indicator"].__setitem__(
                "fallback", False
            ),
        ):
            mutated = deepcopy(plan)
            mutate(mutated)
            with self.assertRaisesRegex(
                SchemaPrecedenceConflictError, "exact typed frozen"
            ):
                validate_schema_precedence_conflict_plan(mutated)

        mutated = deepcopy(plan)
        mutated["cells"][0]["request_preimage"] += " "
        mutated["cells"][0]["request_sha256"] = "sha256:" + hashlib.sha256(
            mutated["cells"][0]["request_preimage"].encode()
        ).hexdigest()
        with self.assertRaisesRegex(
            SchemaPrecedenceConflictError, "exact typed frozen"
        ):
            validate_schema_precedence_conflict_plan(mutated)

        observation = _observation(plan)
        _row(observation, "cell-01")["output_text"] = _output(
            "strict-refuse", reason="schema-authoritative", binding_verified=1
        )
        score = score_schema_precedence_conflict(plan, observation)
        self.assertEqual(score["counterbalanced_contract_utility"], 0.0)
        self.assertEqual(
            score["counterbalanced_contract_zero_reason"],
            "contract-output-failure",
        )

    def test_caller_verdict_and_preimage_swap_are_rejected(self):
        plan = build_schema_precedence_conflict_plan()
        observation = _observation(plan)
        _row(observation, "cell-01")["claimed_pass"] = True
        with self.assertRaisesRegex(
            SchemaPrecedenceConflictError, "keys must be exactly"
        ):
            score_schema_precedence_conflict(plan, observation)

        observation = _observation(plan)
        _row(observation, "cell-01")["request_preimage"] = _row(
            observation, "cell-02"
        )["request_preimage"]
        with self.assertRaisesRegex(
            SchemaPrecedenceConflictError, "does not match frozen bytes"
        ):
            score_schema_precedence_conflict(plan, observation)

    def test_all_evidence_boundaries_remain_false(self):
        plan = build_schema_precedence_conflict_plan()
        validation = validate_schema_precedence_conflict_plan(plan)
        score = score_schema_precedence_conflict(plan, _observation(plan))

        self.assertIn("always null", plan["scoring_rule"]["causal_result"])
        for record in (plan, validation, score):
            self.assertEqual(record["evidence_boundary"], EVIDENCE_BOUNDARY)
            for flag in BOUNDARY_FLAGS:
                self.assertIs(record[flag], False)
            self.assertIs(record["runtime_execution_order_verified"], False)
            self.assertIs(record["runtime_context_isolation_verified"], False)
        for record in (plan, validation, score):
            self.assertIsNone(record["precedence_causal_utility"])
            self.assertEqual(
                record["precedence_causal_utility_reason"],
                "runtime-isolation-and-order-receipts-absent",
            )
