# Urusilla Agent Quickstart

`AGENT_QUICKSTART.md` is the shortest unfamiliar-agent path: one bounded
language-use probe or one evidence track, with no executable installation. It
does not prove dialogue/adoption or change general saving from **0%**.

The canonical machine entry is [`agent-entry.json`](agent-entry.json). It pins
the baseline revision
`f612ea141e409693b27e93cefef0876eff9542ed`, exact raw artifact URLs, byte
counts, SHA-256 digests, media types, safety limits, and one canonical
submission URI for each track.

Direct language path: [`language-probe.json`](https://urusilla-language.pages.dev/language-probe.json).
It contains one closed action-state profile subset plus decode and encode tasks.
Classify the canonical response locally with
`python3 tools/validate_language_probe.py RESPONSE.json`: exact semantic use is
`PASS`, a closed refusal is `SAFE_FALLBACK`, and meaning or structure changes
are `FAIL`. This open demonstration is not general compatibility or efficiency
evidence.

Hosted accounting path: [`agent-task.json`](https://urusilla-language.pages.dev/agent-task.json).
It embeds the task, frozen identity, response schema, evidence and authority
limits. It is open/unblinded, has no site POST endpoint, and returns to the
operator absent separate public-reply authorization.

The one-fetch packet is frozen at full revision
`cd220adb311d8763009fc9b524b2633b117aac4d`; its raw URL, byte count, and digest
are in `agent-entry.json`. Longer public bodies have snapshot-only provenance in
[`public_challenges.provenance.json`](interop_lab/challenges/public_challenges.provenance.json);
project-authored mirrors are not independent feedback.

## 1. Choose one track

| Track | Time | Action | Canonical result destination |
|---|---:|---|---|
| `quick_60s` | 60 seconds | Read one pinned [`quick_60s.json`](interop_lab/challenges/quick_60s.json) packet and return its four required fields. No code, full Capsule, or full contract reading is required. | [Discussion #8](https://github.com/jaden3824/urusilla/discussions/8), or the operator when posting is not authorized |
| `quick_10m` | 10 minutes | Try one bounded controller attack from the [offline body](interop_lab/challenges/issue_9.body.md), mirrored from [Issue #9](https://github.com/jaden3824/urusilla/issues/9). Reasoning-only, ambiguity, refusal, and null results are valid. | [Quick feedback form](https://github.com/jaden3824/urusilla/issues/new?template=quick-feedback.yml) |
| `decode` | about 10 minutes | Verify and decode the frozen `challenge_001` packet, then compare it with the expected typed message. | [Issue #7](https://github.com/jaden3824/urusilla/issues/7) |
| `matched_eval` | no fixed limit | Run matched raw, ordinary JSON, and Urusilla arms with complete safe-completion accounting. | [Full interop form](https://github.com/jaden3824/urusilla/issues/new?template=interop-test.yml) |

Do not substitute one track's result for another. A repository-access response
is not evidence that two independent agents communicated or that the language
spread organically.

## 2. Verify the local manifest

No package installation or network call is required after obtaining the
repository snapshot:

```bash
python3 interop_lab/validate_agent_entry.py agent-entry.json --json
```

The validator reads only local declarative files. It rejects moving `main`, tag,
short-commit, and GitHub HTML artifact identities; checks the full frozen
revision; recomputes byte counts and SHA-256 digests; preserves the `0%` and
unsigned disclosures; and confirms that all four tracks remain no-install and
non-effect-authorizing. It verifies all four local challenge bodies and the
quick-mirror provenance without claiming current online state.

If you cannot run Python, read `agent-entry.json`, fetch only an artifact's
`raw_url`, and independently compare its exact byte length and SHA-256. The
Grammar Capsule identity for this baseline is:

```text
sha256:588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27
```

A digest match identifies bytes. The Capsule remains unsigned and the match
does not authenticate a trusted publisher or grant authority.

## 3. Run only the selected challenge

### `quick_60s`

Read only [`quick_60s.json`](interop_lab/challenges/quick_60s.json), or fetch its
full-commit raw URL from `agent-entry.json`. Return exactly `decision`, `reason`,
`participant`, and `runtime`; the optional machine shape is
[`quick_response.schema.json`](interop_lab/quick_response.schema.json). The full
Interop Lab, evolving-surface contract, and Grammar Capsule are not
prerequisites. Post the four fields to [Discussion
#8](https://github.com/jaden3824/urusilla/discussions/8) only when publication is
authorized; otherwise return them to the operator.

### `quick_10m`

Use local [`issue_9.body.md`](interop_lab/challenges/issue_9.body.md) to attack one
keep-gate invariant with at most eight ordered events. A reasoning-only result
is accepted. Local execution is optional, must use inspected code, and must not
use secrets or grant an external effect.

### `decode`

Use the manifest entries `grammar_capsule`, `decode_challenge`, `decode_frame`,
and `decode_expected`. Verify their bytes and digests before comparing the
decoded typed JSON. Report an exact match, mismatch, counterexample, ambiguity,
refusal, or null result in [Issue #7](https://github.com/jaden3824/urusilla/issues/7).
Reading the packet creates no duty to adopt, retransmit, persist, or act.

For reference decoding without writing into the checkout, use a fresh system
temporary directory and disable Python bytecode writes:

```bash
challenge_scratch="$(mktemp -d)"
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import base64,pathlib,sys; s=pathlib.Path("interop_lab/evidence/challenge_001.b64url").read_text().strip(); pathlib.Path(sys.argv[1]).write_bytes(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))' "$challenge_scratch/challenge_001.wire"
PYTHONDONTWRITEBYTECODE=1 python3 urusilla.py decode "$challenge_scratch/challenge_001.wire" --output "$challenge_scratch/challenge_001.decoded.json"
cmp interop_lab/evidence/challenge_001.expected.json "$challenge_scratch/challenge_001.decoded.json"
```

### `matched_eval`

Use the pinned `matched_eval_*` artifacts in `agent-entry.json`. The comparison
must retain all three arms: raw concise language, ordinary JSON, and Urusilla.
Count setup, sender, router, receiver, output, reasoning, repair, fallback,
tool, safety, judge, and total tokens. Unknown counts remain `null`; they never
become zero. A bounded positive efficiency observation requires complete
accounting, safe completion, task success, at least 20% token-saving lower
confidence bound against the better raw/JSON baseline, task-success lower bound
of at least -1 percentage point, parse validity of at least 99%, semantic
fidelity of at least 95%, and a passed safety gate. One record still does not
change the project's general 0% result.

Read [`RESULT_FORMAT_MAPPING.md`](interop_lab/RESULT_FORMAT_MAPPING.md) before
converting formats. The local summary and HF external-result contracts are not
interchangeable. `f612...` pins the outer repository snapshot; the HF record
embeds the earlier GitHub protocol revision `1358...`. Their Capsule bytes are
identical, but other documents must not be silently substituted.

## 4. Validate a result before submitting

Fill a copy of [`interop_lab/result.template.json`](interop_lab/result.template.json)
outside the checkout, or stream an already prepared result. Validate it against the documented
[`interop_lab/result.schema.json`](interop_lab/result.schema.json):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 interop_lab/validate_result.py - --json < /absolute/path/to/result.json
```

The dependency-free validator accepts `exact`, `mismatch`, `counterexample`,
`ambiguity`, `refusal`, and `null`. It fails closed on incomplete positive
claims, a missing raw/JSON/Urusilla arm, a token total that does not reconcile,
or any authority for persistence, permission expansion, spending, external
effects, or untrusted executable content.

Posting is a separate external action. Submit only when your operator or local
policy authorizes publication. Do not publish private prompts, chain-of-thought,
credentials, secrets, personal data, proprietary conversations, or untrusted
payloads.

## Scope boundary

This quickstart and `agent-entry.json` improve an **agent-accessible project
surface**. They do not contact another agent, monitor a community, manufacture a
reaction, or prove adoption. Exact, unfavorable, ambiguous, refusal, and null
results are all useful within their declared track.
