"""A deterministic append-only ledger for non-financial contribution points.

The module is a local research state machine, not a blockchain or payment
system. It intentionally has no wallet, networking, transfer, approval,
redemption, or future-conversion surface.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


LEDGER_SCHEMA_VERSION = "urusilla-contribution-ledger/0.1"
SNAPSHOT_SCHEMA_VERSION = "urusilla-contribution-ledger-snapshot/0.1"
EVENT_HASH_DOMAIN = b"urusilla:contribution-ledger:event:v1\x00"
CONTRIBUTION_HASH_DOMAIN = b"urusilla:contribution-ledger:contribution:v1\x00"
MERKLE_LEAF_DOMAIN = b"urusilla:contribution-ledger:merkle-leaf:v1\x00"
MERKLE_NODE_DOMAIN = b"urusilla:contribution-ledger:merkle-node:v1\x00"
MERKLE_EMPTY_DOMAIN = b"urusilla:contribution-ledger:merkle-empty:v1\x00"
MAX_POINTS = 2**63 - 1
MAX_ARTIFACT_DIGESTS = 64

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_REASON_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN_PRIVACY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "conversation",
        "conversation_text",
        "email",
        "email_address",
        "message_content",
        "password",
        "private_key",
        "prompt",
        "raw_message",
        "raw_prompt",
        "secret",
        "secrets",
        "user_id",
    }
)

_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_id",
        "seq",
        "prev_event_id",
        "event_type",
        "payload",
        "event_id",
    }
)

_PAYLOAD_FIELDS = {
    "epoch_opened": frozenset({"epoch_id", "budget_points", "policy_digest"}),
    "contribution_registered": frozenset(
        {
            "epoch_id",
            "contribution_id",
            "contributor_ref",
            "contribution_class",
            "commit_digest",
            "claim_digest",
            "artifact_digests",
        }
    ),
    "award_granted": frozenset(
        {"epoch_id", "contribution_id", "points", "decision_digest"}
    ),
    "award_revoked": frozenset(
        {"award_event_id", "reason_code", "decision_digest"}
    ),
    "correction_recorded": frozenset(
        {"target_event_id", "reason_code", "corrected_record_digest"}
    ),
}


class LedgerValidationError(ValueError):
    """A fail-closed validation error with a stable machine reason code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise LedgerValidationError(code, message)


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _fail("invalid_json", f"{path} is not a valid UTF-8 string")
        return
    if type(value) is int:
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("invalid_json_type", f"{path} contains a non-string object key")
            _validate_json_value(item, f"{path}.{key}")
        return
    _fail(
        "invalid_json_type",
        f"{path} contains unsupported type {type(value).__name__}",
    )


def canonical_json(value: Any) -> str:
    """Return the single canonical JSON spelling used by this bounded schema.

    The ledger schema permits only null, booleans, integers, UTF-8 strings,
    arrays, and string-keyed objects. Floats are intentionally unavailable.
    """

    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        _fail("invalid_json", str(exc))


def _sha256_domain(domain: bytes, value: Any) -> str:
    return hashlib.sha256(domain + canonical_json(value).encode("utf-8")).hexdigest()


def _require_exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], path: str
) -> None:
    actual = set(value)
    if actual != set(expected):
        unknown = sorted(actual - set(expected))
        missing = sorted(set(expected) - actual)
        if unknown:
            _fail("unknown_field", f"{path} has unknown fields: {unknown}")
        _fail("missing_field", f"{path} is missing fields: {missing}")


def _require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("invalid_type", f"{path} must be an object")
    return value


def _require_identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        _fail("invalid_identifier", f"{path} is not a bounded opaque identifier")
    return value


def _require_digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        _fail("invalid_digest", f"{path} must be 64 lowercase hexadecimal characters")
    return value


def _require_reason(value: Any, path: str) -> str:
    if not isinstance(value, str) or _REASON_RE.fullmatch(value) is None:
        _fail("invalid_reason_code", f"{path} must be a bounded reason code")
    return value


