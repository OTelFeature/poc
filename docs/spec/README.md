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
| Elaboration | [entity_model.md](entity_model.md) | Flags, `TelemetryPolicy`, evaluation-context contract, enforcement points |
| Elaboration | [use_cases.md](use_cases.md) | Use case diagram (Mermaid) |
| Construction | [use_cases/](use_cases) | One spec per use case, `UC-XXX-name.md` |
| Construction | [test_cases/](test_cases) | End-to-end journeys with acceptance checks, `TC-XXX-name.md` |
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
  `aiup-core` 2.5.0 skills (`entity_model.md`; the diagram is `use_cases.md`, see below). The AIUP
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
- **Extra Overview fields in use cases.** `Requirements` and `Secondary Actors`
  are AIUP fields. `Work Items`, `Test Cases`, `Script Beat` and `Open
  Questions` are ours. AIUP's `validate_use_case.py` may warn about them; it
  has not been run against these files.
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
6. Set the requirement `Status` (Open → In Progress → Implemented) and the use
   case `Status` (Draft → Implemented) in the PR. A test case's checks passing
   moves the requirement to Verified.
7. Stay in your lane (see traceability.md). The extensions and `poc` are
   separate repos; a cross-repo issue is filed once per repo.

### Workflow for implementation (Simon, 2026-10-16)

- **Spec first.** A change that moves behaviour updates these documents
  before (or in the same PR as) the code.
- **Stacked PRs, one per issue.** Each lane's issues are implemented in lane
  order, each as its own PR stacked on the previous one. The open stacks are
  listed in [traceability.md](traceability.md#implementation).
- **Fresh-agent review.** Each PR is reviewed by a fresh agent that has not
  seen the implementation. Its fixes are applied to that PR before the next
  issue in the lane starts.
- **Agents never merge.** Merging and retargeting the stack is done by a
  person.
- **Stop and ask** when a review finding or an implementation detail changes
  an issue's design (what it does, not how). Record the answer in the spec.

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
| OQ-4 | Do the pinned OpenFeature OTel hooks emit the current `feature_flag` semconv (`feature_flag.evaluation` event, `feature_flag.key`, `feature_flag.result.variant`, `feature_flag.provider.name`)? | **Open** | OTelFeature/poc#30 | UC-007, FR-015 |
| OQ-5 | With OTelFeature/poc#23 deferred (P2), nothing calls `/health`. Where does health-check traffic for Demo 2 come from (compose healthchecks, a k6 scenario folded into OTelFeature/poc#26, or a different noise source for the demo)? | **Open** | Speakers, before OTelFeature/poc#26 | UC-002, UC-003, TC-002 |
| OQ-6 | How is a dropped root's subtree dropped outside the Java sampler? | **Resolved (Simon, 2026-10-16):** an incoming request span (`SERVER`/`CONSUMER`) with a remote parent counts as a root. Python returns a non-recording span with a valid, non-sampled context for a dropped root and suppresses only the span itself for a non-root. Java sampler mode returns `DROP` for roots and non-propagating leaves and leaves spans that propagate mid-trace to the processor; processor mode suppresses at `onStart`. Known Java edge with a non-parent-based sampler documented, not fixed. See UC-002 BR-003, C-004, [enforcement points](entity_model.md#enforcement-points) | OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27 | UC-002 BR-003, FR-006 |
| OQ-7 | How does Python know a rule reads only resource and scope keys, so it may decide per tracer? | **Resolved (Simon, 2026-10-16):** Python reads the rule and decides once per tracer only when every key it reads is present on the tracer (resource and scope keys); `fractional` (reads `targetingKey`) and `missing_some` are handled; an OpenFeature global or transaction context, or API-level hooks, force per-span. See FR-007, UC-002 A2 and BR-007 | OTelFeature/poc#12 | UC-002 A2 |
| OQ-8 | Which flag carries the Demo 2 drop rules? | **Resolved (Simon, 2026-10-16):** the per-span boolean flag `recordSpan` (default `true`, key override `OTELFEATURE_RECORD_SPAN_FLAG_NAME`). See FR-023, UC-002 BR-006, [flags](entity_model.md#flags) | Speakers, with OTelFeature/otelfeature-instrument#14, OTelFeature/otelfeature-java-extension#27 | UC-002 BR-006, entity model |
| OQ-9 | Demo 3 script line: "when someone asks why did we stop collecting this, the answer is in the trace" no longer holds for telemetry decisions, because the extensions record none of their own decisions on spans (FR-014). Recommended rewording: "the flag decisions show up in your traces", demonstrated with the application's own `weatherUpstreamFailure` evaluation (OTelFeature/poc#30). | **Open** (recommendation only, not decided) | Speakers | UC-007, TC-005, script |

## Validation

No AIUP tooling was run against these files. To check use case structure with
the AIUP plugin installed:

```sh
python3 scripts/validate_use_case.py docs/spec/use_cases/UC-*.md
```
