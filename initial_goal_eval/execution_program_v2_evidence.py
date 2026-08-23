"""Strict, claim-ineligible evidence closure for canonical Program /2.

This module deliberately does not modify or widen the legacy Program /1
source-record and resolver contracts.  It binds exact Program /2 slots to
inline activation, observation, and failure preimages, then replays the frozen
predicates in canonical slot order.  Hash consistency is structural evidence
only: every authentication and claim flag remains false or null.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .contract import (
    ROUTES,
    VerificationError,
    _count,
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
)
from .execution_program import (
    ACTIVATION_FACTS,
    ARM_EXECUTION_PROGRAM_SCHEMA_V2,
    SLOT_DISPOSITIONS,
    execution_program_sha256,
    validate_goal_arm_execution_program,
)
from .terminal_contract import CAPTURE_TERMINAL_STATUSES, SILENCE_TERMINAL_STATUS


PROGRAM_V2_SOURCE_RECORD_SCHEMA = (
    "urusilla-initial-goal-arm-execution-source-record/2"
)
PROGRAM_V2_EVIDENCE_STORE_SCHEMA = (
    "urusilla-initial-goal-arm-execution-evidence-store/2"
)
PROGRAM_V2_RESOLUTION_SCHEMA = (
    "urusilla-initial-goal-arm-execution-program-resolution/2"
)
PROGRAM_V2_ACTIVATION_INPUT_SCHEMA = (
    "urusilla-initial-goal-execution-program-activation-input/2"
)
PROGRAM_V2_OBSERVATION_SCHEMA = (
    "urusilla-initial-goal-arm-execution-observation/2"
)
PROGRAM_V2_FAILURE_SCHEMA = (
    "urusilla-initial-goal-arm-execution-failure/2"
)
PROGRAM_V2_RESOLUTION_DIGEST_SCHEMA = (
    "urusilla-initial-goal-execution-program-resolution-digest/2"
)
PROGRAM_V2_EVIDENCE_BOUNDARY = (
    "program-v2-structural-evidence-not-authenticated-study-evidence"
)

SOURCE_RECORD_KINDS_V2 = ("executed-source", "failure-before-source-record")

_FACT_FIELDS = set(ACTIVATION_FACTS) - {"disposition"}
_FACT_VALUES = {
    "selected_mode": set(ROUTES),
    "terminal_status": {
        *CAPTURE_TERMINAL_STATUSES,
        SILENCE_TERMINAL_STATUS,
    },
    "fidelity_verdict": {"valid", "invalid"},
    "output_verdict": {"valid", "invalid"},
    "control_decision": {"attempt-action-state", "skip-action-state"},
    "compiler_status": {
        "not-attempted",
        "ok",
        "ambiguous",
        "unsupported",
        "failed",
    },
}
_ROUTER_FACT_COMPONENTS = {"preflight-router", "final-router"}
_FACT_COMPONENTS = {
    "selected_mode": _ROUTER_FACT_COMPONENTS,
    "fidelity_verdict": {"fidelity-verifier"},
    "output_verdict": {"output-validator"},
    "control_decision": {"preflight-router", "compiler-control"},
    "compiler_status": {"sender-compiler", "compiler-control"},
}

_AUTHORITY_FIELDS = {
    "frozen_plan_sha256",
    "plan_bound",
    "program_authenticated",
    "request_deriver_authenticated",
    "implementation_authenticated",
    "model_authenticated",
    "observation_authenticated",
    "provider_authenticated",
    "operator_authenticated",
    "claim_eligible",
    "goal_total_complete",
}
_SOURCE_RECORD_FIELDS = {
    "schema_version",
    "evidence_boundary",
    "program_sha256",
    "record_kind",
    "session_id",
    "arm_id",
    "task_id",
    "task_sha256",
    "slot_id",
    "accounting_phase",
    "component",
    "source_kind",
    "request_deriver_sha256",
    "implementation_sha256",
    "model_binding_sha256",
    "maximum_calls",
    "activation_input_sha256",
    "activation_input",
    "observation_sha256",
    "observation",
    "failure_sha256",
    "failure",
    "result_event_sequence",
    "facts",
    "authority",
}
_OBSERVATION_FIELDS = {
    "schema_version",
    "program_sha256",
    "slot_id",
    "activation_input_sha256",
    "source_kind",
    "request_sha256",
    "provider_record_sha256",
    "local_observation_sha256",
    "result_event_sequence",
    "facts",
    "usage",
}
_FAILURE_FIELDS = {
    "schema_version",
    "program_sha256",
    "slot_id",
    "activation_input_sha256",
    "source_kind",
    "request_sha256",
    "failure_artifact_sha256",
    "result_event_sequence",
    "facts",
    "usage",
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
_RESOLUTION_ITEM_FIELDS = {
    "slot_id",
    "disposition",
    "activation_input_sha256",
    "activation_input",
    "source_record_sha256",
    "result_event_sequence",
}


__all__ = [
    "PROGRAM_V2_ACTIVATION_INPUT_SCHEMA",
    "PROGRAM_V2_EVIDENCE_STORE_SCHEMA",
    "PROGRAM_V2_FAILURE_SCHEMA",
    "PROGRAM_V2_OBSERVATION_SCHEMA",
    "PROGRAM_V2_RESOLUTION_SCHEMA",
    "PROGRAM_V2_SOURCE_RECORD_SCHEMA",
    "SOURCE_RECORD_KINDS_V2",
    "build_program_v2_evidence_store",
    "build_program_v2_resolution_item",
    "build_program_v2_source_record",
    "derive_program_v2_activation_input",
    "resolve_program_v2_evidence",
    "validate_program_v2_evidence_store",
    "validate_program_v2_source_record",
    "validate_resolved_program_v2_evidence",
]


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _program(value: Any) -> dict[str, Any]:
    program = validate_goal_arm_execution_program(value)
    if program["schema_version"] != ARM_EXECUTION_PROGRAM_SCHEMA_V2:
        raise VerificationError("Program /2 evidence requires exact Program /2")
    return program


def _program_sha256(program: Mapping[str, Any]) -> str:
    # Strict goal validation must precede the shared generic digest helper.
    return execution_program_sha256(program)


def _nullable_sha(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _sha(value, path)


def _nullable_count(value: Any, path: str) -> int | None:
    return _count(value, path, nullable=True)


def _authority() -> dict[str, Any]:
    return {
        "frozen_plan_sha256": None,
        "plan_bound": False,
        "program_authenticated": False,
        "request_deriver_authenticated": False,
        "implementation_authenticated": False,
        "model_authenticated": False,
        "observation_authenticated": False,
        "provider_authenticated": False,
        "operator_authenticated": False,
        "claim_eligible": False,
        "goal_total_complete": False,
    }


def _validate_authority(value: Any, path: str) -> dict[str, Any]:
    authority = _object(value, path)
    _exact(authority, _AUTHORITY_FIELDS, path)
    if authority["frozen_plan_sha256"] is not None:
        raise VerificationError(f"{path}.frozen_plan_sha256 must remain null")
    for name in _AUTHORITY_FIELDS - {"frozen_plan_sha256"}:
        if authority[name] is not False:
            raise VerificationError(f"{path}.{name} must remain false")
    return _detach(authority)


def _slot_map(program: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {slot["slot_id"]: slot for slot in program["slots"]}


def _task_sha_by_id(program: Mapping[str, Any]) -> dict[str, str]:
    return {
        ref["task_id"]: ref["task_sha256"] for ref in program["task_refs"]
    }


def _empty_facts() -> dict[str, None]:
    return {name: None for name in sorted(_FACT_FIELDS)}


def _normalize_facts(
    value: Any,
    *,
    component: str,
    source_kind: str,
    executed: bool,
    path: str,
) -> dict[str, str | None]:
    facts = _object(value, path)
    _exact(facts, _FACT_FIELDS, path)
    normalized: dict[str, str | None] = {}
    for name in sorted(_FACT_FIELDS):
        item = facts[name]
        if item is not None and (
            type(item) is not str or item not in _FACT_VALUES[name]
        ):
            raise VerificationError(f"{path}.{name} is invalid")
        normalized[name] = item
    if not executed:
        if any(item is not None for item in normalized.values()):
            raise VerificationError("failed-before-record cannot assert typed facts")
        return normalized

    for name, item in normalized.items():
        if item is None:
            continue
        if name == "terminal_status":
            if source_kind != "external-response":
                raise VerificationError(
                    f"{path}.{name} has the wrong source kind"
                )
        elif component not in _FACT_COMPONENTS[name]:
            raise VerificationError(
                f"{path}.{name} has the wrong source component"
            )

    required: set[str] = set()
    if source_kind == "external-response":
        required.add("terminal_status")
    if component in _ROUTER_FACT_COMPONENTS:
        required.add("selected_mode")
    if component == "fidelity-verifier":
        required.add("fidelity_verdict")
    if component == "output-validator":
        required.add("output_verdict")
    if component == "preflight-router":
        required.add("control_decision")
    if component in {"sender-compiler", "compiler-control"}:
        required.add("compiler_status")
    missing = sorted(name for name in required if normalized[name] is None)
    if missing:
        raise VerificationError(f"{path} lacks required typed facts: {missing}")
    return normalized


def _validate_usage(
    value: Any,
    *,
    source_kind: str,
    failed_before_record: bool,
    path: str,
) -> dict[str, Any]:
    usage = _object(value, path)
    _exact(usage, _USAGE_FIELDS, path)
    model_calls = usage["model_calls"]
    if model_calls is not None:
        _count(model_calls, f"{path}.model_calls")
    for name in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        _nullable_count(usage[name], f"{path}.{name}")
    accounting = usage["reasoning_accounting"]
    if accounting not in {
        None,
        "included-in-output",
        "separately-reported",
        "not-reported",
    }:
        raise VerificationError(f"{path}.reasoning_accounting is invalid")
    if type(usage["usage_complete"]) is not bool:
        raise VerificationError(f"{path}.usage_complete must be boolean")

    if failed_before_record:
        unknown = {
            "model_calls": None,
            "input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "reasoning_accounting": None,
            "total_tokens": None,
            "usage_complete": False,
        }
        if usage != unknown:
            raise VerificationError("failed-before-record usage must remain unknown")
        return _detach(usage)

    external = source_kind == "external-response"
    if model_calls != (1 if external else 0):
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
    if external and total is None:
        if (
            usage["reasoning_tokens"] is not None
            or usage["reasoning_accounting"] not in (None, "not-reported")
        ):
            raise VerificationError(
                f"{path} partial external usage cannot classify reasoning"
            )
    if external and total is not None:
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        if input_tokens is None or output_tokens is None or accounting is None:
            raise VerificationError(f"{path} complete external usage lacks detail")
        reasoning = usage["reasoning_tokens"]
        if accounting == "not-reported":
            if reasoning is not None or total < input_tokens + output_tokens:
                raise VerificationError(f"{path} usage does not reconcile")
        elif accounting == "included-in-output":
            if (
                reasoning is None
                or reasoning > output_tokens
                or total != input_tokens + output_tokens
            ):
                raise VerificationError(f"{path} usage does not reconcile")
        elif (
            reasoning is None
            or total != input_tokens + output_tokens + reasoning
        ):
            raise VerificationError(f"{path} usage does not reconcile")
    return _detach(usage)


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


def _normalize_executed_usage(value: Any, source_kind: str) -> dict[str, Any]:
    supplied = _object(value, "usage")
    normalized = dict(supplied)
    if "usage_complete" not in normalized:
        normalized["usage_complete"] = normalized.get("total_tokens") is not None
    return _validate_usage(
        normalized,
        source_kind=source_kind,
        failed_before_record=False,
        path="usage",
    )


def _validate_activation_input_shape(
    value: Any,
    *,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    path: str,
) -> dict[str, Any]:
    activation = _object(_detach(value), path)
    _exact(
        activation,
        {
            "schema_version",
            "program_sha256",
            "slot_id",
            "activation_predicate",
            "fact_inputs",
        },
        path,
    )
    if activation["schema_version"] != PROGRAM_V2_ACTIVATION_INPUT_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if activation["program_sha256"] != _program_sha256(program):
        raise VerificationError(f"{path}.program_sha256 differs")
    if activation["slot_id"] != slot["slot_id"]:
        raise VerificationError(f"{path}.slot_id differs")
    if activation["activation_predicate"] != slot["activation_predicate"]:
        raise VerificationError(f"{path}.activation_predicate differs")
    conditions = slot["activation_predicate"]["all_of"]
    inputs = _list(activation["fact_inputs"], f"{path}.fact_inputs")
    if len(inputs) != len(conditions):
        raise VerificationError(f"{path}.fact_inputs cardinality differs")
    for index, (raw, condition) in enumerate(zip(inputs, conditions)):
        item_path = f"{path}.fact_inputs[{index}]"
        item = _object(raw, item_path)
        _exact(
            item,
            {
                "source_slot_id",
                "source_record_sha256",
                "source_disposition",
                "fact",
                "observed_value",
            },
            item_path,
        )
        if item["source_slot_id"] != condition["slot_id"]:
            raise VerificationError(f"{item_path}.source_slot_id differs")
        if item["fact"] != condition["fact"]:
            raise VerificationError(f"{item_path}.fact differs")
        _nullable_sha(
            item["source_record_sha256"],
            f"{item_path}.source_record_sha256",
        )
        if item["source_disposition"] not in SLOT_DISPOSITIONS:
            raise VerificationError(f"{item_path}.source_disposition is invalid")
        fact = item["fact"]
        observed = item["observed_value"]
        allowed = set(SLOT_DISPOSITIONS) if fact == "disposition" else _FACT_VALUES[fact]
        if observed is not None and (
            type(observed) is not str or observed not in allowed
        ):
            raise VerificationError(f"{item_path}.observed_value is invalid")
        if fact == "disposition":
            if observed != item["source_disposition"]:
                raise VerificationError(
                    f"{item_path} disposition observation differs"
                )
        elif item["source_record_sha256"] is None and observed is not None:
            raise VerificationError(
                f"{item_path} fact lacks a source-record preimage"
            )
    return _detach(activation)


def _validate_observation(
    value: Any,
    *,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    activation_sha256: str,
    facts: Mapping[str, Any],
    sequence: int,
    path: str,
) -> dict[str, Any]:
    observation = _object(_detach(value), path)
    _exact(observation, _OBSERVATION_FIELDS, path)
    if observation["schema_version"] != PROGRAM_V2_OBSERVATION_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if observation["program_sha256"] != _program_sha256(program):
        raise VerificationError(f"{path}.program_sha256 differs")
    if observation["slot_id"] != slot["slot_id"]:
        raise VerificationError(f"{path}.slot_id differs")
    if observation["activation_input_sha256"] != activation_sha256:
        raise VerificationError(f"{path}.activation_input_sha256 differs")
    if observation["source_kind"] != slot["source_kind"]:
        raise VerificationError(f"{path}.source_kind differs")
    if observation["result_event_sequence"] != sequence:
        raise VerificationError(f"{path}.result_event_sequence differs")
    observed_facts = _normalize_facts(
        observation["facts"],
        component=slot["component"],
        source_kind=slot["source_kind"],
        executed=True,
        path=f"{path}.facts",
    )
    if observed_facts != facts:
        raise VerificationError(f"{path}.facts differs from source record")
    request = _nullable_sha(
        observation["request_sha256"], f"{path}.request_sha256"
    )
    provider = _nullable_sha(
        observation["provider_record_sha256"],
        f"{path}.provider_record_sha256",
    )
    local = _nullable_sha(
        observation["local_observation_sha256"],
        f"{path}.local_observation_sha256",
    )
    if slot["source_kind"] == "external-response":
        if request is None or provider is None or local is not None:
            raise VerificationError(f"{path} external evidence is not exclusive")
    elif request is not None or provider is not None or local is None:
        raise VerificationError(f"{path} local evidence is not exclusive")
    observation["usage"] = _validate_usage(
        observation["usage"],
        source_kind=slot["source_kind"],
        failed_before_record=False,
        path=f"{path}.usage",
    )
    return _detach(observation)


def _validate_failure(
    value: Any,
    *,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    activation_sha256: str,
    path: str,
) -> dict[str, Any]:
    failure = _object(_detach(value), path)
    _exact(failure, _FAILURE_FIELDS, path)
    if failure["schema_version"] != PROGRAM_V2_FAILURE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if failure["program_sha256"] != _program_sha256(program):
        raise VerificationError(f"{path}.program_sha256 differs")
    if failure["slot_id"] != slot["slot_id"]:
        raise VerificationError(f"{path}.slot_id differs")
    if failure["activation_input_sha256"] != activation_sha256:
        raise VerificationError(f"{path}.activation_input_sha256 differs")
    if failure["source_kind"] != slot["source_kind"]:
        raise VerificationError(f"{path}.source_kind differs")
    request = _nullable_sha(failure["request_sha256"], f"{path}.request_sha256")
    _sha(
        failure["failure_artifact_sha256"],
        f"{path}.failure_artifact_sha256",
    )
    if slot["source_kind"] != "external-response" and request is not None:
        raise VerificationError(f"{path} local failure cannot bind a request")
    if failure["result_event_sequence"] is not None:
        raise VerificationError(f"{path} failure cannot consume an event sequence")
    failed_facts = _normalize_facts(
        failure["facts"],
        component=slot["component"],
        source_kind=slot["source_kind"],
        executed=False,
        path=f"{path}.facts",
    )
    if failed_facts != _empty_facts():
        raise VerificationError(f"{path}.facts must remain null")
    failure["usage"] = _validate_usage(
        failure["usage"],
        source_kind=slot["source_kind"],
        failed_before_record=True,
        path=f"{path}.usage",
    )
    return _detach(failure)


def _register_digest(
    registry: dict[str, tuple[str, str]],
    digest: str | None,
    *,
    slot_id: str,
    role: str,
) -> None:
    if digest is None:
        return
    prior = registry.get(digest)
    identity = (slot_id, role)
    if prior is not None and prior != identity:
        raise VerificationError(
            "evidence digest is reused across roles or slots: "
            f"{prior[0]}.{prior[1]}"
        )
    registry[digest] = identity


def _register_source_roles(
    registry: dict[str, tuple[str, str]],
    record: Mapping[str, Any],
    *,
    record_sha256: str | None = None,
) -> None:
    slot_id = record["slot_id"]
    _register_digest(
        registry,
        record_sha256,
        slot_id=slot_id,
        role="source-record",
    )
    _register_digest(
        registry,
        record["activation_input_sha256"],
        slot_id=slot_id,
        role="activation-input",
    )
    _register_digest(
        registry,
        record["observation_sha256"],
        slot_id=slot_id,
        role="observation",
    )
    _register_digest(
        registry,
        record["failure_sha256"],
        slot_id=slot_id,
        role="failure",
    )
    observation = record["observation"]
    if observation is not None:
        for name in (
            "request_sha256",
            "provider_record_sha256",
            "local_observation_sha256",
        ):
            _register_digest(
                registry,
                observation[name],
                slot_id=slot_id,
                role=name,
            )
    failure = record["failure"]
    if failure is not None:
        for name in ("request_sha256", "failure_artifact_sha256"):
            _register_digest(
                registry,
                failure[name],
                slot_id=slot_id,
                role=name,
            )


def validate_program_v2_source_record(
    value: Any,
    program: Any,
    *,
    path: str = "source_record",
) -> dict[str, Any]:
    """Validate one Program /2 record against its exact canonical slot."""

    validated_program = _program(program)
    record = _object(_detach(value), path)
    _exact(record, _SOURCE_RECORD_FIELDS, path)
    if record["schema_version"] != PROGRAM_V2_SOURCE_RECORD_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if record["evidence_boundary"] != PROGRAM_V2_EVIDENCE_BOUNDARY:
        raise VerificationError(f"{path}.evidence_boundary differs")
    program_sha = _program_sha256(validated_program)
    if record["program_sha256"] != program_sha:
        raise VerificationError(f"{path} is replayed under another program")
    if record["record_kind"] not in SOURCE_RECORD_KINDS_V2:
        raise VerificationError(f"{path}.record_kind is invalid")
    if record["session_id"] != validated_program["session_id"]:
        raise VerificationError(f"{path}.session_id differs")
    if record["arm_id"] != validated_program["arm_id"]:
        raise VerificationError(f"{path}.arm_id differs")
    slot_id = _identifier(record["slot_id"], f"{path}.slot_id")
    slot = _slot_map(validated_program).get(slot_id)
    if slot is None:
        raise VerificationError(f"{path} references an unplanned slot")
    task_sha = (
        None
        if slot["task_id"] is None
        else _task_sha_by_id(validated_program)[slot["task_id"]]
    )
    expected = {
        "task_id": slot["task_id"],
        "task_sha256": task_sha,
        "accounting_phase": slot["accounting_phase"],
        "component": slot["component"],
        "source_kind": slot["source_kind"],
        "request_deriver_sha256": slot["request_deriver_sha256"],
        "implementation_sha256": slot["implementation_sha256"],
        "model_binding_sha256": slot["model_binding_sha256"],
        "maximum_calls": slot["maximum_calls"],
    }
    if any(record[name] != expected_value for name, expected_value in expected.items()):
        raise VerificationError(f"{path} domain or frozen binding differs from slot")
    activation = _validate_activation_input_shape(
        record["activation_input"],
        program=validated_program,
        slot=slot,
        path=f"{path}.activation_input",
    )
    activation_sha = _sha(
        record["activation_input_sha256"],
        f"{path}.activation_input_sha256",
    )
    if activation_sha != sha256_ref(activation):
        raise VerificationError(f"{path}.activation_input_sha256 differs")
    sequence = record["result_event_sequence"]
    if sequence is not None:
        _count(sequence, f"{path}.result_event_sequence")
    executed = record["record_kind"] == "executed-source"
    facts = _normalize_facts(
        record["facts"],
        component=slot["component"],
        source_kind=slot["source_kind"],
        executed=executed,
        path=f"{path}.facts",
    )
    observation_sha = _nullable_sha(
        record["observation_sha256"], f"{path}.observation_sha256"
    )
    failure_sha = _nullable_sha(
        record["failure_sha256"], f"{path}.failure_sha256"
    )
    if executed:
        if sequence is None or observation_sha is None or record["observation"] is None:
            raise VerificationError(f"{path} executed source lacks an observation")
        if failure_sha is not None or record["failure"] is not None:
            raise VerificationError(f"{path} executed source has failure evidence")
        observation = _validate_observation(
            record["observation"],
            program=validated_program,
            slot=slot,
            activation_sha256=activation_sha,
            facts=facts,
            sequence=sequence,
            path=f"{path}.observation",
        )
        if observation_sha != sha256_ref(observation):
            raise VerificationError(f"{path}.observation_sha256 differs")
        record["observation"] = observation
    else:
        if sequence is not None or observation_sha is not None or record["observation"] is not None:
            raise VerificationError(f"{path} failed source cannot consume an event")
        if failure_sha is None or record["failure"] is None:
            raise VerificationError(f"{path} failed source lacks failure evidence")
        failure = _validate_failure(
            record["failure"],
            program=validated_program,
            slot=slot,
            activation_sha256=activation_sha,
            path=f"{path}.failure",
        )
        if failure_sha != sha256_ref(failure):
            raise VerificationError(f"{path}.failure_sha256 differs")
        record["failure"] = failure
    record["activation_input"] = activation
    record["facts"] = facts
    record["authority"] = _validate_authority(
        record["authority"], f"{path}.authority"
    )
    normalized = _detach(record)
    registry: dict[str, tuple[str, str]] = {}
    _register_digest(
        registry,
        program_sha,
        slot_id="program",
        role="program",
    )
    _register_source_roles(registry, normalized)
    return normalized


def build_program_v2_source_record(
    program: Any,
    *,
    slot_id: str,
    record_kind: str,
    activation_input: Mapping[str, Any],
    result_event_sequence: int | None = None,
    request_sha256: str | None = None,
    provider_record_sha256: str | None = None,
    local_observation_sha256: str | None = None,
    failure_artifact_sha256: str | None = None,
    usage: Mapping[str, Any] | None = None,
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one exact observation or eventless failure source record."""

    validated_program = _program(program)
    slot = _slot_map(validated_program).get(slot_id)
    if slot is None:
        raise VerificationError("source record references an unplanned slot")
    activation = _validate_activation_input_shape(
        _detach(activation_input),
        program=validated_program,
        slot=slot,
        path="activation_input",
    )
    activation_sha = sha256_ref(activation)
    fact_values = _empty_facts()
    if facts is not None:
        supplied = _object(_detach(facts), "facts")
        if not set(supplied).issubset(_FACT_FIELDS):
            raise VerificationError("facts contains an unknown field")
        fact_values.update(supplied)
    executed = record_kind == "executed-source"
    if record_kind not in SOURCE_RECORD_KINDS_V2:
        raise VerificationError("record_kind is invalid")
    normalized_facts = _normalize_facts(
        fact_values,
        component=slot["component"],
        source_kind=slot["source_kind"],
        executed=executed,
        path="facts",
    )
    program_sha = _program_sha256(validated_program)
    observation = None
    observation_sha = None
    failure = None
    failure_sha = None
    if executed:
        if result_event_sequence is None or usage is None:
            raise VerificationError(
                "executed source requires sequence and observed usage"
            )
        _count(result_event_sequence, "result_event_sequence")
        observed_usage = _normalize_executed_usage(usage, slot["source_kind"])
        observation = {
            "schema_version": PROGRAM_V2_OBSERVATION_SCHEMA,
            "program_sha256": program_sha,
            "slot_id": slot_id,
            "activation_input_sha256": activation_sha,
            "source_kind": slot["source_kind"],
            "request_sha256": request_sha256,
            "provider_record_sha256": provider_record_sha256,
            "local_observation_sha256": local_observation_sha256,
            "result_event_sequence": result_event_sequence,
            "facts": normalized_facts,
            "usage": observed_usage,
        }
        observation = _validate_observation(
            observation,
            program=validated_program,
            slot=slot,
            activation_sha256=activation_sha,
            facts=normalized_facts,
            sequence=result_event_sequence,
            path="observation",
        )
        observation_sha = sha256_ref(observation)
        if failure_artifact_sha256 is not None:
            raise VerificationError("executed source cannot bind a failure artifact")
    else:
        if (
            result_event_sequence is not None
            or provider_record_sha256 is not None
            or local_observation_sha256 is not None
            or usage is not None
            or failure_artifact_sha256 is None
        ):
            raise VerificationError("failed source evidence is ambiguous")
        failure = {
            "schema_version": PROGRAM_V2_FAILURE_SCHEMA,
            "program_sha256": program_sha,
            "slot_id": slot_id,
            "activation_input_sha256": activation_sha,
            "source_kind": slot["source_kind"],
            "request_sha256": request_sha256,
            "failure_artifact_sha256": failure_artifact_sha256,
            "result_event_sequence": None,
            "facts": normalized_facts,
            "usage": _unknown_usage(),
        }
        failure = _validate_failure(
            failure,
            program=validated_program,
            slot=slot,
            activation_sha256=activation_sha,
            path="failure",
        )
        failure_sha = sha256_ref(failure)
    task_sha = (
        None
        if slot["task_id"] is None
        else _task_sha_by_id(validated_program)[slot["task_id"]]
    )
    record = {
        "schema_version": PROGRAM_V2_SOURCE_RECORD_SCHEMA,
        "evidence_boundary": PROGRAM_V2_EVIDENCE_BOUNDARY,
        "program_sha256": program_sha,
        "record_kind": record_kind,
        "session_id": validated_program["session_id"],
        "arm_id": validated_program["arm_id"],
        "task_id": slot["task_id"],
        "task_sha256": task_sha,
        "slot_id": slot_id,
        "accounting_phase": slot["accounting_phase"],
        "component": slot["component"],
        "source_kind": slot["source_kind"],
        "request_deriver_sha256": slot["request_deriver_sha256"],
        "implementation_sha256": slot["implementation_sha256"],
        "model_binding_sha256": slot["model_binding_sha256"],
        "maximum_calls": slot["maximum_calls"],
        "activation_input_sha256": activation_sha,
        "activation_input": activation,
        "observation_sha256": observation_sha,
        "observation": observation,
        "failure_sha256": failure_sha,
        "failure": failure,
        "result_event_sequence": result_event_sequence,
        "facts": normalized_facts,
        "authority": _authority(),
    }
    return validate_program_v2_source_record(record, validated_program)


