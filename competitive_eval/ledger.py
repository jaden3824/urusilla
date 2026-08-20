"""Non-overlapping token, billing, wire, latency, repair, and fallback ledgers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .canonical import canonical_bytes, sha256_bytes
from .config import JUDGE_CATEGORY, LEDGER_CATEGORIES
from .errors import LedgerError


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise LedgerError(f"{label} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class TokenLedger:
    categories: Mapping[str, int]
    judge: int = 0
    provider_annotations: Mapping[str, int | str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if set(self.categories) != set(LEDGER_CATEGORIES):
            missing = sorted(set(LEDGER_CATEGORIES) - set(self.categories))
            extra = sorted(set(self.categories) - set(LEDGER_CATEGORIES))
            raise LedgerError(f"token categories differ; missing={missing}, extra={extra}")
        for name in LEDGER_CATEGORIES:
            _count(self.categories[name], name)
        _count(self.judge, JUDGE_CATEGORY)
        allowed_annotations = {
            "provider_input_tokens",
            "provider_output_tokens",
            "provider_total_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens_subset",
            "accepted_prediction_tokens",
            "rejected_prediction_tokens",
            "unclassified_usage_json",
            "provider_usage_status",
        }
        if not set(self.provider_annotations).issubset(allowed_annotations):
            raise LedgerError("unknown provider billing annotation")
        for key, value in self.provider_annotations.items():
            if key.endswith("_tokens") or key == "reasoning_tokens_subset":
                if value is not None:
                    _count(value, key)

    @property
    def t_total(self) -> int:
        return sum(self.categories.values())

    @property
    def study_tokens(self) -> int:
        return self.t_total + self.judge

    @property
    def research_input_tokens(self) -> int:
        return sum(
            self.categories[name]
            for name in (
                "task_input",
                "system_role",
                "agent_input_history",
                "format_induction",
                "encode_decode_model",
                "negotiation_profile",
                "repair_retry",
                "tool_request",
                "tool_result",
                "safety_filter",
            )
        )

    @property
    def research_output_tokens(self) -> int:
        return sum(
            self.categories[name]
            for name in (
                "agent_output_visible",
                "final_answer",
                "hidden_reasoning_billed",
            )
        )

    def reconciliation(self) -> dict[str, int | str | None]:
        provider_input = self.provider_annotations.get("provider_input_tokens")
        provider_output = self.provider_annotations.get("provider_output_tokens")
        return {
            "research_input_tokens": self.research_input_tokens,
            "research_output_tokens": self.research_output_tokens,
            "provider_input_tokens": provider_input,
            "provider_output_tokens": provider_output,
            "input_delta": (
                None if provider_input is None else int(provider_input) - self.research_input_tokens
            ),
            "output_delta": (
                None if provider_output is None else int(provider_output) - self.research_output_tokens
            ),
            "status": self.provider_annotations.get("provider_usage_status", "not_reported"),
        }

    def to_object(self) -> dict[str, Any]:
        return {
            **{name: self.categories[name] for name in LEDGER_CATEGORIES},
            "judge": self.judge,
            "t_total": self.t_total,
            "study_tokens": self.study_tokens,
            "provider_annotations": dict(self.provider_annotations),
            "reconciliation": self.reconciliation(),
        }


@dataclass(frozen=True)
class WireLedger:
    payload_utf8_bytes: int = 0
    full_envelope_bytes: int = 0
    base64_or_framing_bytes: int = 0
    cold_profile_bytes: int = 0
    retransmitted_bytes: int = 0
    integrity_bytes: int = 0

    def __post_init__(self) -> None:
        for name, value in self.to_object().items():
            _count(value, f"wire.{name}")
        if self.full_envelope_bytes < self.payload_utf8_bytes:
            raise LedgerError("full envelope bytes cannot be below payload bytes")

    @property
    def total_transmitted_bytes(self) -> int:
        return self.full_envelope_bytes + self.cold_profile_bytes + self.retransmitted_bytes

    def to_object(self) -> dict[str, int]:
        return {
            "payload_utf8_bytes": self.payload_utf8_bytes,
            "full_envelope_bytes": self.full_envelope_bytes,
            "base64_or_framing_bytes": self.base64_or_framing_bytes,
            "cold_profile_bytes": self.cold_profile_bytes,
            "retransmitted_bytes": self.retransmitted_bytes,
            "integrity_bytes": self.integrity_bytes,
        }


@dataclass(frozen=True)
class TimingLedger:
    encode_ns: int = 0
    decode_ns: int = 0
    queue_ns: int = 0
    network_ns: int = 0
    model_ns: int = 0
    repair_ns: int = 0
    end_to_end_ns: int = 0

    def __post_init__(self) -> None:
        for name, value in self.to_object().items():
            _count(value, f"timing.{name}")

    def to_object(self) -> dict[str, int]:
        return {
            "encode_ns": self.encode_ns,
            "decode_ns": self.decode_ns,
            "queue_ns": self.queue_ns,
            "network_ns": self.network_ns,
            "model_ns": self.model_ns,
            "repair_ns": self.repair_ns,
            "end_to_end_ns": self.end_to_end_ns,
        }


@dataclass(frozen=True)
class CallLedger:
    call_id: str
    call_kind: str
    agent: str
    model_code: str
    tokens: TokenLedger
    wire: WireLedger
    timing: TimingLedger
    actual_billed_usd: Decimal = Decimal("0")
    estimated_usd: Decimal = Decimal("0")
    was_repair: bool = False
    was_fallback: bool = False
    malformed_attempt: bool = False

    def __post_init__(self) -> None:
        if not self.call_id or self.agent not in {"A", "B"}:
            raise LedgerError("call identity is invalid")
        if self.call_kind not in {"mock_runtime", "mock_repair", "mock_fallback", "wire_control"}:
            raise LedgerError(f"unknown call kind: {self.call_kind}")
        if self.actual_billed_usd < 0 or self.estimated_usd < 0:
            raise LedgerError("dollar values cannot be negative")
        if self.call_kind.startswith("mock_") and self.actual_billed_usd != 0:
            raise LedgerError("offline mock calls must have zero actual billed cost")
        if self.tokens.categories["tool_request"] or self.tokens.categories["tool_result"]:
            raise LedgerError("the no-tools primary lane requires zero tool tokens")

    def to_object(self) -> dict[str, Any]:
        value = {
            "call_id": self.call_id,
            "call_kind": self.call_kind,
            "agent": self.agent,
            "model_code": self.model_code,
            "tokens": self.tokens.to_object(),
            "wire": {**self.wire.to_object(), "total_transmitted_bytes": self.wire.total_transmitted_bytes},
            "timing": self.timing.to_object(),
            "actual_billed_usd": format(self.actual_billed_usd, "f"),
            "estimated_usd": format(self.estimated_usd, "f"),
            "was_repair": self.was_repair,
            "was_fallback": self.was_fallback,
            "malformed_attempt": self.malformed_attempt,
        }
        value["call_ledger_sha256"] = sha256_bytes(canonical_bytes(value))
        return value


@dataclass(frozen=True)
class EpisodeLedger:
    episode_id: str
    calls: tuple[CallLedger, ...]
    base_calls: int
    repair_calls: int
    fallback_calls: int
    malformed_attempts: int
    timeout_attempts: int = 0
    refusal_attempts: int = 0

    def __post_init__(self) -> None:
        if not self.episode_id:
            raise LedgerError("episode ID is missing")
        for label, value in {
            "base_calls": self.base_calls,
            "repair_calls": self.repair_calls,
            "fallback_calls": self.fallback_calls,
            "malformed_attempts": self.malformed_attempts,
            "timeout_attempts": self.timeout_attempts,
            "refusal_attempts": self.refusal_attempts,
        }.items():
            _count(value, label)
        if self.base_calls > 8:
            raise LedgerError("episode exceeded the eight-base-call cap")
        if self.repair_calls > 1:
            raise LedgerError("episode exceeded the one-repair cap")
        if len({call.call_id for call in self.calls}) != len(self.calls):
            raise LedgerError("duplicate call IDs in episode")
        if self.repair_calls != sum(call.was_repair for call in self.calls):
            raise LedgerError("repair-call count does not reconcile")
        if self.fallback_calls != sum(call.was_fallback for call in self.calls):
            raise LedgerError("fallback-call count does not reconcile")
        if self.malformed_attempts != sum(call.malformed_attempt for call in self.calls):
            raise LedgerError("malformed-attempt count does not reconcile")

    @property
    def t_total(self) -> int:
        return sum(call.tokens.t_total for call in self.calls)

    @property
    def judge_tokens(self) -> int:
        return sum(call.tokens.judge for call in self.calls)

    @property
    def actual_billed_usd(self) -> Decimal:
        return sum((call.actual_billed_usd for call in self.calls), Decimal("0"))

    @property
    def estimated_usd(self) -> Decimal:
        return sum((call.estimated_usd for call in self.calls), Decimal("0"))

    @property
    def transmitted_bytes(self) -> int:
        return sum(call.wire.total_transmitted_bytes for call in self.calls)

    def aggregate_categories(self) -> dict[str, int]:
        return {
            name: sum(call.tokens.categories[name] for call in self.calls)
            for name in LEDGER_CATEGORIES
        }

    def to_object(self) -> dict[str, Any]:
        value = {
            "episode_id": self.episode_id,
            "calls": [call.to_object() for call in self.calls],
            "base_calls": self.base_calls,
            "repair_calls": self.repair_calls,
            "fallback_calls": self.fallback_calls,
            "malformed_attempts": self.malformed_attempts,
            "timeout_attempts": self.timeout_attempts,
            "refusal_attempts": self.refusal_attempts,
            "category_totals": self.aggregate_categories(),
            "t_total": self.t_total,
            "judge_tokens": self.judge_tokens,
            "actual_billed_usd": format(self.actual_billed_usd, "f"),
            "estimated_usd": format(self.estimated_usd, "f"),
            "transmitted_bytes": self.transmitted_bytes,
        }
        value["episode_ledger_sha256"] = sha256_bytes(canonical_bytes(value))
        return value


def empty_categories(**updates: int) -> dict[str, int]:
    result = {name: 0 for name in LEDGER_CATEGORIES}
    unknown = set(updates) - set(result)
    if unknown:
        raise LedgerError(f"unknown token category updates: {sorted(unknown)}")
    result.update(updates)
    return result


def call_ledger_from_object(value: Mapping[str, Any]) -> CallLedger:
    """Rebuild and revalidate a persisted call ledger."""

    try:
        token_object = value["tokens"]
        wire_object = value["wire"]
        timing_object = value["timing"]
        categories = {name: token_object[name] for name in LEDGER_CATEGORIES}
        tokens = TokenLedger(
            categories=categories,
            judge=token_object["judge"],
            provider_annotations=token_object["provider_annotations"],
        )
        wire = WireLedger(
            payload_utf8_bytes=wire_object["payload_utf8_bytes"],
            full_envelope_bytes=wire_object["full_envelope_bytes"],
            base64_or_framing_bytes=wire_object["base64_or_framing_bytes"],
            cold_profile_bytes=wire_object["cold_profile_bytes"],
            retransmitted_bytes=wire_object["retransmitted_bytes"],
            integrity_bytes=wire_object["integrity_bytes"],
        )
        timing = TimingLedger(
            encode_ns=timing_object["encode_ns"],
            decode_ns=timing_object["decode_ns"],
            queue_ns=timing_object["queue_ns"],
            network_ns=timing_object["network_ns"],
            model_ns=timing_object["model_ns"],
            repair_ns=timing_object["repair_ns"],
            end_to_end_ns=timing_object["end_to_end_ns"],
        )
        result = CallLedger(
            call_id=value["call_id"],
            call_kind=value["call_kind"],
            agent=value["agent"],
            model_code=value["model_code"],
            tokens=tokens,
            wire=wire,
            timing=timing,
            actual_billed_usd=Decimal(value["actual_billed_usd"]),
            estimated_usd=Decimal(value["estimated_usd"]),
            was_repair=value["was_repair"],
            was_fallback=value["was_fallback"],
            malformed_attempt=value["malformed_attempt"],
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise LedgerError(f"invalid persisted call ledger: {exc}") from exc
    observed_digest = value.get("call_ledger_sha256")
    if result.to_object()["call_ledger_sha256"] != observed_digest:
        raise LedgerError("persisted call ledger digest mismatch")
    return result


def combine_episode_ledgers(ledgers: Iterable[EpisodeLedger]) -> dict[str, Any]:
    values = tuple(ledgers)
    if len({value.episode_id for value in values}) != len(values):
        raise LedgerError("duplicate episode ledgers")
    categories = {
        name: sum(value.aggregate_categories()[name] for value in values)
        for name in LEDGER_CATEGORIES
    }
    return {
        "episodes": len(values),
        "category_totals": categories,
        "t_total": sum(categories.values()),
        "judge_tokens": sum(value.judge_tokens for value in values),
        "actual_billed_usd": format(
            sum((value.actual_billed_usd for value in values), Decimal("0")), "f"
        ),
        "estimated_usd": format(
            sum((value.estimated_usd for value in values), Decimal("0")), "f"
        ),
        "transmitted_bytes": sum(value.transmitted_bytes for value in values),
        "repair_calls": sum(value.repair_calls for value in values),
        "fallback_calls": sum(value.fallback_calls for value in values),
        "malformed_attempts": sum(value.malformed_attempts for value in values),
    }
