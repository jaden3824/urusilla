"""Normative typed QA record used by the modern representation arms."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .canonical import canonical_json, sha256_bytes, strict_json_loads
from .errors import ManifestError, ParseFailure


QA_KEYS = ("a", "c", "e", "n", "x")
EVIDENCE_KEYS = ("f", "s")
ACTS = frozenset({"ask", "propose", "agree", "reject"})
OWNERS = frozenset({"A", "B"})
MAX_OUTPUT_BYTES = 64 * 1024
MAX_STRING_BYTES = 16 * 1024
MAX_LIST_ITEMS = 256
RESERVED_CTE_DELIMITER = " || "
_UNSAFE_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


def _text(value: Any, label: str, *, allow_question: bool = True) -> str:
    if type(value) is not str or not value:
        raise ParseFailure("semantic_invalid", f"{label} must be non-empty text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ParseFailure("semantic_invalid", f"{label} is not UTF-8") from exc
    if size > MAX_STRING_BYTES:
        raise ParseFailure("resource_limit", f"{label} exceeds {MAX_STRING_BYTES} bytes")
    if _UNSAFE_TEXT.search(value) is not None or "\n" in value or "\r" in value:
        raise ParseFailure("semantic_invalid", f"{label} contains unsafe controls")
    if not allow_question and value == "?":
        raise ParseFailure("semantic_invalid", f"{label} cannot be ?")
    return value


def _text_list(value: Any, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise ParseFailure("semantic_invalid", f"{label} must be a list")
    if len(value) > MAX_LIST_ITEMS:
        raise ParseFailure("resource_limit", f"{label} has too many entries")
    return tuple(_text(item, f"{label}[{index}]", allow_question=False) for index, item in enumerate(value))


@dataclass(frozen=True)
class Evidence:
    fact: str
    source: str

    def __post_init__(self) -> None:
        _text(self.fact, "evidence.fact", allow_question=False)
        if self.source not in OWNERS:
            raise ParseFailure("semantic_invalid", f"unknown evidence source: {self.source}")

    def to_object(self) -> dict[str, str]:
        return {"f": self.fact, "s": self.source}


@dataclass(frozen=True)
class QARecord:
    answer: str
    claims: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    needs: tuple[str, ...]
    act: str

    def __post_init__(self) -> None:
        _text(self.answer, "answer")
        if len(self.claims) > MAX_LIST_ITEMS or len(self.evidence) > MAX_LIST_ITEMS or len(self.needs) > MAX_LIST_ITEMS:
            raise ParseFailure("resource_limit", "QA record contains too many list entries")
        for index, claim in enumerate(self.claims):
            _text(claim, f"claims[{index}]", allow_question=False)
        for index, need in enumerate(self.needs):
            _text(need, f"needs[{index}]", allow_question=False)
        if self.act not in ACTS:
            raise ParseFailure("semantic_invalid", f"unknown dialogue act: {self.act}")

    @property
    def answer_candidate(self) -> str | None:
        return None if self.answer == "?" else self.answer

    @property
    def has_unresolved_request(self) -> bool:
        return bool(self.needs) or self.act == "ask"

    def to_object(self) -> dict[str, Any]:
        return {
            "a": self.answer,
            "c": list(self.claims),
            "e": [item.to_object() for item in self.evidence],
            "n": list(self.needs),
            "x": self.act,
        }

    @property
    def canonical_text(self) -> str:
        return canonical_json(self.to_object())

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.canonical_text.encode("utf-8"))


def record_from_object(value: Any) -> QARecord:
    if type(value) is not dict:
        raise ParseFailure("semantic_invalid", "QA record must be a JSON object")
    if tuple(value) != QA_KEYS:
        missing = sorted(set(QA_KEYS) - set(value))
        extra = sorted(set(value) - set(QA_KEYS))
        raise ParseFailure(
            "noncanonical",
            f"QA keys/order differ; expected {QA_KEYS}, missing={missing}, extra={extra}",
        )
    evidence_raw = value["e"]
    if type(evidence_raw) is not list:
        raise ParseFailure("semantic_invalid", "e must be a list")
    if len(evidence_raw) > MAX_LIST_ITEMS:
        raise ParseFailure("resource_limit", "e has too many entries")
    evidence: list[Evidence] = []
    for index, item in enumerate(evidence_raw):
        if type(item) is not dict or tuple(item) != EVIDENCE_KEYS:
            raise ParseFailure(
                "noncanonical", f"e[{index}] must contain keys {EVIDENCE_KEYS} in order"
            )
        evidence.append(Evidence(_text(item["f"], f"e[{index}].f", allow_question=False), item["s"]))
    return QARecord(
        answer=_text(value["a"], "a"),
        claims=_text_list(value["c"], "c"),
        evidence=tuple(evidence),
        needs=_text_list(value["n"], "n"),
        act=value["x"] if type(value["x"]) is str else "",
    )


def parse_canonical_record(text: str) -> QARecord:
    if type(text) is not str:
        raise ParseFailure("malformed", "record output must be text")
    if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ParseFailure("resource_limit", "record output is too large")
    try:
        value = strict_json_loads(text, max_bytes=MAX_OUTPUT_BYTES)
    except ManifestError as exc:
        code = "malformed" if "duplicate" not in str(exc) else "noncanonical"
        raise ParseFailure(code, str(exc)) from exc
    record = record_from_object(value)
    if record.canonical_text != text:
        raise ParseFailure("noncanonical", "record JSON is valid but not canonical")
    return record


def _cte_values(text: str, label: str) -> tuple[str, ...]:
    if text == "NONE":
        return ()
    values = tuple(text.split(RESERVED_CTE_DELIMITER))
    for index, item in enumerate(values):
        _text(item, f"{label}[{index}]", allow_question=False)
        if RESERVED_CTE_DELIMITER in item:
            raise ParseFailure("semantic_invalid", f"{label} contains reserved delimiter")
    return values


def render_cte(record: QARecord) -> str:
    all_values = (*record.claims, *(item.fact for item in record.evidence), *record.needs)
    if any(RESERVED_CTE_DELIMITER in value for value in all_values):
        raise ParseFailure("semantic_invalid", "CTE content contains reserved delimiter")
    claims = RESERVED_CTE_DELIMITER.join(record.claims) if record.claims else "NONE"
    evidence = (
        RESERVED_CTE_DELIMITER.join(f"[{item.source}] {item.fact}" for item in record.evidence)
        if record.evidence
        else "NONE"
    )
    needs = RESERVED_CTE_DELIMITER.join(record.needs) if record.needs else "NONE"
    return (
        f"ACT: {record.act}\n"
        f"CLAIM: {claims}\n"
        f"EVIDENCE: {evidence}\n"
        f"NEED: {needs}\n"
        f"ANSWER: {record.answer}"
    )


def parse_cte(text: str) -> QARecord:
    if type(text) is not str or len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ParseFailure("resource_limit", "CTE output is invalid or too large")
    lines = text.split("\n")
    prefixes = ("ACT: ", "CLAIM: ", "EVIDENCE: ", "NEED: ", "ANSWER: ")
    if len(lines) != len(prefixes) or any(
        not line.startswith(prefix) for line, prefix in zip(lines, prefixes)
    ):
        raise ParseFailure("malformed", "CTE output must contain exactly five ordered lines")
    values = [line[len(prefix):] for line, prefix in zip(lines, prefixes)]
    evidence: list[Evidence] = []
    if values[2] != "NONE":
        for index, raw in enumerate(values[2].split(RESERVED_CTE_DELIMITER)):
            if len(raw) < 5 or raw[:3] not in {"[A]", "[B]"} or raw[3] != " ":
                raise ParseFailure("malformed", f"invalid evidence entry {index}")
            evidence.append(Evidence(raw[4:], raw[1]))
    record = QARecord(
        answer=_text(values[4], "ANSWER"),
        claims=_cte_values(values[1], "CLAIM"),
        evidence=tuple(evidence),
        needs=_cte_values(values[3], "NEED"),
        act=values[0],
    )
    if render_cte(record) != text:
        raise ParseFailure("noncanonical", "CTE output is not canonical")
    return record


@dataclass(frozen=True)
class OpaqueAnswer:
    answer: str
    raw_text: str
    unresolved_request_known: bool = False


def parse_answer_tag(text: str) -> OpaqueAnswer:
    """Parse archival/mock prose without pretending to recover typed fields."""

    if type(text) is not str or len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ParseFailure("resource_limit", "opaque output is invalid or too large")
    lines = text.split("\n")
    matches = [line for line in lines if line.startswith("ANSWER: ")]
    if len(matches) != 1 or lines[-1] != matches[0]:
        raise ParseFailure("malformed", "opaque arm requires one final ANSWER tag")
    answer = _text(matches[0][len("ANSWER: "):], "ANSWER")
    return OpaqueAnswer(answer=answer, raw_text=text)

