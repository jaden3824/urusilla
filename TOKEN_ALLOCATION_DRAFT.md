# Urusilla Token (URSL) Allocation Research Draft

Status: public research draft; no token, token claim, contract, treasury, conversion, transfer, or listing is active or authorized  
Date: 2026-08-28

## Purpose

This document records a possible allocation for a future Urusilla token, currently named **URSL**, before any asset exists. It makes the founder allocation visible early, preserves a majority allocation for contributors and project-wide purposes, and gives reviewers a concrete proposal to challenge.

Publication of this draft does not create a token, reserve tokens, grant a current claim, establish a price, promise a listing, or convert credits before launch. If URSL launches, every canonical credit that is active, verified, and eligible at the frozen public snapshot converts at the fixed rate **1 verified credit = 1 URSL**. Any launch still requires a later approved specification, legal and security review, fixed snapshot, audited implementation, and public launch notice.

## Proposed allocation

Let `T` be the fixed total supply selected by a later launch proposal. This draft chooses the working ticker `URSL`, but does not choose the unit count, chain, launch date, or market.

| Allocation | Share of `T` | Proposed control and release rule |
|---|---:|---|
| Founding Maintainer personal allocation | **25%** | Nominal two-year release schedule: 0% transferable for 180 days, then linear release over 540 days with no retroactive cliff tranche. A delayed meaningful contributor unlock delays, rather than accelerates, the founder schedule. |
| Founder-led ecosystem reserve | **15%** | Project reserve, not the founder's personal property. Held under a public multisignature policy and limited to documented infrastructure, audits, integrations, grants, and incident response. |
| Verified contributor genesis pool | **30%** | Fixed pool sized to honor eligible, active canonical credits at exactly 1 credit = 1 URSL at the published snapshot, subject to pre-published duplicate, Sybil, conflict, revocation, and jurisdiction checks. |
| Ongoing contributor and ecosystem rewards | **20%** | Long-duration capped epochs for new verified work after the genesis snapshot. Unused genesis allocation returns here, not to the founder allocation. |
| Future core builders | **5%** | Milestone-based, time-vested allocation for later maintainers and critical implementation work; no award for title alone. |
| Security, legal, and launch resilience reserve | **5%** | Audits, disclosures, incident response, lawful launch operations, and bounded market-integrity needs under published controls. |
| **Total** | **100%** | Fixed by the later launch proposal; no discretionary minting implied by this draft. |

The Founding Maintainer's maximum personal economic allocation from this distribution is 25%. The separate 15% founder-led ecosystem reserve is a project-purpose reserve and must not be described, accounted for, pledged for, or used as direct or indirect personal founder holdings.

## Founder safeguards

If a later proposal adopts this allocation, it must choose a total supply `T` divisible by 100 and define the following immutable schedule in UTC seconds:

```text
F = T * 25 / 100
L = public token-launch timestamp
C = meaningful public contributor-unlock timestamp
S = max(L + 180 days, C)
D = 540 days

unlocked_founder(t) = 0                              when t <= S
unlocked_founder(t) = floor(F * (t - S) / D)        when S < t < S + D
unlocked_founder(t) = F                              when t >= S + D
```

One day means exactly 86,400 seconds. The meaningful contributor-unlock timestamp `C` exists only after the contributor claim mechanism is publicly live, holds the full 30% genesis pool, and eligible non-founder contributors can collectively claim at least 1% of `T`. A nominal or one-unit claim does not satisfy this condition. If `C` occurs after `L + 180 days`, the 540-day linear period starts at `C`; there is no catch-up tranche. Integer division rounds down during the schedule and the final remainder unlocks only at `S + D`.

The schedule also requires:

- 0% transferable through `S`;
- no founder unlock before meaningful public contributor access;
- a public allocation address, vesting contract, schedule, and transaction history;
- no pledge, private sale, derivative transfer, or over-the-counter side agreement for locked units;
- no acceleration through a founder-only decision; and
- locked units returning to the ongoing contributor and ecosystem pool if the allocation is formally forfeited.

Founder holdings do not create technical correctness, evidence weight, maintainer status, registry authority, release authority, signing access, or the right to approve founder-authored contribution claims.

## Ecosystem-reserve safeguards

