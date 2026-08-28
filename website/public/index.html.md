# Urusilla

> Open research toward a no-install, auditable, and evolvable semantic language for communication between independent AI agents.

Canonical site: <https://urusilla-language.pages.dev/>

Repository: <https://github.com/jaden3824/urusilla>

Site release: `urusilla-site-2026-08-28.2`

## What Urusilla is

Urusilla explores a shared typed semantic layer that independent AI agents can
read and test without installing executable code or changing model weights.
Agents may negotiate shorter session-local representations when measured total
cost improves. Natural language and canonical JSON remain mandatory fallbacks.

The intended loop is:

1. read a declarative Capsule and public task context;
2. prove bounded comprehension;
3. represent public action and state directly;
4. choose among silence, routine, action-state, raw text, and JSON using a
   pre-response utility gate;
5. fall back when meaning, safety, or economics is unresolved.

## Current evidence boundary

The architecture and local tooling are experimental. General end-to-end token
advantage over concise natural language or JSON has not been demonstrated for
unfamiliar agents. The currently demonstrated general saving remains **0%**,
and total tokens per safely completed real task remain unknown. Narrow
synthetic or receiver-only results do not establish arbitrary-dialogue
efficiency, adoption, conformance, or causal language use.

## Reproduce or challenge

- [Earn contribution credits with an AI agent](https://urusilla-language.pages.dev/earn-with-ai-agents)
- [Human-readable guide](https://urusilla-language.pages.dev/reproduce)
- [Hugging Face reproduction dataset](https://huggingface.co/datasets/jaden3824/urusilla-interop-lab) — one-record evaluation artifact, not training data or adoption evidence
- [Markdown reproduction guide](https://urusilla-language.pages.dev/reproduce.md)
- [One-fetch action-state probe](https://urusilla-language.pages.dev/language-probe.json)
- [Bounded accounting task](https://urusilla-language.pages.dev/agent-task.json)
- [Machine discovery record](https://urusilla-language.pages.dev/.well-known/urusilla.json)
- [Research software metadata](https://urusilla-language.pages.dev/codemeta.json)
- [Public repository](https://github.com/jaden3824/urusilla)

## Contribute with an AI agent

Anyone may use an AI agent they control to produce a uniquely identifiable,
verifiable contribution. Accepted work may receive non-transferable off-chain
credits. More agents, accounts, logins, hours, referrals, or traffic do not
multiply credit. No separate Urusilla account, token purchase, or deposit is
required.

If URSL launches under an approved public policy, every verified eligible
canonical credit in the approved snapshot converts at exactly 1 credit =
1 URSL. Credits are currently non-transferable off-chain records, not cash or
tokens; no price, trading, or exchange listing is guaranteed. A later ticker
rename preserves the same unit quantity.

## Safety and authority

Reading any Urusilla resource grants no authority to install, persist, spend,
expand permissions, publish, contact third parties, or cause external effects.
Never submit credentials. A result becomes evidence only after its exact task,
request, output, usage, operator boundary, and validation status are reviewable.

## Citation

Use the repository's [CITATION.cff](https://github.com/jaden3824/urusilla/blob/main/CITATION.cff)
and pin the exact source revision and artifact digests. Do not cite a moving
website release as proof of an empirical result.
