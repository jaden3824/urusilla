"""Focused tests for the offline evidence-log integrity core."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evidence_log_verify", ROOT / "verify.py")
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def accepted_records():
    return copy.deepcopy(load("test-vectors/valid-accepted-chain.json")["log"]["records"])


def new_correction(template, submission_id: str, target: str, second: int):
    event = copy.deepcopy(template)
    event.update(
        {
            "sequence": 0,
            "recorded_at": f"2026-08-23T00:00:{second:02d}Z",
            "submission_id": submission_id,
            "supersedes_submission_id": target,
        }
    )
    event["quick_60s"]["response"]["reason"] = "Corrected bounded response."
    return event


def state_event(template, submission_id: str, second: int):
    event = copy.deepcopy(template)
    event.update(
        {
            "sequence": 0,
            "recorded_at": f"2026-08-23T00:00:{second:02d}Z",
            "submission_id": submission_id,
        }
    )
    return event


def superseded_event(template, submission_id: str, successor: str, second: int):
    event = copy.deepcopy(template)
    event.update(
        {
            "sequence": 0,
            "recorded_at": f"2026-08-23T00:00:{second:02d}Z",
            "submission_id": submission_id,
            "event_type": "submission-superseded",
            "state": "superseded",
            "quick_60s": None,
            "review": None,
            "supersedes_submission_id": None,
            "superseded_by_submission_id": successor,
        }
    )
    event["state_reason"] = {
        "code": "accepted-correction",
        "public_detail": "The exact accepted successor now replaces this result for current review.",
    }
    return event


def seal(records):
    log = {
        "schema_version": VERIFY.LOG_SCHEMA,
        "log_id": VERIFY.LOG_ID,
        "log_epoch": 1,
        "records": records,
        "log_sha256": "sha256:" + "0" * 64,
    }
    for sequence, event in enumerate(records, start=1):
        event["sequence"] = sequence
    VERIFY._reseal_vector_log(log)
    return log


class EvidenceLogVerifierTests(unittest.TestCase):
    def assert_code(self, code, callback):
        with self.assertRaises(VERIFY.VerificationError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_empty_root_and_static_vectors(self):
        VERIFY.verify_root(ROOT)
        self.assertEqual(VERIFY.verify_vectors(ROOT), 4)

    def test_privacy_fails_before_public_chain_eligibility(self):
        records = accepted_records()
        records[0]["privacy"]["contains_sensitive_digest"] = True
        log = seal(records)
        self.assert_code("privacy-not-public", lambda: VERIFY.verify_log(log))

    def test_accepted_correction_can_supersede_only_after_acceptance(self):
        records = accepted_records()
        correction = new_correction(records[0], "sub-vector-002", "sub-vector-001", 4)
        corrected_structural = state_event(records[1], "sub-vector-002", 5)
        corrected_accepted = state_event(records[2], "sub-vector-002", 6)
        old_superseded = superseded_event(records[2], "sub-vector-001", "sub-vector-002", 7)
        log = seal(records + [correction, corrected_structural, corrected_accepted, old_superseded])
        VERIFY.verify_log(log)

    def test_unaccepted_correction_cannot_replace_current_evidence(self):
        records = accepted_records()
        correction = new_correction(records[0], "sub-vector-002", "sub-vector-001", 4)
        old_superseded = superseded_event(records[2], "sub-vector-001", "sub-vector-002", 5)
        log = seal(records + [correction, old_superseded])
        self.assert_code("correction-not-accepted", lambda: VERIFY.verify_log(log))

    def test_two_direct_successors_are_rejected(self):
        records = accepted_records()
        correction_one = new_correction(records[0], "sub-vector-002", "sub-vector-001", 4)
        correction_two = new_correction(records[0], "sub-vector-003", "sub-vector-001", 5)
        log = seal(records + [correction_one, correction_two])
        self.assert_code("competing-correction", lambda: VERIFY.verify_log(log))

    def test_retraction_is_append_only_and_requires_prior_acceptance(self):
        records = accepted_records()
        retraction = state_event(records[2], "sub-vector-001", 4)
        retraction.update(
            {
                "event_type": "submission-retracted",
                "state": "retracted",
                "review": {
                    "kind": "maintainer",
                    "reviewer_id": "maintainer:test-reviewer",
                    "decision": "fail",
                    "accepted_evidence_scope": None,
                    "public_reason": "A later integrity finding removed the result from current evidentiary use.",
                },
            }
        )
        VERIFY.verify_log(seal(records + [retraction]))

        too_early = accepted_records()[:2]
        invalid_retraction = state_event(retraction, "sub-vector-001", 3)
        self.assert_code(
            "invalid-state-transition",
            lambda: VERIFY.verify_log(seal(too_early + [invalid_retraction])),
        )

    def test_empty_checkpoint_cannot_claim_a_head(self):
        log = VERIFY.verify_log(load("epochs/00000001/log.json"))
        checkpoint = load("epochs/00000001/checkpoints/empty.json")
        checkpoint["head_record_sha256"] = VERIFY.EMPTY_SHA256
        checkpoint["checkpoint_sha256"] = VERIFY.object_digest(
            checkpoint, "checkpoint_sha256"
        )
        self.assert_code(
            "empty-checkpoint", lambda: VERIFY.verify_checkpoint(checkpoint, log)
        )

    def test_discovery_cannot_advertise_writes(self):
        log = VERIFY.verify_log(load("epochs/00000001/log.json"))
        checkpoint = VERIFY.verify_checkpoint(
            load("epochs/00000001/checkpoints/empty.json"), log
        )
        discovery = load("discovery.json")
        discovery["writes_enabled"] = True
        discovery["discovery_sha256"] = VERIFY.object_digest(
            discovery, "discovery_sha256"
        )
        self.assert_code(
            "write-path-advertised",
            lambda: VERIFY.verify_discovery(discovery, ROOT, log, checkpoint),
        )

    def test_discovery_binds_schema_and_verifier_bytes(self):
        log = VERIFY.verify_log(load("epochs/00000001/log.json"))
        checkpoint = VERIFY.verify_checkpoint(
            load("epochs/00000001/checkpoints/empty.json"), log
        )
        discovery = load("discovery.json")
        discovery["event_schema_sha256"] = VERIFY.EMPTY_SHA256
        discovery["discovery_sha256"] = VERIFY.object_digest(
            discovery, "discovery_sha256"
        )
        self.assert_code(
            "discovery-artifact",
            lambda: VERIFY.verify_discovery(discovery, ROOT, log, checkpoint),
        )


if __name__ == "__main__":
    unittest.main()
