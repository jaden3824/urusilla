from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import external_ood_evaluation as evaluation


MANIFEST_SHA256 = "892a5218d09f84ffb54dbda9b726660ead30f12d2ed651d37ca1c852929c3fb5"
MEASUREMENT_SHA256 = "4e6d3160cecdd68780e9a0a1fb36488e6e6e19197a60ee952697712d6fed493c"
REPEAT_MEASUREMENT_SHA256 = "d94f8dcb5c2b232afec9700bcfc5b936e77475c1fb2263dc00a42611d614440e"
OUTCOME_SHA256 = "359b07351f1edf343910d723ea7a12de6e48b63a7fa6d87fff88a5ce6a6380de"
INVENTORY_SHA256 = "2a7e903cf690ae82498488a2ea2899f24415b0de0e845666d855676128eb6518"


class ExternalOODEvaluationTests(unittest.TestCase):
    def _manifest_path(self) -> Path:
        supplied = os.environ.get("EXTERNAL_OOD_MANIFEST")
        if supplied:
            return Path(supplied).resolve()
        path = evaluation.EVIDENCE_ROOT / f"premeasurement-manifest-{MANIFEST_SHA256}.json"
        self.assertTrue(path.is_file(), "restore the retained content-addressed manifest")
        return path

    def _measurement_path(self, manifest_digest: str) -> Path:
        supplied = os.environ.get("EXTERNAL_OOD_MEASUREMENT")
        if supplied:
            return Path(supplied).resolve()
        self.assertEqual(manifest_digest, MANIFEST_SHA256)
        path = evaluation.EVIDENCE_ROOT / f"measurement-{MEASUREMENT_SHA256}.json"
        self.assertTrue(path.is_file(), "restore the retained content-addressed measurement")
        return path

    def test_json_fence_extraction_is_deterministic(self) -> None:
        source = b'''before
```json
{"b": 2, "a": 1}
```
```json
{not valid}
```
```
[{"c": 3}, {"d": 4}]
```
'''
        first = evaluation.extract_json_fences(source)
        second = evaluation.extract_json_fences(source)
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            (
                ("/json-fence/0", {"b": 2, "a": 1}),
                ("/json-fence/2/0", {"c": 3}),
                ("/json-fence/2/1", {"d": 4}),
            ),
        )

    def test_wrapper_is_source_bound_and_deterministic(self) -> None:
        record = {
            "protocol_id": "example-protocol",
            "source_uri": "https://example.test/repository/blob/0123456789abcdef0123456789abcdef01234567/example.json",
            "source_revision": "0123456789abcdef0123456789abcdef01234567",
            "source_path": "example.json",
            "source_file_sha256": "a" * 64,
            "source_locator": "$",
            "source_object_sha256": "b" * 64,
            "source_object_canonical_json": '{"value":1}',
        }
        first = evaluation.build_wrapped_message(record, 1)
        second = evaluation.build_wrapped_message(record, 1)
        changed = evaluation.build_wrapped_message(
            {**record, "source_object_sha256": "c" * 64}, 1
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first["id"], changed["id"])
        self.assertEqual(first["body"]["source_json"], '{"value":1}')
        self.assertEqual(first["body"]["kind"], "x:external-ood-record")

    def test_manifest_and_corpus_are_content_addressed(self) -> None:
        manifest_path = self._manifest_path()
        manifest, digest = evaluation._load_content_addressed(
            manifest_path, "premeasurement-manifest"
        )
        messages = evaluation._verify_frozen_inputs(manifest)
        self.assertEqual(manifest["format"], evaluation.MANIFEST_FORMAT)
        self.assertEqual(manifest["stage"], evaluation.RETAINED_STAGE)
        self.assertEqual(
            manifest["external_data_role"],
            "retained_evaluation_only_no_new_training_or_tuning",
        )
        self.assertTrue(manifest["corpus_revealed_before_refreeze"])
        self.assertFalse(manifest["fresh_confirmatory_status"])
        self.assertFalse(
            manifest["source_selection"]["retained_acquisition"]["network_used"]
        )
        self.assertEqual(
            manifest["amendment_chain"]["supersedes_manifest_sha256"],
            "0f10c74e4b640af58ef0daaaef93864be87e6b8a265739bb9aa5984db68433c8",
        )
        self.assertFalse(
            manifest["amendment_chain"]["historical_candidate_snapshots_available"]
        )
        self.assertEqual(manifest["corpus"]["message_count"], 43)
        self.assertEqual(len(messages), 43)
        self.assertEqual(len(manifest["source_selection"]["licenses"]), 4)
        self.assertEqual(len(manifest["frozen_candidates"]["source_snapshots"]), 12)
        self.assertEqual(len(digest), 64)
        corpus_path = evaluation.ROOT / manifest["corpus"]["corpus_file"]
        self.assertEqual(
            corpus_path.name,
            f"corpus-{manifest['corpus']['corpus_file_sha256']}.json",
        )
        for record, digest_key in (
            *(
                (record, "source_file_sha256")
                for record in manifest["source_selection"]["source_groups"]
            ),
            *(
                (record, "license_file_sha256")
                for record in manifest["source_selection"]["licenses"]
            ),
        ):
            cached = evaluation.ROOT / record["cache_file"]
            self.assertEqual(cached.stem, record[digest_key])
        self.assertEqual(
            {key: value["message_count"] for key, value in manifest["corpus"]["partitions"].items()},
            {
                "all": 43,
                "w3c-activitystreams-2.0": 12,
                "cncf-cloudevents-1.0.2": 7,
                "official-mcp-2026-07-28": 12,
                "oasis-stix-2.1-examples": 12,
            },
        )

    def test_archived_candidate_snapshots_are_content_addressed_and_fail_closed(self) -> None:
        manifest, _digest = evaluation._load_content_addressed(
            self._manifest_path(), "premeasurement-manifest"
        )
        evaluation._verify_candidate_snapshots(manifest)
        for name, record in manifest["frozen_candidates"]["source_snapshots"].items():
            path = evaluation.ROOT / record["snapshot_file"]
            self.assertEqual(evaluation.sha256_file(path), record["sha256"], name)
            self.assertIn(record["sha256"], path.name)
        tampered = json.loads(json.dumps(manifest))
        first = sorted(tampered["frozen_candidates"]["source_snapshots"])[0]
        tampered["frozen_candidates"]["source_snapshots"][first]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "candidate snapshot identity changed"):
            evaluation._verify_candidate_snapshots(tampered)

    def test_archived_verification_is_independent_of_later_live_source_drift(self) -> None:
        manifest, _digest = evaluation._load_content_addressed(
            self._manifest_path(), "premeasurement-manifest"
        )
        with patch.object(
            evaluation,
            "_candidate_source_digests",
            return_value={"later-source": "0" * 64},
        ):
            self.assertEqual(len(evaluation._verify_frozen_inputs(manifest)), 43)
            with self.assertRaisesRegex(RuntimeError, "current candidate source changed"):
                evaluation._verify_frozen_inputs(
                    manifest, require_current_candidates=True
                )

    def test_measurement_is_bound_and_preserves_unfavorable_outcomes(self) -> None:
        manifest_path = self._manifest_path()
        _manifest, manifest_digest = evaluation._load_content_addressed(
            manifest_path, "premeasurement-manifest"
        )
        measurement_path = self._measurement_path(manifest_digest)
        verified = evaluation.verify(manifest_path, measurement_path)
        self.assertTrue(verified["manifest_verified"])
        self.assertTrue(verified["measurement_verified"])

        measurement, _digest = evaluation._load_content_addressed(
            measurement_path, "measurement"
        )
        self.assertEqual(measurement["format"], evaluation.MEASUREMENT_FORMAT)
        self.assertEqual(measurement["deterministic_outcome_sha256"], OUTCOME_SHA256)
        self.assertTrue(measurement["corpus_revealed_before_refreeze"])
        self.assertFalse(measurement["fresh_confirmatory_status"])
        self.assertFalse(measurement["archive_network_used"])
        self.assertEqual(measurement["provider_calls"], 0)
        self.assertFalse(measurement["external_corpus_used_for_training_or_tuning"])
        self.assertTrue(measurement["candidate_sources_verified_unchanged"])
        self.assertEqual(measurement["corpus"]["message_count"], 43)
        for result in measurement["exactness"]["fixed"].values():
            self.assertEqual(result["exact"], result["trials"])
            self.assertEqual(result["deterministic"], result["trials"])
        for by_profile in measurement["exactness"]["adaptive"].values():
            for result in by_profile.values():
                self.assertEqual(result["exact"], result["trials"])
                self.assertEqual(result["deterministic"], result["trials"])
        outcomes = measurement["hypothesis_outcomes"]
        for key in (
            "H1_exactness",
            "H2_fallback",
            "H3_v05_selection",
            "H4_v06_warm_guard",
            "H5_v06_cold_guard",
        ):
            self.assertTrue(outcomes[key])
        self.assertIs(type(outcomes["H6_value_signal"]), bool)
        self.assertFalse(outcomes["H6_value_signal"])

    def test_tracked_inventory_covers_the_clean_clone_evidence_closure(self) -> None:
        inventory_path = evaluation.EVIDENCE_ROOT / "DIGESTS.json"
        inventory_bytes = inventory_path.read_bytes()
        self.assertEqual(evaluation.sha256_bytes(inventory_bytes), INVENTORY_SHA256)
        self.assertEqual(
            (evaluation.EVIDENCE_ROOT / "DIGESTS.sha256").read_text(encoding="ascii"),
            f"{INVENTORY_SHA256}  DIGESTS.json\n",
        )
        inventory = json.loads(inventory_bytes.decode("utf-8"))
        self.assertEqual(len(inventory["files"]), 49)
        self.assertEqual(inventory["counts"]["external_sources"], 29)
        self.assertEqual(inventory["counts"]["repository_licenses"], 4)
        self.assertEqual(len(inventory["third_party_notices"]), 4)
        for relative, record in inventory["files"].items():
            path = evaluation.EVIDENCE_ROOT / relative
            self.assertEqual(evaluation.sha256_file(path), record["sha256"])
            self.assertEqual(path.stat().st_size, record["bytes"])
        distributed = {
            path.relative_to(evaluation.EVIDENCE_ROOT).as_posix()
            for path in evaluation.EVIDENCE_ROOT.rglob("*")
            if path.is_file() and path.name not in {"DIGESTS.json", "DIGESTS.sha256"}
        }
        self.assertEqual(distributed, set(inventory["files"]))

    def test_report_is_english_and_does_not_claim_fresh_confirmation(self) -> None:
        report = (evaluation.ROOT / "EXTERNAL_OOD_EVALUATION_REPORT.md").read_text(
            encoding="utf-8"
        )
        self.assertIsNone(__import__("re").search(r"[\uac00-\ud7a3]", report))
        lowered = report.lower()
        self.assertIn("already-revealed", lowered)
        self.assertIn("not fresh confirmatory evidence", lowered)
        self.assertNotIn("# fresh external", lowered)

    def test_repository_third_party_notice_covers_retained_source_families(self) -> None:
        notice = (evaluation.ROOT / "THIRD_PARTY_NOTICES.md").read_text(
            encoding="utf-8"
        )
        self.assertIsNone(__import__("re").search(r"[\uac00-\ud7a3]", notice))
        manifest, _digest = evaluation._load_content_addressed(
            self._manifest_path(), "premeasurement-manifest"
        )
        for record in manifest["source_selection"]["source_groups"]:
            self.assertIn(record["repository"], notice)
            self.assertIn(record["revision"], notice)
        for record in manifest["source_selection"]["licenses"]:
            self.assertIn(record["license_file_sha256"], notice)
        self.assertIn("Modification notice:", notice)
        self.assertIn("material copied from or derived", notice)
        self.assertIn("W3C ActivityStreams 2.0 examples", notice)
        self.assertIn("CloudEvents 1.0.2 specification examples", notice)
        self.assertIn("Model Context Protocol 2026-07-28 examples", notice)
        self.assertIn("OASIS STIX 2.1 examples", notice)

    def test_repeat_measurement_has_identical_deterministic_outcome(self) -> None:
        manifest_path = self._manifest_path()
        repeat_path = evaluation.EVIDENCE_ROOT / (
            f"measurement-{REPEAT_MEASUREMENT_SHA256}.json"
        )
        verified = evaluation.verify(manifest_path, repeat_path)
        self.assertEqual(verified["deterministic_outcome_sha256"], OUTCOME_SHA256)
        primary, _ = evaluation._load_content_addressed(
            self._measurement_path(MANIFEST_SHA256), "measurement"
        )
        repeat, _ = evaluation._load_content_addressed(repeat_path, "measurement")
        self.assertEqual(
            primary["deterministic_outcome_sha256"],
            repeat["deterministic_outcome_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
