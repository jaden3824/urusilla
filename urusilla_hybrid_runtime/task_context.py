"""Bounded public task and symbol semantics shared by every route.

The task context is declarative data, never executable authority.  It gives the
sender a bounded definition of "task-relevant" and prevents unfamiliar agents
from treating equal symbol names as equal meanings without an exact digest.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .canonical import canonical_json, sha256_text, strict_json_loads
from .errors import TaskContextError
from .records import (
    ACTS,
    CAPSULE_AUTHORITY_KEYS,
    OUTCOME_STATUSES,
    PublicActionState,
)


TASK_CONTEXT_FORMAT = "urusilla-public-task-context-draft/1"
TASK_CONTEXT_KEYS = frozenset(
    {
        "format",
        "task_id",
        "objective",
        "output_contract",
        "allowed_acts",
        "outcome_contract",
        "uncertainty_contract",
        "symbols",
        "authority_boundary",
    }
)
OUTPUT_CONTRACT_KEYS = frozenset(
    {"media_type", "validator_sha256", "description"}
)
OUTCOME_CONTRACT_KEYS = frozenset(
    {"statuses", "value", "evidence_required"}
)
UNCERTAINTY_CONTRACT_KEYS = frozenset(
    {"targets", "models", "basis_sources"}
)
SYMBOL_KEYS = frozenset(
    {
        "kind",
        "name",
        "meaning",
        "positional_args",
        "named_args",
        "allowed_effects",
    }
)
ARGUMENT_KEYS = frozenset(
    {"name", "type", "nullable", "required", "unit", "meaning"}
)
SYMBOL_KINDS = frozenset({"predicate", "action", "effect"})
# Container schemas are deliberately unsupported until a bounded recursive
# item/property contract exists.  Falling back is safer than type-checking only
# the outer list/object and pretending its meaning is bound.
JSON_TYPES = frozenset({"boolean", "integer", "string"})
MAX_SYMBOLS = 512
MAX_ARGUMENTS = 128
MAX_TEXT_CHARS = 16_384
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/+-]{0,255}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNSAFE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _fail(message: str) -> None:
    raise TaskContextError(message)


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        _fail(f"{path} must be a bounded public identifier")
    return value


def _text(value: Any, path: str) -> str:
    if type(value) is not str or not value or len(value) > MAX_TEXT_CHARS:
        _fail(f"{path} must be non-empty bounded text")
    if _UNSAFE_CONTROL.search(value) is not None:
        _fail(f"{path} contains unsafe control characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TaskContextError(f"{path} is not valid UTF-8") from exc
    return value


def _exact_object(value: Any, keys: frozenset[str], path: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        _fail(f"{path} fields differ from the declarative contract")
    return value


def _validate_argument(value: Any, path: str, *, named: bool) -> Mapping[str, Any]:
    item = _exact_object(value, ARGUMENT_KEYS, path)
    name = item["name"]
    if named:
        _identifier(name, f"{path}.name")
    else:
        _text(name, f"{path}.name")
        if len(name) > 256:
            _fail(f"{path}.name exceeds 256 characters")
    if item["type"] not in JSON_TYPES:
        _fail(f"{path}.type is unsupported")
    for key in ("nullable", "required"):
        if type(item[key]) is not bool:
            _fail(f"{path}.{key} must be boolean")
    if not named and not item["required"]:
        _fail(f"{path}.required must be true for positional arguments")
    if item["unit"] is not None:
        _identifier(item["unit"], f"{path}.unit")
    _text(item["meaning"], f"{path}.meaning")
    return item


def _validate_symbol(value: Any, path: str) -> Mapping[str, Any]:
    item = _exact_object(value, SYMBOL_KEYS, path)
    if item["kind"] not in SYMBOL_KINDS:
        _fail(f"{path}.kind is unsupported")
    _identifier(item["name"], f"{path}.name")
    _text(item["meaning"], f"{path}.meaning")
    positional = item["positional_args"]
    named = item["named_args"]
    if type(positional) is not list or len(positional) > MAX_ARGUMENTS:
        _fail(f"{path}.positional_args must be a bounded array")
    if type(named) is not list or len(named) > MAX_ARGUMENTS:
        _fail(f"{path}.named_args must be a bounded array")
    for index, argument in enumerate(positional):
        _validate_argument(argument, f"{path}.positional_args[{index}]", named=False)
    positional_names = [str(argument["name"]) for argument in positional]
    if len(set(positional_names)) != len(positional_names):
        _fail(f"{path}.positional_args contains duplicate names")
    named_items = [
        _validate_argument(argument, f"{path}.named_args[{index}]", named=True)
        for index, argument in enumerate(named)
    ]
    names = [str(argument["name"]) for argument in named_items]
    if len(set(names)) != len(names):
        _fail(f"{path}.named_args contains duplicate names")
    if item["kind"] == "predicate" and named:
        _fail(f"{path}: predicates use positional_args only")
    if item["kind"] == "action" and positional:
        _fail(f"{path}: actions use named_args only")
    if item["kind"] == "effect" and (positional or named):
        _fail(f"{path}: effects cannot declare arguments")
    allowed_effects = item["allowed_effects"]
    if type(allowed_effects) is not list or len(allowed_effects) > MAX_ARGUMENTS:
        _fail(f"{path}.allowed_effects must be a bounded array")
    for index, effect in enumerate(allowed_effects):
        _identifier(effect, f"{path}.allowed_effects[{index}]")
    if len(set(allowed_effects)) != len(allowed_effects):
        _fail(f"{path}.allowed_effects contains duplicates")
    if item["kind"] != "action" and allowed_effects:
        _fail(f"{path}: only actions may declare allowed_effects")
    return item


def validate_task_context(value: Any) -> Mapping[str, Any]:
    context = _exact_object(value, TASK_CONTEXT_KEYS, "task_context")
    if context["format"] != TASK_CONTEXT_FORMAT:
        _fail("task_context.format is unsupported")
    _identifier(context["task_id"], "task_context.task_id")
    _text(context["objective"], "task_context.objective")
    output_contract = _exact_object(
        context["output_contract"],
        OUTPUT_CONTRACT_KEYS,
        "task_context.output_contract",
    )
    if output_contract["media_type"] not in {
        "text/plain",
        "application/json",
    }:
        _fail("task_context.output_contract.media_type is unsupported")
    if (
        type(output_contract["validator_sha256"]) is not str
        or _SHA256.fullmatch(output_contract["validator_sha256"]) is None
    ):
        _fail("task_context.output_contract.validator_sha256 is invalid")
    _text(
        output_contract["description"],
        "task_context.output_contract.description",
    )
    allowed_acts = context["allowed_acts"]
    if (
        type(allowed_acts) is not list
        or not allowed_acts
        or any(type(item) is not str or item not in ACTS for item in allowed_acts)
        or len(set(allowed_acts)) != len(allowed_acts)
    ):
        _fail("task_context.allowed_acts is invalid")
    outcome_contract = _exact_object(
        context["outcome_contract"],
        OUTCOME_CONTRACT_KEYS,
        "task_context.outcome_contract",
    )
    statuses = outcome_contract["statuses"]
    if (
        type(statuses) is not list
        or not statuses
        or any(
            type(item) is not str or item not in OUTCOME_STATUSES
            for item in statuses
        )
        or len(set(statuses)) != len(statuses)
    ):
        _fail("task_context.outcome_contract.statuses is invalid")
    value_schema = _validate_argument(
        outcome_contract["value"],
        "task_context.outcome_contract.value",
        named=True,
    )
    if value_schema["required"] is not True:
        _fail("task_context.outcome_contract.value.required must be true")
    if type(outcome_contract["evidence_required"]) is not bool:
        _fail("task_context.outcome_contract.evidence_required must be boolean")
    uncertainty_contract = _exact_object(
        context["uncertainty_contract"],
        UNCERTAINTY_CONTRACT_KEYS,
        "task_context.uncertainty_contract",
    )
    for key in ("targets", "models", "basis_sources"):
        values = uncertainty_contract[key]
        if type(values) is not list or len(values) > MAX_SYMBOLS:
            _fail(f"task_context.uncertainty_contract.{key} is invalid")
        for index, item in enumerate(values):
            _identifier(
                item,
                f"task_context.uncertainty_contract.{key}[{index}]",
            )
        if len(set(values)) != len(values):
            _fail(f"task_context.uncertainty_contract.{key} has duplicates")
    authority = context["authority_boundary"]
    if type(authority) is not dict or set(authority) != CAPSULE_AUTHORITY_KEYS or any(
        authority[key] is not False for key in CAPSULE_AUTHORITY_KEYS
    ):
        _fail("task_context must grant no authority")
    symbols = context["symbols"]
    if type(symbols) is not list or len(symbols) > MAX_SYMBOLS:
        _fail("task_context.symbols must be a bounded array")
    validated = [
        _validate_symbol(symbol, f"task_context.symbols[{index}]")
        for index, symbol in enumerate(symbols)
    ]
    identities = [(item["kind"], item["name"]) for item in validated]
    if len(set(identities)) != len(identities):
        _fail("task_context.symbols contains duplicate kind/name pairs")
    declared_effects = {
        item["name"] for item in validated if item["kind"] == "effect"
    }
    for item in validated:
        if item["kind"] == "action" and not set(item["allowed_effects"]).issubset(
            declared_effects
        ):
            _fail(
                f"action {item['name']} references an undeclared allowed effect"
            )
    return context


@dataclass(frozen=True)
class PublicTaskContext:
    canonical_text: str
    sha256: str

    def __post_init__(self) -> None:
        try:
            value = strict_json_loads(self.canonical_text)
            validate_task_context(value)
            canonical = canonical_json(value)
        except ValueError as exc:
            raise TaskContextError(f"invalid direct task-context construction: {exc}") from exc
        if canonical != self.canonical_text:
            _fail("task-context text is not canonical JSON")
        if self.sha256 != sha256_text(self.canonical_text):
            _fail("task-context digest mismatch")

    @classmethod
    def from_object(cls, value: Any) -> "PublicTaskContext":
        validate_task_context(value)
        text = canonical_json(value)
        return cls(text, sha256_text(text))

    @classmethod
    def from_json(cls, text: str) -> "PublicTaskContext":
        return cls.from_object(strict_json_loads(text))

    def to_object(self) -> dict[str, Any]:
        value = strict_json_loads(self.canonical_text)
        assert type(value) is dict
        return value

    @property
    def symbol_table_sha256(self) -> str:
        return sha256_text(canonical_json(self.to_object()["symbols"]))

    @property
    def task_profile_sha256(self) -> str:
        value = self.to_object()
        profile = {
            "format": value["format"],
            "output_contract": value["output_contract"],
            "allowed_acts": value["allowed_acts"],
            "outcome_contract": value["outcome_contract"],
            "uncertainty_contract": value["uncertainty_contract"],
            "symbols": value["symbols"],
            "authority_boundary": value["authority_boundary"],
        }
        return sha256_text(canonical_json(profile))

    @property
    def output_validator_sha256(self) -> str:
        return str(self.to_object()["output_contract"]["validator_sha256"])

    def symbols_by_identity(self) -> dict[tuple[str, str], Mapping[str, Any]]:
        return {
            (str(item["kind"]), str(item["name"])): item
            for item in self.to_object()["symbols"]
        }


def _matches_json_type(value: Any, declared: str, nullable: bool) -> bool:
    if value is None:
        return nullable
    if declared == "boolean":
        return type(value) is bool
    if declared == "integer":
        return type(value) is int
    if declared == "string":
        return type(value) is str
    if declared == "array":
        return type(value) is list
    if declared == "object":
        return type(value) is dict
    return False


def validate_state_against_task_context(
    state: PublicActionState,
    task_context: PublicTaskContext,
) -> None:
    """Validate arity/types and exact declarative symbol-table membership."""

    symbols = task_context.symbols_by_identity()
    value = state.to_object()
    context_value = task_context.to_object()
    if value["act"] not in context_value["allowed_acts"]:
        _fail(f"action-state act is outside the task profile: {value['act']}")
    atoms: list[Mapping[str, Any]] = []
    if value["goal"] is not None:
        atoms.append(value["goal"])
    for key in ("state", "constraints", "needs"):
        atoms.extend(value[key])
    if value["outcome"] is not None:
        atoms.extend(value["outcome"]["evidence"])
    for atom in atoms:
        identity = ("predicate", str(atom["p"]))
        definition = symbols.get(identity)
        if definition is None:
            _fail(f"action-state uses undeclared predicate: {atom['p']}")
        arguments = atom["a"]
        declared = definition["positional_args"]
        if len(arguments) != len(declared):
            _fail(f"predicate arity mismatch: {atom['p']}")
        for index, (argument, schema) in enumerate(zip(arguments, declared)):
            if not _matches_json_type(argument, schema["type"], schema["nullable"]):
                _fail(f"predicate argument type mismatch: {atom['p']}[{index}]")

    action = value["action"]
    if action is not None:
        identity = ("action", str(action["name"]))
        definition = symbols.get(identity)
        if definition is None:
            _fail(f"action-state uses undeclared action: {action['name']}")
        supplied = action["args"]
        declared = {item["name"]: item for item in definition["named_args"]}
        if set(supplied) - set(declared):
            _fail(f"action has undeclared arguments: {action['name']}")
        for name, schema in declared.items():
            if name not in supplied:
                if schema["required"]:
                    _fail(f"action is missing required argument: {action['name']}.{name}")
                continue
            if not _matches_json_type(supplied[name], schema["type"], schema["nullable"]):
                _fail(f"action argument type mismatch: {action['name']}.{name}")
        allowed_effects = set(definition["allowed_effects"])
        for effect in action["effects"]:
            if ("effect", effect) not in symbols:
                _fail(f"action-state uses undeclared effect: {effect}")
            if effect not in allowed_effects:
                _fail(f"action reports an effect not bound to its schema: {effect}")

    outcome = value["outcome"]
    if outcome is not None:
        contract = context_value["outcome_contract"]
        if outcome["status"] not in contract["statuses"]:
            _fail("outcome status is outside the task profile")
        value_schema = contract["value"]
        if not _matches_json_type(
            outcome["value"],
            value_schema["type"],
            value_schema["nullable"],
        ):
            _fail("outcome value type is outside the task profile")
        if contract["evidence_required"] and not outcome["evidence"]:
            _fail("outcome evidence is required by the task profile")

    uncertainty_contract = context_value["uncertainty_contract"]
    allowed_targets = set(uncertainty_contract["targets"])
    allowed_models = set(uncertainty_contract["models"])
    allowed_basis = set(uncertainty_contract["basis_sources"])
    for uncertainty in value["uncertainty"]:
        if uncertainty["target"] not in allowed_targets:
            _fail("uncertainty target is outside the task profile")
        if uncertainty["model"] not in allowed_models:
            _fail("uncertainty model is outside the task profile")
        if not set(uncertainty["basis"]).issubset(allowed_basis):
            _fail("uncertainty basis is outside the task profile")
