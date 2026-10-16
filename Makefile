.PHONY: build start start-live start-staging prepare-offline stop flag flags demo-reset validate-flags extension-sources

# ── Extension source (FR-027, UC-008 A3) ───────────────────────────────
# By default geocode and weather use the pinned, released extensions. To
# rehearse with unreleased code, build them from git refs:
#
#   make start-staging EXT_REF=main
#   make start OTELFEATURE_INSTRUMENT_REF=feat/x OTELFEATURE_EXTENSION_REF=v0.4.0
#
# A ref counts only from the command line or the environment (the e2e
# defaults further down don't switch the stage stack to git). Images keep
# what they were built from until rebuilt: `make build` goes back to pinned.
ifneq ($(EXT_REF),)
OTELFEATURE_INSTRUMENT_REF := $(EXT_REF)
OTELFEATURE_EXTENSION_REF := $(EXT_REF)
endif
# An empty value doesn't count (make start OTELFEATURE_INSTRUMENT_REF=).
GIVEN = $(and $($(1)),$(filter command line environment environment override,$(origin $(1))))
INSTRUMENT_FROM_GIT := $(or $(EXT_REF),$(call GIVEN,OTELFEATURE_INSTRUMENT_REF))
EXTENSION_FROM_GIT := $(or $(EXT_REF),$(call GIVEN,OTELFEATURE_EXTENSION_REF))
STAGE_FROM_GIT := $(INSTRUMENT_FROM_GIT)$(EXTENSION_FROM_GIT)

build start prepare-offline: export OTELFEATURE_INSTRUMENT_SOURCE := $(if $(INSTRUMENT_FROM_GIT),git,lock)
build start prepare-offline: export OTELFEATURE_EXTENSION_SOURCE := $(if $(EXTENSION_FROM_GIT),git,release)
build start prepare-offline: export OTELFEATURE_INSTRUMENT_REF := $(OTELFEATURE_INSTRUMENT_REF)
build start prepare-offline: export OTELFEATURE_EXTENSION_REF := $(OTELFEATURE_EXTENSION_REF)

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
# Takes EXT_REF / the ref variables too; without them it builds pinned.
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
	$(if $(STAGE_FROM_GIT),docker compose --profile staging build geocode weather geocode-staging weather-staging)
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
	@$(MAKE) --no-print-directory extension-sources

# Which extension each running app container was built with (image labels).
extension-sources:
	@printf '%s\n' '' '         Extensions in the running images:'
	@for svc in geocode weather geocode-staging weather-staging; do \
		id=$$(docker compose --profile staging ps -q $$svc 2>/dev/null); \
		[ -n "$$id" ] || continue; \
		label() { docker inspect -f "{{index .Config.Labels \"io.otelfeature.extension.$$1\"}}" $$id; }; \
		case "$$(label source)" in \
			git) desc="git $$(label ref)" ;; \
			lock) desc="pinned (uv.lock)" ;; \
			release) desc="pinned release $$(label version)" ;; \
			*) desc="unknown (image built before the labels; make build)" ;; \
		esac; \
		printf '         - %s: %s\n' "$$svc" "$$desc"; \
	done

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

# Same checks as CI: flagd schema (needs network for the schema) and the
# Python provider's evaluation of every preset.
validate-flags:
	uvx check-jsonschema --schemafile https://flagd.dev/schema/v0/flags.json src/flagd/flagd.json $(PRESET_DIR)/*.json
	cmp src/flagd/flagd.json $(PRESET_DIR)/00-baseline.json
	uv run --no-project --with openfeature-provider-flagd==0.5.2 python src/flagd/test_presets.py

# ── End-to-end suite (tests/e2e, OTelFeature/poc#35) ───────────────────
# Needs only Docker. Runs as its own compose project, so it can run next to
# a demo stack. geocode and weather are built against extension git refs
# (default main), so unreleased extension code can be checked before merge:
#
#   make e2e
#   make e2e OTELFEATURE_INSTRUMENT_REF=feat/x OTELFEATURE_EXTENSION_REF=v0.4.0
#   make e2e OTELFEATURE_ENFORCEMENT=sampler PYTEST_ARGS="-k baseline -x"
#   make e2e EXT_REF=feat/x  # both refs at once, as for the stage stack
#   make e2e E2E_KEEP=1      # leave the stack up afterwards (make e2e-down)
#   make e2e E2E_SKIP_BUILD=1  # images already built (CI builds them with a layer cache)
#
# Logs and the collected spans land in tests/e2e/.artifacts/.
E2E_PROJECT := otelfeature-e2e
E2E := docker compose -p $(E2E_PROJECT) -f compose.yaml -f compose.e2e.yaml
E2E_ARTIFACTS := tests/e2e/.artifacts
OTELFEATURE_INSTRUMENT_REF ?= main
OTELFEATURE_EXTENSION_REF ?= main
OTELFEATURE_ENFORCEMENT ?= processor
PYTEST_ARGS ?= -m "not slow"
export OTELFEATURE_INSTRUMENT_REF OTELFEATURE_EXTENSION_REF OTELFEATURE_ENFORCEMENT

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
