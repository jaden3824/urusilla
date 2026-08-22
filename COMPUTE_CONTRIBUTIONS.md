# Urusilla Compute Contributions

Status: open for locally executed run candidates; API-key custody and monetary sponsorship are not active

Date: 2026-08-23

## Decision

Urusilla welcomes donated evaluation runs. It does **not** ask contributors to
send provider API keys, access tokens, gift codes, billing identifiers, or
account credentials. Contributors execute a frozen evaluation in an environment
they control and submit only the public result packet and its evidence.

This is a "donate a run" model, not a "donate a key" model.

## Recognition

A run that passes the published identity, completeness, provenance, privacy,
and claim-boundary checks may be listed as a **Compute Contribution**. With the
submitter's explicit consent, the public record may name the accountable
individual, team, or organization and link its immutable result.

Compute Contribution credit acknowledges contributed evaluation capacity and
evidence. It does not by itself establish:

- independent reproduction;
- adoption or endorsement;
- a favorable result;
- employment, reimbursement, or a right to future payment;
- scientific authorship; or
- authority to approve a claim.

Scientific authorship and research credit follow the project's normal evidence
and contribution standards. A contributor who materially designs the study,
interprets results, writes or revises the work, and accepts accountability may
qualify separately; donated compute alone is not authorship.

## Safe submission flow

1. Select a frozen Urusilla revision and evaluation contract.
2. Review the expected provider calls, maximum cost, retry policy, and stopping
   rule before authorizing the run.
3. Execute locally. The credential stays in the contributor's own environment.
4. Remove secrets and private content while preserving all unfavorable, null,
   refusal, repair, retry, and fallback outcomes.
5. Submit the immutable result packet, digests, runtime identity, complete usage
   ledger, independence disclosure, and recognition preference through the
   [compute-run form](https://github.com/jaden3824/urusilla/issues/new?template=compute-run.yml).
6. A maintainer checks structure and provenance. Evidence classes that require
   independence still require independent review or reproduction.

## Credential boundary

The public site and GitHub forms must never request, transmit, log, or store a
provider credential. A future browser runner may use a credential only in local
memory if its provider supports a safe direct-browser flow; it must make the
network destination visible, disable persistence by default, and offer an
equivalent command-line route. Until such a runner is independently reviewed,
the supported path is a contributor-operated local environment.

Urusilla automation does not execute submitted code or dereference arbitrary
result URLs. Public submissions are untrusted input.

## Financial sponsorship

Direct money, provider-credit, voucher, and project-account sponsorship are not
active in this phase. If enabled later, they require a separate budget,
ownership, tax, privacy, provider-policy, conflict-disclosure, and spending
process. Sponsorship will remain distinct from evidence acceptance, contributor
credit, and authorship.

## Current registry

No compute contribution has yet completed review under this policy. An empty
registry is not evidence of participation, adoption, or external reproduction.
