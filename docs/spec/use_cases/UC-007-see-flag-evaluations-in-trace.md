# Use Case: See flag evaluations in the trace

## Overview

**Use Case ID:** UC-007  
**Use Case Name:** See flag evaluations in the trace  
**Primary Actor:** Operator  
**Secondary Actors:** weather, Aspire dashboard  
**Goal:** Looking at one failed trace, the operator sees the application flag evaluation that caused the failure, recorded by the OpenFeature OpenTelemetry hook, so that the trace explains the incident. The telemetry extensions add nothing of their own to spans (opt-in debugging hook: BR-002).  
**Status:** Draft  
**Requirements:** FR-014, FR-015, NFR-006, NFR-008  
**Work Items:** OTelFeature/poc#30, OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23 (closed as not planned, 2026-10-16: the extension writes no decision attributes, FR-014)  
**Test Cases:** TC-005  
**Script Beat:** Demo 3 ("the flag explains itself"; wording open, OQ-9)  
**Open Questions:** OQ-9 (OQ-4 answered: BR-004)  

## Preconditions

- UC-005 is running: `weather` fails a share of requests and samples at 1.0.
- `weather` registers the OpenFeature OpenTelemetry traces hook on its own OpenFeature client, so only the application's evaluations are recorded (BR-006). `geocode` evaluates no application flags and registers none.
- `OTELFEATURE_OPENFEATURE_TRACING_HOOK` is not set (the default).

## Main Success Scenario

1. The operator opens a failed `/weather` trace in the dashboard.
2. A span of the failed `/weather` request shows a flag-evaluation event for `weatherUpstreamFailure` with the flag key, the variant and the provider name (names: BR-004).
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

`OTELFEATURE_OPENFEATURE_TRACING_HOOK=true` is never the default, because a targeted flag adds up to one event per span; it is meant to be switched on for debugging and off again. Each targeted evaluation of the extension's flags adds a flag-evaluation event (BR-003), under the names of the hook version it uses (BR-004: the pinned Python hook uses the current names). Evaluation errors are not recorded as exceptions on application spans. Only the Python extension has this hook ([configuration](../entity_model.md#configuration)). The Java extension has none (OTelFeature/otelfeature-java-extension#23, closed as not planned) and ignores the variable, so `weather` adds no event. Debugging a telemetry rule with this hook is a rule of this use case, not a flow of it, because its goal differs (decided by Simon, 2026-10-16).

### BR-003: Where hook events land

The extension's opt-in hook writes to the span current at evaluation time: the parent of the span being decided. Decisions for new roots (including every `traceSampleRatio` decision) and for dropped spans record nothing, because there is no current span to write to or it is not exported.

### BR-004: Attribute names

Target: the `feature_flag.evaluation` event with `feature_flag.key`, `feature_flag.result.variant` and `feature_flag.provider.name` (current semantic conventions). Verified for the pinned hook (OQ-4, OTelFeature/poc#30): `dev.openfeature.contrib.hooks:otel` 3.3.1 (Java, the only application hook in the demo) emits the **older** names from semantic conventions 1.28: an event named `feature_flag` with `feature_flag.key`, `feature_flag.variant` and `feature_flag.provider_name`. So alternative flow A1 applies until a hook release with the current names is pinned. The event lands on the span current when `weather` evaluates the flag: the `/weather` request's server span. The Python hook `openfeature-hooks-opentelemetry` 0.3.1 (what otelfeature-instrument pins for its opt-in hook, BR-002) already emits the current names: `feature_flag.evaluation`, `feature_flag.key`, `feature_flag.result.variant`, `feature_flag.provider.name`. If an evaluation fails, the Java hook records an exception event on the current span and leaves its status unchanged.

### BR-005: Script line

The Demo 3 line "when someone asks why did we stop collecting this, the answer is in the trace" no longer holds for telemetry decisions. Recommended rewording, not yet decided (OQ-9): "the flag decisions show up in your traces", demonstrated with `weatherUpstreamFailure` (OTelFeature/poc#30).

### BR-006: Hook on the application's client, never global in `geocode`

`weather` adds the traces hook to its own OpenFeature client; the Java extension's evaluations run in its isolated OpenFeature API (NFR-009) and are not affected. `geocode` registers no hook: it evaluates no application flags, and a global hook in the Python process would also record the extension's own per-span evaluations, which BR-002 keeps opt-in.
