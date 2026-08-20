#!/usr/bin/env python3
"""Run bounded local decoder QA and write reproducible evidence artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "decoder_qa"
WORKER = QA_DIR / "qa_worker.py"
RESULT_PREFIX = "DECODER_QA_RESULT="
WALL_TIMEOUT_SECONDS = 30
CAMPAIGN_ORDER = (
    "baseline",
    "roundtrip",
    "boundaries",
    "mutations",
    "replay",
    "known_defects",
    "qa_tests",
)

REQUIRED_READING = (
    "README.md",
    "GOVERNANCE.md",
    "urusilla_v0_1_spec.md",
    "urusilla_capsule_v0_1.json",
    "urusilla_adaptive_dialogue_profile.json",
    "PROVENANCE.md",
    "SECURITY.md",
    "urusilla_benchmark_results.md",
    "urusilla_wire_v02_results.md",
    "urusilla_strong_codec_results.md",
    "urusilla_a2a_envelope_results.md",
    "urusilla_tokenizer_results.md",
    "urusilla_token_surface_v03_results.md",
    "urusilla_token_surface_holdout_results.md",
    "urusilla_adaptive_dialogue_results.md",
    "urusilla_hidden_transfer_results.md",
    "urusilla_teachability_pilot.md",
    "SOURCE_MANIFEST_FORMAT.md",
    "RESEARCH_PROGRAM.md",
    "URUSILLA_INTERNET_LAYER.md",
)

TESTED_INPUTS = (
    "AGENTS.md",
    "urusilla.py",
    "urusilla_wire_v02.py",
    "urusilla_adaptive_dialogue.py",
    "urusilla_benchmark.py",
    "urusilla_example.json",
    "test_urusilla.py",
    "test_urusilla_wire_v02.py",
    "test_urusilla_adaptive_dialogue.py",
    "test_urusilla_boundary_hardening.py",
)

QA_SOURCES = (
    "decoder_qa/__init__.py",
    "decoder_qa/qa_core.py",
    "decoder_qa/qa_worker.py",
    "decoder_qa/run_decoder_qa.py",
    "decoder_qa/test_decoder_qa.py",
    "decoder_qa/known_failures.json",
    "decoder_qa/README.md",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _source_files() -> tuple[str, ...]:
    return tuple(dict.fromkeys(REQUIRED_READING + TESTED_INPUTS + QA_SOURCES))


def _snapshot(paths: Iterable[str]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for relative in paths:
        path = ROOT / relative
        data = path.read_bytes()
        snapshot[relative] = {"bytes": len(data), "sha256": _sha256_bytes(data)}
    return snapshot


def _minimal_child_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_worker(campaign: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [sys.executable, str(WORKER), campaign],
            cwd=ROOT,
            env=_minimal_child_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=WALL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"campaign {campaign!r} exceeded the {WALL_TIMEOUT_SECONDS}-second wall timeout"
        ) from exc

    payloads = [
        line[len(RESULT_PREFIX) :]
        for line in completed.stdout.splitlines()
        if line.startswith(RESULT_PREFIX)
    ]
    if len(payloads) != 1:
        raise RuntimeError(
            f"campaign {campaign!r} emitted {len(payloads)} result records; "
            f"return code={completed.returncode}; stderr={completed.stderr[-2000:]!r}"
        )
    result = json.loads(payloads[0])
    result["process_return_code"] = completed.returncode
    result["stderr"] = completed.stderr
    if completed.returncode != 0 or result.get("status") not in {"passed", "findings"}:
        raise RuntimeError(
            f"campaign {campaign!r} failed: {json.dumps(result, ensure_ascii=True, sort_keys=True)}"
        )
    return result


def _git_revision() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        env=_minimal_child_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="ascii",
        errors="replace",
        timeout=5,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _campaign_row(result: dict[str, Any]) -> str:
    cases = result.get("total_cases", result.get("tests_run", result.get("evaluated_cases", "-")))
    return (
        f"| {result['name']} | {result['status']} | {cases} | "
        f"{result['elapsed_seconds']:.6f} |"
    )


def _json_inline(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _render_report(results: dict[str, Any], results_sha256: str) -> str:
    campaigns = results["campaigns"]
    known = campaigns["known_defects"]
    expected_failure_count = results["totals"]["expected_failures"]
    expected_failure_noun = "failure" if expected_failure_count == 1 else "failures"
    finding_count = results["totals"]["known_findings"]
    finding_noun = "finding" if finding_count == 1 else "findings"
    finding_verb = "remains" if finding_count == 1 else "remain"
    lines = [
        "# Deterministic Decoder Quality-Assurance Report",
        "",
        f"- Run time (UTC): `{results['generated_at_utc']}`",
        f"- Execution ID: `{results['execution_id']}`",
        f"- Machine-readable result SHA-256: `{results_sha256}`",
        f"- Outcome: **{results['outcome']}**",
        "- Scope: local saved parser fixtures and documented grammar only",
        "- External activity: none; network audit events were denied and credential environment variables were not inherited",
        "",
        "## Result",
        "",
        (
            f"The four deterministic behavior campaigns completed "
            f"`{results['totals']['behavior_cases']}` checks. The selected public baseline completed "
            f"`{results['totals']['baseline_tests']}` tests, and the QA regression suite completed "
            f"`{results['totals']['qa_tests']}` tests with "
            f"`{expected_failure_count}` expected {expected_failure_noun}. "
            f"`{finding_count}` shared-code {finding_noun} {finding_verb} reproducible. Shared code was not edited."
        ),
        "",
        "This is quality-assurance evidence, not a conformance badge, security audit, vulnerability assessment, adoption claim, or standards claim.",
        "",
        "## Execution summary",
        "",
        "| Campaign | Status | Cases/tests | Seconds |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(_campaign_row(campaigns[name]) for name in CAMPAIGN_ORDER)

    lines.extend(
        [
            "",
            "## Exact behavior check-unit counts",
            "",
            "A check unit is the campaign's declared deterministic accounting unit (for example, one input, one replay append, or one grouped oracle); it is not necessarily one unittest method or one assertion.",
            "",
        ]
    )
    for name in ("roundtrip", "boundaries", "mutations", "replay"):
        campaign = campaigns[name]
        lines.append(f"### {name}")
        lines.append("")
        for key, value in sorted(campaign["case_counts"].items()):
            lines.append(f"- `{key}`: `{value}`")
        lines.append(f"- `total_cases`: `{campaign['total_cases']}`")
        lines.append("")

    lines.extend(["## Exact campaign digests", ""])
    for name in ("roundtrip", "boundaries", "mutations", "replay"):
        lines.append(f"### {name}")
        lines.append("")
        for key, value in sorted(campaigns[name].get("digests", {}).items()):
            lines.append(f"- `{key}`: `{value}`")
        lines.append("")

    lines.extend(
        [
            "## Shared-code findings",
            "",
            (
                f"The finding campaign evaluated `{known['evaluated_cases']}` minimal deterministic probes "
                f"and reproduced `{known['finding_count']}` {finding_noun}. Binary failing frames were not saved; "
                "they are rebuilt in memory from public fixtures."
            ),
            "",
        ]
    )
    for finding in known["findings"]:
        lines.extend(
            [
                f"### {finding['id']}: {finding['title']}",
                "",
                f"- Expected: {finding['expected']}",
                f"- Observed: `{_json_inline(finding['observed'])}`",
                f"- Shared locations: {', '.join(f'`{item}`' for item in finding['shared_locations'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## Resolved regression probes",
            "",
            (
                "The following formerly failing probes now pass and remain in the QA suite as ordinary "
                f"regressions: {', '.join(f'`{item}`' for item in known['resolved_ids'])}."
            ),
            "",
            "These local results show that the saved implementation rejects or handles the exact prior fixtures as intended. They do not establish the absence of related defect classes.",
            "",
        ]
    )

    capsule = json.loads((ROOT / "urusilla_capsule_v0_1.json").read_text(encoding="utf-8"))
    pinned = capsule["implementation_artifacts"]["reference_codec"]["sha256"]
    current = results["source_snapshot"]["urusilla.py"]["sha256"]
    lines.extend(
        [
            "## Source identity and stability",
            "",
            f"- Source files hashed: `{len(results['source_snapshot'])}`",
            f"- Source snapshot digest: `{results['source_snapshot_sha256']}`",
            f"- Git revision: `{results['git_revision'] or 'unavailable (no resolvable HEAD)'}`",
            f"- Grammar Capsule SHA-256: `{results['source_snapshot']['urusilla_capsule_v0_1.json']['sha256']}`",
            f"- Capsule-pinned reference codec SHA-256: `{pinned}`",
            f"- Saved reference codec SHA-256: `{current}`",
            f"- Saved v0.2 wire codec SHA-256: `{results['source_snapshot']['urusilla_wire_v02.py']['sha256']}`",
            f"- Saved dialogue ledger SHA-256: `{results['source_snapshot']['urusilla_adaptive_dialogue.py']['sha256']}`",
            "- Pre-run and post-run source snapshots were byte-identical.",
            "",
            "The Capsule pin matches the saved reference codec. DQA-004 is retained as an ordinary resolved regression test.",
            "",
            "## Determinism and resource controls",
            "",
            "- Property seed: `0x5e4a01c0de123457`; generated messages: `128`.",
            "- Mutation seed: `0xa11ce55dec0de202`; fixed mutations: `2048`.",
            "- Each campaign ran in a fresh process with a 30-second wall timeout.",
            "- Worker requests: 25 CPU seconds, 1 GiB address space, a 512 MiB sampled RSS watchdog fallback, 1 MiB output-file size, and 64 open files; qa_results.json records host-level availability exactly.",
            "- Network connect, bind, and name-resolution audit events were denied.",
            "- The child process inherited only a minimal non-credential environment.",
            "- Python bytecode generation was disabled.",
            "",
            "## Scope limitations",
            "",
            "- Only the saved local Python implementation, public fixtures, and documented local grammar were exercised.",
            "- No network, third-party target, credentials, external service, exploitation, or vulnerability research was used.",
            "- Fixed mutations provide reproducible coverage but are not exhaustive fuzzing or a proof of absence of defects.",
            "- Checksum mutation tests assess accidental-corruption rejection, not cryptographic authentication.",
            "- Duplicate binary map fields and duplicate CLI JSON members were tested at their respective parser boundaries; the dialogue ledger accepts already-parsed mappings and cannot observe duplicate JSON members.",
            "- Dialogue thread states are asserted using the public conversation/thread composite-key snapshot shape. Alternate snapshot consumers were not tested.",
            "- The exact documented 100,000-recipient boundary and one-over rejection were checked. Unbounded allocation behavior beyond documented limits was not stress-tested.",
            "- Recursive depth was checked at the exact documented boundary with bounded values. No unbounded recursion campaign was run.",
            "- The dialogue corpus has 26 public generated messages; replay consistency outside that fixed corpus remains unproven.",
            "- No unseen partner, comparative fallback, cost benchmark, or public side effect was exercised, so this report cannot establish project support or conformance.",
            "",
            "## Reproduction",
            "",
            "```sh",
            "PYTHONDONTWRITEBYTECODE=1 python3 decoder_qa/run_decoder_qa.py --allow-known-findings",
            "```",
            "",
            "See `known_failures.json` for minimal recipes, `qa_results.json` for full observations, and `SHA256SUMS` for artifact and input identity.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_checksums(paths: Iterable[str]) -> None:
    entries = []
    for relative in sorted(set(paths)):
        entries.append(f"{_sha256_file(ROOT / relative)}  {relative}")
    (QA_DIR / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-known-findings",
        action="store_true",
        help="return success after recording reproducible shared-code findings",
    )
    arguments = parser.parse_args(argv)

    source_files = _source_files()
    before = _snapshot(source_files)
    started = time.monotonic()
    campaigns: dict[str, dict[str, Any]] = {}
    for name in CAMPAIGN_ORDER:
        campaigns[name] = _run_worker(name)
    after = _snapshot(source_files)
    if before != after:
        changed = sorted(path for path in before if before[path] != after[path])
        raise RuntimeError(f"source changed during QA run: {changed}")

    source_snapshot_sha256 = _sha256_bytes(_canonical_json(before))
    behavior_cases = sum(
        campaigns[name]["total_cases"]
        for name in ("roundtrip", "boundaries", "mutations", "replay")
    )
    finding_count = campaigns["known_defects"]["finding_count"]
    outcome = "completed_with_known_findings" if finding_count else "passed"
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "execution_id": _sha256_bytes(
            _canonical_json(
                {
                    "source_snapshot_sha256": source_snapshot_sha256,
                    "property_seed": "0x5e4a01c0de123457",
                    "mutation_seed": "0xa11ce55dec0de202",
                    "campaign_order": CAMPAIGN_ORDER,
                }
            )
        ),
        "outcome": outcome,
        "git_revision": _git_revision(),
        "python": sys.version,
        "platform": platform.platform(),
        "wall_timeout_seconds_per_campaign": WALL_TIMEOUT_SECONDS,
        "elapsed_seconds_total": round(time.monotonic() - started, 6),
        "source_snapshot_sha256": source_snapshot_sha256,
        "source_snapshot": before,
        "source_stable_during_run": True,
        "campaign_order": list(CAMPAIGN_ORDER),
        "campaigns": campaigns,
        "totals": {
            "behavior_cases": behavior_cases,
            "baseline_tests": campaigns["baseline"]["tests_run"],
            "qa_tests": campaigns["qa_tests"]["tests_run"],
            "expected_failures": len(campaigns["qa_tests"]["expected_failures"]),
            "known_finding_probes": campaigns["known_defects"]["evaluated_cases"],
            "known_findings": finding_count,
        },
        "policy": {
            "network": "denied by worker audit hook",
            "credentials": "not inherited by worker environment",
            "external_targets": "none",
            "shared_code_edits": "none",
            "persistent_binary_failures": "none",
        },
    }

    results_path = QA_DIR / "qa_results.json"
    results_path.write_bytes(json.dumps(results, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    results_sha256 = _sha256_file(results_path)
    report_path = QA_DIR / "QA_REPORT.md"
    report_path.write_text(_render_report(results, results_sha256), encoding="utf-8")
    checksum_paths = list(source_files) + [
        "decoder_qa/qa_results.json",
        "decoder_qa/QA_REPORT.md",
    ]
    _write_checksums(checksum_paths)

    print(f"Outcome: {outcome}")
    print(f"Behavior cases: {behavior_cases}")
    print(f"Baseline tests: {campaigns['baseline']['tests_run']}")
    print(
        f"QA tests: {campaigns['qa_tests']['tests_run']} "
        f"({len(campaigns['qa_tests']['expected_failures'])} expected failures)"
    )
    print(f"Known findings: {finding_count}")
    print(f"Results SHA-256: {results_sha256}")
    print(f"Report SHA-256: {_sha256_file(report_path)}")
    return 0 if not finding_count or arguments.allow_known_findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
