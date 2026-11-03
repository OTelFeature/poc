# Use Case: Drop noisy spans before they are created

## Overview

**Use Case ID:** UC-002  
**Use Case Name:** Drop noisy spans before they are created  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, geocode, weather, Aspire dashboard  
**Goal:** The operator first cuts traces down to the I/O boundary by span kind (`telemetryLevel=IO`, Demo 2), then writes one `recordSpan` targeting rule per noise source (health-check requests in `geocode`, database spans in `weather`, Demo 3), so that those spans are never created while every other span in both services is kept and correctly parented.  
**Status:** Tested  
**Requirements:** FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-023, NFR-002, NFR-003, NFR-005, NFR-007, C-003, C-004, C-011  
**Work Items:** OTelFeature/poc#22, OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20, OTelFeature/otelfeature-java-extension#21, OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27, OTelFeature/poc#12, OTelFeature/poc#9, OTelFeature/poc#110  
**Test Cases:** TC-002  
**Script Beat:** Demo 2 (span kind: `telemetryLevel` FULL → IO, preset `02-quiet-noise`, steps 1 to 4); Demo 3 ("service name, instrumentation scope, the path": the `recordSpan` rules, preset `03-semconv-rules`, steps 5 to 11). See BR-009.  
**Open Questions:** none (OQ-1 answered: `processor`, UC-003 BR-004; OQ-5 resolved)  

## Preconditions

