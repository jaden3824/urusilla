"""Receipt provenance tests; all fixtures remain synthetic test data."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import unittest

from initial_goal_eval.contract import ARMS, VerificationError, sha256_ref
from initial_goal_eval.execution_trace import CANONICAL_SILENCE_OUTPUT_SHA256
from initial_goal_eval.receipt_store import (
    RECEIPT_BUNDLE_SCHEMA,
    RECEIPT_BUNDLE_SCHEMA_V2,
    RECEIPT_SCHEMA,
    SCORER_OUTPUT_RECEIPT_SCHEMA,
    USAGE_RECEIPT_SCHEMA_V2,
    ReceiptStore,
    ReceiptValidation,
)
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture
from initial_goal_eval.verifier import verify_result


def _receipt(
    *,
    kind: str,
    issuer_id: str,
    binding: dict[str, object],
    source_payload: dict[str, object],
    schema_version: str = RECEIPT_SCHEMA,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "kind": kind,
        "issuer_id": issuer_id,
        "binding": binding,
        "source_payload": source_payload,
        "source_sha256": sha256_ref(source_payload),
    }


class ReceiptValidationCompatibilityTests(unittest.TestCase):
    def test_legacy_complete_constructor_and_asdict_remain_compatible(self) -> None:
        validation = ReceiptValidation(
            complete=True,
            referenced=1,
            resolved=1,
            unreferenced=0,
            errors=(),
        )

        self.assertTrue(validation.content_consistent)
        self.assertTrue(validation.scorer_output_binding_complete)
        self.assertTrue(asdict(validation)["complete"])

    def test_explicit_complete_cannot_disagree_with_split_gates(self) -> None:
        with self.assertRaisesRegex(ValueError, "disagrees"):
            ReceiptValidation(
                complete=True,
                content_consistent=True,
                scorer_output_binding_complete=False,
            )


def _build_v2_scorer_fixture() -> tuple[
    dict[str, object], dict[str, object], dict[str, object]
]:
    """Build one provider-backed score with exact output and usage binding."""

    plan, source_result = build_synthetic_fixture()
    session = plan["sessions"][0]
    source_arm = source_result["records"][0]["arms"][0]
    task = session["tasks"][0]
    task_result = deepcopy(source_arm["task_results"][0])
    task_result["scorer_receipt_sha256"] = None
    output_text = '{"answer":42}'
    output_sha256 = sha256_ref({"provider_output_text": output_text})
    provider_response_sha256 = sha256_ref(
        {"provider_response": {"id": "response-v2", "output": output_text}}
    )
    usage = deepcopy(source_arm["events"][0]["usage"])
    event = {
        "sequence": 0,
        "phase": "receiver",
        "task_id": task["task_id"],
        "input_sha256": sha256_ref({"provider_input": task["task_id"]}),
        "output_sha256": output_sha256,
        "usage_receipt_sha256": None,
        "usage": usage,
    }
    plan_sha256 = sha256_ref(plan)
    arm_id = "raw-concise"
    manifest_sha256 = session["arm_execution_manifest_sha256"][arm_id]
    model = next(
        item
        for item in plan["receiver_models"]
        if item["family"] == session["receiver_family"]
    )
    usage_binding = {
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
    usage_source = {
        "source_kind": "provider",
        "request_id": "request-v2",
        "response_id": "response-v2",
        "model_id": model["model_id"],
        "settings_sha256": model["settings_sha256"],
        "reported_usage": event["usage"],
        "raw_receipt_sha256": sha256_ref({"raw_provider_receipt": "v2"}),
        "provider_response_sha256": provider_response_sha256,
        "provider_terminal_status": "completed",
    }
    usage_receipt = _receipt(
        kind="usage",
        issuer_id=session["operator_id"],
        binding=usage_binding,
        source_payload=usage_source,
        schema_version=USAGE_RECEIPT_SCHEMA_V2,
    )
    event["usage_receipt_sha256"] = sha256_ref(usage_receipt)

    observed = deepcopy(task_result)
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
    terminal_event = {
        "terminal_kind": "provider-response",
        "event_sequence": event["sequence"],
        "phase": event["phase"],
        "task_id": event["task_id"],
        "input_sha256": event["input_sha256"],
        "output_sha256": event["output_sha256"],
        "usage_receipt_sha256": event["usage_receipt_sha256"],
        "usage": event["usage"],
        "provider_response_sha256": provider_response_sha256,
        "terminal_status": "completed",
    }
    scorer_binding = {
        "study_id": plan["study_id"],
        "plan_sha256": plan_sha256,
        "session_id": session["session_id"],
        "arm_id": arm_id,
        "execution_manifest_sha256": manifest_sha256,
        "task": task,
        "scorer_locks": scorer_locks,
        "observed": observed,
        "terminal_event": terminal_event,
    }
    scorer_source = {
        "artifact_sha256": plan["artifact_locks"]["task_scorer"],
        "observation": observed,
        "terminal_event": deepcopy(terminal_event),
        "provider_output": {
            "kind": "provider-text",
            "encoding": "utf-8",
            "text": output_text,
            "output_sha256": output_sha256,
            "provider_response_sha256": provider_response_sha256,
        },
    }
    scorer_receipt = _receipt(
        kind="scorer",
        issuer_id=session["operator_id"],
        binding=scorer_binding,
        source_payload=scorer_source,
        schema_version=SCORER_OUTPUT_RECEIPT_SCHEMA,
    )
    task_result["scorer_receipt_sha256"] = sha256_ref(scorer_receipt)
    result = {
        "records": [
            {
                "session_id": session["session_id"],
                "attestation": source_result["records"][0]["attestation"],
                "arms": [
                    {
                        "arm_id": arm_id,
                        "events": [event],
                        "task_results": [task_result],
                        "sandbox_evidence": [],
                    }
                ],
            }
        ]
    }
    bundle = {
        "schema_version": RECEIPT_BUNDLE_SCHEMA_V2,
        "plan_sha256": plan_sha256,
        "receipts": [usage_receipt, scorer_receipt],
    }
    return plan, result, bundle


def _reattach_v2_scorer(
    result: dict[str, object], bundle: dict[str, object]
) -> dict[str, object]:
    receipt = next(item for item in bundle["receipts"] if item["kind"] == "scorer")
    receipt["source_sha256"] = sha256_ref(receipt["source_payload"])
    result["records"][0]["arms"][0]["task_results"][0][
        "scorer_receipt_sha256"
    ] = sha256_ref(receipt)
    return receipt


def _build_v2_silence_fixture() -> tuple[
    dict[str, object], dict[str, object], dict[str, object]
]:
    """Build one canonical silence score with no provider terminal artifact."""

    plan, result, bundle = _build_v2_scorer_fixture()
    session = plan["sessions"][0]
    arm = result["records"][0]["arms"][0]
    task_result = arm["task_results"][0]
    task_id = task_result["task_id"]
    arm_id = "hybrid-router"
    manifest_sha256 = session["arm_execution_manifest_sha256"][arm_id]
    local_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "unclassified_tokens": 0,
        "provider_total_tokens": None,
        "total_tokens": 0,
        "hidden_accounting": "none",
    }
    decision_event = {
        "sequence": 0,
        "phase": "router",
        "task_id": task_id,
        "input_sha256": sha256_ref({"silence_router_input": task_id}),
        "output_sha256": sha256_ref({"selected_mode": "silence"}),
        "usage_receipt_sha256": None,
        "usage": local_usage,
    }
    usage_binding = {
        "study_id": plan["study_id"],
        "plan_sha256": sha256_ref(plan),
        "session_id": session["session_id"],
        "arm_id": arm_id,
        "execution_manifest_sha256": manifest_sha256,
        "receiver_family": session["receiver_family"],
        "event_sequence": decision_event["sequence"],
        "phase": decision_event["phase"],
        "task_id": decision_event["task_id"],
        "input_sha256": decision_event["input_sha256"],
        "output_sha256": decision_event["output_sha256"],
        "usage": decision_event["usage"],
    }
    usage_source = {
        "source_kind": "deterministic-local",
        "request_id": None,
        "response_id": None,
        "model_id": None,
        "settings_sha256": None,
        "reported_usage": local_usage,
        "raw_receipt_sha256": sha256_ref({"silence_router": task_id}),
        "provider_response_sha256": None,
        "provider_terminal_status": None,
    }
    usage_receipt = _receipt(
        kind="usage",
        issuer_id=session["operator_id"],
        binding=usage_binding,
        source_payload=usage_source,
        schema_version=USAGE_RECEIPT_SCHEMA_V2,
    )
    decision_event["usage_receipt_sha256"] = sha256_ref(usage_receipt)
    arm["arm_id"] = arm_id
    arm["events"] = [decision_event]
    task_result["route"] = {
        "selected_mode": "silence",
        "decision_event_sequence": 0,
        "receiver_event_sequence": None,
        "decode_before_model": False,
        "natural_language_expansion": False,
        "fallback_from": None,
    }

    scorer_receipt = next(
        item for item in bundle["receipts"] if item["kind"] == "scorer"
    )
    observed = deepcopy(task_result)
    observed.pop("scorer_receipt_sha256", None)
    terminal_event = {
        "terminal_kind": "canonical-silence",
        "event_sequence": None,
        "phase": "silence",
        "task_id": task_id,
        "input_sha256": None,
        "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
        "usage_receipt_sha256": None,
        "usage": None,
        "provider_response_sha256": None,
        "terminal_status": "silenced",
    }
    scorer_receipt["binding"].update(
        {
            "arm_id": arm_id,
            "execution_manifest_sha256": manifest_sha256,
            "observed": observed,
            "terminal_event": deepcopy(terminal_event),
        }
    )
    scorer_receipt["source_payload"].update(
        {
            "observation": observed,
            "terminal_event": deepcopy(terminal_event),
            "provider_output": {
                "kind": "canonical-silence",
                "encoding": None,
                "text": None,
                "output_sha256": CANONICAL_SILENCE_OUTPUT_SHA256,
                "provider_response_sha256": None,
            },
        }
    )
    scorer_receipt["source_sha256"] = sha256_ref(
        scorer_receipt["source_payload"]
    )
    task_result["scorer_receipt_sha256"] = sha256_ref(scorer_receipt)
    bundle["receipts"] = [usage_receipt, scorer_receipt]
    return plan, result, bundle


def _build_v2_no_output_failure_fixture(
    status: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build one provider failure whose exact terminal output is null."""

    plan, result, bundle = _build_v2_scorer_fixture()
    arm = result["records"][0]["arms"][0]
    event = arm["events"][0]
    task_result = arm["task_results"][0]
    event["output_sha256"] = None
    task_result["task_success"] = False

    usage_receipt = next(
        item for item in bundle["receipts"] if item["kind"] == "usage"
    )
    usage_receipt["binding"]["output_sha256"] = None
    usage_receipt["source_payload"]["provider_terminal_status"] = status
    usage_receipt["source_sha256"] = sha256_ref(usage_receipt["source_payload"])
    usage_digest = sha256_ref(usage_receipt)
    event["usage_receipt_sha256"] = usage_digest

    scorer_receipt = next(
        item for item in bundle["receipts"] if item["kind"] == "scorer"
    )
    observed = deepcopy(task_result)
    observed.pop("scorer_receipt_sha256", None)
    terminal_event = deepcopy(scorer_receipt["binding"]["terminal_event"])
    terminal_event.update(
        {
            "output_sha256": None,
            "usage_receipt_sha256": usage_digest,
            "terminal_status": status,
        }
    )
    scorer_receipt["binding"].update(
        {"observed": observed, "terminal_event": deepcopy(terminal_event)}
    )
    scorer_receipt["source_payload"].update(
        {
            "observation": observed,
            "terminal_event": deepcopy(terminal_event),
            "provider_output": {
                "kind": "provider-no-output",
                "encoding": None,
                "text": None,
                "output_sha256": None,
                "provider_response_sha256": terminal_event[
                    "provider_response_sha256"
                ],
            },
        }
    )
    scorer_receipt["source_sha256"] = sha256_ref(
        scorer_receipt["source_payload"]
    )
    task_result["scorer_receipt_sha256"] = sha256_ref(scorer_receipt)
    return plan, result, bundle


