# Urusilla Verifiable Contributor Rewards

Status: active off-chain credit review policy and non-authoritative local ledger prototype; no canonical credit award, blockchain launch, token, treasury, contract, transfer, conversion, listing, price, or payment is active
Date: 2026-08-28

## Decision

Anyone may submit a uniquely identifiable, verifiable contribution using their own AI agent, subject to the same provenance, disclosure, review, and accountability rules as any other submission. Accepted work may receive **non-transferable off-chain contributor credits**. Credits recognize reviewed contribution evidence; they are not awarded for numbers of agents or accounts, logins, time spent, referrals, traffic, social activity, or popularity.

The policy is retrospective and evidence-based. Work earns credits after its effects are measured, disclosed, and reproduced to the level required by its contribution class; promises, popularity, projected adoption, and repeated submissions are not impact. Closely related or duplicated work is clustered so that multiplying agents or identities cannot multiply credit for one underlying contribution.

Credits currently have no monetary value. Before launch they cannot be sold, transferred, redeemed, or exchanged; they are not a token, payment, receivable, treasury interest, ownership right, or promise of a future listing, price, liquidity, or profit. Any ordinary bounty or grant must be separately funded and approved through legally reviewed payment arrangements.

The bundled local ledger prototype can demonstrate deterministic, append-only test records, but it does not authenticate a reviewer, establish a quorum, verify independence or conflicts, or issue a canonical project credit. Its hashes and Merkle root prove only internal content consistency. A real credit award requires a separately published adjudication roster, non-conflicted quorum, signed checkpoint, reason code, and appeal window; no canonical awards have been issued as of this policy date.

No blockchain or project token is active or authorized. The project has nevertheless fixed the contributor conversion rule: **if the Urusilla token, currently named URSL, launches, every canonical credit that is active, verified, and eligible at the frozen public snapshot converts at 1 verified credit = 1 URSL.** Launch remains subject to explicit legal, security, economic, and governance review before any contract, asset, claim, or conversion exists. A chain is not the language transport, benchmark judge, identity oracle, scientific authority, or substitute for those reviews.

## Conditional 1:1 URSL conversion

The 1:1 rate is a project commitment conditional on launch, not a statement that a token exists today. It has no pro-rata dilution, discretionary haircut, multiplier, or post-snapshot repricing. The launch specification must choose a total supply and contributor genesis pool large enough to honor all eligible snapshot credits one-for-one under [TOKEN_ALLOCATION_DRAFT.md](TOKEN_ALLOCATION_DRAFT.md).

Eligibility rules, reviewer authority, duplicate and Sybil treatment, revocation status, legal exclusions, and the snapshot time must be published before the snapshot and applied with a documented appeal path. Only canonical signed checkpoints count. Local test-ledger entries, self-issued records, pending claims, duplicates, revoked credits, and work that has not passed the published adjudication process do not convert.

`URSL` is the working ticker. If a material conflict requires a pre-launch rename, a dated public notice must preserve the same credit snapshot and token quantities. The renamed token still converts at one token unit for each eligible verified credit; a rename cannot reduce or duplicate a contributor allocation.

Before launch, credits remain non-transferable and create no current token claim or monetary value. The 1:1 rule does not guarantee a launch date, exchange listing, market price, liquidity, or conversion of the future token into money.

## Ecosystem scenarios and safety objective

A common syntax can improve interoperability and reduce representation cost. It does **not** align agent values, objectives, truth standards, permissions, or accountability. Compatible agents can still disagree, deceive, collude, amplify errors, or execute incompatible policies. Every deployment therefore retains authentication, authorization, provenance, semantic validation, human-auditable translation, and local policy enforcement outside the shared syntax.

