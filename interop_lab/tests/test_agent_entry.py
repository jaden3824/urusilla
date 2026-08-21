from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
from contextlib import redirect_stderr, redirect_stdout

from interop_lab.validate_agent_entry import (
    BASELINE_REVISION,
    DEFAULT_MANIFEST,
    EXPECTED_PUBLIC_MIRRORS,
    EXPECTED_TRACKS,
    QUICK_ARTIFACT_REVISION,
    REPO_ROOT,
    ValidationError,
    load_manifest,
    main,
    strict_json_loads,
    validate_entry,
)


class AgentEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = load_manifest(DEFAULT_MANIFEST)

    def test_manifest_validates_entirely_offline(self) -> None:
        report = validate_entry(self.entry)
        self.assertTrue(report["valid"])
        self.assertFalse(report["network_used"])
        self.assertEqual(report["baseline_revision"], BASELINE_REVISION)
        self.assertEqual(report["general_unfamiliar_agent_saving_percent"], 0.0)
        self.assertEqual(report["capsule_signature_status"], "unsigned")
        self.assertFalse(report["direct_agent_dialogue_evidence"])
        self.assertFalse(report["external_adoption_evidence"])
        self.assertEqual(report["artifact_count"], 15)
        self.assertEqual(report["public_challenge_mirror_count"], 2)
        self.assertEqual(
            report["public_challenge_mirrors_current_status"],
            "snapshot-only-network-not-checked",
        )

    def test_duplicate_json_member_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate JSON member"):
            strict_json_loads('{"schema_version":"a","schema_version":"b"}')

    def test_short_or_changed_baseline_revision_is_rejected(self) -> None:
        for revision in ("f612ea1", "0" * 40):
            with self.subTest(revision=revision):
                entry = copy.deepcopy(self.entry)
                entry["project"]["baseline_revision"] = revision
                with self.assertRaisesRegex(ValidationError, "revision|40-character"):
                    validate_entry(entry)

    def test_moving_or_html_artifact_identity_is_rejected(self) -> None:
        for replacement in (
            "https://raw.githubusercontent.com/jaden3824/urusilla/main/urusilla_capsule_v0_1.json",
            "https://github.com/jaden3824/urusilla/blob/f612ea1/urusilla_capsule_v0_1.json",
            "https://raw.githubusercontent.com/jaden3824/urusilla/v0.1.0-experimental/urusilla_capsule_v0_1.json",
        ):
            with self.subTest(replacement=replacement):
                entry = copy.deepcopy(self.entry)
                entry["artifacts"][0]["raw_url"] = replacement
                with self.assertRaisesRegex(ValidationError, "full frozen commit and raw bytes"):
                    validate_entry(entry)

    def test_artifact_digest_and_byte_count_are_verified(self) -> None:
        for field, value, message in (
            ("sha256", "sha256:" + "0" * 64, "digest"),
            ("bytes", 1, "byte count"),
        ):
            with self.subTest(field=field):
                entry = copy.deepcopy(self.entry)
                entry["artifacts"][0][field] = value
                with self.assertRaisesRegex(ValidationError, message):
                    validate_entry(entry)

    def test_zero_percent_unsigned_and_surface_only_boundaries_are_frozen(self) -> None:
        mutations = (
            ("general_unfamiliar_agent_saving_percent", 1.0, "saving must be 0%"),
            ("capsule_signature_status", "verified", "unsigned"),
            ("direct_agent_dialogue_evidence", True, "dialogue"),
            ("external_adoption_evidence", True, "adoption"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                entry = copy.deepcopy(self.entry)
                entry["project"][field] = value
                with self.assertRaisesRegex(ValidationError, message):
                    validate_entry(entry)

    def test_effect_authority_is_rejected(self) -> None:
        for field in (
            "state_persistence_authorized",
            "permission_expansion_authorized",
            "spending_authorized",
            "external_effects_authorized",
        ):
            with self.subTest(field=field):
                entry = copy.deepcopy(self.entry)
                entry["safety_boundary"][field] = True
                with self.assertRaisesRegex(ValidationError, "non-effect-authorizing"):
                    validate_entry(entry)

    def test_every_track_has_one_direct_canonical_submission_uri(self) -> None:
        tracks = {track["id"]: track for track in self.entry["tracks"]}
        self.assertEqual(set(tracks), set(EXPECTED_TRACKS))
        for track_id, expected in EXPECTED_TRACKS.items():
            with self.subTest(track=track_id):
                self.assertEqual(
                    tracks[track_id]["canonical_submission_uri"],
                    expected["canonical_submission_uri"],
                )
                self.assertFalse(tracks[track_id]["requires_installation"])

    def test_every_track_has_a_digest_bound_offline_challenge(self) -> None:
        tracks = {track["id"]: track for track in self.entry["tracks"]}
        for track_id, track in tracks.items():
            with self.subTest(track=track_id):
                offline = track["offline_challenge"]
                body = (REPO_ROOT / offline["path"]).read_bytes()
                self.assertEqual(len(body), offline["bytes"])
                self.assertEqual(
                    "sha256:" + hashlib.sha256(body).hexdigest(),
                    offline["sha256"],
                )
        for track_id, track in tracks.items():
            offline = track["offline_challenge"]
            if offline["provenance"] != "public-source-mirror-at-recorded-updated-at":
                continue
            with self.subTest(public_mirror=track_id):
                expected = EXPECTED_PUBLIC_MIRRORS[track_id]
                self.assertEqual(offline["path"], expected["body_path"])
                self.assertEqual(offline["sha256"], expected["body_sha256"])

    def test_offline_challenge_identity_cannot_be_silently_changed(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["tracks"][0]["offline_challenge"]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValidationError, "offline_challenge changed"):
            validate_entry(entry)

    def test_missing_track_or_submission_uri_is_rejected(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["tracks"].pop()
        with self.assertRaisesRegex(ValidationError, "four tracks"):
            validate_entry(entry)

        entry = copy.deepcopy(self.entry)
        entry["tracks"][0]["canonical_submission_uri"] = (
            "https://github.com/jaden3824/urusilla/issues/new/choose"
        )
        with self.assertRaisesRegex(ValidationError, "canonical_submission_uri"):
            validate_entry(entry)

    def test_entry_documents_expose_exact_fast_routes(self) -> None:
        required = (
            "agent-entry.json",
            "AGENT_QUICKSTART.md",
            "interop_lab/challenges/quick_60s.json",
            "https://github.com/jaden3824/urusilla/discussions/8",
            "https://github.com/jaden3824/urusilla/issues/9",
            "https://github.com/jaden3824/urusilla/issues/7",
        )
        for relative in ("README.md", "llms.txt", "AGENTS.md", "AGENT_QUICKSTART.md"):
            with self.subTest(relative=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")
                for item in required:
                    self.assertIn(item, text)

        quickstart = (REPO_ROOT / "AGENT_QUICKSTART.md").read_text(encoding="utf-8")
        for relative in (
            "interop_lab/challenges/quick_60s.json",
            "interop_lab/challenges/issue_9.body.md",
            "interop_lab/RESULT_FORMAT_MAPPING.md",
            "interop_lab/validate_result.py - --json",
        ):
            self.assertIn(relative, quickstart)

    def test_quick_60s_is_one_fetch_and_four_fields(self) -> None:
        tracks = {track["id"]: track for track in self.entry["tracks"]}
        track = tracks["quick_60s"]
        self.assertEqual(track["artifact_ids"], ["quick_60s_challenge"])
        self.assertEqual(
            track["challenge_uri"],
            "https://raw.githubusercontent.com/jaden3824/urusilla/"
            f"{QUICK_ARTIFACT_REVISION}/interop_lab/challenges/quick_60s.json",
        )
        self.assertEqual(
            track["canonical_submission_uri"],
            "https://github.com/jaden3824/urusilla/discussions/8",
        )
        packet = json.loads(
            (REPO_ROOT / "interop_lab/challenges/quick_60s.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(packet["time_budget_seconds"], 60)
        self.assertEqual(
            packet["response"]["required_fields"],
            ["decision", "reason", "participant", "runtime"],
        )
        self.assertEqual(
            packet["evidence_boundary"][
                "general_unfamiliar_agent_saving_percent"
            ],
            0.0,
        )
        self.assertTrue(
            packet["submission"]["posting_is_separate_external_action"]
        )

    def test_fast_entry_files_stay_small(self) -> None:
        self.assertLessEqual((REPO_ROOT / "llms.txt").stat().st_size, 4_096)
        self.assertLessEqual((REPO_ROOT / "AGENT_QUICKSTART.md").stat().st_size, 8_192)

    def test_quick_form_exposes_all_outcomes_and_scope_boundaries(self) -> None:
        text = (REPO_ROOT / ".github/ISSUE_TEMPLATE/quick-feedback.yml").read_text(
            encoding="utf-8"
        )
        for outcome in ("exact", "mismatch", "counterexample", "ambiguity", "refusal"):
            self.assertIn(f"- {outcome}", text)
        self.assertIn('- "null"', text)
        self.assertIn("direct agent dialogue", text)
        self.assertIn("external adoption", text)
        self.assertIn("external effect", text)

    def test_cli_emits_machine_readable_offline_report(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([str(DEFAULT_MANIFEST), "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertFalse(report["network_used"])


if __name__ == "__main__":
    unittest.main()
