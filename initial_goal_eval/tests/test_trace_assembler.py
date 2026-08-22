from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import unittest

from competitive_eval.external_replay import (
    ExternalResponseStore,
    build_execution_profile,
    build_external_response_bundle,
    build_external_response_record,
)
from competitive_eval.hybrid_external_replay import (
    HYBRID_ARM,
    build_hybrid_receiver_external_call,
    expected_receiver_settings_sha256,
)
from competitive_eval.protocol import CallRequest
from competitive_eval.tests.test_hybrid_external_replay import cold_request
from urusilla_hybrid_runtime.comprehension import ReceiverModelBinding
from urusilla_hybrid_runtime.records import PublicActionState

from initial_goal_eval.contract import ARMS, VerificationError, sha256_ref
from initial_goal_eval.execution_trace import (
    CANONICAL_SILENCE_OUTPUT_SHA256,
    POST_RECEIVER_VALIDATION_SCHEMA,
    SILENCE_TERMINAL_STATUS,
    build_arm_execution_manifest,
    build_execution_trace,
    post_receiver_validation_input_sha256,
    post_receiver_validation_output_sha256,
    route_decision_sha256,
    task_input_sha256,
)
from initial_goal_eval.receipt_store import (
    RECEIPT_BUNDLE_SCHEMA_V3,
    USAGE_RECEIPT_SCHEMA_V2,
    ReceiptStore,
)
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture
from initial_goal_eval.trace_assembler import (
    ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
    ASSEMBLY_SCHEMA,
    assemble_execution_trace,
)
from initial_goal_eval.verifier import verify_result


