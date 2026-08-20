#!/usr/bin/env python3
"""Retained external out-of-domain serialization evaluation.

The original 43-message corpus and its outcomes are already revealed.  The
``refreeze`` command therefore does not claim a fresh confirmatory freeze.  It
verifies the exact archived external source, license, and corpus bytes from a
historical content-addressed manifest, snapshots the current Urusilla
candidate sources, and writes an explicitly post-cutover exploratory amendment.
It performs no network or provider call.  Project codecs and tokenizers are
imported only by ``measure``, after the amendment and current source identities
have been verified.

The legacy ``freeze`` command is retained only to reproduce the original
acquisition mechanism.  It performs network fetches and must not be described
as fresh confirmatory evidence after corpus reveal.

This evaluates serialization of already-structured messages.  It does not
measure model comprehension, task success, adoption, energy, or state of the
art.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen
import uuid


FORMAT = "external-ood-evaluation-v2-retained-exploratory"
LEGACY_MANIFEST_FORMAT = "external-ood-premeasurement-manifest-v1"
LEGACY_MEASUREMENT_FORMAT = "external-ood-measurement-v1"
MANIFEST_FORMAT = "external-ood-retained-post-cutover-manifest-v2"
MEASUREMENT_FORMAT = "external-ood-retained-post-cutover-measurement-v2"
RETAINED_STAGE = "retained_revealed_corpus_post_cutover_exploratory_freeze"
ROOT = Path(__file__).resolve().parent
CACHE_ROOT = ROOT / "work" / "external_ood_evaluation"
SOURCE_CACHE = CACHE_ROOT / "sources"
EVIDENCE_ROOT = ROOT / "evidence" / "external_ood_evaluation"
TIMING_WARMUPS = 2
TIMING_REPEATS = 10
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MESSAGE_NAMESPACE = uuid.UUID("7e32b866-7caf-53b8-a288-161444977aa3")


@dataclass(frozen=True)
class SourceGroup:
    protocol_id: str
    organization: str
    repository: str
    revision: str
    license_name: str
    license_path: str
    extractor: str
    paths: tuple[str, ...]

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


SOURCE_GROUPS = (
    SourceGroup(
        protocol_id="w3c-activitystreams-2.0",
        organization="W3C",
        repository="w3c/activitystreams",
        revision="6a647d489e48ed4bc49597275171ff1963bb579e",
        license_name="W3C Software and Document License",
        license_path="LICENSE.md",
        extractor="single_json_object",
        paths=(
            "test/core-ex1-jsonld.json",
            "test/core-ex3-jsonld.json",
            "test/core-ex4-jsonld.json",
            "test/core-ex6-jsonld.json",
            "test/core-ex7-jsonld.json",
            "test/core-ex8-jsonld.json",
            "test/core-ex11b-jsonld.json",
            "test/core-ex13-jsonld.json",
            "test/vocabulary-ex1-jsonld.json",
            "test/vocabulary-ex10-jsonld.json",
            "test/vocabulary-ex112-jsonld.json",
            "test/vocabulary-ex184a-jsonld.json",
        ),
    ),
    SourceGroup(
        protocol_id="cncf-cloudevents-1.0.2",
        organization="Cloud Native Computing Foundation",
        repository="cloudevents/spec",
        revision="fc1f6f31f5f011a72183f1bcea20c987cb683ade",
        license_name="Apache-2.0",
        license_path="LICENSE",
        extractor="valid_json_fences_flatten_arrays",
        paths=(
            "cloudevents/spec.md",
            "cloudevents/formats/json-format.md",
        ),
    ),
    SourceGroup(
        protocol_id="official-mcp-2026-07-28",
        organization="Model Context Protocol project",
        repository="modelcontextprotocol/modelcontextprotocol",
        revision="5f5440bb26a62e2cf3440b92da5a667efa03b267",
        license_name="Repository LICENSE transition notice; specification contributions Apache-2.0",
        license_path="LICENSE",
        extractor="single_json_object",
        paths=(
            "schema/2026-07-28/examples/CallToolRequest/call-tool-request.json",
            "schema/2026-07-28/examples/CallToolResultResponse/call-tool-result-response.json",
            "schema/2026-07-28/examples/CancelledNotification/user-requested-cancellation.json",
            "schema/2026-07-28/examples/CompleteRequest/completion-request.json",
            "schema/2026-07-28/examples/CompleteResultResponse/completion-result-response.json",
            "schema/2026-07-28/examples/DiscoverRequest/server-discover-request.json",
            "schema/2026-07-28/examples/DiscoverResultResponse/discover-result-response.json",
            "schema/2026-07-28/examples/GetPromptRequest/get-prompt-request.json",
            "schema/2026-07-28/examples/GetPromptResultResponse/get-prompt-result-response.json",
            "schema/2026-07-28/examples/ListResourcesRequest/list-resources-request.json",
            "schema/2026-07-28/examples/ProgressNotification/progress-message.json",
            "schema/2026-07-28/examples/ReadResourceResultResponse/read-resource-result-response.json",
        ),
    ),
    SourceGroup(
        protocol_id="oasis-stix-2.1-examples",
        organization="OASIS Open",
        repository="oasis-open/cti-stix2-json-schemas",
        revision="9af1db41b7b86c06324f899649ae83480134f66e",
        license_name="BSD-3-Clause",
        license_path="LICENSE",
        extractor="stix_bundle_objects",
        paths=(
            "examples/indicator-for-c2-ip-address.json",
            "examples/indicator-to-campaign-relationship.json",
            "examples/indicators-for-C2-with-COA.json",
        ),
    ),
)


CANDIDATE_SOURCE_FILES = (
    "urusilla.py",
    "urusilla_benchmark.py",
    "urusilla_wire_v02.py",
    "urusilla_token_surface_holdout.py",
    "urusilla_token_surface_v03.py",
    "urusilla_tokenizer_benchmark.py",
    "urusilla_terse_english_benchmark.py",
    "urusilla_token_surface_v04.py",
    "urusilla_adaptive_surface_v05.py",
    "urusilla_generalization_surface_v06.py",
    "urusilla_model_comprehension_pilot.py",
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


FROZEN_PROFILE_IDENTITIES = {
    "static_wire_profile_dictionary_id": "7d12fc414eae60b2",
    "heldout_surface_codebook_sha256": "d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695",
    "train_only_alias_profile_sha256": "f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d",
}


_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", re.IGNORECASE | re.DOTALL)


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
    request = Request(url, headers={"User-Agent": "external-ood-evaluation/1"})
    with urlopen(request, timeout=120) as response:
        data = response.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise RuntimeError(f"source exceeds {MAX_SOURCE_BYTES} bytes: {url}")
    return data


def _cache_source(data: bytes, suffix: str) -> Path:
    SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(data)
    target = SOURCE_CACHE / f"{digest}{suffix}"
    if target.exists() and target.read_bytes() != data:
        raise RuntimeError(f"content-address collision at {target}")
    if not target.exists():
        target.write_bytes(data)
    return target


def extract_json_fences(data: bytes) -> tuple[tuple[str, Any], ...]:
    text = data.decode("utf-8", errors="strict")
    extracted: list[tuple[str, Any]] = []
    for fence_index, match in enumerate(_FENCE.finditer(text)):
        candidate = match.group(1).strip()
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, Mapping):
            extracted.append((f"/json-fence/{fence_index}", parsed))
        elif isinstance(parsed, list):
            for item_index, item in enumerate(parsed):
                if not isinstance(item, Mapping):
                    raise RuntimeError("a selected JSON fence contains a non-object item")
                extracted.append((f"/json-fence/{fence_index}/{item_index}", item))
    return tuple(extracted)


def extract_objects(extractor: str, data: bytes) -> tuple[tuple[str, Any], ...]:
    if extractor == "valid_json_fences_flatten_arrays":
        return extract_json_fences(data)
    parsed = json.loads(data.decode("utf-8", errors="strict"))
    if extractor == "single_json_object":
        if not isinstance(parsed, Mapping):
            raise RuntimeError("selected JSON source is not one object")
        return (("$", parsed),)
    if extractor == "stix_bundle_objects":
        if not isinstance(parsed, Mapping) or not isinstance(parsed.get("objects"), list):
            raise RuntimeError("selected STIX source is not a bundle with objects")
        objects = parsed["objects"]
        if not all(isinstance(item, Mapping) for item in objects):
            raise RuntimeError("selected STIX bundle has a non-object entry")
        return tuple((f"/objects/{index}", item) for index, item in enumerate(objects))
    raise RuntimeError(f"unknown extractor {extractor!r}")


def build_wrapped_message(record: Mapping[str, Any], logical_clock: int) -> dict[str, Any]:
    protocol_id = str(record["protocol_id"])
    source_locator = str(record["source_locator"])
    object_json = str(record["source_object_canonical_json"])
    object_digest = str(record["source_object_sha256"])
    identity = f"{protocol_id}\x00{source_locator}\x00{object_digest}"
    message_id = str(uuid.uuid5(MESSAGE_NAMESPACE, "message\x00" + identity))
    session_id = str(uuid.uuid5(MESSAGE_NAMESPACE, "session\x00" + protocol_id))
    return {
        "id": message_id,
        "session": session_id,
        "sender": f"urn:external-evaluation:source:{protocol_id}",
        "recipients": ["urn:external-evaluation:receiver"],
        "act": "ASSERT",
        "reply_to": None,
        "schema": "urn:external-evaluation:schema:source-object:v1",
        "logical_clock": logical_clock,
        "expires_ms": 0,
        "confidence_ppm": None,
        "expected": [],
        "body": {
            "kind": "x:external-ood-record",
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


def _snapshot_candidate_sources(
    artifact_root: Path = CACHE_ROOT,
) -> dict[str, dict[str, Any]]:
    """Archive the exact current candidate bytes under content-addressed names."""

    snapshot_root = artifact_root / "candidate_sources"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    snapshots: dict[str, dict[str, Any]] = {}
    for name, digest in _candidate_source_digests().items():
        source = ROOT / name
        data = source.read_bytes()
        target = snapshot_root / f"{digest}-{name}"
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f"content-addressed candidate snapshot collision: {target}")
        if not target.exists():
            target.write_bytes(data)
        snapshots[name] = {
            "snapshot_file": str(target.relative_to(ROOT)),
            "sha256": digest,
            "bytes": len(data),
        }
    return snapshots


def freeze() -> tuple[Path, str, Mapping[str, Any]]:
    forbidden = tuple(name for name in sys.modules if name.startswith("urusilla_") or name.startswith("urusilla_"))
    if forbidden:
        raise RuntimeError(f"project modules were imported before freeze: {forbidden}")

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    source_manifest: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    license_manifest: list[dict[str, Any]] = []
    protocol_clocks: Counter[str] = Counter()

    for group in SOURCE_GROUPS:
        license_data = _fetch(group.raw_url(group.license_path))
        license_cache = _cache_source(license_data, ".license")
        license_manifest.append(
            {
                "protocol_id": group.protocol_id,
                "license_name": group.license_name,
                "license_uri": group.blob_url(group.license_path),
                "license_file_sha256": sha256_bytes(license_data),
                "cache_file": str(license_cache.relative_to(ROOT)),
                "note": "Repository license metadata is recorded as source evidence, not as legal advice.",
            }
        )
        for source_path in group.paths:
            raw = _fetch(group.raw_url(source_path))
            cache = _cache_source(raw, Path(source_path).suffix or ".source")
            file_digest = sha256_bytes(raw)
            extracted = extract_objects(group.extractor, raw)
            if not extracted:
                raise RuntimeError(f"no selected objects extracted from {source_path}")
            source_manifest.append(
                {
                    "protocol_id": group.protocol_id,
                    "organization": group.organization,
                    "repository": group.repository,
                    "revision": group.revision,
                    "source_path": source_path,
                    "source_uri": group.blob_url(source_path),
                    "download_uri": group.raw_url(source_path),
                    "source_file_sha256": file_digest,
                    "source_file_bytes": len(raw),
                    "extractor": group.extractor,
                    "extracted_objects": len(extracted),
                    "cache_file": str(cache.relative_to(ROOT)),
                }
            )
            for locator, value in extracted:
                object_bytes = canonical_json_bytes(value)
                protocol_clocks[group.protocol_id] += 1
                records.append(
                    {
                        "protocol_id": group.protocol_id,
                        "source_revision": group.revision,
                        "source_path": source_path,
                        "source_uri": group.blob_url(source_path),
                        "source_file_sha256": file_digest,
                        "source_locator": locator,
                        "source_object_sha256": sha256_bytes(object_bytes),
                        "source_object_canonical_json": object_bytes.decode("utf-8"),
                        "logical_clock": protocol_clocks[group.protocol_id],
                    }
                )

    messages = tuple(
        build_wrapped_message(record, int(record["logical_clock"])) for record in records
    )
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
            "sequence_sha256": _partition_digest(messages, indices),
        }
        for name, indices in partition_indices.items()
    }

    manifest: dict[str, Any] = {
        "format": LEGACY_MANIFEST_FORMAT,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": "frozen_before_project_codec_or_tokenizer_import",
        "external_data_role": "evaluation_only_no_training_no_tuning",
        "source_selection": {
            "rule": "The exact paths are an a priori convenience sample of complete official example objects across four independently maintained standards or protocol repositories. No path was selected using project codec or tokenizer results.",
            "source_groups": source_manifest,
            "licenses": license_manifest,
        },
        "transform": {
            "rule_version": "source-bound-wrapper-v1",
            "steps": [
                "Decode selected UTF-8 JSON sources with the Python standard library.",
                "For Markdown, scan fenced blocks in source order, retain blocks that parse as JSON objects, flatten non-empty arrays of objects in item order, and ignore invalid or empty examples.",
                "For STIX bundles, select each member of the top-level objects array in order.",
                "Serialize each selected external object as sorted minified UTF-8 JSON with non-ASCII characters unescaped and non-finite numbers forbidden.",
                "Store that canonical external JSON losslessly in source_json inside one quarantined ASSERT extension node.",
                "Derive message and session UUIDs with UUIDv5 from the frozen protocol, locator, and object digest; assign one-based logical clocks per protocol.",
            ],
            "project_authored_envelope_choices": {
                "act": "ASSERT",
                "body_kind": "x:external-ood-record",
                "schema": "urn:external-evaluation:schema:source-object:v1",
                "recipient": "urn:external-evaluation:receiver",
                "reply_to": None,
                "expires_ms": 0,
                "confidence_ppm": None,
                "expected": [],
                "meta": {},
                "caveat": "Repeated source metadata and a canonical JSON string are conservative project-authored envelope choices; this is not a native mapping for any external protocol.",
            },
            "source_preservation": "Every wrapped record carries the immutable source URI and revision, source-file digest, exact source locator, canonical external-object digest, and complete canonical external JSON.",
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
        "frozen_candidates": {
            "candidate_set": [
                "sorted_minified_json",
                "controlled_terse_english",
                "raw_and_base64_static_wire_v0.2",
                "token_surface_v0.4",
                "adaptive_surface_v0.5",
                "generalization_surface_v0.6",
            ],
            "source_sha256": _candidate_source_digests(),
            "profile_identities": FROZEN_PROFILE_IDENTITIES,
            "modification_rule": "All candidates, tokenizers, codebooks, and profiles are used unchanged. External records are never inputs to profile derivation or tuning.",
        },
        "tokenizers": FROZEN_TOKENIZERS,
        "measurement_plan": {
            "timing_warmups": TIMING_WARMUPS,
            "timing_repeats": TIMING_REPEATS,
            "metrics": [
                "UTF-8 bytes and characters",
                "tokens under each pinned tokenizer",
                "exact semantic round-trip",
                "deterministic re-encoding",
                "raw-byte fallback use in the frozen v0.4 codebook",
                "adaptive selected-mode counts",
                "cold artifact cost and full-session cold totals",
                "encode or select and decode wall-clock p50 and p95 latency",
            ],
            "partitions": list(partitions),
            "latency_boundary": "Paths do unequal work. JSON uses native-library serialization; project decoders validate; adaptive encode latency includes candidate construction, token counting, and selection.",
        },
        "hypotheses": {
            "H1_exactness": "Every tested representation must recover all 43 canonical wrapped messages exactly and deterministically.",
            "H2_fallback": "The frozen v0.4 byte codebook must encode every message through complete raw-byte fallback even when learned entries miss.",
            "H3_v05_selection": "For every receiver and message, v0.5 must select the exact minimum-token eligible candidate in its unchanged enumerated set.",
            "H4_v06_warm_guard": "For every receiver and message, v0.6 must use no more warm tokens than its v0.5 baseline candidate.",
            "H5_v06_cold_guard": "For every frozen partition and receiver, the exhaustive v0.6 cold planner must use no more tokens than its complete v0.5 fallback plan.",
            "H6_value_signal": "A diagnostic value signal passes only if full-corpus v0.6 cold tokens are at least 20 percent below the better of plain JSON and controlled terse English for every tokenizer. This does not include task success and cannot support a utility or generalization claim by itself.",
        },
        "claim_boundary": "This frozen evaluation can reveal serialization behavior on independently authored examples. It cannot establish model comprehension, task success, energy savings, adoption, universal generalization, or a state-of-the-art result.",
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


def _verify_external_archive(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Verify retained external bytes without relying on historical candidate code."""

    corpus_info = manifest["corpus"]
    corpus_path = ROOT / corpus_info["corpus_file"]
    corpus_bytes = corpus_path.read_bytes()
    if len(corpus_bytes) != corpus_info["corpus_file_bytes"]:
        raise RuntimeError("frozen corpus byte count changed")
    if sha256_bytes(corpus_bytes) != corpus_info["corpus_file_sha256"]:
        raise RuntimeError("frozen corpus digest changed")
    messages = json.loads(corpus_bytes.decode("utf-8"))
    if not isinstance(messages, list) or len(messages) != corpus_info["message_count"]:
        raise RuntimeError("frozen corpus structure changed")
    observed_sequence = sequence_digest_bytes(canonical_json_bytes(message) for message in messages)
    if observed_sequence != corpus_info["message_sequence_sha256"]:
        raise RuntimeError("frozen message-sequence digest changed")
    for source in manifest["source_selection"]["source_groups"]:
        cached = ROOT / source["cache_file"]
        if sha256_file(cached) != source["source_file_sha256"]:
            raise RuntimeError(f"cached source digest changed: {source['source_path']}")
    for license_record in manifest["source_selection"]["licenses"]:
        cached = ROOT / license_record["cache_file"]
        if sha256_file(cached) != license_record["license_file_sha256"]:
            raise RuntimeError(f"cached license digest changed: {license_record['protocol_id']}")
    return tuple(messages)


