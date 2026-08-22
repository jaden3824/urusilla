"""Offline v2 validation for blinded payload-dependence probe packs.

This module is deliberately separate from the frozen initial-goal v1 method,
plan, result, receipt, and verifier schemas.  It performs no model or provider
call and grants no claim eligibility.  A successful validation establishes
only that the supplied, content-addressed records satisfy this local contract;
it cannot prove preregistration chronology, blinding, operator independence,
provider authenticity, or real-world causal dependence.
"""

from __future__ import annotations

from itertools import product
import json
import re
from typing import Any, Mapping, Sequence

from urusilla_hybrid_runtime.errors import ActionStateError
from urusilla_hybrid_runtime.records import (
    ACTION_STATE_FORMAT,
    validate_action_state,
)

from .contract import (
    HIDDEN_ACCOUNTING,
    VerificationError,
    _count,
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
    strict_json_loads,
)


CAUSAL_PROBE_PLAN_SCHEMA = "urusilla-initial-goal-causal-probe-plan/2"
CAUSAL_PROBE_PACK_SCHEMA = "urusilla-initial-goal-causal-probe-pack/2"
CAUSAL_PROBE_ASSIGNMENT_SCHEMA = (
    "urusilla-initial-goal-causal-probe-assignment-reveal/2"
)
CAUSAL_PROBE_RESULT_SCHEMA = "urusilla-initial-goal-causal-probe-result/2"
CAUSAL_PROBE_CALL_SCHEMA = "urusilla-initial-goal-causal-probe-call/2"
CAUSAL_PROBE_RESPONSE_SCHEMA = "urusilla-initial-goal-causal-probe-response/2"
CAUSAL_PROBE_USAGE_SCHEMA = "urusilla-initial-goal-causal-probe-usage/2"
CAUSAL_PROBE_SUMMARY_SCHEMA = "urusilla-initial-goal-causal-probe-summary/2"
CAUSAL_PROBE_FIELD_UNIVERSE_SCHEMA = (
    "urusilla-initial-goal-causal-probe-field-universe/2"
)
CAUSAL_PROBE_EXTERNAL_REFERENCE_SET_SCHEMA = (
    "urusilla-initial-goal-causal-probe-external-reference-set/2"
)
CAUSAL_PROBE_IDENTITY_ENVELOPE_SCHEMA = (
    "urusilla-initial-goal-causal-probe-identity-envelope/2"
)
CAUSAL_PROBE_ALIAS_BINDING_SCHEMA = (
    "urusilla-initial-goal-causal-probe-alias-binding/2"
)

OFFLINE_EVIDENCE_BOUNDARY = "offline-structural-diagnostic-only"
PLAN_STATUS = "frozen-preregistered-no-results"
TOKEN_SCOPE = "inclusive-all-phases-retries-repairs-and-fallbacks"
PLACEBO_EXPECTATION = "refuse-or-fallback"
EXTERNAL_REFERENCE_STATUS = "frozen-identity-only-no-observations"
EXTERNAL_REFERENCE_PURPOSE = "external-valid-payload-refusal-calibration"
CONDITIONS = ("a", "b", "missing", "shuffled")
AB_CONDITIONS = ("a", "b")
PLACEBO_CONDITIONS = ("missing", "shuffled")
RESPONSE_DISPOSITIONS = ("completed", "refused", "fallback")
FALLBACK_MODES = ("raw", "json")
REQUIRED_PER_SLOT_CONTRAST_ARMS = (
    "critical-field-flip",
    "semantic-invariant",
    "missing-or-corrupt",
    "no-payload-or-byte-lure",
)
VALIDATED_STRATUM_DIMENSIONS = (
    "domain_id",
    "receiver_family",
    "operator_id",
)
REQUIRED_EMPIRICAL_WORST_STRATUM_AXES = (
    "domain",
    "receiver-runtime",
    "operator",
    "principal",
    "slot-class",
)

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_DIMENSION_VALUES = 64
MAX_STRATA = 256
MAX_PROBES = 2_048
MAX_POINTER_TOKENS = 64
MAX_OUTPUT_TEXT_CHARS = 65_536

_BLIND_LABEL_RE = re.compile(r"^blind-[0-9a-f]{16,64}$")
_INVALID_POINTER_ESCAPE_RE = re.compile(r"~(?:[^01]|$)")
_MASKED_POINTER_VALUE = {"urusilla_causal_probe_v2_masked": True}


__all__ = [
    "AB_CONDITIONS",
    "ACTION_STATE_FORMAT",
    "CAUSAL_PROBE_ALIAS_BINDING_SCHEMA",
    "CAUSAL_PROBE_ASSIGNMENT_SCHEMA",
    "CAUSAL_PROBE_CALL_SCHEMA",
    "CAUSAL_PROBE_EXTERNAL_REFERENCE_SET_SCHEMA",
    "CAUSAL_PROBE_FIELD_UNIVERSE_SCHEMA",
    "CAUSAL_PROBE_IDENTITY_ENVELOPE_SCHEMA",
    "CAUSAL_PROBE_PACK_SCHEMA",
    "CAUSAL_PROBE_PLAN_SCHEMA",
    "CAUSAL_PROBE_RESPONSE_SCHEMA",
    "CAUSAL_PROBE_RESULT_SCHEMA",
    "CAUSAL_PROBE_SUMMARY_SCHEMA",
    "CAUSAL_PROBE_USAGE_SCHEMA",
    "CONDITIONS",
    "EXTERNAL_REFERENCE_STATUS",
    "EXTERNAL_REFERENCE_PURPOSE",
    "OFFLINE_EVIDENCE_BOUNDARY",
    "PLACEBO_CONDITIONS",
    "PLACEBO_EXPECTATION",
    "PLAN_STATUS",
    "TOKEN_SCOPE",
    "output_text_sha256",
    "validate_causal_probe_pack",
    "validate_causal_probe_pack_json",
    "validate_causal_probe_plan",
    "validate_causal_probe_plan_json",
]


def _bounded_size(value: Any, path: str) -> None:
    size = len(canonical_json(value).encode("utf-8"))
    if size > MAX_JSON_BYTES:
        raise VerificationError(f"{path} exceeds the resource limit")


def _bounded_list(value: Any, path: str, *, maximum: int) -> list[Any]:
    items = _list(value, path)
    if not items:
        raise VerificationError(f"{path} must not be empty")
    if len(items) > maximum:
        raise VerificationError(f"{path} exceeds {maximum} entries")
    return items


def _unique_identifiers(value: Any, path: str) -> list[str]:
    items = _bounded_list(value, path, maximum=MAX_DIMENSION_VALUES)
    result: list[str] = []
    for index, raw in enumerate(items):
        result.append(_identifier(raw, f"{path}[{index}]"))
    if len(set(result)) != len(result):
        raise VerificationError(f"{path} contains duplicates")
    return result


