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
- Extension releases with OTelFeature/otelfeature-instrument#8 / OTelFeature/otelfeature-java-extension#22 (error rate) and OTelFeature/otelfeature-instrument#9 (opt-in tracing hook).
- The demo stack sets `OTEL_SEMCONV_STABILITY_OPT_IN=http` for `geocode` (the extension does not set it).
- `OTELFEATURE_OPENFEATURE_TRACING_HOOK` is not set.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Reset | Start from the reset command | `make demo-reset` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 2 | Inject failure | Apply the incident preset | `weatherUpstreamFailure` → 0.3 | [UC-006](../use_cases/UC-006-inject-upstream-failures.md) |
| 3 | Verify errors | Error spans for `/weather` in Aspire within 2 s | - | - |
| 4 | Loop reacts | `weather` error rate above 0.05 within one to two collections | interval 10 s, at least 10 requests per interval | [UC-005](../use_cases/UC-005-raise-sampling-on-errors.md) |
| 5 | Verify sampling | `weather` trace volume at 100% of requests; `geocode` unchanged | - | - |
| 6 | Read the trace | Open a failed `/weather` trace | - | [UC-007](../use_cases/UC-007-see-flag-evaluations-in-trace.md) |
| 7 | Verify explanation | Span event for `weatherUpstreamFailure` on the `/weather` span; no span carries attributes written by the extensions | - | - |
| 8 | Revert | Set the failure flag back | `weatherUpstreamFailure` → 0.0 | [UC-006](../use_cases/UC-006-inject-upstream-failures.md) |
| 9 | Verify recovery | `weather` back at the environment ratio after the next error-free interval | - | - |

## Validation

1. **Error rate (OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22):** unit test feeding N requests with k 5xx failures yields `k/N` in the context after the next collection; each collection is its own window.
2. **Minimum requests (OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22):** with fewer than `OTELFEATURE_ERROR_RATE_MIN_REQUESTS` (default 10) requests in an interval the key is absent, even when all of them failed. The README documents this and the one-to-two-interval lag.
3. **Metric versions (OTelFeature/otelfeature-instrument#8):** without the stable opt-in, `http.status_code >= 500` counts as an error; with `http/dup` only the stable metric counts. The README documents `OTEL_SEMCONV_STABILITY_OPT_IN=http`; the extension does not set it.
4. **Reserved key (OTelFeature/otelfeature-instrument#8):** a span start attribute `otelfeature.http.server.error_rate` does not change the context value.
5. **Export unchanged:** the OTLP metric export is identical with and without the extra reader.
6. **Sampling-independent:** sampling spans at 0.0 does not change the measured error rate.
7. **Fault injection (OTelFeature/poc#28):** errors visible in spanmetrics with `status.code=ERROR`; reverting stops them.
8. **Hooks (OTelFeature/poc#30):** exact attribute names per pinned SDK version recorded in the issue.
9. **No decision attributes (OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23):** under any flag state, including a sampled root under `traceSampleRatio=0.1`, the extensions write no `feature_flag.*` attribute, no `otelfeature.sample_ratio` and no tracestate `ot=th`.
10. **Opt-in hook (OTelFeature/otelfeature-instrument#9):** with `OTELFEATURE_OPENFEATURE_TRACING_HOOK=true`, a targeted evaluation for a child span adds a `feature_flag.evaluation` event to its parent; an evaluation for a new root adds nothing; evaluation errors add no exception event. Without the variable, no event is added. The README states the caveat.
11. **Repeatable (OTelFeature/poc#29):** steps 1 to 9 pass three times in a row.
12. **Metrics export off (OTelFeature/otelfeature-instrument#15, OTelFeature/otelfeature-java-extension#31):** with `OTEL_METRICS_EXPORTER=none`, no error-rate reader is registered, the context never contains `otelfeature.http.server.error_rate` and the control-loop rule never matches; `none` mixed with another exporter logs a warning and keeps exporting (FR-024).
13. **Loop end to end (OTelFeature/poc#35):** with `weatherUpstreamFailure=1.0`, `weather` samples at 1.0 within a bounded number of error-rate intervals; `geocode` sampling does not change; after the revert, `weather` returns to its baseline ratio. [e2e: `test_tc005_control_loop`]

## Postconditions

- Flags back at baseline; no injected failures.

## Automation

- **Test:** `test_tc005_control_loop` in `tests/e2e/` (OTelFeature/poc#35, phase 4). Needs the fault-injection flag (OTelFeature/poc#28), the control-loop preset (OTelFeature/poc#29) and the error-rate code in both extensions.
- **How:** differs from the stage flow so it runs fast and deterministically: the failure fraction is 1.0 instead of 0.3, and the e2e override sets a short `OTELFEATURE_ERROR_RATE_INTERVAL` and a low `OTELFEATURE_ERROR_RATE_MIN_REQUESTS`. The test sends its own requests (load generator off).
- **Matrix:** runs in both Java enforcement modes (`processor`, `sampler`).
- **Extension code:** built from git refs until the releases in the preconditions exist (C-013).
- **Not automated:** items 1 to 12; steps 6 and 7 (reading the trace) stay manual. Item 11 is covered for the suite as a whole by NFR-015 (three green runs in a row), not for the stage timings.

## Notes

- Step 7 shows the application's flag, not the telemetry decision. The script line for this beat is open (OQ-9).
