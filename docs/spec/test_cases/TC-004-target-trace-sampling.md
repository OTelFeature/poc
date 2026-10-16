# Test Case: Sample traces by environment and service

## Overview

- **ID:** TC-004
- **Goal:** With production and staging instances running, the operator sets `traceSampleRatio` rules by `deployment.environment.name` and `service.name` and verifies the sampled volume per instance and that sampled traces are complete across services.
- **Priority:** Critical
- **Status:** Draft

## Roles

- Operator: applies the semconv-rules preset.

## Preconditions

- `docker compose --profile staging up` runs four service instances (OTelFeature/poc#25).
- Extension releases containing OTelFeature/poc#10 in both languages.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Check resource | Spans in Aspire carry the environment set by the service | `production`, `staging` | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 2 | Apply env rule | Apply the semconv-rules preset | production → 0.1, else 1.0 | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 3 | Verify volume | Production trace volume about 10% of requests; staging 100% | - | - |
| 4 | Apply service rule | Add `weather` production → 1.0 | `service.name=weather` | [UC-004](../use_cases/UC-004-target-trace-sampling.md) |
| 5 | Verify volume | `weather` production 100%, `geocode` production about 10% | - | - |
| 6 | Verify completeness | Every sampled `geocode` → `weather` trace contains spans from both services | - | - |

## Validation

1. **Flag defined (OTelFeature/poc#10):** `traceSampleRatio` exists in `src/flagd/flagd.json`, default 1.0.
2. **Clamping (OTelFeature/poc#10):** out-of-range values clamp, non-numeric values fall back to the startup default, no exception on the hot path.
3. **Parent-based consistency (OTelFeature/poc#10):** decisions are consistent within one trace.
4. **Environment from service (OTelFeature/poc#25):** the collector only inserts `deployment.environment.name` when missing; a rule on it affects only matching instances.
5. **Docs (OTelFeature/poc#10):** READMEs document the entry-point caveat and the `jaeger_remote` comparison.
6. **Roots only (OTelFeature/poc#10):** only root spans evaluate `traceSampleRatio`; a span with a parent (local or remote) follows the parent's decision, and a mid-trace flip does not split a trace.
7. **Cross-service consistency (OTelFeature/poc#10):** two services in the same language with the same ratio make the same decision for the same trace id; `fractional` variants bucket on the trace id, the same in every language. The READMEs document that the plain ratio can differ between Java and Python for the same trace id (UC-004 BR-008).
8. **Hard floors (OTelFeature/poc#10):** with `OTEL_TRACES_SAMPLER=always_off`, `traceSampleRatio=1.0` samples nothing, and a sampled parent is not followed; with `parentbased_always_off`, no root is sampled locally and sampled parents are followed.
9. **Unknown sampler name (Python, OTelFeature/poc#10):** an unknown `OTEL_TRACES_SAMPLER` (for example `jaeger_remote`) logs a warning and uses 1.0 as the startup ratio.

## Postconditions

- Flags back at baseline; staging profile may be stopped.
