"""Receipt provenance tests; all fixtures remain synthetic test data."""

from __future__ import annotations

from copy import deepcopy
import unittest

from initial_goal_eval.contract import ARMS, VerificationError, sha256_ref
from initial_goal_eval.receipt_store import (
    RECEIPT_BUNDLE_SCHEMA,
    RECEIPT_SCHEMA,
    ReceiptStore,
)
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture
from initial_goal_eval.verifier import verify_result


def _receipt(
    *,
    kind: str,
    issuer_id: str,
    binding: dict[str, object],
    source_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": RECEIPT_SCHEMA,
        "kind": kind,
        "issuer_id": issuer_id,
        "binding": binding,
        "source_payload": source_payload,
        "source_sha256": sha256_ref(source_payload),
    }


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
        self.assertTrue(receipt["complete"])
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
        self.assertTrue(validation.complete)

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


if __name__ == "__main__":
    unittest.main()
