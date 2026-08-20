# Receiver-negotiated token surface v0.7

## Result

All twelve predeclared receiver profiles were derived from the frozen 224-message development partition before the unchanged holdout or out-of-domain sets were evaluated. Exact decode and canonical re-encoding passed for **3,480/3,480** and **3,480/3,480** direct receiver/profile/message cases. The guarded chooser had **0** warm token regressions against the complete v0.6 candidate across **1,160** message/receiver pairs. It saved **23,997** tokens on development and **4,302** on grouped holdout, but **0** on OOD, where every choice remained v0.6.

Cold transfer was unfavorable at the evaluated session lengths: v0.7 was activated in **0/12** exact known-session cold plans, so every cold result retained the existing v0.6 plan.

Deterministic payload corruptions were rejected in **3,480/3,480** trials. Alphabet isolation, repetition, long forward/reverse/permuted concatenation, and actual payload token-ID checks covered **143,360** declared symbol positions in addition to every encoded message.

These are serialization measurements over already-typed messages. No language model, network service, paid API, or external side effect was used. The experiment does not measure comprehension, task success, repair behavior, sender generation, energy, adoption, native model support, or state-of-the-art performance.

## Why the symbol definition changed

A visible single-Unicode-code-point alphabet cannot satisfy all requested sizes. The strict isolated candidate count is shown below. The implemented experimental symbol is instead one canonical ASCII space followed by a nonempty ASCII alphanumeric body. It is a vocabulary token, contains no internal whitespace or delimiter, is uniquely segmented at spaces, and must preserve its exact token ID when concatenated. The leading space is significant; a channel that trims it corrupts the surface and the decoder rejects it.

| Receiver tokenizer | Strict safe single-codepoint | Boundary candidates before prompt-risk filter | After filter | Removed | 1,024 | 2,048 | 4,096 |
|---|---:|---:|---:|---:|---:|---:|---:|
| cl100k_base | 1,050 | 41,366 | 41,268 | 98 | pass | pass | pass |
| o200k_base | 4,545 | 68,059 | 67,962 | 97 | pass | pass | pass |
| Qwen2.5-7B-Instruct tokenizer | 15,513 | 41,547 | 41,449 | 98 | pass | pass | pass |
| Mistral-7B-Instruct-v0.3 tokenizer | 104 | 14,392 | 14,336 | 56 | pass | pass | pass |

This is an explicit relaxation from the earlier non-ASCII single-character surface, not a retroactive claim about v0.3 or v0.4. Added/special tokens, markup, punctuation, controls, bidi formatting, noncharacters, alternate normalization forms, and symbols longer than 64 UTF-8 bytes are excluded. A finite denylist additionally removes direct role markers, common prompt directives, credential terms, and selected high-risk action words; the table measures the resulting capacity loss.

### Mandatory interpretation boundary: decoder before model

Tokenizer-native ASCII tokens can still spell ordinary language, sensitive terms, or prompt-like sequences by accident. Filtering individual high-risk words cannot prove that an arbitrary multi-token sequence is semantically inert. A transport may also trim, collapse, case-fold, or replace whitespace. Therefore this profile is eligible only as decoder-before-model transport: the raw text must be parsed, profile-checked, checksum-checked, canonically decoded, and converted back to validated typed IR before any model sees the content. Raw `R7` text must not be placed in a system, developer, user, tool, or retrieved-context prompt. No direct LLM readability or safe prompt consumption is claimed.

Whitespace trimming at the payload start, removal or collapse of symbol boundaries, replacement with tab/newline/non-breaking space, and case normalization are tested as corruption. Any changed form must fail before semantic use. A checksum detects accidental normalization; it does not make raw word-like text safe against prompt injection if an application violates this decoder boundary.

## Frozen profile identities and cold transfer

The byte entries are trained once with deterministic linked-list byte-pair merging. Each receiver then assigns its shortest safe token strings to entries in descending development-use order. Capsules bind the tokenizer key, implementation string, vocabulary size, full fingerprint, Unicode and safety policy, prompt-risk denylist digest, canonical-encoding and integrity policies, expansion and text bounds, exact development digest, declared size, base v0.2 Capsule digest and dictionary ID, ordered symbols/token IDs, and ordered byte expansions.

