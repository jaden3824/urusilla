"""Construction-only bridge from exact hybrid captures into Program /2 slots.

The bridge removes caller-supplied model, settings, usage, effect, and fact
fields from the compiler/receiver path.  It validates one factory-sealed typed
execution, projects only observations retained by that execution, and then
uses the Program /2 builders.  It does not authenticate the provider, replay a
frozen request deriver, or independently normalize usage from a raw receipt.
The resulting generic Program /2 JSON therefore remains claim-ineligible.
"""

from __future__ import annotations

from typing import Any, Mapping

from urusilla_hybrid_runtime.canonical import (
    canonical_json as runtime_canonical_json,
    sha256_text,
    strict_json_loads,
)
from urusilla_hybrid_runtime.captured_compiler import (
    CapturedCompilerExecution,
    compiler_reply_preimage_json,
)
from urusilla_hybrid_runtime.captured_judge import (
    CapturedJudgeExecution,
    JudgeTaskMessage,
    JudgeTaskMetadata,
    JudgeTerminalEvidence,
    RoleSeparatedJudgeRequest,
    judge_reply_preimage_json,
)
from urusilla_hybrid_runtime.captured_receiver import (
    CapturedReceiverExecution,
    ProviderRequestCapture,
    receiver_model_reply_preimage_json,
)
from urusilla_hybrid_runtime.sender import parse_sender_output
from urusilla_hybrid_runtime.task_context import (
    PublicTaskContext,
    validate_state_against_task_context,
)

from .contract import VerificationError, sha256_ref
from .program_v2_runtime_runner import (
    build_program_v2_failure_capture,
    build_program_v2_provider_capture,
    validate_program_v2_slot_request,
)


PROGRAM_V2_TYPED_REQUEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-typed-request/1"
)
PROGRAM_V2_TYPED_OUTCOME_SCHEMA = (
    "urusilla-initial-goal-program-v2-typed-outcome/1"
)
PROGRAM_V2_TYPED_FAILURE_SCHEMA = (
    "urusilla-initial-goal-program-v2-typed-failure/1"
)
PROGRAM_V2_TYPED_JUDGE_RESULT_SCHEMA = (
    "urusilla-initial-goal-program-v2-typed-judge-result/1"
)

_COMPILER_COMPONENTS = {"sender-compiler"}
_RECEIVER_COMPONENTS = {"receiver", "primary", "fallback-receiver"}
_JUDGE_COMPONENTS = {
    "task-judge",
    "parse-judge",
    "semantic-judge",
    "negative-judge",
}
_EFFECT_NAMES = (
    "tools_used",
    "persistence_created",
    "permission_expanded",
    "spending_authority_created",
    "external_effects_performed",
)


def _execution_binding(execution: Any, expected_type: type, label: str) -> str:
    if type(execution) is not expected_type:
        raise VerificationError(f"typed {label} execution type differs")
    try:
        execution.validate()
        binding = execution.binding_sha256
        execution.validate()
    except Exception as exc:
        raise VerificationError(f"typed {label} execution is invalid") from exc
    return binding


def _ensure_execution_unchanged(
    execution: Any,
    *,
    expected_binding: str,
    label: str,
) -> None:
    try:
        execution.validate()
        current = execution.binding_sha256
    except Exception as exc:
        raise VerificationError(f"typed {label} execution changed") from exc
    if current != expected_binding:
        raise VerificationError(f"typed {label} execution binding changed")


def _reject_structural_capture_failure(execution: Any, label: str) -> None:
    if execution.status == "capture-rejected":
        raise VerificationError(
            f"typed {label} structural capture rejection is fatal"
        )


def _validate_role_and_locks(
    slot_request: Any,
    execution: Any,
    *,
    allowed_components: set[str],
    label: str,
) -> dict[str, Any]:
    request = validate_program_v2_slot_request(slot_request)
    slot = request["slot"]
    if slot["source_kind"] != "external-response":
        raise VerificationError(f"typed {label} requires an external slot")
    if slot["component"] not in allowed_components:
        raise VerificationError(f"typed {label} component is cross-wired")
    if execution.expected_model_id != request["expected_model_id"]:
        raise VerificationError(f"typed {label} expected model differs")
    if execution.expected_settings_sha256 != request["expected_settings_sha256"]:
        raise VerificationError(f"typed {label} expected settings differ")
    return request


