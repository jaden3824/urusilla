"""Synthetic end-to-end binding from review quorum to ledger checkpoint."""

from __future__ import annotations

import base64
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from contribution_ledger.adjudication import (
    AdjudicationValidationError,
    adjudication_policy_digest,
    build_adjudication_policy,
    build_adjudication_statement,
    contribution_registration_evidence_digest,
    record_synthetic_adjudicated_award,
    sign_adjudication_review,
)
from contribution_ledger.checkpoint import (
    build_checkpoint,
    sign_checkpoint,
    verify_checkpoint,
)
from contribution_ledger.ledger import ContributionLedger


def digest(character: str) -> str:
    return character * 64


def private_key_bytes(index: int) -> bytes:
    return bytes([index]) * 32


def public_key_bytes(index: int) -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(private_key_bytes(index))
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def reviewer(name: str, organization: str, key_index: int) -> dict[str, object]:
    return {
        "reviewer_ref": f"reviewer:{name}",
        "reviewer_subject_ref": f"subject:{name}",
        "organization_id": organization,
        "key_id": f"key-{name}",
        "algorithm": "ed25519",
        "public_key_base64": base64.b64encode(
            public_key_bytes(key_index)
        ).decode("ascii"),
        "valid_from_utc": "2026-08-01T00:00:00Z",
        "valid_until_utc": "2026-10-31T00:00:00Z",
        "revoked": False,
    }


