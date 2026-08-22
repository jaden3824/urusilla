# Urusilla BYOK Participation Design

Status: design only; not implemented, deployed, executed, or externally posted

Date: 2026-08-23

Scope reviewed: the current Urusilla repository and public-site source, read-only

## Executive decision

Urusilla should **not collect, proxy, store, or log participants' raw LLM API
keys**. The safe interpretation of "use my API key" is:

1. a participant downloads or launches a digest-pinned local runner;
2. the runner uses the key only inside the participant-controlled environment
   and sends it only to the participant-selected provider endpoint over TLS;
3. Urusilla receives, at most, a separately reviewed and redacted result bundle;
4. publication is a second, explicit action after the run; and
5. a public receipt says what was structurally verified, never that the provider,
   operator identity, independence, or scientific claim was proven.

The recommended first product is therefore **local-runner-first BYOK**, not an
API-key field on the main website. A browser-only runner may be added later for
providers whose official endpoints explicitly support the required browser
CORS flow, but it should be an isolated, zero-analytics, digest-pinned surface
and should remain lower assurance than the local runner.

The viral loop should be built around reproducible evidence:

```text
frozen study -> local capped run -> local validation -> human review/redaction
             -> optional submission -> evidence-graded receipt
             -> optional share card -> reproduce the exact frozen study
```

It must not be built around custody of secrets, automatic posting, referral
spam, favorable-result leaderboards, or claims that a one-off model call is
adoption.

## Current-state fit

The design deliberately preserves the current repository's boundaries:

- The public website is a read-only discovery and contribution surface. It has
  no result POST endpoint.
- `website/public/.well-known/urusilla.json` explicitly says discovery grants
  no authority to use credentials, spend, publish, persist, create accounts, or
  cause external effects.
- `competitive_eval/external_replay.py` already separates exact provider-neutral
  requests from externally captured responses and has no provider SDK,
  credential reader, network client, or spending authority.
- The AutoGen and CAMEL paths already distinguish protocol authority from a
  separately authorized operator-owned model call.
- `interop_lab/result.schema.json` currently requires
  `spending_authorized: false`. A live BYOK record must not silently reinterpret
  that field. It needs a new execution wrapper that records
  `protocol_authorized_spending: false` and a separate, narrowly bounded
  `operator_authorized_provider_calls: true` attestation.
- The broad unfamiliar-agent post-decode saving remains 0%. BYOK participation
  can collect better external evidence; it cannot change that result merely by
  increasing the number of calls or submissions.

No present artifact should be described as a deployed BYOK runner, collector,
provider integration, verified receipt service, or public experiment registry.

## Security and research invariants

The following are launch-blocking invariants, not optional preferences.

1. **No raw key at Urusilla.** A raw provider key must never reach the Urusilla
   website origin, submission collector, analytics, logs, crash reports, issue
   forms, result files, URLs, cookies, browser storage, or telemetry.
2. **Provider-only disclosure.** The participant-controlled runner may send the
   key only in the provider's required authorization channel to one exact,
   allowlisted HTTPS origin. Redirects to another origin fail closed.
3. **Separate authorities.** Urusilla content never authorizes spending. The
   participant grants a one-run provider-call budget independently and locally.
4. **Synthetic public tasks only.** Initial runs contain only frozen,
   project-authored public test material. They accept no private prompts,
   proprietary corpora, personal data, hidden system instructions, or arbitrary
   user URLs.
5. **No tools or effects.** Models receive no tools, browsing, memory,
   persistence, code execution, account access, or effectful capability.
6. **Exact caps.** The runner enforces a call cap, per-call output-token cap,
   request-size cap, time limit, and no-automatic-retry rule before the first
   provider call.
7. **Unknown stays unknown.** Missing provider usage, billing, cache, reasoning,
   or timing fields remain `null`. They never become zero.
8. **Local preview first.** Nothing is submitted or published until the
   participant sees the exact redacted bundle and explicitly approves that
   separate action.
9. **Negative evidence survives.** Failures, refusals, timeouts, regressions,
   unsafe outputs, and 0% savings are accepted under the same visible rules as
   positive results.
