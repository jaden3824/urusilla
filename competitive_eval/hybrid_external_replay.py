"""Cold-only external capture for one bounded hybrid receiver request.

This eval-side module projects an already validated cold
``DirectReceiverRequest`` onto the existing provider-neutral external response
exchange. It neither performs a network call nor adapts the captured output
into a normal runtime ``ReceiverExecution``.

The submitted role/content strings contain the actual canonical public task
context, declarative Capsule, and payload. Provider templates, hidden prefixes,
normalization, and true model-visible bytes remain outside this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from urusilla_hybrid_runtime.canonical import sha256_text
from urusilla_hybrid_runtime.comprehension import ReceiverModelBinding
from urusilla_hybrid_runtime.receiver import DirectReceiverRequest

from .canonical import (
    canonical_bytes,
    canonical_json,
    sha256_bytes,
    strict_json_loads,
)
from .errors import IntegrityError, ManifestError
from .external_replay import (
    CLAIM_BLOCKERS,
    PROVENANCE_STATUS,
    ExternalResponseStore,
)
from .protocol import CallRequest


HYBRID_PROJECTION_FORMAT = "competitive-eval-hybrid-receiver-projection-v1"
PENDING_HYBRID_CALL_FORMAT = "competitive-eval-pending-hybrid-receiver-call-v1"
HYBRID_CAPTURE_FORMAT = "competitive-eval-hybrid-receiver-capture-v1"
HYBRID_ARM = "urusilla_hybrid_direct_receiver_v1"
USAGE_CAPTURE_SCOPE = (
    "operator-supplied-content-bound-input-output-total-not-renormalized"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_USAGE_FIELDS = frozenset(
    {
        "status",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens_subset",
        "reasoning_accounting",
        "actual_billed_usd",
        "unclassified_usage_json",
    }
)
_PROJECTION_FIELDS = frozenset(
    {
        "format",
        "direct_receiver_binding_sha256",
        "runtime_transcript_sha256",
        "provider_neutral_messages_sha256",
        "mode",
        "delivery_disposition",
        "maximum_total_tokens",
        "task_context_sha256",
        "task_profile_sha256",
        "symbol_table_sha256",
        "task_context_included",
        "task_context_id",
        "task_comprehension_evidence_sha256",
        "task_comprehension_verifier_sha256",
        "capsule_sha256",
        "capsule_included",
        "capsule_context_id",
        "comprehension_evidence_sha256",
        "capsule_comprehension_verifier_sha256",
        "payload_sha256",
        "receiver_binding_sha256",
        "execution_profile_sha256",
    }
)


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _validate_captured_usage(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(_USAGE_FIELDS):
        raise ManifestError("hybrid external capture usage fields differ")
    if value["status"] != "complete":
        raise ManifestError("hybrid external capture usage is incomplete")
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        item = value[name]
        if type(item) is not int or item < 0:
            raise ManifestError(f"hybrid external capture {name} is invalid")
    for name in ("cache_read_tokens", "cache_write_tokens"):
        item = value[name]
        if item is not None and (type(item) is not int or item < 0):
            raise ManifestError(f"hybrid external capture {name} is invalid")
        if item is not None and item > value["input_tokens"]:
            raise IntegrityError(f"hybrid external capture {name} exceeds input")
    reasoning = value["reasoning_tokens_subset"]
    if reasoning is not None and (type(reasoning) is not int or reasoning < 0):
        raise ManifestError("hybrid external capture reasoning usage is invalid")
    accounting = value["reasoning_accounting"]
    if accounting == "included-in-output":
        if reasoning is None or reasoning > value["output_tokens"]:
            raise IntegrityError("hybrid external capture included reasoning differs")
        expected_total = value["input_tokens"] + value["output_tokens"]
        if value["total_tokens"] != expected_total:
            raise IntegrityError("hybrid external capture included total differs")
    elif accounting == "separately-reported":
        if reasoning is None:
            raise ManifestError("hybrid external capture separate reasoning is null")
        expected_total = (
            value["input_tokens"] + value["output_tokens"] + reasoning
        )
        if value["total_tokens"] != expected_total:
            raise IntegrityError("hybrid external capture separate total differs")
    elif accounting == "not-reported":
        if reasoning is not None:
            raise ManifestError("hybrid external capture unreported reasoning differs")
        if value["total_tokens"] < (
            value["input_tokens"] + value["output_tokens"]
        ):
            raise IntegrityError("hybrid external capture visible total is too small")
    else:
        raise ManifestError("hybrid external capture reasoning accounting differs")
    billed = value["actual_billed_usd"]
    if billed is not None and (
        type(billed) is not str or _DECIMAL.fullmatch(billed) is None
    ):
        raise ManifestError("hybrid external capture billed amount is invalid")
    if value["unclassified_usage_json"] is not None:
        raise ManifestError("hybrid external capture has unclassified usage")
    return _detach(value)


def _validate_projection(
    value: Any,
    projection_sha256: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(_PROJECTION_FIELDS):
        raise ManifestError("hybrid receiver projection fields differ")
    if value["format"] != HYBRID_PROJECTION_FORMAT:
        raise ManifestError("hybrid receiver projection format differs")
    if (
        type(projection_sha256) is not str
        or _SHA256.fullmatch(projection_sha256) is None
    ):
        raise ManifestError("hybrid receiver projection digest is invalid")
    if sha256_bytes(canonical_bytes(value)) != projection_sha256:
        raise IntegrityError("hybrid receiver projection digest mismatch")
    if value["mode"] != "action-state":
        raise IntegrityError("hybrid receiver projection is not action-state")
    if value["delivery_disposition"] != "live":
        raise IntegrityError("hybrid receiver projection is not live")
    if value["task_context_included"] is not True:
        raise IntegrityError("hybrid receiver projection is not cold task context")
    if value["capsule_included"] is not True:
        raise IntegrityError("hybrid receiver projection is not cold Capsule")
    if value["task_context_id"] is not None:
        raise IntegrityError("cold hybrid projection cannot claim task cache state")
    if value["capsule_context_id"] is not None:
        raise IntegrityError("cold hybrid projection cannot claim Capsule cache state")
    if (
        type(value["maximum_total_tokens"]) is not int
        or value["maximum_total_tokens"] <= 0
    ):
        raise ManifestError("hybrid receiver projection token ceiling is invalid")
    for name in (
        "direct_receiver_binding_sha256",
        "runtime_transcript_sha256",
        "task_context_sha256",
        "task_profile_sha256",
        "symbol_table_sha256",
        "task_comprehension_evidence_sha256",
        "task_comprehension_verifier_sha256",
        "capsule_sha256",
        "comprehension_evidence_sha256",
        "capsule_comprehension_verifier_sha256",
        "payload_sha256",
        "receiver_binding_sha256",
    ):
        item = value[name]
        if (
            type(item) is not str
            or not item.startswith("sha256:")
            or _SHA256.fullmatch(item[7:]) is None
        ):
            raise ManifestError(f"hybrid receiver projection {name} is invalid")
    for name in (
        "provider_neutral_messages_sha256",
        "execution_profile_sha256",
    ):
        item = value[name]
        if type(item) is not str or _SHA256.fullmatch(item) is None:
            raise ManifestError(f"hybrid receiver projection {name} is invalid")
    return _detach(value)


@dataclass(frozen=True)
class HybridReceiverExternalCall:
    """Immutable provider-neutral projection of one cold receiver request."""

    _projection_json: str
    projection_sha256: str
    _call_request_json: str
    claim_eligible: bool = False

    def __post_init__(self) -> None:
        projection = _validate_projection(
            strict_json_loads(self._projection_json),
            self.projection_sha256,
        )
        if canonical_json(projection) != self._projection_json:
            raise ManifestError("hybrid receiver projection is not canonical JSON")
        request_value = strict_json_loads(self._call_request_json)
        request = CallRequest.from_value(request_value)
        if request.to_json() != self._call_request_json:
            raise ManifestError("hybrid receiver call is not canonical JSON")
        if request.value["arm"] != HYBRID_ARM:
            raise IntegrityError("hybrid receiver call arm differs")
        if request.value["purpose"] != "runtime":
            raise IntegrityError("hybrid receiver call purpose differs")
        if (
            request.value["mock_metadata"]["scenario_key"]
            != self.projection_sha256
        ):
            raise IntegrityError("hybrid receiver call projection binding differs")
        messages = request.value["messages"]
        if (
            len(messages) != 2
            or messages[0]["role"] != "system"
            or messages[1]["role"] != "user"
        ):
            raise IntegrityError("hybrid receiver call role mapping differs")
        reconstructed = (
            "SYSTEM\n"
            + messages[0]["content"]
            + "\n\nUSER\n"
            + messages[1]["content"]
        )
        if sha256_text(reconstructed) != projection["runtime_transcript_sha256"]:
            raise IntegrityError("hybrid receiver runtime transcript differs")
        if (
            sha256_bytes(canonical_bytes(messages))
            != projection["provider_neutral_messages_sha256"]
        ):
            raise IntegrityError("hybrid receiver submitted messages differ")
        if self.claim_eligible is not False:
            raise ManifestError(
                "hybrid receiver external call cannot be claim-eligible"
            )

    @property
    def projection(self) -> Mapping[str, Any]:
        return _validate_projection(
            strict_json_loads(self._projection_json),
            self.projection_sha256,
        )

    @property
    def call_request(self) -> CallRequest:
        return CallRequest.from_value(strict_json_loads(self._call_request_json))


@dataclass(frozen=True)
class HybridExternalReplayCapture:
    """Claim-ineligible offline view of one captured external response."""

    output_text: str
    resolved_model_id: str
    _usage_json: str
    host_total_token_ceiling: int
    observed_within_host_total_ceiling: bool
    projection_sha256: str
    call_id: str
    request_sha256: str
    response_record_sha256: str
    external_bundle_sha256: str
    execution_profile_sha256: str
    provenance_status: str = PROVENANCE_STATUS
    usage_capture_scope: str = USAGE_CAPTURE_SCOPE
    provider_authenticated: bool = False
    operator_independence_verified: bool = False
    precall_total_ceiling_enforced: bool = False
    delivery_eligible: bool = False
    full_task_ledger_complete: bool = False
    claim_eligible: bool = False
    claim_blockers: tuple[str, ...] = CLAIM_BLOCKERS

    def __post_init__(self) -> None:
        if type(self.output_text) is not str:
            raise ManifestError("hybrid external capture output must be text")
        if type(self.resolved_model_id) is not str or not self.resolved_model_id:
            raise ManifestError("hybrid external capture model must be non-empty")
        usage = _validate_captured_usage(strict_json_loads(self._usage_json))
        if canonical_json(usage) != self._usage_json:
            raise ManifestError("hybrid external capture usage is not canonical JSON")
        total = usage.get("total_tokens")
        if type(total) is not int or total < 0:
            raise ManifestError("hybrid external capture total usage is invalid")
        if (
            type(self.host_total_token_ceiling) is not int
            or self.host_total_token_ceiling <= 0
        ):
            raise ManifestError("hybrid external capture ceiling is invalid")
        if self.observed_within_host_total_ceiling is not (
            total <= self.host_total_token_ceiling
        ):
            raise IntegrityError("hybrid external capture budget observation differs")
        for name in (
            "provider_authenticated",
            "operator_independence_verified",
            "precall_total_ceiling_enforced",
            "delivery_eligible",
            "full_task_ledger_complete",
            "claim_eligible",
        ):
            if getattr(self, name) is not False:
                raise ManifestError(f"hybrid external capture overstates {name}")
        if self.provenance_status != PROVENANCE_STATUS:
            raise ManifestError("hybrid external capture provenance differs")
        if self.usage_capture_scope != USAGE_CAPTURE_SCOPE:
            raise ManifestError("hybrid external capture usage scope differs")
        if self.claim_blockers != CLAIM_BLOCKERS:
            raise ManifestError("hybrid external capture blockers differ")
        for name in (
            "projection_sha256",
            "call_id",
            "request_sha256",
            "response_record_sha256",
            "external_bundle_sha256",
            "execution_profile_sha256",
        ):
            value = getattr(self, name)
            if type(value) is not str or _SHA256.fullmatch(value) is None:
                raise ManifestError(f"hybrid external capture {name} is invalid")

    @property
    def usage(self) -> Mapping[str, Any]:
        return _validate_captured_usage(strict_json_loads(self._usage_json))

    @property
    def value(self) -> Mapping[str, Any]:
        return {
            "format": HYBRID_CAPTURE_FORMAT,
            "output_text": self.output_text,
            "resolved_model_id": self.resolved_model_id,
            "usage": self.usage,
            "host_total_token_ceiling": self.host_total_token_ceiling,
            "observed_within_host_total_ceiling": (
                self.observed_within_host_total_ceiling
            ),
            "projection_sha256": self.projection_sha256,
            "call_id": self.call_id,
            "request_sha256": self.request_sha256,
            "response_record_sha256": self.response_record_sha256,
            "external_bundle_sha256": self.external_bundle_sha256,
            "execution_profile_sha256": self.execution_profile_sha256,
            "provenance_status": self.provenance_status,
            "usage_capture_scope": self.usage_capture_scope,
            "provider_authenticated": self.provider_authenticated,
            "operator_independence_verified": (
                self.operator_independence_verified
            ),
            "precall_total_ceiling_enforced": self.precall_total_ceiling_enforced,
            "delivery_eligible": self.delivery_eligible,
            "full_task_ledger_complete": self.full_task_ledger_complete,
            "claim_eligible": self.claim_eligible,
            "claim_blockers": list(self.claim_blockers),
        }


def expected_receiver_settings_sha256(
    *,
    model_family_code: str,
    model_id: str,
) -> str:
    """Return the runtime-style digest of the exact v1 neutral settings."""

    probe = CallRequest.build(
        episode_id="0" * 64,
        turn_index=0,
        attempt_index=0,
        purpose="runtime",
        agent="B",
        model_code=model_family_code,
        logical_model_id=model_id,
        arm=HYBRID_ARM,
        messages=[
            {"role": "system", "content": "settings probe"},
            {"role": "user", "content": "settings probe"},
        ],
        mock_scenario_key="settings-probe",
    )
    return "sha256:" + probe.settings_sha256


def _require_cold_request(request: DirectReceiverRequest) -> None:
    if type(request) is not DirectReceiverRequest:
        raise ManifestError("hybrid external replay requires an exact receiver request")
    if not request.model_call_required or request.mode != "action-state":
        raise ManifestError("hybrid external replay requires action-state model input")
    if request.delivery_disposition != "live":
        raise ManifestError("hybrid external replay accepts live disposition only")
    if request.surface_carrier is not None:
        raise ManifestError(
            "live evolving-surface requests require their sealed prepared-message path"
        )
    if request.maximum_total_tokens is None:
        raise ManifestError("hybrid external replay requires a total-token ceiling")
    if not (
        request.task_context_included
        and request.capsule_included
        and request.capsule_text is not None
        and request.task_context_id is None
        and request.capsule_context_id is None
    ):
        raise ManifestError(
            "hybrid external replay requires cold task context and Capsule bytes"
        )


def _projection_for(
    request: DirectReceiverRequest,
    receiver_binding: ReceiverModelBinding,
    execution_profile_sha256: str,
) -> dict[str, Any]:
    _require_cold_request(request)
    messages = [
        {"role": "system", "content": request.base_system_text},
        {"role": "user", "content": request.user_data_text},
    ]
    return {
        "format": HYBRID_PROJECTION_FORMAT,
        "direct_receiver_binding_sha256": request.binding_sha256,
        "runtime_transcript_sha256": sha256_text(request.model_visible_text),
        "provider_neutral_messages_sha256": sha256_bytes(
            canonical_bytes(messages)
        ),
        "mode": request.mode,
        "delivery_disposition": request.delivery_disposition,
        "maximum_total_tokens": request.maximum_total_tokens,
        "task_context_sha256": request.task_context_sha256,
        "task_profile_sha256": request.task_profile_sha256,
        "symbol_table_sha256": request.symbol_table_sha256,
        "task_context_included": request.task_context_included,
        "task_context_id": request.task_context_id,
        "task_comprehension_evidence_sha256": (
            request.task_comprehension_evidence_sha256
        ),
        "task_comprehension_verifier_sha256": (
            request.task_comprehension_verifier_sha256
        ),
        "capsule_sha256": request.capsule_sha256,
        "capsule_included": request.capsule_included,
        "capsule_context_id": request.capsule_context_id,
        "comprehension_evidence_sha256": (
            request.comprehension_evidence_sha256
        ),
        "capsule_comprehension_verifier_sha256": (
            request.capsule_comprehension_verifier_sha256
        ),
        "payload_sha256": request.payload_sha256,
        "receiver_binding_sha256": receiver_binding.sha256,
        "execution_profile_sha256": execution_profile_sha256,
    }


def build_hybrid_receiver_external_call(
    request: DirectReceiverRequest,
    receiver_binding: ReceiverModelBinding,
    *,
    episode_id: str,
    turn_index: int,
    attempt_index: int,
    agent: str,
    model_family_code: str,
    execution_profile_sha256: str,
) -> HybridReceiverExternalCall:
    """Freeze one fully cold direct request for external capture."""

    _require_cold_request(request)
    if type(receiver_binding) is not ReceiverModelBinding:
        raise ManifestError("hybrid external replay requires a receiver model binding")
    if (
        type(execution_profile_sha256) is not str
        or _SHA256.fullmatch(execution_profile_sha256) is None
    ):
        raise ManifestError("hybrid external replay profile digest is invalid")

    expected_settings = expected_receiver_settings_sha256(
        model_family_code=model_family_code,
        model_id=receiver_binding.model_id,
    )
    if receiver_binding.settings_sha256 != expected_settings:
        raise IntegrityError(
            "receiver model binding settings differ from call settings"
        )

    messages = [
        {"role": "system", "content": request.base_system_text},
        {"role": "user", "content": request.user_data_text},
    ]
    projection = _projection_for(
        request,
        receiver_binding,
        execution_profile_sha256,
    )
    projection_sha256 = sha256_bytes(canonical_bytes(projection))
    call_request = CallRequest.build(
        episode_id=episode_id,
        turn_index=turn_index,
        attempt_index=attempt_index,
        purpose="runtime",
        agent=agent,
        model_code=model_family_code,
        logical_model_id=receiver_binding.model_id,
        arm=HYBRID_ARM,
        messages=messages,
        mock_scenario_key=projection_sha256,
    )
    if "sha256:" + call_request.settings_sha256 != receiver_binding.settings_sha256:
        raise IntegrityError("hybrid external call settings binding changed")
    return HybridReceiverExternalCall(
        _projection_json=canonical_json(projection),
        projection_sha256=projection_sha256,
        _call_request_json=call_request.to_json(),
    )


def _validate_request_against_plan(
    request: DirectReceiverRequest,
    receiver_binding: ReceiverModelBinding,
    plan: HybridReceiverExternalCall,
    store: ExternalResponseStore,
) -> None:
    _require_cold_request(request)
    if type(receiver_binding) is not ReceiverModelBinding:
        raise ManifestError("hybrid external operation requires a model binding")
    if type(plan) is not HybridReceiverExternalCall:
        raise ManifestError("hybrid external operation requires an exact plan")
    if type(store) is not ExternalResponseStore:
        raise ManifestError("hybrid external operation requires an external store")
    projection = plan.projection
    call_request = plan.call_request
    observed_profile_sha256 = store.execution_profile["profile_sha256"]
    if observed_profile_sha256 != projection["execution_profile_sha256"]:
        raise IntegrityError("hybrid external execution profile differs from plan")
    expected_projection = _projection_for(
        request,
        receiver_binding,
        observed_profile_sha256,
    )
    if projection != expected_projection:
        raise IntegrityError("hybrid external projection differs from exact request")
    expected_messages = [
        {"role": "system", "content": request.base_system_text},
        {"role": "user", "content": request.user_data_text},
    ]
    if call_request.value["messages"] != expected_messages:
        raise IntegrityError("hybrid external submitted role contents differ")
    if (
        call_request.value["model_ref"]["logical_model_id"]
        != receiver_binding.model_id
    ):
        raise IntegrityError("hybrid external model differs from plan")
    if "sha256:" + call_request.settings_sha256 != receiver_binding.settings_sha256:
        raise IntegrityError("hybrid external settings differ from plan")


def build_pending_hybrid_receiver_call(
    request: DirectReceiverRequest,
    receiver_binding: ReceiverModelBinding,
    plan: HybridReceiverExternalCall,
    store: ExternalResponseStore,
) -> Mapping[str, Any]:
    """Export a pending artifact only when the exact response is absent."""

    _validate_request_against_plan(request, receiver_binding, plan, store)
    coverage = store.coverage([plan.call_request])
    if coverage["all_expected_available"]:
        raise IntegrityError("hybrid external response already exists")
    pending = store.pending_call(plan.call_request)
    return {
        "format": PENDING_HYBRID_CALL_FORMAT,
        "projection": plan.projection,
        "projection_sha256": plan.projection_sha256,
        "external_call": pending,
        "budget_boundary": {
            "host_total_token_ceiling": request.maximum_total_tokens,
            "provider_maximum_output_tokens": plan.call_request.value[
                "generation"
            ]["maximum_output_tokens"],
            "provider_input_tokens_preflighted": False,
            "precall_total_ceiling_enforced": False,
            "execution_authorized_by_this_artifact": False,
        },
        "provider_role_mapping_reverified": False,
        "delivery_eligible": False,
        "claim_eligible": False,
    }


def resolve_hybrid_receiver_external_capture(
    request: DirectReceiverRequest,
    receiver_binding: ReceiverModelBinding,
    plan: HybridReceiverExternalCall,
    store: ExternalResponseStore,
) -> HybridExternalReplayCapture:
    """Import one complete capture without turning it into runtime evidence."""

    _validate_request_against_plan(request, receiver_binding, plan, store)
    record = store.resolve(
        plan.call_request,
        require_core_usage_capture=True,
    )
    if record.status != "completed" or record.output_text is None:
        raise IntegrityError("hybrid receiver external call did not complete")
    usage = record.usage
    response = record.value["response"]
    resolved_model_id = response["provider_observation"]["resolved_model_id"]
    if resolved_model_id != receiver_binding.model_id:
        raise IntegrityError("hybrid receiver resolved model differs")
    if usage["status"] != "complete":
        raise IntegrityError("hybrid receiver usage is incomplete")
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    total_tokens = usage["total_tokens"]
    if not all(
        type(value) is int
        for value in (input_tokens, output_tokens, total_tokens)
    ):
        raise IntegrityError("hybrid receiver token usage contains an unknown")

    record_value = record.value
    bundle_value = store.value
    return HybridExternalReplayCapture(
        output_text=record.output_text,
        resolved_model_id=resolved_model_id,
        _usage_json=canonical_json(usage),
        host_total_token_ceiling=request.maximum_total_tokens,
        observed_within_host_total_ceiling=(
            total_tokens <= request.maximum_total_tokens
        ),
        projection_sha256=plan.projection_sha256,
        call_id=plan.call_request.call_id,
        request_sha256=plan.call_request.request_sha256,
        response_record_sha256=record_value["record_sha256"],
        external_bundle_sha256=bundle_value["bundle_sha256"],
        execution_profile_sha256=bundle_value["execution_profile"][
            "profile_sha256"
        ],
    )
