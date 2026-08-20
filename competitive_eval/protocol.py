"""Provider-neutral call request and response objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .canonical import canonical_bytes, canonical_json, sha256_bytes
from .errors import ManifestError


CALL_FORMAT = "competitive-eval-call-request-v1"
RESPONSE_FORMAT = "competitive-eval-call-response-v1"


@dataclass(frozen=True)
class CallRequest:
    value: Mapping[str, Any]

    @classmethod
    def build(
        cls,
        *,
        episode_id: str,
        turn_index: int,
        attempt_index: int,
        purpose: str,
        agent: str,
        model_code: str,
        logical_model_id: str,
        arm: str,
        messages: Sequence[Mapping[str, str]],
        mock_scenario_key: str,
    ) -> "CallRequest":
        if purpose not in {"runtime", "format_repair"}:
            raise ManifestError(f"unknown call purpose: {purpose}")
        if agent not in {"A", "B"}:
            raise ManifestError(f"unknown agent: {agent}")
        normalized_messages: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            if type(message) is not dict or set(message) != {"role", "content"}:
                raise ManifestError(f"message {index} is not provider-neutral role/content")
            if message["role"] not in {"system", "user", "assistant"}:
                raise ManifestError(f"message {index} has an unknown role")
            if type(message["content"]) is not str:
                raise ManifestError(f"message {index} content is not text")
            normalized_messages.append(dict(message))
        core: dict[str, Any] = {
            "format": CALL_FORMAT,
            "episode_id": episode_id,
            "turn_index": turn_index,
            "attempt_index": attempt_index,
            "purpose": purpose,
            "agent": agent,
            "model_ref": {
                "family_code": model_code,
                "logical_model_id": logical_model_id,
            },
            "arm": arm,
            "messages": normalized_messages,
            "generation": {
                "temperature": 0,
                "maximum_output_tokens": 250,
                "tools": False,
                "web": False,
                "grounding": False,
            },
            "idempotency_key": sha256_bytes(
                f"{episode_id}|{turn_index}|{attempt_index}|{purpose}".encode()
            ),
            "mock_metadata": {
                "scenario_key": mock_scenario_key,
                "gold_answer_present": False,
            },
        }
        core["call_id"] = sha256_bytes(canonical_bytes(core))
        return cls(core)

    @property
    def call_id(self) -> str:
        return str(self.value["call_id"])

    def to_json(self) -> str:
        return canonical_json(self.value)


@dataclass(frozen=True)
class CallResponse:
    value: Mapping[str, Any]

    @classmethod
    def build_mock(
        cls,
        *,
        request: CallRequest,
        status: str,
        output_text: str,
        logical_input_tokens: int,
        logical_output_tokens: int,
        logical_model_ns: int,
        faults: Sequence[str] = (),
    ) -> "CallResponse":
        if status not in {"completed", "timeout", "refused"}:
            raise ManifestError(f"unknown response status: {status}")
        for label, count in {
            "logical_input_tokens": logical_input_tokens,
            "logical_output_tokens": logical_output_tokens,
            "logical_model_ns": logical_model_ns,
        }.items():
            if type(count) is not int or count < 0:
                raise ManifestError(f"{label} must be a nonnegative integer")
        core: dict[str, Any] = {
            "format": RESPONSE_FORMAT,
            "call_id": request.call_id,
            "status": status,
            "output_text": output_text,
            "usage": {
                "counter": "deterministic_utf8_quarter_mock_v1",
                "input_tokens": logical_input_tokens,
                "output_tokens": logical_output_tokens,
                "provider_reported": False,
                "actual_billed_usd": "0",
            },
            "timing": {
                "mode": "deterministic_logical_mock_not_wall_clock",
                "model_ns": logical_model_ns,
            },
            "faults": list(faults),
            "provider_metadata": None,
        }
        core["response_sha256"] = sha256_bytes(canonical_bytes(core))
        return cls(core)

    @property
    def output_text(self) -> str:
        return str(self.value["output_text"])

    @property
    def status(self) -> str:
        return str(self.value["status"])

    def to_json(self) -> str:
        return canonical_json(self.value)

