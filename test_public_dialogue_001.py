from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from urusilla import ValidationError, decode_message, encode_message, normalize_message


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "public_dialogue_001"
CAPSULE_SHA256 = "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
MISSING_ANSWER_SCHEMA = "urn:urusilla:schema:peer-dialogue-reply:0.1"
MISSING_DIALOGUE_SCHEMA = "urn:urusilla:dialogue:0.1"


def load_json(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


class PublicDialogueProbe001Tests(unittest.TestCase):
    def test_pinned_capsule_identity_matches_external_receipt(self) -> None:
        capsule_bytes = (ROOT / "urusilla_capsule_v0_1.json").read_bytes()
        self.assertEqual(len(capsule_bytes), 33_476)
        self.assertEqual(hashlib.sha256(capsule_bytes).hexdigest(), CAPSULE_SHA256)

    def test_structural_validator_does_not_enforce_schema_resolution(self) -> None:
        message = load_json("original_query.json")
        self.assertEqual(message["body"]["answer_schema"], MISSING_ANSWER_SCHEMA)
        canonical = normalize_message(message)
        frame = encode_message(message)
        self.assertEqual(decode_message(frame), canonical)
        self.assertEqual(encode_message(canonical), frame)

    def test_original_schema_identifiers_are_not_defined_by_pinned_artifacts(self) -> None:
        message = load_json("original_query.json")
        self.assertEqual(message["body"]["answer_schema"], MISSING_ANSWER_SCHEMA)
        self.assertEqual(message["schema"], MISSING_DIALOGUE_SCHEMA)
        capsule_text = (ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8")
        specification_text = (ROOT / "urusilla_v0_1_spec.md").read_text(encoding="utf-8")
        for missing_schema in (MISSING_ANSWER_SCHEMA, MISSING_DIALOGUE_SCHEMA):
            self.assertNotIn(missing_schema, capsule_text)
            self.assertNotIn(missing_schema, specification_text)

    def test_capsule_query_body_table_has_no_matching_node_manifest(self) -> None:
        capsule = json.loads(
            (ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8")
        )
        semantic_kernel = capsule["semantic_kernel"]["manifest"]
        self.assertIn(
            "question-plus-answer-schema",
            semantic_kernel["act_body_kinds"]["QUERY"],
        )
        self.assertNotIn(
            "question-plus-answer-schema",
            semantic_kernel["node_kinds"],
        )

    def test_external_reply_reproduces_unknown_answer_kind_rejection(self) -> None:
        message = load_json("external_reply.json")
        with self.assertRaisesRegex(
            ValidationError,
            "unknown node kind 'answer'.*local prototype extensions require x:<name>",
        ):
            normalize_message(message)

    def test_project_continuation_uses_two_structurally_valid_core_acts(self) -> None:
        assertion = load_json("project_schema_resolution_assertion.json")
        followup = load_json("project_followup_query.json")
        capsule = json.loads(
            (ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8")
        )
        core_schema = capsule["identifiers"]["core_schema_id"]

        self.assertEqual(assertion["act"], "ASSERT")
        self.assertEqual(assertion["body"]["kind"], "claim")
        self.assertEqual(followup["act"], "QUERY")
        self.assertEqual(followup["body"]["kind"], "question-plus-answer-schema")
        self.assertEqual(assertion["schema"], core_schema)
        self.assertEqual(followup["schema"], core_schema)
        self.assertEqual(followup["body"]["answer_schema"], core_schema)
        self.assertEqual(followup["reply_to"], assertion["id"])

        for message in (assertion, followup):
            canonical = normalize_message(message)
            frame = encode_message(message)
            self.assertEqual(decode_message(frame), canonical)
            self.assertEqual(encode_message(canonical), frame)

    def test_continuation_does_not_claim_efficiency_or_change_core_version(self) -> None:
        assertion = load_json("project_schema_resolution_assertion.json")
        followup = load_json("project_followup_query.json")
        for message in (assertion, followup):
            self.assertEqual(message["meta"]["language_version"], "0.1.0")
            self.assertFalse(message["meta"]["token_saving_claim"])
            self.assertFalse(message["meta"]["external_effects"])
            self.assertFalse(message["meta"]["permission_expansion"])
            self.assertFalse(message["meta"]["persistence"])
            self.assertFalse(message["meta"]["spending"])


if __name__ == "__main__":
    unittest.main()
