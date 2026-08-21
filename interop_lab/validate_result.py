#!/usr/bin/env python3
"""Dependency-free validator for bounded Urusilla agent-surface results.

This program validates local declarative JSON only. It does not fetch a URL,
contact a model, run submitted code, publish a result, or authorize an effect.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT = Path(__file__).resolve().with_name("result.template.json")
SCHEMA_PATH = Path(__file__).resolve().with_name("result.schema.json")
SCHEMA_VERSION = "urusilla-agent-result/1"
BASELINE_REVISION = "f612ea141e409693b27e93cefef0876eff9542ed"
CAPSULE_SHA256 = (
    "sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
)
TRACKS = {"quick_60s", "quick_10m", "decode", "matched_eval"}
OUTCOMES = {"exact", "mismatch", "counterexample", "ambiguity", "refusal", "null"}
ARM_IDS = {"raw", "json", "urusilla"}
TOKEN_PHASES = (
    "setup",
    "sender",
    "router",
    "receiver",
    "output",
    "reasoning",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
)
KNOWN_ARTIFACT_IDS = {
    "grammar_capsule",
    "action_state_capsule",
    "task_context_example",
    "output_validator_example",
    "evolving_surface_capsule",
    "evolving_surface_contract",
    "decode_challenge",
    "decode_frame",
    "decode_expected",
    "matched_eval_card",
    "matched_eval_record",
    "matched_eval_schema",
    "matched_eval_validator",
}
ROOT_KEYS = {
    "schema_version",
    "result_id",
    "track",
    "baseline_revision",
    "artifact_evidence",
    "participant",
    "outcome",
    "token_accounting",
    "safety_boundary",
    "claim_boundary",
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
MAX_FILE_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_NODES = 50_000
MAX_STRING_CHARS = 65_536
MAX_TOKEN_COUNT = 10**15


class ValidationError(ValueError):
    """Raised when a result violates the bounded submission contract."""


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
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
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


def _load_json_bytes(raw: bytes, source: str) -> Any:
    if type(raw) is not bytes:
        raise ValidationError(f"{source} did not provide bytes")
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError(f"JSON input exceeds {MAX_FILE_BYTES} bytes: {source}")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValidationError(f"{source} must not contain a UTF-8 BOM")
    try:
        return strict_json_loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{source} is not valid UTF-8") from exc


def load_json(path: Path) -> Any:
    if path == Path("-"):
        try:
            raw = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        except OSError as exc:
            raise ValidationError(f"cannot read stdin: {exc}") from exc
        return _load_json_bytes(raw, "stdin")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    return _load_json_bytes(raw, str(path))


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _array(value: Any, path: str, *, maximum: int = 10_000) -> list[Any]:
    if type(value) is not list or len(value) > maximum:
        raise ValidationError(f"{path} must be an array with at most {maximum} items")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Iterable[str], path: str) -> None:
    wanted = set(expected)
    observed = set(value)
    if wanted != observed:
        raise ValidationError(
            f"{path} fields differ; "
            f"missing={sorted(wanted - observed)}, "
            f"extra={sorted(observed - wanted)}"
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _string(value: Any, path: str, *, minimum: int = 0, maximum: int = 4_096) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        raise ValidationError(
            f"{path} must be a string of {minimum}..{maximum} characters"
        )
    return value


def _enum(value: Any, choices: set[str], path: str) -> str:
    if type(value) is not str or value not in choices:
        raise ValidationError(f"{path} must be one of {sorted(choices)}")
    return value


def _nullable_bool(value: Any, path: str) -> bool | None:
    if value is None or type(value) is bool:
        return value
    raise ValidationError(f"{path} must be a boolean or null")


def _nullable_number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float}:
        raise ValidationError(f"{path} must be a finite number or null")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{path} must be finite")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{path} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{path} must be at most {maximum}")
    return number


def _nullable_digest(value: Any, path: str) -> str | None:
    if value is None:
        return None
    text = _string(value, path, minimum=71, maximum=71)
    if SHA256_RE.fullmatch(text) is None:
        raise ValidationError(f"{path} must use sha256:<64-lowercase-hex>")
    return text


def _nullable_https_uri(value: Any, path: str) -> str | None:
    if value is None:
        return None
    text = _string(value, path, minimum=1, maximum=2_048)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValidationError(f"{path} must be an HTTPS URI without credentials")
    return text


def _validate_schema_file() -> None:
    schema = _object(load_json(SCHEMA_PATH), "result.schema.json")
    _require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "result.schema.json must use JSON Schema draft 2020-12",
    )
    _require(schema.get("$id") == "urn:urusilla:agent-result:1", "schema id changed")
    _require(schema.get("type") == "object", "schema root must be an object")
    _require(schema.get("additionalProperties") is False, "schema root must be closed")
    required = schema.get("required")
    _require(
        type(required) is list and set(required) == ROOT_KEYS,
        "schema required root fields differ from the validator",
    )
    properties = _object(schema.get("properties"), "schema.properties")
    _require(set(properties) == ROOT_KEYS, "schema root properties differ from validator")
    arm = _object(_object(schema.get("$defs"), "schema.$defs").get("arm"), "schema.$defs.arm")
    arm_properties = _object(arm.get("properties"), "schema.$defs.arm.properties")
    token_schema = _object(
        _object(arm_properties.get("tokens"), "arm.tokens").get("properties"),
        "arm.tokens.properties",
    )
    _require(
        set(token_schema) == set(TOKEN_PHASES) | {"total"},
        "schema token phases differ from validator",
    )


def _validate_artifact_evidence(value: Any) -> dict[str, Any]:
    evidence = _object(value, "artifact_evidence")
    _exact_keys(
        evidence,
        ("agent_entry_sha256", "capsule_sha256", "verified_artifact_ids"),
        "artifact_evidence",
    )
    _nullable_digest(evidence["agent_entry_sha256"], "artifact_evidence.agent_entry_sha256")
    _require(
        evidence["capsule_sha256"] == CAPSULE_SHA256,
        "artifact_evidence.capsule_sha256 does not match the frozen Capsule",
    )
    identifiers = _array(
        evidence["verified_artifact_ids"],
        "artifact_evidence.verified_artifact_ids",
        maximum=len(KNOWN_ARTIFACT_IDS),
    )
    _require(
        all(
            type(item) is str
            and ARTIFACT_ID_RE.fullmatch(item) is not None
            and item in KNOWN_ARTIFACT_IDS
            for item in identifiers
        ),
        "artifact_evidence.verified_artifact_ids contains an unknown id",
    )
    _require(
        len(identifiers) == len(set(identifiers)),
        "artifact_evidence.verified_artifact_ids contains duplicates",
    )
    return evidence


def _validate_participant(value: Any) -> None:
    participant = _object(value, "participant")
    _exact_keys(
        participant,
        (
            "kind",
            "operator_count",
            "independent_from_project",
            "runtime",
            "prior_urusilla_exposure",
        ),
        "participant",
    )
    _enum(participant["kind"], {"human", "agent", "human+agent"}, "participant.kind")
    operator_count = participant["operator_count"]
    _require(
        type(operator_count) is int and 1 <= operator_count <= 10_000,
        "participant.operator_count must be an integer from 1 to 10000",
    )
    _require(
        type(participant["independent_from_project"]) is bool,
        "participant.independent_from_project must be a boolean",
    )
    _string(participant["runtime"], "participant.runtime", minimum=1, maximum=1_024)
    _enum(
        participant["prior_urusilla_exposure"],
        {"none", "possible", "known", "unknown"},
        "participant.prior_urusilla_exposure",
    )


def _validate_outcome(value: Any) -> str:
    outcome = _object(value, "outcome")
    _exact_keys(outcome, ("kind", "summary", "evidence_uri"), "outcome")
    kind = _enum(outcome["kind"], OUTCOMES, "outcome.kind")
    _string(outcome["summary"], "outcome.summary", minimum=1, maximum=4_096)
    _nullable_https_uri(outcome["evidence_uri"], "outcome.evidence_uri")
    return kind


def _nullable_token(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= MAX_TOKEN_COUNT:
        raise ValidationError(f"{path} must be a nonnegative integer or null")
    return value


def _validate_arm(value: Any, index: int) -> tuple[str, bool, dict[str, Any]]:
    label = f"token_accounting.arms[{index}]"
    arm = _object(value, label)
    _exact_keys(
        arm,
        (
            "arm_id",
            "safe_completion",
            "task_success",
            "parse_valid",
            "semantic_fidelity",
            "failure_reason",
            "tokens",
        ),
        label,
    )
    arm_id = _enum(arm["arm_id"], ARM_IDS, f"{label}.arm_id")
    outcome_values = (
        _nullable_bool(arm[field], f"{label}.{field}")
        for field in (
            "safe_completion",
            "task_success",
            "parse_valid",
            "semantic_fidelity",
        )
    )
    outcomes_known = all(value is not None for value in outcome_values)
    failure_reason = arm["failure_reason"]
    if failure_reason is not None:
        _string(failure_reason, f"{label}.failure_reason", minimum=1, maximum=2_048)
    if any(arm[field] is False for field in ("safe_completion", "task_success")):
        _require(
            failure_reason is not None,
            f"{label}.failure_reason is required for a failed arm",
        )
    tokens = _object(arm["tokens"], f"{label}.tokens")
    _exact_keys(tokens, set(TOKEN_PHASES) | {"total"}, f"{label}.tokens")
    phase_values = [
        _nullable_token(tokens[phase], f"{label}.tokens.{phase}")
        for phase in TOKEN_PHASES
    ]
    total = _nullable_token(tokens["total"], f"{label}.tokens.total")
    tokens_known = all(value is not None for value in phase_values)
    if tokens_known:
        expected_total = sum(value for value in phase_values if value is not None)
        _require(total == expected_total, f"{label}.tokens.total does not reconcile")
    else:
        _require(
            total is None,
            f"{label}.tokens.total must be null when any token phase is unknown",
        )
    return arm_id, outcomes_known and tokens_known, arm


def _validate_token_accounting(value: Any, track: str) -> tuple[str, dict[str, Any]]:
    accounting = _object(value, "token_accounting")
    _exact_keys(accounting, ("status", "arms"), "token_accounting")
    status = _enum(
        accounting["status"],
        {"complete", "incomplete", "not-measured"},
        "token_accounting.status",
    )
    arms = _array(accounting["arms"], "token_accounting.arms", maximum=3)
    if track == "matched_eval":
        _require(
            len(arms) == 3,
            "matched_eval requires raw, json, and urusilla arms even when incomplete",
        )
    else:
        _require(
            arms == [] and status == "not-measured",
            "quick and decode tracks use an empty not-measured token ledger",
        )
    validated = [_validate_arm(arm, index) for index, arm in enumerate(arms)]
    arm_ids = [item[0] for item in validated]
    _require(len(arm_ids) == len(set(arm_ids)), "token_accounting has duplicate arms")
    if track == "matched_eval":
        _require(set(arm_ids) == ARM_IDS, "matched_eval arms must be raw, json, and urusilla")
    all_known = bool(validated) and all(item[1] for item in validated)
    any_known = any(
        any(
            arm[field] is not None
            for field in (
                "safe_completion",
                "task_success",
                "parse_valid",
                "semantic_fidelity",
            )
        )
        or any(arm["tokens"][field] is not None for field in (*TOKEN_PHASES, "total"))
        for _, _, arm in validated
    )
    if status == "complete":
        _require(all_known, "complete token accounting cannot contain null values")
    elif status == "incomplete":
        _require(
            track == "matched_eval" and any_known and not all_known,
            "incomplete accounting must preserve at least one known and one unknown field",
        )
    elif track == "matched_eval":
        _require(not any_known, "not-measured accounting must keep every measurement null")
    return status, {arm_id: arm for arm_id, _, arm in validated}


def _validate_safety(value: Any) -> None:
    safety = _object(value, "safety_boundary")
    expected = {
        "read_only": True,
        "state_persistence_authorized": False,
        "permission_expansion_authorized": False,
        "spending_authorized": False,
        "external_effects_authorized": False,
        "untrusted_executable_content_run": False,
    }
    _exact_keys(safety, expected, "safety_boundary")
    _require(
        safety == expected,
        "safety_boundary grants an effect or records unsafe executable handling",
    )


def _validate_claim(
    value: Any,
    *,
    track: str,
    outcome: str,
    accounting_status: str,
    arms: Mapping[str, Mapping[str, Any]],
    artifact_evidence: Mapping[str, Any],
) -> bool:
    claim = _object(value, "claim_boundary")
    _exact_keys(
        claim,
        (
            "bounded_efficiency_improvement",
            "token_saving_lcb_percent",
            "task_success_difference_lcb_percentage_points",
            "parse_validity_rate",
            "semantic_fidelity_rate",
            "safety_passed",
            "changes_general_zero_percent",
            "direct_agent_dialogue_evidence",
            "external_adoption_claim",
        ),
        "claim_boundary",
    )
    made = claim["bounded_efficiency_improvement"]
    _require(type(made) is bool, "bounded_efficiency_improvement must be a boolean")
    saving_lcb = _nullable_number(
        claim["token_saving_lcb_percent"],
        "claim_boundary.token_saving_lcb_percent",
    )
    success_lcb = _nullable_number(
        claim["task_success_difference_lcb_percentage_points"],
        "claim_boundary.task_success_difference_lcb_percentage_points",
    )
    parse_rate = _nullable_number(
        claim["parse_validity_rate"],
        "claim_boundary.parse_validity_rate",
        minimum=0.0,
        maximum=1.0,
    )
    fidelity_rate = _nullable_number(
        claim["semantic_fidelity_rate"],
        "claim_boundary.semantic_fidelity_rate",
        minimum=0.0,
        maximum=1.0,
    )
    safety_passed = _nullable_bool(
        claim["safety_passed"], "claim_boundary.safety_passed"
    )
    for field in (
        "changes_general_zero_percent",
        "direct_agent_dialogue_evidence",
        "external_adoption_claim",
    ):
        _require(
            claim[field] is False,
            f"claim_boundary.{field} must remain false for this repository surface",
        )
    if not made:
        return False

    _require(track == "matched_eval", "an efficiency claim requires matched_eval")
    _require(outcome == "exact", "an efficiency claim requires an exact outcome")
    _require(
        artifact_evidence["agent_entry_sha256"] is not None,
        "an efficiency claim requires a verified agent-entry digest",
    )
    required_artifacts = {
        "grammar_capsule",
        "matched_eval_card",
        "matched_eval_record",
        "matched_eval_schema",
        "matched_eval_validator",
    }
    _require(
        required_artifacts <= set(artifact_evidence["verified_artifact_ids"]),
        "an efficiency claim requires every matched-eval artifact digest",
    )
    _require(
        accounting_status == "complete",
        "an efficiency claim requires complete token accounting",
    )
    _require(set(arms) == ARM_IDS, "an efficiency claim requires all three arms")
    for arm_id, arm in arms.items():
        for field in (
            "safe_completion",
            "task_success",
            "parse_valid",
            "semantic_fidelity",
        ):
            _require(
                arm[field] is True,
                f"an efficiency claim requires {arm_id}.{field} to pass",
            )
    _require(
        saving_lcb is not None and saving_lcb >= 20.0,
        "an efficiency claim requires a token-saving LCB of at least 20%",
    )
    _require(
        success_lcb is not None and success_lcb >= -1.0,
        "an efficiency claim requires a task-success LCB of at least -1 percentage point",
    )
    _require(
        parse_rate is not None and parse_rate >= 0.99,
        "an efficiency claim requires parse validity of at least 99%",
    )
    _require(
        fidelity_rate is not None and fidelity_rate >= 0.95,
        "an efficiency claim requires semantic fidelity of at least 95%",
    )
    _require(safety_passed is True, "an efficiency claim requires the safety gate")
    baseline_total = min(arms["raw"]["tokens"]["total"], arms["json"]["tokens"]["total"])
    candidate_total = arms["urusilla"]["tokens"]["total"]
    _require(baseline_total > 0, "best baseline total must be positive")
    observed_saving = (baseline_total - candidate_total) * 100.0 / baseline_total
    _require(
        observed_saving >= 20.0,
        "an efficiency claim requires at least 20% observed saving against the best baseline",
    )
    return True


def validate_result(value: Any) -> dict[str, Any]:
    _validate_schema_file()
    result = _object(value, "result")
    _exact_keys(result, ROOT_KEYS, "result")
    _require(result["schema_version"] == SCHEMA_VERSION, "schema_version changed")
    result_id = _string(result["result_id"], "result_id", minimum=1, maximum=128)
    _require(ID_RE.fullmatch(result_id) is not None, "result_id has an invalid format")
    track = _enum(result["track"], TRACKS, "track")
    _require(
        result["baseline_revision"] == BASELINE_REVISION,
        "baseline_revision must be the frozen full commit",
    )
    artifact_evidence = _validate_artifact_evidence(result["artifact_evidence"])
    _validate_participant(result["participant"])
    outcome = _validate_outcome(result["outcome"])
    accounting_status, arms = _validate_token_accounting(result["token_accounting"], track)
    _validate_safety(result["safety_boundary"])
    bounded_claim = _validate_claim(
        result["claim_boundary"],
        track=track,
        outcome=outcome,
        accounting_status=accounting_status,
        arms=arms,
        artifact_evidence=artifact_evidence,
    )
    if outcome != "exact":
        _require(
            not bounded_claim,
            "negative, ambiguous, refusal, and null outcomes cannot make a positive claim",
        )
    return {
        "valid": True,
        "network_used": False,
        "result_id": result_id,
        "track": track,
        "outcome": outcome,
        "negative_or_null_evidence_accepted": outcome != "exact",
        "token_accounting_status": accounting_status,
        "bounded_efficiency_improvement": bounded_claim,
        "changes_general_zero_percent": False,
        "direct_agent_dialogue_evidence": False,
        "external_adoption_claim": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a bounded Urusilla result without network access."
    )
    parser.add_argument(
        "result",
        nargs="?",
        type=Path,
        default=DEFAULT_RESULT,
        help="path to a result JSON file, or - to read bounded UTF-8 JSON from stdin",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_result(load_json(args.result))
    except ValidationError as exc:
        if args.json:
            print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            f"valid: {report['track']} / {report['outcome']}; "
            f"accounting={report['token_accounting_status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
