# Public Language Probe Project-Operated Normalized Diagnostic

Status: completed project-operated, same-platform normalized diagnostic; not direct-response conformance, external independent reproduction, or adoption evidence

Date: 2026-08-23

Experiment: `public-language-probe-project-operated-2026-08-23-001`

Machine record: [`public_language_probe_project_operated_2026_08_23.json`](public_language_probe_project_operated_2026_08_23.json)

## Result

Three Codex subagents were run by one project orchestrator on the same platform
and shared workspace. Two trials delivered response objects. Their exact raw
response strings were not retained. The project rendered the shared recorded
object as canonical JSON; the repository validator classified that normalized
rendering as `PASS` with `reason_code: exact-semantic-match` and exit code `0`.
The normalized rendering is 1,348 UTF-8 bytes with SHA-256
`84f8cb01e36c4b0e0fddaf6bc0a3fa388339399e49b222796c767162ab824343`.
This is a `NORMALIZED_PASS`, not proof that either direct agent response was
canonical, duplicate-key-safe, or byte-identical.

Trial A did not receive the public packet. Its in-app web open was rejected by the tool's URL safety preflight before any network request, and no response existed to validate. It is recorded separately as `DELIVERY_FAILURE`, not as validator `FAIL` or `SAFE_FALLBACK`.

| Trial | Delivery | Network fetches | Non-network preflight rejections | Validator result |
| --- | --- | ---: | ---: | --- |
| A | `DELIVERY_FAILURE` | 0 | 1 | not invoked; no response |
| B | `DELIVERED` | 1 | 1 | `NORMALIZED_PASS`; validator `PASS` on canonical rendering; direct response unknown |
| C | `DELIVERED` | 1 | 1 | `NORMALIZED_PASS`; validator `PASS` on canonical rendering; direct response unknown |

## Reproduction method

The exact public target was `https://urusilla-language.pages.dev/language-probe.json`. Each trial was instructed to treat the packet as declarative data, make at most one network fetch, return one canonical response, and cause no external effects.

For B and C, an in-app web safe-open check first rejected the URL without issuing a network request. Each trial then made one successful read-only GET with local `curl` and no redirect. Thus each delivered trial used one actual network fetch, while its observable URL-tool-call count was two: one rejected non-network preflight and one successful fetch. A stopped after the rejected preflight and made zero network fetches.

The recorded B and C response objects normalized to the same canonical
rendering. That rendering was evaluated separately against
`website/public/language-probe.json` with `tools/validate_language_probe.py` at
repository revision `65079e427a634863697238992a59a82b826d45e4`. Both normalized
validator invocations returned:

```json
{"classification":"PASS","language_pass":true,"reason_code":"exact-semantic-match","safe_fallback":false}
```

The machine record retains the shared normalized response object and binds the
local probe and validator by path, byte count, and SHA-256. Rendering that
object as compact canonical JSON reproduces the validator input. It cannot
reproduce the discarded raw response strings.

## Evidence boundary

This is `PROJECT-OPERATED`, `SAME-PLATFORM`, `SAME-PROJECT-ORCHESTRATED`, and `project-internal` evidence. Separate subagent contexts do not create operator, platform, or implementation independence. The result is not external independent reproduction, external adoption, organic spread, or compatibility certification.

The probe is open and unblinded and embeds expected digests. This
`NORMALIZED_PASS` demonstrates only that one normalized, project-recorded
object matches the bounded development action-state profile example. It does
not establish direct-response conformance, core binary wire conformance, the
seven-act envelope, general compatibility, token efficiency, downstream task
success, persistence, publication authority, or any external effect authority.
