"""End-to-end preparation path up to, but not including, a receiver model call."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from types import MappingProxyType
from typing import Callable, Mapping

from .canonical import canonical_json, sha256_text, strict_json_loads
from .captured_receiver import CapturedReceiverExecution
from .errors import RoutingError
from .fidelity import FidelityVerification, FidelityVerificationInput
from .preparation_journal import (
    PreparationJournal,
    PreparationJournalRecorder,
)
from .records import Capsule
from .receiver import (
    _execute_receiver_request,
    DirectReceiverRequest,
    ReceiverExecution,
    ReceiverModelAdapter,
    execute_receiver,
)
from .router import (
    CostForecast,
    LocalArtifactVerification,
    ReceiverCapabilities,
    RouteDecision,
    RouterPolicy,
    RoutineInvocation,
    SilenceProof,
    UtilityEvidence,
    plan_route,
    should_attempt_action_state,
)
from .sender import (
    CapsuleContextBinding,
    CompileOutcome,
    SenderContextVerification,
    StructuredCompiler,
    compile_natural_language,
)
from .task_context import PublicTaskContext
from .surface import ActiveSurface, RetainedSurface, SurfaceAliasTable


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
OBSERVED_TOKEN_PHASES = (
    "setup",
    "sender",
    "semantic-verification",
    "router",
    "receiver",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
)
_OBSERVED_COMPONENT_PHASE = {
    "local-setup": "setup",
    "cold-comprehension": "setup",
    "sender-compiler": "sender",
    "semantic-fidelity-verifier": "semantic-verification",
    "local-router": "router",
    "primary-receiver": "receiver",
    "local-repair": "repair",
    "local-fallback": "fallback",
    "baseline-fallback-receiver": "fallback",
    "local-tool": "tool",
    "local-safety": "safety",
    "local-judge": "judge",
}
_DETAILED_MODEL_COMPONENTS = {
    "cold-comprehension",
    "primary-receiver",
    "baseline-fallback-receiver",
}
_TOTAL_ONLY_MODEL_COMPONENTS = {
    "sender-compiler",
    "semantic-fidelity-verifier",
}
_LOCAL_SETUP_SCOPE = "runtime-local-exclusive-of-cold-comprehension"


def _clone_exact_artifact(value, expected_type, label: str):
    """Clone a trusted exact dataclass without walking arbitrary properties."""

    if value is None:
        return None
    if type(value) is not expected_type:
        raise RoutingError(f"routing snapshot {label} must use its exact type")
    try:
        if expected_type is RoutineInvocation:
            # Routine payload is the one typed artifact with a deliberately
            # JSON-shaped mutable interior.  Canonical round-trip both validates
            # it without invoking user-defined copy hooks and deeply detaches it.
            payload = strict_json_loads(
                canonical_json(object.__getattribute__(value, "payload"))
            )
            return replace(value, payload=payload)
        return replace(value)
    except Exception as exc:
        raise RoutingError(f"routing snapshot could not clone {label}") from exc


def _snapshot_typed_mapping(
    value: Mapping[str, object] | None,
    expected_value_type,
    label: str,
    *,
    optional: bool = False,
) -> tuple[tuple[str, object], ...]:
    """Capture an exact built-in mapping without trusting custom accessors."""

    if value is None:
        if optional:
            return ()
        raise RoutingError(f"routing snapshot {label} cannot be null")
    if type(value) is not dict:
        raise RoutingError(f"routing snapshot {label} must be an exact dict")
    try:
        items = tuple(value.items())
    except Exception as exc:
        raise RoutingError(f"routing snapshot could not read {label}") from exc
    if any(type(key) is not str for key, _ in items):
        raise RoutingError(f"routing snapshot {label} keys must be strings")
    if len({key for key, _ in items}) != len(items):
        raise RoutingError(f"routing snapshot {label} contains duplicate keys")
    if any(type(item) is not expected_value_type for _, item in items):
        raise RoutingError(
            f"routing snapshot {label} values must use their exact type"
        )
    return tuple(
        sorted(
            (
                key,
                _clone_exact_artifact(item, expected_value_type, f"{label}[{key!r}]"),
            )
            for key, item in items
        )
    )


@dataclass(frozen=True)
class _RoutingInputSnapshot:
    """Callback-isolated source of every mutable routing pass input.

    The master values are captured before any verifier, counter, or compiler is
    invoked.  Each pass receives a fresh typed clone, so a callback can mutate
    neither caller-owned mappings nor a prior pass view to alter a later route.
    """

    forecast_items: tuple[tuple[str, object], ...]
    evidence_items: tuple[tuple[str, object], ...]
    routine: RoutineInvocation | None

    @classmethod
    def capture(
        cls,
        *,
        forecasts: Mapping[str, CostForecast],
        evidence: Mapping[str, UtilityEvidence] | None,
        routine: RoutineInvocation | None,
    ) -> "_RoutingInputSnapshot":
        return cls(
            forecast_items=_snapshot_typed_mapping(
                forecasts, CostForecast, "forecasts"
            ),
            evidence_items=_snapshot_typed_mapping(
                evidence, UtilityEvidence, "evidence", optional=True
            ),
            routine=_clone_exact_artifact(routine, RoutineInvocation, "routine"),
        )

    def materialize(
        self,
    ) -> tuple[
        Mapping[str, CostForecast],
        Mapping[str, UtilityEvidence],
        RoutineInvocation | None,
    ]:
        forecasts = MappingProxyType(
            {
                key: _clone_exact_artifact(
                    value, CostForecast, f"forecasts[{key!r}]"
                )
                for key, value in self.forecast_items
            }
        )
        evidence = MappingProxyType(
            {
                key: _clone_exact_artifact(
                    value, UtilityEvidence, f"evidence[{key!r}]"
                )
                for key, value in self.evidence_items
            }
        )
        return (
            forecasts,
            evidence,
            _clone_exact_artifact(
                self.routine, RoutineInvocation, "routine"
            ),
        )


@dataclass(frozen=True)
class OutputValidationInput:
    source_sha256: str
    task_context_sha256: str
    task_profile_sha256: str
    route_mode: str
    payload_sha256: str
    output_text: str
    output_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "source_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "payload_sha256",
            "output_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"output validation {name} is invalid")
        if self.route_mode not in {"routine", "action-state", "raw", "json"}:
            raise ValueError("output validation route mode is invalid")
        if type(self.output_text) is not str:
            raise ValueError("output validation text must be a string")
        if sha256_text(self.output_text) != self.output_sha256:
            raise ValueError("output validation text digest mismatch")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "source_sha256": self.source_sha256,
                    "task_context_sha256": self.task_context_sha256,
                    "task_profile_sha256": self.task_profile_sha256,
                    "route_mode": self.route_mode,
                    "payload_sha256": self.payload_sha256,
                    "output_sha256": self.output_sha256,
                }
            )
        )


@dataclass(frozen=True)
class LocalOutputValidation:
    valid: bool
    input_binding_sha256: str
    validator_sha256: str
    deterministic_local: bool = True
    model_calls: int = 0
    total_tokens: int = 0
    tools_used: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise ValueError("local output validation must return a boolean")
        if _SHA256.fullmatch(self.input_binding_sha256) is None:
            raise ValueError("local output validation input binding is invalid")
        if _SHA256.fullmatch(self.validator_sha256) is None:
            raise ValueError("local output validator digest is invalid")
        if self.deterministic_local is not True:
            raise ValueError("output validator must be deterministic and local")
        if type(self.model_calls) is not int or self.model_calls != 0:
            raise ValueError("output validator cannot call a model")
        if type(self.total_tokens) is not int or self.total_tokens != 0:
            raise ValueError("output validator cannot consume model tokens")
        if type(self.tools_used) is not bool or self.tools_used:
            raise ValueError("output validator cannot use tools")
        if (
            type(self.external_effects_performed) is not bool
            or self.external_effects_performed
        ):
            raise ValueError("output validator cannot perform external effects")


@dataclass(frozen=True)
class ObservedTokenEvent:
    """One immutable, exact-bound runtime usage observation.

    ``total_tokens`` is the non-overlapping amount contributed to the inclusive
    total.  Provider input/output/reasoning fields are annotations within that
    total and are never added a second time.  Receiver and cold-comprehension
    events retain detailed provider counts; compiler and fidelity interfaces
    expose total-only usage.  ``None`` remains unknown.
    """

    sequence: int
    phase: str
    component: str
    execution_binding_sha256: str
    artifact_binding_sha256: str
    total_tokens: int | None
    model_calls: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    reasoning_accounting: str | None = None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("observed token event sequence must be nonnegative")
        if self.phase not in OBSERVED_TOKEN_PHASES:
            raise ValueError("observed token event phase is unknown")
        if _OBSERVED_COMPONENT_PHASE.get(self.component) != self.phase:
            raise ValueError("observed token event component and phase differ")
        for name in ("execution_binding_sha256", "artifact_binding_sha256"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"observed token event {name} is invalid")
        for name in (
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"observed token event {name} is invalid")
        if type(self.model_calls) is not int or self.model_calls not in {0, 1}:
            raise ValueError("observed token event model_calls must be zero or one")
        if self.reasoning_accounting not in {
            None,
            "included-in-output",
            "separately-reported",
            "not-reported",
        }:
            raise ValueError("observed token event reasoning accounting is unknown")
        if self.model_calls == 0 and any(
            value is not None
            for value in (
                self.input_tokens,
                self.output_tokens,
                self.reasoning_tokens,
                self.reasoning_accounting,
            )
        ):
            raise ValueError("non-model event cannot report model usage fields")
        if (
            self.model_calls == 1
            and self.component in _DETAILED_MODEL_COMPONENTS
            and self.total_tokens is not None
            and (
                self.input_tokens is None
                or self.output_tokens is None
                or self.reasoning_accounting is None
            )
        ):
            raise ValueError(
                "completed receiver-like event requires detailed model usage"
            )
        if (
            self.component in _TOTAL_ONLY_MODEL_COMPONENTS
            and any(
                value is not None
                for value in (
                    self.input_tokens,
                    self.output_tokens,
                    self.reasoning_tokens,
                    self.reasoning_accounting,
                )
            )
        ):
            raise ValueError("total-only model event cannot report detailed usage")
        if self.reasoning_accounting is None and self.reasoning_tokens is not None:
            raise ValueError("reasoning tokens require an accounting disposition")
        if (
            self.reasoning_accounting == "not-reported"
            and self.reasoning_tokens is not None
        ):
            raise ValueError("unreported reasoning tokens must remain unknown")
        if (
            self.reasoning_accounting
            in {"included-in-output", "separately-reported"}
            and self.reasoning_tokens is None
        ):
            raise ValueError("reported reasoning accounting requires a token count")
        known_subtotal = sum(
            value
            for value in (
                self.input_tokens,
                self.output_tokens,
                (
                    self.reasoning_tokens
                    if self.reasoning_accounting == "separately-reported"
                    else None
                ),
            )
            if value is not None
        )
        if self.total_tokens is not None and self.total_tokens < known_subtotal:
            raise ValueError("observed event total is below its known token subtotal")
        if self.model_calls == 0 and self.component in {
            "sender-compiler",
            "primary-receiver",
            "baseline-fallback-receiver",
            "cold-comprehension",
        } and self.total_tokens not in {0, None}:
            raise ValueError("uncalled model component cannot report positive tokens")

    @property
    def usage_complete(self) -> bool:
        return self.total_tokens is not None


@dataclass(frozen=True)
class ObservedExecutionLedger:
    """Runtime-scoped observations, never claim or provenance evidence.

    Scope completeness means only that every runtime category below has an
    explicit nonnegative observation.  It does not authenticate provider usage,
    prove the frozen research scope, or make a performance claim eligible.
    """

    execution_binding_sha256: str
    events: tuple[ObservedTokenEvent, ...]
    provider_authenticity_verified: bool = False
    claim_eligible: bool = False
    goal_total_complete: bool = False

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.execution_binding_sha256) is None:
            raise ValueError("observed ledger execution binding is invalid")
        if type(self.events) is not tuple or not self.events:
            raise ValueError("observed ledger events must be a non-empty tuple")
        if tuple(item.sequence for item in self.events) != tuple(
            range(len(self.events))
        ):
            raise ValueError("observed ledger events must be contiguously ordered")
        if any(
            type(item) is not ObservedTokenEvent
            or item.execution_binding_sha256 != self.execution_binding_sha256
            for item in self.events
        ):
            raise ValueError("observed ledger contains an unbound event")
        if len({item.component for item in self.events}) != len(self.events):
            raise ValueError("observed ledger contains duplicate components")
        if set(item.phase for item in self.events) != set(OBSERVED_TOKEN_PHASES):
            raise ValueError("observed ledger phase coverage is incomplete")
        for name in (
            "provider_authenticity_verified",
            "claim_eligible",
            "goal_total_complete",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"observed ledger {name} must be boolean")
        if any(
            (
                self.provider_authenticity_verified,
                self.claim_eligible,
                self.goal_total_complete,
            )
        ):
            raise ValueError(
                "runtime observations cannot establish authenticity or claim eligibility"
            )

    @property
    def scope_complete(self) -> bool:
        return all(item.usage_complete for item in self.events)

    @property
    def inclusive_total_tokens(self) -> int | None:
        if not self.scope_complete:
            return None
        return sum(item.total_tokens or 0 for item in self.events)

    @property
    def observed_model_total_tokens(self) -> int | None:
        called = tuple(item for item in self.events if item.model_calls == 1)
        if any(not item.usage_complete for item in called):
            return None
        return sum(item.total_tokens or 0 for item in called)

    def phase_total(self, phase: str) -> int | None:
        if phase not in OBSERVED_TOKEN_PHASES:
            raise ValueError("observed ledger phase is unknown")
        matching = tuple(item for item in self.events if item.phase == phase)
        if any(not item.usage_complete for item in matching):
            return None
        return sum(item.total_tokens or 0 for item in matching)


@dataclass(frozen=True)
class PreparedMessage:
    route: RouteDecision
    compilation: CompileOutcome | None
    fidelity_verification: FidelityVerification | None = None
    receiver_model_calls_made: int = 0
    external_effects_performed: bool = False
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    preparation_journal: PreparationJournal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.route, RouteDecision):
            raise ValueError("prepared route must be a sealed RouteDecision")
        if self.receiver_model_calls_made != 0:
            raise ValueError("prepare_message must stop before the receiver model call")
        if any(
            (
                self.external_effects_performed,
                self.persistence_created,
                self.permission_expanded,
                self.spending_authority_created,
            )
        ):
            raise ValueError("message preparation cannot create authority or effects")
        if self.preparation_journal is not None:
            if type(self.preparation_journal) is not PreparationJournal:
                raise ValueError("prepared message journal type is invalid")
            self.preparation_journal.assert_matches(
                route=self.route,
                compilation=self.compilation,
                fidelity_verification=self.fidelity_verification,
            )
        if self.compilation is None:
            if self.fidelity_verification is not None:
                raise ValueError("fidelity verification requires a compilation")
            if self.route.selected_mode == "action-state" or self.route.fallback_from is not None:
                raise ValueError("prepared route lost its action-state compilation")
        else:
            request = self.route.request
            if (
                self.compilation.source_sha256 != self.route.source_sha256
                or self.compilation.capsule_sha256 != self.route.capsule_sha256
                or
                self.compilation.task_context_sha256
                != request.task_context_sha256
                or self.compilation.task_profile_sha256
                != request.task_profile_sha256
                or self.compilation.symbol_table_sha256
                != request.symbol_table_sha256
            ):
                raise ValueError("compilation and route task bindings differ")
            if (
                self.route.selected_mode == "action-state"
                and self.fidelity_verification is not None
            ):
                if self.compilation.compiled is None:
                    raise ValueError("fidelity verification requires compiled state")
                fidelity_input = FidelityVerificationInput(
                    source_text=next(
                        item.request.payload_text
                        for item in self.route.candidates
                        if item.mode == "raw" and item.request is not None
                    ),
                    source_sha256=self.route.source_sha256,
                    state=self.compilation.compiled,
                    task_context=PublicTaskContext.from_json(request.task_context_text),
                    maximum_total_tokens=(
                        self.route.fidelity_verifier_token_ceiling
                        if self.route.fidelity_verifier_token_ceiling is not None
                        else 0
                    ),
                )
                if (
                    self.fidelity_verification.input_binding_sha256
                    != fidelity_input.binding_sha256
                ):
                    raise ValueError("fidelity verification and compilation differ")
            if self.route.selected_mode == "action-state" and self.compilation.status != "ok":
                raise ValueError("action-state route requires one valid compilation")
            if self.route.selected_mode == "action-state":
                expected_state_sha256 = (
                    request.surface_carrier.state_sha256
                    if request.surface_carrier is not None
                    else request.payload_sha256
                )
                if (
                    self.compilation.compiled is None
                    or self.compilation.compiled.sha256 != expected_state_sha256
                    or request.capsule_sha256 != self.compilation.capsule_sha256
                ):
                    raise ValueError("compilation and action request payload differ")
                if self.fidelity_verification is None:
                    raise ValueError("action-state route lost its fidelity proof")
                if (
                    not self.fidelity_verification.passed
                    or self.compilation.total_tokens
                    != self.route.selected_cost.sender_tokens
                    or self.fidelity_verification.total_tokens
                    != self.route.selected_cost.semantic_verification_tokens
                ):
                    raise ValueError("prepared action evidence or token accounting differs")
            elif self.route.fallback_from is not None:
                if self.route.fallback_from != f"action-state:{self.compilation.status}":
                    raise ValueError("fallback status and compilation differ")
                if self.route.fallback_sender_tokens != self.compilation.total_tokens:
                    raise ValueError("fallback compiler token accounting differs")
                expected_fidelity_tokens = (
                    self.fidelity_verification.total_tokens
                    if self.fidelity_verification is not None
                    else 0
                )
                if (
                    self.route.fallback_semantic_verification_tokens
                    != expected_fidelity_tokens
                ):
                    raise ValueError("fallback fidelity token accounting differs")

    @property
    def execution_binding_sha256(self) -> str:
        request = self.route.request
        compilation = self.compilation
        fidelity = self.fidelity_verification
        return sha256_text(
            canonical_json(
                {
                    "source_sha256": self.route.source_sha256,
                    "capsule_sha256": self.route.capsule_sha256,
                    "task_context_sha256": request.task_context_sha256,
                    "task_profile_sha256": request.task_profile_sha256,
                    "symbol_table_sha256": request.symbol_table_sha256,
                    "selected_mode": self.route.selected_mode,
                    "request_binding_sha256": request.binding_sha256,
                    "route_binding_sha256": self.route.binding_sha256,
                    "preparation_journal_sha256": (
                        self.preparation_journal.sha256
                        if self.preparation_journal is not None
                        else None
                    ),
                    "compilation": (
                        None
                        if compilation is None
                        else {
                            "status": compilation.status,
                            "model_id": compilation.model_id,
                            "total_tokens": compilation.total_tokens,
                            "output_sha256": compilation.output_sha256,
                        }
                    ),
                    "fidelity_verification": (
                        None
                        if fidelity is None
                        else {
                            "input_binding_sha256": fidelity.input_binding_sha256,
                            "verifier_sha256": fidelity.verifier_sha256,
                            "method": fidelity.method,
                            "model_id": fidelity.model_id,
                            "total_tokens": fidelity.total_tokens,
                        }
                    ),
                }
            )
        )


@dataclass(frozen=True)
class ObservedLocalUsage:
    """Exact-preparation-bound non-model usage; ``None`` means unobserved.

    ``setup_tokens`` is exclusively runtime-local setup and must exclude the
    separately merged cold-comprehension provider call.  That exclusion is an
    honest-host accounting assertion, not structural proof or claim evidence.
    """

    execution_binding_sha256: str
    setup_tokens: int | None = None
    router_tokens: int | None = None
    repair_tokens: int | None = None
    fallback_tokens: int | None = None
    tool_tokens: int | None = None
    safety_tokens: int | None = None
    judge_tokens: int | None = None
    setup_scope: str = _LOCAL_SETUP_SCOPE

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.execution_binding_sha256) is None:
            raise ValueError("observed local usage binding is invalid")
        if self.setup_scope != _LOCAL_SETUP_SCOPE:
            raise ValueError(
                "observed local setup must exclude cold comprehension"
            )
        for name in (
            "setup_tokens",
            "router_tokens",
            "repair_tokens",
            "fallback_tokens",
            "tool_tokens",
            "safety_tokens",
            "judge_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"observed local usage {name} is invalid")

    @classmethod
    def for_prepared(
        cls,
        prepared: PreparedMessage,
        **usage: int | None,
    ) -> "ObservedLocalUsage":
        if type(prepared) is not PreparedMessage:
            raise ValueError("observed local usage requires an exact preparation")
        return cls(
            execution_binding_sha256=prepared.execution_binding_sha256,
            **usage,
        )


def merge_observed_setup_event(
    ledger: ObservedExecutionLedger,
    *,
    component: str,
    artifact_binding_sha256: str,
    total_tokens: int | None,
    model_calls: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    reasoning_accounting: str | None = None,
) -> ObservedExecutionLedger:
    """Prepend one exact setup event, rejecting replay or cross-run binding."""

    if type(ledger) is not ObservedExecutionLedger:
        raise ValueError("setup merge requires an exact observed ledger")
    if component != "cold-comprehension":
        raise ValueError("only cold comprehension may be merged as setup")
    if any(item.component == component for item in ledger.events):
        raise ValueError("observed setup event was already merged")
    if any(
        item.phase == "setup"
        and item.artifact_binding_sha256 == artifact_binding_sha256
        for item in ledger.events
    ):
        raise ValueError("observed setup artifact was already accounted")
    setup = ObservedTokenEvent(
        sequence=0,
        phase="setup",
        component=component,
        execution_binding_sha256=ledger.execution_binding_sha256,
        artifact_binding_sha256=artifact_binding_sha256,
        total_tokens=total_tokens,
        model_calls=model_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        reasoning_accounting=reasoning_accounting,
    )
    events = (setup,) + tuple(
        replace(item, sequence=index)
        for index, item in enumerate(ledger.events, start=1)
    )
    return ObservedExecutionLedger(
        execution_binding_sha256=ledger.execution_binding_sha256,
        events=events,
    )


_HYBRID_OBSERVATION_FINGERPRINT_FIELDS = (
    "prepared",
    "primary",
    "fallback",
    "observed_local_usage",
    "observed_ledger",
)


class _HybridObservationSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _hybrid_observation_fingerprint(values: Mapping[str, object]) -> str:
    return sha256_text(
        repr(
            tuple(
                (name, values[name])
                for name in _HYBRID_OBSERVATION_FINGERPRINT_FIELDS
            )
        )
    )


@dataclass(frozen=True)
class HybridExecution:
    prepared: PreparedMessage
    primary: ReceiverExecution
    fallback: ReceiverExecution | None
    final_mode: str
    compiler_calls: int
    fidelity_verifier_calls: int
    receiver_calls: int
    output_valid: bool | None
    safely_completed: bool | None
    observed_runtime_tokens: int | None
    goal_total_complete: bool = False
    observed_ledger: ObservedExecutionLedger | None = None
    claim_eligible: bool = False
    observed_local_usage: ObservedLocalUsage | None = None
    _construction_seal: object = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.compiler_calls not in {0, 1}:
            raise ValueError("hybrid compiler calls must be zero or one")
        if self.fidelity_verifier_calls not in {0, 1}:
            raise ValueError("hybrid fidelity verifier calls must be zero or one")
        expected_receiver_calls = self.primary.calls + (
            self.fallback.calls if self.fallback is not None else 0
        )
        if self.receiver_calls != expected_receiver_calls:
            raise ValueError("hybrid receiver call count does not reconcile")
        primary_request = self.prepared.route.request
        if (
            self.primary.request_mode != self.prepared.route.selected_mode
            or self.primary.request_binding_sha256
            != primary_request.binding_sha256
            or self.primary.delivery_disposition != "live"
        ):
            raise ValueError(
                "hybrid primary execution is not bound to its live request"
            )
        if self.final_mode not in {"silence", "routine", "action-state", "raw", "json"}:
            raise ValueError("hybrid final mode is unknown")
        if self.fallback is None:
            if self.final_mode != self.prepared.route.selected_mode:
                raise ValueError("hybrid final mode lost its primary route")
        else:
            baseline = next(
                (
                    item
                    for item in self.prepared.route.candidates
                    if item.mode == self.prepared.route.best_baseline_mode
                ),
                None,
            )
            if (
                self.prepared.route.selected_mode
                not in {"routine", "action-state"}
                or baseline is None
                or baseline.request is None
                or self.fallback.request_mode not in {"raw", "json"}
                or self.fallback.request_mode != baseline.mode
                or self.fallback.request_binding_sha256
                != baseline.request.binding_sha256
                or self.fallback.delivery_disposition != "live"
                or self.final_mode != baseline.mode
            ):
                raise ValueError(
                    "hybrid fallback is not bound to its live baseline request"
                )
        for name in ("claim_eligible", "goal_total_complete"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"hybrid {name} must be boolean")
        if self.claim_eligible or self.goal_total_complete:
            raise ValueError(
                "runtime-only trace cannot claim eligibility or complete goal accounting"
            )
        if self.observed_ledger is None:
            if (
                self.observed_local_usage is not None
                or self._construction_seal is not None
            ):
                raise ValueError(
                    "ledger-free legacy execution cannot contain observations"
                )
        else:
            if (
                type(self.observed_ledger) is not ObservedExecutionLedger
                or type(self.observed_local_usage) is not ObservedLocalUsage
                or self.observed_local_usage.execution_binding_sha256
                != self.prepared.execution_binding_sha256
            ):
                raise ValueError("hybrid observed ledger and execution differ")
            observation_values = {
                name: getattr(self, name)
                for name in _HYBRID_OBSERVATION_FINGERPRINT_FIELDS
            }
            if (
                not isinstance(self._construction_seal, _HybridObservationSeal)
                or self._construction_seal.fingerprint
                != _hybrid_observation_fingerprint(observation_values)
            ):
                raise ValueError(
                    "HybridExecution observations must be minted by the executor"
                )
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
                raise ValueError("hybrid observed ledger and execution differ")

    @property
    def scope_complete(self) -> bool:
        return bool(
            self.observed_ledger is not None
            and self.observed_ledger.scope_complete
        )

    @property
    def inclusive_total_tokens(self) -> int | None:
        if self.observed_ledger is None:
            return None
        return self.observed_ledger.inclusive_total_tokens


def _validate_public_output(
    execution: ReceiverExecution | CapturedReceiverExecution,
    request: DirectReceiverRequest,
    source_sha256: str,
    validator: Callable[[OutputValidationInput], LocalOutputValidation] | None,
    expected_validator_sha256: str | None,
) -> bool | None:
    if execution.status == "silenced":
        return True
    if execution.status != "completed" or execution.reply is None:
        return False
    if validator is None:
        return False if request.mode in {"routine", "action-state"} else None
    validation_input = OutputValidationInput(
        source_sha256=source_sha256,
        task_context_sha256=request.task_context_sha256,
        task_profile_sha256=request.task_profile_sha256,
        route_mode=request.mode,
        payload_sha256=request.payload_sha256,
        output_text=execution.reply.text,
        output_sha256=sha256_text(execution.reply.text),
    )
    try:
        result = validator(validation_input)
    except Exception:
        return False
    if (
        not isinstance(result, LocalOutputValidation)
        or result.input_binding_sha256 != validation_input.binding_sha256
        or expected_validator_sha256 is None
        or result.validator_sha256 != expected_validator_sha256
    ):
        return False
    return result.valid


def _compiler_artifact_binding(prepared: PreparedMessage) -> str:
    compilation = prepared.compilation
    if compilation is None:
        return prepared.execution_binding_sha256
    return sha256_text(
        canonical_json(
            {
                "source_sha256": compilation.source_sha256,
                "capsule_sha256": compilation.capsule_sha256,
                "task_context_sha256": compilation.task_context_sha256,
                "task_profile_sha256": compilation.task_profile_sha256,
                "symbol_table_sha256": compilation.symbol_table_sha256,
                "output_sha256": compilation.output_sha256,
            }
        )
    )


def _receiver_execution_artifact_binding(
    execution: ReceiverExecution | CapturedReceiverExecution,
) -> str:
    if type(execution) is CapturedReceiverExecution:
        return execution.binding_sha256
    if type(execution) is not ReceiverExecution:
        raise ValueError("receiver observation requires an exact execution")
    reply = execution.reply
    return sha256_text(
        canonical_json(
            {
                "status": execution.status,
                "calls": execution.calls,
                "request_mode": execution.request_mode,
                "request_binding_sha256": execution.request_binding_sha256,
                "delivery_disposition": execution.delivery_disposition,
                "model_visible_sha256": execution.model_visible_sha256,
                "failure": execution.failure,
                "usage_complete": execution.usage_complete,
                "reply": (
                    None
                    if reply is None
                    else {
                        "output_sha256": sha256_text(reply.text),
                        "model_id": reply.model_id,
                        "input_tokens": reply.input_tokens,
                        "output_tokens": reply.output_tokens,
                        "reasoning_tokens": reply.reasoning_tokens,
                        "reasoning_accounting": reply.reasoning_accounting,
                        "provider_total_tokens": reply.provider_total_tokens,
                        "tools_used": reply.tools_used,
                        "persistence_created": reply.persistence_created,
                        "permission_expanded": reply.permission_expanded,
                        "spending_authority_created": (
                            reply.spending_authority_created
                        ),
                        "external_effects_performed": (
                            reply.external_effects_performed
                        ),
                    }
                ),
            }
        )
    )


def _local_observation_artifact_binding(
    local_usage: ObservedLocalUsage,
    component: str,
) -> str:
    value: dict[str, str] = {
        "component": component,
        "execution_binding_sha256": local_usage.execution_binding_sha256,
    }
    if component == "local-setup":
        value["setup_scope"] = local_usage.setup_scope
    return sha256_text(canonical_json(value))


def _receiver_observed_event(
    execution_binding_sha256: str,
    execution: ReceiverExecution | CapturedReceiverExecution | None,
    *,
    sequence: int,
    component: str,
    phase: str,
) -> ObservedTokenEvent:
    if execution is None:
        return ObservedTokenEvent(
            sequence=sequence,
            phase=phase,
            component=component,
            execution_binding_sha256=execution_binding_sha256,
            artifact_binding_sha256=execution_binding_sha256,
            total_tokens=0,
            model_calls=0,
        )
    reply = execution.reply
    capture = (
        execution.capture
        if type(execution) is CapturedReceiverExecution
        else None
    )
    return ObservedTokenEvent(
        sequence=sequence,
        phase=phase,
        component=component,
        execution_binding_sha256=execution_binding_sha256,
        artifact_binding_sha256=_receiver_execution_artifact_binding(execution),
        total_tokens=execution.total_tokens,
        model_calls=execution.calls,
        input_tokens=(
            capture.input_tokens
            if capture is not None
            else (reply.input_tokens if reply is not None else None)
        ),
        output_tokens=(
            capture.output_tokens
            if capture is not None
            else (reply.output_tokens if reply is not None else None)
        ),
        reasoning_tokens=(
            capture.reasoning_tokens
            if capture is not None
            else (reply.reasoning_tokens if reply is not None else None)
        ),
        reasoning_accounting=(
            capture.reasoning_accounting
            if capture is not None
            else (reply.reasoning_accounting if reply is not None else None)
        ),
    )


def _build_observed_execution_ledger(
    prepared: PreparedMessage,
    primary: ReceiverExecution | CapturedReceiverExecution | None,
    fallback: ReceiverExecution | CapturedReceiverExecution | None,
    local_usage: ObservedLocalUsage,
) -> ObservedExecutionLedger:
    binding = prepared.execution_binding_sha256
    if local_usage.execution_binding_sha256 != binding:
        raise ValueError("observed local usage is bound to another preparation")
    for name in ("repair_tokens", "tool_tokens"):
        if getattr(local_usage, name) not in {None, 0}:
            raise ValueError(
                f"observed {name} cannot be positive without an executed phase"
            )
    if fallback is None and local_usage.fallback_tokens not in {None, 0}:
        raise ValueError(
            "observed fallback_tokens cannot be positive without a fallback"
        )
    compilation = prepared.compilation
    compiler_calls = int(compilation is not None and compilation.attempted)
    fidelity = prepared.fidelity_verification
    events = (
        ObservedTokenEvent(
            sequence=0,
            phase="setup",
            component="local-setup",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-setup",
            ),
            total_tokens=local_usage.setup_tokens,
            model_calls=0,
        ),
        ObservedTokenEvent(
            sequence=1,
            phase="sender",
            component="sender-compiler",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_compiler_artifact_binding(prepared),
            total_tokens=(
                compilation.total_tokens if compiler_calls else 0
            ),
            model_calls=compiler_calls,
        ),
        ObservedTokenEvent(
            sequence=2,
            phase="semantic-verification",
            component="semantic-fidelity-verifier",
            execution_binding_sha256=binding,
            artifact_binding_sha256=(
                fidelity.input_binding_sha256 if fidelity is not None else binding
            ),
            total_tokens=fidelity.total_tokens if fidelity is not None else 0,
            model_calls=fidelity.model_calls if fidelity is not None else 0,
        ),
        ObservedTokenEvent(
            sequence=3,
            phase="router",
            component="local-router",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-router",
            ),
            total_tokens=local_usage.router_tokens,
            model_calls=0,
        ),
        _receiver_observed_event(
            binding,
            primary,
            sequence=4,
            component="primary-receiver",
            phase="receiver",
        ),
        ObservedTokenEvent(
            sequence=5,
            phase="repair",
            component="local-repair",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-repair",
            ),
            total_tokens=local_usage.repair_tokens,
            model_calls=0,
        ),
        ObservedTokenEvent(
            sequence=6,
            phase="fallback",
            component="local-fallback",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-fallback",
            ),
            total_tokens=local_usage.fallback_tokens,
            model_calls=0,
        ),
        _receiver_observed_event(
            binding,
            fallback,
            sequence=7,
            component="baseline-fallback-receiver",
            phase="fallback",
        ),
        ObservedTokenEvent(
            sequence=8,
            phase="tool",
            component="local-tool",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-tool",
            ),
            total_tokens=local_usage.tool_tokens,
            model_calls=0,
        ),
        ObservedTokenEvent(
            sequence=9,
            phase="safety",
            component="local-safety",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-safety",
            ),
            total_tokens=local_usage.safety_tokens,
            model_calls=0,
        ),
        ObservedTokenEvent(
            sequence=10,
            phase="judge",
            component="local-judge",
            execution_binding_sha256=binding,
            artifact_binding_sha256=_local_observation_artifact_binding(
                local_usage,
                "local-judge",
            ),
            total_tokens=local_usage.judge_tokens,
            model_calls=0,
        ),
    )
    return ObservedExecutionLedger(
        execution_binding_sha256=binding,
        events=events,
    )


def execute_prepared_message(
    prepared: PreparedMessage,
    adapter: ReceiverModelAdapter,
    *,
    output_validator: Callable[
        [OutputValidationInput], LocalOutputValidation
    ]
    | None,
    observed_local_usage: ObservedLocalUsage | None = None,
) -> HybridExecution:
    """Execute a prepared route and one lossless baseline fallback when needed.

    Exact-bound local observations may complete the runtime-scoped inclusive
    ledger.  They still cannot authenticate provider usage or satisfy the frozen
    research gate, so claim and goal-completion flags remain false.
    """

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

    expected_output_validator_sha256 = PublicTaskContext.from_json(
        prepared.route.request.task_context_text
    ).output_validator_sha256
    primary_request = prepared.route.request
    primary = (
        _execute_receiver_request(primary_request, adapter)
        if primary_request.surface_carrier is not None
        else execute_receiver(primary_request, adapter)
    )
    primary_valid = _validate_public_output(
        primary,
        prepared.route.request,
        prepared.route.source_sha256,
        output_validator,
        expected_output_validator_sha256,
    )
    fallback: ReceiverExecution | None = None
    final_mode = prepared.route.selected_mode
    final_valid = primary_valid
    if (
        prepared.route.selected_mode in {"routine", "action-state"}
        and primary_valid is not True
    ):
        baseline = next(
            (
                item
                for item in prepared.route.candidates
                if item.mode == prepared.route.best_baseline_mode
            ),
            None,
        )
        if baseline is None or baseline.request is None:
            raise ValueError("prepared route lost its mandatory baseline fallback")
        fallback = execute_receiver(baseline.request, adapter)
        final_mode = baseline.mode
        final_valid = _validate_public_output(
            fallback,
            baseline.request,
            prepared.route.source_sha256,
            output_validator,
            expected_output_validator_sha256,
        )

    compiler_calls = int(
        prepared.compilation is not None and prepared.compilation.attempted
    )
    receiver_calls = primary.calls + (fallback.calls if fallback else 0)
    usage_values: list[int] = []
    usage_complete = True
    if compiler_calls:
        assert prepared.compilation is not None
        if prepared.compilation.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(prepared.compilation.total_tokens)
    fidelity_verifier_calls = 0
    if prepared.fidelity_verification is not None:
        fidelity_verifier_calls = prepared.fidelity_verification.model_calls
        if prepared.fidelity_verification.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(prepared.fidelity_verification.total_tokens)
    for execution in (primary, fallback):
        if execution is None:
            continue
        if execution.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(execution.total_tokens)
    observed = sum(usage_values) if usage_complete else None
    observed_ledger = _build_observed_execution_ledger(
        prepared,
        primary,
        fallback,
        observed_local_usage,
    )
    if observed_ledger.observed_model_total_tokens != observed:
        raise ValueError("observed model usage does not reconcile with the ledger")
    safely_completed = final_valid if type(final_valid) is bool else None
    observation_values = {
        "prepared": prepared,
        "primary": primary,
        "fallback": fallback,
        "observed_local_usage": observed_local_usage,
        "observed_ledger": observed_ledger,
    }
    return HybridExecution(
        prepared=prepared,
        primary=primary,
        fallback=fallback,
        final_mode=final_mode,
        compiler_calls=compiler_calls,
        fidelity_verifier_calls=fidelity_verifier_calls,
        receiver_calls=receiver_calls,
        output_valid=final_valid,
        safely_completed=safely_completed,
        observed_runtime_tokens=observed,
        observed_ledger=observed_ledger,
        claim_eligible=False,
        observed_local_usage=observed_local_usage,
        goal_total_complete=False,
        _construction_seal=_HybridObservationSeal(
            _hybrid_observation_fingerprint(observation_values)
        ),
    )


def prepare_message(
    source_text: str,
    capsule: Capsule,
    receiver: ReceiverCapabilities,
    token_counter: Callable[[str], int],
    *,
    task_context: PublicTaskContext,
    forecasts: Mapping[str, CostForecast],
    evidence: Mapping[str, UtilityEvidence] | None = None,
    compiler: StructuredCompiler | None = None,
    silence_proof: SilenceProof | None = None,
    routine: RoutineInvocation | None = None,
    surface_table: SurfaceAliasTable | None = None,
    active_surface: ActiveSurface | None = None,
    retained_surface: RetainedSurface | None = None,
    policy: RouterPolicy = RouterPolicy(),
    sender_capsule_context: CapsuleContextBinding | None = None,
    sender_context_verifier: Callable[
        [CapsuleContextBinding, Capsule, PublicTaskContext],
        SenderContextVerification,
    ]
    | None = None,
    fidelity_verifier: Callable[
        [FidelityVerificationInput], FidelityVerification
    ]
    | None = None,
    utility_evidence_verifier: Callable[
        [UtilityEvidence, str, str, str, str, str], LocalArtifactVerification
    ]
    | None = None,
    capsule_comprehension_verifier: Callable[
        [ReceiverCapabilities, Capsule], LocalArtifactVerification
    ]
    | None = None,
    task_context_comprehension_verifier: Callable[
        [ReceiverCapabilities, PublicTaskContext], LocalArtifactVerification
    ]
    | None = None,
    silence_verifier: Callable[[SilenceProof], LocalArtifactVerification]
    | None = None,
    routine_verifier: Callable[[RoutineInvocation], LocalArtifactVerification]
    | None = None,
) -> PreparedMessage:
    """Prepare one hybrid message with a safe raw/JSON fallback.

    The first pass can select a proven silence or routine route without paying
    for a compiler.  Only when those routes do not win and the cheap preflight
    permits action-state does the function invoke the injected sender compiler.
    It never calls the receiver model and never performs a tool or external
    action.
    """

    snapshot = _RoutingInputSnapshot.capture(
        forecasts=forecasts,
        evidence=evidence,
        routine=routine,
    )
    first_forecasts, first_evidence, first_routine = snapshot.materialize()

    first = plan_route(
        source_text,
        capsule,
        receiver,
        token_counter,
        task_context=task_context,
        forecasts=first_forecasts,
        evidence=first_evidence,
        compile_outcome=None,
        silence_proof=silence_proof,
        routine=first_routine,
        policy=policy,
        utility_evidence_verifier=utility_evidence_verifier,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
        silence_verifier=silence_verifier,
        routine_verifier=routine_verifier,
    )
    preparation_journal = PreparationJournalRecorder(first)
    if first.selected_mode in {"silence", "routine"}:
        preparation_journal.record_action_control(
            "skip-action-state",
            "preflight-terminal-route",
        )
        journal = preparation_journal.finish(first)
        return PreparedMessage(
            route=first,
            compilation=None,
            preparation_journal=journal,
        )

    attempt_forecasts, attempt_evidence, _ = snapshot.materialize()
    action_evidence = attempt_evidence.get("action-state")
    if compiler is None:
        attempt_action_state = False
        action_control_reason = "compiler-unavailable"
    elif fidelity_verifier is None:
        attempt_action_state = False
        action_control_reason = "fidelity-verifier-unavailable"
    else:
        attempt_action_state = should_attempt_action_state(
            receiver,
            capsule,
            task_context,
            action_evidence,
            policy,
            best_baseline_tokens=first.best_baseline_tokens,
            forecast=attempt_forecasts.get("action-state", CostForecast()),
            token_counter=token_counter,
            evidence_verifier=utility_evidence_verifier,
            capsule_comprehension_verifier=capsule_comprehension_verifier,
            task_context_comprehension_verifier=(
                task_context_comprehension_verifier
            ),
            surface_forecast=attempt_forecasts.get("action-state-surface"),
            surface_table=surface_table,
            active_surface=active_surface,
            retained_surface=retained_surface,
        )
        action_control_reason = (
            "action-state-preflight-passed"
            if attempt_action_state
            else "action-state-preflight-rejected"
        )
    preparation_journal.record_action_control(
        (
            "attempt-action-state"
            if attempt_action_state
            else "skip-action-state"
        ),
        action_control_reason,
    )
    if not attempt_action_state:
        journal = preparation_journal.finish(first)
        return PreparedMessage(
            route=first,
            compilation=None,
            preparation_journal=journal,
        )

    assert compiler is not None
    assert fidelity_verifier is not None
    compilation = compile_natural_language(
        source_text,
        capsule,
        compiler,
        task_context=task_context,
        capsule_context=sender_capsule_context,
        capsule_context_verifier=sender_context_verifier,
        maximum_total_tokens=policy.compiler_token_ceiling,
    )
    preparation_journal.record_compiler(compilation)
    preparation_journal.record_compiler_control(compilation)
    fidelity_verification: FidelityVerification | None = None
    if compilation.status == "ok" and compilation.compiled is not None:
        fidelity_input = FidelityVerificationInput(
            source_text=source_text,
            source_sha256=compilation.source_sha256,
            state=compilation.compiled,
            task_context=task_context,
            maximum_total_tokens=(
                policy.fidelity_verifier_token_ceiling
                if policy.fidelity_verifier_token_ceiling is not None
                else 0
            ),
        )
        try:
            candidate = fidelity_verifier(fidelity_input)
        except Exception:
            candidate = None
        if isinstance(candidate, FidelityVerification):
            fidelity_verification = candidate
        else:
            # The adapter was invoked but did not return trustworthy usage.
            # Conservatively make the fallback ledger incomplete.
            assert policy.fidelity_verifier_sha256 is not None
            fidelity_verification = FidelityVerification(
                passed=False,
                input_binding_sha256=fidelity_input.binding_sha256,
                verifier_sha256=policy.fidelity_verifier_sha256,
                method="independent-model",
                independent_of_compiler=False,
                model_calls=1,
                model_id="unknown-verifier-adapter",
                total_tokens=None,
                usage_complete=False,
            )
        preparation_journal.record_fidelity(fidelity_verification)
    final_forecasts, final_evidence, final_routine = snapshot.materialize()
    final = plan_route(
        source_text,
        capsule,
        receiver,
        token_counter,
        task_context=task_context,
        forecasts=final_forecasts,
        evidence=final_evidence,
        compile_outcome=compilation,
        fidelity_verification=fidelity_verification,
        surface_table=surface_table,
        active_surface=active_surface,
        retained_surface=retained_surface,
        silence_proof=silence_proof,
        routine=final_routine,
        policy=policy,
        utility_evidence_verifier=utility_evidence_verifier,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
        silence_verifier=silence_verifier,
        routine_verifier=routine_verifier,
    )
    journal = preparation_journal.finish(final)
    return PreparedMessage(
        route=final,
        compilation=compilation,
        fidelity_verification=fidelity_verification,
        preparation_journal=journal,
    )
