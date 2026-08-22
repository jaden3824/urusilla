"""Provider-free bridge from one real runtime execution to declared scoring.

The runtime already prepares and executes one hybrid message, including a
bounded raw/JSON fallback and a runtime-scoped inclusive ledger.  This module
closes the next local orchestration gap: it presents *only the final terminal
output* to an injected task scorer and derives the task-result,
scoring-binding, and deterministic-judge fragments consumed by the offline
execution-trace assembler.

It performs no provider call of its own, grants no network or credential
authority, does not authenticate the injected adapter or scorer, and cannot
produce claim-eligible evidence.  Mapping provider calls into authenticated
external-response records and independently observed sandbox receipts remains
a separate evidence-production boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

from urusilla_hybrid_runtime.canonical import canonical_json
from urusilla_hybrid_runtime.receiver import ReceiverModelAdapter
from urusilla_hybrid_runtime.runtime import (
    HybridExecution,
    LocalOutputValidation,
    ObservedLocalUsage,
    OutputValidationInput,
    PreparedMessage,
    execute_prepared_message,
)
from urusilla_hybrid_runtime.sender import source_text_sha256

from .contract import FEATURE_TAGS, VerificationError, sha256_ref
from .execution_trace import task_input_sha256
from .terminal_contract import (
    CANONICAL_SILENCE_OUTPUT_SHA256,
    CAPTURE_TERMINAL_STATUSES,
    SILENCE_TERMINAL_STATUS,
)


SCORING_INPUT_SCHEMA = "urusilla-initial-goal-runtime-scoring-input/1"
SCORING_OUTPUT_SCHEMA = "urusilla-initial-goal-runtime-scoring-output/1"
SCORER_OBSERVATION_SCHEMA = "urusilla-initial-goal-runtime-scorer-observation/1"
ORCHESTRATION_BOUNDARY = "provider-free-runtime-scoring-diagnostic-only"

_SHA256_REF = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFETY_FIELDS = (
    "unauthorized_external_effects",
    "persistence_events",
    "permission_expansions",
    "spending_authority_events",
    "unknown_schema_executions",
)
_SCORER_LOCK_FIELDS = (
    "task_scorer",
    "parse_scorer",
    "semantic_scorer",
    "negative_scorer",
)


def _detached(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _require_sha256_ref(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_REF.fullmatch(value) is None:
        raise VerificationError(f"{label} must be a sha256 reference")
    return value


def _nullable_bool(value: Any, label: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise VerificationError(f"{label} must be boolean or null")
    return value


def _scorer_locks(value: Any, label: str) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(_SCORER_LOCK_FIELDS):
        raise VerificationError(f"{label} fields differ")
    return {
        field: _require_sha256_ref(value[field], f"{label}.{field}")
        for field in _SCORER_LOCK_FIELDS
    }


def _ledger_value(execution: HybridExecution) -> Mapping[str, Any] | None:
    ledger = execution.observed_ledger
    if ledger is None:
        return None
    return {
        "execution_binding_sha256": ledger.execution_binding_sha256,
        "events": [
            {
                "sequence": event.sequence,
                "phase": event.phase,
                "component": event.component,
                "execution_binding_sha256": event.execution_binding_sha256,
                "artifact_binding_sha256": event.artifact_binding_sha256,
                "total_tokens": event.total_tokens,
                "model_calls": event.model_calls,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "reasoning_tokens": event.reasoning_tokens,
                "reasoning_accounting": event.reasoning_accounting,
            }
            for event in ledger.events
        ],
        "scope_complete": ledger.scope_complete,
        "inclusive_total_tokens": ledger.inclusive_total_tokens,
        "provider_authenticity_verified": False,
        "claim_eligible": False,
        "goal_total_complete": False,
    }


def _terminal_view(
    execution: HybridExecution,
) -> tuple[str, str | None, str | None, str]:
    terminal = execution.fallback or execution.primary
    if terminal.status == "silenced":
        return (
            SILENCE_TERMINAL_STATUS,
            None,
            CANONICAL_SILENCE_OUTPUT_SHA256,
            sha256_ref(
                {
                    "terminal_status": SILENCE_TERMINAL_STATUS,
                    "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                    "failure": None,
                }
            ),
        )
    output_text = terminal.reply.text if terminal.reply is not None else None
    output_sha256 = (
        sha256_ref({"provider_output_text": output_text})
        if output_text is not None
        else None
    )
    status = "completed" if terminal.status == "completed" else "provider_error"
    observation_sha256 = sha256_ref(
        {
            "terminal_status": status,
            "receiver_status": terminal.status,
            "output_sha256": output_sha256,
            "failure": terminal.failure,
        }
    )
    return status, output_text, output_sha256, observation_sha256


def _fallback_from(execution: HybridExecution) -> str | None:
    prepared_fallback = execution.prepared.route.fallback_from
    if execution.fallback is None:
        return prepared_fallback
    primary = execution.primary
    if primary.status == "completed":
        reason = "semantic-invalid"
    elif primary.status == "budget-exceeded":
        reason = "token-budget-exceeded"
    else:
        reason = primary.failure or "provider-error"
    return f"{execution.prepared.route.selected_mode}:receiver:{reason}"


@dataclass(frozen=True)
class RuntimeScoringInput:
    """Exact public input given to the injected caller-declared scorer."""

    task_id: str
    task_sha256: str
    source_sha256: str
    feature_tags: tuple[str, ...]
    parse_probe: bool
    semantic_probe: bool
    negative_probe: bool
    arm_id: str
    selected_mode: str
    final_mode: str
    fallback_from: str | None
    terminal_status: str
    output_text: str | None
    output_sha256: str | None
    terminal_observation_sha256: str
    execution_binding_sha256: str
    route_binding_sha256: str
    primary_request_binding_sha256: str
    fallback_request_binding_sha256: str | None
    observed_ledger_sha256: str | None
    schema_version: str = SCORING_INPUT_SCHEMA

    def __post_init__(self) -> None:
        if type(self.task_id) is not str or not self.task_id:
            raise VerificationError("scoring input task_id must be non-empty")
        if (
            type(self.feature_tags) is not tuple
            or len(self.feature_tags) != len(set(self.feature_tags))
            or not set(self.feature_tags).issubset(FEATURE_TAGS)
        ):
            raise VerificationError("scoring input feature_tags are invalid")
        for field in ("parse_probe", "semantic_probe", "negative_probe"):
            if type(getattr(self, field)) is not bool:
                raise VerificationError(f"scoring input {field} must be boolean")
        if self.arm_id != "hybrid-router":
            raise VerificationError("runtime scorer accepts only the hybrid arm")
        for field in (
            "task_sha256",
            "source_sha256",
            "execution_binding_sha256",
            "route_binding_sha256",
            "primary_request_binding_sha256",
        ):
            _require_sha256_ref(getattr(self, field), f"scoring input {field}")
        if self.output_sha256 is not None:
            _require_sha256_ref(
                self.output_sha256, "scoring input output_sha256"
            )
        _require_sha256_ref(
            self.terminal_observation_sha256,
            "scoring input terminal_observation_sha256",
        )
        for field in (
            "fallback_request_binding_sha256",
            "observed_ledger_sha256",
        ):
            value = getattr(self, field)
            if value is not None:
                _require_sha256_ref(value, f"scoring input {field}")
        if self.selected_mode not in {
            "silence",
            "routine",
            "action-state",
            "raw",
            "json",
        }:
            raise VerificationError("scoring input selected_mode is invalid")
        if self.final_mode not in {
            "silence",
            "routine",
            "action-state",
            "raw",
            "json",
        }:
            raise VerificationError("scoring input final_mode is invalid")
        if self.terminal_status not in {
            *CAPTURE_TERMINAL_STATUSES,
            SILENCE_TERMINAL_STATUS,
        }:
            raise VerificationError("scoring input terminal_status is invalid")
        if self.terminal_status == SILENCE_TERMINAL_STATUS:
            if (
                self.output_text is not None
                or self.output_sha256 != CANONICAL_SILENCE_OUTPUT_SHA256
            ):
                raise VerificationError("silence scorer input is inconsistent")
        elif self.output_text is not None:
            expected = sha256_ref({"provider_output_text": self.output_text})
            if self.output_sha256 != expected:
                raise VerificationError("scoring input output digest differs")
        elif self.output_sha256 is not None:
            raise VerificationError("no-output scoring input must keep output digest null")
        if self.schema_version != SCORING_INPUT_SCHEMA:
            raise VerificationError("scoring input schema differs")

    @property
    def value(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_sha256": self.task_sha256,
            "source_sha256": self.source_sha256,
            "feature_tags": list(self.feature_tags),
            "parse_probe": self.parse_probe,
            "semantic_probe": self.semantic_probe,
            "negative_probe": self.negative_probe,
            "arm_id": self.arm_id,
            "selected_mode": self.selected_mode,
            "final_mode": self.final_mode,
            "fallback_from": self.fallback_from,
            "terminal_status": self.terminal_status,
            "output_text": self.output_text,
            "output_sha256": self.output_sha256,
            "terminal_observation_sha256": self.terminal_observation_sha256,
            "execution_binding_sha256": self.execution_binding_sha256,
            "route_binding_sha256": self.route_binding_sha256,
            "primary_request_binding_sha256": (
                self.primary_request_binding_sha256
            ),
            "fallback_request_binding_sha256": (
                self.fallback_request_binding_sha256
            ),
            "observed_ledger_sha256": self.observed_ledger_sha256,
        }

    @property
    def sha256(self) -> str:
        return sha256_ref(self.value)


@dataclass(frozen=True)
class RuntimeTaskScore:
    """Bounded output returned by a frozen task scorer."""

    task_success: bool | None
    parse_valid: bool | None
    semantic_exact: bool | None
    negative_rejected: bool | None
    preservation: Mapping[str, bool | None]
    safety: Mapping[str, int | None]
    scorer_kind: str
    total_tokens: int | None
    usage_complete: bool
    failure: str | None = None
    schema_version: str = SCORING_OUTPUT_SCHEMA

    def __post_init__(self) -> None:
        for field in (
            "task_success",
            "parse_valid",
            "semantic_exact",
            "negative_rejected",
        ):
            _nullable_bool(getattr(self, field), f"scorer output {field}")
        if set(self.preservation) != set(FEATURE_TAGS):
            raise VerificationError("scorer preservation fields differ")
        normalized_preservation = {
            key: _nullable_bool(
                self.preservation[key], f"scorer preservation {key}"
            )
            for key in FEATURE_TAGS
        }
        if set(self.safety) != set(_SAFETY_FIELDS):
            raise VerificationError("scorer safety fields differ")
        normalized_safety: dict[str, int | None] = {}
        for key in _SAFETY_FIELDS:
            value = self.safety[key]
            if value is not None and (type(value) is not int or value < 0):
                raise VerificationError(f"scorer safety {key} is invalid")
            normalized_safety[key] = value
        if self.total_tokens is not None and (
            type(self.total_tokens) is not int or self.total_tokens < 0
        ):
            raise VerificationError("scorer total_tokens is invalid")
        if type(self.usage_complete) is not bool:
            raise VerificationError("scorer usage_complete must be boolean")
        if self.usage_complete is not (self.total_tokens is not None):
            raise VerificationError("scorer usage completeness differs")
        if self.scorer_kind not in {
            "deterministic-local",
            "external-model",
            "unclassified",
        }:
            raise VerificationError("scorer kind is invalid")
        if self.failure is not None and (
            type(self.failure) is not str or not self.failure
        ):
            raise VerificationError("scorer failure is invalid")
        if self.failure is not None and any(
            value is not None
            for value in (
                self.task_success,
                self.parse_valid,
                self.semantic_exact,
                self.negative_rejected,
                *normalized_preservation.values(),
                *normalized_safety.values(),
            )
        ):
            raise VerificationError("failed scorer cannot report positive observations")
        if self.failure is None and self.scorer_kind == "unclassified":
            raise VerificationError("successful scorer cannot be unclassified")
        if self.failure is not None and self.scorer_kind != "unclassified":
            raise VerificationError("failed scorer kind must remain unclassified")
        if self.scorer_kind == "deterministic-local" and (
            self.total_tokens != 0 or not self.usage_complete
        ):
            raise VerificationError(
                "deterministic local scorer must declare zero model-token usage"
            )
        if self.schema_version != SCORING_OUTPUT_SCHEMA:
            raise VerificationError("scorer output schema differs")
        object.__setattr__(
            self,
            "preservation",
            MappingProxyType(normalized_preservation),
        )
        object.__setattr__(self, "safety", MappingProxyType(normalized_safety))

    @classmethod
    def failed(cls, reason: str) -> "RuntimeTaskScore":
        return cls(
            task_success=None,
            parse_valid=None,
            semantic_exact=None,
            negative_rejected=None,
            preservation={feature: None for feature in FEATURE_TAGS},
            safety={field: None for field in _SAFETY_FIELDS},
            scorer_kind="unclassified",
            total_tokens=None,
            usage_complete=False,
            failure=reason,
        )

    @property
    def value(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_success": self.task_success,
            "parse_valid": self.parse_valid,
            "semantic_exact": self.semantic_exact,
            "negative_rejected": self.negative_rejected,
            "preservation": dict(self.preservation),
            "safety": dict(self.safety),
            "scorer_kind": self.scorer_kind,
            "total_tokens": self.total_tokens,
            "usage_complete": self.usage_complete,
            "failure": self.failure,
        }


class RuntimeTaskScorer(Protocol):
    """Injected scorer whose caller-declared lock labels are checked before use."""

    def __call__(self, scoring_input: RuntimeScoringInput) -> RuntimeTaskScore:
        ...


class _ScoredTaskSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _scored_task_fingerprint(
    *,
    execution: HybridExecution,
    scoring_input: RuntimeScoringInput,
    score: RuntimeTaskScore,
    scorer_locks: Mapping[str, str],
    scorer_observation_sha256: str,
) -> str:
    return sha256_ref(
        {
            "execution_repr": repr(execution),
            "scoring_input": scoring_input.value,
            "scorer_output": score.value,
            "scorer_locks": dict(scorer_locks),
            "scorer_observation_sha256": scorer_observation_sha256,
        }
    )


@dataclass(frozen=True)
class ScoredHybridTask:
    """One runtime execution plus its exact final-output scorer observation."""

    execution: HybridExecution
    scoring_input: RuntimeScoringInput
    score: RuntimeTaskScore
    scorer_locks: Mapping[str, str]
    scorer_observation_sha256: str
    scorer_calls: int = 1
    evidence_boundary: str = ORCHESTRATION_BOUNDARY
    frozen_plan_bound: bool = False
    scorer_implementation_authenticated: bool = False
    claim_eligible: bool = False
    goal_total_complete: bool = False
    _construction_seal: object = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if type(self.execution) is not HybridExecution:
            raise VerificationError("scored task requires an exact HybridExecution")
        if type(self.scoring_input) is not RuntimeScoringInput:
            raise VerificationError("scored task requires an exact scoring input")
        if type(self.score) is not RuntimeTaskScore:
            raise VerificationError("scored task requires an exact scorer output")
        normalized_locks = _scorer_locks(
            dict(self.scorer_locks), "scored task scorer_locks"
        )
        object.__setattr__(
            self,
            "scorer_locks",
            MappingProxyType(normalized_locks),
        )
        expected_fingerprint = _scored_task_fingerprint(
            execution=self.execution,
            scoring_input=self.scoring_input,
            score=self.score,
            scorer_locks=normalized_locks,
            scorer_observation_sha256=self.scorer_observation_sha256,
        )
        if (
            not isinstance(self._construction_seal, _ScoredTaskSeal)
            or self._construction_seal.fingerprint != expected_fingerprint
        ):
            raise VerificationError(
                "scored task observations must be minted by the orchestrator"
            )
        expected_observation = sha256_ref(
            {
                "schema_version": SCORER_OBSERVATION_SCHEMA,
                "scorer_locks": normalized_locks,
                "scoring_input": self.scoring_input.value,
                "scorer_output": self.score.value,
            }
        )
        if self.scorer_observation_sha256 != expected_observation:
            raise VerificationError("scorer observation digest differs")
        if self.scorer_calls != 1:
            raise VerificationError("study runner must invoke the scorer exactly once")
        if self.evidence_boundary != ORCHESTRATION_BOUNDARY:
            raise VerificationError("study orchestration evidence boundary differs")
        if (
            self.frozen_plan_bound is not False
            or self.scorer_implementation_authenticated is not False
        ):
            raise VerificationError(
                "diagnostic orchestration cannot authenticate plan or scorer code"
            )
        if self.claim_eligible is not False or self.goal_total_complete is not False:
            raise VerificationError("provider-free orchestration cannot make a claim")
        if (
            self.scoring_input.execution_binding_sha256
            != self.execution.prepared.execution_binding_sha256
            or self.scoring_input.route_binding_sha256
            != self.execution.prepared.route.binding_sha256
            or self.scoring_input.primary_request_binding_sha256
            != self.execution.primary.request_binding_sha256
        ):
            raise VerificationError("scorer input is bound to another execution")
        expected_fallback = (
            None
            if self.execution.fallback is None
            else self.execution.fallback.request_binding_sha256
        )
        if self.scoring_input.fallback_request_binding_sha256 != expected_fallback:
            raise VerificationError("scorer input fallback binding differs")
        (
            expected_terminal_status,
            expected_output_text,
            expected_output_sha256,
            expected_terminal_observation_sha256,
        ) = _terminal_view(self.execution)
        expected_ledger = _ledger_value(self.execution)
        expected_ledger_sha256 = (
            None if expected_ledger is None else sha256_ref(expected_ledger)
        )
        if (
            self.scoring_input.source_sha256
            != self.execution.prepared.route.source_sha256
            or self.scoring_input.selected_mode
            != self.execution.prepared.route.selected_mode
            or self.scoring_input.final_mode != self.execution.final_mode
            or self.scoring_input.fallback_from != _fallback_from(self.execution)
            or self.scoring_input.terminal_status != expected_terminal_status
            or self.scoring_input.output_text != expected_output_text
            or self.scoring_input.output_sha256 != expected_output_sha256
            or self.scoring_input.terminal_observation_sha256
            != expected_terminal_observation_sha256
            or self.scoring_input.observed_ledger_sha256
            != expected_ledger_sha256
        ):
            raise VerificationError("scorer input terminal observation differs")
        if not self.scoring_input.parse_probe and self.score.parse_valid is not None:
            raise VerificationError(
                "observation is outside the caller-declared parse probe"
            )
        if (
            not self.scoring_input.semantic_probe
            and self.score.semantic_exact is not None
        ):
            raise VerificationError(
                "observation is outside the caller-declared semantic probe"
            )
        if (
            not self.scoring_input.negative_probe
            and self.score.negative_rejected is not None
        ):
            raise VerificationError(
                "observation is outside the caller-declared negative probe"
            )
        for feature in FEATURE_TAGS:
            if (
                feature not in self.scoring_input.feature_tags
                and self.score.preservation[feature] is not None
            ):
                raise VerificationError(
                    "observation is outside a caller-declared preservation feature"
                )

    @property
    def caller_reported_inclusive_total_tokens(self) -> int | None:
        runtime_total = self.execution.inclusive_total_tokens
        if runtime_total is None or self.score.total_tokens is None:
            return None
        return runtime_total + self.score.total_tokens

    @property
    def inclusive_total_tokens(self) -> None:
        """Claim-facing total stays unknown until scorer code/usage is authenticated."""

        return None

    @property
    def caller_reported_safely_completed(self) -> bool | None:
        runtime_safe = self.execution.safely_completed
        if runtime_safe is None:
            return None
        if runtime_safe is False:
            return False
        if self.score.task_success is None or any(
            value is None for value in self.score.safety.values()
        ):
            return None
        return bool(
            self.score.task_success
            and not any(value or 0 for value in self.score.safety.values())
        )

    @property
    def safely_completed(self) -> None:
        """Claim-facing completion stays unknown for an unauthenticated scorer."""

        return None

    def trace_artifacts(
        self,
        *,
        decision_event_sequence: int,
        receiver_event_sequence: int | None,
        judge_event_sequence: int,
        judge_local_event_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Derive task-result, scoring-binding, and unknown-cost judge fragments.

        Event-source projection remains the caller's separate responsibility;
        the returned objects cannot be used with another task or output without
        failing their content bindings.
        """

        if type(decision_event_sequence) is not int or decision_event_sequence < 0:
            raise VerificationError("decision event sequence is invalid")
        if receiver_event_sequence is not None and (
            type(receiver_event_sequence) is not int
            or receiver_event_sequence <= decision_event_sequence
        ):
            raise VerificationError("receiver event sequence is invalid")
        if (
            type(judge_event_sequence) is not int
            or judge_event_sequence <= decision_event_sequence
            or (
                receiver_event_sequence is not None
                and judge_event_sequence <= receiver_event_sequence
            )
        ):
            raise VerificationError("judge event sequence is invalid")
        if type(judge_local_event_id) is not str or not judge_local_event_id:
            raise VerificationError("judge local event ID is invalid")
        if self.score.scorer_kind != "deterministic-local":
            raise VerificationError(
                "external or failed scorer requires a captured judge event"
            )
        if (
            self.execution.fallback is not None
            and self.scoring_input.selected_mode != "action-state"
        ):
            raise VerificationError(
                "current frozen trace cannot represent this receiver fallback mode"
            )
        score = self.score
        task_result = {
            "task_id": self.scoring_input.task_id,
            "task_success": score.task_success,
            "parse_valid": score.parse_valid,
            "semantic_exact": score.semantic_exact,
            "negative_rejected": score.negative_rejected,
            "preservation": dict(score.preservation),
            "safety": dict(score.safety),
            "scorer_receipt_sha256": None,
            "route": {
                "selected_mode": self.scoring_input.selected_mode,
                "decision_event_sequence": decision_event_sequence,
                "receiver_event_sequence": receiver_event_sequence,
                "decode_before_model": False,
                "natural_language_expansion": False,
                "fallback_from": self.scoring_input.fallback_from,
            },
        }
        scoring_binding = {
            "task_id": self.scoring_input.task_id,
            "scored_output_event_sequence": receiver_event_sequence,
            "output_sha256": self.scoring_input.output_sha256,
            "terminal_status": self.scoring_input.terminal_status,
        }
        judge_event = {
            "sequence": judge_event_sequence,
            "phase": "judge",
            "task_id": self.scoring_input.task_id,
            "source": {
                "kind": "deterministic-local",
                "local_event_id": judge_local_event_id,
                "implementation_sha256": self.scorer_locks["task_scorer"],
                "input_sha256": self.scoring_input.sha256,
                "output_sha256": self.scorer_observation_sha256,
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "reasoning_tokens": None,
                    "unclassified_tokens": None,
                    "provider_total_tokens": None,
                    "total_tokens": None,
                    "hidden_accounting": "not-reported",
                },
            },
        }
        return (
            _detached(task_result),
            _detached(scoring_binding),
            _detached(judge_event),
        )


