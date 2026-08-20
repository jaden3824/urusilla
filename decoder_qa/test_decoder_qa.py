#!/usr/bin/env python3
"""Deterministic regression tests for the saved decoder implementation."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from decoder_qa import qa_core as qa


class DeterministicCampaignTests(unittest.TestCase):
    def test_canonical_roundtrip_campaign(self) -> None:
        result = qa.roundtrip_campaign()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["total_cases"], 1097)

    def test_boundary_campaign(self) -> None:
        result = qa.boundary_campaign()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["total_cases"], 1952)

    def test_fixed_mutation_campaign(self) -> None:
        result = qa.mutation_campaign()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["total_cases"], 2048)

    def test_replay_campaign(self) -> None:
        result = qa.replay_campaign()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["total_cases"], 135)

    def test_known_finding_manifest_is_current(self) -> None:
        result = qa.known_defect_campaign()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["findings"], [])
        self.assertEqual(
            result["resolved_ids"],
            [
                "DQA-001",
                "DQA-002",
                "DQA-003",
                "DQA-004",
                "DQA-005",
                "DQA-006",
                "DQA-007",
                "DQA-008",
                "DQA-009",
                "DQA-010",
            ],
        )


class SharedCodeRegressionTests(unittest.TestCase):
    """Regression tests; only unresolved shared-code cases are expected failures."""

    def test_DQA_001_semantic_type_errors_are_project_domain_errors(self) -> None:
        for field in ("constraint.mode", "evidence.stance"):
            for frame, decoder in zip(
                qa.checksum_valid_semantic_type_frames(field),
                (qa.reference.decode_message, qa.wire.decode_message),
            ):
                with self.subTest(field=field, decoder=decoder.__module__):
                    with self.assertRaises(qa.reference.UrusillaError):
                        decoder(frame)

    def test_DQA_002_malformed_mapping_raises_project_domain_error(self) -> None:
        message = qa.reference.demo_message()
        message[1] = "unexpected"
        with self.assertRaises(qa.reference.UrusillaError):
            qa.reference.normalize_message(message)

    def test_DQA_003_duplicate_json_members_are_rejected(self) -> None:
        with patch.object(Path, "open", return_value=io.StringIO('{"field":1,"field":2}')):
            with self.assertRaises(qa.reference.UrusillaError):
                qa.reference._load_json(Path("unused.json"))

    def test_DQA_004_capsule_pins_saved_codec_digest(self) -> None:
        capsule = json.loads((qa.ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            capsule["implementation_artifacts"]["reference_codec"]["sha256"],
            qa.sha256_file(qa.ROOT / "urusilla.py"),
        )

    def test_DQA_005_extension_quarantine_is_recursive(self) -> None:
        message = qa.reference.demo_message()
        message["body"]["condition"] = {"kind": "x:nested", "value": 1}
        with self.assertRaises(qa.reference.ValidationError):
            qa.reference.normalize_message(message)

    def test_DQA_006_capsule_query_kind_is_accepted(self) -> None:
        message = qa.reference.demo_message()
        message["act"] = "QUERY"
        message["body"] = {
            "kind": "question-plus-answer-schema",
            "question": {"kind": "claim", "predicate": "p"},
            "answer_schema": "u:a",
        }
        qa.reference.normalize_message(message)
        message["body"].pop("kind")
        with self.assertRaises(qa.reference.ValidationError):
            qa.reference.normalize_message(message)

    def test_DQA_007_tuples_are_rejected_as_noncanonical(self) -> None:
        message = qa.reference.demo_message()
        message["recipients"] = tuple(message["recipients"])
        with self.assertRaises(qa.reference.ValidationError):
            qa.reference.normalize_message(message)

    def test_DQA_008_thread_state_is_conversation_scoped(self) -> None:
        profile = qa.dialogue.default_profile_document()
        corpus = list(qa.dialogue.build_positive_coverage_corpus(profile))
        ledger = qa.dialogue.ConversationLedger(profile)
        qa._append_all(ledger, corpus[:11])
        message = copy.deepcopy(corpus[7])
        message["id"] = qa.dialogue.stable_uuid("qa:new-conversation:same-thread")
        message["conversation_id"] = qa.dialogue.stable_uuid("qa:new-conversation")
        message["causes"] = []
        message["logical_clock"] = 1
        ledger.append(message)
        snapshot = ledger.snapshot()
        self.assertEqual(
            snapshot["thread_states"][qa._snapshot_thread_key(corpus[10])],
            "COMMITTED",
        )
        self.assertEqual(
            snapshot["thread_states"][qa._snapshot_thread_key(message)],
            "REQUESTED",
        )

    def test_DQA_009_target_thread_must_match_envelope_thread(self) -> None:
        profile = qa.dialogue.default_profile_document()
        corpus = list(qa.dialogue.build_positive_coverage_corpus(profile))
        ledger = qa.dialogue.ConversationLedger(profile)
        qa._append_all(ledger, corpus[:16])
        message = copy.deepcopy(corpus[11])
        message["id"] = qa.dialogue.stable_uuid("qa:progress:cross-thread")
        message["causes"] = [corpus[15]["id"]]
        message["logical_clock"] = 17
        message["thread_id"] = corpus[15]["thread_id"]
        with self.assertRaises(qa.dialogue.LedgerError):
            ledger.append(message)

    def test_DQA_010_target_must_be_a_prior_cause(self) -> None:
        profile = qa.dialogue.default_profile_document()
        corpus = list(qa.dialogue.build_positive_coverage_corpus(profile))
        ledger = qa.dialogue.ConversationLedger(profile)
        qa._append_all(ledger, corpus[:11])
        message = copy.deepcopy(corpus[11])
        message["id"] = qa.dialogue.stable_uuid("qa:progress:no-cause")
        message["causes"] = []
        message["logical_clock"] = 0
        with self.assertRaises(qa.dialogue.LedgerError):
            ledger.append(message)


if __name__ == "__main__":
    unittest.main()
