"""Deterministic zero-call feasibility screen for the action-state path.

This is a separately versioned arithmetic screen.  It consumes caller-frozen
phase bounds for session lengths 1 through 128 and asks only whether the
current action-state path is *provably unable* to reach a 20% inclusive-token
reduction against the better of raw concise text and ordinary JSON.

The candidate uses phase-wise lower bounds and the baselines use phase-wise
upper bounds.  Safe-success denominators are bounded separately, so a baseline
failure cannot be silently treated as a free successful task.  Setup and cold
comprehension are mandatory positive candidate obligations at every evaluated
session length.  A causal-study phase remains in the closed phase vocabulary
but is not endpoint overhead unless the registered allowed path actually
incurs it; it may therefore be explicitly proved zero.  Every phase must be
present and is either finitely bounded or explicitly proved zero.

A baseline minimum safe-success bound of zero is an admissible statement that
no positive lower bound is known.  Such a path cannot provide a finite upper
bound on tokens per safe task.  The other baseline is still usable when its
minimum is positive; when neither minimum is positive, the cell is explicitly
``not-disproven`` and all comparison arithmetic is null.

The module performs no model, provider, tokenizer, filesystem, network, or
external call.  It does not verify that a caller's registered bounds are true;
its result is conditional on the exact digests and assertions in the plan.
Accordingly, the only outcomes are ``impossible``, ``not-disproven``, and
``invalid``.  In particular, ``not-disproven`` is not an efficiency result.
"""

from __future__ import annotations

from typing import Any

from .contract import IDENTIFIER_RE, SHA256_RE, VerificationError, sha256_ref


FEASIBILITY_PLAN_SCHEMA = "urusilla-initial-goal-feasibility-kill-screen-plan/2"
FEASIBILITY_RESULT_SCHEMA = (
    "urusilla-initial-goal-feasibility-kill-screen-result/2"
)
PLAN_STATUS = "frozen-zero-call-bounds"
EVALUATION_REFERENCE = "urusilla-initial-goal-raw-json-feasibility/2"

SESSION_LENGTHS = tuple(range(1, 129))
TARGET_REDUCTION_BASIS_POINTS = 2_000
BASIS_POINTS = 10_000
REMAINING_COST_BASIS_POINTS = BASIS_POINTS - TARGET_REDUCTION_BASIS_POINTS

PATHS = ("action-state", "raw-concise", "ordinary-json")
BASELINE_PATHS = ("raw-concise", "ordinary-json")
PHASES = (
    "setup",
    "comprehension",
    "sender",
    "fidelity",
    "router",
    "primary",
    "validator",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
    "causal",
)
MANDATORY_CANDIDATE_OBLIGATIONS = ("setup", "comprehension")
OUTCOMES = ("impossible", "not-disproven", "invalid")
NO_POSITIVE_BASELINE_SUCCESS_REASON = (
    "unbounded-no-positive-baseline-safe-success-lower-bound"
)

_MAX_ROWS = 128
_MAX_TOKEN_BOUND = (1 << 63) - 1
_MAX_TOTAL_BOUND = (1 << 127) - 1

_REGISTRATION_KEYS = {
    "bounds_frozen_before_screen",
    "provider_calls_performed",
    "model_calls_performed",
    "source_prompt_bundle_sha256",
    "path_enumerator_sha256",
    "tokenizer_registry_sha256",
    "all_dynamic_slots_finitely_bounded",
    "all_allowed_paths_enumerated",
    "inclusive_phase_partition_complete",
    "all_billed_reasoning_and_outputs_included",
    "all_retries_repairs_fallbacks_and_judges_included",
}


class FeasibilityKillScreenError(VerificationError):
    """A plan is not complete enough for conditional arithmetic screening."""


