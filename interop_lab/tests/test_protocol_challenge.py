from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from urusilla import (
    decode_message,
    encode_message,
    normalize_message,
    validate_effect_eligibility,
)


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "interop_lab" / "evidence"
PAYLOAD_PATH = EVIDENCE / "challenge_001.b64url"
EXPECTED_PATH = EVIDENCE / "challenge_001.expected.json"
INSTRUCTIONS_PATH = EVIDENCE / "challenge_001.md"
FRAME_BYTES = 750
FRAME_SHA256 = "490356636a8ebffa6cf4eb27b711459ce849bcbaf87bbf389e57545863054ce7"


def load_frame() -> bytes:
    payload = PAYLOAD_PATH.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", payload):
        raise AssertionError("challenge payload is not unpadded base64url")
    return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))


def load_expected() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


class ProtocolChallengeTests(unittest.TestCase):
    def test_frozen_payload_identity(self) -> None:
        payload = PAYLOAD_PATH.read_text(encoding="ascii").strip()
        self.assertNotIn("=", payload)
        frame = load_frame()
        self.assertEqual(len(frame), FRAME_BYTES)
        self.assertEqual(hashlib.sha256(frame).hexdigest(), FRAME_SHA256)

    def test_decode_matches_expected_canonical_json(self) -> None:
        expected = load_expected()
        self.assertEqual(normalize_message(expected), expected)
        self.assertEqual(decode_message(load_frame()), expected)

    def test_reencoding_is_deterministic(self) -> None:
        frame = load_frame()
        decoded = decode_message(frame)
        self.assertEqual(encode_message(decoded), frame)
        self.assertEqual(encode_message(load_expected()), frame)

    def test_request_grants_no_effect_authority(self) -> None:
        decoded = decode_message(load_frame())
        self.assertEqual(decoded["act"], "REQUEST")
        self.assertNotIn(decoded["act"], {"COMMIT", "RESOLVE", "RETRACT"})

        constraints = {
            item["scope"]: item
            for item in decoded["body"]["constraints"]
        }
        safety = constraints["safety"]
        self.assertEqual(safety["mode"], "hard")
        self.assertEqual(
            safety["condition"],
            {
                "external_effects": False,
                "permission_expansion": False,
                "persistence": False,
                "spending_authority": False,
            },
        )
        self.assertEqual(constraints["evidence"]["mode"], "hard")

        eligible = validate_effect_eligibility(
            decoded,
            authenticated_sender="urusilla.project",
            authorized_schemas={"urn:urusilla:interop-reproduction:1"},
            allowed_effects=(),
            registered_extension_kinds=(),
        )
        self.assertEqual(eligible, decoded)

    def test_documented_cli_decodes_the_frozen_frame(self) -> None:
        instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn("base64.urlsafe_b64decode", instructions)
        self.assertIn("python3 urusilla.py decode", instructions)
        self.assertIn(
            "python3 -m unittest interop_lab.tests.test_protocol_challenge -v",
            instructions,
        )
        self.assertIn("`REQUEST` creates no obligation", instructions)
        self.assertIn("fallback", instructions)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "decoded.json"
            wire_path = Path(temporary_directory) / "challenge_001.wire"
            wire_path.write_bytes(load_frame())
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "urusilla.py"),
                    "decode",
                    str(wire_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                load_expected(),
            )


if __name__ == "__main__":
    unittest.main()
