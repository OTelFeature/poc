# Requirements Catalog

Derived from [vision.md](vision.md). Inception artifact.

- **Scope:** spans and traces only. Metrics appear only as an input
  (FR-011). Metrics and logs gating is deferred (FR-022).
- **Baseline:** `poc` @ `404d54d`, `otelfeature-instrument` @ `9dd4488`
  (v0.2.0), `otelfeature-java-extension` @ `f20c07c` (v0.3.1).
- **Priority:** High = the demo arc cannot be performed without it (backlog
  P0). Medium = a script line is false or a bracket stays empty without it
  (P1). Low = nice to have or post-talk (P2).
- **Status:** Open, In Progress, Implemented, Verified, Deferred, Rejected.
- Which issue implements which requirement is in
  [traceability.md](traceability.md). Issue refs are given here only where the
  requirement *is* the issue.

Roles used in the user stories:

- **Operator**: whoever manages the flags for a service (SRE, platform
  engineer, or the speaker on stage).
- **Speaker**: Simon or Juliano, performing the demo.
- **Adopter**: someone running the extensions or the demo after the talk.

## Functional Requirements

| ID | Title | User Story | Priority | Status |
|---|---|---|---|---|
| FR-001 | Boolean tracing kill switch | As an operator, I want a boolean flag `otelEnabled` that turns span creation off and on in every service at runtime, so that I can stop span ingest during an incident without a redeploy. | High | Open |
| FR-002 | `OFF` variant of `telemetryLevel` | As an operator who already manages `telemetryLevel`, I want an `OFF` variant that behaves exactly like `otelEnabled=false`, so that I don't need a second flag for the kill switch. | High | Open |
| FR-003 | Suppress `INTERNAL` spans | As an operator, I want `telemetryLevel=IO` to drop `INTERNAL` spans and keep the trace tree connected, so that traces show only the I/O boundary. | High | Verified |
| FR-004 | One telemetry policy per decision | As a maintainer, I want every flag read collapsed into one `TelemetryPolicy` resolved once per decision point, so that each new flag costs one field and failure handling lives in one place. | High | Open |
| FR-005 | Evaluation context from semantic conventions | As an operator, I want flag targeting rules to see the span's resource, instrumentation scope and start attributes under their semconv names, so that I can write rules like `service.name == "weather" && url.path == "/health"`. | High | Open |
| FR-006 | Drop root spans by rule before creation | As an operator, I want a targeting rule to drop matching root spans (for example health checks in one service) before they are created, so that the service doesn't pay CPU and memory for spans nobody reads. | High | Open |
| FR-007 | Drop leaf spans by instrumentation scope | As an operator, I want a targeting rule on `otel.scope.name` to drop matching leaf spans (for example JDBC or psycopg spans in one service), so that a flooding instrumentation can be muted live. | High | Open |
| FR-008 | Switchable Java enforcement point | As a maintainer, I want the Java extension to enforce decisions either in a sampler or in a span processor, selected by `OTELFEATURE_ENFORCEMENT`, so that both can be measured before one is chosen for the talk. | High | Open |
| FR-009 | Trace sample ratio as a number flag | As an operator, I want a `traceSampleRatio` number flag (0.0 to 1.0) that samples root spans, with the same trace landing in the same bucket in every service, so that I can change sampling live and keep traces complete. | High | Open |
| FR-010 | Services declare their own resource attributes | As an operator, I want each service to emit `service.name`, `service.namespace`, `service.version` and `deployment.environment.name` itself, with a production and a staging instance, so that rules can target an environment. | High | Open |
| FR-011 | Service error rate in the evaluation context | As an operator, I want the service's current HTTP server error rate, computed from its existing `http.server.request.duration` metric, available as `otelfeature.http.server.error_rate` in the evaluation context, so that a rule can react to errors. | Medium | Open |
| FR-012 | Fault injection flag | As a speaker, I want a `weatherUpstreamFailure` number flag that makes that fraction of `/weather` requests fail, so that I can cause an incident on demand. | Medium | Open |
| FR-013 | Error-driven sampling rule | As an operator, I want a flag rule that sets `traceSampleRatio` to 1.0 for a service whose error rate is above 5%, and returns to the environment rule when it drops, so that sampling goes up exactly where and when it is needed. | Medium | Open |
| FR-014 | Telemetry decision recorded on kept spans | As an operator looking at a trace, I want root spans kept under a non-default decision to carry the flag key, the variant and the applied sample ratio, so that I can see why the trace looks the way it does and re-weight counts. | Medium | Open |
| FR-015 | Application flag evaluations visible in traces | As an operator, I want the applications' own flag evaluations (such as `weatherUpstreamFailure`) recorded on spans using the `feature_flag` semantic conventions, so that a trace shows which flag caused the failure. | Medium | Open |
| FR-016 | Measured savings | As a speaker, I want a repeatable before/after measurement of CPU, memory, spans/s and export bytes per service, so that the numbers on the slide are real. | Medium | Open |
| FR-017 | Noisy demo workload | As a speaker, I want the demo to produce health-check traffic, a chatty DB path and a higher request rate, so that the drop is obvious. Deferred: not needed for the talk, the wall of spans comes from OTel Demo footage (C-007). Demo 2 must work on the stack's normal traffic (OQ-5). | Low | Deferred |
| FR-018 | Offline stage mode | As a speaker, I want the stack to run with no network, external APIs stubbed, so that the demo doesn't depend on venue Wi-Fi. | High | Open |
| FR-019 | Stage controls | As a speaker, I want named flag presets, a one-command flip per script beat and a reset, so that each demo starts from a known state. | High | Open |
| FR-020 | Public, runnable demo repo | As an adopter, I want to clone the demo repo and run `make start` with only Docker installed, so that I can try what I saw in the talk. | Medium | Open |
| FR-021 | Env-var tier documentation | As an adopter, I want to know which `OTEL_*` env vars can become live flags and which cannot, so that I know what OTelFeature can and cannot replace. | Low | Open |
| FR-022 | Per-signal kill switches | As an operator, I want `signalsEnabled` to turn traces, metrics and logs off separately. Out of talk scope (spans only). | Low | Deferred |

## Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|---|---|---|---|---|---|
| NFR-001 | Fail open | If the provider is not ready or unreachable, the flag is missing, has the wrong type, an unknown variant or an out-of-range value, every policy field resolves to the value derived from the startup env vars (stock OTel behaviour). The failure is logged once per state change, not per span. No exception reaches the application. | Availability | High | In Progress |
| NFR-002 | No network on the span hot path | A flag decision for a span performs no network I/O. Flags are evaluated by the flagd in-process resolver from a ruleset synced over gRPC (port 8015). | Performance | High | Verified |
| NFR-003 | Static-flag fast path | When every flag the policy reads resolves with reason `STATIC`, a span decision is one volatile read: no flag evaluation, no hook chain, no evaluation-context allocation. Verified by an allocation test or benchmark in each extension. | Performance | High | Implemented |
| NFR-004 | Flag change propagation | A flag change saved to `flagd.json` affects new spans within 2 s in both services, without a restart. | Performance | High | Open |
| NFR-005 | Per-span decision cost is measured | The cost of one targeted (non-static) span decision, including context build, is measured once per language (JMH / pytest-benchmark) and reported in the extension README and the measurement table, so claimed savings are net of the evaluation. The acceptable upper bound is not set yet (OQ-3). | Performance | Medium | Open |
| NFR-006 | Footprint | The extensions add no new metric or attribute to the OTLP export when all flags are at defaults. The extra in-process metric reader (FR-011) does not change what reaches the collector. Memory held by the extension is bounded (Java suppressed-span registry: 10,000 entries). The resident-memory overhead per service is reported by the measurement harness. | Performance | High | In Progress |
| NFR-007 | One decision per span | A span's fate is decided once, at start, and not re-asked at end. Within one trace, parent-based sampling stays consistent; `fractional` buckets use the trace id so every service puts a trace in the same bucket. | Maintainability | High | In Progress |
| NFR-008 | Non-breaking drop-in | Installing either extension with flags at their defaults produces the same spans as the stock SDK/agent (plus nothing). | Usability | High | Implemented |
| NFR-009 | Isolation from the application's OpenFeature | The Java extension uses an isolated `OpenFeatureAPI` and never replaces the application's global provider. The Python launcher lets the application take over with `OTELFEATURE_FLAG_PROVIDER=none`. | Portability | High | Verified |
| NFR-010 | Startup never blocks on flagd | Service startup does not wait for flagd. Until the provider is ready, flags resolve to defaults (NFR-001). | Availability | High | Implemented |
| NFR-011 | Reproducible measurements | Two runs of the measurement harness with the same preset agree within ±10% per metric. | Maintainability | Medium | Open |
| NFR-012 | Rehearsal repeatability | Each demo run-through, started from the reset command, works three times in a row. | Usability | High | Open |
| NFR-013 | Error rate is sampling-independent | The error rate fed into the context (FR-011) is identical whether spans are sampled at 1.0 or 0.0. | Maintainability | Medium | Open |

## Constraints

| ID | Title | Constraint | Category | Priority | Status |
|---|---|---|---|---|---|
| C-001 | Spans and traces only | The talk controls spans and traces. Metrics are only an input to span decisions. No metric or log gating is built for the talk. | Business | High | Open |
| C-002 | flagd in-process provider | Flags are served by flagd (v0.17) and evaluated in-process (gRPC sync on 8015) in both extensions. OFREP polling was rejected (OTelFeature/otelfeature-java-extension#9). | Technical | High | Verified |
| C-003 | Only start-time attributes | Rules can only use attributes known when the span starts. `http.route` and `http.response.status_code` are not available then (D6), so rules target `url.path`. | Technical | High | Open |
| C-004 | Sampler drop takes the subtree | A sampler `DROP` removes the span and its whole subtree and propagates `sampled=0` downstream. The sampler may therefore only drop root spans (health checks) and leaf spans (DB calls). Mid-trace `INTERNAL` suppression stays in the processor in both modes (D3). | Technical | High | Open |
| C-005 | Python HTTP metric opt-in | The FastAPI/ASGI instrumentation emits `http.server.request.duration` with `error.type` only with `OTEL_SEMCONV_STABILITY_OPT_IN=http`; otherwise the old `http.server.duration`. | Technical | Medium | Open |
| C-006 | Released extension versions | The demo stack consumes released versions of both extensions (`OTELFEATURE_EXTENSION_VERSION` build arg, Python package pin). Final measurements and the control loop need releases that contain the features. | Technical | High | Open |
| C-007 | OTel Demo as footage only | The opening hook uses recorded OTel Demo footage (D1). No live OTel Demo on stage. | Operational | Medium | Open |
| C-008 | Fallback video | Each demo has a recorded fallback in case the live run fails. | Operational | Low | Open |
| C-009 | External API usage policy | Nominatim allows about 1 request/s per source IP. Higher request rates require the stubbed APIs (FR-018). | Regulatory | High | Open |
| C-010 | Collector is not a decision point | Nothing is built in the collector (D4). The script says the collector *could* read the same flags. | Business | Medium | Open |