def _verify_candidate_snapshots(manifest: Mapping[str, Any]) -> None:
    expected_sources = manifest["frozen_candidates"]["source_sha256"]
    snapshots = manifest["frozen_candidates"].get("source_snapshots")
    if not isinstance(snapshots, Mapping) or set(snapshots) != set(expected_sources):
        raise RuntimeError("retained manifest has an incomplete candidate snapshot set")
    allowed_roots = (CACHE_ROOT.resolve(), EVIDENCE_ROOT.resolve())
    for name, expected in expected_sources.items():
        record = snapshots[name]
        if not isinstance(record, Mapping) or record.get("sha256") != expected:
            raise RuntimeError(f"candidate snapshot identity changed: {name}")
        path = (ROOT / str(record.get("snapshot_file"))).resolve()
        if not any(_is_relative_to(path, allowed) for allowed in allowed_roots):
            raise RuntimeError(f"candidate snapshot escapes the evidence roots: {name}")
        if sha256_file(path) != expected or path.stat().st_size != record.get("bytes"):
            raise RuntimeError(f"candidate snapshot bytes changed: {name}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _copy_archived_file(source: Path, destination: Path, expected_sha256: str) -> Path:
    data = source.read_bytes()
    if sha256_bytes(data) != expected_sha256:
        raise RuntimeError(f"archived input changed before copy: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != data:
        raise RuntimeError(f"tracked evidence collision: {destination}")
    if not destination.exists():
        destination.write_bytes(data)
    return destination


def refreeze_retained(
    prior_manifest_path: Path,
    prior_measurement_path: Path,
) -> tuple[Path, str, Mapping[str, Any]]:
    """Freeze current inputs against the already-revealed retained corpus, offline."""

    forbidden = tuple(
        name
        for name in sys.modules
        if name == "urusilla" or name.startswith("urusilla_")
    )
    if forbidden:
        raise RuntimeError(f"project modules were imported before retained refreeze: {forbidden}")
    prior, prior_digest = _load_content_addressed(
        prior_manifest_path, "premeasurement-manifest"
    )
    if prior.get("format") != LEGACY_MANIFEST_FORMAT:
        raise RuntimeError("retained refreeze requires a historical v1 manifest")
    messages = _verify_external_archive(prior)
    prior_measurement, prior_measurement_digest = _load_content_addressed(
        prior_measurement_path, "measurement"
    )
    if (
        prior_measurement.get("format") != LEGACY_MEASUREMENT_FORMAT
        or prior_measurement.get("premeasurement_manifest_sha256") != prior_digest
    ):
        raise RuntimeError("historical measurement is not bound to the supplied manifest")

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    tracked_sources: list[dict[str, Any]] = []
    for record in prior["source_selection"]["source_groups"]:
        source = ROOT / record["cache_file"]
        destination = EVIDENCE_ROOT / "sources" / source.name
        _copy_archived_file(source, destination, record["source_file_sha256"])
        tracked_sources.append(
            {**record, "cache_file": str(destination.relative_to(ROOT))}
        )
    tracked_licenses: list[dict[str, Any]] = []
    for record in prior["source_selection"]["licenses"]:
        source = ROOT / record["cache_file"]
        destination = EVIDENCE_ROOT / "sources" / source.name
        _copy_archived_file(source, destination, record["license_file_sha256"])
        tracked_licenses.append(
            {**record, "cache_file": str(destination.relative_to(ROOT))}
        )
    prior_corpus_path = ROOT / prior["corpus"]["corpus_file"]
    tracked_corpus_path = EVIDENCE_ROOT / prior_corpus_path.name
    _copy_archived_file(
        prior_corpus_path,
        tracked_corpus_path,
        prior["corpus"]["corpus_file_sha256"],
    )

    snapshots = _snapshot_candidate_sources(EVIDENCE_ROOT)
    source_sha256 = {name: record["sha256"] for name, record in snapshots.items()}
    source_selection = {
        **prior["source_selection"],
        "source_groups": tracked_sources,
        "licenses": tracked_licenses,
    }
    source_selection["retained_acquisition"] = {
        "mode": "exact_content_addressed_archive_reuse",
        "network_used": False,
        "provider_calls": 0,
        "archive_verified_before_current_candidate_snapshot": True,
        "caveat": (
            "The source families, records, wrapper, hypotheses, and earlier outcomes "
            "were already revealed before this post-cutover refreeze."
        ),
    }
    corpus = dict(prior["corpus"])
    corpus["corpus_file"] = str(tracked_corpus_path.relative_to(ROOT))
    corpus["reveal_status"] = "revealed_before_post_cutover_refreeze"
    measurement_plan = dict(prior["measurement_plan"])
    measurement_plan["classification"] = (
        "retained_post_cutover_exploratory_remeasurement_not_fresh_confirmation"
    )
    hypotheses = dict(prior["hypotheses"])
    hypotheses["status"] = (
        "historical_thresholds_retained_as_diagnostics_after_outcome_reveal"
    )
    manifest: dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "refrozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": RETAINED_STAGE,
        "external_data_role": "retained_evaluation_only_no_new_training_or_tuning",
        "corpus_revealed_before_refreeze": True,
        "fresh_confirmatory_status": False,
        "amendment_chain": {
            "supersedes_manifest_sha256": prior_digest,
            "supersedes_measurement_sha256": prior_measurement_digest,
            "reason": (
                "Urusilla cutover removed the historical candidate filenames. "
                "The v1 manifests retained their digests but no candidate source snapshots, "
                "so those live-source locks cannot be reconstructed or reverified."
            ),
            "historical_candidate_snapshots_available": False,
            "external_source_archive_reused_exactly": True,
        },
        "source_selection": source_selection,
        "transform": prior["transform"],
        "corpus": corpus,
        "frozen_candidates": {
            "candidate_set": prior["frozen_candidates"]["candidate_set"],
            "source_sha256": source_sha256,
            "source_snapshots": snapshots,
            "profile_identities": FROZEN_PROFILE_IDENTITIES,
            "modification_rule": (
                "Current Urusilla sources are snapshotted after corpus and outcome reveal. "
                "This rerun is exploratory and cannot establish untuned generalization."
            ),
        },
        "tokenizers": prior["tokenizers"],
        "measurement_plan": measurement_plan,
        "hypotheses": hypotheses,
        "claim_boundary": (
            "This retained post-cutover rerun can report serialization and safety diagnostics "
            "on an already-revealed corpus. It is not fresh confirmatory evidence and cannot "
            "establish model comprehension, task success, energy savings, adoption, universal "
            "generalization, or a state-of-the-art result."
        ),
    }
    if len(messages) != 43:
        raise RuntimeError("retained corpus no longer contains exactly 43 messages")
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_digest = sha256_bytes(manifest_bytes)
    manifest_path = EVIDENCE_ROOT / f"premeasurement-manifest-{manifest_digest}.json"
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
        raise RuntimeError("content-addressed retained manifest collision")
    if not manifest_path.exists():
        manifest_path.write_bytes(manifest_bytes)
    return manifest_path, manifest_digest, manifest


def _verify_frozen_inputs(
    manifest: Mapping[str, Any], *, require_current_candidates: bool = False
) -> tuple[dict[str, Any], ...]:
    manifest_format = manifest.get("format")
    if manifest_format == LEGACY_MANIFEST_FORMAT:
        if manifest.get("stage") != "frozen_before_project_codec_or_tokenizer_import":
            raise RuntimeError("legacy manifest does not declare its historical freeze stage")
        expected_sources = manifest["frozen_candidates"]["source_sha256"]
        if expected_sources != _candidate_source_digests():
            raise RuntimeError(
                "historical candidate snapshots are unavailable after Urusilla cutover"
            )
    elif manifest_format == MANIFEST_FORMAT:
        if manifest.get("stage") != RETAINED_STAGE:
            raise RuntimeError("retained manifest does not declare the exploratory freeze stage")
        if manifest.get("corpus_revealed_before_refreeze") is not True:
            raise RuntimeError("retained manifest conceals corpus reveal status")
        if manifest.get("fresh_confirmatory_status") is not False:
            raise RuntimeError("retained manifest incorrectly claims fresh confirmation")
        acquisition = manifest["source_selection"].get("retained_acquisition", {})
        if acquisition.get("network_used") is not False or acquisition.get("provider_calls") != 0:
            raise RuntimeError("retained manifest does not prove archive-only acquisition")
        _verify_candidate_snapshots(manifest)
        if require_current_candidates:
            expected_sources = manifest["frozen_candidates"]["source_sha256"]
            if expected_sources != _candidate_source_digests():
                raise RuntimeError("a current candidate source changed after retained refreeze")
    else:
        raise RuntimeError("unknown external OOD manifest format")
    return _verify_external_archive(manifest)


def _nearest(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))]