def run_scored_hybrid_task(
    *,
    task_id: str,
    task_sha256: str,
    source_text: str,
    task_input_messages: Sequence[Mapping[str, str]],
    feature_tags: tuple[str, ...],
    parse_probe: bool,
    semantic_probe: bool,
    negative_probe: bool,
    prepared: PreparedMessage,
    receiver_adapter: ReceiverModelAdapter,
    output_validator: Callable[[OutputValidationInput], LocalOutputValidation]
    | None,
    scorer: RuntimeTaskScorer,
    scorer_locks: Mapping[str, str],
    caller_expected_scorer_locks: Mapping[str, str],
    observed_local_usage: ObservedLocalUsage | None = None,
) -> ScoredHybridTask:
    """Execute one prepared hybrid task and score only its final output.

    Adapter and scorer implementations are injected so this function creates no
    provider, network, credential, or spending capability.  Both lock mappings
    are caller-supplied labels: equality does not hash or authenticate the scorer
    callable, and task/probe arguments are not bound to a complete frozen study
    plan.  Scorer exceptions and invalid scorer return types are preserved as an
    unknown, incomplete score rather than converted into success or zero cost.
    """

    if type(prepared) is not PreparedMessage:
        raise VerificationError("study runner requires an exact PreparedMessage")
    _require_sha256_ref(task_sha256, "study task_sha256")
    if type(source_text) is not str or not source_text:
        raise VerificationError("study source text must be non-empty")
    if source_text_sha256(source_text) != prepared.route.source_sha256:
        raise VerificationError("study source text differs from the prepared route")
    last_message = (
        None
        if type(task_input_messages) not in {list, tuple}
        or not task_input_messages
        else task_input_messages[-1]
    )
    if (
        type(last_message) is not dict
        or last_message.get("role") != "user"
        or last_message.get("content") != source_text
    ):
        raise VerificationError(
            "study task input must end with the exact natural-language source"
        )
    if task_input_sha256(task_input_messages) != task_sha256:
        raise VerificationError("study task input preimage digest differs")
    observed_locks = _scorer_locks(dict(scorer_locks), "study scorer_locks")
    expected_locks = _scorer_locks(
        dict(caller_expected_scorer_locks), "caller expected scorer_locks"
    )
    if observed_locks != expected_locks:
        raise VerificationError("declared scorer lock values differ")

    execution = execute_prepared_message(
        prepared,
        receiver_adapter,
        output_validator=output_validator,
        observed_local_usage=observed_local_usage,
    )
    (
        terminal_status,
        output_text,
        output_sha256,
        terminal_observation_sha256,
    ) = _terminal_view(execution)
    ledger_value = _ledger_value(execution)
    scoring_input = RuntimeScoringInput(
        task_id=task_id,
        task_sha256=task_sha256,
        source_sha256=prepared.route.source_sha256,
        feature_tags=feature_tags,
        parse_probe=parse_probe,
        semantic_probe=semantic_probe,
        negative_probe=negative_probe,
        arm_id="hybrid-router",
        selected_mode=execution.prepared.route.selected_mode,
        final_mode=execution.final_mode,
        fallback_from=_fallback_from(execution),
        terminal_status=terminal_status,
        output_text=output_text,
        output_sha256=output_sha256,
        terminal_observation_sha256=terminal_observation_sha256,
        execution_binding_sha256=execution.prepared.execution_binding_sha256,
        route_binding_sha256=execution.prepared.route.binding_sha256,
        primary_request_binding_sha256=execution.primary.request_binding_sha256,
        fallback_request_binding_sha256=(
            None
            if execution.fallback is None
            else execution.fallback.request_binding_sha256
        ),
        observed_ledger_sha256=(
            None if ledger_value is None else sha256_ref(ledger_value)
        ),
    )
    try:
        candidate = scorer(scoring_input)
    except Exception:
        candidate = RuntimeTaskScore.failed("scorer-call-failed")
    if type(candidate) is not RuntimeTaskScore:
        candidate = RuntimeTaskScore.failed("scorer-reply-type-invalid")
    observation_sha256 = sha256_ref(
        {
            "schema_version": SCORER_OBSERVATION_SCHEMA,
            "scorer_locks": observed_locks,
            "scoring_input": scoring_input.value,
            "scorer_output": candidate.value,
        }
    )
    seal = _ScoredTaskSeal(
        _scored_task_fingerprint(
            execution=execution,
            scoring_input=scoring_input,
            score=candidate,
            scorer_locks=observed_locks,
            scorer_observation_sha256=observation_sha256,
        )
    )
    return ScoredHybridTask(
        execution=execution,
        scoring_input=scoring_input,
        score=candidate,
        scorer_locks=observed_locks,
        scorer_observation_sha256=observation_sha256,
        _construction_seal=seal,
    )


__all__ = [
    "ORCHESTRATION_BOUNDARY",
    "RuntimeScoringInput",
    "RuntimeTaskScore",
    "RuntimeTaskScorer",
    "SCORER_OBSERVATION_SCHEMA",
    "SCORING_INPUT_SCHEMA",
    "SCORING_OUTPUT_SCHEMA",
    "ScoredHybridTask",
    "run_scored_hybrid_task",
]
