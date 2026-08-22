from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = (
    REPO_ROOT
    / "interop_lab/evidence/gemini_pro_quick_60s_solicited_2026_08_22.json"
)


class SolicitedAgentFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))

    def test_record_preserves_solicited_non_claim_status(self) -> None:
        self.assertEqual(
            self.record["classification"], "PROJECT-SOLICITED-EXTERNAL-MODEL"
        )
        self.assertFalse(self.record["claim_eligible"])
        self.assertEqual(
            self.record["attempts"][0]["disposition"], "invalid-null"
        )
        self.assertEqual(
            self.record["attempts"][1]["disposition"],
            "valid-solicited-feedback",
        )
        self.assertEqual(
            self.record["attempts"][1]["parsed_response"]["decision"],
            "ROLLBACK",
        )
        self.assertTrue(self.record["scoring"]["decision_match"])
        self.assertFalse(self.record["scoring"]["full_packet_fetched_by_model"])
        self.assertFalse(
            self.record["scoring"]["exact_artifact_identity_verified_by_model"]
        )

        boundary = self.record["claim_boundary"]
        for field in (
            "independent_reproduction",
            "organic_adoption",
            "external_adoption_evidence",
            "general_efficiency_evidence",
            "changes_general_zero_percent",
        ):
            with self.subTest(field=field):
                self.assertFalse(boundary[field])
        self.assertEqual(boundary["project_solicited_agent_feedback_count"], 1)

    def test_embedded_transcript_identity_is_recomputable(self) -> None:
        for attempt in self.record["attempts"]:
            for prefix in ("prompt", "observed_response"):
                with self.subTest(attempt=attempt["attempt"], prefix=prefix):
                    text = attempt[f"{prefix}_text"]
                    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
                    self.assertEqual(attempt[f"{prefix}_sha256"], digest)
                    self.assertEqual(attempt[f"{prefix}_characters"], len(text))

    def test_challenge_identity_matches_repository_bytes(self) -> None:
        source = self.record["source_state"]
        challenge = REPO_ROOT / source["challenge_path"]
        payload = challenge.read_bytes()
        self.assertEqual(source["challenge_bytes"], len(payload))
        self.assertEqual(
            source["challenge_sha256"],
            "sha256:" + hashlib.sha256(payload).hexdigest(),
        )

    def test_no_provider_receipt_or_token_usage_is_implied(self) -> None:
        surface = self.record["provider_surface"]
        self.assertFalse(surface["authenticated_provider_receipt"])
        self.assertIsNone(surface["exact_model_version"])
        self.assertIsNone(surface["provider_token_usage"])


if __name__ == "__main__":
    unittest.main()
