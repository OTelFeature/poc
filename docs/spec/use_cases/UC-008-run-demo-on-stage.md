# Use Case: Run the demo on stage

## Overview

**Use Case ID:** UC-008  
**Use Case Name:** Run the demo on stage  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, demo stack, Aspire dashboard  
**Goal:** The operator runs Demos 1 to 3 from a laptop without network access, moving between states with one command per script beat and resetting between rehearsals, so that the live demo cannot be broken by venue Wi-Fi or a typo in a JSON file.  
**Status:** Draft  
**Requirements:** FR-018, FR-019, FR-010, NFR-004, NFR-012, NFR-015, C-007, C-008, C-009  
**Work Items:** OTelFeature/poc#24, OTelFeature/poc#26, OTelFeature/poc#25, OTelFeature/poc#32, OTelFeature/poc#33, OTelFeature/poc#35  
**Test Cases:** TC-006  
**Script Beat:** all demos; cold open uses OTel Demo footage (D1)  
**Open Questions:** none (OQ-10 resolved)  

## Preconditions

- The operator has pulled and built all images while online.
- Presets exist for each demo state: baseline, tracing off, quiet noise, semconv rules, weather boost, incident (BR-006).
- A fallback video exists for each demo.

## Main Success Scenario

1. The operator disconnects the laptop from the network.
2. The operator starts the stack; both services call the stubbed external APIs.
3. The operator resets to the baseline preset; traffic flows and traces appear.
4. For each script beat, the operator runs the one command that applies that beat's preset.
5. The dashboard shows the beat's flag change within 2 seconds (NFR-004). The control-loop effect of `03b-incident` (`weather` from 0.5 to 1.0) follows within one to two error-rate intervals (NFR-014); its errors show within 2 seconds.
6. After the last beat, the operator resets to baseline.

## Alternative Flows

### A1: A live step fails

**Trigger:** The expected effect does not appear within its bound (step 5).

**Flow:**

1. The operator switches to the fallback video for that demo.
2. Use case continues at step 4 with the next beat.

### A2: Running with real external APIs

**Trigger:** The operator chooses the live mode (step 2).

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

### BR-005: Every beat is tested before it reaches the stage

Each demo beat runs as an automated end-to-end test in CI, with the same presets the operator applies on stage, and the suite must be green before extension code is merged (NFR-015, OTelFeature/poc#35). Rehearsals (NFR-012) check what CI cannot: the dashboard, the runbook and the laptop.

### BR-006: Presets are cumulative, in a fixed order

Decided by Simon, 2026-10-16 (OTelFeature/poc#26, PR OTelFeature/poc#41). Each preset keeps the rules of the preset before it, so a later beat never brings back spans an earlier beat dropped: `03-semconv-rules`, `03a-weather-boost` and `03b-incident` keep `02-quiet-noise`'s drop rules. `01-otel-off` is the baseline with tracing off. Demo 3 has three presets: `03-semconv-rules` (production `traceSampleRatio` 0.1, UC-004 step 6), `03a-weather-boost` (adds `weather` at 0.5, UC-004 step 7) and `03b-incident` (the fault and the control-loop rule, UC-005). The stage order is `00-baseline` → `01-otel-off` → `02-quiet-noise` → `03-semconv-rules` → `03a-weather-boost` → `03b-incident` → back to `03a-weather-boost` (incident over). The demo is a **progression**: the operator never resets on stage. `03b-incident` builds on `03a-weather-boost`, which sets `weather` to 0.5, so the error-rate rule visibly raises it from 0.5 to 1.0 when the fault is injected (OQ-10 resolved, Simon, 2026-10-16). Going back to `03a-weather-boost` removes the fault and the rule together, so `weather` is back at 0.5 at once (UC-005 A6); OQ-14 asks whether the talk shows the loop letting go on its own instead. The e2e suite runs the same progression in order without resets (`test_stage_progression`, OTelFeature/poc#35). See the [entity model](../entity_model.md#flag_preset).

### BR-007: A flip counts only once flagd serves it

flagd reloads a flag file only when its mtime strictly increases, so every preset command leaves the file with a newer mtime, and an automated run confirms over OFREP that flagd serves the new value before it counts spans ([flag file reload](../entity_model.md#flag-file-reload), NFR-004).
