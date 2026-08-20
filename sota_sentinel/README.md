# SOTA Sentinel

This directory is a claim-safety audit of reported AI-agent communication-efficiency results available from primary sources and official repositories as of 2026-08-20. It does **not** claim that this project is state of the art, a world record, or conformant with any external standard.

## Contents

- `REPORT.md` — human-readable evidence report, comparability analysis, and the experiment required before any world-record statement.
- `registry.json` — machine-readable evidence records, ledger boundaries, artifact revisions, licenses, and reproduction classifications.
- `registry.schema.json` — JSON Schema for the registry shape.
- `check_registry.py` — standard-library validator that fails closed on unsafe project claims, missing evidence fields, invalid comparison lanes, and malformed revision pins.
- `test_check_registry.py` — positive and negative checker tests.
- `DIGESTS.sha256` — release-file SHA-256 manifest. It deliberately excludes itself.

## Validate

Run from this directory or the repository root:

```sh
python3 sota_sentinel/check_registry.py
python3 -m unittest discover -s sota_sentinel -p 'test_*.py'
python3 sota_sentinel/check_registry.py --verify-digests
```

The validator is offline and makes no model or network calls. Source links were separately retrieved or resolved during the cutoff audit; every registry source records the check date and status.

## Interpretation

Headline percentages and multipliers are retained in the ledger used by each source. They are intentionally split into generated-message tokens, provider prompt tokens, provider completion tokens, total runtime model tokens, decoded system outputs, static tokenizer counts, TTFT/prefill, message-generation latency, end-to-end inference latency, workflow latency, monetary inference cost, latent-payload bytes, and accuracy-cost frontiers. Values in different lanes are not ranked against one another.

`literal` reproduction means rerunning the authors' exact released implementation, model/data revisions, and metric boundary. `clean_room` reproduction means an independently implemented method can be evaluated from the public description without copying code that lacks a license. `conditional` identifies the missing pins, artifacts, hardware, or legal permission that must be supplied first.

No paid model calls were used to create or validate this audit.
