#!/usr/bin/env python3
"""Positive and negative vectors for the experimental source manifest."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from source_manifest import (
    MAX_INPUT_BYTES,
    ManifestValidationError,
    ManifestVerificationError,
    canonical_payload_bytes,
    derive_source_id,
    load_manifest,
    payload_sha256,
    validate_manifest,
)


HERE = Path(__file__).resolve().parent
SPEC_COMMIT = "0123456789abcdef0123456789abcdef01234567"
IMPLEMENTATION_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"
EXPECTED_PAYLOAD_SHA256 = (
    "defc2efc4f0ac1ecd553fb45df7abe931f989ccfcb922f12ba6c00a600d5fd8c"
)
EXPECTED_SOURCE_ID = "defc2efc4f0ac1ecd553fb45df7abe93"
EXPECTED_CANONICAL = (
    '{"capsuleSha256":"588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27",'
    '"conformanceReportSha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
    '"conformanceReportUrl":"https://github.com/example/urusilla-bridge/blob/'
    + IMPLEMENTATION_COMMIT
    + '/conformance_report.json",'
    '"implementationOrigin":"https://github.com/example/urusilla-bridge/tree/'
    + IMPLEMENTATION_COMMIT
    + '/src",'
    '"languageSpecUri":"https://github.com/jaden3824/urusilla/blob/'
    + SPEC_COMMIT
    + '/urusilla_v0_1_spec.md",'
    '"languageVersion":"0.1.0"}'
)


def positive_manifest() -> dict[str, str]:
    return {
        "languageSpecUri": (
            "https://github.com/jaden3824/urusilla/blob/"
            f"{SPEC_COMMIT}/urusilla_v0_1_spec.md"
        ),
        "languageVersion": "0.1.0",
        "capsuleSha256": (
            "588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27"
        ),
        "implementationOrigin": (
            "https://github.com/example/urusilla-bridge/tree/"
            f"{IMPLEMENTATION_COMMIT}/src"
        ),
        "conformanceReportUrl": (
            "https://github.com/example/urusilla-bridge/blob/"
            f"{IMPLEMENTATION_COMMIT}/conformance_report.json"
        ),
        "conformanceReportSha256": "b" * 64,
    }


class SourceManifestPositiveVectors(unittest.TestCase):
    def test_unsigned_vector_has_deterministic_payload_digest_and_source_id(self) -> None:
        manifest = positive_manifest()
        self.assertEqual(canonical_payload_bytes(manifest), EXPECTED_CANONICAL.encode("utf-8"))
        self.assertEqual(payload_sha256(manifest), EXPECTED_PAYLOAD_SHA256)
        self.assertEqual(derive_source_id(manifest), EXPECTED_SOURCE_ID)

        result = validate_manifest(manifest)
        self.assertTrue(result.structurally_valid)
        self.assertEqual(result.signature_status, "unsigned")
        self.assertFalse(result.effect_authorizing)
        self.assertEqual(result.payload_sha256, EXPECTED_PAYLOAD_SHA256)
        self.assertEqual(result.source_id, EXPECTED_SOURCE_ID)

    def test_member_order_and_optional_jws_do_not_change_payload_hash(self) -> None:
        original = positive_manifest()
        reordered = dict(reversed(tuple(original.items())))
        reordered["sourceManifestJws"] = "eyJhbGciOiJFZERTQSJ9..c2ln"

        self.assertEqual(canonical_payload_bytes(original), canonical_payload_bytes(reordered))
        self.assertEqual(derive_source_id(original), derive_source_id(reordered))
        result = validate_manifest(reordered)
        self.assertEqual(result.signature_status, "unverified")
        self.assertFalse(result.effect_authorizing)

    def test_supplied_verifier_receives_exact_jws_and_canonical_payload(self) -> None:
        manifest = positive_manifest()
        jws = "eyJhbGciOiJFZERTQSJ9..c2ln"
        manifest["sourceManifestJws"] = jws
        calls: list[tuple[str, bytes]] = []

        def verifier(candidate_jws: str, candidate_payload: bytes) -> bool:
            calls.append((candidate_jws, candidate_payload))
            return True

        result = validate_manifest(manifest, jws_verifier=verifier)
        self.assertEqual(calls, [(jws, EXPECTED_CANONICAL.encode("utf-8"))])
        self.assertEqual(result.signature_status, "verified")
        self.assertFalse(result.effect_authorizing)

    def test_false_verifier_result_is_explicitly_invalid(self) -> None:
        manifest = positive_manifest()
        manifest["sourceManifestJws"] = "eyJhbGciOiJFZERTQSJ9.cGF5bG9hZA.c2ln"
        result = validate_manifest(manifest, jws_verifier=lambda _jws, _payload: False)
        self.assertEqual(result.signature_status, "invalid")
        self.assertFalse(result.effect_authorizing)

    def test_cli_validate_and_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(positive_manifest()), encoding="utf-8")
            validate_process = subprocess.run(
                [sys.executable, str(HERE / "source_manifest.py"), "validate", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            id_process = subprocess.run(
                [sys.executable, str(HERE / "source_manifest.py"), "id", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(validate_process.returncode, 0, validate_process.stderr)
        diagnostic = json.loads(validate_process.stdout)
        self.assertEqual(diagnostic["sourceId"], EXPECTED_SOURCE_ID)
        self.assertEqual(diagnostic["signatureStatus"], "unsigned")
        self.assertFalse(diagnostic["effectAuthorizing"])
        self.assertEqual(id_process.returncode, 0, id_process.stderr)
        self.assertEqual(id_process.stdout.strip(), EXPECTED_SOURCE_ID)

    def test_schema_declares_exact_vocabulary(self) -> None:
        schema = json.loads((HERE / "source_manifest.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(positive_manifest()))
        self.assertEqual(
            set(schema["properties"]),
            set(positive_manifest()) | {"sourceManifestJws"},
        )

    def test_schema_patterns_have_exact_end_semantics_matching_validator(self) -> None:
        schema = json.loads((HERE / "source_manifest.schema.json").read_text(encoding="utf-8"))
        manifest = positive_manifest()
        manifest["sourceManifestJws"] = "eyJhbGciOiJFZERTQSJ9..c2ln"

        def schema_pattern_matches(field: str, value: str) -> bool:
            definition = schema["properties"][field]
            if "const" in definition:
                return value == definition["const"]
            if len(value) > definition.get("maxLength", len(value)):
                return False
            patterns = [definition["pattern"]] if "pattern" in definition else [
                branch["pattern"] for branch in definition["anyOf"]
            ]
            return any(re.search(pattern, value) is not None for pattern in patterns)

        for field, value in manifest.items():
            with self.subTest(field=field):
                self.assertTrue(schema_pattern_matches(field, value))
                self.assertFalse(schema_pattern_matches(field, value + "\n"))
                mutated = positive_manifest()
                mutated[field] = value + "\n"
                with self.assertRaises(ManifestValidationError):
                    validate_manifest(mutated)

        self.assertFalse(schema_pattern_matches("sourceManifestJws", "a..b"))


class SourceManifestNegativeVectors(unittest.TestCase):
    def assert_invalid(self, manifest: object, message: str) -> None:
        with self.assertRaisesRegex(ManifestValidationError, message):
            validate_manifest(manifest)

    def test_non_object_missing_unknown_and_non_string_values_are_rejected(self) -> None:
        self.assert_invalid([], "JSON object")

        missing = positive_manifest()
        del missing["capsuleSha256"]
        self.assert_invalid(missing, "missing required field: capsuleSha256")

        unknown = positive_manifest()
        unknown["trackingId"] = "user-123"
        self.assert_invalid(unknown, "unknown field")

        wrong_type = positive_manifest()
        wrong_type["languageVersion"] = 1  # type: ignore[assignment]
        self.assert_invalid(wrong_type, "languageVersion must be a string")

    def test_mutable_or_malformed_normative_urls_are_rejected(self) -> None:
        mutations = (
            (
                "languageSpecUri",
                "https://github.com/jaden3824/urusilla/blob/main/urusilla_v0_1_spec.md",
            ),
            (
                "languageSpecUri",
                "https://github.com/jaden3824/urusilla/blob/"
                f"{SPEC_COMMIT[:-1]}/urusilla_v0_1_spec.md",
            ),
            (
                "languageSpecUri",
                "https://github.com/jaden3824/urusilla/blob/"
                f"{SPEC_COMMIT.upper()}/urusilla_v0_1_spec.md",
            ),
            (
                "languageSpecUri",
                "https://github.com/jaden3824/../blob/"
                f"{SPEC_COMMIT}/urusilla_v0_1_spec.md",
            ),
            (
                "implementationOrigin",
                "https://github.com/example/urusilla-bridge/tree/"
                f"{IMPLEMENTATION_COMMIT}/../secrets",
            ),
            (
                "conformanceReportUrl",
                "https://github.com/example/urusilla-bridge/tree/"
                f"{IMPLEMENTATION_COMMIT}/conformance_report.json",
            ),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                manifest = positive_manifest()
                manifest[field] = value
                self.assert_invalid(manifest, field)

    def test_digest_exact_version_ascii_and_jws_constraints_are_rejected(self) -> None:
        mutations = (
            ("capsuleSha256", "A" * 64),
            ("conformanceReportSha256", "b" * 63),
            ("languageVersion", "0.1.0-experimental"),
            ("languageVersion", "0.1.1"),
            ("languageVersion", "01.0.0-experimental"),
            ("languageVersion", "0.1.0-01"),
            ("languageVersion", "0.1.0-experimental-\u2603"),
            ("sourceManifestJws", "not-a-jws"),
            ("sourceManifestJws", "a..b"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                manifest = positive_manifest()
                manifest[field] = value
                self.assert_invalid(manifest, field)

    def test_non_boolean_or_raising_verifier_fails_closed(self) -> None:
        manifest = positive_manifest()
        manifest["sourceManifestJws"] = "eyJhbGciOiJFZERTQSJ9..c2ln"
        with self.assertRaises(ManifestVerificationError):
            validate_manifest(manifest, jws_verifier=lambda _jws, _payload: "yes")  # type: ignore[arg-type,return-value]

        def raising_verifier(_jws: str, _payload: bytes) -> bool:
            raise RuntimeError("verification backend failure")

        with self.assertRaises(ManifestVerificationError):
            validate_manifest(manifest, jws_verifier=raising_verifier)

    def test_duplicate_json_members_are_rejected_by_loader_and_cli(self) -> None:
        raw = '{"languageVersion":"0.1.0","languageVersion":"1.0.0"}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(ManifestValidationError, "duplicate JSON member"):
                load_manifest(str(path))
            process = subprocess.run(
                [sys.executable, str(HERE / "source_manifest.py"), "validate", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(process.returncode, 2)
        self.assertIn("duplicate JSON member", process.stderr)

    def test_loader_bounds_file_reads_and_normalizes_deep_json_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            oversized = Path(directory) / "oversized.json"
            oversized.write_bytes(b" " * (MAX_INPUT_BYTES + 1))
            with self.assertRaisesRegex(ManifestValidationError, "exceeds"):
                load_manifest(str(oversized))

            deeply_nested = Path(directory) / "deep.json"
            deeply_nested.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")
            try:
                nested_value = load_manifest(str(deeply_nested))
            except ManifestValidationError:
                pass
            else:
                with self.assertRaisesRegex(ManifestValidationError, "JSON object"):
                    validate_manifest(nested_value)
            process = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "source_manifest.py"),
                    "validate",
                    str(deeply_nested),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            ordinary = Path(directory) / "ordinary.json"
            ordinary.write_text("{}", encoding="utf-8")
            with mock.patch("source_manifest.json.loads", side_effect=RecursionError("depth")):
                with self.assertRaisesRegex(ManifestValidationError, "invalid JSON"):
                    load_manifest(str(ordinary))
        self.assertEqual(process.returncode, 2)
        self.assertNotIn("Traceback", process.stderr)

    def test_jws_exclusion_does_not_hide_other_mutations(self) -> None:
        first = positive_manifest()
        first["sourceManifestJws"] = "eyJhbGciOiJFZERTQSJ9..c2ln"
        second = copy.deepcopy(first)
        second["conformanceReportSha256"] = "c" * 64
        self.assertNotEqual(derive_source_id(first), derive_source_id(second))


if __name__ == "__main__":
    unittest.main()
