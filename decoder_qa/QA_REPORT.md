# Deterministic Decoder Quality-Assurance Report

- Run time (UTC): `2026-08-23T14:09:58+00:00`
- Execution ID: `ee8c0e17019d52093d031a419f6b856eac025340a85910626a445bc8c3fcb855`
- Machine-readable result SHA-256: `4a551d4c8699570921b7e1f6761a875489c2d3c6600d715198c9340b46df8084`
- Outcome: **passed**
- Scope: local saved parser fixtures and documented grammar only
- External activity: none; network audit events were denied and credential environment variables were not inherited

## Result

The four deterministic behavior campaigns completed `5232` checks. The selected public baseline completed `101` tests, and the QA regression suite completed `15` tests with `0` expected failures. `0` shared-code findings remain reproducible. Shared code was not edited.

This is quality-assurance evidence, not a conformance badge, security audit, vulnerability assessment, adoption claim, or standards claim.

## Execution summary

| Campaign | Status | Cases/tests | Seconds |
|---|---:|---:|---:|
| baseline | passed | 101 | 2.845488 |
| roundtrip | passed | 1097 | 0.664965 |
| boundaries | passed | 1952 | 0.269111 |
| mutations | passed | 2048 | 0.145838 |
| replay | passed | 135 | 0.559369 |
| known_defects | passed | 16 | 0.087742 |
| qa_tests | passed | 15 | 1.683038 |

## Exact behavior check-unit counts

A check unit is the campaign's declared deterministic accounting unit (for example, one input, one replay append, or one grouped oracle); it is not necessarily one unittest method or one assertion.

### roundtrip

- `generated_v01_map_order`: `128`
- `generated_v01_round_trips`: `128`
- `generated_v02_map_order`: `128`
- `generated_v02_round_trips`: `128`
- `grammar_capsule_digest`: `1`
- `grammar_capsule_positive_vector`: `1`
- `gzip_v02_round_trips`: `21`
- `public_corpus_digest`: `1`
- `public_v01_round_trips`: `280`
- `public_v02_round_trips`: `280`
- `v02_profile_capsule_round_trip`: `1`
- `total_cases`: `1097`

### boundaries

- `actual_frame_size_limits`: `2`
- `checksum_mutations`: `6`
- `declared_collection_limits`: `2`
- `declared_frame_size_limits`: `2`
- `declared_string_limits`: `2`
- `dictionary_count_boundary`: `2`
- `documented_limit_constants`: `6`
- `duplicate_dictionary_and_fields`: `3`
- `malformed_headers_and_varints`: `5`
- `proper_prefix_truncations`: `1901`
- `public_type_boundaries`: `3`
- `recipient_count_boundary`: `2`
- `scalar_boundaries`: `2`
- `scalar_over_boundaries`: `10`
- `semantic_depth_boundary`: `4`
- `total_cases`: `1952`

### mutations

- `v01_delete`: `256`
- `v01_flip`: `256`
- `v01_insert`: `256`
- `v01_truncate`: `256`
- `v02_delete`: `256`
- `v02_flip`: `256`
- `v02_insert`: `256`
- `v02_truncate`: `256`
- `total_cases`: `2048`

### replay

- `copy_isolation`: `2`
- `dialogue_corpus_digest`: `1`
- `exact_snapshot_oracles`: `2`
- `full_ledger_replay_rejections`: `26`
- `positive_ledger_appends`: `52`
- `prefix_replay_rejections`: `26`
- `public_negative_dialogue_fixtures`: `20`
- `rejection_atomicity`: `6`
- `total_cases`: `135`

## Exact campaign digests

### roundtrip

- `generated_v01_frame_sequence_sha256`: `f660d83cf2fd66bac5ee7eac71ecd512862dab8498199dae17ff44821ce94751`
- `generated_v02_frame_sequence_sha256`: `4e5259265010125c8b3a3e804e87db9f9c21a79b1223194046f4ca93d839124c`
- `grammar_capsule_sha256`: `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`
- `grammar_positive_wire_sha256`: `b84cd6ac927d4098651397141a9759103b3dcd3142e37aefcdfb07b1738839d1`
- `public_corpus_sha256`: `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`
- `public_v01_frame_sequence_sha256`: `d53549664c6a1f951ada342f146a97939b950a9fdeb3d028dc0010103754bf1f`
- `public_v02_frame_sequence_sha256`: `aeca229ffbd7cb6387cd5e98df168da3f98cd1c71397ba72d94d33050118f81b`
- `v02_profile_capsule_sha256`: `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6`

### boundaries

