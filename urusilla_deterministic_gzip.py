#!/usr/bin/env python3
"""Deterministic gzip member construction for reproducible artifacts.

``gzip.compress(..., mtime=0)`` emitted a platform-specific OS header byte in
some supported Python versions. ``GzipFile`` uses the canonical unknown-OS
value while preserving a standard gzip payload and checksum.
"""

from __future__ import annotations

import gzip
import io


def compress(data: bytes, *, compresslevel: int = 9) -> bytes:
    """Return one gzip member with empty filename, zero time, and OS=unknown."""

    if not isinstance(data, bytes):
        raise TypeError("deterministic gzip input must be bytes")
    if type(compresslevel) is not int or not 0 <= compresslevel <= 9:
        raise ValueError("gzip compresslevel must be an integer from 0 to 9")
    output = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=compresslevel,
        fileobj=output,
        mtime=0,
    ) as stream:
        stream.write(data)
    member = output.getvalue()
    if len(member) < 18 or member[:4] != b"\x1f\x8b\x08\x00":
        raise RuntimeError("unexpected gzip encoder output")
    if member[4:8] != b"\x00\x00\x00\x00" or member[9] != 255:
        raise RuntimeError("gzip header is not canonical")
    return member
