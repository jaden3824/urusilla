from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from interop_lab.adapters.camel.adapter import (
    ARM_IDS,
    CAMEL_REQUIREMENT,
    MAX_EXTERNAL_CALLS,
    MCP_REQUIREMENT,
    CamelAdapterError,
    _load_chat_agent_class,
    _usage_record,
    build_plan,
    main,
    map_capture_to_interop_record,
    offline_preflight,
    run_camel_trial,
    validate_capture,
    validate_plan,
)
from interop_lab.interop_lab import validate_record


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Response:
    def __init__(self, content: str, usage: object | None) -> None:
        self.msg = _Message(content)
        self.info = {"usage": usage} if usage is not None else {}


class _Model:
    def __init__(self, arm_id: str, callback: object) -> None:
        self.arm_id = arm_id
        self.callback = callback
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1


class _FakeChatAgent:
    calls: list[dict[str, object]] = []
    task_digest = ""
    missing_usage_arm: str | None = None
    invalid_output_arm: str | None = None

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.__class__.calls.append(kwargs)

    def step(self, task: str) -> _Response:
        model = self.kwargs["model"]
        assert isinstance(model, _Model)
        output = json.dumps(
            {
                "task_semantics_sha256": self.task_digest,
                "reconstructed_state": {
                    "feasible_plans": ["plan-a", "plan-b"],
                    "selected_plan": None,
                    "would_execute": False,
                },
                "reason": "Both plans pass the hard constraints and no tie-breaker exists.",
                "format_decision": "session-only-before-answer",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        if model.arm_id == self.invalid_output_arm:
            output = json.dumps(
                {
                    "task_semantics_sha256": self.task_digest,
                    "reconstructed_state": {
                        "feasible_plans": ["plan-a"],
                        "selected_plan": "plan-a",
                        "would_execute": False,
                    },
                    "reason": "Incorrectly forced a choice.",
                    "format_decision": "session-only-before-answer",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        prompt = {"raw": 100, "structured-json": 120, "urusilla": 900}[model.arm_id]
        usage = {
            "prompt_tokens": prompt,
            "completion_tokens": 20,
            "total_tokens": prompt + 20,
        }
        if model.arm_id == self.missing_usage_arm:
            return _Response(output, None)
        model.callback(usage)  # type: ignore[operator]
        return _Response(output, usage)


def _operator() -> dict[str, object]:
    return {
        "recorder": "Independent CAMEL reproduction operator",
        "operator_id": "camel-test-operator",
        "evidence_tier": "self-reported",
        "premeasurement_sealed": True,
        "artifacts_public": False,
        "receiver_relationship_to_project": "independent",
        "provider": "fake-provider",
        "model": "fake-model",
        "model_version": "test-1",
    }


class CamelOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_plan(
            experiment_id="camel-fixed-test",
            created_at="2026-08-21T00:00:00Z",
        )

    def test_plan_and_preflight_need_no_optional_dependency_or_network(self) -> None:
        report = validate_plan(self.plan)
        receipt = offline_preflight(self.plan)
        self.assertTrue(report["valid"])
        self.assertEqual(tuple(report["arms"]), ARM_IDS)
        self.assertEqual(
            self.plan["framework"]["optional_requirements"],
            [CAMEL_REQUIREMENT, MCP_REQUIREMENT],
        )
        self.assertEqual(self.plan["runtime_policy"]["tools"], [])
        self.assertEqual(self.plan["runtime_policy"]["external_tools"], [])
        self.assertEqual(self.plan["runtime_policy"]["max_iteration"], 1)
        self.assertEqual(self.plan["runtime_policy"]["retry_attempts"], 1)
        self.assertFalse(self.plan["runtime_policy"]["stream"])
        self.assertFalse(receipt["camel_imported"])
        self.assertEqual(receipt["provider_calls"], 0)
        self.assertEqual(receipt["network_calls"], 0)
        self.assertEqual(receipt["external_effects"], 0)

    def test_tampered_effect_or_call_policy_fails_closed(self) -> None:
        changed = copy.deepcopy(self.plan)
        changed["runtime_policy"]["tools"] = ["unsafe"]
        with self.assertRaisesRegex(CamelAdapterError, "runtime_policy"):
            validate_plan(changed)

        changed = copy.deepcopy(self.plan)
        changed["runtime_policy"]["call_cap"] = 4
        with self.assertRaisesRegex(CamelAdapterError, "runtime_policy"):
            validate_plan(changed)

        changed = copy.deepcopy(self.plan)
        changed["safety_boundary"]["external_effects_authorized"] = True
        with self.assertRaisesRegex(CamelAdapterError, "safety_boundary"):
            validate_plan(changed)

    def test_capsule_discovery_is_charged_and_all_arms_bind_same_task(self) -> None:
        by_id = {arm["arm_id"]: arm for arm in self.plan["arms"]}
        self.assertEqual(by_id["raw"]["discovery_text"], "")
        self.assertEqual(
            by_id["urusilla"]["discovery_text"],
            self.plan["protocol"]["capsule_text"],
        )
        self.assertGreater(
            by_id["urusilla"]["model_input_bytes"],
            by_id["raw"]["model_input_bytes"],
        )
        self.assertEqual(
            {arm["task_semantics_sha256"] for arm in self.plan["arms"]},
            {self.plan["task"]["semantics_sha256"]},
        )

    def test_optional_dependency_failure_is_clean_and_offline_path_remains_open(self) -> None:
        def absent(name: str) -> str:
            raise __import__("importlib").metadata.PackageNotFoundError(name)

        with patch("interop_lab.adapters.camel.adapter.metadata.version", side_effect=absent):
            with self.assertRaisesRegex(CamelAdapterError, "optional dependency"):
                _load_chat_agent_class()
        self.assertTrue(validate_plan(self.plan)["valid"])

    def test_zero_or_conflicting_usage_sources_fail_to_not_measured(self) -> None:
        valid = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        zero = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        conflicting = {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}
        zero_report = _usage_record(zero, [valid])
        conflict_report = _usage_record(valid, [conflicting])
        for report in (zero_report, conflict_report):
            self.assertEqual(report["status"], "not-measured")
            self.assertIsNone(report["prompt_tokens"])
            self.assertIsNone(report["completion_tokens"])
            self.assertIsNone(report["total_tokens"])

    def test_cli_init_validate_and_preflight_are_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "camel-plan.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "init",
                            str(destination),
                            "--experiment-id",
                            "camel-cli-test",
                        ]
                    ),
                    0,
                )
            validate_output = io.StringIO()
            with redirect_stdout(validate_output):
                self.assertEqual(
                    main(["validate-plan", str(destination), "--json"]),
                    0,
                )
            self.assertTrue(json.loads(validate_output.getvalue())["valid"])
            preflight_output = io.StringIO()
            with redirect_stdout(preflight_output):
                self.assertEqual(main(["preflight", str(destination)]), 0)
            receipt = json.loads(preflight_output.getvalue())
            self.assertFalse(receipt["camel_imported"])
            self.assertEqual(receipt["provider_calls"], 0)

    @unittest.skipUnless(
        importlib.util.find_spec("camel") is not None,
        "optional camel-ai integration is not installed",
    )
    def test_optional_pinned_chat_agent_import(self) -> None:
        # This runs only in a separately provisioned environment. Version guards
        # still reject an unpinned CAMEL or incompatible MCP before import.
        self.assertIsNotNone(_load_chat_agent_class())


class CamelGuardedRunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plan = build_plan(
            experiment_id="camel-live-shape-test",
            created_at="2026-08-21T00:00:00Z",
        )
        self.receipt = offline_preflight(self.plan)
        self.models: list[_Model] = []
        self.factory_calls: list[tuple[str, dict[str, object]]] = []
        _FakeChatAgent.calls = []
        _FakeChatAgent.task_digest = self.plan["task"]["semantics_sha256"]
        _FakeChatAgent.missing_usage_arm = None
        _FakeChatAgent.invalid_output_arm = None

    def factory(
        self,
        arm_id: str,
        callback: object,
        policy: dict[str, object],
    ) -> _Model:
        self.factory_calls.append((arm_id, policy))
        model = _Model(arm_id, callback)
        self.models.append(model)
        return model

    async def test_live_path_requires_exact_flag_receipt_and_call_cap_before_factory(self) -> None:
        with self.assertRaisesRegex(CamelAdapterError, "allow_external_model_calls"):
            await run_camel_trial(
                self.plan,
                self.receipt,
                self.factory,
                operator=_operator(),
                chat_agent_class=_FakeChatAgent,
            )
        self.assertEqual(self.factory_calls, [])

        with self.assertRaisesRegex(CamelAdapterError, "call_cap"):
            await run_camel_trial(
                self.plan,
                self.receipt,
                self.factory,
                allow_external_model_calls=True,
                call_cap=4,
                operator=_operator(),
                chat_agent_class=_FakeChatAgent,
            )
        self.assertEqual(self.factory_calls, [])

        stale = copy.deepcopy(self.receipt)
        stale["plan_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(CamelAdapterError, "stale"):
            await run_camel_trial(
                self.plan,
                stale,
                self.factory,
                allow_external_model_calls=True,
                call_cap=MAX_EXTERNAL_CALLS,
                operator=_operator(),
                chat_agent_class=_FakeChatAgent,
            )
        self.assertEqual(self.factory_calls, [])

    async def test_fake_run_is_direct_fresh_tool_free_and_maps_to_interop(self) -> None:
        capture = await run_camel_trial(
            self.plan,
            self.receipt,
            self.factory,
            allow_external_model_calls=True,
            call_cap=MAX_EXTERNAL_CALLS,
            operator=_operator(),
            chat_agent_class=_FakeChatAgent,
        )
        report = validate_capture(capture, self.plan)
        self.assertTrue(report["valid"])
        self.assertTrue(report["usage_complete_for_raw_to_urusilla"])
        self.assertEqual([arm for arm, _ in self.factory_calls], list(ARM_IDS))
        self.assertEqual(len(_FakeChatAgent.calls), 3)
        self.assertEqual([model.close_count for model in self.models], [1, 1, 1])
        for call in _FakeChatAgent.calls:
            self.assertEqual(call["tools"], [])
            self.assertEqual(call["external_tools"], [])
            self.assertEqual(call["max_iteration"], 1)
            self.assertIsNone(call["summarize_threshold"])
        for _, policy in self.factory_calls:
            self.assertEqual(policy["retry_attempts"], 1)
            self.assertFalse(policy["stream"])
            self.assertEqual(policy["tools"], [])
            self.assertEqual(policy["external_tools"], [])

        mapped = map_capture_to_interop_record(capture, self.plan)
        interop_report = validate_record(mapped)
        self.assertTrue(interop_report["valid"])
        self.assertEqual(mapped["hops"][0]["adoption"]["decision"], "adopted")
        self.assertEqual(mapped["hops"][0]["token_ledger"]["status"], "measured")
        self.assertLess(
            interop_report["aggregate_token_metrics"][
                "post_decode_api_input_saving_percent"
            ],
            0,
        )
        self.assertFalse(interop_report["project_wide_claim_changed"])

    async def test_missing_usage_maps_to_not_measured_never_zero(self) -> None:
        _FakeChatAgent.missing_usage_arm = "urusilla"
        capture = await run_camel_trial(
            self.plan,
            self.receipt,
            self.factory,
            allow_external_model_calls=True,
            call_cap=MAX_EXTERNAL_CALLS,
            operator=_operator(),
            chat_agent_class=_FakeChatAgent,
        )
        usage = capture["arms"][2]["usage"]
        self.assertEqual(usage["status"], "not-measured")
        self.assertIsNone(usage["prompt_tokens"])
        self.assertIsNone(usage["completion_tokens"])
        self.assertIsNone(usage["total_tokens"])
        report = validate_capture(capture, self.plan)
        self.assertFalse(report["usage_complete_for_raw_to_urusilla"])

        mapped = map_capture_to_interop_record(capture, self.plan)
        ledger = mapped["hops"][0]["token_ledger"]
        self.assertEqual(ledger["status"], "not-measured")
        self.assertIsNone(ledger["baseline"])
        self.assertIsNone(ledger["candidate"])
        self.assertIsNone(ledger["post_decode_api_input"]["baseline_tokens"])
        self.assertEqual(
            validate_record(mapped)["aggregate_token_metrics"]["status"],
            "not-measured",
        )

    async def test_zero_filled_measured_usage_is_rejected(self) -> None:
        capture = await run_camel_trial(
            self.plan,
            self.receipt,
            self.factory,
            allow_external_model_calls=True,
            call_cap=MAX_EXTERNAL_CALLS,
            operator=_operator(),
            chat_agent_class=_FakeChatAgent,
        )
        changed = copy.deepcopy(capture)
        changed["arms"][2]["usage"].update(
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        )
        with self.assertRaisesRegex(CamelAdapterError, "incomplete, invalid, or zero"):
            validate_capture(changed, self.plan)

    async def test_failed_comprehension_is_preserved_as_no_adoption(self) -> None:
        _FakeChatAgent.invalid_output_arm = "urusilla"
        capture = await run_camel_trial(
            self.plan,
            self.receipt,
            self.factory,
            allow_external_model_calls=True,
            call_cap=MAX_EXTERNAL_CALLS,
            operator=_operator(),
            chat_agent_class=_FakeChatAgent,
        )
        mapped = map_capture_to_interop_record(capture, self.plan)
        self.assertFalse(mapped["hops"][0]["comprehension_gate"]["passed"])
        self.assertEqual(mapped["hops"][0]["adoption"]["decision"], "fallback-only")
        self.assertFalse(mapped["hops"][0]["actual_use"]["attempted"])
        report = validate_record(mapped)
        self.assertTrue(report["valid"])
        self.assertEqual(report["chain_summary"]["adopted_hops"], 0)


if __name__ == "__main__":
    unittest.main()
