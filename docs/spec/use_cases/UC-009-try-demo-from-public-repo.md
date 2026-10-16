# Use Case: Try the demo from the public repository

## Overview

**Use Case ID:** UC-009  
**Use Case Name:** Try the demo from the public repository  
**Primary Actor:** Adopter  
**Secondary Actors:** GitHub, demo stack  
**Goal:** After the talk, an adopter clones the public demo repository and reproduces Demos 1 to 3 with only Docker installed, so that the talk's claims can be checked and the extensions evaluated.  
**Status:** Draft  
**Requirements:** FR-020, FR-021, FR-018, NFR-008, NFR-017  
**Work Items:** OTelFeature/poc#31, OTelFeature/poc#14, OTelFeature/poc#15, OTelFeature/poc#91  
**Test Cases:** TC-007  
**Script Beat:** call to action ("repo and demo are on the slide")  

## Preconditions

- The owner, not an agent, has made the repository public (OTelFeature/poc#31); its history is free of secrets.
- The README has a "Try it locally" section and links both extensions.
- The prebuilt images of `main` are published (NFR-017) and the adopter can pull them: the owner has made the packages public with the repository (OTelFeature/poc#31); until then a `docker login ghcr.io` with read access is needed.

## Main Success Scenario

1. The adopter follows the link from the slide and clones the repository.
2. The adopter pulls the prebuilt images and starts the stack with Docker Compose; nothing is built locally (BR-001).
3. The stack starts with the stubbed APIs and traces appear in the dashboard.
4. The adopter applies the demo presets from the stage runbook with the `flag` compose service and sees the same effects as in the talk.
5. The adopter reads which `OTEL_*` settings can be live flags and which cannot.

## Alternative Flows

### A1: Building from source

**Trigger:** The adopter wants to change a service, or cannot pull the prebuilt images (step 2).

**Flow:**

1. The adopter starts the stack with `docker compose up -d --build`; Docker builds the images from the cloned source with the pinned extension releases (C-006). This needs network access for the build, and no other tool.
2. Use case continues at step 3.

## Postconditions

### Success Postconditions

- The adopter has a running stack and reproduced the demos.

### Failure Postconditions

- _None: the repository changes nothing outside the adopter's Docker environment._

## Business Rules

### BR-001: Docker only

Docker with Compose v2 is the only tool needed to run the demo: no `make`, no local language toolchain and no local image build (NFR-017). The `make` targets stay as shortcuts for maintainers.

### BR-002: Runs offline after pulling

The stack needs no network access to the real APIs once its images are pulled (or built, A1), because it starts on the stubbed APIs.
