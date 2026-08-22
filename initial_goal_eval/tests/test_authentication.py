"""Mutation tests for the signed external-handoff accountability boundary."""

from __future__ import annotations

import base64
from copy import deepcopy
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from initial_goal_eval.authentication import (
    ALGORITHM,
    AUTHENTICATION_BOUNDARY,
    AUTHENTICATION_ENVELOPE_SCHEMA,
    EVIDENCE_STATEMENT_SCHEMA,
    NORMALIZATION_REPORT_SCHEMA,
    PREREGISTRATION_STATEMENT_SCHEMA,
    PROVIDER_CAPTURE_REPORT_SCHEMA,
    SIGNATURE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    AuthenticationValidation,
    signature_message,
    validate_authenticated_provenance,
)
from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.receipt_store import (
    RECEIPT_BUNDLE_SCHEMA_V3,
    ReceiptValidation,
)
from initial_goal_eval.tests.test_verifier import build_synthetic_fixture
from initial_goal_eval.verifier import verify_result


STUDY_ID = "signed-study"
RECEIPT_SHA = sha256_ref({"receipt-bundle": "exact-v3"})
VERIFIER_SHA = sha256_ref({"verifier": "exact"})
NORMALIZER_SHA = sha256_ref({"normalizer-manifest": "frozen"})
PROVIDER_RECORDS = 8


def _private(index: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)


def _key_entry(
    key_id: str,
    principal_id: str,
    organization_id: str,
    role: str,
    private_key: Ed25519PrivateKey,
) -> dict[str, object]:
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "key_id": key_id,
        "principal_id": principal_id,
        "organization_id": organization_id,
        "role": role,
        "algorithm": ALGORITHM,
        "public_key_base64": base64.b64encode(public).decode("ascii"),
        "valid_from_utc": "2026-01-01T00:00:00Z",
        "valid_until_utc": "2027-01-01T00:00:00Z",
        "revoked": False,
    }


def _fixture() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, Ed25519PrivateKey],
]:
    plan = {
        "study_id": STUDY_ID,
        "sessions": [
            {
                "session_id": "session-one",
                "operator_id": "operator-one",
                "boundary_auditor_id": "auditor-one",
            },
            {
                "session_id": "session-two",
                "operator_id": "operator-two",
                "boundary_auditor_id": "auditor-two",
            },
        ],
    }
    result = {"study_id": STUDY_ID, "records": ["opaque-result-content"]}
    identities = (
        ("key-anchor", "anchor-one", "org-anchor", "preregistration-authority"),
        ("key-op-one", "operator-one", "org-operator-one", "operator"),
        ("key-op-two", "operator-two", "org-operator-two", "operator"),
        ("key-audit-one", "auditor-one", "org-auditor-one", "boundary-auditor"),
        ("key-audit-two", "auditor-two", "org-auditor-two", "boundary-auditor"),
        ("key-witness", "witness-one", "org-witness", "provider-witness"),
        ("key-normalizer", "normalizer-one", "org-normalizer", "normalizer-auditor"),
    )
    private_keys = {
        key_id: _private(index)
        for index, (key_id, _principal, _organization, _role) in enumerate(
            identities, start=1
        )
    }
    policy = {
        "schema_version": TRUST_POLICY_SCHEMA,
        "policy_id": "trust-policy-one",
        "study_id": STUDY_ID,
        "project_organization_id": "org-project",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "expires_at_utc": "2027-01-01T00:00:00Z",
        "allowed_normalizer_manifest_sha256s": [NORMALIZER_SHA],
        "keys": [
            _key_entry(
                key_id,
                principal,
                organization,
                role,
                private_keys[key_id],
            )
            for key_id, principal, organization, role in identities
        ],
    }
    policy_sha = sha256_ref(policy)
    preregistration = {
        "schema_version": PREREGISTRATION_STATEMENT_SCHEMA,
        "study_id": STUDY_ID,
        "plan_sha256": sha256_ref(plan),
        "verifier_bundle_sha256": VERIFIER_SHA,
        "trust_policy_sha256": policy_sha,
        "normalizer_manifest_sha256": NORMALIZER_SHA,
        "authority_principal_id": "anchor-one",
        "anchor_nonce": "anchor-nonce-one",
        "anchored_at_utc": "2026-08-01T00:00:00Z",
    }
    evidence = {
        "schema_version": EVIDENCE_STATEMENT_SCHEMA,
        "study_id": STUDY_ID,
        "plan_sha256": sha256_ref(plan),
        "result_sha256": sha256_ref(result),
        "receipt_bundle_sha256": RECEIPT_SHA,
        "verifier_bundle_sha256": VERIFIER_SHA,
        "trust_policy_sha256": policy_sha,
        "normalizer_manifest_sha256": NORMALIZER_SHA,
        "provider_capture_report": {
            "schema_version": PROVIDER_CAPTURE_REPORT_SCHEMA,
            "receipt_bundle_sha256": RECEIPT_SHA,
            "witness_principal_id": "witness-one",
            "records_witnessed": PROVIDER_RECORDS,
            "unknown_records": 0,
            "status": "pass",
        },
        "normalization_report": {
            "schema_version": NORMALIZATION_REPORT_SCHEMA,
            "receipt_bundle_sha256": RECEIPT_SHA,
            "normalizer_manifest_sha256": NORMALIZER_SHA,
            "auditor_principal_id": "normalizer-one",
            "records_validated": PROVIDER_RECORDS,
            "unknown_records": 0,
            "status": "pass",
        },
        "handoff_nonce": "handoff-nonce-one",
        "observed_at_utc": "2026-08-02T00:00:00Z",
    }
    envelope = {
        "schema_version": AUTHENTICATION_ENVELOPE_SCHEMA,
        "evidence_boundary": AUTHENTICATION_BOUNDARY,
        "trust_policy_sha256": policy_sha,
        "preregistration": preregistration,
        "evidence": evidence,
        "signatures": [],
    }
    _resign(envelope, private_keys)
    return plan, result, policy, envelope, private_keys


