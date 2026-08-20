"""Adoption-first wrapper around the repository's current semantic artifacts.

This module deliberately does not reimplement the normative semantic validator.
It imports the repository's v0.1 validator and codecs, verifies their exact file
digests, and adds a small JSON-friendly negotiation boundary. The product label
and private local A2A extension identifier are experimental. No method authorizes an
external effect, and no method performs network I/O.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_LABEL = "Urusilla Adoption Kit"
INTERFACE_VERSION = "1.0.0"
CAPABILITY_FORMAT = "urusilla-capability-v1"
DELIVERY_FORMAT = "urusilla-delivery-v1"
A2A_LOCAL_EXTENSION = "urn:urusilla:local:1"
A2A_VERSION = "1.0"

LANGUAGE_VERSION = "0.1.0"
RELEASE_STATUS = "experimental-unsigned"
CAPSULE_SHA256 = "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
CAPSULE_BYTES = 33_476
PROFILE_ID = 1
PROFILE_CAPSULE_SHA256 = (
    "b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6"
)
PROFILE_DICTIONARY_ID = "7d12fc414eae60b2"
PROFILE_CAPSULE_BYTES = 1_402

JSON_REPRESENTATION = "canonical-json-v1"
TERSE_REPRESENTATION = "controlled-terse-english-v1"
WIRE_V01_REPRESENTATION = "urusilla-wire-v0.1"
WIRE_V02_REPRESENTATION = "urusilla-wire-v0.2-static-7d12fc414eae60b2"

MAX_DELIVERY_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_SAFE_INTEGER = (1 << 53) - 1
_SOURCE_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MODE_ORDER = ("bridge", "native", "fallback")
_REPRESENTATION_ORDER = (
    JSON_REPRESENTATION,
    TERSE_REPRESENTATION,
    WIRE_V02_REPRESENTATION,
    WIRE_V01_REPRESENTATION,
)

_PINNED_FILES = {
    "urusilla_v0_1_spec.md": "4d817a607218f64998e1c0b061f80f07b400b382236485f2a2e7b88f6e92b263",
    "urusilla_capsule_v0_1.json": CAPSULE_SHA256,
    "urusilla.py": "3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf",
    "urusilla_wire_v02.py": "166b1090b536bfff942667d43be583b2345eeb14b9da5d1535b7a16bb6bab2e7",
    "urusilla_a2a_adapter.py": "1a930bfde9e4100789dfaa7666f994399f9d55ed6a27551ad05c3d68e751a15d",
    "source_manifest.py": "7643d29d37d4ac4efc1ddddd2a529aa322b9c0e8b042eb5ed90a292473f6d6a4",
    "urusilla_terse_english_benchmark.py": (
        "f528f68e22aa0c7b2fcc2ef10719648453aeda54c9c08df0e3986a7161e2c00e"
    ),
}

CAPSULE_BOUND_REFERENCE_SHA256 = (
    "3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf"
)


class IntegrationError(ValueError):
    """The integration boundary rejected an incompatible or unsafe value."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _preimport_verify() -> None:
    """Hash executable root modules before importing any of them."""

    for filename, expected in _PINNED_FILES.items():
        path = REPOSITORY_ROOT / filename
        if not path.is_file():
            raise IntegrationError(f"pinned root artifact is missing: {filename}")
        observed = _sha256(path.read_bytes())
        if not hmac.compare_digest(observed, expected):
            raise IntegrationError(
                f"pre-import root artifact mismatch for {filename}: "
                f"expected {expected}, got {observed}"
            )


_preimport_verify()
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import urusilla_a2a_adapter as canonical_a2a  # noqa: E402
import urusilla as canonical_v01  # noqa: E402
import urusilla_wire_v02 as canonical_v02  # noqa: E402
import source_manifest as canonical_source_manifest  # noqa: E402
from urusilla_terse_english_benchmark import (  # noqa: E402
    decode_terse_english,
    encode_terse_english,
)


