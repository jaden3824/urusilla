#!/usr/bin/env python3
"""Validate the SOTA Sentinel evidence registry and its release digests.

The checker intentionally uses only the Python standard library.  It validates
claim-safety invariants, record completeness, comparability lanes, revision
pins, source-link shape, and optional SHA-256 release digests.  It does not
make network requests or attempt to reproduce model experiments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / "registry.json"
DEFAULT_DIGESTS = ROOT / "DIGESTS.sha256"

HEX40 = re.compile(r"^[0-9a-f]{40}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PUBLICATION_DATE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
ALLOWED_TRACKS = {
    "compact_symbolic_or_induced",
    "topology_or_routing_pruning",
    "latent_channel",
    "end_to_end_agent_task",
    "systems_transport_boundary",
    "negative_control",
}
ALLOWED_COMPARISON_CLASSES = {
    "same_workload_candidate",
    "headline_only",
    "systems_boundary",
    "negative_control",
}
ALLOWED_PUBLICATION_STATUS = {
    "peer_reviewed_conference",
    "peer_reviewed_findings",
    "preprint",
    "repository_report",
}
ALLOWED_AVAILABILITY = {"complete", "partial", "absent", "unknown"}
ALLOWED_LICENSE_STATUS = {
    "verified",
    "absent",
    "declared_without_license_text",
    "not_applicable",
    "upstream_mixed_or_unmanifested",
}
ALLOWED_REPRO = {"yes", "conditional", "no"}
ALLOWED_DIRECTIONS = {"lower_is_better", "higher_is_better", "descriptive"}
ALLOWED_LINK_STATUS = {"retrieved", "repository_resolved", "not_applicable"}


class RegistryError(ValueError):
    """Raised when a registry invariant is violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def _require_keys(value: dict[str, Any], keys: Iterable[str], path: str) -> None:
    for key in keys:
        _require(key in value, f"{path}: missing required key {key!r}")


def _is_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _validate_artifact(artifact: dict[str, Any], path: str) -> None:
    _require_keys(
        artifact,
        ["availability", "url", "revision", "license", "license_status", "notes"],
        path,
    )
    _require(
        artifact["availability"] in ALLOWED_AVAILABILITY,
        f"{path}.availability: invalid value",
    )
    if artifact["url"] is not None:
        _require(_is_https_url(artifact["url"]), f"{path}.url: HTTPS URL required")
    revision = artifact["revision"]
    if revision is not None:
        _require(
            isinstance(revision, str) and HEX40.fullmatch(revision) is not None,
            f"{path}.revision: expected a 40-character lowercase Git commit",
        )
        _require(
            artifact["availability"] != "absent",
            f"{path}: absent artifact cannot have a revision",
        )
    _require(
        artifact["license_status"] in ALLOWED_LICENSE_STATUS,
        f"{path}.license_status: invalid value",
    )
    if artifact["license_status"] == "verified":
        _require(
            isinstance(artifact["license"], str) and bool(artifact["license"].strip()),
            f"{path}.license: verified status requires a license identifier",
        )
    _require(isinstance(artifact["notes"], str), f"{path}.notes: string required")