def _request_value(execution: Any) -> dict[str, Any]:
    try:
        parsed = strict_json_loads(execution.request_preimage_json)
    except ValueError as exc:
        raise VerificationError("typed execution request preimage is invalid") from exc
    if runtime_canonical_json(parsed) != execution.request_preimage_json:
        raise VerificationError("typed execution request preimage is not canonical")
    return parsed


def _request_envelope(
    request: Mapping[str, Any],
    execution: Any,
    *,
    bridge_kind: str,
    request_mode: str,
) -> dict[str, Any]:
    return {
        "schema_version": PROGRAM_V2_TYPED_REQUEST_SCHEMA,
        "bridge_kind": bridge_kind,
        "slot_request_sha256": sha256_ref(request),
        "execution_schema_version": execution.schema_version,
        "request_binding_sha256": execution.request_binding_sha256,
        "request_preimage_sha256": execution.request_preimage_sha256,
        "request_preimage_json": execution.request_preimage_json,
        "intended_model_visible_sha256": execution.intended_model_visible_sha256,
        "expected_model_id": execution.expected_model_id,
        "expected_settings_sha256": execution.expected_settings_sha256,
        "request_mode": request_mode,
    }


def _capture_effects(capture: ProviderRequestCapture) -> dict[str, bool]:
    return {name: getattr(capture, name) for name in _EFFECT_NAMES}


def _typed_usage(capture: ProviderRequestCapture) -> dict[str, Any]:
    return {
        "model_calls": capture.attempt_count,
        "input_tokens": capture.input_tokens,
        "output_tokens": capture.output_tokens,
        "reasoning_tokens": capture.reasoning_tokens,
        "reasoning_accounting": capture.reasoning_accounting,
        "total_tokens": capture.provider_total_tokens,
        "usage_complete": capture.usage_complete,
    }


def _program_usage(capture: ProviderRequestCapture) -> dict[str, Any]:
    """Project only usage that Program /2 can represent without coercion.

    The typed outcome retains every original partial field.  Program /2 keeps
    visible input/output counts but treats its total and reasoning split as
    unknown until the typed capture itself marks the usage complete.
    """

    observed = _typed_usage(capture)
    if capture.usage_complete and capture.raw_receipt_text is not None:
        return observed
    return {
        "model_calls": capture.attempt_count,
        "input_tokens": capture.input_tokens,
        "output_tokens": capture.output_tokens,
        "reasoning_tokens": None,
        "reasoning_accounting": None,
        "total_tokens": None,
        "usage_complete": False,
    }


def _outcome_envelope(
    execution: Any,
    *,
    execution_binding_sha256: str,
    bridge_kind: str,
    reply_preimage_json: str | None,
) -> dict[str, Any]:
    capture = execution.capture
    assert type(capture) is ProviderRequestCapture
    return {
        "schema_version": PROGRAM_V2_TYPED_OUTCOME_SCHEMA,
        "bridge_kind": bridge_kind,
        "execution_binding_sha256": execution_binding_sha256,
        "execution_status": execution.status,
        "execution_failure": execution.failure,
        "capture_binding_sha256": capture.binding_sha256,
        "capture_status": capture.status,
        "provider_terminal_status": capture.provider_terminal_status,
        "transmitted_messages_sha256": capture.transmitted_messages_sha256,
        "adapter_calls": execution.adapter_calls,
        "provider_attempt_count": execution.provider_attempt_count,
        "capture_failure_stage": capture.failure_stage,
        "capture_failure_code": capture.failure_code,
        "typed_usage": _typed_usage(capture),
        "reply_preimage_json": reply_preimage_json,
        "reply_preimage_sha256": (
            None if reply_preimage_json is None else sha256_text(reply_preimage_json)
        ),
        "usage_complete": execution.usage_complete,
    }