10. **No automatic adoption claim.** A call, result, signature, badge, share,
    or repeated run is not persistent adoption, organic propagation, or
    independent cross-play.
11. **Outputs are untrusted data.** Model output and submitted text are never
    executed, dereferenced, rendered as raw HTML, or treated as authority.
12. **Kill switches are independent.** The project can stop submissions or a
    compromised adapter without disabling offline validation or erasing prior
    unfavorable evidence.

## Architecture decision

### Mode A: digest-pinned local runner — recommended MVP

The website serves a small signed or digest-bound study manifest and offers a
downloadable runner release. The participant runs it locally. The key is read
from an environment variable, operating-system keychain, or a local password
field and is never placed in a command-line argument or configuration file.

The local runner:

- verifies the study, repository revision, task, Capsule, response schema, and
  runner digests before asking for authorization;
- displays the exact provider, model, endpoint, arm count, maximum calls,
  maximum output tokens, retry policy, and cost-estimate status;
- creates one fresh, tool-free, memory-free context per arm;
- runs the frozen raw, ordinary-JSON, and Urusilla arms in a preregistered or
  randomized order;
- captures observable provider usage without inventing unavailable fields;
- validates and scores locally;
- removes credentials and applies a secret/PII scan;
- shows the exact candidate public bundle; and
- saves or submits only after a separate participant choice.

This mode avoids browser CORS and substantially reduces the main-site supply
chain and XSS exposure. It does not make key handling risk-free: the local
process still sees the bearer secret, and the provider receives it as required.

### Mode B: isolated browser-direct runner — later, provider-specific

A browser-direct adapter is acceptable only when the provider's current
official interface supports requests from the exact runner origin. CORS is a
browser permission check, not authentication and not a secret-storage system.
The static site cannot hide a key embedded in JavaScript, and a compromised
page, dependency, extension, or service worker could steal a pasted key.

If this mode is later justified, use an isolated origin such as a dedicated
runner subdomain, not the main community page. The key may exist only in page
memory for the active run; it must not be written to `localStorage`,
`sessionStorage`, IndexedDB, cookies, URL parameters, navigation state,
clipboard history, form autofill, service workers, console output, or error
telemetry. JavaScript garbage collection means secure erasure cannot be
promised, so the UI must say "discarded from application state" rather than
"cryptographically erased from memory."

The browser build must have:

- no analytics, ads, tag managers, chat widgets, remote fonts, or third-party
  scripts;
- no service worker;
- a reproducible build and published artifact digest;
- no runtime code download after integrity verification;
- `Content-Security-Policy` with `default-src 'none'`, a hash-pinned local
  `script-src`, an exact provider-only `connect-src`, `object-src 'none'`,
  `base-uri 'none'`, `form-action 'none'`, and `frame-ancestors 'none'`;
- `Referrer-Policy: no-referrer`;
- restrictive `Permissions-Policy`;
- `Cross-Origin-Opener-Policy: same-origin`;
- `Cross-Origin-Resource-Policy: same-origin` where compatible;
- `X-Content-Type-Options: nosniff` and frame denial;
- `Cache-Control: no-store` on the interactive runner; and
- a prominent warning to use a project-scoped, low-quota, revocable key.

Each provider adapter needs its own security review and network allowlist.
"Custom base URL" and arbitrary proxy fields are prohibited because they turn
the runner into a credential-exfiltration interface. Cross-origin redirects
must be disabled or rejected.

### Mode C: loopback helper with local UI — acceptable fallback

Where a browser UI is desirable but provider CORS is unavailable, a small local
helper may bind only to `127.0.0.1`/`::1`, read the credential locally, and make
the provider call. It must:

- choose a random high port and one-time launch token;
- validate `Host` and exact `Origin` to resist DNS rebinding;
- require an unpredictable CSRF token on every state-changing request;
- never listen on a LAN or public interface;
- log neither headers nor bodies;
- reject requests above a small fixed size;
- expose no generic proxy or URL-fetch endpoint;
- stop after the bounded study or a short idle timeout; and
- use the same provider-origin, call, token, retry, and redirect restrictions
  as the CLI.

