"""Isolated tests for the frozen broad-dialogue evaluation."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import urusilla_general_dialogue_eval as study


EXPECTED_PUBLIC_DIGESTS = {
    "contract": "1cf2d1c9810ac5b94bc0adf15d2251bae30b1b1d8b36fa161a51e1bbe0f5b1c1",
    "evaluator": "5131497df97788f7caba5b716885184e0677f383341ec3547fad4513235def3c",
    "results": "b90b4673e4a5554ab3cead7d5f7489c826cad3866993483dd4cc922dd15469f9",
    "report": "0cd29bbfed502ee49933f45f2d9f5747d68ad9a960242ac187aecbaab1f02cdc",
}


def require_ignored_research_assets() -> None:
    """Skip a clean clone, but leave present-file drift as a hard failure."""

    required = [
        study.WORK_ROOT / "source_freeze.json",
        study.WORK_ROOT / "corpus_manifest.json",
        study.WORK_ROOT / "corpus.jsonl",
        study.WORK_ROOT / "sources" / "taskmaster_1_self_dialogues.json",
        study.WORK_ROOT / "sources" / "schema_guided_dialogue_dev_001.json",
        study.WORK_ROOT / "sources" / "databricks_dolly_15k.jsonl",
        study.WORK_ROOT / "sources" / "openassistant_oasst1_ready_trees.jsonl.gz",
        study.TOKENIZER_ASSET_ROOT / "cl100k_base" / "cl100k_base.tiktoken",
        study.TOKENIZER_ASSET_ROOT / "o200k_base" / "o200k_base.tiktoken",
        study.TOKENIZER_ASSET_ROOT / "qwen2_5_7b_instruct" / "tokenizer.json",
        study.TOKENIZER_ASSET_ROOT / "mistral_7b_instruct_v03" / "tokenizer.json",
    ]
    missing = [str(path.relative_to(study.ROOT)) for path in required if not path.is_file()]
    if missing:
        raise unittest.SkipTest(
            "ignored frozen research assets are unavailable: " + ", ".join(missing)
        )


class PublishedArtifactTests(unittest.TestCase):
    """Dependency-free checks that run even when every ignored cache is absent."""

    def test_published_artifact_digests(self) -> None:
        self.assertEqual(
            study.sha256_file(study.CONTRACT_PATH), EXPECTED_PUBLIC_DIGESTS["contract"]
        )
        self.assertEqual(
            study.sha256_file(study.ROOT / "urusilla_general_dialogue_eval.py"),
            EXPECTED_PUBLIC_DIGESTS["evaluator"],
        )
        self.assertEqual(
            study.sha256_file(study.RESULTS_PATH), EXPECTED_PUBLIC_DIGESTS["results"]
        )
        self.assertEqual(
            study.sha256_file(study.REPORT_PATH), EXPECTED_PUBLIC_DIGESTS["report"]
        )

    def test_published_aggregate_identities(self) -> None:
        contract = json.loads(study.CONTRACT_PATH.read_text(encoding="utf-8"))
        results = json.loads(study.RESULTS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["corpus"]["file_sha256"], study.EXPECTED_CORPUS_SHA256)
        self.assertEqual(
            contract["corpus"]["sequence_sha256"], study.EXPECTED_SEQUENCE_SHA256
        )
        self.assertEqual(results["format"], study.FORMAT)
        self.assertEqual(results["paid_or_provider_calls"], 0)
        self.assertEqual(
            results["inputs"]["evaluator_sha256"],
            EXPECTED_PUBLIC_DIGESTS["evaluator"],
        )
        self.assertEqual(
            results["postmeasurement_reproducibility_amendment"],
            contract["postmeasurement_reproducibility_amendment"],
        )
        self.assertEqual(results["environment"]["zlib_compile_version"], "1.2.12")
        self.assertEqual(results["environment"]["zlib_runtime_version"], "1.2.12")
        self.assertEqual(
            set(results["inputs"]["tokenizer_asset_files"]),
            set(study.EXPECTED_TOKENIZER_FINGERPRINTS),
        )
        lossless = results["lossless_raw_text"]
        self.assertEqual(lossless["candidate_exact_roundtrips"], 14_996)
        self.assertEqual(lossless["selected_exact_roundtrips"], 10_168)
        self.assertEqual(lossless["positive_regret_turn_tokenizer_pairs"], 0)
        self.assertEqual(lossless["post_decode_api_input_saving_pct"], 0.0)
        self.assertEqual(
            {
                key: value["status"]
                for key, value in lossless["hypotheses"].items()
            },
            {
                "h1_lossless_no_regret": "pass",
                "h2_general_compact_value": "fail",
                "h3_repeated_context_value": "fail",
                "h4_end_to_end_gate": "not_evaluated",
            },
        )
        expected_overall = {
            "cl100k_base": (59_518, 59_082, 9, 59_518),
            "o200k_base": (53_646, 53_219, 9, 53_646),
            "qwen2_5_7b_instruct": (56_857, 56_490, 7, 56_857),
            "mistral_7b_instruct_v03": (64_817, 64_390, 9, 64_817),
        }
        observed = {}
        for key, value in lossless["by_tokenizer"].items():
            overall = value["overall"]
            observed[key] = (
                overall["raw_tokens"],
                overall["warm_selected_tokens"],
                overall["compact_selected"],
                overall["cold_total_tokens"],
            )
            self.assertEqual(overall["cold_activated_families"], 0)
            self.assertEqual(overall["post_decode_model_input_saving_pct"], 0.0)
        self.assertEqual(observed, expected_overall)
        oracle = results["sgd_gold_action_state_oracle"]
        self.assertEqual(oracle["targets"], 399)
        self.assertEqual(oracle["model_calls"], 0)
        self.assertIs(oracle["accuracy_measured"], False)
        self.assertEqual(
            oracle["prompt_pair_digest"],
            "ecf3df17b6b9967b1982713aa61ba70b1da0daf55f3dc2d709fb8352438d690c",
        )


class FrozenInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_ignored_research_assets()
        cls.inputs = study.verify_frozen_inputs()

    def test_frozen_identities_and_counts(self) -> None:
        self.assertEqual(len(self.inputs.records), study.EXPECTED_RECORDS)
        self.assertEqual(
            sum(len(record["turns"]) for record in self.inputs.records),
            study.EXPECTED_TURNS,
        )
        self.assertEqual(
            study.sequence_sha256(self.inputs.records), study.EXPECTED_SEQUENCE_SHA256
        )
        self.assertEqual(
            self.inputs.source_freeze["premeasurement_hypotheses"],
            study.EXPECTED_HYPOTHESES,
        )

    def test_source_freeze_predates_measurement_imports(self) -> None:
        for key in ("measurement_started", "project_codec_imported", "tokenizer_loaded"):
            self.assertIs(self.inputs.source_freeze[key], False)
            self.assertIs(self.inputs.manifest[key], False)

    def test_ignored_tokenizer_assets_match_frozen_digests(self) -> None:
        for key, spec in study.TIKTOKEN_ASSET_SPECS.items():
            path = study.TOKENIZER_ASSET_ROOT / key / f"{key}.tiktoken"
            self.assertEqual(path.stat().st_size, spec["bytes"])
            self.assertEqual(study.sha256_file(path), spec["sha256"])
        for key in ("qwen2_5_7b_instruct", "mistral_7b_instruct_v03"):
            path = study.TOKENIZER_ASSET_ROOT / key / "tokenizer.json"
            self.assertEqual(
                study.sha256_file(path), study.EXPECTED_TOKENIZER_FINGERPRINTS[key]
            )

    def test_tokenizer_loading_is_local_and_hash_pinned(self) -> None:
        study._require_zlib_versions()
        with mock.patch(
            "socket.create_connection",
            side_effect=AssertionError("network access attempted"),
        ):
            profiles = study.load_pinned_tokenizers()
        self.assertEqual(
            {profile.key: profile.fingerprint for profile in profiles},
            study.EXPECTED_TOKENIZER_FINGERPRINTS,
        )

    def test_sgd_pairs_are_oracle_labeled_and_nonempty(self) -> None:
        pairs = study.build_sgd_prompt_pairs(self.inputs.records)
        self.assertGreater(len(pairs), 0)
        raw_prompt, oracle_prompt, target = pairs[0]
        self.assertIn("HISTORY:", raw_prompt)
        self.assertIn("ORACLE_STATE:", oracle_prompt)
        self.assertNotEqual(raw_prompt, oracle_prompt)
        self.assertIsInstance(json.loads(target), list)


class CarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Full input verification deliberately occurs before optional codecs load.
        require_ignored_research_assets()
        study.verify_frozen_inputs()
        for distribution in ("Brotli", "zstandard"):
            try:
                study.metadata.version(distribution)
            except study.metadata.PackageNotFoundError as exc:
                raise unittest.SkipTest(
                    f"optional frozen research dependency is unavailable: {distribution}"
                ) from exc
        cls.brotli, cls.zstandard = study._load_strong_compressors()

    def test_every_mode_round_trips_and_reencodes(self) -> None:
        history = b""
        prior = "Earlier turn with repeated context: Seoul to Paris."
        history = study.append_history(history, prior.encode("utf-8"))
        text = "Exact UTF-8 English: café, naïve, résumé — Seoul to Paris."
        for mode in study.MODE_ORDER:
            with self.subTest(mode=mode):
                carrier = study.encode_carrier(
                    mode, text, history, self.brotli, self.zstandard
                )
                recovered = study.decode_carrier(
                    mode, carrier, history, self.brotli, self.zstandard
                )
                self.assertEqual(recovered, text)
                self.assertEqual(
                    study.encode_carrier(
                        mode, recovered, history, self.brotli, self.zstandard
                    ),
                    carrier,
                )

    def test_history_mode_requires_exact_prior_state(self) -> None:
        history = study.append_history(b"", b"shared repeated context")
        carrier = study.encode_carrier(
            "history_deflate64",
            "shared repeated context plus one",
            history,
            self.brotli,
            self.zstandard,
        )
        with self.assertRaises(study.EvaluationError):
            study.decode_carrier(
                "history_deflate64",
                carrier,
                study.append_history(b"", b"different context"),
                self.brotli,
                self.zstandard,
            )

    def test_integrity_mutation_is_rejected(self) -> None:
        carrier = study.encode_carrier(
            "deflate64", "integrity fixture", b"", self.brotli, self.zstandard
        )
        digest_index = len("~U1D") + 8
        replacement = "0" if carrier[digest_index] != "0" else "1"
        mutated = carrier[:digest_index] + replacement + carrier[digest_index + 1 :]
        with self.assertRaises(study.EvaluationError):
            study.decode_carrier(
                "deflate64", mutated, b"", self.brotli, self.zstandard
            )

    def test_raw_wins_token_ties(self) -> None:
        surfaces = {"raw": "x", "raw_checked": "y", "deflate64": "z"}
        counts = {"raw": 1, "raw_checked": 1, "deflate64": 1}
        self.assertEqual(study._select_mode(counts, surfaces), "raw")

    def test_external_profile_preserves_every_field(self) -> None:
        value = study.external_profile_text(
            corpus_id="general-dialogue-test",
            role="user",
            turn_index=7,
            text="verbatim text",
        )
        parsed = json.loads(value)
        self.assertEqual(
            parsed,
            {
                "profile": study.EXTERNAL_PROFILE_ID,
                "role": "user",
                "session": "general-dialogue-test",
                "text": "verbatim text",
                "turn": 7,
            },
        )
        self.assertEqual(study.canonical_bytes(parsed).decode("utf-8"), value)


if __name__ == "__main__":
    unittest.main()