def _validate_stratum(value: Any, path: str) -> tuple[str, str, str]:
    stratum = _object(value, path)
    _exact(stratum, {"domain_id", "receiver_family", "operator_id"}, path)
    return (
        _identifier(stratum["domain_id"], f"{path}.domain_id"),
        _identifier(stratum["receiver_family"], f"{path}.receiver_family"),
        _identifier(stratum["operator_id"], f"{path}.operator_id"),
    )


def _validate_call_binding(value: Any, path: str) -> Mapping[str, Any]:
    binding = _object(value, path)
    _exact(
        binding,
        {
            "non_payload_context_sha256",
            "receiver_model_id",
            "model_settings_sha256",
            "capsule_sha256",
            "fresh_context_per_call",
        },
        path,
    )
    _sha(
        binding["non_payload_context_sha256"],
        f"{path}.non_payload_context_sha256",
    )
    _identifier(binding["receiver_model_id"], f"{path}.receiver_model_id")
    _sha(binding["model_settings_sha256"], f"{path}.model_settings_sha256")
    _sha(binding["capsule_sha256"], f"{path}.capsule_sha256")
    if binding["fresh_context_per_call"] is not True:
        raise VerificationError(f"{path}.fresh_context_per_call must be true")
    return binding


def _validate_operator(value: Any, path: str) -> str:
    operator = _object(value, path)
    _exact(
        operator,
        {"operator_id", "independent", "attestation_sha256"},
        path,
    )
    operator_id = _identifier(operator["operator_id"], f"{path}.operator_id")
    if operator["independent"] is not True:
        raise VerificationError(f"{path}.independent must be true")
    _sha(operator["attestation_sha256"], f"{path}.attestation_sha256")
    return operator_id


def _pointer_tokens(pointer: Any, path: str) -> tuple[str, ...]:
    if type(pointer) is not str or not pointer or not pointer.startswith("/"):
        raise VerificationError(f"{path} must be a non-root JSON pointer")
    if len(pointer) > 4_096 or _INVALID_POINTER_ESCAPE_RE.search(pointer):
        raise VerificationError(f"{path} is not a bounded RFC 6901 JSON pointer")
    tokens = tuple(
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    )
    if len(tokens) > MAX_POINTER_TOKENS:
        raise VerificationError(f"{path} exceeds {MAX_POINTER_TOKENS} tokens")
    return tokens


def _array_index(token: str, length: int, path: str) -> int:
    if (
        not token.isascii()
        or not token.isdigit()
        or (len(token) > 1 and token.startswith("0"))
    ):
        raise VerificationError(f"{path} has a non-canonical array index")
    index = int(token)
    if index >= length:
        raise VerificationError(f"{path} does not exist in the payload")
    return index


def _resolve_pointer(value: Any, tokens: Sequence[str], path: str) -> Any:
    current = value
    for token in tokens:
        if type(current) is dict:
            if token not in current:
                raise VerificationError(f"{path} does not exist in the payload")
            current = current[token]
        elif type(current) is list:
            current = current[_array_index(token, len(current), path)]
        else:
            raise VerificationError(f"{path} traverses a scalar payload value")
    return current


def _mask_pointer(value: Any, tokens: Sequence[str], path: str) -> Any:
    detached = json.loads(canonical_json(value))
    parent = _resolve_pointer(detached, tokens[:-1], path)
    token = tokens[-1]
    if type(parent) is dict:
        if token not in parent:
            raise VerificationError(f"{path} does not exist in the payload")
        parent[token] = _MASKED_POINTER_VALUE
    elif type(parent) is list:
        parent[_array_index(token, len(parent), path)] = _MASKED_POINTER_VALUE
    else:
        raise VerificationError(f"{path} traverses a scalar payload value")
    return detached


def _validate_single_pointer_difference(
    payload_a: Any,
    payload_b: Any,
    pointer: str,
    path: str,
) -> None:
    tokens = _pointer_tokens(pointer, f"{path}.critical_pointer")
    value_a = _resolve_pointer(payload_a, tokens, f"{path}.critical_pointer")
    value_b = _resolve_pointer(payload_b, tokens, f"{path}.critical_pointer")
    if type(value_a) in {dict, list} or type(value_b) in {dict, list}:
        raise VerificationError(
            f"{path}.critical_pointer must identify one scalar JSON value"
        )
    if type(value_a) is not type(value_b):
        raise VerificationError(
            f"{path}.critical_pointer changes the JSON value type"
        )
    if canonical_json(value_a) == canonical_json(value_b):
        raise VerificationError(f"{path} A/B critical values do not differ")
    masked_a = _mask_pointer(payload_a, tokens, f"{path}.critical_pointer")
    masked_b = _mask_pointer(payload_b, tokens, f"{path}.critical_pointer")
    if canonical_json(masked_a) != canonical_json(masked_b):
        raise VerificationError(
            f"{path} A/B payloads differ outside the critical JSON pointer"
        )


def _validate_field_universe(
    value: Any,
    path: str,
) -> tuple[
    Mapping[str, Any],
    dict[str, frozenset[str]],
    Mapping[str, Any],
]:
    universe = _object(value, path)
    _exact(universe, {"schema_version", "fields"}, path)
    if universe["schema_version"] != CAUSAL_PROBE_FIELD_UNIVERSE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    raw_fields = _bounded_list(
        universe["fields"], f"{path}.fields", maximum=MAX_PROBES
    )
    pointers_by_field: dict[str, frozenset[str]] = {}
    owner_by_pointer: dict[str, str] = {}
    owner_by_semantic_definition: dict[str, str] = {}
    alias_bindings: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_fields):
        field_path = f"{path}.fields[{index}]"
        field = _object(raw, field_path)
        _exact(
            field,
            {
                "field_id",
                "canonical_pointer",
                "pointer_aliases",
                "semantic_definition_sha256",
            },
            field_path,
        )
        field_id = _identifier(field["field_id"], f"{field_path}.field_id")
        if field_id in pointers_by_field:
            raise VerificationError(f"{path} contains duplicate stable field IDs")
        canonical_pointer = field["canonical_pointer"]
        _pointer_tokens(canonical_pointer, f"{field_path}.canonical_pointer")
        raw_aliases = _list(field["pointer_aliases"], f"{field_path}.pointer_aliases")
        if len(raw_aliases) > MAX_POINTER_TOKENS:
            raise VerificationError(f"{field_path}.pointer_aliases exceeds the limit")
        aliases: list[str] = []
        for alias_index, alias in enumerate(raw_aliases):
            _pointer_tokens(alias, f"{field_path}.pointer_aliases[{alias_index}]")
            aliases.append(alias)
        pointers = [canonical_pointer, *aliases]
        if len(set(pointers)) != len(pointers):
            raise VerificationError(f"{field_path} contains duplicate pointer aliases")
        semantic_definition = _sha(
            field["semantic_definition_sha256"],
            f"{field_path}.semantic_definition_sha256",
        )
        prior_semantic_owner = owner_by_semantic_definition.setdefault(
            semantic_definition, field_id
        )
        if prior_semantic_owner != field_id:
            raise VerificationError(
                f"{path} assigns one semantic definition to multiple stable field IDs"
            )
        for pointer in pointers:
            prior_owner = owner_by_pointer.setdefault(pointer, field_id)
            if prior_owner != field_id:
                raise VerificationError(
                    f"{path} assigns one pointer alias to multiple stable field IDs"
                )
        pointers_by_field[field_id] = frozenset(pointers)
        alias_bindings.append(
            {
                "field_id": field_id,
                "canonical_pointer": canonical_pointer,
                "pointer_aliases": sorted(aliases),
            }
        )
    alias_binding = {
        "schema_version": CAUSAL_PROBE_ALIAS_BINDING_SCHEMA,
        "bindings": sorted(alias_bindings, key=lambda item: item["field_id"]),
    }
    return universe, pointers_by_field, alias_binding


