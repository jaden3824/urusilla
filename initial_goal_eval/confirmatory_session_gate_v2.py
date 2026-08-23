"""Reticuli-gated matched-session accounting for a future confirmatory study.

This is a separately versioned evaluation component.  It does not modify or
reinterpret the frozen initial-goal v1 method, and it cannot make a performance
claim.  It adds the missing pre-result constraints identified by the Reticuli
review: explicit prior-search lineage, a complete frozen warm-horizon curve,
and arm-blinded matched-defect calibration before any safe-completion
denominator or efficiency statistic is computed.

The verifier is deliberately provider-neutral and offline.  Content-consistent
flags are not provider-origin proof, so every claim-facing field remains null
or false even when a synthetic fixture passes all diagnostic metric gates.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, MutableSet, Sequence

from .contract import (
    ARMS,
    BASELINES,
    COVERAGE_FIELDS,
    EVENT_PHASES,
    FEATURE_TAGS,
    FROZEN_METHOD_PATH,
    VerificationError,
    load_frozen_method,
    sha256_ref,
    validate_frozen_method,
)
from .statistics import SessionAggregate, compare_to_both_baselines


PLAN_SCHEMA = "urusilla-confirmatory-session-gate-plan/2"
RESULT_SCHEMA = "urusilla-confirmatory-session-gate-result/2"
SUMMARY_SCHEMA = "urusilla-confirmatory-session-gate-summary/2"

EVIDENCE_BOUNDARIES = (
    "synthetic-test-only",
    "real-independent-evaluation",
)
LINEAGE_STATUSES = ("complete", "partial", "unrecoverable")
AUTHENTICITY_FIELDS = (
    "provider_origin_verified",
    "provider_receipts_authenticated",
    "provider_full_history_billing_verified",
    "intermediary_attempt_and_cache_visibility_verified",
    "usage_normalizer_replayed",
    "operator_independence_validated",
    "auditor_independence_validated",
    "judge_receipts_authenticated",
    "preregistration_chronology_verified",
    "global_replay_registry_verified",
    "sandbox_enforcement_independently_observed",
)
SAFETY_FIELDS = (
    "unauthorized_external_effects",
    "unknown_schema_executions",
    "persistence_events",
    "permission_expansions",
    "spending_authority_events",
)
NON_SETUP_PHASES = tuple(item for item in EVENT_PHASES if item != "setup")
TERMINAL_STATUSES = (
    "completed",
    "failed",
    "refused",
    "budget-exceeded",
    "proven-zero",
)
USAGE_SOURCES = ("provider", "local")
REASONING_ACCOUNTING = (
    "none",
    "not-reported",
    "included-in-output",
    "separately-reported",
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,255}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GATE_IMPLEMENTATION_PATHS = (
    Path(__file__),
    FROZEN_METHOD_PATH.with_name("statistics.py"),
    FROZEN_METHOD_PATH.with_name("contract.py"),
)


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise VerificationError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise VerificationError(f"{path} must be an array")
    return value


def _exact(value: Mapping[str, Any], keys: Sequence[str], path: str) -> None:
    expected = set(keys)
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise VerificationError(
            f"{path} fields differ; missing={missing}, extra={extra}"
        )


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise VerificationError(f"{path} must be a bounded identifier")
    return value


def _sha(value: Any, path: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise VerificationError(f"{path} must be a sha256 reference")
    return value


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise VerificationError(f"{path} must be boolean")
    return value


def _nonnegative(value: Any, path: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 0:
        suffix = " or null" if nullable else ""
        raise VerificationError(f"{path} must be a nonnegative integer{suffix}")
    return value


def _fraction(value: Any, path: str) -> Fraction:
    item = _object(value, path)
    _exact(item, ("numerator", "denominator"), path)
    numerator = _nonnegative(item["numerator"], f"{path}.numerator")
    denominator = _nonnegative(item["denominator"], f"{path}.denominator")
    assert numerator is not None and denominator is not None
    if denominator == 0 or numerator > denominator:
        raise VerificationError(f"{path} must be a fraction from zero through one")
    return Fraction(numerator, denominator)


def _fraction_object(value: Fraction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": f"{float(value):.12f}",
    }


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    value = None if denominator == 0 else Fraction(numerator, denominator)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": None if value is None else float(value),
        "exact": _fraction_object(value),
    }


def _file_sha256() -> str:
    return "sha256:" + hashlib.sha256(FROZEN_METHOD_PATH.read_bytes()).hexdigest()


def expected_gate_implementation_binding() -> dict[str, Any]:
    """Bind the exact structural verifier, statistics, and contract bytes."""

    repository_root = FROZEN_METHOD_PATH.parents[1]
    return {
        "schema_version": "urusilla-confirmatory-session-gate-implementation/2",
        "files": [
            {
                "path": path.relative_to(repository_root).as_posix(),
                "file_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in _GATE_IMPLEMENTATION_PATHS
        ],
    }


def _validate_gate_implementation(value: Any) -> None:
    item = _object(value, "plan.gate_implementation")
    _exact(item, ("schema_version", "files"), "plan.gate_implementation")
    expected = expected_gate_implementation_binding()
    if item != expected:
        raise VerificationError(
            "plan.gate_implementation differs from the exact v2 verifier bundle"
        )


def expected_base_method_binding() -> dict[str, str]:
    """Return the immutable v1 identity used by the separate v2 gate."""

    method = load_frozen_method()
    validate_frozen_method(method)
    return {
        "path": "initial_goal_eval/frozen_method_plan.json",
        "schema_version": "urusilla-initial-goal-frozen-method/1",
        "canonical_sha256": sha256_ref(method),
        "file_sha256": _file_sha256(),
    }


def _validate_base_method(value: Any) -> None:
    item = _object(value, "plan.base_method")
    _exact(
        item,
        (
            "path",
            "schema_version",
            "canonical_sha256",
            "file_sha256",
            "modified",
        ),
        "plan.base_method",
    )
    expected = expected_base_method_binding()
    for field, expected_value in expected.items():
        if item[field] != expected_value:
            raise VerificationError(f"plan.base_method.{field} differs from frozen v1")
    if item["modified"] is not False:
        raise VerificationError("the frozen v1 method must remain unmodified")


def _validate_known_boundary(value: Any) -> None:
    item = _object(value, "plan.known_result_boundary")
    _exact(
        item,
        (
            "general_unfamiliar_agent_saving_percent",
            "safely_completed_real_task_total_token_result",
            "single_study_changes_general_result",
            "single_study_supports_protocol_version_change",
            "single_study_supports_state_of_the_art_claim",
        ),
        "plan.known_result_boundary",
    )
    if item != {
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
        "single_study_changes_general_result": False,
        "single_study_supports_protocol_version_change": False,
        "single_study_supports_state_of_the_art_claim": False,
    }:
        raise VerificationError("plan.known_result_boundary overstates current evidence")


def _validate_lineage(value: Any) -> None:
    lineage = _object(value, "plan.prior_search_lineage")
    _exact(
        lineage,
        (
            "status",
            "prior_rounds_seen",
            "arms_dropped_before_freeze",
            "all_known_rounds_disclosed",
            "outcome_independent_freeze_attested",
            "untouched_architecture_selection_claim",
            "nominal_search_wide_confidence_claim",
        ),
        "plan.prior_search_lineage",
    )
    if lineage["status"] not in LINEAGE_STATUSES:
        raise VerificationError("plan.prior_search_lineage.status is invalid")
    rounds = _list(lineage["prior_rounds_seen"], "plan.prior_search_lineage.prior_rounds_seen")
    if not rounds:
        raise VerificationError("prior-search lineage cannot omit every prior round")
    seen: set[str] = set()
    for index, raw in enumerate(rounds):
        path = f"plan.prior_search_lineage.prior_rounds_seen[{index}]"
        item = _object(raw, path)
        _exact(item, ("id", "artifact_sha256", "disclosure"), path)
        identity = _identifier(item["id"], f"{path}.id")
        if identity in seen:
            raise VerificationError("prior-search lineage contains a duplicate round")
        seen.add(identity)
        _sha(item["artifact_sha256"], f"{path}.artifact_sha256")
        if type(item["disclosure"]) is not str or not item["disclosure"].strip():
            raise VerificationError(f"{path}.disclosure must be nonempty text")
    dropped = _list(
        lineage["arms_dropped_before_freeze"],
        "plan.prior_search_lineage.arms_dropped_before_freeze",
    )
    dropped_ids: set[str] = set()
    for index, raw in enumerate(dropped):
        path = f"plan.prior_search_lineage.arms_dropped_before_freeze[{index}]"
        item = _object(raw, path)
        _exact(item, ("arm_id", "reason", "evidence_sha256"), path)
        arm_id = _identifier(item["arm_id"], f"{path}.arm_id")
        if arm_id in dropped_ids or arm_id in ARMS:
            raise VerificationError("dropped-arm lineage is duplicate or drops a required arm")
        dropped_ids.add(arm_id)
        if type(item["reason"]) is not str or not item["reason"].strip():
            raise VerificationError(f"{path}.reason must be nonempty text")
        _sha(item["evidence_sha256"], f"{path}.evidence_sha256")
    if lineage["all_known_rounds_disclosed"] is not True:
        raise VerificationError("all known prior rounds must be disclosed before the run")
    if lineage["outcome_independent_freeze_attested"] is not True:
        raise VerificationError("lineage must be frozen before confirmatory outcomes")
    if (
        lineage["untouched_architecture_selection_claim"] is not False
        or lineage["nominal_search_wide_confidence_claim"] is not False
    ):
        raise VerificationError("lineage cannot erase prior architecture search")


def _validate_warm_reuse(value: Any) -> tuple[int, ...]:
    warm = _object(value, "plan.warm_reuse")
    _exact(
        warm,
        (
            "registered_k_curve",
            "headline_k",
            "publish_every_registered_k",
            "extrapolation_beyond_headline_allowed",
            "cross_session_amortization_allowed",
            "shared_setup_charge_count_per_arm_session",
        ),
        "plan.warm_reuse",
    )
    raw_curve = _list(warm["registered_k_curve"], "plan.warm_reuse.registered_k_curve")
    if not raw_curve or any(type(item) is not int or item < 1 for item in raw_curve):
        raise VerificationError("registered K values must be positive integers")
    curve = tuple(raw_curve)
    if curve != tuple(range(1, curve[-1] + 1)):
        raise VerificationError("registered K curve must publish every prefix from one")
    if warm["headline_k"] != curve[-1]:
        raise VerificationError("headline K must be the frozen final registered prefix")
    if warm["publish_every_registered_k"] is not True:
        raise VerificationError("every registered K must be published")
    if warm["extrapolation_beyond_headline_allowed"] is not False:
        raise VerificationError("unregistered warm-horizon extrapolation is prohibited")
    if warm["cross_session_amortization_allowed"] is not False:
        raise VerificationError("cross-session amortization is prohibited")
    if warm["shared_setup_charge_count_per_arm_session"] != 1:
        raise VerificationError("shared setup must be charged exactly once per arm session")
    return curve


def _validate_calibration_plan(value: Any) -> dict[str, Any]:
    calibration = _object(value, "plan.judge_calibration")
    _exact(
        calibration,
        (
            "scorer_implementation_sha256",
            "scorer_settings_sha256",
            "scorer_receives_arm_identity",
            "arm_blinded",
            "minimum_detection_rate",
            "maximum_between_arm_detection_gap",
            "missing_or_unmeasurable_invalidates_every_denominator",
            "calibration_cost_allocation",
            "matched_defects",
        ),
        "plan.judge_calibration",
    )
    scorer = _sha(
        calibration["scorer_implementation_sha256"],
        "plan.judge_calibration.scorer_implementation_sha256",
    )
    settings = _sha(
        calibration["scorer_settings_sha256"],
        "plan.judge_calibration.scorer_settings_sha256",
    )
    if calibration["scorer_receives_arm_identity"] is not False:
        raise VerificationError("calibration scorer cannot receive arm identity")
    if calibration["arm_blinded"] is not True:
        raise VerificationError("matched-defect calibration must be arm blinded")
    minimum = _fraction(
        calibration["minimum_detection_rate"],
        "plan.judge_calibration.minimum_detection_rate",
    )
    maximum_gap = _fraction(
        calibration["maximum_between_arm_detection_gap"],
        "plan.judge_calibration.maximum_between_arm_detection_gap",
    )
    if calibration["missing_or_unmeasurable_invalidates_every_denominator"] is not True:
        raise VerificationError("missing calibration must invalidate every denominator")
    if calibration["calibration_cost_allocation"] != "reported-separately-not-in-task-total":
        raise VerificationError("calibration cost allocation must be frozen and separate")
    defects = _list(calibration["matched_defects"], "plan.judge_calibration.matched_defects")
    if not defects:
        raise VerificationError("judge calibration requires a known-positive defect")
    defect_ids: set[str] = set()
    blind_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(defects):
        path = f"plan.judge_calibration.matched_defects[{index}]"
        item = _object(raw, path)
        _exact(item, ("matched_defect_id", "semantic_defect_sha256", "blind_inputs"), path)
        defect_id = _identifier(item["matched_defect_id"], f"{path}.matched_defect_id")
        if defect_id in defect_ids:
            raise VerificationError("judge calibration has a duplicate defect ID")
        defect_ids.add(defect_id)
        semantic_sha = _sha(item["semantic_defect_sha256"], f"{path}.semantic_defect_sha256")
        blind = _object(item["blind_inputs"], f"{path}.blind_inputs")
        _exact(blind, ARMS, f"{path}.blind_inputs")
        normalized_blind: dict[str, dict[str, str]] = {}
        for arm in ARMS:
            blind_path = f"{path}.blind_inputs.{arm}"
            row = _object(blind[arm], blind_path)
            _exact(row, ("blind_id", "scorer_input_sha256"), blind_path)
            blind_id = _identifier(row["blind_id"], f"{blind_path}.blind_id")
            if blind_id in blind_ids:
                raise VerificationError("judge calibration blind IDs must be globally unique")
            blind_ids.add(blind_id)
            normalized_blind[arm] = {
                "blind_id": blind_id,
                "scorer_input_sha256": _sha(
                    row["scorer_input_sha256"],
                    f"{blind_path}.scorer_input_sha256",
                ),
            }
        normalized.append(
            {
                "matched_defect_id": defect_id,
                "semantic_defect_sha256": semantic_sha,
                "blind_inputs": normalized_blind,
            }
        )
    return {
        "scorer_implementation_sha256": scorer,
        "scorer_settings_sha256": settings,
        "minimum_detection_rate": minimum,
        "maximum_between_arm_detection_gap": maximum_gap,
        "matched_defects": normalized,
    }


def _validate_required_usage(value: Any) -> None:
    usage = _object(value, "plan.required_usage")
    _exact(
        usage,
        (
            "coverage_fields",
            "event_phases",
            "unknown_is_zero",
            "billed_failed_attempts_included",
            "fallback_cannot_erase_failed_primary_cost",
        ),
        "plan.required_usage",
    )
    if usage["coverage_fields"] != list(COVERAGE_FIELDS):
        raise VerificationError("complete usage coverage fields differ from frozen v1")
    if usage["event_phases"] != list(EVENT_PHASES):
        raise VerificationError("usage event phases differ from frozen v1")
    if usage["unknown_is_zero"] is not False:
        raise VerificationError("unknown usage cannot be zero")
    if usage["billed_failed_attempts_included"] is not True:
        raise VerificationError("billed failed attempts must remain in totals")
    if usage["fallback_cannot_erase_failed_primary_cost"] is not True:
        raise VerificationError("fallback cannot erase a failed primary cost")


def _validate_plan_matrix(plan: Mapping[str, Any], curve: tuple[int, ...]) -> dict[str, Any]:
    domains = _list(plan["domains"], "plan.domains")
    domain_ids: list[str] = []
    for index, raw in enumerate(domains):
        path = f"plan.domains[{index}]"
        item = _object(raw, path)
        _exact(item, ("domain_id", "task_family", "manifest_sha256"), path)
        domain_ids.append(_identifier(item["domain_id"], f"{path}.domain_id"))
        _identifier(item["task_family"], f"{path}.task_family")
        _sha(item["manifest_sha256"], f"{path}.manifest_sha256")
    if len(domain_ids) < 3 or len(set(domain_ids)) != len(domain_ids):
        raise VerificationError("confirmatory plan requires three distinct domains")

    models = _list(plan["receiver_models"], "plan.receiver_models")
    families: list[str] = []
    for index, raw in enumerate(models):
        path = f"plan.receiver_models[{index}]"
        item = _object(raw, path)
        _exact(item, ("family", "model_id", "settings_sha256"), path)
        families.append(_identifier(item["family"], f"{path}.family"))
        _identifier(item["model_id"], f"{path}.model_id")
        _sha(item["settings_sha256"], f"{path}.settings_sha256")
    if len(families) < 2 or len(set(families)) != len(families):
        raise VerificationError("confirmatory plan requires two receiver families")

    operators = _list(plan["operators"], "plan.operators")
    operator_ids: list[str] = []
    for index, raw in enumerate(operators):
        path = f"plan.operators[{index}]"
        item = _object(raw, path)
        _exact(
            item,
            ("operator_id", "independent", "project_operated", "attestation_sha256"),
            path,
        )
        operator_ids.append(_identifier(item["operator_id"], f"{path}.operator_id"))
        if item["independent"] is not True or item["project_operated"] is not False:
            raise VerificationError("confirmatory operators must be independently operated")
        _sha(item["attestation_sha256"], f"{path}.attestation_sha256")
    if len(operator_ids) < 2 or len(set(operator_ids)) != len(operator_ids):
        raise VerificationError("confirmatory plan requires two independent operators")

    sessions = _list(plan["sessions"], "plan.sessions")
    session_ids: set[str] = set()
    cluster_ids: set[str] = set()
    strata: dict[tuple[str, str, str], int] = {}
    feature_union: set[str] = set()
    probe_counts = {"parse_probe": 0, "semantic_probe": 0, "negative_probe": 0}
    normalized_sessions: list[dict[str, Any]] = []
    for index, raw in enumerate(sessions):
        path = f"plan.sessions[{index}]"
        item = _object(raw, path)
        _exact(
            item,
            (
                "session_id",
                "cluster_id",
                "domain_id",
                "receiver_family",
                "operator_id",
                "boundary_auditor_id",
                "arm_order",
                "tasks",
            ),
            path,
        )
        session_id = _identifier(item["session_id"], f"{path}.session_id")
        cluster_id = _identifier(item["cluster_id"], f"{path}.cluster_id")
        if session_id in session_ids or cluster_id in cluster_ids:
            raise VerificationError("session and whole-session cluster IDs must be unique")
        session_ids.add(session_id)
        cluster_ids.add(cluster_id)
        if item["domain_id"] not in domain_ids or item["receiver_family"] not in families:
            raise VerificationError(f"{path} references an unknown domain or receiver family")
        if (
            item["operator_id"] not in operator_ids
            or item["boundary_auditor_id"] not in operator_ids
        ):
            raise VerificationError(f"{path} references an unknown operator or auditor")
        if item["operator_id"] == item["boundary_auditor_id"]:
            raise VerificationError("execution operator and boundary auditor must differ")
        if type(item["arm_order"]) is not list or sorted(item["arm_order"]) != sorted(ARMS):
            raise VerificationError(f"{path}.arm_order must contain every arm exactly once")
        tasks = _list(item["tasks"], f"{path}.tasks")
        if len(tasks) != curve[-1]:
            raise VerificationError(f"{path}.tasks must cover the full registered K horizon")
        task_ids: set[str] = set()
        normalized_tasks: list[dict[str, Any]] = []
        for task_index, raw_task in enumerate(tasks):
            task_path = f"{path}.tasks[{task_index}]"
            task = _object(raw_task, task_path)
            _exact(
                task,
                (
                    "task_id",
                    "task_sha256",
                    "feature_tags",
                    "parse_probe",
                    "semantic_probe",
                    "negative_probe",
                ),
                task_path,
            )
            task_id = _identifier(task["task_id"], f"{task_path}.task_id")
            if task_id in task_ids:
                raise VerificationError(f"{path} contains duplicate task IDs")
            task_ids.add(task_id)
            task_sha = _sha(task["task_sha256"], f"{task_path}.task_sha256")
            tags = _list(task["feature_tags"], f"{task_path}.feature_tags")
            if len(tags) != len(set(tags)) or not set(tags).issubset(FEATURE_TAGS):
                raise VerificationError(f"{task_path}.feature_tags are invalid")
            feature_union.update(tags)
            for field in probe_counts:
                probe_counts[field] += int(_boolean(task[field], f"{task_path}.{field}"))
            normalized_tasks.append(
                {
                    "task_id": task_id,
                    "task_sha256": task_sha,
                    "feature_tags": tuple(tags),
                    "parse_probe": task["parse_probe"],
                    "semantic_probe": task["semantic_probe"],
                    "negative_probe": task["negative_probe"],
                }
            )
        stratum = (item["domain_id"], item["receiver_family"], item["operator_id"])
        strata[stratum] = strata.get(stratum, 0) + 1
        normalized_sessions.append(
            {
                "session_id": session_id,
                "cluster_id": cluster_id,
                "domain_id": item["domain_id"],
                "receiver_family": item["receiver_family"],
                "operator_id": item["operator_id"],
                "arm_order": tuple(item["arm_order"]),
                "tasks": tuple(normalized_tasks),
            }
        )
    expected_strata = {
        (domain, family, operator)
        for domain in domain_ids
        for family in families
        for operator in operator_ids
    }
    if set(strata) != expected_strata or min(strata.values(), default=0) < 2:
        raise VerificationError("every domain/model/operator stratum needs two whole sessions")
    if feature_union != set(FEATURE_TAGS) or min(probe_counts.values()) < 1:
        raise VerificationError("plan must cover every feature and parse/semantic/negative probes")
    return {
        "sessions": tuple(normalized_sessions),
        "domains": len(domain_ids),
        "receiver_families": len(families),
        "operators": len(operator_ids),
        "probe_counts": probe_counts,
    }


def validate_confirmatory_plan(value: Any) -> dict[str, Any]:
    """Validate a pre-result plan without changing frozen v1."""

    plan = _object(value, "plan")
    _exact(
        plan,
        (
            "schema_version",
            "status",
            "study_id",
            "evidence_boundary",
            "base_method",
            "gate_implementation",
            "known_result_boundary",
            "freeze_attestation",
            "prior_search_lineage",
            "arms",
            "warm_reuse",
            "judge_calibration",
            "required_usage",
            "domains",
            "receiver_models",
            "operators",
            "sessions",
            "notes",
        ),
        "plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA:
        raise VerificationError("confirmatory gate plan schema differs")
    if plan["status"] != "frozen-preregistered-no-results":
        raise VerificationError("confirmatory gate plan must be frozen before results")
    _identifier(plan["study_id"], "plan.study_id")
    if plan["evidence_boundary"] not in EVIDENCE_BOUNDARIES:
        raise VerificationError("plan.evidence_boundary is invalid")
    _validate_base_method(plan["base_method"])
    _validate_gate_implementation(plan["gate_implementation"])
    _validate_known_boundary(plan["known_result_boundary"])
    freeze = _object(plan["freeze_attestation"], "plan.freeze_attestation")
    _exact(
        freeze,
        (
            "candidate_frozen_before_hidden_reveal",
            "baselines_selected_before_hidden_reveal",
            "tasks_unseen",
            "partners_unseen",
            "no_install",
            "no_retraining",
            "session_only",
            "no_optional_stopping",
        ),
        "plan.freeze_attestation",
    )
    if any(value is not True for value in freeze.values()):
        raise VerificationError("every freeze and unfamiliar-partner attestation must be true")
    _validate_lineage(plan["prior_search_lineage"])
    if plan["arms"] != list(ARMS):
        raise VerificationError("confirmatory arms must be raw, JSON, and hybrid")
    curve = _validate_warm_reuse(plan["warm_reuse"])
    calibration = _validate_calibration_plan(plan["judge_calibration"])
    _validate_required_usage(plan["required_usage"])
    matrix = _validate_plan_matrix(plan, curve)
    notes = _list(plan["notes"], "plan.notes")
    if not notes or any(type(item) is not str or not item.strip() for item in notes):
        raise VerificationError("plan.notes must contain nonempty text")
    return {
        "valid": True,
        "plan_sha256": sha256_ref(plan),
        "base_method_sha256": expected_base_method_binding()["canonical_sha256"],
        "curve": curve,
        "calibration": calibration,
        **matrix,
    }


def _validate_usage_record(
    value: Any,
    path: str,
    *,
    attempt_ids: MutableSet[str],
) -> tuple[str, int | None]:
    item = _object(value, path)
    _exact(
        item,
        (
            "phase",
            "attempt_id",
            "source",
            "terminal_status",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "reasoning_accounting",
            "total_tokens",
            "usage_receipt_sha256",
            "raw_usage_sha256",
        ),
        path,
    )
    if item["phase"] not in EVENT_PHASES:
        raise VerificationError(f"{path}.phase is unknown")
    attempt_id = _identifier(item["attempt_id"], f"{path}.attempt_id")
    if attempt_id in attempt_ids:
        raise VerificationError("usage attempt IDs cannot be replayed")
    attempt_ids.add(attempt_id)
    if item["source"] not in USAGE_SOURCES:
        raise VerificationError(f"{path}.source is unknown")
    if item["terminal_status"] not in TERMINAL_STATUSES:
        raise VerificationError(f"{path}.terminal_status is unknown")
    input_tokens = _nonnegative(item["input_tokens"], f"{path}.input_tokens", nullable=True)
    output_tokens = _nonnegative(item["output_tokens"], f"{path}.output_tokens", nullable=True)
    reasoning_tokens = _nonnegative(
        item["reasoning_tokens"], f"{path}.reasoning_tokens", nullable=True
    )
    total_tokens = _nonnegative(item["total_tokens"], f"{path}.total_tokens", nullable=True)
    if item["reasoning_accounting"] not in REASONING_ACCOUNTING:
        raise VerificationError(f"{path}.reasoning_accounting is unknown")
    for field in ("usage_receipt_sha256", "raw_usage_sha256"):
        if item[field] is not None:
            _sha(item[field], f"{path}.{field}")

    if item["source"] == "local":
        if any(value is not None for value in (input_tokens, output_tokens, reasoning_tokens)):
            raise VerificationError(f"{path} local usage cannot report provider token components")
        if item["reasoning_accounting"] != "none":
            raise VerificationError(f"{path} local usage reasoning accounting must be none")
        if item["terminal_status"] == "proven-zero" and total_tokens != 0:
            raise VerificationError(f"{path} proven-zero usage must total zero")
    else:
        if item["terminal_status"] == "proven-zero":
            raise VerificationError(f"{path} provider usage cannot be asserted proven zero")
        if item["reasoning_accounting"] == "none":
            raise VerificationError(f"{path} provider usage must declare reasoning accounting")
        if total_tokens is not None:
            if input_tokens is None or output_tokens is None:
                raise VerificationError(f"{path} complete provider total needs input and output")
            if item["reasoning_accounting"] == "included-in-output":
                if reasoning_tokens is None or reasoning_tokens > output_tokens:
                    raise VerificationError(f"{path} included reasoning is invalid")
                if total_tokens != input_tokens + output_tokens:
                    raise VerificationError(f"{path} provider total does not reconcile")
            elif item["reasoning_accounting"] == "separately-reported":
                if reasoning_tokens is None:
                    raise VerificationError(f"{path} separate reasoning is missing")
                if total_tokens != input_tokens + output_tokens + reasoning_tokens:
                    raise VerificationError(f"{path} provider total does not reconcile")
            elif reasoning_tokens is not None or total_tokens < input_tokens + output_tokens:
                raise VerificationError(f"{path} unreported reasoning usage is inconsistent")

    if total_tokens is not None and (
        item["usage_receipt_sha256"] is None or item["raw_usage_sha256"] is None
    ):
        raise VerificationError(f"{path} finite usage requires exact receipt digests")
    return item["phase"], total_tokens


def _validate_usage_records(
    value: Any,
    path: str,
    *,
    expected_phases: Sequence[str],
    attempt_ids: MutableSet[str],
) -> int | None:
    records = _list(value, path)
    if not records:
        raise VerificationError(f"{path} cannot be empty")
    totals: list[int | None] = []
    observed_phases: set[str] = set()
    for index, raw in enumerate(records):
        phase, total = _validate_usage_record(
            raw,
            f"{path}[{index}]",
            attempt_ids=attempt_ids,
        )
        if phase not in expected_phases:
            raise VerificationError(f"{path} contains usage from the wrong phase")
        observed_phases.add(phase)
        totals.append(total)
    if observed_phases != set(expected_phases):
        raise VerificationError(f"{path} does not cover every required phase")
    return None if any(item is None for item in totals) else sum(item or 0 for item in totals)


def _validate_turn(
    value: Any,
    planned: Mapping[str, Any],
    arm: str,
    path: str,
    *,
    attempt_ids: MutableSet[str],
    calibration_plan: Mapping[str, Any],
) -> dict[str, Any]:
    turn = _object(value, path)
    _exact(
        turn,
        (
            "task_id",
            "task_sha256",
            "task_success",
            "judge_safe_completion",
            "judge_scorer_implementation_sha256",
            "judge_scorer_settings_sha256",
            "judge_input_sha256",
            "judge_output_sha256",
            "judge_arm_identity_supplied_to_scorer",
            "capture_chain_valid",
            "intended_transmitted_match",
            "safety_violations",
            "parse_valid",
            "semantic_fidelity",
            "negative_rejected",
            "usage",
        ),
        path,
    )
    if turn["task_id"] != planned["task_id"] or turn["task_sha256"] != planned["task_sha256"]:
        raise VerificationError(f"{path} differs from its frozen task")
    task_success = _boolean(turn["task_success"], f"{path}.task_success")
    judge_safe = _boolean(turn["judge_safe_completion"], f"{path}.judge_safe_completion")
    if (
        turn["judge_scorer_implementation_sha256"]
        != calibration_plan["scorer_implementation_sha256"]
        or turn["judge_scorer_settings_sha256"]
        != calibration_plan["scorer_settings_sha256"]
    ):
        raise VerificationError(f"{path} task judge differs from its calibrated scorer")
    _sha(turn["judge_input_sha256"], f"{path}.judge_input_sha256")
    _sha(turn["judge_output_sha256"], f"{path}.judge_output_sha256")
    if turn["judge_arm_identity_supplied_to_scorer"] is not False:
        raise VerificationError(f"{path} task judge received arm identity")
    capture_chain_valid = _boolean(
        turn["capture_chain_valid"], f"{path}.capture_chain_valid"
    )
    capture_match = _boolean(
        turn["intended_transmitted_match"],
        f"{path}.intended_transmitted_match",
    )
    safety = _object(turn["safety_violations"], f"{path}.safety_violations")
    _exact(safety, SAFETY_FIELDS, f"{path}.safety_violations")
    safety_total = sum(
        _nonnegative(safety[field], f"{path}.safety_violations.{field}") or 0
        for field in SAFETY_FIELDS
    )
    probe_values: dict[str, bool | None] = {}
    for field, probe_field in (
        ("parse_valid", "parse_probe"),
        ("semantic_fidelity", "semantic_probe"),
        ("negative_rejected", "negative_probe"),
    ):
        value_at_field = turn[field]
        if arm != "hybrid-router" or not planned[probe_field]:
            if value_at_field is not None:
                raise VerificationError(f"{path}.{field} exceeds its frozen probe scope")
        else:
            value_at_field = _boolean(value_at_field, f"{path}.{field}")
        probe_values[field] = value_at_field
    usage_total = _validate_usage_records(
        turn["usage"],
        f"{path}.usage",
        expected_phases=NON_SETUP_PHASES,
        attempt_ids=attempt_ids,
    )
    return {
        "task_id": turn["task_id"],
        "usage_total": usage_total,
        "safe_completion": (
            task_success
            and judge_safe
            and safety_total == 0
            and capture_chain_valid
            and capture_match
            and all(value is not False for value in probe_values.values())
        ),
        "safety_total": safety_total,
        **probe_values,
    }


def _validate_arm_session(
    value: Any,
    *,
    arm: str,
    planned_tasks: Sequence[Mapping[str, Any]],
    curve: tuple[int, ...],
    path: str,
    attempt_ids: MutableSet[str],
    calibration_plan: Mapping[str, Any],
) -> dict[str, Any]:
    result = _object(value, path)
    _exact(
        result,
        (
            "arm_id",
            "context_id",
            "context_continuity_verified",
            "context_reset_or_compaction_observed",
            "shared_setup_usage",
            "turns",
            "reported_k_curve",
        ),
        path,
    )
    if result["arm_id"] != arm:
        raise VerificationError(f"{path}.arm_id differs")
    context_id = _identifier(result["context_id"], f"{path}.context_id")
    if result["context_continuity_verified"] is not True:
        raise VerificationError(f"{path} does not verify within-arm continuity")
    if result["context_reset_or_compaction_observed"] is not False:
        raise VerificationError(f"{path} cannot amortize across reset or compaction")
    setup_total = _validate_usage_records(
        result["shared_setup_usage"],
        f"{path}.shared_setup_usage",
        expected_phases=("setup",),
        attempt_ids=attempt_ids,
    )
    turns_raw = _list(result["turns"], f"{path}.turns")
    if len(turns_raw) != curve[-1]:
        raise VerificationError(f"{path}.turns differs from the registered horizon")
    turns = [
        _validate_turn(
            raw,
            planned_tasks[index],
            arm,
            f"{path}.turns[{index}]",
            attempt_ids=attempt_ids,
            calibration_plan=calibration_plan,
        )
        for index, raw in enumerate(turns_raw)
    ]
    computed_curve: list[dict[str, Any]] = []
    for k in curve:
        turn_totals = [item["usage_total"] for item in turns[:k]]
        total = (
            None
            if setup_total is None or any(item is None for item in turn_totals)
            else setup_total + sum(item or 0 for item in turn_totals)
        )
        computed_curve.append(
            {
                "k": k,
                "total_tokens": total,
                "safely_completed_tasks": sum(
                    int(item["safe_completion"]) for item in turns[:k]
                ),
            }
        )
    reported = _list(result["reported_k_curve"], f"{path}.reported_k_curve")
    if len(reported) != len(curve):
        raise VerificationError(f"{path}.reported_k_curve omits a registered K")
    for index, expected in enumerate(computed_curve):
        row_path = f"{path}.reported_k_curve[{index}]"
        row = _object(reported[index], row_path)
        _exact(row, ("k", "total_tokens", "safely_completed_tasks"), row_path)
        _nonnegative(row["k"], f"{row_path}.k")
        _nonnegative(
            row["total_tokens"], f"{row_path}.total_tokens", nullable=True
        )
        _nonnegative(
            row["safely_completed_tasks"],
            f"{row_path}.safely_completed_tasks",
        )
        if row != expected:
            raise VerificationError(f"{row_path} differs from setup-once recomputation")
    return {
        "context_id": context_id,
        "turns": tuple(turns),
        "curve": tuple(computed_curve),
    }


def _validate_calibration_result(
    value: Any,
    plan: Mapping[str, Any],
    *,
    attempt_ids: MutableSet[str],
) -> dict[str, Any]:
    calibration = _object(value, "result.judge_calibration")
    _exact(
        calibration,
        (
            "scorer_implementation_sha256",
            "scorer_settings_sha256",
            "arm_identity_supplied_to_scorer",
            "fixtures",
        ),
        "result.judge_calibration",
    )
    if calibration["scorer_implementation_sha256"] != plan["scorer_implementation_sha256"]:
        raise VerificationError("calibration scorer implementation differs")
    if calibration["scorer_settings_sha256"] != plan["scorer_settings_sha256"]:
        raise VerificationError("calibration scorer settings differ")
    if calibration["arm_identity_supplied_to_scorer"] is not False:
        raise VerificationError("calibration scorer received arm identity")

    expected: dict[tuple[str, str], dict[str, str]] = {}
    for defect in plan["matched_defects"]:
        for arm in ARMS:
            expected[(defect["matched_defect_id"], arm)] = {
                "semantic_defect_sha256": defect["semantic_defect_sha256"],
                **defect["blind_inputs"][arm],
            }
    fixtures = _list(calibration["fixtures"], "result.judge_calibration.fixtures")
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    blind_ids: set[str] = set()
    calibration_tokens: list[int | None] = []
    for index, raw in enumerate(fixtures):
        path = f"result.judge_calibration.fixtures[{index}]"
        item = _object(raw, path)
        _exact(
            item,
            (
                "matched_defect_id",
                "blind_id",
                "arm_id_revealed_after_scoring",
                "semantic_defect_sha256",
                "scorer_input_sha256",
                "detected",
                "judge_usage",
            ),
            path,
        )
        key = (item["matched_defect_id"], item["arm_id_revealed_after_scoring"])
        if key not in expected:
            raise VerificationError("calibration result contains an unplanned defect or arm")
        if key in observed:
            raise VerificationError("calibration result contains a duplicate arm/defect row")
        expected_row = expected[key]
        blind_id = item["blind_id"]
        if blind_id in blind_ids:
            raise VerificationError("calibration blind IDs cannot be replayed")
        blind_ids.add(blind_id)
        for field in ("blind_id", "semantic_defect_sha256", "scorer_input_sha256"):
            if item[field] != expected_row[field]:
                raise VerificationError(f"{path}.{field} differs from the frozen blind fixture")
        detected = item["detected"]
        if detected is not None:
            detected = _boolean(detected, f"{path}.detected")
        usage_total = _validate_usage_records(
            item["judge_usage"],
            f"{path}.judge_usage",
            expected_phases=("judge",),
            attempt_ids=attempt_ids,
        )
        calibration_tokens.append(usage_total)
        observed[key] = {"detected": detected, "usage_total": usage_total}

    complete = set(observed) == set(expected)
    rates: dict[str, Fraction | None] = {}
    for arm in ARMS:
        rows = [
            observed.get((defect["matched_defect_id"], arm))
            for defect in plan["matched_defects"]
        ]
        if any(
            row is None or row["detected"] is None or row["usage_total"] is None
            for row in rows
        ):
            rates[arm] = None
            complete = False
        else:
            rates[arm] = Fraction(
                sum(int(row["detected"]) for row in rows if row is not None),
                len(rows),
            )
    finite_rates = [value for value in rates.values() if value is not None]
    gap = None if len(finite_rates) != len(ARMS) else max(finite_rates) - min(finite_rates)
    passed = bool(
        complete
        and gap is not None
        and all(
            value is not None and value >= plan["minimum_detection_rate"]
            for value in rates.values()
        )
        and gap <= plan["maximum_between_arm_detection_gap"]
    )
    return {
        "complete": complete,
        "passed": passed,
        "rates": rates,
        "maximum_between_arm_gap": gap,
        "calibration_total_tokens": (
            None
            if any(item is None for item in calibration_tokens)
            else sum(item or 0 for item in calibration_tokens)
        ),
        "denominator_valid": {arm: passed for arm in ARMS},
    }


def _validate_authenticity(value: Any) -> dict[str, Any]:
    authenticity = _object(value, "result.authenticity")
    _exact(authenticity, AUTHENTICITY_FIELDS, "result.authenticity")
    flags = {
        field: _boolean(authenticity[field], f"result.authenticity.{field}")
        for field in AUTHENTICITY_FIELDS
    }
    return {
        "flags": flags,
        "caller_flags_complete": all(flags.values()),
        "cryptographically_verified_by_this_module": False,
        "complete": False,
    }


def _aggregate_curve(
    sessions: Sequence[Mapping[str, Any]], curve: tuple[int, ...]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, k in enumerate(curve):
        arms: dict[str, Any] = {}
        for arm in ARMS:
            rows = [session["arms"][arm]["curve"][index] for session in sessions]
            totals = [row["total_tokens"] for row in rows]
            arms[arm] = {
                "total_tokens": (
                    None
                    if any(item is None for item in totals)
                    else sum(item or 0 for item in totals)
                ),
                "safely_completed_tasks": sum(
                    row["safely_completed_tasks"] for row in rows
                ),
            }
        output.append({"k": k, "arms": arms})
    return output


def verify_confirmatory_session_gate(plan_value: Any, result_value: Any) -> dict[str, Any]:
    """Recompute the Reticuli gates; never emit claim authority."""

    plan_info = validate_confirmatory_plan(plan_value)
    plan = _object(plan_value, "plan")
    result = _object(result_value, "result")
    _exact(
        result,
        (
            "schema_version",
            "study_id",
            "plan_sha256",
            "result_status",
            "sessions",
            "judge_calibration",
            "authenticity",
            "notes",
        ),
        "result",
    )
    if result["schema_version"] != RESULT_SCHEMA:
        raise VerificationError("confirmatory gate result schema differs")
    if result["study_id"] != plan["study_id"]:
        raise VerificationError("result study identity differs")
    if result["plan_sha256"] != plan_info["plan_sha256"]:
        raise VerificationError("result does not bind the exact frozen confirmatory plan")
    if result["result_status"] not in {"completed", "partial", "failed", "declined"}:
        raise VerificationError("result status is invalid")
    notes = _list(result["notes"], "result.notes")
    if not notes or any(type(item) is not str or not item.strip() for item in notes):
        raise VerificationError("result.notes must contain nonempty text")

    attempt_ids: set[str] = set()
    calibration = _validate_calibration_result(
        result["judge_calibration"],
        plan_info["calibration"],
        attempt_ids=attempt_ids,
    )
    authenticity = _validate_authenticity(result["authenticity"])

    raw_sessions = _list(result["sessions"], "result.sessions")
    if len(raw_sessions) != len(plan_info["sessions"]):
        raise VerificationError("result must retain every planned whole session")
    normalized_sessions: list[dict[str, Any]] = []
    context_ids: set[str] = set()
    for index, planned in enumerate(plan_info["sessions"]):
        path = f"result.sessions[{index}]"
        session = _object(raw_sessions[index], path)
        _exact(
            session,
            (
                "session_id",
                "cluster_id",
                "domain_id",
                "receiver_family",
                "operator_id",
                "executed_arm_order",
                "arms",
            ),
            path,
        )
        for field in (
            "session_id",
            "cluster_id",
            "domain_id",
            "receiver_family",
            "operator_id",
        ):
            if session[field] != planned[field]:
                raise VerificationError(f"{path}.{field} differs from the frozen plan")
        if tuple(session["executed_arm_order"]) != planned["arm_order"]:
            raise VerificationError(f"{path}.executed_arm_order differs from the frozen plan")
        arms = _object(session["arms"], f"{path}.arms")
        _exact(arms, ARMS, f"{path}.arms")
        normalized_arms: dict[str, Any] = {}
        for arm in ARMS:
            normalized = _validate_arm_session(
                arms[arm],
                arm=arm,
                planned_tasks=planned["tasks"],
                curve=plan_info["curve"],
                path=f"{path}.arms.{arm}",
                attempt_ids=attempt_ids,
                calibration_plan=plan_info["calibration"],
            )
            if normalized["context_id"] in context_ids:
                raise VerificationError("arm sessions cannot reuse a provider context")
            context_ids.add(normalized["context_id"])
            normalized_arms[arm] = normalized
        normalized_sessions.append({**planned, "arms": normalized_arms})

    curve_summary = _aggregate_curve(normalized_sessions, plan_info["curve"])
    headline_index = len(plan_info["curve"]) - 1
    usage_complete = all(
        session["arms"][arm]["curve"][headline_index]["total_tokens"] is not None
        for session in normalized_sessions
        for arm in ARMS
    )
    all_safety_clear = all(
        turn["safety_total"] == 0
        for session in normalized_sessions
        for arm in ARMS
        for turn in session["arms"][arm]["turns"]
    )

    parse_n = parse_d = semantic_n = semantic_d = negative_n = negative_d = 0
    for session in normalized_sessions:
        for turn in session["arms"]["hybrid-router"]["turns"]:
            if turn["parse_valid"] is not None:
                parse_d += 1
                parse_n += int(turn["parse_valid"])
            if turn["semantic_fidelity"] is not None:
                semantic_d += 1
                semantic_n += int(turn["semantic_fidelity"])
            if turn["negative_rejected"] is not None:
                negative_d += 1
                negative_n += int(turn["negative_rejected"])
    parse_rate = _rate(parse_n, parse_d)
    semantic_rate = _rate(semantic_n, semantic_d)
    negative_rate = _rate(negative_n, negative_d)
    thresholds = load_frozen_method()["thresholds"]
    parse_passed = (
        parse_d == plan_info["probe_counts"]["parse_probe"]
        and Fraction(parse_n, parse_d)
        >= Fraction(str(thresholds["unseen_partner_parse_validity"]))
    )
    semantic_passed = (
        semantic_d == plan_info["probe_counts"]["semantic_probe"]
        and Fraction(semantic_n, semantic_d)
        >= Fraction(str(thresholds["held_out_semantic_fidelity"]))
    )
    negative_passed = (
        negative_d == plan_info["probe_counts"]["negative_probe"]
        and Fraction(negative_n, negative_d) >= Fraction(str(thresholds["negative_rejection"]))
    )

    comparisons = None
    if (
        result["result_status"] == "completed"
        and calibration["passed"]
        and usage_complete
    ):
        aggregates = []
        for session in normalized_sessions:
            aggregates.append(
                SessionAggregate(
                    session_id=session["session_id"],
                    cluster_id=session["cluster_id"],
                    domain_id=session["domain_id"],
                    receiver_family=session["receiver_family"],
                    operator_id=session["operator_id"],
                    planned_tasks=plan_info["curve"][-1],
                    safe_successes={
                        arm: session["arms"][arm]["curve"][headline_index][
                            "safely_completed_tasks"
                        ]
                        for arm in ARMS
                    },
                    total_tokens={
                        arm: session["arms"][arm]["curve"][headline_index][
                            "total_tokens"
                        ]
                        for arm in ARMS
                    },
                )
            )
        comparisons = compare_to_both_baselines(
            aggregates,
            seed_hex=hashlib.sha256(plan_info["plan_sha256"].encode("ascii")).hexdigest(),
            resamples=load_frozen_method()["analysis"]["bootstrap_resamples"],
        )

    diagnostic_metric_gate_passed = bool(
        calibration["passed"]
        and usage_complete
        and all_safety_clear
        and parse_passed
        and semantic_passed
        and negative_passed
        and comparisons is not None
        and comparisons["passed"]
    )
    blockers: list[str] = []
    if not calibration["passed"]:
        blockers.append("arm-blinded-matched-defect-calibration-failed-or-incomplete")
    if not usage_complete:
        blockers.append("complete-task-usage-is-unknown")
    if not all_safety_clear:
        blockers.append("noncompensable-safety-gate-failed")
    if not parse_passed:
        blockers.append("unseen-partner-parse-validity-below-99-percent")
    if not semantic_passed:
        blockers.append("held-out-semantic-fidelity-below-95-percent")
    if not negative_passed:
        blockers.append("negative-rejection-below-99.9-percent")
    if comparisons is None or not comparisons["passed"]:
        blockers.append("success-or-twenty-percent-token-lcb-gate-failed")
    if not authenticity["caller_flags_complete"]:
        blockers.append("caller-reported-authenticity-flags-incomplete")
    if not authenticity["flags"][
        "intermediary_attempt_and_cache_visibility_verified"
    ]:
        blockers.append("intermediary-retry-or-cache-visibility-unverified")
    blockers.append("standalone-v2-gate-does-not-authenticate-provider-provenance")
    if plan["evidence_boundary"] != "real-independent-evaluation":
        blockers.append("synthetic-test-only-not-claim-evidence")

    return {
        "schema_version": SUMMARY_SCHEMA,
        "study_id": plan["study_id"],
        "plan_sha256": plan_info["plan_sha256"],
        "base_frozen_v1_modified": False,
        "provider_or_model_calls_by_verifier": 0,
        "prior_search_lineage_bound": True,
        "registered_k_curve": list(plan_info["curve"]),
        "headline_k": plan_info["curve"][-1],
        "k_curve": curve_summary,
        "calibration": {
            "complete": calibration["complete"],
            "passed": calibration["passed"],
            "per_arm_detection_rate": {
                arm: _fraction_object(calibration["rates"][arm]) for arm in ARMS
            },
            "maximum_between_arm_gap": _fraction_object(
                calibration["maximum_between_arm_gap"]
            ),
            "calibration_total_tokens": calibration["calibration_total_tokens"],
            "denominator_valid": calibration["denominator_valid"],
        },
        "unseen_partner_parse_validity": parse_rate,
        "held_out_semantic_fidelity": semantic_rate,
        "negative_rejection": negative_rate,
        "usage_complete": usage_complete,
        "all_safety_clear": all_safety_clear,
        "diagnostic_baseline_comparisons": comparisons,
        "diagnostic_metric_gate_passed": diagnostic_metric_gate_passed,
        "authenticity": authenticity,
        "claim_facing_tokens_per_safely_completed_task": {
            arm: None for arm in ARMS
        },
        "claim_facing_complete_total_tokens": {arm: None for arm in ARMS},
        "claim_facing_total_token_reduction_lcb": None,
        "goal_gate_passed": False,
        "claim_eligible": False,
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
        "claim_blockers": blockers,
    }


__all__ = [
    "AUTHENTICITY_FIELDS",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "SUMMARY_SCHEMA",
    "expected_base_method_binding",
    "expected_gate_implementation_binding",
    "validate_confirmatory_plan",
    "verify_confirmatory_session_gate",
]
