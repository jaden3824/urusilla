#!/usr/bin/env python3
"""Offline codec, request, scoring, cost, and mocked-transport tests."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from urusilla import DecodeError

import urusilla_model_comprehension_pilot as pilot


HERE = Path(__file__).resolve().parent


def _mock_response(messages: tuple[pilot.PilotMessage, ...], *, malformed: bool = False) -> dict:
    if malformed:
        text = "not json"
    else:
        text = json.dumps(
            {
                "messages": [
                    {
                        "index": index,
                        "message": item.message,
                    }
                    for index, item in enumerate(messages)
                ]
            },
            separators=(",", ":"),
        )
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {
            "input_tokens": 1_000,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 2_000,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 3_000,
        },
    }


class SymbolicSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.messages = pilot.select_pilot_messages()

    def test_stratified_set_is_frozen_and_covers_every_act_and_origin(self) -> None:
        self.assertEqual(len(self.messages), 14)
        self.assertEqual({item.act for item in self.messages}, set(pilot.ACTS))
        self.assertEqual(
            {act: sum(item.act == act for item in self.messages) for act in pilot.ACTS},
            {act: 2 for act in pilot.ACTS},
        )
        self.assertEqual(
            {origin: sum(item.origin == origin for item in self.messages) for origin in ("grouped_holdout", "out_of_domain")},
            {"grouped_holdout": 7, "out_of_domain": 7},
        )
        self.assertNotEqual(pilot.PILOT_CORPUS_SHA256, "pending")

    def test_symbolic_surface_is_exact_canonical_and_deterministic(self) -> None:
        values = []
        for index, item in enumerate(self.messages):
            with self.subTest(index=index, act=item.act, origin=item.origin):
                encoded = pilot.encode_symbolic(item.message)
                values.append(encoded)
                self.assertEqual(pilot.decode_symbolic(encoded), item.message)
                self.assertEqual(pilot.encode_symbolic(item.message), encoded)
        self.assertEqual(pilot._sequence_digest(tuple(values)), pilot.SYMBOLIC_TEXT_SHA256)

    def test_every_deterministic_single_character_mutation_is_rejected(self) -> None:
        for index, item in enumerate(self.messages):
            encoded = pilot.encode_symbolic(item.message)
            position = pilot.SYMBOLIC_HEADER_CHARACTERS + (
                int.from_bytes(hashlib.sha256(f"mutation-{index}".encode()).digest()[:8], "big")
                % (len(encoded) - pilot.SYMBOLIC_HEADER_CHARACTERS)
            )
            replacement = "X" if encoded[position] != "X" else "Y"
            mutated = encoded[:position] + replacement + encoded[position + 1 :]
            with self.subTest(index=index, position=position):
                with self.assertRaisesRegex(DecodeError, "checksum mismatch"):
                    pilot.decode_symbolic(mutated)

    def test_malformed_header_labels_trailing_and_noncanonical_values_are_rejected(self) -> None:
        encoded = pilot.encode_symbolic(self.messages[0].message)
        cases = (
            None,
            "",
            "@2" + encoded[2:],
            encoded[:2] + "!" * pilot.SYMBOLIC_CHECKSUM_CHARACTERS + encoded[13:],
            encoded[:13] + ";" + encoded[14:],
        )
        for value in cases:
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(DecodeError):
                    pilot.decode_symbolic(value)  # type: ignore[arg-type]

        body = encoded[pilot.SYMBOLIC_HEADER_CHARACTERS:]
        wrong_label = "z" + body[1:]
        checksum = pilot._symbolic_checksum(wrong_label)
        with self.assertRaises(DecodeError):
            pilot.decode_symbolic(pilot.SYMBOLIC_PREFIX + checksum + ":" + wrong_label)

        trailing = body + "x0"
        checksum = pilot._symbolic_checksum(trailing)
        with self.assertRaisesRegex(DecodeError, "trailing"):
            pilot.decode_symbolic(pilot.SYMBOLIC_PREFIX + checksum + ":" + trailing)

    def test_all_three_formats_use_the_identical_ordered_semantic_set(self) -> None:
        prompts = {
            representation: pilot.build_prompt(self.messages, representation)
            for representation in pilot.FORMATS
        }
        for representation, prompt in prompts.items():
            self.assertIn("RECORDS\n0\t", prompt)
            self.assertEqual(sum(line.split("\t", 1)[0].isdigit() for line in prompt.splitlines()), 14)
            for index in range(14):
                self.assertIn(f"{index}\t", prompt)
        symbolic_records = prompts["symbolic"].split("RECORDS\n", 1)[1].splitlines()
        self.assertTrue(
            all(record.split("\t", 1)[1].startswith(pilot.SYMBOLIC_PREFIX) for record in symbolic_records)
        )
        self.assertTrue(
            all(not record.split("\t", 1)[1].startswith("A4") for record in symbolic_records)
        )


class ResponsesRequestAndMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.messages = pilot.select_pilot_messages()

    def test_requests_force_no_storage_and_strict_json_schema(self) -> None:
        for model in ("gpt-5-nano", "gpt-4o-mini"):
            for representation in pilot.FORMATS:
                request = pilot.build_request(model, self.messages, representation)
                self.assertIs(request["store"], False)
                self.assertEqual(request["text"]["format"]["type"], "json_schema")
                self.assertIs(request["text"]["format"]["strict"], True)
                schema = request["text"]["format"]["schema"]
                self.assertEqual(schema["properties"]["messages"]["minItems"], 14)
                self.assertEqual(schema["properties"]["messages"]["maxItems"], 14)
                self.assertIn("anyOf", schema["properties"]["messages"]["items"])
        self.assertEqual(
            pilot.build_request("gpt-5-nano", self.messages, "json")["reasoning"],
            {"effort": "minimal"},
        )
        self.assertEqual(
            pilot.build_request("gpt-4o-mini", self.messages, "json")["temperature"],
            0,
        )

    def test_worst_case_preflight_including_all_repairs_stays_under_one_dollar(self) -> None:
        requests = [
            pilot.build_request(spec.model, self.messages, representation, repair=repair)
            for spec in pilot.MODEL_SPECS
            for representation in pilot.FORMATS
            for _repeat in range(pilot.REPEATS)
            for repair in (False, True)
        ]
        estimate = pilot.CostGuard().preflight(requests)
        self.assertLess(estimate, 1.0)
        reserved_estimate = pilot.CostGuard(
            reserved_usd=pilot.PRE_AMENDMENT_RESERVED_USD
        ).preflight(requests)
        self.assertLess(
            reserved_estimate + pilot.PRE_AMENDMENT_RESERVED_USD,
            1.0,
        )
        with self.assertRaises(RuntimeError):
            pilot.CostGuard(ceiling_usd=0.000001).preflight(requests[:1])

    def test_mocked_exact_trial_scores_every_message_and_terminal(self) -> None:
        seen: list[dict] = []

        def transport(request: dict) -> dict:
            seen.append(request)
            return _mock_response(self.messages)

        result = pilot.run_trial(
            "gpt-4o-mini",
            "symbolic",
            0,
            self.messages,
            transport,
            pilot.CostGuard(),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.exact_messages, 14)
        self.assertEqual(result.validator_valid_messages, 14)
        self.assertEqual(result.terminal_matches, result.terminal_total)
        self.assertEqual(result.repair_attempts, 0)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0]["store"], False)

    def test_mocked_deterministic_split_preserves_exact_order_and_totals(self) -> None:
        batches = pilot._message_batches(self.messages, pilot.LIVE_BATCH_SIZE)
        responses = iter(_mock_response(batch) for batch in batches)
        seen: list[dict] = []

        def transport(request: dict) -> dict:
            seen.append(request)
            return next(responses)

        result = pilot.run_trial(
            "gpt-4o-mini",
            "symbolic",
            0,
            self.messages,
            transport,
            pilot.CostGuard(),
            batch_size=pilot.LIVE_BATCH_SIZE,
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.exact_messages, 14)
        self.assertEqual(result.batch_count, len(batches))
        self.assertEqual(
            result.batch_message_counts,
            tuple(len(batch) for batch in batches),
        )
        self.assertEqual(len(result.attempt_diagnostics), len(batches))
        self.assertEqual(len(seen), len(batches))
        self.assertTrue(all(request["store"] is False for request in seen))

    def test_safe_diagnostic_retains_no_raw_text_or_response_identifier(self) -> None:
        response = _mock_response(self.messages)
        response["id"] = "should-not-survive"
        diagnostic = pilot.safe_response_diagnostic(
            response,
            attempt="primary",
            batch_index=0,
            parse_failure_code=None,
        )
        serialized = pilot._canonical_json(diagnostic)
        self.assertNotIn("should-not-survive", serialized)
        self.assertNotIn(pilot._canonical_json(self.messages[0].message), serialized)
        self.assertEqual(diagnostic["output_text_items"], 1)
        self.assertEqual(len(diagnostic["output_text_sha256"]), 64)

    def test_mocked_malformed_primary_triggers_one_successful_repair(self) -> None:
        responses = iter(
            [_mock_response(self.messages, malformed=True), _mock_response(self.messages)]
        )
        result = pilot.run_trial(
            "gpt-5-nano",
            "terse_english",
            0,
            self.messages,
            lambda _request: next(responses),
            pilot.CostGuard(),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.exact_messages, 14)
        self.assertEqual(result.malformed_initial, 1)
        self.assertEqual(result.repair_attempts, 1)
        self.assertEqual(result.repair_failures, 0)
        self.assertEqual(result.input_tokens, 2_000)
        self.assertEqual(result.output_tokens, 4_000)

    def test_valid_but_wrong_semantics_are_scored_not_repaired(self) -> None:
        wrong = copy.deepcopy(self.messages[0].message)
        wrong["confidence_ppm"] = 1 if wrong["confidence_ppm"] != 1 else 2
        wrapper = {
            "messages": [
                {
                    "index": index,
                    "message": wrong if index == 0 else item.message,
                }
                for index, item in enumerate(self.messages)
            ]
        }
        response = _mock_response(self.messages)
        response["output"][0]["content"][0]["text"] = json.dumps(wrapper)
        result = pilot.run_trial(
            "gpt-4o-mini",
            "json",
            0,
            self.messages,
            lambda _request: response,
            pilot.CostGuard(),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.exact_messages, 13)
        self.assertLess(result.terminal_matches, result.terminal_total)
        self.assertEqual(result.repair_attempts, 0)

    def test_output_wrapper_shape_and_order_fail_closed(self) -> None:
        parsed = pilot.parse_receiver_batch("{}", 14)
        self.assertTrue(parsed.malformed)
        self.assertEqual(parsed.failure_code, "wrapper_shape")
        wrapper = {
            "messages": [
                {"index": index + 1, "message": {}} for index in range(14)
            ]
        }
        parsed = pilot.parse_receiver_batch(json.dumps(wrapper), 14)
        self.assertTrue(parsed.malformed)
        self.assertEqual(parsed.failure_code, "record_index")


class FrozenLiveArtifactTests(unittest.TestCase):
    def test_live_results_are_frozen_without_raw_outputs_or_response_ids(self) -> None:
        self.assertTrue(pilot.FROZEN_LIVE_RESULTS)

        def keys(value: object) -> set[str]:
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, (list, tuple)):
                return set().union(*(keys(item) for item in value))
            return set()

        retained_keys = keys(pilot.FROZEN_LIVE_RESULTS)
        self.assertNotIn("response_id", retained_keys)
        self.assertNotIn("id", retained_keys)
        self.assertNotIn("output_text", retained_keys)
        self.assertNotIn("raw_output", retained_keys)
        self.assertIs(pilot.FROZEN_LIVE_RESULTS["store"], False)
        self.assertLessEqual(
            pilot.FROZEN_LIVE_RESULTS["actual_usage_estimated_usd"],
            pilot.FROZEN_LIVE_RESULTS["cost_ceiling_usd"],
        )

    def test_failed_gate_has_two_repeats_and_stops_remaining_matrix(self) -> None:
        counts = {}
        for trial in pilot.FROZEN_LIVE_RESULTS["trials"]:
            key = (trial["model"], trial["representation"])
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(
            counts,
            {("gpt-5-nano", "json"): 2},
        )
        self.assertIs(pilot.FROZEN_LIVE_RESULTS["gate"]["passed"], False)
        self.assertIs(
            pilot.FROZEN_LIVE_RESULTS["gate"]["matrix_continued"],
            False,
        )
        self.assertEqual(
            [trial["exact_messages"] for trial in pilot.FROZEN_LIVE_RESULTS["trials"]],
            [13, 14],
        )

    def test_historical_outcomes_are_unchanged_and_not_rebound_to_current_inputs(self) -> None:
        def digest(value: object) -> str:
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            return hashlib.sha256(encoded).hexdigest()

        self.assertEqual(
            digest(pilot.FROZEN_LIVE_RESULTS["trials"]),
            "2606cbe7977b625921b49f989c77ed5c5f8f49d1cd14f903888eeb857a2db93b",
        )
        self.assertEqual(
            digest(pilot.FROZEN_LIVE_RESULTS["pre_amendment_observations"]),
            "6513ceeaa9f523b9d5a850ff0935b021fb238a6e0086e28d3380f0146cd58d0e",
        )
        self.assertEqual(
            digest(pilot.FROZEN_LIVE_RESULTS["gate"]),
            "08d3307fd758f0b6bd67a57e7c875e46d8b3cb147528351da538c7458b09c834",
        )
        usage = {
            key: pilot.FROZEN_LIVE_RESULTS[key]
            for key in (
                "api_attempts",
                "preflight_worst_case_estimated_usd",
                "actual_usage_estimated_usd",
                "pre_amendment_reserved_usd",
                "experiment_cost_upper_bound_usd",
            )
        }
        self.assertEqual(
            digest(usage),
            "20e189ffc9e7b5eb54fb9637d60913e8aeb4ba06656b1f5a180595ec05fcbf49",
        )
        self.assertEqual(
            pilot.FROZEN_LIVE_RESULTS["pilot_corpus_sha256"],
            pilot.MEASURED_PILOT_CORPUS_SHA256,
        )
        self.assertEqual(
            pilot.FROZEN_LIVE_RESULTS["symbolic_text_sha256"],
            pilot.MEASURED_SYMBOLIC_TEXT_SHA256,
        )
        self.assertEqual(
            pilot.FROZEN_LIVE_RESULTS["current_urusilla_pilot_corpus_sha256"],
            pilot.PILOT_CORPUS_SHA256,
        )
        self.assertEqual(
            pilot.FROZEN_LIVE_RESULTS["current_urusilla_symbolic_text_sha256"],
            pilot.SYMBOLIC_TEXT_SHA256,
        )
        self.assertIs(
            pilot.FROZEN_LIVE_RESULTS["provider_rerun_after_urusilla_cutover"],
            False,
        )
        self.assertNotEqual(
            pilot.MEASURED_PILOT_CORPUS_SHA256,
            pilot.PILOT_CORPUS_SHA256,
        )

    def test_report_discloses_live_scope_cost_and_unfavorable_results(self) -> None:
        report = pilot.render_report(pilot.FROZEN_LIVE_RESULTS)
        for required in (
            "Every unfavorable field, token, latency, malformed-output, and repair result",
            "does **not** measure sender generation",
            "store=false",
            "Cold grammar and warm amortization",
            "far too small for a general model-comprehension claim",
            "Cross-vendor and unseen-model transfer remain unknown",
            "Task success",
            "No provider call was rerun after the Urusilla cutover",
            "must not be attributed to those current inputs",
        ):
            self.assertIn(required, report)

    def test_published_report_contains_current_source_digests(self) -> None:
        report_path = HERE / pilot.REPORT_NAME
        self.assertTrue(report_path.is_file())
        report = report_path.read_text(encoding="utf-8")
        self.assertIn(
            hashlib.sha256((HERE / "urusilla_model_comprehension_pilot.py").read_bytes()).hexdigest(),
            report,
        )
        self.assertIn(hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), report)


if __name__ == "__main__":
    unittest.main()
