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
- Extension code (a release on the stage stack, C-006; each extension's `main` or another git ref in the end-to-end suite, C-013) containing OTelFeature/poc#10 in both languages.
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
2. **Clamping (OTelFeature/poc#10, OTelFeature/otelfeature-instrument#22):** a value above 1.0 clamps to 1.0; a negative value, NaN, infinity or a non-number falls back to the startup ratio, logged once; no exception on the hot path.
3. **Parent-based consistency (OTelFeature/poc#10):** decisions are consistent within one trace.
4. **Environment from service (OTelFeature/poc#25):** the collector only inserts `deployment.environment.name` when missing; a rule on it affects only matching instances. [e2e, partly: `test_baseline` checks that the resource carries the key; `test_tc004_target_sampling` checks that a rule on it affects only matching instances]
5. **Docs (OTelFeature/poc#10):** READMEs document the entry-point caveat and the `jaeger_remote` comparison.
6. **Trace roots only (OTelFeature/poc#10):** only trace roots evaluate `traceSampleRatio`; a span with a parent (local or remote) follows the parent's decision, and a mid-trace flip does not split a trace.
7. **Cross-service consistency (OTelFeature/poc#10):** two services in the same language with the same ratio make the same decision for the same trace id; `fractional` variants bucket on the trace id, the same in every language. The READMEs document that the plain ratio can differ between Java and Python for the same trace id (UC-004 BR-008).
8. **Hard floors (OTelFeature/poc#10):** with `OTEL_TRACES_SAMPLER=always_off`, `traceSampleRatio=1.0` samples nothing, and a sampled parent is not followed; with `parentbased_always_off`, no root is sampled locally and sampled parents are followed. [e2e, partly: `test_hard_floors` covers `always_off`]
9. **Unknown sampler name (Python, OTelFeature/poc#10):** an unknown `OTEL_TRACES_SAMPLER` (for example `jaeger_remote`) logs a warning and uses 1.0 as the startup ratio.

10. **Deterministic ratios (OTelFeature/poc#35):** with production at `traceSampleRatio=0.0` and staging at 1.0, no new root trace is exported from a production instance and every staging request produces a trace. [e2e: `test_tc004_target_sampling`]
11. **Statistical ratio (OTelFeature/poc#35):** at 0.5, 200 requests produce a sampled share within a tolerance band. [e2e: `test_tc004_target_sampling`, marked `slow`, nightly only]

## Postconditions

- Flags back at baseline; staging profile may be stopped.

## Automation

- **Test:** `test_tc004_target_sampling` in `tests/e2e/` (OTelFeature/poc#35, phase 4). Needs the production and staging instances (OTelFeature/poc#25) and the ratio code in both extensions.
- **How:** CI asserts only deterministic ratios (0.0 and 1.0); the 0.1 and 0.5 volumes of steps 3 and 5 are not asserted. The statistical case at 0.5 runs nightly.
- **Matrix:** runs in both Java enforcement modes (`processor`, `sampler`).
- **Extension code:** built from git refs (each extension's `main`, where both chains are merged) until the releases in the preconditions exist (C-013).
- **Not automated:** items 1 to 3, 5 to 7 and 9 are extension unit tests or docs checks. Step 6 waits for the cross-service path (OTelFeature/poc#59); once it exists, the e2e test asserts completeness only, not the 10% volume.
