#!/usr/bin/env python3
"""Validate and derive experimental Urusilla source manifests.

This module implements only the restricted source-manifest canonicalization
profile documented in SOURCE_MANIFEST_FORMAT.md. It is not a general RFC 8785
JSON Canonicalization Scheme implementation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence


PAYLOAD_FIELDS: tuple[str, ...] = (
    "languageSpecUri",
    "languageVersion",
    "capsuleSha256",
    "implementationOrigin",
    "conformanceReportUrl",
    "conformanceReportSha256",
)
JWS_FIELD = "sourceManifestJws"
ALLOWED_FIELDS = frozenset((*PAYLOAD_FIELDS, JWS_FIELD))
MAX_INPUT_BYTES = 65_536
LANGUAGE_VERSION = "0.1.0"

_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
_REPOSITORY = r"(?![.]{1,2}(?:/|$))[A-Za-z0-9._-]+"
_COMMIT = r"[0-9a-f]{40}"
_PATH_SEGMENT = r"(?![.]{1,2}(?:/|$))[A-Za-z0-9._-]+"
_PATH = rf"{_PATH_SEGMENT}(?:/{_PATH_SEGMENT})*"
_GITHUB_PREFIX = rf"https://github[.]com/{_OWNER}/{_REPOSITORY}"
_GITHUB_BLOB_RE = re.compile(
    rf"{_GITHUB_PREFIX}/blob/{_COMMIT}/{_PATH}", re.ASCII
)
_GITHUB_TREE_RE = re.compile(
    rf"{_GITHUB_PREFIX}/tree/{_COMMIT}(?:/{_PATH})?", re.ASCII
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
_BASE64URL_SEGMENT = r"(?:[A-Za-z0-9_-]{4})*(?:[A-Za-z0-9_-]{2,4})"
_JWS_RE = re.compile(
    rf"{_BASE64URL_SEGMENT}[.](?:{_BASE64URL_SEGMENT})?[.]"
    rf"{_BASE64URL_SEGMENT}",
    re.ASCII,
)

JwsVerifier = Callable[[str, bytes], bool]


class ManifestValidationError(ValueError):
    """Raised when a source manifest is structurally invalid."""

    def __init__(self, issues: Sequence[str]):
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


class ManifestVerificationError(RuntimeError):
    """Raised when a supplied JWS verifier cannot produce a boolean result."""


class _DuplicateKeyError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    """Derived identifiers and explicit trust status for a valid manifest."""

    source_id: str
    payload_sha256: str
    signature_status: str
    structurally_valid: bool = True
    effect_authorizing: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible diagnostic representation."""

        return {
            "effectAuthorizing": self.effect_authorizing,
            "payloadSha256": self.payload_sha256,
            "signatureStatus": self.signature_status,
            "sourceId": self.source_id,
            "structurallyValid": self.structurally_valid,
        }


def _is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _validate_structure(manifest: object) -> Mapping[str, str]:
    issues: list[str] = []
    if not isinstance(manifest, Mapping):
        raise ManifestValidationError(("manifest must be a JSON object",))

    missing = [field for field in PAYLOAD_FIELDS if field not in manifest]
    unknown = [field for field in manifest if field not in ALLOWED_FIELDS]
    for field in missing:
        issues.append(f"missing required field: {field}")
    for field in sorted(unknown, key=repr):
        issues.append(f"unknown field: {field!r}")

    for field in PAYLOAD_FIELDS:
        if field in manifest and not isinstance(manifest[field], str):
            issues.append(f"{field} must be a string")
    if JWS_FIELD in manifest and not isinstance(manifest[JWS_FIELD], str):
        issues.append(f"{JWS_FIELD} must be a string")

    string_fields = [
        field
        for field in (*PAYLOAD_FIELDS, JWS_FIELD)
        if isinstance(manifest.get(field), str)
    ]
    for field in string_fields:
        if not _is_ascii(manifest[field]):
            issues.append(f"{field} must contain ASCII characters only")

    if isinstance(manifest.get("languageSpecUri"), str):
        value = manifest["languageSpecUri"]
        if len(value) > 2_048 or _GITHUB_BLOB_RE.fullmatch(value) is None:
            issues.append(
                "languageSpecUri must be an immutable HTTPS GitHub blob URL "
                "with an exact 40-lowercase-hex commit and a safe ASCII path"
            )

    if isinstance(manifest.get("implementationOrigin"), str):
        value = manifest["implementationOrigin"]
        if len(value) > 2_048 or (
            _GITHUB_BLOB_RE.fullmatch(value) is None
            and _GITHUB_TREE_RE.fullmatch(value) is None
        ):
            issues.append(
                "implementationOrigin must be an immutable HTTPS GitHub blob or "
                "tree URL with an exact 40-lowercase-hex commit and a safe ASCII path"
            )

    if isinstance(manifest.get("conformanceReportUrl"), str):
        value = manifest["conformanceReportUrl"]
        if len(value) > 2_048 or _GITHUB_BLOB_RE.fullmatch(value) is None:
            issues.append(
                "conformanceReportUrl must be an immutable HTTPS GitHub blob URL "
                "with an exact 40-lowercase-hex commit and a safe ASCII path"
            )

    if isinstance(manifest.get("languageVersion"), str):
        value = manifest["languageVersion"]
        if value != LANGUAGE_VERSION:
            issues.append(
                f"languageVersion must be exactly {LANGUAGE_VERSION} for this profile"
            )

    for field in ("capsuleSha256", "conformanceReportSha256"):
        if isinstance(manifest.get(field), str) and _SHA256_RE.fullmatch(manifest[field]) is None:
            issues.append(f"{field} must be exactly 64 lowercase hexadecimal characters")

    if isinstance(manifest.get(JWS_FIELD), str):
        value = manifest[JWS_FIELD]
        if len(value) > 16_384 or _JWS_RE.fullmatch(value) is None:
            issues.append(
                "sourceManifestJws must have compact or detached JWS shape with "
                "unpadded base64url segments"
            )

    if issues:
        raise ManifestValidationError(issues)
    return manifest  # type: ignore[return-value]