def _require_sha256(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise IntegrationError(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def _require_source_id(value: Any, field: str = "source_id") -> str:
    if type(value) is not str or _SOURCE_ID.fullmatch(value) is None:
        raise IntegrationError(f"{field} must be 32 lowercase hexadecimal characters")
    return value


def _reject_constant(value: str) -> Any:
    raise IntegrationError(f"non-finite JSON number is forbidden: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntegrationError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _reject_float(_value: str) -> Any:
    raise IntegrationError("canonical-json-v1 forbids floating-point numbers")


def _parse_safe_integer(value: str) -> int:
    parsed = int(value)
    if not -MAX_JSON_SAFE_INTEGER <= parsed <= MAX_JSON_SAFE_INTEGER:
        raise IntegrationError("canonical-json-v1 integer exceeds the shared safe range")
    return parsed


def _validate_json_value(
    value: Any,
    *,
    depth: int = 0,
    active: set[int] | None = None,
) -> None:
    """Validate the deliberately narrow frozen Python/Node JSON domain."""

    if depth > MAX_JSON_DEPTH:
        raise IntegrationError(f"canonical-json-v1 exceeds depth {MAX_JSON_DEPTH}")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if not -MAX_JSON_SAFE_INTEGER <= value <= MAX_JSON_SAFE_INTEGER:
            raise IntegrationError("canonical-json-v1 integer exceeds the shared safe range")
        return
    if type(value) is float:
        raise IntegrationError("canonical-json-v1 forbids floating-point numbers")
    if type(value) is str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise IntegrationError("canonical-json-v1 forbids unpaired Unicode surrogates")
        return
    if type(value) not in (list, dict):
        raise IntegrationError(
            f"canonical-json-v1 forbids value type {type(value).__name__}"
        )
    identity = id(value)
    seen = active if active is not None else set()
    if identity in seen:
        raise IntegrationError("canonical-json-v1 requires an acyclic JSON value")
    seen.add(identity)
    try:
        if type(value) is list:
            for item in value:
                _validate_json_value(item, depth=depth + 1, active=seen)
        else:
            for key, item in value.items():
                if type(key) is not str:
                    raise IntegrationError("canonical-json-v1 object keys must be strings")
                _validate_json_value(key, depth=depth + 1, active=seen)
                _validate_json_value(item, depth=depth + 1, active=seen)
    finally:
        seen.remove(identity)


def canonical_json_bytes(value: Any) -> bytes:
    """Return the kit-local deterministic JSON form.

    This is intentionally described as kit-local deterministic JSON, not as a
    general RFC 8785 implementation.  Cross-runtime callers must also honor the
    peer's numeric and byte-value limits advertised during discovery.
    """

    _validate_json_value(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        encoded = text.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise IntegrationError(f"value is not representable as deterministic JSON: {exc}") from exc
    if len(encoded) > MAX_DELIVERY_BYTES:
        raise IntegrationError("canonical-json-v1 value exceeds the kit byte limit")
    return encoded


def _load_canonical_json(raw: bytes) -> Any:
    if not isinstance(raw, bytes) or len(raw) > MAX_DELIVERY_BYTES:
        raise IntegrationError("JSON payload type or size is invalid")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_safe_integer,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrationError("payload is not strict UTF-8 JSON") from exc
    if canonical_json_bytes(value) != raw:
        raise IntegrationError("JSON payload is valid but not kit-canonical")
    return value


def verify_artifact_pins() -> dict[str, str]:
    """Verify every root artifact imported by this kit and the v0.2 capsule."""

    observed: dict[str, str] = {}
    for filename, expected in _PINNED_FILES.items():
        path = REPOSITORY_ROOT / filename
        if not path.is_file():
            raise IntegrationError(f"pinned root artifact is missing: {filename}")
        digest = _sha256(path.read_bytes())
        if not hmac.compare_digest(digest, expected):
            raise IntegrationError(
                f"root artifact digest mismatch for {filename}: expected {expected}, got {digest}"
            )
        observed[filename] = digest

    loaded_modules = {
        "urusilla.py": canonical_v01,
        "urusilla_wire_v02.py": canonical_v02,
        "urusilla_a2a_adapter.py": canonical_a2a,
        "source_manifest.py": canonical_source_manifest,
    }
    for filename, module in loaded_modules.items():
        loaded_path = Path(getattr(module, "__file__", "")).resolve()
        expected_path = (REPOSITORY_ROOT / filename).resolve()
        if loaded_path != expected_path:
            raise IntegrationError(
                f"loaded module path for {filename} is {loaded_path}, not {expected_path}"
            )
        if not hmac.compare_digest(_sha256(loaded_path.read_bytes()), _PINNED_FILES[filename]):
            raise IntegrationError(f"loaded module bytes changed after import: {filename}")

    try:
        capsule = json.loads((REPOSITORY_ROOT / "urusilla_capsule_v0_1.json").read_bytes())
        capsule_reference = capsule["implementation_artifacts"]["reference_codec"]["sha256"]
        capsule_release_status = capsule["release_status"]
        publisher_status = capsule["publisher_authentication"]["status"]
        unsigned_restriction = capsule["security_contract"]["unsigned_restriction"]
        unsigned_publication = capsule["github_distribution"]["publication_modes"][
            "unsigned_research"
        ]
        trusted_publication = capsule["github_distribution"]["publication_modes"][
            "trusted_effect_authorizing"
        ]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise IntegrationError("Grammar Capsule reference-codec pin is missing") from exc
    if capsule_reference != CAPSULE_BOUND_REFERENCE_SHA256:
        raise IntegrationError("Grammar Capsule embedded reference-codec pin changed")
    if capsule_release_status != RELEASE_STATUS or publisher_status != "unsigned":
        raise IntegrationError("Grammar Capsule lifecycle or publisher status changed")
    if (
        "local read-only" not in unsigned_restriction
        or "MUST NOT authorize external side effects" not in unsigned_restriction
        or "Public source review" not in unsigned_publication
        or "effect-authorizing behavior disabled" not in unsigned_publication
        or "accepted publisher signature" not in trusted_publication
        or "authorization policy" not in trusted_publication
    ):
        raise IntegrationError("Grammar Capsule unsigned-operation policy changed")
    observed["capsule.bound_reference_codec_sha256"] = capsule_reference
    observed["capsule.reference_codec_matches_observed"] = str(
        hmac.compare_digest(capsule_reference, observed["urusilla.py"])
    ).lower()
    observed["capsule.release_status"] = capsule_release_status
    observed["capsule.publisher_status"] = publisher_status
    observed["capsule.unsigned_public_source_distribution_allowed"] = "true"
    observed["capsule.unsigned_operation_scope"] = "local-read-only"
    observed["capsule.effect_authorizing_requires_signature_and_policy"] = "true"

    profile_capsule = canonical_v02.encode_capsule(canonical_v02.DEFAULT_PROFILE)
    profile_digest = _sha256(profile_capsule)
    if len(profile_capsule) != PROFILE_CAPSULE_BYTES:
        raise IntegrationError("v0.2 profile capsule byte length changed")
    if not hmac.compare_digest(profile_digest, PROFILE_CAPSULE_SHA256):
        raise IntegrationError("v0.2 profile capsule digest changed")
    if canonical_v02.DEFAULT_PROFILE.profile_id != PROFILE_ID:
        raise IntegrationError("v0.2 profile numeric ID changed")
    if canonical_v02.DEFAULT_PROFILE.dictionary_id_hex != PROFILE_DICTIONARY_ID:
        raise IntegrationError("v0.2 profile dictionary ID changed")
    observed["urusilla_wire_v02.profile_capsule"] = profile_digest
    return observed


@dataclass(frozen=True)
class ColdArtifact:
    name: str
    sha256: str
    bytes: int


GRAMMAR_CAPSULE = ColdArtifact(
    "grammar_capsule", CAPSULE_SHA256, CAPSULE_BYTES
)
WIRE_V02_CAPSULE = ColdArtifact(
    "wire_v02_profile_capsule", PROFILE_CAPSULE_SHA256, PROFILE_CAPSULE_BYTES
)


class ArtifactCache:
    """In-memory receiver-acknowledged artifact cache.

    Constructor digests model artifacts the receiver already acknowledges as
    installed. New entries can be added only by verifying the exact bytes.
    """

    def __init__(self, digests: Sequence[str] = ()) -> None:
        self._digests: set[str] = set()
        for digest in digests:
            self._digests.add(_require_sha256(digest, "cached artifact digest"))

    @property
    def digests(self) -> tuple[str, ...]:
        return tuple(sorted(self._digests))

    def contains(self, digest: str) -> bool:
        return _require_sha256(digest, "artifact digest") in self._digests

    def install_verified(self, artifact: ColdArtifact, data: bytes) -> dict[str, Any]:
        if type(data) is not bytes:
            raise IntegrationError("artifact transfer must provide exact bytes")
        if len(data) != artifact.bytes:
            raise IntegrationError(f"artifact byte length mismatch for {artifact.name}")
        if not hmac.compare_digest(_sha256(data), artifact.sha256):
            raise IntegrationError(f"artifact digest mismatch for {artifact.name}")
        hit = artifact.sha256 in self._digests
        if not hit:
            self._digests.add(artifact.sha256)
        return {
            "name": artifact.name,
            "sha256": artifact.sha256,
            "artifact_bytes": artifact.bytes,
            "cache_hit": hit,
            "transfer_encoding": "raw-bytes-in-memory",
            "transferred_bytes": 0 if hit else artifact.bytes,
        }


@dataclass(frozen=True)
class NegotiatedSession:
    session_id: str
    mode: str
    representation: str
    local_source_id: str
    peer_source_id: str
    peer_language_version: str
    peer_capsule_sha256: str
    peer_profile_id: int | None
    peer_profile_capsule_sha256: str | None
    peer_dictionary_id: str | None
    peer_cached_artifacts: tuple[str, ...]
    pins_compatible: bool
    fallback_reason: str | None
    expected_messages: int
    estimated_warm_envelope_bytes: int
    discovery_bytes: int
    required_artifacts: tuple[ColdArtifact, ...]
    planned_cold_artifacts: tuple[Mapping[str, Any], ...]

    @property
    def planned_cold_bytes(self) -> int:
        return sum(int(item["planned_transfer_bytes"]) for item in self.planned_cold_artifacts)

    @property
    def estimated_session_bytes(self) -> int:
        return self.discovery_bytes + self.planned_cold_bytes + (
            self.expected_messages * self.estimated_warm_envelope_bytes
        )


class SessionAccountingReceipt:
    """One-shot receipt for discovery plus verified in-memory artifact transfer."""

    __slots__ = ("session_id", "discovery_bytes", "artifact_transfers", "_consumed")

    def __init__(
        self,
        *,
        session_id: str,
        discovery_bytes: int,
        artifact_transfers: Sequence[Mapping[str, Any]],
    ) -> None:
        self.session_id = session_id
        self.discovery_bytes = discovery_bytes
        self.artifact_transfers = tuple(dict(item) for item in artifact_transfers)
        self._consumed = False

    @property
    def transferred_artifact_bytes(self) -> int:
        return sum(int(item["transferred_bytes"]) for item in self.artifact_transfers)

    def consume(self, session_id: str) -> tuple[int, int]:
        if not hmac.compare_digest(self.session_id, session_id):
            raise IntegrationError("accounting receipt belongs to a different session")
        if self._consumed:
            raise IntegrationError("session discovery/artifact accounting was already consumed")
        self._consumed = True
        return self.discovery_bytes, self.transferred_artifact_bytes


@dataclass(frozen=True)
class ByteAccounting:
    raw_payload_bytes: int
    carrier_payload_bytes: int
    envelope_bytes: int
    discovery_bytes: int
    transferred_artifact_bytes: int

    @property
    def first_delivery_total_bytes(self) -> int:
        return self.discovery_bytes + self.transferred_artifact_bytes + self.envelope_bytes


@dataclass(frozen=True)
class EncodedDelivery:
    envelope: Mapping[str, Any]
    accounting: ByteAccounting


@dataclass(frozen=True)
class DecodedDelivery:
    message: Mapping[str, Any] | None
    opaque_payload: Any | None
    mode: str
    representation: str
    source_id: str
    semantic_valid: bool
    effect_authorized: bool


def _representation_offer(
    representation_id: str,
    *,
    requires: Sequence[str],
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    offer: dict[str, Any] = {
        "id": representation_id,
        "can_encode": True,
        "can_decode": True,
        "relay_only": False,
        "requires_cached_artifacts": list(requires),
    }
    if profile is not None:
        offer["profile"] = dict(profile)
    return offer


def _representation_map(capability: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    value = capability.get("representations")
    if not isinstance(value, list):
        raise IntegrationError("capability representations must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise IntegrationError(f"representations[{index}] must be an object")
        identifier = item.get("id")
        if type(identifier) is not str or identifier not in _REPRESENTATION_ORDER:
            raise IntegrationError(f"representations[{index}] uses an unknown id")
        if identifier in result:
            raise IntegrationError(f"duplicate representation id: {identifier}")
        expected_fields = {
            "id",
            "can_encode",
            "can_decode",
            "relay_only",
            "requires_cached_artifacts",
        }
        if identifier == WIRE_V02_REPRESENTATION:
            expected_fields.add("profile")
        if set(item) != expected_fields:
            raise IntegrationError(f"representation {identifier} fields differ from the closed profile")
        for flag in ("can_encode", "can_decode", "relay_only"):
            if type(item.get(flag)) is not bool:
                raise IntegrationError(f"representation {identifier} has invalid {flag}")
        requires = item.get("requires_cached_artifacts")
        if not isinstance(requires, list) or not all(
            type(digest) is str and _SHA256.fullmatch(digest) for digest in requires
        ):
            raise IntegrationError(
                f"representation {identifier} has invalid cache requirements"
            )
        if len(requires) != len(set(requires)):
            raise IntegrationError(f"representation {identifier} repeats a cache requirement")
        if identifier == WIRE_V02_REPRESENTATION:
            profile = item.get("profile")
            if not isinstance(profile, Mapping) or set(profile) != {
                "profile_id",
                "profile_capsule_sha256",
                "dictionary_id",
                "status",
            }:
                raise IntegrationError("v0.2 representation profile is not closed")
        result[identifier] = item
    return result


def _validate_capability(capability: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(capability, Mapping):
        raise IntegrationError("peer capability must be an object")
    if capability.get("format") != CAPABILITY_FORMAT:
        raise IntegrationError("unsupported capability format")
    if capability.get("interface_version") != INTERFACE_VERSION:
        raise IntegrationError("unsupported capability interface version")
    expected_top = {
        "format",
        "interface_version",
        "product_label",
        "lifecycle",
        "semantics",
        "pins",
        "provenance",
        "modes",
        "representations",
        "cached_artifacts",
        "bindings",
        "limits",
        "safety",
    }
    if set(capability) != expected_top:
        raise IntegrationError("capability fields differ from the closed profile")
    if capability.get("product_label") != PRODUCT_LABEL:
        raise IntegrationError("capability product label differs")
    if capability.get("lifecycle") != RELEASE_STATUS:
        raise IntegrationError("capability lifecycle differs from the canonical release status")
    semantics = capability.get("semantics")
    if not isinstance(semantics, Mapping):
        raise IntegrationError("capability semantics must be an object")
    if set(semantics) != {
        "language_version",
        "capsule_sha256",
        "release_status",
        "normative_representation",
    } or (
        semantics.get("normative_representation") != "typed-ir"
        or semantics.get("release_status") != RELEASE_STATUS
    ):
        raise IntegrationError("capability semantics fields differ from the closed profile")
    for field in ("language_version", "capsule_sha256", "release_status"):
        if type(semantics.get(field)) is not str:
            raise IntegrationError(f"capability semantics.{field} must be a string")
    _require_sha256(semantics["capsule_sha256"], "semantics.capsule_sha256")
    pins = capability.get("pins")
    if not isinstance(pins, Mapping):
        raise IntegrationError("capability pins must be an object")
    if set(pins) != {
        "source_id",
        "source_status",
        "source_manifest_payload_sha256",
        "source_manifest_signature_status",
    }:
        raise IntegrationError("capability source pins differ from the closed profile")
    _require_source_id(pins.get("source_id"), "capability pins.source_id")
    if type(pins.get("source_status")) is not str:
        raise IntegrationError("capability source_status must be text")
    payload_pin = pins.get("source_manifest_payload_sha256")
    if payload_pin is not None:
        _require_sha256(payload_pin, "source manifest payload digest")
    if type(pins.get("source_manifest_signature_status")) is not str:
        raise IntegrationError("source manifest signature status must be text")
    provenance = capability.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != {
        "capsule_reference_codec_sha256",
        "observed_reference_codec_sha256",
        "reference_codec_matches_capsule",
        "support_claim_eligible",
    }:
        raise IntegrationError("capability provenance fields differ from the closed profile")
    _require_sha256(provenance.get("capsule_reference_codec_sha256"), "Capsule codec pin")
    _require_sha256(provenance.get("observed_reference_codec_sha256"), "observed codec pin")
    if type(provenance.get("reference_codec_matches_capsule")) is not bool:
        raise IntegrationError("capability provenance match flag must be Boolean")
    if provenance.get("support_claim_eligible") is not False:
        raise IntegrationError("this snapshot must not advertise an eligible support claim")
    modes = capability.get("modes")
    if not isinstance(modes, Mapping) or set(modes) != set(_MODE_ORDER):
        raise IntegrationError("capability must declare bridge, native, and fallback modes")
    for mode in _MODE_ORDER:
        if not isinstance(modes[mode], Mapping) or type(modes[mode].get("supported")) is not bool:
            raise IntegrationError(f"capability mode {mode} is invalid")
    if set(modes["bridge"]) != {"supported", "claim"}:
        raise IntegrationError("bridge mode fields differ from the closed profile")
    if set(modes["native"]) != {"supported", "verified", "claim"}:
        raise IntegrationError("native mode fields differ from the closed profile")
    if modes["native"]["supported"] and modes["native"].get("verified") is not True:
        raise IntegrationError("native support cannot be advertised without verified evidence")
    if set(modes["fallback"]) != {"supported", "order"}:
        raise IntegrationError("fallback mode fields differ from the closed profile")
    order = modes["fallback"].get("order")
    if not isinstance(order, list) or len(order) != len(set(order)) or not all(
        item in {JSON_REPRESENTATION, TERSE_REPRESENTATION} for item in order
    ):
        raise IntegrationError("fallback order must contain only JSON and controlled terse English")
    cached = capability.get("cached_artifacts")
    if not isinstance(cached, list) or not all(
        type(item) is str and _SHA256.fullmatch(item) for item in cached
    ):
        raise IntegrationError("cached_artifacts must contain full lowercase SHA-256 values")
    if len(set(cached)) != len(cached):
        raise IntegrationError("cached_artifacts contains a duplicate")
    _representation_map(capability)
    limits = capability.get("limits")
    if not isinstance(limits, Mapping) or set(limits) != {
        "max_delivery_bytes",
        "json_max_safe_integer",
        "json_float64",
        "json_bytes",
        "controlled_terse_float64",
        "controlled_terse_bytes",
    }:
        raise IntegrationError("capability limits differ from the closed profile")
    if (
        limits.get("max_delivery_bytes") != MAX_DELIVERY_BYTES
        or limits.get("json_max_safe_integer") != MAX_JSON_SAFE_INTEGER
        or limits.get("json_float64") is not False
        or limits.get("json_bytes") is not False
        or type(limits.get("controlled_terse_float64")) is not bool
        or type(limits.get("controlled_terse_bytes")) is not bool
    ):
        raise IntegrationError("capability JSON limits are not cross-runtime safe")
    safety = capability.get("safety")
    if not isinstance(safety, Mapping) or set(safety) != {
        "effect_authorization",
        "network_io",
        "unsigned_operation_read_only",
        "provenance_bound",
    } or safety != {
        "effect_authorization": False,
        "network_io": False,
        "unsigned_operation_read_only": True,
        "provenance_bound": False,
    }:
        raise IntegrationError("capability safety flags differ from this unsigned local snapshot")
    return capability


def _json_peer_eligible(value: Any, limits: Mapping[str, Any]) -> bool:
    max_integer = limits.get("json_max_safe_integer", (1 << 53) - 1)
    if type(max_integer) is not int or max_integer < 0:
        return False
    if value is None or type(value) in (bool, str):
        return True
    if type(value) is int:
        return -max_integer <= value <= max_integer
    if type(value) is float:
        return bool(limits.get("json_float64", False)) and value == value and abs(value) != float("inf")
    if type(value) is bytes:
        return False
    if type(value) is list:
        return all(_json_peer_eligible(item, limits) for item in value)
    if isinstance(value, Mapping):
        return all(type(key) is str and _json_peer_eligible(item, limits) for key, item in value.items())
    return False


def _contains_type(value: Any, target: type) -> bool:
    if type(value) is target:
        return True
    if type(value) is list:
        return any(_contains_type(item, target) for item in value)
    if isinstance(value, Mapping):
        return any(_contains_type(item, target) for item in value.values())
    return False


class UrusillaSDK:
    """One local endpoint with explicit capability, source, and cache pins."""

    def __init__(
        self,
        *,
        source_id: str | None = None,
        source_manifest: Mapping[str, Any] | None = None,
        source_manifest_jws_verifier: Callable[[str, bytes], bool] | None = None,
        cache: ArtifactCache | None = None,
        native_evidence_sha256: str | None = None,
    ) -> None:
        self.artifact_digests = verify_artifact_pins()
        self.cache = cache if cache is not None else ArtifactCache()
        self._prepared_session_ids: set[str] = set()
        self.declared_native_evidence_sha256 = (
            _require_sha256(native_evidence_sha256, "native_evidence_sha256")
            if native_evidence_sha256 is not None
            else None
        )

        if source_manifest is not None:
            try:
                result = canonical_source_manifest.validate_manifest(
                    source_manifest,
                    jws_verifier=source_manifest_jws_verifier,
                )
                derived = canonical_source_manifest.derive_source_id(source_manifest)
            except Exception as exc:
                raise IntegrationError(f"source manifest validation failed: {exc}") from exc
            if source_manifest.get("capsuleSha256") != CAPSULE_SHA256:
                raise IntegrationError("source manifest Capsule digest differs from this exact snapshot")
            if result.signature_status == "invalid":
                raise IntegrationError("source manifest signature verification failed")
            if source_id is not None and not hmac.compare_digest(
                _require_source_id(source_id), derived
            ):
                raise IntegrationError("provided source_id differs from the source manifest")
            self.source_id = derived
            self.source_status = "manifest-" + result.signature_status
            self.source_manifest_payload_sha256 = result.payload_sha256
            self.source_manifest_signature_status = result.signature_status
        else:
            if source_id is None:
                raise IntegrationError("source_id or a complete source_manifest is required")
            self.source_id = _require_source_id(source_id)
            self.source_status = "unverified-local-pin"
            self.source_manifest_payload_sha256 = None
            self.source_manifest_signature_status = "not-supplied"

    def discover_capabilities(self) -> dict[str, Any]:
        profile = {
            "profile_id": PROFILE_ID,
            "profile_capsule_sha256": PROFILE_CAPSULE_SHA256,
            "dictionary_id": PROFILE_DICTIONARY_ID,
            "status": "benchmark-specialized-experimental",
        }
        native: dict[str, Any] = {
            "supported": False,
            "verified": False,
            "claim": "native evidence verifier is not implemented; any caller digest is declaration-only",
        }
        reference_matches = self.artifact_digests[
            "capsule.reference_codec_matches_observed"
        ] == "true"
        return {
            "format": CAPABILITY_FORMAT,
            "interface_version": INTERFACE_VERSION,
            "product_label": PRODUCT_LABEL,
            "lifecycle": RELEASE_STATUS,
            "semantics": {
                "language_version": LANGUAGE_VERSION,
                "capsule_sha256": CAPSULE_SHA256,
                "release_status": RELEASE_STATUS,
                "normative_representation": "typed-ir",
            },
            "pins": {
                "source_id": self.source_id,
                "source_status": self.source_status,
                "source_manifest_payload_sha256": self.source_manifest_payload_sha256,
                "source_manifest_signature_status": self.source_manifest_signature_status,
            },
            "provenance": {
                "capsule_reference_codec_sha256": CAPSULE_BOUND_REFERENCE_SHA256,
                "observed_reference_codec_sha256": self.artifact_digests["urusilla.py"],
                "reference_codec_matches_capsule": reference_matches,
                "support_claim_eligible": False,
            },
            "modes": {
                "bridge": {"supported": True, "claim": "adapter input normalized by canonical validator"},
                "native": native,
                "fallback": {
                    "supported": True,
                    "order": [JSON_REPRESENTATION, TERSE_REPRESENTATION],
                },
            },
            "representations": [
                _representation_offer(JSON_REPRESENTATION, requires=(CAPSULE_SHA256,)),
                _representation_offer(TERSE_REPRESENTATION, requires=(CAPSULE_SHA256,)),
                _representation_offer(WIRE_V01_REPRESENTATION, requires=(CAPSULE_SHA256,)),
                _representation_offer(
                    WIRE_V02_REPRESENTATION,
                    requires=(CAPSULE_SHA256, PROFILE_CAPSULE_SHA256),
                    profile=profile,
                ),
            ],
            "cached_artifacts": list(self.cache.digests),
            "bindings": {
                "json_envelope": True,
                "a2a_message_shape": "private-local-identifier-not-official-extension",
                "mcp_structured_content": "friendly-shape-not-conformance-claim",
            },
            "limits": {
                "max_delivery_bytes": MAX_DELIVERY_BYTES,
                "json_max_safe_integer": MAX_JSON_SAFE_INTEGER,
                "json_float64": False,
                "json_bytes": False,
                "controlled_terse_float64": True,
                "controlled_terse_bytes": True,
            },
            "safety": {
                "effect_authorization": False,
                "network_io": False,
                "unsigned_operation_read_only": True,
                "provenance_bound": False,
            },
        }

    def normalize_input(
        self,
        value: Any,
        *,
        mode: str = "bridge",
        bridge_compiler: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Normalize a bridge/native/fallback input without guessing ambiguity."""

        if mode not in _MODE_ORDER:
            raise IntegrationError("mode must be bridge, native, or fallback")
        candidate = value
        if mode == "bridge" and type(value) is str:
            if bridge_compiler is None:
                raise IntegrationError("text bridge input requires an explicit compiler callback")
            candidate = bridge_compiler(value)
            if not isinstance(candidate, Mapping):
                raise IntegrationError("bridge compiler must return exactly one IR object")
        elif mode == "native" and not isinstance(value, Mapping):
            raise IntegrationError("native mode accepts a model-produced typed IR object only")
        elif mode == "fallback" and not isinstance(value, Mapping):
            raise IntegrationError("fallback mode accepts a structured IR object only")
        elif not isinstance(candidate, Mapping):
            raise IntegrationError("input must be a mapping")
        try:
            return canonical_v01.normalize_message(candidate)
        except canonical_v01.UrusillaError as exc:
            raise IntegrationError(f"canonical semantic validation failed: {exc}") from exc

    def _payload(self, message: Mapping[str, Any], representation: str) -> tuple[bytes, str, str]:
        canonical = canonical_v01.normalize_message(message)
        if representation == JSON_REPRESENTATION:
            raw = canonical_json_bytes(canonical)
            return raw, "utf-8-json", raw.decode("utf-8")
        if representation == TERSE_REPRESENTATION:
            text = encode_terse_english(canonical)
            return text.encode("utf-8"), "utf-8-controlled-english", text
        if representation == WIRE_V01_REPRESENTATION:
            raw = canonical_v01.encode_message(canonical)
            return raw, "base64", base64.b64encode(raw).decode("ascii")
        if representation == WIRE_V02_REPRESENTATION:
            raw = canonical_v02.encode_message(canonical, canonical_v02.DEFAULT_PROFILE)
            return raw, "base64", base64.b64encode(raw).decode("ascii")
        raise IntegrationError(f"unsupported representation: {representation}")

    def _pins_for(self, representation: str) -> dict[str, Any]:
        pins: dict[str, Any] = {
            "language_version": LANGUAGE_VERSION,
            "capsule_sha256": CAPSULE_SHA256,
            "source_id": self.source_id,
        }
        if representation == WIRE_V02_REPRESENTATION:
            pins.update(
                {
                    "profile_id": PROFILE_ID,
                    "profile_capsule_sha256": PROFILE_CAPSULE_SHA256,
                    "dictionary_id": PROFILE_DICTIONARY_ID,
                }
            )
        return pins

    def _build_envelope(
        self,
        message: Mapping[str, Any],
        *,
        mode: str,
        representation: str,
        pins_compatible: bool,
        fallback_reason: str | None,
    ) -> tuple[dict[str, Any], bytes, int]:
        raw, encoding, data = self._payload(message, representation)
        envelope = {
            "format": DELIVERY_FORMAT,
            "interface_version": INTERFACE_VERSION,
            "product_label": PRODUCT_LABEL,
            "mode": mode,
            "representation": representation,
            "pins": self._pins_for(representation),
            "payload": {
                "encoding": encoding,
                "data": data,
                "sha256": _sha256(raw),
            },
            "safety": {
                "effect_authorized": False,
                "semantic_status": (
                    "canonical-locally-validated" if pins_compatible else "opaque-fallback-only"
                ),
                "fallback_reason": fallback_reason,
            },
        }
        return envelope, raw, len(data.encode("utf-8"))

    def negotiate(
        self,
        peer_capability: Mapping[str, Any],
        message: Mapping[str, Any],
        *,
        requested_mode: str = "bridge",
        expected_messages: int = 1,
        receiver_cache: ArtifactCache | None = None,
        preferred_representation: str | None = None,
    ) -> NegotiatedSession:
        """Purely plan the least-byte eligible representation for a message mix.

        Negotiation never mutates the receiver cache and never claims an artifact
        was transferred. Call :meth:`prepare_session_artifacts` to perform and
        receipt an explicit local in-memory transfer.
        """

        peer = _validate_capability(peer_capability)
        local = self.discover_capabilities()
        canonical = self.normalize_input(message, mode="fallback")
        if requested_mode not in _MODE_ORDER:
            raise IntegrationError("requested_mode must be bridge, native, or fallback")
        if type(expected_messages) is not int or not 1 <= expected_messages <= 1_000_000:
            raise IntegrationError("expected_messages must be an integer from 1 to 1,000,000")
        if preferred_representation is not None and preferred_representation not in _REPRESENTATION_ORDER:
            raise IntegrationError("preferred_representation is unknown")

        peer_modes = peer["modes"]
        fallback_reason: str | None = None
        if requested_mode == "native":
            local_native = local["modes"]["native"]
            peer_native = peer_modes["native"]
            if not local_native["supported"] or not peer_native["supported"]:
                mode = "fallback"
                fallback_reason = "native_evidence_unavailable"
            else:
                mode = "native"
        elif requested_mode == "bridge" and peer_modes["bridge"]["supported"]:
            mode = "bridge"
        else:
            mode = "fallback"
            if requested_mode != "fallback":
                fallback_reason = "requested_mode_unsupported"

        if mode == "fallback" and not peer_modes["fallback"]["supported"]:
            raise IntegrationError("peer disabled fallback required by this negotiation")

        peer_semantics = peer["semantics"]
        pins_compatible = (
            peer_semantics["language_version"] == LANGUAGE_VERSION
            and hmac.compare_digest(peer_semantics["capsule_sha256"], CAPSULE_SHA256)
        )
        if not pins_compatible:
            mode = "fallback"
            fallback_reason = "semantic_pin_mismatch"
            if not peer_modes["fallback"]["supported"]:
                raise IntegrationError("semantic pin mismatch and peer disabled fallback")

        local_representations = _representation_map(local)
        peer_representations = _representation_map(peer)
        if mode == "fallback":
            local_fallback_order = local["modes"]["fallback"]["order"]
            peer_fallback_order = peer_modes["fallback"]["order"]
            candidate_order = [
                identifier
                for identifier in local_fallback_order
                if identifier in peer_fallback_order
            ]
            if not pins_compatible:
                # JSON remains machine-readable but opaque under mismatched semantics.
                # Controlled text is not parsed across a semantic-version boundary.
                candidate_order = [
                    identifier
                    for identifier in candidate_order
                    if identifier == JSON_REPRESENTATION
                ]
        else:
            candidate_order = list(_REPRESENTATION_ORDER)

        common: list[str] = []
        for identifier in candidate_order:
            ours = local_representations.get(identifier)
            theirs = peer_representations.get(identifier)
            if ours is None or theirs is None:
                continue
            if (
                ours["relay_only"]
                or theirs["relay_only"]
                or not ours["can_encode"]
                or not ours["can_decode"]
                or not theirs["can_encode"]
                or not theirs["can_decode"]
            ):
                continue
            if identifier == JSON_REPRESENTATION and not _json_peer_eligible(
                canonical, peer.get("limits", {}) if isinstance(peer.get("limits"), Mapping) else {}
            ):
                continue
            if identifier == TERSE_REPRESENTATION:
                peer_limits = peer["limits"]
                if _contains_type(canonical, bytes) and not peer_limits[
                    "controlled_terse_bytes"
                ]:
                    continue
                if _contains_type(canonical, float) and not peer_limits[
                    "controlled_terse_float64"
                ]:
                    continue
            if identifier == WIRE_V02_REPRESENTATION:
                profile = theirs.get("profile")
                if not isinstance(profile, Mapping) or (
                    profile.get("profile_id") != PROFILE_ID
                    or profile.get("profile_capsule_sha256") != PROFILE_CAPSULE_SHA256
                    or profile.get("dictionary_id") != PROFILE_DICTIONARY_ID
                ):
                    continue
            common.append(identifier)

        if preferred_representation is not None:
            if preferred_representation not in common:
                raise IntegrationError("preferred representation is not mutually endpoint-decodable")
            common = [preferred_representation]
        if not common:
            raise IntegrationError("no mutually endpoint-decodable safe representation")

        advertised_cache = tuple(sorted(peer["cached_artifacts"]))
        if receiver_cache is not None and receiver_cache.digests != advertised_cache:
            raise IntegrationError(
                "receiver_cache must exactly match the peer's acknowledged cached_artifacts"
            )
        peer_cache = receiver_cache or ArtifactCache(advertised_cache)
        discovery_bytes = len(canonical_json_bytes(local)) + len(canonical_json_bytes(peer))

        estimates: list[tuple[int, int, int, str]] = []
        for identifier in common:
            envelope, _raw, _carrier = self._build_envelope(
                canonical,
                mode=mode,
                representation=identifier,
                pins_compatible=pins_compatible,
                fallback_reason=fallback_reason,
            )
            warm = len(canonical_json_bytes(envelope))
            cold = 0
            if pins_compatible:
                cold = 0 if peer_cache.contains(CAPSULE_SHA256) else CAPSULE_BYTES
                if identifier == WIRE_V02_REPRESENTATION and not peer_cache.contains(
                    PROFILE_CAPSULE_SHA256
                ):
                    cold += PROFILE_CAPSULE_BYTES
            total = discovery_bytes + cold + expected_messages * warm
            estimates.append((total, warm, _REPRESENTATION_ORDER.index(identifier), identifier))
        _total, warm, _order, selected = min(estimates)

        required: list[ColdArtifact] = []
        if pins_compatible:
            required.append(GRAMMAR_CAPSULE)
            if selected == WIRE_V02_REPRESENTATION:
                required.append(WIRE_V02_CAPSULE)
        planned: list[Mapping[str, Any]] = []
        for artifact in required:
            hit = peer_cache.contains(artifact.sha256)
            planned.append(
                {
                    "name": artifact.name,
                    "sha256": artifact.sha256,
                    "artifact_bytes": artifact.bytes,
                    "receiver_acknowledged_cache_hit": hit,
                    "planned_transfer_bytes": 0 if hit else artifact.bytes,
                }
            )
        peer_v02_profile = peer_representations.get(WIRE_V02_REPRESENTATION, {}).get(
            "profile", {}
        )
        session_body = {
            "mode": mode,
            "representation": selected,
            "local_source_id": self.source_id,
            "peer_source_id": peer["pins"]["source_id"],
            "peer_language_version": peer_semantics["language_version"],
            "peer_capsule_sha256": peer_semantics["capsule_sha256"],
            "peer_cached_artifacts": list(advertised_cache),
            "pins_compatible": pins_compatible,
            "fallback_reason": fallback_reason,
            "expected_messages": expected_messages,
            "planned_cold_artifacts": planned,
        }
        session_id = _sha256(canonical_json_bytes(session_body))
        return NegotiatedSession(
            session_id=session_id,
            mode=mode,
            representation=selected,
            local_source_id=self.source_id,
            peer_source_id=_require_source_id(peer["pins"]["source_id"]),
            peer_language_version=peer_semantics["language_version"],
            peer_capsule_sha256=peer_semantics["capsule_sha256"],
            peer_profile_id=(
                peer_v02_profile.get("profile_id")
                if selected == WIRE_V02_REPRESENTATION
                else None
            ),
            peer_profile_capsule_sha256=(
                peer_v02_profile.get("profile_capsule_sha256")
                if selected == WIRE_V02_REPRESENTATION
                else None
            ),
            peer_dictionary_id=(
                peer_v02_profile.get("dictionary_id")
                if selected == WIRE_V02_REPRESENTATION
                else None
            ),
            peer_cached_artifacts=advertised_cache,
            pins_compatible=pins_compatible,
            fallback_reason=fallback_reason,
            expected_messages=expected_messages,
            estimated_warm_envelope_bytes=warm,
            discovery_bytes=discovery_bytes,
            required_artifacts=tuple(required),
            planned_cold_artifacts=tuple(planned),
        )

    def _artifact_bytes(self, artifact: ColdArtifact) -> bytes:
        if artifact == GRAMMAR_CAPSULE:
            data = (REPOSITORY_ROOT / "urusilla_capsule_v0_1.json").read_bytes()
        elif artifact == WIRE_V02_CAPSULE:
            data = canonical_v02.encode_capsule(canonical_v02.DEFAULT_PROFILE)
        else:
            raise IntegrationError("session requested an unknown cold artifact")
        if len(data) != artifact.bytes or not hmac.compare_digest(
            _sha256(data), artifact.sha256
        ):
            raise IntegrationError(f"local artifact changed before transfer: {artifact.name}")
        return data

    def prepare_session_artifacts(
        self,
        session: NegotiatedSession,
        receiver_cache: ArtifactCache,
    ) -> SessionAccountingReceipt:
        """Perform explicit verified local transfer and issue one accounting token."""

        if session.local_source_id != self.source_id:
            raise IntegrationError("session local source pin differs from this SDK")
        if not isinstance(receiver_cache, ArtifactCache):
            raise IntegrationError("receiver_cache must be an ArtifactCache")
        if session.session_id in self._prepared_session_ids:
            raise IntegrationError("this session was already prepared/accounted")
        if receiver_cache.digests != session.peer_cached_artifacts:
            raise IntegrationError("receiver cache changed since negotiation; renegotiate")
        transfers = [
            receiver_cache.install_verified(artifact, self._artifact_bytes(artifact))
            for artifact in session.required_artifacts
        ]
        self._prepared_session_ids.add(session.session_id)
        return SessionAccountingReceipt(
            session_id=session.session_id,
            discovery_bytes=session.discovery_bytes,
            artifact_transfers=transfers,
        )

    def encode_delivery(
        self,
        message: Mapping[str, Any],
        session: NegotiatedSession,
        *,
        accounting_receipt: SessionAccountingReceipt | None = None,
    ) -> EncodedDelivery:
        canonical = self.normalize_input(message, mode="fallback")
        if session.local_source_id != self.source_id:
            raise IntegrationError("session local source pin differs from this SDK")
        envelope, raw, carrier_bytes = self._build_envelope(
            canonical,
            mode=session.mode,
            representation=session.representation,
            pins_compatible=session.pins_compatible,
            fallback_reason=session.fallback_reason,
        )
        envelope_bytes = len(canonical_json_bytes(envelope))
        discovery_bytes = 0
        transferred_artifact_bytes = 0
        if accounting_receipt is not None:
            if not isinstance(accounting_receipt, SessionAccountingReceipt):
                raise IntegrationError("accounting_receipt has the wrong type")
            discovery_bytes, transferred_artifact_bytes = accounting_receipt.consume(
                session.session_id
            )
        return EncodedDelivery(
            envelope=envelope,
            accounting=ByteAccounting(
                raw_payload_bytes=len(raw),
                carrier_payload_bytes=carrier_bytes,
                envelope_bytes=envelope_bytes,
                discovery_bytes=discovery_bytes,
                transferred_artifact_bytes=transferred_artifact_bytes,
            ),
        )

    def decode_delivery(
        self,
        envelope: Mapping[str, Any],
        session: NegotiatedSession,
    ) -> DecodedDelivery:
        if type(envelope) is not dict:
            raise IntegrationError("delivery envelope must be an object")
        expected_fields = {
            "format",
            "interface_version",
            "product_label",
            "mode",
            "representation",
            "pins",
            "payload",
            "safety",
        }
        if set(envelope) != expected_fields:
            raise IntegrationError("delivery envelope fields differ from the closed profile")
        if envelope.get("format") != DELIVERY_FORMAT or envelope.get("interface_version") != INTERFACE_VERSION:
            raise IntegrationError("unsupported delivery format or interface version")
        if envelope.get("product_label") != PRODUCT_LABEL:
            raise IntegrationError("delivery product label differs")
        if len(canonical_json_bytes(envelope)) > MAX_DELIVERY_BYTES:
            raise IntegrationError("delivery envelope exceeds the closed-profile byte limit")
        if envelope.get("mode") != session.mode or envelope.get("representation") != session.representation:
            raise IntegrationError("delivery differs from negotiated mode or representation")
        pins = envelope.get("pins")
        if not isinstance(pins, Mapping):
            raise IntegrationError("delivery pins must be an object")
        expected_pin_fields = {"language_version", "capsule_sha256", "source_id"}
        if session.representation == WIRE_V02_REPRESENTATION:
            expected_pin_fields |= {
                "profile_id",
                "profile_capsule_sha256",
                "dictionary_id",
            }
        if set(pins) != expected_pin_fields:
            raise IntegrationError("delivery pin fields differ from the closed profile")
        declared_source = _require_source_id(pins.get("source_id"), "delivery source_id")
        if not hmac.compare_digest(declared_source, session.peer_source_id):
            raise IntegrationError("delivery source_id differs from the pinned peer source_id")
        if (
            pins.get("language_version") != session.peer_language_version
            or pins.get("capsule_sha256") != session.peer_capsule_sha256
        ):
            raise IntegrationError("delivery semantic pins differ from the exact peer offer")
        if session.representation == WIRE_V02_REPRESENTATION and (
            pins.get("profile_id") != session.peer_profile_id
            or pins.get("profile_capsule_sha256")
            != session.peer_profile_capsule_sha256
            or pins.get("dictionary_id") != session.peer_dictionary_id
        ):
            raise IntegrationError("delivery v0.2 profile pins differ from the negotiated profile")

        safety = envelope.get("safety")
        expected_status = (
            "canonical-locally-validated"
            if session.pins_compatible
            else "opaque-fallback-only"
        )
        if not isinstance(safety, Mapping) or set(safety) != {
            "effect_authorized",
            "semantic_status",
            "fallback_reason",
        }:
            raise IntegrationError("delivery safety fields differ from the closed profile")
        if safety != {
            "effect_authorized": False,
            "semantic_status": expected_status,
            "fallback_reason": session.fallback_reason,
        }:
            raise IntegrationError("delivery must explicitly remain non-effect-authorizing")
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping) or set(payload) != {"encoding", "data", "sha256"}:
            raise IntegrationError("delivery payload fields differ from the closed profile")
        data = payload.get("data")
        if type(data) is not str or len(data.encode("utf-8")) > MAX_DELIVERY_BYTES:
            raise IntegrationError("delivery payload data type or size is invalid")
        digest = _require_sha256(payload.get("sha256"), "payload.sha256")
        representation = session.representation
        if representation in {WIRE_V01_REPRESENTATION, WIRE_V02_REPRESENTATION}:
            if payload.get("encoding") != "base64":
                raise IntegrationError("wire payload must use Base64 in JSON")
            try:
                raw = base64.b64decode(data, validate=True)
            except Exception as exc:
                raise IntegrationError("wire payload contains invalid Base64") from exc
            if len(raw) > MAX_DELIVERY_BYTES or base64.b64encode(raw).decode("ascii") != data:
                raise IntegrationError("wire payload is oversized or non-canonical Base64")
        else:
            expected_encoding = (
                "utf-8-json" if representation == JSON_REPRESENTATION else "utf-8-controlled-english"
            )
            if payload.get("encoding") != expected_encoding:
                raise IntegrationError("text payload encoding differs from its representation")
            raw = data.encode("utf-8")
        if not hmac.compare_digest(_sha256(raw), digest):
            raise IntegrationError("delivery payload digest mismatch")

        if session.mode == "fallback" and not session.pins_compatible:
            if representation != JSON_REPRESENTATION:
                raise IntegrationError("pin-mismatch fallback must use structured JSON")
            opaque = _load_canonical_json(raw)
            return DecodedDelivery(
                message=None,
                opaque_payload=opaque,
                mode=session.mode,
                representation=representation,
                source_id=declared_source,
                semantic_valid=False,
                effect_authorized=False,
            )

        try:
            if representation == JSON_REPRESENTATION:
                value = _load_canonical_json(raw)
                message = canonical_v01.normalize_message(value)
            elif representation == TERSE_REPRESENTATION:
                message = decode_terse_english(data)
            elif representation == WIRE_V01_REPRESENTATION:
                message = canonical_v01.decode_message(raw)
            elif representation == WIRE_V02_REPRESENTATION:
                registry = canonical_v02.ProfileRegistry()
                registry.register_capsule(
                    canonical_v02.encode_capsule(canonical_v02.DEFAULT_PROFILE)
                )
                message = canonical_v02.decode_message(raw, registry)
            else:
                raise IntegrationError("unsupported negotiated representation")
        except canonical_v01.UrusillaError as exc:
            raise IntegrationError(f"canonical payload decode failed: {exc}") from exc
        return DecodedDelivery(
            message=message,
            opaque_payload=None,
            mode=session.mode,
            representation=representation,
            source_id=declared_source,
            semantic_valid=True,
            effect_authorized=False,
        )

    def to_a2a_message(
        self,
        delivery: EncodedDelivery,
        *,
        message_id: str,
        role: str = "ROLE_USER",
    ) -> dict[str, Any]:
        """Return a local A2A-v1-shaped Message using a private experimental marker."""

        if role not in {"ROLE_USER", "ROLE_AGENT"}:
            raise IntegrationError("A2A role must be ROLE_USER or ROLE_AGENT")
        if type(message_id) is not str or not message_id:
            raise IntegrationError("A2A message_id must be non-empty")
        source_id = _require_source_id(delivery.envelope["pins"]["source_id"])
        return {
            "role": role,
            "parts": [{"data": {"urusilla_delivery": dict(delivery.envelope)}}],
            "messageId": message_id,
            "extensions": [A2A_LOCAL_EXTENSION],
            "metadata": {
                A2A_LOCAL_EXTENSION: {
                    "source_id": source_id,
                    "status": "private-local-experimental",
                }
            },
        }

    def from_a2a_message(
        self,
        wrapper: Mapping[str, Any],
        session: NegotiatedSession,
        *,
        activated_extensions: Sequence[str],
        a2a_version: str,
    ) -> DecodedDelivery:
        if a2a_version != A2A_VERSION:
            raise IntegrationError("unsupported A2A version")
        if isinstance(activated_extensions, (str, bytes, bytearray)) or A2A_LOCAL_EXTENSION not in activated_extensions:
            raise IntegrationError("private local A2A marker was not explicitly activated")
        if not isinstance(wrapper, Mapping) or wrapper.get("extensions") != [A2A_LOCAL_EXTENSION]:
            raise IntegrationError("A2A Message does not declare exactly the local marker")
        if set(wrapper) != {"role", "parts", "messageId", "extensions", "metadata"}:
            raise IntegrationError("A2A Message fields differ from the local closed profile")
        if wrapper.get("role") not in {"ROLE_USER", "ROLE_AGENT"}:
            raise IntegrationError("A2A Message role is invalid")
        if type(wrapper.get("messageId")) is not str or not wrapper["messageId"]:
            raise IntegrationError("A2A Message messageId must be non-empty")
        metadata = wrapper.get("metadata")
        if not isinstance(metadata, Mapping) or set(metadata) != {A2A_LOCAL_EXTENSION} or not isinstance(metadata.get(A2A_LOCAL_EXTENSION), Mapping):
            raise IntegrationError("A2A Message omits local provenance metadata")
        local_metadata = metadata[A2A_LOCAL_EXTENSION]
        if set(local_metadata) != {"source_id", "status"} or local_metadata.get("status") != "private-local-experimental":
            raise IntegrationError("A2A local provenance metadata differs from its closed profile")
        source_id = _require_source_id(local_metadata.get("source_id"))
        if not hmac.compare_digest(source_id, session.peer_source_id):
            raise IntegrationError("A2A metadata source_id differs from the peer pin")
        parts = wrapper.get("parts")
        if not isinstance(parts, list) or len(parts) != 1 or set(parts[0]) != {"data"}:
            raise IntegrationError("A2A local profile requires exactly one data Part")
        data = parts[0]["data"]
        if not isinstance(data, Mapping) or set(data) != {"urusilla_delivery"}:
            raise IntegrationError("A2A data Part differs from the local closed profile")
        decoded = self.decode_delivery(data["urusilla_delivery"], session)
        if decoded.message is not None and wrapper.get("messageId") != decoded.message["id"]:
            raise IntegrationError("A2A messageId differs from the semantic message id")
        if (
            decoded.message is None
            and isinstance(decoded.opaque_payload, Mapping)
            and type(decoded.opaque_payload.get("id")) is str
            and wrapper.get("messageId") != decoded.opaque_payload["id"]
        ):
            raise IntegrationError("A2A messageId differs from the opaque JSON message id")
        return decoded

    def to_mcp_result(self, delivery: EncodedDelivery) -> dict[str, Any]:
        """Return an MCP-friendly result shape without claiming MCP conformance."""

        opaque = delivery.envelope["safety"]["semantic_status"] == "opaque-fallback-only"
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Opaque structured fallback; semantic pins differ and no authority is granted."
                        if opaque
                        else "Locally validated semantic delivery; no authority is granted."
                    ),
                }
            ],
            "structuredContent": {"urusilla_delivery": dict(delivery.envelope)},
            "isError": False,
        }

    def from_mcp_result(
        self, result: Mapping[str, Any], session: NegotiatedSession
    ) -> DecodedDelivery:
        if not isinstance(result, Mapping) or result.get("isError") is not False:
            raise IntegrationError("MCP-friendly result is missing or marked as an error")
        if set(result) != {"content", "structuredContent", "isError"}:
            raise IntegrationError("MCP-friendly result fields differ from the closed profile")
        content = result.get("content")
        if (
            not isinstance(content, list)
            or len(content) != 1
            or not isinstance(content[0], Mapping)
            or set(content[0]) != {"type", "text"}
            or content[0].get("type") != "text"
            or type(content[0].get("text")) is not str
        ):
            raise IntegrationError("MCP-friendly content differs from the local profile")
        structured = result.get("structuredContent")
        if not isinstance(structured, Mapping) or set(structured) != {"urusilla_delivery"}:
            raise IntegrationError("MCP-friendly structuredContent differs from the closed profile")
        return self.decode_delivery(structured["urusilla_delivery"], session)

    @staticmethod
    def canonical_a2a_v01_adapter() -> Any:
        """Expose the pinned root A2A v0.1 adapter for callers that need it.

        The adapter remains separate because it is hard-wired to wire v0.1 and
        its private historical extension URI.  It must not decode v0.2.
        """

        return canonical_a2a
