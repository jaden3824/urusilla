"""Provider-free command line interface for verification and dry runs."""

from __future__ import annotations

import argparse

from .canonical import canonical_json
from .manifests import (
    manifest_lock_summary,
    verify_frozen_inputs,
    verify_public_digest_inventory,
)
from .report import generate_dry_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="competitive-eval",
        description="Offline-only public-task evaluation harness",
    )
    parser.add_argument(
        "command", choices=("verify", "verify-public", "verify-local", "dry-run")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    command = build_parser().parse_args(argv).command
    if command in {"verify", "verify-public"}:
        print(canonical_json(verify_public_digest_inventory()))
        return 0
    if command == "verify-local":
        print(canonical_json(manifest_lock_summary(verify_frozen_inputs())))
        return 0
    result = generate_dry_run()
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