def _failure_capture(
    request: Mapping[str, Any],
    execution: Any,
    *,
    request_envelope: Mapping[str, Any],
    execution_binding_sha256: str,
) -> dict[str, Any]:
    capture = execution.capture
    if capture is None:
        stage = (
            "adapter-exception"
            if execution.status == "failed"
            else "capture-unavailable"
        )
        effects = None
    else:
        if capture.request_dispatched:
            raise VerificationError("dispatched capture cannot become before-record")
        stage = "before-dispatch"
        effects = _capture_effects(capture)
    code = execution.failure or "typed-execution-failed"
    failure_envelope = {
        "schema_version": PROGRAM_V2_TYPED_FAILURE_SCHEMA,
        "request": dict(request_envelope),
        "execution_binding_sha256": execution_binding_sha256,
        "execution_status": execution.status,
        "execution_failure": execution.failure,
        "adapter_calls": execution.adapter_calls,
        "capture_binding_sha256": (
            None if capture is None else capture.binding_sha256
        ),
        "capture_status": None if capture is None else capture.status,
        "capture_failure_stage": (
            None if capture is None else capture.failure_stage
        ),
        "capture_failure_code": (
            None if capture is None else capture.failure_code
        ),
        "provider_attempt_count": execution.provider_attempt_count,
    }
    return build_program_v2_failure_capture(
        request,
        stage=stage,
        code=code,
        callback_invoked=True,
        request_preimage=failure_envelope,
        observed_effects=effects,
        typed_execution_sha256=execution_binding_sha256,
    )


def _provider_capture(
    request: Mapping[str, Any],
    execution: Any,
    *,
    request_envelope: Mapping[str, Any],
    outcome_envelope: Mapping[str, Any],
    facts: Mapping[str, Any],
    execution_binding_sha256: str,
) -> dict[str, Any]:
    capture = execution.capture
    assert type(capture) is ProviderRequestCapture
    if not capture.request_dispatched:
        raise VerificationError("undispatched capture cannot become provider evidence")
    if capture.attempt_count != 1 or capture.retry_count != 0:
        raise VerificationError("typed execution retries are not representable")
    if capture.model_id is None or capture.provider_request_id is None:
        raise VerificationError("typed provider observation is incomplete")
    if capture.provider_terminal_status is None:
        raise VerificationError("typed provider terminal is unknown")
    return build_program_v2_provider_capture(
        request,
        request_preimage=request_envelope,
        response_preimage=outcome_envelope,
        terminal_status=capture.provider_terminal_status,
        provider_request_id=capture.provider_request_id,
        provider_response_id=capture.provider_response_id,
        raw_receipt_utf8=capture.raw_receipt_text,
        observed_model_id=capture.model_id,
        observed_settings_sha256=capture.settings_sha256,
        observed_effects=_capture_effects(capture),
        usage=_program_usage(capture),
        facts=facts,
        attempt_count=capture.attempt_count,
        retry_count=capture.retry_count,
        typed_execution_sha256=execution_binding_sha256,
    )


def _compiler_status(execution: CapturedCompilerExecution) -> str:
    if execution.status != "completed" or execution.reply is None:
        return "failed"
    try:
        status, candidates, _, _ = parse_sender_output(execution.reply.text)
        if candidates:
            request_value = _request_value(execution)
            prompt = request_value["prompt"]
            user = strict_json_loads(prompt["user_text"])
            context_value = user["task_context"]
            if context_value is None:
                return "failed"
            context = PublicTaskContext.from_json(
                runtime_canonical_json(context_value)
            )
            for candidate in candidates:
                validate_state_against_task_context(candidate, context)
        return status
    except Exception:
        return "failed"


def _receiver_mode(request: Mapping[str, Any], execution: Any) -> str:
    value = _request_value(execution)
    try:
        mode = value["request"]["mode"]
    except (KeyError, TypeError) as exc:
        raise VerificationError("typed receiver request mode is missing") from exc
    if type(mode) is not str:
        raise VerificationError("typed receiver request mode is invalid")
    component = request["slot"]["component"]
    arm = request["arm_id"]
    if component == "receiver":
        expected = "raw" if arm == "raw-concise" else "json" if arm == "ordinary-json" else None
        if expected is None or mode != expected:
            raise VerificationError("typed baseline receiver mode differs")
    elif component == "primary":
        selected = [
            item["observed_value"]
            for item in request["activation_input"]["fact_inputs"]
            if item["fact"] == "selected_mode"
        ]
        if len(selected) != 1 or selected[0] != mode:
            raise VerificationError("typed primary receiver mode differs")
    elif mode not in {"raw", "json"}:
        raise VerificationError("typed fallback receiver mode differs")
    return mode


