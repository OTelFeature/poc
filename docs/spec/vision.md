# Vision: OpenFeature as a Control Plane for OpenTelemetry

Inception artifact. Hand-written; everything else in `docs/spec/` is derived
from it. Keep it to about one page.

## Problem

Tracing costs money in three places: CPU and memory in the service that
creates the spans, network egress when they are exported, and ingest and
storage in the backend. Most of the noise is known in advance: health checks,
the load generator, the same database call ten thousand times in one trace.

Today the levers to cut that noise sit in two bad places:

- **OTel SDK environment variables** (`OTEL_SDK_DISABLED`,
  `OTEL_TRACES_SAMPLER_ARG`, `OTEL_INSTRUMENTATION_*_ENABLED`) are read once at
  startup. Changing one means a redeploy, which is the wrong speed for an
  incident.
- **The collector** can filter and sample, but only after the span was created,
  populated, batched, serialized and sent. The service has already paid for it.

The talk's thesis: *the collector treats the symptom. The SDK is where the data
is born, so that's where the decision belongs.* OpenFeature already gives teams
a runtime control plane with targeting. If the SDK asks a flag before it
creates a span, the decision is live, targeted and cheap.

## Solution

Two zero-code extensions read OpenFeature flags (served by flagd, evaluated
in-process) at the point where spans are created:

- `otelfeature-instrument`: a Python launcher that wraps the tracer.
- `otelfeature-java-extension`: an OTel Java agent extension that enforces
  either in a span processor or in a sampler (`OTELFEATURE_ENFORCEMENT`,
  default `processor`, the mode chosen for the talk, D3).

The flags' evaluation context is built from OpenTelemetry semantic
conventions (resource, instrumentation scope, span start attributes), so a
targeting rule reads like the telemetry it controls: `service.name`,
`otel.scope.name`, `url.path`. The service's own error rate, read from the
`http.server.request.duration` metric it already records, is added to the same
context so a targeting rule can raise sampling when a service starts failing.

This repository (`poc`) is the demo stack the talk runs on: `geocode`
(Python), `weather` (Java), flagd, Postgres, the OTel Collector, the Aspire
dashboard and k6.

## Stakeholders and target users

| Stakeholder | What they need from this |
|---|---|
| Talk audience (developers, SREs, platform engineers) | A demo that shows each claim live and holds up to "but does it really save anything?" |
| Speakers / maintainers (Simon for OpenFeature, Juliano for OpenTelemetry) | A stage setup that works offline, flips in one keystroke and resets between rehearsals; script lines that are true for both languages |
| Adopters (teams who try it after the talk) | A public repo that starts with `make start`, extensions that change nothing until a flag is flipped, honest docs about what is and isn't saved |
| Agents and contributors picking up issues | A spec that says what "done" means for each work item, so code and tests follow from it; one Docker-based toolchain per repo, so local runs and CI agree |

## Goals

1. **Demo 1.** One boolean flag turns tracing off and back on at runtime, in
   both services, without a restart.
2. **Demo 2.** Flags drop specific spans per service and per instrumentation
   (health checks in one service, DB spans in another) before they are created,
   with CPU, memory and export savings measured at the service.
3. **Demo 3.** Semantic conventions as evaluation context make rules generic;
   the trace sample ratio is a number flag targeted by environment and service;
   a control loop raises sampling for a service whose error rate goes up, and
   the application's own flag evaluations (the injected failure) show up in
   the resulting traces. The extensions do not write their own decisions onto
   spans (OQ-9 for the script line).
4. The extensions fail open: no flagd, no flag, or a broken flag means
   behaviour identical to the stock OTel SDK.
5. Flags only reduce telemetry. They never enable what an env var switched
   off (`OTEL_SDK_DISABLED=true`, `OTEL_TRACES_SAMPLER=always_off`).
6. **A scripted demo that is verified automatically.** Every demo beat runs
   as an end-to-end test against the real stack in CI, in both Java
   enforcement modes, and must pass before extension code is merged
   (OTelFeature/poc#35). What runs on stage is what was tested.

## Non-goals

- **Gating metrics or logs.** Metrics are cheap compared to spans. They appear
  only as an *input* (the error rate that steers span sampling). Per-signal
  kill switches (`signalsEnabled`, OTelFeature/poc#11, P2) and a Python logs
  pipeline are out of scope for the talk.
- Replacing the collector. Tail sampling, redaction and routing stay there. The
  collector *could* read the same flags (decision D4); nothing is built for it.
- A true SDK disable. `OFF` suppresses spans; context propagation and
  instrumentation bytecode stay in place. Known limitation, accepted: while
  `OFF`, trace context keeps propagating, so services that still trace can
  produce traces with gaps or missing parents.
- Recording the extensions' own flag decisions on spans. No `feature_flag.*`
  attributes, no `otelfeature.sample_ratio`, no tracestate `ot=th`. Recording
  flag evaluations is the OpenFeature OpenTelemetry hook's job.
- Making every `OTEL_*` env var a live flag. Some cannot be (the Java agent
  cannot un-install bytecode). OTelFeature/poc#14 documents which; the roadmap
  is OTelFeature/poc#15.
- Running the OTel Demo on stage. Its footage is used for the opening hook
  only (decision D1, OTelFeature/poc#33).
- Making the POC itself noisy (health-check load, chatty DB path, higher
  rates; OTelFeature/poc#23). Deferred to P2: the wall of spans comes from the
  OTel Demo footage (OTelFeature/poc#33), and the measurements in
  OTelFeature/poc#27 no longer depend on it.
- Production hardening of the demo stack (auth, HA flagd, persistent storage).

## Decisions taken in inception

From `DEMO-BACKLOG.md` (settled 2026-10-16). Referenced by ID from the other
documents. Later design decisions (Simon, 2026-10-16: hard floors,
`recordSpan`, context collisions, per-tracer decisions, root-only ratio,
error-rate minimum, no decision recording, workflow, end-to-end suite,
toolchain images, exporter env vars) live in the requirements,
use case business rules and the entity model's reference data; the open
questions table in the [README](README.md#open-questions) points to them.

| ID | Decision |
|---|---|
| D1 | OTel Demo footage for the hook, this POC for Demos 1 to 3 |
| D2 | Demo 1 uses a boolean `otelEnabled` *and* a `telemetryLevel=OFF` variant; both map onto `enabled` in the policy |
| D3 | Java: build the sampler path next to the processor path (`OTELFEATURE_ENFORCEMENT`, default `processor`), decide from measurements: decided `processor` (Simon, 2026-10-16, OQ-1; to confirm with Juliano, OTelFeature/poc#84) |
| D4 | Collector line softened to "you *could* point the collector at the same flags"; nothing to build |
| D5 | Control loop = flagd targeting rule over the existing `http.server.request.duration` metric; no outside script, no new metric |
| D6 | Target `url.path`, not `http.route` (not known at span start) |