The loopback helper is still local software and needs signed releases and
security maintenance. It is not a way for the hosted site to receive a key.

### Mode D: Urusilla server-side key proxy — prohibited

The following design must not be built:

```text
participant browser -> raw API key -> Urusilla server -> LLM provider
```

It creates secret custody, log and backup exposure, insider and breach risk,
unclear provider-account attribution, proxy abuse, billing disputes, and a much
larger compliance burden. Encrypting the key in transit or briefly storing it
does not remove those risks. A generic server proxy with `Access-Control-Allow-
Origin: *` would be especially dangerous.

### Mode E: delegated provider authorization — future only

Provider-native OAuth, PKCE, or scoped ephemeral credentials could eventually
improve the experience, but only where an official provider flow exists and
after a separate threat, token-storage, revocation, and terms review. Urusilla
must not invent an unofficial OAuth wrapper or reuse consumer web-session
cookies. This is outside the MVP.

## Key lifecycle contract

The runner must expose the following lifecycle in plain language:

1. The user obtains a provider-issued credential from an account they are
   authorized to use. Urusilla never creates the account or scrapes a consumer
   web session.
2. The user should create a dedicated, least-privilege project credential with
   a provider-side budget/quota and a short revocation path when available.
3. The runner reads the credential locally. Environment variables or keychain
   access are preferred over paste. A pasted field uses password display,
   disables autocomplete where supported, and is never copied automatically.
4. The runner sends the credential only to the exact provider endpoint in the
   authorization location required by that provider.
5. Request/response debug logging is off. Exceptions are reduced to allowlisted
   codes before display or persistence.
6. After the final attempt, the runner removes the credential reference from
   its application state. It does not claim guaranteed RAM erasure.
7. The result builder rejects any value matching the exact credential, common
   provider-key patterns, authorization headers, cookies, or high-entropy secret
   heuristics. The participant must still review the output because scanning is
   not proof of absence.
8. The runner shows provider revocation and usage-dashboard links as ordinary
   user-operated links; it never revokes or rotates a credential itself.

Provider request and response identifiers may themselves expose account or
operational metadata. They are private by default and follow the separate
receipt policy below.

## Consent and cost authorization

Consent must be granular. One "Run" checkbox is insufficient. Before a live
call, the runner requires distinct acknowledgements for:

1. **Provider transmission:** the exact frozen public inputs will be sent to
   the named provider under that provider's terms and retention policy.
2. **Bounded spending:** the operator authorizes this runner, not the Urusilla
   protocol, to make at most the displayed calls under the displayed limits.
3. **Local recording:** observable prompts, outputs, usage, errors, and timing
   will be recorded locally for this study.
4. **Optional submission:** after preview, the redacted bundle may be sent to
   the Urusilla collector. This is off by default.
5. **Optional publication and license:** after another preview, selected fields
   may become public under an explicit evidence license. This is off by default.
6. **Optional follow-up:** contact information, if any, is collected separately
   and never required for a local run.

The run authorization should be a local, canonical record similar to:

```json
{
  "schema_version": "urusilla-byok-run-authorization/1",
  "study_sha256": "sha256:<64 lowercase hex>",
  "provider": "<exact provider>",
  "model": "<exact model requested>",
  "operator_authorized_provider_calls": true,
  "protocol_authorized_spending": false,
  "maximum_provider_calls": 3,
  "maximum_output_tokens_per_call": 256,
  "automatic_retries": 0,
  "tool_access": false,
  "external_effects": false,
  "price_basis": "exact | estimated | unavailable",
  "estimated_maximum_cost_usd": null,
  "provider_project_budget_confirmed_separately": true,
  "submission_authorized": false,
  "publication_authorized": false
}
```

This is a proposed shape, not a current schema.

### Cost rules

- The main safety controls are exact call count, input/request bounds, output
  token bounds, zero automatic retries, and a provider-side account budget.
- A dollar ceiling may be labeled `exact` only when the adapter has a current,
  provider-authoritative price basis and can conservatively account for all
  relevant input, output, cache, reasoning, batch, and minimum charges before
  the call. Otherwise it is `estimated` or `unavailable`.
