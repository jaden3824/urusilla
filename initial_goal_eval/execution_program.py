"""Standalone, claim-ineligible branch-slot execution programs.

The contract in this module performs no call and changes none of the frozen v1
study, trace, receipt, or result schemas.  It closes only a structural runner
prerequisite: a program is frozen before execution, and its resolution is a
self-contained replay closure containing typed, content-addressed source-record
preimages.  Hash consistency does not authenticate a provider, operator, or
implementation and cannot make a result claim-eligible.  The request,
provider-record, local-observation, and failure digests inside a source record
remain opaque commitments in this standalone module; their underlying
preimages and mutual bindings must be validated by a future receipt-store
integration before any runner or claim path can consume the artifact.

``depends_on`` has one exact meaning: it lists prior slots whose dispositions or
typed source facts are consumed by ``activation_predicate``. ``order_after`` is
separate and carries ordering only; it can never be referenced by a predicate.
An inactive slot has no source record and is never a zero-token usage event.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .contract import (
    ARMS,
    EVENT_PHASES,
    ROUTES,
    VerificationError,
    _count,
    _exact,
    _identifier,
    _list,
    _object,
    _sha,
    canonical_json,
    sha256_ref,
    strict_json_loads,
)
from .terminal_contract import CAPTURE_TERMINAL_STATUSES, SILENCE_TERMINAL_STATUS


ARM_EXECUTION_PROGRAM_SCHEMA = "urusilla-initial-goal-arm-execution-program/1"
ARM_EXECUTION_EVIDENCE_STORE_SCHEMA = (
    "urusilla-initial-goal-arm-execution-evidence-store/1"
)
ARM_EXECUTION_SOURCE_RECORD_SCHEMA = (
    "urusilla-initial-goal-arm-execution-source-record/1"
)
ARM_EXECUTION_PROGRAM_RESOLUTION_SCHEMA = (
    "urusilla-initial-goal-arm-execution-program-resolution/1"
)
EXECUTION_PROGRAM_ACTIVATION_INPUT_SCHEMA = (
    "urusilla-initial-goal-execution-program-activation-input/1"
)
EXECUTION_PROGRAM_RESOLUTION_DIGEST_SCHEMA = (
    "urusilla-initial-goal-execution-program-resolution-digest/1"
)

SLOT_DISPOSITIONS = ("executed", "not-activated", "failed-before-record")
SOURCE_KINDS = (
    "external-response",
    "deterministic-local",
    "deterministic-validator",
)
SOURCE_RECORD_KINDS = ("executed-source", "failure-before-source-record")
ACTIVATION_FACTS = (
    "disposition",
    "selected_mode",
    "terminal_status",
    "fidelity_verdict",
    "output_verdict",
    "control_decision",
    "compiler_status",
)
FIDELITY_VERDICTS = ("valid", "invalid")
OUTPUT_VERDICTS = ("valid", "invalid")
CONTROL_DECISIONS = ("attempt-action-state", "skip-action-state")
COMPILER_STATUSES = (
    "not-attempted",
    "ok",
    "ambiguous",
    "unsupported",
    "failed",
)

BASELINE_COMPONENTS = ("setup", "receiver", "judge")
HYBRID_COMPONENTS = (
    "setup",
    "sender-compiler",
    "fidelity-verifier",
    "router",
    "primary",
    "output-validator",
    "fallback-control",
    "fallback-receiver",
    "judge",
)
HYBRID_CONTROL_COMPONENTS = (
    "preflight-router",
    "compiler-control",
    "final-router",
)
_ROUTER_COMPONENTS = frozenset({"router", "preflight-router", "final-router"})

MAX_SLOTS = 100_000
MAX_CALLS_PER_SLOT = 1

_SLOT_FIELDS = {
    "slot_id",
    "task_id",
    "accounting_phase",
    "component",
    "source_kind",
    "activation_predicate",
    "depends_on",
    "order_after",
    "request_deriver_sha256",
    "implementation_sha256",
    "model_binding_sha256",
    "maximum_calls",
}
_BINDING_FIELDS = {
    "source_kind",
    "request_deriver_sha256",
    "implementation_sha256",
    "model_binding_sha256",
    "maximum_calls",
}
_RESOLUTION_FIELDS = {
    "slot_id",
    "disposition",
    "activation_input_sha256",
    "source_record_sha256",
}
_SOURCE_RECORD_FIELDS = {
    "schema_version",
    "program_sha256",
    "record_kind",
    "session_id",
    "arm_id",
    "task_id",
    "task_sha256",
    "slot_id",
    "accounting_phase",
    "component",
    "source_kind",
    "request_deriver_sha256",
    "implementation_sha256",
    "model_binding_sha256",
    "request_sha256",
    "provider_record_sha256",
    "local_observation_sha256",
    "failure_sha256",
    "result_event_sequence",
    "facts",
}
_FACT_FIELDS = {
    "selected_mode",
    "terminal_status",
    "fidelity_verdict",
    "output_verdict",
    "control_decision",
    "compiler_status",
}

_COMPONENT_PHASE = {
    "setup": "setup",
    "receiver": "receiver",
    "judge": "judge",
    "sender-compiler": "sender",
    # Existing result ledgers have no semantic-verification phase; this
    # standalone prerequisite retains the existing safety accounting bucket.
    "fidelity-verifier": "safety",
    "router": "router",
    "primary": "receiver",
    "output-validator": "safety",
    "fallback-control": "fallback",
    "fallback-receiver": "fallback",
    "preflight-router": "router",
    "compiler-control": "router",
    "final-router": "router",
}

_COMPONENT_SOURCE_KINDS = {
    "setup": frozenset({"external-response", "deterministic-local"}),
    "receiver": frozenset({"external-response"}),
    "judge": frozenset(SOURCE_KINDS),
    "sender-compiler": frozenset(
        {"external-response", "deterministic-local"}
    ),
    "fidelity-verifier": frozenset(
        {
            "external-response",
            "deterministic-local",
            "deterministic-validator",
        }
    ),
    "router": frozenset({"deterministic-local"}),
    "primary": frozenset({"external-response"}),
    "output-validator": frozenset(
        {"deterministic-local", "deterministic-validator"}
    ),
    "fallback-control": frozenset({"deterministic-local"}),
    "fallback-receiver": frozenset({"external-response"}),
    "preflight-router": frozenset({"deterministic-local"}),
    "compiler-control": frozenset({"deterministic-local"}),
    "final-router": frozenset({"deterministic-local"}),
}

_BASELINE_GRAPH = {
    "setup": ("always", ()),
    "receiver": ("dependencies-executed", ("setup",)),
    "judge": ("baseline-terminal-recorded", ("receiver",)),
}
_HYBRID_GRAPH = {
    "setup": ("always", ()),
    "sender-compiler": ("dependencies-executed", ("setup",)),
    "fidelity-verifier": ("dependencies-executed", ("sender-compiler",)),
    "router": ("dependencies-executed", ("fidelity-verifier",)),
    "primary": ("dependencies-executed", ("router",)),
    "output-validator": ("primary-recorded", ("primary",)),
    "fallback-control": (
        "fallback-required",
        ("router", "primary", "output-validator"),
    ),
    "fallback-receiver": ("dependencies-executed", ("fallback-control",)),
    "judge": (
        "final-terminal-recorded",
        (
            "primary",
            "output-validator",
            "fallback-control",
            "fallback-receiver",
        ),
    ),
}

__all__ = [
    "ACTIVATION_FACTS",
    "ARM_EXECUTION_EVIDENCE_STORE_SCHEMA",
    "ARM_EXECUTION_PROGRAM_RESOLUTION_SCHEMA",
    "ARM_EXECUTION_PROGRAM_SCHEMA",
    "ARM_EXECUTION_SOURCE_RECORD_SCHEMA",
    "BASELINE_COMPONENTS",
    "EXECUTION_PROGRAM_ACTIVATION_INPUT_SCHEMA",
    "HYBRID_COMPONENTS",
    "HYBRID_CONTROL_COMPONENTS",
    "SLOT_DISPOSITIONS",
    "SOURCE_KINDS",
    "build_arm_execution_program",
    "build_baseline_execution_program",
    "build_execution_evidence_store",
    "build_hybrid_execution_program",
    "build_raw_json_execution_program",
    "build_slot_evidence_record",
    "execution_program_activation_input_sha256",
    "execution_program_sha256",
    "resolve_arm_execution_program",
    "validate_arm_execution_program",
    "validate_arm_execution_program_json",
    "validate_execution_evidence_store",
    "validate_resolved_arm_execution_program",
]


def _detach(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _nullable_sha(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _sha(value, path)


def _nullable_identifier(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, path)


def _validate_task_refs(value: Any, path: str = "task_refs") -> list[dict[str, str]]:
    refs = _list(value, path)
    if not refs:
        raise VerificationError(f"{path} must not be empty")
    result: list[dict[str, str]] = []
    task_ids: set[str] = set()
    task_digests: set[str] = set()
    for index, raw in enumerate(refs):
        item_path = f"{path}[{index}]"
        ref = _object(raw, item_path)
        _exact(ref, {"task_id", "task_sha256"}, item_path)
        task_id = _identifier(ref["task_id"], f"{item_path}.task_id")
        task_sha256 = _sha(ref["task_sha256"], f"{item_path}.task_sha256")
        if task_id in task_ids or task_sha256 in task_digests:
            raise VerificationError(f"{path} contains duplicate task identity")
        task_ids.add(task_id)
        task_digests.add(task_sha256)
        result.append({"task_id": task_id, "task_sha256": task_sha256})
    return result


def _allowed_fact_values(fact: str) -> set[str]:
    if fact == "disposition":
        return set(SLOT_DISPOSITIONS)
    if fact == "selected_mode":
        return set(ROUTES)
    if fact == "terminal_status":
        return {*CAPTURE_TERMINAL_STATUSES, SILENCE_TERMINAL_STATUS}
    if fact == "fidelity_verdict":
        return set(FIDELITY_VERDICTS)
    if fact == "output_verdict":
        return set(OUTPUT_VERDICTS)
    if fact == "control_decision":
        return set(CONTROL_DECISIONS)
    if fact == "compiler_status":
        return set(COMPILER_STATUSES)
    raise VerificationError("activation fact is outside the closed vocabulary")


def _validate_predicate(value: Any, *, arm_id: str, path: str) -> dict[str, Any]:
    predicate = _object(value, path)
    _exact(predicate, {"all_of"}, path)
    conditions = _list(predicate["all_of"], f"{path}.all_of")
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(conditions):
        condition_path = f"{path}.all_of[{index}]"
        condition = _object(raw, condition_path)
        _exact(condition, {"slot_id", "fact", "equals_any"}, condition_path)
        slot_id = _identifier(condition["slot_id"], f"{condition_path}.slot_id")
        fact = condition["fact"]
        if fact not in ACTIVATION_FACTS:
            raise VerificationError(
                f"{condition_path}.fact is outside the closed vocabulary"
            )
        key = (slot_id, fact)
        if key in seen:
            raise VerificationError(f"{path} contains a duplicate fact condition")
        seen.add(key)
        values = _list(condition["equals_any"], f"{condition_path}.equals_any")
        if not values or len(set(canonical_json(item) for item in values)) != len(values):
            raise VerificationError(
                f"{condition_path}.equals_any must be non-empty and unique"
            )
        allowed = _allowed_fact_values(fact)
        if any(type(item) is not str or item not in allowed for item in values):
            raise VerificationError(f"{condition_path}.equals_any is invalid")
        if fact == "selected_mode":
            compatible = (
                set(ROUTES)
                if arm_id == "hybrid-router"
                else {"raw"}
                if arm_id == "raw-concise"
                else {"json"}
            )
            if not set(values).issubset(compatible):
                raise VerificationError(
                    f"{condition_path} route is incompatible with its arm"
                )
        if (
            fact
            in {
                "fidelity_verdict",
                "output_verdict",
                "control_decision",
                "compiler_status",
            }
            and arm_id != "hybrid-router"
        ):
            raise VerificationError(
                f"{condition_path} hybrid fact is incompatible with a baseline"
            )
    return _detach(predicate)


def _validate_binding(value: Any, path: str, *, component: str) -> dict[str, Any]:
    binding = _object(value, path)
    _exact(binding, _BINDING_FIELDS, path)
    source_kind = binding["source_kind"]
    if source_kind not in SOURCE_KINDS:
        raise VerificationError(f"{path}.source_kind is invalid")
    if source_kind not in _COMPONENT_SOURCE_KINDS[component]:
        raise VerificationError(f"{path} component/source_kind combination is invalid")
    request_deriver = _nullable_sha(
        binding["request_deriver_sha256"], f"{path}.request_deriver_sha256"
    )
    implementation = _nullable_sha(
        binding["implementation_sha256"], f"{path}.implementation_sha256"
    )
    model_binding = _nullable_sha(
        binding["model_binding_sha256"], f"{path}.model_binding_sha256"
    )
    maximum_calls = _count(binding["maximum_calls"], f"{path}.maximum_calls")
    if maximum_calls != MAX_CALLS_PER_SLOT:
        raise VerificationError(f"{path}.maximum_calls must be exactly one")
    if source_kind == "external-response":
        if request_deriver is None or implementation is None or model_binding is None:
            raise VerificationError(
                f"{path} external source needs request, implementation, and model bindings"
            )
    elif request_deriver is not None or model_binding is not None or implementation is None:
        raise VerificationError(f"{path} local source needs only implementation")
    return _detach(binding)


def _fact_source_is_compatible(fact: str, source: Mapping[str, Any]) -> bool:
    component = source["component"]
    if fact == "disposition":
        return True
    if fact == "selected_mode":
        return component in _ROUTER_COMPONENTS
    if fact == "terminal_status":
        return source["source_kind"] == "external-response"
    if fact == "fidelity_verdict":
        return component == "fidelity-verifier"
    if fact == "output_verdict":
        return component == "output-validator"
    if fact == "control_decision":
        return component in {"preflight-router", "compiler-control"}
    if fact == "compiler_status":
        return component in {"sender-compiler", "compiler-control"}
    return False


def _graph_has_path(
    start: str,
    target: str,
    successors: Mapping[str, set[str]],
) -> bool:
    pending = [start]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(successors[current])
    return False


def validate_arm_execution_program(value: Any) -> dict[str, Any]:
    """Validate one exact program, including generic graph completeness."""

    program = _object(value, "execution_program")
    _exact(
        program,
        {"schema_version", "session_id", "arm_id", "task_refs", "slots"},
        "execution_program",
    )
    if program["schema_version"] != ARM_EXECUTION_PROGRAM_SCHEMA:
        raise VerificationError("execution program schema differs")
    _identifier(program["session_id"], "execution_program.session_id")
    arm_id = program["arm_id"]
    if arm_id not in ARMS:
        raise VerificationError("execution_program.arm_id is invalid")
    task_refs = _validate_task_refs(
        program["task_refs"], "execution_program.task_refs"
    )
    task_ids = {item["task_id"] for item in task_refs}
    slots = _list(program["slots"], "execution_program.slots")
    if not slots or len(slots) > MAX_SLOTS:
        raise VerificationError("execution_program.slots has invalid cardinality")

    allowed_components = (
        set(HYBRID_COMPONENTS) | set(HYBRID_CONTROL_COMPONENTS)
        if arm_id == "hybrid-router"
        else set(BASELINE_COMPONENTS)
    )
    normalized_slots: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    index_by_id: dict[str, int] = {}
    task_components: set[tuple[str | None, str]] = set()
    for index, raw in enumerate(slots):
        path = f"execution_program.slots[{index}]"
        slot = _object(raw, path)
        _exact(slot, _SLOT_FIELDS, path)
        slot_id = _identifier(slot["slot_id"], f"{path}.slot_id")
        if slot_id in by_id:
            raise VerificationError("execution program contains duplicate slot IDs")
        task_id = _nullable_identifier(slot["task_id"], f"{path}.task_id")
        component = _identifier(slot["component"], f"{path}.component")
        if component not in allowed_components:
            raise VerificationError(f"{path}.component is incompatible with its arm")
        if task_id is None and component != "setup":
            raise VerificationError("only the session setup slot may have null task_id")
        if task_id is not None and task_id not in task_ids:
            raise VerificationError(f"{path} references an unplanned task")
        key = (task_id, component)
        if key in task_components:
            raise VerificationError("duplicate task/component slot is ambiguous")
        task_components.add(key)
        if slot["accounting_phase"] != _COMPONENT_PHASE[component]:
            raise VerificationError(f"{path} component and accounting phase differ")
        _validate_binding(
            {field: slot[field] for field in _BINDING_FIELDS},
            path,
            component=component,
        )
        predicate = _validate_predicate(
            slot["activation_predicate"],
            arm_id=arm_id,
            path=f"{path}.activation_predicate",
        )
        depends_on = _list(slot["depends_on"], f"{path}.depends_on")
        order_after = _list(slot["order_after"], f"{path}.order_after")
        for field_name, items in (
            ("depends_on", depends_on),
            ("order_after", order_after),
        ):
            for item_index, item in enumerate(items):
                _identifier(item, f"{path}.{field_name}[{item_index}]")
            if len(set(items)) != len(items):
                raise VerificationError(f"{path}.{field_name} contains duplicates")
            if slot_id in items:
                raise VerificationError(f"{path}.{field_name} contains itself")
        if set(depends_on) & set(order_after):
            raise VerificationError(f"{path} dependency and ordering edges overlap")
        predicate_refs = {
            condition["slot_id"] for condition in predicate["all_of"]
        }
        if predicate_refs != set(depends_on):
            raise VerificationError(
                f"{path} predicate refs must exactly equal depends_on"
            )
        normalized = _detach(slot)
        normalized_slots.append(normalized)
        by_id[slot_id] = normalized
        index_by_id[slot_id] = index

    setup_slots = [slot for slot in normalized_slots if slot["component"] == "setup"]
    if len(setup_slots) != 1 or setup_slots[0]["task_id"] is not None:
        raise VerificationError("execution program needs one session-level setup root")
    setup = setup_slots[0]
    if (
        normalized_slots[0]["slot_id"] != setup["slot_id"]
        or setup["depends_on"]
        or setup["order_after"]
        or setup["activation_predicate"] != {"all_of": []}
    ):
        raise VerificationError("session setup must be the unique unconditional root")

    successors = {slot_id: set() for slot_id in by_id}
    for slot in normalized_slots:
        all_predecessors = [*slot["depends_on"], *slot["order_after"]]
        for predecessor_id in all_predecessors:
            predecessor = by_id.get(predecessor_id)
            if predecessor is None:
                raise VerificationError("execution program edge references an unplanned slot")
            if predecessor["task_id"] not in {None, slot["task_id"]}:
                raise VerificationError("execution program edge crosses task boundaries")
            if index_by_id[predecessor_id] >= index_by_id[slot["slot_id"]]:
                raise VerificationError(
                    "execution program edges are not topologically ordered"
                )
            successors[predecessor_id].add(slot["slot_id"])
        for condition in slot["activation_predicate"]["all_of"]:
            source = by_id[condition["slot_id"]]
            if not _fact_source_is_compatible(condition["fact"], source):
                raise VerificationError(
                    "activation fact references an incompatible source component"
                )

    observed_tasks = {slot["task_id"] for slot in normalized_slots if slot["task_id"]}
    if observed_tasks != task_ids:
        raise VerificationError("every task_ref must have a slot subgraph")
    for task_id in sorted(task_ids):
        task_slots = [slot for slot in normalized_slots if slot["task_id"] == task_id]
        task_component_names = {slot["component"] for slot in task_slots}
        if arm_id in {"raw-concise", "ordinary-json"} and task_component_names != {
            "receiver",
            "judge",
        }:
            raise VerificationError(
                "each baseline task needs exactly one receiver and one judge"
            )
        judges = [slot for slot in task_slots if slot["component"] == "judge"]
        if len(judges) != 1:
            raise VerificationError("each task subgraph needs exactly one judge terminal")
        judge_id = judges[0]["slot_id"]
        if successors[judge_id]:
            raise VerificationError("task judge must be a terminal slot")
        for slot in task_slots:
            if not _graph_has_path(setup["slot_id"], slot["slot_id"], successors):
                raise VerificationError("task slot is unreachable from setup root")
            if not _graph_has_path(slot["slot_id"], judge_id, successors):
                raise VerificationError("task slot cannot reach its judge terminal")
    return _detach(program)


def validate_arm_execution_program_json(text: str) -> dict[str, Any]:
    return validate_arm_execution_program(strict_json_loads(text))


def execution_program_sha256(value: Any) -> str:
    return sha256_ref(validate_arm_execution_program(value))


def _condition(slot_id: str, fact: str, values: Sequence[str]) -> dict[str, Any]:
    return {"slot_id": slot_id, "fact": fact, "equals_any": list(values)}


def _build_predicate(kind: str, dependency_ids: Sequence[str]) -> dict[str, Any]:
    if kind == "always":
        conditions: list[dict[str, Any]] = []
    elif kind == "dependencies-executed":
        conditions = [
            _condition(slot_id, "disposition", ["executed"])
            for slot_id in dependency_ids
        ]
    elif kind in {"baseline-terminal-recorded", "primary-recorded"}:
        conditions = [
            _condition(
                dependency_ids[0],
                "disposition",
                ["executed", "failed-before-record"],
            )
        ]
    elif kind == "fallback-required":
        router_id, primary_id, validator_id = dependency_ids
        conditions = [
            _condition(router_id, "disposition", ["executed"]),
            _condition(
                primary_id,
                "disposition",
                ["executed", "failed-before-record"],
            ),
            _condition(validator_id, "disposition", ["executed"]),
            _condition(router_id, "selected_mode", ["routine", "action-state"]),
            _condition(validator_id, "output_verdict", ["invalid"]),
        ]
    elif kind == "final-terminal-recorded":
        primary_id, validator_id, control_id, fallback_id = dependency_ids
        conditions = [
            _condition(
                primary_id,
                "disposition",
                ["executed", "failed-before-record"],
            ),
            _condition(
                validator_id,
                "disposition",
                ["executed", "failed-before-record"],
            ),
            _condition(control_id, "disposition", list(SLOT_DISPOSITIONS)),
            _condition(fallback_id, "disposition", list(SLOT_DISPOSITIONS)),
        ]
    else:  # pragma: no cover - fixed graphs are module-owned
        raise VerificationError("unknown fixed activation predicate")
    return {"all_of": conditions}


def _slot_id(
    *, session_id: str, arm_id: str, task_id: str | None, component: str
) -> str:
    digest = sha256_ref(
        {
            "schema_version": "urusilla-initial-goal-arm-execution-slot-id/1",
            "session_id": session_id,
            "arm_id": arm_id,
            "task_id": task_id,
            "component": component,
        }
    )
    return f"slot-{digest.removeprefix('sha256:')}"


def _validated_bindings(
    frozen_bindings: Any, components: Sequence[str]
) -> dict[str, dict[str, Any]]:
    bindings = _object(frozen_bindings, "frozen_bindings")
    _exact(bindings, set(components), "frozen_bindings")
    return {
        component: _validate_binding(
            bindings[component],
            f"frozen_bindings.{component}",
            component=component,
        )
        for component in components
    }


def _build_fixed_program(
    *,
    session_id: str,
    arm_id: str,
    task_refs: Any,
    frozen_bindings: Any,
    components: Sequence[str],
    graph: Mapping[str, tuple[str, Sequence[str]]],
) -> dict[str, Any]:
    _identifier(session_id, "session_id")
    refs = _validate_task_refs(task_refs)
    bindings = _validated_bindings(frozen_bindings, components)
    setup_id = _slot_id(
        session_id=session_id, arm_id=arm_id, task_id=None, component="setup"
    )
    slots: list[dict[str, Any]] = []

    def append_slot(
        *, task_id: str | None, component: str, ids: Mapping[str, str]
    ) -> None:
        predicate_kind, dependency_components = graph[component]
        dependency_ids = [ids[item] for item in dependency_components]
        slots.append(
            {
                "slot_id": ids[component],
                "task_id": task_id,
                "accounting_phase": _COMPONENT_PHASE[component],
                "component": component,
                **bindings[component],
                "activation_predicate": _build_predicate(
                    predicate_kind, dependency_ids
                ),
                "depends_on": dependency_ids,
                "order_after": [],
            }
        )

    append_slot(task_id=None, component="setup", ids={"setup": setup_id})
    for ref in refs:
        task_id = ref["task_id"]
        ids = {"setup": setup_id}
        ids.update(
            {
                component: _slot_id(
                    session_id=session_id,
                    arm_id=arm_id,
                    task_id=task_id,
                    component=component,
                )
                for component in components
                if component != "setup"
            }
        )
        for component in components:
            if component != "setup":
                append_slot(task_id=task_id, component=component, ids=ids)
    return validate_arm_execution_program(
        {
            "schema_version": ARM_EXECUTION_PROGRAM_SCHEMA,
            "session_id": session_id,
            "arm_id": arm_id,
            "task_refs": refs,
            "slots": slots,
        }
    )


def build_raw_json_execution_program(
    *, session_id: str, arm_id: str, task_refs: Any, frozen_bindings: Any
) -> dict[str, Any]:
    """Build the fixed raw/json diagnostic program (not claim eligible)."""

    if arm_id not in {"raw-concise", "ordinary-json"}:
        raise VerificationError("raw/json builder requires a baseline arm")
    return _build_fixed_program(
        session_id=session_id,
        arm_id=arm_id,
        task_refs=task_refs,
        frozen_bindings=frozen_bindings,
        components=BASELINE_COMPONENTS,
        graph=_BASELINE_GRAPH,
    )


def build_baseline_execution_program(
    *, session_id: str, arm_id: str, task_refs: Any, frozen_bindings: Any
) -> dict[str, Any]:
    return build_raw_json_execution_program(
        session_id=session_id,
        arm_id=arm_id,
        task_refs=task_refs,
        frozen_bindings=frozen_bindings,
    )


def build_hybrid_execution_program(
    *, session_id: str, task_refs: Any, frozen_bindings: Any
) -> dict[str, Any]:
    """Build the all-components hybrid diagnostic program.

    This fixed convenience graph intentionally remains claim-ineligible.  The
    generic validator also admits explicit preflight/compiler/final controls
    for a future runner that represents prepare-message branching faithfully.
    """

    return _build_fixed_program(
        session_id=session_id,
        arm_id="hybrid-router",
        task_refs=task_refs,
        frozen_bindings=frozen_bindings,
        components=HYBRID_COMPONENTS,
        graph=_HYBRID_GRAPH,
    )


def build_arm_execution_program(
    *, session_id: str, arm_id: str, task_refs: Any, frozen_bindings: Any
) -> dict[str, Any]:
    if arm_id == "hybrid-router":
        return build_hybrid_execution_program(
            session_id=session_id,
            task_refs=task_refs,
            frozen_bindings=frozen_bindings,
        )
    return build_raw_json_execution_program(
        session_id=session_id,
        arm_id=arm_id,
        task_refs=task_refs,
        frozen_bindings=frozen_bindings,
    )


def _nullable_fact(value: Any, allowed: set[str], path: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or value not in allowed:
        raise VerificationError(f"{path} is invalid")
    return value


def _validate_source_record(
    value: Any,
    path: str,
    *,
    program: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = _object(value, path)
    _exact(record, _SOURCE_RECORD_FIELDS, path)
    if record["schema_version"] != ARM_EXECUTION_SOURCE_RECORD_SCHEMA:
        raise VerificationError(f"{path}.schema_version differs")
    _sha(record["program_sha256"], f"{path}.program_sha256")
    if record["record_kind"] not in SOURCE_RECORD_KINDS:
        raise VerificationError(f"{path}.record_kind is invalid")
    _identifier(record["session_id"], f"{path}.session_id")
    if record["arm_id"] not in ARMS:
        raise VerificationError(f"{path}.arm_id is invalid")
    task_id = _nullable_identifier(record["task_id"], f"{path}.task_id")
    task_sha256 = _nullable_sha(record["task_sha256"], f"{path}.task_sha256")
    if (task_id is None) != (task_sha256 is None):
        raise VerificationError(f"{path} task identity is incomplete")
    _identifier(record["slot_id"], f"{path}.slot_id")
    component = _identifier(record["component"], f"{path}.component")
    if component not in _COMPONENT_PHASE:
        raise VerificationError(f"{path}.component is invalid")
    if record["accounting_phase"] != _COMPONENT_PHASE[component]:
        raise VerificationError(f"{path} component and phase differ")
    _validate_binding(
        {
            "source_kind": record["source_kind"],
            "request_deriver_sha256": record["request_deriver_sha256"],
            "implementation_sha256": record["implementation_sha256"],
            "model_binding_sha256": record["model_binding_sha256"],
            "maximum_calls": 1,
        },
        path,
        component=component,
    )
    request = _nullable_sha(record["request_sha256"], f"{path}.request_sha256")
    provider = _nullable_sha(
        record["provider_record_sha256"], f"{path}.provider_record_sha256"
    )
    local = _nullable_sha(
        record["local_observation_sha256"], f"{path}.local_observation_sha256"
    )
    failure = _nullable_sha(record["failure_sha256"], f"{path}.failure_sha256")
    sequence = record["result_event_sequence"]
    if sequence is not None:
        _count(sequence, f"{path}.result_event_sequence")

    facts = _object(record["facts"], f"{path}.facts")
    _exact(facts, _FACT_FIELDS, f"{path}.facts")
    normalized_facts = {
        "selected_mode": _nullable_fact(
            facts["selected_mode"], set(ROUTES), f"{path}.facts.selected_mode"
        ),
        "terminal_status": _nullable_fact(
            facts["terminal_status"],
            {*CAPTURE_TERMINAL_STATUSES, SILENCE_TERMINAL_STATUS},
            f"{path}.facts.terminal_status",
        ),
        "fidelity_verdict": _nullable_fact(
            facts["fidelity_verdict"],
            set(FIDELITY_VERDICTS),
            f"{path}.facts.fidelity_verdict",
        ),
        "output_verdict": _nullable_fact(
            facts["output_verdict"],
            set(OUTPUT_VERDICTS),
            f"{path}.facts.output_verdict",
        ),
        "control_decision": _nullable_fact(
            facts["control_decision"],
            set(CONTROL_DECISIONS),
            f"{path}.facts.control_decision",
        ),
        "compiler_status": _nullable_fact(
            facts["compiler_status"],
            set(COMPILER_STATUSES),
            f"{path}.facts.compiler_status",
        ),
    }
    executed = record["record_kind"] == "executed-source"
    external = record["source_kind"] == "external-response"
    if executed:
        if sequence is None:
            raise VerificationError(f"{path} executed source needs an event sequence")
        if external:
            if request is None or provider is None or local is not None or failure is not None:
                raise VerificationError(f"{path} external evidence is not exclusive")
        elif request is not None or provider is not None or local is None or failure is not None:
            raise VerificationError(f"{path} local evidence is not exclusive")
    else:
        if sequence is not None or provider is not None or local is not None or failure is None:
            raise VerificationError(f"{path} failed source has ambiguous evidence")
        if external != (request is not None):
            raise VerificationError(f"{path} failed request evidence differs by source kind")
        if any(value is not None for value in normalized_facts.values()):
            raise VerificationError(f"{path} failed source cannot assert derived facts")

    compatible_components = {
        "selected_mode": _ROUTER_COMPONENTS,
        "terminal_status": frozenset(_COMPONENT_PHASE) if external else frozenset(),
        "fidelity_verdict": frozenset({"fidelity-verifier"}),
        "output_verdict": frozenset({"output-validator"}),
        "control_decision": frozenset({"preflight-router", "compiler-control"}),
        "compiler_status": frozenset({"sender-compiler", "compiler-control"}),
    }
    required_facts: set[str] = set()
    if external:
        required_facts.add("terminal_status")
    if component in _ROUTER_COMPONENTS:
        required_facts.add("selected_mode")
    if component == "fidelity-verifier":
        required_facts.add("fidelity_verdict")
    if component == "output-validator":
        required_facts.add("output_verdict")
    if component == "preflight-router":
        required_facts.add("control_decision")
    if component in {"sender-compiler", "compiler-control"}:
        required_facts.add("compiler_status")
    if executed:
        for fact, fact_value in normalized_facts.items():
            if fact_value is not None and component not in compatible_components[fact]:
                raise VerificationError(f"{path}.facts.{fact} has the wrong source component")
            if fact in required_facts and fact_value is None:
                raise VerificationError(f"{path}.facts.{fact} is required")

    normalized = _detach(record)
    normalized["facts"] = normalized_facts
    if program is not None:
        program_sha = execution_program_sha256(program)
        if normalized["program_sha256"] != program_sha:
            raise VerificationError(f"{path} is replayed under another program")
        if normalized["session_id"] != program["session_id"] or normalized["arm_id"] != program["arm_id"]:
            raise VerificationError(f"{path} session/arm domain differs")
        slots = {slot["slot_id"]: slot for slot in program["slots"]}
        slot = slots.get(normalized["slot_id"])
        if slot is None:
            raise VerificationError(f"{path} references an unplanned slot")
        task_sha_by_id = {
            item["task_id"]: item["task_sha256"] for item in program["task_refs"]
        }
        expected_task_sha = (
            None if slot["task_id"] is None else task_sha_by_id[slot["task_id"]]
        )
        expected = {
            "task_id": slot["task_id"],
            "task_sha256": expected_task_sha,
            "accounting_phase": slot["accounting_phase"],
            "component": slot["component"],
            "source_kind": slot["source_kind"],
            "request_deriver_sha256": slot["request_deriver_sha256"],
            "implementation_sha256": slot["implementation_sha256"],
            "model_binding_sha256": slot["model_binding_sha256"],
        }
        if any(normalized[field] != value for field, value in expected.items()):
            raise VerificationError(f"{path} domain or frozen binding differs from its slot")
    return normalized


def build_slot_evidence_record(
    program: Any,
    *,
    slot_id: str,
    record_kind: str,
    request_sha256: str | None = None,
    provider_record_sha256: str | None = None,
    local_observation_sha256: str | None = None,
    failure_sha256: str | None = None,
    result_event_sequence: int | None = None,
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validated = validate_arm_execution_program(program)
    slots = {slot["slot_id"]: slot for slot in validated["slots"]}
    slot = slots.get(slot_id)
    if slot is None:
        raise VerificationError("evidence record references an unplanned slot")
    task_sha_by_id = {
        item["task_id"]: item["task_sha256"] for item in validated["task_refs"]
    }
    fact_values = {field: None for field in _FACT_FIELDS}
    if facts is not None:
        supplied = _object(facts, "facts")
        if not set(supplied).issubset(_FACT_FIELDS):
            raise VerificationError("facts contains an unknown field")
        fact_values.update(supplied)
    record = {
        "schema_version": ARM_EXECUTION_SOURCE_RECORD_SCHEMA,
        "program_sha256": execution_program_sha256(validated),
        "record_kind": record_kind,
        "session_id": validated["session_id"],
        "arm_id": validated["arm_id"],
        "task_id": slot["task_id"],
        "task_sha256": (
            None
            if slot["task_id"] is None
            else task_sha_by_id[slot["task_id"]]
        ),
        "slot_id": slot["slot_id"],
        "accounting_phase": slot["accounting_phase"],
        "component": slot["component"],
        "source_kind": slot["source_kind"],
        "request_deriver_sha256": slot["request_deriver_sha256"],
        "implementation_sha256": slot["implementation_sha256"],
        "model_binding_sha256": slot["model_binding_sha256"],
        "request_sha256": request_sha256,
        "provider_record_sha256": provider_record_sha256,
        "local_observation_sha256": local_observation_sha256,
        "failure_sha256": failure_sha256,
        "result_event_sequence": result_event_sequence,
        "facts": fact_values,
    }
    return _validate_source_record(record, "source_record", program=validated)


def validate_execution_evidence_store(
    value: Any, program: Any | None = None
) -> dict[str, Any]:
    store = _object(value, "evidence_store")
    _exact(store, {"schema_version", "program_sha256", "records"}, "evidence_store")
    if store["schema_version"] != ARM_EXECUTION_EVIDENCE_STORE_SCHEMA:
        raise VerificationError("evidence store schema differs")
    _sha(store["program_sha256"], "evidence_store.program_sha256")
    validated_program = (
        None if program is None else validate_arm_execution_program(program)
    )
    if validated_program is not None and store["program_sha256"] != execution_program_sha256(validated_program):
        raise VerificationError("evidence store is replayed under another program")
    entries = _list(store["records"], "evidence_store.records")
    seen_records: set[str] = set()
    seen_slots: set[str] = set()
    evidence_roles: dict[str, tuple[str, str]] = {}
    sequences: list[int] = []
    for index, raw in enumerate(entries):
        path = f"evidence_store.records[{index}]"
        entry = _object(raw, path)
        _exact(entry, {"record_sha256", "record"}, path)
        digest = _sha(entry["record_sha256"], f"{path}.record_sha256")
        record = _validate_source_record(
            entry["record"], f"{path}.record", program=validated_program
        )
        if digest != sha256_ref(record):
            raise VerificationError(f"{path} content address differs")
        if record["program_sha256"] != store["program_sha256"]:
            raise VerificationError(f"{path} program domain differs")
        if digest in seen_records or record["slot_id"] in seen_slots:
            raise VerificationError("evidence store contains duplicate source records")
        seen_records.add(digest)
        seen_slots.add(record["slot_id"])
        for field in (
            "request_sha256",
            "provider_record_sha256",
            "local_observation_sha256",
            "failure_sha256",
        ):
            value_digest = record[field]
            if value_digest is None:
                continue
            if value_digest in evidence_roles:
                prior_slot, prior_field = evidence_roles[value_digest]
                raise VerificationError(
                    "evidence digest is reused across roles or slots: "
                    f"{prior_slot}.{prior_field}"
                )
            evidence_roles[value_digest] = (record["slot_id"], field)
        if record["record_kind"] == "executed-source":
            sequences.append(record["result_event_sequence"])
    if sorted(sequences) != list(range(len(sequences))):
        raise VerificationError("result event sequences must be exactly contiguous from zero")
    return _detach(store)


def build_execution_evidence_store(
    program: Any, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    validated = validate_arm_execution_program(program)
    if type(records) not in {list, tuple}:
        raise VerificationError("records must be a sequence")
    store = {
        "schema_version": ARM_EXECUTION_EVIDENCE_STORE_SCHEMA,
        "program_sha256": execution_program_sha256(validated),
        "records": [
            {"record_sha256": sha256_ref(record), "record": _detach(record)}
            for record in records
        ],
    }
    return validate_execution_evidence_store(store, validated)


def _validate_resolution_item(value: Any, path: str) -> dict[str, Any]:
    item = _object(value, path)
    _exact(item, _RESOLUTION_FIELDS, path)
    _identifier(item["slot_id"], f"{path}.slot_id")
    if item["disposition"] not in SLOT_DISPOSITIONS:
        raise VerificationError(f"{path}.disposition is invalid")
    _sha(item["activation_input_sha256"], f"{path}.activation_input_sha256")
    source_digest = _nullable_sha(
        item["source_record_sha256"], f"{path}.source_record_sha256"
    )
    if (item["disposition"] == "not-activated") != (source_digest is None):
        raise VerificationError(
            f"{path} disposition and source-record evidence are inconsistent"
        )
    return _detach(item)


def _record_map(store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        entry["record_sha256"]: entry["record"] for entry in store["records"]
    }


def _validated_prior_map(
    program: Mapping[str, Any],
    resolutions: Any,
    records_by_sha: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    planned_ids = {slot["slot_id"] for slot in program["slots"]}
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(resolutions, "resolutions")):
        item = _validate_resolution_item(raw, f"resolutions[{index}]")
        if item["slot_id"] not in planned_ids:
            raise VerificationError("resolution references an unplanned slot")
        if item["slot_id"] in result:
            raise VerificationError("resolutions contain a duplicate slot")
        source_digest = item["source_record_sha256"]
        if source_digest is not None:
            record = records_by_sha.get(source_digest)
            if record is None or record["slot_id"] != item["slot_id"]:
                raise VerificationError("resolution source record is cross-wired")
            expected_kind = (
                "executed-source"
                if item["disposition"] == "executed"
                else "failure-before-source-record"
            )
            if record["record_kind"] != expected_kind:
                raise VerificationError("resolution source-record kind differs")
        result[item["slot_id"]] = item
    return result


def _activation_preimage(
    *,
    program: Mapping[str, Any],
    slot: Mapping[str, Any],
    prior_by_slot: Mapping[str, Mapping[str, Any]],
    records_by_sha: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], bool | None]:
    fact_inputs: list[dict[str, Any]] = []
    saw_unknown = False
    saw_false = False
    for condition in slot["activation_predicate"]["all_of"]:
        source_resolution = prior_by_slot.get(condition["slot_id"])
        if source_resolution is None:
            raise VerificationError("activation input lacks a dependency resolution")
        source_digest = source_resolution["source_record_sha256"]
        if condition["fact"] == "disposition":
            observed: str | None = source_resolution["disposition"]
        elif source_digest is None:
            observed = None
        else:
            source_record = records_by_sha[source_digest]
            observed = source_record["facts"][condition["fact"]]
        fact_inputs.append(
            {
                "source_slot_id": condition["slot_id"],
                "source_record_sha256": source_digest,
                "fact": condition["fact"],
                "observed_value": observed,
            }
        )
        if observed is None:
            saw_unknown = True
        elif observed not in condition["equals_any"]:
            saw_false = True
    preimage = {
        "schema_version": EXECUTION_PROGRAM_ACTIVATION_INPUT_SCHEMA,
        "program_sha256": execution_program_sha256(program),
        "slot_id": slot["slot_id"],
        "activation_predicate": slot["activation_predicate"],
        "fact_inputs": fact_inputs,
    }
    truth: bool | None = False if saw_false else None if saw_unknown else True
    return preimage, truth


def execution_program_activation_input_sha256(
    program: Any,
    *,
    slot_id: str,
    resolutions: Any,
    evidence_store: Any,
) -> str:
    """Hash activation inputs extracted only from validated source records."""

    validated = validate_arm_execution_program(program)
    store = validate_execution_evidence_store(evidence_store, validated)
    slots = {slot["slot_id"]: slot for slot in validated["slots"]}
    slot = slots.get(slot_id)
    if slot is None:
        raise VerificationError("activation input references an unplanned slot")
    records_by_sha = _record_map(store)
    prior_by_slot = _validated_prior_map(validated, resolutions, records_by_sha)
    preimage, _ = _activation_preimage(
        program=validated,
        slot=slot,
        prior_by_slot=prior_by_slot,
        records_by_sha=records_by_sha,
    )
    return sha256_ref(preimage)


def _resolution_digest(core: Mapping[str, Any]) -> str:
    return sha256_ref(
        {
            "schema_version": EXECUTION_PROGRAM_RESOLUTION_DIGEST_SCHEMA,
            **core,
        }
    )


def resolve_arm_execution_program(
    program: Any,
    resolutions: Any,
    evidence_store: Any,
) -> dict[str, Any]:
    """Resolve every slot and return a self-contained replay closure."""

    validated = validate_arm_execution_program(program)
    store = validate_execution_evidence_store(evidence_store, validated)
    raw_resolutions = _list(resolutions, "resolutions")
    if len(raw_resolutions) != len(validated["slots"]):
        raise VerificationError("resolutions must cover every planned slot exactly once")
    records_by_sha = _record_map(store)
    normalized: list[dict[str, Any]] = []
    prior_by_slot: dict[str, dict[str, Any]] = {}
    used_records: list[str] = []
    executed_slot_ids: list[str] = []
    next_event_sequence = 0
    slots_by_component_task = {
        (slot["task_id"], slot["component"]): slot for slot in validated["slots"]
    }
    for index, (slot, raw) in enumerate(zip(validated["slots"], raw_resolutions)):
        item = _validate_resolution_item(raw, f"resolutions[{index}]")
        if item["slot_id"] != slot["slot_id"]:
            raise VerificationError("resolutions must follow exact planned slot order")
        source_digest = item["source_record_sha256"]
        source_record = None
        if source_digest is not None:
            source_record = records_by_sha.get(source_digest)
            if source_record is None or source_record["slot_id"] != slot["slot_id"]:
                raise VerificationError("resolution source record is cross-wired")
            expected_kind = (
                "executed-source"
                if item["disposition"] == "executed"
                else "failure-before-source-record"
            )
            if source_record["record_kind"] != expected_kind:
                raise VerificationError("resolution source-record kind differs")
            if source_digest in used_records:
                raise VerificationError("source record resolves more than one slot")
            used_records.append(source_digest)
        preimage, truth = _activation_preimage(
            program=validated,
            slot=slot,
            prior_by_slot=prior_by_slot,
            records_by_sha=records_by_sha,
        )
        if item["activation_input_sha256"] != sha256_ref(preimage):
            raise VerificationError("activation input digest differs from source evidence")
        allowed = (
            {"executed", "failed-before-record"}
            if truth is True
            else {"not-activated"}
            if truth is False
            else {"failed-before-record"}
        )
        if item["disposition"] not in allowed:
            state = "true" if truth is True else "false" if truth is False else "unknown"
            raise VerificationError(f"{state} activation has an inconsistent disposition")
        if source_record is not None and item["disposition"] == "executed":
            if source_record["result_event_sequence"] != next_event_sequence:
                raise VerificationError(
                    "result event sequences must follow executed program order"
                )
            next_event_sequence += 1
            executed_slot_ids.append(slot["slot_id"])
        if slot["component"] == "output-validator" and source_record is not None:
            primary_slot = slots_by_component_task[(slot["task_id"], "primary")]
            primary_resolution = prior_by_slot[primary_slot["slot_id"]]
            primary_digest = primary_resolution["source_record_sha256"]
            primary_record = (
                None if primary_digest is None else records_by_sha[primary_digest]
            )
            if source_record["facts"]["output_verdict"] == "valid" and (
                primary_resolution["disposition"] != "executed"
                or primary_record is None
                or primary_record["facts"]["terminal_status"] != "completed"
            ):
                raise VerificationError(
                    "output validator cannot mark a failed/noncompleted primary valid"
                )
        normalized.append(item)
        prior_by_slot[slot["slot_id"]] = item
    store_order = [entry["record_sha256"] for entry in store["records"]]
    if used_records != store_order:
        raise VerificationError(
            "evidence store must contain exactly the used records in program order"
        )
    evidence_store_sha256 = sha256_ref(store)
    core = {
        "program_sha256": execution_program_sha256(validated),
        "evidence_store_sha256": evidence_store_sha256,
        "resolutions": normalized,
        "executed_slot_ids": executed_slot_ids,
    }
    return {
        "schema_version": ARM_EXECUTION_PROGRAM_RESOLUTION_SCHEMA,
        "program_sha256": core["program_sha256"],
        "program": validated,
        "evidence_store_sha256": evidence_store_sha256,
        "evidence_store": store,
        "resolutions": normalized,
        "executed_slot_ids": executed_slot_ids,
        "resolution_sha256": _resolution_digest(core),
    }


def validate_resolved_arm_execution_program(value: Any) -> dict[str, Any]:
    artifact = _object(value, "resolved_program")
    expected_fields = {
        "schema_version",
        "program_sha256",
        "program",
        "evidence_store_sha256",
        "evidence_store",
        "resolutions",
        "executed_slot_ids",
        "resolution_sha256",
    }
    _exact(artifact, expected_fields, "resolved_program")
    if artifact["schema_version"] != ARM_EXECUTION_PROGRAM_RESOLUTION_SCHEMA:
        raise VerificationError("resolved program schema differs")
    _sha(artifact["program_sha256"], "resolved_program.program_sha256")
    _sha(
        artifact["evidence_store_sha256"],
        "resolved_program.evidence_store_sha256",
    )
    _sha(artifact["resolution_sha256"], "resolved_program.resolution_sha256")
    recomputed = resolve_arm_execution_program(
        artifact["program"], artifact["resolutions"], artifact["evidence_store"]
    )
    if canonical_json(artifact) != canonical_json(recomputed):
        raise VerificationError("resolved program closure or digest differs")
    return _detach(artifact)
