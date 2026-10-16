# Spec: OpenFeature as a Control Plane for OpenTelemetry

The specification for the talk demo: what the demo stack and the two
extensions (`otelfeature-instrument`, `otelfeature-java-extension`) must do,
and how we know they do it. Code and tests are derived from these documents;
the GitHub issues are the work items that implement them.

The source for the gap analysis and decisions D1 to D6 is `DEMO-BACKLOG.md`
(kept outside this repo). Where it and this spec disagree, this spec wins and
the backlog is out of date.

**Focus: spans and traces.** Metrics appear only as an input to span
sampling. Metrics and logs gating is out of scope (OTelFeature/poc#11, P2).
The noisy-demo workload (OTelFeature/poc#23) is P2 as well.

## Process: AI Unified Process (AIUP)

These documents follow the [AI Unified Process](https://unifiedprocess.ai/)
by Simon Martinelli, a spec-driven method adapted from the Rational Unified
Process. Sources used:

- Method and phases: <https://unifiedprocess.ai/>,
  <https://unifiedprocess.ai/methodology.html>,
  <https://unifiedprocess.ai/tutorial.html>
- Templates and naming: the `aiup-core` agent plugin, v2.5.0
  (<https://tessl.io/registry/ai-unified-process/aiup-core/2.5.0>), skills
  `requirements`, `entity-model`, `use-case-diagram`, `use-case-spec`,
  `test-case`

The core ideas, as they apply here:

- **Use cases are the gate.** Nothing gets built without a use case. Each
  issue points at one; each use case says which issues implement it.
- **The spec stays in the repo** next to the code and is changed in the same
  pull request as the code.
- **Behaviour is the source of truth.** Use cases describe what the system does,
  not how the code does it. Tests check behaviour and protect it when an agent
  changes code.
- **Phases.** Inception (vision, requirements), Elaboration (entity model, use
  case diagram), Construction (use case specs, test cases, code, tests),
  Transition (stage rehearsal, public repo).

## Documents

| Phase | File | What it is |
|---|---|---|
| Inception | [vision.md](vision.md) | Problem, stakeholders, goals, non-goals, decisions D1 to D6. Hand-written; everything else derives from it |
| Inception | [requirements.md](requirements.md) | Catalog: functional (`FR-`), non-functional (`NFR-`), constraints (`C-`) |
| Inception | [glossary.md](glossary.md) | Domain terms, one name per concept, with the synonyms to avoid |
| Elaboration | [entity_model.md](entity_model.md) | Flags, `TelemetryPolicy`, evaluation-context contract, enforcement points |
| Elaboration | [use_cases.md](use_cases.md) | Use case diagram (Mermaid) |
| Construction | [use_cases/](use_cases) | One spec per use case, `UC-XXX-name.md` |
| Construction | [test_cases/](test_cases) | End-to-end journeys with acceptance checks, `TC-XXX-name.md` |
| Construction | [ratio-parity.md](ratio-parity.md) | Why Java and Python can disagree at the same `traceSampleRatio`, and the `fractional` fix (UC-004 BR-008) |
| All | [traceability.md](traceability.md) | Script beat ↔ requirement ↔ use case ↔ test case ↔ issue |

Use cases:

| ID | Use case | Script beat |
|---|---|---|
| [UC-001](use_cases/UC-001-switch-tracing-off-and-on.md) | Switch tracing off and on at runtime | Demo 1 |
| [UC-002](use_cases/UC-002-drop-noisy-spans.md) | Drop noisy spans before they are created | Demo 2 |
| [UC-003](use_cases/UC-003-measure-savings.md) | Measure the savings of a drop rule | Demo 2 numbers, D3 |
| [UC-004](use_cases/UC-004-target-trace-sampling.md) | Target trace sampling by environment and service | Demo 3 |
| [UC-005](use_cases/UC-005-raise-sampling-on-errors.md) | Raise sampling while a service is failing | Demo 3 control loop |
| [UC-006](use_cases/UC-006-inject-upstream-failures.md) | Inject upstream failures | Demo 3 incident |
| [UC-007](use_cases/UC-007-see-flag-evaluations-in-trace.md) | See flag evaluations in the trace | Demo 3 "flag explains itself" (OQ-9) |
| [UC-008](use_cases/UC-008-run-demo-on-stage.md) | Run the demo on stage | all |
| [UC-009](use_cases/UC-009-try-demo-from-public-repo.md) | Try the demo from the public repository | CTA |

## Where this deviates from AIUP, and why

- **Location.** AIUP puts the artifacts directly under `docs/`. They are under
  `docs/spec/` here so they don't mix with other docs. File names follow the
  `aiup-core` skills (`entity_model.md`; the diagram is `use_cases.md`, see below). The AIUP
  tutorial uses `docs/architecture/entity-model.md` and
  `docs/architecture/use-case-diagram.puml` instead; the plugin's names were
  picked because the plugin is what agents will run.
- **Mermaid instead of PlantUML.** AIUP draws the use case diagram in
  PlantUML. We use Mermaid everywhere (the entity model already is), because
  GitHub renders it inline and it needs no extra tooling. Mermaid has no use
  case diagram type, so [use_cases.md](use_cases.md) uses a flowchart in use
  case notation; `include`/`extend` are labelled dotted arrows.
- **Test case location.** AIUP names test cases `TC-XXX` but does not give a
  folder. `test_cases/TC-XXX-name.md` is our choice. AIUP derives test cases
  from BPMN business-process paths; there is no business-process model here
  (the talk script plays that role), so each test case follows one demo beat.
- **Acceptance criteria live in test cases.** AIUP's use case template has no
  acceptance-criteria section. Each test case's *Validation* list holds the
  acceptance checks, each tagged with the issue whose acceptance criteria it
  mirrors.
- **Automation tags in test cases.** A Validation item that the end-to-end
  suite checks ends with `[e2e: test_name]`, or `[e2e, partly: …]` when only
  the observable part is automated and the rest stays in unit tests. Each
  automated test case has an *Automation* section naming the test and its
  phase. Both are ours, not AIUP's.
- **Extra Overview fields in use cases.** `Requirements` and `Secondary Actors`
  are AIUP fields. `Work Items`, `Test Cases`, `Script Beat` and `Open
  Questions` are ours. The spec lint keeps unknown Overview lines as they
  are, so they pass.
- **Entity model is a domain model, not a schema.** Entities use AIUP's
  attribute-table format and data types. The concrete flags, the
  evaluation-context contract and the enforcement points are added as
  *reference data* tables after the entities, since AIUP's format has no place
  for instances.
- **Technical terms in steps.** AIUP keeps implementation terms out of use case
  steps. Here the users are operators and the subject is telemetry, so span
  kinds, flag names and semconv attribute names are domain language and
  appear in steps. Class names and APIs stay in the issues.
- **No Software Architecture Document.** The one open architecture decision
  (D3, sampler vs processor) is captured in the entity model and OQ-1.

## Changing the spec before the code

Every change, whether a new feature, a change or a bug, starts as a change to
a use case.

1. **Classify it.** If the people who agreed to the current use case would
   still agree to it given what is now wanted, it's an enhancement: change the
   use case. If the use case never meant what it says, it's a bug in the spec:
   fix the wording first.
2. **Change the spec first**, in the same branch as the code: the use case,
   then `requirements.md` if a requirement moves, and `vision.md` only if a
   goal or non-goal changes. Update `entity_model.md` if a flag, context key or
   enforcement point changes.
3. **Update `traceability.md`** in the same change.
4. **Change the code and tests** so they match the spec. Changed expectations
   are updated, dropped scenarios deleted, unchanged ones left alone.
5. **Review spec and code together** in one pull request. A code PR that
   changes behaviour without a spec diff is incomplete.

When a decision is made (for example D3 after OTelFeature/poc#27), replace the
open question with the decision in every place that references it, and set
the affected requirement status.

## For agents picking up an issue

1. Find the issue in [traceability.md](traceability.md). Read the use cases
   and test cases it maps to, then the requirements they list.
2. Read the relevant reference data in [entity_model.md](entity_model.md):
   flag keys and variants, the evaluation-context contract, and which
   enforcement point you are working on.
3. Check the **Open questions** below. If your issue depends on one that is
   still open, don't invent an answer: implement the part that doesn't depend
   on it, or stop and ask.
4. Implement what the main success scenario, the alternative flows and the
   business rules say. Every alternative flow needs a test. The test case's
   Validation items tagged with your issue are your acceptance criteria, next
   to the ones in the issue itself.
5. If the code can't or shouldn't do what the spec says, change the spec in
   the same PR and say why in the PR description. Don't let them drift.
6. Set the use case `Status` in the PR (Draft → Implemented once its flows
   run on `main`, → Tested once its test case passes in the end-to-end
   suite), then set each requirement it lists to the status its use cases
   make it (see the Status rule in [requirements.md](requirements.md)). The
   spec lint reports a mismatch as `REQ_STATUS_DRIFT`.
7. Stay in your lane (see traceability.md). The extensions and `poc` are
   separate repos; a cross-repo issue is filed once per repo.
8. Run tests with `make test` (in `poc`, also `make e2e`) inside WSL. They
   run in the repo's `ci/Dockerfile` image; install nothing on the host but
   Docker (C-014). Keep scripts and Dockerfiles at LF line endings.
9. A `poc` stack is merged only when the end-to-end suite is green against it
   (C-013). See [Verification and tooling](#verification-and-tooling).

### Workflow for implementation (Simon, 2026-10-16)

- **Spec first.** A change that moves behaviour updates these documents
  before (or in the same PR as) the code.
- **Stacked PRs, one per issue.** Each lane's issues are implemented in lane
  order, each as its own PR stacked on the previous one. The stacks and
  their merge state are listed in [traceability.md](traceability.md#implementation).
- **Fresh-agent review.** Each PR is reviewed by a fresh agent that has not
  seen the implementation. Its fixes are applied to that PR before the next
  issue in the lane starts.
- **Agents never merge.** Merging and retargeting the stack is done by a
  person, in the [merge order](traceability.md#merge-order), and only with
  the end-to-end suite green.
- **Stop and ask** when a review finding or an implementation detail changes
  an issue's design (what it does, not how). Record the answer in the spec.

## Verification and tooling

Decided by Simon, 2026-10-16. Requirements: NFR-015, NFR-016, C-013, C-014.

### End-to-end suite (OTelFeature/poc#35)

The talk script's demo beats run as an automated suite in GitHub Actions.

- **Stack:** Docker Compose with a test override `compose.e2e.yaml`, started
  with `docker compose up -d --wait`. The override removes Datadog and
  Aspire, turns the load generator off and points the services at the API
  stubs.
- **Span sink:** the collector's `file` exporter (JSON). It was chosen over
  Tracetest and over querying Jaeger or Tempo because the test reads every
  exported span, so absence assertions ("no `/health` spans") are exact.
- **Traffic and flips:** pytest sends all requests itself. Flags are flipped
  with the stage presets (OTelFeature/poc#26), the same way the operator does on stage.
- **No fixed sleeps:** marker requests with an `x-e2e-step` header are step
  barriers; after a flip, the test polls until a probe shows the new
  behaviour. Every wait has a timeout, and a timeout is a failure.
- **Tests:** one per test case: TC-001, TC-002, TC-004, TC-005, TC-006, plus
  `test_hard_floors` and `test_baseline`. TC-003 (a measurement) and TC-007
  (a manual docs check) are excluded. The test cases' Validation lists mark
  what is automated.
- **Workflow:** runs on pull requests, on `main` and nightly, with a matrix
  over the Java enforcement mode (`processor`, `sampler`). On failure the span
  JSON and the service logs are uploaded as artifacts.

### The suite is the safety net before merging

The suite runs against the **pinned released versions** of both extensions,
the same as the stage (C-006, C-013). Building the extensions from a git ref
remains as an explicit workflow input / `make e2e` variable, to check an
extension change with the demo before it is released. Release order:
extension PRs merged → `v*` tag and GitHub Release → `poc` version bump →
e2e green (see [traceability.md](traceability.md#merge-order)).

**Releases** (Simon, 2026-10-16): GitHub Releases created by a `v*` tag in
each extension repo. The first releases with the talk's features are
otelfeature-instrument v0.3.0 and otelfeature-java-extension v0.4.0. The
stage never builds from git refs; unreleased code gets a pre-release
(`v…-rc.N`).

### Stage tooling: presets and flag flips (OTelFeature/poc#26)

- **Presets are cumulative** (Simon, 2026-10-16, OTelFeature/poc#26, PR
  OTelFeature/poc#41). Each preset in `src/flagd/presets/` keeps the rules of
  the one before it, so `03-semconv-rules`, `03a-weather-boost` and
  `03b-incident` keep `02-quiet-noise`'s drop rules. Demo 3 is split in two:
  `03-semconv-rules` sets production `traceSampleRatio` to 0.1 (UC-004 step 6)
  and `03a-weather-boost` adds a `weather` 0.5 override (step 7). Order:
  `00-baseline` → `01-otel-off` → `02-quiet-noise` → `03-semconv-rules` →
  `03a-weather-boost` → `03b-incident`. Details in the
  [entity model](entity_model.md#flag_preset) and UC-008 BR-006.
- **flagd reloads a flag file only when its mtime strictly increases.**
  Coarse Linux timestamps can make a fast rewrite invisible. Preset scripts
  (`make flag`), `make demo-reset`, extension tests and the e2e flag-flip
  helper bump the mtime and then confirm the new value over OFREP (port 8016)
  before counting spans; OFREP only verifies, services evaluate in process
  (C-002). See
  [flag file reload](entity_model.md#flag-file-reload).

### Toolchain images (OTelFeature/otelfeature-instrument#20, OTelFeature/otelfeature-java-extension#32)

Merged 2026-10-16: OTelFeature/otelfeature-instrument#21,
OTelFeature/otelfeature-java-extension#35 and
OTelFeature/poc#69 (OTelFeature/poc#67), see
[traceability.md](traceability.md#toolchain).

- Each repo has a `ci/Dockerfile`: base image pinned by tag and digest,
  dependencies preinstalled in a layer keyed on the lock files.
- `make test`, `make e2e` (`poc`) and `make shell` run inside it. GitHub
  Actions builds and uses the same image (buildx with GHA cache) instead of
  `setup-python`/`setup-java`. Dependabot watches the Dockerfiles.
- Python: `otelfeature-instrument` had no test CI at all until
  OTelFeature/otelfeature-instrument#20.
- Java: `ci.yml` keeps its shaded service-files check and the JAR upload. Its
  `ci/Dockerfile` is meant to double as the build stage of the `poc` e2e
  suite; that stage still builds with its own Gradle image (C-013).
- `poc`: `ci/Dockerfile` is the toolchain image (uv, the e2e suite's pytest
  dependencies and the preset-check dependencies preinstalled). `make e2e`
  runs the suite in it; `make test` runs the stack-free preset checks, the
  same as `flags.yml`.

### Spec lint (AIUP `/spec-review`, part A)

CI runs the deterministic AIUP spec lint on every pull request that touches
`docs/spec/` and on `main` (`.github/workflows/spec-lint.yml`); it must pass.
Locally, in WSL with Docker only:

```sh
make spec-lint                                   # same command as CI
make spec-lint SPEC_LINT_ARGS=--update-baseline  # accept current findings
make -s spec-lint SPEC_LINT_ARGS=--report > spec-report.html
```

- `ci/spec-lint.sh` fetches `spec_lint.py` and the sibling scripts it imports
  (`validate_use_case.py`, `bpmn_paths.py`) from
  AI-Unified-Process/marketplace at a pinned commit (aiup-core 2.28.0) and
  runs them with `--docs docs/spec` in a pinned `python:3.12-slim` image.
- It runs with `--strict`: an `ERROR` or a warning that is not in the
  baseline fails the build. It first runs the linter's `--self-test`, so a
  sibling script that fails to load fails the build instead of silently
  skipping the use case checks.
- "Must pass" is a review rule, not branch protection (this repo has none):
  maintainers don't merge a spec PR with a red spec-lint check.
- Accepted findings are in [`.spec-lint-baseline.json`](.spec-lint-baseline.json).
  Fix a finding rather than adding it to the baseline; a baseline entry that
  no longer matches is reported as `BASELINE_STALE` and should be removed with
  `--update-baseline`. Baselined: FR-003 and FR-025 (no use case by design) and the weak word "fast" (NFR-003's term, TC-005, OQ-13).
- Use case Overview lines end in two spaces (a Markdown line break, as in
  AIUP's template). Editors must not trim them; `.editorconfig` says so.
- The lint's diagram and actor checks read `use_cases.puml`; our diagram is
  Mermaid ([use_cases.md](use_cases.md)), so those checks don't run here.
- The semantic part of `/spec-review` (part B) is advisory and stays manual:
  run `/spec-review UC-XXX` before the code for a use case starts.

### Local development

Tests, builds and the stack run inside WSL (Ubuntu, WSL2) with Docker only.
Tools run from Docker images and are never installed on the host. Scripts and
Dockerfiles use LF line endings, enforced by `.gitattributes`.

## Open questions

Each is referenced by ID from the documents. Open ones are not answered in
the spec; whoever settles one updates the spec and marks it resolved here
with a pointer to where the answer now lives. Resolved questions keep their
row so references stay valid.

| ID | Question | Status | Settled by | Affects |
|---|---|---|---|---|
| OQ-1 | Java enforcement for the talk: sampler or processor (D3)? The Demo 2 script line follows it: "never recorded" (sampler) or "never batched, never serialized, never sent" (processor). Both modes are built and selected with `OTELFEATURE_ENFORCEMENT`, default `processor` (FR-008). | **Open**, pending the OTelFeature/poc#27 benchmark | Measurements in OTelFeature/poc#27 plus effort notes from OTelFeature/otelfeature-java-extension#21 | UC-001, UC-002, UC-003, FR-008 |
| OQ-2 | Shape of dotted semconv keys in the evaluation context, and the rule for a key that is both a leaf and a prefix. | **Resolved:** nested by dot segment; flat dotted keys never match in any flagd evaluator; on a leaf/prefix collision the namespace wins; extension-provided keys win over a clashing span start attribute; `otelfeature.*` is reserved. See FR-005, [entity model](entity_model.md#evaluation-context-contract), UC-002 BR-001 | Spike OTelFeature/poc#22 | FR-005, entity model, UC-002, UC-004 |
| OQ-3 | What per-span decision cost is acceptable on the targeted path? No bound is set; measure first. | **Open** | OTelFeature/poc#27, extension benchmarks | NFR-005 |
| OQ-4 | Do the pinned OpenFeature OTel hooks emit the current `feature_flag` semconv (`feature_flag.evaluation` event, `feature_flag.key`, `feature_flag.result.variant`, `feature_flag.provider.name`)? | **Answered (2026-10-16, OTelFeature/poc#30):** no. The pinned Java hook `dev.openfeature.contrib.hooks:otel` 3.3.1 emits semconv 1.28 names: event `feature_flag`, `feature_flag.key`, `feature_flag.variant`, `feature_flag.provider_name` (UC-007 BR-004, A1). The Python hook `openfeature-hooks-opentelemetry` 0.3.1 (the extension's opt-in hook) emits the current names (`feature_flag.evaluation`, `feature_flag.result.variant`, `feature_flag.provider.name`). The script wording follows OQ-9 | OTelFeature/poc#30 | UC-007, FR-015 |
| OQ-5 | With OTelFeature/poc#23 deferred (P2), nothing calls `/health`. Where does health-check traffic for Demo 2 come from (compose healthchecks, a k6 scenario folded into OTelFeature/poc#26, or a different noise source for the demo)? | **Answer in review:** a k6 `healthchecks` scenario sends a steady `GET /health` to both services, one root `SERVER` span per check (OTelFeature/poc#38, split out of OTelFeature/poc#23 by Simon). Resolved when PR OTelFeature/poc#40 merges | Speakers, before OTelFeature/poc#26 | UC-002, UC-003, TC-002 |
| OQ-6 | How is a dropped root's subtree dropped outside the Java sampler? | **Resolved (Simon, 2026-10-16):** an incoming request span (`SERVER`/`CONSUMER`) with a remote parent counts as a root. Python returns a non-recording span with a valid, non-sampled context for a dropped root and suppresses only the span itself for a non-root. Java sampler mode returns `DROP` for roots and non-propagating leaves and leaves spans that propagate mid-trace to the processor; processor mode suppresses at `onStart`. Known Java edge with a non-parent-based sampler documented, not fixed. See UC-002 BR-003, C-004, [enforcement points](entity_model.md#enforcement-points) | OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27 | UC-002 BR-003, FR-006 |
| OQ-7 | How does Python know a rule reads only resource and scope keys, so it may decide per tracer? | **Resolved (Simon, 2026-10-16):** Python reads the rule and decides once per tracer only when every key it reads is present on the tracer (resource and scope keys); `fractional` (reads `targetingKey`) and `missing_some` are handled; an OpenFeature global or transaction context, or API-level hooks, force per-span. See FR-007, UC-002 A2 and BR-007 | OTelFeature/poc#12 | UC-002 A2 |
| OQ-8 | Which flag carries the Demo 2 drop rules? | **Resolved (Simon, 2026-10-16):** the per-span boolean flag `recordSpan` (default `true`, key override `OTELFEATURE_RECORD_SPAN_FLAG_NAME`). See FR-023, UC-002 BR-006, [flags](entity_model.md#flags) | Speakers, with OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27 | UC-002 BR-006, entity model |
| OQ-9 | Demo 3 script line: "when someone asks why did we stop collecting this, the answer is in the trace" no longer holds for telemetry decisions, because the extensions record none of their own decisions on spans (FR-014). Recommended rewording: "the flag decisions show up in your traces", demonstrated with the application's own `weatherUpstreamFailure` evaluation (OTelFeature/poc#30). | **Open** (recommendation only, not decided) | Speakers | UC-007, TC-005, script |
| OQ-10 | Which preset does `03b-incident` build on? The presets are cumulative (UC-008 BR-006), but if `03b-incident` includes `03a-weather-boost`'s override, `weather` already samples at 1.0 and the control loop (UC-005) shows no change. PR OTelFeature/poc#42 currently builds it on `03-semconv-rules` (as PR OTelFeature/poc#41 had it, before the split). | **Resolved (Simon, 2026-10-16):** the demo is a progression with no resets, so `03b-incident` builds on `03a-weather-boost`. `03a` sets `weather` to **0.5** (not 1.0), so the error-rate rule in `03b` visibly raises it from 0.5 to 1.0 when the fault is injected. | Speakers, before OTelFeature/poc#42 merges | UC-005, UC-006, UC-008 BR-006, TC-005, TC-006 |
| OQ-11 | "Root span" has two meanings. For drop rules it includes an incoming `SERVER`/`CONSUMER` span with a remote parent (FR-006, UC-002 BR-003, `SPAN_DECISION.isRoot`); for the sample ratio only a span with no parent evaluates `traceSampleRatio` (TC-004 item 6, UC-004 BR-002). FR-009, the entity model (`TELEMETRY_POLICY.sampleRatio`, policy field resolution) and UC-004 steps 2 to 4 say "root spans" for the ratio. Qualify one of them (for example "trace root")? The [glossary](glossary.md) keeps them apart for now. | **Resolved (Simon, 2026-10-16):** rename the ratio sense. A **trace root** (no parent at all) is the only span that evaluates `traceSampleRatio`; **root span** keeps the drop-rule sense. Applied in FR-009, the entity model, UC-004, TC-004, ratio-parity.md and the [glossary](glossary.md) | Speakers | FR-009, entity model, UC-004, glossary |
| OQ-12 | Requirement status vs use case status. All use cases are `Draft`, while 26 requirements are Implemented, In Progress or Verified; AIUP derives a requirement's status from its use cases, so the spec lint reports `REQ_STATUS_DRIFT` (baselined). Move use cases to `Implemented` where their requirements are, or keep requirement statuses hand-set? | **Resolved (Simon, 2026-10-16):** strict AIUP. UC-001 Tested, UC-002 and UC-006 Implemented, the rest Draft; every requirement's status is derived from its use cases, downgrades included. Rule in [requirements.md](requirements.md); drift now fails the spec lint | Simon | all use cases, requirements.md, `.spec-lint-baseline.json` |
| OQ-13 | TC-005 says the e2e variant "runs fast" (spec lint `WEAK_WORD`, baselined). Replace it with a bound, for example "finishes within N s"? | **Resolved (Simon, 2026-10-16):** no bound needed; the `WEAK_WORD` finding stays in the spec-lint baseline | Simon | TC-005, `.spec-lint-baseline.json` |
| OQ-14 | How does the Demo 3 incident end, and is its margin wide enough? (a) Going back to `03a-weather-boost` removes the fault *and* the error-rate rule, so `weather` returns to 0.5 at once: the loop never visibly lets go (UC-005 A6). A preset with the rule kept and the fault off would show the release one or two intervals later (UC-005 steps 6 to 8). (b) On the stage load the error rate is about 9% (only `POST /weather` fails; health checks count), so in about one 10 s interval in seven it stays under 5% and `weather` dips back to 0.5; an incident share of 0.5, a lower `HEALTHCHECK_RATE` or a lower threshold would widen it. Raised in PR OTelFeature/poc#56 (there as OQ-11); 0.5 set in PR OTelFeature/poc#68. | **Resolved (Simon, 2026-10-16):** (a) the incident ends by going back to `03a-weather-boost`, an immediate return (entity model, FLAG_PRESET). (b) The incident share is 0.5 instead of 0.3: an error rate of about 14%, with an interval not above 5% about 1% of the time (UC-006 BR-003). | Speakers | UC-005, UC-006, UC-008 BR-006, TC-005 |
| OQ-15 | Is ±10% per metric (NFR-011, UC-003 BR-003) the right reproducibility rule? It holds for absolute per-run values, but not for small differences: the decision cost and a CPU around 1% of a core move by more than 10% between identical runs. Proposal: ±10% on the per-run values plus an absolute floor (for example ±0.2% of one core), and N repeated runs reported as mean ± sd. Raised by the review of the `make bench` harness (OTelFeature/poc#27). | **Open** | Simon | NFR-011, UC-003 BR-003, TC-003 |

## Validation

See [Spec lint](#spec-lint-aiup-spec-review-part-a): `make spec-lint` checks
these files with the AIUP tooling, and CI runs it on every spec PR.
