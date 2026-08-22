"""Compile exact artifact bytes into conservative finite-bound token vectors.

The older :mod:`finite_bound_preflight_v1` intentionally binds opaque inventory
only.  This module is a separate semantic layer: it accepts that preflight's
exact bytes only when they also satisfy a closed compilation contract.  It then
tokenizes every frozen final model-input prompt, closes every provider-call node
over a finite DAG, derives cumulative vectors for session lengths 1..128, and
invokes the separately versioned arithmetic feasibility screen.

This is still a zero-call conditional screen.  A declared source cap is not an
authenticated provider receipt, a compiled prompt is not proof that a provider
used it, and a successful arithmetic screen authorizes no receiver call or
performance claim.  Those boundaries are explicit in every result.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence

from .contract import (
    IDENTIFIER_RE,
    SHA256_RE,
    VerificationError,
    canonical_json,
    sha256_ref,
)
from .feasibility_kill_screen_v1 import (
    PATHS,
    PHASES,
    PLAN_STATUS,
    SESSION_LENGTHS,
    TARGET_REDUCTION_BASIS_POINTS,
)
from .feasibility_kill_screen_v3 import (
    EVALUATION_REFERENCE,
    FEASIBILITY_PLAN_SCHEMA,
    run_feasibility_kill_screen,
)
from .finite_bound_preflight_v1 import (
    BASELINES,
    KINDS,
    PATH_DAG_SCHEMA,
    SUCCESS_RECEIPT_SCHEMA,
    TOKEN_SCOPE,
    TOTAL_CAP_SCHEMA,
    build_finite_bound_preflight_manifest,
)


COMPILATION_MANIFEST_SCHEMA = "urusilla-initial-goal-content-bound-case/1"
COMPILATION_RESULT_SCHEMA = "urusilla-initial-goal-content-bound-screen/1"
COMPILER_BUNDLE_SCHEMA = "urusilla-initial-goal-content-bound-compiler-bundle/1"
TOKENIZER_SPEC_SCHEMA = "urusilla-initial-goal-tokenizer-spec/1"
FINAL_INPUT_BINDING_SCHEMA = "urusilla-initial-goal-final-input-binding/1"
BASELINE_SUCCESS_EVIDENCE_SCHEMA = (
    "urusilla-initial-goal-baseline-success-evidence/3"
)
CAP_ENFORCEMENT_SOURCE = (
    "reject-before-provider-call-if-complete-input-plus-visible-output-plus-"
    "billed-reasoning-plus-unclassified-exceeds-maximum-total-tokens"
)
TOKENIZER_ENGINES = ("utf8-byte-units", "huggingface-tokenizers-json")
OCCURRENCES = ("once", "per-task")
TOKENIZERS_DISTRIBUTION = "tokenizers"
TOKENIZERS_VERSION = "0.21.4"
BYTE_CONFORMANCE_RECEIVER_MODEL_ID = "synthetic-byte-conformance-receiver"
_MAX_TOKEN_BOUND = (1 << 63) - 1
_MAX_CASES = 128
_MAX_COMPILATION_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_SUCCESS_EVIDENCE_BYTES = 4 * 1024 * 1024
_MAX_RECEIVER_OUTPUT_UTF8_BYTES = 256 * 1024
_MAX_CASE_INPUT_BYTES = 48 * 1024 * 1024
_MAX_BATCH_INPUT_BYTES = 128 * 1024 * 1024
_MAX_NODES_PER_CASE = 256
_MAX_NODES_PER_BATCH = 2048
_MAX_DAG_EDGES_PER_CASE = 4096
_MAX_DAG_EDGES_PER_BATCH = 16384
_MAX_PROMPT_REFERENCES_PER_CASE = 8192
_MAX_PROMPT_REFERENCES_PER_BATCH = 32768
_MAX_UNIQUE_TOKENIZERS_PER_BATCH = 32
_MAX_TOKENIZER_DISTRIBUTION_FILES = 4096
_MAX_TOKENIZER_DISTRIBUTION_BYTES = 64 * 1024 * 1024
_MAX_PLAN_BYTES = 32 * 1024 * 1024
_MAX_SCREEN_BYTES = 32 * 1024 * 1024
_MAX_RESULT_BYTES = 64 * 1024 * 1024
_COMPILER_BUNDLE_FILES = (
    "content_bound_compiler_v1.py",
    "contract.py",
    "feasibility_kill_screen_v1.py",
    "feasibility_kill_screen_v3.py",
    "finite_bound_preflight_v1.py",
)


class ContentBoundCompilerError(VerificationError):
    """The supplied bytes do not close the content-derived compiler contract."""


@dataclass(frozen=True)
class ContentBoundCase:
    """One exact row and its replayable, task-ordered baseline evidence."""

    artifacts: Mapping[str, Mapping[str, bytes]]
    baseline_success_receipts: Mapping[str, bytes]
    compilation_manifest: bytes


def _keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if any(type(key) is not str for key in value) or set(value) != expected:
        raise ContentBoundCompilerError(f"{path}:exact-keys-required")


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        raise ContentBoundCompilerError(f"{path}:identifier-required")
    return value


def _json(raw: bytes, path: str) -> Any:
    if type(raw) is not bytes or not raw:
        raise ContentBoundCompilerError(f"{path}:nonempty-bytes-required")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ContentBoundCompilerError(f"{path}:duplicate-json-key")
            result[key] = item
        return result

    import json

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        if canonical_json(value).encode("utf-8") != raw:
            raise ContentBoundCompilerError(f"{path}:canonical-json-bytes-required")
        return value
    except ContentBoundCompilerError:
        raise
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        raise ContentBoundCompilerError(
            f"{path}:canonical-json-bytes-required"
        ) from exc


def _bounded_raw(raw: Any, *, maximum: int, path: str) -> bytes:
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise ContentBoundCompilerError(f"{path}:bounded-nonempty-bytes-required")
    return raw


def _canonical_size(value: object, *, maximum: int, path: str) -> int:
    try:
        size = len(canonical_json(value).encode("utf-8"))
    except (RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise ContentBoundCompilerError(f"{path}:canonical-size-unavailable") from exc
    if size > maximum:
        raise ContentBoundCompilerError(f"{path}:serialized-byte-limit-exceeded")
    return size


def _artifact_bundles(
    artifacts: Mapping[str, Mapping[str, bytes]],
) -> dict[str, dict[str, bytes]]:
    if type(artifacts) is not dict or set(artifacts) != set(KINDS):
        raise ContentBoundCompilerError("artifacts:all-closed-kinds-required")
    result: dict[str, dict[str, bytes]] = {}
    for kind in KINDS:
        bundle = artifacts[kind]
        if type(bundle) is not dict or not bundle:
            raise ContentBoundCompilerError(f"artifacts.{kind}:nonempty-object-required")
        if any(
            type(key) is not str
            or IDENTIFIER_RE.fullmatch(key) is None
            or type(raw) is not bytes
            or not raw
            for key, raw in bundle.items()
        ):
            raise ContentBoundCompilerError(f"artifacts.{kind}:invalid-artifact")
        result[kind] = dict(bundle)
    return result


def _load_graph(raw: bytes, artifact_id: str) -> dict[str, dict[str, tuple[str, ...]]]:
    value = _json(raw, f"path-dag.{artifact_id}")
    if type(value) is not dict:
        raise ContentBoundCompilerError("path-dag:object-required")
    _keys(value, {"schema_version", "paths"}, "path-dag")
    if value["schema_version"] != PATH_DAG_SCHEMA or type(value["paths"]) is not dict:
        raise ContentBoundCompilerError("path-dag:known-schema-required")
    _keys(value["paths"], set(PATHS), "path-dag.paths")
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for path_name in PATHS:
        path = value["paths"][path_name]
        if type(path) is not dict:
            raise ContentBoundCompilerError(f"path-dag.paths.{path_name}:object-required")
        _keys(path, {"entry", "edges"}, f"path-dag.paths.{path_name}")
        entry = _identifier(path["entry"], f"path-dag.paths.{path_name}.entry")
        edges = path["edges"]
        if type(edges) is not dict or not edges or entry not in edges:
            raise ContentBoundCompilerError(f"path-dag.paths.{path_name}:closed-graph-required")
        graph: dict[str, tuple[str, ...]] = {}
        for node, targets in edges.items():
            node = _identifier(node, f"path-dag.paths.{path_name}.node")
            if type(targets) is not list:
                raise ContentBoundCompilerError(
                    f"path-dag.paths.{path_name}.{node}:edge-array-required"
                )
            checked = tuple(
                _identifier(target, f"path-dag.paths.{path_name}.{node}.edge")
                for target in targets
            )
            if len(set(checked)) != len(checked):
                raise ContentBoundCompilerError(
                    f"path-dag.paths.{path_name}.{node}:duplicate-edge-forbidden"
                )
            graph[node] = checked
        if any(target not in graph for targets in graph.values() for target in targets):
            raise ContentBoundCompilerError(f"path-dag.paths.{path_name}:dangling-edge")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ContentBoundCompilerError(f"path-dag.paths.{path_name}:cycle")
            if node in visited:
                return
            visiting.add(node)
            for target in graph[node]:
                visit(target)
            visiting.remove(node)
            visited.add(node)

        visit(entry)
        if visited != set(graph) or not any(not targets for targets in graph.values()):
            raise ContentBoundCompilerError(
                f"path-dag.paths.{path_name}:all-nodes-must-reach-from-entry"
            )
        result[path_name] = {"__entry__": (entry,), **graph}
    return result


def _load_caps(raw_caps: Mapping[str, bytes]) -> dict[str, int]:
    result: dict[str, int] = {}
    for artifact_id, raw in raw_caps.items():
        value = _json(raw, f"total-cap.{artifact_id}")
        if type(value) is not dict:
            raise ContentBoundCompilerError(f"total-cap.{artifact_id}:object-required")
        _keys(
            value,
            {
                "schema_version",
                "maximum_total_tokens",
                "token_scope",
                "enforcement_stage",
                "overflow_action",
                "enforcement_source_utf8",
            },
            f"total-cap.{artifact_id}",
        )
        cap = value["maximum_total_tokens"]
        if (
            value["schema_version"] != TOTAL_CAP_SCHEMA
            or type(cap) is not int
            or cap <= 0
            or cap > _MAX_TOKEN_BOUND
            or value["token_scope"] != TOKEN_SCOPE
            or value["enforcement_stage"] != "before-provider-call"
            or value["overflow_action"] != "do-not-call"
            or value["enforcement_source_utf8"] != CAP_ENFORCEMENT_SOURCE
        ):
            raise ContentBoundCompilerError(
                f"total-cap.{artifact_id}:exact-compiler-cap-contract-required"
            )
        result[artifact_id] = cap
    return result


def _load_final_input_binding(
    raw: bytes,
    *,
    artifact_id: str,
    prompt_ids: set[str],
    receiver_model_id: str,
    receiver_settings_sha256: str,
    tokenizer_id: str,
    tokenizer_spec_artifact_id: str,
) -> None:
    value = _json(raw, f"final-input-binding.{artifact_id}")
    if type(value) is not dict:
        raise ContentBoundCompilerError("final-input-binding:object-required")
    _keys(
        value,
        {
            "schema_version",
            "rendering_stage",
            "provider_additional_template",
            "model_input_media_type",
            "canonical_prompt_artifact_ids",
            "receiver_model_id",
            "receiver_settings_sha256",
            "tokenizer_id",
            "tokenizer_spec_artifact_id",
            "binding_scope",
            "provider_authentication",
        },
        "final-input-binding",
    )
    ids = value["canonical_prompt_artifact_ids"]
    if (
        value["schema_version"] != FINAL_INPUT_BINDING_SCHEMA
        or value["rendering_stage"] != "already-rendered-exact-model-input"
        or value["provider_additional_template"] != "forbidden"
        or value["model_input_media_type"] != "text/plain;charset=utf-8"
        or type(ids) is not list
        or any(type(item) is not str for item in ids)
        or len(ids) != len(set(ids))
        or set(ids) != prompt_ids
        or value["receiver_model_id"] != receiver_model_id
        or value["receiver_settings_sha256"] != receiver_settings_sha256
        or value["tokenizer_id"] != tokenizer_id
        or value["tokenizer_spec_artifact_id"] != tokenizer_spec_artifact_id
        or value["binding_scope"] != "declared-final-input-conformance-only"
        or value["provider_authentication"] != "not-provided"
    ):
        raise ContentBoundCompilerError(
            "final-input-binding:exact-final-prompt-set-required"
        )


def _load_success_evidence(
    *,
    receipts: Mapping[str, bytes],
    case_id: str,
    domain_id: str,
    tokenizer_id: str,
    receiver_model_id: str,
    receiver_settings_sha256: str,
    task_ids: list[str],
    baseline_prompt_ids: Mapping[str, list[str]],
    prompts: Mapping[str, bytes],
    bundle_hashes: Mapping[str, str],
    compilation_manifest_sha256: str,
) -> tuple[dict[str, dict[str, object]], dict[str, bytes]]:
    if type(receipts) is not dict or set(receipts) != set(BASELINES):
        raise ContentBoundCompilerError(
            "baseline-success-evidence:both-closed-baselines-required"
        )
    summaries: dict[str, dict[str, object]] = {}
    legacy_receipts: dict[str, bytes] = {}
    for baseline in BASELINES:
        raw = _bounded_raw(
            receipts[baseline],
            maximum=_MAX_SUCCESS_EVIDENCE_BYTES,
            path=f"baseline-success-evidence.{baseline}",
        )
        value = _json(raw, f"baseline-success-evidence.{baseline}")
        if type(value) is not dict:
            raise ContentBoundCompilerError(
                f"baseline-success-evidence.{baseline}:object-required"
            )
        _keys(
            value,
            {
                "schema_version",
                "case_id",
                "baseline_path",
                "domain_id",
                "tokenizer_id",
                "artifact_bundle_sha256",
                "compilation_manifest_sha256",
                "receiver_model_id",
                "receiver_settings_sha256",
                "scorer_sha256",
                "tasks",
            },
            f"baseline-success-evidence.{baseline}",
        )
        tasks = value["tasks"]
        if (
            value["schema_version"] != BASELINE_SUCCESS_EVIDENCE_SCHEMA
            or value["case_id"] != case_id
            or value["baseline_path"] != baseline
            or value["domain_id"] != domain_id
            or value["tokenizer_id"] != tokenizer_id
            or value["artifact_bundle_sha256"] != dict(bundle_hashes)
            or value["compilation_manifest_sha256"]
            != compilation_manifest_sha256
            or value["receiver_model_id"] != receiver_model_id
            or value["receiver_settings_sha256"] != receiver_settings_sha256
            or type(value["scorer_sha256"]) is not str
            or SHA256_RE.fullmatch(value["scorer_sha256"]) is None
            or type(tasks) is not list
            or len(tasks) != len(SESSION_LENGTHS)
        ):
            raise ContentBoundCompilerError(
                f"baseline-success-evidence.{baseline}:binding-mismatch"
            )
        expected_prompt_ids = baseline_prompt_ids[baseline]
        safe: list[bool] = []
        task_bindings: list[dict[str, object]] = []
        for index, task in enumerate(tasks):
            path = f"baseline-success-evidence.{baseline}.tasks[{index}]"
            if type(task) is not dict:
                raise ContentBoundCompilerError(f"{path}:object-required")
            _keys(
                task,
                {
                    "task_id",
                    "task_input_sha256",
                    "receiver_output_utf8",
                    "attempt_ledger_sha256",
                    "scorer_output",
                    "safely_completed",
                },
                path,
            )
            output = task["receiver_output_utf8"]
            completed = task["safely_completed"]
            scorer_output = task["scorer_output"]
            if (
                task["task_id"] != task_ids[index]
                or task["task_input_sha256"]
                != sha256_ref(prompts[expected_prompt_ids[index]])
                or type(task["attempt_ledger_sha256"]) is not str
                or SHA256_RE.fullmatch(task["attempt_ledger_sha256"]) is None
                or type(completed) is not bool
                or scorer_output
                != ("safe-success" if completed else "not-safe-success")
                or (output is not None and type(output) is not str)
                or (completed and (type(output) is not str or not output))
            ):
                raise ContentBoundCompilerError(f"{path}:task-binding-mismatch")
            if type(output) is str:
                try:
                    encoded_output = output.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise ContentBoundCompilerError(
                        f"{path}:receiver-output-invalid-utf8"
                    ) from exc
                if len(encoded_output) > _MAX_RECEIVER_OUTPUT_UTF8_BYTES:
                    raise ContentBoundCompilerError(
                        f"{path}:receiver-output-byte-limit-exceeded"
                    )
            safe.append(completed)
            task_bindings.append(
                {
                    "task_id": task_ids[index],
                    "task_input_sha256": task["task_input_sha256"],
                    "receiver_output_sha256": (
                        None
                        if output is None
                        else sha256_ref(output.encode("utf-8"))
                    ),
                    "attempt_ledger_sha256": task["attempt_ledger_sha256"],
                    "scorer_output_sha256": sha256_ref(
                        scorer_output.encode("utf-8")
                    ),
                    "safely_completed": completed,
                }
            )
        summaries[baseline] = {
            "schema_version": BASELINE_SUCCESS_EVIDENCE_SCHEMA,
            "receipt_sha256": sha256_ref(raw),
            "receiver_model_id": receiver_model_id,
            "receiver_settings_sha256": receiver_settings_sha256,
            "scorer_sha256": value["scorer_sha256"],
            "task_order_sha256": sha256_ref(task_ids),
            "task_bindings_sha256": sha256_ref(task_bindings),
            "safe_successes_by_n": [
                sum(int(item) for item in safe[:n]) for n in SESSION_LENGTHS
            ],
        }
        legacy_receipts[baseline] = canonical_json(
            {
                "schema_version": SUCCESS_RECEIPT_SCHEMA,
                "baseline_path": baseline,
                "artifact_bundle_sha256": dict(bundle_hashes),
                "safe_success_by_item": safe,
            }
        ).encode("utf-8")
    return summaries, legacy_receipts


@lru_cache(maxsize=4)
def _distribution_binding(distribution_name: str, expected_version: str) -> dict[str, object]:
    """Bind the actual installed package bytes, not only its version label."""

    try:
        distribution = metadata.distribution(distribution_name)
        if distribution.version != expected_version or distribution.files is None:
            raise ContentBoundCompilerError("tokenizer-runtime:version-drift")
        if len(distribution.files) > _MAX_TOKENIZER_DISTRIBUTION_FILES:
            raise ContentBoundCompilerError("tokenizer-runtime:package-file-budget-exceeded")
        files: list[dict[str, object]] = []
        total_bytes = 0
        for relative in sorted(distribution.files, key=lambda item: str(item)):
            path = Path(distribution.locate_file(relative))
            if not path.is_file():
                raise ContentBoundCompilerError("tokenizer-runtime:package-file-missing")
            raw = path.read_bytes()
            total_bytes += len(raw)
            if total_bytes > _MAX_TOKENIZER_DISTRIBUTION_BYTES:
                raise ContentBoundCompilerError(
                    "tokenizer-runtime:package-byte-budget-exceeded"
                )
            files.append(
                {
                    "path": str(relative),
                    "byte_count": len(raw),
                    "sha256": sha256_ref(raw),
                }
            )
        if not files:
            raise ContentBoundCompilerError("tokenizer-runtime:package-files-empty")
        return {
            "distribution": distribution_name,
            "version": expected_version,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "files_sha256": sha256_ref(files),
        }
    except ContentBoundCompilerError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContentBoundCompilerError("tokenizer-runtime:package-bind-failed") from exc


def _deterministic_tokenizer_json(raw: bytes, *, artifact_id: str) -> str:
    """Reject tokenizer configurations with unsupported or stochastic models."""

    import json

    path = f"tokenizer-model.{artifact_id}"

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ContentBoundCompilerError(f"{path}:duplicate-json-key")
            result[key] = item
        return result

    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=pairs)
    except ContentBoundCompilerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ContentBoundCompilerError(f"{path}:valid-json-required") from exc
    if type(value) is not dict or type(value.get("model")) is not dict:
        raise ContentBoundCompilerError(f"{path}:model-object-required")
    model_type = value["model"].get("type")
    if model_type not in {"BPE", "WordPiece", "WordLevel"}:
        raise ContentBoundCompilerError(f"{path}:deterministic-model-type-required")

    def inspect(item: Any) -> None:
        if type(item) is dict:
            for key, nested in item.items():
                if key == "dropout" and nested is not None:
                    if type(nested) not in {int, float} or nested != 0:
                        raise ContentBoundCompilerError(
                            f"{path}:stochastic-dropout-forbidden"
                        )
                inspect(nested)
        elif type(item) is list:
            for nested in item:
                inspect(nested)

    inspect(value)
    return text


def _load_token_counter(
    *,
    tokenizer_id: str,
    spec_id: str,
    raw_tokenizer_artifacts: Mapping[str, bytes],
    runtime_cache: dict[
        str, tuple[Callable[[bytes], int], str, str]
    ],
) -> tuple[Callable[[bytes], int], str, str]:
    spec = _json(raw_tokenizer_artifacts[spec_id], f"tokenizer-spec.{spec_id}")
    if type(spec) is not dict:
        raise ContentBoundCompilerError("tokenizer-spec:object-required")
    _keys(
        spec,
        {
            "schema_version",
            "tokenizer_id",
            "engine",
            "model_artifact_id",
            "implementation_distribution",
            "implementation_version",
            "add_special_tokens",
        },
        "tokenizer-spec",
    )
    engine = spec["engine"]
    if (
        spec["schema_version"] != TOKENIZER_SPEC_SCHEMA
        or spec["tokenizer_id"] != tokenizer_id
        or engine not in TOKENIZER_ENGINES
        or type(spec["add_special_tokens"]) is not bool
    ):
        raise ContentBoundCompilerError("tokenizer-spec:known-exact-spec-required")

    model_id = spec["model_artifact_id"]
    if engine == "utf8-byte-units":
        if not (
            model_id is None
            and spec["implementation_distribution"] is None
            and spec["implementation_version"] == "builtin/1"
            and spec["add_special_tokens"] is False
            and set(raw_tokenizer_artifacts) == {spec_id}
        ):
            raise ContentBoundCompilerError("tokenizer-spec:invalid-byte-engine")

        cache_key = sha256_ref({"engine": engine, "spec": spec})
        cached = runtime_cache.get(cache_key)
        if cached is not None:
            return cached

        def count_bytes(raw: bytes) -> int:
            raw.decode("utf-8")
            return len(raw)

        result = (count_bytes, sha256_ref(spec), str(engine))
        runtime_cache[cache_key] = result
        return result

    model_id = _identifier(model_id, "tokenizer-spec.model_artifact_id")
    if (
        model_id == spec_id
        or set(raw_tokenizer_artifacts) != {spec_id, model_id}
        or spec["implementation_distribution"] != TOKENIZERS_DISTRIBUTION
        or spec["implementation_version"] != TOKENIZERS_VERSION
    ):
        raise ContentBoundCompilerError("tokenizer-spec:invalid-huggingface-engine")
    model_sha256 = sha256_ref(raw_tokenizer_artifacts[model_id])
    cache_key = sha256_ref(
        {"engine": engine, "spec": spec, "model_sha256": model_sha256}
    )
    cached = runtime_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        distribution_binding = _distribution_binding(
            TOKENIZERS_DISTRIBUTION, TOKENIZERS_VERSION
        )
        from tokenizers import Tokenizer  # type: ignore[import-not-found]

        tokenizer_text = _deterministic_tokenizer_json(
            raw_tokenizer_artifacts[model_id], artifact_id=model_id
        )
        tokenizer = Tokenizer.from_str(tokenizer_text)
    except ContentBoundCompilerError:
        raise
    except Exception as exc:
        raise ContentBoundCompilerError("tokenizer-runtime:load-failed") from exc

    add_special_tokens = spec["add_special_tokens"]

    def count_huggingface(raw: bytes) -> int:
        try:
            text = raw.decode("utf-8")
            first = tokenizer.encode(text, add_special_tokens=add_special_tokens).ids
            second = tokenizer.encode(text, add_special_tokens=add_special_tokens).ids
            if first != second:
                raise ContentBoundCompilerError(
                    "tokenizer-runtime:non-deterministic-encode"
                )
            count = len(first)
        except ContentBoundCompilerError:
            raise
        except Exception as exc:
            raise ContentBoundCompilerError("tokenizer-runtime:encode-failed") from exc
        if type(count) is not int or count < 0 or count > _MAX_TOKEN_BOUND:
            raise ContentBoundCompilerError("tokenizer-runtime:invalid-token-count")
        return count

    result = (
        count_huggingface,
        sha256_ref(
            {
                "spec": spec,
                "model_sha256": model_sha256,
                "runtime_distribution": distribution_binding,
            }
        ),
        str(engine),
    )
    runtime_cache[cache_key] = result
    return result


def _node_vector(
    *,
    node_id: str,
    path_name: str,
    spec: Mapping[str, Any],
    prompts: Mapping[str, bytes],
    caps: Mapping[str, int],
    count_tokens: Callable[[bytes], int],
    prompt_measurements: dict[str, tuple[int, str]],
    referenced_prompts: list[str],
    referenced_caps: set[str],
) -> tuple[str, tuple[int, ...], dict[str, object]]:
    _keys(
        spec,
        {
            "node_kind",
            "phase",
            "occurrence",
            "prompt_artifact_ids",
            "total_cap_artifact_id",
            "task_input_root",
        },
        f"node-spec.{path_name}",
    )
    node_kind = spec["node_kind"]
    phase = spec["phase"]
    occurrence = spec["occurrence"]
    prompt_ids = spec["prompt_artifact_ids"]
    cap_value = spec["total_cap_artifact_id"]
    task_input_root = spec["task_input_root"]
    zero = tuple(0 for _ in SESSION_LENGTHS)
    if node_kind == "local-zero":
        if not (
            phase in PHASES
            and occurrence == "once"
            and prompt_ids == []
            and cap_value is None
            and task_input_root is False
        ):
            raise ContentBoundCompilerError(
                f"node-spec.{path_name}:invalid-local-zero-binding"
            )
        return str(phase), zero, {
            "node_id": node_id,
            "node_kind": node_kind,
            "phase": phase,
            "occurrence": occurrence,
            "prompt_artifact_ids": [],
            "prompt_sha256": [],
            "exact_input_tokens": [],
            "total_cap_artifact_id": None,
            "maximum_total_tokens_per_call": None,
            "task_input_root": False,
            "charged_bound_rule": "proved-local-zero-model-tokens",
            "contribution_tokens_by_n": list(zero),
        }
    if node_kind != "model-call":
        raise ContentBoundCompilerError(f"node-spec.{path_name}:unknown-node-kind")
    cap_id = _identifier(cap_value, "node-spec.total_cap_artifact_id")
    if (
        phase not in PHASES
        or occurrence not in OCCURRENCES
        or type(prompt_ids) is not list
        or any(type(item) is not str or item not in prompts for item in prompt_ids)
        or len(prompt_ids) != (1 if occurrence == "once" else len(SESSION_LENGTHS))
        or cap_id not in caps
        or type(task_input_root) is not bool
        or task_input_root
        and occurrence != "per-task"
    ):
        raise ContentBoundCompilerError(f"node-spec.{path_name}:invalid-call-binding")
    referenced_prompts.extend(prompt_ids)
    referenced_caps.add(cap_id)
    counts: list[int] = []
    prompt_sha256: list[str] = []
    for item in prompt_ids:
        measurement = prompt_measurements.get(item)
        if measurement is None:
            raw = prompts[item]
            measurement = (count_tokens(raw), sha256_ref(raw))
            prompt_measurements[item] = measurement
        counts.append(measurement[0])
        prompt_sha256.append(measurement[1])
    if any(type(item) is not int or item <= 0 or item > caps[cap_id] for item in counts):
        raise ContentBoundCompilerError(
            f"node-spec.{path_name}:input-must-be-positive-and-within-total-cap"
        )
    if path_name == "action-state":
        if occurrence == "once":
            vector = tuple(counts[0] for _ in SESSION_LENGTHS)
        else:
            total = 0
            cumulative: list[int] = []
            for item in counts:
                total += item
                if total > _MAX_TOKEN_BOUND:
                    raise ContentBoundCompilerError("node-spec:cumulative-token-overflow")
                cumulative.append(total)
            vector = tuple(cumulative)
    else:
        cap = caps[cap_id]
        vector = tuple(
            cap if occurrence == "once" else cap * n for n in SESSION_LENGTHS
        )
        if any(item > _MAX_TOKEN_BOUND for item in vector):
            raise ContentBoundCompilerError("node-spec:cumulative-cap-overflow")
    trace = {
        "node_id": node_id,
        "node_kind": node_kind,
        "phase": phase,
        "occurrence": occurrence,
        "prompt_artifact_ids": list(prompt_ids),
        "prompt_sha256": prompt_sha256,
        "exact_input_tokens": counts,
        "total_cap_artifact_id": cap_id,
        "maximum_total_tokens_per_call": caps[cap_id],
        "task_input_root": task_input_root,
        "charged_bound_rule": (
            "exact-final-input-lower-bound"
            if path_name == "action-state"
            else "inclusive-total-cap-upper-bound"
        ),
        "contribution_tokens_by_n": list(vector),
    }
    return str(phase), vector, trace


def _combine_vectors(
    left: tuple[int, ...], right: tuple[int, ...]
) -> tuple[int, ...]:
    result = tuple(a + b for a, b in zip(left, right))
    if any(item > _MAX_TOKEN_BOUND for item in result):
        raise ContentBoundCompilerError("path-bound:cumulative-token-overflow")
    return result


def _path_phase_vectors(
    *,
    path_name: str,
    graph_with_entry: Mapping[str, tuple[str, ...]],
    node_specs: Mapping[str, Any],
    prompts: Mapping[str, bytes],
    caps: Mapping[str, int],
    count_tokens: Callable[[bytes], int],
    prompt_measurements: dict[str, tuple[int, str]],
    referenced_prompts: list[str],
    referenced_caps: set[str],
) -> tuple[
    dict[str, tuple[int, ...]],
    list[dict[str, object]],
    dict[str, set[str]],
    list[str],
]:
    entry = graph_with_entry["__entry__"][0]
    graph = {key: value for key, value in graph_with_entry.items() if key != "__entry__"}
    if type(node_specs) is not dict or set(node_specs) != set(graph):
        raise ContentBoundCompilerError(
            f"node-specs.{path_name}:must-cover-exact-dag-node-set"
        )
    contributions: dict[str, tuple[str, tuple[int, ...]]] = {}
    traces: list[dict[str, object]] = []
    phase_nodes: dict[str, set[str]] = {phase: set() for phase in PHASES}
    for node in graph:
        spec = node_specs[node]
        if type(spec) is not dict:
            raise ContentBoundCompilerError(f"node-specs.{path_name}.{node}:object-required")
        phase, vector, trace = _node_vector(
            node_id=node,
            path_name=path_name,
            spec=spec,
            prompts=prompts,
            caps=caps,
            count_tokens=count_tokens,
            prompt_measurements=prompt_measurements,
            referenced_prompts=referenced_prompts,
            referenced_caps=referenced_caps,
        )
        contributions[node] = (phase, vector)
        traces.append(trace)
        phase_nodes[phase].add(str(trace["node_kind"]))
    zero = tuple(0 for _ in SESSION_LENGTHS)
    memo: dict[str, dict[str, tuple[int, ...]]] = {}

    def visit(node: str) -> dict[str, tuple[int, ...]]:
        if node in memo:
            return memo[node]
        successors = [visit(target) for target in graph[node]]
        tail: dict[str, tuple[int, ...]] = {}
        for phase in PHASES:
            if not successors:
                tail[phase] = zero
            else:
                columns = zip(*(item[phase] for item in successors))
                chooser = min if path_name == "action-state" else max
                tail[phase] = tuple(chooser(column) for column in columns)
        phase, own = contributions[node]
        tail[phase] = _combine_vectors(tail[phase], own)
        memo[node] = tail
        return tail

    roots = [trace for trace in traces if trace["task_input_root"] is True]
    if len(roots) != 1:
        raise ContentBoundCompilerError(
            f"node-specs.{path_name}:exactly-one-per-task-root-required"
        )
    root_node = str(roots[0]["node_id"])
    count_memo: dict[str, tuple[int, int]] = {}

    def root_count_bounds(node: str) -> tuple[int, int]:
        if node in count_memo:
            return count_memo[node]
        own = int(node == root_node)
        children = [root_count_bounds(target) for target in graph[node]]
        result = (
            own if not children else own + min(item[0] for item in children),
            own if not children else own + max(item[1] for item in children),
        )
        count_memo[node] = result
        return result

    if root_count_bounds(entry) != (1, 1):
        raise ContentBoundCompilerError(
            f"node-specs.{path_name}:task-root-must-dominate-every-terminal"
        )
    return (
        visit(entry),
        traces,
        phase_nodes,
        list(roots[0]["prompt_artifact_ids"]),
    )


def _compile_case(
    case: ContentBoundCase,
    *,
    tokenizer_runtime_cache: dict[
        str, tuple[Callable[[bytes], int], str, str]
    ],
) -> dict[str, object]:
    artifacts = _artifact_bundles(case.artifacts)
    inventory = build_finite_bound_preflight_manifest(artifacts=artifacts)
    if inventory["outcome"] != "blocked" or inventory["error"] is not None:
        raise ContentBoundCompilerError("preflight:valid-inventory-required")
    bundles = inventory["artifact_bundles"]
    bundle_hashes = {kind: bundles[kind]["bundle_sha256"] for kind in KINDS}

    manifest_raw = _bounded_raw(
        case.compilation_manifest,
        maximum=_MAX_COMPILATION_MANIFEST_BYTES,
        path="compilation-manifest",
    )
    manifest = _json(manifest_raw, "compilation-manifest")
    if type(manifest) is not dict:
        raise ContentBoundCompilerError("compilation-manifest:object-required")
    _keys(
        manifest,
        {
            "schema_version",
            "case_id",
            "domain_id",
            "tokenizer_id",
            "receiver_model_id",
            "receiver_settings_sha256",
            "task_ids",
            "tokenizer_spec_artifact_id",
            "final_input_binding_artifact_id",
            "path_dag_artifact_id",
            "node_specs",
        },
        "compilation-manifest",
    )
    if manifest["schema_version"] != COMPILATION_MANIFEST_SCHEMA:
        raise ContentBoundCompilerError("compilation-manifest:unknown-schema")
    case_id = _identifier(manifest["case_id"], "compilation-manifest.case_id")
    domain_id = _identifier(manifest["domain_id"], "compilation-manifest.domain_id")
    tokenizer_id = _identifier(
        manifest["tokenizer_id"], "compilation-manifest.tokenizer_id"
    )
    receiver_model_id = _identifier(
        manifest["receiver_model_id"], "compilation-manifest.receiver_model_id"
    )
    receiver_settings_sha256 = manifest["receiver_settings_sha256"]
    task_ids = manifest["task_ids"]
    if (
        type(receiver_settings_sha256) is not str
        or SHA256_RE.fullmatch(receiver_settings_sha256) is None
        or type(task_ids) is not list
        or len(task_ids) != len(SESSION_LENGTHS)
        or any(
            type(item) is not str or IDENTIFIER_RE.fullmatch(item) is None
            for item in task_ids
        )
        or len(set(task_ids)) != len(task_ids)
    ):
        raise ContentBoundCompilerError(
            "compilation-manifest:exact-receiver-and-task-order-required"
        )
    spec_id = _identifier(
        manifest["tokenizer_spec_artifact_id"],
        "compilation-manifest.tokenizer_spec_artifact_id",
    )
    binding_id = _identifier(
        manifest["final_input_binding_artifact_id"],
        "compilation-manifest.final_input_binding_artifact_id",
    )
    dag_id = _identifier(
        manifest["path_dag_artifact_id"],
        "compilation-manifest.path_dag_artifact_id",
    )
    if (
        spec_id not in artifacts["tokenizer-artifacts"]
        or set(artifacts["chat-template-artifacts"]) != {binding_id}
        or set(artifacts["path-dag-artifacts"]) != {dag_id}
    ):
        raise ContentBoundCompilerError("compilation-manifest:artifact-selection-not-closed")

    prompt_ids = set(artifacts["canonical-transmitted-prompts"])
    _load_final_input_binding(
        artifacts["chat-template-artifacts"][binding_id],
        artifact_id=binding_id,
        prompt_ids=prompt_ids,
        receiver_model_id=receiver_model_id,
        receiver_settings_sha256=receiver_settings_sha256,
        tokenizer_id=tokenizer_id,
        tokenizer_spec_artifact_id=spec_id,
    )
    count_tokens, tokenizer_binding_sha256, tokenizer_engine = _load_token_counter(
        tokenizer_id=tokenizer_id,
        spec_id=spec_id,
        raw_tokenizer_artifacts=artifacts["tokenizer-artifacts"],
        runtime_cache=tokenizer_runtime_cache,
    )
    if (
        tokenizer_engine == "utf8-byte-units"
        and receiver_model_id != BYTE_CONFORMANCE_RECEIVER_MODEL_ID
    ):
        raise ContentBoundCompilerError(
            "tokenizer-runtime:byte-engine-is-synthetic-conformance-only"
        )
    graph = _load_graph(artifacts["path-dag-artifacts"][dag_id], dag_id)
    caps = _load_caps(artifacts["source-enforced-total-cap-artifacts"])
    node_specs = manifest["node_specs"]
    if type(node_specs) is not dict:
        raise ContentBoundCompilerError("compilation-manifest.node_specs:object-required")
    _keys(node_specs, set(PATHS), "compilation-manifest.node_specs")

    referenced_prompts: list[str] = []
    referenced_caps: set[str] = set()
    prompt_measurements: dict[str, tuple[int, str]] = {}
    derived: dict[str, dict[str, object]] = {}
    baseline_prompt_ids: dict[str, list[str]] = {}
    for path_name in PATHS:
        vectors, traces, phase_nodes, root_prompt_ids = _path_phase_vectors(
            path_name=path_name,
            graph_with_entry=graph[path_name],
            node_specs=node_specs[path_name],
            prompts=artifacts["canonical-transmitted-prompts"],
            caps=caps,
            count_tokens=count_tokens,
            prompt_measurements=prompt_measurements,
            referenced_prompts=referenced_prompts,
            referenced_caps=referenced_caps,
        )
        derived[path_name] = {
            "vectors": vectors,
            "traces": traces,
            "phase_nodes": phase_nodes,
            "root_prompt_ids": root_prompt_ids,
        }
        if path_name in BASELINES:
            baseline_prompt_ids[path_name] = root_prompt_ids
    if set(referenced_prompts) != prompt_ids:
        raise ContentBoundCompilerError(
            "compilation-manifest:every-final-prompt-must-be-referenced"
        )
    if referenced_caps != set(caps):
        raise ContentBoundCompilerError(
            "compilation-manifest:every-total-cap-must-be-referenced"
        )

    success_evidence, legacy_receipts = _load_success_evidence(
        receipts=case.baseline_success_receipts,
        case_id=case_id,
        domain_id=domain_id,
        tokenizer_id=tokenizer_id,
        receiver_model_id=receiver_model_id,
        receiver_settings_sha256=receiver_settings_sha256,
        task_ids=task_ids,
        baseline_prompt_ids=baseline_prompt_ids,
        prompts=artifacts["canonical-transmitted-prompts"],
        bundle_hashes=bundle_hashes,
        compilation_manifest_sha256=sha256_ref(case.compilation_manifest),
    )
    preflight = build_finite_bound_preflight_manifest(
        artifacts=artifacts,
        baseline_success_receipts=legacy_receipts,
    )
    if (
        preflight["outcome"] != "blocked"
        or not preflight["inventory_complete"]
        or preflight["missing_requirements"]
        != ["content-derived-token-vectors-and-phase-bound-compiler"]
    ):
        raise ContentBoundCompilerError("preflight:compiler-input-closure-failed")

    paths: dict[str, object] = {}
    derivation_trace: dict[str, object] = {}
    for path_name in PATHS:
        vectors = derived[path_name]["vectors"]
        phase_nodes = derived[path_name]["phase_nodes"]
        if type(vectors) is not dict or type(phase_nodes) is not dict:
            raise ContentBoundCompilerError("compiler:internal-derived-shape-invalid")
        success = (
            list(SESSION_LENGTHS)
            if path_name == "action-state"
            else success_evidence[path_name]["safe_successes_by_n"]
        )
        path_body = {
            "bound_direction": "lower" if path_name == "action-state" else "upper",
            "success_direction": "maximum" if path_name == "action-state" else "minimum",
            "safe_successes_by_n": success,
            "phases": [
                {
                    "phase": phase,
                    "bound_kind": (
                        "proved-absent"
                        if not phase_nodes[phase]
                        else (
                            "proved-zero"
                            if phase_nodes[phase] == {"local-zero"}
                            else (
                                "derived-lower-bound"
                                if path_name == "action-state"
                                else "derived-upper-bound"
                            )
                        )
                    ),
                    "tokens_by_n": list(vectors[phase]),
                }
                for phase in PHASES
            ],
        }
        paths[path_name] = path_body
        derivation_trace[path_name] = {
            "dag_sha256": sha256_ref(artifacts["path-dag-artifacts"][dag_id]),
            "node_derivations": derived[path_name]["traces"],
            "root_task_input_prompt_artifact_ids": derived[path_name][
                "root_prompt_ids"
            ],
            "phase_vectors_sha256": sha256_ref(
                {phase: list(vectors[phase]) for phase in PHASES}
            ),
        }

    bound_material = {
        "case_manifest_sha256": sha256_ref(case.compilation_manifest),
        "preflight_manifest_sha256": preflight["manifest_sha256"],
        "tokenizer_binding_sha256": tokenizer_binding_sha256,
        "tokenizer_engine": tokenizer_engine,
        "task_order_sha256": sha256_ref(task_ids),
        "success_evidence_sha256": {
            baseline: success_evidence[baseline]["receipt_sha256"]
            for baseline in BASELINES
        },
        "derivation_trace_sha256": sha256_ref(derivation_trace),
        "paths": paths,
    }
    row = {
        "domain_id": domain_id,
        "domain_manifest_sha256": bundles["pretty-sources"]["bundle_sha256"],
        "tokenizer_id": tokenizer_id,
        "tokenizer_sha256": bundles["tokenizer-artifacts"]["bundle_sha256"],
        "bound_manifest_sha256": sha256_ref(bound_material),
        "paths": paths,
    }
    return {
        "case_id": case_id,
        "row": row,
        "preflight_manifest_sha256": preflight["manifest_sha256"],
        "source_prompt_bundle_sha256": bundles["canonical-transmitted-prompts"][
            "bundle_sha256"
        ],
        "path_dag_bundle_sha256": bundles["path-dag-artifacts"]["bundle_sha256"],
        "tokenizer_bundle_sha256": bundles["tokenizer-artifacts"]["bundle_sha256"],
        "compilation_manifest_sha256": sha256_ref(case.compilation_manifest),
        "tokenizer_binding_sha256": tokenizer_binding_sha256,
        "tokenizer_engine": tokenizer_engine,
        "task_order_sha256": sha256_ref(task_ids),
        "baseline_success_evidence": success_evidence,
        "derivation_trace": derivation_trace,
        "derivation_trace_sha256": sha256_ref(derivation_trace),
    }


def _compiler_bundle() -> tuple[dict[str, object], str]:
    try:
        base = Path(__file__).parent
        sources = []
        for name in _COMPILER_BUNDLE_FILES:
            raw = (base / name).read_bytes()
            sources.append(
                {"name": name, "byte_count": len(raw), "sha256": sha256_ref(raw)}
            )
        executable = Path(sys.executable).resolve().read_bytes()
        manifest = {
            "schema_version": COMPILER_BUNDLE_SCHEMA,
            "sources": sources,
            "python_runtime": {
                "implementation": sys.implementation.name,
                "version": list(sys.version_info[:3]),
                "cache_tag": sys.implementation.cache_tag,
                "executable_sha256": sha256_ref(executable),
            },
        }
        return manifest, sha256_ref(manifest)
    except OSError as exc:
        raise ContentBoundCompilerError("compiler-bundle:unreadable") from exc


def _nonclaims() -> dict[str, object]:
    return {
        "provider_calls_performed": 0,
        "model_calls_performed": 0,
        "kill_decision_permitted": False,
        "receiver_ceiling_run_permitted": False,
        "claim_eligible": False,
        "efficiency_claim_eligible": False,
        "protocol_version_promotion_permitted": False,
        "adoption_claim_permitted": False,
    }


def _preflight_case_batch(cases: Sequence[ContentBoundCase]) -> None:
    """Reject duplicate or oversized work before any expensive compilation."""

    total_bytes = 0
    total_nodes = 0
    total_dag_edges = 0
    total_prompt_references = 0
    seen_case_ids: set[str] = set()
    seen_rows: set[tuple[str, str]] = set()
    seen_manifests: set[str] = set()
    seen_tokenizer_bundles: set[tuple[str, str]] = set()
    for index, case in enumerate(cases):
        manifest_raw = _bounded_raw(
            case.compilation_manifest,
            maximum=_MAX_COMPILATION_MANIFEST_BYTES,
            path=f"cases[{index}].compilation-manifest",
        )
        manifest = _json(manifest_raw, f"cases[{index}].compilation-manifest")
        if type(manifest) is not dict:
            raise ContentBoundCompilerError(
                f"cases[{index}].compilation-manifest:object-required"
            )
        case_id = _identifier(
            manifest.get("case_id"), f"cases[{index}].compilation-manifest.case_id"
        )
        domain_id = _identifier(
            manifest.get("domain_id"),
            f"cases[{index}].compilation-manifest.domain_id",
        )
        tokenizer_id = _identifier(
            manifest.get("tokenizer_id"),
            f"cases[{index}].compilation-manifest.tokenizer_id",
        )
        manifest_sha256 = sha256_ref(manifest_raw)
        row_identity = (domain_id, tokenizer_id)
        if case_id in seen_case_ids:
            raise ContentBoundCompilerError("cases:duplicate-case-id")
        if row_identity in seen_rows:
            raise ContentBoundCompilerError("cases:duplicate-domain-tokenizer-row")
        if manifest_sha256 in seen_manifests:
            raise ContentBoundCompilerError("cases:duplicate-compilation-manifest")
        seen_case_ids.add(case_id)
        seen_rows.add(row_identity)
        seen_manifests.add(manifest_sha256)

        node_specs = manifest.get("node_specs")
        if type(node_specs) is not dict or set(node_specs) != set(PATHS):
            raise ContentBoundCompilerError(
                f"cases[{index}].compilation-manifest.node_specs:closed-paths-required"
            )
        case_nodes = 0
        case_prompt_references = 0
        for path_name in PATHS:
            path_nodes = node_specs[path_name]
            if type(path_nodes) is not dict:
                raise ContentBoundCompilerError(
                    f"cases[{index}].compilation-manifest.node_specs.{path_name}:object-required"
                )
            case_nodes += len(path_nodes)
            for node_id, node_spec in path_nodes.items():
                if type(node_spec) is not dict:
                    raise ContentBoundCompilerError(
                        f"cases[{index}].compilation-manifest.node_specs.{path_name}.{node_id}:object-required"
                    )
                prompt_ids = node_spec.get("prompt_artifact_ids")
                if type(prompt_ids) is not list:
                    raise ContentBoundCompilerError(
                        f"cases[{index}].compilation-manifest.node_specs.{path_name}.{node_id}:prompt-array-required"
                    )
                case_prompt_references += len(prompt_ids)
        if case_nodes > _MAX_NODES_PER_CASE:
            raise ContentBoundCompilerError(f"cases[{index}]:node-budget-exceeded")
        total_nodes += case_nodes
        if total_nodes > _MAX_NODES_PER_BATCH:
            raise ContentBoundCompilerError("cases:batch-node-budget-exceeded")
        if case_prompt_references > _MAX_PROMPT_REFERENCES_PER_CASE:
            raise ContentBoundCompilerError(
                f"cases[{index}]:expanded-prompt-reference-budget-exceeded"
            )
        total_prompt_references += case_prompt_references
        if total_prompt_references > _MAX_PROMPT_REFERENCES_PER_BATCH:
            raise ContentBoundCompilerError(
                "cases:batch-expanded-prompt-reference-budget-exceeded"
            )

        receipts = case.baseline_success_receipts
        if type(receipts) is not dict or set(receipts) != set(BASELINES):
            raise ContentBoundCompilerError(
                f"cases[{index}].baseline-success-evidence:both-baselines-required"
            )
        case_bytes = len(manifest_raw)
        for baseline in BASELINES:
            raw = _bounded_raw(
                receipts[baseline],
                maximum=_MAX_SUCCESS_EVIDENCE_BYTES,
                path=f"cases[{index}].baseline-success-evidence.{baseline}",
            )
            case_bytes += len(raw)

        artifacts = case.artifacts
        if type(artifacts) is not dict or set(artifacts) != set(KINDS):
            raise ContentBoundCompilerError(f"cases[{index}].artifacts:closed-kinds-required")
        for kind in KINDS:
            bundle = artifacts[kind]
            if type(bundle) is not dict or not bundle or len(bundle) > 512:
                raise ContentBoundCompilerError(
                    f"cases[{index}].artifacts.{kind}:bounded-object-required"
                )
            for raw in bundle.values():
                if type(raw) is not bytes or not raw:
                    raise ContentBoundCompilerError(
                        f"cases[{index}].artifacts.{kind}:nonempty-bytes-required"
                    )
                case_bytes += len(raw)
        dag_id = _identifier(
            manifest.get("path_dag_artifact_id"),
            f"cases[{index}].compilation-manifest.path_dag_artifact_id",
        )
        dag_bundle = artifacts["path-dag-artifacts"]
        if set(dag_bundle) != {dag_id}:
            raise ContentBoundCompilerError(
                f"cases[{index}].path-dag:exact-selected-artifact-required"
            )
        dag_value = _json(dag_bundle[dag_id], f"cases[{index}].path-dag")
        if type(dag_value) is not dict or type(dag_value.get("paths")) is not dict:
            raise ContentBoundCompilerError(f"cases[{index}].path-dag:closed-paths-required")
        dag_paths = dag_value["paths"]
        if set(dag_paths) != set(PATHS):
            raise ContentBoundCompilerError(f"cases[{index}].path-dag:closed-paths-required")
        case_dag_edges = 0
        for path_name in PATHS:
            path_value = dag_paths[path_name]
            if type(path_value) is not dict or type(path_value.get("edges")) is not dict:
                raise ContentBoundCompilerError(
                    f"cases[{index}].path-dag.{path_name}:edge-object-required"
                )
            edges = path_value["edges"]
            if set(edges) != set(node_specs[path_name]):
                raise ContentBoundCompilerError(
                    f"cases[{index}].path-dag.{path_name}:node-spec-set-mismatch"
                )
            for targets in edges.values():
                if type(targets) is not list:
                    raise ContentBoundCompilerError(
                        f"cases[{index}].path-dag.{path_name}:edge-array-required"
                    )
                case_dag_edges += len(targets)
        if case_dag_edges > _MAX_DAG_EDGES_PER_CASE:
            raise ContentBoundCompilerError(f"cases[{index}]:dag-edge-budget-exceeded")
        total_dag_edges += case_dag_edges
        if total_dag_edges > _MAX_DAG_EDGES_PER_BATCH:
            raise ContentBoundCompilerError("cases:batch-dag-edge-budget-exceeded")
        tokenizer_bundle = artifacts["tokenizer-artifacts"]
        tokenizer_bundle_sha256 = sha256_ref(
            [
                {"artifact_id": artifact_id, "sha256": sha256_ref(tokenizer_bundle[artifact_id])}
                for artifact_id in sorted(tokenizer_bundle)
            ]
        )
        seen_tokenizer_bundles.add((tokenizer_id, tokenizer_bundle_sha256))
        if len(seen_tokenizer_bundles) > _MAX_UNIQUE_TOKENIZERS_PER_BATCH:
            raise ContentBoundCompilerError("cases:unique-tokenizer-budget-exceeded")
        if case_bytes > _MAX_CASE_INPUT_BYTES:
            raise ContentBoundCompilerError(f"cases[{index}]:input-byte-budget-exceeded")
        total_bytes += case_bytes
        if total_bytes > _MAX_BATCH_INPUT_BYTES:
            raise ContentBoundCompilerError("cases:batch-input-byte-budget-exceeded")


def build_content_bound_feasibility_screen(
    cases: Sequence[ContentBoundCase],
) -> dict[str, object]:
    """Compile exact inputs, run the zero-call screen, and select no live call."""

    try:
        if type(cases) not in {list, tuple} or not cases or len(cases) > _MAX_CASES:
            raise ContentBoundCompilerError("cases:must-have-1..128-entries")
        if any(type(case) is not ContentBoundCase for case in cases):
            raise ContentBoundCompilerError("cases:exact-ContentBoundCase-required")
        _preflight_case_batch(cases)
        tokenizer_runtime_cache: dict[
            str, tuple[Callable[[bytes], int], str, str]
        ] = {}
        compiled = [
            _compile_case(case, tokenizer_runtime_cache=tokenizer_runtime_cache)
            for case in cases
        ]
        compiler_bundle, compiler_sha256 = _compiler_bundle()
        plan = {
            "schema_version": FEASIBILITY_PLAN_SCHEMA,
            "evaluation_id": EVALUATION_REFERENCE,
            "status": PLAN_STATUS,
            "target_reduction_basis_points": TARGET_REDUCTION_BASIS_POINTS,
            "session_lengths": list(SESSION_LENGTHS),
            "registration": {
                "bounds_frozen_before_screen": True,
                "provider_calls_performed": 0,
                "model_calls_performed": 0,
                "source_prompt_bundle_sha256": sha256_ref(
                    [item["source_prompt_bundle_sha256"] for item in compiled]
                ),
                "path_enumerator_sha256": sha256_ref(
                    {
                        "compiler_bundle_sha256": compiler_sha256,
                        "path_dag_bundle_sha256": [
                            item["path_dag_bundle_sha256"] for item in compiled
                        ],
                    }
                ),
                "tokenizer_registry_sha256": sha256_ref(
                    [item["tokenizer_binding_sha256"] for item in compiled]
                ),
                "all_dynamic_slots_finitely_bounded": True,
                "all_allowed_paths_enumerated": True,
                "inclusive_phase_partition_complete": True,
                "all_billed_reasoning_and_outputs_included": True,
                "all_retries_repairs_fallbacks_and_judges_included": True,
            },
            "rows": [item["row"] for item in compiled],
        }
        _canonical_size(plan, maximum=_MAX_PLAN_BYTES, path="feasibility-plan")
        screen = run_feasibility_kill_screen(plan)
        _canonical_size(screen, maximum=_MAX_SCREEN_BYTES, path="feasibility-result")
        if screen["outcome"] == "invalid":
            raise ContentBoundCompilerError(
                f"compiled-feasibility-plan:{screen.get('error', 'invalid')}"
            )
        eligible: list[int] = []
        for position, session_length in enumerate(SESSION_LENGTHS):
            cells = [row["sessions"][position] for row in screen["rows"]]
            if all(
                cell["outcome"] == "not-disproven"
                and cell["comparison_bound_source"] is not None
                and cell["kill_left_scaled"] is not None
                and cell["kill_right_scaled"] is not None
                and cell["kill_right_scaled"] > cell["kill_left_scaled"]
                for cell in cells
            ):
                eligible.append(session_length)
        body = {
            "schema_version": COMPILATION_RESULT_SCHEMA,
            "outcome": "screened",
            "numeric_screen_permitted": True,
            "eligible_session_lengths": eligible,
            "selected_session_length": None,
            "strictly_positive_residual_all_rows": bool(eligible),
            "compiler_bundle": compiler_bundle,
            "compiler_bundle_sha256": compiler_sha256,
            "compiled_case_bindings": [
                {
                    key: item[key]
                    for key in (
                        "case_id",
                        "preflight_manifest_sha256",
                        "compilation_manifest_sha256",
                        "tokenizer_binding_sha256",
                        "tokenizer_engine",
                        "task_order_sha256",
                        "derivation_trace_sha256",
                    )
                }
                for item in compiled
            ],
            "baseline_success_evidence_sha256": [
                {
                    baseline: item["baseline_success_evidence"][baseline][
                        "receipt_sha256"
                    ]
                    for baseline in BASELINES
                }
                for item in compiled
            ],
            "feasibility_plan": plan,
            "feasibility_plan_sha256": sha256_ref(plan),
            "feasibility_result": screen,
            "feasibility_result_sha256": sha256_ref(screen),
            "conditional_arithmetic_only": True,
            "conditional_evidence_only": True,
            "synthetic_tokenizer_conformance_only": any(
                item["tokenizer_engine"] == "utf8-byte-units" for item in compiled
            ),
            "baseline_success_evidence_authenticated": False,
            "provider_cap_authenticity_verified": False,
            "provider_prompt_delivery_verified": False,
            **_nonclaims(),
        }
        _canonical_size(body, maximum=_MAX_RESULT_BYTES, path="compiler-result")
        return {**body, "result_sha256": sha256_ref(body)}
    except (
        ContentBoundCompilerError,
        VerificationError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as exc:
        body = {
            "schema_version": COMPILATION_RESULT_SCHEMA,
            "outcome": "invalid",
            "numeric_screen_permitted": False,
            "eligible_session_lengths": [],
            "selected_session_length": None,
            "strictly_positive_residual_all_rows": False,
            "compiler_bundle": None,
            "compiler_bundle_sha256": None,
            "compiled_case_bindings": [],
            "baseline_success_evidence_sha256": [],
            "feasibility_plan": None,
            "feasibility_plan_sha256": None,
            "feasibility_result": None,
            "feasibility_result_sha256": None,
            "conditional_arithmetic_only": True,
            "conditional_evidence_only": True,
            "synthetic_tokenizer_conformance_only": None,
            "baseline_success_evidence_authenticated": False,
            "provider_cap_authenticity_verified": False,
            "provider_prompt_delivery_verified": False,
            "error": str(exc),
            **_nonclaims(),
        }
        return {**body, "result_sha256": sha256_ref(body)}


__all__ = [
    "BYTE_CONFORMANCE_RECEIVER_MODEL_ID",
    "CAP_ENFORCEMENT_SOURCE",
    "BASELINE_SUCCESS_EVIDENCE_SCHEMA",
    "COMPILATION_MANIFEST_SCHEMA",
    "COMPILATION_RESULT_SCHEMA",
    "COMPILER_BUNDLE_SCHEMA",
    "FINAL_INPUT_BINDING_SCHEMA",
    "TOKENIZER_SPEC_SCHEMA",
    "ContentBoundCase",
    "ContentBoundCompilerError",
    "build_content_bound_feasibility_screen",
]