def _signature_specs(envelope: dict[str, object]):
    yield (
        "preregistration",
        "preregistration-authority",
        None,
        "key-anchor",
        "anchor-one",
    )
    yield "evidence", "provider-witness", None, "key-witness", "witness-one"
    yield (
        "evidence",
        "normalizer-auditor",
        None,
        "key-normalizer",
        "normalizer-one",
    )
    yield "evidence", "operator", "session-one", "key-op-one", "operator-one"
    yield "evidence", "boundary-auditor", "session-one", "key-audit-one", "auditor-one"
    yield "evidence", "operator", "session-two", "key-op-two", "operator-two"
    yield "evidence", "boundary-auditor", "session-two", "key-audit-two", "auditor-two"


def _resign(
    envelope: dict[str, object],
    private_keys: dict[str, Ed25519PrivateKey],
) -> None:
    signatures = []
    for scope, role, session_id, key_id, principal_id in _signature_specs(envelope):
        statement = envelope[
            "preregistration" if scope == "preregistration" else "evidence"
        ]
        signature = private_keys[key_id].sign(
            signature_message(
                scope=scope,
                role=role,
                session_id=session_id,
                key_id=key_id,
                principal_id=principal_id,
                statement=statement,
            )
        )
        signatures.append(
            {
                "schema_version": SIGNATURE_SCHEMA,
                "scope": scope,
                "role": role,
                "session_id": session_id,
                "key_id": key_id,
                "principal_id": principal_id,
                "signature_base64": base64.b64encode(signature).decode("ascii"),
            }
        )
    envelope["signatures"] = signatures


