#!/usr/bin/env python3
"""Post-cutover external OOD reconfirmation for the frozen v0.8 candidate.

The ``freeze`` stage acquires and content-addresses independently authored
official examples, constructs a source-preserving corpus, and seals candidate
source digests, tokenizer identities, hypotheses, and metrics.  It rejects any
run in which a project candidate was imported first.  The ``measure`` stage
verifies that sealed manifest before importing the unchanged v0.8 candidate or
loading a tokenizer.

The source objects are the exact archived bytes used by the earlier external
confirmation.  This run is therefore a post-cutover reconfirmation, not a new
external-corpus preregistration.  It is a serialization and record-contract
evaluation over already-typed messages.  It does not measure model
comprehension, task utility, energy, adoption, universal generalization, or
state of the art.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen
import uuid

import yaml


MANIFEST_FORMAT = "external-ood-v08-post-cutover-reconfirmation-manifest-v2"
MEASUREMENT_FORMAT = "external-ood-v08-post-cutover-reconfirmation-measurement-v2"
ROOT = Path(__file__).resolve().parent
CACHE_ROOT = ROOT / "work" / "external_ood_v08_confirmatory"
SOURCE_CACHE = CACHE_ROOT / "sources"
EVIDENCE_ROOT = ROOT / "evidence" / "external_ood_v08_confirmatory"
EVIDENCE_CACHE_PREFIX = CACHE_ROOT.relative_to(ROOT)
MAX_SOURCE_BYTES = 4 * 1024 * 1024
TIMING_WARMUPS = 1
TIMING_REPEATS = 3
MESSAGE_NAMESPACE = uuid.UUID("464cfbe5-22f6-55d1-817a-9f846fb29f7e")
EXPECTED_SELECTION_CONTRACT_SHA256 = (
    "fcb90039b2a7e193e3b274b6a4cefcb7cf851b116e397bcb721e0b268c5c36b0"
)
FORBIDDEN_PRIOR_PROTOCOL_TERMS = (
    "activitystreams",
    "cloudevents",
    "modelcontextprotocol",
    "stix",
)


@dataclass(frozen=True)
class SourceSelection:
    path: str
    extractor: str


@dataclass(frozen=True)
class SourceGroup:
    protocol_id: str
    organization: str
    standard: str
    repository: str
    revision: str
    license_name: str
    license_path: str
    selections: tuple[SourceSelection, ...]

    def raw_url(self, path: str) -> str:
        return (
            f"https://raw.githubusercontent.com/{self.repository}/"
            f"{self.revision}/{path}"
        )

    def blob_url(self, path: str) -> str:
        return (
            f"https://github.com/{self.repository}/blob/"
            f"{self.revision}/{path}"
        )


_OPENAPI_PATHS = (
    "_archive_/schemas/v3.0/pass/api-with-examples.yaml",
    "_archive_/schemas/v3.0/pass/callback-example.yaml",
    "_archive_/schemas/v3.0/pass/link-example.yaml",
    "_archive_/schemas/v3.0/pass/petstore-expanded.yaml",
    "_archive_/schemas/v3.0/pass/petstore.yaml",
    "_archive_/schemas/v3.0/pass/uspto.yaml",
)

_ASYNCAPI_PATHS = (
    "examples/adeo-kafka-request-reply-asyncapi.yml",
    "examples/anyof-asyncapi.yml",
    "examples/application-headers-asyncapi.yml",
    "examples/correlation-id-asyncapi.yml",
    "examples/gitter-streaming-asyncapi.yml",
    "examples/kraken-websocket-request-reply-message-filter-in-reply-asyncapi.yml",
    "examples/kraken-websocket-request-reply-multiple-channels-asyncapi.yml",
    "examples/mercure-asyncapi.yml",
    "examples/oneof-asyncapi.yml",
    "examples/operation-security-asyncapi.yml",
    "examples/rpc-client-asyncapi.yml",
    "examples/rpc-server-asyncapi.yml",
    "examples/simple-asyncapi.yml",
    "examples/slack-rtm-asyncapi.yml",
    "examples/streetlights-kafka-asyncapi.yml",
    "examples/streetlights-mqtt-asyncapi.yml",
    "examples/streetlights-operation-security-asyncapi.yml",
    "examples/websocket-gemini-asyncapi.yml",
    "examples/social-media/backend/asyncapi.yaml",
    "examples/social-media/comments-service/asyncapi.yaml",
    "examples/social-media/frontend/asyncapi.yaml",
    "examples/social-media/notification-service/asyncapi.yaml",
    "examples/social-media/public-api/asyncapi.yaml",
)


SOURCE_GROUPS = (
    SourceGroup(
        protocol_id="openapi-3.0-official-pass-examples",
        organization="OpenAPI Initiative",
        standard="OpenAPI Specification 3.0",
        repository="OAI/OpenAPI-Specification",
        revision="6d6084fb9ca086dc6db3de9e4089d5fb33c753df",
        license_name="Apache-2.0",
        license_path="LICENSE",
        selections=tuple(SourceSelection(path, "yaml_openapi_document") for path in _OPENAPI_PATHS),
    ),
    SourceGroup(
        protocol_id="asyncapi-3.1-official-examples",
        organization="AsyncAPI Initiative",
        standard="AsyncAPI Specification 3.1",
        repository="asyncapi/spec",
        revision="3afe09b227f408fc4547e294c6cf90dcd280f4db",
        license_name="Apache-2.0",
        license_path="LICENSE",
        selections=tuple(SourceSelection(path, "yaml_asyncapi_document") for path in _ASYNCAPI_PATHS),
    ),
    SourceGroup(
        protocol_id="w3c-wot-thing-description-1.1-validation-examples",
        organization="World Wide Web Consortium",
        standard="Web of Things Thing Description 1.1",
        repository="w3c/wot-thing-description",
        revision="967c957a63c87c71bf55801cffe0694df2efc575",
        license_name="W3C Software and Document License",
        license_path="LICENSE.md",
        selections=(
            SourceSelection(
                "validation/resources/thing-descriptions.js",
                "wot_valid_thing_descriptions",
            ),
        ),
    ),
    SourceGroup(
        protocol_id="opentelemetry-protocol-json-examples",
        organization="OpenTelemetry",
        standard="OpenTelemetry Protocol JSON examples",
        repository="open-telemetry/opentelemetry-proto",
        revision="ac2c4b5d1f3a6079de62f9afec860158ecc8af09",
        license_name="Apache-2.0",
        license_path="LICENSE",
        selections=(
            SourceSelection("examples/events.json", "otel_log_records"),
            SourceSelection("examples/logs.json", "otel_log_records"),
            SourceSelection("examples/metrics.json", "otel_metrics"),
            SourceSelection("examples/trace.json", "otel_spans"),
        ),
    ),
)

EXPECTED_PARTITION_COUNTS = {
    "openapi-3.0-official-pass-examples": 6,
    "asyncapi-3.1-official-examples": 23,
    "w3c-wot-thing-description-1.1-validation-examples": 6,
    "opentelemetry-protocol-json-examples": 7,
}
EXPECTED_MESSAGE_COUNT = sum(EXPECTED_PARTITION_COUNTS.values())

CANDIDATE_SOURCE_FILES = (
    "urusilla_transparent_fallback_v08.py",
    "urusilla_generalization_surface_v06.py",
    "urusilla_terse_english_benchmark.py",
    "urusilla_token_surface_v04.py",
    "urusilla_benchmark.py",
    "urusilla.py",
    "urusilla_token_surface_holdout.py",
    "urusilla_token_surface_v03.py",
    "urusilla_tokenizer_benchmark.py",
    "urusilla_wire_v02.py",
)

FROZEN_TOKENIZERS = {
    "cl100k_base": {
        "implementation": "tiktoken==0.11.0",
        "fingerprint": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    },
    "o200k_base": {
        "implementation": "tiktoken==0.11.0",
        "fingerprint": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    },
    "qwen2_5_7b_instruct": {
        "implementation": "tokenizers==0.21.4",
        "revision": "a09a35458c702b33eeacc393d103063234e8bc28",
        "fingerprint": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    },
    "mistral_7b_instruct_v03": {
        "implementation": "tokenizers==0.21.4",
        "revision": "c170c708c41dac9275d15a8fff4eca08d52bab71",
        "fingerprint": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
    },
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sequence_digest_bytes(items: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(len(item).to_bytes(8, "big"))
        digest.update(item)
    return digest.hexdigest()


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "urusilla-v08-confirmatory/1"})
    with urlopen(request, timeout=120) as response:
        data = response.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise RuntimeError(f"source exceeds {MAX_SOURCE_BYTES} bytes: {url}")
    return data


def _load_archive_index(archive_root: Path) -> tuple[dict[tuple[str, str], bytes], dict[str, bytes]]:
    """Load exact source and license bytes from a prior evidence package.

    The manifest remains the authority for mapping a source path to a
    content-addressed file.  A filename alone is never trusted.  Conflicting
    archived bytes for the same pinned source fail closed.
    """

    source_index: dict[tuple[str, str], bytes] = {}
    license_index: dict[str, bytes] = {}
    manifests = sorted(archive_root.glob("premeasurement-manifest-*.json"))
    if not manifests:
        raise RuntimeError(f"no archived premeasurement manifest under {archive_root}")
    for manifest_path in manifests:
        raw = manifest_path.read_bytes()
        # The cutover migration changed protocol-name strings in the legacy
        # package and thereby invalidated that package's historical manifest
        # filename.  It is used only as a path-to-digest index here.  Every
        # referenced source and license byte sequence is still verified below,
        # and the newly produced manifest is content-addressed normally.
        manifest = json.loads(raw.decode("utf-8"))
        selection = manifest.get("source_selection")
        if not isinstance(selection, Mapping):
            raise RuntimeError(f"archived manifest lacks source selection: {manifest_path}")
        for record in selection.get("source_groups", []):
            cache_file = Path(str(record["cache_file"]))
            try:
                relative = cache_file.relative_to(EVIDENCE_CACHE_PREFIX)
            except ValueError as exc:
                raise RuntimeError(f"unexpected archived source path: {cache_file}") from exc
            cached = archive_root / relative
            data = cached.read_bytes()
            expected = str(record["source_file_sha256"])
            if sha256_bytes(data) != expected or cached.name.split(".", 1)[0] != expected:
                raise RuntimeError(f"archived source digest mismatch: {cached}")
            key = (str(record["protocol_id"]), str(record["source_path"]))
            prior = source_index.setdefault(key, data)
            if prior != data:
                raise RuntimeError(f"conflicting archived source bytes for {key}")
        for record in selection.get("licenses", []):
            cache_file = Path(str(record["cache_file"]))
            try:
                relative = cache_file.relative_to(EVIDENCE_CACHE_PREFIX)
            except ValueError as exc:
                raise RuntimeError(f"unexpected archived license path: {cache_file}") from exc
            cached = archive_root / relative
            data = cached.read_bytes()
            expected = str(record["license_file_sha256"])
            if sha256_bytes(data) != expected or cached.name.split(".", 1)[0] != expected:
                raise RuntimeError(f"archived license digest mismatch: {cached}")
            key = str(record["protocol_id"])
            prior = license_index.setdefault(key, data)
            if prior != data:
                raise RuntimeError(f"conflicting archived license bytes for {key}")
    return source_index, license_index


def _cache_source(data: bytes, suffix: str) -> Path:
    SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    target = SOURCE_CACHE / f"{sha256_bytes(data)}{suffix}"
    if target.exists() and target.read_bytes() != data:
        raise RuntimeError(f"content-address collision at {target}")
    if not target.exists():
        target.write_bytes(data)
    return target


def _json_pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _require_mapping(value: Any, description: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{description} is not a string-keyed mapping")
    canonical_json_bytes(value)
    return value


def _otel_records(
    value: Mapping[str, Any],
    outer_key: str,
    scope_key: str,
    record_key: str,
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    result: list[tuple[str, Mapping[str, Any]]] = []
    outer = value.get(outer_key)
    if not isinstance(outer, list):
        raise RuntimeError(f"OpenTelemetry example lacks {outer_key}")
    for outer_index, outer_value in enumerate(outer):
        outer_mapping = _require_mapping(outer_value, f"{outer_key} item")
        scopes = outer_mapping.get(scope_key)
        if not isinstance(scopes, list):
            raise RuntimeError(f"OpenTelemetry example lacks {scope_key}")
        for scope_index, scope_value in enumerate(scopes):
            scope_mapping = _require_mapping(scope_value, f"{scope_key} item")
            records = scope_mapping.get(record_key)
            if not isinstance(records, list):
                raise RuntimeError(f"OpenTelemetry example lacks {record_key}")
            for record_index, record in enumerate(records):
                result.append(
                    (
                        f"/{outer_key}/{outer_index}/{scope_key}/{scope_index}/"
                        f"{record_key}/{record_index}",
                        _require_mapping(record, f"{record_key} item"),
                    )
                )
    if not result:
        raise RuntimeError(f"OpenTelemetry example has no {record_key}")
    return tuple(result)


def extract_objects(extractor: str, data: bytes) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    if extractor in {"yaml_openapi_document", "yaml_asyncapi_document"}:
        parsed = _require_mapping(yaml.safe_load(data), "YAML example")
        required_key = "openapi" if extractor == "yaml_openapi_document" else "asyncapi"
        if not isinstance(parsed.get(required_key), str):
            raise RuntimeError(f"official YAML example lacks {required_key}")
        return (("$", parsed),)
    text = data.decode("utf-8", errors="strict")
    if extractor == "wot_valid_thing_descriptions":
        marker = "const validTDs = "
        start = text.index(marker) + len(marker)
        end = text.index(";\nconst invalidTDs", start)
        parsed = json.loads(text[start:end])
        if not isinstance(parsed, list) or not parsed:
            raise RuntimeError("Web of Things validTDs is not a non-empty array")
        return tuple(
            (f"/validTDs/{index}", _require_mapping(value, "validTDs item"))
            for index, value in enumerate(parsed)
        )
    parsed = _require_mapping(json.loads(text), "OpenTelemetry JSON example")
    if extractor == "otel_log_records":
        return _otel_records(parsed, "resourceLogs", "scopeLogs", "logRecords")
    if extractor == "otel_metrics":
        return _otel_records(parsed, "resourceMetrics", "scopeMetrics", "metrics")
    if extractor == "otel_spans":
        return _otel_records(parsed, "resourceSpans", "scopeSpans", "spans")
    raise RuntimeError(f"unknown extractor {extractor!r}")


def build_wrapped_message(record: Mapping[str, Any], logical_clock: int) -> dict[str, Any]:
    protocol_id = str(record["protocol_id"])
    source_locator = str(record["source_locator"])
    object_json = str(record["source_object_canonical_json"])
    object_digest = str(record["source_object_sha256"])
    identity = f"{protocol_id}\x00{source_locator}\x00{object_digest}"
    return {
        "id": str(uuid.uuid5(MESSAGE_NAMESPACE, "message\x00" + identity)),
        "session": str(uuid.uuid5(MESSAGE_NAMESPACE, "session\x00" + protocol_id)),
        "sender": f"urn:external-confirmatory:source:{protocol_id}",
        "recipients": ["urn:external-confirmatory:receiver"],
        "act": "ASSERT",
        "reply_to": None,
        "schema": "urn:external-confirmatory:schema:source-object:v2",
        "logical_clock": logical_clock,
        "expires_ms": 0,
        "confidence_ppm": None,
        "expected": [],
        "body": {
            "kind": "x:external-confirmatory-record",
            "protocol_id": protocol_id,
            "source_uri": record["source_uri"],
            "source_revision": record["source_revision"],
            "source_path": record["source_path"],
            "source_file_sha256": record["source_file_sha256"],
            "source_locator": source_locator,
            "source_object_sha256": object_digest,
            "source_json": object_json,
        },
        "meta": {},
    }


def _partition_digest(messages: Sequence[Mapping[str, Any]], indices: Sequence[int]) -> str:
    return sequence_digest_bytes(canonical_json_bytes(messages[index]) for index in indices)


def _candidate_source_digests() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in CANDIDATE_SOURCE_FILES:
        path = ROOT / name
        if not path.is_file():
            raise RuntimeError(f"missing frozen candidate source: {name}")
        result[name] = sha256_file(path)
    result[Path(__file__).name] = sha256_file(Path(__file__))
    return result


def _verify_candidate_source_digests(
    expected: Mapping[str, str],
    *,
    evidence_root: Path | None = None,
    allow_archived_sources: bool = False,
) -> str:
    observed = _candidate_source_digests()
    if set(observed) != set(expected):
        raise RuntimeError("the frozen candidate source set changed after freeze")
    if observed == expected:
        return "current"
    if allow_archived_sources and evidence_root is not None:
        archive_roots = tuple(dict.fromkeys((evidence_root, EVIDENCE_ROOT)))
        for archive_root in archive_roots:
            candidate_root = archive_root / "candidate_sources"
            archived_observed = {
                name: sha256_file(candidate_root / name)
                for name in expected
                if (candidate_root / name).is_file()
            }
            if archived_observed == expected:
                return "archived"
    raise RuntimeError("a frozen candidate or evaluation source changed after freeze")


def freeze(*, source_archive: Path | None = None) -> tuple[Path, str, Mapping[str, Any]]:
    imported = tuple(
        name
        for name in sys.modules
        if name == "urusilla" or name.startswith("urusilla_")
    )
    if imported:
        raise RuntimeError(f"project candidates were imported before freeze: {imported}")

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    source_manifest: list[dict[str, Any]] = []
    license_manifest: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    clocks: Counter[str] = Counter()
    archived_sources: dict[tuple[str, str], bytes] = {}
    archived_licenses: dict[str, bytes] = {}
    if source_archive is not None:
        archived_sources, archived_licenses = _load_archive_index(source_archive)

    for group in SOURCE_GROUPS:
        lowered = (group.protocol_id + " " + group.repository).lower()
        if any(term in lowered for term in FORBIDDEN_PRIOR_PROTOCOL_TERMS):
            raise RuntimeError(f"source group reuses a forbidden prior protocol: {group.protocol_id}")
        if source_archive is None:
            license_data = _fetch(group.raw_url(group.license_path))
        else:
            try:
                license_data = archived_licenses[group.protocol_id]
            except KeyError as exc:
                raise RuntimeError(
                    f"archive lacks the pinned license for {group.protocol_id}"
                ) from exc
        license_cache = _cache_source(license_data, ".license")
        license_manifest.append(
            {
                "protocol_id": group.protocol_id,
                "license_name": group.license_name,
                "license_uri": group.blob_url(group.license_path),
                "license_file_sha256": sha256_bytes(license_data),
                "license_file_bytes": len(license_data),
                "cache_file": str(license_cache.relative_to(ROOT)),
                "note": "Repository license metadata is recorded as source evidence, not legal advice.",
            }
        )
        for selection in group.selections:
            if source_archive is None:
                raw = _fetch(group.raw_url(selection.path))
            else:
                try:
                    raw = archived_sources[(group.protocol_id, selection.path)]
                except KeyError as exc:
                    raise RuntimeError(
                        f"archive lacks pinned source {group.protocol_id}:{selection.path}"
                    ) from exc
            cache = _cache_source(raw, Path(selection.path).suffix or ".source")
            extracted = extract_objects(selection.extractor, raw)
            file_digest = sha256_bytes(raw)
            source_manifest.append(
                {
                    "protocol_id": group.protocol_id,
                    "organization": group.organization,
                    "standard": group.standard,
                    "repository": group.repository,
                    "revision": group.revision,
                    "source_path": selection.path,
                    "source_uri": group.blob_url(selection.path),
                    "download_uri": group.raw_url(selection.path),
                    "source_file_sha256": file_digest,
                    "source_file_bytes": len(raw),
                    "extractor": selection.extractor,
                    "extracted_objects": len(extracted),
                    "cache_file": str(cache.relative_to(ROOT)),
                }
            )
            for locator, value in extracted:
                object_bytes = canonical_json_bytes(value)
                clocks[group.protocol_id] += 1
                records.append(
                    {
                        "protocol_id": group.protocol_id,
                        "source_revision": group.revision,
                        "source_path": selection.path,
                        "source_uri": group.blob_url(selection.path),
                        "source_file_sha256": file_digest,
                        "source_locator": locator,
                        "source_object_sha256": sha256_bytes(object_bytes),
                        "source_object_canonical_json": object_bytes.decode("utf-8"),
                        "logical_clock": clocks[group.protocol_id],
                    }
                )

    observed_counts = dict(Counter(str(record["protocol_id"]) for record in records))
    if observed_counts != EXPECTED_PARTITION_COUNTS:
        raise RuntimeError(f"official example count changed: {observed_counts}")
    if len(records) != EXPECTED_MESSAGE_COUNT or EXPECTED_MESSAGE_COUNT < 40:
        raise RuntimeError("reconfirmation corpus must contain at least 40 records")

    identities = {
        (record["protocol_id"], record["source_path"], record["source_locator"], record["source_object_sha256"])
        for record in records
    }
    if len(identities) != len(records):
        raise RuntimeError("reconfirmation source selection contains a duplicate record identity")

    messages = tuple(build_wrapped_message(record, int(record["logical_clock"])) for record in records)
    corpus_bytes = canonical_json_bytes(messages)
    corpus_digest = sha256_bytes(corpus_bytes)
    corpus_path = CACHE_ROOT / f"corpus-{corpus_digest}.json"
    if corpus_path.exists() and corpus_path.read_bytes() != corpus_bytes:
        raise RuntimeError("content-addressed corpus path contains different bytes")
    if not corpus_path.exists():
        corpus_path.write_bytes(corpus_bytes)

    partition_indices: dict[str, list[int]] = {"all": list(range(len(messages)))}
    for index, record in enumerate(records):
        partition_indices.setdefault(str(record["protocol_id"]), []).append(index)
    partitions = {
        name: {
            "message_indices": indices,
            "message_count": len(indices),
            "message_sequence_sha256": _partition_digest(messages, indices),
        }
        for name, indices in partition_indices.items()
    }

    manifest: dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": "post_cutover_reconfirmation_frozen_before_v08_or_tokenizer_import_and_before_token_measurement",
        "external_data_role": "post_cutover_reconfirmation_only_no_training_no_tuning",
        "reconfirmation_reason": (
            "The Urusilla name and wire-identity cutover changed candidate source bytes. "
            "The same archived external objects are therefore re-frozen against the new "
            "candidate identities before any post-cutover token measurement."
        ),
        "source_selection": {
            "acquisition": {
                "mode": "archived_exact_bytes" if source_archive is not None else "pinned_upstream_download",
                "archive_root": "evidence/external_ood_v08_confirmatory" if source_archive is not None else None,
                "network_used": source_archive is None,
                "caveat": (
                    "Archived exact source bytes from the earlier confirmation were reused. "
                    "This is not a new external-corpus selection or preregistration."
                    if source_archive is not None
                    else "Pinned upstream bytes were downloaded before candidate import or measurement."
                ),
            },
            "rule": (
                "Select every declared complete official OpenAPI and AsyncAPI example document, "
                "every valid W3C Thing Description fixture, and every OpenTelemetry signal record "
                "at the declared paths and revisions. Selection and ordering use source structure only; "
                "no project codec or tokenizer result was observed."
            ),
            "forbidden_prior_corpus_families": [
                "W3C ActivityStreams",
                "CNCF CloudEvents",
                "Model Context Protocol",
                "OASIS STIX",
            ],
            "source_groups": source_manifest,
            "licenses": license_manifest,
            "yaml_parser": {
                "distribution": "PyYAML",
                "version": importlib.metadata.version("PyYAML"),
                "mode": "yaml.safe_load followed by strict JSON-domain validation",
            },
        },
        "transform": {
            "rule_version": "source-bound-wrapper-v2",
            "steps": [
                "Decode selected UTF-8 JSON, JavaScript JSON-array fixtures, or YAML with the declared deterministic extractor.",
                "Require every selected object to be a string-keyed JSON-domain mapping.",
                "Serialize each object as sorted minified UTF-8 JSON with non-ASCII characters unescaped and non-finite numbers forbidden.",
                "Store the complete canonical external JSON losslessly in source_json inside one quarantined ASSERT extension node.",
                "Preserve the immutable source URI and revision, exact path and locator, source-file digest, and canonical-object digest.",
                "Derive message and session UUIDs with UUIDv5 and assign one-based logical clocks per standard partition.",
            ],
            "project_authored_envelope_choices": {
                "act": "ASSERT",
                "body_kind": "x:external-confirmatory-record",
                "schema": "urn:external-confirmatory:schema:source-object:v2",
                "recipient": "urn:external-confirmatory:receiver",
                "reply_to": None,
                "expires_ms": 0,
                "confidence_ppm": None,
                "expected": [],
                "meta": {},
                "caveat": (
                    "The conservative string wrapper repeats source metadata and is not a native "
                    "mapping for any selected standard."
                ),
            },
        },
        "corpus": {
            "message_count": len(messages),
            "corpus_file": str(corpus_path.relative_to(ROOT)),
            "corpus_file_bytes": len(corpus_bytes),
            "corpus_file_sha256": corpus_digest,
            "message_sequence_sha256": sequence_digest_bytes(
                canonical_json_bytes(message) for message in messages
            ),
            "partitions": partitions,
            "records": [
                {key: value for key, value in record.items() if key != "source_object_canonical_json"}
                for record in records
            ],
        },
        "frozen_candidate": {
            "name": "Urusilla transparent fallback v0.8",
            "candidate_modes": ["terse", "json", "optimized", "v04"],
            "plain_modes": ["terse", "json"],
            "compact_modes": ["optimized", "v04"],
            "selection_contract_sha256": EXPECTED_SELECTION_CONTRACT_SHA256,
            "source_sha256": _candidate_source_digests(),
            "modification_rule": (
                "Use the already-frozen v0.8 implementation, strict-smaller compact eligibility, "
                "exact cold planner, profiles, tokenizers, tie order, integrity framing, and thresholds unchanged."
            ),
        },
        "tokenizers": FROZEN_TOKENIZERS,
        "measurement_plan": {
            "timing_warmups": TIMING_WARMUPS,
            "timing_repeats": TIMING_REPEATS,
            "metrics": [
                "raw Controlled Terse English and sorted minified JSON receiver tokens",
                "bound and standalone selected receiver tokens by message, partition, and tokenizer",
                "cold artifact tokens and complete cold-session totals",
                "positive receiver-token regret against the better plain fallback",
                "strict aggregate cold improvement versus tie",
                "compact-mode strict-win counts",
                "direct payload and bound and standalone record exactness and deterministic re-encoding",
                "bound mode, sequence, and integrity-tag bytes as separate components",
                "standalone prefix, mode, sequence, integrity tag, and delimiter bytes as separate components",
                "mode, sequence, payload, tag, and expected-sequence mutation rejection",
                "encode or select and decode p50 and p95 latency plus cold-plan session latency",
            ],
            "latency_boundary": (
                "Paths perform unequal work. Adaptive encoding constructs and tokenizes all candidates; "
                "plain encoding does not. Wall-clock latency is implementation and machine specific."
            ),
        },
        "hypotheses": {
            "H1_exact_deterministic": (
                "Every direct candidate payload and every selected bound and standalone record must "
                "recover the exact canonical message and reproduce deterministically."
            ),
            "H2_bound_zero_positive_regret": (
                "For every message and tokenizer, and for each complete cold partition, bound transport "
                "must have exactly zero positive receiver-token regret against raw Controlled Terse "
                "English and raw sorted JSON. Negative deltas are reported separately as improvements."
            ),
            "H3_metadata_complete": (
                "All bound and standalone mode, sequence, integrity, and framing metadata bytes must be "
                "accounted for in separate named components and sum to the complete record bytes."
            ),
            "H4_standalone_matched_integrity": (
                "Standalone selection must have zero positive receiver-token regret against a plain-only "
                "baseline using the identical standalone integrity envelope; unmatched excess over raw "
                "plain text remains visible."
            ),
            "H5_strict_compact_rule": (
                "A compact mode may be selected only when its complete receiver-token count is strictly "
                "below the best eligible plain mode. The observed strict-win count, including zero, is retained."
            ),
            "H6_aggregate_cold_outcome": (
                "Report whether aggregate bound cold tokens strictly improve on raw plain tokens or merely "
                "tie for every tokenizer; no new percentage-savings threshold is introduced."
            ),
            "H7_integrity_mutations": (
                "Every deterministic bound and standalone mode, sequence, payload, tag, and wrong-sequence "
                "trial must be rejected."
            ),
        },
        "threshold_policy": (
            "No v0.8 threshold, profile, tokenizer, source path, or tie rule may be tuned after this freeze. "
            "The frozen strict-smaller compact gate and exact cold minimum remain unchanged."
        ),
        "claim_boundary": (
            "This post-cutover rerun can reconfirm serialization and record-contract invariants on the "
            "same archived official-example corpus. It cannot establish task utility, model understanding, "
            "energy savings, universal "
            "generalization, external adoption, or a state-of-the-art result."
        ),
    }
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_digest = sha256_bytes(manifest_bytes)
    manifest_path = CACHE_ROOT / f"premeasurement-manifest-{manifest_digest}.json"
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
        raise RuntimeError("content-addressed manifest path contains different bytes")
    if not manifest_path.exists():
        manifest_path.write_bytes(manifest_bytes)
    return manifest_path, manifest_digest, manifest


def _load_content_addressed(path: Path, prefix: str) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if path.name != f"{prefix}-{digest}.json":
        raise RuntimeError(f"content-addressed filename mismatch for {path}")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a JSON object")
    return value, digest


def _resolve_frozen_file(declared: str, evidence_root: Path | None) -> Path:
    relative = Path(declared)
    if evidence_root is not None:
        try:
            evidence_relative = relative.relative_to(EVIDENCE_CACHE_PREFIX)
        except ValueError:
            pass
        else:
            evidence_path = (evidence_root / evidence_relative).resolve()
            try:
                evidence_path.relative_to(evidence_root.resolve())
            except ValueError:
                evidence_path = None
            if evidence_path is not None and evidence_path.is_file():
                return evidence_path
    project_path = (ROOT / relative).resolve()
    try:
        project_path.relative_to(ROOT)
    except ValueError as exc:
        raise RuntimeError(f"frozen evidence path escapes the project root: {declared}") from exc
    if project_path.is_file():
        return project_path
    raise RuntimeError(f"missing frozen evidence file: {declared}")


def _verify_frozen_inputs(
    manifest: Mapping[str, Any],
    *,
    evidence_root: Path | None = None,
    allow_archived_sources: bool = False,
) -> tuple[tuple[dict[str, Any], ...], str]:
    if manifest.get("format") != MANIFEST_FORMAT:
        raise RuntimeError("unknown premeasurement manifest format")
    if manifest.get("stage") != (
        "post_cutover_reconfirmation_frozen_before_v08_or_tokenizer_import_"
        "and_before_token_measurement"
    ):
        raise RuntimeError("manifest does not declare the required premeasurement stage")
    if manifest.get("external_data_role") != (
        "post_cutover_reconfirmation_only_no_training_no_tuning"
    ):
        raise RuntimeError("manifest does not preserve the reconfirmation-only role")
    candidate_source = _verify_candidate_source_digests(
        manifest["frozen_candidate"]["source_sha256"],
        evidence_root=evidence_root,
        allow_archived_sources=allow_archived_sources,
    )
    if manifest["frozen_candidate"]["selection_contract_sha256"] != EXPECTED_SELECTION_CONTRACT_SHA256:
        raise RuntimeError("the frozen v0.8 selection contract identity changed")

    for source in manifest["source_selection"]["source_groups"]:
        cached = _resolve_frozen_file(source["cache_file"], evidence_root)
        if sha256_file(cached) != source["source_file_sha256"]:
            raise RuntimeError(f"cached source digest changed: {source['source_path']}")
        extracted = extract_objects(str(source["extractor"]), cached.read_bytes())
        if len(extracted) != source["extracted_objects"]:
            raise RuntimeError(f"cached source extraction changed: {source['source_path']}")
    for license_record in manifest["source_selection"]["licenses"]:
        cached = _resolve_frozen_file(license_record["cache_file"], evidence_root)
        if sha256_file(cached) != license_record["license_file_sha256"]:
            raise RuntimeError(f"cached license digest changed: {license_record['protocol_id']}")

    corpus_info = manifest["corpus"]
    corpus_path = _resolve_frozen_file(corpus_info["corpus_file"], evidence_root)
    corpus_bytes = corpus_path.read_bytes()
    if len(corpus_bytes) != corpus_info["corpus_file_bytes"]:
        raise RuntimeError("frozen corpus byte count changed")
    if sha256_bytes(corpus_bytes) != corpus_info["corpus_file_sha256"]:
        raise RuntimeError("frozen corpus digest changed")
    raw = json.loads(corpus_bytes.decode("utf-8"))
    if not isinstance(raw, list) or len(raw) != EXPECTED_MESSAGE_COUNT:
        raise RuntimeError("frozen corpus structure or count changed")
    messages = tuple(_require_mapping(value, "wrapped message") for value in raw)
    if sequence_digest_bytes(canonical_json_bytes(value) for value in messages) != corpus_info["message_sequence_sha256"]:
        raise RuntimeError("frozen corpus sequence digest changed")
    observed_partitions = {
        name: info["message_count"]
        for name, info in corpus_info["partitions"].items()
        if name != "all"
    }
    if observed_partitions != EXPECTED_PARTITION_COUNTS:
        raise RuntimeError("frozen partition counts changed")
    return messages, candidate_source


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def _time_indexed_path(
    messages: Sequence[Mapping[str, Any]],
    encoded: Sequence[Any],
    encoder: Callable[[Mapping[str, Any], int], Any],
    decoder: Callable[[Any, int], Mapping[str, Any]],
) -> dict[str, int]:
    for _ in range(TIMING_WARMUPS):
        for index, message in enumerate(messages, 1):
            encoder(message, index)
        for index, value in enumerate(encoded, 1):
            decoder(value, index)
    encode_samples: list[int] = []
    decode_samples: list[int] = []
    for _ in range(TIMING_REPEATS):
        for index, message in enumerate(messages, 1):
            start = time.perf_counter_ns()
            encoder(message, index)
            encode_samples.append(time.perf_counter_ns() - start)
        for index, value in enumerate(encoded, 1):
            start = time.perf_counter_ns()
            decoder(value, index)
            decode_samples.append(time.perf_counter_ns() - start)
    return {
        "samples_per_direction": len(encode_samples),
        "encode_p50_ns": int(statistics.median(encode_samples)),
        "encode_p95_ns": _nearest(encode_samples, 0.95),
        "decode_p50_ns": int(statistics.median(decode_samples)),
        "decode_p95_ns": _nearest(decode_samples, 0.95),
    }


def _time_session(call: Callable[[], Any]) -> dict[str, int]:
    for _ in range(TIMING_WARMUPS):
        call()
    samples: list[int] = []
    for _ in range(TIMING_REPEATS):
        start = time.perf_counter_ns()
        call()
        samples.append(time.perf_counter_ns() - start)
    return {
        "samples": len(samples),
        "p50_ns": int(statistics.median(samples)),
        "p95_ns": _nearest(samples, 0.95),
    }


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _mutated_character(text: str, position: int) -> str:
    replacement = "X" if text[position] != "X" else "Y"
    return text[:position] + replacement + text[position + 1 :]


def _expect_rejection(call: Callable[[], Any], exceptions: tuple[type[BaseException], ...]) -> bool:
    try:
        call()
    except exceptions:
        return True
    return False


def _metadata_accounting(
    bound_selected: Sequence[Any],
    standalone_selected: Sequence[Any],
    bound_records: Sequence[bytes],
    standalone_records: Sequence[str],
    v08: Any,
) -> dict[str, Any]:
    bound_payload_bytes = sum(
        len(item.candidate.payload.encode("utf-8")) for item in bound_selected
    )
    standalone_payload_bytes = sum(
        len(item.candidate.payload.encode("utf-8")) for item in standalone_selected
    )
    count = len(bound_selected)
    if len(standalone_selected) != count:
        raise RuntimeError("bound and standalone metadata rows have different counts")
    bound = {
        "records": count,
        "receiver_payload_bytes": bound_payload_bytes,
        "mode_bytes": count,
        "sequence_bytes": count * v08.SEQUENCE_BYTES,
        "integrity_tag_bytes": count * v08.AUTH_TAG_BYTES,
    }
    bound["separate_metadata_bytes"] = (
        bound["mode_bytes"] + bound["sequence_bytes"] + bound["integrity_tag_bytes"]
    )
    bound["complete_record_bytes"] = sum(len(record) for record in bound_records)
    bound["component_sum_matches_complete"] = (
        bound["receiver_payload_bytes"] + bound["separate_metadata_bytes"]
        == bound["complete_record_bytes"]
    )

    standalone = {
        "records": count,
        "payload_bytes": standalone_payload_bytes,
        "prefix_bytes": count * len(v08.STANDALONE_PREFIX.encode("ascii")),
        "mode_bytes": count,
        "sequence_hex_bytes": count * v08.STANDALONE_SEQUENCE_CHARACTERS,
        "integrity_tag_base64url_bytes": count * v08.STANDALONE_TAG_CHARACTERS,
        "delimiter_bytes": count,
    }
    standalone["inline_metadata_bytes"] = sum(
        standalone[key]
        for key in (
            "prefix_bytes",
            "mode_bytes",
            "sequence_hex_bytes",
            "integrity_tag_base64url_bytes",
            "delimiter_bytes",
        )
    )
    standalone["complete_receiver_text_bytes"] = sum(
        len(record.encode("utf-8")) for record in standalone_records
    )
    standalone["component_sum_matches_complete"] = (
        standalone["payload_bytes"] + standalone["inline_metadata_bytes"]
        == standalone["complete_receiver_text_bytes"]
    )
    return {"bound": bound, "standalone": standalone}


def _integrity_trials(
    bound_records: Sequence[bytes],
    standalone_records: Sequence[str],
    alias_profile: Any,
    v08: Any,
    decode_error: type[BaseException],
    validation_error: type[BaseException],
) -> dict[str, dict[str, int]]:
    exceptions = (decode_error, validation_error)
    attempted = {"bound": 0, "standalone": 0}
    rejected = {"bound": 0, "standalone": 0}
    for sequence, record in enumerate(bound_records, 1):
        payload_start = 1 + v08.SEQUENCE_BYTES
        payload_end = len(record) - v08.AUTH_TAG_BYTES
        variants = []
        changed_mode = bytearray(record)
        changed_mode[0] = 255
        variants.append(bytes(changed_mode))
        changed_sequence = bytearray(record)
        changed_sequence[1] ^= 1
        variants.append(bytes(changed_sequence))
        changed_payload = bytearray(record)
        changed_payload[payload_start + (payload_end - payload_start) // 2] ^= 1
        variants.append(bytes(changed_payload))
        changed_tag = bytearray(record)
        changed_tag[-1] ^= 1
        variants.append(bytes(changed_tag))
        for variant in variants:
            attempted["bound"] += 1
            rejected["bound"] += _expect_rejection(
                lambda value=variant, expected=sequence: v08.open_bound_record(
                    value, alias_profile, expected_sequence=expected
                ),
                exceptions,
            )
        attempted["bound"] += 1
        rejected["bound"] += _expect_rejection(
            lambda value=record, expected=sequence + 1: v08.open_bound_record(
                value, alias_profile, expected_sequence=expected
            ),
            exceptions,
        )

    for sequence, record in enumerate(standalone_records, 1):
        mode_position = len(v08.STANDALONE_PREFIX)
        sequence_position = mode_position + 1
        tag_position = sequence_position + v08.STANDALONE_SEQUENCE_CHARACTERS
        payload_position = v08.STANDALONE_HEADER_CHARACTERS
        variants = (
            record[:mode_position] + "Z" + record[mode_position + 1 :],
            _mutated_character(record, sequence_position),
            _mutated_character(record, payload_position + (len(record) - payload_position) // 2),
            _mutated_character(record, tag_position),
        )
        for variant in variants:
            attempted["standalone"] += 1
            rejected["standalone"] += _expect_rejection(
                lambda value=variant, expected=sequence: v08.open_standalone(
                    value, alias_profile, expected_sequence=expected
                ),
                exceptions,
            )
        attempted["standalone"] += 1
        rejected["standalone"] += _expect_rejection(
            lambda value=record, expected=sequence + 1: v08.open_standalone(
                value, alias_profile, expected_sequence=expected
            ),
            exceptions,
        )
    return {
        contract: {"attempted": attempted[contract], "rejected": rejected[contract]}
        for contract in ("bound", "standalone")
    }


def _deterministic_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the repeat-stable subset of a measurement.

    Wall-clock timestamps, platform strings, and latency are deliberately
    excluded.  Everything that supports exactness, fallback, token, metadata,
    or integrity claims remains bound into this digest.
    """

    return {
        "premeasurement_manifest_sha256": value["premeasurement_manifest_sha256"],
        "corpus": value["corpus"],
        "candidate": value["candidate"],
        "tokenizers": value["tokenizers"],
        "exactness": value["exactness"],
        "profiles": value["profiles"],
        "partitions": value["partitions"],
        "compact_strict_wins": value["compact_strict_wins"],
        "integrity_totals": value["integrity_totals"],
        "hypothesis_outcomes": value["hypothesis_outcomes"],
        "claim_boundary": value["claim_boundary"],
    }


