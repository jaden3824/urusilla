"""Canonical receipt sidecars for real initial-goal evaluation evidence.

The statistical verifier must not trust a result merely because it contains
strings shaped like SHA-256 references. A real study supplies this separate
bundle. Every referenced receipt is content-addressed, carries the payload it
claims to summarize, and is bound back to one frozen plan/session/arm/event or
task. This module performs no provider call and proves no social independence;
it only closes the machine-verifiable provenance boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .contract import (
    ARMS,
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
from .terminal_contract import (
    CANONICAL_SILENCE_OUTPUT_SHA256,
    CAPTURE_TERMINAL_STATUSES,
    SILENCE_TERMINAL_STATUS,
)


RECEIPT_BUNDLE_SCHEMA = "urusilla-initial-goal-receipt-bundle/1"
RECEIPT_BUNDLE_SCHEMA_V2 = "urusilla-initial-goal-receipt-bundle/2"
RECEIPT_SCHEMA = "urusilla-initial-goal-receipt/1"
USAGE_RECEIPT_SCHEMA_V2 = "urusilla-initial-goal-usage-receipt/2"
SCORER_OUTPUT_RECEIPT_SCHEMA = (
    "urusilla-initial-goal-scorer-output-receipt/2"
)
RECEIPT_KINDS = (
    "usage",
    "scorer",
    "sandbox-enforcement",
    "operator-attestation",
    "independent-audit",
)


@dataclass(frozen=True, init=False)
class ReceiptValidation:
    complete: bool
    content_consistent: bool
    scorer_output_binding_complete: bool
    referenced: int
    resolved: int
    unreferenced: int
    errors: tuple[str, ...]

    def __init__(
        self,
        complete: bool | None = None,
        referenced: int = 0,
        resolved: int = 0,
        unreferenced: int = 0,
        errors: tuple[str, ...] = (),
        *,
        content_consistent: bool | None = None,
        scorer_output_binding_complete: bool | None = None,
    ) -> None:
        """Build new split-gate results or accept the legacy ``complete=`` API.

        Legacy callers supplied only ``complete`` plus counters. That value is
        interpreted as both split gates so positional/keyword construction and
        ``dataclasses.asdict`` remain compatible. New callers omit ``complete``
        and must provide both split gates explicitly.
        """

        legacy = (
            content_consistent is None
            and scorer_output_binding_complete is None
        )
        if legacy:
            if type(complete) is not bool:
                raise TypeError("legacy ReceiptValidation requires boolean complete")
            content_consistent = complete
            scorer_output_binding_complete = complete
        elif (
            type(content_consistent) is not bool
            or type(scorer_output_binding_complete) is not bool
        ):
            raise TypeError("both ReceiptValidation split gates must be boolean")
        if complete is not None and type(complete) is not bool:
            raise TypeError("ReceiptValidation.complete must be boolean or null")
        computed = content_consistent and scorer_output_binding_complete
        if complete is not None and complete is not computed:
            raise ValueError("complete disagrees with the split receipt gates")
        object.__setattr__(self, "complete", computed)
        object.__setattr__(self, "content_consistent", content_consistent)
        object.__setattr__(
            self,
            "scorer_output_binding_complete",
            scorer_output_binding_complete,
        )
        object.__setattr__(self, "referenced", referenced)
        object.__setattr__(self, "resolved", resolved)
        object.__setattr__(self, "unreferenced", unreferenced)
        object.__setattr__(self, "errors", errors)

    def to_object(self) -> dict[str, Any]:
        return {
            "required": True,
            "content_consistent": self.content_consistent,
            "scorer_output_binding_complete": (
                self.scorer_output_binding_complete
            ),
            "complete": self.complete,
            "referenced": self.referenced,
            "resolved": self.resolved,
            "unreferenced": self.unreferenced,
            "errors": list(self.errors),
        }


class ReceiptStore:
    """Strict, in-memory lookup of content-addressed receipt payloads."""

    def __init__(self, value: Any):
        bundle = _object(value, "receipt_bundle")
        _exact(
            bundle,
            {"schema_version", "plan_sha256", "receipts"},
            "receipt_bundle",
        )
        if bundle["schema_version"] not in {
            RECEIPT_BUNDLE_SCHEMA,
            RECEIPT_BUNDLE_SCHEMA_V2,
        }:
            raise VerificationError("receipt bundle schema differs")
        self.schema_version = bundle["schema_version"]
        self.plan_sha256 = _sha(
            bundle["plan_sha256"], "receipt_bundle.plan_sha256"
        )
        self._receipts: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(_list(bundle["receipts"], "receipt_bundle.receipts")):
            path = f"receipt_bundle.receipts[{index}]"
            receipt = _object(raw, path)
            _exact(
                receipt,
                {
                    "schema_version",
                    "kind",
                    "issuer_id",
                    "binding",
                    "source_payload",
                    "source_sha256",
                },
                path,
            )
            if receipt["kind"] not in RECEIPT_KINDS:
                raise VerificationError(f"{path}.kind is invalid")
            expected_schema = (
                (
                    SCORER_OUTPUT_RECEIPT_SCHEMA
                    if receipt["kind"] == "scorer"
                    else USAGE_RECEIPT_SCHEMA_V2
                    if receipt["kind"] == "usage"
                    else RECEIPT_SCHEMA
                )
                if self.schema_version == RECEIPT_BUNDLE_SCHEMA_V2
                else RECEIPT_SCHEMA
            )
            if receipt["schema_version"] != expected_schema:
                raise VerificationError(f"{path}.schema_version differs")
            _identifier(receipt["issuer_id"], f"{path}.issuer_id")
            _object(receipt["binding"], f"{path}.binding")
            source = _object(receipt["source_payload"], f"{path}.source_payload")
            if receipt["source_sha256"] != sha256_ref(source):
                raise VerificationError(f"{path}.source payload digest mismatch")
            digest = sha256_ref(receipt)
            if digest in self._receipts:
                raise VerificationError("receipt bundle contains duplicate receipt payloads")
            # Detach from caller-owned mutable objects and normalize to pure JSON.
            self._receipts[digest] = json.loads(canonical_json(receipt))

    @classmethod
    def from_object(cls, value: Any) -> "ReceiptStore":
        return cls(value)

    @property
    def receipt_count(self) -> int:
        return len(self._receipts)

    def _resolve(
        self,
        digest: str,
        *,
        kind: str,
        issuer_id: str,
        binding: Mapping[str, Any],
        found: set[str],
        errors: list[str],
    ) -> Mapping[str, Any] | None:
        if digest in found:
            errors.append(f"replayed-receipt:{digest}")
            return None
        receipt = self._receipts.get(digest)
        if receipt is None:
            errors.append(f"missing-receipt:{digest}")
            return None
        found.add(digest)
        if sha256_ref(receipt) != digest:
            errors.append(f"receipt-content-digest-mismatch:{digest}")
            return None
        valid = True
        if receipt["kind"] != kind:
            errors.append(f"receipt-kind-mismatch:{digest}")
            valid = False
        if receipt["issuer_id"] != issuer_id:
            errors.append(f"receipt-issuer-mismatch:{digest}")
            valid = False
        if receipt["binding"] != dict(binding):
            errors.append(f"receipt-binding-mismatch:{digest}")
            valid = False
        if not valid:
            return None
        return receipt["source_payload"]

    @staticmethod
    def _validate_usage_source(
        source: Mapping[str, Any],
        *,
        require_provider_response_sha256: bool,
        expected_usage: Mapping[str, Any],
        expected_output_sha256: str | None,
        phase: str,
        receiver_model_id: str,
        receiver_settings_sha256: str,
        provider_call_identities: set[tuple[str, str]],
        label: str,
        errors: list[str],
    ) -> bool:
        error_count = len(errors)
        expected_fields = {
            "source_kind",
            "request_id",
            "response_id",
            "model_id",
            "settings_sha256",
            "reported_usage",
            "raw_receipt_sha256",
        }
        if require_provider_response_sha256:
            expected_fields.update(
                {"provider_response_sha256", "provider_terminal_status"}
            )
        if set(source) != expected_fields:
            errors.append(f"usage-source-fields-mismatch:{label}")
            return False
        if source["reported_usage"] != dict(expected_usage):
            errors.append(f"usage-source-accounting-mismatch:{label}")
        raw_receipt_valid = True
        try:
            _sha(source["raw_receipt_sha256"], f"{label}.raw_receipt_sha256")
        except VerificationError:
            raw_receipt_valid = False
            errors.append(f"usage-source-raw-digest-invalid:{label}")
        source_kind = source["source_kind"]
        if source_kind == "provider":
            provider_identity_valid = raw_receipt_valid
            provider_response_valid = True
            if require_provider_response_sha256:
                try:
                    _sha(
                        source["provider_response_sha256"],
                        f"{label}.provider_response_sha256",
                    )
                except VerificationError:
                    provider_response_valid = False
                    provider_identity_valid = False
                    errors.append(
                        f"usage-source-provider-response-digest-invalid:{label}"
                    )
                terminal_status = source["provider_terminal_status"]
                if terminal_status not in CAPTURE_TERMINAL_STATUSES:
                    errors.append(
                        f"usage-source-provider-terminal-status-invalid:{label}"
                    )
                elif (
                    phase in {"receiver", "fallback"}
                    and terminal_status == "completed"
                    and expected_output_sha256 is None
                ):
                    errors.append(
                        f"usage-source-completed-output-required:{label}"
                    )
            for field in ("request_id", "response_id", "model_id"):
                value = source[field]
                if type(value) is not str or not value:
                    errors.append(f"usage-source-{field}-invalid:{label}")
                    if field in {"request_id", "response_id"}:
                        provider_identity_valid = False
            try:
                _sha(source["settings_sha256"], f"{label}.settings_sha256")
            except VerificationError:
                errors.append(f"usage-source-settings-invalid:{label}")
            if phase in {"receiver", "fallback"} and (
                source["model_id"] != receiver_model_id
                or source["settings_sha256"] != receiver_settings_sha256
            ):
                errors.append(f"usage-source-receiver-model-mismatch:{label}")
            if provider_identity_valid:
                identity_parts = {
                    ("request", source["request_id"]),
                    ("response", source["response_id"]),
                    ("raw-receipt", source["raw_receipt_sha256"]),
                }
                if require_provider_response_sha256 and provider_response_valid:
                    identity_parts.add(
                        (
                            "provider-response-sha256",
                            source["provider_response_sha256"],
                        )
                    )
                if identity_parts & provider_call_identities:
                    errors.append(f"usage-source-provider-call-replayed:{label}")
                else:
                    provider_call_identities.update(identity_parts)
        elif source_kind == "deterministic-local":
            if phase in {"receiver", "fallback"}:
                errors.append(f"usage-source-model-call-required:{label}")
            if any(
                source[field] is not None
                for field in (
                    "request_id",
                    "response_id",
                    "model_id",
                    "settings_sha256",
                )
            ):
                errors.append(f"usage-source-local-provider-fields-present:{label}")
            if (
                require_provider_response_sha256
                and source["provider_response_sha256"] is not None
            ):
                errors.append(
                    f"usage-source-local-provider-response-present:{label}"
                )
            if (
                require_provider_response_sha256
                and source["provider_terminal_status"] is not None
            ):
                errors.append(
                    f"usage-source-local-provider-terminal-status-present:{label}"
                )
        else:
            errors.append(f"usage-source-kind-invalid:{label}")
        return len(errors) == error_count

    @staticmethod
    def _validate_generic_source(
        source: Mapping[str, Any],
        *,
        kind: str,
        expected_artifact_sha256: str,
        expected_observation: Mapping[str, Any],
        label: str,
        errors: list[str],
    ) -> bool:
        error_count = len(errors)
        if set(source) != {"artifact_sha256", "observation"}:
            errors.append(f"{kind}-source-fields-mismatch:{label}")
            return False
        try:
            _sha(source["artifact_sha256"], f"{label}.artifact_sha256")
        except VerificationError:
            errors.append(f"{kind}-source-artifact-digest-invalid:{label}")
        if source["artifact_sha256"] != expected_artifact_sha256:
            errors.append(f"{kind}-source-artifact-mismatch:{label}")
        if source["observation"] != dict(expected_observation):
            errors.append(f"{kind}-source-observation-mismatch:{label}")
        return len(errors) == error_count

    @staticmethod
    def _validate_scorer_output_source(
        source: Mapping[str, Any],
        *,
        expected_artifact_sha256: str,
        expected_observation: Mapping[str, Any],
        expected_terminal_event: Mapping[str, Any],
        provider_usage_receipts: set[str],
        label: str,
        errors: list[str],
    ) -> bool:
        """Validate a v2 score against one explicit terminal-output boundary.

        Completed provider output is embedded as UTF-8 text. A noncompleted
        provider call may instead bind an explicit null output, and a silence
        route binds the canonical no-output target without inventing a provider
        call or usage receipt. Provider artifacts remain unresolved and
        unauthenticated at this content-consistency layer.
        """

        error_count = len(errors)
        expected_fields = {
            "artifact_sha256",
            "observation",
            "terminal_event",
            "provider_output",
        }
        if set(source) != expected_fields:
            errors.append(f"scorer-v2-source-fields-mismatch:{label}")
            return False
        try:
            _sha(source["artifact_sha256"], f"{label}.artifact_sha256")
        except VerificationError:
            errors.append(f"scorer-v2-source-artifact-digest-invalid:{label}")
        if source["artifact_sha256"] != expected_artifact_sha256:
            errors.append(f"scorer-v2-source-artifact-mismatch:{label}")
        if source["observation"] != dict(expected_observation):
            errors.append(f"scorer-v2-source-observation-mismatch:{label}")

        try:
            terminal = _object(source["terminal_event"], f"{label}.terminal_event")
            _exact(
                terminal,
                {
                    "terminal_kind",
                    "event_sequence",
                    "phase",
                    "task_id",
                    "input_sha256",
                    "output_sha256",
                    "usage_receipt_sha256",
                    "usage",
                    "provider_response_sha256",
                    "terminal_status",
                },
                f"{label}.terminal_event",
            )
        except VerificationError:
            errors.append(f"scorer-v2-terminal-shape-invalid:{label}")
            terminal = None
        if terminal is not None:
            if terminal != dict(expected_terminal_event):
                errors.append(f"scorer-v2-terminal-event-mismatch:{label}")
            terminal_kind = terminal["terminal_kind"]
            if terminal_kind == "provider-response":
                try:
                    _count(
                        terminal["event_sequence"],
                        f"{label}.terminal_event.event_sequence",
                    )
                except VerificationError:
                    errors.append(f"scorer-v2-terminal-sequence-invalid:{label}")
                for field in (
                    "input_sha256",
                    "usage_receipt_sha256",
                    "provider_response_sha256",
                ):
                    try:
                        _sha(terminal[field], f"{label}.terminal_event.{field}")
                    except VerificationError:
                        errors.append(f"scorer-v2-terminal-{field}-invalid:{label}")
                if terminal["output_sha256"] is not None:
                    try:
                        _sha(
                            terminal["output_sha256"],
                            f"{label}.terminal_event.output_sha256",
                        )
                    except VerificationError:
                        errors.append(
                            f"scorer-v2-terminal-output_sha256-invalid:{label}"
                        )
                if terminal["phase"] not in {"receiver", "fallback"}:
                    errors.append(
                        f"scorer-v2-terminal-provider-phase-required:{label}"
                    )
                if terminal["terminal_status"] not in CAPTURE_TERMINAL_STATUSES:
                    errors.append(f"scorer-v2-terminal-status-invalid:{label}")
                if terminal["usage_receipt_sha256"] not in provider_usage_receipts:
                    errors.append(
                        f"scorer-v2-provider-usage-receipt-required:{label}"
                    )
                if (
                    terminal["terminal_status"] == "completed"
                    and terminal["output_sha256"] is None
                ):
                    errors.append(f"scorer-v2-completed-output-required:{label}")
                if (
                    terminal["terminal_status"] != "completed"
                    and expected_observation.get("task_success") is True
                ):
                    errors.append(f"scorer-v2-noncompleted-success:{label}")
            elif terminal_kind == "canonical-silence":
                expected_silence = {
                    "terminal_kind": "canonical-silence",
                    "event_sequence": None,
                    "phase": "silence",
                    "task_id": expected_terminal_event["task_id"],
                    "input_sha256": None,
                    "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                    "usage_receipt_sha256": None,
                    "usage": None,
                    "provider_response_sha256": None,
                    "terminal_status": SILENCE_TERMINAL_STATUS,
                }
                if terminal != expected_silence:
                    errors.append(f"scorer-v2-canonical-silence-mismatch:{label}")
            else:
                errors.append(f"scorer-v2-terminal-kind-invalid:{label}")

        try:
            provider_output = _object(
                source["provider_output"], f"{label}.provider_output"
            )
            _exact(
                provider_output,
                {
                    "kind",
                    "encoding",
                    "text",
                    "output_sha256",
                    "provider_response_sha256",
                },
                f"{label}.provider_output",
            )
        except VerificationError:
            errors.append(f"scorer-v2-provider-output-shape-invalid:{label}")
            provider_output = None
        if provider_output is not None:
            output_kind = provider_output["kind"]
            if output_kind == "provider-text":
                if provider_output["encoding"] != "utf-8":
                    errors.append(
                        f"scorer-v2-provider-output-encoding-invalid:{label}"
                    )
                output_text = provider_output["text"]
                if type(output_text) is not str:
                    errors.append(f"scorer-v2-provider-output-text-invalid:{label}")
                else:
                    try:
                        output_text.encode("utf-8")
                    except UnicodeEncodeError:
                        errors.append(
                            f"scorer-v2-provider-output-text-invalid:{label}"
                        )
                    else:
                        expected_output_sha256 = sha256_ref(
                            {"provider_output_text": output_text}
                        )
                        if (
                            provider_output["output_sha256"]
                            != expected_output_sha256
                        ):
                            errors.append(
                                f"scorer-v2-provider-output-digest-mismatch:{label}"
                            )
                for field in ("output_sha256", "provider_response_sha256"):
                    try:
                        _sha(
                            provider_output[field],
                            f"{label}.provider_output.{field}",
                        )
                    except VerificationError:
                        errors.append(
                            f"scorer-v2-provider-output-{field}-invalid:{label}"
                        )
            elif output_kind == "provider-no-output":
                if (
                    provider_output["encoding"] is not None
                    or provider_output["text"] is not None
                    or provider_output["output_sha256"] is not None
                ):
                    errors.append(
                        f"scorer-v2-provider-no-output-fields-present:{label}"
                    )
                try:
                    _sha(
                        provider_output["provider_response_sha256"],
                        f"{label}.provider_output.provider_response_sha256",
                    )
                except VerificationError:
                    errors.append(
                        "scorer-v2-provider-output-"
                        f"provider_response_sha256-invalid:{label}"
                    )
                if (
                    terminal is not None
                    and terminal.get("terminal_status") == "completed"
                ):
                    errors.append(f"scorer-v2-completed-output-required:{label}")
            elif output_kind == "canonical-silence":
                if provider_output != {
                    "kind": "canonical-silence",
                    "encoding": None,
                    "text": None,
                    "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                    "provider_response_sha256": None,
                }:
                    errors.append(
                        f"scorer-v2-canonical-silence-output-mismatch:{label}"
                    )
                if terminal is not None and terminal.get("terminal_kind") != (
                    "canonical-silence"
                ):
                    errors.append(f"scorer-v2-output-kind-terminal-mismatch:{label}")
            else:
                errors.append(f"scorer-v2-provider-output-kind-invalid:{label}")
            if terminal is not None and (
                provider_output["output_sha256"] != terminal["output_sha256"]
                or provider_output["provider_response_sha256"]
                != terminal["provider_response_sha256"]
            ):
                errors.append(f"scorer-v2-provider-output-terminal-mismatch:{label}")
        return len(errors) == error_count

    @staticmethod
    def _terminal_event_for_score(
        arm: Mapping[str, Any],
        task_result: Mapping[str, Any],
        *,
        label: str,
        errors: list[str],
    ) -> Mapping[str, Any] | None:
        all_events = [
            event for event in arm["events"] if type(event) is dict
        ]
        task_id = task_result.get("task_id")
        events = [
            event
            for event in all_events
            if event.get("task_id") == task_id
            and event.get("phase") in {"receiver", "fallback"}
        ]
        if arm["arm_id"] == "hybrid-router":
            route = task_result.get("route")
            if type(route) is not dict:
                errors.append(f"scorer-v2-terminal-route-required:{label}")
                return None
            decision_sequence = route.get("decision_event_sequence")
            if type(decision_sequence) is not int or decision_sequence < 0:
                errors.append(f"scorer-v2-route-decision-sequence-invalid:{label}")
                return None
            decision_events = [
                event
                for event in all_events
                if event.get("sequence") == decision_sequence
                and event.get("phase") == "router"
                and event.get("task_id") == task_id
            ]
            if len(decision_events) != 1:
                errors.append(f"scorer-v2-route-decision-task-mismatch:{label}")
                return None
            decision_event = decision_events[0]
            if route.get("selected_mode") == "silence":
                if route.get("receiver_event_sequence") is not None or events:
                    errors.append(f"scorer-v2-silence-provider-event-present:{label}")
                    return None
                return {
                    "terminal_kind": "canonical-silence",
                    "event_sequence": None,
                    "phase": "silence",
                    "task_id": task_result.get("task_id"),
                    "input_sha256": None,
                    "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                    "usage_receipt_sha256": None,
                    "usage": None,
                    "provider_response_sha256": None,
                    "terminal_status": SILENCE_TERMINAL_STATUS,
                }
            sequence = route.get("receiver_event_sequence")
            events = [event for event in events if event.get("sequence") == sequence]
        if len(events) != 1:
            errors.append(f"scorer-v2-terminal-event-not-unique:{label}")
            return None
        if arm["arm_id"] == "hybrid-router":
            fallback_from = task_result["route"].get("fallback_from")
            expected_phase = "fallback" if fallback_from is not None else "receiver"
            if events[0].get("phase") != expected_phase:
                errors.append(f"scorer-v2-fallback-task-binding-mismatch:{label}")
                return None
            terminal_sequence = events[0].get("sequence")
            if type(terminal_sequence) is not int or terminal_sequence < 0:
                errors.append(f"scorer-v2-terminal-sequence-invalid:{label}")
                return None
            if decision_sequence >= terminal_sequence:
                errors.append(f"scorer-v2-route-chronology-invalid:{label}")
                return None
        return events[0]

    def validate(self, plan_value: Any, result_value: Any) -> ReceiptValidation:
        plan = _object(plan_value, "plan")
        result = _object(result_value, "result")
        plan_sha256 = sha256_ref(plan)
        errors: list[str] = []
        if self.plan_sha256 != plan_sha256:
            errors.append("receipt-bundle-plan-mismatch")

        model_by_family = {
            item["family"]: item for item in _list(plan["receiver_models"], "plan.receiver_models")
        }
        planned_sessions = {
            item["session_id"]: item for item in _list(plan["sessions"], "plan.sessions")
        }
        operator_by_id = {
            item["operator_id"]: item
            for item in _list(plan["operators"], "plan.operators")
        }
        found: set[str] = set()
        valid: set[str] = set()
        provider_terminal_by_usage_receipt: dict[str, tuple[str, str]] = {}
        provider_call_identities: set[tuple[str, str]] = set()
        referenced = 0
        scorer_targets = 0
        scorer_v2_valid = 0

        for record_index, record_raw in enumerate(
            _list(result["records"], "result.records")
        ):
            record = _object(record_raw, f"result.records[{record_index}]")
            session = planned_sessions.get(record.get("session_id"))
            if session is None:
                continue
            operator_id = session["operator_id"]
            auditor_id = session["boundary_auditor_id"]
            model = model_by_family[session["receiver_family"]]
            planned_tasks = {item["task_id"]: item for item in session["tasks"]}
            arm_by_id = {
                item.get("arm_id"): item
                for item in _list(record["arms"], f"result.records[{record_index}].arms")
                if type(item) is dict
            }
            for arm_id in ARMS:
                arm = arm_by_id.get(arm_id)
                if arm is None:
                    continue
                manifest_sha256 = session["arm_execution_manifest_sha256"][arm_id]
                for event in _list(arm["events"], "arm.events"):
                    digest = event.get("usage_receipt_sha256")
                    if digest is None:
                        continue
                    referenced += 1
                    binding = {
                        "study_id": plan["study_id"],
                        "plan_sha256": plan_sha256,
                        "session_id": session["session_id"],
                        "arm_id": arm_id,
                        "execution_manifest_sha256": manifest_sha256,
                        "receiver_family": session["receiver_family"],
                        "event_sequence": event["sequence"],
                        "phase": event["phase"],
                        "task_id": event["task_id"],
                        "input_sha256": event["input_sha256"],
                        "output_sha256": event["output_sha256"],
                        "usage": event["usage"],
                    }
                    source = self._resolve(
                        digest,
                        kind="usage",
                        issuer_id=operator_id,
                        binding=binding,
                        found=found,
                        errors=errors,
                    )
                    receipt = self._receipts.get(digest)
                    usage_v2 = (
                        receipt is not None
                        and receipt["schema_version"] == USAGE_RECEIPT_SCHEMA_V2
                    )
                    if source is not None and self._validate_usage_source(
                            source,
                            require_provider_response_sha256=usage_v2,
                            expected_usage=event["usage"],
                            expected_output_sha256=event["output_sha256"],
                            phase=event["phase"],
                            receiver_model_id=model["model_id"],
                            receiver_settings_sha256=model["settings_sha256"],
                            provider_call_identities=provider_call_identities,
                            label=digest,
                            errors=errors,
                    ):
                        valid.add(digest)
                        if source["source_kind"] == "provider" and usage_v2:
                            provider_terminal_by_usage_receipt[digest] = (
                                source["provider_response_sha256"],
                                source["provider_terminal_status"],
                            )

                for task_result in _list(arm["task_results"], "arm.task_results"):
                    scorer_targets += 1
                    digest = task_result.get("scorer_receipt_sha256")
                    if digest is None:
                        continue
                    referenced += 1
                    task = planned_tasks.get(task_result.get("task_id"))
                    if task is None:
                        continue
                    observed = dict(task_result)
                    observed.pop("scorer_receipt_sha256", None)
                    scorer_locks = {
                        name: plan["artifact_locks"][name]
                        for name in (
                            "task_scorer",
                            "parse_scorer",
                            "semantic_scorer",
                            "negative_scorer",
                        )
                    }
                    binding: dict[str, Any] = {
                        "study_id": plan["study_id"],
                        "plan_sha256": plan_sha256,
                        "session_id": session["session_id"],
                        "arm_id": arm_id,
                        "execution_manifest_sha256": manifest_sha256,
                        "task": task,
                        "scorer_locks": scorer_locks,
                        "observed": observed,
                    }
                    receipt = self._receipts.get(digest)
                    scorer_v2 = (
                        receipt is not None
                        and receipt["schema_version"]
                        == SCORER_OUTPUT_RECEIPT_SCHEMA
                    )
                    expected_terminal: Mapping[str, Any] | None = None
                    if scorer_v2:
                        terminal = self._terminal_event_for_score(
                            arm,
                            task_result,
                            label=digest,
                            errors=errors,
                        )
                        if terminal is not None:
                            if terminal.get("terminal_kind") == "canonical-silence":
                                expected_terminal = dict(terminal)
                            else:
                                provider_terminal = (
                                    provider_terminal_by_usage_receipt.get(
                                        terminal["usage_receipt_sha256"]
                                    )
                                )
                                if provider_terminal is None:
                                    errors.append(
                                        "scorer-v2-provider-response-source-required:"
                                        f"{digest}"
                                    )
                                    provider_response_sha256 = None
                                    terminal_status = None
                                else:
                                    (
                                        provider_response_sha256,
                                        terminal_status,
                                    ) = provider_terminal
                                expected_terminal = {
                                    "terminal_kind": "provider-response",
                                    "event_sequence": terminal["sequence"],
                                    "phase": terminal["phase"],
                                    "task_id": terminal["task_id"],
                                    "input_sha256": terminal["input_sha256"],
                                    "output_sha256": terminal["output_sha256"],
                                    "usage_receipt_sha256": terminal[
                                        "usage_receipt_sha256"
                                    ],
                                    "usage": terminal["usage"],
                                    "provider_response_sha256": (
                                        provider_response_sha256
                                    ),
                                    "terminal_status": terminal_status,
                                }
                            binding["terminal_event"] = expected_terminal
                    source = self._resolve(
                        digest,
                        kind="scorer",
                        issuer_id=operator_id,
                        binding=binding,
                        found=found,
                        errors=errors,
                    )
                    if (
                        scorer_v2
                        and source is not None
                        and expected_terminal is not None
                        and self._validate_scorer_output_source(
                            source,
                            expected_artifact_sha256=plan["artifact_locks"][
                                "task_scorer"
                            ],
                            expected_observation=observed,
                            expected_terminal_event=expected_terminal,
                            provider_usage_receipts=set(
                                provider_terminal_by_usage_receipt
                            ),
                            label=digest,
                            errors=errors,
                        )
                    ):
                        valid.add(digest)
                        scorer_v2_valid += 1
                    elif (
                        not scorer_v2
                        and source is not None
                        and self._validate_generic_source(
                            source,
                            kind="scorer",
                            expected_artifact_sha256=plan["artifact_locks"][
                                "task_scorer"
                            ],
                            expected_observation=observed,
                            label=digest,
                            errors=errors,
                        )
                    ):
                        valid.add(digest)

                for entry in _list(arm["sandbox_evidence"], "arm.sandbox_evidence"):
                    role = entry["role"]
                    common = {
                        "study_id": plan["study_id"],
                        "plan_sha256": plan_sha256,
                        "session_id": session["session_id"],
                        "arm_id": arm_id,
                        "role": role,
                        "execution_operator_id": operator_id,
                        "boundary_auditor_id": auditor_id,
                        "policy_sha256": entry["policy_sha256"],
                        "enforcement_profile_sha256": entry[
                            "enforcement_profile_sha256"
                        ],
                        "denied_capability_observations": entry[
                            "denied_capability_observations"
                        ],
                    }
                    receipt_specs = (
                        (
                            "enforcement_receipt_sha256",
                            "sandbox-enforcement",
                            operator_id,
                            {**common, "status": entry["enforcement_status"]},
                            {
                                "status": entry["enforcement_status"],
                                "denied_capability_observations": entry[
                                    "denied_capability_observations"
                                ],
                            },
                            entry["enforcement_profile_sha256"],
                        ),
                        (
                            "operator_attestation_sha256",
                            "operator-attestation",
                            operator_id,
                            {**common, "session_attestation": record["attestation"]},
                            {"session_attestation": record["attestation"]},
                            operator_by_id[operator_id]["attestation_sha256"],
                        ),
                        (
                            "independent_audit_receipt_sha256",
                            "independent-audit",
                            auditor_id,
                            {
                                **common,
                                "independent_audit_protocol_sha256": entry[
                                    "independent_audit_protocol_sha256"
                                ],
                                "status": entry["independent_audit_status"],
                            },
                            {
                                "status": entry["independent_audit_status"],
                                "denied_capability_observations": entry[
                                    "denied_capability_observations"
                                ],
                            },
                            entry["independent_audit_protocol_sha256"],
                        ),
                    )
                    for (
                        field,
                        kind,
                        issuer,
                        binding,
                        observation,
                        expected_artifact,
                    ) in receipt_specs:
                        digest = entry.get(field)
                        if digest is None:
                            continue
                        referenced += 1
                        source = self._resolve(
                            digest,
                            kind=kind,
                            issuer_id=issuer,
                            binding=binding,
                            found=found,
                            errors=errors,
                        )
                        if source is not None and self._validate_generic_source(
                                source,
                                kind=kind,
                                expected_artifact_sha256=expected_artifact,
                                expected_observation=observation,
                                label=digest,
                                errors=errors,
                        ):
                            valid.add(digest)

        unreferenced = len(set(self._receipts) - found)
        if unreferenced:
            errors.append(f"unreferenced-receipts:{unreferenced}")
        content_consistent = (
            not errors and len(valid) == referenced == len(self._receipts)
        )
        scorer_output_binding_complete = (
            self.schema_version == RECEIPT_BUNDLE_SCHEMA_V2
            and scorer_targets > 0
            and scorer_v2_valid == scorer_targets
        )
        return ReceiptValidation(
            content_consistent=content_consistent,
            scorer_output_binding_complete=scorer_output_binding_complete,
            referenced=referenced,
            resolved=len(valid),
            unreferenced=unreferenced,
            errors=tuple(errors),
        )


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the exact reference a result must use for one receipt payload."""

    return sha256_ref(dict(receipt))
