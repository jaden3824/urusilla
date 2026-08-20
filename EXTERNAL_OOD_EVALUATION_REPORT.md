# Retained 43-Message External OOD Evaluation

Status: post-cutover exploratory remeasurement on an already-revealed corpus; not fresh confirmatory evidence  
Evaluation date: 2026-08-20  
Retained amendment manifest SHA-256: `892a5218d09f84ffb54dbda9b726660ead30f12d2ed651d37ca1c852929c3fb5`  
Measurement SHA-256: `4e6d3160cecdd68780e9a0a1fb36488e6e6e19197a60ee952697712d6fed493c`  
Repeat measurement SHA-256: `d94f8dcb5c2b232afec9700bcfc5b936e77475c1fb2263dc00a42611d614440e`  
Deterministic outcome SHA-256: `359b07351f1edf343910d723ea7a12de6e48b63a7fa6d87fff88a5ce6a6380de`
Tracked evidence inventory SHA-256: `2a7e903cf690ae82498488a2ea2899f24415b0de0e845666d855676128eb6518`

## Evidence classification and amendment

This corpus, its wrapper, its historical thresholds, and two earlier outcomes were known before the Urusilla cutover. This run must therefore be interpreted only as a retained, post-cutover exploratory remeasurement. It is not a new preregistration, a fresh external confirmation, or evidence of untuned generalization.

The latest historical manifest, `0f10c74e4b640af58ef0daaaef93864be87e6b8a265739bb9aa5984db68433c8`, recorded candidate digests under filenames removed by the cutover but did not retain those candidate source bytes. Its bound measurement is `19d9ce7f0b509fa4fc77c486753a192a23b06c729df966c18b0d6fd7ed883911`. Those historical candidate locks can no longer be reconstructed or honestly reverified from live files. The current amendment records this limitation instead of treating renamed or changed files as the historical candidates.

The amendment process:

- verified the exact retained 43-message corpus and its message-sequence digest;
- verified 29 archived official source files and four archived repository-license files;
- performed no network or provider call;
- snapshotted all 12 current candidate or evaluator source files under content-addressed filenames;
- recorded the current tokenizer, wire-profile, codebook, and alias-profile identities; and
- froze the current inputs before this exploratory measurement.

Future evidence verification uses the archived candidate snapshots, so later live-source edits do not retroactively invalidate this result. A new measurement still requires live sources to match the amendment exactly.

## Result

All fixed and receiver-specific paths recovered the 43 wrapped records exactly and deterministically: `559/559` exact round trips and `559/559` deterministic re-encodings. The retained safety diagnostics also passed:

- v0.5 exact minimum within its enumerated candidates: `172/172`;
- v0.6 warm no-regression against v0.5: `172/172`; and
- v0.6 cold no-regression against the complete v0.5 plan: `20/20`.

The efficiency result remains unfavorable. Controlled Terse English was the lowest-token plain representation under all four tokenizers. Warm v0.6 used `1.05%` to `1.42%` more tokens than terse text. In the complete 43-message cold session, the planner correctly refused all optional artifacts and used the v0.5 fallback plan; this cost `2.09%` to `2.81%` more than terse text. The retained historical diagnostic requiring at least 20% lower cold tokens than the better plain baseline therefore failed for all four tokenizers.

The five implementation and safety diagnostics pass. The only retained token-value signal fails. This does not support a state-of-the-art, utility, task-generalization, model-comprehension, adoption, or energy claim.

## External corpus and source-preserving transform

