.PHONY: build start start-live prepare-offline stop

# Real API endpoints, used only by `make start-live`. Plain `make start` talks
# to the stub-apis container so the stack runs with no network at all.
LIVE_NOMINATIM_URL := https://nominatim.openstreetmap.org/search
LIVE_OPEN_METEO_GEOCODING_URL := https://geocoding-api.open-meteo.com/v1/search
LIVE_OPEN_METEO_FORECAST_URL := https://api.open-meteo.com/v1/forecast

build:
	docker compose build

# Run once while online: pulls every image and builds the services, so that
# `make start` afterwards needs no network (it never rebuilds on its own).
prepare-offline:
	docker compose pull --ignore-buildable
	docker compose build

start-live: export NOMINATIM_URL := $(LIVE_NOMINATIM_URL)
start-live: export OPEN_METEO_GEOCODING_URL := $(LIVE_OPEN_METEO_GEOCODING_URL)
start-live: export OPEN_METEO_FORECAST_URL := $(LIVE_OPEN_METEO_FORECAST_URL)
start-live: start

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

stop:
	docker compose down
