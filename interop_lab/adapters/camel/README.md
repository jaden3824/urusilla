# CAMEL-AI offline-first reproduction adapter

This adapter lets a CAMEL operator prepare, inspect, and map a matched
`raw / structured JSON / Urusilla` reproduction without importing CAMEL or
contacting a model. The offline CLI is dependency-free beyond this repository.
It never exposes a provider-call command.

The optional live path is deliberately narrow:

- `camel-ai==0.2.90`;
- `mcp>=1.3,<2` (CAMEL 0.2.90 imports `FastMCP` from the MCP 1.x layout);
- Python `>=3.10,<3.15`;
- direct `ChatAgent.step` sequencing, not `RolePlaying` or `Workforce`;
- one fresh model and one fresh `ChatAgent` per arm;
- `tools=[]`, `external_tools=[]`, no memory, and no external effects;
- `max_iteration=1`, `summarize_threshold=None`, provider retries `1`, and
  streaming disabled; and
- an explicit `allow_external_model_calls=True` flag plus an exact three-call
  cap before CAMEL is imported or a model factory is invoked.

The protocol itself never grants spending authority. A live operator must
already have separate provider authorization and remains responsible for cost,
credentials, terms, and network policy.

## Offline workflow

Run from the repository root:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.adapters.camel init camel-plan.json
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.adapters.camel validate-plan camel-plan.json --json
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.adapters.camel preflight camel-plan.json
```

These commands import neither CAMEL nor MCP and make zero provider, network, or
external-effect calls. The plan charges the entire declarative Capsule to the
Urusilla arm and binds all three arms to the same task and public response
contract.

After a separately authorized operator collects a capture with
`run_camel_trial`, validate and map it offline:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.adapters.camel validate-capture camel-plan.json camel-capture.json --json
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.adapters.camel map camel-plan.json camel-capture.json interop-record.json
PYTHONDONTWRITEBYTECODE=1 python3 interop_lab/interop_lab.py validate interop-record.json --json
```

The map command refuses to overwrite a file and calls the existing
`interop_lab.validate_record` before writing. The source capture preserves all
three arms. The public Interop Lab hop has one baseline and one candidate, so
it maps `raw` to baseline and `urusilla` to candidate while retaining the JSON
arm in the byte-bound source capture.

## Guarded CAMEL-native connection

`run_camel_trial` is an async library API, not a CLI command. Its
`model_factory` receives `(arm_id, on_request_usage, frozen_policy)`. A caller
must create a fresh model with `ModelFactory.create(...)`, wire the supplied
`on_request_usage` callback, and enforce the supplied retry and stream policy.
The adapter then creates a fresh direct `ChatAgent` and calls `agent.step(...)`
once for each arm.

Minimal shape (provider details intentionally omitted):

```python
capture = await run_camel_trial(
    plan,
    offline_preflight(plan),
    operator_model_factory,
    allow_external_model_calls=True,
    call_cap=3,
    operator={
        "recorder": "your public recorder name",
        "operator_id": "your-stable-id",
        "evidence_tier": "self-reported",
        "premeasurement_sealed": True,
        "artifacts_public": False,
        "receiver_relationship_to_project": "independent",
        "provider": "provider-name",
        "model": "exact-model-name",
        "model_version": "dated-or-provider-version",
    },
)
```

Do not put an API key, private prompt, chain of thought, or personal data in the
plan, capture, output, or operator metadata.

## Usage accounting fails closed

CAMEL 0.2.90 can expose usage through the `on_request_usage` callback and
`response.info["usage"]`. The adapter accepts either source, cross-checks both
when both appear, and retains provider prompt, completion, and total tokens
only when they are nonnegative, total is positive, and the arithmetic
reconciles. Multiple callback events or conflicting sources are not silently
summed.

If raw or Urusilla usage is missing, invalid, conflicting, or zero, the mapped
Interop ledger is entirely `not-measured`: both sides and every saving field
remain `null`. Unknown is never converted into zero. Provider-only usage is
mapped conservatively with prompt tokens under `unclassified` and completion
tokens under `agent_output_visible`; it is not presented as a complete study
cost, and the project-wide broad post-decode result remains 0%.

## Tests

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s interop_lab/adapters/camel/tests -v
```

The suite uses injected fake `ChatAgent` and model objects only. It performs no
provider or network call. When `camel-ai` is absent, the optional import check
is skipped while every offline and static-mapping test still runs.
