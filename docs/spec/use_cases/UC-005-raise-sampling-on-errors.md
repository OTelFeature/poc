# Use Case: Raise sampling while a service is failing

## Overview

**Use Case ID:** UC-005  
**Use Case Name:** Raise sampling while a service is failing  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, weather, geocode  
**Goal:** When a service's HTTP error rate rises above 5%, a targeting rule raises that service's trace sample ratio to 1.0 and lowers it again once errors stop, with no script outside the services, so that the failing service is fully traced exactly while it fails.  
**Status:** Draft  
**Requirements:** FR-011, FR-013, FR-009, FR-024, FR-026, NFR-004, NFR-006, NFR-012, NFR-013, NFR-014, C-005  
**Work Items:** OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22, OTelFeature/poc#28, OTelFeature/poc#29, OTelFeature/poc#10  
**Test Cases:** TC-005  
**Script Beat:** Demo 3 ("errors go up, a rule turns sampling up for that service")  

## Preconditions

- UC-004 is in place: production `weather` samples at 0.5 and the rest of production at 0.1 (`03a-weather-boost`).
- The control-loop rule is defined in `03b-incident`, ahead of the other ratio rules: 1.0 when `otelfeature.http.server.error_rate` is above 0.05, else the other rules (entity model FLAG_PRESET).
- Each extension reads its service's `http.server.request.duration` metric in process, through a delta reader, every collection interval (`OTELFEATURE_ERROR_RATE_INTERVAL`, default 10 seconds).
- The demo stack sets `OTEL_SEMCONV_STABILITY_OPT_IN=http` for `geocode`, so the metric carries `error.type`. The extension documents this but does not set it.

## Main Success Scenario

1. The operator applies `03b-incident`: it injects upstream failures into `weather` (UC-006) and activates the control-loop rule.
2. `weather` answers a share of `/weather` requests with an error; the HTTP server metric records them with `error.type`.
3. At the next collection, `weather` computes the error rate as error requests divided by all requests in the interval and puts it into its evaluation context.
4. The control-loop rule matches for `weather`; its sample ratio resolves to 1.0.
5. The dashboard shows the traces that start in `weather` rise from about half to all requests within one to two collection intervals, while `geocode` stays at its environment ratio. Cross-service traces follow `geocode`'s decision (UC-004 BR-003).
6. The operator removes the injected failures and keeps the rule (`weatherUpstreamFailure` back to 0.0 alone).
7. At the next collection with no errors, `weather`'s error rate falls below the threshold.
8. The rule no longer matches; `weather` returns to the ratio of the other rules (0.5 on stage).

## Alternative Flows

### A1: Too few requests in the interval

**Trigger:** The service handled fewer than `OTELFEATURE_ERROR_RATE_MIN_REQUESTS` (default 10) requests in the last interval (step 3).

**Flow:**

1. The error-rate key is left out of the context, even if every one of those requests failed.
2. The rule does not match; the other ratio rules apply.
3. Use case continues at step 3 with the next collection.

### A2: Spans are sampled at zero

**Trigger:** The service's sample ratio is 0.0 when errors start (step 2).

**Flow:**

1. The metric still records every request, so the error rate is the same as at 1.0.
2. Use case continues at step 3.

### A3: Python service without the stable HTTP conventions

**Trigger:** `geocode` emits only the older HTTP duration metric without `error.type` (step 3).

**Flow:**

1. The extension counts responses with `http.status_code >= 500` as errors.
2. Use case continues at step 4.

### A4: Both metric versions are emitted

**Trigger:** `geocode` runs with `OTEL_SEMCONV_STABILITY_OPT_IN=http/dup` (step 3).

**Flow:**

1. Only the stable `http.server.request.duration` metric is counted, so no request counts twice.
2. Use case continues at step 4.

### A5: Metrics export is switched off

**Trigger:** The service runs with `OTEL_METRICS_EXPORTER=none` (step 3).

**Flow:**

1. No metrics SDK is installed, so the error-rate reader was never registered; the service logs this once at startup.
2. The error-rate key is never in the context; the control-loop rule never matches and the other ratio rules apply (FR-024).
3. `weather` stays at its ratio before the incident (0.5 on stage) while it fails; the goal is not reached (failure postcondition).
4. Use case ends.

### A6: Incident ended by the stage preset

**Trigger:** The operator goes back to `03a-weather-boost` instead of removing only the failures (step 6).

**Flow:**

1. The preset removes the fault and the control-loop rule together.
2. `weather` is back at 0.5 within 2 seconds (NFR-004), without waiting for an error-free interval; the loop is not seen letting go on its own (OQ-14).
3. Use case ends.

### A7: `geocode`'s error rate also passes the threshold

**Trigger:** On the cross-service path (FR-026), `weather`'s failures make enough `geocode` requests fail that `geocode`'s own error rate passes 0.05 (step 3).

**Flow:**

1. The control-loop rule matches for `geocode` too, and `geocode` samples at 1.0 while it fails (BR-003: each service reacts to its own rate).
2. At stage load this is not expected: the cross-service path carries a small share of `geocode`'s requests (FR-026).
3. Use case continues at step 5, with `geocode` raised as well.

## Postconditions

### Success Postconditions

- `weather` sampled at 1.0 while its error rate was above 5% and returned to its ratio before the incident (0.5 on stage) afterwards.
- `geocode` sampling did not change, unless its own error rate passed the threshold (A7).
- The metric export to the collector is unchanged by the extra in-process reader.

### Failure Postconditions

- If the error rate cannot be computed, the key is absent and sampling follows the other ratio rules.

## Business Rules

### BR-001: Metrics as input, not spans

The error rate comes from the HTTP server metric, not from spans, because sampled-out spans never record a status (decision D5).

### BR-002: No window, no smoothing

The reader uses delta temporality, so each collection is its own window. The rate is `Σcount(points with error.type) / Σcount(all points)`.

### BR-003: Per service

Each service computes its own rate; the rule raises sampling for the failing service only.

### BR-004: Loop lives in the targeting rule

The threshold and the reaction are a flagd targeting rule. No external script and no new exported metric.

### BR-005: Context key

The rate is published as `otelfeature.http.server.error_rate`, a number between 0 and 1. It is extension-owned: the `otelfeature.*` namespace is reserved, so a span attribute cannot fake it.

### BR-006: Repeatable

The run-through works three times in a row from the reset command (NFR-012).

### BR-007: Minimum requests and lag

Below `OTELFEATURE_ERROR_RATE_MIN_REQUESTS` (default 10) requests per interval the key is omitted, so one failed request out of two does not trip the rule. Consequence, accepted: a quiet service below the minimum never gets a rate, even in a total outage. The rate lags the traffic by one to two intervals. Both are documented in the extension READMEs (NFR-014).
