from __future__ import annotations

import copy
import unittest

from interop_lab.a2a_v1_language_probe import (
    A2ALanguageProbeError,
    build_manifest,
    build_message,
    check_artifacts,
    load_probe,
    sha256_canonical,
    verify_fixture,
)


class A2AV1LanguageProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_bytes, cls.probe = load_probe()
        cls.message = build_message(cls.source_bytes, cls.probe)
        cls.manifest = build_manifest(cls.source_bytes, cls.probe, cls.message)

    def test_committed_fixture_is_current_and_deterministic(self) -> None:
        check_artifacts()
        self.assertEqual(
            self.message,
            build_message(self.source_bytes, self.probe),
        )

    def test_standard_v1_data_part_preserves_probe_json_value(self) -> None:
        self.assertEqual(set(self.message), {"messageId", "role", "parts"})
        part = self.message["parts"][0]
        self.assertEqual(set(part), {"data", "mediaType"})
        self.assertEqual(part["mediaType"], "application/json")
        self.assertEqual(part["data"]["probe"], self.probe)
        self.assertEqual(
            part["data"]["probeCanonicalSha256"],
            sha256_canonical(self.probe),
        )
        self.assertFalse(
            self.manifest["transport_semantics"][
                "pretty_printed_source_bytes_carried"
            ]
        )
        self.assertFalse(
            self.manifest["transport_semantics"]["a2a_extension_claimed"]
        )

    def test_probe_tamper_fails_closed(self) -> None:
        changed = copy.deepcopy(self.message)
        changed["parts"][0]["data"]["probe"]["probe_id"] = "tampered"
        with self.assertRaises(A2ALanguageProbeError):
            verify_fixture(changed, self.manifest, self.source_bytes, self.probe)

    def test_source_digest_tamper_fails_closed(self) -> None:
        changed = copy.deepcopy(self.message)
        changed["parts"][0]["data"]["probeSourceSha256"] = "sha256:" + "0" * 64
        with self.assertRaises(A2ALanguageProbeError):
            verify_fixture(changed, self.manifest, self.source_bytes, self.probe)

    def test_wrong_part_union_fails_closed(self) -> None:
        changed = copy.deepcopy(self.message)
        changed["parts"][0]["text"] = "shadow content"
        with self.assertRaises(A2ALanguageProbeError):
            verify_fixture(changed, self.manifest, self.source_bytes, self.probe)

    def test_manifest_tamper_fails_closed(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["fixture"]["part_data_canonical_sha256"] = "sha256:" + "f" * 64
        with self.assertRaises(A2ALanguageProbeError):
            verify_fixture(self.message, changed, self.source_bytes, self.probe)


if __name__ == "__main__":
    unittest.main()
