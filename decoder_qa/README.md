# Decoder QA

This directory contains bounded, deterministic quality-assurance checks for the
saved local parser implementation. It does not modify shared implementation
files and does not make a conformance, security, adoption, or interoperability
claim.

## Run

```sh
PYTHONDONTWRITEBYTECODE=1 python3 decoder_qa/run_decoder_qa.py --allow-known-findings
```

The runner launches each campaign in a fresh local process with a 30-second
wall timeout, a 25-second CPU limit, a requested 1 GiB address-space limit, a
512 MiB sampled RSS watchdog fallback, a 1 MiB file size limit, and a
64-file-descriptor limit where the host supports them. Socket
connect, bind, and name-resolution audit events are denied. The child
environment omits inherited credential variables.

The fixed property seed is `0x5e4a01c0de123457`. The fixed mutation seed is
`0xa11ce55dec0de202`. Failing binary frames are generated only in memory; the
directory preserves recipes and exact runtime digests instead of large binary
fixtures.

## Outputs

- `qa_results.json`: machine-readable source snapshot, exact campaign counts,
  digests, limits, timings, and observations.
- `QA_REPORT.md`: English QA report and scope limitations.
- `known_failures.json`: minimal deterministic reproduction recipes.
- `SHA256SUMS`: digests of the QA artifacts and all inspected local inputs.

The default runner exit status is nonzero when known shared-code findings are
present. `--allow-known-findings` permits an evidence run to finish successfully
while retaining those findings. Repaired cases remain ordinary regression tests;
only an unresolved case may remain an expected failure. An unexpected success
therefore forces the manifest to be reviewed.
