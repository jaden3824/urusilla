"""All prompt arms, strict bridge mapping, and oracle-free selection."""

from __future__ import annotations

from dataclasses import dataclass
import functools
import base64
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Callable, Mapping
import uuid

from .canonical import canonical_json, sha256_bytes
from .config import (
    A0_COLD_ARTIFACT_BYTES,
    A0_COLD_ARTIFACT_LOCKS,
    A0_COLD_TOKENS,
    CURRENT_PROFILE_SHA256,
    PRIMARY_BASELINE,
    PROJECT_ROOT,
    REPRESENTATION_ARMS,
)
from .errors import IntegrityError, ParseFailure
from .records import (
    OpaqueAnswer,
    QARecord,
    parse_answer_tag,
    parse_canonical_record,
    parse_cte,
    record_from_object,
    render_cte,
)


CTE_CONTRACT = (
    "Send only task-relevant facts. Preserve source ownership. Use these lines in "
    "this order: ACT: ask|propose|agree|reject; CLAIM: <short claim or ?>; "
    "EVIDENCE: <[A|B] atomic facts or NONE>; NEED: <missing fact or NONE>; "
    "ANSWER: <exact answer or ?>. No greeting, repetition, unsupported claim, or "
    "private reasoning."
)
JSON_CONTRACT = (
    "Return exactly one JSON object with keys in this order and no whitespace: "
    "{\"a\":\"<exact answer or ?>\",\"c\":[\"<short claim>\"],\"e\":[{\"f\":"
    "\"<atomic fact>\",\"s\":\"A|B\"}],\"n\":[\"<missing fact>\"],\"x\":"
    "\"ask|propose|agree|reject\"}. Use empty arrays when absent. Do not add keys "
    "or prose."
)
ADAPTIVE_CONTRACT = (
    "Return exactly one minified bridge record with keys in this order and no "
    "whitespace: {\"a\":\"<exact answer or ?>\",\"c\":[\"<short claim>\"],\"e\":["
    "{\"f\":\"<atomic fact>\",\"s\":\"A|B\"}],\"n\":[\"<missing fact>\"],"
    "\"x\":\"ask|propose|agree|reject\"}. The verified bridge maps this record to "
    "the negotiated receiver-specific adaptive surface. It rejects unknown fields, "
    "invalid types, integrity errors, and unknown profile state. Use empty arrays "
    "when absent. Do not add prose or private reasoning. Frozen profile SHA-256: "
    + CURRENT_PROFILE_SHA256
    + "."
)
SELECTOR_CONTRACT = (
    JSON_CONTRACT
    + " The deterministic pre-receiver selector may transmit this typed record as "
    "CTE, canonical JSON, or the verified current surface using only eligibility, "
    "cache state, and the receiver's already-pinned token counter."
)
PAPER_MOCK_CONTRACT = (
    "MOCK-ONLY CLEAN ADAPTATION: communicate relevant evidence and end with exactly "
    "one line `ANSWER: <exact answer or ?>`. Exact upstream YAML bytes are required "
    "before a claim-ready run."
)
AUTOFORM_MOCK_CONTRACT = (
    "MOCK-ONLY CLEAN ADAPTATION: choose any concise non-natural representation and "
    "end with exactly one line `ANSWER: <exact answer or ?>`. Exact upstream YAML "
    "bytes are required before a claim-ready run."
)

ARM_CONTRACTS = {
    "paper_natural_language": PAPER_MOCK_CONTRACT,
    "compact_terse_english": CTE_CONTRACT,
    "canonical_minified_json": JSON_CONTRACT,
    "autoform": AUTOFORM_MOCK_CONTRACT,
    "current_adaptive_surface": ADAPTIVE_CONTRACT,
    "oracle_free_adaptive_selector": SELECTOR_CONTRACT,
}


@dataclass(frozen=True)
class TokenCounter:
    key: str
    fingerprint: str
    exact_for_endpoint: bool
    count_fn: Callable[[str], int]
    boundary: str = "receiver_text"

    def count(self, text: str) -> int:
        value = self.count_fn(text)
        if type(value) is not int or value < 0:
            raise IntegrityError("token counter returned an invalid count")
        return value


