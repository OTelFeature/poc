# Offline stand-in for Nominatim and Open-Meteo. stub.py uses only the
# standard library, so the image is the stock Python image plus the script.
# Published as ghcr.io/otelfeature/poc-stub-apis (NFR-017).
FROM python:3.15-slim-bookworm

COPY stub.py /app/stub.py

ENV STUB_PORT=8080
EXPOSE 8080

CMD ["python", "-u", "/app/stub.py"]
