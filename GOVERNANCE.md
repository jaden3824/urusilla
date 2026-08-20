# Urusilla Governance

Status: experimental founder-led project  
Effective date: 2026-08-20

## Founding stewardship

`jaden3824` is the Founding Maintainer, original project initiator, and initial developer and development steward of Urusilla. This attribution is permanent in the canonical project history, release metadata, citations, and provenance records. A later governance transition, rename, or standards contribution must preserve it.

The canonical project is the repository at `https://github.com/jaden3824/urusilla`. Mirrors, forks, compatible implementations, and independently evolved languages are welcome under the license, but they may not represent themselves as the canonical project or an official release without authorization.

## Experimental Stewardship Phase

The project currently uses founder-led governance. The Founding Maintainer has final authority over:

- the roadmap and research priorities;
- merge, revert, and release decisions in the canonical repository;
- ratification or rejection of core semantics and official extension profiles;
- release signing roots, provenance manifests, and compatibility-registry policy;
- security embargoes, emergency pauses, and supported-version decisions;
- appointment, scope, and removal of maintainers and reviewers;
- official project communications, names, domains, and visual identity; and
- amendments to this governance document.

Delegated maintainers exercise only the authority explicitly assigned to them. Contribution, usage, funding, token ownership, benchmark performance, or popularity does not automatically grant governance power.

Founding status is attribution and repository-governance authority, not scientific privilege. Founder-authored code, data, benchmarks, and interpretations receive the same provenance labels, comparison rules, uncertainty treatment, and external-reproduction gates as any other contribution. The Founding Maintainer cannot convert internal evidence into an independent result by approval.

The Experimental Stewardship Phase has no automatic expiry. Only an explicit, signed, public decision by the Founding Maintainer can transition the canonical project to a foundation, standards body, council, or other governance model.

## Constraints on founder authority

Strong leadership remains bounded by public technical and legal commitments:

- published releases and semantic meanings are immutable by version and content hash;
- a breaking meaning change requires a new version, migration, tests, and rollback path;
- benchmark inputs, unfavorable results, external-adoption labels, and known limitations may not be falsified;
- the Apache-2.0 license and contributor copyrights remain in force;
- contributor credit may not be removed from accepted history without a documented legal or integrity reason;
- private user data, prompts, message content, and telemetry may not be used for governance leverage;
- safety and semantic release gates cannot be silently waived;
- scientific claim gates apply equally to founder-authored and contributor-authored evidence; and
- any funded treasury requires separate public rules, conflict disclosure, and controls that prevent unilateral withdrawal.

These constraints make the canonical releases predictable enough for other agents and vendors to adopt while preserving clear founder control of direction and publication.

## Ecosystem scenarios and anti-goals

Urusilla does not assume that one language should replace every agent protocol, human-readable exchange, or general-purpose data format. The project distinguishes three ecosystem scenarios:

1. **Realistic hybrid default:** agents use several protocols, registries, vendors, and representations. Urusilla is one negotiated syntax and semantic layer among JSON, natural language, vendor APIs, domain standards, and other machine-oriented formats. Bridges and explicit fallback remain normal.
2. **Healthy governed aspiration:** compatible implementations share bounded semantic contracts while remaining independently operated. Competing registries, validators, profiles, transports, and governance communities can interoperate through published vectors and provenance without surrendering local policy or safety controls.
3. **Failed systemic outcome and anti-goal:** a single implementation, registry, operator, profile, or economic asset becomes a monoculture; compromise or semantic drift propagates ecosystem-wide; Sybil identities or colluding reviewers capture evidence and rewards; or token speculation becomes the reason to adopt the language. Coercive adoption, hidden lock-in, unverifiable agent traffic, and claims of universal authority belong in this failed scenario.

The project designs for the hybrid default, works toward the governed pluralism of the healthy scenario, and treats the failed scenario as a safety failure rather than a growth milestone. Adoption volume alone is never evidence that the ecosystem is healthy.

## Dual-use safety boundary

A common machine syntax can lower the cost of beneficial coordination, but it can also lower the cost of collusion, manipulation, automated abuse, and rapid propagation of unsafe instructions. Common syntax does not align values, establish identity, grant authorization, make claims true, or make participants trustworthy.