def manifest_payload(manifest: object) -> dict[str, str]:
    """Return the six-field payload, excluding sourceManifestJws."""

    valid = _validate_structure(manifest)
    return {field: valid[field] for field in PAYLOAD_FIELDS}


def canonical_payload_bytes(manifest: object) -> bytes:
    """Return deterministic UTF-8 JSON bytes for the restricted payload domain."""

    payload = manifest_payload(manifest)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return encoded.encode("utf-8")


def payload_sha256(manifest: object) -> str:
    """Return the lowercase SHA-256 hex digest of the canonical payload bytes."""

    return hashlib.sha256(canonical_payload_bytes(manifest)).hexdigest()


def derive_source_id(manifest: object) -> str:
    """Return the lowercase leftmost 16 SHA-256 bytes as 32 hexadecimal digits."""

    return hashlib.sha256(canonical_payload_bytes(manifest)).digest()[:16].hex()


def validate_manifest(
    manifest: object,
    *,
    jws_verifier: JwsVerifier | None = None,
) -> ValidationResult:
    """Validate a manifest and report derivation and signature trust status.

    This module does not implement JWS cryptography. If a JWS is present without
    a caller-supplied verifier, its status is ``unverified``. The callback must
    verify the supplied JWS against the supplied canonical payload bytes and an
    accepted key policy. A false callback result is reported as ``invalid``.

    A result from this validator is never independently effect-authorizing.
    Authentication, referenced-artifact digest checks, conformance checks, and
    deployment authorization remain external policy decisions.
    """

    valid = _validate_structure(manifest)
    canonical = canonical_payload_bytes(valid)
    digest = hashlib.sha256(canonical).digest()

    if JWS_FIELD not in valid:
        signature_status = "unsigned"
    elif jws_verifier is None:
        signature_status = "unverified"
    else:
        try:
            verified = jws_verifier(valid[JWS_FIELD], canonical)
        except Exception as exc:
            raise ManifestVerificationError("the supplied JWS verifier raised an error") from exc
        if type(verified) is not bool:
            raise ManifestVerificationError("the supplied JWS verifier must return bool")
        signature_status = "verified" if verified else "invalid"

    return ValidationResult(
        source_id=digest[:16].hex(),
        payload_sha256=digest.hex(),
        signature_status=signature_status,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def load_manifest(path: str) -> object:
    """Load a UTF-8 JSON manifest from a file path or ``-`` for standard input."""

    if path == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ManifestValidationError((f"manifest input exceeds {MAX_INPUT_BYTES} bytes",))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestValidationError(("manifest input must be UTF-8",)) from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (_DuplicateKeyError, json.JSONDecodeError, RecursionError, MemoryError) as exc:
        raise ManifestValidationError((f"invalid JSON: {exc}",)) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and derive an experimental source manifest."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("validate", "validate a manifest and print a trust-status result"),
        ("id", "validate a manifest and print its derived source_id"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("manifest", help="UTF-8 JSON file, or - for standard input")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the dependency-free command-line interface."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        result = validate_manifest(manifest)
    except (OSError, ManifestValidationError, ManifestVerificationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate":
        print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
    else:
        print(result.source_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
