# Use Case: Target trace sampling by environment and service

## Overview

**Use Case ID:** UC-004  
**Use Case Name:** Target trace sampling by environment and service  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, geocode, weather, their staging instances, Aspire dashboard  
**Goal:** The operator sets the trace sample ratio as a number flag with rules on `deployment.environment.name` and `service.name`, so that sampling changes live per environment and service and every sampled trace stays complete across services.  
**Status:** Implemented  
**Requirements:** FR-004, FR-005, FR-009, FR-010, FR-026, NFR-001, NFR-003, NFR-007, C-003, C-011, C-012  
**Work Items:** OTelFeature/poc#10, OTelFeature/poc#25, OTelFeature/poc#22, OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20, OTelFeature/otelfeature-java-extension#21, OTelFeature/otelfeature-instrument#22, OTelFeature/poc#59  
**Test Cases:** TC-004  
**Script Beat:** Demo 3 ("your evaluation context is just my resource attributes", "sample rate as a number flag")  
**Open Questions:** none (OQ-2 resolved)  

## Preconditions

- Each service sets its own `service.name`, `service.namespace`, `service.version` and `deployment.environment.name`; the collector only fills these when missing.
- A production and a staging instance of each service run and receive traffic.
- `traceSampleRatio` is defined with default 1.0.
- The load generator calls `POST /geocode` and `POST /weather` directly, so each service is the entry point of those traces.
- For the cross-service part of steps 5 and 8 and of A2: the load generator also calls the cross-service path, where `geocode` calls `weather` (FR-026, OTelFeature/poc#59).

## Main Success Scenario

1. The operator sets a rule on `traceSampleRatio`: 0.1 where `deployment.environment.name` is `production`, 1.0 otherwise.
2. flagd pushes the ruleset; all four instances switch to a decision per trace root.
3. For each new trace root, the service builds the evaluation context, with the trace id as targeting key, and resolves the sample ratio.
4. The service samples the trace root by bucketing the trace id against the ratio.
5. On the cross-service path `geocode` is the entry point and decides; `weather` follows the parent's decision, so the trace is either complete or absent. Direct `POST /weather` traces start in `weather`, which decides them itself.
6. The dashboard shows about one in ten production traces and all staging traces.
7. The operator adds a second rule that sets 0.5 for `service.name` = `weather` in production (`03a-weather-boost`), so `weather` is sampled more than the rest but not fully (it leaves room for the error-rate rule in UC-005 to raise it to 1.0).
8. The dashboard shows about half of the production traces that start in `weather` and still about one in ten `geocode` production traces.

## Alternative Flows

### A1: Ratio out of range or not a number

**Trigger:** The flag resolves to a value outside 0.0 to 1.0 or not a number (step 3).

**Flow:**

1. A value above 1.0 is clamped to 1.0. A negative value, NaN, infinity or a non-number falls back to the startup ratio (NFR-001), logged once per state change. Decided by Simon, 2026-10-16: a negative ratio is far more likely a typo than "drop every trace".
2. No exception reaches the application.
3. Use case continues at step 4.

### A2: Ratio flipped on a downstream service only

**Trigger:** The operator expects the raise to change traces that another service starts, for example the cross-service traces `geocode` starts (step 7).

**Flow:**

1. On that path the service follows its parent's sampling decision; the raise has no effect on those traces, which stay at about one in ten (BR-003).
2. The operator moves the rule to the entry-point service, or accepts that only the traces the service starts itself change.
3. Use case continues at step 8.

### A3: Ratio set to zero

**Trigger:** The rule resolves to 0.0 for a service (step 1).

**Flow:**

1. No trace roots of that service are sampled, equivalent to an always-off sampler.
2. Use case continues at step 6, where the dashboard shows no traces that start in that service; traces it joins with a sampled parent still appear (BR-002).

### A4: Service does not declare its environment

**Trigger:** `deployment.environment.name` is missing from the resource (step 3).

**Flow:**

1. The environment rule does not match and the flag's default variant applies.
2. Use case continues at step 4.

### A5: The service's env vars switched sampling off

**Trigger:** The service runs with `OTEL_TRACES_SAMPLER=always_off` or `parentbased_always_off` (step 3).

**Flow:**

1. With `always_off`, nothing is sampled: no ratio and no sampled parent can change that (hard floor).
2. With `parentbased_always_off`, no trace starts sampled in this service whatever the ratio; traces arriving with a sampled parent are followed.
3. Use case continues at step 6.

### A6: Unknown sampler name (Python)

**Trigger:** `OTEL_TRACES_SAMPLER` names a sampler the SDK does not know, for example `jaeger_remote` (step 3).

**Flow:**

1. The extension logs a warning at startup and uses 1.0 as the startup ratio, as the plain SDK provider would; custom samplers are never loaded.
2. The flag works as in the main scenario.
3. Use case continues at step 4.

## Postconditions

### Success Postconditions

- Sampling follows the rules per environment and service, live.
- Sampled traces are complete across services.

### Failure Postconditions

- If the flag cannot be read, sampling follows the startup sampler configuration.

## Business Rules

### BR-001: Trace id is the targeting key

The targeting key is the trace id in hex, so flagd's `fractional` puts a trace in the same bucket in every service.

### BR-002: Trace roots only

Only trace roots evaluate the ratio. All other spans follow the parent's decision (always parent-based), so a flip mid-trace never splits a trace.

### BR-003: Entry point decides

A ratio change only matters at the service that starts the trace. The README of each extension states this.

### BR-004: Environment comes from the service

`deployment.environment.name` is set by the service, not upserted by the collector, because the decision happens in the SDK.

### BR-005: Hard floors

`OTEL_TRACES_SAMPLER=always_off` (and `OTEL_SDK_DISABLED=true`) cannot be overridden by `traceSampleRatio` or a sampled parent (C-011). `parentbased_always_off` keeps its standard meaning.

### BR-006: Fallback for the startup ratio

The startup ratio comes from `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG`, parsed like the SDK. Python treats unknown names as 1.0 with a warning (C-012).

### BR-007: Prior art

OpenTelemetry's `jaeger_remote` sampler also changes sampling remotely. The difference is reuse of existing flag infrastructure and OpenFeature targeting. The extension READMEs name it.

### BR-008: Cross-language ratio parity is not guaranteed (accepted, Simon, 2026-10-16)

Each extension applies its own SDK's trace-id ratio formula. Java compares the lower 64 bits of the trace id, signed, against `ratio * Long.MAX_VALUE`; Python compares 64 bits, unsigned, against `ratio * 2^64`. At the same ratio they can disagree on the same trace id. This is harmless with parent-based propagation, because only the entry service decides (BR-002, BR-003). Where a decision must agree across languages, bucket with a flagd `fractional` rule on `targetingKey` (the trace id), which every service evaluates the same way. Both extension READMEs document this. Worked example and diagrams: [ratio-parity.md](../ratio-parity.md).
