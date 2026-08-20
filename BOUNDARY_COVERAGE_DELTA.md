# Receiver boundary coverage delta

## Result

Seventeen new tests add adversarial coverage for the A2A adapter and v0.2 wire
decoder without modifying either implementation.  The focused suite increased
combined statement-plus-branch coverage from **71.43% to 82.07%** across the
two complete modules.  More importantly, branch coverage in the receiver-side
core increased from **73.24% to 96.48%** for the adapter and from **73.13% to
87.31%** for the wire decoder.

The new tests passed **17/17**.  The focused existing-plus-new suite passed
**51/51**, and the fully provisioned Python 3.12 repository suite passed
**279/279** in 67.620 seconds with no skips or failures reported by unittest.

Coverage is evidence that the listed rejection paths executed; it is not proof
of protocol security, memory safety, interoperability, or complete attack
coverage.

## Method

The baseline ran the 34 existing adapter and wire tests under Coverage.py with
branch measurement enabled.  The after measurement ran those same tests plus
the new boundary module in the same process, interpreter, working directory,
and source filter.  No source, frozen report, exclusion rule, or coverage
configuration changed between measurements.

Two views are retained:

- **Complete module** is the ordinary Coverage.py result, including benchmark,
  report-rendering, and command-line functions that were intentionally not the
  target of this workstream.
- **Receiver core** counts executable statements and branch arcs whose origin
  is at or before line 514 in the adapter and line 878 in the wire module.  The
  cutoffs exclude file-oriented command-line code in the adapter and benchmark,
  report, and command-line code in the wire module.  They do not exclude any
  adapter validation or wire encode/decode boundary.

Environment:

- Python 3.12.14
- Coverage.py 7.15.4 with C extension
- Branch measurement enabled
- Offline execution; no network or paid service calls

## Complete-module delta

| Module | Metric | Before | After | Delta |
|---|---|---:|---:|---:|
| A2A adapter | Statements | 211/290 (72.76%) | 244/290 (84.14%) | +11.38 pp |
| A2A adapter | Branches | 105/150 (70.00%) | 138/150 (92.00%) | +22.00 pp |
| A2A adapter | Combined | 71.82% | 86.82% | +15.00 pp |
| v0.2 wire | Statements | 487/660 (73.79%) | 532/660 (80.61%) | +6.82 pp |
| v0.2 wire | Branches | 197/300 (65.67%) | 235/300 (78.33%) | +12.67 pp |
| v0.2 wire | Combined | 71.25% | 79.90% | +8.65 pp |
| Both modules | Statements | 698/950 (73.47%) | 776/950 (81.68%) | +8.21 pp |
| Both modules | Branches | 302/450 (67.11%) | 373/450 (82.89%) | +15.78 pp |
| Both modules | Combined | 71.43% | 82.07% | +10.64 pp |

## Receiver-core delta

| Module | Metric | Before | After | Delta |
|---|---|---:|---:|---:|
| A2A adapter core | Statements | 207/247 (83.81%) | 240/247 (97.17%) | +13.36 pp |
| A2A adapter core | Branches | 104/142 (73.24%) | 137/142 (96.48%) | +23.24 pp |
| v0.2 wire core | Statements | 479/561 (85.38%) | 524/561 (93.40%) | +8.02 pp |
| v0.2 wire core | Branches | 196/268 (73.13%) | 234/268 (87.31%) | +14.18 pp |

## High-value boundaries added

The tests were selected from previously unexecuted receiver rejection branches,
not from easy report or command-line lines.

### A2A adapter

- Extension activation rejects duplicate URIs, empty elements, wrong container
  types, missing URI schemes, and CRLF header injection.
- Raw parts reject ambiguous content fields, wrong media types, malformed
  metadata, unsupported wire profiles, non-text Base64 values, and missing or
  mistyped capsule pins.
- Strict Base64 preflight rejects invalid limits, length, and alphabet before
  decoding.  A mocked post-preflight length discrepancy exercises the defensive
  time-of-check/time-of-use size guard.
- Underlying wire failures are normalized into an adapter error while retaining
  the original decoder exception as the cause.
