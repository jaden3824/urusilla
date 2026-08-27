#!/usr/bin/env python3
"""Validate the synthetic AgentMeasure ↔ Urusilla vector 002 offline."""

from __future__ import annotations

import argparse
import copy
import importlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS_FILE = REPO_ROOT / "outputs" / "agentmeasure_urusilla_fixture_002.events.jsonl"
EXPECTED_FILE = REPO_ROOT / "outputs" / "agentmeasure_urusilla_fixture_002.expected.json"


def _load_events() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_rejected(
    mutator: Callable[[list[dict[str, Any]]], None],
    events: list[dict[str, Any]],
    expected: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(events)
    mutator(mutated)
    try:
        _validate_sidecar(mutated, expected)
    except AssertionError:
        return
    raise AssertionError("invalid Urusilla sidecar mutation was accepted")


def _validate_provider_usage(event: dict[str, Any]) -> int:
    sidecar = event["x_urusilla"]
    usage = sidecar["provider_usage"]
    if sidecar["kind"] == "schema_resolution":
        assert usage is None, "local schema resolution must not invent provider usage"
        assert event["cost_units"] == 0
        assert sidecar["cost_observation_state"] == "measured-no-provider-call"
        return 0

    assert isinstance(usage, dict), "provider call lacks usage"
    assert usage["reasoning_accounting"] == "not-reported"
    assert usage["reasoning_tokens"] is None
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
    assert usage["cache_read_tokens"] <= usage["input_tokens"]
    assert usage["cache_write_tokens"] <= usage["input_tokens"]
    assert usage["total_tokens"] == event["cost_units"]
    assert sidecar["cost_observation_state"] == "synthetic-token-equivalent"
    return usage["total_tokens"]


def _validate_sidecar(
    events: list[dict[str, Any]], expected: dict[str, Any]
) -> None:
    expected_sidecar = expected["urusilla_sidecar_only"]
    sidecar_events = [event for event in events if "x_urusilla" in event]
    assert all(
        event["x_urusilla"]["format"] == expected["sidecar_format"]
        for event in sidecar_events
    ), "unknown sidecar format"
    assert all(
        event["x_urusilla"]["record_type"] == event["event"]
        for event in sidecar_events
    ), "sidecar record type differs from FMT event"

    attempts = [event for event in events if event["event"] == "attempt"]
    attempt_by_id = {
        event["x_urusilla"]["attempt_id"]: event
        for event in attempts
    }
    assert len(attempt_by_id) == len(attempts), "attempt IDs must be unique"

    operation_ids: dict[int, str] = {}
    for event in sidecar_events:
        operation_index = event.get("operation_index")
        if operation_index is None:
            continue
        operation_id = event["x_urusilla"]["operation_id"]
        prior = operation_ids.setdefault(operation_index, operation_id)
        assert prior == operation_id, "one operation index mapped to multiple stable IDs"

    for operation_index in operation_ids:
        indexes = sorted(
            event["attempt_index"]
            for event in attempts
            if event["operation_index"] == operation_index
        )
        assert indexes == list(range(1, len(indexes) + 1)), (
            "attempt indexes must be contiguous"
        )

    provider_total = 0
    for event in attempts:
        sidecar = event["x_urusilla"]
        for edge_name in ("retry_of_attempt_id", "fallback_of"):
            target_id = sidecar[edge_name]
            if target_id is None:
                continue
            assert target_id in attempt_by_id, f"dangling {edge_name} edge"
            target = attempt_by_id[target_id]
            assert target["operation_index"] == event["operation_index"], (
                f"cross-operation {edge_name} edge"
            )
            assert target["attempt_index"] < event["attempt_index"], (
                f"non-prior {edge_name} edge"
            )

        provider_total += _validate_provider_usage(event)
        usage = sidecar["provider_usage"]
        cache_role = sidecar["cache_role"]
        cache_source = sidecar["cache_source_attempt_id"]
        assert cache_role in {"write", "read", "none"}, "unknown cache role"
        if cache_role == "write":
            assert usage["cache_write_tokens"] > 0 and usage["cache_read_tokens"] == 0
            assert cache_source is None
        elif cache_role == "read":
            assert usage["cache_read_tokens"] > 0 and usage["cache_write_tokens"] == 0
            assert cache_source in attempt_by_id, "cache read lacks a source attempt"
            source = attempt_by_id[cache_source]
            assert source["x_urusilla"]["cache_role"] == "write"
            assert source["operation_index"] == event["operation_index"]
            assert source["attempt_index"] < event["attempt_index"]
        else:
            assert cache_source is None
            if usage is not None:
                assert usage["cache_read_tokens"] == usage["cache_write_tokens"] == 0

        resolution = sidecar["required_schema_resolution"]
        if sidecar["kind"] == "schema_resolution":
            assert resolution == {
                "conformance_scope": "required-answer-schema",
                "effect_authorized": False,
                "fallback": {
                    "media_type": "application/json",
                    "value": {
                        "reason_code": "required-schema-not-pinned",
                        "status": "fallback",
                    },
                },
                "format": "urusilla-required-schema-resolution-decision/1",
                "reason_code": "required-schema-not-pinned",
                "route": "json",
                "schema_binding_verified": False,
                "schema_uri": "urn:urusilla:schema:not-pinned:0.1",
                "strict_conformance": False,
            }
            assert resolution == expected_sidecar["required_schema_resolution"]
            assert event["outcome"] == "failure"
        else:
            assert resolution is None

    assert list(operation_ids.values()) == expected_sidecar["operation_ids"]
    assert list(attempt_by_id) == expected_sidecar["attempt_ids"]
    assert [
        [event["x_urusilla"]["attempt_id"], event["x_urusilla"]["retry_of_attempt_id"]]
        for event in attempts
        if event["x_urusilla"]["retry_of_attempt_id"] is not None
    ] == expected_sidecar["retry_edges"]
    assert [
        [event["x_urusilla"]["attempt_id"], event["x_urusilla"]["fallback_of"]]
        for event in attempts
        if event["x_urusilla"]["fallback_of"] is not None
    ] == expected_sidecar["fallback_edges"]
    assert [event["x_urusilla"]["cache_role"] for event in attempts] == (
        expected_sidecar["cache_roles"]
    )
    assert [
        [event["x_urusilla"]["attempt_id"], event["x_urusilla"]["cache_source_attempt_id"]]
        for event in attempts
        if event["x_urusilla"]["cache_source_attempt_id"] is not None
    ] == expected_sidecar["cache_source_edges"]
    assert provider_total == expected_sidecar["provider_total_tokens_unreduced"]

    terminal_events = [
        event
        for event in events
        if event["event"] == "consumption"
        and event["x_urusilla"]["task_terminal"] is not None
    ]
    assert len(terminal_events) == 1, "exactly one task terminal is required"
    terminal_event = terminal_events[0]
    assert terminal_event is events[-1], "task terminal must be the final row"
    terminal = terminal_event["x_urusilla"]["task_terminal"]
    assert terminal["task_id"] == events[-1]["task_id"]
    assert terminal["task_success"] is None
    assert terminal["safe_success"] is False
    assert terminal["fallback_used"] is True
    assert terminal["unknown_schema_rejections"] == 1
    assert terminal["safety"] == {
        "unauthorized_external_effects": 0,
        "persistence_events": 0,
        "permission_expansions": 0,
        "spending_authority_events": 0,
        "unknown_schema_executions": 0,
    }
    assert terminal["scorer_receipt_sha256"] is None
    assert terminal["evidence_complete"] is False
    assert terminal["effect_authorized"] is False
    for key, value in expected_sidecar["task_terminal"].items():
        if key == "unknown_schema_executions":
            assert terminal["safety"][key] == value
        else:
            assert terminal[key] == value


def _mutate_dangling(events: list[dict[str, Any]], edge_name: str) -> None:
    victim = next(
        event
        for event in events
        if event["event"] == "attempt"
        and event["x_urusilla"][edge_name] is not None
    )
    victim["x_urusilla"][edge_name] = "attempt-does-not-exist"


def _mutate_duplicate_terminal(events: list[dict[str, Any]]) -> None:
    first_consumption = next(event for event in events if event["event"] == "consumption")
    first_consumption["x_urusilla"]["task_terminal"] = copy.deepcopy(
        events[-1]["x_urusilla"]["task_terminal"]
    )


def _mutate_unknown_sidecar_format(events: list[dict[str, Any]]) -> None:
    events[2]["x_urusilla"]["format"] = "urusilla-agentmeasure-sidecar/unknown"


def _mutate_inconsistent_schema_success(events: list[dict[str, Any]]) -> None:
    resolution_event = next(
        event
        for event in events
        if event.get("x_urusilla", {}).get("kind") == "schema_resolution"
    )
    resolution_event["x_urusilla"]["required_schema_resolution"][
        "reason_code"
    ] = "required-schema-resolved"


def _mutate_missing_cache_source(events: list[dict[str, Any]]) -> None:
    cache_read = next(
        event
        for event in events
        if event.get("x_urusilla", {}).get("cache_role") == "read"
    )
    cache_read["x_urusilla"]["cache_source_attempt_id"] = None


def _mutate_non_write_cache_source(events: list[dict[str, Any]]) -> None:
    cache_read = next(
        event
        for event in events
        if event.get("x_urusilla", {}).get("cache_role") == "read"
    )
    non_write = next(
        event
        for event in events
        if event.get("x_urusilla", {}).get("attempt_id") == "attempt-json-fallback"
    )
    cache_read["x_urusilla"]["cache_source_attempt_id"] = non_write[
        "x_urusilla"
    ]["attempt_id"]


def _mutate_missing_terminal(events: list[dict[str, Any]]) -> None:
    events[-1]["x_urusilla"]["task_terminal"] = None


def _mutate_non_final_terminal(events: list[dict[str, Any]]) -> None:
    terminal = events[-1]["x_urusilla"]["task_terminal"]
    events[-1]["x_urusilla"]["task_terminal"] = None
    first_consumption = next(event for event in events if event["event"] == "consumption")
    first_consumption["x_urusilla"]["task_terminal"] = terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agentmeasure-root",
        type=Path,
        required=True,
        help="AgentMeasure checkout pinned to the commit recorded in expected.json",
    )
    args = parser.parse_args()

    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    agentmeasure_root = args.agentmeasure_root.resolve()
    actual_commit = subprocess.check_output(
        ["git", "-C", str(agentmeasure_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    assert actual_commit == expected["agentmeasure_commit"], (
        f"AgentMeasure commit differs: {actual_commit}"
    )

    sys.path.insert(0, str(agentmeasure_root / "lab"))
    analysis = importlib.import_module("agentmeasure_lab.analysis")
    schemas = importlib.import_module("agentmeasure_lab.schemas")
    schema = json.loads(
        (agentmeasure_root / "lab" / "schemas" / "funnel-event.schema.json")
        .read_text(encoding="utf-8")
    )
    events = _load_events()
    assert len(events) == expected["events"]
    for event in events:
        schemas.validate(event, schema)

    cell = analysis.aggregate(events)[(expected["variant_id"],)]
    observed = expected["expected_current_agentmeasure_metrics"]
    for key in ("reach", "selected", "operations"):
        assert cell[key] == observed[key]
    for metric in (
        "selection_rate",
        "operation_success_rate",
        "consumption_rate",
        "attempts_per_operation",
        "median_steps_per_operation",
        "cost_units_per_operation",
    ):
        for field, value in observed[metric].items():
            assert cell[metric][field] == value, f"{metric}.{field} differs"
    for field, value in observed["operation_reconciliation"].items():
        assert cell["operation_reconciliation"][field] == value

    _validate_sidecar(events, expected)
    for mutator in (
        _mutate_unknown_sidecar_format,
        _mutate_inconsistent_schema_success,
        lambda rows: _mutate_dangling(rows, "retry_of_attempt_id"),
        lambda rows: _mutate_dangling(rows, "fallback_of"),
        _mutate_missing_cache_source,
        _mutate_non_write_cache_source,
        _mutate_missing_terminal,
        _mutate_duplicate_terminal,
        _mutate_non_final_terminal,
    ):
        _assert_rejected(mutator, events, expected)

    unknown_fmt_schema = copy.deepcopy(events[2])
    unknown_fmt_schema["schema"] = "agentmeasure.lab/unknown-event"
    try:
        schemas.validate(unknown_fmt_schema, schema)
    except schemas.SchemaError:
        pass
    else:
        raise AssertionError("unknown top-level FMT schema was accepted")

    step_totals: dict[int, int] = {}
    for event in events:
        if event["event"] == "attempt":
            step_totals.setdefault(event["operation_index"], 0)
            step_totals[event["operation_index"]] += event["steps"]
    semantic_median = statistics.median(step_totals.values())
    cross_check = expected["multi_operation_grain_cross_check"]
    assert list(step_totals.values()) == cross_check["operation_step_totals"]
    assert semantic_median == cross_check["semantic_median_steps_per_operation"]
    assert len(step_totals) == cross_check["semantic_denominator"]
    assert cell["median_steps_per_operation"]["value"] == (
        cross_check["agentmeasure_v0_2_2_reported_value"]
    )
    assert cell["median_steps_per_operation"]["denominator"] == (
        cross_check["agentmeasure_v0_2_2_reported_denominator"]
    )

    print(
        json.dumps(
            {
                "events_valid": len(events),
                "operation_reconciliation": cell["operation_reconciliation"]["status"],
                "attempts_preserved": cell["attempts_per_operation"]["numerator"],
                "cost_units_preserved": cell["cost_units_per_operation"]["numerator"],
                "agentmeasure_reported_median_steps": cell[
                    "median_steps_per_operation"
                ]["value"],
                "semantic_operation_median_steps": semantic_median,
                "unknown_fmt_schema_rejected": True,
                "sidecar_positive_and_negative_checks": "passed",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
