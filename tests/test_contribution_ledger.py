from __future__ import annotations

import copy
import json
import unittest

from contribution_ledger import (
    LEDGER_SCHEMA_VERSION,
    ContributionLedger,
    LedgerValidationError,
    canonical_json,
    merkle_root,
)


def digest(character: str) -> str:
    return character * 64


class ContributionLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ContributionLedger("local-research-ledger")
        self.epoch = self.ledger.open_epoch(
            epoch_id="epoch-001", budget_points=100, policy_digest=digest("a")
        )

    def assert_code(self, code: str, callback) -> None:
        with self.assertRaises(LedgerValidationError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def register(
        self,
        *,
        contributor_ref: str = "subject:alice",
        commit: str = "b",
        claim: str = "c",
        artifact: str = "d",
    ) -> dict:
        return self.ledger.register_contribution(
            epoch_id="epoch-001",
            contributor_ref=contributor_ref,
            contribution_class="runtime",
            commit_digest=digest(commit),
            claim_digest=digest(claim),
            artifact_digests=[digest(artifact)],
        )

    def award(self, contribution: dict, points: int = 40) -> dict:
        return self.ledger.grant_award(
            epoch_id="epoch-001",
            contribution_id=contribution["payload"]["contribution_id"],
            points=points,
            decision_digest=digest("e"),
        )

    def test_canonical_json_is_stable_and_float_free(self) -> None:
        self.assertEqual(canonical_json({"z": 1, "a": "우루실라"}), '{"a":"우루실라","z":1}')
        self.assert_code("invalid_json_type", lambda: canonical_json({"value": 1.5}))
        self.assert_code("invalid_json", lambda: canonical_json({"value": "\ud800"}))

    def test_hash_chain_and_replay_verification(self) -> None:
        contribution = self.register()
        award = self.award(contribution)
        self.assertEqual(contribution["seq"], 1)
        self.assertEqual(contribution["prev_event_id"], self.epoch["event_id"])
        self.assertEqual(award["prev_event_id"], contribution["event_id"])
        self.ledger.verify()

    def test_exact_contribution_is_identity_independent_and_unique(self) -> None:
        first = self.register(contributor_ref="subject:alice")
        self.assert_code(
            "duplicate_contribution",
            lambda: self.register(contributor_ref="subject:bob"),
        )
        self.assertEqual(len(self.ledger.events), 2)
        self.assertEqual(
            first["payload"]["contribution_id"],
            self.ledger.export_snapshot()["contributions"][0]["contribution_id"],
        )

    def test_contribution_id_must_match_evidence(self) -> None:
        payload = {
            "epoch_id": "epoch-001",
            "contribution_id": digest("f"),
            "contributor_ref": "subject:alice",
            "contribution_class": "runtime",
            "commit_digest": digest("b"),
            "claim_digest": digest("c"),
            "artifact_digests": [digest("d")],
        }
        self.assert_code(
            "contribution_id_mismatch",
            lambda: self.ledger.append("contribution_registered", payload),
        )

    def test_fixed_epoch_budget_and_integer_points(self) -> None:
        first = self.register()
        self.award(first, 70)
        second = self.register(commit="1", claim="2", artifact="3")
        self.assert_code("budget_exceeded", lambda: self.award(second, 31))
        self.assert_code("invalid_points", lambda: self.award(second, True))
        self.assert_code("invalid_points", lambda: self.award(second, 0))
        self.assert_code("invalid_json_type", lambda: self.award(second, 1.5))

    def test_epoch_budget_cannot_be_changed(self) -> None:
        self.assert_code(
            "duplicate_epoch",
            lambda: self.ledger.open_epoch(
                epoch_id="epoch-001",
                budget_points=200,
                policy_digest=digest("f"),
            ),
        )

    def test_transfer_approve_and_unknown_events_are_unavailable(self) -> None:
        for event_type in ("transfer", "approve", "mint", "convert", "redeem"):
            self.assert_code(
                "unsupported_event",
                lambda event_type=event_type: self.ledger.append(event_type, {}),
            )

    def test_privacy_fields_are_rejected_recursively(self) -> None:
        for key in ("email", "raw_prompt", "secret", "private-key", "api_key"):
            self.assert_code(
                "privacy_field_forbidden",
                lambda key=key: self.ledger.append(
                    "epoch_opened",
                    {
                        "epoch_id": "epoch-private",
                        "budget_points": 1,
                        "policy_digest": digest("f"),
                        "nested": {key: "must-not-enter-ledger"},
                    },
                ),
            )

    def test_unknown_payload_and_event_fields_fail_closed(self) -> None:
        self.assert_code(
            "unknown_field",
            lambda: self.ledger.append(
                "epoch_opened",
                {
                    "epoch_id": "epoch-extra",
                    "budget_points": 1,
                    "policy_digest": digest("f"),
                    "ticker": "NOPE",
                },
            ),
        )
        event = copy.deepcopy(self.ledger.events[0])
        event["extra"] = False
        line = canonical_json(event) + "\n"
        self.assert_code("unknown_field", lambda: ContributionLedger.from_jsonl(line))

    def test_unknown_schema_fails_closed(self) -> None:
        event = copy.deepcopy(self.ledger.events[0])
        event["schema_version"] = "future/9"
        event["event_id"] = digest("f")
        self.assert_code(
            "unsupported_schema",
            lambda: ContributionLedger.from_jsonl(canonical_json(event) + "\n"),
        )

    def test_event_tampering_is_detected(self) -> None:
        events = list(self.ledger.events)
        events[0]["payload"]["budget_points"] = 101
        self.assert_code(
            "event_id_mismatch",
            lambda: ContributionLedger.from_jsonl(canonical_json(events[0]) + "\n"),
        )

    def test_sequence_replay_is_detected_without_state_change(self) -> None:
        original = self.ledger.to_jsonl()
        replayed = original + original
        self.assert_code(
            "sequence_mismatch", lambda: ContributionLedger.from_jsonl(replayed)
        )
        self.assertEqual(len(self.ledger.events), 1)

    def test_previous_event_tampering_is_detected(self) -> None:
        self.register()
        events = list(self.ledger.events)
        events[1]["prev_event_id"] = digest("f")
        text = canonical_json(events[0]) + "\n" + canonical_json(events[1]) + "\n"
        self.assert_code(
            "previous_event_mismatch", lambda: ContributionLedger.from_jsonl(text)
        )

    def test_revocation_is_append_only_and_releases_budget(self) -> None:
        contribution = self.register()
        award = self.award(contribution, 90)
        before = copy.deepcopy(self.ledger.events)
        revocation = self.ledger.revoke_award(
            award_event_id=award["event_id"],
            reason_code="invalid_evidence",
            decision_digest=digest("f"),
        )
        after = self.ledger.events
        self.assertEqual(after[: len(before)], before)
        self.assertEqual(revocation["event_type"], "award_revoked")
        snapshot = self.ledger.export_snapshot()
        self.assertEqual(snapshot["epochs"][0]["active_awarded_points"], 0)
        self.assertEqual(snapshot["epochs"][0]["revoked_points"], 90)
        self.assertEqual(snapshot["epochs"][0]["available_points"], 100)
        self.assertEqual(snapshot["awards"][0]["status"], "revoked")
        self.assert_code(
            "duplicate_revocation",
            lambda: self.ledger.revoke_award(
                award_event_id=award["event_id"],
                reason_code="still_invalid",
                decision_digest=digest("1"),
            ),
        )

    def test_revoked_contribution_cannot_receive_a_second_award(self) -> None:
        contribution = self.register()
        award = self.award(contribution)
        self.ledger.revoke_award(
            award_event_id=award["event_id"],
            reason_code="invalid_evidence",
            decision_digest=digest("f"),
        )
        self.assert_code("duplicate_award", lambda: self.award(contribution, 1))

    def test_released_budget_can_fund_a_different_contribution(self) -> None:
        first = self.register()
        award = self.award(first, 100)
        self.ledger.revoke_award(
            award_event_id=award["event_id"],
            reason_code="invalid_evidence",
            decision_digest=digest("f"),
        )
        second = self.register(commit="1", claim="2", artifact="3")
        self.award(second, 100)
        self.assertEqual(
            self.ledger.export_snapshot()["epochs"][0]["active_awarded_points"],
            100,
        )

    def test_correction_is_append_only_and_has_no_economic_effect(self) -> None:
        contribution = self.register()
        award = self.award(contribution, 40)
        before = copy.deepcopy(self.ledger.events)
        correction = self.ledger.record_correction(
            target_event_id=award["event_id"],
            reason_code="metadata_error",
            corrected_record_digest=digest("f"),
        )
        self.assertEqual(self.ledger.events[: len(before)], tuple(before))
        snapshot = self.ledger.export_snapshot()
        self.assertEqual(snapshot["epochs"][0]["active_awarded_points"], 40)
        self.assertEqual(
            snapshot["corrections"][0]["correction_event_id"],
            correction["event_id"],
        )
        self.assert_code(
            "duplicate_correction",
            lambda: self.ledger.record_correction(
                target_event_id=award["event_id"],
                reason_code="second_error",
                corrected_record_digest=digest("1"),
            ),
        )

    def test_jsonl_round_trip_is_exact(self) -> None:
        contribution = self.register()
        self.award(contribution)
        encoded = self.ledger.to_jsonl()
        restored = ContributionLedger.from_jsonl(encoded)
        self.assertEqual(restored.to_jsonl(), encoded)
        self.assertEqual(restored.snapshot_json(), self.ledger.snapshot_json())
        restored.verify()

    def test_noncanonical_and_duplicate_key_json_are_rejected(self) -> None:
        canonical_line = self.ledger.to_jsonl().rstrip("\n")
        pretty = json.dumps(json.loads(canonical_line), indent=2, sort_keys=True)
        self.assert_code(
            "noncanonical_json",
            lambda: ContributionLedger.from_jsonl(pretty.replace("\n", " ") + "\n"),
        )
        duplicate = canonical_line.replace(
            '{"event_id":',
            '{"event_id":"' + digest("f") + '","event_id":',
            1,
        )
        self.assert_code(
            "duplicate_json_key", lambda: ContributionLedger.from_jsonl(duplicate + "\n")
        )

    def test_snapshot_and_merkle_export_are_deterministic(self) -> None:
        contribution = self.register()
        self.award(contribution)
        first = self.ledger.export_snapshot()
        second = self.ledger.export_snapshot()
        self.assertEqual(first, second)
        self.assertEqual(canonical_json(first), self.ledger.snapshot_json())
        event_ids = [event["event_id"] for event in self.ledger.events]
        self.assertEqual(first["events_merkle_root"], merkle_root(event_ids))
        self.assertFalse(first["transferable"])
        self.assertFalse(first["convertible"])
        self.assertTrue(first["non_financial"])
        self.assertNotIn("wallet", self.ledger.snapshot_json())

    def test_returned_events_cannot_mutate_internal_history(self) -> None:
        returned = self.register()
        original = self.ledger.to_jsonl()
        returned["payload"]["contributor_ref"] = "subject:mallory"
        exported = self.ledger.events
        exported[1]["payload"]["contributor_ref"] = "subject:mallory"
        self.assertEqual(self.ledger.to_jsonl(), original)
        self.ledger.verify()

    def test_cross_ledger_event_is_rejected(self) -> None:
        event = self.ledger.events[0]
        event["ledger_id"] = "another-ledger"
        self.assert_code(
            "event_id_mismatch",
            lambda: ContributionLedger.from_jsonl(canonical_json(event) + "\n"),
        )

    def test_snapshot_has_only_nonfinancial_state(self) -> None:
        snapshot = self.ledger.export_snapshot()
        serialized = canonical_json(snapshot)
        for forbidden in ("ticker", "price", "exchange", "conversion_rate", "allowance"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(snapshot["ledger_schema_version"], LEDGER_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
