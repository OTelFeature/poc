# Use Case: Run the demo on stage

## Overview

**Use Case ID:** UC-008  
**Use Case Name:** Run the demo on stage  
**Primary Actor:** Operator  
**Secondary Actors:** flagd, demo stack, Aspire dashboard, Flagsmith (A4 only)  
**Goal:** The operator runs Demos 1 to 3 from a laptop without network access, moving between states with one command per script beat and resetting between rehearsals, so that the live demo cannot be broken by venue Wi-Fi or a typo in a JSON file.  
**Status:** Draft  
**Requirements:** FR-018, FR-019, FR-010, NFR-004, NFR-012, NFR-015, NFR-017, C-006, C-007, C-008, C-009, FR-027  
**Work Items:** OTelFeature/poc#24, OTelFeature/poc#26, OTelFeature/poc#25, OTelFeature/poc#32, OTelFeature/poc#33, OTelFeature/poc#35, OTelFeature/poc#64, OTelFeature/poc#74, OTelFeature/poc#91, OTelFeature/poc#110  
**Test Cases:** TC-006, TC-008  
**Script Beat:** all demos; cold open uses OTel Demo footage (D1)  
**Open Questions:** OQ-16 (OQ-10 resolved)  

## Preconditions

- The operator has pulled all images while online: the prebuilt `geocode`, `weather` and `stub-apis` images published from `main`, which carry the pinned extension releases (C-006, NFR-017), and the third-party images, including the `flag` command's busybox (BR-008).
- Presets exist for each demo state: baseline, tracing off, quiet noise, semconv rules, weather boost, incident (BR-006).
- A fallback video exists for each demo.

## Main Success Scenario

1. The operator disconnects the laptop from the network.
2. The operator starts the stack; both services call the stubbed external APIs.
3. The operator resets to the baseline preset; traffic flows and traces appear.
4. For each script beat, the operator runs the one command that applies that beat's preset; the command reports once flagd serves it (BR-007).
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

### A3: Prebuilt images unavailable

**Trigger:** Before going offline (step 1), the prebuilt images cannot be pulled, for example because the registry refuses the pull, or the operator needs a local code change.

**Flow:**

1. The operator builds the images from source while online (`docker compose --profile staging build`), with the same pinned extension releases (C-006).
2. Use case continues at step 1.

### A4: Flags authored in Flagsmith

**Trigger:** The operator runs the demo with the flags in Flagsmith instead of the flag file (FR-027) and stays online (step 1); not the stage default (BR-012).

**Flow:**

1. The operator starts the stack in Flagsmith mode. The Flagsmith proxy loads the demo environment from Flagsmith and subscribes to its real-time updates; flagd syncs its flag set from the proxy instead of reading the flag file (BR-011). Both services still evaluate in process from flagd (C-002).
2. The operator resets to the baseline with the Flagsmith preset command.
3. For each script beat, the operator runs the Flagsmith preset command for that beat's preset. It changes the environment's flag values and segment overrides with the Flagsmith CLI and reports once flagd serves the preset (BR-010). The flag set flagd serves is the preset file's (BR-009).
4. Use case continues at step 5.

### A5: Flagsmith sends something the proxy cannot translate

**Trigger:** In Flagsmith mode the environment uses a segment operator, a flag value or an override the translation does not support (BR-009), when the operator applies a preset (step 4, in A4 step 3).

**Flow:**

1. The proxy logs the reason and keeps serving the last flag set it translated; flagd and the services see no change. If it has translated none yet (A4 step 1), its flagd endpoint answers with an error, flagd serves no flags, and the services run on their defaults (NFR-001).
2. The preset command does not see its preset served and fails after its timeout.
3. The operator fixes the environment or switches to the flag file, and applies the beat's preset again.
4. Use case continues at step 4.

### A6: Flagsmith cannot be reached

**Trigger:** In Flagsmith mode the proxy cannot fetch the environment document or loses the real-time stream, when the operator applies a preset (step 4, in A4 step 3).

**Flow:**

1. The proxy keeps serving the last flag set it translated and retries; without the stream it picks up changes only at its fallback poll, once a minute (BR-011).
2. The preset command does not see its preset served and fails after its timeout.
3. The operator switches to the flag file and applies the beat's preset with the file command.
4. Use case continues at step 4.

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

