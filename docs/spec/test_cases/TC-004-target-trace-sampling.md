# Test Case: Sample traces by environment and service

## Overview

- **ID:** TC-004
- **Goal:** With production and staging instances running, the operator sets `traceSampleRatio` rules by `deployment.environment.name` and `service.name` and verifies the sampled volume per instance and that sampled traces are complete across services.
- **Priority:** Critical
- **Status:** Draft

## Roles

- Operator: applies the semconv-rules and weather-boost presets.

## Preconditions

- `docker compose --profile staging up` runs four service instances (OTelFeature/poc#25).
- Extension code in the pinned released versions (C-006: otelfeature-instrument v0.4.0, otelfeature-java-extension v0.5.0; a git ref only when passed explicitly to the e2e suite, C-013) containing OTelFeature/poc#10 in both languages.
- The cross-service path (FR-026, OTelFeature/poc#59) for step 6.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Check resource | Spans in Aspire carry the environment set by the service | `production`, `staging` | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 2 | Apply env rule | Apply the semconv-rules preset | production → 0.1, else 1.0 | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 3 | Verify volume | Production trace volume about 10% of requests; staging 100% | - | - |
| 4 | Apply service rule | Apply the weather-boost preset: adds `weather` production → 0.5 | `03a-weather-boost`, `service.name=weather` | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 5 | Verify volume | Production traces that start in `weather` about 50%; `geocode` production about 10% | - | - |
| 6 | Verify completeness | Every sampled cross-service trace contains spans from both services; its sampling follows `geocode` (about 10% in production), not `weather`'s 0.5 | cross-service path | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |

## Validation

1. **Flag defined (OTelFeature/poc#10):** `traceSampleRatio` exists in `src/flagd/flagd.json`, default 1.0.
2. **Clamping (OTelFeature/poc#10, OTelFeature/otelfeature-instrument#22):** a value above 1.0 clamps to 1.0; a negative value, NaN, infinity or a non-number falls back to the startup ratio, logged once per state change; no exception on the hot path.
3. **Parent-based consistency (OTelFeature/poc#10):** decisions are consistent within one trace. [e2e, partly: `test_tc004_cross_service`, across services]
4. **Environment from service (OTelFeature/poc#25):** the collector only inserts `deployment.environment.name` when missing; a rule on it affects only matching instances. [e2e, partly: `test_baseline` checks that the resource carries the key; `test_tc004_target_sampling` checks that a rule on it affects only matching instances]
5. **Docs (OTelFeature/poc#10):** READMEs document the entry-point caveat and the `jaeger_remote` comparison.
6. **Trace roots only (OTelFeature/poc#10):** only trace roots evaluate `traceSampleRatio`; a span with a parent (local or remote) follows the parent's decision, and a mid-trace flip does not split a trace. [e2e, partly: `test_tc004_cross_service`, across services]
7. **Cross-service consistency (OTelFeature/poc#10):** two services in the same language with the same ratio make the same decision for the same trace id; `fractional` variants bucket on the trace id, the same in every language. The READMEs document that the plain ratio can differ between Java and Python for the same trace id (UC-004 BR-008).
8. **Hard floors (OTelFeature/poc#10):** with `OTEL_TRACES_SAMPLER=always_off`, `traceSampleRatio=1.0` samples nothing, and a sampled parent is not followed; with `parentbased_always_off`, no root is sampled locally and sampled parents are followed. [e2e, partly: `test_hard_floors` covers `always_off`]
9. **Unknown sampler name (Python, OTelFeature/poc#10):** an unknown `OTEL_TRACES_SAMPLER` (for example `jaeger_remote`) logs a warning and uses 1.0 as the startup ratio.
10. **Deterministic ratios (OTelFeature/poc#35):** with production at `traceSampleRatio=0.0` and staging at 1.0, no new root trace is exported from a production instance and every staging request produces a trace. [e2e: `test_tc004_target_sampling`]
11. **Statistical ratio (OTelFeature/poc#35):** with the stage preset `03-semconv-rules` as it is (production at 0.1, UC-004 step 6), 300 root requests per production service produce between 10 and 55 sampled traces, a band that still fails on 0.0, 0.5 or 1.0. [e2e: `test_tc004_stage_preset_ratio`, marked `slow`, nightly only]

## Postconditions

- Flags back at baseline; staging profile may be stopped.

## Automation

- **Tests:** `test_tc004_target_sampling`, `test_tc004_cross_service` and `test_tc004_stage_preset_ratio` (`slow`) in `tests/e2e/` (OTelFeature/poc#35, phase 4). Needs the production and staging instances (OTelFeature/poc#25) and the ratio code in both extensions.
- **How:** CI asserts only deterministic ratios (0.0 and 1.0); the 0.1 and 0.5 volumes of steps 3 and 5 are not asserted. The statistical case, the stage preset's 0.1, runs nightly (`test_tc004_stage_preset_ratio`, item 11); until a nightly run is green, this test case stays Draft (status rule in [requirements.md](../requirements.md)).
- **Matrix:** runs in both Java enforcement modes (`processor`, `sampler`).
- **Extension code:** the pinned released versions (C-006): otelfeature-instrument v0.4.0, otelfeature-java-extension v0.5.0. A git ref can be passed explicitly to check unreleased extension code (C-013).
- **Step 6:** `test_tc004_cross_service` (OTelFeature/poc#59) asserts completeness, not the 10% volume. At baseline a `/forecast` trace has spans from both services, `weather`'s server span is a child of `geocode`'s HTTP client span, and the tree is connected. With `geocode` at 0.0 and `weather` at 1.0 in production, `/forecast` traces are absent from both services while direct `POST /weather` traces are sampled: the entry point decides (UC-004 BR-003, A2).
- **Not automated:** items 1, 2, 5, 7 and 9 are extension unit tests or docs checks; items 3 and 6 are extension unit tests and, across services, partly `test_tc004_cross_service`.