def _build_v2_fallback_fixture() -> tuple[
    dict[str, object], dict[str, object], dict[str, object]
]:
    """Build one hybrid result whose exact scored terminal is a fallback."""

    plan, result, bundle = _build_v2_scorer_fixture()
    silence_plan, silence_result, silence_bundle = _build_v2_silence_fixture()
    assert sha256_ref(plan) == sha256_ref(silence_plan)
    session = plan["sessions"][0]
    arm = result["records"][0]["arms"][0]
    task_result = arm["task_results"][0]
    arm_id = "hybrid-router"
    manifest_sha256 = session["arm_execution_manifest_sha256"][arm_id]
    decision_event = deepcopy(silence_result["records"][0]["arms"][0]["events"][0])
    decision_receipt = deepcopy(
        next(item for item in silence_bundle["receipts"] if item["kind"] == "usage")
    )

    fallback_event = arm["events"][0]
    fallback_event["sequence"] = 1
    fallback_event["phase"] = "fallback"
    usage_receipt = next(
        item for item in bundle["receipts"] if item["kind"] == "usage"
    )
    usage_receipt["binding"].update(
        {
            "arm_id": arm_id,
            "execution_manifest_sha256": manifest_sha256,
            "event_sequence": 1,
            "phase": "fallback",
        }
    )
    usage_receipt["source_sha256"] = sha256_ref(usage_receipt["source_payload"])
    usage_digest = sha256_ref(usage_receipt)
    fallback_event["usage_receipt_sha256"] = usage_digest
    arm["arm_id"] = arm_id
    arm["events"] = [decision_event, fallback_event]
    task_result["route"] = {
        "selected_mode": "action-state",
        "decision_event_sequence": 0,
        "receiver_event_sequence": 1,
        "decode_before_model": False,
        "natural_language_expansion": False,
        "fallback_from": "action-state:receiver:refused",
    }

    scorer_receipt = next(
        item for item in bundle["receipts"] if item["kind"] == "scorer"
    )
    observed = deepcopy(task_result)
    observed.pop("scorer_receipt_sha256", None)
    terminal_event = deepcopy(scorer_receipt["binding"]["terminal_event"])
    terminal_event.update(
        {
            "event_sequence": 1,
            "phase": "fallback",
            "usage_receipt_sha256": usage_digest,
        }
    )
    scorer_receipt["binding"].update(
        {
            "arm_id": arm_id,
            "execution_manifest_sha256": manifest_sha256,
            "observed": observed,
            "terminal_event": deepcopy(terminal_event),
        }
    )
    scorer_receipt["source_payload"].update(
        {"observation": observed, "terminal_event": deepcopy(terminal_event)}
    )
    scorer_receipt["source_sha256"] = sha256_ref(
        scorer_receipt["source_payload"]
    )
    task_result["scorer_receipt_sha256"] = sha256_ref(scorer_receipt)
    bundle["receipts"] = [decision_receipt, usage_receipt, scorer_receipt]
    return plan, result, bundle


