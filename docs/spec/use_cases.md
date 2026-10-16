# Use case diagram

Mermaid has no use case diagram type, so this is a flowchart in use case
notation: actors on the outside, use cases as rounded nodes inside the system
boundary, solid arrows for participation, dotted arrows for `include` and
`extend`.

```mermaid
flowchart LR
    operator["👤 Operator"]
    adopter["👤 Adopter"]
    flagd["⚙️ flagd"]

    subgraph demo["OTelFeature demo"]
        UC001(["UC-001<br/>Switch tracing off and on at runtime"])
        UC002(["UC-002<br/>Drop noisy spans before they are created"])
        UC003(["UC-003<br/>Measure the savings of a drop rule"])
        UC004(["UC-004<br/>Target trace sampling by environment and service"])
        UC005(["UC-005<br/>Raise sampling while a service is failing"])
        UC006(["UC-006<br/>Inject upstream failures"])
        UC007(["UC-007<br/>See flag evaluations in the trace"])
        UC008(["UC-008<br/>Run the demo on stage"])
        UC009(["UC-009<br/>Try the demo from the public repository"])
    end

    operator --> UC001
    operator --> UC002
    operator --> UC003
    operator --> UC004
    operator --> UC005
    operator --> UC006
    operator --> UC007
    operator --> UC008
    adopter --> UC009

    UC001 --> flagd
    UC002 --> flagd
    UC004 --> flagd
    UC005 --> flagd
    UC006 --> flagd

    UC005 -. include .-> UC006
    UC005 -. extend .-> UC004
    UC003 -. include .-> UC002
    UC008 -. include .-> UC001
    UC008 -. include .-> UC002
    UC008 -. include .-> UC004
    UC008 -. include .-> UC005
```

On stage, Simon and Juliano are the Operator and run the use cases through
flag presets (UC-008). There is no separate Speaker actor (Simon, 2026-10-16).
