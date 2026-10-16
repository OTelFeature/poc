# Use Case: Switch tracing off and on at runtime

## Overview

- **Use Case ID:** UC-001
- **Use Case Name:** Switch tracing off and on at runtime
- **Primary Actor:** Operator
- **Secondary Actors:** flagd, geocode, weather, Aspire dashboard
- **Goal:** The operator stops all span creation in every service with one boolean flag and starts it again, without a restart, so that span ingest drops to zero during an incident and recovers cleanly afterwards.
- **Status:** Draft
- **Requirements:** FR-001, FR-002, FR-004, NFR-001, NFR-003, NFR-004, NFR-008, C-001, C-004
- **Work Items:** OTelFeature/poc#8, OTelFeature/poc#9, OTelFeature/otelfeature-java-extension#21 (sampler mode)
- **Test Cases:** TC-001
- **Script Beat:** Demo 1

## Preconditions

- The demo stack is running with the baseline flags: `otelEnabled=true`, `telemetryLevel=FULL`.
- Traffic reaches both services and their traces are visible in the dashboard.
- Both services run extension releases that contain the policy and the `OFF` handling.

## Main Success Scenario

1. The operator sets `otelEnabled` to `false`.
2. flagd pushes the changed ruleset to both services.
3. Each service resolves its telemetry policy again and gets `enabled=false`.
4. From the next request on, each service creates no spans.
5. The dashboard shows no new traces from `geocode` or `weather`, while their metrics keep arriving.
6. The operator sets `otelEnabled` back to `true`.
7. flagd pushes the changed ruleset to both services.
8. Each service resolves `enabled=true` and creates spans again from the next request on.
9. The dashboard shows new, complete traces from both services.

## Alternative Flows

### A1: Operator uses the telemetryLevel OFF variant

**Trigger:** Step 1, the operator sets `telemetryLevel` to `OFF` instead of changing `otelEnabled`.

**Flow:**

1. The services resolve `enabled=false`, exactly as for `otelEnabled=false`.
2. Use case continues at step 4.

### A2: flagd is unreachable or the flag is missing

**Trigger:** Step 2, the services cannot get a ruleset, or `otelEnabled` is not defined.

**Flow:**

1. Each service resolves the policy from its startup defaults (`enabled=true`).
2. Each service logs the provider state once.
3. Spans keep being created as with the stock OTel SDK.
4. Use case ends.

### A3: Java service runs in processor mode

**Trigger:** Step 4, `weather` runs with `OTELFEATURE_ENFORCEMENT=processor`.

**Flow:**

1. `weather` still creates and populates spans, then drops all of them before batching.
2. No `weather` spans are exported. Service CPU is not saved, only export.
3. Use case continues at step 5.

### A4: A request is in flight while the flag flips

**Trigger:** Step 4, a trace started before the flip is still running.

**Flow:**

1. Spans of that trace that start after the flip are not created; spans that already started are exported when they end.
2. Context propagation continues, so downstream services see a valid trace context.
3. Use case continues at step 5.

## Postconditions

### Success Postconditions

- Both services create spans again and traces are complete.
- No service was restarted.
- Metrics were exported throughout.

### Failure Postconditions

- If the flag cannot be read, both services behave like the stock OTel SDK (spans on).

## Business Rules

### BR-001: Either flag switches tracing off

Tracing is off when `otelEnabled=false` or `telemetryLevel=OFF`. Neither flag can turn tracing on while the other says off (decision D2).

### BR-002: Traces only

The kill switch affects spans only. Metrics and logs keep flowing (C-001). Per-signal switches are deferred (OTelFeature/poc#11).

### BR-003: Suppression, not SDK disable

Context propagation and instrumentation stay in place. In Python no span is created. In Java sampler mode every root span is dropped before creation, which drops its subtree. In Java processor mode spans are created and dropped before batching (A3).

### BR-004: Fail open

Any provider or flag error resolves to tracing on (NFR-001). Unknown `telemetryLevel` values resolve to `FULL`.

### BR-005: Propagation time

A flip affects new spans within 2 seconds (NFR-004).
