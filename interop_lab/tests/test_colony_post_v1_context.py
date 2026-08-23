"""Focused offline checks for the immutable Colony post-v1 context."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from interop_lab.colony_post_v1_context import (
    COMMENT_IDS,
    CONDITIONAL_OFFER,
    CONTEXT_PATH,
    CORRECTION_IDS,
    PROSE_COMMENT_ID,
    load_context,
    validate_context,
)
from interop_lab.interop_lab import ValidationError
from interop_lab.solicited_matched_experiment import sha256_ref


V1_STOP_COMMENT_ID = "bdc42fcc-a75a-4d60-b2aa-97f249f872bf"


class ColonyPostV1ContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))

    def test_committed_context_preserves_exact_post_stop_bodies(self) -> None:
        report = validate_context(self.context)

        self.assertTrue(report["valid"])
        self.assertEqual(report["comment_ids"], list(COMMENT_IDS))
        self.assertNotIn(V1_STOP_COMMENT_ID, report["comment_ids"])
        self.assertEqual(
            report["conditional_reproduction_interest_comment_id"],
            PROSE_COMMENT_ID,
        )
        self.assertFalse(report["claim_eligible"])
        self.assertFalse(report["independent_reproduction"])
        self.assertFalse(report["organic_adoption"])
        self.assertEqual(report["general_unfamiliar_agent_saving_percent"], 0.0)
        self.assertIsNone(report["safely_completed_real_task_total_token_result"])

        for comment in self.context["comments"]:
            body = comment["body"]
            self.assertEqual(body["utf8_bytes"], len(body["text"].encode("utf-8")))
            self.assertEqual(body["characters"], len(body["text"]))
            self.assertEqual(body["sha256"], sha256_ref(body["text"]))
            self.assertFalse(comment["chronology"]["direct_descendant_of_invitation"])
            self.assertTrue(comment["chronology"]["post_stop_context_only"])
            self.assertFalse(comment["classification"]["experimental_result_observed"])
            self.assertFalse(comment["claim_boundary"]["claim_eligible"])

    def test_loader_validates_the_committed_artifact(self) -> None:
        self.assertEqual(load_context(), self.context)

    def test_conditional_offer_and_reply_boundary_are_not_overclaimed(self) -> None:
        comments = {item["id"]: item for item in self.context["comments"]}
        prose = comments[PROSE_COMMENT_ID]
        action = self.context["external_action_boundary"]

        self.assertEqual(
            prose["classification"]["reproduction_interest"],
            "conditional",
        )
        self.assertEqual(prose["classification"]["conditional_offer"], CONDITIONAL_OFFER)
        self.assertIn(CONDITIONAL_OFFER, prose["body"]["text"])
        self.assertEqual(action["proposed_direct_reply_parent_id"], PROSE_COMMENT_ID)
        self.assertFalse(action["third_party_invitation_is_project_operator_authorization"])
        self.assertFalse(action["automatic_reply_allowed"])
        self.assertFalse(action["external_reply_performed_for_this_observation"])

        for comment_id, comment in comments.items():
            if comment_id != PROSE_COMMENT_ID:
                self.assertEqual(comment["classification"]["reproduction_interest"], "none")
                self.assertIsNone(comment["classification"]["conditional_offer"])

    def test_venue_and_null_classifications_remain_context_only(self) -> None:
        comments = {item["id"]: item for item in self.context["comments"]}
        maximus = comments["f0ab1c26-cdab-44cf-9018-1e916b05b99d"]
        specie = comments["569c288b-8fc8-4405-8706-4e43c55241bf"]
        longcat = comments["f3473a32-0099-4aae-85d2-c18815d32a1e"]

        self.assertEqual(maximus["classification"]["cross_platform_testimony"], "read-only-observer")
        self.assertTrue(maximus["classification"]["explicit_non_adoption"])
        self.assertEqual(specie["classification"]["response_scope"], "venue-objective-framing")
        self.assertEqual(longcat["classification"]["cross_platform_testimony"], "explicit-null")
        self.assertTrue(longcat["classification"]["explicit_non_adoption"])

    def test_body_text_or_metadata_tampering_is_rejected(self) -> None:
        changed_body = deepcopy(self.context)
        body = changed_body["comments"][0]["body"]
        body["text"] = body["text"].replace("Prose note", "Prose mote", 1)
        body["sha256"] = sha256_ref(body["text"])
        with self.assertRaisesRegex(ValidationError, "frozen context body differs"):
            validate_context(changed_body)

        changed_parent = deepcopy(self.context)
        changed_parent["comments"][0]["parent_id"] = PROSE_COMMENT_ID
        with self.assertRaisesRegex(ValidationError, "context comment parent differs"):
            validate_context(changed_parent)

        changed_time = deepcopy(self.context)
        changed_time["comments"][3]["updated_at"] = "2026-08-23T12:32:27.698667Z"
        with self.assertRaisesRegex(ValidationError, "context update time differs"):
            validate_context(changed_time)

    def test_reclassification_or_claim_promotion_is_rejected(self) -> None:
        reclassified = deepcopy(self.context)
        reclassified["comments"][1]["classification"][
            "reproduction_interest"
        ] = "conditional"
        with self.assertRaisesRegex(ValidationError, "context classification differs"):
            validate_context(reclassified)

        promoted_comment = deepcopy(self.context)
        promoted_comment["comments"][0]["claim_boundary"]["independent_reproduction"] = True
        with self.assertRaisesRegex(ValidationError, "comment claim boundary differs"):
            validate_context(promoted_comment)

        promoted_aggregate = deepcopy(self.context)
        promoted_aggregate["aggregate_claim_boundary"]["efficiency_evidence"] = True
        with self.assertRaisesRegex(ValidationError, "aggregate claim boundary differs"):
            validate_context(promoted_aggregate)

    def test_longcat_corrections_are_exact_and_fail_closed(self) -> None:
        corrections = self.context["project_corrections"]
        self.assertEqual(
            [item["correction_id"] for item in corrections],
            list(CORRECTION_IDS),
        )
        statuses = {item["correction_id"]: item["project_status"] for item in corrections}
        self.assertEqual(statuses["longcat-clawprint-stub-confirmed"], "confirmed")
        self.assertEqual(
            statuses["longcat-reachability-denominator-inconsistent"],
            "contradicted-by-embedded-table",
        )
        self.assertEqual(
            statuses["longcat-4claw-wrong-domain"],
            "contradicted-as-venue-result",
        )
        self.assertEqual(
            statuses["longcat-moltbook-discovery-probe-incomplete"],
            "contradicted-by-public-skill-file",
        )
        self.assertEqual(
            statuses["longcat-526-maintenance-inference-unsupported"],
            "unsupported-inference",
        )
        self.assertEqual(
            statuses["longcat-verification-cost-percentages-unverified"],
            "unverified-self-report",
        )

        mutated = deepcopy(self.context)
        mutated["project_corrections"][2]["project_status"] = "confirmed"
        with self.assertRaisesRegex(ValidationError, "project corrections differ"):
            validate_context(mutated)

    def test_frozen_v1_references_cannot_be_rewritten_or_duplicated(self) -> None:
        frozen = self.context["frozen_v1"]
        self.assertTrue(frozen["stop_observation_referenced_not_duplicated"])
        self.assertFalse(frozen["frozen_contract_modified"])
        self.assertNotIn(
            frozen["stop_comment_id"],
            [item["id"] for item in self.context["comments"]],
        )

        mutated = deepcopy(self.context)
        mutated["frozen_v1"]["stop_triggered_at_utc"] = (
            "2026-08-23T08:59:15.457085Z"
        )
        with self.assertRaisesRegex(ValidationError, "frozen v1 reference differs"):
            validate_context(mutated)

    def test_external_action_boundary_cannot_be_expanded(self) -> None:
        for field in (
            "third_party_invitation_is_project_operator_authorization",
            "automatic_reply_allowed",
            "external_reply_performed_for_this_observation",
        ):
            with self.subTest(field=field):
                mutated = deepcopy(self.context)
                mutated["external_action_boundary"][field] = True
                with self.assertRaisesRegex(
                    ValidationError,
                    "external action boundary differs",
                ):
                    validate_context(mutated)


if __name__ == "__main__":
    unittest.main()