@dataclass(frozen=True)
class SurfaceArtifact:
    assigned_arm: str
    selected_representation: str
    normative_record_sha256: str
    sender_output_text: str
    surface_text: str
    receiver_text: str
    payload_bytes: int
    full_envelope_bytes: int
    cold_tokens: int
    cold_bytes: int
    tokenizer_exact: bool
    receiver_boundary: str
    fallback_used: bool = False
    fallback_reason: str | None = None


@dataclass(frozen=True)
class SelectionContext:
    episode_id: str
    turn_index: int
    sender: str
    receiver: str
    counter: TokenCounter
    artifacts_cached: bool
    receiver_boundary: str = "surface_prompt"
    persistent_verified_context: bool = True


def prompt_contract_digest(arm: str) -> str:
    if arm not in ARM_CONTRACTS:
        raise ParseFailure("unknown_profile", f"unknown arm: {arm}")
    return sha256_bytes(ARM_CONTRACTS[arm].encode("utf-8"))


def parse_arm_output(arm: str, text: str) -> QARecord | OpaqueAnswer:
    if arm == "compact_terse_english":
        return parse_cte(text)
    if arm in {
        "canonical_minified_json",
        "current_adaptive_surface",
        "oracle_free_adaptive_selector",
    }:
        return parse_canonical_record(text)
    if arm in {"paper_natural_language", "autoform"}:
        return parse_answer_tag(text)
    raise ParseFailure("unknown_profile", f"unknown arm: {arm}")


def render_arm_record(arm: str, record: QARecord) -> str:
    if arm == "compact_terse_english":
        return render_cte(record)
    if arm in {
        "canonical_minified_json",
        "current_adaptive_surface",
        "oracle_free_adaptive_selector",
    }:
        return record.canonical_text
    if arm in {"paper_natural_language", "autoform"}:
        return f"MOCK REPRESENTATION {record.sha256[:16]}\nANSWER: {record.answer}"
    raise ParseFailure("unknown_profile", f"unknown arm: {arm}")


def _uuid_from_material(domain: str, *values: str) -> str:
    digest = hashlib.sha256((domain + "\x00" + "\x00".join(values)).encode()).digest()
    return str(uuid.UUID(bytes=digest[:16]))


def wrap_record(record: QARecord, context: SelectionContext) -> dict[str, Any]:
    """Map a QA record to a quarantined, non-effectful canonical Urusilla message."""

    return {
        "id": _uuid_from_material("competitive-eval-message-v1", context.episode_id, str(context.turn_index)),
        "session": _uuid_from_material("competitive-eval-session-v1", context.episode_id),
        "sender": f"urn:competitive-eval:agent:{context.sender}",
        "recipients": [f"urn:competitive-eval:agent:{context.receiver}"],
        "act": "ASSERT",
        "reply_to": None,
        "schema": "urn:competitive-eval:qa:1",
        "logical_clock": context.turn_index + 1,
        "expires_ms": 0,
        "confidence_ppm": None,
        "expected": [],
        "body": {"kind": "x:competitive-eval-qa-v1", **record.to_object()},
        # Keep one inert, quarantined metadata value.  Proto3 does not preserve
        # presence for an entirely empty nested SemanticValue map, while the
        # strict baseline decoder correctly requires both body and meta.
        "meta": {"x:competitive-eval-bridge": "qa-v1"},
    }


