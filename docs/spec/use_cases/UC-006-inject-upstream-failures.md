# Use Case: Inject upstream failures

## Overview

**Use Case ID:** UC-006  
**Use Case Name:** Inject upstream failures  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, weather, geocode, Aspire dashboard  
**Goal:** The operator makes a chosen fraction of `/weather` requests (or, for the e2e suite, `geocode`'s requests, A3) fail through a feature flag evaluated in the application's own code, so that an incident can be started and stopped on demand, the same way the OTel Demo does it.  
**Status:** Tested  
**Requirements:** FR-012, NFR-004  
**Work Items:** OTelFeature/poc#28, OTelFeature/poc#80  
**Test Cases:** TC-005, TC-006  
**Script Beat:** Demo 3 incident; "the only part of the demo I understand"  

## Preconditions

- `weather` evaluates `weatherUpstreamFailure` through its own OpenFeature client, separate from the agent extension's isolated one.
- `weatherUpstreamFailure` is defined with default 0.0.
- For A3: `geocode` evaluates `geocodeUpstreamFailure` through its own OpenFeature client (BR-004).

## Main Success Scenario

1. The operator sets `weatherUpstreamFailure` to 0.5 (incident preset, BR-003).
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

### A3: Failures in `geocode`

**Trigger:** The operator wants the incident in the Python service instead (step 1).

**Flow:**

1. The operator sets `geocodeUpstreamFailure` to a share between 0.0 and 1.0.
2. For each `POST /geocode` request (and so each `POST /forecast`, which resolves its coordinates the same way), `geocode` evaluates the flag and fails that share with "service unavailable" before the cache lookup.
3. The failed requests appear as error spans, as in step 4; the same range rules apply (BR-002, A2).
4. The operator sets `geocodeUpstreamFailure` back to 0.0.
5. Use case ends.

## Postconditions

### Success Postconditions

- No requests fail after the flag is reset.

### Failure Postconditions

- _None: a missing flag means no injected failures._

## Business Rules

### BR-001: Application flag, not extension flag

The failure flag is evaluated by the application, not by the telemetry extension. Its evaluation is what UC-007 shows on the span, for `weatherUpstreamFailure` and for `geocodeUpstreamFailure` (UC-007 A2).

### BR-002: Value range

The value is the share of `/weather` requests (for `geocodeUpstreamFailure`: `POST /geocode` requests) that fail, from 0.0 (none) to 1.0 (all), both bounds inclusive. Values outside the range act as the nearest bound; NaN and non-numbers act as 0.0 (A2). This is the behaviour of `FaultInjection` today; it is documented, not changed. `geocode` applies the same rules (A3). Unit tests in both services check the bounds (TC-005 item 7, OTelFeature/poc#75).

### BR-003: The incident fails half of `/weather`

Decided by Simon, 2026-10-16 (OQ-14 b): the incident preset `03b-incident` sets the share to **0.5** (was 0.3). The control loop (UC-005) reads the error rate over all of `weather`'s requests, and only `POST /weather` fails; on the stage load (k6 `/weather` 1/s and `/health` 2/s, plus the compose healthcheck every 2 s) that is about 35 requests per 10 s interval. At 0.3 the error rate was about 9%, and in about one interval in seven it stayed under the 5% threshold, so `weather` dipped back to its 0.5 ratio. At 0.5 it is about 14% (5 in 35), and an interval not above the 5% threshold (at most one failure in ten `/weather` requests) has a chance of about 1%.

### BR-004: `geocode`'s fault flag is for the e2e suite

`geocodeUpstreamFailure` exists so the control loop (UC-005) also runs end to end for the Python error-rate reader (OTelFeature/poc#80). The stage presets don't define it, so on stage it resolves to its default 0.0 (A1). `geocode` evaluates it through a client of its own on the OpenFeature API the Python extension also uses. The traces hook sits on that client only, never API-wide, since an API-wide hook would also record the extension's evaluations (UC-007 BR-006).
