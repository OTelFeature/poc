# Test Case: Fresh clone runs the demo

## Overview

- **ID:** TC-007
- **Goal:** An adopter clones the public repository on a machine with only Docker and gets a running demo from the prebuilt images, without `make` and without building an image.
- **Priority:** Medium
- **Status:** Draft

## Roles

- Adopter: clones and starts.

## Preconditions

- Repository and its GHCR packages public (owner action, OTelFeature/poc#31, done 2026-11-04); no `docker login`.
- Clean machine with Docker and Compose v2 only: no `make`, no Python, no Java, and no `ghcr.io/otelfeature/poc-*` image present.
- `main` has published its images (NFR-017, `.github/workflows/images.yml`).

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Clone | Clone the repository | public URL from the slide | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |
| 2 | Pull | Pull every image of the stack | `docker compose pull` | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |
| 3 | Start | Start the stack | `docker compose up -d` | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |
| 4 | Verify | Traces from both services in Aspire at `http://localhost:18888` | - | - |
| 5 | Flip | Apply the stage presets in order, each with the flag service | `docker compose run --rm flag 01-otel-off`, then `02-quiet-noise`, `03-semconv-rules`, `03a-weather-boost`, `03b-incident` | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |
| 6 | Reset | Back to baseline | `docker compose run --rm flag 00-baseline` | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |

## Validation

1. **Secrets (OTelFeature/poc#31):** `gitleaks` is clean on the full history.
2. **Docs:** README has "Try it locally" and links both extensions; env-var tiers documented (OTelFeature/poc#14): the README section matches the [entity model](../entity_model.md#otel_-env-vars-and-live-flags) table, links both extension READMEs, and states the governing rule with its two hard floors and the security reason for excluding the OTLP endpoint.
3. **Nothing is built (NFR-017, OTelFeature/poc#91):** steps 2 and 3 print no build step, and afterwards `docker image ls` lists `ghcr.io/otelfeature/poc-geocode`, `poc-weather` and `poc-stub-apis` with tag `main` and no locally built image of the stack.
4. **Multi-arch:** `docker buildx imagetools inspect ghcr.io/otelfeature/poc-<service>:main` lists `linux/amd64` and `linux/arm64` for all three images.
5. **Labels:** `org.opencontainers.image.revision` of each image is a commit on `main`, and the pinned-version labels equal C-006's pins (`io.github.otelfeature.instrument.version` on `geocode`, `io.github.otelfeature.java-extension.version` on `weather`).
6. **Flips confirmed:** every step 5 and 6 command exits 0 after reporting that flagd serves the preset, each within its timeout (`FLAG_CONFIRM_TIMEOUT`, 10 s), and Aspire shows each beat's effect as in `STAGE.md`.

## Postconditions

- `docker compose --profile staging down` removes the stack.

## Automation

Not part of the end-to-end suite (OTelFeature/poc#35): it is a manual check of the public repository and its docs. Partly covered in CI: every pull request that touches an image builds all three images for both platforms (`images.yml`), and `make test` checks that every preset names itself in its metadata (`src/flagd/test_presets.py`), which the flag service's confirmation relies on.
