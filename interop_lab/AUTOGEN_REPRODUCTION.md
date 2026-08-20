# Microsoft AutoGen Minimal Reproduction

Status: offline-first external reproduction kit; structural validation is not adoption or efficiency evidence

This kit lets an existing Microsoft AutoGen AgentChat user freeze and inspect a matched raw/JSON/Urusilla experiment before connecting any model. The offline path uses only the repository and the Python standard library. It does not install or import AutoGen, contact a provider, open a network connection, or authorize spending or effects.

AutoGen is currently in maintenance mode, and Microsoft recommends Microsoft Agent Framework for new projects. This adapter remains useful for existing AutoGen users and records that lifecycle status in every plan. It follows the current AgentChat `AssistantAgent.run` interface documented by the AutoGen project:

- [AutoGen repository and maintenance notice](https://github.com/microsoft/autogen)
- [AgentChat AssistantAgent documentation](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html)
- [AgentChat model-client documentation](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/models.html)

## 1. Run the offline preflight

From a clean clone at the repository root, without installing AutoGen:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.autogen_reproduction \
  init autogen-plan.json --experiment-id my-autogen-repro

PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.autogen_reproduction \
  validate autogen-plan.json --json

PYTHONDONTWRITEBYTECODE=1 python3 -m interop_lab.autogen_reproduction \
  preflight autogen-plan.json --output autogen-preflight.json
```

`init` refuses to overwrite an existing file. The preflight receipt is byte-bound to the full plan. It verifies:

- the exact frozen Capsule SHA-256;
- the Capsule's declarative JSON and unsigned status;
- canonical UrusillaIR normalization and exact UrusillaWire round trip;
- one identical public semantic task across raw, structured-JSON, and Urusilla arms;
- the exact Capsule teaching cost inside the Urusilla model input;
- fresh agent and fresh model-client requirements for every arm;
- the no-tools, no-memory, one-turn, no-persistence, no-permission-expansion, no-protocol-spending, and no-effects boundary; and
- a matched ledger whose unavailable categories remain `null`, never zero.

A successful receipt reports `autogen_imported: false`, `provider_calls: 0`, `network_calls: 0`, and `external_effects: 0`. It proves only that the local experiment structure is internally consistent.

## 2. Inspect the frozen task

The synthetic task contains two plans. Both satisfy the hard budget and network constraints, but no utility tie-breaker exists. A correct response must preserve that ambiguity:

```json
{
  "feasible_plans": ["plan-a", "plan-b"],
  "reason": "<public concise reason>",
  "selected_plan": null,
  "would_execute": false
}
```

The three arms use the same task semantics and response contract:

1. `raw` uses concise natural language and no discovery payload.
2. `structured-json` charges its explicit format description and JSON carrier.
3. `urusilla` charges the complete frozen Capsule text plus canonical UrusillaIR.

This is deliberately a cold first-contact test. It does not assume prior installation, hidden teaching, cached state, or a free Capsule. The Urusilla arm may regress substantially; that is valid negative evidence.

## 3. Connect an operator-owned model only after review

The model path is a Python API rather than a CLI command so the experiment cannot infer a provider, credential, endpoint, or spending authority. The caller must supply one fresh AutoGen model client per arm and set the explicit approval flag.

The example below uses AutoGen's OpenAI extension only as an illustration. It may make billable network calls after `operator_approved_model_calls=True`; the offline commands above do not.

```python
import asyncio
import json
from pathlib import Path

from autogen_ext.models.openai import OpenAIChatCompletionClient

from interop_lab.autogen_reproduction import (
    offline_preflight,
    run_autogen_trial,
    validate_plan,
)
from interop_lab.interop_lab import load_record


async def main() -> None:
    plan = load_record(Path("autogen-plan.json"))
    validate_plan(plan)
    receipt = offline_preflight(plan)

    def fresh_client(_arm_id: str) -> OpenAIChatCompletionClient:
        # Keep the same pinned model and settings for every arm.
        # Each call returns a distinct client so no conversational state carries over.
        return OpenAIChatCompletionClient(model="<PINNED-MODEL-ID>")

    result = await run_autogen_trial(
        plan,
        receipt,
        fresh_client,
        operator_approved_model_calls=True,
        include_public_response=False,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


asyncio.run(main())
```

The adapter constructs one fresh `AssistantAgent` per arm with `tools=[]`, `memory=None`, `reflect_on_tool_use=False`, and one bounded `run` call. It closes every model client, including failure paths. It never accepts one shared client across arms.

## 4. Interpret the result conservatively

The adapter deterministically scores the public JSON answer. Malformed output, an invented tie-breaker, a missing feasible plan, an execution claim, or any extra output field is preserved as task failure rather than repaired.

AutoGen's `models_usage` prompt and completion counts are recorded when present. They support a clearly labeled model-usage-only comparison and a post-decode API-input observation. They are not silently promoted to a complete task-token ledger: reported reasoning categories, evaluator tokens, conversion work, retries, fallback, and any provider-specific accounting that is not exposed remain unknown. Therefore `complete_total_task_tokens` and `complete_total_task_token_saving_percent` stay `null` in the generated result.

Before submitting evidence to the Interop Lab, preserve the raw, JSON, and Urusilla arms and add every applicable category from the main ledger:

```text
task_input, system_role, agent_input_history, agent_output_visible,
final_answer, format_induction, encode_decode_model, negotiation_profile,
repair_retry, tool_request, tool_result, safety_filter,
hidden_reasoning_billed, unclassified
```

Also disclose the exact AutoGen, model-client, model, tokenizer, provider, and settings versions; operator relationships; failed attempts; output redaction; receipts; and whether the run was premeasurement-sealed. Attach the generated result as a staging artifact, then create a complete `interop_lab.py` propagation record. Do not relabel one operator's three-arm run as independent cross-play, organic adoption, or general token saving.

## Fail-closed behavior

The guarded model path stops before any model call when:

- the plan or embedded Capsule changed;
- the preflight receipt is absent or stale;
- the operator approval flag is not exactly `True`;
- `autogen-agentchat` is unavailable and no compatible class is explicitly injected for a local test;
- the client factory returns `None` or reuses a client across arms;
- AutoGen returns no public final text or invalid token counts; or
- any frozen tool, memory, safety, task, carrier, ledger, or claim-boundary field changed.

Provider configuration and costs remain entirely outside Urusilla. The protocol never grants spending authority.