- `dictionary_at_limit_v01_sha256`: `709dedb15d3a9bb742e24a1c156a28bfa592d8cc7e36d0c27f7bc6ccc48961e0`
- `dictionary_over_limit_v01_sha256`: `b9b982f87098943f4881a9d49514af86a131236d11ba2cb622e17b6fca585ff1`
- `duplicate_dictionary_v01_sha256`: `173f9ac67f4d15d1d45485641c61b49909b0051bd3a99027d8e82deb39472cde`
- `duplicate_map_v01_sha256`: `40a7e880e08703cf216d1251e5da3c863174f50f53ce7953032e914b15763c95`
- `duplicate_map_v02_sha256`: `6605ba5c574dcdbd81fc3cd753aacfcdb95e11834d936cb1d3b04f68a112d3d7`
- `truncation_input_sequence_sha256`: `fe4d7ab074147eb4db302186080b297570a46cb4a1b0c6abcbbb8230300985b8`

### mutations

- `v01_mutation_sequence_sha256`: `2fc49f89d4b10694e9eb23d65e51eb0e3232f8376729d8d17e4d4091101a4113`
- `v02_mutation_sequence_sha256`: `06c40497bed408159fb398087ea3bad13bb6717c64a44f5c6b06fb23225279ed`

### replay

- `dialogue_corpus_sha256`: `sha256:af65510aeb9a7bf26b0ccb265783cc3f0082fb37f183aea3f37527e68fb7ee13`
- `ledger_sha256`: `sha256:0ae2147fa81c3822284740e41118f1bbea292aa2a060232b94e8d9b74b92ecc2`
- `snapshot_sha256`: `51b3dfb81d2a2c681dc1d66d9b96fab6e71a325502811f81cd4ec6e9e31aebca`

## Shared-code findings

The finding campaign evaluated `16` minimal deterministic probes and reproduced `0` findings. Binary failing frames were not saved; they are rebuilt in memory from public fixtures.

## Resolved regression probes

The following formerly failing probes now pass and remain in the QA suite as ordinary regressions: `DQA-001`, `DQA-002`, `DQA-003`, `DQA-004`, `DQA-005`, `DQA-006`, `DQA-007`, `DQA-008`, `DQA-009`, `DQA-010`.

These local results show that the saved implementation rejects or handles the exact prior fixtures as intended. They do not establish the absence of related defect classes.

## Source identity and stability

- Source files hashed: `37`
- Source snapshot digest: `b3f3bba0c3276791cc40436595fddbffcdf627764cc57860c8d2f9b0241c2454`
- Git revision: `7f8da7473a2581ea86ab2149f6bdb17de511ff02`
- Grammar Capsule SHA-256: `588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27`
- Capsule-pinned reference codec SHA-256: `3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf`
- Saved reference codec SHA-256: `3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf`
- Saved v0.2 wire codec SHA-256: `166b1090b536bfff942667d43be583b2345eeb14b9da5d1535b7a16bb6bab2e7`
- Saved dialogue ledger SHA-256: `206135d02168076d0afce09e74c8c1c96c73f03f8dcc5451aaebd0ada545ff65`
- Pre-run and post-run source snapshots were byte-identical.

The Capsule pin matches the saved reference codec. DQA-004 is retained as an ordinary resolved regression test.

## Determinism and resource controls

- Property seed: `0x5e4a01c0de123457`; generated messages: `128`.
- Mutation seed: `0xa11ce55dec0de202`; fixed mutations: `2048`.
- Each campaign ran in a fresh process with a 30-second wall timeout.
- Worker requests: 25 CPU seconds, 1 GiB address space, a 512 MiB sampled RSS watchdog fallback, 1 MiB output-file size, and 64 open files; qa_results.json records host-level availability exactly.
- Network connect, bind, and name-resolution audit events were denied.
- The child process inherited only a minimal non-credential environment.
- Python bytecode generation was disabled.

## Scope limitations

- Only the saved local Python implementation, public fixtures, and documented local grammar were exercised.
- No network, third-party target, credentials, external service, exploitation, or vulnerability research was used.
- Fixed mutations provide reproducible coverage but are not exhaustive fuzzing or a proof of absence of defects.
- Checksum mutation tests assess accidental-corruption rejection, not cryptographic authentication.
- Duplicate binary map fields and duplicate CLI JSON members were tested at their respective parser boundaries; the dialogue ledger accepts already-parsed mappings and cannot observe duplicate JSON members.
- Dialogue thread states are asserted using the public conversation/thread composite-key snapshot shape. Alternate snapshot consumers were not tested.
- The exact documented 100,000-recipient boundary and one-over rejection were checked. Unbounded allocation behavior beyond documented limits was not stress-tested.
- Recursive depth was checked at the exact documented boundary with bounded values. No unbounded recursion campaign was run.
- The dialogue corpus has 26 public generated messages; replay consistency outside that fixed corpus remains unproven.
- No unseen partner, comparative fallback, cost benchmark, or public side effect was exercised, so this report cannot establish project support or conformance.

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 python3 decoder_qa/run_decoder_qa.py --allow-known-findings
```

See `known_failures.json` for minimal recipes, `qa_results.json` for full observations, and `SHA256SUMS` for artifact and input identity.
