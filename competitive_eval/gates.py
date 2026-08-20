"""Exact protocol, promotion, claim, and call/cost stopping gates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .config import (
    A1_ABSOLUTE_CALL_CAP_CONVENTION,
    A1_ABSOLUTE_PAID_CALL_CAP_CONVENTION,
    A1_APPROVAL_USD_CEILING,
    NONINFERIORITY_MARGIN,
    SMOKE_MAX_SUCCESS_LOSS,
    TOKEN_REDUCTION_GATE,
)
from .errors import ApprovalRequired, BudgetStop, ManifestError


@dataclass(frozen=True)
class BudgetAuthorization:
    execution_mode: str
    provider_calls_allowed: bool
    paid_calls_allowed: bool
    total_call_cap: int
    paid_call_cap: int
    usd_cap: Decimal
    approval_reference: str | None = None

    @classmethod
    def offline_mock(cls) -> "BudgetAuthorization":
        return cls("offline_mock", False, False, 0, 0, Decimal("0"), None)


class BudgetGuard:
    def __init__(self, authorization: BudgetAuthorization):
        self.authorization = authorization
        self.provider_calls = 0
        self.paid_calls = 0
        self.actual_usd = Decimal("0")
        self.mock_calls = 0

    def before_call(
        self,
        *,
        is_mock: bool,
        is_paid: bool,
        projected_actual_usd: Decimal = Decimal("0"),
    ) -> None:
        if projected_actual_usd < 0:
            raise ManifestError("projected call cost cannot be negative")
        if is_mock:
            if is_paid or projected_actual_usd != 0:
                raise ApprovalRequired("a mock call cannot be paid or billed")
            self.mock_calls += 1
            return
        if not self.authorization.provider_calls_allowed:
            raise ApprovalRequired("provider/model calls are not authorized")
        if is_paid and not self.authorization.paid_calls_allowed:
            raise ApprovalRequired("paid calls are not authorized")
        if self.provider_calls + 1 > self.authorization.total_call_cap:
            raise BudgetStop("next provider call would cross the approved call cap")
        if is_paid and self.paid_calls + 1 > self.authorization.paid_call_cap:
            raise BudgetStop("next paid call would cross the approved paid-call cap")
        if self.actual_usd + projected_actual_usd > self.authorization.usd_cap:
            raise BudgetStop("next call would cross the approved dollar cap")
        self.provider_calls += 1
        self.paid_calls += int(is_paid)
        self.actual_usd += projected_actual_usd

    def snapshot(self) -> dict[str, Any]:
        return {
            "execution_mode": self.authorization.execution_mode,
            "provider_calls": self.provider_calls,
            "paid_calls": self.paid_calls,
            "mock_calls": self.mock_calls,
            "actual_usd": format(self.actual_usd, "f"),
            "total_call_cap": self.authorization.total_call_cap,
            "paid_call_cap": self.authorization.paid_call_cap,
            "usd_cap": format(self.authorization.usd_cap, "f"),
        }


def a1_live_authorization_template(approval_reference: str) -> BudgetAuthorization:
    if not approval_reference:
        raise ApprovalRequired("A1 requires an explicit approval reference")
    return BudgetAuthorization(
        execution_mode="A1_live",
        provider_calls_allowed=True,
        paid_calls_allowed=True,
        total_call_cap=A1_ABSOLUTE_CALL_CAP_CONVENTION,
        paid_call_cap=A1_ABSOLUTE_PAID_CALL_CAP_CONVENTION,
        usd_cap=Decimal(str(A1_APPROVAL_USD_CEILING)),
        approval_reference=approval_reference,
    )


def success_noninferiority_pass(lower_bound: float) -> bool:
    return lower_bound > NONINFERIORITY_MARGIN


def token_reduction_pass(lower_bound: float) -> bool:
    return lower_bound >= TOKEN_REDUCTION_GATE


def receiver_family_regression_gate(
    arm_minus_cte_point_estimates: Mapping[str, float],
) -> dict[str, Any]:
    regressions = {
        receiver: difference
        for receiver, difference in arm_minus_cte_point_estimates.items()
        if difference < NONINFERIORITY_MARGIN
    }
    return {
        "gate": "receiver_family_point_regression",
        "passed": bool(arm_minus_cte_point_estimates) and not regressions,
        "minimum_allowed_point_difference": NONINFERIORITY_MARGIN,
        "strictly_worse_receivers": regressions,
        "note": "A point difference exactly equal to -0.010 passes; a smaller value fails.",
    }


def a1_to_a2_promotion(
    *,
    exact_parsing_all_episodes: bool,
    complete_paired_stage: bool,
    arm_minus_cte_point_estimates: Mapping[str, float],
) -> dict[str, Any]:
    regressions = {
        arm: value
        for arm, value in arm_minus_cte_point_estimates.items()
        if value < SMOKE_MAX_SUCCESS_LOSS
    }
    passed = exact_parsing_all_episodes and complete_paired_stage and not regressions
    return {
        "gate": "A1_to_A2",
        "passed": passed,
        "exact_parsing_all_episodes": exact_parsing_all_episodes,
        "complete_paired_stage": complete_paired_stage,
        "minimum_allowed_point_difference": SMOKE_MAX_SUCCESS_LOSS,
        "strictly_worse_arms": regressions,
        "note": "A difference exactly equal to -0.030 passes this promotion gate.",
    }


def competitive_claim_gate(
    *,
    all_success_ni_pass: bool,
    all_task_token_pass: bool,
    holm_pass: bool,
    three_model_families: bool,
    required_pairings_complete: bool,
    three_repeats: bool,
    complete_cost_ledger: bool,
    power_gate_pass: bool,
    negative_results_visible: bool,
    no_receiver_regression_over_one_pp: bool,
) -> dict[str, Any]:
    fields = {
        "all_success_ni_pass": all_success_ni_pass,
        "all_task_token_pass": all_task_token_pass,
        "holm_pass": holm_pass,
        "three_model_families": three_model_families,
        "required_pairings_complete": required_pairings_complete,
        "three_repeats": three_repeats,
        "complete_cost_ledger": complete_cost_ledger,
        "power_gate_pass": power_gate_pass,
        "negative_results_visible": negative_results_visible,
        "no_receiver_regression_over_one_pp": no_receiver_regression_over_one_pp,
    }
    return {
        "gate": "competitive_symbolic_format",
        "passed": all(fields.values()),
        **fields,
        "noninferiority_margin": NONINFERIORITY_MARGIN,
        "token_reduction_lcb_threshold": TOKEN_REDUCTION_GATE,
    }