| Partition | Objects | Official repository revision | Recorded license evidence |
|---|---:|---|---|
| W3C ActivityStreams 2.0 | 12 | [`w3c/activitystreams@6a647d4`](https://github.com/w3c/activitystreams/tree/6a647d489e48ed4bc49597275171ff1963bb579e) | [W3C Software and Document License](https://github.com/w3c/activitystreams/blob/6a647d489e48ed4bc49597275171ff1963bb579e/LICENSE.md) |
| CNCF CloudEvents 1.0.2 | 7 | [`cloudevents/spec@fc1f6f3`](https://github.com/cloudevents/spec/tree/fc1f6f31f5f011a72183f1bcea20c987cb683ade) | [Apache-2.0](https://github.com/cloudevents/spec/blob/fc1f6f31f5f011a72183f1bcea20c987cb683ade/LICENSE) |
| Official MCP 2026-07-28 | 12 | [`modelcontextprotocol/modelcontextprotocol@5f5440b`](https://github.com/modelcontextprotocol/modelcontextprotocol/tree/5f5440bb26a62e2cf3440b92da5a667efa03b267) | [Repository licensing notice](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5f5440bb26a62e2cf3440b92da5a667efa03b267/LICENSE) |
| OASIS STIX 2.1 examples | 12 | [`oasis-open/cti-stix2-json-schemas@9af1db4`](https://github.com/oasis-open/cti-stix2-json-schemas/tree/9af1db41b7b86c06324f899649ae83480134f66e) | [BSD-3-Clause](https://github.com/oasis-open/cti-stix2-json-schemas/blob/9af1db41b7b86c06324f899649ae83480134f66e/LICENSE) |

These are official repository examples, not a representative sample of deployed agent traffic. Some are explicitly non-normative. License metadata is source evidence, not legal advice.

Each selected object is decoded from its exact archived bytes and serialized as sorted minified UTF-8 JSON. The complete canonical object is retained losslessly in `source_json` inside one quarantined `ASSERT` extension node. The wrapper also retains the immutable source URI and revision, source path and locator, source-file digest, canonical-object digest, deterministic IDs, and a one-based protocol clock.

The wrapper is deliberately conservative. It repeats source metadata and stores the external object as a JSON string. This protects validator isolation and exact source recovery but can penalize structural codecs. It is not a native ActivityStreams, CloudEvents, MCP, or STIX mapping.

Corpus identity:

- Canonical corpus: `55,723` bytes, SHA-256 `0a7b315a0b2e3a94bb98aa564d91dd8e117cca7c920c49f623349ba53db19b11`.
- Length-prefixed message sequence: `edbbfe4deb34913a8988ed5cd59d689b98d5769d34a8df2b483929fa17c0efa9`.
- Partitions: ActivityStreams `12`, CloudEvents `7`, MCP `12`, and STIX `12`.
- Training records used by this run: `0`.

## Warm accounting

Each message is counted independently without BOS/EOS tokens, chat templates, role markers, prompts, HTTP envelopes, repairs, or task traffic.

| Receiver tokenizer | Terse English | Minified JSON | Base64 v0.2 | v0.4 | v0.5 warm | v0.6 warm | v0.6 vs terse |
|---|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 18,032 | 19,036 | 44,143 | 38,988 | 18,539 | 18,286 | 1.41% larger |
| o200k_base | 18,063 | 19,127 | 40,615 | 36,780 | 18,544 | 18,320 | 1.42% larger |
| Qwen2.5-7B-Instruct | 22,797 | 23,801 | 45,481 | 38,971 | 23,312 | 23,069 | 1.19% larger |
| Mistral-7B-Instruct-v0.3 | 26,271 | 27,530 | 50,432 | 38,992 | 26,815 | 26,548 | 1.05% larger |

Warm v0.6 selected the optimized surface for `172/172` receiver-message pairs. It improved on v0.5 but did not beat terse text.

| Representation | Full-corpus UTF-8 bytes | Qualification |
|---|---:|---|
| Raw v0.2 binary | 45,688 | Smallest bytes; not a model-text representation |
| Warm v0.6 selected text | 48,885 | Optional artifacts not charged |
| Controlled Terse English | 51,594 | Lowest tokens under every receiver tokenizer |
| Warm v0.5 selected text | 52,239-52,268 | Receiver-specific selection changes four Mistral rows |
| Minified JSON | 55,679 | Plain structured baseline |
| Base64 v0.2 | 60,972 | Text-safe transport form with tokenizer expansion |
| v0.4 text surface | 84,752 | Non-ASCII symbols make UTF-8 bytes unfavorable |

## Fallback and cold-session accounting

The current v0.4 codebook retained complete raw-byte fallback. All `43/43` messages used fallback. Raw symbols were `84.3%` of payload symbols and covered `71.1%` of raw frame bytes, which is strong evidence of distribution shift for that codebook.

The current v0.2 profile capsule is `1,872` UTF-8 bytes. The complete structured profile/codebook bundle is `13,799` bytes. Cold totals charge these artifacts whenever activated.

| Receiver tokenizer | Best plain | v0.2 cold | v0.4 cold | v0.5 cold | v0.6 cold | v0.6 vs best plain |
|---|---:|---:|---:|---:|---:|---:|
| cl100k_base | 18,032 | 45,489 | 48,558 | 18,539 | 18,539 | 2.81% larger |
| o200k_base | 18,063 | 41,876 | 45,787 | 18,544 | 18,544 | 2.66% larger |
| Qwen2.5-7B-Instruct | 22,797 | 46,856 | 48,690 | 23,313 | 23,313 | 2.26% larger |
| Mistral-7B-Instruct-v0.3 | 26,271 | 51,948 | 49,930 | 26,820 | 26,820 | 2.09% larger |

The v0.6 cold planner activated no structured bundle, symbolic grammar, or optimized profile. It selected the complete v0.5 fallback plan for all 43 messages under every tokenizer. No partition produced a cold win:

| Partition | v0.6 cold excess over best plain across tokenizers |
|---|---:|
| ActivityStreams | 2.37% to 3.23% |
| CloudEvents | 2.10% to 2.81% |
| MCP | 2.14% to 2.87% |
| STIX | 1.83% to 2.43% |

## Retained diagnostic outcomes

| Historical diagnostic retained after reveal | Exploratory outcome |
|---|---|
| H1: exact deterministic recovery | PASS, 559/559 |
| H2: complete v0.4 fallback | PASS, 43/43 |
| H3: v0.5 exact minimum | PASS, 172/172 |
| H4: v0.6 warm no-regression | PASS, 172/172 |
| H5: v0.6 cold no-regression | PASS, 20/20 |
| H6: at least 20% lower cold tokens than the better plain baseline | **FAIL, 0/4** |

These are retained diagnostics, not newly preregistered hypotheses. H6 remains the relevant negative token-economics result.

## Current identities and integrity boundary

- Static wire-profile dictionary ID: `7d12fc414eae60b2`.
- Held-out v0.4 codebook SHA-256: `d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695`.
- Train-only v0.6 alias-profile SHA-256: `f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d`.
- Evaluator source SHA-256: `22d2597239a7b67238e40101d3b93b67c11d6c77b7a8d192da993bc2277cc860`.
- Isolated test source SHA-256: `f48147efc230fef2266ec8099e015aed9b62a00b46415c116afef97ba1b53ab6`.

Both measurements produced the same deterministic outcome digest. They include local latency samples, but those timings are excluded from the outcome digest because they depend on machine load. The digest covers corpus identities, exactness, token and byte accounting, fallback, selections, cold plans, diagnostics, and claim boundaries.

## Limitations

- The corpus and outcomes were already revealed before this amendment.
- Historical candidate bytes were not archived, so historical live-source locks cannot be reconstructed.
- The current candidates may contain changes beyond a pure filename cutover; this report does not equate them with historical candidates.
- The 43 objects are a fixed convenience sample, not a statistically representative deployment sample.
- The project chose the source families and conservative wrapper.
- Token counts begin after a valid typed message exists and exclude model task execution, repairs, prompts, and transport overhead.
- Exact serialization does not show that a model understands the representation or completes tasks correctly.
- Checksums detect accidental corruption; they do not authenticate an attacker.
- Energy, memory, dollar cost, adoption, and persistent stream compression were not measured.

## Offline reproduction

The tracked `evidence/external_ood_evaluation/` directory contains the complete clean-clone verification closure: 29 source files, four repository licenses and notices, 12 candidate snapshots, the corpus, amendment manifest, and both measurements. `DIGESTS.json` covers all 49 evidence files and has a detached checksum. The repository-level `THIRD_PARTY_NOTICES.md` records the exact ActivityStreams, CloudEvents, Model Context Protocol, and STIX revisions, cached license identities, and the required W3C modification notice. No ignored `work/` artifact is required to verify the published result.

```bash
.venv-research-py312/bin/python external_ood_evaluation.py verify \
  --manifest evidence/external_ood_evaluation/premeasurement-manifest-892a5218d09f84ffb54dbda9b726660ead30f12d2ed651d37ca1c852929c3fb5.json \
  --measurement evidence/external_ood_evaluation/measurement-4e6d3160cecdd68780e9a0a1fb36488e6e6e19197a60ee952697712d6fed493c.json

.venv-research-py312/bin/python -m unittest -v test_external_ood_evaluation.py

(cd evidence/external_ood_evaluation && shasum -a 256 -c DIGESTS.sha256)
```

Creating a new amendment with `refreeze` additionally requires the separately retained historical anchor files. Those local provenance inputs are not needed for clean-clone verification. The legacy `freeze` command retains the original network-acquisition mechanism, but running it now cannot restore fresh-confirmatory status because the corpus and earlier outcomes are already known.
