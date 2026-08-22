"""Tests for content-only validation of supplied provider artifacts."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from competitive_eval.canonical import canonical_json
from competitive_eval.external_replay import (
    build_execution_profile,
    build_external_response_bundle,
    build_external_response_record,
)
from competitive_eval.protocol import CallRequest
from initial_goal_eval.contract import VerificationError
from initial_goal_eval.provider_artifact_store import (
    PROVIDER_ARTIFACTS_SCHEMA,
    ProviderArtifactStore,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _profile() -> dict[str, object]:
    return build_execution_profile(
        provider_id="provider.test",
        api_id="responses/v1",
        normalizer_id="test-normalizer-v1",
        normalizer_sha256=_digest("normalizer"),
    )


def _request(label: str) -> CallRequest:
    return CallRequest.build(
        episode_id=_digest(f"episode-{label}"),
        turn_index=0,
        attempt_index=0,
        purpose="runtime",
        agent="A",
        model_code="G",
        logical_model_id="model-test-001",
        arm="hybrid-router",
        messages=[
            {"role": "system", "content": "Preserve negation and null."},
            {"role": "user", "content": f"fixture={label}; ok=false; value=null"},
        ],
        mock_scenario_key=_digest(f"scenario-{label}"),
    )


def _observation(request: CallRequest, label: str) -> dict[str, object]:
    response_id = f"response-{label}"
    raw_receipt = canonical_json(
        {
            "id": response_id,
            "model": request.value["model_ref"]["logical_model_id"],
            "usage": {"input": 11, "output": 5, "total": 16},
        }
    )
    return {
        "source_kind": "provider",
        "provider_id": "provider.test",
        "request_id": f"request-{label}",
        "response_id": response_id,
        "resolved_model_id": request.value["model_ref"]["logical_model_id"],
        "effective_settings_status": "confirmed-exact",
        "raw_receipt_utf8": raw_receipt,
        "raw_receipt_sha256": hashlib.sha256(raw_receipt.encode("utf-8")).hexdigest(),
    }


def _usage() -> dict[str, object]:
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


def _producer_bundle(
    label: str,
    *,
    observation_overrides: dict[str, object] | None = None,
    output_text: str = '{"answer":42}',
) -> tuple[CallRequest, dict[str, object]]:
    request = _request(label)
    observation = _observation(request, label)
    if observation_overrides is not None:
        observation.update(observation_overrides)
    record = build_external_response_record(
        sequence=0,
        request=request,
        execution_profile=_profile(),
        status="completed",
        output_text=output_text,
        provider_observation=observation,
        usage=_usage(),
        timing={"model_ns": 1234},
    )
    return request, _bundle_for_record(label, record)


def _bundle_for_record(label: str, record: dict[str, object]) -> dict[str, object]:
    return build_external_response_bundle(
        run_id=_digest(f"run-{label}"),
        run_manifest_sha256=_digest(f"run-manifest-{label}"),
        episode_sequence_sha256=_digest(f"episode-sequence-{label}"),
        operator_id="operator.test",
        capture_implementation_sha256=_digest("capture"),
        operator_attestation_sha256=None,
        execution_profile=_profile(),
        records=[record],
    )


def _artifacts(*bundles: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": PROVIDER_ARTIFACTS_SCHEMA,
        "external_bundles": sorted(bundles, key=lambda item: item["bundle_sha256"]),
    }


def _replace_at_path(
    value: object, path: tuple[object, ...], replacement: object
) -> None:
    cursor = value
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = replacement  # type: ignore[index]


class ProviderArtifactStoreTests(unittest.TestCase):
    def test_valid_competitive_producer_fixture_has_exact_consumer_parity(self) -> None:
        request, bundle = _producer_bundle("parity")
        artifacts = _artifacts(bundle)

        store = ProviderArtifactStore.from_object(artifacts)
        record_ref = "sha256:" + bundle["records"][0]["record_sha256"]
        resolved = store.resolve(record_ref)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(store.value, artifacts)
        self.assertEqual(store.record_refs, (record_ref,))
        self.assertEqual(store.record_count, 1)
        self.assertEqual(resolved.record, bundle["records"][0])
        self.assertEqual(resolved.call_id, request.call_id)
        self.assertEqual(resolved.request_sha256, "sha256:" + request.request_sha256)
        self.assertEqual(resolved.terminal_status, "completed")
        self.assertTrue(resolved.provider_observation_complete)
        self.assertTrue(resolved.usage_capture_complete)
        self.assertEqual(resolved.initial_goal_usage["total_tokens"], 16)

    def test_mutated_self_digest_request_response_raw_status_and_profile_fail(
        self,
    ) -> None:
        _, bundle = _producer_bundle("mutation")
        valid = _artifacts(bundle)
        root = ("external_bundles", 0)
        record = root + ("records", 0)
        response = record + ("response",)
        cases = (
            (
                "self-digest",
                record + ("record_sha256",),
                _digest("forged-record-digest"),
                "provider response record digest mismatch",
            ),
            (
                "request",
                record + ("call_request", "messages", 1, "content"),
                "tampered request",
                "provider call request call ID digest mismatch",
            ),
            (
                "response",
                response + ("output_text",),
                "tampered response",
                "provider response digest mismatch",
            ),
            (
                "raw-receipt",
                response + ("provider_observation", "raw_receipt_utf8"),
                '{"tampered":true}',
                "raw provider receipt digest mismatch",
            ),
            (
                "terminal-status",
                response + ("status",),
                "unknown-terminal-status",
                "provider response terminal status differs",
            ),
            (
                "execution-profile",
                root + ("execution_profile", "api_id"),
                "responses/v2",
                "provider execution profile digest mismatch",
            ),
        )

        for name, path, replacement, expected_error in cases:
            with self.subTest(name=name):
                mutated = deepcopy(valid)
                _replace_at_path(mutated, path, replacement)
                with self.assertRaisesRegex(VerificationError, expected_error):
                    ProviderArtifactStore.from_object(mutated)

    def test_global_cross_bundle_replay_is_rejected(self) -> None:
        _, first = _producer_bundle("first")
        first_record = first["records"][0]
        first_observation = first_record["response"]["provider_observation"]

        exact_record_replay = _bundle_for_record("second-run", first_record)
        with self.assertRaisesRegex(
            VerificationError, "provider record digest is replayed"
        ):
            ProviderArtifactStore.from_object(_artifacts(first, exact_record_replay))

        replay_cases = (
            (
                "provider-request",
                {"request_id": first_observation["request_id"]},
            ),
            (
                "provider-response",
                {"response_id": first_observation["response_id"]},
            ),
            (
                "raw-receipt",
                {
                    "raw_receipt_utf8": first_observation["raw_receipt_utf8"],
                    "raw_receipt_sha256": first_observation["raw_receipt_sha256"],
                },
            ),
        )
        for identity_kind, overrides in replay_cases:
            with self.subTest(identity_kind=identity_kind):
                _, second = _producer_bundle(
                    f"second-{identity_kind}", observation_overrides=overrides
                )
                with self.assertRaisesRegex(
                    VerificationError,
                    f"provider artifact identity is replayed: {identity_kind}",
                ):
                    ProviderArtifactStore.from_object(_artifacts(first, second))

    def test_repeated_resolve_is_stateless_and_returns_detached_values(self) -> None:
        _, bundle = _producer_bundle("stateless")
        store = ProviderArtifactStore.from_object(_artifacts(bundle))
        record_ref = "sha256:" + bundle["records"][0]["record_sha256"]
        expected_record = deepcopy(bundle["records"][0])

        first = store.resolve(record_ref)
        self.assertIsNotNone(first)
        assert first is not None
        exported_store = store.value
        exported_record = first.record
        exported_observation = first.observation
        exported_usage = first.initial_goal_usage
        exported_store["external_bundles"][0]["run_id"] = _digest("mutated-run")
        exported_record["response"]["output_text"] = "mutated"
        exported_observation["request_id"] = "mutated"
        exported_usage["total_tokens"] = 0

        second = store.resolve(record_ref)
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(second.record, expected_record)
        self.assertEqual(second.observation["request_id"], "request-stateless")
        self.assertEqual(second.initial_goal_usage["total_tokens"], 16)
        self.assertEqual(store.unreferenced(set()), (record_ref,))
        self.assertEqual(store.unreferenced({record_ref}), ())

    def test_fully_self_consistent_replacement_is_content_valid_not_authenticated(
        self,
    ) -> None:
        _, original = _producer_bundle("original")
        _, replacement = _producer_bundle(
            "replacement", output_text='{"answer":"replacement"}'
        )
        self.assertNotEqual(original["bundle_sha256"], replacement["bundle_sha256"])

        # Rebuilding every supplied preimage and dependent digest can pass a
        # content-only validator. This is deliberately not provider authentication.
        store = ProviderArtifactStore.from_object(_artifacts(replacement))
        record_ref = "sha256:" + replacement["records"][0]["record_sha256"]
        resolved = store.resolve(record_ref)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertTrue(resolved.provider_observation_complete)
        self.assertTrue(resolved.usage_capture_complete)
        self.assertEqual(
            resolved.record["response"]["provenance_status"],
            "content-bound-not-authenticated",
        )
        self.assertIs(replacement["claim_eligible"], False)
        self.assertIn(
            "content hashes do not authenticate a provider or operator",
            replacement["claim_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
