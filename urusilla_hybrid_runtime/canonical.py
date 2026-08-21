"""Strict, dependency-free JSON helpers for the development hybrid runtime."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


MAX_JSON_BYTES = 1_048_576
MAX_JSON_DEPTH = 48
MAX_JSON_NODES = 100_000
MAX_STRING_CHARS = 65_536
MAX_SAFE_INTEGER = 9_007_199_254_740_991


class HybridRuntimeError(ValueError):
    """Base error for fail-closed runtime validation."""


class JsonValidationError(HybridRuntimeError):
    """Raised when untrusted JSON is malformed, ambiguous, or too large."""


def _reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JsonValidationError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _validate_tree(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise JsonValidationError(f"JSON exceeds {MAX_JSON_NODES} values")
        if depth > MAX_JSON_DEPTH:
            raise JsonValidationError(f"JSON nesting exceeds {MAX_JSON_DEPTH}")
        if current is None or type(current) is bool:
            continue
        if type(current) is int:
            if not -MAX_SAFE_INTEGER <= current <= MAX_SAFE_INTEGER:
                raise JsonValidationError(
                    "hybrid canonical JSON integer exceeds the I-JSON safe range"
                )
            continue
        if type(current) is float:
            raise JsonValidationError(
                "hybrid canonical JSON forbids floating-point numbers; use a "
                "bounded integer or an explicitly scaled integer field"
            )
        if type(current) is str:
            if len(current) > MAX_STRING_CHARS:
                raise JsonValidationError(
                    f"JSON string exceeds {MAX_STRING_CHARS} characters"
                )
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise JsonValidationError("JSON string is not valid UTF-8") from exc
            continue
        if type(current) is list:
            stack.extend((item, depth + 1) for item in current)
            continue
        if type(current) is dict:
            for key, item in current.items():
                if type(key) is not str:
                    raise JsonValidationError("JSON object keys must be strings")
                try:
                    encoded_key = key.encode("ascii")
                except UnicodeEncodeError as exc:
                    raise JsonValidationError(
                        "hybrid canonical JSON object keys must be ASCII"
                    ) from exc
                if not encoded_key or any(byte < 0x20 or byte == 0x7F for byte in encoded_key):
                    raise JsonValidationError(
                        "hybrid canonical JSON object keys must be non-empty "
                        "printable ASCII"
                    )
                stack.append((key, depth + 1))
                stack.append((item, depth + 1))
            continue
        raise JsonValidationError(f"unsupported JSON value type: {type(current).__name__}")


def strict_json_loads(text: str, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    if type(text) is not str:
        raise JsonValidationError("JSON input must be text")
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise JsonValidationError("JSON input is not valid UTF-8") from exc
    if len(raw) > max_bytes:
        raise JsonValidationError(f"JSON input exceeds {max_bytes} bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                JsonValidationError(f"non-finite JSON number: {token}")
            ),
        )
    except JsonValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError) as exc:
        raise JsonValidationError(f"invalid JSON: {exc}") from exc
    _validate_tree(value)
    return value


def canonical_json(value: Any) -> str:
    _validate_tree(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise JsonValidationError(f"value is not canonical-JSON encodable: {exc}") from exc


def sha256_text(text: str) -> str:
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise JsonValidationError("digest input is not valid UTF-8") from exc
    return "sha256:" + hashlib.sha256(raw).hexdigest()
