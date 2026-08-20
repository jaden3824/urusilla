#!/usr/bin/env python3
"""Conformance-smoke tests for the Urusilla v0.1 reference prototype."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import urusilla as reference
from urusilla import (
    DecodeError,
    MAX_COLLECTION_ITEMS,
    MAX_SEMANTIC_NODES,
    ValidationError,
    decode_message,
    demo_message,
    encode_message,
    normalize_message,
    translate_message,
    validate_effect_eligibility,
)


class UrusillaTests(unittest.TestCase):
    @staticmethod
    def _aggregate_message(scalar_count: int) -> dict:
        message = demo_message()
        message["act"] = "ASSERT"
        groups = []
        remaining = scalar_count
        while remaining:
            size = min(remaining, MAX_COLLECTION_ITEMS)
            groups.append([None] * size)
            remaining -= size
        message["body"] = {
            "kind": "x:aggregate-probe",
            "value": groups,
        }
        message["meta"] = {}
        return message

    @staticmethod
    def _aggregate_frame(scalar_count: int) -> bytes:
        groups = []
        remaining = scalar_count
        while remaining:
            size = min(remaining, MAX_COLLECTION_ITEMS)
            groups.append([None] * size)
            remaining -= size
        strings = (
            "urn:agent:probe",
            "urn:agent:sink",
            "urn:example:schema",
            "kind",
            "x:aggregate-probe",
            "value",
        )
        table = {value: index for index, value in enumerate(strings)}
        payload = bytearray()
        payload += reference._encode_uvarint(len(strings))
        for value in strings:
            raw = value.encode("utf-8")
            payload += reference._encode_uvarint(len(raw)) + raw
        payload += uuid.UUID(int=1).bytes
        payload += uuid.UUID(int=2).bytes
        payload += reference._encode_uvarint(table["urn:agent:probe"])
        payload += reference._encode_uvarint(1)
        payload += reference._encode_uvarint(table["urn:agent:sink"])
        payload.append(reference.ACT_TO_CODE["ASSERT"])
        payload.append(0)
        payload += reference._encode_uvarint(table["urn:example:schema"])
        payload += reference._encode_uvarint(0) * 3
        payload.append(0)
        payload += reference._encode_value(
            {"kind": "x:aggregate-probe", "value": groups}, table
        )
        payload += reference._encode_value({}, table)
        header = (
            reference.MAGIC
            + bytes([reference.FLAGS])
            + reference._encode_uvarint(len(payload))
        )
        checksum = hashlib.sha256(header + payload).digest()[: reference.CHECKSUM_SIZE]
        return header + payload + checksum

    def test_demo_round_trip_is_exact_and_canonical(self) -> None:
        source = demo_message()
        frame = encode_message(source)
        decoded = decode_message(frame)
        self.assertEqual(decoded, normalize_message(source))
        self.assertEqual(encode_message(decoded), frame)

    def test_grammar_capsule_frozen_identities_are_self_consistent(self) -> None:
        root = Path(__file__).resolve().parent
        capsule_path = root / "urusilla_capsule_v0_1.json"
        capsule_bytes = capsule_path.read_bytes()
        capsule = json.loads(capsule_bytes)

        self.assertEqual(
            hashlib.sha256(capsule_bytes).hexdigest(),
            "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
        )
        self.assertEqual(capsule["release_status"], "experimental-unsigned")
        self.assertEqual(capsule["language"]["name"], "Urusilla")
        self.assertEqual(
            capsule["language"]["name_status"],
            "final-project-name",
        )
        self.assertEqual(
            capsule["identifiers"]["source_repository"],
            "https://github.com/jaden3824/urusilla",
        )
        self.assertEqual(capsule["publisher_authentication"]["status"], "unsigned")
        self.assertEqual(capsule["publisher_authentication"]["signatures"], [])
        signature_policy = capsule["publisher_authentication"]["signature_profile"]
        safe_use = capsule["publisher_authentication"]["safe_use"]
        self.assertIn("Unsigned public research distribution is permitted", signature_policy)
        self.assertIn(
            "required before effect-authorizing or production use",
            signature_policy,
        )
        self.assertIn("public source review and distribution", safe_use)
        self.assertIn("never external side effects", safe_use)
        publication_modes = capsule["github_distribution"]["publication_modes"]
        self.assertIn("unsigned_research", publication_modes)
        self.assertIn("trusted_effect_authorizing", publication_modes)
        self.assertIn(
            "Public source review and versioned research assets are permitted",
            publication_modes["unsigned_research"],
        )
        self.assertIn(
            "effect-authorizing behavior disabled",
            publication_modes["unsigned_research"],
        )
        self.assertIn(
            "requires an accepted publisher signature",
            publication_modes["trusted_effect_authorizing"],
        )
        unsigned_restriction = capsule["security_contract"]["unsigned_restriction"]
        self.assertIn("distributed publicly for source review", unsigned_restriction)
        self.assertIn("local read-only research", unsigned_restriction)
        self.assertIn("MUST NOT authorize external side effects", unsigned_restriction)

        manifest_bytes = json.dumps(
            capsule["semantic_kernel"]["manifest"],
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            capsule["semantic_kernel"]["manifest_digest"],
            "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        )

        vector = capsule["conformance"]["positive_vectors"][0]
        frame = base64.b64decode(vector["wire_base64"], validate=True)
        self.assertEqual(frame[:5], reference.MAGIC)
        self.assertEqual(len(frame), vector["wire_bytes"])
        self.assertEqual(hashlib.sha256(frame).hexdigest(), vector["wire_sha256"])
        self.assertEqual(decode_message(frame), normalize_message(vector["input"]))
        self.assertEqual(encode_message(decode_message(frame)), frame)

        for artifact in ("reference_codec", "reference_spec"):
            record = capsule["implementation_artifacts"][artifact]
            observed = hashlib.sha256((root / record["local_filename"]).read_bytes()).hexdigest()
            self.assertEqual(record["sha256"], observed)

    def test_map_insertion_order_does_not_change_wire_bytes(self) -> None:
        first = demo_message()
        second = copy.deepcopy(first)
        body = second["body"]
        second["body"] = {
            "constraints": body["constraints"],
            "condition": body["condition"],
            "kind": body["kind"],
        }
        second["meta"] = {
            "provenance": second["meta"]["provenance"],
            "budget": second["meta"]["budget"],
        }
        self.assertEqual(encode_message(first), encode_message(second))

    def test_recipient_limit_is_rejected_before_encoding(self) -> None:
        message = demo_message()
        message["recipients"] = [
            f"recipient-{index}" for index in range(MAX_COLLECTION_ITEMS + 1)
        ]
        with self.assertRaisesRegex(ValidationError, "collection-item limit"):
            normalize_message(message)
        with self.assertRaisesRegex(ValidationError, "collection-item limit"):
            encode_message(message)

    def test_aggregate_semantic_node_limit_is_shared_by_body_and_meta(self) -> None:
        # Three inner lists produce seven non-payload nodes: body map, kind,
        # outer list, three inner lists, and the meta map.
        exact = self._aggregate_message(MAX_SEMANTIC_NODES - 7)
        self.assertEqual(
            normalize_message(exact)["body"]["kind"], "x:aggregate-probe"
        )
        exact_frame = encode_message(exact)
        self.assertEqual(
            decode_message(exact_frame)["body"]["kind"], "x:aggregate-probe"
        )

        over = self._aggregate_message(MAX_SEMANTIC_NODES - 6)
        with self.assertRaisesRegex(ValidationError, "aggregate node limit"):
            normalize_message(over)
        with self.assertRaisesRegex(ValidationError, "aggregate node limit"):
            encode_message(over)

    def test_decoder_rejects_nested_collections_above_aggregate_budget(self) -> None:
        frame = self._aggregate_frame(MAX_SEMANTIC_NODES - 6)
        with self.assertRaisesRegex(DecodeError, "aggregate node limit"):
            decode_message(frame)

    def test_single_bit_mutation_fails_integrity_check(self) -> None:
        frame = bytearray(encode_message(demo_message()))
        frame[len(frame) // 2] ^= 0x01
        with self.assertRaises(DecodeError):
            decode_message(bytes(frame))

    def test_trailing_bytes_are_rejected(self) -> None:
        frame = encode_message(demo_message()) + b"\x00"
        with self.assertRaises(DecodeError):
            decode_message(frame)

    def test_commit_requires_causal_reference(self) -> None:
        message = demo_message()
        message["act"] = "COMMIT"
        with self.assertRaises(ValidationError):
            encode_message(message)

    def test_unregistered_bare_node_kind_is_rejected(self) -> None:
        message = demo_message()
        message["body"] = {"kind": "private-secret-code", "value": 7}
        with self.assertRaises(ValidationError):
            encode_message(message)

    def test_namespaced_extension_kind_is_preserved_only_as_assertion(self) -> None:
        message = demo_message()
        message["act"] = "ASSERT"
        message["body"] = {"kind": "x:demo", "value": 7}
        decoded = decode_message(encode_message(message))
        self.assertEqual(decoded["body"], {"kind": "x:demo", "value": 7})

    def test_unknown_top_level_shadow_field_is_rejected(self) -> None:
        message = demo_message()
        message["critical_authority"] = "admin"
        with self.assertRaisesRegex(ValidationError, "unknown top-level"):
            normalize_message(message)

    def test_tuple_is_rejected_as_noncanonical(self) -> None:
        message = demo_message()
        message["meta"]["tuple"] = (1, 2)
        with self.assertRaisesRegex(ValidationError, "tuples are not canonical"):
            normalize_message(message)

    def test_top_level_sequences_must_use_canonical_lists(self) -> None:
        for field in ("recipients", "expected"):
            message = demo_message()
            message[field] = tuple(message.get(field, []))
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    normalize_message(message)

    def test_malformed_ingress_uses_project_domain_errors(self) -> None:
        non_string_key = demo_message()
        non_string_key[1] = "unexpected"
        lone_surrogate = demo_message()
        lone_surrogate["sender"] = "\ud800"
        invalid_mode = demo_message()
        invalid_mode["body"]["constraints"][0]["mode"] = []

        for message in (non_string_key, lone_surrogate, invalid_mode):
            with self.subTest(message=message):
                with self.assertRaises(reference.UrusillaError):
                    normalize_message(message)

        with patch.object(Path, "open", return_value=io.StringIO("{")):
            with self.assertRaisesRegex(ValidationError, "invalid JSON"):
                reference._load_json(Path("unused.json"))

    def test_json_loader_rejects_duplicate_members_at_any_depth(self) -> None:
        duplicate = '{"outer":{"field":1,"field":2}}'
        with patch.object(Path, "open", return_value=io.StringIO(duplicate)):
            with self.assertRaisesRegex(ValidationError, "duplicate JSON member"):
                reference._load_json(Path("unused.json"))

    def test_extension_quarantine_is_recursive(self) -> None:
        message = demo_message()
        message["body"]["condition"] = {"kind": "x:nested", "value": 1}
        with self.assertRaisesRegex(ValidationError, "quarantined to ASSERT"):
            normalize_message(message)

        message["act"] = "ASSERT"
        message["body"] = {
            "kind": "claim",
            "predicate": "p",
            "arguments": [{"kind": "x:nested", "value": 1}],
        }
        self.assertEqual(
            normalize_message(message)["body"]["arguments"][0]["kind"],
            "x:nested",
        )

    def test_query_grammar_matches_the_capsule(self) -> None:
        message = demo_message()
        message["act"] = "QUERY"
        message["body"] = {
            "kind": "question-plus-answer-schema",
            "question": {"kind": "claim", "predicate": "p"},
            "answer_schema": "urn:test:answer",
        }
        canonical = normalize_message(message)
        self.assertEqual(canonical["body"]["kind"], "question-plus-answer-schema")
        self.assertEqual(decode_message(encode_message(message)), canonical)

        message["body"].pop("kind")
        with self.assertRaisesRegex(ValidationError, "must declare kind"):
            normalize_message(message)

    def test_commitment_fields_and_debtor_are_typed_and_bound(self) -> None:
        message = demo_message()
        message["act"] = "COMMIT"
        message["reply_to"] = "20000000-0000-0000-0000-000000000001"
        message["body"] = {
            "kind": "commitment",
            "debtor": "another.agent",
            "creditors": "verifier.agent",
            "goal": None,
            "expiry_ms": "never",
        }
        with self.assertRaises(ValidationError):
            normalize_message(message)

        message["body"] = {
            "kind": "commitment",
            "debtor": "another.agent",
            "creditors": ["verifier.agent"],
            "goal": demo_message()["body"],
            "expiry_ms": 1_500,
        }
        with self.assertRaisesRegex(ValidationError, "debtor"):
            normalize_message(message)

    def test_act_body_schema_and_uri_looking_extension_fail_closed(self) -> None:
        message = demo_message()
        message["act"] = "COMMIT"
        message["reply_to"] = "20000000-0000-0000-0000-000000000001"
        with self.assertRaisesRegex(ValidationError, "COMMIT cannot carry"):
            normalize_message(message)

        message = demo_message()
        message["schema"] = "not-a-uri"
        with self.assertRaisesRegex(ValidationError, "absolute URI"):
            normalize_message(message)

        message = demo_message()
        message["act"] = "ASSERT"
        message["body"] = {"kind": "https://attacker.example/node", "value": 1}
        with self.assertRaisesRegex(ValidationError, "x:<name>"):
            normalize_message(message)

    def test_effect_eligibility_requires_external_policy(self) -> None:
        message = demo_message()
        message["act"] = "PROPOSE"
        message["body"] = {
            "kind": "action",
            "capability": "deploy.code",
            "arguments": {},
            "declared_effects": ["deployment.write"],
        }
        with self.assertRaisesRegex(ValidationError, "unauthorized declared effect"):
            validate_effect_eligibility(
                message,
                authenticated_sender=message["sender"],
                authorized_schemas=[message["schema"]],
            )
        validated = validate_effect_eligibility(
            message,
            authenticated_sender=message["sender"],
            authorized_schemas=[message["schema"]],
            allowed_effects=["deployment.write"],
        )
        self.assertEqual(validated["body"]["capability"], "deploy.code")

    def test_effectful_act_requires_conversation_state_check(self) -> None:
        message = demo_message()
        message["act"] = "COMMIT"
        message["reply_to"] = "20000000-0000-0000-0000-000000000001"
        message["body"] = {
            "kind": "commitment",
            "debtor": message["sender"],
            "creditors": message["recipients"],
            "goal": demo_message()["body"],
            "expiry_ms": 1_500,
        }
        with self.assertRaisesRegex(ValidationError, "conversation-state"):
            validate_effect_eligibility(
                message,
                authenticated_sender=message["sender"],
                authorized_schemas=[message["schema"]],
            )
        self.assertEqual(
            validate_effect_eligibility(
                message,
                authenticated_sender=message["sender"],
                authorized_schemas=[message["schema"]],
                conversation_check=lambda candidate: candidate["reply_to"] is not None,
            )["act"],
            "COMMIT",
        )

    def test_literal_translations_reference_same_message(self) -> None:
        message = decode_message(encode_message(demo_message()))
        korean = translate_message(message, "ko")
        english = translate_message(message, "en")
        self.assertIn("[REQUEST]", korean)
        self.assertIn("[REQUEST]", english)
        self.assertIn(message["id"], korean)
        self.assertIn(message["id"], english)

    def test_audit_lens_changes_for_priority_meta_and_expiry(self) -> None:
        base = demo_message()
        baseline = translate_message(base, "en")
        for mutation in (
            lambda message: message["body"].__setitem__("priority", 999),
            lambda message: message["meta"].__setitem__("authorization", "denied"),
            lambda message: message.__setitem__("expires_ms", 999_999),
        ):
            changed = copy.deepcopy(base)
            mutation(changed)
            rendered = translate_message(changed, "en")
            self.assertNotEqual(rendered, baseline)
            self.assertIn("Complete canonical IR:", rendered)


if __name__ == "__main__":
    unittest.main()
