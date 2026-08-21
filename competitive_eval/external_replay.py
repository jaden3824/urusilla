"""Content-addressed exchange for externally executed model responses.

The core harness deliberately has no provider SDK, credential reader, socket,
or spending authority.  This module supplies the missing file boundary: the
harness can emit one exact pending request, an external operator can execute
that request, and a later offline process can import the captured response.

This is not an authentication layer and it does not make the current mock
runner claim-eligible.  Content-only records may preserve useful output while
leaving model identity, usage, timing, or billing as ``null``.  Such unknowns
are never coerced to zero and cannot satisfy ``require_core_usage_capture``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .canonical import (
    canonical_bytes,
    canonical_json,
    require_exact_keys,
    sequence_sha256,
    sha256_bytes,
    strict_json_loads,
)
from .errors import EvaluationError, IntegrityError, ManifestError
from .protocol import CallRequest


EXECUTION_PROFILE_FORMAT = "competitive-eval-external-execution-profile-v1"
CAPTURED_RESPONSE_FORMAT = "competitive-eval-captured-response-v1"
EXTERNAL_RECORD_FORMAT = "competitive-eval-external-response-record-v1"
EXTERNAL_BUNDLE_FORMAT = "competitive-eval-external-response-bundle-v1"
PENDING_CALL_FORMAT = "competitive-eval-pending-external-call-v1"
PROVENANCE_STATUS = "content-bound-not-authenticated"
ROLE_MAPPING = "provider-neutral-role-content-v1"
MAX_EXTERNAL_BUNDLE_BYTES = 128 * 1024 * 1024
ALLOWED_USE = "content-replay-and-core-usage-capture-only"
CLAIM_BLOCKERS = (
    "raw provider observation was not re-normalized by this module",
    "content hashes do not authenticate a provider or operator",
    "research token partition and full task ledger are not assembled",
    "the competitive runner does not consume the hybrid capture path or assemble "
    "it into the authenticated full-task study ledger",
    "cross-bundle provider receipt replay is not indexed",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_STATUS = frozenset({"completed", "timeout", "refused", "provider_error"})
_SOURCE_KINDS = frozenset({"provider", "provider-ui", "unavailable"})
_SETTINGS_STATUS = frozenset({"confirmed-exact", "partial", "unknown"})
_USAGE_STATUS = frozenset({"complete", "partial", "unavailable"})
_REASONING_ACCOUNTING = frozenset(
    {"included-in-output", "separately-reported", "not-reported"}
)


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ManifestError(f"{label} must be a JSON object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ManifestError(f"{label} must be a JSON array")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ManifestError(f"{label} must be non-empty text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ManifestError(f"{label} is not valid UTF-8 text") from exc
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ManifestError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _optional_sha(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _sha(value, label)


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ManifestError(f"{label} must be a nonnegative integer")
    return value


def _optional_count(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _count(value, label)


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    core = dict(value)
    core.pop(field, None)
    return sha256_bytes(canonical_bytes(core))


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _validate_decimal(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ManifestError(f"{label} must be a nonnegative plain decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ManifestError(f"{label} is not a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ManifestError(f"{label} must be finite and nonnegative")
    return value


def build_execution_profile(
    *,
    provider_id: str,
    api_id: str,
    normalizer_id: str | None,
    normalizer_sha256: str | None,
) -> dict[str, Any]:
    """Freeze the provider-facing mapping used by an external operator."""

    core: dict[str, Any] = {
        "format": EXECUTION_PROFILE_FORMAT,
        "provider_id": provider_id,
        "api_id": api_id,
        "role_mapping": ROLE_MAPPING,
        "normalizer_id": normalizer_id,
        "normalizer_sha256": normalizer_sha256,
    }
    core["profile_sha256"] = sha256_bytes(canonical_bytes(core))
    return _validate_execution_profile(core)


def _validate_execution_profile(raw: Any) -> dict[str, Any]:
    profile = _object(raw, "execution_profile")
    require_exact_keys(
        profile,
        (
            "format",
            "provider_id",
            "api_id",
            "role_mapping",
            "normalizer_id",
            "normalizer_sha256",
            "profile_sha256",
        ),
        label="execution_profile",
    )
    if profile["format"] != EXECUTION_PROFILE_FORMAT:
        raise ManifestError("execution profile format differs")
    _text(profile["provider_id"], "execution_profile.provider_id")
    _text(profile["api_id"], "execution_profile.api_id")
    if profile["role_mapping"] != ROLE_MAPPING:
        raise ManifestError("execution profile role mapping differs")
    normalizer_id = _optional_text(
        profile["normalizer_id"], "execution_profile.normalizer_id"
    )
    normalizer_sha256 = _optional_sha(
        profile["normalizer_sha256"], "execution_profile.normalizer_sha256"
    )
    if (normalizer_id is None) is not (normalizer_sha256 is None):
        raise ManifestError("execution profile normalizer id and digest must be paired")
    supplied = _sha(profile["profile_sha256"], "execution_profile.profile_sha256")
    if _digest_without(profile, "profile_sha256") != supplied:
        raise IntegrityError("execution profile digest mismatch")
    return _detach(profile)


def _validate_provider_observation(
    raw: Any,
    *,
    request: CallRequest,
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    observation = _object(raw, "response.provider_observation")
    require_exact_keys(
        observation,
        (
            "source_kind",
            "provider_id",
            "request_id",
            "response_id",
            "resolved_model_id",
            "effective_settings_status",
            "raw_receipt_utf8",
            "raw_receipt_sha256",
        ),
        label="response.provider_observation",
    )
    source_kind = observation["source_kind"]
    if source_kind not in _SOURCE_KINDS:
        raise ManifestError("provider observation source kind is unknown")
    if observation["provider_id"] != profile["provider_id"]:
        raise IntegrityError("provider observation differs from execution profile")
    _text(observation["provider_id"], "response.provider_observation.provider_id")
    request_id = _optional_text(
        observation["request_id"], "response.provider_observation.request_id"
    )
    response_id = _optional_text(
        observation["response_id"], "response.provider_observation.response_id"
    )
    resolved_model_id = _optional_text(
        observation["resolved_model_id"],
        "response.provider_observation.resolved_model_id",
    )
    if (
        resolved_model_id is not None
        and resolved_model_id != request.value["model_ref"]["logical_model_id"]
    ):
        raise IntegrityError("captured response resolved model differs from request")
    settings_status = observation["effective_settings_status"]
    if settings_status not in _SETTINGS_STATUS:
        raise ManifestError("effective settings status is unknown")

    raw_receipt = observation["raw_receipt_utf8"]
    raw_sha = observation["raw_receipt_sha256"]
    if raw_receipt is None:
        if raw_sha is not None:
            raise ManifestError("raw receipt digest exists without inline receipt bytes")
    else:
        if type(raw_receipt) is not str or not raw_receipt:
            raise ManifestError("raw provider receipt must be non-empty UTF-8 text or null")
        try:
            encoded = raw_receipt.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ManifestError("raw provider receipt is not valid UTF-8") from exc
        if _sha(raw_sha, "response.provider_observation.raw_receipt_sha256") != (
            sha256_bytes(encoded)
        ):
            raise IntegrityError("raw provider receipt digest mismatch")

    provider_complete = source_kind == "provider"
    if provider_complete and not all(
        (
            request_id,
            response_id,
            resolved_model_id,
            settings_status == "confirmed-exact",
            raw_receipt is not None,
        )
    ):
        raise ManifestError(
            "provider capture requires IDs, exact settings, model identity, and raw receipt"
        )
    if source_kind == "unavailable" and any(
        value is not None
        for value in (request_id, response_id, resolved_model_id, raw_receipt, raw_sha)
    ):
        raise ManifestError("unavailable provider observation cannot carry provider evidence")
    if source_kind == "unavailable" and settings_status != "unknown":
        raise ManifestError("unavailable provider observation must keep settings unknown")
    return _detach(observation), provider_complete


def _validate_usage(raw: Any) -> tuple[dict[str, Any], bool]:
    usage = _object(raw, "response.usage")
    require_exact_keys(
        usage,
        (
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
        ),
        label="response.usage",
    )
    status = usage["status"]
    if status not in _USAGE_STATUS:
        raise ManifestError("usage status is unknown")
    input_tokens = _optional_count(usage["input_tokens"], "usage.input_tokens")
    output_tokens = _optional_count(usage["output_tokens"], "usage.output_tokens")
    total_tokens = _optional_count(usage["total_tokens"], "usage.total_tokens")
    cache_read = _optional_count(usage["cache_read_tokens"], "usage.cache_read_tokens")
    cache_write = _optional_count(
        usage["cache_write_tokens"], "usage.cache_write_tokens"
    )
    reasoning = _optional_count(
        usage["reasoning_tokens_subset"], "usage.reasoning_tokens_subset"
    )
    reasoning_accounting = usage["reasoning_accounting"]
    if reasoning_accounting not in _REASONING_ACCOUNTING:
        raise ManifestError("reasoning accounting is unknown")
    _validate_decimal(usage["actual_billed_usd"], "usage.actual_billed_usd")

    unclassified = usage["unclassified_usage_json"]
    if unclassified is not None:
        if type(unclassified) is not str:
            raise ManifestError("unclassified usage must be canonical JSON text or null")
        parsed = strict_json_loads(unclassified)
        if canonical_json(parsed) != unclassified:
            raise ManifestError("unclassified usage text is not canonical JSON")

    values = (input_tokens, output_tokens, total_tokens)
    if status == "unavailable":
        if any(
            value is not None
            for value in (
                *values,
                cache_read,
                cache_write,
                reasoning,
                usage["actual_billed_usd"],
                unclassified,
            )
        ):
            raise ManifestError("unavailable usage must preserve every value as null")
        if reasoning_accounting != "not-reported":
            raise ManifestError("unavailable usage cannot classify reasoning")
        return _detach(usage), False

    if status == "complete" and any(value is None for value in values):
        raise ManifestError("complete usage requires input, output, and total tokens")
    if status == "partial" and all(value is None for value in values):
        raise ManifestError("partial usage must carry at least one reported token count")

    if input_tokens is not None:
        if cache_read is not None and cache_read > input_tokens:
            raise ManifestError("cache-read tokens cannot exceed input tokens")
        if cache_write is not None and cache_write > input_tokens:
            raise ManifestError("cache-write tokens cannot exceed input tokens")

    if all(value is not None for value in values):
        assert input_tokens is not None
        assert output_tokens is not None
        assert total_tokens is not None
        if reasoning_accounting == "included-in-output":
            if reasoning is None or reasoning > output_tokens:
                raise ManifestError("included reasoning must be a reported output subset")
            expected_total = input_tokens + output_tokens
            if total_tokens != expected_total:
                raise IntegrityError("included-reasoning provider total does not reconcile")
        elif reasoning_accounting == "separately-reported":
            if reasoning is None:
                raise ManifestError("separately reported reasoning cannot be null")
            expected_total = input_tokens + output_tokens + reasoning
            if total_tokens != expected_total:
                raise IntegrityError("separate-reasoning provider total does not reconcile")
        else:
            if reasoning is not None:
                raise ManifestError("unreported reasoning must remain null")
            if total_tokens < input_tokens + output_tokens:
                raise IntegrityError("provider total is below visible token usage")
    elif reasoning_accounting != "not-reported" or reasoning is not None:
        raise ManifestError("partial token totals cannot make a reasoning allocation")

    usage_complete = status == "complete" and unclassified is None
    return _detach(usage), usage_complete


def _validate_timing(raw: Any) -> dict[str, Any]:
    timing = _object(raw, "response.timing")
    require_exact_keys(timing, ("model_ns",), label="response.timing")
    _optional_count(timing["model_ns"], "response.timing.model_ns")
    return _detach(timing)


@dataclass(frozen=True)
class ExternalResponseRecord:
    _value: Mapping[str, Any]
    core_usage_capture_complete: bool

    @property
    def value(self) -> Mapping[str, Any]:
        """Return a detached record so its verified invariants stay immutable."""

        return _detach(self._value)

    @property
    def call_id(self) -> str:
        return str(self._value["call_id"])

    @property
    def request(self) -> CallRequest:
        return CallRequest.from_value(_detach(self._value["call_request"]))

    @property
    def status(self) -> str:
        return str(self._value["response"]["status"])

    @property
    def output_text(self) -> str | None:
        value = self._value["response"]["output_text"]
        return None if value is None else str(value)

    @property
    def usage(self) -> Mapping[str, Any]:
        return _detach(self._value["response"]["usage"])

    @property
    def claim_eligible(self) -> bool:
        """A content-bound capture is never authenticated study evidence alone."""

        return False

    @property
    def claim_blockers(self) -> tuple[str, ...]:
        return CLAIM_BLOCKERS


def build_external_response_record(
    *,
    sequence: int,
    request: CallRequest,
    execution_profile: Mapping[str, Any],
    status: str,
    output_text: str | None,
    provider_observation: Mapping[str, Any],
    usage: Mapping[str, Any],
    timing: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one canonical captured response after an external execution."""

    request = CallRequest.from_value(dict(request.value))
    profile = _validate_execution_profile(execution_profile)
    response: dict[str, Any] = {
        "format": CAPTURED_RESPONSE_FORMAT,
        "binding": {
            "call_id": request.call_id,
            "request_sha256": request.request_sha256,
            "settings_sha256": request.settings_sha256,
        },
        "status": status,
        "output_text": output_text,
        "provider_observation": dict(provider_observation),
        "usage": dict(usage),
        "timing": dict(timing),
        "provenance_status": PROVENANCE_STATUS,
    }
    response["response_sha256"] = sha256_bytes(canonical_bytes(response))
    record: dict[str, Any] = {
        "format": EXTERNAL_RECORD_FORMAT,
        "sequence": sequence,
        "episode_id": request.value["episode_id"],
        "call_id": request.call_id,
        "request_sha256": request.request_sha256,
        "execution_profile_sha256": profile["profile_sha256"],
        "call_request": dict(request.value),
        "response": response,
    }
    record["record_sha256"] = sha256_bytes(canonical_bytes(record))
    return dict(_validate_record(record, profile=profile).value)


