"""Offline-only assembly of provider-neutral captures into result ledgers.

This module performs no provider call and grants no execution or claim
authority.  It consumes already validated ``ExternalResponseStore`` objects,
derives every provider event usage field without mapping an unknown to zero,
and emits RESULT-compatible matched-session records plus content-only usage
receipts.  Provider normalization, signatures, scorer receipts, sandbox
receipts, and independent-operator authentication remain deliberately out of
scope and fail closed in the existing verifier.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from competitive_eval.errors import EvaluationError
from competitive_eval.external_replay import ExternalResponseStore
from competitive_eval.protocol import CallRequest

from .contract import (
    ARMS,
    EVENT_PHASES,
    RESULT_SCHEMA,
    SESSION_RESULT_SCHEMA,
    VerificationError,
    canonical_json,
    sha256_ref,
    validate_study_plan,
)
from .execution_trace import (
    CANONICAL_SILENCE_OUTPUT_SHA256,
    SILENCE_TERMINAL_STATUS,
    validate_execution_trace,
)
from .receipt_store import RECEIPT_BUNDLE_SCHEMA, RECEIPT_SCHEMA
from .verifier import _validate_session_result, _validate_usage


ASSEMBLY_SCHEMA = "urusilla-initial-goal-trace-assembly/1"
ASSEMBLY_BLOCKERS = (
    "provider receipts are content-bound but not independently re-normalized",
    "deterministic local sender/router outputs are content-bound but not "
    "independently replayed",
    "provider, operator, and auditor signatures are not authenticated",
    "the current scorer receipt schema does not bind a score to the exact captured provider output digest",
    "only usage receipts are assembled; scorer and sandbox receipts remain external",
    "the frozen scorer-receipt schema does not yet authenticate scored-output bindings",
    "the frozen phase schema cannot yet bind deterministic rejection of a completed "
    "primary output before fallback, so that lane is rejected rather than inferred",
    "offline trace assembly is not independent performance evidence",
)


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _prefixed_sha256(value: str, path: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise VerificationError(f"{path} is not a lowercase SHA-256 digest")
    return "sha256:" + value


def _external_usage(value: Mapping[str, Any]) -> dict[str, Any]:
    if value["status"] != "complete":
        raise VerificationError("external usage is incomplete")
    if value["unclassified_usage_json"] is not None:
        raise VerificationError("external usage has an unnormalized remainder")
    input_tokens = value["input_tokens"]
    output_tokens = value["output_tokens"]
    total_tokens = value["total_tokens"]
    if any(type(item) is not int or item < 0 for item in (input_tokens, output_tokens, total_tokens)):
        raise VerificationError("external core token usage is unknown")
    accounting = value["reasoning_accounting"]
    reasoning = value["reasoning_tokens_subset"]
    if accounting == "not-reported":
        if reasoning is not None:
            raise VerificationError("unreported external reasoning must remain unknown")
        unclassified: int | None = None
    elif accounting in {"included-in-output", "separately-reported"}:
        if type(reasoning) is not int or reasoning < 0:
            raise VerificationError("classified external reasoning is missing")
        unclassified = 0
    else:
        raise VerificationError("external reasoning accounting is unsupported")
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "unclassified_tokens": unclassified,
        "provider_total_tokens": total_tokens,
        "total_tokens": total_tokens,
        "hidden_accounting": accounting,
    }
    _, complete = _validate_usage(usage, "assembled.external_usage")
    if not complete:
        raise VerificationError("external usage did not close exactly")
    return usage


def _local_usage(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        raise VerificationError("deterministic local usage must be an object")
    usage = _detach(value)
    _, complete = _validate_usage(usage, "assembled.local_usage")
    if not complete:
        raise VerificationError("deterministic local usage is incomplete")
    if (
        usage["provider_total_tokens"] is not None
        or usage["hidden_accounting"] != "none"
        or usage["reasoning_tokens"] != 0
        or usage["unclassified_tokens"] != 0
    ):
        raise VerificationError(
            "deterministic local usage cannot claim provider or hidden reasoning tokens"
        )
    return usage


def _coverage(
    events: Sequence[Mapping[str, Any]],
    *,
    zero_phases: Sequence[str],
    setup_included_in_call_id: str | None,
    event_call_ids: Mapping[int, str | None],
) -> dict[str, str]:
    observed = {event["phase"] for event in events}
    coverage: dict[str, str] = {}
    for phase in EVENT_PHASES:
        if phase in observed:
            coverage[phase] = "counted"
        elif phase == "setup" and setup_included_in_call_id is not None:
            matching = [
                event
                for event in events
                if event_call_ids[event["sequence"]] == setup_included_in_call_id
            ]
            if len(matching) != 1 or matching[0]["usage"]["provider_total_tokens"] is None:
                raise VerificationError("setup is not covered by one exact provider total")
            coverage[phase] = "included-in-provider-total"
        elif phase in zero_phases:
            coverage[phase] = "proven-zero"
        else:  # validate_execution_trace should make this unreachable.
            raise VerificationError(f"token phase is unaccounted: {phase}")

    output_values = [event["usage"]["output_tokens"] for event in events]
    if any(value is None for value in output_values):
        raise VerificationError("output token accounting is unknown")
    coverage["output"] = (
        "counted" if any(value > 0 for value in output_values) else "proven-zero"
    )

    if any(event["usage"]["hidden_accounting"] == "not-reported" for event in events):
        coverage["reasoning"] = "included-in-provider-total"
    else:
        reasoning_values = [event["usage"]["reasoning_tokens"] for event in events]
        if any(value is None for value in reasoning_values):
            raise VerificationError("reasoning token accounting is unknown")
        coverage["reasoning"] = (
            "counted" if any(value > 0 for value in reasoning_values) else "proven-zero"
        )
    return coverage


def _usage_receipt(
    *,
    plan: Mapping[str, Any],
    session: Mapping[str, Any],
    arm_id: str,
    execution_manifest_sha256: str,
    event: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> dict[str, Any]:
    binding = {
        "study_id": plan["study_id"],
        "plan_sha256": sha256_ref(plan),
        "session_id": session["session_id"],
        "arm_id": arm_id,
        "execution_manifest_sha256": execution_manifest_sha256,
        "receiver_family": session["receiver_family"],
        "event_sequence": event["sequence"],
        "phase": event["phase"],
        "task_id": event["task_id"],
        "input_sha256": event["input_sha256"],
        "output_sha256": event["output_sha256"],
        "usage": event["usage"],
    }
    source = dict(source_payload)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "kind": "usage",
        "issuer_id": session["operator_id"],
        "binding": binding,
        "source_payload": source,
        "source_sha256": sha256_ref(source),
    }
    return receipt


@dataclass(frozen=True)
class TraceAssembly:
    """Defensive wrapper around one verified, explicitly non-claim assembly."""

    _value: Mapping[str, Any]

    @property
    def value(self) -> Mapping[str, Any]:
        return _detach(self._value)

    @property
    def result(self) -> Mapping[str, Any]:
        return _detach(self._value["result"])

    @property
    def usage_receipt_bundle(self) -> Mapping[str, Any]:
        return _detach(self._value["usage_receipt_bundle"])

    @property
    def claim_eligible(self) -> bool:
        return False


def assemble_execution_trace(
    plan_value: Any,
    trace_value: Any,
    external_stores: Sequence[ExternalResponseStore],
) -> TraceAssembly:
    """Assemble a complete three-arm result without performing an external call."""

    validate_study_plan(plan_value)
    plan = plan_value
    trace = validate_execution_trace(plan_value, trace_value)
    model_by_family = {item["family"]: item for item in plan["receiver_models"]}

    stores: dict[str, ExternalResponseStore] = {}
    for store in external_stores:
        if not isinstance(store, ExternalResponseStore):
            raise VerificationError("external_stores must contain validated stores")
        digest = _prefixed_sha256(
            store.value["bundle_sha256"], "external response bundle digest"
        )
        if digest in stores:
            raise VerificationError("the same external bundle was supplied more than once")
        stores[digest] = store
    if set(stores) != set(trace["external_bundle_sha256s"]):
        raise VerificationError("supplied external bundles differ from the frozen trace")

    used_calls: set[str] = set()
    used_local_events: set[str] = set()
    provider_identities: set[tuple[str, str]] = set()
    expected_requests: dict[str, list[CallRequest]] = {digest: [] for digest in stores}
    receipts: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    scoring_targets: list[dict[str, Any]] = []
    external_capture_metadata: list[dict[str, Any]] = []

    planned_by_session = {item["session_id"]: item for item in plan["sessions"]}
    for session in trace["sessions"]:
        planned = planned_by_session[session["session_id"]]
        model = model_by_family[session["receiver_family"]]
        assembled_arms: list[dict[str, Any]] = []
        for arm_id, arm in zip(ARMS, session["arms"]):
            assembled_events: list[dict[str, Any]] = []
            call_id_by_sequence: dict[int, str | None] = {}
            status_by_sequence: dict[int, str] = {}
            for event_spec in arm["events"]:
                source = event_spec["source"]
                source_kind = source["kind"]
                call_id: str | None = None
                capture_metadata_index: int | None = None
                if source_kind == "external-response":
                    bundle_sha = source["bundle_sha256"]
                    store = stores[bundle_sha]
                    bundle_value = store.value
                    execution_binding = source["execution_binding"]
                    observed_execution_binding = {
                        "run_id": _prefixed_sha256(
                            bundle_value["run_id"], "external bundle run ID"
                        ),
                        "run_manifest_sha256": _prefixed_sha256(
                            bundle_value["run_manifest_sha256"],
                            "external bundle run manifest",
                        ),
                        "episode_sequence_sha256": _prefixed_sha256(
                            bundle_value["episode_sequence_sha256"],
                            "external bundle episode sequence",
                        ),
                        "execution_profile_sha256": _prefixed_sha256(
                            store.execution_profile["profile_sha256"],
                            "external bundle execution profile",
                        ),
                        "bundle_record_sequence": execution_binding[
                            "bundle_record_sequence"
                        ],
                    }
                    if execution_binding != observed_execution_binding:
                        raise VerificationError(
                            "external bundle run/profile identity differs from its "
                            "precommitted execution binding"
                        )
                    if bundle_value["producer"]["operator_id"] != session["operator_id"]:
                        raise VerificationError(
                            "external bundle producer differs from the frozen session operator"
                        )
                    try:
                        request = CallRequest.from_value(source["call_request"])
                        captured = store.resolve(
                            request, require_core_usage_capture=True
                        )
                    except EvaluationError as exc:
                        raise VerificationError(f"external capture cannot be resolved: {exc}") from exc
                    call_id = request.call_id
                    if call_id in used_calls:
                        raise VerificationError("one external call was charged more than once")
                    used_calls.add(call_id)
                    expected_requests[bundle_sha].append(request)

                    response = captured.value["response"]
                    if (
                        captured.value["sequence"]
                        != execution_binding["bundle_record_sequence"]
                    ):
                        raise VerificationError(
                            "captured provider record order differs from the "
                            "precommitted trace order"
                        )
                    observation = response["provider_observation"]
                    hybrid_projection = source["hybrid_projection"]
                    if request.value["arm"] == "urusilla_hybrid_direct_receiver_v1" and hybrid_projection is None:
                        raise VerificationError(
                            "hybrid receiver capture lacks its validated projection"
                        )
                    if (
                        hybrid_projection is not None
                        and hybrid_projection["projection"][
                            "execution_profile_sha256"
                        ]
                        != store.execution_profile["profile_sha256"]
                    ):
                        raise VerificationError(
                            "hybrid projection differs from the capture execution profile"
                        )
                    for kind, field in (
                        ("provider-request", "request_id"),
                        ("provider-response", "response_id"),
                        ("raw-receipt", "raw_receipt_sha256"),
                    ):
                        identity = observation[field]
                        if type(identity) is not str or not identity:
                            raise VerificationError("provider identity is incomplete")
                        pair = (kind, identity)
                        if pair in provider_identities:
                            raise VerificationError(
                                "provider identity is replayed across external bundles"
                            )
                        provider_identities.add(pair)

                    if event_spec["phase"] in {"receiver", "fallback"}:
                        if (
                            request.value["model_ref"]["family_code"]
                            != session["receiver_family"]
                            or request.value["model_ref"]["logical_model_id"]
                            != model["model_id"]
                            or _prefixed_sha256(
                                request.settings_sha256, "receiver request settings"
                            )
                            != model["settings_sha256"]
                        ):
                            raise VerificationError(
                                "receiver capture differs from the frozen model or settings"
                            )
                    usage = _external_usage(response["usage"])
                    if (
                        hybrid_projection is not None
                        and usage["total_tokens"]
                        > hybrid_projection["projection"]["maximum_total_tokens"]
                    ):
                        raise VerificationError(
                            "hybrid capture exceeds its projected maximum total tokens"
                        )
                    output_text = response["output_text"]
                    input_sha256 = sha256_ref(
                        {"provider_neutral_messages": request.value["messages"]}
                    )
                    output_sha256 = (
                        None
                        if output_text is None
                        else sha256_ref({"provider_output_text": output_text})
                    )
                    source_payload = {
                        "source_kind": "provider",
                        "request_id": observation["request_id"],
                        "response_id": observation["response_id"],
                        "model_id": observation["resolved_model_id"],
                        "settings_sha256": _prefixed_sha256(
                            request.settings_sha256, "provider request settings"
                        ),
                        "reported_usage": usage,
                        "raw_receipt_sha256": _prefixed_sha256(
                            observation["raw_receipt_sha256"],
                            "raw provider receipt digest",
                        ),
                    }
                    if response["status"] != "completed" and event_spec["task_id"] is None:
                        raise VerificationError(
                            "a noncompleted provider call lacks a failed-task binding"
                        )
                    event_status = response["status"]
                    capture_metadata_index = len(external_capture_metadata)
                    external_capture_metadata.append(
                        {
                            "session_id": session["session_id"],
                            "arm_id": arm_id,
                            "task_id": event_spec["task_id"],
                            "event_sequence": event_spec["sequence"],
                            "bundle_sha256": bundle_sha,
                            "bundle_record_sequence": captured.value["sequence"],
                            "call_id": call_id,
                            "response_sha256": _prefixed_sha256(
                                response["response_sha256"],
                                "captured provider response digest",
                            ),
                            "status": event_status,
                        }
                    )
                else:
                    local_id = source["local_event_id"]
                    if local_id in used_local_events:
                        raise VerificationError(
                            "one deterministic local event was charged more than once"
                        )
                    used_local_events.add(local_id)
                    usage = _local_usage(source["usage"])
                    input_sha256 = source["input_sha256"]
                    output_sha256 = source["output_sha256"]
                    if usage["output_tokens"] > 0 and output_sha256 is None:
                        raise VerificationError(
                            "local output tokens lack an exact output binding"
                        )
                    source_payload = {
                        "source_kind": "deterministic-local",
                        "request_id": None,
                        "response_id": None,
                        "model_id": None,
                        "settings_sha256": None,
                        "reported_usage": usage,
                        "raw_receipt_sha256": sha256_ref(
                            {
                                "local_event_id": local_id,
                                "implementation_sha256": source[
                                    "implementation_sha256"
                                ],
                                "input_sha256": input_sha256,
                                "output_sha256": output_sha256,
                                "usage": usage,
                            }
                        ),
                    }
                    event_status = "completed"

                event = {
                    "sequence": event_spec["sequence"],
                    "phase": event_spec["phase"],
                    "task_id": event_spec["task_id"],
                    "input_sha256": input_sha256,
                    "output_sha256": output_sha256,
                    "usage_receipt_sha256": None,
                    "usage": usage,
                }
                receipt = _usage_receipt(
                    plan=plan,
                    session=session,
                    arm_id=arm_id,
                    execution_manifest_sha256=arm["execution_manifest_sha256"],
                    event=event,
                    source_payload=source_payload,
                )
                event["usage_receipt_sha256"] = sha256_ref(receipt)
                if capture_metadata_index is not None:
                    external_capture_metadata[capture_metadata_index][
                        "usage_receipt_sha256"
                    ] = event["usage_receipt_sha256"]
                receipts.append(receipt)
                assembled_events.append(event)
                call_id_by_sequence[event["sequence"]] = call_id
                status_by_sequence[event["sequence"]] = event_status

            if arm_id == "hybrid-router":
                by_sequence = {event["sequence"]: event for event in assembled_events}
                for task_result in arm["task_results"]:
                    route = task_result["route"]
                    if type(route) is not dict:
                        continue
                    receiver_sequence = route["receiver_event_sequence"]
                    if receiver_sequence is None:
                        continue
                    receiver_event = by_sequence[receiver_sequence]
                    if route["fallback_from"] is None:
                        if receiver_event["phase"] == "fallback":
                            raise VerificationError(
                                "fallback cost is present without a fallback disposition"
                            )
                    elif receiver_event["phase"] != "fallback":
                        raise VerificationError(
                            "fallback disposition does not bind its exact fallback cost"
                        )

            by_sequence = {event["sequence"]: event for event in assembled_events}
            event_spec_by_sequence = {
                event["sequence"]: event for event in arm["events"]
            }
            for binding, task_result in zip(
                arm["scoring_bindings"], arm["task_results"]
            ):
                scored_sequence = binding["scored_output_event_sequence"]
                if (
                    arm_id == "hybrid-router"
                    and task_result["route"]["selected_mode"] == "silence"
                ):
                    if (
                        scored_sequence is not None
                        or binding["output_sha256"]
                        != CANONICAL_SILENCE_OUTPUT_SHA256
                        or binding["terminal_status"] != SILENCE_TERMINAL_STATUS
                    ):
                        raise VerificationError(
                            "silence scoring target lost its canonical no-output binding"
                        )
                    scoring_targets.append(
                        {
                            "session_id": session["session_id"],
                            "arm_id": arm_id,
                            "task_id": task_result["task_id"],
                            "scored_output_event_sequence": None,
                            "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                            "terminal_status": SILENCE_TERMINAL_STATUS,
                        }
                    )
                    continue
                if scored_sequence is None:
                    raise VerificationError(
                        "non-silence scoring target has no terminal event"
                    )
                terminal = by_sequence[scored_sequence]
                if (
                    binding["output_sha256"] != terminal["output_sha256"]
                    or binding["terminal_status"]
                    != status_by_sequence[scored_sequence]
                ):
                    raise VerificationError(
                        "captured terminal output differs from its trace scoring target"
                    )
                if (
                    status_by_sequence[scored_sequence] != "completed"
                    and task_result["task_success"] is True
                ):
                    raise VerificationError(
                        "a noncompleted terminal output cannot be a successful task"
                    )
                if (
                    task_result["task_success"] is True
                    and terminal["usage"]["total_tokens"] == 0
                ):
                    raise VerificationError(
                        "a successful task cannot have a zero-token terminal receiver"
                    )
                if arm_id == "hybrid-router":
                    route = task_result["route"]
                    primary_specs = [
                        event
                        for event in arm["events"]
                        if event["task_id"] == task_result["task_id"]
                        and event["phase"] == "receiver"
                    ]
                    if (
                        route["selected_mode"] == "action-state"
                        and (
                            len(primary_specs) != 1
                            or primary_specs[0]["source"].get("hybrid_projection")
                            is None
                        )
                    ):
                        raise VerificationError(
                            "action-state route bypasses the validated hybrid projection"
                        )
                    fallback_specs = [
                        event
                        for event in arm["events"]
                        if event["task_id"] == task_result["task_id"]
                        and event["phase"] == "fallback"
                    ]
                    if fallback_specs and primary_specs:
                        primary_status = status_by_sequence[
                            primary_specs[0]["sequence"]
                        ]
                        if primary_status == "completed":
                            raise VerificationError(
                                "a completed primary receiver cannot be replaced by fallback"
                            )
                        if route["fallback_from"] != (
                            f"action-state:receiver:{primary_status}"
                        ):
                            raise VerificationError(
                                "post-receiver fallback reason differs from the exact "
                                "captured primary status"
                            )
                scoring_targets.append(
                    {
                        "session_id": session["session_id"],
                        "arm_id": arm_id,
                        "task_id": task_result["task_id"],
                        "scored_output_event_sequence": scored_sequence,
                        "output_sha256": terminal["output_sha256"],
                        "terminal_status": status_by_sequence[scored_sequence],
                    }
                )

            coverage = _coverage(
                assembled_events,
                zero_phases=arm["zero_token_phases"],
                setup_included_in_call_id=arm["setup_included_in_call_id"],
                event_call_ids=call_id_by_sequence,
            )
            assembled_arms.append(
                {
                    "arm_id": arm_id,
                    "execution_manifest_sha256": arm[
                        "execution_manifest_sha256"
                    ],
                    "disposition": arm["disposition"],
                    "events": assembled_events,
                    "scope_coverage": coverage,
                    "sandbox_evidence": arm["sandbox_evidence"],
                    "task_results": arm["task_results"],
                }
            )

        record = {
            "schema_version": SESSION_RESULT_SCHEMA,
            "session_id": session["session_id"],
            "cluster_id": session["cluster_id"],
            "domain_id": session["domain_id"],
            "receiver_family": session["receiver_family"],
            "operator_id": session["operator_id"],
            "executed_arm_order": session["executed_arm_order"],
            "attestation": session["attestation"],
            "arms": assembled_arms,
        }
        _, complete, all_attested = _validate_session_result(
            record,
            planned,
            plan["sandbox_boundaries"],
            f"assembled.records[{len(records)}]",
        )
        if not complete or not all_attested:
            raise VerificationError("assembled session is not RESULT-compatible and complete")
        records.append(record)

    for bundle_sha, store in stores.items():
        coverage = store.coverage(expected_requests[bundle_sha])
        if not coverage["all_bundle_records_accounted_for"]:
            raise VerificationError("external response bundle contains an unused capture")

    result = {
        "schema_version": RESULT_SCHEMA,
        "study_id": plan["study_id"],
        "plan_sha256": sha256_ref(plan),
        "result_status": "completed",
        "records": records,
        "notes": [
            "Offline provider-neutral assembly only; authentication remains fail-closed."
        ],
    }
    usage_receipt_bundle = {
        "schema_version": RECEIPT_BUNDLE_SCHEMA,
        "plan_sha256": sha256_ref(plan),
        "receipts": receipts,
    }
    external_capture_metadata.sort(
        key=lambda item: (item["bundle_sha256"], item["bundle_record_sequence"])
    )
    core: dict[str, Any] = {
        "schema_version": ASSEMBLY_SCHEMA,
        "plan_sha256": sha256_ref(plan),
        "trace_sha256": trace["trace_sha256"],
        "offline_only": True,
        "claim_eligible": False,
        "authentication_complete": False,
        "claim_blockers": list(ASSEMBLY_BLOCKERS),
        "external_capture_metadata": external_capture_metadata,
        "scoring_targets": scoring_targets,
        "result": result,
        "usage_receipt_bundle": usage_receipt_bundle,
    }
    core["assembly_sha256"] = sha256_ref(core)
    return TraceAssembly(_detach(core))


__all__ = [
    "ASSEMBLY_BLOCKERS",
    "ASSEMBLY_SCHEMA",
    "TraceAssembly",
    "assemble_execution_trace",
]
