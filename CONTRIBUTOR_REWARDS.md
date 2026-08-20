# Urusilla Verifiable Contributor Rewards

Status: design proposal; no blockchain launch, token, treasury, contract, or payment is active  
Date: 2026-08-20

## Decision

Rewarding contributors who measurably improve the language is aligned with the project. Launching a blockchain or issuing a tradable project token now is not proposed or authorized.

The recommended design is a **retrospective, evidence-based reward system**. Work earns consideration after its effects are measured, disclosed, and reproduced; promises, popularity, and projected adoption are not impact. The first production rewards, if funded, should use ordinary bounties or grants through legally reviewed payment and escrow providers.

Blockchain use is disabled during the bootstrap period. Only after the ecosystem passes explicit maturity, governance, security, and legal gates may a chain be considered, and then only to anchor record digests, carry revocable attestations, or settle already approved rewards. A chain is not the language transport, benchmark judge, identity oracle, scientific authority, or substitute for legal and security review. A proprietary project token is outside this roadmap.

## Ecosystem scenarios and safety objective

A common syntax can improve interoperability and reduce representation cost. It does **not** align agent values, objectives, truth standards, permissions, or accountability. Compatible agents can still disagree, deceive, collude, amplify errors, or execute incompatible policies. Every deployment therefore retains authentication, authorization, provenance, semantic validation, human-auditable translation, and local policy enforcement outside the shared syntax.

| Scenario | Expected structure | Reward and governance posture |
|---|---|---|
| realistic hybrid default | Most agents continue to mix natural language, JSON, vendor protocols, and task-specific formats. Compatible peers negotiate Urusilla only where it produces measured benefit, with translation and fallback at every boundary. | Off-chain evidence records and conventional bounties; reward measured link-level improvements rather than universal adoption. |
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

| Contribution class | Minimum evidence | Reward trigger |
|---|---|---|
| codec or runtime improvement | paired strong-baseline run and complete cost accounting | independently reproduced Pareto improvement |
| semantic or grammar extension | normative vectors, migration, fallback, and rollback | held-out unseen-partner acceptance gate |
| model integration | pinned implementation and cross-implementation transcript digest | verified external compatibility edge |
| security report | reproducible exploit or valid threat analysis | triage plus remediation or accepted risk |
| external independent reproduction | independently operated environment, disclosed shared inputs, and signed result digest | agreement or explained disagreement |
| benchmark or dataset | leakage review, license, frozen split, scoring code | accepted use in a release gate |
| negative result | preregistered method and reproducible evidence | prevents a false claim or bad deployment |
| documentation or translation tooling | tested technical accuracy and accessibility | maintained release inclusion |

Repository traffic, social posts, raw token volume, unverifiable agent claims, benchmark-only overfitting, and self-reported adoption do not earn technical impact credit.

The bundled Node.js lane is same-project cross-runtime compatibility evidence and does not satisfy the external independent reproduction reward class by itself.

## Impact record

The canonical off-chain record contains:

