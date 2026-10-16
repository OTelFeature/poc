# Use Case: Measure the savings of a drop rule

## Overview

**Use Case ID:** UC-003  
**Use Case Name:** Measure the savings of a drop rule  
**Primary Actor:** Operator  
**Secondary Actors:** OTel Collector, geocode, weather  
**Goal:** The operator gets per-service numbers for CPU, memory, spans per second and export bytes per second, before and after the Demo 2 rules, for both Java enforcement modes, so that the slide brackets are filled with measured values and the sampler-versus-processor decision is made on data.  
**Status:** Draft  
**Requirements:** FR-016, FR-008, NFR-005, NFR-006, NFR-011, C-006  
**Work Items:** OTelFeature/poc#27, OTelFeature/otelfeature-java-extension#21  
**Test Cases:** TC-003  
**Script Beat:** Demo 2 ("CPU [X%] lower, memory [Y MB] lower, export bytes [Z%] lower"); input to decision D3  
**Open Questions:** OQ-3 (deferred to a later load test; OQ-1 answered: BR-004; OQ-5 resolved)  

## Preconditions

- Released extension versions containing the semconv context and the Java sampler are pinned in the demo stack.
- The stack runs offline with the stubbed external APIs, so the load is not limited by third-party rate limits.
- The Demo 2 preset exists (UC-008).

## Main Success Scenario

1. The operator starts the measurement with one command.
2. The system runs the baseline preset for the configured duration and records, per service, CPU, resident memory, spans per second and export bytes per second, at the service, not at the backend.
3. The system runs the Demo 2 preset with `weather` in processor mode (the default, `OTELFEATURE_ENFORCEMENT=processor`) and records the same values.
4. The system runs the Demo 2 preset with `weather` in sampler mode and records the same values.
5. The system runs the baseline with a targeted rule that never matches, so every span is decided per span but none is dropped, and records the same values: the extra CPU over the baseline is the decision cost (BR-006).
6. The system prints one table per service comparing the runs and the decision cost.
7. The operator runs a second measurement with the same command and compares the two tables.
8. The operator records the numbers for the script brackets and the D3 recommendation in OTelFeature/poc#27.

## Alternative Flows

### A1: Runs are not reproducible

**Trigger:** The two measurements differ by more than 10% on spans or bytes, or by more than the run-to-run noise on CPU (BR-003), for the same preset (step 7).

**Flow:**

1. The operator extends the run duration or removes the source of variance and repeats the measurement.
2. Use case continues at step 1.

### A2: Savings are smaller than the decision cost

**Trigger:** The targeted decision costs more CPU than the dropped spans save (step 6).

**Flow:**

1. The operator records the result in OTelFeature/poc#27 and the script claim is changed to match the numbers.
2. Use case ends.

### A3: Live view on stage

**Trigger:** The operator needs the drop visible during the talk rather than as a table (step 1).

**Flow:**

1. The dashboard shows the collector's span metrics per service (`traces.span.metrics.calls`, by `service.name`) live, so the drop is visible within seconds of the flag flip.
2. Use case ends.

## Postconditions

### Success Postconditions

- A per-service table with baseline, processor mode and sampler mode exists and is recorded in OTelFeature/poc#27.
- A D3 recommendation with numbers and the implementation-effort notes from OTelFeature/otelfeature-java-extension#21 is recorded.

### Failure Postconditions

- _None: the slide brackets stay empty until a reproducible table exists._

## Business Rules

### BR-001: Measure at the service

Savings are measured where the data is born: container CPU and memory and the service's own export volume, not backend ingest.

### BR-002: Net of evaluation cost

Reported savings include the cost of the targeted flag evaluation (NFR-005).

### BR-003: Reproducibility

Two runs of the same preset agree within 10% on exported spans and bytes per service. CPU is reported as mean ± sd of 5 s samples; a difference counts only beyond the run-to-run noise, the largest CPU difference among `geocode`'s identically configured runs in the same report (its baseline, no-op and Demo 2 runs in the two Java modes; the mode is Java-only). Memory is reported as a mean and not compared (NFR-011; softened by Simon, 2026-10-16, OQ-15).

### BR-004: Script wording follows the decision

D3 is decided: `processor` (OQ-1, Simon, 2026-10-16; to confirm with Juliano, OTelFeature/poc#84). The Demo 2 line is "never batched, never serialized, never sent". Sampler mode would have meant "never recorded" (non-recording spans still cost the instrumentation and context work).

### BR-005: Traffic source

The measurement does not depend on OTelFeature/poc#23 (deferred). It uses the stack's normal traffic plus the k6 `healthchecks` scenario (OQ-5, OTelFeature/poc#38, PR OTelFeature/poc#40).

### BR-006: Decision cost from a targeted no-op rule

The decision cost is measured at the service like the savings: a run with a `recordSpan` rule that reads a span attribute but never matches makes both extensions decide every span with a built context, and drops nothing. Its CPU minus the baseline's CPU in the same Java mode is the cost of the targeted path, reported as % of one core and as µs per span (that CPU difference divided by the spans decided), so it compares with the extensions' micro-benchmarks (NFR-005).

### BR-007: What each number is

- **CPU:** the container's CPU time in percent of one core over the measurement window, with the standard deviation of 5 s samples (Docker stats).
- **Memory:** the container's memory usage minus inactive file cache, averaged over the window, in MB (what `docker stats` shows; not the process RSS).
- **Requests per second:** the service's business requests (server spans not on `/health`, which no rule drops). Every run must show the same load; the report warns when it differs by more than 5%.
- **Spans per second:** spans of the service instance (`service.instance.id`) that reached the collector in the window.
- **Export bytes per second:** the size of those spans as the OTLP protobuf the service sends (`ResourceSpans`, before compression).
- Each run starts from freshly created `geocode`, `weather` and load generator, and warms up with the same traffic, so caches and JIT are settled the same way in every run. The services run with the stage's settings (export batching, error-rate window, stub latency). The traffic is the stage's normal load (BR-005) unless the operator raises it (`BENCH_RATE`).