def unwrap_record(message: Mapping[str, Any]) -> QARecord:
    if type(message) is not dict:
        raise ParseFailure("semantic_invalid", "decoded bridge message is not an object")
    expected_fields = {
        "id",
        "session",
        "sender",
        "recipients",
        "act",
        "reply_to",
        "schema",
        "logical_clock",
        "expires_ms",
        "confidence_ppm",
        "expected",
        "body",
        "meta",
    }
    if set(message) != expected_fields:
        raise ParseFailure("semantic_invalid", "decoded bridge top-level fields changed")
    for name in ("id", "session"):
        try:
            parsed_uuid = uuid.UUID(message[name])
        except (TypeError, ValueError, AttributeError) as exc:
            raise ParseFailure("semantic_invalid", f"decoded bridge {name} is not a UUID") from exc
        if str(parsed_uuid) != message[name]:
            raise ParseFailure("noncanonical", f"decoded bridge {name} is not canonical")
    agents = {"urn:competitive-eval:agent:A", "urn:competitive-eval:agent:B"}
    if message["sender"] not in agents:
        raise ParseFailure("semantic_invalid", "decoded bridge sender changed")
    recipients = message["recipients"]
    if (
        type(recipients) is not list
        or len(recipients) != 1
        or recipients[0] not in agents
        or recipients[0] == message["sender"]
    ):
        raise ParseFailure("semantic_invalid", "decoded bridge recipient changed")
    if (
        message["act"] != "ASSERT"
        or message["reply_to"] is not None
        or message["schema"] != "urn:competitive-eval:qa:1"
        or type(message["logical_clock"]) is not int
        or not 1 <= message["logical_clock"] <= 8
        or message["expires_ms"] != 0
        or message["confidence_ppm"] is not None
        or message["expected"] != []
        or message["meta"] != {"x:competitive-eval-bridge": "qa-v1"}
    ):
        raise ParseFailure("semantic_invalid", "decoded bridge control fields changed")
    body = message.get("body")
    if type(body) is not dict or body.get("kind") != "x:competitive-eval-qa-v1":
        raise ParseFailure("semantic_invalid", "decoded bridge has the wrong body kind")
    if set(body) != {"kind", "a", "c", "e", "n", "x"}:
        raise ParseFailure("semantic_invalid", "decoded bridge body fields changed")
    ordered = {key: body[key] for key in ("a", "c", "e", "n", "x")}
    return record_from_object(ordered)


@functools.lru_cache(maxsize=1)
def _current_runtime() -> tuple[Any, Any]:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import urusilla_generalization_surface_v06 as current

    profile = current.derive_alias_profile(current.build_datasets()["development"])
    observed = current.profile_sha256(profile)
    if observed != CURRENT_PROFILE_SHA256:
        raise IntegrityError(
            f"adaptive profile changed: expected {CURRENT_PROFILE_SHA256}, got {observed}"
        )
    return current, profile


@functools.lru_cache(maxsize=1)
def verify_cold_artifact_locks() -> dict[str, dict[str, Any]]:
    """Rebuild and verify every logical cold artifact from frozen root code."""

    current, profile = _current_runtime()
    import urusilla_adaptive_surface_v05 as adaptive

    values = {
        "symbolic_grammar": current.existing_grammar_capsule(),
        "optimized_grammar": current.optimized_grammar_capsule(),
        "optimized_profile": current.profile_capsule(profile),
        "structured_profile_base64": base64.b64encode(
            adaptive.encode_profile_capsule(adaptive.DEFAULT_PROFILE)
        ).decode("ascii"),
        "structured_codebook": adaptive.encode_codebook_capsule_text(
            adaptive.holdout_codebook()
        ),
    }
    values["structured_bundle"] = (
        values["structured_profile_base64"] + values["structured_codebook"]
    )
    observed: dict[str, dict[str, Any]] = {}
    for name, expected in A0_COLD_ARTIFACT_LOCKS.items():
        raw = values[name].encode("utf-8")
        fact = {"utf8_bytes": len(raw), "sha256": sha256_bytes(raw)}
        if fact != expected:
            raise IntegrityError(
                f"cold artifact {name} changed: expected {expected}, got {fact}"
            )
        observed[name] = fact
    logical_total = sum(
        observed[name]["utf8_bytes"]
        for name in ("symbolic_grammar", "optimized_grammar", "optimized_profile", "structured_bundle")
    )
    if logical_total != A0_COLD_ARTIFACT_BYTES:
        raise IntegrityError("conservative cold artifact total changed")
    return observed


