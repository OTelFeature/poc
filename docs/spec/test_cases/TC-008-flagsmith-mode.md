# Test Case: Stage progression with the flags in Flagsmith

## Overview

- **ID:** TC-008
- **Goal:** The operator runs the demo presets in Flagsmith mode, one Flagsmith preset command per beat, and flagd serves exactly the preset files.
- **Priority:** Low
- **Status:** Draft

## Roles

- Operator: runs the Flagsmith preset command for each beat.

## Preconditions

- A Flagsmith environment for the demo, with real-time updates on (Flagsmith Enterprise), and its server-side key, client-side key and an Admin API key (entity model, [Flagsmith mode](../entity_model.md#flagsmith-mode)).
- The seed command has created the demo features and segments in that environment's project.
- The stack runs with `compose.flagsmith.yaml` (UC-008 A4).

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Start | Start the stack in Flagsmith mode; the proxy loads the environment and flagd syncs from it | `docker compose -f compose.yaml -f compose.flagsmith.yaml up -d` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 2 | Reset | Apply the baseline with the Flagsmith preset command | `00-baseline` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 3 | Demo 1 | Apply tracing off, then baseline | `01-otel-off` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |
| 4 | Demo 2 | Apply quiet noise | `02-quiet-noise` | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 5 | Demo 3 | Apply semconv rules, then weather boost, then incident, then weather boost again | `03-semconv-rules`, `03a-weather-boost`, `03b-incident`, `03a-weather-boost` | [UC-004](../use_cases/UC-004-target-trace-sampling.md), [UC-005](../use_cases/UC-005-raise-sampling-on-errors.md) |
| 6 | Bad input | Add an override the translation does not support | an override whose value is no variant of its flag | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |

## Validation

1. **Same flag sets:** for every preset, the Flagsmith state its preset command produces translates to that preset's file: flags, variants, default variants, targeting and `metadata.preset` (UC-008 BR-009). Checked without Flagsmith, by applying the command's CLI calls to a model of the environment (`src/flagsmith-proxy/test_translate.py`, `make test`).
2. **Translation rules:** each supported operator and rule type maps as the entity model says; an unsupported operator, a value that is not a variant, and a disabled override of a non-boolean flag are rejected (`test_translate.py`).
3. **Pushed flip:** through the real Edge Proxy and flagd against a stub of Flagsmith Cloud, each preset of steps 2 to 5 is served by flagd's OFREP with its `metadata.preset` within 2 s of the real-time event, and the proxy's flag set equals the preset file (UC-008 BR-010, BR-011; `test_pushed_progression`, `make flagsmith-test`).
4. **Fallback poll:** with the real-time stream switched off, a change still reaches flagd after the proxy's next poll (`test_poll_fallback`, `make flagsmith-test`).
5. **Rejected input keeps the last flag set:** after step 6, flagd still serves the previous preset (UC-008 A5; `test_rejected_environment`, `make flagsmith-test`).
6. **Against Flagsmith Cloud:** steps 1 to 5 with the real CLI and Cloud; each preset command reports its preset served within its timeout. Rehearsal check (OQ-16).

## Postconditions

- The Flagsmith environment is at `00-baseline`.

## Automation

- **Tests:** items 1 and 2 run in `make test` (stack-free, the toolchain image). Items 3 to 5 run in `make flagsmith-test`: a compose project with a stub of Flagsmith Cloud (environment document and real-time stream), the Flagsmith proxy image and flagd, and the toolchain image running pytest.
- **Not automated:** item 6 needs Flagsmith Cloud credentials; the stub serves the environment documents the same model of the environment builds, so the CLI's real writes are checked only in rehearsal.
- **Not in the e2e suite:** spans are not counted in Flagsmith mode. Since flagd serves the same flag sets (item 1), the span behaviour is TC-006's.