def _generic_source(
    artifact_sha256: str,
    observation: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_sha256": artifact_sha256,
        "observation": observation,
    }


def build_bound_receipts(
    plan_value: dict[str, object],
    result_value: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Replace every fixture reference with an exactly bound test receipt."""

    plan = deepcopy(plan_value)
    result = deepcopy(result_value)
    plan["evidence_boundary"] = "real-independent-evaluation"
    plan_sha256 = sha256_ref(plan)
    result["plan_sha256"] = plan_sha256
    model_by_family = {
        item["family"]: item for item in plan["receiver_models"]
    }
    session_by_id = {
        item["session_id"]: item for item in plan["sessions"]
    }
    receipts: list[dict[str, object]] = []

    def attach(
        target: dict[str, object],
        field: str,
        *,
        kind: str,
        issuer_id: str,
        binding: dict[str, object],
        source_payload: dict[str, object],
    ) -> None:
        value = _receipt(
            kind=kind,
            issuer_id=issuer_id,
            binding=binding,
            source_payload=source_payload,
        )
        receipts.append(value)
        target[field] = sha256_ref(value)

    for record in result["records"]:
        session = session_by_id[record["session_id"]]
        operator_id = session["operator_id"]
        auditor_id = session["boundary_auditor_id"]
        model = model_by_family[session["receiver_family"]]
        planned_tasks = {item["task_id"]: item for item in session["tasks"]}
        arm_by_id = {item["arm_id"]: item for item in record["arms"]}
        for arm_id in ARMS:
            arm = arm_by_id[arm_id]
            manifest_sha256 = session["arm_execution_manifest_sha256"][arm_id]
            for event in arm["events"]:
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
                provider_phase = event["phase"] in {"receiver", "fallback"}
                source = {
                    "source_kind": (
                        "provider" if provider_phase else "deterministic-local"
                    ),
                    "request_id": (
                        f"request-{session['session_id']}-{arm_id}-{event['sequence']}"
                        if provider_phase
                        else None
                    ),
                    "response_id": (
                        f"response-{session['session_id']}-{arm_id}-{event['sequence']}"
                        if provider_phase
                        else None
                    ),
                    "model_id": model["model_id"] if provider_phase else None,
                    "settings_sha256": (
                        model["settings_sha256"] if provider_phase else None
                    ),
                    "reported_usage": event["usage"],
                    "raw_receipt_sha256": sha256_ref(
                        {
                            "synthetic-provider-receipt": [
                                session["session_id"],
                                arm_id,
                                event["sequence"],
                            ]
                        }
                    ),
                }
                attach(
                    event,
                    "usage_receipt_sha256",
                    kind="usage",
                    issuer_id=operator_id,
                    binding=binding,
                    source_payload=source,
                )

            for task_result in arm["task_results"]:
                observed = deepcopy(task_result)
                observed.pop("scorer_receipt_sha256", None)
                task = planned_tasks[task_result["task_id"]]
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
                attach(
                    task_result,
                    "scorer_receipt_sha256",
                    kind="scorer",
                    issuer_id=operator_id,
                    binding=binding,
                    source_payload=_generic_source(
                        plan["artifact_locks"]["task_scorer"],
                        observed,
                    ),
                )

            for entry in arm["sandbox_evidence"]:
                common = {
                    "study_id": plan["study_id"],
                    "plan_sha256": plan_sha256,
                    "session_id": session["session_id"],
                    "arm_id": arm_id,
                    "role": entry["role"],
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
                specs = (
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
                    ),
                    (
                        "operator_attestation_sha256",
                        "operator-attestation",
                        operator_id,
                        {**common, "session_attestation": record["attestation"]},
                        {"session_attestation": record["attestation"]},
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
                    ),
                )
                for field, kind, issuer, binding, observation in specs:
                    if kind == "sandbox-enforcement":
                        artifact_sha256 = entry["enforcement_profile_sha256"]
                    elif kind == "operator-attestation":
                        artifact_sha256 = next(
                            item["attestation_sha256"]
                            for item in plan["operators"]
                            if item["operator_id"] == operator_id
                        )
                    else:
                        artifact_sha256 = entry[
                            "independent_audit_protocol_sha256"
                        ]
                    attach(
                        entry,
                        field,
                        kind=kind,
                        issuer_id=issuer,
                        binding=binding,
                        source_payload=_generic_source(
                            artifact_sha256,
                            observation,
                        ),
                    )

    bundle = {
        "schema_version": RECEIPT_BUNDLE_SCHEMA,
        "plan_sha256": plan_sha256,
        "receipts": receipts,
    }
    return plan, result, bundle


def _replace_reference(value: object, old: str, new: str) -> bool:
    """Replace one digest reference in nested test JSON."""

    if type(value) is dict:
        for key, item in value.items():
            if item == old:
                value[key] = new
                return True
            if _replace_reference(item, old, new):
                return True
    elif type(value) is list:
        for item in value:
            if _replace_reference(item, old, new):
                return True
    return False


class ReceiptStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        plan, result = build_synthetic_fixture()
        self.plan, self.result, self.bundle = build_bound_receipts(plan, result)

    def verify(
        self,
        *,
        plan: dict[str, object] | None = None,
        result: dict[str, object] | None = None,
        bundle: dict[str, object] | None = None,
    ) -> dict[str, object]:
        store = ReceiptStore.from_object(bundle or self.bundle)
        return verify_result(
            plan or self.plan,
            result or self.result,
            receipt_store=store,
        )

    def test_real_evidence_without_receipt_store_fails_closed(self) -> None:
        summary = verify_result(self.plan, self.result)
        self.assertFalse(summary["metric_gate_passed"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertFalse(summary["measurement_scope_complete"])
        self.assertEqual(
            summary["receipt_bundle"]["errors"],
            ["receipt-bundle-not-supplied"],
        )
        self.assertIn(
            "receipt-bundle-incomplete-or-unvalidated",
            summary["gate_failures"],
        )

    def test_self_authored_bundle_only_closes_content_gate(self) -> None:
        summary = self.verify()
        receipt = summary["receipt_bundle"]
        self.assertTrue(receipt["required"])
        self.assertTrue(receipt["supplied"])
        self.assertTrue(receipt["content_consistent"])
        self.assertFalse(receipt["scorer_output_binding_complete"])
        self.assertFalse(receipt["complete"])
        self.assertEqual(receipt["referenced"], 576)
        self.assertEqual(receipt["resolved"], 576)
        self.assertEqual(receipt["unreferenced"], 0)
        self.assertFalse(summary["metric_gate_passed"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertFalse(summary["evidence_authentication"]["complete"])
        self.assertIn(
            "authenticated-provenance-not-established",
            summary["gate_failures"],
        )
        self.assertIn(
            "receipt-bundle-incomplete-or-unvalidated",
            summary["gate_failures"],
        )

    def test_complete_v2_receipt_gate_cannot_self_authenticate(self) -> None:
        class CompleteReceiptStore:
            @staticmethod
            def validate(plan_value, result_value):
                return ReceiptValidation(
                    content_consistent=True,
                    scorer_output_binding_complete=True,
                    referenced=576,
                    resolved=576,
                    unreferenced=0,
                    errors=(),
                )

        summary = verify_result(
            self.plan,
            self.result,
            receipt_store=CompleteReceiptStore(),
        )

        self.assertTrue(summary["receipt_bundle"]["complete"])
        self.assertFalse(summary["evidence_authentication"]["complete"])
        self.assertFalse(summary["metric_gate_passed"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertIn(
            "authenticated-provenance-not-established",
            summary["gate_failures"],
        )

    def test_missing_and_replayed_receipts_fail_closed(self) -> None:
        missing_bundle = deepcopy(self.bundle)
        missing_bundle["receipts"].pop(0)
        missing = self.verify(bundle=missing_bundle)
        self.assertFalse(missing["goal_gate_passed"])
        self.assertTrue(
            any(
                item.startswith("missing-receipt:")
                for item in missing["receipt_bundle"]["errors"]
            )
        )

        replay_result = deepcopy(self.result)
        first = replay_result["records"][0]["arms"][0]["events"][0]
        second = replay_result["records"][0]["arms"][1]["events"][0]
        second["usage_receipt_sha256"] = first["usage_receipt_sha256"]
        replayed = self.verify(result=replay_result)
        self.assertFalse(replayed["goal_gate_passed"])
        self.assertTrue(
            any(
                item.startswith("replayed-receipt:")
                for item in replayed["receipt_bundle"]["errors"]
            )
        )

    def test_wrong_binding_and_usage_accounting_fail_closed(self) -> None:
        for mutation, expected in (
            ("binding", "receipt-binding-mismatch:"),
            ("usage", "usage-source-accounting-mismatch:"),
            ("model", "usage-source-receiver-model-mismatch:"),
        ):
            with self.subTest(mutation=mutation):
                result = deepcopy(self.result)
                bundle = deepcopy(self.bundle)
                receipt = bundle["receipts"][0]
                if mutation == "binding":
                    receipt["binding"]["event_sequence"] = 999
                elif mutation == "usage":
                    receipt["source_payload"]["reported_usage"] = deepcopy(
                        receipt["source_payload"]["reported_usage"]
                    )
                    receipt["source_payload"]["reported_usage"][
                        "input_tokens"
                    ] += 1
                    receipt["source_sha256"] = sha256_ref(
                        receipt["source_payload"]
                    )
                else:
                    receipt["source_payload"]["model_id"] = "wrong-model"
                    receipt["source_sha256"] = sha256_ref(
                        receipt["source_payload"]
                    )
                result["records"][0]["arms"][0]["events"][0][
                    "usage_receipt_sha256"
                ] = sha256_ref(receipt)
                summary = self.verify(result=result, bundle=bundle)
                self.assertFalse(summary["goal_gate_passed"])
                self.assertLess(summary["receipt_bundle"]["resolved"], 576)
                self.assertTrue(
                    any(
                        item.startswith(expected)
                        for item in summary["receipt_bundle"]["errors"]
                    )
                )

    def test_receiver_cannot_be_relabelled_deterministic_local(self) -> None:
        result = deepcopy(self.result)
        bundle = deepcopy(self.bundle)
        receipt = next(
            item
            for item in bundle["receipts"]
            if item["kind"] == "usage"
            and item["binding"]["phase"] == "receiver"
        )
        old = sha256_ref(receipt)
        source = receipt["source_payload"]
        source["source_kind"] = "deterministic-local"
        for field in ("request_id", "response_id", "model_id", "settings_sha256"):
            source[field] = None
        receipt["source_sha256"] = sha256_ref(source)
        new = sha256_ref(receipt)
        self.assertTrue(_replace_reference(result, old, new))
        summary = self.verify(result=result, bundle=bundle)
        self.assertFalse(summary["receipt_bundle"]["content_consistent"])
        self.assertTrue(
            any(
                item.startswith("usage-source-model-call-required:")
                for item in summary["receipt_bundle"]["errors"]
            )
        )

    def test_provider_call_identity_cannot_be_replayed(self) -> None:
        result = deepcopy(self.result)
        bundle = deepcopy(self.bundle)
        provider = [
            item
            for item in bundle["receipts"]
            if item["kind"] == "usage"
            and item["source_payload"]["source_kind"] == "provider"
        ]
        first, second = provider[:2]
        old = sha256_ref(second)
        second["source_payload"]["raw_receipt_sha256"] = first[
            "source_payload"
        ]["raw_receipt_sha256"]
        second["source_sha256"] = sha256_ref(second["source_payload"])
        new = sha256_ref(second)
        self.assertTrue(_replace_reference(result, old, new))
        summary = self.verify(result=result, bundle=bundle)
        self.assertFalse(summary["receipt_bundle"]["content_consistent"])
        self.assertTrue(
            any(
                item.startswith("usage-source-provider-call-replayed:")
                for item in summary["receipt_bundle"]["errors"]
            )
        )

    def test_unhashable_provider_identity_fails_closed_without_exception(
        self,
    ) -> None:
        cases = (
            ("request_id", [], "usage-source-request_id-invalid:"),
            ("response_id", {}, "usage-source-response_id-invalid:"),
            (
                "raw_receipt_sha256",
                [],
                "usage-source-raw-digest-invalid:",
            ),
            (
                "raw_receipt_sha256",
                "not-a-sha256",
                "usage-source-raw-digest-invalid:",
            ),
        )
        for field, malformed, expected_error in cases:
            with self.subTest(field=field, malformed=malformed):
                result = deepcopy(self.result)
                bundle = deepcopy(self.bundle)
                receipt = next(
                    item
                    for item in bundle["receipts"]
                    if item["kind"] == "usage"
                    and item["source_payload"]["source_kind"] == "provider"
                )
                old = sha256_ref(receipt)
                receipt["source_payload"][field] = malformed
                receipt["source_sha256"] = sha256_ref(
                    receipt["source_payload"]
                )
                new = sha256_ref(receipt)
                self.assertTrue(_replace_reference(result, old, new))

                summary = self.verify(result=result, bundle=bundle)

                self.assertFalse(
                    summary["receipt_bundle"]["content_consistent"]
                )
                self.assertFalse(summary["goal_gate_passed"])
                self.assertLess(summary["receipt_bundle"]["resolved"], 576)
                self.assertTrue(
                    any(
                        item.startswith(expected_error)
                        for item in summary["receipt_bundle"]["errors"]
                    )
                )

    def test_frozen_artifact_identity_is_not_an_arbitrary_digest(self) -> None:
        result = deepcopy(self.result)
        bundle = deepcopy(self.bundle)
        receipt = next(
            item for item in bundle["receipts"] if item["kind"] == "scorer"
        )
        old = sha256_ref(receipt)
        receipt["source_payload"]["artifact_sha256"] = sha256_ref(
            {"unfrozen": "scorer"}
        )
        receipt["source_sha256"] = sha256_ref(receipt["source_payload"])
        new = sha256_ref(receipt)
        self.assertTrue(_replace_reference(result, old, new))
        summary = self.verify(result=result, bundle=bundle)
        self.assertFalse(summary["receipt_bundle"]["content_consistent"])
        self.assertTrue(
            any(
                item.startswith("scorer-source-artifact-mismatch:")
                for item in summary["receipt_bundle"]["errors"]
            )
        )

    def test_store_detaches_input_and_rechecks_internal_content_digest(self) -> None:
        bundle = deepcopy(self.bundle)
        store = ReceiptStore.from_object(bundle)
        bundle["receipts"][0]["source_payload"]["request_id"] = "mutated"
        validation = store.validate(self.plan, self.result)
        self.assertTrue(validation.content_consistent)
        self.assertFalse(validation.scorer_output_binding_complete)
        self.assertFalse(validation.complete)

        digest = next(iter(store._receipts))
        store._receipts[digest]["source_payload"]["request_id"] = "corrupt"
        corrupted = store.validate(self.plan, self.result)
        self.assertFalse(corrupted.complete)
        self.assertIn(
            f"receipt-content-digest-mismatch:{digest}",
            corrupted.errors,
        )

    def test_source_digest_tamper_is_rejected_at_load(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["receipts"][0]["source_payload"]["request_id"] = "tampered"
        with self.assertRaisesRegex(
            VerificationError, "source payload digest mismatch"
        ):
            ReceiptStore.from_object(bundle)

    def test_unreferenced_receipt_and_plan_rebinding_fail_closed(self) -> None:
        bundle = deepcopy(self.bundle)
        extra = deepcopy(bundle["receipts"][0])
        extra["binding"]["event_sequence"] = 1001
        bundle["receipts"].append(extra)
        unreferenced = self.verify(bundle=bundle)
        self.assertFalse(unreferenced["goal_gate_passed"])
        self.assertIn(
            "unreferenced-receipts:1",
            unreferenced["receipt_bundle"]["errors"],
        )

        wrong_plan_bundle = deepcopy(self.bundle)
        wrong_plan_bundle["plan_sha256"] = sha256_ref({"different": "plan"})
        wrong_plan = self.verify(bundle=wrong_plan_bundle)
        self.assertFalse(wrong_plan["goal_gate_passed"])
        self.assertIn(
            "receipt-bundle-plan-mismatch",
            wrong_plan["receipt_bundle"]["errors"],
        )


class ScorerOutputReceiptV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan, self.result, self.bundle = _build_v2_scorer_fixture()

    def validate(self):
        return ReceiptStore.from_object(self.bundle).validate(
            self.plan, self.result
        )

    def test_exact_provider_output_and_usage_receipt_close_v2_binding(self) -> None:
        validation = self.validate()
        self.assertTrue(validation.content_consistent)
        self.assertTrue(validation.scorer_output_binding_complete)
        self.assertTrue(validation.complete)
        self.assertEqual(validation.referenced, 2)
        self.assertEqual(validation.resolved, 2)

    def test_canonical_silence_closes_without_provider_terminal_receipt(self) -> None:
        plan, result, bundle = _build_v2_silence_fixture()

        validation = ReceiptStore.from_object(bundle).validate(plan, result)

        self.assertTrue(validation.content_consistent)
        self.assertTrue(validation.scorer_output_binding_complete)
        self.assertTrue(validation.complete)
        scorer = next(item for item in bundle["receipts"] if item["kind"] == "scorer")
        terminal = scorer["source_payload"]["terminal_event"]
        self.assertEqual(terminal["terminal_status"], "silenced")
        self.assertIsNone(terminal["usage_receipt_sha256"])
        self.assertIsNone(terminal["provider_response_sha256"])

    def test_canonical_silence_digest_cannot_be_self_rebound(self) -> None:
        plan, result, bundle = _build_v2_silence_fixture()
        scorer = next(item for item in bundle["receipts"] if item["kind"] == "scorer")
        replacement = sha256_ref({"not": "canonical-silence"})
        scorer["binding"]["terminal_event"]["output_sha256"] = replacement
        scorer["source_payload"]["terminal_event"]["output_sha256"] = replacement
        scorer["source_payload"]["provider_output"]["output_sha256"] = replacement
        scorer["source_sha256"] = sha256_ref(scorer["source_payload"])
        result["records"][0]["arms"][0]["task_results"][0][
            "scorer_receipt_sha256"
        ] = sha256_ref(scorer)

        validation = ReceiptStore.from_object(bundle).validate(plan, result)

        self.assertFalse(validation.content_consistent)
        self.assertFalse(validation.complete)
        self.assertTrue(
            any(
                item.startswith("receipt-binding-mismatch:")
                for item in validation.errors
            )
        )

    def test_no_output_provider_failures_are_explicit_scored_failures(self) -> None:
        for status in ("timeout", "refused", "provider_error"):
            with self.subTest(status=status):
                plan, result, bundle = _build_v2_no_output_failure_fixture(status)

                validation = ReceiptStore.from_object(bundle).validate(plan, result)

                self.assertTrue(validation.content_consistent)
                self.assertTrue(validation.scorer_output_binding_complete)
                self.assertTrue(validation.complete)

    def test_noncompleted_provider_terminal_cannot_score_success(self) -> None:
        plan, result, bundle = _build_v2_no_output_failure_fixture("timeout")
        task_result = result["records"][0]["arms"][0]["task_results"][0]
        task_result["task_success"] = True
        observed = deepcopy(task_result)
        observed.pop("scorer_receipt_sha256", None)
        scorer = next(item for item in bundle["receipts"] if item["kind"] == "scorer")
        scorer["binding"]["observed"] = observed
        scorer["source_payload"]["observation"] = observed
        scorer["source_sha256"] = sha256_ref(scorer["source_payload"])
        task_result["scorer_receipt_sha256"] = sha256_ref(scorer)

        validation = ReceiptStore.from_object(bundle).validate(plan, result)

        self.assertFalse(validation.content_consistent)
        self.assertFalse(validation.complete)
        self.assertTrue(
            any(
                item.startswith("scorer-v2-noncompleted-success:")
                for item in validation.errors
            )
        )

    def test_provider_response_digest_replay_across_arms_fails_closed(self) -> None:
        arm = self.result["records"][0]["arms"][0]
        usage = next(
            item for item in self.bundle["receipts"] if item["kind"] == "usage"
        )
        scorer = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        replay_arm = deepcopy(arm)
        replay_arm["arm_id"] = "ordinary-json"
        manifest_sha256 = self.plan["sessions"][0][
            "arm_execution_manifest_sha256"
        ]["ordinary-json"]
        replacement_text = '{"answer":9000}'
        replacement_output_sha256 = sha256_ref(
            {"provider_output_text": replacement_text}
        )
        replay_arm["events"][0]["output_sha256"] = replacement_output_sha256

        replay_usage = deepcopy(usage)
        replay_usage["binding"].update(
            {
                "arm_id": "ordinary-json",
                "execution_manifest_sha256": manifest_sha256,
                "output_sha256": replacement_output_sha256,
            }
        )
        replay_usage["source_payload"].update(
            {
                "request_id": "request-v2-replay",
                "response_id": "response-v2-replay",
                "raw_receipt_sha256": sha256_ref({"raw": "v2-replay"}),
            }
        )
        replay_usage["source_sha256"] = sha256_ref(
            replay_usage["source_payload"]
        )
        replay_usage_digest = sha256_ref(replay_usage)
        replay_arm["events"][0]["usage_receipt_sha256"] = replay_usage_digest

        replay_scorer = deepcopy(scorer)
        replay_scorer["binding"].update(
            {
                "arm_id": "ordinary-json",
                "execution_manifest_sha256": manifest_sha256,
            }
        )
        replay_scorer["binding"]["terminal_event"].update(
            {
                "output_sha256": replacement_output_sha256,
                "usage_receipt_sha256": replay_usage_digest,
            }
        )
        replay_scorer["source_payload"]["terminal_event"].update(
            {
                "output_sha256": replacement_output_sha256,
                "usage_receipt_sha256": replay_usage_digest,
            }
        )
        replay_scorer["source_payload"]["provider_output"].update(
            {"text": replacement_text, "output_sha256": replacement_output_sha256}
        )
        replay_scorer["source_sha256"] = sha256_ref(
            replay_scorer["source_payload"]
        )
        replay_arm["task_results"][0]["scorer_receipt_sha256"] = sha256_ref(
            replay_scorer
        )
        self.result["records"][0]["arms"].append(replay_arm)
        self.bundle["receipts"].extend([replay_usage, replay_scorer])

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertFalse(validation.complete)
        self.assertTrue(
            any(
                item.startswith("usage-source-provider-call-replayed:")
                for item in validation.errors
            )
        )

    def test_hybrid_route_decision_cannot_borrow_another_tasks_event(self) -> None:
        plan, result, bundle = _build_v2_silence_fixture()
        foreign_task_id = plan["sessions"][0]["tasks"][1]["task_id"]
        event = result["records"][0]["arms"][0]["events"][0]
        event["task_id"] = foreign_task_id
        usage = next(item for item in bundle["receipts"] if item["kind"] == "usage")
        usage["binding"]["task_id"] = foreign_task_id
        usage["source_sha256"] = sha256_ref(usage["source_payload"])
        event["usage_receipt_sha256"] = sha256_ref(usage)

        validation = ReceiptStore.from_object(bundle).validate(plan, result)

        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                item.startswith("scorer-v2-route-decision-task-mismatch:")
                for item in validation.errors
            )
        )

    def test_hybrid_fallback_cannot_borrow_another_tasks_event(self) -> None:
        plan, result, bundle = _build_v2_fallback_fixture()
        exact = ReceiptStore.from_object(bundle).validate(plan, result)
        self.assertTrue(exact.complete)
        foreign_task_id = plan["sessions"][0]["tasks"][1]["task_id"]
        fallback = result["records"][0]["arms"][0]["events"][1]
        fallback["task_id"] = foreign_task_id
        provider_usage = next(
            item
            for item in bundle["receipts"]
            if item["kind"] == "usage"
            and item["source_payload"]["source_kind"] == "provider"
        )
        provider_usage["binding"]["task_id"] = foreign_task_id
        provider_usage["source_sha256"] = sha256_ref(
            provider_usage["source_payload"]
        )
        fallback["usage_receipt_sha256"] = sha256_ref(provider_usage)

        validation = ReceiptStore.from_object(bundle).validate(plan, result)

        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                item.startswith("scorer-v2-terminal-event-not-unique:")
                for item in validation.errors
            )
        )

    def test_exact_provider_output_text_mutation_fails_closed(self) -> None:
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        receipt["source_payload"]["provider_output"]["text"] = '{"answer":43}'
        _reattach_v2_scorer(self.result, self.bundle)

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertFalse(validation.complete)
        self.assertTrue(
            any(
                item.startswith("scorer-v2-provider-output-digest-mismatch:")
                for item in validation.errors
            )
        )

    def test_terminal_output_rebinding_cannot_replace_observed_event(self) -> None:
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        replacement_text = '{"answer":9000}'
        replacement_sha = sha256_ref({"provider_output_text": replacement_text})
        receipt["binding"]["terminal_event"]["output_sha256"] = replacement_sha
        receipt["source_payload"]["terminal_event"][
            "output_sha256"
        ] = replacement_sha
        receipt["source_payload"]["provider_output"].update(
            {"text": replacement_text, "output_sha256": replacement_sha}
        )
        _reattach_v2_scorer(self.result, self.bundle)

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                item.startswith("receipt-binding-mismatch:")
                for item in validation.errors
            )
        )

    def test_terminal_usage_receipt_rebinding_fails_closed(self) -> None:
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        replacement = sha256_ref({"unrelated_usage_receipt": True})
        receipt["binding"]["terminal_event"][
            "usage_receipt_sha256"
        ] = replacement
        receipt["source_payload"]["terminal_event"][
            "usage_receipt_sha256"
        ] = replacement
        _reattach_v2_scorer(self.result, self.bundle)

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                item.startswith("receipt-binding-mismatch:")
                for item in validation.errors
            )
        )

    def test_provider_response_digest_is_mandatory(self) -> None:
        usage_receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "usage"
        )
        usage_receipt["source_payload"]["provider_response_sha256"] = None
        usage_receipt["source_sha256"] = sha256_ref(
            usage_receipt["source_payload"]
        )
        replacement_usage_sha = sha256_ref(usage_receipt)
        self.result["records"][0]["arms"][0]["events"][0][
            "usage_receipt_sha256"
        ] = replacement_usage_sha
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        receipt["binding"]["terminal_event"][
            "usage_receipt_sha256"
        ] = replacement_usage_sha
        receipt["source_payload"]["terminal_event"][
            "usage_receipt_sha256"
        ] = replacement_usage_sha
        receipt["binding"]["terminal_event"]["provider_response_sha256"] = None
        receipt["source_payload"]["terminal_event"][
            "provider_response_sha256"
        ] = None
        receipt["source_payload"]["provider_output"][
            "provider_response_sha256"
        ] = None
        _reattach_v2_scorer(self.result, self.bundle)

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertFalse(validation.scorer_output_binding_complete)
        self.assertTrue(
            any(
                item.startswith(
                    "usage-source-provider-response-digest-invalid:"
                )
                for item in validation.errors
            )
        )

    def test_scorer_cannot_self_rebind_provider_response_digest(self) -> None:
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        replacement = sha256_ref({"different_provider_response": True})
        receipt["binding"]["terminal_event"][
            "provider_response_sha256"
        ] = replacement
        receipt["source_payload"]["terminal_event"][
            "provider_response_sha256"
        ] = replacement
        receipt["source_payload"]["provider_output"][
            "provider_response_sha256"
        ] = replacement
        _reattach_v2_scorer(self.result, self.bundle)

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                item.startswith("receipt-binding-mismatch:")
                for item in validation.errors
            )
        )

    def test_scorer_verdict_mutation_breaks_binding(self) -> None:
        self.result["records"][0]["arms"][0]["task_results"][0][
            "task_success"
        ] = False

        validation = self.validate()

        self.assertFalse(validation.content_consistent)
        self.assertTrue(
            any(
                item.startswith("receipt-binding-mismatch:")
                for item in validation.errors
            )
        )

    def test_v2_bundle_rejects_legacy_scorer_receipt(self) -> None:
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "scorer"
        )
        receipt["schema_version"] = RECEIPT_SCHEMA
        _reattach_v2_scorer(self.result, self.bundle)

        with self.assertRaisesRegex(VerificationError, "schema_version differs"):
            ReceiptStore.from_object(self.bundle)

    def test_v2_bundle_rejects_legacy_usage_receipt(self) -> None:
        receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "usage"
        )
        receipt["schema_version"] = RECEIPT_SCHEMA

        with self.assertRaisesRegex(VerificationError, "schema_version differs"):
            ReceiptStore.from_object(self.bundle)

    def test_local_null_response_is_content_only_not_claim_complete(self) -> None:
        event = self.result["records"][0]["arms"][0]["events"][0]
        event["phase"] = "sender"
        self.result["records"][0]["arms"][0]["task_results"] = []
        usage_receipt = next(
            item for item in self.bundle["receipts"] if item["kind"] == "usage"
        )
        usage_receipt["binding"]["phase"] = "sender"
        usage_source = usage_receipt["source_payload"]
        usage_source.update(
            {
                "source_kind": "deterministic-local",
                "request_id": None,
                "response_id": None,
                "model_id": None,
                "settings_sha256": None,
                "provider_response_sha256": None,
                "provider_terminal_status": None,
            }
        )
        usage_receipt["source_sha256"] = sha256_ref(usage_source)
        event["usage_receipt_sha256"] = sha256_ref(usage_receipt)
        self.bundle["receipts"] = [usage_receipt]

        validation = self.validate()

        self.assertTrue(validation.content_consistent)
        self.assertFalse(validation.scorer_output_binding_complete)
        self.assertFalse(validation.complete)


if __name__ == "__main__":
    unittest.main()
