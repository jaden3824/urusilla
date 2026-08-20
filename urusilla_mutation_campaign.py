#!/usr/bin/env python3
"""Deterministic cross-codec and corruption mutation campaign.

This is a bounded mutation campaign, not coverage-guided fuzzing.  It checks
four independently shaped representations against the same canonical semantic
messages, perturbs complete encoded artifacts without recomputing integrity
fields, and requires every perturbation to fail closed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import random
from typing import Any, Callable, Mapping

from urusilla_benchmark import build_corpus, corpus_digest
from urusilla import (
    DecodeError,
    ValidationError,
    decode_message as decode_reference,
    encode_message as encode_reference,
    normalize_message,
)
from urusilla_wire_v02 import decode_message as decode_v02
from urusilla_wire_v02 import encode_message as encode_v02
from urusilla_terse_english_benchmark import (
    decode_terse_english,
    encode_terse_english,
)
from urusilla_token_surface_v04 import decode_message as decode_v04
from urusilla_token_surface_v04 import encode_message as encode_v04
from urusilla_adaptive_surface_v05 import (
    decode_message as decode_adaptive,
    encode_envelope,
    holdout_codebook,
)


FORMAT = "urusilla-mutation-campaign-v1"
DEFAULT_SEED = 0xA61E_2026_0820
DEFAULT_MUTATIONS_PER_MESSAGE = 8
EXPECTED_CORPUS_SHA256 = (
    "61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc"
)

Encoded = bytes | str
Encoder = Callable[[Mapping[str, Any]], Encoded]
Decoder = Callable[[Encoded], dict[str, Any]]


@dataclass(frozen=True)
class Codec:
    name: str
    encode: Encoder
    decode: Decoder
    integrity_required: bool


def _v04_codec() -> Codec:
    codebook = holdout_codebook()
    return Codec(
        "token_surface_v04",
        lambda message: encode_v04(message, codebook),
        lambda surface: decode_v04(surface, codebook),  # type: ignore[arg-type]
        True,
    )


def codecs() -> tuple[Codec, ...]:
    return (
        Codec(
            "reference_wire",
            encode_reference,
            lambda frame: decode_reference(frame),  # type: ignore[arg-type]
            True,
        ),
        Codec(
            "static_profile_wire",
            encode_v02,
            lambda frame: decode_v02(frame),  # type: ignore[arg-type]
            True,
        ),
        Codec(
            "controlled_terse_english",
            encode_terse_english,
            lambda text: decode_terse_english(text),  # type: ignore[arg-type]
            False,
        ),
        Codec(
            "controlled_terse_envelope",
            lambda message: encode_envelope("E", encode_terse_english(message)),
            lambda text: decode_adaptive(text),  # type: ignore[arg-type]
            True,
        ),
        _v04_codec(),
    )


def _reordered(value: Any, rng: random.Random) -> Any:
    if isinstance(value, dict):
        keys = list(value)
        rng.shuffle(keys)
        return {key: _reordered(value[key], rng) for key in keys}
    if isinstance(value, list):
        return [_reordered(item, rng) for item in value]
    return value


def _mutate_bytes(value: bytes, operation: int, rng: random.Random) -> bytes:
    if not value:
        return b"!"
    position = rng.randrange(len(value))
    if operation == 0:
        changed = value[position] ^ (1 << rng.randrange(8))
        return value[:position] + bytes([changed]) + value[position + 1 :]
    if operation == 1:
        changed = (value[position] + 1 + rng.randrange(255)) & 0xFF
        return value[:position] + bytes([changed]) + value[position + 1 :]
    if operation == 2:
        return value[:position] + value[position + 1 :]
    if operation == 3:
        return value[:position] + bytes([rng.randrange(256)]) + value[position:]
    if operation == 4:
        return value + bytes([rng.randrange(256)])
    if operation == 5:
        return value[:position]
    if operation == 6:
        return bytes([rng.randrange(256)]) + value
    changed = value[position] ^ 0x80
    return value[:position] + bytes([changed]) + value[position + 1 :]


def _mutate_text(value: str, operation: int, rng: random.Random) -> str:
    if not value:
        return "!"
    position = rng.randrange(len(value))
    replacement = "!" if value[position] != "!" else "?"
    if operation == 0:
        return value[:position] + replacement + value[position + 1 :]
    if operation == 1:
        return value[:position] + value[position + 1 :]
    if operation == 2:
        return value[:position] + "!" + value[position:]
    if operation == 3:
        return value + "!"
    if operation == 4 and len(value) > 1:
        other = position + 1 if position + 1 < len(value) else position - 1
        chars = list(value)
        chars[position], chars[other] = chars[other], chars[position]
        mutated = "".join(chars)
        if mutated != value:
            return mutated
        return value[:position] + replacement + value[position + 1 :]
    if operation == 5:
        return value[:position]
    if operation == 6:
        return "!" + value
    return value[:position] + "~" + value[position + 1 :]


def mutate(value: Encoded, operation: int, rng: random.Random) -> Encoded:
    if isinstance(value, bytes):
        result: Encoded = _mutate_bytes(value, operation, rng)
    elif isinstance(value, str):
        result = _mutate_text(value, operation, rng)
    else:
        raise TypeError("encoded artifact must be bytes or text")
    if result == value:
        raise RuntimeError("mutation unexpectedly preserved the encoded artifact")
    return result


def _artifact_bytes(value: Encoded) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")


def run_campaign(
    *,
    seed: int = DEFAULT_SEED,
    mutations_per_message: int = DEFAULT_MUTATIONS_PER_MESSAGE,
) -> dict[str, Any]:
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if type(mutations_per_message) is not int or not 1 <= mutations_per_message <= 64:
        raise ValueError("mutations_per_message must be in [1, 64]")

    messages = tuple(build_corpus())
    if corpus_digest(messages) != EXPECTED_CORPUS_SHA256:
        raise RuntimeError("frozen corpus digest changed")
    available = codecs()
    rng = random.Random(seed)
    mutation_digest = hashlib.sha256()
    encoded_digest = hashlib.sha256()
    rejection_counts = {codec.name: 0 for codec in available}
    accepted_mutation_counts = {codec.name: 0 for codec in available}
    exception_counts: dict[str, int] = {}
    exact_decodes = 0
    insertion_order_checks = 0
    mutation_attempts = 0

    for message_index, message in enumerate(messages):
        canonical = normalize_message(message)
        reordered = _reordered(message, rng)
        for codec in available:
            encoded = codec.encode(message)
            encoded_reordered = codec.encode(reordered)
            if encoded_reordered != encoded:
                raise AssertionError(
                    f"{codec.name} changed under map insertion order at message {message_index}"
                )
            insertion_order_checks += 1
            decoded = codec.decode(encoded)
            if decoded != canonical:
                raise AssertionError(
                    f"{codec.name} semantic mismatch at message {message_index}"
                )
            if codec.encode(decoded) != encoded:
                raise AssertionError(
                    f"{codec.name} non-deterministic re-encode at message {message_index}"
                )
            exact_decodes += 1
            raw = _artifact_bytes(encoded)
            encoded_digest.update(codec.name.encode("ascii") + b"\x00")
            encoded_digest.update(len(raw).to_bytes(8, "big") + raw)

            for mutation_index in range(mutations_per_message):
                operation = mutation_index % 8
                mutated = mutate(encoded, operation, rng)
                mutation_raw = _artifact_bytes(mutated)
                mutation_digest.update(codec.name.encode("ascii") + b"\x00")
                mutation_digest.update(message_index.to_bytes(4, "big"))
                mutation_digest.update(mutation_index.to_bytes(2, "big"))
                mutation_digest.update(len(mutation_raw).to_bytes(8, "big"))
                mutation_digest.update(mutation_raw)
                mutation_attempts += 1
                try:
                    mutated_message = codec.decode(mutated)
                except (DecodeError, ValidationError) as exc:
                    rejection_counts[codec.name] += 1
                    key = f"{codec.name}:{type(exc).__name__}"
                    exception_counts[key] = exception_counts.get(key, 0) + 1
                else:
                    if codec.integrity_required:
                        raise AssertionError(
                            f"{codec.name} accepted integrity-protected mutation "
                            f"{mutation_index} for message {message_index}"
                        )
                    mutated_canonical = normalize_message(mutated_message)
                    if mutated_canonical == canonical:
                        raise AssertionError(
                            f"{codec.name} accepted an alternative spelling for the "
                            f"same semantics at message {message_index}"
                        )
                    if codec.encode(mutated_canonical) != mutated:
                        raise AssertionError(
                            f"{codec.name} accepted a non-canonical mutation at "
                            f"message {message_index}"
                        )
                    accepted_mutation_counts[codec.name] += 1

    return {
        "format": FORMAT,
        "seed": seed,
        "messages": len(messages),
        "codecs": [codec.name for codec in available],
        "mutations_per_message_codec": mutations_per_message,
        "exact_decodes": exact_decodes,
        "insertion_order_checks": insertion_order_checks,
        "mutation_attempts": mutation_attempts,
        "mutation_rejections": sum(rejection_counts.values()),
        "canonical_semantic_mutations_accepted": sum(
            accepted_mutation_counts.values()
        ),
        "rejections_by_codec": rejection_counts,
        "accepted_mutations_by_codec": accepted_mutation_counts,
        "exception_counts": dict(sorted(exception_counts.items())),
        "encoded_sequence_sha256": encoded_digest.hexdigest(),
        "mutation_sequence_sha256": mutation_digest.hexdigest(),
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--mutations-per-message",
        type=int,
        default=DEFAULT_MUTATIONS_PER_MESSAGE,
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run_campaign(
                seed=args.seed,
                mutations_per_message=args.mutations_per_message,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
