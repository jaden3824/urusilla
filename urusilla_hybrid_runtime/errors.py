"""Named error classes for hybrid sender, routing, and receiver failures."""

from __future__ import annotations

from .canonical import HybridRuntimeError


class CapsuleError(HybridRuntimeError):
    pass


class ActionStateError(HybridRuntimeError):
    pass


class TaskContextError(HybridRuntimeError):
    pass


class SenderError(HybridRuntimeError):
    pass


class RoutingError(HybridRuntimeError):
    pass


class ReceiverError(HybridRuntimeError):
    pass


class SurfaceError(HybridRuntimeError):
    pass