def _require_points(value: Any, path: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_POINTS:
        _fail("invalid_points", f"{path} must be an integer from 1 through {MAX_POINTS}")
    return value


def _privacy_guard(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_PRIVACY_KEYS:
                _fail("privacy_field_forbidden", f"{path}.{key} is not public-ledger data")
            _privacy_guard(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _privacy_guard(item, f"{path}[{index}]")


def compute_contribution_id(
    *,
    contribution_class: str,
    commit_digest: str,
    claim_digest: str,
    artifact_digests: Sequence[str],
) -> str:
    """Derive an identity-independent contribution digest.

    Excluding the contributor and epoch prevents the same exact evidence from
    receiving duplicate credit through another subject or later epoch.
    """

    _require_identifier(contribution_class, "contribution_class")
    _require_digest(commit_digest, "commit_digest")
    _require_digest(claim_digest, "claim_digest")
    artifacts = list(artifact_digests)
    if not 1 <= len(artifacts) <= MAX_ARTIFACT_DIGESTS:
        _fail(
            "invalid_artifact_digests",
            f"artifact_digests must contain 1 through {MAX_ARTIFACT_DIGESTS} entries",
        )
    for index, digest in enumerate(artifacts):
        _require_digest(digest, f"artifact_digests[{index}]")
    if artifacts != sorted(set(artifacts)):
        _fail(
            "noncanonical_artifact_digests",
            "artifact_digests must be sorted and unique",
        )
    return _sha256_domain(
        CONTRIBUTION_HASH_DOMAIN,
        {
            "artifact_digests": artifacts,
            "claim_digest": claim_digest,
            "commit_digest": commit_digest,
            "contribution_class": contribution_class,
        },
    )


def merkle_root(event_ids: Iterable[str]) -> str:
    """Return a deterministic binary Merkle root over ordered event IDs."""

    leaves: list[bytes] = []
    for index, event_id in enumerate(event_ids):
        _require_digest(event_id, f"event_ids[{index}]")
        leaves.append(
            hashlib.sha256(MERKLE_LEAF_DOMAIN + bytes.fromhex(event_id)).digest()
        )
    if not leaves:
        return hashlib.sha256(MERKLE_EMPTY_DOMAIN).hexdigest()
    level = leaves
    while len(level) > 1:
        if len(level) % 2:
            level = level + [level[-1]]
        level = [
            hashlib.sha256(MERKLE_NODE_DOMAIN + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0].hex()


def _event_id(unsigned_event: Mapping[str, Any]) -> str:
    return _sha256_domain(EVENT_HASH_DOMAIN, unsigned_event)


def _strict_json_loads(text: str) -> Any:
    def reject_constant(value: str) -> None:
        _fail("invalid_json_number", f"non-finite number {value} is forbidden")

    def reject_float(value: str) -> None:
        _fail("invalid_json_number", f"floating-point number {value} is forbidden")

    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("duplicate_json_key", f"duplicate object key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=no_duplicate_keys,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except LedgerValidationError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _fail("invalid_json", str(exc))


@dataclass
class _EpochState:
    budget_points: int
    policy_digest: str
    active_awarded_points: int = 0
    revoked_points: int = 0


@dataclass
class _ContributionState:
    epoch_id: str
    contributor_ref: str
    contribution_class: str
    registration_event_id: str
    award_event_id: str | None = None


@dataclass
class _AwardState:
    epoch_id: str
    contribution_id: str
    points: int
    decision_digest: str
    revocation_event_id: str | None = None


@dataclass
class ContributionLedger:
    """Append-only local ledger with deterministic replay and export."""

    ledger_id: str
    _events: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _epochs: dict[str, _EpochState] = field(default_factory=dict, init=False, repr=False)
    _contributions: dict[str, _ContributionState] = field(
        default_factory=dict, init=False, repr=False
    )
    _awards: dict[str, _AwardState] = field(default_factory=dict, init=False, repr=False)
    _correction_targets: dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        _require_identifier(self.ledger_id, "ledger_id")

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._events))

    @property
    def head_event_id(self) -> str | None:
        return self._events[-1]["event_id"] if self._events else None

    def append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and append one supported event.

        Unsupported operations, including transfer and approve, fail closed.
        """

        if event_type not in _PAYLOAD_FIELDS:
            _fail("unsupported_event", f"event type {event_type!r} is unavailable")
        payload_copy = copy.deepcopy(_require_dict(payload, "payload"))
        _privacy_guard(payload_copy, "payload")
        unsigned = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "ledger_id": self.ledger_id,
            "seq": len(self._events),
            "prev_event_id": self.head_event_id,
            "event_type": event_type,
            "payload": payload_copy,
        }
        event = {**unsigned, "event_id": _event_id(unsigned)}
        self._ingest(event)
        return copy.deepcopy(event)

    def open_epoch(
        self, *, epoch_id: str, budget_points: int, policy_digest: str
    ) -> dict[str, Any]:
        return self.append(
            "epoch_opened",
            {
                "epoch_id": epoch_id,
                "budget_points": budget_points,
                "policy_digest": policy_digest,
            },
        )

    def register_contribution(
        self,
        *,
        epoch_id: str,
        contributor_ref: str,
        contribution_class: str,
        commit_digest: str,
        claim_digest: str,
        artifact_digests: Sequence[str],
    ) -> dict[str, Any]:
        artifacts = sorted(artifact_digests)
        contribution_id = compute_contribution_id(
            contribution_class=contribution_class,
            commit_digest=commit_digest,
            claim_digest=claim_digest,
            artifact_digests=artifacts,
        )
        return self.append(
            "contribution_registered",
            {
                "epoch_id": epoch_id,
                "contribution_id": contribution_id,
                "contributor_ref": contributor_ref,
                "contribution_class": contribution_class,
                "commit_digest": commit_digest,
                "claim_digest": claim_digest,
                "artifact_digests": artifacts,
            },
        )

    def grant_award(
        self,
        *,
        epoch_id: str,
        contribution_id: str,
        points: int,
        decision_digest: str,
    ) -> dict[str, Any]:
        return self.append(
            "award_granted",
            {
                "epoch_id": epoch_id,
                "contribution_id": contribution_id,
                "points": points,
                "decision_digest": decision_digest,
            },
        )

    def revoke_award(
        self, *, award_event_id: str, reason_code: str, decision_digest: str
    ) -> dict[str, Any]:
        return self.append(
            "award_revoked",
            {
                "award_event_id": award_event_id,
                "reason_code": reason_code,
                "decision_digest": decision_digest,
            },
        )

    def record_correction(
        self, *, target_event_id: str, reason_code: str, corrected_record_digest: str
    ) -> dict[str, Any]:
        return self.append(
            "correction_recorded",
            {
                "target_event_id": target_event_id,
                "reason_code": reason_code,
                "corrected_record_digest": corrected_record_digest,
            },
        )

    def _ingest(self, event: Mapping[str, Any]) -> None:
        event_copy = copy.deepcopy(_require_dict(event, "event"))
        _privacy_guard(event_copy, "event")
        _require_exact_fields(event_copy, _EVENT_FIELDS, "event")
        if event_copy["schema_version"] != LEDGER_SCHEMA_VERSION:
            _fail("unsupported_schema", "event schema version is not supported")
        if event_copy["ledger_id"] != self.ledger_id:
            _fail("ledger_id_mismatch", "event belongs to another ledger")
        if type(event_copy["seq"]) is not int or event_copy["seq"] != len(self._events):
            _fail("sequence_mismatch", "event sequence is not the next sequence")
        if event_copy["prev_event_id"] != self.head_event_id:
            _fail("previous_event_mismatch", "event does not extend the current head")
        event_type = event_copy["event_type"]
        if not isinstance(event_type, str) or event_type not in _PAYLOAD_FIELDS:
            _fail("unsupported_event", f"event type {event_type!r} is unavailable")
        payload = _require_dict(event_copy["payload"], "event.payload")
        _require_exact_fields(payload, _PAYLOAD_FIELDS[event_type], "event.payload")
        supplied_event_id = _require_digest(event_copy["event_id"], "event.event_id")
        unsigned = {key: event_copy[key] for key in _EVENT_FIELDS if key != "event_id"}
        expected_event_id = _event_id(unsigned)
        if supplied_event_id != expected_event_id:
            _fail("event_id_mismatch", "event content does not match its event_id")
        self._apply_payload(event_type, payload, supplied_event_id)
        self._events.append(event_copy)

    def _apply_payload(
        self, event_type: str, payload: dict[str, Any], event_id: str
    ) -> None:
        if event_type == "epoch_opened":
            epoch_id = _require_identifier(payload["epoch_id"], "payload.epoch_id")
            budget = _require_points(payload["budget_points"], "payload.budget_points")
            policy_digest = _require_digest(
                payload["policy_digest"], "payload.policy_digest"
            )
            if epoch_id in self._epochs:
                _fail("duplicate_epoch", "epoch budget and policy are immutable")
            self._epochs[epoch_id] = _EpochState(budget, policy_digest)
            return

        if event_type == "contribution_registered":
            epoch_id = _require_identifier(payload["epoch_id"], "payload.epoch_id")
            if epoch_id not in self._epochs:
                _fail("unknown_epoch", "contribution references an unopened epoch")
            contribution_id = _require_digest(
                payload["contribution_id"], "payload.contribution_id"
            )
            contributor_ref = _require_identifier(
                payload["contributor_ref"], "payload.contributor_ref"
            )
            contribution_class = _require_identifier(
                payload["contribution_class"], "payload.contribution_class"
            )
            commit_digest = _require_digest(
                payload["commit_digest"], "payload.commit_digest"
            )
            claim_digest = _require_digest(
                payload["claim_digest"], "payload.claim_digest"
            )
            artifact_digests = payload["artifact_digests"]
            if not isinstance(artifact_digests, list):
                _fail("invalid_type", "payload.artifact_digests must be an array")
            expected_id = compute_contribution_id(
                contribution_class=contribution_class,
                commit_digest=commit_digest,
                claim_digest=claim_digest,
                artifact_digests=artifact_digests,
            )
            if contribution_id != expected_id:
                _fail(
                    "contribution_id_mismatch",
                    "contribution_id does not match its evidence digests",
                )
            if contribution_id in self._contributions:
                _fail(
                    "duplicate_contribution",
                    "the same exact contribution was already registered",
                )
            self._contributions[contribution_id] = _ContributionState(
                epoch_id=epoch_id,
                contributor_ref=contributor_ref,
                contribution_class=contribution_class,
                registration_event_id=event_id,
            )
            return

        if event_type == "award_granted":
            epoch_id = _require_identifier(payload["epoch_id"], "payload.epoch_id")
            contribution_id = _require_digest(
                payload["contribution_id"], "payload.contribution_id"
            )
            points = _require_points(payload["points"], "payload.points")
            decision_digest = _require_digest(
                payload["decision_digest"], "payload.decision_digest"
            )
            contribution = self._contributions.get(contribution_id)
            if contribution is None:
                _fail("unknown_contribution", "award references an unknown contribution")
            if contribution.epoch_id != epoch_id:
                _fail("epoch_mismatch", "award and contribution epochs differ")
            if contribution.award_event_id is not None:
                _fail("duplicate_award", "a contribution can be awarded only once")
            epoch = self._epochs[epoch_id]
            if epoch.active_awarded_points + points > epoch.budget_points:
                _fail("budget_exceeded", "award exceeds the fixed epoch budget")
            epoch.active_awarded_points += points
            contribution.award_event_id = event_id
            self._awards[event_id] = _AwardState(
                epoch_id=epoch_id,
                contribution_id=contribution_id,
                points=points,
                decision_digest=decision_digest,
            )
            return

        if event_type == "award_revoked":
            award_event_id = _require_digest(
                payload["award_event_id"], "payload.award_event_id"
            )
            _require_reason(payload["reason_code"], "payload.reason_code")
            _require_digest(payload["decision_digest"], "payload.decision_digest")
            award = self._awards.get(award_event_id)
            if award is None:
                _fail("unknown_award", "revocation references an unknown award")
            if award.revocation_event_id is not None:
                _fail("duplicate_revocation", "award was already revoked")
            award.revocation_event_id = event_id
            epoch = self._epochs[award.epoch_id]
            epoch.active_awarded_points -= award.points
            epoch.revoked_points += award.points
            return

        if event_type == "correction_recorded":
            target_event_id = _require_digest(
                payload["target_event_id"], "payload.target_event_id"
            )
            _require_reason(payload["reason_code"], "payload.reason_code")
            _require_digest(
                payload["corrected_record_digest"],
                "payload.corrected_record_digest",
            )
            if target_event_id not in {item["event_id"] for item in self._events}:
                _fail("unknown_correction_target", "correction target does not exist")
            if target_event_id in self._correction_targets:
                _fail("duplicate_correction", "event already has a correction record")
            self._correction_targets[target_event_id] = event_id
            return

        _fail("unsupported_event", f"event type {event_type!r} is unavailable")

    def verify(self) -> None:
        replay = ContributionLedger(self.ledger_id)
        for event in self._events:
            replay._ingest(event)
        if replay.snapshot_json() != self.snapshot_json():
            _fail("state_replay_mismatch", "replayed state differs from live state")

    def export_snapshot(self) -> dict[str, Any]:
        """Export deterministic public state for snapshots or Merkle anchoring."""

        epochs = []
        for epoch_id in sorted(self._epochs):
            epoch = self._epochs[epoch_id]
            epochs.append(
                {
                    "epoch_id": epoch_id,
                    "budget_points": epoch.budget_points,
                    "active_awarded_points": epoch.active_awarded_points,
                    "revoked_points": epoch.revoked_points,
                    "available_points": epoch.budget_points
                    - epoch.active_awarded_points,
                    "policy_digest": epoch.policy_digest,
                }
            )
        contributions = []
        for contribution_id in sorted(self._contributions):
            contribution = self._contributions[contribution_id]
            contributions.append(
                {
                    "contribution_id": contribution_id,
                    "epoch_id": contribution.epoch_id,
                    "contributor_ref": contribution.contributor_ref,
                    "contribution_class": contribution.contribution_class,
                    "registration_event_id": contribution.registration_event_id,
                    "award_event_id": contribution.award_event_id,
                }
            )
        awards = []
        for award_event_id in sorted(self._awards):
            award = self._awards[award_event_id]
            awards.append(
                {
                    "award_event_id": award_event_id,
                    "epoch_id": award.epoch_id,
                    "contribution_id": award.contribution_id,
                    "points": award.points,
                    "decision_digest": award.decision_digest,
                    "status": "revoked"
                    if award.revocation_event_id is not None
                    else "active",
                    "revocation_event_id": award.revocation_event_id,
                }
            )
        corrections = [
            {
                "target_event_id": target,
                "correction_event_id": self._correction_targets[target],
            }
            for target in sorted(self._correction_targets)
        ]
        event_ids = [event["event_id"] for event in self._events]
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "ledger_id": self.ledger_id,
            "event_count": len(self._events),
            "head_event_id": self.head_event_id,
            "events_merkle_root": merkle_root(event_ids),
            "epochs": epochs,
            "contributions": contributions,
            "awards": awards,
            "corrections": corrections,
            "non_financial": True,
            "transferable": False,
            "convertible": False,
        }

    def snapshot_json(self) -> str:
        return canonical_json(self.export_snapshot())

    def to_jsonl(self) -> str:
        if not self._events:
            return ""
        return "".join(canonical_json(event) + "\n" for event in self._events)

    @classmethod
    def from_jsonl(cls, text: str) -> "ContributionLedger":
        if not isinstance(text, str) or not text:
            _fail("empty_ledger", "JSONL ledger must contain at least one event")
        lines = text.splitlines()
        if not lines or any(not line for line in lines):
            _fail("invalid_jsonl", "blank JSONL records are forbidden")
        first = _strict_json_loads(lines[0])
        first_object = _require_dict(first, "event")
        ledger_id = _require_identifier(first_object.get("ledger_id"), "event.ledger_id")
        ledger = cls(ledger_id)
        for index, line in enumerate(lines):
            value = first if index == 0 else _strict_json_loads(line)
            if canonical_json(value) != line:
                _fail("noncanonical_json", f"JSONL record {index} is not canonical")
            ledger._ingest(_require_dict(value, f"event[{index}]"))
        return ledger
