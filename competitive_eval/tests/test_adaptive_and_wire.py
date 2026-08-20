from __future__ import annotations

import unittest

from competitive_eval.config import A0_COLD_ARTIFACT_BYTES, A0_COLD_TOKENS, WIRE_CONTROLS
from competitive_eval.errors import EvaluationError
from competitive_eval.mocks import mock_count
from competitive_eval.records import Evidence, QARecord
from competitive_eval.representations import (
    SelectionContext,
    TokenCounter,
    encode_current_surface,
    oracle_free_select,
    unwrap_record,
    verify_cold_artifact_locks,
    wrap_record,
)
from competitive_eval.wire_controls import (
    corrupt_frame,
    decode_wire_control,
    encode_wire_control,
)


class AdaptiveAndWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = QARecord(
            answer="answer",
            claims=("claim",),
            evidence=(Evidence("fact", "A"),),
            needs=(),
            act="agree",
        )
        cls.counter = TokenCounter(
            key="qwen2_5_7b_instruct",
            fingerprint="mock",
            exact_for_endpoint=True,
            count_fn=mock_count,
        )
        cls.context = SelectionContext(
            episode_id="0" * 64,
            turn_index=0,
            sender="A",
            receiver="B",
            counter=cls.counter,
            artifacts_cached=False,
        )

    def test_adaptive_bridge_exact_and_cold_overhead_retained(self) -> None:
        locks = verify_cold_artifact_locks()
        self.assertEqual(locks["structured_bundle"]["utf8_bytes"], 13_799)
        artifact = encode_current_surface(self.record, self.context)
        self.assertEqual(artifact.normative_record_sha256, self.record.sha256)
        self.assertEqual(artifact.cold_bytes, A0_COLD_ARTIFACT_BYTES)
        self.assertEqual(artifact.cold_tokens, A0_COLD_TOKENS["qwen2_5_7b_instruct"])
        self.assertGreater(artifact.cold_tokens, self.counter.count(self.record.canonical_text))

    def test_oracle_free_selector_avoids_cold_adaptive_regret(self) -> None:
        selected = oracle_free_select(self.record, self.context)
        self.assertIn(
            selected.selected_representation,
            {"compact_terse_english", "canonical_minified_json"},
        )
        self.assertEqual(selected.cold_tokens, 0)

    def test_unverified_tokenizer_excludes_current_surface(self) -> None:
        unverified = SelectionContext(
            **{
                **self.context.__dict__,
                "counter": TokenCounter("o200k_base", "proxy", False, mock_count),
            }
        )
        selected = oracle_free_select(self.record, unverified)
        self.assertFalse(selected.selected_representation.startswith("current_surface"))

    def test_bridge_control_fields_fail_closed(self) -> None:
        message = wrap_record(self.record, self.context)
        self.assertEqual(unwrap_record(message), self.record)
        tampered = {**message, "act": "QUERY"}
        with self.assertRaises(EvaluationError):
            unwrap_record(tampered)

    def test_all_wire_controls_recover_same_receiver_text_and_reject_corruption(self) -> None:
        receiver_texts = set()
        for codec in WIRE_CONTROLS:
            with self.subTest(codec=codec):
                result, frame = encode_wire_control(codec, self.record, self.context)
                self.assertTrue(result.exact_round_trip)
                self.assertEqual(result.additional_model_calls if hasattr(result, "additional_model_calls") else 0, 0)
                receiver_texts.add(result.receiver_text)
                recovered = decode_wire_control(codec, frame, self.record.sha256)
                self.assertEqual(recovered, self.record)
                with self.assertRaises(Exception):
                    decode_wire_control(codec, corrupt_frame(frame), self.record.sha256)
        self.assertEqual(receiver_texts, {self.record.canonical_text})


if __name__ == "__main__":
    unittest.main()
