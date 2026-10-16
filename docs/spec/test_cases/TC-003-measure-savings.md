# Test Case: Measure Demo 2 savings in both Java modes

## Overview

- **ID:** TC-003
- **Goal:** The operator runs the measurement harness and gets a reproducible per-service table of CPU, memory, spans/s and export bytes/s for baseline, processor mode and sampler mode, plus the per-span decision cost.
- **Priority:** High
- **Status:** Draft

## Roles

- Operator: runs the harness, records the numbers.

## Preconditions

- Released extension versions with OTelFeature/otelfeature-java-extension#21 pinned in `poc`.
- Offline stage mode (OTelFeature/poc#24) active.
- Quiet-noise preset (OTelFeature/poc#26) exists.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Run harness | Run the benchmark command | `make bench`, default duration | [UC-003](../use_cases/UC-003-measure-savings.md) |
| 2 | Verify table | One table per service with six runs (baseline, targeted no-op and Demo 2, each in processor and sampler mode), the decision cost per mode (UC-003 BR-006) and no load warning | - | - |
| 3 | Repeat | Run the harness again | same | [UC-003](../use_cases/UC-003-measure-savings.md) |
| 4 | Verify reproducibility | Every metric within ±10% of the first run | - | - |

## Validation

1. **Numbers recorded (OTelFeature/poc#27):** the script bracket values are posted in the issue.
2. **D3 recommendation (OTelFeature/poc#27):** sampler vs processor recommendation posted with numbers and the effort notes from OTelFeature/otelfeature-java-extension#21.
3. **Live view:** a view usable on stage shows the drop within seconds of the flip.
4. **No dependency on OTelFeature/poc#23:** the harness runs on the stack's normal traffic.

## Postconditions

- Stack back at baseline preset, Java in default mode.

## Automation

Not part of the end-to-end suite (OTelFeature/poc#35): this is a measurement, not a pass/fail check.

- **Harness:** `make bench` runs its own compose project (`otelfeature-bench`) on the pinned releases, with the load generator on and the collector writing spans to a file. Per run it recreates `geocode`, `weather` (with the run's `OTELFEATURE_ENFORCEMENT`) and the load generator, applies the preset (the e2e flag helper), warms up for `BENCH_WARMUP` seconds and measures for `BENCH_SECONDS`, then prints and saves the tables and raw results (`bench/.results/`).
- **Live view (item 3):** the dashboard's span-metrics chart per service; no extra component.