```text
record_version
epoch_id
contribution_id = hash(commit + artifacts + claim)
contributor_payout_subject
contribution_class
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

## Reward allocation

No single compressibility score determines payment. Each epoch publishes separate Pareto-qualified pools for performance, interoperability, security, reproducibility, and maintenance. A contribution first passes non-compensable safety and exactness gates. Eligible work is then assessed on:

1. measured effect size and uncertainty;
2. breadth across held-out tasks, partners, models, and tokenizers;
3. independent reproduction quality;
4. durability across releases;
5. marginal value beyond prior work; and
6. maintenance and incident-response burden.

Epoch budgets are fixed before claims are revealed. Reviewers publish reason codes and conflicts. A contributor cannot approve their own claim. Closely related submissions are clustered to prevent duplicate-credit splitting. Rewards are capped per contribution and partially delayed when durability cannot yet be observed.

The system deliberately rewards a valid negative result and independent disconfirmation. Otherwise contributors would be paid to make every experiment look positive.

## Founder stewardship and evidence independence

The founder retains bootstrap stewardship of project identity, repository administration, release sequencing, compatibility direction, and emergency safety pauses. These responsibilities preserve continuity and do not create scientific privilege.

No founder, maintainer, sponsor, contributor, or reviewer may unilaterally accept evidence or approve their own claim. Acceptance follows published gates and a documented quorum of non-conflicted reviewers; reward classes that require independent reproduction cannot waive it. Founder-authored work receives the same frozen splits, provenance labels, reproduction requirements, reason codes, and appeal path as any other contribution.

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
- delayed or milestone escrow for high-value claims; and
- revocable attestations and public corrections for invalidated evidence.

Gitcoin's published grant rules explicitly treat Sybil identities and collusion as funding risks. A blockchain makes transactions visible; it does not make contributors unique or benchmark claims true.

## Staged rollout

Blockchain functions remain disabled throughout Phases 0 and 1. Progression is not automatic, and the maturity conditions in the go/no-go gates are minimum requirements rather than evidence that a chain is necessary.

### Phase 0 — evidence points, no money

- GitHub contribution records and a public impact ledger;
- non-transferable, non-financial test points;
- mock epochs against historical project contributions;
- independent review of scoring stability and gaming resistance.

### Phase 1 — conventional bounties

- fixed fiat bounties or grants funded before an epoch;
- human-approved payouts through a legally supported provider;
- public evidence and decision records;
- tax, sanctions, employment, privacy, and jurisdiction review.

### Phase 2 — optional tokenless attestations after ecosystem maturity

- signed off-chain impact records;
- optional batched chain anchoring of record roots;
- revocation and appeal links;
- no tradability and no promise of future token conversion.

### Phase 3 — optional reviewed settlement after ecosystem maturity

- milestone release through audited, narrowly scoped contracts;
- multisignature emergency controls and published signers;
- stable-value payout assets where lawful;
- capped pools and an incident pause mechanism.

[Allo Protocol](https://docs.allo.gitcoin.co/) may be evaluated as a modular allocation and distribution substrate at this phase. Adoption is conditional on contract review, chain availability, cost, governance fit, and a simpler-payment comparison.

### No token phase

These phases do not culminate in a proprietary token, presale, airdrop, or promise that points or attestations will become transferable assets. Any later token proposal would be outside this rewards design and would require a new public-safety, governance, economic, and jurisdiction-specific legal review. Contributors must not be asked to rely on such a proposal or expect future conversion.

## Legal and operational boundary

Crypto-asset classification and offering rules depend on the asset, transaction, promises, distribution, participants, and jurisdiction. The U.S. SEC states that some crypto assets may be offered and sold subject to an investment contract even when the asset is not itself a security. Korea's virtual-asset framework also imposes user-protection and market-conduct obligations. These sources make a legal review necessary; this document is not legal, tax, or investment advice.

No contract deployment, asset issuance, sale, airdrop, treasury custody, or contributor payment is authorized by this proposal.

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

Even after these gates pass, a chain integration may only anchor digests, carry attestations, or settle independently approved rewards. It must not determine scientific acceptance, governance membership, agent permissions, or protocol truth.

The default outcome is a transparent, off-chain contributor-bounty program. If ecosystem maturity and a concrete need are later demonstrated, optional tokenless attestations can add portable, verifiable provenance without making speculation a prerequisite for improving the language.

## Primary and official references

- [Ethereum Attestation Service documentation](https://docs.attest.org/)
- [Gitcoin Allo Protocol documentation](https://docs.allo.gitcoin.co/)
- [Optimism governance FAQ: Retro Funding](https://docs.optimism.io/governance/gov-faq)
- [Gitcoin grant rules on Sybil attacks and collusion](https://support.gitcoin.co/gitcoin-knowledge-base/gitcoin-grants/general-questions/are-there-any-grant-rules-i-need-to-follow)
- [U.S. SEC: Transactions Involving Crypto Assets](https://www.sec.gov/resources-small-businesses/capital-raising-building-blocks/transactions-involving-crypto-assets)
- [Korea Financial Services Commission: Virtual Asset User Protection Act implementation](https://www.fsc.go.kr/eng/pr010101/82534)
