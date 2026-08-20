# Live model receiver-comprehension pilot

## Result

The predeclared reliability gate produced **27/28 exact semantic message reconstructions** across 2 gate trials and 15 API attempts. The gate did not pass, so the remaining matrix was not run. Every unfavorable field, token, latency, malformed-output, and repair result remains in the tables below. Validator failures are also retained by privacy-safe category.

This is a small prompted receiver-comprehension pilot. It does **not** measure sender generation, multi-turn agent task success, autonomous repair, cross-vendor transfer, unprompted protocol adoption, latent communication, or state-of-the-art performance.

These provider outcomes remain bound to the historical pre-cutover input digests recorded below. No provider call was rerun after the Urusilla cutover. The current Urusilla corpus and symbolic surface were rederived and validated only through offline deterministic tests, so the 27/28 live result must not be attributed to those current inputs.

## Controlled design

The measured fixed corpus contains 14 semantic messages: one grouped-holdout and one out-of-domain example for each of the seven core acts. Every model/format/repeat receives the identical ordered semantic set, deterministically split into 7 batches of 2 messages. Grammar is paid once per batch, not once per message.

The receiver returns a strict JSON-schema object containing the original index and a direct typed message object. The schema is inferred from each batch's recursive value types and key/list shape but contains no terminal values. Scoring locally canonicalizes and validates each reconstructed object, compares the full semantic message, and compares every terminal path/value occurrence. This removes the original double-serialized `canonical_json` string confound.

The predeclared gate required both `gpt-5-nano` + JSON repeats to recover at least 14/14 messages with zero validator failures. Gate passed: **false**. Matrix continued: **false**.