| Receiver | Size | Profile SHA-256 | Capsule binary bytes | Text-transfer bytes | Receiver tokens | Alphabet bytes |
|---|---:|---|---:|---:|---:|---:|
| cl100k_base | 1,024 | `b5b98c160879ec821f38d5625fa93201391f400f82bb40153d9a77a7f706ff5b` | 12,163 | 16,222 | 11,156 | 3,020 |
| cl100k_base | 2,048 | `858b8291742cf772fbe40525bca7d6c9f56b141ddb266ede88af8aefcc2acf33` | 27,582 | 36,780 | 25,320 | 6,627 |
| cl100k_base | 4,096 | `a2381c6ae67c3bde5ae0ccb83f1b039993c37a669c4c855b94a07d4efcd69534` | 56,100 | 74,804 | 51,124 | 14,819 |
| o200k_base | 1,024 | `baec66d767f05e7f4efc1f7732583485b08f5fc5e528888d7eeeb4d1c88c443d` | 12,257 | 16,347 | 10,452 | 3,020 |
| o200k_base | 2,048 | `c27a077c96095f1bfb155b57d6d4f5e93efbb0b28cee7f285c8fa4b7cfda4f70` | 27,491 | 36,659 | 23,534 | 6,498 |
| o200k_base | 4,096 | `da2774c4f8da01cf1f18a3b93f01e44e22a7622da8d35b7d355775d245db8256` | 56,159 | 74,883 | 47,869 | 14,690 |
| Qwen2.5-7B-Instruct tokenizer | 1,024 | `d10a1083c6c3f972186d561a64834d3854ae507351f0aec516727c171a54858d` | 12,165 | 16,224 | 11,230 | 3,020 |
| Qwen2.5-7B-Instruct tokenizer | 2,048 | `e67355f42e38ad1e0a9cfb39981d0cfe9c2a0b49a2b2551d91780f8af863d88e` | 27,580 | 36,778 | 25,772 | 6,627 |
| Qwen2.5-7B-Instruct tokenizer | 4,096 | `652e654cce91127e3800b4b0ae1e1ebe490cae06456e4b2c146f49fc2039893b` | 56,092 | 74,794 | 51,699 | 14,819 |
| Mistral-7B-Instruct-v0.3 tokenizer | 1,024 | `2bf907f0428a2d2774a40634bb0d5be19eaf208d185f4ac1e57ce155dae715a6` | 12,083 | 16,115 | 12,574 | 3,223 |
| Mistral-7B-Instruct-v0.3 tokenizer | 2,048 | `51ea8442715b47843ba31d86c13470aa7a79d272ace8a60f21670bc90d140ab8` | 27,654 | 36,876 | 28,923 | 7,319 |
| Mistral-7B-Instruct-v0.3 tokenizer | 4,096 | `c0160f89ebd2b71d63adf026d0cb45e921cabff254027b1bfc1641fe5466c7a4` | 56,498 | 75,335 | 58,422 | 16,713 |

The actual text capsule is `R7C:` plus unpadded Base64url of the canonical binary capsule. Cold costs below also charge the shared v0.2 static profile once when needed. Decoder software and the public specification are treated as installed.

## Warm receiver tokens

Every count covers the complete serialized text, including the receiver-profile tag and 64-bit accidental-corruption checksum. Lower is better. `Guarded` compares the complete v0.6 choice with all three v0.7 profiles for that receiver; v0.6 wins ties.