def _time_paths(
    messages: Sequence[Mapping[str, Any]],
    encoded: Sequence[Any],
    encoder: Callable[[Mapping[str, Any]], Any],
    decoder: Callable[[Any], Mapping[str, Any]],
) -> dict[str, int]:
    for _ in range(TIMING_WARMUPS):
        for message in messages:
            encoder(message)
        for value in encoded:
            decoder(value)
    encode_samples: list[int] = []
    decode_samples: list[int] = []
    for _ in range(TIMING_REPEATS):
        for message in messages:
            start = time.perf_counter_ns()
            encoder(message)
            encode_samples.append(time.perf_counter_ns() - start)
        for value in encoded:
            start = time.perf_counter_ns()
            decoder(value)
            decode_samples.append(time.perf_counter_ns() - start)
    return {
        "samples_per_direction": len(encode_samples),
        "encode_p50_ns": int(statistics.median(encode_samples)),
        "encode_p95_ns": _nearest(encode_samples, 0.95),
        "decode_p50_ns": int(statistics.median(decode_samples)),
        "decode_p95_ns": _nearest(decode_samples, 0.95),
    }


def _text_metrics(texts: Sequence[str], profiles: Sequence[Any]) -> dict[str, Any]:
    return {
        "utf8_bytes": sum(len(text.encode("utf-8")) for text in texts),
        "characters": sum(len(text) for text in texts),
        "sequence_sha256": sequence_digest_bytes(text.encode("utf-8") for text in texts),
        "tokens": {
            profile.key: sum(profile.count(text) for text in texts) for profile in profiles
        },
    }


