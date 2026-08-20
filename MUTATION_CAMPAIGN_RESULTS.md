# Deterministic cross-codec mutation campaign

Status: bounded mutation testing, not coverage-guided fuzzing  
Evidence cut-off: 2026-08-20

## Result

Five representations decoded and re-encoded the same 280 canonical messages exactly. Recursive map insertion-order changes left every encoded artifact unchanged, for **1,400/1,400 checks**.

The campaign then applied eight deterministic operations to every message under every representation: bit or character replacement, deletion, insertion, append, truncation, prefix insertion, and a second replacement family. It changed **11,200 complete artifacts** without recomputing an integrity field.

All four integrity-protected representations rejected every mutation:

| Representation | Mutation attempts | Rejected | Accepted |
|---|---:|---:|---:|
| Reference binary wire | 2,240 | 2,240 | 0 |
| Static-profile binary wire | 2,240 | 2,240 | 0 |
| Checksummed controlled-terse envelope | 2,240 | 2,240 | 0 |
| Token surface v0.4 | 2,240 | 2,240 | 0 |

Raw Controlled Terse English has no integrity field. It rejected **1,956/2,240** mutations, but **284/2,240** became different canonical, semantically valid messages. This is not a parser escape: each accepted result re-encoded byte-for-byte to the mutated text and represented different semantics. It is an expected integrity limitation of readable plaintext without an authenticated or checksummed envelope.

Wrapping the identical readable payload in the adaptive envelope changed the result from 284 silent semantic mutations to zero accepted mutations in this campaign. The outer checksum detects accidental damage. It does not authenticate a sender or protect against an attacker who can recompute the checksum.

## Frozen design

- Corpus messages: `280`
- Corpus SHA-256: `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`
- Seed: `182648318593056`
- Mutations per message and representation: `8`
- Exact decodes: `1,400`
- Insertion-order checks: `1,400`
- Mutation attempts: `11,200`
- Mutation rejections: `10,916`
- Canonical semantic mutations accepted by raw readable text: `284`
- Encoded-sequence SHA-256: `f6bfb3cde39d220a275b8326d8fbb61072747d3756aa488b863ac91829f29a61`
- Mutation-sequence SHA-256: `d5e992e8567d34807f2c820ee6ae367cda294bf3f596390dd72e4b4030634065`

## Interpretation

The result supports three bounded conclusions:

1. all five pinned reference paths agree on the original canonical messages;
2. canonical encoding is independent of nested map insertion order for the frozen corpus; and
3. the integrity-protected paths reject the exact 8-operation mutation set.

It also exposes a useful negative result: a readable grammar can remain syntactically and semantically valid after accidental character loss. Readability and semantic validation do not replace transport integrity.

## Limitations

- This is deterministic mutation testing, not coverage-guided fuzzing, symbolic execution, or a proof over all inputs.
- The source corpus is synthetic and project-authored.
- Mutations do not recompute checksums; an active attacker can do so.
- The campaign does not exercise packet boundaries, concurrency, streaming, compression bombs, authentication, signatures, replay, or authorization.
- The campaign tests the pinned Python implementation, not cross-language behavior.
- Eight operations per artifact sample a tiny fraction of possible corruptions.
- A successful rejection does not prove constant-time behavior or freedom from denial-of-service bugs.

## Reproduction

```bash
python3 urusilla_mutation_campaign.py
python3 -m unittest test_urusilla_mutation_campaign.py -v
```
