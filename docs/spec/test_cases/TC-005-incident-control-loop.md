# Test Case: Incident raises sampling for the failing service

## Overview

- **ID:** TC-005
- **Goal:** The speaker injects failures into `weather`; within one collection interval `weather` samples at 1.0 while `geocode` does not change, the failed traces show the cause flag and the telemetry decision, and reverting returns to baseline.
- **Priority:** High
- **Status:** Draft

## Roles

- Speaker: injects and removes the failure.
- Operator: reads the trace.

## Preconditions

- TC-004 preconditions; semconv-rules preset with the control-loop rule active (OTelFeature/poc#29).
- Extension releases with OTelFeature/otelfeature-instrument#8 / OTelFeature/otelfeature-java-extension#22 and #9 / #23.
- `geocode` runs with `OTEL_SEMCONV_STABILITY_OPT_IN=http`.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Reset | Start from the reset command | `make demo-reset` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 2 | Inject failure | Apply the incident preset | `weatherUpstreamFailure` → 0.3 | [UC-006](../use_cases/UC-006-inject-upstream-failures.md) |
| 3 | Verify errors | Error spans for `/weather` in Aspire within 2 s | - | - |
| 4 | Loop reacts | `weather` error rate above 0.05 at next collection | interval 10 s | [UC-005](../use_cases/UC-005-raise-sampling-on-errors.md) |
| 5 | Verify sampling | `weather` trace volume at 100% of requests; `geocode` unchanged | - | - |
| 6 | Read the trace | Open a failed `/weather` trace | - | [UC-007](../use_cases/UC-007-explain-telemetry-decision.md) |
| 7 | Verify explanation | Span event for `weatherUpstreamFailure`; root span has `feature_flag.key`, `feature_flag.result.variant`, `otelfeature.sample_ratio` | - | - |
| 8 | Revert | Set the failure flag back | `weatherUpstreamFailure` → 0.0 | [UC-006](../use_cases/UC-006-inject-upstream-failures.md) |
| 9 | Verify recovery | `weather` back at the environment ratio after the next error-free interval | - | - |

## Validation

1. **Error rate (OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22):** unit test feeding N requests with k 5xx failures yields `k/N` in the context after the next collection.
2. **Export unchanged:** the OTLP metric export is identical with and without the extra reader.
3. **Sampling-independent:** sampling spans at 0.0 does not change the measured error rate.
4. **Fault injection (OTelFeature/poc#28):** errors visible in spanmetrics with `status.code=ERROR`; reverting stops them.
5. **Hooks (OTelFeature/poc#30):** exact attribute names per pinned SDK version recorded in the issue.
6. **Decision attributes (OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23):** a sampled root span under `traceSampleRatio=0.1` carries the ratio and flag key; nothing is added at defaults.
7. **Repeatable (OTelFeature/poc#29):** steps 1 to 9 pass three times in a row.

## Postconditions

- Flags back at baseline; no injected failures.