def _subset(values: Sequence[Any], indices: Sequence[int]) -> tuple[Any, ...]:
    return tuple(values[index] for index in indices)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _deterministic_outcome_sha256(measurement: Mapping[str, Any]) -> str:
    """Digest claim-bearing deterministic results, excluding time and latency."""

    keys = (
        "format",
        "corpus",
        "tokenizers",
        "profiles",
        "exactness",
        "partitions",
        "fallback",
        "selection",
        "hypothesis_outcomes",
        "external_corpus_used_for_training_or_tuning",
        "corpus_revealed_before_refreeze",
        "fresh_confirmatory_status",
        "claim_boundary",
    )
    return sha256_bytes(canonical_json_bytes({key: measurement.get(key) for key in keys}))


def measure(manifest_path: Path) -> tuple[Path, str, Mapping[str, Any]]:
    manifest, manifest_digest = _load_content_addressed(
        manifest_path, "premeasurement-manifest"
    )
    raw_messages = _verify_frozen_inputs(manifest, require_current_candidates=True)

    # Project imports intentionally occur only after the complete premeasurement
    # manifest, source cache, corpus, and candidate source digests pass above.
    from urusilla_benchmark import json_decode, json_encode
    from urusilla import normalize_message
    from urusilla_token_surface_holdout import holdout_codebook
    from urusilla_tokenizer_benchmark import default_asset_root, load_tokenizer_profiles
    from urusilla_wire_v02 import (
        DEFAULT_PROFILE,
        decode_message as decode_v02,
        encode_capsule as encode_profile_capsule,
        encode_message as encode_v02,
    )
    from urusilla_terse_english_benchmark import (
        decode_terse_english,
        encode_terse_english,
    )
    from urusilla_token_surface_v04 import (
        decode_message as decode_v04,
        encode_bytes_optimal,
        encode_codebook_capsule_text,
        encode_message as encode_v04,
    )
    from urusilla_adaptive_surface_v05 import (
        decode_message as decode_v05,
        plan_session as plan_v05,
        prepare_message as prepare_v05,
        select_message as select_v05,
    )
    from urusilla_generalization_surface_v06 import (
        build_datasets as build_existing_datasets,
        cold_artifact_metrics,
        decode_selected as decode_v06,
        derive_alias_profile,
        plan_cold_session as plan_v06,
        prepare_message as prepare_v06,
        profile_sha256,
        select_message as select_v06,
    )

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
    for key, expected in manifest["tokenizers"].items():
        if observed_tokenizers[key]["fingerprint"] != expected["fingerprint"]:
            raise RuntimeError(f"frozen tokenizer fingerprint changed: {key}")

    messages = tuple(normalize_message(message) for message in raw_messages)
    if tuple(raw_messages) != messages:
        raise RuntimeError("frozen wrapper corpus is not already canonical")
    if DEFAULT_PROFILE.dictionary_id.hex() != FROZEN_PROFILE_IDENTITIES[
        "static_wire_profile_dictionary_id"
    ]:
        raise RuntimeError("frozen v0.2 profile dictionary identity changed")
    codebook = holdout_codebook()
    if codebook.sha256 != FROZEN_PROFILE_IDENTITIES["heldout_surface_codebook_sha256"]:
        raise RuntimeError("frozen v0.4 codebook identity changed")
    existing_datasets = build_existing_datasets()
    alias_profile = derive_alias_profile(existing_datasets["development"])
    if profile_sha256(alias_profile) != FROZEN_PROFILE_IDENTITIES["train_only_alias_profile_sha256"]:
        raise RuntimeError("frozen v0.6 alias profile identity changed")

    json_texts = tuple(json_encode(message).decode("utf-8") for message in messages)
    terse_texts = tuple(encode_terse_english(message) for message in messages)
    raw_v02 = tuple(encode_v02(message) for message in messages)
    base64_v02 = tuple(base64.b64encode(frame).decode("ascii") for frame in raw_v02)
    v04_texts = tuple(encode_v04(message, codebook) for message in messages)
    fixed_encodings: dict[str, Sequence[Any]] = {
        "sorted_minified_json": json_texts,
        "controlled_terse_english": terse_texts,
        "raw_static_wire_v0.2": raw_v02,
        "base64_static_wire_v0.2": base64_v02,
        "token_surface_v0.4": v04_texts,
    }
    fixed_decoders: dict[str, Callable[[Any], Mapping[str, Any]]] = {
        "sorted_minified_json": lambda text: json_decode(text.encode("utf-8")),
        "controlled_terse_english": decode_terse_english,
        "raw_static_wire_v0.2": decode_v02,
        "base64_static_wire_v0.2": lambda text: decode_v02(base64.b64decode(text, validate=True)),
        "token_surface_v0.4": lambda text: decode_v04(text, codebook),
    }
    fixed_encoders: dict[str, Callable[[Mapping[str, Any]], Any]] = {
        "sorted_minified_json": lambda message: json_encode(message).decode("utf-8"),
        "controlled_terse_english": encode_terse_english,
        "raw_static_wire_v0.2": encode_v02,
        "base64_static_wire_v0.2": lambda message: base64.b64encode(encode_v02(message)).decode("ascii"),
        "token_surface_v0.4": lambda message: encode_v04(message, codebook),
    }

    fixed_exactness: dict[str, dict[str, int]] = {}
    for codec, values in fixed_encodings.items():
        decoder = fixed_decoders[codec]
        encoder = fixed_encoders[codec]
        exact = deterministic = 0
        for message, value in zip(messages, values, strict=True):
            decoded = decoder(value)
            exact += decoded == message
            deterministic += encoder(message) == value and encoder(decoded) == value
        fixed_exactness[codec] = {
            "exact": exact,
            "deterministic": deterministic,
            "trials": len(messages),
        }

    prepared_v05 = tuple(prepare_v05(message) for message in messages)
    prepared_v06 = tuple(prepare_v06(message, alias_profile) for message in messages)
    v05_texts: dict[str, tuple[str, ...]] = {}
    v06_texts: dict[str, tuple[str, ...]] = {}
    v05_modes: dict[str, Counter[str]] = {}
    v06_modes: dict[str, Counter[str]] = {}
    adaptive_exactness: dict[str, dict[str, dict[str, int]]] = {"v0.5": {}, "v0.6": {}}
    v05_selector_trials = v05_selector_passes = 0
    v06_guard_trials = v06_guard_passes = 0
    for profile in profiles:
        selected05 = tuple(select_v05(message, profile) for message in messages)
        selected06 = tuple(select_v06(message, alias_profile, profile) for message in messages)
        texts05 = tuple(item.candidate.text for item in selected05)
        texts06 = tuple(item.candidate.text for item in selected06)
        v05_texts[profile.key] = texts05
        v06_texts[profile.key] = texts06
        v05_modes[profile.key] = Counter(item.candidate.mode for item in selected05)
        v06_modes[profile.key] = Counter(item.candidate.mode for item in selected06)
        for item in selected05:
            v05_selector_trials += 1
            v05_selector_passes += item.candidate.tokens == item.all_best_tokens
        for item in selected06:
            v06_guard_trials += 1
            v06_guard_passes += item.candidate.tokens <= item.baseline.tokens
        for label, texts, decoder, selector in (
            (
                "v0.5",
                texts05,
                decode_v05,
                lambda message, _profile=profile: select_v05(message, _profile).candidate.text,
            ),
            (
                "v0.6",
                texts06,
                lambda text: decode_v06(text, alias_profile),
                lambda message, _profile=profile: select_v06(message, alias_profile, _profile).candidate.text,
            ),
        ):
            exact = deterministic = 0
            for message, text_value in zip(messages, texts, strict=True):
                decoded = decoder(text_value)
                exact += decoded == message
                deterministic += selector(message) == text_value and selector(decoded) == text_value
            adaptive_exactness[label][profile.key] = {
                "exact": exact,
                "deterministic": deterministic,
                "trials": len(messages),
            }

    partition_map = manifest["corpus"]["partitions"]
    partition_metrics: dict[str, Any] = {}
    profile_capsule_text = base64.b64encode(encode_profile_capsule(DEFAULT_PROFILE)).decode("ascii")
    codebook_capsule_text = encode_codebook_capsule_text(codebook)
    v06_cold_guard_trials = v06_cold_guard_passes = 0
    for partition, partition_info in partition_map.items():
        indices = tuple(partition_info["message_indices"])
        fixed_partition = {
            "sorted_minified_json": _text_metrics(_subset(json_texts, indices), profiles),
            "controlled_terse_english": _text_metrics(_subset(terse_texts, indices), profiles),
            "base64_static_wire_v0.2": _text_metrics(_subset(base64_v02, indices), profiles),
            "token_surface_v0.4": _text_metrics(_subset(v04_texts, indices), profiles),
        }
        fixed_partition["raw_static_wire_v0.2"] = {
            "bytes": sum(len(raw_v02[index]) for index in indices),
            "sequence_sha256": sequence_digest_bytes(raw_v02[index] for index in indices),
        }
        adaptive_partition: dict[str, Any] = {"v0.5": {}, "v0.6": {}}
        cold_partition: dict[str, Any] = {}
        for profile in profiles:
            texts05 = _subset(v05_texts[profile.key], indices)
            texts06 = _subset(v06_texts[profile.key], indices)
            adaptive_partition["v0.5"][profile.key] = {
                "utf8_bytes": sum(len(value.encode("utf-8")) for value in texts05),
                "tokens": sum(profile.count(value) for value in texts05),
                "sequence_sha256": sequence_digest_bytes(value.encode("utf-8") for value in texts05),
                "mode_counts": dict(Counter(select_v05(messages[index], profile).candidate.mode for index in indices)),
            }
            adaptive_partition["v0.6"][profile.key] = {
                "utf8_bytes": sum(len(value.encode("utf-8")) for value in texts06),
                "tokens": sum(profile.count(value) for value in texts06),
                "sequence_sha256": sequence_digest_bytes(value.encode("utf-8") for value in texts06),
                "mode_counts": dict(Counter(select_v06(messages[index], alias_profile, profile).candidate.mode for index in indices)),
            }
            subset_prepared05 = _subset(prepared_v05, indices)
            subset_prepared06 = _subset(prepared_v06, indices)
            plan05 = plan_v05(subset_prepared05, profile)
            plan06 = plan_v06(subset_prepared06, profile, alias_profile)
            if plan06.baseline_total_tokens != plan05.total_tokens:
                raise RuntimeError("v0.6 baseline cold plan disagrees with direct v0.5 plan")
            v06_cold_guard_trials += 1
            v06_cold_guard_passes += plan06.selected.total_tokens <= plan05.total_tokens
            json_tokens = fixed_partition["sorted_minified_json"]["tokens"][profile.key]
            terse_tokens = fixed_partition["controlled_terse_english"]["tokens"][profile.key]
            base64_tokens = fixed_partition["base64_static_wire_v0.2"]["tokens"][profile.key]
            v04_tokens = fixed_partition["token_surface_v0.4"]["tokens"][profile.key]
            v02_cold_tokens = profile.count(profile_capsule_text)
            structured_cold_tokens, structured_cold_bytes = (
                cold_artifact_metrics(profile, alias_profile)["structured_bundle"]
            )
            cold_partition[profile.key] = {
                "plain_json_total_tokens": json_tokens,
                "controlled_terse_total_tokens": terse_tokens,
                "v0.2_profile_cold_tokens": v02_cold_tokens,
                "v0.2_profile_cold_bytes": len(profile_capsule_text.encode("utf-8")),
                "v0.2_full_total_tokens": v02_cold_tokens + base64_tokens,
                "v0.4_structured_bundle_cold_tokens": structured_cold_tokens,
                "v0.4_structured_bundle_cold_bytes": structured_cold_bytes,
                "v0.4_full_total_tokens": structured_cold_tokens + v04_tokens,
                "v0.5": {
                    "activated_bundle": plan05.activated_bundle,
                    "cold_tokens": plan05.cold_tokens,
                    "total_tokens": plan05.total_tokens,
                    "no_bundle_total_tokens": plan05.no_bundle_total_tokens,
                    "activated_total_tokens": plan05.activated_total_tokens,
                    "mode_counts": dict(Counter(item.mode for item in plan05.choices)),
                },
                "v0.6": {
                    "cold_tokens": plan06.selected.cold_tokens,
                    "cold_bytes": plan06.selected.cold_bytes,
                    "message_tokens": plan06.selected.message_tokens,
                    "total_tokens": plan06.selected.total_tokens,
                    "v0.5_baseline_total_tokens": plan06.baseline_total_tokens,
                    "structured_bundle": plan06.selected.structured_bundle,
                    "symbolic_grammar": plan06.selected.symbolic_grammar,
                    "optimized_profile": plan06.selected.optimized_profile,
                    "mode_counts": dict(Counter(item.mode for item in plan06.selected.choices)),
                },
            }
        partition_metrics[partition] = {
            "message_count": len(indices),
            "fixed": fixed_partition,
            "adaptive": adaptive_partition,
            "cold": cold_partition,
        }

    alphabet_index = {symbol: index for index, symbol in enumerate(codebook.alphabet)}
    fallback_by_partition: dict[str, Any] = {}
    optimal_payloads = tuple(encode_bytes_optimal(frame, codebook) for frame in raw_v02)
    for partition, partition_info in partition_map.items():
        indices = tuple(partition_info["message_indices"])
        raw_symbols = total_symbols = frame_bytes = messages_with_raw = 0
        for index in indices:
            payload = optimal_payloads[index]
            raw_here = sum(alphabet_index[symbol] < 256 for symbol in payload)
            raw_symbols += raw_here
            total_symbols += len(payload)
            frame_bytes += len(raw_v02[index])
            messages_with_raw += raw_here > 0
        fallback_by_partition[partition] = {
            "messages": len(indices),
            "messages_with_raw_fallback": messages_with_raw,
            "raw_symbols": raw_symbols,
            "payload_symbols": total_symbols,
            "raw_symbol_rate": raw_symbols / total_symbols if total_symbols else 0.0,
            "raw_bytes": raw_symbols,
            "frame_bytes": frame_bytes,
            "raw_byte_coverage": raw_symbols / frame_bytes if frame_bytes else 0.0,
        }

    latency: dict[str, Any] = {}
    for codec in (
        "sorted_minified_json",
        "controlled_terse_english",
        "raw_static_wire_v0.2",
        "base64_static_wire_v0.2",
        "token_surface_v0.4",
    ):
        latency[codec] = _time_paths(
            messages,
            fixed_encodings[codec],
            fixed_encoders[codec],
            fixed_decoders[codec],
        )
    latency["v0.5"] = {}
    latency["v0.6"] = {}
    for profile in profiles:
        latency["v0.5"][profile.key] = _time_paths(
            messages,
            v05_texts[profile.key],
            lambda message, _profile=profile: select_v05(message, _profile).candidate.text,
            decode_v05,
        )
        latency["v0.6"][profile.key] = _time_paths(
            messages,
            v06_texts[profile.key],
            lambda message, _profile=profile: select_v06(message, alias_profile, _profile).candidate.text,
            lambda text: decode_v06(text, alias_profile),
        )

    exact_values = list(fixed_exactness.values()) + [
        value for by_profile in adaptive_exactness.values() for value in by_profile.values()
    ]
    h1 = all(item["exact"] == item["trials"] and item["deterministic"] == item["trials"] for item in exact_values)
    h2 = fallback_by_partition["all"]["messages"] == len(messages)
    h3 = v05_selector_passes == v05_selector_trials
    h4 = v06_guard_passes == v06_guard_trials
    h5 = v06_cold_guard_passes == v06_cold_guard_trials
    h6_by_profile: dict[str, bool] = {}
    for profile in profiles:
        cold = partition_metrics["all"]["cold"][profile.key]
        best_plain = min(cold["plain_json_total_tokens"], cold["controlled_terse_total_tokens"])
        h6_by_profile[profile.key] = cold["v0.6"]["total_tokens"] * 5 <= best_plain * 4
    h6 = all(h6_by_profile.values())

    retained = manifest.get("format") == MANIFEST_FORMAT
    measurement: dict[str, Any] = {
        "format": MEASUREMENT_FORMAT if retained else LEGACY_MEASUREMENT_FORMAT,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "premeasurement_manifest_sha256": manifest_digest,
        "premeasurement_manifest_file": str(manifest_path.relative_to(ROOT)),
        "candidate_sources_verified_unchanged": True,
        "external_corpus_used_for_training_or_tuning": False,
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "tiktoken": _package_version("tiktoken"),
            "tokenizers": _package_version("tokenizers"),
        },
        "corpus": {
            "message_count": len(messages),
            "corpus_file_sha256": manifest["corpus"]["corpus_file_sha256"],
            "partitions": {key: value["message_count"] for key, value in manifest["corpus"]["partitions"].items()},
        },
        "tokenizers": observed_tokenizers,
        "profiles": {
            **FROZEN_PROFILE_IDENTITIES,
            "observed_alias_profile_sha256": profile_sha256(alias_profile),
            "v0.2_profile_capsule_text_bytes": len(profile_capsule_text.encode("utf-8")),
            "v0.4_codebook_capsule_text_bytes": len(codebook_capsule_text.encode("utf-8")),
        },
        "exactness": {
            "fixed": fixed_exactness,
            "adaptive": adaptive_exactness,
        },
        "partitions": partition_metrics,
        "fallback": fallback_by_partition,
        "selection": {
            "v0.5_full_corpus_mode_counts": {key: dict(value) for key, value in v05_modes.items()},
            "v0.6_full_corpus_mode_counts": {key: dict(value) for key, value in v06_modes.items()},
            "v0.5_exact_minimum_trials": v05_selector_trials,
            "v0.5_exact_minimum_passes": v05_selector_passes,
            "v0.6_warm_guard_trials": v06_guard_trials,
            "v0.6_warm_guard_passes": v06_guard_passes,
            "v0.6_cold_guard_trials": v06_cold_guard_trials,
            "v0.6_cold_guard_passes": v06_cold_guard_passes,
        },
        "latency": latency,
        "hypothesis_outcomes": {
            "H1_exactness": h1,
            "H2_fallback": h2,
            "H3_v05_selection": h3,
            "H4_v06_warm_guard": h4,
            "H5_v06_cold_guard": h5,
            "H6_value_signal": h6,
            "H6_by_tokenizer": h6_by_profile,
        },
        "claim_boundary": manifest["claim_boundary"],
    }
    if retained:
        measurement.update(
            measurement_status=(
                "retained_post_cutover_exploratory_remeasurement_not_fresh_confirmation"
            ),
            corpus_revealed_before_refreeze=True,
            fresh_confirmatory_status=False,
            archive_network_used=False,
            provider_calls=0,
            candidate_snapshots_verified=True,
        )
        measurement["deterministic_outcome_sha256"] = _deterministic_outcome_sha256(
            measurement
        )
    measurement_bytes = canonical_json_bytes(measurement)
    measurement_digest = sha256_bytes(measurement_bytes)
    measurement_root = (
        EVIDENCE_ROOT
        if _is_relative_to(manifest_path.resolve(), EVIDENCE_ROOT.resolve())
        else CACHE_ROOT
    )
    measurement_path = measurement_root / f"measurement-{measurement_digest}.json"
    if measurement_path.exists() and measurement_path.read_bytes() != measurement_bytes:
        raise RuntimeError("content-addressed measurement path contains different bytes")
    if not measurement_path.exists():
        measurement_path.write_bytes(measurement_bytes)
    return measurement_path, measurement_digest, measurement