- UC-001 preconditions hold, with tracing on and `telemetryLevel=FULL`.
- Both extensions build an evaluation context from semantic conventions, nested by dot segment (OTelFeature/poc#22).
- `recordSpan` is defined with default `true` and no targeting.
- Both services create `INTERNAL` spans under their server spans, `/health` included: `geocode` the ASGI `http receive`/`http send` spans of its FastAPI instrumentation and its own `geocode.resolve` span, `weather` its Spring MVC controller spans (controller telemetry is on in the stack, A9) and, on failed requests, servlet error-handling spans.
- Health-check requests reach `geocode` and `/weather` requests in `weather` read from the database (see OQ-5 for where the health-check traffic comes from).

## Main Success Scenario

1. The operator sets `telemetryLevel` to `IO` (Demo 2).
2. flagd pushes the new value; both services take it as a static decision, with no evaluation context per span (BR-002).
3. Neither service creates `INTERNAL` spans; `SERVER` and `CLIENT` spans, database client spans included, are still created, and the children of a suppressed span attach to its real parent (BR-008).
4. The dashboard shows traces that contain only the I/O boundary, with every span correctly parented.
5. The operator adds a targeting rule on `recordSpan` that returns `false` for spans with `service.name` = `geocode`, `span.kind` = `server` and `url.path` = `/health` (Demo 3; `telemetryLevel` stays `IO`, BR-009).
6. The operator adds a targeting rule on `recordSpan` that returns `false` for spans with `service.name` = `weather` and an `otel.scope.name` of the database instrumentation.
7. flagd pushes the ruleset; both services see that `recordSpan` now has targeting and switch from the cached decision to a decision per span (or, in Python, per tracer, A2).
8. For each new span, the service builds the evaluation context from its resource, the instrumentation scope and the span's start attributes, with the trace id as `targetingKey`, and resolves the policy.
9. `geocode` does not create the health-check server span or anything under it.
10. `weather` does not create the database client spans; the request's server and HTTP client spans are still created.
11. The dashboard shows no new health-check traces from `geocode` and `/weather` traces without database spans, with the remaining spans correctly parented.
12. The operator removes both rules and sets `telemetryLevel` back to `FULL` (the baseline preset).
13. Both services return to the cached decision and create all spans again, `INTERNAL` spans included.

## Alternative Flows

### A1: Java service runs in processor mode

**Trigger:** `weather` runs with `OTELFEATURE_ENFORCEMENT=processor`, the default (step 10).

**Flow:**

1. `weather` creates the database spans and suppresses them at `onStart`, before batching.
2. The trace looks the same in the dashboard; service CPU for those spans is still spent.
3. Use case continues at step 11.

### A2: Rule reads only keys present on the tracer (Python)

**Trigger:** A rule for `geocode` reads only resource and scope keys (step 8), for example muting its database instrumentation by `otel.scope.name`.

**Flow:**

1. `geocode` decides once per tracer for that scope instead of per span; the muted instrumentation's spans cost nothing per span.
2. The decision is redone when flagd reports a configuration change.
3. Use case continues at step 9.

### A3: Rule targets an attribute that is not known at span start

**Trigger:** The operator writes the rule on `http.route` or `http.response.status_code` (step 5).

**Flow:**

1. The key is absent from the evaluation context, so the rule never matches.
2. All spans are kept (fail open).
3. Use case ends.

### A4: The sampler cannot drop the span safely (Java sampler mode)

**Trigger:** In sampler mode, the matching span propagates mid-trace (neither a root nor a non-propagating leaf), or the rule reads a key a `Sampler` is not told, such as `otel.scope.name` (step 10).

**Flow:**

1. The sampler does not drop it; the span is created with `sampled=1`, so downstream services are not affected.
2. The processor suppresses it at `onStart`, as in A1; its children are re-parented.
3. Use case continues at step 11.

### A5: Evaluation fails for a span

**Trigger:** The provider is not ready, the flag is missing, or the rule errors (step 8).

**Flow:**

1. The policy resolves to its startup defaults for that span (`recordSpan=true`); the span is created.
2. The failure is logged once per state change.
3. Use case continues at step 11.

### A6: Rule matches an incoming request from another service

**Trigger:** The matching span is a `SERVER` or `CONSUMER` span whose parent is remote, because the request came from another traced service (step 8).

**Flow:**

1. The span counts as a root (BR-003). The whole request is dropped in this service.
2. Outgoing calls from this request carry `sampled=0`, so downstream services drop it too.
3. The caller's client span is exported; the trace ends there.
4. Use case continues at step 11.

### A7: Tracing is off globally

**Trigger:** `otelEnabled=false`, `telemetryLevel=OFF`, or an env-var hard floor applies (step 3 or step 8).

**Flow:**

1. Neither the span kind nor `recordSpan` is evaluated; no span is created, whatever the level or the rule says.
2. Use case ends.

### A8: Java service suppresses INTERNAL spans in either mode

**Trigger:** `weather` applies `telemetryLevel=IO` (step 3).

**Flow:**

1. In both `processor` and `sampler` mode the processor suppresses the `INTERNAL` spans at `onStart`, and the exporter re-parents their children; the sampler does not drop mid-trace spans (BR-004).
2. The trace looks the same in the dashboard as in Python, where the tracer wrapper does not create the `INTERNAL` span at all; the Java service still spends CPU creating it.
3. Use case continues at step 4.

### A9: Controller telemetry is off in weather

**Trigger:** `weather` runs without `OTEL_INSTRUMENTATION_COMMON_EXPERIMENTAL_CONTROLLER_TELEMETRY_ENABLED=true`, so the Java agent creates no controller spans (step 3).

**Flow:**

1. `weather` has almost no `INTERNAL` spans left to suppress (only error-handling spans on failed requests); its traces are nearly the same under `FULL` and `IO`.
2. Use case continues at step 4, with the effect visible in `geocode` only (UC-003 BR-008 has the measured share per service).

## Postconditions

### Success Postconditions

- With `telemetryLevel=IO`, no `INTERNAL` span is exported and every exported span has a valid parent.
- With the rules active, matching spans are not exported and all other spans are exported with valid parents.
- After the rules are removed and `telemetryLevel` is back at `FULL`, both services are back on the cached decision.

### Failure Postconditions

- If a rule cannot be evaluated, spans are kept (stock behaviour).

## Business Rules

### BR-001: Rules use the semantic-convention context

Targeting rules read the evaluation-context contract in `entity_model.md` (Reference data). The context is nested by dot segment; flat dotted keys never match. On a leaf/prefix collision the namespace wins. Extension-provided keys (resource, `span.kind`, `otel.scope.*`) win over a clashing span start attribute. The `otelfeature.*` namespace is reserved; span attributes cannot set it. `targetingKey` is the trace id. Rules use `url.path`, not `http.route` (decision D6).

### BR-002: Context only on the targeted path

The evaluation context is built only when the flag is not static. While all flags are static (or missing), a span decision is one volatile read (NFR-003).

### BR-003: What counts as a root, and what dropping it does

A span is a root when it has no valid parent, or when it is an incoming request span (`SERVER`/`CONSUMER`) with a remote parent. Dropping a root drops the whole request in that service, and downstream services receive `sampled=0`. Trade-off: for a remote-parent entry span the trace ends at the caller.

- **Python:** a dropped root returns a non-recording span with a valid, non-sampled context (the trace id it was evaluated on). A dropped non-root is suppressed alone; its children attach to the real parent.
- **Java sampler mode:** `DROP` for roots and for non-propagating leaves (database client spans). A span that propagates mid-trace is suppressed by the processor instead (A4).
- **Java processor mode:** the span is suppressed at `onStart`; children are re-parented (A1).
- **Known Java edge (documented, not fixed):** with a non-parent-based sampler (for example `OTEL_TRACES_SAMPLER=always_on`), children of a dropped root are sampled as orphans.

Implemented by OTelFeature/otelfeature-instrument#14 and OTelFeature/otelfeature-java-extension#27 (OQ-6 resolved; also see OQ-8).

### BR-004: Sampler only drops roots and leaves

In sampler mode, only root spans and leaf spans (database client spans, identified by `db.system.name`) are dropped (C-004). Everything else is delegated to the configured sampler and, if it matches a rule, suppressed by the processor.

### BR-005: One decision per span

A span's fate is decided once, at start (NFR-007).

### BR-006: Which flag carries the drop rule

The drop rules are targeting on the dedicated boolean flag `recordSpan` (default `true`, key override `OTELFEATURE_RECORD_SPAN_FLAG_NAME`), evaluated per span against the semconv context (OQ-8 resolved). `otelEnabled` and `telemetryLevel` stay global switches. Precedence: hard floors (`OTEL_SDK_DISABLED=true`, `OTEL_TRACES_SAMPLER=always_off`) > `otelEnabled`/`telemetryLevel=OFF` > `telemetryLevel=IO` for `INTERNAL` spans (BR-008) > `recordSpan`. `recordSpan=true` never re-enables anything a higher level turned off.

### BR-007: When Python decides per tracer

Python decides once per tracer only when every key the rule can read is present on the tracer (resource and scope keys). A rule that reads span keys, `targetingKey` (including through `fractional`), `otelfeature.*`, or keys listed in `missing`/`missing_some` that are not on the tracer is decided per span. An OpenFeature global or transaction context, or API-level hooks, force per-span decisions, because they can change per request (OQ-7 resolved, OTelFeature/poc#12).

### BR-008: What `telemetryLevel=IO` keeps

`telemetryLevel=IO` suppresses `INTERNAL` spans only. `SERVER`, `CLIENT`, `PRODUCER` and `CONSUMER` spans are kept, so every hop between processes and every database call stays visible. A suppressed span's children attach to its real parent, so the tree stays connected. The level is a static flag value: it is decided without an evaluation context (BR-002). It combines with `recordSpan`: a span is created only when the level keeps its kind and `recordSpan` does not drop it; `recordSpan=true` never brings back an `INTERNAL` span under `IO` (BR-006, FR-003).

### BR-009: Demo 2 cuts by span kind, Demo 3 by semantic conventions

Decided by Simon, 2026-11-03 (OTelFeature/poc#110). Demo 2 limits traces by span kind only: `02-quiet-noise` sets `telemetryLevel` to `IO` and leaves `recordSpan` at `true` without targeting, so no service, path or scope condition is involved. The `recordSpan` targeting rules on the semconv context (steps 5 and 6) arrive in Demo 3, in `03-semconv-rules`, next to the `traceSampleRatio` rules (UC-004), because Demo 3 is the beat about rules on semantic conventions. The presets are cumulative (UC-008 BR-006): `03-semconv-rules`, `03a-weather-boost` and `03b-incident` keep `telemetryLevel=IO` and the `recordSpan` rules. Before this decision, Demo 2 used the `recordSpan` rules and kept `telemetryLevel=FULL` (OTelFeature/poc#26).
