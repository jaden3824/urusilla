"""Same-context Capsule use with a cold, lossless fallback.

This module is the narrow bridge between the cold comprehension proof, the
stateful provider-context guard, and the ordinary hybrid router.  It does not
create a provider client or grant authority.  A host still supplies adapters,
but an optimized turn can reach one only after exact session, Capsule, task,
and action-state validation.  Every optimized-path failure is contained and
the already prepared cold raw/JSON baseline is used instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .canonical import canonical_json, sha256_text
from .comprehension import ComprehensionAttempt
from .receiver import (
    DirectReceiverRequest,
    ReceiverExecution,
    ReceiverModelAdapter,
    ReceiverModelReply,
    execute_receiver,
)
from .records import Capsule, PublicActionState, source_text_sha256
from .router import LocalArtifactVerification, ReceiverCapabilities
from .runtime import LocalOutputValidation, OutputValidationInput, PreparedMessage
from .session import (
    ReceiverSession,
    SessionError,
    SessionObservation,
    SessionState,
    SessionTurnAdapter,
    SessionTurnCall,
    SessionTurnProviderReply,
    SessionTurnResult,
    execute_session_turn,
    prepare_session_turn,
)
from .task_context import PublicTaskContext, validate_state_against_task_context


SESSION_CACHED_CAPSULE_VERIFIER_SHA256 = sha256_text(
    canonical_json(
        {
            "format": "urusilla-session-cached-comprehension-verifier-draft/1",
            "target": "capsule",
            "requires_passed_cold_comprehension": True,
            "requires_exact_live_session_binding": True,
            "deterministic_local": True,
            "model_calls": 0,
            "total_tokens": 0,
        }
    )
)
SESSION_CACHED_TASK_CONTEXT_VERIFIER_SHA256 = sha256_text(
    canonical_json(
        {
            "format": "urusilla-session-cached-comprehension-verifier-draft/1",
            "target": "task-context",
            "requires_passed_cold_comprehension": True,
            "requires_exact_live_session_binding": True,
            "deterministic_local": True,
            "model_calls": 0,
            "total_tokens": 0,
        }
    )
)


class SessionRuntimeError(ValueError):
    """The session-bound hybrid contract was not exact."""


def _context_id(session_binding_sha256: str) -> str:
    return "session:" + session_binding_sha256.removeprefix("sha256:")


def _cached_proof_sha256(
    *,
    attempt: ComprehensionAttempt,
    observation: SessionObservation,
) -> str:
    evidence = attempt.evidence
    assert evidence is not None
    return sha256_text(
        canonical_json(
            {
                "format": "urusilla-session-cached-comprehension-proof-draft/1",
                "comprehension_evidence_sha256": evidence.sha256,
                "session_binding_sha256": observation.session_binding_sha256,
                "model_id": observation.model_id,
                "model_settings_sha256": observation.model_settings_sha256,
                "system_sha256": observation.system_sha256,
                "context_epoch": observation.context_epoch,
                "capsule_sha256": observation.capsule_sha256,
                "task_context_sha256": observation.task_context_sha256,
                "task_profile_sha256": observation.task_profile_sha256,
                "symbol_table_sha256": observation.symbol_table_sha256,
                "last_provider_receipts_sha256": (
                    observation.last_provider_receipts_sha256
                ),
            }
        )
    )

_CACHED_RECEIVER_FIELDS = (
    "comprehension_evidence_sha256",
    "session_binding_sha256",
    "model_id",
    "model_settings_sha256",
    "system_sha256",
    "context_epoch",
    "last_provider_receipts_sha256",
    "context_id",
    "proof_sha256",
    "capabilities",
)


class _CachedReceiverSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _cached_receiver_fingerprint(values: dict[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _CACHED_RECEIVER_FIELDS))
    )


@dataclass(frozen=True)
class SessionCachedReceiver:
    """Factory-sealed capability minted from one live comprehension context."""

    comprehension_evidence_sha256: str
    session_binding_sha256: str
    model_id: str
    model_settings_sha256: str
    system_sha256: str
    context_epoch: str
    last_provider_receipts_sha256: str
    context_id: str
    proof_sha256: str
    capabilities: ReceiverCapabilities
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {
            name: getattr(self, name) for name in _CACHED_RECEIVER_FIELDS
        }
        if (
            not isinstance(self._construction_seal, _CachedReceiverSeal)
            or self._construction_seal.fingerprint
            != _cached_receiver_fingerprint(values)
        ):
            raise SessionRuntimeError(
                "SessionCachedReceiver must be minted from a live session"
            )
        receiver = self.capabilities
        if (
            type(receiver) is not ReceiverCapabilities
            or not receiver.session_only
            or not receiver.capsule_cached_in_same_model_context
            or not receiver.task_context_cached_in_same_model_context
            or receiver.capsule_context_id != self.context_id
            or receiver.task_context_id != self.context_id
            or receiver.capsule_comprehension_sha256 != self.proof_sha256
            or receiver.task_context_comprehension_sha256 != self.proof_sha256
            or receiver.capsule_comprehension_verifier_sha256
            != SESSION_CACHED_CAPSULE_VERIFIER_SHA256
            or receiver.task_context_comprehension_verifier_sha256
            != SESSION_CACHED_TASK_CONTEXT_VERIFIER_SHA256
            or any(
                (
                    receiver.persistence_authorized,
                    receiver.permission_expansion_authorized,
                    receiver.spending_authorized,
                    receiver.external_effects_authorized,
                )
            )
        ):
            raise SessionRuntimeError(
                "cached receiver capabilities differ from the session proof"
            )

    @property
    def binding_sha256(self) -> str:
        return self.proof_sha256

    def capsule_comprehension_verifier(
        self,
        receiver: ReceiverCapabilities,
        capsule: Capsule,
    ) -> LocalArtifactVerification:
        return LocalArtifactVerification(
            passed=(
                type(receiver) is ReceiverCapabilities
                and receiver == self.capabilities
                and type(capsule) is Capsule
                and receiver.capsule_sha256 == capsule.sha256
                and receiver.capsule_comprehension_sha256 == self.proof_sha256
                and receiver.capsule_context_id == self.context_id
                and not any(
                    (
                        receiver.persistence_authorized,
                        receiver.permission_expansion_authorized,
                        receiver.spending_authorized,
                        receiver.external_effects_authorized,
                    )
                )
            ),
            verifier_sha256=SESSION_CACHED_CAPSULE_VERIFIER_SHA256,
            input_binding_sha256=self.proof_sha256,
        )

    def task_context_comprehension_verifier(
        self,
        receiver: ReceiverCapabilities,
        task_context: PublicTaskContext,
    ) -> LocalArtifactVerification:
        return LocalArtifactVerification(
            passed=(
                type(receiver) is ReceiverCapabilities
                and receiver == self.capabilities
                and type(task_context) is PublicTaskContext
                and receiver.task_context_sha256 == task_context.sha256
                and receiver.task_profile_sha256
                == task_context.task_profile_sha256
                and receiver.symbol_table_sha256
                == task_context.symbol_table_sha256
                and receiver.task_context_comprehension_sha256
                == self.proof_sha256
                and receiver.task_context_id == self.context_id
                and not any(
                    (
                        receiver.persistence_authorized,
                        receiver.permission_expansion_authorized,
                        receiver.spending_authorized,
                        receiver.external_effects_authorized,
                    )
                )
            ),
            verifier_sha256=SESSION_CACHED_TASK_CONTEXT_VERIFIER_SHA256,
            input_binding_sha256=self.proof_sha256,
        )


def mint_session_cached_receiver(
    session: ReceiverSession,
    attempt: ComprehensionAttempt,
    observation: SessionObservation,
) -> SessionCachedReceiver:
    """Mint cached capabilities only from the exact active comprehension turn."""

    if type(session) is not ReceiverSession:
        raise SessionRuntimeError("cached receiver requires ReceiverSession")
    if type(attempt) is not ComprehensionAttempt or not attempt.passed:
        raise SessionRuntimeError(
            "cached receiver requires passed cold comprehension"
        )
    if type(observation) is not SessionObservation:
        raise SessionRuntimeError("cached receiver requires exact observation")
    expected = session.expected_observation()
    if observation != expected:
        raise SessionRuntimeError(
            "cached receiver observation differs from the live session"
        )
    snapshot = session.snapshot()
    evidence = attempt.evidence
    assert evidence is not None
    if (
        snapshot.state is not SessionState.ACTIVE
        or snapshot.pending_lease_sha256 is not None
        or snapshot.session_binding_sha256 != observation.session_binding_sha256
        or snapshot.model_id != evidence.model_id
        or snapshot.model_settings_sha256 != evidence.model_settings_sha256
        or snapshot.system_sha256 != sha256_text(attempt.challenge.system_text)
        or snapshot.capsule_sha256 != evidence.capsule_sha256
        or snapshot.task_context_sha256 != evidence.task_context_sha256
        or snapshot.task_profile_sha256 != evidence.task_profile_sha256
        or snapshot.symbol_table_sha256 != evidence.symbol_table_sha256
        or snapshot.comprehension_evidence_sha256 != evidence.sha256
        or observation.context_reset_observed
        or observation.context_compaction_observed
    ):
        raise SessionRuntimeError(
            "cold comprehension and active provider context are not exact"
        )
    context_id = _context_id(snapshot.session_binding_sha256)
    proof_sha256 = _cached_proof_sha256(
        attempt=attempt,
        observation=observation,
    )
    capabilities = ReceiverCapabilities(
        supports_raw=True,
        supports_json=True,
        supports_direct_action_state=True,
        accepts_declarative_capsule=True,
        capsule_comprehension_passed=True,
        capsule_cached_in_same_model_context=True,
        capsule_sha256=evidence.capsule_sha256,
        capsule_context_id=context_id,
        capsule_comprehension_sha256=proof_sha256,
        capsule_comprehension_verifier_sha256=(
            SESSION_CACHED_CAPSULE_VERIFIER_SHA256
        ),
        accepts_public_task_context=True,
        task_context_comprehension_passed=True,
        task_context_cached_in_same_model_context=True,
        task_context_sha256=evidence.task_context_sha256,
        task_profile_sha256=evidence.task_profile_sha256,
        symbol_table_sha256=evidence.symbol_table_sha256,
        task_context_id=context_id,
        task_context_comprehension_sha256=proof_sha256,
        task_context_comprehension_verifier_sha256=(
            SESSION_CACHED_TASK_CONTEXT_VERIFIER_SHA256
        ),
    )
    values: dict[str, object] = {
        "comprehension_evidence_sha256": evidence.sha256,
        "session_binding_sha256": snapshot.session_binding_sha256,
        "model_id": snapshot.model_id,
        "model_settings_sha256": snapshot.model_settings_sha256,
        "system_sha256": snapshot.system_sha256,
        "context_epoch": snapshot.context_epoch,
        "last_provider_receipts_sha256": (
            snapshot.last_provider_receipts_sha256
        ),
        "context_id": context_id,
        "proof_sha256": proof_sha256,
        "capabilities": capabilities,
    }
    return SessionCachedReceiver(
        **values,
        _construction_seal=_CachedReceiverSeal(
            _cached_receiver_fingerprint(values)
        ),
    )


def _validate_primary_request(
    cached: SessionCachedReceiver,
    prepared: PreparedMessage,
    request: DirectReceiverRequest,
) -> tuple[PublicTaskContext, PublicActionState]:
    if type(prepared) is not PreparedMessage:
        raise SessionRuntimeError("optimized input must be PreparedMessage")
    if type(request) is not DirectReceiverRequest:
        raise SessionRuntimeError("optimized input must be DirectReceiverRequest")
    if prepared.route.selected_mode != "action-state":
        raise SessionRuntimeError("session optimized route must be action-state")
    if request is not prepared.route.request:
        raise SessionRuntimeError(
            "session request must be the exact prepared route request"
        )
    if (
        request.mode != "action-state"
        or request.delivery_disposition != "live"
        or request.surface_carrier is not None
        or request.capsule_text is not None
        or request.capsule_included
        or request.task_context_included
        or request.capsule_context_id != cached.context_id
        or request.task_context_id != cached.context_id
        or request.capsule_sha256 != cached.capabilities.capsule_sha256
        or request.comprehension_evidence_sha256 != cached.proof_sha256
        or request.task_comprehension_evidence_sha256 != cached.proof_sha256
        or request.capsule_comprehension_verifier_sha256
        != SESSION_CACHED_CAPSULE_VERIFIER_SHA256
        or request.task_comprehension_verifier_sha256
        != SESSION_CACHED_TASK_CONTEXT_VERIFIER_SHA256
        or request.natural_language_expansion is not None
        or request.decode_before_model
        or request.tools
        or request.memory is not None
        or request.external_effects_authorized
    ):
        raise SessionRuntimeError(
            "optimized request is not the exact direct cached action-state"
        )
    try:
        task_context = PublicTaskContext.from_json(request.task_context_text)
        state = PublicActionState.from_json(request.payload_text)
        validate_state_against_task_context(state, task_context)
    except ValueError as exc:
        raise SessionRuntimeError(
            f"optimized action-state validation failed: {exc}"
        ) from exc
    if (
        state.sha256 != request.payload_sha256
        or task_context.sha256 != request.task_context_sha256
        or task_context.task_profile_sha256 != request.task_profile_sha256
        or task_context.symbol_table_sha256 != request.symbol_table_sha256
        or request.user_data_text != "PAYLOAD\n" + state.canonical_text
    ):
        raise SessionRuntimeError(
            "optimized request content differs from its exact bindings"
        )
    return task_context, state


def _validate_cold_fallback(
    fallback: PreparedMessage,
    *,
    expected_source_sha256: str | None = None,
    expected_capsule_sha256: str | None = None,
    expected_task_context_sha256: str | None = None,
    expected_mode: str | None = None,
    expected_payload_sha256: str | None = None,
) -> DirectReceiverRequest:
    if type(fallback) is not PreparedMessage:
        raise SessionRuntimeError("fallback must be PreparedMessage")
    request = fallback.route.request
    if (
        fallback.route.selected_mode not in {"raw", "json"}
        or request.mode != fallback.route.selected_mode
        or request is not fallback.route.request
        or request.delivery_disposition != "live"
        or not request.task_context_included
        or request.task_context_id is not None
        or request.task_comprehension_evidence_sha256 is not None
        or request.task_comprehension_verifier_sha256 is not None
        or request.capsule_text is not None
        or request.capsule_sha256 is not None
        or request.capsule_included
        or request.capsule_context_id is not None
        or request.comprehension_evidence_sha256 is not None
        or request.capsule_comprehension_verifier_sha256 is not None
        or request.surface_carrier is not None
        or request.natural_language_expansion is not None
        or request.decode_before_model
        or request.tools
        or request.memory is not None
        or request.external_effects_authorized
    ):
        raise SessionRuntimeError(
            "fallback is not an exact cold raw/JSON prepared request"
        )
    PublicTaskContext.from_json(request.task_context_text)
    raw = next(
        (
            item.request
            for item in fallback.route.candidates
            if item.mode == "raw" and item.request is not None
        ),
        None,
    )
    if raw is None or source_text_sha256(raw.payload_text) != fallback.route.source_sha256:
        raise SessionRuntimeError("fallback lost its exact source text")
    checks = (
        (expected_source_sha256, fallback.route.source_sha256),
        (expected_capsule_sha256, fallback.route.capsule_sha256),
        (expected_task_context_sha256, request.task_context_sha256),
        (expected_mode, request.mode),
        (expected_payload_sha256, request.payload_sha256),
    )
    if any(expected is not None and expected != actual for expected, actual in checks):
        raise SessionRuntimeError(
            "cold fallback differs from the optimized route baseline"
        )
    return request


_SESSION_PLAN_FIELDS = (
    "cached_receiver",
    "optimized",
    "primary_request",
    "fallback",
    "optimized_execution_binding_sha256",
    "primary_request_binding_sha256",
    "fallback_execution_binding_sha256",
)


class _SessionPlanSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _session_plan_fingerprint(values: dict[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _SESSION_PLAN_FIELDS))
    )


@dataclass(frozen=True)
class SessionBoundPreparedMessage:
    """One validated hot action-state request plus one cold baseline."""

    cached_receiver: SessionCachedReceiver
    optimized: PreparedMessage
    primary_request: DirectReceiverRequest
    fallback: PreparedMessage
    optimized_execution_binding_sha256: str
    primary_request_binding_sha256: str
    fallback_execution_binding_sha256: str
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {name: getattr(self, name) for name in _SESSION_PLAN_FIELDS}
        if (
            not isinstance(self._construction_seal, _SessionPlanSeal)
            or self._construction_seal.fingerprint
            != _session_plan_fingerprint(values)
        ):
            raise SessionRuntimeError(
                "SessionBoundPreparedMessage must be created by its binder"
            )

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "format": "urusilla-session-bound-prepared-message-draft/1",
                    "cached_receiver_sha256": (
                        self.cached_receiver.binding_sha256
                    ),
                    "optimized_execution_binding_sha256": (
                        self.optimized_execution_binding_sha256
                    ),
                    "primary_request_binding_sha256": (
                        self.primary_request_binding_sha256
                    ),
                    "fallback_execution_binding_sha256": (
                        self.fallback_execution_binding_sha256
                    ),
                }
            )
        )


def bind_prepared_message_to_session(
    cached_receiver: SessionCachedReceiver,
    optimized: PreparedMessage,
    fallback: PreparedMessage,
    *,
    request: DirectReceiverRequest | None = None,
) -> SessionBoundPreparedMessage:
    """Bind only one exact prepared action request and its cold baseline."""

    if type(cached_receiver) is not SessionCachedReceiver:
        raise SessionRuntimeError("session binder requires cached receiver proof")
    primary = optimized.route.request if request is None else request
    _validate_primary_request(cached_receiver, optimized, primary)
    baseline = next(
        (
            item.request
            for item in optimized.route.candidates
            if item.mode == optimized.route.best_baseline_mode
            and item.request is not None
        ),
        None,
    )
    if baseline is None:
        raise SessionRuntimeError("optimized route lost its baseline candidate")
    _validate_cold_fallback(
        fallback,
        expected_source_sha256=optimized.route.source_sha256,
        expected_capsule_sha256=optimized.route.capsule_sha256,
        expected_task_context_sha256=primary.task_context_sha256,
        expected_mode=optimized.route.best_baseline_mode,
        expected_payload_sha256=baseline.payload_sha256,
    )
    values: dict[str, object] = {
        "cached_receiver": cached_receiver,
        "optimized": optimized,
        "primary_request": primary,
        "fallback": fallback,
        "optimized_execution_binding_sha256": (
            optimized.execution_binding_sha256
        ),
        "primary_request_binding_sha256": primary.binding_sha256,
        "fallback_execution_binding_sha256": (
            fallback.execution_binding_sha256
        ),
    }
    return SessionBoundPreparedMessage(
        **values,
        _construction_seal=_SessionPlanSeal(_session_plan_fingerprint(values)),
    )


class _CapturingSessionAdapter:
    def __init__(self, adapter: SessionTurnAdapter) -> None:
        self._adapter = adapter
        self.reply: SessionTurnProviderReply | None = None

    def complete_session_turn(
        self,
        raw_provider_handle: object,
        call: SessionTurnCall,
    ) -> SessionTurnProviderReply:
        reply = self._adapter.complete_session_turn(raw_provider_handle, call)
        if type(reply) is SessionTurnProviderReply:
            self.reply = reply
        return reply


def _validate_output(
    reply: ReceiverModelReply,
    request: DirectReceiverRequest,
    source_sha256: str,
    validator: Callable[[OutputValidationInput], LocalOutputValidation] | None,
) -> bool:
    if validator is None:
        return False
    task_context = PublicTaskContext.from_json(request.task_context_text)
    item = OutputValidationInput(
        source_sha256=source_sha256,
        task_context_sha256=request.task_context_sha256,
        task_profile_sha256=request.task_profile_sha256,
        route_mode=request.mode,
        payload_sha256=request.payload_sha256,
        output_text=reply.text,
        output_sha256=sha256_text(reply.text),
    )
    try:
        result = validator(item)
    except Exception:
        return False
    return bool(
        type(result) is LocalOutputValidation
        and result.valid
        and result.input_binding_sha256 == item.binding_sha256
        and result.validator_sha256 == task_context.output_validator_sha256
    )


_SESSION_EXECUTION_FIELDS = (
    "status",
    "attempt",
    "plan",
    "fallback_prepared",
    "optimized_failure",
    "primary_result",
    "primary_reply",
    "fallback_execution",
    "final_mode",
    "comprehension_calls",
    "primary_calls",
    "fallback_calls",
    "primary_output_valid",
    "output_valid",
    "safely_completed",
    "optimized_path_invalidated",
    "output_discard_required",
    "observed_comprehension_and_receiver_tokens",
    "usage_complete",
    "tools_used",
    "persistence_created",
    "permission_expanded",
    "spending_authority_created",
    "external_effects_performed",
)


class _SessionExecutionSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _session_execution_fingerprint(values: dict[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _SESSION_EXECUTION_FIELDS))
    )


@dataclass(frozen=True)
class SessionBoundExecution:
    """Sealed terminal result; a failed optimized output is never live."""

    status: str
    attempt: ComprehensionAttempt
    plan: SessionBoundPreparedMessage | None
    fallback_prepared: PreparedMessage
    optimized_failure: str | None
    primary_result: SessionTurnResult | None
    primary_reply: ReceiverModelReply | None
    fallback_execution: ReceiverExecution | None
    final_mode: str
    comprehension_calls: int
    primary_calls: int
    fallback_calls: int
    primary_output_valid: bool | None
    output_valid: bool
    safely_completed: bool
    optimized_path_invalidated: bool
    output_discard_required: bool
    observed_comprehension_and_receiver_tokens: int | None
    usage_complete: bool
    tools_used: bool = False
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {name: getattr(self, name) for name in _SESSION_EXECUTION_FIELDS}
        if (
            not isinstance(self._construction_seal, _SessionExecutionSeal)
            or self._construction_seal.fingerprint
            != _session_execution_fingerprint(values)
        ):
            raise SessionRuntimeError(
                "SessionBoundExecution must be created by the bounded executor"
            )
        if self.status not in {"optimized-completed", "fallback-completed", "failed"}:
            raise SessionRuntimeError("session execution status is unknown")
        if self.comprehension_calls != self.attempt.calls:
            raise SessionRuntimeError("comprehension call accounting differs")
        if self.primary_calls not in {0, 1} or self.fallback_calls not in {0, 1}:
            raise SessionRuntimeError("receiver call accounting is invalid")
        if any(
            (
                self.tools_used,
                self.persistence_created,
                self.permission_expanded,
                self.spending_authority_created,
                self.external_effects_performed,
            )
        ):
            raise SessionRuntimeError(
                "session-bound execution crossed a prohibited boundary"
            )
        if self.status == "optimized-completed":
            if (
                self.plan is None
                or self.optimized_failure is not None
                or self.primary_result is None
                or self.primary_reply is None
                or self.fallback_execution is not None
                or self.final_mode != "action-state"
                or self.primary_calls != 1
                or self.fallback_calls != 0
                or self.primary_output_valid is not True
                or not self.output_valid
                or not self.safely_completed
                or self.optimized_path_invalidated
                or self.output_discard_required
            ):
                raise SessionRuntimeError("optimized terminal result is inconsistent")
        else:
            if (
                type(self.optimized_failure) is not str
                or not self.optimized_failure
                or not self.optimized_path_invalidated
                or self.fallback_execution is None
                or self.final_mode not in {"raw", "json"}
                or self.fallback_calls != self.fallback_execution.calls
                or self.output_discard_required == self.safely_completed
                or self.output_valid != self.safely_completed
            ):
                raise SessionRuntimeError("fallback terminal result is inconsistent")
            if self.status == "fallback-completed" and not self.safely_completed:
                raise SessionRuntimeError("fallback-completed must be safe")
            if self.status == "failed" and self.safely_completed:
                raise SessionRuntimeError("failed result cannot be safe")
        if self.usage_complete is not (
            self.observed_comprehension_and_receiver_tokens is not None
        ):
            raise SessionRuntimeError("session execution usage completeness differs")

    @property
    def receiver_calls(self) -> int:
        return self.primary_calls + self.fallback_calls


def _make_execution(**values: object) -> SessionBoundExecution:
    observed = values["observed_comprehension_and_receiver_tokens"]
    values["usage_complete"] = observed is not None
    for name in (
        "tools_used",
        "persistence_created",
        "permission_expanded",
        "spending_authority_created",
        "external_effects_performed",
    ):
        values[name] = False
    fingerprint_values = {
        name: values[name] for name in _SESSION_EXECUTION_FIELDS
    }
    return SessionBoundExecution(
        **values,
        _construction_seal=_SessionExecutionSeal(
            _session_execution_fingerprint(fingerprint_values)
        ),
    )


def _observed_tokens(
    attempt: ComprehensionAttempt,
    *,
    primary_calls: int,
    primary_reply: ReceiverModelReply | None,
    fallback: ReceiverExecution | None,
) -> int | None:
    values: list[int] = []
    if attempt.total_tokens is None:
        return None
    values.append(attempt.total_tokens)
    if primary_calls:
        if primary_reply is None:
            return None
        values.append(primary_reply.provider_total_tokens)
    if fallback is not None:
        if fallback.total_tokens is None:
            return None
        values.append(fallback.total_tokens)
    return sum(values)


def _invalidate_session(session: ReceiverSession | None, reason: str) -> None:
    if type(session) is ReceiverSession and session.state is SessionState.ACTIVE:
        session._invalidate(reason)


def _run_fallback(
    *,
    attempt: ComprehensionAttempt,
    plan: SessionBoundPreparedMessage | None,
    fallback_prepared: PreparedMessage,
    fallback_adapter: ReceiverModelAdapter,
    output_validator: Callable[[OutputValidationInput], LocalOutputValidation]
    | None,
    optimized_failure: str,
    primary_calls: int,
    primary_result: SessionTurnResult | None,
    primary_reply: ReceiverModelReply | None,
    primary_output_valid: bool | None,
) -> SessionBoundExecution:
    fallback_request = _validate_cold_fallback(fallback_prepared)
    fallback_execution = execute_receiver(fallback_request, fallback_adapter)
    fallback_valid = bool(
        fallback_execution.status == "completed"
        and fallback_execution.reply is not None
        and _validate_output(
            fallback_execution.reply,
            fallback_request,
            fallback_prepared.route.source_sha256,
            output_validator,
        )
    )
    return _make_execution(
        status="fallback-completed" if fallback_valid else "failed",
        attempt=attempt,
        plan=plan,
        fallback_prepared=fallback_prepared,
        optimized_failure=optimized_failure,
        primary_result=primary_result,
        primary_reply=primary_reply,
        fallback_execution=fallback_execution,
        final_mode=fallback_request.mode,
        comprehension_calls=attempt.calls,
        primary_calls=primary_calls,
        fallback_calls=fallback_execution.calls,
        primary_output_valid=primary_output_valid,
        output_valid=fallback_valid,
        safely_completed=fallback_valid,
        optimized_path_invalidated=True,
        output_discard_required=not fallback_valid,
        observed_comprehension_and_receiver_tokens=_observed_tokens(
            attempt,
            primary_calls=primary_calls,
            primary_reply=primary_reply,
            fallback=fallback_execution,
        ),
    )


def execute_session_bound_hybrid(
    attempt: ComprehensionAttempt,
    fallback_prepared: PreparedMessage,
    fallback_adapter: ReceiverModelAdapter,
    *,
    plan: SessionBoundPreparedMessage | None = None,
    session: ReceiverSession | None = None,
    observation: SessionObservation | None = None,
    session_adapter: SessionTurnAdapter | None = None,
    output_validator: Callable[[OutputValidationInput], LocalOutputValidation]
    | None,
) -> SessionBoundExecution:
    """Run one hot action-state turn or its pre-bound cold baseline.

    Failed comprehension never produces cached capabilities.  A failed or
    unavailable optimized path therefore takes the baseline with zero optimized
    receiver calls.  Once an optimized call is attempted, any context, adapter,
    receipt, boundary, or output failure invalidates that session and only the
    independently validated fallback output may become live.
    """

    if type(attempt) is not ComprehensionAttempt:
        raise SessionRuntimeError("execution requires ComprehensionAttempt")
    fallback_request = _validate_cold_fallback(fallback_prepared)
    if not callable(getattr(fallback_adapter, "complete", None)):
        raise SessionRuntimeError("fallback adapter must provide complete")
    if not attempt.passed:
        return _run_fallback(
            attempt=attempt,
            plan=None,
            fallback_prepared=fallback_prepared,
            fallback_adapter=fallback_adapter,
            output_validator=output_validator,
            optimized_failure=f"comprehension:{attempt.failure}",
            primary_calls=0,
            primary_result=None,
            primary_reply=None,
            primary_output_valid=None,
        )

    if (
        type(plan) is not SessionBoundPreparedMessage
        or type(session) is not ReceiverSession
        or type(observation) is not SessionObservation
        or not callable(getattr(session_adapter, "complete_session_turn", None))
    ):
        _invalidate_session(session, "session-binding-unavailable")
        return _run_fallback(
            attempt=attempt,
            plan=plan if type(plan) is SessionBoundPreparedMessage else None,
            fallback_prepared=fallback_prepared,
            fallback_adapter=fallback_adapter,
            output_validator=output_validator,
            optimized_failure="session-binding-unavailable",
            primary_calls=0,
            primary_result=None,
            primary_reply=None,
            primary_output_valid=None,
        )
    if plan.fallback != fallback_prepared:
        raise SessionRuntimeError("executor fallback differs from bound plan")
    evidence = attempt.evidence
    assert evidence is not None
    if plan.cached_receiver.comprehension_evidence_sha256 != evidence.sha256:
        raise SessionRuntimeError("executor attempt differs from session proof")

    try:
        _validate_primary_request(
            plan.cached_receiver,
            plan.optimized,
            plan.primary_request,
        )
        if (
            plan.optimized_execution_binding_sha256
            != plan.optimized.execution_binding_sha256
            or plan.primary_request_binding_sha256
            != plan.primary_request.binding_sha256
            or plan.fallback_execution_binding_sha256
            != fallback_prepared.execution_binding_sha256
            or session.state is not SessionState.ACTIVE
            or observation != session.expected_observation()
            or observation.session_binding_sha256
            != plan.cached_receiver.session_binding_sha256
            or observation.context_epoch != plan.cached_receiver.context_epoch
            or observation.system_sha256 != plan.cached_receiver.system_sha256
            or observation.last_provider_receipts_sha256
            != plan.cached_receiver.last_provider_receipts_sha256
        ):
            raise SessionRuntimeError("session or prepared binding changed")
    except (SessionError, SessionRuntimeError, ValueError):
        _invalidate_session(session, "session-primary-preflight-failed")
        return _run_fallback(
            attempt=attempt,
            plan=plan,
            fallback_prepared=fallback_prepared,
            fallback_adapter=fallback_adapter,
            output_validator=output_validator,
            optimized_failure="session-primary-preflight-failed",
            primary_calls=0,
            primary_result=None,
            primary_reply=None,
            primary_output_valid=None,
        )

    try:
        lease = prepare_session_turn(
            session,
            plan.primary_request.user_data_text,
            maximum_total_tokens=(
                plan.primary_request.maximum_total_tokens or 1
            ),
            observation=observation,
        )
    except SessionError:
        return _run_fallback(
            attempt=attempt,
            plan=plan,
            fallback_prepared=fallback_prepared,
            fallback_adapter=fallback_adapter,
            output_validator=output_validator,
            optimized_failure=(
                session.invalidation_reason or "session-context-mismatch"
            ),
            primary_calls=0,
            primary_result=None,
            primary_reply=None,
            primary_output_valid=None,
        )

    capturing = _CapturingSessionAdapter(session_adapter)
    try:
        primary_result = execute_session_turn(session, lease, capturing)
    except SessionError:
        return _run_fallback(
            attempt=attempt,
            plan=plan,
            fallback_prepared=fallback_prepared,
            fallback_adapter=fallback_adapter,
            output_validator=output_validator,
            optimized_failure=(
                session.invalidation_reason or "session-adapter-failed"
            ),
            primary_calls=1,
            primary_result=None,
            primary_reply=capturing.reply.reply if capturing.reply else None,
            primary_output_valid=False,
        )

    provider_reply = capturing.reply
    primary_reply = provider_reply.reply if provider_reply is not None else None
    primary_valid = bool(
        primary_reply is not None
        and primary_result.response_sha256 == sha256_text(primary_reply.text)
        and _validate_output(
            primary_reply,
            plan.primary_request,
            plan.optimized.route.source_sha256,
            output_validator,
        )
    )
    if not primary_valid:
        _invalidate_session(session, "session-primary-output-invalid")
        return _run_fallback(
            attempt=attempt,
            plan=plan,
            fallback_prepared=fallback_prepared,
            fallback_adapter=fallback_adapter,
            output_validator=output_validator,
            optimized_failure="session-primary-output-invalid",
            primary_calls=1,
            primary_result=primary_result,
            primary_reply=primary_reply,
            primary_output_valid=False,
        )

    assert primary_reply is not None
    return _make_execution(
        status="optimized-completed",
        attempt=attempt,
        plan=plan,
        fallback_prepared=fallback_prepared,
        optimized_failure=None,
        primary_result=primary_result,
        primary_reply=primary_reply,
        fallback_execution=None,
        final_mode="action-state",
        comprehension_calls=attempt.calls,
        primary_calls=1,
        fallback_calls=0,
        primary_output_valid=True,
        output_valid=True,
        safely_completed=True,
        optimized_path_invalidated=False,
        output_discard_required=False,
        observed_comprehension_and_receiver_tokens=_observed_tokens(
            attempt,
            primary_calls=1,
            primary_reply=primary_reply,
            fallback=None,
        ),
    )