def _judge_probe_applicable(
    task_metadata: Mapping[str, Any],
    judge_role: str,
) -> bool:
    if judge_role == "task-judge":
        return True
    field_by_role = {
        "parse-judge": "parse_probe",
        "semantic-judge": "semantic_probe",
        "negative-judge": "negative_probe",
    }
    try:
        value = task_metadata[field_by_role[judge_role]]
    except (KeyError, TypeError) as exc:
        raise VerificationError("typed judge role or probe metadata differs") from exc
    if type(value) is not bool:
        raise VerificationError("typed judge probe applicability is invalid")
    return value


def _judge_task_metadata(value: Any) -> JudgeTaskMetadata:
    if type(value) is not dict or set(value) != {
        "task_id",
        "task_sha256",
        "feature_tags",
        "parse_probe",
        "semantic_probe",
        "negative_probe",
    }:
        raise VerificationError("typed judge task metadata differs")
    tags = value["feature_tags"]
    if type(tags) is not list:
        raise VerificationError("typed judge feature tags differ")
    try:
        return JudgeTaskMetadata(
            task_id=value["task_id"],
            task_sha256=value["task_sha256"],
            feature_tags=tuple(tags),
            parse_probe=value["parse_probe"],
            semantic_probe=value["semantic_probe"],
            negative_probe=value["negative_probe"],
        )
    except Exception as exc:
        raise VerificationError("typed judge task metadata is invalid") from exc


def _judge_terminal(value: Any) -> JudgeTerminalEvidence:
    if type(value) is not dict:
        raise VerificationError("typed judge terminal evidence differs")
    try:
        terminal = JudgeTerminalEvidence(**value)
    except Exception as exc:
        raise VerificationError("typed judge terminal evidence is invalid") from exc
    if terminal.value != value:
        raise VerificationError("typed judge terminal projection is lossy")
    return terminal


def build_program_v2_judge_request(
    slot_request: Any,
    *,
    task_messages: tuple[JudgeTaskMessage, ...],
    rubric_text: str,
    reference_text: str | None = None,
    maximum_total_tokens: int | None = None,
) -> RoleSeparatedJudgeRequest:
    """Construct a typed judge request before any provider dispatch.

    Program /2 freezes only the task-input digest, probe metadata and exact
    terminal selection.  The caller supplies the matching task-message
    preimage plus the still-diagnostic rubric/reference text.  The typed
    constructor checks every digest and preserves the full Program objects in
    the model-visible request; it does not authenticate the rubric issuer.
    """

    request = validate_program_v2_slot_request(slot_request)
    slot = request["slot"]
    role = slot["component"]
    if slot["source_kind"] != "external-response" or role not in _JUDGE_COMPONENTS:
        raise VerificationError("typed judge requires a judge external slot")
    metadata = _judge_task_metadata(request["task_metadata"])
    terminal = _judge_terminal(request["terminal_evidence"])
    applicable = _judge_probe_applicable(request["task_metadata"], role)
    try:
        return RoleSeparatedJudgeRequest(
            judge_role=role,
            task_id=slot["task_id"],
            planned_task_sha256=request["task_sha256"],
            task_messages=task_messages,
            probe_applicable=applicable,
            task_metadata=metadata,
            terminal=terminal,
            rubric_text=rubric_text,
            rubric_sha256=sha256_text(rubric_text),
            reference_text=reference_text,
            reference_sha256=(
                None if reference_text is None else sha256_text(reference_text)
            ),
            maximum_total_tokens=maximum_total_tokens,
        )
    except Exception as exc:
        raise VerificationError("typed judge request is invalid") from exc