def _rebind_policy(
    policy: dict[str, object],
    envelope: dict[str, object],
    private_keys: dict[str, Ed25519PrivateKey],
) -> None:
    policy_sha = sha256_ref(policy)
    envelope["trust_policy_sha256"] = policy_sha
    envelope["preregistration"]["trust_policy_sha256"] = policy_sha
    envelope["evidence"]["trust_policy_sha256"] = policy_sha
    _resign(envelope, private_keys)


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        (
            self.plan,
            self.result,
            self.policy,
            self.envelope,
            self.private_keys,
        ) = _fixture()

    def validate(
        self,
        *,
        plan=None,
        result=None,
        policy=None,
        envelope=None,
        expected_policy_sha=None,
    ):
        return validate_authenticated_provenance(
            plan_value=plan or self.plan,
            result_value=result or self.result,
            receipt_bundle_sha256=RECEIPT_SHA,
            provider_record_count=PROVIDER_RECORDS,
            verifier_bundle_sha256=VERIFIER_SHA,
            expected_trust_policy_sha256=(
                expected_policy_sha or sha256_ref(self.policy)
            ),
            trust_policy_value=policy or self.policy,
            envelope_value=envelope or self.envelope,
        )

    def test_valid_handoff_verifies_bytes_but_not_real_world_independence(self):
        summary = self.validate().to_object()
        self.assertFalse(summary["complete"])
        self.assertTrue(summary["signed_accountability_complete"])
        self.assertTrue(
            summary["preregistration_statement_signature_verified"]
        )
        self.assertFalse(summary["external_timestamp_anchor_verified"])
        self.assertFalse(summary["execution_after_preregistration_verified"])
        self.assertTrue(summary["separate_trust_policy_pin_matched"])
        self.assertFalse(
            summary[
                "trust_policy_out_of_band_origin_cryptographically_proven"
            ]
        )
        self.assertFalse(summary["global_replay_registry_checked"])
        self.assertEqual(summary["session_signatures_verified"], 4)
        self.assertEqual(summary["provider_records_attested"], PROVIDER_RECORDS)
        self.assertFalse(summary["operational_independence_cryptographically_proven"])
        self.assertFalse(summary["provider_origin_cryptographically_proven"])
        self.assertFalse(summary["provider_normalization_replayed_by_verifier"])

    def test_signature_mutation_is_rejected(self):
        envelope = deepcopy(self.envelope)
        raw = base64.b64decode(envelope["signatures"][0]["signature_base64"])
        envelope["signatures"][0]["signature_base64"] = base64.b64encode(
            bytes([raw[0] ^ 1]) + raw[1:]
        ).decode("ascii")
        with self.assertRaisesRegex(VerificationError, "signature is invalid"):
            self.validate(envelope=envelope)

    def test_result_rebinding_is_rejected_before_signatures(self):
        result = deepcopy(self.result)
        result["records"].append("post-signed-mutation")
        with self.assertRaisesRegex(VerificationError, "evidence binding differs"):
            self.validate(result=result)

    def test_missing_or_replayed_signature_is_rejected(self):
        missing = deepcopy(self.envelope)
        missing["signatures"].pop()
        with self.assertRaisesRegex(VerificationError, "required signatures"):
            self.validate(envelope=missing)

        replayed = deepcopy(self.envelope)
        replayed["signatures"][1]["signature_base64"] = replayed["signatures"][0][
            "signature_base64"
        ]
        with self.assertRaisesRegex(VerificationError, "signature bytes are replayed"):
            self.validate(envelope=replayed)

    def test_untrusted_normalizer_is_rejected(self):
        envelope = deepcopy(self.envelope)
        foreign = sha256_ref({"normalizer": "not-in-trust-policy"})
        envelope["preregistration"]["normalizer_manifest_sha256"] = foreign
        envelope["evidence"]["normalizer_manifest_sha256"] = foreign
        envelope["evidence"]["normalization_report"][
            "normalizer_manifest_sha256"
        ] = foreign
        _resign(envelope, self.private_keys)
        with self.assertRaisesRegex(VerificationError, "normalizer is not trusted"):
            self.validate(envelope=envelope)

    def test_operator_organizations_must_be_independent_of_project_and_each_other(self):
        policy = deepcopy(self.policy)
        op_two = next(
            item for item in policy["keys"] if item["key_id"] == "key-op-two"
        )
        op_two["organization_id"] = "org-operator-one"
        envelope = deepcopy(self.envelope)
        _rebind_policy(policy, envelope, self.private_keys)
        with self.assertRaisesRegex(VerificationError, "operators are not separated"):
            self.validate(
                policy=policy,
                envelope=envelope,
                expected_policy_sha=sha256_ref(policy),
            )

    def test_operator_and_boundary_auditor_cannot_share_organization(self):
        policy = deepcopy(self.policy)
        auditor = next(
            item for item in policy["keys"] if item["key_id"] == "key-audit-one"
        )
        auditor["organization_id"] = "org-operator-one"
        envelope = deepcopy(self.envelope)
        _rebind_policy(policy, envelope, self.private_keys)
        with self.assertRaisesRegex(VerificationError, "boundary auditor"):
            self.validate(
                policy=policy,
                envelope=envelope,
                expected_policy_sha=sha256_ref(policy),
            )

    def test_preregistration_must_precede_observation(self):
        envelope = deepcopy(self.envelope)
        envelope["preregistration"]["anchored_at_utc"] = "2026-08-03T00:00:00Z"
        _resign(envelope, self.private_keys)
        with self.assertRaisesRegex(VerificationError, "chronology"):
            self.validate(envelope=envelope)

    def test_provider_and_normalization_reports_must_cover_every_record(self):
        envelope = deepcopy(self.envelope)
        envelope["evidence"]["normalization_report"]["records_validated"] -= 1
        _resign(envelope, self.private_keys)
        with self.assertRaisesRegex(VerificationError, "normalization report"):
            self.validate(envelope=envelope)

    def test_key_role_and_revocation_are_fail_closed(self):
        for mutation, expected in (("role", "key or principal"), ("revoked", "key or principal")):
            with self.subTest(mutation=mutation):
                policy = deepcopy(self.policy)
                key = next(
                    item for item in policy["keys"] if item["key_id"] == "key-op-one"
                )
                if mutation == "role":
                    key["role"] = "boundary-auditor"
                else:
                    key["revoked"] = True
                envelope = deepcopy(self.envelope)
                _rebind_policy(policy, envelope, self.private_keys)
                with self.assertRaisesRegex(VerificationError, expected):
                    self.validate(
                        policy=policy,
                        envelope=envelope,
                        expected_policy_sha=sha256_ref(policy),
                    )

    def test_evidence_producer_cannot_select_a_replacement_trust_policy(self):
        policy = deepcopy(self.policy)
        policy["policy_id"] = "attacker-selected-policy"
        envelope = deepcopy(self.envelope)
        _rebind_policy(policy, envelope, self.private_keys)
        with self.assertRaisesRegex(VerificationError, "out-of-band pin"):
            self.validate(policy=policy, envelope=envelope)


