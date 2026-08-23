"""Regression tests for typed receiver/judge envelope integrity replay."""

from __future__ import annotations

from copy import deepcopy
import unittest

import initial_goal_eval.program_v2_runtime_runner as runtime_runner
from initial_goal_eval.contract import VerificationError, sha256_ref
from initial_goal_eval.program_v2_runtime_runner import (
    build_program_v2_provider_capture,
    run_planned_program_v2_arm,
)
from initial_goal_eval.tests.test_program_v2_judge_summary import (
    _SummaryAdapter,
)
from initial_goal_eval.tests.test_runtime_capture_bridge import (
    _digest,
    _judge_ready_plan,
)
from urusilla_hybrid_runtime.canonical import canonical_json


_EFFECT_NAMES = {
    "tools_used",
    "persistence_created",
    "permission_expanded",
    "spending_authority_created",
    "external_effects_performed",
}
_JUDGE_COMPONENTS = {
    "task-judge",
    "parse-judge",
    "semantic-judge",
    "negative-judge",
}


def _rebuild_provider_capture(
    entry: dict,
    *,
    request_preimage: dict,
    response_preimage: dict,
) -> dict:
    provider = entry["capture"]["provider_record"]
    return build_program_v2_provider_capture(
        entry["slot_request"],
        request_preimage=request_preimage,
        response_preimage=response_preimage,
        terminal_status=provider["terminal_status"],
        provider_request_id=provider["provider_request_id"],
        provider_response_id=provider["provider_response_id"],
        raw_receipt_utf8=provider["raw_receipt_utf8"],
        observed_model_id=provider["model_id"],
        observed_settings_sha256=provider["settings_sha256"],
        observed_effects={
            name: provider["effects"][name] for name in _EFFECT_NAMES
        },
        usage=provider["usage"],
        facts=entry["capture"]["facts"],
        attempt_count=provider["attempt_count"],
        retry_count=provider["retry_count"],
        typed_execution_sha256=entry["capture"][
            "typed_execution_sha256"
        ],
    )


class ProgramV2TypedIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = _judge_ready_plan()
        cls.session = cls.plan["sessions"][0]
        cls.artifact = run_planned_program_v2_arm(
            cls.plan,
            session_id=cls.session["session_id"],
            arm_id="raw-concise",
            execution_instance_sha256=_digest("typed-integrity-source"),
            adapter=_SummaryAdapter(),
        )

    def _entry(self, component: str) -> dict:
        task_id = self.session["tasks"][0]["task_id"]
        matches = [
            entry
            for entry in self.artifact["slot_runs"]
            if entry["slot_request"]["slot"]["task_id"] == task_id
            and entry["slot_request"]["slot"]["component"] == component
        ]
        self.assertEqual(len(matches), 1)
        return deepcopy(matches[0])

    def test_rejects_resealed_judge_execution_status_substitution(self) -> None:
        entry = self._entry("task-judge")
        provider = entry["capture"]["provider_record"]
        outcome = deepcopy(provider["response"])
        outcome["execution_status"] = "failed"
        outcome["execution_failure"] = "synthetic-failure"
        entry["capture"] = _rebuild_provider_capture(
            entry,
            request_preimage=deepcopy(provider["request"]),
            response_preimage=outcome,
        )

        with self.assertRaisesRegex(
            VerificationError,
            "typed judge (failure state|execution binding) differs",
        ):
            runtime_runner._judge_result_from_slot_run(entry)

    def test_rejects_resealed_judge_reply_verdict_substitution(self) -> None:
        entry = self._entry("task-judge")
        provider = entry["capture"]["provider_record"]
        outcome = deepcopy(provider["response"])
        reply_preimage = runtime_runner._strict_canonical_json_text(
            outcome["reply_preimage_json"],
            "test.judge_reply",
        )
        role = entry["slot_request"]["slot"]["component"]
        reply_preimage["reply"]["text"] = canonical_json(
            {
                "schema_version": (
                    "urusilla-hybrid-role-separated-judge-verdict/1"
                ),
                "judge_role": role,
                "verdict": "fail",
            }
        )
        outcome["reply_preimage_json"] = canonical_json(reply_preimage)
        outcome["reply_preimage_sha256"] = sha256_ref(
            outcome["reply_preimage_json"].encode("utf-8")
        )
        entry["capture"] = _rebuild_provider_capture(
            entry,
            request_preimage=deepcopy(provider["request"]),
            response_preimage=outcome,
        )

        with self.assertRaisesRegex(
            VerificationError,
            "typed.*(provider capture binding|reply verdict) differs",
        ):
            runtime_runner._judge_result_from_slot_run(entry)

    def test_cross_slot_receiver_envelope_cannot_bind_terminal_content(self) -> None:
        entry = self._entry("receiver")
        provider = entry["capture"]["provider_record"]
        request_envelope = deepcopy(provider["request"])
        request_envelope["slot_request_sha256"] = sha256_ref(
            {"forged-receiver-slot": "other"}
        )
        entry["capture"] = _rebuild_provider_capture(
            entry,
            request_preimage=request_envelope,
            response_preimage=deepcopy(provider["response"]),
        )
        entry["capture_sha256"] = sha256_ref(entry["capture"])
        slot_id = entry["slot_request"]["slot"]["slot_id"]
        resolution = next(
            item
            for item in self.artifact["resolved_program_v2"]["resolutions"]
            if item["slot_id"] == slot_id
        )
        task = self.session["tasks"][0]

        terminal = runtime_runner._typed_receiver_terminal(
            task_id=task["task_id"],
            task_sha256=task["task_sha256"],
            arm_id="raw-concise",
            selected_mode="raw",
            run=entry,
            resolution=resolution,
        )

        self.assertEqual(terminal["terminal_kind"], "unresolved")
        self.assertFalse(terminal["content_binding_verified"])
        self.assertIsNone(terminal["output_text"])

    def test_integrity_replay_never_widens_completion_or_authority(self) -> None:
        self.assertIsNone(self.artifact["safely_completed"])
        for field in (
            "provider_authenticated",
            "operator_authenticated",
            "sandbox_verified",
            "independent_operator_verified",
            "claim_eligible",
            "goal_total_complete",
        ):
            self.assertFalse(self.artifact["authority"][field], field)
        self.assertTrue(
            all(
                result["judge_role"] in _JUDGE_COMPONENTS
                for result in self.artifact["judge_results"]
            )
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
