# Use Case: Run the demo on stage

## Overview

- **Use Case ID:** UC-008
- **Use Case Name:** Run the demo on stage
- **Primary Actor:** Speaker
- **Secondary Actors:** flagd, demo stack, Aspire dashboard
- **Goal:** The speaker runs Demos 1 to 3 from a laptop without network access, moving between states with one command per script beat and resetting between rehearsals, so that the live demo cannot be broken by venue Wi-Fi or a typo in a JSON file.
- **Status:** Draft
- **Requirements:** FR-018, FR-019, FR-010, NFR-004, NFR-012, C-007, C-008, C-009
- **Work Items:** OTelFeature/poc#24, OTelFeature/poc#26, OTelFeature/poc#25, OTelFeature/poc#32, OTelFeature/poc#33
- **Test Cases:** TC-006
- **Script Beat:** all demos; cold open uses OTel Demo footage (D1)

## Preconditions

- The speaker has pulled and built all images while online.
- Presets exist for each demo state: baseline, tracing off, quiet noise, semconv rules, incident.
- A fallback video exists for each demo.

## Main Success Scenario

1. The speaker disconnects the laptop from the network.
2. The speaker starts the stack; both services call the stubbed external APIs.
3. The speaker resets to the baseline preset; traffic flows and traces appear.
4. For each script beat, the speaker runs the one command that applies that beat's preset.
5. The dashboard shows the effect within 2 seconds.
6. After the last beat, the speaker resets to baseline.

## Alternative Flows

### A1: A live step fails

**Trigger:** Step 5, the expected effect does not appear.

**Flow:**

1. The speaker switches to the fallback video for that demo.
2. Use case continues at step 4 with the next beat.

### A2: Running with real external APIs

**Trigger:** Step 2, the speaker chooses the live mode.

**Flow:**

1. Both services call Nominatim and Open-Meteo; request rates stay within their usage policies.
2. Use case continues at step 3.

## Postconditions

### Success Postconditions

- All demo beats ran from presets and the stack is back at baseline.

### Failure Postconditions

- The fallback video was shown for any beat that failed.

## Business Rules

### BR-001: Offline by default

The stack's default start uses the stubbed APIs; outgoing client spans still look realistic (server address of the stub).

### BR-002: One command per beat

Every script beat maps to one command in the stage runbook.

### BR-003: Presets are valid

Every preset validates against the flagd schema.

### BR-004: Opening hook is footage

The wall of spans in the cold open is recorded OTel Demo footage; the POC does not need to be noisy (OTelFeature/poc#23 is deferred).
