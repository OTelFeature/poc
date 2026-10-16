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
- Presets and `STAGE.md` exist (OTelFeature/poc#26). Presets are cumulative and applied in the order of UC-008 BR-006.
- Fallback videos recorded (OTelFeature/poc#32); OTel Demo footage in the slides (OTelFeature/poc#33).

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Go offline | Disconnect networking | airplane mode | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 2 | Start | Start the stack and reset | `make start`, `make demo-reset` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 3 | Verify healthy | End-to-end traces appear; client spans show the stub as `server.address` | - | - |
| 4 | Demo 1 | Apply tracing-off preset, then baseline | `01-otel-off` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |
| 5 | Demo 2 | Apply quiet-noise preset | `02-quiet-noise` | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 6 | Demo 3 | Apply semconv-rules preset, then weather-boost, then incident | `03-semconv-rules`, `03a-weather-boost`, `03b-incident` | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 7 | Reset | Restore baseline | `make demo-reset` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |

## Validation

1. **Offline (OTelFeature/poc#24):** no step needs network access. [e2e, partly: `test_tc006_offline`; the suite runs against the API stubs with the external API hosts unreachable, but image pulls and builds still use the network]
2. **Presets valid (OTelFeature/poc#26):** each preset validates against the flagd schema in CI.
3. **Flip latency:** every flip is visible in Aspire within 2 s. [e2e, partly: every flip in the suite waits on the flag-propagation barrier; CI allows the poll timeout (default 5 s) instead of 2 s, and reads the collector, not Aspire]
4. **Runbook:** `STAGE.md` maps every script beat to one command.
5. **Baseline healthy (OTelFeature/poc#35):** both services export server, client and database spans; every trace tree is connected; the resource carries `service.name` and `deployment.environment.name`. [e2e: `test_baseline`]
6. **Presets apply (OTelFeature/poc#35):** every preset the suite uses is applied the way `make flag PRESET=…` applies it, so a preset that does not parse or does not take effect fails the suite. [e2e: all tests]
7. **Flip is really applied (OTelFeature/poc#26, OTelFeature/poc#35):** every flag-file write leaves a strictly newer mtime (flagd ignores a rewrite with an unchanged mtime), and the flip counts only after flagd serves the new value over OFREP (port 8016); spans are counted after that barrier, never before. Three flips within one second end in the last preset's state. [e2e: all tests, through the flag-flip helper]
8. **Stage from git refs (FR-026, UC-008 A3, BR-008):** `make start-staging EXT_REF=<ref>` builds both extensions from the ref and starts; `make start` prints `git <ref>` for both images; `make build` followed by `make start` prints the pinned versions again. [manual; the e2e suite builds the same Dockerfile stages from git refs on every run]

## Stage progression in CI

The e2e suite runs this whole sequence as one ordered test, `test_stage_progression` (OTelFeature/poc#35): presets 00 → 01 → 02 → 03 → 03a → 03b in order, **no resets**, asserting the expected spans and sampling after each flip. A preset that only works after a reset fails CI.

## Postconditions

- Stack at baseline.

## Automation

- **Tests:** `test_baseline` (OTelFeature/poc#35, phase 1) and `test_tc006_offline`. The e2e override points both services at the API stubs (OTelFeature/poc#24), so every test in the suite also runs offline from the external APIs.
- **How:** `docker compose -f compose.yaml -f compose.e2e.yaml up -d --wait`. The override adds the collector `file` exporter, turns the load generator off, removes the Datadog exporter and Aspire, and enables request-header capture for the `x-e2e-step` marker.
- **Flag flips:** the flag-flip helper writes the preset to a temp file, gives it an mtime strictly newer than the current file's, renames it into place, and polls flagd over OFREP (port 8016) until a per-write revision flag shows the new value. Only then does the test send traffic and count spans ([flag file reload](../entity_model.md#flag-file-reload)).
- **Matrix:** runs in both Java enforcement modes (`processor`, `sampler`).
- **Not automated:** step 1 (airplane mode on the stage laptop), item 4 (runbook) and the fallback videos stay rehearsal checks (NFR-012).
