"""Focused offline checks for the public methodological counterexample."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from interop_lab.interop_lab import ValidationError
from interop_lab.solicited_matched_experiment import sha256_ref
from interop_lab.solicited_matched_response_observation import (
    OBSERVATION_PATH,
    PARENTAGE_CAVEAT,
    RESPONSE_BODY_SHA256,
    load_observation,
    validate_observation,
)


PUBLICATION_RECEIPT_PATH = (
    Path(__file__).parents[1]
    / "evidence"
    / "solicited_matched_001.publication.receipt.json"
)


class SolicitedMatchedResponseObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.observation = json.loads(OBSERVATION_PATH.read_text(encoding="utf-8"))

    def test_committed_observation_preserves_exact_external_response(self) -> None:
        report = validate_observation(self.observation)
        body = self.observation["response_body"]["text"]

        self.assertTrue(report["valid"])
        self.assertEqual(report["response_kind"], "methodological-counterexample")
        self.assertEqual(report["response_body_sha256"], RESPONSE_BODY_SHA256)
        self.assertEqual(len(body.encode("utf-8")), 1752)
        self.assertEqual(sha256_ref(body), RESPONSE_BODY_SHA256)
        self.assertEqual(body, json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")))
        self.assertTrue(report["qualifies_under_literal_frozen_contract"])
        self.assertFalse(report["direct_child_of_invitation"])
        self.assertEqual(
            report["stop_triggered_at_utc"],
            "2026-08-23T08:59:15.457084Z",
        )
        self.assertFalse(report["claim_eligible"])
        self.assertEqual(report["general_unfamiliar_agent_saving_percent"], 0.0)
        self.assertIsNone(report["safely_completed_real_task_total_token_result"])

    def test_loader_validates_the_committed_artifact(self) -> None:
        self.assertEqual(load_observation(), self.observation)

    def test_parentage_caveat_and_conservative_stop_are_fail_closed(self) -> None:
        cases = (
            (
                "direct-child",
                ("parentage", "direct_child_of_invitation"),
                True,
                "parentage observation differs",
            ),
            (
                "caveat",
                ("qualification", "parentage_caveat"),
                PARENTAGE_CAVEAT + " ",
                "qualification observation differs",
            ),
            (
                "qualification",
                ("qualification", "qualifies_under_literal_frozen_contract"),
                False,
                "qualification observation differs",
            ),
            (
                "stop",
                ("qualification", "conservative_stop_applied"),
                False,
                "qualification observation differs",
            ),
        )
        for name, path, replacement, message in cases:
            with self.subTest(name=name):
                mutated = deepcopy(self.observation)
                mutated[path[0]][path[1]] = replacement
                with self.assertRaisesRegex(ValidationError, message):
                    validate_observation(mutated)

    def test_noncanonical_or_reclassified_body_is_rejected(self) -> None:
        noncanonical = deepcopy(self.observation)
        body = noncanonical["response_body"]["text"] + "\n"
        noncanonical["response_body"].update(
            {
                "text": body,
                "utf8_bytes": len(body.encode("utf-8")),
                "characters": len(body),
                "sha256": sha256_ref(body),
            }
        )
        with self.assertRaisesRegex(ValidationError, "frozen byte count differs"):
            validate_observation(noncanonical)

        reclassified = deepcopy(self.observation)
        reclassified["evidence_class"] = "independent-reproduction"
        with self.assertRaisesRegex(ValidationError, "evidence class differs"):
            validate_observation(reclassified)

    def test_zero_and_null_claim_boundary_cannot_be_promoted(self) -> None:
        cases = (
            ("claim", "claim_eligible", True),
            ("saving", "general_unfamiliar_agent_saving_percent", 1.0),
            ("tokens", "safely_completed_real_task_total_token_result", 100),
            ("adoption", "organic_adoption", True),
            ("independence", "independent_reproduction", True),
        )
        for name, field, replacement in cases:
            with self.subTest(name=name):
                mutated = deepcopy(self.observation)
                mutated["claim_boundary"][field] = replacement
                with self.assertRaisesRegex(ValidationError, "claim boundary differs"):
                    validate_observation(mutated)

    def test_existing_publication_receipt_remains_byte_bound(self) -> None:
        self.assertEqual(
            sha256_ref(PUBLICATION_RECEIPT_PATH.read_bytes()),
            "sha256:fba9a1553852a44ee2645b8df8408c1678548cdeb27fe88c83b3f756009432a6",
        )


if __name__ == "__main__":
    unittest.main()
