"""Fail-closed pre-receiver utility router for the five required modes."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
import math
import re
from typing import Any, Callable, Mapping

from .canonical import canonical_json, sha256_text, strict_json_loads
from .errors import RoutingError
from .fidelity import FidelityVerification, FidelityVerificationInput
from .integrity import current_runtime_sha256
from .receiver import (
    DIRECT_SYSTEM,
    SURFACE_DIRECT_SYSTEM,
    DirectReceiverRequest,
    build_action_state_request,
    build_json_request,
    build_raw_request,
    build_routine_request,
    build_silence_request,
    _build_surface_action_state_request,
)
from .records import Capsule, source_text_sha256
from .sender import CompileOutcome
from .task_context import (
    PublicTaskContext,
    validate_state_against_task_context,
)
from .surface import ActiveSurface, RetainedSurface, SurfaceAliasTable


ROUTE_MODES = ("silence", "routine", "action-state", "raw", "json")
OPTIMIZED_MODES = frozenset({"silence", "routine", "action-state"})
BASELINE_MODES = frozenset({"raw", "json"})
ROUTE_CLAIM_UNAVAILABLE = "route-claim-unavailable-no-authoritative-producer"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTEXT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$")
_DECISION_FINGERPRINT_FIELDS = (
    "source_sha256",
    "capsule_sha256",
    "fidelity_verifier_token_ceiling",
    "selected_mode",
    "request",
    "selected_cost",
    "candidates",
    "best_baseline_mode",
    "best_baseline_tokens",
    "claim_eligible",
    "fallback_from",
    "fallback_sender_tokens",
    "fallback_semantic_verification_tokens",
    "goal_gate_passed",
)


class _RouteDecisionSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _route_decision_fingerprint(values: Mapping[str, Any]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _DECISION_FINGERPRINT_FIELDS))
    )


@dataclass(frozen=True)
class ReceiverCapabilities:
    supports_raw: bool = True
    supports_json: bool = True
    supports_direct_action_state: bool = False
    accepts_declarative_capsule: bool = False
    capsule_comprehension_passed: bool = False
    capsule_cached_in_same_model_context: bool = False
    capsule_sha256: str | None = None
    capsule_context_id: str | None = None
    capsule_comprehension_sha256: str | None = None
    capsule_comprehension_verifier_sha256: str | None = None
    accepts_public_task_context: bool = False
    task_context_comprehension_passed: bool = False
    task_context_cached_in_same_model_context: bool = False
    task_context_sha256: str | None = None
    task_profile_sha256: str | None = None
    symbol_table_sha256: str | None = None
    task_context_id: str | None = None
    task_context_comprehension_sha256: str | None = None
    task_context_comprehension_verifier_sha256: str | None = None
    session_routine_sha256: tuple[str, ...] = ()
    session_only: bool = True
    persistence_authorized: bool = False
    permission_expansion_authorized: bool = False
    spending_authorized: bool = False
    external_effects_authorized: bool = False

    def __post_init__(self) -> None:
        for name in (
            "supports_raw",
            "supports_json",
            "supports_direct_action_state",
            "accepts_declarative_capsule",
            "capsule_comprehension_passed",
            "capsule_cached_in_same_model_context",
            "accepts_public_task_context",
            "task_context_comprehension_passed",
            "task_context_cached_in_same_model_context",
            "session_only",
            "persistence_authorized",
            "permission_expansion_authorized",
            "spending_authorized",
            "external_effects_authorized",
        ):
            if type(getattr(self, name)) is not bool:
                raise RoutingError(f"receiver capability {name} must be boolean")
        if not self.supports_raw:
            raise RoutingError("raw fallback is mandatory")
        if not self.session_only:
            raise RoutingError("development hybrid state must remain session-only")
        if any(
            (
                self.persistence_authorized,
                self.permission_expansion_authorized,
                self.spending_authorized,
                self.external_effects_authorized,
            )
        ):
            raise RoutingError("hybrid receiver capabilities cannot grant authority")
        if self.capsule_comprehension_passed and not self.accepts_declarative_capsule:
            raise RoutingError("Capsule comprehension requires Capsule acceptance")
        if self.capsule_cached_in_same_model_context and not self.capsule_comprehension_passed:
            raise RoutingError("cached Capsule requires proven comprehension")
        if self.task_context_comprehension_passed and not self.accepts_public_task_context:
            raise RoutingError(
                "task-context comprehension requires task-context acceptance"
            )
        if (
            self.task_context_cached_in_same_model_context
            and not self.task_context_comprehension_passed
        ):
            raise RoutingError(
                "cached task context requires proven comprehension"
            )
        if (
            self.accepts_declarative_capsule
            or self.capsule_comprehension_passed
            or self.capsule_cached_in_same_model_context
        ) and (
            self.capsule_sha256 is None
            or _SHA256.fullmatch(self.capsule_sha256) is None
        ):
            raise RoutingError("Capsule support requires an exact sha256 digest")
        if self.capsule_comprehension_passed and (
            self.capsule_comprehension_sha256 is None
            or _SHA256.fullmatch(self.capsule_comprehension_sha256) is None
        ):
            raise RoutingError(
                "Capsule comprehension requires an evidence digest"
            )
        if self.capsule_comprehension_passed and (
            self.capsule_comprehension_verifier_sha256 is None
            or _SHA256.fullmatch(
                self.capsule_comprehension_verifier_sha256
            )
            is None
        ):
            raise RoutingError(
                "Capsule comprehension requires a deterministic verifier digest"
            )
        if self.capsule_cached_in_same_model_context:
            if (
                type(self.capsule_context_id) is not str
                or _CONTEXT_ID.fullmatch(self.capsule_context_id) is None
            ):
                raise RoutingError("cached Capsule requires a model-context id")
        elif self.capsule_context_id is not None:
            raise RoutingError("uncached Capsule cannot claim a model-context id")
        if (
            self.accepts_public_task_context
            or self.task_context_comprehension_passed
            or self.task_context_cached_in_same_model_context
        ):
            for name in (
                "task_context_sha256",
                "task_profile_sha256",
                "symbol_table_sha256",
            ):
                value = getattr(self, name)
                if value is None or _SHA256.fullmatch(value) is None:
                    raise RoutingError(
                        f"task-context support requires an exact {name}"
                    )
        if self.task_context_comprehension_passed and (
            self.task_context_comprehension_sha256 is None
            or _SHA256.fullmatch(self.task_context_comprehension_sha256) is None
        ):
            raise RoutingError(
                "task-context comprehension requires an evidence digest"
            )
        if self.task_context_comprehension_passed and (
            self.task_context_comprehension_verifier_sha256 is None
            or _SHA256.fullmatch(
                self.task_context_comprehension_verifier_sha256
            )
            is None
        ):
            raise RoutingError(
                "task-context comprehension requires a deterministic verifier digest"
            )
        if self.task_context_cached_in_same_model_context:
            if (
                type(self.task_context_id) is not str
                or _CONTEXT_ID.fullmatch(self.task_context_id) is None
            ):
                raise RoutingError("cached task context requires a model-context id")
        elif self.task_context_id is not None:
            raise RoutingError(
                "uncached task context cannot claim a model-context id"
            )
        if (
            self.capsule_cached_in_same_model_context
            and self.task_context_cached_in_same_model_context
            and self.capsule_context_id != self.task_context_id
        ):
            raise RoutingError(
                "cached Capsule and task context must bind the same model context"
            )
        if len(set(self.session_routine_sha256)) != len(self.session_routine_sha256):
            raise RoutingError("session routine digest list contains duplicates")
        if any(_SHA256.fullmatch(item) is None for item in self.session_routine_sha256):
            raise RoutingError("session routine digest is invalid")


@dataclass(frozen=True)
class LocalArtifactVerification:
    """Typed proof that a verifier was deterministic, local, and zero-token."""

    passed: bool
    verifier_sha256: str
    deterministic_local: bool = True
    model_calls: int = 0
    total_tokens: int = 0
    tools_used: bool = False
    external_effects_performed: bool = False
    input_binding_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise RoutingError("local verification passed must be boolean")
        if _SHA256.fullmatch(self.verifier_sha256) is None:
            raise RoutingError("local verification digest is invalid")
        if self.deterministic_local is not True:
            raise RoutingError("route verifier must be deterministic and local")
        if type(self.model_calls) is not int or self.model_calls != 0:
            raise RoutingError("route verifier cannot make model calls")
        if type(self.total_tokens) is not int or self.total_tokens != 0:
            raise RoutingError("route verifier cannot consume model tokens")
        if type(self.tools_used) is not bool or self.tools_used:
            raise RoutingError("route verifier cannot use tools")
        if (
            type(self.external_effects_performed) is not bool
            or self.external_effects_performed
        ):
            raise RoutingError("route verifier cannot perform external effects")
        if self.input_binding_sha256 is not None and (
            type(self.input_binding_sha256) is not str
            or _SHA256.fullmatch(self.input_binding_sha256) is None
        ):
            raise RoutingError("local verification input binding is invalid")


@dataclass(frozen=True)
class UtilityEvidence:
    """Caller-supplied route-policy input, never claim authority by itself.

    The authoritative initial-goal verifier deliberately emits aggregate
    hybrid-system evidence and no route-scoped ``UtilityEvidence``.  These
    fields may therefore help a host make a conservative local routing choice
    after exact binding checks, but they cannot make a runtime route or the
    initial goal claim-eligible.
    """

    evidence_id: str
    route_mode: str
    capsule_sha256: str
    task_profile_sha256: str
    symbol_table_sha256: str
    runtime_sha256: str
    plan_sha256: str
    result_sha256: str
    verifier_sha256: str
    verifier_passed: bool
    frozen_before_execution: bool
    measurement_scope_complete: bool
    unseen_tasks: bool
    unseen_partner: bool
    domain_count: int
    model_family_count: int
    independent_operator_count: int
    project_operated_only: bool
    parse_validity: float | None
    semantic_fidelity: float | None
    task_success_difference_lcb: float | None
    total_token_reduction_lcb: float | None
    negative_rejection: float | None
    unauthorized_external_effects: int

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not str
            or _CONTEXT_ID.fullmatch(self.evidence_id) is None
        ):
            raise RoutingError(
                "utility evidence_id must be a bounded ASCII identifier"
            )
        if self.route_mode not in OPTIMIZED_MODES:
            raise RoutingError("utility evidence route_mode is not optimized")
        for name in (
            "capsule_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
            "runtime_sha256",
            "plan_sha256",
            "result_sha256",
            "verifier_sha256",
        ):
            if type(getattr(self, name)) is not str or _SHA256.fullmatch(getattr(self, name)) is None:
                raise RoutingError(f"utility {name} is invalid")
        for name in (
            "verifier_passed",
            "frozen_before_execution",
            "measurement_scope_complete",
            "unseen_tasks",
            "unseen_partner",
            "project_operated_only",
        ):
            if type(getattr(self, name)) is not bool:
                raise RoutingError(f"utility {name} must be boolean")
        for name in ("domain_count", "model_family_count", "independent_operator_count"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise RoutingError(f"{name} must be nonnegative")
        for name in ("parse_validity", "semantic_fidelity", "negative_rejection"):
            value = getattr(self, name)
            if value is not None and (
                type(value) not in {int, float} or not 0.0 <= value <= 1.0
            ):
                raise RoutingError(f"{name} must be null or 0..1")
        if self.task_success_difference_lcb is not None and (
            type(self.task_success_difference_lcb) not in {int, float}
            or not -1.0 <= self.task_success_difference_lcb <= 1.0
        ):
            raise RoutingError("task_success_difference_lcb must be null or -1..1")
        if self.total_token_reduction_lcb is not None and (
            type(self.total_token_reduction_lcb) not in {int, float}
            or not math.isfinite(float(self.total_token_reduction_lcb))
            or self.total_token_reduction_lcb > 1.0
        ):
            raise RoutingError("total_token_reduction_lcb cannot exceed 1")
        if type(self.unauthorized_external_effects) is not int or self.unauthorized_external_effects < 0:
            raise RoutingError("unauthorized_external_effects must be nonnegative")

    def declared_threshold_failures(self) -> tuple[str, ...]:
        """Return failures in the caller-supplied metric declarations only."""

        failures: list[str] = []
        checks = (
            (self.verifier_passed, "evidence-verifier-failed"),
            (self.frozen_before_execution, "evidence-not-frozen-before-execution"),
            (self.measurement_scope_complete, "incomplete-total-token-scope"),
            (self.unseen_tasks, "tasks-not-unseen"),
            (self.unseen_partner, "partner-not-unseen"),
            (self.domain_count >= 3, "fewer-than-three-domains"),
            (self.model_family_count >= 2, "not-multi-model"),
            (
                self.independent_operator_count >= 2,
                "fewer-than-two-independent-operators",
            ),
            (not self.project_operated_only, "project-operated-only"),
            (
                self.parse_validity is not None and self.parse_validity >= 0.99,
                "parse-validity-below-99-percent",
            ),
            (
                self.semantic_fidelity is not None and self.semantic_fidelity >= 0.95,
                "semantic-fidelity-below-95-percent",
            ),
            (
                self.task_success_difference_lcb is not None
                and self.task_success_difference_lcb >= -0.01,
                "task-success-noninferiority-failed",
            ),
            (
                self.total_token_reduction_lcb is not None
                and self.total_token_reduction_lcb >= 0.20,
                "total-token-reduction-below-20-percent",
            ),
            (
                self.negative_rejection is not None and self.negative_rejection >= 0.999,
                "negative-rejection-below-99.9-percent",
            ),
            (self.unauthorized_external_effects == 0, "unauthorized-effect-observed"),
        )
        for passed, reason in checks:
            if not passed:
                failures.append(reason)
        return tuple(failures)

    def goal_gate_failures(self) -> tuple[str, ...]:
        """Fail closed because no authoritative route-scoped producer exists."""

        return (*self.declared_threshold_failures(), ROUTE_CLAIM_UNAVAILABLE)

    @property
    def declared_thresholds_passed(self) -> bool:
        """Whether declared values meet thresholds for local policy use only."""

        return not self.declared_threshold_failures()

    @property
    def passes_initial_goal_gate(self) -> bool:
        """No runtime route can pass the aggregate initial-goal claim gate."""

        return False

    @property
    def binding_sha256(self) -> str:
        """Canonical identity of every route-policy evidence field."""

        values: dict[str, object] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            # JSON floating-point serialization is intentionally forbidden by
            # the runtime canonicalizer.  IEEE hexadecimal text preserves the
            # exact finite Python value without rounding or locale ambiguity.
            values[item.name] = (
                {"finite_float_hex": value.hex()}
                if type(value) is float
                else value
            )
        return sha256_text(canonical_json(values))


@dataclass(frozen=True)
class CostForecast:
    """Non-overlapping expected tokens not derivable from the carrier itself."""

    task_system_tokens: int = 0
    sender_tokens: int = 0
    router_tokens: int = 0
    provider_framing_tokens: int = 0
    receiver_output_tokens: int = 0
    reasoning_tokens: int = 0
    repair_tokens: int = 0
    fallback_tokens: int = 0
    tool_tokens: int = 0
    safety_tokens: int = 0
    judge_tokens: int = 0
    cached_context_tokens: int | None = None
    comprehension_setup_tokens: int | None = None
    routine_setup_tokens: int | None = None
    receiver_payload_token_ceiling: int | None = None
    complete: bool = False

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "complete":
                if type(value) is not bool:
                    raise RoutingError("cost forecast complete must be boolean")
            elif item.name in {
                "receiver_payload_token_ceiling",
                "cached_context_tokens",
            }:
                if value is not None and (type(value) is not int or value <= 0):
                    raise RoutingError(
                        f"{item.name} must be null or positive"
                    )
            elif item.name in {
                "comprehension_setup_tokens",
                "routine_setup_tokens",
            }:
                if value is not None and (type(value) is not int or value < 0):
                    raise RoutingError(f"{item.name} must be null or nonnegative")
            elif type(value) is not int or value < 0:
                raise RoutingError(f"cost forecast {item.name} must be nonnegative")


@dataclass(frozen=True)
class CostLedger:
    task_system_tokens: int
    task_context_setup_tokens: int
    capsule_setup_tokens: int
    cached_context_tokens: int
    comprehension_setup_tokens: int
    routine_setup_tokens: int
    sender_tokens: int
    semantic_verification_tokens: int
    router_tokens: int
    provider_framing_tokens: int
    receiver_input_tokens: int
    receiver_output_tokens: int
    reasoning_tokens: int
    repair_tokens: int
    fallback_tokens: int
    tool_tokens: int
    safety_tokens: int
    judge_tokens: int
    complete: bool

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "complete":
                if type(value) is not bool:
                    raise RoutingError("cost ledger complete must be boolean")
            elif type(value) is not int or value < 0:
                raise RoutingError(f"cost ledger {item.name} must be nonnegative")

    @property
    def total_tokens(self) -> int:
        return sum(
            getattr(self, item.name)
            for item in fields(self)
            if item.name != "complete"
        )


@dataclass(frozen=True)
class SilenceProof:
    source_text: str
    source_sha256: str
    task_context_text: str
    task_context_sha256: str
    verifier_sha256: str
    no_required_message: bool
    no_effectful_intent: bool
    session_local: bool = True
    deterministic_local_creation: bool = True
    creation_model_calls: int = 0
    creation_total_tokens: int = 0

    def __post_init__(self) -> None:
        if (
            _SHA256.fullmatch(self.source_sha256) is None
            or _SHA256.fullmatch(self.task_context_sha256) is None
            or _SHA256.fullmatch(self.verifier_sha256) is None
        ):
            raise RoutingError("silence proof digests are invalid")
        if source_text_sha256(self.source_text) != self.source_sha256:
            raise RoutingError("silence proof source text digest mismatch")
        try:
            parsed_task_context = PublicTaskContext.from_json(self.task_context_text)
        except ValueError as exc:
            raise RoutingError("silence proof task context is invalid") from exc
        if parsed_task_context.sha256 != self.task_context_sha256:
            raise RoutingError("silence proof task context digest mismatch")
        for name in (
            "no_required_message",
            "no_effectful_intent",
            "session_local",
            "deterministic_local_creation",
        ):
            if type(getattr(self, name)) is not bool:
                raise RoutingError(f"silence proof {name} must be boolean")
        if self.deterministic_local_creation is not True:
            raise RoutingError("silence proof must be created deterministically")
        if type(self.creation_model_calls) is not int or self.creation_model_calls != 0:
            raise RoutingError("silence proof creation cannot call a model")
        if type(self.creation_total_tokens) is not int or self.creation_total_tokens != 0:
            raise RoutingError("silence proof creation cannot consume model tokens")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "source_sha256": self.source_sha256,
                    "task_context_sha256": self.task_context_sha256,
                    "verifier_sha256": self.verifier_sha256,
                    "no_required_message": self.no_required_message,
                    "no_effectful_intent": self.no_effectful_intent,
                    "session_local": self.session_local,
                }
            )
        )


@dataclass(frozen=True)
class RoutineInvocation:
    routine_id: str
    routine_sha256: str
    routine_definition_text: str
    source_text: str
    source_sha256: str
    task_context_text: str
    task_context_sha256: str
    verifier_sha256: str
    payload: Any
    receiver_acknowledged: bool
    session_local: bool
    effect_free: bool
    deterministic_local_creation: bool = True
    creation_model_calls: int = 0
    creation_total_tokens: int = 0

    def __post_init__(self) -> None:
        if type(self.routine_id) is not str or not self.routine_id:
            raise RoutingError("routine_id must be non-empty")
        if (
            _SHA256.fullmatch(self.routine_sha256) is None
            or _SHA256.fullmatch(self.source_sha256) is None
            or _SHA256.fullmatch(self.task_context_sha256) is None
            or _SHA256.fullmatch(self.verifier_sha256) is None
        ):
            raise RoutingError("routine digests are invalid")
        if source_text_sha256(self.source_text) != self.source_sha256:
            raise RoutingError("routine source text digest mismatch")
        try:
            definition = strict_json_loads(self.routine_definition_text)
        except ValueError as exc:
            raise RoutingError("routine definition must be strict JSON") from exc
        if canonical_json(definition) != self.routine_definition_text:
            raise RoutingError("routine definition must be canonical JSON")
        if sha256_text(self.routine_definition_text) != self.routine_sha256:
            raise RoutingError("routine definition digest mismatch")
        try:
            parsed_task_context = PublicTaskContext.from_json(self.task_context_text)
        except ValueError as exc:
            raise RoutingError("routine task context is invalid") from exc
        if parsed_task_context.sha256 != self.task_context_sha256:
            raise RoutingError("routine task context digest mismatch")
        for name in (
            "receiver_acknowledged",
            "session_local",
            "effect_free",
            "deterministic_local_creation",
        ):
            if type(getattr(self, name)) is not bool:
                raise RoutingError(f"routine {name} must be boolean")
        if self.deterministic_local_creation is not True:
            raise RoutingError("routine invocation must be created deterministically")
        if type(self.creation_model_calls) is not int or self.creation_model_calls != 0:
            raise RoutingError("routine creation cannot call a model")
        if type(self.creation_total_tokens) is not int or self.creation_total_tokens != 0:
            raise RoutingError("routine creation cannot consume model tokens")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "routine_id": self.routine_id,
                    "routine_sha256": self.routine_sha256,
                    "source_sha256": self.source_sha256,
                    "task_context_sha256": self.task_context_sha256,
                    "verifier_sha256": self.verifier_sha256,
                    "payload": self.payload,
                    "receiver_acknowledged": self.receiver_acknowledged,
                    "session_local": self.session_local,
                    "effect_free": self.effect_free,
                }
            )
        )


@dataclass(frozen=True)
class RouterPolicy:
    allow_development_trial: bool = False
    switching_margin_tokens: int = 0
    compiler_token_ceiling: int | None = None
    fidelity_verifier_sha256: str | None = None
    fidelity_verifier_token_ceiling: int | None = None
    receiver_total_token_ceiling: int | None = None

    def __post_init__(self) -> None:
        if type(self.allow_development_trial) is not bool:
            raise RoutingError("allow_development_trial must be boolean")
        if type(self.switching_margin_tokens) is not int or self.switching_margin_tokens < 0:
            raise RoutingError("switching margin must be nonnegative")
        if self.compiler_token_ceiling is not None and (
            type(self.compiler_token_ceiling) is not int
            or self.compiler_token_ceiling <= 0
        ):
            raise RoutingError("compiler_token_ceiling must be null or positive")
        if self.fidelity_verifier_sha256 is not None and (
            type(self.fidelity_verifier_sha256) is not str
            or _SHA256.fullmatch(self.fidelity_verifier_sha256) is None
        ):
            raise RoutingError("fidelity_verifier_sha256 must be null or sha256")
        if self.fidelity_verifier_token_ceiling is not None and (
            type(self.fidelity_verifier_token_ceiling) is not int
            or self.fidelity_verifier_token_ceiling < 0
        ):
            raise RoutingError(
                "fidelity_verifier_token_ceiling must be null or nonnegative"
            )
        if self.receiver_total_token_ceiling is not None and (
            type(self.receiver_total_token_ceiling) is not int
            or self.receiver_total_token_ceiling <= 0
        ):
            raise RoutingError(
                "receiver_total_token_ceiling must be null or positive"
            )


@dataclass(frozen=True)
class RouteCandidate:
    mode: str
    request: DirectReceiverRequest | None
    cost: CostLedger | None
    eligible: bool
    claim_eligible: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.mode not in ROUTE_MODES:
            raise RoutingError("route candidate mode is unknown")
        if self.request is not None and self.request.mode != self.mode:
            raise RoutingError("route candidate request mode mismatch")
        if self.cost is not None and not isinstance(self.cost, CostLedger):
            raise RoutingError("route candidate cost is invalid")
        for name in ("eligible", "claim_eligible"):
            if type(getattr(self, name)) is not bool:
                raise RoutingError(f"route candidate {name} must be boolean")
        if self.claim_eligible and not self.eligible:
            raise RoutingError("ineligible route cannot be claim eligible")
        if self.claim_eligible:
            raise RoutingError(
                "runtime route claims require an authoritative route-scoped producer"
            )
        if type(self.reasons) is not tuple or any(
            type(item) is not str or not item for item in self.reasons
        ):
            raise RoutingError("route candidate reasons are invalid")


@dataclass(frozen=True)
class RouteDecision:
    source_sha256: str
    capsule_sha256: str
    fidelity_verifier_token_ceiling: int | None
    selected_mode: str
    request: DirectReceiverRequest
    selected_cost: CostLedger
    candidates: tuple[RouteCandidate, ...]
    best_baseline_mode: str
    best_baseline_tokens: int | None
    claim_eligible: bool
    fallback_from: str | None
    fallback_sender_tokens: int | None
    fallback_semantic_verification_tokens: int | None
    goal_gate_passed: bool
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {
            name: getattr(self, name) for name in _DECISION_FINGERPRINT_FIELDS
        }
        if (
            not isinstance(self._construction_seal, _RouteDecisionSeal)
            or self._construction_seal.fingerprint
            != _route_decision_fingerprint(values)
        ):
            raise RoutingError("RouteDecision must be created by plan_route")
        if (
            _SHA256.fullmatch(self.source_sha256) is None
            or _SHA256.fullmatch(self.capsule_sha256) is None
        ):
            raise RoutingError("route decision source or Capsule digest is invalid")
        if self.fidelity_verifier_token_ceiling is not None and (
            type(self.fidelity_verifier_token_ceiling) is not int
            or self.fidelity_verifier_token_ceiling < 0
        ):
            raise RoutingError("route fidelity verifier ceiling is invalid")
        if type(self.candidates) is not tuple or tuple(
            item.mode for item in self.candidates
        ) != ROUTE_MODES:
            raise RoutingError("route decision candidate matrix is incomplete")
        selected = next(
            (item for item in self.candidates if item.mode == self.selected_mode),
            None,
        )
        if selected is None or selected.request != self.request:
            raise RoutingError("route decision selected request is inconsistent")
        if self.request.mode != self.selected_mode:
            raise RoutingError("route decision request mode changed")
        if self.selected_mode in OPTIMIZED_MODES and not selected.eligible:
            raise RoutingError("route decision selected an ineligible optimized route")
        if self.best_baseline_mode not in BASELINE_MODES:
            raise RoutingError("route decision baseline is invalid")
        baseline = next(
            item for item in self.candidates if item.mode == self.best_baseline_mode
        )
        expected_baseline = (
            baseline.cost.total_tokens
            if baseline.cost is not None and baseline.cost.complete
            else None
        )
        if self.best_baseline_tokens != expected_baseline:
            raise RoutingError("route decision baseline token total is inconsistent")
        eligible_optimized = [
            item
            for item in self.candidates
            if item.mode in OPTIMIZED_MODES
            and item.eligible
            and item.cost is not None
        ]
        optimized_rank = {"silence": 0, "routine": 1, "action-state": 2}
        expected_selected = (
            min(
                eligible_optimized,
                key=lambda item: (
                    item.cost.total_tokens,
                    optimized_rank[item.mode],
                ),
            )
            if eligible_optimized
            else baseline
        )
        if selected != expected_selected:
            raise RoutingError("route decision did not select the deterministic winner")
        if selected.cost is None:
            raise RoutingError("selected route has no cost ledger")
        if self.fallback_from is None:
            if (
                self.fallback_sender_tokens != 0
                or self.fallback_semantic_verification_tokens != 0
                or self.selected_cost != selected.cost
            ):
                raise RoutingError("non-fallback selected cost is inconsistent")
        else:
            if self.selected_mode not in BASELINE_MODES or not self.fallback_from.startswith(
                "action-state:"
            ):
                raise RoutingError("route decision fallback metadata is invalid")
            if self.fallback_sender_tokens is not None and not (
                type(self.fallback_sender_tokens) is int
                and self.fallback_sender_tokens >= 0
            ):
                raise RoutingError("fallback sender token usage is invalid")
            if self.fallback_semantic_verification_tokens is not None and not (
                type(self.fallback_semantic_verification_tokens) is int
                and self.fallback_semantic_verification_tokens >= 0
            ):
                raise RoutingError(
                    "fallback semantic verification token usage is invalid"
                )
            expected_selected_cost = replace(
                selected.cost,
                sender_tokens=(
                    selected.cost.sender_tokens
                    + (self.fallback_sender_tokens or 0)
                ),
                semantic_verification_tokens=(
                    selected.cost.semantic_verification_tokens
                    + (self.fallback_semantic_verification_tokens or 0)
                ),
                complete=(
                    selected.cost.complete
                    and self.fallback_sender_tokens is not None
                    and self.fallback_semantic_verification_tokens is not None
                ),
            )
            if self.selected_cost != expected_selected_cost:
                raise RoutingError("fallback selected cost is inconsistent")
        if type(self.claim_eligible) is not bool or type(self.goal_gate_passed) is not bool:
            raise RoutingError("route decision claim flags must be boolean")
        if self.claim_eligible != selected.claim_eligible:
            raise RoutingError("route decision claim eligibility changed")
        if self.goal_gate_passed != self.claim_eligible:
            raise RoutingError("route decision goal gate is inconsistent")
        if self.claim_eligible or self.goal_gate_passed:
            raise RoutingError(
                "runtime route claims require an authoritative route-scoped producer"
            )
        bound_task_digests = {
            item.request.task_context_sha256
            for item in self.candidates
            if item.request is not None
        }
        if bound_task_digests != {self.request.task_context_sha256}:
            raise RoutingError("route candidates are not bound to one task context")
        action = next(item for item in self.candidates if item.mode == "action-state")
        if (
            action.request is not None
            and action.request.capsule_sha256 != self.capsule_sha256
        ):
            raise RoutingError("route action request is not bound to its Capsule")
        raw = next(item for item in self.candidates if item.mode == "raw")
        if (
            raw.request is None
            or source_text_sha256(raw.request.payload_text) != self.source_sha256
        ):
            raise RoutingError("route source digest is not bound to raw payload")

    @property
    def binding_sha256(self) -> str:
        """Exact identity of the sealed route, including every candidate."""

        return _route_decision_fingerprint(
            {
                name: getattr(self, name)
                for name in _DECISION_FINGERPRINT_FIELDS
            }
        )


def _safe_count(counter: Callable[[str], int], text: str) -> int:
    value = counter(text)
    if type(value) is not int or value < 0:
        raise RoutingError("token counter returned an invalid count")
    return value


def _cost(
    request: DirectReceiverRequest,
    forecast: CostForecast,
    counter: Callable[[str], int],
    *,
    sender_tokens: int | None = None,
    semantic_verification_tokens: int | None = 0,
) -> CostLedger:
    full_receiver_input = _safe_count(counter, request.model_visible_text)
    cached_context_required = (
        request.task_context_id is not None
        or request.capsule_context_id is not None
    )
    cached_context_tokens = forecast.cached_context_tokens or 0
    comprehension_setup_required = (
        request.mode == "action-state" or cached_context_required
    )
    routine_setup_required = request.mode == "routine"
    base_text = (
        "SYSTEM\n"
        + request.base_system_text
        + "\n\nUSER\nPAYLOAD\n"
        + request.payload_text
    )
    base_tokens = _safe_count(counter, base_text) if request.model_call_required else 0
    with_task_user_parts: list[str] = []
    if request.task_context_included:
        with_task_user_parts.append(
            "PUBLIC TASK CONTEXT\n" + request.task_context_text
        )
    with_task_user_parts.append("PAYLOAD\n" + request.payload_text)
    with_task_text = (
        "SYSTEM\n"
        + request.base_system_text
        + "\n\nUSER\n"
        + "\n\n".join(with_task_user_parts)
    )
    with_task_tokens = (
        _safe_count(counter, with_task_text)
        if request.model_call_required
        else 0
    )
    if full_receiver_input >= with_task_tokens >= base_tokens:
        receiver_input = base_tokens
        task_context_tokens = with_task_tokens - base_tokens
        capsule_tokens = full_receiver_input - with_task_tokens
    else:
        # A non-monotone custom counter still reconciles exactly; component
        # attribution becomes conservative instead of fabricating negative usage.
        receiver_input = full_receiver_input
        task_context_tokens = 0
        capsule_tokens = 0
    resolved_sender = forecast.sender_tokens if sender_tokens is None else sender_tokens
    return CostLedger(
        task_system_tokens=forecast.task_system_tokens,
        task_context_setup_tokens=task_context_tokens,
        capsule_setup_tokens=capsule_tokens,
        cached_context_tokens=cached_context_tokens,
        comprehension_setup_tokens=forecast.comprehension_setup_tokens or 0,
        routine_setup_tokens=forecast.routine_setup_tokens or 0,
        sender_tokens=resolved_sender,
        semantic_verification_tokens=semantic_verification_tokens or 0,
        router_tokens=forecast.router_tokens,
        provider_framing_tokens=forecast.provider_framing_tokens,
        receiver_input_tokens=receiver_input,
        receiver_output_tokens=forecast.receiver_output_tokens,
        reasoning_tokens=forecast.reasoning_tokens,
        repair_tokens=forecast.repair_tokens,
        fallback_tokens=forecast.fallback_tokens,
        tool_tokens=forecast.tool_tokens,
        safety_tokens=forecast.safety_tokens,
        judge_tokens=forecast.judge_tokens,
        complete=(
            forecast.complete
            and sender_tokens is not None
            and semantic_verification_tokens is not None
            and (not cached_context_required or forecast.cached_context_tokens is not None)
            and (
                not comprehension_setup_required
                or forecast.comprehension_setup_tokens is not None
            )
            and (
                not routine_setup_required
                or forecast.routine_setup_tokens is not None
            )
        ),
    )


def _evidence_eligibility(
    mode: str,
    evidence: UtilityEvidence | None,
    policy: RouterPolicy,
) -> tuple[bool, bool, tuple[str, ...]]:
    if mode in BASELINE_MODES:
        return True, False, ()
    if evidence is not None and evidence.declared_thresholds_passed:
        return True, False, (ROUTE_CLAIM_UNAVAILABLE,)
    failures = ("goal-evidence-missing",) if evidence is None else evidence.goal_gate_failures()
    if policy.allow_development_trial:
        return True, False, ("development-trial-only", *failures)
    return False, False, failures


def _receiver_forecast_total(cost: CostLedger) -> int:
    return sum(
        (
            cost.task_context_setup_tokens,
            cost.capsule_setup_tokens,
            cost.cached_context_tokens,
            cost.receiver_input_tokens,
            cost.provider_framing_tokens,
            cost.receiver_output_tokens,
            cost.reasoning_tokens,
        )
    )


def _validated_route_policy_evidence(
    evidence: UtilityEvidence | None,
    verifier: Callable[
        [UtilityEvidence, str, str, str, str, str], LocalArtifactVerification
    ]
    | None,
    *,
    mode: str,
    capsule_sha256: str,
    task_profile_sha256: str,
    symbol_table_sha256: str,
) -> UtilityEvidence | None:
    """Bind caller evidence for local route policy, never for claim issuance."""

    runtime_sha256 = current_runtime_sha256()
    if type(evidence) is not UtilityEvidence or verifier is None:
        return None
    try:
        evidence_binding_sha256 = evidence.binding_sha256
        evidence_verifier_sha256 = evidence.verifier_sha256
        if (
            evidence.route_mode != mode
            or evidence.capsule_sha256 != capsule_sha256
            or evidence.task_profile_sha256 != task_profile_sha256
            or evidence.symbol_table_sha256 != symbol_table_sha256
            or evidence.runtime_sha256 != runtime_sha256
        ):
            return None
        verified = verifier(
            evidence,
            mode,
            capsule_sha256,
            task_profile_sha256,
            symbol_table_sha256,
            runtime_sha256,
        )
        post_verification_binding_sha256 = evidence.binding_sha256
    except Exception:
        return None
    if (
        not isinstance(verified, LocalArtifactVerification)
        or not verified.passed
        or post_verification_binding_sha256 != evidence_binding_sha256
        or verified.verifier_sha256 != evidence_verifier_sha256
        or verified.input_binding_sha256 != evidence_binding_sha256
    ):
        return None
    return evidence


def _run_local_verifier(
    verifier: Callable[..., LocalArtifactVerification] | None,
    expected_verifier_sha256: str | None,
    *args: Any,
    expected_input_binding_sha256: str | None = None,
) -> bool:
    if verifier is None or expected_verifier_sha256 is None:
        return False
    try:
        result = verifier(*args)
    except Exception:
        return False
    return (
        isinstance(result, LocalArtifactVerification)
        and result.passed
        and result.verifier_sha256 == expected_verifier_sha256
        and (
            expected_input_binding_sha256 is None
            or result.input_binding_sha256 == expected_input_binding_sha256
        )
    )


def action_state_preflight(
    receiver: ReceiverCapabilities,
    capsule: Capsule,
    task_context: PublicTaskContext,
    evidence: UtilityEvidence | None,
    policy: RouterPolicy,
    *,
    capsule_comprehension_verifier: Callable[
        [ReceiverCapabilities, Capsule], LocalArtifactVerification
    ]
    | None,
    task_context_comprehension_verifier: Callable[
        [ReceiverCapabilities, PublicTaskContext], LocalArtifactVerification
    ]
    | None,
) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    if not receiver.supports_direct_action_state:
        failures.append("receiver-does-not-support-direct-action-state")
    if not receiver.accepts_declarative_capsule:
        failures.append("receiver-does-not-accept-declarative-capsule")
    if not receiver.capsule_comprehension_passed:
        failures.append("capsule-comprehension-not-proven")
    if receiver.capsule_sha256 != capsule.sha256:
        failures.append("capsule-digest-mismatch")
    if not receiver.accepts_public_task_context:
        failures.append("receiver-does-not-accept-public-task-context")
    if not receiver.task_context_comprehension_passed:
        failures.append("task-context-comprehension-not-proven")
    if receiver.task_context_sha256 != task_context.sha256:
        failures.append("task-context-digest-mismatch")
    if receiver.task_profile_sha256 != task_context.task_profile_sha256:
        failures.append("task-profile-digest-mismatch")
    if receiver.symbol_table_sha256 != task_context.symbol_table_sha256:
        failures.append("symbol-table-digest-mismatch")
    if not _run_local_verifier(
        capsule_comprehension_verifier,
        receiver.capsule_comprehension_verifier_sha256,
        receiver,
        capsule,
    ):
        failures.append("capsule-comprehension-verification-failed")
    if not _run_local_verifier(
        task_context_comprehension_verifier,
        receiver.task_context_comprehension_verifier_sha256,
        receiver,
        task_context,
    ):
        failures.append("task-context-comprehension-verification-failed")
    evidence_ok, _, evidence_failures = _evidence_eligibility(
        "action-state", evidence, policy
    )
    if not evidence_ok:
        failures.extend(evidence_failures)
    return not failures, tuple(failures)


def should_attempt_action_state(
    receiver: ReceiverCapabilities,
    capsule: Capsule,
    task_context: PublicTaskContext,
    evidence: UtilityEvidence | None,
    policy: RouterPolicy,
    *,
    best_baseline_tokens: int | None,
    forecast: CostForecast,
    token_counter: Callable[[str], int],
    evidence_verifier: Callable[
        [UtilityEvidence, str, str, str, str, str], LocalArtifactVerification
    ]
    | None,
    capsule_comprehension_verifier: Callable[
        [ReceiverCapabilities, Capsule], LocalArtifactVerification
    ]
    | None,
    task_context_comprehension_verifier: Callable[
        [ReceiverCapabilities, PublicTaskContext], LocalArtifactVerification
    ]
    | None,
    surface_forecast: CostForecast | None = None,
    surface_table: SurfaceAliasTable | None = None,
    active_surface: ActiveSurface | None = None,
    retained_surface: RetainedSurface | None = None,
) -> bool:
    """Conservative pre-compiler gate; no model call or outcome is consulted.

    Compilation is worthwhile when either the canonical action-state carrier or
    an already activated, exactly scoped evolving surface can conservatively
    beat the best raw/JSON baseline.  Surface activation setup is deliberately
    absent here: it is a session-level sunk cost charged exactly once by the
    frozen ``SurfaceTrial``, while this gate compares marginal message costs.
    """

    trusted_evidence = _validated_route_policy_evidence(
        evidence,
        evidence_verifier,
        mode="action-state",
        capsule_sha256=capsule.sha256,
        task_profile_sha256=task_context.task_profile_sha256,
        symbol_table_sha256=task_context.symbol_table_sha256,
    )
    if not action_state_preflight(
        receiver,
        capsule,
        task_context,
        trusted_evidence,
        policy,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
    )[0]:
        return False
    if (
        best_baseline_tokens is None
        or policy.compiler_token_ceiling is None
        or policy.fidelity_verifier_sha256 is None
        or policy.fidelity_verifier_token_ceiling is None
        or policy.receiver_total_token_ceiling is None
    ):
        return False

    cached_context_required = (
        receiver.task_context_cached_in_same_model_context
        or receiver.capsule_cached_in_same_model_context
    )

    def forecast_can_win(candidate: CostForecast, system_text: str) -> bool:
        if (
            not candidate.complete
            or candidate.receiver_payload_token_ceiling is None
            or candidate.comprehension_setup_tokens is None
            or (
                cached_context_required
                and candidate.cached_context_tokens is None
            )
        ):
            return False
        static_user_parts: list[str] = []
        if not receiver.task_context_cached_in_same_model_context:
            static_user_parts.append(
                "PUBLIC TASK CONTEXT\n" + task_context.canonical_text
            )
        if not receiver.capsule_cached_in_same_model_context:
            static_user_parts.append(
                "DECLARATIVE CAPSULE\n" + capsule.canonical_text
            )
        static_user_parts.append("PAYLOAD\n")
        static_receiver_text = (
            "SYSTEM\n"
            + system_text
            + "\n\nUSER\n"
            + "\n\n".join(static_user_parts)
        )
        static_receiver_tokens = _safe_count(
            token_counter, static_receiver_text
        )
        receiver_forecast_total = (
            static_receiver_tokens
            + candidate.receiver_payload_token_ceiling
            + (candidate.cached_context_tokens or 0)
            + candidate.provider_framing_tokens
            + candidate.receiver_output_tokens
            + candidate.reasoning_tokens
        )
        assert policy.receiver_total_token_ceiling is not None
        if receiver_forecast_total > policy.receiver_total_token_ceiling:
            return False
        assert policy.compiler_token_ceiling is not None
        assert policy.fidelity_verifier_token_ceiling is not None
        non_receiver = sum(
            (
                candidate.task_system_tokens,
                policy.compiler_token_ceiling,
                policy.fidelity_verifier_token_ceiling,
                candidate.router_tokens,
                candidate.provider_framing_tokens,
                candidate.receiver_output_tokens,
                candidate.reasoning_tokens,
                candidate.repair_tokens,
                candidate.fallback_tokens,
                candidate.tool_tokens,
                candidate.safety_tokens,
                candidate.judge_tokens,
                candidate.comprehension_setup_tokens,
            )
        )
        conservative_total = (
            static_receiver_tokens
            + candidate.receiver_payload_token_ceiling
            + (candidate.cached_context_tokens or 0)
            + non_receiver
        )
        return conservative_total < (
            best_baseline_tokens - policy.switching_margin_tokens
        )

    if forecast_can_win(forecast, DIRECT_SYSTEM):
        return True

    surface_is_exactly_authorized = (
        surface_forecast is not None
        and surface_table is not None
        and active_surface is not None
        and retained_surface is not None
        and active_surface.authorizes(surface_table)
        and retained_surface.authorizes(surface_table, active_surface)
        and surface_table.scope.capsule_sha256 == capsule.sha256
        and surface_table.scope.task_profile_sha256
        == task_context.task_profile_sha256
        and surface_table.scope.symbol_table_sha256
        == task_context.symbol_table_sha256
    )
    return bool(
        surface_is_exactly_authorized
        and forecast_can_win(surface_forecast, SURFACE_DIRECT_SYSTEM)
    )


def _candidate(
    mode: str,
    request: DirectReceiverRequest | None,
    cost: CostLedger | None,
    base_eligible: bool,
    evidence: UtilityEvidence | None,
    policy: RouterPolicy,
    reasons: list[str] | None = None,
    *,
    session_local_retained_surface: bool = False,
) -> RouteCandidate:
    reason_list = list(reasons or ())
    if session_local_retained_surface:
        # A frozen, passing surface trial authorizes only this exact session and
        # model context.  It can make the live route locally eligible, but it
        # cannot inherit or manufacture a general action-state performance claim.
        evidence_ok = True
        claim_eligible = False
        evidence_reasons = ("session-local-retained-surface-only",)
    else:
        evidence_ok, claim_eligible, evidence_reasons = _evidence_eligibility(
            mode, evidence, policy
        )
    eligible = base_eligible and evidence_ok
    if not base_eligible:
        claim_eligible = False
    if not evidence_ok or (mode in OPTIMIZED_MODES and not claim_eligible):
        reason_list.extend(item for item in evidence_reasons if item not in reason_list)
    if cost is None or not cost.complete:
        eligible = mode in BASELINE_MODES and base_eligible
        claim_eligible = False
        if "incomplete-cost-forecast" not in reason_list:
            reason_list.append("incomplete-cost-forecast")
    return RouteCandidate(
        mode=mode,
        request=request,
        cost=cost,
        eligible=eligible,
        claim_eligible=claim_eligible,
        reasons=tuple(reason_list),
    )


def plan_route(
    source_text: str,
    capsule: Capsule,
    receiver: ReceiverCapabilities,
    token_counter: Callable[[str], int],
    *,
    task_context: PublicTaskContext,
    forecasts: Mapping[str, CostForecast],
    evidence: Mapping[str, UtilityEvidence] | None = None,
    compile_outcome: CompileOutcome | None = None,
    fidelity_verification: FidelityVerification | None = None,
    surface_table: SurfaceAliasTable | None = None,
    active_surface: ActiveSurface | None = None,
    retained_surface: RetainedSurface | None = None,
    silence_proof: SilenceProof | None = None,
    routine: RoutineInvocation | None = None,
    policy: RouterPolicy = RouterPolicy(),
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
) -> RouteDecision:
    """Select a route before the receiver model call and without outcome data."""

    source_digest = source_text_sha256(source_text)
    untrusted_evidence_map = dict(evidence or {})
    evidence_map = {
        mode: trusted
        for mode, item in untrusted_evidence_map.items()
        if (
            trusted := _validated_route_policy_evidence(
                item,
                utility_evidence_verifier,
                mode=mode,
                capsule_sha256=capsule.sha256,
                task_profile_sha256=task_context.task_profile_sha256,
                symbol_table_sha256=task_context.symbol_table_sha256,
            )
        )
        is not None
    }

    task_context_verified = (
        receiver.task_context_comprehension_passed
        and receiver.task_context_sha256 == task_context.sha256
        and receiver.task_profile_sha256 == task_context.task_profile_sha256
        and receiver.symbol_table_sha256 == task_context.symbol_table_sha256
        and _run_local_verifier(
            task_context_comprehension_verifier,
            receiver.task_context_comprehension_verifier_sha256,
            receiver,
            task_context,
        )
    )
    task_context_cache_verified = (
        receiver.task_context_cached_in_same_model_context
        and task_context_verified
    )
    task_request_kwargs = {
        "task_context_cached_in_same_model_context": task_context_cache_verified,
        "task_context_id": (
            receiver.task_context_id if task_context_cache_verified else None
        ),
        "task_comprehension_evidence_sha256": (
            receiver.task_context_comprehension_sha256
            if task_context_verified
            else None
        ),
        "task_comprehension_verifier_sha256": (
            receiver.task_context_comprehension_verifier_sha256
            if task_context_verified
            else None
        ),
        "maximum_total_tokens": policy.receiver_total_token_ceiling,
    }

    raw_request = build_raw_request(
        source_text,
        task_context,
        **task_request_kwargs,
    )
    raw_forecast = forecasts.get("raw", CostForecast())
    raw_cost = _cost(raw_request, raw_forecast, token_counter, sender_tokens=0)
    candidates: dict[str, RouteCandidate] = {
        "raw": _candidate(
            "raw", raw_request, raw_cost, True, None, policy
        )
    }

    if receiver.supports_json:
        json_request = build_json_request(
            source_text,
            task_context,
            **task_request_kwargs,
        )
        json_forecast = forecasts.get("json", CostForecast())
        json_cost = _cost(json_request, json_forecast, token_counter, sender_tokens=0)
        candidates["json"] = _candidate(
            "json", json_request, json_cost, True, None, policy
        )
    else:
        candidates["json"] = _candidate(
            "json", None, None, False, None, policy, ["receiver-does-not-support-json"]
        )

    baseline_complete = [
        item
        for item in candidates.values()
        if item.mode in BASELINE_MODES
        and item.eligible
        and item.cost is not None
        and item.cost.complete
    ]
    baseline_rank = {"raw": 0, "json": 1}
    if baseline_complete:
        best_baseline = min(
            baseline_complete,
            key=lambda item: (item.cost.total_tokens, baseline_rank[item.mode]),
        )
    else:
        best_baseline = candidates["raw"]

    silence_reasons: list[str] = []
    silence_ok = silence_proof is not None
    if silence_proof is None:
        silence_reasons.append("silence-proof-missing")
    else:
        if silence_proof.source_text != source_text:
            silence_ok = False
            silence_reasons.append("silence-source-text-mismatch")
        if silence_proof.source_sha256 != source_digest:
            silence_ok = False
            silence_reasons.append("silence-source-digest-mismatch")
        if silence_proof.task_context_sha256 != task_context.sha256:
            silence_ok = False
            silence_reasons.append("silence-task-context-digest-mismatch")
        if silence_proof.task_context_text != task_context.canonical_text:
            silence_ok = False
            silence_reasons.append("silence-task-context-text-mismatch")
        if not silence_proof.no_required_message:
            silence_ok = False
            silence_reasons.append("message-still-required")
        if not silence_proof.no_effectful_intent:
            silence_ok = False
            silence_reasons.append("effectful-intent-cannot-be-silenced")
        if not silence_proof.session_local:
            silence_ok = False
            silence_reasons.append("silence-proof-not-session-local")
        if not _run_local_verifier(
            silence_verifier,
            silence_proof.verifier_sha256,
            silence_proof,
            expected_input_binding_sha256=silence_proof.binding_sha256,
        ):
            silence_ok = False
            silence_reasons.append("silence-proof-verification-failed")
    silence_request = build_silence_request(task_context) if silence_ok else None
    silence_cost = None
    if silence_request is not None:
        silence_cost = _cost(
            silence_request,
            forecasts.get("silence", CostForecast()),
            token_counter,
            sender_tokens=0,
        )
    candidates["silence"] = _candidate(
        "silence",
        silence_request,
        silence_cost,
        silence_ok,
        evidence_map.get("silence"),
        policy,
        silence_reasons,
    )

    routine_reasons: list[str] = []
    routine_ok = routine is not None
    if policy.receiver_total_token_ceiling is None:
        routine_ok = False
        routine_reasons.append("receiver-token-ceiling-missing")
    if routine is None:
        routine_reasons.append("routine-invocation-missing")
        routine_request = None
        routine_cost = None
    else:
        if routine.source_text != source_text:
            routine_ok = False
            routine_reasons.append("routine-source-text-mismatch")
        if routine.source_sha256 != source_digest:
            routine_ok = False
            routine_reasons.append("routine-source-digest-mismatch")
        if routine.task_context_sha256 != task_context.sha256:
            routine_ok = False
            routine_reasons.append("routine-task-context-digest-mismatch")
        if routine.task_context_text != task_context.canonical_text:
            routine_ok = False
            routine_reasons.append("routine-task-context-text-mismatch")
        if not routine.receiver_acknowledged:
            routine_ok = False
            routine_reasons.append("routine-not-acknowledged")
        if not routine.session_local:
            routine_ok = False
            routine_reasons.append("routine-not-session-local")
        if not routine.effect_free:
            routine_ok = False
            routine_reasons.append("routine-not-effect-free")
        if routine.routine_sha256 not in receiver.session_routine_sha256:
            routine_ok = False
            routine_reasons.append("routine-digest-not-active-at-receiver")
        if not _run_local_verifier(
            routine_verifier,
            routine.verifier_sha256,
            routine,
            expected_input_binding_sha256=routine.binding_sha256,
        ):
            routine_ok = False
            routine_reasons.append("routine-verification-failed")
        routine_request = (
            build_routine_request(
                routine.payload,
                routine.routine_sha256,
                task_context,
                **task_request_kwargs,
            )
            if routine_ok
            else None
        )
        routine_cost = (
            _cost(
                routine_request,
                forecasts.get("routine", CostForecast()),
                token_counter,
                sender_tokens=0,
            )
            if routine_request is not None
            else None
        )
        if (
            routine_cost is not None
            and policy.receiver_total_token_ceiling is not None
            and _receiver_forecast_total(routine_cost)
            > policy.receiver_total_token_ceiling
        ):
            routine_ok = False
            routine_reasons.append("receiver-token-ceiling-forecast-exceeded")
            routine_request = None
            routine_cost = None
    candidates["routine"] = _candidate(
        "routine",
        routine_request,
        routine_cost,
        routine_ok,
        evidence_map.get("routine"),
        policy,
        routine_reasons,
    )

    action_reasons: list[str] = []
    preflight_ok, preflight_reasons = action_state_preflight(
        receiver,
        capsule,
        task_context,
        evidence_map.get("action-state"),
        policy,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
    )
    action_reasons.extend(preflight_reasons)
    action_ok = preflight_ok and compile_outcome is not None
    if policy.fidelity_verifier_sha256 is None:
        action_ok = False
        action_reasons.append("fidelity-verifier-digest-missing")
    if policy.fidelity_verifier_token_ceiling is None:
        action_ok = False
        action_reasons.append("fidelity-verifier-token-ceiling-missing")
    if policy.receiver_total_token_ceiling is None:
        action_ok = False
        action_reasons.append("receiver-token-ceiling-missing")
    action_request = None
    action_cost = None
    action_uses_retained_surface = False
    if compile_outcome is None:
        action_reasons.append("compiler-not-run")
    else:
        if compile_outcome.source_sha256 != source_digest:
            action_ok = False
            action_reasons.append("compiler-source-digest-mismatch")
        if compile_outcome.capsule_sha256 != capsule.sha256:
            action_ok = False
            action_reasons.append("compiler-capsule-digest-mismatch")
        if compile_outcome.task_context_sha256 != task_context.sha256:
            action_ok = False
            action_reasons.append("compiler-task-context-digest-mismatch")
        if compile_outcome.task_profile_sha256 != task_context.task_profile_sha256:
            action_ok = False
            action_reasons.append("compiler-task-profile-digest-mismatch")
        if compile_outcome.symbol_table_sha256 != task_context.symbol_table_sha256:
            action_ok = False
            action_reasons.append("compiler-symbol-table-digest-mismatch")
        state = compile_outcome.compiled
        if state is None:
            action_ok = False
            action_reasons.append(f"compiler-status-{compile_outcome.status}")
        if compile_outcome.total_tokens is None:
            action_ok = False
            action_reasons.append("compiler-token-usage-unknown")
        if state is not None:
            try:
                validate_state_against_task_context(state, task_context)
            except ValueError:
                action_ok = False
                action_reasons.append("action-state-task-schema-mismatch")
        fidelity_input = None
        if state is not None:
            fidelity_input = FidelityVerificationInput(
                source_text=source_text,
                source_sha256=source_digest,
                state=state,
                task_context=task_context,
                maximum_total_tokens=(
                    policy.fidelity_verifier_token_ceiling
                    if policy.fidelity_verifier_token_ceiling is not None
                    else 0
                ),
            )
        if fidelity_verification is None:
            action_ok = False
            action_reasons.append("per-message-fidelity-verification-missing")
        elif fidelity_input is None:
            action_ok = False
            action_reasons.append("per-message-fidelity-input-missing")
        else:
            if (
                fidelity_verification.input_binding_sha256
                != fidelity_input.binding_sha256
            ):
                action_ok = False
                action_reasons.append("per-message-fidelity-binding-mismatch")
            if (
                policy.fidelity_verifier_sha256 is None
                or fidelity_verification.verifier_sha256
                != policy.fidelity_verifier_sha256
            ):
                action_ok = False
                action_reasons.append("per-message-fidelity-verifier-mismatch")
            if not fidelity_verification.passed:
                action_ok = False
                action_reasons.append("per-message-semantic-fidelity-failed")
            if not fidelity_verification.independent_of_compiler:
                action_ok = False
                action_reasons.append("fidelity-verifier-not-independent")
            if (
                fidelity_verification.method == "independent-model"
                and compile_outcome.model_id is not None
                and fidelity_verification.model_id == compile_outcome.model_id
            ):
                action_ok = False
                action_reasons.append("compiler-and-fidelity-model-identical")
            if (
                not fidelity_verification.usage_complete
                or fidelity_verification.total_tokens is None
            ):
                action_ok = False
                action_reasons.append("fidelity-verifier-token-usage-unknown")
            elif (
                policy.fidelity_verifier_token_ceiling is None
                or fidelity_verification.total_tokens
                > policy.fidelity_verifier_token_ceiling
            ):
                action_ok = False
                action_reasons.append("fidelity-verifier-token-ceiling-exceeded")
        if action_ok and state is not None:
            assert fidelity_input is not None
            assert fidelity_verification is not None
            canonical_action_request = build_action_state_request(
                state,
                capsule,
                task_context,
                **task_request_kwargs,
                capsule_cached_in_same_model_context=receiver.capsule_cached_in_same_model_context,
                capsule_context_id=receiver.capsule_context_id,
                comprehension_evidence_sha256=(
                    receiver.capsule_comprehension_sha256 or ""
                ),
                capsule_comprehension_verifier_sha256=(
                    receiver.capsule_comprehension_verifier_sha256 or ""
                ),
            )
            canonical_action_cost = _cost(
                canonical_action_request,
                forecasts.get("action-state", CostForecast()),
                token_counter,
                sender_tokens=compile_outcome.total_tokens,
                semantic_verification_tokens=(
                    fidelity_verification.total_tokens
                    if fidelity_verification is not None
                    else None
                ),
            )
            action_request = canonical_action_request
            action_cost = canonical_action_cost
            surface_bindings = (
                surface_table,
                active_surface,
                retained_surface,
            )
            if any(item is not None for item in surface_bindings) and not all(
                item is not None for item in surface_bindings
            ):
                action_reasons.append("evolving-surface-binding-incomplete")
            elif (
                surface_table is not None
                and active_surface is not None
                and retained_surface is not None
            ):
                surface_forecast = forecasts.get("action-state-surface")
                if surface_forecast is None:
                    action_reasons.append("evolving-surface-forecast-missing")
                else:
                    try:
                        surface_action_request = _build_surface_action_state_request(
                            state,
                            capsule,
                            task_context,
                            surface_table,
                            active_surface,
                            retained_surface,
                            fidelity_input=fidelity_input,
                            fidelity_verification=fidelity_verification,
                            expected_fidelity_verifier_sha256=(
                                policy.fidelity_verifier_sha256 or ""
                            ),
                            **task_request_kwargs,
                            capsule_cached_in_same_model_context=(
                                receiver.capsule_cached_in_same_model_context
                            ),
                            capsule_context_id=receiver.capsule_context_id,
                            comprehension_evidence_sha256=(
                                receiver.capsule_comprehension_sha256 or ""
                            ),
                            capsule_comprehension_verifier_sha256=(
                                receiver.capsule_comprehension_verifier_sha256 or ""
                            ),
                        )
                        surface_action_cost = _cost(
                            surface_action_request,
                            surface_forecast,
                            token_counter,
                            sender_tokens=compile_outcome.total_tokens,
                            semantic_verification_tokens=(
                                fidelity_verification.total_tokens
                                if fidelity_verification is not None
                                else None
                            ),
                        )
                        if (
                            surface_action_cost.complete
                            and surface_action_cost.total_tokens
                            < canonical_action_cost.total_tokens
                        ):
                            action_request = surface_action_request
                            action_cost = surface_action_cost
                            action_uses_retained_surface = True
                    except ValueError:
                        action_reasons.append("evolving-surface-validation-failed")
            if (
                policy.receiver_total_token_ceiling is not None
                and _receiver_forecast_total(action_cost)
                > policy.receiver_total_token_ceiling
            ):
                action_ok = False
                action_reasons.append("receiver-token-ceiling-forecast-exceeded")
                action_request = None
                action_cost = None
    candidates["action-state"] = _candidate(
        "action-state",
        action_request,
        action_cost,
        action_ok,
        evidence_map.get("action-state"),
        policy,
        action_reasons,
        session_local_retained_surface=action_uses_retained_surface,
    )

    if best_baseline.cost is None or not best_baseline.cost.complete:
        for mode in OPTIMIZED_MODES:
            item = candidates[mode]
            candidates[mode] = replace(
                item,
                eligible=False,
                claim_eligible=False,
                reasons=(*item.reasons, "best-raw-json-baseline-incomplete"),
            )
    else:
        threshold = best_baseline.cost.total_tokens - policy.switching_margin_tokens
        for mode in OPTIMIZED_MODES:
            item = candidates[mode]
            if (
                item.eligible
                and item.cost is not None
                and item.cost.total_tokens >= threshold
            ):
                candidates[mode] = replace(
                    item,
                    eligible=False,
                    claim_eligible=False,
                    reasons=(*item.reasons, "no-strict-total-token-advantage"),
                )

    eligible_optimized = [
        item
        for mode, item in candidates.items()
        if mode in OPTIMIZED_MODES and item.eligible and item.cost is not None
    ]
    optimized_rank = {"silence": 0, "routine": 1, "action-state": 2}
    if eligible_optimized:
        selected = min(
            eligible_optimized,
            key=lambda item: (item.cost.total_tokens, optimized_rank[item.mode]),
        )
    else:
        selected = best_baseline
    assert selected.request is not None and selected.cost is not None

    fallback_from = None
    fallback_sender_tokens: int | None = 0
    fallback_semantic_verification_tokens: int | None = 0
    selected_cost = selected.cost
    if (
        compile_outcome is not None
        and compile_outcome.attempted
        and selected.mode != "action-state"
    ):
        fallback_from = f"action-state:{compile_outcome.status}"
        fallback_sender_tokens = compile_outcome.total_tokens
        fallback_semantic_verification_tokens = (
            fidelity_verification.total_tokens
            if fidelity_verification is not None
            else 0
        )
        selected_cost = replace(
            selected_cost,
            sender_tokens=(
                selected_cost.sender_tokens + (fallback_sender_tokens or 0)
            ),
            semantic_verification_tokens=(
                selected_cost.semantic_verification_tokens
                + (fallback_semantic_verification_tokens or 0)
            ),
            complete=(
                selected_cost.complete
                and fallback_sender_tokens is not None
                and fallback_semantic_verification_tokens is not None
            ),
        )

    ordered = tuple(candidates[mode] for mode in ROUTE_MODES)
    decision_values = {
        "source_sha256": source_digest,
        "capsule_sha256": capsule.sha256,
        "fidelity_verifier_token_ceiling": (
            policy.fidelity_verifier_token_ceiling
        ),
        "selected_mode": selected.mode,
        "request": selected.request,
        "selected_cost": selected_cost,
        "candidates": ordered,
        "best_baseline_mode": best_baseline.mode,
        "best_baseline_tokens": (
            best_baseline.cost.total_tokens
            if best_baseline.cost is not None and best_baseline.cost.complete
            else None
        ),
        "claim_eligible": False,
        "fallback_from": fallback_from,
        "fallback_sender_tokens": fallback_sender_tokens,
        "fallback_semantic_verification_tokens": (
            fallback_semantic_verification_tokens
        ),
        "goal_gate_passed": False,
    }
    return RouteDecision(
        **decision_values,
        _construction_seal=_RouteDecisionSeal(
            _route_decision_fingerprint(decision_values)
        ),
    )
