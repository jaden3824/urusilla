"""Provider-captured direct receiver execution without prose re-expansion.

The ordinary receiver adapter is intentionally convenient and diagnostic: it
returns a reply, but cannot prove which role-separated messages reached a
provider.  This module adds a stricter, separate path that requires the adapter
to return an exact transmission capture alongside the reply.  A mismatch is a
hard failure, including any adapter-side conversion of an action-state payload
back into natural-language prose.

The capture is still caller supplied.  Hash consistency does not authenticate
the provider, its token usage, or the adapter implementation.  Every artifact
therefore remains explicitly ineligible for a study claim until a later receipt
layer resolves and authenticates the capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import inspect
import re
from typing import Any, Protocol

from .canonical import canonical_json, sha256_text, strict_json_loads
from .errors import ReceiverError
from .receiver import DirectReceiverRequest, ReceiverModelReply


DIRECT_REQUEST_PREIMAGE_SCHEMA = (
    "urusilla-hybrid-direct-receiver-request-preimage/1"
)
PROVIDER_MESSAGES_SCHEMA = "urusilla-hybrid-provider-messages/1"
PROVIDER_REQUEST_CAPTURE_SCHEMA = (
    "urusilla-hybrid-provider-request-capture/1"
)
RECEIVER_REPLY_PREIMAGE_SCHEMA = (
    "urusilla-hybrid-receiver-model-reply-preimage/1"
)
CAPTURED_RECEIVER_EXECUTION_SCHEMA = (
    "urusilla-hybrid-captured-receiver-execution/1"
)

MAX_PROVIDER_ATTEMPTS = 8
CAPTURE_FAILURE_STAGES = frozenset(
    {"before-dispatch", "transport", "provider", "response-validation"}
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,511}$")


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ReceiverError(f"{label} must be a sha256 reference")
    return value


def _identifier(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise ReceiverError(f"{label} must be a bounded identifier{suffix}")
    return value


def _json_public_value(value: Any) -> Any:
    """Project an exact public dataclass tree into canonical JSON values.

    Private construction seals are intentionally excluded.  All public request
    fields, including nested surface and fidelity artifacts, remain present.
    """

    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) in {tuple, list}:
        return [_json_public_value(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ReceiverError("request preimage contains a non-string key")
        return {key: _json_public_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            item.name: _json_public_value(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
    raise ReceiverError(
        "request preimage contains a non-canonical public value: "
        f"{type(value).__name__}"
    )


def direct_receiver_request_preimage(request: DirectReceiverRequest) -> dict[str, Any]:
    """Return the portable, role-preserving preimage for one exact request."""

    if type(request) is not DirectReceiverRequest:
        raise ReceiverError("captured receiver requires an exact DirectReceiverRequest")
    projected = _json_public_value(request)
    assert type(projected) is dict
    return {
        "schema_version": DIRECT_REQUEST_PREIMAGE_SCHEMA,
        "request_binding_sha256": request.binding_sha256,
        "request": projected,
        "roles": {
            "system": request.base_system_text,
            "user": request.user_data_text,
        },
    }


def direct_receiver_request_preimage_json(request: DirectReceiverRequest) -> str:
    return canonical_json(direct_receiver_request_preimage(request))


def direct_receiver_request_preimage_sha256(request: DirectReceiverRequest) -> str:
    return sha256_text(direct_receiver_request_preimage_json(request))


def provider_messages_preimage(system_text: str, user_text: str) -> dict[str, Any]:
    if type(system_text) is not str or type(user_text) is not str:
        raise ReceiverError("provider messages must be exact text")
    return {
        "schema_version": PROVIDER_MESSAGES_SCHEMA,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
    }


def provider_messages_sha256(system_text: str, user_text: str) -> str:
    return sha256_text(canonical_json(provider_messages_preimage(system_text, user_text)))


def receiver_model_reply_preimage(reply: ReceiverModelReply) -> dict[str, Any]:
    """Return every exact public reply, usage, and boundary field."""

    if type(reply) is not ReceiverModelReply:
        raise ReceiverError("reply preimage requires an exact ReceiverModelReply")
    # Reconstructing runs the reply's validation against post-construction
    # mutation before any evidence is accepted.
    validated = ReceiverModelReply(
        **{
            item.name: object.__getattribute__(reply, item.name)
            for item in fields(ReceiverModelReply)
        }
    )
    return {
        "schema_version": RECEIVER_REPLY_PREIMAGE_SCHEMA,
        "reply": {
            item.name: object.__getattribute__(validated, item.name)
            for item in fields(ReceiverModelReply)
        },
    }


def receiver_model_reply_preimage_json(reply: ReceiverModelReply) -> str:
    return canonical_json(receiver_model_reply_preimage(reply))


def receiver_model_reply_preimage_sha256(reply: ReceiverModelReply) -> str:
    return sha256_text(receiver_model_reply_preimage_json(reply))


@dataclass(frozen=True)
class ProviderRequestCapture:
    """One strict but unauthenticated observation of a provider dispatch."""

    schema_version: str
    status: str
    request_binding_sha256: str
    request_preimage_sha256: str
    request_mode: str
    request_dispatched: bool
    transmitted_system_text: str | None
    transmitted_user_text: str | None
    transmitted_messages_sha256: str | None
    intended_model_visible_sha256: str
    model_id: str | None
    settings_sha256: str
    provider_request_id: str | None
    provider_response_id: str | None
    reply_preimage_sha256: str | None
    attempt_count: int
    retry_count: int
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    reasoning_accounting: str | None
    provider_total_tokens: int | None
    usage_complete: bool
    raw_receipt_sha256: str | None
    failure_stage: str | None
    failure_code: str | None
    tools_used: bool = False
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False
    provider_authenticity_verified: bool = False
    claim_eligible: bool = False

    def __post_init__(self) -> None:
        if type(self) is not ProviderRequestCapture:
            raise ReceiverError("provider capture requires an exact artifact type")
        if (
            type(self.schema_version) is not str
            or self.schema_version != PROVIDER_REQUEST_CAPTURE_SCHEMA
        ):
            raise ReceiverError("provider capture schema differs")
        if type(self.status) is not str or self.status not in {"completed", "failed"}:
            raise ReceiverError("provider capture status is unknown")
        _sha(self.request_binding_sha256, "provider capture request binding")
        _sha(self.request_preimage_sha256, "provider capture request preimage")
        _identifier(self.request_mode, "provider capture request mode")
        _sha(
            self.intended_model_visible_sha256,
            "provider capture intended model-visible digest",
        )
        _sha(self.settings_sha256, "provider capture settings")
        if type(self.request_dispatched) is not bool:
            raise ReceiverError("provider capture dispatch flag must be boolean")
        if type(self.attempt_count) is not int or not 0 <= self.attempt_count <= MAX_PROVIDER_ATTEMPTS:
            raise ReceiverError("provider capture attempt count is invalid")
        if type(self.retry_count) is not int or self.retry_count < 0:
            raise ReceiverError("provider capture retry count is invalid")
        if self.attempt_count == 0:
            if self.retry_count != 0:
                raise ReceiverError("an unattempted capture cannot report retries")
        elif self.retry_count != self.attempt_count - 1:
            raise ReceiverError("provider retries and attempts do not reconcile")
        for name in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "provider_total_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ReceiverError(f"provider capture {name} is invalid")
        for name in (
            "tools_used",
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
            "provider_authenticity_verified",
            "claim_eligible",
        ):
            value = getattr(self, name)
            if type(value) is not bool:
                raise ReceiverError(f"provider capture {name} must be boolean")
            if value:
                raise ReceiverError(f"provider capture crossed a closed boundary: {name}")

        if self.request_dispatched:
            if self.attempt_count < 1:
                raise ReceiverError("a dispatched request requires an attempt")
            if (
                type(self.transmitted_system_text) is not str
                or type(self.transmitted_user_text) is not str
            ):
                raise ReceiverError("a dispatched request requires exact role messages")
            _sha(
                self.transmitted_messages_sha256,
                "provider capture transmitted messages",
            )
            if self.transmitted_messages_sha256 != provider_messages_sha256(
                self.transmitted_system_text,
                self.transmitted_user_text,
            ):
                raise ReceiverError("provider capture message digest differs")
            _identifier(self.model_id, "provider capture model")
            _identifier(
                self.provider_request_id,
                "provider capture request id",
            )
            _identifier(
                self.provider_response_id,
                "provider capture response id",
                nullable=True,
            )
        else:
            if any(
                item is not None
                for item in (
                    self.transmitted_system_text,
                    self.transmitted_user_text,
                    self.transmitted_messages_sha256,
                    self.model_id,
                    self.provider_request_id,
                    self.provider_response_id,
                )
            ):
                raise ReceiverError("an undispatched capture cannot report provider facts")
            if self.attempt_count != 0:
                raise ReceiverError("an undispatched capture cannot report attempts")

        if type(self.usage_complete) is not bool:
            raise ReceiverError("provider capture usage completeness must be boolean")
        if self.status == "completed":
            if not self.request_dispatched:
                raise ReceiverError("a completed capture must be dispatched")
            _identifier(
                self.provider_response_id,
                "completed provider response id",
            )
            _sha(self.reply_preimage_sha256, "completed provider reply preimage")
            _sha(self.raw_receipt_sha256, "completed provider receipt")
            if self.attempt_count != 1 or self.retry_count != 0:
                raise ReceiverError(
                    "completed provider usage requires one unretried attempt"
                )
            if self.failure_stage is not None or self.failure_code is not None:
                raise ReceiverError("a completed capture cannot report failure")
            if not self.usage_complete:
                raise ReceiverError("a completed capture requires complete usage")
            if self.input_tokens is None or self.output_tokens is None or self.provider_total_tokens is None:
                raise ReceiverError("completed provider usage is incomplete")
            if self.reasoning_accounting not in {
                "included-in-output",
                "separately-reported",
                "not-reported",
            }:
                raise ReceiverError("completed reasoning accounting is unknown")
            if self.reasoning_accounting == "not-reported":
                if self.reasoning_tokens is not None:
                    raise ReceiverError("unreported reasoning must remain unknown")
                minimum = self.input_tokens + self.output_tokens
                if self.provider_total_tokens < minimum:
                    raise ReceiverError("provider total is below visible usage")
            elif self.reasoning_accounting == "included-in-output":
                if self.reasoning_tokens is None or self.reasoning_tokens > self.output_tokens:
                    raise ReceiverError("included reasoning is inconsistent")
                if self.provider_total_tokens != self.input_tokens + self.output_tokens:
                    raise ReceiverError("included reasoning total does not reconcile")
            else:
                if self.reasoning_tokens is None:
                    raise ReceiverError("separate reasoning cannot be unknown")
                if self.provider_total_tokens != (
                    self.input_tokens + self.output_tokens + self.reasoning_tokens
                ):
                    raise ReceiverError("separate reasoning total does not reconcile")
        else:
            if self.reply_preimage_sha256 is not None:
                raise ReceiverError("failed provider capture cannot bind a reply")
            if self.failure_stage not in CAPTURE_FAILURE_STAGES:
                raise ReceiverError("failed provider capture stage is invalid")
            _identifier(self.failure_code, "provider capture failure code")
            if self.failure_stage == "before-dispatch" and self.request_dispatched:
                raise ReceiverError("before-dispatch failure cannot report dispatch")
            if self.failure_stage != "before-dispatch" and not self.request_dispatched:
                raise ReceiverError("post-dispatch failure lost its dispatch")
            if self.usage_complete or any(
                item is not None
                for item in (
                    self.input_tokens,
                    self.output_tokens,
                    self.reasoning_tokens,
                    self.reasoning_accounting,
                    self.provider_total_tokens,
                )
            ):
                raise ReceiverError("failed provider usage must remain unknown")
            if self.failure_stage == "before-dispatch" and self.raw_receipt_sha256 is not None:
                raise ReceiverError("before-dispatch failure cannot have a receipt")
            if self.raw_receipt_sha256 is not None:
                _sha(self.raw_receipt_sha256, "failed provider receipt")

    @property
    def value(self) -> dict[str, Any]:
        self.validate()
        return {
            item.name: object.__getattribute__(self, item.name)
            for item in fields(ProviderRequestCapture)
        }

    def validate(self) -> None:
        """Recheck all capture invariants after construction."""

        self.__post_init__()

    @property
    def binding_sha256(self) -> str:
        self.validate()
        return sha256_text(
            canonical_json(
                {
                    item.name: object.__getattribute__(self, item.name)
                    for item in fields(ProviderRequestCapture)
                }
            )
        )


@dataclass(frozen=True)
class CapturedProviderResponse:
    capture: ProviderRequestCapture
    reply: ReceiverModelReply | None

    def __post_init__(self) -> None:
        if type(self.capture) is not ProviderRequestCapture:
            raise ReceiverError("captured provider response requires an exact capture")
        self.capture.validate()
        if self.capture.status == "completed":
            if type(self.reply) is not ReceiverModelReply:
                raise ReceiverError("completed provider capture requires an exact reply")
            receiver_model_reply_preimage(self.reply)
        elif self.reply is not None:
            raise ReceiverError("failed provider capture cannot carry a reply")


class CapturedReceiverAdapter(Protocol):
    """Adapter returning its exact provider transmission and response facts."""

    def complete_captured(self, request: DirectReceiverRequest) -> CapturedProviderResponse:
        ...


@dataclass(frozen=True)
class _CapturedExecutionSeal:
    fingerprint_sha256: str


def _execution_fingerprint(
    *,
    schema_version: str,
    status: str,
    calls: int,
    request_binding_sha256: str,
    request_preimage_sha256: str,
    intended_model_visible_sha256: str,
    capture: ProviderRequestCapture | None,
    reply: ReceiverModelReply | None,
    failure: str | None,
    usage_complete: bool,
    provider_authenticity_verified: bool,
    claim_eligible: bool,
    goal_total_complete: bool,
) -> str:
    """Bind every execution field, using canonical child-artifact bindings."""

    return sha256_text(
        canonical_json(
            {
                "schema_version": schema_version,
                "status": status,
                "calls": calls,
                "request_binding_sha256": request_binding_sha256,
                # The exact canonical preimage text is validated against this
                # digest before the construction seal is accepted.
                "request_preimage_sha256": request_preimage_sha256,
                "intended_model_visible_sha256": intended_model_visible_sha256,
                "capture_binding_sha256": (
                    None if capture is None else capture.binding_sha256
                ),
                "reply_preimage_sha256": (
                    None
                    if reply is None
                    else receiver_model_reply_preimage_sha256(reply)
                ),
                "failure": failure,
                "usage_complete": usage_complete,
                "provider_authenticity_verified": provider_authenticity_verified,
                "claim_eligible": claim_eligible,
                "goal_total_complete": goal_total_complete,
            }
        )
    )


def _validated_execution_request_preimage(
    request_preimage_json: str,
    *,
    request_preimage_sha256: str,
    request_binding_sha256: str,
    intended_model_visible_sha256: str,
) -> dict[str, Any]:
    if type(request_preimage_json) is not str:
        raise ReceiverError("captured execution request preimage must be text")
    if sha256_text(request_preimage_json) != request_preimage_sha256:
        raise ReceiverError("captured execution request preimage differs")
    try:
        preimage = strict_json_loads(request_preimage_json)
    except ValueError as exc:
        raise ReceiverError("captured execution request preimage is invalid") from exc
    if canonical_json(preimage) != request_preimage_json:
        raise ReceiverError("captured execution request preimage is not canonical")
    if type(preimage) is not dict or set(preimage) != {
        "schema_version",
        "request_binding_sha256",
        "request",
        "roles",
    }:
        raise ReceiverError("captured execution request preimage shape differs")
    if preimage["schema_version"] != DIRECT_REQUEST_PREIMAGE_SCHEMA:
        raise ReceiverError("captured execution request preimage schema differs")
    if preimage["request_binding_sha256"] != request_binding_sha256:
        raise ReceiverError("captured execution request binding differs from preimage")
    if type(preimage["request"]) is not dict:
        raise ReceiverError("captured execution request value is invalid")
    roles = preimage["roles"]
    if (
        type(roles) is not dict
        or set(roles) != {"system", "user"}
        or type(roles.get("system")) is not str
        or type(roles.get("user")) is not str
    ):
        raise ReceiverError("captured execution role preimage differs")
    visible_text = "SYSTEM\n" + roles["system"] + "\n\nUSER\n" + roles["user"]
    if sha256_text(visible_text) != intended_model_visible_sha256:
        raise ReceiverError("captured execution model-visible preimage differs")
    return preimage


@dataclass(frozen=True)
class CapturedReceiverExecution:
    schema_version: str
    status: str
    calls: int
    request_binding_sha256: str
    request_preimage_json: str
    request_preimage_sha256: str
    intended_model_visible_sha256: str
    capture: ProviderRequestCapture | None
    reply: ReceiverModelReply | None
    failure: str | None
    usage_complete: bool
    provider_authenticity_verified: bool
    claim_eligible: bool
    goal_total_complete: bool
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self) is not CapturedReceiverExecution:
            raise ReceiverError("captured execution requires an exact artifact type")
        if (
            type(self.schema_version) is not str
            or self.schema_version != CAPTURED_RECEIVER_EXECUTION_SCHEMA
        ):
            raise ReceiverError("captured execution schema differs")
        if type(self.status) is not str or self.status not in {
            "completed",
            "failed",
            "capture-rejected",
            "budget-exceeded",
        }:
            raise ReceiverError("captured execution status is unknown")
        if type(self.calls) is not int or self.calls != 1:
            raise ReceiverError("captured provider execution requires one adapter call")
        _sha(self.request_binding_sha256, "captured execution request binding")
        _sha(self.request_preimage_sha256, "captured execution request preimage")
        _sha(
            self.intended_model_visible_sha256,
            "captured execution model-visible digest",
        )
        request_preimage = _validated_execution_request_preimage(
            self.request_preimage_json,
            request_preimage_sha256=self.request_preimage_sha256,
            request_binding_sha256=self.request_binding_sha256,
            intended_model_visible_sha256=self.intended_model_visible_sha256,
        )
        for name in (
            "usage_complete",
            "provider_authenticity_verified",
            "claim_eligible",
            "goal_total_complete",
        ):
            if type(getattr(self, name)) is not bool:
                raise ReceiverError(f"captured execution {name} must be boolean")
        if any(
            (
                self.provider_authenticity_verified,
                self.claim_eligible,
                self.goal_total_complete,
            )
        ):
            raise ReceiverError("captured execution cannot establish claim authority")

        if self.capture is not None:
            if type(self.capture) is not ProviderRequestCapture:
                raise ReceiverError("captured execution requires an exact capture")
            self.capture.validate()
            if self.capture.request_binding_sha256 != self.request_binding_sha256:
                raise ReceiverError("captured execution and capture request differ")
            if self.capture.request_preimage_sha256 != self.request_preimage_sha256:
                raise ReceiverError("captured execution and capture preimage differ")
            if (
                self.capture.intended_model_visible_sha256
                != self.intended_model_visible_sha256
            ):
                raise ReceiverError("captured execution and capture visibility differ")
            request_value = request_preimage["request"]
            if (
                type(request_value.get("mode")) is not str
                or self.capture.request_mode != request_value["mode"]
            ):
                raise ReceiverError("captured execution and capture route differ")
            if self.capture.request_dispatched and (
                self.capture.transmitted_system_text
                != request_preimage["roles"]["system"]
                or self.capture.transmitted_user_text
                != request_preimage["roles"]["user"]
            ):
                raise ReceiverError("captured execution and transmitted roles differ")
        if self.reply is not None:
            if type(self.reply) is not ReceiverModelReply:
                raise ReceiverError("captured execution requires an exact reply")
            receiver_model_reply_preimage(self.reply)
        if self.capture is not None and self.capture.status == "completed":
            if self.reply is None:
                raise ReceiverError("completed capture requires a bound reply")
            _validate_capture_reply_usage(self.capture, self.reply)

        if self.status == "completed":
            if (
                type(self.capture) is not ProviderRequestCapture
                or self.capture.status != "completed"
                or type(self.reply) is not ReceiverModelReply
                or self.failure is not None
                or not self.usage_complete
            ):
                raise ReceiverError("completed captured execution is inconsistent")
        elif self.status == "budget-exceeded":
            if (
                type(self.capture) is not ProviderRequestCapture
                or self.capture.status != "completed"
                or type(self.reply) is not ReceiverModelReply
                or self.failure != "receiver-token-budget-exceeded"
                or not self.usage_complete
            ):
                raise ReceiverError("budget-exceeded captured execution is inconsistent")
        elif self.status == "failed":
            if (
                self.reply is not None
                or type(self.failure) is not str
                or not self.failure
                or self.usage_complete
            ):
                raise ReceiverError("failed captured execution is inconsistent")
            if (
                self.capture is not None
                and (
                    type(self.capture) is not ProviderRequestCapture
                    or self.capture.status != "failed"
                )
            ):
                raise ReceiverError("failed execution has a non-failure capture")
        elif not (
            self.capture is None
            and self.reply is None
            and type(self.failure) is str
            and self.failure
            and not self.usage_complete
        ):
            raise ReceiverError("rejected captured execution is inconsistent")

        expected_fingerprint = _execution_fingerprint(
            schema_version=self.schema_version,
            status=self.status,
            calls=self.calls,
            request_binding_sha256=self.request_binding_sha256,
            request_preimage_sha256=self.request_preimage_sha256,
            intended_model_visible_sha256=self.intended_model_visible_sha256,
            capture=self.capture,
            reply=self.reply,
            failure=self.failure,
            usage_complete=self.usage_complete,
            provider_authenticity_verified=self.provider_authenticity_verified,
            claim_eligible=self.claim_eligible,
            goal_total_complete=self.goal_total_complete,
        )
        if (
            type(self._construction_seal) is not _CapturedExecutionSeal
            or self._construction_seal.fingerprint_sha256 != expected_fingerprint
        ):
            raise ReceiverError("captured execution construction seal differs")

    def validate(self) -> None:
        """Recheck the complete request/capture/reply integrity chain."""

        self.__post_init__()

    @property
    def binding_sha256(self) -> str:
        self.validate()
        assert type(self._construction_seal) is _CapturedExecutionSeal
        return self._construction_seal.fingerprint_sha256

    @property
    def total_tokens(self) -> int | None:
        self.validate()
        if not self.usage_complete or self.capture is None:
            return None
        return self.capture.provider_total_tokens


def _execution(
    *,
    status: str,
    request_preimage_json: str,
    request_preimage_sha256: str,
    request_binding_sha256: str,
    intended_model_visible_sha256: str,
    capture: ProviderRequestCapture | None,
    reply: ReceiverModelReply | None,
    failure: str | None,
    usage_complete: bool,
) -> CapturedReceiverExecution:
    values = {
        "schema_version": CAPTURED_RECEIVER_EXECUTION_SCHEMA,
        "status": status,
        "calls": 1,
        "request_binding_sha256": request_binding_sha256,
        "request_preimage_json": request_preimage_json,
        "request_preimage_sha256": request_preimage_sha256,
        "intended_model_visible_sha256": intended_model_visible_sha256,
        "capture": capture,
        "reply": reply,
        "failure": failure,
        "usage_complete": usage_complete,
        "provider_authenticity_verified": False,
        "claim_eligible": False,
        "goal_total_complete": False,
    }
    fingerprint = _execution_fingerprint(
        **{
            key: value
            for key, value in values.items()
            if key != "request_preimage_json"
        }
    )
    return CapturedReceiverExecution(
        **values,
        _construction_seal=_CapturedExecutionSeal(fingerprint),
    )


def _copy_reply(reply: ReceiverModelReply) -> ReceiverModelReply:
    if type(reply) is not ReceiverModelReply:
        raise ReceiverError("captured provider reply type is invalid")
    receiver_model_reply_preimage(reply)
    return ReceiverModelReply(
        **{
            item.name: object.__getattribute__(reply, item.name)
            for item in fields(ReceiverModelReply)
        }
    )


def _copy_capture(capture: ProviderRequestCapture) -> ProviderRequestCapture:
    if type(capture) is not ProviderRequestCapture:
        raise ReceiverError("captured provider capture type is invalid")
    capture.validate()
    return ProviderRequestCapture(
        **{
            item.name: object.__getattribute__(capture, item.name)
            for item in fields(ProviderRequestCapture)
        }
    )


def _validate_capture_against_request(
    capture: ProviderRequestCapture,
    request: DirectReceiverRequest,
    *,
    request_binding_sha256: str,
    request_preimage_sha256: str,
    expected_model_id: str,
    expected_settings_sha256: str,
) -> None:
    if capture.request_binding_sha256 != request_binding_sha256:
        raise ReceiverError("captured provider request is replayed from another request")
    if capture.request_preimage_sha256 != request_preimage_sha256:
        raise ReceiverError("captured provider request preimage differs")
    if capture.request_mode != request.mode:
        raise ReceiverError("captured provider route differs")
    if capture.intended_model_visible_sha256 != sha256_text(request.model_visible_text):
        raise ReceiverError("captured intended model-visible digest differs")
    if capture.settings_sha256 != expected_settings_sha256:
        raise ReceiverError("captured provider settings differ")
    if capture.request_dispatched:
        if (
            capture.transmitted_system_text != request.base_system_text
            or capture.transmitted_user_text != request.user_data_text
        ):
            raise ReceiverError("captured provider transmission differs from direct request")
        if capture.model_id != expected_model_id:
            raise ReceiverError("captured provider model differs")


def _validate_capture_reply_usage(
    capture: ProviderRequestCapture,
    reply: ReceiverModelReply,
) -> None:
    if (
        capture.reply_preimage_sha256
        != receiver_model_reply_preimage_sha256(reply)
    ):
        raise ReceiverError("captured provider reply preimage differs")
    if any(
        (
            capture.model_id != reply.model_id,
            capture.input_tokens != reply.input_tokens,
            capture.output_tokens != reply.output_tokens,
            capture.reasoning_tokens != reply.reasoning_tokens,
            capture.reasoning_accounting != reply.reasoning_accounting,
            capture.provider_total_tokens != reply.provider_total_tokens,
            capture.tools_used != reply.tools_used,
            capture.persistence_created != reply.persistence_created,
            capture.permission_expanded != reply.permission_expanded,
            capture.spending_authority_created != reply.spending_authority_created,
            capture.external_effects_performed != reply.external_effects_performed,
        )
    ):
        raise ReceiverError("captured provider usage or boundary facts differ from reply")


def execute_captured_receiver(
    request: DirectReceiverRequest,
    adapter: CapturedReceiverAdapter,
    *,
    expected_model_id: str,
    expected_settings_sha256: str,
) -> CapturedReceiverExecution:
    """Execute one live model request only when exact provider messages are captured."""

    if type(request) is not DirectReceiverRequest:
        raise ReceiverError("captured receiver requires an exact DirectReceiverRequest")
    if not request.model_call_required or request.mode == "silence":
        raise ReceiverError("silence is local and has no captured provider request")
    if request.delivery_disposition != "live":
        raise ReceiverError("captured receiver accepts only live requests")
    _identifier(expected_model_id, "expected captured model")
    _sha(expected_settings_sha256, "expected captured settings")
    try:
        complete_method = inspect.getattr_static(adapter, "complete_captured")
    except Exception as exc:
        raise ReceiverError("captured adapter is not statically inspectable") from exc
    if isinstance(complete_method, (staticmethod, classmethod)):
        complete_method = complete_method.__func__
    if not callable(complete_method):
        raise ReceiverError("captured adapter requires a static method surface")

    request_binding = request.binding_sha256
    request_preimage_json = direct_receiver_request_preimage_json(request)
    if (
        request.binding_sha256 != request_binding
        or direct_receiver_request_preimage_json(request) != request_preimage_json
    ):
        raise ReceiverError("direct request changed while its preimage was captured")
    request_preimage_sha = sha256_text(request_preimage_json)
    intended_model_visible_sha = sha256_text(request.model_visible_text)
    try:
        candidate = adapter.complete_captured(request)
    except Exception:
        try:
            request_changed = (
                request.binding_sha256 != request_binding
                or direct_receiver_request_preimage_json(request)
                != request_preimage_json
            )
        except Exception:
            request_changed = True
        return _execution(
            status="capture-rejected" if request_changed else "failed",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_model_visible_sha,
            capture=None,
            reply=None,
            failure=(
                "captured-adapter-mutated-request"
                if request_changed
                else "captured-adapter-call-failed"
            ),
            usage_complete=False,
        )

    try:
        if (
            request.binding_sha256 != request_binding
            or direct_receiver_request_preimage_json(request) != request_preimage_json
        ):
            raise ReceiverError("captured adapter mutated the direct request")
        if type(candidate) is not CapturedProviderResponse:
            raise ReceiverError("captured adapter response type is invalid")
        original_capture_binding = candidate.capture.binding_sha256
        capture = _copy_capture(candidate.capture)
        if candidate.capture.binding_sha256 != original_capture_binding:
            raise ReceiverError("captured adapter mutated its capture during validation")
        reply = None if candidate.reply is None else _copy_reply(candidate.reply)
        _validate_capture_against_request(
            capture,
            request,
            request_binding_sha256=request_binding,
            request_preimage_sha256=request_preimage_sha,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha256,
        )
        if capture.status == "completed":
            assert reply is not None
            _validate_capture_reply_usage(capture, reply)
    except Exception:
        return _execution(
            status="capture-rejected",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_model_visible_sha,
            capture=None,
            reply=None,
            failure="captured-provider-evidence-invalid",
            usage_complete=False,
        )

    if capture.status == "failed":
        return _execution(
            status="failed",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_model_visible_sha,
            capture=capture,
            reply=None,
            failure=capture.failure_code,
            usage_complete=False,
        )
    assert reply is not None
    if (
        request.maximum_total_tokens is not None
        and reply.provider_total_tokens > request.maximum_total_tokens
    ):
        return _execution(
            status="budget-exceeded",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_model_visible_sha,
            capture=capture,
            reply=reply,
            failure="receiver-token-budget-exceeded",
            usage_complete=True,
        )
    return _execution(
        status="completed",
        request_preimage_json=request_preimage_json,
        request_preimage_sha256=request_preimage_sha,
        request_binding_sha256=request_binding,
        intended_model_visible_sha256=intended_model_visible_sha,
        capture=capture,
        reply=reply,
        failure=None,
        usage_complete=True,
    )


__all__ = [
    "CAPTURED_RECEIVER_EXECUTION_SCHEMA",
    "CAPTURE_FAILURE_STAGES",
    "CapturedProviderResponse",
    "CapturedReceiverAdapter",
    "CapturedReceiverExecution",
    "DIRECT_REQUEST_PREIMAGE_SCHEMA",
    "MAX_PROVIDER_ATTEMPTS",
    "PROVIDER_MESSAGES_SCHEMA",
    "PROVIDER_REQUEST_CAPTURE_SCHEMA",
    "RECEIVER_REPLY_PREIMAGE_SCHEMA",
    "ProviderRequestCapture",
    "direct_receiver_request_preimage",
    "direct_receiver_request_preimage_json",
    "direct_receiver_request_preimage_sha256",
    "execute_captured_receiver",
    "provider_messages_preimage",
    "provider_messages_sha256",
    "receiver_model_reply_preimage",
    "receiver_model_reply_preimage_json",
    "receiver_model_reply_preimage_sha256",
]
