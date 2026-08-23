"""Provider-captured sender compilation with exact role preservation.

The ordinary :class:`~urusilla_hybrid_runtime.sender.StructuredCompiler`
interface intentionally exposes only the model reply needed by the runtime.
This separate boundary retains the exact sender prompt, provider transmission,
reply, normalized usage, and prohibited-effect observations.  It is suitable
for later structural evidence assembly, but the capture remains caller
supplied and therefore authenticates neither a provider nor an operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import inspect
import re
from typing import Any, Protocol

from .canonical import canonical_json, sha256_text, strict_json_loads
from .captured_receiver import (
    ProviderRequestCapture,
    provider_messages_sha256,
)
from .errors import SenderError
from .sender import ModelReply, SenderPrompt, source_text_sha256
from .task_context import PublicTaskContext


SENDER_PROMPT_BINDING_SCHEMA = "urusilla-hybrid-sender-prompt-binding/1"
SENDER_PROMPT_PREIMAGE_SCHEMA = "urusilla-hybrid-sender-prompt-preimage/1"
COMPILER_REPLY_PREIMAGE_SCHEMA = "urusilla-hybrid-compiler-reply-preimage/1"
CAPTURED_COMPILER_EXECUTION_SCHEMA = (
    "urusilla-hybrid-captured-compiler-execution/2"
)
COMPILER_REQUEST_MODE = "sender-compiler"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,511}$")
_PROMPT_FIELDS = tuple(item.name for item in fields(SenderPrompt))
_USER_FIELDS = {
    "operation",
    "source_sha256",
    "source_text",
    "task_context_sha256",
    "task_profile_sha256",
    "symbol_table_sha256",
    "task_context",
    "cached_task_context_binding",
}


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise SenderError(f"{label} must be a sha256 reference")
    return value


def _identifier(value: Any, label: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise SenderError(f"{label} must be a bounded identifier")
    return value


def _prompt_values(prompt: SenderPrompt) -> dict[str, Any]:
    """Validate and detach every exact public sender-prompt field."""

    if type(prompt) is not SenderPrompt:
        raise SenderError("captured compiler requires an exact SenderPrompt")
    values = {
        name: object.__getattribute__(prompt, name) for name in _PROMPT_FIELDS
    }
    for name in ("system_text", "user_text"):
        value = values[name]
        if type(value) is not str or not value:
            raise SenderError(f"sender prompt {name} must be non-empty text")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise SenderError(f"sender prompt {name} is not UTF-8") from exc
    for name in (
        "capsule_sha256",
        "task_context_sha256",
        "task_profile_sha256",
        "symbol_table_sha256",
        "source_sha256",
    ):
        _sha(values[name], f"sender prompt {name}")
    for name in ("capsule_included", "task_context_included"):
        if type(values[name]) is not bool:
            raise SenderError(f"sender prompt {name} must be boolean")
    if values["capsule_included"] is not values["task_context_included"]:
        raise SenderError("sender prompt Capsule and task-context modes differ")
    ceiling = values["maximum_total_tokens"]
    if ceiling is not None and (type(ceiling) is not int or ceiling <= 0):
        raise SenderError("sender prompt token ceiling is invalid")

    cached_names = (
        "capsule_context_id",
        "capsule_comprehension_evidence_sha256",
        "task_comprehension_evidence_sha256",
    )
    if values["capsule_included"]:
        if any(values[name] is not None for name in cached_names):
            raise SenderError("cold sender prompt carries cached-context claims")
    else:
        _identifier(values["capsule_context_id"], "sender prompt context id")
        for name in cached_names[1:]:
            _sha(values[name], f"sender prompt {name}")

    try:
        user = strict_json_loads(values["user_text"])
    except ValueError as exc:
        raise SenderError("sender prompt user preimage is invalid") from exc
    if type(user) is not dict or set(user) != _USER_FIELDS:
        raise SenderError("sender prompt user preimage fields differ")
    if canonical_json(user) != values["user_text"]:
        raise SenderError("sender prompt user preimage is not canonical")
    if (
        user["operation"] != "compile-public-action-state"
        or type(user["source_text"]) is not str
        or source_text_sha256(user["source_text"]) != values["source_sha256"]
        or user["source_sha256"] != values["source_sha256"]
        or user["task_context_sha256"] != values["task_context_sha256"]
        or user["task_profile_sha256"] != values["task_profile_sha256"]
        or user["symbol_table_sha256"] != values["symbol_table_sha256"]
    ):
        raise SenderError("sender prompt user preimage binding differs")
    if values["task_context_included"]:
        if user["cached_task_context_binding"] is not None:
            raise SenderError("cold sender prompt carries a cached user binding")
        try:
            task_context = PublicTaskContext.from_json(
                canonical_json(user["task_context"])
            )
        except ValueError as exc:
            raise SenderError("sender prompt task context is invalid") from exc
        if (
            task_context.sha256 != values["task_context_sha256"]
            or task_context.task_profile_sha256
            != values["task_profile_sha256"]
            or task_context.symbol_table_sha256
            != values["symbol_table_sha256"]
        ):
            raise SenderError("sender prompt task-context binding differs")
    else:
        binding = user["cached_task_context_binding"]
        if (
            user["task_context"] is not None
            or type(binding) is not dict
            or set(binding) != {"context_id", "comprehension_evidence_sha256"}
            or binding["context_id"] != values["capsule_context_id"]
            or binding["comprehension_evidence_sha256"]
            != values["task_comprehension_evidence_sha256"]
        ):
            raise SenderError("cached sender prompt user binding differs")
    return values


def sender_prompt_binding_sha256(prompt: SenderPrompt) -> str:
    return sha256_text(
        canonical_json(
            {
                "schema_version": SENDER_PROMPT_BINDING_SCHEMA,
                "prompt": _prompt_values(prompt),
            }
        )
    )


def sender_prompt_preimage(prompt: SenderPrompt) -> dict[str, Any]:
    values = _prompt_values(prompt)
    return {
        "schema_version": SENDER_PROMPT_PREIMAGE_SCHEMA,
        "request_binding_sha256": sender_prompt_binding_sha256(prompt),
        "prompt": values,
        "roles": {
            "system": values["system_text"],
            "user": values["user_text"],
        },
    }


def sender_prompt_preimage_json(prompt: SenderPrompt) -> str:
    return canonical_json(sender_prompt_preimage(prompt))


def sender_prompt_preimage_sha256(prompt: SenderPrompt) -> str:
    return sha256_text(sender_prompt_preimage_json(prompt))


def compiler_reply_preimage(reply: ModelReply) -> dict[str, Any]:
    if type(reply) is not ModelReply:
        raise SenderError("compiler reply preimage requires an exact ModelReply")
    validated = ModelReply(
        **{
            item.name: object.__getattribute__(reply, item.name)
            for item in fields(ModelReply)
        }
    )
    return {
        "schema_version": COMPILER_REPLY_PREIMAGE_SCHEMA,
        "reply": {
            item.name: object.__getattribute__(validated, item.name)
            for item in fields(ModelReply)
        },
    }


def compiler_reply_preimage_json(reply: ModelReply) -> str:
    return canonical_json(compiler_reply_preimage(reply))


def compiler_reply_preimage_sha256(reply: ModelReply) -> str:
    return sha256_text(compiler_reply_preimage_json(reply))


@dataclass(frozen=True)
class CapturedCompilerResponse:
    capture: ProviderRequestCapture
    reply: ModelReply | None

    def __post_init__(self) -> None:
        if type(self.capture) is not ProviderRequestCapture:
            raise SenderError("captured compiler response requires an exact capture")
        try:
            self.capture.validate()
        except Exception as exc:
            raise SenderError("captured compiler response capture is invalid") from exc
        if self.capture.status == "completed":
            if type(self.reply) is not ModelReply:
                raise SenderError("completed compiler capture requires an exact reply")
            compiler_reply_preimage(self.reply)
        elif self.reply is not None:
            raise SenderError("failed compiler capture cannot carry a reply")


class CapturedCompilerAdapter(Protocol):
    def complete_captured(self, prompt: SenderPrompt) -> CapturedCompilerResponse:
        ...


@dataclass(frozen=True)
class _CapturedCompilerSeal:
    fingerprint_sha256: str


def _capture_binding(capture: ProviderRequestCapture | None) -> str | None:
    if capture is None:
        return None
    try:
        return capture.binding_sha256
    except Exception as exc:
        raise SenderError("captured compiler provider capture is invalid") from exc


def _execution_fingerprint(
    *,
    schema_version: str,
    status: str,
    calls: int,
    request_binding_sha256: str,
    request_preimage_sha256: str,
    intended_model_visible_sha256: str,
    expected_model_id: str,
    expected_settings_sha256: str,
    capture: ProviderRequestCapture | None,
    reply: ModelReply | None,
    failure: str | None,
    usage_complete: bool,
    provider_authenticity_verified: bool,
    claim_eligible: bool,
    goal_total_complete: bool,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "schema_version": schema_version,
                "status": status,
                "calls": calls,
                "request_binding_sha256": request_binding_sha256,
                "request_preimage_sha256": request_preimage_sha256,
                "intended_model_visible_sha256": intended_model_visible_sha256,
                "expected_model_id": expected_model_id,
                "expected_settings_sha256": expected_settings_sha256,
                "capture_binding_sha256": _capture_binding(capture),
                "reply_preimage_sha256": (
                    None
                    if reply is None
                    else compiler_reply_preimage_sha256(reply)
                ),
                "failure": failure,
                "usage_complete": usage_complete,
                "provider_authenticity_verified": provider_authenticity_verified,
                "claim_eligible": claim_eligible,
                "goal_total_complete": goal_total_complete,
            }
        )
    )


def _validated_request_preimage(
    request_preimage_json: str,
    *,
    request_preimage_sha256: str,
    request_binding_sha256: str,
    intended_model_visible_sha256: str,
) -> dict[str, Any]:
    if type(request_preimage_json) is not str:
        raise SenderError("captured compiler request preimage must be text")
    if sha256_text(request_preimage_json) != request_preimage_sha256:
        raise SenderError("captured compiler request preimage differs")
    try:
        preimage = strict_json_loads(request_preimage_json)
    except ValueError as exc:
        raise SenderError("captured compiler request preimage is invalid") from exc
    if canonical_json(preimage) != request_preimage_json:
        raise SenderError("captured compiler request preimage is not canonical")
    if type(preimage) is not dict or set(preimage) != {
        "schema_version",
        "request_binding_sha256",
        "prompt",
        "roles",
    }:
        raise SenderError("captured compiler request preimage shape differs")
    if preimage["schema_version"] != SENDER_PROMPT_PREIMAGE_SCHEMA:
        raise SenderError("captured compiler request preimage schema differs")
    prompt_value = preimage["prompt"]
    if type(prompt_value) is not dict or set(prompt_value) != set(_PROMPT_FIELDS):
        raise SenderError("captured compiler prompt preimage fields differ")
    try:
        reconstructed = SenderPrompt(**prompt_value)
    except TypeError as exc:
        raise SenderError("captured compiler prompt preimage is invalid") from exc
    if _prompt_values(reconstructed) != prompt_value:
        raise SenderError("captured compiler prompt preimage value differs")
    expected_binding = sender_prompt_binding_sha256(reconstructed)
    if (
        preimage["request_binding_sha256"] != expected_binding
        or request_binding_sha256 != expected_binding
    ):
        raise SenderError("captured compiler request binding differs")
    roles = preimage["roles"]
    if roles != {
        "system": prompt_value["system_text"],
        "user": prompt_value["user_text"],
    }:
        raise SenderError("captured compiler role preimage differs")
    visible = "SYSTEM\n" + roles["system"] + "\n\nUSER\n" + roles["user"]
    if sha256_text(visible) != intended_model_visible_sha256:
        raise SenderError("captured compiler model-visible preimage differs")
    return preimage


@dataclass(frozen=True)
class CapturedCompilerExecution:
    schema_version: str
    status: str
    calls: int
    request_binding_sha256: str
    request_preimage_json: str
    request_preimage_sha256: str
    intended_model_visible_sha256: str
    expected_model_id: str
    expected_settings_sha256: str
    capture: ProviderRequestCapture | None
    reply: ModelReply | None
    failure: str | None
    usage_complete: bool
    provider_authenticity_verified: bool
    claim_eligible: bool
    goal_total_complete: bool
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self) is not CapturedCompilerExecution:
            raise SenderError("captured compiler execution type differs")
        if self.schema_version != CAPTURED_COMPILER_EXECUTION_SCHEMA:
            raise SenderError("captured compiler execution schema differs")
        if self.status not in {
            "completed",
            "failed",
            "capture-rejected",
            "budget-exceeded",
        }:
            raise SenderError("captured compiler execution status is unknown")
        if type(self.calls) is not int or self.calls != 1:
            raise SenderError("captured compiler execution requires one adapter call")
        _sha(self.request_binding_sha256, "captured compiler request binding")
        _sha(self.request_preimage_sha256, "captured compiler request preimage")
        _sha(
            self.intended_model_visible_sha256,
            "captured compiler model-visible digest",
        )
        _identifier(self.expected_model_id, "captured compiler expected model")
        _sha(
            self.expected_settings_sha256,
            "captured compiler expected settings",
        )
        request_preimage = _validated_request_preimage(
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
                raise SenderError(f"captured compiler {name} must be boolean")
        if any(
            (
                self.provider_authenticity_verified,
                self.claim_eligible,
                self.goal_total_complete,
            )
        ):
            raise SenderError("captured compiler cannot establish claim authority")

        if self.capture is not None:
            if type(self.capture) is not ProviderRequestCapture:
                raise SenderError("captured compiler execution capture type differs")
            try:
                self.capture.validate()
            except Exception as exc:
                raise SenderError("captured compiler execution capture is invalid") from exc
            if self.capture.request_binding_sha256 != self.request_binding_sha256:
                raise SenderError("captured compiler execution request differs")
            if self.capture.request_preimage_sha256 != self.request_preimage_sha256:
                raise SenderError("captured compiler execution preimage differs")
            if (
                self.capture.intended_model_visible_sha256
                != self.intended_model_visible_sha256
            ):
                raise SenderError("captured compiler execution visibility differs")
            if self.capture.settings_sha256 != self.expected_settings_sha256:
                raise SenderError(
                    "captured compiler execution expected settings differ"
                )
            if (
                self.capture.request_dispatched
                and self.capture.model_id != self.expected_model_id
            ):
                raise SenderError(
                    "captured compiler execution expected model differs"
                )
            if self.capture.request_mode != COMPILER_REQUEST_MODE:
                raise SenderError("captured compiler execution route differs")
            if (
                self.capture.retry_count != 0
                or self.capture.attempt_count not in {0, 1}
            ):
                raise SenderError(
                    "captured compiler execution contains an unplanned retry"
                )
            if self.capture.request_dispatched and (
                self.capture.transmitted_system_text
                != request_preimage["roles"]["system"]
                or self.capture.transmitted_user_text
                != request_preimage["roles"]["user"]
            ):
                raise SenderError(
                    "captured compiler execution transmitted roles differ"
                )
        if self.reply is not None:
            compiler_reply_preimage(self.reply)
        if self.capture is not None and self.capture.status == "completed":
            if self.reply is None:
                raise SenderError("completed compiler capture requires a reply")
            _validate_capture_reply(self.capture, self.reply)

        if self.status == "completed":
            if not (
                type(self.capture) is ProviderRequestCapture
                and self.capture.status == "completed"
                and type(self.reply) is ModelReply
                and self.failure is None
                and self.usage_complete
            ):
                raise SenderError("completed captured compiler is inconsistent")
        elif self.status == "budget-exceeded":
            if not (
                type(self.capture) is ProviderRequestCapture
                and self.capture.status == "completed"
                and type(self.reply) is ModelReply
                and self.failure == "compiler-token-budget-exceeded"
                and self.usage_complete
            ):
                raise SenderError("budget-exceeded captured compiler is inconsistent")
        elif self.status == "failed":
            if not (
                self.reply is None
                and type(self.failure) is str
                and self.failure
                and (
                    self.capture is None
                    or (
                        type(self.capture) is ProviderRequestCapture
                        and self.capture.status == "failed"
                    )
                )
            ):
                raise SenderError("failed captured compiler is inconsistent")
            if self.usage_complete is not (
                False if self.capture is None else self.capture.usage_complete
            ):
                raise SenderError(
                    "failed compiler usage completeness differs from capture"
                )
        elif not (
            self.capture is None
            and self.reply is None
            and type(self.failure) is str
            and self.failure
            and not self.usage_complete
        ):
            raise SenderError("rejected captured compiler is inconsistent")

        expected = _execution_fingerprint(
            schema_version=self.schema_version,
            status=self.status,
            calls=self.calls,
            request_binding_sha256=self.request_binding_sha256,
            request_preimage_sha256=self.request_preimage_sha256,
            intended_model_visible_sha256=self.intended_model_visible_sha256,
            expected_model_id=self.expected_model_id,
            expected_settings_sha256=self.expected_settings_sha256,
            capture=self.capture,
            reply=self.reply,
            failure=self.failure,
            usage_complete=self.usage_complete,
            provider_authenticity_verified=self.provider_authenticity_verified,
            claim_eligible=self.claim_eligible,
            goal_total_complete=self.goal_total_complete,
        )
        if (
            type(self._construction_seal) is not _CapturedCompilerSeal
            or self._construction_seal.fingerprint_sha256 != expected
        ):
            raise SenderError("captured compiler execution construction seal differs")

    def validate(self) -> None:
        self.__post_init__()

    @property
    def binding_sha256(self) -> str:
        self.validate()
        assert type(self._construction_seal) is _CapturedCompilerSeal
        return self._construction_seal.fingerprint_sha256

    @property
    def total_tokens(self) -> int | None:
        self.validate()
        if not self.usage_complete or self.capture is None:
            return None
        return self.capture.provider_total_tokens

    @property
    def adapter_calls(self) -> int:
        self.validate()
        return self.calls

    @property
    def provider_attempt_count(self) -> int | None:
        self.validate()
        return None if self.capture is None else self.capture.attempt_count


def _execution(
    *,
    status: str,
    request_preimage_json: str,
    request_preimage_sha256: str,
    request_binding_sha256: str,
    intended_model_visible_sha256: str,
    expected_model_id: str,
    expected_settings_sha256: str,
    capture: ProviderRequestCapture | None,
    reply: ModelReply | None,
    failure: str | None,
    usage_complete: bool,
) -> CapturedCompilerExecution:
    values = {
        "schema_version": CAPTURED_COMPILER_EXECUTION_SCHEMA,
        "status": status,
        "calls": 1,
        "request_binding_sha256": request_binding_sha256,
        "request_preimage_json": request_preimage_json,
        "request_preimage_sha256": request_preimage_sha256,
        "intended_model_visible_sha256": intended_model_visible_sha256,
        "expected_model_id": expected_model_id,
        "expected_settings_sha256": expected_settings_sha256,
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
    return CapturedCompilerExecution(
        **values,
        _construction_seal=_CapturedCompilerSeal(fingerprint),
    )


def _copy_reply(reply: ModelReply) -> ModelReply:
    if type(reply) is not ModelReply:
        raise SenderError("captured compiler reply type differs")
    compiler_reply_preimage(reply)
    return ModelReply(
        **{
            item.name: object.__getattribute__(reply, item.name)
            for item in fields(ModelReply)
        }
    )


def _copy_capture(capture: ProviderRequestCapture) -> ProviderRequestCapture:
    if type(capture) is not ProviderRequestCapture:
        raise SenderError("captured compiler provider capture type differs")
    try:
        capture.validate()
        return ProviderRequestCapture(
            **{
                item.name: object.__getattribute__(capture, item.name)
                for item in fields(ProviderRequestCapture)
            }
        )
    except Exception as exc:
        raise SenderError("captured compiler provider capture is invalid") from exc


def _validate_capture_against_prompt(
    capture: ProviderRequestCapture,
    prompt: SenderPrompt,
    *,
    request_binding_sha256: str,
    request_preimage_sha256: str,
    expected_model_id: str,
    expected_settings_sha256: str,
) -> None:
    if capture.request_binding_sha256 != request_binding_sha256:
        raise SenderError("captured compiler request is replayed from another prompt")
    if capture.request_preimage_sha256 != request_preimage_sha256:
        raise SenderError("captured compiler request preimage differs")
    if capture.request_mode != COMPILER_REQUEST_MODE:
        raise SenderError("captured compiler request mode differs")
    if capture.intended_model_visible_sha256 != sha256_text(prompt.model_visible_text):
        raise SenderError("captured compiler intended visibility differs")
    if capture.settings_sha256 != expected_settings_sha256:
        raise SenderError("captured compiler settings differ")
    # Program /2 freezes one call per slot.  Do not accept an adapter's hidden
    # retry aggregate even for a failed request whose usage is unknown.
    if capture.retry_count != 0 or capture.attempt_count not in {0, 1}:
        raise SenderError("captured compiler retries are not representable")
    if capture.request_dispatched:
        if capture.attempt_count != 1:
            raise SenderError("captured compiler dispatch count differs")
        if (
            capture.transmitted_system_text != prompt.system_text
            or capture.transmitted_user_text != prompt.user_text
            or capture.transmitted_messages_sha256
            != provider_messages_sha256(prompt.system_text, prompt.user_text)
        ):
            raise SenderError("captured compiler transmission differs from prompt")
        if capture.model_id != expected_model_id:
            raise SenderError("captured compiler model differs")
    elif capture.attempt_count != 0:
        raise SenderError("undispatched compiler capture reports an attempt")


def _validate_capture_reply(
    capture: ProviderRequestCapture,
    reply: ModelReply,
) -> None:
    if capture.reply_preimage_sha256 != compiler_reply_preimage_sha256(reply):
        raise SenderError("captured compiler reply preimage differs")
    if (
        capture.model_id != reply.model_id
        or capture.provider_total_tokens != reply.total_tokens
        or reply.total_tokens is None
    ):
        raise SenderError("captured compiler reply usage differs")


def execute_captured_compiler(
    prompt: SenderPrompt,
    adapter: CapturedCompilerAdapter,
    *,
    expected_model_id: str,
    expected_settings_sha256: str,
) -> CapturedCompilerExecution:
    """Execute one exact sender prompt through a caller-supplied capture adapter."""

    if type(prompt) is not SenderPrompt:
        raise SenderError("captured compiler requires an exact SenderPrompt")
    _identifier(expected_model_id, "expected compiler model")
    _sha(expected_settings_sha256, "expected compiler settings")
    try:
        complete_method = inspect.getattr_static(adapter, "complete_captured")
    except Exception as exc:
        raise SenderError("captured compiler adapter is not inspectable") from exc
    if isinstance(complete_method, (staticmethod, classmethod)):
        complete_method = complete_method.__func__
    if not callable(complete_method):
        raise SenderError("captured compiler adapter requires a static method surface")

    request_binding = sender_prompt_binding_sha256(prompt)
    request_preimage_json = sender_prompt_preimage_json(prompt)
    if (
        sender_prompt_binding_sha256(prompt) != request_binding
        or sender_prompt_preimage_json(prompt) != request_preimage_json
    ):
        raise SenderError("sender prompt changed while its preimage was captured")
    request_preimage_sha = sha256_text(request_preimage_json)
    intended_visible_sha = sha256_text(prompt.model_visible_text)
    try:
        candidate = adapter.complete_captured(prompt)
    except Exception:
        try:
            changed = (
                sender_prompt_binding_sha256(prompt) != request_binding
                or sender_prompt_preimage_json(prompt) != request_preimage_json
            )
        except Exception:
            changed = True
        return _execution(
            status="capture-rejected" if changed else "failed",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_visible_sha,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha256,
            capture=None,
            reply=None,
            failure=(
                "captured-compiler-adapter-mutated-prompt"
                if changed
                else "captured-compiler-adapter-call-failed"
            ),
            usage_complete=False,
        )

    try:
        if (
            sender_prompt_binding_sha256(prompt) != request_binding
            or sender_prompt_preimage_json(prompt) != request_preimage_json
        ):
            raise SenderError("captured compiler adapter mutated the prompt")
        if type(candidate) is not CapturedCompilerResponse:
            raise SenderError("captured compiler response type differs")
        original_capture_binding = candidate.capture.binding_sha256
        capture = _copy_capture(candidate.capture)
        if candidate.capture.binding_sha256 != original_capture_binding:
            raise SenderError("captured compiler adapter mutated its capture")
        if candidate.reply is None:
            reply = None
        else:
            original_reply_preimage = compiler_reply_preimage_sha256(
                candidate.reply
            )
            reply = _copy_reply(candidate.reply)
            if (
                compiler_reply_preimage_sha256(candidate.reply)
                != original_reply_preimage
            ):
                raise SenderError("captured compiler adapter mutated its reply")
        _validate_capture_against_prompt(
            capture,
            prompt,
            request_binding_sha256=request_binding,
            request_preimage_sha256=request_preimage_sha,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha256,
        )
        if capture.status == "completed":
            assert reply is not None
            _validate_capture_reply(capture, reply)
    except Exception:
        return _execution(
            status="capture-rejected",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_visible_sha,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha256,
            capture=None,
            reply=None,
            failure="captured-compiler-evidence-invalid",
            usage_complete=False,
        )

    if capture.status == "failed":
        return _execution(
            status="failed",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_visible_sha,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha256,
            capture=capture,
            reply=None,
            failure=capture.failure_code,
            usage_complete=capture.usage_complete,
        )
    assert reply is not None
    if (
        prompt.maximum_total_tokens is not None
        and reply.total_tokens is not None
        and reply.total_tokens > prompt.maximum_total_tokens
    ):
        return _execution(
            status="budget-exceeded",
            request_preimage_json=request_preimage_json,
            request_preimage_sha256=request_preimage_sha,
            request_binding_sha256=request_binding,
            intended_model_visible_sha256=intended_visible_sha,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha256,
            capture=capture,
            reply=reply,
            failure="compiler-token-budget-exceeded",
            usage_complete=True,
        )
    return _execution(
        status="completed",
        request_preimage_json=request_preimage_json,
        request_preimage_sha256=request_preimage_sha,
        request_binding_sha256=request_binding,
        intended_model_visible_sha256=intended_visible_sha,
        expected_model_id=expected_model_id,
        expected_settings_sha256=expected_settings_sha256,
        capture=capture,
        reply=reply,
        failure=None,
        usage_complete=True,
    )


__all__ = [
    "CAPTURED_COMPILER_EXECUTION_SCHEMA",
    "COMPILER_REPLY_PREIMAGE_SCHEMA",
    "COMPILER_REQUEST_MODE",
    "SENDER_PROMPT_BINDING_SCHEMA",
    "SENDER_PROMPT_PREIMAGE_SCHEMA",
    "CapturedCompilerAdapter",
    "CapturedCompilerExecution",
    "CapturedCompilerResponse",
    "compiler_reply_preimage",
    "compiler_reply_preimage_json",
    "compiler_reply_preimage_sha256",
    "execute_captured_compiler",
    "sender_prompt_binding_sha256",
    "sender_prompt_preimage",
    "sender_prompt_preimage_json",
    "sender_prompt_preimage_sha256",
]