def _assumptions() -> dict[str, object]:
    """Return the exact interpretation boundary embedded in every result."""

    return {
        "arithmetic": "exact-integer-rational-cross-multiplication",
        "candidate_cost_bound": "sum-of-registered-phase-lower-bounds",
        "candidate_success_bound": "maximum-safe-successes-equals-N",
        "baseline_cost_bound": "sum-of-registered-phase-upper-bounds",
        "baseline_success_bound": (
            "registered-minimum-safe-successes-per-path-and-N;zero-means-no-positive-guarantee"
        ),
        "baseline_comparator": (
            "minimum-finite-upper-tokens-per-safe-task-among-baselines-with-"
            "positive-minimum-safe-successes"
        ),
        "no_positive_baseline_success": (
            "not-disproven-with-null-comparison-arithmetic"
        ),
        "candidate_mandatory_obligations": list(
            MANDATORY_CANDIDATE_OBLIGATIONS
        ),
        "inclusive_phase_scope": list(PHASES),
        "token_occurrence_scope": (
            "complete-input-visible-output-billed-reasoning-and-unclassified-usage"
        ),
        "contingency_scope": (
            "all-retries-repairs-fallbacks-and-judge-calls-within-registered-bounds"
        ),
        "session_lengths": list(SESSION_LENGTHS),
        "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
        "kill_rule": (
            "candidate_lower_per_safe_task>"
            "0.80*better_baseline_upper_per_safe_task"
        ),
        "equality_rule": "not-disproven",
        "unknown_or_unbounded_token_input": "invalid",
        "bound_truth": (
            "conditional-on-caller-registered-digests-and-completeness-assertions"
        ),
        "not_disproven_interpretation": (
            "absence-of-this-arithmetic-impossibility-result-only"
        ),
        "nonclaims": [
            "no-positive-efficiency-claim",
            "no-task-success-claim",
            "no-comprehension-claim",
            "no-parse-validity-claim",
            "no-semantic-fidelity-claim",
            "no-provider-or-model-run",
            "no-protocol-version-promotion",
        ],
    }


EXACT_ASSUMPTIONS_SHA256 = sha256_ref(_assumptions())


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise FeasibilityKillScreenError(f"{path}:object-required")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise FeasibilityKillScreenError(f"{path}:array-required")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    if any(type(key) is not str for key in value):
        raise FeasibilityKillScreenError(f"{path}:string-keys-required")
    actual = set(value)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        raise FeasibilityKillScreenError(
            f"{path}:keys-mismatch:missing={missing}:extra={extra}"
        )


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        raise FeasibilityKillScreenError(f"{path}:identifier-required")
    return value


