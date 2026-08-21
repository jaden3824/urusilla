"""Provider-neutral call request and response objects."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence

from .canonical import (
    canonical_bytes,
    canonical_json,
    require_exact_keys,
    sha256_bytes,
)
from .errors import ManifestError


CALL_FORMAT = "competitive-eval-call-request-v1"
RESPONSE_FORMAT = "competitive-eval-call-response-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty_text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ManifestError(f"{label} must be non-empty text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ManifestError(f"{label} is not valid UTF-8 text") from exc
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ManifestError(f"{label} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class CallRequest:
    value: Mapping[str, Any]

    @classmethod
    def from_value(cls, raw: Mapping[str, Any]) -> "CallRequest":
        """Revalidate one imported request instead of trusting its self-digest.

        External operators need to receive and later return an exact request.
        A matching ``call_id`` string alone is insufficient because a caller
        could mutate nested messages, model settings, or mock metadata after
        construction.  This parser checks every field and recomputes both the
        idempotency key and the content identity.
        """

        if type(raw) is not dict:
            raise ManifestError("call request must be a JSON object")
        require_exact_keys(
            raw,
            (
                "format",
                "episode_id",
                "turn_index",
                "attempt_index",
                "purpose",
                "agent",
                "model_ref",
                "arm",
                "messages",
                "generation",
                "idempotency_key",
                "mock_metadata",
                "call_id",
            ),
            label="call request",
        )
        if raw["format"] != CALL_FORMAT:
            raise ManifestError("call request format differs")
        episode_id = _nonempty_text(raw["episode_id"], "episode_id")
        turn_index = _nonnegative_integer(raw["turn_index"], "turn_index")
        attempt_index = _nonnegative_integer(raw["attempt_index"], "attempt_index")
        if raw["purpose"] not in {"runtime", "format_repair"}:
            raise ManifestError(f"unknown call purpose: {raw['purpose']}")
        if raw["agent"] not in {"A", "B"}:
            raise ManifestError(f"unknown agent: {raw['agent']}")

        model_ref = raw["model_ref"]
        if type(model_ref) is not dict:
            raise ManifestError("call request model_ref must be an object")
        require_exact_keys(
            model_ref,
            ("family_code", "logical_model_id"),
            label="call request model_ref",
        )
        _nonempty_text(model_ref["family_code"], "model_ref.family_code")
        _nonempty_text(model_ref["logical_model_id"], "model_ref.logical_model_id")
        _nonempty_text(raw["arm"], "arm")

        messages = raw["messages"]
        if type(messages) is not list or not messages:
            raise ManifestError("call request messages must be a non-empty array")
        for index, message in enumerate(messages):
            if type(message) is not dict:
                raise ManifestError(f"message {index} is not an object")
            require_exact_keys(
                message,
                ("role", "content"),
                label=f"message {index}",
            )
            if message["role"] not in {"system", "user", "assistant"}:
                raise ManifestError(f"message {index} has an unknown role")
            if type(message["content"]) is not str:
                raise ManifestError(f"message {index} content is not text")
            try:
                message["content"].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ManifestError(f"message {index} content is not UTF-8") from exc

        generation = raw["generation"]
        if type(generation) is not dict:
            raise ManifestError("call request generation must be an object")
        require_exact_keys(
            generation,
            (
                "temperature",
                "maximum_output_tokens",
                "tools",
                "web",
                "grounding",
            ),
            label="call request generation",
        )
        if not (
            type(generation["temperature"]) is int
            and generation["temperature"] == 0
            and type(generation["maximum_output_tokens"]) is int
            and generation["maximum_output_tokens"] == 250
            and type(generation["tools"]) is bool
            and generation["tools"] is False
            and type(generation["web"]) is bool
            and generation["web"] is False
            and type(generation["grounding"]) is bool
            and generation["grounding"] is False
        ):
            raise ManifestError("call request generation settings changed")

        mock_metadata = raw["mock_metadata"]
        if type(mock_metadata) is not dict:
            raise ManifestError("call request mock_metadata must be an object")
        require_exact_keys(
            mock_metadata,
            ("scenario_key", "gold_answer_present"),
            label="call request mock_metadata",
        )
        _nonempty_text(mock_metadata["scenario_key"], "mock_metadata.scenario_key")
        if mock_metadata["gold_answer_present"] is not False:
            raise ManifestError("provider request cannot contain the gold answer")

        expected_idempotency = sha256_bytes(
            (
                f"{episode_id}|{turn_index}|{attempt_index}|{raw['purpose']}"
            ).encode()
        )
        if raw["idempotency_key"] != expected_idempotency:
            raise ManifestError("call request idempotency key mismatch")
        if (
            type(raw["call_id"]) is not str
            or _SHA256.fullmatch(raw["call_id"]) is None
        ):
            raise ManifestError("call request call_id is invalid")
        core = dict(raw)
        supplied_call_id = core.pop("call_id")
        if sha256_bytes(canonical_bytes(core)) != supplied_call_id:
            raise ManifestError("call request call_id digest mismatch")

        # Detach all nested values from caller-owned mutable objects.
        normalized = json.loads(canonical_json(raw))
        return cls(normalized)

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
        return cls.from_value(core)

    @property
    def call_id(self) -> str:
        return str(self.value["call_id"])

    @property
    def request_sha256(self) -> str:
        """Digest the complete frozen request, including its verified call ID."""

        return sha256_bytes(canonical_bytes(self.value))

    @property
    def settings_sha256(self) -> str:
        """Bind the requested logical endpoint and provider-neutral settings."""

        return sha256_bytes(
            canonical_bytes(
                {
                    "model_ref": self.value["model_ref"],
                    "generation": self.value["generation"],
                }
            )
        )

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