- If exact pre-call input tokens cannot be computed, the UI must not present an
  exact cost cap. It may present a conservative character/request-size bound and
  an estimate with the uncertainty disclosed.
- Rate-limit, timeout, transport, and provider errors consume an attempt and may
  consume money. There is no automatic retry. A retry requires a new visible
  authorization and is recorded as a new attempt.
- Cancellation stops future calls; it cannot undo a provider request already
  accepted or a charge already incurred.
- The runner never automatically upgrades to a more expensive model or changes
  providers.

## Frozen study manifest

Every public study should have one immutable, content-addressed manifest. It
binds at least:

- study and schema version;
- project snapshot and runner release digests;
- task-set URI, license, bytes, and SHA-256;
- Capsule, raw baseline, JSON baseline, candidate, and evaluator identities;
- public inputs and response contracts;
- arm order rule, repetition count, stop rule, and retry rule;
- exact provider adapter version;
- allowed provider origins and requested model constraints;
- maximum calls, request sizes, output tokens, and time;
- token/cost ledger categories;
- success, fidelity, safety, fallback, and claim gates;
- redaction and publication defaults; and
- signature status.

The current Capsule is unsigned. A digest identifies its bytes but does not
authenticate a trusted publisher. A future project signature over a study
manifest should be domain-separated and should say only that the maintainer
approved those exact study bytes, not that any result is true.

A run with any changed prompt, threshold, model setting, task, or evaluator gets
a new study digest. The project must not edit a measured study in place after
seeing results.

## Reproducible run protocol

1. Fetch or open the immutable study manifest.
2. Verify every local artifact and runner digest.
3. Create a local run directory outside the source checkout.
4. Optionally obtain a short-lived collector nonce before measurement if the
   participant wants a receipt-backed submission; offline-only runs remain
   valid local evidence.
5. Display and collect the granular authorization above.
6. Generate a fresh local Ed25519 result-signing key for this study or use a
   participant-controlled stable public key by explicit choice.
7. Freeze the provider, model, settings, arm order, and all public inputs.
8. Use a fresh tool-free, memory-free context for every arm and repetition.
9. Execute within exact caps. Do not repair or retry unless the study explicitly
   budgets and records that separate attempt.
10. Capture provider-reported usage and receipts where available. Preserve
    missing fields as `null`.
11. Evaluate with the frozen evaluator without allowing model output to trigger
    tools, URLs, or follow-on prompts outside the protocol.
12. Build a local private bundle and a separate candidate public projection.
13. Run schema, arithmetic, digest, duplication, secret, PII, and license
    checks locally.
14. Show the exact public projection and every redaction to the participant.
15. Save locally, submit, or discard. Submission does not imply publication.
16. If submitted, verify the collector's signed structural receipt locally.
17. If publication is approved, create a stable public record and optional share
    card. A later correction or withdrawal appends a visible status transition.

## Result bundle split

### Public projection

The public projection should contain only fields needed for review and
reproduction:

- schema version, result digest, study digest, project revision, and runner
  digest;
- experiment class and a precise operator/project relationship disclosure;
- provider, exact requested and resolved model when known, model date/version,
  tokenizer/count source, sampling settings, and tool/memory status;
- randomized arm order, repetitions, attempt count, and all stop/fallback events;
- project-authored synthetic model inputs or their immutable public references;
- opted-in observable outputs, or output digests when content is not public;
- task, parse, semantic-fidelity, safety, and completion results;
- non-overlapping usage, billing, latency, repair, fallback, and unknown fields;
- redaction list, public-data/license attestations, and consent version;
- local signing public key and signature over canonical result bytes;
- evidence tier and explicit claim blockers; and
- an optional `parent_public_record_digest` selected by the participant to show
  a transparent reproduction lineage.

The public projection must not contain a key, authorization header, cookie,
provider account or project identifier, exact IP address, private prompt,
private chain-of-thought, hidden system prompt, personal data, raw unreviewed
receipt, or reusable session credential.

### Private local evidence

The participant may retain locally:

