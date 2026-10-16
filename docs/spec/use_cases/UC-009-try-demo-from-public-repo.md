# Use Case: Try the demo from the public repository

## Overview

**Use Case ID:** UC-009  
**Use Case Name:** Try the demo from the public repository  
**Primary Actor:** Adopter  
**Secondary Actors:** GitHub, demo stack  
**Goal:** After the talk, an adopter clones the public demo repository and reproduces Demos 1 to 3 with only Docker installed, so that the talk's claims can be checked and the extensions evaluated.  
**Status:** Draft  
**Requirements:** FR-020, FR-021, FR-018, NFR-008  
**Work Items:** OTelFeature/poc#31, OTelFeature/poc#14, OTelFeature/poc#15  
**Test Cases:** TC-007  
**Script Beat:** call to action ("repo and demo are on the slide")  

## Preconditions

- The owner, not an agent, has made the repository public (OTelFeature/poc#31); its history is free of secrets.
- The README has a "Try it in 5 minutes" section and links both extensions.

## Main Success Scenario

1. The adopter follows the link from the slide and clones the repository.
2. The adopter runs `make start`.
3. The stack starts with the stubbed APIs and traces appear in the dashboard.
4. The adopter applies the demo presets from the stage runbook and sees the same effects as in the talk.
5. The adopter reads which `OTEL_*` settings can be live flags and which cannot (BR-003).

## Alternative Flows

_None: the stack starts on the stubbed APIs (step 3), so being offline after building changes nothing (BR-002)._

## Postconditions

### Success Postconditions

- The adopter has a running stack and reproduced the demos.

### Failure Postconditions

- _None: the repository changes nothing outside the adopter's Docker environment._

## Business Rules

### BR-001: Docker only

No local language toolchain is needed to run the demo.

### BR-002: Runs offline after building

The stack needs no network access to the real APIs once its images are built, because it starts on the stubbed APIs.

### BR-003: Env-var tiers

The README says which `OTEL_*` env vars have a live flag, which are honoured only at startup, which are deferred or excluded, and which cannot be live flags, with the reason for each, and links the extension READMEs. It states the governing rule, "the env var is the default, the flag is the live override", and its two exceptions, the hard floors `OTEL_SDK_DISABLED=true` and `OTEL_TRACES_SAMPLER=always_off` (C-011). The OTLP endpoint and headers are excluded on security grounds. The tiers are in the [entity model](../entity_model.md#otel_-env-vars-and-live-flags) (FR-021, OTelFeature/poc#14).
