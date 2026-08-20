#!/usr/bin/env python3
"""Conformance tests for the zero-call public-task preflight."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import competitive_public_task_preflight as preflight


DECLARED_FILES = (
    "competitive_public_task_preflight.py",
    "test_competitive_public_task_preflight.py",
    "COMPETITIVE_PUBLIC_TASK_PREFLIGHT_REPORT.md",
)


class CompetitivePublicTaskPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = preflight.project_root()
        cls.cache = preflight.default_cache_dir()
        cls.assets = cls.root / "work" / "tokenizer_assets"
        required_local_inputs = [
            *(cls.cache / spec.cache_name for spec in preflight.DATASETS),
            cls.assets / "qwen2_5_7b_instruct" / "tokenizer.json",
            cls.assets / "mistral_7b_instruct_v03" / "tokenizer.json",
        ]
        missing = [path for path in required_local_inputs if not path.is_file()]
        if missing:
            raise unittest.SkipTest(
                "local-only public-task preflight inputs are absent; "
                "run the documented acquisition step to enable this suite"
            )
        cls.datasets = {}
        for spec in preflight.DATASETS:
            path = preflight.obtain_dataset(spec, cls.cache, offline=True)
            cls.datasets[spec.key] = preflight.load_dataset(spec, path)
        cls.snapshot, cls.records = preflight.build_snapshot(
            cls.cache,
            cls.assets,
            offline=True,
        )

    def test_source_artifacts_are_exact(self) -> None:
        expected = {
            "hotpotqa": (
                "eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284",
                100,
                7,
            ),
            "wikihop": (
                "724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39",
                100,
                3,
            ),
        }
        for key, (digest, count, field_count) in expected.items():
            row = self.snapshot["sources"][key]
            self.assertEqual(row["sha256"], digest)
            self.assertEqual(row["records"], count)
            self.assertEqual(len(row["required_fields"]), field_count)

    def test_acquisition_is_allowlisted_and_offline_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "blocked.jsonl"
            with self.assertRaisesRegex(RuntimeError, "not allowlisted"):
                preflight._download_exact("https://example.invalid/data.jsonl", target)
            with self.assertRaisesRegex(RuntimeError, "offline mode"):
                preflight.obtain_dataset(
                    preflight.DATASETS[0], Path(directory), offline=True
                )

    def test_digest_drift_fails_closed(self) -> None:
        spec = preflight.DATASET_BY_KEY["hotpotqa"]
        source = self.cache / spec.cache_name
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / spec.cache_name
            changed.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaisesRegex(RuntimeError, "changed after acquisition"):
                preflight.load_dataset(spec, changed)

    def test_field_drift_fails_closed(self) -> None:
        spec = preflight.DATASET_BY_KEY["wikihop"]
        path = self.cache / spec.cache_name
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[0]["unexpected"] = True
        with self.assertRaisesRegex(RuntimeError, "field drift"):
            preflight.validate_rows(spec, rows)

    def test_splits_are_locked_and_cover_every_context_once(self) -> None:
        self.assertEqual(
            self.snapshot["split_digests"], preflight.EXPECTED_SPLIT_DIGESTS
        )
        for dataset, items in self.datasets.items():
            for item in items:
                for seed in preflight.DATA_SEEDS:
                    value = preflight.alternating_split(item, seed)
                    self.assertEqual(
                        sorted(value.owner_a + value.owner_b),
                        list(range(len(item.contexts))),
                    )
                    self.assertFalse(set(value.owner_a) & set(value.owner_b))

    def test_forced_distribution_is_strict(self) -> None:
        hotpot = self.datasets["hotpotqa"]
        eligible = [item for item in hotpot if item.forced_eligible]
        excluded = [item for item in hotpot if not item.forced_eligible]
        self.assertEqual(len(eligible), 99)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].source_index, 13)
        self.assertEqual(
            excluded[0].forced_reason, "gold_paragraph_match_is_not_unique"
        )
        for item in eligible:
            for seed in preflight.DATA_SEEDS:
                value = preflight.forced_split(item, seed)
                support = set(item.support_indices)
                self.assertTrue(set(value.owner_a) & support)
                self.assertTrue(set(value.owner_b) & support)
        self.assertEqual(
            self.snapshot["forced_distribution"]["hotpotqa"]["20240826"],
            {"eligible": 99, "naturally_distributed": 55, "forced_distributed": 99},
        )
        self.assertEqual(
            self.snapshot["forced_distribution"]["hotpotqa"]["20250424"],
            {"eligible": 99, "naturally_distributed": 64, "forced_distributed": 99},
        )
        self.assertEqual(
            self.snapshot["forced_distribution"]["hotpotqa"]["20260820"],
            {"eligible": 99, "naturally_distributed": 61, "forced_distributed": 99},
        )

    def test_missing_wikihop_gold_support_blocks_forced_stratum(self) -> None:
        items = self.datasets["wikihop"]
        self.assertEqual(sum(item.forced_eligible for item in items), 0)
        self.assertEqual(
            {item.forced_reason for item in items},
            {"gold_support_annotations_absent"},
        )
        with self.assertRaisesRegex(RuntimeError, "not forced-split eligible"):
            preflight.forced_split(items[0], preflight.DATA_SEEDS[0])

    def test_answer_field_never_changes_a_prompt(self) -> None:
        item = self.datasets["hotpotqa"][0]
        split = preflight.alternating_split(item, preflight.DATA_SEEDS[0])
        changed = replace(item, answer="answer-field-mutation")
        for arm in preflight.ARMS:
            for agent in preflight.AGENTS:
                self.assertEqual(
                    preflight.render_prompt(item, split, agent, arm),
                    preflight.render_prompt(changed, split, agent, arm),
                )

    def test_question_or_evidence_change_changes_a_prompt(self) -> None:
        item = self.datasets["wikihop"][0]
        split = preflight.alternating_split(item, preflight.DATA_SEEDS[0])
        changed_question = replace(item, question=item.question + " changed")
        contexts = list(item.contexts)
        contexts[split.owner_a[0]] += " changed"
        changed_evidence = replace(item, contexts=tuple(contexts))
        original = preflight.render_prompt(item, split, "A", "json")
        self.assertNotEqual(
            original, preflight.render_prompt(changed_question, split, "A", "json")
        )
        self.assertNotEqual(
            original, preflight.render_prompt(changed_evidence, split, "A", "json")
        )

    def test_prompt_locks_are_complete(self) -> None:
        self.assertEqual(len(self.records), 5382)
        self.assertEqual(self.snapshot["unique_prompt_text_sha256"], 5358)
        self.assertEqual(self.snapshot["duplicate_prompt_records"], 24)
        self.assertEqual(
            self.snapshot["prompt_groups"],
            preflight.EXPECTED_PROMPT_GROUP_DIGESTS,
        )
        self.assertEqual(
            self.snapshot["prompt_set_sha256"],
            preflight.EXPECTED_PROMPT_SET_SHA256,
        )
        self.assertEqual(
            self.snapshot["prompt_contract_sha256"],
            {
                "adaptive": "f83489a3dca68e1eb4e94d8d20207c3e6fd8bf0d44d496f1fa4ea3cc8581ef74",
                "cte": "51d1d56aad635ff10c5883cd6f09691a1c45af3a80c9729a6439d4145443deac",
                "json": "f330179b6cb10cff5c44992405d208d1a68664a45cb78a34e762db2dbc7da1a5",
            },
        )

    def test_four_tokenizers_and_exact_totals(self) -> None:
        observed = {
            row["key"]: row["fingerprint"] for row in self.snapshot["tokenizers"]
        }
        self.assertEqual(observed, preflight.EXPECTED_TOKENIZER_FINGERPRINTS)
        hotpot = self.snapshot["prompt_token_metrics"]["hotpotqa"]["alternating"]
        wiki = self.snapshot["prompt_token_metrics"]["wikihop"]["alternating"]
        self.assertEqual(
            hotpot["cte"]["tokenizers"]["cl100k_base"]["total"], 555223
        )
        self.assertEqual(
            hotpot["json"]["tokenizers"]["o200k_base"]["total"], 547366
        )
        self.assertEqual(
            hotpot["adaptive"]["tokenizers"]["qwen2_5_7b_instruct"]["total"],
            632554,
        )
        self.assertEqual(
            wiki["adaptive"]["tokenizers"]["mistral_7b_instruct_v03"]["total"],
            981084,
        )

    def test_current_artifact_lock_and_conservative_cold_charge(self) -> None:
        artifacts = self.snapshot["current_adaptive_artifacts"]
        self.assertEqual(
            artifacts["implementation_sha256"],
            preflight.EXPECTED_CURRENT_IMPLEMENTATION_SHA256,
        )
        self.assertEqual(
            artifacts["profile_sha256"], preflight.EXPECTED_CURRENT_PROFILE_SHA256
        )
        expected_tokens = {
            "cl100k_base": 10170,
            "o200k_base": 9661,
            "qwen2_5_7b_instruct": 10348,
            "mistral_7b_instruct_v03": 11750,
        }
        for key, tokens in expected_tokens.items():
            row = artifacts["tokenizers"][key]
            self.assertEqual(row["conservative_all_artifacts_tokens"], tokens)
            self.assertEqual(row["conservative_all_artifacts_bytes"], 16005)

    def test_a1_selection_and_call_cost_reconcile(self) -> None:
        self.assertEqual(
            self.snapshot["a1_selection"]["sha256"],
            preflight.EXPECTED_A1_ITEM_SET_SHA256,
        )
        cost = self.snapshot["cost_preflight"]
        self.assertEqual(cost["items"], 40)
        self.assertEqual(cost["episodes"], 360)
        self.assertEqual(cost["base_calls"], 2880)
        self.assertEqual(cost["paid_calls"], 1920)
        self.assertEqual(cost["local_calls"], 960)
        self.assertEqual(cost["twenty_percent_call_reserve"], 576)
        self.assertEqual(cost["twenty_percent_paid_call_reserve"], 384)
        upper = cost["scenarios"]["conservative_upper"]
        self.assertEqual(upper["paid_cost_usd"], 4.492993)
        self.assertEqual(
            upper["with_20_percent_retry_and_price_reserve_usd"], 5.391592
        )

    def test_zero_call_claim_boundary_and_snapshot(self) -> None:
        self.assertEqual(self.snapshot["model_calls"], 0)
        self.assertEqual(self.snapshot["paid_calls"], 0)
        self.assertIs(self.snapshot["task_success_measured"], False)
        self.assertEqual(
            self.snapshot["snapshot_sha256"], preflight.EXPECTED_SNAPSHOT_SHA256
        )

    def test_declared_files_are_ascii_and_retired_label_is_absent(self) -> None:
        retired = bytes((115, 101, 109, 97))
        for filename in DECLARED_FILES:
            path = self.root / filename
            self.assertTrue(path.is_file(), filename)
            data = path.read_bytes()
            self.assertTrue(data.isascii(), filename)
            self.assertNotIn(retired, data.lower(), filename)

    def test_report_preserves_the_claim_boundary(self) -> None:
        report = (self.root / DECLARED_FILES[-1]).read_text(encoding="ascii")
        self.assertIn("No task success was measured", report)
        self.assertIn("CC BY-SA 4.0", report)
        self.assertIn("CC BY-SA 3.0", report)
        self.assertIn(preflight.EXPECTED_SNAPSHOT_SHA256, report)


if __name__ == "__main__":
    unittest.main()
