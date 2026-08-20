"""Deterministic provider-free mock adapter with scripted fault classes."""

from __future__ import annotations

import hashlib
import math
from typing import Mapping

from .protocol import CallRequest, CallResponse
from .records import Evidence, QARecord
from .representations import render_arm_record


MOCK_VERSION = "competitive-eval-scripted-mock-v1"


def mock_count(text: str) -> int:
    """A deterministic dry-run counter, explicitly not a provider tokenizer."""

    size = len(text.encode("utf-8"))
    return 0 if size == 0 else math.ceil(size / 4)


def scenario_key(
    dataset: str, item_key: str, ordered_pair: tuple[str, str], repeat_index: int
) -> str:
    material = (
        f"{MOCK_VERSION}|{dataset}|{item_key}|{ordered_pair[0]}->{ordered_pair[1]}|"
        f"{repeat_index}"
    )
    return hashlib.sha256(material.encode()).hexdigest()


class ScriptedMockAdapter:
    """Returns deterministic semantic intent; never imports an SDK or uses a socket."""

    is_mock = True

    def __init__(self, gold_by_episode: Mapping[str, str]):
        self.gold_by_episode = dict(gold_by_episode)
        self.invocations = 0

    def generate(self, request: CallRequest) -> CallResponse:
        self.invocations += 1
        value = request.value
        episode_id = value["episode_id"]
        gold = self.gold_by_episode[episode_id]
        scenario = value["mock_metadata"]["scenario_key"]
        code = int(scenario[:8], 16)
        attempt = value["attempt_index"]
        arm = value["arm"]
        agent = value["agent"]
        input_text = "\n".join(message["content"] for message in value["messages"])

        # Faults are paired by scenario because scenario_key excludes the arm.
        # Repair is deterministic and never adds task evidence.
        if attempt == 0 and code % 31 == 0:
            return self._response(request, "timeout", "", input_text, ())
        if attempt == 0 and code % 37 == 0:
            return self._response(request, "refused", "", input_text, ())
        # The secondary residues ensure the compact 108-episode published dry
        # run visibly exercises repair and surface-fallback ledgers.  The older
        # residues remain as additional deterministic fault vectors for tests.
        if (
            attempt == 0
            and value["turn_index"] == 0
            and (code % 17 == 0 or code % 11 == 0)
        ):
            return self._response(request, "completed", "MALFORMED", input_text, ("format_once",))

        record = QARecord(
            answer=gold,
            claims=("offline deterministic fixture",),
            evidence=(Evidence("scripted mock evidence", agent),),
            needs=(),
            act="agree",
        )
        output = render_arm_record(arm, record)
        faults: tuple[str, ...] = ()
        if (
            attempt == 0
            and (code % 13 == 0 or code % 7 == 0)
            and arm == "current_adaptive_surface"
        ):
            faults = ("surface_integrity",)
        return self._response(request, "completed", output, input_text, faults)

    @staticmethod
    def _response(
        request: CallRequest,
        status: str,
        output: str,
        input_text: str,
        faults: tuple[str, ...],
    ) -> CallResponse:
        logical_ns = 1_000_000 + int(request.call_id[:8], 16) % 5_000_000
        return CallResponse.build_mock(
            request=request,
            status=status,
            output_text=output,
            logical_input_tokens=mock_count(input_text),
            logical_output_tokens=mock_count(output),
            logical_model_ns=logical_ns,
            faults=faults,
        )