def validate_registry(data: dict[str, Any]) -> None:
    """Validate a loaded registry object or raise ``RegistryError``."""

    _require_keys(
        data,
        [
            "registry_version",
            "as_of",
            "scope",
            "project_claims",
            "comparability_lanes",
            "records",
            "screened_but_not_ranked",
            "claim_gate",
        ],
        "$",
    )
    _require(
        isinstance(data["as_of"], str) and ISO_DATE.fullmatch(data["as_of"]) is not None,
        "$.as_of: YYYY-MM-DD required",
    )
    claims = data["project_claims"]
    _require(isinstance(claims, dict), "$.project_claims: object required")
    _require_keys(
        claims,
        ["sota_claim_made", "world_record_claim_made", "paid_model_calls_used"],
        "$.project_claims",
    )
    _require(claims["sota_claim_made"] is False, "registry must not make a project SOTA claim")
    _require(
        claims["world_record_claim_made"] is False,
        "registry must not make a project world-record claim",
    )
    _require(
        claims["paid_model_calls_used"] is False,
        "registry records a forbidden paid model call",
    )

    lanes = data["comparability_lanes"]
    _require(isinstance(lanes, list) and lanes, "$.comparability_lanes: non-empty list required")
    lane_ids: set[str] = set()
    for index, lane in enumerate(lanes):
        path = f"$.comparability_lanes[{index}]"
        _require(isinstance(lane, dict), f"{path}: object required")
        _require_keys(lane, ["id", "definition", "unit", "included", "excluded"], path)
        lane_id = lane["id"]
        _require(isinstance(lane_id, str) and lane_id, f"{path}.id: non-empty string required")
        _require(lane_id not in lane_ids, f"{path}.id: duplicate lane {lane_id!r}")
        lane_ids.add(lane_id)
        _require(isinstance(lane["included"], list), f"{path}.included: list required")
        _require(isinstance(lane["excluded"], list), f"{path}.excluded: list required")

    records = data["records"]
    _require(isinstance(records, list) and records, "$.records: non-empty list required")
    record_ids: set[str] = set()
    for index, record in enumerate(records):
        path = f"$.records[{index}]"
        _require(isinstance(record, dict), f"{path}: object required")
        _require_keys(
            record,
            [
                "id",
                "method",
                "track",
                "comparison_class",
                "publication",
                "headline",
                "workload",
                "models",
                "ledger",
                "success_constraint",
                "artifacts",
                "reproduction",
                "sources",
                "audit_notes",
            ],
            path,
        )
        record_id = record["id"]
        _require(isinstance(record_id, str) and record_id, f"{path}.id: string required")
        _require(record_id not in record_ids, f"{path}.id: duplicate record {record_id!r}")
        record_ids.add(record_id)
        _require(record["track"] in ALLOWED_TRACKS, f"{path}.track: invalid value")
        _require(
            record["comparison_class"] in ALLOWED_COMPARISON_CLASSES,
            f"{path}.comparison_class: invalid value",
        )

        publication = record["publication"]
        _require(isinstance(publication, dict), f"{path}.publication: object required")
        _require_keys(
            publication,
            ["title", "venue", "status", "date", "primary_url", "doi_or_id"],
            f"{path}.publication",
        )
        _require(
            publication["status"] in ALLOWED_PUBLICATION_STATUS,
            f"{path}.publication.status: invalid value",
        )
        _require(_is_https_url(publication["primary_url"]), f"{path}.publication.primary_url: HTTPS URL required")
        _require(
            isinstance(publication["date"], str)
            and PUBLICATION_DATE.fullmatch(publication["date"]),
            f"{path}.publication.date: YYYY, YYYY-MM, or YYYY-MM-DD required",
        )
        _require(
            publication["date"] <= data["as_of"],
            f"{path}.publication.date: later than registry cutoff",
        )

        headline = record["headline"]
        _require(isinstance(headline, dict), f"{path}.headline: object required")
        _require_keys(
            headline,
            [
                "claim",
                "metric",
                "value",
                "unit",
                "direction",
                "baseline",
                "comparability_lane",
                "incomparable_reason",
            ],
            f"{path}.headline",
        )
        _require(
            headline["direction"] in ALLOWED_DIRECTIONS,
            f"{path}.headline.direction: invalid value",
        )
        _require(
            headline["comparability_lane"] in lane_ids,
            f"{path}.headline.comparability_lane: unknown lane",
        )
        _require(
            isinstance(headline["value"], (int, float)) and not isinstance(headline["value"], bool),
            f"{path}.headline.value: number required",
        )
        if record["comparison_class"] in {"headline_only", "systems_boundary"}:
            _require(
                isinstance(headline["incomparable_reason"], str)
                and bool(headline["incomparable_reason"].strip()),
                f"{path}.headline.incomparable_reason: required for incomparable headline",
            )

        workload = record["workload"]
        _require(isinstance(workload, dict), f"{path}.workload: object required")
        _require_keys(
            workload,
            ["tasks", "sample_definition", "topology", "repetitions", "hardware"],
            f"{path}.workload",
        )
        _require(isinstance(workload["tasks"], list) and workload["tasks"], f"{path}.workload.tasks: non-empty list required")
        _require(isinstance(record["models"], list) and record["models"], f"{path}.models: non-empty list required")

        ledger = record["ledger"]
        _require(isinstance(ledger, dict), f"{path}.ledger: object required")
        _require_keys(ledger, ["included", "excluded", "unknown"], f"{path}.ledger")
        for key in ("included", "excluded", "unknown"):
            _require(isinstance(ledger[key], list), f"{path}.ledger.{key}: list required")

        success = record["success_constraint"]
        _require(isinstance(success, dict), f"{path}.success_constraint: object required")
        _require_keys(
            success,
            ["metric", "baseline", "method", "constraint", "satisfied_as_reported"],
            f"{path}.success_constraint",
        )
        _require(
            isinstance(success["satisfied_as_reported"], bool),
            f"{path}.success_constraint.satisfied_as_reported: boolean required",
        )

        artifacts = record["artifacts"]
        _require(isinstance(artifacts, dict), f"{path}.artifacts: object required")
        _require_keys(artifacts, ["code", "data"], f"{path}.artifacts")
        _validate_artifact(artifacts["code"], f"{path}.artifacts.code")
        _validate_artifact(artifacts["data"], f"{path}.artifacts.data")

        reproduction = record["reproduction"]
        _require(isinstance(reproduction, dict), f"{path}.reproduction: object required")
        _require_keys(
            reproduction,
            ["literal", "clean_room", "literal_blockers", "clean_room_requirements"],
            f"{path}.reproduction",
        )
        _require(reproduction["literal"] in ALLOWED_REPRO, f"{path}.reproduction.literal: invalid value")
        _require(reproduction["clean_room"] in ALLOWED_REPRO, f"{path}.reproduction.clean_room: invalid value")
        _require(isinstance(reproduction["literal_blockers"], list), f"{path}.reproduction.literal_blockers: list required")
        if reproduction["literal"] != "yes":
            _require(
                bool(reproduction["literal_blockers"]),
                f"{path}.reproduction.literal_blockers: non-empty when literal reproduction is not yes",
            )

        sources = record["sources"]
        _require(isinstance(sources, list) and sources, f"{path}.sources: non-empty list required")
        primary_count = 0
        for source_index, source in enumerate(sources):
            source_path = f"{path}.sources[{source_index}]"
            _require(isinstance(source, dict), f"{source_path}: object required")
            _require_keys(source, ["kind", "url", "checked_on", "link_status"], source_path)
            _require(_is_https_url(source["url"]), f"{source_path}.url: HTTPS URL required")
            _require(
                isinstance(source["checked_on"], str) and ISO_DATE.fullmatch(source["checked_on"]),
                f"{source_path}.checked_on: YYYY-MM-DD required",
            )
            _require(source["checked_on"] <= data["as_of"], f"{source_path}.checked_on: later than cutoff")
            _require(source["link_status"] in ALLOWED_LINK_STATUS, f"{source_path}.link_status: invalid value")
            if source["kind"] in {"paper", "official_proceedings", "official_repository"}:
                primary_count += 1
        _require(primary_count >= 1, f"{path}.sources: at least one primary source required")

    screened = data["screened_but_not_ranked"]
    _require(isinstance(screened, list), "$.screened_but_not_ranked: list required")
    for index, item in enumerate(screened):
        path = f"$.screened_but_not_ranked[{index}]"
        _require(isinstance(item, dict), f"{path}: object required")
        _require_keys(item, ["name", "primary_url", "publication_status", "reason"], path)
        _require(_is_https_url(item["primary_url"]), f"{path}.primary_url: HTTPS URL required")

    gate = data["claim_gate"]
    _require(isinstance(gate, dict), "$.claim_gate: object required")
    _require_keys(
        gate,
        ["primary_baseline", "mandatory_baselines", "required_ledgers", "success_rule", "unseen_partner_rule", "release_rule"],
        "$.claim_gate",
    )
    _require(gate["primary_baseline"] in record_ids, "$.claim_gate.primary_baseline: unknown record")
    for record_id in gate["mandatory_baselines"]:
        _require(record_id in record_ids, f"$.claim_gate.mandatory_baselines: unknown record {record_id!r}")


