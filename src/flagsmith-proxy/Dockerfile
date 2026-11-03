# Flagsmith proxy (UC-008 A4): Flagsmith's Edge Proxy with a flagd endpoint
# and real-time updates, plus the Flagsmith CLI for the preset command
# (`flagsmith-flag`). Build context: src/ (it needs src/flagd/presets).
#
# Base images pinned by tag and digest.
FROM ghcr.io/flagsmith/flagsmith-cli:v2.0.0@sha256:405f38b7517c56811055bc45fe3e8d6fd36ba25963e76fbcbe1dbdc955120a32 AS cli

FROM flagsmith/edge-proxy:2.23.0@sha256:ff7700c202fbc7c5d7224a2640cb9ff7a94a34420942a3f8642e8fb902baf195

COPY --from=cli /usr/local/bin/flagsmith /usr/local/bin/flagsmith
COPY flagd/presets /app/flagd/presets
COPY flagsmith-proxy/demo.json /app/flagsmith-proxy/demo.json
COPY flagsmith-proxy/otelfeature_flagsmith /app/flagsmith-proxy/otelfeature_flagsmith

ENV PYTHONPATH=/app/flagsmith-proxy \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
CMD ["uvicorn", "otelfeature_flagsmith.app:app", "--host", "0.0.0.0", "--port", "8000"]
