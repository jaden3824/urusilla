"""End-to-end preparation path up to, but not including, a receiver model call."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Mapping

from .canonical import canonical_json, sha256_text
from .fidelity import FidelityVerification, FidelityVerificationInput
from .records import Capsule
from .receiver import (
    _execute_receiver_request,
    DirectReceiverRequest,
    ReceiverExecution,
    ReceiverModelAdapter,
    execute_receiver,
)
from .router import (
    CostForecast,
    LocalArtifactVerification,
    ReceiverCapabilities,
    RouteDecision,
    RouterPolicy,
    RoutineInvocation,
    SilenceProof,
    UtilityEvidence,
    plan_route,
    should_attempt_action_state,
)
from .sender import (
    CapsuleContextBinding,
    CompileOutcome,
    SenderContextVerification,
    StructuredCompiler,
    compile_natural_language,
)
from .task_context import PublicTaskContext
from .surface import ActiveSurface, RetainedSurface, SurfaceAliasTable


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class OutputValidationInput:
    source_sha256: str
    task_context_sha256: str
    task_profile_sha256: str
    route_mode: str
    payload_sha256: str
    output_text: str
    output_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "source_sha256",
            "task_context_sha256",
            "task_profile_sha256",
            "payload_sha256",
            "output_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"output validation {name} is invalid")
        if self.route_mode not in {"routine", "action-state", "raw", "json"}:
            raise ValueError("output validation route mode is invalid")
        if type(self.output_text) is not str:
            raise ValueError("output validation text must be a string")
        if sha256_text(self.output_text) != self.output_sha256:
            raise ValueError("output validation text digest mismatch")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "source_sha256": self.source_sha256,
                    "task_context_sha256": self.task_context_sha256,
                    "task_profile_sha256": self.task_profile_sha256,
                    "route_mode": self.route_mode,
                    "payload_sha256": self.payload_sha256,
                    "output_sha256": self.output_sha256,
                }
            )
        )


@dataclass(frozen=True)
class LocalOutputValidation:
    valid: bool
    input_binding_sha256: str
    validator_sha256: str
    deterministic_local: bool = True
    model_calls: int = 0
    total_tokens: int = 0
    tools_used: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise ValueError("local output validation must return a boolean")
        if _SHA256.fullmatch(self.input_binding_sha256) is None:
            raise ValueError("local output validation input binding is invalid")
        if _SHA256.fullmatch(self.validator_sha256) is None:
            raise ValueError("local output validator digest is invalid")
        if self.deterministic_local is not True:
            raise ValueError("output validator must be deterministic and local")
        if type(self.model_calls) is not int or self.model_calls != 0:
            raise ValueError("output validator cannot call a model")
        if type(self.total_tokens) is not int or self.total_tokens != 0:
            raise ValueError("output validator cannot consume model tokens")
        if type(self.tools_used) is not bool or self.tools_used:
            raise ValueError("output validator cannot use tools")
        if (
            type(self.external_effects_performed) is not bool
            or self.external_effects_performed
        ):
            raise ValueError("output validator cannot perform external effects")


@dataclass(frozen=True)
class PreparedMessage:
    route: RouteDecision
    compilation: CompileOutcome | None
    fidelity_verification: FidelityVerification | None = None
    receiver_model_calls_made: int = 0
    external_effects_performed: bool = False
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.route, RouteDecision):
            raise ValueError("prepared route must be a sealed RouteDecision")
        if self.receiver_model_calls_made != 0:
            raise ValueError("prepare_message must stop before the receiver model call")
        if any(
            (
                self.external_effects_performed,
                self.persistence_created,
                self.permission_expanded,
                self.spending_authority_created,
            )
        ):
            raise ValueError("message preparation cannot create authority or effects")
        if self.compilation is None:
            if self.fidelity_verification is not None:
                raise ValueError("fidelity verification requires a compilation")
            if self.route.selected_mode == "action-state" or self.route.fallback_from is not None:
                raise ValueError("prepared route lost its action-state compilation")
        else:
            request = self.route.request
            if (
                self.compilation.source_sha256 != self.route.source_sha256
                or self.compilation.capsule_sha256 != self.route.capsule_sha256
                or
                self.compilation.task_context_sha256
                != request.task_context_sha256
                or self.compilation.task_profile_sha256
                != request.task_profile_sha256
                or self.compilation.symbol_table_sha256
                != request.symbol_table_sha256
            ):
                raise ValueError("compilation and route task bindings differ")
            if (
                self.route.selected_mode == "action-state"
                and self.fidelity_verification is not None
            ):
                if self.compilation.compiled is None:
                    raise ValueError("fidelity verification requires compiled state")
                fidelity_input = FidelityVerificationInput(
                    source_text=next(
                        item.request.payload_text
                        for item in self.route.candidates
                        if item.mode == "raw" and item.request is not None
                    ),
                    source_sha256=self.route.source_sha256,
                    state=self.compilation.compiled,
                    task_context=PublicTaskContext.from_json(request.task_context_text),
                    maximum_total_tokens=(
                        self.route.fidelity_verifier_token_ceiling
                        if self.route.fidelity_verifier_token_ceiling is not None
                        else 0
                    ),
                )
                if (
                    self.fidelity_verification.input_binding_sha256
                    != fidelity_input.binding_sha256
                ):
                    raise ValueError("fidelity verification and compilation differ")
            if self.route.selected_mode == "action-state" and self.compilation.status != "ok":
                raise ValueError("action-state route requires one valid compilation")
            if self.route.selected_mode == "action-state":
                expected_state_sha256 = (
                    request.surface_carrier.state_sha256
                    if request.surface_carrier is not None
                    else request.payload_sha256
                )
                if (
                    self.compilation.compiled is None
                    or self.compilation.compiled.sha256 != expected_state_sha256
                    or request.capsule_sha256 != self.compilation.capsule_sha256
                ):
                    raise ValueError("compilation and action request payload differ")
                if self.fidelity_verification is None:
                    raise ValueError("action-state route lost its fidelity proof")
                if (
                    not self.fidelity_verification.passed
                    or self.compilation.total_tokens
                    != self.route.selected_cost.sender_tokens
                    or self.fidelity_verification.total_tokens
                    != self.route.selected_cost.semantic_verification_tokens
                ):
                    raise ValueError("prepared action evidence or token accounting differs")
            elif self.route.fallback_from is not None:
                if self.route.fallback_from != f"action-state:{self.compilation.status}":
                    raise ValueError("fallback status and compilation differ")
                if self.route.fallback_sender_tokens != self.compilation.total_tokens:
                    raise ValueError("fallback compiler token accounting differs")
                expected_fidelity_tokens = (
                    self.fidelity_verification.total_tokens
                    if self.fidelity_verification is not None
                    else 0
                )
                if (
                    self.route.fallback_semantic_verification_tokens
                    != expected_fidelity_tokens
                ):
                    raise ValueError("fallback fidelity token accounting differs")


@dataclass(frozen=True)
class HybridExecution:
    prepared: PreparedMessage
    primary: ReceiverExecution
    fallback: ReceiverExecution | None
    final_mode: str
    compiler_calls: int
    fidelity_verifier_calls: int
    receiver_calls: int
    output_valid: bool | None
    safely_completed: bool | None
    observed_runtime_tokens: int | None
    goal_total_complete: bool = False

    def __post_init__(self) -> None:
        if self.compiler_calls not in {0, 1}:
            raise ValueError("hybrid compiler calls must be zero or one")
        if self.fidelity_verifier_calls not in {0, 1}:
            raise ValueError("hybrid fidelity verifier calls must be zero or one")
        expected_receiver_calls = self.primary.calls + (
            self.fallback.calls if self.fallback is not None else 0
        )
        if self.receiver_calls != expected_receiver_calls:
            raise ValueError("hybrid receiver call count does not reconcile")
        primary_request = self.prepared.route.request
        if (
            self.primary.request_mode != self.prepared.route.selected_mode
            or self.primary.request_binding_sha256
            != primary_request.binding_sha256
            or self.primary.delivery_disposition != "live"
        ):
            raise ValueError(
                "hybrid primary execution is not bound to its live request"
            )
        if self.final_mode not in {"silence", "routine", "action-state", "raw", "json"}:
            raise ValueError("hybrid final mode is unknown")
        if self.fallback is None:
            if self.final_mode != self.prepared.route.selected_mode:
                raise ValueError("hybrid final mode lost its primary route")
        else:
            baseline = next(
                (
                    item
                    for item in self.prepared.route.candidates
                    if item.mode == self.prepared.route.best_baseline_mode
                ),
                None,
            )
            if (
                self.prepared.route.selected_mode
                not in {"routine", "action-state"}
                or baseline is None
                or baseline.request is None
                or self.fallback.request_mode not in {"raw", "json"}
                or self.fallback.request_mode != baseline.mode
                or self.fallback.request_binding_sha256
                != baseline.request.binding_sha256
                or self.fallback.delivery_disposition != "live"
                or self.final_mode != baseline.mode
            ):
                raise ValueError(
                    "hybrid fallback is not bound to its live baseline request"
                )
        if self.goal_total_complete:
            raise ValueError(
                "runtime-only trace cannot claim complete goal-token accounting"
            )


def _validate_public_output(
    execution: ReceiverExecution,
    request: DirectReceiverRequest,
    source_sha256: str,
    validator: Callable[[OutputValidationInput], LocalOutputValidation] | None,
    expected_validator_sha256: str | None,
) -> bool | None:
    if execution.status == "silenced":
        return True
    if execution.status != "completed" or execution.reply is None:
        return False
    if validator is None:
        return False if execution.request_mode in {"routine", "action-state"} else None
    validation_input = OutputValidationInput(
        source_sha256=source_sha256,
        task_context_sha256=request.task_context_sha256,
        task_profile_sha256=request.task_profile_sha256,
        route_mode=request.mode,
        payload_sha256=request.payload_sha256,
        output_text=execution.reply.text,
        output_sha256=sha256_text(execution.reply.text),
    )
    try:
        result = validator(validation_input)
    except Exception:
        return False
    if (
        not isinstance(result, LocalOutputValidation)
        or result.input_binding_sha256 != validation_input.binding_sha256
        or expected_validator_sha256 is None
        or result.validator_sha256 != expected_validator_sha256
    ):
        return False
    return result.valid


def execute_prepared_message(
    prepared: PreparedMessage,
    adapter: ReceiverModelAdapter,
    *,
    output_validator: Callable[
        [OutputValidationInput], LocalOutputValidation
    ]
    | None,
) -> HybridExecution:
    """Execute a prepared route and one lossless baseline fallback when needed.

    This trace deliberately remains insufficient for the research goal's token
    claim because setup probes, router measurement, safety filters, and judge
    calls are supplied by the frozen evaluation harness rather than this runtime.
    """

    expected_output_validator_sha256 = PublicTaskContext.from_json(
        prepared.route.request.task_context_text
    ).output_validator_sha256
    primary_request = prepared.route.request
    primary = (
        _execute_receiver_request(primary_request, adapter)
        if primary_request.surface_carrier is not None
        else execute_receiver(primary_request, adapter)
    )
    primary_valid = _validate_public_output(
        primary,
        prepared.route.request,
        prepared.route.source_sha256,
        output_validator,
        expected_output_validator_sha256,
    )
    fallback: ReceiverExecution | None = None
    final_mode = prepared.route.selected_mode
    final_valid = primary_valid
    if (
        prepared.route.selected_mode in {"routine", "action-state"}
        and primary_valid is not True
    ):
        baseline = next(
            (
                item
                for item in prepared.route.candidates
                if item.mode == prepared.route.best_baseline_mode
            ),
            None,
        )
        if baseline is None or baseline.request is None:
            raise ValueError("prepared route lost its mandatory baseline fallback")
        fallback = execute_receiver(baseline.request, adapter)
        final_mode = baseline.mode
        final_valid = _validate_public_output(
            fallback,
            baseline.request,
            prepared.route.source_sha256,
            output_validator,
            expected_output_validator_sha256,
        )

    compiler_calls = int(
        prepared.compilation is not None and prepared.compilation.attempted
    )
    receiver_calls = primary.calls + (fallback.calls if fallback else 0)
    usage_values: list[int] = []
    usage_complete = True
    if compiler_calls:
        assert prepared.compilation is not None
        if prepared.compilation.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(prepared.compilation.total_tokens)
    fidelity_verifier_calls = 0
    if prepared.fidelity_verification is not None:
        fidelity_verifier_calls = prepared.fidelity_verification.model_calls
        if prepared.fidelity_verification.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(prepared.fidelity_verification.total_tokens)
    for execution in (primary, fallback):
        if execution is None:
            continue
        if execution.total_tokens is None:
            usage_complete = False
        else:
            usage_values.append(execution.total_tokens)
    observed = sum(usage_values) if usage_complete else None
    safely_completed = final_valid if type(final_valid) is bool else None
    return HybridExecution(
        prepared=prepared,
        primary=primary,
        fallback=fallback,
        final_mode=final_mode,
        compiler_calls=compiler_calls,
        fidelity_verifier_calls=fidelity_verifier_calls,
        receiver_calls=receiver_calls,
        output_valid=final_valid,
        safely_completed=safely_completed,
        observed_runtime_tokens=observed,
        goal_total_complete=False,
    )


def prepare_message(
    source_text: str,
    capsule: Capsule,
    receiver: ReceiverCapabilities,
    token_counter: Callable[[str], int],
    *,
    task_context: PublicTaskContext,
    forecasts: Mapping[str, CostForecast],
    evidence: Mapping[str, UtilityEvidence] | None = None,
    compiler: StructuredCompiler | None = None,
    silence_proof: SilenceProof | None = None,
    routine: RoutineInvocation | None = None,
    surface_table: SurfaceAliasTable | None = None,
    active_surface: ActiveSurface | None = None,
    retained_surface: RetainedSurface | None = None,
    policy: RouterPolicy = RouterPolicy(),
    sender_capsule_context: CapsuleContextBinding | None = None,
    sender_context_verifier: Callable[
        [CapsuleContextBinding, Capsule, PublicTaskContext],
        SenderContextVerification,
    ]
    | None = None,
    fidelity_verifier: Callable[
        [FidelityVerificationInput], FidelityVerification
    ]
    | None = None,
    utility_evidence_verifier: Callable[
        [UtilityEvidence, str, str, str, str, str], LocalArtifactVerification
    ]
    | None = None,
    capsule_comprehension_verifier: Callable[
        [ReceiverCapabilities, Capsule], LocalArtifactVerification
    ]
    | None = None,
    task_context_comprehension_verifier: Callable[
        [ReceiverCapabilities, PublicTaskContext], LocalArtifactVerification
    ]
    | None = None,
    silence_verifier: Callable[[SilenceProof], LocalArtifactVerification]
    | None = None,
    routine_verifier: Callable[[RoutineInvocation], LocalArtifactVerification]
    | None = None,
) -> PreparedMessage:
    """Prepare one hybrid message with a safe raw/JSON fallback.

    The first pass can select a proven silence or routine route without paying
    for a compiler.  Only when those routes do not win and the cheap preflight
    permits action-state does the function invoke the injected sender compiler.
    It never calls the receiver model and never performs a tool or external
    action.
    """

    first = plan_route(
        source_text,
        capsule,
        receiver,
        token_counter,
        task_context=task_context,
        forecasts=forecasts,
        evidence=evidence,
        compile_outcome=None,
        silence_proof=silence_proof,
        routine=routine,
        policy=policy,
        utility_evidence_verifier=utility_evidence_verifier,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
        silence_verifier=silence_verifier,
        routine_verifier=routine_verifier,
    )
    if first.selected_mode in {"silence", "routine"}:
        return PreparedMessage(route=first, compilation=None)

    action_evidence = None if evidence is None else evidence.get("action-state")
    if compiler is None or fidelity_verifier is None or not should_attempt_action_state(
        receiver,
        capsule,
        task_context,
        action_evidence,
        policy,
        best_baseline_tokens=first.best_baseline_tokens,
        forecast=forecasts.get("action-state", CostForecast()),
        token_counter=token_counter,
        evidence_verifier=utility_evidence_verifier,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
        surface_forecast=forecasts.get("action-state-surface"),
        surface_table=surface_table,
        active_surface=active_surface,
        retained_surface=retained_surface,
    ):
        return PreparedMessage(route=first, compilation=None)

    compilation = compile_natural_language(
        source_text,
        capsule,
        compiler,
        task_context=task_context,
        capsule_context=sender_capsule_context,
        capsule_context_verifier=sender_context_verifier,
        maximum_total_tokens=policy.compiler_token_ceiling,
    )
    fidelity_verification: FidelityVerification | None = None
    if compilation.status == "ok" and compilation.compiled is not None:
        fidelity_input = FidelityVerificationInput(
            source_text=source_text,
            source_sha256=compilation.source_sha256,
            state=compilation.compiled,
            task_context=task_context,
            maximum_total_tokens=(
                policy.fidelity_verifier_token_ceiling
                if policy.fidelity_verifier_token_ceiling is not None
                else 0
            ),
        )
        try:
            candidate = fidelity_verifier(fidelity_input)
        except Exception:
            candidate = None
        if isinstance(candidate, FidelityVerification):
            fidelity_verification = candidate
        else:
            # The adapter was invoked but did not return trustworthy usage.
            # Conservatively make the fallback ledger incomplete.
            assert policy.fidelity_verifier_sha256 is not None
            fidelity_verification = FidelityVerification(
                passed=False,
                input_binding_sha256=fidelity_input.binding_sha256,
                verifier_sha256=policy.fidelity_verifier_sha256,
                method="independent-model",
                independent_of_compiler=False,
                model_calls=1,
                model_id="unknown-verifier-adapter",
                total_tokens=None,
                usage_complete=False,
            )
    final = plan_route(
        source_text,
        capsule,
        receiver,
        token_counter,
        task_context=task_context,
        forecasts=forecasts,
        evidence=evidence,
        compile_outcome=compilation,
        fidelity_verification=fidelity_verification,
        surface_table=surface_table,
        active_surface=active_surface,
        retained_surface=retained_surface,
        silence_proof=silence_proof,
        routine=routine,
        policy=policy,
        utility_evidence_verifier=utility_evidence_verifier,
        capsule_comprehension_verifier=capsule_comprehension_verifier,
        task_context_comprehension_verifier=task_context_comprehension_verifier,
        silence_verifier=silence_verifier,
        routine_verifier=routine_verifier,
    )
    return PreparedMessage(
        route=final,
        compilation=compilation,
        fidelity_verification=fidelity_verification,
    )