def verify(manifest_path: Path, measurement_path: Path | None = None) -> dict[str, Any]:
    manifest, manifest_digest = _load_content_addressed(manifest_path, "premeasurement-manifest")
    messages = _verify_frozen_inputs(manifest)
    result: dict[str, Any] = {
        "manifest_sha256": manifest_digest,
        "message_count": len(messages),
        "manifest_verified": True,
    }
    if measurement_path is not None:
        measurement, measurement_digest = _load_content_addressed(measurement_path, "measurement")
        expected_measurement_format = (
            MEASUREMENT_FORMAT
            if manifest.get("format") == MANIFEST_FORMAT
            else LEGACY_MEASUREMENT_FORMAT
        )
        if measurement.get("format") != expected_measurement_format:
            raise RuntimeError("unknown measurement format")
        if measurement.get("premeasurement_manifest_sha256") != manifest_digest:
            raise RuntimeError("measurement is bound to a different manifest")
        if expected_measurement_format == MEASUREMENT_FORMAT:
            if (
                measurement.get("corpus_revealed_before_refreeze") is not True
                or measurement.get("fresh_confirmatory_status") is not False
                or measurement.get("archive_network_used") is not False
                or measurement.get("provider_calls") != 0
            ):
                raise RuntimeError("retained measurement has an invalid evidence classification")
            expected_outcome = measurement.get("deterministic_outcome_sha256")
            if expected_outcome != _deterministic_outcome_sha256(measurement):
                raise RuntimeError("retained deterministic outcome digest changed")
        result.update(
            measurement_sha256=measurement_digest,
            measurement_verified=True,
            hypothesis_outcomes=measurement["hypothesis_outcomes"],
        )
        if expected_measurement_format == MEASUREMENT_FORMAT:
            result.update(
                deterministic_outcome_sha256=measurement[
                    "deterministic_outcome_sha256"
                ],
                evidence_classification=measurement["measurement_status"],
            )
    return result


