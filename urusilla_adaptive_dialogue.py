#!/usr/bin/env python3
"""Experimental adaptive semantic dialogue and Capsule-evolution layer.

This dependency-free prototype targets the *external* utterance boundary between
agents.  It does not prescribe a model's internal reasoning representation,
request chain-of-thought disclosure, or replace HTTP, TCP, A2A, MCP, or another
transport.  Large media remain content-addressed external assets.

The experiment combines five independently testable mechanisms:

* a typed semantic envelope and task-state ledger;
* fragment-local codec splicing with fail-closed execution eligibility;
* receiver-token codec selection behind semantic, safety, and policy gates;
* immutable, content-addressed Capsule deltas and explicit migrations; and
* proposal, session-trial, cross-play, ratification, deprecation, rollback, and
  codebook-cache garbage-collection controls.

Representational coverage in the included corpus is not proof that the format
captures every human meaning, that a model understands it, or that agents will
adopt it.
"""

from __future__ import annotations

import argparse
import base64
import copy
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence
import uuid


PROFILE_FORMAT = "urusilla-experimental-adaptive-profile-v1"
PROFILE_VERSION = "research-fixture-1"
CORE_LANGUAGE_VERSION = "0.1.0"
MESSAGE_VERSION = "urusilla-experimental-dialogue-envelope-v1"
UUID_NAMESPACE = uuid.UUID("2838e727-5be1-50b9-ae3d-d13166caf651")
FOUNDING_MAINTAINER_ID = "github:jaden3824"

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s]+\Z")


class DialogueError(ValueError):
    """Fail-closed protocol validation error carrying a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class ValidationError(DialogueError):
    pass


class LedgerError(DialogueError):
    pass


class SelectionError(DialogueError):
    pass


class GovernanceError(DialogueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    """Return the prototype's deterministic JSON representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("non_canonical_value", "value is not finite JSON") from exc


def content_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, label))


