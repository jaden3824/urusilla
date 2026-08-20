# Post-Cutover External OOD Reconfirmation for Transparent Fallback v0.8

Status: completed local two-pass reconfirmation  
Evidence date: 2026-08-20  
Claim boundary: exact serialization and record-contract evidence only

## Result in one sentence

Urusilla transparent fallback v0.8 preserved exact deterministic recovery and zero positive bound receiver-token regret on the retained 42-record official-example corpus: bound transport tied the raw plain minimum, compact modes recorded **0/168 bound and 0/168 standalone** strict wins, and standalone text remained above raw plain text after its integrity envelope.

## Honest post-cutover protocol

This is a post-cutover reconfirmation, not a new external-corpus preregistration. The evaluator reused the exact archived source and repository-license bytes from the earlier confirmation without network access. It verified every archived byte sequence against the digest recorded for its pinned repository revision, rebuilt the same source-preserving wrappers, and obtained the unchanged corpus SHA-256 `6a00c011af8a2b264ec4e79bca84106b143439b3df4ba4e969e48e199fb9d978` and message-sequence SHA-256 `f73e8f520a2b1720dcbf8ab74beb928fe356661e3d6a84259b0ff0c64c6d782b`.

The new manifest was frozen at `2026-08-20T14:08:00+00:00`, before importing v0.8, loading a tokenizer, or measuring tokens. The primary run began at `2026-08-20T14:11:43+00:00`; the repeat began at `2026-08-20T14:11:48+00:00`. Both were bound to the same new Urusilla candidate-source identities and selection-contract digest. The corpus was not used for training or tuning, and the candidate, thresholds, profiles, tokenizer identities, source selection, and tie rules were not modified after the retained freeze.

This is strong local procedural evidence, not an externally timestamped preregistration or independent operator reproduction.

## Archived evidence

The public evidence package is under `evidence/external_ood_v08_confirmatory/`.

| Artifact | SHA-256 |
|---|---|
| Premeasurement manifest | `834047439e8bd13b244c913343c31581c2fd242b331fd259d749fb707f54ff64` |
| Frozen corpus | `6a00c011af8a2b264ec4e79bca84106b143439b3df4ba4e969e48e199fb9d978` |
| Message sequence | `f73e8f520a2b1720dcbf8ab74beb928fe356661e3d6a84259b0ff0c64c6d782b` |
| Primary measurement | `0f6dd299203021e60186613caede5dfeeeb8d6fad561f0dd1203d9be6563a44d` |
| Repeat measurement | `aae93e4d9023e83b220fe6fee481df3f032bd48891065b410ef3f226f016f619` |
| Repeat-stable deterministic outcome | `3bbbd740a5a22e00a794052efc224ca98f2ce0240a49abbc93c213606918247f` |
| Frozen evaluator | `fcb03b568fd8babe3132a6c2556158a8eab7ba87691e10738b20a867faef5d6a` |
| Frozen v0.8 selection contract | `fcb90039b2a7e193e3b274b6a4cefcb7cf851b116e397bcb721e0b268c5c36b0` |
| Evidence inventory | `19cca24a3e0663ba8fa8b9a56c0614c17c8e7ca7470428ba49371ffaadb27ed0` |

The package retains 38 exact external source or repository-license files and snapshots of all 11 candidate or evaluator sources. `DIGESTS.json` covers 54 files and excludes only itself and its detached checksum.

## Corpus and source-preserving transform

| Partition | Pinned repository revision | Records |
|---|---|---:|
| OpenAPI 3.0 official pass examples | `6d6084fb9ca086dc6db3de9e4089d5fb33c753df` | 6 |
| AsyncAPI 3.1 official examples | `3afe09b227f408fc4547e294c6cf90dcd280f4db` | 23 |
| W3C Web of Things Thing Description 1.1 validation examples | `967c957a63c87c71bf55801cffe0694df2efc575` | 6 |
| OpenTelemetry Protocol JSON examples | `ac2c4b5d1f3a6079de62f9afec860158ecc8af09` | 7 |
| Total |  | 42 |

Each selected source object is retained losslessly as canonical JSON inside a conservative project-authored ASSERT wrapper. Source URI, revision, path, locator, source-file digest, and canonical-object digest remain attached. The wrapper is not a native mapping for any selected standard, and this corpus is not representative deployed agent traffic.

## Exactness, deterministic re-encoding, and repeat stability

