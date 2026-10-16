# Traceability Matrix

Links every script beat to its requirements, use cases, test cases and the
GitHub issues that implement them. When any of these changes, update this
file in the same change.

Issue refs: `OTelFeature/poc#N` (poc), `OTelFeature/otelfeature-instrument#N`
(Python), `OTelFeature/otelfeature-java-extension#N` (Java).

## Script beat → spec → issue

| Script beat | Requirements | Use case | Test case | Issues |
|---|---|---|---|---|
| Cold open: wall of spans (OTel Demo) | C-007 | UC-008 | TC-006 | OTelFeature/poc#33 |
| "Let me show you on something smaller" (transition to POC) | FR-018, FR-019 | UC-008 | TC-006 | OTelFeature/poc#24, OTelFeature/poc#26 |
| Demo 1: one flag turns OTel off, zero span ingest | FR-001, FR-002, FR-004, NFR-001, NFR-003, NFR-004 | UC-001 | TC-001 | OTelFeature/poc#8, OTelFeature/poc#9, OTelFeature/otelfeature-java-extension#21 |
| Demo 2: the SDK asks OpenFeature before the span exists | FR-006, FR-008, C-004 | UC-002 | TC-002 | OTelFeature/otelfeature-java-extension#21 |
| Demo 2: context = service name, instrumentation scope, the path | FR-005, C-003 | UC-002 | TC-002 | OTelFeature/poc#22, OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20 |
| Demo 2: health checks off in one service, DB spans off in another | FR-006, FR-007, NFR-007 | UC-002 | TC-002 | OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20, OTelFeature/otelfeature-java-extension#21, OTelFeature/poc#12 |
| Demo 2: CPU [X%], memory [Y MB], export bytes [Z%] | FR-016, NFR-005, NFR-006, NFR-011 | UC-003 | TC-003 | OTelFeature/poc#27 |
| Demo 3: rules on `service.name`, `deployment.environment.name` | FR-005, FR-010 | UC-004 | TC-004 | OTelFeature/poc#25, OTelFeature/otelfeature-instrument#7, OTelFeature/otelfeature-java-extension#20 |
| Demo 3: sample rate as a number flag | FR-009, NFR-007 | UC-004 | TC-004 | OTelFeature/poc#10 |
| Demo 3: errors rise, a rule turns sampling up for that service | FR-011, FR-012, FR-013, NFR-013, C-005 | UC-005, UC-006 | TC-005 | OTelFeature/poc#28, OTelFeature/otelfeature-instrument#8, OTelFeature/otelfeature-java-extension#22, OTelFeature/poc#29 |
| Demo 3: the flag explains itself | FR-014, FR-015 | UC-007 | TC-005 | OTelFeature/otelfeature-instrument#9, OTelFeature/otelfeature-java-extension#23, OTelFeature/poc#30 |
| "Why not the collector?" (could read the same flags) | C-010 | - | - | none (D4, script only) |
| CTA: repo and demo on the slide | FR-020, FR-021 | UC-009 | TC-007 | OTelFeature/poc#31, OTelFeature/poc#14 |
| Stage risk: live demo fails | C-008 | UC-008 | TC-006 | OTelFeature/poc#32 |
| Q&A: what else can become a flag | FR-021 | UC-009 | TC-007 | OTelFeature/poc#14, OTelFeature/poc#15 |

## Issue → spec

Priority as in `DEMO-BACKLOG.md`, updated with the 2026-10-16 change that
moved OTelFeature/poc#23 to P2.

