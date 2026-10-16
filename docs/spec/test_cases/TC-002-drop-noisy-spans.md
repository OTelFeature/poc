# Test Case: Drop health-check and database spans by rule

## Overview

- **ID:** TC-002
- **Goal:** The operator applies the Demo 2 rules and verifies that `geocode` health-check traces and `weather` database spans are no longer created, all other spans remain correctly parented, and removing the rules restores everything.
- **Priority:** Critical
- **Status:** Draft

## Roles

- Operator: applies and removes the rules.

## Preconditions

- Extension releases containing OTelFeature/otelfeature-instrument#7 and OTelFeature/otelfeature-java-extension#20 (context) and, for sampler mode, OTelFeature/otelfeature-java-extension#21.
- Context shape fixed by OTelFeature/poc#22.
- Health-check traffic reaches `geocode` (source: OQ-5).

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Apply rules | Apply the quiet-noise preset | rule A: `service.name=geocode`, `span.kind=server`, `url.path=/health` → drop; rule B: `service.name=weather`, `otel.scope.name`=JDBC instrumentation scope → drop | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 2 | Verify geocode | No new `geocode` `/health` traces; `/geocode` traces unchanged | - | - |
| 3 | Verify weather | New `/weather` traces contain server and HTTP client spans and no database spans; no orphaned parents | - | - |
| 4 | Remove rules | Apply the baseline preset | baseline `flagd.json` | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 5 | Verify restore | Health-check traces and database spans reappear within 2 s | - | - |

## Validation

1. **Contract (OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20):** a flagd FILE-resolver unit test resolves the rule `service.name == "weather" && span.kind == "server" && url.path == "/health"` differently for a health span and a `/weather` span.
2. **Trace-consistent bucketing:** `fractional` on `targetingKey` yields the same bucket for two spans of the same trace.
3. **Static path (NFR-003):** with no targeting, the decision allocates no evaluation context (allocation test or benchmark).
4. **Both Java modes (OTelFeature/otelfeature-java-extension#21):** the same behavioural tests for health-check roots and database leaf spans pass in `processor` and `sampler` mode; in sampler mode a dropped span never reaches any processor's `onStart`; unknown or erroring flag → delegate.
5. **Start-time only (D6):** the extension READMEs list the contract keys and state that `http.route` and `http.response.status_code` are not available.
6. **Per-tracer decision (OTelFeature/poc#12):** a Python rule on scope keys only is decided once per tracer and redone on configuration change; rules with span keys behave unchanged.
7. **Decision cost:** per-span evaluation cost measured once per language and noted in the README.

## Postconditions

- Flags back at baseline.
