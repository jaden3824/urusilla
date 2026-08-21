"""Deterministic source identity for binding empirical evidence to this runtime."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .canonical import canonical_json, sha256_text


@lru_cache(maxsize=1)
def current_runtime_sha256() -> str:
    package = Path(__file__).resolve().parent
    members: dict[str, str] = {}
    for path in sorted(package.glob("*.py"), key=lambda item: item.name):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot identify runtime source: {exc}") from exc
        members[path.name] = sha256_text(text)
    if not members:
        raise ValueError("runtime source identity has no members")
    return sha256_text(canonical_json(members))
