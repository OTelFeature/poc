# Use Case: See flag evaluations in the trace

## Overview

**Use Case ID:** UC-007  
**Use Case Name:** See flag evaluations in the trace  
**Primary Actor:** Operator  
**Secondary Actors:** weather, geocode, Aspire dashboard  
**Goal:** Looking at one failed trace, the operator sees the application flag evaluation that caused the failure, recorded by the OpenFeature OpenTelemetry hook, so that the trace explains the incident. The telemetry extensions add nothing of their own to spans (opt-in debugging hook: BR-002).  
**Status:** Draft  
**Requirements:** FR-014, FR-015, NFR-006, NFR-008  
**Work Items:** OTelFeature/poc#30, OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23 (closed as not planned, 2026-10-16: the extension writes no decision attributes, FR-014)  
**Test Cases:** TC-005  
**Script Beat:** Demo 3 ("the flag explains itself"; wording open, OQ-9)  
**Open Questions:** OQ-4, OQ-9  

## Preconditions

- UC-005 is running: `weather` fails a share of requests and samples at 1.0.
- `weather` and `geocode` register the OpenFeature OpenTelemetry hooks for their own flag evaluations.
- `OTELFEATURE_OPENFEATURE_TRACING_HOOK` is not set (the default).

## Main Success Scenario

1. The operator opens a failed `/weather` trace in the dashboard.
2. The `/weather` span shows a flag-evaluation event for `weatherUpstreamFailure` with the flag key, the variant and the provider name.
3. The operator reads from the trace which flag made the request fail.
4. No span in the trace carries attributes written by the telemetry extensions: no `feature_flag.*` attributes, no `otelfeature.sample_ratio`, and no tracestate `ot=th`.

## Alternative Flows

### A1: Hook emits older attribute names

**Trigger:** The pinned hook version does not emit the current `feature_flag` semantic conventions (step 2).

**Flow:**

1. The operator sees the evaluation under the older names; the names per SDK version are recorded in OTelFeature/poc#30 and the script is adjusted.
2. Use case continues at step 3.

## Postconditions

### Success Postconditions

- A failed trace shows the cause flag.
- The extensions added nothing to the export (NFR-006).

### Failure Postconditions

- _None: missing events leave the trace as it is without the hook._

## Business Rules

### BR-001: The extensions write no decision attributes

The extensions write no `feature_flag.*` attributes, no `otelfeature.sample_ratio` and no tracestate `ot=th` (FR-014). Recording flag evaluations is the OpenFeature OpenTelemetry hook's job.

### BR-002: Hook for the extension's own evaluations is opt-in only

`OTELFEATURE_OPENFEATURE_TRACING_HOOK=true` is never the default, because a targeted flag adds up to one event per span; it is meant to be switched on for debugging and off again. Each targeted evaluation of the extension's flags adds a `feature_flag.evaluation` event (BR-003). Evaluation errors are not recorded as exceptions on application spans. Only the Python extension has this hook ([configuration](../entity_model.md#configuration)). The Java extension has none (OTelFeature/otelfeature-java-extension#23, closed as not planned) and ignores the variable, so `weather` adds no event. Debugging a telemetry rule with this hook is a rule of this use case, not a flow of it, because its goal differs (decided by Simon, 2026-10-16).

### BR-003: Where hook events land

The hook writes to the span current at evaluation time: the parent of the span being decided. Decisions for new roots (including every `traceSampleRatio` decision) and for dropped spans record nothing, because there is no current span to write to or it is not exported.

### BR-004: Attribute names

Application evaluations: the `feature_flag.evaluation` event with `feature_flag.key`, `feature_flag.result.variant`, `feature_flag.provider.name`, if the pinned hooks emit them (OQ-4).

### BR-005: Script line

The Demo 3 line "when someone asks why did we stop collecting this, the answer is in the trace" no longer holds for telemetry decisions. Recommended rewording, not yet decided (OQ-9): "the flag decisions show up in your traces", demonstrated with `weatherUpstreamFailure` (OTelFeature/poc#30).