| Dataset | Receiver | v0.4 | v0.5 | v0.6 | v0.7-1024 | v0.7-2048 | v0.7-4096 | Guarded | Guarded vs v0.6 | Guarded modes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| development training partition | cl100k_base | 23,751 | 24,423 | 24,423 | 26,265 | 21,542 | 18,550 | 18,550 | +24.05% | v07_4096:224 |
| development training partition | o200k_base | 23,560 | 24,232 | 24,232 | 26,604 | 21,876 | 18,455 | 18,455 | +23.84% | v07_4096:224 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 23,610 | 24,282 | 24,282 | 27,653 | 22,042 | 18,375 | 18,375 | +24.33% | v07_4096:224 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 23,859 | 24,755 | 24,755 | 27,627 | 22,216 | 18,315 | 18,315 | +26.01% | v07_4096:224 |
| grouped holdout | cl100k_base | 6,362 | 6,530 | 6,530 | 7,000 | 5,661 | 5,490 | 5,484 | +16.02% | v07_2048:8, v07_4096:48 |
| grouped holdout | o200k_base | 6,310 | 6,478 | 6,478 | 7,099 | 5,769 | 5,479 | 5,479 | +15.42% | v07_4096:56 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 6,333 | 6,501 | 6,501 | 7,343 | 5,793 | 5,450 | 5,448 | +16.20% | v07_2048:1, v07_4096:55 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 6,412 | 6,636 | 6,636 | 7,337 | 5,843 | 5,432 | 5,432 | +18.14% | v07_4096:56 |
| out of domain | cl100k_base | 5,361 | 2,761 | 2,600 | 5,486 | 5,483 | 5,352 | 2,600 | +0.00% | v06:10 |
| out of domain | o200k_base | 5,011 | 2,762 | 2,618 | 5,501 | 5,501 | 5,354 | 2,618 | +0.00% | v06:10 |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 5,353 | 3,192 | 3,065 | 5,551 | 5,506 | 5,346 | 3,065 | +0.00% | v06:10 |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 5,368 | 3,691 | 3,626 | 5,552 | 5,512 | 5,345 | 3,626 | +0.00% | v06:10 |

## Warm UTF-8 bytes

Token selection can still increase bytes, so byte results are reported independently.

| Dataset | Receiver | v0.4 | v0.5 | v0.6 | v0.7-1024 | v0.7-2048 | v0.7-4096 | Guarded | Guarded vs v0.6 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | 57,906 | 58,802 | 58,802 | 66,669 | 52,190 | 45,497 | 45,497 | +22.63% |
| development training partition | o200k_base | 57,906 | 58,802 | 58,802 | 66,669 | 52,190 | 45,239 | 45,239 | +23.07% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 57,906 | 58,802 | 58,802 | 66,669 | 52,190 | 45,497 | 45,497 | +22.63% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 57,906 | 58,802 | 58,802 | 66,669 | 52,625 | 47,008 | 47,008 | +20.06% |
| grouped holdout | cl100k_base | 15,368 | 15,592 | 15,592 | 17,716 | 13,778 | 13,912 | 13,849 | +11.18% |
| grouped holdout | o200k_base | 15,368 | 15,592 | 15,592 | 17,716 | 13,773 | 13,903 | 13,903 | +10.83% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 15,368 | 15,592 | 15,592 | 17,716 | 13,778 | 13,912 | 13,906 | +10.81% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 15,368 | 15,592 | 15,592 | 17,753 | 13,930 | 14,445 | 14,445 | +7.36% |
| out of domain | cl100k_base | 11,465 | 8,552 | 7,248 | 14,795 | 15,002 | 15,439 | 7,248 | +0.00% |
| out of domain | o200k_base | 11,465 | 8,552 | 7,248 | 14,795 | 15,001 | 15,438 | 7,248 | +0.00% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 11,465 | 8,728 | 7,248 | 14,795 | 15,002 | 15,439 | 7,248 | +0.00% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 11,465 | 8,728 | 7,475 | 14,955 | 15,347 | 16,309 | 7,475 | +0.00% |

## Per-message regressions retained

Raw v0.7 profiles are not protected by the chooser and may regress. `Worst token regression` and `worst byte regression` are relative increases for one message. The guarded row must retain zero token regressions but may still select a token win with more bytes. The machine-readable `frozen_results.json` retains all **1,310** message/candidate records having either a positive token delta or a positive UTF-8-byte delta; records identify only the frozen dataset, receiver, message index, candidate, and numeric deltas, not message content.

