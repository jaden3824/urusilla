#!/usr/bin/env python3
"""Offline validator for the bounded project-solicited matched microstudy.

The module reads declarative local JSON only.  It does not contact a model,
open a network connection, publish a post, authenticate a provider, or grant
authority for spending or another external effect.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

try:
    from .interop_lab import ValidationError, strict_json_loads
except ImportError:  # pragma: no cover - direct execution convenience
    from interop_lab import ValidationError, strict_json_loads  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = REPO_ROOT / "interop_lab/challenges/solicited_matched_001.preregistration.json"
PACKET_PATH = REPO_ROOT / "interop_lab/challenges/solicited_matched_001.packet.json"
RECEIPT_TEMPLATE_PATH = REPO_ROOT / "interop_lab/evidence/solicited_matched_001.receipt.template.json"
OUTREACH_BODY_RELATIVE_PATH = "interop_lab/challenges/solicited_matched_001.outreach.json"
OUTREACH_BODY_PATH = REPO_ROOT / OUTREACH_BODY_RELATIVE_PATH

PREREG_SCHEMA = "urusilla-solicited-matched-preregistration/1"
PACKET_SCHEMA = "urusilla-solicited-matched-packet/1"
RECEIPT_SCHEMA = "urusilla-solicited-matched-evidence-receipt/1"
OUTREACH_BODY_SCHEMA = "urusilla-solicited-matched-outreach-body/1"
EXPERIMENT_ID = "solicited-matched-001"
BASE_COMMIT = "c0834262f995ce3d695b3e76e6e2594c60d4f1f7"
HF_SHA256 = "sha256:b07125173b71585a943567cfd94ba55d9b375e5ae0024c21dbf2aa026c87066d"
FROZEN_METHOD_SHA256 = "sha256:5dedd746db68ad53e1c5d01ad5a1127eba78cfbab642bf697fa75a82584afd20"
CAPSULE_SHA256 = "sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
PREREG_CANONICAL_SHA256 = "sha256:c1e7293681a2ed640526c38b126a0d83da3883ea2e2e006f553920471c0385c8"
PREREG_FILE_SHA256 = "sha256:80b2f68fa64fac04c6e17d85a57fd3f8ea318fec4eda73b240c94eeccbc26cbe"
PACKET_CANONICAL_SHA256 = "sha256:0b891567a1601241466481912303541458c42d10571d023663b8840cdd3290fd"
PACKET_FILE_SHA256 = "sha256:56bd1e2bfe405918b6950f1b8c47defdb57c644e1cec29ade406c3d938bac339"

OUTREACH_HOST = "thecolony.ai"
OUTREACH_THREAD_URI = "https://thecolony.ai/post/11d4e684-5791-4015-acdb-9dda9ff157d0"
OUTREACH_PARENT_COMMENT_ID = "d33a0c4e-3a06-4e92-914c-af612f4a34e4"
OUTREACH_PARENT_COMMENT_URI = (
    OUTREACH_THREAD_URI + "#comment-" + OUTREACH_PARENT_COMMENT_ID
)
OUTREACH_PARENT_AUTHOR_LABEL = "ColonistOne"
OUTREACH_PARENT_AUTHOR_ID = "324ab98e-955c-4274-bd30-8570cbdf58f1"
OUTREACH_PUBLISHER_ACCOUNT_LABEL = "skdhbegjk"
OUTREACH_PUBLISHER_ACCOUNT_ID = "5ca1345d-5c38-400e-9fec-e1b12386d7bf"
OUTREACH_RENDERER_VERSION = "solicited-matched-outreach-v1"
IDENTITY_RESPONSE_FIELDS = (
    "experiment_id",
    "preregistration_canonical_sha256",
    "packet_canonical_sha256",
    "grammar_capsule_file_sha256",
)
PUBLIC_RESPONSE_FIELDS = (
    "experiment_id",
    "grammar_capsule_file_sha256",
    "packet_canonical_sha256",
    "preregistration_canonical_sha256",
    "response_kind",
    "response_note",
)
PUBLIC_RESPONSE_KINDS = (
    "matched-result",
    "refusal",
    "null",
    "fallback",
    "identity-mismatch",
    "methodological-counterexample",
)

ARM_IDS = ("raw", "json", "urusilla")
ARM_ORDER = ("json", "urusilla", "raw")
TASK_IDS = ("task-a", "task-b")
K_VALUES = (1, 2)
BLIND_BY_ARM = {
    "raw": "blind-13b7f4d89a0c2e61",
    "json": "blind-5e42c88a73f01d9b",
    "urusilla": "blind-a9c06d3145ef728b",
}
TOKEN_PHASES = (
    "setup",
    "sender",
    "router",
    "receiver",
    "output",
    "reasoning",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
)
LEDGER_FIELDS = (*TOKEN_PHASES, "total")
ATTEMPT_KINDS = {"primary", "retry", "repair", "fallback"}
ATTEMPT_STATUSES = {
    "completed",
    "timeout",
    "refused",
    "provider-error",
    "capture-rejected",
    "before-dispatch-failure",
}
NO_RESPONSE_ALLOWED_STATUSES = {
    "timeout",
    "provider-error",
    "capture-rejected",
    "before-dispatch-failure",
}
TOKEN_COUNT_SOURCES = {
    "provider-reported",
    "provider-reported-plus-local",
    "locally-counted-from-capture",
    "unknown",
}
RESULT_STATUSES = {
    "not-run",
    "matched-result",
    "refusal",
    "null",
    "fallback",
    "identity-mismatch",
    "methodological-counterexample",
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
RFC3339_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
MAX_TOKEN_COUNT = 10**15
MAX_PUBLIC_BODY_UTF8_BYTES = 10_000


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_ref(value: Any) -> str:
    if type(value) is bytes:
        raw = value
    elif type(value) is str:
        raw = value.encode("utf-8")
    else:
        raw = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    return strict_json_loads(text)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{path} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], keys: Iterable[str], path: str) -> None:
    expected = set(keys)
    observed = set(value)
    if expected != observed:
        raise ValidationError(
            f"{path} fields differ; missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _sha(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise ValidationError(f"{path} must be sha256:<64-lowercase-hex>{suffix}")
    return value


def _file_sha256(path: Path) -> str:
    try:
        return sha256_ref(path.read_bytes())
    except OSError as exc:
        raise ValidationError(f"cannot hash {path}: {exc}") from exc


def _nullable_bool(value: Any, path: str) -> bool | None:
    if value is None or type(value) is bool:
        return value
    raise ValidationError(f"{path} must be boolean or null")


def _nullable_count(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= MAX_TOKEN_COUNT:
        raise ValidationError(f"{path} must be a nonnegative integer or null")
    return value


def _https_uri(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str:
        raise ValidationError(f"{path} must be an HTTPS URI")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValidationError(f"{path} must be an HTTPS URI without credentials")
    return value


def _utc_timestamp(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or RFC3339_UTC_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise ValidationError(f"{path} must be an RFC 3339 UTC timestamp{suffix}")
    return value


def _github_blob_uri(commit: str, relative_path: str) -> str:
    return f"https://github.com/jaden3824/urusilla/blob/{commit}/{relative_path}"


def _github_raw_uri(commit: str, relative_path: str) -> str:
    return f"https://raw.githubusercontent.com/jaden3824/urusilla/{commit}/{relative_path}"


def _utc_datetime(value: Any, path: str) -> datetime:
    timestamp = _utc_timestamp(value, path)
    assert timestamp is not None
    try:
        return datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:  # pragma: no cover - guarded by the syntax check
        raise ValidationError(f"{path} is not a valid UTC timestamp") from exc


def _require_host(uri: str, host: str, path: str) -> None:
    parsed = urlsplit(uri)
    _require(parsed.hostname == host, f"{path} host differs")


def _task_by_id(plan: Mapping[str, Any], task_id: str) -> dict[str, Any]:
    tasks = _list(plan["tasks"], "preregistration.tasks")
    matches = [item for item in tasks if _object(item, "task").get("task_id") == task_id]
    _require(len(matches) == 1, f"preregistration must contain one {task_id}")
    return matches[0]


def _expected_from_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    budget = facts["budget_cents"]
    network_allowed = facts["network_allowed"]
    plans = facts["plans"]
    feasible = [
        plan
        for plan in plans
        if plan["cost_cents"] <= budget
        and (network_allowed or not plan["network_required"])
    ]
    tie_break = facts["tie_break"]
    if tie_break == "prefer-higher-robustness-when-both-feasible":
        selected = next(plan for plan in feasible if plan["robustness"] == "higher")
    elif tie_break == "prefer-lower-cost-when-both-feasible":
        selected = min(feasible, key=lambda plan: plan["cost_cents"])
    else:
        raise ValidationError("task tie-break is unknown")
    return {
        "ambiguous_without_tie_break": len(feasible) > 1,
        "feasible_plans": [plan["plan_id"] for plan in feasible],
        "remaining_budget_cents": {
            plan["plan_id"]: budget - plan["cost_cents"] for plan in plans
        },
        "selected_plan": selected["plan_id"],
        "selection_basis": "supplied-tie-break",
        "would_execute": False,
    }


def _validate_hf_task_a(plan: Mapping[str, Any]) -> None:
    try:
        source = load_json(REPO_ROOT / "hf_dataset/data/challenge.jsonl")
    except ValidationError:
        # JSONL has exactly one JSON object and no blank prefix in the frozen pack.
        text = (REPO_ROOT / "hf_dataset/data/challenge.jsonl").read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line]
        _require(len(lines) == 1, "HF challenge must contain exactly one record")
        source = strict_json_loads(lines[0])
    source_facts = source["challenge"]["task"]["facts"]
    expected = {
        "budget_cents": int(source_facts["budget_usd"] * 100),
        "network_allowed": source_facts["network_allowed"],
        "tie_break": "prefer-higher-robustness-when-both-feasible",
        "plans": [
            {
                "plan_id": item["plan_id"],
                "cost_cents": int(item["cost_usd"] * 100),
                "network_required": item["network_required"],
                "robustness": item["robustness"],
            }
            for item in source_facts["plans"]
        ],
    }
    _require(
        _task_by_id(plan, "task-a")["facts"] == expected,
        "task-a facts differ from the frozen HF task",
    )


def validate_preregistration(value: Any) -> dict[str, Any]:
    plan = _object(value, "preregistration")
    _exact_keys(
        plan,
        (
            "schema_version",
            "experiment_id",
            "status",
            "classification",
            "source_bindings",
            "known_result_boundary",
            "prior_search_lineage",
            "study_design",
            "common_output_contract",
            "tasks",
            "direct_consumption_contract",
            "capture_and_accounting_contract",
            "judge_calibration",
            "identity_readback_contract",
            "outreach_venue",
            "outreach_stop_rule",
            "authority_boundary",
            "interpretation",
        ),
        "preregistration",
    )
    _require(plan.get("schema_version") == PREREG_SCHEMA, "preregistration schema differs")
    _require(plan.get("experiment_id") == EXPERIMENT_ID, "experiment id differs")
    _require(plan.get("status") == "frozen-prerun-no-result", "preregistration status differs")
    _require(sha256_ref(plan) == PREREG_CANONICAL_SHA256, "preregistration canonical digest differs")
    _require(_file_sha256(PREREG_PATH) == PREREG_FILE_SHA256, "preregistration file bytes differ")

    classification = _object(plan.get("classification"), "classification")
    _require(
        classification
        == {
            "operation": "PROJECT-SOLICITED",
            "independent_reproduction_inferred": False,
            "organic_adoption_inferred": False,
            "external_adoption_evidence": False,
        },
        "preregistration classification differs",
    )

    bindings = _object(plan.get("source_bindings"), "source_bindings")
    expected_bindings = {
        "base_repository_commit": BASE_COMMIT,
        "hf_challenge_file_sha256": HF_SHA256,
        "frozen_method_file_sha256": FROZEN_METHOD_SHA256,
        "grammar_capsule_file_sha256": CAPSULE_SHA256,
    }
    for field, expected in expected_bindings.items():
        _require(bindings.get(field) == expected, f"source binding {field} differs")
    _require(bindings.get("frozen_method_modified") is False, "frozen v1 must remain unchanged")
    _require(bindings.get("language_version") == "0.1.0", "language version changed")
    _require(_file_sha256(REPO_ROOT / bindings["hf_challenge_path"]) == HF_SHA256, "HF challenge bytes differ")
    _require(_file_sha256(REPO_ROOT / bindings["frozen_method_path"]) == FROZEN_METHOD_SHA256, "frozen method bytes differ")
    _require(_file_sha256(REPO_ROOT / bindings["grammar_capsule_path"]) == CAPSULE_SHA256, "Capsule bytes differ")

    boundary = _object(plan.get("known_result_boundary"), "known_result_boundary")
    _require(boundary.get("general_unfamiliar_agent_saving_percent") == 0.0, "general result must remain 0%")
    _require(boundary.get("safely_completed_real_task_total_token_result") is None, "unknown real-task result must remain null")
    for field in (
        "single_study_changes_general_result",
        "single_study_supports_protocol_version_change",
        "single_study_supports_state_of_the_art_claim",
    ):
        _require(boundary.get(field) is False, f"known result boundary {field} must remain false")

    lineage = _object(plan.get("prior_search_lineage"), "prior_search_lineage")
    _require(lineage.get("status") == "partial", "prior search lineage must remain partial")
    _require(len(_list(lineage.get("prior_rounds_seen"), "prior_rounds_seen")) >= 2, "prior rounds are missing")
    _require(lineage.get("untouched_architecture_selection_claim") is False, "lineage cannot claim untouched selection")

    design = _object(plan.get("study_design"), "study_design")
    _require(tuple(design.get("required_arms", [])) == ARM_IDS, "required arm order differs")
    _require(tuple(design.get("executed_arm_order", [])) == ARM_ORDER, "executed arm order differs")
    _require(design.get("arm_order_randomized") is False, "arm order must be disclosed as fixed")
    _require(
        isinstance(design.get("fixed_order_carryover_risk"), str)
        and bool(design["fixed_order_carryover_risk"].strip()),
        "fixed-order carryover risk is not disclosed",
    )
    _require(tuple(design.get("task_order_within_each_arm", [])) == TASK_IDS, "task order differs")
    _require(design.get("base_receiver_executions") == 6, "exactly six base executions are required")
    _require(tuple(design.get("registered_cumulative_k_curve", [])) == K_VALUES, "K curve must be [1,2]")
    _require(design.get("headline_k") == 2, "headline K must remain 2")
    _require(design.get("publish_every_registered_k") is True, "every registered K must be published")
    _require(design.get("extrapolation_beyond_k2_allowed") is False, "K>2 extrapolation must be disabled")
    _require(design.get("cross_session_amortization_allowed") is False, "cross-session amortization must remain disabled")
    for field in (
        "same_session_within_arm_required",
        "fresh_context_between_arms_required",
        "same_receiver_model_and_settings_required",
        "same_common_response_contract_required",
        "same_task_facts_required",
    ):
        _require(design.get(field) is True, f"study design {field} must be true")
    for field in ("cross_arm_memory_allowed", "tools_allowed", "task_execution_external_effects_allowed"):
        _require(design.get(field) is False, f"study design {field} must be false")

    _validate_hf_task_a(plan)
    tasks = _list(plan.get("tasks"), "tasks")
    _require([item.get("task_id") for item in tasks] == list(TASK_IDS), "task IDs or order differ")
    for task in tasks:
        facts = _object(task.get("facts"), f"{task.get('task_id')}.facts")
        _require(task.get("expected_output") == _expected_from_facts(facts), f"{task.get('task_id')} expected output differs")

    direct = _object(plan.get("direct_consumption_contract"), "direct_consumption_contract")
    _require(direct.get("decode_before_model") is False, "Urusilla must not decode before model")
    _require(direct.get("natural_language_re_expansion") is False, "Urusilla must not expand to natural language")
    _require(direct.get("fallback_cannot_erase_failed_primary_cost") is True, "failed primary cost must remain")

    accounting = _object(plan.get("capture_and_accounting_contract"), "capture_and_accounting_contract")
    _require(tuple(accounting.get("token_phases", [])) == TOKEN_PHASES, "token phases differ")
    for field in (
        "primary_and_declared_fallback_preflight_before_first_dispatch",
        "capture_match_derived_from_equal_message_digests",
        "model_id_and_settings_digest_required_per_dispatched_attempt",
        "provider_request_and_terminal_response_receipts_required",
        "raw_usage_receipt_digest_and_count_source_required_for_finite_usage",
        "capture_mismatch_fail_closed",
        "capture_mismatch_can_never_be_safe_completion",
        "attempt_level_records_required",
        "billed_failed_primary_included",
        "unknown_usage_is_null_not_zero",
        "any_unknown_attempt_usage_makes_task_arm_and_k_totals_null",
    ):
        _require(accounting.get(field) is True, f"accounting contract {field} must be true")

    calibration = _object(plan.get("judge_calibration"), "judge_calibration")
    _require(calibration.get("scorer_receives_arm_identity") is False, "scorer must be arm-blind")
    _require(calibration.get("required_detection_rate_per_arm") == 1.0, "calibration rate must be 100%")
    _require(calibration.get("maximum_between_arm_detection_gap") == 0.0, "calibration gap must be zero")
    fixtures = _list(calibration.get("blinded_fixtures"), "blinded_fixtures")
    _require(
        {item.get("arm_id_revealed_after_scoring"): item.get("blind_id") for item in fixtures} == BLIND_BY_ARM,
        "blinded calibration fixtures differ",
    )

    readback_contract = _object(plan.get("identity_readback_contract"), "identity_readback_contract")
    _require(
        tuple(readback_contract.get("participant_must_return", ()))
        == (
            "experiment_id",
            "preregistration_canonical_sha256",
            "packet_canonical_sha256",
            "grammar_capsule_file_sha256",
        ),
        "identity readback fields differ",
    )
    _require(readback_contract.get("mismatch_disposition") == "null-identity-mismatch", "identity mismatch disposition differs")
    _require(readback_contract.get("digest_match_authenticates_publisher") is False, "digest match cannot authenticate a publisher")
    _require(
        readback_contract.get("public_response_body_encoding")
        == "compact-canonical-json-entire-body",
        "public response body encoding differs",
    )
    _require(
        tuple(readback_contract.get("public_response_exact_fields", ()))
        == PUBLIC_RESPONSE_FIELDS,
        "public response fields differ",
    )
    _require(
        tuple(readback_contract.get("qualifying_response_kinds", ()))
        == PUBLIC_RESPONSE_KINDS,
        "qualifying response kinds differ",
    )
    for field in (
        "identity_mismatch_is_qualifying_negative_evidence",
        "non_identity_mismatch_requires_exact_identity",
        "methodological_counterexample_requires_nonempty_note",
        "selected_fields_must_be_derived_from_public_body",
    ):
        _require(readback_contract.get(field) is True, f"identity readback contract {field} must be true")

    venue = _object(plan.get("outreach_venue"), "outreach_venue")
    _require(venue.get("venue_id") == "the-colony", "registered outreach venue differs")
    _require(venue.get("public_host") == OUTREACH_HOST, "registered outreach host differs")
    _require(venue.get("thread_uri") == OUTREACH_THREAD_URI, "registered outreach thread differs")
    _require(venue.get("registered_parent_comment_id") == OUTREACH_PARENT_COMMENT_ID, "registered parent comment differs")
    _require(venue.get("registered_parent_comment_uri") == OUTREACH_PARENT_COMMENT_URI, "registered parent URI differs")
    _require(venue.get("registered_parent_author_label") == OUTREACH_PARENT_AUTHOR_LABEL, "registered parent author label differs")
    _require(venue.get("registered_parent_author_id") == OUTREACH_PARENT_AUTHOR_ID, "registered parent author ID differs")
    _require(venue.get("registered_publisher_account_label") == OUTREACH_PUBLISHER_ACCOUNT_LABEL, "registered publisher label differs")
    _require(venue.get("registered_publisher_account_id") == OUTREACH_PUBLISHER_ACCOUNT_ID, "registered publisher ID differs")
    _require(
        venue.get("publication_mode") == "one-substantive-reply-to-the-registered-external-comment",
        "registered publication mode differs",
    )
    for field in (
        "new_account_creation_allowed",
        "new_secret_creation_allowed",
        "new_terms_acceptance_allowed",
        "spending_allowed",
    ):
        _require(venue.get(field) is False, f"outreach venue {field} must remain false")

    stop = _object(plan.get("outreach_stop_rule"), "outreach_stop_rule")
    _require(stop.get("deadline_utc") == "2026-08-30T08:00:00Z", "outreach deadline differs")
    _require(stop.get("self_bump_allowed") is False, "self-bump must remain disabled")
    _require(stop.get("registered_initial_event_is_visibility_only_self_bump") is False, "initial substantive reply is not a visibility-only bump")
    _require(type(stop.get("self_bump_definition")) is str and bool(stop["self_bump_definition"].strip()), "self-bump definition is missing")
    _require(stop.get("cross_post_to_multiple_venues_under_this_registration") is False, "registration is single-venue")
    authority = _object(plan.get("authority_boundary"), "authority_boundary")
    _require(authority.get("task_execution_external_effects_authorized") is False, "task effects cannot be authorized")
    _require(authority.get("public_reply_authorized_by_registration") is False, "registration cannot authorize publication")
    _require(authority.get("separately_authorized_publication_receipt_allowed") is True, "separate publication receipt must remain allowed")

    interpretation = _object(plan.get("interpretation"), "interpretation")
    _require(interpretation.get("open_answer_key_copyable") is True, "open-answer-key limitation is missing")
    for field in ("changes_general_zero_percent", "adoption_claim", "independent_reproduction_claim"):
        _require(interpretation.get(field) is False, f"interpretation cannot claim {field}")

    return {
        "valid": True,
        "validation_scope": "structural-content-consistency-only",
        "provider_authenticity_verified": False,
        "invocation_chronology_authenticated": False,
        "experiment_id": EXPERIMENT_ID,
        "canonical_sha256": sha256_ref(plan),
        "network_used": False,
        "provider_calls": 0,
        "base_receiver_executions": 6,
        "registered_k_curve": [1, 2],
        "changes_general_zero_percent": False,
    }


def _payload_facts_json(payload: str) -> dict[str, Any]:
    value = _object(strict_json_loads(payload), "JSON arm payload")
    _exact_keys(
        value,
        ("budget_cents", "network_allowed", "plans", "request", "tie_break"),
        "JSON arm payload",
    )
    _require(
        value["request"]
        == {
            "determine_feasibility": True,
            "external_action": False,
            "preserve_decision_ambiguity_without_tie_break": True,
            "report_remaining_budget_for_each": True,
            "select_plan": True,
        },
        "JSON arm request semantics differ",
    )
    return {
        "budget_cents": value["budget_cents"],
        "network_allowed": value["network_allowed"],
        "tie_break": value["tie_break"],
        "plans": value["plans"],
    }


def _payload_facts_urusilla(payload: str) -> dict[str, Any]:
    value = _object(strict_json_loads(payload), "Urusilla arm payload")
    _require(value.get("act") == "REQUEST", "Urusilla payload act differs")
    _require(value.get("schema") == "urn:urusilla:schema:core:0.1", "Urusilla payload schema differs")
    body = _object(value.get("body"), "Urusilla arm body")
    _require(body.get("kind") == "goal", "Urusilla body kind differs")
    condition = _object(body.get("condition"), "Urusilla arm condition")
    _require(condition.get("kind") == "claim", "Urusilla condition kind differs")
    _require(condition.get("predicate") == "plan.selection.required", "Urusilla predicate differs")
    arguments = _list(condition.get("arguments"), "Urusilla condition arguments")
    _require(len(arguments) == 5, "Urusilla condition argument count differs")
    top = arguments[0]
    plans = arguments[1:3]
    tie = arguments[3]["tie_break"]
    request = _object(arguments[4], "Urusilla request argument")
    _require(
        request
        == {
            "external_action": False,
            "report": [
                "feasibility",
                "selection",
                "remaining-budget-each",
                "decision-ambiguity-without-tie-break",
            ],
        },
        "Urusilla request semantics differ",
    )
    tie_break = {
        "prefer-higher-robustness-when-both-feasible": "prefer-higher-robustness-when-both-feasible",
        "prefer-lower-cost-when-both-feasible": "prefer-lower-cost-when-both-feasible",
    }[tie]
    expected_constraints = [
        {
            "condition": {"budget_cents_lte": top["budget_cents"]},
            "kind": "constraint",
            "mode": "hard",
            "scope": "budget",
        },
        {
            "condition": {"network_allowed": top["network_allowed"]},
            "kind": "constraint",
            "mode": "hard",
            "scope": "network",
        },
        {
            "condition": {
                "tie_break": {
                    "prefer-higher-robustness-when-both-feasible": "higher-robustness",
                    "prefer-lower-cost-when-both-feasible": "lower-cost",
                }[tie_break]
            },
            "kind": "constraint",
            "mode": "soft",
            "scope": "selection",
        },
        {
            "condition": {"external_action": False},
            "kind": "constraint",
            "mode": "hard",
            "scope": "effects",
        },
    ]
    _require(body.get("constraints") == expected_constraints, "Urusilla constraints differ")
    return {
        "budget_cents": top["budget_cents"],
        "network_allowed": top["network_allowed"],
        "tie_break": tie_break,
        "plans": plans,
    }


def score_output_text(output_text: str, expected: Mapping[str, Any]) -> bool:
    if type(output_text) is not str:
        return False
    try:
        parsed = strict_json_loads(output_text)
    except ValidationError:
        return False
    return parsed == expected and output_text == canonical_json(expected)


def _matched_defect_output(expected: Mapping[str, Any]) -> str:
    """Return the one frozen calibration defect without mutating the oracle."""

    _require(
        expected.get("would_execute") is False,
        "calibration oracle must prohibit execution",
    )
    defective = strict_json_loads(canonical_json(expected))
    defective["would_execute"] = True
    return canonical_json(defective)


def _validate_packet_calibration(
    packet: Mapping[str, Any], plan: Mapping[str, Any]
) -> list[Any]:
    calibration = _object(packet.get("calibration"), "packet.calibration")
    _require(
        calibration.get("arm_identity_supplied_to_scorer") is False,
        "packet scorer is not arm-blind",
    )
    fixtures = _list(calibration.get("fixtures"), "packet.calibration.fixtures")
    _require(
        [item.get("blind_id") for item in fixtures]
        == [BLIND_BY_ARM[arm] for arm in ARM_IDS],
        "packet blind fixtures differ",
    )
    task_a_expected = _task_by_id(plan, "task-a")["expected_output"]
    expected_defect = _matched_defect_output(task_a_expected)
    for index, fixture in enumerate(fixtures):
        _exact_keys(
            _object(fixture, f"packet.calibration.fixtures[{index}]"),
            ("blind_id", "defective_output"),
            f"packet.calibration.fixtures[{index}]",
        )
        defective = fixture.get("defective_output")
        _require(
            type(defective) is str
            and defective == canonical_json(strict_json_loads(defective)),
            "defect fixture is not canonical",
        )
        _require(
            defective == expected_defect,
            "calibration fixture must differ only by would_execute false-to-true",
        )
        _require(
            not score_output_text(defective, task_a_expected),
            "known semantic defect was not detected",
        )
    return fixtures


def validate_packet(value: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    validate_preregistration(plan)
    packet = _object(value, "packet")
    _exact_keys(
        packet,
        (
            "schema_version",
            "experiment_id",
            "status",
            "preregistration_path",
            "source_bindings",
            "current_result",
            "participant_action",
            "execution",
            "shared_model_visible",
            "arms",
            "calibration",
            "identity_readback",
            "evidence_requirements",
            "outreach",
            "claim_boundary",
        ),
        "packet",
    )
    _require(packet.get("schema_version") == PACKET_SCHEMA, "packet schema differs")
    _require(packet.get("experiment_id") == EXPERIMENT_ID, "packet experiment differs")
    _require(packet.get("status") == "public-prerun-packet", "packet status differs")
    _require(packet.get("preregistration_path") == "interop_lab/challenges/solicited_matched_001.preregistration.json", "packet preregistration path differs")
    _require(sha256_ref(packet) == PACKET_CANONICAL_SHA256, "packet canonical digest differs")
    _require(_file_sha256(PACKET_PATH) == PACKET_FILE_SHA256, "packet file bytes differ")
    bindings = _object(packet.get("source_bindings"), "packet.source_bindings")
    for field, expected in {
        "base_repository_commit": BASE_COMMIT,
        "hf_challenge_file_sha256": HF_SHA256,
        "frozen_method_file_sha256": FROZEN_METHOD_SHA256,
        "grammar_capsule_file_sha256": CAPSULE_SHA256,
    }.items():
        _require(bindings.get(field) == expected, f"packet binding {field} differs")
    current = _object(packet.get("current_result"), "packet.current_result")
    _require(current.get("general_unfamiliar_agent_saving_percent") == 0.0, "packet must disclose 0%")
    _require(current.get("safely_completed_real_task_total_token_result") is None, "packet real-task result must be null")
    _require(current.get("negative_null_refusal_and_fallback_results_welcome") is True, "packet must retain negative and null results")
    action = _object(packet.get("participant_action"), "packet.participant_action")
    for field in (
        "installation_required",
        "submitted_code_execution_required",
        "task_external_effect_required",
        "publication_authorized_by_packet",
    ):
        _require(action.get(field) is False, f"packet participant action {field} must remain false")
    execution = _object(packet.get("execution"), "packet.execution")
    _require(tuple(execution.get("arm_order", [])) == ARM_ORDER, "packet arm order differs")
    _require(execution.get("arm_order_randomized") is False, "packet arm order must be disclosed as fixed")
    _require(
        isinstance(execution.get("fixed_order_carryover_disclosure"), str)
        and bool(execution["fixed_order_carryover_disclosure"].strip()),
        "packet fixed-order carryover disclosure is missing",
    )
    _require(tuple(execution.get("task_order_within_arm", [])) == TASK_IDS, "packet task order differs")
    _require(execution.get("expected_base_receiver_executions") == 6, "packet must declare six base executions")
    _require(tuple(execution.get("registered_cumulative_k_curve", [])) == K_VALUES, "packet K curve differs")

    arms = _list(packet.get("arms"), "packet.arms")
    _require([arm.get("arm_id") for arm in arms] == list(ARM_IDS), "packet arms differ")
    for arm in arms:
        arm_id = arm["arm_id"]
        tasks = _list(arm.get("tasks"), f"packet.{arm_id}.tasks")
        _require([task.get("task_id") for task in tasks] == list(TASK_IDS), f"{arm_id} task order differs")
        for task in tasks:
            task_id = task["task_id"]
            facts = _task_by_id(plan, task_id)["facts"]
            payload = task["model_visible_payload"]
            if arm_id == "json":
                _require(_payload_facts_json(payload) == facts, f"JSON {task_id} semantics differ")
                _require(payload == canonical_json(strict_json_loads(payload)), f"JSON {task_id} is not canonical")
            elif arm_id == "urusilla":
                _require(_payload_facts_urusilla(payload) == facts, f"Urusilla {task_id} semantics differ")
                _require(payload == canonical_json(strict_json_loads(payload)), f"Urusilla {task_id} is not canonical")
            else:
                _require(type(payload) is str and payload, f"raw {task_id} is empty")
        if arm_id == "urusilla":
            direct = _object(arm.get("direct_consumption"), "packet.urusilla.direct_consumption")
            _require(direct.get("decode_before_model") is False, "packet would decode before model")
            _require(direct.get("natural_language_re_expansion") is False, "packet permits an NL expansion")
            setup = _object(arm.get("session_setup"), "packet.urusilla.session_setup")
            _require(setup.get("artifact_sha256") == CAPSULE_SHA256, "packet Capsule identity differs")
            _require(setup.get("charge_once_at_session_open") is True, "Capsule must be charged once")
        else:
            _require("Urusilla Capsule" in arm["session_setup"]["model_visible_text"], f"{arm_id} setup boundary is missing")

    fixtures = _validate_packet_calibration(packet, plan)
    identity = _object(packet.get("identity_readback"), "packet.identity_readback")
    _require(
        tuple(identity.get("required_fields", ()))
        == IDENTITY_RESPONSE_FIELDS,
        "packet identity readback fields differ",
    )
    _require(identity.get("digest_match_is_not_authentication") is True, "packet digest match cannot authenticate")
    _require(
        identity.get("public_response_body_encoding")
        == "compact-canonical-json-entire-body",
        "packet public response encoding differs",
    )
    _require(
        tuple(identity.get("public_response_exact_fields", ()))
        == PUBLIC_RESPONSE_FIELDS,
        "packet public response fields differ",
    )
    _require(
        tuple(identity.get("qualifying_response_kinds", ()))
        == PUBLIC_RESPONSE_KINDS,
        "packet qualifying response kinds differ",
    )
    for field in (
        "identity_mismatch_is_qualifying_negative_evidence",
        "non_identity_mismatch_requires_exact_identity",
        "methodological_counterexample_requires_nonempty_note",
        "selected_fields_must_be_derived_from_public_body",
    ):
        _require(identity.get(field) is True, f"packet identity contract {field} must be true")
    _require(packet["outreach"]["self_bump"] is False, "packet permits a self-bump")
    outreach = _object(packet.get("outreach"), "packet.outreach")
    _require(outreach.get("single_venue") is True, "packet is not single-venue")
    _require(outreach.get("venue_id") == "the-colony", "packet outreach venue differs")
    _require(outreach.get("public_host") == OUTREACH_HOST, "packet outreach host differs")
    _require(outreach.get("thread_uri") == OUTREACH_THREAD_URI, "packet outreach thread differs")
    _require(outreach.get("registered_parent_comment_id") == OUTREACH_PARENT_COMMENT_ID, "packet parent comment differs")
    _require(outreach.get("registered_parent_comment_uri") == OUTREACH_PARENT_COMMENT_URI, "packet parent URI differs")
    _require(outreach.get("registered_parent_author_label") == OUTREACH_PARENT_AUTHOR_LABEL, "packet parent author label differs")
    _require(outreach.get("registered_parent_author_id") == OUTREACH_PARENT_AUTHOR_ID, "packet parent author ID differs")
    _require(outreach.get("registered_publisher_account_label") == OUTREACH_PUBLISHER_ACCOUNT_LABEL, "packet publisher label differs")
    _require(outreach.get("registered_publisher_account_id") == OUTREACH_PUBLISHER_ACCOUNT_ID, "packet publisher ID differs")
    _require(outreach.get("registered_initial_event_is_visibility_only_self_bump") is False, "packet initial event is not a visibility-only bump")

    evidence = _object(packet.get("evidence_requirements"), "packet.evidence_requirements")
    _require(all(value is True for value in evidence.values()), "packet evidence requirements must remain enabled")
    claim_boundary = _object(packet.get("claim_boundary"), "packet.claim_boundary")
    _require(claim_boundary.get("open_answer_key_copyable") is True, "packet open-answer-key limitation is missing")
    for field in (
        "changes_general_zero_percent",
        "efficiency_claim_eligible",
        "independent_reproduction_claim",
        "adoption_claim",
        "protocol_version_change_claim",
        "state_of_the_art_claim",
    ):
        _require(claim_boundary.get(field) is False, f"packet cannot claim {field}")

    return {
        "valid": True,
        "experiment_id": EXPERIMENT_ID,
        "canonical_sha256": sha256_ref(packet),
        "network_used": False,
        "provider_calls": 0,
        "known_defects_detected": len(fixtures),
        "direct_consumption": True,
    }


def _validate_ledger(value: Any, path: str) -> dict[str, int | None]:
    ledger = _object(value, path)
    _exact_keys(ledger, LEDGER_FIELDS, path)
    phases = [_nullable_count(ledger[field], f"{path}.{field}") for field in TOKEN_PHASES]
    total = _nullable_count(ledger["total"], f"{path}.total")
    if all(item is not None for item in phases):
        _require(total == sum(item for item in phases if item is not None), f"{path}.total does not reconcile")
    else:
        _require(total is None, f"{path}.total must be null when any phase is unknown")
    return ledger


def _sum_ledgers(ledgers: Sequence[Mapping[str, int | None]]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for field in TOKEN_PHASES:
        values = [ledger[field] for ledger in ledgers]
        result[field] = None if any(value is None for value in values) else sum(values)  # type: ignore[arg-type]
    result["total"] = (
        None
        if any(result[field] is None for field in TOKEN_PHASES)
        else sum(result[field] for field in TOKEN_PHASES)  # type: ignore[arg-type]
    )
    return result


def _validate_attempt(value: Any, path: str, expected_index: int) -> dict[str, Any]:
    attempt = _object(value, path)
    _exact_keys(
        attempt,
        (
            "attempt_index",
            "attempt_kind",
            "parent_attempt_index",
            "request_dispatched",
            "billed",
            "status",
            "request_sha256",
            "intended_messages_sha256",
            "transmitted_messages_sha256",
            "capture_match",
            "provider_request_id",
            "provider_response_id",
            "model_id",
            "settings_sha256",
            "response_sha256",
            "failure_code",
            "raw_usage_receipt_sha256",
            "token_count_source",
            "token_ledger",
        ),
        path,
    )
    _require(attempt["attempt_index"] == expected_index, f"{path} index differs")
    _require(attempt["attempt_kind"] in ATTEMPT_KINDS, f"{path} kind is unknown")
    parent = attempt["parent_attempt_index"]
    if attempt["attempt_kind"] == "primary":
        _require(parent is None, f"{path} primary cannot have a parent")
    else:
        _require(
            type(parent) is int and 1 <= parent < expected_index,
            f"{path} retry, repair, or fallback must reference an earlier parent attempt",
        )
    _require(type(attempt["request_dispatched"]) is bool, f"{path}.request_dispatched must be boolean")
    _nullable_bool(attempt["billed"], f"{path}.billed")
    _require(attempt["status"] in ATTEMPT_STATUSES, f"{path} status is unknown")
    _sha(attempt["request_sha256"], f"{path}.request_sha256")
    intended = _sha(attempt["intended_messages_sha256"], f"{path}.intended_messages_sha256")
    transmitted = _sha(attempt["transmitted_messages_sha256"], f"{path}.transmitted_messages_sha256", nullable=True)
    _nullable_bool(attempt["capture_match"], f"{path}.capture_match")
    response_digest = _sha(attempt["response_sha256"], f"{path}.response_sha256", nullable=True)
    for field in ("provider_request_id", "provider_response_id", "model_id"):
        if attempt[field] is not None:
            _require(type(attempt[field]) is str and bool(attempt[field].strip()), f"{path}.{field} is invalid")
    settings_digest = _sha(attempt["settings_sha256"], f"{path}.settings_sha256", nullable=True)
    usage_receipt = _sha(
        attempt["raw_usage_receipt_sha256"],
        f"{path}.raw_usage_receipt_sha256",
        nullable=True,
    )
    source = attempt["token_count_source"]
    _require(source in TOKEN_COUNT_SOURCES, f"{path}.token_count_source is unknown")
    if attempt["failure_code"] is not None:
        _require(type(attempt["failure_code"]) is str and attempt["failure_code"], f"{path}.failure_code is invalid")
    if attempt["status"] == "completed":
        _require(attempt["failure_code"] is None, f"{path} completed attempt cannot have a failure code")
    else:
        _require(attempt["failure_code"] is not None, f"{path} terminal non-completion requires a failure code")
    ledger = _validate_ledger(attempt["token_ledger"], f"{path}.token_ledger")

    dispatched = attempt["request_dispatched"]
    if dispatched:
        _require(transmitted is not None, f"{path} dispatched without transmitted-message evidence")
        _require(attempt["provider_request_id"] is not None, f"{path} dispatched without provider request ID")
        _require(attempt["model_id"] is not None, f"{path} dispatched without actual model ID")
        _require(settings_digest is not None, f"{path} dispatched without settings digest")
        _require(attempt["status"] != "before-dispatch-failure", f"{path} dispatched with a before-dispatch status")
        _require(
            attempt["capture_match"] is (intended == transmitted),
            f"{path}.capture_match must be derived from intended/transmitted digest equality",
        )
    else:
        _require(attempt["status"] == "before-dispatch-failure", f"{path} non-dispatch must be a before-dispatch failure")
        _require(transmitted is None, f"{path} non-dispatch cannot claim transmitted messages")
        _require(attempt["capture_match"] is None, f"{path} non-dispatch capture result must be null")
        _require(attempt["provider_request_id"] is None, f"{path} non-dispatch cannot claim a provider request")
        _require(attempt["provider_response_id"] is None, f"{path} non-dispatch cannot claim a provider response")
        _require(attempt["model_id"] is None, f"{path} non-dispatch cannot claim an actual model")
        _require(settings_digest is None, f"{path} non-dispatch cannot claim actual settings")
        _require(response_digest is None, f"{path} non-dispatch cannot claim a response")
        _require(attempt["billed"] is not True, f"{path} non-dispatch cannot claim provider billing")

    if attempt["status"] in {"completed", "refused"}:
        _require(dispatched, f"{path} {attempt['status']} without dispatch")
        _require(attempt["capture_match"] is True, f"{path} {attempt['status']} without matched capture")
        _require(response_digest is not None, f"{path} {attempt['status']} without response digest")
        _require(attempt["provider_response_id"] is not None, f"{path} {attempt['status']} without provider response ID")
    elif response_digest is None:
        _require(
            attempt["status"] in NO_RESPONSE_ALLOWED_STATUSES,
            f"{path} response may be absent only for a terminal failure",
        )
        _require(attempt["provider_response_id"] is None, f"{path} response ID exists without a response")
    else:
        _require(attempt["provider_response_id"] is not None, f"{path} response digest lacks provider response ID")

    if ledger["total"] is not None:
        _require(source != "unknown", f"{path} finite ledger has unknown count source")
        _require(usage_receipt is not None, f"{path} finite ledger lacks raw usage receipt")
    if source == "unknown" or usage_receipt is None:
        _require(ledger["total"] is None, f"{path} unknown or receipt-free usage must poison total")
    if attempt["status"] == "capture-rejected":
        _require(attempt["capture_match"] is False, f"{path} rejected capture must mismatch")
    if attempt["capture_match"] is False:
        _require(attempt["status"] == "capture-rejected", f"{path} mismatch must fail closed")
    if attempt["billed"] is True and ledger["total"] is None:
        # This is valid evidence, but its unknown usage must poison all totals.
        pass
    return attempt


def _expected_execution_pairs() -> list[tuple[str, str]]:
    return [(arm, task) for arm in ARM_ORDER for task in TASK_IDS]


def _validate_execution_result(
    item: Any,
    path: str,
    expected_arm: str,
    expected_task: str,
    expected_output: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, int | None] | None]:
    execution = _object(item, path)
    _require(execution.get("execution_id") == f"{expected_arm}-{expected_task}", f"{path}.execution_id differs")
    _require(execution.get("arm_id") == expected_arm, f"{path}.arm_id differs")
    _require(execution.get("task_id") == expected_task, f"{path}.task_id differs")
    attempted = execution.get("attempted")
    _require(type(attempted) is bool, f"{path}.attempted must be boolean")
    attempts = _list(execution.get("attempts"), f"{path}.attempts")
    if not attempted:
        _require(attempts == [], f"{path} unattempted execution has attempts")
        _require(execution.get("session_id") is None, f"{path} unattempted session must be null")
        _require(execution.get("token_ledger") is None, f"{path} unattempted ledger must be null")
        _require(execution.get("final_output_text") is None, f"{path} unattempted output must be null")
        _require(execution.get("final_output_sha256") is None, f"{path} unattempted output digest must be null")
        for field in (
            "parse_valid",
            "semantic_fidelity",
            "task_success",
            "safe_completion",
            "capture_chain_valid",
            "fallback_used",
        ):
            _require(execution.get(field) is None, f"{path} unattempted {field} must be null")
        return execution, None

    _require(type(execution.get("session_id")) is str and execution["session_id"], f"{path}.session_id is required")
    validated_attempts = [
        _validate_attempt(attempt, f"{path}.attempts[{index}]", index + 1)
        for index, attempt in enumerate(attempts)
    ]
    primary = [attempt for attempt in validated_attempts if attempt["attempt_kind"] == "primary"]
    _require(len(primary) == 1, f"{path} must retain exactly one base primary attempt")
    _require(validated_attempts[0]["attempt_kind"] == "primary", f"{path} primary must be first")
    expected_ledger = _sum_ledgers([attempt["token_ledger"] for attempt in validated_attempts])
    observed_ledger = _validate_ledger(execution.get("token_ledger"), f"{path}.token_ledger")
    _require(observed_ledger == expected_ledger, f"{path} task ledger omits or duplicates attempt cost")

    final_text = execution.get("final_output_text")
    final_digest = execution.get("final_output_sha256")
    if final_text is None:
        _require(final_digest is None, f"{path} output digest exists without text")
        scored = False
    else:
        _require(type(final_text) is str, f"{path}.final_output_text must be text or null")
        _require(final_digest == sha256_ref(final_text), f"{path} output digest differs")
        scored = score_output_text(final_text, expected_output)
    for field in ("parse_valid", "semantic_fidelity", "task_success", "safe_completion", "capture_chain_valid", "fallback_used"):
        _nullable_bool(execution.get(field), f"{path}.{field}")
    if final_text is not None:
        _require(execution.get("parse_valid") is scored, f"{path}.parse_valid differs from exact scorer")
        _require(execution.get("semantic_fidelity") is scored, f"{path}.semantic_fidelity differs from exact scorer")
        _require(execution.get("task_success") is scored, f"{path}.task_success differs from exact scorer")
        completed_responses = {
            attempt["response_sha256"]
            for attempt in validated_attempts
            if attempt["status"] == "completed"
        }
        _require(
            final_digest in completed_responses,
            f"{path} final output is not bound to a completed provider response",
        )
    else:
        for field in ("parse_valid", "semantic_fidelity", "task_success"):
            _require(execution.get(field) is not True, f"{path} no-output {field} cannot be true")
        _require(execution.get("safe_completion") is False, f"{path} no-output execution cannot be safe")
    capture_valid = all(attempt["capture_match"] is True for attempt in validated_attempts)
    _require(execution.get("capture_chain_valid") is capture_valid, f"{path}.capture_chain_valid differs")
    if not capture_valid:
        _require(execution.get("safe_completion") is False, f"{path} capture mismatch cannot be safe")
    elif execution.get("safe_completion") is True:
        _require(scored, f"{path} safe completion lacks exact task success")
    fallback_present = any(attempt["attempt_kind"] == "fallback" for attempt in validated_attempts)
    _require(execution.get("fallback_used") is fallback_present, f"{path}.fallback_used differs")
    if any(attempt["billed"] is True and attempt["status"] != "completed" for attempt in validated_attempts):
        _require(observed_ledger == expected_ledger, f"{path} billed failed primary cost is missing")
    return execution, observed_ledger


def _replay_calibration(
    packet: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, int]:
    calibration = _object(packet.get("calibration"), "packet.calibration")
    fixtures = _list(calibration.get("fixtures"), "packet.calibration.fixtures")
    by_blind_id = {
        _object(item, f"packet.calibration.fixtures[{index}]")["blind_id"]: item
        for index, item in enumerate(fixtures)
    }
    expected = _task_by_id(plan, "task-a")["expected_output"]
    replayed: dict[str, int] = {}
    for arm in ARM_IDS:
        fixture = by_blind_id[BLIND_BY_ARM[arm]]
        # Arm identity is deliberately not an input to the deterministic scorer.
        replayed[arm] = int(
            not score_output_text(fixture["defective_output"], expected)
        )
    return replayed


def _calibration_state(
    value: Any,
    packet: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> tuple[bool | None, dict[str, bool]]:
    calibration = _object(value, "judge_calibration")
    _exact_keys(
        calibration,
        (
            "scorer",
            "arm_identity_supplied_to_scorer",
            "results",
            "maximum_between_arm_gap",
            "passed",
        ),
        "judge_calibration",
    )
    _require(calibration.get("scorer") == "deterministic-exact-canonical-json", "calibration scorer differs")
    _require(calibration.get("arm_identity_supplied_to_scorer") is False, "calibration scorer received arm identity")
    replayed = _replay_calibration(packet, plan)
    results = _list(calibration.get("results"), "judge_calibration.results")
    by_arm: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(results):
        result = _object(item, f"judge_calibration.results[{index}]")
        _exact_keys(
            result,
            (
                "blind_id",
                "arm_id",
                "known_positive_total",
                "defects_detected",
                "detection_rate",
            ),
            f"judge_calibration.results[{index}]",
        )
        arm = result.get("arm_id")
        _require(arm in ARM_IDS and arm not in by_arm, "calibration has an unknown or duplicate arm")
        _require(result.get("blind_id") == BLIND_BY_ARM[arm], "calibration blind identity differs")
        _require(result.get("known_positive_total") == 1, "calibration known-positive total differs")
        detected = result.get("defects_detected")
        rate = result.get("detection_rate")
        if detected is None:
            _require(rate is None, "missing calibration detection must keep rate null")
        else:
            _require(type(detected) is int and 0 <= detected <= 1, "calibration detection count is invalid")
            _require(
                detected == replayed[arm],
                "calibration detection count differs from deterministic replay",
            )
            _require(
                rate == float(replayed[arm]),
                "calibration detection rate differs from deterministic replay",
            )
        by_arm[arm] = result
    complete = set(by_arm) == set(ARM_IDS) and all(by_arm[arm]["defects_detected"] is not None for arm in ARM_IDS)
    if not complete:
        expected_passed: bool | None = None if not any(item.get("defects_detected") is not None for item in results) else False
        _require(calibration.get("passed") is expected_passed, "incomplete calibration verdict differs")
        _require(calibration.get("maximum_between_arm_gap") is None, "incomplete calibration gap must be null")
        return expected_passed, {arm: False for arm in ARM_IDS}
    rates = [float(replayed[arm]) for arm in ARM_IDS]
    gap = max(rates) - min(rates)
    passed = all(rate == 1.0 for rate in rates) and gap == 0.0
    _require(calibration.get("maximum_between_arm_gap") == gap, "calibration gap differs")
    _require(calibration.get("passed") is passed, "calibration verdict differs")
    return passed, {arm: passed for arm in ARM_IDS}


def render_outreach_body(registration_commit: str) -> str:
    _require(
        type(registration_commit) is str
        and COMMIT_RE.fullmatch(registration_commit) is not None,
        "outreach renderer requires a full registration commit",
    )
    preregistration_uri = _github_blob_uri(
        registration_commit,
        "interop_lab/challenges/solicited_matched_001.preregistration.json",
    )
    packet_uri = _github_blob_uri(
        registration_commit,
        "interop_lab/challenges/solicited_matched_001.packet.json",
    )
    response_fields = ", ".join(PUBLIC_RESPONSE_FIELDS)
    return "\n".join(
        (
            "Thanks, ColonistOne — your 313-platform map gave us a bounded venue set to verify.",
            "",
            "Independent read-only checks found that culture.sbs, 1f916, and 4claw require a new persistent credential; Moltbook also adds human verification and material content/data-license terms. To stay inside the no-new-account, no-new-secret, no-new-terms, and no-spend boundary, this is one registered experiment in the existing thread, not a cross-post campaign.",
            "",
            "Current evidence is 0% general unfamiliar-agent token saving, and total tokens per safely completed real task remain null/unknown. This run is PROJECT-SOLICITED. It is not independent reproduction, adoption, a protocol-version result, an efficiency claim, or a state-of-the-art claim.",
            "",
            "Question: can one unfamiliar agent directly consume a declarative Capsule without installation, injected execution code, model retraining, or natural-language re-expansion, while matched raw text and ordinary JSON remain available as baselines?",
            "",
            f"Preregistration: {preregistration_uri}",
            f"Packet: {packet_uri}",
            f"Preregistration canonical SHA-256: {PREREG_CANONICAL_SHA256}",
            f"Preregistration file SHA-256: {PREREG_FILE_SHA256}",
            f"Packet canonical SHA-256: {PACKET_CANONICAL_SHA256}",
            f"Packet file SHA-256: {PACKET_FILE_SHA256}",
            f"Grammar Capsule file SHA-256: {CAPSULE_SHA256}",
            "",
            "Method: run JSON → Urusilla → concise raw text, with two frozen tasks per arm, the same model/settings, one session within each arm, fresh context between arms, and the complete K=[1,2] curve. Charge the exact Capsule once at the Urusilla session open. Capture intended and transmitted bytes; bill failed primaries, setup, reasoning, output, repair, fallback, safety, and judge usage. Any unknown usage keeps efficiency null. Task execution itself permits no tools, network, persistence, spending, permission expansion, or external effect.",
            "",
            "A public answer is qualifying only when its entire body is one compact canonical JSON object with exactly these keys: "
            + response_fields
            + ". response_kind must be matched-result, refusal, null, fallback, identity-mismatch, or methodological-counterexample. Return the four observed identity values; for identity-mismatch, do not replace them with the expected values. response_note may be null, but must explain a methodological-counterexample.",
            "",
            "Negative, null, fallback, refusal, identity-mismatch, malformed, and methodological-counterexample evidence is welcome and retained. Public answer keys are copyable, so task success alone does not prove direct representation consumption.",
            "",
            "Stop rule: first qualifying public response or 2026-08-30T08:00:00Z, whichever comes first. There will be no later visibility-only self-bump and no cross-post under this registration. The packet authorizes no publication or other external action.",
        )
    )


def build_outreach_manifest(registration_commit: str) -> dict[str, Any]:
    body = render_outreach_body(registration_commit)
    return {
        "schema_version": OUTREACH_BODY_SCHEMA,
        "renderer_version": OUTREACH_RENDERER_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "registration_commit": registration_commit,
        "expected_parent_commit": registration_commit,
        "preregistration_uri": _github_blob_uri(
            registration_commit,
            "interop_lab/challenges/solicited_matched_001.preregistration.json",
        ),
        "packet_uri": _github_blob_uri(
            registration_commit,
            "interop_lab/challenges/solicited_matched_001.packet.json",
        ),
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "preregistration_file_sha256": PREREG_FILE_SHA256,
        "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
        "packet_file_sha256": PACKET_FILE_SHA256,
        "grammar_capsule_file_sha256": CAPSULE_SHA256,
        "venue_id": "the-colony",
        "thread_uri": OUTREACH_THREAD_URI,
        "parent_comment_id": OUTREACH_PARENT_COMMENT_ID,
        "parent_comment_uri": OUTREACH_PARENT_COMMENT_URI,
        "parent_author_label": OUTREACH_PARENT_AUTHOR_LABEL,
        "parent_author_id": OUTREACH_PARENT_AUTHOR_ID,
        "publisher_account_label": OUTREACH_PUBLISHER_ACCOUNT_LABEL,
        "publisher_account_id": OUTREACH_PUBLISHER_ACCOUNT_ID,
        "body_text": body,
        "body_sha256": sha256_ref(body),
        "body_utf8_bytes": len(body.encode("utf-8")),
    }


def publication_intent_sha256(
    registration_commit: str,
    body_manifest_commit: str,
    body_manifest_file_sha256: str,
    body_sha256: str,
) -> str:
    return sha256_ref(
        {
            "authorization_scope": "one-substantive-reply-to-registered-external-comment",
            "body_manifest_commit": body_manifest_commit,
            "body_manifest_file_sha256": body_manifest_file_sha256,
            "body_sha256": body_sha256,
            "parent_comment_id": OUTREACH_PARENT_COMMENT_ID,
            "publisher_account_id": OUTREACH_PUBLISHER_ACCOUNT_ID,
            "publisher_account_label": OUTREACH_PUBLISHER_ACCOUNT_LABEL,
            "registration_commit": registration_commit,
            "thread_uri": OUTREACH_THREAD_URI,
            "venue_id": "the-colony",
        }
    )


def public_comment_record_sha256(
    *,
    comment_id: str,
    parent_id: str,
    author_label: str,
    author_id: str,
    body_sha256: str,
    public_uri: str,
    observed_at_utc: str,
) -> str:
    return sha256_ref(
        {
            "author_id": author_id,
            "author_label": author_label,
            "body_sha256": body_sha256,
            "comment_id": comment_id,
            "observed_at_utc": observed_at_utc,
            "parent_id": parent_id,
            "public_uri": public_uri,
        }
    )


def _parse_public_response_body(body: str) -> dict[str, Any]:
    _require(
        len(body.encode("utf-8")) <= MAX_PUBLIC_BODY_UTF8_BYTES,
        "external response body exceeds the registered byte limit",
    )
    try:
        envelope = _object(strict_json_loads(body), "external response body")
    except (ValidationError, ValueError) as exc:
        raise ValidationError("external response body must be one strict JSON object") from exc
    _exact_keys(envelope, PUBLIC_RESPONSE_FIELDS, "external response body")
    _require(body == canonical_json(envelope), "external response body must be compact canonical JSON")
    _require(type(envelope.get("experiment_id")) is str, "external response experiment ID must be text")
    for field in (
        "grammar_capsule_file_sha256",
        "packet_canonical_sha256",
        "preregistration_canonical_sha256",
    ):
        _sha(envelope.get(field), f"external response body.{field}")
    _require(
        envelope.get("response_kind") in RESULT_STATUSES - {"not-run"},
        "external response body kind is not qualifying",
    )
    note = envelope.get("response_note")
    _require(note is None or (type(note) is str and bool(note.strip())), "external response note must be nonempty text or null")
    if envelope.get("response_kind") == "methodological-counterexample":
        _require(type(note) is str and bool(note.strip()), "methodological counterexample requires a response note")
    return envelope


def _validate_outreach_body_manifest(value: Any, registration_commit: str) -> dict[str, Any]:
    manifest = _object(value, "outreach body manifest")
    _exact_keys(
        manifest,
        (
            "schema_version",
            "renderer_version",
            "experiment_id",
            "registration_commit",
            "expected_parent_commit",
            "preregistration_uri",
            "packet_uri",
            "preregistration_canonical_sha256",
            "preregistration_file_sha256",
            "packet_canonical_sha256",
            "packet_file_sha256",
            "grammar_capsule_file_sha256",
            "venue_id",
            "thread_uri",
            "parent_comment_id",
            "parent_comment_uri",
            "parent_author_label",
            "parent_author_id",
            "publisher_account_label",
            "publisher_account_id",
            "body_text",
            "body_sha256",
            "body_utf8_bytes",
        ),
        "outreach body manifest",
    )
    _require(manifest.get("schema_version") == OUTREACH_BODY_SCHEMA, "outreach body schema differs")
    _require(manifest.get("renderer_version") == OUTREACH_RENDERER_VERSION, "outreach body renderer differs")
    _require(manifest.get("experiment_id") == EXPERIMENT_ID, "outreach body experiment differs")
    _require(manifest.get("registration_commit") == registration_commit, "outreach body registration commit differs")
    _require(manifest.get("expected_parent_commit") == registration_commit, "outreach body expected parent commit differs")
    _require(
        manifest.get("preregistration_uri")
        == _github_blob_uri(registration_commit, "interop_lab/challenges/solicited_matched_001.preregistration.json"),
        "outreach body preregistration URI differs",
    )
    _require(
        manifest.get("packet_uri")
        == _github_blob_uri(registration_commit, "interop_lab/challenges/solicited_matched_001.packet.json"),
        "outreach body packet URI differs",
    )
    for field, expected in {
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "preregistration_file_sha256": PREREG_FILE_SHA256,
        "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
        "packet_file_sha256": PACKET_FILE_SHA256,
        "grammar_capsule_file_sha256": CAPSULE_SHA256,
    }.items():
        _require(manifest.get(field) == expected, f"outreach body {field} differs")
    _require(manifest.get("venue_id") == "the-colony", "outreach body venue differs")
    _require(manifest.get("thread_uri") == OUTREACH_THREAD_URI, "outreach body thread differs")
    _require(manifest.get("parent_comment_id") == OUTREACH_PARENT_COMMENT_ID, "outreach body parent differs")
    _require(manifest.get("parent_comment_uri") == OUTREACH_PARENT_COMMENT_URI, "outreach body parent URI differs")
    _require(manifest.get("parent_author_label") == OUTREACH_PARENT_AUTHOR_LABEL, "outreach body parent author label differs")
    _require(manifest.get("parent_author_id") == OUTREACH_PARENT_AUTHOR_ID, "outreach body parent author ID differs")
    _require(manifest.get("publisher_account_label") == OUTREACH_PUBLISHER_ACCOUNT_LABEL, "outreach body publisher label differs")
    _require(manifest.get("publisher_account_id") == OUTREACH_PUBLISHER_ACCOUNT_ID, "outreach body publisher ID differs")
    body = manifest.get("body_text")
    _require(type(body) is str and bool(body.strip()), "outreach body text is empty")
    _require(body == render_outreach_body(registration_commit), "outreach body differs from the deterministic renderer")
    _require(manifest.get("body_sha256") == sha256_ref(body), "outreach body digest differs")
    _require(manifest.get("body_utf8_bytes") == len(body.encode("utf-8")), "outreach body byte count differs")
    _require(
        manifest["body_utf8_bytes"] <= MAX_PUBLIC_BODY_UTF8_BYTES,
        "outreach body exceeds the venue byte limit",
    )
    return manifest


def validate_outreach_manifest(value: Any, registration_commit: str) -> dict[str, Any]:
    manifest = _validate_outreach_body_manifest(value, registration_commit)
    return {
        "valid": True,
        "validation_scope": "deterministic-local-content-consistency-only",
        "experiment_id": EXPERIMENT_ID,
        "registration_commit": registration_commit,
        "renderer_version": OUTREACH_RENDERER_VERSION,
        "body_sha256": manifest["body_sha256"],
        "body_utf8_bytes": manifest["body_utf8_bytes"],
        "network_used": False,
        "publication_authorized": False,
    }


def _validate_publication(value: Any, bindings: Mapping[str, Any]) -> dict[str, Any]:
    publication = _object(value, "publication")
    _exact_keys(
        publication,
        (
            "performed",
            "separate_authorization_attested",
            "authorization_scope",
            "authorization_intent_sha256",
            "authorized_at_utc",
            "venue",
            "public_host",
            "thread_uri",
            "parent_comment_id",
            "parent_comment_uri",
            "publisher_account_label",
            "publisher_account_id",
            "public_uri",
            "public_comment_id",
            "platform_published_at_utc",
            "body_manifest_path",
            "body_manifest_commit",
            "body_manifest_parent_commit",
            "body_manifest_public_uri",
            "body_manifest_file_sha256",
            "body_manifest_public_file_sha256",
            "body_manifest_public_readback_observed_at_utc",
            "submitted_body_text",
            "submitted_body_sha256",
            "submitted_body_utf8_bytes",
            "submitted_body_matches_manifest",
            "readback_uri",
            "readback_body_text",
            "readback_sha256",
            "readback_utf8_bytes",
            "readback_exact_match",
            "readback_observed_at_utc",
            "readback_method",
            "readback_unauthenticated",
            "public_persistence_created",
            "client_tool_used",
            "new_account_created",
            "new_secret_created",
            "new_terms_accepted",
            "spending_performed",
            "platform_receipt",
        ),
        "publication",
    )
    performed = publication.get("performed")
    _require(type(performed) is bool, "publication.performed must be boolean")
    action_fields = (
        "public_persistence_created",
        "client_tool_used",
        "new_account_created",
        "new_secret_created",
        "new_terms_accepted",
        "spending_performed",
    )
    for field in action_fields:
        _require(type(publication.get(field)) is bool, f"publication.{field} must be boolean")
    if not performed:
        _require(publication.get("separate_authorization_attested") is False, "unperformed publication cannot claim authorization")
        for field in set(publication) - {"performed", "separate_authorization_attested", *action_fields}:
            _require(publication.get(field) is None, f"unperformed publication.{field} must be null")
        _require(not any(publication[field] for field in action_fields), "unperformed publication cannot record actions")
        return publication

    _require(publication.get("separate_authorization_attested") is True, "publication requires separate authorization")
    _require(
        publication.get("authorization_scope") == "one-substantive-reply-to-registered-external-comment",
        "publication authorization scope differs",
    )
    _utc_timestamp(publication.get("authorized_at_utc"), "publication.authorized_at_utc")
    _require(publication.get("venue") == "The Colony", "publication venue differs")
    _require(publication.get("public_host") == OUTREACH_HOST, "publication host differs")
    _require(publication.get("thread_uri") == OUTREACH_THREAD_URI, "publication thread differs")
    _require(publication.get("parent_comment_id") == OUTREACH_PARENT_COMMENT_ID, "publication parent comment differs")
    _require(publication.get("parent_comment_uri") == OUTREACH_PARENT_COMMENT_URI, "publication parent URI differs")
    publisher_label = publication.get("publisher_account_label")
    _require(publisher_label == OUTREACH_PUBLISHER_ACCOUNT_LABEL, "publication publisher account label differs")
    _require(
        publication.get("publisher_account_id") == OUTREACH_PUBLISHER_ACCOUNT_ID,
        "publication publisher account ID differs",
    )
    public_uri = _https_uri(publication.get("public_uri"), "publication.public_uri")
    assert public_uri is not None
    _require_host(public_uri, OUTREACH_HOST, "publication.public_uri")
    comment_id = publication.get("public_comment_id")
    _require(
        type(comment_id) is str and UUID_RE.fullmatch(comment_id) is not None,
        "publication comment ID is invalid",
    )
    _require(comment_id != OUTREACH_PARENT_COMMENT_ID, "publication comment ID must differ from the registered parent")
    _require(public_uri == OUTREACH_THREAD_URI + "#comment-" + comment_id, "publication comment URI differs")
    published_at = _utc_datetime(
        publication.get("platform_published_at_utc"),
        "publication.platform_published_at_utc",
    )

    _require(publication.get("body_manifest_path") == OUTREACH_BODY_RELATIVE_PATH, "publication body manifest path differs")
    manifest_commit = publication.get("body_manifest_commit")
    _require(type(manifest_commit) is str and COMMIT_RE.fullmatch(manifest_commit) is not None, "publication body manifest commit is invalid")
    registration_commit = bindings.get("published_registration_commit")
    _require(type(registration_commit) is str, "publication requires a published registration commit")
    _require(manifest_commit != registration_commit, "outreach body manifest must be a distinct post-registration commit")
    _require(
        publication.get("body_manifest_parent_commit") == registration_commit,
        "outreach body manifest must record the registration commit as its direct parent",
    )
    _require(
        publication.get("body_manifest_public_uri")
        == _github_raw_uri(manifest_commit, OUTREACH_BODY_RELATIVE_PATH),
        "publication body manifest public URI differs",
    )
    local_manifest_sha = _file_sha256(OUTREACH_BODY_PATH)
    _require(publication.get("body_manifest_file_sha256") == local_manifest_sha, "publication body manifest file digest differs")
    _require(
        publication.get("body_manifest_public_file_sha256") == local_manifest_sha,
        "public outreach body manifest bytes differ",
    )
    manifest_public_at = _utc_datetime(
        publication.get("body_manifest_public_readback_observed_at_utc"),
        "publication.body_manifest_public_readback_observed_at_utc",
    )
    manifest = _validate_outreach_body_manifest(load_json(OUTREACH_BODY_PATH), registration_commit)
    _require(
        publication.get("authorization_intent_sha256")
        == publication_intent_sha256(
            registration_commit,
            manifest_commit,
            local_manifest_sha,
            manifest["body_sha256"],
        ),
        "publication authorization intent digest differs",
    )
    submitted_body = publication.get("submitted_body_text")
    _require(type(submitted_body) is str and bool(submitted_body.strip()), "submitted body text is required")
    _require(publication.get("submitted_body_sha256") == sha256_ref(submitted_body), "submitted body digest differs from its text")
    _require(
        publication.get("submitted_body_utf8_bytes") == len(submitted_body.encode("utf-8")),
        "submitted body bytes differ from its text",
    )
    submitted_matches = submitted_body == manifest["body_text"]
    _require(
        publication.get("submitted_body_matches_manifest") is submitted_matches,
        "submitted body manifest-match verdict differs",
    )

    readback_uri = _https_uri(publication.get("readback_uri"), "publication.readback_uri")
    assert readback_uri is not None
    _require(readback_uri == public_uri, "publication readback URI differs")
    readback_body = publication.get("readback_body_text")
    _require(type(readback_body) is str, "publication readback body text is required")
    readback_sha = _sha(publication.get("readback_sha256"), "publication.readback_sha256")
    _require(readback_sha == sha256_ref(readback_body), "publication readback digest differs from its text")
    readback_bytes = publication.get("readback_utf8_bytes")
    _require(
        readback_bytes == len(readback_body.encode("utf-8")),
        "publication readback byte count differs from its text",
    )
    exact_match = submitted_matches and readback_body == submitted_body
    _require(publication.get("readback_exact_match") is exact_match, "publication readback match verdict differs")
    publication_readback_at = _utc_datetime(
        publication.get("readback_observed_at_utc"),
        "publication.readback_observed_at_utc",
    )
    registration_public_at = _utc_datetime(
        bindings.get("registration_public_readback_observed_at_utc"),
        "bindings.registration_public_readback_observed_at_utc",
    )
    authorized_at = _utc_datetime(publication.get("authorized_at_utc"), "publication.authorized_at_utc")
    _require(
        registration_public_at
        <= manifest_public_at
        <= authorized_at
        <= published_at
        <= publication_readback_at,
        "publication chronology must be C1 readback <= C2 readback <= authorization <= publication <= readback",
    )
    deadline_at = _utc_datetime("2026-08-30T08:00:00Z", "outreach deadline")
    _require(published_at <= deadline_at, "publication occurred after the registered deadline")
    _require(type(publication.get("readback_method")) is str and bool(publication["readback_method"].strip()), "publication readback method is required")
    _require(publication.get("readback_unauthenticated") is True, "publication readback must use the public unauthenticated surface")
    _require(publication.get("public_persistence_created") is True, "publication must disclose public persistence")
    _require(publication.get("client_tool_used") is True, "publication must disclose the client tool")
    for field in ("new_account_created", "new_secret_created", "new_terms_accepted", "spending_performed"):
        _require(publication.get(field) is False, f"publication crossed the closed venue gate: {field}")
    platform_receipt = _object(publication.get("platform_receipt"), "publication.platform_receipt")
    _exact_keys(platform_receipt, ("kind", "value", "authenticated"), "publication.platform_receipt")
    _require(
        platform_receipt.get("kind") == "the-colony-public-comment-record-sha256",
        "platform receipt kind differs",
    )
    expected_comment_record = public_comment_record_sha256(
        comment_id=comment_id,
        parent_id=OUTREACH_PARENT_COMMENT_ID,
        author_label=OUTREACH_PUBLISHER_ACCOUNT_LABEL,
        author_id=OUTREACH_PUBLISHER_ACCOUNT_ID,
        body_sha256=readback_sha,
        public_uri=public_uri,
        observed_at_utc=publication["readback_observed_at_utc"],
    )
    _require(platform_receipt.get("value") == expected_comment_record, "platform receipt comment record differs")
    _require(platform_receipt.get("authenticated") is False, "local validation cannot authenticate a platform receipt")
    return publication


def _validate_external_response(
    value: Any,
    readback: Mapping[str, Any],
    publication: Mapping[str, Any],
    receipt_status: str,
) -> None:
    response = _object(value, "external_response")
    _exact_keys(
        response,
        (
            "qualifying_response_received",
            "public_uri",
            "response_id",
            "parent_id",
            "author_label",
            "author_id",
            "response_kind",
            "response_body_text",
            "exact_response_sha256",
            "exact_response_utf8_bytes",
            "selected_fields",
            "normalized_selected_fields_sha256",
            "normalization_rule",
            "platform_published_at_utc",
            "observed_at_utc",
            "readback_method",
            "readback_unauthenticated",
            "readback_comment_record_sha256",
            "stopped_by",
        ),
        "external_response",
    )
    received = response["qualifying_response_received"]
    _require(type(received) is bool, "external_response.qualifying_response_received must be boolean")
    if received:
        _require(publication.get("performed") is True, "external response requires a published invitation")
        _require(publication.get("readback_exact_match") is True, "external response requires exact invitation readback")
        public_uri = _https_uri(response["public_uri"], "external_response.public_uri")
        assert public_uri is not None
        _require_host(public_uri, OUTREACH_HOST, "external_response.public_uri")
        _require(
            type(response["response_id"]) is str
            and UUID_RE.fullmatch(response["response_id"]) is not None,
            "external response ID is invalid",
        )
        _require(
            response["response_id"]
            not in {publication.get("public_comment_id"), OUTREACH_PARENT_COMMENT_ID},
            "external response ID must differ from the invitation and registered parent",
        )
        _require(public_uri == OUTREACH_THREAD_URI + "#comment-" + response["response_id"], "external response URI differs")
        _require(response.get("parent_id") == publication.get("public_comment_id"), "external response parent differs")
        _require(type(response.get("author_label")) is str and bool(response["author_label"].strip()), "external response author is required")
        _require(
            type(response.get("author_id")) is str
            and UUID_RE.fullmatch(response["author_id"]) is not None,
            "external response author ID is invalid",
        )
        _require(
            response["author_label"].strip().casefold()
            != str(publication.get("publisher_account_label")).strip().casefold(),
            "external response author must differ from the publisher",
        )
        _require(
            response["author_id"] != publication.get("publisher_account_id"),
            "external response author ID must differ from the publisher",
        )
        _require(response["response_kind"] in RESULT_STATUSES - {"not-run"}, "external response kind is not qualifying")
        _require(response["response_kind"] == receipt_status, "receipt status differs from external response kind")
        body = response.get("response_body_text")
        _require(type(body) is str and bool(body.strip()), "external response body is required")
        envelope = _parse_public_response_body(body)
        _require(envelope["response_kind"] == response["response_kind"], "external response body kind differs")
        _require(response.get("exact_response_sha256") == sha256_ref(body), "external response digest differs")
        _require(
            response.get("exact_response_utf8_bytes") == len(body.encode("utf-8")),
            "external response byte count differs",
        )
        selected = _object(response.get("selected_fields"), "external_response.selected_fields")
        _exact_keys(
            selected,
            (
                "experiment_id",
                "preregistration_canonical_sha256",
                "packet_canonical_sha256",
                "grammar_capsule_file_sha256",
                "response_kind",
            ),
            "external_response.selected_fields",
        )
        derived_selected = {
            "experiment_id": envelope["experiment_id"],
            "preregistration_canonical_sha256": envelope["preregistration_canonical_sha256"],
            "packet_canonical_sha256": envelope["packet_canonical_sha256"],
            "grammar_capsule_file_sha256": envelope["grammar_capsule_file_sha256"],
            "response_kind": envelope["response_kind"],
        }
        _require(selected == derived_selected, "external response selected fields are not derived from the body")
        expected_readback = {
            "experiment_id_returned": envelope["experiment_id"],
            "preregistration_canonical_sha256_returned": envelope["preregistration_canonical_sha256"],
            "packet_canonical_sha256_returned": envelope["packet_canonical_sha256"],
            "grammar_capsule_file_sha256_returned": envelope["grammar_capsule_file_sha256"],
        }
        _require(
            {field: readback.get(field) for field in expected_readback} == expected_readback,
            "identity readback is not derived from the external response body",
        )
        _require(response.get("normalization_rule") == "canonical-json-sorted-keys-utf8", "external response normalization rule differs")
        _require(response.get("normalized_selected_fields_sha256") == sha256_ref(selected), "external response selected-fields digest differs")
        response_platform_timestamp = _utc_timestamp(
            response.get("platform_published_at_utc"),
            "external_response.platform_published_at_utc",
            nullable=True,
        )
        observed_at = _utc_datetime(response.get("observed_at_utc"), "external_response.observed_at_utc")
        deadline_at = _utc_datetime("2026-08-30T08:00:00Z", "outreach deadline")
        _require(observed_at <= deadline_at, "qualifying external response was observed after the deadline")
        invitation_readback_at = _utc_datetime(
            publication.get("readback_observed_at_utc"),
            "publication.readback_observed_at_utc",
        )
        if response_platform_timestamp is None:
            _require(invitation_readback_at <= observed_at, "external response predates invitation readback")
        else:
            response_platform_at = _utc_datetime(
                response_platform_timestamp,
                "external_response.platform_published_at_utc",
            )
            _require(
                invitation_readback_at <= response_platform_at <= observed_at,
                "external response chronology differs",
            )
        _require(type(response.get("readback_method")) is str and bool(response["readback_method"].strip()), "external response readback method is required")
        _require(response.get("readback_unauthenticated") is True, "external response must use public unauthenticated readback")
        _require(
            response.get("readback_comment_record_sha256")
            == public_comment_record_sha256(
                comment_id=response["response_id"],
                parent_id=response["parent_id"],
                author_label=response["author_label"],
                author_id=response["author_id"],
                body_sha256=response["exact_response_sha256"],
                public_uri=public_uri,
                observed_at_utc=response["observed_at_utc"],
            ),
            "external response comment record differs",
        )
        _require(response["stopped_by"] == "first-qualifying-response", "qualifying response must stop outreach")
        if response["response_kind"] == "identity-mismatch":
            _require(readback.get("all_matched") is False, "identity-mismatch response requires mismatched identity readback")
        else:
            _require(readback.get("all_matched") is True, "non-mismatch response requires exact identity readback")
        return
    if response["stopped_by"] is None:
        for field in set(response) - {"qualifying_response_received", "stopped_by"}:
            _require(response[field] is None, f"active outreach external_response.{field} must be null")
        return
    _require(response["stopped_by"] == "deadline", "outreach may stop only on a qualifying response or deadline")
    _require(response["observed_at_utc"] == "2026-08-30T08:00:00Z", "deadline stop time differs")
    for field in set(response) - {"qualifying_response_received", "stopped_by", "observed_at_utc"}:
        _require(response[field] is None, f"deadline stop external_response.{field} must be null")


def _validate_nonqualifying_responses(
    value: Any,
    publication: Mapping[str, Any],
    qualifying_response: Mapping[str, Any],
) -> int:
    observations = _list(value, "observed_nonqualifying_responses")
    _require(len(observations) <= 100, "too many nonqualifying response observations")
    if observations:
        _require(publication.get("performed") is True, "response observations require a published invitation")
    seen_ids: set[str] = set()
    qualifying_id = qualifying_response.get("response_id")
    invitation_readback_at = (
        _utc_datetime(publication.get("readback_observed_at_utc"), "publication.readback_observed_at_utc")
        if publication.get("performed") is True
        else None
    )
    deadline_at = _utc_datetime("2026-08-30T08:00:00Z", "outreach deadline")
    qualifying_observed_at = (
        _utc_datetime(qualifying_response.get("observed_at_utc"), "external_response.observed_at_utc")
        if qualifying_response.get("qualifying_response_received") is True
        else None
    )
    for index, item in enumerate(observations):
        path = f"observed_nonqualifying_responses[{index}]"
        observation = _object(item, path)
        _exact_keys(
            observation,
            (
                "public_uri",
                "response_id",
                "parent_id",
                "author_label",
                "author_id",
                "response_body_text",
                "exact_response_sha256",
                "exact_response_utf8_bytes",
                "body_contract_valid",
                "identity_all_matched",
                "observed_at_utc",
                "within_registered_window",
                "readback_method",
                "readback_unauthenticated",
                "nonqualifying_reason",
            ),
            path,
        )
        public_uri = _https_uri(observation.get("public_uri"), f"{path}.public_uri")
        assert public_uri is not None
        _require_host(public_uri, OUTREACH_HOST, f"{path}.public_uri")
        response_id = observation.get("response_id")
        _require(
            type(response_id) is str and UUID_RE.fullmatch(response_id) is not None,
            f"{path}.response_id is invalid",
        )
        _require(response_id not in seen_ids, f"{path}.response_id is duplicated")
        _require(response_id != qualifying_id, f"{path} duplicates the qualifying response")
        seen_ids.add(response_id)
        _require(public_uri == OUTREACH_THREAD_URI + "#comment-" + response_id, f"{path}.public_uri differs")
        _require(type(observation.get("parent_id")) is str and bool(observation["parent_id"]), f"{path}.parent_id is invalid")
        _require(type(observation.get("author_label")) is str and bool(observation["author_label"].strip()), f"{path}.author_label is invalid")
        _require(
            type(observation.get("author_id")) is str
            and UUID_RE.fullmatch(observation["author_id"]) is not None,
            f"{path}.author_id is invalid",
        )
        body = observation.get("response_body_text")
        _require(type(body) is str, f"{path}.response_body_text must be text")
        _require(len(body.encode("utf-8")) <= MAX_PUBLIC_BODY_UTF8_BYTES, f"{path} body exceeds the byte limit")
        _require(observation.get("exact_response_sha256") == sha256_ref(body), f"{path} body digest differs")
        _require(
            observation.get("exact_response_utf8_bytes") == len(body.encode("utf-8")),
            f"{path} body byte count differs",
        )
        try:
            envelope = _parse_public_response_body(body)
        except ValidationError:
            envelope = None
        body_valid = envelope is not None
        _require(observation.get("body_contract_valid") is body_valid, f"{path} body-contract verdict differs")
        if envelope is None:
            identity_all_matched = None
        else:
            identity_all_matched = (
                envelope["experiment_id"] == EXPERIMENT_ID
                and envelope["preregistration_canonical_sha256"] == PREREG_CANONICAL_SHA256
                and envelope["packet_canonical_sha256"] == PACKET_CANONICAL_SHA256
                and envelope["grammar_capsule_file_sha256"] == CAPSULE_SHA256
            )
        _require(
            observation.get("identity_all_matched") is identity_all_matched,
            f"{path} identity verdict differs",
        )
        observed_at = _utc_datetime(observation.get("observed_at_utc"), f"{path}.observed_at_utc")
        assert invitation_readback_at is not None
        within_window = invitation_readback_at <= observed_at <= deadline_at
        _require(
            observation.get("within_registered_window") is within_window,
            f"{path} registered-window verdict differs",
        )
        if qualifying_observed_at is not None:
            _require(observed_at <= qualifying_observed_at, f"{path} was observed after outreach stopped")
        _require(
            type(observation.get("readback_method")) is str
            and bool(observation["readback_method"].strip()),
            f"{path}.readback_method is invalid",
        )
        _require(observation.get("readback_unauthenticated") is True, f"{path} must use unauthenticated public readback")
        _require(
            type(observation.get("nonqualifying_reason")) is str
            and bool(observation["nonqualifying_reason"].strip()),
            f"{path}.nonqualifying_reason is required",
        )
    return len(observations)


def validate_receipt(value: Any, plan: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    validate_preregistration(plan)
    validate_packet(packet, plan)
    receipt = _object(value, "receipt")
    _exact_keys(
        receipt,
        (
            "schema_version",
            "experiment_id",
            "receipt_id",
            "status",
            "bindings",
            "classification",
            "participant",
            "identity_readback",
            "execution",
            "judge_calibration",
            "metrics",
            "publication",
            "external_response",
            "observed_nonqualifying_responses",
            "safety",
            "claim_boundary",
            "limitations",
        ),
        "receipt",
    )
    _require(receipt.get("schema_version") == RECEIPT_SCHEMA, "receipt schema differs")
    _require(receipt.get("experiment_id") == EXPERIMENT_ID, "receipt experiment differs")
    _require(
        type(receipt.get("receipt_id")) is str
        and re.fullmatch(r"[a-z0-9][a-z0-9._:-]{2,127}", receipt["receipt_id"]) is not None,
        "receipt ID is invalid",
    )
    _require(receipt.get("status") in RESULT_STATUSES, "receipt status is unknown")

    bindings = _object(receipt.get("bindings"), "receipt.bindings")
    _exact_keys(
        bindings,
        (
            "base_repository_commit",
            "preregistration_path",
            "preregistration_canonical_sha256",
            "preregistration_file_sha256",
            "packet_path",
            "packet_canonical_sha256",
            "packet_file_sha256",
            "hf_challenge_file_sha256",
            "frozen_method_file_sha256",
            "grammar_capsule_file_sha256",
            "published_registration_commit",
            "published_preregistration_uri",
            "published_preregistration_raw_uri",
            "published_packet_uri",
            "published_packet_raw_uri",
            "registration_public_readback_observed_at_utc",
            "preregistration_public_file_sha256",
            "packet_public_file_sha256",
        ),
        "receipt.bindings",
    )
    for field, expected in {
        "base_repository_commit": BASE_COMMIT,
        "preregistration_path": "interop_lab/challenges/solicited_matched_001.preregistration.json",
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "preregistration_file_sha256": PREREG_FILE_SHA256,
        "packet_path": "interop_lab/challenges/solicited_matched_001.packet.json",
        "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
        "packet_file_sha256": PACKET_FILE_SHA256,
        "hf_challenge_file_sha256": HF_SHA256,
        "frozen_method_file_sha256": FROZEN_METHOD_SHA256,
        "grammar_capsule_file_sha256": CAPSULE_SHA256,
    }.items():
        _require(bindings.get(field) == expected, f"receipt binding {field} differs")
    registration_commit = bindings.get("published_registration_commit")
    if registration_commit is not None:
        _require(
            type(registration_commit) is str and COMMIT_RE.fullmatch(registration_commit) is not None,
            "published registration requires a full commit",
        )
        _require(
            bindings.get("published_preregistration_uri")
            == _github_blob_uri(registration_commit, bindings["preregistration_path"]),
            "published preregistration URI differs",
        )
        _require(
            bindings.get("published_packet_uri")
            == _github_blob_uri(registration_commit, bindings["packet_path"]),
            "published packet URI differs",
        )
        _require(
            bindings.get("published_preregistration_raw_uri")
            == _github_raw_uri(registration_commit, bindings["preregistration_path"]),
            "published preregistration raw URI differs",
        )
        _require(
            bindings.get("published_packet_raw_uri")
            == _github_raw_uri(registration_commit, bindings["packet_path"]),
            "published packet raw URI differs",
        )
        _utc_timestamp(
            bindings.get("registration_public_readback_observed_at_utc"),
            "bindings.registration_public_readback_observed_at_utc",
        )
        _require(bindings.get("preregistration_public_file_sha256") == PREREG_FILE_SHA256, "public preregistration bytes differ")
        _require(bindings.get("packet_public_file_sha256") == PACKET_FILE_SHA256, "public packet bytes differ")
    else:
        for field in (
            "published_preregistration_uri",
            "published_preregistration_raw_uri",
            "published_packet_uri",
            "published_packet_raw_uri",
            "registration_public_readback_observed_at_utc",
            "preregistration_public_file_sha256",
            "packet_public_file_sha256",
        ):
            _require(bindings.get(field) is None, f"unpublished registration {field} must be null")

    classification = _object(receipt.get("classification"), "classification")
    _require(
        classification
        == {
            "declared_experiment_class": "PROJECT-SOLICITED",
            "verified_experiment_class": "UNVERIFIED",
            "independent_reproduction": False,
            "organic_adoption": False,
            "external_adoption_evidence": False,
        },
        "receipt classification differs",
    )
    participant = _object(receipt.get("participant"), "participant")
    _exact_keys(
        participant,
        (
            "public_account_label",
            "control_group_id",
            "accountable_operator",
            "runtime",
            "exact_model_version",
            "prior_urusilla_exposure",
            "relationship_to_project_authenticated",
            "provider_authenticity_verified",
        ),
        "participant",
    )
    for field in ("public_account_label", "control_group_id", "accountable_operator", "runtime", "exact_model_version"):
        if participant[field] is not None:
            _require(type(participant[field]) is str and bool(participant[field].strip()), f"participant.{field} is invalid")
    _require(participant.get("prior_urusilla_exposure") in {"unknown", "none", "self-reported", "project-reported"}, "participant prior exposure is invalid")
    _require(participant.get("relationship_to_project_authenticated") is False, "project relationship is not authenticated")
    _require(participant.get("provider_authenticity_verified") is False, "provider authenticity is not verified")

    readback = _object(receipt.get("identity_readback"), "identity_readback")
    _exact_keys(
        readback,
        (
            "experiment_id_returned",
            "preregistration_canonical_sha256_returned",
            "packet_canonical_sha256_returned",
            "grammar_capsule_file_sha256_returned",
            "all_matched",
        ),
        "identity_readback",
    )
    returned = (
        readback.get("experiment_id_returned"),
        readback.get("preregistration_canonical_sha256_returned"),
        readback.get("packet_canonical_sha256_returned"),
        readback.get("grammar_capsule_file_sha256_returned"),
    )
    if all(item is None for item in returned):
        _require(readback.get("all_matched") is None, "absent readback must remain null")
    else:
        _require(type(returned[0]) is str, "returned experiment ID must be text")
        for index, item in enumerate(returned[1:], start=1):
            _sha(item, f"identity_readback.returned[{index}]", nullable=True)
        expected = (EXPERIMENT_ID, PREREG_CANONICAL_SHA256, PACKET_CANONICAL_SHA256, CAPSULE_SHA256)
        _require(readback.get("all_matched") is (returned == expected), "identity readback verdict differs")

    execution = _object(receipt.get("execution"), "execution")
    _require(tuple(execution.get("arm_order", [])) == ARM_ORDER, "receipt arm order differs")
    _require(tuple(execution.get("task_order_within_arm", [])) == TASK_IDS, "receipt task order differs")
    _require(execution.get("base_receiver_executions_expected") == 6, "receipt expected execution count differs")
    base = _list(execution.get("base_executions"), "execution.base_executions")
    _require(len(base) == 6, "receipt must retain all six base execution slots")
    ledgers: dict[tuple[str, str], dict[str, int | None] | None] = {}
    executions: dict[tuple[str, str], dict[str, Any]] = {}
    for index, ((arm, task), item) in enumerate(zip(_expected_execution_pairs(), base, strict=True)):
        execution_item, ledger = _validate_execution_result(
            item,
            f"execution.base_executions[{index}]",
            arm,
            task,
            _task_by_id(plan, task)["expected_output"],
        )
        executions[(arm, task)] = execution_item
        ledgers[(arm, task)] = ledger
    observed = sum(item["attempted"] for item in executions.values())
    _require(execution.get("base_receiver_executions_observed") == observed, "observed base execution count differs")
    if observed:
        sessions_by_arm = {
            arm: {executions[(arm, task)]["session_id"] for task in TASK_IDS if executions[(arm, task)]["attempted"]}
            for arm in ARM_IDS
        }
        same_within = all(len(values) <= 1 for values in sessions_by_arm.values())
        used_sessions = [next(iter(values)) for values in sessions_by_arm.values() if values]
        fresh_between = len(used_sessions) == len(set(used_sessions))
        dispatched_attempts = [
            attempt
            for item in executions.values()
            for attempt in item["attempts"]
            if attempt["request_dispatched"]
        ]
        actual_model_settings = {
            (attempt["model_id"], attempt["settings_sha256"])
            for attempt in dispatched_attempts
        }
        same_actual_model_and_settings = bool(dispatched_attempts) and len(actual_model_settings) == 1
        _require(execution.get("same_session_within_arm") is same_within, "same-session attestation differs")
        _require(execution.get("fresh_context_between_arms") is fresh_between, "fresh-context attestation differs")
        _require(
            execution.get("same_model_and_settings") is same_actual_model_and_settings,
            "same-model attestation differs from attempt evidence",
        )
        _require(
            type(execution.get("preflight_primary_and_fallback_complete")) is bool,
            "preflight attestation must be boolean",
        )
    else:
        for field in ("same_session_within_arm", "fresh_context_between_arms", "same_model_and_settings", "preflight_primary_and_fallback_complete"):
            _require(execution.get(field) is None, f"unrun execution.{field} must be null")

    if receipt.get("status") == "matched-result":
        _require(observed == 6, "matched result must contain exactly six base receiver executions")
        base_primaries = [
            next(attempt for attempt in executions[(arm, task)]["attempts"] if attempt["attempt_kind"] == "primary")
            for arm, task in _expected_execution_pairs()
        ]
        _require(
            sum(attempt["request_dispatched"] for attempt in base_primaries) == 6,
            "matched result must contain six dispatched base primaries",
        )
        _require(execution.get("same_session_within_arm") is True, "matched result violates same-session design")
        _require(execution.get("fresh_context_between_arms") is True, "matched result violates fresh-context design")
        _require(execution.get("same_model_and_settings") is True, "matched result changes model or settings")
        _require(
            execution.get("preflight_primary_and_fallback_complete") is True,
            "matched result lacks primary and fallback preflight",
        )

    calibration_passed, denominator_expected = _calibration_state(
        receipt.get("judge_calibration"), packet, plan
    )
    metrics = _object(receipt.get("metrics"), "metrics")
    denominators = _object(metrics.get("safe_completion_denominator_valid"), "metrics.safe_completion_denominator_valid")
    _require(set(denominators) == set(ARM_IDS), "denominator arms differ")
    for arm in ARM_IDS:
        _require(denominators[arm] is denominator_expected[arm], f"{arm} denominator validity differs")
    tokens_per_safe = _object(metrics.get("tokens_per_safely_completed_task"), "metrics.tokens_per_safely_completed_task")
    _require(set(tokens_per_safe) == set(ARM_IDS), "tokens-per-safe arms differ")
    for arm in ARM_IDS:
        if not denominators[arm] or any(ledgers[(arm, task)] is None or ledgers[(arm, task)]["total"] is None for task in TASK_IDS):
            _require(tokens_per_safe[arm] is None, f"{arm} tokens per safe task must be null")
        else:
            safe_count = sum(executions[(arm, task)]["safe_completion"] is True for task in TASK_IDS)
            expected_value = None if safe_count == 0 else sum(ledgers[(arm, task)]["total"] for task in TASK_IDS) / safe_count  # type: ignore[misc]
            _require(tokens_per_safe[arm] == expected_value, f"{arm} tokens per safe task differs")

    curve = _list(metrics.get("cumulative_k_curve"), "metrics.cumulative_k_curve")
    _require([row.get("k") for row in curve] == list(K_VALUES), "receipt must publish full K=[1,2] curve")
    for row in curve:
        k = row["k"]
        totals: dict[str, int | None] = {}
        for arm in ARM_IDS:
            prefix = [ledgers[(arm, task)] for task in TASK_IDS[:k]]
            total = None if any(item is None or item["total"] is None for item in prefix) else sum(item["total"] for item in prefix)  # type: ignore[misc]
            field = f"{arm}_total_tokens"
            _require(row.get(field) == total, f"K={k} {arm} cumulative total differs")
            totals[arm] = total
        if any(totals[arm] is None for arm in ARM_IDS):
            expected_saving = None
        else:
            baseline = min(totals["raw"], totals["json"])  # type: ignore[type-var]
            expected_saving = None if baseline == 0 else round((baseline - totals["urusilla"]) * 100.0 / baseline, 6)  # type: ignore[operator]
        _require(row.get("urusilla_saving_vs_better_baseline_percent") == expected_saving, f"K={k} saving differs")
    _require(metrics.get("efficiency_result") is None, "microstudy efficiency result must remain null")
    _require(metrics.get("break_even_k") is None, "microstudy break-even must remain null")

    publication = _validate_publication(receipt.get("publication"), bindings)
    external_response = _object(receipt.get("external_response"), "external_response")
    _validate_external_response(external_response, readback, publication, receipt["status"])
    nonqualifying_response_count = _validate_nonqualifying_responses(
        receipt.get("observed_nonqualifying_responses"),
        publication,
        external_response,
    )
    safety = _object(receipt.get("safety"), "safety")
    expected_safety = {
        "task_execution_read_only": True,
        "task_execution_tools_used": False,
        "task_execution_persistence_created": False,
        "task_execution_spending_performed": False,
        "task_execution_new_account_created": False,
        "task_execution_new_secret_created": False,
        "task_execution_new_terms_accepted": False,
        "permission_expanded": False,
        "protocol_spending_authority_created": False,
        "task_execution_external_effects_performed": False,
        "untrusted_executable_content_run": False,
    }
    _require(safety == expected_safety, "task safety boundary differs")
    claims = _object(receipt.get("claim_boundary"), "claim_boundary")
    _require(claims.get("general_unfamiliar_agent_saving_percent") == 0.0, "receipt changes 0% result")
    _require(claims.get("safely_completed_real_task_total_token_result") is None, "receipt promotes unknown real-task result")
    for field in (
        "changes_general_zero_percent",
        "efficiency_claim_eligible",
        "independent_reproduction_claim",
        "organic_adoption_claim",
        "external_adoption_claim",
        "protocol_version_change_claim",
        "state_of_the_art_claim",
    ):
        _require(claims.get(field) is False, f"receipt cannot claim {field}")
    if receipt.get("status") == "not-run":
        _require(observed == 0, "not-run receipt contains an execution")
        _require(calibration_passed is None, "not-run receipt contains calibration")
    if receipt.get("status") == "matched-result":
        _require(readback.get("all_matched") is True, "matched result requires exact identity readback")
    if receipt.get("status") == "identity-mismatch":
        _require(readback.get("all_matched") is False, "identity-mismatch status requires a mismatched readback")
    limitations = _list(receipt.get("limitations"), "limitations")
    _require(bool(limitations) and all(type(item) is str and bool(item.strip()) for item in limitations), "receipt limitations are invalid")
    _require(any("copy" in item.lower() and "answer" in item.lower() for item in limitations), "open-answer-key limitation is missing")
    _require(
        any(
            "first-qualifying-response" in item.lower()
            and "not independently authenticated" in item.lower()
            for item in limitations
        ),
        "first-response authentication limitation is missing",
    )
    return {
        "valid": True,
        "validation_scope": "structural-content-consistency-only",
        "provider_authenticity_verified": False,
        "invocation_chronology_authenticated": False,
        "experiment_id": EXPERIMENT_ID,
        "receipt_id": receipt.get("receipt_id"),
        "status": receipt.get("status"),
        "network_used_by_validator": False,
        "provider_calls_by_validator": 0,
        "base_receiver_executions_observed": observed,
        "judge_calibration_passed": calibration_passed,
        "safe_completion_denominator_valid": denominators,
        "observed_nonqualifying_response_count": nonqualifying_response_count,
        "efficiency_result": None,
        "changes_general_zero_percent": False,
    }


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise ValidationError(f"refusing to overwrite existing path: {path}")
    try:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot write {path}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, default in (
        ("validate-prereg", PREREG_PATH),
        ("validate-packet", PACKET_PATH),
        ("validate-receipt", RECEIPT_TEMPLATE_PATH),
    ):
        item = sub.add_parser(name)
        item.add_argument("path", nargs="?", type=Path, default=default)
        item.add_argument("--json", action="store_true")
    init = sub.add_parser("init-receipt")
    init.add_argument("path", type=Path)
    for name in ("build-outreach", "validate-outreach", "print-outreach"):
        item = sub.add_parser(name)
        item.add_argument("registration_commit")
        item.add_argument("path", nargs="?", type=Path, default=OUTREACH_BODY_PATH)
        if name == "validate-outreach":
            item.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = load_json(PREREG_PATH)
        packet = load_json(PACKET_PATH)
        if args.command == "build-outreach":
            _write_new(args.path, build_outreach_manifest(args.registration_commit))
            print(args.path)
            return 0
        if args.command == "validate-outreach":
            report = validate_outreach_manifest(load_json(args.path), args.registration_commit)
        elif args.command == "print-outreach":
            manifest = _validate_outreach_body_manifest(load_json(args.path), args.registration_commit)
            sys.stdout.write(manifest["body_text"])
            return 0
        elif args.command == "validate-prereg":
            report = validate_preregistration(load_json(args.path))
        elif args.command == "validate-packet":
            report = validate_packet(load_json(args.path), plan)
        elif args.command == "validate-receipt":
            report = validate_receipt(load_json(args.path), plan, packet)
        elif args.command == "init-receipt":
            _write_new(args.path, load_json(RECEIPT_TEMPLATE_PATH))
            print(args.path)
            return 0
        else:  # pragma: no cover - argparse keeps this unreachable
            raise ValidationError(f"unknown command: {args.command}")
    except (ValidationError, OSError, UnicodeError, ValueError, KeyError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        print(json.dumps(report, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
