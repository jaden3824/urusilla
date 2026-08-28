"""Mutation tests for the zero-authority signed checkpoint trial."""

from __future__ import annotations

import base64
import copy
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from contribution_ledger.checkpoint import (
    CHECKPOINT_BOUNDARY,
    MAX_SNAPSHOT_BYTES,
    CheckpointDependencyError,
    CheckpointValidationError,
    build_checkpoint,
    checkpoint_canonical_json,
    checkpoint_sha256,
    sign_checkpoint,
    verify_checkpoint,
)
from contribution_ledger.ledger import ContributionLedger, canonical_json


def digest(character: str) -> str:
    return character * 64


PRIVATE_KEY_BYTES = bytes([7]) * 32
OTHER_PRIVATE_KEY_BYTES = bytes([9]) * 32
KEY_ID = "checkpoint-key-001"
TRUST_POLICY_DIGEST = digest("a")
CONTRIBUTION_POLICY_DIGEST = digest("1")
REVIEWER_ROSTER_DIGEST = digest("2")
CHECKPOINT_CREATED_AT_UTC = "2026-08-28T00:00:00Z"
APPEAL_DEADLINE_UTC = "2026-09-30T00:00:00Z"


def public_key_bytes(private_key_bytes: bytes) -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ContributionLedger("synthetic-checkpoint-ledger")
        self.ledger.open_epoch(
            epoch_id="epoch-001",
            budget_points=100,
            policy_digest=digest("b"),
        )
        contribution = self.ledger.register_contribution(
            epoch_id="epoch-001",
            contributor_ref="subject:alice",
            contribution_class="runtime",
            commit_digest=digest("c"),
            claim_digest=digest("d"),
            artifact_digests=[digest("e")],
        )
        self.ledger.grant_award(
            epoch_id="epoch-001",
            contribution_id=contribution["payload"]["contribution_id"],
            points=40,
            decision_digest=digest("f"),
        )
        self.snapshot = self.ledger.export_snapshot()
        self.checkpoint = build_checkpoint(
            self.ledger,
            contribution_policy_digest=CONTRIBUTION_POLICY_DIGEST,
            reviewer_roster_digest=REVIEWER_ROSTER_DIGEST,
            checkpoint_created_at_utc=CHECKPOINT_CREATED_AT_UTC,
            appeal_deadline_utc=APPEAL_DEADLINE_UTC,
            trust_policy_digest=TRUST_POLICY_DIGEST,
            signing_key_id=KEY_ID,
        )
        self.signature = sign_checkpoint(
            self.checkpoint, private_key_bytes=PRIVATE_KEY_BYTES
        )
        self.public_key = public_key_bytes(PRIVATE_KEY_BYTES)

    def assert_code(self, code: str, callback) -> None:
        with self.assertRaises(CheckpointValidationError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def verify(self, *, checkpoint=None, signature=None, snapshot=None, public_key=None):
        return verify_checkpoint(
            checkpoint or self.checkpoint,
            signature or self.signature,
            expected_snapshot_value=snapshot or self.snapshot,
            expected_trust_policy_digest=TRUST_POLICY_DIGEST,
            expected_signing_key_id=KEY_ID,
            expected_contribution_policy_digest=CONTRIBUTION_POLICY_DIGEST,
            expected_reviewer_roster_digest=REVIEWER_ROSTER_DIGEST,
            expected_checkpoint_created_at_utc=CHECKPOINT_CREATED_AT_UTC,
            expected_appeal_deadline_utc=APPEAL_DEADLINE_UTC,
            trusted_public_key_bytes=public_key or self.public_key,
        )

    def test_valid_signature_binds_exact_snapshot_and_has_zero_authority(self) -> None:
        result = self.verify().to_object()
        self.assertTrue(result["signature_verified"])
        self.assertTrue(result["snapshot_binding_verified"])
        self.assertTrue(result["snapshot_bytes_matched"])
        self.assertFalse(result["snapshot_semantics_verified"])
        self.assertFalse(result["ledger_replay_verified_by_verifier"])
        self.assertTrue(result["separate_trust_policy_pin_matched"])
        self.assertTrue(result["review_metadata_pins_matched"])
        self.assertEqual(result["evidence_boundary"], CHECKPOINT_BOUNDARY)
        self.assertEqual(
            result["ledger_snapshot_sha256"],
            self.checkpoint["ledger_snapshot_sha256"],
        )
        for field in (
            "canonical_credit_issued",
            "token_claim_created",
            "transferable",
            "convertible",
            "effect_authorized",
            "onchain_anchor_verified",
            "external_timestamp_verified",
        ):
            self.assertFalse(result[field])

    def test_checkpoint_json_digest_and_signature_are_deterministic(self) -> None:
        duplicate = build_checkpoint(
            self.ledger,
            contribution_policy_digest=CONTRIBUTION_POLICY_DIGEST,
            reviewer_roster_digest=REVIEWER_ROSTER_DIGEST,
            checkpoint_created_at_utc=CHECKPOINT_CREATED_AT_UTC,
            appeal_deadline_utc=APPEAL_DEADLINE_UTC,
            trust_policy_digest=TRUST_POLICY_DIGEST,
            signing_key_id=KEY_ID,
        )
        second_signature = sign_checkpoint(
            duplicate, private_key_bytes=PRIVATE_KEY_BYTES
        )
        self.assertEqual(checkpoint_canonical_json(duplicate), canonical_json(duplicate))
        self.assertEqual(checkpoint_sha256(duplicate), checkpoint_sha256(self.checkpoint))
        self.assertEqual(second_signature, self.signature)

    def test_any_signed_field_mutation_is_rejected(self) -> None:
        for field, replacement in (
            ("checkpoint_created_at_utc", "2026-08-29T00:00:00Z"),
            ("appeal_deadline_utc", "2026-10-01T00:00:00Z"),
            ("contribution_policy_digest", digest("3")),
            ("reviewer_roster_digest", digest("4")),
        ):
            mutated = copy.deepcopy(self.checkpoint)
            mutated[field] = replacement
            self.assert_code(
                "checkpoint_digest_mismatch",
                lambda mutated=mutated: self.verify(checkpoint=mutated),
            )

    def test_appeal_deadline_must_follow_checkpoint_creation(self) -> None:
        self.assert_code(
            "invalid_appeal_window",
            lambda: build_checkpoint(
                self.ledger,
                contribution_policy_digest=digest("1"),
                reviewer_roster_digest=digest("2"),
                checkpoint_created_at_utc="2026-08-28T00:00:00Z",
                appeal_deadline_utc="2026-08-28T00:00:00Z",
                trust_policy_digest=TRUST_POLICY_DIGEST,
                signing_key_id=KEY_ID,
            ),
        )

    def test_oversized_embedded_snapshot_is_rejected_before_parsing(self) -> None:
        checkpoint = copy.deepcopy(self.checkpoint)
        checkpoint["ledger_snapshot_canonical_json"] = "x" * (
            MAX_SNAPSHOT_BYTES + 1
        )
        self.assert_code(
            "snapshot_too_large", lambda: self.verify(checkpoint=checkpoint)
        )

    def test_deeply_nested_snapshot_fails_closed(self) -> None:
        checkpoint = copy.deepcopy(self.checkpoint)
        checkpoint["ledger_snapshot_canonical_json"] = (
            '{"x":' + "[" * 65 + "0" + "]" * 65 + "}"
        )
        self.assert_code(
            "json_nesting_too_deep", lambda: self.verify(checkpoint=checkpoint)
        )

    def test_wide_snapshot_checks_node_budget_before_enqueuing_children(self) -> None:
        checkpoint = copy.deepcopy(self.checkpoint)
        checkpoint["ledger_snapshot_canonical_json"] = (
            '{"x":[' + ",".join("0" for _ in range(10)) + "]}"
        )
        with patch("contribution_ledger.checkpoint.MAX_JSON_NODES", 10):
            self.assert_code(
                "json_node_limit_exceeded",
                lambda: self.verify(checkpoint=checkpoint),
            )

    def test_oversized_signature_is_rejected_before_base64_decode(self) -> None:
        signature = copy.deepcopy(self.signature)
        signature["signature_base64"] = "A" * 1_000_000
        with patch("contribution_ledger.checkpoint.base64.b64decode") as decode:
            self.assert_code(
                "malformed_signature", lambda: self.verify(signature=signature)
            )
        decode.assert_not_called()

    def test_snapshot_mismatch_is_rejected(self) -> None:
        other = copy.deepcopy(self.snapshot)
        other["epochs"][0]["budget_points"] += 1
        self.assert_code("snapshot_mismatch", lambda: self.verify(snapshot=other))

    def test_embedded_snapshot_mutation_cannot_retain_original_digest(self) -> None:
        mutated = copy.deepcopy(self.checkpoint)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["epochs"][0]["budget_points"] += 1
        mutated["ledger_snapshot_canonical_json"] = canonical_json(snapshot)
        self.assert_code(
            "snapshot_digest_mismatch", lambda: self.verify(checkpoint=mutated)
        )

    def test_wrong_public_key_is_rejected(self) -> None:
        wrong = public_key_bytes(OTHER_PRIVATE_KEY_BYTES)
        self.assert_code("invalid_signature", lambda: self.verify(public_key=wrong))

    def test_wrong_key_id_is_rejected_even_with_a_valid_resign(self) -> None:
        attacker = copy.deepcopy(self.checkpoint)
        attacker["signing_key_id"] = "attacker-key"
        attacker_signature = sign_checkpoint(
            attacker, private_key_bytes=OTHER_PRIVATE_KEY_BYTES
        )
        self.assert_code(
            "key_id_pin_mismatch",
            lambda: self.verify(
                checkpoint=attacker,
                signature=attacker_signature,
                public_key=public_key_bytes(OTHER_PRIVATE_KEY_BYTES),
            ),
        )

    def test_artifact_cannot_supply_or_substitute_a_public_key(self) -> None:
        checkpoint = copy.deepcopy(self.checkpoint)
        checkpoint["public_key_base64"] = base64.b64encode(self.public_key).decode("ascii")
        self.assert_code("unknown_field", lambda: self.verify(checkpoint=checkpoint))

        signature = copy.deepcopy(self.signature)
        signature["public_key_base64"] = base64.b64encode(self.public_key).decode("ascii")
        self.assert_code("unknown_field", lambda: self.verify(signature=signature))

    def test_self_selected_trust_policy_is_rejected_even_when_resigned(self) -> None:
        attacker = copy.deepcopy(self.checkpoint)
        attacker["trust_policy_digest"] = digest("9")
        attacker_signature = sign_checkpoint(
            attacker, private_key_bytes=PRIVATE_KEY_BYTES
        )
        self.assert_code(
            "trust_policy_pin_mismatch",
            lambda: self.verify(checkpoint=attacker, signature=attacker_signature),
        )

    def test_review_metadata_is_pinned_even_when_trusted_key_resigns(self) -> None:
        for field, replacement, code in (
            ("contribution_policy_digest", digest("3"), "contribution_policy_pin_mismatch"),
            ("reviewer_roster_digest", digest("4"), "reviewer_roster_pin_mismatch"),
            ("checkpoint_created_at_utc", "2026-08-29T00:00:00Z", "checkpoint_time_pin_mismatch"),
            ("appeal_deadline_utc", "2026-10-01T00:00:00Z", "appeal_deadline_pin_mismatch"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.checkpoint)
                changed[field] = replacement
                changed_signature = sign_checkpoint(
                    changed, private_key_bytes=PRIVATE_KEY_BYTES
                )
                self.assert_code(
                    code,
                    lambda changed=changed, changed_signature=changed_signature: self.verify(
                        checkpoint=changed, signature=changed_signature
                    ),
                )

    def test_malformed_signatures_fail_closed(self) -> None:
        for encoded in ("%%%", "", base64.b64encode(b"short").decode("ascii")):
            malformed = copy.deepcopy(self.signature)
            malformed["signature_base64"] = encoded
            self.assert_code(
                "malformed_signature",
                lambda malformed=malformed: self.verify(signature=malformed),
            )

    def test_signature_checkpoint_digest_must_match(self) -> None:
        signature = copy.deepcopy(self.signature)
        signature["checkpoint_sha256"] = digest("8")
        self.assert_code(
            "checkpoint_digest_mismatch", lambda: self.verify(signature=signature)
        )

    def test_noncanonical_embedded_snapshot_is_rejected(self) -> None:
        checkpoint = copy.deepcopy(self.checkpoint)
        checkpoint["ledger_snapshot_canonical_json"] = (
            checkpoint["ledger_snapshot_canonical_json"] + " "
        )
        self.assert_code("noncanonical_json", lambda: self.verify(checkpoint=checkpoint))

    def test_authority_flags_cannot_be_promoted_and_resigned(self) -> None:
        for field in (
            "canonical_credit_issued",
            "token_claim_created",
            "transferable",
            "convertible",
            "effect_authorized",
        ):
            promoted = copy.deepcopy(self.checkpoint)
            promoted[field] = True
            self.assert_code(
                "authority_boundary",
                lambda promoted=promoted: sign_checkpoint(
                    promoted, private_key_bytes=PRIVATE_KEY_BYTES
                ),
            )

    def test_dependency_is_optional_until_sign_or_verify_is_called(self) -> None:
        with patch(
            "contribution_ledger.checkpoint._load_crypto",
            side_effect=CheckpointDependencyError("optional dependency unavailable"),
        ):
            self.assertEqual(
                checkpoint_canonical_json(self.checkpoint), canonical_json(self.checkpoint)
            )
            with self.assertRaisesRegex(
                CheckpointDependencyError, "optional dependency unavailable"
            ):
                sign_checkpoint(self.checkpoint, private_key_bytes=PRIVATE_KEY_BYTES)
            with self.assertRaisesRegex(
                CheckpointDependencyError, "optional dependency unavailable"
            ):
                self.verify()


if __name__ == "__main__":
    unittest.main()