def _validate_external_reference_set(value: Any, path: str) -> Mapping[str, Any]:
    reference = _object(value, path)
    _exact(
        reference,
        {
            "schema_version",
            "status",
            "purpose",
            "reference_set_id",
            "manifest_sha256",
            "selection_protocol_sha256",
            "validity_scorer_sha256",
            "source_id",
            "source_attestation_sha256",
            "independent_specifier_id",
            "independent_specification_sha256",
        },
        path,
    )
    if reference["schema_version"] != CAUSAL_PROBE_EXTERNAL_REFERENCE_SET_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if reference["status"] != EXTERNAL_REFERENCE_STATUS:
        raise VerificationError(f"{path}.status must remain identity-only")
    if reference["purpose"] != EXTERNAL_REFERENCE_PURPOSE:
        raise VerificationError(f"{path}.purpose differs")
    _identifier(reference["reference_set_id"], f"{path}.reference_set_id")
    _identifier(reference["source_id"], f"{path}.source_id")
    _identifier(
        reference["independent_specifier_id"],
        f"{path}.independent_specifier_id",
    )
    for field in (
        "manifest_sha256",
        "selection_protocol_sha256",
        "validity_scorer_sha256",
        "source_attestation_sha256",
        "independent_specification_sha256",
    ):
        _sha(reference[field], f"{path}.{field}")
    return reference


def _validate_identity_envelope(
    value: Any,
    path: str,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    dict[str, frozenset[str]],
    Mapping[str, Any],
    Mapping[str, Any],
]:
    envelope = _object(value, path)
    _exact(
        envelope,
        {
            "schema_version",
            "status",
            "field_universe",
            "external_refusal_calibration_reference_set",
        },
        path,
    )
    if envelope["schema_version"] != CAUSAL_PROBE_IDENTITY_ENVELOPE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if envelope["status"] != PLAN_STATUS:
        raise VerificationError(f"{path}.status differs")
    field_universe, pointers_by_field, alias_binding = _validate_field_universe(
        envelope["field_universe"], f"{path}.field_universe"
    )
    external_reference_set = _validate_external_reference_set(
        envelope["external_refusal_calibration_reference_set"],
        f"{path}.external_refusal_calibration_reference_set",
    )
    return (
        envelope,
        field_universe,
        pointers_by_field,
        alias_binding,
        external_reference_set,
    )


def output_text_sha256(output_text: str) -> str:
    """Return the v2 exact-output commitment used by probe expectations."""

    if (
        type(output_text) is not str
        or not output_text
        or len(output_text) > MAX_OUTPUT_TEXT_CHARS
    ):
        raise VerificationError(
            "output_text must be non-empty bounded text"
        )
    try:
        output_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise VerificationError("output_text is not UTF-8") from exc
    return sha256_ref({"provider_output_text": output_text})


def _validate_probe_spec(value: Any, path: str) -> Mapping[str, Any]:
    spec = _object(value, path)
    _exact(
        spec,
        {
            "probe_id",
            "stratum",
            "field_id",
            "payload_format",
            "critical_pointer",
            "call_binding",
            "payload_sha256",
            "expected_output_sha256",
            "placebo_expected_disposition",
            "shuffled_from",
        },
        path,
    )
    _identifier(spec["probe_id"], f"{path}.probe_id")
    _validate_stratum(spec["stratum"], f"{path}.stratum")
    _identifier(spec["field_id"], f"{path}.field_id")
    if spec["payload_format"] != ACTION_STATE_FORMAT:
        raise VerificationError(f"{path}.payload_format is unsupported")
    _pointer_tokens(spec["critical_pointer"], f"{path}.critical_pointer")
    _validate_call_binding(spec["call_binding"], f"{path}.call_binding")

    payloads = _object(spec["payload_sha256"], f"{path}.payload_sha256")
    _exact(payloads, CONDITIONS, f"{path}.payload_sha256")
    for condition in ("a", "b", "shuffled"):
        _sha(payloads[condition], f"{path}.payload_sha256.{condition}")
    if payloads["missing"] is not None:
        raise VerificationError(f"{path}.payload_sha256.missing must be null")
    if payloads["a"] == payloads["b"]:
        raise VerificationError(f"{path} A/B payload commitments must differ")

    expected = _object(
        spec["expected_output_sha256"], f"{path}.expected_output_sha256"
    )
    _exact(expected, AB_CONDITIONS, f"{path}.expected_output_sha256")
    for condition in AB_CONDITIONS:
        _sha(expected[condition], f"{path}.expected_output_sha256.{condition}")
    if expected["a"] == expected["b"]:
        raise VerificationError(f"{path} expected A/B outputs must flip")

    placebo = _object(
        spec["placebo_expected_disposition"],
        f"{path}.placebo_expected_disposition",
    )
    _exact(placebo, PLACEBO_CONDITIONS, f"{path}.placebo_expected_disposition")
    for condition in PLACEBO_CONDITIONS:
        if placebo[condition] != PLACEBO_EXPECTATION:
            raise VerificationError(
                f"{path}.placebo_expected_disposition.{condition} must be "
                f"{PLACEBO_EXPECTATION}"
            )

    shuffled_from = _object(spec["shuffled_from"], f"{path}.shuffled_from")
    _exact(shuffled_from, {"probe_id", "condition"}, f"{path}.shuffled_from")
    _identifier(shuffled_from["probe_id"], f"{path}.shuffled_from.probe_id")
    if shuffled_from["condition"] not in AB_CONDITIONS:
        raise VerificationError(f"{path}.shuffled_from.condition is invalid")
    return spec


