#!/usr/bin/env python3
"""Tests for the private experimental A2A v1 binding adapter."""

from __future__ import annotations

import base64
import copy
import unittest
from unittest.mock import patch

from urusilla_a2a_adapter import (
    A2A_VERSION,
    A2AAdapterError,
    EXTENSION_URI,
    agent_extension,
    pack_part,
    service_headers,
    unpack_part,
    unwrap_a2a_message,
    wrap_a2a_message,
)
from urusilla import demo_message, normalize_message


SOURCE_ID = "0123456789abcdef0123456789abcdef"
OTHER_SOURCE_ID = "fedcba9876543210fedcba9876543210"
OTHER_EXTENSION = "https://example.test/extensions/trace/v1"
REPLY_ID = "018f4f2e-1d33-7b62-8af8-5a09497d34c2"


def effectful_message(act: str = "COMMIT") -> dict:
    message = demo_message()
    message["act"] = act
    message["reply_to"] = REPLY_ID
    if act == "COMMIT":
        message["body"] = {
            "kind": "commitment",
            "debtor": message["sender"],
            "creditors": message["recipients"],
            "goal": message["body"],
            "expiry_ms": message["expires_ms"],
        }
    elif act == "RESOLVE":
        message["body"] = {
            "kind": "resolution",
            "target": {"kind": "ref", "uri": f"urn:message:{REPLY_ID}"},
            "status": "completed",
        }
    elif act == "RETRACT":
        message["body"] = {"kind": "ref", "uri": f"urn:message:{REPLY_ID}"}
    return message


def unwrap_defaults(wrapper: dict, **overrides: object) -> dict:
    arguments: dict[str, object] = {
        "expected_source_id": SOURCE_ID,
        "activated_extensions": [EXTENSION_URI],
        "a2a_version": A2A_VERSION,
    }
    arguments.update(overrides)
    return unwrap_a2a_message(wrapper, **arguments)