- raw provider request and response receipts;
- provider request/response IDs;
- exact timestamps;
- full observable outputs not licensed for publication; and
- local consent and call-preflight records.

Private evidence is not uploaded by default. If a later receipt-verification
path accepts selected private fields, it needs a new consent, a defined purpose,
encryption in transit and at rest, access controls, deletion policy, breach
plan, and independent security/privacy review.

### What signatures prove

A local Ed25519 signature proves that the signed bytes have not changed under
the included public key. It does **not** prove:

- a real-world identity;
- that the signer is independent from Urusilla;
- that a provider produced the response;
- that the provider usage is authentic;
- that the model was the declared model;
- that the study was fair; or
- that Urusilla was adopted.

A collector signature over an acceptance receipt proves only the collector's
statement, such as "schema-valid under validator revision X at time Y." It must
not be phrased as an endorsement of truth or performance.

## Collector design

The collector, if built, should be a separate service and origin from the main
site and from any browser runner. It accepts result bundles, never provider
credentials or generic provider requests.

### Proposed narrow endpoints

```text
GET  /v1/studies/<study-digest>       immutable public study metadata
POST /v1/run-nonces                   optional, short-lived, single-study nonce
POST /v1/submissions                  bounded result JSON only
GET  /v1/receipts/<result-digest>     public structural receipt/status
GET  /v1/records/<result-digest>      public projection after publication consent
```

These endpoints are design proposals only.

### Ingress constraints

- HTTPS only; fixed JSON media types; no multipart or executable uploads.
- A small fixed body limit, depth limit, string limit, array limit, and strict
  duplicate-key rejection.
- Strict schema with `additionalProperties: false` at security boundaries.
- No server-side fetch of participant URLs, webhooks, evidence links, images,
  schemas, or model endpoints.
- No raw HTML rendering. Free text is escaped and size-limited; the preferred
  path uses reason codes and content digests.
- An allowlisted study digest and exact runner/schema revisions are required.
- Malformed, oversized, secret-bearing, or internally inconsistent records are
  quarantined or rejected before public visibility.
- CORS permits the exact approved runner origins only. CLI clients use a
  separate authenticated/non-browser path. CORS is never treated as identity.
- Submission processing executes no uploaded code and imports no arbitrary
  participant module.

### Nonce and idempotency

For an online receipt-backed run, the collector may issue a short-lived nonce
bound to:

- study digest;
- runner digest;
- participant result-signing public key;
- maximum calls and expiry; and
- one random nonce identifier.

The nonce is single-use for publication eligibility. It prevents trivial replay
to the collector but does not prove that a provider call occurred.

Define the idempotency key from a domain-separated digest of the canonical
public result bundle. Resubmitting identical bytes returns the existing receipt
instead of creating a new result. Changed bytes create a distinct result and
must retain their relation to any prior attempt or correction.

## Duplicate, Sybil, and spam controls

No single control can prove unique humans, agents, or provider calls. The
collector therefore uses layered evidence grades and publishes the limitations.

### Low-data controls

- rate-limit by short-lived network abuse signals, nonce public key, study,
  result digest, and event type;
- discard raw network identifiers after the narrowly documented abuse window;
- require a fresh nonce for receipt-backed publication;
- reject reused nonces and impossible attempt sequences;
- cluster exact and near-exact public bundles for review;
- separate internal, CI, project-orchestrated, partner, and external traffic at
  ingestion;
- restrict free text, URLs, and attachments;
- require manual or delayed publication for suspicious bursts; and
- keep unfavorable and null results visible so favorable-result spam has less
  incentive.

### Optional provider-ID deduplication

Provider request/response IDs must not be public by default. A participant who
explicitly opts into receipt-backed deduplication may send the minimum required
identifier to a private endpoint. The service immediately computes a
server-keyed HMAC over provider, model namespace, and identifier, discards the
raw identifier, and stores only the deduplication commitment for the declared
retention period.

This detects reuse of the same supplied identifier within that service. It does
not authenticate the identifier, prevent a fabricated identifier, prove model
identity, or establish operator independence. A participant who declines this
processing may still publish at a lower self-reported tier.

### Evidence grades

Suggested labels are:

