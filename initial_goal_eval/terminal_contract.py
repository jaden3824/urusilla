"""Lightweight terminal-state constants shared by evidence validators.

This module deliberately depends only on the packaged initial-goal contract.
Provider replay adapters live outside the installable wheel, so importing the
receipt verifier must not pull those research-only modules into the runtime.
"""

from __future__ import annotations

from .contract import sha256_ref


CAPTURE_TERMINAL_STATUSES = (
    "completed",
    "timeout",
    "refused",
    "provider_error",
)
SILENCE_TERMINAL_STATUS = "silenced"
CANONICAL_SILENCE_OUTPUT_SHA256 = sha256_ref(
    {
        "schema_version": "urusilla-initial-goal-canonical-silence-output/1",
        "selected_mode": "silence",
        "receiver_output": None,
    }
)


__all__ = [
    "CANONICAL_SILENCE_OUTPUT_SHA256",
    "CAPTURE_TERMINAL_STATUSES",
    "SILENCE_TERMINAL_STATUS",
]
