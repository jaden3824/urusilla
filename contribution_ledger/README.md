# Local Contribution Ledger MVP

Status: local research prototype with a synthetic signed-checkpoint trial;
non-financial, non-transferable, and non-authoritative

`ledger.py` implements a standard-library-only append-only ledger for
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

The optional `checkpoint.py` trial tests one narrow part of that later path. It
binds an exact replay-verified snapshot, contribution-policy digest, reviewer-
roster digest, checkpoint time, appeal deadline, trust-policy digest, and key
ID to a detached Ed25519 signature. Verification trusts only a public key, key
ID, trust-policy digest, expected snapshot, and review-metadata pins obtained
separately by the caller. The artifact cannot supply its own replacement key.
This proves key approval of exact bytes;
it does not authenticate real-world reviewer identity, establish a quorum,
issue canonical credit, create a token claim, authorize an effect, or anchor a
timestamp or record onchain.

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

## Synthetic signed-checkpoint trial

`build_checkpoint()` first replays the local ledger and freezes its canonical
snapshot. `sign_checkpoint()` and `verify_checkpoint()` require the optional
`evidence-auth` dependency. Signing accepts a raw 32-byte Ed25519 seed for the
bounded offline trial, but no private or public key is written into the
checkpoint artifact. Production key custody, signer publication, reviewer
quorum, and canonical checkpoint designation remain outside this prototype.

The verifier rejects snapshot or metadata mutation, a mismatched caller-pinned
trust policy or key ID, substituted public keys, malformed signatures,
noncanonical or oversized snapshot JSON, invalid appeal windows, and any attempt
to enable canonical credit, a token claim, transfer, conversion, or effects.

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

Run the standard-library ledger tests from the repository root:

```text
python3 -m unittest discover -s tests -p 'test_contribution_ledger.py' -v
```

Install the optional signature dependency before running the checkpoint tests:

```text
python3 -m pip install '.[evidence-auth]'
python3 -m unittest discover -s tests -p 'test_contribution_checkpoint.py' -v
```
