# Test Case: Full stage run, offline

## Overview

- **ID:** TC-006
- **Goal:** The speaker runs all demo beats with the network disconnected, one command per beat, and ends at baseline.
- **Priority:** Critical
- **Status:** Draft

## Roles

- Speaker: runs every command from `STAGE.md`.

## Preconditions

- `make prepare-offline` was run while online (OTelFeature/poc#24).
- Presets and `STAGE.md` exist (OTelFeature/poc#26).
- Fallback videos recorded (OTelFeature/poc#32); OTel Demo footage in the slides (OTelFeature/poc#33).

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Go offline | Disconnect networking | airplane mode | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 2 | Start | Start the stack and reset | `make start`, `make demo-reset` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 3 | Verify healthy | End-to-end traces appear; client spans show the stub as `server.address` | - | - |
| 4 | Demo 1 | Apply tracing-off preset, then baseline | `01-otel-off` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |
| 5 | Demo 2 | Apply quiet-noise preset | `02-quiet-noise` | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 6 | Demo 3 | Apply semconv-rules preset, then incident | `03-semconv-rules`, `03b-incident` | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 7 | Reset | Restore baseline | `make demo-reset` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |

## Validation

1. **Offline (OTelFeature/poc#24):** no step needs network access.
2. **Presets valid (OTelFeature/poc#26):** each preset validates against the flagd schema in CI.
3. **Flip latency:** every flip is visible in Aspire within 2 s.
4. **Runbook:** `STAGE.md` maps every script beat to one command.

## Postconditions

- Stack at baseline.