def _validate_record(
    raw: Any, *, profile: Mapping[str, Any]
) -> ExternalResponseRecord:
    record = _object(raw, "external response record")
    require_exact_keys(
        record,
        (
            "format",
            "sequence",
            "episode_id",
            "call_id",
            "request_sha256",
            "execution_profile_sha256",
            "call_request",
            "response",
            "record_sha256",
        ),
        label="external response record",
    )
    if record["format"] != EXTERNAL_RECORD_FORMAT:
        raise ManifestError("external response record format differs")
    _count(record["sequence"], "external response record sequence")
    request = CallRequest.from_value(
        _object(record["call_request"], "external response record call_request")
    )
    if record["episode_id"] != request.value["episode_id"]:
        raise IntegrityError("external response episode binding mismatch")
    if record["call_id"] != request.call_id:
        raise IntegrityError("external response call binding mismatch")
    if record["request_sha256"] != request.request_sha256:
        raise IntegrityError("external response request digest mismatch")
    if record["execution_profile_sha256"] != profile["profile_sha256"]:
        raise IntegrityError("external response execution profile mismatch")

    response = _object(record["response"], "external response")
    require_exact_keys(
        response,
        (
            "format",
            "binding",
            "status",
            "output_text",
            "provider_observation",
            "usage",
            "timing",
            "provenance_status",
            "response_sha256",
        ),
        label="external response",
    )
    if response["format"] != CAPTURED_RESPONSE_FORMAT:
        raise ManifestError("captured response format differs")
    binding = _object(response["binding"], "external response binding")
    require_exact_keys(
        binding,
        ("call_id", "request_sha256", "settings_sha256"),
        label="external response binding",
    )
    expected_binding = {
        "call_id": request.call_id,
        "request_sha256": request.request_sha256,
        "settings_sha256": request.settings_sha256,
    }
    if binding != expected_binding:
        raise IntegrityError("captured response binding differs from exact request")
    if response["status"] not in _STATUS:
        raise ManifestError("captured response status is unknown")
    output_text = response["output_text"]
    if response["status"] == "completed":
        if type(output_text) is not str:
            raise ManifestError("completed response output must be text")
    elif output_text is not None and type(output_text) is not str:
        raise ManifestError("non-completed response output must be text or null")
    if type(output_text) is str:
        try:
            output_text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ManifestError("captured response output is not valid UTF-8") from exc

    _, provider_complete = _validate_provider_observation(
        response["provider_observation"], request=request, profile=profile
    )
    _, usage_complete = _validate_usage(response["usage"])
    _validate_timing(response["timing"])
    if response["provenance_status"] != PROVENANCE_STATUS:
        raise ManifestError("captured response overstates its provenance")
    supplied_response_sha = _sha(
        response["response_sha256"], "external response response_sha256"
    )
    if _digest_without(response, "response_sha256") != supplied_response_sha:
        raise IntegrityError("captured response digest mismatch")
    supplied_record_sha = _sha(
        record["record_sha256"], "external response record_sha256"
    )
    if _digest_without(record, "record_sha256") != supplied_record_sha:
        raise IntegrityError("external response record digest mismatch")
    return ExternalResponseRecord(
        _detach(record),
        core_usage_capture_complete=provider_complete and usage_complete,
    )