| Issue | Title (short) | Pri | Requirements | Use case | Test case |
|---|---|---|---|---|---|
| OTelFeature/poc#8 | `OFF` variant + `otelEnabled` | P0 | FR-001, FR-002, NFR-001 | UC-001 | TC-001 |
| OTelFeature/poc#9 | `TelemetryPolicy` | P0 | FR-004, NFR-001 | UC-001, UC-002, UC-004 | TC-001 |
| OTelFeature/poc#10 | `traceSampleRatio` | P0 | FR-009, NFR-007 | UC-004, UC-005 | TC-004 |
| OTelFeature/poc#11 | `signalsEnabled` | P2, out of scope | FR-022 | - | - |
| OTelFeature/poc#12 | Per-tracer scope decision (Python) | P1 | FR-007 | UC-002 (A2) | TC-002 |
| OTelFeature/poc#14 | Env-var tier docs | P2 | FR-021 | UC-009 | TC-007 |
| OTelFeature/poc#15 | Roadmap | P2 | - | - | - |
| OTelFeature/poc#22 | Spike: dotted semconv keys | P0 | FR-005 | UC-002, UC-004 | TC-002 |
| OTelFeature/poc#23 | Noisy demo | P2, deferred | FR-017 | none | none |
| OTelFeature/poc#24 | Offline stage mode | P0 | FR-018, C-009 | UC-008, UC-009 | TC-006 |
| OTelFeature/poc#25 | Resource attrs, prod/staging | P0 | FR-010 | UC-004 | TC-004 |
| OTelFeature/poc#26 | Stage controls | P0 | FR-019 | UC-008 | TC-006 |
| OTelFeature/poc#27 | Measurement harness | P1 | FR-016, NFR-005, NFR-011 | UC-003 | TC-003 |
| OTelFeature/poc#28 | Fault-injection flag | P1 | FR-012 | UC-006 | TC-005 |
| OTelFeature/poc#29 | Control-loop preset | P1 | FR-013, NFR-012 | UC-005 | TC-005 |
| OTelFeature/poc#30 | OpenFeature OTel hooks | P1 | FR-015 | UC-007 | TC-005 |
| OTelFeature/poc#31 | Public repo | P1 | FR-020 | UC-009 | TC-007 |
| OTelFeature/poc#32 | Fallback video | P2 | C-008 | UC-008 | TC-006 |
| OTelFeature/poc#33 | OTel Demo footage | P1 | C-007 | UC-008 | TC-006 |
| OTelFeature/otelfeature-instrument#7 | Eval context from semconv (Python) | P0 | FR-005, NFR-003 | UC-002, UC-004 | TC-002, TC-004 |
| OTelFeature/otelfeature-instrument#8 | Error rate into context (Python) | P1 | FR-011, NFR-013, C-005 | UC-005 | TC-005 |
| OTelFeature/otelfeature-instrument#9 | Decision attributes (Python) | P1 | FR-014 | UC-007 | TC-005 |
| OTelFeature/otelfeature-java-extension#20 | Eval context from semconv (Java) | P0 | FR-005, NFR-003 | UC-002, UC-004 | TC-002, TC-004 |
| OTelFeature/otelfeature-java-extension#21 | `FlagAwareSampler`, switchable | P0 | FR-006, FR-008, C-004 | UC-001, UC-002, UC-003 | TC-001, TC-002, TC-003 |
| OTelFeature/otelfeature-java-extension#22 | Error rate into context (Java) | P1 | FR-011, NFR-013 | UC-005 | TC-005 |
| OTelFeature/otelfeature-java-extension#23 | Decision attributes (Java) | P1 | FR-014 | UC-007 | TC-005 |

## Execution lanes

One agent per lane can run concurrently; within a lane, go in order.

- **Python** (`otelfeature-instrument`): poc#8 → poc#9 → instrument#7 → poc#10 (py) → instrument#8 → instrument#9 → poc#12
- **Java** (`otelfeature-java-extension`): poc#8 → poc#9 → java#21 → java#20 → poc#10 (java) → java#22 → java#23
- **POC** (`poc`): poc#22 → poc#24 → poc#25 → poc#26 → poc#28 → poc#30 → poc#27 → poc#29 → poc#31
- **People, not agents:** poc#33, poc#32

Sync points: poc#22 finishes before instrument#7 / java#20 start. poc#27
decides D3 once java#21 is released. poc#27's final numbers and poc#29 need
released versions of both extensions (C-006).

## Requirements without a use case

| Requirement | Why |
|---|---|
| FR-003 | Existing behaviour (`telemetryLevel=IO`), kept as is; covered by the extensions' existing tests |
| FR-017 | Deferred with OTelFeature/poc#23 |
| FR-022 | Deferred with OTelFeature/poc#11 |
| NFR-002, NFR-009, NFR-010 | Already met by the current code; regression-tested in the extension repos |
