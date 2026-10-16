# Use Case: Measure the savings of a drop rule

## Overview

- **Use Case ID:** UC-003
- **Use Case Name:** Measure the savings of a drop rule
- **Primary Actor:** Speaker
- **Secondary Actors:** OTel Collector, geocode, weather
- **Goal:** The speaker gets per-service numbers for CPU, memory, spans per second and export bytes per second, before and after the Demo 2 rules, for both Java enforcement modes, so that the slide brackets are filled with measured values and the sampler-versus-processor decision is made on data.
- **Status:** Draft
- **Requirements:** FR-016, FR-008, NFR-005, NFR-006, NFR-011, C-006
- **Work Items:** OTelFeature/poc#27, OTelFeature/otelfeature-java-extension#21
- **Test Cases:** TC-003
- **Script Beat:** Demo 2 ("CPU [X%] lower, memory [Y MB] lower, export bytes [Z%] lower"); input to decision D3
- **Open Questions:** OQ-1, OQ-3, OQ-5

## Preconditions

- Released extension versions containing the semconv context and the Java sampler are pinned in the demo stack.
- The stack runs offline with the stubbed external APIs, so the load is not limited by third-party rate limits.
- The Demo 2 preset exists (UC-008).

## Main Success Scenario

1. The speaker starts the measurement with one command.
2. The system runs the baseline preset for the configured duration and records, per service, CPU, resident memory, spans per second and export bytes per second, at the service, not at the backend.
3. The system runs the Demo 2 preset with `weather` in processor mode and records the same values.
4. The system runs the Demo 2 preset with `weather` in sampler mode and records the same values.
5. The system measures the cost of one targeted span decision in each language.
6. The system prints one table per service comparing the three runs and the decision cost.
7. The speaker records the numbers for the script brackets and the D3 recommendation in OTelFeature/poc#27.

## Alternative Flows

### A1: Runs are not reproducible

**Trigger:** Step 6, two runs of the same preset differ by more than 10% on a metric.

**Flow:**

1. The speaker extends the run duration or removes the source of variance and repeats the measurement.
2. Use case continues at step 1.

### A2: Savings are smaller than the decision cost

**Trigger:** Step 6, the targeted decision costs more CPU than the dropped spans save.

**Flow:**

1. The speaker records the result in OTelFeature/poc#27 and the script claim is changed to match the numbers.
2. Use case ends.

### A3: Live view on stage

**Trigger:** Step 1, the speaker needs the drop visible during the talk rather than as a table.

**Flow:**

1. The system shows the per-service spans per second and export bytes per second live, so the drop is visible within seconds of the flag flip.
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

### BR-004: Traffic source

The measurement does not depend on OTelFeature/poc#23 (deferred). It uses the stack's normal traffic plus whatever health-check traffic OQ-5 settles on.
