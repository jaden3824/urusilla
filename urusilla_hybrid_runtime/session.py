"""Fail-closed bookkeeping for one same-context receiver session.

This module does not prove that a provider retained a context, that its receipts
are authentic, or that a warm session saves tokens.  It only binds a host's
declared provider context to one successful cold-comprehension attempt and
prevents reuse after a replay, sibling turn, reset, compaction, or binding
mismatch.

The raw provider handle is held inside :class:`ReceiverSession` and is passed
only to the configured adapter.  Public artifacts contain digests and declared
bindings, never the handle.  Reported per-call token counts are retained, but
provider full-history billing and total tokens per safely completed task remain
unknown and therefore ineligible for performance claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from threading import RLock
from typing import Protocol

from .canonical import canonical_json, sha256_text
from .comprehension import (
    ComprehensionAttempt,
    ReceiverModelBinding,
)
from .receiver import ReceiverModelReply


SESSION_BINDING_FORMAT = "urusilla-receiver-session-binding-draft/1"
SESSION_RECEIPTS_FORMAT = "urusilla-provider-receipt-binding-draft/1"
SESSION_OBSERVATION_FORMAT = "urusilla-session-observation-draft/1"
SESSION_LEASE_FORMAT = "urusilla-single-use-session-lease-draft/1"
SESSION_TRANSCRIPT_FORMAT = "urusilla-session-transcript-chain-draft/1"
SESSION_SNAPSHOT_FORMAT = "urusilla-receiver-session-snapshot-draft/1"
SESSION_COST_FORMAT = "urusilla-session-cost-ledger-draft/1"
SESSION_RESULT_FORMAT = "urusilla-session-turn-result-draft/1"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SESSION_NONCE = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$")
_MAX_REQUEST_BYTES = 1_048_576


class SessionError(ValueError):
    """A session transition or exact binding failed closed."""


class SessionState(str, Enum):
    NEW = "NEW"
    OPENING = "OPENING"
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise SessionError(f"{label} must be an exact sha256 digest")
    return value


def _require_context_epoch(value: object) -> str:
    if type(value) is not str or _CONTEXT_EPOCH.fullmatch(value) is None:
        raise SessionError("context_epoch must be an exact bounded identifier")
    return value


def _request_sha256(text: object) -> str:
    if type(text) is not str:
        raise SessionError("session request must be text")
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SessionError("session request is not valid UTF-8") from exc
    if not raw or len(raw) > _MAX_REQUEST_BYTES:
        raise SessionError(
            f"session request must contain 1..{_MAX_REQUEST_BYTES} UTF-8 bytes"
        )
    return sha256_text(text)


@dataclass(frozen=True)
class ProviderReceiptBinding:
    """Host-declared receipt digests; never provider-authenticity proof."""

    request_content_sha256: str
    response_content_sha256: str
    provider_request_receipt_sha256: str
    provider_response_receipt_sha256: str
    provider_context_receipt_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "request_content_sha256",
            "response_content_sha256",
            "provider_request_receipt_sha256",
            "provider_response_receipt_sha256",
            "provider_context_receipt_sha256",
        ):
            _require_sha256(getattr(self, name), f"provider receipts {name}")

    @property
    def provider_authenticity_verified(self) -> bool:
        return False

    def to_object(self) -> dict[str, object]:
        return {
            "format": SESSION_RECEIPTS_FORMAT,
            "request_content_sha256": self.request_content_sha256,
            "response_content_sha256": self.response_content_sha256,
            "provider_request_receipt_sha256": (
                self.provider_request_receipt_sha256
            ),
            "provider_response_receipt_sha256": (
                self.provider_response_receipt_sha256
            ),
            "provider_context_receipt_sha256": (
                self.provider_context_receipt_sha256
            ),
            "provider_authenticity_verified": False,
        }

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class SessionObservation:
    """Exact host observation required before a new turn or clean close."""

    session_binding_sha256: str
    model_id: str
    model_settings_sha256: str
    system_sha256: str
    context_epoch: str
    session_nonce_sha256: str
    next_turn: int
    transcript_chain_sha256: str
    capsule_sha256: str
    task_context_sha256: str
    task_profile_sha256: str
    symbol_table_sha256: str
    comprehension_evidence_sha256: str
    last_provider_receipts_sha256: str
    context_reset_observed: bool = False
    context_compaction_observed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "session_binding_sha256",
            "model_settings_sha256",
            "system_sha256",
            "session_nonce_sha256",
            "transcript_chain_sha256",
            "capsule_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
            "comprehension_evidence_sha256",
            "last_provider_receipts_sha256",
        ):
            _require_sha256(getattr(self, name), f"session observation {name}")
        if type(self.model_id) is not str or not self.model_id:
            raise SessionError("session observation model_id must be non-empty")
        _require_context_epoch(self.context_epoch)
        if type(self.next_turn) is not int or self.next_turn < 1:
            raise SessionError("session observation next_turn must be positive")
        for name in (
            "context_reset_observed",
            "context_compaction_observed",
        ):
            if type(getattr(self, name)) is not bool:
                raise SessionError(f"session observation {name} must be boolean")

    def to_object(self) -> dict[str, object]:
        return {
            "format": SESSION_OBSERVATION_FORMAT,
            "session_binding_sha256": self.session_binding_sha256,
            "model_id": self.model_id,
            "model_settings_sha256": self.model_settings_sha256,
            "system_sha256": self.system_sha256,
            "context_epoch": self.context_epoch,
            "session_nonce_sha256": self.session_nonce_sha256,
            "next_turn": self.next_turn,
            "transcript_chain_sha256": self.transcript_chain_sha256,
            "capsule_sha256": self.capsule_sha256,
            "task_context_sha256": self.task_context_sha256,
            "task_profile_sha256": self.task_profile_sha256,
            "symbol_table_sha256": self.symbol_table_sha256,
            "comprehension_evidence_sha256": (
                self.comprehension_evidence_sha256
            ),
            "last_provider_receipts_sha256": (
                self.last_provider_receipts_sha256
            ),
            "context_reset_observed": self.context_reset_observed,
            "context_compaction_observed": self.context_compaction_observed,
        }


@dataclass(frozen=True)
class SessionTurnLease:
    """Public, single-use lease for exactly one next turn."""

    session_binding_sha256: str
    model_id: str
    model_settings_sha256: str
    system_sha256: str
    context_epoch: str
    session_nonce_sha256: str
    turn: int
    parent_transcript_chain_sha256: str
    capsule_sha256: str
    task_context_sha256: str
    task_profile_sha256: str
    symbol_table_sha256: str
    comprehension_evidence_sha256: str
    previous_provider_receipts_sha256: str
    request_sha256: str
    maximum_total_tokens: int

    def __post_init__(self) -> None:
        for name in (
            "session_binding_sha256",
            "model_settings_sha256",
            "system_sha256",
            "session_nonce_sha256",
            "parent_transcript_chain_sha256",
            "capsule_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
            "comprehension_evidence_sha256",
            "previous_provider_receipts_sha256",
            "request_sha256",
        ):
            _require_sha256(getattr(self, name), f"session lease {name}")
        if type(self.model_id) is not str or not self.model_id:
            raise SessionError("session lease model_id must be non-empty")
        _require_context_epoch(self.context_epoch)
        if type(self.turn) is not int or self.turn < 1:
            raise SessionError("session lease turn must be positive")
        if (
            type(self.maximum_total_tokens) is not int
            or self.maximum_total_tokens <= 0
        ):
            raise SessionError("session lease token ceiling must be positive")

    def to_object(self) -> dict[str, object]:
        return {
            "format": SESSION_LEASE_FORMAT,
            "session_binding_sha256": self.session_binding_sha256,
            "model_id": self.model_id,
            "model_settings_sha256": self.model_settings_sha256,
            "system_sha256": self.system_sha256,
            "context_epoch": self.context_epoch,
            "session_nonce_sha256": self.session_nonce_sha256,
            "turn": self.turn,
            "parent_transcript_chain_sha256": (
                self.parent_transcript_chain_sha256
            ),
            "capsule_sha256": self.capsule_sha256,
            "task_context_sha256": self.task_context_sha256,
            "task_profile_sha256": self.task_profile_sha256,
            "symbol_table_sha256": self.symbol_table_sha256,
            "comprehension_evidence_sha256": (
                self.comprehension_evidence_sha256
            ),
            "previous_provider_receipts_sha256": (
                self.previous_provider_receipts_sha256
            ),
            "request_sha256": self.request_sha256,
            "maximum_total_tokens": self.maximum_total_tokens,
        }

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class SessionTurnCall:
    """Adapter input; the provider handle is deliberately not part of it."""

    lease: SessionTurnLease
    request_text: str

    def __post_init__(self) -> None:
        if type(self.lease) is not SessionTurnLease:
            raise SessionError("session turn call requires an exact lease")
        if _request_sha256(self.request_text) != self.lease.request_sha256:
            raise SessionError("session turn call request differs from its lease")


@dataclass(frozen=True)
class SessionTurnProviderReply:
    """One continued-context reply with exact host-declared context bindings."""

    reply: ReceiverModelReply
    model_settings_sha256: str
    system_sha256: str
    context_epoch: str
    lease_sha256: str
    turn: int
    parent_transcript_chain_sha256: str
    receipts: ProviderReceiptBinding
    context_reset_observed: bool = False
    context_compaction_observed: bool = False

    def __post_init__(self) -> None:
        if type(self.reply) is not ReceiverModelReply:
            raise SessionError("session provider reply must wrap ReceiverModelReply")
        for name in (
            "model_settings_sha256",
            "system_sha256",
            "lease_sha256",
            "parent_transcript_chain_sha256",
        ):
            _require_sha256(getattr(self, name), f"session reply {name}")
        _require_context_epoch(self.context_epoch)
        if type(self.turn) is not int or self.turn < 1:
            raise SessionError("session reply turn must be positive")
        if type(self.receipts) is not ProviderReceiptBinding:
            raise SessionError("session reply requires exact provider receipts")
        for name in (
            "context_reset_observed",
            "context_compaction_observed",
        ):
            if type(getattr(self, name)) is not bool:
                raise SessionError(f"session reply {name} must be boolean")


class SessionTurnAdapter(Protocol):
    """Continue exactly one turn using the private handle supplied by session."""

    def complete_session_turn(
        self,
        raw_provider_handle: object,
        call: SessionTurnCall,
    ) -> SessionTurnProviderReply:
        ...


@dataclass(frozen=True)
class SessionCostLedger:
    """Reported calls only; full-history billing deliberately remains unknown."""

    setup_provider_reported_tokens: int
    turn_provider_reported_tokens: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            type(self.setup_provider_reported_tokens) is not int
            or self.setup_provider_reported_tokens < 0
        ):
            raise SessionError("session setup token count is invalid")
        if type(self.turn_provider_reported_tokens) is not tuple or any(
            type(value) is not int or value < 0
            for value in self.turn_provider_reported_tokens
        ):
            raise SessionError("session turn token counts are invalid")

    @property
    def setup_charge_count(self) -> int:
        return 1

    @property
    def reported_call_total_tokens(self) -> int:
        return self.setup_provider_reported_tokens + sum(
            self.turn_provider_reported_tokens
        )

    @property
    def provider_full_history_billing_tokens(self) -> None:
        return None

    @property
    def total_tokens_per_safely_completed_task(self) -> None:
        return None

    @property
    def total_cost_complete(self) -> bool:
        return False

    @property
    def performance_claim_eligible(self) -> bool:
        return False

    def to_object(self) -> dict[str, object]:
        return {
            "format": SESSION_COST_FORMAT,
            "setup_provider_reported_tokens": (
                self.setup_provider_reported_tokens
            ),
            "setup_charge_count": 1,
            "turn_provider_reported_tokens": list(
                self.turn_provider_reported_tokens
            ),
            "reported_call_total_tokens": self.reported_call_total_tokens,
            "provider_full_history_billing_tokens": None,
            "provider_full_history_billing_accounting": "unknown",
            "total_tokens_per_safely_completed_task": None,
            "total_cost_complete": False,
            "performance_claim_eligible": False,
        }


@dataclass(frozen=True)
class SessionSnapshot:
    state: SessionState
    state_history: tuple[SessionState, ...]
    session_binding_sha256: str
    model_id: str
    model_settings_sha256: str
    system_sha256: str
    context_epoch: str
    session_nonce_sha256: str
    next_turn: int
    transcript_chain_sha256: str
    capsule_sha256: str
    task_context_sha256: str
    task_profile_sha256: str
    symbol_table_sha256: str
    comprehension_evidence_sha256: str
    last_provider_receipts_sha256: str
    pending_lease_sha256: str | None
    invalidation_reason: str | None
    provider_receipt_authenticity_verified: bool
    cost: SessionCostLedger

    def __post_init__(self) -> None:
        if type(self.state) is not SessionState:
            raise SessionError("session snapshot state is invalid")
        if (
            type(self.state_history) is not tuple
            or not self.state_history
            or any(type(value) is not SessionState for value in self.state_history)
            or self.state_history[-1] is not self.state
        ):
            raise SessionError("session snapshot history is invalid")
        for name in (
            "session_binding_sha256",
            "model_settings_sha256",
            "system_sha256",
            "session_nonce_sha256",
            "transcript_chain_sha256",
            "capsule_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
            "comprehension_evidence_sha256",
            "last_provider_receipts_sha256",
        ):
            _require_sha256(getattr(self, name), f"session snapshot {name}")
        if self.pending_lease_sha256 is not None:
            _require_sha256(
                self.pending_lease_sha256,
                "session snapshot pending_lease_sha256",
            )
        if type(self.model_id) is not str or not self.model_id:
            raise SessionError("session snapshot model_id must be non-empty")
        _require_context_epoch(self.context_epoch)
        if type(self.next_turn) is not int or self.next_turn < 1:
            raise SessionError("session snapshot next_turn must be positive")
        if self.state is SessionState.INVALIDATED:
            if type(self.invalidation_reason) is not str or not self.invalidation_reason:
                raise SessionError("invalidated snapshot requires a reason")
        elif self.invalidation_reason is not None:
            raise SessionError("non-invalidated snapshot cannot have a reason")
        if self.provider_receipt_authenticity_verified is not False:
            raise SessionError("provider receipt authenticity is not established")
        if type(self.cost) is not SessionCostLedger:
            raise SessionError("session snapshot cost ledger is invalid")

    def to_object(self) -> dict[str, object]:
        return {
            "format": SESSION_SNAPSHOT_FORMAT,
            "state": self.state.value,
            "state_history": [value.value for value in self.state_history],
            "session_binding_sha256": self.session_binding_sha256,
            "model_id": self.model_id,
            "model_settings_sha256": self.model_settings_sha256,
            "system_sha256": self.system_sha256,
            "context_epoch": self.context_epoch,
            "session_nonce_sha256": self.session_nonce_sha256,
            "next_turn": self.next_turn,
            "transcript_chain_sha256": self.transcript_chain_sha256,
            "capsule_sha256": self.capsule_sha256,
            "task_context_sha256": self.task_context_sha256,
            "task_profile_sha256": self.task_profile_sha256,
            "symbol_table_sha256": self.symbol_table_sha256,
            "comprehension_evidence_sha256": (
                self.comprehension_evidence_sha256
            ),
            "last_provider_receipts_sha256": (
                self.last_provider_receipts_sha256
            ),
            "pending_lease_sha256": self.pending_lease_sha256,
            "invalidation_reason": self.invalidation_reason,
            "provider_receipt_authenticity_verified": False,
            "cost": self.cost.to_object(),
        }

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())


@dataclass(frozen=True)
class SessionTurnResult:
    lease_sha256: str
    response_sha256: str
    provider_receipts_sha256: str
    transcript_chain_sha256: str
    provider_reported_tokens: int
    performance_claim_eligible: bool = False

    def __post_init__(self) -> None:
        for name in (
            "lease_sha256",
            "response_sha256",
            "provider_receipts_sha256",
            "transcript_chain_sha256",
        ):
            _require_sha256(getattr(self, name), f"session result {name}")
        if (
            type(self.provider_reported_tokens) is not int
            or self.provider_reported_tokens < 0
        ):
            raise SessionError("session result token count is invalid")
        if self.performance_claim_eligible is not False:
            raise SessionError("a session turn cannot support a performance claim")

    def to_object(self) -> dict[str, object]:
        return {
            "format": SESSION_RESULT_FORMAT,
            "lease_sha256": self.lease_sha256,
            "response_sha256": self.response_sha256,
            "provider_receipts_sha256": self.provider_receipts_sha256,
            "transcript_chain_sha256": self.transcript_chain_sha256,
            "provider_reported_tokens": self.provider_reported_tokens,
            "performance_claim_eligible": False,
        }


class ReceiverSession:
    """Mutable transition guard with a private provider handle.

    Construct sessions only with :func:`open_receiver_session`.  The object is
    intentionally stateful so two callers cannot both consume the same lease.
    """

    __slots__ = (
        "__raw_provider_handle",
        "_lock",
        "_state",
        "_state_history",
        "_invalidation_reason",
        "_session_binding_sha256",
        "_model_id",
        "_model_settings_sha256",
        "_system_sha256",
        "_context_epoch",
        "_session_nonce_sha256",
        "_next_turn",
        "_transcript_chain_sha256",
        "_capsule_sha256",
        "_task_context_sha256",
        "_task_profile_sha256",
        "_symbol_table_sha256",
        "_comprehension_evidence_sha256",
        "_last_provider_receipts_sha256",
        "_setup_provider_reported_tokens",
        "_turn_provider_reported_tokens",
        "_pending_lease",
        "_pending_call",
        "_consumed_leases",
    )

    def __init__(self) -> None:
        self.__raw_provider_handle: object | None = None
        self._lock = RLock()
        self._state = SessionState.NEW
        self._state_history = [SessionState.NEW]
        self._invalidation_reason: str | None = None
        self._session_binding_sha256 = ""
        self._model_id = ""
        self._model_settings_sha256 = ""
        self._system_sha256 = ""
        self._context_epoch = ""
        self._session_nonce_sha256 = ""
        self._next_turn = 1
        self._transcript_chain_sha256 = ""
        self._capsule_sha256 = ""
        self._task_context_sha256 = ""
        self._task_profile_sha256 = ""
        self._symbol_table_sha256 = ""
        self._comprehension_evidence_sha256 = ""
        self._last_provider_receipts_sha256 = ""
        self._setup_provider_reported_tokens = 0
        self._turn_provider_reported_tokens: list[int] = []
        self._pending_lease: SessionTurnLease | None = None
        self._pending_call: SessionTurnCall | None = None
        self._consumed_leases: set[str] = set()

    def __repr__(self) -> str:
        if self._state in {SessionState.NEW, SessionState.OPENING}:
            return f"ReceiverSession(state={self._state.value!r})"
        return f"ReceiverSession(snapshot={self.snapshot().to_object()!r})"

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def invalidation_reason(self) -> str | None:
        return self._invalidation_reason

    def _transition(self, state: SessionState) -> None:
        allowed = {
            SessionState.NEW: {SessionState.OPENING},
            SessionState.OPENING: {
                SessionState.ACTIVE,
                SessionState.INVALIDATED,
            },
            SessionState.ACTIVE: {
                SessionState.INVALIDATED,
                SessionState.CLOSED,
            },
            SessionState.INVALIDATED: set(),
            SessionState.CLOSED: set(),
        }
        if state not in allowed[self._state]:
            raise SessionError(
                f"invalid session transition: {self._state.value}->{state.value}"
            )
        self._state = state
        self._state_history.append(state)

    def _invalidate(self, reason: str) -> None:
        if self._state is SessionState.INVALIDATED:
            return
        if self._state is SessionState.CLOSED:
            raise SessionError("closed session is terminal")
        self._invalidation_reason = reason
        self._pending_lease = None
        self._pending_call = None
        self.__raw_provider_handle = None
        self._transition(SessionState.INVALIDATED)

    def _fail(self, reason: str, message: str) -> None:
        self._invalidate(reason)
        raise SessionError(message)

    def _binding_object(
        self,
        *,
        opening_provider_receipts_sha256: str,
    ) -> dict[str, object]:
        return {
            "format": SESSION_BINDING_FORMAT,
            "model_id": self._model_id,
            "model_settings_sha256": self._model_settings_sha256,
            "system_sha256": self._system_sha256,
            "context_epoch": self._context_epoch,
            "session_nonce_sha256": self._session_nonce_sha256,
            "capsule_sha256": self._capsule_sha256,
            "task_context_sha256": self._task_context_sha256,
            "task_profile_sha256": self._task_profile_sha256,
            "symbol_table_sha256": self._symbol_table_sha256,
            "comprehension_evidence_sha256": (
                self._comprehension_evidence_sha256
            ),
            "opening_provider_receipts_sha256": (
                opening_provider_receipts_sha256
            ),
            "provider_receipt_authenticity_verified": False,
        }

    def _open(
        self,
        *,
        attempt: ComprehensionAttempt,
        raw_provider_handle: object,
        context_epoch: str,
        session_nonce: str,
        opening_receipts: ProviderReceiptBinding,
    ) -> None:
        with self._lock:
            self._transition(SessionState.OPENING)
            try:
                if type(attempt) is not ComprehensionAttempt or not attempt.passed:
                    raise SessionError(
                        "session opening requires passed comprehension evidence"
                    )
                evidence = attempt.evidence
                assert evidence is not None
                if raw_provider_handle is None:
                    raise SessionError("session provider handle cannot be null")
                _require_context_epoch(context_epoch)
                if (
                    type(session_nonce) is not str
                    or _SESSION_NONCE.fullmatch(session_nonce) is None
                ):
                    raise SessionError(
                        "session_nonce must be 64 lowercase hexadecimal characters"
                    )
                if type(opening_receipts) is not ProviderReceiptBinding:
                    raise SessionError(
                        "session opening requires exact provider receipts"
                    )
                if (
                    opening_receipts.request_content_sha256
                    != attempt.challenge.model_visible_sha256
                    or opening_receipts.response_content_sha256
                    != evidence.output_sha256
                ):
                    raise SessionError(
                        "opening provider receipts differ from comprehension"
                    )

                self._model_id = evidence.model_id
                self._model_settings_sha256 = evidence.model_settings_sha256
                self._system_sha256 = sha256_text(
                    attempt.challenge.system_text
                )
                self._context_epoch = context_epoch
                self._session_nonce_sha256 = sha256_text(
                    "urusilla-session-nonce\x00" + session_nonce
                )
                self._capsule_sha256 = evidence.capsule_sha256
                self._task_context_sha256 = evidence.task_context_sha256
                self._task_profile_sha256 = evidence.task_profile_sha256
                self._symbol_table_sha256 = evidence.symbol_table_sha256
                self._comprehension_evidence_sha256 = evidence.sha256
                self._last_provider_receipts_sha256 = opening_receipts.sha256
                self._setup_provider_reported_tokens = (
                    evidence.provider_total_tokens
                )
                self._session_binding_sha256 = sha256_text(
                    canonical_json(
                        self._binding_object(
                            opening_provider_receipts_sha256=(
                                opening_receipts.sha256
                            )
                        )
                    )
                )
                self._transcript_chain_sha256 = sha256_text(
                    canonical_json(
                        {
                            "format": SESSION_TRANSCRIPT_FORMAT,
                            "event": "opening",
                            "session_binding_sha256": (
                                self._session_binding_sha256
                            ),
                            "turn": 0,
                            "parent_transcript_chain_sha256": None,
                            "request_content_sha256": (
                                opening_receipts.request_content_sha256
                            ),
                            "response_content_sha256": (
                                opening_receipts.response_content_sha256
                            ),
                            "provider_receipts_sha256": (
                                opening_receipts.sha256
                            ),
                        }
                    )
                )
                self.__raw_provider_handle = raw_provider_handle
            except Exception:
                self._invalidate("opening-binding-failed")
                raise
            self._transition(SessionState.ACTIVE)

    def expected_observation(self) -> SessionObservation:
        with self._lock:
            self._require_active()
            return SessionObservation(
                session_binding_sha256=self._session_binding_sha256,
                model_id=self._model_id,
                model_settings_sha256=self._model_settings_sha256,
                system_sha256=self._system_sha256,
                context_epoch=self._context_epoch,
                session_nonce_sha256=self._session_nonce_sha256,
                next_turn=self._next_turn,
                transcript_chain_sha256=self._transcript_chain_sha256,
                capsule_sha256=self._capsule_sha256,
                task_context_sha256=self._task_context_sha256,
                task_profile_sha256=self._task_profile_sha256,
                symbol_table_sha256=self._symbol_table_sha256,
                comprehension_evidence_sha256=(
                    self._comprehension_evidence_sha256
                ),
                last_provider_receipts_sha256=(
                    self._last_provider_receipts_sha256
                ),
            )

    def _require_active(self) -> None:
        if self._state is SessionState.INVALIDATED:
            raise SessionError(
                f"session is invalidated: {self._invalidation_reason}"
            )
        if self._state is SessionState.CLOSED:
            raise SessionError("session is closed")
        if self._state is not SessionState.ACTIVE:
            raise SessionError(f"session is not active: {self._state.value}")

    def _verify_observation(self, observation: SessionObservation) -> None:
        if type(observation) is not SessionObservation:
            self._fail(
                "observation-type-invalid",
                "session requires an exact observation",
            )
        if observation.context_reset_observed:
            self._fail("context-reset", "provider context reset was observed")
        if observation.context_compaction_observed:
            self._fail(
                "context-compaction",
                "provider context compaction was observed",
            )
        expected = self.expected_observation()
        fields = (
            "session_binding_sha256",
            "model_id",
            "model_settings_sha256",
            "system_sha256",
            "context_epoch",
            "session_nonce_sha256",
            "next_turn",
            "transcript_chain_sha256",
            "capsule_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
            "comprehension_evidence_sha256",
            "last_provider_receipts_sha256",
        )
        for name in fields:
            if getattr(observation, name) != getattr(expected, name):
                reason = {
                    "context_epoch": "context-reset",
                    "transcript_chain_sha256": "transcript-mismatch",
                    "next_turn": "turn-mismatch",
                }.get(name, f"{name.replace('_', '-')}-mismatch")
                self._fail(reason, f"session observation differs at {name}")

    def _prepare(
        self,
        request_text: str,
        *,
        maximum_total_tokens: int,
        observation: SessionObservation,
    ) -> SessionTurnLease:
        with self._lock:
            self._require_active()
            if self._pending_lease is not None:
                self._fail(
                    "sibling-turn",
                    "a sibling turn was prepared before the active lease completed",
                )
            self._verify_observation(observation)
            request_sha256 = _request_sha256(request_text)
            if (
                type(maximum_total_tokens) is not int
                or maximum_total_tokens <= 0
            ):
                raise SessionError("maximum_total_tokens must be positive")
            lease = SessionTurnLease(
                session_binding_sha256=self._session_binding_sha256,
                model_id=self._model_id,
                model_settings_sha256=self._model_settings_sha256,
                system_sha256=self._system_sha256,
                context_epoch=self._context_epoch,
                session_nonce_sha256=self._session_nonce_sha256,
                turn=self._next_turn,
                parent_transcript_chain_sha256=(
                    self._transcript_chain_sha256
                ),
                capsule_sha256=self._capsule_sha256,
                task_context_sha256=self._task_context_sha256,
                task_profile_sha256=self._task_profile_sha256,
                symbol_table_sha256=self._symbol_table_sha256,
                comprehension_evidence_sha256=(
                    self._comprehension_evidence_sha256
                ),
                previous_provider_receipts_sha256=(
                    self._last_provider_receipts_sha256
                ),
                request_sha256=request_sha256,
                maximum_total_tokens=maximum_total_tokens,
            )
            self._pending_lease = lease
            self._pending_call = SessionTurnCall(
                lease=lease,
                request_text=request_text,
            )
            return lease

    def _execute(
        self,
        lease: SessionTurnLease,
        adapter: SessionTurnAdapter,
    ) -> SessionTurnResult:
        with self._lock:
            self._require_active()
            if type(lease) is not SessionTurnLease:
                self._fail("lease-type-invalid", "session lease type is invalid")
            if lease.sha256 in self._consumed_leases:
                self._fail("replay", "session lease was already consumed")
            if self._pending_lease is None or self._pending_call is None:
                self._fail("replay", "session has no unconsumed lease")
            if lease != self._pending_lease:
                self._fail(
                    "sibling-turn",
                    "session lease is not the exact pending lease",
                )
            if not callable(getattr(adapter, "complete_session_turn", None)):
                self._fail(
                    "adapter-invalid",
                    "session adapter must provide complete_session_turn",
                )

            call = self._pending_call
            self._consumed_leases.add(lease.sha256)
            self._pending_lease = None
            self._pending_call = None
            handle = self.__raw_provider_handle
            if handle is None:
                self._fail(
                    "provider-handle-missing",
                    "session provider handle is unavailable",
                )
            try:
                reply = adapter.complete_session_turn(handle, call)
            except Exception as exc:
                self._invalidate("adapter-call-failed")
                raise SessionError("session adapter call failed") from exc
            if type(reply) is not SessionTurnProviderReply:
                self._fail(
                    "adapter-reply-type-invalid",
                    "session adapter returned an invalid reply type",
                )
            if reply.context_reset_observed:
                self._fail("context-reset", "provider reported a context reset")
            if reply.context_compaction_observed:
                self._fail(
                    "context-compaction",
                    "provider reported context compaction",
                )

            exact_pairs = (
                ("model_id", reply.reply.model_id, self._model_id),
                (
                    "model_settings_sha256",
                    reply.model_settings_sha256,
                    self._model_settings_sha256,
                ),
                ("system_sha256", reply.system_sha256, self._system_sha256),
                ("context_epoch", reply.context_epoch, self._context_epoch),
                ("lease_sha256", reply.lease_sha256, lease.sha256),
                ("turn", reply.turn, lease.turn),
                (
                    "parent_transcript_chain_sha256",
                    reply.parent_transcript_chain_sha256,
                    lease.parent_transcript_chain_sha256,
                ),
                (
                    "request_content_sha256",
                    reply.receipts.request_content_sha256,
                    lease.request_sha256,
                ),
                (
                    "response_content_sha256",
                    reply.receipts.response_content_sha256,
                    sha256_text(reply.reply.text),
                ),
            )
            for name, actual, expected in exact_pairs:
                if actual != expected:
                    reason = {
                        "context_epoch": "context-reset",
                        "parent_transcript_chain_sha256": (
                            "transcript-mismatch"
                        ),
                        "turn": "turn-mismatch",
                    }.get(name, f"{name.replace('_', '-')}-mismatch")
                    self._fail(reason, f"session reply differs at {name}")
            if reply.reply.provider_total_tokens > lease.maximum_total_tokens:
                self._fail(
                    "token-budget-exceeded",
                    "session reply exceeded the lease token ceiling",
                )

            self._transcript_chain_sha256 = sha256_text(
                canonical_json(
                    {
                        "format": SESSION_TRANSCRIPT_FORMAT,
                        "event": "turn",
                        "session_binding_sha256": (
                            self._session_binding_sha256
                        ),
                        "turn": lease.turn,
                        "parent_transcript_chain_sha256": (
                            lease.parent_transcript_chain_sha256
                        ),
                        "lease_sha256": lease.sha256,
                        "request_content_sha256": lease.request_sha256,
                        "response_content_sha256": (
                            reply.receipts.response_content_sha256
                        ),
                        "provider_receipts_sha256": reply.receipts.sha256,
                    }
                )
            )
            self._last_provider_receipts_sha256 = reply.receipts.sha256
            self._next_turn += 1
            self._turn_provider_reported_tokens.append(
                reply.reply.provider_total_tokens
            )
            return SessionTurnResult(
                lease_sha256=lease.sha256,
                response_sha256=reply.receipts.response_content_sha256,
                provider_receipts_sha256=reply.receipts.sha256,
                transcript_chain_sha256=self._transcript_chain_sha256,
                provider_reported_tokens=reply.reply.provider_total_tokens,
            )

    def _close(self, observation: SessionObservation) -> SessionSnapshot:
        with self._lock:
            self._require_active()
            if self._pending_lease is not None:
                self._fail(
                    "pending-lease-on-close",
                    "cannot close cleanly with an unconsumed lease",
                )
            self._verify_observation(observation)
            self.__raw_provider_handle = None
            self._transition(SessionState.CLOSED)
            return self.snapshot()

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            if self._state in {SessionState.NEW, SessionState.OPENING}:
                raise SessionError("session binding is not yet available")
            return SessionSnapshot(
                state=self._state,
                state_history=tuple(self._state_history),
                session_binding_sha256=self._session_binding_sha256,
                model_id=self._model_id,
                model_settings_sha256=self._model_settings_sha256,
                system_sha256=self._system_sha256,
                context_epoch=self._context_epoch,
                session_nonce_sha256=self._session_nonce_sha256,
                next_turn=self._next_turn,
                transcript_chain_sha256=self._transcript_chain_sha256,
                capsule_sha256=self._capsule_sha256,
                task_context_sha256=self._task_context_sha256,
                task_profile_sha256=self._task_profile_sha256,
                symbol_table_sha256=self._symbol_table_sha256,
                comprehension_evidence_sha256=(
                    self._comprehension_evidence_sha256
                ),
                last_provider_receipts_sha256=(
                    self._last_provider_receipts_sha256
                ),
                pending_lease_sha256=(
                    None
                    if self._pending_lease is None
                    else self._pending_lease.sha256
                ),
                invalidation_reason=self._invalidation_reason,
                provider_receipt_authenticity_verified=False,
                cost=SessionCostLedger(
                    setup_provider_reported_tokens=(
                        self._setup_provider_reported_tokens
                    ),
                    turn_provider_reported_tokens=tuple(
                        self._turn_provider_reported_tokens
                    ),
                ),
            )


def open_receiver_session(
    attempt: ComprehensionAttempt,
    *,
    raw_provider_handle: object,
    context_epoch: str,
    session_nonce: str,
    opening_receipts: ProviderReceiptBinding,
) -> ReceiverSession:
    """Bind one passed cold attempt to one declared live provider context."""

    session = ReceiverSession()
    session._open(
        attempt=attempt,
        raw_provider_handle=raw_provider_handle,
        context_epoch=context_epoch,
        session_nonce=session_nonce,
        opening_receipts=opening_receipts,
    )
    return session


def prepare_session_turn(
    session: ReceiverSession,
    request_text: str,
    *,
    maximum_total_tokens: int,
    observation: SessionObservation,
) -> SessionTurnLease:
    """Reserve the exact next turn; a second reservation invalidates session."""

    if type(session) is not ReceiverSession:
        raise SessionError("prepare_session_turn requires ReceiverSession")
    return session._prepare(
        request_text,
        maximum_total_tokens=maximum_total_tokens,
        observation=observation,
    )


def execute_session_turn(
    session: ReceiverSession,
    lease: SessionTurnLease,
    adapter: SessionTurnAdapter,
) -> SessionTurnResult:
    """Consume one lease exactly once and advance its transcript chain."""

    if type(session) is not ReceiverSession:
        raise SessionError("execute_session_turn requires ReceiverSession")
    return session._execute(lease, adapter)


def close_receiver_session(
    session: ReceiverSession,
    observation: SessionObservation,
) -> SessionSnapshot:
    """Close an active, exactly observed session and discard its private handle."""

    if type(session) is not ReceiverSession:
        raise SessionError("close_receiver_session requires ReceiverSession")
    return session._close(observation)
