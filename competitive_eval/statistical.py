"""Deterministic paired bootstrap intervals and Holm correction.

The resample count, endpoints, margins, and confidence levels come from the
current evaluation plan. The seed, SHA-256 counter sampler, cluster convention,
inverse-ECDF quantile, and centered-bootstrap p-value are new v1 harness locks
because the plan did not specify them.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
from typing import Any, Iterable, Mapping, Sequence

from .canonical import canonical_json, sequence_sha256
from .config import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED_HEX,
    HOLM_ALPHA,
    NONINFERIORITY_MARGIN,
    TOKEN_REDUCTION_GATE,
)
from .errors import StatisticsError


@dataclass(frozen=True)
class AnalysisRow:
    task_family: str
    item_id: str
    evidence_mode: str
    repeat_seed: int
    sender_family: str
    receiver_family: str
    repeat_id: int
    arm: str
    safe_task_success: bool
    t_total: int

    def __post_init__(self) -> None:
        for label, value in {
            "task_family": self.task_family,
            "item_id": self.item_id,
            "evidence_mode": self.evidence_mode,
            "sender_family": self.sender_family,
            "receiver_family": self.receiver_family,
            "arm": self.arm,
        }.items():
            if type(value) is not str or not value:
                raise StatisticsError(f"MANIFEST_MISMATCH: {label} must be text")
        if type(self.safe_task_success) is not bool:
            raise StatisticsError("BAD_SUCCESS_TYPE: safe_task_success must be Boolean")
        if type(self.t_total) is not int or self.t_total < 0:
            raise StatisticsError("BAD_TOKEN_COUNT: t_total must be a nonnegative integer")
        if type(self.repeat_seed) is not int or type(self.repeat_id) is not int:
            raise StatisticsError("MANIFEST_MISMATCH: repeat fields must be integers")

    @property
    def ordered_pair(self) -> str:
        return f"{self.sender_family}->{self.receiver_family}"

    @property
    def unit_key(self) -> tuple[Any, ...]:
        return (
            self.task_family,
            self.item_id,
            self.evidence_mode,
            self.repeat_seed,
            self.ordered_pair,
            self.repeat_id,
        )

    @property
    def cluster_key(self) -> tuple[str, ...]:
        return (
            self.task_family,
            self.evidence_mode,
            self.item_id,
            self.ordered_pair,
        )

    @property
    def item_only_cluster_key(self) -> tuple[str, ...]:
        return (self.task_family, self.evidence_mode, self.item_id)

    @property
    def stratum_key(self) -> tuple[str, ...]:
        return (self.task_family, self.evidence_mode, self.ordered_pair)

    @property
    def item_only_stratum_key(self) -> tuple[str, ...]:
        # Pair-specific strata would split the same item back into separate
        # sampling units, defeating the purpose of the conservative sensitivity.
        return (self.task_family, self.evidence_mode)


@dataclass(frozen=True)
class PairedValue:
    row: AnalysisRow
    baseline_success: bool
    baseline_tokens: int

    @property
    def success_difference(self) -> int:
        return int(self.row.safe_task_success) - int(self.baseline_success)


def _decimal(value: Fraction, places: int = 12) -> str:
    return f"{float(value):.{places}f}"


def _fraction_object(value: Fraction) -> dict[str, Any]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": _decimal(value),
    }


def pair_rows(
    rows: Sequence[AnalysisRow], *, candidate_arm: str, baseline_arm: str
) -> tuple[PairedValue, ...]:
    if candidate_arm == baseline_arm:
        raise StatisticsError("MANIFEST_MISMATCH: candidate and baseline arms are identical")
    grouped: dict[tuple[Any, ...], dict[str, AnalysisRow]] = {}
    for row in rows:
        if row.arm not in {candidate_arm, baseline_arm}:
            continue
        cell = grouped.setdefault(row.unit_key, {})
        if row.arm in cell:
            raise StatisticsError(
                f"DUPLICATE_PAIR_ARM: duplicate {row.arm} for unit {row.unit_key}"
            )
        cell[row.arm] = row
    if not grouped:
        raise StatisticsError("INCOMPLETE_PAIR_BLOCK: no paired rows")
    paired: list[PairedValue] = []
    for key in sorted(grouped, key=lambda value: canonical_json(value)):
        cell = grouped[key]
        if set(cell) != {candidate_arm, baseline_arm}:
            raise StatisticsError(f"INCOMPLETE_PAIR_BLOCK: missing arm for unit {key}")
        candidate = cell[candidate_arm]
        baseline = cell[baseline_arm]
        paired.append(PairedValue(candidate, baseline.safe_task_success, baseline.t_total))
    return tuple(paired)


def _point_success(values: Sequence[PairedValue]) -> Fraction:
    if not values:
        raise StatisticsError("INCOMPLETE_PAIR_BLOCK: no paired values")
    return Fraction(sum(value.success_difference for value in values), len(values))


def _point_reduction(values: Sequence[PairedValue]) -> Fraction:
    baseline = sum(value.baseline_tokens for value in values)
    if baseline == 0:
        raise StatisticsError("ZERO_BASELINE_TOKEN_SUM: CTE token total is zero")
    candidate = sum(value.row.t_total for value in values)
    return Fraction(baseline - candidate, baseline)


class ShaCounterSampler:
    def __init__(self, seed_hex: str, analysis_id: str):
        if len(seed_hex) != 64:
            raise StatisticsError("bootstrap seed must be a 32-byte hex digest")
        try:
            self.seed = bytes.fromhex(seed_hex)
        except ValueError as exc:
            raise StatisticsError("bootstrap seed is not hexadecimal") from exc
        self.analysis = analysis_id.encode("utf-8")

    def index(
        self, *, draw: int, stratum: str, position: int, size: int
    ) -> int:
        if size < 1:
            raise StatisticsError("cannot sample an empty stratum")
        maximum = 1 << 256
        accepted_below = maximum - (maximum % size)
        rejection = 0
        while True:
            payload = b"\x00".join(
                (
                    b"competitive-eval-bootstrap-v1",
                    self.seed,
                    self.analysis,
                    str(draw).encode(),
                    stratum.encode("utf-8"),
                    str(position).encode(),
                    str(rejection).encode(),
                )
            )
            number = int.from_bytes(hashlib.sha256(payload).digest(), "big")
            if number < accepted_below:
                return number % size
            rejection += 1


def _inverse_ecdf(values: Sequence[Fraction], probability: Fraction) -> Fraction:
    if not values or not 0 < probability <= 1:
        raise StatisticsError("invalid empirical quantile request")
    ordered = sorted(values)
    rank = (
        probability.numerator * len(ordered) + probability.denominator - 1
    ) // probability.denominator
    return ordered[max(0, rank - 1)]


def _resample(
    paired: Sequence[PairedValue],
    *,
    analysis_id: str,
    resamples: int,
    seed_hex: str,
    item_only_cluster: bool,
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    if resamples < 1:
        raise StatisticsError("resamples must be positive")
    strata: dict[tuple[str, ...], dict[tuple[str, ...], list[PairedValue]]] = {}
    for value in paired:
        row = value.row
        stratum = row.item_only_stratum_key if item_only_cluster else row.stratum_key
        cluster = row.item_only_cluster_key if item_only_cluster else row.cluster_key
        strata.setdefault(stratum, {}).setdefault(cluster, []).append(value)
    cluster_count = sum(len(clusters) for clusters in strata.values())
    if cluster_count < 2:
        raise StatisticsError("INSUFFICIENT_CLUSTERS: claim interval needs at least two clusters")

    sampler = ShaCounterSampler(seed_hex, analysis_id)
    success_draws: list[Fraction] = []
    token_draws: list[Fraction] = []
    for draw in range(resamples):
        sampled: list[PairedValue] = []
        for stratum_key in sorted(strata, key=canonical_json):
            clusters = strata[stratum_key]
            cluster_keys = sorted(clusters, key=canonical_json)
            stratum_text = canonical_json(stratum_key)
            for position in range(len(cluster_keys)):
                chosen = cluster_keys[
                    sampler.index(
                        draw=draw,
                        stratum=stratum_text,
                        position=position,
                        size=len(cluster_keys),
                    )
                ]
                sampled.extend(clusters[chosen])
        success_draws.append(_point_success(sampled))
        token_draws.append(_point_reduction(sampled))
    return tuple(success_draws), tuple(token_draws)


def _centered_p_value(
    draws: Sequence[Fraction], point: Fraction, null: Fraction
) -> Fraction:
    threshold = point - null
    count = sum((draw - point) >= threshold for draw in draws)
    return Fraction(1 + count, len(draws) + 1)


def paired_bootstrap(
    rows: Sequence[AnalysisRow],
    *,
    candidate_arm: str,
    baseline_arm: str,
    analysis_id: str,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed_hex: str = BOOTSTRAP_SEED_HEX,
    item_only_cluster: bool = False,
) -> dict[str, Any]:
    paired = pair_rows(rows, candidate_arm=candidate_arm, baseline_arm=baseline_arm)
    point_success = _point_success(paired)
    point_token = _point_reduction(paired)
    success_draws, token_draws = _resample(
        paired,
        analysis_id=analysis_id,
        resamples=resamples,
        seed_hex=seed_hex,
        item_only_cluster=item_only_cluster,
    )
    success_lower = _inverse_ecdf(success_draws, Fraction(5, 100))
    token_lower = _inverse_ecdf(token_draws, Fraction(25, 1000))
    token_upper = _inverse_ecdf(token_draws, Fraction(975, 1000))
    success_null = Fraction(-1, 100)
    token_null = Fraction(1, 4)
    success_p = _centered_p_value(success_draws, point_success, success_null)
    token_p = _centered_p_value(token_draws, point_token, token_null)
    stream_digest = sequence_sha256(
        f"{s.numerator}/{s.denominator}|{t.numerator}/{t.denominator}"
        for s, t in zip(success_draws, token_draws)
    )
    return {
        "format": "competitive-eval-paired-bootstrap-v1",
        "analysis_id": analysis_id,
        "candidate_arm": candidate_arm,
        "baseline_arm": baseline_arm,
        "paired_episodes": len(paired),
        "clusters": len(
            {
                value.row.item_only_cluster_key if item_only_cluster else value.row.cluster_key
                for value in paired
            }
        ),
        "strata": len(
            {
                value.row.item_only_stratum_key
                if item_only_cluster
                else value.row.stratum_key
                for value in paired
            }
        ),
        "cluster_convention": "item_only" if item_only_cluster else "item_by_ordered_pair",
        "resamples": resamples,
        "seed_hex": seed_hex,
        "sampler": "sha256_counter_rejection_sampling_v1",
        "quantile": "inverse_ecdf_hyndman_fan_type_1",
        "success": {
            "estimand": "success_candidate_minus_success_cte",
            "point": _fraction_object(point_success),
            "one_sided_95_lower": _fraction_object(success_lower),
            "margin": NONINFERIORITY_MARGIN,
            "passes_unadjusted_ci": success_lower > success_null,
            "centered_bootstrap_p": _fraction_object(success_p),
        },
        "tokens": {
            "estimand": "one_minus_ratio_of_summed_t_total",
            "point": _fraction_object(point_token),
            "two_sided_95_lower": _fraction_object(token_lower),
            "two_sided_95_upper": _fraction_object(token_upper),
            "gate": TOKEN_REDUCTION_GATE,
            "passes_unadjusted_ci": token_lower >= token_null,
            "centered_bootstrap_p": _fraction_object(token_p),
        },
        "resample_stream_sha256": stream_digest,
    }


def exact_mcnemar(
    rows: Sequence[AnalysisRow], *, candidate_arm: str, baseline_arm: str
) -> dict[str, Any]:
    """Return the preregistered exact two-sided McNemar sensitivity."""

    paired = pair_rows(rows, candidate_arm=candidate_arm, baseline_arm=baseline_arm)
    candidate_only = sum(
        value.row.safe_task_success and not value.baseline_success for value in paired
    )
    baseline_only = sum(
        value.baseline_success and not value.row.safe_task_success for value in paired
    )
    both_success = sum(
        value.baseline_success and value.row.safe_task_success for value in paired
    )
    both_failure = len(paired) - candidate_only - baseline_only - both_success
    discordant = candidate_only + baseline_only
    if discordant == 0:
        p_value = Fraction(1, 1)
    else:
        smaller = min(candidate_only, baseline_only)
        tail_numerator = sum(math.comb(discordant, index) for index in range(smaller + 1))
        p_value = min(Fraction(1, 1), Fraction(2 * tail_numerator, 2**discordant))
    risk_difference = _point_success(paired)
    return {
        "format": "competitive-eval-exact-mcnemar-v1",
        "candidate_arm": candidate_arm,
        "baseline_arm": baseline_arm,
        "paired_episodes": len(paired),
        "both_success": both_success,
        "both_failure": both_failure,
        "candidate_only_success": candidate_only,
        "baseline_only_success": baseline_only,
        "discordant_pairs": discordant,
        "paired_risk_difference": _fraction_object(risk_difference),
        "two_sided_exact_binomial_p": _fraction_object(p_value),
        "sensitivity_only": True,
    }


def holm_adjust(
    p_values: Mapping[str, Fraction | float],
    *,
    expected_hypotheses: Sequence[str] | None = None,
    alpha: float = HOLM_ALPHA,
) -> dict[str, Any]:
    if expected_hypotheses is not None and set(p_values) != set(expected_hypotheses):
        missing = sorted(set(expected_hypotheses) - set(p_values))
        extra = sorted(set(p_values) - set(expected_hypotheses))
        raise StatisticsError(
            f"INCOMPLETE_HOLM_FAMILY: missing={missing}, extra={extra}"
        )
    if not p_values:
        raise StatisticsError("INCOMPLETE_HOLM_FAMILY: no hypotheses")
    normalized: dict[str, Fraction] = {}
    for key, raw in p_values.items():
        value = raw if isinstance(raw, Fraction) else Fraction(str(raw))
        if value < 0 or value > 1:
            raise StatisticsError(f"invalid p-value for {key}")
        normalized[key] = value
    ordered = sorted(normalized.items(), key=lambda item: (item[1], item[0]))
    family_size = len(ordered)
    running = Fraction(0, 1)
    adjusted: dict[str, Fraction] = {}
    for index, (key, value) in enumerate(ordered):
        candidate = min(Fraction(1, 1), value * (family_size - index))
        running = max(running, candidate)
        adjusted[key] = running
    threshold = Fraction(str(alpha))
    return {
        "format": "competitive-eval-holm-v1",
        "alpha": alpha,
        "family_size": family_size,
        "hypotheses": {
            key: {
                "raw_p": _fraction_object(normalized[key]),
                "adjusted_p": _fraction_object(adjusted[key]),
                "passes": adjusted[key] <= threshold,
            }
            for key in sorted(normalized)
        },
        "all_pass": all(adjusted[key] <= threshold for key in adjusted),
    }
