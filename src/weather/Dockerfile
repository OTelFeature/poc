# Selects where otelfeature's extension comes from; see the stages below.
ARG OTELFEATURE_EXTENSION_SOURCE=release

# Multi-arch (NFR-017): every stage but the runtime one produces
# architecture-independent files (JARs), so it runs on the build platform.
# An arm64 image built on an amd64 runner then needs no Gradle under QEMU.

# ── OTel agent download ─────────────────────────────────────────────
# Separate stage so the runtime image doesn't need wget/curl installed.
# Alpine ships wget in its BusyBox base — no package install needed.
FROM --platform=$BUILDPLATFORM alpine:3.24 AS otel-agent

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
#                       unreleased extension code (only when passed
#                       explicitly to make e2e). ADD of a git
#                       URL resolves the ref on every build, so a moved
#                       branch is rebuilt.
# (declared at the top: an ARG used in FROM must come before the first FROM)

FROM --platform=$BUILDPLATFORM alpine:3.24 AS extension-release
ARG OTELFEATURE_EXTENSION_VERSION=v0.5.0
RUN wget -q -O /otelfeature-java-extension.jar \
    https://github.com/OTelFeature/otelfeature-java-extension/releases/download/${OTELFEATURE_EXTENSION_VERSION}/otelfeature-java-extension.jar

FROM --platform=$BUILDPLATFORM gradle:9.8.2-jdk21@sha256:37110d25b7a0f866d07f7e61968347b83d2e0fd01bd6ddf74c9ae2ff04000691 AS extension-git
ARG OTELFEATURE_EXTENSION_REF=main
ADD https://github.com/OTelFeature/otelfeature-java-extension.git#${OTELFEATURE_EXTENSION_REF} /src
WORKDIR /src
# The cache mount keeps downloaded dependencies across refs (local builds).
RUN --mount=type=cache,target=/home/gradle/.gradle \
    gradle shadowJar --no-daemon -q \
    && cp build/libs/otelfeature-java-extension.jar /otelfeature-java-extension.jar

FROM extension-${OTELFEATURE_EXTENSION_SOURCE} AS otelfeature-agent

# ── Build stage ─────────────────────────────────────────────────────
FROM --platform=$BUILDPLATFORM gradle:9-jdk25@sha256:ca424744a6a45a575f333edea680696d980999c461be38b1574a4c70d5455f24 AS builder

WORKDIR /app

# Dependencies in their own layer, keyed on the build files only: a source
# change doesn't download Spring Boot and the rest again (OTelFeature/poc#70).
COPY build.gradle settings.gradle ./
RUN gradle downloadDependencies --no-daemon -q
COPY src ./src
RUN gradle build -x test --no-daemon --offline

# ── Unit tests (make unit-test, OTelFeature/poc#75) ─────────────────
# Only built with `--target test`; the default build skips this stage, so
# the image is unchanged. Online: the test dependencies aren't in the
# dependency layer above.
FROM builder AS test
RUN gradle test --no-daemon

# ── Runtime stage ───────────────────────────────────────────────────
FROM eclipse-temurin:25-jre-alpine@sha256:e1898fd6a11fc965a994d8ace186fd3585aeb636cf8f05f47a723fcfee0b0918

WORKDIR /app

COPY --from=builder /app/build/libs/weather-0.1.0.jar /app/app.jar
COPY --from=otel-agent /opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar
COPY --from=otelfeature-agent /otelfeature-java-extension.jar /app/otelfeature-java-extension.jar

ENV OTEL_JAVAAGENT_EXTENSIONS=/app/otelfeature-java-extension.jar

EXPOSE 8001

CMD ["java", \
     "-javaagent:/app/opentelemetry-javaagent.jar", \
     "-jar", "/app/app.jar"]