def build_external_response_bundle(
    *,
    run_id: str,
    run_manifest_sha256: str,
    episode_sequence_sha256: str,
    operator_id: str,
    capture_implementation_sha256: str | None,
    operator_attestation_sha256: str | None,
    execution_profile: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a bundle without granting network, spending, or claim authority."""

    profile = _validate_execution_profile(execution_profile)
    normalized_records = [
        dict(_validate_record(dict(record), profile=profile).value)
        for record in records
    ]
    core: dict[str, Any] = {
        "format": EXTERNAL_BUNDLE_FORMAT,
        "run_id": run_id,
        "run_manifest_sha256": run_manifest_sha256,
        "episode_sequence_sha256": episode_sequence_sha256,
        "producer": {
            "operator_id": operator_id,
            "capture_implementation_sha256": capture_implementation_sha256,
            "operator_attestation_sha256": operator_attestation_sha256,
        },
        "execution_profile": profile,
        "records": normalized_records,
        "record_sequence_sha256": sequence_sha256(
            record["record_sha256"] for record in normalized_records
        ),
        "allowed_use": ALLOWED_USE,
        "claim_eligible": False,
        "claim_blockers": list(CLAIM_BLOCKERS),
    }
    core["bundle_sha256"] = sha256_bytes(canonical_bytes(core))
    return dict(ExternalResponseStore.from_object(core).value)


class MissingExternalResponse(EvaluationError):
    """Raised with the exact next request an external operator must execute."""

    def __init__(self, pending: Mapping[str, Any]):
        self.pending = _detach(pending)
        super().__init__(
            "external response is missing for call "
            + str(self.pending["call_request"]["call_id"])
        )


class ExternalResponseStore:
    """Strict, offline, idempotent lookup over externally captured responses."""

    def __init__(
        self,
        value: Any,
        *,
        expected_run_id: str | None = None,
        expected_run_manifest_sha256: str | None = None,
        expected_episode_sequence_sha256: str | None = None,
    ):
        bundle = _object(value, "external response bundle")
        require_exact_keys(
            bundle,
            (
                "format",
                "run_id",
                "run_manifest_sha256",
                "episode_sequence_sha256",
                "producer",
                "execution_profile",
                "records",
                "record_sequence_sha256",
                "allowed_use",
                "claim_eligible",
                "claim_blockers",
                "bundle_sha256",
            ),
            label="external response bundle",
        )
        if bundle["format"] != EXTERNAL_BUNDLE_FORMAT:
            raise ManifestError("external response bundle format differs")
        run_id = _sha(bundle["run_id"], "external response bundle run_id")
        run_manifest_sha256 = _sha(
            bundle["run_manifest_sha256"],
            "external response bundle run_manifest_sha256",
        )
        episode_sequence_sha256 = _sha(
            bundle["episode_sequence_sha256"],
            "external response bundle episode_sequence_sha256",
        )
        for observed, expected, label in (
            (run_id, expected_run_id, "run ID"),
            (run_manifest_sha256, expected_run_manifest_sha256, "run manifest"),
            (
                episode_sequence_sha256,
                expected_episode_sequence_sha256,
                "episode sequence",
            ),
        ):
            if expected is not None and observed != _sha(expected, f"expected {label}"):
                raise IntegrityError(f"external response bundle {label} mismatch")

        producer = _object(bundle["producer"], "external response bundle producer")
        require_exact_keys(
            producer,
            (
                "operator_id",
                "capture_implementation_sha256",
                "operator_attestation_sha256",
            ),
            label="external response bundle producer",
        )
        _text(producer["operator_id"], "external response bundle producer.operator_id")
        _optional_sha(
            producer["capture_implementation_sha256"],
            "external response bundle producer.capture_implementation_sha256",
        )
        _optional_sha(
            producer["operator_attestation_sha256"],
            "external response bundle producer.operator_attestation_sha256",
        )

        profile = _validate_execution_profile(bundle["execution_profile"])
        records: list[ExternalResponseRecord] = []
        seen_calls: set[str] = set()
        seen_provider_identities: set[tuple[str, str]] = set()
        for index, raw_record in enumerate(
            _array(bundle["records"], "external response bundle records")
        ):
            record = _validate_record(raw_record, profile=profile)
            if record.value["sequence"] != index:
                raise IntegrityError("external response record sequence is not contiguous")
            if record.call_id in seen_calls:
                raise IntegrityError("external response bundle contains a duplicate call")
            seen_calls.add(record.call_id)
            observation = record.value["response"]["provider_observation"]
            for kind, field in (
                ("provider-request", "request_id"),
                ("provider-response", "response_id"),
                ("raw-receipt", "raw_receipt_sha256"),
            ):
                identity = observation[field]
                if identity is None:
                    continue
                pair = (kind, identity)
                if pair in seen_provider_identities:
                    raise IntegrityError(
                        f"external response provider identity replayed: {kind}"
                    )
                seen_provider_identities.add(pair)
            records.append(record)

        supplied_sequence = _sha(
            bundle["record_sequence_sha256"],
            "external response bundle record_sequence_sha256",
        )
        observed_sequence = sequence_sha256(
            record.value["record_sha256"] for record in records
        )
        if supplied_sequence != observed_sequence:
            raise IntegrityError("external response record sequence digest mismatch")
        if bundle["allowed_use"] != ALLOWED_USE:
            raise ManifestError("external response bundle allowed use differs")
        if bundle["claim_eligible"] is not False:
            raise ManifestError("external response bundle cannot be claim-eligible")
        if bundle["claim_blockers"] != list(CLAIM_BLOCKERS):
            raise ManifestError("external response bundle claim blockers differ")
        supplied_bundle_sha = _sha(
            bundle["bundle_sha256"], "external response bundle bundle_sha256"
        )
        if _digest_without(bundle, "bundle_sha256") != supplied_bundle_sha:
            raise IntegrityError("external response bundle digest mismatch")

        self._value = _detach(bundle)
        self._profile = _detach(profile)
        self._records = {record.call_id: record for record in records}
        self._resolved_call_ids: set[str] = set()

    @classmethod
    def from_object(
        cls,
        value: Any,
        **expected: str | None,
    ) -> "ExternalResponseStore":
        return cls(value, **expected)

    @classmethod
    def from_json(
        cls,
        text: str,
        **expected: str | None,
    ) -> "ExternalResponseStore":
        return cls(
            strict_json_loads(text, max_bytes=MAX_EXTERNAL_BUNDLE_BYTES),
            **expected,
        )

    @property
    def run_id(self) -> str:
        return str(self._value["run_id"])

    @property
    def value(self) -> Mapping[str, Any]:
        """Return a detached bundle so callers cannot mutate store state."""

        return _detach(self._value)

    @property
    def execution_profile(self) -> Mapping[str, Any]:
        return _detach(self._profile)

    @property
    def response_count(self) -> int:
        return len(self._records)

    def pending_call(self, request: CallRequest) -> dict[str, Any]:
        request = CallRequest.from_value(dict(request.value))
        return {
            "format": PENDING_CALL_FORMAT,
            "run_id": self._value["run_id"],
            "run_manifest_sha256": self._value["run_manifest_sha256"],
            "episode_sequence_sha256": self._value["episode_sequence_sha256"],
            "execution_profile_sha256": self._profile["profile_sha256"],
            "call_request": dict(request.value),
            "request_sha256": request.request_sha256,
            "settings_sha256": request.settings_sha256,
            "response_template": {
                "status": None,
                "output_text": None,
                "provider_observation": {
                    "source_kind": None,
                    "provider_id": self._profile["provider_id"],
                    "request_id": None,
                    "response_id": None,
                    "resolved_model_id": None,
                    "effective_settings_status": "unknown",
                    "raw_receipt_utf8": None,
                    "raw_receipt_sha256": None,
                },
                "usage": {
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
                },
                "timing": {"model_ns": None},
            },
            "authority": {
                "network": False,
                "credentials": False,
                "spending": False,
                "external_effects": False,
            },
        }

    def resolve(
        self,
        request: CallRequest,
        *,
        require_core_usage_capture: bool = False,
    ) -> ExternalResponseRecord:
        request = CallRequest.from_value(dict(request.value))
        stored = self._records.get(request.call_id)
        if stored is None:
            raise MissingExternalResponse(self.pending_call(request))
        # Never expose the store-owned mutable mapping. Revalidate a detached
        # copy on every resolve so even accidental internal mutation fails
        # closed before an output or usage value is returned.
        record = _validate_record(stored.value, profile=self._profile)
        if canonical_bytes(record.request.value) != canonical_bytes(request.value):
            raise IntegrityError("external response request differs from pending call")
        if record.value["request_sha256"] != request.request_sha256:
            raise IntegrityError("external response request digest differs on resolve")
        if (
            require_core_usage_capture
            and not record.core_usage_capture_complete
        ):
            raise IntegrityError(
                "external response is content-replayable but core-usage-capture-incomplete"
            )
        # Resume of the exact same call is intentionally idempotent. Reuse of
        # provider identities across different calls in this bundle was
        # rejected at load time.
        self._resolved_call_ids.add(request.call_id)
        return record

    def coverage(
        self, expected_requests: Iterable[CallRequest] | None = None
    ) -> dict[str, Any]:
        if expected_requests is None:
            expected = set(self._resolved_call_ids)
        else:
            expected = set()
            for request in expected_requests:
                validated = CallRequest.from_value(dict(request.value))
                if validated.call_id in expected:
                    raise ManifestError("coverage received a duplicate expected call")
                expected.add(validated.call_id)
        available = set(self._records)
        return {
            "format": "competitive-eval-external-response-coverage-v1",
            "bundle_records": len(available),
            "resolved_calls": len(self._resolved_call_ids),
            "expected_calls": len(expected),
            "missing_call_ids": sorted(expected - available),
            "unused_call_ids": sorted(available - expected),
            "all_expected_available": expected.issubset(available),
            "all_bundle_records_accounted_for": available == expected,
        }

    def assert_all_consumed(self) -> None:
        unused = set(self._records) - self._resolved_call_ids
        if unused:
            raise IntegrityError(
                f"external response bundle has {len(unused)} unused record(s)"
            )