The official Responses API was called with `store=false`. No raw model output, response identifier, or API key is stored in this artifact. GPT-5 nano and GPT-4o mini both document Responses and Structured Outputs support. Current price constants used for the estimate are $0.05/$0.40 and $0.15/$0.60 per million input/output tokens, respectively. See the official [GPT-5 nano](https://developers.openai.com/api/docs/models/gpt-5-nano) and [GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini) model pages and the [Responses API reference](https://developers.openai.com/api/reference/responses/create).

## Semantic recovery

| Model | Input format | Runs | Exact messages | Validator-valid | Terminal fields | Failed runs | Initial malformed | Repairs | Repair failures |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5-nano` | sorted minified JSON | 2 | 27/28 | 27/28 | 984/1,018 | 1 | 1 | 1 | 1 |
| `gpt-5-nano` | Controlled Terse English | not run | — | — | — | — | — | — | — |
| `gpt-5-nano` | compact symbolic surface | not run | — | — | — | — | — | — | — |
| `gpt-4o-mini` | sorted minified JSON | not run | — | — | — | — | — | — | — |
| `gpt-4o-mini` | Controlled Terse English | not run | — | — | — | — | — | — | — |
| `gpt-4o-mini` | compact symbolic surface | not run | — | — | — | — | — | — | — |

## API tokens, latency, and estimated cost

Usage values come from the API response. Output tokens include reasoning tokens where reported. Cost applies the published uncached input/output rates to measured usage; it is an estimate rather than an invoice. Latency is wall time for the full HTTPS response and is based on only two observations per cell.

| Model | Input format | Input | Cached input | Output | Reasoning | Total | Input/msg | Output/msg | Median latency | p95 latency | Estimated cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5-nano` | sorted minified JSON | 23,034 | 5,760 | 9,559 | 0 | 32,593 | 822.6 | 341.4 | 39279.7 ms | 39534.0 ms | $0.004975 |
| `gpt-5-nano` | Controlled Terse English | not run | — | — | — | — | — | — | — | — | — |
| `gpt-5-nano` | compact symbolic surface | not run | — | — | — | — | — | — | — | — | — |
| `gpt-4o-mini` | sorted minified JSON | not run | — | — | — | — | — | — | — | — | — |
| `gpt-4o-mini` | Controlled Terse English | not run | — | — | — | — | — | — | — | — | — |
| `gpt-4o-mini` | compact symbolic surface | not run | — | — | — | — | — | — | — | — | — |

## Cold grammar and warm amortization

Cold grammar counts below use local `o200k_base` when available; otherwise the script labels and uses a four-UTF-8-byte proxy. They exclude common instructions, records, the shape-derived output schema, and API framing, so they are a grammar-only accounting aid rather than API-billed usage. Warm amortization divides the once-per-batch grammar by 2 messages.

| Input format | Grammar bytes | Grammar tokens/proxy | Warm grammar tokens/message |
|---|---:|---:|---:|
| sorted minified JSON | 140 | 26 | 13.00 |
| Controlled Terse English | 423 | 109 | 54.50 |
| compact symbolic surface | 411 | 112 | 56.00 |

## Compact symbolic surface

The symbolic surface is a standard-library implementation with shared semantic validation. After `@1`, an 11-character Base64url checksum and colon protect a fixed sequence of one-letter fields. Values are canonical JSON and `~` is null. The labels map as follows:

| Label | Semantic field |
|---|---|
| `i` | `id` |
| `s` | `session` |
| `f` | `sender` |
| `t` | `recipients` |
| `a` | `act` |
| `r` | `reply_to` |
| `y` | `schema` |
| `l` | `logical_clock` |
| `x` | `expires_ms` |
| `c` | `confidence_ppm` |
| `e` | `expected` |
| `b` | `body` |
| `m` | `meta` |

The decoder verifies the checksum, exact label order, JSON values, shared semantic constraints, absence of trailing data, and byte-identical canonical re-encoding. Unit tests cover every pilot message, deterministic output, malformed headers, non-canonical spelling, and deterministic single-character mutations.

## Protocol amendments and preserved failures

The original output contract asked the model to place a complete JSON document inside a JSON string. That conflated semantic recovery with escaping and double serialization. Before changing the contract, the following unfavorable observations were frozen. They are not pooled with the final direct-object results.

| Stage | Model / format | Repeat | Batch | Exact | Terminals | Total tokens | Latency | Status / failure |
|---|---|---:|---:|---:|---:|---:|---:|---|
| double-serialized output | `gpt-5-nano` / sorted minified JSON | 1 | 14 | 0/14 | 0/509 | 17,751 | 61879.8 ms | failed |
| double-serialized output | `gpt-5-nano` / sorted minified JSON | 2 | 14 | 9/14 | 373/509 | 17,408 | 56865.3 ms | failed |
| double-serialized output | `gpt-5-nano` / sorted minified JSON | 1 | 7+7 | 11/14 | 397/509 | 25,836 | 120436.3 ms | `batch_0:semantic_json|batch_1:semantic_json` |
| double-serialized output | `gpt-5-nano` / sorted minified JSON | 2 | 7+7 | 4/14 | 142/509 | 16,018 | 43393.5 ms | `batch_0:semantic_json|batch_1:semantic_json` |
| privacy-safe diagnostic | `gpt-5-nano` / sorted minified JSON | 1 | 14 | 0/14 | 0/509 | 8,554 | not retained | `completed` / `semantic_json` |

The diagnostic response completed without an API error or incomplete reason, but validator parsing failed. It contained 14,306 output-text characters with SHA-256 `12f0364529105a861ec87539d2c473285136d7542280c806b128a1377b9c77f3`; the text itself was discarded. Two later requests were interrupted in flight across the two stopped stages, so their server completion and billing outcome are unknown. The cost guard reserves a deliberately conservative upper bound for all of these calls.

## Cost gate

- Hard estimated ceiling: `$1.00`.
- Worst-case preflight estimate, including one full repair call after every primary call: `$0.406244`.
- Measured-usage estimate for the final gated run: `$0.004975`.
- Conservative reserve for all pre-amendment and interrupted calls: `$0.150000`.
- Whole-experiment upper bound used by the guard: `$0.154975`.
- Planned repeats: `2` per model/format; only the gate cell ran because the gate failed.
- The preflight assumes two UTF-8 input bytes per token, includes the shape-derived output schema, and assumes every call consumes the full output-token limit. Calls are blocked if the reserve plus measured usage and the next call's bound would cross the ceiling.

## Frozen inputs and provenance

- Run UTC: `2026-08-20T09:00:37.659471+00:00`
- Format: `urusilla-model-comprehension-pilot-v1`
- Measured pilot corpus SHA-256: `fde113bb8b89eb3e3135b8797b42667a63078657c035de8e286780a4575003ad`
- Measured symbolic text-sequence SHA-256: `ab1f66decf8f24961c45b54eaeb602377b9b5fea0397a78eac9a72f291fe79c9`
- Current Urusilla pilot corpus SHA-256: `f80d6f1483fba62aad006e6c45ade3f1a0f912ad7a714b94f7a6072a637b29c7`
- Current Urusilla symbolic text-sequence SHA-256: `a820c137167afe669c9fb33d2366498f9894252f93a9cc17d37e72aa806a0f4b`
- Provider rerun after Urusilla cutover: `false`
- Frozen aggregate results SHA-256: `ee1b3423bdfb4745ccf8bf58106ee6c8c10f98815fb323308c6db9246dc4f0d2`
- Acts: `ASSERT, QUERY, REQUEST, PROPOSE, COMMIT, RESOLVE, RETRACT`
- Origins: `{"grouped_holdout":7,"out_of_domain":7}`
- Offline report-render Python: `3.12.14`
- Offline report-render platform: `macOS-15.0-arm64-arm-64bit`

Source SHA-256 values:

- pilot and symbolic codec: `52e018b5c65b4b2769807a2341897bccf02ee519767eab9878cea17402469787`
- offline tests: `26d67785d5515fc6341cd671d509e7a02cf11f55cc07d7c0cb8308417c88f4b1`

Reproduce deliberately; network calls occur only with `--live` and consume API credits:

```bash
PYTHONPATH=outputs work/tokenizer_venv/bin/python outputs/urusilla_model_comprehension_pilot.py --live
PYTHONPATH=outputs python3 -m unittest outputs/test_urusilla_model_comprehension_pilot.py -v
```

## Limitations

- Fourteen synthetic messages and two repeats per cell are far too small for a general model-comprehension claim or a rank ordering with confidence intervals.
- The retained live outcomes predate the Urusilla cutover. Current renamed inputs pass offline codec and determinism tests only; they have no new provider outcome.
- The historical live runtime was not embedded separately in the aggregate result. The Python and platform values above identify this offline report render, not the provider measurement environment.
- The prompt explicitly teaches each format and asks for reconstruction. This measures prompted receiver comprehension, not spontaneous acquisition or use.
- The strict output wrapper can improve formatting reliability but does not reveal whether internal semantic understanding is robust. Its batch-specific recursive schema exposes key, type, list-length, and container shape, though never terminal values; this can materially assist reconstruction.
- Two-message batches pay the format grammar and shape schema seven times per corpus pass. This is an unfavorable latency and cold-context tradeoff introduced only after larger batches failed the reliability gate.
- The same project authored the language, prompts, and evaluation. No blinded external evaluator or independent corpus was used.
- Only GPT-5 nano reached the gate. GPT-4o mini and all non-JSON format cells were deliberately not run after the gate failed. Cross-vendor and unseen-model transfer remain unknown.
- Task success, sender generation, dialogue, tool use, repair after semantic errors, and adversarial inputs remain unmeasured.
- Token usage and API latency do not directly measure energy, local inference cost, KV-cache behavior, or production throughput.
- Model aliases and prices can change. The report records the aliases used and links the official model pages consulted for this run.

## Failure codes

No raw failed output is retained. Aggregate failure codes:

- `batch_1:semantic_message`: 1

## Validator failure categories

Categories contain paths and error classes only, never reconstructed values:

- `ValidationError/unknown/other`: 1

## Privacy-safe unfavorable response diagnostics

Raw output and response identifiers were discarded. Digests identify output text without retaining it.

| Model / format | Repeat | Batch | Attempt | Transport / status | Parse failure | Validator categories | Output chars | Output SHA-256 | Tokens |
|---|---:|---:|---|---|---|---|---:|---|---:|
| `gpt-5-nano` / sorted minified JSON | 1 | 1 | primary | completed / completed | `semantic_message` | `{"ValidationError/unknown/other":1}` | 1730 | `2149016667e77c34234d9e87b00344853fe275678c7694220602f972592e07d7` | 1873 |
| `gpt-5-nano` / sorted minified JSON | 1 | 1 | repair | completed / completed | `semantic_message` | `{"ValidationError/unknown/other":1}` | 1722 | `2b9d1e5b2a07fbed9da6e6c215be560a7b523e35af752ae6047345caa3dc0aec` | 1890 |