class VerifierAuthenticationIntegrationTests(unittest.TestCase):
    class CompleteV3Store:
        schema_version = RECEIPT_BUNDLE_SCHEMA_V3
        bundle_sha256 = RECEIPT_SHA
        provider_record_count = PROVIDER_RECORDS

        @staticmethod
        def validate(plan_value, result_value):
            return ReceiptValidation(
                content_consistent=True,
                scorer_output_binding_complete=True,
                provider_preimage_resolution_required=True,
                provider_preimage_resolution_complete=True,
                referenced=1,
                resolved=1,
                unreferenced=0,
                errors=(),
            )

    def setUp(self):
        self.plan, self.result = build_synthetic_fixture()
        self.plan["evidence_boundary"] = "real-independent-evaluation"
        self.result["plan_sha256"] = sha256_ref(self.plan)

    def test_signed_accountability_cannot_open_the_claim_gate(self):
        validation = AuthenticationValidation(
            complete=False,
            signed_accountability_complete=True,
            trust_policy_sha256=sha256_ref({"trusted": "policy"}),
            envelope_sha256=sha256_ref({"signed": "envelope"}),
            preregistration_statement_signature_verified=True,
            session_signatures_verified=48,
            provider_capture_attested=True,
            provider_normalization_attested=True,
            provider_records_attested=PROVIDER_RECORDS,
            signer_principals=7,
        )
        expected_pin = sha256_ref({"out-of-band": "trust-policy"})
        with patch(
            "initial_goal_eval.verifier.validate_authenticated_provenance",
            return_value=validation,
        ) as mocked:
            summary = verify_result(
                self.plan,
                self.result,
                receipt_store=self.CompleteV3Store(),
                trust_policy_value={"trusted": "policy"},
                authentication_envelope_value={"signed": "envelope"},
                expected_trust_policy_sha256=expected_pin,
            )
        self.assertTrue(summary["evidence_authentication"][
            "signed_accountability_complete"
        ])
        self.assertFalse(summary["evidence_authentication"]["complete"])
        self.assertFalse(summary["measurement_scope_complete"])
        self.assertFalse(summary["metric_gate_passed"])
        self.assertFalse(summary["goal_gate_passed"])
        self.assertIn(
            "authenticated-provenance-not-established",
            summary["gate_failures"],
        )
        self.assertEqual(
            mocked.call_args.kwargs["expected_trust_policy_sha256"],
            expected_pin,
        )

    def test_authentication_inputs_require_the_separate_pin(self):
        with self.assertRaisesRegex(VerificationError, "out-of-band pin"):
            verify_result(
                self.plan,
                self.result,
                receipt_store=self.CompleteV3Store(),
                trust_policy_value={"trusted": "policy"},
                authentication_envelope_value={"signed": "envelope"},
            )


if __name__ == "__main__":
    unittest.main()
