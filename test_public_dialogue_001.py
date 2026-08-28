from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from urusilla import ValidationError, decode_message, encode_message, normalize_message
from urusilla_schema_resolution import (
    SchemaResource,
    resolve_required_answer_schema,
)


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "public_dialogue_001"
CAPSULE_SHA256 = "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
MISSING_ANSWER_SCHEMA = "urn:urusilla:schema:peer-dialogue-reply:0.1"
MISSING_DIALOGUE_SCHEMA = "urn:urusilla:dialogue:0.1"


def load_json(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def run_schema_resolution_vector(case_id: str) -> dict[str, object]:
    vectors = load_json("schema_resolution_vectors.json")
    descriptors = {
        descriptor["resource_id"]: descriptor
        for descriptor in vectors["resources"]
    }
    case = next(item for item in vectors["cases"] if item["case_id"] == case_id)
    query = load_json(str(case.get("query_path", vectors["query_path"])))
    resources = {}
    for resource_id in case["available_resource_ids"]:
        descriptor = descriptors[resource_id]
        resources[descriptor["uri"]] = SchemaResource(
            uri=descriptor["uri"],
            media_type=descriptor["media_type"],
            content=(EVIDENCE / descriptor["path"]).read_bytes(),
        )
    return resolve_required_answer_schema(
        query,
        case["binding"],
        resources,
        fallback_route=case["fallback_route"],
    )


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

    def test_schema_resolution_positive_fixture_matches_complete_binding(self) -> None:
        vectors = load_json("schema_resolution_vectors.json")
        query = load_json(str(vectors["query_path"]))
        descriptor = vectors["resources"][0]
        schema_bytes = (EVIDENCE / descriptor["path"]).read_bytes()
        schema = json.loads(schema_bytes.decode("utf-8"))
        capsule = json.loads(
            (ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8")
        )

        self.assertTrue(vectors["offline_only"])
        self.assertFalse(vectors["external_effects_authorized"])
        self.assertEqual(query["schema"], capsule["identifiers"]["core_schema_id"])
        self.assertEqual(query["body"]["answer_schema"], MISSING_ANSWER_SCHEMA)
        self.assertFalse(query["meta"]["external_effects"])
        self.assertEqual(descriptor["uri"], MISSING_ANSWER_SCHEMA)
        self.assertEqual(schema["$id"], descriptor["uri"])
        self.assertEqual(descriptor["media_type"], "application/schema+json")
        self.assertEqual(len(schema_bytes), descriptor["bytes"])
        self.assertEqual(
            "sha256:" + hashlib.sha256(schema_bytes).hexdigest(),
            descriptor["sha256"],
        )

        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "resolved-exact-binding"
        )
        decision = run_schema_resolution_vector(case["case_id"])
        self.assertEqual(decision, case["expected"])
        self.assertTrue(decision["schema_binding_verified"])
        self.assertFalse(decision["strict_conformance"])
        self.assertEqual(decision["route"], "urusilla")
        self.assertFalse(decision["effect_authorized"])

    def test_schema_resolution_failure_vectors_close_to_fallback(self) -> None:
        vectors = load_json("schema_resolution_vectors.json")
        for case_id, route, media_type in (
            ("required-schema-missing", "json", "application/json"),
            ("required-schema-sha256-mismatch", "text", "text/plain"),
        ):
            with self.subTest(case_id=case_id):
                case = next(
                    item for item in vectors["cases"] if item["case_id"] == case_id
                )
                decision = run_schema_resolution_vector(case_id)
                self.assertEqual(decision, case["expected"])
                self.assertFalse(decision["strict_conformance"])
                self.assertFalse(decision["schema_binding_verified"])
                self.assertEqual(decision["route"], route)
                self.assertEqual(decision["fallback"]["media_type"], media_type)
                self.assertFalse(decision["effect_authorized"])

    def test_resolved_schema_closes_on_forbidden_inline_required_field(self) -> None:
        base_query = load_json("schema_resolution_query.json")
        conflict_query = load_json("schema_resolution_query.inline-conflict.json")
        expected_mutation = deepcopy(base_query)
        expected_mutation["body"]["constraints"][0]["condition"][
            "required_fields"
        ].append("confidence")
        self.assertEqual(conflict_query, expected_mutation)

        canonical = normalize_message(conflict_query)
        frame = encode_message(conflict_query)
        self.assertEqual(decode_message(frame), canonical)

        vectors = load_json("schema_resolution_vectors.json")
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "required-schema-inline-constraint-conflict"
        )
        decision = run_schema_resolution_vector(case["case_id"])
        self.assertEqual(decision, case["expected"])
        self.assertTrue(decision["schema_binding_verified"])
        self.assertFalse(decision["strict_conformance"])
        self.assertEqual(decision["route"], "json")
        self.assertFalse(decision["effect_authorized"])

    def test_self_consistent_unpinned_schema_cannot_open_typed_route(self) -> None:
        vectors = load_json("schema_resolution_vectors.json")
        query = load_json(str(vectors["query_path"]))
        schema_uri = query["body"]["answer_schema"]
        content = json.dumps(
            {"$id": schema_uri}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        binding = {
            "uri": schema_uri,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "media_type": "application/schema+json",
        }
        decision = resolve_required_answer_schema(
            query,
            binding,
            {
                schema_uri: SchemaResource(
                    uri=schema_uri,
                    media_type="application/schema+json",
                    content=content,
                )
            },
        )
        self.assertEqual(decision["reason_code"], "required-schema-binding-not-pinned")
        self.assertEqual(decision["route"], "json")
        self.assertFalse(decision["schema_binding_verified"])
        self.assertFalse(decision["strict_conformance"])

    def test_schema_resolution_rejects_each_non_digest_identity_mismatch(self) -> None:
        vectors = load_json("schema_resolution_vectors.json")
        query = load_json(str(vectors["query_path"]))
        descriptor = vectors["resources"][0]
        content = (EVIDENCE / descriptor["path"]).read_bytes()
        exact_binding = {
            field: descriptor[field]
            for field in ("uri", "sha256", "bytes", "media_type")
        }
        exact_resource = SchemaResource(
            uri=descriptor["uri"],
            media_type=descriptor["media_type"],
            content=content,
        )
        cases = []

        uri_binding = dict(exact_binding)
        uri_binding["uri"] = "urn:urusilla:schema:other:0.1"
        cases.append(
            (
                "uri",
                uri_binding,
                {descriptor["uri"]: exact_resource},
                "required-schema-uri-mismatch",
            )
        )

        byte_binding = dict(exact_binding)
        byte_binding["bytes"] += 1
        cases.append(
            (
                "bytes",
                byte_binding,
                {descriptor["uri"]: exact_resource},
                "required-schema-binding-not-pinned",
            )
        )

        media_resource = SchemaResource(
            uri=descriptor["uri"],
            media_type="application/json",
            content=content,
        )
        cases.append(
            (
                "media-type",
                exact_binding,
                {descriptor["uri"]: media_resource},
                "required-schema-media-type-mismatch",
            )
        )

        for label, binding, resources, reason_code in cases:
            with self.subTest(label=label):
                decision = resolve_required_answer_schema(
                    query, binding, resources, fallback_route="json"
                )
                self.assertFalse(decision["strict_conformance"])
                self.assertFalse(decision["schema_binding_verified"])
                self.assertEqual(decision["reason_code"], reason_code)
                self.assertEqual(decision["route"], "json")
                self.assertFalse(decision["effect_authorized"])

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
