"""Deterministic tests for the local content-free telemetry module."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


KIT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_DIR))

from telemetry import (  # noqa: E402
    EvidenceRegistry,
    TelemetryState,
    TelemetryValidationError,
    TrustedLocalCompletionIssuerRegistry,
    ValidationResult,
    adoption_adjusted_impact,
    aggregate_events,
    aggregate_json,
    attach_local_completion_attestation,
    canonical_json_bytes,
    coarse_day_bucket,
    create_signed_event,
    derive_rotating_pseudonym,
    sign_event,
    validate_event,
)


DAY = "2026-08-20"
IMPLEMENTATION = "neutral-kit/0.1.0"
PROFILE = "sha256:" + "3" * 64
CONFORMANCE = "sha256:" + "1" * 64
CROSSPLAY = "sha256:" + "2" * 64
ISSUER_ID = "synthetic-collector-1"
ISSUER_SECRET = b"synthetic-completion-issuer-key!!"
METRICS = {
    "cache_state": "warm",
    "wire_delta": "saved_256_1023",
    "token_delta": "saved_32_127",
    "latency": "10_99ms",
    "repair_turns": "0",
}


def nonce(number: int) -> str:
    return f"{number:032x}"


def registry() -> EvidenceRegistry:
    return EvidenceRegistry(
        {
            CONFORMANCE: {
                "kind": "conformance",
                "implementation_version": IMPLEMENTATION,
            },
            CROSSPLAY: {
                "kind": "crossplay",
                "implementation_version": IMPLEMENTATION,
                "conformance_ref": CONFORMANCE,
            },
        }
    )


def completion_registry() -> TrustedLocalCompletionIssuerRegistry:
    return TrustedLocalCompletionIssuerRegistry({ISSUER_ID: ISSUER_SECRET})


def signed(
    secret: bytes,
    sequence: int,
    event_type: str,
    outcome: str,
    *,
    nonce_number: int,
    mode: str = "bridge",
    deployment_class: str = "external",
    reason_code: str | None = None,
    evidence_refs: dict[str, str] | None = None,
    metrics: dict[str, str] | None = None,
    day: str = DAY,
) -> dict:
    return create_signed_event(
        secret=secret,
        telemetry_opt_in=True,
        event_type=event_type,
        coarse_time_bucket=day,
        deployment_class=deployment_class,
        implementation_version=IMPLEMENTATION,
        mode=mode,
        outcome=outcome,
        sequence=sequence,
        event_nonce=nonce(nonce_number),
        reason_code=reason_code,
        public_profile_digest=PROFILE,
        metric_buckets=metrics,
        evidence_refs=evidence_refs,
    )


def validate_trajectory(
    secret: bytes,
    *,
    nonce_base: int,
    deployment_class: str = "external",
    evidence_refs: dict[str, str] | None = None,
    evidence_registry: EvidenceRegistry | None = None,
    metrics: dict[str, str] | None = METRICS,
    locally_attested: bool = False,
) -> list:
    state = TelemetryState()
    events = [
        signed(
            secret,
            0,
            "profile_discovered",
            "observed",
            nonce_number=nonce_base,
            deployment_class=deployment_class,
        ),
        signed(
            secret,
            1,
            "manifest_verified",
            "succeeded",
            nonce_number=nonce_base + 1,
            deployment_class=deployment_class,
        ),
        signed(
            secret,
            2,
            "negotiation_accepted",
            "succeeded",
            nonce_number=nonce_base + 2,
            deployment_class=deployment_class,
        ),
        signed(
            secret,
            3,
            "safe_message_completed",
            "succeeded",
            nonce_number=nonce_base + 3,
            deployment_class=deployment_class,
            evidence_refs=evidence_refs,
            metrics=metrics,
        ),
    ]
    if locally_attested:
        events[-1] = attach_local_completion_attestation(
            events[-1],
            event_secret=secret,
            issuer_id=ISSUER_ID,
            issuer_secret=ISSUER_SECRET,
        )
    return [
        validate_event(
            event,
            secret=secret,
            state=state,
            evidence_registry=evidence_registry,
            completion_issuer_registry=(
                completion_registry() if locally_attested else None
            ),
        )
        for event in events
    ]


def active_state(secret: bytes, *, nonce_base: int) -> TelemetryState:
    state = TelemetryState()
    prefix = [
        signed(
            secret,
            0,
            "profile_discovered",
            "observed",
            nonce_number=nonce_base,
        ),
        signed(
            secret,
            1,
            "manifest_verified",
            "succeeded",
            nonce_number=nonce_base + 1,
        ),
        signed(
            secret,
            2,
            "negotiation_accepted",
            "succeeded",
            nonce_number=nonce_base + 2,
        ),
    ]
    for event in prefix:
        validate_event(event, secret=secret, state=state)
    return state


class TelemetrySchemaTests(unittest.TestCase):
    def test_schema_is_exact_opt_in_content_free_allowlist(self) -> None:
        schema = json.loads((KIT_DIR / "telemetry_schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["telemetry_opt_in"]["const"], True)
        keys = set(schema["properties"])
        forbidden = {
            "message_id",
            "user_id",
            "session_id",
            "device_id",
            "account_id",
            "ip_address",
            "content",
            "prompt",
            "answer",
            "query",
            "source_uri",
        }
        self.assertTrue(keys.isdisjoint(forbidden))
        self.assertEqual(schema["properties"]["coarse_time_bucket"]["type"], "string")
        self.assertIn("structural documentation only", schema["$comment"])
        self.assertIn("completion_attestation", keys)

    def test_rotating_pseudonym_and_utc_day_are_deterministic(self) -> None:
        secret = b"A" * 32
        august = derive_rotating_pseudonym(secret, "2026-08")
        self.assertEqual(august, derive_rotating_pseudonym(secret, "2026-08"))
        self.assertNotEqual(august, derive_rotating_pseudonym(secret, "2026-09"))
        self.assertRegex(august, r"^rp1:2026-08:[0-9a-f]{32}$")
        instant = datetime(2026, 8, 20, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(coarse_day_bucket(instant), DAY)
        with self.assertRaises(TelemetryValidationError):
            coarse_day_bucket(datetime(2026, 8, 20, 23, 30))


class TelemetryValidationTests(unittest.TestCase):
    def test_opt_in_is_mandatory_and_non_allowlisted_content_fails(self) -> None:
        secret = b"B" * 32
        with self.assertRaisesRegex(TelemetryValidationError, "opt-in"):
            create_signed_event(
                secret=secret,
                telemetry_opt_in=False,
                event_type="profile_discovered",
                coarse_time_bucket=DAY,
                deployment_class="test",
                implementation_version=IMPLEMENTATION,
                mode="bridge",
                outcome="observed",
                sequence=0,
                event_nonce=nonce(1),
            )
        event = signed(secret, 0, "profile_discovered", "observed", nonce_number=2)
        event["message_content"] = "forbidden"
        with self.assertRaisesRegex(TelemetryValidationError, "non-allowlisted"):
            validate_event(event, secret=secret, state=TelemetryState())

    def test_hmac_tampering_and_wrong_secret_fail_closed(self) -> None:
        secret = b"C" * 32
        event = signed(secret, 0, "profile_discovered", "observed", nonce_number=3)
        tampered = dict(event)
        tampered["implementation_version"] = "neutral-kit/0.1.1"
        state = TelemetryState()
        with self.assertRaisesRegex(TelemetryValidationError, "HMAC"):
            validate_event(tampered, secret=secret, state=state)
        self.assertEqual(state.seen_nonces, set())
        with self.assertRaises(TelemetryValidationError):
            validate_event(event, secret=b"D" * 32, state=state)
        self.assertEqual(state.last_sequence, {})

    def test_replay_sequence_gap_and_impossible_transition_are_rejected(self) -> None:
        secret = b"E" * 32
        state = TelemetryState()
        discovery = signed(secret, 0, "profile_discovered", "observed", nonce_number=4)
        validate_event(discovery, secret=secret, state=state)
        with self.assertRaisesRegex(TelemetryValidationError, "replay"):
            validate_event(discovery, secret=secret, state=state)
        gap = signed(secret, 2, "manifest_verified", "succeeded", nonce_number=5)
        with self.assertRaisesRegex(TelemetryValidationError, "exactly 1"):
            validate_event(gap, secret=secret, state=state)
        impossible = signed(secret, 1, "negotiation_accepted", "succeeded", nonce_number=6)
        with self.assertRaisesRegex(TelemetryValidationError, "impossible"):
            validate_event(impossible, secret=secret, state=state)
        manifest = signed(secret, 1, "manifest_verified", "succeeded", nonce_number=7)
        validate_event(manifest, secret=secret, state=state)
        self.assertEqual(state.last_sequence[next(iter(state.last_sequence))], 1)

    def test_first_safe_message_and_precise_timestamp_fail(self) -> None:
        secret = b"F" * 32
        first_safe = signed(
            secret,
            0,
            "safe_message_completed",
            "succeeded",
            nonce_number=8,
            metrics=METRICS,
        )
        with self.assertRaisesRegex(TelemetryValidationError, "first event"):
            validate_event(first_safe, secret=secret, state=TelemetryState())
        with self.assertRaisesRegex(TelemetryValidationError, "YYYY-MM-DD"):
            signed(
                secret,
                0,
                "profile_discovered",
                "observed",
                nonce_number=9,
                day="2026-08-20T12:00:00Z",
            )

    def test_rate_limit_is_per_pseudonym_day_and_type(self) -> None:
        secret = b"G" * 32
        state = TelemetryState()
        initial = [
            signed(secret, 0, "profile_discovered", "observed", nonce_number=10),
            signed(secret, 1, "manifest_verified", "succeeded", nonce_number=11),
            signed(secret, 2, "negotiation_accepted", "succeeded", nonce_number=12),
            signed(
                secret,
                3,
                "safe_message_completed",
                "succeeded",
                nonce_number=13,
                metrics=METRICS,
            ),
        ]
        for event in initial:
            validate_event(
                event,
                secret=secret,
                state=state,
                per_type_limits={"safe_message_completed": 1},
            )
        second = signed(
            secret,
            4,
            "safe_message_completed",
            "succeeded",
            nonce_number=14,
            metrics=METRICS,
        )
        with self.assertRaisesRegex(TelemetryValidationError, "event-type rate"):
            validate_event(
                second,
                secret=secret,
                state=state,
                per_type_limits={"safe_message_completed": 1},
            )
        self.assertNotIn(nonce(14), state.seen_nonces)

    def test_valid_fallback_lifecycle_preserves_controlled_mode(self) -> None:
        secret = b"H" * 32
        state = TelemetryState()
        events = [
            signed(secret, 0, "profile_discovered", "observed", nonce_number=20),
            signed(secret, 1, "manifest_verified", "succeeded", nonce_number=21),
            signed(
                secret,
                2,
                "negotiation_rejected",
                "failed",
                nonce_number=22,
                reason_code="CODEC_UNSUPPORTED",
            ),
            signed(
                secret,
                3,
                "fallback_succeeded",
                "succeeded",
                nonce_number=23,
                mode="json_fallback",
            ),
            signed(
                secret,
                4,
                "safe_message_completed",
                "succeeded",
                nonce_number=24,
                mode="json_fallback",
                metrics=METRICS,
            ),
        ]
        for event in events:
            validate_event(event, secret=secret, state=state)
        pseudonym = events[0]["rotating_install_pseudonym"]
        self.assertEqual(state.phases[pseudonym], "FALLBACK")
        self.assertEqual(state.active_modes[pseudonym], "json_fallback")

    def test_evidence_tiers_are_local_and_fail_closed(self) -> None:
        declared = validate_trajectory(
            b"I" * 32,
            nonce_base=30,
            evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
            evidence_registry=registry(),
        )[-1]
        self.assertEqual(declared.evidence_tier, "local_evidence_declared")
        self.assertIn(
            "local_evidence_registry_is_not_independent_verification",
            declared.evidence_warnings,
        )
        self.assertFalse(hasattr(declared, "secret_fingerprint"))

        unknown_ref = "sha256:" + "9" * 64
        unverified = validate_trajectory(
            b"J" * 32,
            nonce_base=40,
            evidence_refs={"conformance": unknown_ref},
            evidence_registry=registry(),
        )[-1]
        self.assertEqual(unverified.evidence_tier, "local_hmac")
        self.assertIn(
            "conformance_evidence_not_locally_declared",
            unverified.evidence_warnings,
        )
        self.assertEqual(
            adoption_adjusted_impact([unverified])["value_milliunits"],
            0,
        )

    def test_caller_cannot_mark_evidence_registry_record_verified(self) -> None:
        with self.assertRaisesRegex(TelemetryValidationError, "invalid conformance"):
            EvidenceRegistry(
                {
                    CONFORMANCE: {
                        "kind": "conformance",
                        "verified": True,
                        "implementation_version": IMPLEMENTATION,
                    }
                }
            )

    def test_missing_completion_attestation_is_accepted_but_scores_zero(self) -> None:
        result = validate_trajectory(
            b"T" * 32,
            nonce_base=1200,
            evidence_refs={"conformance": CONFORMANCE},
            evidence_registry=registry(),
        )[-1]
        self.assertEqual(result.evidence_tier, "local_evidence_declared")
        self.assertIn("completion_attestation_missing", result.evidence_warnings)
        aggregate = aggregate_events([result])
        self.assertEqual(aggregate["adoption_adjusted_impact"]["value_milliunits"], 0)
        self.assertEqual(
            aggregate["synthetic_locally_attested_impact"]["value_milliunits"],
            0,
        )

    def test_forged_or_misbound_completion_attestation_fails_closed(self) -> None:
        secret = b"U" * 32
        state = active_state(secret, nonce_base=1300)
        safe = signed(
            secret,
            3,
            "safe_message_completed",
            "succeeded",
            nonce_number=1303,
            evidence_refs={"conformance": CONFORMANCE},
            metrics=METRICS,
        )
        attested = attach_local_completion_attestation(
            safe,
            event_secret=secret,
            issuer_id=ISSUER_ID,
            issuer_secret=ISSUER_SECRET,
        )
        unsigned_forged = {
            key: value for key, value in attested.items() if key != "signature"
        }
        unsigned_forged["completion_attestation"] = dict(
            unsigned_forged["completion_attestation"]
        )
        unsigned_forged["completion_attestation"]["signature"] = (
            "hmac-sha256:" + "0" * 64
        )
        forged = sign_event(unsigned_forged, secret)
        with self.assertRaisesRegex(TelemetryValidationError, "binding or HMAC"):
            validate_event(
                forged,
                secret=secret,
                state=state,
                evidence_registry=registry(),
                completion_issuer_registry=completion_registry(),
            )
        self.assertNotIn(nonce(1303), state.seen_nonces)

        other_secret = b"V" * 32
        other_state = active_state(other_secret, nonce_base=1400)
        other_safe = signed(
            other_secret,
            3,
            "safe_message_completed",
            "succeeded",
            nonce_number=1403,
            evidence_refs={"conformance": CONFORMANCE},
            metrics=METRICS,
        )
        unsigned_misbound = {
            key: value for key, value in other_safe.items() if key != "signature"
        }
        unsigned_misbound["completion_attestation"] = dict(
            attested["completion_attestation"]
        )
        misbound = sign_event(unsigned_misbound, other_secret)
        with self.assertRaisesRegex(TelemetryValidationError, "binding or HMAC"):
            validate_event(
                misbound,
                secret=other_secret,
                state=other_state,
                evidence_registry=registry(),
                completion_issuer_registry=completion_registry(),
            )
        self.assertNotIn(nonce(1403), other_state.seen_nonces)

    def test_valid_local_attestation_is_synthetic_not_external_verification(self) -> None:
        result = validate_trajectory(
            b"W" * 32,
            nonce_base=1500,
            deployment_class="external",
            evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
            evidence_registry=registry(),
            locally_attested=True,
        )[-1]
        self.assertEqual(result.evidence_tier, "locally_attested_completion")
        aggregate = aggregate_events([result])
        self.assertEqual(
            aggregate["safe_completion"]["independently_verified_external"],
            0,
        )
        self.assertEqual(aggregate["adoption_adjusted_impact"]["value_milliunits"], 0)
        self.assertEqual(
            aggregate["synthetic_locally_attested_impact"]["value_milliunits"],
            1000,
        )


class TelemetryAggregateTests(unittest.TestCase):
    def test_hand_built_receipt_cannot_forge_evidence_tier_or_impact(self) -> None:
        accepted = validate_trajectory(
            b"R" * 32,
            nonce_base=900,
            evidence_refs=None,
            evidence_registry=registry(),
        )[-1]
        self.assertEqual(accepted.evidence_tier, "local_hmac")
        with self.assertRaisesRegex(TypeError, "issued only"):
            ValidationResult(
                accepted.event,
                "locally_attested_completion",
                (),
                "0" * 32,
            )

        forged = object.__new__(ValidationResult)
        object.__setattr__(forged, "_event_bytes", canonical_json_bytes(accepted.event))
        object.__setattr__(forged, "_evidence_tier", "locally_attested_completion")
        object.__setattr__(forged, "_evidence_warnings", ())
        object.__setattr__(
            forged,
            "_secret_epoch_fingerprint",
            accepted._secret_epoch_fingerprint,
        )
        object.__setattr__(forged, "_receipt_seal", accepted._receipt_seal)
        with self.assertRaisesRegex(TelemetryValidationError, "unauthentic receipt"):
            aggregate_events([forged])

    def test_aggregate_is_deterministic_and_uses_safe_messages_not_downloads(self) -> None:
        locally_attested_external = validate_trajectory(
            b"K" * 32,
            nonce_base=100,
            evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
            evidence_registry=registry(),
            locally_attested=True,
        )
        locally_attested_external_2 = validate_trajectory(
            b"L" * 32,
            nonce_base=200,
            evidence_refs={"conformance": CONFORMANCE},
            evidence_registry=registry(),
            metrics={**METRICS, "latency": "100_999ms"},
            locally_attested=True,
        )
        self_reported_internal = validate_trajectory(
            b"M" * 32,
            nonce_base=300,
            deployment_class="internal",
            evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
            evidence_registry=registry(),
        )
        results = (
            locally_attested_external
            + locally_attested_external_2
            + self_reported_internal
        )
        first = aggregate_events(results)
        second = aggregate_events(reversed(results))
        self.assertEqual(first, second)
        self.assertEqual(aggregate_json(results), aggregate_json(reversed(results)))
        self.assertEqual(first["safe_completion"]["self_reported_observed"], 3)
        self.assertEqual(first["safe_completion"]["locally_attested_synthetic"], 2)
        self.assertEqual(first["safe_completion"]["independently_verified_external"], 0)
        self.assertEqual(first["adoption_adjusted_impact"]["value_milliunits"], 0)
        self.assertEqual(
            first["synthetic_locally_attested_impact"]["value_milliunits"],
            2000,
        )
        self.assertFalse(
            first["adoption_adjusted_impact"]["downloads_or_repository_activity_used"]
        )
        self.assertRegex(first["aggregate_sha256"], r"^[0-9a-f]{64}$")

    def test_shared_evidence_and_synchronized_sybil_cluster_is_flagged(self) -> None:
        results = []
        for offset, fill in enumerate((b"N", b"O", b"P")):
            results.extend(
                validate_trajectory(
                    fill * 32,
                    nonce_base=400 + 100 * offset,
                    evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
                    evidence_registry=registry(),
                    locally_attested=True,
                )
            )
        aggregate = aggregate_events(results)
        flags = aggregate["anti_sybil"]["cluster_flag_counts"]
        self.assertEqual(flags["shared_evidence_cluster"], 3)
        self.assertEqual(flags["synchronized_activity_cluster"], 3)
        self.assertEqual(aggregate["anti_sybil"]["flagged_events"], 3)
        self.assertEqual(
            aggregate["synthetic_locally_attested_impact"]["value_milliunits"],
            750,
        )
        self.assertEqual(aggregate["adoption_adjusted_impact"]["value_milliunits"], 0)
        self.assertEqual(
            aggregate["anti_sybil"]["classification"],
            "heuristic_not_identity_or_independence_proof",
        )

    def test_aggregate_rejects_duplicate_validated_event(self) -> None:
        result = validate_trajectory(
            b"Q" * 32,
            nonce_base=800,
            evidence_refs={"conformance": CONFORMANCE},
            evidence_registry=registry(),
        )[-1]
        with self.assertRaisesRegex(TelemetryValidationError, "repeats"):
            aggregate_events([result, result])

    def test_separate_states_cannot_duplicate_pseudonym_sequence_trajectory(self) -> None:
        secret = b"S" * 32
        first = validate_trajectory(
            secret,
            nonce_base=1000,
            evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
            evidence_registry=registry(),
        )[-1]
        duplicate_position = validate_trajectory(
            secret,
            nonce_base=1100,
            evidence_refs={"conformance": CONFORMANCE, "crossplay": CROSSPLAY},
            evidence_registry=registry(),
        )[-1]
        self.assertNotEqual(first.event["event_nonce"], duplicate_position.event["event_nonce"])
        self.assertEqual(
            (
                first.event["rotating_install_pseudonym"],
                first.event["sequence"],
            ),
            (
                duplicate_position.event["rotating_install_pseudonym"],
                duplicate_position.event["sequence"],
            ),
        )
        with self.assertRaisesRegex(TelemetryValidationError, "lifecycle sequence"):
            aggregate_events([first, duplicate_position])


if __name__ == "__main__":
    unittest.main()
