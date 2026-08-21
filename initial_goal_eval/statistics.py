"""Deterministic matched whole-session statistics for the initial-goal gate."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
from typing import Any, Mapping, Sequence

from .contract import BASELINES, VerificationError, canonical_json


@dataclass(frozen=True)
class SessionAggregate:
    """One matched session containing all three representation arms."""

    session_id: str
    cluster_id: str
    domain_id: str
    receiver_family: str
    operator_id: str
    planned_tasks: int
    safe_successes: Mapping[str, int]
    total_tokens: Mapping[str, int]

    @property
    def stratum(self) -> tuple[str, str, str]:
        return (self.domain_id, self.receiver_family, self.operator_id)


def _fraction_object(value: Fraction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": f"{float(value):.12f}",
    }


class ShaCounterSampler:
    """Platform-independent counter sampler with rejection to remove modulo bias."""

    def __init__(self, seed_hex: str, analysis_id: str):
        try:
            self.seed = bytes.fromhex(seed_hex)
        except ValueError as exc:
            raise VerificationError("bootstrap seed is not hexadecimal") from exc
        if len(self.seed) != 32:
            raise VerificationError("bootstrap seed must be 32 bytes")
        self.analysis_id = analysis_id.encode("utf-8")

    def index(self, *, draw: int, stratum: str, position: int, size: int) -> int:
        if size < 1:
            raise VerificationError("cannot sample an empty bootstrap stratum")
        maximum = 1 << 256
        accepted_below = maximum - maximum % size
        rejection = 0
        while True:
            payload = b"\x00".join(
                (
                    b"urusilla-initial-goal-whole-session-bootstrap-v1",
                    self.seed,
                    self.analysis_id,
                    str(draw).encode("ascii"),
                    stratum.encode("utf-8"),
                    str(position).encode("ascii"),
                    str(rejection).encode("ascii"),
                )
            )
            number = int.from_bytes(hashlib.sha256(payload).digest(), "big")
            if number < accepted_below:
                return number % size
            rejection += 1


def _inverse_ecdf(values: Sequence[Fraction], probability: Fraction) -> Fraction:
    if not values or not 0 < probability <= 1:
        raise VerificationError("invalid bootstrap quantile")
    ordered = sorted(values)
    rank = (
        probability.numerator * len(ordered) + probability.denominator - 1
    ) // probability.denominator
    return ordered[max(0, rank - 1)]


def _summed_metrics(
    sessions: Sequence[SessionAggregate], baseline: str
) -> tuple[Fraction, Fraction | None, Fraction | None, Fraction | None]:
    if baseline not in BASELINES:
        raise VerificationError("unknown baseline in statistical comparison")
    tasks = sum(item.planned_tasks for item in sessions)
    if tasks < 1:
        raise VerificationError("statistical sample has no planned tasks")
    candidate_success = sum(item.safe_successes["hybrid-router"] for item in sessions)
    baseline_success = sum(item.safe_successes[baseline] for item in sessions)
    candidate_tokens = sum(item.total_tokens["hybrid-router"] for item in sessions)
    baseline_tokens = sum(item.total_tokens[baseline] for item in sessions)
    success_difference = Fraction(candidate_success - baseline_success, tasks)

    candidate_cost = (
        None if candidate_success == 0 else Fraction(candidate_tokens, candidate_success)
    )
    baseline_cost = (
        None if baseline_success == 0 else Fraction(baseline_tokens, baseline_success)
    )
    if candidate_success == 0:
        reduction = None
    elif baseline_success == 0:
        # A control that completes nothing has no finite cost-per-completion and
        # cannot qualify as the claimed strong baseline.
        reduction = None
    elif baseline_tokens == 0:
        reduction = None
    else:
        reduction = Fraction(
            baseline_tokens * candidate_success
            - candidate_tokens * baseline_success,
            baseline_tokens * candidate_success,
        )
    return success_difference, reduction, candidate_cost, baseline_cost


def compare_against_baseline(
    sessions: Sequence[SessionAggregate],
    *,
    baseline: str,
    seed_hex: str,
    resamples: int,
    success_margin: Fraction = Fraction(-1, 100),
    token_gate: Fraction = Fraction(1, 5),
) -> dict[str, Any]:
    """Return frozen one-sided success and two-sided cost-reduction bounds.

    Every draw samples complete matched sessions within the frozen
    domain/model/operator strata.  Setup and routine amortization therefore
    remain attached to the tasks that actually shared them.
    """

    if resamples < 1:
        raise VerificationError("bootstrap resamples must be positive")
    strata: dict[tuple[str, str, str], list[SessionAggregate]] = {}
    for item in sessions:
        strata.setdefault(item.stratum, []).append(item)
    if not strata or any(len(items) < 2 for items in strata.values()):
        raise VerificationError("every bootstrap stratum needs two whole sessions")

    point_success, point_reduction, candidate_cost, baseline_cost = _summed_metrics(
        sessions, baseline
    )
    sampler = ShaCounterSampler(seed_hex, f"hybrid-router-vs-{baseline}")
    success_draws: list[Fraction] = []
    reduction_draws: list[Fraction] = []
    undefined_reduction_draws = 0
    # A finite sentinel below every possible real reduction makes any draw with
    # no safely completed candidate task fail closed rather than disappear.
    failure_sentinel = Fraction(-10**12, 1)
    for draw in range(resamples):
        sampled: list[SessionAggregate] = []
        for stratum in sorted(strata, key=canonical_json):
            population = sorted(strata[stratum], key=lambda item: item.session_id)
            stratum_text = canonical_json(stratum)
            for position in range(len(population)):
                sampled.append(
                    population[
                        sampler.index(
                            draw=draw,
                            stratum=stratum_text,
                            position=position,
                            size=len(population),
                        )
                    ]
                )
        success, reduction, _, _ = _summed_metrics(sampled, baseline)
        success_draws.append(success)
        if reduction is None:
            undefined_reduction_draws += 1
            reduction_draws.append(failure_sentinel)
        else:
            reduction_draws.append(reduction)

    success_lower = _inverse_ecdf(success_draws, Fraction(5, 100))
    token_lower = _inverse_ecdf(reduction_draws, Fraction(25, 1000))
    token_upper = _inverse_ecdf(reduction_draws, Fraction(975, 1000))
    return {
        "baseline": baseline,
        "matched_sessions": len(sessions),
        "strata": len(strata),
        "bootstrap_resamples": resamples,
        "bootstrap_unit": "matched-whole-session",
        "success": {
            "estimand": "safe-success-rate-hybrid-minus-baseline",
            "point": _fraction_object(point_success),
            "one_sided_95_lower": _fraction_object(success_lower),
            "margin": _fraction_object(success_margin),
            "passed": success_lower >= success_margin,
        },
        "safe_completion_cost": {
            "estimand": "one-minus-hybrid-cost-per-safe-completion-over-baseline",
            "hybrid_point": _fraction_object(candidate_cost),
            "baseline_point": _fraction_object(baseline_cost),
            "reduction_point": _fraction_object(point_reduction),
            "two_sided_95_lower": _fraction_object(token_lower),
            "two_sided_95_upper": _fraction_object(token_upper),
            "gate": _fraction_object(token_gate),
            "undefined_bootstrap_draws": undefined_reduction_draws,
            "passed": point_reduction is not None and token_lower >= token_gate,
        },
    }


def compare_to_both_baselines(
    sessions: Sequence[SessionAggregate],
    *,
    seed_hex: str,
    resamples: int,
) -> dict[str, Any]:
    comparisons = {
        baseline: compare_against_baseline(
            sessions,
            baseline=baseline,
            seed_hex=seed_hex,
            resamples=resamples,
        )
        for baseline in BASELINES
    }
    success_lcbs = [
        Fraction(
            item["success"]["one_sided_95_lower"]["numerator"],
            item["success"]["one_sided_95_lower"]["denominator"],
        )
        for item in comparisons.values()
    ]
    token_lcbs = [
        Fraction(
            item["safe_completion_cost"]["two_sided_95_lower"]["numerator"],
            item["safe_completion_cost"]["two_sided_95_lower"]["denominator"],
        )
        for item in comparisons.values()
    ]
    return {
        "comparison_rule": "candidate-must-pass-separately-vs-raw-and-vs-json",
        "comparisons": comparisons,
        "worst_success_difference_lcb": _fraction_object(min(success_lcbs)),
        "worst_total_token_reduction_lcb": _fraction_object(min(token_lcbs)),
        "passed": all(
            item["success"]["passed"] and item["safe_completion_cost"]["passed"]
            for item in comparisons.values()
        ),
    }
