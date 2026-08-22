"""Strict provider-neutral execution-trace contract for offline assembly.

The trace binds externally captured calls and deterministic local events to the
already frozen initial-goal study plan.  It grants no network, credential,
spending, authentication, or claim authority.  A trace is only an exact input
to :mod:`initial_goal_eval.trace_assembler`.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from competitive_eval.protocol import CallRequest
from competitive_eval.canonical import canonical_json as competitive_canonical_json
from competitive_eval.hybrid_external_replay import (
    HYBRID_ARM,
    HybridReceiverExternalCall,
)

from .contract import (
    ARMS,
    EVENT_PHASES,
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
    validate_study_plan,
)
from .terminal_contract import (
    CANONICAL_SILENCE_OUTPUT_SHA256,
    CAPTURE_TERMINAL_STATUSES,
    SILENCE_TERMINAL_STATUS,
)


TRACE_SCHEMA = "urusilla-initial-goal-execution-trace/2"
ARM_EXECUTION_MANIFEST_SCHEMA = "urusilla-initial-goal-arm-execution-content/2"
ROUTE_DECISION_SCHEMA = "urusilla-initial-goal-route-decision/1"
TASK_INPUT_SCHEMA = "urusilla-initial-goal-task-input/1"
POST_RECEIVER_VALIDATION_SCHEMA = (
    "urusilla-initial-goal-post-receiver-semantic-validation/1"
)
TRACE_BOUNDARY = "offline-content-bound-not-authenticated"
AUTHENTICATION_STATUS = "not-authenticated-fail-closed"
SOURCE_KINDS = (
    "external-response",
    "deterministic-local",
    "deterministic-validator",
)
LOCAL_SOURCE_PHASES = ("setup", "sender", "router", "tool", "safety", "judge")
BASELINE_ROUTE_MODES = ("raw", "json")
ROUTE_REQUEST_ARMS = {
    "routine": "hybrid-router",
    "raw": "raw-concise",
    "json": "ordinary-json",
}
PRE_RECEIVER_FALLBACK_PREFIXES = (
    "action-state:compiler",
    "action-state:sender",
    "action-state:semantic",
    "action-state:fidelity",
)
_CALL_ID = re.compile(r"^[0-9a-f]{64}$")


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _call_id(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or _CALL_ID.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise VerificationError(f"{path} must be a lowercase call ID{suffix}")
    return value


def route_decision_sha256(*, task_id: str, selected_mode: str) -> str:
    """Bind the router's exact pre-receiver mode without binding later output."""

    return sha256_ref(
        {
            "schema_version": ROUTE_DECISION_SCHEMA,
            "task_id": task_id,
            "selected_mode": selected_mode,
        }
    )


def task_input_sha256(messages: Sequence[Mapping[str, str]]) -> str:
    """Digest the exact task-bearing provider-neutral message sequence."""

    normalized: list[dict[str, str]] = []
    if type(messages) not in {list, tuple} or not messages:
        raise VerificationError("task input messages must be a non-empty sequence")
    for index, raw in enumerate(messages):
        message = _object(raw, f"task input messages[{index}]")
        _exact(message, {"role", "content"}, f"task input messages[{index}]")
        if message["role"] not in {"system", "user", "assistant"}:
            raise VerificationError(f"task input messages[{index}].role is invalid")
        if type(message["content"]) is not str:
            raise VerificationError(
                f"task input messages[{index}].content must be text"
            )
        normalized.append(dict(message))
    return sha256_ref(
        {
            "schema_version": TASK_INPUT_SCHEMA,
            "provider_neutral_messages": normalized,
        }
    )


def post_receiver_validation_input_sha256(
    *,
    task_id: str,
    task_sha256: str,
    primary_event_sequence: int,
    primary_output_sha256: str,
) -> str:
    """Bind the exact task and completed primary output presented to a validator."""

    return sha256_ref(
        {
            "schema_version": POST_RECEIVER_VALIDATION_SCHEMA,
            "record_kind": "validator-input",
            "task_id": task_id,
            "task_sha256": task_sha256,
            "primary_event_sequence": primary_event_sequence,
            "primary_output_sha256": primary_output_sha256,
        }
    )


def post_receiver_validation_output_sha256(
    *, input_sha256: str, verdict: str, reason_code: str
) -> str:
    """Bind one deterministic semantic verdict without embedding provider text."""

    return sha256_ref(
        {
            "schema_version": POST_RECEIVER_VALIDATION_SCHEMA,
            "record_kind": "validator-output",
            "input_sha256": input_sha256,
            "verdict": verdict,
            "reason_code": reason_code,
        }
    )


def _validate_task_inputs(
    value: Any,
    *,
    planned_tasks: Sequence[Mapping[str, Any]],
    path: str,
) -> dict[str, list[dict[str, str]]]:
    raw_inputs = _list(value, path)
    if len(raw_inputs) != len(planned_tasks):
        raise VerificationError(f"{path} must reveal every planned task input once")
    result: dict[str, list[dict[str, str]]] = {}
    for index, (raw, task) in enumerate(zip(raw_inputs, planned_tasks)):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path)
        _exact(
            item,
            {"task_id", "task_sha256", "provider_neutral_messages"},
            item_path,
        )
        if item["task_id"] != task["task_id"]:
            raise VerificationError(f"{item_path} binds the wrong planned task")
        if item["task_sha256"] != task["task_sha256"]:
            raise VerificationError(f"{item_path} task digest differs from the plan")
        messages = _list(
            item["provider_neutral_messages"],
            f"{item_path}.provider_neutral_messages",
        )
        observed_sha256 = task_input_sha256(messages)
        if observed_sha256 != task["task_sha256"]:
            raise VerificationError(
                f"{item_path} input preimage does not match the planned task digest"
            )
        result[task["task_id"]] = [dict(message) for message in messages]
    return result


