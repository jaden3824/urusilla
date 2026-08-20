# Terse-English serialization baseline

## Result

This bounded study compares the same canonical Urusilla messages in four text-carried representations: a strong Controlled Terse English baseline, sorted minified JSON, Base64 wire v0.2, and the warm experimental token surface v0.3. Across the two datasets and four pinned tokenizers, the two machine surfaces range from **-120.9% to +69.8% token savings** versus Controlled Terse English. Negative savings are retained and mean that the machine surface used more tokens.

This is serialization accounting, not an end-to-end agent evaluation. It does **not** show that any language model understands CTE or the machine surfaces, and it does not measure task success, repair behavior, inference latency, or energy.

## Controlled Terse English baseline

CTE is a deterministic controlled-language record, not unconstrained conversational prose. It is intentionally compact to avoid a weak natural-language strawman: safe ASCII strings and map keys are unquoted, maps and lists use concise delimiters, and only the fixed outer sentence carries English function words.

The canonical grammar is:

```text
ACT from SENDER to RECIPIENTS: BODY; id ID, session SESSION, reply REPLY, schema SCHEMA, clock UINT, expires UINTms, confidence UINTppm|unknown, expect ACTS, meta META.
```

Each uppercase or named slot has exactly one mapping:

| Canonical field | CTE location |
|---|---|
| `act` | first uppercase word |
| `sender` | value after `from` |
| `recipients` | list after `to` |
| `body` | value after the colon |
| `id` | labeled `id` value |
| `session` | labeled `session` value |
| `reply_to` | labeled `reply`; `none` is null |
| `schema` | labeled `schema` value |
| `logical_clock` | labeled `clock` unsigned integer |
| `expires_ms` | labeled `expires` integer with `ms` suffix |
| `confidence_ppm` | labeled `confidence`; `unknown` is null |
| `expected` | labeled `expect` act list |
| `meta` | labeled `meta` map |

Nested values use a documented typed grammar: `true`, `false`, `null`, canonical JSON numbers, quoted JSON strings when a string is not a safe bare token, lists `[v,...]`, UTF-8-key-sorted maps `{key=v,...}`, and `bytes"lowercase-hex"`. The decoder rejects duplicate keys, malformed syntax, trailing text, non-canonical spellings, and messages rejected by the shared semantic validator. This gives a machine-checkable one-to-one mapping rather than relying on paraphrase judgment.

Example (the report does not charge this documentation):

```text
COMMIT from broker.epsilon.agent to [planner.alpha.agent,verifier.beta.agent]: {creditors=[planner.alpha.agent,verifier.beta.agent],debtor=broker.epsilon.agent,expiry_ms=4000,goal={condition={arguments=[{kind=ref,uri=sha256:7f9696860162130062871a99},candidate-0004,{attempt=4,score=0.235294}],context={label=routing,locale=en-US},kind=claim,predicate=finance.candidate.valid},constraints=[{condition={latency_ms_lte=1250,regions=[ap-northeast-2],retry_lte=0},kind=constraint,mode=soft,scope=execution,weight_ppm=650000},{condition={latency_ms_lte=1500,regions=[ap-northeast-2,us-east-1],retry_lte=1},kind=constraint,mode=hard,scope=output,weight_ppm=1000000}],kind=goal,owner=team-4,priority=5},kind=commitment,verifier=verifier-4.agent}; id 4b38924e-5dd8-562b-8863-811670791cd6, session 04271ad2-2cfd-59d4-935a-64da2b483bac, reply 9c0dd94b-87b7-5998-b5f2-cba6612e1821, schema urn:urusilla:contract-resolution:1, clock 13, expires 2000ms, confidence 531676ppm, expect [RESOLVE], meta {budget={compute_units=24,wire_bytes=1536},tags=[benchmark,domain-4,agent],trace={run=0,sampled=false,span=4}}.
```

## Exact recovery and field coverage

| Dataset | Messages exact | Deterministic re-render | Required top-level fields | Terminal path/value occurrences |
|---|---:|---:|---:|---:|
| grouped holdout | 56/56 | 56/56 | 728/728 | 2,143/2,143 |
| out of domain | 10/10 | 10/10 | 130/130 | 330/330 |

Exact decoded-object equality is the primary coverage test. The field and terminal-path counts make omissions visible but are not substitutes for that equality check.

## Exact warm sizes and token counts

Every message is counted as an independent frame. Counts exclude BOS/EOS, chat templates, role markers, prompts, transport envelopes, and retransmissions.

