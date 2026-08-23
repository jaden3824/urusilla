# Reproduce one Urusilla result

> One bounded public artifact, one fresh receiver, no credentials, and an exact record of what happened.

Canonical page: <https://urusilla-language.pages.dev/reproduce>

Site release: `urusilla-site-2026-08-23.6`

## Evidence boundary

General unfamiliar-agent token saving remains **0%**. One passing response is
not adoption, conformance, authorization, causal language use, or an efficiency
result.

## Choose exactly one path

### Language-use probe

Fetch <https://urusilla-language.pages.dev/language-probe.json> and give the
complete artifact to one fresh receiver in a read-only session. Preserve the
exact response. The probe distinguishes exact semantic use, safe fallback,
refusal, malformed output, and meaning loss.

### Accounting check

Fetch <https://urusilla-language.pages.dev/agent-task.json> and return only the
four requested fields. Unknown usage must remain unknown; the task authorizes no
external action.

## Minimum result record

Record all of the following without repairing or interpreting the response:

1. receiver model and exact version, when visible;
2. runtime or host;
3. prior Urusilla exposure: `yes`, `no`, or `unknown`;
4. exact raw response;
5. `PASS`, `SAFE_FALLBACK`, `FAIL`, or `not-run`;
6. first divergence or fallback reason.

## Validate locally

For the language probe, save the response outside the repository checkout and
run the dependency-free validator from a pinned repository snapshot:

```text
python3 tools/validate_language_probe.py RESPONSE.json
```

If the validator was not run, report `not-run`. Never guess a pass.

## Submit only if you choose

- [Compute-run candidate](https://github.com/jaden3824/urusilla/issues/new?template=compute-run.yml)
- [Counterexample](https://github.com/jaden3824/urusilla/issues/new?template=counterexample.yml)
- [Design discussion](https://github.com/jaden3824/urusilla/discussions/8)

Do not submit an API key, access token, billing identifier, private prompt, or
other secret. Reading this guide grants no authority to publish, persist,
install, spend, expand permissions, contact others, or retransmit.
