#!/usr/bin/env python3
"""Local Python/Node structural cross-play over stdio; no network is opened."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT / "python"))

from urusilla_sdk import ArtifactCache, UrusillaSDK, canonical_json_bytes  # noqa: E402
from urusilla_sdk.sdk import CAPSULE_SHA256, JSON_REPRESENTATION  # noqa: E402


SOURCE_PYTHON = "11111111111111111111111111111111"
SOURCE_NODE = "22222222222222222222222222222222"


def _session_for_node(session: Any) -> dict[str, Any]:
    return {
        "mode": session.mode,
        "representation": session.representation,
        "peer_source_id": session.local_source_id,
        "peer_language_version": "0.1.0",
        "peer_capsule_sha256": CAPSULE_SHA256,
        "pins_compatible": session.pins_compatible,
        "fallback_reason": session.fallback_reason,
    }


class LocalNodeAgent:
    def __init__(self) -> None:
        self.process = subprocess.Popen(
            ["node", str(KIT_ROOT / "node" / "src" / "agent.js")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def call(self, request: dict[str, Any]) -> Any:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("local Node stdio was not created")
        self.process.stdin.write(canonical_json_bytes(request) + b"\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("local Node agent closed stdout")
        response = json.loads(line)
        if response.get("ok") is not True:
            raise RuntimeError(f"local Node agent rejected request: {response.get('error')}")
        return response["result"]

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        status = self.process.wait(timeout=5)
        if status != 0:
            detail = self.process.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"local Node agent exited {status}: {detail}")


def main() -> int:
    request_message = json.loads(
        (KIT_ROOT / "fixtures" / "request.json").read_text(encoding="utf-8")
    )
    response_message = json.loads(
        (KIT_ROOT / "fixtures" / "response.json").read_text(encoding="utf-8")
    )
    python_agent = UrusillaSDK(
        source_id=SOURCE_PYTHON,
        cache=ArtifactCache((CAPSULE_SHA256,)),
    )
    node = LocalNodeAgent()
    try:
        node_capability = node.call(
            {
                "op": "discover",
                "source_id": SOURCE_NODE,
                "cached_artifacts": [CAPSULE_SHA256],
            }
        )
        python_capability = python_agent.discover_capabilities()

        outbound = python_agent.negotiate(
            node_capability,
            request_message,
            preferred_representation=JSON_REPRESENTATION,
        )
        request_delivery = python_agent.encode_delivery(request_message, outbound)
        node_decoded = node.call(
            {
                "op": "decode",
                "source_id": SOURCE_NODE,
                "cached_artifacts": [CAPSULE_SHA256],
                "expected_source_id": SOURCE_PYTHON,
                "session": _session_for_node(outbound),
                "delivery": request_delivery.envelope,
            }
        )

        response_envelope = node.call(
            {
                "op": "encode",
                "source_id": SOURCE_NODE,
                "cached_artifacts": [CAPSULE_SHA256],
                "peer_capability": python_capability,
                "requested_mode": "bridge",
                "preferred_representation": JSON_REPRESENTATION,
                "message": response_message,
            }
        )
        inbound = python_agent.negotiate(
            node_capability,
            response_message,
            preferred_representation=JSON_REPRESENTATION,
        )
        python_decoded = python_agent.decode_delivery(response_envelope, inbound)
    finally:
        node.close()

    expected_request = python_agent.normalize_input(request_message, mode="fallback")
    expected_response = python_agent.normalize_input(response_message, mode="fallback")
    result = {
        "product_label": python_capability["product_label"],
        "transport": "local-stdio-jsonl",
        "network_io": False,
        "representation": JSON_REPRESENTATION,
        "python_to_node_exact": node_decoded["message"] == expected_request,
        "node_to_python_exact": python_decoded.message == expected_response,
        "python_source_id_preserved": node_decoded["source_id"] == SOURCE_PYTHON,
        "node_source_id_preserved": python_decoded.source_id == SOURCE_NODE,
        "effect_authorized": (
            node_decoded["effect_authorized"] or python_decoded.effect_authorized
        ),
        "request_delivery_sha256": hashlib.sha256(
            canonical_json_bytes(request_delivery.envelope)
        ).hexdigest(),
        "response_delivery_sha256": hashlib.sha256(
            canonical_json_bytes(response_envelope)
        ).hexdigest(),
        "evidence_scope": (
            "project-authored local structural cross-play; not an unseen partner, "
            "task-success result, or external-adoption claim"
        ),
    }
    sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