class A2AAdapterTests(unittest.TestCase):
    def test_part_round_trip(self) -> None:
        source = demo_message()
        part = pack_part(source, capsule_digest="sha256:capsule")
        decoded = unpack_part(part, expected_capsule_digest="sha256:capsule")
        self.assertEqual(decoded, normalize_message(source))

    def test_message_round_trip_checks_complete_boundary(self) -> None:
        source = demo_message()
        wrapped = wrap_a2a_message(
            source,
            source_id=SOURCE_ID,
            authenticated_sender=source["sender"],
            context_id="context-1",
            task_id="task-1",
            reference_task_ids=["task-0"],
        )
        decoded = unwrap_defaults(
            wrapped,
            authenticated_sender=source["sender"],
            expected_role="ROLE_USER",
            expected_context_id="context-1",
            expected_task_id="task-1",
        )
        self.assertEqual(decoded, normalize_message(source))

    def test_source_id_is_required_at_message_not_part_metadata(self) -> None:
        wrapped = wrap_a2a_message(demo_message(), source_id=SOURCE_ID)
        self.assertEqual(
            wrapped["metadata"][EXTENSION_URI]["source_id"], SOURCE_ID
        )
        self.assertNotIn("metadata", wrapped["parts"][0])

        missing = copy.deepcopy(wrapped)
        del missing["metadata"]
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(missing)

    def test_source_id_format_and_session_pin_are_enforced(self) -> None:
        with self.assertRaises(A2AAdapterError):
            wrap_a2a_message(demo_message(), source_id=SOURCE_ID.upper())

        wrapped = wrap_a2a_message(demo_message(), source_id=SOURCE_ID)
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped, expected_source_id=OTHER_SOURCE_ID)

        malformed = copy.deepcopy(wrapped)
        malformed["metadata"][EXTENSION_URI]["source_id"] = "abc"
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(malformed)

    def test_service_headers_activate_version_and_multiple_extensions(self) -> None:
        headers = service_headers(additional_extensions=[OTHER_EXTENSION])
        self.assertEqual(headers["A2A-Version"], "1.0")
        self.assertEqual(
            headers["A2A-Extensions"], f"{EXTENSION_URI},{OTHER_EXTENSION}"
        )

    def test_multiple_activated_and_message_extensions_are_allowed(self) -> None:
        wrapped = wrap_a2a_message(
            demo_message(),
            source_id=SOURCE_ID,
            additional_extensions=[OTHER_EXTENSION],
        )
        header = service_headers(additional_extensions=[OTHER_EXTENSION])
        decoded = unwrap_defaults(
            wrapped,
            activated_extensions=header["A2A-Extensions"],
        )
        self.assertEqual(decoded, normalize_message(demo_message()))

    def test_absent_or_partial_extension_activation_is_rejected(self) -> None:
        wrapped = wrap_a2a_message(
            demo_message(),
            source_id=SOURCE_ID,
            additional_extensions=[OTHER_EXTENSION],
        )
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped, activated_extensions=[OTHER_EXTENSION])
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped, activated_extensions=[EXTENSION_URI])

    def test_wrong_a2a_version_is_rejected(self) -> None:
        wrapped = wrap_a2a_message(demo_message(), source_id=SOURCE_ID)
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped, a2a_version="0.3")

    def test_effectful_acts_require_matching_authenticated_sender(self) -> None:
        for act in ("COMMIT", "RESOLVE", "RETRACT"):
            source = effectful_message(act)
            with self.subTest(act=act), self.assertRaises(A2AAdapterError):
                wrap_a2a_message(source, source_id=SOURCE_ID)
            with self.subTest(act=act), self.assertRaises(A2AAdapterError):
                wrap_a2a_message(
                    source,
                    source_id=SOURCE_ID,
                    authenticated_sender="attacker.agent",
                )

            wrapped = wrap_a2a_message(
                source,
                source_id=SOURCE_ID,
                authenticated_sender=source["sender"],
            )
            with self.subTest(act=act), self.assertRaises(A2AAdapterError):
                unwrap_defaults(wrapped)
            with self.subTest(act=act), self.assertRaises(A2AAdapterError):
                unwrap_defaults(wrapped, authenticated_sender="attacker.agent")
            decoded = unwrap_defaults(
                wrapped, authenticated_sender=source["sender"]
            )
            self.assertEqual(decoded["act"], act)

    def test_authenticated_sender_mismatch_rejects_non_effectful_act(self) -> None:
        wrapped = wrap_a2a_message(demo_message(), source_id=SOURCE_ID)
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped, authenticated_sender="attacker.agent")

    def test_role_is_validated_and_can_be_pinned(self) -> None:
        with self.assertRaises(A2AAdapterError):
            wrap_a2a_message(
                demo_message(), source_id=SOURCE_ID, role="ROLE_UNSPECIFIED"
            )
        wrapped = wrap_a2a_message(
            demo_message(), source_id=SOURCE_ID, role="ROLE_AGENT"
        )
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped, expected_role="ROLE_USER")
        self.assertEqual(
            unwrap_defaults(wrapped, expected_role="ROLE_AGENT")["id"],
            demo_message()["id"],
        )

    def test_a2a_message_id_must_match_semantic_id(self) -> None:
        wrapped = wrap_a2a_message(demo_message(), source_id=SOURCE_ID)
        wrapped["messageId"] = REPLY_ID
        with self.assertRaises(A2AAdapterError):
            unwrap_defaults(wrapped)

    def test_raw_mutation_is_rejected(self) -> None:
        part = pack_part(demo_message())
        changed = copy.deepcopy(part)
        raw = changed["raw"]
        changed["raw"] = ("A" if raw[0] != "A" else "B") + raw[1:]
        with self.assertRaises(A2AAdapterError):
            unpack_part(changed)

    def test_base64_decoded_size_is_rejected_before_decode(self) -> None:
        part = pack_part(demo_message())
        frame_size = len(base64.b64decode(part["raw"], validate=True))
        with patch("urusilla_a2a_adapter.base64.b64decode") as decoder:
            with self.assertRaises(A2AAdapterError):
                unpack_part(part, max_frame_bytes=frame_size - 1)
            decoder.assert_not_called()

    def test_invalid_base64_shape_is_rejected(self) -> None:
        part = pack_part(demo_message())
        part["raw"] = "A==="
        with self.assertRaises(A2AAdapterError):
            unpack_part(part)

    def test_schema_disagreement_is_rejected(self) -> None:
        part = pack_part(demo_message(), diagnostic_metadata=True)
        part["metadata"][EXTENSION_URI]["semanticSchema"] = "urn:wrong"
        with self.assertRaises(A2AAdapterError):
            unpack_part(part)

    def test_hot_part_omits_redundant_diagnostic_metadata(self) -> None:
        part = pack_part(demo_message())
        self.assertNotIn("metadata", part)
        self.assertEqual(unpack_part(part), normalize_message(demo_message()))

    def test_capsule_disagreement_is_rejected(self) -> None:
        part = pack_part(demo_message(), capsule_digest="sha256:one")
        with self.assertRaises(A2AAdapterError):
            unpack_part(part, expected_capsule_digest="sha256:two")

    def test_agent_extension_uses_only_official_v1_fields(self) -> None:
        manifest = {"languageVersion": "0.1.0"}
        declaration = agent_extension(
            "sha256:capsule", source_manifest=manifest
        )
        self.assertEqual(
            set(declaration), {"uri", "description", "required", "params"}
        )
        self.assertFalse(declaration["required"])
        self.assertEqual(declaration["uri"], EXTENSION_URI)
        self.assertEqual(declaration["params"]["status"], "experimental")
        self.assertEqual(declaration["params"]["languageVersion"], "0.1.0")
        self.assertEqual(declaration["params"]["semanticKernelVersion"], "0.1.0")
        self.assertEqual(declaration["params"]["sourceManifest"], manifest)

    def test_agent_extension_rejects_prerelease_as_semantic_version(self) -> None:
        with self.assertRaisesRegex(A2AAdapterError, "exactly 0.1.0"):
            agent_extension(
                source_manifest={"languageVersion": "0.1.0-experimental"}
            )


if __name__ == "__main__":
    unittest.main()
