# Transparent fallback v0.8 development experiment

Status: post-reveal exploratory development evidence; not a confirmatory generalization, model, task-utility, adoption, energy, or state-of-the-art result  
Date: 2026-08-20  
External corpus: 43 previously revealed records, file SHA-256 `0a7b315a0b2e3a94bb98aa564d91dd8e117cca7c920c49f623349ba53db19b11`  
Canonical message sequence SHA-256: `edbbfe4deb34913a8988ed5cd59d689b98d5769d34a8df2b483929fa17c0efa9`

## Result

Under the authenticated bound-transport contract, the prior **2.12% to 2.80% external cold token penalty becomes exactly zero** on all four pinned tokenizers. The selector delivered raw Controlled Terse English for all `172/172` receiver-message pairs. That delivered text was byte-for-byte identical to the plain baseline, and mode, sequence, and exact-byte authentication remained outside the receiver text.

This is a contract correction, not a new compression win. No compact project surface was selected by the bound contract. The result says that a fallback path should stop wrapping a baseline when a negotiated authenticated transport already supplies the wrapper's functions. It does not show that a new language beats Controlled Terse English on this corpus.

The separate standalone text envelope preserves the same mode, sequence, and keyed integrity contract when no such transport binding exists. Its warm selected receiver-token cost is **5.85% to 6.80% higher** than raw Controlled Terse English. That unfavorable overhead is retained rather than attributed to the language or hidden outside the comparison.

The external records and their earlier failure were known before v0.8 was designed. This corpus is therefore development data for this candidate. No fresh confirmatory corpus was obtained or measured.

## Frozen selection contract

The candidate enumerates four exact representations:

- raw Controlled Terse English with no session artifact;
- sorted minified canonical JSON with no session artifact;
- the frozen train-only optimized surface with its grammar and alias profile; and
- the frozen v0.4 surface with its structured bundle.

For each receiver and message, the selector counts the complete receiver text. It first finds the best plain representation. A compact representation is eligible only when its complete token count is strictly lower than that plain minimum. The final choice is the exact minimum with fixed tie order `terse, json, optimized, v04`. Thus a compact mode cannot win a tie merely because it belongs to this project.

Cold planning enumerates all four activation states for the structured and optimized artifacts, charges their exact tokenizer-specific cost once, and selects the exact minimum session total. A tie prefers fewer cold tokens and no activation. Thresholds are not tuned per message.

- Selection contract SHA-256: `fcb90039b2a7e193e3b274b6a4cefcb7cf851b116e397bcb721e0b268c5c36b0`
- Frozen exploratory snapshot SHA-256: `a8996a65dde500bdc9928f5462574dc39c3edc591de6dd42919d523b50d3bea9`
- Frozen train-only alias profile SHA-256: `f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d`

## Warm and cold receiver tokens

The previous v0.6 cold row is reproduced only to identify the observed failure that motivated this candidate. The raw plain, v0.8 bound, and standalone values were measured by the v0.8 harness.

| Receiver tokenizer | Raw CTE | Previous v0.6 cold | Previous excess | v0.8 bound warm | v0.8 bound cold | Bound regret | Standalone cold | Standalone excess vs raw |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 18,032 | 18,536 | 2.80% | 18,032 | 18,032 | 0 (0.00%) | 19,128 | 6.08% |
| o200k_base | 18,063 | 18,539 | 2.64% | 18,063 | 18,063 | 0 (0.00%) | 19,120 | 5.85% |
| Qwen2.5-7B-Instruct tokenizer | 22,797 | 23,315 | 2.27% | 22,797 | 22,797 | 0 (0.00%) | 24,346 | 6.80% |
| Mistral-7B-Instruct-v0.3 tokenizer | 26,271 | 26,829 | 2.12% | 26,271 | 26,271 | 0 (0.00%) | 27,894 | 6.18% |

For both contracts, all four cold plans refused every optional artifact and selected Controlled Terse English for `43/43` messages. The warm standalone selector also chose Controlled Terse English for all `172/172` receiver-message pairs. No compact representation produced a strict token win, so every cold plan retained the plain fallback. The positive percentage above raw CTE is the explicit cost of using the standalone security envelope.

## Application and transport bytes

The bound profile models a record-oriented authenticated transport. Its metadata is one mode byte, eight sequence bytes, and a 16-byte HMAC-SHA-256 tag, for exactly 25 bytes per record. The record boundary supplies payload length and is not assigned an invented byte cost. The receiver-facing text contains only the application payload.

The standalone profile uses a 42-character ASCII header per record: `T8`, one mode character, 16 lowercase hexadecimal sequence characters, a 22-character Base64url tag, and a colon. This header remains in the receiver-token count.

