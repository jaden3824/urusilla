#!/usr/bin/env python3
"""Dependency-free static validation for the Urusilla HF dataset pack.

This validator reads local declarative files only. It does not fetch URLs,
contact a model, execute dataset content, or authorize an external effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence


PACK_DIR = Path(__file__).resolve().parent
DATA_PATH = PACK_DIR / "data" / "challenge.jsonl"
SCHEMA_PATH = PACK_DIR / "schema.json"
CARD_PATH = PACK_DIR / "README.md"

SCHEMA_VERSION = "urusilla-hf-external-reproduction/1"
RECORD_ID = "urusilla-external-reproduction-001"
PINNED_COMMIT = "1358de54c8a7034ee057a47e252e8947fe042f55"
CAPSULE_DIGEST = (
    "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
)
CAPSULE_REF = "sha256:" + CAPSULE_DIGEST
CAPSULE_URI = (
    "https://raw.githubusercontent.com/jaden3824/urusilla/"
    f"{PINNED_COMMIT}/urusilla_capsule_v0_1.json"
)
INTEROP_URI = (
    "https://github.com/jaden3824/urusilla/blob/"
    f"{PINNED_COMMIT}/INTEROP_LAB.md"
)
SPEC_URI = (
    "https://github.com/jaden3824/urusilla/blob/"
    f"{PINNED_COMMIT}/urusilla_v0_1_spec.md"
)

TOP_LEVEL_KEYS = {
    "schema_version",
    "record_id",
    "record_type",
    "protocol",
    "known_evidence",
    "challenge",
    "safety_boundary",
    "data_governance",
}

TOKEN_LEDGER_CATEGORIES = [
    "task_input",
    "system_role",
    "agent_input_history",
    "agent_output_visible",
    "final_answer",
    "format_induction",
    "encode_decode_model",
    "negotiation_profile",
    "repair_retry",
    "tool_request",
    "tool_result",
    "safety_filter",
    "hidden_reasoning_billed",
    "unclassified",
    "total_tokens",
]

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_FILE_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_NODES = 50_000
MAX_STRING_CHARS = 65_536


class ValidationError(ValueError):
    """Raised when the static pack violates its frozen contract."""


def _duplicate_rejector(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _resource_check(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES:
            raise ValidationError(f"JSON exceeds {MAX_NODES} values")
        if depth > MAX_DEPTH:
            raise ValidationError(f"JSON nesting exceeds {MAX_DEPTH}")
        if type(current) is str:
            if len(current) > MAX_STRING_CHARS:
                raise ValidationError(
                    f"JSON string exceeds {MAX_STRING_CHARS} characters"
                )
            current.encode("utf-8")
        elif type(current) is dict:
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in current)
        elif type(current) is float and not math.isfinite(current):
            raise ValidationError("non-finite JSON number")


def strict_json_loads(text: str) -> Any:
    if type(text) is not str:
        raise ValidationError("JSON input must be text")
    try:
        encoded = text.encode("utf-8")
    except UnicodeError as exc:
        raise ValidationError("JSON input is not valid UTF-8 text") from exc
    if len(encoded) > MAX_FILE_BYTES:
        raise ValidationError(f"JSON exceeds {MAX_FILE_BYTES} bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_rejector,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValidationError(f"non-finite JSON number: {constant}")
            ),
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError) as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc
    _resource_check(value)
    return value


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError(f"{path} exceeds {MAX_FILE_BYTES} bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValidationError(f"{path} must not contain a UTF-8 BOM")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{path} is not valid UTF-8") from exc


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{path} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Iterable[str], path: str) -> None:
    wanted = set(expected)
    observed = set(value)
    if wanted != observed:
        raise ValidationError(
            f"{path} fields differ; "
            f"missing={sorted(wanted - observed)}, extra={sorted(observed - wanted)}"
        )


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValidationError(message)


def _validate_card() -> None:
    text = _read_text(CARD_PATH)
    _require(text.startswith("---\n"), "README.md must start with YAML metadata")
    try:
        _, metadata, body = text.split("---\n", 2)
    except ValueError as exc:
        raise ValidationError("README.md needs a closed YAML metadata block") from exc
    required_metadata = (
        "license: apache-2.0",
        "language:\n- en",
        "pretty_name: Urusilla External Reproduction Challenge",
        "path: data/challenge.jsonl",
    )
    for item in required_metadata:
        _require(item in metadata, f"README.md metadata is missing {item!r}")
    for item in (
        "Proven general post-decode API-input token saving: **0%**",
        "only **2 of 3** receivers explicitly opted in",
        CAPSULE_URI,
        CAPSULE_DIGEST,
        INTEROP_URI,
        "No package, plugin, model weight, executable grammar, or persistent memory",
        "Private chain-of-thought is neither required nor accepted.",
    ):
        _require(item in body, f"README.md is missing required disclosure: {item!r}")


def _validate_schema() -> None:
    schema = _object(strict_json_loads(_read_text(SCHEMA_PATH)), "schema")
    _require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "schema.json must declare JSON Schema draft 2020-12",
    )
    _require(schema.get("type") == "object", "schema root type must be object")
    required = schema.get("required")
    _require(
        type(required) is list and set(required) == TOP_LEVEL_KEYS,
        "schema.json required root keys must match the record contract",
    )
    properties = _object(schema.get("properties"), "schema.properties")
    _require(
        set(properties) == TOP_LEVEL_KEYS,
        "schema.json properties must match the record contract",
    )


def _validate_protocol(value: Any) -> None:
    protocol = _object(value, "protocol")
    _exact_keys(
        protocol,
        (
            "project",
            "release_tag",
            "language_version",
            "capsule_uri",
            "capsule_sha256",
            "capsule_signature_status",
            "interop_protocol_uri",
            "language_spec_uri",
            "evidence_room_uri",
        ),
        "protocol",
    )
    _require(protocol["project"] == "Urusilla", "protocol.project mismatch")
    _require(protocol["release_tag"] == "v0.1.0-experimental", "release tag mismatch")
    _require(protocol["language_version"] == "0.1.0", "language version mismatch")
    _require(protocol["capsule_uri"] == CAPSULE_URI, "Capsule URI is not pinned")
    _require(SHA256_RE.fullmatch(protocol["capsule_sha256"]) is not None, "invalid Capsule digest")
    _require(protocol["capsule_sha256"] == CAPSULE_REF, "Capsule digest mismatch")
    _require(
        protocol["capsule_signature_status"] == "unsigned-experimental",
        "unsigned Capsule must not be presented as verified",
    )
    _require(protocol["interop_protocol_uri"] == INTEROP_URI, "Interop URI mismatch")
    _require(protocol["language_spec_uri"] == SPEC_URI, "specification URI mismatch")
    _require(
        protocol["evidence_room_uri"]
        == "https://github.com/jaden3824/urusilla/discussions/6",
        "evidence room URI mismatch",
    )


def _validate_known_evidence(value: Any) -> None:
    evidence = _object(value, "known_evidence")
    _exact_keys(
        evidence,
        (
            "general_post_decode_api_input_saving_percent",
            "general_result_scope",
            "general_total_task_tokens_status",
            "same_project_pilot",
        ),
        "known_evidence",
    )
    _require(
        type(evidence["general_post_decode_api_input_saving_percent"]) in {int, float}
        and float(evidence["general_post_decode_api_input_saving_percent"]) == 0.0,
        "general post-decode saving must remain 0%",
    )
    _require(
        evidence["general_total_task_tokens_status"] == "unknown",
        "general total-task tokens must remain unknown",
    )
    pilot = _object(evidence["same_project_pilot"], "known_evidence.same_project_pilot")
    _require(
        pilot.get("classification") == "SAME-PROJECT-ORCHESTRATED",
        "pilot must not be relabeled independent",
    )
    _require(pilot.get("receivers_total") == 3, "pilot receiver count mismatch")
    _require(pilot.get("explicit_session_adoptions") == 2, "pilot adoption count mismatch")
    _require(pilot.get("explicit_adoption_failures") == 1, "pilot failure count mismatch")
    _require(
        pilot.get("valid_typed_message_generators") == 3,
        "pilot valid-message count mismatch",
    )
    _require(pilot.get("matched_raw_json_controls") is False, "pilot had no matched controls")
    _require(pilot.get("efficiency_status") == "not-measured", "pilot efficiency was not measured")


def _validate_task(value: Any) -> None:
    task = _object(value, "challenge.task")
    _exact_keys(
        task,
        (
            "task_id",
            "provenance",
            "license",
            "facts",
            "instruction",
            "observable_success_rubric",
        ),
        "challenge.task",
    )
    _require(task["provenance"] == "project-authored-synthetic", "task provenance mismatch")
    _require(task["license"] == "Apache-2.0", "task license mismatch")
    facts = _object(task["facts"], "challenge.task.facts")
    _exact_keys(facts, ("budget_usd", "network_allowed", "tie_break", "plans"), "challenge.task.facts")
    _require(facts["budget_usd"] == 1.0, "task budget mismatch")
    _require(facts["network_allowed"] is False, "network must be forbidden")
    plans = _array(facts["plans"], "challenge.task.facts.plans")
    _require(len(plans) == 2, "task must contain exactly two plans")
    observed = {plan.get("plan_id"): plan for plan in plans if type(plan) is dict}
    _require(set(observed) == {"single-pass", "double-pass"}, "plan IDs mismatch")
    _require(observed["single-pass"].get("cost_usd") == 0.2, "single-pass cost mismatch")
    _require(observed["double-pass"].get("cost_usd") == 0.7, "double-pass cost mismatch")
    for plan in plans:
        _require(plan.get("network_required") is False, "plans must require no network")
    rubric = _array(task["observable_success_rubric"], "challenge.task.observable_success_rubric")
    _require(len(rubric) == 5, "success rubric must retain all five gates")


def _validate_arms(value: Any) -> None:
    arms = _array(value, "challenge.arms")
    _require(len(arms) == 3, "exactly three matched arms are required")
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(arms):
        arm = _object(raw, f"challenge.arms[{index}]")
        _exact_keys(
            arm,
            ("arm_id", "representation", "model_visible_payload", "constraints"),
            f"challenge.arms[{index}]",
        )
        arm_id = arm["arm_id"]
        _require(type(arm_id) is str and arm_id not in by_id, "arm IDs must be unique strings")
        _require(type(arm["model_visible_payload"]) is str and arm["model_visible_payload"], "arm payload must be nonempty")
        _require(type(arm["constraints"]) is list and arm["constraints"], "arm constraints must be nonempty")
        by_id[arm_id] = arm
    _require(set(by_id) == {"raw", "json", "urusilla"}, "required arm set mismatch")
    ordinary_json = _object(
        strict_json_loads(by_id["json"]["model_visible_payload"]),
        "json arm payload",
    )
    _require(ordinary_json.get("budget_usd") == 1.0, "JSON arm budget mismatch")
    _require(ordinary_json.get("network_allowed") is False, "JSON arm network flag mismatch")
    _require(
        {plan.get("plan_id") for plan in ordinary_json.get("plans", [])}
        == {"single-pass", "double-pass"},
        "JSON arm plan set mismatch",
    )
    urusilla_message = _object(
        strict_json_loads(by_id["urusilla"]["model_visible_payload"]),
        "Urusilla arm payload",
    )
    _require(urusilla_message.get("act") == "REQUEST", "Urusilla arm must be a REQUEST")
    _require(
        urusilla_message.get("schema")
        == "urn:urusilla:hf-challenge:budgeted-plan-selection:1",
        "Urusilla arm schema mismatch",
    )
    body = _object(urusilla_message.get("body"), "Urusilla arm body")
    _require(body.get("kind") == "goal", "Urusilla REQUEST body must be a goal")
    condition = _object(body.get("condition"), "Urusilla arm goal condition")
    _require(condition.get("kind") == "claim", "Urusilla goal condition must be a claim")
    arguments = _array(condition.get("arguments"), "Urusilla arm claim arguments")
    _require(
        {item.get("plan_id") for item in arguments if type(item) is dict and "plan_id" in item}
        == {"single-pass", "double-pass"},
        "Urusilla arm plan set mismatch",
    )
    _require(
        any(
            type(item) is dict
            and item.get("budget_usd") == 1.0
            and item.get("network_allowed") is False
            for item in arguments
        ),
        "Urusilla arm budget/network facts mismatch",
    )
    _require(
        hashlib.sha256(by_id["urusilla"]["model_visible_payload"].encode("utf-8")).hexdigest()
        == "69e7a7c75743dae42a932a89c036b76c1704b61c7e757c14829a7cf48087a6f4",
        "Urusilla arm exact payload digest mismatch",
    )
    _require("Urusilla" not in by_id["raw"]["model_visible_payload"], "raw arm leaked Urusilla induction")
    _require("Urusilla" not in by_id["json"]["model_visible_payload"], "JSON arm leaked Urusilla induction")


def _validate_design(value: Any) -> None:
    design = _object(value, "challenge.study_design")
    _require(design.get("required_arms") == ["raw", "json", "urusilla"], "study arm order contract mismatch")
    _require(design.get("same_receiver_configuration_required") is True, "receiver matching must be required")
    _require(design.get("same_task_facts_required") is True, "task matching must be required")
    _require(design.get("same_success_rubric_required") is True, "rubric matching must be required")
    _require(design.get("report_cold_profile") is True, "cold accounting must be required")
    _require(design.get("complete_failures_and_retries_required") is True, "failure accounting must be required")
    _require(
        set(design.get("allowed_experiment_classes", []))
        == {"EXTERNAL-CONTROLLED", "INDEPENDENT-CROSS-PLAY"},
        "external experiment classes mismatch",
    )


def _validate_result_contract(value: Any) -> None:
    contract = _object(value, "challenge.result_contract")
    _require(
        contract.get("result_schema_version") == "urusilla-hf-external-result/1",
        "result schema version mismatch",
    )
    _require(
        contract.get("token_ledger_categories") == TOKEN_LEDGER_CATEGORIES,
        "token ledger categories changed or reordered",
    )
    required_arm_fields = set(contract.get("per_arm_required_fields", []))
    for field in (
        "arm_id",
        "public_model_inputs",
        "public_model_outputs",
        "task_successes",
        "adoption_decision",
        "fallback_events",
        "parser_or_semantic_failures",
        "repair_turns",
        "token_ledger",
        "count_source",
    ):
        _require(field in required_arm_fields, f"result contract omits {field}")
    _require(
        contract.get("submission_uri")
        == "https://github.com/jaden3824/urusilla/discussions/6",
        "submission URI mismatch",
    )


def _validate_boundaries(value: Any, governance_value: Any) -> None:
    boundary = _object(value, "safety_boundary")
    required_true = {
        "read_only",
        "reversible_session_participation_only",
        "fallback_required",
    }
    required_false = {
        "state_persistence_authorized",
        "permission_expansion_authorized",
        "spending_authorized",
        "external_effects_authorized",
        "executable_installation_required",
        "content_is_authority",
    }
    for field in required_true:
        _require(boundary.get(field) is True, f"safety_boundary.{field} must be true")
    for field in required_false:
        _require(boundary.get(field) is False, f"safety_boundary.{field} must be false")

    governance = _object(governance_value, "data_governance")
    _require(governance.get("record_license") == "Apache-2.0", "record license mismatch")
    _require(
        governance.get("contains_only_project_authored_synthetic_data") is True,
        "pack must contain only project-authored synthetic data",
    )
    for field in (
        "contains_raw_mixed_license_data",
        "contains_private_chain_of_thought",
        "contains_hidden_prompts",
        "contains_personal_data",
        "contains_secrets",
        "contains_executable_payloads",
    ):
        _require(governance.get(field) is False, f"data_governance.{field} must be false")


def _validate_record(record: Any) -> None:
    root = _object(record, "record")
    _exact_keys(root, TOP_LEVEL_KEYS, "record")
    _require(root["schema_version"] == SCHEMA_VERSION, "record schema version mismatch")
    _require(root["record_id"] == RECORD_ID, "record ID mismatch")
    _require(root["record_type"] == "matched-three-arm-challenge", "record type mismatch")
    _validate_protocol(root["protocol"])
    _validate_known_evidence(root["known_evidence"])
    challenge = _object(root["challenge"], "challenge")
    _exact_keys(challenge, ("objective", "task", "arms", "study_design", "result_contract"), "challenge")
    _require(type(challenge["objective"]) is str and challenge["objective"], "challenge objective must be nonempty")
    _validate_task(challenge["task"])
    _validate_arms(challenge["arms"])
    _validate_design(challenge["study_design"])
    _validate_result_contract(challenge["result_contract"])
    _validate_boundaries(root["safety_boundary"], root["data_governance"])


def _validate_jsonl() -> None:
    text = _read_text(DATA_PATH)
    _require(text.endswith("\n"), "challenge.jsonl must end with a newline")
    lines = text.splitlines()
    _require(len(lines) == 1 and bool(lines[0].strip()), "challenge.jsonl must contain exactly one record")
    _validate_record(strict_json_loads(lines[0]))


def _validate_capsule(path: Path) -> None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read Capsule {path}: {exc}") from exc
    observed = hashlib.sha256(raw).hexdigest()
    _require(observed == CAPSULE_DIGEST, f"Capsule digest mismatch: observed {observed}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Capsule is not UTF-8 JSON") from exc
    capsule = _object(strict_json_loads(text), "capsule")
    _require(capsule.get("capsule_type") == "urusilla-grammar-capsule", "Capsule type mismatch")
    _require(capsule.get("capsule_version") == "0.1.0", "Capsule version mismatch")
    _require(capsule.get("release_status") == "experimental-unsigned", "Capsule status mismatch")


def validate(capsule_path: Path | None = None) -> None:
    _validate_card()
    _validate_schema()
    _validate_jsonl()
    if capsule_path is not None:
        _validate_capsule(capsule_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capsule",
        type=Path,
        help="optional local Capsule path whose exact bytes should be hashed",
    )
    args = parser.parse_args(argv)
    try:
        validate(args.capsule)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    checked = "card + schema + 1 JSONL record"
    if args.capsule is not None:
        checked += " + exact local Capsule bytes"
    print(f"PASS: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
