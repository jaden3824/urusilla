from __future__ import annotations

from collections.abc import Mapping
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
from urusilla_schema_reply_evaluation import (
    ReplyEvidenceError,
    evaluate_required_schema_reply,
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


def run_schema_reply_evidence_vector(case_id: str) -> dict[str, object]:
    vectors = load_json("schema_reply_evidence_vectors.json")
    descriptors = {
        descriptor["resource_id"]: descriptor
        for descriptor in vectors["resources"]
    }
    case = next(item for item in vectors["cases"] if item["case_id"] == case_id)
    resources = {}
    for resource_id in case["available_resource_ids"]:
        descriptor = descriptors[resource_id]
        resources[descriptor["uri"]] = SchemaResource(
            uri=descriptor["uri"],
            media_type=descriptor["media_type"],
            content=(EVIDENCE / descriptor["path"]).read_bytes(),
        )
    inline_resource = None
    inline_resource_id = case["inline_fallback_resource_id"]
    if inline_resource_id is not None:
        descriptor = descriptors[inline_resource_id]
        inline_resource = SchemaResource(
            uri=descriptor["uri"],
            media_type=descriptor["media_type"],
            content=(EVIDENCE / descriptor["path"]).read_bytes(),
        )
    return evaluate_required_schema_reply(
        load_json(case["query_path"]),
        case["binding"],
        resources,
        case["reply"],
        inline_fallback_resource=inline_resource,
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

    def test_reply_evidence_vectors_separate_shape_from_contract_binding(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        result_fields = {
            "classification",
            "effect_authorized",
            "fallback_artifact_valid",
            "format",
            "inline_fallback_contract_verified",
            "inline_required_fields",
            "invalid_fields",
            "missing_fields",
            "must_fail",
            "publisher_authenticated",
            "reason_code",
            "reply_evidence_signal_valid",
            "resolution_reason_code",
            "schema_binding_verified",
            "schema_payload_valid",
            "schema_required_fields",
            "schema_uri",
            "schema_urn",
            "strict_conformance",
            "unexpected_fields",
            "validated_against",
        }
        self.assertTrue(vectors["offline_only"])
        self.assertFalse(vectors["external_effects_authorized"])
        for case in vectors["cases"]:
            with self.subTest(case_id=case["case_id"]):
                evaluation = run_schema_reply_evidence_vector(case["case_id"])
                self.assertEqual(set(evaluation), result_fields)
                for field, expected in case["expected"].items():
                    self.assertEqual(evaluation[field], expected)
                self.assertFalse(evaluation["strict_conformance"])
                self.assertFalse(evaluation["effect_authorized"])

    def test_reply_evidence_resources_and_queries_are_content_bound(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        descriptors = {
            descriptor["resource_id"]: descriptor
            for descriptor in vectors["resources"]
        }
        for descriptor in descriptors.values():
            with self.subTest(resource_id=descriptor["resource_id"]):
                content = (EVIDENCE / descriptor["path"]).read_bytes()
                self.assertEqual(len(content), descriptor["bytes"])
                self.assertEqual(
                    "sha256:" + hashlib.sha256(content).hexdigest(),
                    descriptor["sha256"],
                )
                self.assertEqual(
                    json.loads(content.decode("utf-8"))["$id"], descriptor["uri"]
                )

        for query_path in sorted({case["query_path"] for case in vectors["cases"]}):
            with self.subTest(query_path=query_path):
                query = load_json(query_path)
                canonical = normalize_message(query)
                frame = encode_message(query)
                self.assertEqual(decode_message(frame), canonical)
                self.assertEqual(encode_message(canonical), frame)

        inline = descriptors["inline-fallback-contract"]
        inline_binding = load_json(
            "schema_reply_evidence_query.unresolved-inline.json"
        )["meta"]["inline_fallback_contract"]
        self.assertEqual(
            inline_binding,
            {
                field: inline[field]
                for field in ("uri", "sha256", "bytes", "media_type")
            },
        )

    def test_nine_field_schema_exposes_the_two_field_provenance_gap(self) -> None:
        full = run_schema_reply_evidence_vector("resolved-nine-reply-nine")
        partial = run_schema_reply_evidence_vector("resolved-nine-reply-seven")
        inline_fields = set(full["inline_required_fields"])
        schema_fields = set(full["schema_required_fields"])

        self.assertEqual(len(inline_fields), 7)
        self.assertEqual(len(schema_fields), 9)
        self.assertEqual(
            schema_fields - inline_fields,
            {"schema_urn", "validated_against"},
        )
        self.assertTrue(full["reply_evidence_signal_valid"])
        self.assertFalse(partial["reply_evidence_signal_valid"])
        self.assertEqual(
            partial["missing_fields"], ["schema_urn", "validated_against"]
        )

    def test_unresolved_no_inline_is_must_fail_even_for_shaped_reply(self) -> None:
        evaluation = run_schema_reply_evidence_vector(
            "unresolved-no-inline-shaped-reply"
        )
        self.assertEqual(evaluation["validated_against"], "resolved-schema")
        self.assertEqual(evaluation["classification"], "must-fail")
        self.assertTrue(evaluation["must_fail"])
        self.assertFalse(evaluation["reply_evidence_signal_valid"])
        self.assertFalse(evaluation["schema_payload_valid"])

    def test_unresolved_cells_hold_schema_identity_constant(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        resolved = next(
            case
            for case in vectors["cases"]
            if case["case_id"] == "resolved-nine-reply-nine"
        )
        for case_id in (
            "unresolved-bound-inline-diagnostic",
            "unresolved-no-inline-shaped-reply",
        ):
            with self.subTest(case_id=case_id):
                case = next(
                    item for item in vectors["cases"] if item["case_id"] == case_id
                )
                self.assertEqual(case["binding"], resolved["binding"])
                self.assertEqual(
                    load_json(case["query_path"])["body"]["answer_schema"],
                    load_json(resolved["query_path"])["body"]["answer_schema"],
                )
                evaluation = run_schema_reply_evidence_vector(case_id)
                self.assertEqual(
                    evaluation["resolution_reason_code"], "required-schema-missing"
                )

    def test_inline_fallback_contract_must_match_its_content_binding(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        descriptors = {
            descriptor["resource_id"]: descriptor
            for descriptor in vectors["resources"]
        }
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "unresolved-bound-inline-diagnostic"
        )
        descriptor = descriptors[case["inline_fallback_resource_id"]]
        tampered = SchemaResource(
            uri=descriptor["uri"],
            media_type=descriptor["media_type"],
            content=(EVIDENCE / descriptor["path"]).read_bytes() + b"\n",
        )
        evaluation = evaluate_required_schema_reply(
            load_json(case["query_path"]),
            case["binding"],
            {},
            case["reply"],
            inline_fallback_resource=tampered,
        )
        self.assertEqual(evaluation["classification"], "must-fail")
        self.assertFalse(evaluation["inline_fallback_contract_verified"])
        self.assertFalse(evaluation["reply_evidence_signal_valid"])

    def test_unpinned_self_bound_inline_contract_cannot_verify(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "unresolved-bound-inline-diagnostic"
        )
        query = load_json(case["query_path"])
        contract = load_json("peer_dialogue_reply_inline_fallback.schema.json")
        attacker_uri = "urn:example:untrusted-inline-contract:0.1"
        contract["$id"] = attacker_uri
        content = json.dumps(
            contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        query["meta"]["inline_fallback_contract"] = {
            "uri": attacker_uri,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "media_type": "application/schema+json",
        }
        evaluation = evaluate_required_schema_reply(
            query,
            case["binding"],
            {},
            case["reply"],
            inline_fallback_resource=SchemaResource(
                uri=attacker_uri,
                media_type="application/schema+json",
                content=content,
            ),
        )
        self.assertEqual(evaluation["classification"], "must-fail")
        self.assertFalse(evaluation["inline_fallback_contract_verified"])
        self.assertFalse(evaluation["publisher_authenticated"])

    def test_schema_conflict_cannot_resume_through_inline_fallback(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        resolved = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "resolved-nine-reply-nine"
        )
        query = load_json(resolved["query_path"])
        query["body"]["constraints"][0]["condition"]["required_fields"].append(
            "confidence"
        )
        inline_query = load_json(
            "schema_reply_evidence_query.unresolved-inline.json"
        )
        query["meta"]["inline_fallback_contract"] = inline_query["meta"][
            "inline_fallback_contract"
        ]
        schema_descriptor, inline_descriptor = vectors["resources"]
        schema_uri = schema_descriptor["uri"]
        reply = dict(resolved["reply"])
        reply["validated_against"] = "inline-fallback"
        evaluation = evaluate_required_schema_reply(
            query,
            resolved["binding"],
            {
                schema_uri: SchemaResource(
                    uri=schema_uri,
                    media_type=schema_descriptor["media_type"],
                    content=(EVIDENCE / schema_descriptor["path"]).read_bytes(),
                )
            },
            reply,
            inline_fallback_resource=SchemaResource(
                uri=inline_descriptor["uri"],
                media_type=inline_descriptor["media_type"],
                content=(EVIDENCE / inline_descriptor["path"]).read_bytes(),
            ),
        )
        self.assertEqual(
            evaluation["resolution_reason_code"],
            "required-schema-inline-constraint-conflict",
        )
        self.assertEqual(evaluation["classification"], "must-fail")
        self.assertEqual(
            evaluation["reason_code"],
            "schema-resolution-failure-not-fallback-eligible",
        )
        self.assertFalse(evaluation["fallback_artifact_valid"])
        self.assertFalse(evaluation["reply_evidence_signal_valid"])

    def test_schema_resource_is_snapshotted_before_resolution(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "resolved-nine-reply-nine"
        )
        descriptor = vectors["resources"][0]
        schema_uri = descriptor["uri"]
        good = SchemaResource(
            uri=schema_uri,
            media_type=descriptor["media_type"],
            content=(EVIDENCE / descriptor["path"]).read_bytes(),
        )
        altered_schema = json.loads(good.content.decode("utf-8"))
        altered_schema["title"] = "post-resolution replacement"
        changed = SchemaResource(
            uri=schema_uri,
            media_type=descriptor["media_type"],
            content=json.dumps(altered_schema).encode("utf-8"),
        )

        class FlippingResources(Mapping):
            def __init__(self) -> None:
                self.lookups = 0

            def __iter__(self):
                return iter((schema_uri,))

            def __len__(self) -> int:
                return 1

            def __getitem__(self, key):
                if key != schema_uri:
                    raise KeyError(key)
                self.lookups += 1
                return good if self.lookups == 1 else changed

        resources = FlippingResources()
        evaluation = evaluate_required_schema_reply(
            load_json(case["query_path"]),
            case["binding"],
            resources,
            case["reply"],
        )
        self.assertEqual(resources.lookups, 1)
        self.assertTrue(evaluation["schema_payload_valid"])

    def test_reply_is_snapshotted_before_validation_and_result_export(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "resolved-nine-reply-nine"
        )
        descriptor = vectors["resources"][0]
        schema_uri = descriptor["uri"]
        resources = {
            schema_uri: SchemaResource(
                uri=schema_uri,
                media_type=descriptor["media_type"],
                content=(EVIDENCE / descriptor["path"]).read_bytes(),
            )
        }

        class FlippingReply(Mapping):
            def __init__(self) -> None:
                self.lookups: dict[str, int] = {}

            def __iter__(self):
                return iter(case["reply"])

            def __len__(self) -> int:
                return len(case["reply"])

            def __getitem__(self, key):
                lookups = self.lookups.get(key, 0)
                self.lookups[key] = lookups + 1
                if key == "schema_urn" and lookups >= 1:
                    return "urn:attacker:changed"
                if key == "validated_against" and lookups >= 1:
                    return "inline-fallback"
                return case["reply"][key]

        reply = FlippingReply()
        evaluation = evaluate_required_schema_reply(
            load_json(case["query_path"]),
            case["binding"],
            resources,
            reply,
        )
        self.assertEqual(reply.lookups["schema_urn"], 1)
        self.assertEqual(reply.lookups["validated_against"], 1)
        self.assertEqual(evaluation["classification"], "resolved-schema-payload")
        self.assertTrue(evaluation["reply_evidence_signal_valid"])
        self.assertEqual(evaluation["schema_urn"], schema_uri)
        self.assertEqual(evaluation["validated_against"], "resolved-schema")

    def test_underdetermined_is_only_the_exact_valid_f7_gap(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "resolved-nine-reply-nine"
        )
        descriptor = vectors["resources"][0]
        schema_uri = descriptor["uri"]
        resources = {
            schema_uri: SchemaResource(
                uri=schema_uri,
                media_type=descriptor["media_type"],
                content=(EVIDENCE / descriptor["path"]).read_bytes(),
            )
        }
        query = load_json(case["query_path"])
        empty = evaluate_required_schema_reply(
            query, case["binding"], resources, {}
        )
        self.assertEqual(empty["classification"], "rejected")
        self.assertFalse(empty["reply_evidence_signal_valid"])

        one_missing = dict(case["reply"])
        one_missing.pop("schema_urn")
        partial = evaluate_required_schema_reply(
            query, case["binding"], resources, one_missing
        )
        self.assertEqual(partial["classification"], "rejected")
        self.assertEqual(partial["missing_fields"], ["schema_urn"])

        malformed = evaluate_required_schema_reply(
            query, case["binding"], resources, None
        )
        self.assertEqual(malformed["classification"], "rejected")
        self.assertEqual(malformed["reason_code"], "reply-artifact-not-object")
        self.assertFalse(malformed["schema_payload_valid"])

        for field, wrong_value in (
            ("schema_urn", "urn:example:wrong-schema"),
            ("validated_against", "inline-fallback"),
        ):
            with self.subTest(invalid_diagnostic=field):
                wrong = dict(case["reply"])
                wrong[field] = wrong_value
                rejected = evaluate_required_schema_reply(
                    query, case["binding"], resources, wrong
                )
                self.assertEqual(rejected["classification"], "rejected")
                self.assertIn(field, rejected["invalid_fields"])
                self.assertFalse(rejected["reply_evidence_signal_valid"])

    def test_reply_evidence_rejects_non_text_field_names(self) -> None:
        vectors = load_json("schema_reply_evidence_vectors.json")
        case = next(
            item
            for item in vectors["cases"]
            if item["case_id"] == "resolved-nine-reply-nine"
        )
        descriptor = vectors["resources"][0]
        schema_uri = descriptor["uri"]
        resources = {
            schema_uri: SchemaResource(
                uri=schema_uri,
                media_type=descriptor["media_type"],
                content=(EVIDENCE / descriptor["path"]).read_bytes(),
            )
        }
        malformed = dict(case["reply"])
        malformed[1] = "not-a-json-object-key"
        with self.assertRaises(ReplyEvidenceError):
            evaluate_required_schema_reply(
                load_json(case["query_path"]),
                case["binding"],
                resources,
                malformed,
            )

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
