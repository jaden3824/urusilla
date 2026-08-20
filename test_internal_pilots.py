import hashlib
import json
from pathlib import Path
import unittest

import urusilla as v1
import urusilla_wire_v02 as v2


ROOT = Path(__file__).resolve().parent
PILOTS = ROOT / "internal_pilots"


class InternalPilotTests(unittest.TestCase):
    def _message(self, filename: str) -> dict:
        return json.loads((PILOTS / filename).read_text(encoding="utf-8"))

    def _assert_frame(self, filename: str, codec, expected_sha256: str) -> dict:
        source = self._message(filename)
        frame = codec.encode_message(source)
        self.assertEqual(hashlib.sha256(frame).hexdigest(), expected_sha256)
        decoded = codec.decode_message(frame)
        self.assertEqual(codec.encode_message(decoded), frame)
        self.assertIn("\n[ASSERT]", v1.translate_message(decoded, "en"))
        return decoded

    def test_landscape_bridge_message_is_reproducible_and_internal(self):
        message = self._assert_frame(
            "global_landscape_message.json",
            v1,
            "ebd30eeca09271dce9b262ee261dd4d9dc9ace31d5cd428bc02d34c5f90ad9ec",
        )
        self.assertIs(message["meta"]["external_adopter_claim"], False)
        self.assertEqual(message["meta"]["evidence_scope"], "internal-pilot-only")

    def test_bootstrap_bridge_message_is_reproducible_and_internal(self):
        message = self._assert_frame(
            "bootstrap_adoption_message.json",
            v1,
            "14cd50f65b48209063e73449b9cb6751fa67343b4fe405cf08ff2fbbcdb5cfab",
        )
        self.assertIs(message["meta"]["provenance"]["external_adopter"], False)
        self.assertEqual(message["meta"]["provenance"]["implementation_mode"], "bridge")

    def test_wire_v02_bridge_message_is_reproducible_and_internal(self):
        message = self._assert_frame(
            "wire_v02_message.json",
            v2,
            "dd5c185c35a3a838ca644dc85801d0688f1debfc51997756d767f7dc71c55a04",
        )
        self.assertIs(message["meta"]["external_adoption"], False)
        self.assertEqual(message["meta"]["classification"], "internal-bridge-pilot")


if __name__ == "__main__":
    unittest.main()
