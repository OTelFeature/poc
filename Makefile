.PHONY: build start start-live start-staging prepare-offline stop flag flags demo-reset validate-flags

PRESET_DIR := src/flagd/presets
PRESETS := $(sort $(basename $(notdir $(wildcard $(PRESET_DIR)/*.json))))

# Real API endpoints, used only by `make start-live`. Plain `make start` talks
# to the stub-apis container so the stack runs with no network at all.
LIVE_NOMINATIM_URL := https://nominatim.openstreetmap.org/search
LIVE_OPEN_METEO_GEOCODING_URL := https://geocoding-api.open-meteo.com/v1/search
LIVE_OPEN_METEO_FORECAST_URL := https://api.open-meteo.com/v1/forecast

build:
	docker compose --profile staging build

# Run once while online: pulls every image and builds the services, so that
# `make start` afterwards needs no network (it never rebuilds on its own).
prepare-offline:
	docker compose --profile staging pull --ignore-buildable
	docker compose --profile staging build

start-live: export NOMINATIM_URL := $(LIVE_NOMINATIM_URL)
start-live: export OPEN_METEO_GEOCODING_URL := $(LIVE_OPEN_METEO_GEOCODING_URL)
start-live: export OPEN_METEO_FORECAST_URL := $(LIVE_OPEN_METEO_FORECAST_URL)
start-live: start

# Adds geocode-staging, weather-staging and a second k6 next to the
# production pair (deployment.environment.name=staging vs production).
start-staging: export COMPOSE_PROFILES := staging
start-staging: start

start:
	docker compose up -d
	@printf '%s\n' ''
	@printf '%s\n' '               ██████████████████████████████████████████████████             '
	@printf '%s\n' '            ████████████████████████████████████████████████████████          '
	@printf '%s\n' '          ████████████████████████████████████████████████████████████        '
	@printf '%s\n' '        ████████████████████████████████████████████████████████████████      '
	@printf '%s\n' '      ████████████████████████████████████████               ████████████     '
	@printf '%s\n' '     ██████████████████████████████████████              █      ███████████   '
	@printf '%s\n' '    ██████████████████████████████████████             ████      ███████████  '
	@printf '%s\n' '   █████████████████████████████████████                 ████      █████████  '
	@printf '%s\n' '   ████████████████████████████████████              ████  ████     █████████ '
	@printf '%s\n' '  ████████████████████████████████████             ████████ ██      █████████ '
	@printf '%s\n' '  ████████████████████████████████████               █  ███          ████████ '
	@printf '%s\n' '  ████████████████████████████████████           ███  ███            ████████ '
	@printf '%s\n' '  ████████████████████████████████████         █████ █  █            ████████ '
	@printf '%s\n' '  ████████████████████████████████████         ████   ██            █████████ '
	@printf '%s\n' '   ████████████████████████████████████      ██  █                  █████████ '
	@printf '%s\n' '   ████████████████████████████████████    ███                     ██████████ '
	@printf '%s\n' '   ██████████████████████████████████████    █                    ██████████  '
	@printf '%s\n' '    ██████████████████████████████████████                      ███████████   '
	@printf '%s\n' '     ███████████████████████████████████████                  ████████████    '
	@printf '%s\n' '      ██████████████████████████████████████████          ███████████████     '
	@printf '%s\n' '        ███████████████████████████████████████████████████████████████       '
	@printf '%s\n' '         █████████████████████████████████████████████████████████████        '
	@printf '%s\n' '            ███████████████████████████████████████████████████████           '
	@printf '%s\n' '               █████████████████████████████████████████████████              '
	@printf '%s\n' ''
	@printf '%s\n' ' ███  █████ █████ █     █████ █████  ███  █████ █   █ ████  █████    ████   ███   ███  '
	@printf '%s\n' '█   █   █   █     █     █     █     █   █   █   █   █ █   █ █        █   █ █   █ █     '
	@printf '%s\n' '█   █   █   ████  █     ████  ████  █████   █   █   █ ████  ████     ████  █   █ █     '
	@printf '%s\n' '█   █   █   █     █     █     █     █   █   █   █   █ █  █  █        █     █   █ █     '
	@printf '%s\n' ' ███    █   █████ █████ █     █████ █   █   █    ███  █   █ █████    █      ███   ███  '
	@printf '%s\n' ''
	@printf '%s\n' '         Access the following services:'
	@printf '%s\n' '         - Geocode Service (health): http://localhost:8000/health'
	@printf '%s\n' '         - Geocode Service (POST):'
	@printf '%s\n' '             curl -s -X POST http://localhost:8000/geocode \'
	@printf '%s\n' '                  -H "Content-Type: application/json" \'
	@printf '%s\n' "                  -d '{\"city\": \"linz\", \"country\": \"austria\"}'"
	@printf '%s\n' '         - Aspire Dashboard: http://localhost:18888'
	@printf '%s\n' '         - Staging twins (make start-staging): geocode :8002, weather :8003'

stop:
	docker compose --profile staging down

# ── Stage controls (see STAGE.md) ──────────────────────────────────────
# `make flag PRESET=02-quiet-noise` replaces src/flagd/flagd.json with a
# preset. flagd watches that file and pushes the change to both services, so
# the flip shows up on the next span. apply-preset.sh renames a temp file
# over it (atomic) with a strictly newer mtime, so no watcher misses a quick
# second flip. flagd.json is tracked and equal to 00-baseline;
# `make demo-reset` puts it back.
flag:
	@test -n "$(PRESET)" || { echo "usage: make flag PRESET=<name>, one of: $(PRESETS)"; exit 1; }
	@test -f "$(PRESET_DIR)/$(PRESET).json" || { echo "unknown preset '$(PRESET)', one of: $(PRESETS)"; exit 1; }
	sh src/flagd/apply-preset.sh "$(PRESET_DIR)/$(PRESET).json" src/flagd/flagd.json
	@echo "flagd.json is now $(PRESET)"

flags:
	@printf '%s\n' $(PRESETS)

# Back to baseline flags, and restart k6 so traffic starts fresh (its run
# also ends after DURATION). The staging k6 is restarted only if it exists.
demo-reset:
	@$(MAKE) --no-print-directory flag PRESET=00-baseline
	docker compose restart load-generator
	@if [ -n "$$(docker compose --profile staging ps -a -q load-generator-staging)" ]; then \
		docker compose --profile staging restart load-generator-staging; \
	fi

# ── Toolchain image (ci/Dockerfile, NFR-016) ───────────────────────────
# `make test` and `make shell` run in the toolchain image with the repo
# mounted at /workspace, as the host user, so the only host requirement is
# Docker. It is the same image `make e2e` runs the suite in (same tag).
# CI (flags.yml) builds it with a layer cache and runs `make test-only`.
CI_IMAGE ?= otelfeature-e2e-runner
DOCKER_USER ?= $(shell id -u):$(shell id -g)
CI_RUN = docker run --rm --user "$(DOCKER_USER)" -e HOME=/tmp \
	-v "$(CURDIR)":/workspace -w /workspace
FLAGD_SCHEMA := https://flagd.dev/schema/v0/flags.json

.PHONY: image test test-only shell

image:
	docker build -f ci/Dockerfile -t $(CI_IMAGE) .

test: image
	@$(MAKE) --no-print-directory test-only

# The checks that need no stack, the same as CI: every preset against the
# flagd schema (fetched, so this needs network), committed flagd.json =
# baseline, and the Python flagd provider's evaluation of every preset.
test-only:
	$(CI_RUN) --entrypoint sh $(CI_IMAGE) -ec '\
		check-jsonschema --schemafile $(FLAGD_SCHEMA) src/flagd/flagd.json $(PRESET_DIR)/*.json; \
		cmp src/flagd/flagd.json $(PRESET_DIR)/00-baseline.json; \
		python src/flagd/test_presets.py'

# The services' own unit tests (OTelFeature/poc#75), in the test stage of
# each service's Dockerfile: the same pinned builder images as the stage
# images, so they need only Docker. A cached stage means the tests passed
# on the same inputs. CI: unit.yml.
.PHONY: unit-test
unit-test:
	docker build --progress=plain --target test src/weather
	docker build --progress=plain --target test src/geocode

shell: image
	$(CI_RUN) -it --entrypoint bash $(CI_IMAGE)

# Older name of `make test`, kept for muscle memory.
validate-flags: test

# ── End-to-end suite (tests/e2e, OTelFeature/poc#35) ───────────────────
# Needs only Docker. Runs as its own compose project, so it can run next to
# a demo stack. By default geocode and weather use the pinned extension
# releases, like the stage (C-006, C-013): geocode's uv.lock and weather's
# OTELFEATURE_EXTENSION_VERSION. A git ref (branch, tag or commit) builds an
# extension from source instead, only when passed explicitly, to check
# unreleased extension code with the demo:
#
#   make e2e
#   make e2e OTELFEATURE_INSTRUMENT_REF=feat/x OTELFEATURE_EXTENSION_REF=main
#   make e2e OTELFEATURE_ENFORCEMENT=sampler PYTEST_ARGS="-k baseline -x"
#   make e2e E2E_KEEP=1      # leave the stack up afterwards (make e2e-down)
#   make e2e E2E_SKIP_BUILD=1  # images already built (CI builds them with a layer cache)
#
# Logs and the collected spans land in tests/e2e/.artifacts/.
E2E_PROJECT := otelfeature-e2e
E2E := docker compose -p $(E2E_PROJECT) -f compose.yaml -f compose.e2e.yaml
E2E_ARTIFACTS := tests/e2e/.artifacts
# `release` = the pinned release; anything else is a git ref to build from.
OTELFEATURE_INSTRUMENT_REF ?= release
OTELFEATURE_EXTENSION_REF ?= release
# Dockerfile stage for each extension, derived from the refs above.
OTELFEATURE_INSTRUMENT_SOURCE := $(if $(filter release,$(OTELFEATURE_INSTRUMENT_REF)),lock,git)
OTELFEATURE_EXTENSION_SOURCE := $(if $(filter release,$(OTELFEATURE_EXTENSION_REF)),release,git)
OTELFEATURE_ENFORCEMENT ?= processor
PYTEST_ARGS ?= -m "not slow"
export OTELFEATURE_INSTRUMENT_REF OTELFEATURE_EXTENSION_REF OTELFEATURE_ENFORCEMENT
export OTELFEATURE_INSTRUMENT_SOURCE OTELFEATURE_EXTENSION_SOURCE

.PHONY: e2e e2e-build e2e-up e2e-test e2e-artifacts e2e-down

e2e: $(if $(filter 1,$(E2E_SKIP_BUILD)),,e2e-build)
	@$(MAKE) --no-print-directory e2e-up || { $(MAKE) --no-print-directory e2e-artifacts; [ -n "$(E2E_KEEP)" ] || $(MAKE) --no-print-directory e2e-down; exit 1; }
	@rc=0; $(MAKE) --no-print-directory e2e-test || rc=$$?; $(MAKE) --no-print-directory e2e-artifacts; [ -n "$(E2E_KEEP)" ] || $(MAKE) --no-print-directory e2e-down; exit $$rc

e2e-build:
	$(E2E) --profile runner build

e2e-up:
	$(E2E) up -d --wait --wait-timeout 180

e2e-test:
	$(E2E) --profile runner run --rm e2e $(PYTEST_ARGS)

e2e-artifacts:
	@mkdir -p $(E2E_ARTIFACTS)
	@rm -f $(E2E_ARTIFACTS)/compose.log $(E2E_ARTIFACTS)/spans.jsonl $(E2E_ARTIFACTS)/metrics.jsonl
	-@$(E2E) logs --no-color --timestamps > $(E2E_ARTIFACTS)/compose.log 2>&1
	-@$(E2E) cp otel-collector:/out/spans.jsonl $(E2E_ARTIFACTS)/spans.jsonl 2>/dev/null
	-@$(E2E) cp otel-collector:/out/metrics.jsonl $(E2E_ARTIFACTS)/metrics.jsonl 2>/dev/null
	@echo "e2e artifacts in $(E2E_ARTIFACTS)/"

e2e-down:
	$(E2E) --profile runner down -v --remove-orphans

# ── Spec lint (docs/spec, AIUP /spec-review part A) ─────────────────────
# Same command as .github/workflows/spec-lint.yml; needs only Docker.
#   make spec-lint                                    # --strict, as in CI
#   make spec-lint SPEC_LINT_ARGS=--update-baseline   # accept current findings
SPEC_LINT_IMAGE := python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
SPEC_LINT_ARGS ?= --strict

.PHONY: spec-lint
spec-lint:
	docker run --rm -u "$$(id -u):$$(id -g)" -v "$(CURDIR)":/w -w /w $(SPEC_LINT_IMAGE) sh ci/spec-lint.sh $(SPEC_LINT_ARGS)

# ── Measurement harness (bench/, OTelFeature/poc#27, UC-003, TC-003) ───
# Needs only Docker. Its own compose project on the pinned releases with the
# stage's configuration and normal traffic (BENCH_RATE multiplies the
# business requests and the health checks). Six runs, each from freshly
# created geocode, weather and load generator, warmed up first:
#   baseline, noop (a targeted rule that never matches: the decision cost,
#   UC-003 BR-006) and 02-quiet-noise (Demo 2), each with weather in
#   processor mode and again in sampler mode (decision D3).
# Prints per-service tables and saves them, with the raw results, to
# bench/.results/. Takes about 6 x (BENCH_WARMUP + BENCH_SECONDS) seconds.
#
#   make bench
#   make bench BENCH_SECONDS=600 BENCH_RATE=5
BENCH_PROJECT := otelfeature-bench
BENCH := docker compose -p $(BENCH_PROJECT) -f compose.yaml -f compose.e2e.yaml -f compose.bench.yaml
BENCH_WARMUP ?= 120
BENCH_SECONDS ?= 240
BENCH_RATE ?= 1
BENCH_HEALTHCHECK_RATE := $(shell echo $$((2 * $(BENCH_RATE))))
export BENCH_RATE BENCH_HEALTHCHECK_RATE
BENCH_TOOL = $(BENCH) --profile bench run --rm -e BENCH_SETTINGS="warm-up $(BENCH_WARMUP) s, BENCH_RATE=$(BENCH_RATE)" bench

.PHONY: bench bench-down

# bash: dash doesn't run an EXIT trap on Ctrl-C.
bench: SHELL := /bin/bash
bench:
	$(BENCH) --profile bench build
	@mkdir -p bench/.results
	@set -e; \
	cleanup() { \
		rc=$$?; \
		if [ $$rc -ne 0 ]; then $(BENCH) logs --no-color --tail=200 > bench/.results/failed-run.log 2>&1 || true; \
			echo "bench failed ($$rc); logs in bench/.results/failed-run.log"; fi; \
		$(BENCH) --profile bench down -v --remove-orphans; \
	}; \
	trap cleanup EXIT; \
	trap 'exit 130' INT TERM; \
	OTELFEATURE_ENFORCEMENT=processor $(BENCH) up -d --wait --wait-timeout 180; \
	run() { \
		OTELFEATURE_ENFORCEMENT=$$3 $(BENCH) up -d --wait --wait-timeout 180 --force-recreate geocode weather load-generator; \
		$(BENCH_TOOL) apply $$2; \
		$(BENCH_TOOL) measure $$1 --mode $$3 --warmup $(BENCH_WARMUP) --seconds $(BENCH_SECONDS); \
	}; \
	run baseline baseline processor; \
	run noop noop processor; \
	run quiet-noise-processor quiet-noise processor; \
	run baseline-sampler baseline sampler; \
	run noop-sampler noop sampler; \
	run quiet-noise-sampler quiet-noise sampler; \
	out=bench/.results/report-$$(date -u +%Y%m%dT%H%M%SZ).md; \
	$(BENCH_TOOL) report > $$out; \
	cat $$out; \
	echo "saved $$out"

bench-down:
	$(BENCH) --profile bench down -v --remove-orphans