Both retained runs passed all 504/504 exactness trials and all 504/504 deterministic re-encoding trials.

| Path | Exact | Deterministic | Trials |
|---|---:|---:|---:|
| Four direct payload modes | 168 | 168 | 168 |
| Bound selected records across four tokenizers | 168 | 168 | 168 |
| Standalone selected records across four tokenizers | 168 | 168 | 168 |
| Total per run | 504 | 504 | 504 |

Timestamps, platform strings, and machine-specific latency samples differ by design. After excluding only those nondeterministic fields and the run label, both complete claim-bearing outcome objects have the identical digest `3bbbd740a5a22e00a794052efc224ca98f2ce0240a49abbc93c213606918247f`.

## Receiver-token outcome

The bound contract carries mode, sequence, and integrity information outside receiver text. Every bound warm choice and every bound cold choice was Controlled Terse English, so compact modes won `0/168` bound choices. Each complete bound cold session tied the raw per-message plain minimum exactly.

| Receiver tokenizer | Raw best plain | Bound cold | Bound delta | Standalone cold | Standalone delta vs raw | Overhead |
|---|---:|---:|---:|---:|---:|---:|
| `cl100k_base` | 46,653 | 46,653 | 0 | 47,738 | +1,085 | 2.326% |
| `o200k_base` | 46,652 | 46,652 | 0 | 47,697 | +1,045 | 2.240% |
| `qwen2_5_7b_instruct` | 50,855 | 50,855 | 0 | 52,382 | +1,527 | 3.003% |
| `mistral_7b_instruct_v03` | 64,628 | 64,628 | 0 | 66,220 | +1,592 | 2.463% |

Standalone warm selection recorded `0/168` strict compact wins. It selected Controlled Terse English for all 42 messages under every tokenizer, as did every cold plan. The matched-integrity standalone selector tied its plain-only baseline, but standalone cold text remained **2.24% to 3.00%** above raw plain text. This is a safe fallback result, not a compact-language compression result.

The zero-positive-bound-regret result also holds for every complete standard partition.

## Metadata accounting and evaluator correction

An earlier diagnostic run exposed a real evaluator defect: standalone metadata accounting reused bound-selected payload bytes. The evaluator was fixed to account for bound and standalone payloads independently, and a new premeasurement manifest was frozen before either retained measurement. No result from the diagnostic run is part of this evidence package.

All retained component sums are exact. Bound records contain 180,044 payload bytes and 1,050 separately accounted metadata bytes, for 181,094 bytes under every tokenizer. Standalone records contain the same 180,044 payload bytes plus 1,764 inline metadata bytes, for 181,808 bytes under every tokenizer.

## Record-contract mutation checks

For each of four tokenizers and each of 42 records, each run mutated mode, sequence, payload, and tag and supplied a wrong expected sequence.

| Contract | Rejected per run | Attempted per run |
|---|---:|---:|
| Bound | 840 | 840 |
| Standalone | 840 | 840 |
| Total | 1,680 | 1,680 |

The checks use a public deterministic HMAC fixture key. They validate parsing and deterministic rejection, not production key management or resistance to an attacker who knows the fixture key.

## Hypothesis outcomes

- H1 exact deterministic recovery: passed in both runs.
- H2 zero positive bound receiver-token regret: passed as a fallback tie.
- H3 complete, contract-specific metadata accounting: passed after the premeasurement evaluator correction and refreeze.
- H4 zero positive standalone regret against the matched-integrity plain baseline: passed.
- H5 strict compact-selection rule: passed with zero bound and zero standalone warm compact wins.
- H6 aggregate bound cold outcome: tie for all four tokenizers, not an improvement.
- H7 deterministic integrity-mutation rejection: passed.

## Latency boundary

In the primary run, direct minified JSON encode p50 was 15.48 microseconds. Bound adaptive encode/select p50 ranged from 4.04 to 16.26 milliseconds across the four tokenizers. The paths perform unequal work, the measurements are machine-specific, and the repeat has different timing samples. No universal speed claim follows.

## Claim boundary

This lane reconfirms bounded serialization, deterministic reselection, transparent fallback, component accounting, and test-fixture mutation rejection on the retained 42-record corpus. It does not demonstrate compact-language generalization, receiver understanding, sender generation, end-to-end task success, aggregate token savings, energy savings, external adoption, independent reproduction, or a state-of-the-art result.