def _validate_plan_internal(value: Any) -> tuple[Mapping[str, Any], dict[str, Any]]:
    _bounded_size(value, "causal_probe_plan")
    plan = _object(value, "causal_probe_plan")
    _exact(
        plan,
        {
            "schema_version",
            "status",
            "evidence_boundary",
            "domains",
            "receiver_families",
            "independent_operators",
            "preregistered_identity_envelope",
            "probe_specs",
            "assignment_commitment_sha256",
        },
        "causal_probe_plan",
    )
    if plan["schema_version"] != CAUSAL_PROBE_PLAN_SCHEMA:
        raise VerificationError("causal probe plan schema differs")
    if plan["status"] != PLAN_STATUS:
        raise VerificationError("causal probe plan status differs")
    if plan["evidence_boundary"] != OFFLINE_EVIDENCE_BOUNDARY:
        raise VerificationError("causal probe plan evidence boundary differs")

    (
        identity_envelope,
        field_universe,
        pointers_by_field,
        alias_binding,
        external_reference_set,
    ) = _validate_identity_envelope(
        plan["preregistered_identity_envelope"],
        "causal_probe_plan.preregistered_identity_envelope",
    )

    domains = _unique_identifiers(plan["domains"], "causal_probe_plan.domains")
    families = _unique_identifiers(
        plan["receiver_families"], "causal_probe_plan.receiver_families"
    )
    raw_operators = _bounded_list(
        plan["independent_operators"],
        "causal_probe_plan.independent_operators",
        maximum=MAX_DIMENSION_VALUES,
    )
    operator_ids = [
        _validate_operator(item, f"causal_probe_plan.independent_operators[{index}]")
        for index, item in enumerate(raw_operators)
    ]
    if len(set(operator_ids)) != len(operator_ids):
        raise VerificationError("causal_probe_plan.independent_operators contains duplicates")

    expected_strata = set(product(domains, families, operator_ids))
    if len(expected_strata) > MAX_STRATA:
        raise VerificationError("causal probe plan exceeds the stratum resource limit")

    raw_specs = _bounded_list(
        plan["probe_specs"],
        "causal_probe_plan.probe_specs",
        maximum=MAX_PROBES,
    )
    specs: dict[str, Mapping[str, Any]] = {}
    specs_by_stratum: dict[tuple[str, str, str], list[str]] = {}
    model_by_family: dict[str, str] = {}
    family_by_model: dict[str, str] = {}
    context_owner: dict[str, str] = {}
    field_identity_coverage = {
        field_id: 0 for field_id in pointers_by_field
    }
    planned_pointer_usage: dict[str, int] = {}
    for index, raw in enumerate(raw_specs):
        path = f"causal_probe_plan.probe_specs[{index}]"
        spec = _validate_probe_spec(raw, path)
        probe_id = spec["probe_id"]
        if probe_id in specs:
            raise VerificationError("causal probe plan contains duplicate probe IDs")
        stratum = _validate_stratum(spec["stratum"], f"{path}.stratum")
        if stratum not in expected_strata:
            raise VerificationError(f"{path} references an undeclared stratum")
        field_id = spec["field_id"]
        allowed_pointers = pointers_by_field.get(field_id)
        if allowed_pointers is None:
            raise VerificationError(f"{path} references an undeclared stable field ID")
        pointer = spec["critical_pointer"]
        if pointer not in allowed_pointers:
            raise VerificationError(
                f"{path}.critical_pointer is not registered to its stable field ID"
            )
        field_identity_coverage[field_id] += 1
        planned_pointer_usage[pointer] = planned_pointer_usage.get(pointer, 0) + 1
        family = stratum[1]
        model_id = spec["call_binding"]["receiver_model_id"]
        prior_model = model_by_family.setdefault(family, model_id)
        if prior_model != model_id:
            raise VerificationError(
                f"{path} maps one receiver family to multiple model IDs"
            )
        prior_family = family_by_model.setdefault(model_id, family)
        if prior_family != family:
            raise VerificationError(
                f"{path} relabels one receiver model as multiple families"
            )
        context_digest = spec["call_binding"]["non_payload_context_sha256"]
        prior_probe = context_owner.setdefault(context_digest, probe_id)
        if prior_probe != probe_id:
            raise VerificationError(
                f"{path} reuses another probe's non-payload task context"
            )
        specs[probe_id] = spec
        specs_by_stratum.setdefault(stratum, []).append(probe_id)

    absent = expected_strata - set(specs_by_stratum)
    if absent:
        raise VerificationError(
            "causal probe plan has absent per-stratum probes: "
            f"{sorted(absent)}"
        )
    if len(specs) < 2:
        raise VerificationError(
            "causal probe plan needs at least two probes for shuffled placebos"
        )

    for probe_id, spec in specs.items():
        source = spec["shuffled_from"]
        source_id = source["probe_id"]
        if source_id == probe_id:
            raise VerificationError(f"probe {probe_id} shuffled placebo is self-sourced")
        donor = specs.get(source_id)
        if donor is None:
            raise VerificationError(f"probe {probe_id} shuffled source is unknown")
        source_condition = source["condition"]
        if (
            spec["payload_sha256"]["shuffled"]
            != donor["payload_sha256"][source_condition]
        ):
            raise VerificationError(
                f"probe {probe_id} shuffled payload commitment differs from its source"
            )
        if (
            spec["call_binding"]["non_payload_context_sha256"]
            == donor["call_binding"]["non_payload_context_sha256"]
        ):
            raise VerificationError(
                f"probe {probe_id} shuffled source must use a different task context"
            )

    assignment_commitment = _sha(
        plan["assignment_commitment_sha256"],
        "causal_probe_plan.assignment_commitment_sha256",
    )
    info = {
        "domains": domains,
        "families": families,
        "operator_ids": operator_ids,
        "expected_strata": expected_strata,
        "specs": specs,
        "spec_order": [spec["probe_id"] for spec in raw_specs],
        "assignment_commitment": assignment_commitment,
        "identity_envelope": identity_envelope,
        "field_universe": field_universe,
        "alias_binding": alias_binding,
        "field_identity_coverage": field_identity_coverage,
        "planned_pointer_usage": planned_pointer_usage,
        "external_reference_set": external_reference_set,
    }
    return plan, info


