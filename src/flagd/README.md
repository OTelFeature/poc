# flagd

The [flagd](https://flagd.dev/) feature-flag backend. It serves the
telemetry flags to [geocode](../geocode) (through
[otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument))
and [weather](../weather) (through
[otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension)),
and the fault-injection flags to the services' own OpenFeature clients.

Both services use the in-process resolver: flagd pushes the ruleset over the
gRPC sync stream (port `8015`) and each service evaluates it locally. A flag
change takes effect on the next span, with no restart.

## Flag definitions

[flagd.json](flagd.json) is mounted at `/etc/flagd` and loaded with
`--uri file:./etc/flagd/flagd.json`. The committed file is the neutral
baseline (every flag at its default, no targeting) and must equal
[presets/00-baseline.json](presets/00-baseline.json).

The flags, their variants and what they control are specified in
[entity_model.md#flags](../../docs/spec/entity_model.md#flags). Write flag
descriptions into each flag's `metadata`. A flag-level `"description"` key
passes the flagd schema, but the Python provider rejects the whole file.

## Presets

[presets/](presets) holds one complete flag file per demo state.
[STAGE.md](../../STAGE.md) says which beat uses which preset.

```sh
make flag PRESET=<name>               # copy a preset over flagd.json
make flags                            # list the presets
make demo-reset                       # back to 00-baseline, restart k6
docker compose run --rm flag <name>   # same as make flag, Docker only, and waits for flagd
```

Each preset names itself in its flag-set metadata (`"preset": "<name>"`).
The `flag` service ([flag.sh](flag.sh)) polls OFREP until flagd serves that
name and fails after `FLAG_CONFIRM_TIMEOUT` seconds (default 10).
`make flag` only writes the file.

## Tests

`make test` (in the `ci/Dockerfile` image; CI:
[flags.yml](../../.github/workflows/flags.yml)) checks every preset and
`flagd.json`:

1. against the schema `https://flagd.dev/schema/v0/flags.json`,
2. that `flagd.json` equals `00-baseline`,
3. with [test_presets.py](test_presets.py), which evaluates each preset with
   the Python flagd evaluator against the spans of each demo beat and checks
   the preset names itself. When you add a preset, add its expected results
   there.

## Updating a flag

Edit [flagd.json](flagd.json) and save. flagd's file watcher picks it up and
pushes it to both services; nothing restarts. The rule format is the
[flag definition schema](https://flagd.dev/reference/flag-definitions/).

To check what flagd serves right now, ask its OFREP endpoint (port `8016`,
debugging only; the services don't use it):

```sh
curl -s -X POST http://localhost:8016/ofrep/v1/evaluate/flags/telemetryLevel \
  -H "Content-Type: application/json" -d '{"context":{}}'
```

## Ports

| Port | Protocol | Purpose |
|---|---|---|
| `8013` | gRPC | Evaluation (`rpc` resolver). Unused |
| `8015` | gRPC | Sync (`in-process` resolver). Both services use it |
| `8016` | HTTP | [OFREP](https://github.com/open-feature/protocol) evaluation. Debugging and the `flag` service |

## Configuration

| Environment variable | Description |
|---|---|
| `GOMEMLIMIT` | Go soft memory limit (`60MiB`) |
| `OTEL_SERVICE_NAME` | Service name on flagd's own telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector endpoint for flagd's own telemetry |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | OTLP protocol for that export |

## Flag changes with no effect?

- **Stale image.** `docker compose up -d` without `--build` runs the image
  it already has (the prebuilt one from GHCR, or an earlier build), not your
  source. Rebuild with `docker compose up -d --build geocode weather`.
- **mtime not newer.** flagd reloads the file only when its mtime strictly
  increases, so a second write in the same second can be lost. `make flag`
  and the `flag` service handle this; a plain `cp` may not
  ([entity_model.md#flag-file-reload](../../docs/spec/entity_model.md#flag-file-reload)).
- **Check what flagd serves** with the OFREP `curl` above. If flagd serves
  the new value, the problem is in the service, not in flagd.
