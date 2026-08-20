from __future__ import annotations

import builtins
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from interop_lab.autogen_reproduction import (
    ARM_IDS,
    AutoGenReproductionError,
    _load_assistant_agent_class,
    build_plan,
    main,
    offline_preflight,
    run_autogen_trial,
    validate_plan,
)


class _Usage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _Message:
    def __init__(self, content: str, usage: _Usage | None = None) -> None:
        self.content = content
        self.models_usage = usage


class _Result:
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.messages = [
            _Message("public synthetic task"),
            _Message(content, _Usage(prompt_tokens, completion_tokens)),
        ]


class _Client:
    def __init__(self, arm_id: str) -> None:
        self.arm_id = arm_id
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1


class _FakeAssistantAgent:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.__class__.calls.append(kwargs)

    async def run(self, *, task: str) -> _Result:
        client = self.kwargs["model_client"]
        assert isinstance(client, _Client)
        prompt_tokens = {
            "raw": 100,
            "structured-json": 120,
            "urusilla": 900,
        }[client.arm_id]
        response = json.dumps(
            {
                "selected_plan": None,
                "feasible_plans": ["plan-a", "plan-b"],
                "reason": "Both satisfy the hard constraints and no tie-breaker exists.",
                "would_execute": False,
            },
            separators=(",", ":"),
        )
        return _Result(response, prompt_tokens, 20)


class AutoGenReproductionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plan = build_plan(
            experiment_id="autogen-fixed-test",
            created_at="2026-08-21T00:00:00Z",
        )
        self.receipt = offline_preflight(self.plan)
        _FakeAssistantAgent.calls = []

    def test_clean_clone_preflight_uses_no_autogen_or_provider(self) -> None:
        report = validate_plan(self.plan)
        self.assertTrue(report["valid"])
        self.assertEqual(tuple(report["arms"]), ARM_IDS)
        self.assertFalse(self.receipt["autogen_imported"])
        self.assertEqual(self.receipt["provider_calls"], 0)
        self.assertEqual(self.receipt["network_calls"], 0)
        self.assertEqual(self.receipt["external_effects"], 0)
        self.assertFalse(self.receipt["claim_boundary"]["adoption_proven"])
        self.assertFalse(self.receipt["claim_boundary"]["token_saving_proven"])

    def test_capsule_discovery_cost_is_charged_only_to_urusilla_arm(self) -> None:
        by_id = {arm["arm_id"]: arm for arm in self.plan["arms"]}
        self.assertEqual(by_id["raw"]["discovery_text"], "")
        self.assertGreater(len(by_id["structured-json"]["discovery_text"]), 0)
        self.assertEqual(
            by_id["urusilla"]["discovery_text"],
            self.plan["protocol"]["capsule_text"],
        )
        self.assertGreater(
            by_id["urusilla"]["model_input_bytes"],
            by_id["raw"]["model_input_bytes"],
        )

    def test_all_arms_bind_same_task_and_blank_matched_ledger(self) -> None:
        digest = self.plan["task"]["semantics_sha256"]
        self.assertEqual(
            [arm["task_semantics_sha256"] for arm in self.plan["arms"]],
            [digest, digest, digest],
        )
        self.assertEqual(
            tuple(self.plan["ledger_template"]["arms"]),
            ARM_IDS,
        )
        for arm in self.plan["ledger_template"]["arms"].values():
            self.assertTrue(all(value is None for value in arm.values()))

    def test_tampered_plan_fails_closed(self) -> None:
        changed = copy.deepcopy(self.plan)
        changed["safety_boundary"]["external_effects_authorized"] = True
        with self.assertRaisesRegex(AutoGenReproductionError, "safety_boundary"):
            validate_plan(changed)

        changed = copy.deepcopy(self.plan)
        changed["arms"][2]["model_input_text"] += "hidden tutorial"
        with self.assertRaisesRegex(AutoGenReproductionError, "does not match"):
            validate_plan(changed)

    def test_capsule_byte_change_is_rejected_before_plan_creation(self) -> None:
        source = Path(__file__).resolve().parents[2] / "urusilla_capsule_v0_1.json"
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "capsule.json"
            changed.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaisesRegex(AutoGenReproductionError, "digest mismatch"):
                build_plan(capsule_path=changed)

    def test_optional_dependency_is_fail_closed_when_unavailable(self) -> None:
        real_import = builtins.__import__

        def guarded_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("autogen_agentchat"):
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            with self.assertRaisesRegex(AutoGenReproductionError, "optional dependency"):
                _load_assistant_agent_class()

    async def test_model_path_requires_exact_receipt_and_explicit_approval(self) -> None:
        factory_calls: list[str] = []

        def factory(arm_id: str) -> _Client:
            factory_calls.append(arm_id)
            return _Client(arm_id)

        with self.assertRaisesRegex(AutoGenReproductionError, "operator_approved"):
            await run_autogen_trial(
                self.plan,
                self.receipt,
                factory,
                assistant_agent_class=_FakeAssistantAgent,
            )
        self.assertEqual(factory_calls, [])
        self.assertEqual(_FakeAssistantAgent.calls, [])

        stale = copy.deepcopy(self.receipt)
        stale["plan_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(AutoGenReproductionError, "stale"):
            await run_autogen_trial(
                self.plan,
                stale,
                factory,
                operator_approved_model_calls=True,
                assistant_agent_class=_FakeAssistantAgent,
            )
        self.assertEqual(factory_calls, [])

    async def test_guarded_fake_autogen_run_is_three_arm_tool_free_and_conservative(self) -> None:
        clients: list[_Client] = []

        def factory(arm_id: str) -> _Client:
            client = _Client(arm_id)
            clients.append(client)
            return client

        result = await run_autogen_trial(
            self.plan,
            self.receipt,
            factory,
            operator_approved_model_calls=True,
            assistant_agent_class=_FakeAssistantAgent,
        )
        self.assertEqual([item["arm_id"] for item in result["observations"]], list(ARM_IDS))
        self.assertEqual(len(_FakeAssistantAgent.calls), 3)
        for call in _FakeAssistantAgent.calls:
            self.assertEqual(call["tools"], [])
            self.assertIsNone(call["memory"])
            self.assertFalse(call["reflect_on_tool_use"])
        self.assertTrue(all(item["task_success"] for item in result["observations"]))
        self.assertTrue(all(item["public_response"] is None for item in result["observations"]))
        self.assertEqual([client.close_count for client in clients], [1, 1, 1])
        self.assertLess(
            result["comparisons"]["urusilla_vs_raw"][
                "post_decode_api_input_saving_percent"
            ],
            0,
        )
        self.assertIsNone(
            result["comparisons"]["urusilla_vs_raw"][
                "complete_total_task_token_saving_percent"
            ]
        )
        self.assertFalse(result["claim_boundary"]["complete_total_task_tokens_measured"])
        self.assertFalse(result["claim_boundary"]["changes_project_wide_claim"])

    async def test_reused_client_is_rejected_before_any_agent_call_and_closed_once(self) -> None:
        client = _Client("raw")
        with self.assertRaisesRegex(AutoGenReproductionError, "fresh client"):
            await run_autogen_trial(
                self.plan,
                self.receipt,
                lambda _arm_id: client,
                operator_approved_model_calls=True,
                assistant_agent_class=_FakeAssistantAgent,
            )
        self.assertEqual(_FakeAssistantAgent.calls, [])
        self.assertEqual(client.close_count, 1)

    def test_cli_init_validate_and_preflight_work_without_optional_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "plan.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "init",
                            str(destination),
                            "--experiment-id",
                            "autogen-cli-test",
                        ]
                    ),
                    0,
                )
            validate_output = io.StringIO()
            with redirect_stdout(validate_output):
                self.assertEqual(main(["validate", str(destination), "--json"]), 0)
            self.assertTrue(json.loads(validate_output.getvalue())["valid"])

            receipt_path = Path(temporary) / "preflight.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "preflight",
                            str(destination),
                            "--output",
                            str(receipt_path),
                        ]
                    ),
                    0,
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertFalse(receipt["autogen_imported"])
            self.assertEqual(receipt["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
