"""Local, opt-in, content-free telemetry for the neutral adoption kit.

The module deliberately does not perform network I/O. Events have an exact
allowlist, use UTC calendar-day buckets, carry a monthly rotating pseudonym,
and are authenticated with a deployment-local HMAC key. HMAC proves only that
the local holder of that key created the event; it is not public identity,
release provenance, or authorization.

Local evidence references and HMAC completion attestations are useful synthetic
or operational signals, but they do not prove independent external adoption.
This kit therefore reports verified external adoption impact as zero. Its
separately labeled synthetic metric counts only locally attested safe-completion
events. Downloads, repository activity, and installation claims are not event
inputs and cannot contribute to either metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "urusilla-adoption-telemetry/1"
AGGREGATE_VERSION = "urusilla-adoption-impact/2"
COMPLETION_ATTESTATION_VERSION = "urusilla-local-completion-attestation/1"
MIN_HMAC_KEY_BYTES = 32
DEFAULT_MAX_EVENTS_PER_DAY = 128
DEFAULT_PER_TYPE_LIMITS = {
    "profile_discovered": 2,
    "manifest_verified": 2,
    "negotiation_accepted": 2,
    "negotiation_rejected": 2,
    "fallback_succeeded": 8,
    "fallback_exhausted": 8,
    "safe_message_completed": 64,
    "message_failed": 64,
    "profile_disabled": 2,
}
MAX_PSEUDONYMS_PER_EVIDENCE_BUCKET = 2
MAX_IMPACT_MILLIUNITS_PER_EVIDENCE_BUCKET = 32_000

EVENT_TYPES = tuple(DEFAULT_PER_TYPE_LIMITS)
DEPLOYMENT_CLASSES = ("internal", "external", "test")
MODES = ("bridge", "native", "json_fallback", "terse_english_fallback")
OUTCOMES = ("observed", "succeeded", "failed", "abstained", "disabled")
REASON_CODES = (
    "UNSUPPORTED_EXTENSION",
    "MANIFEST_FETCH_FAILED",
    "MANIFEST_SIGNATURE_INVALID",
    "CAPSULE_DIGEST_MISMATCH",
    "SCHEMA_UNSUPPORTED",
    "CODEC_UNSUPPORTED",
    "POLICY_DENIED",
    "RIGHTS_SCOPE_DENIED",
    "RESOURCE_LIMIT",
    "SEMANTIC_VALIDATION_FAILED",
    "PROVENANCE_INVALID",
    "FRESHNESS_UNSATISFIED",
    "FALLBACK_EXHAUSTED",
    "TASK_FAILED",
    "PROFILE_DEPRECATED",
    "OPERATOR_DISABLED",
)
EVIDENCE_TIERS = (
    "local_hmac",
    "local_evidence_declared",
    "locally_attested_completion",
)
CLUSTER_FLAGS = (
    "shared_evidence_cluster",
    "signature_secret_epoch_fanout",
    "synchronized_activity_cluster",
)

_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "telemetry_opt_in",
        "event_type",
        "coarse_time_bucket",
        "rotating_install_pseudonym",
        "deployment_class",
        "implementation_version",
        "mode",
        "outcome",
        "reason_code",
        "public_profile_digest",
        "metric_buckets",
        "evidence_refs",
        "completion_attestation",
        "event_nonce",
        "sequence",
        "signature",
    }
)
_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "telemetry_opt_in",
        "event_type",
        "coarse_time_bucket",
        "rotating_install_pseudonym",
        "deployment_class",
        "implementation_version",
        "mode",
        "outcome",
        "event_nonce",
        "sequence",
    }
)
_METRIC_FIELDS = frozenset(
    {"cache_state", "wire_delta", "token_delta", "latency", "repair_turns"}
)
_METRIC_VALUES = {
    "cache_state": frozenset({"cold", "warm", "not_applicable"}),
    "wire_delta": frozenset(
        {
            "regressed",
            "neutral",
            "saved_lt256",
            "saved_256_1023",
            "saved_1024_plus",
            "not_measured",
        }
    ),
    "token_delta": frozenset(
        {
            "regressed",
            "neutral",
            "saved_lt32",
            "saved_32_127",
            "saved_128_plus",
            "not_measured",
        }
    ),
    "latency": frozenset(
        {"lt10ms", "10_99ms", "100_999ms", "gte1000ms", "not_measured"}
    ),
    "repair_turns": frozenset({"0", "1", "2_3", "4_plus", "not_measured"}),
}
_OUTCOMES_BY_EVENT = {
    "profile_discovered": frozenset({"observed"}),
    "manifest_verified": frozenset({"succeeded"}),
    "negotiation_accepted": frozenset({"succeeded"}),
    "negotiation_rejected": frozenset({"failed", "abstained"}),
    "fallback_succeeded": frozenset({"succeeded"}),
    "fallback_exhausted": frozenset({"failed", "abstained"}),
    "safe_message_completed": frozenset({"succeeded"}),
    "message_failed": frozenset({"failed", "abstained"}),
    "profile_disabled": frozenset({"disabled"}),
}
_INITIAL_MODES = frozenset({"bridge", "native"})
_FALLBACK_MODES = frozenset({"json_fallback", "terse_english_fallback"})
_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SIGNATURE_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
_PSEUDONYM_RE = re.compile(r"^rp1:([0-9]{4}-(?:0[1-9]|1[0-2])):([0-9a-f]{32})$")
_IMPLEMENTATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/-]{0,63}$")
_ISSUER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,31}$")
_RECEIPT_SEAL_KEY = secrets.token_bytes(32)


class TelemetryValidationError(ValueError):
    """Raised when an event fails closed without changing validator state."""


def _require_hmac_key(secret: bytes) -> bytes:
    if type(secret) is not bytes or len(secret) < MIN_HMAC_KEY_BYTES:
        raise TelemetryValidationError(
            f"HMAC secret must be bytes with at least {MIN_HMAC_KEY_BYTES} bytes"
        )
    return secret


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON for already validated simple values."""

    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def coarse_day_bucket(instant: datetime) -> str:
    """Return a UTC day bucket, rejecting naive datetimes."""

    if not isinstance(instant, datetime) or instant.tzinfo is None:
        raise TelemetryValidationError("instant must be a timezone-aware datetime")
    return instant.astimezone(timezone.utc).date().isoformat()


