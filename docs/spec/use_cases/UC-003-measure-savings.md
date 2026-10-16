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
**Open Questions:** OQ-1, OQ-3, OQ-5  

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

**Trigger:** The two measurements differ by more than 10% on a metric for the same preset (step 7).

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

1. The dashboard shows the collector's span metrics per service (`traces.span.metrics.calls`, by `service.name`) live, so the drop is visible within seconds of the flag flip (BR-007).
2. Use case ends.

## Postconditions

### Success Postconditions

- A per-service table with baseline, processor mode and sampler mode exists and is recorded in OTelFeature/poc#27.
- A D3 recommendation with numbers and the implementation-effort notes from OTelFeature/otelfeature-java-extension#21 is recorded.

### Failure Postconditions

- _None: the slide brackets stay empty and D3 stays open until a reproducible table exists._

## Business Rules

### BR-001: Measure at the service

Savings are measured where the data is born: container CPU and memory and the service's own export volume, not backend ingest.

### BR-002: Net of evaluation cost

Reported savings include the cost of the targeted flag evaluation (NFR-005).

### BR-003: Reproducibility

Two runs of the same preset agree within 10% per metric (NFR-011).

### BR-004: Script wording follows the decision

Until D3 is decided (OQ-1), the Demo 2 line covers both: sampler mode means "never recorded" (non-recording spans still cost the instrumentation and context work), processor mode means "never batched, never serialized, never sent".

### BR-005: Traffic source

The measurement does not depend on OTelFeature/poc#23 (deferred). It uses the stack's normal traffic plus whatever health-check traffic OQ-5 settles on.

### BR-006: Decision cost from a targeted no-op rule

The decision cost is measured at the service like the savings: a run with a `recordSpan` rule that reads a span attribute but never matches makes both extensions decide every span with a built context, and drops nothing. Its CPU minus the baseline's CPU is the cost of the targeted path at that load; the per-span micro-benchmarks stay in the extension READMEs (NFR-005).

### BR-007: What each number is

- **CPU:** the container's CPU use in percent of one core, averaged over the measurement window (Docker stats).
- **Memory:** the container's resident memory (usage minus page cache) at the end of the window, in MB.
- **Spans per second:** spans with the service's `service.name` that reached the collector in the window.
- **Export bytes per second:** the size of those spans as the OTLP protobuf the service sends (`ResourceSpans`, before compression).
- Each run starts from a warm-up with the same traffic, so caches and JIT are settled. The traffic is the stack's normal load (TC-003 item 4) unless the operator raises it (`BENCH_RATE`).