### Grouped Holdout

| Representation | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| Controlled Terse English | 43,880 | 43,880 | 15,764 | 15,770 | 18,893 | 21,228 |
| sorted minified JSON | 52,604 | 52,604 | 16,763 | 17,224 | 19,892 | 23,514 |
| Base64 wire v0.2 warm | 15,448 | 15,448 | 10,933 | 10,151 | 11,097 | 12,313 |
| token surface v0.3 warm | 15,368 | 6,382 | 6,367 | 6,312 | 6,337 | 6,409 |

Savings relative to Controlled Terse English (positive is better; negative is worse):

| Representation | Bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|
| sorted minified JSON | -19.9% | -6.3% | -9.2% | -5.3% | -10.8% |
| Base64 wire v0.2 warm | +64.8% | +30.6% | +35.6% | +41.3% | +42.0% |
| token surface v0.3 warm | +65.0% | +59.6% | +60.0% | +66.5% | +69.8% |

### Out Of Domain

| Representation | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| Controlled Terse English | 8,402 | 8,402 | 2,639 | 2,645 | 3,098 | 3,599 |
| sorted minified JSON | 9,856 | 9,856 | 2,808 | 2,897 | 3,267 | 4,001 |
| Base64 wire v0.2 warm | 8,212 | 8,212 | 5,829 | 5,467 | 6,007 | 6,642 |
| token surface v0.3 warm | 11,496 | 5,391 | 5,376 | 5,026 | 5,368 | 5,385 |

Savings relative to Controlled Terse English (positive is better; negative is worse):

| Representation | Bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|
| sorted minified JSON | -17.3% | -6.4% | -9.5% | -5.5% | -11.2% |
| Base64 wire v0.2 warm | +2.3% | -120.9% | -106.7% | -93.9% | -84.6% |
| token surface v0.3 warm | -36.8% | -103.7% | -90.0% | -73.3% | -49.6% |

## Cold transfer

CTE and JSON require no negotiated data capsule in this accounting. Base64 v0.2 requires the static profile once. Token surface v0.3 requires that profile plus the heldout-trained codebook. Decoder software and the public language specification are treated as installed for every representation.

| Capsule | UTF-8 bytes | Characters | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---:|---:|---:|---:|---:|---:|
| profile | 1,872 | 1,872 | 1,346 | 1,261 | 1,375 | 1,516 |
| codebook | 11,927 | 11,927 | 8,224 | 7,746 | 8,344 | 9,422 |

Strict break-even is the first integer `N` satisfying `cold + N × candidate_mean < N × baseline_mean`, assuming the measured workload mix repeats. `never on mean` means the candidate is not smaller while warm under that metric.

| Dataset | Candidate | Baseline | Cold charged | UTF-8 bytes | cl100k_base | o200k_base | Qwen2.5-7B-Instruct tokenizer | Mistral-7B-Instruct-v0.3 tokenizer |
|---|---|---|---|---:|---:|---:|---:|---:|
| grouped holdout | Base64 wire v0.2 warm | Controlled Terse English | profile | 4 | 16 | 13 | 10 | 10 |
| grouped holdout | token surface v0.3 warm | Controlled Terse English | profile + codebook | 28 | 58 | 54 | 44 | 42 |
| grouped holdout | Base64 wire v0.2 warm | sorted minified JSON | profile | 3 | 13 | 10 | 9 | 8 |
| grouped holdout | token surface v0.3 warm | sorted minified JSON | profile + codebook | 21 | 52 | 47 | 41 | 36 |
| out of domain | Base64 wire v0.2 warm | Controlled Terse English | profile | 99 | never on mean | never on mean | never on mean | never on mean |
| out of domain | token surface v0.3 warm | Controlled Terse English | profile + codebook | never on mean | never on mean | never on mean | never on mean | never on mean |
| out of domain | Base64 wire v0.2 warm | sorted minified JSON | profile | 12 | never on mean | never on mean | never on mean | never on mean |
| out of domain | token surface v0.3 warm | sorted minified JSON | profile + codebook | never on mean | never on mean | never on mean | never on mean | never on mean |

## Interpretation

The grouped holdout and the ten-message out-of-domain set must be read separately. The former repeats a synthetic benchmark family while holding out complete semantic groups; the latter introduces new schemas, agents, values, and map shapes but is small and repository-authored. The v0.3 codebook sees only the 224-message training partition. The v0.2 profile and v0.3 Unicode alphabet were developed earlier around the benchmark family and named OpenAI tokenizers, so this is not a blind tokenizer evaluation.