def validate_causal_probe_plan(value: Any) -> dict[str, Any]:
    """Validate a frozen v2 preregistration without observing any result."""

    plan, info = _validate_plan_internal(value)
    field_identity_coverage = dict(sorted(info["field_identity_coverage"].items()))
    covered_field_count = sum(count > 0 for count in field_identity_coverage.values())
    declared_field_count = len(field_identity_coverage)
    external_reference = info["external_reference_set"]
    per_stable_semantic_slot = [
        {
            "field_id": field_id,
            "planned_probes": field_identity_coverage[field_id],
            "required_arm_matrix_preregistered": False,
        }
        for field_id in sorted(field_identity_coverage)
    ]
    return {
        "schema_version": CAUSAL_PROBE_SUMMARY_SCHEMA,
        "valid": True,
        "plan_sha256": sha256_ref(plan),
        "strata": len(info["expected_strata"]),
        "probes": len(info["specs"]),
        "semantic_invariance_checked": False,
        "composition_holdout_checked": False,
        "no_payload_accuracy_measured": False,
        "declared_field_universe_covered": covered_field_count == declared_field_count,
        "declared_field_count": declared_field_count,
        "covered_field_count": covered_field_count,
        "field_identity_coverage": field_identity_coverage,
        "field_identity_coverage_basis": "preregistered-probe-specs-only",
        "critical_pointer_usage": dict(
            sorted(info["planned_pointer_usage"].items())
        ),
        "authoritative_coverage_unit": "stable-field-id",
        "field_universe_sha256": sha256_ref(info["field_universe"]),
        "alias_to_field_id_binding_sha256": sha256_ref(info["alias_binding"]),
        "preregistered_identity_envelope_sha256": sha256_ref(
            info["identity_envelope"]
        ),
        "field_identity_and_external_refusal_calibration_same_envelope_bound": True,
        "pack_binds_identity_envelope": False,
        "preregistration_chronology_verified": False,
        "identity_envelope_external_anchor_verified": False,
        "calibration_headline_seed_separated": False,
        "external_reference_set_identity_bound": True,
        "external_refusal_calibration_reference_set_identity_bound": True,
        "external_reference_set_id": external_reference["reference_set_id"],
        "external_reference_set_sha256": sha256_ref(external_reference),
        "external_refusal_calibration_purpose": external_reference["purpose"],
        "independent_specification_commitment_bound": True,
        "independent_specification_authenticated": False,
        "external_reference_observations_validated": False,
        "external_refusal_calibration_gate_implemented": False,
        "same_receiver_valid_ab_refusal_or_fallback_baseline_externally_anchored": False,
        "per_stable_semantic_slot": per_stable_semantic_slot,
        "required_per_slot_contrast_arms": list(REQUIRED_PER_SLOT_CONTRAST_ARMS),
        "per_slot_arm_matrix_validated": False,
        "pooled_intervention_pair_count_is_claim_gate": False,
        "validated_stratum_dimensions": list(VALIDATED_STRATUM_DIMENSIONS),
        "required_empirical_worst_stratum_axes": list(
            REQUIRED_EMPIRICAL_WORST_STRATUM_AXES
        ),
        "five_dimensional_strata_validated": False,
        "task_semantics_used_verdict_validated": False,
        "verdicts": {
            "payload_influenced_output": {
                "status": "not-evaluated-plan-only",
                "checks_passed": False,
                "claim_eligible": False,
            },
            "task_semantics_used": {
                "status": "not-validated",
                "checks_passed": False,
                "claim_eligible": False,
            },
        },
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "claim_eligible": False,
        "provider_or_model_calls_by_validator": 0,
    }


def validate_causal_probe_plan_json(text: str) -> dict[str, Any]:
    """Strict-JSON form of :func:`validate_causal_probe_plan`."""

    return validate_causal_probe_plan(strict_json_loads(text, max_bytes=MAX_JSON_BYTES))


def _validate_assignment_reveal(
    value: Any,
    info: Mapping[str, Any],
) -> dict[str, list[tuple[str, str]]]:
    reveal = _object(value, "causal_probe_pack.assignment_reveal")
    _exact(
        reveal,
        {"schema_version", "assignments"},
        "causal_probe_pack.assignment_reveal",
    )
    if reveal["schema_version"] != CAUSAL_PROBE_ASSIGNMENT_SCHEMA:
        raise VerificationError("causal probe assignment schema differs")
    if sha256_ref(reveal) != info["assignment_commitment"]:
        raise VerificationError("causal probe assignment commitment mismatch")

    assignments = _bounded_list(
        reveal["assignments"],
        "causal_probe_pack.assignment_reveal.assignments",
        maximum=MAX_PROBES,
    )
    by_probe: dict[str, list[tuple[str, str]]] = {}
    all_labels: set[str] = set()
    for index, raw in enumerate(assignments):
        path = f"causal_probe_pack.assignment_reveal.assignments[{index}]"
        assignment = _object(raw, path)
        _exact(assignment, {"probe_id", "slots"}, path)
        probe_id = _identifier(assignment["probe_id"], f"{path}.probe_id")
        if probe_id not in info["specs"]:
            raise VerificationError(f"{path} references an unknown probe")
        if probe_id in by_probe:
            raise VerificationError("causal probe reveal contains duplicate probes")
        slots = _list(assignment["slots"], f"{path}.slots")
        if len(slots) != len(CONDITIONS):
            raise VerificationError(f"{path}.slots must contain all four conditions")
        parsed: list[tuple[str, str]] = []
        variants: set[str] = set()
        for slot_index, raw_slot in enumerate(slots):
            slot_path = f"{path}.slots[{slot_index}]"
            slot = _object(raw_slot, slot_path)
            _exact(slot, {"blind_label", "condition"}, slot_path)
            blind_label = slot["blind_label"]
            if (
                type(blind_label) is not str
                or _BLIND_LABEL_RE.fullmatch(blind_label) is None
            ):
                raise VerificationError(f"{slot_path}.blind_label is not opaque")
            condition = slot["condition"]
            if condition not in CONDITIONS:
                raise VerificationError(f"{slot_path}.condition is invalid")
            if blind_label in all_labels:
                raise VerificationError("causal probe reveal reuses a blind label")
            if condition in variants:
                raise VerificationError(f"{path}.slots contains duplicate conditions")
            all_labels.add(blind_label)
            variants.add(condition)
            parsed.append((blind_label, condition))
        if variants != set(CONDITIONS):
            raise VerificationError(f"{path}.slots omits a required placebo or A/B call")
        by_probe[probe_id] = parsed

    if set(by_probe) != set(info["specs"]):
        raise VerificationError("causal probe reveal omits a preregistered probe")
    if list(by_probe) != info["spec_order"]:
        raise VerificationError("causal probe reveal order differs from the plan")
    return by_probe


def _validate_response(value: Any, digest: Any, path: str) -> Mapping[str, Any]:
    response = _object(value, path)
    _exact(
        response,
        {
            "schema_version",
            "provider_response_id",
            "disposition",
            "fallback_mode",
            "output_text",
            "output_sha256",
        },
        path,
    )
    if response["schema_version"] != CAUSAL_PROBE_RESPONSE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    _identifier(response["provider_response_id"], f"{path}.provider_response_id")
    disposition = response["disposition"]
    if disposition not in RESPONSE_DISPOSITIONS:
        raise VerificationError(f"{path}.disposition is invalid")
    fallback_mode = response["fallback_mode"]
    if disposition == "fallback":
        if fallback_mode not in FALLBACK_MODES:
            raise VerificationError(f"{path}.fallback_mode is invalid")
    elif fallback_mode is not None:
        raise VerificationError(f"{path}.fallback_mode must be null")

    output_text = response["output_text"]
    output_digest = response["output_sha256"]
    if output_text is None:
        if disposition != "refused" or output_digest is not None:
            raise VerificationError(f"{path} has an invalid null output")
    else:
        expected_digest = output_text_sha256(output_text)
        if output_digest != expected_digest:
            raise VerificationError(f"{path}.output_sha256 digest mismatch")
    response_digest = _sha(digest, f"{path}_sha256")
    if response_digest != sha256_ref(response):
        raise VerificationError(f"{path} digest mismatch")
    return response


