# flagsmith-proxy

**Flagsmith mode**, a proof of concept (FR-027, [UC-008 A4](../../docs/spec/use_cases/UC-008-run-demo-on-stage.md),
[TC-008](../../docs/spec/test_cases/TC-008-flagsmith-mode.md)). The demo flags are
authored in [Flagsmith](https://www.flagsmith.com/) instead of
[flagd.json](../flagd/flagd.json), and each stage preset is applied with the
[Flagsmith CLI](https://github.com/Flagsmith/flagsmith-cli). Neither
extension changes: both services still sync from flagd and evaluate in
process (C-002). The flag file stays the default and the offline fallback.
Whether this goes on stage is still open (OQ-16).

```text
Flagsmith CLI ──writes──> Flagsmith ──real-time event──> flagsmith-proxy ──HTTP, 1 s──> flagd ──gRPC sync──> geocode, weather
                              ▲                               │
                              └──── environment document ─────┘  (once per event; fallback poll 60 s)
```

## What is in here

| File | What it does |
|---|---|
| [Dockerfile](Dockerfile) | [Flagsmith's Edge Proxy](https://github.com/Flagsmith/edge-proxy) 2.23.0 plus this package and the Flagsmith CLI v2.0.0, both pinned by digest. Published from `main` as `ghcr.io/otelfeature/poc-flagsmith-proxy` (`main`, `sha-<short>`; amd64 and arm64) by `.github/workflows/images.yml`. It bakes in the presets, so a preset change publishes a new image |
| [otelfeature_flagsmith/app.py](otelfeature_flagsmith/app.py) | The Edge Proxy app with two additions: `GET /api/v1/flagd/flags.json` (the environment as a flagd flag set) and a subscription to Flagsmith's real-time stream |
| [otelfeature_flagsmith/translate.py](otelfeature_flagsmith/translate.py) | Environment document → flagd flag set, for the demo flags only (rules in the [entity model](../../docs/spec/entity_model.md#flagsmith-mode)) |
| [demo.json](demo.json) | The Flagsmith side of the presets: the segments, each flag's overrides in priority order, and which overrides each preset switches on |
| [otelfeature_flagsmith/preset.py](otelfeature_flagsmith/preset.py) | The preset command (`flagsmith-flag`): seed, apply, plan, check |
| [otelfeature_flagsmith/model.py](otelfeature_flagsmith/model.py) | A model of a Flagsmith environment driven by CLI calls, for the tests and the stub |
| [otelfeature_flagsmith/stub_cloud.py](otelfeature_flagsmith/stub_cloud.py) | A stub of Flagsmith Cloud: environment document and real-time stream |

The preset files in [src/flagd/presets](../flagd/presets) stay the source
of every demo state. Flagsmith only decides which variant each flag serves,
and for the gated flags whether their rules reach flagd at all.
The variants, their names and their descriptions come from `00-baseline.json`,
so in Flagsmith mode flagd serves exactly the preset files (UC-008 BR-009).

## In Flagsmith

One project and one environment with real-time updates switched on
(Flagsmith Enterprise; without it, see the fallback poll below). `seed`
creates everything, once (UC-008 BR-013):

- one feature per flag: `otelEnabled`, `telemetryLevel`, `recordSpan`,
  `traceSampleRatio`, `weatherUpstreamFailure`. `recordSpan`,
  `traceSampleRatio` and `weatherUpstreamFailure` are **gated**: switched
  off, flagd gets them as in `00-baseline.json`, without targeting, so the
  services keep their static fast path. They are seeded off, holding the
  value they serve once switched on (`weatherUpstreamFailure` = 0.5, the
  incident).
- five segments, each feature-specific to the flag that uses it:
  `geocode-health`, `weather-jdbc` (on `recordSpan`), `high-error-rate`,
  `production-weather`, `production` (on `traceSampleRatio`).
- every segment override, in priority order. `recordSpan`'s serve `off`
  and apply whenever `recordSpan` is on; `traceSampleRatio`'s are seeded
  switched off and each applies once switched on.

Each beat is then a few switches in the Flagsmith UI (the entity model's
"Beats as switches" table): `03-semconv-rules` is `recordSpan` on,
`traceSampleRatio` on and its `production` override on; `03a-weather-boost`
adds the `production-weather` override; `03b-incident` the
`high-error-rate` override and `weatherUpstreamFailure`. flagd's
`metadata.preset` names the preset the switches match, or `custom`.

A project seeded before this has its segments project-wide; `seed` stops
and names them. Delete them in the UI (Segments) and seed again.

## Running it

Needs a server-side and a client-side key of the environment, and an Admin
API key for the CLI:

```sh
export FLAGSMITH_SERVER_KEY=ser.… FLAGSMITH_CLIENT_KEY=… FLAGSMITH_API_KEY=… FLAGSMITH_PROJECT=…
FS="docker compose -f compose.yaml -f compose.flagsmith.yaml"
$FS pull flagsmith-proxy                # ghcr.io/otelfeature/poc-flagsmith-proxy, or `build` for a local change
$FS run --rm flagsmith-flag seed        # once per project
$FS up -d
$FS run --rm flagsmith-flag 00-baseline
$FS run --rm flagsmith-flag 03a-weather-boost   # prints "flagd serves 03a-weather-boost"
$FS run --rm flagsmith-flag check       # does Flagsmith translate to the preset it names?
$FS run --rm flagsmith-flag plan 03b-incident   # the CLI calls, without running them
```

The preset command makes the same switches with the CLI. It reads the
environment document first and writes only what differs; it creates or
deletes an override only to repair one changed by hand (missing, out of
order, or not in demo.json). Then it waits until the proxy's
flag set equals the preset file (writing every value again if the document
it diffed against was stale) and flagd's OFREP endpoint names the preset,
like the `flag` service. flagd authenticates to the proxy with the
client-side key, so the server-side key stays out of flagd's command line.

Configuration is in the [entity model](../../docs/spec/entity_model.md#flagsmith-mode).
`FLAGSMITH_REALTIME_URL=` (empty) switches the stream off, which leaves only
the fallback poll (`FLAGSMITH_POLL_SECONDS`, default 60).

## What the proxy rejects

Only the comparisons the presets use and their direct counterparts are
translated: `EQUAL`, `NOT_EQUAL`, `GREATER_THAN(_INCLUSIVE)`,
`LESS_THAN(_INCLUSIVE)` in `ALL`, `ANY` and `NONE` rules, and values that are
a variant of their flag. Anything else, such as a regex condition, a
percentage split, `traceSampleRatio` = 0.3, or a switched-off override of a non-boolean flag,
is rejected for the whole environment. The proxy logs
`flagd_translation_rejected` and keeps serving the last good flag set
(UC-008 A5). Features that are no demo flag are ignored.

## Tests

- `make test`: [test_translate.py](test_translate.py). Every preset command,
  applied to the model of the environment, translates back to its preset
  file, in stage order, from every other preset, and blind (no document).
  Plus the translation rules one by one (TC-008 items 1 and 2).
- `make flagsmith-test`: [test_integration.py](test_integration.py) in
  [compose.test.yaml](compose.test.yaml). The real Edge Proxy and flagd run
  against the stub of Cloud: the pushed stage progression within 2 s, the
  fallback poll, and a rejected environment (TC-008 items 3 to 5). CI:
  `.github/workflows/flagsmith.yml`.

Not covered: the CLI's real writes against Flagsmith Cloud. The stub serves
documents the model builds, so this is a rehearsal check (TC-008 item 6).