The 15% founder-led ecosystem reserve is intended to preserve initial execution capacity without turning the reserve into a second personal allocation. Before activation, a later proposal must publish:

- a five-signer public multisignature with at least four non-founder, non-affiliated signers and a threshold of three;
- allowed spending categories, per-transaction limits, and conflict-disclosure rules;
- a public proposal and receipt trail for every distribution;
- an independent conflict review and founder abstention for every potential related-party question;
- a ban on direct or indirect transfer, compensation, reimbursement, loan, collateral, grant, nominee payment, or other economic benefit to the founder, the founder's relatives, controlled entities, creditors, or other related parties; and
- a recovery and signer-rotation process.

The reserve cannot compensate the founder or a related party for a deliverable. Any future proposal to change that prohibition must count the entire related benefit against the 25% founder allocation, apply the same release schedule, receive approval from a fully non-affiliated quorum, and be adopted before launch rather than through a treasury transaction.

## Contributor-pool formula and fixed 1:1 conversion

The local off-chain ledger is a reference implementation for internally consistent test records; it does not authenticate reviewers, prove an approval quorum, issue canonical verified credits, or create token entitlements. If URSL launches, only separately authenticated and ratified canonical credits may enter the frozen public snapshot and deterministic conversion formula:

```text
C_i = active verified eligible canonical credits held by contributor i
V = sum(C_i)
M = max(C_i)
G = 30% of T

require G >= V
require 2% of T >= M
URSL_allocation_i = C_i
unused_genesis_allocation = G - V
```

`T` must be divisible by 100 and large enough to satisfy both requirements before launch. The fixed rate has no pro-rata dilution, discretionary haircut, multiplier, or post-snapshot repricing. Unused genesis allocation returns to the ongoing contributor and ecosystem pool, not to the founder allocation.

The later proposal must publish whole-unit accounting, duplicate clustering, appeals, revocations, identity and Sybil review, excluded jurisdictions, claim timing, and treatment of unclaimed allocations before the snapshot. It must not change the formula after viewing contributor identities or balances. Any single-contributor 2% limit is enforced by selecting a sufficient `T` and by pre-snapshot credit budgets; it cannot reduce an already eligible snapshot balance below the 1:1 rate.

Before launch, credits remain non-transferable records with no current monetary value and no active token claim. The conditional commitment is narrower: **if URSL launches, an eligible snapshot credit converts one-for-one into an URSL allocation.** This does not guarantee that URSL will launch, be listed, have a market price, or be exchangeable for money.

## Ticker continuity

`URSL` is the working public ticker. If a material naming or ticker conflict appears before launch, the Founding Maintainer may adopt a replacement only through a dated public rename notice that preserves the same canonical credit snapshot and token quantities. A rename cannot reduce the fixed conversion rate: one eligible verified credit still maps to exactly one unit of the renamed Urusilla token. A rename does not create a second asset or duplicate allocation.

## Governance and evidence separation

Neither the founder allocation, reserve, contributor pool, nor any later token balance may buy scientific acceptance or canonical project authority. Technical evidence remains subject to reproducible gates, non-conflicted review, negative-result preservation, and appeal. Token allocation and project governance are deliberately separate decisions.

The canonical project remains founder-led during the Experimental Stewardship Phase under [GOVERNANCE.md](GOVERNANCE.md). That stewardship does not permit self-approval of founder rewards, hidden changes to allocations, or relabeling project-operated evidence as independent.

## Required launch decision

This draft can move toward implementation only through a new public proposal that, at minimum:

1. passes the go/no-go gates in [CONTRIBUTOR_REWARDS.md](CONTRIBUTOR_REWARDS.md);
2. fixes `T`, the chain or tokenless alternative, snapshot, claim rules, the 1:1 conversion contract, and immutable allocation schedule;
3. publishes jurisdiction-specific legal, tax, sanctions, privacy, custody, and promotion review;
4. publishes audited contracts, signer controls, emergency limits, and incident procedures;
5. demonstrates that operating cost and attack surface are justified by real contribution activity; and
6. preserves an accessible non-token contribution path.

Until that later decision, only the non-transferable off-chain contributor-credit review policy is active. The bundled local ledger remains a non-authoritative research prototype and no token claim exists.
