# Use Case: Explain a telemetry decision from the trace

## Overview

- **Use Case ID:** UC-007
- **Use Case Name:** Explain a telemetry decision from the trace
- **Primary Actor:** Operator
- **Secondary Actors:** weather, geocode, Aspire dashboard
- **Goal:** Looking at one trace, the operator sees which flag evaluations shaped it: the application flag that caused the failure and the telemetry flag and sample ratio that kept the trace, so that the trace explains itself and counts can be re-weighted.
- **Status:** Draft
- **Requirements:** FR-014, FR-015, NFR-006, NFR-008
- **Work Items:** OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23, OTelFeature/poc#30
- **Test Cases:** TC-005
- **Script Beat:** Demo 3 ("the flag explains itself")
- **Open Questions:** OQ-4

## Preconditions

- UC-005 is running: `weather` fails a share of requests and samples at 1.0.
- `weather` and `geocode` register the OpenFeature OpenTelemetry hooks for their own flag evaluations.

## Main Success Scenario

1. The operator opens a failed `/weather` trace in the dashboard.
2. The `/weather` span shows a flag-evaluation event for `weatherUpstreamFailure` with the flag key, the variant and the provider name.
3. The root span shows the telemetry decision: the flag key `traceSampleRatio`, the variant, and the applied ratio as `otelfeature.sample_ratio`.
4. The operator reads from the trace why it was failing and why it was kept.

## Alternative Flows

### A1: Everything at defaults

**Trigger:** Step 3, all telemetry flags resolve to their defaults.

**Flow:**

1. No decision attributes are added to any span.
2. Use case ends.

### A2: Hook emits older attribute names

**Trigger:** Step 2, the pinned hook version does not emit the current `feature_flag` semantic conventions.

**Flow:**

1. The operator sees the evaluation under the older names; the names per SDK version are recorded in OTelFeature/poc#30 and the script is adjusted.
2. Use case continues at step 3.

## Postconditions

### Success Postconditions

- A failed trace shows both the cause flag and the telemetry decision.

### Failure Postconditions

- _None: missing attributes leave the trace as it is without the extension._

## Business Rules

### BR-001: Root spans only

Decision attributes are added to kept root spans only, and only for a non-default decision.

### BR-002: Attribute names

Decision attributes: `feature_flag.key`, `feature_flag.result.variant`, `otelfeature.sample_ratio`. Application evaluations: the `feature_flag.evaluation` event with `feature_flag.key`, `feature_flag.result.variant`, `feature_flag.provider.name`, if the pinned hooks emit them (OQ-4).

### BR-003: No cost at defaults

On the static default path no attributes are added (NFR-008).