def bare(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def local_usage(tokens: int = 1) -> dict[str, object]:
    return {
        "input_tokens": tokens,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "unclassified_tokens": 0,
        "provider_total_tokens": None,
        "total_tokens": tokens,
        "hidden_accounting": "none",
    }


def provider_usage(
    *,
    unavailable: bool = False,
    input_tokens: int = 12,
    output_tokens: int = 3,
    total_tokens: int = 15,
) -> dict[str, object]:
    if unavailable:
        return {
            "status": "unavailable",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "reasoning_tokens_subset": None,
            "reasoning_accounting": "not-reported",
            "actual_billed_usd": None,
            "unclassified_usage_json": None,
        }
    return {
        "status": "complete",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens_subset": None,
        "reasoning_accounting": "not-reported",
        "actual_billed_usd": None,
        "unclassified_usage_json": None,
    }


def make_fixture(
    *,
    unavailable_first: bool = False,
    unused_capture: bool = False,
    failed_first: bool = False,
    fallback_recovery: bool = False,
    over_hybrid_ceiling: bool = False,
    zero_first_usage: bool = False,
    silence_first: bool = False,
    pre_receiver_fallback: bool = False,
    completed_primary_validation_fallback: bool = False,
    real_evidence: bool = False,
):
    plan, template_result = build_synthetic_fixture()
    if real_evidence:
        plan["evidence_boundary"] = "real-independent-evaluation"
    task_inputs_by_session: dict[str, list[dict]] = {}
    for planned in plan["sessions"]:
        task_inputs: list[dict] = []
        for task in planned["tasks"]:
            messages = [{"role": "user", "content": task["task_id"]}]
            task["task_sha256"] = task_input_sha256(messages)
            task_inputs.append(
                {
                    "task_id": task["task_id"],
                    "task_sha256": task["task_sha256"],
                    "provider_neutral_messages": messages,
                }
            )
        task_inputs_by_session[planned["session_id"]] = task_inputs
    profile = build_execution_profile(
        provider_id="provider.test",
        api_id="responses/v1",
        normalizer_id="test-normalizer-v1",
        normalizer_sha256=bare("normalizer"),
    )
    for model in plan["receiver_models"]:
        model["settings_sha256"] = expected_receiver_settings_sha256(
            model_family_code=model["family"], model_id=model["model_id"]
        )

    direct_request = cold_request()
    records_by_operator: dict[str, list[dict]] = {
        item["operator_id"]: [] for item in plan["operators"]
    }
    execution_by_operator: dict[str, dict[str, str]] = {}
    for operator in records_by_operator:
        episode_sequence_sha256 = sha256_ref(
            {
                "operator_id": operator,
                "session_ids": [
                    session["session_id"]
                    for session in plan["sessions"]
                    if session["operator_id"] == operator
                ],
            }
        )
        run_id = sha256_ref({"study_id": plan["study_id"], "operator": operator})
        execution_by_operator[operator] = {
            "run_id": run_id,
            "run_manifest_sha256": sha256_ref(
                {
                    "run_id": run_id,
                    "episode_sequence_sha256": episode_sequence_sha256,
                    "execution_profile_sha256": "sha256:"
                    + profile["profile_sha256"],
                }
            ),
            "episode_sequence_sha256": episode_sequence_sha256,
            "execution_profile_sha256": "sha256:" + profile["profile_sha256"],
        }
    trace_sessions: list[dict] = []
    first_call_seen = False

    for planned, template in zip(plan["sessions"], template_result["records"]):
        model = next(
            item
            for item in plan["receiver_models"]
            if item["family"] == planned["receiver_family"]
        )
        operator = planned["operator_id"]
        trace_arms: list[dict] = []
        for arm_index, (arm_id, template_arm) in enumerate(zip(ARMS, template["arms"])):
            events: list[dict] = []
            scoring_bindings: list[dict] = []
            task_results = deepcopy(template_arm["task_results"])
            first_receiver_call_id = None
            for task_index, task in enumerate(planned["tasks"]):
                first_hybrid_task = (
                    planned["session_id"] == plan["sessions"][0]["session_id"]
                    and arm_id == "hybrid-router"
                    and task_index == 0
                )
                if arm_id == "hybrid-router":
                    selected_mode = (
                        "silence"
                        if silence_first and first_hybrid_task
                        else "raw"
                        if pre_receiver_fallback and first_hybrid_task
                        else "action-state"
                    )
                    if selected_mode == "action-state" or (
                        pre_receiver_fallback and first_hybrid_task
                    ):
                        sender_sequence = len(events)
                        events.append(
                            {
                                "sequence": sender_sequence,
                                "phase": "sender",
                                "task_id": task["task_id"],
                                "source": {
                                    "kind": "deterministic-local",
                                    "local_event_id": (
                                        f"{planned['session_id']}-{arm_id}-"
                                        f"{task_index}-sender"
                                    ),
                                    "implementation_sha256": plan["artifact_locks"][
                                        "sender"
                                    ],
                                    "input_sha256": task["task_sha256"],
                                    "output_sha256": sha256_ref(
                                        {
                                            "task_id": task["task_id"],
                                            "action_state": "synthetic-fixture",
                                        }
                                    ),
                                    "usage": local_usage(),
                                },
                            }
                        )
                    local_sequence = len(events)
                    events.append(
                        {
                            "sequence": local_sequence,
                            "phase": "router",
                            "task_id": task["task_id"],
                            "source": {
                                "kind": "deterministic-local",
                                "local_event_id": (
                                    f"{planned['session_id']}-{arm_id}-{task_index}-router"
                                ),
                                "implementation_sha256": plan["artifact_locks"][
                                    "router"
                                ],
                                "input_sha256": task["task_sha256"],
                                "output_sha256": route_decision_sha256(
                                    task_id=task["task_id"],
                                    selected_mode=selected_mode,
                                ),
                                "usage": local_usage(),
                            },
                        }
                    )
                    decision_sequence = local_sequence
                    if selected_mode == "silence":
                        task_results[task_index]["route"] = {
                            "selected_mode": "silence",
                            "decision_event_sequence": decision_sequence,
                            "receiver_event_sequence": None,
                            "decode_before_model": False,
                            "natural_language_expansion": False,
                            "fallback_from": None,
                        }
                        scoring_bindings.append(
                            {
                                "task_id": task["task_id"],
                                "scored_output_event_sequence": None,
                                "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                                "terminal_status": SILENCE_TERMINAL_STATUS,
                            }
                        )
                        continue
                    if pre_receiver_fallback and first_hybrid_task:
                        request = CallRequest.build(
                            episode_id=planned["session_id"],
                            turn_index=task_index,
                            attempt_index=0,
                            purpose="runtime",
                            agent="B",
                            model_code=model["family"],
                            logical_model_id=model["model_id"],
                            arm="raw-concise",
                            messages=[
                                {"role": "system", "content": "frozen raw fallback"},
                                {"role": "user", "content": task["task_id"]},
                            ],
                            mock_scenario_key=task["task_sha256"],
                        )
                        hybrid_projection = None
                        terminal_phase = "fallback"
                    else:
                        binding = ReceiverModelBinding(
                            model_id=model["model_id"],
                            settings_sha256=model["settings_sha256"],
                        )
                        state_object = PublicActionState.from_json(
                            direct_request.payload_text
                        ).to_object()
                        state_object["goal"]["a"] = [task["task_id"]]
                        task_state = PublicActionState.from_object(state_object)
                        task_direct_request = replace(
                            direct_request,
                            payload_text=task_state.canonical_text,
                            payload_sha256=task_state.sha256,
                        )
                        hybrid_call = build_hybrid_receiver_external_call(
                            task_direct_request,
                            binding,
                            episode_id=planned["session_id"],
                            turn_index=task_index,
                            attempt_index=0,
                            agent="B",
                            model_family_code=model["family"],
                            execution_profile_sha256=profile["profile_sha256"],
                        )
                        request = hybrid_call.call_request
                        hybrid_projection = {
                            "projection_sha256": hybrid_call.projection_sha256,
                            "projection": dict(hybrid_call.projection),
                            "planned_task_sha256": task["task_sha256"],
                        }
                        events[sender_sequence]["source"][
                            "output_sha256"
                        ] = hybrid_projection["projection"]["payload_sha256"]
                        terminal_phase = "receiver"
                else:
                    request = CallRequest.build(
                        episode_id=planned["session_id"],
                        turn_index=task_index,
                        attempt_index=0,
                        purpose="runtime",
                        agent="B",
                        model_code=model["family"],
                        logical_model_id=model["model_id"],
                        arm=arm_id,
                        messages=[
                            {"role": "system", "content": f"{arm_id} contract"},
                            {"role": "user", "content": task["task_id"]},
                        ],
                        mock_scenario_key=task["task_sha256"],
                    )
                    hybrid_projection = None
                    decision_sequence = None
                    terminal_phase = "receiver"

                is_first = not first_call_seen
                first_call_seen = True
                unavailable = unavailable_first and is_first
                semantic_validation_failure = (
                    completed_primary_validation_fallback and first_hybrid_task
                )
                failed = (failed_first and is_first) or (
                    fallback_recovery and first_hybrid_task
                )
                terminal_status = "refused" if failed else "completed"
                terminal_output = (
                    None
                    if failed
                    else '{"ok":false,"semantic":"invalid"}'
                    if semantic_validation_failure
                    else '{"ok":true}'
                )
                raw_receipt = (
                    f"receipt:{planned['session_id']}:{arm_id}:{task_index}"
                )
                observation = {
                    "source_kind": "unavailable" if unavailable else "provider",
                    "provider_id": "provider.test",
                    "request_id": None if unavailable else f"req:{request.call_id}",
                    "response_id": None if unavailable else f"resp:{request.call_id}",
                    "resolved_model_id": (
                        None if unavailable else request.value["model_ref"]["logical_model_id"]
                    ),
                    "effective_settings_status": (
                        "unknown" if unavailable else "confirmed-exact"
                    ),
                    "raw_receipt_utf8": None if unavailable else raw_receipt,
                    "raw_receipt_sha256": (
                        None
                        if unavailable
                        else hashlib.sha256(raw_receipt.encode()).hexdigest()
                    ),
                }
                bundle_record_sequence = len(records_by_operator[operator])
                external_record = build_external_response_record(
                    sequence=bundle_record_sequence,
                    request=request,
                    execution_profile=profile,
                    status=terminal_status,
                    output_text=terminal_output,
                    provider_observation=observation,
                    usage=provider_usage(
                        unavailable=unavailable,
                        input_tokens=(
                            0
                            if zero_first_usage and is_first
                            else 100
                            if over_hybrid_ceiling and first_hybrid_task
                            else 12
                        ),
                        output_tokens=(0 if zero_first_usage and is_first else 3),
                        total_tokens=(
                            0
                            if zero_first_usage and is_first
                            else 103
                            if over_hybrid_ceiling and first_hybrid_task
                            else 15
                        ),
                    ),
                    timing={"model_ns": 1 if not unavailable else None},
                )
                records_by_operator[operator].append(external_record)
                receiver_sequence = len(events)
                events.append(
                    {
                        "sequence": receiver_sequence,
                        "phase": terminal_phase,
                        "task_id": task["task_id"],
                        "source": {
                            "kind": "external-response",
                            "bundle_sha256": "pending",
                            "call_request": dict(request.value),
                            "hybrid_projection": hybrid_projection,
                            "execution_binding": {
                                **execution_by_operator[operator],
                                "bundle_record_sequence": bundle_record_sequence,
                            },
                        },
                    }
                )
                first_receiver_call_id = first_receiver_call_id or request.call_id
                if failed and not (fallback_recovery and first_hybrid_task):
                    task_results[task_index]["task_success"] = False
                if arm_id == "hybrid-router":
                    task_results[task_index]["route"] = {
                        "selected_mode": selected_mode,
                        "decision_event_sequence": decision_sequence,
                        "receiver_event_sequence": receiver_sequence,
                        "decode_before_model": False,
                        "natural_language_expansion": False,
                        "fallback_from": (
                            "action-state:semantic"
                            if pre_receiver_fallback and first_hybrid_task
                            else None
                        ),
                    }
                scored_sequence = receiver_sequence
                if semantic_validation_failure:
                    assert terminal_output is not None
                    primary_output_sha256 = sha256_ref(
                        {"provider_output_text": terminal_output}
                    )
                    validation_sequence = len(events)
                    validation_input_sha256 = (
                        post_receiver_validation_input_sha256(
                            task_id=task["task_id"],
                            task_sha256=task["task_sha256"],
                            primary_event_sequence=receiver_sequence,
                            primary_output_sha256=primary_output_sha256,
                        )
                    )
                    events.append(
                        {
                            "sequence": validation_sequence,
                            "phase": "safety",
                            "task_id": task["task_id"],
                            "source": {
                                "kind": "deterministic-validator",
                                "schema_version": POST_RECEIVER_VALIDATION_SCHEMA,
                                "local_event_id": (
                                    f"{planned['session_id']}-{arm_id}-"
                                    f"{task_index}-semantic-validator"
                                ),
                                "implementation_sha256": plan["artifact_locks"][
                                    "semantic_scorer"
                                ],
                                "task_sha256": task["task_sha256"],
                                "primary_event_sequence": receiver_sequence,
                                "primary_output_sha256": primary_output_sha256,
                                "verdict": "invalid",
                                "reason_code": "semantic-invalid",
                                "input_sha256": validation_input_sha256,
                                "output_sha256": (
                                    post_receiver_validation_output_sha256(
                                        input_sha256=validation_input_sha256,
                                        verdict="invalid",
                                        reason_code="semantic-invalid",
                                    )
                                ),
                                "usage": local_usage(),
                            },
                        }
                    )
                if (
                    fallback_recovery or completed_primary_validation_fallback
                ) and first_hybrid_task:
                    fallback_request = CallRequest.build(
                        episode_id=planned["session_id"],
                        turn_index=task_index,
                        attempt_index=1,
                        purpose="runtime",
                        agent="B",
                        model_code=model["family"],
                        logical_model_id=model["model_id"],
                        arm="raw-concise",
                        messages=[
                            {"role": "system", "content": "frozen raw fallback"},
                            {"role": "user", "content": task["task_id"]},
                        ],
                        mock_scenario_key=task["task_sha256"],
                    )
                    fallback_receipt = (
                        f"receipt:{planned['session_id']}:{arm_id}:{task_index}:fallback"
                    )
                    fallback_record_sequence = len(records_by_operator[operator])
                    records_by_operator[operator].append(
                        build_external_response_record(
                            sequence=fallback_record_sequence,
                            request=fallback_request,
                            execution_profile=profile,
                            status="completed",
                            output_text='{"ok":true,"fallback":true}',
                            provider_observation={
                                "source_kind": "provider",
                                "provider_id": "provider.test",
                                "request_id": f"req:{fallback_request.call_id}",
                                "response_id": f"resp:{fallback_request.call_id}",
                                "resolved_model_id": model["model_id"],
                                "effective_settings_status": "confirmed-exact",
                                "raw_receipt_utf8": fallback_receipt,
                                "raw_receipt_sha256": hashlib.sha256(
                                    fallback_receipt.encode()
                                ).hexdigest(),
                            },
                            usage=provider_usage(),
                            timing={"model_ns": 1},
                        )
                    )
                    scored_sequence = len(events)
                    events.append(
                        {
                            "sequence": scored_sequence,
                            "phase": "fallback",
                            "task_id": task["task_id"],
                            "source": {
                                "kind": "external-response",
                                "bundle_sha256": "pending",
                                "call_request": dict(fallback_request.value),
                                "hybrid_projection": None,
                                "execution_binding": {
                                    **execution_by_operator[operator],
                                    "bundle_record_sequence": (
                                        fallback_record_sequence
                                    ),
                                },
                            },
                        }
                    )
                    task_results[task_index]["route"][
                        "receiver_event_sequence"
                    ] = scored_sequence
                    task_results[task_index]["route"][
                        "fallback_from"
                    ] = (
                        "action-state:receiver:semantic-invalid"
                        if semantic_validation_failure
                        else "action-state:receiver:refused"
                    )
                    terminal_status = "completed"
                    terminal_output = '{"ok":true,"fallback":true}'
                scoring_bindings.append(
                    {
                        "task_id": task["task_id"],
                        "scored_output_event_sequence": scored_sequence,
                        "output_sha256": (
                            None
                            if terminal_output is None
                            else sha256_ref(
                                {"provider_output_text": terminal_output}
                            )
                        ),
                        "terminal_status": terminal_status,
                    }
                )

            observed = {item["phase"] for item in events}
            zero_phases = [
                phase
                for phase in (
                    "setup",
                    "sender",
                    "router",
                    "receiver",
                    "repair",
                    "fallback",
                    "tool",
                    "safety",
                    "judge",
                )
                if phase not in observed and phase != "setup"
            ]
            execution_manifest = build_arm_execution_manifest(
                session_id=planned["session_id"], arm_id=arm_id, events=events
            )
            execution_manifest_sha256 = sha256_ref(execution_manifest)
            planned["arm_execution_manifest_sha256"][
                arm_id
            ] = execution_manifest_sha256
            trace_arms.append(
                {
                    "arm_id": arm_id,
                    "execution_manifest_sha256": execution_manifest_sha256,
                    "execution_manifest": execution_manifest,
                    "disposition": "completed",
                    "zero_token_phases": zero_phases,
                    "setup_included_in_call_id": first_receiver_call_id,
                    "events": events,
                    "sandbox_evidence": deepcopy(template_arm["sandbox_evidence"]),
                    "task_results": task_results,
                    "scoring_bindings": scoring_bindings,
                }
            )
        trace_sessions.append(
            {
                "session_id": planned["session_id"],
                "cluster_id": planned["cluster_id"],
                "domain_id": planned["domain_id"],
                "receiver_family": planned["receiver_family"],
                "operator_id": operator,
                "executed_arm_order": planned["arm_order"],
                "task_inputs": deepcopy(
                    task_inputs_by_session[planned["session_id"]]
                ),
                "attestation": deepcopy(template["attestation"]),
                "arms": trace_arms,
            }
        )

    if unused_capture:
        operator = plan["operators"][0]["operator_id"]
        model = plan["receiver_models"][0]
        request = CallRequest.build(
            episode_id="unused-session",
            turn_index=0,
            attempt_index=0,
            purpose="runtime",
            agent="B",
            model_code=model["family"],
            logical_model_id=model["model_id"],
            arm="raw-concise",
            messages=[{"role": "user", "content": "unused"}],
            mock_scenario_key="unused",
        )
        raw_receipt = "unused-receipt"
        records_by_operator[operator].append(
            build_external_response_record(
                sequence=len(records_by_operator[operator]),
                request=request,
                execution_profile=profile,
                status="completed",
                output_text="unused",
                provider_observation={
                    "source_kind": "provider",
                    "provider_id": "provider.test",
                    "request_id": f"req:{request.call_id}",
                    "response_id": f"resp:{request.call_id}",
                    "resolved_model_id": model["model_id"],
                    "effective_settings_status": "confirmed-exact",
                    "raw_receipt_utf8": raw_receipt,
                    "raw_receipt_sha256": hashlib.sha256(
                        raw_receipt.encode()
                    ).hexdigest(),
                },
                usage=provider_usage(),
                timing={"model_ns": 1},
            )
        )

    stores: list[ExternalResponseStore] = []
    bundle_by_operator: dict[str, str] = {}
    for operator, records in records_by_operator.items():
        execution = execution_by_operator[operator]
        bundle = build_external_response_bundle(
            run_id=execution["run_id"].removeprefix("sha256:"),
            run_manifest_sha256=execution["run_manifest_sha256"].removeprefix(
                "sha256:"
            ),
            episode_sequence_sha256=execution[
                "episode_sequence_sha256"
            ].removeprefix("sha256:"),
            operator_id=operator,
            capture_implementation_sha256=bare("capture"),
            operator_attestation_sha256=None,
            execution_profile=profile,
            records=records,
        )
        store = ExternalResponseStore.from_object(bundle)
        stores.append(store)
        bundle_by_operator[operator] = "sha256:" + bundle["bundle_sha256"]

    for session in trace_sessions:
        bundle_sha = bundle_by_operator[session["operator_id"]]
        for arm in session["arms"]:
            for event in arm["events"]:
                if event["source"]["kind"] == "external-response":
                    event["source"]["bundle_sha256"] = bundle_sha
    trace = build_execution_trace(
        plan_value=plan,
        sessions=trace_sessions,
        external_bundle_sha256s=sorted(bundle_by_operator.values()),
    )
    return plan, trace, stores


def rebind_arm_manifest(plan: dict, sessions: list[dict], session_index: int, arm_index: int):
    planned = plan["sessions"][session_index]
    arm = sessions[session_index]["arms"][arm_index]
    manifest = build_arm_execution_manifest(
        session_id=planned["session_id"], arm_id=arm["arm_id"], events=arm["events"]
    )
    digest = sha256_ref(manifest)
    planned["arm_execution_manifest_sha256"][arm["arm_id"]] = digest
    arm["execution_manifest"] = manifest
    arm["execution_manifest_sha256"] = digest


def replace_bundle_reference(
    plan: dict,
    trace: dict,
    *,
    old_bundle_sha256: str,
    new_bundle_sha256: str,
) -> dict:
    sessions = deepcopy(trace["sessions"])
    for session in sessions:
        for arm in session["arms"]:
            for event in arm["events"]:
                source = event["source"]
                if (
                    source["kind"] == "external-response"
                    and source["bundle_sha256"] == old_bundle_sha256
                ):
                    source["bundle_sha256"] = new_bundle_sha256
    bundle_sha256s = [
        new_bundle_sha256 if item == old_bundle_sha256 else item
        for item in trace["external_bundle_sha256s"]
    ]
    return build_execution_trace(
        plan_value=plan,
        sessions=sessions,
        external_bundle_sha256s=bundle_sha256s,
    )


def rebuild_store(
    store: ExternalResponseStore,
    *,
    run_id: str | None = None,
    execution_profile: dict | None = None,
    reverse_records: bool = False,
    status_overrides: dict[str, tuple[str, str | None]] | None = None,
) -> ExternalResponseStore:
    original = store.value
    profile = execution_profile or dict(store.execution_profile)
    raw_records = list(original["records"])
    if reverse_records:
        raw_records.reverse()
    rebuilt_records: list[dict] = []
    for sequence, raw_record in enumerate(raw_records):
        request = CallRequest.from_value(raw_record["call_request"])
        response = raw_record["response"]
        status, output_text = (status_overrides or {}).get(
            request.call_id,
            (response["status"], response["output_text"]),
        )
        observation = deepcopy(response["provider_observation"])
        observation["provider_id"] = profile["provider_id"]
        rebuilt_records.append(
            build_external_response_record(
                sequence=sequence,
                request=request,
                execution_profile=profile,
                status=status,
                output_text=output_text,
                provider_observation=observation,
                usage=response["usage"],
                timing=response["timing"],
            )
        )
    rebuilt_bundle = build_external_response_bundle(
        run_id=run_id or original["run_id"],
        run_manifest_sha256=original["run_manifest_sha256"],
        episode_sequence_sha256=original["episode_sequence_sha256"],
        operator_id=original["producer"]["operator_id"],
        capture_implementation_sha256=original["producer"][
            "capture_implementation_sha256"
        ],
        operator_attestation_sha256=original["producer"][
            "operator_attestation_sha256"
        ],
        execution_profile=profile,
        records=rebuilt_records,
    )
    return ExternalResponseStore.from_object(rebuilt_bundle)


class TraceAssemblerTests(unittest.TestCase):
    def test_three_arm_assembly_accepts_actual_hybrid_projection_and_stays_nonclaim(self):
        plan, trace, stores = make_fixture(failed_first=True)
        hybrid_source = next(
            event["source"]
            for event in trace["sessions"][0]["arms"][2]["events"]
            if event["phase"] == "receiver"
        )
        self.assertEqual(hybrid_source["call_request"]["arm"], HYBRID_ARM)
        self.assertTrue(hybrid_source["bundle_sha256"].startswith("sha256:"))

        assembled = assemble_execution_trace(plan, trace, stores)
        self.assertFalse(assembled.claim_eligible)
        self.assertFalse(assembled.value["authentication_complete"])
        self.assertEqual(assembled.value["schema_version"], ASSEMBLY_SCHEMA)
        self.assertEqual(
            ASSEMBLY_SCHEMA, "urusilla-initial-goal-trace-assembly/4"
        )
        self.assertIn("receipt_bundle", assembled.value)
        self.assertNotIn("usage_receipt_bundle", assembled.value)
        self.assertEqual(
            assembled.value["receipt_content_validation_mode"],
            "self-issued-diagnostic",
        )
        self.assertEqual(
            {
                receipt["issuer_id"]
                for receipt in assembled.receipt_bundle["receipts"]
            },
            {ASSEMBLER_DIAGNOSTIC_ISSUER_ID},
        )
        self.assertEqual(
            assembled.receipt_bundle["schema_version"],
            RECEIPT_BUNDLE_SCHEMA_V3,
        )
        receipt_store = ReceiptStore.from_object(assembled.receipt_bundle)
        default_validation = receipt_store.validate(plan, assembled.result)
        self.assertFalse(default_validation.content_consistent)
        self.assertTrue(
            any(
                error.startswith("receipt-issuer-mismatch:")
                for error in default_validation.errors
            )
        )
        receipt_validation = receipt_store.validate(
            plan,
            assembled.result,
            diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
        )
        self.assertTrue(receipt_validation.content_consistent)
        self.assertTrue(receipt_validation.scorer_output_binding_complete)
        self.assertTrue(receipt_validation.provider_preimage_resolution_required)
        self.assertTrue(receipt_validation.provider_preimage_resolution_complete)
        self.assertTrue(receipt_validation.complete)
        self.assertTrue(
            assembled.value["receipt_content_validation"]["complete"]
        )
        summary = verify_result(
            plan,
            assembled.result,
            receipt_store=ReceiptStore.from_object(assembled.receipt_bundle),
        )
        self.assertFalse(summary["receipt_bundle"]["complete"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertFalse(summary["synthetic_fixture_can_support_external_claim"])
        self.assertIn(
            "synthetic-test-only-not-claim-evidence", summary["gate_failures"]
        )
        self.assertEqual(
            [arm["arm_id"] for arm in assembled.result["records"][0]["arms"]],
            list(ARMS),
        )
        failed_arm = assembled.result["records"][0]["arms"][0]
        self.assertFalse(failed_arm["task_results"][0]["task_success"])
        self.assertEqual(sum(e["usage"]["total_tokens"] for e in failed_arm["events"]), 30)

    def test_self_issued_bundle_fails_real_evidence_authentication_boundary(self):
        plan, trace, stores = make_fixture(real_evidence=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        store = ReceiptStore.from_object(assembled.receipt_bundle)

        default_validation = store.validate(plan, assembled.result)
        self.assertFalse(default_validation.complete)
        self.assertTrue(
            any(
                error.startswith("receipt-issuer-mismatch:")
                for error in default_validation.errors
            )
        )
        diagnostic_validation = store.validate(
            plan,
            assembled.result,
            diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
        )
        self.assertTrue(diagnostic_validation.complete)

        summary = verify_result(
            plan,
            assembled.result,
            receipt_store=store,
        )
        self.assertFalse(summary["receipt_bundle"]["complete"])
        self.assertFalse(summary["evidence_authentication"]["complete"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertIn(
            "receipt-bundle-incomplete-or-unvalidated",
            summary["gate_failures"],
        )
        self.assertIn(
            "authenticated-provenance-not-established",
            summary["gate_failures"],
        )

    def test_assembled_v2_score_rejects_unsynchronized_output_text_mutation(self):
        plan, trace, stores = make_fixture()
        assembled = assemble_execution_trace(plan, trace, stores)
        bundle = deepcopy(assembled.receipt_bundle)
        result = deepcopy(assembled.result)
        scorer = next(
            receipt
            for receipt in bundle["receipts"]
            if receipt["kind"] == "scorer"
            and receipt["source_payload"]["provider_output"]["kind"]
            == "provider-text"
        )
        scorer["source_payload"]["provider_output"]["text"] = '{"forged":true}'
        scorer["source_sha256"] = sha256_ref(scorer["source_payload"])
        replacement_digest = sha256_ref(scorer)
        binding = scorer["binding"]
        record = next(
            item
            for item in result["records"]
            if item["session_id"] == binding["session_id"]
        )
        arm = next(
            item for item in record["arms"] if item["arm_id"] == binding["arm_id"]
        )
        task_result = next(
            item
            for item in arm["task_results"]
            if item["task_id"] == binding["task"]["task_id"]
        )
        task_result["scorer_receipt_sha256"] = replacement_digest

        validation = ReceiptStore.from_object(bundle).validate(
            plan,
            result,
            diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
        )
        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                error.startswith("scorer-v2-provider-output-digest-mismatch:")
                for error in validation.errors
            )
        )

    def test_downstream_coordinated_rehash_is_rejected_by_v3_preimage(self):
        plan, trace, stores = make_fixture(real_evidence=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        bundle = deepcopy(assembled.receipt_bundle)
        result = deepcopy(assembled.result)
        record = result["records"][0]
        arm = record["arms"][0]
        task_result = arm["task_results"][0]
        event = next(
            item
            for item in arm["events"]
            if item["task_id"] == task_result["task_id"]
        )
        usage_receipt = next(
            item
            for item in bundle["receipts"]
            if sha256_ref(item) == event["usage_receipt_sha256"]
        )
        scorer_receipt = next(
            item
            for item in bundle["receipts"]
            if sha256_ref(item) == task_result["scorer_receipt_sha256"]
        )

        forged_text = '{"forged":true}'
        forged_output_sha256 = sha256_ref(
            {"provider_output_text": forged_text}
        )
        event["output_sha256"] = forged_output_sha256
        usage_receipt["binding"]["output_sha256"] = forged_output_sha256
        forged_usage_receipt_sha256 = sha256_ref(usage_receipt)
        event["usage_receipt_sha256"] = forged_usage_receipt_sha256
        for terminal in (
            scorer_receipt["binding"]["terminal_event"],
            scorer_receipt["source_payload"]["terminal_event"],
        ):
            terminal["output_sha256"] = forged_output_sha256
            terminal["usage_receipt_sha256"] = forged_usage_receipt_sha256
        provider_output = scorer_receipt["source_payload"]["provider_output"]
        provider_output["text"] = forged_text
        provider_output["output_sha256"] = forged_output_sha256
        scorer_receipt["source_sha256"] = sha256_ref(
            scorer_receipt["source_payload"]
        )
        task_result["scorer_receipt_sha256"] = sha256_ref(scorer_receipt)

        store = ReceiptStore.from_object(bundle)
        diagnostic = store.validate(
            plan,
            result,
            diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
        )
        self.assertFalse(diagnostic.complete)
        self.assertTrue(
            any(
                error.startswith("usage-v3-provider-event-output-mismatch:")
                for error in diagnostic.errors
            )
        )
        self.assertFalse(store.validate(plan, result).complete)
        summary = verify_result(plan, result, receipt_store=store)
        self.assertFalse(summary["goal_gate_passed"])
        self.assertIn(
            "authenticated-provenance-not-established",
            summary["gate_failures"],
        )

    def test_receipt_bundle_v3_rejects_usage_schema_downgrade(self):
        plan, trace, stores = make_fixture(real_evidence=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        bundle = deepcopy(assembled.receipt_bundle)
        usage_receipt = next(
            item for item in bundle["receipts"] if item["kind"] == "usage"
        )
        usage_receipt["schema_version"] = USAGE_RECEIPT_SCHEMA_V2

        with self.assertRaisesRegex(VerificationError, "schema_version differs"):
            ReceiptStore.from_object(bundle)

    def test_receipt_bundle_v3_requires_source_commitment_preimage(self):
        plan, trace, stores = make_fixture(real_evidence=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        bundle = deepcopy(assembled.receipt_bundle)
        bundle["source_commitment_preimages"].pop(0)

        validation = ReceiptStore.from_object(bundle).validate(
            plan,
            assembled.result,
            diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
        )

        self.assertFalse(validation.provider_preimage_resolution_complete)
        self.assertTrue(
            any(
                error.startswith("v3-source-commitment-preimage-missing:")
                for error in validation.errors
            )
        )

    def test_receipt_bundle_v3_rejects_cross_task_provider_record_swap(self):
        plan, trace, stores = make_fixture(real_evidence=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        bundle = deepcopy(assembled.receipt_bundle)
        result = deepcopy(assembled.result)
        usage_receipts = [
            item
            for item in bundle["receipts"]
            if item["kind"] == "usage"
            and item["source_payload"]["source_kind"] == "provider"
        ][:2]
        first_ref = usage_receipts[0]["source_payload"]["provider_record_sha256"]
        second_ref = usage_receipts[1]["source_payload"]["provider_record_sha256"]
        usage_receipts[0]["source_payload"]["provider_record_sha256"] = second_ref
        usage_receipts[1]["source_payload"]["provider_record_sha256"] = first_ref

        for receipt in usage_receipts:
            receipt["source_sha256"] = sha256_ref(receipt["source_payload"])
            replacement_digest = sha256_ref(receipt)
            binding = receipt["binding"]
            record = next(
                item
                for item in result["records"]
                if item["session_id"] == binding["session_id"]
            )
            arm = next(
                item
                for item in record["arms"]
                if item["arm_id"] == binding["arm_id"]
            )
            event = next(
                item
                for item in arm["events"]
                if item["sequence"] == binding["event_sequence"]
            )
            event["usage_receipt_sha256"] = replacement_digest

        validation = ReceiptStore.from_object(bundle).validate(
            plan,
            result,
            diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
        )

        self.assertFalse(validation.provider_preimage_resolution_complete)
        self.assertTrue(
            any(
                error.startswith(
                    (
                        "usage-v3-provider-event-input-mismatch:",
                        "usage-v3-provider-event-output-mismatch:",
                        "v3-manifest-call-id-mismatch:",
                    )
                )
                for error in validation.errors
            )
        )

    def test_unknown_provider_usage_fails_instead_of_becoming_zero(self):
        plan, trace, stores = make_fixture(unavailable_first=True)
        with self.assertRaisesRegex(VerificationError, "cannot be resolved"):
            assemble_execution_trace(plan, trace, stores)

    def test_unused_capture_is_rejected(self):
        plan, trace, stores = make_fixture(unused_capture=True)
        with self.assertRaisesRegex(VerificationError, "unused capture"):
            assemble_execution_trace(plan, trace, stores)

    def test_missing_arm_is_rejected(self):
        plan, trace, _ = make_fixture()
        sessions = deepcopy(trace["sessions"])
        sessions[0]["arms"].pop()
        with self.assertRaisesRegex(VerificationError, "all three arms"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_wrong_arm_binding_is_rejected(self):
        plan, trace, _ = make_fixture()
        sessions = deepcopy(trace["sessions"])
        source = sessions[0]["arms"][0]["events"][0]["source"]
        old = CallRequest.from_value(source["call_request"])
        source["call_request"] = dict(
            CallRequest.build(
                episode_id=old.value["episode_id"],
                turn_index=old.value["turn_index"],
                attempt_index=old.value["attempt_index"],
                purpose=old.value["purpose"],
                agent=old.value["agent"],
                model_code=old.value["model_ref"]["family_code"],
                logical_model_id=old.value["model_ref"]["logical_model_id"],
                arm="ordinary-json",
                messages=old.value["messages"],
                mock_scenario_key=old.value["mock_metadata"]["scenario_key"],
            ).value
        )
        with self.assertRaisesRegex(VerificationError, "frozen execution manifest"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_repair_or_fallback_cannot_reuse_a_charged_call(self):
        plan, trace, _ = make_fixture()
        for phase in ("repair", "fallback"):
            with self.subTest(phase=phase):
                sessions = deepcopy(trace["sessions"])
                arm = sessions[0]["arms"][0]
                duplicate = deepcopy(arm["events"][0])
                duplicate["sequence"] = len(arm["events"])
                duplicate["phase"] = phase
                arm["events"].append(duplicate)
                arm["zero_token_phases"].remove(phase)
                with self.assertRaises(VerificationError):
                    build_execution_trace(
                        plan_value=plan,
                        sessions=sessions,
                        external_bundle_sha256s=trace[
                            "external_bundle_sha256s"
                        ],
                    )

    def test_baseline_cannot_omit_one_tasks_terminal_receiver(self):
        plan, trace, _ = make_fixture()
        plan = deepcopy(plan)
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][0]
        removed_call = arm["events"].pop(0)
        self.assertEqual(removed_call["task_id"], plan["sessions"][0]["tasks"][0]["task_id"])
        arm["events"].insert(
            0,
            {
                "sequence": 0,
                "phase": "judge",
                "task_id": removed_call["task_id"],
                "source": {
                    "kind": "deterministic-local",
                    "local_event_id": "baseline-missing-terminal-judge",
                    "implementation_sha256": sha256_ref({"judge": "test"}),
                    "input_sha256": plan["sessions"][0]["tasks"][0]["task_sha256"],
                    "output_sha256": None,
                    "usage": local_usage(),
                },
            },
        )
        arm["events"][1]["sequence"] = 1
        arm["zero_token_phases"].remove("judge")
        arm["setup_included_in_call_id"] = arm["events"][1]["source"]["call_request"][
            "call_id"
        ]
        arm["scoring_bindings"][0]["scored_output_event_sequence"] = None
        arm["scoring_bindings"][1]["scored_output_event_sequence"] = 1
        rebind_arm_manifest(plan, sessions, 0, 0)
        with self.assertRaisesRegex(VerificationError, "terminal receiver"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_successful_baseline_cannot_declare_setup_zero(self):
        plan, trace, _ = make_fixture()
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][0]
        arm["setup_included_in_call_id"] = None
        arm["zero_token_phases"].append("setup")
        with self.assertRaisesRegex(VerificationError, "baseline setup zero"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_successful_baseline_terminal_cannot_cost_zero_tokens(self):
        plan, trace, stores = make_fixture(zero_first_usage=True)
        with self.assertRaisesRegex(VerificationError, "zero-token terminal receiver"):
            assemble_execution_trace(plan, trace, stores)

    def test_verified_silence_can_succeed_with_canonical_no_output_target(self):
        plan, trace, stores = make_fixture(silence_first=True)
        hybrid_trace = trace["sessions"][0]["arms"][2]
        task_result = hybrid_trace["task_results"][0]
        task_id = task_result["task_id"]
        task_events = [
            event for event in hybrid_trace["events"] if event["task_id"] == task_id
        ]
        self.assertTrue(task_result["task_success"])
        self.assertEqual([event["phase"] for event in task_events], ["router"])
        self.assertEqual(
            hybrid_trace["scoring_bindings"][0],
            {
                "task_id": task_id,
                "scored_output_event_sequence": None,
                "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                "terminal_status": SILENCE_TERMINAL_STATUS,
            },
        )

        assembled = assemble_execution_trace(plan, trace, stores)
        target = next(
            item
            for item in assembled.value["scoring_targets"]
            if item["session_id"] == plan["sessions"][0]["session_id"]
            and item["arm_id"] == "hybrid-router"
            and item["task_id"] == task_id
        )
        self.assertEqual(target["scored_output_event_sequence"], None)
        self.assertEqual(target["output_sha256"], CANONICAL_SILENCE_OUTPUT_SHA256)
        self.assertEqual(target["terminal_status"], SILENCE_TERMINAL_STATUS)
        self.assertFalse(
            any(
                "does not emit receipt-bundle v3" in blocker
                for blocker in assembled.value["claim_blockers"]
            )
        )
        scorer = next(
            receipt
            for receipt in assembled.receipt_bundle["receipts"]
            if receipt["kind"] == "scorer"
            and receipt["binding"]["session_id"]
            == plan["sessions"][0]["session_id"]
            and receipt["binding"]["arm_id"] == "hybrid-router"
            and receipt["binding"]["task"]["task_id"] == task_id
        )
        self.assertEqual(
            scorer["source_payload"]["provider_output"]["kind"],
            "canonical-silence",
        )
        self.assertTrue(
            ReceiptStore.from_object(assembled.receipt_bundle)
            .validate(
                plan,
                assembled.result,
                diagnostic_issuer_id=ASSEMBLER_DIAGNOSTIC_ISSUER_ID,
            )
            .complete
        )

    def test_silence_rejects_receiver_or_fallback_events(self):
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                plan, trace, _ = make_fixture(fallback_recovery=fallback)
                plan = deepcopy(plan)
                sessions = deepcopy(trace["sessions"])
                arm = sessions[0]["arms"][2]
                route = arm["task_results"][0]["route"]
                route["selected_mode"] = "silence"
                route["receiver_event_sequence"] = None
                route["fallback_from"] = None
                arm["scoring_bindings"][0] = {
                    "task_id": arm["task_results"][0]["task_id"],
                    "scored_output_event_sequence": None,
                    "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                    "terminal_status": SILENCE_TERMINAL_STATUS,
                }
                decision_event = arm["events"][route["decision_event_sequence"]]
                decision_event["source"]["output_sha256"] = route_decision_sha256(
                    task_id=arm["task_results"][0]["task_id"],
                    selected_mode="silence",
                )
                rebind_arm_manifest(plan, sessions, 0, 2)
                with self.assertRaisesRegex(VerificationError, "exactly zero"):
                    build_execution_trace(
                        plan_value=plan,
                        sessions=sessions,
                        external_bundle_sha256s=trace["external_bundle_sha256s"],
                    )

    def test_silence_rejects_orphan_post_receiver_validator(self):
        plan, trace, _ = make_fixture(silence_first=True)
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][2]
        task = plan["sessions"][0]["tasks"][0]
        primary_output_sha256 = sha256_ref({"nonexistent-primary": True})
        validation_input_sha256 = post_receiver_validation_input_sha256(
            task_id=task["task_id"],
            task_sha256=task["task_sha256"],
            primary_event_sequence=999,
            primary_output_sha256=primary_output_sha256,
        )
        arm["events"].append(
            {
                "sequence": len(arm["events"]),
                "phase": "safety",
                "task_id": task["task_id"],
                "source": {
                    "kind": "deterministic-validator",
                    "schema_version": POST_RECEIVER_VALIDATION_SCHEMA,
                    "local_event_id": "orphan-validator-on-silence",
                    "implementation_sha256": plan["artifact_locks"][
                        "semantic_scorer"
                    ],
                    "task_sha256": task["task_sha256"],
                    "primary_event_sequence": 999,
                    "primary_output_sha256": primary_output_sha256,
                    "verdict": "invalid",
                    "reason_code": "semantic-invalid",
                    "input_sha256": validation_input_sha256,
                    "output_sha256": post_receiver_validation_output_sha256(
                        input_sha256=validation_input_sha256,
                        verdict="invalid",
                        reason_code="semantic-invalid",
                    ),
                    "usage": local_usage(),
                },
            }
        )
        arm["zero_token_phases"].remove("safety")
        rebind_arm_manifest(plan, sessions, 0, 2)

        with self.assertRaisesRegex(
            VerificationError, "silence cannot contain post-receiver"
        ):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_silence_cannot_use_setup_or_repair_as_a_terminal_substitute(self):
        for phase in ("setup", "repair"):
            with self.subTest(phase=phase):
                plan, trace, _ = make_fixture(silence_first=True)
                plan = deepcopy(plan)
                sessions = deepcopy(trace["sessions"])
                arm = sessions[0]["arms"][2]
                task = plan["sessions"][0]["tasks"][0]
                sequence = len(arm["events"])
                forged_output = sha256_ref(
                    {"forged_silence_terminal_phase": phase}
                )
                if phase == "setup":
                    source = {
                        "kind": "deterministic-local",
                        "local_event_id": f"forged-silence-{phase}",
                        "implementation_sha256": sha256_ref({"forger": phase}),
                        "input_sha256": task["task_sha256"],
                        "output_sha256": forged_output,
                        "usage": local_usage(),
                    }
                    arm["setup_included_in_call_id"] = None
                else:
                    model = plan["receiver_models"][0]
                    request = CallRequest.build(
                        episode_id=plan["sessions"][0]["session_id"],
                        turn_index=0,
                        attempt_index=1,
                        purpose="format_repair",
                        agent="B",
                        model_code=model["family"],
                        logical_model_id=model["model_id"],
                        arm="hybrid-router",
                        messages=[
                            {"role": "system", "content": "forged repair"},
                            *sessions[0]["task_inputs"][0][
                                "provider_neutral_messages"
                            ],
                        ],
                        mock_scenario_key=task["task_sha256"],
                    )
                    bundle_sha256 = next(
                        event["source"]["bundle_sha256"]
                        for event in arm["events"]
                        if event["source"]["kind"] == "external-response"
                    )
                    existing_external_source = next(
                        event["source"]
                        for event in arm["events"]
                        if event["source"]["kind"] == "external-response"
                    )
                    source = {
                        "kind": "external-response",
                        "bundle_sha256": bundle_sha256,
                        "call_request": dict(request.value),
                        "hybrid_projection": None,
                        "execution_binding": {
                            **existing_external_source["execution_binding"],
                            "bundle_record_sequence": 10_000,
                        },
                    }
                    arm["zero_token_phases"].remove("repair")
                arm["events"].append(
                    {
                        "sequence": sequence,
                        "phase": phase,
                        "task_id": task["task_id"],
                        "source": source,
                    }
                )
                arm["scoring_bindings"][0].update(
                    {
                        "scored_output_event_sequence": sequence,
                        "output_sha256": forged_output,
                        "terminal_status": "completed",
                    }
                )
                rebind_arm_manifest(plan, sessions, 0, 2)
                with self.assertRaisesRegex(VerificationError, "silence task cannot"):
                    build_execution_trace(
                        plan_value=plan,
                        sessions=sessions,
                        external_bundle_sha256s=trace["external_bundle_sha256s"],
                    )

    def test_non_silence_route_still_requires_a_terminal_event(self):
        plan, trace, _ = make_fixture()
        sessions = deepcopy(trace["sessions"])
        binding = sessions[0]["arms"][2]["scoring_bindings"][0]
        binding["scored_output_event_sequence"] = None
        with self.assertRaisesRegex(VerificationError, "non-silence route requires"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_silence_canonical_target_cannot_be_mutated(self):
        plan, trace, _ = make_fixture(silence_first=True)
        for field, value in (
            ("output_sha256", sha256_ref({"not": "silence"})),
            ("terminal_status", "completed"),
        ):
            with self.subTest(field=field):
                sessions = deepcopy(trace["sessions"])
                sessions[0]["arms"][2]["scoring_bindings"][0][field] = value
                with self.assertRaisesRegex(VerificationError, "canonical no-output"):
                    build_execution_trace(
                        plan_value=plan,
                        sessions=sessions,
                        external_bundle_sha256s=trace["external_bundle_sha256s"],
                    )

    def test_hybrid_route_cannot_reuse_another_tasks_events(self):
        plan, trace, _ = make_fixture()
        first = trace["sessions"][0]["arms"][2]
        second_route = first["task_results"][1]["route"]
        for field, message in (
            ("decision_event_sequence", "another task"),
            ("receiver_event_sequence", "route terminal"),
        ):
            with self.subTest(field=field):
                sessions = deepcopy(trace["sessions"])
                arm = sessions[0]["arms"][2]
                arm["task_results"][0]["route"][field] = second_route[field]
                with self.assertRaisesRegex(VerificationError, message):
                    build_execution_trace(
                        plan_value=plan,
                        sessions=sessions,
                        external_bundle_sha256s=trace["external_bundle_sha256s"],
                    )

    def test_scored_output_cannot_target_another_task(self):
        plan, trace, _ = make_fixture()
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][0]
        arm["scoring_bindings"][0]["scored_output_event_sequence"] = arm[
            "scoring_bindings"
        ][1]["scored_output_event_sequence"]
        with self.assertRaisesRegex(VerificationError, "that task"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_hybrid_projection_total_ceiling_is_enforced(self):
        plan, trace, stores = make_fixture(over_hybrid_ceiling=True)
        with self.assertRaisesRegex(VerificationError, "maximum total tokens"):
            assemble_execution_trace(plan, trace, stores)

    def test_failed_primary_can_recover_through_completed_fallback(self):
        plan, trace, stores = make_fixture(fallback_recovery=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        hybrid = assembled.result["records"][0]["arms"][2]
        self.assertTrue(hybrid["task_results"][0]["task_success"])
        task_id = hybrid["task_results"][0]["task_id"]
        task_events = [event for event in hybrid["events"] if event["task_id"] == task_id]
        self.assertEqual(
            [event["phase"] for event in task_events],
            ["sender", "router", "receiver", "fallback"],
        )
        target = next(
            item
            for item in assembled.value["scoring_targets"]
            if item["session_id"] == hybrid["task_results"][0]["task_id"].rsplit("-task-", 1)[0]
            and item["arm_id"] == "hybrid-router"
            and item["task_id"] == task_id
        )
        self.assertEqual(target["terminal_status"], "completed")
        self.assertEqual(target["output_sha256"], task_events[-1]["output_sha256"])
        capture_statuses = [
            item["status"]
            for item in assembled.value["external_capture_metadata"]
            if item["session_id"] == target["session_id"]
            and item["arm_id"] == "hybrid-router"
            and item["task_id"] == task_id
        ]
        self.assertEqual(capture_statuses, ["refused", "completed"])

    def test_completed_semantic_invalid_primary_uses_bound_fallback(self):
        plan, trace, stores = make_fixture(
            completed_primary_validation_fallback=True
        )
        assembled = assemble_execution_trace(plan, trace, stores)
        hybrid = assembled.result["records"][0]["arms"][2]
        task = hybrid["task_results"][0]
        task_events = [
            event for event in hybrid["events"] if event["task_id"] == task["task_id"]
        ]
        self.assertEqual(
            [event["phase"] for event in task_events],
            ["sender", "router", "receiver", "safety", "fallback"],
        )
        self.assertEqual(
            [event["usage"]["total_tokens"] for event in task_events],
            [1, 1, 15, 1, 15],
        )
        self.assertEqual(hybrid["scope_coverage"]["receiver"], "counted")
        self.assertEqual(hybrid["scope_coverage"]["safety"], "counted")
        self.assertEqual(hybrid["scope_coverage"]["fallback"], "counted")
        self.assertTrue(task["task_success"])
        self.assertEqual(
            task["route"]["fallback_from"],
            "action-state:receiver:semantic-invalid",
        )
        validation = assembled.value["post_receiver_validations"][0]
        primary, validator, fallback = task_events[2:]
        self.assertEqual(validation["primary_output_sha256"], primary["output_sha256"])
        self.assertEqual(
            validation["primary_usage_receipt_sha256"],
            primary["usage_receipt_sha256"],
        )
        self.assertEqual(
            validation["validation_usage_receipt_sha256"],
            validator["usage_receipt_sha256"],
        )
        self.assertEqual(
            validation["fallback_usage_receipt_sha256"],
            fallback["usage_receipt_sha256"],
        )
        self.assertEqual(validation["verdict"], "invalid")
        self.assertEqual(validation["reason_code"], "semantic-invalid")
        target = next(
            item
            for item in assembled.value["scoring_targets"]
            if item["session_id"] == plan["sessions"][0]["session_id"]
            and item["arm_id"] == "hybrid-router"
            and item["task_id"] == task["task_id"]
        )
        self.assertEqual(
            target["scored_output_event_sequence"], fallback["sequence"]
        )
        self.assertEqual(target["output_sha256"], fallback["output_sha256"])
        capture_statuses = [
            item["status"]
            for item in assembled.value["external_capture_metadata"]
            if item["session_id"] == validation["session_id"]
            and item["arm_id"] == "hybrid-router"
            and item["task_id"] == task["task_id"]
        ]
        self.assertEqual(capture_statuses, ["completed", "completed"])

    def test_router_decision_must_precede_semantic_invalid_primary(self):
        plan, trace, _ = make_fixture(
            completed_primary_validation_fallback=True
        )
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][2]
        task_id = arm["task_results"][0]["task_id"]
        task_events = [
            event for event in arm["events"] if event["task_id"] == task_id
        ]
        sender, router, primary, validator, fallback = task_events
        self.assertEqual(
            [event["phase"] for event in task_events],
            ["sender", "router", "receiver", "safety", "fallback"],
        )
        router_index = arm["events"].index(router)
        primary_index = arm["events"].index(primary)
        arm["events"][router_index], arm["events"][primary_index] = (
            arm["events"][primary_index],
            arm["events"][router_index],
        )
        for sequence, event in enumerate(arm["events"]):
            event["sequence"] = sequence

        route = arm["task_results"][0]["route"]
        route["decision_event_sequence"] = router["sequence"]
        route["receiver_event_sequence"] = fallback["sequence"]
        arm["scoring_bindings"][0]["scored_output_event_sequence"] = fallback[
            "sequence"
        ]
        validator_source = validator["source"]
        validator_source["primary_event_sequence"] = primary["sequence"]
        validator_source["input_sha256"] = post_receiver_validation_input_sha256(
            task_id=task_id,
            task_sha256=validator_source["task_sha256"],
            primary_event_sequence=primary["sequence"],
            primary_output_sha256=validator_source["primary_output_sha256"],
        )
        validator_source["output_sha256"] = (
            post_receiver_validation_output_sha256(
                input_sha256=validator_source["input_sha256"],
                verdict=validator_source["verdict"],
                reason_code=validator_source["reason_code"],
            )
        )
        rebind_arm_manifest(plan, sessions, 0, 2)

        with self.assertRaisesRegex(
            VerificationError, "router decision must precede its primary"
        ):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_semantic_validator_must_bind_exact_captured_primary_output(self):
        plan, trace, stores = make_fixture(
            completed_primary_validation_fallback=True
        )
        sessions = deepcopy(trace["sessions"])
        hybrid = sessions[0]["arms"][2]
        validator = next(
            event
            for event in hybrid["events"]
            if event["source"].get("kind") == "deterministic-validator"
        )
        source = validator["source"]
        source["primary_output_sha256"] = sha256_ref(
            {"provider_output_text": '{"forged":true}'}
        )
        source["input_sha256"] = post_receiver_validation_input_sha256(
            task_id=validator["task_id"],
            task_sha256=source["task_sha256"],
            primary_event_sequence=source["primary_event_sequence"],
            primary_output_sha256=source["primary_output_sha256"],
        )
        source["output_sha256"] = post_receiver_validation_output_sha256(
            input_sha256=source["input_sha256"],
            verdict=source["verdict"],
            reason_code=source["reason_code"],
        )
        forged_trace = build_execution_trace(
            plan_value=plan,
            sessions=sessions,
            external_bundle_sha256s=trace["external_bundle_sha256s"],
        )
        with self.assertRaisesRegex(VerificationError, "exact completed primary"):
            assemble_execution_trace(plan, forged_trace, stores)

    def test_semantic_validator_must_use_frozen_semantic_scorer(self):
        plan, trace, _ = make_fixture(
            completed_primary_validation_fallback=True
        )
        plan = deepcopy(plan)
        sessions = deepcopy(trace["sessions"])
        hybrid = sessions[0]["arms"][2]
        validator = next(
            event
            for event in hybrid["events"]
            if event["source"].get("kind") == "deterministic-validator"
        )
        validator["source"]["implementation_sha256"] = sha256_ref(
            {"different": "validator"}
        )
        rebind_arm_manifest(plan, sessions, 0, 2)
        with self.assertRaisesRegex(VerificationError, "frozen semantic scorer"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_semantic_validator_cannot_relabel_a_noncompleted_primary(self):
        plan, trace, stores = make_fixture(
            completed_primary_validation_fallback=True
        )
        hybrid = trace["sessions"][0]["arms"][2]
        task_id = hybrid["task_results"][0]["task_id"]
        primary_call_id = next(
            event["source"]["call_request"]["call_id"]
            for event in hybrid["events"]
            if event["task_id"] == task_id and event["phase"] == "receiver"
        )
        old_store = next(
            store
            for store in stores
            if primary_call_id
            in {record["call_id"] for record in store.value["records"]}
        )
        replacement = rebuild_store(
            old_store,
            status_overrides={primary_call_id: ("refused", None)},
        )
        replaced_trace = replace_bundle_reference(
            plan,
            trace,
            old_bundle_sha256="sha256:" + old_store.value["bundle_sha256"],
            new_bundle_sha256="sha256:" + replacement.value["bundle_sha256"],
        )
        replacement_stores = [
            replacement if store is old_store else store for store in stores
        ]
        with self.assertRaisesRegex(VerificationError, "requires a completed primary"):
            assemble_execution_trace(plan, replaced_trace, replacement_stores)

    def test_baseline_message_content_must_match_plan_manifest_preimage(self):
        plan, trace, _ = make_fixture()
        sessions = deepcopy(trace["sessions"])
        source = sessions[0]["arms"][0]["events"][0]["source"]
        old = CallRequest.from_value(source["call_request"])
        changed_messages = deepcopy(old.value["messages"])
        changed_messages[-1]["content"] += " changed"
        source["call_request"] = dict(
            CallRequest.build(
                episode_id=old.value["episode_id"],
                turn_index=old.value["turn_index"],
                attempt_index=old.value["attempt_index"],
                purpose=old.value["purpose"],
                agent=old.value["agent"],
                model_code=old.value["model_ref"]["family_code"],
                logical_model_id=old.value["model_ref"]["logical_model_id"],
                arm=old.value["arm"],
                messages=changed_messages,
                mock_scenario_key=old.value["mock_metadata"]["scenario_key"],
            ).value
        )
        with self.assertRaisesRegex(VerificationError, "frozen execution manifest"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_baseline_request_cannot_be_relabelled_to_another_task(self):
        plan, trace, _ = make_fixture()
        plan = deepcopy(plan)
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][0]
        first_task_id = arm["events"][0]["task_id"]
        second_task_id = arm["events"][1]["task_id"]
        arm["events"][0]["task_id"] = second_task_id
        arm["events"][1]["task_id"] = first_task_id
        rebind_arm_manifest(plan, sessions, 0, 0)
        with self.assertRaisesRegex(VerificationError, "wrong frozen task"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_baseline_foreign_content_cannot_keep_current_task_metadata(self):
        plan, trace, _ = make_fixture()
        plan = deepcopy(plan)
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][0]
        source = arm["events"][0]["source"]
        old = CallRequest.from_value(source["call_request"])
        foreign_task_messages = sessions[0]["task_inputs"][1][
            "provider_neutral_messages"
        ]
        source["call_request"] = dict(
            CallRequest.build(
                episode_id=old.value["episode_id"],
                turn_index=old.value["turn_index"],
                attempt_index=old.value["attempt_index"],
                purpose=old.value["purpose"],
                agent=old.value["agent"],
                model_code=old.value["model_ref"]["family_code"],
                logical_model_id=old.value["model_ref"]["logical_model_id"],
                arm=old.value["arm"],
                messages=[old.value["messages"][0], *foreign_task_messages],
                mock_scenario_key=plan["sessions"][0]["tasks"][0][
                    "task_sha256"
                ],
            ).value
        )
        rebind_arm_manifest(plan, sessions, 0, 0)
        with self.assertRaisesRegex(VerificationError, "exact frozen task input"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_hybrid_sender_output_must_match_task_specific_projection(self):
        plan, trace, _ = make_fixture()
        plan = deepcopy(plan)
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][2]
        first_task_id = arm["task_results"][0]["task_id"]
        second_task_id = arm["task_results"][1]["task_id"]
        first_sender = next(
            event
            for event in arm["events"]
            if event["task_id"] == first_task_id and event["phase"] == "sender"
        )
        second_receiver = next(
            event
            for event in arm["events"]
            if event["task_id"] == second_task_id and event["phase"] == "receiver"
        )
        first_sender["source"]["output_sha256"] = second_receiver["source"][
            "hybrid_projection"
        ]["projection"]["payload_sha256"]
        rebind_arm_manifest(plan, sessions, 0, 2)
        with self.assertRaisesRegex(VerificationError, "direct receiver payload"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_route_mode_relabel_cannot_escape_sealed_router_decision(self):
        plan, trace, _ = make_fixture()
        for relabeled_mode in ("routine", "raw", "json", "silence"):
            with self.subTest(relabeled_mode=relabeled_mode):
                sessions = deepcopy(trace["sessions"])
                sessions[0]["arms"][2]["task_results"][0]["route"][
                    "selected_mode"
                ] = relabeled_mode
                with self.assertRaisesRegex(VerificationError, "sealed router"):
                    build_execution_trace(
                        plan_value=plan,
                        sessions=sessions,
                        external_bundle_sha256s=trace[
                            "external_bundle_sha256s"
                        ],
                    )

    def test_action_state_route_requires_its_exact_sender_event(self):
        plan, trace, _ = make_fixture()
        plan = deepcopy(plan)
        sessions = deepcopy(trace["sessions"])
        arm = sessions[0]["arms"][2]
        sender = next(
            event
            for event in arm["events"]
            if event["task_id"] == arm["task_results"][0]["task_id"]
            and event["phase"] == "sender"
        )
        sender["phase"] = "safety"
        arm["zero_token_phases"].remove("safety")
        rebind_arm_manifest(plan, sessions, 0, 2)
        with self.assertRaisesRegex(VerificationError, "sender event"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_pre_receiver_semantic_failure_uses_one_raw_fallback(self):
        plan, trace, stores = make_fixture(pre_receiver_fallback=True)
        assembled = assemble_execution_trace(plan, trace, stores)
        arm = assembled.result["records"][0]["arms"][2]
        task = arm["task_results"][0]
        task_events = [
            event for event in arm["events"] if event["task_id"] == task["task_id"]
        ]
        self.assertEqual(
            [event["phase"] for event in task_events],
            ["sender", "router", "fallback"],
        )
        self.assertEqual(task["route"]["selected_mode"], "raw")
        self.assertEqual(task["route"]["fallback_from"], "action-state:semantic")

    def test_fallback_reason_must_be_action_state_namespaced(self):
        plan, trace, _ = make_fixture(fallback_recovery=True)
        sessions = deepcopy(trace["sessions"])
        sessions[0]["arms"][2]["task_results"][0]["route"][
            "fallback_from"
        ] = "anything"
        with self.assertRaisesRegex(VerificationError, "must start action-state"):
            build_execution_trace(
                plan_value=plan,
                sessions=sessions,
                external_bundle_sha256s=trace["external_bundle_sha256s"],
            )

    def test_external_run_identity_is_precommitted(self):
        plan, trace, stores = make_fixture()
        old_store = stores[0]
        replacement = rebuild_store(old_store, run_id=bare("moved-run"))
        old_sha = "sha256:" + old_store.value["bundle_sha256"]
        new_sha = "sha256:" + replacement.value["bundle_sha256"]
        moved_trace = replace_bundle_reference(
            plan,
            trace,
            old_bundle_sha256=old_sha,
            new_bundle_sha256=new_sha,
        )
        with self.assertRaisesRegex(VerificationError, "run/profile identity"):
            assemble_execution_trace(plan, moved_trace, [replacement, *stores[1:]])

    def test_external_provider_profile_is_precommitted(self):
        plan, trace, stores = make_fixture()
        old_store = stores[0]
        alternate_profile = build_execution_profile(
            provider_id="provider.alt",
            api_id="responses/v2",
            normalizer_id="alternate-normalizer-v1",
            normalizer_sha256=bare("alternate-normalizer"),
        )
        replacement = rebuild_store(
            old_store, execution_profile=alternate_profile
        )
        moved_trace = replace_bundle_reference(
            plan,
            trace,
            old_bundle_sha256="sha256:" + old_store.value["bundle_sha256"],
            new_bundle_sha256="sha256:" + replacement.value["bundle_sha256"],
        )
        with self.assertRaisesRegex(VerificationError, "run/profile identity"):
            assemble_execution_trace(plan, moved_trace, [replacement, *stores[1:]])

    def test_external_bundle_record_order_must_match_trace_chronology(self):
        plan, trace, stores = make_fixture()
        old_store = stores[0]
        replacement = rebuild_store(old_store, reverse_records=True)
        reordered_trace = replace_bundle_reference(
            plan,
            trace,
            old_bundle_sha256="sha256:" + old_store.value["bundle_sha256"],
            new_bundle_sha256="sha256:" + replacement.value["bundle_sha256"],
        )
        with self.assertRaisesRegex(VerificationError, "record order"):
            assemble_execution_trace(
                plan, reordered_trace, [replacement, *stores[1:]]
            )

    def test_completed_primary_cannot_be_replaced_by_fallback(self):
        plan, trace, stores = make_fixture(fallback_recovery=True)
        hybrid = trace["sessions"][0]["arms"][2]
        task_id = hybrid["task_results"][0]["task_id"]
        primary_call_id = next(
            event["source"]["call_request"]["call_id"]
            for event in hybrid["events"]
            if event["task_id"] == task_id and event["phase"] == "receiver"
        )
        old_store = next(
            store
            for store in stores
            if primary_call_id
            in {record["call_id"] for record in store.value["records"]}
        )
        replacement = rebuild_store(
            old_store,
            status_overrides={
                primary_call_id: ("completed", '{"ok":true,"primary":true}')
            },
        )
        replaced_trace = replace_bundle_reference(
            plan,
            trace,
            old_bundle_sha256="sha256:" + old_store.value["bundle_sha256"],
            new_bundle_sha256="sha256:" + replacement.value["bundle_sha256"],
        )
        replacement_stores = [
            replacement if store is old_store else store for store in stores
        ]
        with self.assertRaisesRegex(VerificationError, "completed primary"):
            assemble_execution_trace(plan, replaced_trace, replacement_stores)


if __name__ == "__main__":
    unittest.main()