def _validate_external_execution_binding(value: Any, path: str) -> dict[str, Any]:
    binding = _object(value, path)
    _exact(
        binding,
        {
            "run_id",
            "run_manifest_sha256",
            "episode_sequence_sha256",
            "execution_profile_sha256",
            "bundle_record_sequence",
        },
        path,
    )
    for field in (
        "run_id",
        "run_manifest_sha256",
        "episode_sequence_sha256",
        "execution_profile_sha256",
    ):
        _sha(binding[field], f"{path}.{field}")
    _count(binding["bundle_record_sequence"], f"{path}.bundle_record_sequence")
    return binding


def _validate_external_trace_order(sessions: Sequence[Mapping[str, Any]]) -> None:
    """Match each precommitted bundle sequence to actual session/arm chronology."""

    by_bundle: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for session in sessions:
        arm_by_id = {arm["arm_id"]: arm for arm in session["arms"]}
        for arm_id in session["executed_arm_order"]:
            for event in arm_by_id[arm_id]["events"]:
                source = event["source"]
                if source["kind"] == "external-response":
                    by_bundle.setdefault(source["bundle_sha256"], []).append(
                        (session["operator_id"], source)
                    )

    seen_run_ids: dict[str, str] = {}
    for bundle_sha256, entries in by_bundle.items():
        expected_identity: dict[str, Any] | None = None
        expected_operator: str | None = None
        for expected_sequence, (operator_id, source) in enumerate(entries):
            binding = source["execution_binding"]
            identity = {
                key: binding[key]
                for key in (
                    "run_id",
                    "run_manifest_sha256",
                    "episode_sequence_sha256",
                    "execution_profile_sha256",
                )
            }
            if binding["bundle_record_sequence"] != expected_sequence:
                raise VerificationError(
                    "external bundle record order differs from executed session/arm order"
                )
            if expected_identity is None:
                expected_identity = identity
                expected_operator = operator_id
            elif identity != expected_identity or operator_id != expected_operator:
                raise VerificationError(
                    "one external bundle crosses a precommitted run/profile/operator boundary"
                )
        assert expected_identity is not None
        run_id = expected_identity["run_id"]
        previous_bundle = seen_run_ids.get(run_id)
        if previous_bundle is not None and previous_bundle != bundle_sha256:
            raise VerificationError(
                "one precommitted external run ID is split across multiple bundles"
            )
        seen_run_ids[run_id] = bundle_sha256


