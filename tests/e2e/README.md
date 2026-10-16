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
(`otelfeature-e2e`, no fixed container names or host ports, so it can run
next to a demo stack), runs pytest in the runner container, saves logs and
spans to `tests/e2e/.artifacts/`, and tears everything down.

| Variable | Default | Meaning |
|---|---|---|
| `OTELFEATURE_INSTRUMENT_REF` | `main` | Git ref (branch, tag, commit) of otelfeature-instrument that geocode is built with |
| `OTELFEATURE_EXTENSION_REF` | `main` | Git ref of otelfeature-java-extension that weather's agent extension is built from |
| `OTELFEATURE_ENFORCEMENT` | `processor` | Java enforcement mode, `processor` or `sampler` |
| `PYTEST_ARGS` | `-m "not slow"` | Passed to pytest, e.g. `-k baseline -x` |
| `E2E_KEEP` | unset | Set to keep the stack running afterwards; `make e2e-down` removes it |

The extension refs exist so unreleased extension code can be checked with
the demo before it's merged or released. Once releases exist, the defaults
should go back to pinned versions. The stage stack (`make start`) always uses
the pinned versions; only the e2e override builds from git (`ADD` of a git
URL in the Dockerfiles, which re-resolves the ref on every build).

In CI, [e2e.yml](../../.github/workflows/e2e.yml) runs `make e2e` for both
Java enforcement modes on PRs, on `main` and nightly. The refs are
`workflow_dispatch` inputs. Artifacts are uploaded on every run.

## How it works

[compose.e2e.yaml](../../compose.e2e.yaml) changes the stack for testing:

- **Spans to a file.** The collector ([collector.yaml](collector.yaml))
  writes every export request it receives, unprocessed, as one JSON line to
  `/out/spans.jsonl`. [spans.py](spans.py) tails that file. A test sees every
  span that reached the collector, so "no `/health` span" is an exact
  assertion. No Aspire, no Datadog.
- **No background traffic.** The load generator is off; the tests send
  every request themselves.
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
carries the id, and `spans.since(step.mark)` returns everything exported
after the step started (for absence checks: a dropped request has no server
span to carry the header).

### Barriers instead of sleeps

There are no fixed sleeps. `wait_until(check, timeout)` polls a check that
returns what is still missing (or `None`), and fails with that description
when the timeout passes.

Flag flips (`flags.apply("02-quiet-noise")`) go through [flags.py](flags.py):

1. Copy the preset with an extra throwaway flag `e2eRevision` = a fresh id.
2. Write it to a temp file with an mtime strictly newer than the old file,
   then rename it over the old file. flagd v0.17 polls the mtime and ignores
   a rewrite within the same timestamp tick.
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
4. Wait with `wait_until`. Assert presence through `step.traces()`, absence
   through `spans.since(step.mark)`, and tree shape with `tree_problem`.
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
| [../../ci/Dockerfile](../../ci/Dockerfile) | Runner image: Python, uv, locked test deps |
