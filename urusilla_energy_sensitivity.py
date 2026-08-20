#!/usr/bin/env python3
"""Transparent energy-per-safe-task sensitivity model for Urusilla.

This model is deliberately normalized. It does not claim to measure joules.
It shows which empirical quantities must be measured before an energy claim is
valid and how conversion, repair, and training overhead can erase codec gains.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


MEASURED_MEAN_WARM_TOKEN_REDUCTION = 0.45794324920364504
MEASURED_AGGREGATE_A2A_WIRE_REDUCTION = 0.18236583423154207


@dataclass(frozen=True)
class EnergyCase:
    name: str
    communication_share: float
    token_sensitive_share: float
    wire_sensitive_share: float
    token_reduction: float
    wire_reduction: float
    added_overhead: float
    relative_safe_success: float = 1.0


@dataclass(frozen=True)
class EnergyResult:
    name: str
    baseline_energy_per_safe_task: float
    gross_saved_energy: float
    added_overhead: float
    energy_before_success_adjustment: float
    relative_safe_success: float
    energy_per_safe_task: float
    net_saving: float


def _fraction(name: str, value: float, *, positive: bool = False) -> None:
    lower_ok = value > 0.0 if positive else value >= 0.0
    if not lower_ok or value > 1.0:
        boundary = "(0, 1]" if positive else "[0, 1]"
        raise ValueError(f"{name} must be in {boundary}")


def evaluate(case: EnergyCase) -> EnergyResult:
    """Evaluate normalized energy per safely completed task.

    ``communication_share`` is the fraction of baseline system energy used by
    communication-related work. Token- and wire-sensitive shares are fractions
    within that communication component; their sum may not exceed one. Added
    overhead is a fraction of the complete baseline system energy.
    """

    _fraction("communication_share", case.communication_share)
    _fraction("token_sensitive_share", case.token_sensitive_share)
    _fraction("wire_sensitive_share", case.wire_sensitive_share)
    _fraction("token_reduction", case.token_reduction)
    _fraction("wire_reduction", case.wire_reduction)
    _fraction("added_overhead", case.added_overhead)
    _fraction("relative_safe_success", case.relative_safe_success, positive=True)
    if case.token_sensitive_share + case.wire_sensitive_share > 1.0:
        raise ValueError("token- and wire-sensitive shares may not sum above 1")

    gross = case.communication_share * (
        case.token_sensitive_share * case.token_reduction
        + case.wire_sensitive_share * case.wire_reduction
    )
    before_success = 1.0 - gross + case.added_overhead
    per_safe_task = before_success / case.relative_safe_success
    return EnergyResult(
        name=case.name,
        baseline_energy_per_safe_task=1.0,
        gross_saved_energy=gross,
        added_overhead=case.added_overhead,
        energy_before_success_adjustment=before_success,
        relative_safe_success=case.relative_safe_success,
        energy_per_safe_task=per_safe_task,
        net_saving=1.0 - per_safe_task,
    )


def illustrative_cases() -> tuple[EnergyCase, ...]:
    """Return sensitivity cases, not forecasts.

    The 45.8% token figure is the measured arithmetic mean for warm Base64
    v0.2 versus minified UrusillaIR JSON across four tokenizers. The 18.2%
    wire figure is the aggregate compressed complete-request reduction across
    the HTTP+JSON and JSON-RPC A2A bindings versus structured DataPart JSON.
    Neither figure compares against natural-language dialogue.
    """

    return (
        EnergyCase(
            name="overhead-dominates",
            communication_share=0.10,
            token_sensitive_share=0.20,
            wire_sensitive_share=0.10,
            token_reduction=MEASURED_MEAN_WARM_TOKEN_REDUCTION,
            wire_reduction=MEASURED_AGGREGATE_A2A_WIRE_REDUCTION,
            added_overhead=0.030,
            relative_safe_success=1.0,
        ),
        EnergyCase(
            name="communication-moderate",
            communication_share=0.30,
            token_sensitive_share=0.70,
            wire_sensitive_share=0.10,
            token_reduction=MEASURED_MEAN_WARM_TOKEN_REDUCTION,
            wire_reduction=MEASURED_AGGREGATE_A2A_WIRE_REDUCTION,
            added_overhead=0.025,
            relative_safe_success=1.0,
        ),
        EnergyCase(
            name="communication-heavy",
            communication_share=0.70,
            token_sensitive_share=0.80,
            wire_sensitive_share=0.10,
            token_reduction=MEASURED_MEAN_WARM_TOKEN_REDUCTION,
            wire_reduction=MEASURED_AGGREGATE_A2A_WIRE_REDUCTION,
            added_overhead=0.040,
            relative_safe_success=1.0,
        ),
        EnergyCase(
            name="repair-regression",
            communication_share=0.30,
            token_sensitive_share=0.70,
            wire_sensitive_share=0.10,
            token_reduction=MEASURED_MEAN_WARM_TOKEN_REDUCTION,
            wire_reduction=MEASURED_AGGREGATE_A2A_WIRE_REDUCTION,
            added_overhead=0.025,
            relative_safe_success=0.90,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    results = [evaluate(case) for case in illustrative_cases()]
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        for result in results:
            print(f"{result.name}: {result.net_saving:+.2%} net energy change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