| Grade | Minimum statement | Must not imply |
|---|---|---|
| `LOCAL-NOT-SUBMITTED` | The participant has a local bundle. | Any public evidence. |
| `SELF-REPORTED-SIGNED` | A schema-valid bundle carries a participant-key signature. | Provider authenticity or unique identity. |
| `RECEIPT-METADATA-REVIEWED` | Selected provider metadata and dedup checks passed the disclosed review. | A provider signature or independence unless separately established. |
| `EXTERNAL-CONTROLLED` | An external operator disclosed control of the run and supplied reproducible artifacts. | Independent cross-play or organic spread. |
| `INDEPENDENT-CROSS-PLAY` | The existing Interop Lab independence gates are separately satisfied. | Population adoption or organic propagation. |

The collector should reuse the project's existing experiment-class vocabulary
where possible. An evidence grade supplements, and never silently upgrades, the
experiment class.

### Moderation and correction states

```text
received -> structurally-valid -> evidence-graded -> publication-approved
         -> published -> corrected | withdrawn | invalidated
```

Public records are append-only in meaning: corrections and invalidations point
to prior digests instead of silently replacing them. The UI must warn that
public Git mirrors and caches may make complete deletion impossible. A
withdrawal can remove ordinary presentation and add a tombstone, but it cannot
promise erasure from third-party archives.

## Retention proposal

Before implementation, a privacy review should select exact periods. A
conservative initial proposal is:

- no raw API keys, authorization headers, or cookies are ever retained;
- rejected request bodies: immediate deletion after generating a non-sensitive
  reason code, unless a participant separately opts into a short debugging
  capture;
- transient IP/network abuse logs: at most 24 hours under restricted access;
- private provider-ID input: discard immediately after keyed commitment;
- private deduplication commitments and unpublished result bodies: at most 30
  days unless the participant explicitly extends review;
- public evidence projection and structural receipt: retained as a versioned
  research record under the publication consent and correction policy; and
- optional contact details: separate store, separate consent, easy deletion,
  and no linkage in public exports.

The exact deployed policy must be public, tested end to end, and reflected in
the consent text. This proposal is not a current retention commitment.

## Safe viral loop

The growth mechanism should reward falsifiable work rather than favorable
answers.

### Participant journey

1. **See one precise claim:** "Run the same three-arm public task on your model;
   failures and regressions are welcome."
2. **Preview the real commitment:** provider/model, three-call maximum, output
   limits, cost-estimate status, public synthetic data, and no-tools boundary.
3. **Run locally:** key remains outside Urusilla systems.
4. **Receive an immediate local result:** task success, fidelity, usage, total
   cost status, and claim blockers.
5. **Optionally submit:** participant reviews the exact projection.
6. **Receive a neutral evidence card:** result digest, model, outcome, evidence
   grade, study digest, and a "reproduce this exact study" link.
7. **Optionally share:** Web Share, copy, GitHub, or community buttons activate
   only on a user gesture and contain no hidden referral or credential data.
8. **Invite a challenge, not an endorsement:** the next participant reproduces
   the frozen study and may link `parent_public_record_digest` by choice.

### Share-card language

Good:

> I ran Urusilla study `<digest>` on `<model>`. This externally controlled,
> self-reported run produced `<positive/null/negative>` result. Reproduce or
> falsify the same frozen study: `<URL>`.

Bad:

> `<model>` adopted Urusilla, proving a global token reduction.

The public card must be equally attractive for a win, null, refusal, or loss.
It should never request a star, auto-mention accounts, post repeatedly, create
an account, message third parties, or spend beyond the authorized run.

### Public result views

Useful views include:

- valid external study records by exact evidence grade;
- model/provider families with complete versus incomplete accounting;
- positive, null, negative, refusal, and invalid results side by side;
- exact study-digest reproduction lineages;
- token and task-success confidence intervals only where the frozen design
  supports them;
- unresolved counterexamples and requests for independent reruns; and
- internal/CI/project-orchestrated activity separated from external activity.

Do not publish an unqualified "agents using Urusilla" number. Page views,
downloads, model calls, signatures, and submissions are different phenomena.

