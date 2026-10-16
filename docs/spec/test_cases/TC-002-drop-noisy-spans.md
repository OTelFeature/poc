# Test Case: Drop health-check and database spans by rule

## Overview

- **ID:** TC-002
- **Goal:** The operator applies the Demo 2 rules and verifies that `geocode` health-check traces and `weather` database spans are no longer created, all other spans remain correctly parented, and removing the rules restores everything.
- **Priority:** Critical
- **Status:** Passed

## Roles

- Operator: applies and removes the rules.

## Preconditions

- Extension code in the pinned released versions (C-006: otelfeature-instrument v0.3.0, otelfeature-java-extension v0.4.0; a git ref only when passed explicitly to the e2e suite, C-013) containing OTelFeature/otelfeature-instrument#7 and OTelFeature/otelfeature-java-extension#20 (context), OTelFeature/otelfeature-instrument#14 and OTelFeature/otelfeature-java-extension#27 (`recordSpan`) and, for sampler mode, OTelFeature/otelfeature-java-extension#21.
- Context shape fixed by OTelFeature/poc#22.
- Health-check traffic reaches `geocode` (source: OQ-5).

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Apply rules | Apply the quiet-noise preset | `recordSpan` targeting. Rule A: `service.name=geocode`, `span.kind=server`, `url.path=/health` → `false`; rule B: `service.name=weather`, `otel.scope.name`=JDBC instrumentation scope → `false` | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 2 | Verify geocode | No new `geocode` `/health` traces; `/geocode` traces unchanged | - | - |
| 3 | Verify weather | New `/weather` traces contain server and HTTP client spans and no database spans; no orphaned parents | - | - |
| 4 | Remove rules | Apply the baseline preset | baseline `flagd.json` | [UC-002](../use_cases/UC-002-drop-noisy-spans.md) |
| 5 | Verify restore | Health-check traces and database spans reappear within 2 s | - | - |

## Validation

1. **Contract (OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20):** a flagd FILE-resolver unit test resolves the rule `service.name == "weather" && span.kind == "server" && url.path == "/health"` differently for a health span and a `/weather` span.
2. **Trace-consistent bucketing:** `fractional` on `targetingKey` yields the same bucket for two spans of the same trace.
3. **Static path (NFR-003):** with no targeting, the decision allocates no evaluation context (allocation test or benchmark).
4. **Both Java modes (OTelFeature/otelfeature-java-extension#21):** the same behavioural tests for health-check roots and database leaf spans pass in `processor` and `sampler` mode; in sampler mode a dropped span never reaches any processor's `onStart`; unknown or erroring flag → delegate. [e2e, partly: `test_tc002_drop_noisy_spans` and `test_tc002_sampler_paths` in both matrix modes; the `onStart` and delegate parts stay in the Java unit tests]
5. **Start-time only (D6):** the extension READMEs list the contract keys and state that `http.route` and `http.response.status_code` are not available.
6. **Per-tracer decision (OTelFeature/poc#12):** a Python rule on resource and scope keys only is decided once per tracer and redone on configuration change; rules with span keys, `targetingKey`/`fractional` or `otelfeature.*` are evaluated per span; `missing_some` lists count as reads; setting an OpenFeature global or transaction context, or API-level hooks, falls back to per span.
7. **Decision cost:** per-span evaluation cost measured once per language and noted in the README.
8. **Context collisions (OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20):** a leaf/prefix collision (`db.system` and `db.system.name`) keeps the namespace in either order; a start attribute named `service.name`, `span.kind` or `otel.scope.name` does not override the extension's value; a start attribute under `otelfeature.*` is ignored; `targetingKey` equals the trace id.
9. **Remote-parent entry span is a root (OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27):** a matching `SERVER` or `CONSUMER` span with a remote sampled parent produces no spans in the service, and outgoing calls carry `sampled=0`. `INTERNAL` and `CLIENT` spans with a remote parent are treated as non-roots. [e2e, partly: `test_tc002_drop_noisy_spans`, see item 17; `test_tc002_sampler_paths` checks that the dropped entry span takes its downstream calls along]
10. **Python root vs non-root (OTelFeature/otelfeature-instrument#14):** a dropped root yields a non-recording span with a valid, non-sampled context (for both `start_as_current_span` and `start_span`); a dropped non-root is suppressed alone and its children attach to the real parent.
11. **Java modes (OTelFeature/otelfeature-java-extension#27):** in sampler mode a root or database leaf matching `recordSpan=false` never reaches `onStart`; a matching mid-trace span keeps `sampled=1` and is suppressed by the processor; a rule on `otel.scope.name` is enforced by the processor. In processor mode every match is suppressed at `onStart`. [e2e, partly: `test_tc002_sampler_paths`, the root and leaf drops in both modes; `onStart` and the scope rule stay in the Java unit tests]
12. **Precedence (OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27):** `recordSpan=true` does not re-enable spans while `otelEnabled=false`, `telemetryLevel=OFF` or a hard floor applies; `recordSpan` is not evaluated then.
13. **Fail open and static path (OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27):** a ruleset without `recordSpan`, a provider error or a non-boolean value records the span; a static or missing `recordSpan` adds no per-span evaluation.
14. **Known Java edge documented (OTelFeature/otelfeature-java-extension#27):** the README states that with a non-parent-based sampler children of a dropped root are sampled as orphans.
15. **Health checks gone, exactly (OTelFeature/poc#35):** with the quiet-noise preset, the collector exports no `geocode` `/health` span; `/geocode` traces are unchanged. [e2e: `test_tc002_drop_noisy_spans`]
16. **Database spans gone, tree intact (OTelFeature/poc#35):** new `weather` traces contain the server and HTTP client spans and no database spans, and every parent id resolves within the trace (no orphans). The baseline preset brings back both the health-check and the database spans. [e2e: `test_tc002_drop_noisy_spans`]
17. **Proxied health check (OTelFeature/poc#35):** a `/health` request that arrives with a sampled `traceparent` leaves no spans in `geocode`, because a remote-parent entry span counts as a root. [e2e: `test_tc002_drop_noisy_spans`]
18. **Flip latency (OTelFeature/poc#35, NFR-004):** after applying and removing the preset, a probe request shows the new behaviour within the poll timeout. [e2e: `test_tc002_drop_noisy_spans`]

## Postconditions

- Flags back at baseline.

## Automation

- **Tests:** `test_tc002_drop_noisy_spans` and `test_tc002_sampler_paths` in `tests/e2e/` (OTelFeature/poc#35, phase 3). Needs the `recordSpan` code in both extensions, the presets (OTelFeature/poc#26) and health-check traffic (OQ-5).
- **How:** applies the `02-quiet-noise` preset, then the baseline; the test sends its own `/health`, `/geocode` and `/weather` requests (load generator off) and reads every exported span from the collector's `file` exporter.
- **Matrix:** runs in both Java enforcement modes (`processor`, `sampler`).
- **Extension code:** the pinned released versions (C-006): otelfeature-instrument v0.3.0, otelfeature-java-extension v0.4.0. A git ref can be passed explicitly to check unreleased extension code (C-013).
- **Not automated:** items 1 to 3, 5 to 8, 10 and 12 to 14 are extension unit tests, benchmarks or docs checks; item 11 is partly automated (`test_tc002_sampler_paths`).