| Dataset | Receiver | Candidate | Improved / equal / regressed | Tokens saved | Bytes saved | Worst token regression | Worst byte regression |
|---|---|---|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | v0.7-1024 | 0 / 0 / 224 | -1,842 | -7,867 | 14.29% | 21.00% |
| development training partition | cl100k_base | v0.7-2048 | 221 / 1 / 2 | +2,881 | +6,612 | 2.88% | 4.42% |
| development training partition | cl100k_base | v0.7-4096 | 224 / 0 / 0 | +5,873 | +13,305 | 0.00% | 0.00% |
| development training partition | cl100k_base | guarded | 224 / 0 / 0 | +5,873 | +13,305 | 0.00% | 0.00% |
| development training partition | o200k_base | v0.7-1024 | 0 / 0 / 224 | -2,372 | -7,867 | 14.13% | 21.00% |
| development training partition | o200k_base | v0.7-2048 | 220 / 0 / 4 | +2,356 | +6,612 | 5.61% | 4.42% |
| development training partition | o200k_base | v0.7-4096 | 224 / 0 / 0 | +5,777 | +13,563 | 0.00% | 0.00% |
| development training partition | o200k_base | guarded | 224 / 0 / 0 | +5,777 | +13,563 | 0.00% | 0.00% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | v0.7-1024 | 0 / 0 / 224 | -3,371 | -7,867 | 20.24% | 21.00% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | v0.7-2048 | 217 / 2 / 5 | +2,240 | +6,612 | 6.48% | 4.42% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | v0.7-4096 | 224 / 0 / 0 | +5,907 | +13,305 | 0.00% | 0.00% |
| development training partition | Qwen2.5-7B-Instruct tokenizer | guarded | 224 / 0 / 0 | +5,907 | +13,305 | 0.00% | 0.00% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-1024 | 0 / 0 / 224 | -2,872 | -7,867 | 18.68% | 21.00% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-2048 | 218 / 3 / 3 | +2,539 | +6,177 | 4.59% | 5.34% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-4096 | 224 / 0 / 0 | +6,440 | +11,794 | 0.00% | 0.00% |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | guarded | 224 / 0 / 0 | +6,440 | +11,794 | 0.00% | 0.00% |
| grouped holdout | cl100k_base | v0.7-1024 | 0 / 0 / 56 | -470 | -2,124 | 9.90% | 18.33% |
| grouped holdout | cl100k_base | v0.7-2048 | 56 / 0 / 0 | +869 | +1,814 | 0.00% | 0.00% |
| grouped holdout | cl100k_base | v0.7-4096 | 56 / 0 / 0 | +1,040 | +1,680 | 0.00% | 3.37% |
| grouped holdout | cl100k_base | guarded | 56 / 0 / 0 | +1,046 | +1,743 | 0.00% | 3.37% |
| grouped holdout | o200k_base | v0.7-1024 | 0 / 0 / 56 | -621 | -2,124 | 14.00% | 18.33% |
| grouped holdout | o200k_base | v0.7-2048 | 56 / 0 / 0 | +709 | +1,819 | 0.00% | 0.00% |
| grouped holdout | o200k_base | v0.7-4096 | 56 / 0 / 0 | +999 | +1,689 | 0.00% | 3.37% |
| grouped holdout | o200k_base | guarded | 56 / 0 / 0 | +999 | +1,689 | 0.00% | 3.37% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | v0.7-1024 | 0 / 0 / 56 | -842 | -2,124 | 16.83% | 18.33% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | v0.7-2048 | 56 / 0 / 0 | +708 | +1,814 | 0.00% | 0.00% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | v0.7-4096 | 56 / 0 / 0 | +1,051 | +1,680 | 0.00% | 3.37% |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | guarded | 56 / 0 / 0 | +1,053 | +1,686 | 0.00% | 3.37% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-1024 | 0 / 0 / 56 | -701 | -2,161 | 14.56% | 19.12% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-2048 | 56 / 0 / 0 | +793 | +1,662 | 0.00% | 0.40% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-4096 | 56 / 0 / 0 | +1,204 | +1,147 | 0.00% | 6.74% |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | guarded | 56 / 0 / 0 | +1,204 | +1,147 | 0.00% | 6.74% |
| out of domain | cl100k_base | v0.7-1024 | 0 / 0 / 10 | -2,886 | -7,547 | 138.87% | 126.29% |
| out of domain | cl100k_base | v0.7-2048 | 0 / 0 / 10 | -2,883 | -7,754 | 138.49% | 128.27% |
| out of domain | cl100k_base | v0.7-4096 | 0 / 0 / 10 | -2,752 | -8,191 | 132.48% | 134.48% |
| out of domain | cl100k_base | guarded | 0 / 10 / 0 | +0 | +0 | 0.00% | 0.00% |
| out of domain | o200k_base | v0.7-1024 | 0 / 0 / 10 | -2,883 | -7,547 | 139.10% | 126.29% |
| out of domain | o200k_base | v0.7-2048 | 0 / 0 / 10 | -2,883 | -7,753 | 139.10% | 128.27% |
| out of domain | o200k_base | v0.7-4096 | 0 / 0 / 10 | -2,736 | -8,190 | 131.58% | 134.48% |
| out of domain | o200k_base | guarded | 0 / 10 / 0 | +0 | +0 | 0.00% | 0.00% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | v0.7-1024 | 0 / 0 / 10 | -2,486 | -7,547 | 111.70% | 126.29% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | v0.7-2048 | 0 / 0 / 10 | -2,441 | -7,754 | 110.19% | 128.27% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | v0.7-4096 | 0 / 0 / 10 | -2,281 | -8,191 | 104.53% | 134.48% |
| out of domain | Qwen2.5-7B-Instruct tokenizer | guarded | 0 / 10 / 0 | +0 | +0 | 0.00% | 0.00% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-1024 | 0 / 0 / 10 | -1,926 | -7,480 | 73.37% | 128.01% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-2048 | 0 / 0 / 10 | -1,886 | -7,872 | 72.76% | 132.76% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | v0.7-4096 | 0 / 0 / 10 | -1,719 | -8,834 | 68.11% | 146.90% |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | guarded | 0 / 10 / 0 | +0 | +0 | 0.00% | 0.00% |