def derive_rotating_pseudonym(secret: bytes, month: str) -> str:
    """Derive a monthly installation pseudonym from a local secret.

    ``month`` is exactly ``YYYY-MM``. The HMAC domain is intentionally distinct
    from the event-signature domain.
    """

    secret = _require_hmac_key(secret)
    if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", month):
        raise TelemetryValidationError("month must have YYYY-MM form")
    token = hmac.new(
        secret,
        ("urusilla:pseudonym:v1|" + month).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"rp1:{month}:{token}"


def _parse_day_bucket(value: Any) -> date:
    if type(value) is not str or not re.fullmatch(
        r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:[0-2][0-9]|3[01])", value
    ):
        raise TelemetryValidationError("coarse_time_bucket must have YYYY-MM-DD form")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise TelemetryValidationError("coarse_time_bucket is not a calendar day") from exc
    if parsed.isoformat() != value:
        raise TelemetryValidationError("coarse_time_bucket is not canonical")
    return parsed


def _validate_digest(value: Any, field_name: str) -> None:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise TelemetryValidationError(f"{field_name} must be a lowercase SHA-256 ref")


def _validate_event_shape(event: Mapping[str, Any], *, require_signature: bool) -> None:
    if type(event) is not dict:
        raise TelemetryValidationError("event must be a plain JSON object")
    if any(type(key) is not str for key in event):
        raise TelemetryValidationError("event field names must be strings")
    unknown = set(event) - _ALLOWED_FIELDS
    if unknown:
        raise TelemetryValidationError(f"event contains non-allowlisted fields: {sorted(unknown)!r}")
    required = set(_REQUIRED_FIELDS)
    if require_signature:
        required.add("signature")
    missing = required - set(event)
    if missing:
        raise TelemetryValidationError(f"event is missing required fields: {sorted(missing)!r}")
    if not require_signature and "signature" in event:
        raise TelemetryValidationError("unsigned event must not already contain signature")

    if event["schema_version"] != SCHEMA_VERSION:
        raise TelemetryValidationError("unsupported telemetry schema_version")
    if event["telemetry_opt_in"] is not True:
        raise TelemetryValidationError("telemetry requires explicit deployment-owner opt-in")

    event_type = event["event_type"]
    if type(event_type) is not str or event_type not in EVENT_TYPES:
        raise TelemetryValidationError("event_type is not allowlisted")
    parsed_day = _parse_day_bucket(event["coarse_time_bucket"])

    pseudonym = event["rotating_install_pseudonym"]
    match = _PSEUDONYM_RE.fullmatch(pseudonym) if type(pseudonym) is str else None
    if not match:
        raise TelemetryValidationError("rotating_install_pseudonym has invalid form")
    if match.group(1) != parsed_day.isoformat()[:7]:
        raise TelemetryValidationError("pseudonym rotation month does not match day bucket")

    if event["deployment_class"] not in DEPLOYMENT_CLASSES:
        raise TelemetryValidationError("deployment_class is not allowlisted")
    implementation = event["implementation_version"]
    if type(implementation) is not str or not _IMPLEMENTATION_RE.fullmatch(implementation):
        raise TelemetryValidationError("implementation_version has invalid form")
    mode = event["mode"]
    if type(mode) is not str or mode not in MODES:
        raise TelemetryValidationError("mode is not allowlisted")
    outcome = event["outcome"]
    if type(outcome) is not str or outcome not in _OUTCOMES_BY_EVENT[event_type]:
        raise TelemetryValidationError("outcome is impossible for event_type")

    if event_type in {
        "profile_discovered",
        "manifest_verified",
        "negotiation_accepted",
        "negotiation_rejected",
    } and mode not in _INITIAL_MODES:
        raise TelemetryValidationError("negotiation lifecycle events require bridge or native mode")
    if event_type in {"fallback_succeeded", "fallback_exhausted"} and mode not in _FALLBACK_MODES:
        raise TelemetryValidationError("fallback events require an explicit fallback mode")

    reason = event.get("reason_code")
    needs_reason = outcome in {"failed", "abstained", "disabled"}
    if needs_reason:
        if type(reason) is not str or reason not in REASON_CODES:
            raise TelemetryValidationError("failed, abstained, or disabled event requires reason_code")
    elif "reason_code" in event:
        raise TelemetryValidationError("successful or observed event must not include reason_code")
    if event_type == "profile_disabled" and reason not in {
        "OPERATOR_DISABLED",
        "PROFILE_DEPRECATED",
    }:
        raise TelemetryValidationError("profile_disabled has an impossible reason_code")

    if "public_profile_digest" in event:
        _validate_digest(event["public_profile_digest"], "public_profile_digest")

    metrics = event.get("metric_buckets")
    if metrics is not None:
        if type(metrics) is not dict or set(metrics) != _METRIC_FIELDS:
            raise TelemetryValidationError("metric_buckets must contain exactly the bucket allowlist")
        for key in sorted(_METRIC_FIELDS):
            value = metrics[key]
            if type(value) is not str or value not in _METRIC_VALUES[key]:
                raise TelemetryValidationError(f"metric_buckets.{key} is not allowlisted")

    refs = event.get("evidence_refs")
    if refs is not None:
        if type(refs) is not dict or not refs or not set(refs) <= {
            "conformance",
            "crossplay",
        }:
            raise TelemetryValidationError("evidence_refs contains a non-allowlisted field")
        for key, value in refs.items():
            _validate_digest(value, f"evidence_refs.{key}")
        if "crossplay" in refs and "conformance" not in refs:
            raise TelemetryValidationError("crossplay evidence requires conformance evidence")

    attestation = event.get("completion_attestation")
    if attestation is not None:
        if event_type != "safe_message_completed" or outcome != "succeeded":
            raise TelemetryValidationError(
                "completion_attestation is allowed only on safe_message_completed"
            )
        if refs is None or "conformance" not in refs:
            raise TelemetryValidationError(
                "completion_attestation requires a conformance evidence reference"
            )
        if type(attestation) is not dict or set(attestation) != {
            "attestation_version",
            "issuer_id",
            "signature",
        }:
            raise TelemetryValidationError(
                "completion_attestation must contain exactly its structural allowlist"
            )
        if attestation["attestation_version"] != COMPLETION_ATTESTATION_VERSION:
            raise TelemetryValidationError("unsupported completion attestation version")
        issuer_id = attestation["issuer_id"]
        if type(issuer_id) is not str or not _ISSUER_ID_RE.fullmatch(issuer_id):
            raise TelemetryValidationError("completion attestation issuer_id has invalid form")
        attestation_signature = attestation["signature"]
        if (
            type(attestation_signature) is not str
            or not _SIGNATURE_RE.fullmatch(attestation_signature)
        ):
            raise TelemetryValidationError("completion attestation signature has invalid form")

    nonce = event["event_nonce"]
    if type(nonce) is not str or not _HEX32_RE.fullmatch(nonce):
        raise TelemetryValidationError("event_nonce must be 32 lowercase hexadecimal characters")
    sequence = event["sequence"]
    if type(sequence) is not int or not 0 <= sequence <= 0xFFFFFFFF:
        raise TelemetryValidationError("sequence must be a uint32")
    if require_signature:
        signature = event["signature"]
        if type(signature) is not str or not _SIGNATURE_RE.fullmatch(signature):
            raise TelemetryValidationError("signature has invalid form")


