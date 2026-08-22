from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class ContributionEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = json.loads(
            (REPO_ROOT / "contribution-entry.json").read_text(encoding="utf-8")
        )
        self.registry = json.loads(
            (REPO_ROOT / "contributor-evidence.json").read_text(encoding="utf-8")
        )

    def test_fast_path_binds_the_exact_quick_challenge(self) -> None:
        challenge = self.entry["fast_path"]["challenge"]
        self.assertEqual(
            challenge["revision"],
            "cd220adb311d8763009fc9b524b2633b117aac4d",
        )
        self.assertIn(challenge["revision"], challenge["raw_url"])
        self.assertNotIn("/main/", challenge["raw_url"])

        payload = (REPO_ROOT / "interop_lab/challenges/quick_60s.json").read_bytes()
        self.assertEqual(challenge["bytes"], len(payload))
        self.assertEqual(
            challenge["sha256"],
            "sha256:" + hashlib.sha256(payload).hexdigest(),
        )
        self.assertEqual(
            self.entry["fast_path"]["response_fields"],
            ["decision", "reason", "participant", "runtime"],
        )

    def test_escalation_paths_are_distinct_and_public(self) -> None:
        paths = self.entry["escalation_paths"]
        self.assertEqual(
            [path["id"] for path in paths],
            ["counterexample", "codec_candidate", "corpus_example"],
        )
        for path in paths:
            with self.subTest(path=path["id"]):
                self.assertTrue(path["issue_url"].startswith("https://github.com/"))
                self.assertTrue(path["required_public_evidence"])

    def test_claim_and_authority_boundaries_remain_false(self) -> None:
        self.assertEqual(
            self.entry["current_general_unfamiliar_agent_saving_percent"], 0.0
        )
        self.assertFalse(self.entry["external_adoption_evidence"])
        self.assertEqual(self.entry["independent_reproduction_count"], 0)
        self.assertTrue(
            all(value is False for value in self.entry["safety"].values())
        )
        self.assertTrue(
            all(value is False for value in self.entry["claim_boundary"].values())
        )

    def test_evidence_registry_starts_empty_without_implied_participation(self) -> None:
        self.assertEqual(self.registry["validated_record_count"], 0)
        self.assertEqual(self.registry["independently_reproduced_record_count"], 0)
        self.assertEqual(self.registry["records"], [])
        self.assertTrue(
            all(value is False for value in self.registry["claim_boundary"].values())
        )

    def test_linked_issue_forms_exist(self) -> None:
        templates = REPO_ROOT / ".github/ISSUE_TEMPLATE"
        for name in (
            "quick-60s.yml",
            "counterexample.yml",
            "codec-candidate.yml",
            "corpus-example.yml",
        ):
            with self.subTest(name=name):
                text = (templates / name).read_text(encoding="utf-8")
                self.assertIn("claim boundary", text.lower())
                self.assertIn("required: true", text)


if __name__ == "__main__":
    unittest.main()