## Strict mean break-even against warm v0.6

The first strict win is the smallest integer `N` satisfying `cold + N × candidate_mean < N × v0.6_mean`. Token and UTF-8-byte thresholds are computed separately. Each cold value charges the receiver profile text and shared v0.2 static profile. `Never on mean` is retained when the raw v0.7 warm mean is not smaller.

| Dataset | Receiver | Profile | Cold tokens | Token break-even | Cold bytes | Byte break-even |
|---|---|---:|---:|---:|---:|---:|
| development training partition | cl100k_base | 1,024 | 12,502 | never on mean | 18,094 | never on mean |
| development training partition | cl100k_base | 2,048 | 26,666 | 2,074 | 38,652 | 1,310 |
| development training partition | cl100k_base | 4,096 | 52,470 | 2,002 | 76,676 | 1,291 |
| development training partition | o200k_base | 1,024 | 11,713 | never on mean | 18,219 | never on mean |
| development training partition | o200k_base | 2,048 | 24,795 | 2,358 | 38,531 | 1,306 |
| development training partition | o200k_base | 4,096 | 49,130 | 1,905 | 76,755 | 1,268 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 1,024 | 12,605 | never on mean | 18,096 | never on mean |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 2,048 | 27,147 | 2,715 | 38,650 | 1,310 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 4,096 | 53,074 | 2,013 | 76,666 | 1,291 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 1,024 | 14,090 | never on mean | 17,987 | never on mean |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 2,048 | 30,439 | 2,686 | 38,748 | 1,406 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 4,096 | 59,938 | 2,085 | 77,207 | 1,467 |
| grouped holdout | cl100k_base | 1,024 | 12,502 | never on mean | 18,094 | never on mean |
| grouped holdout | cl100k_base | 2,048 | 26,666 | 1,719 | 38,652 | 1,194 |
| grouped holdout | cl100k_base | 4,096 | 52,470 | 2,826 | 76,676 | 2,556 |
| grouped holdout | o200k_base | 1,024 | 11,713 | never on mean | 18,219 | never on mean |
| grouped holdout | o200k_base | 2,048 | 24,795 | 1,959 | 38,531 | 1,187 |
| grouped holdout | o200k_base | 4,096 | 49,130 | 2,755 | 76,755 | 2,545 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 1,024 | 12,605 | never on mean | 18,096 | never on mean |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 2,048 | 27,147 | 2,148 | 38,650 | 1,194 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 4,096 | 53,074 | 2,828 | 76,666 | 2,556 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 1,024 | 14,090 | never on mean | 17,987 | never on mean |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 2,048 | 30,439 | 2,150 | 38,748 | 1,306 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 4,096 | 59,938 | 2,788 | 77,207 | 3,770 |
| out of domain | cl100k_base | 1,024 | 12,502 | never on mean | 18,094 | never on mean |
| out of domain | cl100k_base | 2,048 | 26,666 | never on mean | 38,652 | never on mean |
| out of domain | cl100k_base | 4,096 | 52,470 | never on mean | 76,676 | never on mean |
| out of domain | o200k_base | 1,024 | 11,713 | never on mean | 18,219 | never on mean |
| out of domain | o200k_base | 2,048 | 24,795 | never on mean | 38,531 | never on mean |
| out of domain | o200k_base | 4,096 | 49,130 | never on mean | 76,755 | never on mean |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 1,024 | 12,605 | never on mean | 18,096 | never on mean |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 2,048 | 27,147 | never on mean | 38,650 | never on mean |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 4,096 | 53,074 | never on mean | 76,666 | never on mean |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 1,024 | 14,090 | never on mean | 17,987 | never on mean |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 2,048 | 30,439 | never on mean | 38,748 | never on mean |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 4,096 | 59,938 | never on mean | 77,207 | never on mean |

