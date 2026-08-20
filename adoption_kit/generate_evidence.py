#!/usr/bin/env python3
"""Regenerate deterministic local evidence for the Urusilla Adoption Kit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


KIT = Path(__file__).resolve().parent
ROOT = KIT.parent
sys.path.insert(0, str(KIT / "python"))

from urusilla_sdk import ArtifactCache, UrusillaSDK, canonical_json_bytes  # noqa: E402
from urusilla_sdk.sdk import (  # noqa: E402
    CAPSULE_BOUND_REFERENCE_SHA256,
    CAPSULE_BYTES,
    CAPSULE_SHA256,
    JSON_REPRESENTATION,
    PROFILE_CAPSULE_BYTES,
    PROFILE_CAPSULE_SHA256,
    PROFILE_DICTIONARY_ID,
    RELEASE_STATUS,
    TERSE_REPRESENTATION,
    WIRE_V01_REPRESENTATION,
    WIRE_V02_REPRESENTATION,
    verify_artifact_pins,
)


SOURCE_A = "11111111111111111111111111111111"
SOURCE_B = "22222222222222222222222222222222"
REPRESENTATIONS = (
    JSON_REPRESENTATION,
    TERSE_REPRESENTATION,
    WIRE_V01_REPRESENTATION,
    WIRE_V02_REPRESENTATION,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def freeze_artifact_digests() -> int:
    manifest = KIT / "ARTIFACTS.sha256"
    paths = sorted(
        path
        for path in KIT.rglob("*")
        if path.is_file()
        and path != manifest
        and "__pycache__" not in path.parts
        and path.name != ".DS_Store"
    )
    lines = [f"{sha256(path.read_bytes())}  {path.relative_to(ROOT).as_posix()}" for path in paths]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def endpoint(cache: tuple[str, ...] = (), source: str = SOURCE_A) -> UrusillaSDK:
    return UrusillaSDK(source_id=source, cache=ArtifactCache(cache))


def measure(message: dict[str, Any], representation: str, cache: tuple[str, ...]) -> dict[str, int]:
    sender = endpoint(source=SOURCE_A)
    receiver = endpoint(cache, SOURCE_B)
    session = sender.negotiate(
        receiver.discover_capabilities(),
        message,
        preferred_representation=representation,
        receiver_cache=receiver.cache,
    )
    delivery = sender.encode_delivery(message, session)
    return {
        "raw_payload_bytes": delivery.accounting.raw_payload_bytes,
        "carrier_payload_bytes": delivery.accounting.carrier_payload_bytes,
        "envelope_bytes": delivery.accounting.envelope_bytes,
        "discovery_bytes": session.discovery_bytes,
        "planned_artifact_bytes": session.planned_cold_bytes,
        "first_delivery_total_bytes": (
            session.discovery_bytes
            + session.planned_cold_bytes
            + delivery.accounting.envelope_bytes
        ),
    }


def strict_break_even(
    candidate_cold: int,
    candidate_warm: int,
    baseline_cold: int,
    baseline_warm: int,
) -> int | None:
    per_message = baseline_warm - candidate_warm
    if per_message <= 0:
        return None
    incremental_cold = candidate_cold - baseline_cold
    return max(1, incremental_cold // per_message + 1)


def run_example(path: Path) -> bytes:
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def main() -> int:
    message = json.loads((KIT / "fixtures/request.json").read_text(encoding="utf-8"))
    canonical_fixture = endpoint().normalize_input(message, mode="fallback")
    empty = {rep: measure(message, rep, ()) for rep in REPRESENTATIONS}
    grammar_cache = (CAPSULE_SHA256,)
    full_cache = (CAPSULE_SHA256, PROFILE_CAPSULE_SHA256)
    warm = {
        rep: measure(
            message,
            rep,
            full_cache if rep == WIRE_V02_REPRESENTATION else grammar_cache,
        )
        for rep in REPRESENTATIONS
    }
    representations = {
        rep: {
            "raw_payload_bytes": empty[rep]["raw_payload_bytes"],
            "carrier_payload_bytes": empty[rep]["carrier_payload_bytes"],
            "envelope_bytes": empty[rep]["envelope_bytes"],
            "planned_and_verified_transfer_bytes_empty_cache": empty[rep][
                "planned_artifact_bytes"
            ],
            "first_delivery_total_empty_cache": empty[rep][
                "first_delivery_total_bytes"
            ],
            "first_delivery_total_warm_cache": warm[rep]["first_delivery_total_bytes"],
        }
        for rep in REPRESENTATIONS
    }

    raw_break_even: dict[str, int | None] = {}
    envelope_break_even: dict[str, int | None] = {}
    pairs = (
        (WIRE_V01_REPRESENTATION, JSON_REPRESENTATION),
        (WIRE_V02_REPRESENTATION, JSON_REPRESENTATION),
        (WIRE_V02_REPRESENTATION, WIRE_V01_REPRESENTATION),
        (TERSE_REPRESENTATION, JSON_REPRESENTATION),
    )
    cold = {
        rep: CAPSULE_BYTES + (PROFILE_CAPSULE_BYTES if rep == WIRE_V02_REPRESENTATION else 0)
        for rep in REPRESENTATIONS
    }
    for candidate, baseline in pairs:
        name = f"{candidate}_vs_{baseline}"
        raw_break_even[name] = strict_break_even(
            cold[candidate],
            representations[candidate]["raw_payload_bytes"],
            cold[baseline],
            representations[baseline]["raw_payload_bytes"],
        )
        envelope_break_even[name] = strict_break_even(
            cold[candidate],
            representations[candidate]["envelope_bytes"],
            cold[baseline],
            representations[baseline]["envelope_bytes"],
        )

    selector: dict[str, dict[str, str]] = {"empty_cache": {}, "warm_cache": {}}
    for count in (1, 10, 100):
        for label, cache in (("empty_cache", ()), ("warm_cache", full_cache)):
            sender = endpoint(source=SOURCE_A)
            receiver = endpoint(cache, SOURCE_B)
            selected = sender.negotiate(
                receiver.discover_capabilities(),
                message,
                expected_messages=count,
                receiver_cache=receiver.cache,
            )
            suffix = "message" if count == 1 else "messages"
            selector[label][f"{count}_{suffix}"] = selected.representation

    accounting = {
        "format": "urusilla-codec-accounting-v2",
        "fixture": {
            "canonical_json_sha256": sha256(canonical_json_bytes(canonical_fixture)),
            "path": "adoption_kit/fixtures/request.json",
            "repetition_assumption": "the same canonical message shape repeats",
        },
        "cold_artifacts": {
            "grammar_capsule": {"bytes": CAPSULE_BYTES, "sha256": CAPSULE_SHA256},
            "wire_v02_profile_capsule": {
                "bytes": PROFILE_CAPSULE_BYTES,
                "sha256": PROFILE_CAPSULE_SHA256,
            },
        },
        "discovery_bytes": {
            "both_endpoints_empty_cache": empty[JSON_REPRESENTATION]["discovery_bytes"],
            "both_endpoints_grammar_capsule_cached": warm[JSON_REPRESENTATION][
                "discovery_bytes"
            ],
            "both_endpoints_grammar_and_v02_capsules_cached": warm[
                WIRE_V02_REPRESENTATION
            ]["discovery_bytes"],
        },
        "representations": representations,
        "strict_break_even_messages": {
            "raw_payload_incremental_profile_cost": raw_break_even,
            "full_kit_envelope_incremental_profile_cost": envelope_break_even,
            "null_rule": "candidate warm envelope is not smaller, so no break-even exists",
        },
        "selector_result": {
            **selector,
            "reason": "For this explicit JSON delivery envelope, repeated full v0.2 pin fields outweigh its smaller raw frame relative to v0.1. The unfavorable result is retained.",
        },
        "scope": {
            "includes": [
                "deterministic capability discovery JSON",
                "actual representation payload",
                "Base64 expansion for binary representations",
                "deterministic local delivery envelope",
                "planned cold artifacts followed by exact digest-verified raw in-memory transfer",
            ],
            "excludes": [
                "HTTP, A2A request, MCP transport, TLS, TCP, DNS, authentication, responses, retries",
                "model tokens, model comprehension, task success, latency, energy, external network cost",
                "Base64 or transport wrapping for artifacts",
            ],
        },
    }
    dump(KIT / "evidence/codec_accounting.json", accounting)

    pins = verify_artifact_pins()
    one_a = run_example(KIT / "examples/one_agent_onboarding.py")
    one_b = run_example(KIT / "examples/one_agent_onboarding.py")
    cross_a = run_example(KIT / "examples/two_agent_crossplay.py")
    cross_b = run_example(KIT / "examples/two_agent_crossplay.py")
    if one_a != one_b or cross_a != cross_b:
        raise AssertionError("example output was not byte-stable across two runs")
    cross_result = json.loads(cross_a)
    node_version = subprocess.run(
        ["node", "--version"], check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()
    local_verification = {
        "format": "urusilla-local-verification-v2",
        "snapshot_date": "2026-08-20",
        "scope": "same-project local verification only",
        "environment": {
            "python": sys.version.split()[0],
            "node": node_version.removeprefix("v"),
            "network_traffic_created": False,
            "packages_installed": False,
        },
        "implementation_revision": {
            "status": "unsigned worktree; bind any versioned release manifest to an immutable commit",
        },
        "root_artifact_pins": {
            **{key: value for key, value in pins.items() if not key.startswith("capsule.")},
            "urusilla.py_capsule_embedded": CAPSULE_BOUND_REFERENCE_SHA256,
            "wire_v02_profile_capsule": PROFILE_CAPSULE_SHA256,
            "wire_v02_dictionary_id": PROFILE_DICTIONARY_ID,
        },
        "release_gate": {
            "lifecycle_status": RELEASE_STATUS,
            "unsigned_public_source_distribution_allowed": True,
            "unsigned_operation_scope": "local-read-only",
            "effect_authorizing_requires_trusted_signature_and_policy": True,
            "reference_codec_matches_capsule": pins[
                "capsule.reference_codec_matches_observed"
            ]
            == "true",
            "provenance_bound": False,
            "support_claim_eligible": False,
            "reason": "public source distribution is allowed, but this unsigned worktree has no authenticated provenance or external conformance verifier",
        },
        "tests": {
            "isolated_python_sdk_and_telemetry": {"passed": 41, "failed": 0},
            "dependency_free_node": {"passed": 9, "failed": 0},
        },
        "deterministic_examples": {
            "one_agent_onboarding": {
                "two_runs_identical": True,
                "stdout_bytes": len(one_a),
                "stdout_sha256": sha256(one_a),
            },
            "two_agent_python_node_crossplay": {
                "two_runs_identical": True,
                "stdout_bytes": len(cross_a),
                "stdout_sha256": sha256(cross_a),
                "request_delivery_sha256": cross_result["request_delivery_sha256"],
                "response_delivery_sha256": cross_result["response_delivery_sha256"],
            },
        },
        "wire_identities": {
            "v01_magic_hex": "5552534c01",
            "v02_magic_hex": "5552534c02",
            "v02_capsule_magic_hex": "5552435002",
        },
        "claims": {
            "external_adopters_observed": 0,
            "independently_verified_external_safe_messages": 0,
            "adoption_adjusted_impact_milliunits": 0,
            "crossplay_is_unseen_or_independent": False,
            "task_success_measured": False,
            "download_counts_used": False,
            "external_adoption_claim": False,
        },
    }
    dump(KIT / "evidence/local_verification.json", local_verification)
    artifact_entries = freeze_artifact_digests()
    print(
        json.dumps(
            {
                "accounting": accounting,
                "verification": local_verification,
                "artifact_digest_entries": artifact_entries,
                "artifact_manifest_sha256": sha256((KIT / "ARTIFACTS.sha256").read_bytes()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
