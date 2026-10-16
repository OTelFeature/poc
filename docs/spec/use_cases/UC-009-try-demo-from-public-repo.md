# Use Case: Try the demo from the public repository

## Overview

- **Use Case ID:** UC-009
- **Use Case Name:** Try the demo from the public repository
- **Primary Actor:** Adopter
- **Secondary Actors:** GitHub, demo stack
- **Goal:** After the talk, an adopter clones the public demo repository and reproduces Demos 1 to 3 with only Docker installed, so that the talk's claims can be checked and the extensions evaluated.
- **Status:** Draft
- **Requirements:** FR-020, FR-021, FR-018, NFR-008
- **Work Items:** OTelFeature/poc#31, OTelFeature/poc#14, OTelFeature/poc#15
- **Test Cases:** TC-007
- **Script Beat:** call to action ("repo and demo are on the slide")

## Preconditions

- The repository is public and its history is free of secrets.
- The README has a "Try it in 5 minutes" section and links both extensions.

## Main Success Scenario

1. The adopter follows the link from the slide and clones the repository.
2. The adopter runs `make start`.
3. The stack starts with the stubbed APIs and traces appear in the dashboard.
4. The adopter applies the demo presets from the stage runbook and sees the same effects as in the talk.
5. The adopter reads which `OTEL_*` settings can be live flags and which cannot.

## Alternative Flows

### A1: No network access to the real APIs

**Trigger:** Step 3, the adopter is offline after building.

**Flow:**

1. The stack runs on the stubbed APIs as in step 3.
2. Use case continues at step 4.

## Postconditions

### Success Postconditions

- The adopter has a running stack and reproduced the demos.

### Failure Postconditions

- _None: the repository changes nothing outside the adopter's Docker environment._

## Business Rules

### BR-001: Docker only

No local language toolchain is needed to run the demo.

### BR-002: Visibility is an owner action

Making the repository public is done by the owner, not by an agent.