## Exact known-session cold planning

The planner enumerates 64 activation states: the three existing v0.6 artifact gates and every subset of the three receiver profiles. The shared v0.2 profile is charged once. The complete v0.6 cold plan remains an exact option and wins ties through the deterministic ordering.

| Dataset | Receiver | v0.6 cold total | Selected total | Saving | Cold tokens | Old structured / symbolic / optimized | Active v0.7 sizes | Selected modes |
|---|---|---:|---:|---:|---:|---|---|---|
| development training partition | cl100k_base | 33,993 | 33,993 | +0.00% | 9,570 | true / false / false | none | v06:224 |
| development training partition | o200k_base | 33,239 | 33,239 | +0.00% | 9,007 | true / false / false | none | v06:224 |
| development training partition | Qwen2.5-7B-Instruct tokenizer | 34,001 | 34,001 | +0.00% | 9,719 | true / false / false | none | v06:224 |
| development training partition | Mistral-7B-Instruct-v0.3 tokenizer | 35,693 | 35,693 | +0.00% | 10,938 | true / false / false | none | v06:224 |
| grouped holdout | cl100k_base | 13,570 | 13,570 | +0.00% | 487 | false / false / true | none | v06:56 |
| grouped holdout | o200k_base | 13,699 | 13,699 | +0.00% | 542 | false / false / true | none | v06:56 |
| grouped holdout | Qwen2.5-7B-Instruct tokenizer | 16,220 | 16,220 | +0.00% | 9,719 | true / false / false | none | v06:56 |
| grouped holdout | Mistral-7B-Instruct-v0.3 tokenizer | 17,574 | 17,574 | +0.00% | 10,938 | true / false / false | none | v06:56 |
| out of domain | cl100k_base | 2,761 | 2,761 | +0.00% | 0 | false / false / false | none | v06:10 |
| out of domain | o200k_base | 2,762 | 2,762 | +0.00% | 0 | false / false / false | none | v06:10 |
| out of domain | Qwen2.5-7B-Instruct tokenizer | 3,220 | 3,220 | +0.00% | 0 | false / false / false | none | v06:10 |
| out of domain | Mistral-7B-Instruct-v0.3 tokenizer | 3,726 | 3,726 | +0.00% | 0 | false / false / false | none | v06:10 |

