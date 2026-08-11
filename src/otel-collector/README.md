# otel-collector

An `otel/opentelemetry-collector-contrib` instance that's the hub of this
repo's telemetry: it receives OTLP from [geocode](../geocode) and
[load-generator](../load-generator), scrapes Docker container stats directly,
derives span metrics, and forwards everything to the Aspire Dashboard.

Configured entirely by [config.yaml](config.yaml), mounted read-only into the
container via [compose.yaml](../../compose.yaml).

## Pipelines

- **traces**: `otlp` receiver → `debug` + `otlp_grpc/aspire` exporters, and
  the `span_metrics` connector (derives RED metrics from spans).
- **metrics**: `otlp` + `span_metrics` + `docker_stats` receivers → a
  `transform` processor (relabels `docker_stats`-sourced metrics'
  `service.name` to `docker-stats`, so they show up as their own service in
  Aspire rather than under `otelcol-contrib`) → `debug` + `otlp_grpc/aspire`
  exporters.
- **logs**: `otlp` receiver → `debug` + `otlp_grpc/aspire` exporters.

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

| Port   | Protocol       | Purpose                        |
|--------|----------------|--------------------------------|
| `4317` | OTLP/gRPC      | Used by `load-generator`       |
| `4318` | OTLP/HTTP      | Used by `geocode`              |

## Docker socket access

The `docker_stats` receiver reads container stats from
`/var/run/docker.sock`, mounted read-only. The image runs as a non-root user
(`10001`) by default, but the socket (as seen inside a Linux container under
Docker Desktop) is owned by `root:root`, mode `660`. `compose.yaml` sets
`user: "10001:0"` — keeps the non-root UID but runs with GID `0` (root
group), which has `rw` on the socket via the group bit. This is the minimal
privilege needed; running as full root isn't necessary.

## Configuration

Reads its own OTLP receiver endpoints from environment variables (set in
[compose.yaml](../../compose.yaml)):

| Environment variable       | Default           | Description                      |
|----------------------------|-------------------|----------------------------------|
| `OTEL_COLLECTOR_HOST`      | `otel-collector`  | Bind host for the OTLP receivers |
| `OTEL_COLLECTOR_PORT_GRPC` | `4317`            | OTLP/gRPC receiver port          |
| `OTEL_COLLECTOR_PORT_HTTP` | `4318`            | OTLP/HTTP receiver port          |

## Debugging

The `debug` exporter logs every received trace/metric/log batch to stdout:

```sh
docker compose logs -f otel-collector
```
