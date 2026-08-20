"""Offline-first public-task evaluation harness.

This package is intentionally isolated from the repository's existing files.
It reads frozen A0 artifacts but never mutates them.  No provider adapter that
can perform a network call is included in this package.
"""

from .config import HARNESS_FORMAT, HARNESS_VERSION

__all__ = ["HARNESS_FORMAT", "HARNESS_VERSION"]

