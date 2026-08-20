# Urusilla Propagation Interop Lab

This directory is a neutral measurement harness for one question:

> Can an agent receive the declarative Urusilla Capsule, pass a comprehension
> gate, use it in an actual bounded exchange, retransmit it, and obtain a
> downstream acknowledgement without hidden repair, fallback, or shared-context
> contamination?

It is not a chat service, promotion system, adopter registry, standards claim,
or proof that Urusilla saves tokens in general dialogue. The currently recorded
broad post-decode API-input saving remains **0%**. A valid submitted chain does
not change that project-wide result.

## Safety boundary

`interop_lab.py` uses only the Python standard library. It reads JSON as
declarative data and does not:

- install a package, plugin, model, or executable;
- import or execute code named by a submission;
- open a network connection or contact an agent/model;
- follow a URI or download a Capsule;
- grant spending authority or perform an external side effect; or
- infer that a self-reported participant is independent.

The parser rejects duplicate JSON members, non-finite numbers, oversized files,
excessive nesting, unknown fields, unsafe publication attestations, and any
record claiming that untrusted code ran or an external effect was authorized.

Do not publish secrets, credentials, personal data, private prompts, or chain of
thought. `public_content` is optional and `null` by default; publish a SHA-256
content reference instead. The validator checks the submitter's safety
attestation but cannot discover a secret hidden inside arbitrary text.
When `public_content` is present, its UTF-8 SHA-256 must match
`content_sha256`. All digest fields use `sha256:` followed by 64 lowercase
hexadecimal characters.

## Run without installation

Python 3.11 or later is recommended. From the repository root, generate an
editable two-hop example:

```text
PYTHONDONTWRITEBYTECODE=1 python3 interop_lab/interop_lab.py init my-chain.json
```

The command refuses to overwrite an existing path. Validate the record:

```text
PYTHONDONTWRITEBYTECODE=1 python3 interop_lab/interop_lab.py validate my-chain.json
PYTHONDONTWRITEBYTECODE=1 python3 interop_lab/interop_lab.py validate my-chain.json --json
```

Exit status is `0` for a structurally valid record and `2` for invalid input.
A valid record may contain a failed gate, rejected adoption, task failure,
fallback, repair, token regression, 0% saving, or an unmeasured result. Negative
and null results are first-class evidence, not validation failures.

Run the isolated test suite:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s interop_lab/tests -v
```

## What one hop records

Every hop binds the following fields:

1. `parent_hop`, `parent_capsule_sha256`, and the received
   `capsule_sha256`;
2. the exact received-context digest, size, measured token count when known,
   and disclosure of examples, prior transcripts, evaluator instructions, or
   executable-looking material;
3. positive, negative, and exact-reconstruction comprehension results;
4. adoption decision, turn/session scope, declarative-read mechanism,
   authorization basis, utility threshold evidence, and revocation state;
5. actual message use, exactness, task attempt/result, and result digest;
6. retransmission intent, attempt, downstream result, and acknowledgement
   content digest;
7. transcript content digests plus optional public content;
8. fallback and repair counts reconciled to transcript flags;
9. same-operator/model/prompt/state contamination and researcher
   intervention disclosures; and
10. non-overlapping baseline/candidate token ledgers, with total-task saving
    and **post-decode API-input saving recorded separately**.

A child hop is accepted only if its sender was the parent hop's receiver and
the parent recorded a matching acknowledged retransmission to the child
receiver with the exact same Capsule digest.

## Autonomous session policy

Interactive human approval is not required at every hop. An agent may opt in or
retransmit autonomously when `authorization_basis` is `standing-policy` and the
record binds that policy with `authorization_evidence_sha256`. The same fields
also allow an actual `interactive-approval` to be disclosed. `none` is valid
only when the agent declines, uses a fallback, does not attempt adoption, or
does not intend to retransmit.

An authorized action is accepted only when all of these conditions hold:

- participation is read-only and can be revoked;
- scope is one turn or one session, never persistent state;
- state persistence, spending, and external effects are not authorized;
- expected mutual utility was evaluated against a recorded minimum threshold;
- the observed utility meets or exceeds that threshold and its evidence has a
  SHA-256 reference; and
- a revocation path is available and its invocation/result is recorded.

Revocation stops later participation or advertisement. It cannot erase a
Capsule digest or public message that was already transmitted, so experiments
must remain non-secret and non-effect-authorizing from the start. Model-provider
costs may be paid separately under an operator's experiment budget, but the
Urusilla negotiation itself can never create or expand spending authority.

## What structural validation does not prove

A green report proves only that the JSON is internally consistent under this
format. It does not prove the statements are true, the runtime identities are
unique, the operators are independent, the Capsule signature is authentic,
the public transcript is complete, or the task comparison is fair. Provider
receipts, immutable transcript artifacts, premeasurement sealing, independent
operators, and external review are still needed for stronger evidence.

The report deliberately says `structural_validation_only: true` and keeps
`project_wide_claim_changed: false`. A single chain cannot claim SOTA,
project-wide efficiency, or external adoption.

## Token accounting

Each measured baseline and candidate side has the same non-overlapping
categories used by the project's competitive harness, plus `unclassified`:

```text
task_input, system_role, agent_input_history, agent_output_visible,
final_answer, format_induction, encode_decode_model, negotiation_profile,
repair_retry, tool_request, tool_result, safety_filter,
hidden_reasoning_billed, unclassified
```

`task_total_tokens` must equal the category sum. `judge_tokens` is kept outside
that deployment-facing total, and `study_total_tokens` must equal task plus
judge tokens. The validator recomputes all percentages. A claimed saving with
incorrect arithmetic is rejected.

Post-decode API input is a separate observation because compressing a network
message does not reduce model API input when the receiver expands it before the
model reads it. The generated sample intentionally records 0% post-decode
saving and a small total-token regression while both synthetic tasks succeed.

## Suggested experiment procedure

1. Freeze the task, baseline, Capsule bytes, context package, and success rule
   before measurement.
2. Record the origin and receiver runtimes and operator relationship.
3. Give the receiver only the disclosed context. Do not install or execute a
   submitted payload.
4. Run positive, negative, and exact-reconstruction gates.
5. If the gate and expected-mutual-utility threshold pass under a pinned
   standing policy or recorded interactive approval, allow a bounded
   session-scoped opt-in. Otherwise use structured JSON or concise natural
   language.
6. Exchange task messages and record only public outputs or content digests.
7. Count setup, repairs, retries, fallbacks, and all model-visible tokens.
8. If the receiver chooses to retransmit, record both intent and the downstream
   acknowledgement. Create the next hop only after that acknowledgement exists.
9. Disclose shared operators, prompts, model instances, state, expected outputs,
   researcher intervention, and project-authored tasks.
10. Validate the JSON and publish the immutable record with supporting artifact
    digests. Preserve failures unchanged.

The harness performs step 10 only. Agent orchestration and provider calls stay
outside the validator so an untrusted record can never become executable input.
