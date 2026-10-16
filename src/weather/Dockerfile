# Selects where otelfeature's extension comes from; see the stages below.
ARG OTELFEATURE_EXTENSION_SOURCE=release

# ── OTel agent download ─────────────────────────────────────────────
# Separate stage so the runtime image doesn't need wget/curl installed.
# Alpine ships wget in its BusyBox base — no package install needed.
FROM alpine:3.24 AS otel-agent

# Pinned for reproducibility — update as new versions are released.
# See https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases
ARG OTEL_AGENT_VERSION=v2.31.1
RUN wget -q -O /opentelemetry-javaagent.jar \
    https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/${OTEL_AGENT_VERSION}/opentelemetry-javaagent.jar

# ── otelfeature-java-extension ──────────────────────────────────────
# Flagd-controlled span decisions.
# See https://github.com/OTelFeature/otelfeature-java-extension
# OTELFEATURE_EXTENSION_SOURCE picks the stage below:
#   release (default) - the released JAR OTELFEATURE_EXTENSION_VERSION
#   git               - built from OTELFEATURE_EXTENSION_REF (branch, tag or
#                       commit) with Gradle's shadowJar, for testing
#                       unreleased extension code (make e2e). ADD of a git
#                       URL resolves the ref on every build, so a moved
#                       branch is rebuilt.
# (declared at the top: an ARG used in FROM must come before the first FROM)

FROM alpine:3.24 AS extension-release
ARG OTELFEATURE_EXTENSION_VERSION=v0.3.1
RUN wget -q -O /otelfeature-java-extension.jar \
    https://github.com/OTelFeature/otelfeature-java-extension/releases/download/${OTELFEATURE_EXTENSION_VERSION}/otelfeature-java-extension.jar

FROM gradle:9.7.1-jdk21 AS extension-git
ARG OTELFEATURE_EXTENSION_REF=main
ADD https://github.com/OTelFeature/otelfeature-java-extension.git#${OTELFEATURE_EXTENSION_REF} /src
WORKDIR /src
RUN gradle shadowJar -x test --no-daemon -q \
    && cp build/libs/otelfeature-java-extension.jar /otelfeature-java-extension.jar

FROM extension-${OTELFEATURE_EXTENSION_SOURCE} AS otelfeature-agent

# ── Build stage ─────────────────────────────────────────────────────
FROM gradle:9-jdk25@sha256:d868117760a7c92214705f47ed173116a5d13e58d68702f974ff30acd062737e AS builder

WORKDIR /app

# Copy build files and source, then build in one layer
COPY build.gradle settings.gradle ./
COPY src ./src
RUN gradle build -x test --no-daemon

# ── Runtime stage ───────────────────────────────────────────────────
FROM eclipse-temurin:25-jre-alpine@sha256:3c0a9084927a221ccd1d007fcaf614465672c0af37aaa834c5184483afe56d61

WORKDIR /app

COPY --from=builder /app/build/libs/weather-0.1.0.jar /app/app.jar
COPY --from=otel-agent /opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar
COPY --from=otelfeature-agent /otelfeature-java-extension.jar /app/otelfeature-java-extension.jar

ENV OTEL_JAVAAGENT_EXTENSIONS=/app/otelfeature-java-extension.jar

EXPOSE 8001

CMD ["java", \
     "-javaagent:/app/opentelemetry-javaagent.jar", \
     "-jar", "/app/app.jar"]