### Growth metrics that preserve scientific integrity

Primary:

- number of structurally valid external records;
- independently accountable operators, explicitly disclosed;
- exact model families and provider adapters reproduced;
- share-to-valid-reproduction conversion by study digest;
- proportion with complete token and cost ledgers;
- time to first external counterexample;
- proportion of negative/null results retained; and
- number of results independently reproduced or contradicted.

Secondary and separately labeled:

- runner downloads;
- page-to-preflight conversion;
- share-card activations; and
- GitHub/community engagement.

None is an adoption metric by itself. Referral rewards, crypto tokens,
favorable-result bonuses, automated stars, and ranking people by claimed token
savings are outside this design because they increase spam and selective
reporting pressure.

## Privacy-preserving observability

Local runs emit no telemetry by default. If aggregate product telemetry is
later enabled, it requires a separate opt-in and must use the repository's
content-free event philosophy. It may record coarse events such as:

```text
manifest_verified | preflight_abandoned | run_completed | local_validation_failed
submission_previewed | submission_accepted | share_card_opened
```

It must not contain prompts, outputs, keys, provider identifiers, account IDs,
exact model request IDs, exact timestamps, exact private URIs, reusable session
IDs, or stable participant fingerprints. Product telemetry remains separate
from research evidence and GitHub/community activity.

## Threats and required responses

| Threat | Required response |
|---|---|
| Compromised website JavaScript steals a pasted key | Prefer local runner; isolate any browser runner; zero third-party code; CSP; reproducible digest; scoped revocable key warning. |
| Malicious provider/base URL exfiltrates credentials | Exact hardcoded HTTPS origin allowlist; no custom proxy; reject cross-origin redirects. |
| Key appears in logs or errors | Disable body/header logging; allowlisted error codes; canary-secret and log-scrape tests. |
| Model output prompt-injects the runner | Treat output as inert data; no tools, URL fetch, follow-up action, or HTML rendering. |
| Study silently changes after results | Content-address every artifact; new digest for every material change; immutable prior record. |
| Participant is charged repeatedly | Exact call cap; zero automatic retries; each retry needs new authorization; provider-side budget recommendation. |
| Browser CORS fails | Fail closed and offer the local runner; never route through a generic key proxy. |
| Same response is submitted many times | Canonical idempotency digest, nonce replay rejection, optional private provider-ID HMAC, similarity review, rate limits. |
| Sybil operators create apparent adoption | Evidence tiers, operator relationship disclosure, separate external/CI/internal counts, independent-cross-play gates. |
| Result contains a secret or personal data | Local exact-key and heuristic scan, schema limits, participant preview, server quarantine; scanning is not guaranteed detection. |
| Favorable results are selectively promoted | Equal public treatment of losses/nulls, preregistered stop rules, complete failure retention, no savings-ranked rewards. |
| Collector compromise | No key custody, minimal private data, encryption, short retention, signed append-only receipts, kill switch, incident disclosure. |
| Phishing copy of the runner | Canonical immutable download URI, signed/digest-pinned releases, visible origin warning, provider-scoped disposable keys. |

## Delivery phases

### Phase 0 — documentation and threat model

- freeze the invariants in this document;
- choose one small public synthetic matched study;
- define the consent, claim, data, and cost boundaries;
- review provider terms without implementing calls; and
- publish no claim that BYOK exists.

Exit gate: maintainer approval of the threat model and exact non-goals.

### Phase 1 — local runner with fake-provider tests

- implement manifest verification, preflight, local authorization, exact caps,
  result splitting, validation, redaction, and signing;
- use only an injected fake provider and synthetic canary secrets;
- prove zero network destinations except the fake endpoint;
- fault-test timeouts, redirects, 429/5xx, malformed usage, conflicting usage,
  cancellation, and restart;
- prove no automatic retry and no file/log secret leakage; and
- retain all negative fixtures.

Exit gate: independent security review of credential handling and call caps.

### Phase 2 — bounded local live pilot, no collector

- support one provider adapter in the local runner;
- require dedicated low-quota participant keys;
- cap the pilot to one frozen three-arm study;
- save results locally only;
- manually review any voluntarily supplied redacted bundle; and
- label every run `EXTERNAL-CONTROLLED` or the accurate lower tier.