## Reference implementation latency

Times are per message on this machine over the fixed 290-message combined sequence with the requested repeat count (one in the frozen report), fixed order, and Python garbage collection disabled during timed loops. Direct rows include canonical v0.2 encoding/decoding, optimal byte parsing, receiver tokenization, checksum validation, and canonical re-encoding. Fresh chooser rows rebuild all candidates. Paths do unequal work and are not protocol-intrinsic limits.

| Receiver | Direct profile | Encode p50 / p95 | Decode p50 / p95 |
|---|---:|---:|---:|
| cl100k_base | 1,024 | 399.2 / 574.2 us | 571.2 / 894.9 us |
| cl100k_base | 2,048 | 392.9 / 511.5 us | 545.8 / 761.2 us |
| cl100k_base | 4,096 | 496.9 / 626.2 us | 629.2 / 863.9 us |
| o200k_base | 1,024 | 439.3 / 563.6 us | 635.0 / 892.6 us |
| o200k_base | 2,048 | 484.0 / 704.2 us | 592.3 / 768.4 us |
| o200k_base | 4,096 | 529.8 / 678.3 us | 702.2 / 918.2 us |
| Qwen2.5-7B-Instruct tokenizer | 1,024 | 701.1 / 843.4 us | 881.1 / 1075.2 us |
| Qwen2.5-7B-Instruct tokenizer | 2,048 | 700.9 / 797.8 us | 834.9 / 1025.0 us |
| Qwen2.5-7B-Instruct tokenizer | 4,096 | 731.6 / 888.5 us | 903.9 / 1084.5 us |
| Mistral-7B-Instruct-v0.3 tokenizer | 1,024 | 423.0 / 535.5 us | 581.8 / 777.6 us |
| Mistral-7B-Instruct-v0.3 tokenizer | 2,048 | 460.2 / 563.7 us | 619.0 / 804.8 us |
| Mistral-7B-Instruct-v0.3 tokenizer | 4,096 | 531.2 / 643.5 us | 673.4 / 864.1 us |

| Receiver | Chooser | Select p50 / p95 | Decode p50 / p95 |
|---|---|---:|---:|
| cl100k_base | v06 | 4345.1 / 6155.0 us | 1848.8 / 2118.1 us |
| cl100k_base | guarded_v07 | 6006.0 / 8306.6 us | 647.1 / 851.4 us |
| o200k_base | v06 | 4471.5 / 6226.7 us | 1743.6 / 2020.3 us |
| o200k_base | guarded_v07 | 6277.7 / 8497.3 us | 711.3 / 932.1 us |
| Qwen2.5-7B-Instruct tokenizer | v06 | 6605.2 / 8981.7 us | 1739.9 / 2023.2 us |
| Qwen2.5-7B-Instruct tokenizer | guarded_v07 | 9721.0 / 12477.7 us | 900.4 / 1067.9 us |
| Mistral-7B-Instruct-v0.3 tokenizer | v06 | 4887.0 / 6585.9 us | 1738.9 / 1995.8 us |
| Mistral-7B-Instruct-v0.3 tokenizer | guarded_v07 | 6567.5 / 8671.0 us | 676.3 / 859.3 us |

## Exactness, corruption, bounds, and binding