Public evolution therefore requires the following separations and controls:

- registries describe identifiers, schemas, profiles, lifecycle state, and provenance; validators independently enforce semantic, resource, authorization, and canonicalization rules;
- at least two independently operated implementations should cross-check normative vectors before a profile can be described as interoperable, and same-project compatibility is labeled separately;
- new profiles move through experimental, trial, and candidate stages before ratification, with content-addressed artifacts, bounded exposure, explicit quarantine criteria, rollback paths, and revocation or deprecation procedures;
- a compromised registry entry, validator, implementation, profile, or signing key can be isolated without requiring the entire ecosystem to accept its state;
- evidence and reward review remain provenance-aware, conflict-disclosed, retrospective, and independently reproducible; popularity, token holdings, automated votes, or raw traffic cannot substitute for technical evidence; and
- no blockchain, proprietary token, DAO, or onchain governance launch is authorized at this stage. After ecosystem maturity and separate legal, security, and governance review, a chain may at most record compact digests, attestations, or settlement events; it must not become the semantic authority, validator, identity oracle, benchmark judge, or mandatory transport.

Founder stewardship applies to the canonical repository and release process, not to truth by decree. The Founding Maintainer may accept or reject project changes, but cannot unilaterally turn internal work into independent evidence, waive a declared scientific gate, approve a personal reward claim, or require other implementations to accept unsupported results.

## Change process

Anyone may open an issue or pull request. A proposal that changes normative semantics must include motivation, version impact, observable meaning, positive and negative vectors, migration and fallback behavior, security and privacy analysis, benchmark evidence, and an attribution record.

Review proceeds through four states:

1. **proposal** — public discussion and evidence collection;
2. **trial** — content-addressed experimental profile with no core claim;
3. **candidate** — held-out, cross-implementation, safety, and rollback gates passed; and
4. **ratified** — explicitly approved and signed by the Founding Maintainer.

No vote, popularity threshold, automated agent decision, reward allocation, or blockchain transaction can bypass ratification during the Experimental Stewardship Phase. The Founding Maintainer should publish a concise reason when rejecting a candidate that passed its declared gates.

## Maintainer and reviewer roles

The Founding Maintainer may delegate bounded roles such as codec maintainer, semantic editor, security reviewer, benchmark curator, integration maintainer, release operator, and community moderator. Role assignments, protected paths, signing access, conflicts, and expiry dates should be public where security permits.

Reviewers must disclose financial, employment, model-provider, benchmark-author, and contributor conflicts relevant to a decision. A reviewer may not be the sole approver of their own reward claim or conformance implementation.

## Contributor rewards

The separate [`CONTRIBUTOR_REWARDS.md`](CONTRIBUTOR_REWARDS.md) proposal does not create a DAO, token vote, or treasury. If rewards are later activated, funding decisions cannot alter core semantics, release signatures, founder attribution, or canonical-repository control. Technical acceptance and financial reward remain separate decisions.

## Attribution and provenance

Every official release carries:

- the canonical repository and immutable commit;
- the Founding Maintainer attribution;
- specification, Capsule, implementation, and conformance-report digests;
- the complete list of material contributors for that release; and
- a compact `source_id` that resolves to the full source manifest.

Hot agent messages carry only the compact source identifier. They do not carry personal data or imply that the Founding Maintainer authored, endorsed, or is liable for each message sent by downstream agents.

## Succession, inactivity, and forks

The Founding Maintainer may designate a successor or establish a later council through a signed public amendment. A succession record must preserve the historical founder attribution and published release identities.

If the canonical project becomes inactive, the Apache-2.0 license permits continued independent development. The software license does not grant a right to claim that a fork is the canonical project or an official release. Forks are requested to choose a distinguishable name and provenance root unless explicitly authorized; this is a project-identity policy, not an added source-code license restriction, and it is enforceable only to the extent supported by applicable trademark, attribution, and unfair-competition law. No trademark registration is claimed by this draft. This exit right protects users without erasing the canonical project's origin.

## Current institutional status

Urusilla is not a standards body, foundation, DAO, incorporated association, or official A2A project. No proprietary token, treasury, membership class, or voting asset exists. The current governance is an explicit founder-led open-source research arrangement.
