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
| [Dockerfile](Dockerfile) | [Flagsmith's Edge Proxy](https://github.com/Flagsmith/edge-proxy) 2.23.0 plus this package and the Flagsmith CLI v2.0.0, both pinned by digest |
| [otelfeature_flagsmith/app.py](otelfeature_flagsmith/app.py) | The Edge Proxy app with two additions: `GET /api/v1/flagd/flags.json` (the environment as a flagd flag set) and a subscription to Flagsmith's real-time stream |
| [otelfeature_flagsmith/translate.py](otelfeature_flagsmith/translate.py) | Environment document → flagd flag set, for the demo flags only (rules in the [entity model](../../docs/spec/entity_model.md#flagsmith-mode)) |
| [demo.json](demo.json) | The Flagsmith side of the presets: the segments, each flag's overrides in priority order, and which overrides each preset switches on |
| [otelfeature_flagsmith/preset.py](otelfeature_flagsmith/preset.py) | The preset command (`flagsmith-flag`): seed, apply, plan, check |
| [otelfeature_flagsmith/model.py](otelfeature_flagsmith/model.py) | A model of a Flagsmith environment driven by CLI calls, for the tests and the stub |
| [otelfeature_flagsmith/stub_cloud.py](otelfeature_flagsmith/stub_cloud.py) | A stub of Flagsmith Cloud: environment document and real-time stream |

The preset files in [src/flagd/presets](../flagd/presets) stay the source
of every demo state. Flagsmith only decides which variant each flag serves.
The variants, their names and their descriptions come from `00-baseline.json`,
so in Flagsmith mode flagd serves exactly the preset files (UC-008 BR-009).

## In Flagsmith

One project and one environment with real-time updates switched on
(Flagsmith Enterprise). `seed` creates:

- one feature per flag (`otelEnabled`, `telemetryLevel`, `recordSpan`,
  `traceSampleRatio`, `weatherUpstreamFailure`), plus `demoPreset`, which
  names the preset last applied. For the two boolean flags the feature's
  on/off state is the value.
- five segments: `geocode-health`, `weather-jdbc`, `high-error-rate`,
  `production-weather` and `production`, built the way the Flagsmith UI
  builds them (all of the conditions).

A preset then creates and deletes segment overrides and sets the values.
`03b-incident` in Flagsmith, for example: `traceSampleRatio` overrides
`high-error-rate` → 1.0, `production-weather` → 0.5, `production` → 0.1,
in that order; `weatherUpstreamFailure` = 0.5.

## Running it

Needs a server-side and a client-side key of the environment, and an Admin
API key for the CLI:

```sh
export FLAGSMITH_SERVER_KEY=ser.… FLAGSMITH_CLIENT_KEY=… FLAGSMITH_API_KEY=… FLAGSMITH_PROJECT=…
FS="docker compose -f compose.yaml -f compose.flagsmith.yaml"
$FS build flagsmith-proxy               # not published yet (OQ-16)
$FS run --rm flagsmith-flag seed        # once per project
$FS up -d
$FS run --rm flagsmith-flag 00-baseline
$FS run --rm flagsmith-flag 03a-weather-boost   # prints "flagd serves 03a-weather-boost"
$FS run --rm flagsmith-flag check       # does Flagsmith translate to the preset it names?
$FS run --rm flagsmith-flag plan 03b-incident   # the CLI calls, without running them
```

The preset command reads the environment document first and writes only
what differs, `demoPreset` last. Then it waits on flagd's OFREP endpoint
until the flag set names the preset, like the `flag` service.

Configuration is in the [entity model](../../docs/spec/entity_model.md#flagsmith-mode).
`FLAGSMITH_REALTIME_URL=` (empty) switches the stream off, which leaves only
the fallback poll (`FLAGSMITH_POLL_SECONDS`, default 60).

## What the proxy rejects

Only the comparisons the presets use and their direct counterparts are
translated: `EQUAL`, `NOT_EQUAL`, `GREATER_THAN(_INCLUSIVE)`,
`LESS_THAN(_INCLUSIVE)` in `ALL`, `ANY` and `NONE` rules, and values that are
a variant of their flag. Anything else, such as a regex condition,
`traceSampleRatio` = 0.3, or a switched-off override of a non-boolean flag,
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
