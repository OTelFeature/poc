# flagd

An [OpenFeature](https://openfeature.dev/) feature-flag backend
([flagd](https://flagd.dev/)), used here to control the `telemetryLevel` flag
— whether `INTERNAL` spans are kept (`FULL`) or suppressed (`IO`) — live,
without restarting any service.

Both services consume this flag, each through its own language-specific
mechanism:

- **geocode** ([Python](../geocode)) — uses
  [otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument),
  which connects to flagd via gRPC (in-process resolver, port `8015`) and
  suppresses `INTERNAL` spans at the SDK level. See
  [geocode's README](../geocode/README.md#the-telemetrylevel-flag).
- **weather** ([Java](../weather)) — uses
  [otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension),
  an OTel Java agent extension that connects to flagd via gRPC (in-process
  resolver, port `8015`) and suppresses `INTERNAL` spans (with re-parenting of
  child spans) at the exporter level. See
  [weather's README](../weather/README.md#otelfeature-java-extension).

Both therefore consume the flag the same way: flagd **pushes** the ruleset
down a gRPC sync stream and each service evaluates it in-process, with no
network call on the span hot path and no poll interval to wait out.

## Flag definitions

[flagd.json](flagd.json) is flagd's
[flag definition file](https://flagd.dev/reference/flag-definitions/),
mounted into the container at `/etc/flagd` and passed via
`--uri file:./etc/flagd/flagd.json` (see the `flagd` service in
[compose.yaml](../../compose.yaml)):

| Flag | Type | Variants | Default | What it does |
|---|---|---|---|---|
| `otelEnabled` | boolean | `on`, `off` | `on` | Kill switch: `off` means no spans in either service (Demo 1) |
| `telemetryLevel` | string | `full`=FULL, `io`=IO, `off`=OFF | `full` | `IO` drops `INTERNAL` spans; `OFF` is the same as `otelEnabled=off` |
| `recordSpan` | boolean | `on`, `off` | `on` | Evaluated per span against the semconv context; a targeting rule returning `off` drops that span (Demo 2) |
| `traceSampleRatio` | number | `all`=1.0, `half`=0.5, `tenth`=0.1, `none`=0.0 | `all` | Sample ratio for root spans (Demo 3) |
| `weatherUpstreamFailure` | number | `none`=0.0, `incident`=0.3, `outage`=1.0 | `none` | **Application flag**: share of `weather`'s `/weather` requests that fail with HTTP 503 (Demo 3 incident). Evaluated by weather's own OpenFeature client, not the extension |

The committed `flagd.json` is the neutral baseline: every flag at its
default, no targeting, so the services behave like stock OpenTelemetry. It is
byte-for-byte the `00-baseline` preset (CI checks this). The flags other than
`telemetryLevel` FULL/IO need otelfeature-instrument v0.3.0 /
otelfeature-java-extension v0.4.0 or later, the versions the stack pins;
older versions ignore them.

Flag descriptions live in each flag's `metadata`. A flag-level
`"description"` key passes the flagd schema, but the Python in-process
provider (`openfeature-provider-flagd`) refuses the whole file because of it.

## Presets

[presets/](presets) holds one complete flag file per demo state. `make flag
PRESET=<name>` copies one over `flagd.json`, and `make demo-reset` goes back
to `00-baseline`. [STAGE.md](../../STAGE.md) maps every script beat to a
preset and says what each one changes.

Every preset is checked in CI ([flags.yml](../../.github/workflows/flags.yml),
or `make test` locally, inside the `ci/Dockerfile` image):

1. It validates against `https://flagd.dev/schema/v0/flags.json`.
2. [test_presets.py](test_presets.py) loads it with the same Python flagd
   evaluator geocode uses and checks the rules against the spans of each demo
   beat. When you add a preset, add its expected results there.

## Updating a flag

Just edit [flagd.json](flagd.json) and save — no restart needed for `flagd`
or any consuming service:

1. flagd's file-provider watches the file for changes (`Starting filepath
   sync notifier` in its startup logs) and picks up the edit almost
   instantly.
2. flagd pushes the updated ruleset to both services' in-process providers
   over the gRPC sync stream (port `8015`).
3. Each provider raises `PROVIDER_CONFIGURATION_CHANGED`, and both services
   re-evaluate `telemetryLevel` on the very next span they create.

To flip trace verbosity by hand, change `telemetryLevel`'s `defaultVariant`
between `"full"` and `"io"`; for the demo beats use the presets above.
More elaborate changes (targeting rules, additional flags) follow the same
[flag definition schema](https://flagd.dev/reference/flag-definitions/) — see
below for what a targeting rule changes about how the flag is *evaluated*.

## Static flags are evaluated once; targeted flags, every time

`telemetryLevel` is consulted on every single span, so both services do
something slightly clever with it. flagd reports *why* it produced a value,
and the flag definition above has no `targeting` block, so the reason is
`STATIC`: one `defaultVariant` for the whole world, the same answer for every
span. Both services therefore evaluate it **once**, from their provider's
configuration-change handler, and answer every span from memory after that.

Add a `targeting` block and the reason becomes `TARGETING_MATCH` — the value
now depends on who is asking, so caching switches itself off and every span is
evaluated individually. Remove it and caching resumes. Nothing is configured
and nothing is restarted; the flag definition itself decides.

### Seeing it happen

Paste a `targeting` block into `telemetryLevel` in
[flagd.json](flagd.json) and save. This one flips on every second, so
consecutive spans genuinely get different answers:

```json
"targeting": {
  "if": [
    { "==": [{ "%": [{ "var": "$flagd.timestamp" }, 2] }, 0] },
    "io",
    "full"
  ]
}
```

`$flagd.timestamp` (unix seconds) is injected by flagd itself, so this needs
no evaluation context from the services. Watch the Aspire Dashboard: traces
start alternating between full and I/O-only as the second ticks over, and both
services log that `telemetryLevel` is now being evaluated per span. Delete the
block again and they log that it is static and go back to evaluating it once.

> [!NOTE]
> The evaluation context built from the span's semconv attributes (resource,
> scope, span-start attributes; trace id as `targetingKey`) needs
> otelfeature-instrument v0.3.0 / otelfeature-java-extension v0.4.0 or later,
> the versions the stack pins. With older versions a rule has nothing to match
> on beyond flagd's own `$flagd.*` properties.

## Verifying a flag's current value

Without going through any service, flagd's OFREP REST endpoint (port `8016`,
published in [compose.yaml](../../compose.yaml)) evaluates a flag directly.
Nothing in this repo consumes OFREP any more — it's kept published purely as
a debugging convenience:

```sh
curl -s -X POST http://localhost:8016/ofrep/v1/evaluate/flags/telemetryLevel \
  -H "Content-Type: application/json" -d '{"context":{}}'
```

## Ports

| Port   | Protocol  | Purpose                                                                                              |
|--------|-----------|------------------------------------------------------------------------------------------------------|
| `8013` | gRPC      | Flag evaluation (`rpc` resolver mode) — unused                                                       |
| `8015` | gRPC      | Flag sync (`in-process` resolver mode) — what **both** services connect to                            |
| `8016` | HTTP      | [OFREP](https://github.com/open-feature/protocol) REST evaluation — debugging only, no longer consumed |

`8014` (flagd's own Prometheus metrics/health endpoint) isn't published —
nothing in this repo consumes it.

## Configuration

| Environment variable          | Description                                            |
|--------------------------------|-------------------------------------------------------|
| `GOMEMLIMIT`                   | Go runtime soft memory limit (`60MiB` here)           |
| `OTEL_SERVICE_NAME`            | Service name flagd reports on its own telemetry       |
| `OTEL_EXPORTER_OTLP_ENDPOINT`  | Collector endpoint flagd exports its own telemetry to |
| `OTEL_EXPORTER_OTLP_PROTOCOL`  | OTLP wire protocol for that export                    |

## Flag changes with no effect?

If editing `flagd.json` seems to do nothing, it's very likely not a flagd
issue — see the rebuild caveats in
[geocode's README](../geocode/README.md#running-via-docker-compose) and
[weather's README](../weather/README.md#running-via-docker-compose).
A stale container image is the most common cause: `docker compose up -d`
(without `--build`) silently keeps serving the old image.