| Contract | Receiver text bytes | Separate transport metadata | Complete record bytes | Excess over raw payload bytes |
|---|---:|---:|---:|---:|
| Raw CTE payload | 51,594 | 0 | 51,594 | 0.00% |
| Authenticated bound transport | 51,594 | 1,075 | 52,669 | 2.08% |
| Standalone authenticated text envelope, warm selected | 53,400 | 0 | 53,400 | 3.50% |

The byte result is intentionally different from the token result. Moving metadata outside model input removes receiver-token overhead, but it does not make network metadata disappear.

## Profile and contract cost

The selector contract itself is 1,895 UTF-8 bytes. It is measured below but not charged as an in-prompt session transfer because both v0.8 transport contracts assume that the selection and record contract is installed and negotiated before application messages. If a peer must learn that contract in its prompt, the zero cold-regret result does not apply until that cost is amortized.

| Receiver tokenizer | Selection contract | Optimized grammar + profile | Structured bundle |
|---|---:|---:|---:|
| cl100k_base | 483 tokens / 1,895 B | 487 tokens / 1,795 B | 9,570 tokens / 13,799 B |
| o200k_base | 489 tokens / 1,895 B | 542 tokens / 1,795 B | 9,007 tokens / 13,799 B |
| Qwen2.5-7B-Instruct tokenizer | 553 tokens / 1,895 B | 514 tokens / 1,795 B | 9,719 tokens / 13,799 B |
| Mistral-7B-Instruct-v0.3 tokenizer | 642 tokens / 1,895 B | 673 tokens / 1,795 B | 10,938 tokens / 13,799 B |

Optional artifact cost was included in every cold activation option. Since neither compact representation produced a strict win, the selected artifact cost was zero for every tokenizer.

## Exactness, determinism, and integrity

| Check | Result |
|---|---:|
| Four direct candidate payloads | 172/172 exact; 172/172 deterministic |
| Receiver-specific bound selections | 172/172 exact; 172/172 deterministic |
| Receiver-specific standalone selections | 172/172 exact; 172/172 deterministic |
| Bound delivery of raw CTE and JSON bytes | 86/86 byte-identical |
| Bound mutations and wrong-sequence trials | 860/860 rejected |
| Standalone mutations and wrong-sequence trials | 860/860 rejected |

Each integrity set covers every receiver-message pair. For each record, the harness independently changes the mode, sequence, payload, and tag, then also supplies a wrong expected sequence. The tag is HMAC-SHA-256 truncated to 128 bits and binds the exact mode, sequence, and UTF-8 payload bytes. The public deterministic test key is a fixture, not a deployment secret. A deployment must obtain its key and authenticated session context from a real security protocol. HMAC authentication does not itself grant semantic authority or authorize an external effect.

Raw CTE and JSON without either record contract have no independent keyed integrity guarantee. They are not presented as matched security baselines.

## Current Python path latency

Latency was not rerun as part of this deterministic identity refreeze, so the earlier timing table is not carried forward as a current measurement. The adaptive path constructs and counts four candidate representations before selection and is expected to do more work than plain Controlled Terse English encoding. No current latency improvement claim is made.

## Interpretation boundary

- The exact zero-regret outcome is an implementation invariant over an enumerated candidate set, not a learned prediction.
- The 43 external records were revealed before the design. This is post-hoc development evidence, not fresh confirmation.
- Every bound and standalone selection was raw Controlled Terse English. The current refreeze found zero compact wins.
- Token accounting begins after an exact typed message exists. It excludes model construction, comprehension, task execution, repair, chat templates, and user translation.
- The HMAC harness tests one precise record contract. It is not a TLS, QUIC, A2A, gRPC, or production security implementation.
- The bound profile assumes an authenticated record transport that exposes verified mode and sequence to the adapter but only the exact payload to the model. A transport without this property must use a matched standalone envelope or another explicitly measured binding.
- The study does not measure a new corpus, model comprehension, safely completed tasks, energy, dollar cost, external adoption, or comparison with the best published multi-agent methods.
- No state-of-the-art or generalization claim is supported.

## Frozen artifacts and reproduction

- Implementation SHA-256: `240c8b011733f925467fca9c73e86b523dd2f8758daa63bdbd9e70aa9b3fdeb2`
- Isolated test SHA-256: `0e8ae33f243ff3a5ca64ebffb5f306f5d10dff9e0c31635dacfca6e0602a68d6`
- Isolated tests: `11/11` passed

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python \
  urusilla_transparent_fallback_v08.py --assets-dir work/tokenizer_assets --repeats 1
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m unittest -v \
  test_urusilla_transparent_fallback_v08.py
```

The benchmark verifies the frozen external corpus, four tokenizer fingerprints, train-only alias profile, relevant dependency source digests, selection-contract digest, and complete deterministic snapshot before reporting a result.
