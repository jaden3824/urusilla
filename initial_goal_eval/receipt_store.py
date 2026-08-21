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
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
)


RECEIPT_BUNDLE_SCHEMA = "urusilla-initial-goal-receipt-bundle/1"
RECEIPT_SCHEMA = "urusilla-initial-goal-receipt/1"
RECEIPT_KINDS = (
    "usage",
    "scorer",
    "sandbox-enforcement",
    "operator-attestation",
    "independent-audit",
)


@dataclass(frozen=True)
class ReceiptValidation:
    complete: bool
    referenced: int
    resolved: int
    unreferenced: int
    errors: tuple[str, ...]

    def to_object(self) -> dict[str, Any]:
        return {
            "required": True,
            "content_consistent": self.complete,
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
        if bundle["schema_version"] != RECEIPT_BUNDLE_SCHEMA:
            raise VerificationError("receipt bundle schema differs")
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
            if receipt["schema_version"] != RECEIPT_SCHEMA:
                raise VerificationError(f"{path}.schema_version differs")
            if receipt["kind"] not in RECEIPT_KINDS:
                raise VerificationError(f"{path}.kind is invalid")
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
        expected_usage: Mapping[str, Any],
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
        provider_call_identities: set[tuple[str, str]] = set()
        referenced = 0

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
                    if source is not None and self._validate_usage_source(
                            source,
                            expected_usage=event["usage"],
                            phase=event["phase"],
                            receiver_model_id=model["model_id"],
                            receiver_settings_sha256=model["settings_sha256"],
                            provider_call_identities=provider_call_identities,
                            label=digest,
                            errors=errors,
                    ):
                        valid.add(digest)

                for task_result in _list(arm["task_results"], "arm.task_results"):
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
                    binding = {
                        "study_id": plan["study_id"],
                        "plan_sha256": plan_sha256,
                        "session_id": session["session_id"],
                        "arm_id": arm_id,
                        "execution_manifest_sha256": manifest_sha256,
                        "task": task,
                        "scorer_locks": scorer_locks,
                        "observed": observed,
                    }
                    source = self._resolve(
                        digest,
                        kind="scorer",
                        issuer_id=operator_id,
                        binding=binding,
                        found=found,
                        errors=errors,
                    )
                    if source is not None and self._validate_generic_source(
                            source,
                            kind="scorer",
                            expected_artifact_sha256=plan["artifact_locks"][
                                "task_scorer"
                            ],
                            expected_observation=observed,
                            label=digest,
                            errors=errors,
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
        return ReceiptValidation(
            complete=not errors and len(valid) == referenced == len(self._receipts),
            referenced=referenced,
            resolved=len(valid),
            unreferenced=unreferenced,
            errors=tuple(errors),
        )


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the exact reference a result must use for one receipt payload."""

    return sha256_ref(dict(receipt))
