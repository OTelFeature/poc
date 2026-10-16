# Measurement harness

`make bench` measures what the Demo 2 rules save, at the service, and what
the targeted flag decision costs (OTelFeature/poc#27, UC-003, TC-003). It also
gives the numbers for decision D3 (Java `processor` vs `sampler` mode, OQ-1).

```sh
make bench                                   # stage load, 45 s warm-up, 120 s per run
make bench BENCH_SECONDS=300 BENCH_RATE=5    # longer windows, 5x the load
```

Only Docker is needed. It runs its own compose project (`otelfeature-bench`)
on the pinned releases, layered on the e2e override (`compose.e2e.yaml`, for
the flag volume and the collector span file) and `compose.bench.yaml`: the
load generator on, the staging and hard-floor instances off.

## Runs

| Run | Flags | weather mode |
|---|---|---|
| `baseline` | `00-baseline` | processor |
| `noop` | baseline plus a `recordSpan` rule that reads `url.path` but never matches | processor |
| `quiet-noise-processor` | `02-quiet-noise` (Demo 2) | processor |
| `quiet-noise-sampler` | `02-quiet-noise` | sampler |

Each run applies its flags (the e2e flag helper: newer mtime and an OFREP
barrier), recreates `weather` when the mode changes, warms up for
`BENCH_WARMUP` seconds and measures for `BENCH_SECONDS`.

## Numbers (UC-003 BR-007)

Per service (`geocode`, `weather`):

- **CPU %**: container CPU time in the window / window length, in % of one core.
- **RSS MB**: container memory usage minus page cache, at the end of the window.
- **spans/s**: spans with that `service.name` the collector received in the window.
- **export KB/s**: those spans as OTLP protobuf (`ResourceSpans`), uncompressed.

The **decision cost** is the `noop` run's CPU minus the baseline's
(UC-003 BR-006): every span is decided with a built evaluation context, and
nothing is dropped.

The report is printed and saved to `bench/.results/report-<UTC time>.md`. Run
it twice to check reproducibility (±10 % per metric, NFR-011).

## Live view on stage

No extra component: the dashboard's span-metrics chart per service
(`traces.span.metrics.calls`, grouped by `service.name`) drops within seconds
of the flip (UC-003 A3).
