"""Per-message source-to-action-state fidelity evidence.

Structural validity and a source digest do not prove semantic relevance.  This
module binds a candidate to the exact source, task profile, and verifier usage
before an action-state route can become eligible.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .canonical import canonical_json, sha256_text
from .errors import RoutingError
from .records import PublicActionState, source_text_sha256
from .task_context import PublicTaskContext


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
FIDELITY_METHODS = frozenset({"deterministic-local", "independent-model"})


@dataclass(frozen=True)
class FidelityVerificationInput:
    source_text: str
    source_sha256: str
    state: PublicActionState
    task_context: PublicTaskContext
    maximum_total_tokens: int

    def __post_init__(self) -> None:
        if source_text_sha256(self.source_text) != self.source_sha256:
            raise RoutingError("fidelity input source digest mismatch")
        if not isinstance(self.state, PublicActionState):
            raise RoutingError("fidelity input state is invalid")
        if not isinstance(self.task_context, PublicTaskContext):
            raise RoutingError("fidelity input task context is invalid")
        if (
            type(self.maximum_total_tokens) is not int
            or self.maximum_total_tokens < 0
        ):
            raise RoutingError(
                "fidelity input maximum_total_tokens must be nonnegative"
            )

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "source_sha256": self.source_sha256,
                    "state_sha256": self.state.sha256,
                    "task_context_sha256": self.task_context.sha256,
                    "task_profile_sha256": self.task_context.task_profile_sha256,
                    "symbol_table_sha256": self.task_context.symbol_table_sha256,
                    "maximum_total_tokens": self.maximum_total_tokens,
                }
            )
        )


@dataclass(frozen=True)
class FidelityVerification:
    passed: bool
    input_binding_sha256: str
    verifier_sha256: str
    method: str
    independent_of_compiler: bool
    model_calls: int
    model_id: str | None
    total_tokens: int | None
    usage_complete: bool
    tools_used: bool = False
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise RoutingError("fidelity verification passed must be boolean")
        for name in ("input_binding_sha256", "verifier_sha256"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise RoutingError(f"fidelity verification {name} is invalid")
        if self.method not in FIDELITY_METHODS:
            raise RoutingError("fidelity verification method is unknown")
        if type(self.independent_of_compiler) is not bool:
            raise RoutingError("fidelity verifier independence must be boolean")
        if type(self.model_calls) is not int or self.model_calls not in {0, 1}:
            raise RoutingError("fidelity verifier model_calls must be zero or one")
        if self.total_tokens is not None and (
            type(self.total_tokens) is not int or self.total_tokens < 0
        ):
            raise RoutingError("fidelity verifier tokens must be null or nonnegative")
        if type(self.usage_complete) is not bool:
            raise RoutingError("fidelity verifier usage_complete must be boolean")
        for name in (
            "tools_used",
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            value = getattr(self, name)
            if type(value) is not bool or value:
                raise RoutingError(f"fidelity verifier crossed a prohibited boundary: {name}")
        if self.method == "deterministic-local":
            if not (
                self.model_calls == 0
                and self.model_id is None
                and self.total_tokens == 0
                and self.usage_complete
            ):
                raise RoutingError("local fidelity verification usage is inconsistent")
        else:
            if self.model_calls != 1 or type(self.model_id) is not str or not self.model_id:
                raise RoutingError("model fidelity verification identity is incomplete")
            if self.usage_complete is not (self.total_tokens is not None):
                raise RoutingError("model fidelity usage completeness is inconsistent")
        if self.passed and not (
            self.independent_of_compiler and self.usage_complete
        ):
            raise RoutingError("passing fidelity evidence must be independent and complete")
