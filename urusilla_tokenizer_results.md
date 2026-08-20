# Urusilla serialization tokenizer accounting study

## Result

Across the four pinned tokenizer profiles, warm Base64 UrusillaWire v0.2 used **39.0% to 51.0% fewer tokens** than sorted minified UrusillaIR JSON on the fixed 280-message corpus. Counting the Base64 profile capsule once changed the range to **37.4% to 49.7% fewer tokens**. In contrast, Base64 UrusillaWire v0.1 used **57.2% to 94.3% more tokens** than JSON.

The favorable v0.2 result is an **in-sample, warm-profile upper bound**. Its static profile was manually built around this benchmark vocabulary and map shapes. These numbers measure serialization tokenization only. They do not measure task success, model understanding, reasoning quality, translation cost, generation latency, or total application tokens. They are not a comparison with semantically equivalent natural-language messages; no terse-English baseline was constructed.

## Exact token counts

Each message was tokenized separately, matching its framing boundary. Counts exclude BOS/EOS tokens, role markers, chat templates, HTTP/A2A envelopes, and prompts. No raw binary was treated as text: both wire formats were represented by standard padded Base64 ASCII.

| Tokenizer | JSON tokens | Base64 v0.1 | Saved vs JSON | Base64 warm v0.2 | Saved vs JSON | + one capsule | Saved vs JSON |
|---|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 85,429 | 166,025 | -94.3% | 52,092 | +39.0% | 53,438 | +37.4% |
| o200k_base | 87,494 | 154,919 | -77.1% | 48,199 | +44.9% | 49,460 | +43.5% |
| Qwen2.5-7B-Instruct tokenizer | 100,958 | 169,487 | -67.9% | 52,801 | +47.7% | 54,176 | +46.3% |
| Mistral-7B-Instruct-v0.3 tokenizer | 119,253 | 187,414 | -57.2% | 58,432 | +51.0% | 59,948 | +49.7% |

A positive `Saved vs JSON` value means fewer tokens. A negative value means the candidate used more tokens. Base64 v0.1 is a useful negative result: although its binary frame is smaller than JSON in bytes, Base64 fragments are poorly aligned with these tokenizer vocabularies.

## One-time v0.2 profile cost

The canonical v0.2 profile capsule is `1,402` binary bytes, `1,872` Base64 characters, SHA-256 `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6`, and dictionary ID `7d12fc414eae60b2`.

| Tokenizer | Capsule tokens | Mean-corpus break-even |
|---|---:|---:|
| cl100k_base | 1,346 | 12 messages |
| o200k_base | 1,261 | 9 messages |
| Qwen2.5-7B-Instruct tokenizer | 1,375 | 8 messages |
| Mistral-7B-Instruct-v0.3 tokenizer | 1,516 | 7 messages |

Break-even divides the one-time capsule token count by the mean per-message token saving observed on this same corpus, then rounds to the first whole message that exceeds the capsule cost. It is not a held-out estimate.

## Text and byte accounting

| Representation | Messages | Text code points | UTF-8 text bytes | Underlying binary bytes | Text bytes saved vs JSON | Serialization digest |
|---|---:|---:|---:|---:|---:|---|
| Sorted minified UrusillaIR JSON | 280 | 264,123 | 266,684 | 266,684 | +0.0% | `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc` |
| Base64 UrusillaWire v0.1 | 280 | 235,116 | 235,116 | 176,069 | +11.8% | `00873eef24b4960272e4c1faf9ea7ce3dcd4604f9758edd626a7f4ea1b4c0d71` |
| Base64 UrusillaWire v0.2 warm | 280 | 73,376 | 73,376 | 54,752 | +72.5% | `d120342693577cbce4c2c81633800f4f9305205036941be0148caedd7e439657` |

The serialization digest is SHA-256 over every message's 8-byte big-endian UTF-8 length followed by its exact UTF-8 text. The JSON representation is the current CPython `json.dumps` path with `sort_keys=True`, compact separators, UTF-8 output, and non-ASCII characters left unescaped. It is deterministic for this fixed runtime and corpus, but it is not claimed to implement an independent cross-runtime JSON canonicalization standard.

## Corpus and exactness

- Corpus version: `urusilla-benchmark-corpus-v1`
- Message count: `280`
- Length-prefixed canonical corpus SHA-256: `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`
- UrusillaWire v0.1 semantic round-trip: `280/280`
- UrusillaWire v0.2 semantic round-trip: `280/280`

The corpus already contains typed UrusillaIR objects. The study therefore excludes the tokens and errors involved in converting user language or model state into UrusillaIR.

## Tokenizer provenance

Execution runtime: `CPython 3.12.14` on `macOS-15.0-arm64-arm-64bit`. Package pins were `tiktoken==0.11.0` and `tokenizers==0.21.4`.

| Profile | Implementation | Vocabulary size | Exact vocabulary fingerprint |
|---|---|---:|---|
| cl100k_base | tiktoken 0.11.0 | 100,277 | `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d` |
| o200k_base | tiktoken 0.11.0 | 200,019 | `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc` |
| Qwen2.5-7B-Instruct tokenizer | tokenizers 0.21.4 | 151,665 | `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539` |
| Mistral-7B-Instruct-v0.3 tokenizer | tokenizers 0.21.4 | 32,768 | `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49` |

For tiktoken profiles, the fingerprint covers the regex pattern, ordered mergeable byte ranks, and special-token mapping. For open-model profiles it is the SHA-256 of the complete `tokenizer.json` file.

Immutable open-model acquisitions:

- **Qwen2.5-7B-Instruct tokenizer:** official repository `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`, file `tokenizer.json`, SHA-256 `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`; measured local cache path `work/tokenizer_assets/qwen2_5_7b_instruct/tokenizer.json`.
- **Mistral-7B-Instruct-v0.3 tokenizer:** official repository `mistralai/Mistral-7B-Instruct-v0.3`, revision `c170c708c41dac9275d15a8fff4eca08d52bab71`, file `tokenizer.json`, SHA-256 `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49`; measured local cache path `work/tokenizer_assets/mistral_7b_instruct_v03/tokenizer.json`.

## Reproduction

Create an isolated Python 3.12 environment, install the two exact dependency pins, then run:

```text
PYTHONPATH=. python urusilla_tokenizer_benchmark.py --download-assets
PYTHONPATH=. python -m unittest test_urusilla_tokenizer_benchmark.py -v
```

The download step uses only immutable official model revisions and verifies each asset before use. Subsequent runs can be offline.

Source SHA-256 values for this run:

- `urusilla_tokenizer_benchmark.py`: `b00f834c279d2cdb6bf314ecbba136f9f8e9885f1d1572a2b66efb616b43f7d3`
- `test_urusilla_tokenizer_benchmark.py`: `3b800a5a17ce8a56047cd882782f668be6379e114224d2b74ac2bd73a098dbb8`
- `urusilla_benchmark.py`: `b5e2885f7e17097643c1e93ba3326f285cd37aa8199cf1cc3b234227e515b5f8`
- `urusilla.py`: `3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf`
- `urusilla_wire_v02.py`: `166b1090b536bfff942667d43be583b2345eeb14b9da5d1535b7a16bb6bab2e7`

## Interpretation boundary

Token count is tokenizer-dependent and does not by itself establish useful agent communication. A complete claim needs held-out schemas, equivalent natural-language baselines, task-success parity, model-side translation costs, latency, safety, and cross-model evaluation. The present result answers only: how many tokenizer units these exact text serializations occupy after a semantic object already exists.
