# Urusilla Competitive Public-Task Preflight

Status: completed zero-call preflight  
Date: 2026-08-20  
Track: external symbolic dialogue only

## Result

The pinned HotpotQA and WikiHop artifacts passed byte, record-count, and strict
field validation. The harness produced 5,382 exact initial prompts across three
data seeds, two evidence-allocation modes where allowed, three representation
arms, two agents, and four pinned tokenizers. The complete prompt-set SHA-256 is
`1b7b8d415812a358dbe92d1fcd158f69a57884f6bb735ec0855c0f624b26c7c9`.

No task success was measured. No model, provider, tool, judge, or paid API was
called. This report does not establish model understanding, answer quality,
non-inferiority, total-task savings, energy savings, competitive performance,
near-leading performance, or leading performance. It is an A0 input and budget
preflight only.

The requested 40-item, three-arm A1 design has 360 episodes and at most 2,880
base calls: 1,920 paid and 960 local. Under the conservative assumptions in this
report, its estimated paid cost is $4.492993, or $5.391592 after a 20% retry and
price reserve. The preregistered $40 approval ceiling remains the controlling
cap because hosted token accounting and prices can differ from local proxies.

## Frozen public inputs

Both files came only from the official AutoForm repository at commit
[`8df94501c462e7f7b4708e5f0297fbdcf8e12ffa`](https://github.com/thunlp/AutoForm/tree/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa).
The repository code is [Apache-2.0](https://github.com/thunlp/AutoForm/blob/8df94501c462e7f7b4708e5f0297fbdcf8e12ffa/LICENSE).
The raw files remain in ignored `work/` storage and are not added as project
artifacts.

| Family | Pinned path | Records | Required fields | Context blocks | SHA-256 | Dataset access and license |
| --- | --- | ---: | ---: | ---: | --- | --- |
| HotpotQA | `data/hotpot_qa/test_single.jsonl` | 100 | 7 | 1,000; exactly 10 per item | `eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284` | [Official site](https://hotpotqa.github.io/); [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| WikiHop | `data/wiki_hop_qa/test_processed.jsonl` | 100 | 3 | 1,702; 4 to 48 per item | `724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39` | [QAngaroo v1.1 archive](https://zenodo.org/records/6407402); [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |

The exact HotpotQA field set is `answer`, `context`, `id`, `input`, `level`,
`supporting_paragraphs`, and `type`. The exact WikiHop field set is `answer`,
`context`, and `input`. Missing, extra, mistyped, empty, reordered-source, or
digest-changed data fails closed. The gold `answer` value is validated but never
read by prompt rendering. A test changes only `answer` and requires every
rendered prompt to stay byte-identical.

## Evidence allocation and forced-stratum boundary

The data-order seeds are `20240826`, `20250424`, and `20260820`. For each item,
SHA-256 ranks each context using the format ID, dataset, seed, item key, original
context index, and exact context bytes. Alternating ownership starts with agent
A. This avoids runtime-specific random-number behavior and keeps the allocation
identical across arms.

HotpotQA includes gold supporting paragraph text. Ninety-nine items have at
least two gold paragraphs that map uniquely to at least two context blocks and
are therefore eligible for a forced distributed-evidence split. One item,
source index 13, is excluded because two gold paragraphs each match duplicate
context blocks; choosing one would invent evidence ownership. A forced split
places gold context on both agents and preserves every context exactly once.

| Seed | Eligible HotpotQA items | Naturally distributed | Forced distributed |
| ---: | ---: | ---: | ---: |
| 20240826 | 99 | 55 | 99 |
| 20250424 | 99 | 64 | 99 |
| 20260820 | 99 | 61 | 99 |

The pinned WikiHop artifact has no gold support annotation. All 100 items are
therefore ineligible for a claim-bearing forced stratum. Alternating allocation
is available, but neither an answer-bearing heuristic nor a model guess is
treated as known support. A WikiHop forced-stratum result remains blocked until
an official item-aligned support manifest is pinned.

Exact split-manifest SHA-256 values:

| Family | Seed | Mode | SHA-256 |
| --- | ---: | --- | --- |
| HotpotQA | 20240826 | alternating | `b554fd496a4dc4b448a15c895dd3ef4b819d3448090a015a426f7da1a89cd748` |
| HotpotQA | 20240826 | forced | `6fd431148a726a83d2d57cdcddf3cf453f5919313c2eab4c56b62bf0de02c4a7` |
| HotpotQA | 20250424 | alternating | `359e4c9d619321faa69a05dbf5ce086297e47e8718e4a6cf62c83bb877ff0f9d` |
| HotpotQA | 20250424 | forced | `a70a127972a7de8898b371e01aaa71c08bc37926d053fcdf3e4d8ae387399145` |
| HotpotQA | 20260820 | alternating | `ca86017e89707a1c6ceb0e966adddd7ea7774314d8360d8bb7adc704f2d8ea8e` |
| HotpotQA | 20260820 | forced | `2872701267fd42e39ffea51fb40e9638b031ea97c1567f544a3649dd4f1bf063` |
| WikiHop | 20240826 | alternating | `9a5dcd2bea740b16839651fa88e241f8a960760b5a83e49f62942fb13ea25208` |
| WikiHop | 20250424 | alternating | `1e28152547d6b99370e407b6b1176bafc78d484ddbd0bf9c05c01205b1d76b0d` |
| WikiHop | 20260820 | alternating | `d15788b0f7c51c6bc6dc19db049eb3957e711f61028495287a84879001d66b57` |

## Prompt lock

Each initial prompt fixes the agent identity, partner identity, strict
alternation, stop rule, question, private evidence with original context index,
and one output contract. The only arm-specific text is the frozen output
contract:

- Controlled Terse English (CTE), contract SHA-256
  `51d1d56aad635ff10c5883cd6f09691a1c45af3a80c9729a6439d4145443deac`.
- Canonical minified JSON, contract SHA-256
  `f330179b6cb10cff5c44992405d208d1a68664a45cb78a34e762db2dbc7da1a5`.
- Current adaptive bridge, contract SHA-256
  `f83489a3dca68e1eb4e94d8d20207c3e6fd8bf0d44d496f1fa4ea3cc8581ef74`.

The adaptive arm is explicitly bridge mode. Its output record is validated and
then mapped to the negotiated receiver-specific surface. This preflight does
not show that a model can produce or understand that surface natively. The
current implementation is pinned by SHA-256
`85ab4676698acb2a887e31c297ed938d09c898a39d645b710a71149064fce753`,
the profile by `f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d`,
and its frozen local snapshot by
`81993226c8fe9b2bd631a2e63e59355fa8e31e993ecbe14af1848a9c5a44bb57`.

The prompt manifest contains 5,382 rows and 5,358 unique prompt-text digests.
The remaining 24 rows are exact repeated texts caused by repeated allocation
outcomes; they are not hash collisions. The ignored cache stores every
item-level prompt digest. Group sequence digests below bind the item key, agent,
and prompt digest in source order.

| Prompt group | Sequence SHA-256 |
| --- | --- |
| `hotpotqa|20240826|alternating|cte` | `c9c2699deda0f3f050ed37ed2b0950bba6ceb951a5c273aa835aea5335e3ce14` |
| `hotpotqa|20240826|alternating|json` | `73e3770d56f160bdae34349cc6f81d95c2938b282e8ada068c22e5ee183300ab` |
| `hotpotqa|20240826|alternating|adaptive` | `fd63da34363f3b3707a2bdfcd4ee2330aff8058243da70b932985f5ed4b20336` |
| `hotpotqa|20240826|forced|cte` | `6c31ede82c9758cb28e411e459009af6bca10885e1613f4ebdebe6b78f45d20e` |
| `hotpotqa|20240826|forced|json` | `ad32cae386cbc872061553c930fef38114821d69112e46ed7a1273c564540f05` |
| `hotpotqa|20240826|forced|adaptive` | `4935659f8799fb8db307c0999aa128a5b0c9a7cb0eac6192d7f295bba85d7d4e` |
| `hotpotqa|20250424|alternating|cte` | `21b31fa0f0771a3a938aedcb9c215ac75edda0dd6a5b20f1162d04b30ce7f733` |
| `hotpotqa|20250424|alternating|json` | `44f5e947a532d88fbccf5148f6c7baa36a67b78d6c14323e956df4ca936371ab` |
| `hotpotqa|20250424|alternating|adaptive` | `4a28f70fc149649eadd6e863687a84bf47e3084a779cfaacb47580d3b0b482a6` |
| `hotpotqa|20250424|forced|cte` | `53b1df4eee80f89b9c569cba8cfa4b343eba150d139ffe3feb951ad06949bedf` |
| `hotpotqa|20250424|forced|json` | `482cbc43f91fd74b156ddf3235c8685bb53e47bb006b1354f35e1952ec2a617e` |
| `hotpotqa|20250424|forced|adaptive` | `c04074b273edeca35a11adda4b6093c40ef1103c57f4b8c993d4069152dd84a4` |
| `hotpotqa|20260820|alternating|cte` | `58da8f6a185d5532189ea76f3915f828166ad8bb8d72d0e946cb81004ed6b4ae` |
| `hotpotqa|20260820|alternating|json` | `b404cb69fc153f273e91c22c9254cec7ad79d8ca984519aa2b5dab65aa68be74` |
| `hotpotqa|20260820|alternating|adaptive` | `000dc1d989b35f33aa570285a8ecd6346e3741d46d276cad43123b34e687dd8b` |
| `hotpotqa|20260820|forced|cte` | `4b39005549d8278da7fb930b66c9719906152b799f43cd4258e3ce4ee079e3e3` |
| `hotpotqa|20260820|forced|json` | `7294f6bf77a612fb5415504ec08d95a6f29be17cb188b91ab9f255884927a636` |
| `hotpotqa|20260820|forced|adaptive` | `2a46daab83cb5e8288bb87692cf1a3f5f2c8363ed65c5feba6ba6f2bbe97d4f0` |
| `wikihop|20240826|alternating|cte` | `707815dfb6e9c9f590138709f29d0dc4336e442c63a03bfce5dec69989907181` |
| `wikihop|20240826|alternating|json` | `49979372077c031f53d8ebc9d1dd2638af228f55d85a88f581b8cd7ad32ec661` |
| `wikihop|20240826|alternating|adaptive` | `336ab33e5d91025632d8360d176dd4899928ffd294e1013791fb3f718980ba2b` |
| `wikihop|20250424|alternating|cte` | `1bd48b1739bc8b5319797751dd2158891623f9aa40573ecde668e6d114ccb919` |
| `wikihop|20250424|alternating|json` | `783317c268d23f8699ef20bb4b44fb5650f1cec8e8ed7bd1322f111a88084080` |
| `wikihop|20250424|alternating|adaptive` | `206831a0b7e70dd4c6e4e21a7bf0ae9d401c0d69476bf9da542a1a0e69c7ded6` |
| `wikihop|20260820|alternating|cte` | `bfcde37f7e637f4e1b7bdf061bc3ea2773afa9e1a9a75a00479f6737084875f7` |
| `wikihop|20260820|alternating|json` | `0344758d7dce516019f759f6c4c9a1af617c09d04cacf4877537905879c95a57` |
| `wikihop|20260820|alternating|adaptive` | `d88a753ff5a1a3bac1edce870db07bd39ee9f12e637a436ae9b0f5b8c0deff90` |

## Four-tokenizer accounting

Dependencies are pinned to `tiktoken==0.11.0` and `tokenizers==0.21.4`.
Counts exclude BOS/EOS, provider chat templates, HTTP envelopes, and any later
dialogue history. Each prompt is counted independently at its request boundary.

| Tokenizer | Vocabulary | Fingerprint |
| --- | ---: | --- |
| `cl100k_base` | 100,277 | `71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d` |
| `o200k_base` | 200,019 | `09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc` |
| Qwen2.5-7B-Instruct | 151,665 | `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539` |
| Mistral-7B-Instruct-v0.3 | 32,768 | `e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49` |

Exact aggregate initial-prompt token counts across all three seeds:

| Family and split | Arm | Prompts | UTF-8 bytes | cl100k | o200k | Qwen | Mistral |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HotpotQA alternating | CTE | 600 | 2,352,204 | 555,223 | 547,366 | 573,154 | 644,412 |
| HotpotQA alternating | JSON | 600 | 2,328,804 | 553,423 | 547,366 | 571,354 | 641,412 |
| HotpotQA alternating | adaptive | 600 | 2,504,004 | 604,423 | 598,366 | 632,554 | 705,612 |
| HotpotQA forced | CTE | 594 | 2,329,356 | 549,898 | 542,077 | 567,682 | 637,959 |
| HotpotQA forced | JSON | 594 | 2,306,190 | 548,116 | 542,077 | 565,900 | 634,989 |
| HotpotQA forced | adaptive | 594 | 2,479,638 | 598,606 | 592,567 | 626,488 | 698,547 |
| WikiHop alternating | CTE | 600 | 3,357,441 | 789,217 | 778,753 | 814,537 | 919,884 |
| WikiHop alternating | JSON | 600 | 3,334,041 | 787,417 | 778,753 | 812,737 | 916,884 |
| WikiHop alternating | adaptive | 600 | 3,509,241 | 838,417 | 829,753 | 873,937 | 981,084 |

The adaptive contract has the largest initial-prompt total in every reported
row. This unfavorable result is retained. It is not yet balanced against
runtime message length, exact recovery, repairs, or task success, so no net
efficiency conclusion is valid. Exact minimum, p25, p50, p75, p95, maximum,
task-slice, and role-slice counts are retained in the ignored snapshot.

For a conservative cold charge, the preflight counts every currently available
grammar, profile, and structured bundle once per endpoint, even though a future
negotiation may select a smaller subset:

| Tokenizer | All cold artifacts, tokens | All cold artifacts, UTF-8 bytes |
| --- | ---: | ---: |
| cl100k | 10,170 | 16,005 |
| o200k | 9,661 | 16,005 |
| Qwen | 10,348 | 16,005 |
| Mistral | 11,750 | 16,005 |

## Cheapest A1 call and cost preflight

The fixed item set contains 20 HotpotQA forced-split items and 20 WikiHop
alternating-split items at seed `20260820`. Its SHA-256 is
`9eee61ecaeee10a0b2826bd0eaeb541fd3e6da0c047ea7043213a9b7c4ea675d`.
It uses CTE, JSON, and current adaptive arms; ordered pairs O-to-G, G-to-Q, and
Q-to-O; one repeat; and eight calls per episode. This is the requested local
preflight variant, not a change to any later preregistered full matrix.

| Quantity | Count |
| --- | ---: |
| Items | 40 |
| Episodes | 360 |
| Maximum base calls | 2,880 |
| Paid calls | 1,920 |
| Local calls | 960 |
| Paid final calls | 240 |
| Local final calls | 120 |
| 20% all-call reserve | 576 |
| 20% paid-call reserve | 384 |

Planning prices were checked on 2026-08-20: [OpenAI GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini)
at $0.25 per million input tokens and $2.00 per million output tokens, and
[Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/latest-model) at the
listed promotional $0.75 input and $3.75 output rates. Prices are assumptions,
not quotes. The Google estimate uses the maximum local count across the four
pinned tokenizers because provider billing telemetry is unavailable before a
call.

| Scenario | Output per call | History reserve per prior message | Request reserve | Paid estimate | With 20% reserve |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lower planning | 80 | 16 | 64 | $2.868193 | $3.441832 |
| Conservative upper | 250 | 32 | 128 | $4.492993 | $5.391592 |

In the conservative upper scenario, G has 3,199,608 estimated input tokens,
240,000 output tokens, and $3.299706 cost. O has 2,853,148 estimated input
tokens, 240,000 output tokens, and $1.193287 cost. The local Q lane has 2,955,080
estimated input tokens and 240,000 output tokens; accelerator cost is unknown.
Initial prompts are replayed on every call, prior outputs grow history, and all
cold artifacts are charged to each endpoint in the adaptive arm.

## Ledger boundary

| Category | Preflight treatment |
| --- | --- |
| `task_input` | Initial question and private-evidence slices counted locally; every future replay must count again |
| `system_role` | Initial role, stop rule, and output-contract slices counted locally |
| `agent_input_history` | Bounded by the two planning scenarios; no observed value |
| `agent_output_visible` | 80 to 250 tokens per call assumed; no observed value |
| `final_answer` | Last call classified separately for planning; no observed value |
| `format_induction` | Zero model tokens in this preflight |
| `encode_decode_model` | Zero model tokens; deterministic local bridge planned |
| `negotiation_profile` | All current cold artifacts charged once per endpoint |
| `repair_retry` | Zero observed; 20% call and price reserve |
| `tool_request`, `tool_result` | Zero by protocol |
| `safety_filter` | Zero here; any future call must be logged |
| `judge` | Zero here; future judge use stays outside runtime efficiency and inside study cost |
| `hidden_reasoning_billed` | Unknown until provider usage is returned |

Initial prompt UTF-8 bytes and cold-artifact bytes are measured. Agent-message
payload bytes, complete envelopes, retransmissions, conversion time, queue time,
network time, model time, repair time, and end-to-end p50/p95 latency are not
observable in this zero-call preflight. They must remain separate measured axes
in a scored run. Provider energy is also unknown.

## Claim and promotion gates

This preflight cannot pass the performance policy's task gate. A later scored
run must keep every malformed, refused, timed-out, repaired, and fallback
episode in the denominator; measure exact match, token F1, ROUGE-L, safe task
success, every ledger category, wire bytes, and latency; and run the
preregistered one-sided non-inferiority analysis with a -1.0 percentage-point
margin. A competitive token claim additionally needs a lower confidence bound
of at least 25% reduction against CTE on each qualifying family, three model
families, unseen cross-family pairings, three repeats, and sufficient unique
items. No serialization-only result can satisfy those gates.

Open blockers are:

1. WikiHop forced evidence cannot be identified from this artifact without an
   official gold-support manifest.
2. One HotpotQA item has ambiguous duplicate context matches and is excluded
   from forced evidence rather than guessed.
3. Provider chat templates, billing tokenizers, hidden tokens, endpoint drift,
   and actual prices are not available from a local replay.
4. No output exists yet, so parsing, repair, fallback, answer quality, full wire
   cost, and end-to-end latency remain unmeasured.
5. The 100-item families may be underpowered for the one-point margin; the
   preregistered paired-discordance power audit is still required before claim
   use.

## Validation results

- Isolated preflight suite: 16 tests passed in 54.196 seconds.
- Complete repository status: see the commit-bound CI run for the release revision; this frozen preflight does not assert a mutable repository-wide test count.

The isolated preflight command used the pinned Python 3.12 research environment
with bytecode generation disabled. No preflight test initiated a provider or
model call. The release revision's repository-wide environment and result must
be read from its CI run.

## Reproduction and frozen result

From the repository root, with the two public artifacts already in ignored
cache:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python competitive_public_task_preflight.py --offline
PYTHONDONTWRITEBYTECODE=1 .venv-research-py312/bin/python -m unittest test_competitive_public_task_preflight.py -v
```

The first command fails on any source digest, record count, field set, split,
prompt, tokenizer, current-profile, item-selection, or snapshot drift. Its
complete frozen snapshot SHA-256 is
`4642d1386640037edfbfcf17f8a94152847ec27217335c14100152238cc4b70b`.
