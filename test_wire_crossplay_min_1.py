from __future__ import annotations

import unittest

from urusilla_wire_v02 import DEFAULT_PROFILE, encode_capsule, encode_message
from tools.run_wire_crossplay_min_1 import (
    _pack_input,
    _request,
    _run_node,
    run_experiment,
)


class WireCrossplayMinOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_experiment()

    def test_raw_wire_cross_runtime_gates_pass(self) -> None:
        gates = self.result["functional_gates"]
        self.assertTrue(all(value is True for key, value in gates.items() if key != "external_effect_authority"))
        self.assertFalse(gates["external_effect_authority"])
        self.assertEqual(self.result["negative_controls"]["reply_frames_emitted"], 0)
        self.assertEqual(
            [record["rejection_code"] for record in self.result["negative_controls"]["records"]],
            ["checksum", "unknown_profile"],
        )

    def test_task_critical_and_inert_relations_are_observable(self) -> None:
        bodies = {case["case_id"]: case["body"] for case in self.result["cases"]}
        self.assertNotEqual(bodies["critical-a"], bodies["critical-b"])
        self.assertEqual(bodies["critical-a"], bodies["inert-metadata"])
        self.assertEqual(
            bodies["missing-branch"]["arguments"],
            [{"reason_code": "missing-branch"}],
        )
        self.assertEqual(
            bodies["no-payload"]["arguments"],
            [{"reason_code": "missing-payload"}],
        )

    def test_byte_result_is_bounded_to_raw_local_stdio(self) -> None:
        accounting = self.result["byte_accounting"]
        self.assertLess(
            accounting["wire_cold_framed_total_bytes"],
            accounting["json_framed_total_bytes"],
        )
        self.assertLess(
            accounting["wire_warm_framed_total_bytes_excluding_profile"],
            accounting["json_framed_total_bytes"],
        )
        self.assertFalse(self.result["protocol"]["base64_used"])
        self.assertIn("five fixed records only", accounting["scope"])

    def test_effect_authority_mutation_is_rejected_without_a_reply_frame(self) -> None:
        request = _request("effect-mutation", branch="A", invariant_marker="stable")
        request["body"]["constraints"][0]["condition"]["external_effects"] = True
        packed = _pack_input(
            [encode_message(request)],
            capsule=encode_capsule(DEFAULT_PROFILE),
        )
        _, records = _run_node("wire", packed)
        self.assertEqual(records, [(1, b"application_envelope")])


if __name__ == "__main__":
    unittest.main()