def encode_current_surface(record: QARecord, context: SelectionContext) -> SurfaceArtifact:
    current, profile = _current_runtime()
    message = wrap_record(record, context)
    tokenizer = SimpleNamespace(count=context.counter.count)
    selection = current.select_message(message, profile, tokenizer)
    decoded = current.decode_selected(selection.candidate.text, profile)
    if decoded != current.normalize_message(message):
        raise IntegrityError("current surface changed the complete bridge message")
    recovered = unwrap_record(decoded)
    if recovered != record:
        raise IntegrityError("current surface did not recover the exact QA record")
    surface = selection.candidate.text
    receiver_text = surface if context.receiver_boundary == "surface_prompt" else record.canonical_text
    if context.receiver_boundary not in {"surface_prompt", "decoded_json_bridge"}:
        raise ParseFailure("unknown_profile", "unknown receiver boundary")
    cold_tokens = 0
    cold_bytes = 0
    if not context.artifacts_cached:
        cold_tokens = A0_COLD_TOKENS.get(context.counter.key, max(A0_COLD_TOKENS.values()))
        cold_bytes = A0_COLD_ARTIFACT_BYTES
        if context.receiver_boundary == "surface_prompt" and not context.persistent_verified_context:
            # The caller must apply this charge on every stateless request.
            cold_tokens = A0_COLD_TOKENS.get(context.counter.key, max(A0_COLD_TOKENS.values()))
    return SurfaceArtifact(
        assigned_arm="current_adaptive_surface",
        selected_representation=f"current_surface:{selection.candidate.mode}",
        normative_record_sha256=record.sha256,
        sender_output_text=record.canonical_text,
        surface_text=surface,
        receiver_text=receiver_text,
        payload_bytes=len(surface.encode("utf-8")),
        full_envelope_bytes=len(surface.encode("utf-8")),
        cold_tokens=cold_tokens,
        cold_bytes=cold_bytes,
        tokenizer_exact=context.counter.exact_for_endpoint,
        receiver_boundary=context.receiver_boundary,
    )


def encode_direct(arm: str, record: QARecord, context: SelectionContext) -> SurfaceArtifact:
    if arm == "current_adaptive_surface":
        return encode_current_surface(record, context)
    text = render_arm_record(arm, record)
    recovered = parse_arm_output(arm, text)
    if isinstance(recovered, QARecord) and recovered != record:
        raise IntegrityError(f"{arm} did not recover the exact QA record")
    return SurfaceArtifact(
        assigned_arm=arm,
        selected_representation=arm,
        normative_record_sha256=record.sha256,
        sender_output_text=text,
        surface_text=text,
        receiver_text=text,
        payload_bytes=len(text.encode("utf-8")),
        full_envelope_bytes=len(text.encode("utf-8")),
        cold_tokens=0,
        cold_bytes=0,
        tokenizer_exact=context.counter.exact_for_endpoint,
        receiver_boundary="surface_prompt",
    )


def oracle_free_select(record: QARecord, context: SelectionContext) -> SurfaceArtifact:
    """Choose from CTE, JSON, and current surface without outcome information."""

    cte = encode_direct("compact_terse_english", record, context)
    structured = encode_direct("canonical_minified_json", record, context)
    candidates = [cte, structured]
    # Current v0.6 selection requires the receiver's exact tokenizer. Planning
    # proxies for hosted O/G endpoints cannot make it eligible.
    if context.counter.exact_for_endpoint:
        candidates.append(encode_current_surface(record, context))

    rank = {
        "compact_terse_english": 0,
        "canonical_minified_json": 1,
    }

    def cost(artifact: SurfaceArtifact) -> tuple[int, int, str]:
        tokens = context.counter.count(artifact.receiver_text) + artifact.cold_tokens
        preference = rank.get(artifact.selected_representation, 2)
        return tokens, preference, artifact.surface_text

    selected = min(candidates, key=cost)
    return SurfaceArtifact(
        assigned_arm="oracle_free_adaptive_selector",
        selected_representation=selected.selected_representation,
        normative_record_sha256=selected.normative_record_sha256,
        sender_output_text=record.canonical_text,
        surface_text=selected.surface_text,
        receiver_text=selected.receiver_text,
        payload_bytes=selected.payload_bytes,
        full_envelope_bytes=selected.full_envelope_bytes,
        cold_tokens=selected.cold_tokens,
        cold_bytes=selected.cold_bytes,
        tokenizer_exact=selected.tokenizer_exact,
        receiver_boundary=selected.receiver_boundary,
    )


def encode_for_arm(arm: str, record: QARecord, context: SelectionContext) -> SurfaceArtifact:
    if arm not in REPRESENTATION_ARMS:
        raise ParseFailure("unknown_profile", f"unknown arm: {arm}")
    if arm == "oracle_free_adaptive_selector":
        return oracle_free_select(record, context)
    return encode_direct(arm, record, context)
