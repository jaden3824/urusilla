from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest import mock

import external_ood_v08_confirmatory as subject


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "external_ood_v08_confirmatory"
MANIFEST_SHA256 = "834047439e8bd13b244c913343c31581c2fd242b331fd259d749fb707f54ff64"
CORPUS_SHA256 = "6a00c011af8a2b264ec4e79bca84106b143439b3df4ba4e969e48e199fb9d978"
PRIMARY_SHA256 = "0f6dd299203021e60186613caede5dfeeeb8d6fad561f0dd1203d9be6563a44d"
REPEAT_SHA256 = "aae93e4d9023e83b220fe6fee481df3f032bd48891065b410ef3f226f016f619"
EVALUATOR_SHA256 = "fcb03b568fd8babe3132a6c2556158a8eab7ba87691e10738b20a867faef5d6a"
INVENTORY_SHA256 = "19cca24a3e0663ba8fa8b9a56c0614c17c8e7ca7470428ba49371ffaadb27ed0"
SEQUENCE_SHA256 = "f73e8f520a2b1720dcbf8ab74beb928fe356661e3d6a84259b0ff0c64c6d782b"
SELECTION_CONTRACT_SHA256 = "fcb90039b2a7e193e3b274b6a4cefcb7cf851b116e397bcb721e0b268c5c36b0"
DETERMINISTIC_OUTCOME_SHA256 = "3bbbd740a5a22e00a794052efc224ca98f2ce0240a49abbc93c213606918247f"
MANIFEST_PATH = EVIDENCE / f"premeasurement-manifest-{MANIFEST_SHA256}.json"
CORPUS_PATH = EVIDENCE / f"corpus-{CORPUS_SHA256}.json"
PRIMARY_PATH = EVIDENCE / f"measurement-{PRIMARY_SHA256}.json"
REPEAT_PATH = EVIDENCE / f"measurement-{REPEAT_SHA256}.json"
REPORT_PATH = ROOT / "EXTERNAL_OOD_V08_CONFIRMATORY_REPORT.md"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class ExternalOodV08ConfirmatoryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.primary = json.loads(PRIMARY_PATH.read_text(encoding="utf-8"))
        cls.repeat = json.loads(REPEAT_PATH.read_text(encoding="utf-8"))
        cls.corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        cls.inventory = json.loads((EVIDENCE / "DIGESTS.json").read_text(encoding="utf-8"))

    def test_primary_artifacts_are_exactly_content_addressed(self) -> None:
        expected = {
            MANIFEST_PATH: MANIFEST_SHA256,
            CORPUS_PATH: CORPUS_SHA256,
            PRIMARY_PATH: PRIMARY_SHA256,
            REPEAT_PATH: REPEAT_SHA256,
            EVIDENCE / f"evaluator-{EVALUATOR_SHA256}.py": EVALUATOR_SHA256,
        }
        for path, digest in expected.items():
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertEqual(file_sha256(path), digest)
                self.assertIn(digest, path.name)
        self.assertEqual(self.manifest["corpus"]["corpus_file_sha256"], CORPUS_SHA256)
        self.assertEqual(self.manifest["corpus"]["message_sequence_sha256"], SEQUENCE_SHA256)
        for measurement in (self.primary, self.repeat):
            self.assertEqual(measurement["premeasurement_manifest_sha256"], MANIFEST_SHA256)

    def test_detached_inventory_covers_every_distributed_evidence_file(self) -> None:
        inventory_path = EVIDENCE / "DIGESTS.json"
        self.assertEqual(file_sha256(inventory_path), INVENTORY_SHA256)
        self.assertEqual(
            (EVIDENCE / "DIGESTS.sha256").read_text(encoding="ascii"),
            f"{INVENTORY_SHA256}  DIGESTS.json\n",
        )
        self.assertEqual(
            self.inventory["format"],
            "external-ood-v08-post-cutover-evidence-inventory-v1",
        )
        self.assertEqual(self.inventory["source_and_license_files"], 38)
        self.assertEqual(self.inventory["candidate_source_files"], 11)
        self.assertEqual(len(self.inventory["files"]), 54)
        self.assertEqual(
            self.inventory["deterministic_outcome_sha256"],
            DETERMINISTIC_OUTCOME_SHA256,
        )
        for relative, record in self.inventory["files"].items():
            path = EVIDENCE / relative
            with self.subTest(relative=relative):
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(file_sha256(path), record["sha256"])

    def test_all_frozen_sources_are_archived_by_exact_digest(self) -> None:
        candidate_root = EVIDENCE / "candidate_sources"
        expected_candidates = self.manifest["frozen_candidate"]["source_sha256"]
        self.assertEqual(len(expected_candidates), 11)
        for name, digest in expected_candidates.items():
            with self.subTest(candidate=name):
                self.assertEqual(file_sha256(candidate_root / name), digest)

        source_records = self.manifest["source_selection"]["source_groups"]
        license_records = self.manifest["source_selection"]["licenses"]
        self.assertEqual(len(source_records), 34)
        self.assertEqual(len(license_records), 4)
        for record, digest_key in (
            *((record, "source_file_sha256") for record in source_records),
            *((record, "license_file_sha256") for record in license_records),
        ):
            relative = Path(record["cache_file"]).relative_to(subject.EVIDENCE_CACHE_PREFIX)
            with self.subTest(cache_file=str(relative)):
                self.assertEqual(file_sha256(EVIDENCE / relative), record[digest_key])

    def test_tracked_package_verifies_offline_for_both_runs(self) -> None:
        with mock.patch.object(subject, "_fetch", side_effect=AssertionError("network access attempted")):
            for measurement_path, digest in (
                (PRIMARY_PATH, PRIMARY_SHA256),
                (REPEAT_PATH, REPEAT_SHA256),
            ):
                result = subject.verify(MANIFEST_PATH, measurement_path)
                self.assertTrue(result["manifest_verified"])
                self.assertTrue(result["measurement_verified"])
                self.assertEqual(result["manifest_sha256"], MANIFEST_SHA256)
                self.assertEqual(result["measurement_sha256"], digest)
                self.assertEqual(result["message_count"], 42)
                self.assertEqual(result["frozen_candidate_source"], "current")
                self.assertEqual(
                    result["deterministic_outcome_sha256"],
                    DETERMINISTIC_OUTCOME_SHA256,
                )

    def test_candidate_source_mismatch_fails_closed(self) -> None:
        observed = subject._candidate_source_digests()
        changed = dict(observed)
        first = next(iter(changed))
        changed[first] = "0" * 64
        with mock.patch.object(subject, "_candidate_source_digests", return_value=changed):
            with self.assertRaisesRegex(RuntimeError, "changed after freeze"):
                subject._verify_frozen_inputs(self.manifest)

    def test_freeze_precedes_both_measurements_and_reuses_exact_archive_offline(self) -> None:
        self.assertEqual(
            self.manifest["stage"],
            "post_cutover_reconfirmation_frozen_before_v08_or_tokenizer_import_and_before_token_measurement",
        )
        self.assertEqual(
            self.manifest["external_data_role"],
            "post_cutover_reconfirmation_only_no_training_no_tuning",
        )
        acquisition = self.manifest["source_selection"]["acquisition"]
        self.assertEqual(acquisition["mode"], "archived_exact_bytes")
        self.assertFalse(acquisition["network_used"])
        frozen = datetime.fromisoformat(self.manifest["frozen_at_utc"])
        for expected_label, measurement in (
            ("primary", self.primary),
            ("repeat", self.repeat),
        ):
            self.assertEqual(measurement["run_label"], expected_label)
            self.assertLess(frozen, datetime.fromisoformat(measurement["measured_at_utc"]))
            self.assertTrue(measurement["candidate_sources_verified_unchanged_before_import"])
            self.assertFalse(measurement["external_corpus_used_for_training_or_tuning"])
            self.assertFalse(measurement["candidate_or_threshold_modified_after_freeze"])
        self.assertEqual(
            self.manifest["frozen_candidate"]["selection_contract_sha256"],
            SELECTION_CONTRACT_SHA256,
        )

    def test_corpus_and_partition_counts_are_exact(self) -> None:
        expected = {
            "all": 42,
            "openapi-3.0-official-pass-examples": 6,
            "asyncapi-3.1-official-examples": 23,
            "w3c-wot-thing-description-1.1-validation-examples": 6,
            "opentelemetry-protocol-json-examples": 7,
        }
        manifest_counts = {
            key: value["message_count"]
            for key, value in self.manifest["corpus"]["partitions"].items()
        }
        self.assertEqual(manifest_counts, expected)
        self.assertEqual(len(self.corpus), 42)
        for measurement in (self.primary, self.repeat):
            self.assertEqual(measurement["corpus"]["partitions"], expected)
            self.assertEqual(measurement["corpus"]["message_count"], 42)

    def test_exactness_and_determinism_are_504_of_504_in_both_runs(self) -> None:
        for measurement in (self.primary, self.repeat):
            exactness = measurement["exactness"]
            self.assertEqual(exactness["total_trials"], 504)
            self.assertEqual(exactness["total_exact"], 504)
            self.assertEqual(exactness["total_deterministic"], 504)
            rows = list(exactness["direct_payloads"].values())
            rows.extend(exactness["selected_records"]["bound"].values())
            rows.extend(exactness["selected_records"]["standalone"].values())
            self.assertEqual(len(rows), 12)
            self.assertTrue(
                all(row == {"deterministic": 42, "exact": 42, "trials": 42} for row in rows)
            )

    def test_two_runs_have_identical_claim_bearing_outcomes(self) -> None:
        self.assertNotEqual(PRIMARY_SHA256, REPEAT_SHA256)
        self.assertEqual(
            self.primary["deterministic_outcome_sha256"],
            DETERMINISTIC_OUTCOME_SHA256,
        )
        self.assertEqual(
            self.repeat["deterministic_outcome_sha256"],
            DETERMINISTIC_OUTCOME_SHA256,
        )
        self.assertEqual(
            subject._deterministic_outcome(self.primary),
            subject._deterministic_outcome(self.repeat),
        )

    def test_integrity_trials_reject_840_of_840_per_contract_in_both_runs(self) -> None:
        expected = {
            "bound": {"attempted": 840, "rejected": 840},
            "standalone": {"attempted": 840, "rejected": 840},
        }
        for measurement in (self.primary, self.repeat):
            self.assertEqual(measurement["integrity_totals"], expected)

    def test_bound_and_standalone_have_zero_strict_compact_wins(self) -> None:
        for measurement in (self.primary, self.repeat):
            self.assertEqual(
                measurement["compact_strict_wins"],
                {"bound": 0, "standalone": 0},
            )
            warm_standalone = {
                key: profile["standalone"]["mode_counts_warm"]
                for key, profile in measurement["profiles"].items()
            }
            self.assertEqual(warm_standalone["o200k_base"], {"terse": 42})
            self.assertEqual(warm_standalone["mistral_7b_instruct_v03"], {"terse": 42})
            self.assertEqual(warm_standalone["cl100k_base"], {"terse": 42})
            self.assertEqual(warm_standalone["qwen2_5_7b_instruct"], {"terse": 42})
            for profile in measurement["profiles"].values():
                self.assertEqual(profile["bound"]["mode_counts_warm"], {"terse": 42})
                self.assertEqual(profile["bound"]["mode_counts_cold"], {"terse": 42})
                self.assertEqual(profile["standalone"]["mode_counts_cold"], {"terse": 42})

    def test_contract_specific_metadata_components_sum_exactly(self) -> None:
        expected_standalone_payload = {
            "cl100k_base": 180_044,
            "o200k_base": 180_044,
            "qwen2_5_7b_instruct": 180_044,
            "mistral_7b_instruct_v03": 180_044,
        }
        for key, profile in self.primary["profiles"].items():
            bound = profile["metadata_bytes"]["bound"]
            self.assertEqual(bound["separate_metadata_bytes"], 1_050)
            self.assertEqual(bound["receiver_payload_bytes"], 180_044)
            self.assertEqual(bound["complete_record_bytes"], 181_094)
            self.assertTrue(bound["component_sum_matches_complete"])
            standalone = profile["metadata_bytes"]["standalone"]
            self.assertEqual(standalone["inline_metadata_bytes"], 1_764)
            self.assertEqual(standalone["payload_bytes"], expected_standalone_payload[key])
            self.assertEqual(
                standalone["payload_bytes"] + standalone["inline_metadata_bytes"],
                standalone["complete_receiver_text_bytes"],
            )
            self.assertTrue(standalone["component_sum_matches_complete"])

    def test_every_bound_cold_outcome_is_a_tie(self) -> None:
        for profile in self.primary["profiles"].values():
            raw = profile["raw_receiver_tokens"]["best_plain_per_message"]
            bound = profile["bound"]
            self.assertEqual(bound["aggregate_outcome"], "tie")
            self.assertEqual(bound["cold_delta_vs_raw_best_per_message"], 0)
            self.assertEqual(bound["cold_positive_regret_tokens"], 0)
            self.assertEqual(bound["cold_total_tokens"], raw)
        for partition in self.primary["partitions"].values():
            for values in partition["tokenizers"].values():
                self.assertEqual(values["bound_cold_delta_tokens"], 0)
                self.assertEqual(values["bound_positive_regret_tokens"], 0)

    def test_standalone_cold_overhead_is_2_24_to_3_00_percent(self) -> None:
        expected = {
            "cl100k_base": (1_085, 2.325681092319894),
            "o200k_base": (1_045, 2.239989711052045),
            "qwen2_5_7b_instruct": (1_527, 3.0026546062334085),
            "mistral_7b_instruct_v03": (1_592, 2.4633285882280127),
        }
        observed = []
        for key, profile in self.primary["profiles"].items():
            raw = profile["raw_receiver_tokens"]["best_plain_per_message"]
            standalone = profile["standalone"]
            delta = standalone["unmatched_delta_vs_raw_best_per_message"]
            percentage = delta * 100 / raw
            self.assertEqual(delta, expected[key][0])
            self.assertAlmostEqual(percentage, expected[key][1], places=12)
            self.assertEqual(standalone["matched_plain_delta_tokens"], 0)
            observed.append(percentage)
        self.assertEqual(round(min(observed), 2), 2.24)
        self.assertEqual(round(max(observed), 2), 3.00)

    def test_report_is_english_only_and_makes_no_positive_sota_claim(self) -> None:
        report = REPORT_PATH.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[\uac00-\ud7a3]", report))
        for digest in (
            MANIFEST_SHA256,
            CORPUS_SHA256,
            PRIMARY_SHA256,
            REPEAT_SHA256,
            EVALUATOR_SHA256,
            INVENTORY_SHA256,
            DETERMINISTIC_OUTCOME_SHA256,
        ):
            self.assertIn(digest, report)
        self.assertIn("504/504 exactness trials", report)
        self.assertIn("0/168", report)
        self.assertIn("0/168 bound and 0/168 standalone", report)
        self.assertIn("2.24% to 3.00%", report)
        self.assertIn("does not demonstrate", report)
        self.assertIn("or a state-of-the-art result", report)
        lower = report.lower()
        for prohibited in (
            "we achieve state of the art",
            "is state of the art",
            "state-of-the-art performance",
            "sets a world record",
            "world-leading",
            "best-in-class",
        ):
            self.assertNotIn(prohibited, lower)


if __name__ == "__main__":
    unittest.main()