def _event_signature(secret: bytes, unsigned_event: Mapping[str, Any]) -> str:
    digest = hmac.new(
        secret,
        b"urusilla:event:v1\x00" + canonical_json_bytes(unsigned_event),
        hashlib.sha256,
    ).hexdigest()
    return "hmac-sha256:" + digest


def sign_event(unsigned_event: Mapping[str, Any], secret: bytes) -> dict[str, Any]:
    """Validate and sign an event locally without performing any I/O."""

    secret = _require_hmac_key(secret)
    _validate_event_shape(unsigned_event, require_signature=False)
    month = unsigned_event["coarse_time_bucket"][:7]
    expected = derive_rotating_pseudonym(secret, month)
    if unsigned_event["rotating_install_pseudonym"] != expected:
        raise TelemetryValidationError("pseudonym does not derive from the local HMAC secret")
    normalized = json.loads(canonical_json_bytes(unsigned_event))
    normalized["signature"] = _event_signature(secret, normalized)
    return normalized


def create_signed_event(
    *,
    secret: bytes,
    telemetry_opt_in: bool,
    event_type: str,
    coarse_time_bucket: str,
    deployment_class: str,
    implementation_version: str,
    mode: str,
    outcome: str,
    sequence: int,
    event_nonce: str | None = None,
    reason_code: str | None = None,
    public_profile_digest: str | None = None,
    metric_buckets: Mapping[str, str] | None = None,
    evidence_refs: Mapping[str, str] | None = None,
    completion_attestation: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a signed allowlisted event after explicit local opt-in."""

    if telemetry_opt_in is not True:
        raise TelemetryValidationError("telemetry is disabled unless opt-in is exactly true")
    month = _parse_day_bucket(coarse_time_bucket).isoformat()[:7]
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "telemetry_opt_in": True,
        "event_type": event_type,
        "coarse_time_bucket": coarse_time_bucket,
        "rotating_install_pseudonym": derive_rotating_pseudonym(secret, month),
        "deployment_class": deployment_class,
        "implementation_version": implementation_version,
        "mode": mode,
        "outcome": outcome,
        "event_nonce": event_nonce if event_nonce is not None else secrets.token_hex(16),
        "sequence": sequence,
    }
    if reason_code is not None:
        event["reason_code"] = reason_code
    if public_profile_digest is not None:
        event["public_profile_digest"] = public_profile_digest
    if metric_buckets is not None:
        event["metric_buckets"] = dict(metric_buckets)
    if evidence_refs is not None:
        event["evidence_refs"] = dict(evidence_refs)
    if completion_attestation is not None:
        event["completion_attestation"] = dict(completion_attestation)
    return sign_event(event, secret)


def _completion_attestation_binding(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "attestation_version": COMPLETION_ATTESTATION_VERSION,
        "coarse_time_bucket": event["coarse_time_bucket"],
        "event_nonce": event["event_nonce"],
        "event_type": event["event_type"],
        "evidence_refs": event.get("evidence_refs", {}),
        "implementation_version": event["implementation_version"],
        "mode": event["mode"],
        "outcome": event["outcome"],
        "rotating_install_pseudonym": event["rotating_install_pseudonym"],
        "sequence": event["sequence"],
    }


def _completion_attestation_signature(
    issuer_secret: bytes, event: Mapping[str, Any]
) -> str:
    issuer_secret = _require_hmac_key(issuer_secret)
    digest = hmac.new(
        issuer_secret,
        b"urusilla:local-completion-attestation:v1\x00"
        + canonical_json_bytes(_completion_attestation_binding(event)),
        hashlib.sha256,
    ).hexdigest()
    return "hmac-sha256:" + digest


def issue_local_completion_attestation(
    event: Mapping[str, Any], *, issuer_id: str, issuer_secret: bytes
) -> dict[str, str]:
    """Issue a content-free local/synthetic completion attestation.

    The attestation is bound to the nonce, implementation and evidence IDs,
    rotating pseudonym, UTC day, sequence, event type, mode, outcome, and
    attestation version. It is a local test/operations primitive and is never
    evidence of independent external adoption.
    """

    if type(issuer_id) is not str or not _ISSUER_ID_RE.fullmatch(issuer_id):
        raise TelemetryValidationError("completion issuer_id has invalid form")
    _require_hmac_key(issuer_secret)
    _validate_event_shape(event, require_signature=True)
    if "completion_attestation" in event:
        raise TelemetryValidationError("event already contains completion_attestation")
    if event["event_type"] != "safe_message_completed" or event["outcome"] != "succeeded":
        raise TelemetryValidationError("only a safe completed event may be attested")
    if "conformance" not in event.get("evidence_refs", {}):
        raise TelemetryValidationError("completion attestation requires conformance evidence")
    return {
        "attestation_version": COMPLETION_ATTESTATION_VERSION,
        "issuer_id": issuer_id,
        "signature": _completion_attestation_signature(issuer_secret, event),
    }


def attach_local_completion_attestation(
    event: Mapping[str, Any],
    *,
    event_secret: bytes,
    issuer_id: str,
    issuer_secret: bytes,
) -> dict[str, Any]:
    """Attach a local completion attestation and re-sign the outer event."""

    _validate_event_shape(event, require_signature=True)
    unsigned = {key: value for key, value in event.items() if key != "signature"}
    expected_outer_signature = _event_signature(event_secret, unsigned)
    if not hmac.compare_digest(event["signature"], expected_outer_signature):
        raise TelemetryValidationError("cannot attest an event with invalid outer HMAC")
    attestation = issue_local_completion_attestation(
        event,
        issuer_id=issuer_id,
        issuer_secret=issuer_secret,
    )
    unsigned["completion_attestation"] = attestation
    return sign_event(unsigned, event_secret)


class TrustedLocalCompletionIssuerRegistry:
    """Explicit local HMAC issuers accepted for synthetic completion checks.

    Creating this registry is a deployment-local trust choice. It cannot promote
    an event to independently verified external adoption, even when the event's
    self-declared deployment class is ``external``.
    """

    def __init__(self, issuers: Mapping[str, bytes] | None = None):
        self._issuers: dict[str, bytes] = {}
        for issuer_id, issuer_secret in (issuers or {}).items():
            if type(issuer_id) is not str or not _ISSUER_ID_RE.fullmatch(issuer_id):
                raise TelemetryValidationError("trusted local completion issuer_id is invalid")
            self._issuers[issuer_id] = _require_hmac_key(issuer_secret)

    def verify(self, event: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
        attestation = event.get("completion_attestation")
        if attestation is None:
            return False, ("completion_attestation_missing",)
        issuer_id = attestation["issuer_id"]
        issuer_secret = self._issuers.get(issuer_id)
        if issuer_secret is None:
            raise TelemetryValidationError("completion attestation issuer is not locally trusted")
        expected = _completion_attestation_signature(issuer_secret, event)
        if not hmac.compare_digest(attestation["signature"], expected):
            raise TelemetryValidationError("completion attestation binding or HMAC is invalid")
        return True, ()


class EvidenceRegistry:
    """A local declaration cache for public evidence references.

    Records in this caller-created object are never independently verified. The
    vocabulary intentionally has no ``verified`` or ``independent`` Boolean;
    such caller assertions are rejected. A match can produce only the
    ``local_evidence_declared`` tier and zero verified external impact.
    """

    def __init__(self, records: Mapping[str, Mapping[str, Any]] | None = None):
        self._records: dict[str, dict[str, Any]] = {}
        for reference, record in (records or {}).items():
            _validate_digest(reference, "evidence registry reference")
            if type(record) is not dict:
                raise TelemetryValidationError("evidence registry record must be a plain object")
            kind = record.get("kind")
            if kind == "conformance":
                required = {"kind", "implementation_version"}
                if set(record) != required:
                    raise TelemetryValidationError("invalid conformance evidence record")
            elif kind == "crossplay":
                required = {
                    "kind",
                    "implementation_version",
                    "conformance_ref",
                }
                if set(record) != required:
                    raise TelemetryValidationError("invalid crossplay evidence record")
                _validate_digest(record["conformance_ref"], "crossplay conformance_ref")
            else:
                raise TelemetryValidationError("unknown evidence registry record kind")
            implementation = record["implementation_version"]
            if type(implementation) is not str or not _IMPLEMENTATION_RE.fullmatch(implementation):
                raise TelemetryValidationError("evidence implementation_version has invalid form")
            self._records[reference] = dict(record)

    def classify(self, event: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
        refs = event.get("evidence_refs")
        if not refs:
            return "local_hmac", ()
        warnings: list[str] = []
        conformance_ref = refs.get("conformance")
        conformance = self._records.get(conformance_ref)
        if (
            conformance is None
            or conformance.get("kind") != "conformance"
            or conformance.get("implementation_version") != event["implementation_version"]
        ):
            warnings.append("conformance_evidence_not_locally_declared")
            return "local_hmac", tuple(warnings)
        tier = "local_evidence_declared"
        warnings.append("local_evidence_registry_is_not_independent_verification")
        crossplay_ref = refs.get("crossplay")
        if crossplay_ref is None:
            return tier, tuple(warnings)
        crossplay = self._records.get(crossplay_ref)
        if (
            crossplay is None
            or crossplay.get("kind") != "crossplay"
            or crossplay.get("implementation_version") != event["implementation_version"]
            or crossplay.get("conformance_ref") != conformance_ref
        ):
            warnings.append("crossplay_evidence_not_locally_declared")
            return tier, tuple(warnings)
        return tier, tuple(warnings)


@dataclass
class TelemetryState:
    """Mutable, local validation state; rejected events do not alter it."""

    seen_nonces: set[str] = field(default_factory=set)
    last_sequence: dict[str, int] = field(default_factory=dict)
    phases: dict[str, str] = field(default_factory=dict)
    active_modes: dict[str, str] = field(default_factory=dict)
    deployment_identity: dict[str, tuple[str, str]] = field(default_factory=dict)
    rate_counts: dict[tuple[str, str, str], int] = field(default_factory=dict)
    secret_epoch_pseudonyms: dict[tuple[str, str], str] = field(default_factory=dict)


class ValidationResult:
    """An opaque, process-local receipt for one accepted event.

    Receipts can be issued only by :func:`validate_event`. Their internal MAC
    binds the canonical event, evidence tier, warnings, and an epoch-scoped
    local-secret fingerprint. The fingerprint is not publicly exposed and
    changes every month. Receipts are deliberately not serializable evidence
    and become invalid after the module process exits.
    """

    __slots__ = (
        "_event_bytes",
        "_evidence_tier",
        "_evidence_warnings",
        "_secret_epoch_fingerprint",
        "_receipt_seal",
    )

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("ValidationResult receipts are issued only by validate_event")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("ValidationResult receipts are immutable")

    @property
    def event(self) -> dict[str, Any]:
        """Return a defensive JSON copy of the accepted event."""

        return json.loads(self._event_bytes)

    @property
    def evidence_tier(self) -> str:
        return self._evidence_tier

    @property
    def evidence_warnings(self) -> tuple[str, ...]:
        return self._evidence_warnings

def _receipt_payload(
    event_bytes: bytes,
    evidence_tier: str,
    evidence_warnings: tuple[str, ...],
    secret_epoch_fingerprint: str,
) -> bytes:
    return canonical_json_bytes(
        {
            "event": json.loads(event_bytes),
            "evidence_tier": evidence_tier,
            "evidence_warnings": list(evidence_warnings),
            "secret_epoch_fingerprint": secret_epoch_fingerprint,
        }
    )


def _issue_validation_result(
    event: Mapping[str, Any],
    evidence_tier: str,
    evidence_warnings: tuple[str, ...],
    secret_epoch_fingerprint: str,
) -> ValidationResult:
    event_bytes = canonical_json_bytes(event)
    receipt_seal = hmac.new(
        _RECEIPT_SEAL_KEY,
        b"urusilla:accepted-receipt:v1\x00"
        + _receipt_payload(
            event_bytes,
            evidence_tier,
            evidence_warnings,
            secret_epoch_fingerprint,
        ),
        hashlib.sha256,
    ).digest()
    receipt = object.__new__(ValidationResult)
    object.__setattr__(receipt, "_event_bytes", event_bytes)
    object.__setattr__(receipt, "_evidence_tier", evidence_tier)
    object.__setattr__(receipt, "_evidence_warnings", evidence_warnings)
    object.__setattr__(
        receipt, "_secret_epoch_fingerprint", secret_epoch_fingerprint
    )
    object.__setattr__(receipt, "_receipt_seal", receipt_seal)
    return receipt


def _verify_validation_result(result: ValidationResult) -> None:
    try:
        event_bytes = result._event_bytes
        evidence_tier = result._evidence_tier
        evidence_warnings = result._evidence_warnings
        secret_epoch_fingerprint = result._secret_epoch_fingerprint
        supplied_seal = result._receipt_seal
    except (AttributeError, TypeError) as exc:
        raise TelemetryValidationError("aggregate input contains an unissued receipt") from exc
    if (
        type(event_bytes) is not bytes
        or evidence_tier not in EVIDENCE_TIERS
        or type(evidence_warnings) is not tuple
        or any(type(item) is not str for item in evidence_warnings)
        or type(secret_epoch_fingerprint) is not str
        or not _HEX32_RE.fullmatch(secret_epoch_fingerprint)
        or type(supplied_seal) is not bytes
    ):
        raise TelemetryValidationError("aggregate input contains a malformed receipt")
    expected_seal = hmac.new(
        _RECEIPT_SEAL_KEY,
        b"urusilla:accepted-receipt:v1\x00"
        + _receipt_payload(
            event_bytes,
            evidence_tier,
            evidence_warnings,
            secret_epoch_fingerprint,
        ),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(supplied_seal, expected_seal):
        raise TelemetryValidationError("aggregate input contains an unauthentic receipt")
    try:
        decoded_event = json.loads(event_bytes)
        _validate_event_shape(decoded_event, require_signature=True)
    except (json.JSONDecodeError, UnicodeDecodeError, TelemetryValidationError) as exc:
        raise TelemetryValidationError("aggregate receipt event is invalid") from exc
    if canonical_json_bytes(decoded_event) != event_bytes:
        raise TelemetryValidationError("aggregate receipt event is non-canonical")


def _prospective_transition(
    event: Mapping[str, Any], phase: str | None, active_mode: str | None
) -> tuple[str, str]:
    event_type = event["event_type"]
    mode = event["mode"]
    if phase is None:
        if event_type != "profile_discovered":
            raise TelemetryValidationError("first event in a pseudonym epoch must be profile_discovered")
        return "DISCOVERED", mode
    if phase in {"DISABLED", "EXHAUSTED"}:
        raise TelemetryValidationError("event follows a terminal lifecycle state")
    if event_type == "profile_disabled":
        return "DISABLED", active_mode or mode
    if event_type == "manifest_verified" and phase == "DISCOVERED" and mode == active_mode:
        return "VERIFIED", mode
    if event_type == "negotiation_accepted" and phase == "VERIFIED" and mode == active_mode:
        return "ACTIVE", mode
    if event_type == "negotiation_rejected" and phase == "VERIFIED" and mode == active_mode:
        return "REJECTED", mode
    if event_type == "fallback_succeeded" and phase in {"ACTIVE", "REJECTED"}:
        return "FALLBACK", mode
    if event_type == "fallback_exhausted" and phase in {"ACTIVE", "REJECTED"}:
        return "EXHAUSTED", mode
    if event_type in {"safe_message_completed", "message_failed"} and phase in {
        "ACTIVE",
        "FALLBACK",
    }:
        if mode != active_mode:
            raise TelemetryValidationError("message event mode does not match active lifecycle mode")
        return phase, active_mode
    raise TelemetryValidationError("impossible event sequence")


def validate_event(
    event: Mapping[str, Any],
    *,
    secret: bytes,
    state: TelemetryState,
    evidence_registry: EvidenceRegistry | None = None,
    completion_issuer_registry: TrustedLocalCompletionIssuerRegistry | None = None,
    max_events_per_day: int = DEFAULT_MAX_EVENTS_PER_DAY,
    per_type_limits: Mapping[str, int] | None = None,
) -> ValidationResult:
    """Validate one event atomically and fail closed on any mismatch."""

    secret = _require_hmac_key(secret)
    if not isinstance(state, TelemetryState):
        raise TelemetryValidationError("state must be TelemetryState")
    _validate_event_shape(event, require_signature=True)
    unsigned = {key: value for key, value in event.items() if key != "signature"}
    expected_signature = _event_signature(secret, unsigned)
    if not hmac.compare_digest(event["signature"], expected_signature):
        raise TelemetryValidationError("HMAC signature mismatch")
    month = event["coarse_time_bucket"][:7]
    if event["rotating_install_pseudonym"] != derive_rotating_pseudonym(secret, month):
        raise TelemetryValidationError("rotating pseudonym does not match local secret and month")

    nonce = event["event_nonce"]
    pseudonym = event["rotating_install_pseudonym"]
    sequence = event["sequence"]
    if nonce in state.seen_nonces:
        raise TelemetryValidationError("duplicate event_nonce replay")
    last_sequence = state.last_sequence.get(pseudonym)
    expected_sequence = 0 if last_sequence is None else last_sequence + 1
    if sequence != expected_sequence:
        raise TelemetryValidationError(
            f"sequence must be exactly {expected_sequence} for this pseudonym epoch"
        )

    identity = (event["deployment_class"], event["implementation_version"])
    old_identity = state.deployment_identity.get(pseudonym)
    if old_identity is not None and identity != old_identity:
        raise TelemetryValidationError("deployment identity changed inside pseudonym epoch")

    if type(max_events_per_day) is not int or max_events_per_day <= 0:
        raise TelemetryValidationError("max_events_per_day must be a positive integer")
    limits = dict(DEFAULT_PER_TYPE_LIMITS)
    if per_type_limits is not None:
        if not set(per_type_limits) <= set(EVENT_TYPES):
            raise TelemetryValidationError("per_type_limits contains an unknown event type")
        for event_type, limit in per_type_limits.items():
            if type(limit) is not int or limit <= 0:
                raise TelemetryValidationError("per-type rate limits must be positive integers")
            limits[event_type] = limit
    day = event["coarse_time_bucket"]
    total_key = (pseudonym, day, "*")
    type_key = (pseudonym, day, event["event_type"])
    if state.rate_counts.get(total_key, 0) >= max_events_per_day:
        raise TelemetryValidationError("daily event rate limit exceeded")
    if state.rate_counts.get(type_key, 0) >= limits[event["event_type"]]:
        raise TelemetryValidationError("daily event-type rate limit exceeded")

    secret_epoch_fingerprint = hmac.new(
        secret,
        ("urusilla:secret-epoch-fingerprint:v1|" + month).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:32]
    secret_epoch_key = (secret_epoch_fingerprint, month)
    bound_pseudonym = state.secret_epoch_pseudonyms.get(secret_epoch_key)
    if bound_pseudonym is not None and bound_pseudonym != pseudonym:
        raise TelemetryValidationError("one local secret produced multiple pseudonyms in one epoch")

    phase, active_mode = _prospective_transition(
        event,
        state.phases.get(pseudonym),
        state.active_modes.get(pseudonym),
    )
    registry = evidence_registry if evidence_registry is not None else EvidenceRegistry()
    tier, warnings = registry.classify(event)
    if event["event_type"] == "safe_message_completed":
        completion_registry = (
            completion_issuer_registry
            if completion_issuer_registry is not None
            else TrustedLocalCompletionIssuerRegistry()
        )
        locally_attested, attestation_warnings = completion_registry.verify(event)
        warnings = tuple(warnings) + tuple(attestation_warnings)
        if locally_attested:
            tier = "locally_attested_completion"

    # Commit state only after every validation and classification check succeeds.
    state.seen_nonces.add(nonce)
    state.last_sequence[pseudonym] = sequence
    state.phases[pseudonym] = phase
    state.active_modes[pseudonym] = active_mode
    state.deployment_identity[pseudonym] = identity
    state.rate_counts[total_key] = state.rate_counts.get(total_key, 0) + 1
    state.rate_counts[type_key] = state.rate_counts.get(type_key, 0) + 1
    state.secret_epoch_pseudonyms[secret_epoch_key] = pseudonym

    normalized = json.loads(canonical_json_bytes(event))
    return _issue_validation_result(
        normalized,
        tier,
        warnings,
        secret_epoch_fingerprint,
    )


def _event_evidence_ref(event: Mapping[str, Any]) -> str | None:
    refs = event.get("evidence_refs") or {}
    return refs.get("crossplay") or refs.get("conformance")


def _cluster_flags(results: list[ValidationResult]) -> dict[str, set[str]]:
    flags = {result.event["event_nonce"]: set() for result in results}

    secret_groups: dict[tuple[str, str], list[ValidationResult]] = {}
    evidence_groups: dict[tuple[str, str], list[ValidationResult]] = {}
    synchronized_groups: dict[tuple[Any, ...], list[ValidationResult]] = {}
    for result in results:
        event = result.event
        month = event["coarse_time_bucket"][:7]
        secret_groups.setdefault(
            (result._secret_epoch_fingerprint, month), []
        ).append(result)
        evidence_ref = _event_evidence_ref(event)
        if evidence_ref is not None:
            evidence_groups.setdefault((event["coarse_time_bucket"], evidence_ref), []).append(result)
        if event["event_type"] == "safe_message_completed":
            synchronized_key = (
                event["coarse_time_bucket"],
                event["sequence"],
                event["implementation_version"],
                event["mode"],
                evidence_ref,
                canonical_json_bytes(event.get("metric_buckets", {})),
            )
            synchronized_groups.setdefault(synchronized_key, []).append(result)

    for group in secret_groups.values():
        if len({item.event["rotating_install_pseudonym"] for item in group}) > 1:
            for item in group:
                flags[item.event["event_nonce"]].add("signature_secret_epoch_fanout")
    for group in evidence_groups.values():
        if (
            len({item.event["rotating_install_pseudonym"] for item in group})
            > MAX_PSEUDONYMS_PER_EVIDENCE_BUCKET
        ):
            for item in group:
                flags[item.event["event_nonce"]].add("shared_evidence_cluster")
    for group in synchronized_groups.values():
        if (
            len({item.event["rotating_install_pseudonym"] for item in group})
            > MAX_PSEUDONYMS_PER_EVIDENCE_BUCKET
        ):
            for item in group:
                flags[item.event["event_nonce"]].add("synchronized_activity_cluster")
    return flags


def aggregate_events(results: Iterable[ValidationResult]) -> dict[str, Any]:
    """Return a deterministic content-free aggregate with honest trust labels.

    This local kit has no independent external verifier, so verified external
    adoption impact is always zero. A separately labeled synthetic example gives
    1,000 milliunits only to safe-completion events whose content-free completion
    attestation passed an explicitly configured local HMAC issuer. Heuristic
    clusters receive one quarter weight, secret-epoch fanout receives zero, and
    each evidence/day bucket is capped. These heuristics are abuse signals, not
    proof of distinct agents, independence, fraud, or adoption. Downloads never
    enter either metric.
    """

    accepted = list(results)
    if any(not isinstance(result, ValidationResult) for result in accepted):
        raise TelemetryValidationError("aggregate input must contain ValidationResult values")
    for result in accepted:
        _verify_validation_result(result)
    accepted.sort(
        key=lambda result: (
            result.event["coarse_time_bucket"],
            result.event["rotating_install_pseudonym"],
            result.event["sequence"],
            result.event["event_nonce"],
        )
    )
    nonces = [result.event["event_nonce"] for result in accepted]
    if len(nonces) != len(set(nonces)):
        raise TelemetryValidationError("aggregate input repeats an accepted event")
    lifecycle_positions = [
        (
            result.event["rotating_install_pseudonym"],
            result.event["sequence"],
        )
        for result in accepted
    ]
    if len(lifecycle_positions) != len(set(lifecycle_positions)):
        raise TelemetryValidationError(
            "aggregate input repeats a pseudonym lifecycle sequence position"
        )

    flags_by_nonce = _cluster_flags(accepted)
    event_counts = {key: 0 for key in EVENT_TYPES}
    deployment_counts = {key: 0 for key in DEPLOYMENT_CLASSES}
    mode_counts = {key: 0 for key in MODES}
    tier_counts = {key: 0 for key in EVIDENCE_TIERS}
    flag_counts = {key: 0 for key in CLUSTER_FLAGS}
    for result in accepted:
        event = result.event
        event_counts[event["event_type"]] += 1
        deployment_counts[event["deployment_class"]] += 1
        mode_counts[event["mode"]] += 1
        tier_counts[result.evidence_tier] += 1
        for flag_name in flags_by_nonce[event["event_nonce"]]:
            flag_counts[flag_name] += 1

    locally_attested_safe = [
        result
        for result in accepted
        if result.event["event_type"] == "safe_message_completed"
        and result.evidence_tier == "locally_attested_completion"
    ]
    contribution_by_proof_day: dict[tuple[str, str], int] = {}
    synthetic_impact_milliunits = 0
    unflagged_locally_attested = 0
    for result in locally_attested_safe:
        event = result.event
        event_flags = flags_by_nonce[event["event_nonce"]]
        if not event_flags:
            unflagged_locally_attested += 1
        base = 1_000
        if "signature_secret_epoch_fanout" in event_flags:
            base = 0
        elif event_flags & {"shared_evidence_cluster", "synchronized_activity_cluster"}:
            base //= 4
        proof = _event_evidence_ref(event)
        if proof is None:
            base = 0
            proof = "missing"
        proof_day = (event["coarse_time_bucket"], proof)
        already = contribution_by_proof_day.get(proof_day, 0)
        allowed = max(0, MAX_IMPACT_MILLIUNITS_PER_EVIDENCE_BUCKET - already)
        contribution = min(base, allowed)
        contribution_by_proof_day[proof_day] = already + contribution
        synthetic_impact_milliunits += contribution

    aggregate: dict[str, Any] = {
        "aggregate_schema_version": AGGREGATE_VERSION,
        "accepted_events": len(accepted),
        "coarse_time_buckets": sorted(
            {result.event["coarse_time_bucket"] for result in accepted}
        ),
        "event_counts": event_counts,
        "self_declared_deployment_counts": deployment_counts,
        "mode_counts": mode_counts,
        "evidence_tier_counts": tier_counts,
        "safe_completion": {
            "self_reported_observed": event_counts["safe_message_completed"],
            "locally_attested_synthetic": len(locally_attested_safe),
            "locally_attested_without_cluster_flags": unflagged_locally_attested,
            "independently_verified_external": 0,
        },
        "anti_sybil": {
            "classification": "heuristic_not_identity_or_independence_proof",
            "cluster_flag_counts": flag_counts,
            "flagged_events": sum(
                1 for event_flags in flags_by_nonce.values() if event_flags
            ),
            "max_pseudonyms_per_evidence_day_before_flag": (
                MAX_PSEUDONYMS_PER_EVIDENCE_BUCKET
            ),
            "max_impact_milliunits_per_evidence_day": (
                MAX_IMPACT_MILLIUNITS_PER_EVIDENCE_BUCKET
            ),
        },
        "adoption_adjusted_impact": {
            "formula_version": "independent-external-evidence-required-v2",
            "unit": "verified-safe-message-milliunit",
            "value_milliunits": 0,
            "independent_external_verifier_present": False,
            "self_declared_external_class_used_as_verification": False,
            "downloads_or_repository_activity_used": False,
        },
        "synthetic_locally_attested_impact": {
            "formula_version": "local-hmac-completion-example-v1",
            "unit": "locally-attested-safe-message-milliunit",
            "value_milliunits": synthetic_impact_milliunits,
            "external_adoption_claim": False,
            "independent_verification_claim": False,
            "downloads_or_repository_activity_used": False,
        },
        "privacy_boundary": {
            "content_free": True,
            "precise_timestamps_present": False,
            "message_user_session_identifiers_present": False,
        },
    }
    aggregate["aggregate_sha256"] = hashlib.sha256(canonical_json_bytes(aggregate)).hexdigest()
    return aggregate


def adoption_adjusted_impact(results: Iterable[ValidationResult]) -> dict[str, Any]:
    """Return verified external impact, which is zero without an independent verifier."""

    return aggregate_events(results)["adoption_adjusted_impact"]


def synthetic_locally_attested_impact(
    results: Iterable[ValidationResult],
) -> dict[str, Any]:
    """Return the separately labeled local HMAC completion example metric."""

    return aggregate_events(results)["synthetic_locally_attested_impact"]


def aggregate_json(results: Iterable[ValidationResult]) -> str:
    """Return canonical aggregate JSON followed by one newline."""

    return canonical_json_bytes(aggregate_events(results)).decode("utf-8") + "\n"


__all__ = [
    "AGGREGATE_VERSION",
    "COMPLETION_ATTESTATION_VERSION",
    "DEFAULT_MAX_EVENTS_PER_DAY",
    "DEFAULT_PER_TYPE_LIMITS",
    "EvidenceRegistry",
    "SCHEMA_VERSION",
    "TelemetryState",
    "TelemetryValidationError",
    "TrustedLocalCompletionIssuerRegistry",
    "ValidationResult",
    "adoption_adjusted_impact",
    "aggregate_events",
    "aggregate_json",
    "attach_local_completion_attestation",
    "canonical_json_bytes",
    "coarse_day_bucket",
    "create_signed_event",
    "derive_rotating_pseudonym",
    "issue_local_completion_attestation",
    "sign_event",
    "synthetic_locally_attested_impact",
    "validate_event",
]
