"""Canonical, claim-ineligible observations from ``prepare_message``.

The inventory describes the bounded preparation operations that may run.  The
observation tuple is separate and contains only operations that actually ran.
No receiver or judge operation belongs in this preparation-only journal.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import re
from typing import Any

from .canonical import canonical_json, sha256_text, strict_json_loads
from .errors import RoutingError
from .fidelity import FidelityVerification
from .router import RouteDecision
from .sender import CompileOutcome


PREPARATION_JOURNAL_FORMAT = "urusilla-hybrid-preparation-journal/1"
PREPARATION_STAGE_ARTIFACT_FORMAT = (
    "urusilla-hybrid-preparation-stage-artifact/1"
)
PREPARATION_STAGES = (
    "preflight-route",
    "action-control",
    "sender-compiler",
    "compiler-control",
    "fidelity-verifier",
    "final-route",
)
_INVENTORY_SPEC = (
    (0, "preflight-route", False, "deterministic-control"),
    (1, "action-control", False, "deterministic-control"),
    (2, "sender-compiler", True, "model-boundary"),
    (3, "compiler-control", True, "deterministic-control"),
    (4, "fidelity-verifier", True, "fidelity-boundary"),
    (5, "final-route", False, "deterministic-control"),
)
_STAGE_ARTIFACT_SPEC = {
    "preflight-route": ("route-decision", {"route"}),
    "action-control": (
        "control-decision",
        {"decision", "preflight_route_sha256", "reason"},
    ),
    "sender-compiler": ("compile-outcome", {"result"}),
    "compiler-control": (
        "control-decision",
        {"compiler_artifact_sha256", "compiler_status", "decision"},
    ),
    "fidelity-verifier": ("fidelity-verification", {"result"}),
    "final-route": (
        "route-decision",
        {
            "compiler_artifact_sha256",
            "fidelity_artifact_sha256",
            "preflight_route_sha256",
            "route",
        },
    ),
}
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_TEXT_CHUNK_CHARS = 60_000
_TEXT_CHUNK_FORMAT = "urusilla-canonical-text-chunks/1"
_EXECUTED_STAGE_SEQUENCES = {
    (
        "preflight-route",
        "action-control",
        "final-route",
    ),
    (
        "preflight-route",
        "action-control",
        "sender-compiler",
        "compiler-control",
        "final-route",
    ),
    (
        "preflight-route",
        "action-control",
        "sender-compiler",
        "compiler-control",
        "fidelity-verifier",
        "final-route",
    ),
}


def _public_json_value(value: Any) -> Any:
    """Detach public dataclass fields into canonical-JSON-compatible values."""

    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is str:
        if len(value) <= _TEXT_CHUNK_CHARS:
            return value
        return {
            "chunks": [
                value[index : index + _TEXT_CHUNK_CHARS]
                for index in range(0, len(value), _TEXT_CHUNK_CHARS)
            ],
            "format": _TEXT_CHUNK_FORMAT,
            "sha256": sha256_text(value),
            "utf8_bytes": len(value.encode("utf-8")),
        }
    if type(value) is tuple:
        return [_public_json_value(item) for item in value]
    if type(value) is list:
        return [_public_json_value(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise RoutingError("preparation artifact mapping keys must be strings")
        return {
            key: _public_json_value(item)
            for key, item in value.items()
        }
    if is_dataclass(value) and not isinstance(value, type):
        result: dict[str, Any] = {}
        for item in fields(value):
            if item.name.startswith("_"):
                continue
            try:
                field_value = object.__getattribute__(value, item.name)
            except Exception as exc:
                raise RoutingError(
                    "preparation artifact public field could not be read"
                ) from exc
            result[item.name] = _public_json_value(field_value)
        return result
    raise RoutingError(
        "preparation artifact contains a non-public value type: "
        f"{type(value).__name__}"
    )


def _stage_artifact_text(
    stage: str,
    artifact_kind: str,
    value: dict[str, Any],
) -> str:
    if stage not in PREPARATION_STAGES:
        raise RoutingError("preparation observation stage is unknown")
    return canonical_json(
        {
            "artifact_kind": artifact_kind,
            "format": PREPARATION_STAGE_ARTIFACT_FORMAT,
            "stage": stage,
            "value": value,
        }
    )


def _parse_artifact_text(text: str) -> dict[str, Any]:
    try:
        max_bytes = max(1_048_576, len(text.encode("utf-8")))
        value = strict_json_loads(text, max_bytes=max_bytes)
    except (UnicodeError, ValueError) as exc:
        raise RoutingError("preparation observation artifact is invalid") from exc
    if type(value) is not dict:
        raise RoutingError("preparation observation artifact must be an object")
    return value


def _route_artifact_text(stage: str, route: RouteDecision) -> str:
    if type(route) is not RouteDecision:
        raise RoutingError("preparation route observation requires an exact decision")
    return _stage_artifact_text(
        stage,
        "route-decision",
        {"route": _public_json_value(route)},
    )


def _route_root_identity(route: Any) -> tuple[str, str, str, str, str]:
    if type(route) is not dict or type(route.get("request")) is not dict:
        raise RoutingError("preparation route artifact structure is invalid")
    request = route["request"]
    names = (
        (route, "source_sha256"),
        (route, "capsule_sha256"),
        (request, "task_context_sha256"),
        (request, "task_profile_sha256"),
        (request, "symbol_table_sha256"),
    )
    values = tuple(item.get(name) for item, name in names)
    if any(
        type(value) is not str or _SHA256.fullmatch(value) is None
        for value in values
    ):
        raise RoutingError("preparation route artifact binding is invalid")
    return values  # type: ignore[return-value]


@dataclass(frozen=True)
class PreparationStageSlot:
    ordinal: int
    stage: str
    conditional: bool
    operation_kind: str

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise RoutingError("preparation inventory ordinal is invalid")
        if self.stage not in PREPARATION_STAGES:
            raise RoutingError("preparation inventory stage is unknown")
        if type(self.conditional) is not bool:
            raise RoutingError("preparation inventory conditional must be boolean")
        if self.operation_kind not in {
            "deterministic-control",
            "model-boundary",
            "fidelity-boundary",
        }:
            raise RoutingError("preparation inventory operation kind is unknown")

    def to_object(self) -> dict[str, Any]:
        self._validate()
        return {
            "conditional": self.conditional,
            "operation_kind": self.operation_kind,
            "ordinal": self.ordinal,
            "stage": self.stage,
        }


PREPARATION_STAGE_INVENTORY = tuple(
    PreparationStageSlot(*spec) for spec in _INVENTORY_SPEC
)


@dataclass(frozen=True)
class PreparationStageObservation:
    sequence: int
    stage: str
    artifact_text: str
    artifact_sha256: str
    model_calls: int
    model_total_tokens: int | None
    usage_complete: bool

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise RoutingError("preparation observation sequence is invalid")
        if self.stage not in PREPARATION_STAGES:
            raise RoutingError("preparation observation stage is unknown")
        if type(self.artifact_text) is not str:
            raise RoutingError("preparation observation artifact must be text")
        artifact = _parse_artifact_text(self.artifact_text)
        if canonical_json(artifact) != self.artifact_text:
            raise RoutingError("preparation observation artifact is not canonical")
        if (
            type(artifact) is not dict
            or set(artifact) != {"artifact_kind", "format", "stage", "value"}
            or artifact["format"] != PREPARATION_STAGE_ARTIFACT_FORMAT
            or artifact["stage"] != self.stage
            or type(artifact["artifact_kind"]) is not str
            or type(artifact["value"]) is not dict
        ):
            raise RoutingError("preparation observation artifact fields differ")
        expected_kind, expected_value_fields = _STAGE_ARTIFACT_SPEC[self.stage]
        if (
            artifact["artifact_kind"] != expected_kind
            or set(artifact["value"]) != expected_value_fields
        ):
            raise RoutingError("preparation stage artifact payload differs")
        if (
            type(self.artifact_sha256) is not str
            or _SHA256.fullmatch(self.artifact_sha256) is None
            or sha256_text(self.artifact_text) != self.artifact_sha256
        ):
            raise RoutingError("preparation observation artifact digest differs")
        if type(self.model_calls) is not int or self.model_calls not in {0, 1}:
            raise RoutingError("preparation observation model_calls is invalid")
        if self.model_total_tokens is not None and (
            type(self.model_total_tokens) is not int
            or self.model_total_tokens < 0
        ):
            raise RoutingError("preparation observation model usage is invalid")
        if type(self.usage_complete) is not bool:
            raise RoutingError("preparation observation usage flag is invalid")
        if self.model_calls == 0 and not (
            self.model_total_tokens == 0 and self.usage_complete
        ):
            raise RoutingError("local preparation observation usage is inconsistent")
        if self.model_calls == 1 and self.usage_complete is not (
            self.model_total_tokens is not None
        ):
            raise RoutingError("model preparation observation usage is inconsistent")
        if self.stage in {
            "preflight-route",
            "action-control",
            "compiler-control",
            "final-route",
        } and self.model_calls != 0:
            raise RoutingError("preparation control cannot claim a model call")
        if self.stage == "sender-compiler" and self.model_calls != 1:
            raise RoutingError("compiler observation must record its attempted call")
        if self.stage == "sender-compiler":
            result = artifact["value"]["result"]
            if (
                type(result) is not dict
                or result.get("attempted") is not True
                or type(result.get("status")) is not str
                or result.get("total_tokens") != self.model_total_tokens
                or self.usage_complete is not (
                    result.get("total_tokens") is not None
                )
            ):
                raise RoutingError("compiler observation result usage differs")
        if self.stage == "fidelity-verifier":
            result = artifact["value"]["result"]
            if (
                type(result) is not dict
                or result.get("model_calls") != self.model_calls
                or result.get("total_tokens") != self.model_total_tokens
                or result.get("usage_complete") is not self.usage_complete
            ):
                raise RoutingError("fidelity observation result usage differs")

    @property
    def artifact(self) -> dict[str, Any]:
        self._validate()
        return _parse_artifact_text(self.artifact_text)

    def to_object(self) -> dict[str, Any]:
        self._validate()
        return {
            "artifact": self.artifact,
            "artifact_sha256": self.artifact_sha256,
            "model_calls": self.model_calls,
            "model_total_tokens": self.model_total_tokens,
            "sequence": self.sequence,
            "stage": self.stage,
            "usage_complete": self.usage_complete,
        }


@dataclass(frozen=True)
class PreparationJournal:
    source_sha256: str
    capsule_sha256: str
    task_context_sha256: str
    task_profile_sha256: str
    symbol_table_sha256: str
    inventory: tuple[PreparationStageSlot, ...]
    observations: tuple[PreparationStageObservation, ...]
    claim_eligible: bool = False

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        for name in (
            "source_sha256",
            "capsule_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
        ):
            value = object.__getattribute__(self, name)
            if type(value) is not str or _SHA256.fullmatch(value) is None:
                raise RoutingError(f"preparation journal {name} is invalid")
        if type(self.inventory) is not tuple or any(
            type(item) is not PreparationStageSlot for item in self.inventory
        ):
            raise RoutingError("preparation journal inventory is invalid")
        for item in self.inventory:
            item._validate()
        if tuple(
            (
                item.ordinal,
                item.stage,
                item.conditional,
                item.operation_kind,
            )
            for item in self.inventory
        ) != _INVENTORY_SPEC:
            raise RoutingError("preparation journal inventory differs")
        if type(self.observations) is not tuple or any(
            type(item) is not PreparationStageObservation
            for item in self.observations
        ):
            raise RoutingError("preparation journal observations are invalid")
        if tuple(item.sequence for item in self.observations) != tuple(
            range(len(self.observations))
        ):
            raise RoutingError("preparation observation sequence is not contiguous")
        stages = tuple(item.stage for item in self.observations)
        if stages not in _EXECUTED_STAGE_SEQUENCES:
            raise RoutingError("preparation observation chronology is invalid")
        if self.claim_eligible is not False:
            raise RoutingError("preparation journal cannot be claim eligible")
        for item in self.observations:
            item._validate()

        by_stage = {item.stage: item for item in self.observations}
        preflight = by_stage["preflight-route"].artifact
        action = by_stage["action-control"].artifact
        final = by_stage["final-route"].artifact
        preflight_route = preflight["value"]["route"]
        final_route = final["value"]["route"]
        for route in (preflight_route, final_route):
            if _route_root_identity(route) != (
                self.source_sha256,
                self.capsule_sha256,
                self.task_context_sha256,
                self.task_profile_sha256,
                self.symbol_table_sha256,
            ):
                raise RoutingError("preparation journal route binding differs")

        action_value = action["value"]
        if (
            action_value["preflight_route_sha256"]
            != by_stage["preflight-route"].artifact_sha256
            or action_value["decision"]
            not in {"attempt-action-state", "skip-action-state"}
            or type(action_value["reason"]) is not str
            or not action_value["reason"]
        ):
            raise RoutingError("preparation action control is invalid")
        attempted = action_value["decision"] == "attempt-action-state"
        has_compiler = "sender-compiler" in by_stage
        has_fidelity = "fidelity-verifier" in by_stage
        if attempted is not has_compiler:
            raise RoutingError("preparation compiler execution contradicts control")
        if not attempted:
            if preflight_route != final_route:
                raise RoutingError("skipped preparation changed its final route")
        else:
            compiler = by_stage["sender-compiler"]
            compiler_control = by_stage["compiler-control"].artifact["value"]
            compiler_value = compiler.artifact["value"]["result"]
            expected_control = (
                "run-fidelity"
                if compiler_value["status"] == "ok"
                else "skip-fidelity"
            )
            if (
                compiler_control["compiler_artifact_sha256"]
                != compiler.artifact_sha256
                or compiler_control["compiler_status"]
                != compiler_value["status"]
                or compiler_control["decision"] != expected_control
                or has_fidelity is not (expected_control == "run-fidelity")
            ):
                raise RoutingError("preparation compiler control is invalid")

        final_value = final["value"]
        expected_compiler_sha256 = (
            by_stage["sender-compiler"].artifact_sha256
            if has_compiler
            else None
        )
        expected_fidelity_sha256 = (
            by_stage["fidelity-verifier"].artifact_sha256
            if has_fidelity
            else None
        )
        if (
            final_value["preflight_route_sha256"]
            != by_stage["preflight-route"].artifact_sha256
            or final_value["compiler_artifact_sha256"]
            != expected_compiler_sha256
            or final_value["fidelity_artifact_sha256"]
            != expected_fidelity_sha256
        ):
            raise RoutingError("preparation final-route provenance differs")

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)

    def to_object(self) -> dict[str, Any]:
        self._validate()
        return {
            "capsule_sha256": self.capsule_sha256,
            "claim_eligible": False,
            "format": PREPARATION_JOURNAL_FORMAT,
            "inventory": [item.to_object() for item in self.inventory],
            "observations": [item.to_object() for item in self.observations],
            "source_sha256": self.source_sha256,
            "symbol_table_sha256": self.symbol_table_sha256,
            "task_context_sha256": self.task_context_sha256,
            "task_profile_sha256": self.task_profile_sha256,
        }

    def assert_matches(
        self,
        *,
        route: RouteDecision,
        compilation: CompileOutcome | None,
        fidelity_verification: FidelityVerification | None,
    ) -> None:
        """Fail closed if prepared artifacts diverge from recorded preimages."""

        self._validate()
        if type(route) is not RouteDecision:
            raise RoutingError("journal matching requires an exact route decision")
        if compilation is not None and type(compilation) is not CompileOutcome:
            raise RoutingError("journal matching requires an exact compile outcome")
        if (
            fidelity_verification is not None
            and type(fidelity_verification) is not FidelityVerification
        ):
            raise RoutingError(
                "journal matching requires an exact fidelity verification"
            )
        by_stage = {item.stage: item for item in self.observations}
        final_route = by_stage["final-route"].artifact["value"]["route"]
        if final_route != _public_json_value(route):
            raise RoutingError("prepared route differs from its preparation journal")
        compiler = by_stage.get("sender-compiler")
        if (compiler is None) is not (compilation is None):
            raise RoutingError("prepared compilation presence differs from journal")
        if compiler is not None and (
            compiler.artifact["value"]["result"]
            != _public_json_value(compilation)
        ):
            raise RoutingError("prepared compilation differs from journal")
        fidelity = by_stage.get("fidelity-verifier")
        if (fidelity is None) is not (fidelity_verification is None):
            raise RoutingError("prepared fidelity presence differs from journal")
        if fidelity is not None and (
            fidelity.artifact["value"]["result"]
            != _public_json_value(fidelity_verification)
        ):
            raise RoutingError("prepared fidelity result differs from journal")


class PreparationJournalRecorder:
    """Internal append-only recorder used at actual preparation branch points."""

    def __init__(self, preflight_route: RouteDecision):
        if type(preflight_route) is not RouteDecision:
            raise RoutingError("preparation recorder requires an exact preflight route")
        request = preflight_route.request
        self._source_sha256 = preflight_route.source_sha256
        self._capsule_sha256 = preflight_route.capsule_sha256
        self._task_context_sha256 = request.task_context_sha256
        self._task_profile_sha256 = request.task_profile_sha256
        self._symbol_table_sha256 = request.symbol_table_sha256
        self._observations: list[PreparationStageObservation] = []
        self._compiler_artifact_sha256: str | None = None
        self._fidelity_artifact_sha256: str | None = None
        self._finished = False
        self._append_local(
            "preflight-route",
            _route_artifact_text("preflight-route", preflight_route),
        )

    def _append(
        self,
        *,
        stage: str,
        artifact_text: str,
        model_calls: int,
        model_total_tokens: int | None,
        usage_complete: bool,
    ) -> PreparationStageObservation:
        if self._finished:
            raise RoutingError("preparation recorder is already finalized")
        observation = PreparationStageObservation(
            sequence=len(self._observations),
            stage=stage,
            artifact_text=artifact_text,
            artifact_sha256=sha256_text(artifact_text),
            model_calls=model_calls,
            model_total_tokens=model_total_tokens,
            usage_complete=usage_complete,
        )
        self._observations.append(observation)
        return observation

    def _append_local(
        self, stage: str, artifact_text: str
    ) -> PreparationStageObservation:
        return self._append(
            stage=stage,
            artifact_text=artifact_text,
            model_calls=0,
            model_total_tokens=0,
            usage_complete=True,
        )

    def record_action_control(self, decision: str, reason: str) -> None:
        if decision not in {"attempt-action-state", "skip-action-state"}:
            raise RoutingError("preparation action decision is invalid")
        if type(reason) is not str or not reason:
            raise RoutingError("preparation action decision reason is invalid")
        preflight = self._observations[0]
        self._append_local(
            "action-control",
            _stage_artifact_text(
                "action-control",
                "control-decision",
                {
                    "decision": decision,
                    "preflight_route_sha256": preflight.artifact_sha256,
                    "reason": reason,
                },
            ),
        )

    def record_compiler(self, compilation: CompileOutcome) -> None:
        if type(compilation) is not CompileOutcome or not compilation.attempted:
            raise RoutingError("preparation compiler observation is invalid")
        observation = self._append(
            stage="sender-compiler",
            artifact_text=_stage_artifact_text(
                "sender-compiler",
                "compile-outcome",
                {"result": _public_json_value(compilation)},
            ),
            model_calls=1,
            model_total_tokens=compilation.total_tokens,
            usage_complete=compilation.total_tokens is not None,
        )
        self._compiler_artifact_sha256 = observation.artifact_sha256

    def record_compiler_control(self, compilation: CompileOutcome) -> None:
        if self._compiler_artifact_sha256 is None:
            raise RoutingError("compiler control requires a compiler observation")
        decision = (
            "run-fidelity" if compilation.status == "ok" else "skip-fidelity"
        )
        self._append_local(
            "compiler-control",
            _stage_artifact_text(
                "compiler-control",
                "control-decision",
                {
                    "compiler_artifact_sha256": self._compiler_artifact_sha256,
                    "compiler_status": compilation.status,
                    "decision": decision,
                },
            ),
        )

    def record_fidelity(self, verification: FidelityVerification) -> None:
        if type(verification) is not FidelityVerification:
            raise RoutingError("preparation fidelity observation is invalid")
        observation = self._append(
            stage="fidelity-verifier",
            artifact_text=_stage_artifact_text(
                "fidelity-verifier",
                "fidelity-verification",
                {"result": _public_json_value(verification)},
            ),
            model_calls=verification.model_calls,
            model_total_tokens=verification.total_tokens,
            usage_complete=verification.usage_complete,
        )
        self._fidelity_artifact_sha256 = observation.artifact_sha256

    def finish(self, final_route: RouteDecision) -> PreparationJournal:
        preflight = self._observations[0]
        self._append_local(
            "final-route",
            _stage_artifact_text(
                "final-route",
                "route-decision",
                {
                    "compiler_artifact_sha256": self._compiler_artifact_sha256,
                    "fidelity_artifact_sha256": self._fidelity_artifact_sha256,
                    "preflight_route_sha256": preflight.artifact_sha256,
                    "route": _public_json_value(final_route),
                },
            ),
        )
        self._finished = True
        return PreparationJournal(
            source_sha256=self._source_sha256,
            capsule_sha256=self._capsule_sha256,
            task_context_sha256=self._task_context_sha256,
            task_profile_sha256=self._task_profile_sha256,
            symbol_table_sha256=self._symbol_table_sha256,
            inventory=tuple(
                PreparationStageSlot(*spec) for spec in _INVENTORY_SPEC
            ),
            observations=tuple(self._observations),
            claim_eligible=False,
        )


__all__ = [
    "PREPARATION_JOURNAL_FORMAT",
    "PREPARATION_STAGE_ARTIFACT_FORMAT",
    "PREPARATION_STAGE_INVENTORY",
    "PREPARATION_STAGES",
    "PreparationJournal",
    "PreparationStageObservation",
    "PreparationStageSlot",
]
