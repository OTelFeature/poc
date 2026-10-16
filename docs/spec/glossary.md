# Glossary

One name per domain concept, used in [requirements.md](requirements.md), the
use cases, the test cases and the code. Words in **Avoid** are flagged by the
spec lint wherever they appear. Flag keys, env vars and semconv attribute
names are defined in the [entity model](entity_model.md#reference-data), not
here.

| Term | Definition | Avoid |
|---|---|---|
| Operator | Whoever manages the flags for a service: an SRE, a platform engineer, or the speaker on stage. | |
| Speaker | Simon or Juliano, performing the demo on stage. | |
| Adopter | Someone running the extensions or the demo after the talk. | |
| Maintainer | Someone who develops the extensions or the demo stack. | |
| Extension | One of the two OTelFeature packages, `otelfeature-instrument` (Python) or `otelfeature-java-extension` (Java agent), that let flags steer span creation. | |
| Application | The service's own code, as opposed to the extension that instruments it; it may evaluate its own flags (`weatherUpstreamFailure`). | |
| Service | An instrumented process, identified by its OTel resource (`service.name`, `deployment.environment.name`). | |
| Flag | An OpenFeature flag served by flagd. Every flag has a key, a type and named variants. | toggle |
| Variant | One named value of a flag, such as `off` for `otelEnabled`. | |
| Targeting rule | The flagd JsonLogic expression of a flag that picks a variant from the evaluation context. A flag without one serves its default variant. | flag rule |
| Kill switch | A flag that turns span creation off and on in every service at runtime: `otelEnabled=false`, or `telemetryLevel=OFF`. Trace context keeps propagating. | |
| Flag preset | A named, complete flag file for one stage state, in `src/flagd/presets/`. Presets are cumulative: each keeps the rules of the one before it. | |
| Telemetry policy | The single value an enforcement point reads per span decision, resolved from every flag the extension reads (`TelemetryPolicy`). | |
| Evaluation context | What a targeting rule sees for one span decision: resource, instrumentation scope and span start attributes under their semconv names, the error rate, and the trace id as `targetingKey`. | |
| Context key | One key of the evaluation-context contract, nested by dot segment. | |
| Semantic conventions | The OpenTelemetry attribute names (semconv), such as `service.name` or `url.path`, that the evaluation context reuses as its keys. | |
| Instrumentation scope | The library that created a span, as `otel.scope.name`. A rule on it mutes one instrumentation. | |
| Span decision | The outcome for one span start: record, drop, suppress, or delegate. Taken once, at start. | |
| Enforcement point | Where an extension applies the telemetry policy to a span: the Java sampler, the Java span processor, or the Python tracer. | |
| Enforcement mode | The Java choice between sampler and processor enforcement, set by `OTELFEATURE_ENFORCEMENT` (default `processor`). | |
| Root span | A span with no valid parent, or an incoming request span (`SERVER`/`CONSUMER`) with a remote parent. Only root spans evaluate the trace sample ratio. | |
| Leaf span | A span with no children of its own, such as a DB client span. | |
| Drop | A span decision that leaves out the span and its whole subtree; downstream services receive `sampled=0`. | |
| Suppress | A span decision that leaves out only this span; its children attach to the real parent and the trace stays sampled. | |
| Trace sample ratio | The fraction of root spans that are sampled, from the `traceSampleRatio` flag (0.0 to 1.0). Every other span follows its parent. | |
| Error rate | A service's current HTTP server error rate, computed in process from `http.server.request.duration` and offered to rules as `otelfeature.http.server.error_rate`. | |
| Control loop | The error-driven targeting rule that raises a failing service's trace sample ratio to 1.0 and lowers it once errors stop. | |
| Hard floor | An env var setting no flag can override: `OTEL_SDK_DISABLED=true` and `OTEL_TRACES_SAMPLER=always_off`. Flags only reduce telemetry. | |
| Fail open | On any flag failure (provider not ready, flag missing, wrong type or value) the policy falls back to the startup env vars, that is stock OTel behaviour. | |
| Static-flag fast path | When every flag the policy reads resolves with reason `STATIC`, a span decision is one cached read with no flag evaluation. | |
| Fault injection | Making a share of `/weather` requests fail on demand with the `weatherUpstreamFailure` flag, to cause an incident. | |
| Offline stage mode | The demo stack running with no network, external APIs replaced by stubs. | |
| Script beat | One step of the talk script that a demo performs (Demo 1, Demo 2, Demo 3). | |
| End-to-end suite | The automated tests that run the script beats against the real stack in GitHub Actions (NFR-015). | |
