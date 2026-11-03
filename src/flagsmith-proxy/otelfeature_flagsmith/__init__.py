"""Flagsmith mode: the demo flags authored in Flagsmith (FR-027, UC-008 A4)."""

from pathlib import Path

# Same layout in the repo and in the image (/app/flagsmith-proxy, /app/flagd).
HERE = Path(__file__).resolve().parent.parent
DEMO = HERE / "demo.json"
PRESETS = HERE.parent / "flagd" / "presets"
CATALOG = PRESETS / "00-baseline.json"
STAGE_ORDER = ["00-baseline", "01-otel-off", "02-quiet-noise", "03-semconv-rules",
               "03a-weather-boost", "03b-incident"]
