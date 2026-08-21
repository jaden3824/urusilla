from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import inspect
import unittest

from competitive_eval.canonical import canonical_json
from competitive_eval.errors import IntegrityError, ManifestError
from competitive_eval.external_replay import (
    ExternalResponseStore,
    MissingExternalResponse,
    build_execution_profile,
    build_external_response_bundle,
    build_external_response_record,
)
import competitive_eval.external_replay as external_replay
from competitive_eval.protocol import CallRequest


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def make_request(*, turn: int = 0, attempt: int = 0) -> CallRequest:
    return CallRequest.build(
        episode_id=digest("episode"),
        turn_index=turn,
        attempt_index=attempt,
        purpose="runtime" if attempt == 0 else "format_repair",
        agent="A" if turn % 2 == 0 else "B",
        model_code="G",
        logical_model_id="model-test-001",
        arm="current_adaptive_surface",
        messages=[
            {"role": "system", "content": "Preserve negation and null."},
            {"role": "user", "content": "The result is not successful; value=null."},
        ],
        mock_scenario_key=digest(f"scenario-{turn}-{attempt}"),
    )


def make_profile() -> dict:
    return build_execution_profile(
        provider_id="provider.test",
        api_id="responses/v1",
        normalizer_id="test-normalizer-v1",
        normalizer_sha256=digest("normalizer"),
    )


