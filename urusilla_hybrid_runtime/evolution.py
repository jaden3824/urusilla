"""Bounded, session-local orchestration for online surface evolution.

This module joins the sealed surface primitives without adding persistence,
tool, permission, spending, or external-effect authority.  Observation data is
used only for proposing aliases.  A separately frozen held-out manifest drives
activation and shadow evaluation, and only a retained proof can authorize a
live surface.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import secrets
from typing import Callable, Literal, Mapping, Sequence

from .canonical import canonical_json, sha256_text
from .errors import SurfaceError
from .records import PublicActionState, source_text_sha256
from .surface import (
    ActiveSurface,
    RetainedSurface,
    SurfaceActivationEvidence,
    SurfaceAliasTable,
    SurfaceArtifactVerification,
    SurfaceEvolutionDecision,
    SurfaceScope,
    SurfaceTrial,
    SurfaceTrialPlan,
    activate_surface,
    decide_surface_evolution,
    optimize_alias_table,
)
from .task_context import PublicTaskContext, validate_state_against_task_context


EVOLUTION_TRIAL_MANIFEST_FORMAT = "urusilla-evolution-trial-manifest-draft/1"
EVOLUTION_ATTEMPT_FORMAT = "urusilla-evolution-attempt-draft/1"
EVOLUTION_COST_LEDGER_FORMAT = "urusilla-evolution-cost-ledger-draft/1"
EVOLUTION_OBSERVATION_WINDOW_FORMAT = (
    "urusilla-evolution-observation-window-draft/1"
)
MAX_EVOLUTION_OBSERVATIONS = 512
MAX_EVOLUTION_TRIAL_CASES = 512
MAX_EVOLUTION_CANDIDATE_ALIASES = 1_024
MAX_EVOLUTION_ATTEMPTS = 128

EvolutionPhase = Literal[
    "observing",
    "ready",
    "evolving",
    "retained",
    "rolled-back",
    "failed",
]
EvolutionStatus = Literal["not-ready", "keep", "rollback", "failed"]

_TERMINAL_PHASES = frozenset({"retained", "rolled-back", "failed"})
_FAILURE_STAGES = frozenset({"proposal", "activation", "trial", "decision"})
_FAILURE_CODES = frozenset(
    {
        "callback-failed",
        "invalid-callback-result",
        "binding-mismatch",
        "operation-rejected",
        "attempt-limit",
    }
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTEXT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$")


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise SurfaceError(f"{label} must be an exact sha256 digest")
    return value


def _require_context_id(value: object, label: str) -> str:
    if type(value) is not str or _CONTEXT_ID.fullmatch(value) is None:
        raise SurfaceError(f"{label} must be a bounded public identifier")
    return value


def semantic_ref_frequencies(
    state: PublicActionState,
    task_context: PublicTaskContext,
) -> dict[str, int]:
    """Count semantic references in exact wire positions of one valid state."""

    if type(state) is not PublicActionState:
        raise SurfaceError("semantic frequency input must be a PublicActionState")
    if type(task_context) is not PublicTaskContext:
        raise SurfaceError("semantic frequency context must be a PublicTaskContext")
    validate_state_against_task_context(state, task_context)
    value = state.to_object()
    counts: Counter[str] = Counter()
    counts[f"act:{value['act']}"] += 1

    atoms: list[Mapping[str, object]] = []
    if value["goal"] is not None:
        atoms.append(value["goal"])
    for field_name in ("state", "constraints", "needs"):
        atoms.extend(value[field_name])
    outcome = value["outcome"]
    if outcome is not None:
        atoms.extend(outcome["evidence"])
    for atom in atoms:
        counts[f"predicate:{atom['p']}"] += 1

    action = value["action"]
    if action is not None:
        counts[f"action:{action['name']}"] += 1
        counts[f"action-status:{action['status']}"] += 1
        for effect in action["effects"]:
            counts[f"effect:{effect}"] += 1
    if outcome is not None:
        counts[f"outcome-status:{outcome['status']}"] += 1
    for uncertainty in value["uncertainty"]:
        counts[f"uncertainty-target:{uncertainty['target']}"] += 1
        counts[f"uncertainty-model:{uncertainty['model']}"] += 1
        for basis in uncertainty["basis"]:
            counts[f"uncertainty-basis:{basis}"] += 1
    return {key: counts[key] for key in sorted(counts)}


def _trial_plan_policy_sha256(plan: SurfaceTrialPlan) -> str:
    return sha256_text(
        canonical_json(
            {
                "expected_activation_vectors_sha256": (
                    plan.expected_activation_vectors_sha256
                ),
                "expected_activation_verifier_sha256": (
                    plan.expected_activation_verifier_sha256
                ),
                "expected_trial_verifier_sha256": (
                    plan.expected_trial_verifier_sha256
                ),
                "exact_message_count": plan.exact_message_count,
                "minimum_messages": plan.minimum_messages,
                "shadow_call_token_ceiling": plan.shadow_call_token_ceiling,
                "shadow_aggregate_token_ceiling": (
                    plan.shadow_aggregate_token_ceiling
                ),
                "switching_margin_tokens_per_safe_completion": (
                    plan.switching_margin_tokens_per_safe_completion
                ),
                "require_all_parse_valid": plan.require_all_parse_valid,
                "require_all_fidelity_valid": plan.require_all_fidelity_valid,
                "require_negative_preservation": (
                    plan.require_negative_preservation
                ),
                "require_zero_boundary_violations": (
                    plan.require_zero_boundary_violations
                ),
            }
        )
    )


@dataclass(frozen=True)
class EvolutionTrialManifest:
    """Frozen held-out cases for exactly one evolution attempt."""

    session_id: str
    model_context_id: str
    expected_attempt_id: int
    parent_table_sha256: str | None
    cases: tuple[tuple[str, str], ...]
    external_plan_sha256: str

    def __post_init__(self) -> None:
        _require_context_id(self.session_id, "trial manifest session_id")
        _require_context_id(
            self.model_context_id,
            "trial manifest model_context_id",
        )
        if (
            type(self.expected_attempt_id) is not int
            or not 1 <= self.expected_attempt_id <= MAX_EVOLUTION_ATTEMPTS
        ):
            raise SurfaceError("trial manifest expected attempt is invalid")
        if self.parent_table_sha256 is not None:
            _require_sha256(
                self.parent_table_sha256,
                "trial manifest parent_table_sha256",
            )
        if (
            type(self.cases) is not tuple
            or not self.cases
            or len(self.cases) > MAX_EVOLUTION_TRIAL_CASES
        ):
            raise SurfaceError("trial manifest cases are not a bounded tuple")
        case_ids: list[str] = []
        source_sha256s: list[str] = []
        for item in self.cases:
            if type(item) is not tuple or len(item) != 2:
                raise SurfaceError("trial manifest case entry is invalid")
            case_id, source_sha256 = item
            case_ids.append(_require_context_id(case_id, "trial case id"))
            source_sha256s.append(
                _require_sha256(source_sha256, "trial case source_sha256")
            )
        if len(set(case_ids)) != len(case_ids):
            raise SurfaceError("trial manifest case ids must be unique")
        if len(set(source_sha256s)) != len(source_sha256s):
            raise SurfaceError("trial manifest source digests must be unique")
        _require_sha256(
            self.external_plan_sha256,
            "trial manifest external_plan_sha256",
        )

    @property
    def canonical_text(self) -> str:
        return canonical_json(
            {
                "format": EVOLUTION_TRIAL_MANIFEST_FORMAT,
                "session_id": self.session_id,
                "model_context_id": self.model_context_id,
                "expected_attempt_id": self.expected_attempt_id,
                "parent_table_sha256": self.parent_table_sha256,
                "cases": [
                    {"case_id": case_id, "source_sha256": source_sha256}
                    for case_id, source_sha256 in self.cases
                ],
                "external_plan_sha256": self.external_plan_sha256,
            }
        )

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)

    @property
    def case_ids(self) -> frozenset[str]:
        return frozenset(case_id for case_id, _ in self.cases)

    @property
    def source_sha256s(self) -> frozenset[str]:
        return frozenset(source_sha256 for _, source_sha256 in self.cases)


@dataclass(frozen=True)
class EvolutionCostLedger:
    """Immutable lifetime and currently unamortized evolution accounting."""

    attempt_count: int
    lifetime_overhead_tokens: int | None
    unamortized_overhead_tokens: int | None
    usage_complete: bool

    def __post_init__(self) -> None:
        if (
            type(self.attempt_count) is not int
            or not 0 <= self.attempt_count <= MAX_EVOLUTION_ATTEMPTS
        ):
            raise SurfaceError("evolution ledger attempt count is invalid")
        for name in (
            "lifetime_overhead_tokens",
            "unamortized_overhead_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise SurfaceError(f"evolution ledger {name} is invalid")
        if type(self.usage_complete) is not bool:
            raise SurfaceError("evolution ledger completeness must be boolean")
        complete = (
            self.lifetime_overhead_tokens is not None
            and self.unamortized_overhead_tokens is not None
        )
        if self.usage_complete is not complete:
            raise SurfaceError("evolution ledger completeness is inconsistent")

    @property
    def canonical_text(self) -> str:
        return canonical_json(
            {
                "format": EVOLUTION_COST_LEDGER_FORMAT,
                "attempt_count": self.attempt_count,
                "lifetime_overhead_tokens": self.lifetime_overhead_tokens,
                "unamortized_overhead_tokens": self.unamortized_overhead_tokens,
                "usage_complete": self.usage_complete,
            }
        )

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class EvolutionAttempt:
    """Exact proposal/evaluation attempt bound to prior accounting and data."""

    attempt_id: int
    session_id: str
    model_context_id: str
    controller_epoch_sha256: str
    retained_parent_sha256: str | None
    observation_window_sha256: str
    observation_count: int
    manifest_sha256: str
    prior_ledger_sha256: str
    prior_attempt_count: int
    prior_lifetime_overhead_tokens: int | None
    prior_unamortized_overhead_tokens: int | None
    prior_usage_complete: bool

    def __post_init__(self) -> None:
        if (
            type(self.attempt_id) is not int
            or not 1 <= self.attempt_id <= MAX_EVOLUTION_ATTEMPTS
        ):
            raise SurfaceError("evolution attempt id is invalid")
        _require_context_id(self.session_id, "evolution attempt session_id")
        _require_context_id(
            self.model_context_id,
            "evolution attempt model_context_id",
        )
        _require_sha256(
            self.controller_epoch_sha256,
            "evolution attempt controller epoch",
        )
        if self.retained_parent_sha256 is not None:
            _require_sha256(
                self.retained_parent_sha256,
                "evolution attempt retained parent",
            )
        for name in (
            "observation_window_sha256",
            "manifest_sha256",
            "prior_ledger_sha256",
        ):
            _require_sha256(getattr(self, name), f"evolution attempt {name}")
        if (
            type(self.observation_count) is not int
            or not 1 <= self.observation_count <= MAX_EVOLUTION_OBSERVATIONS
        ):
            raise SurfaceError("evolution attempt observation count is invalid")
        if (
            type(self.prior_attempt_count) is not int
            or self.prior_attempt_count < 0
            or self.attempt_id != self.prior_attempt_count + 1
        ):
            raise SurfaceError("evolution attempt prior count is inconsistent")
        for name in (
            "prior_lifetime_overhead_tokens",
            "prior_unamortized_overhead_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise SurfaceError(f"evolution attempt {name} is invalid")
        if type(self.prior_usage_complete) is not bool:
            raise SurfaceError("evolution attempt prior completeness is invalid")
        complete = (
            self.prior_lifetime_overhead_tokens is not None
            and self.prior_unamortized_overhead_tokens is not None
        )
        if self.prior_usage_complete is not complete:
            raise SurfaceError("evolution attempt prior usage is inconsistent")

    @property
    def canonical_text(self) -> str:
        return canonical_json(
            {
                "format": EVOLUTION_ATTEMPT_FORMAT,
                "attempt_id": self.attempt_id,
                "session_id": self.session_id,
                "model_context_id": self.model_context_id,
                "controller_epoch_sha256": self.controller_epoch_sha256,
                "retained_parent_sha256": self.retained_parent_sha256,
                "observation_window_sha256": self.observation_window_sha256,
                "observation_count": self.observation_count,
                "manifest_sha256": self.manifest_sha256,
                "prior_ledger_sha256": self.prior_ledger_sha256,
                "prior_attempt_count": self.prior_attempt_count,
                "prior_lifetime_overhead_tokens": (
                    self.prior_lifetime_overhead_tokens
                ),
                "prior_unamortized_overhead_tokens": (
                    self.prior_unamortized_overhead_tokens
                ),
                "prior_usage_complete": self.prior_usage_complete,
            }
        )

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class EvolutionOutcome:
    """Bounded result carrying no callback output, transcript, or exception."""

    status: EvolutionStatus
    phase: EvolutionPhase
    controller_epoch_sha256: str
    observed_count: int
    required_count: int
    cost_ledger: EvolutionCostLedger
    cost_ledger_sha256: str
    attempt_id: int | None = None
    attempt_sha256: str | None = None
    generation_attempted: int | None = None
    candidate_table_sha256: str | None = None
    decision: SurfaceEvolutionDecision | None = None
    failure_stage: str | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        _require_sha256(
            self.controller_epoch_sha256,
            "evolution outcome controller epoch",
        )
        if type(self.cost_ledger) is not EvolutionCostLedger:
            raise SurfaceError("evolution outcome ledger type is invalid")
        if self.cost_ledger_sha256 != self.cost_ledger.sha256:
            raise SurfaceError("evolution outcome ledger digest differs")
        if type(self.observed_count) is not int or self.observed_count < 0:
            raise SurfaceError("evolution outcome observed count is invalid")
        if type(self.required_count) is not int or self.required_count <= 0:
            raise SurfaceError("evolution outcome required count is invalid")
        if self.observed_count > self.required_count:
            raise SurfaceError("evolution outcome exceeds its observation window")
        expected_phase = {
            "not-ready": "observing",
            "keep": "retained",
            "rollback": "rolled-back",
            "failed": "failed",
        }.get(self.status)
        if expected_phase != self.phase:
            raise SurfaceError("evolution outcome status and phase differ")
        if (self.attempt_id is None) is not (self.attempt_sha256 is None):
            raise SurfaceError("evolution outcome attempt identity is incomplete")
        if self.attempt_id is not None:
            if type(self.attempt_id) is not int or self.attempt_id <= 0:
                raise SurfaceError("evolution outcome attempt id is invalid")
            _require_sha256(self.attempt_sha256, "evolution outcome attempt")
            if self.cost_ledger.attempt_count != self.attempt_id:
                raise SurfaceError("evolution outcome ledger and attempt differ")
        if self.generation_attempted is not None and (
            type(self.generation_attempted) is not int
            or self.generation_attempted <= 0
        ):
            raise SurfaceError("evolution outcome generation is invalid")
        if self.candidate_table_sha256 is not None:
            _require_sha256(
                self.candidate_table_sha256,
                "evolution outcome candidate",
            )
        if (self.generation_attempted is None) is not (
            self.candidate_table_sha256 is None
        ):
            raise SurfaceError("evolution candidate generation and digest differ")
        if self.status == "not-ready" and (
            self.observed_count >= self.required_count
            or self.attempt_id is not None
            or self.generation_attempted is not None
        ):
            raise SurfaceError("not-ready evolution outcome is inconsistent")
        if self.status in {"keep", "rollback"} and (
            self.observed_count != self.required_count
            or self.attempt_id is None
            or self.generation_attempted is None
        ):
            raise SurfaceError("terminal decision lacks its exact attempt")
        if self.status in {"keep", "rollback"}:
            if (
                type(self.decision) is not SurfaceEvolutionDecision
                or self.decision.action != self.status
                or self.decision.table_sha256 != self.candidate_table_sha256
                or self.failure_stage is not None
                or self.failure_code is not None
            ):
                raise SurfaceError("evolution decision outcome is inconsistent")
        elif self.decision is not None:
            raise SurfaceError("non-decision outcome carries a decision")
        if self.status == "failed":
            if (
                self.failure_stage not in _FAILURE_STAGES
                or self.failure_code not in _FAILURE_CODES
            ):
                raise SurfaceError("evolution failure is not a bounded code")
        elif self.failure_stage is not None or self.failure_code is not None:
            raise SurfaceError("non-failure outcome carries failure data")
        if self.status == "keep":
            assert self.decision is not None
            retained = self.decision.retained_surface
            if (
                type(retained) is not RetainedSurface
                or retained.attempt_sha256 != self.attempt_sha256
            ):
                raise SurfaceError("kept evolution lacks its exact retained proof")


@dataclass(frozen=True)
class _EvolutionObservation:
    observation_id: str
    source_sha256: str
    state: PublicActionState


ActivationCallback = Callable[
    [SurfaceAliasTable, EvolutionAttempt, EvolutionTrialManifest],
    SurfaceActivationEvidence,
]
ActivationVerifier = Callable[
    [SurfaceActivationEvidence, SurfaceAliasTable],
    SurfaceArtifactVerification,
]
TrialCallback = Callable[
    [
        SurfaceAliasTable,
        ActiveSurface,
        SurfaceTrialPlan,
        EvolutionAttempt,
        EvolutionTrialManifest,
    ],
    SurfaceTrial,
]
TrialVerifier = Callable[
    [
        SurfaceTrial,
        SurfaceTrialPlan,
        SurfaceAliasTable,
        ActiveSurface,
        EvolutionAttempt,
        EvolutionTrialManifest,
    ],
    SurfaceArtifactVerification,
]


class OnlineEvolutionController:
    """Synchronous in-memory evolution state machine for one exact session.

    Every instance mints an unpredictable, caller-independent epoch.  The host
    must enforce a one-controller-per-scope lease: replacing or concurrently
    constructing a controller invalidates the prior instance's live surface,
    and resuming the same session/model context without its sealed ledger is
    forbidden.  This module deliberately provides no persistence or lease API.
    """

    __slots__ = (
        "_scope",
        "_controller_epoch_sha256",
        "_task_context",
        "_candidate_aliases",
        "_token_counters",
        "_observation_message_count",
        "_trial_plan",
        "_plan_policy_sha256",
        "_trial_manifest",
        "_activation_callback",
        "_activation_verifier",
        "_trial_callback",
        "_trial_verifier",
        "_phase",
        "_observations",
        "_terminal_outcome",
        "_retained_table",
        "_retained_active_surface",
        "_retained_surface",
        "_attempt_history",
        "_ledger",
        "_used_manifest_sha256s",
        "_used_external_plan_sha256s",
        "_used_trial_case_ids",
        "_used_trial_source_sha256s",
        "_used_observation_ids",
        "_used_observation_source_sha256s",
    )

    def __init__(
        self,
        *,
        scope: SurfaceScope,
        task_context: PublicTaskContext,
        candidate_aliases: Sequence[str],
        token_counters: Mapping[str, Callable[[str], int]],
        observation_message_count: int,
        trial_plan: SurfaceTrialPlan,
        trial_manifest: EvolutionTrialManifest,
        activation_callback: ActivationCallback,
        activation_verifier: ActivationVerifier,
        trial_callback: TrialCallback,
        trial_verifier: TrialVerifier,
    ) -> None:
        if type(scope) is not SurfaceScope:
            raise SurfaceError("evolution scope must be a SurfaceScope")
        if type(task_context) is not PublicTaskContext:
            raise SurfaceError("evolution context must be a PublicTaskContext")
        if scope.task_profile_sha256 != task_context.task_profile_sha256:
            raise SurfaceError("evolution scope and task profile differ")
        if scope.symbol_table_sha256 != task_context.symbol_table_sha256:
            raise SurfaceError("evolution scope and symbol table differ")
        if (
            type(observation_message_count) is not int
            or not 1
            <= observation_message_count
            <= MAX_EVOLUTION_OBSERVATIONS
        ):
            raise SurfaceError("evolution observation count is out of bounds")
        if isinstance(candidate_aliases, (str, bytes)):
            raise SurfaceError("evolution candidate aliases must be a sequence")
        aliases = tuple(candidate_aliases)
        if (
            not aliases
            or len(aliases) > MAX_EVOLUTION_CANDIDATE_ALIASES
            or any(type(alias) is not str for alias in aliases)
        ):
            raise SurfaceError("evolution candidate aliases are out of bounds")
        counters = dict(token_counters)
        if set(counters) != set(scope.tokenizer_ids) or any(
            not callable(counter) for counter in counters.values()
        ):
            raise SurfaceError("evolution token counters differ from scope")
        for name, callback in (
            ("activation_callback", activation_callback),
            ("activation_verifier", activation_verifier),
            ("trial_callback", trial_callback),
            ("trial_verifier", trial_verifier),
        ):
            if not callable(callback):
                raise SurfaceError(f"evolution {name} must be callable")

        self._scope = scope
        self._controller_epoch_sha256 = sha256_text(secrets.token_hex(32))
        self._task_context = task_context
        self._candidate_aliases = aliases
        self._token_counters = counters
        self._observation_message_count = observation_message_count
        if type(trial_plan) is not SurfaceTrialPlan:
            raise SurfaceError("evolution requires a frozen SurfaceTrialPlan")
        self._plan_policy_sha256 = _trial_plan_policy_sha256(trial_plan)
        self._activation_callback = activation_callback
        self._activation_verifier = activation_verifier
        self._trial_callback = trial_callback
        self._trial_verifier = trial_verifier
        self._phase: EvolutionPhase = "observing"
        self._observations: list[_EvolutionObservation] = []
        self._terminal_outcome: EvolutionOutcome | None = None
        self._retained_table: SurfaceAliasTable | None = None
        self._retained_active_surface: ActiveSurface | None = None
        self._retained_surface: RetainedSurface | None = None
        self._attempt_history: list[EvolutionAttempt] = []
        self._ledger = EvolutionCostLedger(0, 0, 0, True)
        self._used_manifest_sha256s: set[str] = set()
        self._used_external_plan_sha256s: set[str] = set()
        self._used_trial_case_ids: set[str] = set()
        self._used_trial_source_sha256s: set[str] = set()
        self._used_observation_ids: set[str] = set()
        self._used_observation_source_sha256s: set[str] = set()
        self._validate_freeze(
            trial_plan,
            trial_manifest,
            expected_attempt_id=1,
            expected_parent_sha256=None,
        )
        self._trial_plan = trial_plan
        self._trial_manifest = trial_manifest
        self._register_manifest(trial_manifest)

    def _validate_freeze(
        self,
        plan: SurfaceTrialPlan,
        manifest: EvolutionTrialManifest,
        *,
        expected_attempt_id: int,
        expected_parent_sha256: str | None,
    ) -> None:
        if type(plan) is not SurfaceTrialPlan:
            raise SurfaceError("evolution requires a frozen SurfaceTrialPlan")
        if _trial_plan_policy_sha256(plan) != self._plan_policy_sha256:
            raise SurfaceError("evolution trial policy changed within the session")
        if type(manifest) is not EvolutionTrialManifest:
            raise SurfaceError("evolution requires a typed trial manifest")
        if (
            manifest.session_id != self._scope.session_id
            or manifest.model_context_id != self._scope.model_context_id
        ):
            raise SurfaceError("trial manifest belongs to another exact scope")
        if manifest.expected_attempt_id != expected_attempt_id:
            raise SurfaceError("trial manifest expected attempt differs")
        if manifest.parent_table_sha256 != expected_parent_sha256:
            raise SurfaceError("trial manifest retained parent differs")
        if plan.plan_artifact_sha256 != manifest.sha256:
            raise SurfaceError("trial plan is not bound to its exact manifest")
        if len(manifest.cases) != plan.exact_message_count:
            raise SurfaceError("trial manifest count differs from frozen plan")
        if manifest.sha256 in self._used_manifest_sha256s:
            raise SurfaceError("trial manifest was already used")
        if manifest.external_plan_sha256 in self._used_external_plan_sha256s:
            raise SurfaceError("external trial plan was already used")
        if manifest.case_ids & (
            self._used_trial_case_ids | self._used_observation_ids
        ):
            raise SurfaceError("trial case id overlaps prior session data")
        if manifest.source_sha256s & (
            self._used_trial_source_sha256s
            | self._used_observation_source_sha256s
        ):
            raise SurfaceError("trial source overlaps prior session data")

    def _register_manifest(self, manifest: EvolutionTrialManifest) -> None:
        self._used_manifest_sha256s.add(manifest.sha256)
        self._used_external_plan_sha256s.add(manifest.external_plan_sha256)
        self._used_trial_case_ids.update(manifest.case_ids)
        self._used_trial_source_sha256s.update(manifest.source_sha256s)

    @property
    def phase(self) -> EvolutionPhase:
        return self._phase

    @property
    def controller_epoch_sha256(self) -> str:
        """Public lease identity; generated by core and never caller-selected."""

        return self._controller_epoch_sha256

    @property
    def observed_count(self) -> int:
        return len(self._observations)

    @property
    def required_count(self) -> int:
        return self._observation_message_count

    @property
    def observation_window_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "format": EVOLUTION_OBSERVATION_WINDOW_FORMAT,
                    "session_id": self._scope.session_id,
                    "model_context_id": self._scope.model_context_id,
                    "controller_epoch_sha256": self._controller_epoch_sha256,
                    "observation_count": len(self._observations),
                    "observations": [
                        {
                            "observation_id": item.observation_id,
                            "source_sha256": item.source_sha256,
                            "state_sha256": item.state.sha256,
                        }
                        for item in self._observations
                    ],
                }
            )
        )

    @property
    def last_outcome(self) -> EvolutionOutcome | None:
        return self._terminal_outcome

    @property
    def cost_ledger(self) -> EvolutionCostLedger:
        return self._ledger

    @property
    def attempt_history(self) -> tuple[EvolutionAttempt, ...]:
        return tuple(self._attempt_history)

    @property
    def retained_table(self) -> SurfaceAliasTable | None:
        return self._retained_table

    @property
    def retained_active_surface(self) -> ActiveSurface | None:
        return self._retained_active_surface

    @property
    def retained_surface(self) -> RetainedSurface | None:
        return self._retained_surface

    @property
    def live_authorization(
        self,
    ) -> tuple[SurfaceAliasTable, ActiveSurface, RetainedSurface] | None:
        if (
            self._retained_table is None
            or self._retained_active_surface is None
            or self._retained_surface is None
        ):
            return None
        if not self._retained_surface.authorizes(
            self._retained_table,
            self._retained_active_surface,
        ):
            raise SurfaceError("retained evolution authorization is inconsistent")
        if not any(
            attempt.controller_epoch_sha256 == self._controller_epoch_sha256
            and attempt.sha256 == self._retained_surface.attempt_sha256
            for attempt in self._attempt_history
        ):
            raise SurfaceError(
                "retained evolution authorization belongs to another epoch"
            )
        return (
            self._retained_table,
            self._retained_active_surface,
            self._retained_surface,
        )

    def observe(
        self,
        observation_id: str,
        source_text: str,
        state: PublicActionState,
    ) -> int:
        if self._phase != "observing":
            raise SurfaceError("evolution observation window is not open")
        observation_id = _require_context_id(
            observation_id,
            "evolution observation_id",
        )
        try:
            source_sha256 = source_text_sha256(source_text)
        except Exception as exc:
            raise SurfaceError("evolution observation source text is invalid") from exc
        if type(state) is not PublicActionState:
            raise SurfaceError("evolution observation must be a PublicActionState")
        validate_state_against_task_context(state, self._task_context)
        if observation_id in (
            self._used_observation_ids | self._used_trial_case_ids
        ):
            raise SurfaceError("evolution observation id is reused or held out")
        if source_sha256 in self._used_trial_source_sha256s:
            raise SurfaceError("evolution observation source is held out")
        if len(self._observations) >= self.required_count:
            raise SurfaceError("evolution observation window is already full")
        self._observations.append(
            _EvolutionObservation(observation_id, source_sha256, state)
        )
        self._used_observation_ids.add(observation_id)
        self._used_observation_source_sha256s.add(source_sha256)
        if len(self._observations) == self.required_count:
            self._phase = "ready"
        return len(self._observations)

    def _outcome_kwargs(self) -> dict[str, object]:
        return {
            "controller_epoch_sha256": self._controller_epoch_sha256,
            "observed_count": len(self._observations),
            "required_count": self.required_count,
            "cost_ledger": self._ledger,
            "cost_ledger_sha256": self._ledger.sha256,
        }

    def _not_ready(self) -> EvolutionOutcome:
        return EvolutionOutcome(
            status="not-ready",
            phase="observing",
            **self._outcome_kwargs(),
        )

    def _failed(
        self,
        *,
        stage: str,
        code: str,
        attempt: EvolutionAttempt | None = None,
        table: SurfaceAliasTable | None = None,
    ) -> EvolutionOutcome:
        self._phase = "failed"
        outcome = EvolutionOutcome(
            status="failed",
            phase="failed",
            attempt_id=None if attempt is None else attempt.attempt_id,
            attempt_sha256=None if attempt is None else attempt.sha256,
            generation_attempted=None if table is None else table.generation,
            candidate_table_sha256=None if table is None else table.sha256,
            failure_stage=stage,
            failure_code=code,
            **self._outcome_kwargs(),
        )
        self._terminal_outcome = outcome
        return outcome

    def _start_attempt(self) -> EvolutionAttempt | None:
        if self._ledger.attempt_count >= MAX_EVOLUTION_ATTEMPTS:
            return None
        expected_id = self._ledger.attempt_count + 1
        parent_sha256 = (
            None if self._retained_table is None else self._retained_table.sha256
        )
        if (
            self._trial_manifest.expected_attempt_id != expected_id
            or self._trial_manifest.parent_table_sha256 != parent_sha256
        ):
            raise SurfaceError("frozen manifest no longer matches controller state")
        prior = self._ledger
        attempt = EvolutionAttempt(
            attempt_id=expected_id,
            session_id=self._scope.session_id,
            model_context_id=self._scope.model_context_id,
            controller_epoch_sha256=self._controller_epoch_sha256,
            retained_parent_sha256=parent_sha256,
            observation_window_sha256=self.observation_window_sha256,
            observation_count=len(self._observations),
            manifest_sha256=self._trial_manifest.sha256,
            prior_ledger_sha256=prior.sha256,
            prior_attempt_count=prior.attempt_count,
            prior_lifetime_overhead_tokens=prior.lifetime_overhead_tokens,
            prior_unamortized_overhead_tokens=(
                prior.unamortized_overhead_tokens
            ),
            prior_usage_complete=prior.usage_complete,
        )
        self._attempt_history.append(attempt)
        self._ledger = EvolutionCostLedger(
            attempt_count=expected_id,
            lifetime_overhead_tokens=prior.lifetime_overhead_tokens,
            unamortized_overhead_tokens=prior.unamortized_overhead_tokens,
            usage_complete=prior.usage_complete,
        )
        return attempt

    def _mark_usage_unknown(self) -> None:
        self._ledger = EvolutionCostLedger(
            attempt_count=self._ledger.attempt_count,
            lifetime_overhead_tokens=None,
            unamortized_overhead_tokens=None,
            usage_complete=False,
        )

    def _add_known_cost(self, tokens: int) -> None:
        if type(tokens) is not int or tokens < 0:
            self._mark_usage_unknown()
            return
        if not self._ledger.usage_complete:
            return
        assert self._ledger.lifetime_overhead_tokens is not None
        assert self._ledger.unamortized_overhead_tokens is not None
        self._ledger = EvolutionCostLedger(
            attempt_count=self._ledger.attempt_count,
            lifetime_overhead_tokens=(
                self._ledger.lifetime_overhead_tokens + tokens
            ),
            unamortized_overhead_tokens=(
                self._ledger.unamortized_overhead_tokens + tokens
            ),
            usage_complete=True,
        )

    def _settle_trial(self, trial: SurfaceTrial) -> None:
        if (
            trial.usage_complete
            and trial.surface_total_tokens_including_setup is not None
        ):
            self._add_known_cost(trial.surface_total_tokens_including_setup)
        else:
            self._mark_usage_unknown()

    def evolve_if_ready(self) -> EvolutionOutcome:
        if self._phase in _TERMINAL_PHASES:
            assert self._terminal_outcome is not None
            return self._terminal_outcome
        if self._phase == "observing":
            return self._not_ready()
        if self._phase != "ready":
            raise SurfaceError("evolution controller is already evolving")
        if self._trial_manifest.case_ids & {
            item.observation_id for item in self._observations
        } or self._trial_manifest.source_sha256s & {
            item.source_sha256 for item in self._observations
        }:
            return self._failed(stage="proposal", code="binding-mismatch")

        self._phase = "evolving"
        try:
            attempt = self._start_attempt()
        except Exception:
            return self._failed(stage="proposal", code="operation-rejected")
        if attempt is None:
            return self._failed(stage="proposal", code="attempt-limit")

        aggregate: Counter[str] = Counter()
        try:
            for observation in self._observations:
                aggregate.update(
                    semantic_ref_frequencies(
                        observation.state,
                        self._task_context,
                    )
                )
            table = optimize_alias_table(
                scope=self._scope,
                task_context=self._task_context,
                semantic_frequencies={
                    key: aggregate[key] for key in sorted(aggregate)
                },
                candidate_aliases=self._candidate_aliases,
                token_counters=self._token_counters,
                parent=self._retained_table,
            )
        except Exception:
            return self._failed(
                stage="proposal",
                code="operation-rejected",
                attempt=attempt,
            )

        try:
            evidence = self._activation_callback(
                table,
                attempt,
                self._trial_manifest,
            )
        except Exception:
            self._mark_usage_unknown()
            return self._failed(
                stage="activation",
                code="callback-failed",
                attempt=attempt,
                table=table,
            )
        if type(evidence) is not SurfaceActivationEvidence:
            self._mark_usage_unknown()
            return self._failed(
                stage="activation",
                code="invalid-callback-result",
                attempt=attempt,
                table=table,
            )
        if not evidence.claims_match(table, attempt.sha256):
            self._mark_usage_unknown()
            return self._failed(
                stage="activation",
                code="binding-mismatch",
                attempt=attempt,
                table=table,
            )

        try:
            def exact_activation_verifier(
                item: SurfaceActivationEvidence,
                candidate: SurfaceAliasTable,
            ) -> SurfaceArtifactVerification:
                result = self._activation_verifier(item, candidate)
                if type(result) is not SurfaceArtifactVerification:
                    raise SurfaceError(
                        "activation verifier returned an invalid result type"
                    )
                return result

            active = activate_surface(
                table,
                evidence,
                attempt_sha256=attempt.sha256,
                active_capsule_sha256=self._scope.capsule_sha256,
                expected_round_trip_vectors_sha256=(
                    self._trial_plan.expected_activation_vectors_sha256
                ),
                expected_verifier_sha256=(
                    self._trial_plan.expected_activation_verifier_sha256
                ),
                verifier=exact_activation_verifier,
            )
        except Exception:
            self._mark_usage_unknown()
            return self._failed(
                stage="activation",
                code="operation-rejected",
                attempt=attempt,
                table=table,
            )

        try:
            trial = self._trial_callback(
                table,
                active,
                self._trial_plan,
                attempt,
                self._trial_manifest,
            )
        except Exception:
            self._mark_usage_unknown()
            return self._failed(
                stage="trial",
                code="callback-failed",
                attempt=attempt,
                table=table,
            )
        if type(trial) is not SurfaceTrial:
            self._mark_usage_unknown()
            return self._failed(
                stage="trial",
                code="invalid-callback-result",
                attempt=attempt,
                table=table,
            )
        if any(
            (
                trial.table_sha256 != table.sha256,
                trial.attempt_sha256 != attempt.sha256,
                trial.executed_cases != self._trial_manifest.cases,
                trial.activation_binding_sha256
                != active.activation_binding_sha256,
                trial.plan_sha256 != self._trial_plan.sha256,
                trial.message_count != self._trial_plan.exact_message_count,
                trial.activation_setup_tokens != active.setup_total_tokens,
                trial.prior_evolution_overhead_tokens
                != attempt.prior_unamortized_overhead_tokens,
            )
        ):
            self._mark_usage_unknown()
            return self._failed(
                stage="trial",
                code="binding-mismatch",
                attempt=attempt,
                table=table,
            )

        try:
            def exact_trial_verifier(
                item: SurfaceTrial,
                plan: SurfaceTrialPlan,
                candidate: SurfaceAliasTable,
                candidate_active: ActiveSurface,
            ) -> SurfaceArtifactVerification:
                result = self._trial_verifier(
                    item,
                    plan,
                    candidate,
                    candidate_active,
                    attempt,
                    self._trial_manifest,
                )
                if type(result) is not SurfaceArtifactVerification:
                    raise SurfaceError(
                        "trial verifier returned an invalid result type"
                    )
                return result

            decision = decide_surface_evolution(
                table,
                trial,
                active_surface=active,
                plan=self._trial_plan,
                verifier=exact_trial_verifier,
            )
        except Exception:
            self._mark_usage_unknown()
            return self._failed(
                stage="decision",
                code="operation-rejected",
                attempt=attempt,
                table=table,
            )
        if type(decision) is not SurfaceEvolutionDecision:
            self._mark_usage_unknown()
            return self._failed(
                stage="decision",
                code="invalid-callback-result",
                attempt=attempt,
                table=table,
            )

        if decision.action == "rollback":
            if "trial-artifact-verification-failed" in decision.reasons:
                self._mark_usage_unknown()
            else:
                self._settle_trial(trial)
            self._phase = "rolled-back"
            outcome = EvolutionOutcome(
                status="rollback",
                phase="rolled-back",
                attempt_id=attempt.attempt_id,
                attempt_sha256=attempt.sha256,
                generation_attempted=table.generation,
                candidate_table_sha256=table.sha256,
                decision=decision,
                **self._outcome_kwargs(),
            )
            self._terminal_outcome = outcome
            return outcome

        retained = decision.retained_surface
        if (
            type(retained) is not RetainedSurface
            or retained.attempt_sha256 != attempt.sha256
            or not retained.authorizes(table, active)
        ):
            self._mark_usage_unknown()
            return self._failed(
                stage="decision",
                code="binding-mismatch",
                attempt=attempt,
                table=table,
            )
        self._settle_trial(trial)
        self._retained_table = table
        self._retained_active_surface = active
        self._retained_surface = retained
        self._phase = "retained"
        outcome = EvolutionOutcome(
            status="keep",
            phase="retained",
            attempt_id=attempt.attempt_id,
            attempt_sha256=attempt.sha256,
            generation_attempted=table.generation,
            candidate_table_sha256=table.sha256,
            decision=decision,
            **self._outcome_kwargs(),
        )
        self._terminal_outcome = outcome
        return outcome

    def begin_next_generation(
        self,
        *,
        trial_plan: SurfaceTrialPlan,
        trial_manifest: EvolutionTrialManifest,
    ) -> int:
        """Install one fresh frozen held-out plan and reopen observation."""

        if self._phase not in _TERMINAL_PHASES:
            raise SurfaceError("next generation requires a terminal result")
        expected_attempt_id = self._ledger.attempt_count + 1
        expected_parent_sha256 = (
            None if self._retained_table is None else self._retained_table.sha256
        )
        self._validate_freeze(
            trial_plan,
            trial_manifest,
            expected_attempt_id=expected_attempt_id,
            expected_parent_sha256=expected_parent_sha256,
        )
        self._trial_plan = trial_plan
        self._trial_manifest = trial_manifest
        self._register_manifest(trial_manifest)
        self._observations.clear()
        self._terminal_outcome = None
        self._phase = "observing"
        return expected_attempt_id