def _sha256(value: Any, path: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise FeasibilityKillScreenError(f"{path}:sha256-required")
    return value


def _exact_bool(value: Any, expected: bool, path: str) -> None:
    if type(value) is not bool or value is not expected:
        rendered = "true" if expected else "false"
        raise FeasibilityKillScreenError(f"{path}:must-be-{rendered}")


def _exact_int(value: Any, expected: int, path: str) -> None:
    if type(value) is not int or value != expected:
        raise FeasibilityKillScreenError(f"{path}:must-equal-{expected}")


def _validate_registration(value: Any) -> dict[str, Any]:
    registration = _object(value, "plan.registration")
    _exact_keys(registration, _REGISTRATION_KEYS, "plan.registration")
    _exact_bool(
        registration["bounds_frozen_before_screen"],
        True,
        "plan.registration.bounds_frozen_before_screen",
    )
    _exact_int(
        registration["provider_calls_performed"],
        0,
        "plan.registration.provider_calls_performed",
    )
    _exact_int(
        registration["model_calls_performed"],
        0,
        "plan.registration.model_calls_performed",
    )
    for field in (
        "source_prompt_bundle_sha256",
        "path_enumerator_sha256",
        "tokenizer_registry_sha256",
    ):
        _sha256(registration[field], f"plan.registration.{field}")
    for field in (
        "all_dynamic_slots_finitely_bounded",
        "all_allowed_paths_enumerated",
        "inclusive_phase_partition_complete",
        "all_billed_reasoning_and_outputs_included",
        "all_retries_repairs_fallbacks_and_judges_included",
    ):
        _exact_bool(registration[field], True, f"plan.registration.{field}")
    return registration


def _token_vector(value: Any, path: str) -> tuple[int, ...]:
    items = _array(value, path)
    if len(items) != len(SESSION_LENGTHS):
        raise FeasibilityKillScreenError(
            f"{path}:must-have-{len(SESSION_LENGTHS)}-entries"
        )
    checked: list[int] = []
    previous = -1
    for index, item in enumerate(items):
        if type(item) is not int or item < 0 or item > _MAX_TOKEN_BOUND:
            raise FeasibilityKillScreenError(
                f"{path}[{index}]:finite-nonnegative-token-bound-required"
            )
        if item < previous:
            raise FeasibilityKillScreenError(
                f"{path}[{index}]:phase-total-must-be-nondecreasing"
            )
        checked.append(item)
        previous = item
    return tuple(checked)


def _success_vector(
    value: Any,
    *,
    path_name: str,
    path: str,
) -> tuple[int, ...]:
    items = _array(value, path)
    if len(items) != len(SESSION_LENGTHS):
        raise FeasibilityKillScreenError(
            f"{path}:must-have-{len(SESSION_LENGTHS)}-entries"
        )
    checked: list[int] = []
    previous = 0
    for index, (item, session_length) in enumerate(zip(items, SESSION_LENGTHS)):
        if type(item) is not int:
            raise FeasibilityKillScreenError(
                f"{path}[{index}]:integer-safe-success-bound-required"
            )
        if path_name == "action-state":
            if item != session_length:
                raise FeasibilityKillScreenError(
                    f"{path}[{index}]:candidate-maximum-must-equal-N"
                )
        elif item < 0 or item > session_length:
            raise FeasibilityKillScreenError(
                f"{path}[{index}]:baseline-safe-success-bound-must-be-in-0..N"
            )
        if item < previous:
            raise FeasibilityKillScreenError(
                f"{path}[{index}]:safe-success-bound-must-be-nondecreasing"
            )
        checked.append(item)
        previous = item
    return tuple(checked)


def _validate_path(
    value: Any,
    *,
    path_name: str,
    path: str,
) -> tuple[tuple[int, ...], tuple[int, ...], str]:
    bound = _object(value, path)
    _exact_keys(
        bound,
        {"bound_direction", "success_direction", "safe_successes_by_n", "phases"},
        path,
    )
    expected_bound_direction = "lower" if path_name == "action-state" else "upper"
    if bound["bound_direction"] != expected_bound_direction:
        raise FeasibilityKillScreenError(
            f"{path}.bound_direction:must-equal-{expected_bound_direction}"
        )
    expected_success_direction = (
        "maximum" if path_name == "action-state" else "minimum"
    )
    if bound["success_direction"] != expected_success_direction:
        raise FeasibilityKillScreenError(
            f"{path}.success_direction:must-equal-{expected_success_direction}"
        )
    successes = _success_vector(
        bound["safe_successes_by_n"],
        path_name=path_name,
        path=f"{path}.safe_successes_by_n",
    )

    phases = _array(bound["phases"], f"{path}.phases")
    if len(phases) != len(PHASES):
        raise FeasibilityKillScreenError(
            f"{path}.phases:must-have-{len(PHASES)}-entries"
        )
    totals = [0] * len(SESSION_LENGTHS)
    phase_vectors: dict[str, tuple[int, ...]] = {}
    for index, expected_phase in enumerate(PHASES):
        phase_path = f"{path}.phases[{index}]"
        phase = _object(phases[index], phase_path)
        _exact_keys(
            phase,
            {"phase", "bound_kind", "tokens_by_n"},
            phase_path,
        )
        if phase["phase"] != expected_phase:
            raise FeasibilityKillScreenError(
                f"{phase_path}.phase:must-equal-{expected_phase}"
            )
        vector = _token_vector(phase["tokens_by_n"], f"{phase_path}.tokens_by_n")
        all_zero = all(item == 0 for item in vector)
        expected_kind = (
            "proved-zero"
            if all_zero
            else (
                "proved-lower-bound"
                if path_name == "action-state"
                else "proved-upper-bound"
            )
        )
        if phase["bound_kind"] != expected_kind:
            raise FeasibilityKillScreenError(
                f"{phase_path}.bound_kind:must-equal-{expected_kind}"
            )
        if (
            path_name == "action-state"
            and expected_phase in MANDATORY_CANDIDATE_OBLIGATIONS
            and any(item <= 0 for item in vector)
        ):
            raise FeasibilityKillScreenError(
                f"{phase_path}:mandatory-candidate-obligation-must-be-positive-for-every-N"
            )
        phase_vectors[expected_phase] = vector
        for position, item in enumerate(vector):
            totals[position] += item
            if totals[position] > _MAX_TOTAL_BOUND:
                raise FeasibilityKillScreenError(
                    f"{path}:summed-token-bound-exceeds-resource-limit"
                )

    if any(item <= 0 for item in totals):
        raise FeasibilityKillScreenError(
            f"{path}:total-token-bound-must-be-positive-for-every-N"
        )
    return tuple(totals), successes, sha256_ref(bound)


def _fraction_compare(
    left_numerator: int,
    left_denominator: int,
    right_numerator: int,
    right_denominator: int,
) -> int:
    left = left_numerator * right_denominator
    right = right_numerator * left_denominator
    return -1 if left < right else (1 if left > right else 0)


def _validate_and_screen(plan: Any) -> dict[str, object]:
    plan_object = _object(plan, "plan")
    _exact_keys(
        plan_object,
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
    if plan_object["schema_version"] != FEASIBILITY_PLAN_SCHEMA:
        raise FeasibilityKillScreenError("plan.schema_version:unknown")
    evaluation_id = _identifier(
        plan_object["evaluation_id"], "plan.evaluation_id"
    )
    if evaluation_id != EVALUATION_REFERENCE:
        raise FeasibilityKillScreenError(
            "plan.evaluation_id:must-match-frozen-evaluation-reference"
        )
    if plan_object["status"] != PLAN_STATUS:
        raise FeasibilityKillScreenError("plan.status:not-frozen-zero-call-bounds")
    _exact_int(
        plan_object["target_reduction_basis_points"],
        TARGET_REDUCTION_BASIS_POINTS,
        "plan.target_reduction_basis_points",
    )
    session_lengths = _array(plan_object["session_lengths"], "plan.session_lengths")
    if (
        len(session_lengths) != len(SESSION_LENGTHS)
        or any(type(item) is not int for item in session_lengths)
        or session_lengths != list(SESSION_LENGTHS)
    ):
        raise FeasibilityKillScreenError("plan.session_lengths:must-be-exact-1..128")
    registration = _validate_registration(plan_object["registration"])

    rows = _array(plan_object["rows"], "plan.rows")
    if not rows or len(rows) > _MAX_ROWS:
        raise FeasibilityKillScreenError(
            f"plan.rows:must-have-1..{_MAX_ROWS}-entries"
        )

    seen: set[tuple[str, str]] = set()
    result_rows: list[dict[str, object]] = []
    all_cells_impossible = True
    for row_index, row_value in enumerate(rows):
        row_path = f"plan.rows[{row_index}]"
        row = _object(row_value, row_path)
        _exact_keys(
            row,
            {
                "domain_id",
                "domain_manifest_sha256",
                "tokenizer_id",
                "tokenizer_sha256",
                "bound_manifest_sha256",
                "paths",
            },
            row_path,
        )
        domain_id = _identifier(row["domain_id"], f"{row_path}.domain_id")
        tokenizer_id = _identifier(row["tokenizer_id"], f"{row_path}.tokenizer_id")
        identity = (domain_id, tokenizer_id)
        if identity in seen:
            raise FeasibilityKillScreenError(
                f"{row_path}:duplicate-domain-tokenizer-row"
            )
        seen.add(identity)
        domain_manifest_sha256 = _sha256(
            row["domain_manifest_sha256"], f"{row_path}.domain_manifest_sha256"
        )
        tokenizer_sha256 = _sha256(
            row["tokenizer_sha256"], f"{row_path}.tokenizer_sha256"
        )
        bound_manifest_sha256 = _sha256(
            row["bound_manifest_sha256"], f"{row_path}.bound_manifest_sha256"
        )
        paths = _object(row["paths"], f"{row_path}.paths")
        _exact_keys(paths, set(PATHS), f"{row_path}.paths")

        totals: dict[str, tuple[int, ...]] = {}
        successes: dict[str, tuple[int, ...]] = {}
        path_sha256: dict[str, str] = {}
        for path_name in PATHS:
            total, success, bound_sha256 = _validate_path(
                paths[path_name],
                path_name=path_name,
                path=f"{row_path}.paths.{path_name}",
            )
            totals[path_name] = total
            successes[path_name] = success
            path_sha256[path_name] = bound_sha256

        session_results: list[dict[str, object]] = []
        row_all_impossible = True
        for position, session_length in enumerate(SESSION_LENGTHS):
            raw_fraction = (
                totals["raw-concise"][position],
                successes["raw-concise"][position],
            )
            json_fraction = (
                totals["ordinary-json"][position],
                successes["ordinary-json"][position],
            )
            raw_has_finite_bound = raw_fraction[1] > 0
            json_has_finite_bound = json_fraction[1] > 0
            if raw_has_finite_bound and json_has_finite_bound:
                comparison = _fraction_compare(*raw_fraction, *json_fraction)
                if comparison < 0:
                    selected: str | None = "raw-concise"
                elif comparison > 0:
                    selected = "ordinary-json"
                else:
                    selected = "tie-raw-concise-and-ordinary-json"
                selected_fraction: tuple[int, int] | None = (
                    raw_fraction if comparison <= 0 else json_fraction
                )
            elif raw_has_finite_bound:
                selected = "raw-concise"
                selected_fraction = raw_fraction
            elif json_has_finite_bound:
                selected = "ordinary-json"
                selected_fraction = json_fraction
            else:
                selected = None
                selected_fraction = None
            candidate_numerator = totals["action-state"][position]
            candidate_denominator = successes["action-state"][position]
            if selected_fraction is None:
                baseline_numerator: int | None = None
                baseline_denominator: int | None = None
                kill_left: int | None = None
                kill_right: int | None = None
                comparison_unavailable_reason: str | None = (
                    NO_POSITIVE_BASELINE_SUCCESS_REASON
                )
                outcome = "not-disproven"
            else:
                baseline_numerator, baseline_denominator = selected_fraction
                kill_left = (
                    candidate_numerator * baseline_denominator * BASIS_POINTS
                )
                kill_right = (
                    baseline_numerator
                    * candidate_denominator
                    * REMAINING_COST_BASIS_POINTS
                )
                comparison_unavailable_reason = None
                outcome = (
                    "impossible" if kill_left > kill_right else "not-disproven"
                )
            if outcome != "impossible":
                row_all_impossible = False
                all_cells_impossible = False
            session_results.append(
                {
                    "session_length": session_length,
                    "outcome": outcome,
                    "candidate_lower_total_tokens": candidate_numerator,
                    "candidate_max_safe_successes": candidate_denominator,
                    "raw_upper_total_tokens": raw_fraction[0],
                    "raw_min_safe_successes": raw_fraction[1],
                    "json_upper_total_tokens": json_fraction[0],
                    "json_min_safe_successes": json_fraction[1],
                    "comparison_bound_source": selected,
                    "comparison_unavailable_reason": comparison_unavailable_reason,
                    "comparison_upper_total_tokens": baseline_numerator,
                    "comparison_min_safe_successes": baseline_denominator,
                    "kill_left_scaled": kill_left,
                    "kill_right_scaled": kill_right,
                }
            )

        result_rows.append(
            {
                "domain_id": domain_id,
                "domain_manifest_sha256": domain_manifest_sha256,
                "tokenizer_id": tokenizer_id,
                "tokenizer_sha256": tokenizer_sha256,
                "bound_manifest_sha256": bound_manifest_sha256,
                "path_bounds_sha256": path_sha256,
                "outcome": (
                    "impossible" if row_all_impossible else "not-disproven"
                ),
                "sessions": session_results,
            }
        )

    return {
        "schema_version": FEASIBILITY_RESULT_SCHEMA,
        "evaluation_reference": EVALUATION_REFERENCE,
        "outcome": "impossible" if all_cells_impossible else "not-disproven",
        "plan_sha256": sha256_ref(plan_object),
        "registration_sha256": sha256_ref(registration),
        "assumptions": _assumptions(),
        "assumptions_sha256": EXACT_ASSUMPTIONS_SHA256,
        "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
        "session_lengths": list(SESSION_LENGTHS),
        "rows": result_rows,
        "provider_calls_performed": 0,
        "model_calls_performed": 0,
        "claim_eligible": False,
    }


def run_feasibility_kill_screen(plan: Any) -> dict[str, object]:
    """Return a fail-closed conditional screen result without external calls."""

    try:
        return _validate_and_screen(plan)
    except (FeasibilityKillScreenError, VerificationError) as exc:
        return {
            "schema_version": FEASIBILITY_RESULT_SCHEMA,
            "evaluation_reference": EVALUATION_REFERENCE,
            "outcome": "invalid",
            # Invalid input is deliberately not canonicalized again here.
            # Structural/resource rejection can precede a safe full-object
            # traversal, so hashing the rejected value would bypass the cap.
            "plan_sha256": None,
            "registration_sha256": None,
            "assumptions": _assumptions(),
            "assumptions_sha256": EXACT_ASSUMPTIONS_SHA256,
            "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
            "session_lengths": list(SESSION_LENGTHS),
            "rows": [],
            "error": str(exc),
            "provider_calls_performed": 0,
            "model_calls_performed": 0,
            "claim_eligible": False,
        }


__all__ = [
    "BASELINE_PATHS",
    "BASIS_POINTS",
    "EXACT_ASSUMPTIONS_SHA256",
    "FEASIBILITY_PLAN_SCHEMA",
    "FEASIBILITY_RESULT_SCHEMA",
    "MANDATORY_CANDIDATE_OBLIGATIONS",
    "NO_POSITIVE_BASELINE_SUCCESS_REASON",
    "OUTCOMES",
    "PATHS",
    "PHASES",
    "PLAN_STATUS",
    "EVALUATION_REFERENCE",
    "SESSION_LENGTHS",
    "TARGET_REDUCTION_BASIS_POINTS",
    "FeasibilityKillScreenError",
    "run_feasibility_kill_screen",
]