def _validate_record_entries(
    program: Mapping[str, Any],
    entries: Any,
    *,
    path: str,
    allow_empty: bool,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_entries = _list(entries, path)
    if not raw_entries and not allow_empty:
        raise VerificationError(f"{path} must contain at least one record")
    slot_index = {
        slot["slot_id"]: index for index, slot in enumerate(program["slots"])
    }
    normalized: list[dict[str, Any]] = []
    by_sha: dict[str, dict[str, Any]] = {}
    seen_slots: set[str] = set()
    indices: list[int] = []
    sequences: list[int] = []
    registry: dict[str, tuple[str, str]] = {}
    _register_digest(
        registry,
        _program_sha256(program),
        slot_id="program",
        role="program",
    )
    for index, raw in enumerate(raw_entries):
        entry_path = f"{path}[{index}]"
        entry = _object(raw, entry_path)
        _exact(entry, {"record_sha256", "record"}, entry_path)
        digest = _sha(entry["record_sha256"], f"{entry_path}.record_sha256")
        record = validate_program_v2_source_record(
            entry["record"], program, path=f"{entry_path}.record"
        )
        if digest != sha256_ref(record):
            raise VerificationError(f"{entry_path} content address differs")
        if digest in by_sha or record["slot_id"] in seen_slots:
            raise VerificationError("evidence store contains duplicate source records")
        by_sha[digest] = record
        seen_slots.add(record["slot_id"])
        indices.append(slot_index[record["slot_id"]])
        if record["record_kind"] == "executed-source":
            sequences.append(record["result_event_sequence"])
        _register_source_roles(registry, record, record_sha256=digest)
        normalized.append({"record_sha256": digest, "record": record})
    if indices != sorted(indices):
        raise VerificationError("evidence records must follow canonical program order")
    if sequences != list(range(len(sequences))):
        raise VerificationError(
            "executed event sequences must be contiguous in program order"
        )
    return normalized, by_sha


def validate_program_v2_evidence_store(
    value: Any,
    program: Any,
) -> dict[str, Any]:
    """Validate a Program /2 store only with its exact program preimage."""

    validated_program = _program(program)
    store = _object(_detach(value), "evidence_store")
    _exact(
        store,
        {
            "schema_version",
            "evidence_boundary",
            "program_sha256",
            "records",
            "authority",
        },
        "evidence_store",
    )
    if store["schema_version"] != PROGRAM_V2_EVIDENCE_STORE_SCHEMA:
        raise VerificationError("evidence_store.schema_version differs")
    if store["evidence_boundary"] != PROGRAM_V2_EVIDENCE_BOUNDARY:
        raise VerificationError("evidence_store.evidence_boundary differs")
    if store["program_sha256"] != _program_sha256(validated_program):
        raise VerificationError("evidence store is replayed under another program")
    records, _ = _validate_record_entries(
        validated_program,
        store["records"],
        path="evidence_store.records",
        allow_empty=False,
    )
    authority = _validate_authority(store["authority"], "evidence_store.authority")
    normalized = _detach(store)
    normalized["records"] = records
    normalized["authority"] = authority
    return normalized


def build_program_v2_evidence_store(
    program: Any,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validated_program = _program(program)
    if type(records) not in {list, tuple}:
        raise VerificationError("records must be a list or tuple")
    entries = [
        {
            "record_sha256": sha256_ref(record),
            "record": _detach(record),
        }
        for record in records
    ]
    store = {
        "schema_version": PROGRAM_V2_EVIDENCE_STORE_SCHEMA,
        "evidence_boundary": PROGRAM_V2_EVIDENCE_BOUNDARY,
        "program_sha256": _program_sha256(validated_program),
        "records": entries,
        "authority": _authority(),
    }
    return validate_program_v2_evidence_store(store, validated_program)


def _validate_resolution_item(
    value: Any,
    *,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    path: str,
) -> dict[str, Any]:
    item = _object(_detach(value), path)
    _exact(item, _RESOLUTION_ITEM_FIELDS, path)
    if item["slot_id"] != slot["slot_id"]:
        raise VerificationError(f"{path}.slot_id differs from canonical order")
    disposition = item["disposition"]
    if disposition not in SLOT_DISPOSITIONS:
        raise VerificationError(f"{path}.disposition is invalid")
    activation = _validate_activation_input_shape(
        item["activation_input"],
        program=program,
        slot=slot,
        path=f"{path}.activation_input",
    )
    activation_sha = _sha(
        item["activation_input_sha256"],
        f"{path}.activation_input_sha256",
    )
    if activation_sha != sha256_ref(activation):
        raise VerificationError(f"{path}.activation_input_sha256 differs")
    source_digest = _nullable_sha(
        item["source_record_sha256"], f"{path}.source_record_sha256"
    )
    sequence = item["result_event_sequence"]
    if sequence is not None:
        _count(sequence, f"{path}.result_event_sequence")
    if disposition == "not-activated":
        if source_digest is not None or sequence is not None:
            raise VerificationError("not-activated slot must remain recordless and eventless")
    elif source_digest is None:
        raise VerificationError("activated slot requires a source record")
    elif disposition == "executed" and sequence is None:
        raise VerificationError("executed slot requires an event sequence")
    elif disposition == "failed-before-record" and sequence is not None:
        raise VerificationError("failed-before-record slot must remain eventless")
    normalized = _detach(item)
    normalized["activation_input"] = activation
    return normalized


def _activation_preimage(
    *,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    prior_by_slot: Mapping[str, Mapping[str, Any]],
    records_by_sha: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], bool | None]:
    fact_inputs: list[dict[str, Any]] = []
    saw_false = False
    saw_unknown = False
    for condition in slot["activation_predicate"]["all_of"]:
        source = prior_by_slot.get(condition["slot_id"])
        if source is None:
            raise VerificationError("activation input lacks a prior resolution")
        source_digest = source["source_record_sha256"]
        if condition["fact"] == "disposition":
            observed: str | None = source["disposition"]
        elif source_digest is None:
            observed = None
        else:
            observed = records_by_sha[source_digest]["facts"][condition["fact"]]
        fact_inputs.append(
            {
                "source_slot_id": condition["slot_id"],
                "source_record_sha256": source_digest,
                "source_disposition": source["disposition"],
                "fact": condition["fact"],
                "observed_value": observed,
            }
        )
        if observed is None:
            saw_unknown = True
        elif observed not in condition["equals_any"]:
            saw_false = True
    activation = {
        "schema_version": PROGRAM_V2_ACTIVATION_INPUT_SCHEMA,
        "program_sha256": _program_sha256(program),
        "slot_id": slot["slot_id"],
        "activation_predicate": slot["activation_predicate"],
        "fact_inputs": fact_inputs,
    }
    truth: bool | None = False if saw_false else None if saw_unknown else True
    return _detach(activation), truth


def _allowed_dispositions(truth: bool | None) -> set[str]:
    if truth is True:
        return {"executed", "failed-before-record"}
    if truth is False:
        return {"not-activated"}
    return {"failed-before-record"}


def _replay_prefix(
    program: Mapping[str, Any],
    resolutions: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    *,
    length: int,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    list[str],
    int,
]:
    if type(resolutions) not in {list, tuple}:
        raise VerificationError("resolutions must be a list or tuple")
    if type(records) not in {list, tuple}:
        raise VerificationError("records must be a list or tuple")
    if len(resolutions) != length:
        raise VerificationError("resolution prefix must cover every prior slot")
    entries = [
        {"record_sha256": sha256_ref(record), "record": _detach(record)}
        for record in records
    ]
    _, records_by_sha = _validate_record_entries(
        program,
        entries,
        path="records",
        allow_empty=True,
    )
    prior_by_slot: dict[str, dict[str, Any]] = {}
    used_records: list[str] = []
    executed_slot_ids: list[str] = []
    next_sequence = 0
    slots = program["slots"]
    for index, (slot, raw) in enumerate(zip(slots[:length], resolutions)):
        item = _validate_resolution_item(
            raw,
            program=program,
            slot=slot,
            path=f"resolutions[{index}]",
        )
        expected_activation, truth = _activation_preimage(
            program=program,
            slot=slot,
            prior_by_slot=prior_by_slot,
            records_by_sha=records_by_sha,
        )
        if item["activation_input"] != expected_activation:
            raise VerificationError("activation input differs from predicate replay")
        if item["activation_input_sha256"] != sha256_ref(expected_activation):
            raise VerificationError("activation input digest differs from predicate replay")
        if item["disposition"] not in _allowed_dispositions(truth):
            state = "true" if truth is True else "false" if truth is False else "unknown"
            raise VerificationError(f"{state} activation has an inconsistent disposition")
        source_digest = item["source_record_sha256"]
        if source_digest is not None:
            source = records_by_sha.get(source_digest)
            if source is None or source["slot_id"] != slot["slot_id"]:
                raise VerificationError("resolution source record is cross-wired")
            expected_kind = (
                "executed-source"
                if item["disposition"] == "executed"
                else "failure-before-source-record"
            )
            if source["record_kind"] != expected_kind:
                raise VerificationError("resolution source-record kind differs")
            if (
                source["activation_input"] != expected_activation
                or source["activation_input_sha256"]
                != item["activation_input_sha256"]
            ):
                raise VerificationError("source record activation input differs")
            if source_digest in used_records:
                raise VerificationError("source record resolves more than one slot")
            used_records.append(source_digest)
            if item["disposition"] == "executed":
                if (
                    source["result_event_sequence"] != next_sequence
                    or item["result_event_sequence"] != next_sequence
                ):
                    raise VerificationError(
                        "executed event sequences must follow canonical program order"
                    )
                executed_slot_ids.append(slot["slot_id"])
                next_sequence += 1
            elif (
                source["result_event_sequence"] is not None
                or item["result_event_sequence"] is not None
            ):
                raise VerificationError("failed-before-record slot consumed an event")
        prior_by_slot[slot["slot_id"]] = item
    record_order = [sha256_ref(record) for record in records]
    if used_records != record_order:
        raise VerificationError(
            "records must contain exactly the used prefix records in program order"
        )
    return prior_by_slot, records_by_sha, executed_slot_ids, next_sequence


def derive_program_v2_activation_input(
    program: Any,
    *,
    slot_id: str,
    prior_resolutions: Sequence[Mapping[str, Any]],
    prior_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive one exact activation preimage from a validated prior prefix."""

    validated_program = _program(program)
    index_by_slot = {
        slot["slot_id"]: index
        for index, slot in enumerate(validated_program["slots"])
    }
    if slot_id not in index_by_slot:
        raise VerificationError("activation input references an unplanned slot")
    index = index_by_slot[slot_id]
    prior_by_slot, records_by_sha, _, _ = _replay_prefix(
        validated_program,
        prior_resolutions,
        prior_records,
        length=index,
    )
    activation, _ = _activation_preimage(
        program=validated_program,
        slot=validated_program["slots"][index],
        prior_by_slot=prior_by_slot,
        records_by_sha=records_by_sha,
    )
    return activation


def build_program_v2_resolution_item(
    program: Any,
    *,
    slot_id: str,
    disposition: str,
    activation_input: Mapping[str, Any],
    source_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    validated_program = _program(program)
    slot = _slot_map(validated_program).get(slot_id)
    if slot is None:
        raise VerificationError("resolution references an unplanned slot")
    activation = _validate_activation_input_shape(
        _detach(activation_input),
        program=validated_program,
        slot=slot,
        path="activation_input",
    )
    source = (
        None
        if source_record is None
        else validate_program_v2_source_record(source_record, validated_program)
    )
    if source is not None and source["slot_id"] != slot_id:
        raise VerificationError("resolution source record is cross-wired")
    item = {
        "slot_id": slot_id,
        "disposition": disposition,
        "activation_input_sha256": sha256_ref(activation),
        "activation_input": activation,
        "source_record_sha256": None if source is None else sha256_ref(source),
        "result_event_sequence": (
            None if source is None else source["result_event_sequence"]
        ),
    }
    return _validate_resolution_item(
        item,
        program=validated_program,
        slot=slot,
        path="resolution",
    )


def _validate_output_verdicts(
    program: Mapping[str, Any],
    resolutions: Sequence[Mapping[str, Any]],
    records_by_sha: Mapping[str, Mapping[str, Any]],
) -> None:
    by_slot = {item["slot_id"]: item for item in resolutions}
    by_task_component = {
        (slot["task_id"], slot["component"]): slot for slot in program["slots"]
    }
    for slot in program["slots"]:
        if slot["component"] != "output-validator":
            continue
        item = by_slot[slot["slot_id"]]
        source_sha = item["source_record_sha256"]
        if item["disposition"] != "executed" or source_sha is None:
            continue
        source = records_by_sha[source_sha]
        if source["facts"]["output_verdict"] != "valid":
            continue
        primary_slot = by_task_component[(slot["task_id"], "primary")]
        primary_item = by_slot[primary_slot["slot_id"]]
        primary_sha = primary_item["source_record_sha256"]
        primary_record = (
            None if primary_sha is None else records_by_sha[primary_sha]
        )
        if (
            primary_item["disposition"] != "executed"
            or primary_record is None
            or primary_record["facts"]["terminal_status"] != "completed"
        ):
            raise VerificationError(
                "output validator cannot mark a failed or noncompleted primary valid"
            )


def _resolution_digest(core: Mapping[str, Any]) -> str:
    return sha256_ref(
        {
            "schema_version": PROGRAM_V2_RESOLUTION_DIGEST_SCHEMA,
            **core,
        }
    )


def resolve_program_v2_evidence(
    program: Any,
    resolutions: Sequence[Mapping[str, Any]],
    evidence_store: Any,
) -> dict[str, Any]:
    """Replay a complete Program /2 closure in canonical slot order."""

    validated_program = _program(program)
    store = validate_program_v2_evidence_store(evidence_store, validated_program)
    if type(resolutions) not in {list, tuple}:
        raise VerificationError("resolutions must be a list or tuple")
    if len(resolutions) != len(validated_program["slots"]):
        raise VerificationError("resolutions must cover every Program /2 slot")
    records = [entry["record"] for entry in store["records"]]
    prior_by_slot, records_by_sha, executed_slot_ids, _ = _replay_prefix(
        validated_program,
        resolutions,
        records,
        length=len(validated_program["slots"]),
    )
    normalized_resolutions = [
        prior_by_slot[slot["slot_id"]] for slot in validated_program["slots"]
    ]
    _validate_output_verdicts(
        validated_program,
        normalized_resolutions,
        records_by_sha,
    )

    registry: dict[str, tuple[str, str]] = {}
    program_sha = _program_sha256(validated_program)
    _register_digest(
        registry,
        program_sha,
        slot_id="program",
        role="program",
    )
    for entry in store["records"]:
        _register_source_roles(
            registry,
            entry["record"],
            record_sha256=entry["record_sha256"],
        )
    for item in normalized_resolutions:
        _register_digest(
            registry,
            item["activation_input_sha256"],
            slot_id=item["slot_id"],
            role="activation-input",
        )
        _register_digest(
            registry,
            item["source_record_sha256"],
            slot_id=item["slot_id"],
            role="source-record",
        )
    store_sha = sha256_ref(store)
    _register_digest(
        registry,
        store_sha,
        slot_id="evidence-store",
        role="evidence-store",
    )
    authority = _authority()
    core = {
        "program_sha256": program_sha,
        "evidence_store_sha256": store_sha,
        "resolutions": normalized_resolutions,
        "executed_slot_ids": executed_slot_ids,
        "authority": authority,
    }
    resolution_sha = _resolution_digest(core)
    _register_digest(
        registry,
        resolution_sha,
        slot_id="resolution",
        role="resolution",
    )
    return {
        "schema_version": PROGRAM_V2_RESOLUTION_SCHEMA,
        "evidence_boundary": PROGRAM_V2_EVIDENCE_BOUNDARY,
        "program_sha256": program_sha,
        "program": validated_program,
        "evidence_store_sha256": store_sha,
        "evidence_store": store,
        "resolutions": normalized_resolutions,
        "executed_slot_ids": executed_slot_ids,
        "authority": authority,
        "resolution_sha256": resolution_sha,
    }


def validate_resolved_program_v2_evidence(value: Any) -> dict[str, Any]:
    """Recompute an entire Program /2 closure and its domain-separated digest."""

    artifact = _object(_detach(value), "resolved_program_v2")
    _exact(
        artifact,
        {
            "schema_version",
            "evidence_boundary",
            "program_sha256",
            "program",
            "evidence_store_sha256",
            "evidence_store",
            "resolutions",
            "executed_slot_ids",
            "authority",
            "resolution_sha256",
        },
        "resolved_program_v2",
    )
    if artifact["schema_version"] != PROGRAM_V2_RESOLUTION_SCHEMA:
        raise VerificationError("resolved_program_v2.schema_version differs")
    if artifact["evidence_boundary"] != PROGRAM_V2_EVIDENCE_BOUNDARY:
        raise VerificationError("resolved_program_v2.evidence_boundary differs")
    _sha(artifact["program_sha256"], "resolved_program_v2.program_sha256")
    _sha(
        artifact["evidence_store_sha256"],
        "resolved_program_v2.evidence_store_sha256",
    )
    _sha(
        artifact["resolution_sha256"],
        "resolved_program_v2.resolution_sha256",
    )
    _validate_authority(artifact["authority"], "resolved_program_v2.authority")
    recomputed = resolve_program_v2_evidence(
        artifact["program"],
        artifact["resolutions"],
        artifact["evidence_store"],
    )
    if canonical_json(artifact) != canonical_json(recomputed):
        raise VerificationError("resolved Program /2 closure or digest differs")
    return _detach(artifact)
