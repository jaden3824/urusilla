"""Content-derived, zero-call inventory check for the finite-bound screen.

This module binds the currently supplied artifact inventory. It deliberately
cannot release the arithmetic screen because no compiler yet derives exact
token vectors and phase bounds from those bytes. It never selects a session
length or authorizes a receiver-ceiling run.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from .contract import IDENTIFIER_RE, VerificationError, canonical_json, sha256_ref

PREFLIGHT_SCHEMA = "urusilla-initial-goal-finite-bound-preflight/1"
PATH_DAG_SCHEMA = "urusilla-initial-goal-finite-bound-path-dag/1"
TOTAL_CAP_SCHEMA = "urusilla-initial-goal-source-enforced-total-cap/1"
SUCCESS_RECEIPT_SCHEMA = "urusilla-initial-goal-baseline-success-receipt/1"
SESSION_LENGTHS = tuple(range(1, 129))
PATHS = ("action-state", "raw-concise", "ordinary-json")
BASELINES = ("raw-concise", "ordinary-json")
KINDS = (
    "pretty-sources",
    "canonical-transmitted-prompts",
    "tokenizer-artifacts",
    "chat-template-artifacts",
    "path-dag-artifacts",
    "source-enforced-total-cap-artifacts",
)
MISSING_NAME = {
    "pretty-sources": "pretty-source-bytes",
    "canonical-transmitted-prompts": "exact-canonical-transmitted-prompt-bytes",
    "tokenizer-artifacts": "exact-tokenizer-bytes",
    "chat-template-artifacts": "exact-chat-template-bytes",
    "path-dag-artifacts": "finite-path-dag-bytes",
    "source-enforced-total-cap-artifacts": "source-enforced-total-cap-bytes",
}
TOKEN_SCOPE = ["complete-input", "visible-output", "billed-reasoning", "unclassified"]
_MAX_ITEM_BYTES = 4 * 1024 * 1024
_MAX_TOTAL_BYTES = 32 * 1024 * 1024


class FiniteBoundPreflightError(VerificationError):
    """Supplied evidence is malformed or contradictory."""


def _keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if any(type(key) is not str for key in value) or set(value) != expected:
        raise FiniteBoundPreflightError(f"{path}:exact-keys-required")


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        raise FiniteBoundPreflightError(f"{path}:identifier-required")
    return value


def _bytes(value: Any, path: str) -> bytes:
    if type(value) is not bytes or not value or len(value) > _MAX_ITEM_BYTES:
        raise FiniteBoundPreflightError(f"{path}:bounded-nonempty-bytes-required")
    return value


def _json(raw: bytes, path: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise FiniteBoundPreflightError(f"{path}:duplicate-json-key")
            result[key] = item
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        if canonical_json(value).encode("utf-8") != raw:
            raise FiniteBoundPreflightError(f"{path}:canonical-json-bytes-required")
        return value
    except FiniteBoundPreflightError:
        raise
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        raise FiniteBoundPreflightError(f"{path}:canonical-json-bytes-required") from exc


def _bundle(
    kind: str,
    value: Any,
    *,
    remaining_bytes: int,
) -> tuple[dict[str, object], dict[str, bytes], int]:
    source = {} if value is None else value
    if type(source) is not dict or len(source) > 512:
        raise FiniteBoundPreflightError(f"artifacts.{kind}:bounded-object-required")
    if any(type(key) is not str for key in source):
        raise FiniteBoundPreflightError(
            f"artifacts.{kind}:string-artifact-ids-required"
        )
    checked: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    used_bytes = 0
    for artifact_id in sorted(source):
        artifact_id = _identifier(artifact_id, f"artifacts.{kind}.id")
        raw = _bytes(source[artifact_id], f"artifacts.{kind}.{artifact_id}")
        used_bytes += len(raw)
        if used_bytes > remaining_bytes:
            raise FiniteBoundPreflightError(
                "artifacts:total-byte-limit-exceeded"
            )
        checked[artifact_id] = raw
        entries.append(
            {"artifact_id": artifact_id, "byte_count": len(raw), "sha256": sha256_ref(raw)}
        )
    body = {"kind": kind, "artifacts": entries}
    return {**body, "bundle_sha256": sha256_ref(body)}, checked, used_bytes


def _validate_dag(raw: bytes, artifact_id: str) -> dict[str, object]:
    path = f"artifacts.path-dag-artifacts.{artifact_id}"
    value = _json(raw, path)
    if type(value) is not dict:
        raise FiniteBoundPreflightError(f"{path}:object-required")
    _keys(value, {"schema_version", "paths"}, path)
    paths = value["paths"]
    if value["schema_version"] != PATH_DAG_SCHEMA or type(paths) is not dict:
        raise FiniteBoundPreflightError(f"{path}:known-schema-required")
    _keys(paths, set(PATHS), f"{path}.paths")
    counts: dict[str, int] = {}
    for name in PATHS:
        spec = paths[name]
        if type(spec) is not dict:
            raise FiniteBoundPreflightError(f"{path}.paths.{name}:object-required")
        _keys(spec, {"entry", "edges"}, f"{path}.paths.{name}")
        entry = _identifier(spec["entry"], f"{path}.paths.{name}.entry")
        edges = spec["edges"]
        if type(edges) is not dict or not edges or len(edges) > 512 or entry not in edges:
            raise FiniteBoundPreflightError(f"{path}.paths.{name}:bounded-graph-required")
        graph: dict[str, tuple[str, ...]] = {}
        for node, targets in edges.items():
            node = _identifier(node, f"{path}.paths.{name}.node")
            if type(targets) is not list:
                raise FiniteBoundPreflightError(f"{path}.paths.{name}.{node}:edge-array-required")
            checked_targets = tuple(
                _identifier(target, f"{path}.paths.{name}.{node}.edge") for target in targets
            )
            if len(set(checked_targets)) != len(checked_targets):
                raise FiniteBoundPreflightError(
                    f"{path}.paths.{name}.{node}:duplicate-edge-forbidden"
                )
            graph[node] = checked_targets
        if any(
            target not in graph
            for targets in graph.values()
            for target in targets
        ):
            raise FiniteBoundPreflightError(f"{path}.paths.{name}:dangling-edge")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise FiniteBoundPreflightError(f"{path}.paths.{name}:cycle-forbidden")
            if node not in visited:
                visiting.add(node)
                for target in graph[node]:
                    visit(target)
                visiting.remove(node)
                visited.add(node)

        visit(entry)
        if visited != set(graph) or not any(not targets for targets in graph.values()):
            raise FiniteBoundPreflightError(
                f"{path}.paths.{name}:reachable-terminal-required"
            )
        counts[name] = len(graph)
    return {"artifact_id": artifact_id, "node_counts": counts}


def _validate_cap(raw: bytes, artifact_id: str) -> dict[str, object]:
    path = f"artifacts.source-enforced-total-cap-artifacts.{artifact_id}"
    value = _json(raw, path)
    if type(value) is not dict:
        raise FiniteBoundPreflightError(f"{path}:object-required")
    _keys(
        value,
        {
            "schema_version",
            "maximum_total_tokens",
            "token_scope",
            "enforcement_stage",
            "overflow_action",
            "enforcement_source_utf8",
        },
        path,
    )
    cap = value["maximum_total_tokens"]
    source = value["enforcement_source_utf8"]
    if (
        value["schema_version"] != TOTAL_CAP_SCHEMA
        or type(cap) is not int
        or cap <= 0
        or cap > (1 << 63) - 1
        or value["token_scope"] != TOKEN_SCOPE
        or value["enforcement_stage"] != "before-provider-call"
        or value["overflow_action"] != "do-not-call"
        or type(source) is not str
        or not source
    ):
        raise FiniteBoundPreflightError(
            f"{path}:source-enforced-inclusive-cap-required"
        )
    return {
        "artifact_id": artifact_id,
        "maximum_total_tokens": cap,
        "enforcement_source_sha256": sha256_ref(source.encode("utf-8")),
    }


def _receipt(raw: bytes, baseline: str, bundle_hashes: dict[str, str]) -> dict[str, object]:
    path = f"baseline_success_receipts.{baseline}"
    value = _json(raw, path)
    if type(value) is not dict:
        raise FiniteBoundPreflightError(f"{path}:object-required")
    _keys(
        value,
        {
            "schema_version",
            "baseline_path",
            "artifact_bundle_sha256",
            "safe_success_by_item",
        },
        path,
    )
    safe = value["safe_success_by_item"]
    if (
        value["schema_version"] != SUCCESS_RECEIPT_SCHEMA
        or value["baseline_path"] != baseline
        or value["artifact_bundle_sha256"] != bundle_hashes
        or type(safe) is not list or len(safe) != 128
        or any(type(item) is not bool for item in safe)
    ):
        raise FiniteBoundPreflightError(
            f"{path}:content-bound-128-item-receipt-required"
        )
    total = 0
    by_n: list[int] = []
    for succeeded in safe:
        total += int(succeeded)
        by_n.append(total)
    return {
        "status": "content-bound-positive" if total else "content-bound-zero",
        "receipt_byte_count": len(raw),
        "receipt_sha256": sha256_ref(raw),
        "safe_successes_by_n": by_n,
    }


def _nonclaims() -> dict[str, object]:
    return {
        "provider_calls_performed": 0,
        "model_calls_performed": 0,
        "receiver_ceiling_run_permitted": False,
        "claim_eligible": False,
        "efficiency_claim_eligible": False,
        "protocol_version_promotion_permitted": False,
        "adoption_claim_permitted": False,
    }


def _finish(body: dict[str, object]) -> dict[str, object]:
    return {**body, "result_sha256": sha256_ref(body)}


def build_finite_bound_preflight_manifest(
    *,
    artifacts: Mapping[str, Mapping[str, bytes]] | None = None,
    baseline_success_receipts: Mapping[str, bytes | None] | None = None,
) -> dict[str, object]:
    """Bind supplied inventory; numeric readiness always remains blocked."""
    try:
        artifacts = {} if artifacts is None else artifacts
        if type(artifacts) is not dict or set(artifacts) - set(KINDS):
            raise FiniteBoundPreflightError("artifacts:closed-kind-object-required")
        bundles: dict[str, dict[str, object]] = {}
        raw_bundles: dict[str, dict[str, bytes]] = {}
        ids: set[str] = set()
        remaining_bytes = _MAX_TOTAL_BYTES
        for kind in KINDS:
            bundles[kind], raw_bundles[kind], used_bytes = _bundle(
                kind,
                artifacts.get(kind),
                remaining_bytes=remaining_bytes,
            )
            remaining_bytes -= used_bytes
            if ids.intersection(raw_bundles[kind]):
                raise FiniteBoundPreflightError(
                    "artifact-id:cross-kind-reuse-forbidden"
                )
            ids.update(raw_bundles[kind])
        dags = [
            _validate_dag(raw, key)
            for key, raw in sorted(raw_bundles["path-dag-artifacts"].items())
        ]
        caps = [
            _validate_cap(raw, key)
            for key, raw in sorted(
                raw_bundles["source-enforced-total-cap-artifacts"].items()
            )
        ]
        receipts = (
            {} if baseline_success_receipts is None else baseline_success_receipts
        )
        if type(receipts) is not dict or set(receipts) - set(BASELINES):
            raise FiniteBoundPreflightError(
                "baseline_success_receipts:closed-baseline-object-required"
            )
        bundle_hashes = {
            kind: str(bundles[kind]["bundle_sha256"]) for kind in KINDS
        }
        success: dict[str, dict[str, object]] = {}
        for baseline in BASELINES:
            raw = receipts.get(baseline)
            success[baseline] = (
                {
                    "status": "unknown",
                    "receipt_byte_count": None,
                    "receipt_sha256": None,
                    "safe_successes_by_n": None,
                }
                if raw is None
                else _receipt(
                    _bytes(raw, f"baseline_success_receipts.{baseline}"),
                    baseline,
                    bundle_hashes,
                )
            )
        missing_inventory = [
            MISSING_NAME[kind] for kind in KINDS if not raw_bundles[kind]
        ]
        for baseline in BASELINES:
            status = success[baseline]["status"]
            if status == "unknown":
                missing_inventory.append(
                    f"baseline-safe-success-receipt:{baseline}:unknown"
                )
        missing_inventory.sort()
        inventory_complete = not missing_inventory
        missing = [
            *missing_inventory,
            "content-derived-token-vectors-and-phase-bound-compiler",
        ]
        commitment = {
            "schema_version": (
                "urusilla-initial-goal-finite-bound-preflight-commitment/1"
            ),
            "artifact_bundles": bundles,
            "path_dag_summaries": dags,
            "total_cap_summaries": caps,
            "baseline_safe_success": success,
        }
        body = {
            "schema_version": PREFLIGHT_SCHEMA,
            "outcome": "blocked",
            "inventory_complete": inventory_complete,
            "numeric_screen_permitted": False,
            "selected_session_length": None,
            "manifest_sha256": sha256_ref(commitment),
            "missing_requirements": missing,
            "artifact_bundles": bundles,
            "path_dag_summaries": dags,
            "total_cap_summaries": caps,
            "baseline_safe_success": success,
            "error": None,
            **_nonclaims(),
        }
        return _finish(body)
    except (
        FiniteBoundPreflightError,
        VerificationError,
        TypeError,
        KeyError,
        IndexError,
    ) as exc:
        return _finish(
            {
                "schema_version": PREFLIGHT_SCHEMA,
                "outcome": "invalid",
                "inventory_complete": False,
                "numeric_screen_permitted": False,
                "selected_session_length": None,
                "manifest_sha256": None,
                "missing_requirements": [],
                "artifact_bundles": {},
                "path_dag_summaries": [],
                "total_cap_summaries": [],
                "baseline_safe_success": {},
                "error": str(exc),
                **_nonclaims(),
            }
        )


def canonical_preflight_json(result: Mapping[str, Any]) -> str:
    """Return deterministic canonical JSON for storage or comparison."""
    return canonical_json(result)
