#!/usr/bin/env python3
"""Offline validator for the public Urusilla agent-entry manifest.

The validator reads local declarative files only. It does not fetch a URL,
contact an agent or model, install code, publish a result, or authorize an
external effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "agent-entry.json"
SCHEMA_VERSION = "urusilla-agent-entry/1"
BASELINE_REVISION = "f612ea141e409693b27e93cefef0876eff9542ed"
QUICK_ARTIFACT_REVISION = "cd220adb311d8763009fc9b524b2633b117aac4d"
RAW_PREFIX = (
    "https://raw.githubusercontent.com/jaden3824/urusilla/"
    f"{BASELINE_REVISION}/"
)
QUICK_RAW_PREFIX = (
    "https://raw.githubusercontent.com/jaden3824/urusilla/"
    f"{QUICK_ARTIFACT_REVISION}/"
)
CAPSULE_SHA256 = (
    "sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_FILE_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_NODES = 50_000
MAX_STRING_CHARS = 65_536
MIRROR_OBSERVED_AT = "2026-08-21T11:44:37Z"

EXPECTED_ARTIFACTS = {
    "quick_60s_challenge": (
        "interop_lab/challenges/quick_60s.json",
        "application/json",
        "sha256:da39f621274bb054797d39536a39b671b26344c5082887ee48a4c3556ccac2e5",
        1596,
    ),
    "quick_response_schema": (
        "interop_lab/quick_response.schema.json",
        "application/schema+json",
        "sha256:9586e0fb2c5bfa40334a10779eb63a66ce6529c4411995b6d5d65c65195d5c07",
        835,
    ),
    "grammar_capsule": (
        "urusilla_capsule_v0_1.json",
        "application/json",
        "sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",
        33476,
    ),
    "action_state_capsule": (
        "urusilla_action_state_capsule.json",
        "application/json",
        "sha256:feb46f3987648bfee4f38daa284d103bba3d8c4311bd7ef7e12778f5d3cb7946",
        8609,
    ),
    "task_context_example": (
        "urusilla_task_context.example.json",
        "application/json",
        "sha256:c2d93094a07eeeea071c01fd14f3a9f396ba7a474672710aa2478abb64654a03",
        2285,
    ),
    "output_validator_example": (
        "urusilla_output_validator.example.json",
        "application/json",
        "sha256:48e8501548897fabb853e4682cc6e7c18cfcf3f2ceda84e6d5c11ae427116e95",
        272,
    ),
    "evolving_surface_capsule": (
        "urusilla_evolving_surface_capsule.json",
        "application/json",
        "sha256:ae5c63b225cda18a73154c9f911d95106d70ebc44024a1210ff5147ad042cfd4",
        8367,
    ),
    "evolving_surface_contract": (
        "EVOLVING_SURFACE.md",
        "text/markdown",
        "sha256:e8af299cd24582251e9c710787586015617a6a04c423051a886b86aad6a213b1",
        9119,
    ),
    "decode_challenge": (
        "interop_lab/evidence/challenge_001.md",
        "text/markdown",
        "sha256:bf31f88eb4fa0113d39775b24d76b6ccc7b8c1b90aeeb1a30b9a808119bf0dc0",
        3004,
    ),
    "decode_frame": (
        "interop_lab/evidence/challenge_001.b64url",
        "text/plain",
        "sha256:ff15a6f7647594f796be006c60e68842f70f3c567c3f148dd80cd3cf004d47cc",
        1001,
    ),
    "decode_expected": (
        "interop_lab/evidence/challenge_001.expected.json",
        "application/json",
        "sha256:a0d8a0d1f917791581630d52e960bfb6717244b42ada7a36eb0bd107f8632f3e",
        1575,
    ),
    "matched_eval_card": (
        "hf_dataset/README.md",
        "text/markdown",
        "sha256:1eaba1cb35dcdd6084e80bafb0143d0e9dd0a5f3b7138413dad310df06affd05",
        8739,
    ),
    "matched_eval_record": (
        "hf_dataset/data/challenge.jsonl",
        "application/x-ndjson",
        "sha256:b07125173b71585a943567cfd94ba55d9b375e5ae0024c21dbf2aa026c87066d",
        8532,
    ),
    "matched_eval_schema": (
        "hf_dataset/schema.json",
        "application/json",
        "sha256:621ffe26157e5026833cebcf99e6520f289739dca2f1fe6176734dc7413a873f",
        5890,
    ),
    "matched_eval_validator": (
        "hf_dataset/validate.py",
        "text/x-python",
        "sha256:e86ba800d961603ad08eb137205abe8dc49e8ddad91f400a7e125b50406fd353",
        21473,
    ),
}

NON_BASELINE_RAW_URLS = {
    "quick_60s_challenge": (
        QUICK_RAW_PREFIX + "interop_lab/challenges/quick_60s.json"
    ),
    "quick_response_schema": (
        QUICK_RAW_PREFIX + "interop_lab/quick_response.schema.json"
    ),
}

EXPECTED_PUBLIC_MIRRORS = {
    "quick_60s": {
        "source_kind": "github-discussion",
        "source_number": 8,
        "source_uri": "https://github.com/jaden3824/urusilla/discussions/8",
        "source_title": (
            "10-minute falsification challenge: can you break Urusilla’s "
            "evolving-session controller? (zero install; 0% general savings)"
        ),
        "source_state": "open",
        "source_locked": False,
        "source_created_at": "2026-08-21T10:43:50Z",
        "source_updated_at": "2026-08-21T10:44:12Z",
        "source_author_association": "OWNER",
        "body_path": "interop_lab/challenges/discussion_8.body.md",
        "body_bytes": 2746,
        "body_sha256": (
            "sha256:e30f0dfbfc613844ad9297bcbadeb0ff4ac6fe6998899081da334f5ccc15efbb"
        ),
        "mirror_status": "exact-body-at-source-updated-at",
    },
    "quick_10m": {
        "source_kind": "github-issue",
        "source_number": 9,
        "source_uri": "https://github.com/jaden3824/urusilla/issues/9",
        "source_title": "[Help wanted] Add one adversarial test for the evolving-session keep gate",
        "source_state": "open",
        "source_locked": False,
        "source_created_at": "2026-08-21T10:44:05Z",
        "source_updated_at": "2026-08-21T10:44:05Z",
        "source_author_association": "OWNER",
        "body_path": "interop_lab/challenges/issue_9.body.md",
        "body_bytes": 1943,
        "body_sha256": (
            "sha256:6f40446ef468f63bb79ac3296ad616ed28c564e743c17a159fcced79dcdcfbea"
        ),
        "mirror_status": "exact-body-at-source-updated-at",
    },
}

EXPECTED_TRACKS = {
    "quick_60s": {
        "time_budget_seconds": 60,
        "challenge_uri": (
            QUICK_RAW_PREFIX + "interop_lab/challenges/quick_60s.json"
        ),
        "offline_challenge": {
            "path": "interop_lab/challenges/quick_60s.json",
            "sha256": EXPECTED_ARTIFACTS["quick_60s_challenge"][2],
            "bytes": EXPECTED_ARTIFACTS["quick_60s_challenge"][3],
            "provenance": "frozen-one-fetch-artifact",
        },
        "canonical_submission_uri": "https://github.com/jaden3824/urusilla/discussions/8",
    },
    "quick_10m": {
        "time_budget_seconds": 600,
        "challenge_uri": "https://github.com/jaden3824/urusilla/issues/9",
        "offline_challenge": {
            "path": "interop_lab/challenges/issue_9.body.md",
            "sha256": EXPECTED_PUBLIC_MIRRORS["quick_10m"]["body_sha256"],
            "bytes": EXPECTED_PUBLIC_MIRRORS["quick_10m"]["body_bytes"],
            "provenance": "public-source-mirror-at-recorded-updated-at",
        },
        "canonical_submission_uri": (
            "https://github.com/jaden3824/urusilla/issues/new?"
            "template=quick-feedback.yml"
        ),
    },
    "decode": {
        "time_budget_seconds": 600,
        "challenge_uri": (
            RAW_PREFIX + "interop_lab/evidence/challenge_001.md"
        ),
        "offline_challenge": {
            "path": "interop_lab/evidence/challenge_001.md",
            "sha256": "sha256:bf31f88eb4fa0113d39775b24d76b6ccc7b8c1b90aeeb1a30b9a808119bf0dc0",
            "bytes": 3004,
            "provenance": "frozen-baseline-artifact",
        },
        "canonical_submission_uri": (
            "https://github.com/jaden3824/urusilla/issues/7"
        ),
    },
    "matched_eval": {
        "time_budget_seconds": None,
        "challenge_uri": RAW_PREFIX + "hf_dataset/data/challenge.jsonl",
        "offline_challenge": {
            "path": "hf_dataset/data/challenge.jsonl",
            "sha256": "sha256:b07125173b71585a943567cfd94ba55d9b375e5ae0024c21dbf2aa026c87066d",
            "bytes": 8532,
            "provenance": "frozen-baseline-artifact",
        },
        "canonical_submission_uri": (
            "https://github.com/jaden3824/urusilla/issues/new?"
            "template=interop-test.yml"
        ),
    },
}

ACCEPTED_OUTCOMES = (
    "exact",
    "mismatch",
    "counterexample",
    "ambiguity",
    "refusal",
    "null",
)

LOCAL_ENTRYPOINTS = {
    "quickstart_path": "AGENT_QUICKSTART.md",
    "entry_validator_path": "interop_lab/validate_agent_entry.py",
    "result_schema_path": "interop_lab/result.schema.json",
    "result_template_path": "interop_lab/result.template.json",
    "result_validator_path": "interop_lab/validate_result.py",
    "result_mapping_path": "interop_lab/RESULT_FORMAT_MAPPING.md",
    "challenge_mirror_provenance_path": (
        "interop_lab/challenges/public_challenges.provenance.json"
    ),
    "quick_feedback_form_path": ".github/ISSUE_TEMPLATE/quick-feedback.yml",
}


class ValidationError(ValueError):
    """Raised when the local agent-access surface is inconsistent."""


def _duplicate_rejector(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _resource_check(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES:
            raise ValidationError(f"JSON exceeds {MAX_NODES} values")
        if depth > MAX_DEPTH:
            raise ValidationError(f"JSON nesting exceeds {MAX_DEPTH}")
        if type(current) is str:
            if len(current) > MAX_STRING_CHARS:
                raise ValidationError(
                    f"JSON string exceeds {MAX_STRING_CHARS} characters"
                )
            current.encode("utf-8")
        elif type(current) is dict:
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in current)
        elif type(current) is float and not math.isfinite(current):
            raise ValidationError("non-finite JSON number")


def strict_json_loads(text: str) -> Any:
    if type(text) is not str:
        raise ValidationError("JSON input must be text")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValidationError(f"JSON exceeds {MAX_FILE_BYTES} bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_rejector,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValidationError(f"non-finite JSON number: {constant}")
            ),
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError) as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc
    _resource_check(value)
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError(f"manifest exceeds {MAX_FILE_BYTES} bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValidationError("manifest must not contain a UTF-8 BOM")
    try:
        return strict_json_loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValidationError("manifest is not valid UTF-8") from exc


def _load_local_json(path: Path, label: str) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {label}: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError(f"{label} exceeds {MAX_FILE_BYTES} bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValidationError(f"{label} must not contain a UTF-8 BOM")
    try:
        return strict_json_loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{label} is not valid UTF-8") from exc


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{path} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Iterable[str], path: str) -> None:
    wanted = set(expected)
    observed = set(value)
    if wanted != observed:
        raise ValidationError(
            f"{path} fields differ; "
            f"missing={sorted(wanted - observed)}, "
            f"extra={sorted(observed - wanted)}"
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _https_uri(value: Any, path: str) -> str:
    _require(type(value) is str and 1 <= len(value) <= 2_048, f"{path} is invalid")
    parsed = urlsplit(value)
    _require(
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None,
        f"{path} must be an HTTPS URI without credentials",
    )
    return value


def _safe_local_path(value: Any, path: str) -> str:
    _require(type(value) is str and value != "", f"{path} must be a path string")
    candidate = PurePosixPath(value)
    _require(
        not candidate.is_absolute() and ".." not in candidate.parts,
        f"{path} must remain inside the repository",
    )
    return candidate.as_posix()


def _validate_project(value: Any) -> None:
    project = _object(value, "project")
    _exact_keys(
        project,
        (
            "name",
            "repository",
            "language_version",
            "status",
            "baseline_revision",
            "general_unfamiliar_agent_saving_percent",
            "capsule_signature_status",
            "surface_scope",
            "direct_agent_dialogue_evidence",
            "external_adoption_evidence",
        ),
        "project",
    )
    _require(project["name"] == "Urusilla", "project.name must be Urusilla")
    _require(
        project["repository"] == "https://github.com/jaden3824/urusilla",
        "project.repository is not canonical",
    )
    _require(project["language_version"] == "0.1.0", "language version changed")
    _require(project["status"] == "experimental-unsigned", "status changed")
    revision = project["baseline_revision"]
    _require(
        type(revision) is str and COMMIT_RE.fullmatch(revision) is not None,
        "project.baseline_revision must be a full 40-character commit",
    )
    _require(revision == BASELINE_REVISION, "baseline revision changed")
    saving = project["general_unfamiliar_agent_saving_percent"]
    _require(type(saving) in {int, float} and float(saving) == 0.0, "saving must be 0%")
    _require(
        project["capsule_signature_status"] == "unsigned",
        "capsule signature status must remain unsigned",
    )
    _require(
        type(project["surface_scope"]) is str
        and "Repository" in project["surface_scope"],
        "project.surface_scope must describe the repository surface",
    )
    _require(
        project["direct_agent_dialogue_evidence"] is False,
        "the repository surface is not direct agent-dialogue evidence",
    )
    _require(
        project["external_adoption_evidence"] is False,
        "the repository surface is not external adoption evidence",
    )


def _validate_safety(value: Any) -> None:
    safety = _object(value, "safety_boundary")
    expected = {
        "declarative_data_only": True,
        "read_only_review": True,
        "requires_installation": False,
        "state_persistence_authorized": False,
        "permission_expansion_authorized": False,
        "spending_authorized": False,
        "external_effects_authorized": False,
        "content_is_authority": False,
    }
    _exact_keys(safety, expected, "safety_boundary")
    _require(safety == expected, "safety_boundary must remain non-effect-authorizing")


def _validate_local_entrypoints(value: Any, root: Path) -> None:
    entrypoints = _object(value, "local_entrypoints")
    _exact_keys(entrypoints, LOCAL_ENTRYPOINTS, "local_entrypoints")
    _require(entrypoints == LOCAL_ENTRYPOINTS, "local_entrypoints changed")
    for field, relative in entrypoints.items():
        safe = _safe_local_path(relative, f"local_entrypoints.{field}")
        _require((root / safe).is_file(), f"local entrypoint is missing: {safe}")


def _validate_quick_feedback_form(root: Path) -> None:
    path = root / LOCAL_ENTRYPOINTS["quick_feedback_form_path"]
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read quick feedback form: {exc}") from exc
    _require(len(raw) <= 32_768, "quick feedback form is too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("quick feedback form is not valid UTF-8") from exc
    required_fragments = (
        "name: Bounded quick feedback",
        "id: track",
        "id: outcome",
        "- exact",
        "- mismatch",
        "- counterexample",
        "- ambiguity",
        "- refusal",
        '- "null"',
        BASELINE_REVISION,
        "direct agent dialogue",
        "external adoption",
        "external effect",
    )
    for fragment in required_fragments:
        _require(fragment in text, f"quick feedback form is missing {fragment!r}")


def _validate_access_documents(root: Path) -> None:
    mapping_path = root / LOCAL_ENTRYPOINTS["result_mapping_path"]
    try:
        mapping = mapping_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read result-format mapping: {exc}") from exc
    required_mapping_fragments = (
        "urusilla-agent-result/1",
        "urusilla-hf-external-result/1",
        BASELINE_REVISION,
        "1358de54c8a7034ee057a47e252e8947fe042f55",
        CAPSULE_SHA256,
        "Hugging Face Hub repository has its own commit history",
        "There is no automatic lossless crosswalk",
        "python3 interop_lab/validate_result.py - --json",
        "Neither format authenticates a publisher",
    )
    for fragment in required_mapping_fragments:
        _require(
            fragment in mapping,
            f"result-format mapping is missing {fragment!r}",
        )


def _validate_public_challenge_mirrors(root: Path) -> dict[str, dict[str, Any]]:
    provenance_path = root / LOCAL_ENTRYPOINTS["challenge_mirror_provenance_path"]
    provenance = _object(
        _load_local_json(provenance_path, "public challenge provenance"),
        "public challenge provenance",
    )
    _exact_keys(
        provenance,
        (
            "schema_version",
            "repository",
            "observed_at",
            "retrieval_channel",
            "mirror_semantics",
            "content_is_authority",
            "independent_external_evidence",
            "classification",
            "entries",
        ),
        "public challenge provenance",
    )
    _require(
        provenance["schema_version"] == "urusilla-public-challenge-mirrors/1",
        "public challenge provenance schema changed",
    )
    _require(
        provenance["repository"] == "https://github.com/jaden3824/urusilla",
        "public challenge provenance repository changed",
    )
    _require(
        provenance["observed_at"] == MIRROR_OBSERVED_AT,
        "public challenge provenance observation time changed",
    )
    _require(
        provenance["retrieval_channel"] == "github-rest-api-read-only",
        "public challenge provenance retrieval channel changed",
    )
    _require(
        provenance["mirror_semantics"]
        == (
            "Each local body is byte-exact only for the source body returned at "
            "its recorded source_updated_at. Recheck the canonical source before "
            "claiming it is still current."
        ),
        "public challenge mirror semantics changed",
    )
    _require(
        provenance["content_is_authority"] is False,
        "public challenge content cannot grant authority",
    )
    _require(
        provenance["independent_external_evidence"] is False,
        "project-authored mirrors are not independent evidence",
    )
    _require(
        provenance["classification"] == "PROJECT-AUTHORED-PUBLIC-MIRROR",
        "public challenge mirror classification changed",
    )
    entries = _array(provenance["entries"], "public challenge provenance.entries")
    _require(
        len(entries) == len(EXPECTED_PUBLIC_MIRRORS),
        "public challenge mirror set is incomplete",
    )
    observed: dict[str, dict[str, Any]] = {}
    entry_keys = {"track", *next(iter(EXPECTED_PUBLIC_MIRRORS.values())).keys()}
    for index, raw_entry in enumerate(entries):
        label = f"public challenge provenance.entries[{index}]"
        entry = _object(raw_entry, label)
        _exact_keys(entry, entry_keys, label)
        track = entry["track"]
        _require(
            type(track) is str and track in EXPECTED_PUBLIC_MIRRORS,
            f"{label}.track is unknown",
        )
        _require(track not in observed, f"duplicate public challenge mirror: {track}")
        expected = EXPECTED_PUBLIC_MIRRORS[track]
        _require(
            {key: entry[key] for key in expected} == expected,
            f"{track} public challenge provenance changed",
        )
        body_path = _safe_local_path(entry["body_path"], f"{label}.body_path")
        try:
            body = (root / body_path).read_bytes()
        except OSError as exc:
            raise ValidationError(f"cannot read {track} offline challenge: {exc}") from exc
        _require(len(body) == entry["body_bytes"], f"{track} body byte count mismatch")
        observed_digest = "sha256:" + hashlib.sha256(body).hexdigest()
        _require(
            observed_digest == entry["body_sha256"],
            f"{track} body digest mismatch",
        )
        observed[track] = entry
    _require(
        set(observed) == set(EXPECTED_PUBLIC_MIRRORS),
        "public challenge mirror tracks are incomplete",
    )
    return observed


def _validate_artifacts(value: Any, root: Path) -> set[str]:
    artifacts = _array(value, "artifacts")
    _require(len(artifacts) == len(EXPECTED_ARTIFACTS), "artifact set is incomplete")
    observed_ids: set[str] = set()
    observed_paths: set[str] = set()
    for index, raw_artifact in enumerate(artifacts):
        path_label = f"artifacts[{index}]"
        artifact = _object(raw_artifact, path_label)
        _exact_keys(
            artifact,
            ("id", "path", "raw_url", "sha256", "bytes", "media_type"),
            path_label,
        )
        artifact_id = artifact["id"]
        _require(
            type(artifact_id) is str and artifact_id in EXPECTED_ARTIFACTS,
            f"{path_label}.id is unknown",
        )
        _require(artifact_id not in observed_ids, f"duplicate artifact id: {artifact_id}")
        observed_ids.add(artifact_id)
        (
            expected_path,
            expected_media_type,
            expected_digest,
            expected_bytes,
        ) = EXPECTED_ARTIFACTS[artifact_id]
        local_path = _safe_local_path(artifact["path"], f"{path_label}.path")
        _require(local_path == expected_path, f"{artifact_id} path changed")
        _require(local_path not in observed_paths, f"duplicate artifact path: {local_path}")
        observed_paths.add(local_path)
        raw_url = _https_uri(artifact["raw_url"], f"{path_label}.raw_url")
        expected_raw_url = NON_BASELINE_RAW_URLS.get(
            artifact_id,
            RAW_PREFIX + local_path,
        )
        _require(
            raw_url == expected_raw_url,
            f"{artifact_id} raw_url must use the full frozen commit and raw bytes",
        )
        digest = artifact["sha256"]
        _require(
            type(digest) is str and SHA256_RE.fullmatch(digest) is not None,
            f"{artifact_id} sha256 is invalid",
        )
        _require(digest == expected_digest, f"{artifact_id} frozen digest changed")
        byte_count = artifact["bytes"]
        _require(
            type(byte_count) is int and 0 < byte_count <= MAX_FILE_BYTES,
            f"{artifact_id} bytes is invalid",
        )
        _require(byte_count == expected_bytes, f"{artifact_id} frozen byte count changed")
        _require(
            artifact["media_type"] == expected_media_type,
            f"{artifact_id} media_type changed",
        )
        target = root / local_path
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise ValidationError(f"cannot read artifact {local_path}: {exc}") from exc
        _require(len(content) == byte_count, f"{artifact_id} byte count mismatch")
        observed_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        _require(observed_digest == digest, f"{artifact_id} digest mismatch")

    _require(observed_ids == set(EXPECTED_ARTIFACTS), "artifact ids are incomplete")
    grammar = next(
        artifact for artifact in artifacts if artifact["id"] == "grammar_capsule"
    )
    _require(grammar["sha256"] == CAPSULE_SHA256, "Grammar Capsule digest changed")
    return observed_ids


def _validate_tracks(
    value: Any,
    artifact_ids: set[str],
    mirrors: Mapping[str, Mapping[str, Any]],
    root: Path,
) -> None:
    tracks = _array(value, "tracks")
    _require(len(tracks) == len(EXPECTED_TRACKS), "exactly four tracks are required")
    observed: set[str] = set()
    for index, raw_track in enumerate(tracks):
        label = f"tracks[{index}]"
        track = _object(raw_track, label)
        _exact_keys(
            track,
            (
                "id",
                "time_budget_seconds",
                "purpose",
                "challenge_uri",
                "offline_challenge",
                "canonical_submission_uri",
                "artifact_ids",
                "requires_installation",
                "accepted_outcomes",
            ),
            label,
        )
        track_id = track["id"]
        _require(
            type(track_id) is str and track_id in EXPECTED_TRACKS,
            f"{label}.id is unknown",
        )
        _require(track_id not in observed, f"duplicate track: {track_id}")
        observed.add(track_id)
        expected = EXPECTED_TRACKS[track_id]
        for field in (
            "time_budget_seconds",
            "challenge_uri",
            "canonical_submission_uri",
        ):
            _require(track[field] == expected[field], f"{track_id}.{field} changed")
        offline = _object(track["offline_challenge"], f"{track_id}.offline_challenge")
        _exact_keys(
            offline,
            ("path", "sha256", "bytes", "provenance"),
            f"{track_id}.offline_challenge",
        )
        _require(
            offline == expected["offline_challenge"],
            f"{track_id}.offline_challenge changed",
        )
        offline_path = _safe_local_path(
            offline["path"], f"{track_id}.offline_challenge.path"
        )
        try:
            offline_body = (root / offline_path).read_bytes()
        except OSError as exc:
            raise ValidationError(
                f"cannot read {track_id} offline challenge: {exc}"
            ) from exc
        _require(
            len(offline_body) == offline["bytes"],
            f"{track_id} offline challenge byte count mismatch",
        )
        _require(
            "sha256:" + hashlib.sha256(offline_body).hexdigest()
            == offline["sha256"],
            f"{track_id} offline challenge digest mismatch",
        )
        if offline["provenance"] == "public-source-mirror-at-recorded-updated-at":
            _require(
                track_id in mirrors,
                f"{track_id} has no public-mirror provenance record",
            )
            mirror = mirrors[track_id]
            _require(
                offline["path"] == mirror["body_path"]
                and offline["sha256"] == mirror["body_sha256"]
                and offline["bytes"] == mirror["body_bytes"],
                f"{track_id} offline challenge differs from its provenance record",
            )
        _https_uri(track["challenge_uri"], f"{track_id}.challenge_uri")
        _https_uri(
            track["canonical_submission_uri"],
            f"{track_id}.canonical_submission_uri",
        )
        _require(
            type(track["purpose"]) is str and 1 <= len(track["purpose"]) <= 512,
            f"{track_id}.purpose is invalid",
        )
        selected = _array(track["artifact_ids"], f"{track_id}.artifact_ids")
        _require(bool(selected), f"{track_id} must name at least one artifact")
        _require(
            all(type(item) is str for item in selected)
            and len(selected) == len(set(selected))
            and set(selected) <= artifact_ids,
            f"{track_id}.artifact_ids is invalid",
        )
        _require(
            track["requires_installation"] is False,
            f"{track_id} must remain no-install",
        )
        _require(
            track["accepted_outcomes"] == list(ACCEPTED_OUTCOMES),
            f"{track_id} must accept exact, negative, refusal, and null outcomes",
        )
    _require(observed == set(EXPECTED_TRACKS), "track set is incomplete")


def validate_entry(value: Any, *, root: Path = REPO_ROOT) -> dict[str, Any]:
    entry = _object(value, "agent-entry")
    _exact_keys(
        entry,
        (
            "schema_version",
            "project",
            "safety_boundary",
            "local_entrypoints",
            "artifacts",
            "tracks",
        ),
        "agent-entry",
    )
    _require(entry["schema_version"] == SCHEMA_VERSION, "schema_version changed")
    _validate_project(entry["project"])
    _validate_safety(entry["safety_boundary"])
    _validate_local_entrypoints(entry["local_entrypoints"], root)
    _validate_quick_feedback_form(root)
    _validate_access_documents(root)
    mirrors = _validate_public_challenge_mirrors(root)
    artifact_ids = _validate_artifacts(entry["artifacts"], root)
    _validate_tracks(entry["tracks"], artifact_ids, mirrors, root)
    return {
        "valid": True,
        "network_used": False,
        "baseline_revision": BASELINE_REVISION,
        "artifact_count": len(artifact_ids),
        "track_count": len(EXPECTED_TRACKS),
        "public_challenge_mirror_count": len(mirrors),
        "public_challenge_mirrors_current_status": "snapshot-only-network-not-checked",
        "general_unfamiliar_agent_saving_percent": 0.0,
        "capsule_signature_status": "unsigned",
        "direct_agent_dialogue_evidence": False,
        "external_adoption_evidence": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate agent-entry.json against local frozen bytes only."
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="path to agent-entry.json",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_entry(load_manifest(args.manifest), root=REPO_ROOT)
    except ValidationError as exc:
        if args.json:
            print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            "valid: offline agent surface; "
            f"{report['artifact_count']} frozen artifacts; "
            f"{report['track_count']} bounded tracks"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
