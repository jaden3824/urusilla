# Energy sensitivity analysis

Status: normalized model, not a joule measurement  
Date: 2026-08-20

## Result

The current codec results make material energy savings plausible in communication-heavy systems, but they do not prove an energy saving. Token savings are not a direct energy meter. Conversion, validation, repair, cache misses, codebook distribution, and model training may consume or erase the gain.

The model normalizes baseline energy per safely completed task to 1.0:

```text
gross saving = communication energy share
             * (token-sensitive share * token reduction
                + wire-sensitive share * wire reduction)

new energy per safely completed task =
  (1 - gross saving + conversion/training/repair overhead)
  / relative safe-task success
```

The current illustrative inputs use two measured serialization results:

- 45.8% arithmetic-mean warm token reduction for Base64 UrusillaWire v0.2 versus sorted minified UrusillaIR JSON across four tokenizers; and
- 18.2% aggregate compressed byte reduction across the measured complete HTTP+JSON and JSON-RPC A2A requests versus structured DataPart JSON.

These are not natural-language dialogue reductions and are not total model-token reductions. The cases below are sensitivity examples, not forecasts.

| Case | Communication share | Token-/wire-sensitive share | Added overhead | Relative safe success | Net normalized energy saving |
|---|---:|---:|---:|---:|---:|
| overhead-dominates | 10% | 20% / 10% | 3.0% | 100% | -1.90% |
| communication-moderate | 30% | 70% / 10% | 2.5% | 100% | +7.66% |
| communication-heavy | 70% | 80% / 10% | 4.0% | 100% | +22.92% |
| repair-regression | 30% | 70% / 10% | 2.5% | 90% | -2.60% |

The table demonstrates the release rule: a shorter serialization is valuable only if the affected work is a meaningful share of the complete system and semantic failures do not create repair or task-success regressions.

## Measurement required for a real claim

A controlled paired experiment must measure the same agent models, tasks, hardware, batching, cache state, and safety policy under Urusilla and the strongest baseline. Report:

1. wall-plug or device energy for GPU, CPU, memory, and networking;
2. complete input, output, cached, translation, repair, and evaluator tokens;
3. end-to-end latency, utilization, and peak memory;
4. cold Capsule/codebook distribution and amortized training energy;
5. safely completed tasks, not merely emitted messages; and
6. uncertainty intervals over repeated randomized runs.

Energy claims must be stated per safely completed task and must include a negative result when conversion or repair overhead dominates.

## Reproduction

```bash
PYTHONPATH=. python3 urusilla_energy_sensitivity.py --json
PYTHONPATH=. python3 -m unittest test_urusilla_energy_sensitivity.py -v
```
