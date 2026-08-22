"""Claim-ineligible perfect-sender receiver-ceiling diagnostic.

The runner owns no provider client and performs no network I/O.  A host injects
the same provider boundary used by ``matched_session_pilot``.  One deterministic
normative record produces three bytewise-distinct representations: concise raw
text, descriptive canonical JSON, and canonical ``PublicActionState``.  The
sender therefore makes zero model calls; this is a receiver ceiling only.

The injected callback is outside this module's security boundary.  A matching
handoff and ``offline_synthetic`` attribute are only host declarations: they do
not authenticate, sandbox, or prove that the callback is offline.  A callback
exception is therefore preserved as an attempted call with unknown usage and
rejects the run.  All result authority, claim, version, adoption, authenticity,
and independence flags remain false.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass
import inspect
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence

from initial_goal_eval.matched_session_pilot import (
    ComprehensionProviderResult,
    MatchedSessionProvider,
    NormalizedProviderUsage,
    ProviderCallCapture,
    ReceiverProviderResult,
)
from urusilla_hybrid_runtime.canonical import (
    canonical_json,
    sha256_text,
    strict_json_loads,
)
from urusilla_hybrid_runtime.comprehension import (
    ColdStartComprehensionChallenge,
    ComprehensionModelReply,
    ReceiverModelBinding,
    build_cold_start_comprehension_challenge,
    run_cold_start_comprehension,
)
from urusilla_hybrid_runtime.receiver import (
    DirectReceiverRequest,
    ReceiverModelReply,
    build_action_state_request,
    build_json_request,
    build_raw_request,
)
from urusilla_hybrid_runtime.records import Capsule, PublicActionState
from urusilla_hybrid_runtime.session import (
    ProviderReceiptBinding,
    SessionError,
    SessionTurnCall,
    SessionTurnProviderReply,
    execute_session_turn,
    open_receiver_session,
    prepare_session_turn,
)
from urusilla_hybrid_runtime.session_runtime import (
    mint_session_cached_receiver,
)
from urusilla_hybrid_runtime.task_context import (
    PublicTaskContext,
    validate_state_against_task_context,
)


RUN_FORMAT = "urusilla-perfect-sender-receiver-ceiling-run/1"
FIXTURE_FORMAT = "urusilla-perfect-sender-task-fixture/1"
PREFLIGHT_FORMAT = "urusilla-receiver-ceiling-preflight-handoff/1"
JOURNAL_FORMAT = "urusilla-receiver-ceiling-attempt/1"
SCORER_SHA256 = sha256_text(
    "receiver-ceiling-deterministic-exact-output-scorer-v1"
)
ARMS = ("raw", "json", "action-state")
PHASES = (
    "setup",
    "comprehension",
    "sender",
    "fidelity",
    "router",
    "primary",
    "validator",
    "repair",
    "fallback",
    "tool",
    "safety",
    "judge",
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_JOURNAL_REQUEST_BYTES = 1_048_576
_TASK_RESULT_FACTORY_TOKEN = object()
_RUN_RESULT_FACTORY_TOKEN = object()


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ReceiverCeilingError(f"{label} must be an exact sha256 digest")
    return value


def _require_text(value: object, label: str, *, limit: int = 1_048_576) -> str:
    if type(value) is not str or not value:
        raise ReceiverCeilingError(f"{label} must be non-empty text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReceiverCeilingError(f"{label} is not UTF-8") from exc
    if len(encoded) > limit:
        raise ReceiverCeilingError(f"{label} exceeds its byte limit")
    return value


def _describe_atom(value: Mapping[str, Any] | None) -> str:
    if value is None:
        return "none"
    negated = "not " if value["n"] else ""
    arguments = ",".join(canonical_json(item) for item in value["a"])
    source = "unknown" if value["src"] is None else str(value["src"])
    return f"{negated}{value['p']}({arguments}) from {source}"


def _render_raw(item_id: str, state: PublicActionState) -> str:
    value = state.to_object()
    facts = "; ".join(_describe_atom(item) for item in value["state"]) or "none"
    constraints = (
        "; ".join(
            f"{_describe_atom(item)} ({'hard' if item['hard'] else 'soft'})"
            for item in value["constraints"]
        )
        or "none"
    )
    needs = "; ".join(_describe_atom(item) for item in value["needs"]) or "none"
    action = value["action"]
    action_text = (
        "none"
        if action is None
        else f"{action['name']} args={canonical_json(action['args'])} "
        f"status={action['status']} effects={canonical_json(action['effects'])}"
    )
    outcome = value["outcome"]
    outcome_text = (
        "none"
        if outcome is None
        else f"{outcome['status']} value={canonical_json(outcome['value'])}"
    )
    return (
        f"Item {item_id}. Act: {value['act']}. Goal: "
        f"{_describe_atom(value['goal'])}. Facts: {facts}. Constraints: "
        f"{constraints}. Action: {action_text}. Outcome: {outcome_text}. "
        f"Needs: {needs}. Return only the task-contract output."
    )


def _ordinary_atom(value: Mapping[str, Any] | None) -> object:
    if value is None:
        return None
    return {
        "arguments": value["a"],
        "is_negated": value["n"],
        "predicate": value["p"],
        "source": value["src"],
    }


def _render_json(item_id: str, state: PublicActionState) -> str:
    value = state.to_object()
    return canonical_json(
        {
            "communicative_act": value["act"],
            "constraints": [
                {
                    **_ordinary_atom(item),
                    "is_hard": item["hard"],
                }
                for item in value["constraints"]
            ],
            "goal": _ordinary_atom(value["goal"]),
            "item_id": item_id,
            "known_facts": [_ordinary_atom(item) for item in value["state"]],
            "needs": [_ordinary_atom(item) for item in value["needs"]],
            "outcome": value["outcome"],
            "proposed_action": value["action"],
            "uncertainty": value["uncertainty"],
        }
    )


@dataclass(frozen=True)
class PerfectSenderTaskFixture:
    """Three deterministic renderings content-bound to one normative record."""

    item_id: str
    task_context_sha256: str
    normative_text: str
    normative_sha256: str
    raw_concise_text: str
    ordinary_json_text: str
    action_state: PublicActionState
    expected_output_text: str
    representation_binding_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.item_id, "fixture item_id", limit=256)
        _require_sha256(self.task_context_sha256, "fixture task_context_sha256")
        _require_sha256(self.normative_sha256, "fixture normative_sha256")
        _require_sha256(
            self.representation_binding_sha256,
            "fixture representation_binding_sha256",
        )
        _require_text(self.expected_output_text, "fixture expected_output_text")
        if type(self.action_state) is not PublicActionState:
            raise ReceiverCeilingError("fixture action_state type is invalid")
        try:
            normative = strict_json_loads(self.normative_text)
        except ValueError as exc:
            raise ReceiverCeilingError("fixture normative record is invalid") from exc
        if canonical_json(normative) != self.normative_text:
            raise ReceiverCeilingError("fixture normative record is not canonical")
        if type(normative) is not dict or set(normative) != {
            "format",
            "item_id",
            "task_context_sha256",
            "public_action_state",
            "expected_output_text",
        }:
            raise ReceiverCeilingError("fixture normative fields differ")
        if normative["format"] != FIXTURE_FORMAT:
            raise ReceiverCeilingError("fixture format is unknown")
        if (
            normative["item_id"] != self.item_id
            or normative["task_context_sha256"] != self.task_context_sha256
            or normative["public_action_state"] != self.action_state.to_object()
            or normative["expected_output_text"] != self.expected_output_text
            or sha256_text(self.normative_text) != self.normative_sha256
        ):
            raise ReceiverCeilingError("fixture differs from its normative record")
        expected_raw = _render_raw(self.item_id, self.action_state)
        expected_json = _render_json(self.item_id, self.action_state)
        if self.raw_concise_text != expected_raw:
            raise ReceiverCeilingError("raw rendering is not deterministic")
        if self.ordinary_json_text != expected_json:
            raise ReceiverCeilingError("ordinary JSON rendering is not deterministic")
        strict_json_loads(self.ordinary_json_text)
        payloads = (
            self.raw_concise_text.encode("utf-8"),
            self.ordinary_json_text.encode("utf-8"),
            self.action_state.canonical_text.encode("utf-8"),
        )
        if len(set(payloads)) != 3:
            raise ReceiverCeilingError("fixture payloads must be bytewise distinct")
        if self.representation_binding_sha256 != sha256_text(
            canonical_json(self.representation_binding_object)
        ):
            raise ReceiverCeilingError("fixture representation binding differs")

    @classmethod
    def from_state(
        cls,
        *,
        item_id: str,
        task_context: PublicTaskContext,
        action_state: PublicActionState,
        expected_output_text: str,
    ) -> "PerfectSenderTaskFixture":
        if type(task_context) is not PublicTaskContext:
            raise ReceiverCeilingError("fixture requires exact task context")
        validate_state_against_task_context(action_state, task_context)
        normative_text = canonical_json(
            {
                "format": FIXTURE_FORMAT,
                "item_id": item_id,
                "task_context_sha256": task_context.sha256,
                "public_action_state": action_state.to_object(),
                "expected_output_text": expected_output_text,
            }
        )
        raw = _render_raw(item_id, action_state)
        ordinary_json = _render_json(item_id, action_state)
        normative_sha256 = sha256_text(normative_text)
        binding = {
            "normative_sha256": normative_sha256,
            "raw_sha256": sha256_text(raw),
            "ordinary_json_sha256": sha256_text(ordinary_json),
            "action_state_sha256": action_state.sha256,
        }
        return cls(
            item_id=item_id,
            task_context_sha256=task_context.sha256,
            normative_text=normative_text,
            normative_sha256=normative_sha256,
            raw_concise_text=raw,
            ordinary_json_text=ordinary_json,
            action_state=action_state,
            expected_output_text=expected_output_text,
            representation_binding_sha256=sha256_text(canonical_json(binding)),
        )

    @property
    def representation_binding_object(self) -> dict[str, str]:
        return {
            "normative_sha256": self.normative_sha256,
            "raw_sha256": sha256_text(self.raw_concise_text),
            "ordinary_json_sha256": sha256_text(self.ordinary_json_text),
            "action_state_sha256": self.action_state.sha256,
        }

    def validate_for(self, task_context: PublicTaskContext) -> None:
        if self.task_context_sha256 != task_context.sha256:
            raise ReceiverCeilingError("fixture task context binding differs")
        validate_state_against_task_context(self.action_state, task_context)

    def to_object(self) -> dict[str, object]:
        return {
            "format": FIXTURE_FORMAT,
            "item_id": self.item_id,
            "task_context_sha256": self.task_context_sha256,
            "normative_text": self.normative_text,
            "normative_sha256": self.normative_sha256,
            "raw_concise_text": self.raw_concise_text,
            "ordinary_json_text": self.ordinary_json_text,
            "action_state_text": self.action_state.canonical_text,
            "expected_output_text": self.expected_output_text,
            "representation_binding": self.representation_binding_object,
            "representation_binding_sha256": self.representation_binding_sha256,
            "perfect_sender_model_calls": 0,
        }


def _snapshot_fixtures(
    fixtures: Sequence[PerfectSenderTaskFixture],
) -> tuple[PerfectSenderTaskFixture, ...]:
    return tuple(
        PerfectSenderTaskFixture(
            item_id=item.item_id,
            task_context_sha256=item.task_context_sha256,
            normative_text=item.normative_text,
            normative_sha256=item.normative_sha256,
            raw_concise_text=item.raw_concise_text,
            ordinary_json_text=item.ordinary_json_text,
            action_state=PublicActionState.from_object(
                item.action_state.to_object()
            ),
            expected_output_text=item.expected_output_text,
            representation_binding_sha256=(
                item.representation_binding_sha256
            ),
        )
        for item in fixtures
    )


def _receiver_ceiling_experiment_manifest(
    *,
    capsule: Capsule,
    task_context: PublicTaskContext,
    receiver_binding: ReceiverModelBinding,
    fixtures: Sequence[PerfectSenderTaskFixture],
    arm_order: Sequence[str],
    maximum_comprehension_tokens: int,
    maximum_receiver_tokens: int,
) -> dict[str, object]:
    tasks = _snapshot_fixtures(fixtures)
    arms = tuple(arm_order)
    if not tasks:
        raise ReceiverCeilingError("receiver ceiling requires at least one task")
    if set(arms) != set(ARMS) or len(arms) != len(ARMS):
        raise ReceiverCeilingError("arm_order must be one exact permutation")
    if len({item.item_id for item in tasks}) != len(tasks):
        raise ReceiverCeilingError("task order contains duplicate item ids")
    for item in tasks:
        if type(item) is not PerfectSenderTaskFixture:
            raise ReceiverCeilingError("task fixture type is invalid")
        item.validate_for(task_context)
    for value, label in (
        (maximum_comprehension_tokens, "maximum_comprehension_tokens"),
        (maximum_receiver_tokens, "maximum_receiver_tokens"),
    ):
        if type(value) is not int or value <= 0:
            raise ReceiverCeilingError(f"{label} must be positive")
    comprehension_challenge = build_cold_start_comprehension_challenge(
        capsule,
        task_context,
        receiver_binding,
        maximum_total_tokens=maximum_comprehension_tokens,
    )
    return {
        "format": RUN_FORMAT,
        "capsule_sha256": capsule.sha256,
        "capsule_text": capsule.canonical_text,
        "task_context_sha256": task_context.sha256,
        "task_context_text": task_context.canonical_text,
        "receiver_binding_sha256": receiver_binding.sha256,
        "receiver_model_id": receiver_binding.model_id,
        "receiver_settings_sha256": receiver_binding.settings_sha256,
        "comprehension_request_sha256": (
            comprehension_challenge.model_visible_sha256
        ),
        "task_order": [item.item_id for item in tasks],
        "tasks": [
            {
                "item_id": item.item_id,
                "representation_binding_sha256": (
                    item.representation_binding_sha256
                ),
                "expected_output_sha256": sha256_text(
                    item.expected_output_text
                ),
                "raw_request_sha256": sha256_text(
                    _baseline_request(
                        "raw",
                        item,
                        task_context,
                        maximum_receiver_tokens,
                    ).model_visible_text
                ),
                "json_request_sha256": sha256_text(
                    _baseline_request(
                        "json",
                        item,
                        task_context,
                        maximum_receiver_tokens,
                    ).model_visible_text
                ),
                "action_state_request_sha256": sha256_text(
                    "PAYLOAD\n" + item.action_state.canonical_text
                ),
            }
            for item in tasks
        ],
        "session_length": len(tasks),
        "arm_order": list(arms),
        "maximum_comprehension_tokens": maximum_comprehension_tokens,
        "maximum_receiver_tokens": maximum_receiver_tokens,
    }


def receiver_ceiling_experiment_binding_sha256(
    *,
    capsule: Capsule,
    task_context: PublicTaskContext,
    receiver_binding: ReceiverModelBinding,
    fixtures: Sequence[PerfectSenderTaskFixture],
    arm_order: Sequence[str],
    maximum_comprehension_tokens: int,
    maximum_receiver_tokens: int,
) -> str:
    manifest = _receiver_ceiling_experiment_manifest(
        capsule=capsule,
        task_context=task_context,
        receiver_binding=receiver_binding,
        fixtures=fixtures,
        arm_order=arm_order,
        maximum_comprehension_tokens=maximum_comprehension_tokens,
        maximum_receiver_tokens=maximum_receiver_tokens,
    )
    return sha256_text(canonical_json(manifest))


@dataclass(frozen=True)
class SyntheticReceiverCeilingAuthorization:
    """Content-bound host declaration; never external-call authorization.

    The object is intentionally constructible by any caller.  It binds inputs
    and prevents accidental mismatches, but it is not a signature, permission,
    or sandbox.  In particular, this is not derived from either
    ``finite_bound_preflight_v1.numeric_screen_permitted`` or the content-bound
    compiler's ``numeric_screen_permitted`` / ``eligible_session_lengths``.
    Those are arithmetic-only facts: an eligible N is neither selected nor
    authorized and cannot hand off to this runner.
    """

    canonical_text: str
    sha256: str

    def __post_init__(self) -> None:
        try:
            value = strict_json_loads(self.canonical_text)
        except ValueError as exc:
            raise ReceiverCeilingError("preflight handoff is invalid JSON") from exc
        if canonical_json(value) != self.canonical_text:
            raise ReceiverCeilingError("preflight handoff is not canonical")
        if type(value) is not dict or set(value) != {
            "format",
            "experiment_binding_sha256",
            "selected_session_length",
            "synthetic_fixture_screen_passed",
            "all_retained_cells_not_disproven",
            "worst_cell_residual_positive",
            "authorization_scope",
            "live_provider_calls_authorized",
        }:
            raise ReceiverCeilingError("preflight handoff fields differ")
        if value["format"] != PREFLIGHT_FORMAT:
            raise ReceiverCeilingError("preflight handoff format is unknown")
        if (
            value["authorization_scope"] != "synthetic-test-only"
            or value["live_provider_calls_authorized"] is not False
        ):
            raise ReceiverCeilingError(
                "this local handoff can authorize synthetic tests only"
            )
        _require_sha256(
            value["experiment_binding_sha256"],
            "preflight experiment binding",
        )
        length = value["selected_session_length"]
        if length is not None and (type(length) is not int or length <= 0):
            raise ReceiverCeilingError("selected session length is invalid")
        for key in (
            "synthetic_fixture_screen_passed",
            "all_retained_cells_not_disproven",
            "worst_cell_residual_positive",
        ):
            if type(value[key]) is not bool:
                raise ReceiverCeilingError(f"preflight {key} must be boolean")
        if self.sha256 != sha256_text(self.canonical_text):
            raise ReceiverCeilingError("preflight handoff digest differs")

    @classmethod
    def from_values(
        cls,
        *,
        experiment_binding_sha256: str,
        selected_session_length: int | None,
        synthetic_fixture_screen_passed: bool,
        all_retained_cells_not_disproven: bool,
        worst_cell_residual_positive: bool,
    ) -> "SyntheticReceiverCeilingAuthorization":
        value = {
            "format": PREFLIGHT_FORMAT,
            "experiment_binding_sha256": experiment_binding_sha256,
            "selected_session_length": selected_session_length,
            "synthetic_fixture_screen_passed": synthetic_fixture_screen_passed,
            "all_retained_cells_not_disproven": (
                all_retained_cells_not_disproven
            ),
            "worst_cell_residual_positive": worst_cell_residual_positive,
            "authorization_scope": "synthetic-test-only",
            "live_provider_calls_authorized": False,
        }
        text = canonical_json(value)
        return cls(text, sha256_text(text))

    @property
    def value(self) -> dict[str, object]:
        parsed = strict_json_loads(self.canonical_text)
        assert type(parsed) is dict
        return parsed

    def require_authorized(self, experiment_sha256: str, length: int) -> None:
        value = self.value
        if (
            value["experiment_binding_sha256"] != experiment_sha256
            or value["selected_session_length"] != length
            or value["synthetic_fixture_screen_passed"] is not True
            or value["all_retained_cells_not_disproven"] is not True
            or value["worst_cell_residual_positive"] is not True
            or value["authorization_scope"] != "synthetic-test-only"
            or value["live_provider_calls_authorized"] is not False
        ):
            raise ReceiverCeilingError(
                "preflight cannot authorize this exact known-N experiment"
            )


@dataclass(frozen=True)
class ReceiverCeilingAttempt:
    sequence: int
    phase: str
    arm: str
    item_id: str | None
    request_scope: str
    request_text: str
    response_text: str | None
    capture: ProviderCallCapture | None
    disposition: str = "captured"
    failure: str | None = None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ReceiverCeilingError("journal sequence is invalid")
        if self.phase not in {"comprehension", "primary"}:
            raise ReceiverCeilingError("journal phase is invalid")
        if self.arm not in (*ARMS, "action-state-comprehension"):
            raise ReceiverCeilingError("journal arm is invalid")
        if self.request_scope not in {"root-model-visible", "same-context-user"}:
            raise ReceiverCeilingError("journal request scope is invalid")
        _require_text(
            self.request_text,
            "journal request_text",
            limit=_MAX_JOURNAL_REQUEST_BYTES,
        )
        if self.disposition == "captured":
            if type(self.capture) is not ProviderCallCapture:
                raise ReceiverCeilingError("captured journal entry requires capture")
            if self.failure is not None:
                raise ReceiverCeilingError("captured journal entry cannot have failure")
            if self.capture.request_content_sha256 != sha256_text(self.request_text):
                raise ReceiverCeilingError("journal request capture differs")
            if self.response_text is None:
                if self.capture.response_content_sha256 is not None:
                    raise ReceiverCeilingError("journal response omission differs")
            else:
                _require_text(
                    self.response_text,
                    "journal response_text",
                    limit=_MAX_JOURNAL_REQUEST_BYTES,
                )
                if self.capture.response_content_sha256 != sha256_text(
                    self.response_text
                ):
                    raise ReceiverCeilingError("journal response capture differs")
        elif self.disposition == "callback-error":
            if self.capture is not None or self.response_text is not None:
                raise ReceiverCeilingError(
                    "callback-error entry cannot assert response or capture"
                )
            _require_text(self.failure, "journal callback failure", limit=256)
        else:
            raise ReceiverCeilingError("journal disposition is invalid")

    def to_object(self) -> dict[str, object]:
        return {
            "format": JOURNAL_FORMAT,
            "sequence": self.sequence,
            "phase": self.phase,
            "arm": self.arm,
            "item_id": self.item_id,
            "request_scope": self.request_scope,
            "request_text": self.request_text,
            "request_sha256": sha256_text(self.request_text),
            "response_text": self.response_text,
            "response_sha256": (
                None if self.response_text is None else sha256_text(self.response_text)
            ),
            "provider_callback_attempted": True,
            "disposition": self.disposition,
            "failure": self.failure,
            "capture": None if self.capture is None else self.capture.to_object(),
            "capture_binding_sha256": (
                None if self.capture is None else self.capture.binding_sha256
            ),
            "usage_complete": (
                False if self.capture is None else self.capture.usage.usage_complete
            ),
        }


@dataclass(frozen=True)
class ReceiverCeilingTaskResult:
    arm: str
    item_id: str
    expected_output_sha256: str
    status: str
    output_text: str | None
    exact_score: bool
    provider_call_performed: bool
    capture_binding_sha256: str | None
    _factory_token: InitVar[object] = None

    def __post_init__(self, _factory_token: object) -> None:
        if _factory_token is not _TASK_RESULT_FACTORY_TOKEN:
            raise ReceiverCeilingError(
                "task result construction is factory-sealed"
            )
        if self.arm not in ARMS:
            raise ReceiverCeilingError("task result arm is invalid")
        _require_text(self.item_id, "task result item_id", limit=256)
        _require_sha256(
            self.expected_output_sha256,
            "task result expected output",
        )
        if self.status not in {
            "completed",
            "provider-failed",
            "not-run-comprehension-failed",
            "not-run-session-invalid",
        }:
            raise ReceiverCeilingError("task result status is invalid")
        if type(self.exact_score) is not bool:
            raise ReceiverCeilingError("task result exact score must be boolean")
        if type(self.provider_call_performed) is not bool:
            raise ReceiverCeilingError(
                "task result provider callback flag must be boolean"
            )
        expected_match = (
            self.output_text is not None
            and sha256_text(self.output_text) == self.expected_output_sha256
        )
        if self.exact_score is not expected_match:
            raise ReceiverCeilingError(
                "task result exact score differs from expected output binding"
            )
        if self.capture_binding_sha256 is not None:
            _require_sha256(
                self.capture_binding_sha256,
                "task result capture binding",
            )
        if self.status == "completed":
            _require_text(self.output_text, "completed task output")
            if not self.provider_call_performed or self.capture_binding_sha256 is None:
                raise ReceiverCeilingError(
                    "completed task requires returned callback and capture"
                )
        elif self.status == "provider-failed":
            if (
                self.output_text is not None
                or self.exact_score
                or not self.provider_call_performed
                or self.capture_binding_sha256 is None
            ):
                raise ReceiverCeilingError(
                    "provider-failed task result is internally inconsistent"
                )
        elif (
            self.output_text is not None
            or self.exact_score
            or self.provider_call_performed
            or self.capture_binding_sha256 is not None
        ):
            raise ReceiverCeilingError("not-run task result is internally inconsistent")

    def to_object(self) -> dict[str, object]:
        return {
            "arm": self.arm,
            "item_id": self.item_id,
            "expected_output_sha256": self.expected_output_sha256,
            "status": self.status,
            "output_text": self.output_text,
            "output_sha256": (
                None if self.output_text is None else sha256_text(self.output_text)
            ),
            "deterministic_scorer_sha256": SCORER_SHA256,
            "diagnostic_exact_match": self.exact_score,
            "safe_success": None,
            "provider_callback_returned": self.provider_call_performed,
            "capture_binding_sha256": self.capture_binding_sha256,
            "judge_model_calls": 0,
        }


class ReceiverCeilingError(ValueError):
    """Fail-closed diagnostic error with any already-observed calls attached."""

    def __init__(
        self,
        message: str,
        *,
        journal: Sequence[ReceiverCeilingAttempt] = (),
    ) -> None:
        super().__init__(message)
        self.journal = tuple(journal)

    def to_object(self) -> dict[str, object]:
        return {
            "format": RUN_FORMAT,
            "status": "rejected",
            "failure": str(self),
            "journal": [item.to_object() for item in self.journal],
            "usage_complete": False,
            "inclusive_total_tokens": None,
            "safely_completed": None,
            "callback_scope_authenticated": False,
            "synthetic_boundary_enforced": False,
            **_false_flags(),
        }


class ReceiverCeilingCallbackInterrupt(BaseException):
    """Guaranteed journal carrier when an interrupt rejects attribute attachment."""

    def __init__(
        self,
        original: BaseException,
        error: ReceiverCeilingError,
    ) -> None:
        super().__init__(
            "provider callback interrupted; attempted-call journal is attached"
        )
        self.original = original
        self.receiver_ceiling_journal = error.journal
        self.receiver_ceiling_failure = str(error)


def _false_flags() -> dict[str, bool]:
    return {
        "authority_created": False,
        "claim_eligible": False,
        "performance_claim_eligible": False,
        "protocol_conformance_claim_eligible": False,
        "protocol_version_ratified": False,
        "adoption_verified": False,
        "independent_reproduction_verified": False,
        "provider_authenticity_verified": False,
        "receipt_authenticated": False,
        "operator_independence_validated": False,
        "preregistration_chronology_verified": False,
    }


@dataclass(frozen=True)
class PerfectSenderMatchedSessionResult:
    experiment_binding_sha256: str
    experiment_manifest_text: str
    preflight_sha256: str
    preflight_text: str
    task_order: tuple[str, ...]
    arm_order: tuple[str, ...]
    comprehension_passed: bool
    comprehension_failure: str | None
    task_results: tuple[ReceiverCeilingTaskResult, ...]
    journal: tuple[ReceiverCeilingAttempt, ...]
    _factory_token: InitVar[object] = None

    def __post_init__(self, _factory_token: object) -> None:
        if _factory_token is not _RUN_RESULT_FACTORY_TOKEN:
            raise ReceiverCeilingError(
                "matched-session result construction is factory-sealed"
            )
        _require_sha256(
            self.experiment_binding_sha256,
            "result experiment binding",
        )
        _require_sha256(self.preflight_sha256, "result preflight binding")
        _require_text(
            self.experiment_manifest_text,
            "result experiment manifest",
        )
        _require_text(self.preflight_text, "result preflight handoff")
        if (
            type(self.task_order) is not tuple
            or not self.task_order
            or len(set(self.task_order)) != len(self.task_order)
        ):
            raise ReceiverCeilingError("result task order is invalid")
        for item_id in self.task_order:
            _require_text(item_id, "result task item_id", limit=256)
        if (
            type(self.arm_order) is not tuple
            or set(self.arm_order) != set(ARMS)
            or len(self.arm_order) != len(ARMS)
        ):
            raise ReceiverCeilingError("result arm order is invalid")
        try:
            manifest = strict_json_loads(self.experiment_manifest_text)
        except ValueError as exc:
            raise ReceiverCeilingError(
                "result experiment manifest is invalid JSON"
            ) from exc
        if canonical_json(manifest) != self.experiment_manifest_text:
            raise ReceiverCeilingError(
                "result experiment manifest is not canonical"
            )
        if type(manifest) is not dict or set(manifest) != {
            "format",
            "capsule_sha256",
            "capsule_text",
            "task_context_sha256",
            "task_context_text",
            "receiver_binding_sha256",
            "receiver_model_id",
            "receiver_settings_sha256",
            "comprehension_request_sha256",
            "task_order",
            "tasks",
            "session_length",
            "arm_order",
            "maximum_comprehension_tokens",
            "maximum_receiver_tokens",
        }:
            raise ReceiverCeilingError(
                "result experiment manifest fields differ"
            )
        if manifest["format"] != RUN_FORMAT:
            raise ReceiverCeilingError(
                "result experiment manifest format is unknown"
            )
        for key in (
            "capsule_sha256",
            "task_context_sha256",
            "receiver_binding_sha256",
            "receiver_settings_sha256",
            "comprehension_request_sha256",
        ):
            _require_sha256(manifest[key], f"result manifest {key}")
        _require_text(manifest["capsule_text"], "result manifest Capsule")
        _require_text(
            manifest["task_context_text"],
            "result manifest task context",
        )
        try:
            manifest_capsule = Capsule(
                canonical_text=manifest["capsule_text"],
                sha256=manifest["capsule_sha256"],
                path=Path("experiment-manifest-capsule.json"),
            )
            manifest_task_context = PublicTaskContext(
                canonical_text=manifest["task_context_text"],
                sha256=manifest["task_context_sha256"],
            )
            manifest_receiver_binding = ReceiverModelBinding(
                model_id=manifest["receiver_model_id"],
                settings_sha256=manifest["receiver_settings_sha256"],
            )
        except ValueError as exc:
            raise ReceiverCeilingError(
                "result manifest public inputs are invalid"
            ) from exc
        if (
            manifest_receiver_binding.sha256
            != manifest["receiver_binding_sha256"]
        ):
            raise ReceiverCeilingError(
                "result manifest receiver binding digest differs"
            )
        if (
            manifest["task_order"] != list(self.task_order)
            or manifest["arm_order"] != list(self.arm_order)
            or manifest["session_length"] != len(self.task_order)
        ):
            raise ReceiverCeilingError(
                "result ordering differs from its experiment manifest"
            )
        for key in (
            "maximum_comprehension_tokens",
            "maximum_receiver_tokens",
        ):
            if type(manifest[key]) is not int or manifest[key] <= 0:
                raise ReceiverCeilingError(
                    f"result manifest {key} must be positive"
                )
        manifest_tasks = manifest["tasks"]
        if type(manifest_tasks) is not list or len(manifest_tasks) != len(
            self.task_order
        ):
            raise ReceiverCeilingError("result manifest task cells differ")
        expected_output_by_item: dict[str, str] = {}
        request_sha256_by_cell: dict[tuple[str, str], str] = {}
        for index, manifest_task in enumerate(manifest_tasks):
            if type(manifest_task) is not dict or set(manifest_task) != {
                "item_id",
                "representation_binding_sha256",
                "expected_output_sha256",
                "raw_request_sha256",
                "json_request_sha256",
                "action_state_request_sha256",
            }:
                raise ReceiverCeilingError(
                    "result manifest task fields differ"
                )
            item_id = manifest_task["item_id"]
            if item_id != self.task_order[index]:
                raise ReceiverCeilingError(
                    "result manifest task order differs"
                )
            _require_sha256(
                manifest_task["representation_binding_sha256"],
                "result manifest representation binding",
            )
            expected_output_by_item[item_id] = _require_sha256(
                manifest_task["expected_output_sha256"],
                "result manifest expected output",
            )
            for arm, key in (
                ("raw", "raw_request_sha256"),
                ("json", "json_request_sha256"),
                ("action-state", "action_state_request_sha256"),
            ):
                request_sha256_by_cell[(arm, item_id)] = _require_sha256(
                    manifest_task[key],
                    f"result manifest {arm} request",
                )
        if self.experiment_binding_sha256 != sha256_text(
            self.experiment_manifest_text
        ):
            raise ReceiverCeilingError(
                "result experiment manifest binding differs"
            )
        authorization = SyntheticReceiverCeilingAuthorization(
            self.preflight_text,
            self.preflight_sha256,
        )
        authorization.require_authorized(
            self.experiment_binding_sha256,
            len(self.task_order),
        )
        if type(self.comprehension_passed) is not bool:
            raise ReceiverCeilingError("result comprehension flag must be boolean")
        if self.comprehension_passed:
            if self.comprehension_failure is not None:
                raise ReceiverCeilingError(
                    "passed comprehension cannot have a failure"
                )
        else:
            _require_text(
                self.comprehension_failure,
                "failed comprehension reason",
                limit=256,
            )
        if type(self.task_results) is not tuple or type(self.journal) is not tuple:
            raise ReceiverCeilingError("result collections must be exact tuples")
        if any(type(item) is not ReceiverCeilingTaskResult for item in self.task_results):
            raise ReceiverCeilingError("result contains an invalid task result")
        if any(type(item) is not ReceiverCeilingAttempt for item in self.journal):
            raise ReceiverCeilingError("result contains an invalid journal entry")
        if [item.sequence for item in self.journal] != list(range(len(self.journal))):
            raise ReceiverCeilingError("result journal sequence is not contiguous")
        if any(item.disposition != "captured" for item in self.journal):
            raise ReceiverCeilingError(
                "completed diagnostic cannot contain an uncaptured callback"
            )
        comprehension_entries = [
            item for item in self.journal if item.phase == "comprehension"
        ]
        if (
            len(comprehension_entries) != 1
            or comprehension_entries[0].arm != "action-state-comprehension"
        ):
            raise ReceiverCeilingError(
                "completed diagnostic requires one comprehension capture"
            )
        for item in self.journal:
            assert item.capture is not None
            if (
                not item.capture.usage.usage_complete
                or not item.capture.safety_boundary_clear
                or not item.capture.continuity_clear
                or item.capture.retry_count != 0
                or item.capture.repair_count != 0
            ):
                raise ReceiverCeilingError(
                    "completed diagnostic contains a non-eligible capture"
                )
            token_cap = (
                manifest["maximum_comprehension_tokens"]
                if item.phase == "comprehension"
                else manifest["maximum_receiver_tokens"]
            )
            assert item.capture.usage.provider_total_tokens is not None
            if item.capture.usage.provider_total_tokens > token_cap:
                raise ReceiverCeilingError(
                    "journal capture exceeds its experiment token cap"
                )
            if item.phase == "comprehension" and (
                item.response_text is None
                or item.capture.terminal_status != "completed"
            ):
                raise ReceiverCeilingError(
                    "comprehension journal contradicts its captured terminal"
                )
        comprehension_entry = comprehension_entries[0]
        comprehension_capture = comprehension_entry.capture
        assert comprehension_capture is not None
        assert comprehension_entry.response_text is not None
        usage = comprehension_capture.usage
        try:
            reconstructed_challenge = build_cold_start_comprehension_challenge(
                manifest_capsule,
                manifest_task_context,
                manifest_receiver_binding,
                maximum_total_tokens=manifest[
                    "maximum_comprehension_tokens"
                ],
            )
            reconstructed_reply = ComprehensionModelReply(
                text=comprehension_entry.response_text,
                model_id=comprehension_capture.resolved_model_id,
                model_settings_sha256=(
                    comprehension_capture.model_settings_sha256
                ),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                reasoning_accounting=usage.reasoning_accounting,
                provider_total_tokens=usage.provider_total_tokens,
                tools_used=comprehension_capture.tools_used,
                persistence_created=comprehension_capture.persistence_created,
                permission_expanded=comprehension_capture.permission_expanded,
                spending_authority_created=(
                    comprehension_capture.spending_authority_created
                ),
                external_effects_performed=(
                    comprehension_capture.external_effects_performed
                ),
            )
            derived_comprehension = run_cold_start_comprehension(
                manifest_capsule,
                manifest_task_context,
                manifest_receiver_binding,
                _StaticComprehensionAdapter(reconstructed_reply),
                maximum_total_tokens=manifest[
                    "maximum_comprehension_tokens"
                ],
            )
        except ValueError as exc:
            raise ReceiverCeilingError(
                "captured comprehension cannot be revalidated"
            ) from exc
        if (
            reconstructed_challenge.model_visible_text
            != comprehension_entry.request_text
            or reconstructed_challenge.model_visible_sha256
            != manifest["comprehension_request_sha256"]
        ):
            raise ReceiverCeilingError(
                "comprehension request differs from deterministic challenge"
            )
        if (
            derived_comprehension.passed != self.comprehension_passed
            or derived_comprehension.failure != self.comprehension_failure
        ):
            raise ReceiverCeilingError(
                "comprehension result differs from captured response"
            )
        expected_cells = {
            (arm, item_id) for arm in ARMS for item_id in self.task_order
        }
        actual_cells = {(item.arm, item.item_id) for item in self.task_results}
        if (
            len(self.task_results) != len(expected_cells)
            or actual_cells != expected_cells
        ):
            raise ReceiverCeilingError("result task cells are incomplete or duplicated")
        if any(
            item.expected_output_sha256
            != expected_output_by_item[item.item_id]
            for item in self.task_results
        ):
            raise ReceiverCeilingError(
                "task result expected output differs from experiment manifest"
            )
        action_results = [
            item for item in self.task_results if item.arm == "action-state"
        ]
        action_by_item = {item.item_id: item for item in action_results}
        baseline_results = [
            item for item in self.task_results if item.arm in {"raw", "json"}
        ]
        if any(
            not item.provider_call_performed
            or item.status not in {"completed", "provider-failed"}
            for item in baseline_results
        ):
            raise ReceiverCeilingError(
                "completed diagnostic requires every baseline callback cell"
            )
        if not self.comprehension_passed and any(
            item.status != "not-run-comprehension-failed" for item in action_results
        ):
            raise ReceiverCeilingError(
                "failed comprehension cannot have action-state task calls"
            )
        if self.comprehension_passed and any(
            item.status == "not-run-comprehension-failed" for item in action_results
        ):
            raise ReceiverCeilingError(
                "passed comprehension cannot emit comprehension-failed cells"
            )
        if self.comprehension_passed:
            session_terminated = False
            for item_id in self.task_order:
                item = action_by_item[item_id]
                if not session_terminated:
                    if item.status == "completed":
                        continue
                    if item.status == "provider-failed":
                        session_terminated = True
                        continue
                    raise ReceiverCeilingError(
                        "action-state session has an unaccounted call gap"
                    )
                if item.status != "not-run-session-invalid":
                    raise ReceiverCeilingError(
                        "action-state calls continued after session failure"
                    )
        expected_journal_order: list[tuple[str, str, str | None, str]] = []
        for arm in self.arm_order:
            if arm == "action-state":
                expected_journal_order.append(
                    (
                        "comprehension",
                        "action-state-comprehension",
                        None,
                        "root-model-visible",
                    )
                )
                if self.comprehension_passed:
                    for item_id in self.task_order:
                        if action_by_item[item_id].provider_call_performed:
                            expected_journal_order.append(
                                (
                                    "primary",
                                    "action-state",
                                    item_id,
                                    "same-context-user",
                                )
                            )
            else:
                expected_journal_order.extend(
                    (
                        "primary",
                        arm,
                        item_id,
                        "root-model-visible",
                    )
                    for item_id in self.task_order
                )
        actual_journal_order = [
            (item.phase, item.arm, item.item_id, item.request_scope)
            for item in self.journal
        ]
        if actual_journal_order != expected_journal_order:
            raise ReceiverCeilingError(
                "result journal differs from exact experiment call order"
            )
        for attempt in self.journal:
            expected_request_sha256 = (
                manifest["comprehension_request_sha256"]
                if attempt.phase == "comprehension"
                else request_sha256_by_cell[(attempt.arm, attempt.item_id)]
            )
            if sha256_text(attempt.request_text) != expected_request_sha256:
                raise ReceiverCeilingError(
                    "journal request differs from experiment target binding"
                )
        if (
            comprehension_capture.parent_response_id is not None
            or comprehension_capture.response_id is None
        ):
            raise ReceiverCeilingError(
                "comprehension capture is not a fresh session root"
            )
        provider_id = comprehension_capture.provider_id
        session_context_id = comprehension_capture.context_id
        session_parent_response_id = comprehension_capture.response_id
        session_response_ids = {session_parent_response_id}
        baseline_context_ids: set[str] = set()
        for attempt in self.journal:
            capture = attempt.capture
            assert capture is not None
            if (
                capture.provider_id != provider_id
                or capture.resolved_model_id != manifest["receiver_model_id"]
                or capture.model_settings_sha256
                != manifest["receiver_settings_sha256"]
            ):
                raise ReceiverCeilingError(
                    "journal provider or receiver binding changed"
                )
            if attempt.phase == "comprehension":
                continue
            if attempt.arm == "action-state":
                if (
                    capture.context_id != session_context_id
                    or capture.parent_response_id
                    != session_parent_response_id
                ):
                    raise ReceiverCeilingError(
                        "action-state capture breaks session lineage"
                    )
                if attempt.response_text is not None:
                    if capture.response_id is None:
                        raise ReceiverCeilingError(
                            "completed session capture has no response id"
                        )
                    if capture.response_id in session_response_ids:
                        raise ReceiverCeilingError(
                            "action-state response id is reused"
                        )
                    session_response_ids.add(capture.response_id)
                    session_parent_response_id = capture.response_id
                continue
            if (
                capture.parent_response_id is not None
                or capture.context_id == session_context_id
                or capture.context_id in baseline_context_ids
            ):
                raise ReceiverCeilingError(
                    "baseline capture is not a fresh root context"
                )
            baseline_context_ids.add(capture.context_id)
        primary_by_cell: dict[tuple[str, str], ReceiverCeilingAttempt] = {}
        for attempt in self.journal:
            if attempt.phase != "primary":
                continue
            if attempt.item_id is None:
                raise ReceiverCeilingError("primary journal entry requires item_id")
            cell = (attempt.arm, attempt.item_id)
            if cell in primary_by_cell:
                raise ReceiverCeilingError("primary journal cell is duplicated")
            primary_by_cell[cell] = attempt
        for item in self.task_results:
            cell = (item.arm, item.item_id)
            if item.provider_call_performed:
                attempt = primary_by_cell.get(cell)
                if (
                    attempt is None
                    or attempt.capture is None
                    or item.capture_binding_sha256
                    != attempt.capture.binding_sha256
                ):
                    raise ReceiverCeilingError(
                        "task result capture is absent from its journal cell"
                    )
                if item.output_text != attempt.response_text:
                    raise ReceiverCeilingError(
                        "task result output differs from its journal response"
                    )
                assert attempt.capture is not None
                if item.status == "completed":
                    if (
                        attempt.response_text is None
                        or attempt.capture.terminal_status != "completed"
                    ):
                        raise ReceiverCeilingError(
                            "completed task contradicts its captured terminal"
                        )
                elif (
                    item.status != "provider-failed"
                    or attempt.response_text is not None
                    or attempt.capture.terminal_status == "completed"
                ):
                    raise ReceiverCeilingError(
                        "failed task contradicts its captured terminal"
                    )
            elif cell in primary_by_cell:
                raise ReceiverCeilingError(
                    "not-run task result contradicts its journal cell"
                )

    @property
    def total_provider_tokens(self) -> int:
        return sum(
            item.capture.usage.provider_total_tokens or 0
            for item in self.journal
            if item.capture is not None
        )

    def to_object(self) -> dict[str, object]:
        phase_calls = {phase: 0 for phase in PHASES}
        phase_tokens = {phase: 0 for phase in PHASES}
        for item in self.journal:
            phase_calls[item.phase] += 1
            assert item.capture is not None
            assert item.capture.usage.provider_total_tokens is not None
            phase_tokens[item.phase] += item.capture.usage.provider_total_tokens
        phases = {
            phase: {
                "model_calls": phase_calls[phase],
                "provider_total_tokens": phase_tokens[phase],
            }
            for phase in PHASES
        }
        phases["sender"]["deterministic_perfect_sender"] = True
        phases["judge"]["deterministic_scorer_calls"] = sum(
            item.provider_call_performed for item in self.task_results
        )
        usage = [
            item.capture.usage for item in self.journal if item.capture is not None
        ]
        input_tokens = sum(item.input_tokens or 0 for item in usage)
        output_tokens = sum(item.output_tokens or 0 for item in usage)
        separate_reasoning_tokens = sum(
            item.reasoning_tokens or 0
            for item in usage
            if item.reasoning_accounting == "separately-reported"
        )
        unclassified = sum(
            (item.provider_total_tokens or 0)
            - (item.input_tokens or 0)
            - (item.output_tokens or 0)
            - (
                item.reasoning_tokens
                if item.reasoning_accounting == "separately-reported"
                and item.reasoning_tokens is not None
                else 0
            )
            for item in usage
            if item.reasoning_accounting == "not-reported"
        )
        value = {
            "format": RUN_FORMAT,
            "status": "completed",
            "experiment_binding_sha256": self.experiment_binding_sha256,
            "experiment_manifest_text": self.experiment_manifest_text,
            "preflight_sha256": self.preflight_sha256,
            "preflight_text": self.preflight_text,
            "task_order": list(self.task_order),
            "arm_order": list(self.arm_order),
            "comprehension_passed": self.comprehension_passed,
            "comprehension_failure": self.comprehension_failure,
            "perfect_sender": {
                "deterministic": True,
                "model_calls": 0,
                "model_tokens": 0,
            },
            "task_results": [item.to_object() for item in self.task_results],
            "journal": [item.to_object() for item in self.journal],
            "journal_sha256": sha256_text(
                canonical_json([item.to_object() for item in self.journal])
            ),
            "phase_accounting": phases,
            "diagnostic_usage": {
                "complete": True,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "separately_reported_reasoning_tokens": (
                    separate_reasoning_tokens
                ),
                "provider_total_tokens": self.total_provider_tokens,
                "unclassified_tokens": unclassified,
            },
            "repair_calls": 0,
            "fallback_calls": 0,
            "host_declared_offline_synthetic": True,
            "callback_scope_authenticated": False,
            "synthetic_boundary_enforced": False,
            "returned_captures_reported_boundary_clear": True,
            "unauthorized_effects": None,
            "usage_complete": False,
            "inclusive_total_tokens": None,
            "safely_completed": None,
            **_false_flags(),
        }
        return value

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())


class ReceiverCeilingProvider(MatchedSessionProvider, Protocol):
    """Provider protocol alias: implementations remain fully host injected."""


def _provider_receipts(capture: ProviderCallCapture) -> ProviderReceiptBinding:
    if capture.response_content_sha256 is None:
        raise ReceiverCeilingError("provider receipt requires response content")
    raw = capture.raw_receipt_sha256
    return ProviderReceiptBinding(
        request_content_sha256=capture.request_content_sha256,
        response_content_sha256=capture.response_content_sha256,
        provider_request_receipt_sha256=sha256_text(
            canonical_json(
                {
                    "provider_id": capture.provider_id,
                    "context_id": capture.context_id,
                    "request_id": capture.request_id,
                    "request_sha256": capture.request_content_sha256,
                    "raw_receipt_sha256": raw,
                }
            )
        ),
        provider_response_receipt_sha256=sha256_text(
            canonical_json(
                {
                    "provider_id": capture.provider_id,
                    "context_id": capture.context_id,
                    "response_id": capture.response_id,
                    "response_sha256": capture.response_content_sha256,
                    "raw_receipt_sha256": raw,
                }
            )
        ),
        provider_context_receipt_sha256=sha256_text(
            canonical_json(
                {
                    "provider_id": capture.provider_id,
                    "context_id": capture.context_id,
                    "continuation_binding_sha256": (
                        capture.continuation_binding_sha256
                    ),
                    "raw_receipt_sha256": raw,
                }
            )
        ),
    )


def _raise_with_journal(message: str, journal: Sequence[ReceiverCeilingAttempt]) -> None:
    raise ReceiverCeilingError(message, journal=journal)


def _require_request_text(value: object, label: str) -> str:
    """Reject an unjournalable request before host callback resolution."""

    return _require_text(
        value,
        label,
        limit=_MAX_JOURNAL_REQUEST_BYTES,
    )


def _require_static_provider_interface(provider: object) -> None:
    """Inspect the declared interface without executing dynamic descriptors."""

    for name in (
        "complete_comprehension",
        "complete_receiver",
        "complete_session_turn",
    ):
        member = inspect.getattr_static(provider, name, None)
        if isinstance(member, (classmethod, staticmethod)):
            member = member.__func__
        if not callable(member):
            raise ReceiverCeilingError(
                f"provider boundary is missing static callable {name}"
            )
    if inspect.getattr_static(provider, "offline_synthetic", None) is not True:
        raise ReceiverCeilingError(
            "host must statically declare offline_synthetic=True; this declaration "
            "is not authenticated or sandbox-enforced"
        )


def _uncaptured_callback_error(
    *,
    journal: list[ReceiverCeilingAttempt],
    phase: str,
    arm: str,
    item_id: str | None,
    request_scope: str,
    request_text: str,
    failure: str,
) -> ReceiverCeilingError:
    """Preserve that host code was invoked when no exact capture was returned."""

    journal.append(
        ReceiverCeilingAttempt(
            sequence=len(journal),
            phase=phase,
            arm=arm,
            item_id=item_id,
            request_scope=request_scope,
            request_text=request_text,
            response_text=None,
            capture=None,
            disposition="callback-error",
            failure=failure,
        )
    )
    return ReceiverCeilingError(
        "provider callback returned no verifiable capture; usage is unknown",
        journal=journal,
    )


def _raise_or_propagate_callback_failure(
    exc: BaseException,
    error: ReceiverCeilingError,
) -> None:
    """Preserve interrupts while attaching the exact attempted-call journal."""

    if isinstance(exc, Exception):
        raise error from exc
    raise ReceiverCeilingCallbackInterrupt(exc, error) from exc


def _validate_capture(
    result: ComprehensionProviderResult | ReceiverProviderResult,
    *,
    receiver_binding: ReceiverModelBinding,
    expected_request_sha256: str,
    expected_provider_id: str | None,
    expected_context_id: str | None,
    expected_parent_response_id: str | None,
    maximum_tokens: int,
    journal: Sequence[ReceiverCeilingAttempt],
) -> str:
    capture = result.capture
    if not capture.usage.usage_complete:
        _raise_with_journal("provider usage is unknown", journal)
    if capture.retry_count != 0 or capture.repair_count != 0:
        _raise_with_journal("implicit retry or repair is prohibited", journal)
    if not capture.safety_boundary_clear:
        _raise_with_journal("provider crossed a prohibited effect boundary", journal)
    if not capture.continuity_clear:
        _raise_with_journal("provider context reset or compaction was observed", journal)
    if capture.request_content_sha256 != expected_request_sha256:
        _raise_with_journal("provider request digest differs", journal)
    if expected_provider_id is not None and capture.provider_id != expected_provider_id:
        _raise_with_journal("provider identity changed", journal)
    if (
        capture.resolved_model_id != receiver_binding.model_id
        or capture.model_settings_sha256 != receiver_binding.settings_sha256
    ):
        _raise_with_journal("receiver model or settings changed", journal)
    if expected_context_id is not None and capture.context_id != expected_context_id:
        _raise_with_journal("same-context receiver context changed", journal)
    if capture.parent_response_id != expected_parent_response_id:
        _raise_with_journal("provider parent response binding differs", journal)
    total = capture.usage.provider_total_tokens
    assert total is not None
    if total > maximum_tokens:
        _raise_with_journal("provider token ceiling was exceeded", journal)
    reply = result.reply
    if reply is not None:
        if reply.model_id != receiver_binding.model_id:
            _raise_with_journal("provider reply model identity changed", journal)
        if (
            type(reply) is ComprehensionModelReply
            and reply.model_settings_sha256 != receiver_binding.settings_sha256
        ):
            _raise_with_journal("comprehension reply settings changed", journal)
        if capture.terminal_status != "completed":
            _raise_with_journal("live reply has non-completed capture", journal)
        if capture.response_content_sha256 != sha256_text(reply.text):
            _raise_with_journal("provider response digest differs", journal)
        expected_usage = (
            NormalizedProviderUsage.from_comprehension_reply(reply)
            if type(reply) is ComprehensionModelReply
            else NormalizedProviderUsage.from_receiver_reply(reply)
        )
        if capture.usage != expected_usage:
            _raise_with_journal("provider capture usage differs from reply", journal)
    return capture.provider_id


class _StaticComprehensionAdapter:
    def __init__(self, reply: ComprehensionModelReply) -> None:
        self.reply = reply

    def complete(
        self, challenge: ColdStartComprehensionChallenge
    ) -> ComprehensionModelReply:
        return self.reply


class _HotAdapter:
    def __init__(
        self,
        *,
        provider: ReceiverCeilingProvider,
        receiver_binding: ReceiverModelBinding,
        provider_id: str,
        context_id: str,
        parent_response_id: str,
        item_id: str,
        maximum_tokens: int,
        journal: list[ReceiverCeilingAttempt],
    ) -> None:
        self.provider = provider
        self.receiver_binding = receiver_binding
        self.provider_id = provider_id
        self.context_id = context_id
        self.parent_response_id = parent_response_id
        self.item_id = item_id
        self.maximum_tokens = maximum_tokens
        self.journal = journal
        self.result: ReceiverProviderResult | None = None
        self.fatal: ReceiverCeilingError | None = None

    def complete_session_turn(
        self, raw_provider_handle: object, call: SessionTurnCall
    ) -> SessionTurnProviderReply:
        request_text = _require_request_text(
            call.request_text,
            "hot provider request",
        )
        lease_snapshot = (
            call.lease.model_settings_sha256,
            call.lease.system_sha256,
            call.lease.context_epoch,
            call.lease.sha256,
            call.lease.turn,
            call.lease.parent_transcript_chain_sha256,
        )
        try:
            result = self.provider.complete_session_turn(raw_provider_handle, call)
        except BaseException as exc:
            self.fatal = _uncaptured_callback_error(
                journal=self.journal,
                phase="primary",
                arm="action-state",
                item_id=self.item_id,
                request_scope="same-context-user",
                request_text=request_text,
                failure="callback-raised",
            )
            _raise_or_propagate_callback_failure(exc, self.fatal)
        if type(result) is not ReceiverProviderResult:
            self.fatal = _uncaptured_callback_error(
                journal=self.journal,
                phase="primary",
                arm="action-state",
                item_id=self.item_id,
                request_scope="same-context-user",
                request_text=request_text,
                failure="callback-return-invalid-type",
            )
            raise self.fatal
        try:
            result = ReceiverProviderResult(
                reply=result.reply,
                capture=result.capture,
            )
            entry = ReceiverCeilingAttempt(
                sequence=len(self.journal),
                phase="primary",
                arm="action-state",
                item_id=self.item_id,
                request_scope="same-context-user",
                request_text=request_text,
                response_text=None if result.reply is None else result.reply.text,
                capture=result.capture,
            )
        except BaseException as exc:
            self.result = None
            self.fatal = _uncaptured_callback_error(
                journal=self.journal,
                phase="primary",
                arm="action-state",
                item_id=self.item_id,
                request_scope="same-context-user",
                request_text=request_text,
                failure="callback-return-incoherent-capture",
            )
            _raise_or_propagate_callback_failure(exc, self.fatal)
        self.result = result
        self.journal.append(entry)
        try:
            _validate_capture(
                result,
                receiver_binding=self.receiver_binding,
                expected_request_sha256=sha256_text(request_text),
                expected_provider_id=self.provider_id,
                expected_context_id=self.context_id,
                expected_parent_response_id=self.parent_response_id,
                maximum_tokens=self.maximum_tokens,
                journal=self.journal,
            )
        except ReceiverCeilingError as exc:
            self.fatal = exc
            raise
        if result.reply is None:
            raise SessionError("hot provider call did not complete")
        (
            model_settings_sha256,
            system_sha256,
            context_epoch,
            lease_sha256,
            turn,
            parent_transcript_chain_sha256,
        ) = lease_snapshot
        return SessionTurnProviderReply(
            reply=result.reply,
            model_settings_sha256=model_settings_sha256,
            system_sha256=system_sha256,
            context_epoch=context_epoch,
            lease_sha256=lease_sha256,
            turn=turn,
            parent_transcript_chain_sha256=parent_transcript_chain_sha256,
            receipts=_provider_receipts(result.capture),
            context_reset_observed=result.capture.context_reset_observed,
            context_compaction_observed=result.capture.context_compaction_observed,
        )


def _baseline_request(
    arm: str,
    fixture: PerfectSenderTaskFixture,
    task_context: PublicTaskContext,
    maximum_tokens: int,
) -> DirectReceiverRequest:
    if arm == "raw":
        request = build_raw_request(
            fixture.raw_concise_text,
            task_context,
            maximum_total_tokens=maximum_tokens,
        )
    elif arm == "json":
        request = build_json_request(
            fixture.ordinary_json_text,
            task_context,
            maximum_total_tokens=maximum_tokens,
        )
        if request.payload_text != fixture.ordinary_json_text:
            raise ReceiverCeilingError("strong ordinary JSON payload was rewritten")
    else:
        raise ReceiverCeilingError("baseline arm is invalid")
    return request


def _run_perfect_sender_matched_session_impl(
    *,
    capsule: Capsule,
    task_context: PublicTaskContext,
    receiver_binding: ReceiverModelBinding,
    provider: ReceiverCeilingProvider,
    fixtures: Sequence[PerfectSenderTaskFixture],
    arm_order: Sequence[str],
    preflight: SyntheticReceiverCeilingAuthorization,
    maximum_comprehension_tokens: int,
    maximum_receiver_tokens: int,
    _journal: list[ReceiverCeilingAttempt],
) -> PerfectSenderMatchedSessionResult:
    """Execute one fixed-order, perfect-sender, claim-ineligible session."""

    if type(capsule) is not Capsule:
        raise ReceiverCeilingError("receiver ceiling requires exact Capsule type")
    if type(task_context) is not PublicTaskContext:
        raise ReceiverCeilingError(
            "receiver ceiling requires exact task-context type"
        )
    if type(receiver_binding) is not ReceiverModelBinding:
        raise ReceiverCeilingError(
            "receiver ceiling requires exact receiver-binding type"
        )
    capsule = Capsule(
        canonical_text=capsule.canonical_text,
        sha256=capsule.sha256,
        path=capsule.path,
    )
    task_context = PublicTaskContext(
        canonical_text=task_context.canonical_text,
        sha256=task_context.sha256,
    )
    receiver_binding = ReceiverModelBinding(
        model_id=receiver_binding.model_id,
        settings_sha256=receiver_binding.settings_sha256,
    )
    tasks = _snapshot_fixtures(fixtures)
    arms = tuple(arm_order)
    task_order = tuple(item.item_id for item in tasks)
    experiment_manifest_text = canonical_json(
        _receiver_ceiling_experiment_manifest(
            capsule=capsule,
            task_context=task_context,
            receiver_binding=receiver_binding,
            fixtures=tasks,
            arm_order=arms,
            maximum_comprehension_tokens=maximum_comprehension_tokens,
            maximum_receiver_tokens=maximum_receiver_tokens,
        )
    )
    experiment_sha256 = sha256_text(experiment_manifest_text)
    if type(preflight) is not SyntheticReceiverCeilingAuthorization:
        raise ReceiverCeilingError(
            "exact synthetic authorization type is required; arithmetic preflight "
            "readiness cannot authorize receiver calls"
        )
    preflight.require_authorized(experiment_sha256, len(tasks))
    _require_static_provider_interface(provider)

    journal = _journal
    results: list[ReceiverCeilingTaskResult] = []
    provider_id: str | None = None
    root_context_ids: set[str] = set()
    comprehension_passed = False
    comprehension_failure: str | None = "not-run"

    for arm in arms:
        if arm in {"raw", "json"}:
            for fixture in tasks:
                request = _baseline_request(
                    arm, fixture, task_context, maximum_receiver_tokens
                )
                request_text = _require_request_text(
                    request.model_visible_text,
                    "baseline model-visible request",
                )
                try:
                    result = provider.complete_receiver(arm, request)
                except BaseException as exc:
                    error = _uncaptured_callback_error(
                        journal=journal,
                        phase="primary",
                        arm=arm,
                        item_id=fixture.item_id,
                        request_scope="root-model-visible",
                        request_text=request_text,
                        failure="callback-raised",
                    )
                    _raise_or_propagate_callback_failure(exc, error)
                if type(result) is not ReceiverProviderResult:
                    raise _uncaptured_callback_error(
                        journal=journal,
                        phase="primary",
                        arm=arm,
                        item_id=fixture.item_id,
                        request_scope="root-model-visible",
                        request_text=request_text,
                        failure="callback-return-invalid-type",
                    )
                try:
                    result = ReceiverProviderResult(
                        reply=result.reply,
                        capture=result.capture,
                    )
                    entry = ReceiverCeilingAttempt(
                        sequence=len(journal),
                        phase="primary",
                        arm=arm,
                        item_id=fixture.item_id,
                        request_scope="root-model-visible",
                        request_text=request_text,
                        response_text=None if result.reply is None else result.reply.text,
                        capture=result.capture,
                    )
                except BaseException as exc:
                    error = _uncaptured_callback_error(
                        journal=journal,
                        phase="primary",
                        arm=arm,
                        item_id=fixture.item_id,
                        request_scope="root-model-visible",
                        request_text=request_text,
                        failure="callback-return-incoherent-capture",
                    )
                    _raise_or_propagate_callback_failure(exc, error)
                journal.append(entry)
                provider_id = _validate_capture(
                    result,
                    receiver_binding=receiver_binding,
                    expected_request_sha256=sha256_text(request_text),
                    expected_provider_id=provider_id,
                    expected_context_id=None,
                    expected_parent_response_id=None,
                    maximum_tokens=maximum_receiver_tokens,
                    journal=journal,
                )
                if result.capture.context_id in root_context_ids:
                    _raise_with_journal(
                        "baseline calls must use fresh root contexts", journal
                    )
                root_context_ids.add(result.capture.context_id)
                output = None if result.reply is None else result.reply.text
                exact = output == fixture.expected_output_text
                results.append(
                    ReceiverCeilingTaskResult(
                        arm=arm,
                        item_id=fixture.item_id,
                        expected_output_sha256=sha256_text(
                            fixture.expected_output_text
                        ),
                        status="completed" if result.reply is not None else "provider-failed",
                        output_text=output,
                        exact_score=exact,
                        provider_call_performed=True,
                        capture_binding_sha256=result.capture.binding_sha256,
                        _factory_token=_TASK_RESULT_FACTORY_TOKEN,
                    )
                )
            continue

        challenge = build_cold_start_comprehension_challenge(
            capsule,
            task_context,
            receiver_binding,
            maximum_total_tokens=maximum_comprehension_tokens,
        )
        challenge_request_text = _require_request_text(
            challenge.model_visible_text,
            "comprehension model-visible request",
        )
        challenge_request_sha256 = sha256_text(challenge_request_text)
        try:
            comprehension = provider.complete_comprehension(challenge)
        except BaseException as exc:
            error = _uncaptured_callback_error(
                journal=journal,
                phase="comprehension",
                arm="action-state-comprehension",
                item_id=None,
                request_scope="root-model-visible",
                request_text=challenge_request_text,
                failure="callback-raised",
            )
            _raise_or_propagate_callback_failure(exc, error)
        if type(comprehension) is not ComprehensionProviderResult:
            raise _uncaptured_callback_error(
                journal=journal,
                phase="comprehension",
                arm="action-state-comprehension",
                item_id=None,
                request_scope="root-model-visible",
                request_text=challenge_request_text,
                failure="callback-return-invalid-type",
            )
        try:
            comprehension = ComprehensionProviderResult(
                reply=comprehension.reply,
                capture=comprehension.capture,
                raw_provider_handle=comprehension.raw_provider_handle,
                context_epoch=comprehension.context_epoch,
                session_nonce=comprehension.session_nonce,
            )
            comprehension_entry = ReceiverCeilingAttempt(
                sequence=len(journal),
                phase="comprehension",
                arm="action-state-comprehension",
                item_id=None,
                request_scope="root-model-visible",
                request_text=challenge_request_text,
                response_text=comprehension.reply.text,
                capture=comprehension.capture,
            )
        except BaseException as exc:
            error = _uncaptured_callback_error(
                journal=journal,
                phase="comprehension",
                arm="action-state-comprehension",
                item_id=None,
                request_scope="root-model-visible",
                request_text=challenge_request_text,
                failure="callback-return-incoherent-capture",
            )
            _raise_or_propagate_callback_failure(exc, error)
        journal.append(comprehension_entry)
        provider_id = _validate_capture(
            comprehension,
            receiver_binding=receiver_binding,
            expected_request_sha256=challenge_request_sha256,
            expected_provider_id=provider_id,
            expected_context_id=None,
            expected_parent_response_id=None,
            maximum_tokens=maximum_comprehension_tokens,
            journal=journal,
        )
        if comprehension.capture.context_id in root_context_ids:
            _raise_with_journal(
                "comprehension must use a fresh action-state context", journal
            )
        root_context_ids.add(comprehension.capture.context_id)
        attempt = run_cold_start_comprehension(
            capsule,
            task_context,
            receiver_binding,
            _StaticComprehensionAdapter(comprehension.reply),
            maximum_total_tokens=maximum_comprehension_tokens,
        )
        comprehension_passed = attempt.passed
        comprehension_failure = attempt.failure
        if not attempt.passed:
            for fixture in tasks:
                results.append(
                    ReceiverCeilingTaskResult(
                        arm="action-state",
                        item_id=fixture.item_id,
                        expected_output_sha256=sha256_text(
                            fixture.expected_output_text
                        ),
                        status="not-run-comprehension-failed",
                        output_text=None,
                        exact_score=False,
                        provider_call_performed=False,
                        capture_binding_sha256=None,
                        _factory_token=_TASK_RESULT_FACTORY_TOKEN,
                    )
                )
            continue

        session = open_receiver_session(
            attempt,
            raw_provider_handle=comprehension.raw_provider_handle,
            context_epoch=comprehension.context_epoch,
            session_nonce=comprehension.session_nonce,
            opening_receipts=_provider_receipts(comprehension.capture),
        )
        parent_response_id = comprehension.capture.response_id
        assert parent_response_id is not None
        session_response_ids = {parent_response_id}
        session_failed = False
        for fixture in tasks:
            if session_failed:
                results.append(
                    ReceiverCeilingTaskResult(
                        arm="action-state",
                        item_id=fixture.item_id,
                        expected_output_sha256=sha256_text(
                            fixture.expected_output_text
                        ),
                        status="not-run-session-invalid",
                        output_text=None,
                        exact_score=False,
                        provider_call_performed=False,
                        capture_binding_sha256=None,
                        _factory_token=_TASK_RESULT_FACTORY_TOKEN,
                    )
                )
                continue
            observation = session.expected_observation()
            cached = mint_session_cached_receiver(session, attempt, observation)
            request = build_action_state_request(
                fixture.action_state,
                capsule,
                task_context,
                task_context_cached_in_same_model_context=True,
                task_context_id=cached.context_id,
                task_comprehension_evidence_sha256=cached.proof_sha256,
                task_comprehension_verifier_sha256=(
                    cached.capabilities.task_context_comprehension_verifier_sha256
                ),
                capsule_cached_in_same_model_context=True,
                capsule_context_id=cached.context_id,
                comprehension_evidence_sha256=cached.proof_sha256,
                capsule_comprehension_verifier_sha256=(
                    cached.capabilities.capsule_comprehension_verifier_sha256
                ),
                maximum_total_tokens=maximum_receiver_tokens,
            )
            expected_hot = "PAYLOAD\n" + fixture.action_state.canonical_text
            _require_request_text(expected_hot, "hot model-visible request")
            if (
                request.user_data_text != expected_hot
                or request.capsule_text is not None
                or request.task_context_included
                or request.natural_language_expansion is not None
                or request.decode_before_model
            ):
                _raise_with_journal("hot request contains prose re-expansion", journal)
            lease = prepare_session_turn(
                session,
                expected_hot,
                maximum_total_tokens=maximum_receiver_tokens,
                observation=observation,
            )
            adapter = _HotAdapter(
                provider=provider,
                receiver_binding=receiver_binding,
                provider_id=provider_id,
                context_id=comprehension.capture.context_id,
                parent_response_id=parent_response_id,
                item_id=fixture.item_id,
                maximum_tokens=maximum_receiver_tokens,
                journal=journal,
            )
            try:
                execute_session_turn(session, lease, adapter)
            except SessionError:
                if adapter.fatal is not None:
                    raise adapter.fatal
                result = adapter.result
                if result is None:
                    _raise_with_journal(
                        "session failed before a provider callback was captured",
                        journal,
                    )
                if result.reply is not None:
                    _raise_with_journal(
                        "session rejected a captured completed reply",
                        journal,
                    )
                results.append(
                    ReceiverCeilingTaskResult(
                        arm="action-state",
                        item_id=fixture.item_id,
                        expected_output_sha256=sha256_text(
                            fixture.expected_output_text
                        ),
                        status="provider-failed",
                        output_text=None,
                        exact_score=False,
                        provider_call_performed=True,
                        capture_binding_sha256=result.capture.binding_sha256,
                        _factory_token=_TASK_RESULT_FACTORY_TOKEN,
                    )
                )
                session_failed = True
                continue
            result = adapter.result
            assert result is not None and result.reply is not None
            assert result.capture.response_id is not None
            if result.capture.response_id in session_response_ids:
                _raise_with_journal(
                    "action-state response id is reused",
                    journal,
                )
            session_response_ids.add(result.capture.response_id)
            parent_response_id = result.capture.response_id
            output = result.reply.text
            results.append(
                ReceiverCeilingTaskResult(
                    arm="action-state",
                    item_id=fixture.item_id,
                    expected_output_sha256=sha256_text(
                        fixture.expected_output_text
                    ),
                    status="completed",
                    output_text=output,
                    exact_score=output == fixture.expected_output_text,
                    provider_call_performed=True,
                    capture_binding_sha256=result.capture.binding_sha256,
                    _factory_token=_TASK_RESULT_FACTORY_TOKEN,
                )
            )

    if comprehension_failure == "not-run":
        raise ReceiverCeilingError("fixed arm order did not execute action-state")
    try:
        return PerfectSenderMatchedSessionResult(
            experiment_binding_sha256=experiment_sha256,
            experiment_manifest_text=experiment_manifest_text,
            preflight_sha256=preflight.sha256,
            preflight_text=preflight.canonical_text,
            task_order=task_order,
            arm_order=arms,
            comprehension_passed=comprehension_passed,
            comprehension_failure=comprehension_failure,
            task_results=tuple(results),
            journal=tuple(journal),
            _factory_token=_RUN_RESULT_FACTORY_TOKEN,
        )
    except ReceiverCeilingError as exc:
        if exc.journal:
            raise
        raise ReceiverCeilingError(str(exc), journal=journal) from exc


def run_perfect_sender_matched_session(
    *,
    capsule: Capsule,
    task_context: PublicTaskContext,
    receiver_binding: ReceiverModelBinding,
    provider: ReceiverCeilingProvider,
    fixtures: Sequence[PerfectSenderTaskFixture],
    arm_order: Sequence[str],
    preflight: SyntheticReceiverCeilingAuthorization,
    maximum_comprehension_tokens: int,
    maximum_receiver_tokens: int,
) -> PerfectSenderMatchedSessionResult:
    """Run the diagnostic and retain every completed callback on later errors."""

    journal: list[ReceiverCeilingAttempt] = []
    try:
        return _run_perfect_sender_matched_session_impl(
            capsule=capsule,
            task_context=task_context,
            receiver_binding=receiver_binding,
            provider=provider,
            fixtures=fixtures,
            arm_order=arm_order,
            preflight=preflight,
            maximum_comprehension_tokens=maximum_comprehension_tokens,
            maximum_receiver_tokens=maximum_receiver_tokens,
            _journal=journal,
        )
    except ReceiverCeilingCallbackInterrupt:
        raise
    except ReceiverCeilingError as exc:
        if exc.journal or not journal:
            raise
        raise ReceiverCeilingError(str(exc), journal=journal) from exc
    except Exception as exc:
        if not journal:
            raise
        raise ReceiverCeilingError(
            "receiver-ceiling post-callback validation failed",
            journal=journal,
        ) from exc
