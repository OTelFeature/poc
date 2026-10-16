# Use Case: Inject upstream failures

## Overview

**Use Case ID:** UC-006  
**Use Case Name:** Inject upstream failures  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, weather, Aspire dashboard  
**Goal:** The operator makes a chosen fraction of `/weather` requests fail through a feature flag evaluated in the application's own code, so that an incident can be started and stopped on demand, the same way the OTel Demo does it.  
**Status:** Implemented  
**Requirements:** FR-012, NFR-004  
**Work Items:** OTelFeature/poc#28  
**Test Cases:** TC-005  
**Script Beat:** Demo 3 incident; "the only part of the demo I understand"  

## Preconditions

- `weather` evaluates `weatherUpstreamFailure` through its own OpenFeature client, separate from the agent extension's isolated one.
- `weatherUpstreamFailure` is defined with default 0.0.

## Main Success Scenario

1. The operator sets `weatherUpstreamFailure` to 0.3 (incident preset).
2. flagd pushes the ruleset to `weather`.
3. For each `/weather` request, `weather` evaluates the flag and fails that share of requests with "service unavailable".
4. Failed requests appear as error spans in the dashboard within 2 seconds, and in span metrics with status error.
5. The operator sets `weatherUpstreamFailure` back to 0.0.
6. New `/weather` requests succeed again.

## Alternative Flows

### A1: Flag missing or unreadable

**Trigger:** `weather` cannot evaluate the flag (step 3).

**Flow:**

1. The flag resolves to 0.0 and no request fails.
2. Use case ends.

### A2: Value outside 0.0 to 1.0, or not a number

**Trigger:** The flag resolves to a value below 0.0, above 1.0, NaN, or a non-number (step 3).

**Flow:**

1. A value at or above 1.0, or +infinity, fails every `/weather` request with HTTP 503; use case continues at step 4.
2. A value at or below 0.0, -infinity or NaN fails no request. A non-number is a type mismatch, so the OpenFeature client returns the default 0.0 and no request fails either.
3. No exception other than the injected HTTP 503 reaches a request.
4. In the cases of flow step 2, use case ends.

## Postconditions

### Success Postconditions

- No requests fail after the flag is reset.

### Failure Postconditions

- _None: a missing flag means no injected failures._

## Business Rules

### BR-001: Application flag, not extension flag

The failure flag is evaluated by the application, not by the telemetry extension. Its evaluation is what UC-007 shows on the span.

### BR-002: Value range

The value is the share of `/weather` requests that fail, from 0.0 (none) to 1.0 (all), both bounds inclusive. Values outside the range act as the nearest bound; NaN and non-numbers act as 0.0 (A2). This is the behaviour of `FaultInjection` today; it is documented, not changed.
