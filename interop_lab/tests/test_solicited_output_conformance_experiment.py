"""Offline tests for the answer-blind Colony output-conformance study."""

from __future__ import annotations

from copy import deepcopy
import json
import re
import unittest

from interop_lab.interop_lab import ValidationError
from interop_lab.solicited_output_conformance_experiment import (
    CAPSULE_CANONICAL_SHA256,
    CASE_IDS,
    DEADLINE_UTC,
    EXPERIMENT_ID,
    OFFER_AUTHOR_ID,
    OFFER_COMMENT_ID,
    ORACLE_COMMITMENT_SHA256,
    PACKET_CANONICAL_SHA256,
    PACKET_PATH,
    PREREG_CANONICAL_SHA256,
    PREREG_PATH,
    REPO_ROOT,
    THREAD_POST_ID,
    V1_FROZEN_FILES,
    canonical_json_text,
    canonical_sha256,
    classify_response_events,
    inspect_public_response_text,
    load_json,
    render_outreach_manifest,
    score_public_response,
    sha256_ref,
    validate_outreach_manifest,
    validate_public_artifacts,
    validate_publication_receipt,
    validate_public_response_text,
    verify_commitment_preimage,
)


def _non_gold_results() -> list[dict[str, object]]:
    """Schema-valid records deliberately wrong for every registered case."""

    return [
        {
            "case_id": case_id,
            "disposition": "failed",
            "route": None,
            "output": None,
            "note": "test-fixture-not-gold",
        }
        for case_id in CASE_IDS
    ]


def _response(results: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "capsule_canonical_sha256": CAPSULE_CANONICAL_SHA256,
        "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "response_kind": "output-conformance-result",
        "response_note": None,
        "results": _non_gold_results() if results is None else results,
    }


def _manifest_and_receipt() -> tuple[dict[str, object], dict[str, object]]:
    manifest = render_outreach_manifest("1" * 40)
    body = manifest["body_text"]
    receipt = {
        "schema_version": "urusilla-solicited-output-conformance-publication-receipt/2",
        "experiment_id": EXPERIMENT_ID,
        "registration_commit": "1" * 40,
        "outreach_commit": "2" * 40,
        "observed_at_utc": "2026-08-23T14:05:00Z",
        "outreach_manifest_canonical_sha256": canonical_sha256(manifest),
        "invitation": {
            "id": "invitation-002",
            "post_id": THREAD_POST_ID,
            "parent_id": OFFER_COMMENT_ID,
            "author": {
                "id": "5ca1345d-5c38-400e-9fec-e1b12386d7bf",
                "username": "skdhbegjk",
                "user_type": "human",
            },
            "created_at_utc": "2026-08-23T14:00:00Z",
            "updated_at_utc": "2026-08-23T14:00:00Z",
            "body_text": body,
            "body_utf8_bytes": len(body.encode("utf-8")),
            "body_sha256": sha256_ref(body),
            "readback_body_text": body,
            "readback_body_sha256": sha256_ref(body),
            "source": "web",
            "client": None,
        },
        "readback": {
            "official_api_uri": "https://thecolony.ai/api/v1/comments/invitation-002",
            "http_status": 200,
            "authenticated": False,
        },
    }
    return manifest, receipt


def _event(
    event_id: str,
    created_at: str,
    body: str,
    *,
    parent_id: str = "invitation-002",
    author_id: str = OFFER_AUTHOR_ID,
    post_id: str = THREAD_POST_ID,
) -> dict[str, object]:
    return {
        "id": event_id,
        "post_id": post_id,
        "parent_id": parent_id,
        "author_id": author_id,
        "created_at_utc": created_at,
        "body_text": body,
    }


def _stream_receipt(events: list[dict[str, object]], observed_at: str) -> dict[str, object]:
    item_ids = [event["id"] for event in events]
    return {
        "schema_version": "urusilla-colony-comment-stream-observation/1",
        "official_api_uri": (
            f"https://thecolony.ai/api/v1/posts/{THREAD_POST_ID}/comments"
            "?sort=oldest&limit=100&page=1"
        ),
        "observed_at_utc": observed_at,
        "http_status": 200,
        "authenticated": False,
        "page": 1,
        "total": len(events),
        "has_more": False,
        "item_ids": item_ids,
        "item_ids_canonical_sha256": canonical_sha256(item_ids),
    }


class SolicitedOutputConformanceExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prereg = load_json(PREREG_PATH)
        self.packet = load_json(PACKET_PATH)

    def test_public_artifacts_validate_and_preserve_null_claims(self) -> None:
        report = validate_public_artifacts()
        self.assertTrue(report["valid"])
        self.assertEqual(report["case_count"], 6)
        self.assertFalse(report["answer_oracle_public"])
        self.assertTrue(report["same_thread_prior_exposure_present"])
        self.assertFalse(report["cold_or_unfamiliar_claim_eligible"])
        self.assertEqual(report["general_unfamiliar_agent_saving_percent"], 0.0)
        self.assertIsNone(report["safely_completed_real_task_total_token_result"])

    def test_v1_files_remain_byte_frozen(self) -> None:
        for relative_path, expected in V1_FROZEN_FILES.items():
            with self.subTest(path=relative_path):
                self.assertEqual(sha256_ref((REPO_ROOT / relative_path).read_bytes()), expected)
        self.assertFalse(self.prereg["v1_parentage"]["v1_modified"])
        self.assertFalse(self.prereg["v1_parentage"]["v2_supersedes_v1"])
        self.assertTrue(self.prereg["v1_parentage"]["v1_stop_remains_effective"])

    def test_packet_has_six_new_cases_without_answer_or_salt_fields(self) -> None:
        cases = self.packet["cases"]
        self.assertEqual(tuple(case["case_id"] for case in cases), CASE_IDS)
        self.assertEqual(len({canonical_sha256(case["model_visible_input"]) for case in cases}), 6)
        serialized = canonical_json_text(self.packet)
        for forbidden in (
            '"expected_output"',
            '"expected_outputs"',
            '"expected_result"',
            '"expected_results"',
            '"gold_output"',
            '"salt_hex"',
            "solicited-matched-001",
            "model_visible_raw",
            "ordinary_json_arm",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_hosted_lane_excludes_accounting_and_cold_claims(self) -> None:
        procedure = self.packet["procedure"]
        self.assertFalse(procedure["fresh_context_required"])
        self.assertFalse(procedure["provider_receipts_required"])
        self.assertFalse(procedure["usage_receipts_required"])
        self.assertFalse(procedure["model_settings_digest_required"])
        self.assertFalse(procedure["natural_language_re_expansion_requested"])
        design = self.prereg["study_design"]
        self.assertEqual(design["contamination_status"], "same-thread-prior-exposure-present")
        self.assertFalse(design["cold_or_unfamiliar_claim_eligible"])
        self.assertFalse(design["internal_direct_consumption_measurable"])
        self.assertFalse(design["full_hosted_context_known"])

    def test_registered_inputs_have_only_declared_mutations(self) -> None:
        inputs = [case["model_visible_input"] for case in self.packet["cases"]]
        pair_a = [deepcopy(inputs[0]), deepcopy(inputs[1])]
        values = [item.pop("t") for item in pair_a]
        self.assertEqual(pair_a[0], pair_a[1])
        self.assertNotEqual(values[0], values[1])

        pair_b = [deepcopy(inputs[2]), deepcopy(inputs[3])]
        values = [item["p"][1].pop(2) for item in pair_b]
        self.assertEqual(pair_b[0], pair_b[1])
        self.assertEqual(values, [0, 1])

        pair_c = [deepcopy(inputs[4]), deepcopy(inputs[5])]
        values = [item["m"].pop("note") for item in pair_c]
        self.assertEqual(pair_c[0], pair_c[1])
        self.assertNotEqual(values[0], values[1])
        self.assertIn("execute", values[1])

    def test_real_reveal_is_absent_from_public_artifacts(self) -> None:
        self.assertEqual(self.prereg["oracle_commitment"]["commitment_sha256"], ORACLE_COMMITMENT_SHA256)
        self.assertFalse(
            (REPO_ROOT / "interop_lab/evidence/solicited_output_conformance_002.oracle.reveal.json").exists()
        )
        public_text = PREREG_PATH.read_text() + PACKET_PATH.read_text()
        self.assertIsNone(re.search(r'"salt_hex"\s*:\s*"[0-9a-f]{64}"', public_text))

    def test_generic_commitment_primitive_matches_and_rejects_without_real_cases(self) -> None:
        salt = "11" * 32
        dummy_results = [{"dummy_case": "not-a-registered-case", "value": "not-gold"}]
        commitment = canonical_sha256({"salt_hex": salt, "expected_results": dummy_results})
        report = verify_commitment_preimage(
            salt_hex=salt,
            expected_results=dummy_results,
            expected_commitment_sha256=commitment,
        )
        self.assertTrue(report["valid"])
        with self.assertRaisesRegex(ValidationError, "does not match"):
            verify_commitment_preimage(
                salt_hex="22" * 32,
                expected_results=dummy_results,
                expected_commitment_sha256=commitment,
            )

    def test_exact_canonical_non_gold_response_validates_from_raw_bytes(self) -> None:
        text = canonical_json_text(_response())
        report = validate_public_response_text(text)
        self.assertTrue(report["valid"])
        self.assertTrue(report["canonical_valid"])
        self.assertEqual(report["raw_utf8_bytes"], len(text.encode("utf-8")))
        self.assertEqual(report["raw_sha256"], sha256_ref(text))

    def test_staged_inspection_preserves_parse_schema_canonical_failures(self) -> None:
        parsed = inspect_public_response_text("not json")
        self.assertTrue(parsed["raw_body_captured"])
        self.assertFalse(parsed["parse_valid"])
        self.assertEqual(parsed["failed_stage"], "parse-valid")

        extra = _response()
        extra["extra"] = False
        schema = inspect_public_response_text(canonical_json_text(extra))
        self.assertTrue(schema["parse_valid"])
        self.assertFalse(schema["schema_valid"])
        self.assertEqual(schema["failed_stage"], "schema-valid")

        noncanonical = inspect_public_response_text(canonical_json_text(_response()) + "\n")
        self.assertTrue(noncanonical["schema_valid"])
        self.assertFalse(noncanonical["canonical_valid"])
        self.assertEqual(noncanonical["failed_stage"], "canonical-valid")

    def test_deeply_nested_malformed_json_is_retained_not_crashed(self) -> None:
        report = inspect_public_response_text("[" * 3000 + "]" * 3000)
        self.assertFalse(report["valid"])
        self.assertIn(report["failed_stage"], ("parse-valid", "schema-valid"))
        self.assertIsNotNone(report["error"])

    def test_wrapped_duplicate_extra_wrong_identity_and_order_are_rejected(self) -> None:
        canonical = canonical_json_text(_response())
        for wrapped in (" " + canonical, "```json\n" + canonical + "\n```", json.dumps(_response(), indent=2)):
            with self.assertRaises(ValidationError):
                validate_public_response_text(wrapped)
        duplicate = canonical.replace(
            '"experiment_id":"solicited-output-conformance-002"',
            '"experiment_id":"solicited-output-conformance-002","experiment_id":"other"',
            1,
        )
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            validate_public_response_text(duplicate)

        wrong_identity = _response()
        wrong_identity["packet_canonical_sha256"] = "sha256:" + "0" * 64
        wrong_order = _response()
        wrong_order["results"] = list(reversed(wrong_order["results"]))
        for mutation in (wrong_identity, wrong_order):
            with self.assertRaises(ValidationError):
                validate_public_response_text(canonical_json_text(mutation))

    def test_identity_mismatch_requires_and_accepts_observed_mismatch(self) -> None:
        response = _response()
        response.update(
            {
                "packet_canonical_sha256": "sha256:" + "0" * 64,
                "response_kind": "identity-mismatch",
                "response_note": "Observed packet identity differs.",
                "results": None,
            }
        )
        report = validate_public_response_text(canonical_json_text(response))
        self.assertFalse(report["identity_matches_registered"])

        response["packet_canonical_sha256"] = PACKET_CANONICAL_SHA256
        with self.assertRaisesRegex(ValidationError, "at least one observed mismatch"):
            validate_public_response_text(canonical_json_text(response))

    def test_result_cross_field_and_note_boundaries_are_enforced(self) -> None:
        for length, valid in ((256, True), (257, False)):
            response = _response()
            response["results"][0]["note"] = "x" * length
            text = canonical_json_text(response)
            if valid:
                validate_public_response_text(text)
            else:
                with self.assertRaisesRegex(ValidationError, "note invalid"):
                    validate_public_response_text(text)

        response = _response()
        response["results"][0].update(
            {
                "disposition": "completed",
                "route": "json-fallback",
                "output": None,
                "note": None,
            }
        )
        with self.assertRaises(ValidationError):
            validate_public_response_text(canonical_json_text(response))

    def test_missing_or_mismatched_reveal_keeps_semantic_scores_null(self) -> None:
        text = canonical_json_text(_response())
        missing = score_public_response(text, None)
        self.assertIsNone(missing["oracle_reveal_valid"])
        self.assertIsNone(missing["suite_exact_oracle_match"])
        self.assertIsNone(missing["oracle_semantic_correctness_verified"])
        self.assertIsNone(missing["final_capsule_conformance"])

        mismatch = score_public_response(text, {})
        self.assertFalse(mismatch["oracle_reveal_valid"])
        self.assertIsNotNone(mismatch["oracle_reveal_error"])
        self.assertIsNone(mismatch["case_exact_matches"])
        self.assertIsNone(mismatch["suite_exact_oracle_match"])

    def test_non_result_kinds_preserve_negative_and_null_evidence(self) -> None:
        for kind in ("refusal", "null", "methodological-counterexample"):
            with self.subTest(kind=kind):
                response = _response()
                response.update(
                    {
                        "response_kind": kind,
                        "response_note": "Public reason.",
                        "results": None,
                    }
                )
                report = validate_public_response_text(canonical_json_text(response))
                self.assertEqual(report["response_kind"], kind)

    def test_publication_receipt_binds_parent_body_and_registration(self) -> None:
        manifest, receipt = _manifest_and_receipt()
        self.assertEqual(validate_outreach_manifest(manifest), manifest)
        report = validate_publication_receipt(receipt, manifest)
        self.assertTrue(report["valid"])
        self.assertEqual(report["invitation_comment_id"], "invitation-002")

        mutations = []
        wrong_parent = deepcopy(receipt)
        wrong_parent["invitation"]["parent_id"] = "wrong-parent"
        mutations.append(wrong_parent)
        wrong_post = deepcopy(receipt)
        wrong_post["invitation"]["post_id"] = "wrong-post"
        mutations.append(wrong_post)
        wrong_body = deepcopy(receipt)
        wrong_body["invitation"]["body_text"] += "x"
        mutations.append(wrong_body)
        wrong_registration = deepcopy(receipt)
        wrong_registration["registration_commit"] = "3" * 40
        mutations.append(wrong_registration)
        for mutation in mutations:
            with self.assertRaises(ValidationError):
                validate_publication_receipt(mutation, manifest)

    def test_first_exact_direct_child_stops_even_when_malformed(self) -> None:
        manifest, receipt = _manifest_and_receipt()
        events = [
            _event("later-valid", "2026-08-23T14:02:00Z", canonical_json_text(_response())),
            _event("earlier-malformed", "2026-08-23T14:01:00Z", "not json"),
        ]
        report = classify_response_events(
            events,
            publication_receipt=receipt,
            outreach_manifest=manifest,
            stream_receipt=_stream_receipt(events, "2026-08-23T14:03:00Z"),
        )
        self.assertEqual(report["status"], "stopped-response")
        self.assertEqual(report["selected_event_id"], "earlier-malformed")
        self.assertEqual(report["eligible_response_count"], 2)
        self.assertFalse(report["response_contract_report"]["valid"])
        self.assertTrue(report["malformed_stopping_response_still_stops"])

    def test_sibling_wrong_author_wrong_post_and_late_events_do_not_stop(self) -> None:
        manifest, receipt = _manifest_and_receipt()
        body = canonical_json_text(_response())
        events = [
            _event("sibling", "2026-08-23T14:01:00Z", body, parent_id=OFFER_COMMENT_ID),
            _event("wrong-author", "2026-08-23T14:01:01Z", body, author_id="other"),
            _event("wrong-post", "2026-08-23T14:01:02Z", body, post_id="other"),
            _event("late", "2026-08-30T13:00:01Z", body),
        ]
        report = classify_response_events(
            events,
            publication_receipt=receipt,
            outreach_manifest=manifest,
            stream_receipt=_stream_receipt(events, "2026-08-30T13:00:02Z"),
        )
        self.assertEqual(report["status"], "stopped-channel-null")
        self.assertFalse(report["stopping_response"])
        self.assertIsNone(report["selected_event_id"])

    def test_outreach_is_commit_pinned_claim_bounded_and_not_authority(self) -> None:
        manifest = render_outreach_manifest("1" * 40)
        self.assertEqual(manifest["parent_offer_comment_id"], OFFER_COMMENT_ID)
        self.assertIn("/" + "1" * 40 + "/", manifest["packet_uri"])
        self.assertEqual(manifest["body_utf8_bytes"], len(manifest["body_text"].encode("utf-8")))
        self.assertEqual(manifest["body_sha256"], sha256_ref(manifest["body_text"]))
        self.assertIn("If that still fits your offer", manifest["body_text"])
        self.assertIn("0%", manifest["body_text"])
        self.assertIn("unknown/null", manifest["body_text"])
        self.assertIn("no reminder", manifest["body_text"])
        self.assertIn("packet is not authority", manifest["body_text"])
        self.assertIn(DEADLINE_UTC, manifest["body_text"])
        self.assertNotIn("salt_hex", manifest["body_text"])

    def test_validator_is_offline_and_has_no_network_client(self) -> None:
        source = (REPO_ROOT / "interop_lab/solicited_output_conformance_experiment.py").read_text()
        for forbidden in ("import requests", "urllib.request", "httpx", "aiohttp", "subprocess", "curl "):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