def measure(
    manifest_path: Path,
    *,
    run_label: str = "primary",
) -> tuple[Path, str, Mapping[str, Any]]:
    manifest, manifest_digest = _load_content_addressed(
        manifest_path, "premeasurement-manifest"
    )
    raw_messages, _candidate_source = _verify_frozen_inputs(manifest)

    # These imports intentionally occur only after the complete frozen
    # manifest, source cache, corpus, and candidate source digests pass.
    import urusilla_transparent_fallback_v08 as v08
    from urusilla import DecodeError, ValidationError, normalize_message
    from urusilla_tokenizer_benchmark import default_asset_root, load_tokenizer_profiles

    profiles = load_tokenizer_profiles(default_asset_root())
    observed_tokenizers = {
        profile.key: {
            "display_name": profile.display_name,
            "implementation": profile.implementation,
            "vocabulary_size": profile.vocabulary_size,
            "fingerprint": profile.fingerprint,
        }
        for profile in profiles
    }
    if tuple(observed_tokenizers) != tuple(FROZEN_TOKENIZERS):
        raise RuntimeError("the four frozen tokenizers are required in declared order")
    for key, expected in FROZEN_TOKENIZERS.items():
        if observed_tokenizers[key]["fingerprint"] != expected["fingerprint"]:
            raise RuntimeError(f"frozen tokenizer fingerprint changed: {key}")
    v08.verify_frozen_inputs(profiles)
    if v08.selection_contract_sha256() != EXPECTED_SELECTION_CONTRACT_SHA256:
        raise RuntimeError("the imported v0.8 selection contract changed")

    messages = tuple(normalize_message(message) for message in raw_messages)
    if messages != raw_messages:
        raise RuntimeError("the frozen wrapper corpus is not already canonical")
    alias_profile = v08.build_alias_profile()
    prepared = tuple(v08.prepare_message(message, alias_profile) for message in messages)

    direct_exactness: dict[str, dict[str, int]] = {}
    for mode in v08.MODE_ORDER:
        exact = deterministic = 0
        for item in prepared:
            payload = item.texts[mode]
            decoded = v08.decode_payload(mode, payload, alias_profile)
            exact += decoded == item.message
            rebuilt = v08.prepare_message(decoded, alias_profile).texts[mode]
            deterministic += rebuilt == payload
        direct_exactness[mode] = {
            "exact": exact,
            "deterministic": deterministic,
            "trials": len(messages),
        }

    profile_results: dict[str, Any] = {}
    runtime_state: dict[str, Any] = {}
    integrity_totals = {
        "bound": {"attempted": 0, "rejected": 0},
        "standalone": {"attempted": 0, "rejected": 0},
    }
    selected_exactness: dict[str, dict[str, dict[str, int]]] = {
        "bound": {},
        "standalone": {},
    }
    total_strict_compact_wins = {"bound": 0, "standalone": 0}

    for profile in profiles:
        bound_selections = tuple(
            v08.select_prepared(item, profile, contract="bound", sequence=index)
            for index, item in enumerate(prepared, 1)
        )
        standalone_selections = tuple(
            v08.select_prepared(item, profile, contract="standalone", sequence=index)
            for index, item in enumerate(prepared, 1)
        )
        bound_records = tuple(
            v08.encode_bound_record(
                selection.candidate.mode,
                index,
                selection.candidate.payload,
            )
            for index, selection in enumerate(bound_selections, 1)
        )
        standalone_records = tuple(
            v08.encode_standalone(
                selection.candidate.mode,
                index,
                selection.candidate.payload,
            )
            for index, selection in enumerate(standalone_selections, 1)
        )
        bound_cold = v08.plan_cold_session(
            prepared, profile, alias_profile, contract="bound"
        )
        standalone_cold = v08.plan_cold_session(
            prepared, profile, alias_profile, contract="standalone"
        )

        raw_terse_tokens = sum(profile.count(item.texts["terse"]) for item in prepared)
        raw_json_tokens = sum(profile.count(item.texts["json"]) for item in prepared)
        raw_best_per_message = sum(
            min(profile.count(item.texts["terse"]), profile.count(item.texts["json"]))
            for item in prepared
        )
        bound_warm_tokens = sum(selection.candidate.tokens for selection in bound_selections)
        standalone_warm_tokens = sum(
            selection.candidate.tokens for selection in standalone_selections
        )
        warm_positive_regret = sum(
            max(0, selection.candidate.tokens - selection.plain_best.tokens)
            for selection in bound_selections
        )

        for contract, selections in (
            ("bound", bound_selections),
            ("standalone", standalone_selections),
        ):
            total_strict_compact_wins[contract] += sum(
                selection.candidate.mode in v08.COMPACT_MODES
                for selection in selections
            )
            if any(
                selection.candidate.mode in v08.COMPACT_MODES
                and selection.candidate.tokens >= selection.plain_best.tokens
                for selection in selections
            ):
                raise RuntimeError("a compact mode won without a strict complete-token improvement")

        bound_exact = bound_deterministic = 0
        standalone_exact = standalone_deterministic = 0
        for index, (message, bound_selection, standalone_selection, bound_record, standalone_record) in enumerate(
            zip(
                messages,
                bound_selections,
                standalone_selections,
                bound_records,
                standalone_records,
                strict=True,
            ),
            1,
        ):
            bound_mode, bound_payload, bound_decoded = v08.open_bound_record(
                bound_record, alias_profile, expected_sequence=index
            )
            bound_exact += bound_decoded == message
            rebuilt_bound_selection = v08.select_prepared(
                v08.prepare_message(bound_decoded, alias_profile),
                profile,
                contract="bound",
                sequence=index,
            )
            rebuilt_bound = v08.encode_bound_record(
                rebuilt_bound_selection.candidate.mode,
                index,
                rebuilt_bound_selection.candidate.payload,
            )
            bound_deterministic += (
                bound_mode == bound_selection.candidate.mode
                and bound_payload == bound_selection.candidate.payload
                and rebuilt_bound == bound_record
            )

            standalone_mode, standalone_payload, standalone_decoded = v08.open_standalone(
                standalone_record, alias_profile, expected_sequence=index
            )
            standalone_exact += standalone_decoded == message
            rebuilt_standalone_selection = v08.select_prepared(
                v08.prepare_message(standalone_decoded, alias_profile),
                profile,
                contract="standalone",
                sequence=index,
            )
            rebuilt_standalone = v08.encode_standalone(
                rebuilt_standalone_selection.candidate.mode,
                index,
                rebuilt_standalone_selection.candidate.payload,
            )
            standalone_deterministic += (
                standalone_mode == standalone_selection.candidate.mode
                and standalone_payload == standalone_selection.candidate.payload
                and rebuilt_standalone == standalone_record
            )

        selected_exactness["bound"][profile.key] = {
            "exact": bound_exact,
            "deterministic": bound_deterministic,
            "trials": len(messages),
        }
        selected_exactness["standalone"][profile.key] = {
            "exact": standalone_exact,
            "deterministic": standalone_deterministic,
            "trials": len(messages),
        }

        integrity = _integrity_trials(
            bound_records,
            standalone_records,
            alias_profile,
            v08,
            DecodeError,
            ValidationError,
        )
        for contract in integrity_totals:
            integrity_totals[contract]["attempted"] += integrity[contract]["attempted"]
            integrity_totals[contract]["rejected"] += integrity[contract]["rejected"]
        metadata = _metadata_accounting(
            bound_selections,
            standalone_selections,
            bound_records,
            standalone_records,
            v08,
        )

        bound_delta = bound_cold.selected.total_tokens - raw_best_per_message
        standalone_matched_delta = (
            standalone_cold.selected.total_tokens - standalone_cold.plain_total_tokens
        )
        profile_results[profile.key] = {
            "raw_receiver_tokens": {
                "controlled_terse_english": raw_terse_tokens,
                "sorted_minified_json": raw_json_tokens,
                "better_whole_session_plain": min(raw_terse_tokens, raw_json_tokens),
                "best_plain_per_message": raw_best_per_message,
            },
            "bound": {
                "warm_receiver_tokens": bound_warm_tokens,
                "warm_positive_regret_tokens": warm_positive_regret,
                "cold_artifact_tokens": bound_cold.selected.cold_tokens,
                "cold_message_tokens": bound_cold.selected.message_tokens,
                "cold_total_tokens": bound_cold.selected.total_tokens,
                "cold_delta_vs_raw_best_per_message": bound_delta,
                "cold_positive_regret_tokens": max(0, bound_delta),
                "aggregate_outcome": "strict_improvement" if bound_delta < 0 else "tie" if bound_delta == 0 else "regression",
                "mode_counts_warm": dict(Counter(item.candidate.mode for item in bound_selections)),
                "mode_counts_cold": dict(Counter(item.mode for item in bound_cold.selected.choices)),
                "structured_artifact_activated": bound_cold.selected.structured,
                "optimized_artifacts_activated": bound_cold.selected.optimized,
            },
            "standalone": {
                "warm_receiver_tokens": standalone_warm_tokens,
                "cold_artifact_tokens": standalone_cold.selected.cold_tokens,
                "cold_message_tokens": standalone_cold.selected.message_tokens,
                "cold_total_tokens": standalone_cold.selected.total_tokens,
                "matched_plain_integrity_total_tokens": standalone_cold.plain_total_tokens,
                "matched_plain_delta_tokens": standalone_matched_delta,
                "matched_plain_positive_regret_tokens": max(0, standalone_matched_delta),
                "unmatched_delta_vs_raw_best_per_message": standalone_cold.selected.total_tokens
                - raw_best_per_message,
                "mode_counts_warm": dict(Counter(item.candidate.mode for item in standalone_selections)),
                "mode_counts_cold": dict(Counter(item.mode for item in standalone_cold.selected.choices)),
                "structured_artifact_activated": standalone_cold.selected.structured,
                "optimized_artifacts_activated": standalone_cold.selected.optimized,
            },
            "metadata_bytes": metadata,
            "integrity": integrity,
        }
        runtime_state[profile.key] = {
            "bound_selections": bound_selections,
            "standalone_selections": standalone_selections,
            "bound_records": bound_records,
            "standalone_records": standalone_records,
        }

    partition_results: dict[str, Any] = {}
    for partition, info in manifest["corpus"]["partitions"].items():
        indices = tuple(int(index) for index in info["message_indices"])
        subset_prepared = tuple(prepared[index] for index in indices)
        partition_results[partition] = {"message_count": len(indices), "tokenizers": {}}
        for profile in profiles:
            raw_terse = sum(profile.count(item.texts["terse"]) for item in subset_prepared)
            raw_json = sum(profile.count(item.texts["json"]) for item in subset_prepared)
            raw_best = sum(
                min(profile.count(item.texts["terse"]), profile.count(item.texts["json"]))
                for item in subset_prepared
            )
            bound_plan = v08.plan_cold_session(
                subset_prepared, profile, alias_profile, contract="bound"
            )
            standalone_plan = v08.plan_cold_session(
                subset_prepared, profile, alias_profile, contract="standalone"
            )
            bound_delta = bound_plan.selected.total_tokens - raw_best
            standalone_delta = (
                standalone_plan.selected.total_tokens - standalone_plan.plain_total_tokens
            )
            partition_results[partition]["tokenizers"][profile.key] = {
                "raw_terse_tokens": raw_terse,
                "raw_json_tokens": raw_json,
                "raw_best_per_message_tokens": raw_best,
                "bound_cold_total_tokens": bound_plan.selected.total_tokens,
                "bound_cold_delta_tokens": bound_delta,
                "bound_positive_regret_tokens": max(0, bound_delta),
                "bound_mode_counts": dict(Counter(item.mode for item in bound_plan.selected.choices)),
                "standalone_cold_total_tokens": standalone_plan.selected.total_tokens,
                "standalone_matched_plain_tokens": standalone_plan.plain_total_tokens,
                "standalone_matched_delta_tokens": standalone_delta,
                "standalone_matched_positive_regret_tokens": max(0, standalone_delta),
                "standalone_mode_counts": dict(Counter(item.mode for item in standalone_plan.selected.choices)),
            }

    latency: dict[str, Any] = {}
    terse_values = tuple(item.texts["terse"] for item in prepared)
    json_values = tuple(item.texts["json"] for item in prepared)
    latency["raw_controlled_terse_english"] = _time_indexed_path(
        messages,
        terse_values,
        lambda message, _index: v08.encode_terse_english(message),
        lambda value, _index: v08.decode_terse_english(value),
    )
    latency["raw_sorted_minified_json"] = _time_indexed_path(
        messages,
        json_values,
        lambda message, _index: v08.json_encode(message).decode("utf-8"),
        lambda value, _index: v08.json_decode(value.encode("utf-8")),
    )
    latency["bound"] = {}
    latency["standalone"] = {}
    latency["cold_plan_session"] = {}
    for profile in profiles:
        state = runtime_state[profile.key]

        def encode_bound(message: Mapping[str, Any], sequence: int, selected_profile: Any = profile) -> bytes:
            item = v08.prepare_message(message, alias_profile)
            selected = v08.select_prepared(
                item, selected_profile, contract="bound", sequence=sequence
            ).candidate
            return v08.encode_bound_record(selected.mode, sequence, selected.payload)

        def decode_bound(record: bytes, sequence: int) -> Mapping[str, Any]:
            return v08.open_bound_record(
                record, alias_profile, expected_sequence=sequence
            )[2]

        def encode_standalone(message: Mapping[str, Any], sequence: int, selected_profile: Any = profile) -> str:
            item = v08.prepare_message(message, alias_profile)
            selected = v08.select_prepared(
                item, selected_profile, contract="standalone", sequence=sequence
            ).candidate
            return v08.encode_standalone(selected.mode, sequence, selected.payload)

        def decode_standalone(text: str, sequence: int) -> Mapping[str, Any]:
            return v08.open_standalone(
                text, alias_profile, expected_sequence=sequence
            )[2]

        latency["bound"][profile.key] = _time_indexed_path(
            messages,
            state["bound_records"],
            encode_bound,
            decode_bound,
        )
        latency["standalone"][profile.key] = _time_indexed_path(
            messages,
            state["standalone_records"],
            encode_standalone,
            decode_standalone,
        )
        latency["cold_plan_session"][profile.key] = {
            "bound": _time_session(
                lambda selected_profile=profile: v08.plan_cold_session(
                    prepared, selected_profile, alias_profile, contract="bound"
                )
            ),
            "standalone": _time_session(
                lambda selected_profile=profile: v08.plan_cold_session(
                    prepared, selected_profile, alias_profile, contract="standalone"
                )
            ),
        }

    exact_rows = list(direct_exactness.values()) + [
        row for contract in selected_exactness.values() for row in contract.values()
    ]
    h1 = all(
        row["exact"] == row["trials"] and row["deterministic"] == row["trials"]
        for row in exact_rows
    )
    h2 = all(
        result["bound"]["warm_positive_regret_tokens"] == 0
        and result["bound"]["cold_positive_regret_tokens"] == 0
        for result in profile_results.values()
    ) and all(
        values["bound_positive_regret_tokens"] == 0
        for partition in partition_results.values()
        for values in partition["tokenizers"].values()
    )
    h3 = all(
        result["metadata_bytes"][contract]["component_sum_matches_complete"]
        for result in profile_results.values()
        for contract in ("bound", "standalone")
    )
    h4 = all(
        result["standalone"]["matched_plain_positive_regret_tokens"] == 0
        for result in profile_results.values()
    ) and all(
        values["standalone_matched_positive_regret_tokens"] == 0
        for partition in partition_results.values()
        for values in partition["tokenizers"].values()
    )
    h5 = all(
        selection.candidate.mode not in v08.COMPACT_MODES
        or selection.candidate.tokens < selection.plain_best.tokens
        for state in runtime_state.values()
        for contract in ("bound_selections", "standalone_selections")
        for selection in state[contract]
    )
    h6_by_tokenizer = {
        key: result["bound"]["aggregate_outcome"] for key, result in profile_results.items()
    }
    h7 = all(
        values["attempted"] == values["rejected"] for values in integrity_totals.values()
    )

    measurement: dict[str, Any] = {
        "format": MEASUREMENT_FORMAT,
        "run_label": run_label,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "premeasurement_manifest_sha256": manifest_digest,
        "premeasurement_manifest_file": str(manifest_path.relative_to(ROOT)),
        "candidate_sources_verified_unchanged_before_import": True,
        "external_corpus_used_for_training_or_tuning": False,
        "candidate_or_threshold_modified_after_freeze": False,
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "PyYAML": _package_version("PyYAML"),
            "tiktoken": _package_version("tiktoken"),
            "tokenizers": _package_version("tokenizers"),
        },
        "corpus": {
            "message_count": len(messages),
            "corpus_file_sha256": manifest["corpus"]["corpus_file_sha256"],
            "message_sequence_sha256": manifest["corpus"]["message_sequence_sha256"],
            "partitions": {
                key: value["message_count"]
                for key, value in manifest["corpus"]["partitions"].items()
            },
        },
        "candidate": {
            "selection_contract_sha256": v08.selection_contract_sha256(),
            "source_sha256": manifest["frozen_candidate"]["source_sha256"],
        },
        "tokenizers": observed_tokenizers,
        "exactness": {
            "direct_payloads": direct_exactness,
            "selected_records": selected_exactness,
            "total_exact": sum(row["exact"] for row in exact_rows),
            "total_deterministic": sum(row["deterministic"] for row in exact_rows),
            "total_trials": sum(row["trials"] for row in exact_rows),
        },
        "profiles": profile_results,
        "partitions": partition_results,
        "compact_strict_wins": total_strict_compact_wins,
        "integrity_totals": integrity_totals,
        "latency": latency,
        "hypothesis_outcomes": {
            "H1_exact_deterministic": h1,
            "H2_bound_zero_positive_regret": h2,
            "H3_metadata_complete": h3,
            "H4_standalone_matched_integrity": h4,
            "H5_strict_compact_rule": h5,
            "H6_aggregate_cold_outcome_by_tokenizer": h6_by_tokenizer,
            "H7_integrity_mutations": h7,
        },
        "claim_boundary": manifest["claim_boundary"],
    }
    measurement["deterministic_outcome_sha256"] = sha256_bytes(
        canonical_json_bytes(_deterministic_outcome(measurement))
    )
    measurement_bytes = canonical_json_bytes(measurement)
    measurement_digest = sha256_bytes(measurement_bytes)
    measurement_path = CACHE_ROOT / f"measurement-{measurement_digest}.json"
    if measurement_path.exists() and measurement_path.read_bytes() != measurement_bytes:
        raise RuntimeError("content-addressed measurement path contains different bytes")
    if not measurement_path.exists():
        measurement_path.write_bytes(measurement_bytes)
    return measurement_path, measurement_digest, measurement