def _validate_usage(value: Any, digest: Any, path: str) -> tuple[int | None, bool]:
    usage = _object(value, path)
    _exact(
        usage,
        {
            "schema_version",
            "scope",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "unclassified_tokens",
            "provider_total_tokens",
            "total_tokens",
            "hidden_accounting",
        },
        path,
    )
    if usage["schema_version"] != CAUSAL_PROBE_USAGE_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    if usage["scope"] != TOKEN_SCOPE:
        raise VerificationError(f"{path}.scope is not inclusive")
    count_fields = (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "unclassified_tokens",
        "provider_total_tokens",
        "total_tokens",
    )
    counts = {
        field: _count(usage[field], f"{path}.{field}", nullable=True)
        for field in count_fields
    }
    accounting = usage["hidden_accounting"]
    if accounting not in HIDDEN_ACCOUNTING:
        raise VerificationError(f"{path}.hidden_accounting is invalid")

    input_tokens = counts["input_tokens"]
    output_tokens = counts["output_tokens"]
    reasoning_tokens = counts["reasoning_tokens"]
    unclassified_tokens = counts["unclassified_tokens"]
    provider_total = counts["provider_total_tokens"]
    total = counts["total_tokens"]

    if accounting == "none" and reasoning_tokens != 0:
        raise VerificationError(f"{path}.reasoning_tokens must be zero for none")
    if accounting == "not-reported" and reasoning_tokens is not None:
        raise VerificationError(f"{path}.reasoning_tokens must be null when unreported")
    if accounting == "included-in-output" and (
        reasoning_tokens is None
        or output_tokens is None
        or reasoning_tokens > output_tokens
    ):
        raise VerificationError(f"{path}.reasoning_tokens is not an output subset")
    if accounting == "included-in-unclassified" and (
        reasoning_tokens is None
        or unclassified_tokens is None
        or reasoning_tokens > unclassified_tokens
    ):
        raise VerificationError(
            f"{path}.reasoning_tokens is not an unclassified subset"
        )
    if accounting == "separately-reported" and reasoning_tokens is None:
        raise VerificationError(f"{path}.reasoning_tokens is required when separate")

    if provider_total is not None and total != provider_total:
        raise VerificationError(f"{path}.provider_total_tokens differs from total_tokens")
    additive = [input_tokens, output_tokens, unclassified_tokens]
    if accounting == "separately-reported":
        additive.append(reasoning_tokens)
    if all(item is not None for item in additive):
        expected = sum(item for item in additive if item is not None)
        if total != expected:
            raise VerificationError(f"{path}.total_tokens does not reconcile to {expected}")
    elif total is not None and provider_total is None:
        raise VerificationError(f"{path}.total_tokens has an unclosed component")

    usage_digest = _sha(digest, f"{path}_sha256")
    if usage_digest != sha256_ref(usage):
        raise VerificationError(f"{path} digest mismatch")
    return total, total is not None


def _validate_call(
    value: Any,
    *,
    spec: Mapping[str, Any],
    condition: str,
    expected_blind_label: str,
    path: str,
) -> tuple[Mapping[str, Any], int | None]:
    call = _object(value, path)
    _exact(
        call,
        {
            "schema_version",
            "call_id",
            "request_id",
            "context_instance_id",
            "blind_label",
            "binding",
            "payload",
            "payload_sha256",
            "response",
            "response_sha256",
            "usage",
            "usage_sha256",
        },
        path,
    )
    if call["schema_version"] != CAUSAL_PROBE_CALL_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    _identifier(call["call_id"], f"{path}.call_id")
    _identifier(call["request_id"], f"{path}.request_id")
    _identifier(call["context_instance_id"], f"{path}.context_instance_id")
    if call["blind_label"] != expected_blind_label:
        raise VerificationError(f"{path}.blind_label differs from committed order")
    binding = _validate_call_binding(call["binding"], f"{path}.binding")
    if canonical_json(binding) != canonical_json(spec["call_binding"]):
        raise VerificationError(f"{path} call binding differs from preregistration")

    payload = call["payload"]
    payload_digest = call["payload_sha256"]
    expected_payload_digest = spec["payload_sha256"][condition]
    if condition == "missing":
        if payload is not None or payload_digest is not None:
            raise VerificationError(f"{path} missing placebo must carry no payload")
    else:
        _sha(payload_digest, f"{path}.payload_sha256")
        if payload_digest != sha256_ref(payload):
            raise VerificationError(f"{path} payload digest mismatch")
        if payload_digest != expected_payload_digest:
            raise VerificationError(f"{path} payload differs from preregistration")
        try:
            validate_action_state(payload)
        except ActionStateError as exc:
            raise VerificationError(f"{path} payload is not schema-valid: {exc}") from exc

    response = _validate_response(
        call["response"], call["response_sha256"], f"{path}.response"
    )
    total, _complete = _validate_usage(
        call["usage"], call["usage_sha256"], f"{path}.usage"
    )
    return response, total


