# Use Case: Raise sampling while a service is failing

## Overview

- **Use Case ID:** UC-005
- **Use Case Name:** Raise sampling while a service is failing
- **Primary Actor:** Operator
- **Secondary Actors:** flagd, weather, geocode, Speaker (causes the failure through UC-006)
- **Goal:** When a service's HTTP error rate rises above 5%, a flag rule raises that service's trace sample ratio to 1.0 and lowers it again once errors stop, with no script outside the services, so that the failing service is fully traced exactly while it fails.
- **Status:** Draft
- **Requirements:** FR-011, FR-013, FR-009, NFR-006, NFR-012, NFR-013, C-005
- **Work Items:** OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22, OTelFeature/poc#28, OTelFeature/poc#29, OTelFeature/poc#10
- **Test Cases:** TC-005
- **Script Beat:** Demo 3 ("errors go up, a rule turns sampling up for that service")

## Preconditions

- UC-004 is in place: production samples at 0.1.
- The control-loop rule is active on `traceSampleRatio`: 1.0 when `otelfeature.http.server.error_rate` is above 0.05, else the environment rule.
- Each extension reads its service's `http.server.request.duration` metric in process every collection interval (default 10 seconds).
- In `geocode`, the stable HTTP semantic conventions are enabled so the metric carries `error.type`.

## Main Success Scenario

1. The speaker injects upstream failures into `weather` (UC-006).
2. `weather` answers a share of `/weather` requests with an error; the HTTP server metric records them with `error.type`.
3. At the next collection, `weather` computes the error rate as error requests divided by all requests in the interval and puts it into its evaluation context.
4. The control-loop rule matches for `weather`; its sample ratio resolves to 1.0.
5. The dashboard shows `weather` trace volume rise to all requests within one collection interval, while `geocode` stays at its environment ratio.
6. The speaker removes the injected failures.
7. At the next collection with no errors, `weather`'s error rate falls below the threshold.
8. The rule no longer matches; `weather` returns to the environment ratio.

## Alternative Flows

### A1: No requests in the interval

**Trigger:** Step 3, the service handled no requests in the last interval.

**Flow:**

1. The error-rate key is left out of the context.
2. The rule does not match; the environment rule applies.
3. Use case continues at step 5.

### A2: Spans are sampled at zero

**Trigger:** Step 2, the service's sample ratio is 0.0 when errors start.

**Flow:**

1. The metric still records every request, so the error rate is the same as at 1.0.
2. Use case continues at step 3.

### A3: Python service without the stable HTTP conventions

**Trigger:** Step 3, `geocode` emits only the older HTTP duration metric without `error.type`.

**Flow:**

1. The extension counts responses with status 500 or higher as errors.
2. Use case continues at step 4.

## Postconditions

### Success Postconditions

- `weather` sampled at 1.0 while its error rate was above 5% and returned to the environment ratio afterwards.
- `geocode` sampling did not change.
- The metric export to the collector is unchanged by the extra in-process reader.

### Failure Postconditions

- If the error rate cannot be computed, the key is absent and sampling follows the environment rule.

## Business Rules

### BR-001: Metrics as input, not spans

The error rate comes from the HTTP server metric, not from spans, because sampled-out spans never record a status (decision D5).

### BR-002: No window, no smoothing

The reader uses delta temporality, so each collection is its own window. The rate is `Σcount(points with error.type) / Σcount(all points)`.

### BR-003: Per service

Each service computes its own rate; the rule raises sampling for the failing service only.

### BR-004: Loop lives in the flag rule

The threshold and the reaction are a flagd targeting rule. No external script and no new exported metric.

### BR-005: Context key

The rate is published as `otelfeature.http.server.error_rate`, a number between 0 and 1.

### BR-006: Repeatable

The run-through works three times in a row from the reset command (NFR-012).
