#!/usr/bin/env python3
"""Reproducible tokenizer accounting for text-carried Urusilla serializations.

This study measures how public tokenizer vocabularies segment three already-
structured representations of the same fixed 280-message UrusillaIR corpus:

* sorted, minified UTF-8 UrusillaIR JSON;
* Base64 text carrying one UrusillaWire v0.1 frame per message; and
* Base64 text carrying one warm UrusillaWire v0.2 frame per message.

Raw binary is never passed to a tokenizer.  The v0.2 profile capsule is counted
separately as one Base64 text transfer.  This is serialization accounting, not
an end-to-end language-model benchmark and not a comparison with equivalent
natural-language messages.

Benchmark dependency pins:

    tiktoken==0.11.0
    tokenizers==0.21.4

The two open-model tokenizer.json files are fetched from immutable official
model-repository revisions and verified against SHA-256 constants below.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib.request import Request, urlopen

from urusilla_benchmark import build_corpus, corpus_digest, json_encode
from urusilla import decode_message as decode_v01
from urusilla import encode_message as encode_v01
from urusilla_wire_v02 import DEFAULT_PROFILE, DEFAULT_REGISTRY
from urusilla_wire_v02 import decode_message as decode_v02
from urusilla_wire_v02 import encode_capsule
from urusilla_wire_v02 import encode_message as encode_v02


MESSAGE_COUNT = 280
TIKTOKEN_VERSION = "0.11.0"
TOKENIZERS_VERSION = "0.21.4"


@dataclass(frozen=True)
class OpenTokenizerSpec:
    key: str
    display_name: str
    repository: str
    revision: str
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return (
            f"https://huggingface.co/{self.repository}/resolve/"
            f"{self.revision}/{self.filename}?download=true"
        )


OPEN_TOKENIZERS = (
    OpenTokenizerSpec(
        key="qwen2_5_7b_instruct",
        display_name="Qwen2.5-7B-Instruct tokenizer",
        repository="Qwen/Qwen2.5-7B-Instruct",
        revision="a09a35458c702b33eeacc393d103063234e8bc28",
        filename="tokenizer.json",
        sha256="c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    ),
    OpenTokenizerSpec(
        key="mistral_7b_instruct_v03",
        display_name="Mistral-7B-Instruct-v0.3 tokenizer",
        repository="mistralai/Mistral-7B-Instruct-v0.3",
        revision="c170c708c41dac9275d15a8fff4eca08d52bab71",
        filename="tokenizer.json",
        sha256="e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
    ),
)


@dataclass(frozen=True)
class Serialization:
    key: str
    display_name: str
    texts: tuple[str, ...]
    raw_binary_bytes: int | None

    @property
    def text_codepoints(self) -> int:
        return sum(len(text) for text in self.texts)

    @property
    def text_utf8_bytes(self) -> int:
        return sum(len(text.encode("utf-8")) for text in self.texts)

    @property
    def digest(self) -> str:
        digest = hashlib.sha256()
        for text in self.texts:
            raw = text.encode("utf-8")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
        return digest.hexdigest()


@dataclass(frozen=True)
class TokenizerProfile:
    key: str
    display_name: str
    implementation: str
    vocabulary_size: int
    fingerprint: str
    count: Callable[[str], int]


@dataclass(frozen=True)
class TokenResult:
    profile: TokenizerProfile
    totals: Mapping[str, int]
    capsule_tokens: int


def default_asset_root() -> Path:
    """Return a non-published research-cache location for tokenizer assets."""

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent if script_dir.name == "outputs" else script_dir
    return project_root / "work" / "tokenizer_assets"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest(path: Path) -> str:
    return sha256_file(path.resolve())


def _base64_text(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def build_serializations(
    count: int = MESSAGE_COUNT,
) -> tuple[list[dict[str, Any]], dict[str, Serialization], str]:
    """Build and verify the three text representations and one cold capsule."""

    corpus = build_corpus(count)
    json_texts: list[str] = []
    v01_texts: list[str] = []
    v02_texts: list[str] = []
    v01_raw_bytes = 0
    v02_raw_bytes = 0

    for message in corpus:
        json_texts.append(json_encode(message).decode("utf-8"))

        frame_v01 = encode_v01(message)
        if decode_v01(frame_v01) != message:
            raise AssertionError("v0.1 semantic round-trip changed a corpus message")
        v01_raw_bytes += len(frame_v01)
        v01_texts.append(_base64_text(frame_v01))

        frame_v02 = encode_v02(message, DEFAULT_PROFILE)
        if decode_v02(frame_v02, DEFAULT_REGISTRY) != message:
            raise AssertionError("v0.2 semantic round-trip changed a corpus message")
        v02_raw_bytes += len(frame_v02)
        v02_texts.append(_base64_text(frame_v02))

    serializations = {
        "json": Serialization(
            "json",
            "Sorted minified UrusillaIR JSON",
            tuple(json_texts),
            sum(len(json_encode(message)) for message in corpus),
        ),
        "base64_v01": Serialization(
            "base64_v01",
            "Base64 UrusillaWire v0.1",
            tuple(v01_texts),
            v01_raw_bytes,
        ),
        "base64_v02_warm": Serialization(
            "base64_v02_warm",
            "Base64 UrusillaWire v0.2 warm",
            tuple(v02_texts),
            v02_raw_bytes,
        ),
    }
    capsule_text = _base64_text(encode_capsule(DEFAULT_PROFILE))
    return corpus, serializations, capsule_text


def download_open_tokenizers(asset_root: Path) -> None:
    """Fetch exact official tokenizer assets and fail closed on digest mismatch."""

    for spec in OPEN_TOKENIZERS:
        target = asset_root / spec.key / spec.filename
        if target.is_file() and sha256_file(target) == spec.sha256:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        request = Request(spec.url, headers={"User-Agent": "urusilla-token-study/0.1"})
        with urlopen(request, timeout=120) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != spec.sha256:
            raise RuntimeError(
                f"digest mismatch for {spec.display_name}: expected {spec.sha256}, got {actual}"
            )
        temporary = target.with_suffix(target.suffix + ".download")
        temporary.write_bytes(data)
        temporary.replace(target)


def _require_version(distribution: str, expected: str) -> str:
    try:
        actual = metadata.version(distribution)
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"missing benchmark dependency: install {distribution}=={expected}"
        ) from exc
    if actual != expected:
        raise RuntimeError(
            f"{distribution} version must be {expected} for this report; found {actual}"
        )
    return actual


def tiktoken_fingerprint(encoding: Any) -> str:
    """Fingerprint the exact regex, merge ranks, and special-token mapping."""

    digest = hashlib.sha256()
    pattern = encoding._pat_str.encode("utf-8")
    digest.update(len(pattern).to_bytes(8, "big"))
    digest.update(pattern)
    for token, rank in sorted(
        encoding._mergeable_ranks.items(), key=lambda item: (item[1], item[0])
    ):
        digest.update(len(token).to_bytes(4, "big"))
        digest.update(token)
        digest.update(rank.to_bytes(8, "big"))
    for token, rank in sorted(encoding._special_tokens.items()):
        raw = token.encode("utf-8")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
        digest.update(rank.to_bytes(8, "big"))
    return digest.hexdigest()


def load_tokenizer_profiles(asset_root: Path) -> tuple[TokenizerProfile, ...]:
    """Load exactly pinned tokenizer implementations and verified vocabularies."""

    _require_version("tiktoken", TIKTOKEN_VERSION)
    _require_version("tokenizers", TOKENIZERS_VERSION)
    try:
        import tiktoken
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise RuntimeError("pinned tokenizer dependencies are not importable") from exc

    profiles: list[TokenizerProfile] = []
    for encoding_name in ("cl100k_base", "o200k_base"):
        encoding = tiktoken.get_encoding(encoding_name)

        def count_tiktoken(text: str, *, _encoding: Any = encoding) -> int:
            return len(
                _encoding.encode(
                    text,
                    allowed_special=set(),
                    disallowed_special=(),
                )
            )

        profiles.append(
            TokenizerProfile(
                key=encoding_name,
                display_name=encoding_name,
                implementation=f"tiktoken {TIKTOKEN_VERSION}",
                vocabulary_size=encoding.n_vocab,
                fingerprint=tiktoken_fingerprint(encoding),
                count=count_tiktoken,
            )
        )

    for spec in OPEN_TOKENIZERS:
        path = asset_root / spec.key / spec.filename
        if not path.is_file():
            raise RuntimeError(
                f"missing {path}; run this script once with --download-assets"
            )
        actual = sha256_file(path)
        if actual != spec.sha256:
            raise RuntimeError(
                f"digest mismatch for {path}: expected {spec.sha256}, got {actual}"
            )
        tokenizer = Tokenizer.from_file(str(path))

        def count_tokenizers(text: str, *, _tokenizer: Any = tokenizer) -> int:
            return len(_tokenizer.encode(text, add_special_tokens=False).ids)

        profiles.append(
            TokenizerProfile(
                key=spec.key,
                display_name=spec.display_name,
                implementation=f"tokenizers {TOKENIZERS_VERSION}",
                vocabulary_size=tokenizer.get_vocab_size(with_added_tokens=True),
                fingerprint=actual,
                count=count_tokenizers,
            )
        )
    return tuple(profiles)


def measure_tokens(
    profiles: Sequence[TokenizerProfile],
    serializations: Mapping[str, Serialization],
    capsule_text: str,
) -> tuple[TokenResult, ...]:
    """Count each independently framed message without BOS/EOS or chat templates."""

    results: list[TokenResult] = []
    for profile in profiles:
        totals = {
            key: sum(profile.count(text) for text in serialization.texts)
            for key, serialization in serializations.items()
        }
        results.append(
            TokenResult(
                profile=profile,
                totals=totals,
                capsule_tokens=profile.count(capsule_text),
            )
        )
    return tuple(results)


def saved_percent(candidate: int, baseline: int) -> float:
    return 100.0 * (1.0 - candidate / baseline)


def _break_even_messages(result: TokenResult, message_count: int) -> int | None:
    average_saving = (
        result.totals["json"] - result.totals["base64_v02_warm"]
    ) / message_count
    if average_saving <= 0:
        return None
    return int(result.capsule_tokens // average_saving) + 1


def render_report(
    corpus: Sequence[Mapping[str, Any]],
    serializations: Mapping[str, Serialization],
    capsule_text: str,
    results: Sequence[TokenResult],
    asset_root: Path,
) -> str:
    json_bytes = serializations["json"].text_utf8_bytes
    warm_savings = [
        saved_percent(result.totals["base64_v02_warm"], result.totals["json"])
        for result in results
    ]
    session_savings = [
        saved_percent(
            result.totals["base64_v02_warm"] + result.capsule_tokens,
            result.totals["json"],
        )
        for result in results
    ]
    v01_savings = [
        saved_percent(result.totals["base64_v01"], result.totals["json"])
        for result in results
    ]
    capsule_raw = encode_capsule(DEFAULT_PROFILE)
    script_dir = Path(__file__).resolve().parent
    source_files = (
        "urusilla_tokenizer_benchmark.py",
        "test_urusilla_tokenizer_benchmark.py",
        "urusilla_benchmark.py",
        "urusilla.py",
        "urusilla_wire_v02.py",
    )

    lines = [
        "# Urusilla serialization tokenizer accounting study",
        "",
        "## Result",
        "",
        f"Across the four pinned tokenizer profiles, warm Base64 UrusillaWire v0.2 used "
        f"**{min(warm_savings):.1f}% to {max(warm_savings):.1f}% fewer tokens** than sorted "
        f"minified UrusillaIR JSON on the fixed {len(corpus)}-message corpus. Counting the Base64 "
        f"profile capsule once changed the range to **{min(session_savings):.1f}% to "
        f"{max(session_savings):.1f}% fewer tokens**. In contrast, Base64 UrusillaWire v0.1 used "
        f"**{-max(v01_savings):.1f}% to {-min(v01_savings):.1f}% more tokens** than JSON.",
        "",
        "The favorable v0.2 result is an **in-sample, warm-profile upper bound**. Its static "
        "profile was manually built around this benchmark vocabulary and map shapes. These "
        "numbers measure serialization tokenization only. They do not measure task success, "
        "model understanding, reasoning quality, translation cost, generation latency, or total "
        "application tokens. They are not a comparison with semantically equivalent natural-"
        "language messages; no terse-English baseline was constructed.",
        "",
        "## Exact token counts",
        "",
        "Each message was tokenized separately, matching its framing boundary. Counts exclude "
        "BOS/EOS tokens, role markers, chat templates, HTTP/A2A envelopes, and prompts. No raw "
        "binary was treated as text: both wire formats were represented by standard padded "
        "Base64 ASCII.",
        "",
        "| Tokenizer | JSON tokens | Base64 v0.1 | Saved vs JSON | Base64 warm v0.2 | Saved vs JSON | + one capsule | Saved vs JSON |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        json_tokens = result.totals["json"]
        v01_tokens = result.totals["base64_v01"]
        v02_tokens = result.totals["base64_v02_warm"]
        session_tokens = v02_tokens + result.capsule_tokens
        lines.append(
            f"| {result.profile.display_name} | {json_tokens:,} | {v01_tokens:,} | "
            f"{saved_percent(v01_tokens, json_tokens):+.1f}% | {v02_tokens:,} | "
            f"{saved_percent(v02_tokens, json_tokens):+.1f}% | {session_tokens:,} | "
            f"{saved_percent(session_tokens, json_tokens):+.1f}% |"
        )

    lines.extend(
        [
            "",
            "A positive `Saved vs JSON` value means fewer tokens. A negative value means the "
            "candidate used more tokens. Base64 v0.1 is a useful negative result: although its "
            "binary frame is smaller than JSON in bytes, Base64 fragments are poorly aligned "
            "with these tokenizer vocabularies.",
            "",
            "## One-time v0.2 profile cost",
            "",
            f"The canonical v0.2 profile capsule is `{len(capsule_raw):,}` binary bytes, "
            f"`{len(capsule_text):,}` Base64 characters, SHA-256 "
            f"`{hashlib.sha256(capsule_raw).hexdigest()}`, and dictionary ID "
            f"`{DEFAULT_PROFILE.dictionary_id_hex}`.",
            "",
            "| Tokenizer | Capsule tokens | Mean-corpus break-even |",
            "|---|---:|---:|",
        ]
    )
    for result in results:
        break_even = _break_even_messages(result, len(corpus))
        break_even_text = "not reached" if break_even is None else f"{break_even} messages"
        lines.append(
            f"| {result.profile.display_name} | {result.capsule_tokens:,} | {break_even_text} |"
        )

    lines.extend(
        [
            "",
            "Break-even divides the one-time capsule token count by the mean per-message token "
            "saving observed on this same corpus, then rounds to the first whole message that "
            "exceeds the capsule cost. It is not a held-out estimate.",
            "",
            "## Text and byte accounting",
            "",
            "| Representation | Messages | Text code points | UTF-8 text bytes | Underlying binary bytes | Text bytes saved vs JSON | Serialization digest |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for serialization in serializations.values():
        raw = (
            "n/a"
            if serialization.raw_binary_bytes is None
            else f"{serialization.raw_binary_bytes:,}"
        )
        byte_saving = saved_percent(serialization.text_utf8_bytes, json_bytes)
        lines.append(
            f"| {serialization.display_name} | {len(serialization.texts)} | "
            f"{serialization.text_codepoints:,} | {serialization.text_utf8_bytes:,} | "
            f"{raw} | {byte_saving:+.1f}% | `{serialization.digest}` |"
        )

    lines.extend(
        [
            "",
            "The serialization digest is SHA-256 over every message's 8-byte big-endian UTF-8 "
            "length followed by its exact UTF-8 text. The JSON representation is the current "
            "CPython `json.dumps` path with `sort_keys=True`, compact separators, UTF-8 output, "
            "and non-ASCII characters left unescaped. It is deterministic for this fixed runtime "
            "and corpus, but it is not claimed to implement an independent cross-runtime JSON "
            "canonicalization standard.",
            "",
            "## Corpus and exactness",
            "",
            f"- Corpus version: `urusilla-benchmark-corpus-v1`",
            f"- Message count: `{len(corpus)}`",
            f"- Length-prefixed canonical corpus SHA-256: `{corpus_digest(corpus)}`",
            f"- UrusillaWire v0.1 semantic round-trip: `{len(corpus)}/{len(corpus)}`",
            f"- UrusillaWire v0.2 semantic round-trip: `{len(corpus)}/{len(corpus)}`",
            "",
            "The corpus already contains typed UrusillaIR objects. The study therefore excludes the "
            "tokens and errors involved in converting user language or model state into UrusillaIR.",
            "",
            "## Tokenizer provenance",
            "",
            f"Execution runtime: `{platform.python_implementation()} {platform.python_version()}` "
            f"on `{platform.platform()}`. Package pins were `tiktoken=={TIKTOKEN_VERSION}` and "
            f"`tokenizers=={TOKENIZERS_VERSION}`.",
            "",
            "| Profile | Implementation | Vocabulary size | Exact vocabulary fingerprint |",
            "|---|---|---:|---|",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.profile.display_name} | {result.profile.implementation} | "
            f"{result.profile.vocabulary_size:,} | `{result.profile.fingerprint}` |"
        )
    lines.extend(
        [
            "",
            "For tiktoken profiles, the fingerprint covers the regex pattern, ordered mergeable "
            "byte ranks, and special-token mapping. For open-model profiles it is the SHA-256 of "
            "the complete `tokenizer.json` file.",
            "",
            "Immutable open-model acquisitions:",
            "",
        ]
    )
    for spec in OPEN_TOKENIZERS:
        relative = Path("work") / "tokenizer_assets" / spec.key / spec.filename
        lines.append(
            f"- **{spec.display_name}:** official repository `{spec.repository}`, revision "
            f"`{spec.revision}`, file `{spec.filename}`, SHA-256 `{spec.sha256}`; measured local "
            f"cache path `{relative}`."
        )

    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "Create an isolated Python 3.12 environment, install the two exact dependency pins, "
            "then run:",
            "",
            "```text",
            "PYTHONPATH=. python urusilla_tokenizer_benchmark.py --download-assets",
            "PYTHONPATH=. python -m unittest test_urusilla_tokenizer_benchmark.py -v",
            "```",
            "",
            "The download step uses only immutable official model revisions and verifies each "
            "asset before use. Subsequent runs can be offline.",
            "",
            "Source SHA-256 values for this run:",
            "",
        ]
    )
    for name in source_files:
        path = script_dir / name
        if path.is_file():
            lines.append(f"- `{name}`: `{source_digest(path)}`")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Token count is tokenizer-dependent and does not by itself establish useful agent "
            "communication. A complete claim needs held-out schemas, equivalent natural-language "
            "baselines, task-success parity, model-side translation costs, latency, safety, and "
            "cross-model evaluation. The present result answers only: how many tokenizer units "
            "these exact text serializations occupy after a semantic object already exists.",
            "",
        ]
    )
    return "\n".join(lines)


def run(asset_root: Path) -> tuple[str, tuple[TokenResult, ...]]:
    corpus, serializations, capsule_text = build_serializations(MESSAGE_COUNT)
    profiles = load_tokenizer_profiles(asset_root)
    results = measure_tokens(profiles, serializations, capsule_text)
    return (
        render_report(corpus, serializations, capsule_text, results, asset_root),
        results,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=default_asset_root(),
        help="directory containing verified open-model tokenizer assets",
    )
    parser.add_argument(
        "--download-assets",
        action="store_true",
        help="fetch missing pinned assets before running the study",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("urusilla_tokenizer_results.md"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.download_assets:
        download_open_tokenizers(args.assets_dir)
    report, results = run(args.assets_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")
    for result in results:
        print(
            f"{result.profile.key}: json={result.totals['json']} "
            f"base64_v01={result.totals['base64_v01']} "
            f"base64_v02_warm={result.totals['base64_v02_warm']} "
            f"capsule={result.capsule_tokens}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
