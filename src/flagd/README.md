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
  an OTel Java agent extension that polls flagd's OFREP REST endpoint (port
  `8016`) every 5 seconds and suppresses `INTERNAL` spans (with re-parenting
  of child spans) at the exporter level. See
  [weather's README](../weather/README.md#otelfeature-java-extension).

## Flag definitions

[flagd.json](flagd.json) is flagd's
[flag definition file](https://flagd.dev/reference/flag-definitions/),
mounted read-only into the container at `/etc/flagd` and passed via
`--uri file:./etc/flagd/flagd.json` (see the `flagd` service in
[compose.yaml](../../compose.yaml)):

```json
{
  "flags": {
    "telemetryLevel": {
      "defaultVariant": "io",
      "description": "Control telemetry level",
      "state": "ENABLED",
      "variants": {
        "io": "IO",
        "full": "FULL"
      }
    }
  }
}
```

The default is `"io"` — `INTERNAL` spans are suppressed by default. Flip to
`"full"` to see all spans including controller/internal implementation spans.

## Updating a flag

Just edit [flagd.json](flagd.json) and save — no restart needed for `flagd`
or any consuming service:

1. flagd's file-provider watches the file for changes (`Starting filepath
   sync notifier` in its startup logs) and picks up the edit almost
   instantly.
2. For `geocode`: flagd pushes the updated ruleset to the in-process provider
   over the gRPC sync stream (port `8015`).
3. For `weather`: the extension's background poller picks up the change
   within 5 seconds via the OFREP REST endpoint (port `8016`).
4. Both services evaluate the new value on the very next span they create.

To flip trace verbosity, change `defaultVariant` between `"full"` and `"io"`.
More elaborate changes (targeting rules, additional flags) follow the same
[flag definition schema](https://flagd.dev/reference/flag-definitions/).

## Verifying a flag's current value

Without going through any service, flagd's OFREP REST endpoint (port `8016`,
published in [compose.yaml](../../compose.yaml)) evaluates a flag directly:

```sh
curl -s -X POST http://localhost:8016/ofrep/v1/evaluate/flags/telemetryLevel \
  -H "Content-Type: application/json" -d '{"context":{}}'
```

## Ports

| Port   | Protocol  | Purpose                                                                                              |
|--------|-----------|------------------------------------------------------------------------------------------------------|
| `8013` | gRPC      | Flag evaluation (`rpc` resolver mode) — unused                                                       |
| `8015` | gRPC      | Flag sync (`in-process` resolver mode) — what `geocode`'s otelfeature-instrument connects to          |
| `8016` | HTTP      | [OFREP](https://github.com/open-feature/protocol) REST evaluation — what `weather`'s extension polls   |

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