def validate_causal_probe_pack(plan_value: Any, pack_value: Any) -> dict[str, Any]:
    """Validate one complete blinded pack against its separate preregistration.

    Malformed, incomplete, replayed, or contradictory bindings raise
    :class:`VerificationError`.  Structurally valid adverse outcomes are
    retained as explicit gate failures.  Nullable token totals remain unknown
    in the returned aggregate; they are never converted to zero.
    """

    plan, info = _validate_plan_internal(plan_value)
    _bounded_size(pack_value, "causal_probe_pack")
    pack = _object(pack_value, "causal_probe_pack")
    _exact(
        pack,
        {
            "schema_version",
            "evidence_boundary",
            "plan_sha256",
            "assignment_reveal",
            "probe_results",
        },
        "causal_probe_pack",
    )
    if pack["schema_version"] != CAUSAL_PROBE_PACK_SCHEMA:
        raise VerificationError("causal probe pack schema differs")
    if pack["evidence_boundary"] != OFFLINE_EVIDENCE_BOUNDARY:
        raise VerificationError("causal probe pack evidence boundary differs")
    if pack["plan_sha256"] != sha256_ref(plan):
        raise VerificationError("causal probe pack does not bind the plan")

    assignments = _validate_assignment_reveal(pack["assignment_reveal"], info)
    raw_results = _bounded_list(
        pack["probe_results"],
        "causal_probe_pack.probe_results",
        maximum=MAX_PROBES,
    )
    if len(raw_results) != len(info["specs"]):
        raise VerificationError("causal probe pack has absent per-stratum probes")

    result_ids: list[str] = []
    all_calls: dict[str, str] = {}
    request_ids: set[str] = set()
    context_ids: set[str] = set()
    response_ids: set[str] = set()
    response_digests: set[str] = set()
    observed_payloads: dict[tuple[str, str], Any] = {}
    known_total_tokens = 0
    unknown_total_calls = 0
    gate_failures: list[str] = []
    intervention_pairs_passed = 0
    placebo_calls_passed = 0
    valid_ab_calls_denominator = 0
    valid_ab_refusals_or_fallbacks_numerator = 0
    critical_pointer_usage: dict[str, int] = {}
    per_stratum: dict[tuple[str, str, str], dict[str, int]] = {
        stratum: {
            "probes": 0,
            "probes_passed": 0,
            "probes_failed": 0,
            "intervention_pairs_passed": 0,
            "intervention_pairs_failed": 0,
            "placebo_calls_passed": 0,
            "placebo_calls_failed": 0,
            "valid_ab_calls_denominator": 0,
            "valid_ab_refusals_or_fallbacks_numerator": 0,
        }
        for stratum in info["expected_strata"]
    }
    per_stable_semantic_slot: dict[str, dict[str, int]] = {
        field_id: {
            "probes": 0,
            "probes_passed": 0,
            "probes_failed": 0,
            "intervention_pairs_passed": 0,
            "intervention_pairs_failed": 0,
            "placebo_calls_passed": 0,
            "placebo_calls_failed": 0,
            "valid_ab_calls_denominator": 0,
            "valid_ab_refusals_or_fallbacks_numerator": 0,
        }
        for field_id in info["field_identity_coverage"]
    }

    for result_index, raw_result in enumerate(raw_results):
        result_path = f"causal_probe_pack.probe_results[{result_index}]"
        result = _object(raw_result, result_path)
        _exact(result, {"schema_version", "probe_id", "calls"}, result_path)
        if result["schema_version"] != CAUSAL_PROBE_RESULT_SCHEMA:
            raise VerificationError(f"{result_path}.schema_version differs")
        probe_id = _identifier(result["probe_id"], f"{result_path}.probe_id")
        if probe_id not in info["specs"]:
            raise VerificationError(f"{result_path} references an unknown probe")
        if probe_id in result_ids:
            raise VerificationError("causal probe pack contains duplicate probe results")
        result_ids.append(probe_id)
        spec = info["specs"][probe_id]
        stratum = _validate_stratum(spec["stratum"], f"{result_path}.stratum")
        stratum_counts = per_stratum[stratum]
        slot_counts = per_stable_semantic_slot[spec["field_id"]]
        gate_failure_count_before_probe = len(gate_failures)
        assignment = assignments[probe_id]
        calls = _list(result["calls"], f"{result_path}.calls")
        if len(calls) != len(CONDITIONS):
            raise VerificationError(
                f"{result_path}.calls must contain A/B and both placebo variants"
            )

        by_condition: dict[str, Mapping[str, Any]] = {}
        for call_index, raw_call in enumerate(calls):
            blind_label, condition = assignment[call_index]
            call_path = f"{result_path}.calls[{call_index}]"
            response, total = _validate_call(
                raw_call,
                spec=spec,
                condition=condition,
                expected_blind_label=blind_label,
                path=call_path,
            )
            call = _object(raw_call, call_path)
            call_id = call["call_id"]
            if call_id in all_calls:
                raise VerificationError("causal probe pack replays a call ID")
            all_calls[call_id] = probe_id
            for identity, seen, label in (
                (call["request_id"], request_ids, "request ID"),
                (call["context_instance_id"], context_ids, "context instance"),
                (response["provider_response_id"], response_ids, "response ID"),
                (call["response_sha256"], response_digests, "response digest"),
            ):
                if identity in seen:
                    raise VerificationError(f"causal probe pack replays a {label}")
                seen.add(identity)
            by_condition[condition] = response
            if condition != "missing":
                observed_payloads[(probe_id, condition)] = call["payload"]
            if total is None:
                unknown_total_calls += 1
                gate_failures.append(
                    f"unknown-inclusive-token-total:{probe_id}:{condition}"
                )
            else:
                known_total_tokens += total

        if set(by_condition) != set(CONDITIONS):
            raise VerificationError(f"{result_path} is missing a placebo or A/B condition")
        _validate_single_pointer_difference(
            observed_payloads[(probe_id, "a")],
            observed_payloads[(probe_id, "b")],
            spec["critical_pointer"],
            result_path,
        )

        output_a = by_condition["a"]["output_sha256"]
        output_b = by_condition["b"]["output_sha256"]
        if output_a == output_b:
            gate_failures.append(f"constant-output:{probe_id}")
        pair_passed = output_a != output_b
        for condition in AB_CONDITIONS:
            response = by_condition[condition]
            if response["disposition"] != "completed":
                gate_failures.append(f"intervention-not-completed:{probe_id}:{condition}")
                pair_passed = False
            if response["output_sha256"] != spec["expected_output_sha256"][condition]:
                gate_failures.append(
                    f"expected-output-mismatch:{probe_id}:{condition}"
                )
                pair_passed = False
        intervention_pairs_passed += int(pair_passed)
        valid_ab_calls_denominator += len(AB_CONDITIONS)
        refused_or_fallback = sum(
            by_condition[condition]["disposition"] in {"refused", "fallback"}
            for condition in AB_CONDITIONS
        )
        valid_ab_refusals_or_fallbacks_numerator += refused_or_fallback
        probe_placebo_calls_passed = 0
        for condition in PLACEBO_CONDITIONS:
            if by_condition[condition]["disposition"] not in {"refused", "fallback"}:
                gate_failures.append(
                    f"placebo-did-not-refuse-or-fallback:{probe_id}:{condition}"
                )
            else:
                placebo_calls_passed += 1
                probe_placebo_calls_passed += 1

        pointer = spec["critical_pointer"]
        critical_pointer_usage[pointer] = (
            critical_pointer_usage.get(pointer, 0) + 1
        )
        probe_passed = len(gate_failures) == gate_failure_count_before_probe
        stratum_counts["probes"] += 1
        stratum_counts["probes_passed"] += int(probe_passed)
        stratum_counts["probes_failed"] += int(not probe_passed)
        stratum_counts["intervention_pairs_passed"] += int(pair_passed)
        stratum_counts["intervention_pairs_failed"] += int(not pair_passed)
        stratum_counts["placebo_calls_passed"] += probe_placebo_calls_passed
        stratum_counts["placebo_calls_failed"] += (
            len(PLACEBO_CONDITIONS) - probe_placebo_calls_passed
        )
        stratum_counts["valid_ab_calls_denominator"] += len(AB_CONDITIONS)
        stratum_counts[
            "valid_ab_refusals_or_fallbacks_numerator"
        ] += refused_or_fallback
        slot_counts["probes"] += 1
        slot_counts["probes_passed"] += int(probe_passed)
        slot_counts["probes_failed"] += int(not probe_passed)
        slot_counts["intervention_pairs_passed"] += int(pair_passed)
        slot_counts["intervention_pairs_failed"] += int(not pair_passed)
        slot_counts["placebo_calls_passed"] += probe_placebo_calls_passed
        slot_counts["placebo_calls_failed"] += (
            len(PLACEBO_CONDITIONS) - probe_placebo_calls_passed
        )
        slot_counts["valid_ab_calls_denominator"] += len(AB_CONDITIONS)
        slot_counts[
            "valid_ab_refusals_or_fallbacks_numerator"
        ] += refused_or_fallback

    if result_ids != info["spec_order"]:
        raise VerificationError("causal probe result order differs from the plan")

    for probe_id, spec in info["specs"].items():
        source = spec["shuffled_from"]
        expected_payload = observed_payloads[(source["probe_id"], source["condition"])]
        observed = observed_payloads[(probe_id, "shuffled")]
        if canonical_json(observed) != canonical_json(expected_payload):
            raise VerificationError(
                f"probe {probe_id} shuffled placebo differs from its source payload"
            )

    total_calls = len(info["specs"]) * len(CONDITIONS)
    per_stratum_summary = [
        {
            "stratum": {
                "domain_id": stratum[0],
                "receiver_family": stratum[1],
                "operator_id": stratum[2],
            },
            **per_stratum[stratum],
            "checks_passed": per_stratum[stratum]["probes_failed"] == 0,
        }
        for stratum in sorted(per_stratum)
    ]
    worst_stratum_checks_passed = all(
        item["checks_passed"] for item in per_stratum_summary
    )
    per_stable_semantic_slot_summary = [
        {
            "field_id": field_id,
            **per_stable_semantic_slot[field_id],
            "available_contract_checks_passed": (
                per_stable_semantic_slot[field_id]["probes"] > 0
                and per_stable_semantic_slot[field_id]["probes_failed"] == 0
            ),
            "required_arm_matrix_validated": False,
        }
        for field_id in sorted(per_stable_semantic_slot)
    ]
    worst_stable_semantic_slot_available_checks_passed = all(
        item["available_contract_checks_passed"]
        for item in per_stable_semantic_slot_summary
    )
    field_identity_coverage = dict(sorted(info["field_identity_coverage"].items()))
    covered_field_count = sum(count > 0 for count in field_identity_coverage.values())
    declared_field_count = len(field_identity_coverage)
    external_reference = info["external_reference_set"]
    return {
        "schema_version": CAUSAL_PROBE_SUMMARY_SCHEMA,
        "valid": True,
        "structurally_valid": True,
        "payload_dependence_checks_passed": not gate_failures,
        "gate_failures": gate_failures,
        "plan_sha256": sha256_ref(plan),
        "pack_sha256": sha256_ref(pack),
        "strata": len(info["expected_strata"]),
        "probes": len(info["specs"]),
        "calls": total_calls,
        "intervention_pairs_passed": intervention_pairs_passed,
        "placebo_calls_passed": placebo_calls_passed,
        "valid_ab_calls_denominator": valid_ab_calls_denominator,
        "valid_ab_refusals_or_fallbacks_numerator": (
            valid_ab_refusals_or_fallbacks_numerator
        ),
        "critical_pointer_usage": dict(sorted(critical_pointer_usage.items())),
        "field_identity_coverage": field_identity_coverage,
        "field_identity_coverage_basis": "validated-probe-results",
        "authoritative_coverage_unit": "stable-field-id",
        "declared_field_count": declared_field_count,
        "covered_field_count": covered_field_count,
        "field_universe_sha256": sha256_ref(info["field_universe"]),
        "alias_to_field_id_binding_sha256": sha256_ref(info["alias_binding"]),
        "preregistered_identity_envelope_sha256": sha256_ref(
            info["identity_envelope"]
        ),
        "field_identity_and_external_refusal_calibration_same_envelope_bound": True,
        "pack_binds_identity_envelope": True,
        "preregistration_chronology_verified": False,
        "identity_envelope_external_anchor_verified": False,
        "per_stratum": per_stratum_summary,
        "worst_stratum_checks_passed": worst_stratum_checks_passed,
        "per_stable_semantic_slot": per_stable_semantic_slot_summary,
        "worst_stable_semantic_slot_available_checks_passed": (
            worst_stable_semantic_slot_available_checks_passed
        ),
        "pooled_intervention_pair_count_is_claim_gate": False,
        "token_accounting_complete": unknown_total_calls == 0,
        "known_total_token_calls": total_calls - unknown_total_calls,
        "unknown_total_token_calls": unknown_total_calls,
        "known_total_tokens": known_total_tokens,
        "inclusive_total_tokens": (
            None if unknown_total_calls else known_total_tokens
        ),
        "semantic_invariance_checked": False,
        "composition_holdout_checked": False,
        "no_payload_accuracy_measured": False,
        "declared_field_universe_covered": covered_field_count == declared_field_count,
        "calibration_headline_seed_separated": False,
        "external_reference_set_identity_bound": True,
        "external_refusal_calibration_reference_set_identity_bound": True,
        "external_reference_set_id": external_reference["reference_set_id"],
        "external_reference_set_sha256": sha256_ref(external_reference),
        "external_refusal_calibration_purpose": external_reference["purpose"],
        "independent_specification_commitment_bound": True,
        "independent_specification_authenticated": False,
        "external_reference_observations_validated": False,
        "external_refusal_calibration_gate_implemented": False,
        "same_receiver_valid_ab_refusal_or_fallback_baseline_externally_anchored": False,
        "required_per_slot_contrast_arms": list(REQUIRED_PER_SLOT_CONTRAST_ARMS),
        "per_slot_arm_matrix_validated": False,
        "validated_stratum_dimensions": list(VALIDATED_STRATUM_DIMENSIONS),
        "required_empirical_worst_stratum_axes": list(
            REQUIRED_EMPIRICAL_WORST_STRATUM_AXES
        ),
        "five_dimensional_strata_validated": False,
        "task_semantics_used_verdict_validated": False,
        "verdicts": {
            "payload_influenced_output": {
                "status": (
                    "local-record-contract-passed"
                    if not gate_failures
                    else "local-record-contract-failed"
                ),
                "checks_passed": not gate_failures,
                "claim_eligible": False,
            },
            "task_semantics_used": {
                "status": "not-validated",
                "checks_passed": False,
                "claim_eligible": False,
            },
        },
        "evidence_boundary": OFFLINE_EVIDENCE_BOUNDARY,
        "claim_eligible": False,
        "provider_or_model_calls_by_validator": 0,
    }


def validate_causal_probe_pack_json(
    plan_text: str,
    pack_text: str,
) -> dict[str, Any]:
    """Strict-JSON form of :func:`validate_causal_probe_pack`."""

    plan = strict_json_loads(plan_text, max_bytes=MAX_JSON_BYTES)
    pack = strict_json_loads(pack_text, max_bytes=MAX_JSON_BYTES)
    return validate_causal_probe_pack(plan, pack)
