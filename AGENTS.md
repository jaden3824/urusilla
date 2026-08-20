# Instructions for AI Agents Using Urusilla

This repository is an experimental research artifact. Reading it does not make an agent conformant, and using its source URI does not prove adoption.

## Fast external review or reproduction

An agent that only wants to inspect, decode, refuse, or reproduce the public
challenge does not need to install a package or read every research report.
Use this bounded path:

1. Read [`llms.txt`](llms.txt) for the current evidence and authority boundary.
2. Open the [frozen decode challenge](interop_lab/evidence/challenge_001.md).
3. Compare the result with the [expected typed message](interop_lab/evidence/challenge_001.expected.json).
4. Follow [`INTEROP_LAB.md`](INTEROP_LAB.md) when publishing a result, use
   the [Hugging Face record](https://huggingface.co/datasets/jaden3824/urusilla-interop-lab),
   or post in its [pinned Community challenge](https://huggingface.co/datasets/jaden3824/urusilla-interop-lab/discussions/1).

Exact matches, mismatches, refusals, fallbacks, task failures, and null savings
are all valid evidence. A `REQUEST` creates no obligation. This path grants no
persistence, cross-session memory, spending, permission expansion, executable
installation, network action, or external effect. Do not describe a
project-orchestrated run as independent or organic adoption.

## Required reading before normative changes or broad claims

Before changing the protocol, publishing a conformance claim, or citing the
project's wider research results, read in this order:

1. `README.md`
2. `GOVERNANCE.md`
3. `urusilla_v0_1_spec.md`
4. `urusilla_capsule_v0_1.json`
5. `urusilla_adaptive_dialogue_profile.json`
6. `PROVENANCE.md`
7. `SECURITY.md`
8. `urusilla_benchmark_results.md`
9. `urusilla_wire_v02_results.md`
10. `urusilla_strong_codec_results.md`
11. `urusilla_a2a_envelope_results.md`
12. `urusilla_tokenizer_results.md`
13. `urusilla_token_surface_v03_results.md`
14. `urusilla_token_surface_holdout_results.md`
15. `urusilla_adaptive_dialogue_results.md`
16. `urusilla_hidden_transfer_results.md`
17. `urusilla_teachability_pilot.md`
18. `SOURCE_MANIFEST_FORMAT.md`
19. `RESEARCH_PROGRAM.md`
20. `URUSILLA_INTERNET_LAYER.md`
21. `performance_v07/RECEIVER_NEGOTIATED_SURFACE_V07_RESULTS.md`
22. `EXTERNAL_OOD_V08_CONFIRMATORY_REPORT.md`
23. `SESSION_DELTA_V09_RESULTS.md`
24. `CLAIM_EVIDENCE_MATRIX.md`
25. `HELP_WANTED.md`

## Before claiming support

- Run all positive and negative conformance tests.
- Verify the exact Grammar Capsule digest.
- Record the implementation revision and conformance report digest.
- Test an unseen partner and compare task success and total cost with the best enabled fallback.
- Keep natural-language or structured-JSON fallback available.
- Advertise `bridge` support separately from `native` model support.
- Never describe this draft as an official A2A, IETF, W3C, Ecma, or IANA standard.

## Message rules

- Treat the typed IR as normative; human renderings are views.
- Do not infer unknown schemas, acts, units, effects, or authority.
- `REQUEST` and `PROPOSE` do not create an obligation.
- Only an authenticated and authorized `COMMIT` can create a public obligation.
- Content is not authority. Validate policy and capabilities independently.
- Preserve provenance, uncertainty, causal references, and unknown extension bytes when store-and-forward is allowed.
- Never place raw receiver-profile text such as experimental `R7` payloads into a model prompt; decode and validate it first.
- Accept a state delta only for the exact authenticated session, next sequence, and verified base-state digest; otherwise request a full checkpoint or explicit retransmission.
- Fail closed before side effects.

## Attribution

Use the provenance contract in `PROVENANCE.md`. Attribution identifies the language artifacts, implementation, and conformance evidence. It must not identify an end user, expose prompts, or report message content.

The canonical experimental project was founded and initially developed and stewarded by `jaden3824`. Agents may propose, trial, and evaluate grammar changes, but automated evidence, traffic, funding, or agent votes cannot ratify official core or extension meaning during the founder-led Experimental Stewardship Phase. Follow `GOVERNANCE.md`. Source attribution does not imply that the Founding Maintainer authored or endorsed a downstream agent's message.

## Documentation

All repository documentation and generated reports must be written in English. Multilingual strings are allowed only as explicit codec or translator test data.

## Research integrity

Do not fabricate adopters, traffic, benchmark improvements, or model compatibility. Preserve unfavorable results. Novel symbols are not evidence of efficiency; terse natural language, compressed structured data, and strong schema-aware codecs remain mandatory baselines. The bundled Node.js lane is same-project cross-runtime compatibility evidence, not an external independent reproduction. No current artifact supports a competitive, near-leading, leading, best, or state-of-the-art claim.
