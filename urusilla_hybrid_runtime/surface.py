"""Session-local, evidence-gated evolution of the wire surface.

The semantic task context remains stable.  Only a reversible alias table and
its compact positional carrier may evolve.  Nothing here installs code,
persists state, grants authority, or treats human readability as an objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Callable, Mapping, Sequence

from .canonical import canonical_json, sha256_text, strict_json_loads
from .errors import SurfaceError
from .fidelity import FidelityVerification, FidelityVerificationInput
from .records import (
    ACTION_STATUSES,
    ACTS,
    OUTCOME_STATUSES,
    PublicActionState,
)
from .task_context import PublicTaskContext, validate_state_against_task_context


SURFACE_FORMAT = "urusilla-session-evolving-surface-draft/1"
EVOLVING_SURFACE_CAPSULE_SHA256 = (
    "sha256:b007fe91ee39abf9167b8d73a627f8ecba56c0f401850ac73b3981e534854848"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTEXT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$")
_SEMANTIC_REF = re.compile(
    r"^(act|action-status|outcome-status|predicate|action|effect|"
    r"uncertainty-target|uncertainty-model|uncertainty-basis):"
    r"[A-Za-z][A-Za-z0-9_.:/+-]{0,255}$"
)
_ROLE_LIKE = frozenset({"system", "assistant", "user", "tool", "developer"})
_NORMALIZED_ROLE_LIKE = frozenset(
    unicodedata.normalize("NFKC", item).casefold() for item in _ROLE_LIKE
)
# One scalar is deliberately stricter than human-oriented words.  It preserves
# non-English/opaque optimization while avoiding mixed-script role-like strings
# until a pinned UTS #39 confusable-skeleton implementation exists.
_MAX_ALIAS_CODEPOINTS = 1
_BLANK_LIKE_SCALARS = frozenset(
    {
        "\u115f",  # HANGUL CHOSEONG FILLER
        "\u1160",  # HANGUL JUNGSEONG FILLER
        "\u2800",  # BRAILLE PATTERN BLANK
        "\u3164",  # HANGUL FILLER
        "\U00013441",  # EGYPTIAN HIEROGLYPH FULL BLANK
        "\U00013442",  # EGYPTIAN HIEROGLYPH HALF BLANK
        "\uffa0",  # HALFWIDTH HANGUL FILLER
    }
)


def _fail(message: str) -> None:
    raise SurfaceError(message)


def _validate_alias(alias: str) -> str:
    if type(alias) is not str or not alias or len(alias) > _MAX_ALIAS_CODEPOINTS:
        _fail("surface alias must be non-empty bounded Unicode text")
    if unicodedata.normalize("NFC", alias) != alias:
        _fail("surface alias must already be NFC-normalized")
    if (
        unicodedata.normalize("NFKC", alias).casefold() in _NORMALIZED_ROLE_LIKE
        or "<|" in alias
        or "|>" in alias
    ):
        _fail("surface alias resembles a model role/control token")
    previous_was_base = False
    for char in alias:
        category = unicodedata.category(char)
        if char in _BLANK_LIKE_SCALARS:
            _fail("surface alias contains a blank-like Unicode scalar")
        if category[0] in {"C", "P", "Z"} or char.isspace():
            _fail("surface alias contains a control, separator, or delimiter")
        if char in {"\ufe0e", "\ufe0f"} or 0xE0100 <= ord(char) <= 0xE01EF:
            _fail("surface alias contains a variation selector")
        if category[0] == "M" and not previous_was_base:
            _fail("surface alias cannot begin with a combining mark")
        previous_was_base = category[0] != "M"
    try:
        alias.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SurfaceError("surface alias is not valid UTF-8") from exc
    return alias


def _wire_value(semantic_ref: str) -> str:
    return semantic_ref.split(":", 1)[1]


def allowed_semantic_refs(task_context: PublicTaskContext) -> frozenset[str]:
    value = task_context.to_object()
    refs = {f"act:{item}" for item in value["allowed_acts"]}
    refs.update(f"action-status:{item}" for item in ACTION_STATUSES)
    refs.update(
        f"outcome-status:{item}"
        for item in value["outcome_contract"]["statuses"]
    )
    for symbol in value["symbols"]:
        kind = str(symbol["kind"])
        name = str(symbol["name"])
        refs.add(f"{kind}:{name}")
    uncertainty = value["uncertainty_contract"]
    refs.update(
        f"uncertainty-target:{item}" for item in uncertainty["targets"]
    )
    refs.update(
        f"uncertainty-model:{item}" for item in uncertainty["models"]
    )
    refs.update(
        f"uncertainty-basis:{item}" for item in uncertainty["basis_sources"]
    )
    return frozenset(refs)


@dataclass(frozen=True)
class SurfaceScope:
    session_id: str
    model_context_id: str
    capsule_sha256: str
    surface_capsule_sha256: str
    task_profile_sha256: str
    symbol_table_sha256: str
    tokenizer_ids: tuple[str, ...]
    session_only: bool = True
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        for name in ("session_id", "model_context_id"):
            value = getattr(self, name)
            if type(value) is not str or _CONTEXT_ID.fullmatch(value) is None:
                _fail(f"surface scope {name} is invalid")
        for name in (
            "capsule_sha256",
            "surface_capsule_sha256",
            "task_profile_sha256",
            "symbol_table_sha256",
        ):
            value = getattr(self, name)
            if type(value) is not str or _SHA256.fullmatch(value) is None:
                _fail(f"surface scope {name} is invalid")
        if self.surface_capsule_sha256 != EVOLVING_SURFACE_CAPSULE_SHA256:
            _fail("surface scope uses an unknown evolving-surface Capsule")
        if (
            type(self.tokenizer_ids) is not tuple
            or not self.tokenizer_ids
            or len(set(self.tokenizer_ids)) != len(self.tokenizer_ids)
            or any(
                type(item) is not str or _CONTEXT_ID.fullmatch(item) is None
                for item in self.tokenizer_ids
            )
        ):
            _fail("surface scope requires unique bounded tokenizer ids")
        if self.session_only is not True:
            _fail("evolving surfaces must remain session-local")
        for name in (
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            if type(getattr(self, name)) is not bool or getattr(self, name):
                _fail(f"surface scope crossed a prohibited boundary: {name}")

    def to_object(self) -> dict[str, object]:
        return {
            "format": SURFACE_FORMAT,
            "session_id": self.session_id,
            "model_context_id": self.model_context_id,
            "capsule_sha256": self.capsule_sha256,
            "surface_capsule_sha256": self.surface_capsule_sha256,
            "task_profile_sha256": self.task_profile_sha256,
            "symbol_table_sha256": self.symbol_table_sha256,
            "tokenizer_ids": list(self.tokenizer_ids),
            "session_only": self.session_only,
            "authority_boundary": {
                "persistence_created": self.persistence_created,
                "permission_expanded": self.permission_expanded,
                "spending_authority_created": self.spending_authority_created,
                "external_effects_performed": self.external_effects_performed,
            },
        }


_ALIAS_TABLE_FIELDS = ("scope", "generation", "parent_sha256", "aliases")


class _AliasTableSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _alias_table_fingerprint(values: Mapping[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _ALIAS_TABLE_FIELDS))
    )


@dataclass(frozen=True)
class SurfaceAliasTable:
    scope: SurfaceScope
    generation: int
    parent_sha256: str | None
    aliases: tuple[tuple[str, str], ...]
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {name: getattr(self, name) for name in _ALIAS_TABLE_FIELDS}
        if (
            not isinstance(self._construction_seal, _AliasTableSeal)
            or self._construction_seal.fingerprint
            != _alias_table_fingerprint(values)
        ):
            _fail("SurfaceAliasTable must be created by from_mapping")
        if type(self.generation) is not int or self.generation < 1:
            _fail("surface generation must be positive")
        if self.parent_sha256 is not None and (
            type(self.parent_sha256) is not str
            or _SHA256.fullmatch(self.parent_sha256) is None
        ):
            _fail("surface parent digest is invalid")
        if self.generation == 1 and self.parent_sha256 is not None:
            _fail("first surface generation cannot have a parent")
        if self.generation > 1 and self.parent_sha256 is None:
            _fail("later surface generation requires its exact parent")
        if type(self.aliases) is not tuple or not self.aliases:
            _fail("surface alias table cannot be empty")
        if tuple(sorted(self.aliases)) != self.aliases:
            _fail("surface aliases must be sorted by semantic reference")
        refs: list[str] = []
        aliases: list[str] = []
        normalized_aliases: list[str] = []
        for item in self.aliases:
            if type(item) is not tuple or len(item) != 2:
                _fail("surface alias entry is invalid")
            semantic_ref, alias = item
            if type(semantic_ref) is not str or _SEMANTIC_REF.fullmatch(semantic_ref) is None:
                _fail("surface semantic reference is invalid")
            refs.append(semantic_ref)
            aliases.append(_validate_alias(alias))
            normalized_aliases.append(
                unicodedata.normalize("NFKC", alias).casefold()
            )
        if len(set(refs)) != len(refs):
            _fail("surface semantic references are duplicated")
        if len(set(aliases)) != len(aliases):
            _fail("surface aliases must be injective")
        if len(set(normalized_aliases)) != len(normalized_aliases):
            _fail("surface aliases collide after compatibility normalization")

    @classmethod
    def from_mapping(
        cls,
        *,
        scope: SurfaceScope,
        task_context: PublicTaskContext,
        aliases: Mapping[str, str],
        parent: "SurfaceAliasTable" | None = None,
    ) -> "SurfaceAliasTable":
        if scope.task_profile_sha256 != task_context.task_profile_sha256:
            _fail("surface scope and task profile differ")
        if scope.symbol_table_sha256 != task_context.symbol_table_sha256:
            _fail("surface scope and symbol table differ")
        if parent is not None and parent.scope != scope:
            _fail("surface parent belongs to another exact scope")
        allowed = allowed_semantic_refs(task_context)
        if not set(aliases).issubset(allowed):
            _fail("surface table contains an undeclared semantic reference")
        reserved = {_wire_value(item) for item in allowed}
        normalized_reserved = {
            unicodedata.normalize("NFKC", item).casefold() for item in reserved
        }
        for semantic_ref, alias in aliases.items():
            _validate_alias(alias)
            if (
                alias in reserved
                or alias == _wire_value(semantic_ref)
                or unicodedata.normalize("NFKC", alias).casefold()
                in normalized_reserved
            ):
                _fail("surface alias collides with an unaliased semantic token")
        values = {
            "scope": scope,
            "generation": 1 if parent is None else parent.generation + 1,
            "parent_sha256": None if parent is None else parent.sha256,
            "aliases": tuple(sorted(aliases.items())),
        }
        return cls(
            **values,
            _construction_seal=_AliasTableSeal(
                _alias_table_fingerprint(values)
            ),
        )

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self.aliases)

    @property
    def inverse(self) -> dict[str, str]:
        return {alias: ref for ref, alias in self.aliases}

    @property
    def canonical_text(self) -> str:
        return canonical_json(
            {
                "scope": self.scope.to_object(),
                "generation": self.generation,
                "parent_sha256": self.parent_sha256,
                "aliases": [list(item) for item in self.aliases],
            }
        )

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class SurfaceActivationEvidence:
    table_sha256: str
    attempt_sha256: str
    session_id: str
    model_context_id: str
    round_trip_vectors_sha256: str
    verifier_sha256: str
    sender_acknowledged: bool
    receiver_acknowledged: bool
    exact_round_trip_passed: bool
    comprehension_passed: bool
    setup_total_tokens: int | None
    usage_complete: bool
    session_only: bool = True
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "table_sha256",
            "attempt_sha256",
            "round_trip_vectors_sha256",
            "verifier_sha256",
        ):
            value = getattr(self, name)
            if type(value) is not str or _SHA256.fullmatch(value) is None:
                _fail(f"surface activation {name} is invalid")
        for name in ("session_id", "model_context_id"):
            value = getattr(self, name)
            if type(value) is not str or _CONTEXT_ID.fullmatch(value) is None:
                _fail(f"surface activation {name} is invalid")
        for name in (
            "sender_acknowledged",
            "receiver_acknowledged",
            "exact_round_trip_passed",
            "comprehension_passed",
            "usage_complete",
            "session_only",
        ):
            if type(getattr(self, name)) is not bool:
                _fail(f"surface activation {name} must be boolean")
        if self.setup_total_tokens is not None and (
            type(self.setup_total_tokens) is not int or self.setup_total_tokens < 0
        ):
            _fail("surface activation setup tokens are invalid")
        if self.usage_complete is not (self.setup_total_tokens is not None):
            _fail("surface activation usage completeness is inconsistent")
        if not self.session_only:
            _fail("surface activation must remain session-local")
        for name in (
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            if type(getattr(self, name)) is not bool or getattr(self, name):
                _fail(f"surface activation crossed a prohibited boundary: {name}")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "table_sha256": self.table_sha256,
                    "attempt_sha256": self.attempt_sha256,
                    "session_id": self.session_id,
                    "model_context_id": self.model_context_id,
                    "round_trip_vectors_sha256": self.round_trip_vectors_sha256,
                    "verifier_sha256": self.verifier_sha256,
                    "sender_acknowledged": self.sender_acknowledged,
                    "receiver_acknowledged": self.receiver_acknowledged,
                    "exact_round_trip_passed": self.exact_round_trip_passed,
                    "comprehension_passed": self.comprehension_passed,
                    "setup_total_tokens": self.setup_total_tokens,
                    "usage_complete": self.usage_complete,
                    "session_only": self.session_only,
                }
            )
        )

    def claims_match(
        self,
        table: SurfaceAliasTable,
        attempt_sha256: str,
    ) -> bool:
        return all(
            (
                self.table_sha256 == table.sha256,
                self.attempt_sha256 == attempt_sha256,
                self.session_id == table.scope.session_id,
                self.model_context_id == table.scope.model_context_id,
                self.sender_acknowledged,
                self.receiver_acknowledged,
                self.exact_round_trip_passed,
                self.comprehension_passed,
                self.usage_complete,
            )
        )


@dataclass(frozen=True)
class SurfaceArtifactVerification:
    passed: bool
    input_binding_sha256: str
    verifier_sha256: str
    deterministic_local: bool = True
    model_calls: int = 0
    total_tokens: int = 0
    tools_used: bool = False
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            _fail("surface artifact verification passed must be boolean")
        for name in ("input_binding_sha256", "verifier_sha256"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                _fail(f"surface artifact verification {name} is invalid")
        if self.deterministic_local is not True:
            _fail("surface artifact verification must be deterministic/local")
        if type(self.model_calls) is not int or self.model_calls != 0:
            _fail("surface artifact verification cannot call a model")
        if type(self.total_tokens) is not int or self.total_tokens != 0:
            _fail("surface artifact verification cannot consume model tokens")
        if type(self.tools_used) is not bool or self.tools_used:
            _fail("surface artifact verification cannot use tools")
        for name in (
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            if type(getattr(self, name)) is not bool or getattr(self, name):
                _fail(f"surface artifact verification crossed boundary: {name}")


_ACTIVE_SURFACE_FIELDS = (
    "table_sha256",
    "attempt_sha256",
    "capsule_sha256",
    "session_id",
    "model_context_id",
    "generation",
    "activation_binding_sha256",
    "round_trip_vectors_sha256",
    "verifier_sha256",
    "setup_total_tokens",
)


class _ActiveSurfaceSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _active_surface_fingerprint(values: Mapping[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _ACTIVE_SURFACE_FIELDS))
    )


@dataclass(frozen=True)
class ActiveSurface:
    table_sha256: str
    attempt_sha256: str
    capsule_sha256: str
    session_id: str
    model_context_id: str
    generation: int
    activation_binding_sha256: str
    round_trip_vectors_sha256: str
    verifier_sha256: str
    setup_total_tokens: int
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {name: getattr(self, name) for name in _ACTIVE_SURFACE_FIELDS}
        if (
            not isinstance(self._construction_seal, _ActiveSurfaceSeal)
            or self._construction_seal.fingerprint
            != _active_surface_fingerprint(values)
        ):
            _fail("ActiveSurface must be created by activate_surface")
        for name in (
            "table_sha256",
            "attempt_sha256",
            "capsule_sha256",
            "activation_binding_sha256",
            "round_trip_vectors_sha256",
            "verifier_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                _fail(f"active surface {name} is invalid")
        for name in ("session_id", "model_context_id"):
            if _CONTEXT_ID.fullmatch(getattr(self, name)) is None:
                _fail(f"active surface {name} is invalid")
        if type(self.generation) is not int or self.generation < 1:
            _fail("active surface generation is invalid")
        if type(self.setup_total_tokens) is not int or self.setup_total_tokens < 0:
            _fail("active surface setup tokens are invalid")

    def authorizes(self, table: SurfaceAliasTable) -> bool:
        return all(
            (
                self.table_sha256 == table.sha256,
                self.capsule_sha256 == table.scope.capsule_sha256,
                self.session_id == table.scope.session_id,
                self.model_context_id == table.scope.model_context_id,
                self.generation == table.generation,
            )
        )


def activate_surface(
    table: SurfaceAliasTable,
    evidence: SurfaceActivationEvidence,
    *,
    attempt_sha256: str,
    active_capsule_sha256: str,
    expected_round_trip_vectors_sha256: str,
    expected_verifier_sha256: str,
    verifier: Callable[
        [SurfaceActivationEvidence, SurfaceAliasTable],
        SurfaceArtifactVerification,
    ],
) -> ActiveSurface:
    for name, value in (
        ("attempt_sha256", attempt_sha256),
        ("expected_round_trip_vectors_sha256", expected_round_trip_vectors_sha256),
        ("expected_verifier_sha256", expected_verifier_sha256),
    ):
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            _fail(f"surface activation {name} is invalid")
    if active_capsule_sha256 != table.scope.capsule_sha256:
        _fail("surface table belongs to another Capsule")
    if not evidence.claims_match(table, attempt_sha256):
        _fail("surface activation claims do not authorize the table")
    if evidence.round_trip_vectors_sha256 != expected_round_trip_vectors_sha256:
        _fail("surface activation vectors differ from the frozen plan")
    if evidence.verifier_sha256 != expected_verifier_sha256:
        _fail("surface activation verifier differs from the frozen plan")
    try:
        result = verifier(evidence, table)
    except Exception as exc:
        raise SurfaceError("surface activation artifact verifier failed") from exc
    if (
        not isinstance(result, SurfaceArtifactVerification)
        or not result.passed
        or result.input_binding_sha256 != evidence.binding_sha256
        or result.verifier_sha256 != expected_verifier_sha256
    ):
        _fail("surface activation artifact verification failed")
    active_values = {
        "table_sha256": table.sha256,
        "attempt_sha256": attempt_sha256,
        "capsule_sha256": active_capsule_sha256,
        "session_id": table.scope.session_id,
        "model_context_id": table.scope.model_context_id,
        "generation": table.generation,
        "activation_binding_sha256": evidence.binding_sha256,
        "round_trip_vectors_sha256": evidence.round_trip_vectors_sha256,
        "verifier_sha256": result.verifier_sha256,
        "setup_total_tokens": evidence.setup_total_tokens,
    }
    return ActiveSurface(
        **active_values,
        _construction_seal=_ActiveSurfaceSeal(
            _active_surface_fingerprint(active_values)
        ),
    )


def _encode_ref(table: SurfaceAliasTable, kind: str, value: str) -> str:
    return table.mapping.get(f"{kind}:{value}", value)


def _decode_ref(table: SurfaceAliasTable, kind: str, value: object) -> str:
    if type(value) is not str:
        _fail(f"surface {kind} token must be text")
    semantic_ref = table.inverse.get(value)
    if semantic_ref is None:
        return value
    prefix, decoded = semantic_ref.split(":", 1)
    if prefix != kind:
        _fail("surface alias appeared in the wrong semantic position")
    return decoded


def _encode_atom(atom: Mapping[str, object], table: SurfaceAliasTable) -> list[object]:
    return [
        _encode_ref(table, "predicate", str(atom["p"])),
        atom["a"],
        1 if atom["n"] else 0,
        atom["src"],
    ]


def _decode_atom(value: object, table: SurfaceAliasTable) -> dict[str, object]:
    if (
        type(value) is not list
        or len(value) != 4
        or type(value[2]) is not int
        or value[2] not in {0, 1}
    ):
        _fail("surface atom shape is invalid")
    return {
        "p": _decode_ref(table, "predicate", value[0]),
        "a": value[1],
        "n": bool(value[2]),
        "src": value[3],
    }


def _validate_surface_fidelity(
    state: PublicActionState,
    task_context: PublicTaskContext,
    fidelity_input: FidelityVerificationInput,
    fidelity_verification: FidelityVerification,
    expected_fidelity_verifier_sha256: str,
) -> None:
    if _SHA256.fullmatch(expected_fidelity_verifier_sha256) is None:
        _fail("surface expected fidelity verifier digest is invalid")
    if (
        fidelity_input.state.sha256 != state.sha256
        or fidelity_input.task_context.sha256 != task_context.sha256
    ):
        _fail("surface fidelity input belongs to another state or task")
    if (
        not fidelity_verification.passed
        or not fidelity_verification.independent_of_compiler
        or not fidelity_verification.usage_complete
        or fidelity_verification.total_tokens is None
        or fidelity_verification.total_tokens
        > fidelity_input.maximum_total_tokens
        or fidelity_verification.input_binding_sha256
        != fidelity_input.binding_sha256
        or fidelity_verification.verifier_sha256
        != expected_fidelity_verifier_sha256
    ):
        _fail("surface state lacks exact passing per-message fidelity evidence")


@dataclass(frozen=True)
class SurfaceCarrier:
    """Identity-bound host envelope; only payload_text is model-visible.

    The exact table/session/context identity is verified outside the model
    prompt.  This prevents sibling-table alias confusion without charging a
    64-hex digest to every model input.  Transport authenticity remains an
    external trust boundary; hashes alone are not a MAC or signature.
    """

    table_sha256: str
    session_id: str
    model_context_id: str
    generation: int
    task_context_sha256: str
    source_sha256: str
    state_sha256: str
    payload_text: str
    payload_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "table_sha256",
            "task_context_sha256",
            "source_sha256",
            "state_sha256",
            "payload_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                _fail(f"surface carrier {name} is invalid")
        for name in ("session_id", "model_context_id"):
            value = getattr(self, name)
            if type(value) is not str or _CONTEXT_ID.fullmatch(value) is None:
                _fail(f"surface carrier {name} is invalid")
        if type(self.generation) is not int or self.generation < 1:
            _fail("surface carrier generation is invalid")
        try:
            parsed = strict_json_loads(self.payload_text)
        except ValueError as exc:
            raise SurfaceError("surface carrier payload is not strict JSON") from exc
        if canonical_json(parsed) != self.payload_text:
            _fail("surface carrier payload is not canonical JSON")
        if sha256_text(self.payload_text) != self.payload_sha256:
            _fail("surface carrier payload digest mismatch")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "table_sha256": self.table_sha256,
                    "session_id": self.session_id,
                    "model_context_id": self.model_context_id,
                    "generation": self.generation,
                    "task_context_sha256": self.task_context_sha256,
                    "source_sha256": self.source_sha256,
                    "state_sha256": self.state_sha256,
                    "payload_sha256": self.payload_sha256,
                }
            )
        )


def encode_surface_state(
    state: PublicActionState,
    task_context: PublicTaskContext,
    table: SurfaceAliasTable,
    active_surface: ActiveSurface,
    *,
    fidelity_input: FidelityVerificationInput,
    fidelity_verification: FidelityVerification,
    expected_fidelity_verifier_sha256: str,
) -> SurfaceCarrier:
    if not active_surface.authorizes(table):
        _fail("surface table is not activated for this session/model context")
    if (
        table.scope.task_profile_sha256 != task_context.task_profile_sha256
        or table.scope.symbol_table_sha256 != task_context.symbol_table_sha256
    ):
        _fail("surface table is stale for this task profile")
    validate_state_against_task_context(state, task_context)
    _validate_surface_fidelity(
        state,
        task_context,
        fidelity_input,
        fidelity_verification,
        expected_fidelity_verifier_sha256,
    )
    value = state.to_object()
    goal = None if value["goal"] is None else _encode_atom(value["goal"], table)
    facts = [_encode_atom(item, table) for item in value["state"]]
    constraints = [
        [*_encode_atom(item, table), 1 if item["hard"] else 0]
        for item in value["constraints"]
    ]
    action_value = value["action"]
    action = None
    if action_value is not None:
        action_name = str(action_value["name"])
        action = [
            _encode_ref(table, "action", action_name),
            action_value["args"],
            _encode_ref(table, "action-status", str(action_value["status"])),
            [
                _encode_ref(table, "effect", str(item))
                for item in action_value["effects"]
            ],
        ]
    outcome_value = value["outcome"]
    outcome = None
    if outcome_value is not None:
        outcome = [
            _encode_ref(table, "outcome-status", str(outcome_value["status"])),
            outcome_value["value"],
            [_encode_atom(item, table) for item in outcome_value["evidence"]],
        ]
    uncertainty = [
        [
            _encode_ref(table, "uncertainty-target", str(item["target"])),
            _encode_ref(table, "uncertainty-model", str(item["model"])),
            item["confidence_ppm"],
            [
                _encode_ref(table, "uncertainty-basis", str(basis))
                for basis in item["basis"]
            ],
        ]
        for item in value["uncertainty"]
    ]
    carrier = [
        table.generation,
        _encode_ref(table, "act", str(value["act"])),
        goal,
        facts,
        constraints,
        action,
        outcome,
        [_encode_atom(item, table) for item in value["needs"]],
        uncertainty,
    ]
    payload_text = canonical_json(carrier)
    return SurfaceCarrier(
        table_sha256=table.sha256,
        session_id=table.scope.session_id,
        model_context_id=table.scope.model_context_id,
        generation=table.generation,
        task_context_sha256=task_context.sha256,
        source_sha256=fidelity_input.source_sha256,
        state_sha256=state.sha256,
        payload_text=payload_text,
        payload_sha256=sha256_text(payload_text),
    )


def decode_surface_state(
    carrier: SurfaceCarrier,
    task_context: PublicTaskContext,
    table: SurfaceAliasTable,
    active_surface: ActiveSurface,
    *,
    fidelity_input: FidelityVerificationInput,
    fidelity_verification: FidelityVerification,
    expected_fidelity_verifier_sha256: str,
) -> PublicActionState:
    if not active_surface.authorizes(table):
        _fail("surface table is not activated for this session/model context")
    if (
        table.scope.task_profile_sha256 != task_context.task_profile_sha256
        or table.scope.symbol_table_sha256 != task_context.symbol_table_sha256
    ):
        _fail("surface table is stale for this task profile")
    if not isinstance(carrier, SurfaceCarrier):
        _fail("surface carrier envelope is missing")
    if (
        carrier.table_sha256 != table.sha256
        or carrier.session_id != table.scope.session_id
        or carrier.model_context_id != table.scope.model_context_id
        or carrier.generation != table.generation
        or carrier.task_context_sha256 != task_context.sha256
        or carrier.source_sha256 != fidelity_input.source_sha256
    ):
        _fail("surface carrier is bound to another table/session/context")
    wire = strict_json_loads(carrier.payload_text)
    if type(wire) is not list or len(wire) != 9:
        _fail("surface carrier shape is invalid")
    if type(wire[0]) is not int or wire[0] != table.generation:
        _fail("surface carrier generation is stale or unknown")
    carrier_value = wire
    goal = None if carrier_value[2] is None else _decode_atom(carrier_value[2], table)
    if type(carrier_value[3]) is not list or type(carrier_value[4]) is not list:
        _fail("surface state/constraint arrays are invalid")
    constraints: list[dict[str, object]] = []
    for item in carrier_value[4]:
        if (
            type(item) is not list
            or len(item) != 5
            or type(item[4]) is not int
            or item[4] not in {0, 1}
        ):
            _fail("surface constraint shape is invalid")
        decoded = _decode_atom(item[:4], table)
        decoded["hard"] = bool(item[4])
        constraints.append(decoded)
    action = None
    if carrier_value[5] is not None:
        item = carrier_value[5]
        if type(item) is not list or len(item) != 4 or type(item[1]) is not dict:
            _fail("surface action shape is invalid")
        action_name = _decode_ref(table, "action", item[0])
        if type(item[3]) is not list:
            _fail("surface action effects are invalid")
        action = {
            "name": action_name,
            "args": item[1],
            "status": _decode_ref(table, "action-status", item[2]),
            "effects": [_decode_ref(table, "effect", effect) for effect in item[3]],
        }
    outcome = None
    if carrier_value[6] is not None:
        item = carrier_value[6]
        if type(item) is not list or len(item) != 3 or type(item[2]) is not list:
            _fail("surface outcome shape is invalid")
        outcome = {
            "status": _decode_ref(table, "outcome-status", item[0]),
            "value": item[1],
            "evidence": [_decode_atom(atom, table) for atom in item[2]],
        }
    if type(carrier_value[7]) is not list or type(carrier_value[8]) is not list:
        _fail("surface needs/uncertainty arrays are invalid")
    uncertainty: list[dict[str, object]] = []
    for item in carrier_value[8]:
        if type(item) is not list or len(item) != 4 or type(item[3]) is not list:
            _fail("surface uncertainty shape is invalid")
        uncertainty.append(
            {
                "target": _decode_ref(table, "uncertainty-target", item[0]),
                "model": _decode_ref(table, "uncertainty-model", item[1]),
                "confidence_ppm": item[2],
                "basis": [
                    _decode_ref(table, "uncertainty-basis", basis)
                    for basis in item[3]
                ],
            }
        )
    state = PublicActionState.from_object(
        {
            "format": "urusilla-public-action-state-draft/1",
            "act": _decode_ref(table, "act", carrier_value[1]),
            "goal": goal,
            "state": [_decode_atom(item, table) for item in carrier_value[3]],
            "constraints": constraints,
            "action": action,
            "outcome": outcome,
            "needs": [_decode_atom(item, table) for item in carrier_value[7]],
            "uncertainty": uncertainty,
        }
    )
    validate_state_against_task_context(state, task_context)
    if state.sha256 != carrier.state_sha256:
        _fail("surface decoded state digest differs from its bound state")
    _validate_surface_fidelity(
        state,
        task_context,
        fidelity_input,
        fidelity_verification,
        expected_fidelity_verifier_sha256,
    )
    return state


def optimize_alias_table(
    *,
    scope: SurfaceScope,
    task_context: PublicTaskContext,
    semantic_frequencies: Mapping[str, int],
    candidate_aliases: Sequence[str],
    token_counters: Mapping[str, Callable[[str], int]],
    parent: SurfaceAliasTable | None = None,
) -> SurfaceAliasTable:
    """Choose aliases by strict worst-tokenizer improvement over the parent.

    Generation one compares each alias with the canonical wire token.  A child
    compares with its exact parent's alias for that semantic reference and
    preserves every parent entry that no candidate strictly improves for every
    bound tokenizer.
    """

    if set(token_counters) != set(scope.tokenizer_ids):
        _fail("surface optimizer counters do not match the bound tokenizer scope")
    if parent is not None and parent.scope != scope:
        _fail("surface parent belongs to another session/model/tokenizer scope")
    allowed = allowed_semantic_refs(task_context)
    if not semantic_frequencies or not set(semantic_frequencies).issubset(allowed):
        _fail("surface optimizer frequencies contain undeclared semantics")
    for count in semantic_frequencies.values():
        if type(count) is not int or count <= 0:
            _fail("surface optimizer frequencies must be positive integers")
    unique_candidates: list[str] = []
    for alias in candidate_aliases:
        _validate_alias(alias)
        if alias not in unique_candidates:
            unique_candidates.append(alias)
    if not unique_candidates:
        _fail("surface optimizer has no valid candidates")

    parent_mapping = {} if parent is None else parent.mapping
    scored: list[tuple[int, str, str]] = []
    for semantic_ref, frequency in semantic_frequencies.items():
        baseline = parent_mapping.get(semantic_ref, _wire_value(semantic_ref))
        for alias in unique_candidates:
            deltas: list[int] = []
            for tokenizer_id, counter in token_counters.items():
                baseline_tokens = counter(baseline)
                alias_tokens = counter(alias)
                if (
                    type(baseline_tokens) is not int
                    or type(alias_tokens) is not int
                    or baseline_tokens < 0
                    or alias_tokens < 0
                ):
                    _fail(f"token counter {tokenizer_id} returned invalid usage")
                deltas.append(baseline_tokens - alias_tokens)
            score = frequency * min(deltas)
            if score > 0:
                scored.append((score, semantic_ref, alias))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected: dict[str, str] = dict(parent_mapping)
    used_aliases: set[str] = set(selected.values())
    retired_parent_aliases: set[str] = set(parent_mapping.values())
    improved_refs: set[str] = set()
    reserved = {_wire_value(item) for item in allowed}
    for _, semantic_ref, alias in scored:
        if semantic_ref in improved_refs or alias in reserved:
            continue
        previous = selected.get(semantic_ref)
        if alias in used_aliases and alias != previous:
            continue
        selected[semantic_ref] = alias
        used_aliases.add(alias)
        if previous is not None:
            retired_parent_aliases.add(previous)
            used_aliases.update(retired_parent_aliases)
        improved_refs.add(semantic_ref)
    if parent is not None and not improved_refs:
        _fail("child surface has no strict parent-relative tokenizer improvement")
    if not selected:
        _fail("no alias has positive savings for every bound tokenizer")
    return SurfaceAliasTable.from_mapping(
        scope=scope,
        task_context=task_context,
        aliases=selected,
        parent=parent,
    )


@dataclass(frozen=True)
class SurfaceTrialPlan:
    plan_artifact_sha256: str
    expected_activation_vectors_sha256: str
    expected_activation_verifier_sha256: str
    expected_trial_verifier_sha256: str
    exact_message_count: int
    minimum_messages: int
    shadow_call_token_ceiling: int
    shadow_aggregate_token_ceiling: int
    switching_margin_tokens_per_safe_completion: int
    require_all_parse_valid: bool = True
    require_all_fidelity_valid: bool = True
    require_negative_preservation: bool = True
    require_zero_boundary_violations: bool = True

    def __post_init__(self) -> None:
        for name in (
            "plan_artifact_sha256",
            "expected_activation_vectors_sha256",
            "expected_activation_verifier_sha256",
            "expected_trial_verifier_sha256",
        ):
            value = getattr(self, name)
            if type(value) is not str or _SHA256.fullmatch(value) is None:
                _fail(f"surface trial plan {name} is invalid")
        if type(self.exact_message_count) is not int or self.exact_message_count <= 0:
            _fail("surface trial plan exact_message_count must be positive")
        if type(self.minimum_messages) is not int or self.minimum_messages <= 0:
            _fail("surface trial plan minimum_messages must be positive")
        if self.exact_message_count < self.minimum_messages:
            _fail("surface trial exact count cannot be below its minimum")
        for name in (
            "shadow_call_token_ceiling",
            "shadow_aggregate_token_ceiling",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                _fail(f"surface trial plan {name} must be positive")
        if self.shadow_aggregate_token_ceiling < self.shadow_call_token_ceiling:
            _fail("shadow aggregate ceiling cannot be below its call ceiling")
        if (
            type(self.switching_margin_tokens_per_safe_completion) is not int
            or self.switching_margin_tokens_per_safe_completion < 0
        ):
            _fail("surface trial plan switching margin must be nonnegative")
        for name in (
            "require_all_parse_valid",
            "require_all_fidelity_valid",
            "require_negative_preservation",
            "require_zero_boundary_violations",
        ):
            if getattr(self, name) is not True:
                _fail(f"surface trial plan cannot weaken hard gate: {name}")

    @property
    def canonical_text(self) -> str:
        return canonical_json(
            {
                "plan_artifact_sha256": self.plan_artifact_sha256,
                "expected_activation_vectors_sha256": (
                    self.expected_activation_vectors_sha256
                ),
                "expected_activation_verifier_sha256": (
                    self.expected_activation_verifier_sha256
                ),
                "expected_trial_verifier_sha256": (
                    self.expected_trial_verifier_sha256
                ),
                "exact_message_count": self.exact_message_count,
                "minimum_messages": self.minimum_messages,
                "shadow_call_token_ceiling": self.shadow_call_token_ceiling,
                "shadow_aggregate_token_ceiling": (
                    self.shadow_aggregate_token_ceiling
                ),
                "switching_margin_tokens_per_safe_completion": (
                    self.switching_margin_tokens_per_safe_completion
                ),
                "require_all_parse_valid": self.require_all_parse_valid,
                "require_all_fidelity_valid": self.require_all_fidelity_valid,
                "require_negative_preservation": (
                    self.require_negative_preservation
                ),
                "require_zero_boundary_violations": (
                    self.require_zero_boundary_violations
                ),
            }
        )

    @property
    def sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class SurfaceTrial:
    table_sha256: str
    attempt_sha256: str
    activation_binding_sha256: str
    plan_sha256: str
    result_sha256: str
    transcript_sha256: str
    verifier_sha256: str
    executed_cases: tuple[tuple[str, str], ...]
    baseline_execution_binding_sha256s: tuple[str, ...]
    baseline_request_binding_sha256s: tuple[str, ...]
    baseline_configured_token_ceilings: tuple[int, ...]
    baseline_observed_total_tokens: tuple[int | None, ...]
    shadow_execution_binding_sha256s: tuple[str, ...]
    shadow_request_binding_sha256s: tuple[str, ...]
    shadow_configured_token_ceilings: tuple[int, ...]
    shadow_observed_total_tokens: tuple[int | None, ...]
    prior_evolution_overhead_tokens: int | None
    message_count: int
    baseline_total_tokens: int | None
    activation_setup_tokens: int
    surface_runtime_tokens_excluding_setup: int | None
    surface_total_tokens_including_setup: int | None
    baseline_safe_completions: int
    surface_safe_completions: int
    parse_valid: int
    fidelity_valid: int
    negation_preserved: bool
    null_preserved: bool
    failure_preserved: bool
    refusal_preserved: bool
    usage_complete: bool
    frozen_before_execution: bool
    measurement_scope_complete: bool
    persistence_created: bool = False
    permission_expanded: bool = False
    spending_authority_created: bool = False
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "table_sha256",
            "attempt_sha256",
            "activation_binding_sha256",
            "plan_sha256",
            "result_sha256",
            "transcript_sha256",
            "verifier_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                _fail(f"surface trial {name} is invalid")
        for name in (
            "message_count",
            "baseline_safe_completions",
            "surface_safe_completions",
            "parse_valid",
            "fidelity_valid",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                _fail(f"surface trial {name} must be nonnegative")
        if any(
            value > self.message_count
            for value in (
                self.baseline_safe_completions,
                self.surface_safe_completions,
                self.parse_valid,
                self.fidelity_valid,
            )
        ):
            _fail("surface trial counts exceed the message count")
        for name in (
            "executed_cases",
            "baseline_execution_binding_sha256s",
            "baseline_request_binding_sha256s",
            "baseline_configured_token_ceilings",
            "baseline_observed_total_tokens",
            "shadow_execution_binding_sha256s",
            "shadow_request_binding_sha256s",
            "shadow_configured_token_ceilings",
            "shadow_observed_total_tokens",
        ):
            value = getattr(self, name)
            if type(value) is not tuple or len(value) != self.message_count:
                _fail(f"surface trial {name} length differs from message_count")
        case_ids: list[str] = []
        case_sources: list[str] = []
        for item in self.executed_cases:
            if type(item) is not tuple or len(item) != 2:
                _fail("surface trial executed case entry is invalid")
            case_id, source_sha256 = item
            if type(case_id) is not str or _CONTEXT_ID.fullmatch(case_id) is None:
                _fail("surface trial executed case id is invalid")
            if (
                type(source_sha256) is not str
                or _SHA256.fullmatch(source_sha256) is None
            ):
                _fail("surface trial executed case source digest is invalid")
            case_ids.append(case_id)
            case_sources.append(source_sha256)
        if len(set(case_ids)) != len(case_ids) or len(set(case_sources)) != len(
            case_sources
        ):
            _fail("surface trial executed cases must be unique")
        for name in (
            "baseline_execution_binding_sha256s",
            "baseline_request_binding_sha256s",
            "shadow_execution_binding_sha256s",
            "shadow_request_binding_sha256s",
        ):
            values = getattr(self, name)
            if any(
                type(value) is not str or _SHA256.fullmatch(value) is None
                for value in values
            ):
                _fail(f"surface trial {name} contains an invalid digest")
            if len(set(values)) != len(values):
                _fail(f"surface trial {name} must bind unique calls")
        if len(
            set(
                self.baseline_execution_binding_sha256s
                + self.shadow_execution_binding_sha256s
            )
        ) != self.message_count * 2:
            _fail("baseline and surface execution receipts must be distinct")
        if len(
            set(
                self.baseline_request_binding_sha256s
                + self.shadow_request_binding_sha256s
            )
        ) != self.message_count * 2:
            _fail("baseline and surface request receipts must be distinct")
        if any(
            type(value) is not int or value <= 0
            for value in self.baseline_configured_token_ceilings
        ):
            _fail("surface trial baseline call ceilings must be positive integers")
        if any(
            type(value) is not int or value <= 0
            for value in self.shadow_configured_token_ceilings
        ):
            _fail("surface trial shadow call ceilings must be positive integers")
        if any(
            value is not None and (type(value) is not int or value < 0)
            for value in (
                self.baseline_observed_total_tokens
                + self.shadow_observed_total_tokens
            )
        ):
            _fail("surface trial observed call tokens are invalid")
        if self.prior_evolution_overhead_tokens is not None and (
            type(self.prior_evolution_overhead_tokens) is not int
            or self.prior_evolution_overhead_tokens < 0
        ):
            _fail("surface trial prior evolution overhead is invalid")
        if (
            type(self.activation_setup_tokens) is not int
            or self.activation_setup_tokens < 0
        ):
            _fail("surface trial activation setup tokens are invalid")
        for name in (
            "baseline_total_tokens",
            "surface_runtime_tokens_excluding_setup",
            "surface_total_tokens_including_setup",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                _fail(f"surface trial {name} is invalid")
        if self.usage_complete is not (
            self.baseline_total_tokens is not None
            and self.surface_runtime_tokens_excluding_setup is not None
            and self.surface_total_tokens_including_setup is not None
            and all(
                value is not None
                for value in (
                    self.baseline_observed_total_tokens
                    + self.shadow_observed_total_tokens
                )
            )
        ):
            _fail("surface trial usage completeness is inconsistent")
        if (
            self.usage_complete
            and self.surface_total_tokens_including_setup
            != self.activation_setup_tokens
            + self.surface_runtime_tokens_excluding_setup
        ):
            _fail("surface trial setup and runtime tokens do not reconcile")
        for name in (
            "negation_preserved",
            "null_preserved",
            "failure_preserved",
            "refusal_preserved",
            "usage_complete",
            "frozen_before_execution",
            "measurement_scope_complete",
            "persistence_created",
            "permission_expanded",
            "spending_authority_created",
            "external_effects_performed",
        ):
            if type(getattr(self, name)) is not bool:
                _fail(f"surface trial {name} must be boolean")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "table_sha256": self.table_sha256,
                    "attempt_sha256": self.attempt_sha256,
                    "activation_binding_sha256": self.activation_binding_sha256,
                    "plan_sha256": self.plan_sha256,
                    "result_sha256": self.result_sha256,
                    "transcript_sha256": self.transcript_sha256,
                    "verifier_sha256": self.verifier_sha256,
                    "executed_cases": [list(item) for item in self.executed_cases],
                    "baseline_execution_binding_sha256s": list(
                        self.baseline_execution_binding_sha256s
                    ),
                    "baseline_request_binding_sha256s": list(
                        self.baseline_request_binding_sha256s
                    ),
                    "baseline_configured_token_ceilings": list(
                        self.baseline_configured_token_ceilings
                    ),
                    "baseline_observed_total_tokens": list(
                        self.baseline_observed_total_tokens
                    ),
                    "shadow_execution_binding_sha256s": (
                        list(self.shadow_execution_binding_sha256s)
                    ),
                    "shadow_request_binding_sha256s": (
                        list(self.shadow_request_binding_sha256s)
                    ),
                    "shadow_configured_token_ceilings": (
                        list(self.shadow_configured_token_ceilings)
                    ),
                    "shadow_observed_total_tokens": (
                        list(self.shadow_observed_total_tokens)
                    ),
                    "prior_evolution_overhead_tokens": (
                        self.prior_evolution_overhead_tokens
                    ),
                    "message_count": self.message_count,
                    "baseline_total_tokens": self.baseline_total_tokens,
                    "activation_setup_tokens": self.activation_setup_tokens,
                    "surface_runtime_tokens_excluding_setup": (
                        self.surface_runtime_tokens_excluding_setup
                    ),
                    "surface_total_tokens_including_setup": (
                        self.surface_total_tokens_including_setup
                    ),
                    "baseline_safe_completions": self.baseline_safe_completions,
                    "surface_safe_completions": self.surface_safe_completions,
                    "parse_valid": self.parse_valid,
                    "fidelity_valid": self.fidelity_valid,
                    "negation_preserved": self.negation_preserved,
                    "null_preserved": self.null_preserved,
                    "failure_preserved": self.failure_preserved,
                    "refusal_preserved": self.refusal_preserved,
                    "usage_complete": self.usage_complete,
                    "frozen_before_execution": self.frozen_before_execution,
                    "measurement_scope_complete": self.measurement_scope_complete,
                    "persistence_created": self.persistence_created,
                    "permission_expanded": self.permission_expanded,
                    "spending_authority_created": self.spending_authority_created,
                    "external_effects_performed": self.external_effects_performed,
                }
            )
        )


_RETAINED_SURFACE_FIELDS = (
    "table_sha256",
    "attempt_sha256",
    "activation_binding_sha256",
    "session_id",
    "model_context_id",
    "generation",
    "plan_sha256",
    "plan_artifact_sha256",
    "trial_binding_sha256",
    "result_sha256",
    "transcript_sha256",
    "verifier_sha256",
    "surface_capsule_sha256",
)


class _RetainedSurfaceSeal:
    __slots__ = ("fingerprint",)

    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint


def _retained_surface_fingerprint(values: Mapping[str, object]) -> str:
    return sha256_text(
        repr(tuple((name, values[name]) for name in _RETAINED_SURFACE_FIELDS))
    )


@dataclass(frozen=True)
class RetainedSurface:
    """Unforgeable authorization for post-trial, session-local live routing.

    ``ActiveSurface`` proves only that a table can be decoded for a bounded
    shadow trial.  This stronger artifact is minted solely after every frozen
    trial gate passes and is required before the table can affect a live answer.
    It still grants no persistence, tool, spending, permission, or effect
    authority and cannot support a general performance claim by itself.
    """

    table_sha256: str
    attempt_sha256: str
    activation_binding_sha256: str
    session_id: str
    model_context_id: str
    generation: int
    plan_sha256: str
    plan_artifact_sha256: str
    trial_binding_sha256: str
    result_sha256: str
    transcript_sha256: str
    verifier_sha256: str
    surface_capsule_sha256: str
    _construction_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        values = {
            name: getattr(self, name) for name in _RETAINED_SURFACE_FIELDS
        }
        if (
            not isinstance(self._construction_seal, _RetainedSurfaceSeal)
            or self._construction_seal.fingerprint
            != _retained_surface_fingerprint(values)
        ):
            _fail("RetainedSurface must be created by decide_surface_evolution")
        for name in (
            "table_sha256",
            "attempt_sha256",
            "activation_binding_sha256",
            "plan_sha256",
            "plan_artifact_sha256",
            "trial_binding_sha256",
            "result_sha256",
            "transcript_sha256",
            "verifier_sha256",
            "surface_capsule_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                _fail(f"retained surface {name} is invalid")
        for name in ("session_id", "model_context_id"):
            if _CONTEXT_ID.fullmatch(getattr(self, name)) is None:
                _fail(f"retained surface {name} is invalid")
        if type(self.generation) is not int or self.generation < 1:
            _fail("retained surface generation is invalid")
        if self.surface_capsule_sha256 != EVOLVING_SURFACE_CAPSULE_SHA256:
            _fail("retained surface uses an unknown evolving-surface Capsule")

    @property
    def binding_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    name: getattr(self, name)
                    for name in _RETAINED_SURFACE_FIELDS
                }
            )
        )

    def authorizes(
        self,
        table: SurfaceAliasTable,
        active_surface: ActiveSurface,
    ) -> bool:
        return all(
            (
                active_surface.authorizes(table),
                self.table_sha256 == table.sha256,
                self.attempt_sha256 == active_surface.attempt_sha256,
                self.activation_binding_sha256
                == active_surface.activation_binding_sha256,
                self.session_id == table.scope.session_id,
                self.session_id == active_surface.session_id,
                self.model_context_id == table.scope.model_context_id,
                self.model_context_id == active_surface.model_context_id,
                self.generation == table.generation,
                self.generation == active_surface.generation,
                self.surface_capsule_sha256
                == table.scope.surface_capsule_sha256,
            )
        )


@dataclass(frozen=True)
class SurfaceEvolutionDecision:
    action: str
    table_sha256: str
    measured_savings_tokens: int | None
    reasons: tuple[str, ...]
    retained_surface: RetainedSurface | None = None

    def __post_init__(self) -> None:
        if self.action not in {"keep", "rollback"}:
            _fail("surface evolution action is unknown")
        if _SHA256.fullmatch(self.table_sha256) is None:
            _fail("surface evolution table digest is invalid")
        if self.measured_savings_tokens is not None and type(
            self.measured_savings_tokens
        ) is not int:
            _fail("surface evolution savings must be an integer or null")
        if type(self.reasons) is not tuple:
            _fail("surface evolution reasons must be a tuple")
        if self.action == "keep":
            if (
                not isinstance(self.retained_surface, RetainedSurface)
                or self.retained_surface.table_sha256 != self.table_sha256
                or self.reasons
            ):
                _fail("keep decision requires its exact retained-surface proof")
        elif self.retained_surface is not None:
            _fail("rollback decision cannot retain a live surface")


def decide_surface_evolution(
    table: SurfaceAliasTable,
    trial: SurfaceTrial,
    *,
    active_surface: ActiveSurface,
    plan: SurfaceTrialPlan,
    verifier: Callable[
        [SurfaceTrial, SurfaceTrialPlan, SurfaceAliasTable, ActiveSurface],
        SurfaceArtifactVerification,
    ],
) -> SurfaceEvolutionDecision:
    if trial.table_sha256 != table.sha256:
        _fail("surface trial belongs to a different table")
    reasons: list[str] = []
    if trial.plan_sha256 != plan.sha256:
        reasons.append("trial-plan-digest-mismatch")
    if (
        not active_surface.authorizes(table)
        or trial.activation_binding_sha256
        != active_surface.activation_binding_sha256
        or trial.attempt_sha256 != active_surface.attempt_sha256
    ):
        reasons.append("surface-not-activated-for-trial")
    if (
        active_surface.round_trip_vectors_sha256
        != plan.expected_activation_vectors_sha256
    ):
        reasons.append("activation-vectors-differ-from-frozen-plan")
    if active_surface.verifier_sha256 != plan.expected_activation_verifier_sha256:
        reasons.append("activation-verifier-differs-from-frozen-plan")
    if trial.verifier_sha256 != plan.expected_trial_verifier_sha256:
        reasons.append("trial-verifier-differs-from-frozen-plan")
    if trial.activation_setup_tokens != active_surface.setup_total_tokens:
        reasons.append("activation-setup-token-mismatch")
    try:
        verification = verifier(trial, plan, table, active_surface)
    except Exception:
        verification = None
    if (
        not isinstance(verification, SurfaceArtifactVerification)
        or not verification.passed
        or verification.input_binding_sha256 != trial.binding_sha256
        or verification.verifier_sha256 != plan.expected_trial_verifier_sha256
    ):
        reasons.append("trial-artifact-verification-failed")
    if not trial.frozen_before_execution:
        reasons.append("trial-plan-not-frozen-before-execution")
    if not trial.measurement_scope_complete:
        reasons.append("trial-measurement-scope-incomplete")
    if trial.message_count < plan.minimum_messages:
        reasons.append("insufficient-bounded-trial-messages")
    if trial.message_count != plan.exact_message_count:
        reasons.append("trial-message-count-differs-from-frozen-plan")
    if not trial.usage_complete:
        reasons.append("incomplete-total-token-usage")
    else:
        assert trial.surface_runtime_tokens_excluding_setup is not None
        assert all(
            value is not None for value in trial.shadow_observed_total_tokens
        )
        assert all(
            value is not None for value in trial.baseline_observed_total_tokens
        )
        baseline_call_tokens = tuple(
            int(value) for value in trial.baseline_observed_total_tokens
        )
        observed_call_tokens = tuple(
            int(value) for value in trial.shadow_observed_total_tokens
        )
        if (
            trial.surface_runtime_tokens_excluding_setup
            > plan.shadow_aggregate_token_ceiling
            or sum(observed_call_tokens) > plan.shadow_aggregate_token_ceiling
        ):
            reasons.append("shadow-aggregate-token-ceiling-exceeded")
        if any(
            value > plan.shadow_call_token_ceiling
            for value in observed_call_tokens
        ):
            reasons.append("shadow-call-token-ceiling-exceeded")
        if any(
            value > plan.shadow_call_token_ceiling
            for value in baseline_call_tokens
        ):
            reasons.append("baseline-call-token-ceiling-exceeded")
        if sum(baseline_call_tokens) > plan.shadow_aggregate_token_ceiling:
            reasons.append("baseline-aggregate-token-ceiling-exceeded")
        if sum(baseline_call_tokens) != trial.baseline_total_tokens:
            reasons.append("baseline-call-usage-total-mismatch")
        if sum(observed_call_tokens) > trial.surface_runtime_tokens_excluding_setup:
            reasons.append("shadow-call-usage-exceeds-surface-runtime")
    if trial.shadow_configured_token_ceilings != (
        plan.shadow_call_token_ceiling,
    ) * trial.message_count:
        reasons.append("shadow-call-token-ceiling-mismatch")
    if trial.baseline_configured_token_ceilings != (
        plan.shadow_call_token_ceiling,
    ) * trial.message_count:
        reasons.append("baseline-call-token-ceiling-mismatch")
    if trial.prior_evolution_overhead_tokens is None:
        reasons.append("prior-evolution-overhead-unknown")
    if trial.surface_safe_completions < trial.baseline_safe_completions:
        reasons.append("safe-completion-regression")
    if (
        trial.baseline_safe_completions == 0
        or trial.surface_safe_completions == 0
    ):
        reasons.append("no-safely-completed-task")
    if trial.parse_valid != trial.message_count:
        reasons.append("parse-error-observed")
    if trial.fidelity_valid != trial.message_count:
        reasons.append("semantic-fidelity-error-observed")
    for name in (
        "negation_preserved",
        "null_preserved",
        "failure_preserved",
        "refusal_preserved",
    ):
        if not getattr(trial, name):
            reasons.append(name.replace("_", "-") + "-failed")
    for name in (
        "persistence_created",
        "permission_expanded",
        "spending_authority_created",
        "external_effects_performed",
    ):
        if getattr(trial, name):
            reasons.append(name.replace("_", "-") + "-observed")
    savings = None
    if (
        trial.usage_complete
        and trial.baseline_safe_completions > 0
        and trial.surface_safe_completions > 0
    ):
        assert trial.baseline_total_tokens is not None
        assert trial.surface_total_tokens_including_setup is not None
        if trial.prior_evolution_overhead_tokens is None:
            effective_surface_total = None
        else:
            effective_surface_total = (
                trial.prior_evolution_overhead_tokens
                + trial.surface_total_tokens_including_setup
            )
        # Compare inclusive tokens per safely completed task without floats.
        advantage_scaled = None
        if effective_surface_total is not None:
            advantage_scaled = (
                trial.baseline_total_tokens * trial.surface_safe_completions
                - effective_surface_total * trial.baseline_safe_completions
            )
        denominator = (
            trial.baseline_safe_completions
            * trial.surface_safe_completions
        )
        if advantage_scaled is not None:
            savings = advantage_scaled // denominator
        if advantage_scaled is not None and advantage_scaled <= (
            plan.switching_margin_tokens_per_safe_completion * denominator
        ):
            reasons.append("no-strict-total-token-advantage")
    retained_surface = None
    if not reasons:
        retained_values = {
            "table_sha256": table.sha256,
            "attempt_sha256": trial.attempt_sha256,
            "activation_binding_sha256": (
                active_surface.activation_binding_sha256
            ),
            "session_id": table.scope.session_id,
            "model_context_id": table.scope.model_context_id,
            "generation": table.generation,
            "plan_sha256": plan.sha256,
            "plan_artifact_sha256": plan.plan_artifact_sha256,
            "trial_binding_sha256": trial.binding_sha256,
            "result_sha256": trial.result_sha256,
            "transcript_sha256": trial.transcript_sha256,
            "verifier_sha256": trial.verifier_sha256,
            "surface_capsule_sha256": table.scope.surface_capsule_sha256,
        }
        retained_surface = RetainedSurface(
            **retained_values,
            _construction_seal=_RetainedSurfaceSeal(
                _retained_surface_fingerprint(retained_values)
            ),
        )
    return SurfaceEvolutionDecision(
        action="rollback" if reasons else "keep",
        table_sha256=table.sha256,
        measured_savings_tokens=savings,
        reasons=tuple(reasons),
        retained_surface=retained_surface,
    )
