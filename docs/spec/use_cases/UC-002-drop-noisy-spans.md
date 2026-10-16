# Use Case: Drop noisy spans before they are created

## Overview

- **Use Case ID:** UC-002
- **Use Case Name:** Drop noisy spans before they are created
- **Primary Actor:** Operator
- **Secondary Actors:** flagd, geocode, weather, Aspire dashboard
- **Goal:** The operator writes one targeting rule per noise source (health-check requests in `geocode`, database spans in `weather`) so that those spans are never created, while every other span in both services is kept.
- **Status:** Draft
- **Requirements:** FR-004, FR-005, FR-006, FR-007, FR-008, NFR-002, NFR-003, NFR-005, NFR-007, C-003, C-004
- **Work Items:** OTelFeature/poc#22, OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20, OTelFeature/otelfeature-java-extension#21, OTelFeature/poc#12, OTelFeature/poc#9
- **Test Cases:** TC-002
- **Script Beat:** Demo 2 ("service name, instrumentation scope, the path")
- **Open Questions:** OQ-1, OQ-2, OQ-5, OQ-6, OQ-7, OQ-8

## Preconditions

- UC-001 preconditions hold, with tracing on.
- Both extensions build an evaluation context from semantic conventions, in the shape decided by OTelFeature/poc#22.
- Health-check requests reach `geocode` and `/weather` requests in `weather` read from the database (see OQ-5 for where the health-check traffic comes from).

## Main Success Scenario

1. The operator adds a targeting rule that marks spans with `service.name` = `geocode`, `span.kind` = `server` and `url.path` = `/health` as dropped.
2. The operator adds a targeting rule that marks spans with `service.name` = `weather` and an `otel.scope.name` of the database instrumentation as dropped.
3. flagd pushes the ruleset; both services see that the flag now has targeting and switch from the cached decision to a decision per span.
4. For each new span, the service builds the evaluation context from its resource, the instrumentation scope and the span's start attributes, and resolves the policy.
5. `geocode` does not create the health-check server span or anything under it.
6. `weather` does not create the database client spans; the request's server and HTTP client spans are still created.
7. The dashboard shows no new health-check traces from `geocode` and `/weather` traces without database spans, with the remaining spans correctly parented.
8. The operator removes both rules.
9. Both services return to the cached decision and create all spans again.

## Alternative Flows

### A1: Java service runs in processor mode

**Trigger:** Step 6, `weather` runs with `OTELFEATURE_ENFORCEMENT=processor`.

**Flow:**

1. `weather` creates the database spans and drops them when they start, before batching.
2. The trace looks the same in the dashboard; service CPU for those spans is still spent.
3. Use case continues at step 7.

### A2: Rule depends only on resource and scope keys (Python)

**Trigger:** Step 4, a rule for `geocode` reads only resource and scope keys (for example muting its database instrumentation by `otel.scope.name`).

**Flow:**

1. `geocode` decides once per tracer for that scope instead of per span.
2. The decision is redone when flagd reports a configuration change.
3. Use case continues at step 5.

### A3: Rule targets an attribute that is not known at span start

**Trigger:** Step 1, the operator writes the rule on `http.route` or `http.response.status_code`.

**Flow:**

1. The key is absent from the evaluation context, so the rule never matches.
2. All spans are kept (fail open).
3. Use case ends.

### A4: The sampler cannot drop the span safely

**Trigger:** Step 6, in sampler mode, the matching span is neither a root nor a leaf (for example a mid-trace `INTERNAL` span).

**Flow:**

1. The sampler delegates; the span is created.
2. Mid-trace `INTERNAL` suppression, when requested by `telemetryLevel=IO`, is done by the processor as today.
3. Use case continues at step 7.

### A5: Evaluation fails for a span

**Trigger:** Step 4, the provider is not ready or the rule errors.

**Flow:**

1. The policy resolves to its startup defaults for that span; the span is created.
2. The failure is logged once per state change.
3. Use case continues at step 7.

## Postconditions

### Success Postconditions

- With the rules active, matching spans are not exported and all other spans are exported with valid parents.
- After the rules are removed, both services are back on the cached decision.

### Failure Postconditions

- If a rule cannot be evaluated, spans are kept (stock behaviour).

## Business Rules

### BR-001: Rules use semantic-convention names

Targeting rules read the evaluation-context contract in `entity_model.md` (Reference data). Rules use `url.path`, not `http.route` (decision D6).

### BR-002: Context only on the targeted path

The evaluation context is built only when the flag is not static. While all flags are static, a span decision is one volatile read (NFR-003).

### BR-003: Dropping a root drops its subtree

A dropped root span takes its descendants in the same service with it, and downstream services receive a not-sampled trace context. How Python's tracer wrapper and Java's processor mode achieve this is open (OQ-6).

### BR-004: Sampler only drops roots and leaves

In sampler mode, only root spans and leaf spans (database client spans, identified by `db.system.name`) are dropped (C-004). Everything else is delegated to the configured sampler.

### BR-005: One decision per span

A span's fate is decided once, at start (NFR-007).

### BR-006: Which flag carries the drop rule

Working assumption: the rules are targeting on `telemetryLevel` returning `OFF` for the matching context, so they map onto `enabled=false` in the policy. Not decided (OQ-8).
