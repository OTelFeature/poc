# otel-collector

An `otel/opentelemetry-collector-contrib` instance. It receives OTLP from
[geocode](../geocode), [weather](../weather),
[load-generator](../load-generator) and [flagd](../flagd), reads Docker
container stats, derives span metrics, and sends everything to the Aspire
Dashboard, and to Dash0 where that is enabled.

Configured by [config.yaml](config.yaml), plus [dash0.yaml](dash0.yaml)
when [compose.dash0.yaml](../../compose.dash0.yaml) is in use.

## Pipelines

| Pipeline | Receivers | Processors | Exporters |
|---|---|---|---|
| `traces` | `otlp` | `resource` | `debug`, `otlp_grpc/aspire`, `span_metrics` |
| `metrics` | `otlp`, `span_metrics`, `docker_stats` | `transform`, `resource` | `debug`, `otlp_grpc/aspire` |
| `logs` | `otlp` | `resource` | `debug`, `otlp_grpc/aspire` |

- `resource` sets `deployment.environment.name=otelfeature` with
  `action: insert`, so only senders without one get it (flagd, k6, docker
  stats). `geocode` and `weather` set their own, and their flag rules depend
  on it, so the collector must not overwrite it.
- `transform` sets `service.name=docker-stats` on the `docker_stats`
  metrics, so they show up as their own service.
- `span_metrics` derives RED metrics from the spans. Metrics stay
  cumulative.

The collector's own metrics and logs go to Aspire through
`service::telemetry` and show up as a separate resource.

## Dash0 export

Opt-in per laptop (C-016). To enable it, add the lines of
[.env.dash0.example](../../.env.dash0.example) to the git-ignored `.env` at
the repo root and fill in the token. `COMPOSE_FILE` there makes every
`docker compose` command and `make` target load
[compose.dash0.yaml](../../compose.dash0.yaml), which passes
[dash0.yaml](dash0.yaml) as a second `--config`. Without `.env` nothing goes
to Dash0.

dash0.yaml adds the `otlp_grpc/dash0` exporter and three pipelines,
`traces/dash0`, `metrics/dash0` and `logs/dash0`, with the same receivers and
processors as config.yaml. Keep them in step. It adds pipelines instead of
extending config.yaml's because the collector replaces lists when it merges
configs.

The token is the compose secret `dash0_token`, read with
`${file:/run/secrets/dash0_token}`, so `docker compose config` and
`docker inspect` don't show it.

Offline, each batch gets one attempt (2 s timeout, no retries, 20 consumers)
and is dropped. The queue never fills, so the SDKs never re-send, which
would show those batches twice in Aspire (UC-008 BR-009).

Validate a change with the pinned image (the variable values don't matter):

```sh
docker run --rm -v "$PWD/src/otel-collector:/c:ro" \
  -v /dev/null:/run/secrets/dash0_token:ro \
  -e OTEL_COLLECTOR_HOST=0.0.0.0 -e OTEL_COLLECTOR_PORT_GRPC=4317 -e OTEL_COLLECTOR_PORT_HTTP=4318 \
  -e DASH0_ENDPOINT=x:4317 \
  otel/opentelemetry-collector-contrib:0.164.0 validate --config=/c/config.yaml --config=/c/dash0.yaml
```

## Ports

| Port | Protocol | Used by |
|---|---|---|
| `4317` | OTLP/gRPC | `load-generator` |
| `4318` | OTLP/HTTP | `geocode`, `weather`, `flagd` |

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `OTEL_COLLECTOR_HOST` | `otel-collector` | Bind host for the OTLP receivers |
| `OTEL_COLLECTOR_PORT_GRPC` | `4317` | OTLP/gRPC receiver port |
| `OTEL_COLLECTOR_PORT_HTTP` | `4318` | OTLP/HTTP receiver port |
| `DASH0_ENDPOINT` | - | Dash0 only: OTLP/gRPC ingress, `ingress.<region>.aws.dash0.com:4317` |
| `DASH0_AUTH_TOKEN` | - | Dash0 only: auth token, passed in as the secret `dash0_token` |
| `DASH0_DATASET` | `default` | Dash0 only: dataset |

The first three are set in [compose.yaml](../../compose.yaml), the Dash0
ones in `.env`.

## Troubleshooting

The `debug` exporter logs every batch it receives:

```sh
docker compose logs -f otel-collector
```

The collector runs as root (`user: "0:0"`) so the `docker_stats` receiver
can read `/var/run/docker.sock`. On a native engine (WSL2, Linux) the socket
is `root:docker 660`. As a non-root user the receiver fails to start and the
collector exits, so no telemetry arrives at all.