def load_registry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    _require(isinstance(value, dict), "registry root must be an object")
    return value


def verify_digests(root: Path, digest_file: Path) -> None:
    """Verify a GNU-style SHA-256 manifest."""

    _require(digest_file.is_file(), f"digest manifest not found: {digest_file}")
    seen: set[str] = set()
    for line_number, raw_line in enumerate(digest_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        _require(match is not None, f"{digest_file.name}:{line_number}: malformed digest line")
        expected, relative = match.groups()
        _require(relative not in seen, f"{digest_file.name}:{line_number}: duplicate path {relative!r}")
        seen.add(relative)
        target = (root / relative).resolve()
        _require(target.is_relative_to(root.resolve()), f"digest path escapes release directory: {relative!r}")
        _require(target.is_file(), f"digest target not found: {relative!r}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        _require(actual == expected, f"digest mismatch for {relative!r}: expected {expected}, got {actual}")
    _require(seen, "digest manifest contains no entries")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--verify-digests", action="store_true")
    parser.add_argument("--digests", type=Path, default=DEFAULT_DIGESTS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_registry(args.registry)
        validate_registry(registry)
        if args.verify_digests:
            verify_digests(ROOT, args.digests)
    except (OSError, json.JSONDecodeError, RegistryError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"OK: {len(registry['records'])} evidence records, "
        f"{len(registry['comparability_lanes'])} comparability lanes"
        + (", digests verified" if args.verify_digests else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
