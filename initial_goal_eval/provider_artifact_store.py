"""Portable validation of supplied external provider-record preimages.

The installable initial-goal verifier cannot import the research-only
``competitive_eval`` package.  This module therefore freezes the exact v1
external bundle/profile/request/response rules needed to recheck a supplied
provider record before a receipt may summarize it.

This is a content verifier, not an authenticator.  A self-consistent fabricated
bundle can still pass these checks.  Provider signatures, operator identity,
independence, and provider-specific re-normalization of the raw receipt remain
outside this boundary and must stay fail-closed in the claim verifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .contract import (
    VerificationError,
    _count,
    _exact,
    _list,
    _object,
    canonical_json,
    sha256_ref,
    strict_json_loads,
)
from .terminal_contract import CAPTURE_TERMINAL_STATUSES


PROVIDER_ARTIFACTS_SCHEMA = "urusilla-initial-goal-provider-artifacts/1"
EXECUTION_PROFILE_FORMAT = "competitive-eval-external-execution-profile-v1"
CALL_FORMAT = "competitive-eval-call-request-v1"
CAPTURED_RESPONSE_FORMAT = "competitive-eval-captured-response-v1"
EXTERNAL_RECORD_FORMAT = "competitive-eval-external-response-record-v1"
EXTERNAL_BUNDLE_FORMAT = "competitive-eval-external-response-bundle-v1"
PROVENANCE_STATUS = "content-bound-not-authenticated"
ROLE_MAPPING = "provider-neutral-role-content-v1"
ALLOWED_USE = "content-replay-and-core-usage-capture-only"
EXTERNAL_CLAIM_BLOCKERS = (
    "raw provider observation was not re-normalized by this module",
    "content hashes do not authenticate a provider or operator",
    "research token partition and full task ledger are not assembled",
    "the competitive runner does not consume the hybrid capture path or assemble "
    "it into the authenticated full-task study ledger",
    "cross-bundle provider receipt replay is not indexed",
)

_BARE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_SOURCE_KINDS = frozenset({"provider", "provider-ui", "unavailable"})
_SETTINGS_STATUSES = frozenset({"confirmed-exact", "partial", "unknown"})
_USAGE_STATUSES = frozenset({"complete", "partial", "unavailable"})
_REASONING_ACCOUNTING = frozenset(
    {"included-in-output", "separately-reported", "not-reported"}
)


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise VerificationError(f"{label} must be non-empty text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise VerificationError(f"{label} is not valid UTF-8 text") from exc
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _bare_sha(value: Any, label: str) -> str:
    if type(value) is not str or _BARE_SHA256.fullmatch(value) is None:
        raise VerificationError(f"{label} must be a lowercase bare SHA-256 digest")
    return value


def _optional_bare_sha(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _bare_sha(value, label)


def _bare_digest(value: Any) -> str:
    return sha256_ref(value).removeprefix("sha256:")


def _bare_bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    core = dict(value)
    core.pop(field, None)
    return _bare_digest(core)


def _sequence_sha256(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        raw = value.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _optional_count(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _count(value, label)


def _validate_decimal(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise VerificationError(f"{label} must be a nonnegative plain decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise VerificationError(f"{label} is not a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise VerificationError(f"{label} must be finite and nonnegative")
    return value


def _validate_execution_profile(raw: Any) -> dict[str, Any]:
    profile = _object(raw, "provider execution profile")
    _exact(
        profile,
        {
            "format",
            "provider_id",
            "api_id",
            "role_mapping",
            "normalizer_id",
            "normalizer_sha256",
            "profile_sha256",
        },
        "provider execution profile",
    )
    if profile["format"] != EXECUTION_PROFILE_FORMAT:
        raise VerificationError("provider execution profile format differs")
    _text(profile["provider_id"], "provider execution profile.provider_id")
    _text(profile["api_id"], "provider execution profile.api_id")
    if profile["role_mapping"] != ROLE_MAPPING:
        raise VerificationError("provider execution profile role mapping differs")
    normalizer_id = _optional_text(
        profile["normalizer_id"], "provider execution profile.normalizer_id"
    )
    normalizer_sha256 = _optional_bare_sha(
        profile["normalizer_sha256"],
        "provider execution profile.normalizer_sha256",
    )
    if (normalizer_id is None) is not (normalizer_sha256 is None):
        raise VerificationError("provider normalizer id and digest must be paired")
    supplied = _bare_sha(
        profile["profile_sha256"], "provider execution profile.profile_sha256"
    )
    if _digest_without(profile, "profile_sha256") != supplied:
        raise VerificationError("provider execution profile digest mismatch")
    return _detach(profile)


def _validate_call_request(raw: Any) -> tuple[dict[str, Any], dict[str, str]]:
    request = _object(raw, "provider call request")
    _exact(
        request,
        {
            "format",
            "episode_id",
            "turn_index",
            "attempt_index",
            "purpose",
            "agent",
            "model_ref",
            "arm",
            "messages",
            "generation",
            "idempotency_key",
            "mock_metadata",
            "call_id",
        },
        "provider call request",
    )
    if request["format"] != CALL_FORMAT:
        raise VerificationError("provider call request format differs")
    episode_id = _text(request["episode_id"], "provider call request.episode_id")
    turn_index = _count(request["turn_index"], "provider call request.turn_index")
    attempt_index = _count(
        request["attempt_index"], "provider call request.attempt_index"
    )
    if request["purpose"] not in {"runtime", "format_repair"}:
        raise VerificationError("provider call request purpose differs")
    if request["agent"] not in {"A", "B"}:
        raise VerificationError("provider call request agent differs")
    model_ref = _object(request["model_ref"], "provider call request.model_ref")
    _exact(
        model_ref,
        {"family_code", "logical_model_id"},
        "provider call request.model_ref",
    )
    _text(model_ref["family_code"], "provider call request.model_ref.family_code")
    _text(
        model_ref["logical_model_id"],
        "provider call request.model_ref.logical_model_id",
    )
    _text(request["arm"], "provider call request.arm")
    messages = _list(request["messages"], "provider call request.messages")
    if not messages:
        raise VerificationError("provider call request messages are empty")
    for index, raw_message in enumerate(messages):
        message = _object(raw_message, f"provider call request.messages[{index}]")
        _exact(
            message,
            {"role", "content"},
            f"provider call request.messages[{index}]",
        )
        if message["role"] not in {"system", "user", "assistant"}:
            raise VerificationError("provider call request message role differs")
        if type(message["content"]) is not str:
            raise VerificationError("provider call request message content is not text")
        try:
            message["content"].encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VerificationError(
                "provider call request message content is not UTF-8"
            ) from exc
    generation = _object(
        request["generation"], "provider call request.generation"
    )
    _exact(
        generation,
        {
            "temperature",
            "maximum_output_tokens",
            "tools",
            "web",
            "grounding",
        },
        "provider call request.generation",
    )
    if generation != {
        "temperature": 0,
        "maximum_output_tokens": 250,
        "tools": False,
        "web": False,
        "grounding": False,
    }:
        raise VerificationError("provider call request generation settings changed")
    mock = _object(request["mock_metadata"], "provider call request.mock_metadata")
    _exact(
        mock,
        {"scenario_key", "gold_answer_present"},
        "provider call request.mock_metadata",
    )
    _text(mock["scenario_key"], "provider call request.mock_metadata.scenario_key")
    if mock["gold_answer_present"] is not False:
        raise VerificationError("provider call request contains a gold answer")
    expected_idempotency = _bare_bytes_digest(
        (
            f"{episode_id}|{turn_index}|{attempt_index}|{request['purpose']}"
        ).encode("utf-8")
    )
    if request["idempotency_key"] != expected_idempotency:
        raise VerificationError("provider call request idempotency key mismatch")
    call_id = _bare_sha(request["call_id"], "provider call request.call_id")
    if _digest_without(request, "call_id") != call_id:
        raise VerificationError("provider call request call ID digest mismatch")
    detached = _detach(request)
    return detached, {
        "call_id": call_id,
        "request_sha256": _bare_digest(detached),
        "settings_sha256": _bare_digest(
            {"model_ref": detached["model_ref"], "generation": detached["generation"]}
        ),
    }


def _validate_provider_observation(
    raw: Any,
    *,
    request: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    observation = _object(raw, "provider response observation")
    _exact(
        observation,
        {
            "source_kind",
            "provider_id",
            "request_id",
            "response_id",
            "resolved_model_id",
            "effective_settings_status",
            "raw_receipt_utf8",
            "raw_receipt_sha256",
        },
        "provider response observation",
    )
    source_kind = observation["source_kind"]
    if source_kind not in _SOURCE_KINDS:
        raise VerificationError("provider response source kind differs")
    if observation["provider_id"] != profile["provider_id"]:
        raise VerificationError("provider response provider differs from profile")
    _text(observation["provider_id"], "provider response observation.provider_id")
    request_id = _optional_text(
        observation["request_id"], "provider response observation.request_id"
    )
    response_id = _optional_text(
        observation["response_id"], "provider response observation.response_id"
    )
    resolved_model_id = _optional_text(
        observation["resolved_model_id"],
        "provider response observation.resolved_model_id",
    )
    if (
        resolved_model_id is not None
        and resolved_model_id != request["model_ref"]["logical_model_id"]
    ):
        raise VerificationError("provider response model differs from request")
    settings_status = observation["effective_settings_status"]
    if settings_status not in _SETTINGS_STATUSES:
        raise VerificationError("provider response settings status differs")
    raw_receipt = observation["raw_receipt_utf8"]
    raw_sha = observation["raw_receipt_sha256"]
    if raw_receipt is None:
        if raw_sha is not None:
            raise VerificationError("raw receipt digest exists without exact bytes")
    else:
        if type(raw_receipt) is not str or not raw_receipt:
            raise VerificationError("raw provider receipt must be non-empty text")
        try:
            raw_bytes = raw_receipt.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VerificationError("raw provider receipt is not UTF-8") from exc
        if _bare_sha(raw_sha, "raw provider receipt digest") != _bare_bytes_digest(
            raw_bytes
        ):
            raise VerificationError("raw provider receipt digest mismatch")
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
        raise VerificationError(
            "provider capture requires IDs, exact settings, model, and raw receipt"
        )
    if source_kind == "unavailable":
        if any(
            item is not None
            for item in (
                request_id,
                response_id,
                resolved_model_id,
                raw_receipt,
                raw_sha,
            )
        ):
            raise VerificationError("unavailable provider observation carries evidence")
        if settings_status != "unknown":
            raise VerificationError("unavailable provider settings must stay unknown")
    return _detach(observation), provider_complete


def _validate_external_usage(raw: Any) -> tuple[dict[str, Any], bool]:
    usage = _object(raw, "provider response usage")
    _exact(
        usage,
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
        },
        "provider response usage",
    )
    status = usage["status"]
    if status not in _USAGE_STATUSES:
        raise VerificationError("provider response usage status differs")
    input_tokens = _optional_count(usage["input_tokens"], "usage.input_tokens")
    output_tokens = _optional_count(usage["output_tokens"], "usage.output_tokens")
    total_tokens = _optional_count(usage["total_tokens"], "usage.total_tokens")
    cache_read = _optional_count(
        usage["cache_read_tokens"], "usage.cache_read_tokens"
    )
    cache_write = _optional_count(
        usage["cache_write_tokens"], "usage.cache_write_tokens"
    )
    reasoning = _optional_count(
        usage["reasoning_tokens_subset"], "usage.reasoning_tokens_subset"
    )
    reasoning_accounting = usage["reasoning_accounting"]
    if reasoning_accounting not in _REASONING_ACCOUNTING:
        raise VerificationError("provider reasoning accounting differs")
    _validate_decimal(usage["actual_billed_usd"], "usage.actual_billed_usd")
    unclassified = usage["unclassified_usage_json"]
    if unclassified is not None:
        if type(unclassified) is not str:
            raise VerificationError("unclassified provider usage must be JSON text")
        parsed = strict_json_loads(unclassified)
        if canonical_json(parsed) != unclassified:
            raise VerificationError("unclassified provider usage is not canonical JSON")
    if status == "unavailable":
        if any(
            item is not None
            for item in (
                input_tokens,
                output_tokens,
                total_tokens,
                cache_read,
                cache_write,
                reasoning,
                usage["actual_billed_usd"],
                unclassified,
            )
        ):
            raise VerificationError("unavailable provider usage contains values")
        if reasoning_accounting != "not-reported":
            raise VerificationError("unavailable provider reasoning is classified")
        return _detach(usage), False
    if status == "complete" and any(
        item is None for item in (input_tokens, output_tokens, total_tokens)
    ):
        raise VerificationError("complete provider usage lacks a core token count")
    if status == "partial" and all(
        item is None for item in (input_tokens, output_tokens, total_tokens)
    ):
        raise VerificationError("partial provider usage has no token count")
    if input_tokens is not None:
        if cache_read is not None and cache_read > input_tokens:
            raise VerificationError("cache-read tokens exceed input tokens")
        if cache_write is not None and cache_write > input_tokens:
            raise VerificationError("cache-write tokens exceed input tokens")
    if all(item is not None for item in (input_tokens, output_tokens, total_tokens)):
        assert input_tokens is not None
        assert output_tokens is not None
        assert total_tokens is not None
        if reasoning_accounting == "included-in-output":
            if reasoning is None or reasoning > output_tokens:
                raise VerificationError("included reasoning is not an output subset")
            if total_tokens != input_tokens + output_tokens:
                raise VerificationError("provider total does not reconcile")
        elif reasoning_accounting == "separately-reported":
            if reasoning is None:
                raise VerificationError("separate reasoning count is missing")
            if total_tokens != input_tokens + output_tokens + reasoning:
                raise VerificationError("provider total omits separate reasoning")
        else:
            if reasoning is not None:
                raise VerificationError("unreported reasoning has a value")
            if total_tokens < input_tokens + output_tokens:
                raise VerificationError("provider total is below visible usage")
    elif reasoning_accounting != "not-reported" or reasoning is not None:
        raise VerificationError("partial provider totals classify reasoning")
    return _detach(usage), status == "complete" and unclassified is None


def project_initial_goal_usage(external_usage: Mapping[str, Any]) -> dict[str, Any]:
    """Reproject a generic normalized capture into the frozen task ledger.

    This does not parse or independently normalize provider-specific raw JSON.
    It only rechecks and maps the already normalized external usage object.
    """

    usage, complete = _validate_external_usage(external_usage)
    if not complete:
        raise VerificationError("provider usage is incomplete or unclassified")
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    total_tokens = usage["total_tokens"]
    assert type(input_tokens) is int
    assert type(output_tokens) is int
    assert type(total_tokens) is int
    accounting = usage["reasoning_accounting"]
    reasoning = usage["reasoning_tokens_subset"]
    if accounting == "not-reported":
        if reasoning is not None:
            raise VerificationError("unreported provider reasoning has a value")
        unclassified: int | None = None
    else:
        if type(reasoning) is not int or reasoning < 0:
            raise VerificationError("classified provider reasoning is missing")
        unclassified = 0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "unclassified_tokens": unclassified,
        "provider_total_tokens": total_tokens,
        "total_tokens": total_tokens,
        "hidden_accounting": accounting,
    }


@dataclass(frozen=True)
class ProviderRecordView:
    _record: Mapping[str, Any]
    _profile: Mapping[str, Any]
    _bundle_context: Mapping[str, Any]
    provider_observation_complete: bool
    usage_capture_complete: bool

    @property
    def record(self) -> Mapping[str, Any]:
        return _detach(self._record)

    @property
    def provider_record_sha256(self) -> str:
        return "sha256:" + str(self._record["record_sha256"])

    @property
    def call_id(self) -> str:
        return str(self._record["call_id"])

    @property
    def session_id(self) -> str:
        return str(self._record["episode_id"])

    @property
    def record_sequence(self) -> int:
        return int(self._record["sequence"])

    @property
    def call_request(self) -> Mapping[str, Any]:
        return _detach(self._record["call_request"])

    @property
    def producer_operator_id(self) -> str:
        return str(self._bundle_context["producer_operator_id"])

    @property
    def request_sha256(self) -> str:
        return "sha256:" + str(self._record["request_sha256"])

    @property
    def settings_sha256(self) -> str:
        return "sha256:" + str(self._record["response"]["binding"]["settings_sha256"])

    @property
    def response_sha256(self) -> str:
        return "sha256:" + str(self._record["response"]["response_sha256"])

    @property
    def execution_profile_sha256(self) -> str:
        return "sha256:" + str(self._profile["profile_sha256"])

    @property
    def input_sha256(self) -> str:
        return sha256_ref(
            {"provider_neutral_messages": self._record["call_request"]["messages"]}
        )

    @property
    def output_sha256(self) -> str | None:
        output = self._record["response"]["output_text"]
        return None if output is None else sha256_ref({"provider_output_text": output})

    @property
    def terminal_status(self) -> str:
        return str(self._record["response"]["status"])

    @property
    def observation(self) -> Mapping[str, Any]:
        return _detach(self._record["response"]["provider_observation"])

    @property
    def initial_goal_usage(self) -> Mapping[str, Any]:
        return project_initial_goal_usage(self._record["response"]["usage"])

    @property
    def execution_binding(self) -> Mapping[str, Any]:
        return {
            "run_id": "sha256:" + str(self._bundle_context["run_id"]),
            "run_manifest_sha256": "sha256:"
            + str(self._bundle_context["run_manifest_sha256"]),
            "episode_sequence_sha256": "sha256:"
            + str(self._bundle_context["episode_sequence_sha256"]),
            "execution_profile_sha256": self.execution_profile_sha256,
            "bundle_record_sequence": self.record_sequence,
        }

    @property
    def external_execution_binding_sha256(self) -> str:
        return sha256_ref(self.execution_binding)


def _validate_record(
    raw: Any,
    *,
    profile: Mapping[str, Any],
    bundle_context: Mapping[str, Any],
) -> ProviderRecordView:
    record = _object(raw, "provider response record")
    _exact(
        record,
        {
            "format",
            "sequence",
            "episode_id",
            "call_id",
            "request_sha256",
            "execution_profile_sha256",
            "call_request",
            "response",
            "record_sha256",
        },
        "provider response record",
    )
    if record["format"] != EXTERNAL_RECORD_FORMAT:
        raise VerificationError("provider response record format differs")
    _count(record["sequence"], "provider response record.sequence")
    request, request_digests = _validate_call_request(record["call_request"])
    if record["episode_id"] != request["episode_id"]:
        raise VerificationError("provider response episode binding mismatch")
    if record["call_id"] != request_digests["call_id"]:
        raise VerificationError("provider response call binding mismatch")
    if record["request_sha256"] != request_digests["request_sha256"]:
        raise VerificationError("provider response request digest mismatch")
    if record["execution_profile_sha256"] != profile["profile_sha256"]:
        raise VerificationError("provider response profile binding mismatch")
    response = _object(record["response"], "provider response")
    _exact(
        response,
        {
            "format",
            "binding",
            "status",
            "output_text",
            "provider_observation",
            "usage",
            "timing",
            "provenance_status",
            "response_sha256",
        },
        "provider response",
    )
    if response["format"] != CAPTURED_RESPONSE_FORMAT:
        raise VerificationError("captured provider response format differs")
    binding = _object(response["binding"], "provider response.binding")
    _exact(
        binding,
        {"call_id", "request_sha256", "settings_sha256"},
        "provider response.binding",
    )
    if binding != {
        "call_id": request_digests["call_id"],
        "request_sha256": request_digests["request_sha256"],
        "settings_sha256": request_digests["settings_sha256"],
    }:
        raise VerificationError("provider response binding differs from request")
    if response["status"] not in CAPTURE_TERMINAL_STATUSES:
        raise VerificationError("provider response terminal status differs")
    output = response["output_text"]
    if response["status"] == "completed" and type(output) is not str:
        raise VerificationError("completed provider response lacks text output")
    if response["status"] != "completed" and output is not None and type(output) is not str:
        raise VerificationError("noncompleted provider output must be text or null")
    if type(output) is str:
        try:
            output.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VerificationError("provider response output is not UTF-8") from exc
    observation, observation_complete = _validate_provider_observation(
        response["provider_observation"], request=request, profile=profile
    )
    _, usage_complete = _validate_external_usage(response["usage"])
    timing = _object(response["timing"], "provider response.timing")
    _exact(timing, {"model_ns"}, "provider response.timing")
    _optional_count(timing["model_ns"], "provider response.timing.model_ns")
    if response["provenance_status"] != PROVENANCE_STATUS:
        raise VerificationError("provider response overstates provenance")
    if _digest_without(response, "response_sha256") != _bare_sha(
        response["response_sha256"], "provider response.response_sha256"
    ):
        raise VerificationError("provider response digest mismatch")
    if _digest_without(record, "record_sha256") != _bare_sha(
        record["record_sha256"], "provider response record.record_sha256"
    ):
        raise VerificationError("provider response record digest mismatch")
    detached = _detach(record)
    detached["response"]["provider_observation"] = observation
    return ProviderRecordView(
        detached,
        _detach(profile),
        _detach(bundle_context),
        observation_complete,
        usage_complete,
    )


class ProviderArtifactStore:
    """Strict, repeatable lookup over exact supplied external bundles."""

    def __init__(self, value: Any):
        artifacts = _object(value, "provider_artifacts")
        _exact(
            artifacts,
            {"schema_version", "external_bundles"},
            "provider_artifacts",
        )
        if artifacts["schema_version"] != PROVIDER_ARTIFACTS_SCHEMA:
            raise VerificationError("provider artifact schema differs")
        bundles = _list(
            artifacts["external_bundles"], "provider_artifacts.external_bundles"
        )
        normalized_bundles: list[dict[str, Any]] = []
        records: dict[str, ProviderRecordView] = {}
        seen_bundle_refs: list[str] = []
        seen_run_ids: set[str] = set()
        global_identities: set[tuple[str, str]] = set()
        for bundle_index, raw_bundle in enumerate(bundles):
            path = f"provider_artifacts.external_bundles[{bundle_index}]"
            bundle = _object(raw_bundle, path)
            _exact(
                bundle,
                {
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
                },
                path,
            )
            if bundle["format"] != EXTERNAL_BUNDLE_FORMAT:
                raise VerificationError(f"{path}.format differs")
            run_id = _bare_sha(bundle["run_id"], f"{path}.run_id")
            if run_id in seen_run_ids:
                raise VerificationError("provider run is split across bundles")
            seen_run_ids.add(run_id)
            _bare_sha(bundle["run_manifest_sha256"], f"{path}.run_manifest_sha256")
            _bare_sha(
                bundle["episode_sequence_sha256"],
                f"{path}.episode_sequence_sha256",
            )
            producer = _object(bundle["producer"], f"{path}.producer")
            _exact(
                producer,
                {
                    "operator_id",
                    "capture_implementation_sha256",
                    "operator_attestation_sha256",
                },
                f"{path}.producer",
            )
            _text(producer["operator_id"], f"{path}.producer.operator_id")
            _optional_bare_sha(
                producer["capture_implementation_sha256"],
                f"{path}.producer.capture_implementation_sha256",
            )
            _optional_bare_sha(
                producer["operator_attestation_sha256"],
                f"{path}.producer.operator_attestation_sha256",
            )
            profile = _validate_execution_profile(bundle["execution_profile"])
            bundle_context = {
                "run_id": bundle["run_id"],
                "run_manifest_sha256": bundle["run_manifest_sha256"],
                "episode_sequence_sha256": bundle["episode_sequence_sha256"],
                "producer_operator_id": producer["operator_id"],
            }
            record_views: list[ProviderRecordView] = []
            for record_index, raw_record in enumerate(
                _list(bundle["records"], f"{path}.records")
            ):
                view = _validate_record(
                    raw_record, profile=profile, bundle_context=bundle_context
                )
                if view.record_sequence != record_index:
                    raise VerificationError("provider record sequence is not contiguous")
                record_ref = view.provider_record_sha256
                if record_ref in records:
                    raise VerificationError("provider record digest is replayed")
                observation = view.observation
                identities = {
                    ("call-id", view.call_id),
                    ("request-sha256", view.request_sha256),
                    ("response-sha256", view.response_sha256),
                    ("record-sha256", record_ref),
                    ("bundle-position", f"{run_id}:{record_index}"),
                }
                for kind, field in (
                    ("provider-request", "request_id"),
                    ("provider-response", "response_id"),
                    ("raw-receipt", "raw_receipt_sha256"),
                ):
                    identity = observation[field]
                    if identity is not None:
                        identities.add((kind, str(identity)))
                overlap = identities & global_identities
                if overlap:
                    raise VerificationError(
                        "provider artifact identity is replayed: "
                        + sorted(overlap)[0][0]
                    )
                global_identities.update(identities)
                records[record_ref] = view
                record_views.append(view)
            supplied_sequence = _bare_sha(
                bundle["record_sequence_sha256"], f"{path}.record_sequence_sha256"
            )
            if supplied_sequence != _sequence_sha256(
                view.record["record_sha256"] for view in record_views
            ):
                raise VerificationError("provider record sequence digest mismatch")
            if bundle["allowed_use"] != ALLOWED_USE:
                raise VerificationError("provider bundle allowed use differs")
            if bundle["claim_eligible"] is not False:
                raise VerificationError("provider bundle cannot be claim-eligible")
            if bundle["claim_blockers"] != list(EXTERNAL_CLAIM_BLOCKERS):
                raise VerificationError("provider bundle claim blockers differ")
            supplied_bundle_sha = _bare_sha(
                bundle["bundle_sha256"], f"{path}.bundle_sha256"
            )
            if _digest_without(bundle, "bundle_sha256") != supplied_bundle_sha:
                raise VerificationError("provider bundle digest mismatch")
            bundle_ref = "sha256:" + supplied_bundle_sha
            seen_bundle_refs.append(bundle_ref)
            normalized_bundles.append(_detach(bundle))
        if seen_bundle_refs != sorted(set(seen_bundle_refs)):
            raise VerificationError("provider bundles must be unique and digest-sorted")
        self._value = {
            "schema_version": PROVIDER_ARTIFACTS_SCHEMA,
            "external_bundles": normalized_bundles,
        }
        self._records = records

    @classmethod
    def from_object(cls, value: Any) -> "ProviderArtifactStore":
        return cls(value)

    @property
    def value(self) -> Mapping[str, Any]:
        return _detach(self._value)

    @property
    def record_refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    @property
    def record_count(self) -> int:
        return len(self._records)

    def resolve(self, provider_record_sha256: str) -> ProviderRecordView | None:
        return self._records.get(provider_record_sha256)

    def unreferenced(self, referenced: set[str]) -> tuple[str, ...]:
        return tuple(sorted(set(self._records) - referenced))


__all__ = [
    "PROVIDER_ARTIFACTS_SCHEMA",
    "ProviderArtifactStore",
    "ProviderRecordView",
    "project_initial_goal_usage",
]
