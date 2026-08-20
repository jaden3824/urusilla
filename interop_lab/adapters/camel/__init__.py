"""Offline-first CAMEL-AI adapter for the Urusilla Interop Lab."""

from .adapter import (
    ARM_IDS,
    CAMEL_REQUIREMENT,
    MCP_REQUIREMENT,
    CamelAdapterError,
    build_plan,
    map_capture_to_interop_record,
    offline_preflight,
    run_camel_trial,
    validate_capture,
    validate_plan,
)

__all__ = [
    "ARM_IDS",
    "CAMEL_REQUIREMENT",
    "MCP_REQUIREMENT",
    "CamelAdapterError",
    "build_plan",
    "map_capture_to_interop_record",
    "offline_preflight",
    "run_camel_trial",
    "validate_capture",
    "validate_plan",
]
