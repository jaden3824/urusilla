"""Strict signed-accountability boundary for real initial-goal evidence.

This module verifies canonical Ed25519 signatures over a preregistered plan
statement and one result/receipt handoff statement.  It proves only that keys
trusted by an out-of-band verifier policy approved the exact bytes and declared
roles.  It does not make a provider sign an API response, prove that a person or
organization is genuinely independent, or replay a provider-specific usage
normalizer.  Those facts remain responsibilities of the trust-policy operator
and the named witnesses.

The dependency-free runtime never imports this module.  Verification of a real
signed handoff requires the optional ``evidence-auth`` dependency.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .contract import (
    VerificationError,
    _boolean,
    _count,
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
)


TRUST_POLICY_SCHEMA = "urusilla-initial-goal-auth-trust-policy/1"
AUTHENTICATION_ENVELOPE_SCHEMA = "urusilla-initial-goal-auth-envelope/1"
PREREGISTRATION_STATEMENT_SCHEMA = (
    "urusilla-initial-goal-auth-preregistration-statement/1"
)
EVIDENCE_STATEMENT_SCHEMA = "urusilla-initial-goal-auth-evidence-statement/1"
PROVIDER_CAPTURE_REPORT_SCHEMA = (
    "urusilla-initial-goal-auth-provider-capture-report/1"
)
NORMALIZATION_REPORT_SCHEMA = "urusilla-initial-goal-auth-normalization-report/1"
SIGNATURE_SCHEMA = "urusilla-initial-goal-auth-signature/1"
AUTHENTICATION_BOUNDARY = "signed-accountability-not-provider-or-independence-proof"
SIGNATURE_DOMAIN = b"urusilla-initial-goal-auth-ed25519-v1\x00"
ALGORITHM = "ed25519"

ROLES = (
    "preregistration-authority",
    "operator",
    "boundary-auditor",
    "provider-witness",
    "normalizer-auditor",
)
SCOPES = ("preregistration", "evidence")
GLOBAL_EVIDENCE_ROLES = ("provider-witness", "normalizer-auditor")
MAX_KEYS = 512
MAX_SIGNATURES = 16_384


__all__ = [
    "ALGORITHM",
    "AUTHENTICATION_BOUNDARY",
    "AUTHENTICATION_ENVELOPE_SCHEMA",
    "EVIDENCE_STATEMENT_SCHEMA",
    "NORMALIZATION_REPORT_SCHEMA",
    "PREREGISTRATION_STATEMENT_SCHEMA",
    "PROVIDER_CAPTURE_REPORT_SCHEMA",
    "ROLES",
    "SCOPES",
    "SIGNATURE_SCHEMA",
    "TRUST_POLICY_SCHEMA",
    "AuthenticationValidation",
    "signature_message",
    "validate_authenticated_provenance",
]


def _utc(value: Any, path: str) -> datetime:
    if type(value) is not str:
        raise VerificationError(f"{path} must be a UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise VerificationError(
            f"{path} must use canonical YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    return parsed


def _canonical_base64(value: Any, length: int, path: str) -> bytes:
    if type(value) is not str or not value:
        raise VerificationError(f"{path} must be canonical Base64 text")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise VerificationError(f"{path} is not valid Base64") from exc
    if len(raw) != length or base64.b64encode(raw).decode("ascii") != value:
        raise VerificationError(f"{path} is not canonical {length}-byte Base64")
    return raw


def signature_message(
    *,
    scope: str,
    role: str,
    session_id: str | None,
    key_id: str,
    principal_id: str,
    statement: Mapping[str, Any],
) -> bytes:
    """Return the exact domain-separated bytes an external signer approves."""

    if scope not in SCOPES:
        raise VerificationError("signature scope is invalid")
    if role not in ROLES:
        raise VerificationError("signature role is invalid")
    if session_id is not None:
        _identifier(session_id, "signature session_id")
    _identifier(key_id, "signature key_id")
    _identifier(principal_id, "signature principal_id")
    subject = _object(statement, "signature statement")
    value = {
        "schema_version": SIGNATURE_SCHEMA,
        "scope": scope,
        "role": role,
        "session_id": session_id,
        "key_id": key_id,
        "principal_id": principal_id,
        "statement": subject,
    }
    return SIGNATURE_DOMAIN + canonical_json(value).encode("utf-8")


def _verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:
        raise VerificationError(
            "signed evidence requires the optional evidence-auth dependency"
        ) from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except InvalidSignature as exc:
        raise VerificationError("authentication signature is invalid") from exc
    except ValueError as exc:
        raise VerificationError("authentication public key is invalid") from exc


@dataclass(frozen=True)
class AuthenticationValidation:
    complete: bool
    signed_accountability_complete: bool
    trust_policy_sha256: str
    envelope_sha256: str
    preregistration_statement_signature_verified: bool
    session_signatures_verified: int
    provider_capture_attested: bool
    provider_normalization_attested: bool
    provider_records_attested: int
    signer_principals: int

    def to_object(self) -> dict[str, Any]:
        return {
            "required": True,
            "supplied": True,
            "complete": self.complete,
            "signed_accountability_complete": (
                self.signed_accountability_complete
            ),
            "mechanism": "ed25519-signed-accountability-v1",
            "evidence_boundary": AUTHENTICATION_BOUNDARY,
            "trust_policy_sha256": self.trust_policy_sha256,
            "envelope_sha256": self.envelope_sha256,
            "preregistration_statement_signature_verified": (
                self.preregistration_statement_signature_verified
            ),
            "external_timestamp_anchor_verified": False,
            "execution_after_preregistration_verified": False,
            "session_signatures_verified": self.session_signatures_verified,
            "provider_capture_attested": self.provider_capture_attested,
            "provider_normalization_attested": (
                self.provider_normalization_attested
            ),
            "provider_records_attested": self.provider_records_attested,
            "signer_principals": self.signer_principals,
            "operational_independence_cryptographically_proven": False,
            "provider_origin_cryptographically_proven": False,
            "provider_normalization_replayed_by_verifier": False,
            "separate_trust_policy_pin_matched": True,
            "trust_policy_out_of_band_origin_cryptographically_proven": False,
            "envelope_local_signature_replay_checked": True,
            "global_replay_registry_checked": False,
            "errors": [
                "execution-after-preregistration-not-established",
                "provider-origin-authentication-not-established",
                "provider-normalizer-replay-not-established",
                "global-replay-reservation-not-established",
            ],
            "limitations": [
                "signatures prove approval of exact bytes, not real-world identity",
                "the preregistration timestamp is a signer assertion, not an external time anchor",
                "a separate expected policy digest is matched, but its independent origin is a caller responsibility",
                "organizational independence is asserted by the verifier trust policy",
                "provider and normalization facts are witness attestations, not provider signatures",
                "the verifier does not replay provider-specific normalizer code",
                "signature replay is checked only inside one envelope, not across submissions",
            ],
        }


def _validate_trust_policy(
    value: Any,
    *,
    study_id: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], datetime, datetime]:
    policy = _object(value, "authentication trust_policy")
    _exact(
        policy,
        {
            "schema_version",
            "policy_id",
            "study_id",
            "project_organization_id",
            "created_at_utc",
            "expires_at_utc",
            "allowed_normalizer_manifest_sha256s",
            "keys",
        },
        "authentication trust_policy",
    )
    if policy["schema_version"] != TRUST_POLICY_SCHEMA:
        raise VerificationError("authentication trust policy schema differs")
    _identifier(policy["policy_id"], "authentication trust_policy.policy_id")
    if policy["study_id"] != study_id:
        raise VerificationError("authentication trust policy study differs")
    project_organization_id = _identifier(
        policy["project_organization_id"],
        "authentication trust_policy.project_organization_id",
    )
    created = _utc(
        policy["created_at_utc"], "authentication trust_policy.created_at_utc"
    )
    expires = _utc(
        policy["expires_at_utc"], "authentication trust_policy.expires_at_utc"
    )
    if created >= expires:
        raise VerificationError("authentication trust policy validity is empty")
    normalizers = _list(
        policy["allowed_normalizer_manifest_sha256s"],
        "authentication trust_policy.allowed_normalizer_manifest_sha256s",
    )
    if not normalizers:
        raise VerificationError("authentication trust policy allows no normalizer")
    normalized_normalizers = [
        _sha(item, f"authentication trust_policy normalizer[{index}]")
        for index, item in enumerate(normalizers)
    ]
    if len(set(normalized_normalizers)) != len(normalized_normalizers):
        raise VerificationError("authentication trust policy repeats a normalizer")

    raw_keys = _list(policy["keys"], "authentication trust_policy.keys")
    if not raw_keys or len(raw_keys) > MAX_KEYS:
        raise VerificationError("authentication trust policy key count is invalid")
    keys: dict[str, dict[str, Any]] = {}
    public_keys: set[bytes] = set()
    principal_organizations: dict[str, str] = {}
    for index, raw in enumerate(raw_keys):
        path = f"authentication trust_policy.keys[{index}]"
        key = _object(raw, path)
        _exact(
            key,
            {
                "key_id",
                "principal_id",
                "organization_id",
                "role",
                "algorithm",
                "public_key_base64",
                "valid_from_utc",
                "valid_until_utc",
                "revoked",
            },
            path,
        )
        key_id = _identifier(key["key_id"], f"{path}.key_id")
        principal_id = _identifier(key["principal_id"], f"{path}.principal_id")
        organization_id = _identifier(
            key["organization_id"], f"{path}.organization_id"
        )
        if key_id in keys:
            raise VerificationError("authentication trust policy repeats a key ID")
        prior_organization = principal_organizations.setdefault(
            principal_id, organization_id
        )
        if prior_organization != organization_id:
            raise VerificationError(
                "one authentication principal belongs to multiple organizations"
            )
        if key["role"] not in ROLES or key["algorithm"] != ALGORITHM:
            raise VerificationError(f"{path} role or algorithm is unsupported")
        public_key = _canonical_base64(
            key["public_key_base64"], 32, f"{path}.public_key_base64"
        )
        if public_key in public_keys:
            raise VerificationError("authentication public key is reused by another ID")
        public_keys.add(public_key)
        valid_from = _utc(key["valid_from_utc"], f"{path}.valid_from_utc")
        valid_until = _utc(key["valid_until_utc"], f"{path}.valid_until_utc")
        if valid_from >= valid_until:
            raise VerificationError(f"{path} validity is empty")
        revoked = _boolean(key["revoked"], f"{path}.revoked")
        keys[key_id] = {
            "key_id": key_id,
            "principal_id": principal_id,
            "organization_id": organization_id,
            "role": key["role"],
            "public_key": public_key,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "revoked": revoked,
        }
    detached = {
        **policy,
        "allowed_normalizer_manifest_sha256s": normalized_normalizers,
    }
    return detached, keys, created, expires


def _validate_preregistration(
    value: Any,
    *,
    study_id: str,
    plan_sha256: str,
    verifier_sha256: str,
    trust_policy_sha256: str,
) -> tuple[dict[str, Any], datetime]:
    statement = _object(value, "authentication preregistration")
    _exact(
        statement,
        {
            "schema_version",
            "study_id",
            "plan_sha256",
            "verifier_bundle_sha256",
            "trust_policy_sha256",
            "normalizer_manifest_sha256",
            "authority_principal_id",
            "anchor_nonce",
            "anchored_at_utc",
        },
        "authentication preregistration",
    )
    if statement["schema_version"] != PREREGISTRATION_STATEMENT_SCHEMA:
        raise VerificationError("authentication preregistration schema differs")
    if (
        statement["study_id"] != study_id
        or statement["plan_sha256"] != plan_sha256
        or statement["verifier_bundle_sha256"] != verifier_sha256
        or statement["trust_policy_sha256"] != trust_policy_sha256
    ):
        raise VerificationError("authentication preregistration binding differs")
    _sha(
        statement["normalizer_manifest_sha256"],
        "authentication preregistration.normalizer_manifest_sha256",
    )
    _identifier(
        statement["authority_principal_id"],
        "authentication preregistration.authority_principal_id",
    )
    _identifier(
        statement["anchor_nonce"],
        "authentication preregistration.anchor_nonce",
    )
    anchored = _utc(
        statement["anchored_at_utc"],
        "authentication preregistration.anchored_at_utc",
    )
    return dict(statement), anchored


def _validate_evidence_statement(
    value: Any,
    *,
    study_id: str,
    plan_sha256: str,
    result_sha256: str,
    receipt_bundle_sha256: str,
    verifier_sha256: str,
    trust_policy_sha256: str,
    normalizer_manifest_sha256: str,
    provider_record_count: int,
) -> tuple[dict[str, Any], datetime, str, str]:
    statement = _object(value, "authentication evidence")
    _exact(
        statement,
        {
            "schema_version",
            "study_id",
            "plan_sha256",
            "result_sha256",
            "receipt_bundle_sha256",
            "verifier_bundle_sha256",
            "trust_policy_sha256",
            "normalizer_manifest_sha256",
            "provider_capture_report",
            "normalization_report",
            "handoff_nonce",
            "observed_at_utc",
        },
        "authentication evidence",
    )
    if statement["schema_version"] != EVIDENCE_STATEMENT_SCHEMA:
        raise VerificationError("authentication evidence schema differs")
    expected = {
        "study_id": study_id,
        "plan_sha256": plan_sha256,
        "result_sha256": result_sha256,
        "receipt_bundle_sha256": receipt_bundle_sha256,
        "verifier_bundle_sha256": verifier_sha256,
        "trust_policy_sha256": trust_policy_sha256,
        "normalizer_manifest_sha256": normalizer_manifest_sha256,
    }
    if any(statement[field] != expected[field] for field in expected):
        raise VerificationError("authentication evidence binding differs")
    observed = _utc(
        statement["observed_at_utc"], "authentication evidence.observed_at_utc"
    )
    _identifier(statement["handoff_nonce"], "authentication evidence.handoff_nonce")

    capture = _object(
        statement["provider_capture_report"],
        "authentication evidence.provider_capture_report",
    )
    _exact(
        capture,
        {
            "schema_version",
            "receipt_bundle_sha256",
            "witness_principal_id",
            "records_witnessed",
            "unknown_records",
            "status",
        },
        "authentication evidence.provider_capture_report",
    )
    if capture["schema_version"] != PROVIDER_CAPTURE_REPORT_SCHEMA:
        raise VerificationError("authentication provider capture schema differs")
    witness = _identifier(
        capture["witness_principal_id"],
        "authentication provider witness principal",
    )
    witnessed = _count(capture["records_witnessed"], "provider records witnessed")
    unknown_capture = _count(capture["unknown_records"], "unknown provider records")
    if (
        capture["receipt_bundle_sha256"] != receipt_bundle_sha256
        or capture["status"] != "pass"
        or witnessed != provider_record_count
        or unknown_capture != 0
        or provider_record_count <= 0
    ):
        raise VerificationError("authentication provider capture report is incomplete")

    normalization = _object(
        statement["normalization_report"],
        "authentication evidence.normalization_report",
    )
    _exact(
        normalization,
        {
            "schema_version",
            "receipt_bundle_sha256",
            "normalizer_manifest_sha256",
            "auditor_principal_id",
            "records_validated",
            "unknown_records",
            "status",
        },
        "authentication evidence.normalization_report",
    )
    if normalization["schema_version"] != NORMALIZATION_REPORT_SCHEMA:
        raise VerificationError("authentication normalization report schema differs")
    normalizer_auditor = _identifier(
        normalization["auditor_principal_id"],
        "authentication normalizer auditor principal",
    )
    validated = _count(
        normalization["records_validated"], "normalized provider records"
    )
    unknown_normalization = _count(
        normalization["unknown_records"], "unknown normalized records"
    )
    if (
        normalization["receipt_bundle_sha256"] != receipt_bundle_sha256
        or normalization["normalizer_manifest_sha256"]
        != normalizer_manifest_sha256
        or normalization["status"] != "pass"
        or validated != provider_record_count
        or unknown_normalization != 0
    ):
        raise VerificationError("authentication normalization report is incomplete")
    return dict(statement), observed, witness, normalizer_auditor


def validate_authenticated_provenance(
    *,
    plan_value: Any,
    result_value: Any,
    receipt_bundle_sha256: str,
    provider_record_count: int,
    verifier_bundle_sha256: str,
    expected_trust_policy_sha256: str,
    trust_policy_value: Any,
    envelope_value: Any,
) -> AuthenticationValidation:
    """Validate one signed external handoff under an out-of-band trust policy."""

    plan = _object(plan_value, "authentication plan")
    result = _object(result_value, "authentication result")
    study_id = _identifier(plan.get("study_id"), "authentication plan.study_id")
    if result.get("study_id") != study_id:
        raise VerificationError("authentication result study differs")
    plan_sha256 = sha256_ref(plan)
    result_sha256 = sha256_ref(result)
    _sha(receipt_bundle_sha256, "authentication receipt_bundle_sha256")
    _sha(verifier_bundle_sha256, "authentication verifier_bundle_sha256")
    _sha(
        expected_trust_policy_sha256,
        "authentication expected_trust_policy_sha256",
    )
    if type(provider_record_count) is not int or provider_record_count <= 0:
        raise VerificationError("authentication provider record count is invalid")

    policy, keys, policy_created, policy_expires = _validate_trust_policy(
        trust_policy_value, study_id=study_id
    )
    policy_sha256 = sha256_ref(policy)
    if policy_sha256 != expected_trust_policy_sha256:
        raise VerificationError(
            "authentication trust policy differs from the out-of-band pin"
        )
    envelope = _object(envelope_value, "authentication envelope")
    _exact(
        envelope,
        {
            "schema_version",
            "evidence_boundary",
            "trust_policy_sha256",
            "preregistration",
            "evidence",
            "signatures",
        },
        "authentication envelope",
    )
    if envelope["schema_version"] != AUTHENTICATION_ENVELOPE_SCHEMA:
        raise VerificationError("authentication envelope schema differs")
    if envelope["evidence_boundary"] != AUTHENTICATION_BOUNDARY:
        raise VerificationError("authentication envelope boundary differs")
    if envelope["trust_policy_sha256"] != policy_sha256:
        raise VerificationError("authentication envelope trust policy differs")

    preregistration, anchored = _validate_preregistration(
        envelope["preregistration"],
        study_id=study_id,
        plan_sha256=plan_sha256,
        verifier_sha256=verifier_bundle_sha256,
        trust_policy_sha256=policy_sha256,
    )
    normalizer_manifest_sha256 = preregistration[
        "normalizer_manifest_sha256"
    ]
    if normalizer_manifest_sha256 not in policy[
        "allowed_normalizer_manifest_sha256s"
    ]:
        raise VerificationError("authentication normalizer is not trusted")
    evidence, observed, witness, normalizer_auditor = _validate_evidence_statement(
        envelope["evidence"],
        study_id=study_id,
        plan_sha256=plan_sha256,
        result_sha256=result_sha256,
        receipt_bundle_sha256=receipt_bundle_sha256,
        verifier_sha256=verifier_bundle_sha256,
        trust_policy_sha256=policy_sha256,
        normalizer_manifest_sha256=normalizer_manifest_sha256,
        provider_record_count=provider_record_count,
    )
    if not (policy_created <= anchored < observed <= policy_expires):
        raise VerificationError("authentication chronology is outside policy validity")

    raw_sessions = _list(plan.get("sessions"), "authentication plan.sessions")
    planned: dict[str, tuple[str, str]] = {}
    for index, raw_session in enumerate(raw_sessions):
        path = f"authentication plan.sessions[{index}]"
        session = _object(raw_session, path)
        session_id = _identifier(session.get("session_id"), f"{path}.session_id")
        operator_id = _identifier(session.get("operator_id"), f"{path}.operator_id")
        auditor_id = _identifier(
            session.get("boundary_auditor_id"), f"{path}.boundary_auditor_id"
        )
        if session_id in planned or operator_id == auditor_id:
            raise VerificationError("authentication session identity is invalid")
        planned[session_id] = (operator_id, auditor_id)
    if not planned:
        raise VerificationError("authentication plan contains no sessions")

    required: dict[tuple[str, str, str | None], str] = {
        ("preregistration", "preregistration-authority", None): preregistration[
            "authority_principal_id"
        ],
        ("evidence", "provider-witness", None): witness,
        ("evidence", "normalizer-auditor", None): normalizer_auditor,
    }
    for session_id, (operator_id, auditor_id) in planned.items():
        required[("evidence", "operator", session_id)] = operator_id
        required[("evidence", "boundary-auditor", session_id)] = auditor_id

    raw_signatures = _list(
        envelope["signatures"], "authentication envelope.signatures"
    )
    if not raw_signatures or len(raw_signatures) > MAX_SIGNATURES:
        raise VerificationError("authentication signature count is invalid")
    observed_signatures: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    signature_bytes_seen: set[bytes] = set()
    used_principals: set[str] = set()
    used_organizations: dict[str, str] = {}
    for index, raw in enumerate(raw_signatures):
        path = f"authentication envelope.signatures[{index}]"
        signature_entry = _object(raw, path)
        _exact(
            signature_entry,
            {
                "schema_version",
                "scope",
                "role",
                "session_id",
                "key_id",
                "principal_id",
                "signature_base64",
            },
            path,
        )
        if signature_entry["schema_version"] != SIGNATURE_SCHEMA:
            raise VerificationError(f"{path}.schema_version differs")
        scope = signature_entry["scope"]
        role = signature_entry["role"]
        session_id = signature_entry["session_id"]
        if scope not in SCOPES or role not in ROLES:
            raise VerificationError(f"{path} scope or role is invalid")
        if session_id is not None:
            _identifier(session_id, f"{path}.session_id")
        required_key = (scope, role, session_id)
        expected_principal = required.get(required_key)
        if expected_principal is None or required_key in observed_signatures:
            raise VerificationError("authentication signature is extra or duplicated")
        key_id = _identifier(signature_entry["key_id"], f"{path}.key_id")
        principal_id = _identifier(
            signature_entry["principal_id"], f"{path}.principal_id"
        )
        key = keys.get(key_id)
        if (
            key is None
            or key["revoked"]
            or key["role"] != role
            or key["principal_id"] != principal_id
            or principal_id != expected_principal
        ):
            raise VerificationError("authentication signature key or principal differs")
        signed_time = anchored if scope == "preregistration" else observed
        if not (key["valid_from"] <= signed_time <= key["valid_until"]):
            raise VerificationError("authentication signature key is outside validity")
        signature = _canonical_base64(
            signature_entry["signature_base64"], 64, f"{path}.signature_base64"
        )
        if signature in signature_bytes_seen:
            raise VerificationError("authentication signature bytes are replayed")
        signature_bytes_seen.add(signature)
        statement = preregistration if scope == "preregistration" else evidence
        _verify_ed25519(
            key["public_key"],
            signature,
            signature_message(
                scope=scope,
                role=role,
                session_id=session_id,
                key_id=key_id,
                principal_id=principal_id,
                statement=statement,
            ),
        )
        observed_signatures[required_key] = dict(signature_entry)
        used_principals.add(principal_id)
        used_organizations[principal_id] = key["organization_id"]
    if set(observed_signatures) != set(required):
        raise VerificationError("authentication required signatures are incomplete")

    project_organization = policy["project_organization_id"]
    operator_principals = {operator for operator, _auditor in planned.values()}
    auditor_principals = {auditor for _operator, auditor in planned.values()}
    operator_organizations = {
        used_organizations[principal] for principal in operator_principals
    }
    auditor_organizations = {
        used_organizations[principal] for principal in auditor_principals
    }
    if (
        project_organization in operator_organizations
        or len(operator_organizations) < 2
    ):
        raise VerificationError(
            "authentication operators are not separated from the project"
        )
    for operator, auditor in planned.values():
        if (
            used_organizations[operator] == used_organizations[auditor]
            or used_organizations[auditor] == project_organization
        ):
            raise VerificationError(
                "authentication boundary auditor is not organization-separated"
            )
    special_principals = {
        preregistration["authority_principal_id"],
        witness,
        normalizer_auditor,
    }
    if len(special_principals) != 3:
        raise VerificationError("authentication special roles share a principal")
    special_organizations = {
        used_organizations[principal] for principal in special_principals
    }
    if (
        len(special_organizations) != 3
        or project_organization in special_organizations
        or special_organizations & (
            operator_organizations | auditor_organizations
        )
    ):
        raise VerificationError(
            "authentication special roles are not organization-separated"
        )

    return AuthenticationValidation(
        complete=False,
        signed_accountability_complete=True,
        trust_policy_sha256=policy_sha256,
        envelope_sha256=sha256_ref(envelope),
        preregistration_statement_signature_verified=True,
        session_signatures_verified=2 * len(planned),
        provider_capture_attested=True,
        provider_normalization_attested=True,
        provider_records_attested=provider_record_count,
        signer_principals=len(used_principals),
    )
