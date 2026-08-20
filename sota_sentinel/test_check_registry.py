#!/usr/bin/env python3
"""Regression tests for the standard-library SOTA Sentinel checker."""

from __future__ import annotations

import copy
import unittest

from check_registry import DEFAULT_REGISTRY, RegistryError, load_registry, validate_registry


class RegistryValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid = load_registry(DEFAULT_REGISTRY)

    def test_release_registry_is_valid(self) -> None:
        validate_registry(copy.deepcopy(self.valid))

    def test_sota_claim_fails_closed(self) -> None:
        value = copy.deepcopy(self.valid)
        value["project_claims"]["sota_claim_made"] = True
        with self.assertRaisesRegex(RegistryError, "must not make a project SOTA claim"):
            validate_registry(value)

    def test_world_record_claim_fails_closed(self) -> None:
        value = copy.deepcopy(self.valid)
        value["project_claims"]["world_record_claim_made"] = True
        with self.assertRaisesRegex(RegistryError, "must not make a project world-record claim"):
            validate_registry(value)

    def test_paid_call_flag_fails_closed(self) -> None:
        value = copy.deepcopy(self.valid)
        value["project_claims"]["paid_model_calls_used"] = True
        with self.assertRaisesRegex(RegistryError, "forbidden paid model call"):
            validate_registry(value)

    def test_unpinned_available_repository_fails(self) -> None:
        value = copy.deepcopy(self.valid)
        first_with_code = next(
            record for record in value["records"] if record["artifacts"]["code"]["revision"]
        )
        first_with_code["artifacts"]["code"]["revision"] = "deadbeef"
        with self.assertRaisesRegex(RegistryError, "40-character lowercase Git commit"):
            validate_registry(value)

    def test_unknown_comparability_lane_fails(self) -> None:
        value = copy.deepcopy(self.valid)
        value["records"][0]["headline"]["comparability_lane"] = "invented_lane"
        with self.assertRaisesRegex(RegistryError, "unknown lane"):
            validate_registry(value)

    def test_incomparable_headline_requires_reason(self) -> None:
        value = copy.deepcopy(self.valid)
        record = next(
            item for item in value["records"] if item["comparison_class"] == "headline_only"
        )
        record["headline"]["incomparable_reason"] = ""
        with self.assertRaisesRegex(RegistryError, "required for incomparable headline"):
            validate_registry(value)

    def test_claim_gate_references_existing_record(self) -> None:
        value = copy.deepcopy(self.valid)
        value["claim_gate"]["primary_baseline"] = "missing_record"
        with self.assertRaisesRegex(RegistryError, "unknown record"):
            validate_registry(value)


if __name__ == "__main__":
    unittest.main()
