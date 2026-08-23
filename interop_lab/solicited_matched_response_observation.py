#!/usr/bin/env python3
"""Offline validation for the first public solicited-matched response.

This additive validator does not change the frozen preregistration, packet,
publication receipt, or the receipt-v1 direct-child rule.  It preserves the
observed sibling-branch parentage and applies the frozen public-reply stop rule
conservatively.  It performs no network or external action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .interop_lab import ValidationError
    from .solicited_matched_experiment import (
        CAPSULE_SHA256,
        EXPERIMENT_ID,
        OUTREACH_THREAD_URI,
        PACKET_CANONICAL_SHA256,
        PACKET_FILE_SHA256,
        PREREG_CANONICAL_SHA256,
        PREREG_FILE_SHA256,
        PUBLIC_RESPONSE_KINDS,
        _exact_keys,
        _object,
        _parse_public_response_body,
        _require,
        _utc_datetime,
        load_json,
        sha256_ref,
    )
except ImportError:  # pragma: no cover - direct execution convenience
    from interop_lab import ValidationError  # type: ignore[no-redef]
    from solicited_matched_experiment import (  # type: ignore[no-redef]
        CAPSULE_SHA256,
        EXPERIMENT_ID,
        OUTREACH_THREAD_URI,
        PACKET_CANONICAL_SHA256,
        PACKET_FILE_SHA256,
        PREREG_CANONICAL_SHA256,
        PREREG_FILE_SHA256,
        PUBLIC_RESPONSE_KINDS,
        _exact_keys,
        _object,
        _parse_public_response_body,
        _require,
        _utc_datetime,
        load_json,
        sha256_ref,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVATION_PATH = (
    REPO_ROOT
    / "interop_lab/evidence/solicited_matched_001.external_response.observation.json"
)
PREREG_PATH = REPO_ROOT / "interop_lab/challenges/solicited_matched_001.preregistration.json"
PACKET_PATH = REPO_ROOT / "interop_lab/challenges/solicited_matched_001.packet.json"
CAPSULE_PATH = REPO_ROOT / "urusilla_capsule_v0_1.json"
PUBLICATION_RECEIPT_PATH = (
    REPO_ROOT / "interop_lab/evidence/solicited_matched_001.publication.receipt.json"
)

OBSERVATION_SCHEMA = "urusilla-solicited-matched-external-response-observation/1"
OBSERVATION_ID = "solicited-matched-001-the-colony-bdc42fcc"
PUBLICATION_RECEIPT_FILE_SHA256 = (
    "sha256:fba9a1553852a44ee2645b8df8408c1678548cdeb27fe88c83b3f756009432a6"
)
RESPONSE_BODY_SHA256 = (
    "sha256:f822fe6b5851266b4dc95d7af326aaba40506ade4d783fa3ccb53dc362a66049"
)
HTTP_RESPONSE_BODY_SHA256 = (
    "sha256:7acaae1c293fc39aac5fa8fe882310d9c909a1bf38622619b21da34863cba0bf"
)

THREAD_POST_ID = "11d4e684-5791-4015-acdb-9dda9ff157d0"
ROOT_COMMENT_ID = "0deb1ba2-ec0d-4be1-8a57-41c847faeac0"
REGISTERED_PARENT_ID = "d33a0c4e-3a06-4e92-914c-af612f4a34e4"
INVITATION_COMMENT_ID = "a93a952a-2aef-42af-bebe-6766b7363f6c"
RESPONSE_COMMENT_ID = "bdc42fcc-a75a-4d60-b2aa-97f249f872bf"
RESPONSE_PUBLIC_URI = f"{OUTREACH_THREAD_URI}#comment-{RESPONSE_COMMENT_ID}"
RESPONSE_AUTHOR_ID = "324ab98e-955c-4274-bd30-8570cbdf58f1"
RESPONSE_CREATED_AT = "2026-08-23T08:59:15.457084Z"
OBSERVED_AT = "2026-08-23T11:15:36Z"

PARENTAGE_CAVEAT = (
    "The response is not a direct child or descendant of the invitation. It is "
    "a sibling of the invitation's registered parent under the same root comment. "
    "The frozen qualifying-response wording requires a public reply in the "
    "registered thread but contains no parent_id constraint; qualification is "
    "therefore literal and conservative, without retroactively changing v1."
)


def _file_sha256(path: Path) -> str:
    try:
        return sha256_ref(path.read_bytes())
    except OSError as exc:
        raise ValidationError(f"cannot hash {path}: {exc}") from exc


def validate_observation(value: Any) -> dict[str, Any]:
    """Validate the immutable, read-only external-response observation."""

    observation = _object(value, "observation")
    _exact_keys(
        observation,
        (
            "schema_version",
            "observation_id",
            "experiment_id",
            "recorded_at_utc",
            "bindings",
            "readback",
            "comment",
            "response_body",
            "parentage",
            "qualification",
            "evidence_class",
            "claim_boundary",
            "limitations",
        ),
        "observation",
    )
    _require(observation.get("schema_version") == OBSERVATION_SCHEMA, "observation schema differs")
    _require(observation.get("observation_id") == OBSERVATION_ID, "observation ID differs")
    _require(observation.get("experiment_id") == EXPERIMENT_ID, "observation experiment differs")
    _require(observation.get("recorded_at_utc") == OBSERVED_AT, "observation time differs")

    bindings = _object(observation.get("bindings"), "bindings")
    expected_bindings = {
        "preregistration_path": "interop_lab/challenges/solicited_matched_001.preregistration.json",
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "preregistration_file_sha256": PREREG_FILE_SHA256,
        "packet_path": "interop_lab/challenges/solicited_matched_001.packet.json",
        "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
        "packet_file_sha256": PACKET_FILE_SHA256,
        "grammar_capsule_path": "urusilla_capsule_v0_1.json",
        "grammar_capsule_file_sha256": CAPSULE_SHA256,
        "grammar_capsule_utf8_bytes": 33476,
        "publication_receipt_path": "interop_lab/evidence/solicited_matched_001.publication.receipt.json",
        "publication_receipt_file_sha256": PUBLICATION_RECEIPT_FILE_SHA256,
    }
    _require(bindings == expected_bindings, "observation frozen bindings differ")
    _require(_file_sha256(PREREG_PATH) == PREREG_FILE_SHA256, "frozen preregistration bytes differ")
    _require(_file_sha256(PACKET_PATH) == PACKET_FILE_SHA256, "frozen packet bytes differ")
    _require(_file_sha256(CAPSULE_PATH) == CAPSULE_SHA256, "Grammar Capsule bytes differ")
    _require(len(CAPSULE_PATH.read_bytes()) == 33476, "Grammar Capsule byte count differs")
    _require(
        _file_sha256(PUBLICATION_RECEIPT_PATH) == PUBLICATION_RECEIPT_FILE_SHA256,
        "frozen publication receipt bytes differ",
    )

    readback = _object(observation.get("readback"), "readback")
    expected_readback = {
        "method": "public-unauthenticated-single-comment-api",
        "official_comment_api_uri": f"https://thecolony.ai/api/v1/comments/{RESPONSE_COMMENT_ID}",
        "official_thread_comments_api_uri": (
            f"https://thecolony.ai/api/v1/posts/{THREAD_POST_ID}/comments"
            "?sort=oldest&limit=100&page=1"
        ),
        "observed_at_utc": OBSERVED_AT,
        "http_status": 200,
        "response_server_date_utc": OBSERVED_AT,
        "request_id": "req_24ed2e3ede21489c87a53b48b28d903c",
        "content_type": "application/json",
        "content_length": 5682,
        "http_response_body_sha256": HTTP_RESPONSE_BODY_SHA256,
        "http_response_body_embedded": False,
        "thread_total_comments": 9,
        "thread_has_more": False,
        "direct_reply_count_to_invitation": 0,
        "authenticated": False,
    }
    _require(readback == expected_readback, "observation API readback differs")

    comment = _object(observation.get("comment"), "comment")
    _exact_keys(
        comment,
        (
            "id",
            "public_uri",
            "post_id",
            "parent_id",
            "author",
            "created_at",
            "updated_at",
            "source",
            "client",
            "score",
            "content_warnings",
            "cognition",
            "body_equals_safe_text",
        ),
        "comment",
    )
    _require(comment.get("id") == RESPONSE_COMMENT_ID, "response comment ID differs")
    _require(comment.get("public_uri") == RESPONSE_PUBLIC_URI, "response public URI differs")
    _require(comment.get("post_id") == THREAD_POST_ID, "response post ID differs")
    _require(comment.get("parent_id") == ROOT_COMMENT_ID, "response parent ID differs")
    _require(
        comment.get("author")
        == {
            "id": RESPONSE_AUTHOR_ID,
            "username": "colonist-one",
            "display_name": "ColonistOne",
            "user_type": "agent",
        },
        "response author differs",
    )
    _require(comment.get("created_at") == RESPONSE_CREATED_AT, "response creation time differs")
    _require(comment.get("updated_at") == "2026-08-23T08:59:15.457089Z", "response update time differs")
    _require(comment.get("source") == "api", "response source differs")
    _require(comment.get("client") == "colony-sdk-python", "response client differs")
    _require(comment.get("score") == 0, "response score differs")
    _require(comment.get("content_warnings") == [], "response content warnings differ")
    _require(comment.get("cognition") is None, "response cognition must remain null")
    _require(comment.get("body_equals_safe_text") is True, "response body/safe-text match differs")

    response_body = _object(observation.get("response_body"), "response_body")
    _exact_keys(
        response_body,
        (
            "encoding",
            "utf8_bytes",
            "characters",
            "sha256",
            "ascii_only",
            "compact_canonical_json_exact_match",
            "text",
            "parsed_envelope",
        ),
        "response_body",
    )
    body_text = response_body.get("text")
    _require(type(body_text) is str, "response body text must be text")
    assert isinstance(body_text, str)
    _require(response_body.get("encoding") == "utf-8", "response body encoding differs")
    _require(response_body.get("utf8_bytes") == len(body_text.encode("utf-8")), "response body byte count differs")
    _require(response_body.get("characters") == len(body_text), "response body character count differs")
    _require(response_body.get("utf8_bytes") == 1752, "response body frozen byte count differs")
    _require(response_body.get("sha256") == sha256_ref(body_text), "response body digest differs")
    _require(response_body.get("sha256") == RESPONSE_BODY_SHA256, "response body frozen digest differs")
    _require(response_body.get("ascii_only") is body_text.isascii(), "response ASCII verdict differs")
    _require(response_body.get("ascii_only") is True, "response body must remain exact ASCII")
    envelope = _parse_public_response_body(body_text)
    _require(response_body.get("parsed_envelope") == envelope, "parsed response envelope differs")
    _require(
        response_body.get("compact_canonical_json_exact_match") is True,
        "response canonical-body verdict differs",
    )
    _require(envelope.get("experiment_id") == EXPERIMENT_ID, "response experiment identity differs")
    _require(envelope.get("grammar_capsule_file_sha256") == CAPSULE_SHA256, "response Capsule identity differs")
    _require(envelope.get("packet_canonical_sha256") == PACKET_CANONICAL_SHA256, "response packet identity differs")
    _require(
        envelope.get("preregistration_canonical_sha256") == PREREG_CANONICAL_SHA256,
        "response preregistration identity differs",
    )
    _require(envelope.get("response_kind") == "methodological-counterexample", "response kind differs")
    _require(
        type(envelope.get("response_note")) is str and bool(envelope["response_note"].strip()),
        "methodological counterexample note must remain nonempty",
    )

    parentage = _object(observation.get("parentage"), "parentage")
    expected_parentage = {
        "root_comment_id": ROOT_COMMENT_ID,
        "root_comment_parent_id": None,
        "registered_parent_comment_id": REGISTERED_PARENT_ID,
        "registered_parent_parent_id": ROOT_COMMENT_ID,
        "invitation_comment_id": INVITATION_COMMENT_ID,
        "invitation_parent_id": REGISTERED_PARENT_ID,
        "response_comment_id": RESPONSE_COMMENT_ID,
        "response_parent_id": ROOT_COMMENT_ID,
        "same_registered_post": True,
        "direct_child_of_invitation": False,
        "direct_descendant_of_invitation": False,
        "response_is_sibling_of_registered_parent": True,
    }
    _require(parentage == expected_parentage, "response parentage observation differs")

    qualification = _object(observation.get("qualification"), "qualification")
    expected_qualification = {
        "frozen_stop_rule": "first-qualifying-public-response-or-deadline-whichever-first",
        "registered_body_contract_valid": True,
        "exact_identity": True,
        "response_kind_allowed": True,
        "methodological_counterexample_note_nonempty": True,
        "same_registered_thread": True,
        "parent_id_constrained_by_frozen_qualification": False,
        "qualifies_under_literal_frozen_contract": True,
        "participant_asserted_independent_identity_recomputation": True,
        "participant_independence_verified": False,
        "project_recomputed_identity_values_match": True,
        "parentage_caveat": PARENTAGE_CAVEAT,
        "conservative_stop_applied": True,
        "stopped_by": "first-qualifying-public-response",
        "stop_triggered_at_utc": RESPONSE_CREATED_AT,
        "frozen_contract_modified": False,
        "later_visibility_only_self_bump_allowed": False,
        "cross_post_under_registration_allowed": False,
    }
    _require(qualification == expected_qualification, "response qualification observation differs")
    _require(envelope["response_kind"] in PUBLIC_RESPONSE_KINDS, "response kind is outside the frozen set")

    _require(
        observation.get("evidence_class")
        == "project-solicited-external-methodological-counterexample",
        "response evidence class differs",
    )
    claim_boundary = _object(observation.get("claim_boundary"), "claim_boundary")
    expected_claim_boundary = {
        "claim_eligible": False,
        "matched_result": False,
        "matched_task_run_observed": False,
        "direct_consumption_task_run_observed": False,
        "independent_reproduction": False,
        "organic_adoption": False,
        "task_success_evidence": False,
        "efficiency_evidence": False,
        "protocol_version_result": False,
        "state_of_the_art_claim_eligible": False,
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
    }
    _require(claim_boundary == expected_claim_boundary, "response claim boundary differs")

    limitations = observation.get("limitations")
    _require(
        type(limitations) is list
        and len(limitations) == 5
        and all(type(item) is str and bool(item.strip()) for item in limitations),
        "response limitations differ",
    )

    response_at = _utc_datetime(RESPONSE_CREATED_AT, "response created_at")
    observed_at = _utc_datetime(OBSERVED_AT, "observation recorded_at")
    _require(response_at <= observed_at, "response was observed before it was created")

    return {
        "valid": True,
        "observation_id": OBSERVATION_ID,
        "response_kind": envelope["response_kind"],
        "response_body_sha256": RESPONSE_BODY_SHA256,
        "qualifies_under_literal_frozen_contract": True,
        "direct_child_of_invitation": False,
        "stop_triggered_at_utc": RESPONSE_CREATED_AT,
        "evidence_class": observation["evidence_class"],
        "claim_eligible": False,
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
    }


def load_observation(path: Path = OBSERVATION_PATH) -> dict[str, Any]:
    value = load_json(path)
    validate_observation(value)
    return _object(value, "observation")


__all__ = [
    "HTTP_RESPONSE_BODY_SHA256",
    "OBSERVATION_ID",
    "OBSERVATION_PATH",
    "OBSERVATION_SCHEMA",
    "PARENTAGE_CAVEAT",
    "RESPONSE_BODY_SHA256",
    "load_observation",
    "validate_observation",
]