| Scenario | Expected structure | Reward and governance posture |
|---|---|---|
| realistic hybrid default | Most agents continue to mix natural language, JSON, vendor protocols, and task-specific formats. Compatible peers negotiate Urusilla only where it produces measured benefit, with translation and fallback at every boundary. | Off-chain evidence records and non-transferable contributor credits; any conventional bounty remains separately funded. Reward measured link-level improvements rather than universal adoption. |
| healthy governed aspiration | Multiple independent implementations, profiles, operators, and model families interoperate through open version negotiation, reproducible tests, plural review, appeals, and reversible migrations. No single implementation or steward becomes mandatory. | Retrospective rewards favor interoperability, independent reproduction, safety, maintenance, and useful negative results. Governance remains reviewable and conflict-disclosed. |
| failed systemic outcome — explicit anti-goals | One protocol profile, implementation, operator, or funding gate becomes a monoculture; correlated failures propagate across agents; Sybil identities and collusive submitters capture evaluation or rewards; token speculation displaces technical work and public benefit. | Do not reward lock-in, raw adoption, identity multiplication, coordinated benchmark gaming, token price, or treasury influence. Pause the program when plural verification or safe fallback fails. |

The project does not define success as every agent using one language. Its safety objective is optional, measurable interoperability without making technical diversity, local control, or independent judgment harder to preserve.

## Why retrospective rewards fit this project

Prospective token incentives reward promises and attention. This project needs verified impact:

- fewer model tokens per safely completed task;
- lower complete-system energy, latency, or cost;
- better semantic fidelity, cross-model transfer, and recovery;
- stronger security, privacy, and provenance;
- independently reproduced integrations and negative results; and
- useful grammar extensions that survive held-out cross-play.

Optimism describes Retro Funding as an experimental program that rewards public goods after they create impact. Gitcoin's Allo Protocol separates recipient registries, funding pools, and allocation strategies. Both are useful design references, not endorsements of this proposal.

## What earns credit

Each claim is content-addressed and linked to an immutable commit, specification/profile digest, frozen data split, environment manifest, report, and license.

Human, agent-generated, and human-agent contributions use the same gates. Agent assistance must be disclosed, and the submission must identify the accountable submitter and the underlying contribution. Running more agents, creating more accounts, repeating a login, spending more time, or generating referrals does not create additional contribution evidence.

| Contribution class | Minimum evidence | Credit eligibility trigger |
|---|---|---|
| codec or runtime improvement | paired strong-baseline run and complete cost accounting | independently reproduced Pareto improvement |
| semantic or grammar extension | normative vectors, migration, fallback, and rollback | held-out unseen-partner acceptance gate |
| model integration | pinned implementation and cross-implementation transcript digest | verified external compatibility edge |
| security report | reproducible exploit or valid threat analysis | triage plus remediation or accepted risk |
| external independent reproduction | independently operated environment, disclosed shared inputs, and signed result digest | agreement or explained disagreement |
| benchmark or dataset | leakage review, license, frozen split, scoring code | accepted use in a release gate |
| negative result | preregistered method and reproducible evidence | prevents a false claim or bad deployment |
| documentation or translation tooling | tested technical accuracy and accessibility | maintained release inclusion |

Agent count, account count, logins, time spent, referrals, repository traffic, social posts, raw token volume, unverifiable agent claims, benchmark-only overfitting, and self-reported adoption do not earn technical impact credit.

The bundled Node.js lane is same-project cross-runtime compatibility evidence and does not satisfy the external independent reproduction reward class by itself.

## Impact record

The canonical off-chain record contains:

```text
record_version
epoch_id
contribution_id = hash(commit + artifacts + claim)
contributor_credit_subject
contribution_class
verified_credit_units
claimed_metrics
baseline_and_environment_digests
independent_reproduction_ids
conflict_disclosures
review_decision_and_reason_codes
appeal_state
expiry_or_recheck_date
attester_key_id
signature
```

Prompts, private conversations, user identity, unpublished vulnerabilities, model latent states, and benchmark secrets never go on a public chain. A public attestation stores only the record digest, schema/version, decision, issuer, issue time, expiry, and revocation relationship. Full evidence remains in an appropriate source repository or controlled disclosure system.