def _deep_copy(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _require_digest(value: Any, field_name: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise ValidationError("invalid_digest", f"{field_name} must be sha256 plus 64 lowercase hex digits")
    return value


def _require_identifier(value: Any, field_name: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValidationError("invalid_identifier", f"{field_name} must be an absolute identifier")
    return value


def _require_text(value: Any, field_name: str) -> str:
    if type(value) is not str or not value:
        raise ValidationError("invalid_text", f"{field_name} must be a non-empty string")
    if any(ord(character) < 0x20 for character in value):
        raise ValidationError("invalid_text", f"{field_name} cannot contain control characters")
    return value


def _require_uuid(value: Any, field_name: str) -> str:
    if type(value) is not str:
        raise ValidationError("invalid_uuid", f"{field_name} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError("invalid_uuid", f"{field_name} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ValidationError("invalid_uuid", f"{field_name} must be a lowercase canonical UUID")
    return value


def _schema(required: Sequence[str], optional: Sequence[str] = ()) -> dict[str, list[str]]:
    return {"required": list(required), "optional": list(optional)}


# Every mapping inside the semantic tree is a typed node.  Raw maps and raw
# natural-language escape objects are deliberately excluded from native cover.
NODE_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "ref": _schema(("uri",)),
    "literal": _schema(("datatype", "value"), ("language",)),
    "record": _schema(("entries",)),
    "entry": _schema(("key", "value")),
    "operator": _schema(("operator", "operands")),
    "claim": _schema(("predicate", "arguments"), ("context", "valid_time")),
    "query": _schema(("target", "variables"), ("answer_schema",)),
    "clarification": _schema(("target", "ambiguity", "options")),
    "goal": _schema(("condition",), ("constraints", "priority")),
    "request": _schema(("goal",), ("deadline", "budget")),
    "capability_query": _schema(("capability",), ("requirements",)),
    "capability_advertisement": _schema(
        ("capability", "input_schema", "output_schema"),
        ("limits", "policy"),
    ),
    "action": _schema(("capability", "arguments", "effects"), ("policy", "budget")),
    "proposal": _schema(("mode", "action", "conditions"), ("valid_until", "preference")),
    "conditional": _schema(("if", "then"), ("else",)),
    "choice": _schema(("alternatives",), ("preference", "minimum", "maximum")),
    "plan": _schema(("steps",), ("goal", "policy", "budget")),
    "plan_step": _schema(("step_id", "action", "depends_on"), ("assignee",)),
    "commitment": _schema(("debtor", "creditors", "goal", "expiry_ms"), ("verifier",)),
    "refusal": _schema(("target", "reason_code"), ("alternatives",)),
    "cancellation": _schema(("target", "reason_code")),
    "progress": _schema(("target", "completed_ppm"), ("status",)),
    "partial_result": _schema(("target", "value", "completed_ppm"), ("evidence",)),
    "success": _schema(("target", "result"), ("evidence",)),
    "failure": _schema(("target", "code", "recoverable"), ("evidence", "fallback")),
    "retraction": _schema(("target", "reason_code")),
    "correction": _schema(("target", "replacement"), ("reason_code",)),
    "definition": _schema(("symbol", "version", "schema_digest", "semantics")),
    "schema_negotiation": _schema(("offered", "required_features"), ("accepted", "migration")),
    "time": _schema(("relation", "epoch_ms"), ("duration_ms", "timezone")),
    "quantity": _schema(("mantissa", "scale", "unit"), ("comparator",)),
    "preference": _schema(("ordering",), ("weight_ppm", "tie_policy")),
    "policy": _schema(("rule", "effect", "scope"), ("authority",)),
    "budget": _schema(("resource", "limit", "unit"), ("consumed",)),
    "uncertainty": _schema(("target", "distribution", "parameters"), ("confidence_ppm",)),
    "evidence": _schema(("target", "digest", "method", "stance"), ("provenance",)),
    "coordination": _schema(("participants", "plan", "assignments", "quorum"), ("policy",)),
    "assignment": _schema(("agent", "step_ids", "role")),
    "not_understood": _schema(
        ("target", "fragment_ids", "reason_codes", "acceptable_codecs"),
        ("scope",),
    ),
    "tool_result": _schema(("tool", "schema_digest", "value", "provenance")),
    "web_fact": _schema(("subject", "predicate", "object", "provenance", "observed_at")),
    "working_state": _schema(("state_schema", "state_digest", "summary"), ("privacy",)),
    "action_state": _schema(("action", "phase", "state_digest"), ("checkpoint",)),
    "provenance": _schema(("source", "digest", "method"), ("observed_at", "license")),
    "asset_ref": _schema(("uri", "media_type", "digest", "size_bytes"), ("chunks",)),
    "splice": _schema(
        (
            "fragment_id",
            "role",
            "codec",
            "codec_version",
            "schema_digest",
            "profile_digest",
            "payload_b64",
            "payload_digest",
            "loss_mode",
            "fallback_chain",
            "execution_eligibility",
        )
    ),
}


CORE_WIRE_ACTS = (
    "ASSERT",
    "QUERY",
    "REQUEST",
    "PROPOSE",
    "COMMIT",
    "RESOLVE",
    "RETRACT",
)


INTERACTION_FUNCTION_BODY_KINDS: dict[str, tuple[str, ...]] = {
    "ASSERT": ("claim", "evidence", "uncertainty"),
    "QUERY": ("query",),
    "CLARIFY": ("clarification",),
    "REQUEST": ("request",),
    "DISCOVER": ("capability_query", "capability_advertisement"),
    "PROPOSE": ("proposal",),
    "COUNTERPROPOSE": ("proposal",),
    "COMMIT": ("commitment",),
    "REFUSE": ("refusal",),
    "CANCEL": ("cancellation",),
    "PROGRESS": ("progress",),
    "PARTIAL": ("partial_result",),
    "SUCCEED": ("success",),
    "FAIL": ("failure",),
    "RETRACT": ("retraction",),
    "CORRECT": ("correction",),
    "DEFINE": ("definition",),
    "NEGOTIATE_SCHEMA": ("schema_negotiation",),
    "COORDINATE": ("coordination",),
    "NOT_UNDERSTOOD": ("not_understood",),
}


INTERACTION_PROJECTION: dict[str, dict[str, str]] = {
    "ASSERT": {"claim": "ASSERT", "evidence": "ASSERT", "uncertainty": "ASSERT"},
    "QUERY": {"query": "QUERY"},
    "CLARIFY": {"clarification": "QUERY"},
    "REQUEST": {"request": "REQUEST"},
    "DISCOVER": {
        "capability_query": "QUERY",
        "capability_advertisement": "ASSERT",
    },
    "PROPOSE": {"proposal:initial": "PROPOSE"},
    "COUNTERPROPOSE": {"proposal:counter": "PROPOSE"},
    "COMMIT": {"commitment": "COMMIT"},
    "REFUSE": {"refusal": "RESOLVE"},
    "CANCEL": {"cancellation": "RETRACT"},
    "PROGRESS": {"progress": "RESOLVE"},
    "PARTIAL": {"partial_result": "RESOLVE"},
    "SUCCEED": {"success": "RESOLVE"},
    "FAIL": {"failure": "RESOLVE"},
    "RETRACT": {"retraction": "RETRACT"},
    "CORRECT": {"correction": "ASSERT"},
    "DEFINE": {"definition": "ASSERT"},
    "NEGOTIATE_SCHEMA": {"schema_negotiation": "PROPOSE"},
    "COORDINATE": {"coordination": "PROPOSE"},
    "NOT_UNDERSTOOD": {"not_understood": "RESOLVE"},
}


INTERACTION_EFFECT_SCOPE: dict[str, str] = {
    "COMMIT": "commit",
    "CANCEL": "cancel",
    "PROGRESS": "execute",
    "PARTIAL": "execute",
    "SUCCEED": "resolve",
    "FAIL": "resolve",
    "RETRACT": "revise",
    "CORRECT": "revise",
    "DEFINE": "schema",
    "NEGOTIATE_SCHEMA": "schema",
}


SPLICE_ROLES = frozenset(
    {
        "argument",
        "condition",
        "constraint",
        "result",
        "evidence",
        "tool_payload",
        "web_payload",
        "working_state",
        "action_state",
        "modality_reference",
        "other",
    }
)
LOSS_MODES = frozenset({"exact", "lossless_bridge", "lossy_summary", "opaque"})


DEFAULT_CODEBOOK_BYTES: dict[str, bytes] = {
    "urusilla-json-fixture@1": b"urusilla-experimental-json-codebook-v1",
    "urusilla-wire-v02-fixture@1": b"urusilla-experimental-wire-v02-codebook-v1",
}


def _codebook_descriptors() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "digest": bytes_digest(data),
            "exact": True,
            "verified": True,
            "executable": True,
        }
        for name, data in DEFAULT_CODEBOOK_BYTES.items()
    }


def interaction_projection_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for interaction_function, selectors in INTERACTION_PROJECTION.items():
        for selector, wire_act in selectors.items():
            if ":" in selector:
                body_kind, mode = selector.split(":", 1)
                discriminator: dict[str, str] | None = {"field": "mode", "equals": mode}
            else:
                body_kind = selector
                discriminator = None
            rows.append(
                {
                    "interaction_function": interaction_function,
                    "body_kind": body_kind,
                    "discriminator": discriminator,
                    "wire_act": wire_act,
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["interaction_function"],
            row["body_kind"],
            canonical_json_bytes(row["discriminator"]),
        ),
    )


def project_interaction_function(
    body: Mapping[str, Any],
    profile_payload: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Infer the typed interaction function and its canonical seven-act projection."""

    if profile_payload is None:
        profile_payload = default_profile_payload()
    rows = profile_payload.get("interaction_projection")
    if type(rows) is not list:
        raise ValidationError("interaction_projection", "profile projection table is missing")
    matches: list[tuple[str, str]] = []
    for row in rows:
        if type(row) is not dict or row.get("body_kind") != body.get("kind"):
            continue
        discriminator = row.get("discriminator")
        if discriminator is not None:
            if type(discriminator) is not dict or set(discriminator) != {"field", "equals"}:
                raise ValidationError("interaction_projection", "projection discriminator is malformed")
            if body.get(discriminator["field"]) != discriminator["equals"]:
                continue
        interaction_function = row.get("interaction_function")
        wire_act = row.get("wire_act")
        if interaction_function not in INTERACTION_FUNCTION_BODY_KINDS:
            raise ValidationError("interaction_projection", "projection function is unknown")
        if wire_act not in CORE_WIRE_ACTS:
            raise ValidationError("interaction_projection", "projection uses a non-core wire act")
        matches.append((interaction_function, wire_act))
    if len(matches) != 1:
        raise ValidationError(
            "interaction_projection",
            "typed body must match exactly one interaction-function projection",
        )
    return matches[0]


def default_profile_payload() -> dict[str, Any]:
    """Return the semantic profile payload whose wrapper is content-addressed."""

    return {
        "profile_id": "urn:urusilla:experimental:profile:adaptive-dialogue:fixture-1",
        "version": PROFILE_VERSION,
        "status": "research_fixture_not_official_extension",
        "core_language_version": CORE_LANGUAGE_VERSION,
        "core_relationship": "experimental_external_dialogue_projection",
        "official_language_claim": "none",
        "scope": {
            "external_utterance_layer": "targeted_for_staged_semantic_replacement",
            "internal_reasoning": "model_specific_and_out_of_scope",
            "chain_of_thought": "not_requested_or_required",
            "transport": "payload_layer_over_existing_http_tcp_a2a_mcp_or_other_transport",
            "large_modalities": "content_addressed_external_assets",
            "native_coverage_rule": "raw_natural_language_escape_never_counts_as_native_coverage",
        },
        "north_star_stages": [
            {
                "stage": 1,
                "name": "external_agent_dialogue",
                "gate": "exact_semantics_with_fragment_local_fallback",
            },
            {
                "stage": 2,
                "name": "tool_and_web_information_payloads",
                "gate": "schema_provenance_privacy_and_asset_integrity",
            },
            {
                "stage": 3,
                "name": "model_native_working_memory_and_action_state",
                "gate": "explicit_state_schema_without_chain_of_thought_disclosure",
            },
            {
                "stage": 4,
                "name": "optional_compatible_latent_fast_paths",
                "gate": "hidden_state_compatibility_exact_decoder_and_semantic_fallback",
            },
            {
                "stage": 5,
                "name": "internet_semantic_control_plane",
                "gate": "open_conformance_federated_governance_and_transport_independence",
            },
        ],
        "admission_gates": [
            "semantic_exactness",
            "receiver_capability",
            "authorization",
            "latency",
            "risk",
            "privacy",
            "hidden_state_compatibility",
            "provenance",
            "energy_task_utility",
            "fallback",
        ],
        "core_wire_acts": list(CORE_WIRE_ACTS),
        "interaction_functions": {
            interaction_function: list(kinds)
            for interaction_function, kinds in INTERACTION_FUNCTION_BODY_KINDS.items()
        },
        "interaction_projection": interaction_projection_rows(),
        "node_schemas": copy.deepcopy(NODE_SCHEMAS),
        "splice": {
            "roles": sorted(SPLICE_ROLES),
            "loss_modes": sorted(LOSS_MODES),
            "unsupported_scope": "fragment_only",
            "unknown_or_unverified_execution": "forbidden",
        },
        "codebooks": _codebook_descriptors(),
        "lifecycle": [
            "proposed",
            "session_trial",
            "cross_play_candidate",
            "ratified",
            "deprecated",
        ],
        "governance": {
            "phase": "founder_led_experimental_stewardship",
            "agent_permissions": ["propose", "session_trial", "cross_play_evaluate"],
            "core_or_official_ratification": (
                "externally_verified_signed_founding_maintainer_approval_required"
            ),
            "automated_metrics": "evidence_only_never_authority_to_ratify_meaning",
            "ephemeral_session_delta": {
                "scope": "negotiated_non_core_only",
                "requirements": [
                    "all_hard_safety_gates_pass",
                    "session_and_peer_pins",
                    "no_global_activation",
                    "no_ratification_claim",
                ],
            },
        },
        "migration_relations": ["equivalent", "narrowing", "widening", "transform"],
        "interaction_effect_scopes": copy.deepcopy(INTERACTION_EFFECT_SCOPE),
    }


def wrap_profile(
    payload: Mapping[str, Any],
    *,
    sequence: int,
    parent_digest: str | None,
    applied_delta_digest: str | None,
) -> dict[str, Any]:
    unsigned = {
        "format": PROFILE_FORMAT,
        "sequence": sequence,
        "parent_digest": parent_digest,
        "applied_delta_digest": applied_delta_digest,
        "profile": _deep_copy(payload),
    }
    return {**unsigned, "profile_digest": content_digest(unsigned)}


def default_profile_document() -> dict[str, Any]:
    return wrap_profile(
        default_profile_payload(),
        sequence=0,
        parent_digest=None,
        applied_delta_digest=None,
    )


def validate_profile_document(document: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "format",
        "sequence",
        "parent_digest",
        "applied_delta_digest",
        "profile",
        "profile_digest",
    }
    if set(document) != required:
        raise ValidationError("profile_fields", "profile wrapper fields are not exact")
    if document["format"] != PROFILE_FORMAT:
        raise ValidationError("profile_format", "unsupported profile format")
    if type(document["sequence"]) is not int or document["sequence"] < 0:
        raise ValidationError("profile_sequence", "sequence must be a non-negative integer")
    unsigned = {key: _deep_copy(document[key]) for key in required - {"profile_digest"}}
    expected = content_digest(unsigned)
    if document["profile_digest"] != expected:
        raise ValidationError("profile_digest", "profile content digest does not match")
    if document["parent_digest"] is not None:
        _require_digest(document["parent_digest"], "parent_digest")
    if document["applied_delta_digest"] is not None:
        _require_digest(document["applied_delta_digest"], "applied_delta_digest")
    profile = document["profile"]
    if type(profile) is not dict or type(profile.get("node_schemas")) is not dict:
        raise ValidationError("profile_payload", "profile and node_schemas must be mappings")
    if profile.get("status") != "research_fixture_not_official_extension":
        raise ValidationError("profile_status", "adaptive dialogue profile is a research fixture only")
    if profile.get("core_language_version") != CORE_LANGUAGE_VERSION:
        raise ValidationError("core_relationship", "profile must pin the experimental v0.1 core")
    if profile.get("core_relationship") != "experimental_external_dialogue_projection":
        raise ValidationError("core_relationship", "profile relationship is not an external dialogue projection")
    if profile.get("core_wire_acts") != list(CORE_WIRE_ACTS):
        raise ValidationError("core_wire_acts", "profile must use exactly the seven canonical v0.1 acts")
    functions = profile.get("interaction_functions")
    if type(functions) is not dict or set(functions) != set(INTERACTION_FUNCTION_BODY_KINDS):
        raise ValidationError("interaction_functions", "profile interaction-function set is not exact")
    expected_functions = {
        name: list(kinds) for name, kinds in INTERACTION_FUNCTION_BODY_KINDS.items()
    }
    if functions != expected_functions:
        raise ValidationError("interaction_functions", "typed body coverage cannot drift silently")
    if profile.get("interaction_projection") != interaction_projection_rows():
        raise ValidationError("interaction_projection", "canonical v0.1 projection cannot drift silently")
    return _deep_copy(document)


def _validate_semantic_value(value: Any, profile_payload: Mapping[str, Any], kinds: set[str]) -> None:
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationError("non_finite", "semantic numbers must be finite")
        return
    if type(value) is list:
        for item in value:
            _validate_semantic_value(item, profile_payload, kinds)
        return
    if type(value) is dict:
        validate_node(value, profile_payload, kinds=kinds)
        return
    raise ValidationError("semantic_type", "semantic values must be JSON scalars, lists, or typed nodes")


def _validate_splice(node: Mapping[str, Any], profile_payload: Mapping[str, Any]) -> None:
    _require_text(node["fragment_id"], "fragment_id")
    if node["role"] not in SPLICE_ROLES:
        raise ValidationError("splice_role", "splice role is unknown")
    _require_text(node["codec"], "codec")
    _require_text(node["codec_version"], "codec_version")
    _require_digest(node["schema_digest"], "schema_digest")
    _require_digest(node["profile_digest"], "profile_digest")
    _require_digest(node["payload_digest"], "payload_digest")
    if node["loss_mode"] not in LOSS_MODES:
        raise ValidationError("splice_loss", "splice loss mode is unknown")
    if type(node["execution_eligibility"]) is not bool:
        raise ValidationError("splice_execution", "execution_eligibility must be boolean")
    if type(node["fallback_chain"]) is not list or not node["fallback_chain"]:
        raise ValidationError("splice_fallback", "fallback_chain must be a non-empty list")
    for fallback in node["fallback_chain"]:
        _require_text(fallback, "fallback codec")
    if len(set(node["fallback_chain"])) != len(node["fallback_chain"]):
        raise ValidationError("splice_fallback", "fallback_chain cannot contain duplicates")
    try:
        payload = base64.b64decode(node["payload_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValidationError("splice_payload", "payload_b64 is not canonical Base64") from exc
    if base64.b64encode(payload).decode("ascii") != node["payload_b64"]:
        raise ValidationError("splice_payload", "payload_b64 is not canonical padded Base64")
    if bytes_digest(payload) != node["payload_digest"]:
        raise ValidationError("splice_payload_digest", "splice payload digest does not match")
    codec_key = f"{node['codec']}@{node['codec_version']}"
    descriptor = profile_payload.get("codebooks", {}).get(codec_key)
    exact_loss = node["loss_mode"] in {"exact", "lossless_bridge"}
    if node["execution_eligibility"]:
        if descriptor is None:
            raise ValidationError("splice_unknown_executable", "unknown splice codecs cannot execute")
        if not descriptor.get("verified") or not descriptor.get("executable"):
            raise ValidationError("splice_unverified_executable", "unverified splice codecs cannot execute")
        if not descriptor.get("exact") or not exact_loss:
            raise ValidationError("splice_lossy_executable", "lossy or opaque splices cannot execute")


def _validate_plan(node: Mapping[str, Any]) -> None:
    steps = node["steps"]
    if type(steps) is not list or not steps:
        raise ValidationError("plan_steps", "plan must contain steps")
    identifiers: list[str] = []
    dependencies: dict[str, list[str]] = {}
    for step in steps:
        if type(step) is not dict or step.get("kind") != "plan_step":
            raise ValidationError("plan_steps", "every plan step must be a plan_step node")
        step_id = _require_text(step.get("step_id"), "step_id")
        identifiers.append(step_id)
        depends_on = step.get("depends_on")
        if type(depends_on) is not list or any(type(item) is not str for item in depends_on):
            raise ValidationError("plan_dependencies", "depends_on must be a string list")
        dependencies[step_id] = list(depends_on)
    if len(set(identifiers)) != len(identifiers):
        raise ValidationError("plan_duplicate", "plan step IDs must be unique")
    known = set(identifiers)
    if any(dependency not in known for values in dependencies.values() for dependency in values):
        raise ValidationError("plan_dependency", "plan dependency references an unknown step")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValidationError("plan_cycle", "plan dependency graph must be acyclic")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in dependencies[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in identifiers:
        visit(step_id)


def validate_node(
    node: Mapping[str, Any],
    profile_payload: Mapping[str, Any] | None = None,
    *,
    kinds: set[str] | None = None,
) -> dict[str, Any]:
    """Validate a typed semantic tree, rejecting untyped mapping escapes."""

    if profile_payload is None:
        profile_payload = default_profile_payload()
    if type(node) is not dict:
        raise ValidationError("node_type", "semantic node must be a mapping")
    kind = node.get("kind")
    if type(kind) is not str:
        raise ValidationError("node_kind", "every semantic mapping must carry a kind")
    schemas = profile_payload.get("node_schemas", {})
    schema = schemas.get(kind)
    if type(schema) is not dict:
        raise ValidationError("unknown_node", f"node kind {kind!r} is not in the active profile")
    required = set(schema.get("required", []))
    optional = set(schema.get("optional", []))
    fields = set(node) - {"kind"}
    missing = required - fields
    unknown = fields - required - optional
    if missing:
        raise ValidationError("node_missing", f"{kind} is missing {sorted(missing)}")
    if unknown:
        raise ValidationError("node_fields", f"{kind} has unknown fields {sorted(unknown)}")
    if kinds is None:
        kinds = set()
    kinds.add(kind)
    for key in fields:
        _validate_semantic_value(node[key], profile_payload, kinds)

    if kind == "ref":
        _require_identifier(node["uri"], "ref.uri")
    elif kind == "literal":
        datatype = _require_identifier(node["datatype"], "literal.datatype")
        if datatype in {"urn:datatype:natural-language", "urn:datatype:raw-text"}:
            raise ValidationError(
                "raw_language_escape",
                "raw natural language must use a non-executable splice and never counts as native coverage",
            )
    elif kind == "plan":
        _validate_plan(node)
    elif kind == "proposal":
        if node["mode"] not in {"initial", "counter"}:
            raise ValidationError("proposal_mode", "proposal mode must be initial or counter")
    elif kind == "plan_step":
        _require_text(node["step_id"], "step_id")
    elif kind in {"progress", "partial_result"}:
        ppm = node["completed_ppm"]
        if type(ppm) is not int or not 0 <= ppm <= 1_000_000:
            raise ValidationError("progress_range", "completed_ppm must be 0 through 1,000,000")
    elif kind == "preference" and "weight_ppm" in node:
        ppm = node["weight_ppm"]
        if type(ppm) is not int or not 0 <= ppm <= 1_000_000:
            raise ValidationError("ppm_range", "weight_ppm must be 0 through 1,000,000")
    elif kind == "uncertainty" and "confidence_ppm" in node:
        ppm = node["confidence_ppm"]
        if type(ppm) is not int or not 0 <= ppm <= 1_000_000:
            raise ValidationError("ppm_range", "confidence_ppm must be 0 through 1,000,000")
    elif kind == "commitment":
        _require_text(node["debtor"], "debtor")
        if type(node["creditors"]) is not list or not node["creditors"]:
            raise ValidationError("creditors", "creditors must be a non-empty list")
        if type(node["expiry_ms"]) is not int or node["expiry_ms"] < 0:
            raise ValidationError("expiry", "expiry_ms must be a non-negative integer")
    elif kind == "splice":
        _validate_splice(node, profile_payload)
    elif kind in {"evidence", "provenance", "asset_ref"}:
        _require_digest(node["digest"], f"{kind}.digest")
        if kind == "asset_ref" and (
            type(node["size_bytes"]) is not int or node["size_bytes"] < 0
        ):
            raise ValidationError("asset_size", "asset size must be a non-negative integer")
    elif kind == "working_state":
        _require_digest(node["state_digest"], "working_state.state_digest")
    elif kind == "action_state":
        _require_digest(node["state_digest"], "action_state.state_digest")
    elif kind == "definition":
        _require_digest(node["schema_digest"], "definition.schema_digest")
    elif kind == "capability_advertisement":
        _require_digest(node["input_schema"], "input_schema")
        _require_digest(node["output_schema"], "output_schema")
    return _deep_copy(node)


MESSAGE_FIELDS = frozenset(
    {
        "version",
        "id",
        "conversation_id",
        "thread_id",
        "sender",
        "recipients",
        "act",
        "logical_clock",
        "causes",
        "profile_digest",
        "schema_digest",
        "body",
        "authorization",
    }
)
AUTHORIZATION_FIELDS = frozenset(
    {"principal", "key_id", "verified", "scopes", "provenance_digest"}
)


def validate_message(
    message: Mapping[str, Any],
    profile_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a complete semantic external-utterance envelope."""

    if profile_document is None:
        profile_document = default_profile_document()
    validated_profile = validate_profile_document(profile_document)
    if type(message) is not dict or set(message) != MESSAGE_FIELDS:
        raise ValidationError("message_fields", "message envelope fields are not exact")
    if message["version"] != MESSAGE_VERSION:
        raise ValidationError("message_version", "unsupported dialogue-envelope version")
    _require_uuid(message["id"], "id")
    _require_uuid(message["conversation_id"], "conversation_id")
    _require_uuid(message["thread_id"], "thread_id")
    sender = _require_text(message["sender"], "sender")
    recipients = message["recipients"]
    if type(recipients) is not list or not recipients:
        raise ValidationError("recipients", "recipients must be a non-empty list")
    if any(type(recipient) is not str or not recipient for recipient in recipients):
        raise ValidationError("recipients", "every recipient must be a non-empty string")
    if sender in recipients or len(set(recipients)) != len(recipients):
        raise ValidationError("recipients", "recipients must be unique and exclude sender")
    act = message["act"]
    if act not in CORE_WIRE_ACTS:
        raise ValidationError("act", "message act must be one of the seven canonical v0.1 wire acts")
    if type(message["logical_clock"]) is not int or message["logical_clock"] < 0:
        raise ValidationError("clock", "logical_clock must be a non-negative integer")
    causes = message["causes"]
    if type(causes) is not list or len(set(causes)) != len(causes):
        raise ValidationError("causes", "causes must be a unique UUID list")
    for cause in causes:
        _require_uuid(cause, "cause")
    if message["profile_digest"] != validated_profile["profile_digest"]:
        raise ValidationError("profile_pin", "message does not pin the active profile digest")
    _require_digest(message["schema_digest"], "schema_digest")

    body = message["body"]
    validate_node(body, validated_profile["profile"])
    interaction_function, projected_act = project_interaction_function(
        body, validated_profile["profile"]
    )
    if act != projected_act:
        raise ValidationError(
            "interaction_projection",
            f"{interaction_function} must project to {projected_act}, not {act}",
        )
    authorization = message["authorization"]
    if type(authorization) is not dict or set(authorization) != AUTHORIZATION_FIELDS:
        raise ValidationError("authorization_fields", "authorization fields are not exact")
    principal = _require_text(authorization["principal"], "authorization.principal")
    _require_text(authorization["key_id"], "authorization.key_id")
    if type(authorization["verified"]) is not bool:
        raise ValidationError("authorization_verified", "verified must be boolean")
    scopes = authorization["scopes"]
    if type(scopes) is not list or any(type(scope) is not str or not scope for scope in scopes):
        raise ValidationError("authorization_scopes", "scopes must be a string list")
    if len(set(scopes)) != len(scopes):
        raise ValidationError("authorization_scopes", "scopes cannot contain duplicates")
    _require_digest(authorization["provenance_digest"], "authorization.provenance_digest")
    if principal != sender:
        raise ValidationError("principal_binding", "authorization principal must equal sender")
    effect_scopes = validated_profile["profile"].get("interaction_effect_scopes", {})
    if interaction_function in effect_scopes:
        required_scope = effect_scopes[interaction_function]
        if not authorization["verified"] or required_scope not in scopes:
            raise ValidationError(
                "authorization_gate",
                f"{interaction_function} requires verified sender scope {required_scope!r}",
            )
    if interaction_function == "COMMIT" and body["debtor"] != sender:
        raise ValidationError("commitment_owner", "commitment debtor must equal sender")
    return _deep_copy(message)


def message_digest(message: Mapping[str, Any]) -> str:
    return content_digest(message)


def message_interaction_function(
    message: Mapping[str, Any],
    profile_document: Mapping[str, Any] | None = None,
) -> str:
    if profile_document is None:
        profile_document = default_profile_document()
    profile = validate_profile_document(profile_document)
    return project_interaction_function(message["body"], profile["profile"])[0]


def _target_message_id(node: Mapping[str, Any]) -> str:
    target = node.get("target")
    if type(target) is not dict or target.get("kind") != "ref":
        raise LedgerError("target_ref", "state and revision acts require a ref target")
    uri = target.get("uri")
    prefix = "urn:message:"
    if type(uri) is not str or not uri.startswith(prefix):
        raise LedgerError("target_ref", "target must use urn:message:<uuid>")
    return _require_uuid(uri[len(prefix) :], "target message ID")


INTERACTION_TASK_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "REQUEST": (frozenset({"NONE"}), "REQUESTED"),
    "PROPOSE": (frozenset({"REQUESTED", "PROPOSED"}), "PROPOSED"),
    "COUNTERPROPOSE": (frozenset({"PROPOSED"}), "PROPOSED"),
    "COMMIT": (frozenset({"REQUESTED", "PROPOSED"}), "COMMITTED"),
    "REFUSE": (frozenset({"REQUESTED", "PROPOSED"}), "REFUSED"),
    "CANCEL": (
        frozenset({"REQUESTED", "PROPOSED", "COMMITTED", "IN_PROGRESS", "PARTIAL"}),
        "CANCELLED",
    ),
    "PROGRESS": (frozenset({"COMMITTED", "IN_PROGRESS", "PARTIAL"}), "IN_PROGRESS"),
    "PARTIAL": (frozenset({"COMMITTED", "IN_PROGRESS", "PARTIAL"}), "PARTIAL"),
    "SUCCEED": (frozenset({"COMMITTED", "IN_PROGRESS", "PARTIAL"}), "SUCCEEDED"),
    "FAIL": (frozenset({"COMMITTED", "IN_PROGRESS", "PARTIAL"}), "FAILED"),
}


REVISION_FUNCTIONS = frozenset({"RETRACT", "CORRECT"})
EXECUTION_FUNCTIONS = frozenset({"PROGRESS", "PARTIAL", "SUCCEED", "FAIL"})


class ConversationLedger:
    """Append-only semantic ledger with replay, causal, ownership, and task checks."""

    def __init__(self, profile_document: Mapping[str, Any] | None = None):
        if profile_document is None:
            profile_document = default_profile_document()
        self.profile_document = validate_profile_document(profile_document)
        self.messages: dict[str, dict[str, Any]] = {}
        self.digests: dict[str, str] = {}
        self.order: list[str] = []
        self.thread_states: dict[tuple[str, str], str] = {}
        self.retracted: set[str] = set()
        self.corrections: dict[str, str] = {}

    def _check_causality(self, message: Mapping[str, Any]) -> None:
        for cause_id in message["causes"]:
            cause = self.messages.get(cause_id)
            if cause is None:
                raise LedgerError("missing_cause", "every cause must already exist")
            if cause["conversation_id"] != message["conversation_id"]:
                raise LedgerError("cross_conversation_cause", "causes must stay within a conversation")
            if cause["logical_clock"] >= message["logical_clock"]:
                raise LedgerError("causal_clock", "logical clock must advance beyond every cause")

    def _check_target_and_ownership(self, message: Mapping[str, Any]) -> None:
        interaction_function, _ = project_interaction_function(
            message["body"], self.profile_document["profile"]
        )
        if interaction_function not in REVISION_FUNCTIONS | EXECUTION_FUNCTIONS | {"CANCEL", "REFUSE"}:
            return
        target_id = _target_message_id(message["body"])
        target = self.messages.get(target_id)
        if target is None:
            raise LedgerError("missing_target", "target message must already exist")
        if target["conversation_id"] != message["conversation_id"]:
            raise LedgerError("cross_conversation_target", "target must stay within a conversation")
        if target["thread_id"] != message["thread_id"]:
            raise LedgerError("cross_thread_target", "target must stay within the envelope thread")
        if target["logical_clock"] >= message["logical_clock"]:
            raise LedgerError("target_clock", "logical clock must advance beyond the target")

        reachable = set(message["causes"])
        pending = list(reachable)
        while pending:
            cause_id = pending.pop()
            cause = self.messages.get(cause_id)
            if cause is None:
                continue
            for ancestor_id in cause["causes"]:
                if ancestor_id not in reachable:
                    reachable.add(ancestor_id)
                    pending.append(ancestor_id)
        if target_id not in reachable:
            raise LedgerError(
                "target_causality",
                "target must be directly or transitively referenced by causes",
            )
        sender = message["sender"]
        scopes = set(message["authorization"]["scopes"])
        if interaction_function in REVISION_FUNCTIONS:
            if sender != target["sender"] and "revise:any" not in scopes:
                raise LedgerError("revision_owner", "only the source owner may revise a message")
        elif interaction_function == "CANCEL":
            if sender != target["sender"] and "cancel:any" not in scopes:
                raise LedgerError("cancellation_owner", "only the target owner may cancel it")
        elif interaction_function == "REFUSE":
            if sender not in target["recipients"]:
                raise LedgerError("refusal_party", "only a requested recipient may refuse")
        elif interaction_function in EXECUTION_FUNCTIONS:
            target_function, _ = project_interaction_function(
                target["body"], self.profile_document["profile"]
            )
            if target_function != "COMMIT":
                raise LedgerError("execution_target", "execution updates must target a commitment")
            if target["body"]["debtor"] != sender:
                raise LedgerError("execution_owner", "only the commitment debtor may update it")

    def _check_transition(self, message: Mapping[str, Any]) -> str | None:
        interaction_function, _ = project_interaction_function(
            message["body"], self.profile_document["profile"]
        )
        transition = INTERACTION_TASK_TRANSITIONS.get(interaction_function)
        if transition is None:
            return None
        allowed, next_state = transition
        thread_key = (message["conversation_id"], message["thread_id"])
        current = self.thread_states.get(thread_key, "NONE")
        if current not in allowed:
            raise LedgerError(
                "illegal_transition",
                f"{interaction_function} cannot transition thread state {current}",
            )
        return next_state

    def append(self, message: Mapping[str, Any]) -> str:
        canonical = validate_message(message, self.profile_document)
        message_id = canonical["id"]
        if message_id in self.messages:
            raise LedgerError("replay", "message ID has already been appended")
        self._check_causality(canonical)
        self._check_target_and_ownership(canonical)
        next_state = self._check_transition(canonical)
        digest = message_digest(canonical)
        self.messages[message_id] = canonical
        self.digests[message_id] = digest
        self.order.append(message_id)
        if next_state is not None:
            thread_key = (canonical["conversation_id"], canonical["thread_id"])
            self.thread_states[thread_key] = next_state
        interaction_function, _ = project_interaction_function(
            canonical["body"], self.profile_document["profile"]
        )
        if interaction_function == "RETRACT":
            self.retracted.add(_target_message_id(canonical["body"]))
        elif interaction_function == "CORRECT":
            self.corrections[_target_message_id(canonical["body"])] = message_id
        return digest

    def snapshot(self) -> dict[str, Any]:
        return {
            "message_count": len(self.order),
            "ordered_message_ids": list(self.order),
            "thread_states": {
                f"{conversation_id}/{thread_id}": state
                for (conversation_id, thread_id), state in sorted(self.thread_states.items())
            },
            "retracted": sorted(self.retracted),
            "corrections": dict(sorted(self.corrections.items())),
            "ledger_digest": content_digest(
                [
                    {"id": message_id, "digest": self.digests[message_id]}
                    for message_id in self.order
                ]
            ),
        }


@dataclass(frozen=True)
class ReceiverContext:
    supported_codecs: frozenset[str]
    verified_schema_digests: frozenset[str]
    verified_profile_digests: frozenset[str]
    execution_authorized: bool


@dataclass(frozen=True)
class FragmentAssessment:
    fragment_id: str
    status: str
    executable: bool
    reason: str
    requested_codec: str | None


def iter_splices(value: Any) -> Iterable[dict[str, Any]]:
    if type(value) is dict:
        if value.get("kind") == "splice":
            yield value
        for child in value.values():
            yield from iter_splices(child)
    elif type(value) is list:
        for child in value:
            yield from iter_splices(child)


def assess_splice(
    splice: Mapping[str, Any],
    receiver: ReceiverContext,
    profile_document: Mapping[str, Any] | None = None,
) -> FragmentAssessment:
    """Assess one splice without granting authority from structural validity."""

    if profile_document is None:
        profile_document = default_profile_document()
    profile = validate_profile_document(profile_document)
    validate_node(splice, profile["profile"])
    codec_key = f"{splice['codec']}@{splice['codec_version']}"
    descriptor = profile["profile"].get("codebooks", {}).get(codec_key)
    requested = next(
        (codec for codec in splice["fallback_chain"] if codec in receiver.supported_codecs),
        None,
    )
    if codec_key not in receiver.supported_codecs:
        return FragmentAssessment(
            splice["fragment_id"],
            "replace_fragment",
            False,
            "receiver_does_not_support_codec",
            requested,
        )
    if descriptor is None or not descriptor.get("verified"):
        return FragmentAssessment(
            splice["fragment_id"],
            "quarantined",
            False,
            "unknown_or_unverified_codec",
            requested,
        )
    if splice["schema_digest"] not in receiver.verified_schema_digests:
        return FragmentAssessment(
            splice["fragment_id"],
            "replace_fragment",
            False,
            "schema_not_verified",
            requested,
        )
    if splice["profile_digest"] not in receiver.verified_profile_digests:
        return FragmentAssessment(
            splice["fragment_id"],
            "replace_fragment",
            False,
            "profile_not_verified",
            requested,
        )
    if splice["loss_mode"] not in {"exact", "lossless_bridge"}:
        return FragmentAssessment(
            splice["fragment_id"],
            "quarantined",
            False,
            "lossy_or_opaque_fragment",
            requested,
        )
    executable = bool(
        splice["execution_eligibility"]
        and receiver.execution_authorized
        and descriptor.get("executable")
    )
    return FragmentAssessment(
        splice["fragment_id"],
        "accepted",
        executable,
        "exact_verified_fragment" if executable else "semantic_only_not_execution_authorized",
        None,
    )


def assess_message_fragments(
    message: Mapping[str, Any],
    receiver: ReceiverContext,
    profile_document: Mapping[str, Any] | None = None,
) -> tuple[FragmentAssessment, ...]:
    if profile_document is None:
        profile_document = default_profile_document()
    canonical = validate_message(message, profile_document)
    identifiers: set[str] = set()
    assessments: list[FragmentAssessment] = []
    for splice in iter_splices(canonical["body"]):
        fragment_id = splice["fragment_id"]
        if fragment_id in identifiers:
            raise ValidationError("fragment_duplicate", "fragment IDs must be unique per message")
        identifiers.add(fragment_id)
        assessments.append(assess_splice(splice, receiver, profile_document))
    return tuple(assessments)


FRAGMENT_PATCH_FIELDS = frozenset(
    {"kind", "message_digest", "fragment_id", "replacement", "patch_digest"}
)


def make_fragment_patch(
    original_message: Mapping[str, Any],
    fragment_id: str,
    replacement: Mapping[str, Any],
    profile_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a fragment-only patch; the original envelope is never embedded."""

    if profile_document is None:
        profile_document = default_profile_document()
    profile = validate_profile_document(profile_document)
    original = validate_message(original_message, profile)
    replacement_copy = validate_node(replacement, profile["profile"])
    if replacement_copy.get("kind") != "splice":
        raise ValidationError("fragment_patch", "replacement must be a splice")
    if replacement_copy["fragment_id"] != fragment_id:
        raise ValidationError("fragment_patch", "replacement fragment ID must be unchanged")
    matches = [splice for splice in iter_splices(original["body"]) if splice["fragment_id"] == fragment_id]
    if len(matches) != 1:
        raise ValidationError("fragment_patch", "fragment patch must target exactly one splice")
    unsigned = {
        "kind": "fragment_patch",
        "message_digest": message_digest(original),
        "fragment_id": fragment_id,
        "replacement": replacement_copy,
    }
    return {**unsigned, "patch_digest": content_digest(unsigned)}


def apply_fragment_patch(
    original_message: Mapping[str, Any],
    patch: Mapping[str, Any],
    profile_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply only the named fragment and preserve every non-target subtree."""

    if profile_document is None:
        profile_document = default_profile_document()
    profile = validate_profile_document(profile_document)
    original = validate_message(original_message, profile)
    if type(patch) is not dict or set(patch) != FRAGMENT_PATCH_FIELDS:
        raise ValidationError("fragment_patch_fields", "fragment patch fields are not exact")
    if patch["kind"] != "fragment_patch":
        raise ValidationError("fragment_patch_kind", "unsupported patch kind")
    unsigned = {key: _deep_copy(patch[key]) for key in FRAGMENT_PATCH_FIELDS - {"patch_digest"}}
    if content_digest(unsigned) != patch["patch_digest"]:
        raise ValidationError("fragment_patch_digest", "fragment patch digest does not match")
    if patch["message_digest"] != message_digest(original):
        raise ValidationError("fragment_patch_target", "patch does not pin the original message")
    replacement = validate_node(patch["replacement"], profile["profile"])
    if replacement.get("kind") != "splice" or replacement.get("fragment_id") != patch["fragment_id"]:
        raise ValidationError("fragment_patch_replacement", "patch replacement identity is invalid")
    replaced = 0

    def visit(value: Any) -> Any:
        nonlocal replaced
        if type(value) is dict:
            if value.get("kind") == "splice" and value.get("fragment_id") == patch["fragment_id"]:
                replaced += 1
                return _deep_copy(replacement)
            return {key: visit(child) for key, child in value.items()}
        if type(value) is list:
            return [visit(child) for child in value]
        return value

    updated = _deep_copy(original)
    updated["body"] = visit(updated["body"])
    if replaced != 1:
        raise ValidationError("fragment_patch_target", "patch must replace exactly one fragment")
    return validate_message(updated, profile)


def fragment_replacement_request(
    original_message: Mapping[str, Any],
    assessment: FragmentAssessment,
) -> dict[str, Any]:
    """Return a fragment-scoped recovery request, never a whole-message resend."""

    if assessment.status != "replace_fragment":
        raise ValidationError("replacement_status", "assessment does not request replacement")
    return {
        "kind": "fragment_replacement_request",
        "message_digest": message_digest(original_message),
        "fragment_id": assessment.fragment_id,
        "scope": "fragment_only",
        "reason": assessment.reason,
        "requested_codec": assessment.requested_codec,
    }


@dataclass(frozen=True)
class CodecCandidate:
    codec: str
    version: str
    receiver_tokens: int
    encode_latency_us: int
    decode_latency_us: int
    risk_ppm: int
    energy_uj: int
    task_utility_ppm: int
    semantics_exact: bool
    receiver_capable: bool
    verified: bool
    authorized: bool
    privacy_allowed: bool
    provenance_verified: bool
    fallback_available: bool
    is_latent: bool = False
    hidden_state_compatible: bool = False

    @property
    def key(self) -> str:
        return f"{self.codec}@{self.version}"


@dataclass(frozen=True)
class SelectionPolicy:
    max_total_latency_us: int
    max_risk_ppm: int
    max_energy_uj: int
    min_task_utility_ppm: int
    effectful: bool
    require_provenance: bool = True
    require_fallback: bool = True


@dataclass(frozen=True)
class SelectionDecision:
    selected: CodecCandidate
    rejected: Mapping[str, tuple[str, ...]]


def _candidate_rejections(candidate: CodecCandidate, policy: SelectionPolicy) -> tuple[str, ...]:
    reasons: list[str] = []
    if type(candidate.receiver_tokens) is not int or candidate.receiver_tokens < 0:
        reasons.append("invalid_receiver_token_cost")
    if not candidate.semantics_exact:
        reasons.append("semantic_exactness")
    if not candidate.receiver_capable:
        reasons.append("receiver_capability")
    if not candidate.verified:
        reasons.append("codec_verification")
    if policy.effectful and not candidate.authorized:
        reasons.append("authorization")
    if candidate.encode_latency_us + candidate.decode_latency_us > policy.max_total_latency_us:
        reasons.append("latency")
    if candidate.risk_ppm > policy.max_risk_ppm:
        reasons.append("risk")
    if candidate.energy_uj > policy.max_energy_uj:
        reasons.append("energy")
    if candidate.task_utility_ppm < policy.min_task_utility_ppm:
        reasons.append("task_utility")
    if not candidate.privacy_allowed:
        reasons.append("privacy")
    if policy.require_provenance and not candidate.provenance_verified:
        reasons.append("provenance")
    if policy.require_fallback and not candidate.fallback_available:
        reasons.append("fallback")
    if candidate.is_latent and not candidate.hidden_state_compatible:
        reasons.append("hidden_state_compatibility")
    return tuple(reasons)


def select_lowest_receiver_token_codec(
    candidates: Sequence[CodecCandidate],
    policy: SelectionPolicy,
) -> SelectionDecision:
    """Apply every hard gate first, then minimize receiver tokenizer cost."""

    rejected: dict[str, tuple[str, ...]] = {}
    eligible: list[CodecCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.key in seen:
            raise SelectionError("duplicate_codec", "codec candidates must have unique keys")
        seen.add(candidate.key)
        reasons = _candidate_rejections(candidate, policy)
        if reasons:
            rejected[candidate.key] = reasons
        else:
            eligible.append(candidate)
    if not eligible:
        raise SelectionError("no_eligible_codec", "no codec passed all hard gates")
    selected = min(
        eligible,
        key=lambda candidate: (
            candidate.receiver_tokens,
            candidate.encode_latency_us + candidate.decode_latency_us,
            candidate.risk_ppm,
            candidate.energy_uj,
            candidate.key,
        ),
    )
    return SelectionDecision(selected=selected, rejected=dict(sorted(rejected.items())))


DELTA_OPERATIONS = frozenset(
    {"add_node", "add_codec", "add_migration", "deprecate_symbol"}
)
MIGRATION_RELATIONS = frozenset({"equivalent", "narrowing", "widening", "transform"})


@dataclass(frozen=True)
class CapsuleDelta:
    base_digest: str
    sequence: int
    proposal_id: str
    changes: tuple[Mapping[str, Any], ...]
    _payload_bytes: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_digest(self.base_digest, "delta.base_digest")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValidationError("delta_sequence", "delta sequence must be positive")
        _require_text(self.proposal_id, "delta.proposal_id")
        if not self.changes:
            raise ValidationError("delta_changes", "delta must contain at least one change")
        for change in self.changes:
            if type(change) is not dict or change.get("op") not in DELTA_OPERATIONS:
                raise ValidationError("delta_operation", "delta contains an unknown operation")
        snapshot = {
            "format": "urusilla-experimental-capsule-delta-v1",
            "base_digest": self.base_digest,
            "sequence": self.sequence,
            "proposal_id": self.proposal_id,
            "changes": [_deep_copy(change) for change in self.changes],
        }
        object.__setattr__(self, "_payload_bytes", canonical_json_bytes(snapshot))

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self._payload_bytes.decode("utf-8"))

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self._payload_bytes).hexdigest()


def _validate_new_node_schema(schema: Any) -> dict[str, list[str]]:
    if type(schema) is not dict or set(schema) != {"required", "optional"}:
        raise GovernanceError("node_schema", "node schema requires required and optional lists")
    required = schema["required"]
    optional = schema["optional"]
    if type(required) is not list or type(optional) is not list:
        raise GovernanceError("node_schema", "node schema fields must be lists")
    if any(type(field_name) is not str or not field_name for field_name in required + optional):
        raise GovernanceError("node_schema", "node field names must be non-empty strings")
    if set(required) & set(optional) or len(set(required + optional)) != len(required + optional):
        raise GovernanceError("node_schema", "node schema fields must be unique")
    return {"required": list(required), "optional": list(optional)}


def apply_capsule_delta(
    profile_document: Mapping[str, Any],
    delta: CapsuleDelta,
) -> dict[str, Any]:
    """Apply an additive/deprecation delta without mutating the base snapshot."""

    base = validate_profile_document(profile_document)
    if delta.base_digest != base["profile_digest"]:
        raise GovernanceError("delta_base", "delta base digest does not match the profile")
    if delta.sequence != base["sequence"] + 1:
        raise GovernanceError("delta_sequence", "delta sequence must immediately follow the base")
    payload = _deep_copy(base["profile"])
    migrations = payload.setdefault("migrations", {})
    deprecated = payload.setdefault("deprecated_symbols", {})
    for change in delta.payload["changes"]:
        operation = change["op"]
        if operation == "add_node":
            if set(change) != {"op", "kind", "schema", "semantics_digest"}:
                raise GovernanceError("delta_fields", "add_node fields are not exact")
            kind = _require_text(change["kind"], "add_node.kind")
            _require_digest(change["semantics_digest"], "add_node.semantics_digest")
            if kind in payload["node_schemas"]:
                raise GovernanceError(
                    "silent_redefinition",
                    "existing node definitions cannot be changed in place",
                )
            payload["node_schemas"][kind] = _validate_new_node_schema(change["schema"])
            payload.setdefault("semantic_fingerprints", {})[kind] = change["semantics_digest"]
        elif operation == "add_codec":
            if set(change) != {"op", "codec_key", "descriptor"}:
                raise GovernanceError("delta_fields", "add_codec fields are not exact")
            codec_key = _require_text(change["codec_key"], "add_codec.codec_key")
            if codec_key in payload["codebooks"]:
                raise GovernanceError("silent_redefinition", "existing codecs cannot be changed in place")
            descriptor = change["descriptor"]
            required_descriptor = {"digest", "exact", "verified", "executable"}
            if type(descriptor) is not dict or set(descriptor) != required_descriptor:
                raise GovernanceError("codec_descriptor", "codec descriptor fields are not exact")
            _require_digest(descriptor["digest"], "codec descriptor digest")
            if any(type(descriptor[field_name]) is not bool for field_name in required_descriptor - {"digest"}):
                raise GovernanceError("codec_descriptor", "codec flags must be booleans")
            payload["codebooks"][codec_key] = _deep_copy(descriptor)
        elif operation == "add_migration":
            required_fields = {
                "op",
                "migration_id",
                "from_symbol",
                "to_symbol",
                "relation",
                "mapping_digest",
                "reversible",
                "requires_review",
            }
            if set(change) != required_fields:
                raise GovernanceError("delta_fields", "add_migration fields are not exact")
            migration_id = _require_text(change["migration_id"], "migration_id")
            if migration_id in migrations:
                raise GovernanceError("silent_redefinition", "migration IDs are immutable")
            if change["relation"] not in MIGRATION_RELATIONS:
                raise GovernanceError("migration_relation", "unknown migration relation")
            _require_digest(change["mapping_digest"], "mapping_digest")
            if type(change["reversible"]) is not bool or type(change["requires_review"]) is not bool:
                raise GovernanceError("migration_flags", "migration flags must be booleans")
            if change["relation"] != "equivalent" and not change["requires_review"]:
                raise GovernanceError(
                    "unsafe_migration",
                    "non-equivalent migrations must require explicit review",
                )
            migrations[migration_id] = {
                key: _deep_copy(value) for key, value in change.items() if key != "op"
            }
        elif operation == "deprecate_symbol":
            if set(change) != {"op", "symbol", "replacement", "migration_id"}:
                raise GovernanceError("delta_fields", "deprecate_symbol fields are not exact")
            symbol = _require_text(change["symbol"], "deprecated symbol")
            replacement = _require_text(change["replacement"], "replacement symbol")
            migration_id = _require_text(change["migration_id"], "migration_id")
            if symbol in deprecated:
                raise GovernanceError("silent_redefinition", "deprecation records are immutable")
            if migration_id not in migrations:
                raise GovernanceError("missing_migration", "deprecation requires an explicit migration")
            migration = migrations[migration_id]
            if migration["from_symbol"] != symbol or migration["to_symbol"] != replacement:
                raise GovernanceError("migration_mismatch", "migration endpoints do not match deprecation")
            deprecated[symbol] = {"replacement": replacement, "migration_id": migration_id}
        else:
            raise AssertionError(operation)
    return wrap_profile(
        payload,
        sequence=delta.sequence,
        parent_digest=base["profile_digest"],
        applied_delta_digest=delta.digest,
    )


def apply_symbol_migration(
    node: Mapping[str, Any],
    migration: Mapping[str, Any],
    *,
    allow_reviewed_non_equivalent: bool = False,
) -> dict[str, Any]:
    """Apply a kind rename only when semantic relation policy permits it."""

    relation = migration.get("relation")
    if relation not in MIGRATION_RELATIONS:
        raise GovernanceError("migration_relation", "unknown migration relation")
    if relation != "equivalent" and not allow_reviewed_non_equivalent:
        raise GovernanceError("migration_review", "non-equivalent migration needs explicit review")
    if node.get("kind") != migration.get("from_symbol"):
        raise GovernanceError("migration_source", "node does not match migration source")
    migrated = _deep_copy(node)
    migrated["kind"] = migration["to_symbol"]
    return migrated


@dataclass
class GrammarProposal:
    delta: CapsuleDelta
    proposer: str
    state: str = "proposed"
    session_trials: list[dict[str, Any]] = field(default_factory=list)
    cross_play: list[dict[str, Any]] = field(default_factory=list)
    ratified_profile_digest: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


SIGNED_APPROVAL_FIELDS = frozenset(
    {
        "signer_id",
        "signer_role",
        "key_id",
        "proposal_id",
        "delta_digest",
        "target_class",
        "statement_digest",
        "signature_b64",
        "signature_verified",
        "verification_method",
    }
)


def _founding_maintainer_approval_statement(
    proposal: GrammarProposal,
    target_class: str,
) -> dict[str, str]:
    return {
        "action": "approve_capsule_ratification",
        "signer_id": FOUNDING_MAINTAINER_ID,
        "proposal_id": proposal.delta.proposal_id,
        "delta_digest": proposal.delta.digest,
        "target_class": target_class,
    }


def make_signed_founding_maintainer_approval_fixture(
    proposal: GrammarProposal,
    target_class: str = "core",
) -> dict[str, Any]:
    """Create deterministic external-verifier evidence for lifecycle tests only.

    The fixture is not a real Founding Maintainer signature and cannot authorize
    an official release. Production deployments must replace it with evidence
    emitted by an authenticated signature verifier.
    """

    statement = _founding_maintainer_approval_statement(proposal, target_class)
    fixture_signature = hashlib.sha256(
        b"research-fixture-not-a-real-founder-signature\x00"
        + canonical_json_bytes(statement)
    ).digest()
    return {
        "signer_id": FOUNDING_MAINTAINER_ID,
        "signer_role": "Founding Maintainer",
        "key_id": "urn:urusilla:experimental:key:founding-maintainer-fixture",
        "proposal_id": proposal.delta.proposal_id,
        "delta_digest": proposal.delta.digest,
        "target_class": target_class,
        "statement_digest": content_digest(statement),
        "signature_b64": base64.b64encode(fixture_signature).decode("ascii"),
        "signature_verified": True,
        "verification_method": "external_signature_verifier_research_fixture",
    }


def validate_signed_founding_maintainer_approval(
    approval: Mapping[str, Any] | None,
    proposal: GrammarProposal,
    target_class: str,
) -> str:
    """Validate a bound external signature-verification record and return its digest."""

    if type(approval) is not dict or set(approval) != SIGNED_APPROVAL_FIELDS:
        raise GovernanceError(
            "founding_maintainer_approval",
            "ratification requires an exact signed Founding Maintainer approval record",
        )
    if approval["signer_id"] != FOUNDING_MAINTAINER_ID:
        raise GovernanceError(
            "founding_maintainer_approval",
            "approval signer must be the registered Founding Maintainer",
        )
    if approval["signer_role"] != "Founding Maintainer":
        raise GovernanceError(
            "founding_maintainer_approval",
            "approval signer role must be Founding Maintainer",
        )
    _require_identifier(approval["key_id"], "approval.key_id")
    if approval["proposal_id"] != proposal.delta.proposal_id:
        raise GovernanceError("founding_maintainer_approval", "approval proposal binding differs")
    if approval["delta_digest"] != proposal.delta.digest:
        raise GovernanceError("founding_maintainer_approval", "approval delta binding differs")
    if approval["target_class"] != target_class:
        raise GovernanceError("founding_maintainer_approval", "approval target class differs")
    expected_statement_digest = content_digest(
        _founding_maintainer_approval_statement(proposal, target_class)
    )
    if approval["statement_digest"] != expected_statement_digest:
        raise GovernanceError("founding_maintainer_approval", "approval statement binding differs")
    if approval["signature_verified"] is not True:
        raise GovernanceError(
            "founding_maintainer_approval",
            "Founding Maintainer signature must be verified before ratification",
        )
    if approval["verification_method"] not in {
        "external_signature_verifier",
        "external_signature_verifier_research_fixture",
    }:
        raise GovernanceError(
            "founding_maintainer_approval",
            "approval verification method is not recognized",
        )
    try:
        signature = base64.b64decode(approval["signature_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise GovernanceError(
            "founding_maintainer_approval",
            "approval signature must be canonical base64",
        ) from exc
    if len(signature) < 32:
        raise GovernanceError(
            "founding_maintainer_approval",
            "approval signature evidence is too short",
        )
    return content_digest(approval)


class CapsuleStore:
    """Immutable profile snapshots plus separately collectable codebook bytes."""

    def __init__(self, initial_profile: Mapping[str, Any] | None = None):
        if initial_profile is None:
            initial_profile = default_profile_document()
        initial = validate_profile_document(initial_profile)
        self.profiles: dict[str, bytes] = {
            initial["profile_digest"]: canonical_json_bytes(initial)
        }
        self.active_digest = initial["profile_digest"]
        self.activation_history: list[str] = [self.active_digest]
        self.codebooks: dict[str, bytes] = {}
        self.profile_codebooks: dict[str, set[str]] = {}
        for name, data in DEFAULT_CODEBOOK_BYTES.items():
            digest = bytes_digest(data)
            self.codebooks[digest] = data
        self._index_profile_codebooks(initial)

    def _index_profile_codebooks(self, document: Mapping[str, Any]) -> None:
        digests = {
            descriptor["digest"]
            for descriptor in document["profile"].get("codebooks", {}).values()
        }
        self.profile_codebooks[document["profile_digest"]] = digests

    def get(self, digest: str | None = None) -> dict[str, Any]:
        if digest is None:
            digest = self.active_digest
        raw = self.profiles.get(digest)
        if raw is None:
            raise GovernanceError("unknown_profile", "profile digest is not stored")
        return json.loads(raw.decode("utf-8"))

    def add_codebook(self, data: bytes) -> str:
        if type(data) is not bytes or not data:
            raise GovernanceError("codebook_bytes", "codebook must be non-empty bytes")
        digest = bytes_digest(data)
        self.codebooks.setdefault(digest, data)
        return digest

    def activate(self, document: Mapping[str, Any]) -> str:
        validated = validate_profile_document(document)
        missing = {
            descriptor["digest"]
            for descriptor in validated["profile"].get("codebooks", {}).values()
            if descriptor["digest"] not in self.codebooks
        }
        if missing:
            raise GovernanceError("missing_codebook", f"profile codebooks are missing: {sorted(missing)}")
        digest = validated["profile_digest"]
        raw = canonical_json_bytes(validated)
        existing = self.profiles.get(digest)
        if existing is not None and existing != raw:
            raise GovernanceError("digest_collision", "profile digest collision")
        self.profiles[digest] = raw
        self._index_profile_codebooks(validated)
        self.active_digest = digest
        self.activation_history.append(digest)
        return digest

    def rollback(self, target_digest: str) -> str:
        if target_digest not in self.profiles:
            raise GovernanceError("rollback_target", "rollback profile is not stored")
        self.active_digest = target_digest
        self.activation_history.append(target_digest)
        return target_digest

    def garbage_collect_codebooks(
        self,
        *,
        live_session_profiles: Iterable[str] = (),
        migration_profiles: Iterable[str] = (),
        pinned_codebooks: Iterable[str] = (),
    ) -> tuple[str, ...]:
        """Remove only re-fetchable codebook bytes, never profile or history metadata."""

        retained_profiles = {
            self.active_digest,
            *live_session_profiles,
            *migration_profiles,
        }
        retained_codebooks = set(pinned_codebooks)
        for profile_digest in retained_profiles:
            retained_codebooks.update(self.profile_codebooks.get(profile_digest, set()))
        deleted = tuple(sorted(set(self.codebooks) - retained_codebooks))
        for digest in deleted:
            del self.codebooks[digest]
        return deleted


class GrammarGovernance:
    """Evidence-gated lifecycle for immutable Capsule deltas."""

    def __init__(self, store: CapsuleStore | None = None):
        self.store = CapsuleStore() if store is None else store
        self.proposals: dict[str, GrammarProposal] = {}

    def propose(self, delta: CapsuleDelta, proposer: str, *, authorized: bool) -> str:
        if not authorized:
            raise GovernanceError("governance_authorization", "proposal requires authorization")
        _require_text(proposer, "proposer")
        if delta.proposal_id in self.proposals:
            raise GovernanceError("proposal_replay", "proposal ID already exists")
        if delta.base_digest != self.store.active_digest:
            raise GovernanceError("proposal_base", "proposal must target the active profile")
        proposal = GrammarProposal(delta=delta, proposer=proposer)
        proposal.events.append({"event": "proposed", "delta_digest": delta.digest})
        self.proposals[delta.proposal_id] = proposal
        return delta.digest

    def begin_session_trial(self, proposal_id: str, session_id: str, *, authorized: bool) -> None:
        proposal = self._proposal(proposal_id)
        if not authorized:
            raise GovernanceError("governance_authorization", "trial requires authorization")
        if proposal.state != "proposed":
            raise GovernanceError("lifecycle_transition", "trial must follow proposal")
        _require_uuid(session_id, "session_id")
        proposal.state = "session_trial"
        proposal.events.append({"event": "session_trial", "session_id": session_id})

    def record_session_trial(
        self,
        proposal_id: str,
        *,
        session_id: str,
        implementation: str,
        exact_roundtrips: int,
        cases: int,
        semantic_mismatches: int,
    ) -> None:
        proposal = self._proposal(proposal_id)
        if proposal.state != "session_trial":
            raise GovernanceError("lifecycle_transition", "session evidence requires trial state")
        if type(cases) is not int or cases <= 0 or exact_roundtrips != cases:
            raise GovernanceError("trial_exactness", "all session cases must round-trip exactly")
        if semantic_mismatches != 0:
            raise GovernanceError("trial_semantics", "session trial has semantic mismatches")
        proposal.session_trials.append(
            {
                "session_id": _require_uuid(session_id, "session_id"),
                "implementation": _require_text(implementation, "implementation"),
                "exact_roundtrips": exact_roundtrips,
                "cases": cases,
                "semantic_mismatches": semantic_mismatches,
            }
        )

    def ephemeral_session_profile(
        self,
        proposal_id: str,
        *,
        session_id: str,
        negotiated_non_core: bool,
        safety_gates_passed: bool,
    ) -> dict[str, Any]:
        """Return a session-local trial snapshot without activating or ratifying it."""

        proposal = self._proposal(proposal_id)
        if proposal.state != "session_trial":
            raise GovernanceError("lifecycle_transition", "ephemeral use requires session trial state")
        _require_uuid(session_id, "session_id")
        if not negotiated_non_core:
            raise GovernanceError("ephemeral_scope", "ephemeral deltas are limited to negotiated non-core scope")
        if not safety_gates_passed:
            raise GovernanceError("ephemeral_safety", "every hard safety gate must pass")
        document = apply_capsule_delta(self.store.get(proposal.delta.base_digest), proposal.delta)
        proposal.events.append(
            {
                "event": "ephemeral_session_profile",
                "session_id": session_id,
                "profile_digest": document["profile_digest"],
                "global_activation": False,
                "ratification": False,
            }
        )
        return document

    def promote_cross_play(
        self,
        proposal_id: str,
        implementations: Sequence[str],
        *,
        authorized: bool,
    ) -> None:
        proposal = self._proposal(proposal_id)
        if not authorized:
            raise GovernanceError("governance_authorization", "promotion requires authorization")
        if proposal.state != "session_trial" or not proposal.session_trials:
            raise GovernanceError("lifecycle_transition", "cross-play must follow successful session trial")
        unique = {_require_text(item, "implementation") for item in implementations}
        if len(unique) < 2:
            raise GovernanceError("cross_play_independence", "cross-play needs two implementations")
        proposal.state = "cross_play_candidate"
        proposal.events.append({"event": "cross_play_candidate", "implementations": sorted(unique)})

    def record_cross_play(
        self,
        proposal_id: str,
        *,
        implementation_a: str,
        implementation_b: str,
        exact_roundtrips: int,
        cases: int,
        semantic_mismatches: int,
    ) -> None:
        proposal = self._proposal(proposal_id)
        if proposal.state != "cross_play_candidate":
            raise GovernanceError("lifecycle_transition", "cross-play evidence requires candidate state")
        if implementation_a == implementation_b:
            raise GovernanceError("cross_play_independence", "implementations must differ")
        if type(cases) is not int or cases <= 0 or exact_roundtrips != cases:
            raise GovernanceError("cross_play_exactness", "all cross-play cases must round-trip exactly")
        if semantic_mismatches != 0:
            raise GovernanceError("cross_play_semantics", "cross-play has semantic mismatches")
        proposal.cross_play.append(
            {
                "implementation_a": _require_text(implementation_a, "implementation_a"),
                "implementation_b": _require_text(implementation_b, "implementation_b"),
                "exact_roundtrips": exact_roundtrips,
                "cases": cases,
                "semantic_mismatches": semantic_mismatches,
            }
        )

    def ratify(
        self,
        proposal_id: str,
        ratifiers: Sequence[str],
        *,
        quorum: int,
        authorized: bool,
        signed_founding_maintainer_approval: Mapping[str, Any] | None,
        target_class: str = "core",
    ) -> str:
        proposal = self._proposal(proposal_id)
        if not authorized:
            raise GovernanceError("governance_authorization", "ratification requires authorization")
        if proposal.state != "cross_play_candidate" or not proposal.cross_play:
            raise GovernanceError("lifecycle_transition", "ratification must follow successful cross-play")
        if target_class not in {"core", "official_extension"}:
            raise GovernanceError("ratification_class", "ratification target class is invalid")
        approval_digest = validate_signed_founding_maintainer_approval(
            signed_founding_maintainer_approval,
            proposal,
            target_class,
        )
        unique = {_require_text(ratifier, "ratifier") for ratifier in ratifiers}
        if type(quorum) is not int or quorum < 2 or len(unique) < quorum:
            raise GovernanceError("ratification_quorum", "ratification quorum is not met")
        evolved = apply_capsule_delta(self.store.get(proposal.delta.base_digest), proposal.delta)
        digest = self.store.activate(evolved)
        proposal.state = "ratified"
        proposal.ratified_profile_digest = digest
        proposal.events.append(
            {
                "event": "ratified",
                "ratifiers": sorted(unique),
                "profile_digest": digest,
                "signed_founding_maintainer_approval_digest": approval_digest,
            }
        )
        return digest

    def deprecate(self, proposal_id: str, replacement_profile_digest: str, *, authorized: bool) -> None:
        proposal = self._proposal(proposal_id)
        if not authorized:
            raise GovernanceError("governance_authorization", "deprecation requires authorization")
        if proposal.state != "ratified":
            raise GovernanceError("lifecycle_transition", "only a ratified proposal may be deprecated")
        if replacement_profile_digest not in self.store.profiles:
            raise GovernanceError("deprecation_replacement", "replacement profile is not stored")
        proposal.state = "deprecated"
        proposal.events.append(
            {"event": "deprecated", "replacement_profile_digest": replacement_profile_digest}
        )

    def _proposal(self, proposal_id: str) -> GrammarProposal:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise GovernanceError("unknown_proposal", "proposal ID is unknown")
        return proposal


DEFAULT_SCHEMA_DIGEST = content_digest({"schema": "adaptive-dialogue-coverage-v1"})
DEFAULT_PROVENANCE_DIGEST = content_digest({"source": "deterministic-coverage-generator-v1"})
ALL_SCOPES = tuple(
    sorted(set(INTERACTION_EFFECT_SCOPE.values()) | {"revise:any", "cancel:any"})
)


def _authorization(agent: str, *, verified: bool = True, scopes: Sequence[str] = ALL_SCOPES) -> dict[str, Any]:
    return {
        "principal": agent,
        "key_id": f"urn:key:{agent}:test",
        "verified": verified,
        "scopes": list(scopes),
        "provenance_digest": DEFAULT_PROVENANCE_DIGEST,
    }


def _ref(uri: str) -> dict[str, Any]:
    return {"kind": "ref", "uri": uri}


def _message_ref(message_id: str) -> dict[str, Any]:
    return _ref(f"urn:message:{message_id}")


def _literal(value: str, datatype: str = "urn:datatype:string") -> dict[str, Any]:
    return {"kind": "literal", "datatype": datatype, "value": value}


def _record(**values: Any) -> dict[str, Any]:
    return {
        "kind": "record",
        "entries": [
            {"kind": "entry", "key": key, "value": value}
            for key, value in sorted(values.items())
        ],
    }


def make_splice(
    *,
    fragment_id: str,
    role: str,
    codec: str,
    codec_version: str,
    schema_digest: str,
    profile_digest: str,
    payload: bytes,
    loss_mode: str,
    fallback_chain: Sequence[str],
    execution_eligibility: bool,
) -> dict[str, Any]:
    return {
        "kind": "splice",
        "fragment_id": fragment_id,
        "role": role,
        "codec": codec,
        "codec_version": codec_version,
        "schema_digest": schema_digest,
        "profile_digest": profile_digest,
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "payload_digest": bytes_digest(payload),
        "loss_mode": loss_mode,
        "fallback_chain": list(fallback_chain),
        "execution_eligibility": execution_eligibility,
    }


def _make_message(
    label: str,
    *,
    act: str,
    body: Mapping[str, Any],
    sender: str,
    recipients: Sequence[str],
    logical_clock: int,
    causes: Sequence[str],
    thread_label: str,
    profile_digest: str,
    conversation_id: str,
    verified: bool = True,
    scopes: Sequence[str] = ALL_SCOPES,
) -> dict[str, Any]:
    return {
        "version": MESSAGE_VERSION,
        "id": stable_uuid(f"coverage:message:{label}"),
        "conversation_id": conversation_id,
        "thread_id": stable_uuid(f"coverage:thread:{thread_label}"),
        "sender": sender,
        "recipients": list(recipients),
        "act": act,
        "logical_clock": logical_clock,
        "causes": list(causes),
        "profile_digest": profile_digest,
        "schema_digest": DEFAULT_SCHEMA_DIGEST,
        "body": _deep_copy(body),
        "authorization": _authorization(sender, verified=verified, scopes=scopes),
    }


def build_positive_coverage_corpus(
    profile_document: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Build deterministic coverage for seven wire acts and twenty typed functions."""

    if profile_document is None:
        profile_document = default_profile_document()
    profile = validate_profile_document(profile_document)
    profile_digest = profile["profile_digest"]
    conversation_id = stable_uuid("coverage:conversation:positive")
    messages: list[dict[str, Any]] = []

    def add(
        label: str,
        *,
        act: str,
        body: Mapping[str, Any],
        sender: str = "planner.agent",
        recipients: Sequence[str] = ("executor.agent",),
        thread: str = "semantic",
        causes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if causes is None:
            causes = () if not messages else (messages[-1]["id"],)
        projected_function, wire_act = project_interaction_function(body, profile["profile"])
        if projected_function != act:
            raise AssertionError(
                f"coverage label {act} does not match typed function {projected_function}"
            )
        message = _make_message(
            label,
            act=wire_act,
            body=body,
            sender=sender,
            recipients=recipients,
            logical_clock=len(messages) + 1,
            causes=causes,
            thread_label=thread,
            profile_digest=profile_digest,
            conversation_id=conversation_id,
        )
        messages.append(message)
        return message

    definition = add(
        "definition",
        act="DEFINE",
        sender="schema.agent",
        recipients=("planner.agent", "executor.agent"),
        body={
            "kind": "definition",
            "symbol": "urn:predicate:parcel.ready",
            "version": "1",
            "schema_digest": content_digest({"type": "boolean"}),
            "semantics": {
                "kind": "operator",
                "operator": "iff",
                "operands": [_literal("parcel_scanned"), _literal("route_assigned")],
            },
        },
    )
    add(
        "schema-negotiation",
        act="NEGOTIATE_SCHEMA",
        sender="schema.agent",
        recipients=("planner.agent", "executor.agent"),
        body={
            "kind": "schema_negotiation",
            "offered": [_ref("urn:schema:parcel:1"), _ref("urn:schema:parcel:2")],
            "required_features": [_literal("exact-quantity"), _literal("typed-time")],
            "accepted": _ref("urn:schema:parcel:2"),
            "migration": _ref("urn:migration:parcel:1-to-2"),
        },
    )

    provenance = {
        "kind": "provenance",
        "source": "urn:source:sensor:alpha",
        "digest": content_digest({"reading": 18}),
        "method": "signed-observation",
        "observed_at": {"kind": "time", "relation": "at", "epoch_ms": 1_800_000_000_000},
        "license": _ref("urn:license:cc-by-4.0"),
    }
    main_assertion = add(
        "assertion",
        act="ASSERT",
        sender="observer.agent",
        recipients=("planner.agent",),
        body={
            "kind": "claim",
            "predicate": "urn:predicate:parcel.ready",
            "arguments": [
                _ref("urn:parcel:42"),
                {
                    "kind": "quantity",
                    "mantissa": 1250,
                    "scale": -3,
                    "unit": "urn:unit:kilogram",
                    "comparator": "equal",
                },
                {
                    "kind": "preference",
                    "ordering": [_ref("urn:route:north"), _ref("urn:route:south")],
                    "weight_ppm": 800_000,
                    "tie_policy": "lowest-latency",
                },
                {
                    "kind": "policy",
                    "rule": _ref("urn:policy:no-hazardous-route"),
                    "effect": "deny",
                    "scope": _ref("urn:scope:delivery"),
                    "authority": _ref("urn:authority:operator"),
                },
                {
                    "kind": "budget",
                    "resource": "energy",
                    "limit": {
                        "kind": "quantity",
                        "mantissa": 5000,
                        "scale": 0,
                        "unit": "urn:unit:joule",
                    },
                    "unit": "urn:unit:joule",
                    "consumed": {
                        "kind": "quantity",
                        "mantissa": 1200,
                        "scale": 0,
                        "unit": "urn:unit:joule",
                    },
                },
                {
                    "kind": "uncertainty",
                    "target": _ref("urn:estimate:arrival:42"),
                    "distribution": "urn:distribution:normal",
                    "parameters": _record(mean_ms=4200, standard_deviation_ms=300),
                    "confidence_ppm": 910_000,
                },
                {
                    "kind": "evidence",
                    "target": _ref("urn:predicate:parcel.ready"),
                    "digest": content_digest({"evidence": "scan-42"}),
                    "method": "barcode-scan",
                    "stance": "supports",
                    "provenance": provenance,
                },
                {
                    "kind": "tool_result",
                    "tool": "urn:tool:route-validator",
                    "schema_digest": content_digest({"tool_schema": 1}),
                    "value": _literal("valid"),
                    "provenance": provenance,
                },
                {
                    "kind": "web_fact",
                    "subject": _ref("urn:road:a1"),
                    "predicate": "urn:predicate:status",
                    "object": _literal("open"),
                    "provenance": provenance,
                    "observed_at": {"kind": "time", "relation": "at", "epoch_ms": 1_800_000_001_000},
                },
                {
                    "kind": "working_state",
                    "state_schema": _ref("urn:schema:planner-working-state:1"),
                    "state_digest": content_digest({"frontier": [1, 2]}),
                    "summary": _record(frontier_size=2, best_score=87),
                    "privacy": {"kind": "policy", "rule": _ref("urn:policy:private"), "effect": "restrict", "scope": _ref("urn:scope:session")},
                },
                {
                    "kind": "action_state",
                    "action": {
                        "kind": "action",
                        "capability": "urn:capability:route",
                        "arguments": [_ref("urn:parcel:42")],
                        "effects": [_ref("urn:effect:route-assigned")],
                    },
                    "phase": "prepared",
                    "state_digest": content_digest({"phase": "prepared"}),
                    "checkpoint": _ref("urn:checkpoint:route:42"),
                },
                {
                    "kind": "asset_ref",
                    "uri": "urn:asset:camera-frame:42",
                    "media_type": "image/avif",
                    "digest": content_digest({"external_asset": 42}),
                    "size_bytes": 8_388_608,
                    "chunks": [_ref("urn:asset-chunk:42:0"), _ref("urn:asset-chunk:42:1")],
                },
            ],
            "context": _record(zone=_ref("urn:zone:seoul-1"), source_definition=_message_ref(definition["id"])),
            "valid_time": {
                "kind": "time",
                "relation": "during",
                "epoch_ms": 1_800_000_000_000,
                "duration_ms": 60_000,
                "timezone": "UTC",
            },
        },
    )
    add(
        "query",
        act="QUERY",
        body={
            "kind": "query",
            "target": {
                "kind": "claim",
                "predicate": "urn:predicate:route.available",
                "arguments": [_ref("urn:parcel:42"), _literal("variable:route")],
            },
            "variables": [_literal("route")],
            "answer_schema": content_digest({"answer": "route-ref"}),
        },
    )
    add(
        "clarification",
        act="CLARIFY",
        sender="executor.agent",
        recipients=("planner.agent",),
        body={
            "kind": "clarification",
            "target": _message_ref(messages[-1]["id"]),
            "ambiguity": _literal("route-ranking-basis"),
            "options": [_literal("latency"), _literal("energy")],
        },
    )
    add(
        "capability-query",
        act="DISCOVER",
        body={
            "kind": "capability_query",
            "capability": "urn:capability:route",
            "requirements": [
                {"kind": "policy", "rule": _ref("urn:policy:no-hazardous-route"), "effect": "require", "scope": _ref("urn:scope:delivery")}
            ],
        },
    )
    add(
        "capability-advertisement",
        act="DISCOVER",
        sender="executor.agent",
        recipients=("planner.agent",),
        body={
            "kind": "capability_advertisement",
            "capability": "urn:capability:route",
            "input_schema": content_digest({"route_input": 1}),
            "output_schema": content_digest({"route_output": 1}),
            "limits": [{"kind": "quantity", "mantissa": 100, "scale": 0, "unit": "urn:unit:requests-per-minute"}],
            "policy": {"kind": "policy", "rule": _ref("urn:policy:tenant-isolation"), "effect": "require", "scope": _ref("urn:scope:service")},
        },
    )

    goal = {
        "kind": "goal",
        "condition": {
            "kind": "conditional",
            "if": {"kind": "claim", "predicate": "urn:predicate:road.open", "arguments": [_ref("urn:road:a1")]},
            "then": {
                "kind": "choice",
                "alternatives": [_ref("urn:route:north"), _ref("urn:route:south")],
                "preference": {
                    "kind": "preference",
                    "ordering": [_ref("urn:route:north"), _ref("urn:route:south")],
                    "weight_ppm": 750_000,
                },
                "minimum": 1,
                "maximum": 1,
            },
            "else": _ref("urn:route:hold"),
        },
        "constraints": [
            {"kind": "budget", "resource": "latency", "limit": 5000, "unit": "urn:unit:millisecond"}
        ],
        "priority": 3,
    }
    request = add(
        "task-request",
        act="REQUEST",
        thread="task-success",
        body={
            "kind": "request",
            "goal": goal,
            "deadline": {"kind": "time", "relation": "before", "epoch_ms": 1_800_000_100_000},
            "budget": {"kind": "budget", "resource": "compute", "limit": 4000, "unit": "urn:unit:token"},
        },
    )
    action = {
        "kind": "action",
        "capability": "urn:capability:route",
        "arguments": [_ref("urn:parcel:42")],
        "effects": [_ref("urn:effect:route-assigned")],
        "policy": {"kind": "policy", "rule": _ref("urn:policy:dry-run-first"), "effect": "require", "scope": _ref("urn:scope:execution")},
        "budget": {"kind": "budget", "resource": "compute", "limit": 3000, "unit": "urn:unit:token"},
    }
    proposal = add(
        "task-proposal",
        act="PROPOSE",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-success",
        body={
            "kind": "proposal",
            "mode": "initial",
            "action": action,
            "conditions": [_ref("urn:condition:road-open")],
        },
    )
    counter = add(
        "task-counterproposal",
        act="COUNTERPROPOSE",
        sender="planner.agent",
        recipients=("executor.agent",),
        thread="task-success",
        body={
            "kind": "proposal",
            "mode": "counter",
            "action": action,
            "conditions": [_ref("urn:condition:energy-under-budget")],
            "valid_until": {"kind": "time", "relation": "before", "epoch_ms": 1_800_000_050_000},
        },
    )
    commitment = add(
        "task-commitment",
        act="COMMIT",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-success",
        body={
            "kind": "commitment",
            "debtor": "executor.agent",
            "creditors": ["planner.agent"],
            "goal": goal,
            "expiry_ms": 60_000,
            "verifier": _ref("urn:agent:auditor"),
        },
    )
    add(
        "task-progress",
        act="PROGRESS",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-success",
        body={"kind": "progress", "target": _message_ref(commitment["id"]), "completed_ppm": 300_000, "status": _literal("routing")},
    )
    add(
        "task-partial",
        act="PARTIAL",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-success",
        body={
            "kind": "partial_result",
            "target": _message_ref(commitment["id"]),
            "value": _ref("urn:route:north"),
            "completed_ppm": 800_000,
            "evidence": _ref("urn:evidence:route-simulation"),
        },
    )
    add(
        "task-success",
        act="SUCCEED",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-success",
        body={"kind": "success", "target": _message_ref(commitment["id"]), "result": _ref("urn:route:north")},
    )

    fail_request = add(
        "fail-request",
        act="REQUEST",
        thread="task-failure",
        body={"kind": "request", "goal": goal},
    )
    fail_commitment = add(
        "fail-commitment",
        act="COMMIT",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-failure",
        body={"kind": "commitment", "debtor": "executor.agent", "creditors": ["planner.agent"], "goal": goal, "expiry_ms": 30_000},
    )
    add(
        "task-failure",
        act="FAIL",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-failure",
        body={
            "kind": "failure",
            "target": _message_ref(fail_commitment["id"]),
            "code": "route-blocked",
            "recoverable": True,
            "fallback": _ref("urn:route:south"),
        },
    )

    cancel_request = add(
        "cancel-request",
        act="REQUEST",
        thread="task-cancel",
        body={"kind": "request", "goal": goal},
    )
    add(
        "task-cancel",
        act="CANCEL",
        thread="task-cancel",
        body={"kind": "cancellation", "target": _message_ref(cancel_request["id"]), "reason_code": "priority-changed"},
    )
    refuse_request = add(
        "refuse-request",
        act="REQUEST",
        thread="task-refuse",
        body={"kind": "request", "goal": goal},
    )
    add(
        "task-refuse",
        act="REFUSE",
        sender="executor.agent",
        recipients=("planner.agent",),
        thread="task-refuse",
        body={
            "kind": "refusal",
            "target": _message_ref(refuse_request["id"]),
            "reason_code": "capability-unavailable",
            "alternatives": [_ref("urn:agent:executor-backup")],
        },
    )

    plan = {
        "kind": "plan",
        "steps": [
            {"kind": "plan_step", "step_id": "scan", "action": action, "depends_on": [], "assignee": _ref("urn:agent:scanner")},
            {"kind": "plan_step", "step_id": "route", "action": action, "depends_on": ["scan"], "assignee": _ref("urn:agent:executor")},
        ],
        "goal": goal,
    }
    add(
        "coordination",
        act="COORDINATE",
        sender="planner.agent",
        recipients=("executor.agent", "observer.agent"),
        body={
            "kind": "coordination",
            "participants": [_ref("urn:agent:planner"), _ref("urn:agent:executor"), _ref("urn:agent:observer")],
            "plan": plan,
            "assignments": [
                {"kind": "assignment", "agent": _ref("urn:agent:scanner"), "step_ids": ["scan"], "role": "observer"},
                {"kind": "assignment", "agent": _ref("urn:agent:executor"), "step_ids": ["route"], "role": "debtor"},
            ],
            "quorum": 2,
        },
    )
    add(
        "correction",
        act="CORRECT",
        sender="observer.agent",
        recipients=("planner.agent",),
        body={
            "kind": "correction",
            "target": _message_ref(main_assertion["id"]),
            "replacement": {"kind": "claim", "predicate": "urn:predicate:parcel.ready", "arguments": [_ref("urn:parcel:42"), False]},
            "reason_code": "new-scan",
        },
    )
    add(
        "retraction",
        act="RETRACT",
        sender="observer.agent",
        recipients=("planner.agent",),
        body={"kind": "retraction", "target": _message_ref(main_assertion["id"]), "reason_code": "sensor-invalidated"},
    )
    add(
        "not-understood",
        act="NOT_UNDERSTOOD",
        sender="executor.agent",
        recipients=("planner.agent",),
        body={
            "kind": "not_understood",
            "target": _message_ref(main_assertion["id"]),
            "fragment_ids": ["unsupported-detail"],
            "reason_codes": ["codec-unsupported"],
            "acceptable_codecs": [
                _literal("urusilla-json-fixture@1"),
                _literal("urusilla-wire-v02-fixture@1"),
            ],
            "scope": "fragment_only",
        },
    )
    opaque_splice = make_splice(
        fragment_id="unsupported-detail",
        role="argument",
        codec="natural-language",
        codec_version="human-v1",
        schema_digest=DEFAULT_SCHEMA_DIGEST,
        profile_digest=profile_digest,
        payload=b"opaque bridge fragment",
        loss_mode="opaque",
        fallback_chain=(
            "urusilla-json-fixture@1",
            "urusilla-wire-v02-fixture@1",
        ),
        execution_eligibility=False,
    )
    add(
        "spliced-assertion",
        act="ASSERT",
        body={
            "kind": "claim",
            "predicate": "urn:predicate:external-detail-attached",
            "arguments": [_ref("urn:parcel:42"), opaque_splice],
        },
    )
    return tuple(validate_message(message, profile) for message in messages)


def collect_node_kinds(value: Any) -> set[str]:
    kinds: set[str] = set()
    if type(value) is dict:
        kind = value.get("kind")
        if type(kind) is str and kind in NODE_SCHEMAS:
            kinds.add(kind)
        for child in value.values():
            kinds.update(collect_node_kinds(child))
    elif type(value) is list:
        for child in value:
            kinds.update(collect_node_kinds(child))
    return kinds


NEGATIVE_CASES: tuple[tuple[str, str], ...] = (
    ("message_replay", "replay"),
    ("missing_cause", "missing_cause"),
    ("causal_clock_regression", "causal_clock"),
    ("unauthorized_effect", "authorization_gate"),
    ("commitment_owner_mismatch", "commitment_owner"),
    ("foreign_correction", "revision_owner"),
    ("illegal_task_transition", "illegal_transition"),
    ("cross_thread_target", "cross_thread_target"),
    ("untyped_mapping_escape", "node_kind"),
    ("raw_language_as_native", "raw_language_escape"),
    ("cyclic_plan", "plan_cycle"),
    ("splice_payload_mismatch", "splice_payload_digest"),
    ("unknown_executable_splice", "splice_unknown_executable"),
    ("whole_message_fragment_patch", "fragment_patch_fields"),
    ("capsule_base_mismatch", "delta_base"),
    ("silent_node_redefinition", "silent_redefinition"),
    ("unsafe_automatic_migration", "unsafe_migration"),
    ("governance_lifecycle_skip", "lifecycle_transition"),
    ("automated_metrics_cannot_ratify", "founding_maintainer_approval"),
    ("all_codecs_fail_hard_gates", "no_eligible_codec"),
)


def _proposal_delta(base_digest: str) -> CapsuleDelta:
    new_kind = "literal_v2"
    migration_id = "urn:migration:literal:v1-to-v2"
    return CapsuleDelta(
        base_digest=base_digest,
        sequence=1,
        proposal_id="literal-v2-proposal",
        changes=(
            {
                "op": "add_node",
                "kind": new_kind,
                "schema": _schema(("datatype", "value"), ("language",)),
                "semantics_digest": content_digest(
                    {"meaning": "typed literal with unchanged v1 denotation", "version": 2}
                ),
            },
            {
                "op": "add_migration",
                "migration_id": migration_id,
                "from_symbol": "literal",
                "to_symbol": new_kind,
                "relation": "equivalent",
                "mapping_digest": content_digest({"operation": "rename-kind-only"}),
                "reversible": True,
                "requires_review": False,
            },
            {
                "op": "deprecate_symbol",
                "symbol": "literal",
                "replacement": new_kind,
                "migration_id": migration_id,
            },
        ),
    )


def _run_negative_operation(case_id: str) -> None:
    profile = default_profile_document()
    corpus = list(build_positive_coverage_corpus(profile))
    if case_id == "message_replay":
        ledger = ConversationLedger(profile)
        ledger.append(corpus[0])
        ledger.append(corpus[0])
    elif case_id == "missing_cause":
        message = _deep_copy(corpus[0])
        message["id"] = stable_uuid("negative:missing-cause")
        message["logical_clock"] = 1000
        message["causes"] = [stable_uuid("negative:absent-cause")]
        ConversationLedger(profile).append(message)
    elif case_id == "causal_clock_regression":
        ledger = ConversationLedger(profile)
        ledger.append(corpus[0])
        message = _deep_copy(corpus[1])
        message["id"] = stable_uuid("negative:causal-clock")
        message["logical_clock"] = corpus[0]["logical_clock"]
        ledger.append(message)
    elif case_id == "unauthorized_effect":
        message = _deep_copy(corpus[0])
        message["id"] = stable_uuid("negative:unauthorized-effect")
        message["authorization"]["verified"] = False
        message["authorization"]["scopes"] = []
        validate_message(message, profile)
    elif case_id == "commitment_owner_mismatch":
        index = next(
            index
            for index, message in enumerate(corpus)
            if message_interaction_function(message, profile) == "COMMIT"
        )
        ledger = ConversationLedger(profile)
        for message in corpus[:index]:
            ledger.append(message)
        invalid = _deep_copy(corpus[index])
        invalid["id"] = stable_uuid("negative:commitment-owner")
        invalid["body"]["debtor"] = "intruder.agent"
        ledger.append(invalid)
    elif case_id == "foreign_correction":
        index = next(
            index
            for index, message in enumerate(corpus)
            if message_interaction_function(message, profile) == "CORRECT"
        )
        ledger = ConversationLedger(profile)
        for message in corpus[:index]:
            ledger.append(message)
        invalid = _deep_copy(corpus[index])
        invalid["id"] = stable_uuid("negative:foreign-correction")
        invalid["sender"] = "executor.agent"
        invalid["authorization"] = _authorization("executor.agent", scopes=("revise",))
        ledger.append(invalid)
    elif case_id == "illegal_task_transition":
        propose_index = next(
            index
            for index, message in enumerate(corpus)
            if message_interaction_function(message, profile) == "PROPOSE"
        )
        ledger = ConversationLedger(profile)
        invalid = _deep_copy(corpus[propose_index])
        invalid["id"] = stable_uuid("negative:illegal-transition")
        invalid["conversation_id"] = stable_uuid("negative:empty-conversation")
        invalid["thread_id"] = stable_uuid("negative:empty-thread")
        invalid["logical_clock"] = 1
        invalid["causes"] = []
        ledger.append(invalid)
    elif case_id == "cross_thread_target":
        progress_index = next(
            index
            for index, message in enumerate(corpus)
            if message_interaction_function(message, profile) == "PROGRESS"
        )
        ledger = ConversationLedger(profile)
        for message in corpus[:progress_index]:
            ledger.append(message)
        invalid = _deep_copy(corpus[progress_index])
        invalid["id"] = stable_uuid("negative:cross-thread-target")
        invalid["thread_id"] = stable_uuid("negative:other-thread")
        invalid["logical_clock"] = 1000
        ledger.append(invalid)
    elif case_id == "untyped_mapping_escape":
        invalid = _deep_copy(corpus[2])
        invalid["body"]["arguments"].append({"raw": "untyped"})
        validate_message(invalid, profile)
    elif case_id == "raw_language_as_native":
        validate_node(
            {
                "kind": "literal",
                "datatype": "urn:datatype:natural-language",
                "value": "untyped escape",
            },
            profile["profile"],
        )
    elif case_id == "cyclic_plan":
        coordination = next(
            message
            for message in corpus
            if message_interaction_function(message, profile) == "COORDINATE"
        )
        invalid = _deep_copy(coordination)
        invalid["body"]["plan"]["steps"][0]["depends_on"] = ["route"]
        validate_message(invalid, profile)
    elif case_id == "splice_payload_mismatch":
        spliced = corpus[-1]
        invalid = _deep_copy(spliced)
        splice = next(iter(iter_splices(invalid["body"])))
        splice["payload_digest"] = "sha256:" + "0" * 64
        validate_message(invalid, profile)
    elif case_id == "unknown_executable_splice":
        validate_node(
            make_splice(
                fragment_id="unknown-exec",
                role="action_state",
                codec="unknown-latent",
                codec_version="1",
                schema_digest=DEFAULT_SCHEMA_DIGEST,
                profile_digest=profile["profile_digest"],
                payload=b"not verified",
                loss_mode="exact",
                fallback_chain=("urusilla-json-fixture@1",),
                execution_eligibility=True,
            ),
            profile["profile"],
        )
    elif case_id == "whole_message_fragment_patch":
        original = corpus[-1]
        replacement = make_splice(
            fragment_id="unsupported-detail",
            role="argument",
            codec="urusilla-json-fixture",
            codec_version="1",
            schema_digest=DEFAULT_SCHEMA_DIGEST,
            profile_digest=profile["profile_digest"],
            payload=canonical_json_bytes(_literal("replacement")),
            loss_mode="exact",
            fallback_chain=("urusilla-wire-v02-fixture@1",),
            execution_eligibility=False,
        )
        patch = make_fragment_patch(original, "unsupported-detail", replacement, profile)
        patch["message"] = original
        apply_fragment_patch(original, patch, profile)
    elif case_id == "capsule_base_mismatch":
        delta = CapsuleDelta(
            base_digest="sha256:" + "0" * 64,
            sequence=1,
            proposal_id="bad-base",
            changes=(
                {
                    "op": "add_node",
                    "kind": "new_node",
                    "schema": _schema(("value",)),
                    "semantics_digest": content_digest({"new": 1}),
                },
            ),
        )
        apply_capsule_delta(profile, delta)
    elif case_id == "silent_node_redefinition":
        delta = CapsuleDelta(
            base_digest=profile["profile_digest"],
            sequence=1,
            proposal_id="silent-redefinition",
            changes=(
                {
                    "op": "add_node",
                    "kind": "claim",
                    "schema": _schema(("different",)),
                    "semantics_digest": content_digest({"different": True}),
                },
            ),
        )
        apply_capsule_delta(profile, delta)
    elif case_id == "unsafe_automatic_migration":
        delta = CapsuleDelta(
            base_digest=profile["profile_digest"],
            sequence=1,
            proposal_id="unsafe-migration",
            changes=(
                {
                    "op": "add_migration",
                    "migration_id": "urn:migration:unsafe",
                    "from_symbol": "claim",
                    "to_symbol": "claim-narrower",
                    "relation": "narrowing",
                    "mapping_digest": content_digest({"mapping": "unsafe"}),
                    "reversible": False,
                    "requires_review": False,
                },
            ),
        )
        apply_capsule_delta(profile, delta)
    elif case_id == "governance_lifecycle_skip":
        governance = GrammarGovernance()
        delta = _proposal_delta(governance.store.active_digest)
        governance.propose(delta, "governor.agent", authorized=True)
        governance.ratify(
            delta.proposal_id,
            ("ratifier-a", "ratifier-b"),
            quorum=2,
            authorized=True,
            signed_founding_maintainer_approval=None,
        )
    elif case_id == "automated_metrics_cannot_ratify":
        governance = GrammarGovernance()
        delta = _proposal_delta(governance.store.active_digest)
        governance.propose(delta, "governor.agent", authorized=True)
        session_id = stable_uuid("negative:metrics-only-session")
        governance.begin_session_trial(delta.proposal_id, session_id, authorized=True)
        governance.record_session_trial(
            delta.proposal_id,
            session_id=session_id,
            implementation="runtime-a",
            exact_roundtrips=10,
            cases=10,
            semantic_mismatches=0,
        )
        governance.promote_cross_play(
            delta.proposal_id,
            ("runtime-a", "runtime-b"),
            authorized=True,
        )
        governance.record_cross_play(
            delta.proposal_id,
            implementation_a="runtime-a",
            implementation_b="runtime-b",
            exact_roundtrips=10,
            cases=10,
            semantic_mismatches=0,
        )
        governance.ratify(
            delta.proposal_id,
            ("automated-evaluator-a", "automated-evaluator-b"),
            quorum=2,
            authorized=True,
            signed_founding_maintainer_approval=None,
        )
    elif case_id == "all_codecs_fail_hard_gates":
        select_lowest_receiver_token_codec(
            (
                CodecCandidate(
                    "opaque",
                    "1",
                    1,
                    1,
                    1,
                    0,
                    1,
                    1_000_000,
                    False,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                ),
            ),
            SelectionPolicy(100, 1000, 100, 900_000, False),
        )
    else:
        raise AssertionError(case_id)
    raise AssertionError(f"negative case {case_id} was unexpectedly accepted")


def run_negative_coverage() -> tuple[dict[str, Any], ...]:
    """Execute the deterministic negative corpus and record exact failure codes."""

    results: list[dict[str, Any]] = []
    for case_id, expected_code in NEGATIVE_CASES:
        observed_code: str | None = None
        try:
            _run_negative_operation(case_id)
        except DialogueError as exc:
            observed_code = exc.code
        rejected = observed_code == expected_code
        results.append(
            {
                "case_id": case_id,
                "expected_code": expected_code,
                "observed_code": observed_code,
                "rejected": rejected,
            }
        )
    return tuple(results)


def _selection_demonstration() -> SelectionDecision:
    policy = SelectionPolicy(
        max_total_latency_us=500,
        max_risk_ppm=10_000,
        max_energy_uj=10_000,
        min_task_utility_ppm=950_000,
        effectful=True,
    )
    candidates = (
        CodecCandidate(
            "urusilla-json-fixture",
            "1",
            900,
            30,
            40,
            1_000,
            7_000,
            995_000,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ),
        CodecCandidate(
            "urusilla-wire-v02-fixture",
            "1",
            500,
            120,
            150,
            2_000,
            9_000,
            990_000,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ),
        CodecCandidate(
            "latent-fast-path",
            "model-a-to-b-v1",
            80,
            10,
            10,
            1_000,
            800,
            990_000,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            is_latent=True,
            hidden_state_compatible=False,
        ),
        CodecCandidate(
            "privacy-leaking-codec",
            "1",
            20,
            5,
            5,
            1_000,
            100,
            999_000,
            True,
            True,
            True,
            True,
            False,
            True,
            True,
        ),
    )
    return select_lowest_receiver_token_codec(candidates, policy)


def run_conformance() -> dict[str, Any]:
    profile = default_profile_document()
    corpus = build_positive_coverage_corpus(profile)
    ledger = ConversationLedger(profile)
    for message in corpus:
        ledger.append(message)
    covered_acts = sorted({message["act"] for message in corpus})
    covered_functions = sorted(
        {message_interaction_function(message, profile) for message in corpus}
    )
    covered_nodes = sorted(
        set().union(*(collect_node_kinds(message["body"]) for message in corpus))
    )
    negative = run_negative_coverage()

    original = corpus[-1]
    receiver = ReceiverContext(
        supported_codecs=frozenset(
            {
                "urusilla-json-fixture@1",
                "urusilla-wire-v02-fixture@1",
            }
        ),
        verified_schema_digests=frozenset({DEFAULT_SCHEMA_DIGEST}),
        verified_profile_digests=frozenset({profile["profile_digest"]}),
        execution_authorized=False,
    )
    original_assessment = assess_message_fragments(original, receiver, profile)
    replacement = make_splice(
        fragment_id="unsupported-detail",
        role="argument",
        codec="urusilla-json-fixture",
        codec_version="1",
        schema_digest=DEFAULT_SCHEMA_DIGEST,
        profile_digest=profile["profile_digest"],
        payload=canonical_json_bytes(_record(detail=_literal("typed replacement"))),
        loss_mode="exact",
        fallback_chain=("urusilla-wire-v02-fixture@1",),
        execution_eligibility=False,
    )
    patch = make_fragment_patch(original, "unsupported-detail", replacement, profile)
    patched = apply_fragment_patch(original, patch, profile)
    patched_assessment = assess_message_fragments(patched, receiver, profile)

    governance = GrammarGovernance()
    initial_digest = governance.store.active_digest
    delta = _proposal_delta(initial_digest)
    governance.propose(delta, "governor.agent", authorized=True)
    session_id = stable_uuid("governance:trial:session")
    governance.begin_session_trial(delta.proposal_id, session_id, authorized=True)
    ephemeral = governance.ephemeral_session_profile(
        delta.proposal_id,
        session_id=session_id,
        negotiated_non_core=True,
        safety_gates_passed=True,
    )
    ephemeral_global_active_unchanged = governance.store.active_digest == initial_digest
    governance.record_session_trial(
        delta.proposal_id,
        session_id=session_id,
        implementation="reference-python-a",
        exact_roundtrips=46,
        cases=46,
        semantic_mismatches=0,
    )
    governance.promote_cross_play(
        delta.proposal_id,
        ("reference-python-a", "independent-runtime-b"),
        authorized=True,
    )
    governance.record_cross_play(
        delta.proposal_id,
        implementation_a="reference-python-a",
        implementation_b="independent-runtime-b",
        exact_roundtrips=46,
        cases=46,
        semantic_mismatches=0,
    )
    signed_approval = make_signed_founding_maintainer_approval_fixture(
        governance.proposals[delta.proposal_id]
    )
    signed_approval_digest = content_digest(signed_approval)
    ratified_digest = governance.ratify(
        delta.proposal_id,
        ("ratifier-a", "ratifier-b", "ratifier-c"),
        quorum=2,
        authorized=True,
        signed_founding_maintainer_approval=signed_approval,
    )
    ratified = governance.store.get(ratified_digest)
    migration = ratified["profile"]["migrations"]["urn:migration:literal:v1-to-v2"]
    migrated = apply_symbol_migration(_literal("example"), migration)
    governance.store.rollback(initial_digest)
    orphan_digest = governance.store.add_codebook(b"orphan-re-fetchable-codebook")
    deleted = governance.store.garbage_collect_codebooks(
        live_session_profiles=(ratified_digest,),
        migration_profiles=(initial_digest, ratified_digest),
    )
    governance.deprecate(delta.proposal_id, initial_digest, authorized=True)

    selection = _selection_demonstration()
    result = {
        "profile_digest": profile["profile_digest"],
        "positive_messages": len(corpus),
        "positive_accepted": len(ledger.order),
        "acts_covered": len(covered_acts),
        "acts_total": len(CORE_WIRE_ACTS),
        "interaction_functions_covered": len(covered_functions),
        "interaction_functions_total": len(INTERACTION_FUNCTION_BODY_KINDS),
        "nodes_covered": len(covered_nodes),
        "nodes_total": len(NODE_SCHEMAS),
        "covered_acts": covered_acts,
        "covered_interaction_functions": covered_functions,
        "interaction_projection": interaction_projection_rows(),
        "covered_nodes": covered_nodes,
        "corpus_digest": content_digest(list(corpus)),
        "ledger": ledger.snapshot(),
        "negative_cases": list(negative),
        "negative_rejected": sum(result["rejected"] for result in negative),
        "fragment": {
            "original_status": original_assessment[0].status,
            "original_requested_codec": original_assessment[0].requested_codec,
            "patch_fields": sorted(patch),
            "patch_contains_whole_message": "message" in patch,
            "patched_status": patched_assessment[0].status,
            "patched_executable": patched_assessment[0].executable,
            "non_target_envelope_fields_unchanged": all(
                original[key] == patched[key] for key in MESSAGE_FIELDS - {"body"}
            ),
        },
        "selection": {
            "selected": selection.selected.key,
            "selected_receiver_tokens": selection.selected.receiver_tokens,
            "rejected": {key: list(reasons) for key, reasons in selection.rejected.items()},
        },
        "grammar": {
            "delta_digest": delta.digest,
            "ratified_profile_digest": ratified_digest,
            "signed_approval_evidence_digest": signed_approval_digest,
            "ephemeral_profile_digest": ephemeral["profile_digest"],
            "ephemeral_global_active_unchanged": ephemeral_global_active_unchanged,
            "rollback_active_digest": governance.store.active_digest,
            "proposal_state": governance.proposals[delta.proposal_id].state,
            "migration_result_kind": migrated["kind"],
            "orphan_codebook_digest": orphan_digest,
            "orphan_codebook_collected": orphan_digest in deleted,
            "profile_snapshots_retained": len(governance.store.profiles),
            "activation_history": list(governance.store.activation_history),
        },
    }
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def render_results(result: Mapping[str, Any], profile_path: Path) -> str:
    script_dir = Path(__file__).resolve().parent
    lines = [
        "# Adaptive semantic dialogue experiment",
        "",
        "## Result",
        "",
        f"The dependency-free reference accepted `{result['positive_accepted']}/{result['positive_messages']}` "
        f"deterministic positive dialogue messages, exercised exactly `{result['acts_covered']}/{result['acts_total']}` "
        f"canonical v0.1 wire acts, `{result['interaction_functions_covered']}/{result['interaction_functions_total']}` "
        f"typed interaction functions, and `{result['nodes_covered']}/{result['nodes_total']}` typed node kinds, and rejected "
        f"`{result['negative_rejected']}/{len(result['negative_cases'])}` representative negative cases with "
        "their expected fail-closed error codes. The corpus SHA-256 is "
        f"`{result['corpus_digest']}`.",
        "",
        "This is **representational and protocol-mechanism coverage**, not proof of every human meaning, "
        "model understanding, task quality, energy savings, security against every adversary, or adoption. "
        "Raw natural language is not counted as native semantic coverage.",
        "",
        "Machine status is `research_fixture_not_official_extension`. It pins core language version "
        "`0.1.0` and declares its relationship as "
        "`experimental_external_dialogue_projection`. It is not an official language version, extension, or "
        "standards claim.",
        "",
        "## Architecture boundary",
        "",
        "The first deployment target is the external LLM-to-LLM utterance layer. Internal reasoning remains "
        "model-specific. The protocol neither requires nor encourages disclosure of private chain-of-thought. "
        "It is a semantic payload/control layer over existing transports; it does not replace HTTP, TCP, A2A, "
        "MCP, routing, congestion control, or cryptographic identity infrastructure. Large image, audio, video, "
        "model, and dataset objects remain external content-addressed assets carried by typed `asset_ref` nodes.",
        "",
        "The staged north star is:",
        "",
        "1. Replace external agent dialogue where exact semantics and fragment-local fallback are demonstrated.",
        "2. Extend typed exchange to tool and web information with schema, provenance, privacy, and asset-integrity gates.",
        "3. Add model-native working-memory and action-state exchange through explicit schemas without exposing chain-of-thought.",
        "4. Permit optional latent fast paths only for compatible hidden-state interfaces with an exact semantic decoder and fallback.",
        "5. Evolve toward a federated Internet semantic control plane after open conformance and governance exist.",
        "",
        "Every codec decision passes semantic exactness, receiver capability, authorization, latency, risk, "
        "privacy, hidden-state compatibility, provenance, energy/task-utility, and fallback gates before token "
        "cost is minimized.",
        "",
        "## Typed dialogue coverage",
        "",
        "Covered canonical wire acts:",
        "",
        "`" + "`, `".join(result["covered_acts"]) + "`",
        "",
        "Covered typed interaction functions:",
        "",
        "`" + "`, `".join(result["covered_interaction_functions"]) + "`",
        "",
        "Covered node kinds:",
        "",
        "`" + "`, `".join(result["covered_nodes"]) + "`",
        "",
        "The corpus covers assertion; query and clarification; request; capability discovery and "
        "advertisement; proposal and counterproposal; conditionals and choices; plan DAGs; commitments; "
        "refusal, cancellation, progress, partial result, success, and failure; retraction and correction; "
        "definition and schema negotiation; time, exact quantity, preferences, policy, and budget; uncertainty "
        "and evidence; multi-party coordination; and not-understood recovery. Tool results, web facts, working "
        "state, action state, provenance, and external modality references are also typed.",
        "",
        "### Deterministic projection to the v0.1 wire",
        "",
        "Interaction functions are inferred from typed body kinds and the closed `proposal.mode` enum; "
        "there is no free-form intent field or escape. Every message is rejected unless the inferred function "
        "projects to its declared canonical wire act.",
        "",
        "| Interaction function | Typed body selector | Canonical wire act |",
        "|---|---|---|",
    ]
    for row in result["interaction_projection"]:
        selector = row["body_kind"]
        if row["discriminator"] is not None:
            selector += f"[{row['discriminator']['field']}={row['discriminator']['equals']}]"
        lines.append(
            f"| `{row['interaction_function']}` | `{selector}` | `{row['wire_act']}` |"
        )
    lines.extend(
        [
        "",
        "The conversation ledger produced:",
        "",
        f"- Ledger SHA-256: `{result['ledger']['ledger_digest']}`",
        f"- Final state machines: `{len(result['ledger']['thread_states'])}`",
        f"- Retractions recorded: `{len(result['ledger']['retracted'])}`",
        f"- Corrections recorded: `{len(result['ledger']['corrections'])}`",
        "",
        "Append checks bind UUID replay protection, causal predecessors, monotonic logical clocks, conversation "
        "scope, task transitions, commitment debtor identity, execution-result ownership, cancellation rights, "
        "revision ownership, sender authentication, and effect scopes.",
        "",
        "## Fragment-local code switching",
        "",
        f"The unsupported example fragment returned `{result['fragment']['original_status']}` with requested "
        f"fallback `{result['fragment']['original_requested_codec']}`. Its patch contained only fields "
        f"`{', '.join(result['fragment']['patch_fields'])}`; whole-message embedding was "
        f"`{str(result['fragment']['patch_contains_whole_message']).lower()}`. After replacement, status was "
        f"`{result['fragment']['patched_status']}` and every envelope field outside the body remained unchanged: "
        f"`{str(result['fragment']['non_target_envelope_fields_unchanged']).lower()}`.",
        "",
        "A splice pins fragment role, codec and version, schema and profile digests, payload digest, loss mode, "
        "fallback chain, and execution eligibility. Unsupported content requests replacement of that fragment "
        "only. Unknown, unverified, lossy, opaque, unauthorized, schema-unverified, or profile-unverified "
        "fragments cannot execute. An opaque natural-language bridge may be quarantined for a human or bridge "
        "decoder, but it never becomes native coverage merely by being carried.",
        "",
        "## Receiver-token codec selection",
        "",
        f"The deterministic selection example chose `{result['selection']['selected']}` at "
        f"`{result['selection']['selected_receiver_tokens']}` receiver tokens after hard gates. Rejections were:",
        "",
        "| Candidate | Hard-gate reasons |",
        "|---|---|",
        ]
    )
    for codec, reasons in result["selection"]["rejected"].items():
        lines.append(f"| `{codec}` | `{', '.join(reasons)}` |")
    lines.extend(
        [
            "",
            "The numeric values in this selector example are deterministic fixtures, not measurements. The "
            "selector's tested property is ordering: no lower-token candidate can bypass a hard gate. A latent "
            "candidate is optional and must prove hidden-state compatibility; incompatibility routes to a "
            "semantic fallback rather than silently changing meaning.",
            "",
            "## Continuous grammar evolution",
            "",
            f"- Base profile: `{result['profile_digest']}`",
            f"- Immutable delta: `{result['grammar']['delta_digest']}`",
            f"- Ephemeral session profile: `{result['grammar']['ephemeral_profile_digest']}`",
            f"- Ephemeral trial left global active profile unchanged: `{str(result['grammar']['ephemeral_global_active_unchanged']).lower()}`",
            f"- Fixture-local ratified profile: `{result['grammar']['ratified_profile_digest']}`",
            f"- Signed approval evidence fixture: `{result['grammar']['signed_approval_evidence_digest']}`",
            f"- Post-rollback active profile: `{result['grammar']['rollback_active_digest']}`",
            f"- Final proposal lifecycle state: `{result['grammar']['proposal_state']}`",
            f"- Equivalent migration output kind: `{result['grammar']['migration_result_kind']}`",
            f"- Orphan codebook cache entry collected: `{str(result['grammar']['orphan_codebook_collected']).lower()}`",
            f"- Immutable profile snapshots retained: `{result['grammar']['profile_snapshots_retained']}`",
            "",
            "A delta pins its base digest and sequence. The seven core wire acts are fixed; existing node, codec, "
            "migration, and deprecation records cannot be redefined in place. Non-equivalent migrations require explicit review. Promotion "
            "follows `proposed -> session_trial -> cross_play_candidate -> ratified -> deprecated`; session and "
            "cross-play evidence require exact round-trip with zero recorded semantic mismatches. Rollback changes "
            "the active pointer without deleting snapshots. Garbage collection removes only re-fetchable "
            "codebook bytes not referenced by active, live-session, migration, or pinned profiles.",
            "",
            "During founder-led Experimental Stewardship, agents may propose, trial, and evaluate grammar changes, "
            "but core or official-extension meaning cannot be ratified without an externally verified, signed "
            "Founding Maintainer approval record bound to the proposal, delta, and target class. Automated scores "
            "and lifecycle events are evidence, never ratification authority. An "
            "ephemeral session-local delta is permitted only in negotiated non-core scope after every hard safety "
            "gate passes; it is pinned to the session, is not globally activated, and makes no ratification claim.",
            "",
            "## Negative corpus",
            "",
            "| Case | Expected code | Observed code | Rejected |",
            "|---|---|---|---:|",
        ]
    )
    for case in result["negative_cases"]:
        lines.append(
            f"| `{case['case_id']}` | `{case['expected_code']}` | `{case['observed_code']}` | "
            f"{str(case['rejected']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Reproduction and artifact identity",
            "",
            "```text",
            "PYTHONPATH=. python urusilla_adaptive_dialogue.py",
            "PYTHONPATH=. python -m unittest test_urusilla_adaptive_dialogue.py -v",
            "```",
            "",
            f"Profile wrapper digest: `{result['profile_digest']}`  ",
            f"Profile file SHA-256: `{_file_sha256(profile_path)}`  ",
        ]
    )
    for filename in ("urusilla_adaptive_dialogue.py", "test_urusilla_adaptive_dialogue.py"):
        path = script_dir / filename
        if path.is_file():
            lines.append(f"`{filename}` SHA-256: `{_file_sha256(path)}`  ")
    lines.extend(
        [
            "",
            "## Limits and next evidence",
            "",
            "The profile is a designed vocabulary and the corpus was written against it, so full coverage is "
            "expected and in-sample. It does not establish open-world completeness. The grammar trial and "
            "cross-play implementations in this file are state-machine fixtures, not independent software "
            "implementations or model families. The selection costs are fixtures, not a performance benchmark. "
            "Content digests detect mismatch but do not provide signatures, confidentiality, identity, or trust "
            "by themselves. The included signed-approval record is a deterministic state-machine fixture, not a "
            "real Founding Maintainer signature or an official ratification; deployment must supply authenticated "
            "external signature verification.",
            "",
            "The next credible gates are held-out human intent suites, independently implemented cross-play, "
            "multi-model task-success parity, privacy red teaming, authenticated provenance, equivalent natural-"
            "language baselines, measured receiver tokens/latency/energy, and adversarial governance tests. "
            "Internet-wide use should not be claimed before those gates pass.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-output",
        type=Path,
        default=Path(__file__).with_name("urusilla_adaptive_dialogue_profile.json"),
    )
    parser.add_argument(
        "--results-output",
        type=Path,
        default=Path(__file__).with_name("urusilla_adaptive_dialogue_results.md"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = default_profile_document()
    args.profile_output.parent.mkdir(parents=True, exist_ok=True)
    args.profile_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = run_conformance()
    report = render_results(result, args.profile_output)
    args.results_output.parent.mkdir(parents=True, exist_ok=True)
    args.results_output.write_text(report, encoding="utf-8")
    print(f"wrote {args.profile_output}")
    print(f"wrote {args.results_output}")
    print(
        f"positive={result['positive_accepted']}/{result['positive_messages']} "
        f"acts={result['acts_covered']}/{result['acts_total']} "
        f"functions={result['interaction_functions_covered']}/{result['interaction_functions_total']} "
        f"nodes={result['nodes_covered']}/{result['nodes_total']} "
        f"negative={result['negative_rejected']}/{len(result['negative_cases'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
