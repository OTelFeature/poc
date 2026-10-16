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
# `make flag PRESET=02-quiet-noise` copies a preset over src/flagd/flagd.json.
# flagd watches that file and pushes the change to both services, so the
# flip shows up on the next span. cp rewrites the file in place, which the
# bind mount's file watcher sees. flagd.json is tracked and equal to
# 00-baseline; `make demo-reset` puts it back.
flag:
	@test -n "$(PRESET)" || { echo "usage: make flag PRESET=<name>, one of: $(PRESETS)"; exit 1; }
	@test -f "$(PRESET_DIR)/$(PRESET).json" || { echo "unknown preset '$(PRESET)', one of: $(PRESETS)"; exit 1; }
	cp "$(PRESET_DIR)/$(PRESET).json" src/flagd/flagd.json
	@echo "flagd.json is now $(PRESET)"

flags:
	@printf '%s
' $(PRESETS)

# Back to baseline flags, and restart k6 so traffic starts fresh (its run
# also ends after DURATION). The staging k6 is restarted only if it exists.
demo-reset:
	@$(MAKE) --no-print-directory flag PRESET=00-baseline
	docker compose restart load-generator
	@if [ -n "$$(docker compose --profile staging ps -a -q load-generator-staging)" ]; then 		docker compose --profile staging restart load-generator-staging; 	fi

# Same checks as CI: flagd schema (needs network for the schema) and the
# Python provider's evaluation of every preset.
validate-flags:
	uvx check-jsonschema --schemafile https://flagd.dev/schema/v0/flags.json src/flagd/flagd.json $(PRESET_DIR)/*.json
	cmp src/flagd/flagd.json $(PRESET_DIR)/00-baseline.json
	uv run --no-project --with openfeature-provider-flagd==0.5.2 python src/flagd/test_presets.py
