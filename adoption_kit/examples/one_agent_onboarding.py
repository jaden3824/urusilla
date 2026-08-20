#!/usr/bin/env python3
"""One-process onboarding with no network or external side effect."""

from __future__ import annotations

import json
from pathlib import Path
import sys


KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT / "python"))

from urusilla_sdk import ArtifactCache, UrusillaSDK, canonical_json_bytes  # noqa: E402


DEMO_SOURCE_ID = "11111111111111111111111111111111"


def main() -> int:
    message = json.loads((KIT_ROOT / "fixtures" / "request.json").read_text(encoding="utf-8"))
    sender = UrusillaSDK(source_id=DEMO_SOURCE_ID)
    receiver = UrusillaSDK(
        source_id="22222222222222222222222222222222",
        cache=ArtifactCache(),
    )
    peer = receiver.discover_capabilities()
    session = sender.negotiate(
        peer,
        message,
        requested_mode="bridge",
        expected_messages=10,
        receiver_cache=receiver.cache,
    )
    receipt = sender.prepare_session_artifacts(session, receiver.cache)
    delivery = sender.encode_delivery(message, session, accounting_receipt=receipt)

    # A second directional session is how a real receiver pins the sender.
    receiver_session = receiver.negotiate(
        sender.discover_capabilities(),
        message,
        requested_mode="bridge",
        expected_messages=10,
        preferred_representation=session.representation,
    )
    decoded = receiver.decode_delivery(delivery.envelope, receiver_session)
    result = {
        "product_label": peer["product_label"],
        "mode": session.mode,
        "representation": session.representation,
        "source_id_preserved": decoded.source_id == DEMO_SOURCE_ID,
        "semantic_round_trip": decoded.message == sender.normalize_input(message, mode="fallback"),
        "effect_authorized": decoded.effect_authorized,
        "accounting": {
            "raw_payload_bytes": delivery.accounting.raw_payload_bytes,
            "carrier_payload_bytes": delivery.accounting.carrier_payload_bytes,
            "envelope_bytes": delivery.accounting.envelope_bytes,
            "discovery_bytes": delivery.accounting.discovery_bytes,
            "planned_artifact_bytes": session.planned_cold_bytes,
            "transferred_artifact_bytes": delivery.accounting.transferred_artifact_bytes,
            "first_delivery_total_bytes": delivery.accounting.first_delivery_total_bytes,
            "receiver_cache_after": list(receiver.cache.digests),
        },
        "scope": "local-only; no network; no external adoption claim",
    }
    sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
