# End-to-end suite

Runs the talk's demo beats against the real stack, the same compose services
as on stage, with real flag flips, and asserts on every span the services
export (OTelFeature/poc#35). One test per spec test case
(`docs/spec/test_cases/TC-*.md`).

## Running

Only Docker is needed. From the repo root:

```sh
make e2e
```

This builds the images, starts the stack as its own compose project
(`otelfeature-e2e`: own network, volumes and images, no fixed container
names and no published ports, so it can run next to a demo stack), runs pytest in the runner container, saves logs and
spans to `tests/e2e/.artifacts/`, and tears everything down.

| Variable | Default | Meaning |
|---|---|---|
| `OTELFEATURE_INSTRUMENT_REF` | `main` | Git ref (branch, tag, commit) of otelfeature-instrument that geocode is built with |
| `OTELFEATURE_EXTENSION_REF` | `main` | Git ref of otelfeature-java-extension that weather's agent extension is built from |
| `OTELFEATURE_ENFORCEMENT` | `processor` | Java enforcement mode, `processor` or `sampler` |
| `PYTEST_ARGS` | `-m "not slow"` | Passed to pytest, e.g. `-k baseline -x` |
| `E2E_KEEP` | unset | Set to keep the stack running afterwards (also when startup fails); `make e2e-down` removes it. Run `make e2e-down` before the next `make e2e` |

The extension refs exist so unreleased extension code can be checked with
the demo before it's merged or released. Once releases exist, the defaults
should go back to pinned versions. The stage stack (`make start`) always uses
the pinned versions; only the e2e override builds from git (`ADD` of a git
URL in the Dockerfiles, which re-resolves the ref on every build).

In CI, [e2e.yml](../../.github/workflows/e2e.yml) runs `make e2e` for both
Java enforcement modes on PRs, on `main` and nightly. The refs are
`workflow_dispatch` inputs. Artifacts are uploaded on every run. The images
are built first by `docker/bake-action` with the GitHub Actions layer cache
(one cache scope per image; `make e2e E2E_SKIP_BUILD=1` then uses them). The nightly run also includes
the `slow` statistical tests and runs everything three times in a row
(`pytest --count 3 --repeat-scope session`: the whole suite, then again), the
suite's flake check.

## How it works

[compose.e2e.yaml](../../compose.e2e.yaml) changes the stack for testing:

- **Metrics to a file too.** The services export metrics every second, and
  the collector writes them to `/out/metrics.jsonl` (`MetricLog`), so a test
  can check that metrics keep flowing while tracing is off.
- **Spans to a file.** The collector ([collector.yaml](collector.yaml))
  writes every export request it receives, unprocessed, as one JSON line to
  `/out/spans.jsonl`. [spans.py](spans.py) tails that file. A test sees every
  span that reached the collector, so "no `/health` span since the flip took
  effect" is an exact assertion. No Aspire, no Datadog.
- **Almost no background traffic.** The load generator is off; the tests
  send the requests. The one exception is Docker's healthchecks: they call
  `/health` on every geocode and weather instance (including the hard-floor
  instances) every 2 s, in every flag state.
- **Fast export.** `OTEL_BSP_SCHEDULE_DELAY=100` in both services, and the
  collector's file exporter flushes every 100 ms.
- **Flags on a volume.** flagd reads `/etc/flagd/flagd.json` from the
  `e2e-flags` volume, seeded with `00-baseline`. Tests rewrite it there;
  `src/flagd/flagd.json` is never touched.

### Steps: telling a test's spans apart

Each test gets a `step` fixture with a unique id. Every request the step sends
carries the header `x-e2e-step: <id>`. Both services record that header on
their server span (`OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`
for Python, `OTEL_INSTRUMENTATION_HTTP_SERVER_CAPTURE_REQUEST_HEADERS` for
Java). `step.traces()` returns every span of every trace whose server span
carries the id.

Absence checks ("no span like this any more") can't use the header: a
dropped request has no server span to carry it. They use a window instead.
After the flip, and after a probe shows the new behaviour, call
`step.remark()`; `step.since_mark()` then returns everything exported after
that point. Filter it by service and path, because Docker's healthchecks keep
running. Taking the mark before the flip would let spans still in the 100 ms
export queue leak into the window.

### Staging instances and the error-rate window

The e2e project always runs `geocode-staging` and `weather-staging` (same
images, `deployment.environment.name=staging`, reachable by those names) for
the environment rules of TC-004. Both extensions compute the error rate every
2 s with a minimum of 5 requests (`OTELFEATURE_ERROR_RATE_INTERVAL`,
`OTELFEATURE_ERROR_RATE_MIN_REQUESTS`) instead of 10 s / 10, so the control
loop of TC-005 reacts within seconds.

### Hard-floor instances

compose.e2e.yaml also starts `geocode-sdk-disabled`, `weather-sdk-disabled`,
`geocode-always-off` and `weather-always-off`. They run the same images with
`OTEL_SDK_DISABLED=true` or `OTEL_TRACES_SAMPLER=always_off` and their own
`service.instance.id`, so a test can check that no flag gets around those env
vars.

### Barriers instead of sleeps

`wait_until(check, timeout)` polls a check that returns what is still
missing (or `None`), and fails with that description when the timeout
passes. Tests that depend on the error rate (TC-005, the 03b beat) need
continuous traffic, at least the minimum requests per 2 s interval, so they
must not put an absence window between their batches. The only deliberate wait is the absence window: `step.quiet(...)`
waits `QUIET_SECONDS` (2 s, `E2E_QUIET_SECONDS`) before it collects spans,
because proving that nothing arrived takes some time.

After a flip, `step.wait_tracing(service, traced=...)` is the behaviour
barrier for "is this request traced at all". For a change *inside* a traced
request (for example weather's DB spans), `step.wait_for_trace(send,
satisfied)` sends a fresh request per poll and waits until one probe's trace
satisfies the check. Both return the flip latency. `wait_tracing` sends a probe request (its own header value) on every poll.
`traced=True` is done once any probe shows up. `traced=False` is done once
the last three probes are older than `QUIET_SECONDS` and none of them
showed up. It returns the flip latency (when the first probe with the new
behaviour was sent), which tests compare against `FLIP_BUDGET_SECONDS` (5 s,
`E2E_FLIP_BUDGET_SECONDS`): the spec's "visible within 2 s" with CI headroom.

Flag flips (`flags.apply("02-quiet-noise")`) go through [flags.py](flags.py):

1. Copy the preset with an extra throwaway flag `e2eRevision` = a fresh id.
2. Write it to a temp file with an mtime at least 1 s newer than the old
   file, then rename it over the old file. flagd v0.17 with `--uri file:`
   uses its polling (`fileinfo`) watcher, which reloads only when the mtime
   increases, so a rewrite within the same timestamp tick would be ignored.
3. Poll flagd's OFREP endpoint until it serves the new `e2eRevision`.

The services receive the same push over the sync stream, but on their own
schedule. A test that depends on a behaviour change probes for it (sends
requests until the new behaviour shows) before counting.

## Adding a test for a test case

1. Name it after the spec test case: `test_tc00N_<what>.py`, one test per
   TC Flow, with the TC's steps as comments.
2. Use the `step` fixture. It starts and ends on `00-baseline`.
3. Flip flags with `flags.apply("<preset>")`, or `flags.write(config)` for a
   variation that isn't a stage preset.
4. After a flip, wait with `step.wait_tracing(...)` (behaviour barrier; it
   also returns the flip latency to check against the budget); otherwise
   `wait_until`. Assert presence through `step.traces()`, absence
   through `step.remark()` + `step.since_mark()` (after the flip has taken
   effect), and tree shape with `tree_problem` (pass `remote_parents` for a
   request the test sent with a `traceparent`).
5. Mark statistical or long tests `@pytest.mark.slow` (nightly only).
6. In the TC's **Validation** list (spec), mark which checks are now
   automated.

## Files

| File | What |
|---|---|
| [conftest.py](conftest.py) | Fixtures: `spans`, `flags`, `step`, `baseline` |
| [spans.py](spans.py) | OTLP/JSON span parsing, `wait_until`, `tree_problem` |
| [flags.py](flags.py) | Preset application with the mtime and revision barrier |
| [collector.yaml](collector.yaml) | e2e collector: OTLP in, JSON file out |
| [test_baseline.py](test_baseline.py) | Baseline: complete traces from both services |
| [test_tc001_kill_switch.py](test_tc001_kill_switch.py) | TC-001: `otelEnabled=false` and `telemetryLevel=OFF` stop all spans in both services while their metrics keep arriving; baseline brings complete traces back |
| [test_hard_floors.py](test_hard_floors.py) | TC-001 V6 (spans only) / V7, TC-004 V8 (`always_off` half): `OTEL_SDK_DISABLED=true` and `OTEL_TRACES_SAMPLER=always_off` instances export nothing, even with flags on and a sampled `traceparent` |
| [test_tc002_drop_noisy_spans.py](test_tc002_drop_noisy_spans.py) | TC-002: `02-quiet-noise` drops geocode `/health` (also a proxied one with a sampled `traceparent`, with a positive control at baseline) and weather's JDBC spans; everything else stays, trees connected; baseline restores both. Plus a non-stage variation the Java *sampler* can decide (weather root, DB leaves by `db.system`, a proxied `/geocode` with its downstream calls) |
| [test_tc004_target_sampling.py](test_tc004_target_sampling.py) | TC-004: `traceSampleRatio` rules on `deployment.environment.name` and `service.name`, deterministic (0.0 / 1.0) against production and staging instances, built on `00-baseline` (the stage presets keep geocode's `/health` drop rule); `03-semconv-rules`' real 0.1 as a `slow` statistical test |
| [test_tc005_control_loop.py](test_tc005_control_loop.py) | TC-005: `weatherUpstreamFailure` errors raise weather's error rate in its evaluation context, a rule on it samples weather fully while error-free geocode traffic stays unsampled; recovery from a measured 0.0 rate when the failures stop |
| [test_tc006_stage_progression.py](test_tc006_stage_progression.py) | TC-006: the stage presets in stage order with no resets (00 → 01 → 02 → 03 → 03a → 03b → 03a), each beat checked for its core effect (tracing off/on, the drops, production sampled down with staging full, weather boosted to about half with geocode at 0.1, the incident's loop sampling weather fully). Statistical bands, on every PR. Plus three flips within one second ending in the last preset's state (V7) |
| [checks.py](checks.py) | Shared trace-shape checks (complete request trace, DB and stub client spans) |
| [../../ci/Dockerfile](../../ci/Dockerfile) | Toolchain image (also `make test` / `make shell`): Python, uv, locked test and preset-check deps |
