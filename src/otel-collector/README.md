# otel-collector

An `otel/opentelemetry-collector-contrib` instance that's the hub of this
repo's telemetry: it receives OTLP from [geocode](../geocode),
[load-generator](../load-generator), and [flagd](../flagd), scrapes Docker
container stats directly, derives span metrics, and forwards everything to
the Aspire Dashboard — and, on a laptop that opts in, to Dash0.

Configured by [config.yaml](config.yaml), mounted into the container via
[compose.yaml](../../compose.yaml), plus [dash0.yaml](dash0.yaml) where
[compose.dash0.yaml](../../compose.dash0.yaml) is enabled.

## Pipelines

- **traces**: `otlp` receiver → `resource` processor → `debug` +
  `otlp_grpc/aspire` exporters, and the `span_metrics` connector (derives
  RED metrics from spans).
- **metrics**: `otlp` + `span_metrics` + `docker_stats` receivers → a
  `transform` processor (relabels `docker_stats`-sourced metrics'
  `service.name` to `docker-stats`, so they show up as their own service in
  Aspire rather than under `otelcol-contrib`) and a `resource` processor →
  `debug` + `otlp_grpc/aspire` exporters. Metrics stay cumulative, the OTLP
  default; the `cumulativetodelta` processor went with the Datadog exporter,
  whose intake needed delta.
- **logs**: `otlp` receiver → `resource` processor → `debug` +
  `otlp_grpc/aspire` exporters.

With Dash0 enabled, `traces/dash0`, `metrics/dash0` and `logs/dash0` send
the same signals, with the same receivers and processors, to
`otlp_grpc/dash0`.

## Resource processor

The `resource` processor sets `deployment.environment.name=otelfeature` with
`action: insert`, so it only fills the attribute when a sender didn't set one
(flagd, k6, docker stats). `geocode` and `weather` set their own
(`production` or `staging`) because the flag rules that read it run inside
their SDKs; the collector must not overwrite it.

## Dash0 export

Opt-in per laptop (C-016). [dash0.yaml](dash0.yaml) adds the
`otlp_grpc/dash0` exporter (OTLP/gRPC to `DASH0_ENDPOINT`, with
`Authorization: Bearer <token>` and `Dash0-Dataset`) and three pipelines of
its own. It doesn't extend config.yaml's pipelines: the collector merges maps
but replaces lists, so that would mean copying their exporter lists. Keep
the receivers and processors of the `/dash0` pipelines in step with
config.yaml. The token is the compose secret `dash0_token`, read with
`${file:/run/secrets/dash0_token}`, so `docker compose config` and
`docker inspect` don't show it.
[compose.dash0.yaml](../../compose.dash0.yaml) passes it as a second
`--config`. To enable it on one laptop, add the lines of
[.env.dash0.example](../../.env.dash0.example) to the git-ignored `.env` at
the repo root and fill in the token: `COMPOSE_FILE` there makes every
`docker compose` command, `make` target and stage command use the overlay,
so the stage commands don't change. Without `.env` nothing goes to Dash0.

Offline, each batch gets one attempt (2 s timeout, no retries, 20 consumers) and is
dropped. The queue never fills, so no error goes back to the receiver; a
full queue would make the SDKs re-send, and Aspire would show those batches
twice (UC-008 BR-009, TC-006 item 8).

Check a change with the pinned image (any values for the variables):

```sh
docker run --rm -v "$PWD/src/otel-collector:/c:ro" \
  -v /dev/null:/run/secrets/dash0_token:ro \
  -e OTEL_COLLECTOR_HOST=0.0.0.0 -e OTEL_COLLECTOR_PORT_GRPC=4317 -e OTEL_COLLECTOR_PORT_HTTP=4318 \
  -e DASH0_ENDPOINT=x:4317 \
  otel/opentelemetry-collector-contrib:0.164.0 validate --config=/c/config.yaml --config=/c/dash0.yaml
```

## Self-telemetry

The collector also exports its own internal metrics and logs to the Aspire
Dashboard, via `service::telemetry` in [config.yaml](config.yaml):

- **metrics**: a `periodic` reader pushes internal metrics (e.g. receiver/
  exporter throughput, queue sizes) to Aspire over OTLP/gRPC.
- **logs**: a `batch` processor forwards the collector's own log records to
  Aspire over OTLP/gRPC, in addition to the default stdout logging.

These show up in Aspire as their own resource, separate from the
`otlp_grpc/aspire` exporter used for the pipelines above (which carries
telemetry *received from* other services).

## Ports

| Port   | Protocol       | Purpose                          |
|--------|----------------|----------------------------------|
| `4317` | OTLP/gRPC      | Used by `load-generator`         |
| `4318` | OTLP/HTTP      | Used by `geocode` and `flagd`    |

## Docker socket access

The `docker_stats` receiver reads container stats from
`/var/run/docker.sock`, mounted read-only. The image runs as a non-root user
(`10001`) by default, but the socket (as seen inside a Linux container under
Docker Desktop) is owned by `root:root`, mode `660`. `compose.yaml` sets
`user: "10001:0"` — keeps the non-root UID but runs with GID `0` (root
group), which has `rw` on the socket via the group bit. This is the minimal
privilege needed; running as full root isn't necessary.

## Configuration

Reads its own OTLP receiver endpoints from environment variables set in
[compose.yaml](../../compose.yaml), and the Dash0 settings from
[compose.dash0.yaml](../../compose.dash0.yaml), which reads them from `.env`:

| Environment variable       | Default           | Description                                     |
|----------------------------|-------------------|-------------------------------------------------|
| `OTEL_COLLECTOR_HOST`      | `otel-collector`  | Bind host for the OTLP receivers                |
| `OTEL_COLLECTOR_PORT_GRPC` | `4317`            | OTLP/gRPC receiver port                         |
| `OTEL_COLLECTOR_PORT_HTTP` | `4318`            | OTLP/HTTP receiver port                         |
| `DASH0_ENDPOINT`           | -                 | Dash0 OTLP/gRPC ingress, `ingress.<region>.aws.dash0.com:4317` (Dash0 only) |
| `DASH0_AUTH_TOKEN`         | -                 | Dash0 auth token (Dash0 only); reaches the collector as the compose secret `dash0_token` |
| `DASH0_DATASET`            | `default`         | Dash0 dataset (Dash0 only)                      |

## Debugging

The `debug` exporter logs every received trace/metric/log batch to stdout:

```sh
docker compose logs -f otel-collector
```