def verify(manifest_path: Path, measurement_path: Path | None = None) -> dict[str, Any]:
    manifest, manifest_digest = _load_content_addressed(
        manifest_path, "premeasurement-manifest"
    )
    messages, candidate_source = _verify_frozen_inputs(
        manifest,
        evidence_root=manifest_path.parent,
        allow_archived_sources=True,
    )
    result: dict[str, Any] = {
        "manifest_sha256": manifest_digest,
        "message_count": len(messages),
        "manifest_verified": True,
        "frozen_candidate_source": candidate_source,
    }
    if measurement_path is not None:
        measurement, measurement_digest = _load_content_addressed(
            measurement_path, "measurement"
        )
        if measurement.get("format") != MEASUREMENT_FORMAT:
            raise RuntimeError("unknown measurement format")
        if measurement.get("premeasurement_manifest_sha256") != manifest_digest:
            raise RuntimeError("measurement is bound to a different manifest")
        observed_outcome = sha256_bytes(
            canonical_json_bytes(_deterministic_outcome(measurement))
        )
        if measurement.get("deterministic_outcome_sha256") != observed_outcome:
            raise RuntimeError("measurement deterministic-outcome digest changed")
        result.update(
            measurement_sha256=measurement_digest,
            measurement_verified=True,
            deterministic_outcome_sha256=observed_outcome,
            hypothesis_outcomes=measurement["hypothesis_outcomes"],
        )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser(
        "freeze", help="freeze sources, corpus, candidate identities, and metrics"
    )
    freeze_parser.add_argument(
        "--source-archive",
        type=Path,
        help="reuse exact sources and licenses from a verified prior evidence package",
    )
    measure_parser = subparsers.add_parser(
        "measure", help="measure the unchanged v0.8 candidate after freeze"
    )
    measure_parser.add_argument("--manifest", type=Path, required=True)
    measure_parser.add_argument("--run-label", default="primary")
    verify_parser = subparsers.add_parser(
        "verify", help="verify content-addressed manifest and optional measurement"
    )
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--measurement", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "freeze":
        path, digest, manifest = freeze(
            source_archive=args.source_archive.resolve() if args.source_archive else None
        )
        result = {
            "manifest_file": str(path.relative_to(ROOT)),
            "manifest_sha256": digest,
            "message_count": manifest["corpus"]["message_count"],
            "partitions": {
                key: value["message_count"]
                for key, value in manifest["corpus"]["partitions"].items()
            },
            "candidate_imported": False,
            "tokens_measured": False,
        }
    elif args.command == "measure":
        path, digest, measurement = measure(
            args.manifest.resolve(), run_label=args.run_label
        )
        result = {
            "measurement_file": str(path.relative_to(ROOT)),
            "measurement_sha256": digest,
            "premeasurement_manifest_sha256": measurement[
                "premeasurement_manifest_sha256"
            ],
            "message_count": measurement["corpus"]["message_count"],
            "compact_strict_wins": measurement["compact_strict_wins"],
            "deterministic_outcome_sha256": measurement[
                "deterministic_outcome_sha256"
            ],
            "hypothesis_outcomes": measurement["hypothesis_outcomes"],
        }
    else:
        result = verify(
            args.manifest.resolve(),
            args.measurement.resolve() if args.measurement else None,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
