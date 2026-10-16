# Test Case: Tracing kill switch round trip

## Overview

- **ID:** TC-001
- **Goal:** The operator turns tracing off with `otelEnabled`, confirms zero span ingest from both services while metrics keep flowing, turns it back on and gets complete traces, all without a restart.
- **Priority:** Critical
- **Status:** Draft

## Roles

- Operator: edits the flag (on stage: applies the preset).

## Preconditions

- Stack running from `make start` with the baseline `src/flagd/flagd.json`.
- Both services on extension releases containing OTelFeature/poc#8 and OTelFeature/poc#9.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Turn tracing off | Set the boolean flag to off | `otelEnabled` → `off` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |
| 2 | Verify off | No new `geocode` or `weather` spans arrive in Aspire after 2 s; their metrics still arrive | - | - |
| 3 | Turn tracing on | Set the boolean flag to on | `otelEnabled` → `on` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |
| 4 | Verify on | New traces from both services arrive within 2 s, parent chains complete | - | - |
| 5 | Use the variant | Set the string flag to OFF | `telemetryLevel` → `off` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |
| 6 | Verify variant | Same result as step 2 | - | - |
| 7 | Reset | Restore baseline | `telemetryLevel` → `full` | [UC-001](../use_cases/UC-001-switch-tracing-off-and-on.md) |

## Validation

1. **No restart:** container start times of `geocode` and `weather` are unchanged across the test.
2. **Equivalence (OTelFeature/poc#8):** `otelEnabled=false` and `telemetryLevel=OFF` produce the same span output in both languages.
3. **Fail open (OTelFeature/poc#8, OTelFeature/poc#9):** with flagd stopped, or with an unknown `telemetryLevel` value, spans are created as with the stock SDK; the failure is logged once, not per span.
4. **Java sampler mode (OTelFeature/otelfeature-java-extension#21):** with `OTELFEATURE_ENFORCEMENT=sampler` and tracing off, zero spans reach any span processor.
5. **Pure refactor (OTelFeature/poc#9):** existing `FULL`/`IO` behaviour is unchanged; existing extension tests pass.
6. **Hard floor `OTEL_SDK_DISABLED` (OTelFeature/poc#9):** with `OTEL_SDK_DISABLED=true`, flags saying on (`otelEnabled=true`, `telemetryLevel=FULL`) create no spans in either language. In Java the customizer still runs and installs nothing: no sampler, no processor, no flagd connection.
7. **Hard floor `always_off` (OTelFeature/poc#10):** with `OTEL_TRACES_SAMPLER=always_off`, no flag and no sampled parent produces a sampled span.
8. **Known limitation documented (OTelFeature/poc#8):** both extension READMEs have a "Known limitations" entry saying that trace context keeps propagating while `OFF`, so services still tracing can produce traces with gaps or missing parents.
9. **Propagation under OFF (OTelFeature/poc#8):** a request arriving with a `traceparent` while `OFF` passes it on to its outgoing calls (Python: the extracted remote parent stays current).

## Postconditions

- Flags back at baseline.