def write_evidence_inventory(
    manifest_path: Path, measurement_paths: Sequence[Path]
) -> tuple[Path, str, Mapping[str, Any]]:
    """Write a detached digest inventory for the tracked clean-clone closure."""

    manifest, manifest_digest = _load_content_addressed(
        manifest_path, "premeasurement-manifest"
    )
    _verify_frozen_inputs(manifest)
    paths = {
        manifest_path.resolve(),
        (ROOT / manifest["corpus"]["corpus_file"]).resolve(),
        *(
            (ROOT / record["cache_file"]).resolve()
            for record in manifest["source_selection"]["source_groups"]
        ),
        *(
            (ROOT / record["cache_file"]).resolve()
            for record in manifest["source_selection"]["licenses"]
        ),
        *(
            (ROOT / record["snapshot_file"]).resolve()
            for record in manifest["frozen_candidates"]["source_snapshots"].values()
        ),
    }
    measurement_digests: list[str] = []
    for measurement_path in measurement_paths:
        verified = verify(manifest_path, measurement_path)
        measurement_digests.append(str(verified["measurement_sha256"]))
        paths.add(measurement_path.resolve())
    files: dict[str, dict[str, Any]] = {}
    evidence_root = EVIDENCE_ROOT.resolve()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not _is_relative_to(path, evidence_root):
            raise RuntimeError(f"tracked evidence closure escapes evidence root: {path}")
        relative = path.relative_to(evidence_root).as_posix()
        files[relative] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    inventory: dict[str, Any] = {
        "format": "external-ood-retained-evidence-digests-v1",
        "algorithm": "sha256",
        "manifest_sha256": manifest_digest,
        "measurement_sha256": measurement_digests,
        "deterministic_outcome_sha256": json.loads(
            measurement_paths[0].read_text(encoding="utf-8")
        )["deterministic_outcome_sha256"],
        "files": files,
        "counts": {
            "external_sources": len(manifest["source_selection"]["source_groups"]),
            "repository_licenses": len(manifest["source_selection"]["licenses"]),
            "candidate_snapshots": len(
                manifest["frozen_candidates"]["source_snapshots"]
            ),
            "measurements": len(measurement_paths),
        },
        "third_party_notices": [
            {
                "protocol_id": record["protocol_id"],
                "license_name": record["license_name"],
                "license_uri": record["license_uri"],
                "license_file_sha256": record["license_file_sha256"],
            }
            for record in manifest["source_selection"]["licenses"]
        ],
        "corpus_revealed_before_refreeze": True,
        "fresh_confirmatory_status": False,
        "network_used": False,
        "provider_calls": 0,
        "self_digest_excluded": True,
        "detached_digest_excluded": True,
    }
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    inventory_path = EVIDENCE_ROOT / "DIGESTS.json"
    inventory_path.write_bytes(canonical_json_bytes(inventory))
    inventory_digest = sha256_file(inventory_path)
    (EVIDENCE_ROOT / "DIGESTS.sha256").write_text(
        f"{inventory_digest}  DIGESTS.json\n", encoding="ascii"
    )
    return inventory_path, inventory_digest, inventory


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "freeze",
        help="legacy network acquisition; not fresh evidence after corpus reveal",
    )
    refreeze_parser = subparsers.add_parser(
        "refreeze",
        help="offline retained-corpus post-cutover exploratory refreeze",
    )
    refreeze_parser.add_argument("--prior-manifest", type=Path, required=True)
    refreeze_parser.add_argument("--prior-measurement", type=Path, required=True)
    measure_parser = subparsers.add_parser("measure", help="run unchanged candidates after freeze")
    measure_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify", help="verify content-addressed artifacts")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--measurement", type=Path)
    inventory_parser = subparsers.add_parser(
        "inventory", help="write tracked clean-clone digest inventory"
    )
    inventory_parser.add_argument("--manifest", type=Path, required=True)
    inventory_parser.add_argument("--measurement", type=Path, action="append", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "freeze":
        path, digest, manifest = freeze()
        result = {
            "manifest_file": str(path.relative_to(ROOT)),
            "manifest_sha256": digest,
            "message_count": manifest["corpus"]["message_count"],
            "partitions": {
                key: value["message_count"] for key, value in manifest["corpus"]["partitions"].items()
            },
            "stage": manifest["stage"],
        }
    elif args.command == "refreeze":
        path, digest, manifest = refreeze_retained(
            args.prior_manifest.resolve(), args.prior_measurement.resolve()
        )
        result = {
            "manifest_file": str(path.relative_to(ROOT)),
            "manifest_sha256": digest,
            "message_count": manifest["corpus"]["message_count"],
            "stage": manifest["stage"],
            "fresh_confirmatory_status": False,
            "network_used": False,
            "provider_calls": 0,
            "supersedes_manifest_sha256": manifest["amendment_chain"][
                "supersedes_manifest_sha256"
            ],
        }
    elif args.command == "measure":
        path, digest, measurement = measure(args.manifest.resolve())
        result = {
            "measurement_file": str(path.relative_to(ROOT)),
            "measurement_sha256": digest,
            "premeasurement_manifest_sha256": measurement["premeasurement_manifest_sha256"],
            "hypothesis_outcomes": measurement["hypothesis_outcomes"],
        }
    elif args.command == "verify":
        result = verify(
            args.manifest.resolve(),
            args.measurement.resolve() if args.measurement else None,
        )
    else:
        path, digest, inventory = write_evidence_inventory(
            args.manifest.resolve(),
            tuple(value.resolve() for value in args.measurement),
        )
        result = {
            "inventory_file": str(path.relative_to(ROOT)),
            "inventory_sha256": digest,
            "files": len(inventory["files"]),
            "network_used": False,
            "provider_calls": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
