# flagd

An [OpenFeature](https://openfeature.dev/) feature-flag backend
([flagd](https://flagd.dev/)), used here to control
[geocode](../geocode)'s `telemetryLevel` flag — whether `INTERNAL` spans are
kept (`FULL`) or suppressed (`IO`) — live, without restarting `geocode`. See
[geocode's README](../geocode/README.md#the-telemetrylevel-flag) for how the
flag is consumed.

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
      "defaultVariant": "full",
      "state": "ENABLED",
      "variants": {
        "io": "IO",
        "full": "FULL"
      }
    }
  }
}
```

## Updating a flag

Just edit [flagd.json](flagd.json) and save — no restart needed for either
`flagd` or `geocode`:

1. flagd's file-provider watches the file for changes (`Starting filepath
   sync notifier` in its startup logs) and picks up the edit almost
   instantly.
2. It pushes the updated ruleset to every connected client — including
   `geocode`'s in-process provider — over the gRPC sync stream (port `8015`).
3. `geocode` evaluates the new value on the very next span it creates.

To flip trace verbosity, change `defaultVariant` between `"full"` and `"io"`.
More elaborate changes (targeting rules, additional flags) follow the same
[flag definition schema](https://flagd.dev/reference/flag-definitions/).

## Verifying a flag's current value

Without going through `geocode`, flagd's OFREP REST endpoint (port `8016`,
published in [compose.yaml](../../compose.yaml)) evaluates a flag directly:

```sh
curl -s -X POST http://localhost:8016/ofrep/v1/evaluate/flags/telemetryLevel \
  -H "Content-Type: application/json" -d '{"context":{}}'
```

## Ports

| Port   | Protocol  | Purpose                                              |
|--------|-----------|-------------------------------------------------------|
| `8013` | gRPC      | Flag evaluation (`rpc` resolver mode) — unused by `geocode`, which uses `in-process` instead |
| `8015` | gRPC      | Flag sync (`in-process` resolver mode) — what `geocode` actually connects to |
| `8016` | HTTP      | [OFREP](https://github.com/open-feature/protocol) REST evaluation |

`8014` (flagd's own Prometheus metrics/health endpoint) isn't published —
nothing in this repo consumes it.

## Configuration

| Environment variable          | Description                                        |
|--------------------------------|----------------------------------------------------|
| `GOMEMLIMIT`                   | Go runtime soft memory limit (`60MiB` here)         |
| `OTEL_SERVICE_NAME`            | Service name flagd reports on its own telemetry     |
| `OTEL_EXPORTER_OTLP_ENDPOINT`  | Collector endpoint flagd exports its own telemetry to |
| `OTEL_EXPORTER_OTLP_PROTOCOL`  | OTLP wire protocol for that export                  |

## Flag changes with no effect?

If editing `flagd.json` seems to do nothing, it's very likely not a flagd
issue — see the rebuild caveat in
[geocode's README](../geocode/README.md#running-via-docker-compose).
