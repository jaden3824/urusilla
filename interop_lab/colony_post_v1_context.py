#!/usr/bin/env python3
"""Offline validation for post-stop context on the frozen Colony v1 run.

The artifact validated here is additive. It does not change the frozen v1
publication, qualification, stop, or claim boundary. It performs no network or
external action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .interop_lab import ValidationError
    from .solicited_matched_experiment import (
        _exact_keys,
        _object,
        _require,
        _utc_datetime,
        load_json,
        sha256_ref,
    )
    from .solicited_matched_response_observation import (
        load_observation as load_v1_response_observation,
    )
except ImportError:  # pragma: no cover - direct execution convenience
    from interop_lab import ValidationError  # type: ignore[no-redef]
    from solicited_matched_experiment import (  # type: ignore[no-redef]
        _exact_keys,
        _object,
        _require,
        _utc_datetime,
        load_json,
        sha256_ref,
    )
    from solicited_matched_response_observation import (  # type: ignore[no-redef]
        load_observation as load_v1_response_observation,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PATH = (
    REPO_ROOT / "interop_lab/evidence/colony_post_v1_context_2026_08_23.json"
)
V1_RESPONSE_OBSERVATION_PATH = (
    REPO_ROOT
    / "interop_lab/evidence/solicited_matched_001.external_response.observation.json"
)
V1_PUBLICATION_RECEIPT_PATH = (
    REPO_ROOT / "interop_lab/evidence/solicited_matched_001.publication.receipt.json"
)

CONTEXT_SCHEMA = "urusilla-colony-post-v1-context-observation/1"
CONTEXT_ID = "the-colony-post-v1-context-2026-08-23"
RECORDED_AT = "2026-08-23T13:05:21Z"
THREAD_POST_ID = "11d4e684-5791-4015-acdb-9dda9ff157d0"
ROOT_COMMENT_ID = "0deb1ba2-ec0d-4be1-8a57-41c847faeac0"
REGISTERED_PARENT_ID = "d33a0c4e-3a06-4e92-914c-af612f4a34e4"
INVITATION_COMMENT_ID = "a93a952a-2aef-42af-bebe-6766b7363f6c"
V1_STOP_COMMENT_ID = "bdc42fcc-a75a-4d60-b2aa-97f249f872bf"
V1_STOP_AT = "2026-08-23T08:59:15.457084Z"
PROSE_COMMENT_ID = "0fcf2733-5bdb-41c4-98ec-a0725dfcbf0f"
LONGCAT_COMMENT_ID = "f3473a32-0099-4aae-85d2-c18815d32a1e"

V1_RESPONSE_OBSERVATION_SHA256 = (
    "sha256:34b6099499368568c12c2d83c826d8fb154a515c4936e45db76d7daf46716012"
)
V1_PUBLICATION_RECEIPT_SHA256 = (
    "sha256:fba9a1553852a44ee2645b8df8408c1678548cdeb27fe88c83b3f756009432a6"
)

SOURCE_SHA256 = (
    "sha256:e962fdeea5ac71acad8a1a0d91dcc945d80da8d8aa01881f57eb8146a617a6b8"
)
FROZEN_V1_SHA256 = (
    "sha256:8745a8c6cae636cbd7249e6a4da847f82114f245dfc2fbed8074dba767836339"
)
THREAD_SNAPSHOT_SHA256 = (
    "sha256:91155e73bb985cfbb9fcdfcece3e5f75cf56bc11e60dbdbef51842496e432823"
)
CORRECTIONS_SHA256 = (
    "sha256:29c4df79dab20ddb132903a06cdf3889dddc7a02b69a49693cc813ab025963f9"
)
EXTERNAL_ACTION_BOUNDARY_SHA256 = (
    "sha256:48c6dec6a958ee84878db4e9a9037ef214ee52dbb95ebfac442a31e16c806b43"
)
CLAIM_BOUNDARY_SHA256 = (
    "sha256:f1416f77ce4688de43aaacb39892a3797713777e6772009da8f64f2048a66444"
)
LIMITATIONS_SHA256 = (
    "sha256:77e85d45a13256f91e247a6442855ceb4091139ffdb57be636aa92d48bb6daa4"
)

COMMENT_IDS = (
    PROSE_COMMENT_ID,
    "f0ab1c26-cdab-44cf-9018-1e916b05b99d",
    "569c288b-8fc8-4405-8706-4e43c55241bf",
    LONGCAT_COMMENT_ID,
)

COMMENT_SPECS: dict[str, dict[str, Any]] = {
    PROSE_COMMENT_ID: {
        "parent_id": ROOT_COMMENT_ID,
        "created_at": "2026-08-23T09:00:33.588965Z",
        "updated_at": "2026-08-23T09:00:33.588969Z",
        "client": "colony-sdk-python",
        "body_equals_safe_text": False,
        "body_bytes": 3642,
        "body_characters": 3628,
        "body_sha256": "sha256:2ee90400155cc1b1bd015cbc9c91aefe3b8e78f4e60fa6e4277e0ca39d0178d3",
        "author_sha256": "sha256:2c127d1fb3ff108d6100f7a02a261535a127502edce07a0225420d72053427f0",
        "chronology_sha256": "sha256:a0d32b731d94900dafa7c48001ba689fb99d03d9669ed03288eee6131df00116",
        "classification_sha256": "sha256:0b4155d94aa245daafd2a6a683d26670a885d43735f9b8f648b8b21c9e140ca0",
    },
    "f0ab1c26-cdab-44cf-9018-1e916b05b99d": {
        "parent_id": ROOT_COMMENT_ID,
        "created_at": "2026-08-23T09:34:29.440023Z",
        "updated_at": "2026-08-23T09:34:29.440028Z",
        "client": None,
        "body_equals_safe_text": False,
        "body_bytes": 2450,
        "body_characters": 2446,
        "body_sha256": "sha256:6b606be73bab87995e6005571edc5811eaf44a27013cc0217e30c54f6194f8b7",
        "author_sha256": "sha256:10429adcebab044d8460f5ad8b8365335253d9d0886598c03411c5504212a6fd",
        "chronology_sha256": "sha256:7b244d6768531ad609bffba12d924afe952893922ecae81f048af609cd12c5a1",
        "classification_sha256": "sha256:435fe0b18a482ea9691af10f864154c9d0332111f3c1a76c483b8609ae833ee8",
    },
    "569c288b-8fc8-4405-8706-4e43c55241bf": {
        "parent_id": None,
        "created_at": "2026-08-23T09:39:36.484111Z",
        "updated_at": "2026-08-23T09:39:36.484118Z",
        "client": None,
        "body_equals_safe_text": True,
        "body_bytes": 505,
        "body_characters": 505,
        "body_sha256": "sha256:82920d1d93d7fe9f4cf9376ffdad28bd543788f4bd0eab6eae8d68b4c113eb0b",
        "author_sha256": "sha256:b488cf570cb78a26764482d78c408575564d51fb49449d1a1358855df049f451",
        "chronology_sha256": "sha256:3c9e61dda8f457a67ac79795c740d6ea665dac5e3faa6073f9fc258fa929f6ba",
        "classification_sha256": "sha256:5ef8e8c2dfc1613f674df05bb748f9d6c3169d63b802ab7fafc0dffe2b0cc998",
    },
    LONGCAT_COMMENT_ID: {
        "parent_id": None,
        "created_at": "2026-08-23T12:32:27.698661Z",
        "updated_at": "2026-08-23T12:32:27.698666Z",
        "client": "colony-sdk-python",
        "body_equals_safe_text": False,
        "body_bytes": 4602,
        "body_characters": 4592,
        "body_sha256": "sha256:fb2ee58b1fb9d452e615605cf75a41d65ae9932d1613d6f17658d5dcf5f44d98",
        "author_sha256": "sha256:65a5875275001c2ef194f085347a280760da03826e0c1e5e6a54a2bdae542632",
        "chronology_sha256": "sha256:3c9e61dda8f457a67ac79795c740d6ea665dac5e3faa6073f9fc258fa929f6ba",
        "classification_sha256": "sha256:aec6a64b69a87d53d745d8bf1e4f55d66aae3f61c44c4d3d98510b875167e073",
    },
}

CORRECTION_IDS = (
    "longcat-clawprint-stub-confirmed",
    "longcat-reachability-denominator-inconsistent",
    "longcat-4claw-wrong-domain",
    "longcat-moltbook-discovery-probe-incomplete",
    "longcat-526-maintenance-inference-unsupported",
    "longcat-verification-cost-percentages-unverified",
)

CONDITIONAL_OFFER = (
    "I will run all six and return them in your envelope if you register a "
    "variant whose evidence requirements are scoped to output conformance."
)

TOP_LEVEL_KEYS = (
    "schema_version",
    "observation_id",
    "recorded_at_utc",
    "source",
    "frozen_v1",
    "thread_snapshot",
    "comments",
    "project_corrections",
    "external_action_boundary",
    "aggregate_claim_boundary",
    "limitations",
)

COMMENT_KEYS = (
    "id",
    "official_api_uri",
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
    "body",
    "chronology",
    "classification",
    "claim_boundary",
)

CLAIM_KEYS = (
    "claim_eligible",
    "matched_result",
    "matched_task_run_observed",
    "direct_consumption_task_run_observed",
    "independent_reproduction",
    "organic_adoption",
    "task_success_evidence",
    "efficiency_evidence",
    "protocol_version_result",
    "state_of_the_art_claim_eligible",
    "general_unfamiliar_agent_saving_percent",
    "safely_completed_real_task_total_token_result",
)


def _file_sha256(path: Path) -> str:
    try:
        return sha256_ref(path.read_bytes())
    except OSError as exc:
        raise ValidationError(f"cannot hash {path}: {exc}") from exc


def _require_digest(value: Any, expected: str, label: str) -> None:
    _require(sha256_ref(value) == expected, f"{label} differs")


def _validate_frozen_v1(frozen: dict[str, Any]) -> None:
    _exact_keys(
        frozen,
        (
            "experiment_id",
            "publication_comment_id",
            "publication_parent_id",
            "publication_created_at",
            "publication_body_sha256",
            "stop_comment_id",
            "stop_comment_parent_id",
            "stop_triggered_at_utc",
            "stop_comment_body_sha256",
            "response_observation_path",
            "response_observation_file_sha256",
            "publication_receipt_path",
            "publication_receipt_file_sha256",
            "stop_observation_referenced_not_duplicated",
            "frozen_contract_modified",
        ),
        "frozen_v1",
    )
    _require_digest(frozen, FROZEN_V1_SHA256, "frozen v1 reference")
    _require(
        _file_sha256(V1_RESPONSE_OBSERVATION_PATH) == V1_RESPONSE_OBSERVATION_SHA256,
        "frozen v1 response observation bytes differ",
    )
    _require(
        _file_sha256(V1_PUBLICATION_RECEIPT_PATH) == V1_PUBLICATION_RECEIPT_SHA256,
        "frozen v1 publication receipt bytes differ",
    )
    v1 = load_v1_response_observation()
    _require(v1["comment"]["id"] == V1_STOP_COMMENT_ID, "referenced v1 stop comment differs")
    _require(
        v1["response_body"]["sha256"] == frozen["stop_comment_body_sha256"],
        "referenced v1 stop body digest differs",
    )
    _require(
        v1["qualification"]["stop_triggered_at_utc"] == V1_STOP_AT,
        "referenced v1 stop time differs",
    )


def _validate_comment(value: Any, expected_id: str) -> dict[str, Any]:
    comment = _object(value, f"comment {expected_id}")
    _exact_keys(comment, COMMENT_KEYS, f"comment {expected_id}")
    spec = COMMENT_SPECS[expected_id]
    _require(comment.get("id") == expected_id, "context comment order or ID differs")
    _require(comment.get("post_id") == THREAD_POST_ID, "context comment post differs")
    _require(comment.get("parent_id") == spec["parent_id"], "context comment parent differs")
    _require(
        comment.get("official_api_uri")
        == f"https://thecolony.ai/api/v1/comments/{expected_id}",
        "context comment API URI differs",
    )
    _require(
        comment.get("public_uri")
        == f"https://thecolony.ai/post/{THREAD_POST_ID}#comment-{expected_id}",
        "context comment public URI differs",
    )
    _require(comment.get("created_at") == spec["created_at"], "context creation time differs")
    _require(comment.get("updated_at") == spec["updated_at"], "context update time differs")
    _require(comment.get("source") == "api", "context source differs")
    _require(comment.get("client") == spec["client"], "context client differs")
    _require(comment.get("score") == 0, "context score differs")
    _require(comment.get("content_warnings") == [], "context warnings differ")
    _require(comment.get("cognition") is None, "context cognition must remain null")
    _require(
        comment.get("body_equals_safe_text") is spec["body_equals_safe_text"],
        "context body/safe-text verdict differs",
    )

    author = _object(comment.get("author"), f"comment {expected_id} author")
    _exact_keys(author, ("id", "username", "display_name", "user_type"), "comment author")
    _require(author.get("user_type") == "agent", "context author type differs")
    _require_digest(author, spec["author_sha256"], "context author")

    body = _object(comment.get("body"), f"comment {expected_id} body")
    _exact_keys(
        body,
        ("encoding", "utf8_bytes", "characters", "sha256", "text"),
        "context body",
    )
    text = body.get("text")
    _require(type(text) is str, "context body text must be text")
    assert isinstance(text, str)
    _require(body.get("encoding") == "utf-8", "context body encoding differs")
    _require(body.get("utf8_bytes") == len(text.encode("utf-8")), "context byte count differs")
    _require(body.get("characters") == len(text), "context character count differs")
    _require(body.get("utf8_bytes") == spec["body_bytes"], "frozen context byte count differs")
    _require(
        body.get("characters") == spec["body_characters"],
        "frozen context character count differs",
    )
    _require(body.get("sha256") == sha256_ref(text), "context body digest differs")
    _require(body.get("sha256") == spec["body_sha256"], "frozen context body differs")

    chronology = _object(comment.get("chronology"), f"comment {expected_id} chronology")
    _exact_keys(
        chronology,
        (
            "after_v1_publication",
            "after_v1_stop",
            "direct_child_of_invitation",
            "direct_descendant_of_invitation",
            "direct_child_of_root_comment",
            "top_level_comment",
            "sibling_of_registered_parent",
            "post_stop_context_only",
            "semantic_relation_to_v1",
        ),
        "comment chronology",
    )
    _require_digest(chronology, spec["chronology_sha256"], "context chronology")
    _require(chronology.get("after_v1_stop") is True, "context must remain post-stop")
    _require(
        chronology.get("direct_descendant_of_invitation") is False,
        "context cannot be reparented to the v1 invitation",
    )

    classification = _object(
        comment.get("classification"), f"comment {expected_id} classification"
    )
    _exact_keys(
        classification,
        (
            "evidence_class",
            "substantive",
            "response_scope",
            "reproduction_interest",
            "conditional_offer",
            "venue_advice",
            "cross_platform_testimony",
            "explicit_non_adoption",
            "experimental_result_observed",
        ),
        "comment classification",
    )
    _require_digest(
        classification,
        spec["classification_sha256"],
        "context classification",
    )
    _require(
        classification.get("experimental_result_observed") is False,
        "context cannot become an experiment result",
    )
    if expected_id == PROSE_COMMENT_ID:
        _require(
            classification.get("reproduction_interest") == "conditional",
            "prose conditional interest differs",
        )
        _require(
            classification.get("conditional_offer") == CONDITIONAL_OFFER,
            "prose conditional offer differs",
        )
        _require(CONDITIONAL_OFFER in text, "prose body does not contain the frozen offer")
    else:
        _require(
            classification.get("reproduction_interest") == "none",
            "venue context cannot become reproduction interest",
        )
        _require(
            classification.get("conditional_offer") is None,
            "venue context conditional offer must remain null",
        )

    claim_boundary = _object(
        comment.get("claim_boundary"), f"comment {expected_id} claim boundary"
    )
    _exact_keys(claim_boundary, CLAIM_KEYS, "comment claim boundary")
    _require_digest(claim_boundary, CLAIM_BOUNDARY_SHA256, "comment claim boundary")

    created_at = _utc_datetime(comment["created_at"], "context created_at")
    updated_at = _utc_datetime(comment["updated_at"], "context updated_at")
    stop_at = _utc_datetime(V1_STOP_AT, "v1 stop")
    recorded_at = _utc_datetime(RECORDED_AT, "context recorded_at")
    _require(stop_at < created_at <= updated_at <= recorded_at, "context chronology differs")
    return comment


def validate_context(value: Any) -> dict[str, Any]:
    """Validate the immutable post-stop context manifest."""

    context = _object(value, "context")
    _exact_keys(context, TOP_LEVEL_KEYS, "context")
    _require(context.get("schema_version") == CONTEXT_SCHEMA, "context schema differs")
    _require(context.get("observation_id") == CONTEXT_ID, "context observation ID differs")
    _require(context.get("recorded_at_utc") == RECORDED_AT, "context record time differs")

    source = _object(context.get("source"), "source")
    _exact_keys(
        source,
        (
            "method",
            "official_thread_comments_api_uri",
            "authenticated",
            "external_write_performed",
        ),
        "source",
    )
    _require_digest(source, SOURCE_SHA256, "context source")
    _require(source.get("external_write_performed") is False, "context must remain read-only")

    frozen = _object(context.get("frozen_v1"), "frozen_v1")
    _validate_frozen_v1(frozen)

    snapshot = _object(context.get("thread_snapshot"), "thread_snapshot")
    _exact_keys(
        snapshot,
        (
            "post_id",
            "root_comment_id",
            "registered_parent_comment_id",
            "invitation_comment_id",
            "observed_at_utc",
            "response_server_date_utc",
            "request_id",
            "content_type",
            "content_length",
            "total_comments",
            "has_more",
            "post_stop_context_comment_count",
            "direct_reply_count_to_invitation",
        ),
        "thread_snapshot",
    )
    _require_digest(snapshot, THREAD_SNAPSHOT_SHA256, "thread snapshot")
    _require(snapshot.get("post_id") == THREAD_POST_ID, "thread post differs")
    _require(snapshot.get("root_comment_id") == ROOT_COMMENT_ID, "thread root differs")
    _require(
        snapshot.get("registered_parent_comment_id") == REGISTERED_PARENT_ID,
        "thread registered parent differs",
    )
    _require(
        snapshot.get("invitation_comment_id") == INVITATION_COMMENT_ID,
        "thread invitation differs",
    )
    _require(snapshot.get("direct_reply_count_to_invitation") == 0, "direct reply count differs")

    comments = context.get("comments")
    _require(type(comments) is list and len(comments) == 4, "context comments differ")
    assert isinstance(comments, list)
    _require(
        [item.get("id") if type(item) is dict else None for item in comments]
        == list(COMMENT_IDS),
        "context comment IDs or order differ",
    )
    _require(V1_STOP_COMMENT_ID not in COMMENT_IDS, "v1 stop response must not be duplicated")
    validated_comments = [
        _validate_comment(comment, expected_id)
        for comment, expected_id in zip(comments, COMMENT_IDS, strict=True)
    ]

    corrections = context.get("project_corrections")
    _require(type(corrections) is list and len(corrections) == 6, "project corrections differ")
    assert isinstance(corrections, list)
    _require(
        [item.get("correction_id") if type(item) is dict else None for item in corrections]
        == list(CORRECTION_IDS),
        "project correction IDs or order differ",
    )
    for item in corrections:
        correction = _object(item, "project correction")
        _exact_keys(
            correction,
            (
                "correction_id",
                "source_comment_id",
                "subject",
                "respondent_assertion",
                "project_status",
                "project_finding",
                "verification",
                "claim_use",
            ),
            "project correction",
        )
        _require(
            correction.get("source_comment_id") == LONGCAT_COMMENT_ID,
            "project correction source differs",
        )
        _object(correction.get("verification"), "project correction verification")
    _require_digest(corrections, CORRECTIONS_SHA256, "project corrections")

    action = _object(context.get("external_action_boundary"), "external_action_boundary")
    _exact_keys(
        action,
        (
            "source_comment_id",
            "conditional_variant_invitation_present",
            "invited_scope",
            "proposed_direct_reply_parent_id",
            "third_party_invitation_is_project_operator_authorization",
            "automatic_reply_allowed",
            "external_reply_performed_for_this_observation",
        ),
        "external_action_boundary",
    )
    _require_digest(action, EXTERNAL_ACTION_BOUNDARY_SHA256, "external action boundary")
    _require(
        action.get("proposed_direct_reply_parent_id") == PROSE_COMMENT_ID,
        "proposed direct reply parent differs",
    )
    _require(
        action.get("third_party_invitation_is_project_operator_authorization") is False
        and action.get("automatic_reply_allowed") is False
        and action.get("external_reply_performed_for_this_observation") is False,
        "external action boundary was expanded",
    )

    aggregate = _object(context.get("aggregate_claim_boundary"), "aggregate_claim_boundary")
    _exact_keys(aggregate, CLAIM_KEYS, "aggregate claim boundary")
    _require_digest(aggregate, CLAIM_BOUNDARY_SHA256, "aggregate claim boundary")

    limitations = context.get("limitations")
    _require(
        type(limitations) is list
        and len(limitations) == 6
        and all(type(item) is str and bool(item.strip()) for item in limitations),
        "context limitations differ",
    )
    _require_digest(limitations, LIMITATIONS_SHA256, "context limitations")

    snapshot_at = _utc_datetime(snapshot["observed_at_utc"], "thread observed_at")
    recorded_at = _utc_datetime(context["recorded_at_utc"], "context recorded_at")
    _require(snapshot_at <= recorded_at, "context was recorded before the thread snapshot")

    return {
        "valid": True,
        "observation_id": CONTEXT_ID,
        "comment_ids": [item["id"] for item in validated_comments],
        "conditional_reproduction_interest_comment_id": PROSE_COMMENT_ID,
        "proposed_direct_reply_parent_id": PROSE_COMMENT_ID,
        "project_correction_ids": list(CORRECTION_IDS),
        "claim_eligible": False,
        "independent_reproduction": False,
        "organic_adoption": False,
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
    }


def load_context(path: Path = CONTEXT_PATH) -> dict[str, Any]:
    value = load_json(path)
    validate_context(value)
    return _object(value, "context")


__all__ = [
    "COMMENT_IDS",
    "CONDITIONAL_OFFER",
    "CONTEXT_ID",
    "CONTEXT_PATH",
    "CONTEXT_SCHEMA",
    "CORRECTION_IDS",
    "PROSE_COMMENT_ID",
    "load_context",
    "validate_context",
]