- Wrapper provenance rejects invalid authenticated principals, ambiguous task
  references, duplicate task references, missing extension provenance,
  multiple semantic parts, empty message identifiers, and context/task pin
  disagreement.

### v0.2 wire decoder

- Checksum-valid adversarial frames reach recipient-count, reserved-bit,
  unknown-act, confidence-range, expected-bitset, semantic-validation, trailing
  payload, and non-map metadata rejection paths.
- Canonical varint checks reject zero profile IDs, overlong encodings, overflow,
  encodings longer than ten bytes, and oversized declared payloads.
- String decoding rejects out-of-range direct, indirect, and prefix references,
  invalid UTF-8, oversized declared text, and non-string tags.
- Value decoding rejects negative zero, NaN, duplicate map keys, oversized byte
  strings, oversized list/map counts, unknown shape and value tags, and trees
  beyond the recursion limit.
- Checksum-valid profile capsules reject unsupported formats, invalid profile
  IDs, oversized tables, duplicate dictionary entries, invalid shape sizes,
  out-of-range key references, non-canonical key order, and trailing payload.
- Gzip decoding rejects wrong input types, oversized compressed input, invalid
  streams, truncation, and concatenated/trailing members.

Private reader and encoding helpers are used only to locate canonical field
boundaries and rebuild checksums for malicious fixtures.  Every behavioral
assertion enters through a public adapter, frame decoder, capsule decoder, or
gzip decoder API.

## Remaining gaps

The receiver core is intentionally not forced to 100%.

- Most remaining wire lines are encoder-only validation, static-profile
  constructor limits that would require very large allocations, or defensive
  branches whose preconditions are already ruled out by an earlier invariant.
- Two strict Base64 padding branches appear structurally dominated by the
  preceding alphabet check and suffix-derived padding width.  Tests were not
  coupled to internal state merely to mark them executed.
- Cryptographic fingerprint-collision handling was not mocked.  Replacing the
  digest primitive would inflate coverage without testing the real security
  assumption.
- Allocation-failure behavior, concurrent registry mutation, fuzzing, and
  external A2A interoperability remain outside this bounded workstream.

## Generated-Protobuf temporary-source warning

The plain 279-test repository run completed without a warning.  A separate
unfiltered coverage reproduction of the strong-codec tests emitted the expected
Coverage.py warning:

> Couldn't parse a generated `*_pb2.py` temporary file: No source for code.

The Protobuf fixture compiles Python source into a temporary directory and
retains the imported module only for the test process.  The temporary directory
is removed when that process exits, before the later coverage-report process can
read the generated source.  This is a coverage source-lifetime warning, not a
test failure or a decoder failure.  The before/after numbers above use an
explicit two-module source filter, so the generated file is outside both
measurements and the warning does not affect the delta.  The warning was
retained and disclosed rather than treated as evidence of missing product
coverage.

## Reproduction

From the repository root, with the fully provisioned Python 3.12 environment:

```bash
COVERAGE_FILE=/tmp/boundary-before python -m coverage run --branch --source=urusilla_a2a_adapter,urusilla_wire_v02 -m unittest test_urusilla_a2a_adapter test_urusilla_wire_v02
COVERAGE_FILE=/tmp/boundary-before python -m coverage report -m

COVERAGE_FILE=/tmp/boundary-after python -m coverage run --branch --source=urusilla_a2a_adapter,urusilla_wire_v02 -m unittest test_urusilla_a2a_adapter test_urusilla_wire_v02 test_urusilla_boundary_hardening
COVERAGE_FILE=/tmp/boundary-after python -m coverage report -m

python -m unittest discover -v
```

The coverage data files belong in a temporary directory and are not repository
artifacts.

## Artifact identity

- A2A adapter source SHA-256: `25f3b9f697650f71be23588265436b89a52e25c812e8364a766eb78ccc211135`
- v0.2 wire source SHA-256: `c53b07b8fff754fc7342680c8c6cf7e73ae0a52063a172181f94ac56068df27c`
- New boundary tests SHA-256: `30f7b4780224ddab88efe6f00565801568319e5d6e668c8b64964a4208c6f21f`
