"""Declarative Capsule and public action-state records.

The record is a development profile layered on Urusilla 0.1.0.  It is not a
new protocol version and cannot authorize an effect.  Its canonical JSON is
intended to be consumed directly by a model or deterministic agent.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
from pathlib import Path
import re
import sysconfig
from typing import Any, Mapping, Sequence

from .canonical import canonical_json, sha256_text, strict_json_loads
from .errors import ActionStateError, CapsuleError


ACTION_STATE_FORMAT = "urusilla-public-action-state-draft/1"
CAPSULE_TYPE = "urusilla-session-action-state-capsule"
CAPSULE_VERSION = "draft-1"
CAPSULE_STATUS = "development-only-unpromoted"
PROTOCOL_LANGUAGE_VERSION = "0.1.0"
CAPSULE_CANONICAL_SHA256 = (
    "sha256:7942bb348c3b2b839a3f87304b7d850796c837afdc66177eb1a48e5a45f0f778"
)
CAPSULE_AUTHORITY_KEYS = frozenset(
    {
        "content_is_authority",
        "executable_code",
        "external_effects",
        "permission_expansion",
        "persistent_storage",
        "spending_authority",
    }
)

ACTION_STATE_KEYS = frozenset(
    {
        "format",
        "act",
        "goal",
        "state",
        "constraints",
        "action",
        "outcome",
        "needs",
        "uncertainty",
    }
)
ATOM_KEYS = frozenset({"p", "a", "n", "src"})
CONSTRAINT_KEYS = frozenset({"p", "a", "n", "src", "hard"})
ACTION_KEYS = frozenset({"name", "args", "status", "effects"})
OUTCOME_KEYS = frozenset({"status", "value", "evidence"})
UNCERTAINTY_KEYS = frozenset({"target", "model", "confidence_ppm", "basis"})

ACTS = frozenset({"assert", "query", "request", "propose", "resolve", "refuse"})
ACTION_STATUSES = frozenset(
    {"proposed", "blocked", "running", "completed", "failed", "canceled"}
)
OUTCOME_STATUSES = frozenset(
    {"succeeded", "failed", "error", "rejected", "canceled", "unknown"}
)

MAX_LIST_ITEMS = 512
MAX_IDENTIFIER_CHARS = 256
MAX_PUBLIC_TEXT_CHARS = 16_384
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/+-]{0,255}$")
_UNSAFE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise ActionStateError(f"{path} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    observed = set(value)
    if observed != set(expected):
        raise ActionStateError(
            f"{path} fields differ; missing={sorted(set(expected) - observed)}, "
            f"extra={sorted(observed - set(expected))}"
        )


def _list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise ActionStateError(f"{path} must be an array")
    if len(value) > MAX_LIST_ITEMS:
        raise ActionStateError(f"{path} exceeds {MAX_LIST_ITEMS} entries")
    return value


def _text(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if type(value) is not str or not value or len(value) > MAX_PUBLIC_TEXT_CHARS:
        raise ActionStateError(
            f"{path} must be non-empty text of at most {MAX_PUBLIC_TEXT_CHARS} characters"
        )
    if _UNSAFE_CONTROL.search(value) is not None:
        raise ActionStateError(f"{path} contains unsafe control characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ActionStateError(f"{path} is not valid UTF-8") from exc
    return value


def _identifier(value: Any, path: str) -> str:
    text = _text(value, path)
    assert text is not None
    if len(text) > MAX_IDENTIFIER_CHARS or _IDENTIFIER.fullmatch(text) is None:
        raise ActionStateError(f"{path} is not a bounded public identifier")
    return text


def _validate_public_json(value: Any, path: str) -> None:
    """Apply public-record limits recursively, including scalar arguments."""

    if type(value) is str:
        if len(value) > MAX_PUBLIC_TEXT_CHARS:
            raise ActionStateError(
                f"{path} exceeds {MAX_PUBLIC_TEXT_CHARS} public text characters"
            )
        if _UNSAFE_CONTROL.search(value) is not None:
            raise ActionStateError(f"{path} contains unsafe control characters")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ActionStateError(f"{path} is not valid UTF-8") from exc
        return
    if type(value) is list:
        if len(value) > MAX_LIST_ITEMS:
            raise ActionStateError(f"{path} exceeds {MAX_LIST_ITEMS} entries")
        for index, item in enumerate(value):
            _validate_public_json(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            _validate_public_json(item, f"{path}.{key}")
        return
    canonical_json(value)


def _validate_atom(value: Any, path: str, *, constraint: bool = False) -> None:
    item = _mapping(value, path)
    _exact_keys(item, CONSTRAINT_KEYS if constraint else ATOM_KEYS, path)
    _identifier(item["p"], f"{path}.p")
    _list(item["a"], f"{path}.a")
    _validate_public_json(item["a"], f"{path}.a")
    if type(item["n"]) is not bool:
        raise ActionStateError(f"{path}.n must be boolean")
    if item["src"] is not None:
        _identifier(item["src"], f"{path}.src")
    if constraint and type(item["hard"]) is not bool:
        raise ActionStateError(f"{path}.hard must be boolean")


def _validate_action(value: Any, path: str) -> None:
    item = _mapping(value, path)
    _exact_keys(item, ACTION_KEYS, path)
    _identifier(item["name"], f"{path}.name")
    if type(item["args"]) is not dict:
        raise ActionStateError(f"{path}.args must be an object")
    _validate_public_json(item["args"], f"{path}.args")
    if type(item["status"]) is not str or item["status"] not in ACTION_STATUSES:
        raise ActionStateError(f"{path}.status is unknown")
    effects = _list(item["effects"], f"{path}.effects")
    for index, effect in enumerate(effects):
        _identifier(effect, f"{path}.effects[{index}]")
    if len(set(effects)) != len(effects):
        raise ActionStateError(f"{path}.effects contains duplicates")


def _validate_outcome(value: Any, path: str) -> None:
    item = _mapping(value, path)
    _exact_keys(item, OUTCOME_KEYS, path)
    if type(item["status"]) is not str or item["status"] not in OUTCOME_STATUSES:
        raise ActionStateError(f"{path}.status is unknown")
    _validate_public_json(item["value"], f"{path}.value")
    evidence = _list(item["evidence"], f"{path}.evidence")
    for index, atom in enumerate(evidence):
        _validate_atom(atom, f"{path}.evidence[{index}]")


def _validate_uncertainty(value: Any, path: str) -> None:
    item = _mapping(value, path)
    _exact_keys(item, UNCERTAINTY_KEYS, path)
    _identifier(item["target"], f"{path}.target")
    _identifier(item["model"], f"{path}.model")
    confidence = item["confidence_ppm"]
    if confidence is not None and (
        type(confidence) is not int or not 0 <= confidence <= 1_000_000
    ):
        raise ActionStateError(f"{path}.confidence_ppm must be null or 0..1000000")
    basis = _list(item["basis"], f"{path}.basis")
    for index, text in enumerate(basis):
        _identifier(text, f"{path}.basis[{index}]")


def validate_action_state(value: Any) -> Mapping[str, Any]:
    state = _mapping(value, "action_state")
    _exact_keys(state, ACTION_STATE_KEYS, "action_state")
    if state["format"] != ACTION_STATE_FORMAT:
        raise ActionStateError("action_state.format is unsupported")
    if type(state["act"]) is not str or state["act"] not in ACTS:
        raise ActionStateError("action_state.act is unknown")

    goal = state["goal"]
    if goal is not None:
        _validate_atom(goal, "action_state.goal")
    facts = _list(state["state"], "action_state.state")
    for index, atom in enumerate(facts):
        _validate_atom(atom, f"action_state.state[{index}]")
    constraints = _list(state["constraints"], "action_state.constraints")
    for index, constraint in enumerate(constraints):
        _validate_atom(
            constraint, f"action_state.constraints[{index}]", constraint=True
        )
    action = state["action"]
    if action is not None:
        _validate_action(action, "action_state.action")
    outcome = state["outcome"]
    if outcome is not None:
        _validate_outcome(outcome, "action_state.outcome")
    needs = _list(state["needs"], "action_state.needs")
    for index, atom in enumerate(needs):
        _validate_atom(atom, f"action_state.needs[{index}]")
    uncertainty = _list(state["uncertainty"], "action_state.uncertainty")
    for index, item in enumerate(uncertainty):
        _validate_uncertainty(item, f"action_state.uncertainty[{index}]")

    act = state["act"]
    if act == "request" and goal is None:
        raise ActionStateError("request action state requires a goal")
    if act == "query" and not needs:
        raise ActionStateError("query action state requires at least one need")
    if act == "propose" and action is None:
        raise ActionStateError("propose action state requires an action")
    if act == "resolve" and outcome is None:
        raise ActionStateError("resolve action state requires an outcome")
    if act == "refuse" and (
        outcome is None or outcome["status"] not in {"rejected", "failed", "canceled"}
    ):
        raise ActionStateError("refuse action state requires a negative outcome")
    if act == "assert" and not (goal is not None or facts or outcome is not None):
        raise ActionStateError("assert action state contains no public state")
    return state


@dataclass(frozen=True)
class PublicActionState:
    """Immutable-by-serialization validated public action-state."""

    canonical_text: str
    sha256: str

    def __post_init__(self) -> None:
        try:
            value = strict_json_loads(self.canonical_text)
            validate_action_state(value)
            canonical = canonical_json(value)
        except ValueError as exc:
            raise ActionStateError(f"invalid direct action-state construction: {exc}") from exc
        if canonical != self.canonical_text:
            raise ActionStateError("action-state text is not canonical JSON")
        if self.sha256 != sha256_text(self.canonical_text):
            raise ActionStateError("action-state digest mismatch")

    @classmethod
    def from_object(cls, value: Any) -> "PublicActionState":
        validate_action_state(value)
        text = canonical_json(value)
        return cls(text, sha256_text(text))

    @classmethod
    def from_json(cls, text: str) -> "PublicActionState":
        return cls.from_object(strict_json_loads(text))

    def to_object(self) -> dict[str, Any]:
        value = strict_json_loads(self.canonical_text)
        assert type(value) is dict
        return value

    @property
    def act(self) -> str:
        return str(self.to_object()["act"])

    @property
    def preserves_negative_or_null(self) -> bool:
        value = self.to_object()
        atoms: list[Mapping[str, Any]] = []
        if value["goal"] is not None:
            atoms.append(value["goal"])
        atoms.extend(value["state"])
        atoms.extend(value["constraints"])
        atoms.extend(value["needs"])
        outcome = value["outcome"]
        has_negative = any(item["n"] for item in atoms)
        has_null_source = any(item["src"] is None for item in atoms)
        has_null_outcome = outcome is not None and outcome["value"] is None
        has_null_uncertainty = any(
            item["confidence_ppm"] is None for item in value["uncertainty"]
        )
        has_failure = outcome is not None and outcome["status"] in {
            "failed",
            "error",
            "rejected",
            "canceled",
        }
        action = value["action"]
        has_failed_action = action is not None and action["status"] in {
            "blocked",
            "failed",
            "canceled",
        }
        return (
            has_negative
            or has_null_source
            or has_null_outcome
            or has_null_uncertainty
            or has_failure
            or has_failed_action
        )


@dataclass(frozen=True)
class Capsule:
    canonical_text: str
    sha256: str
    path: Path

    def __post_init__(self) -> None:
        try:
            value = strict_json_loads(self.canonical_text)
            canonical = canonical_json(value)
        except ValueError as exc:
            raise CapsuleError(f"invalid direct Capsule construction: {exc}") from exc
        if canonical != self.canonical_text:
            raise CapsuleError("Capsule text is not canonical JSON")
        if self.sha256 != sha256_text(self.canonical_text):
            raise CapsuleError("Capsule digest mismatch")
        if self.sha256 != CAPSULE_CANONICAL_SHA256:
            raise CapsuleError("Capsule content is not the pinned development Capsule")
        if not isinstance(self.path, Path):
            raise CapsuleError("Capsule path must be a Path")

    def to_object(self) -> dict[str, Any]:
        value = strict_json_loads(self.canonical_text)
        assert type(value) is dict
        return value


def default_capsule_path() -> Path:
    checkout_path = (
        Path(__file__).resolve().parents[1]
        / "urusilla_action_state_capsule.json"
    )
    if checkout_path.is_file():
        return checkout_path
    target_scheme_path = (
        Path(__file__).resolve().parents[1]
        / "share"
        / "urusilla"
        / "urusilla_action_state_capsule.json"
    )
    if target_scheme_path.is_file():
        return target_scheme_path
    # A wheel's RECORD retains the location relative to its own dist-info
    # directory.  Resolving through distribution metadata also supports
    # --target, --user, and custom installation schemes where the interpreter's
    # global sysconfig data prefix does not describe this imported package.
    try:
        distribution = importlib.metadata.distribution("urusilla")
    except importlib.metadata.PackageNotFoundError:
        distribution = None
    if distribution is not None:
        for item in distribution.files or ():
            item_text = str(item).replace("\\", "/")
            if (
                item_text.endswith(
                    "share/urusilla/urusilla_action_state_capsule.json"
                )
                or item_text == "urusilla_action_state_capsule.json"
            ):
                installed_path = Path(distribution.locate_file(item)).resolve()
                if installed_path.is_file():
                    return installed_path
    # Setuptools installs project data under the active Python scheme's data
    # prefix (for example, <venv>/share/urusilla).  Resolve that location
    # explicitly instead of depending on the current working directory.
    return (
        Path(sysconfig.get_path("data"))
        / "share"
        / "urusilla"
        / "urusilla_action_state_capsule.json"
    )


def load_capsule(path: Path | None = None) -> Capsule:
    source = path or default_capsule_path()
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CapsuleError(f"cannot read declarative Capsule: {exc}") from exc
    try:
        value = strict_json_loads(text)
    except ValueError as exc:
        raise CapsuleError(f"invalid declarative Capsule: {exc}") from exc
    if type(value) is not dict:
        raise CapsuleError("Capsule must be an object")
    required = {
        "capsule_type",
        "capsule_version",
        "status",
        "protocol_language_version",
        "purpose",
        "canonicalization",
        "authority_boundary",
        "record",
        "sender_contract",
        "sender_output",
        "receiver_contract",
        "fallback_contract",
        "examples",
    }
    if set(value) != required:
        raise CapsuleError(
            f"Capsule fields differ; missing={sorted(required - set(value))}, "
            f"extra={sorted(set(value) - required)}"
        )
    canonical = canonical_json(value)
    observed_sha256 = sha256_text(canonical)
    if observed_sha256 != CAPSULE_CANONICAL_SHA256:
        raise CapsuleError(
            "declarative Capsule content digest mismatch; "
            f"expected {CAPSULE_CANONICAL_SHA256}, observed {observed_sha256}"
        )
    if (
        value["capsule_type"] != CAPSULE_TYPE
        or value["capsule_version"] != CAPSULE_VERSION
        or value["status"] != CAPSULE_STATUS
        or value["protocol_language_version"] != PROTOCOL_LANGUAGE_VERSION
    ):
        raise CapsuleError("Capsule identity or lifecycle status is unsupported")
    canonicalization = value["canonicalization"]
    if (
        type(canonicalization) is not dict
        or set(canonicalization) != {"format", "rules"}
        or canonicalization["format"] != "urusilla-hybrid-canonical-json/1"
        or type(canonicalization["rules"]) is not list
        or not canonicalization["rules"]
        or any(type(item) is not str or not item for item in canonicalization["rules"])
    ):
        raise CapsuleError("Capsule canonicalization contract is invalid")
    authority = value["authority_boundary"]
    if type(authority) is not dict or set(authority) != CAPSULE_AUTHORITY_KEYS or any(
        authority[key] is not False for key in CAPSULE_AUTHORITY_KEYS
    ):
        raise CapsuleError("development Capsule must grant no authority")
    record = value["record"]
    if type(record) is not dict or record.get("format") != ACTION_STATE_FORMAT:
        raise CapsuleError("Capsule action-state format changed")
    record_contracts = {
        "fields": ACTION_STATE_KEYS,
        "acts": ACTS,
    }
    for key, expected in record_contracts.items():
        observed = record.get(key)
        if type(observed) is not list or set(observed) != set(expected) or len(observed) != len(expected):
            raise CapsuleError(f"Capsule record.{key} contract changed")
    nested_contracts = {
        "atom": ATOM_KEYS,
        "constraint": CONSTRAINT_KEYS,
        "action": ACTION_KEYS,
        "outcome": OUTCOME_KEYS,
        "uncertainty": UNCERTAINTY_KEYS,
    }
    for name, expected in nested_contracts.items():
        contract = record.get(name)
        if type(contract) is not dict:
            raise CapsuleError(f"Capsule record.{name} contract is invalid")
        observed = contract.get("fields")
        if type(observed) is not list or set(observed) != set(expected) or len(observed) != len(expected):
            raise CapsuleError(f"Capsule record.{name}.fields changed")
    sender_output = value["sender_output"]
    if (
        type(sender_output) is not dict
        or set(sender_output.get("fields", []))
        != {"status", "candidates", "unsupported", "failure"}
        or set(sender_output.get("statuses", []))
        != {"ok", "ambiguous", "unsupported", "failed"}
    ):
        raise CapsuleError("Capsule sender output contract changed")
    for name in (
        "sender_contract",
        "receiver_contract",
        "fallback_contract",
    ):
        contract = value[name]
        if type(contract) is not list or not contract or any(
            type(item) is not str or not item for item in contract
        ):
            raise CapsuleError(f"Capsule {name} must be a non-empty text array")
    try:
        PublicActionState.from_object(value["examples"]["positive"])
    except (KeyError, TypeError, ActionStateError) as exc:
        raise CapsuleError("Capsule positive example is invalid") from exc
    return Capsule(canonical, observed_sha256, source)


def source_text_sha256(text: str) -> str:
    if type(text) is not str or not text:
        raise ActionStateError("source text must be non-empty")
    if len(text) > MAX_PUBLIC_TEXT_CHARS * 4:
        raise ActionStateError("source text exceeds the runtime limit")
    if _UNSAFE_CONTROL.search(text) is not None:
        raise ActionStateError("source text contains unsafe control characters")
    return sha256_text(text)


def wrap_as_quarantined_urusilla_message(
    state: PublicActionState,
    *,
    message_id: str,
    session_id: str,
    sender: str,
    recipient: str,
    logical_clock: int,
) -> dict[str, Any]:
    """Wrap direct state in the existing 0.1 local-extension quarantine.

    The returned ASSERT is observable data only.  This helper intentionally
    cannot produce COMMIT, RESOLVE, RETRACT, or an effect authorization.
    """

    from urusilla import normalize_message

    return normalize_message(
        {
            "id": message_id,
            "session": session_id,
            "sender": sender,
            "recipients": [recipient],
            "act": "ASSERT",
            "reply_to": None,
            "schema": "urn:urusilla:profile:public-action-state:draft-1",
            "logical_clock": logical_clock,
            "expires_ms": 0,
            "confidence_ppm": None,
            "expected": [],
            "body": {
                "kind": "x:public-action-state-draft-1",
                "record": state.to_object(),
            },
            "meta": {
                "x:capsule-status": CAPSULE_STATUS,
                "x:effect-authorized": False,
            },
        }
    )
