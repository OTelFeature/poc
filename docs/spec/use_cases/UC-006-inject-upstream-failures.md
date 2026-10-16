# Use Case: Inject upstream failures

## Overview

**Use Case ID:** UC-006  
**Use Case Name:** Inject upstream failures  
**Primary Actor:** Speaker  
**Secondary Actors:** flagd, weather, Aspire dashboard  
**Goal:** The speaker makes a chosen fraction of `/weather` requests fail through a feature flag evaluated in the application's own code, so that an incident can be started and stopped on demand, the same way the OTel Demo does it.  
**Status:** Implemented  
**Requirements:** FR-012, NFR-004  
**Work Items:** OTelFeature/poc#28  
**Test Cases:** TC-005  
**Script Beat:** Demo 3 incident; "the only part of the demo I understand"  

## Preconditions

- `weather` evaluates `weatherUpstreamFailure` through its own OpenFeature client, separate from the agent extension's isolated one.
- `weatherUpstreamFailure` is defined with default 0.0.

## Main Success Scenario

1. The speaker sets `weatherUpstreamFailure` to 0.5 (incident preset, BR-003).
2. flagd pushes the ruleset to `weather`.
3. For each `/weather` request, `weather` evaluates the flag and fails that share of requests with "service unavailable".
4. Failed requests appear as error spans in the dashboard within 2 seconds, and in span metrics with status error.
5. The speaker sets `weatherUpstreamFailure` back to 0.0.
6. New `/weather` requests succeed again.

## Alternative Flows

### A1: Flag missing or unreadable

**Trigger:** `weather` cannot evaluate the flag (step 3).

**Flow:**

1. The flag resolves to 0.0 and no request fails.
2. Use case ends.

## Postconditions

### Success Postconditions

- No requests fail after the flag is reset.

### Failure Postconditions

- _None: a missing flag means no injected failures._

## Business Rules

### BR-001: Application flag, not extension flag

The failure flag is evaluated by the application, not by the telemetry extension. Its evaluation is what UC-007 shows on the span.

### BR-002: Value range

The value is a fraction from 0.0 to 1.0 of `/weather` requests.

### BR-003: The incident fails half of `/weather`

Decided by Simon, 2026-10-16 (OQ-14 b): the incident preset `03b-incident` sets the share to **0.5** (was 0.3). The control loop (UC-005) reads the error rate over all of `weather`'s requests, and only `POST /weather` fails; on the stage load (k6 `/weather` 1/s and `/health` 2/s, plus the compose healthcheck every 2 s) that is about 35 requests per 10 s interval. At 0.3 the error rate was about 9%, and in about one interval in seven it stayed under the 5% threshold, so `weather` dipped back to its 0.5 ratio. At 0.5 it is about 15%, and an interval under 5% (at most one failure in ten `/weather` requests) has a chance of about 1%.
