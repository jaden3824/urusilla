"""Corrected zero-call finite-bound arithmetic consumer.

Schema ``/3`` separates a zero numerical lower bound from proof that a phase is
absent.  The legacy ``/2`` consumer required every all-zero vector to be called
``proved-zero``; that label is false for a conditional candidate repair or
fallback whose sound lower bound is zero.  This module validates the corrected
labels, projects only the already-validated numbers into the legacy exact
integer arithmetic, and binds the returned rows back to the original ``/3``
path objects.

The projection is an implementation reuse, not evidence reuse.  Both versions
remain conditional, zero-call, and claim-ineligible.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contract import IDENTIFIER_RE, VerificationError, sha256_ref
from .feasibility_kill_screen_v1 import (
    EXACT_ASSUMPTIONS_SHA256 as LEGACY_ASSUMPTIONS_SHA256,
    FEASIBILITY_PLAN_SCHEMA as LEGACY_PLAN_SCHEMA,
    EVALUATION_REFERENCE as LEGACY_EVALUATION_REFERENCE,
    PATHS,
    PHASES,
    PLAN_STATUS,
    SESSION_LENGTHS,
    TARGET_REDUCTION_BASIS_POINTS,
    _assumptions as _legacy_assumptions,
    run_feasibility_kill_screen as run_legacy_screen,
)


FEASIBILITY_PLAN_SCHEMA = "urusilla-initial-goal-feasibility-kill-screen-plan/3"
FEASIBILITY_RESULT_SCHEMA = "urusilla-initial-goal-feasibility-kill-screen-result/3"
EVALUATION_REFERENCE = "urusilla-initial-goal-raw-json-feasibility/3"
BOUND_KINDS = (
    "derived-lower-bound",
    "derived-upper-bound",
    "proved-absent",
    "proved-zero",
)
_MAX_TOKEN_BOUND = (1 << 63) - 1


class FeasibilityKillScreenV3Error(VerificationError):
    """A corrected bound plan is malformed or semantically mislabeled."""


def _keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    if any(type(key) is not str for key in value) or set(value) != expected:
        raise FeasibilityKillScreenV3Error(f"{path}:exact-keys-required")


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise FeasibilityKillScreenV3Error(f"{path}:object-required")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise FeasibilityKillScreenV3Error(f"{path}:array-required")
    return value


def _project_plan(plan: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    source = _object(plan, "plan")
    _keys(
        source,
        {
            "schema_version",
            "evaluation_id",
            "status",
            "target_reduction_basis_points",
            "session_lengths",
            "registration",
            "rows",
        },
        "plan",
    )
    if (
        source["schema_version"] != FEASIBILITY_PLAN_SCHEMA
        or source["evaluation_id"] != EVALUATION_REFERENCE
        or source["status"] != PLAN_STATUS
        or source["target_reduction_basis_points"]
        != TARGET_REDUCTION_BASIS_POINTS
        or source["session_lengths"] != list(SESSION_LENGTHS)
    ):
        raise FeasibilityKillScreenV3Error("plan:unknown-or-drifted-contract")
    rows = _array(source["rows"], "plan.rows")
    if not rows or len(rows) > 128:
        raise FeasibilityKillScreenV3Error("plan.rows:must-have-1..128-entries")

    projected: dict[str, Any] = {
        "schema_version": LEGACY_PLAN_SCHEMA,
        "evaluation_id": LEGACY_EVALUATION_REFERENCE,
        "status": source["status"],
        "target_reduction_basis_points": source[
            "target_reduction_basis_points"
        ],
        "session_lengths": source["session_lengths"],
        "registration": source["registration"],
        "rows": [],
    }
    original_path_hashes: list[dict[str, str]] = []
    for row_index, row_value in enumerate(rows):
        row = _object(row_value, f"plan.rows[{row_index}]")
        _keys(
            row,
            {
                "domain_id",
                "domain_manifest_sha256",
                "tokenizer_id",
                "tokenizer_sha256",
                "bound_manifest_sha256",
                "paths",
            },
            f"plan.rows[{row_index}]",
        )
        paths = _object(row.get("paths"), f"plan.rows[{row_index}].paths")
        _keys(paths, set(PATHS), f"plan.rows[{row_index}].paths")
        row_hashes: dict[str, str] = {}
        projected_row = {
            key: row[key]
            for key in (
                "domain_id",
                "domain_manifest_sha256",
                "tokenizer_id",
                "tokenizer_sha256",
                "bound_manifest_sha256",
            )
        }
        projected_row["paths"] = {}
        for path_name in PATHS:
            path = _object(paths[path_name], f"plan.rows[{row_index}].paths.{path_name}")
            _keys(
                path,
                {"bound_direction", "success_direction", "safe_successes_by_n", "phases"},
                f"plan.rows[{row_index}].paths.{path_name}",
            )
            phases = _array(
                path["phases"], f"plan.rows[{row_index}].paths.{path_name}.phases"
            )
            if len(phases) != len(PHASES):
                raise FeasibilityKillScreenV3Error(
                    f"plan.rows[{row_index}].paths.{path_name}.phases:wrong-length"
                )
            row_hashes[path_name] = sha256_ref(path)
            projected_path = {
                "bound_direction": path["bound_direction"],
                "success_direction": path["success_direction"],
                "safe_successes_by_n": path["safe_successes_by_n"],
                "phases": [],
            }
            for phase_index, expected_phase in enumerate(PHASES):
                phase = _object(
                    phases[phase_index],
                    f"plan.rows[{row_index}].paths.{path_name}.phases[{phase_index}]",
                )
                _keys(
                    phase,
                    {"phase", "bound_kind", "tokens_by_n"},
                    f"plan.rows[{row_index}].paths.{path_name}.phases[{phase_index}]",
                )
                vector = _array(
                    phase["tokens_by_n"],
                    f"plan.rows[{row_index}].paths.{path_name}.phases[{phase_index}].tokens_by_n",
                )
                if (
                    phase["phase"] != expected_phase
                    or len(vector) != len(SESSION_LENGTHS)
                    or any(
                        type(item) is not int
                        or item < 0
                        or item > _MAX_TOKEN_BOUND
                        for item in vector
                    )
                ):
                    raise FeasibilityKillScreenV3Error(
                        f"plan.rows[{row_index}].paths.{path_name}.phases[{phase_index}]:invalid-vector"
                    )
                all_zero = all(item == 0 for item in vector)
                kind = phase["bound_kind"]
                if path_name == "action-state":
                    allowed = (
                        {
                            "proved-absent",
                            "proved-zero",
                            "derived-lower-bound",
                        }
                        if all_zero
                        else {"derived-lower-bound"}
                    )
                else:
                    allowed = (
                        {"proved-absent", "proved-zero"}
                        if all_zero
                        else {"derived-upper-bound"}
                    )
                if kind not in allowed:
                    raise FeasibilityKillScreenV3Error(
                        f"plan.rows[{row_index}].paths.{path_name}.phases[{phase_index}]:bound-kind-mismatch"
                    )
                projected_phase = {
                    "phase": phase["phase"],
                    "bound_kind": (
                        "proved-zero"
                        if all_zero
                        else (
                            "proved-lower-bound"
                            if path_name == "action-state"
                            else "proved-upper-bound"
                        )
                    ),
                    "tokens_by_n": vector,
                }
                projected_path["phases"].append(projected_phase)
            projected_row["paths"][path_name] = projected_path
        original_path_hashes.append(row_hashes)
        projected["rows"].append(projected_row)
    return source, {
        "projected_plan": projected,
        "original_path_hashes": original_path_hashes,
    }


def _assumptions() -> dict[str, object]:
    legacy = _legacy_assumptions()
    if sha256_ref(legacy) != LEGACY_ASSUMPTIONS_SHA256:
        raise FeasibilityKillScreenV3Error("legacy-assumptions:digest-drift")
    return {
        "arithmetic": "legacy-v2-exact-integer-projection-after-v3-semantic-validation",
        "legacy_arithmetic_contract": legacy,
        "legacy_arithmetic_contract_sha256": LEGACY_ASSUMPTIONS_SHA256,
        "v3_zero_label_contract": {
            "zero_candidate_lower_bound": (
                "derived-lower-bound-zero-is-distinct-from-proved-absent"
            ),
            "zero_baseline_upper_bound": "must-be-proved-absent-or-proved-zero",
            "proved_zero": "phase-present-but-closed-local-model-token-charge-is-zero",
        },
        "v3_nonclaims": {
            "not_disproven_interpretation": (
                "absence-of-this-arithmetic-impossibility-only"
            ),
            "provider_calls": 0,
            "model_calls": 0,
            "claim_eligible": False,
        },
    }


def run_feasibility_kill_screen(plan: Any) -> dict[str, object]:
    """Validate corrected labels and reuse the legacy exact arithmetic only."""

    try:
        source, projection = _project_plan(plan)
        legacy = run_legacy_screen(projection["projected_plan"])
        if legacy["outcome"] == "invalid":
            raise FeasibilityKillScreenV3Error(
                f"arithmetic-projection:{legacy.get('error', 'invalid')}"
            )
        if (
            legacy.get("assumptions_sha256") != LEGACY_ASSUMPTIONS_SHA256
            or legacy.get("assumptions") != _legacy_assumptions()
        ):
            raise FeasibilityKillScreenV3Error(
                "arithmetic-projection:legacy-assumptions-drift"
            )
        rows = deepcopy(legacy["rows"])
        for index, row in enumerate(rows):
            row["path_bounds_sha256"] = projection["original_path_hashes"][index]
        assumptions = _assumptions()
        return {
            "schema_version": FEASIBILITY_RESULT_SCHEMA,
            "evaluation_reference": EVALUATION_REFERENCE,
            "outcome": legacy["outcome"],
            "plan_sha256": sha256_ref(source),
            "registration_sha256": sha256_ref(source["registration"]),
            "assumptions": assumptions,
            "assumptions_sha256": sha256_ref(assumptions),
            "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
            "session_lengths": list(SESSION_LENGTHS),
            "rows": rows,
            "arithmetic_projection_sha256": sha256_ref(
                projection["projected_plan"]
            ),
            "provider_calls_performed": 0,
            "model_calls_performed": 0,
            "claim_eligible": False,
        }
    except (FeasibilityKillScreenV3Error, VerificationError, KeyError, TypeError) as exc:
        assumptions = _assumptions()
        return {
            "schema_version": FEASIBILITY_RESULT_SCHEMA,
            "evaluation_reference": EVALUATION_REFERENCE,
            "outcome": "invalid",
            "plan_sha256": None,
            "registration_sha256": None,
            "assumptions": assumptions,
            "assumptions_sha256": sha256_ref(assumptions),
            "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
            "session_lengths": list(SESSION_LENGTHS),
            "rows": [],
            "arithmetic_projection_sha256": None,
            "error": str(exc),
            "provider_calls_performed": 0,
            "model_calls_performed": 0,
            "claim_eligible": False,
        }


__all__ = [
    "BOUND_KINDS",
    "EVALUATION_REFERENCE",
    "FEASIBILITY_PLAN_SCHEMA",
    "FEASIBILITY_RESULT_SCHEMA",
    "FeasibilityKillScreenV3Error",
    "run_feasibility_kill_screen",
]
