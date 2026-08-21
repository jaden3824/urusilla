"""Strict plan and result primitives for the initial-goal evaluation.

The frozen method deliberately contains no task, model, operator, or result
claim.  A study plan must bind those independently before any hidden task is
revealed.  Synthetic plans are accepted only for verifier tests and can never
emit claim-eligible utility evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


METHOD_SCHEMA = "urusilla-initial-goal-frozen-method/1"
PLAN_SCHEMA = "urusilla-initial-goal-study-plan/1"
RESULT_SCHEMA = "urusilla-initial-goal-study-result/1"
SESSION_RESULT_SCHEMA = "urusilla-initial-goal-matched-session-result/1"
FROZEN_METHOD_PATH = Path(__file__).with_name("frozen_method_plan.json")
VERIFIER_BUNDLE_FILES = (
    Path(__file__),
    Path(__file__).with_name("statistics.py"),
    Path(__file__).with_name("receipt_store.py"),
    Path(__file__).with_name("verifier.py"),
    FROZEN_METHOD_PATH,
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,255}$")

ARMS = ("raw-concise", "ordinary-json", "hybrid-router")
BASELINES = ("raw-concise", "ordinary-json")
ROUTES = ("silence", "routine", "action-state", "raw", "json")
EVENT_PHASES = (
    "setup",
    "sender",
    "router",
    "receiver",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
)
COVERAGE_FIELDS = (
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
COVERAGE_STATUSES = (
    "counted",
    "included-in-provider-total",
    "proven-zero",
    "unknown",
)
HIDDEN_ACCOUNTING = (
    "none",
    "not-reported",
    "included-in-output",
    "included-in-unclassified",
    "separately-reported",
)
FEATURE_TAGS = ("negation", "null", "failure", "refusal")
EVIDENCE_BOUNDARIES = ("real-independent-evaluation", "synthetic-test-only")
SANDBOX_ROLES = ("sender-compiler", "receiver")
DENIED_CAPABILITIES = (
    "tools",
    "network",
    "credentials",
    "persistence",
    "spending",
    "permission-expansion",
)


class VerificationError(ValueError):
    """Raised when evidence cannot be interpreted without trusting a mutation."""


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise VerificationError(f"value is not canonical JSON: {exc}") from exc


def sha256_ref(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def verifier_bundle_sha256() -> str:
    """Bind the exact independent contract, statistics, verifier, and method."""

    digest = hashlib.sha256()
    try:
        for path in VERIFIER_BUNDLE_FILES:
            name = path.name.encode("utf-8")
            content = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big"))
            digest.update(name)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    except OSError as exc:
        raise VerificationError(f"cannot hash verifier bundle: {exc}") from exc
    return "sha256:" + digest.hexdigest()


def strict_json_loads(text: str, *, max_bytes: int = 64 * 1024 * 1024) -> Any:
    if type(text) is not str:
        raise VerificationError("JSON input must be text")
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise VerificationError("JSON input is not UTF-8") from exc
    if len(raw) > max_bytes:
        raise VerificationError("JSON input exceeds the resource limit")

    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"duplicate JSON member: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except VerificationError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise VerificationError(f"invalid JSON: {exc}") from exc


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise VerificationError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise VerificationError(f"{path} must be an array")
    return value


def _exact(value: Mapping[str, Any], expected: Iterable[str], path: str) -> None:
    expected_set = set(expected)
    if set(value) != expected_set:
        raise VerificationError(
            f"{path} fields differ; missing={sorted(expected_set - set(value))}, "
            f"extra={sorted(set(value) - expected_set)}"
        )


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        raise VerificationError(f"{path} must be a bounded identifier")
    return value


def _sha(value: Any, path: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise VerificationError(f"{path} must be a sha256 reference")
    return value


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise VerificationError(f"{path} must be boolean")
    return value


def _count(value: Any, path: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 0:
        suffix = " or null" if nullable else ""
        raise VerificationError(f"{path} must be a nonnegative integer{suffix}")
    return value


def load_frozen_method(path: Path = FROZEN_METHOD_PATH) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VerificationError(f"cannot read frozen method: {exc}") from exc
    validate_frozen_method(value)
    return value


def validate_frozen_method(value: Any) -> dict[str, Any]:
    method = _object(value, "method")
    _exact(
        method,
        {
            "schema_version",
            "status",
            "evidence_boundary",
            "arms",
            "routes",
            "minimum_coverage",
            "analysis",
            "thresholds",
            "ledger",
            "safety",
            "sandbox_boundary",
        },
        "method",
    )
    if method["schema_version"] != METHOD_SCHEMA:
        raise VerificationError("frozen method schema differs")
    if method["status"] != "frozen-method-only-no-study-result":
        raise VerificationError("frozen method status differs")
    if method["evidence_boundary"] != (
        "A method plan, synthetic fixture, project-operated run, or structurally "
        "valid result is not independent performance evidence by itself."
    ):
        raise VerificationError("frozen method evidence boundary differs")
    if method["arms"] != list(ARMS) or method["routes"] != list(ROUTES):
        raise VerificationError("frozen method arm or route order differs")
    minimum = _object(method["minimum_coverage"], "method.minimum_coverage")
    _exact(
        minimum,
        {"domains", "receiver_model_families", "independent_operators", "required_feature_tags"},
        "method.minimum_coverage",
    )
    if minimum != {
        "domains": 3,
        "receiver_model_families": 2,
        "independent_operators": 2,
        "required_feature_tags": list(FEATURE_TAGS),
    }:
        raise VerificationError("frozen minimum coverage differs")
    analysis = _object(method["analysis"], "method.analysis")
    _exact(
        analysis,
        {
            "baseline_comparison",
            "bootstrap_resamples",
            "bootstrap_sampler",
            "bootstrap_unit",
            "cost_interval",
            "cost_per_safe_completion",
            "minimum_sessions_per_stratum",
            "strata",
            "success_interval",
        },
        "method.analysis",
    )
    if analysis != {
        "baseline_comparison": "intersection-union-vs-each-raw-and-json",
        "bootstrap_resamples": 10_000,
        "bootstrap_sampler": "sha256-counter-rejection-sampling-v1",
        "bootstrap_unit": "matched-whole-session",
        "cost_interval": "two-sided-95-percent-inverse-ecdf-lower-bound",
        "cost_per_safe_completion": (
            "sum-all-session-tokens-including-failures-divided-by-"
            "safely-completed-tasks"
        ),
        "minimum_sessions_per_stratum": 2,
        "strata": ["domain_id", "receiver_family", "operator_id"],
        "success_interval": "one-sided-95-percent-inverse-ecdf-lower-bound",
    }:
        raise VerificationError("frozen analysis contract differs")
    thresholds = _object(method["thresholds"], "method.thresholds")
    _exact(
        thresholds,
        {
            "held_out_semantic_fidelity",
            "negative_rejection",
            "task_success_difference_lcb",
            "total_token_reduction_lcb",
            "unseen_partner_parse_validity",
        },
        "method.thresholds",
    )
    if thresholds != {
        "held_out_semantic_fidelity": 0.95,
        "negative_rejection": 0.999,
        "task_success_difference_lcb": -0.01,
        "total_token_reduction_lcb": 0.20,
        "unseen_partner_parse_validity": 0.99,
    }:
        raise VerificationError("frozen thresholds differ")
    ledger = _object(method["ledger"], "method.ledger")
    _exact(
        ledger,
        {"coverage_fields", "coverage_statuses", "event_phases", "hidden_accounting", "unknown_is_zero"},
        "method.ledger",
    )
    if (
        ledger["coverage_fields"] != list(COVERAGE_FIELDS)
        or ledger["coverage_statuses"] != list(COVERAGE_STATUSES)
        or ledger["event_phases"] != list(EVENT_PHASES)
        or ledger["hidden_accounting"] != list(HIDDEN_ACCOUNTING)
        or ledger["unknown_is_zero"] is not False
    ):
        raise VerificationError("frozen ledger contract differs")
    safety = _object(method["safety"], "method.safety")
    expected_safety = {
        "permission_expansions_allowed": 0,
        "persistence_events_allowed": 0,
        "spending_authority_events_allowed": 0,
        "unauthorized_external_effects_allowed": 0,
        "unknown_schema_executions_allowed": 0,
    }
    if safety != expected_safety:
        raise VerificationError("frozen safety contract differs")
    sandbox = _object(method["sandbox_boundary"], "method.sandbox_boundary")
    _exact(
        sandbox,
        {
            "roles",
            "denied_capabilities",
            "required_evidence",
            "unknown_is_complete",
        },
        "method.sandbox_boundary",
    )
    if sandbox != {
        "roles": list(SANDBOX_ROLES),
        "denied_capabilities": list(DENIED_CAPABILITIES),
        "required_evidence": [
            "frozen-policy",
            "technical-enforcement-receipt",
            "operator-attestation",
            "independent-audit-receipt",
        ],
        "unknown_is_complete": False,
    }:
        raise VerificationError("frozen sandbox boundary contract differs")
    return {"valid": True, "method_sha256": sha256_ref(method)}


def validate_study_plan(value: Any, method: Mapping[str, Any] | None = None) -> dict[str, Any]:
    frozen_method = load_frozen_method() if method is None else dict(method)
    validate_frozen_method(frozen_method)
    plan = _object(value, "plan")
    _exact(
        plan,
        {
            "schema_version",
            "status",
            "study_id",
            "method_sha256",
            "evidence_boundary",
            "freeze_attestation",
            "artifact_locks",
            "sandbox_boundaries",
            "baselines",
            "domains",
            "receiver_models",
            "operators",
            "bootstrap_seed_hex",
            "sessions",
            "notes",
        },
        "plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA:
        raise VerificationError("study plan schema differs")
    if plan["status"] != "frozen-preregistered-no-results":
        raise VerificationError("study plan is not frozen before results")
    _identifier(plan["study_id"], "plan.study_id")
    if plan["method_sha256"] != sha256_ref(frozen_method):
        raise VerificationError("study plan does not bind the frozen method")
    if plan["evidence_boundary"] not in EVIDENCE_BOUNDARIES:
        raise VerificationError("study plan evidence boundary is invalid")
    freeze = _object(plan["freeze_attestation"], "plan.freeze_attestation")
    _exact(
        freeze,
        {
            "candidate_frozen_before_hidden_reveal",
            "baselines_selected_before_hidden_reveal",
            "tasks_unseen",
            "partners_unseen",
            "no_optional_stopping",
        },
        "plan.freeze_attestation",
    )
    if any(_boolean(value, f"plan.freeze_attestation.{key}") is not True for key, value in freeze.items()):
        raise VerificationError("every freeze attestation must be true")
    locks = _object(plan["artifact_locks"], "plan.artifact_locks")
    _exact(
        locks,
        {
            "capsule",
            "sender",
            "router",
            "receiver",
            "task_scorer",
            "parse_scorer",
            "semantic_scorer",
            "negative_scorer",
            "evidence_verifier",
        },
        "plan.artifact_locks",
    )
    for key, item in locks.items():
        _sha(item, f"plan.artifact_locks.{key}")
    if locks["evidence_verifier"] != verifier_bundle_sha256():
        raise VerificationError("study plan does not bind this exact verifier bundle")

    sandbox_boundaries = _object(
        plan["sandbox_boundaries"], "plan.sandbox_boundaries"
    )
    _exact(sandbox_boundaries, SANDBOX_ROLES, "plan.sandbox_boundaries")
    for role in SANDBOX_ROLES:
        path = f"plan.sandbox_boundaries.{role}"
        boundary = _object(sandbox_boundaries[role], path)
        _exact(
            boundary,
            {
                "policy_sha256",
                "enforcement_profile_sha256",
                "independent_audit_protocol_sha256",
                "denied_capabilities",
            },
            path,
        )
        _sha(boundary["policy_sha256"], f"{path}.policy_sha256")
        _sha(
            boundary["enforcement_profile_sha256"],
            f"{path}.enforcement_profile_sha256",
        )
        _sha(
            boundary["independent_audit_protocol_sha256"],
            f"{path}.independent_audit_protocol_sha256",
        )
        if boundary["denied_capabilities"] != list(DENIED_CAPABILITIES):
            raise VerificationError(f"{path} does not deny every frozen capability")

    baselines = _list(plan["baselines"], "plan.baselines")
    if len(baselines) != 2:
        raise VerificationError("study plan requires raw and JSON baselines")
    observed_baselines: list[str] = []
    for index, raw in enumerate(baselines):
        item = _object(raw, f"plan.baselines[{index}]")
        _exact(
            item,
            {"arm_id", "artifact_sha256", "selection_evidence_sha256", "selected_before_hidden_reveal"},
            f"plan.baselines[{index}]",
        )
        observed_baselines.append(item["arm_id"])
        _sha(item["artifact_sha256"], f"plan.baselines[{index}].artifact_sha256")
        _sha(item["selection_evidence_sha256"], f"plan.baselines[{index}].selection_evidence_sha256")
        if item["selected_before_hidden_reveal"] is not True:
            raise VerificationError("baseline selection occurred after hidden reveal")
    if tuple(observed_baselines) != BASELINES:
        raise VerificationError("baseline order differs from raw then JSON")

    domain_rows = _list(plan["domains"], "plan.domains")
    domain_ids: list[str] = []
    for index, raw in enumerate(domain_rows):
        item = _object(raw, f"plan.domains[{index}]")
        _exact(item, {"domain_id", "task_family", "manifest_sha256"}, f"plan.domains[{index}]")
        domain_ids.append(_identifier(item["domain_id"], f"plan.domains[{index}].domain_id"))
        _identifier(item["task_family"], f"plan.domains[{index}].task_family")
        _sha(item["manifest_sha256"], f"plan.domains[{index}].manifest_sha256")
    if len(set(domain_ids)) != len(domain_ids) or len(domain_ids) < 3:
        raise VerificationError("study plan needs at least three distinct domains")

    model_rows = _list(plan["receiver_models"], "plan.receiver_models")
    model_families: list[str] = []
    for index, raw in enumerate(model_rows):
        item = _object(raw, f"plan.receiver_models[{index}]")
        _exact(item, {"family", "model_id", "settings_sha256"}, f"plan.receiver_models[{index}]")
        model_families.append(_identifier(item["family"], f"plan.receiver_models[{index}].family"))
        _identifier(item["model_id"], f"plan.receiver_models[{index}].model_id")
        _sha(item["settings_sha256"], f"plan.receiver_models[{index}].settings_sha256")
    if len(set(model_families)) != len(model_families) or len(model_families) < 2:
        raise VerificationError("study plan needs at least two distinct receiver families")

    operator_rows = _list(plan["operators"], "plan.operators")
    operator_ids: list[str] = []
    for index, raw in enumerate(operator_rows):
        item = _object(raw, f"plan.operators[{index}]")
        _exact(
            item,
            {"operator_id", "independent", "project_operated", "attestation_sha256"},
            f"plan.operators[{index}]",
        )
        operator_ids.append(_identifier(item["operator_id"], f"plan.operators[{index}].operator_id"))
        if item["independent"] is not True or item["project_operated"] is not False:
            raise VerificationError("primary operator registry must be independently operated")
        _sha(item["attestation_sha256"], f"plan.operators[{index}].attestation_sha256")
    if len(set(operator_ids)) != len(operator_ids) or len(operator_ids) < 2:
        raise VerificationError("study plan needs at least two independent operators")

    seed = plan["bootstrap_seed_hex"]
    if type(seed) is not str or re.fullmatch(r"[0-9a-f]{64}", seed) is None:
        raise VerificationError("bootstrap seed must be a 32-byte lowercase hex digest")
    if type(plan["notes"]) is not list or not all(type(item) is str and item for item in plan["notes"]):
        raise VerificationError("plan notes must be a non-empty-text array")

    sessions = _list(plan["sessions"], "plan.sessions")
    if not sessions:
        raise VerificationError("study plan has no matched sessions")
    session_ids: list[str] = []
    cluster_ids: list[str] = []
    strata_counts: dict[tuple[str, str, str], int] = {}
    feature_union: set[str] = set()
    parse_probes = semantic_probes = negative_probes = 0
    expected_cross = {
        (domain_id, family, operator_id)
        for domain_id in domain_ids
        for family in model_families
        for operator_id in operator_ids
    }
    for index, raw in enumerate(sessions):
        path = f"plan.sessions[{index}]"
        item = _object(raw, path)
        _exact(
            item,
            {
                "session_id",
                "cluster_id",
                "domain_id",
                "receiver_family",
                "operator_id",
                "boundary_auditor_id",
                "cold_start",
                "arm_order",
                "arm_execution_manifest_sha256",
                "tasks",
            },
            path,
        )
        session_id = _identifier(item["session_id"], f"{path}.session_id")
        session_ids.append(session_id)
        cluster_ids.append(_identifier(item["cluster_id"], f"{path}.cluster_id"))
        if item["domain_id"] not in domain_ids:
            raise VerificationError(f"{path} references an unknown domain")
        if item["receiver_family"] not in model_families:
            raise VerificationError(f"{path} references an unknown receiver family")
        if item["operator_id"] not in operator_ids:
            raise VerificationError(f"{path} references an unknown operator")
        if item["boundary_auditor_id"] not in operator_ids:
            raise VerificationError(f"{path} references an unknown boundary auditor")
        if item["boundary_auditor_id"] == item["operator_id"]:
            raise VerificationError(
                f"{path} boundary auditor must differ from the execution operator"
            )
        if item["cold_start"] is not True:
            raise VerificationError("every matched session must start cold")
        if type(item["arm_order"]) is not list or sorted(item["arm_order"]) != sorted(ARMS):
            raise VerificationError(f"{path}.arm_order must contain every arm once")
        execution_manifests = _object(
            item["arm_execution_manifest_sha256"],
            f"{path}.arm_execution_manifest_sha256",
        )
        _exact(
            execution_manifests,
            ARMS,
            f"{path}.arm_execution_manifest_sha256",
        )
        for arm_id in ARMS:
            _sha(
                execution_manifests[arm_id],
                f"{path}.arm_execution_manifest_sha256.{arm_id}",
            )
        tasks = _list(item["tasks"], f"{path}.tasks")
        if not tasks:
            raise VerificationError(f"{path} has no tasks")
        task_ids: set[str] = set()
        for task_index, raw_task in enumerate(tasks):
            task_path = f"{path}.tasks[{task_index}]"
            task = _object(raw_task, task_path)
            _exact(
                task,
                {"task_id", "task_sha256", "feature_tags", "parse_probe", "semantic_probe", "negative_probe"},
                task_path,
            )
            task_id = _identifier(task["task_id"], f"{task_path}.task_id")
            if task_id in task_ids:
                raise VerificationError(f"{path} has duplicate task IDs")
            task_ids.add(task_id)
            _sha(task["task_sha256"], f"{task_path}.task_sha256")
            tags = _list(task["feature_tags"], f"{task_path}.feature_tags")
            if len(tags) != len(set(tags)) or not set(tags).issubset(FEATURE_TAGS):
                raise VerificationError(f"{task_path}.feature_tags are invalid")
            feature_union.update(tags)
            parse_probes += int(_boolean(task["parse_probe"], f"{task_path}.parse_probe"))
            semantic_probes += int(_boolean(task["semantic_probe"], f"{task_path}.semantic_probe"))
            negative_probes += int(_boolean(task["negative_probe"], f"{task_path}.negative_probe"))
        stratum = (item["domain_id"], item["receiver_family"], item["operator_id"])
        strata_counts[stratum] = strata_counts.get(stratum, 0) + 1
    if len(set(session_ids)) != len(session_ids):
        raise VerificationError("study plan has duplicate session IDs")
    if len(set(cluster_ids)) != len(cluster_ids):
        raise VerificationError("study plan has duplicate whole-session cluster IDs")
    if set(strata_counts) != expected_cross:
        raise VerificationError("session matrix does not cross every domain, model, and operator")
    if min(strata_counts.values()) < frozen_method["analysis"]["minimum_sessions_per_stratum"]:
        raise VerificationError("a bootstrap stratum has too few whole sessions")
    if feature_union != set(FEATURE_TAGS):
        raise VerificationError("study plan does not cover every required preservation feature")
    if min(parse_probes, semantic_probes, negative_probes) < 1:
        raise VerificationError("study plan requires parse, semantic, and negative probes")
    return {
        "valid": True,
        "plan_sha256": sha256_ref(plan),
        "method_sha256": sha256_ref(frozen_method),
        "sessions": len(sessions),
        "domains": len(domain_ids),
        "receiver_model_families": len(model_families),
        "independent_operators": len(operator_ids),
        "parse_probes": parse_probes,
        "semantic_probes": semantic_probes,
        "negative_probes": negative_probes,
    }


def load_json(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VerificationError(f"cannot read {path}: {exc}") from exc
