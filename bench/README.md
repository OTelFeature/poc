# Measurement harness

`make bench` measures what Demo 2 (`telemetryLevel` IO) saves, at the service, and what
the targeted flag decision costs (OTelFeature/poc#27, UC-003, TC-003). It also
gave the numbers for decision D3 (Java `processor` vs `sampler` mode, OQ-1: decided `processor`).

```sh
make bench                                   # stage load, 120 s warm-up, 240 s per run (~36 min)
make bench BENCH_SECONDS=600 BENCH_RATE=5    # longer windows, 5x the requests and health checks
```

Only Docker is needed. It runs its own compose project (`otelfeature-bench`)
on the pinned releases, layered on the e2e override (`compose.e2e.yaml`, for
the flag volume and the collector span file) and `compose.bench.yaml`, which
puts the services back on the **stage** settings (5 s export batches, 60 s
metric export, 10 s error-rate window, 20–120 ms stub latency), turns the load
generator on and the staging and hard-floor instances off.

## Runs

| Run | Flags | weather mode |
|---|---|---|
| `baseline` | `00-baseline` | processor |
| `noop` | baseline plus a `recordSpan` rule that reads `url.path` but never matches | processor |
| `quiet-noise-processor` | `02-quiet-noise` (Demo 2: `telemetryLevel` IO, no `INTERNAL` spans) | processor |
| `baseline-sampler` | `00-baseline` | sampler |
| `noop-sampler` | as `noop` | sampler |
| `quiet-noise-sampler` | `02-quiet-noise` | sampler |

Every run recreates `geocode`, `weather` (with the run's
`OTELFEATURE_ENFORCEMENT`) and the load generator, so each starts from the
same state, applies its flags (the e2e flag helper: newer mtime and an OFREP
barrier), warms up for `BENCH_WARMUP` seconds and measures for
`BENCH_SECONDS`. Deltas compare with the baseline of the same Java mode.

## Numbers (UC-003 BR-007)

Per service (`geocode`, `weather`):

- **CPU %**: container CPU time over the window, % of one core, ± the standard
  deviation of 5 s samples.
- **Memory MB**: container memory usage minus inactive file cache, averaged
  over the window (what `docker stats` shows, not the process RSS).
- **req/s**: business requests (server spans not on `/health`). They must be
  the same in every run; the report warns when they differ by more than 5%.
- **spans/s**: spans of that service instance the collector received.
- **export KB/s**: those spans as OTLP protobuf (`ResourceSpans`), uncompressed.

The **decision cost** per Java mode is the `noop` run's CPU minus the baseline's
(UC-003 BR-006), as % of one core and in µs per span. geocode's two Demo 2
runs have the same configuration (the mode is Java-only), so their difference
is printed as the run-to-run noise.

The report and the raw per-run JSON are saved to `bench/.results/` (owned by
root on a native Docker engine). Run it twice to check reproducibility
(NFR-011): spans and bytes within 10%; CPU only beyond the run-to-run noise, the largest CPU difference among geocode's identically configured runs; memory is not compared (OQ-15). If a run fails, the
last service logs are in `bench/.results/failed-run.log`.

## Live view on stage

No extra component: the dashboard's span-metrics chart per service
(`traces.span.metrics.calls`, grouped by `service.name`) drops within seconds
of the flip (UC-003 A3).
