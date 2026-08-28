"""Mutation coverage for the synthetic contribution adjudication boundary."""

from __future__ import annotations

import base64
import copy
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import contribution_ledger.adjudication as adjudication
from contribution_ledger.adjudication import (
    ADJUDICATION_BOUNDARY,
    MAX_POLICY_BYTES,
    MAX_REVIEWERS,
    AdjudicationDependencyError,
    AdjudicationValidationError,
    adjudication_policy_canonical_json,
    adjudication_policy_digest,
    adjudication_statement_canonical_json,
    adjudication_statement_digest,
    build_adjudication_policy,
    build_adjudication_statement,
    reviewer_roster_digest,
    sign_adjudication_review,
    verify_adjudication,
)
from contribution_ledger.ledger import canonical_json


def digest(character: str) -> str:
    return character * 64


def private_bytes(index: int) -> bytes:
    return bytes([index]) * 32


def public_base64(index: int) -> str:
    public = (
        Ed25519PrivateKey.from_private_bytes(private_bytes(index))
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    return base64.b64encode(public).decode("ascii")


def reviewer(
    name: str,
    organization: str,
    index: int,
    *,
    key_id: str | None = None,
    valid_from: str = "2026-08-01T00:00:00Z",
    valid_until: str = "2026-10-31T00:00:00Z",
    revoked: bool = False,
) -> dict[str, object]:
    return {
        "reviewer_ref": f"reviewer:{name}",
        "reviewer_subject_ref": f"subject:{name}",
        "organization_id": organization,
        "key_id": key_id or f"key-{name}",
        "algorithm": "ed25519",
        "public_key_base64": public_base64(index),
        "valid_from_utc": valid_from,
        "valid_until_utc": valid_until,
        "revoked": revoked,
    }


class AdjudicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reviewers = [
            reviewer("alice", "org-one", 1),
            reviewer("bob", "org-two", 2),
            reviewer("carol", "org-three", 3),
        ]
        self.policy = self.make_policy(self.reviewers)
        self.policy_digest = adjudication_policy_digest(self.policy)
        self.statement = self.make_statement(self.policy)
        self.signatures = [
            self.sign(self.policy, self.statement, "alice", 1),
            self.sign(self.policy, self.statement, "bob", 2),
        ]

    def make_policy(
        self,
        reviewers,
        *,
        minimum_approvals: int = 2,
        minimum_organizations: int = 2,
        project_id: str = "project:urusilla",
        contribution_policy_digest: str = digest("a"),
        created: str = "2026-07-31T00:00:00Z",
        valid_from: str = "2026-08-01T00:00:00Z",
        valid_until: str = "2026-10-31T00:00:00Z",
    ):
        return build_adjudication_policy(
            policy_id="synthetic-policy-001",
            project_id=project_id,
            contribution_policy_digest=contribution_policy_digest,
            created_at_utc=created,
            valid_from_utc=valid_from,
            valid_until_utc=valid_until,
            minimum_approvals=minimum_approvals,
            minimum_distinct_organizations=minimum_organizations,
            appeal_window_seconds=2 * 24 * 60 * 60,
            reviewers=reviewers,
        )

    def make_statement(
        self,
        policy,
        *,
        subject_ref: str = "subject:contributor",
        decided_at: str = "2026-08-28T00:00:00Z",
        ledger_id: str = "ledger:research",
        points: int = 40,
    ):
        return build_adjudication_statement(
            policy,
            ledger_id=ledger_id,
            epoch_id="epoch-001",
            contribution_id=digest("b"),
            registration_event_id=digest("c"),
            subject_ref=subject_ref,
            contribution_class="runtime",
            points=points,
            evidence_digest=digest("d"),
            reason_code="verified_evidence",
            decided_at_utc=decided_at,
        )

    def sign(
        self,
        policy,
        statement,
        name: str,
        index: int,
        *,
        signed_at: str = "2026-08-28T01:00:00Z",
    ):
        return sign_adjudication_review(
            policy,
            statement,
            reviewer_ref=f"reviewer:{name}",
            key_id=f"key-{name}",
            signed_at_utc=signed_at,
            private_key_bytes=private_bytes(index),
        )

    def assert_code(self, code: str, callback) -> None:
        with self.assertRaises(AdjudicationValidationError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def verify(
        self,
        *,
        policy=None,
        statement=None,
        signatures=None,
        expected_policy_digest=None,
        expected_statement=None,
        verification_time: str = "2026-08-29T00:00:00Z",
    ):
        selected_policy = self.policy if policy is None else policy
        return verify_adjudication(
            selected_policy,
            self.statement if statement is None else statement,
            self.signatures if signatures is None else signatures,
            expected_policy_digest=(
                self.policy_digest
                if expected_policy_digest is None
                else expected_policy_digest
            ),
            expected_statement_value=(
                self.statement
                if expected_statement is None
                else expected_statement
            ),
            verification_time_utc=verification_time,
        )

    def test_end_to_end_quorum_has_explicit_zero_authority(self) -> None:
        result = self.verify().to_object()
        self.assertTrue(result["policy_pin_matched"])
        self.assertTrue(result["statement_pin_matched"])
        self.assertTrue(result["presented_quorum_signatures_verified"])
        self.assertTrue(result["pinned_policy_threshold_satisfied"])
        self.assertEqual(result["approvals_verified"], 2)
        self.assertEqual(result["distinct_policy_organization_labels"], 2)
        self.assertEqual(result["evidence_boundary"], ADJUDICATION_BOUNDARY)
        for field in (
            "canonical_credit_issued",
            "token_issued",
            "token_claim_created",
            "checkpoint_created",
            "canonical_checkpoint_created",
            "transferable",
            "convertible",
            "effect_authorized",
            "canonical_ledger_verified",
            "evidence_truth_verified",
            "external_timestamp_verified",
            "real_world_identity_verified",
            "subject_aliases_resolved",
            "conflicts_exhaustively_verified",
            "reviewer_independence_beyond_policy_verified",
        ):
            self.assertFalse(result[field])

    def test_canonical_policy_statement_and_roster_digests_are_deterministic(self) -> None:
        reordered = self.make_policy(list(reversed(self.reviewers)))
        self.assertEqual(reordered, self.policy)
        self.assertEqual(
            adjudication_policy_canonical_json(self.policy), canonical_json(self.policy)
        )
        self.assertEqual(adjudication_policy_digest(reordered), self.policy_digest)
        self.assertEqual(
            adjudication_statement_canonical_json(self.policy, self.statement),
            canonical_json(self.statement),
        )
        self.assertEqual(
            self.statement["reviewer_roster_digest"],
            reviewer_roster_digest(self.policy["reviewers"]),
        )

    def test_caller_pin_rejects_replacement_policy(self) -> None:
        replacement = copy.deepcopy(self.policy)
        replacement["contribution_policy_digest"] = digest("e")
        self.assert_code("policy_pin_mismatch", lambda: self.verify(policy=replacement))

    def test_minimum_approval_count_is_enforced(self) -> None:
        self.assert_code(
            "insufficient_approvals",
            lambda: self.verify(signatures=self.signatures[:1]),
        )

    def test_minimum_distinct_organizations_is_enforced(self) -> None:
        roster = [
            reviewer("alice", "org-shared", 1),
            reviewer("bob", "org-shared", 2),
            reviewer("carol", "org-three", 3),
        ]
        policy = self.make_policy(roster)
        statement = self.make_statement(policy)
        signatures = [
            self.sign(policy, statement, "alice", 1),
            self.sign(policy, statement, "bob", 2),
        ]
        self.assert_code(
            "insufficient_organizations",
            lambda: self.verify(
                policy=policy,
                statement=statement,
                signatures=signatures,
                expected_policy_digest=adjudication_policy_digest(policy),
                expected_statement=statement,
            ),
        )

    def test_duplicate_reviewer_key_and_public_key_in_roster_are_rejected(self) -> None:
        duplicate_reviewer = [
            reviewer("alice", "org-one", 1),
            reviewer("alice", "org-two", 2, key_id="key-other"),
        ]
        self.assert_code(
            "duplicate_reviewer",
            lambda: self.make_policy(duplicate_reviewer, minimum_organizations=1),
        )

        duplicate_key = [
            reviewer("alice", "org-one", 1, key_id="key-shared"),
            reviewer("bob", "org-two", 2, key_id="key-shared"),
        ]
        self.assert_code(
            "duplicate_key",
            lambda: self.make_policy(duplicate_key, minimum_organizations=1),
        )

        duplicate_public = [
            reviewer("alice", "org-one", 1),
            {**reviewer("bob", "org-two", 2), "public_key_base64": public_base64(1)},
        ]
        self.assert_code(
            "duplicate_public_key",
            lambda: self.make_policy(duplicate_public, minimum_organizations=1),
        )

        duplicate_subject = [
            reviewer("alice", "org-one", 1),
            {
                **reviewer("bob", "org-two", 2),
                "reviewer_subject_ref": "subject:alice",
            },
        ]
        self.assert_code(
            "duplicate_reviewer_subject",
            lambda: self.make_policy(duplicate_subject, minimum_organizations=1),
        )

    def test_duplicate_reviewer_key_and_signature_bytes_are_rejected(self) -> None:
        repeated_reviewer = [self.signatures[0], copy.deepcopy(self.signatures[0])]
        self.assert_code(
            "duplicate_reviewer", lambda: self.verify(signatures=repeated_reviewer)
        )

        repeated_key = copy.deepcopy(self.signatures)
        repeated_key[1]["key_id"] = repeated_key[0]["key_id"]
        self.assert_code("duplicate_key", lambda: self.verify(signatures=repeated_key))

        repeated_bytes = copy.deepcopy(self.signatures)
        repeated_bytes[1]["signature_base64"] = repeated_bytes[0]["signature_base64"]
        self.assert_code(
            "duplicate_signature", lambda: self.verify(signatures=repeated_bytes)
        )

    def test_revoked_expired_and_not_yet_valid_keys_cannot_sign(self) -> None:
        cases = (
            (
                reviewer("alice", "org-one", 1, revoked=True),
                "revoked_key",
            ),
            (
                reviewer(
                    "alice",
                    "org-one",
                    1,
                    valid_until="2026-08-27T00:00:00Z",
                ),
                "key_outside_validity",
            ),
            (
                reviewer(
                    "alice",
                    "org-one",
                    1,
                    valid_from="2026-08-29T00:00:00Z",
                ),
                "key_outside_validity",
            ),
        )
        for first, expected in cases:
            policy = self.make_policy(
                [first, reviewer("bob", "org-two", 2)],
                minimum_organizations=1,
            )
            statement = self.make_statement(policy)
            self.assert_code(
                expected,
                lambda policy=policy, statement=statement: self.sign(
                    policy, statement, "alice", 1
                ),
            )

    def test_subject_cannot_review_own_claim(self) -> None:
        statement = self.make_statement(self.policy, subject_ref="subject:alice")
        self.assert_code(
            "self_review", lambda: self.sign(self.policy, statement, "alice", 1)
        )

    def test_policy_statement_and_appeal_times_are_checked(self) -> None:
        self.assert_code(
            "invalid_policy_time",
            lambda: self.make_policy(
                self.reviewers, created="2026-08-02T00:00:00Z"
            ),
        )
        self.assert_code(
            "statement_outside_policy_time",
            lambda: self.make_statement(
                self.policy, decided_at="2026-07-31T00:00:00Z"
            ),
        )
        mutated = copy.deepcopy(self.statement)
        mutated["appeal_deadline_utc"] = "2026-08-31T00:00:00Z"
        self.assert_code("invalid_appeal_window", lambda: self.verify(statement=mutated))

    def test_future_signature_is_rejected(self) -> None:
        late = [
            self.sign(
                self.policy,
                self.statement,
                "alice",
                1,
                signed_at="2026-08-29T12:00:00Z",
            ),
            self.signatures[1],
        ]
        self.assert_code(
            "signature_from_future",
            lambda: self.verify(
                signatures=late, verification_time="2026-08-29T00:00:00Z"
            ),
        )

    def test_keys_and_policy_must_still_be_valid_at_caller_time(self) -> None:
        roster = [
            reviewer(
                "alice",
                "org-one",
                1,
                valid_until="2026-08-29T12:00:00Z",
            ),
            reviewer("bob", "org-two", 2),
        ]
        policy = self.make_policy(roster)
        statement = self.make_statement(policy)
        signatures = [
            self.sign(policy, statement, "alice", 1),
            self.sign(policy, statement, "bob", 2),
        ]
        self.assert_code(
            "key_not_current_at_verification",
            lambda: self.verify(
                policy=policy,
                statement=statement,
                signatures=signatures,
                expected_policy_digest=adjudication_policy_digest(policy),
                expected_statement=statement,
                verification_time="2026-08-29T23:00:00Z",
            ),
        )
        self.assert_code(
            "verification_outside_policy_time",
            lambda: self.verify(verification_time="2026-11-01T00:00:00Z"),
        )

    def test_cross_project_ledger_registration_reason_and_points_rebinding_fail(self) -> None:
        project = copy.deepcopy(self.statement)
        project["project_id"] = "project:attacker"
        self.assert_code("project_mismatch", lambda: self.verify(statement=project))

        for field, replacement in (
            ("ledger_id", "ledger:other"),
            ("registration_event_id", digest("f")),
            ("reason_code", "other_reason"),
            ("points", 41),
        ):
            mutated = copy.deepcopy(self.statement)
            mutated[field] = replacement
            self.assert_code(
                "statement_pin_mismatch",
                lambda mutated=mutated: self.verify(statement=mutated),
            )
        for invalid_points in (0, True, 2**63):
            self.assert_code(
                "invalid_count",
                lambda invalid_points=invalid_points: self.make_statement(
                    self.policy, points=invalid_points
                ),
            )

    def test_fully_resigned_other_award_still_fails_caller_statement_pin(self) -> None:
        attacker_statement = self.make_statement(
            self.policy,
            ledger_id="ledger:other",
            points=99,
        )
        attacker_signatures = [
            self.sign(self.policy, attacker_statement, "alice", 1),
            self.sign(self.policy, attacker_statement, "bob", 2),
        ]
        self.assert_code(
            "statement_pin_mismatch",
            lambda: self.verify(
                statement=attacker_statement,
                signatures=attacker_signatures,
                expected_statement=self.statement,
            ),
        )

    def test_wrong_key_signature_is_rejected(self) -> None:
        signature = copy.deepcopy(self.signatures[0])
        raw = base64.b64decode(signature["signature_base64"])
        signature["signature_base64"] = base64.b64encode(
            bytes([raw[0] ^ 1]) + raw[1:]
        ).decode("ascii")
        self.assert_code(
            "invalid_signature",
            lambda: self.verify(signatures=[signature, self.signatures[1]]),
        )

    def test_input_limits_run_before_json_or_base64_expansion(self) -> None:
        oversized_json = "x" * (MAX_POLICY_BYTES + 1)
        with patch("contribution_ledger.adjudication.json.loads") as loads:
            self.assert_code(
                "input_too_large", lambda: adjudication_policy_digest(oversized_json)
            )
        loads.assert_not_called()

        oversized_key = [
            {**self.reviewers[0], "public_key_base64": "A" * 1_000},
            self.reviewers[1],
        ]
        with patch("contribution_ledger.adjudication.base64.b64decode") as decode:
            self.assert_code(
                "malformed_base64",
                lambda: self.make_policy(oversized_key, minimum_organizations=1),
            )
        decode.assert_not_called()

        signature = copy.deepcopy(self.signatures[0])
        signature["signature_base64"] = "A" * 1_000
        with patch("contribution_ledger.adjudication.base64.b64decode") as decode:
            self.assert_code(
                "malformed_base64", lambda: adjudication._signature_entries([signature])
            )
        decode.assert_not_called()

    def test_count_limits_run_before_deepcopy(self) -> None:
        huge_object = {str(index): 0 for index in range(65)}
        with patch("contribution_ledger.adjudication.copy.deepcopy") as deepcopy:
            self.assert_code(
                "input_count_limit", lambda: adjudication_policy_digest(huge_object)
            )
        deepcopy.assert_not_called()

        wide_policy = {
            **self.policy,
            "reviewers": [
                {
                    **self.reviewers[0],
                    "organization_id": [0] * adjudication.MAX_JSON_NODES,
                },
                self.reviewers[1],
                self.reviewers[2],
            ],
        }
        with patch("contribution_ledger.adjudication.copy.deepcopy") as deepcopy:
            self.assert_code(
                "json_node_limit_exceeded",
                lambda: adjudication_policy_digest(wide_policy),
            )
        deepcopy.assert_not_called()

        nested: object = 0
        for _ in range(adjudication.MAX_JSON_DEPTH + 1):
            nested = [nested]
        deep_statement = {**self.statement, "evidence_digest": nested}
        with patch("contribution_ledger.adjudication.copy.deepcopy") as deepcopy:
            self.assert_code(
                "json_nesting_too_deep",
                lambda: adjudication._object_input(
                    deep_statement,
                    "adjudication_statement",
                    adjudication.MAX_STATEMENT_BYTES,
                ),
            )
        deepcopy.assert_not_called()

        too_many_reviewers = [{}] * (MAX_REVIEWERS + 1)
        with patch("contribution_ledger.adjudication.copy.deepcopy") as deepcopy:
            self.assert_code(
                "reviewer_count_limit",
                lambda: reviewer_roster_digest(too_many_reviewers),
            )
        deepcopy.assert_not_called()

        oversized_nested_roster = {
            **self.policy,
            "reviewers": [{}] * (MAX_REVIEWERS + 1),
        }
        with patch("contribution_ledger.adjudication.copy.deepcopy") as deepcopy:
            self.assert_code(
                "reviewer_count_limit",
                lambda: adjudication_policy_digest(oversized_nested_roster),
            )
        deepcopy.assert_not_called()

        with patch("contribution_ledger.adjudication.MAX_SIGNATURES", 1), patch(
            "contribution_ledger.adjudication.copy.deepcopy"
        ) as deepcopy:
            self.assert_code(
                "signature_count_limit",
                lambda: adjudication._signature_entries(self.signatures),
            )
        deepcopy.assert_not_called()

    def test_noncanonical_policy_json_is_rejected(self) -> None:
        pretty = json.dumps(self.policy, sort_keys=True, indent=2)
        self.assert_code(
            "noncanonical_json", lambda: adjudication_policy_digest(pretty)
        )

    def test_crypto_dependency_is_lazy_and_explicit(self) -> None:
        with patch(
            "contribution_ledger.adjudication._load_crypto",
            side_effect=AdjudicationDependencyError("optional dependency unavailable"),
        ):
            self.assertEqual(
                adjudication_policy_canonical_json(self.policy), canonical_json(self.policy)
            )
            with self.assertRaisesRegex(
                AdjudicationDependencyError, "optional dependency unavailable"
            ):
                self.sign(self.policy, self.statement, "alice", 1)
            with self.assertRaisesRegex(
                AdjudicationDependencyError, "optional dependency unavailable"
            ):
                self.verify()


if __name__ == "__main__":
    unittest.main()