def _judge_request_value(execution: CapturedJudgeExecution) -> dict[str, Any]:
    preimage = _request_value(execution)
    if type(preimage) is not dict or set(preimage) != {
        "schema_version",
        "request_binding_sha256",
        "request",
        "roles",
    }:
        raise VerificationError("typed judge request preimage shape differs")
    value = preimage["request"]
    if type(value) is not dict:
        raise VerificationError("typed judge request value differs")
    return value


def _validate_judge_request_binding(
    request: Mapping[str, Any],
    execution: CapturedJudgeExecution,
) -> tuple[str, dict[str, Any]]:
    role = request["slot"]["component"]
    value = _judge_request_value(execution)
    if value.get("role") != role:
        raise VerificationError("typed judge role is cross-wired")
    if value.get("task_sha256") != request["task_sha256"]:
        raise VerificationError("typed judge task digest differs")
    if value.get("task_metadata") != request["task_metadata"]:
        raise VerificationError("typed judge task metadata differs")
    if value.get("terminal_evidence") != request["terminal_evidence"]:
        raise VerificationError("typed judge terminal evidence differs")
    applicable = _judge_probe_applicable(request["task_metadata"], role)
    if value.get("probe_applicable") is not applicable:
        raise VerificationError("typed judge probe applicability differs")
    messages = value.get("task_input_messages")
    if type(messages) is not list or not messages:
        raise VerificationError("typed judge task messages are missing")
    if value.get("maximum_total_tokens") is not None and (
        type(value["maximum_total_tokens"]) is not int
        or value["maximum_total_tokens"] <= 0
    ):
        raise VerificationError("typed judge token ceiling differs")
    return role, value


def _judge_result_envelope(
    execution: CapturedJudgeExecution,
    *,
    role: str,
    request_value: Mapping[str, Any],
) -> dict[str, Any]:
    verdict = None if execution.verdict is None else execution.verdict.value
    terminal = request_value["terminal_evidence"]
    return {
        "schema_version": PROGRAM_V2_TYPED_JUDGE_RESULT_SCHEMA,
        "judge_role": role,
        "task_sha256": request_value["task_sha256"],
        "task_metadata_sha256": sha256_ref(request_value["task_metadata"]),
        "terminal_evidence_sha256": sha256_ref(terminal),
        "terminal_content_binding_verified": terminal[
            "content_binding_verified"
        ],
        "probe_applicable": request_value["probe_applicable"],
        "rubric_sha256": request_value["rubric"]["sha256"],
        "reference_sha256": (
            None
            if request_value["reference"] is None
            else request_value["reference"]["sha256"]
        ),
        "verdict_parse_status": execution.verdict_parse_status,
        "verdict": verdict,
    }


def build_program_v2_compiler_capture(
    slot_request: Any,
    execution: CapturedCompilerExecution,
) -> dict[str, Any]:
    """Project one exact sender-compiler execution without free-form facts."""

    binding = _execution_binding(execution, CapturedCompilerExecution, "compiler")
    _reject_structural_capture_failure(execution, "compiler")
    request = _validate_role_and_locks(
        slot_request,
        execution,
        allowed_components=_COMPILER_COMPONENTS,
        label="compiler",
    )
    request_value = _request_value(execution)
    if request_value.get("schema_version") is None:
        raise VerificationError("typed compiler request schema is missing")
    request_envelope = _request_envelope(
        request,
        execution,
        bridge_kind="compiler",
        request_mode="sender-compiler",
    )
    capture = execution.capture
    if capture is None or not capture.request_dispatched:
        result = _failure_capture(
            request,
            execution,
            request_envelope=request_envelope,
            execution_binding_sha256=binding,
        )
    else:
        reply_json = (
            None
            if execution.reply is None
            else compiler_reply_preimage_json(execution.reply)
        )
        outcome = _outcome_envelope(
            execution,
            execution_binding_sha256=binding,
            bridge_kind="compiler",
            reply_preimage_json=reply_json,
        )
        result = _provider_capture(
            request,
            execution,
            request_envelope=request_envelope,
            outcome_envelope=outcome,
            facts={
                "terminal_status": capture.provider_terminal_status,
                "compiler_status": _compiler_status(execution),
            },
            execution_binding_sha256=binding,
        )
    _ensure_execution_unchanged(
        execution,
        expected_binding=binding,
        label="compiler",
    )
    return result


