"""Plan-bound, content-only execution seam for canonical Program /2 arms.

The runner invokes one caller-supplied slot adapter in canonical Program /2
order.  Every invocation is bound to the exact frozen Plan /2 preimage,
execution instance, session, arm, task, slot, activation prefix, implementation,
request deriver, and model lock.  Returned request, provider, local, and failure
preimages are embedded and re-derived before they can enter the existing
Program /2 structural evidence closure.

This is deliberately not an authenticated provider runner.  A caller can still
fabricate a self-consistent capture, and no judge verdict is promoted into a
claim result.  Provider, operator, sandbox, independence, safe-success, and
claim authority therefore remain closed even when every content record carries
complete token usage.  Provider and receipt identity uniqueness is enforced
only within one returned runtime artifact; cross-run freshness requires an
external authenticated reservation store and remains unverified here.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Mapping, Protocol, Sequence

from .contract import (
    PLAN_SCHEMA_V2,
    VerificationError,
    _count,
    _exact,
    _identifier,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
    validate_study_plan,
)
from .execution_program import execution_program_sha256
from .execution_program_v2_evidence import (
    build_program_v2_evidence_store,
    build_program_v2_resolution_item,
    build_program_v2_source_record,
    derive_program_v2_activation_input,
    resolve_program_v2_evidence,
    validate_resolved_program_v2_evidence,
)
from .terminal_contract import CAPTURE_TERMINAL_STATUSES


PROGRAM_V2_SLOT_REQUEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-slot-request/1"
)
PROGRAM_V2_SLOT_CAPTURE_SCHEMA = (
    "urusilla-initial-goal-program-v2-slot-capture/3"
)
PROGRAM_V2_PROVIDER_RECORD_SCHEMA = (
    "urusilla-initial-goal-program-v2-provider-record/2"
)
PROGRAM_V2_LOCAL_OBSERVATION_SCHEMA = (
    "urusilla-initial-goal-program-v2-local-observation/2"
)
PROGRAM_V2_FAILURE_ARTIFACT_SCHEMA = (
    "urusilla-initial-goal-program-v2-failure-artifact/2"
)
PROGRAM_V2_RUNTIME_RUN_SCHEMA = (
    "urusilla-initial-goal-program-v2-runtime-run/2"
)
PROGRAM_V2_RUNTIME_RUN_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-runtime-run-digest/1"
)
PROGRAM_V2_PREFIX_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-resolution-prefix/1"
)
PROGRAM_V2_REQUEST_PREIMAGE_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-request-preimage-digest/1"
)
PROGRAM_V2_RESPONSE_PREIMAGE_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-response-preimage-digest/1"
)
PROGRAM_V2_LOCAL_INPUT_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-local-input-digest/1"
)
PROGRAM_V2_LOCAL_OUTPUT_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-local-output-digest/1"
)
PROGRAM_V2_FAILURE_PREIMAGE_DIGEST_SCHEMA = (
    "urusilla-initial-goal-program-v2-failure-preimage-digest/1"
)
PROGRAM_V2_RUNTIME_EVIDENCE_BOUNDARY = (
    "plan-v2-content-bound-runtime-not-authenticated-study-evidence"
)

MAX_PREIMAGE_BYTES = 1_000_000
MAX_RUN_SLOTS = 100_000

_CAPTURE_RECORD_KINDS = {"executed-source", "failure-before-source-record"}
_FAILURE_STAGES = {
    "activation-unknown",
    "before-dispatch",
    "adapter-exception",
    "capture-unavailable",
}
_EFFECT_VALUE_FIELDS = {
    "tools_used",
    "persistence_created",
    "permission_expanded",
    "spending_authority_created",
    "external_effects_performed",
}
_EFFECT_FIELDS = {*_EFFECT_VALUE_FIELDS, "effects_complete"}
_AUTHORITY_FIELDS = {
    "provider_authenticated",
    "operator_authenticated",
    "sandbox_verified",
    "independent_operator_verified",
    "claim_eligible",
    "goal_total_complete",
}
_RUN_AUTHORITY_FIELDS = {
    "plan_reference_content_verified",
    "program_reference_content_verified",
    "capture_internal_binding_verified",
    "request_derivation_verified",
    "raw_usage_normalization_verified",
    *_AUTHORITY_FIELDS,
}
_USAGE_FIELDS = {
    "model_calls",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "reasoning_accounting",
    "total_tokens",
    "usage_complete",
}
_SLOT_RUN_FIELDS = {
    "slot_request_sha256",
    "slot_request",
    "callback_invoked",
    "capture_sha256",
    "capture",
}

_TYPED_REQUEST_SCHEMA = "urusilla-initial-goal-program-v2-typed-request/1"
_TYPED_OUTCOME_SCHEMA = "urusilla-initial-goal-program-v2-typed-outcome/1"
_TYPED_FAILURE_SCHEMA = "urusilla-initial-goal-program-v2-typed-failure/1"


class ProgramV2SlotAdapter(Protocol):
    """Caller-owned adapter for exactly one activated canonical slot."""

    def execute_slot(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _bounded_value(value: Any, path: str) -> Any:
    detached = _detach(value)
    encoded = canonical_json(detached).encode("utf-8")
    if len(encoded) > MAX_PREIMAGE_BYTES:
        raise VerificationError(f"{path} exceeds the bounded preimage size")
    return detached


def _nullable_sha(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _sha(value, path)


def _effects() -> dict[str, bool]:
    return {
        **{name: False for name in sorted(_EFFECT_VALUE_FIELDS)},
        "effects_complete": True,
    }


def _unknown_effects() -> dict[str, bool | None]:
    return {
        **{name: None for name in sorted(_EFFECT_VALUE_FIELDS)},
        "effects_complete": False,
    }


def _authority() -> dict[str, bool]:
    return {name: False for name in sorted(_AUTHORITY_FIELDS)}


def _run_authority() -> dict[str, bool]:
    return {
        "plan_reference_content_verified": True,
        "program_reference_content_verified": True,
        "capture_internal_binding_verified": True,
        "request_derivation_verified": False,
        "raw_usage_normalization_verified": False,
        **_authority(),
    }


def _validate_effects(value: Any, path: str) -> dict[str, bool | None]:
    effects = _object(_detach(value), path)
    _exact(effects, _EFFECT_FIELDS, path)
    if type(effects["effects_complete"]) is not bool:
        raise VerificationError(f"{path}.effects_complete must be boolean")
    expected = False if effects["effects_complete"] else None
    for name in sorted(_EFFECT_VALUE_FIELDS):
        if effects[name] is not expected:
            state = "false" if expected is False else "unknown"
            raise VerificationError(f"{path}.{name} must remain {state}")
    return effects


def _validate_observed_effects(value: Any, path: str) -> dict[str, bool]:
    effects = _object(_detach(value), path)
    _exact(effects, _EFFECT_VALUE_FIELDS, path)
    for name in sorted(_EFFECT_VALUE_FIELDS):
        if effects[name] is not False:
            raise VerificationError(f"{path}.{name} must remain false")
    return _effects()


def _validate_authority(value: Any, path: str) -> dict[str, bool]:
    authority = _object(_detach(value), path)
    _exact(authority, _AUTHORITY_FIELDS, path)
    for name in sorted(_AUTHORITY_FIELDS):
        if authority[name] is not False:
            raise VerificationError(f"{path}.{name} must remain false")
    return authority


def _validate_run_authority(value: Any, path: str) -> dict[str, bool]:
    authority = _object(_detach(value), path)
    _exact(authority, _RUN_AUTHORITY_FIELDS, path)
    for name in (
        "plan_reference_content_verified",
        "program_reference_content_verified",
        "capture_internal_binding_verified",
    ):
        if authority[name] is not True:
            raise VerificationError(f"{path}.{name} must be true")
    for name in (
        "request_derivation_verified",
        "raw_usage_normalization_verified",
    ):
        if authority[name] is not False:
            raise VerificationError(f"{path}.{name} must be false")
    _validate_authority(
        {name: authority[name] for name in _AUTHORITY_FIELDS},
        path,
    )
    return authority


def _unknown_usage() -> dict[str, Any]:
    return {
        "model_calls": None,
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "reasoning_accounting": None,
        "total_tokens": None,
        "usage_complete": False,
    }


def _validate_usage_shape(value: Any, path: str) -> dict[str, Any]:
    usage = _object(_detach(value), path)
    _exact(usage, _USAGE_FIELDS, path)
    for name in (
        "model_calls",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        item = usage[name]
        if item is not None:
            _count(item, f"{path}.{name}")
    if usage["reasoning_accounting"] not in {
        None,
        "included-in-output",
        "separately-reported",
        "not-reported",
    }:
        raise VerificationError(f"{path}.reasoning_accounting is invalid")
    if type(usage["usage_complete"]) is not bool:
        raise VerificationError(f"{path}.usage_complete must be boolean")
    return usage


def _validate_executed_usage(
    usage: Mapping[str, Any],
    *,
    external: bool,
    path: str,
) -> None:
    if usage["model_calls"] != (1 if external else 0):
        raise VerificationError(f"{path}.model_calls differs from source kind")
    if not external and any(
        usage[name] is not None
        for name in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "reasoning_accounting",
        )
    ):
        raise VerificationError(f"{path} local usage has model-only fields")
    total = usage["total_tokens"]
    if usage["usage_complete"] is not (total is not None):
        raise VerificationError(f"{path}.usage_complete differs from total")
    if not external:
        if total != 0:
            raise VerificationError(
                f"{path} deterministic-local model-token total must be zero"
            )
        return
    if total is None:
        if (
            usage["reasoning_tokens"] is not None
            or usage["reasoning_accounting"] not in (None, "not-reported")
        ):
            raise VerificationError(
                f"{path} partial external usage cannot classify reasoning"
            )
        return
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    reasoning_tokens = usage["reasoning_tokens"]
    accounting = usage["reasoning_accounting"]
    if input_tokens is None or output_tokens is None or accounting is None:
        raise VerificationError(f"{path} complete external usage lacks detail")
    if accounting == "not-reported":
        if reasoning_tokens is not None or total < input_tokens + output_tokens:
            raise VerificationError(f"{path} usage does not reconcile")
    elif accounting == "included-in-output":
        if (
            reasoning_tokens is None
            or reasoning_tokens > output_tokens
            or total != input_tokens + output_tokens
        ):
            raise VerificationError(f"{path} usage does not reconcile")
    elif (
        reasoning_tokens is None
        or total != input_tokens + output_tokens + reasoning_tokens
    ):
        raise VerificationError(f"{path} usage does not reconcile")


def _digest_value(
    schema_version: str,
    *,
    execution_instance_sha256: str,
    slot_request_sha256: str,
    value: Any,
    request_sha256: str | None = None,
) -> str:
    preimage = {
        "schema_version": schema_version,
        "execution_instance_sha256": execution_instance_sha256,
        "slot_request_sha256": slot_request_sha256,
        "value": _detach(value),
    }
    if request_sha256 is not None:
        preimage["request_sha256"] = request_sha256
    return sha256_ref(preimage)


def _validated_plan_and_program(
    plan: Any,
    *,
    session_id: str,
    arm_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    frozen = _detach(plan)
    summary = validate_study_plan(frozen)
    if summary["plan_schema_version"] != PLAN_SCHEMA_V2:
        raise VerificationError("runtime runner requires exact Plan /2")
    _identifier(session_id, "session_id")
    _identifier(arm_id, "arm_id")
    matches = [
        item for item in frozen["sessions"] if item["session_id"] == session_id
    ]
    if len(matches) != 1:
        raise VerificationError("runtime runner session is not uniquely planned")
    session = matches[0]
    wrapper = session["arm_execution_programs"].get(arm_id)
    if wrapper is None:
        raise VerificationError("runtime runner arm is not planned")
    program = _detach(wrapper["program"])
    program_sha = execution_program_sha256(program)
    if wrapper["program_sha256"] != program_sha:
        raise VerificationError("runtime runner program wrapper differs")
    return frozen, session, program, str(summary["plan_sha256"])


def _expected_model(
    plan: Mapping[str, Any],
    session: Mapping[str, Any],
) -> tuple[str, str]:
    family = session["receiver_family"]
    rows = [item for item in plan["receiver_models"] if item["family"] == family]
    if len(rows) != 1:
        raise VerificationError("runtime runner receiver model is ambiguous")
    return rows[0]["model_id"], rows[0]["settings_sha256"]


def _activation_truth(activation: Mapping[str, Any]) -> bool | None:
    conditions = activation["activation_predicate"]["all_of"]
    inputs = activation["fact_inputs"]
    saw_unknown = False
    for condition, observed in zip(conditions, inputs):
        value = observed["observed_value"]
        if value is None:
            saw_unknown = True
        elif value not in condition["equals_any"]:
            return False
    return None if saw_unknown else True


def _slot_request(
    *,
    execution_instance_sha256: str,
    plan_sha256: str,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    slot_index: int,
    activation_input: Mapping[str, Any],
    prior_resolutions: Sequence[Mapping[str, Any]],
    expected_model_id: str,
    expected_settings_sha256: str,
) -> dict[str, Any]:
    task_sha_by_id = {
        item["task_id"]: item["task_sha256"] for item in program["task_refs"]
    }
    external = slot["source_kind"] == "external-response"
    return {
        "schema_version": PROGRAM_V2_SLOT_REQUEST_SCHEMA,
        "execution_instance_sha256": execution_instance_sha256,
        "frozen_plan_sha256": plan_sha256,
        "program_sha256": execution_program_sha256(program),
        "session_id": program["session_id"],
        "arm_id": program["arm_id"],
        "slot_index": slot_index,
        "slot": _detach(slot),
        "task_sha256": (
            None
            if slot["task_id"] is None
            else task_sha_by_id[slot["task_id"]]
        ),
        "activation_input_sha256": sha256_ref(activation_input),
        "activation_input": _detach(activation_input),
        "prior_resolution_prefix_sha256": sha256_ref(
            {
                "schema_version": PROGRAM_V2_PREFIX_DIGEST_SCHEMA,
                "execution_instance_sha256": execution_instance_sha256,
                "resolutions": _detach(prior_resolutions),
            }
        ),
        "expected_model_id": expected_model_id if external else None,
        "expected_settings_sha256": (
            expected_settings_sha256 if external else None
        ),
    }


def _validate_slot_request(value: Any) -> dict[str, Any]:
    request = _object(_detach(value), "slot_request")
    _exact(
        request,
        {
            "schema_version",
            "execution_instance_sha256",
            "frozen_plan_sha256",
            "program_sha256",
            "session_id",
            "arm_id",
            "slot_index",
            "slot",
            "task_sha256",
            "activation_input_sha256",
            "activation_input",
            "prior_resolution_prefix_sha256",
            "expected_model_id",
            "expected_settings_sha256",
        },
        "slot_request",
    )
    if request["schema_version"] != PROGRAM_V2_SLOT_REQUEST_SCHEMA:
        raise VerificationError("slot request schema differs")
    for name in (
        "execution_instance_sha256",
        "frozen_plan_sha256",
        "program_sha256",
        "activation_input_sha256",
        "prior_resolution_prefix_sha256",
    ):
        _sha(request[name], f"slot_request.{name}")
    _identifier(request["session_id"], "slot_request.session_id")
    _identifier(request["arm_id"], "slot_request.arm_id")
    _count(request["slot_index"], "slot_request.slot_index")
    slot = _object(request["slot"], "slot_request.slot")
    if request["task_sha256"] is not None:
        _sha(request["task_sha256"], "slot_request.task_sha256")
    if request["activation_input_sha256"] != sha256_ref(
        request["activation_input"]
    ):
        raise VerificationError("slot request activation digest differs")
    external = slot.get("source_kind") == "external-response"
    if external:
        _identifier(request["expected_model_id"], "slot_request.expected_model_id")
        _sha(
            request["expected_settings_sha256"],
            "slot_request.expected_settings_sha256",
        )
    elif (
        request["expected_model_id"] is not None
        or request["expected_settings_sha256"] is not None
    ):
        raise VerificationError("local slot request carries provider settings")
    return request


def validate_program_v2_slot_request(value: Any) -> dict[str, Any]:
    """Publicly replay one immutable Program /2 slot-request preimage."""

    return _validate_slot_request(value)


def _validate_provider_record(
    value: Any,
    *,
    request: Mapping[str, Any],
    slot_request_sha256: str,
) -> dict[str, Any]:
    path = "slot_capture.provider_record"
    record = _object(_detach(value), path)
    _exact(
        record,
        {
            "schema_version",
            "slot_request_sha256",
            "request_sha256",
            "request",
            "response_sha256",
            "response",
            "terminal_status",
            "model_id",
            "settings_sha256",
            "provider_request_id",
            "provider_response_id",
            "raw_receipt_utf8",
            "raw_receipt_sha256",
            "attempt_count",
            "retry_count",
            "usage",
            "effects",
            "provider_authenticated",
        },
        path,
    )
    if record["schema_version"] != PROGRAM_V2_PROVIDER_RECORD_SCHEMA:
        raise VerificationError("provider record schema differs")
    if record["slot_request_sha256"] != slot_request_sha256:
        raise VerificationError("provider record is cross-wired to another slot")
    request_value = _bounded_value(record["request"], f"{path}.request")
    expected_request_sha = _digest_value(
        PROGRAM_V2_REQUEST_PREIMAGE_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha256,
        value=request_value,
    )
    if record["request_sha256"] != expected_request_sha:
        raise VerificationError("provider request preimage digest differs")
    response_value = (
        None
        if record["response"] is None
        else _bounded_value(record["response"], f"{path}.response")
    )
    expected_response_sha = _digest_value(
        PROGRAM_V2_RESPONSE_PREIMAGE_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha256,
        request_sha256=expected_request_sha,
        value=response_value,
    )
    if record["response_sha256"] != expected_response_sha:
        raise VerificationError("provider response preimage digest differs")
    if record["terminal_status"] not in CAPTURE_TERMINAL_STATUSES:
        raise VerificationError("provider terminal status is invalid")
    if record["model_id"] != request["expected_model_id"]:
        raise VerificationError("provider model differs from the frozen session")
    if record["settings_sha256"] != request["expected_settings_sha256"]:
        raise VerificationError("provider settings differ from the frozen session")
    _identifier(record["provider_request_id"], f"{path}.provider_request_id")
    if record["provider_response_id"] is not None:
        _identifier(record["provider_response_id"], f"{path}.provider_response_id")
    if record["attempt_count"] != 1 or record["retry_count"] != 0:
        raise VerificationError("Program /2 provider slot cannot aggregate retries")
    raw_receipt = record["raw_receipt_utf8"]
    raw_receipt_sha = record["raw_receipt_sha256"]
    if raw_receipt is None:
        if raw_receipt_sha is not None:
            raise VerificationError("raw receipt digest exists without exact bytes")
    else:
        if type(raw_receipt) is not str or not raw_receipt:
            raise VerificationError("raw provider receipt must be non-empty text")
        try:
            raw_bytes = raw_receipt.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VerificationError("raw provider receipt is not UTF-8") from exc
        if len(raw_bytes) > MAX_PREIMAGE_BYTES:
            raise VerificationError("raw provider receipt exceeds the size bound")
        if raw_receipt_sha != sha256_ref(raw_bytes):
            raise VerificationError("raw provider receipt digest differs")
    if record["terminal_status"] == "completed":
        if (
            response_value is None
            or record["provider_response_id"] is None
            or raw_receipt is None
        ):
            raise VerificationError("completed provider capture lacks exact evidence")
    record["usage"] = _validate_usage_shape(record["usage"], f"{path}.usage")
    if record["usage"]["usage_complete"] and raw_receipt is None:
        raise VerificationError(
            "complete provider usage requires an exact raw receipt preimage"
        )
    record["effects"] = _validate_effects(record["effects"], f"{path}.effects")
    if not record["effects"]["effects_complete"]:
        raise VerificationError("provider record effects must be complete")
    if record["provider_authenticated"] is not False:
        raise VerificationError("content capture cannot authenticate a provider")
    record["request"] = request_value
    record["response"] = response_value
    return _detach(record)


def _validate_local_observation(
    value: Any,
    *,
    request: Mapping[str, Any],
    slot_request_sha256: str,
) -> dict[str, Any]:
    path = "slot_capture.local_observation"
    observation = _object(_detach(value), path)
    _exact(
        observation,
        {
            "schema_version",
            "slot_request_sha256",
            "input_sha256",
            "input",
            "output_sha256",
            "output",
            "usage",
            "effects",
        },
        path,
    )
    if observation["schema_version"] != PROGRAM_V2_LOCAL_OBSERVATION_SCHEMA:
        raise VerificationError("local observation schema differs")
    if observation["slot_request_sha256"] != slot_request_sha256:
        raise VerificationError("local observation is cross-wired")
    input_value = _bounded_value(observation["input"], f"{path}.input")
    output_value = _bounded_value(observation["output"], f"{path}.output")
    expected_input = _digest_value(
        PROGRAM_V2_LOCAL_INPUT_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha256,
        value=input_value,
    )
    expected_output = _digest_value(
        PROGRAM_V2_LOCAL_OUTPUT_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha256,
        request_sha256=expected_input,
        value=output_value,
    )
    if observation["input_sha256"] != expected_input:
        raise VerificationError("local input preimage digest differs")
    if observation["output_sha256"] != expected_output:
        raise VerificationError("local output preimage digest differs")
    observation["usage"] = _validate_usage_shape(
        observation["usage"], f"{path}.usage"
    )
    observation["effects"] = _validate_effects(
        observation["effects"], f"{path}.effects"
    )
    if not observation["effects"]["effects_complete"]:
        raise VerificationError("local observation effects must be complete")
    observation["input"] = input_value
    observation["output"] = output_value
    return _detach(observation)


def _validate_failure_artifact(
    value: Any,
    *,
    request: Mapping[str, Any],
    slot_request_sha256: str,
) -> dict[str, Any]:
    path = "slot_capture.failure_artifact"
    failure = _object(_detach(value), path)
    _exact(
        failure,
        {
            "schema_version",
            "slot_request_sha256",
            "stage",
            "code",
            "request_sha256",
            "request",
            "callback_invoked",
            "effects",
        },
        path,
    )
    if failure["schema_version"] != PROGRAM_V2_FAILURE_ARTIFACT_SCHEMA:
        raise VerificationError("failure artifact schema differs")
    if failure["slot_request_sha256"] != slot_request_sha256:
        raise VerificationError("failure artifact is cross-wired")
    if failure["stage"] not in _FAILURE_STAGES:
        raise VerificationError("failure artifact stage is invalid")
    _identifier(failure["code"], f"{path}.code")
    if type(failure["callback_invoked"]) is not bool:
        raise VerificationError("failure callback flag must be boolean")
    if failure["stage"] == "activation-unknown":
        if failure["callback_invoked"]:
            raise VerificationError("unknown activation cannot invoke an adapter")
    elif not failure["callback_invoked"]:
        raise VerificationError("operational failure must retain its invocation")
    request_value = (
        None
        if failure["request"] is None
        else _bounded_value(failure["request"], f"{path}.request")
    )
    if request_value is None:
        if failure["request_sha256"] is not None:
            raise VerificationError("failure request digest lacks a preimage")
    else:
        if request["slot"]["source_kind"] != "external-response":
            raise VerificationError("local failure cannot bind a provider request")
        expected = _digest_value(
            PROGRAM_V2_REQUEST_PREIMAGE_DIGEST_SCHEMA,
            execution_instance_sha256=request["execution_instance_sha256"],
            slot_request_sha256=slot_request_sha256,
            value=request_value,
        )
        if failure["request_sha256"] != expected:
            raise VerificationError("failure request preimage digest differs")
    failure["effects"] = _validate_effects(failure["effects"], f"{path}.effects")
    if failure["stage"] == "activation-unknown":
        if not failure["effects"]["effects_complete"]:
            raise VerificationError("uninvoked activation failure effects are known")
    elif failure["effects"]["effects_complete"] and not failure["callback_invoked"]:
        raise VerificationError("operational failure effects lack an observation")
    failure["request"] = request_value
    return _detach(failure)


def validate_program_v2_slot_capture(
    value: Any,
    slot_request: Any,
) -> dict[str, Any]:
    """Validate one exact capture against its immutable slot request."""

    request = _validate_slot_request(slot_request)
    request_sha = sha256_ref(request)
    capture = _object(_detach(value), "slot_capture")
    _exact(
        capture,
        {
            "schema_version",
            "slot_request_sha256",
            "record_kind",
            "typed_execution_sha256",
            "request_sha256",
            "request",
            "provider_record_sha256",
            "provider_record",
            "local_observation_sha256",
            "local_observation",
            "failure_artifact_sha256",
            "failure_artifact",
            "facts",
            "usage",
            "effects",
            "authority",
        },
        "slot_capture",
    )
    if capture["schema_version"] != PROGRAM_V2_SLOT_CAPTURE_SCHEMA:
        raise VerificationError("slot capture schema differs")
    if capture["slot_request_sha256"] != request_sha:
        raise VerificationError("slot capture is replayed under another request")
    if capture["record_kind"] not in _CAPTURE_RECORD_KINDS:
        raise VerificationError("slot capture record kind is invalid")
    capture["facts"] = _object(_detach(capture["facts"]), "slot_capture.facts")
    capture["usage"] = _validate_usage_shape(
        capture["usage"], "slot_capture.usage"
    )
    capture["effects"] = _validate_effects(
        capture["effects"], "slot_capture.effects"
    )
    capture["authority"] = _validate_authority(
        capture["authority"], "slot_capture.authority"
    )
    typed_execution_sha = _nullable_sha(
        capture["typed_execution_sha256"],
        "slot_capture.typed_execution_sha256",
    )
    request_digest = _nullable_sha(
        capture["request_sha256"], "slot_capture.request_sha256"
    )
    provider_digest = _nullable_sha(
        capture["provider_record_sha256"],
        "slot_capture.provider_record_sha256",
    )
    local_digest = _nullable_sha(
        capture["local_observation_sha256"],
        "slot_capture.local_observation_sha256",
    )
    failure_digest = _nullable_sha(
        capture["failure_artifact_sha256"],
        "slot_capture.failure_artifact_sha256",
    )
    external = request["slot"]["source_kind"] == "external-response"
    if capture["record_kind"] == "executed-source":
        _validate_executed_usage(
            capture["usage"],
            external=external,
            path="slot_capture.usage",
        )
        if failure_digest is not None or capture["failure_artifact"] is not None:
            raise VerificationError("executed capture contains failure evidence")
        if not capture["effects"]["effects_complete"]:
            raise VerificationError("executed capture effects must be complete")
        if external:
            if (
                capture["request"] is None
                or request_digest is None
                or capture["provider_record"] is None
                or provider_digest is None
                or capture["local_observation"] is not None
                or local_digest is not None
            ):
                raise VerificationError("external capture evidence is not exclusive")
            request_value = _bounded_value(
                capture["request"], "slot_capture.request"
            )
            expected_request = _digest_value(
                PROGRAM_V2_REQUEST_PREIMAGE_DIGEST_SCHEMA,
                execution_instance_sha256=request["execution_instance_sha256"],
                slot_request_sha256=request_sha,
                value=request_value,
            )
            if request_digest != expected_request:
                raise VerificationError("slot capture request digest differs")
            provider = _validate_provider_record(
                capture["provider_record"],
                request=request,
                slot_request_sha256=request_sha,
            )
            if provider["request"] != request_value:
                raise VerificationError("provider and slot request preimages differ")
            if provider_digest != sha256_ref(provider):
                raise VerificationError("provider record digest differs")
            if provider["usage"] != capture["usage"]:
                raise VerificationError("provider and slot usage differ")
            if provider["effects"] != capture["effects"]:
                raise VerificationError("provider and slot effects differ")
            if capture["facts"].get("terminal_status") != provider["terminal_status"]:
                raise VerificationError("provider terminal fact differs")
            typed_request = provider["request"]
            typed_outcome = provider["response"]
            typed_marker = (
                type(typed_request) is dict
                and typed_request.get("schema_version") == _TYPED_REQUEST_SCHEMA
            ) or (
                type(typed_outcome) is dict
                and typed_outcome.get("schema_version") == _TYPED_OUTCOME_SCHEMA
            )
            if typed_marker and typed_execution_sha is None:
                raise VerificationError("typed envelope lacks execution identity")
            if typed_execution_sha is not None:
                if (
                    type(typed_request) is not dict
                    or typed_request.get("schema_version") != _TYPED_REQUEST_SCHEMA
                    or type(typed_outcome) is not dict
                    or typed_outcome.get("schema_version") != _TYPED_OUTCOME_SCHEMA
                    or typed_outcome.get("execution_binding_sha256")
                    != typed_execution_sha
                ):
                    raise VerificationError(
                        "typed provider execution binding differs"
                    )
            capture["request"] = request_value
            capture["provider_record"] = provider
        else:
            if typed_execution_sha is not None:
                raise VerificationError("local capture cannot bind a typed execution")
            if (
                capture["request"] is not None
                or request_digest is not None
                or capture["provider_record"] is not None
                or provider_digest is not None
                or capture["local_observation"] is None
                or local_digest is None
            ):
                raise VerificationError("local capture evidence is not exclusive")
            local = _validate_local_observation(
                capture["local_observation"],
                request=request,
                slot_request_sha256=request_sha,
            )
            if local_digest != sha256_ref(local):
                raise VerificationError("local observation digest differs")
            if local["usage"] != capture["usage"]:
                raise VerificationError("local observation and slot usage differ")
            if local["effects"] != capture["effects"]:
                raise VerificationError("local observation and slot effects differ")
            capture["local_observation"] = local
    else:
        if (
            capture["provider_record"] is not None
            or provider_digest is not None
            or capture["local_observation"] is not None
            or local_digest is not None
            or capture["failure_artifact"] is None
            or failure_digest is None
        ):
            raise VerificationError("failed capture evidence is not exclusive")
        failure = _validate_failure_artifact(
            capture["failure_artifact"],
            request=request,
            slot_request_sha256=request_sha,
        )
        if failure_digest != sha256_ref(failure):
            raise VerificationError("failure artifact digest differs")
        if capture["request"] != failure["request"]:
            raise VerificationError("failure and slot request preimages differ")
        if capture["request_sha256"] != failure["request_sha256"]:
            raise VerificationError("failure and slot request digests differ")
        if capture["facts"]:
            raise VerificationError("failed-before-record capture cannot assert facts")
        if capture["usage"] != _unknown_usage():
            raise VerificationError("failed-before-record usage must remain unknown")
        if capture["effects"] != failure["effects"]:
            raise VerificationError("failure and slot effects differ")
        typed_failure = failure["request"]
        typed_failure_marker = (
            type(typed_failure) is dict
            and (
                typed_failure.get("schema_version") == _TYPED_FAILURE_SCHEMA
                or (
                    type(typed_failure.get("request")) is dict
                    and typed_failure["request"].get("schema_version")
                    == _TYPED_REQUEST_SCHEMA
                )
            )
        )
        if typed_failure_marker and typed_execution_sha is None:
            raise VerificationError("typed envelope lacks execution identity")
        if typed_execution_sha is not None:
            if (
                not failure["callback_invoked"]
                or failure["stage"] == "activation-unknown"
            ):
                raise VerificationError(
                    "uninvoked failure cannot bind a typed execution"
                )
            if (
                type(typed_failure) is not dict
                or typed_failure.get("schema_version") != _TYPED_FAILURE_SCHEMA
                or typed_failure.get("execution_binding_sha256")
                != typed_execution_sha
                or type(typed_failure.get("request")) is not dict
                or typed_failure["request"].get("schema_version")
                != _TYPED_REQUEST_SCHEMA
            ):
                raise VerificationError("typed failure execution binding differs")
        capture["failure_artifact"] = failure
    encoded = canonical_json(capture).encode("utf-8")
    if len(encoded) > MAX_PREIMAGE_BYTES * 3:
        raise VerificationError("slot capture exceeds the bounded artifact size")
    return _detach(capture)


def build_program_v2_provider_capture(
    slot_request: Any,
    *,
    request_preimage: Any,
    response_preimage: Any,
    terminal_status: str,
    provider_request_id: str,
    provider_response_id: str | None,
    raw_receipt_utf8: str | None,
    observed_model_id: str,
    observed_settings_sha256: str,
    observed_effects: Mapping[str, Any],
    usage: Mapping[str, Any],
    facts: Mapping[str, Any],
    attempt_count: int = 1,
    retry_count: int = 0,
    typed_execution_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one exact but self-reported provider capture.

    The function validates observed model, settings, and effect fields against
    the frozen slot; it never derives those observations from the Plan.  This
    generic surface is content-only.  A provider-facing integration must first
    obtain the values from an exact typed transmission capture.
    """

    request = _validate_slot_request(slot_request)
    if request["slot"]["source_kind"] != "external-response":
        raise VerificationError("provider capture requires an external slot")
    slot_request_sha = sha256_ref(request)
    request_value = _bounded_value(request_preimage, "request_preimage")
    response_value = (
        None
        if response_preimage is None
        else _bounded_value(response_preimage, "response_preimage")
    )
    _identifier(observed_model_id, "observed_model_id")
    _sha(observed_settings_sha256, "observed_settings_sha256")
    normalized_effects = _validate_observed_effects(
        observed_effects, "observed_effects"
    )
    request_sha = _digest_value(
        PROGRAM_V2_REQUEST_PREIMAGE_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha,
        value=request_value,
    )
    response_sha = _digest_value(
        PROGRAM_V2_RESPONSE_PREIMAGE_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha,
        request_sha256=request_sha,
        value=response_value,
    )
    if raw_receipt_utf8 is None:
        raw_sha = None
    else:
        if type(raw_receipt_utf8) is not str or not raw_receipt_utf8:
            raise VerificationError("raw provider receipt must be non-empty text")
        try:
            raw_bytes = raw_receipt_utf8.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VerificationError("raw provider receipt is not UTF-8") from exc
        if len(raw_bytes) > MAX_PREIMAGE_BYTES:
            raise VerificationError("raw provider receipt exceeds the size bound")
        raw_sha = sha256_ref(raw_bytes)
    normalized_usage = _validate_usage_shape(usage, "usage")
    if typed_execution_sha256 is not None:
        _sha(typed_execution_sha256, "typed_execution_sha256")
    provider_record = {
        "schema_version": PROGRAM_V2_PROVIDER_RECORD_SCHEMA,
        "slot_request_sha256": slot_request_sha,
        "request_sha256": request_sha,
        "request": request_value,
        "response_sha256": response_sha,
        "response": response_value,
        "terminal_status": terminal_status,
        "model_id": observed_model_id,
        "settings_sha256": observed_settings_sha256,
        "provider_request_id": provider_request_id,
        "provider_response_id": provider_response_id,
        "raw_receipt_utf8": raw_receipt_utf8,
        "raw_receipt_sha256": raw_sha,
        "attempt_count": attempt_count,
        "retry_count": retry_count,
        "usage": normalized_usage,
        "effects": normalized_effects,
        "provider_authenticated": False,
    }
    provider_record = _validate_provider_record(
        provider_record,
        request=request,
        slot_request_sha256=slot_request_sha,
    )
    capture = {
        "schema_version": PROGRAM_V2_SLOT_CAPTURE_SCHEMA,
        "slot_request_sha256": slot_request_sha,
        "record_kind": "executed-source",
        "typed_execution_sha256": typed_execution_sha256,
        "request_sha256": request_sha,
        "request": request_value,
        "provider_record_sha256": sha256_ref(provider_record),
        "provider_record": provider_record,
        "local_observation_sha256": None,
        "local_observation": None,
        "failure_artifact_sha256": None,
        "failure_artifact": None,
        "facts": _detach(facts),
        "usage": normalized_usage,
        "effects": normalized_effects,
        "authority": _authority(),
    }
    return validate_program_v2_slot_capture(capture, request)