def complete_observation(request: CallRequest, *, suffix: str = "0") -> dict:
    raw = canonical_json(
        {
            "id": f"response-{suffix}",
            "model": request.value["model_ref"]["logical_model_id"],
            "usage": {"input": 11, "output": 5, "total": 16},
        }
    )
    return {
        "source_kind": "provider",
        "provider_id": "provider.test",
        "request_id": f"request-{suffix}",
        "response_id": f"response-{suffix}",
        "resolved_model_id": request.value["model_ref"]["logical_model_id"],
        "effective_settings_status": "confirmed-exact",
        "raw_receipt_utf8": raw,
        "raw_receipt_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


def complete_usage() -> dict:
    return {
        "status": "complete",
        "input_tokens": 11,
        "output_tokens": 5,
        "total_tokens": 16,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens_subset": None,
        "reasoning_accounting": "not-reported",
        "actual_billed_usd": None,
        "unclassified_usage_json": None,
    }


def unavailable_observation() -> dict:
    return {
        "source_kind": "unavailable",
        "provider_id": "provider.test",
        "request_id": None,
        "response_id": None,
        "resolved_model_id": None,
        "effective_settings_status": "unknown",
        "raw_receipt_utf8": None,
        "raw_receipt_sha256": None,
    }


def unavailable_usage() -> dict:
    return {
        "status": "unavailable",
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens_subset": None,
        "reasoning_accounting": "not-reported",
        "actual_billed_usd": None,
        "unclassified_usage_json": None,
    }


def make_record(
    request: CallRequest,
    *,
    sequence: int = 0,
    complete: bool = True,
    suffix: str = "0",
) -> dict:
    return build_external_response_record(
        sequence=sequence,
        request=request,
        execution_profile=make_profile(),
        status="completed",
        output_text='{"a":null,"ok":false}',
        provider_observation=(
            complete_observation(request, suffix=suffix)
            if complete
            else unavailable_observation()
        ),
        usage=complete_usage() if complete else unavailable_usage(),
        timing={"model_ns": 1234 if complete else None},
    )


def make_bundle(records: list[dict]) -> dict:
    return build_external_response_bundle(
        run_id=digest("run"),
        run_manifest_sha256=digest("run-manifest"),
        episode_sequence_sha256=digest("episode-sequence"),
        operator_id="operator.test",
        capture_implementation_sha256=digest("capture"),
        operator_attestation_sha256=None,
        execution_profile=make_profile(),
        records=records,
    )


class CallRequestValidationTests(unittest.TestCase):
    def test_imported_request_recomputes_nested_identity_and_settings(self) -> None:
        request = make_request()
        imported = CallRequest.from_value(deepcopy(request.value))
        self.assertEqual(imported.value, request.value)
        self.assertEqual(imported.call_id, request.call_id)
        self.assertEqual(imported.request_sha256, request.request_sha256)
        self.assertEqual(imported.settings_sha256, request.settings_sha256)

        changed = deepcopy(request.value)
        changed["messages"][1]["content"] = "value=success"
        with self.assertRaisesRegex(ManifestError, "call_id digest mismatch"):
            CallRequest.from_value(changed)

    def test_request_rejects_extra_fields_bool_counts_and_gold_leak(self) -> None:
        request = make_request()
        extra = deepcopy(request.value)
        extra["surprise"] = True
        with self.assertRaisesRegex(ManifestError, "field mismatch"):
            CallRequest.from_value(extra)

        boolean_turn = deepcopy(request.value)
        boolean_turn["turn_index"] = False
        with self.assertRaisesRegex(ManifestError, "nonnegative integer"):
            CallRequest.from_value(boolean_turn)

        float_limit = deepcopy(request.value)
        float_limit["generation"]["maximum_output_tokens"] = 250.0
        with self.assertRaisesRegex(ManifestError, "generation settings"):
            CallRequest.from_value(float_limit)

        gold = deepcopy(request.value)
        gold["mock_metadata"]["gold_answer_present"] = True
        with self.assertRaisesRegex(ManifestError, "gold answer"):
            CallRequest.from_value(gold)


class ExternalResponseStoreTests(unittest.TestCase):
    def test_complete_round_trip_is_idempotent_and_fully_accounted(self) -> None:
        request = make_request()
        bundle = make_bundle([make_record(request)])
        store = ExternalResponseStore.from_json(
            canonical_json(bundle),
            expected_run_id=digest("run"),
            expected_run_manifest_sha256=digest("run-manifest"),
            expected_episode_sequence_sha256=digest("episode-sequence"),
        )
        self.assertFalse(store.value["claim_eligible"])
        self.assertEqual(
            store.value["allowed_use"],
            "content-replay-and-core-usage-capture-only",
        )
        self.assertGreater(len(store.value["claim_blockers"]), 0)
        first = store.resolve(request, require_core_usage_capture=True)
        resumed = store.resolve(request, require_core_usage_capture=True)
        self.assertEqual(first.value, resumed.value)
        self.assertTrue(first.core_usage_capture_complete)
        self.assertFalse(first.claim_eligible)
        self.assertGreater(len(first.claim_blockers), 0)
        self.assertEqual(first.output_text, '{"a":null,"ok":false}')
        self.assertEqual(first.usage["total_tokens"], 16)
        self.assertTrue(store.coverage([request])["all_bundle_records_accounted_for"])
        store.assert_all_consumed()

    def test_missing_response_exposes_exact_pending_request_without_authority(self) -> None:
        request = make_request()
        store = ExternalResponseStore.from_object(make_bundle([]))
        with self.assertRaises(MissingExternalResponse) as caught:
            store.resolve(request)
        pending = caught.exception.pending
        self.assertEqual(pending["call_request"], request.value)
        self.assertEqual(pending["request_sha256"], request.request_sha256)
        self.assertEqual(
            pending["response_template"]["usage"]["input_tokens"], None
        )
        self.assertEqual(set(pending["authority"].values()), {False})

    def test_unknown_usage_remains_null_and_capture_is_incomplete(self) -> None:
        request = make_request()
        store = ExternalResponseStore.from_object(
            make_bundle([make_record(request, complete=False)])
        )
        record = store.resolve(request)
        self.assertFalse(record.core_usage_capture_complete)
        self.assertIsNone(record.usage["input_tokens"])
        self.assertIsNone(record.usage["total_tokens"])
        with self.assertRaisesRegex(IntegrityError, "core-usage-capture-incomplete"):
            store.resolve(request, require_core_usage_capture=True)

    def test_core_usage_capture_does_not_imply_timing_billing_or_normalization(self) -> None:
        request = make_request()
        profile = build_execution_profile(
            provider_id="provider.test",
            api_id="responses/v1",
            normalizer_id=None,
            normalizer_sha256=None,
        )
        record = build_external_response_record(
            sequence=0,
            request=request,
            execution_profile=profile,
            status="completed",
            output_text="ok",
            provider_observation=complete_observation(request),
            usage=complete_usage(),
            timing={"model_ns": None},
        )
        bundle = build_external_response_bundle(
            run_id=digest("run"),
            run_manifest_sha256=digest("run-manifest"),
            episode_sequence_sha256=digest("episode-sequence"),
            operator_id="operator.test",
            capture_implementation_sha256=None,
            operator_attestation_sha256=None,
            execution_profile=profile,
            records=[record],
        )
        resolved = ExternalResponseStore.from_object(bundle).resolve(
            request, require_core_usage_capture=True
        )
        self.assertTrue(resolved.core_usage_capture_complete)
        self.assertIsNone(resolved.usage["actual_billed_usd"])
        self.assertIsNone(resolved.value["response"]["timing"]["model_ns"])
        self.assertFalse(resolved.claim_eligible)
        self.assertIn("re-normalized", " ".join(resolved.claim_blockers))

    def test_resolved_record_and_exported_bundle_cannot_mutate_store_state(self) -> None:
        request = make_request()
        store = ExternalResponseStore.from_object(make_bundle([make_record(request)]))
        exported = store.value
        exported["run_id"] = digest("mutated-run")
        exported["records"][0]["response"]["usage"]["total_tokens"] = 0

        first = store.resolve(request, require_core_usage_capture=True)
        first_export = first.value
        first_export["response"]["usage"]["total_tokens"] = 0
        first_export["response"]["output_text"] = "mutated"
        first_usage = first.usage
        first_usage["total_tokens"] = 0

        self.assertEqual(first.usage["total_tokens"], 16)
        self.assertEqual(first.output_text, '{"a":null,"ok":false}')

        second = store.resolve(request, require_core_usage_capture=True)
        self.assertEqual(store.run_id, digest("run"))
        self.assertEqual(second.usage["total_tokens"], 16)
        self.assertEqual(second.output_text, '{"a":null,"ok":false}')

    def test_raw_receipt_tampering_and_bad_total_fail_closed(self) -> None:
        request = make_request()
        observation = complete_observation(request)
        observation["raw_receipt_sha256"] = digest("wrong")
        with self.assertRaisesRegex(IntegrityError, "raw provider receipt"):
            build_external_response_record(
                sequence=0,
                request=request,
                execution_profile=make_profile(),
                status="completed",
                output_text="ok",
                provider_observation=observation,
                usage=complete_usage(),
                timing={"model_ns": 1},
            )

        usage = complete_usage()
        usage["total_tokens"] = 15
        with self.assertRaisesRegex(IntegrityError, "below visible token usage"):
            build_external_response_record(
                sequence=0,
                request=request,
                execution_profile=make_profile(),
                status="completed",
                output_text="ok",
                provider_observation=complete_observation(request),
                usage=usage,
                timing={"model_ns": 1},
            )

    def test_provider_identity_reuse_across_calls_is_rejected(self) -> None:
        first = make_request(turn=0)
        second = make_request(turn=1)
        first_record = make_record(first, sequence=0, suffix="shared")
        observation = complete_observation(second, suffix="shared")
        second_record = build_external_response_record(
            sequence=1,
            request=second,
            execution_profile=make_profile(),
            status="completed",
            output_text="ok",
            provider_observation=observation,
            usage=complete_usage(),
            timing={"model_ns": 2},
        )
        with self.assertRaisesRegex(IntegrityError, "identity replayed"):
            make_bundle([first_record, second_record])

    def test_bundle_binding_sequence_and_unused_records_fail_closed(self) -> None:
        first = make_request(turn=0)
        second = make_request(turn=1)
        bundle = make_bundle(
            [
                make_record(first, sequence=0, suffix="0"),
                make_record(second, sequence=1, suffix="1"),
            ]
        )
        with self.assertRaisesRegex(IntegrityError, "run ID mismatch"):
            ExternalResponseStore.from_object(
                bundle, expected_run_id=digest("different-run")
            )

        store = ExternalResponseStore.from_object(bundle)
        store.resolve(first)
        coverage = store.coverage()
        self.assertEqual(coverage["unused_call_ids"], [second.call_id])
        with self.assertRaisesRegex(IntegrityError, "unused record"):
            store.assert_all_consumed()

        reordered = deepcopy(bundle)
        reordered["records"].reverse()
        with self.assertRaisesRegex(IntegrityError, "sequence is not contiguous"):
            ExternalResponseStore.from_object(reordered)

    def test_strict_json_rejects_duplicates_nan_and_extra_fields(self) -> None:
        with self.assertRaisesRegex(ManifestError, "duplicate JSON member"):
            ExternalResponseStore.from_json(
                '{"format":"a","format":"b"}'
            )
        with self.assertRaisesRegex(ManifestError, "invalid JSON"):
            ExternalResponseStore.from_json('{"value":NaN}')

        bundle = make_bundle([])
        bundle["unexpected"] = None
        with self.assertRaisesRegex(ManifestError, "field mismatch"):
            ExternalResponseStore.from_object(bundle)

    def test_module_imports_no_network_credential_or_process_client(self) -> None:
        tree = ast.parse(inspect.getsource(external_replay))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_roots.add(node.module.split(".")[0])
        self.assertTrue(
            imported_roots.isdisjoint(
                {
                    "boto3",
                    "google",
                    "httpx",
                    "openai",
                    "os",
                    "requests",
                    "socket",
                    "subprocess",
                    "urllib",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