Decided by Simon, 2026-10-16 (OTelFeature/poc#26, PR OTelFeature/poc#41). Each preset keeps the rules of the preset before it, so a later beat never brings back spans an earlier beat dropped: `03-semconv-rules`, `03a-weather-boost` and `03b-incident` keep `02-quiet-noise`'s `telemetryLevel=IO`, and `03a-weather-boost` and `03b-incident` keep `03-semconv-rules`'s `recordSpan` drop rules. `01-otel-off` is the baseline with tracing off. Demo 2 has one preset, `02-quiet-noise`: `telemetryLevel` IO, a cut by span kind only, with `recordSpan` untargeted (decided by Simon, 2026-11-03, OTelFeature/poc#110, UC-002 BR-009). Demo 3 has three presets: `03-semconv-rules` (the `recordSpan` drop rules of UC-002 steps 5 and 6, and production `traceSampleRatio` 0.1, UC-004 step 6), `03a-weather-boost` (adds `weather` at 0.5, UC-004 step 7) and `03b-incident` (the fault and the control-loop rule, UC-005). The stage order is `00-baseline` → `01-otel-off` → `02-quiet-noise` → `03-semconv-rules` → `03a-weather-boost` → `03b-incident` → back to `03a-weather-boost` (incident over). The demo is a **progression**: the operator never resets on stage. `03b-incident` builds on `03a-weather-boost`, which sets `weather` to 0.5, so the error-rate rule visibly raises it from 0.5 to 1.0 when the fault is injected (OQ-10 resolved, Simon, 2026-10-16). Going back to `03a-weather-boost` removes the fault and the rule together, so `weather` is back at 0.5 at once (UC-005 A6; OQ-14 resolved, Simon, 2026-10-16). The e2e suite runs the same progression in order without resets (`test_stage_progression`, OTelFeature/poc#35). See the [entity model](../entity_model.md#flag_preset).

### BR-007: A flip counts only once flagd serves it

flagd reloads a flag file only when its mtime strictly increases, so every preset command leaves the file with a newer mtime, and an automated run checks that flagd serves the new value before it counts spans. The check reads the value over flagd's OFREP endpoint and only verifies it; the services still evaluate in process over gRPC sync (C-002, NFR-004, [flag file reload](../entity_model.md#flag-file-reload)). The stage's flag command (`docker compose run --rm flag <preset>`) does the same check: every preset names itself in its flag-set metadata, and the command reports success only once flagd's OFREP answer carries that name, or fails after its timeout (OTelFeature/poc#91).

### BR-008: The stage pulls, it does not build

The stage runs the images published from `main` (NFR-017), so the operator's laptop needs Docker only and no build can fail on the day. `POC_IMAGE_TAG` selects them: `main` by default, or the `sha-<short>` tag of the commit that was rehearsed, so the stage runs exactly the rehearsed images. The stage starts with `--pull never --no-build`, so a missing image fails before the talk instead of being built quietly. Building from source is the fallback (A3), never the default (Simon, 2026-10-16, OTelFeature/poc#91).

### BR-009: Flagsmith mode serves the preset files

In Flagsmith mode (A4) the flag set the proxy derives from the Flagsmith environment is the preset file of the preset last applied: the same flags, variants, default variants, targeting and `metadata.preset`. The preset files stay the single source of the demo states; each Flagsmith preset only says which segment overrides are on, and CI checks for every preset that the Flagsmith state the command produces translates back to that preset's file. The translation covers the comparisons the presets use and their direct counterparts, nothing more: Flagsmith segments whose rules are `ALL`, `ANY` or `NONE` with the conditions `EQUAL`, `NOT_EQUAL`, `GREATER_THAN`, `GREATER_THAN_INCLUSIVE`, `LESS_THAN` and `LESS_THAN_INCLUSIVE`, and flag values that are a variant of the flag, with no percentage split. For a flag of the presets, any other operator, value or override is rejected, and the environment as a whole with it; Flagsmith features that are no flag of the presets are not translated and do not cause a rejection. On a rejected environment the proxy logs why and keeps serving the last flag set it translated (A5), as flagd keeps its last flag set when a file does not parse. See the [entity model](../entity_model.md#flagsmith-mode) (Simon, 2026-11-03).

### BR-010: A Flagsmith flip counts only once flagd serves it

The Flagsmith preset command writes the `demoPreset` flag last, with the preset's name. The proxy puts that value into the flag set's `metadata.preset` and leaves `demoPreset` out of the flags, so the command confirms the flip over flagd's OFREP endpoint exactly as BR-007 does, and fails after its timeout. Before that it checks that the proxy's flag set equals the preset file, because the environment document the command diffed against can lag behind Flagsmith's last write; on a mismatch it writes every value again.

### BR-011: Pushed from Flagsmith, polled only locally

The proxy is Flagsmith's Edge Proxy with a flagd endpoint added. It fetches the environment document again when Flagsmith's real-time stream reports a change (Flagsmith Enterprise), and polls Flagsmith only as a fallback, once a minute. flagd polls the proxy over the local network every second. The bound is measured from the real-time event that reports the preset command's last write (`demoPreset`) to the moment flagd serves the preset over OFREP: at most 2 s (the bound of NFR-004), including the proxy's refetches while the document is older than the event. Without the stream (A6) there is no bound beyond the fallback poll. CI measures this against a stub of Flagsmith; against Flagsmith Cloud it is a rehearsal check (OQ-16).

### BR-012: Flagsmith mode is not the stage default

Flagsmith mode (A4) needs network, unlike the Goal and BR-001. Its proxy image is published like the others (BR-008, NFR-017), so the operator pulls it while online. This stands until OQ-16 decides whether Flagsmith mode goes on stage; until then the file mode is the stage run and the fallback (Simon, 2026-11-03).
