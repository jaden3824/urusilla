#!/usr/bin/env python3
"""Checkpointed semantic-delta experiment for correlated agent state.

The experiment compares independently authenticated full-state records with a
stateful semantic-delta candidate under the same standalone text envelope.
The delta candidate is selected only when its complete tokenizer count is
strictly lower than the full-state fallback. Periodic full checkpoints bound
state-loss recovery. This is an offline serialization study over a synthetic,
scenario-shaped correlated workload; it does not measure model understanding,
task success, deployment energy, adoption, or state-of-the-art standing.
"""

from __future__ import annotations

import argparse
import base64
import copy
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
from pathlib import Path
import platform
import statistics
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import uuid

from urusilla_tokenizer_benchmark import (
    TokenizerProfile,
    default_asset_root,
    load_tokenizer_profiles,
)


FORMAT = "urusilla-session-delta-v0.9-experimental"
REPORT_NAME = "SESSION_DELTA_V09_RESULTS.md"
ROOT = Path(__file__).resolve().parent

SESSIONS_PER_WORKFLOW = 6
TURNS_PER_SESSION = 32
CHECKPOINT_INTERVALS = (1, 2, 4, 8, 16, 32)
REPRESENTATIVE_INTERVAL = 8

MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_STATE_BYTES = 2 * 1024 * 1024
MAX_STRING_BYTES = 256 * 1024
MAX_COLLECTION_ITEMS = 20_000
MAX_DEPTH = 32
MAX_PATH_COMPONENTS = 16
MAX_PATCH_OPERATIONS = 20_000

PREFIX = "D9"
MODES = ("F", "D")
SESSION_HEX_CHARACTERS = 32
SEQUENCE_HEX_CHARACTERS = 8
DIGEST_BYTES = 16
DIGEST_CHARACTERS = 22
TAG_BYTES = 16
TAG_CHARACTERS = 22
HEADER_CHARACTERS = (
    len(PREFIX)
    + 1
    + SESSION_HEX_CHARACTERS
    + SEQUENCE_HEX_CHARACTERS
    + DIGEST_CHARACTERS
    + TAG_CHARACTERS
    + 1
)
ZERO_DIGEST = b"\x00" * DIGEST_BYTES
DOMAIN = b"UrusillaSessionDelta-v0.9-standalone\x00"
TEST_KEY = hashlib.sha256(
    b"public deterministic v0.9 integrity fixture; never a deployment secret"
).digest()

EXPECTED_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}

EXPECTED_CORPUS_DIGEST = (
    "729a602163a6e7698ea6aa9d9859dba17decfbed998afba219ec88b51aaeb419"
)
EXPECTED_MATRIX_DIGEST = (
    "2647d3c4c3a1c399352d49f7c79d5456986ee7176c0e9f131b5a14760e6131d2"
)

JsonValue = Any
JsonMap = dict[str, Any]
PathTuple = tuple[str, ...]

_TOKEN_COUNT_CACHE: dict[tuple[str, str], int] = {}


class DeltaError(ValueError):
    """Raised when a state, patch, record, or stream transition is invalid."""


@dataclass(frozen=True)
class ParsedRecord:
    mode: str
    session_id: str
    sequence: int
    base_digest: bytes
    payload: str


@dataclass(frozen=True)
class Plan:
    tokenizer_key: str
    interval: int
    session_id: str
    records: tuple[str, ...]
    modes: tuple[str, ...]
    token_total: int
    byte_total: int
    full_baseline_tokens: int
    full_baseline_bytes: int
    raw_json_tokens: int
    raw_json_bytes: int
    forced_full: int
    fallback_full: int
    delta_wins: int
    cold_checkpoint_tokens: int
    cold_checkpoint_bytes: int


@dataclass(frozen=True)
class Aggregate:
    tokenizer_key: str
    tokenizer_name: str
    interval: int
    records: int
    token_total: int
    byte_total: int
    full_baseline_tokens: int
    full_baseline_bytes: int
    raw_json_tokens: int
    raw_json_bytes: int
    forced_full: int
    fallback_full: int
    delta_wins: int
    cold_checkpoint_tokens: int
    cold_checkpoint_bytes: int
    exact: int
    deterministic: int

    @property
    def token_saving_percent(self) -> float:
        return _saving(self.full_baseline_tokens, self.token_total)

    @property
    def byte_saving_percent(self) -> float:
        return _saving(self.full_baseline_bytes, self.byte_total)


@dataclass(frozen=True)
class ByteAggregate:
    interval: int
    records: int
    selected_bytes: int
    full_bytes: int
    forced_full: int
    fallback_full: int
    delta_wins: int
    exact: int
    deterministic: int

    @property
    def saving_percent(self) -> float:
        return _saving(self.full_bytes, self.selected_bytes)


@dataclass(frozen=True)
class FaultResults:
    records: int
    integrity_attempted: int
    integrity_rejected: int
    reset_delta_attempted: int
    reset_delta_rejected: int
    independent_checkpoints: int
    replay_attempted: int
    replay_rejected: int
    out_of_order_attempted: int
    out_of_order_rejected: int
    loss_attempted: int
    post_loss_rejected: int
    checkpoint_recovered: int
    maximum_skipped_records: int


@dataclass(frozen=True)
class LatencyResults:
    samples: int
    full_encode_p50_us: float
    full_encode_p95_us: float
    adaptive_encode_p50_us: float
    adaptive_encode_p95_us: float
    adaptive_decode_p50_us: float
    adaptive_decode_p95_us: float


@dataclass(frozen=True)
class Study:
    sessions: tuple[tuple[JsonMap, ...], ...]
    profiles: tuple[TokenizerProfile, ...]
    aggregates: tuple[Aggregate, ...]
    byte_aggregates: tuple[ByteAggregate, ...]
    fault_results: FaultResults
    latency: LatencyResults
    matrix_digest: str


WORKFLOWS = (
    {
        "key": "incident-triage",
        "targets": ("payments-api", "search-index", "identity-gateway"),
        "criteria": (
            "restore service health",
            "preserve an auditable evidence chain",
            "obtain verifier approval before closure",
        ),
        "actions": ("observe", "classify", "contain", "repair", "verify", "close"),
        "labels": ("operations", "safety", "availability"),
    },
    {
        "key": "inventory-reservation",
        "targets": ("north-warehouse", "central-warehouse", "coastal-warehouse"),
        "criteria": (
            "reserve the requested quantity",
            "respect allocation and expiry constraints",
            "publish a reconciled reservation receipt",
        ),
        "actions": ("inspect", "allocate", "hold", "reconcile", "confirm", "release"),
        "labels": ("inventory", "transaction", "reconciliation"),
    },
    {
        "key": "document-review",
        "targets": ("policy-draft", "research-memo", "release-notes"),
        "criteria": (
            "resolve every material review finding",
            "retain source provenance",
            "publish a verifier-approved revision",
        ),
        "actions": ("read", "annotate", "revise", "cross-check", "approve", "publish"),
        "labels": ("review", "provenance", "quality"),
    },
    {
        "key": "route-planning",
        "targets": ("route-blue", "route-green", "route-orange"),
        "criteria": (
            "produce a feasible route",
            "stay within time and cost budgets",
            "record constraint and verifier outcomes",
        ),
        "actions": ("survey", "propose", "simulate", "adjust", "verify", "dispatch"),
        "labels": ("planning", "constraints", "logistics"),
    },
)