def build_program_v2_local_capture(
    slot_request: Any,
    *,
    input_preimage: Any,
    output_preimage: Any,
    usage: Mapping[str, Any],
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    request = _validate_slot_request(slot_request)
    if request["slot"]["source_kind"] == "external-response":
        raise VerificationError("local capture requires a local slot")
    slot_request_sha = sha256_ref(request)
    input_value = _bounded_value(input_preimage, "input_preimage")
    output_value = _bounded_value(output_preimage, "output_preimage")
    input_sha = _digest_value(
        PROGRAM_V2_LOCAL_INPUT_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha,
        value=input_value,
    )
    output_sha = _digest_value(
        PROGRAM_V2_LOCAL_OUTPUT_DIGEST_SCHEMA,
        execution_instance_sha256=request["execution_instance_sha256"],
        slot_request_sha256=slot_request_sha,
        request_sha256=input_sha,
        value=output_value,
    )
    normalized_usage = _validate_usage_shape(usage, "usage")
    local = {
        "schema_version": PROGRAM_V2_LOCAL_OBSERVATION_SCHEMA,
        "slot_request_sha256": slot_request_sha,
        "input_sha256": input_sha,
        "input": input_value,
        "output_sha256": output_sha,
        "output": output_value,
        "usage": normalized_usage,
        "effects": _effects(),
    }
    local = _validate_local_observation(
        local,
        request=request,
        slot_request_sha256=slot_request_sha,
    )
    capture = {
        "schema_version": PROGRAM_V2_SLOT_CAPTURE_SCHEMA,
        "slot_request_sha256": slot_request_sha,
        "record_kind": "executed-source",
        "typed_execution_sha256": None,
        "request_sha256": None,
        "request": None,
        "provider_record_sha256": None,
        "provider_record": None,
        "local_observation_sha256": sha256_ref(local),
        "local_observation": local,
        "failure_artifact_sha256": None,
        "failure_artifact": None,
        "facts": _detach(facts),
        "usage": normalized_usage,
        "effects": _effects(),
        "authority": _authority(),
    }
    return validate_program_v2_slot_capture(capture, request)


def build_program_v2_failure_capture(
    slot_request: Any,
    *,
    stage: str,
    code: str,
    callback_invoked: bool,
    request_preimage: Any | None = None,
    observed_effects: Mapping[str, Any] | None = None,
    typed_execution_sha256: str | None = None,
) -> dict[str, Any]:
    request = _validate_slot_request(slot_request)
    slot_request_sha = sha256_ref(request)
    request_value = (
        None
        if request_preimage is None
        else _bounded_value(request_preimage, "failure_request_preimage")
    )
    request_sha = (
        None
        if request_value is None
        else _digest_value(
            PROGRAM_V2_REQUEST_PREIMAGE_DIGEST_SCHEMA,
            execution_instance_sha256=request["execution_instance_sha256"],
            slot_request_sha256=slot_request_sha,
            value=request_value,
        )
    )
    normalized_effects = (
        _effects()
        if stage == "activation-unknown" and not callback_invoked
        else _unknown_effects()
        if observed_effects is None
        else _validate_observed_effects(observed_effects, "observed_effects")
    )
    if typed_execution_sha256 is not None:
        _sha(typed_execution_sha256, "typed_execution_sha256")
        if not callback_invoked or stage == "activation-unknown":
            raise VerificationError(
                "uninvoked failure cannot bind a typed execution"
            )
    failure = {
        "schema_version": PROGRAM_V2_FAILURE_ARTIFACT_SCHEMA,
        "slot_request_sha256": slot_request_sha,
        "stage": stage,
        "code": code,
        "request_sha256": request_sha,
        "request": request_value,
        "callback_invoked": callback_invoked,
        "effects": normalized_effects,
    }
    failure = _validate_failure_artifact(
        failure,
        request=request,
        slot_request_sha256=slot_request_sha,
    )
    capture = {
        "schema_version": PROGRAM_V2_SLOT_CAPTURE_SCHEMA,
        "slot_request_sha256": slot_request_sha,
        "record_kind": "failure-before-source-record",
        "typed_execution_sha256": typed_execution_sha256,
        "request_sha256": request_sha,
        "request": request_value,
        "provider_record_sha256": None,
        "provider_record": None,
        "local_observation_sha256": None,
        "local_observation": None,
        "failure_artifact_sha256": sha256_ref(failure),
        "failure_artifact": failure,
        "facts": {},
        "usage": _unknown_usage(),
        "effects": normalized_effects,
        "authority": _authority(),
    }
    return validate_program_v2_slot_capture(capture, request)


def _register_identity(
    registry: dict[tuple[str, str], str],
    *,
    kind: str,
    value: str | None,
    slot_id: str,
) -> None:
    if value is None:
        return
    key = (kind, value)
    prior = registry.get(key)
    if prior is not None:
        raise VerificationError(
            f"runtime capture identity {kind} is replayed across {prior} and {slot_id}"
        )
    registry[key] = slot_id


def _replay_slot_runs(
    *,
    plan: Mapping[str, Any],
    session: Mapping[str, Any],
    program: Mapping[str, Any],
    plan_sha256: str,
    execution_instance_sha256: str,
    slot_runs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if type(slot_runs) not in {list, tuple}:
        raise VerificationError("slot_runs must be a list or tuple")
    if len(slot_runs) != len(program["slots"]) or len(slot_runs) > MAX_RUN_SLOTS:
        raise VerificationError("slot_runs must cover the exact Program /2 slots")
    expected_model_id, expected_settings_sha = _expected_model(plan, session)
    records: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    normalized_runs: list[dict[str, Any]] = []
    identities: dict[tuple[str, str], str] = {}
    sequence = 0
    for index, (slot, raw_entry) in enumerate(zip(program["slots"], slot_runs)):
        activation = derive_program_v2_activation_input(
            program,
            slot_id=slot["slot_id"],
            prior_resolutions=resolutions,
            prior_records=records,
        )
        expected_request = _slot_request(
            execution_instance_sha256=execution_instance_sha256,
            plan_sha256=plan_sha256,
            program=program,
            slot=slot,
            slot_index=index,
            activation_input=activation,
            prior_resolutions=resolutions,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha,
        )
        entry = _object(_detach(raw_entry), f"slot_runs[{index}]")
        _exact(entry, _SLOT_RUN_FIELDS, f"slot_runs[{index}]")
        request = _validate_slot_request(entry["slot_request"])
        request_sha = _sha(
            entry["slot_request_sha256"],
            f"slot_runs[{index}].slot_request_sha256",
        )
        if request != expected_request or request_sha != sha256_ref(expected_request):
            raise VerificationError("slot run request differs from canonical replay")
        if type(entry["callback_invoked"]) is not bool:
            raise VerificationError("slot run callback flag must be boolean")
        truth = _activation_truth(activation)
        capture = None
        capture_sha = _nullable_sha(
            entry["capture_sha256"], f"slot_runs[{index}].capture_sha256"
        )
        if entry["capture"] is not None:
            capture = validate_program_v2_slot_capture(entry["capture"], request)
            if capture_sha != sha256_ref(capture):
                raise VerificationError("slot run capture digest differs")
            _register_identity(
                identities,
                kind="typed-execution-sha256",
                value=capture["typed_execution_sha256"],
                slot_id=slot["slot_id"],
            )
        elif capture_sha is not None:
            raise VerificationError("slot run capture digest lacks a preimage")
        if truth is False:
            if entry["callback_invoked"] or capture is not None:
                raise VerificationError("inactive slot invoked or recorded a source")
            disposition = "not-activated"
            source_record = None
        else:
            if capture is None:
                raise VerificationError("activated or unknown slot lacks a capture")
            failure = capture["record_kind"] == "failure-before-source-record"
            if truth is None:
                if entry["callback_invoked"]:
                    raise VerificationError("unknown activation invoked an adapter")
                if not failure or capture["failure_artifact"]["stage"] != "activation-unknown":
                    raise VerificationError("unknown activation lacks its exact failure")
            elif not entry["callback_invoked"]:
                raise VerificationError("active slot did not invoke its adapter")
            disposition = "failed-before-record" if failure else "executed"
            if failure:
                source_record = build_program_v2_source_record(
                    program,
                    slot_id=slot["slot_id"],
                    record_kind="failure-before-source-record",
                    activation_input=activation,
                    request_sha256=capture["request_sha256"],
                    failure_artifact_sha256=capture["failure_artifact_sha256"],
                )
            else:
                source_record = build_program_v2_source_record(
                    program,
                    slot_id=slot["slot_id"],
                    record_kind="executed-source",
                    activation_input=activation,
                    result_event_sequence=sequence,
                    request_sha256=capture["request_sha256"],
                    provider_record_sha256=capture["provider_record_sha256"],
                    local_observation_sha256=capture["local_observation_sha256"],
                    usage=capture["usage"],
                    facts=capture["facts"],
                )
                sequence += 1
            if capture["provider_record"] is not None:
                provider = capture["provider_record"]
                for kind, value in (
                    ("request-sha256", provider["request_sha256"]),
                    ("response-sha256", provider["response_sha256"]),
                    ("provider-record-sha256", capture["provider_record_sha256"]),
                    ("provider-request-id", provider["provider_request_id"]),
                    ("provider-response-id", provider["provider_response_id"]),
                    ("raw-receipt-sha256", provider["raw_receipt_sha256"]),
                ):
                    _register_identity(
                        identities,
                        kind=kind,
                        value=value,
                        slot_id=slot["slot_id"],
                    )
        resolution = build_program_v2_resolution_item(
            program,
            slot_id=slot["slot_id"],
            disposition=disposition,
            activation_input=activation,
            source_record=source_record,
        )
        if source_record is not None:
            records.append(source_record)
        resolutions.append(resolution)
        normalized_runs.append(
            {
                "slot_request_sha256": request_sha,
                "slot_request": request,
                "callback_invoked": entry["callback_invoked"],
                "capture_sha256": capture_sha,
                "capture": capture,
            }
        )
    store = build_program_v2_evidence_store(program, records)
    resolved = resolve_program_v2_evidence(program, resolutions, store)
    return normalized_runs, records, resolved


def _assemble_runtime_run(
    *,
    plan: Any,
    session_id: str,
    arm_id: str,
    execution_instance_sha256: str,
    slot_runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _sha(execution_instance_sha256, "execution_instance_sha256")
    frozen, session, program, plan_sha = _validated_plan_and_program(
        plan,
        session_id=session_id,
        arm_id=arm_id,
    )
    normalized_runs, records, resolved = _replay_slot_runs(
        plan=frozen,
        session=session,
        program=program,
        plan_sha256=plan_sha,
        execution_instance_sha256=execution_instance_sha256,
        slot_runs=slot_runs,
    )
    totals = [
        record["observation"]["usage"]["total_tokens"]
        for record in records
        if record["observation"] is not None
    ]
    has_failure = any(record["failure"] is not None for record in records)
    content_usage_complete = (
        not has_failure and all(type(item) is int for item in totals)
    )
    content_total = sum(totals) if content_usage_complete else None
    judge_components = {
        "task-judge",
        "parse-judge",
        "semantic-judge",
        "negative-judge",
    }
    records_by_slot = {record["slot_id"]: record for record in records}
    judges = [slot for slot in program["slots"] if slot["component"] in judge_components]
    four_judge_slots_recorded = all(
        slot["slot_id"] in records_by_slot
        and records_by_slot[slot["slot_id"]]["record_kind"] == "executed-source"
        for slot in judges
    )
    authority = _run_authority()
    core = {
        "evidence_boundary": PROGRAM_V2_RUNTIME_EVIDENCE_BOUNDARY,
        "execution_instance_sha256": execution_instance_sha256,
        "frozen_plan_sha256": plan_sha,
        "frozen_plan": frozen,
        "session_id": session_id,
        "arm_id": arm_id,
        "program_sha256": execution_program_sha256(program),
        "program": program,
        "slot_runs": normalized_runs,
        "resolved_program_v2_sha256": sha256_ref(resolved),
        "resolved_program_v2": resolved,
        "content_usage_complete": content_usage_complete,
        "content_bound_total_tokens": content_total,
        "four_judge_slots_recorded": four_judge_slots_recorded,
        "safely_completed": None,
        "authority": authority,
    }
    run_sha = sha256_ref(
        {"schema_version": PROGRAM_V2_RUNTIME_RUN_DIGEST_SCHEMA, **core}
    )
    return {
        "schema_version": PROGRAM_V2_RUNTIME_RUN_SCHEMA,
        **core,
        "run_sha256": run_sha,
    }


def run_planned_program_v2_arm(
    plan: Any,
    *,
    session_id: str,
    arm_id: str,
    execution_instance_sha256: str,
    adapter: ProgramV2SlotAdapter,
) -> dict[str, Any]:
    """Execute every active Program /2 slot once in canonical order."""

    original_plan_text = canonical_json(plan)
    frozen, session, program, plan_sha = _validated_plan_and_program(
        plan,
        session_id=session_id,
        arm_id=arm_id,
    )
    _sha(execution_instance_sha256, "execution_instance_sha256")
    try:
        static_method = inspect.getattr_static(adapter, "execute_slot")
    except Exception as exc:
        raise VerificationError("slot adapter is not statically inspectable") from exc
    if isinstance(static_method, (staticmethod, classmethod)):
        static_method = static_method.__func__
    if not callable(static_method):
        raise VerificationError("slot adapter requires a callable execute_slot")
    expected_model_id, expected_settings_sha = _expected_model(frozen, session)
    records: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    slot_runs: list[dict[str, Any]] = []
    live_identities: dict[tuple[str, str], str] = {}
    for index, slot in enumerate(program["slots"]):
        activation = derive_program_v2_activation_input(
            program,
            slot_id=slot["slot_id"],
            prior_resolutions=resolutions,
            prior_records=records,
        )
        request = _slot_request(
            execution_instance_sha256=execution_instance_sha256,
            plan_sha256=plan_sha,
            program=program,
            slot=slot,
            slot_index=index,
            activation_input=activation,
            prior_resolutions=resolutions,
            expected_model_id=expected_model_id,
            expected_settings_sha256=expected_settings_sha,
        )
        request_text = canonical_json(request)
        request_sha = sha256_ref(request)
        truth = _activation_truth(activation)
        invoked = False
        capture = None
        if truth is None:
            capture = build_program_v2_failure_capture(
                request,
                stage="activation-unknown",
                code="activation-input-unknown",
                callback_invoked=False,
            )
        elif truth is True:
            invoked = True
            request_for_adapter = _detach(request)
            try:
                candidate = adapter.execute_slot(request_for_adapter)
            except VerificationError:
                # A public capture builder can be called inside the adapter.
                # Its structural rejection is evidence of an invalid capture,
                # not an operational provider failure, and must remain fatal.
                raise
            except Exception:
                if (
                    canonical_json(plan) != original_plan_text
                    or canonical_json(request_for_adapter) != request_text
                ):
                    raise VerificationError(
                        "slot adapter mutated frozen input before failure"
                    )
                capture = build_program_v2_failure_capture(
                    request,
                    stage="adapter-exception",
                    code="slot-adapter-call-failed",
                    callback_invoked=True,
                )
            else:
                if (
                    canonical_json(plan) != original_plan_text
                    or canonical_json(request_for_adapter) != request_text
                ):
                    raise VerificationError("slot adapter mutated frozen input")
                capture = validate_program_v2_slot_capture(candidate, request)
        entry = {
            "slot_request_sha256": request_sha,
            "slot_request": request,
            "callback_invoked": invoked,
            "capture_sha256": None if capture is None else sha256_ref(capture),
            "capture": capture,
        }
        # The capture was independently reconstructed against this exact
        # slot request above.  Reserve provider identities immediately so a
        # replay fails before another potentially billable slot is invoked.
        if capture is not None and capture["provider_record"] is not None:
            provider = capture["provider_record"]
            for kind, value in (
                ("request-sha256", provider["request_sha256"]),
                ("response-sha256", provider["response_sha256"]),
                ("provider-record-sha256", capture["provider_record_sha256"]),
                ("provider-request-id", provider["provider_request_id"]),
                ("provider-response-id", provider["provider_response_id"]),
                ("raw-receipt-sha256", provider["raw_receipt_sha256"]),
            ):
                _register_identity(
                    live_identities,
                    kind=kind,
                    value=value,
                    slot_id=slot["slot_id"],
                )
        if capture is not None:
            _register_identity(
                live_identities,
                kind="typed-execution-sha256",
                value=capture["typed_execution_sha256"],
                slot_id=slot["slot_id"],
            )
        # Program graph validators require the complete graph, so use the
        # canonical source builder for the live prefix and leave a second,
        # full independent replay to _assemble_runtime_run below.
        if truth is False:
            source = None
            disposition = "not-activated"
        elif capture is not None and capture["record_kind"] == "executed-source":
            source = build_program_v2_source_record(
                program,
                slot_id=slot["slot_id"],
                record_kind="executed-source",
                activation_input=activation,
                result_event_sequence=len(
                    [record for record in records if record["observation"] is not None]
                ),
                request_sha256=capture["request_sha256"],
                provider_record_sha256=capture["provider_record_sha256"],
                local_observation_sha256=capture["local_observation_sha256"],
                usage=capture["usage"],
                facts=capture["facts"],
            )
            disposition = "executed"
        else:
            assert capture is not None
            source = build_program_v2_source_record(
                program,
                slot_id=slot["slot_id"],
                record_kind="failure-before-source-record",
                activation_input=activation,
                request_sha256=capture["request_sha256"],
                failure_artifact_sha256=capture["failure_artifact_sha256"],
            )
            disposition = "failed-before-record"
        resolution = build_program_v2_resolution_item(
            program,
            slot_id=slot["slot_id"],
            disposition=disposition,
            activation_input=activation,
            source_record=source,
        )
        if source is not None:
            records.append(source)
        resolutions.append(resolution)
        slot_runs.append(entry)
    artifact = _assemble_runtime_run(
        plan=frozen,
        session_id=session_id,
        arm_id=arm_id,
        execution_instance_sha256=execution_instance_sha256,
        slot_runs=slot_runs,
    )
    return validate_program_v2_runtime_run(artifact)


def validate_program_v2_runtime_run(value: Any) -> dict[str, Any]:
    """Recompute the full Plan -> Program -> capture -> closure chain."""

    artifact = _object(_detach(value), "program_v2_runtime_run")
    _exact(
        artifact,
        {
            "schema_version",
            "evidence_boundary",
            "execution_instance_sha256",
            "frozen_plan_sha256",
            "frozen_plan",
            "session_id",
            "arm_id",
            "program_sha256",
            "program",
            "slot_runs",
            "resolved_program_v2_sha256",
            "resolved_program_v2",
            "content_usage_complete",
            "content_bound_total_tokens",
            "four_judge_slots_recorded",
            "safely_completed",
            "authority",
            "run_sha256",
        },
        "program_v2_runtime_run",
    )
    if artifact["schema_version"] != PROGRAM_V2_RUNTIME_RUN_SCHEMA:
        raise VerificationError("Program /2 runtime run schema differs")
    if artifact["evidence_boundary"] != PROGRAM_V2_RUNTIME_EVIDENCE_BOUNDARY:
        raise VerificationError("Program /2 runtime evidence boundary differs")
    _sha(artifact["execution_instance_sha256"], "execution_instance_sha256")
    _sha(artifact["frozen_plan_sha256"], "frozen_plan_sha256")
    _sha(artifact["program_sha256"], "program_sha256")
    _sha(artifact["resolved_program_v2_sha256"], "resolved_program_v2_sha256")
    _sha(artifact["run_sha256"], "run_sha256")
    if type(artifact["content_usage_complete"]) is not bool:
        raise VerificationError("content usage completeness must be boolean")
    if artifact["content_bound_total_tokens"] is not None:
        _count(artifact["content_bound_total_tokens"], "content_bound_total_tokens")
    if type(artifact["four_judge_slots_recorded"]) is not bool:
        raise VerificationError("four-judge slot-record flag must be boolean")
    if artifact["safely_completed"] is not None:
        raise VerificationError("runtime content cannot establish safe completion")
    _validate_run_authority(artifact["authority"], "authority")
    validate_resolved_program_v2_evidence(artifact["resolved_program_v2"])
    recomputed = _assemble_runtime_run(
        plan=artifact["frozen_plan"],
        session_id=artifact["session_id"],
        arm_id=artifact["arm_id"],
        execution_instance_sha256=artifact["execution_instance_sha256"],
        slot_runs=artifact["slot_runs"],
    )
    if canonical_json(artifact) != canonical_json(recomputed):
        raise VerificationError("Program /2 runtime run or digest differs")
    return _detach(artifact)


__all__ = [
    "PROGRAM_V2_FAILURE_ARTIFACT_SCHEMA",
    "PROGRAM_V2_LOCAL_OBSERVATION_SCHEMA",
    "PROGRAM_V2_PROVIDER_RECORD_SCHEMA",
    "PROGRAM_V2_RUNTIME_EVIDENCE_BOUNDARY",
    "PROGRAM_V2_RUNTIME_RUN_SCHEMA",
    "PROGRAM_V2_SLOT_CAPTURE_SCHEMA",
    "PROGRAM_V2_SLOT_REQUEST_SCHEMA",
    "ProgramV2SlotAdapter",
    "build_program_v2_failure_capture",
    "build_program_v2_local_capture",
    "build_program_v2_provider_capture",
    "run_planned_program_v2_arm",
    "validate_program_v2_runtime_run",
    "validate_program_v2_slot_request",
    "validate_program_v2_slot_capture",
]