def build_program_v2_receiver_capture(
    slot_request: Any,
    execution: CapturedReceiverExecution,
) -> dict[str, Any]:
    """Project one exact direct-receiver execution without free-form facts."""

    binding = _execution_binding(execution, CapturedReceiverExecution, "receiver")
    _reject_structural_capture_failure(execution, "receiver")
    request = _validate_role_and_locks(
        slot_request,
        execution,
        allowed_components=_RECEIVER_COMPONENTS,
        label="receiver",
    )
    mode = _receiver_mode(request, execution)
    request_envelope = _request_envelope(
        request,
        execution,
        bridge_kind="receiver",
        request_mode=mode,
    )
    capture = execution.capture
    if capture is None or not capture.request_dispatched:
        result = _failure_capture(
            request,
            execution,
            request_envelope=request_envelope,
            execution_binding_sha256=binding,
        )
    else:
        reply_json = (
            None
            if execution.reply is None
            else receiver_model_reply_preimage_json(execution.reply)
        )
        outcome = _outcome_envelope(
            execution,
            execution_binding_sha256=binding,
            bridge_kind="receiver",
            reply_preimage_json=reply_json,
        )
        result = _provider_capture(
            request,
            execution,
            request_envelope=request_envelope,
            outcome_envelope=outcome,
            facts={"terminal_status": capture.provider_terminal_status},
            execution_binding_sha256=binding,
        )
    _ensure_execution_unchanged(
        execution,
        expected_binding=binding,
        label="receiver",
    )
    return result


def build_program_v2_judge_capture(
    slot_request: Any,
    execution: CapturedJudgeExecution,
) -> dict[str, Any]:
    """Project one exact role-separated judge call into Program /2.

    The generic Program fact surface intentionally retains only provider
    terminal status.  Parsed verdict semantics stay inside the typed outcome
    envelope so the frozen Program /2 graph is not silently widened.  A later
    diagnostic closure may derive tri-state summaries from these exact typed
    outcomes, but this bridge alone cannot establish safe completion.
    """

    binding = _execution_binding(execution, CapturedJudgeExecution, "judge")
    _reject_structural_capture_failure(execution, "judge")
    request = _validate_role_and_locks(
        slot_request,
        execution,
        allowed_components=_JUDGE_COMPONENTS,
        label="judge",
    )
    role, request_value = _validate_judge_request_binding(request, execution)
    request_envelope = _request_envelope(
        request,
        execution,
        bridge_kind="judge",
        request_mode=role,
    )
    capture = execution.capture
    if capture is None or not capture.request_dispatched:
        result = _failure_capture(
            request,
            execution,
            request_envelope=request_envelope,
            execution_binding_sha256=binding,
        )
    else:
        reply_json = (
            None
            if execution.reply is None
            else judge_reply_preimage_json(execution.reply)
        )
        outcome = _outcome_envelope(
            execution,
            execution_binding_sha256=binding,
            bridge_kind="judge",
            reply_preimage_json=reply_json,
        )
        outcome["judge_result"] = _judge_result_envelope(
            execution,
            role=role,
            request_value=request_value,
        )
        result = _provider_capture(
            request,
            execution,
            request_envelope=request_envelope,
            outcome_envelope=outcome,
            facts={"terminal_status": capture.provider_terminal_status},
            execution_binding_sha256=binding,
        )
    _ensure_execution_unchanged(
        execution,
        expected_binding=binding,
        label="judge",
    )
    return result


__all__ = [
    "PROGRAM_V2_TYPED_FAILURE_SCHEMA",
    "PROGRAM_V2_TYPED_JUDGE_RESULT_SCHEMA",
    "PROGRAM_V2_TYPED_OUTCOME_SCHEMA",
    "PROGRAM_V2_TYPED_REQUEST_SCHEMA",
    "build_program_v2_compiler_capture",
    "build_program_v2_judge_capture",
    "build_program_v2_judge_request",
    "build_program_v2_receiver_capture",
]
