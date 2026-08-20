#!/usr/bin/env python3
"""Conformance tests for the checkpointed semantic-delta experiment."""

from __future__ import annotations

import copy
import json
import unittest

import urusilla_session_delta_v09 as subject


class WorkloadAndDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sessions = subject.build_sessions()

    def test_frozen_workload_shape_and_digest(self) -> None:
        self.assertEqual(len(self.sessions), 24)
        self.assertTrue(all(len(session) == 32 for session in self.sessions))
        self.assertEqual(
            subject.corpus_digest(self.sessions),
            "729a602163a6e7698ea6aa9d9859dba17decfbed998afba219ec88b51aaeb419",
        )
        self.assertEqual(
            {session[0]["workflow"] for session in self.sessions},
            {
                "incident-triage",
                "inventory-reservation",
                "document-review",
                "route-planning",
            },
        )

    def test_sessions_are_correlated_but_state_changes_every_turn(self) -> None:
        for session in self.sessions:
            first = session[0]
            for state in session:
                self.assertEqual(state["session_id"], first["session_id"])
                self.assertEqual(state["participants"], first["participants"])
                self.assertEqual(state["objective"], first["objective"])
                self.assertEqual(state["constraints"], first["constraints"])
                self.assertEqual(state["annotations"], first["annotations"])
            self.assertEqual(
                [state["turn"] for state in session], list(range(32))
            )
            self.assertEqual(len({state["history_digest"] for state in session}), 32)

    def test_every_adjacent_delta_is_exact_and_deterministic(self) -> None:
        checked = 0
        for session in self.sessions:
            for base, target in zip(session[:-1], session[1:], strict=True):
                patch = subject.build_delta(base, target)
                self.assertEqual(subject.apply_delta(base, patch), target)
                self.assertEqual(subject.build_delta(base, target), patch)
                checked += 1
        self.assertEqual(checked, 24 * 31)

    def test_canonical_deletion_round_trip(self) -> None:
        base = self.sessions[0][8]
        target = copy.deepcopy(base)
        del target["evidence_index"]["e04"]
        target = subject.validate_state(target)
        patch = subject.build_delta(base, target)
        self.assertIn(["evidence_index", "e04"], patch["delete"])
        self.assertEqual(subject.apply_delta(base, patch), target)

    def test_noncanonical_or_ambiguous_patches_are_rejected(self) -> None:
        base = self.sessions[0][0]
        cases = (
            {"delete": [], "set": [[[], {}]]},
            {
                "delete": [["progress"], ["progress", "open_items"]],
                "set": [],
            },
            {
                "delete": [],
                "set": [
                    [["progress", "open_items"], 2],
                    [["progress", "open_items"], 3],
                ],
            },
            {
                "delete": [],
                "set": [
                    [["turn"], 1],
                    [["phase"], "analysis"],
                ],
            },
        )
        for patch in cases:
            with self.subTest(patch=patch):
                with self.assertRaises(subject.DeltaError):
                    subject.apply_delta(base, patch)

    def test_no_op_patch_is_rejected_as_nonminimal(self) -> None:
        base = self.sessions[0][0]
        patch = {"delete": [], "set": [[['phase'], base['phase']]]}
        with self.assertRaises(subject.DeltaError):
            subject.apply_delta(base, patch)

    def test_state_resource_and_type_limits_fail_closed(self) -> None:
        invalid_float = copy.deepcopy(self.sessions[0][0])
        invalid_float["progress"]["confidence_ppm"] = 0.5
        with self.assertRaises(subject.DeltaError):
            subject.validate_state(invalid_float)
        invalid_string = copy.deepcopy(self.sessions[0][0])
        invalid_string["latest_event"]["summary"] = "x" * (
            subject.MAX_STRING_BYTES + 1
        )
        with self.assertRaises(subject.DeltaError):
            subject.validate_state(invalid_string)


class RecordAndStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = subject.build_sessions()[0]
        cls.session_id = cls.session[0]["session_id"]

    def test_full_and_delta_records_reconstruct_exact_state(self) -> None:
        decoder = subject.SessionDecoder(self.session_id)
        for index, state in enumerate(self.session):
            record = (
                subject.encode_full(state)
                if index == 0
                else subject.encode_delta(self.session[index - 1], state)
            )
            self.assertEqual(decoder.open(record), state)

    def test_record_header_is_complete_and_canonical(self) -> None:
        full = subject.encode_full(self.session[0])
        parsed = subject.parse_record(full)
        self.assertEqual(parsed.mode, "F")
        self.assertEqual(parsed.session_id, self.session_id)
        self.assertEqual(parsed.sequence, 0)
        self.assertEqual(parsed.base_digest, subject.ZERO_DIGEST)
        self.assertEqual(len(full) - len(parsed.payload), subject.HEADER_CHARACTERS)
        self.assertEqual(
            subject.encode_record(
                parsed.mode,
                parsed.session_id,
                parsed.sequence,
                parsed.base_digest,
                parsed.payload,
            ),
            full,
        )

    def test_mutation_wrong_key_and_wrong_session_are_rejected(self) -> None:
        record = subject.encode_delta(self.session[0], self.session[1])
        payload_index = subject.HEADER_CHARACTERS
        mutations = (
            record[:2] + "X" + record[3:],
            record[:payload_index] + "[" + record[payload_index + 1 :],
            record[:-1] + ("X" if record[-1] != "X" else "Y"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[:16]):
                with self.assertRaises(subject.DeltaError):
                    subject.parse_record(mutation)
        with self.assertRaises(subject.DeltaError):
            subject.parse_record(record, key=b"different-integrity-key-32bytes!!")
        other_session = subject.build_sessions()[1][0]["session_id"]
        with self.assertRaises(subject.DeltaError):
            subject.SessionDecoder(other_session).open(record)

    def test_loss_reorder_replay_and_checkpoint_resync(self) -> None:
        full0 = subject.encode_full(self.session[0])
        delta1 = subject.encode_delta(self.session[0], self.session[1])
        delta2 = subject.encode_delta(self.session[1], self.session[2])
        checkpoint8 = subject.encode_full(self.session[8])

        decoder = subject.SessionDecoder(self.session_id)
        decoder.open(full0)
        with self.assertRaises(subject.DeltaError):
            decoder.open(delta2)
        self.assertEqual(decoder.open(delta1), self.session[1])
        with self.assertRaises(subject.DeltaError):
            decoder.open(delta1)

        reset = subject.SessionDecoder(self.session_id)
        with self.assertRaises(subject.DeltaError):
            reset.open(delta1, allow_checkpoint_resync=True)
        self.assertEqual(
            reset.open(checkpoint8, allow_checkpoint_resync=True), self.session[8]
        )

    def test_noncanonical_full_or_patch_payload_is_rejected_after_authentication(self) -> None:
        full_value = copy.deepcopy(self.session[0])
        noncanonical_full = json.dumps(full_value, ensure_ascii=False)
        full_record = subject.encode_record(
            "F",
            self.session_id,
            0,
            subject.ZERO_DIGEST,
            noncanonical_full,
        )
        with self.assertRaises(subject.DeltaError):
            subject.SessionDecoder(self.session_id).open(full_record)

        patch = subject.build_delta(self.session[0], self.session[1])
        noncanonical_patch = json.dumps(patch, ensure_ascii=False)
        delta_record = subject.encode_record(
            "D",
            self.session_id,
            1,
            subject.state_digest(self.session[0]),
            noncanonical_patch,
        )
        decoder = subject.SessionDecoder(self.session_id)
        decoder.open(subject.encode_full(self.session[0]))
        with self.assertRaises(subject.DeltaError):
            decoder.open(delta_record)


class FrozenMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.study = subject.collect_study()

    def test_four_pinned_tokenizers_and_matrix_identity(self) -> None:
        self.assertEqual(
            tuple(profile.key for profile in self.study.profiles),
            tuple(subject.EXPECTED_TOKENIZER_FINGERPRINTS),
        )
        self.assertEqual(self.study.matrix_digest, subject.EXPECTED_MATRIX_DIGEST)

    def test_all_plans_are_exact_deterministic_and_no_regression(self) -> None:
        expected_per_row = 24 * 32
        self.assertEqual(len(self.study.aggregates), 4 * 6)
        for result in self.study.aggregates:
            with self.subTest(
                tokenizer=result.tokenizer_key, interval=result.interval
            ):
                self.assertEqual(result.records, expected_per_row)
                self.assertEqual(result.exact, expected_per_row)
                self.assertEqual(result.deterministic, expected_per_row)
                self.assertLessEqual(result.token_total, result.full_baseline_tokens)
                self.assertLessEqual(
                    result.cold_checkpoint_tokens, result.token_total
                )
                if result.interval == 1:
                    self.assertEqual(result.token_total, result.full_baseline_tokens)
                    self.assertEqual(result.delta_wins, 0)
                else:
                    self.assertGreater(result.delta_wins, 0)
                    self.assertLess(result.token_total, result.full_baseline_tokens)

    def test_byte_selector_is_exact_deterministic_and_no_regression(self) -> None:
        expected_per_row = 24 * 32
        self.assertEqual(len(self.study.byte_aggregates), 6)
        for result in self.study.byte_aggregates:
            with self.subTest(interval=result.interval):
                self.assertEqual(result.records, expected_per_row)
                self.assertEqual(result.exact, expected_per_row)
                self.assertEqual(result.deterministic, expected_per_row)
                self.assertLessEqual(result.selected_bytes, result.full_bytes)

    def test_representative_fault_campaign_fails_closed(self) -> None:
        fault = self.study.fault_results
        self.assertEqual(fault.records, 24 * 32)
        self.assertEqual(fault.integrity_rejected, fault.integrity_attempted)
        self.assertEqual(fault.reset_delta_rejected, fault.reset_delta_attempted)
        self.assertGreater(fault.independent_checkpoints, 0)
        self.assertEqual(fault.replay_rejected, fault.replay_attempted)
        self.assertEqual(fault.out_of_order_rejected, fault.out_of_order_attempted)
        self.assertEqual(fault.post_loss_rejected, fault.loss_attempted)
        self.assertEqual(fault.checkpoint_recovered, fault.loss_attempted)
        self.assertLessEqual(
            fault.maximum_skipped_records, subject.REPRESENTATIVE_INTERVAL - 1
        )


if __name__ == "__main__":
    unittest.main()
