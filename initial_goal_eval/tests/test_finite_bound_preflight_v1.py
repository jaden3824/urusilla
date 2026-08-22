"""Focused tests for the content-derived finite-bound preflight."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from initial_goal_eval.contract import canonical_json, sha256_ref
from initial_goal_eval.finite_bound_preflight_v1 import (
    BASELINES,
    KINDS,
    PATH_DAG_SCHEMA,
    PREFLIGHT_SCHEMA,
    SUCCESS_RECEIPT_SCHEMA,
    TOKEN_SCOPE,
    TOTAL_CAP_SCHEMA,
    build_finite_bound_preflight_manifest,
    canonical_preflight_json,
)


def _json_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


def _dag(*, cycle: bool = False) -> bytes:
    edges = {"start": ["start"]} if cycle else {"done": [], "start": ["done"]}
    return _json_bytes(
        {
            "schema_version": PATH_DAG_SCHEMA,
            "paths": {
                name: {"entry": "start", "edges": edges}
                for name in ("action-state", "raw-concise", "ordinary-json")
            },
        }
    )


def _cap() -> bytes:
    return _json_bytes(
        {
            "schema_version": TOTAL_CAP_SCHEMA,
            "maximum_total_tokens": 4096,
            "token_scope": TOKEN_SCOPE,
            "enforcement_stage": "before-provider-call",
            "overflow_action": "do-not-call",
            "enforcement_source_utf8": "if total > 4096: do_not_call()",
        }
    )


def _artifacts(*, cycle: bool = False) -> dict[str, dict[str, bytes]]:
    return {
        "pretty-sources": {"source.pretty": b'{\n  "message": "hello"\n}\n'},
        "canonical-transmitted-prompts": {
            "prompt.canonical": b'{"message":"hello"}'
        },
        "tokenizer-artifacts": {
            "tokenizer.asset": b"exact-vocab-and-merges-bytes",
            "tokenizer.impl": b"exact-tokenizer-implementation-bytes",
        },
        "chat-template-artifacts": {"chat.template": b"<system>{{ prompt }}</system>"},
        "path-dag-artifacts": {"paths.dag": _dag(cycle=cycle)},
        "source-enforced-total-cap-artifacts": {"total.cap": _cap()},
    }


def _receipts(
    first: dict[str, object], *, raw_positive: bool = True, json_positive: bool = True
) -> dict[str, bytes]:
    bindings = {
        kind: first["artifact_bundles"][kind]["bundle_sha256"] for kind in KINDS
    }
    result: dict[str, bytes] = {}
    for baseline, positive in zip(BASELINES, (raw_positive, json_positive)):
        result[baseline] = _json_bytes(
            {
                "schema_version": SUCCESS_RECEIPT_SCHEMA,
                "baseline_path": baseline,
                "artifact_bundle_sha256": bindings,
                "safe_success_by_item": [positive] + [False] * 127,
            }
        )
    return result


class FiniteBoundPreflightV1Tests(unittest.TestCase):
    def test_empty_current_state_is_deterministically_blocked(self) -> None:
        first = build_finite_bound_preflight_manifest()
        second = build_finite_bound_preflight_manifest()

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], PREFLIGHT_SCHEMA)
        self.assertEqual(first["outcome"], "blocked")
        self.assertFalse(first["inventory_complete"])
        self.assertFalse(first["numeric_screen_permitted"])
        self.assertIsNone(first["selected_session_length"])
        self.assertFalse(first["receiver_ceiling_run_permitted"])
        self.assertIn("exact-tokenizer-bytes", first["missing_requirements"])
        self.assertIn(
            "baseline-safe-success-receipt:raw-concise:unknown",
            first["missing_requirements"],
        )

    def test_counts_and_hashes_distinguish_pretty_from_transmitted(self) -> None:
        result = build_finite_bound_preflight_manifest(artifacts=_artifacts())
        pretty = result["artifact_bundles"]["pretty-sources"]["artifacts"][0]
        transmitted = result["artifact_bundles"]["canonical-transmitted-prompts"][
            "artifacts"
        ][0]

        self.assertEqual(pretty["byte_count"], len(_artifacts()["pretty-sources"]["source.pretty"]))
        self.assertEqual(
            transmitted["sha256"],
            sha256_ref(_artifacts()["canonical-transmitted-prompts"]["prompt.canonical"]),
        )
        self.assertNotEqual(pretty["sha256"], transmitted["sha256"])

    def test_zero_and_unknown_success_are_retained_without_permission(self) -> None:
        artifacts = _artifacts()
        first = build_finite_bound_preflight_manifest(artifacts=artifacts)
        receipts = _receipts(first, raw_positive=False)
        receipts.pop("ordinary-json")

        result = build_finite_bound_preflight_manifest(
            artifacts=artifacts, baseline_success_receipts=receipts
        )

        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(
            result["baseline_safe_success"]["raw-concise"]["status"],
            "content-bound-zero",
        )
        self.assertEqual(
            result["baseline_safe_success"]["raw-concise"]["safe_successes_by_n"],
            [0] * 128,
        )
        self.assertEqual(
            result["baseline_safe_success"]["ordinary-json"]["status"], "unknown"
        )
        self.assertFalse(result["numeric_screen_permitted"])

    def test_complete_inventory_still_cannot_release_numeric_screen(self) -> None:
        artifacts = _artifacts()
        first = build_finite_bound_preflight_manifest(artifacts=artifacts)
        result = build_finite_bound_preflight_manifest(
            artifacts=artifacts,
            baseline_success_receipts=_receipts(first),
        )

        self.assertEqual(result["outcome"], "blocked")
        self.assertTrue(result["inventory_complete"])
        self.assertFalse(result["numeric_screen_permitted"])
        self.assertIn(
            "content-derived-token-vectors-and-phase-bound-compiler",
            result["missing_requirements"],
        )
        self.assertIsNone(result["selected_session_length"])
        self.assertFalse(result["receiver_ceiling_run_permitted"])
        for field in (
            "claim_eligible",
            "efficiency_claim_eligible",
            "protocol_version_promotion_permitted",
            "adoption_claim_permitted",
        ):
            self.assertFalse(result[field])
        self.assertEqual(result["provider_calls_performed"], 0)
        self.assertEqual(result["model_calls_performed"], 0)

        digestless = deepcopy(result)
        observed_digest = digestless.pop("result_sha256")
        self.assertEqual(observed_digest, sha256_ref(digestless))
        self.assertEqual(canonical_preflight_json(result), canonical_json(result))

    def test_zero_and_delayed_success_receipts_are_complete_inventory(self) -> None:
        artifacts = _artifacts()
        first = build_finite_bound_preflight_manifest(artifacts=artifacts)
        all_zero = build_finite_bound_preflight_manifest(
            artifacts=artifacts,
            baseline_success_receipts=_receipts(
                first,
                raw_positive=False,
                json_positive=False,
            ),
        )
        delayed_receipts = _receipts(
            first,
            raw_positive=False,
            json_positive=False,
        )
        for baseline in BASELINES:
            receipt = json_load(delayed_receipts[baseline])
            receipt["safe_success_by_item"][9] = True
            delayed_receipts[baseline] = _json_bytes(receipt)
        delayed = build_finite_bound_preflight_manifest(
            artifacts=artifacts,
            baseline_success_receipts=delayed_receipts,
        )

        for result in (all_zero, delayed):
            self.assertEqual(result["outcome"], "blocked")
            self.assertTrue(result["inventory_complete"])
            self.assertFalse(result["numeric_screen_permitted"])
            self.assertEqual(
                result["missing_requirements"],
                ["content-derived-token-vectors-and-phase-bound-compiler"],
            )

    def test_mismatched_receipt_and_cyclic_dag_fail_closed(self) -> None:
        artifacts = _artifacts()
        first = build_finite_bound_preflight_manifest(artifacts=artifacts)
        receipts = _receipts(first)
        receipt = json_load(receipts["raw-concise"])
        receipt["artifact_bundle_sha256"]["tokenizer-artifacts"] = "sha256:" + "0" * 64
        receipts["raw-concise"] = _json_bytes(receipt)
        mismatch = build_finite_bound_preflight_manifest(
            artifacts=artifacts, baseline_success_receipts=receipts
        )
        cycle = build_finite_bound_preflight_manifest(artifacts=_artifacts(cycle=True))

        for result in (mismatch, cycle):
            self.assertEqual(result["outcome"], "invalid")
            self.assertFalse(result["numeric_screen_permitted"])
            self.assertIsNone(result["selected_session_length"])
            self.assertFalse(result["receiver_ceiling_run_permitted"])

    def test_unhashable_dag_entry_and_target_fail_closed(self) -> None:
        for mutation in ("entry", "target"):
            with self.subTest(mutation=mutation):
                artifacts = _artifacts()
                dag = json_load(artifacts["path-dag-artifacts"]["paths.dag"])
                path = dag["paths"]["action-state"]
                if mutation == "entry":
                    path["entry"] = []
                else:
                    path["edges"]["start"] = [[]]
                artifacts["path-dag-artifacts"]["paths.dag"] = _json_bytes(dag)

                result = build_finite_bound_preflight_manifest(artifacts=artifacts)

                self.assertEqual(result["outcome"], "invalid")
                self.assertFalse(result["numeric_screen_permitted"])
                self.assertFalse(result["receiver_ceiling_run_permitted"])

    def test_unpaired_surrogate_json_fails_closed(self) -> None:
        artifacts = _artifacts()
        artifacts["source-enforced-total-cap-artifacts"]["total.cap"] = (
            _cap().replace(
                b'"if total > 4096: do_not_call()"',
                b'"\\ud800"',
            )
        )

        result = build_finite_bound_preflight_manifest(artifacts=artifacts)

        self.assertEqual(result["outcome"], "invalid")
        self.assertFalse(result["numeric_screen_permitted"])
        self.assertFalse(result["receiver_ceiling_run_permitted"])

    def test_non_string_nan_mapping_keys_fail_closed_before_sort(self) -> None:
        result = build_finite_bound_preflight_manifest(
            artifacts={
                "pretty-sources": {
                    Decimal("NaN"): b"first",
                    Decimal("1"): b"second",
                }
            }
        )

        self.assertEqual(result["outcome"], "invalid")
        self.assertIn("string-artifact-ids-required", result["error"])
        self.assertFalse(result["numeric_screen_permitted"])
        self.assertFalse(result["receiver_ceiling_run_permitted"])


def json_load(raw: bytes) -> dict[str, object]:
    import json

    value = json.loads(raw.decode("utf-8"))
    assert type(value) is dict
    return value


if __name__ == "__main__":
    unittest.main()
