# Receiver-negotiated token surface v0.7

This directory contains an offline experimental investigation of a receiver-specific token transport. It does not change the language, typed IR, v0.2 frame, or any root artifact.

## Scope

The experiment freezes all profile decisions from the exact ordered 223-message development partition. It then evaluates the unchanged 57-message grouped holdout and the existing ten-message out-of-domain set without tuning either one.

The original visible single-Unicode-code-point idea cannot supply the requested 1,024, 2,048, and 4,096 stable symbols for every pinned tokenizer. In particular, the pinned Mistral tokenizer has far fewer than 1,024 strict safe scalar candidates. The implemented profile is therefore an explicit experimental relaxation: each symbol is one tokenizer token whose decoded text is exactly one ASCII space followed by a nonempty ASCII alphanumeric body.

This boundary-token form is uniquely segmented at spaces and is checked against the exact receiver token IDs in isolation, in repeated and long concatenations, at the header and checksum boundaries, and for every emitted benchmark payload. Any mismatch makes the profile or message ineligible. The complete v0.6 choice remains the warm and cold fallback and wins ties.

## Mandatory decoder boundary

The raw `R7` text is decoder-before-model transport only. Tokenizer vocabulary strings may resemble natural-language words, directives, sensitive terms, or prompt fragments. A finite denylist removes direct role/control markers, common prompt directives, credential terms, and selected high-risk action terms, but it cannot prove arbitrary token sequences semantically inert.

Applications must decode, bind the full profile, verify the checksum and canonical form, recover the v0.2 frame, and validate the typed IR before model exposure. They must not place raw `R7` text in system, developer, user, tool, or retrieval context. Whitespace trimming, boundary removal, tab/newline/non-breaking-space replacement, and case rewriting are corruption and fail closed. No direct LLM readability or safe prompt consumption is claimed.

## Files

- `receiver_negotiated_surface_v07.py` derives profiles, implements exact encoding and decoding, runs the guarded chooser and cold planner, measures latency, and renders the frozen report.
- `test_receiver_negotiated_surface_v07.py` covers the derivation firewall, tokenizer and profile binding, Unicode and symbol policy, concatenation, canonicality, corruption, normalization, expansion bounds, break-even arithmetic, and fallback guards.
- `frozen_results.json` is the canonical machine-readable study snapshot. It includes every raw or guarded message/candidate record with a positive token or UTF-8-byte delta.
- `RECEIVER_NEGOTIATED_SURFACE_V07_RESULTS.md` is the English results report, including unfavorable outcomes and limitations.

## Offline reproduction

From the repository root, with the pinned local tokenizer assets already present. The exact cl100k and o200k rank blobs must already exist in tiktoken's cache; set `TIKTOKEN_CACHE_DIR` to an explicit verified cache directory when the default temporary cache is not stable. Missing or mismatched rank blobs fail before the tokenizer loader can attempt a network read.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv-research-py312/bin/python -m unittest performance_v07/test_receiver_negotiated_surface_v07.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv-research-py312/bin/python performance_v07/receiver_negotiated_surface_v07.py --benchmark --assets-dir work/tokenizer_assets --repeats 1
```

Both commands are offline. Missing packages, changed asset fingerprints, changed development ordering, changed profile capsules, or changed frozen metrics are rejected.

## Interpretation

The measurements concern serialization length under four pinned tokenizer implementations. They do not measure model comprehension, task success, prompt safety, generation reliability, energy, adoption, native model support, or state-of-the-art performance. A tokenizer or Unicode database change requires a new profile and new evidence.
