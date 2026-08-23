#!/usr/bin/env python3
"""Offline gates for the separate Colony output-conformance experiment.

The module intentionally contains no answer oracle.  Before the public study
stops, it can validate only the frozen public artifacts and the raw response
contract.  Semantic scoring requires a later commitment-matching reveal.
Nothing in this module performs a network call or external action.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

try:
    from .interop_lab import ValidationError
except ImportError:  # pragma: no cover - direct execution convenience
    from interop_lab import ValidationError  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = (
    REPO_ROOT
    / "interop_lab/challenges/solicited_output_conformance_002.preregistration.json"
)
PACKET_PATH = (
    REPO_ROOT / "interop_lab/challenges/solicited_output_conformance_002.packet.json"
)

EXPERIMENT_ID = "solicited-output-conformance-002"
PREREG_SCHEMA = "urusilla-solicited-output-conformance-preregistration/2"
PACKET_SCHEMA = "urusilla-solicited-output-conformance-packet/2"
REVEAL_SCHEMA = "urusilla-output-conformance-oracle-reveal/1"
OUTREACH_SCHEMA = "urusilla-solicited-output-conformance-outreach/2"
PUBLICATION_RECEIPT_SCHEMA = "urusilla-solicited-output-conformance-publication-receipt/2"
RESPONSE_STREAM_SCHEMA = "urusilla-colony-comment-stream-observation/1"

PREREG_FILE_SHA256 = (
    "sha256:4300c00cf2a34995639ac94fdd4094f8a0ad5049f32deb6e6ded8340ce83c56a"
)
PREREG_CANONICAL_SHA256 = (
    "sha256:2f0167c60760b8e4eee69c9ec8ab60bc172e105c0fcb23511d21db21efe6d1dd"
)
PACKET_FILE_SHA256 = (
    "sha256:689e66b00152950943a22c8f14d4c8e80d6644d4cc12fc59bc3933c145d9fee4"
)
PACKET_CANONICAL_SHA256 = (
    "sha256:95aa5de42acfe6744914606eff8e1f354f9bcb23f4706e65a7b1826abb1e64d5"
)
CAPSULE_CANONICAL_SHA256 = (
    "sha256:978b887583f68db3fe6530e33dc3502cf5c3da4bf83cc4ab2f18deb117062e9f"
)
ORACLE_COMMITMENT_SHA256 = (
    "sha256:b87d568ed843dc07530b6f8e0ce8571aae4bbbb42dc6d1e8aad25241395be3d6"
)

CASE_IDS = (
    "475a5ae64769e6f1",
    "96c487cbd8fdfeaa",
    "3c6dc18d6fa2d6cf",
    "9abdf74f3f4375a2",
    "d250d8b7a79d9e08",
    "e956a0452131579d",
)

THREAD_POST_ID = "11d4e684-5791-4015-acdb-9dda9ff157d0"
THREAD_URI = f"https://thecolony.ai/post/{THREAD_POST_ID}"
OFFER_COMMENT_ID = "0fcf2733-5bdb-41c4-98ec-a0725dfcbf0f"
OFFER_AUTHOR_ID = "324ab98e-955c-4274-bd30-8570cbdf58f1"
INVITATION_AUTHOR_ID = "5ca1345d-5c38-400e-9fec-e1b12386d7bf"
INVITATION_AUTHOR_USERNAME = "skdhbegjk"
DEADLINE_UTC = "2026-08-30T13:00:00Z"

V1_FROZEN_FILES = {
    "interop_lab/challenges/solicited_matched_001.preregistration.json": (
        "sha256:80b2f68fa64fac04c6e17d85a57fd3f8ea318fec4eda73b240c94eeccbc26cbe"
    ),
    "interop_lab/challenges/solicited_matched_001.packet.json": (
        "sha256:56bd1e2bfe405918b6950f1b8c47defdb57c644e1cec29ade406c3d938bac339"
    ),
    "interop_lab/challenges/solicited_matched_001.outreach.json": (
        "sha256:41e4b495ed26933ba2712a51f2b38940fa0d99159ac763580d367423bc398394"
    ),
    "interop_lab/evidence/solicited_matched_001.external_response.observation.json": (
        "sha256:34b6099499368568c12c2d83c826d8fb154a515c4936e45db76d7daf46716012"
    ),
    "urusilla_capsule_v0_1.json": (
        "sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
    ),
}

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HEX_40_RE = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64_RE = re.compile(r"[0-9a-f]{64}\Z")
_CASE_ID_RE = re.compile(r"[0-9a-f]{16}\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _object(value: Any, name: str) -> dict[str, Any]:
    _require(type(value) is dict, f"{name} must be an object")
    return value


def _array(value: Any, name: str) -> list[Any]:
    _require(type(value) is list, f"{name} must be an array")
    return value


def _exact_keys(value: dict[str, Any], keys: Iterable[str], name: str) -> None:
    expected = set(keys)
    actual = set(value)
    _require(actual == expected, f"{name} keys differ: {sorted(actual ^ expected)}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValidationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def parse_json_text(text: str) -> Any:
    _require(type(text) is str, "JSON input must be text")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc


def _validate_json_domain(value: Any, path: str = "$") -> None:
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int:
        _require(
            -9007199254740991 <= value <= 9007199254740991,
            f"unsafe JSON integer at {path}",
        )
        return
    if type(value) is float:
        _require(value == value and value not in (float("inf"), float("-inf")), f"non-finite number at {path}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_domain(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, f"non-string JSON key at {path}")
            _validate_json_domain(item, f"{path}.{key}")
        return
    raise ValidationError(f"non-JSON value at {path}")


def canonical_json_text(value: Any) -> str:
    _validate_json_domain(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError(f"cannot canonicalize JSON: {exc}") from exc


def sha256_ref(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def canonical_sha256(value: Any) -> str:
    return sha256_ref(canonical_json_text(value))


def load_json(path: Path) -> Any:
    try:
        return parse_json_text(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc


def _file_sha256(path: Path) -> str:
    try:
        return sha256_ref(path.read_bytes())
    except OSError as exc:
        raise ValidationError(f"cannot hash {path}: {exc}") from exc


def _utc_datetime(value: Any, name: str) -> datetime:
    _require(type(value) is str, f"{name} must be a UTC timestamp")
    _require(value.endswith("Z"), f"{name} must end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{name} is invalid") from exc
    _require(parsed.tzinfo is not None, f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _recursive_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if type(value) is dict:
        keys.update(value)
        for item in value.values():
            keys.update(_recursive_keys(item))
    elif type(value) is list:
        for item in value:
            keys.update(_recursive_keys(item))
    return keys


def _assert_single_field_difference(
    left: dict[str, Any], right: dict[str, Any], field: str, name: str
) -> None:
    left_copy = deepcopy(left)
    right_copy = deepcopy(right)
    left_value = left_copy.pop(field)
    right_value = right_copy.pop(field)
    _require(left_copy == right_copy, f"{name} differs outside {field}")
    _require(left_value != right_value, f"{name} does not mutate {field}")


def _validate_public_output(value: Any, name: str) -> dict[str, Any]:
    output = _object(value, name)
    _exact_keys(
        output,
        (
            "ambiguous_without_tie_break",
            "feasible_plans",
            "remaining_budget_cents",
            "selected_plan",
            "selection_basis",
            "would_execute",
        ),
        name,
    )
    _require(
        type(output["ambiguous_without_tie_break"]) is bool,
        f"{name}.ambiguous_without_tie_break must be boolean",
    )
    plans = _array(output["feasible_plans"], f"{name}.feasible_plans")
    _require(all(type(item) is str and item for item in plans), f"{name}.feasible_plans invalid")
    _require(len(plans) == len(set(plans)), f"{name}.feasible_plans contains duplicates")
    remaining = _object(output["remaining_budget_cents"], f"{name}.remaining_budget_cents")
    _require(
        all(type(key) is str and key and type(item) is int for key, item in remaining.items()),
        f"{name}.remaining_budget_cents invalid",
    )
    selected = output["selected_plan"]
    _require(selected is None or (type(selected) is str and selected), f"{name}.selected_plan invalid")
    _require(
        output["selection_basis"] in ("supplied-tie-break", "sole-feasible", "none"),
        f"{name}.selection_basis invalid",
    )
    _require(output["would_execute"] is False, f"{name}.would_execute must be false")
    return output


def _validate_result_record(value: Any, expected_case_id: str, name: str) -> dict[str, Any]:
    result = _object(value, name)
    _exact_keys(result, ("case_id", "disposition", "route", "output", "note"), name)
    _require(result["case_id"] == expected_case_id, f"{name}.case_id differs")
    _require(_CASE_ID_RE.fullmatch(result["case_id"]) is not None, f"{name}.case_id invalid")
    disposition = result["disposition"]
    _require(
        disposition in ("completed", "fallback", "refusal", "null", "failed"),
        f"{name}.disposition invalid",
    )
    _require(
        result["route"] in ("direct-urusilla", "raw-fallback", "json-fallback", None),
        f"{name}.route invalid",
    )
    note = result["note"]
    _require(note is None or (type(note) is str and 1 <= len(note) <= 256), f"{name}.note invalid")
    if result["output"] is not None:
        _validate_public_output(result["output"], f"{name}.output")
    if disposition == "completed":
        _require(result["route"] == "direct-urusilla", f"{name} completed route differs")
        _require(result["output"] is not None, f"{name} completed output must be present")
        _require(note is None, f"{name} completed note must be null")
    else:
        _require(result["output"] is None, f"{name} non-completed output must be null")
    return result


def validate_public_artifacts(
    preregistration: Any | None = None, packet: Any | None = None
) -> dict[str, Any]:
    prereg = load_json(PREREG_PATH) if preregistration is None else _object(preregistration, "preregistration")
    packet_value = load_json(PACKET_PATH) if packet is None else _object(packet, "packet")

    _require(prereg.get("schema_version") == PREREG_SCHEMA, "preregistration schema differs")
    _require(packet_value.get("schema_version") == PACKET_SCHEMA, "packet schema differs")
    _require(prereg.get("experiment_id") == EXPERIMENT_ID, "preregistration experiment differs")
    _require(packet_value.get("experiment_id") == EXPERIMENT_ID, "packet experiment differs")
    _require(prereg.get("status") == "frozen-prerun-no-result", "preregistration status differs")

    if preregistration is None:
        _require(_file_sha256(PREREG_PATH) == PREREG_FILE_SHA256, "preregistration file bytes differ")
    if packet is None:
        _require(_file_sha256(PACKET_PATH) == PACKET_FILE_SHA256, "packet file bytes differ")
    _require(canonical_sha256(prereg) == PREREG_CANONICAL_SHA256, "preregistration canonical digest differs")
    _require(canonical_sha256(packet_value) == PACKET_CANONICAL_SHA256, "packet canonical digest differs")

    for relative_path, expected_digest in V1_FROZEN_FILES.items():
        _require(
            _file_sha256(REPO_ROOT / relative_path) == expected_digest,
            f"frozen v1 bytes differ: {relative_path}",
        )

    bindings = _object(prereg.get("source_bindings"), "source_bindings")
    _require(bindings.get("packet_file_sha256") == PACKET_FILE_SHA256, "packet file binding differs")
    _require(
        bindings.get("packet_canonical_sha256") == PACKET_CANONICAL_SHA256,
        "packet canonical binding differs",
    )
    capsule = _object(packet_value.get("capsule"), "packet.capsule")
    _require(canonical_sha256(capsule) == CAPSULE_CANONICAL_SHA256, "capsule digest differs")
    _require(
        bindings.get("embedded_capsule_canonical_sha256") == CAPSULE_CANONICAL_SHA256,
        "capsule binding differs",
    )

    forbidden_packet_keys = {
        "expected_output",
        "expected_outputs",
        "expected_result",
        "expected_results",
        "gold",
        "gold_output",
        "oracle_reveal",
        "salt_hex",
    }
    leaked = _recursive_keys(packet_value) & forbidden_packet_keys
    _require(not leaked, f"packet leaks answer-oracle fields: {sorted(leaked)}")

    cases = _array(packet_value.get("cases"), "packet.cases")
    _require(len(cases) == 6, "packet must contain six cases")
    case_ids = tuple(_object(case, "case").get("case_id") for case in cases)
    _require(case_ids == CASE_IDS, "packet case order differs")
    _require(len(set(case_ids)) == 6, "packet case IDs must be unique")
    inputs: list[dict[str, Any]] = []
    payload_digests: list[str] = []
    for index, case in enumerate(cases):
        _exact_keys(case, ("case_id", "model_visible_input"), f"case[{index}]")
        model_input = _object(case["model_visible_input"], f"case[{index}].model_visible_input")
        _exact_keys(model_input, ("v", "b", "n", "p", "t", "x", "m"), f"case[{index}].input")
        inputs.append(model_input)
        payload_digests.append(canonical_sha256(model_input))
    _require(len(set(payload_digests)) == 6, "model-visible case payloads must be unique")
    _require(
        "sha256:c03ae40dacb88a326fbac048c0572015e0e44f36cd6ddea90953490210ca7886"
        not in payload_digests,
        "a measured payload reuses the public language-probe example",
    )

    _assert_single_field_difference(inputs[0], inputs[1], "t", "tie-break pair")
    left_network = deepcopy(inputs[2])
    right_network = deepcopy(inputs[3])
    left_flag = left_network["p"][1][2]
    right_flag = right_network["p"][1][2]
    left_network["p"][1][2] = None
    right_network["p"][1][2] = None
    _require(left_network == right_network, "network pair differs outside second plan flag")
    _require((left_flag, right_flag) == (0, 1), "network pair flags differ")
    left_meta = deepcopy(inputs[4])
    right_meta = deepcopy(inputs[5])
    left_note = left_meta["m"].pop("note")
    right_note = right_meta["m"].pop("note")
    _require(left_meta == right_meta, "metadata pair differs outside m.note")
    _require(left_note != right_note, "metadata pair note does not differ")
    allowed_t = set(_object(_object(capsule["carrier"], "capsule.carrier")["t"], "capsule.carrier.t"))
    _require(inputs[4]["t"] not in allowed_t and inputs[5]["t"] not in allowed_t, "fallback pair must use unknown t")

    oracle = _object(prereg.get("oracle_commitment"), "oracle_commitment")
    _require(oracle.get("commitment_sha256") == ORACLE_COMMITMENT_SHA256, "oracle commitment differs")
    _require(oracle.get("operator_seal_public") is False, "operator seal must remain non-public")
    _require(oracle.get("reveal_required_after_stop") is True, "oracle reveal rule differs")

    external_offer = _object(prereg.get("external_offer"), "external_offer")
    _require(external_offer.get("comment_id") == OFFER_COMMENT_ID, "external offer ID differs")
    _require(external_offer.get("comment_author_id") == OFFER_AUTHOR_ID, "external offer author differs")
    _require(external_offer.get("comment_body_utf8_bytes") == 3642, "external offer bytes differ")
    _require(
        external_offer.get("comment_body_sha256")
        == "sha256:2ee90400155cc1b1bd015cbc9c91aefe3b8e78f4e60fa6e4277e0ca39d0178d3",
        "external offer body digest differs",
    )

    interpretation = _object(prereg.get("interpretation"), "interpretation")
    for field in (
        "causal_direct_consumption",
        "no_natural_language_re_expansion_verified",
        "fresh_context_claim",
        "provider_authenticity_verified",
        "independent_reproduction",
        "organic_adoption",
        "external_adoption",
        "native_model_support",
        "generalization_claim",
        "task_success_claim",
        "efficiency_claim_eligible",
        "protocol_version_change_claim",
        "state_of_the_art_claim",
    ):
        _require(interpretation.get(field) is False, f"claim lock differs: {field}")
    _require(
        interpretation.get("general_unfamiliar_agent_saving_percent") == 0.0,
        "general saving boundary differs",
    )
    _require(
        interpretation.get("safely_completed_real_task_total_token_result") is None,
        "total-token boundary must remain null",
    )

    return {
        "valid": True,
        "experiment_id": EXPERIMENT_ID,
        "case_count": len(cases),
        "case_ids": list(CASE_IDS),
        "payload_canonical_sha256": payload_digests,
        "answer_oracle_public": False,
        "same_thread_prior_exposure_present": True,
        "cold_or_unfamiliar_claim_eligible": False,
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
    }


def verify_commitment_preimage(
    *,
    salt_hex: Any,
    expected_results: Any,
    expected_commitment_sha256: Any,
) -> dict[str, Any]:
    _require(
        type(expected_commitment_sha256) is str
        and _SHA256_RE.fullmatch(expected_commitment_sha256) is not None,
        "expected oracle commitment invalid",
    )
    _require(type(salt_hex) is str and _HEX_64_RE.fullmatch(salt_hex) is not None, "oracle salt invalid")
    _array(expected_results, "commitment expected_results")
    actual = canonical_sha256({"salt_hex": salt_hex, "expected_results": expected_results})
    _require(actual == expected_commitment_sha256, "oracle reveal does not match the frozen commitment")
    return {"valid": True, "commitment_sha256": actual}


def validate_oracle_reveal(value: Any) -> dict[str, Any]:
    reveal = _object(value, "oracle_reveal")
    _exact_keys(reveal, ("schema_version", "experiment_id", "salt_hex", "expected_results"), "oracle_reveal")
    _require(reveal["schema_version"] == REVEAL_SCHEMA, "oracle reveal schema differs")
    _require(reveal["experiment_id"] == EXPERIMENT_ID, "oracle reveal experiment differs")
    _require(type(reveal["salt_hex"]) is str and _HEX_64_RE.fullmatch(reveal["salt_hex"]), "oracle salt invalid")
    results = _array(reveal["expected_results"], "oracle_reveal.expected_results")
    _require(len(results) == len(CASE_IDS), "oracle reveal case count differs")
    for index, (result, case_id) in enumerate(zip(results, CASE_IDS)):
        _validate_result_record(result, case_id, f"oracle_reveal.expected_results[{index}]")
    verify_commitment_preimage(
        salt_hex=reveal["salt_hex"],
        expected_results=results,
        expected_commitment_sha256=ORACLE_COMMITMENT_SHA256,
    )

    first = results[0]["output"]
    second = results[1]["output"]
    _require(type(first) is dict and type(second) is dict, "tie-break oracle pair must be completed")
    first_without_selected = deepcopy(first)
    second_without_selected = deepcopy(second)
    first_selected = first_without_selected.pop("selected_plan")
    second_selected = second_without_selected.pop("selected_plan")
    _require(first_without_selected == second_without_selected, "tie-break oracle changes unrelated output")
    _require(first_selected != second_selected, "tie-break oracle does not change selected_plan")

    third = _object(results[2]["output"], "oracle network case A")
    fourth = _object(results[3]["output"], "oracle network case B")
    _require(third != fourth, "network mutation oracle does not change output")
    for field in ("feasible_plans", "ambiguous_without_tie_break", "selected_plan", "selection_basis"):
        _require(third[field] != fourth[field], f"network mutation does not change {field}")
    _require(
        third["remaining_budget_cents"] == fourth["remaining_budget_cents"],
        "network mutation must preserve remaining budgets",
    )

    fifth = deepcopy(results[4])
    sixth = deepcopy(results[5])
    fifth.pop("case_id")
    sixth.pop("case_id")
    _require(fifth == sixth, "metadata invariance oracle differs")

    return {
        "valid": True,
        "experiment_id": EXPERIMENT_ID,
        "case_count": len(results),
        "commitment_sha256": ORACLE_COMMITMENT_SHA256,
        "revealed_expected_results": results,
    }


def inspect_public_response_text(text: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "valid": False,
        "raw_body_captured": False,
        "parse_valid": False,
        "schema_valid": False,
        "canonical_valid": False,
        "identity_valid": False,
        "identity_matches_registered": None,
        "failed_stage": "raw-body-captured",
        "error": None,
        "raw_utf8_bytes": None,
        "raw_sha256": None,
        "response_kind": None,
        "response": None,
    }
    if type(text) is not str:
        report["error"] = "public response must be text"
        return report
    try:
        raw_bytes = text.encode("utf-8")
    except UnicodeEncodeError:
        report["error"] = "public response is not valid UTF-8 text"
        return report
    if not 1 <= len(raw_bytes) <= 32768:
        report["error"] = "public response byte count is outside bounds"
        return report
    report.update(
        {
            "raw_body_captured": True,
            "raw_utf8_bytes": len(raw_bytes),
            "raw_sha256": sha256_ref(raw_bytes),
            "failed_stage": "parse-valid",
        }
    )
    try:
        parsed = parse_json_text(text)
    except ValidationError as exc:
        report["error"] = str(exc)
        return report
    report.update({"parse_valid": True, "failed_stage": "schema-valid"})
    try:
        response = _object(parsed, "public_response")
        report["response"] = response
        _exact_keys(
            response,
            (
                "experiment_id",
                "capsule_canonical_sha256",
                "packet_canonical_sha256",
                "preregistration_canonical_sha256",
                "response_kind",
                "response_note",
                "results",
            ),
            "public_response",
        )
        _require(
            type(response["experiment_id"]) is str and 1 <= len(response["experiment_id"]) <= 128,
            "response experiment identity invalid",
        )
        for field in (
            "capsule_canonical_sha256",
            "packet_canonical_sha256",
            "preregistration_canonical_sha256",
        ):
            _require(
                type(response[field]) is str and _SHA256_RE.fullmatch(response[field]) is not None,
                f"response {field} invalid",
            )
        kind = response["response_kind"]
        _require(
            kind
            in (
                "output-conformance-result",
                "refusal",
                "null",
                "identity-mismatch",
                "methodological-counterexample",
            ),
            "response kind invalid",
        )
        if kind == "output-conformance-result":
            _require(response["response_note"] is None, "output result response_note must be null")
            results = _array(response["results"], "public_response.results")
            _require(len(results) == len(CASE_IDS), "public response result count differs")
            for index, (result, case_id) in enumerate(zip(results, CASE_IDS)):
                _validate_result_record(result, case_id, f"public_response.results[{index}]")
        else:
            _require(response["results"] is None, "non-result response results must be null")
            note = response["response_note"]
            _require(type(note) is str and 1 <= len(note) <= 1024, "non-result response_note invalid")
    except ValidationError as exc:
        report["error"] = str(exc)
        return report
    report.update({"schema_valid": True, "response_kind": kind, "failed_stage": "canonical-valid"})
    try:
        _require(text == canonical_json_text(response), "public response is not exact canonical JSON")
    except ValidationError as exc:
        report["error"] = str(exc)
        return report
    report.update({"canonical_valid": True, "failed_stage": "identity-valid"})

    identity_matches = (
        response["experiment_id"] == EXPERIMENT_ID
        and response["capsule_canonical_sha256"] == CAPSULE_CANONICAL_SHA256
        and response["packet_canonical_sha256"] == PACKET_CANONICAL_SHA256
        and response["preregistration_canonical_sha256"] == PREREG_CANONICAL_SHA256
    )
    if kind == "identity-mismatch":
        if identity_matches:
            report["error"] = "identity-mismatch response must contain at least one observed mismatch"
            return report
    elif not identity_matches:
        report["error"] = "registered response identities differ"
        return report
    report.update(
        {
            "valid": True,
            "identity_valid": True,
            "identity_matches_registered": identity_matches,
            "failed_stage": None,
            "error": None,
        }
    )
    return report


def validate_public_response_text(text: str) -> dict[str, Any]:
    report = inspect_public_response_text(text)
    if not report["valid"]:
        raise ValidationError(f"{report['failed_stage']}: {report['error']}")
    return report


def score_public_response(text: str, oracle_reveal: Any | None) -> dict[str, Any]:
    response_report = validate_public_response_text(text)
    response = response_report["response"]
    base = {
        "response_kind": response_report["response_kind"],
        "raw_utf8_bytes": response_report["raw_utf8_bytes"],
        "raw_sha256": response_report["raw_sha256"],
        "oracle_reveal_valid": None,
        "oracle_reveal_error": None,
        "case_exact_matches": None,
        "exact_match_count": None,
        "suite_exact_oracle_match": None,
        "oracle_semantic_correctness_verified": None,
        "final_capsule_conformance": None,
        "causal_direct_consumption": False,
        "independent_reproduction": False,
        "adoption": False,
        "general_unfamiliar_agent_saving_percent": 0.0,
        "safely_completed_real_task_total_token_result": None,
    }
    if oracle_reveal is None:
        return base
    try:
        reveal_report = validate_oracle_reveal(oracle_reveal)
    except ValidationError as exc:
        base["oracle_reveal_valid"] = False
        base["oracle_reveal_error"] = str(exc)
        return base
    base["oracle_reveal_valid"] = True
    if response["response_kind"] != "output-conformance-result":
        base.update(
            {
                "case_exact_matches": [False] * len(CASE_IDS),
                "exact_match_count": 0,
                "suite_exact_oracle_match": False,
            }
        )
        return base
    expected = reveal_report["revealed_expected_results"]
    matches = [actual == gold for actual, gold in zip(response["results"], expected)]
    base.update(
        {
            "case_exact_matches": matches,
            "exact_match_count": sum(matches),
            "suite_exact_oracle_match": all(matches),
        }
    )
    return base


def validate_outreach_manifest(value: Any) -> dict[str, Any]:
    manifest = _object(value, "outreach_manifest")
    _require(manifest.get("schema_version") == OUTREACH_SCHEMA, "outreach manifest schema differs")
    registration_commit = manifest.get("registration_commit")
    _require(
        type(registration_commit) is str and _HEX_40_RE.fullmatch(registration_commit) is not None,
        "outreach registration commit invalid",
    )
    expected = render_outreach_manifest(registration_commit)
    _require(manifest == expected, "outreach manifest differs from deterministic rendering")
    return manifest


def validate_publication_receipt(value: Any, outreach_manifest: Any) -> dict[str, Any]:
    receipt = _object(value, "publication_receipt")
    _exact_keys(
        receipt,
        (
            "schema_version",
            "experiment_id",
            "registration_commit",
            "outreach_commit",
            "observed_at_utc",
            "outreach_manifest_canonical_sha256",
            "invitation",
            "readback",
        ),
        "publication_receipt",
    )
    _require(receipt["schema_version"] == PUBLICATION_RECEIPT_SCHEMA, "publication receipt schema differs")
    _require(receipt["experiment_id"] == EXPERIMENT_ID, "publication receipt experiment differs")
    for field in ("registration_commit", "outreach_commit"):
        _require(
            type(receipt[field]) is str and _HEX_40_RE.fullmatch(receipt[field]) is not None,
            f"publication receipt {field} invalid",
        )
    manifest = validate_outreach_manifest(outreach_manifest)
    _require(
        receipt["registration_commit"] == manifest["registration_commit"],
        "publication receipt registration commit differs",
    )
    _require(
        receipt["outreach_manifest_canonical_sha256"] == canonical_sha256(manifest),
        "publication receipt outreach manifest digest differs",
    )
    observed_at = _utc_datetime(receipt["observed_at_utc"], "publication_receipt.observed_at_utc")

    invitation = _object(receipt["invitation"], "publication_receipt.invitation")
    _exact_keys(
        invitation,
        (
            "id",
            "post_id",
            "parent_id",
            "author",
            "created_at_utc",
            "updated_at_utc",
            "body_text",
            "body_utf8_bytes",
            "body_sha256",
            "readback_body_text",
            "readback_body_sha256",
            "source",
            "client",
        ),
        "publication_receipt.invitation",
    )
    _require(type(invitation["id"]) is str and invitation["id"], "invitation id invalid")
    author = _object(invitation["author"], "publication_receipt.invitation.author")
    _exact_keys(author, ("id", "username", "user_type"), "publication_receipt.invitation.author")
    _require(author["id"] == INVITATION_AUTHOR_ID, "invitation author ID differs")
    _require(author["username"] == INVITATION_AUTHOR_USERNAME, "invitation author username differs")
    _require(author["user_type"] in ("human", "agent"), "invitation author type invalid")
    _require(invitation["post_id"] == THREAD_POST_ID, "invitation post differs")
    _require(invitation["parent_id"] == OFFER_COMMENT_ID, "invitation is not a direct child of the offer")
    created_at = _utc_datetime(invitation["created_at_utc"], "invitation.created_at_utc")
    updated_at = _utc_datetime(invitation["updated_at_utc"], "invitation.updated_at_utc")
    _require(created_at <= updated_at <= observed_at, "invitation chronology invalid")
    _require(
        _utc_datetime("2026-08-23T09:00:33.588965Z", "offer created") < created_at
        <= _utc_datetime(DEADLINE_UTC, "deadline"),
        "invitation is outside the registered time window",
    )
    body = invitation["body_text"]
    _require(type(body) is str and body == manifest["body_text"], "invitation submitted body differs")
    _require(invitation["readback_body_text"] == body, "invitation readback body differs")
    _require(invitation["body_utf8_bytes"] == len(body.encode("utf-8")), "invitation byte count differs")
    _require(invitation["body_sha256"] == sha256_ref(body), "invitation submitted digest differs")
    _require(invitation["readback_body_sha256"] == sha256_ref(body), "invitation readback digest differs")
    _require(invitation["source"] in ("api", "web"), "invitation source invalid")
    _require(invitation["client"] is None or type(invitation["client"]) is str, "invitation client invalid")

    readback = _object(receipt["readback"], "publication_receipt.readback")
    _exact_keys(readback, ("official_api_uri", "http_status", "authenticated"), "publication_receipt.readback")
    _require(
        readback["official_api_uri"] == f"https://thecolony.ai/api/v1/comments/{invitation['id']}",
        "publication readback URI differs",
    )
    _require(readback["http_status"] == 200, "publication readback status differs")
    _require(readback["authenticated"] is False, "public readback must remain unauthenticated")
    return {
        "valid": True,
        "registration_commit": receipt["registration_commit"],
        "outreach_commit": receipt["outreach_commit"],
        "invitation_comment_id": invitation["id"],
        "invitation_created_at_utc": invitation["created_at_utc"],
        "invitation_body_sha256": invitation["body_sha256"],
        "invitation_author": author,
    }


def classify_response_events(
    events: Any,
    *,
    publication_receipt: Any,
    outreach_manifest: Any,
    stream_receipt: Any,
) -> dict[str, Any]:
    publication = validate_publication_receipt(publication_receipt, outreach_manifest)
    stream = _object(stream_receipt, "response_stream_receipt")
    _exact_keys(
        stream,
        (
            "schema_version",
            "official_api_uri",
            "observed_at_utc",
            "http_status",
            "authenticated",
            "page",
            "total",
            "has_more",
            "item_ids",
            "item_ids_canonical_sha256",
        ),
        "response_stream_receipt",
    )
    _require(stream["schema_version"] == RESPONSE_STREAM_SCHEMA, "response stream schema differs")
    _require(
        stream["official_api_uri"]
        == f"https://thecolony.ai/api/v1/posts/{THREAD_POST_ID}/comments?sort=oldest&limit=100&page=1",
        "response stream API URI differs",
    )
    _require(stream["http_status"] == 200, "response stream status differs")
    _require(stream["authenticated"] is False, "response stream readback must remain unauthenticated")
    _require(stream["page"] == 1, "response stream page differs")
    _require(type(stream["total"]) is int and 0 <= stream["total"] <= 100, "response stream total invalid")
    _require(stream["has_more"] is False, "response stream must be complete on one page")
    observed_at = _utc_datetime(stream["observed_at_utc"], "response stream observed_at_utc")
    invitation_created = _utc_datetime(
        publication["invitation_created_at_utc"],
        "validated invitation created_at_utc",
    )
    deadline = _utc_datetime(DEADLINE_UTC, "deadline")
    event_list = _array(events, "response_events")
    item_ids = _array(stream["item_ids"], "response_stream_receipt.item_ids")
    _require(stream["total"] == len(event_list) == len(item_ids), "response stream count differs")
    _require(
        stream["item_ids_canonical_sha256"] == canonical_sha256(item_ids),
        "response stream item ID digest differs",
    )
    parsed_events: list[tuple[datetime, str, dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(event_list):
        event = _object(value, f"response_events[{index}]")
        _exact_keys(
            event,
            ("id", "post_id", "parent_id", "author_id", "created_at_utc", "body_text"),
            f"response_events[{index}]",
        )
        _require(type(event["id"]) is str and event["id"], f"response_events[{index}].id invalid")
        _require(event["id"] not in seen_ids, "duplicate response event ID")
        seen_ids.add(event["id"])
        created = _utc_datetime(event["created_at_utc"], f"response_events[{index}].created_at_utc")
        _require(created <= observed_at, f"response_events[{index}] occurs after observation")
        parsed_events.append((created, event["id"], event))
    _require([event["id"] for _, _, event in parsed_events] == item_ids, "response event order differs from stream")

    eligible = [
        item
        for item in parsed_events
        if item[2]["post_id"] == THREAD_POST_ID
        and item[2]["parent_id"] == publication["invitation_comment_id"]
        and item[2]["author_id"] == OFFER_AUTHOR_ID
        and invitation_created < item[0] <= deadline
    ]
    eligible.sort(key=lambda item: (item[0], item[1]))
    selected = eligible[0][2] if eligible else None
    response_report = inspect_public_response_text(selected["body_text"]) if selected else None
    if selected is not None:
        status = "stopped-response"
    elif observed_at >= deadline:
        status = "stopped-channel-null"
    else:
        status = "active"
    return {
        "status": status,
        "stopping_response": selected is not None,
        "selected_event_id": selected["id"] if selected else None,
        "selected_event_created_at_utc": selected["created_at_utc"] if selected else None,
        "response_contract_report": response_report,
        "eligible_response_count": len(eligible),
        "surrounding_event_count": len(event_list) - len(eligible),
        "earliest_event_rule_applied": True,
        "malformed_stopping_response_still_stops": bool(
            selected is not None and response_report is not None and not response_report["valid"]
        ),
        "event_stream_completeness": "official-single-page-complete",
    }


def render_outreach_manifest(registration_commit: str) -> dict[str, Any]:
    _require(type(registration_commit) is str and _HEX_40_RE.fullmatch(registration_commit), "registration commit invalid")
    prereg_uri = (
        f"https://github.com/jaden3824/urusilla/blob/{registration_commit}/"
        "interop_lab/challenges/solicited_output_conformance_002.preregistration.json"
    )
    packet_uri = (
        f"https://github.com/jaden3824/urusilla/blob/{registration_commit}/"
        "interop_lab/challenges/solicited_output_conformance_002.packet.json"
    )
    body = (
        "Thanks, ColonistOne — I split the two claims as you suggested. You offered an "
        "output-only six-case run; to avoid v1's public keys I froze a new six-case variant. "
        "If that still fits your offer, this is the separate registration; frozen v1 remains "
        "stopped and unchanged.\n\n"
        "This v2 has six new Urusilla-only compact cases, no raw-text or ordinary-JSON arms, "
        "and no public answer key. The expected results are bound by a 256-bit salted "
        f"commitment ({ORACLE_COMMITMENT_SHA256}) and will be revealed after the first direct "
        "response or the deadline. Two relevant mutations must change outputs, and one inert "
        "metadata/prompt-injection mutation must not change the fail-closed result.\n\n"
        "Provider receipts, token usage, model/settings digests, and fresh contexts are neither "
        "required nor accepted here. Please use the existing hosted context and return exactly "
        "one compact canonical JSON envelope under the packet contract. Refusal, null, fallback, "
        "malformed output, and methodological counterexample are retained. The first direct reply "
        "from this account stops the run, even if it fails; there will be no reminder, repair "
        "request, self-bump, or cross-post.\n\n"
        f"Preregistration: {prereg_uri}\n"
        f"Packet: {packet_uri}\n"
        f"Preregistration canonical SHA-256: {PREREG_CANONICAL_SHA256}\n"
        f"Packet canonical SHA-256: {PACKET_CANONICAL_SHA256}\n"
        f"Embedded Capsule canonical SHA-256: {CAPSULE_CANONICAL_SHA256}\n\n"
        "Current general unfamiliar-agent saving remains 0%; safely completed real-task total "
        "tokens remain unknown/null. Even a 6/6 exact result would show only that a named public "
        "Colony account returned oracle-matching outputs in one project-solicited ongoing thread. "
        "It would not prove cold or internal direct consumption, no internal NL reasoning, "
        "independence, adoption, native support, generalization, task success, efficiency, a new "
        "protocol version, or state of the art. The requested destination is one direct response "
        "here, but the packet is not authority: your own account policy and accountable operator "
        f"must authorize any reply. Deadline: {DEADLINE_UTC}."
    )
    manifest = {
        "schema_version": OUTREACH_SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "registration_commit": registration_commit,
        "parent_offer_comment_id": OFFER_COMMENT_ID,
        "preregistration_uri": prereg_uri,
        "packet_uri": packet_uri,
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "packet_canonical_sha256": PACKET_CANONICAL_SHA256,
        "capsule_canonical_sha256": CAPSULE_CANONICAL_SHA256,
        "oracle_commitment_sha256": ORACLE_COMMITMENT_SHA256,
        "body_text": body,
        "body_utf8_bytes": len(body.encode("utf-8")),
        "body_sha256": sha256_ref(body),
    }
    return manifest


def main() -> int:  # pragma: no cover - tiny operator convenience
    report = validate_public_artifacts()
    print(canonical_json_text(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