- Direct exact semantic recovery: 3,480/3,480.
- Direct canonical deterministic re-encoding: 3,480/3,480.
- Guarded selected recovery and deterministic reselection: 1,160/1,160 and 1,160/1,160.
- Deterministic payload mutation rejection: 3,480/3,480.
- Capsule decoding checks the exact receiver key and full tokenizer fingerprint, Unicode policy, training digest, base v0.2 profile, declared cardinality, token IDs, byte expansions, checksum, and canonical byte equality.
- Surface decoding checks the 96-bit profile tag against one pinned full profile, unique space segmentation, exact concatenated token IDs, a 262,144-symbol limit, cumulative 16 MiB frame expansion, the profile-bound checksum, v0.2 validation, and canonical optimal re-encoding. An ineligible oversized v0.7 candidate fails closed to the complete v0.6 chooser path.
- The checksum detects accidental corruption only. It is not authentication, a signature, replay protection, or authority against an attacker who can recompute it.
- Raw surfaces are decoder-before-model transport only. Prompt exposure is an application-policy failure even when the surface is structurally valid.

## Frozen inputs and artifact identities

- Development: 224 messages, `f4b93d600d7199c26069e9b21cdfa13a684369eab9bad67448d14406b1a82759`.
- Grouped holdout: 56 messages, `6fbf24c1a3d7bf6bb7ba49b24dca79387a120957506d2ac49521bf0c9a1cc5b9`.
- Out of domain: 10 messages, `4e8c265e778cb0ce6d2e1122ad35e85e45dcfa3233e09937521c852f22414310`.
- Byte-entry sequence SHA-256: `01d3495f20ba18e79ec484c22f8f6395b88a7cdce4efc2a7088e2c4897c9ea6b`.
- Deterministic study snapshot SHA-256: `5c287f7eb6c34d7f9eb62593cff5a1e0ab978a86175daed7da896f23466f4b82`.
- Byte-entry training and twelve-profile assembly wall time, excluding tokenizer loading and vocabulary enumeration: 1.340s.
- Runtime: `CPython 3.12.14` / `macOS-15.0-arm64-arm-64bit`.
- Tokenizer packages: `tiktoken==0.11.0`, `tokenizers==0.21.4`.
- Implementation SHA-256: `9ee20b19b99f8ab71d702df520fc19e2fe3dfb5a79dfb9264b695b22fe83bafa`.
- Test-suite SHA-256: `a0be43ecce078b1089f8b5469b85992b01557684f6e3cad411ad4347a1707780`.

This is an unsigned downstream research artifact derived from the existing experimental language repository stewarded by `jaden3824`. The working tree has no committed implementation revision, so the exact file digests above identify this run. They do not establish conformance, adoption, endorsement, or authority.

## Limitations

- Development is in-sample. Grouped holdout shares the synthetic generator family, and OOD contains only ten repository-authored messages.
- The boundary-token alphabet intentionally uses readable ASCII word fragments and significant leading spaces. It changes the older non-ASCII single-character threat and transport assumptions. Channels that normalize whitespace are ineligible even though corruption is detected.
- The finite prompt-risk denylist lowers direct leakage but cannot eliminate accidental directives, sensitive language, or meaningful multi-token phrases. The raw surface is not a prompt format and has no direct-LLM-readability claim.
- Long concatenation and every observed payload are verified exactly, but this is evidence for four pinned tokenizer implementations and fingerprints only. A tokenizer update requires a new profile.
- The cold planner is an offline optimum for a known sequence. An unknown-horizon streaming runtime needs a conservative activation policy and may not achieve it.
- Counts exclude chat templates, BOS/EOS, prompts, HTTP envelopes, retransmission, negotiation round trips, and hosted billing rules.
- No model was asked to understand or generate the surfaces. Token reduction does not establish lower energy, latency, memory, money, or total task cost.
- No external benchmark search or independent reproduction was performed. Unfavorable raw-profile regressions, cold non-break-even cases, byte growth, and slower paths are retained above.

## Offline reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv-research-py312/bin/python -m unittest performance_v07/test_receiver_negotiated_surface_v07.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv-research-py312/bin/python performance_v07/receiver_negotiated_surface_v07.py --benchmark --assets-dir work/tokenizer_assets --repeats 1
```

Both commands are offline and reject missing or mismatched tokenizer assets.