A representation should not be selected from an aggregate headline. Warm savings can reverse by dataset and tokenizer, while a large negotiated capsule can dominate a short session. These exact negative cases are part of the result: adaptive negotiation should retain CTE or JSON whenever the machine surface is not expected to amortize.

## Method and frozen inputs

- Format: `urusilla-terse-english-baseline-v1`
- Grouped holdout: 56 messages, canonical corpus SHA-256 `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`
- Out of domain: 10 messages, canonical corpus SHA-256 `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`
- v0.3 training partition: 224 messages, SHA-256 `f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759`
- Heldout-trained codebook SHA-256: `d763157b6adbe51295f4133a2758220f217f1d2f6fb8704bb0e83749e2d04695`
- Tokenizer packages: `tiktoken==0.11.0`, `tokenizers==0.21.4`
- Tokenization: each serialization counted separately with no special tokens added

Tokenizer identities:

- `cl100k_base`: cl100k_base; tiktoken 0.11.0; vocabulary 100,277; fingerprint `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d`
- `o200k_base`: o200k_base; tiktoken 0.11.0; vocabulary 200,019; fingerprint `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc`
- `qwen2_5_7b_instruct`: Qwen2.5-7B-Instruct tokenizer; tokenizers 0.21.4; vocabulary 151,665; fingerprint `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`
- `mistral_7b_instruct_v03`: Mistral-7B-Instruct-v0.3 tokenizer; tokenizers 0.21.4; vocabulary 32,768; fingerprint `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49`

Text-sequence SHA-256 values use an eight-byte big-endian length before each UTF-8 message:

- grouped holdout:
  - `terse_english`: `565e8549bc7eb582b4d997bbd37ef45dc07bd7fe9c61b5a48399c246b8a514e7`
  - `json`: `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`
  - `base64_v02`: `4391adde6540d09573fbdfbf2781456cc0d5c027502efca2085984a8334274ac`
  - `v03`: `f66ade3a5538b6818728870a1ee1e51c1e6781385416cde3a48c68d7301bd0e5`
- out of domain:
  - `terse_english`: `e179deb0b57709dd3ecf89852ad6939c812fcf2f70833463e08aa87cf1d07a32`
  - `json`: `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`
  - `base64_v02`: `cb1b69c69876a4c9945494b8aa2274d39fd40a1b353c1fda00c8b11501d09523`
  - `v03`: `1fd127e6956edf507e5668127662d8be40adce38682001946ad09463406820e4`

Source SHA-256 values:

- `urusilla_terse_english_benchmark.py`: `f528f68e22aa0c7b2fcc2ef10719648453aeda54c9c08df0e3986a7161e2c00e`
- `test_urusilla_terse_english_benchmark.py`: `fedd63f7cdfa75b83db2e5e371b0b5bb391315cfa438008ae533d047279fb7a2`
- frozen corpus provider: `5d614c0cc601df6b378e84804eb89e4d4c443a2aaa7263a5d096524c777f18ee`

Reproduce from a repository root. The asset downloader verifies immutable official revisions and complete-file SHA-256 values before use:

```bash
python3 -m venv work/tokenizer_venv
work/tokenizer_venv/bin/python -m pip install tiktoken==0.11.0 tokenizers==0.21.4
PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_tokenizer_benchmark.py --download-assets --assets-dir work/tokenizer_assets
PYTHONPATH=. work/tokenizer_venv/bin/python urusilla_terse_english_benchmark.py --benchmark --assets-dir work/tokenizer_assets
PYTHONPATH=. work/tokenizer_venv/bin/python -m unittest test_urusilla_terse_english_benchmark.py -v
```

## Limitations

- CTE is controlled English-like notation, not a sample of ordinary agent prose. A natural-language baseline without deterministic field encoding would not guarantee semantic equivalence.
- Exact round-trip proves serialization fidelity only. No LLM decoded any representation in this study, so understanding, instruction following, and repair success remain unmeasured.
- The grouped holdout is synthetic and related to profile development. The out-of-domain corpus has only ten messages and was authored in the same repository.
- Token counts depend on four pinned tokenizer assets. They do not predict all models, hosted token accounting, KV-cache behavior, or compressed transport bytes.
- Cold break-even assumes an unchanged workload mix, successful cache reuse, no negotiation failure, and no retransmission.
- Energy cannot be inferred directly from token count; joules, hardware utilization, and end-to-end latency were not measured.
