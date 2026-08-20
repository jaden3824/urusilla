"""Offline episode state machine with strict stops, repair, fallback, and resume."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical import canonical_bytes, sha256_bytes
from .checkpoint import CheckpointStore
from .config import A0_COLD_TOKENS, MODEL_SPECS
from .errors import EvaluationError, IntegrityError, LedgerError, ParseFailure
from .gates import BudgetAuthorization, BudgetGuard
from .ledger import (
    CallLedger,
    EpisodeLedger,
    TimingLedger,
    TokenLedger,
    WireLedger,
    call_ledger_from_object,
    empty_categories,
)
from .manifests import EpisodeManifest, FrozenInputs, RunManifest, _common_prompt, _split_for_item
from .mocks import ScriptedMockAdapter, mock_count, scenario_key
from .protocol import CallRequest, CallResponse
from .records import OpaqueAnswer, QARecord, parse_cte, render_cte
from .representations import (
    SelectionContext,
    SurfaceArtifact,
    TokenCounter,
    encode_direct,
    encode_for_arm,
    parse_arm_output,
)
from .scoring import score_answer


@dataclass(frozen=True)
class EpisodeResult:
    value: Mapping[str, Any]

    @property
    def episode_id(self) -> str:
        return str(self.value["episode_id"])


def _counter(model_code: str) -> TokenCounter:
    key = MODEL_SPECS[model_code]["tokenizer"]
    if key == "max_four_planning_proxy":
        cold_key = "mistral_7b_instruct_v03"
    else:
        cold_key = key
    # Exactness is with respect to this mock adapter only. The episode manifest
    # separately keeps hosted O/G claim eligibility false.
    return TokenCounter(
        key=cold_key,
        fingerprint="deterministic-utf8-quarter-mock-v1",
        exact_for_endpoint=True,
        count_fn=mock_count,
    )


def _artifact_object(artifact: SurfaceArtifact) -> dict[str, Any]:
    return {
        "assigned_arm": artifact.assigned_arm,
        "selected_representation": artifact.selected_representation,
        "normative_record_sha256": artifact.normative_record_sha256,
        "sender_output_text": artifact.sender_output_text,
        "surface_text": artifact.surface_text,
        "receiver_text": artifact.receiver_text,
        "payload_bytes": artifact.payload_bytes,
        "full_envelope_bytes": artifact.full_envelope_bytes,
        "cold_tokens": artifact.cold_tokens,
        "cold_bytes": artifact.cold_bytes,
        "tokenizer_exact": artifact.tokenizer_exact,
        "receiver_boundary": artifact.receiver_boundary,
        "fallback_used": artifact.fallback_used,
        "fallback_reason": artifact.fallback_reason,
    }


def _partition_runtime_input(
    *, prompt: str, task_slice: str, history_text: str, total_input: int
) -> dict[str, int]:
    """Partition the exact mock input count without overlap or rounding loss."""

    prompt_tokens = mock_count(prompt)
    task_tokens = mock_count(task_slice)
    result = {
        "task_input": task_tokens,
        # Runtime output-contract instructions are part of the system/role
        # slice. format_induction is reserved for calls that invent, train, or
        # select a representation and remains zero in this deterministic lane.
        "system_role": prompt_tokens - task_tokens,
        # The adapter joins provider-neutral messages with one newline. Keep
        # that boundary cost with history so all input tokens reconcile.
        "agent_input_history": total_input - prompt_tokens,
    }
    if any(value < 0 for value in result.values()) or sum(result.values()) != total_input:
        raise LedgerError("mock runtime input categories do not reconcile exactly")
    if not history_text and result["agent_input_history"] != 0:
        raise LedgerError("empty history unexpectedly carried input tokens")
    return result


class OfflineRunner:
    def __init__(
        self,
        *,
        inputs: FrozenInputs,
        run_manifest: RunManifest,
        episodes: Sequence[EpisodeManifest],
        output_dir: Path,
        adapter: ScriptedMockAdapter | None = None,
    ):
        if run_manifest.value["execution_mode"] != "offline_mock":
            raise EvaluationError("only offline_mock execution is implemented")
        self.inputs = inputs
        self.run_manifest = run_manifest
        self.episodes = tuple(episodes)
        self.items = {
            item.key: item
            for dataset in inputs.datasets.values()
            for item in dataset
        }
        gold = {
            episode.episode_id: self.items[episode.value["item_key"]].answer
            for episode in episodes
        }
        self.adapter = adapter or ScriptedMockAdapter(gold)
        if not getattr(self.adapter, "is_mock", False):
            raise EvaluationError("non-mock adapters are not available in this harness")
        self.budget = BudgetGuard(BudgetAuthorization.offline_mock())
        self.store = CheckpointStore(output_dir, run_manifest, episodes)

    def run_all(self, *, max_new_turns: int | None = None) -> tuple[EpisodeResult, ...]:
        results: list[EpisodeResult] = []
        remaining = max_new_turns
        for episode in self.episodes:
            result, used = self.run_episode(episode, max_new_turns=remaining)
            if result is not None:
                results.append(result)
            if remaining is not None:
                remaining -= used
                if remaining <= 0:
                    break
        return tuple(results)

    def run_episode(
        self, episode: EpisodeManifest, *, max_new_turns: int | None = None
    ) -> tuple[EpisodeResult | None, int]:
        events = self.store.load(episode.episode_id)
        if events and events[-1].event_type == "episode_terminal":
            return EpisodeResult(events[-1].payload["result"]), 0

        turn_events = [event for event in events if event.event_type == "turn_completed"]
        if turn_events:
            state = dict(turn_events[-1].payload["state_after"])
        else:
            state = self._initial_state()
        new_turns = 0

        while not state["should_terminate"] and state["next_turn"] < 8:
            if max_new_turns is not None and new_turns >= max_new_turns:
                return None, new_turns
            turn_payload = self._run_turn(episode, state)
            self.store.append(episode.episode_id, "turn_completed", turn_payload)
            state = dict(turn_payload["state_after"])
            new_turns += 1

        if max_new_turns is not None and new_turns >= max_new_turns and not state["should_terminate"]:
            return None, new_turns
        result = self._terminal_result(episode, state)
        self.store.append(episode.episode_id, "episode_terminal", {"result": result.value})
        return result, new_turns

    @staticmethod
    def _initial_state() -> dict[str, Any]:
        return {
            "next_turn": 0,
            "history": [],
            "candidates": {"A": None, "B": None},
            "unresolved": {"A": True, "B": True},
            "typed": {"A": False, "B": False},
            "call_ledgers": [],
            "repair_calls": 0,
            "fallback_calls": 0,
            "malformed_attempts": 0,
            "timeout_attempts": 0,
            "refusal_attempts": 0,
            "cached_endpoints": [],
            "should_terminate": False,
            "terminal_reason": None,
            "last_answer": None,
        }

    def _run_turn(
        self, episode: EpisodeManifest, previous_state: Mapping[str, Any]
    ) -> dict[str, Any]:
        state = {
            key: (dict(value) if isinstance(value, dict) else list(value) if isinstance(value, list) else value)
            for key, value in previous_state.items()
        }
        turn = state["next_turn"]
        agent = "A" if turn % 2 == 0 else "B"
        peer = "B" if agent == "A" else "A"
        model_code = episode.value["role_models"][agent]
        receiver_model_code = episode.value["role_models"][peer]
        arm = episode.value["arm"]
        item = self.items[episode.value["item_key"]]
        split_data = episode.value["split"]
        split = _split_for_item(item, split_data["seed"], split_data["mode"])
        prompt, task_slice, role_slice = _common_prompt(item, split, agent, arm)
        history_text = "\n".join(
            f"Agent {entry['agent']}: {entry['receiver_text']}" for entry in state["history"]
        )
        messages = [{"role": "system", "content": prompt}]
        if history_text:
            messages.append({"role": "user", "content": history_text})
        pair = tuple(episode.value["ordered_pair"])
        scenario = scenario_key(
            episode.value["dataset"], item.key, pair, episode.value["repeat_index"]
        )
        request = CallRequest.build(
            episode_id=episode.episode_id,
            turn_index=turn,
            attempt_index=0,
            purpose="runtime",
            agent=agent,
            model_code=model_code,
            logical_model_id=MODEL_SPECS[model_code]["logical_model_id"],
            arm=arm,
            messages=messages,
            mock_scenario_key=scenario,
        )
        self.budget.before_call(is_mock=True, is_paid=False)
        response = self.adapter.generate(request)
        call_ledgers: list[CallLedger] = []
        runtime_input = _partition_runtime_input(
            prompt=prompt,
            task_slice=task_slice,
            history_text=history_text,
            total_input=response.value["usage"]["input_tokens"],
        )

        if response.status in {"timeout", "refused"}:
            if response.status == "timeout":
                state["timeout_attempts"] += 1
            else:
                state["refusal_attempts"] += 1
            categories = empty_categories(**runtime_input)
            call_ledgers.append(
                self._call_ledger(
                    request,
                    response,
                    categories,
                    agent=agent,
                    model_code=model_code,
                    malformed=False,
                    artifact=None,
                )
            )
            state["should_terminate"] = True
            state["terminal_reason"] = response.status
            state["next_turn"] += 1
            state["call_ledgers"].extend(call.to_object() for call in call_ledgers)
            return {
                "requests": [request.value],
                "responses": [response.value],
                "state_after": state,
            }

        parsed: QARecord | OpaqueAnswer | None = None
        repair_request: CallRequest | None = None
        repair_response: CallResponse | None = None
        malformed = False
        try:
            parsed = parse_arm_output(arm, response.output_text)
        except ParseFailure:
            malformed = True
            state["malformed_attempts"] += 1
            if state["repair_calls"] < 1:
                repair_request = CallRequest.build(
                    episode_id=episode.episode_id,
                    turn_index=turn,
                    attempt_index=1,
                    purpose="format_repair",
                    agent=agent,
                    model_code=model_code,
                    logical_model_id=MODEL_SPECS[model_code]["logical_model_id"],
                    arm=arm,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Repair only the output format under the already supplied "
                                "contract. Add no task evidence and no new factual content."
                            ),
                        },
                        {"role": "assistant", "content": response.output_text},
                    ],
                    mock_scenario_key=scenario,
                )
                self.budget.before_call(is_mock=True, is_paid=False)
                repair_response = self.adapter.generate(repair_request)
                state["repair_calls"] += 1
                try:
                    parsed = parse_arm_output(arm, repair_response.output_text)
                except ParseFailure:
                    parsed = None

        artifact: SurfaceArtifact | None = None
        fallback_used = False
        failed_surface_bytes = 0
        if parsed is not None:
            if isinstance(parsed, OpaqueAnswer):
                text = parsed.raw_text
                artifact = SurfaceArtifact(
                    assigned_arm=arm,
                    selected_representation=arm,
                    normative_record_sha256=sha256_bytes(text.encode("utf-8")),
                    sender_output_text=text,
                    surface_text=text,
                    receiver_text=text,
                    payload_bytes=len(text.encode("utf-8")),
                    full_envelope_bytes=len(text.encode("utf-8")),
                    cold_tokens=0,
                    cold_bytes=0,
                    tokenizer_exact=True,
                    receiver_boundary="surface_prompt",
                )
                state["candidates"][agent] = None if parsed.answer == "?" else parsed.answer
                state["unresolved"][agent] = True
                state["typed"][agent] = False
            else:
                cached = receiver_model_code in state["cached_endpoints"]
                context = SelectionContext(
                    episode_id=episode.episode_id,
                    turn_index=turn,
                    sender=agent,
                    receiver=peer,
                    counter=_counter(receiver_model_code),
                    artifacts_cached=cached,
                    receiver_boundary="surface_prompt",
                    persistent_verified_context=True,
                )
                try:
                    artifact = encode_for_arm(arm, parsed, context)
                    if "surface_integrity" in response.value["faults"]:
                        failed_surface_bytes = artifact.full_envelope_bytes
                        raise IntegrityError("deterministic surface-integrity fault")
                except (EvaluationError, ValueError) as exc:
                    if arm not in {"current_adaptive_surface", "oracle_free_adaptive_selector"}:
                        raise
                    failed = artifact
                    fallback = encode_direct("compact_terse_english", parsed, context)
                    artifact = SurfaceArtifact(
                        assigned_arm=arm,
                        selected_representation="compact_terse_english",
                        normative_record_sha256=parsed.sha256,
                        sender_output_text=parsed.canonical_text,
                        surface_text=fallback.surface_text,
                        receiver_text=fallback.receiver_text,
                        payload_bytes=fallback.payload_bytes,
                        full_envelope_bytes=fallback.full_envelope_bytes,
                        cold_tokens=failed.cold_tokens if failed is not None else (
                            0 if cached else A0_COLD_TOKENS.get(context.counter.key, max(A0_COLD_TOKENS.values()))
                        ),
                        cold_bytes=failed.cold_bytes if failed is not None else 0,
                        tokenizer_exact=context.counter.exact_for_endpoint,
                        receiver_boundary="surface_prompt",
                        fallback_used=True,
                        fallback_reason=type(exc).__name__,
                    )
                    fallback_used = True
                    state["fallback_calls"] += 1
                if artifact.selected_representation.startswith("current_surface") and not cached:
                    state["cached_endpoints"].append(receiver_model_code)
                state["candidates"][agent] = parsed.answer_candidate
                state["unresolved"][agent] = parsed.has_unresolved_request
                state["typed"][agent] = True
            state["last_answer"] = state["candidates"][agent]
            state["history"].append(
                {"agent": agent, "receiver_text": artifact.receiver_text}
            )

        both_candidates = (
            state["candidates"]["A"] is not None
            and state["candidates"]["A"] == state["candidates"]["B"]
        )
        modern_typed = state["typed"]["A"] and state["typed"]["B"]
        if modern_typed and both_candidates and not any(state["unresolved"].values()):
            state["should_terminate"] = True
            state["terminal_reason"] = "common_early_stop"
        if parsed is None:
            state["should_terminate"] = True
            state["terminal_reason"] = "repair_exhausted"

        # The failed runtime output remains charged. A dedicated repair call is
        # wholly classified as repair_retry and never duplicates runtime slices.
        base_output = response.value["usage"]["output_tokens"]
        terminal_output = bool(state["should_terminate"] or turn == 7)
        base_categories = empty_categories(
            **runtime_input,
            repair_retry=base_output if malformed else 0,
            final_answer=(
                0
                if malformed else base_output if terminal_output and parsed is not None else 0
            ),
            agent_output_visible=(
                0
                if malformed or (terminal_output and parsed is not None)
                else base_output
            ),
            negotiation_profile=artifact.cold_tokens if artifact is not None else 0,
        )
        call_ledgers.append(
            self._call_ledger(
                request,
                response,
                base_categories,
                agent=agent,
                model_code=model_code,
                malformed=malformed,
                artifact=artifact,
                fallback=fallback_used,
                retransmitted_bytes=failed_surface_bytes,
            )
        )
        if repair_request is not None and repair_response is not None:
            repair_tokens = (
                repair_response.value["usage"]["input_tokens"]
                + repair_response.value["usage"]["output_tokens"]
            )
            call_ledgers.append(
                self._call_ledger(
                    repair_request,
                    repair_response,
                    empty_categories(repair_retry=repair_tokens),
                    agent=agent,
                    model_code=model_code,
                    malformed=False,
                    artifact=None,
                    repair=True,
                )
            )

        state["next_turn"] += 1
        state["call_ledgers"].extend(call.to_object() for call in call_ledgers)
        return {
            "requests": [
                request.value,
                *([repair_request.value] if repair_request is not None else []),
            ],
            "responses": [
                response.value,
                *([repair_response.value] if repair_response is not None else []),
            ],
            "artifact": None if artifact is None else _artifact_object(artifact),
            "state_after": state,
        }

    @staticmethod
    def _call_ledger(
        request: CallRequest,
        response: CallResponse,
        categories: Mapping[str, int],
        *,
        agent: str,
        model_code: str,
        malformed: bool,
        artifact: SurfaceArtifact | None,
        fallback: bool = False,
        repair: bool = False,
        retransmitted_bytes: int = 0,
    ) -> CallLedger:
        expected_tokens = (
            response.value["usage"]["input_tokens"]
            + response.value["usage"]["output_tokens"]
            + (0 if artifact is None else artifact.cold_tokens)
        )
        if sum(categories.values()) != expected_tokens:
            raise LedgerError(
                "mock call token categories do not reconcile to logical usage plus cold artifacts"
            )
        wire = WireLedger(
            payload_utf8_bytes=0 if artifact is None else artifact.payload_bytes,
            full_envelope_bytes=0 if artifact is None else artifact.full_envelope_bytes,
            cold_profile_bytes=0 if artifact is None else artifact.cold_bytes,
            retransmitted_bytes=retransmitted_bytes,
            integrity_bytes=0,
        )
        model_ns = response.value["timing"]["model_ns"]
        logical_encode = 0 if artifact is None else 10_000 + artifact.payload_bytes
        logical_decode = 0 if artifact is None else 20_000 + artifact.payload_bytes
        timing = TimingLedger(
            encode_ns=logical_encode,
            decode_ns=logical_decode,
            model_ns=model_ns,
            repair_ns=model_ns if repair else 0,
            end_to_end_ns=model_ns + logical_encode + logical_decode,
        )
        annotations = {
            "provider_input_tokens": None,
            "provider_output_tokens": None,
            "provider_total_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "reasoning_tokens_subset": None,
            "accepted_prediction_tokens": None,
            "rejected_prediction_tokens": None,
            "unclassified_usage_json": None,
            "provider_usage_status": "mock_not_provider_reported",
        }
        return CallLedger(
            call_id=request.call_id,
            call_kind="mock_repair" if repair else "mock_runtime",
            agent=agent,
            model_code=model_code,
            tokens=TokenLedger(categories, judge=0, provider_annotations=annotations),
            wire=wire,
            timing=timing,
            actual_billed_usd=Decimal("0"),
            estimated_usd=Decimal("0"),
            was_repair=repair,
            was_fallback=fallback,
            malformed_attempt=malformed,
        )

    def _terminal_result(
        self, episode: EpisodeManifest, state: Mapping[str, Any]
    ) -> EpisodeResult:
        calls = tuple(call_ledger_from_object(value) for value in state["call_ledgers"])
        ledger = EpisodeLedger(
            episode_id=episode.episode_id,
            calls=calls,
            base_calls=state["next_turn"],
            repair_calls=state["repair_calls"],
            fallback_calls=state["fallback_calls"],
            malformed_attempts=state["malformed_attempts"],
            timeout_attempts=state["timeout_attempts"],
            refusal_attempts=state["refusal_attempts"],
        )
        item = self.items[episode.value["item_key"]]
        prediction = state["last_answer"]
        scores = score_answer(prediction, item.answer)
        consensus = (
            state["candidates"]["A"] is not None
            and state["candidates"]["A"] == state["candidates"]["B"]
        )
        provenance_retained = state["typed"]["A"] and state["typed"]["B"]
        terminal_failure = state["terminal_reason"] in {
            "timeout",
            "refused",
            "repair_exhausted",
        }
        safe_success = bool(
            scores["normalized_exact_match"] == 1.0
            and consensus
            and provenance_retained
            and not terminal_failure
        )
        value: dict[str, Any] = {
            "format": "competitive-eval-episode-result-v1",
            "episode_id": episode.episode_id,
            "dataset": episode.value["dataset"],
            "item_id": episode.value["item_key"],
            "evidence_mode": episode.value["split"]["mode"],
            "repeat_seed": episode.value["repeat_seed"],
            "repeat_id": episode.value["repeat_index"],
            "sender_family": episode.value["ordered_pair"][0],
            "receiver_family": episode.value["ordered_pair"][1],
            "arm": episode.value["arm"],
            "terminal_reason": state["terminal_reason"] or "eight_call_cap",
            "answer_candidate": prediction,
            "gold_answer_used_only_by_mock_and_scorer": True,
            "metrics": scores,
            "consensus": consensus,
            "provenance_retained": provenance_retained,
            "safe_task_success": safe_success,
            "malformed_in_denominator": state["malformed_attempts"] > 0,
            "repaired_in_denominator": state["repair_calls"] > 0,
            "fallback_in_denominator": state["fallback_calls"] > 0,
            "timeout_in_denominator": state["timeout_attempts"] > 0,
            "refusal_in_denominator": state["refusal_attempts"] > 0,
            "ledger": ledger.to_object(),
            "claim_eligible": False,
        }
        value["result_sha256"] = sha256_bytes(canonical_bytes(value))
        return EpisodeResult(value)


def results_to_analysis_rows(results: Sequence[EpisodeResult]) -> tuple[Any, ...]:
    from .statistical import AnalysisRow

    rows = []
    for result in results:
        value = result.value
        rows.append(
            AnalysisRow(
                task_family=value["dataset"],
                item_id=value["item_id"],
                evidence_mode=value["evidence_mode"],
                repeat_seed=value["repeat_seed"],
                sender_family=value["sender_family"],
                receiver_family=value["receiver_family"],
                repeat_id=value["repeat_id"],
                arm=value["arm"],
                safe_task_success=value["safe_task_success"],
                t_total=value["ledger"]["t_total"],
            )
        )
    return tuple(rows)
