"""Runtime-only accounting for several exact turns in one receiver session.

This module does not change the Urusilla language or authorize a route.  It
combines already sealed session executions with their exact raw/JSON controls,
charges the cold comprehension call once, and keeps incomplete usage null.
Provider receipt authenticity and provider full-history billing remain
unverified, so the result cannot establish complete goal accounting or a
performance claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from fractions import Fraction
import re
from typing import Mapping

from .canonical import canonical_json, sha256_text
from .comprehension import ComprehensionAttempt
from .runtime import HybridExecution, PreparedMessage
from .session import SessionObservation, SessionTurnLease
from .session_runtime import SessionBoundExecution


SESSION_PORTFOLIO_ACCOUNTING_FORMAT = (
    "urusilla-session-portfolio-accounting-draft/1"
)
SESSION_PORTFOLIO_LOCAL_SCOPE = (
    "session-turn-local-exclusive-of-shared-comprehension-and-model-calls"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_LOCAL_TOKEN_FIELDS = (
    "setup_tokens",
    "router_tokens",
    "repair_tokens",
    "fallback_tokens",
    "tool_tokens",
    "safety_tokens",
    "judge_tokens",
)


class SessionPortfolioError(ValueError):
    """A portfolio receipt or accounting binding was not exact."""


@dataclass(frozen=True)
class SessionPortfolioLocalUsage:
    """Non-overlapping local usage for one session task.

    The binding covers both the optimized preparation and its independently
    prepared cold fallback.  ``setup_tokens`` excludes the shared cold
    comprehension provider call.  Every nullable token field is required for
    a structurally complete reported total; unknown is never replaced by a
    forecast or by zero.
    """

    session_binding_sha256: str
    lease_sha256: str
    optimized_execution_binding_sha256: str
    fallback_execution_binding_sha256: str
    setup_tokens: int | None = None
    router_tokens: int | None = None
    repair_tokens: int | None = None
    fallback_tokens: int | None = None
    tool_tokens: int | None = None
    safety_tokens: int | None = None
    judge_tokens: int | None = None
    scope: str = SESSION_PORTFOLIO_LOCAL_SCOPE

    def __post_init__(self) -> None:
        for name in (
            "session_binding_sha256",
            "lease_sha256",
            "optimized_execution_binding_sha256",
            "fallback_execution_binding_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise SessionPortfolioError(
                    f"portfolio local usage {name} is invalid"
                )
        if self.scope != SESSION_PORTFOLIO_LOCAL_SCOPE:
            raise SessionPortfolioError(
                "portfolio local usage must exclude shared comprehension and model calls"
            )
        for name in _LOCAL_TOKEN_FIELDS:
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise SessionPortfolioError(
                    f"portfolio local usage {name} is invalid"
                )

    @property
    def usage_complete(self) -> bool:
        return all(getattr(self, name) is not None for name in _LOCAL_TOKEN_FIELDS)

    @property
    def total_tokens(self) -> int | None:
        if not self.usage_complete:
            return None
        return sum(getattr(self, name) or 0 for name in _LOCAL_TOKEN_FIELDS)

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    item.name: getattr(self, item.name)
                    for item in fields(self)
                }
            )
        )


@dataclass(frozen=True)
class SessionPortfolioTurn:
    """One hot session turn, its local ledger, and its exact cold control."""

    lease: SessionTurnLease
    execution: SessionBoundExecution
    local_usage: SessionPortfolioLocalUsage
    baseline: HybridExecution

    def __post_init__(self) -> None:
        if type(self.lease) is not SessionTurnLease:
            raise SessionPortfolioError("portfolio turn requires an exact lease")
        if type(self.execution) is not SessionBoundExecution:
            raise SessionPortfolioError(
                "portfolio turn requires an exact session execution"
            )
        if type(self.local_usage) is not SessionPortfolioLocalUsage:
            raise SessionPortfolioError(
                "portfolio turn requires exact local usage"
            )
        if type(self.baseline) is not HybridExecution:
            raise SessionPortfolioError(
                "portfolio turn requires an exact raw/JSON baseline execution"
            )


def _prepared_model_tokens(prepared: PreparedMessage) -> int | None:
    values: list[int] = []
    compilation = prepared.compilation
    if compilation is not None and compilation.attempted:
        if compilation.total_tokens is None:
            return None
        values.append(compilation.total_tokens)
    fidelity = prepared.fidelity_verification
    if fidelity is not None and fidelity.model_calls:
        if fidelity.total_tokens is None:
            return None
        values.append(fidelity.total_tokens)
    return sum(values)


def _primary_tokens(execution: SessionBoundExecution) -> int | None:
    if execution.primary_calls == 0:
        return 0
    if execution.primary_reply is None:
        return None
    return execution.primary_reply.provider_total_tokens


def _fallback_tokens(execution: SessionBoundExecution) -> int | None:
    if execution.fallback_calls == 0:
        return 0
    fallback = execution.fallback_execution
    if fallback is None:
        return None
    return fallback.total_tokens


def _turn_candidate_tokens(turn: SessionPortfolioTurn) -> int | None:
    execution = turn.execution
    plan = execution.plan
    if plan is None:
        return None
    values = (
        _prepared_model_tokens(plan.optimized),
        _prepared_model_tokens(execution.fallback_prepared),
        turn.local_usage.total_tokens,
        _primary_tokens(execution),
        _fallback_tokens(execution),
    )
    if any(value is None for value in values):
        return None
    return sum(value or 0 for value in values)


def _turn_summary(turn: SessionPortfolioTurn) -> Mapping[str, object]:
    execution = turn.execution
    return {
        "turn": turn.lease.turn,
        "lease_sha256": turn.lease.sha256,
        "optimized_execution_binding_sha256": (
            execution.plan.optimized_execution_binding_sha256
            if execution.plan is not None
            else None
        ),
        "fallback_execution_binding_sha256": (
            execution.fallback_prepared.execution_binding_sha256
        ),
        "local_usage_binding_sha256": turn.local_usage.binding_sha256,
        "primary_calls": execution.primary_calls,
        "fallback_calls": execution.fallback_calls,
        "optimized_failure": execution.optimized_failure,
        "primary_reported_tokens": _primary_tokens(execution),
        "fallback_reported_tokens": _fallback_tokens(execution),
        "candidate_reported_tokens_excluding_shared_setup": (
            _turn_candidate_tokens(turn)
        ),
        "candidate_safely_completed": execution.safely_completed,
        "baseline_mode": turn.baseline.final_mode,
        "baseline_reported_tokens": turn.baseline.inclusive_total_tokens,
        "baseline_safely_completed": turn.baseline.safely_completed,
    }


_ACCOUNTING_FIELDS = (
    "attempt",
    "opening_observation",
    "turns",
    "setup_reported_tokens",
    "candidate_reported_total_tokens",
    "baseline_reported_total_tokens",
    "reported_usage_complete",
    "matched_safely_completed",
)


class _SessionPortfolioSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _accounting_fingerprint(values: Mapping[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _ACCOUNTING_FIELDS))
    )


@dataclass(frozen=True)
class SessionPortfolioAccounting:
    """Sealed provider-reported portfolio accounting, never claim evidence."""

    attempt: ComprehensionAttempt
    opening_observation: SessionObservation
    turns: tuple[SessionPortfolioTurn, ...]
    setup_reported_tokens: int | None
    candidate_reported_total_tokens: int | None
    baseline_reported_total_tokens: int | None
    reported_usage_complete: bool
    matched_safely_completed: bool
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {name: getattr(self, name) for name in _ACCOUNTING_FIELDS}
        if (
            not isinstance(self._construction_seal, _SessionPortfolioSeal)
            or self._construction_seal.fingerprint
            != _accounting_fingerprint(values)
        ):
            raise SessionPortfolioError(
                "SessionPortfolioAccounting must be created by its bounded builder"
            )
        if type(self.reported_usage_complete) is not bool:
            raise SessionPortfolioError(
                "portfolio reported usage completeness must be boolean"
            )
        if type(self.matched_safely_completed) is not bool:
            raise SessionPortfolioError(
                "portfolio safe-completion status must be boolean"
            )
        for name in (
            "setup_reported_tokens",
            "candidate_reported_total_tokens",
            "baseline_reported_total_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise SessionPortfolioError(f"portfolio {name} is invalid")
        if self.reported_usage_complete is not (
            self.candidate_reported_total_tokens is not None
            and self.baseline_reported_total_tokens is not None
        ):
            raise SessionPortfolioError(
                "portfolio reported usage completeness differs from totals"
            )

    @property
    def session_binding_sha256(self) -> str:
        return self.opening_observation.session_binding_sha256

    @property
    def comprehension_evidence_sha256(self) -> str:
        evidence = self.attempt.evidence
        assert evidence is not None
        return evidence.sha256

    @property
    def setup_charge_count(self) -> int:
        return 1

    @property
    def baseline_modes(self) -> tuple[str, ...]:
        return tuple(turn.baseline.final_mode for turn in self.turns)

    @property
    def reported_token_saving_fraction(self) -> Fraction | None:
        if (
            not self.reported_usage_complete
            or not self.matched_safely_completed
            or self.baseline_reported_total_tokens in {None, 0}
        ):
            return None
        assert self.candidate_reported_total_tokens is not None
        assert self.baseline_reported_total_tokens is not None
        return Fraction(
            self.baseline_reported_total_tokens
            - self.candidate_reported_total_tokens,
            self.baseline_reported_total_tokens,
        )

    @property
    def reported_token_saving_percent(self) -> Fraction | None:
        saving = self.reported_token_saving_fraction
        return None if saving is None else saving * 100

    @property
    def complete_total_tokens(self) -> None:
        return None

    @property
    def complete_total_token_saving_percent(self) -> None:
        return None

    @property
    def provider_authenticity_verified(self) -> bool:
        return False

    @property
    def provider_full_history_billing_verified(self) -> bool:
        return False

    @property
    def goal_total_complete(self) -> bool:
        return False

    @property
    def claim_eligible(self) -> bool:
        return False

    def to_object(self) -> dict[str, object]:
        saving = self.reported_token_saving_fraction
        return {
            "format": SESSION_PORTFOLIO_ACCOUNTING_FORMAT,
            "session_binding_sha256": self.session_binding_sha256,
            "comprehension_evidence_sha256": (
                self.comprehension_evidence_sha256
            ),
            "setup_charge_count": 1,
            "setup_reported_tokens": self.setup_reported_tokens,
            "turns": [dict(_turn_summary(turn)) for turn in self.turns],
            "baseline_modes": list(self.baseline_modes),
            "candidate_reported_total_tokens": (
                self.candidate_reported_total_tokens
            ),
            "baseline_reported_total_tokens": (
                self.baseline_reported_total_tokens
            ),
            "reported_usage_complete": self.reported_usage_complete,
            "matched_safely_completed": self.matched_safely_completed,
            "reported_token_saving": (
                None
                if saving is None
                else {
                    "numerator_tokens": saving.numerator,
                    "denominator_tokens": saving.denominator,
                }
            ),
            "complete_total_tokens": None,
            "complete_total_token_saving_percent": None,
            "provider_authenticity_verified": False,
            "provider_full_history_billing_verified": False,
            "goal_total_complete": False,
            "claim_eligible": False,
        }

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


def _validate_opening(
    attempt: ComprehensionAttempt,
    opening: SessionObservation,
) -> None:
    if type(attempt) is not ComprehensionAttempt or not attempt.passed:
        raise SessionPortfolioError(
            "session portfolio requires passed comprehension"
        )
    if type(opening) is not SessionObservation:
        raise SessionPortfolioError(
            "session portfolio requires an exact opening observation"
        )
    evidence = attempt.evidence
    assert evidence is not None
    if (
        opening.next_turn != 1
        or opening.context_reset_observed
        or opening.context_compaction_observed
    ):
        raise SessionPortfolioError(
            "portfolio opening must precede the first uncompacted session turn"
        )
    exact_pairs = (
        (opening.model_id, evidence.model_id),
        (opening.model_settings_sha256, evidence.model_settings_sha256),
        (opening.system_sha256, sha256_text(attempt.challenge.system_text)),
        (opening.capsule_sha256, evidence.capsule_sha256),
        (opening.task_context_sha256, evidence.task_context_sha256),
        (opening.task_profile_sha256, evidence.task_profile_sha256),
        (opening.symbol_table_sha256, evidence.symbol_table_sha256),
        (opening.comprehension_evidence_sha256, evidence.sha256),
    )
    if any(actual != expected for actual, expected in exact_pairs):
        raise SessionPortfolioError(
            "portfolio opening differs from comprehension evidence"
        )


def _validate_turn(
    turn: SessionPortfolioTurn,
    *,
    attempt: ComprehensionAttempt,
    opening: SessionObservation,
    expected_turn: int,
    expected_parent_transcript_sha256: str,
    expected_previous_receipts_sha256: str,
    last: bool,
) -> tuple[str, str]:
    if type(turn) is not SessionPortfolioTurn:
        raise SessionPortfolioError("portfolio turns must use their exact type")
    lease = turn.lease
    execution = turn.execution
    plan = execution.plan
    if plan is None:
        raise SessionPortfolioError(
            "portfolio turn has no session-bound optimized plan"
        )
    if execution.attempt != attempt:
        raise SessionPortfolioError(
            "portfolio turn uses another comprehension attempt"
        )
    if execution.primary_calls != 1:
        raise SessionPortfolioError(
            "portfolio turn requires one attempted hot receiver call"
        )
    if execution.status != "optimized-completed" and not last:
        raise SessionPortfolioError(
            "a failed optimized path must be the terminal portfolio turn"
        )
    evidence = attempt.evidence
    assert evidence is not None
    exact_lease_pairs = (
        (lease.turn, expected_turn),
        (lease.session_binding_sha256, opening.session_binding_sha256),
        (lease.model_id, opening.model_id),
        (lease.model_settings_sha256, opening.model_settings_sha256),
        (lease.system_sha256, opening.system_sha256),
        (lease.context_epoch, opening.context_epoch),
        (lease.session_nonce_sha256, opening.session_nonce_sha256),
        (lease.parent_transcript_chain_sha256, expected_parent_transcript_sha256),
        (lease.previous_provider_receipts_sha256, expected_previous_receipts_sha256),
        (lease.capsule_sha256, evidence.capsule_sha256),
        (lease.task_context_sha256, evidence.task_context_sha256),
        (lease.task_profile_sha256, evidence.task_profile_sha256),
        (lease.symbol_table_sha256, evidence.symbol_table_sha256),
        (lease.comprehension_evidence_sha256, evidence.sha256),
        (lease.request_sha256, sha256_text(plan.primary_request.user_data_text)),
    )
    if any(actual != expected for actual, expected in exact_lease_pairs):
        raise SessionPortfolioError(
            "portfolio lease is noncontiguous or differs from its session binding"
        )
    cached = plan.cached_receiver
    if (
        cached.session_binding_sha256 != opening.session_binding_sha256
        or cached.comprehension_evidence_sha256 != evidence.sha256
        or cached.last_provider_receipts_sha256
        != expected_previous_receipts_sha256
        or plan.fallback != execution.fallback_prepared
        or plan.optimized_execution_binding_sha256
        != plan.optimized.execution_binding_sha256
        or plan.fallback_execution_binding_sha256
        != execution.fallback_prepared.execution_binding_sha256
    ):
        raise SessionPortfolioError(
            "portfolio plan differs from its exact session predecessor"
        )
    local = turn.local_usage
    if (
        local.session_binding_sha256 != opening.session_binding_sha256
        or local.lease_sha256 != lease.sha256
        or local.optimized_execution_binding_sha256
        != plan.optimized.execution_binding_sha256
        or local.fallback_execution_binding_sha256
        != execution.fallback_prepared.execution_binding_sha256
    ):
        raise SessionPortfolioError(
            "portfolio local usage differs from its exact turn"
        )
    if local.repair_tokens not in {None, 0} or local.tool_tokens not in {None, 0}:
        raise SessionPortfolioError(
            "session portfolio cannot report an unexecuted repair or tool phase"
        )
    if execution.fallback_calls == 0 and local.fallback_tokens not in {None, 0}:
        raise SessionPortfolioError(
            "portfolio cannot report fallback usage without a fallback call"
        )

    baseline = turn.baseline
    fallback = execution.fallback_prepared
    if (
        baseline.prepared != fallback
        or baseline.prepared.execution_binding_sha256
        != fallback.execution_binding_sha256
        or baseline.prepared.route.selected_mode not in {"raw", "json"}
        or baseline.final_mode != baseline.prepared.route.selected_mode
        or baseline.fallback is not None
        or baseline.prepared.route.source_sha256
        != plan.optimized.route.source_sha256
        or baseline.prepared.route.capsule_sha256
        != plan.optimized.route.capsule_sha256
        or baseline.prepared.route.request.task_context_sha256
        != plan.primary_request.task_context_sha256
    ):
        raise SessionPortfolioError(
            "portfolio baseline is not the exact raw/JSON fallback comparator"
        )

    primary_result = execution.primary_result
    if primary_result is None:
        if not last:
            raise SessionPortfolioError(
                "a turn without a terminal receipt cannot precede another turn"
            )
        return expected_parent_transcript_sha256, expected_previous_receipts_sha256
    if primary_result.lease_sha256 != lease.sha256:
        raise SessionPortfolioError(
            "portfolio execution receipt differs from its lease"
        )
    return (
        primary_result.transcript_chain_sha256,
        primary_result.provider_receipts_sha256,
    )


def build_session_portfolio_accounting(
    attempt: ComprehensionAttempt,
    opening_observation: SessionObservation,
    turns: tuple[SessionPortfolioTurn, ...],
) -> SessionPortfolioAccounting:
    """Build one setup-once, fail-closed reported-token portfolio ledger."""

    _validate_opening(attempt, opening_observation)
    if type(turns) is not tuple or not turns:
        raise SessionPortfolioError(
            "session portfolio requires a non-empty exact turn tuple"
        )
    expected_parent = opening_observation.transcript_chain_sha256
    expected_receipts = opening_observation.last_provider_receipts_sha256
    seen_leases: set[str] = set()
    for index, turn in enumerate(turns, start=1):
        if type(turn) is not SessionPortfolioTurn:
            raise SessionPortfolioError(
                "session portfolio turn type is invalid"
            )
        lease_sha256 = turn.lease.sha256
        if lease_sha256 in seen_leases:
            raise SessionPortfolioError(
                "session portfolio contains a duplicate lease"
            )
        seen_leases.add(lease_sha256)
        expected_parent, expected_receipts = _validate_turn(
            turn,
            attempt=attempt,
            opening=opening_observation,
            expected_turn=index,
            expected_parent_transcript_sha256=expected_parent,
            expected_previous_receipts_sha256=expected_receipts,
            last=index == len(turns),
        )

    setup = attempt.total_tokens
    turn_totals = tuple(_turn_candidate_tokens(turn) for turn in turns)
    baseline_totals = tuple(
        turn.baseline.inclusive_total_tokens for turn in turns
    )
    candidate_total = (
        None
        if setup is None or any(value is None for value in turn_totals)
        else setup + sum(value or 0 for value in turn_totals)
    )
    baseline_total = (
        None
        if any(value is None for value in baseline_totals)
        else sum(value or 0 for value in baseline_totals)
    )
    matched_safe = all(
        turn.execution.safely_completed
        and turn.baseline.safely_completed is True
        for turn in turns
    )
    values: dict[str, object] = {
        "attempt": attempt,
        "opening_observation": opening_observation,
        "turns": turns,
        "setup_reported_tokens": setup,
        "candidate_reported_total_tokens": candidate_total,
        "baseline_reported_total_tokens": baseline_total,
        "reported_usage_complete": (
            candidate_total is not None and baseline_total is not None
        ),
        "matched_safely_completed": matched_safe,
    }
    return SessionPortfolioAccounting(
        **values,
        _construction_seal=_SessionPortfolioSeal(
            _accounting_fingerprint(values)
        ),
    )