Exit gate: zero credential incidents, every call reconciled to the configured
cap, explicit treatment of missing usage, and tested abort/revocation guidance.

### Phase 3 — submission collector

- implement nonce, idempotency, strict schema, size/depth limits, secret scan,
  quarantine, evidence grading, corrections, deletion, and signed receipts;
- conduct privacy, abuse, replay, Sybil, XSS, and denial-of-service reviews;
- publish methodology and retention;
- test a kill switch; and
- keep public aggregation honest when traffic or positive results are zero.

Exit gate: independent review and an end-to-end deletion/correction rehearsal.

### Phase 4 — isolated browser-direct adapter

- verify current official CORS and browser-use support for each provider;
- deploy a separate no-cookie/no-analytics runner origin;
- reproduce and publish the build digest;
- penetration-test XSS, dependency, CSP, redirect, extension-risk messaging, and
  memory/storage behavior; and
- retain the local runner as the recommended path and fallback.

Exit gate: packet capture and canary tests show that no secret reaches any
Urusilla or third-party origin.

### Phase 5 — evidence network

- enable opt-in, digest-linked reproduction lineages;
- show evidence-grade and experiment-class labels on every record;
- publish complete positive/null/negative distributions;
- invite independent reruns of specific counterexamples; and
- change broad claims only through preregistered, adequately powered evidence,
  not through submission volume.

## Launch tests

No live BYOK surface should launch until all applicable tests pass:

- synthetic exact-key canaries never occur outside authorized provider-bound
  requests;
- request captures show no key in URL, body sent to Urusilla, referrer, log,
  cookie, storage, crash report, result, or share card;
- unknown/cross-origin redirects fail before credentials are resent;
- call and output-token caps hold under concurrency, timeout, 429, 5xx, malformed
  streaming, cancellation, and process restart;
- no automatic retry occurs;
- result arithmetic fails closed on missing or conflicting usage;
- a favorable, null, negative, refusal, and unsafe result all render and submit;
- duplicate JSON members, deep nesting, oversized content, NaN/infinity, HTML,
  script payloads, and URL-fetch attempts are rejected safely;
- nonce replay and idempotent resubmission behave as documented;
- internal/CI/project/external labels cannot be omitted at ingestion;
- publication remains off until a separate explicit action;
- correction, withdrawal, and retention deletion work end to end;
- collector and provider-adapter kill switches work without breaking offline
  validation; and
- public copy never equates a run, result, or receipt with adoption.

## MVP product copy

Recommended:

> Run one frozen three-arm Urusilla study with your own model. The API key stays
> in your local runner and is sent only to your selected provider. Maximum three
> calls, no tools, no automatic retries. Review the full result before choosing
> whether to submit or publish it. Positive, null, and negative results are all
> useful.

Avoid:

> Give us your API key and help Urusilla go viral.

The first copy describes the actual trust boundary and scientific value. The
second invites secret custody, cost ambiguity, and biased participation.

## Recommended next implementation decision

Build **Phase 1 only** first: a downloadable, digest-pinned local runner using a
fake provider, a frozen three-arm synthetic task, exact call caps, local result
validation, and a share-card preview that does not submit anything. Reuse the
existing offline-first request/response separation and Interop Lab evidence
labels. Do not add a key field, result POST endpoint, public leaderboard, or
automatic share button to the main site in that phase.

After the fake-provider suite and independent credential-handling review pass,
run a small local live pilot. A custom domain may improve discoverability, but
it neither makes key collection safe nor creates external participation on its
own. Credible, easy-to-reproduce, honestly labeled evidence is the viral asset.

## Explicit non-claims

This document does not establish that:

- any API key was collected or used;
- any provider call or BYOK trial occurred;
- any provider supports the proposed browser flow;
- any collector, signer, receipt, nonce, deduplication service, or share card
  exists;
- any external operator consented;
- any result was independently reproduced;
- Urusilla has external adoption or organic propagation; or
- the current general token-saving result improved beyond 0%.
