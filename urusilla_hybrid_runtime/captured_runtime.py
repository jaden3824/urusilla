"""Capture-backed hybrid execution without provider-claim promotion.

This module closes the gap between the route the runtime intended to send and
the role-separated request an honest provider adapter says it transmitted.  It
does not authenticate that adapter, the provider, or its usage receipt.  Those
facts therefore remain ineligible for frozen research claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .canonical import sha256_text
from .captured_receiver import (
    CapturedReceiverAdapter,
    CapturedReceiverExecution,
    execute_captured_receiver,
    validate_captured_receiver_endpoint,
)
from .errors import ReceiverError
from .runtime import (
    LocalOutputValidation,
    ObservedExecutionLedger,
    ObservedLocalUsage,
    OutputValidationInput,
    PreparedMessage,
    _build_observed_execution_ledger,
    _validate_public_output,
)
from .task_context import PublicTaskContext


_FINGERPRINT_FIELDS = (
    "prepared",
    "primary",
    "fallback",
    "final_mode",
    "compiler_calls",
    "fidelity_verifier_calls",
    "receiver_calls",
    "output_valid",
    "safely_completed",
    "capture_chain_valid",
    "observed_runtime_tokens",
    "observed_local_usage",
    "observed_ledger",
    "provider_authenticity_verified",
    "claim_eligible",
    "goal_total_complete",
)


class _CapturedHybridSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _observation_fingerprint(values: dict[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _FINGERPRINT_FIELDS))
    )


def _baseline_request(prepared: PreparedMessage):
    return next(
        (
            item
            for item in prepared.route.candidates
            if item.mode == prepared.route.best_baseline_mode
        ),
        None,
    )


def _execution_matches_request(
    execution: CapturedReceiverExecution,
    request,
) -> bool:
    execution.validate()
    return bool(
        execution.request_binding_sha256 == request.binding_sha256
        and execution.intended_model_visible_sha256
        == sha256_text(request.model_visible_text)
    )


@dataclass(frozen=True)
class CapturedHybridExecution:
    """One prepared route executed only through capture-returning endpoints.

    ``scope_complete`` concerns the local runtime ledger only.  All provenance
    and empirical-claim flags are structurally false because adapter-returned
    captures are not authenticated provider receipts.
    """

    prepared: PreparedMessage
    primary: CapturedReceiverExecution | None
    fallback: CapturedReceiverExecution | None
    final_mode: str
    compiler_calls: int
    fidelity_verifier_calls: int
    receiver_calls: int
    output_valid: bool | None
    safely_completed: bool | None
    capture_chain_valid: bool
    observed_runtime_tokens: int | None
    observed_ledger: ObservedExecutionLedger
    observed_local_usage: ObservedLocalUsage
    provider_authenticity_verified: bool = False
    claim_eligible: bool = False
    goal_total_complete: bool = False
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.prepared) is not PreparedMessage:
            raise ValueError("captured hybrid requires an exact preparation")
        if self.compiler_calls not in {0, 1}:
            raise ValueError("captured hybrid compiler calls must be zero or one")
        if self.fidelity_verifier_calls not in {0, 1}:
            raise ValueError(
                "captured hybrid fidelity verifier calls must be zero or one"
            )
        for name in (
            "capture_chain_valid",
            "provider_authenticity_verified",
            "claim_eligible",
            "goal_total_complete",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"captured hybrid {name} must be boolean")
        if any(
            (
                self.provider_authenticity_verified,
                self.claim_eligible,
                self.goal_total_complete,
            )
        ):
            raise ValueError(
                "capture-backed runtime cannot establish provider or claim authority"
            )
        for name in ("output_valid", "safely_completed"):
            if getattr(self, name) is not None and type(getattr(self, name)) is not bool:
                raise ValueError(f"captured hybrid {name} must be boolean or null")
        if self.observed_runtime_tokens is not None and (
            type(self.observed_runtime_tokens) is not int
            or self.observed_runtime_tokens < 0
        ):
            raise ValueError("captured hybrid observed tokens are invalid")
        if self.final_mode not in {
            "silence",
            "routine",
            "action-state",
            "raw",
            "json",
        }:
            raise ValueError("captured hybrid final mode is unknown")

        primary_request = self.prepared.route.request
        if self.prepared.route.selected_mode == "silence":
            if self.primary is not None or self.fallback is not None:
                raise ValueError("captured silence cannot contain provider executions")
            if self.receiver_calls != 0 or self.final_mode != "silence":
                raise ValueError("captured silence call accounting differs")
        else:
            if type(self.primary) is not CapturedReceiverExecution:
                raise ValueError("captured hybrid lost its primary execution")
            if not _execution_matches_request(self.primary, primary_request):
                raise ValueError("captured hybrid primary request binding differs")
            if (
                self.fallback is not None
                and type(self.fallback) is not CapturedReceiverExecution
            ):
                raise ValueError("captured hybrid fallback type is invalid")
            expected_calls = self.primary.calls + (
                self.fallback.calls if self.fallback is not None else 0
            )
            if self.receiver_calls != expected_calls:
                raise ValueError("captured hybrid receiver calls do not reconcile")

        if self.fallback is None:
            if self.final_mode != self.prepared.route.selected_mode:
                raise ValueError("captured hybrid final mode lost its primary route")
        else:
            if type(self.fallback) is not CapturedReceiverExecution:
                raise ValueError("captured hybrid fallback type is invalid")
            baseline = _baseline_request(self.prepared)
            if (
                self.prepared.route.selected_mode not in {"routine", "action-state"}
                or baseline is None
                or baseline.request is None
                or baseline.mode not in {"raw", "json"}
                or not _execution_matches_request(self.fallback, baseline.request)
                or self.final_mode != baseline.mode
            ):
                raise ValueError("captured hybrid fallback binding differs")

        executions = tuple(
            item for item in (self.primary, self.fallback) if item is not None
        )
        expected_chain_valid = all(
            item.status != "capture-rejected" for item in executions
        )
        if self.capture_chain_valid is not expected_chain_valid:
            raise ValueError("captured hybrid chain validity differs")
        if self.safely_completed is True and not self.capture_chain_valid:
            raise ValueError("rejected capture cannot become a safe completion")

        if (
            type(self.observed_local_usage) is not ObservedLocalUsage
            or self.observed_local_usage.execution_binding_sha256
            != self.prepared.execution_binding_sha256
            or type(self.observed_ledger) is not ObservedExecutionLedger
        ):
            raise ValueError("captured hybrid observations are unbound")
        expected_ledger = _build_observed_execution_ledger(
            self.prepared,
            self.primary,
            self.fallback,
            self.observed_local_usage,
        )
        if (
            self.observed_ledger != expected_ledger
            or self.observed_ledger.observed_model_total_tokens
            != self.observed_runtime_tokens
        ):
            raise ValueError("captured hybrid observed ledger differs")
        values = {name: getattr(self, name) for name in _FINGERPRINT_FIELDS}
        if (
            type(self._construction_seal) is not _CapturedHybridSeal
            or self._construction_seal.fingerprint
            != _observation_fingerprint(values)
        ):
            raise ValueError(
                "CapturedHybridExecution observations must be minted by the executor"
            )

    @property
    def scope_complete(self) -> bool:
        return self.observed_ledger.scope_complete

    @property
    def inclusive_total_tokens(self) -> int | None:
        return self.observed_ledger.inclusive_total_tokens


def _validate_local_usage(
    prepared: PreparedMessage,
    observed_local_usage: ObservedLocalUsage | None,
) -> ObservedLocalUsage:
    if observed_local_usage is None:
        observed_local_usage = ObservedLocalUsage.for_prepared(prepared)
    if (
        type(observed_local_usage) is not ObservedLocalUsage
        or observed_local_usage.execution_binding_sha256
        != prepared.execution_binding_sha256
    ):
        raise ValueError("observed local usage is not bound to this preparation")
    for name in ("repair_tokens", "tool_tokens"):
        if getattr(observed_local_usage, name) not in {None, 0}:
            raise ValueError(
                f"observed {name} cannot be positive without an executed phase"
            )
    if (
        prepared.route.selected_mode in {"silence", "raw", "json"}
        and observed_local_usage.fallback_tokens not in {None, 0}
    ):
        raise ValueError(
            "observed fallback_tokens cannot be positive without a fallback"
        )
    return observed_local_usage


def _preflight_endpoints(
    prepared: PreparedMessage,
    primary_adapter: CapturedReceiverAdapter | None,
    primary_expected_model_id: str | None,
    primary_expected_settings_sha256: str | None,
    fallback_adapter: CapturedReceiverAdapter | None,
    fallback_expected_model_id: str | None,
    fallback_expected_settings_sha256: str | None,
) -> None:
    primary_values = (
        primary_adapter,
        primary_expected_model_id,
        primary_expected_settings_sha256,
    )
    fallback_values = (
        fallback_adapter,
        fallback_expected_model_id,
        fallback_expected_settings_sha256,
    )
    if prepared.route.selected_mode == "silence":
        if any(item is not None for item in primary_values + fallback_values):
            raise ReceiverError("captured silence does not accept provider endpoints")
        return
    if any(item is None for item in primary_values):
        raise ReceiverError("captured primary endpoint bindings are incomplete")
    assert primary_adapter is not None
    assert primary_expected_model_id is not None
    assert primary_expected_settings_sha256 is not None
    validate_captured_receiver_endpoint(
        primary_adapter,
        expected_model_id=primary_expected_model_id,
        expected_settings_sha256=primary_expected_settings_sha256,
    )

    optimized = prepared.route.selected_mode in {"routine", "action-state"}
    if optimized:
        baseline = _baseline_request(prepared)
        if baseline is None or baseline.request is None:
            raise ReceiverError("captured optimized route lost its baseline request")
        if any(item is None for item in fallback_values):
            raise ReceiverError(
                "captured optimized route requires an explicit fallback endpoint"
            )
        assert fallback_adapter is not None
        assert fallback_expected_model_id is not None
        assert fallback_expected_settings_sha256 is not None
        validate_captured_receiver_endpoint(
            fallback_adapter,
            expected_model_id=fallback_expected_model_id,
            expected_settings_sha256=fallback_expected_settings_sha256,
        )
    elif any(item is not None for item in fallback_values):
        raise ReceiverError("baseline route cannot declare an unused fallback endpoint")


def execute_prepared_message_captured(
    prepared: PreparedMessage,
    primary_adapter: CapturedReceiverAdapter | None,
    *,
    primary_expected_model_id: str | None,
    primary_expected_settings_sha256: str | None,
    fallback_adapter: CapturedReceiverAdapter | None = None,
    fallback_expected_model_id: str | None = None,
    fallback_expected_settings_sha256: str | None = None,
    output_validator: Callable[
        [OutputValidationInput], LocalOutputValidation
    ]
    | None,
    observed_local_usage: ObservedLocalUsage | None = None,
) -> CapturedHybridExecution:
    """Execute a prepared message through preflighted capture endpoints.

    Optimized modes require an explicit baseline endpoint, and both endpoint
    surfaces are preflighted before the primary request is dispatched.  A
    capture mismatch can still trigger the lossless fallback, but it makes the
    overall capture chain invalid and can never be reported as a safe or
    claim-eligible completion.
    """

    if type(prepared) is not PreparedMessage:
        raise ValueError("captured hybrid requires an exact preparation")
    local_usage = _validate_local_usage(prepared, observed_local_usage)
    _preflight_endpoints(
        prepared,
        primary_adapter,
        primary_expected_model_id,
        primary_expected_settings_sha256,
        fallback_adapter,
        fallback_expected_model_id,
        fallback_expected_settings_sha256,
    )

    expected_validator_sha256 = PublicTaskContext.from_json(
        prepared.route.request.task_context_text
    ).output_validator_sha256
    primary: CapturedReceiverExecution | None = None
    fallback: CapturedReceiverExecution | None = None
    final_mode = prepared.route.selected_mode

    if prepared.route.selected_mode == "silence":
        primary_valid: bool | None = True
    else:
        assert primary_adapter is not None
        assert primary_expected_model_id is not None
        assert primary_expected_settings_sha256 is not None
        primary = execute_captured_receiver(
            prepared.route.request,
            primary_adapter,
            expected_model_id=primary_expected_model_id,
            expected_settings_sha256=primary_expected_settings_sha256,
        )
        primary_valid = _validate_public_output(
            primary,
            prepared.route.request,
            prepared.route.source_sha256,
            output_validator,
            expected_validator_sha256,
        )

    final_valid = primary_valid
    if (
        prepared.route.selected_mode in {"routine", "action-state"}
        and primary_valid is not True
    ):
        baseline = _baseline_request(prepared)
        assert baseline is not None and baseline.request is not None
        assert fallback_adapter is not None
        assert fallback_expected_model_id is not None
        assert fallback_expected_settings_sha256 is not None
        fallback = execute_captured_receiver(
            baseline.request,
            fallback_adapter,
            expected_model_id=fallback_expected_model_id,
            expected_settings_sha256=fallback_expected_settings_sha256,
        )
        final_mode = baseline.mode
        final_valid = _validate_public_output(
            fallback,
            baseline.request,
            prepared.route.source_sha256,
            output_validator,
            expected_validator_sha256,
        )

    compiler_calls = int(
        prepared.compilation is not None and prepared.compilation.attempted
    )
    fidelity_calls = (
        0
        if prepared.fidelity_verification is None
        else prepared.fidelity_verification.model_calls
    )
    receiver_calls = sum(
        item.calls for item in (primary, fallback) if item is not None
    )
    usage_values: list[int] = []
    usage_complete = True
    if compiler_calls:
        assert prepared.compilation is not None
        if prepared.compilation.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(prepared.compilation.total_tokens)
    if prepared.fidelity_verification is not None:
        if prepared.fidelity_verification.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(prepared.fidelity_verification.total_tokens)
    for execution in (primary, fallback):
        if execution is None:
            continue
        total = execution.total_tokens
        if total is None:
            usage_complete = False
        else:
            usage_values.append(total)
    observed = sum(usage_values) if usage_complete else None
    ledger = _build_observed_execution_ledger(
        prepared,
        primary,
        fallback,
        local_usage,
    )
    if ledger.observed_model_total_tokens != observed:
        raise ValueError("captured model usage does not reconcile with the ledger")
    capture_chain_valid = all(
        item.status != "capture-rejected"
        for item in (primary, fallback)
        if item is not None
    )
    safely_completed = final_valid if type(final_valid) is bool else None
    if not capture_chain_valid:
        safely_completed = False
    result_values = {
        "prepared": prepared,
        "primary": primary,
        "fallback": fallback,
        "final_mode": final_mode,
        "compiler_calls": compiler_calls,
        "fidelity_verifier_calls": fidelity_calls,
        "receiver_calls": receiver_calls,
        "output_valid": final_valid,
        "safely_completed": safely_completed,
        "capture_chain_valid": capture_chain_valid,
        "observed_runtime_tokens": observed,
        "observed_ledger": ledger,
        "observed_local_usage": local_usage,
        "provider_authenticity_verified": False,
        "claim_eligible": False,
        "goal_total_complete": False,
    }
    return CapturedHybridExecution(
        **result_values,
        _construction_seal=_CapturedHybridSeal(
            _observation_fingerprint(result_values)
        ),
    )


__all__ = [
    "CapturedHybridExecution",
    "execute_prepared_message_captured",
]