def build_arm_execution_manifest(
    *,
    session_id: str,
    arm_id: str,
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Commit the ordered task/phase/source inputs before responses are known.

    External bundle digests are deliberately excluded because response bundles
    are created after execution.  The exact request, model-neutral messages,
    optional hybrid projection, run/profile identity, and expected bundle
    record position are committed instead.
    """

    manifest_events: list[dict[str, Any]] = []
    for event in events:
        source = _object(event["source"], "manifest event source")
        if source.get("kind") == "external-response":
            request = CallRequest.from_value(source["call_request"])
            projection = source.get("hybrid_projection")
            execution_binding = _validate_external_execution_binding(
                source.get("execution_binding"),
                "manifest event source.execution_binding",
            )
            projection_sha256 = (
                None
                if projection is None
                else "sha256:" + projection["projection_sha256"]
            )
            source_commitment = {
                "kind": "external-response",
                "call_request": request.value,
                "hybrid_projection": projection,
                "execution_binding": execution_binding,
            }
            request_sha256 = "sha256:" + request.request_sha256
            messages_sha256 = sha256_ref(
                {"provider_neutral_messages": request.value["messages"]}
            )
            source_id = request.call_id
            external_execution_binding_sha256 = sha256_ref(execution_binding)
            bundle_record_sequence = execution_binding["bundle_record_sequence"]
        elif source.get("kind") == "deterministic-local":
            projection_sha256 = None
            source_commitment = source
            request_sha256 = None
            messages_sha256 = None
            source_id = source["local_event_id"]
            external_execution_binding_sha256 = None
            bundle_record_sequence = None
        elif source.get("kind") == "deterministic-validator":
            # The manifest commits the validator before the provider response is
            # known.  Response-bound input/output digests and the verdict remain
            # observed trace evidence and are checked against the capture during
            # assembly; including them here would make pre-registration impossible.
            _exact(
                source,
                {
                    "kind",
                    "schema_version",
                    "local_event_id",
                    "implementation_sha256",
                    "task_sha256",
                    "primary_event_sequence",
                    "primary_output_sha256",
                    "verdict",
                    "reason_code",
                    "input_sha256",
                    "output_sha256",
                    "usage",
                },
                "manifest deterministic validator source",
            )
            projection_sha256 = None
            source_commitment = {
                "kind": "deterministic-validator",
                "schema_version": source["schema_version"],
                "local_event_id": source["local_event_id"],
                "implementation_sha256": source["implementation_sha256"],
                "task_sha256": source["task_sha256"],
                "primary_event_sequence": source["primary_event_sequence"],
            }
            request_sha256 = None
            messages_sha256 = None
            source_id = source["local_event_id"]
            external_execution_binding_sha256 = None
            bundle_record_sequence = None
        else:
            raise VerificationError("execution manifest source kind is invalid")
        manifest_events.append(
            {
                "sequence": event["sequence"],
                "task_id": event["task_id"],
                "phase": event["phase"],
                "source_kind": source["kind"],
                "source_id": source_id,
                "request_sha256": request_sha256,
                "messages_sha256": messages_sha256,
                "hybrid_projection_sha256": projection_sha256,
                "external_execution_binding_sha256": (
                    external_execution_binding_sha256
                ),
                "bundle_record_sequence": bundle_record_sequence,
                "source_commitment_sha256": sha256_ref(source_commitment),
            }
        )
    return {
        "schema_version": ARM_EXECUTION_MANIFEST_SCHEMA,
        "session_id": session_id,
        "arm_id": arm_id,
        "events": manifest_events,
    }


def _validate_source(
    value: Any,
    *,
    session: Mapping[str, Any],
    arm_id: str,
    task_by_id: Mapping[str, Mapping[str, Any]],
    task_input_by_id: Mapping[str, Sequence[Mapping[str, str]]],
    semantic_scorer_sha256: str,
    phase: str,
    task_id: str | None,
    path: str,
) -> tuple[str, str]:
    source = _object(value, path)
    kind = source.get("kind")
    if kind == "external-response":
        _exact(
            source,
            {
                "kind",
                "bundle_sha256",
                "call_request",
                "hybrid_projection",
                "execution_binding",
            },
            path,
        )
        _sha(source["bundle_sha256"], f"{path}.bundle_sha256")
        _validate_external_execution_binding(
            source["execution_binding"], f"{path}.execution_binding"
        )
        try:
            request = CallRequest.from_value(
                _object(source["call_request"], f"{path}.call_request")
            )
        except Exception as exc:
            raise VerificationError(f"{path}.call_request is invalid: {exc}") from exc
        request_value = request.value
        if request_value["episode_id"] != session["session_id"]:
            raise VerificationError(f"{path} call is bound to the wrong frozen session")
        if (
            task_id is not None
            and source["hybrid_projection"] is None
            and request_value["mock_metadata"]["scenario_key"]
            != task_by_id[task_id]["task_sha256"]
        ):
            raise VerificationError(
                f"{path} call request is bound to the wrong frozen task"
            )
        if task_id is not None and source["hybrid_projection"] is None:
            expected_task_messages = list(task_input_by_id[task_id])
            submitted_messages = request_value["messages"]
            if (
                len(submitted_messages) < len(expected_task_messages)
                or submitted_messages[-len(expected_task_messages) :]
                != expected_task_messages
            ):
                raise VerificationError(
                    f"{path} submitted messages do not contain the exact frozen "
                    "task input suffix"
                )
        hybrid_projection = source["hybrid_projection"]
        if hybrid_projection is None:
            allowed_arms = {arm_id}
            if arm_id == "hybrid-router" and phase in {"receiver", "fallback"}:
                allowed_arms.update(ROUTE_REQUEST_ARMS.values())
            if request_value["arm"] not in allowed_arms:
                raise VerificationError(f"{path} call is bound to the wrong arm")
        else:
            if arm_id != "hybrid-router" or phase != "receiver" or task_id is None:
                raise VerificationError(
                    f"{path} hybrid projection is only valid for a hybrid receiver task"
                )
            projection_binding = _object(
                hybrid_projection, f"{path}.hybrid_projection"
            )
            _exact(
                projection_binding,
                {"projection_sha256", "projection", "planned_task_sha256"},
                f"{path}.hybrid_projection",
            )
            if (
                projection_binding["planned_task_sha256"]
                != task_by_id[task_id]["task_sha256"]
            ):
                raise VerificationError(f"{path} hybrid projection binds the wrong task")
            if request_value["arm"] != HYBRID_ARM:
                raise VerificationError(f"{path} hybrid projection call arm differs")
            try:
                HybridReceiverExternalCall(
                    _projection_json=competitive_canonical_json(
                        _object(
                            projection_binding["projection"],
                            f"{path}.hybrid_projection.projection",
                        )
                    ),
                    projection_sha256=projection_binding["projection_sha256"],
                    _call_request_json=request.to_json(),
                )
            except Exception as exc:
                raise VerificationError(
                    f"{path} hybrid projection binding is invalid: {exc}"
                ) from exc
        purpose = request_value["purpose"]
        if (phase == "repair") != (purpose == "format_repair"):
            raise VerificationError(f"{path} repair phase and call purpose differ")
        return kind, request.call_id

    if kind == "deterministic-local":
        _exact(
            source,
            {
                "kind",
                "local_event_id",
                "implementation_sha256",
                "input_sha256",
                "output_sha256",
                "usage",
            },
            path,
        )
        if phase not in LOCAL_SOURCE_PHASES:
            raise VerificationError(f"{path} phase requires an external model capture")
        local_id = _identifier(source["local_event_id"], f"{path}.local_event_id")
        _sha(source["implementation_sha256"], f"{path}.implementation_sha256")
        if source["input_sha256"] is not None:
            _sha(source["input_sha256"], f"{path}.input_sha256")
        if source["output_sha256"] is not None:
            _sha(source["output_sha256"], f"{path}.output_sha256")
        _object(source["usage"], f"{path}.usage")
        return kind, local_id

    if kind == "deterministic-validator":
        _exact(
            source,
            {
                "kind",
                "schema_version",
                "local_event_id",
                "implementation_sha256",
                "task_sha256",
                "primary_event_sequence",
                "primary_output_sha256",
                "verdict",
                "reason_code",
                "input_sha256",
                "output_sha256",
                "usage",
            },
            path,
        )
        if arm_id != "hybrid-router" or phase != "safety" or task_id is None:
            raise VerificationError(
                f"{path} deterministic validator must be a task-bound hybrid "
                "safety-accounting event"
            )
        if source["schema_version"] != POST_RECEIVER_VALIDATION_SCHEMA:
            raise VerificationError(f"{path} validator schema differs")
        local_id = _identifier(source["local_event_id"], f"{path}.local_event_id")
        implementation_sha256 = _sha(
            source["implementation_sha256"], f"{path}.implementation_sha256"
        )
        if implementation_sha256 != semantic_scorer_sha256:
            raise VerificationError(
                f"{path} validator is not the frozen semantic scorer"
            )
        if source["task_sha256"] != task_by_id[task_id]["task_sha256"]:
            raise VerificationError(f"{path} validator binds the wrong frozen task")
        primary_sequence = _count(
            source["primary_event_sequence"], f"{path}.primary_event_sequence"
        )
        assert primary_sequence is not None
        primary_output_sha256 = _sha(
            source["primary_output_sha256"], f"{path}.primary_output_sha256"
        )
        if source["verdict"] != "invalid":
            raise VerificationError(f"{path} validator verdict must be invalid")
        if source["reason_code"] != "semantic-invalid":
            raise VerificationError(
                f"{path} validator reason must be semantic-invalid"
            )
        expected_input = post_receiver_validation_input_sha256(
            task_id=task_id,
            task_sha256=source["task_sha256"],
            primary_event_sequence=primary_sequence,
            primary_output_sha256=primary_output_sha256,
        )
        if source["input_sha256"] != expected_input:
            raise VerificationError(f"{path} validator input digest differs")
        expected_output = post_receiver_validation_output_sha256(
            input_sha256=expected_input,
            verdict=source["verdict"],
            reason_code=source["reason_code"],
        )
        if source["output_sha256"] != expected_output:
            raise VerificationError(f"{path} validator output digest differs")
        _object(source["usage"], f"{path}.usage")
        return kind, local_id

    raise VerificationError(f"{path}.kind must be one of {list(SOURCE_KINDS)}")


def validate_execution_trace(plan_value: Any, trace_value: Any) -> dict[str, Any]:
    """Validate and detach one complete, non-claim execution trace."""

    validate_study_plan(plan_value)
    plan = _object(plan_value, "plan")
    trace = _object(trace_value, "trace")
    _exact(
        trace,
        {
            "schema_version",
            "plan_sha256",
            "evidence_boundary",
            "offline_only",
            "claim_eligible",
            "authentication_status",
            "external_bundle_sha256s",
            "sessions",
            "trace_sha256",
        },
        "trace",
    )
    if trace["schema_version"] != TRACE_SCHEMA:
        raise VerificationError("execution trace schema differs")
    if trace["plan_sha256"] != sha256_ref(plan):
        raise VerificationError("execution trace does not bind the frozen study plan")
    if trace["evidence_boundary"] != TRACE_BOUNDARY:
        raise VerificationError("execution trace evidence boundary differs")
    if trace["offline_only"] is not True:
        raise VerificationError("execution trace must remain offline-only")
    if trace["claim_eligible"] is not False:
        raise VerificationError("execution trace cannot be claim-eligible")
    if trace["authentication_status"] != AUTHENTICATION_STATUS:
        raise VerificationError("execution trace cannot overstate authentication")

    bundle_ids = _list(
        trace["external_bundle_sha256s"], "trace.external_bundle_sha256s"
    )
    for index, digest in enumerate(bundle_ids):
        _sha(digest, f"trace.external_bundle_sha256s[{index}]")
    if bundle_ids != sorted(set(bundle_ids)):
        raise VerificationError(
            "trace.external_bundle_sha256s must be unique and sorted"
        )

    planned_sessions = plan["sessions"]
    raw_sessions = _list(trace["sessions"], "trace.sessions")
    if len(raw_sessions) != len(planned_sessions):
        raise VerificationError("execution trace must contain every frozen session")

    observed_external: set[str] = set()
    seen_calls: set[str] = set()
    seen_local_events: set[str] = set()
    for session_index, planned in enumerate(planned_sessions):
        path = f"trace.sessions[{session_index}]"
        session = _object(raw_sessions[session_index], path)
        _exact(
            session,
            {
                "session_id",
                "cluster_id",
                "domain_id",
                "receiver_family",
                "operator_id",
                "executed_arm_order",
                "task_inputs",
                "attestation",
                "arms",
            },
            path,
        )
        for field in (
            "session_id",
            "cluster_id",
            "domain_id",
            "receiver_family",
            "operator_id",
        ):
            if session[field] != planned[field]:
                raise VerificationError(f"{path}.{field} differs from the frozen session")
        if session["executed_arm_order"] != planned["arm_order"]:
            raise VerificationError(f"{path}.executed_arm_order differs from the frozen order")
        _object(session["attestation"], f"{path}.attestation")

        arms = _list(session["arms"], f"{path}.arms")
        if len(arms) != len(ARMS):
            raise VerificationError(f"{path} must contain all three arms")
        task_by_id = {task["task_id"]: task for task in planned["tasks"]}
        task_input_by_id = _validate_task_inputs(
            session["task_inputs"],
            planned_tasks=planned["tasks"],
            path=f"{path}.task_inputs",
        )
        for arm_index, arm_id in enumerate(ARMS):
            arm_path = f"{path}.arms[{arm_index}]"
            arm = _object(arms[arm_index], arm_path)
            _exact(
                arm,
                {
                    "arm_id",
                    "execution_manifest_sha256",
                    "execution_manifest",
                    "disposition",
                    "zero_token_phases",
                    "setup_included_in_call_id",
                    "events",
                    "sandbox_evidence",
                    "task_results",
                    "scoring_bindings",
                },
                arm_path,
            )
            if arm["arm_id"] != arm_id:
                raise VerificationError(f"{arm_path}.arm_id differs from the frozen order")
            expected_manifest = planned["arm_execution_manifest_sha256"][arm_id]
            if arm["execution_manifest_sha256"] != expected_manifest:
                raise VerificationError(
                    f"{arm_path} does not bind the frozen arm execution manifest"
                )
            manifest = _object(
                arm["execution_manifest"], f"{arm_path}.execution_manifest"
            )
            computed_manifest = build_arm_execution_manifest(
                session_id=session["session_id"],
                arm_id=arm_id,
                events=_list(arm["events"], f"{arm_path}.events"),
            )
            if manifest != computed_manifest:
                raise VerificationError(
                    f"{arm_path} events differ from the frozen execution manifest preimage"
                )
            if sha256_ref(manifest) != expected_manifest:
                raise VerificationError(
                    f"{arm_path} execution manifest preimage digest differs from the plan"
                )
            if arm["disposition"] != "completed":
                raise VerificationError(
                    f"{arm_path} must finish every planned task without optional stopping"
                )
            zero_phases = _list(arm["zero_token_phases"], f"{arm_path}.zero_token_phases")
            if (
                len(zero_phases) != len(set(zero_phases))
                or not set(zero_phases).issubset(EVENT_PHASES)
            ):
                raise VerificationError(f"{arm_path}.zero_token_phases are invalid")
            setup_call_id = _call_id(
                arm["setup_included_in_call_id"],
                f"{arm_path}.setup_included_in_call_id",
                nullable=True,
            )

            events = _list(arm["events"], f"{arm_path}.events")
            event_phases: set[str] = set()
            task_event_counts = {task_id: 0 for task_id in task_by_id}
            special_counts: dict[tuple[str, str], int] = {}
            arm_call_ids: set[str] = set()
            sequences: list[int] = []
            for event_index, event_raw in enumerate(events):
                event_path = f"{arm_path}.events[{event_index}]"
                event = _object(event_raw, event_path)
                _exact(event, {"sequence", "phase", "task_id", "source"}, event_path)
                sequence = _count(event["sequence"], f"{event_path}.sequence")
                assert sequence is not None
                sequences.append(sequence)
                phase = event["phase"]
                if phase not in EVENT_PHASES:
                    raise VerificationError(f"{event_path}.phase is invalid")
                event_phases.add(phase)
                task_id = event["task_id"]
                if task_id is not None and task_id not in task_by_id:
                    raise VerificationError(f"{event_path} references an unknown task")
                if task_id is None and phase not in {"setup", "tool", "safety"}:
                    raise VerificationError(f"{event_path} lacks an exact task binding")
                if task_id is not None:
                    task_event_counts[task_id] += 1
                    key = (task_id, phase)
                    special_counts[key] = special_counts.get(key, 0) + 1
                    if phase in {"repair", "fallback"} and special_counts[key] > 1:
                        raise VerificationError(
                            f"{arm_path} has more than one {phase} event for a task"
                        )
                kind, source_id = _validate_source(
                    event["source"],
                    session=session,
                    arm_id=arm_id,
                    task_by_id=task_by_id,
                    task_input_by_id=task_input_by_id,
                    semantic_scorer_sha256=plan["artifact_locks"][
                        "semantic_scorer"
                    ],
                    phase=phase,
                    task_id=task_id,
                    path=f"{event_path}.source",
                )
                if kind == "external-response":
                    bundle_sha = event["source"]["bundle_sha256"]
                    observed_external.add(bundle_sha)
                    if bundle_sha not in bundle_ids:
                        raise VerificationError(f"{event_path} references an unlisted bundle")
                    if source_id in seen_calls:
                        raise VerificationError("execution trace reuses one external call")
                    seen_calls.add(source_id)
                    arm_call_ids.add(source_id)
                else:
                    if source_id in seen_local_events:
                        raise VerificationError(
                            "execution trace reuses one deterministic local event"
                        )
                    seen_local_events.add(source_id)

            if sequences != list(range(len(events))):
                raise VerificationError(f"{arm_path}.events must have contiguous sequences")
            if any(count == 0 for count in task_event_counts.values()):
                raise VerificationError(f"{arm_path} has a planned task with no bound event")
            if event_phases & set(zero_phases):
                raise VerificationError(f"{arm_path} counts and zeroes the same phase")
            accounted_phases = event_phases | set(zero_phases)
            if setup_call_id is not None:
                if "setup" in accounted_phases:
                    raise VerificationError(
                        f"{arm_path} double-counts setup outside its provider total"
                    )
                if setup_call_id not in arm_call_ids:
                    raise VerificationError(
                        f"{arm_path}.setup_included_in_call_id is not an arm call"
                    )
                accounted_phases.add("setup")
            if accounted_phases != set(EVENT_PHASES):
                missing = sorted(set(EVENT_PHASES) - accounted_phases)
                raise VerificationError(f"{arm_path} leaves token phases unaccounted: {missing}")
            if arm_id == "hybrid-router" and "setup" in zero_phases:
                raise VerificationError("hybrid setup cannot be declared zero")
            _list(arm["sandbox_evidence"], f"{arm_path}.sandbox_evidence")
            task_results = _list(arm["task_results"], f"{arm_path}.task_results")
            if len(task_results) != len(planned["tasks"]):
                raise VerificationError(f"{arm_path} must report every planned task")
            if (
                arm_id in {"raw-concise", "ordinary-json"}
                and "setup" in zero_phases
                and any(result.get("task_success") is True for result in task_results)
            ):
                raise VerificationError(
                    f"{arm_path} cannot declare successful baseline setup zero"
                )
            scoring_bindings = _list(
                arm["scoring_bindings"], f"{arm_path}.scoring_bindings"
            )
            if len(scoring_bindings) != len(planned["tasks"]):
                raise VerificationError(f"{arm_path} must bind every scoring target")
            event_by_sequence = {event["sequence"]: event for event in events}
            for task_index, task in enumerate(planned["tasks"]):
                binding_path = f"{arm_path}.scoring_bindings[{task_index}]"
                binding = _object(scoring_bindings[task_index], binding_path)
                _exact(
                    binding,
                    {
                        "task_id",
                        "scored_output_event_sequence",
                        "output_sha256",
                        "terminal_status",
                    },
                    binding_path,
                )
                if binding["task_id"] != task["task_id"]:
                    raise VerificationError(f"{binding_path} binds the wrong task")
                scored_sequence = _count(
                    binding["scored_output_event_sequence"],
                    f"{binding_path}.scored_output_event_sequence",
                    nullable=True,
                )
                scored_output_sha256 = binding["output_sha256"]
                if scored_output_sha256 is not None:
                    _sha(scored_output_sha256, f"{binding_path}.output_sha256")
                terminal_status = binding["terminal_status"]
                if terminal_status not in {
                    *CAPTURE_TERMINAL_STATUSES,
                    SILENCE_TERMINAL_STATUS,
                }:
                    raise VerificationError(
                        f"{binding_path}.terminal_status is invalid"
                    )
                task_result = _object(
                    task_results[task_index], f"{arm_path}.task_results[{task_index}]"
                )
                if task_result.get("task_id") != task["task_id"]:
                    raise VerificationError(
                        f"{arm_path}.task_results[{task_index}] binds the wrong task"
                    )
                task_events = [
                    event for event in events if event["task_id"] == task["task_id"]
                ]
                receiver_events = [
                    event for event in task_events if event["phase"] == "receiver"
                ]
                fallback_events = [
                    event for event in task_events if event["phase"] == "fallback"
                ]
                repair_events = [
                    event for event in task_events if event["phase"] == "repair"
                ]
                sender_events = [
                    event for event in task_events if event["phase"] == "sender"
                ]
                validator_events = [
                    event
                    for event in task_events
                    if event["source"].get("kind") == "deterministic-validator"
                ]
                if len(repair_events) > 1:
                    raise VerificationError(f"{binding_path} has unbounded repair")
                if len(validator_events) > 1:
                    raise VerificationError(
                        f"{binding_path} has more than one post-receiver validator"
                    )
                if arm_id in {"raw-concise", "ordinary-json"} and validator_events:
                    raise VerificationError(
                        f"{binding_path} baseline cannot contain hybrid validation evidence"
                    )
                if arm_id in {"raw-concise", "ordinary-json"} and (
                    len(receiver_events) != 1 or fallback_events
                ):
                    raise VerificationError(
                        f"{binding_path} baseline needs exactly one terminal receiver"
                    )
                route: Mapping[str, Any] | None = None
                if arm_id == "hybrid-router":
                    route = _object(task_result.get("route"), f"{binding_path}.route")
                    _exact(
                        route,
                        {
                            "selected_mode",
                            "decision_event_sequence",
                            "receiver_event_sequence",
                            "decode_before_model",
                            "natural_language_expansion",
                            "fallback_from",
                        },
                        f"{binding_path}.route",
                    )
                    selected_mode = route["selected_mode"]
                    if selected_mode not in ROUTES:
                        raise VerificationError(
                            f"{binding_path} route selected_mode is invalid"
                        )
                    decision_sequence = _count(
                        route["decision_event_sequence"],
                        f"{binding_path}.route.decision_event_sequence",
                    )
                    assert decision_sequence is not None
                    decision_event = event_by_sequence.get(decision_sequence)
                    if (
                        decision_event is None
                        or decision_event["phase"] != "router"
                        or decision_event["task_id"] != task["task_id"]
                    ):
                        raise VerificationError(
                            f"{binding_path} route decision belongs to another task"
                        )
                    decision_source = decision_event["source"]
                    if (
                        decision_source["kind"] != "deterministic-local"
                        or decision_source["implementation_sha256"]
                        != plan["artifact_locks"]["router"]
                        or decision_source["output_sha256"]
                        != route_decision_sha256(
                            task_id=task["task_id"], selected_mode=selected_mode
                        )
                    ):
                        raise VerificationError(
                            f"{binding_path} selected mode differs from the sealed "
                            "router decision output"
                        )
                    if (
                        route["decode_before_model"] is not False
                        or route["natural_language_expansion"] is not False
                    ):
                        raise VerificationError(
                            f"{binding_path} route must remain direct and non-expanding"
                        )
                    fallback_from = route["fallback_from"]
                    if fallback_from is not None and (
                        type(fallback_from) is not str
                        or not fallback_from.startswith("action-state:")
                    ):
                        raise VerificationError(
                            f"{binding_path} fallback_from must start action-state:"
                        )
                    routed_sequence = _count(
                        route["receiver_event_sequence"],
                        f"{binding_path}.route.receiver_event_sequence",
                        nullable=True,
                    )
                    if routed_sequence is not None:
                        routed_event = event_by_sequence.get(routed_sequence)
                        if (
                            routed_event is None
                            or routed_event["phase"] not in {"receiver", "fallback"}
                            or routed_event["task_id"] != task["task_id"]
                        ):
                            raise VerificationError(
                                f"{binding_path} route terminal belongs to another task"
                            )
                        if decision_sequence >= routed_sequence:
                            raise VerificationError(
                                f"{binding_path} router decision must precede its terminal"
                            )
                    if (
                        receiver_events
                        and decision_sequence >= receiver_events[0]["sequence"]
                    ):
                        raise VerificationError(
                            f"{binding_path} router decision must precede its primary "
                            "receiver"
                        )
                    attempted_action_state = (
                        selected_mode == "action-state" or fallback_from is not None
                    )
                    if attempted_action_state:
                        if len(sender_events) != 1:
                            raise VerificationError(
                                f"{binding_path} action-state attempt needs exactly one "
                                "sender event"
                            )
                        sender_source = sender_events[0]["source"]
                        if (
                            sender_source["kind"] != "deterministic-local"
                            or sender_source["implementation_sha256"]
                            != plan["artifact_locks"]["sender"]
                            or sender_source["input_sha256"] != task["task_sha256"]
                        ):
                            raise VerificationError(
                                f"{binding_path} sender does not bind the frozen task "
                                "and sender implementation"
                            )
                        if sender_events[0]["sequence"] >= decision_sequence:
                            raise VerificationError(
                                f"{binding_path} sender must precede the router decision"
                            )
                    if selected_mode == "silence":
                        if validator_events:
                            raise VerificationError(
                                f"{binding_path} silence cannot contain post-receiver "
                                "validation evidence"
                            )
                        invalid_silence_phases = sorted(
                            {
                                event["phase"]
                                for event in task_events
                                if event["phase"]
                                not in {"router", "safety", "judge"}
                            }
                        )
                        if receiver_events or fallback_events:
                            raise VerificationError(
                                f"{binding_path} silence must have exactly zero "
                                "receiver/fallback events"
                            )
                        if repair_events or invalid_silence_phases:
                            raise VerificationError(
                                f"{binding_path} silence task cannot contain a "
                                "setup/sender/repair/tool terminal substitute"
                            )
                        if (
                            routed_sequence is not None
                            or fallback_from is not None
                        ):
                            raise VerificationError(
                                f"{binding_path} silence route must have null "
                                "receiver and fallback bindings"
                            )
                        if (
                            scored_sequence is not None
                            or scored_output_sha256
                            != CANONICAL_SILENCE_OUTPUT_SHA256
                            or terminal_status != SILENCE_TERMINAL_STATUS
                        ):
                            raise VerificationError(
                                f"{binding_path} silence scoring target must bind "
                                "the canonical no-output digest and silenced status"
                            )
                        continue
                if scored_sequence is None:
                    raise VerificationError(
                        f"{binding_path} non-silence route requires a scored terminal output"
                    )
                if terminal_status == SILENCE_TERMINAL_STATUS:
                    raise VerificationError(
                        f"{binding_path} non-silence route cannot use silenced status"
                    )
                if task_result.get("task_success") is True and terminal_status != "completed":
                    raise VerificationError(
                        f"{binding_path} successful terminal status must be completed"
                    )
                scored_event = event_by_sequence.get(scored_sequence)
                if (
                    scored_event is None
                    or scored_event["task_id"] != task["task_id"]
                    or scored_event["phase"] not in {"receiver", "fallback"}
                ):
                    raise VerificationError(
                        f"{binding_path} does not bind that task's receiver/fallback output"
                    )

                if arm_id in {"raw-concise", "ordinary-json"}:
                    if scored_sequence != receiver_events[0]["sequence"]:
                        raise VerificationError(
                            f"{binding_path} does not score the baseline terminal receiver"
                        )
                else:
                    assert route is not None
                    selected_mode = route["selected_mode"]
                    fallback_from = route["fallback_from"]
                    receiver_sequence = route["receiver_event_sequence"]
                    if receiver_sequence != scored_sequence:
                        raise VerificationError(
                            f"{binding_path} scoring target differs from route terminal"
                        )
                    if len(fallback_events) > 1 or len(receiver_events) > 1:
                        raise VerificationError(
                            f"{binding_path} hybrid terminal event cardinality differs"
                        )
                    if fallback_events:
                        if fallback_from is None:
                            raise VerificationError(
                                f"{binding_path} fallback lacks an exact disposition"
                            )
                        if receiver_events:
                            if (
                                selected_mode != "action-state"
                                or not fallback_from.startswith(
                                    "action-state:receiver:"
                                )
                                or receiver_events[0]["source"].get(
                                    "hybrid_projection"
                                )
                                is None
                                or sender_events[0]["source"]["output_sha256"]
                                != receiver_events[0]["source"][
                                    "hybrid_projection"
                                ]["projection"]["payload_sha256"]
                                or receiver_events[0]["sequence"]
                                >= fallback_events[0]["sequence"]
                            ):
                                raise VerificationError(
                                    f"{binding_path} post-receiver fallback binding differs"
                                )
                            semantic_validation_fallback = (
                                fallback_from
                                == "action-state:receiver:semantic-invalid"
                            )
                            if semantic_validation_fallback:
                                if len(validator_events) != 1:
                                    raise VerificationError(
                                        f"{binding_path} completed-primary semantic "
                                        "fallback lacks exact validator evidence"
                                    )
                                validator_event = validator_events[0]
                                validator_source = validator_event["source"]
                                if (
                                    validator_source["primary_event_sequence"]
                                    != receiver_events[0]["sequence"]
                                    or not (
                                        receiver_events[0]["sequence"]
                                        < validator_event["sequence"]
                                        < fallback_events[0]["sequence"]
                                    )
                                ):
                                    raise VerificationError(
                                        f"{binding_path} validator does not bind the "
                                        "exact primary-to-fallback chronology"
                                    )
                            elif validator_events:
                                raise VerificationError(
                                    f"{binding_path} validator evidence is not bound "
                                    "to a semantic-invalid fallback"
                                )
                            fallback_request_arm = fallback_events[0]["source"][
                                "call_request"
                            ]["arm"]
                            if fallback_request_arm not in {
                                "raw-concise",
                                "ordinary-json",
                            }:
                                raise VerificationError(
                                    f"{binding_path} post-receiver fallback must use "
                                    "a frozen raw/json baseline request"
                                )
                        else:
                            if validator_events:
                                raise VerificationError(
                                    f"{binding_path} pre-receiver fallback cannot "
                                    "contain post-receiver validation evidence"
                                )
                            if (
                                selected_mode not in BASELINE_ROUTE_MODES
                                or not any(
                                    fallback_from.startswith(prefix)
                                    for prefix in PRE_RECEIVER_FALLBACK_PREFIXES
                                )
                            ):
                                raise VerificationError(
                                    f"{binding_path} pre-receiver action-state fallback "
                                    "must select a raw/json baseline"
                                )
                            if (
                                fallback_events[0]["source"]["call_request"]["arm"]
                                != ROUTE_REQUEST_ARMS[selected_mode]
                            ):
                                raise VerificationError(
                                    f"{binding_path} fallback request differs from its "
                                    "selected baseline"
                                )
                        expected_terminal = fallback_events[0]
                    else:
                        if validator_events:
                            raise VerificationError(
                                f"{binding_path} validation evidence has no fallback"
                            )
                        if fallback_from is not None or len(receiver_events) != 1:
                            raise VerificationError(
                                f"{binding_path} hybrid terminal event cardinality differs"
                            )
                        receiver_projection = receiver_events[0]["source"].get(
                            "hybrid_projection"
                        )
                        if (
                            selected_mode == "action-state"
                            and receiver_projection is None
                        ) or (
                            selected_mode != "action-state"
                            and receiver_projection is not None
                        ):
                            raise VerificationError(
                                f"{binding_path} selected mode and receiver request differ"
                            )
                        if (
                            selected_mode == "action-state"
                            and sender_events[0]["source"]["output_sha256"]
                            != receiver_projection["projection"]["payload_sha256"]
                        ):
                            raise VerificationError(
                                f"{binding_path} sender output differs from the direct "
                                "receiver payload"
                            )
                        if (
                            selected_mode in ROUTE_REQUEST_ARMS
                            and receiver_events[0]["source"]["call_request"]["arm"]
                            != ROUTE_REQUEST_ARMS[selected_mode]
                        ):
                            raise VerificationError(
                                f"{binding_path} selected mode and baseline request differ"
                            )
                        expected_terminal = receiver_events[0]
                    if scored_sequence != expected_terminal["sequence"]:
                        raise VerificationError(
                            f"{binding_path} does not score the final terminal event"
                        )

    if observed_external != set(bundle_ids):
        raise VerificationError("execution trace lists an unused external bundle")
    _validate_external_trace_order(raw_sessions)

    supplied = _sha(trace["trace_sha256"], "trace.trace_sha256")
    core = dict(trace)
    core.pop("trace_sha256")
    if supplied != sha256_ref(core):
        raise VerificationError("execution trace digest mismatch")
    return _detach(trace)


def build_execution_trace(
    *,
    plan_value: Mapping[str, Any],
    sessions: Sequence[Mapping[str, Any]],
    external_bundle_sha256s: Sequence[str],
) -> dict[str, Any]:
    """Build and immediately validate a canonical, non-claim trace."""

    plan = _object(plan_value, "plan")
    core: dict[str, Any] = {
        "schema_version": TRACE_SCHEMA,
        "plan_sha256": sha256_ref(plan),
        "evidence_boundary": TRACE_BOUNDARY,
        "offline_only": True,
        "claim_eligible": False,
        "authentication_status": AUTHENTICATION_STATUS,
        "external_bundle_sha256s": sorted(external_bundle_sha256s),
        "sessions": [dict(session) for session in sessions],
    }
    core["trace_sha256"] = sha256_ref(core)
    return validate_execution_trace(plan_value, core)


__all__ = [
    "AUTHENTICATION_STATUS",
    "TRACE_BOUNDARY",
    "TRACE_SCHEMA",
    "ARM_EXECUTION_MANIFEST_SCHEMA",
    "POST_RECEIVER_VALIDATION_SCHEMA",
    "ROUTE_DECISION_SCHEMA",
    "TASK_INPUT_SCHEMA",
    "CANONICAL_SILENCE_OUTPUT_SHA256",
    "SILENCE_TERMINAL_STATUS",
    "build_arm_execution_manifest",
    "build_execution_trace",
    "post_receiver_validation_input_sha256",
    "post_receiver_validation_output_sha256",
    "route_decision_sha256",
    "task_input_sha256",
    "validate_execution_trace",
]