AGENTS = (
    "planner.alpha.agent",
    "executor.beta.agent",
    "verifier.gamma.agent",
    "auditor.delta.agent",
    "broker.epsilon.agent",
    "observer.zeta.agent",
)


def _canonical_json(value: JsonValue) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise DeltaError("value is not canonical JSON data") from exc


def _parse_canonical_json(text: str) -> JsonValue:
    if not isinstance(text, str):
        raise DeltaError("JSON payload must be text")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DeltaError("payload is not valid JSON") from exc
    if _canonical_json(value) != text:
        raise DeltaError("payload is not canonical JSON")
    return value


def _stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{FORMAT}:{label}"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str, expected_bytes: int, field: str) -> bytes:
    if not isinstance(text, str) or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in text
    ):
        raise DeltaError(f"{field} is not canonical Base64url")
    try:
        value = base64.b64decode(
            text + "=" * (-len(text) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise DeltaError(f"{field} is not canonical Base64url") from exc
    if len(value) != expected_bytes or _b64url(value) != text:
        raise DeltaError(f"{field} has the wrong canonical width")
    return value


def _saving(baseline: int, candidate: int) -> float:
    if baseline <= 0:
        raise ValueError("baseline must be positive")
    return (baseline - candidate) * 100.0 / baseline


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("at least one value is required")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _walk_json(value: JsonValue, *, depth: int = 0) -> int:
    if depth > MAX_DEPTH:
        raise DeltaError("JSON nesting exceeds the resource limit")
    if value is None or isinstance(value, bool):
        return 1
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(1 << 63) <= value <= (1 << 63) - 1:
            raise DeltaError("integer is outside the signed 64-bit range")
        return 1
    if isinstance(value, float):
        raise DeltaError("floating-point values are not permitted")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise DeltaError("string exceeds the resource limit")
        return 1
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise DeltaError("list exceeds the resource limit")
        total = 1
        for item in value:
            total += _walk_json(item, depth=depth + 1)
            if total > MAX_COLLECTION_ITEMS:
                raise DeltaError("JSON tree exceeds the item limit")
        return total
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise DeltaError("object exceeds the resource limit")
        total = 1
        for key, item in value.items():
            if not isinstance(key, str):
                raise DeltaError("object keys must be text")
            if len(key.encode("utf-8")) > MAX_STRING_BYTES:
                raise DeltaError("object key exceeds the resource limit")
            total += _walk_json(item, depth=depth + 1)
            if total > MAX_COLLECTION_ITEMS:
                raise DeltaError("JSON tree exceeds the item limit")
        return total
    raise DeltaError("unsupported JSON value type")


def validate_state(value: JsonValue) -> JsonMap:
    _walk_json(value)
    if not isinstance(value, dict):
        raise DeltaError("state must be an object")
    required = {
        "session_id",
        "workflow",
        "turn",
        "phase",
        "participants",
        "objective",
        "constraints",
        "progress",
        "latest_event",
        "evidence_index",
        "decision_log",
        "pending_actions",
        "annotations",
        "history_digest",
    }
    if set(value) != required:
        raise DeltaError("state fields do not match the frozen schema")
    try:
        session = str(uuid.UUID(value["session_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DeltaError("state session_id is not a canonical UUID") from exc
    if session != value["session_id"]:
        raise DeltaError("state session_id is not canonical")
    if value["workflow"] not in {item["key"] for item in WORKFLOWS}:
        raise DeltaError("state workflow is unknown")
    turn = value["turn"]
    if not isinstance(turn, int) or isinstance(turn, bool) or not 0 <= turn < 2**32:
        raise DeltaError("state turn is not an unsigned 32-bit integer")
    raw = _canonical_json(value).encode("utf-8")
    if len(raw) > MAX_STATE_BYTES:
        raise DeltaError("state exceeds the byte limit")
    return copy.deepcopy(value)


def _phase(turn: int) -> str:
    boundaries = (
        "discovery",
        "analysis",
        "execution",
        "verification",
        "closure",
    )
    return boundaries[min(len(boundaries) - 1, turn * len(boundaries) // TURNS_PER_SESSION)]


def _event_digest(workflow: str, variant: int, turn: int) -> str:
    return hashlib.sha256(
        f"{FORMAT}|event|{workflow}|{variant}|{turn}".encode("utf-8")
    ).hexdigest()


def build_state(workflow_index: int, variant: int, turn: int) -> JsonMap:
    if not 0 <= workflow_index < len(WORKFLOWS):
        raise ValueError("workflow index is outside the frozen set")
    if not 0 <= variant < SESSIONS_PER_WORKFLOW:
        raise ValueError("variant is outside the frozen set")
    if not 0 <= turn < TURNS_PER_SESSION:
        raise ValueError("turn is outside the frozen session")
    workflow = WORKFLOWS[workflow_index]
    key = workflow["key"]
    session_id = _stable_uuid(f"session:{key}:{variant}")
    target = workflow["targets"][variant % len(workflow["targets"])]
    coordinator = AGENTS[(workflow_index + variant) % len(AGENTS)]
    worker = AGENTS[(workflow_index + variant + 1) % len(AGENTS)]
    verifier = AGENTS[(workflow_index + variant + 2) % len(AGENTS)]
    action = workflow["actions"][turn % len(workflow["actions"])]
    evidence_index: JsonMap = {}
    for evidence_turn in range(0, turn + 1, 4):
        evidence_index[f"e{evidence_turn:02d}"] = {
            "uri": f"urn:evidence:{key}:{variant}:{evidence_turn}",
            "sha256": _event_digest(key, variant, evidence_turn),
            "confidence_ppm": min(990_000, 610_000 + evidence_turn * 11_000 + variant * 2_000),
            "verified": evidence_turn + 4 <= turn,
        }
    decision_log: JsonMap = {}
    for decision_turn in range(3, turn + 1, 8):
        decision_log[f"d{decision_turn:02d}"] = {
            "decision": f"{workflow['actions'][decision_turn % len(workflow['actions'])]}:{target}",
            "owner": AGENTS[(variant + decision_turn) % len(AGENTS)],
            "basis": f"urn:evidence:{key}:{variant}:{max(0, decision_turn - 3)}",
            "status": "accepted" if decision_turn + 8 <= turn else "provisional",
        }
    completed = min(TURNS_PER_SESSION, turn + 1)
    progress_ppm = completed * 1_000_000 // TURNS_PER_SESSION
    event_material = "|".join(_event_digest(key, variant, item) for item in range(turn + 1))
    state = {
        "session_id": session_id,
        "workflow": key,
        "turn": turn,
        "phase": _phase(turn),
        "participants": {
            "coordinator": coordinator,
            "worker": worker,
            "verifier": verifier,
            "observers": [AGENTS[(variant + 3) % len(AGENTS)]],
        },
        "objective": {
            "target": target,
            "success_criteria": list(workflow["criteria"]),
            "requested_by": AGENTS[(variant + 4) % len(AGENTS)],
        },
        "constraints": {
            "deadline_ms": 1_800_000 + variant * 120_000,
            "budget_units": 800 + workflow_index * 100 + variant * 25,
            "requires_verifier": True,
            "policies": ["least-authority", "source-provenance", "explicit-effects"],
        },
        "progress": {
            "completed_steps": completed,
            "total_steps": TURNS_PER_SESSION,
            "progress_ppm": progress_ppm,
            "confidence_ppm": min(985_000, 540_000 + turn * 13_000 + variant * 1_000),
            "open_items": max(0, 9 - turn // 4),
            "compute_units_used": 18 + turn * (3 + workflow_index) + variant,
        },
        "latest_event": {
            "id": _stable_uuid(f"event:{key}:{variant}:{turn}"),
            "actor": AGENTS[(variant + turn) % len(AGENTS)],
            "act": action,
            "summary": f"{action} {target} at step {turn + 1}",
            "result": "accepted" if turn % 5 else "needs-review",
            "evidence_uri": f"urn:evidence:{key}:{variant}:{turn - turn % 4}",
        },
        "evidence_index": evidence_index,
        "decision_log": decision_log,
        "pending_actions": [
            {
                "owner": AGENTS[(variant + turn + offset + 1) % len(AGENTS)],
                "action": workflow["actions"][(turn + offset + 1) % len(workflow["actions"])],
                "due_turn": min(TURNS_PER_SESSION - 1, turn + offset + 1),
            }
            for offset in range(2)
        ],
        "annotations": {
            "priority": ("normal", "high", "urgent")[variant % 3],
            "region": ("ap-northeast", "eu-west", "us-central")[workflow_index % 3],
            "labels": list(workflow["labels"]),
            "synthetic_workload": True,
        },
        "history_digest": hashlib.sha256(event_material.encode("ascii")).hexdigest(),
    }
    return validate_state(state)


def build_sessions() -> tuple[tuple[JsonMap, ...], ...]:
    sessions = tuple(
        tuple(build_state(workflow_index, variant, turn) for turn in range(TURNS_PER_SESSION))
        for workflow_index in range(len(WORKFLOWS))
        for variant in range(SESSIONS_PER_WORKFLOW)
    )
    if len(sessions) != len(WORKFLOWS) * SESSIONS_PER_WORKFLOW:
        raise RuntimeError("session count changed")
    return sessions


def corpus_digest(sessions: Sequence[Sequence[Mapping[str, Any]]]) -> str:
    digest = hashlib.sha256()
    for session in sessions:
        for state in session:
            raw = _canonical_json(state).encode("utf-8")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
    return digest.hexdigest()


def _path_sort_key(path: PathTuple) -> tuple[int, tuple[str, ...]]:
    return (len(path), path)


def _diff(base: JsonValue, target: JsonValue, path: PathTuple, deletes: list[PathTuple], sets: list[tuple[PathTuple, JsonValue]]) -> None:
    if base == target:
        return
    if isinstance(base, dict) and isinstance(target, dict):
        for key in sorted(set(base) - set(target)):
            deletes.append(path + (key,))
        for key in sorted(target):
            if key not in base:
                sets.append((path + (key,), copy.deepcopy(target[key])))
            else:
                _diff(base[key], target[key], path + (key,), deletes, sets)
        return
    sets.append((path, copy.deepcopy(target)))


def build_delta(base: Mapping[str, Any], target: Mapping[str, Any]) -> JsonMap:
    validate_state(base)
    validate_state(target)
    if base["session_id"] != target["session_id"]:
        raise DeltaError("delta states belong to different sessions")
    deletes: list[PathTuple] = []
    sets: list[tuple[PathTuple, JsonValue]] = []
    _diff(base, target, (), deletes, sets)
    deletes.sort(key=_path_sort_key)
    sets.sort(key=lambda item: _path_sort_key(item[0]))
    patch = {
        "delete": [list(path) for path in deletes],
        "set": [[list(path), value] for path, value in sets],
    }
    validate_patch(patch)
    return patch


def _proper_prefix(left: PathTuple, right: PathTuple) -> bool:
    return len(left) < len(right) and right[: len(left)] == left


def validate_patch(value: JsonValue) -> JsonMap:
    _walk_json(value)
    if not isinstance(value, dict) or set(value) != {"delete", "set"}:
        raise DeltaError("patch must contain exactly delete and set")
    if not isinstance(value["delete"], list) or not isinstance(value["set"], list):
        raise DeltaError("patch operation collections must be lists")
    if len(value["delete"]) + len(value["set"]) > MAX_PATCH_OPERATIONS:
        raise DeltaError("patch contains too many operations")
    deletes: list[PathTuple] = []
    for raw_path in value["delete"]:
        if not isinstance(raw_path, list) or not raw_path:
            raise DeltaError("delete paths must be non-empty lists")
        if len(raw_path) > MAX_PATH_COMPONENTS or any(
            not isinstance(component, str) or not component for component in raw_path
        ):
            raise DeltaError("delete path is invalid")
        deletes.append(tuple(raw_path))
    sets: list[tuple[PathTuple, JsonValue]] = []
    for operation in value["set"]:
        if not isinstance(operation, list) or len(operation) != 2:
            raise DeltaError("set operation must be [path, value]")
        raw_path, replacement = operation
        if not isinstance(raw_path, list) or not raw_path:
            raise DeltaError("set paths must be non-empty lists")
        if len(raw_path) > MAX_PATH_COMPONENTS or any(
            not isinstance(component, str) or not component for component in raw_path
        ):
            raise DeltaError("set path is invalid")
        sets.append((tuple(raw_path), replacement))
    if deletes != sorted(deletes, key=_path_sort_key):
        raise DeltaError("delete paths are not canonical")
    if sets != sorted(sets, key=lambda item: _path_sort_key(item[0])):
        raise DeltaError("set paths are not canonical")
    paths = deletes + [path for path, _ in sets]
    if len(paths) != len(set(paths)):
        raise DeltaError("patch contains duplicate paths")
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _proper_prefix(left, right) or _proper_prefix(right, left):
                raise DeltaError("patch paths overlap")
    return copy.deepcopy(value)


def _resolve_parent(root: JsonMap, path: PathTuple, *, create: bool) -> tuple[JsonMap, str]:
    if not path:
        raise DeltaError("root replacement is not permitted")
    current: JsonValue = root
    for component in path[:-1]:
        if not isinstance(current, dict):
            raise DeltaError("patch path crosses a non-object value")
        if component not in current:
            if not create:
                raise DeltaError("patch path does not exist")
            current[component] = {}
        current = current[component]
    if not isinstance(current, dict):
        raise DeltaError("patch parent is not an object")
    return current, path[-1]


def apply_delta(base: Mapping[str, Any], patch: Mapping[str, Any]) -> JsonMap:
    canonical_base = validate_state(base)
    canonical_patch = validate_patch(patch)
    result = copy.deepcopy(canonical_base)
    for raw_path in canonical_patch["delete"]:
        path = tuple(raw_path)
        parent, key = _resolve_parent(result, path, create=False)
        if key not in parent:
            raise DeltaError("delete target does not exist")
        del parent[key]
    for raw_path, replacement in canonical_patch["set"]:
        path = tuple(raw_path)
        parent, key = _resolve_parent(result, path, create=False)
        parent[key] = copy.deepcopy(replacement)
    recovered = validate_state(result)
    if build_delta(canonical_base, recovered) != canonical_patch:
        raise DeltaError("patch is not the canonical minimal delta")
    return recovered


def state_digest(state: Mapping[str, Any]) -> bytes:
    canonical = validate_state(state)
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).digest()[:DIGEST_BYTES]


def _record_tag(mode: str, session_bytes: bytes, sequence: int, base_digest: bytes, payload_bytes: bytes, key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 16:
        raise DeltaError("integrity key must contain at least 16 bytes")
    return hmac.new(
        key,
        DOMAIN
        + mode.encode("ascii")
        + session_bytes
        + sequence.to_bytes(4, "big")
        + base_digest
        + payload_bytes,
        hashlib.sha256,
    ).digest()[:TAG_BYTES]


def encode_record(mode: str, session_id: str, sequence: int, base_digest: bytes, payload: str, *, key: bytes = TEST_KEY) -> str:
    if mode not in MODES:
        raise DeltaError("record mode is unknown")
    try:
        session = uuid.UUID(session_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise DeltaError("record session is not a UUID") from exc
    if str(session) != session_id:
        raise DeltaError("record session UUID is not canonical")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or not 0 <= sequence < 2**32:
        raise DeltaError("record sequence is not unsigned 32-bit")
    if not isinstance(base_digest, bytes) or len(base_digest) != DIGEST_BYTES:
        raise DeltaError("record base digest has the wrong width")
    if mode == "F" and base_digest != ZERO_DIGEST:
        raise DeltaError("full record must use the zero base digest")
    if not isinstance(payload, str) or not payload:
        raise DeltaError("record payload must be non-empty text")
    payload_bytes = payload.encode("utf-8")
    if HEADER_CHARACTERS + len(payload_bytes) > MAX_RECORD_BYTES:
        raise DeltaError("record exceeds the byte limit")
    tag = _record_tag(mode, session.bytes, sequence, base_digest, payload_bytes, key)
    return (
        PREFIX
        + mode
        + session.hex
        + f"{sequence:08x}"
        + _b64url(base_digest)
        + _b64url(tag)
        + ":"
        + payload
    )


def parse_record(text: str, *, key: bytes = TEST_KEY) -> ParsedRecord:
    if not isinstance(text, str) or len(text) <= HEADER_CHARACTERS:
        raise DeltaError("record is truncated")
    if len(text.encode("utf-8")) > MAX_RECORD_BYTES:
        raise DeltaError("record exceeds the byte limit")
    if not text.startswith(PREFIX) or text[2] not in MODES:
        raise DeltaError("record prefix or mode is unknown")
    mode = text[2]
    cursor = 3
    session_hex = text[cursor : cursor + SESSION_HEX_CHARACTERS]
    cursor += SESSION_HEX_CHARACTERS
    if len(session_hex) != SESSION_HEX_CHARACTERS or any(
        character not in "0123456789abcdef" for character in session_hex
    ):
        raise DeltaError("record session is not canonical lowercase hex")
    session = uuid.UUID(hex=session_hex)
    sequence_text = text[cursor : cursor + SEQUENCE_HEX_CHARACTERS]
    cursor += SEQUENCE_HEX_CHARACTERS
    if len(sequence_text) != SEQUENCE_HEX_CHARACTERS or any(
        character not in "0123456789abcdef" for character in sequence_text
    ):
        raise DeltaError("record sequence is not canonical lowercase hex")
    sequence = int(sequence_text, 16)
    digest_text = text[cursor : cursor + DIGEST_CHARACTERS]
    cursor += DIGEST_CHARACTERS
    base_digest = _b64url_decode(digest_text, DIGEST_BYTES, "base digest")
    tag_text = text[cursor : cursor + TAG_CHARACTERS]
    cursor += TAG_CHARACTERS
    supplied_tag = _b64url_decode(tag_text, TAG_BYTES, "authentication tag")
    if cursor >= len(text) or text[cursor] != ":":
        raise DeltaError("record header terminator is missing")
    payload = text[cursor + 1 :]
    if not payload:
        raise DeltaError("record payload is empty")
    payload_bytes = payload.encode("utf-8")
    expected_tag = _record_tag(
        mode, session.bytes, sequence, base_digest, payload_bytes, key
    )
    if not hmac.compare_digest(supplied_tag, expected_tag):
        raise DeltaError("record authentication failed")
    if mode == "F" and base_digest != ZERO_DIGEST:
        raise DeltaError("full record has a nonzero base digest")
    return ParsedRecord(mode, str(session), sequence, base_digest, payload)


def encode_full(state: Mapping[str, Any], *, key: bytes = TEST_KEY) -> str:
    canonical = validate_state(state)
    return encode_record(
        "F",
        canonical["session_id"],
        canonical["turn"],
        ZERO_DIGEST,
        _canonical_json(canonical),
        key=key,
    )


def encode_delta(base: Mapping[str, Any], target: Mapping[str, Any], *, key: bytes = TEST_KEY) -> str:
    canonical_base = validate_state(base)
    canonical_target = validate_state(target)
    patch = build_delta(canonical_base, canonical_target)
    return encode_record(
        "D",
        canonical_target["session_id"],
        canonical_target["turn"],
        state_digest(canonical_base),
        _canonical_json(patch),
        key=key,
    )


class SessionDecoder:
    """Strict single-session decoder with explicit checkpoint resynchronization."""

    def __init__(self, session_id: str, *, key: bytes = TEST_KEY):
        try:
            canonical = str(uuid.UUID(session_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DeltaError("decoder session is not a UUID") from exc
        if canonical != session_id:
            raise DeltaError("decoder session UUID is not canonical")
        if not isinstance(key, bytes) or len(key) < 16:
            raise DeltaError("integrity key must contain at least 16 bytes")
        self.session_id = session_id
        self.key = key
        self.current: JsonMap | None = None
        self.next_sequence = 0

    def open(self, record: str, *, allow_checkpoint_resync: bool = False) -> JsonMap:
        parsed = parse_record(record, key=self.key)
        if parsed.session_id != self.session_id:
            raise DeltaError("record belongs to a different session")
        if parsed.sequence != self.next_sequence:
            if not (
                allow_checkpoint_resync
                and parsed.mode == "F"
                and parsed.sequence > self.next_sequence
            ):
                raise DeltaError("record sequence mismatch")
        if parsed.mode == "F":
            value = _parse_canonical_json(parsed.payload)
            state = validate_state(value)
        else:
            if self.current is None:
                raise DeltaError("delta record has no installed base state")
            if parsed.base_digest != state_digest(self.current):
                raise DeltaError("delta base digest mismatch")
            patch = _parse_canonical_json(parsed.payload)
            state = apply_delta(self.current, patch)
        if state["session_id"] != self.session_id:
            raise DeltaError("decoded state belongs to a different session")
        if state["turn"] != parsed.sequence:
            raise DeltaError("decoded state turn does not match the record sequence")
        self.current = state
        self.next_sequence = parsed.sequence + 1
        return copy.deepcopy(state)


def _forced_checkpoint(sequence: int, interval: int) -> bool:
    if interval not in CHECKPOINT_INTERVALS:
        raise ValueError("checkpoint interval is not frozen")
    return sequence == 0 or sequence == TURNS_PER_SESSION - 1 or sequence % interval == 0


def _token_count(
    tokenizer: TokenizerProfile, text: str, *, use_cache: bool
) -> int:
    if not use_cache:
        return tokenizer.count(text)
    key = (tokenizer.key, text)
    cached = _TOKEN_COUNT_CACHE.get(key)
    if cached is None:
        cached = tokenizer.count(text)
        _TOKEN_COUNT_CACHE[key] = cached
    return cached


def build_plan(
    states: Sequence[Mapping[str, Any]],
    tokenizer: TokenizerProfile,
    interval: int,
    *,
    use_count_cache: bool = True,
) -> Plan:
    if len(states) != TURNS_PER_SESSION:
        raise ValueError("session length changed")
    canonical_states = tuple(validate_state(state) for state in states)
    session_id = canonical_states[0]["session_id"]
    if any(state["session_id"] != session_id for state in canonical_states):
        raise ValueError("plan states span multiple sessions")
    full_records = tuple(encode_full(state) for state in canonical_states)
    records: list[str] = []
    modes: list[str] = []
    forced_full = fallback_full = delta_wins = 0
    for index, state in enumerate(canonical_states):
        full = full_records[index]
        if _forced_checkpoint(index, interval):
            records.append(full)
            modes.append("F")
            forced_full += 1
            continue
        delta = encode_delta(canonical_states[index - 1], state)
        full_tokens = _token_count(tokenizer, full, use_cache=use_count_cache)
        delta_tokens = _token_count(tokenizer, delta, use_cache=use_count_cache)
        if delta_tokens < full_tokens:
            records.append(delta)
            modes.append("D")
            delta_wins += 1
        else:
            records.append(full)
            modes.append("F")
            fallback_full += 1
    raw_json = tuple(_canonical_json(state) for state in canonical_states)
    return Plan(
        tokenizer.key,
        interval,
        session_id,
        tuple(records),
        tuple(modes),
        sum(
            _token_count(tokenizer, record, use_cache=use_count_cache)
            for record in records
        ),
        sum(len(record.encode("utf-8")) for record in records),
        sum(
            _token_count(tokenizer, record, use_cache=use_count_cache)
            for record in full_records
        ),
        sum(len(record.encode("utf-8")) for record in full_records),
        sum(
            _token_count(tokenizer, text, use_cache=use_count_cache)
            for text in raw_json
        ),
        sum(len(text.encode("utf-8")) for text in raw_json),
        forced_full,
        fallback_full,
        delta_wins,
        _token_count(tokenizer, full_records[0], use_cache=use_count_cache),
        len(full_records[0].encode("utf-8")),
    )


def build_byte_plan(states: Sequence[Mapping[str, Any]], interval: int) -> tuple[tuple[str, ...], tuple[str, ...], int, int, int]:
    canonical_states = tuple(validate_state(state) for state in states)
    records: list[str] = []
    modes: list[str] = []
    forced = fallback = wins = 0
    for index, state in enumerate(canonical_states):
        full = encode_full(state)
        if _forced_checkpoint(index, interval):
            records.append(full)
            modes.append("F")
            forced += 1
            continue
        delta = encode_delta(canonical_states[index - 1], state)
        if len(delta.encode("utf-8")) < len(full.encode("utf-8")):
            records.append(delta)
            modes.append("D")
            wins += 1
        else:
            records.append(full)
            modes.append("F")
            fallback += 1
    return tuple(records), tuple(modes), forced, fallback, wins


def decode_plan(plan: Plan) -> tuple[JsonMap, ...]:
    decoder = SessionDecoder(plan.session_id)
    return tuple(decoder.open(record) for record in plan.records)


def _aggregate_plans(plans: Sequence[Plan], profile: TokenizerProfile, interval: int, sessions: Sequence[Sequence[Mapping[str, Any]]]) -> Aggregate:
    exact = 0
    deterministic = 0
    for plan, states in zip(plans, sessions, strict=True):
        exact += sum(left == right for left, right in zip(decode_plan(plan), states, strict=True))
        second = build_plan(states, profile, interval)
        deterministic += sum(left == right for left, right in zip(plan.records, second.records, strict=True))
    return Aggregate(
        profile.key,
        profile.display_name,
        interval,
        sum(len(plan.records) for plan in plans),
        sum(plan.token_total for plan in plans),
        sum(plan.byte_total for plan in plans),
        sum(plan.full_baseline_tokens for plan in plans),
        sum(plan.full_baseline_bytes for plan in plans),
        sum(plan.raw_json_tokens for plan in plans),
        sum(plan.raw_json_bytes for plan in plans),
        sum(plan.forced_full for plan in plans),
        sum(plan.fallback_full for plan in plans),
        sum(plan.delta_wins for plan in plans),
        sum(plan.cold_checkpoint_tokens for plan in plans),
        sum(plan.cold_checkpoint_bytes for plan in plans),
        exact,
        deterministic,
    )


def _aggregate_byte_plans(sessions: Sequence[Sequence[Mapping[str, Any]]], interval: int) -> ByteAggregate:
    selected_bytes = full_bytes = forced = fallback = wins = exact = deterministic = 0
    records_total = 0
    for states in sessions:
        records, _, session_forced, session_fallback, session_wins = build_byte_plan(states, interval)
        second, _, _, _, _ = build_byte_plan(states, interval)
        decoder = SessionDecoder(states[0]["session_id"])
        recovered = tuple(decoder.open(record) for record in records)
        exact += sum(left == right for left, right in zip(recovered, states, strict=True))
        deterministic += sum(left == right for left, right in zip(records, second, strict=True))
        selected_bytes += sum(len(record.encode("utf-8")) for record in records)
        full_bytes += sum(len(encode_full(state).encode("utf-8")) for state in states)
        forced += session_forced
        fallback += session_fallback
        wins += session_wins
        records_total += len(records)
    return ByteAggregate(
        interval,
        records_total,
        selected_bytes,
        full_bytes,
        forced,
        fallback,
        wins,
        exact,
        deterministic,
    )


def _flip_character(text: str, index: int, alphabet: str = "XY") -> str:
    replacement = alphabet[0] if text[index] != alphabet[0] else alphabet[1]
    return text[:index] + replacement + text[index + 1 :]


def _seed_before(states: Sequence[Mapping[str, Any]], index: int) -> SessionDecoder:
    decoder = SessionDecoder(states[0]["session_id"])
    if index > 0:
        decoder.open(encode_full(states[index - 1]), allow_checkpoint_resync=True)
    return decoder


def run_fault_campaign(sessions: Sequence[Sequence[Mapping[str, Any]]], profile: TokenizerProfile) -> FaultResults:
    plans = tuple(build_plan(states, profile, REPRESENTATIVE_INTERVAL) for states in sessions)
    integrity_attempted = integrity_rejected = 0
    reset_attempted = reset_rejected = checkpoints = 0
    replay_attempted = replay_rejected = 0
    order_attempted = order_rejected = 0
    loss_attempted = post_loss_rejected = recovered = 0
    maximum_skipped = 0
    for states, plan in zip(sessions, plans, strict=True):
        for index, record in enumerate(plan.records):
            parsed = parse_record(record)
            tag_start = 3 + SESSION_HEX_CHARACTERS + SEQUENCE_HEX_CHARACTERS + DIGEST_CHARACTERS
            payload_start = HEADER_CHARACTERS
            mutations = (
                record[:2] + ("X" if record[2] != "X" else "Y") + record[3:],
                _flip_character(record, 3, "01"),
                _flip_character(record, 3 + SESSION_HEX_CHARACTERS, "01"),
                _flip_character(record, 3 + SESSION_HEX_CHARACTERS + SEQUENCE_HEX_CHARACTERS, "AB"),
                _flip_character(record, tag_start, "AB"),
                _flip_character(record, payload_start, "[]"),
            )
            for mutation in mutations:
                integrity_attempted += 1
                try:
                    parse_record(mutation)
                except DeltaError:
                    integrity_rejected += 1
            if parsed.mode == "D":
                reset_attempted += 1
                try:
                    SessionDecoder(plan.session_id).open(record, allow_checkpoint_resync=True)
                except DeltaError:
                    reset_rejected += 1
            else:
                decoder = SessionDecoder(plan.session_id)
                if decoder.open(record, allow_checkpoint_resync=True) == states[index]:
                    checkpoints += 1
            decoder = _seed_before(states, index)
            decoder.open(record)
            replay_attempted += 1
            try:
                decoder.open(record)
            except DeltaError:
                replay_rejected += 1
        for index in range(len(plan.records) - 1):
            decoder = _seed_before(states, index)
            order_attempted += 1
            try:
                decoder.open(plan.records[index + 1])
            except DeltaError:
                order_rejected += 1
            decoder.open(plan.records[index])
            if decoder.open(plan.records[index + 1]) != states[index + 1]:
                raise RuntimeError("ordered recovery changed state")

            decoder = _seed_before(states, index)
            loss_attempted += 1
            try:
                decoder.open(plan.records[index + 1])
            except DeltaError:
                post_loss_rejected += 1
            checkpoint_index = next(
                candidate
                for candidate in range(index + 1, len(plan.records))
                if plan.modes[candidate] == "F"
            )
            if decoder.open(
                plan.records[checkpoint_index], allow_checkpoint_resync=True
            ) == states[checkpoint_index]:
                recovered += 1
            maximum_skipped = max(maximum_skipped, checkpoint_index - index - 1)
    return FaultResults(
        sum(len(plan.records) for plan in plans),
        integrity_attempted,
        integrity_rejected,
        reset_attempted,
        reset_rejected,
        checkpoints,
        replay_attempted,
        replay_rejected,
        order_attempted,
        order_rejected,
        loss_attempted,
        post_loss_rejected,
        recovered,
        maximum_skipped,
    )


def _measure_call(function: Callable[[], Any]) -> float:
    started = time.perf_counter_ns()
    function()
    return (time.perf_counter_ns() - started) / 1_000


def measure_latency(sessions: Sequence[Sequence[Mapping[str, Any]]], profile: TokenizerProfile) -> LatencyResults:
    full_samples: list[float] = []
    adaptive_samples: list[float] = []
    decode_samples: list[float] = []
    for states in sessions:
        plan = build_plan(states, profile, REPRESENTATIVE_INTERVAL)
        full_samples.append(
            _measure_call(
                lambda states=states: tuple(
                    profile.count(encode_full(state)) for state in states
                )
            )
        )
        adaptive_samples.append(
            _measure_call(
                lambda states=states: build_plan(
                    states,
                    profile,
                    REPRESENTATIVE_INTERVAL,
                    use_count_cache=False,
                )
            )
        )
        decode_samples.append(_measure_call(lambda plan=plan: decode_plan(plan)))
    return LatencyResults(
        len(full_samples),
        statistics.median(full_samples),
        _nearest_rank(full_samples, 0.95),
        statistics.median(adaptive_samples),
        _nearest_rank(adaptive_samples, 0.95),
        statistics.median(decode_samples),
        _nearest_rank(decode_samples, 0.95),
    )


def verify_profiles(profiles: Sequence[TokenizerProfile]) -> None:
    if tuple(profile.key for profile in profiles) != tuple(EXPECTED_TOKENIZER_FINGERPRINTS):
        raise RuntimeError("the four pinned tokenizers are required in frozen order")
    for profile in profiles:
        if profile.fingerprint != EXPECTED_TOKENIZER_FINGERPRINTS[profile.key]:
            raise RuntimeError(f"pinned tokenizer changed: {profile.key}")


def _matrix_digest(aggregates: Sequence[Aggregate], byte_aggregates: Sequence[ByteAggregate], fault: FaultResults) -> str:
    value = {
        "aggregates": [
            {
                "tokenizer": item.tokenizer_key,
                "interval": item.interval,
                "records": item.records,
                "token_total": item.token_total,
                "byte_total": item.byte_total,
                "full_baseline_tokens": item.full_baseline_tokens,
                "full_baseline_bytes": item.full_baseline_bytes,
                "raw_json_tokens": item.raw_json_tokens,
                "raw_json_bytes": item.raw_json_bytes,
                "forced_full": item.forced_full,
                "fallback_full": item.fallback_full,
                "delta_wins": item.delta_wins,
                "cold_checkpoint_tokens": item.cold_checkpoint_tokens,
                "cold_checkpoint_bytes": item.cold_checkpoint_bytes,
                "exact": item.exact,
                "deterministic": item.deterministic,
            }
            for item in aggregates
        ],
        "byte_aggregates": [item.__dict__ for item in byte_aggregates],
        "fault": fault.__dict__,
    }
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def collect_study(asset_root: Path | None = None) -> Study:
    _TOKEN_COUNT_CACHE.clear()
    profiles = tuple(load_tokenizer_profiles(asset_root or default_asset_root()))
    verify_profiles(profiles)
    sessions = build_sessions()
    observed_corpus = corpus_digest(sessions)
    if EXPECTED_CORPUS_DIGEST != "pending" and observed_corpus != EXPECTED_CORPUS_DIGEST:
        raise RuntimeError("frozen correlated-session corpus changed")
    aggregates: list[Aggregate] = []
    for profile in profiles:
        for interval in CHECKPOINT_INTERVALS:
            plans = tuple(build_plan(states, profile, interval) for states in sessions)
            aggregates.append(
                _aggregate_plans(plans, profile, interval, sessions)
            )
    byte_aggregates = tuple(
        _aggregate_byte_plans(sessions, interval) for interval in CHECKPOINT_INTERVALS
    )
    fault = run_fault_campaign(sessions, profiles[0])
    latency = measure_latency(sessions, profiles[0])
    matrix = _matrix_digest(aggregates, byte_aggregates, fault)
    if EXPECTED_MATRIX_DIGEST != "pending" and matrix != EXPECTED_MATRIX_DIGEST:
        raise RuntimeError("frozen v0.9 measurement matrix changed")
    return Study(
        sessions,
        profiles,
        tuple(aggregates),
        byte_aggregates,
        fault,
        latency,
        matrix,
    )


def _percent(value: float) -> str:
    return f"{value:.2f}%"


def _source_digest(name: str) -> str:
    path = ROOT / name
    return _sha256_file(path) if path.is_file() else "missing"


def render_report(study: Study) -> str:
    sessions = study.sessions
    total_records = sum(len(session) for session in sessions)
    representative = {
        item.tokenizer_key: item
        for item in study.aggregates
        if item.interval == REPRESENTATIVE_INTERVAL
    }
    exact_total = sum(item.exact for item in study.aggregates)
    deterministic_total = sum(item.deterministic for item in study.aggregates)
    measurement_total = sum(item.records for item in study.aggregates)
    token_rows = []
    for item in study.aggregates:
        token_rows.append(
            f"| {item.tokenizer_name} | {item.interval} | {item.full_baseline_tokens:,} | "
            f"{item.token_total:,} | {_percent(item.token_saving_percent)} | "
            f"{item.forced_full}/{item.fallback_full}/{item.delta_wins} | "
            f"{item.cold_checkpoint_tokens:,} ({_percent(item.cold_checkpoint_tokens / item.token_total * 100)}) |"
        )
    byte_rows = []
    for item in study.byte_aggregates:
        byte_rows.append(
            f"| {item.interval} | {item.full_bytes:,} | {item.selected_bytes:,} | "
            f"{_percent(item.saving_percent)} | {item.forced_full}/{item.fallback_full}/{item.delta_wins} |"
        )
    representative_rows = []
    for profile in study.profiles:
        item = representative[profile.key]
        envelope_excess = (item.full_baseline_tokens - item.raw_json_tokens) * 100 / item.raw_json_tokens
        representative_rows.append(
            f"| {item.tokenizer_name} | {item.raw_json_tokens:,} | {item.full_baseline_tokens:,} | "
            f"+{envelope_excess:.2f}% | {item.token_total:,} | {_percent(item.token_saving_percent)} |"
        )
    fault = study.fault_results
    latency = study.latency
    return f"""# Checkpointed semantic delta v0.9 development experiment

Status: bounded offline serialization evidence over a synthetic, scenario-shaped correlated workload; not external generalization, model comprehension, task utility, adoption, energy, or state of the art  
Date: 2026-08-20  
Format: `{FORMAT}`

## Outcome

Across {len(sessions)} sessions and {total_records:,} state snapshots, the matched full-state baseline and the checkpointed semantic-delta candidate used the same standalone session, sequence, base-state, and HMAC framing. The selector admitted a delta only when its **complete record** used strictly fewer tokens than the full fallback for the negotiated receiver tokenizer.

At the predeclared representative checkpoint interval of {REPRESENTATIVE_INTERVAL}, aggregate token savings versus the matched full-record baseline were **{min(item.token_saving_percent for item in representative.values()):.2f}% to {max(item.token_saving_percent for item in representative.values()):.2f}%** across the four pinned tokenizers. These favorable numbers are expected to depend strongly on correlation: the workload deliberately models evolving shared state, and it was authored in this repository. They are not evidence that arbitrary agent messages compress by this amount.

The interval-1 control is full-only and therefore saves exactly zero. Every interval retains the unfavorable cost of full cold bootstrap and periodic checkpoints. The result is a serialization bound: no language model read or produced a delta, and no safely completed task was measured.

## Frozen workload and protocol

- Workflows: incident triage, inventory reservation, document review, and route planning.
- Sessions: {len(sessions)} ({SESSIONS_PER_WORKFLOW} deterministic variants per workflow).
- State snapshots: {total_records:,} ({TURNS_PER_SESSION} per session).
- Workload SHA-256: `{corpus_digest(sessions)}`.
- Checkpoint intervals: `{', '.join(str(value) for value in CHECKPOINT_INTERVALS)}` records; the final record is also forced full.
- Deterministic matrix SHA-256: `{study.matrix_digest}`.
- Standalone header: {HEADER_CHARACTERS} ASCII characters per record before payload.
- Integrity: HMAC-SHA-256 truncated to 128 bits over mode, 128-bit session UUID, 32-bit sequence, 128-bit base-state digest, and exact UTF-8 payload bytes.
- Delta: canonical sorted set/delete operations over object paths; changed arrays are replaced as complete values.
- Selection: forced checkpoints use full state; otherwise choose delta only on a strict complete-token win, with full state winning ties.
- Cold contract: decoder software and the record contract are installed, but session state is absent. The first full checkpoint, all headers, periodic checkpoints, and the final checkpoint are charged. Software installation, key exchange, transport packets, and prompt-teaching the grammar are outside this experiment.

## Complete standalone receiver-token accounting

`Full / fallback / delta` reports forced checkpoints, non-forced full fallbacks, and strict delta wins. Cold checkpoint tokens are the sum of the first full record of every session and are already included in selected total.

| Receiver tokenizer | Interval | Matched full tokens | Selected tokens | Saving | Full / fallback / delta | Cold checkpoint tokens (share) |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(token_rows)}

The selector has a mechanical no-regression guarantee against the matched full record for every non-forced message. That guarantee is conditional on exact receiver-tokenizer negotiation and does not include any model response or repair turn.

## Representative interval-8 framing sensitivity

Raw JSON omits session framing and authentication and is not a matched protocol baseline. It is retained to show the material cost of the standalone envelope rather than hiding it.

| Receiver tokenizer | Raw full-state JSON | Matched full records | Envelope excess | Interval-8 selected | Saving vs matched full |
|---|---:|---:|---:|---:|---:|
{chr(10).join(representative_rows)}

## Byte-only selector sensitivity

This separate selector minimizes complete UTF-8 bytes instead of receiver tokens. It uses the identical checkpoint and integrity contract. It is not the byte count of any one tokenizer-specific plan.

| Interval | Matched full bytes | Selected bytes | Saving | Full / fallback / delta |
|---:|---:|---:|---:|---:|
{chr(10).join(byte_rows)}

## Exactness, determinism, and state-fault behavior

- Tokenizer-specific plan recovery: `{exact_total:,}/{measurement_total:,}` exact snapshots.
- Tokenizer-specific canonical reselection: `{deterministic_total:,}/{measurement_total:,}` byte-identical records.
- Byte-specific plan recovery and determinism: `{sum(item.exact for item in study.byte_aggregates):,}/{sum(item.records for item in study.byte_aggregates):,}` and `{sum(item.deterministic for item in study.byte_aggregates):,}/{sum(item.records for item in study.byte_aggregates):,}`.
- Representative interval-8 mutation campaign: `{fault.integrity_rejected:,}/{fault.integrity_attempted:,}` changes to mode, session, sequence, base digest, tag, or payload rejected before state acceptance.
- Fresh-decoder delta rejection: `{fault.reset_delta_rejected:,}/{fault.reset_delta_attempted:,}`; independently decodable full checkpoints: `{fault.independent_checkpoints:,}`.
- Replay rejection: `{fault.replay_rejected:,}/{fault.replay_attempted:,}`.
- Adjacent out-of-order rejection: `{fault.out_of_order_rejected:,}/{fault.out_of_order_attempted:,}`; ordered replay after rejection still recovered the exact state.
- One-record loss trials: `{fault.post_loss_rejected:,}/{fault.loss_attempted:,}` immediate post-gap records rejected and `{fault.checkpoint_recovered:,}/{fault.loss_attempted:,}` later full checkpoints resynchronized the current state. The maximum number of unavailable intervening snapshots was `{fault.maximum_skipped_records}` at interval {REPRESENTATIVE_INTERVAL}.

Checkpoint resynchronization recovers current state, not missing historical snapshots. An application requiring every missed intermediate state must retransmit or replay them; that traffic is not silently counted as recovered.

## Current Python path latency

Values are whole 32-snapshot sessions over {latency.samples} scenario sessions on `{platform.python_implementation()} {platform.python_version()}` / `{platform.platform()}`. Full encode counts authenticated full records. Adaptive encode constructs full and delta candidates and performs tokenizer counting; paths do unequal work. The descriptive p95 is a nearest-rank sample statistic, not a confidence bound.

| Path | p50 | p95 |
|---|---:|---:|
| Matched full encode + cl100k count | {latency.full_encode_p50_us:,.1f} us | {latency.full_encode_p95_us:,.1f} us |
| Interval-8 adaptive encode/select + cl100k count | {latency.adaptive_encode_p50_us:,.1f} us | {latency.adaptive_encode_p95_us:,.1f} us |
| Interval-8 authenticated decode | {latency.adaptive_decode_p50_us:,.1f} us | {latency.adaptive_decode_p95_us:,.1f} us |

## Interpretation boundary

- The workload is synthetic and deliberately correlated. It repeats stable objectives, constraints, participants, and growing evidence/decision indexes while changing progress and current events. This makes it suitable for testing the stated state-sync hypothesis and unsuitable for estimating traffic-wide savings.
- The baseline is full canonical state under the same record contract. This is not a claim against compressed streams, general-purpose binary codecs, KV-cache methods, latent communication, or published multi-agent systems.
- Exact reconstruction proves codec behavior, not that a model understands the compact text. If a deterministic adapter expands every delta before model input, network text is reduced but receiver model-input tokens are not. If the model consumes deltas directly, task success and repair cost remain unmeasured.
- A receiver must retain the exact preceding state and its digest. Memory, cache invalidation, multi-device synchronization, key rotation, and concurrent branch merging are not measured.
- Loss and reordering fail closed. Checkpoints bound current-state resynchronization but do not restore omitted history; retransmission, packet headers, congestion control, TLS, and denial-of-service resistance are outside scope.
- The public deterministic HMAC key is a test fixture. Deployment requires an authenticated key-establishment protocol and authorization policy.
- Token counts exclude chat templates, BOS/EOS, prompts, model output, tool calls, repair turns, and hosted billing transformations. Token reduction does not directly establish lower energy, latency, memory, money, or emissions.
- There is no external holdout, model call, task benchmark, independent reproduction, adoption measurement, or state-of-the-art claim.

## Reproduction identity

- Tokenizer packages are pinned by the repository research environment; exact vocabulary fingerprints are verified at runtime.
- `cl100k_base`: `{EXPECTED_TOKENIZER_FINGERPRINTS['cl100k_base']}`.
- `o200k_base`: `{EXPECTED_TOKENIZER_FINGERPRINTS['o200k_base']}`.
- `Qwen2.5-7B-Instruct tokenizer`: `{EXPECTED_TOKENIZER_FINGERPRINTS['qwen2_5_7b_instruct']}`.
- `Mistral-7B-Instruct-v0.3 tokenizer`: `{EXPECTED_TOKENIZER_FINGERPRINTS['mistral_7b_instruct_v03']}`.
- Implementation SHA-256: `{_source_digest('urusilla_session_delta_v09.py')}`.
- Test SHA-256: `{_source_digest('test_urusilla_session_delta_v09.py')}`.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python \\
  urusilla_session_delta_v09.py --output SESSION_DELTA_V09_RESULTS.md
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m unittest -v \\
  test_urusilla_session_delta_v09.py
```
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, default=default_asset_root())
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    study = collect_study(args.assets_dir)
    report = render_report(study)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
