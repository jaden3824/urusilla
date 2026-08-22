"""Mutation tests for the bounded public action-state language probe."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VALIDATOR_PATH = ROOT / "tools" / "validate_language_probe.py"
PROJECT_RECORD_PATH = (
    ROOT
    / "interop_lab"
    / "evidence"
    / "public_language_probe_project_operated_2026_08_23.json"
)
SPEC = importlib.util.spec_from_file_location("validate_language_probe", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def canonical(value: object) -> str:
    return validator.canonical_json(value)


def fallback_response() -> dict[str, object]:
    return {
        "schema_version": validator.RESPONSE_SCHEMA,
        "probe_id": validator.PROBE_ID,
        "disposition": "fallback",
        "decode": None,
        "encode": None,
        "fallback": {
            "route": "json",
            "stage": "encode",
            "reason_code": "ambiguous-meaning",
            "reason": "The bounded meaning could not be encoded unambiguously.",
        },
    }


class ProbeArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = validator.load_probe()

    def test_probe_is_one_fetch_declarative_and_profile_scoped(self) -> None:
        self.assertEqual(self.probe["limits"]["maximum_fetches"], 1)
        self.assertFalse(
            self.probe["limits"]["linked_resource_dereference_authorized"]
        )
        self.assertFalse(
            self.probe["authority_boundary"]["external_effects_authorized"]
        )
        self.assertIn("core binary wire codec", self.probe["claim_scope"])

    def test_probe_frozen_preimages_and_hashes_validate(self) -> None:
        self.assertEqual(
            self.probe["tasks"]["decode"]["input_canonical_sha256"],
            validator._canonical_sha256(validator.DECODE_INPUT),
        )
        self.assertEqual(
            self.probe["tasks"]["encode"]["expected_candidate_canonical_sha256"],
            validator._canonical_sha256(validator.expected_encode_candidate()),
        )
        self.assertEqual(
            self.probe["evaluation"]["completed_response_canonical_sha256"],
            validator.sha256_text(
                canonical(validator.expected_completed_response())
            ),
        )

    def test_probe_mutation_is_rejected(self) -> None:
        mutated = deepcopy(self.probe)
        mutated["tasks"]["decode"]["input"]["outcome"]["status"] = "succeeded"
        with self.assertRaises(validator.ProbeValidationError):
            validator.validate_probe(mutated)

        mutated = deepcopy(self.probe)
        del mutated["language_profile"]["decode_projection"]["atom_mapping"][
            "n true"
        ]
        with self.assertRaises(validator.ProbeValidationError):
            validator.validate_probe(mutated)


class CompletedResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = validator.load_probe()

    def classify(self, value: object) -> dict[str, object]:
        return validator.classify_response(self.probe, canonical(value))

    def test_exact_completed_response_passes(self) -> None:
        expected = validator.expected_completed_response()
        result = self.classify(expected)
        self.assertEqual(result["classification"], "PASS")
        self.assertTrue(result["language_pass"])
        self.assertFalse(result["safe_fallback"])

    def test_semantic_mutations_fail(self) -> None:
        mutations: list[tuple[str, object]] = []

        negation = validator.expected_completed_response()
        negation["decode"]["facts"][0]["truth"] = True
        mutations.append(("negation-inversion", negation))

        null_replacement = validator.expected_completed_response()
        null_replacement["encode"]["candidates"][0]["outcome"]["value"] = "ok"
        mutations.append(("null-replacement", null_replacement))

        failure_rewrite = validator.expected_completed_response()
        failure_rewrite["decode"]["outcome"]["status"] = "succeeded"
        mutations.append(("failure-to-success", failure_rewrite))

        source_swap = validator.expected_completed_response()
        source_swap["encode"]["candidates"][0]["goal"]["src"] = "agent:other"
        mutations.append(("source-ownership", source_swap))

        slot_move = validator.expected_completed_response()
        candidate = slot_move["encode"]["candidates"][0]
        candidate["state"] = []
        candidate["needs"].append(
            {"p": "check.passed", "a": ["unit"], "n": True, "src": "runner:8"}
        )
        mutations.append(("semantic-slot-move", slot_move))

        invented_action = validator.expected_completed_response()
        invented_action["encode"]["candidates"][0]["action"] = {
            "name": "publish",
            "args": {},
            "status": "proposed",
            "effects": ["external.publish"],
        }
        mutations.append(("invented-action", invented_action))

        for label, mutation in mutations:
            with self.subTest(label=label):
                result = self.classify(mutation)
                self.assertEqual(result["classification"], "FAIL")
                self.assertFalse(result["language_pass"])

    def test_structural_and_canonical_mutations_fail(self) -> None:
        extra = validator.expected_completed_response()
        extra["invented"] = True
        self.assertEqual(self.classify(extra)["classification"], "FAIL")

        pretty = json.dumps(
            validator.expected_completed_response(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self.assertEqual(
            validator.classify_response(self.probe, pretty)["reason_code"],
            "response-not-canonical",
        )

        duplicate = canonical(validator.expected_completed_response()).replace(
            '{"decode":',
            '{"probe_id":"language-use-001","decode":',
            1,
        )
        result = validator.classify_response(self.probe, duplicate)
        self.assertEqual(result["classification"], "FAIL")
        self.assertEqual(result["reason_code"], "response-invalid-json")


class SafeFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = validator.load_probe()

    def classify(self, value: object) -> dict[str, object]:
        return validator.classify_response(self.probe, canonical(value))

    def test_closed_fallback_is_valid_but_never_a_language_pass(self) -> None:
        result = self.classify(fallback_response())
        self.assertEqual(result["classification"], "SAFE_FALLBACK")
        self.assertFalse(result["language_pass"])
        self.assertTrue(result["safe_fallback"])

    def test_fallback_with_partial_output_fails(self) -> None:
        response = fallback_response()
        response["decode"] = validator.expected_decode_projection()
        result = self.classify(response)
        self.assertEqual(result["classification"], "FAIL")
        self.assertEqual(result["reason_code"], "fallback-contains-partial-output")

    def test_open_or_malformed_fallback_fails(self) -> None:
        invalid_cases = []

        route = fallback_response()
        route["fallback"]["route"] = "execute"
        invalid_cases.append(route)

        reason_code = fallback_response()
        reason_code["fallback"]["reason_code"] = "invented"
        invalid_cases.append(reason_code)

        extra = fallback_response()
        extra["fallback"]["authority"] = "granted"
        invalid_cases.append(extra)

        empty_reason = fallback_response()
        empty_reason["fallback"]["reason"] = ""
        invalid_cases.append(empty_reason)

        for case in invalid_cases:
            with self.subTest(case=case):
                self.assertEqual(self.classify(case)["classification"], "FAIL")


class ProjectOperatedReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = validator.load_probe()
        cls.record = json.loads(PROJECT_RECORD_PATH.read_text(encoding="utf-8"))

    def test_normalized_response_is_bound_and_passes_only_after_rendering(self) -> None:
        normalized = self.record["normalized_response"]
        self.assertFalse(normalized["raw_agent_response_bytes_retained"])
        self.assertFalse(normalized["direct_agent_response_validated"])
        response = normalized["response"]
        raw = canonical(response).encode("utf-8")
        self.assertEqual(
            "sha256:" + hashlib.sha256(raw).hexdigest(),
            normalized["sha256"],
        )
        self.assertEqual(len(raw), normalized["utf8_bytes"])
        result = validator.classify_response(self.probe, raw.decode("utf-8"))
        self.assertEqual(result["classification"], "PASS")
        self.assertTrue(result["language_pass"])
        pretty = json.dumps(response, ensure_ascii=False, indent=2)
        self.assertEqual(
            validator.classify_response(self.probe, pretty)["classification"],
            "FAIL",
        )

    def test_record_binds_the_probe_and_validator_source_bytes(self) -> None:
        source_state = self.record["source_state"]
        for path_key, digest_key, bytes_key in (
            ("probe_path", "probe_file_sha256", "probe_file_bytes"),
            ("validator_path", "validator_file_sha256", "validator_file_bytes"),
        ):
            raw = (ROOT / source_state[path_key]).read_bytes()
            self.assertEqual(len(raw), source_state[bytes_key])
            self.assertEqual(
                "sha256:" + hashlib.sha256(raw).hexdigest(),
                source_state[digest_key],
            )

    def test_delivery_failure_is_not_relabelled_as_language_failure(self) -> None:
        trials = {trial["trial_id"]: trial for trial in self.record["trials"]}
        self.assertEqual(trials["A"]["delivery"]["status"], "DELIVERY_FAILURE")
        self.assertFalse(trials["A"]["response_received"])
        self.assertFalse(trials["A"]["validator"]["invoked"])
        self.assertIsNone(trials["A"]["validator"]["classification"])
        for trial_id in ("B", "C"):
            observed = trials[trial_id]["validator"]
            self.assertEqual(observed["classification"], "NORMALIZED_PASS")
            self.assertEqual(observed["validator_returned_classification"], "PASS")
            self.assertTrue(observed["language_pass_on_normalized_input"])
            self.assertIsNone(observed["direct_response_language_pass"])
        boundary = self.record["evidence_classification"]
        self.assertFalse(boundary["claim_eligible"])
        self.assertFalse(boundary["external_independent_reproduction"])
        self.assertFalse(boundary["external_adoption_evidence"])

    def test_aggregate_recomputes_from_trials(self) -> None:
        trials = self.record["trials"]
        aggregate = self.record["aggregate"]
        delivered = [
            trial for trial in trials if trial["delivery"]["status"] == "DELIVERED"
        ]
        normalized_passes = [
            trial
            for trial in delivered
            if trial["validator"].get("classification") == "NORMALIZED_PASS"
        ]
        self.assertEqual(len(trials), aggregate["trial_count"])
        self.assertEqual(len(delivered), aggregate["delivered_response_count"])
        self.assertEqual(
            len(normalized_passes),
            aggregate["normalized_rendering_validator_pass_count"],
        )
        self.assertIsNone(aggregate["direct_response_pass_count"])


if __name__ == "__main__":
    unittest.main()
