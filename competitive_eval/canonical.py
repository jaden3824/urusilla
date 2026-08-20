"""Restricted canonical JSON and atomic artifact helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .errors import IntegrityError, ManifestError


def canonical_json(value: Any) -> str:
    """Return the harness's deterministic UTF-8 JSON study profile."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ManifestError(f"value is not canonical-JSON encodable: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sequence_sha256(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        raw = value.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def strict_json_loads(text: str, *, max_bytes: int = 8 * 1024 * 1024) -> Any:
    if type(text) is not str:
        raise ManifestError("JSON input must be text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ManifestError("JSON input is not valid UTF-8 text") from exc
    if size > max_bytes:
        raise ManifestError(f"JSON input exceeds {max_bytes} bytes")
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError(f"invalid JSON: {exc}") from exc


def strict_json_file(path: Path, *, max_bytes: int = 64 * 1024 * 1024) -> Any:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ManifestError(f"JSON file exceeds {max_bytes} bytes: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError(f"JSON file is not UTF-8: {path}") from exc
    return strict_json_loads(text, max_bytes=max_bytes)


def require_exact_keys(
    value: Mapping[str, Any], expected: Sequence[str], *, label: str
) -> None:
    if type(value) is not dict:
        raise ManifestError(f"{label} must be a JSON object")
    observed = tuple(value)
    wanted = tuple(expected)
    if set(observed) != set(wanted):
        missing = sorted(set(wanted) - set(observed))
        extra = sorted(set(observed) - set(wanted))
        raise ManifestError(f"{label} field mismatch; missing={missing}, extra={extra}")


def verify_file(path: Path, expected_sha256: str, *, label: str) -> None:
    if not path.is_file():
        raise IntegrityError(f"missing frozen {label}: {path}")
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise IntegrityError(
            f"{label} digest mismatch: expected {expected_sha256}, got {observed}"
        )


def atomic_write(path: Path, data: bytes) -> None:
    """Write one artifact atomically and fsync it before publication."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    if pretty:
        data = (
            json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    else:
        data = canonical_bytes(value) + b"\n"
    atomic_write(path, data)

