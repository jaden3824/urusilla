from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT / "python"))

from urusilla_sdk import (  # noqa: E402
    A2A_LOCAL_EXTENSION,
    ArtifactCache,
    IntegrationError,
    UrusillaSDK,
    SessionAccountingReceipt,
    canonical_json_bytes,
    verify_artifact_pins,
)
from urusilla_sdk.sdk import (  # noqa: E402
    CAPSULE_BYTES,
    CAPSULE_SHA256,
    CAPSULE_BOUND_REFERENCE_SHA256,
    JSON_REPRESENTATION,
    PROFILE_CAPSULE_SHA256,
    RELEASE_STATUS,
    TERSE_REPRESENTATION,
    WIRE_V02_REPRESENTATION,
)


SOURCE_A = "11111111111111111111111111111111"
SOURCE_B = "22222222222222222222222222222222"


def fixture() -> dict:
    return json.loads((KIT_ROOT / "fixtures" / "request.json").read_text(encoding="utf-8"))


class PythonSDKTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        warm = (CAPSULE_SHA256, PROFILE_CAPSULE_SHA256)
        cls.a = UrusillaSDK(source_id=SOURCE_A, cache=ArtifactCache(warm))
        cls.b = UrusillaSDK(source_id=SOURCE_B, cache=ArtifactCache(warm))

    def directional_sessions(self, representation: str):
        message = fixture()
        a_to_b = self.a.negotiate(
            self.b.discover_capabilities(),
            message,
            expected_messages=4,
            preferred_representation=representation,
        )
        b_receives_a = self.b.negotiate(
            self.a.discover_capabilities(),
            message,
            expected_messages=4,
            preferred_representation=representation,
        )
        return a_to_b, b_receives_a

    def test_exact_root_artifact_pins(self) -> None:
        observed = verify_artifact_pins()
        self.assertEqual(observed["urusilla_capsule_v0_1.json"], CAPSULE_SHA256)
        self.assertEqual(
            observed["urusilla_wire_v02.profile_capsule"], PROFILE_CAPSULE_SHA256
        )
        self.assertEqual(
            observed["capsule.bound_reference_codec_sha256"],
            CAPSULE_BOUND_REFERENCE_SHA256,
        )
        self.assertEqual(observed["capsule.reference_codec_matches_observed"], "true")
        self.assertEqual(observed["capsule.release_status"], "experimental-unsigned")
        self.assertEqual(observed["capsule.publisher_status"], "unsigned")
        self.assertEqual(observed["capsule.unsigned_operation_scope"], "local-read-only")
        self.assertEqual(
            observed["capsule.effect_authorizing_requires_signature_and_policy"], "true"
        )

    def test_capability_separates_modes_and_disables_effects(self) -> None:
        capability = self.a.discover_capabilities()
        self.assertEqual(RELEASE_STATUS, "experimental-unsigned")
        self.assertEqual(capability["lifecycle"], RELEASE_STATUS)
        self.assertEqual(capability["semantics"]["release_status"], RELEASE_STATUS)
        self.assertTrue(capability["modes"]["bridge"]["supported"])
        self.assertFalse(capability["modes"]["native"]["supported"])
        self.assertTrue(capability["modes"]["fallback"]["supported"])
        self.assertFalse(capability["safety"]["effect_authorization"])
        self.assertEqual(capability["limits"]["json_max_safe_integer"], (1 << 53) - 1)
        self.assertFalse(capability["limits"]["json_float64"])
        self.assertFalse(capability["provenance"]["support_claim_eligible"])
        self.assertTrue(capability["provenance"]["reference_codec_matches_capsule"])
        self.assertFalse(capability["safety"]["provenance_bound"])
        self.assertTrue(capability["safety"]["unsigned_operation_read_only"])
        retired = copy.deepcopy(capability)
        retired["lifecycle"] = "experimental-unsigned-invalid"
        with self.assertRaisesRegex(IntegrationError, "lifecycle"):
            self.a.negotiate(retired, fixture())
        retired = copy.deepcopy(capability)
        retired["semantics"]["release_status"] = "experimental-unsigned-invalid"
        with self.assertRaisesRegex(IntegrationError, "semantics"):
            self.a.negotiate(retired, fixture())

    def test_v02_round_trip_with_exact_profile_registry(self) -> None:
        outbound, inbound = self.directional_sessions(WIRE_V02_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        decoded = self.b.decode_delivery(delivery.envelope, inbound)
        self.assertEqual(decoded.message, self.a.normalize_input(fixture(), mode="fallback"))
        self.assertEqual(decoded.source_id, SOURCE_A)
        self.assertFalse(decoded.effect_authorized)

    def test_json_round_trip_and_source_preservation(self) -> None:
        outbound, inbound = self.directional_sessions(JSON_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        decoded = self.b.decode_delivery(delivery.envelope, inbound)
        self.assertEqual(decoded.source_id, SOURCE_A)
        self.assertTrue(decoded.semantic_valid)

    def test_controlled_terse_english_round_trip(self) -> None:
        outbound, inbound = self.directional_sessions(TERSE_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        decoded = self.b.decode_delivery(delivery.envelope, inbound)
        self.assertEqual(decoded.message, self.a.normalize_input(fixture(), mode="fallback"))

    def test_native_request_falls_back_without_evidence(self) -> None:
        session = self.a.negotiate(
            self.b.discover_capabilities(), fixture(), requested_mode="native"
        )
        self.assertEqual(session.mode, "fallback")
        self.assertEqual(session.fallback_reason, "native_evidence_unavailable")

    def test_cache_charges_each_artifact_once(self) -> None:
        sender = UrusillaSDK(source_id=SOURCE_A)
        receiver = UrusillaSDK(source_id=SOURCE_B)
        first = sender.negotiate(
            receiver.discover_capabilities(),
            fixture(),
            receiver_cache=receiver.cache,
            expected_messages=20,
            preferred_representation=WIRE_V02_REPRESENTATION,
        )
        self.assertEqual(first.planned_cold_bytes, CAPSULE_BYTES + 1_402)
        self.assertEqual(receiver.cache.digests, ())
        receipt = sender.prepare_session_artifacts(first, receiver.cache)
        self.assertIsInstance(receipt, SessionAccountingReceipt)
        delivery = sender.encode_delivery(fixture(), first, accounting_receipt=receipt)
        self.assertEqual(
            delivery.accounting.transferred_artifact_bytes, CAPSULE_BYTES + 1_402
        )
        with self.assertRaisesRegex(IntegrationError, "already consumed"):
            sender.encode_delivery(fixture(), first, accounting_receipt=receipt)
        with self.assertRaisesRegex(IntegrationError, "already prepared"):
            sender.prepare_session_artifacts(first, receiver.cache)

        second = sender.negotiate(
            receiver.discover_capabilities(),
            fixture(),
            receiver_cache=receiver.cache,
            expected_messages=20,
            preferred_representation=WIRE_V02_REPRESENTATION,
        )
        self.assertEqual(second.planned_cold_bytes, 0)

    def test_source_mismatch_fails_closed(self) -> None:
        outbound, inbound = self.directional_sessions(JSON_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        changed = copy.deepcopy(delivery.envelope)
        changed["pins"]["source_id"] = SOURCE_B
        with self.assertRaisesRegex(IntegrationError, "source_id"):
            self.b.decode_delivery(changed, inbound)

    def test_payload_damage_fails_closed(self) -> None:
        outbound, inbound = self.directional_sessions(JSON_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        changed = copy.deepcopy(delivery.envelope)
        changed["payload"]["data"] += " "
        with self.assertRaisesRegex(IntegrationError, "digest mismatch"):
            self.b.decode_delivery(changed, inbound)

    def test_a2a_friendly_shape_preserves_source_and_activation(self) -> None:
        outbound, inbound = self.directional_sessions(JSON_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        wrapper = self.a.to_a2a_message(delivery, message_id=fixture()["id"])
        decoded = self.b.from_a2a_message(
            wrapper,
            inbound,
            activated_extensions=[A2A_LOCAL_EXTENSION],
            a2a_version="1.0",
        )
        self.assertEqual(decoded.source_id, SOURCE_A)
        with self.assertRaisesRegex(IntegrationError, "not explicitly activated"):
            self.b.from_a2a_message(
                wrapper, inbound, activated_extensions=[], a2a_version="1.0"
            )

    def test_mcp_friendly_shape_round_trip(self) -> None:
        outbound, inbound = self.directional_sessions(JSON_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        result = self.a.to_mcp_result(delivery)
        decoded = self.b.from_mcp_result(result, inbound)
        self.assertEqual(decoded.message["id"], fixture()["id"])

    def test_bridge_text_requires_explicit_compiler(self) -> None:
        with self.assertRaisesRegex(IntegrationError, "compiler callback"):
            self.a.normalize_input("please do something", mode="bridge")
        canonical = self.a.normalize_input(
            "bounded fixture", mode="bridge", bridge_compiler=lambda _text: fixture()
        )
        self.assertEqual(canonical["act"], "REQUEST")

    def test_json_fallback_rejects_bytes_and_uses_other_exact_codec(self) -> None:
        message = fixture()
        message["meta"] = {"opaque": b"\x00\xff"}
        session = self.a.negotiate(
            self.b.discover_capabilities(), message, expected_messages=1
        )
        self.assertNotEqual(session.representation, JSON_REPRESENTATION)

    def test_cross_runtime_json_excludes_floats_and_unsafe_integers(self) -> None:
        for value in (0.125, 1 << 53):
            message = fixture()
            message["meta"] = {"cross_runtime_unsafe": value}
            session = self.a.negotiate(
                self.b.discover_capabilities(), message, expected_messages=1
            )
            self.assertNotEqual(session.representation, JSON_REPRESENTATION)

    def test_delivery_json_is_deterministic(self) -> None:
        outbound, _inbound = self.directional_sessions(JSON_REPRESENTATION)
        one = self.a.encode_delivery(fixture(), outbound)
        two = self.a.encode_delivery(fixture(), outbound)
        self.assertEqual(canonical_json_bytes(one.envelope), canonical_json_bytes(two.envelope))

    def test_frozen_json_domain_and_unicode_key_order(self) -> None:
        self.assertEqual(
            canonical_json_bytes({"😀": 1, "\ue000": 2, "a": 3}).decode("utf-8"),
            '{"a":3,"\ue000":2,"😀":1}',
        )
        for value in (0.125, 1 << 53, -(1 << 53), b"no-json"):
            with self.assertRaises(IntegrationError):
                canonical_json_bytes({"value": value})
        cyclic: list = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(IntegrationError, "acyclic"):
            canonical_json_bytes(cyclic)

    def test_declared_native_digest_cannot_enable_native(self) -> None:
        sdk = UrusillaSDK(
            source_id=SOURCE_A,
            native_evidence_sha256="a" * 64,
        )
        native = sdk.discover_capabilities()["modes"]["native"]
        self.assertFalse(native["supported"])
        self.assertFalse(native["verified"])

    def test_peer_can_disable_required_fallback(self) -> None:
        peer = self.b.discover_capabilities()
        peer["modes"]["fallback"]["supported"] = False
        with self.assertRaisesRegex(IntegrationError, "disabled fallback"):
            self.a.negotiate(peer, fixture(), requested_mode="native")

    def test_source_manifest_must_pin_exact_capsule_and_payload(self) -> None:
        commit = "1" * 40
        manifest = {
            "languageSpecUri": (
                f"https://github.com/example/project/blob/{commit}/urusilla_v0_1_spec.md"
            ),
            "languageVersion": "0.1.0",
            "capsuleSha256": CAPSULE_SHA256,
            "implementationOrigin": f"https://github.com/example/project/tree/{commit}/impl",
            "conformanceReportUrl": (
                f"https://github.com/example/project/blob/{commit}/report.json"
            ),
            "conformanceReportSha256": "2" * 64,
        }
        sdk = UrusillaSDK(source_manifest=manifest)
        pins = sdk.discover_capabilities()["pins"]
        self.assertRegex(pins["source_manifest_payload_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(pins["source_manifest_signature_status"], "unsigned")
        mismatched = copy.deepcopy(manifest)
        mismatched["capsuleSha256"] = "f" * 64
        with self.assertRaisesRegex(IntegrationError, "Capsule digest differs"):
            UrusillaSDK(source_manifest=mismatched)

    def test_pin_mismatch_is_opaque_json_and_preserves_exact_peer_offer(self) -> None:
        peer = self.a.discover_capabilities()
        peer["semantics"]["language_version"] = "9.9.9"
        peer["semantics"]["capsule_sha256"] = "f" * 64
        inbound = self.b.negotiate(
            peer,
            fixture(),
            preferred_representation=JSON_REPRESENTATION,
        )
        self.assertEqual(inbound.mode, "fallback")
        self.assertEqual(inbound.planned_cold_bytes, 0)

        current_outbound, _ = self.directional_sessions(JSON_REPRESENTATION)
        envelope = copy.deepcopy(self.a.encode_delivery(fixture(), current_outbound).envelope)
        envelope["mode"] = "fallback"
        envelope["pins"]["language_version"] = "9.9.9"
        envelope["pins"]["capsule_sha256"] = "f" * 64
        envelope["safety"] = {
            "effect_authorized": False,
            "semantic_status": "opaque-fallback-only",
            "fallback_reason": "semantic_pin_mismatch",
        }
        decoded = self.b.decode_delivery(envelope, inbound)
        self.assertFalse(decoded.semantic_valid)
        self.assertIsNone(decoded.message)
        self.assertEqual(decoded.opaque_payload["id"], fixture()["id"])

        changed = copy.deepcopy(envelope)
        changed["pins"]["capsule_sha256"] = "e" * 64
        with self.assertRaisesRegex(IntegrationError, "exact peer offer"):
            self.b.decode_delivery(changed, inbound)

    def test_pin_mismatch_never_plans_or_transfers_local_capsule(self) -> None:
        sender = UrusillaSDK(source_id=SOURCE_A)
        receiver_cache = ArtifactCache()
        peer = UrusillaSDK(source_id=SOURCE_B).discover_capabilities()
        peer["semantics"]["capsule_sha256"] = "f" * 64
        session = sender.negotiate(
            peer,
            fixture(),
            receiver_cache=receiver_cache,
            preferred_representation=JSON_REPRESENTATION,
        )
        self.assertEqual(session.required_artifacts, ())
        receipt = sender.prepare_session_artifacts(session, receiver_cache)
        self.assertEqual(receipt.transferred_artifact_bytes, 0)
        self.assertEqual(receiver_cache.digests, ())

    def test_delivery_nested_profiles_are_closed(self) -> None:
        outbound, inbound = self.directional_sessions(JSON_REPRESENTATION)
        delivery = self.a.encode_delivery(fixture(), outbound)
        for parent, key in (("pins", "authority"), ("safety", "claimed_authority")):
            changed = copy.deepcopy(delivery.envelope)
            changed[parent][key] = "admin"
            with self.assertRaisesRegex(IntegrationError, "fields differ"):
                self.b.decode_delivery(changed, inbound)

    def test_opaque_a2a_binds_message_id_and_mcp_labels_opaque(self) -> None:
        peer = self.a.discover_capabilities()
        peer["semantics"]["language_version"] = "9.9.9"
        peer["semantics"]["capsule_sha256"] = "f" * 64
        inbound = self.b.negotiate(peer, fixture())
        outbound, _ = self.directional_sessions(JSON_REPRESENTATION)
        envelope = copy.deepcopy(self.a.encode_delivery(fixture(), outbound).envelope)
        envelope["mode"] = "fallback"
        envelope["pins"].update(
            {"language_version": "9.9.9", "capsule_sha256": "f" * 64}
        )
        envelope["safety"] = {
            "effect_authorized": False,
            "semantic_status": "opaque-fallback-only",
            "fallback_reason": "semantic_pin_mismatch",
        }
        opaque_delivery = type(self.a.encode_delivery(fixture(), outbound))(
            envelope=envelope,
            accounting=self.a.encode_delivery(fixture(), outbound).accounting,
        )
        wrapper = self.a.to_a2a_message(opaque_delivery, message_id="wrong-id")
        with self.assertRaisesRegex(IntegrationError, "opaque JSON message id"):
            self.b.from_a2a_message(
                wrapper,
                inbound,
                activated_extensions=[A2A_LOCAL_EXTENSION],
                a2a_version="1.0",
            )
        result = self.a.to_mcp_result(opaque_delivery)
        self.assertIn("Opaque structured fallback", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
