#!/usr/bin/env python3
"""Deterministically classify the bounded one-fetch language probe response.

This validator performs no network call and no external action.  ``PASS`` is
reserved for one exact canonical completed response.  A closed, canonical
fallback is reported separately as ``SAFE_FALLBACK`` and never counts as a
language-use pass.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from urusilla_hybrid_runtime.canonical import (  # noqa: E402
    JsonValidationError,
    canonical_json,
    sha256_text,
    strict_json_loads,
)
from urusilla_hybrid_runtime.records import PublicActionState  # noqa: E402
from urusilla_hybrid_runtime.sender import parse_sender_output  # noqa: E402


DEFAULT_PROBE_PATH = ROOT / "website" / "public" / "language-probe.json"
PROBE_SCHEMA = "urusilla-one-fetch-action-state-language-probe/1"
SITE_RELEASE_REVISION = "urusilla-site-2026-08-23.1"
RESPONSE_SCHEMA = "urusilla-one-fetch-language-probe-response/1"
PROBE_ID = "language-use-001"
PROFILE_FORMAT = "urusilla-public-action-state-draft/1"
CAPSULE_SHA256 = (
    "sha256:7942bb348c3b2b839a3f87304b7d850796c837afdc66177eb1a48e5a45f0f778"
)
CLAIM_SCOPE = (
    "This probe tests only one bounded semantic decode and encode under the "
    "development action-state profile layered on Urusilla 0.1.0. It does not "
    "test the core binary wire codec, the seven-act envelope, conversation "
    "authorization, adoption, general compatibility, or token efficiency."
)
SECTION_SHA256 = {
    "limits": "sha256:683292d1dc75a8643bba18c13663ae8a0ffb154ac92cc60149759292d7e5bb9e",
    "authority_boundary": "sha256:63610520fcd99e1452c3bbd9935ce70fabd1355be5aa719cce24c56b154fce90",
    "language_profile": "sha256:f150fe963a3b5e9a1471dd223496adeb3bc71ec4ffd4eebeba0a07d8a684b8e0",
    "symbol_table": "sha256:d50122daff38422a681f2911a9e5eee89b86273cce7409f8042695cd5f01cda3",
    "tasks": "sha256:828aaea06261e979740a352265bd9a0f0e6d629d06ebde004c73b21dd7b3baa1",
    "response_contract": "sha256:33e70f151c1d98ad84840d6f96b05cccb57da265bc5b9da391b5e18d787e5af1",
    "evaluation": "sha256:edb4515106487385279a4567f10c860000c0ba34159c5c4cbde7cf10cf42e0bd",
    "return_policy": "sha256:48a64f848d8fc82a8d9bd35d2ddb7668d6c052ec3f90b6fe3a4979b6500e9ec3",
}

DECODE_INPUT = {
    "format": PROFILE_FORMAT,
    "act": "resolve",
    "goal": {
        "p": "artifact.verify",
        "a": ["artifact-19"],
        "n": False,
        "src": "agent:sender",
    },
    "state": [
        {
            "p": "check.passed",
            "a": ["unit"],
            "n": True,
            "src": "runner:7",
        }
    ],
    "constraints": [
        {
            "p": "publish.allowed",
            "a": [],
            "n": True,
            "src": "policy:local",
            "hard": True,
        }
    ],
    "action": None,
    "outcome": {"status": "failed", "value": None, "evidence": []},
    "needs": [
        {
            "p": "diagnostic.required",
            "a": ["public-log"],
            "n": False,
            "src": None,
        }
    ],
    "uncertainty": [
        {
            "target": "failure.cause",
            "model": "unspecified",
            "confidence_ppm": None,
            "basis": [],
        }
    ],
}

EXPECTED_DECODE = {
    "act": "resolve",
    "goal": {
        "predicate": "artifact.verify",
        "arguments": ["artifact-19"],
        "truth": True,
        "source": "agent:sender",
    },
    "facts": [
        {
            "predicate": "check.passed",
            "arguments": ["unit"],
            "truth": False,
            "source": "runner:7",
        }
    ],
    "hard_constraints": [
        {
            "predicate": "publish.allowed",
            "arguments": [],
            "truth": False,
            "source": "policy:local",
        }
    ],
    "outcome": {"status": "failed", "value": None},
    "needs": [
        {
            "predicate": "diagnostic.required",
            "arguments": ["public-log"],
            "truth": True,
            "source": None,
        }
    ],
    "uncertainty": [
        {
            "target": "failure.cause",
            "model": "unspecified",
            "confidence_ppm": None,
        }
    ],
    "effect_authorized": False,
}

EXPECTED_CANDIDATE = {
    "format": PROFILE_FORMAT,
    "act": "resolve",
    "goal": {
        "p": "artifact.verify",
        "a": ["artifact-23"],
        "n": False,
        "src": "agent:beta",
    },
    "state": [
        {
            "p": "check.passed",
            "a": ["unit"],
            "n": True,
            "src": "runner:8",
        }
    ],
    "constraints": [
        {
            "p": "publish.allowed",
            "a": [],
            "n": True,
            "src": "policy:local",
            "hard": True,
        }
    ],
    "action": None,
    "outcome": {"status": "failed", "value": None, "evidence": []},
    "needs": [
        {
            "p": "diagnostic.required",
            "a": ["public-log"],
            "n": False,
            "src": None,
        }
    ],
    "uncertainty": [
        {
            "target": "failure.cause",
            "model": "unspecified",
            "confidence_ppm": None,
            "basis": [],
        }
    ],
}

EXPECTED_ENCODE = {
    "status": "ok",
    "candidates": [EXPECTED_CANDIDATE],
    "unsupported": [],
    "failure": None,
}

EXPECTED_COMPLETED = {
    "schema_version": RESPONSE_SCHEMA,
    "probe_id": PROBE_ID,
    "disposition": "completed",
    "decode": EXPECTED_DECODE,
    "encode": EXPECTED_ENCODE,
    "fallback": None,
}

DECODE_SLOT_MAPPING = {
    "record.act": "decode.act",
    "record.goal": "decode.goal",
    "record.state": "decode.facts",
    "record.constraints where hard is true": "decode.hard_constraints",
    "record.outcome status and value": "decode.outcome",
    "record.needs": "decode.needs",
    "record.uncertainty": "decode.uncertainty",
    "authority_boundary.external_effects_authorized": "decode.effect_authorized",
}

ATOM_MAPPING = {
    "p": "predicate",
    "a": "arguments",
    "n false": "truth true",
    "n true": "truth false",
    "src": "source",
}

ENCODE_SLOT_MAPPING = {
    "artifact.verify": "goal",
    "check.passed": "state",
    "hard publish.allowed": "constraints",
    "diagnostic.required": "needs",
    "failure.cause uncertainty": "uncertainty",
}

ENCODE_SOURCE_TEXT = (
    "Agent agent:beta publicly resolves artifact.verify for artifact-23. "
    "check.passed(unit) is explicitly false, observed by runner:8. "
    "publish.allowed is explicitly false as a hard constraint from policy:local. "
    "The outcome status is failed and its value is null. There is no public "
    "outcome evidence. diagnostic.required(public-log) is explicitly true with "
    "unknown source. failure.cause under model unspecified has null confidence "
    "and no uncertainty basis. No action is present or authorized."
)


class ProbeValidationError(ValueError):
    """Raised when the public probe artifact is internally inconsistent."""


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ProbeValidationError(f"{path} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], path: str) -> None:
    if set(value) != fields:
        raise ProbeValidationError(f"{path} fields differ")


def _canonical_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))


def expected_decode_projection() -> dict[str, Any]:
    return deepcopy(EXPECTED_DECODE)


def expected_encode_candidate() -> dict[str, Any]:
    return deepcopy(EXPECTED_CANDIDATE)


def expected_sender_output() -> dict[str, Any]:
    return deepcopy(EXPECTED_ENCODE)


def expected_completed_response() -> dict[str, Any]:
    return deepcopy(EXPECTED_COMPLETED)


def load_probe(path: Path | str = DEFAULT_PROBE_PATH) -> dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProbeValidationError(f"cannot read probe: {exc}") from exc
    try:
        value = strict_json_loads(text)
    except JsonValidationError as exc:
        raise ProbeValidationError(f"probe JSON is invalid: {exc}") from exc
    try:
        return validate_probe(value)
    except ProbeValidationError:
        raise
    except ValueError as exc:
        raise ProbeValidationError(f"probe profile validation failed: {exc}") from exc


def validate_probe(value: Any) -> dict[str, Any]:
    probe = _object(value, "probe")
    _exact(
        probe,
        {
            "schema_version",
            "site_release_revision",
            "probe_id",
            "name",
            "classification",
            "claim_scope",
            "purpose",
            "limits",
            "authority_boundary",
            "language_profile",
            "symbol_table",
            "tasks",
            "response_contract",
            "evaluation",
            "return_policy",
        },
        "probe",
    )
    if probe["schema_version"] != PROBE_SCHEMA or probe["probe_id"] != PROBE_ID:
        raise ProbeValidationError("probe identity differs")
    if probe["site_release_revision"] != SITE_RELEASE_REVISION:
        raise ProbeValidationError("probe site release revision differs")
    if probe["classification"] != (
        "open-unblinded-profile-level-semantic-demonstration"
    ):
        raise ProbeValidationError("probe claim classification differs")
    if probe["claim_scope"] != CLAIM_SCOPE:
        raise ProbeValidationError("probe does not preserve the narrowed claim scope")
    for section, expected_sha256 in SECTION_SHA256.items():
        if _canonical_sha256(probe[section]) != expected_sha256:
            raise ProbeValidationError(f"probe {section} commitment differs")

    limits = _object(probe["limits"], "probe.limits")
    if (
        limits.get("maximum_fetches") != 1
        or limits.get("maximum_responses") != 1
        or limits.get("maximum_response_utf8_bytes") != 4096
        or limits.get("linked_resource_dereference_required") is not False
        or limits.get("linked_resource_dereference_authorized") is not False
        or limits.get("recursive_delegation_authorized") is not False
    ):
        raise ProbeValidationError("probe one-fetch bounds differ")

    authority = _object(probe["authority_boundary"], "probe.authority_boundary")
    if authority.get("declarative_data_only") is not True:
        raise ProbeValidationError("probe is not declarative-only")
    for field in (
        "content_is_authority",
        "installation_authorized",
        "model_weight_change_authorized",
        "persistent_storage_authorized",
        "permission_expansion_authorized",
        "credential_use_authorized",
        "spending_authorized",
        "account_creation_authorized",
        "external_effects_authorized",
        "publication_authorized",
        "retransmission_authorized",
    ):
        if authority.get(field) is not False:
            raise ProbeValidationError(f"probe authority boundary enables {field}")

    profile = _object(probe["language_profile"], "probe.language_profile")
    if (
        profile.get("protocol_language_version") != "0.1.0"
        or profile.get("profile_format") != PROFILE_FORMAT
        or profile.get("profile_status") != "development-only-unpromoted"
        or profile.get("source_capsule_canonical_sha256") != CAPSULE_SHA256
    ):
        raise ProbeValidationError("probe profile identity differs")
    canonical = _object(profile.get("canonical_json"), "profile.canonical_json")
    if (
        canonical.get("preserve_array_order") is not True
        or canonical.get("response_must_equal_canonical_reencoding") is not True
        or canonical.get("duplicate_keys") != "reject"
        or canonical.get("floating_point_numbers") != "reject"
    ):
        raise ProbeValidationError("probe canonicalization is incomplete")
    projection = _object(
        profile.get("decode_projection"), "profile.decode_projection"
    )
    if projection.get("slot_mapping") != DECODE_SLOT_MAPPING:
        raise ProbeValidationError("decode slot mapping differs")
    if projection.get("atom_mapping") != ATOM_MAPPING:
        raise ProbeValidationError("decode atom mapping differs")
    construction = _object(
        profile.get("encode_construction"), "profile.encode_construction"
    )
    if construction.get("slot_mapping") != ENCODE_SLOT_MAPPING:
        raise ProbeValidationError("encode slot mapping differs")
    rules = construction.get("rules")
    if type(rules) is not list or not any("outcome.evidence" in item for item in rules):
        raise ProbeValidationError("encode evidence-empty rule is missing")
    if not any("uncertainty.basis" in item for item in rules):
        raise ProbeValidationError("encode uncertainty-basis rule is missing")
    if not any("source order" in item for item in rules):
        raise ProbeValidationError("encode array-order rule is missing")

    tasks = _object(probe["tasks"], "probe.tasks")
    _exact(tasks, {"decode", "encode"}, "probe.tasks")
    decode_task = _object(tasks["decode"], "probe.tasks.decode")
    if decode_task.get("input") != DECODE_INPUT:
        raise ProbeValidationError("decode input differs from its frozen preimage")
    if decode_task.get("input_canonical_sha256") != _canonical_sha256(DECODE_INPUT):
        raise ProbeValidationError("decode input digest differs")
    PublicActionState.from_object(decode_task["input"])

    encode_task = _object(tasks["encode"], "probe.tasks.encode")
    if encode_task.get("source_public_text") != ENCODE_SOURCE_TEXT:
        raise ProbeValidationError("encode source text is ambiguous or differs")
    if encode_task.get("expected_candidate_canonical_sha256") != _canonical_sha256(
        EXPECTED_CANDIDATE
    ):
        raise ProbeValidationError("encoded candidate digest differs")
    PublicActionState.from_object(EXPECTED_CANDIDATE)
    parse_sender_output(canonical_json(EXPECTED_ENCODE))

    contract = _object(probe["response_contract"], "probe.response_contract")
    if contract.get("schema_version") != RESPONSE_SCHEMA:
        raise ProbeValidationError("response schema identity differs")
    if set(contract.get("exact_top_level_fields", [])) != set(EXPECTED_COMPLETED):
        raise ProbeValidationError("response top-level contract differs")
    fallback = _object(contract.get("fallback"), "response_contract.fallback")
    if set(fallback.get("fallback_exact_fields", [])) != {
        "route",
        "stage",
        "reason_code",
        "reason",
    }:
        raise ProbeValidationError("fallback field contract differs")

    evaluation = _object(probe["evaluation"], "probe.evaluation")
    expected_text = canonical_json(EXPECTED_COMPLETED)
    if evaluation.get("decoded_projection_canonical_sha256") != _canonical_sha256(
        EXPECTED_DECODE
    ):
        raise ProbeValidationError("decode projection digest differs")
    if evaluation.get("completed_response_canonical_sha256") != sha256_text(
        expected_text
    ):
        raise ProbeValidationError("completed response digest differs")
    if evaluation.get("completed_response_utf8_bytes") != len(
        expected_text.encode("utf-8")
    ):
        raise ProbeValidationError("completed response byte count differs")
    return deepcopy(probe)


def _classification(
    classification: str, *, reason_code: str, language_pass: bool
) -> dict[str, Any]:
    return {
        "classification": classification,
        "language_pass": language_pass,
        "safe_fallback": classification == "SAFE_FALLBACK",
        "reason_code": reason_code,
    }


def classify_response(probe_value: Any, response_text: str) -> dict[str, Any]:
    """Classify one response without executing or publishing anything."""

    try:
        probe = validate_probe(probe_value)
    except (ProbeValidationError, JsonValidationError, ValueError) as exc:
        raise ProbeValidationError(f"cannot evaluate against invalid probe: {exc}") from exc
    if type(response_text) is not str:
        return _classification("FAIL", reason_code="response-not-text", language_pass=False)
    maximum_bytes = probe["limits"]["maximum_response_utf8_bytes"]
    try:
        response_bytes = response_text.encode("utf-8")
    except UnicodeEncodeError:
        return _classification("FAIL", reason_code="response-not-utf8", language_pass=False)
    if len(response_bytes) > maximum_bytes:
        return _classification("FAIL", reason_code="response-too-large", language_pass=False)
    try:
        response = strict_json_loads(response_text, max_bytes=maximum_bytes)
        if canonical_json(response) != response_text:
            return _classification(
                "FAIL", reason_code="response-not-canonical", language_pass=False
            )
    except JsonValidationError:
        return _classification("FAIL", reason_code="response-invalid-json", language_pass=False)
    if type(response) is not dict or set(response) != set(EXPECTED_COMPLETED):
        return _classification("FAIL", reason_code="response-fields-differ", language_pass=False)
    if response.get("schema_version") != RESPONSE_SCHEMA or response.get("probe_id") != PROBE_ID:
        return _classification("FAIL", reason_code="response-domain-differs", language_pass=False)

    disposition = response.get("disposition")
    if disposition == "completed":
        expected_text = canonical_json(EXPECTED_COMPLETED)
        if response != EXPECTED_COMPLETED or response_text != expected_text:
            return _classification(
                "FAIL", reason_code="completed-semantics-differ", language_pass=False
            )
        evaluation = probe["evaluation"]
        if (
            _canonical_sha256(response["decode"])
            != evaluation["decoded_projection_canonical_sha256"]
            or _canonical_sha256(response["encode"]["candidates"][0])
            != probe["tasks"]["encode"]["expected_candidate_canonical_sha256"]
            or sha256_text(response_text)
            != evaluation["completed_response_canonical_sha256"]
        ):
            return _classification(
                "FAIL", reason_code="completed-digest-differs", language_pass=False
            )
        try:
            PublicActionState.from_object(response["encode"]["candidates"][0])
            parse_sender_output(canonical_json(response["encode"]))
        except ValueError:
            return _classification(
                "FAIL", reason_code="encoded-profile-invalid", language_pass=False
            )
        return _classification("PASS", reason_code="exact-semantic-match", language_pass=True)

    if disposition == "fallback":
        if response.get("decode") is not None or response.get("encode") is not None:
            return _classification(
                "FAIL", reason_code="fallback-contains-partial-output", language_pass=False
            )
        fallback = response.get("fallback")
        if type(fallback) is not dict or set(fallback) != {
            "route",
            "stage",
            "reason_code",
            "reason",
        }:
            return _classification("FAIL", reason_code="fallback-fields-differ", language_pass=False)
        fallback_contract = probe["response_contract"]["fallback"]
        if fallback.get("route") not in fallback_contract["route_values"]:
            return _classification("FAIL", reason_code="fallback-route-invalid", language_pass=False)
        if fallback.get("stage") not in fallback_contract["stage_values"]:
            return _classification("FAIL", reason_code="fallback-stage-invalid", language_pass=False)
        if fallback.get("reason_code") not in fallback_contract["reason_code_values"]:
            return _classification("FAIL", reason_code="fallback-reason-code-invalid", language_pass=False)
        reason = fallback.get("reason")
        if (
            type(reason) is not str
            or not 1 <= len(reason) <= 256
            or reason != reason.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in reason)
        ):
            return _classification("FAIL", reason_code="fallback-reason-invalid", language_pass=False)
        return _classification(
            "SAFE_FALLBACK", reason_code="closed-safe-fallback", language_pass=False
        )

    return _classification("FAIL", reason_code="disposition-invalid", language_pass=False)


def _read_response(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", help="Canonical response JSON path, or - for stdin")
    parser.add_argument(
        "--probe",
        default=str(DEFAULT_PROBE_PATH),
        help="Path to the one-fetch probe JSON",
    )
    args = parser.parse_args(argv)
    try:
        probe = load_probe(args.probe)
        response_text = _read_response(args.response)
        result = classify_response(probe, response_text)
    except (OSError, UnicodeError, ProbeValidationError) as exc:
        print(canonical_json({"classification": "FAIL", "error": str(exc)}))
        return 1
    print(canonical_json(result))
    if result["classification"] == "PASS":
        return 0
    if result["classification"] == "SAFE_FALLBACK":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
