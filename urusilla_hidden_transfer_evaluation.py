#!/usr/bin/env python3
"""Evaluate the neutral-ID Capsule transfer pilot reproducibly.

This evaluator was authored after the participant submission. It therefore
reports a hidden-input transfer exercise, not a preregistered or cryptographically
precommitted Teachability Score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from urusilla import UrusillaError, normalize_message


ROOT = Path(__file__).resolve().parent
DEFAULT_TASKS = ROOT / "urusilla_hidden_transfer_tasks.json"
DEFAULT_SUBMISSION = ROOT / "urusilla_hidden_transfer_submission.json"
DEFAULT_EXPECTATIONS = ROOT / "urusilla_hidden_transfer_expectations.json"
DEFAULT_CAPSULE = ROOT / "urusilla_capsule_v0_1.json"
DEFAULT_JSON_OUTPUT = ROOT / "urusilla_hidden_transfer_score.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "urusilla_hidden_transfer_results.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains(value: Any, expected: Any) -> bool:
    if value == expected:
        return True
    if isinstance(value, Mapping):
        return any(_contains(key, expected) or _contains(item, expected) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains(item, expected) for item in value)
    return False


def _envelope_preserved(task: Mapping[str, Any], message: Mapping[str, Any]) -> bool:
    for key, expected in task["envelope"].items():
        target_key = "reply_to" if key == "causal_parent" else key
        if message.get(target_key) != expected:
            return False
    return True


def _essential(case_id: str, message: Mapping[str, Any]) -> bool:
    body = message["body"]
    checks: dict[str, tuple[Any, ...]] = {
        "N4Q7": ("urn:artifact:route-7", 42, "ms"),
        "K2M9": (
            "urn:artifact:route-7",
            "urn:test:route-valid",
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "urn:runner:route-validator-3",
        ),
        "R8D1": ("urn:capability:gpu-a100", "urn:schema:artifact-ref-list:1", "current"),
        "B6T3": ("urn:capability:route-fast", "eu-west", 2),
        "H9V5": (
            "urn:agent:router",
            "urn:agent:planner",
            "urn:artifact:route-7",
            1900000000400,
        ),
        "C3J8": (
            "failed",
            "urn:error:upstream-timeout",
            "urn:log:route-job-88",
            "10000000-0000-4000-8000-000000000005",
        ),
        "P7A2": ("10000000-0000-4000-8000-000000000002",),
        "W5L4": ("urn:sensor:temp-9", 21.5, "UCUM", "Cel", "beta", 9, 1, "calibrated"),
        "M6E3": ("x:trace", "run-17"),
        "V3G8": (
            "urn:artifact:route-7",
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
    }
    if not all(_contains(body, item) for item in checks[case_id]):
        return False
    if case_id == "N4Q7":
        return "RESOLVE" in message.get("expected", [])
    if case_id == "H9V5":
        return message.get("reply_to") == "10000000-0000-4000-8000-000000000004"
    if case_id == "C3J8":
        return message.get("reply_to") == "10000000-0000-4000-8000-000000000005"
    if case_id == "P7A2":
        return message.get("reply_to") == "10000000-0000-4000-8000-000000000002"
    if case_id == "V3G8":
        return (
            message.get("recipients") == ["urn:agent:planner", "urn:agent:router"]
            and message.get("expires_ms") == 1900000010000
        )
    return True


def evaluate(
    tasks_path: Path = DEFAULT_TASKS,
    submission_path: Path = DEFAULT_SUBMISSION,
    expectations_path: Path = DEFAULT_EXPECTATIONS,
    capsule_path: Path = DEFAULT_CAPSULE,
) -> dict[str, Any]:
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    expectations = json.loads(expectations_path.read_text(encoding="utf-8"))

    if _sha256(tasks_path) != expectations["task_sha256"]:
        raise ValueError("task digest does not match the post-submission expectation record")
    if _sha256(submission_path) != expectations["submission_sha256"]:
        raise ValueError("submission digest does not match the post-submission expectation record")
    if _sha256(capsule_path) != expectations["capsule_sha256"]:
        raise ValueError("capsule digest does not match the post-submission expectation record")
    if submission.get("capsule_sha256") != expectations["capsule_sha256"]:
        raise ValueError("participant capsule digest does not match the expectation record")

    task_by_id = {item["case_id"]: item for item in tasks["cases"]}
    expected_by_id = {item["case_id"]: item for item in expectations["cases"]}
    submitted_by_id = {item["case_id"]: item for item in submission["cases"]}
    if set(task_by_id) != set(expected_by_id) or set(task_by_id) != set(submitted_by_id):
        raise ValueError("case identifiers are missing, duplicated, or unexpected")
    historical_failures = expectations["historical_structural_failures"]
    positive_case_ids = {
        case_id
        for case_id, expected in expected_by_id.items()
        if expected["decision"] == "emit"
    }
    if not isinstance(historical_failures, Mapping) or not set(historical_failures) < positive_case_ids:
        raise ValueError("historical structural failures must be a proper subset of emitted cases")

    rows: list[dict[str, Any]] = []
    for case in tasks["cases"]:
        case_id = case["case_id"]
        expected = expected_by_id[case_id]
        submitted = submitted_by_id[case_id]
        decision_ok = submitted.get("decision") == expected["decision"]
        row: dict[str, Any] = {
            "case_id": case_id,
            "expected_decision": expected["decision"],
            "submitted_decision": submitted.get("decision"),
            "decision_ok": decision_ok,
            "act_ok": None,
            "envelope_ok": None,
            "structural_valid": None,
            "essential_semantics_ok": None,
            "validation_error": None,
        }
        if expected["decision"] == "emit":
            message = submitted.get("message")
            row["act_ok"] = isinstance(message, Mapping) and message.get("act") == expected["act"]
            row["envelope_ok"] = isinstance(message, Mapping) and _envelope_preserved(case, message)
            if isinstance(message, Mapping):
                if case_id in historical_failures:
                    row["structural_valid"] = False
                    row["validation_error"] = historical_failures[case_id]
                else:
                    try:
                        canonical = normalize_message(message)
                    except UrusillaError as exc:
                        raise ValueError(
                            f"current validator rejected historically valid case {case_id}: {exc}"
                        ) from exc
                    else:
                        row["structural_valid"] = True
                        row["essential_semantics_ok"] = _essential(case_id, canonical)
            else:
                row["structural_valid"] = False
                row["validation_error"] = "emitted case has no message object"
        else:
            reason = submitted.get("reason")
            row["essential_semantics_ok"] = decision_ok and isinstance(reason, str) and bool(reason.strip())
        rows.append(row)

    positive_rows = [row for row in rows if row["expected_decision"] == "emit"]
    negative_rows = [row for row in rows if row["expected_decision"] == "reject"]
    components = {
        "decision_accuracy": {
            "earned": sum(row["decision_ok"] for row in rows),
            "possible": len(rows),
        },
        "act_selection": {
            "earned": sum(row["act_ok"] is True for row in positive_rows),
            "possible": len(positive_rows),
        },
        "envelope_preservation": {
            "earned": sum(row["envelope_ok"] is True for row in positive_rows),
            "possible": len(positive_rows),
        },
        "structural_generation": {
            "earned": sum(row["structural_valid"] is True for row in positive_rows),
            "possible": len(positive_rows),
        },
        "essential_semantics": {
            "earned": sum(row["essential_semantics_ok"] is True for row in positive_rows),
            "possible": len(positive_rows),
        },
        "negative_rejection": {
            "earned": sum(row["essential_semantics_ok"] is True for row in negative_rows),
            "possible": len(negative_rows),
        },
    }
    return {
        "evaluation": expectations["evaluation"],
        "status": "internal-neutral-id-transfer-pilot-only",
        "external_adopter_claim": False,
        "participant_rerun_after_urusilla_cutover": False,
        "current_artifacts_are_post_cutover_projection": True,
        "standardized_teachability_score": None,
        "why_no_standardized_score": (
            "The pilot did not measure frame parsing, exact graph targets, unseen-partner cross-play, "
            "sample efficiency, or the full non-compensable gates in the Capsule formula."
        ),
        "precommitment": {
            "tasks_existed_before_submission": True,
            "expectations_created_after_submission": True,
            "cryptographic_precommitment": False,
        },
        "digests": {
            "tasks_sha256": _sha256(tasks_path),
            "submission_sha256": _sha256(submission_path),
            "expectations_sha256": _sha256(expectations_path),
            "capsule_sha256": _sha256(capsule_path),
            "historical_task_sha256_before_project_rename": expectations[
                "historical_task_sha256_before_project_rename"
            ],
            "historical_published_submission_sha256_before_project_rename": expectations[
                "historical_published_submission_sha256_before_project_rename"
            ],
            "historical_participant_original_submission_sha256": expectations[
                "historical_participant_original_submission_sha256"
            ],
            "historical_capsule_sha256_before_project_rename": expectations[
                "historical_capsule_sha256_before_project_rename"
            ],
        },
        "components": components,
        "cases": rows,
        "limitations": [
            "One participant instance from the same model family and research environment was used.",
            "File-access isolation was self-declared rather than operating-system enforced.",
            "The participant was not rerun after the Urusilla cutover. Historical digest fields preserve the measured task, Capsule, published submission, and untouched participant artifact; the current files are a post-cutover projection with distinct digests.",
            "Structural generation replays the frozen original validator outcomes; later validator improvements are not credited retroactively.",
            "Expected decisions were conceived while authoring the tasks, but the machine-readable expectation file and evaluator were created only after submission.",
            "Case-specific semantic checks accept multiple valid graphs and are not a complete ontology equivalence proof.",
            "No binary generation, partner task success, latency, learning-token count, or confidence interval was measured.",
        ],
    }


def render_markdown(result: Mapping[str, Any]) -> str:
    components = result["components"]
    lines = [
        "# Neutral-ID Capsule Transfer Pilot",
        "",
        "Status: internal transfer evidence only; not an external adopter claim and not a standardized Teachability Score",
        "",
        "## Result",
        "",
        "Before the Urusilla cutover, a fresh participant saw the then-frozen Capsule and 16 neutral-ID tasks. It selected all 16 emit/reject decisions and all 10 positive acts correctly, but only 6 of 10 emitted messages passed the structural validator used for the original evaluation. The four recorded failures were concrete representation mistakes, so this pilot does not support a native-readiness claim.",
        "",
        "No participant was rerun after the cutover. The current task, submission, and Capsule files are a post-cutover projection bound to current digests; the measured outcomes remain bound to the separately listed historical digests and must not be attributed to a new Urusilla participant run.",
        "",
        "| Component | Result |",
        "|---|---:|",
    ]
    for name in (
        "decision_accuracy",
        "act_selection",
        "envelope_preservation",
        "structural_generation",
        "essential_semantics",
        "negative_rejection",
    ):
        item = components[name]
        percent = 100 * item["earned"] / item["possible"]
        lines.append(f"| {name.replace('_', ' ').title()} | {item['earned']}/{item['possible']} ({percent:.1f}%) |")
    lines.extend(
        [
            "",
            "## Structural failures",
            "",
            "| Case | Validator result |",
            "|---|---|",
        ]
    )
    for row in result["cases"]:
        if row["structural_valid"] is False:
            lines.append(f"| `{row['case_id']}` | {row['validation_error']} |")
    lines.extend(
        [
            "",
            "## Evaluation boundary",
            "",
            "The task file was frozen before the participant response, and identifiers did not disclose acts or decisions. The machine-readable expectation record and evaluator were deliberately created only after the response; there was no cryptographic precommitment. This is better controlled than the earlier open-label smoke test, but it is not a formally preregistered blind trial.",
            "",
            "The structural component replays the original validator snapshot. Later validator changes are not applied retroactively to this historical result; currently valid historical successes are still checked to detect regressions.",
            "",
            "The Capsule's standardized formula also requires frame parsing, exact held-out semantic graphs, unseen composition, sample efficiency, and non-compensable safety gates. Those were not measured, so this report leaves the standardized score null instead of inventing one.",
            "",
            "## Artifact digests",
            "",
        ]
    )
    for name, digest in result["digests"].items():
        lines.append(f"- {name}: `{digest}`")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```bash",
            "python3 urusilla_hidden_transfer_evaluation.py",
            "python3 -m unittest -v test_urusilla_hidden_transfer_evaluation.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--submission", type=Path, default=DEFAULT_SUBMISSION)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument("--capsule", type=Path, default=DEFAULT_CAPSULE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    args = parser.parse_args()
    result = evaluate(args.tasks, args.submission, args.expectations, args.capsule)
    args.json_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(f"wrote {args.json_output}")
    print(f"wrote {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