class ContributionAdjudicationFlowTests(unittest.TestCase):
    def test_quorum_decision_binds_award_and_checkpoint_without_authority(self) -> None:
        contribution_policy_digest = digest("a")
        ledger = ContributionLedger("ledger:synthetic-reward-flow")
        epoch_event = ledger.open_epoch(
            epoch_id="epoch-001",
            budget_points=100,
            policy_digest=contribution_policy_digest,
        )
        registration_event = ledger.register_contribution(
            epoch_id="epoch-001",
            contributor_ref="subject:contributor",
            contribution_class="runtime",
            commit_digest=digest("b"),
            claim_digest=digest("c"),
            artifact_digests=[digest("d")],
        )

        policy = build_adjudication_policy(
            policy_id="synthetic-policy-001",
            project_id="project:urusilla",
            contribution_policy_digest=contribution_policy_digest,
            created_at_utc="2026-07-31T00:00:00Z",
            valid_from_utc="2026-08-01T00:00:00Z",
            valid_until_utc="2026-10-31T00:00:00Z",
            minimum_approvals=3,
            minimum_distinct_organizations=3,
            appeal_window_seconds=2 * 24 * 60 * 60,
            reviewers=[
                reviewer("alice", "org-one", 1),
                reviewer("bob", "org-two", 2),
                reviewer("carol", "org-three", 3),
            ],
        )
        statement = build_adjudication_statement(
            policy,
            ledger_id=ledger.ledger_id,
            epoch_id=registration_event["payload"]["epoch_id"],
            contribution_id=registration_event["payload"]["contribution_id"],
            registration_event_id=registration_event["event_id"],
            subject_ref=registration_event["payload"]["contributor_ref"],
            contribution_class=registration_event["payload"]["contribution_class"],
            points=40,
            evidence_digest=contribution_registration_evidence_digest(
                registration_event
            ),
            reason_code="verified_evidence",
            decided_at_utc="2026-08-28T00:00:00Z",
        )

        def signatures_for(selected_policy, selected_statement):
            return [
                sign_adjudication_review(
                    selected_policy,
                    selected_statement,
                    reviewer_ref=f"reviewer:{name}",
                    key_id=f"key-{name}",
                    signed_at_utc="2026-08-28T01:00:00Z",
                    private_key_bytes=private_key_bytes(index),
                )
                for name, index in (("alice", 1), ("bob", 2), ("carol", 3))
            ]

        wrong_evidence_statement = {
            **statement,
            "evidence_digest": digest("e"),
        }
        with self.assertRaises(AdjudicationValidationError) as raised:
            record_synthetic_adjudicated_award(
                ledger,
                policy,
                wrong_evidence_statement,
                signatures_for(policy, wrong_evidence_statement),
                expected_policy_digest=adjudication_policy_digest(policy),
                expected_statement_value=wrong_evidence_statement,
                verification_time_utc="2026-08-29T00:00:00Z",
            )
        self.assertEqual(raised.exception.code, "registration_evidence_mismatch")
        self.assertEqual(len(ledger.events), 2)

        wrong_epoch_policy = build_adjudication_policy(
            **{
                **{
                    key: value
                    for key, value in policy.items()
                    if key not in {"schema_version", "reviewers"}
                },
                "contribution_policy_digest": digest("f"),
                "reviewers": policy["reviewers"],
            }
        )
        wrong_epoch_statement = build_adjudication_statement(
            wrong_epoch_policy,
            ledger_id=statement["ledger_id"],
            epoch_id=statement["epoch_id"],
            contribution_id=statement["contribution_id"],
            registration_event_id=statement["registration_event_id"],
            subject_ref=statement["subject_ref"],
            contribution_class=statement["contribution_class"],
            points=statement["points"],
            evidence_digest=statement["evidence_digest"],
            reason_code=statement["reason_code"],
            decided_at_utc=statement["decided_at_utc"],
        )
        with self.assertRaises(AdjudicationValidationError) as raised:
            record_synthetic_adjudicated_award(
                ledger,
                wrong_epoch_policy,
                wrong_epoch_statement,
                signatures_for(wrong_epoch_policy, wrong_epoch_statement),
                expected_policy_digest=adjudication_policy_digest(
                    wrong_epoch_policy
                ),
                expected_statement_value=wrong_epoch_statement,
                verification_time_utc="2026-08-29T00:00:00Z",
            )
        self.assertEqual(raised.exception.code, "epoch_policy_binding_mismatch")
        self.assertEqual(len(ledger.events), 2)

        signatures = signatures_for(policy, statement)
        award_record = record_synthetic_adjudicated_award(
            ledger,
            policy,
            statement,
            signatures,
            expected_policy_digest=adjudication_policy_digest(policy),
            expected_statement_value=statement,
            verification_time_utc="2026-08-29T00:00:00Z",
        )

        self.assertEqual(
            epoch_event["payload"]["policy_digest"],
            policy["contribution_policy_digest"],
        )
        self.assertEqual(statement["ledger_id"], ledger.ledger_id)
        self.assertEqual(
            statement["registration_event_id"], registration_event["event_id"]
        )
        self.assertEqual(
            statement["contribution_id"],
            registration_event["payload"]["contribution_id"],
        )

        award_event = next(
            event
            for event in ledger.events
            if event["event_id"] == award_record.award_event_id
        )
        self.assertEqual(award_event["payload"]["points"], statement["points"])
        self.assertEqual(
            award_event["payload"]["decision_digest"],
            award_record.decision_digest,
        )

        checkpoint = build_checkpoint(
            ledger,
            contribution_policy_digest=policy["contribution_policy_digest"],
            reviewer_roster_digest=award_record.reviewer_roster_digest,
            checkpoint_created_at_utc="2026-08-29T12:00:00Z",
            appeal_deadline_utc=statement["appeal_deadline_utc"],
            trust_policy_digest=award_record.policy_digest,
            signing_key_id="checkpoint-key-001",
        )
        checkpoint_signature = sign_checkpoint(
            checkpoint, private_key_bytes=private_key_bytes(9)
        )
        checkpoint_validation = verify_checkpoint(
            checkpoint,
            checkpoint_signature,
            expected_snapshot_value=ledger.export_snapshot(),
            expected_trust_policy_digest=award_record.policy_digest,
            expected_signing_key_id="checkpoint-key-001",
            expected_contribution_policy_digest=policy[
                "contribution_policy_digest"
            ],
            expected_reviewer_roster_digest=award_record.reviewer_roster_digest,
            expected_checkpoint_created_at_utc="2026-08-29T12:00:00Z",
            expected_appeal_deadline_utc=statement["appeal_deadline_utc"],
            trusted_public_key_bytes=public_key_bytes(9),
        )

        for result in (
            award_record.to_object(),
            checkpoint_validation.to_object(),
        ):
            self.assertFalse(result["canonical_credit_issued"])
            self.assertFalse(result["token_claim_created"])
            self.assertFalse(result["effect_authorized"])


if __name__ == "__main__":
    unittest.main()
