# Test Case: Incident raises sampling for the failing service

## Overview

- **ID:** TC-005
- **Goal:** The operator injects failures into `weather`; within one to two collection intervals `weather` samples at 1.0 while `geocode` does not change, the failed traces show the cause flag (`weatherUpstreamFailure`), and reverting returns `weather` to its ratio before the incident.
- **Priority:** High
- **Status:** Draft

## Roles

- Operator: injects and removes the failure, reads the trace.

## Preconditions

- TC-004 preconditions, except the cross-service path. The stage progression has reached `03a-weather-boost` (production `weather` at 0.5, UC-008 BR-006); the control-loop rule comes with `03b-incident`.
- Extension code in the pinned released versions (C-006: otelfeature-instrument v0.3.0, otelfeature-java-extension v0.4.0; a git ref only when passed explicitly to the e2e suite, C-013) with OTelFeature/otelfeature-instrument#8 / OTelFeature/otelfeature-java-extension#22 (error rate) and OTelFeature/otelfeature-instrument#9 (opt-in tracing hook).
- The demo stack sets `OTEL_SEMCONV_STABILITY_OPT_IN=http` for `geocode` (the extension does not set it).
- `OTELFEATURE_OPENFEATURE_TRACING_HOOK` is not set.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Start state | `03a-weather-boost` applied, no reset (progression) | `make flag PRESET=03a-weather-boost` | [UC-008](../use_cases/UC-008-run-demo-on-stage.md) |
| 2 | Inject failure | Apply the incident preset: the fault and the control-loop rule (OTelFeature/poc#29) | `03b-incident`, `weatherUpstreamFailure` → 0.5 (UC-006 BR-003) | [UC-006](../use_cases/UC-006-inject-upstream-failures.md), [UC-005](../use_cases/UC-005-raise-sampling-on-errors.md) |
| 3 | Verify errors | Error spans for `/weather` in Aspire within 2 s | - | - |
| 4 | Loop reacts | `weather` error rate above 0.05 within one to two collections | interval 10 s, at least 10 requests per interval | [UC-005](../use_cases/UC-005-raise-sampling-on-errors.md) |
| 5 | Verify sampling | Traces that start in `weather` at 100% of requests (from about 50%); `geocode` unchanged | - | - |
| 6 | Read the trace | Open a failed `/weather` trace | - | [UC-007](../use_cases/UC-007-see-flag-evaluations-in-trace.md) |
| 7 | Verify explanation | Span event for `weatherUpstreamFailure` on the `/weather` span; no span carries attributes written by the extensions | - | - |
| 8 | Revert | Apply the weather-boost preset again: no fault, no loop rule | `03a-weather-boost`, `weatherUpstreamFailure` → 0.0 | [UC-006](../use_cases/UC-006-inject-upstream-failures.md) |
| 9 | Verify recovery | Traces that start in `weather` back at about 50% within 2 s: the fault and the rule leave with the preset (UC-005 A6, OQ-14). The main scenario's self-release, with the rule kept, is check 13 | - | - |

## Validation

1. **Error rate (OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22):** unit test feeding N requests with k 5xx failures yields `k/N` in the context after the next collection; each collection is its own window.
2. **Minimum requests (OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22):** with fewer than `OTELFEATURE_ERROR_RATE_MIN_REQUESTS` (default 10) requests in an interval the key is absent, even when all of them failed. The README documents this and the one-to-two-interval lag.
3. **Metric versions (OTelFeature/otelfeature-instrument#8):** without the stable opt-in, `http.status_code >= 500` counts as an error; with `http/dup` only the stable metric counts. The README documents `OTEL_SEMCONV_STABILITY_OPT_IN=http`; the extension does not set it.
4. **Reserved key (OTelFeature/otelfeature-instrument#8):** a span start attribute `otelfeature.http.server.error_rate` does not change the context value.
5. **Export unchanged:** the OTLP metric export is identical with and without the extra reader.
6. **Sampling-independent:** sampling spans at 0.0 does not change the measured error rate.
7. **Fault injection (OTelFeature/poc#28):** errors visible in spanmetrics with `status.code=ERROR`; reverting stops them. Values outside 0.0 to 1.0, NaN and non-numbers behave as UC-006 BR-002 and A2 (code review of `FaultInjection`; no test yet).
8. **Hooks (OTelFeature/poc#30):** exact attribute names per pinned SDK version recorded in the issue.
9. **No decision attributes (OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23):** under any flag state, including a sampled root under `traceSampleRatio=0.1`, the extensions write no `feature_flag.*` attribute, no `otelfeature.sample_ratio` and no tracestate `ot=th`.
10. **Opt-in hook, Python only (OTelFeature/otelfeature-instrument#9):** on `geocode`, with `OTELFEATURE_OPENFEATURE_TRACING_HOOK=true`, a targeted evaluation for a child span adds a `feature_flag.evaluation` event to its parent; an evaluation for a new root adds nothing; evaluation errors add no exception event. Without the variable, no event is added. The README states the caveat. On `weather` (Java) the variable adds no event (UC-007 BR-002).
11. **Repeatable (OTelFeature/poc#29):** steps 1 to 9 pass three times in a row.
12. **Metrics export off (OTelFeature/otelfeature-instrument#15, OTelFeature/otelfeature-java-extension#31):** with `OTEL_METRICS_EXPORTER=none`, no error-rate reader is registered, the context never contains `otelfeature.http.server.error_rate` and the control-loop rule never matches; `none` mixed with another exporter logs a warning and keeps exporting (FR-024).
13. **Loop end to end (OTelFeature/poc#35):** with `weatherUpstreamFailure=1.0`, `weather` samples at 1.0 within a bounded number of error-rate intervals; `geocode` sampling does not change; after reverting only `weatherUpstreamFailure` (the rule stays), `weather` returns to its ratio before the incident after an error-free interval (UC-005 steps 6 to 8, the loop letting go on its own). [e2e: `test_tc005_control_loop`]

## Note on the stage preset

On stage, `03b-incident` builds on `03a-weather-boost` (UC-008 BR-006), which sets `weather` to 0.5. The check is therefore a rise from 0.5 to 1.0 while the fault is active and a return to 0.5 after it, from the stage preset itself, with no reset.

## Postconditions

- Flags at `03a-weather-boost`; no injected failures.

## Automation

- **Test:** `test_tc005_control_loop` in `tests/e2e/` (OTelFeature/poc#35, phase 4). Needs the fault-injection flag (OTelFeature/poc#28), the control-loop preset (OTelFeature/poc#29) and the error-rate code in both extensions.
- **How:** differs from the stage flow so it runs fast and deterministically: the failure fraction is 1.0 instead of 0.5, and the e2e override sets a short `OTELFEATURE_ERROR_RATE_INTERVAL` and a low `OTELFEATURE_ERROR_RATE_MIN_REQUESTS`. The test sends its own requests (load generator off).
- **Matrix:** runs in both Java enforcement modes (`processor`, `sampler`).
- **Extension code:** the pinned released versions (C-006): otelfeature-instrument v0.3.0, otelfeature-java-extension v0.4.0. A git ref can be passed explicitly to check unreleased extension code (C-013).
- **Not automated:** items 1 to 12; steps 6 and 7 (reading the trace) stay manual. Item 11 is covered for the suite as a whole by NFR-015 (three green runs in a row), not for the stage timings.

## Notes

- Step 7 shows the application's flag, not the telemetry decision. The script line for this beat is open (OQ-9).