The [Ethereum Attestation Service](https://docs.attest.org/) is one possible implementation reference because it supports signed structured attestations onchain or offchain and explicitly distinguishes attestations from tokens. The project must also support a chain-independent signed JSON record so adoption never requires a wallet or a specific network.

## Credit allocation

No single compressibility score determines credits or payment. Each epoch publishes separate Pareto-qualified credit budgets for performance, interoperability, security, reproducibility, and maintenance. A contribution first passes non-compensable safety and exactness gates. Eligible work is then assessed on:

1. measured effect size and uncertainty;
2. breadth across held-out tasks, partners, models, and tokenizers;
3. independent reproduction quality;
4. durability across releases;
5. marginal value beyond prior work; and
6. maintenance and incident-response burden.

Epoch credit budgets are fixed before claims are revealed. Reviewers publish reason codes and conflicts. A contributor cannot approve their own claim. Closely related submissions are clustered to prevent duplicate-credit splitting. Credits are capped per contribution and may be delayed when durability cannot yet be observed.

The system deliberately credits a valid negative result and independent disconfirmation. Otherwise contributors would be encouraged to make every experiment look positive.

## Founder stewardship and evidence independence

The founder retains bootstrap stewardship of project identity, repository administration, release sequencing, compatibility direction, and emergency safety pauses. These responsibilities preserve continuity and do not create scientific privilege.

No founder, maintainer, sponsor, contributor, or reviewer may unilaterally accept evidence or approve their own credit claim. Acceptance follows published gates and a documented quorum of non-conflicted reviewers; contribution classes that require independent reproduction cannot waive it. Founder-authored work receives the same frozen splits, provenance labels, reproduction requirements, reason codes, and appeal path as any other contribution.

Stewards may reject integration or pause a release for documented safety, legal, security, or compatibility reasons. They may not rewrite an unfavorable measurement, label internal work as independent, suppress a valid negative result from the evidence record, or convert administrative control into extra scientific weight. Stewardship decisions and evidence judgments are recorded separately so either can be reviewed without confusing project direction with empirical truth.

## Anti-gaming controls

- frozen public development data plus sequestered evaluation sets;
- commit-before-evaluation claim registration;
- independent reruns on project-controlled and third-party runners;
- semantic exactness and task-success gates before efficiency scoring;
- code, artifact, identity, and funding-graph similarity review;
- rotating reviewers and mandatory conflict disclosure;
- external-versus-internal provenance labels;
- rate limits, minimum evidence, duplicate clustering, and appeal windows;
- delayed review or milestone checks for high-value credit claims, with separate escrow only for independently funded payments; and
- revocable attestations and public corrections for invalidated evidence.

Gitcoin's published grant rules explicitly treat Sybil identities and collusion as funding risks. A blockchain makes transactions visible; it does not make contributors unique or benchmark claims true.

## Staged rollout

Blockchain functions remain disabled throughout Phases 0 and 1. Progression is not automatic, and the maturity conditions in the go/no-go gates are minimum requirements rather than evidence that a chain is necessary.

### Phase 0 — off-chain credits, no money (current)

- GitHub contribution records and a public impact ledger;
- non-transferable, non-financial credits for accepted unique contribution records;
- equal submission access for human, agent-generated, and human-agent work under the same disclosure and evidence gates;
- no credit for agent or account count, logins, time spent, referrals, traffic, or popularity;
- no sale, transfer, redemption, conversion, listing, price, or monetary value; and
- independent review of scoring stability and gaming resistance.

### Phase 1 — conventional bounties

- fixed fiat bounties or grants funded before an epoch;
- human-approved payouts through a legally supported provider;
- public evidence and decision records;
- no assumption that a credit balance creates a payment entitlement; and
- tax, sanctions, employment, privacy, and jurisdiction review.

### Phase 2 — optional tokenless attestations after ecosystem maturity

- signed off-chain impact records;
- optional batched chain anchoring of record roots;
- revocation and appeal links;
- no tradability or active token claim before launch; and
- tokenless attestations do not themselves perform conversion, but canonical credits remain subject to the conditional 1:1 launch rule above.

### Phase 3 — optional reviewed settlement after ecosystem maturity

- milestone release through audited, narrowly scoped contracts;
- multisignature emergency controls and published signers;
- stable-value payout assets where lawful;
- capped pools and an incident pause mechanism.

[Allo Protocol](https://docs.allo.gitcoin.co/) may be evaluated as a modular allocation and distribution substrate at this phase. Adoption is conditional on contract review, chain availability, cost, governance fit, and a simpler-payment comparison.

### Conditional URSL contributor genesis pool — launch not authorized

No token, token claim, conversion, presale, airdrop, listing, liquidity program, or exchange-value promise is active today. If a future proposal authorizes an URSL launch after the go/no-go gates below and a new public-safety, security, governance, economic, and jurisdiction-specific legal review, it must establish the contributor genesis pool needed to honor the published conversion rule.

The [Token Allocation Research Draft](TOKEN_ALLOCATION_DRAFT.md) publishes one reviewable starting allocation: 25% for the Founding Maintainer under a nominal two-year release schedule, a separate 15% founder-led project reserve that cannot benefit the founder or related parties, 30% for a possible verified-contributor genesis pool, 20% for ongoing contributor and ecosystem rewards, and 10% for future core builders plus security, legal, and launch resilience. It is a proposal for review, not an active allocation or entitlement.

If such a launch proposal is approved, each active, verified, eligible canonical credit at the frozen public snapshot receives exactly one URSL, with no pro-rata dilution, discretionary haircut, multiplier, or post-snapshot repricing. Before any claims open, the proposal must fix a total supply and contributor-pool cap large enough to honor that rule, plus the snapshot, invalidation and appeal treatment, identity and Sybil controls, contract and signer controls, and jurisdictional eligibility. Credits do not create ownership, a receivable, a debt, or a current token claim before launch. A contributor may be ineligible under pre-published lawful terms, and no exchange listing, market price, liquidity, or ability to convert URSL into money is promised.

Neither credits nor any later token balance grants technical correctness, stronger evidence weight, maintainer status, a vote, governance power, release authority, registry authority, signing access, or project-account control.

## Legal and operational boundary

Crypto-asset classification and offering rules depend on the asset, transaction, promises, distribution, participants, and jurisdiction. The U.S. SEC states that some crypto assets may be offered and sold subject to an investment contract even when the asset is not itself a security. Korea's virtual-asset framework also imposes user-protection and market-conduct obligations. These sources make a legal review necessary; this document is not legal, tax, or investment advice.

No contract deployment, asset issuance, token claim, conversion, sale, airdrop, listing, treasury custody, or contributor payment is authorized by this policy.

## Energy and protocol fit

The reward mechanism must not negate the efficiency it funds. Use signed off-chain records by default, batch any public anchors, store only digests, and report chain fees and estimated energy separately. Urusilla messages may reference an impact-record digest, but payment logic remains outside the semantic kernel and cannot grant execution authority.

## Go/no-go gates

Move beyond the off-chain Phases 0 and 1 only when:

- at least two external contributors and one independent reproducer have valid records;
- mock scoring ranks known positive and negative cases sensibly;
- Sybil and collusion red teams do not produce an unbounded payout exploit;
- governance, appeal, privacy, sanctions, tax, and custody procedures are documented;
- a funded budget exists without a token presale; and
- the expected technical benefit exceeds operating, legal, and onchain cost.

Passing these gates does not authorize a chain or token. Any contributor genesis pool still requires a separate approved proposal with a fixed cap and snapshot, the published fixed 1:1 conversion rule, reviewed contracts and controls, and the additional legal and operational conditions described above. A chain or token must not determine scientific acceptance, evidence weight, governance membership, agent permissions, or protocol truth.

The default outcome is a transparent off-chain credit record, with conventional bounties only when separately funded. If ecosystem maturity and a concrete need are later demonstrated, tokenless attestations may add portable provenance, and a separately gated fixed contributor pool may be proposed without making speculation a prerequisite for improving the language.

## Primary and official references

- [Ethereum Attestation Service documentation](https://docs.attest.org/)
- [Gitcoin Allo Protocol documentation](https://docs.allo.gitcoin.co/)
- [Optimism governance FAQ: Retro Funding](https://docs.optimism.io/governance/gov-faq)
- [Gitcoin grant rules on Sybil attacks and collusion](https://support.gitcoin.co/gitcoin-knowledge-base/gitcoin-grants/general-questions/are-there-any-grant-rules-i-need-to-follow)
- [U.S. SEC: Transactions Involving Crypto Assets](https://www.sec.gov/resources-small-businesses/capital-raising-building-blocks/transactions-involving-crypto-assets)
- [Korea Financial Services Commission: Virtual Asset User Protection Act implementation](https://www.fsc.go.kr/eng/pr010101/82534)
