# Local Contribution Ledger MVP

Status: local research prototype; non-financial and non-transferable

This directory implements a standard-library-only append-only ledger for
retrospective contribution test points. It is not a blockchain, coin, token,
wallet, treasury, payment rail, or financial product. It performs no network
operation and contains no future conversion, redemption, transfer, approval,
allowance, exchange, pricing, or governance-by-balance function.

An `award_granted` event in this prototype is a test record, not an accepted or
verified Urusilla contribution credit. Anyone can instantiate a separate local
ledger and supply a decision digest. The implementation does not authenticate
reviewers, enforce a non-conflicted quorum, designate a canonical ledger, or
prove the truth or independence of evidence. Hash chains and Merkle roots prove
internal content consistency only. A future canonical credit system would need
separately authenticated adjudication and signed public checkpoints.

## Bounded purpose

The MVP tests whether evidence-linked contribution decisions can be recorded
deterministically without rewriting history. It supports five event types:

1. `epoch_opened`
2. `contribution_registered`
3. `award_granted`
4. `award_revoked`
5. `correction_recorded`

Revocations and corrections append new records. They never delete or modify an
earlier event. A correction carries only a reason code and corrected-record
digest; it has no economic effect. A revocation releases active test-point
budget but permanently prevents a second award for that contribution.

## Fail-closed properties

- Every event binds `seq`, `prev_event_id`, complete payload, ledger ID, and
  schema version into a SHA-256 `event_id`.
- JSONL import requires the exact restricted canonical JSON spelling, rejects
  duplicate keys and floating-point numbers, and replays every state change.
- Epoch budget and policy are fixed when the epoch opens.
- Points are positive bounded integers. Boolean and floating-point values do
  not qualify as integers.
- The same exact contribution cannot be registered under another subject or
  epoch because the contribution ID excludes identity and epoch.
- Payloads and imported events use exact field sets. Unknown schemas, fields,
  event types, chain links, and identifiers fail closed.
- Public-ledger fields named for email, raw prompts, secrets, credentials,
  conversations, or raw messages are rejected recursively.
- Export returns deterministic state plus an ordered event Merkle root. It
  creates no on-chain anchor and grants no authority.

Exact hashes stop exact duplicate and replay attacks. They do not prove human
identity, reviewer independence, originality of slightly modified work, or the
truth of off-chain evidence. Those remain mandatory review boundaries before
any real-world bounty could be considered.

## Minimal example

```python
from contribution_ledger import ContributionLedger

ledger = ContributionLedger("local-research-ledger")
ledger.open_epoch(
    epoch_id="epoch-001",
    budget_points=100,
    policy_digest="a" * 64,
)
claim = ledger.register_contribution(
    epoch_id="epoch-001",
    contributor_ref="subject:alice",
    contribution_class="runtime",
    commit_digest="b" * 64,
    claim_digest="c" * 64,
    artifact_digests=["d" * 64],
)
ledger.grant_award(
    epoch_id="epoch-001",
    contribution_id=claim["payload"]["contribution_id"],
    points=40,
    decision_digest="e" * 64,
)

jsonl = ledger.to_jsonl()
snapshot = ledger.snapshot_json()
```

Run the bounded test suite from the repository root:

```text
python3 -m unittest -v contribution_ledger.test_ledger
```
