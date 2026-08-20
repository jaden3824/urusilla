#!/usr/bin/env python3
"""Run one decoder QA campaign inside fixed local resource limits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import resource
import sys
import threading
import time
import traceback
from typing import Any


CPU_SECONDS = 25
ADDRESS_SPACE_BYTES = 1_073_741_824
DATA_BYTES = 536_870_912
RSS_WATCHDOG_BYTES = 536_870_912
FILE_BYTES = 1_048_576
OPEN_FILES = 64
RESULT_PREFIX = "DECODER_QA_RESULT="
ROOT = Path(__file__).resolve().parents[1]


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _start_rss_watchdog() -> tuple[threading.Event, threading.Thread]:
    stopped = threading.Event()

    def monitor() -> None:
        while not stopped.wait(0.025):
            if _peak_rss_bytes() > RSS_WATCHDOG_BYTES:
                os._exit(71)

    thread = threading.Thread(target=monitor, name="decoder-qa-rss-watchdog", daemon=True)
    thread.start()
    return stopped, thread


def _bounded_limit(kind: int, requested: int) -> tuple[int, int]:
    _soft, hard = resource.getrlimit(kind)
    bounded_soft = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (bounded_soft, hard))
    return resource.getrlimit(kind)


def _install_limits() -> dict[str, Any]:
    applied: dict[str, Any] = {}
    requested = {
        "cpu_seconds": (resource.RLIMIT_CPU, CPU_SECONDS),
        "address_space_bytes": (resource.RLIMIT_AS, ADDRESS_SPACE_BYTES),
        "data_bytes": (resource.RLIMIT_DATA, DATA_BYTES),
        "file_bytes": (resource.RLIMIT_FSIZE, FILE_BYTES),
        "open_files": (resource.RLIMIT_NOFILE, OPEN_FILES),
    }
    if hasattr(resource, "RLIMIT_RSS"):
        requested["resident_set_bytes"] = (resource.RLIMIT_RSS, DATA_BYTES)
    for name, (kind, value) in requested.items():
        try:
            soft, hard = _bounded_limit(kind, value)
            applied[name] = {
                "requested": value,
                "soft": soft,
                "hard": hard,
                "status": "applied",
            }
        except (OSError, ValueError) as exc:
            applied[name] = {
                "requested": value,
                "status": "unavailable",
                "reason": f"{type(exc).__name__}: {exc}",
            }
    return applied


def _deny_network(event: str, _arguments: tuple[Any, ...]) -> None:
    if event in {
        "socket.bind",
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyaddr",
        "socket.gethostbyname",
        "socket.gethostbyname_ex",
    }:
        raise RuntimeError(f"decoder QA forbids network audit event: {event}")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: qa_worker.py CAMPAIGN", file=sys.stderr)
        return 2

    limits = _install_limits()
    limits["rss_watchdog_bytes"] = {
        "requested": RSS_WATCHDOG_BYTES,
        "sample_interval_seconds": 0.025,
        "status": "applied",
    }
    watchdog_stopped, watchdog_thread = _start_rss_watchdog()
    sys.addaudithook(_deny_network)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    started = time.monotonic()
    try:
        from decoder_qa.qa_core import run_campaign

        result = run_campaign(arguments[0])
        exit_code = 0 if result.get("status") in {"passed", "findings"} else 1
    except BaseException as exc:
        result = {
            "name": arguments[0],
            "status": "error",
            "exception": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=20),
        }
        exit_code = 1

    watchdog_stopped.set()
    watchdog_thread.join(timeout=0.1)
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    result["peak_rss_bytes"] = _peak_rss_bytes()
    result["resource_limits"] = limits
    result["network_policy"] = "socket connect, bind, and name-resolution audit events denied"
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
