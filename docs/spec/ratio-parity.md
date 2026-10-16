# traceSampleRatio: Java and Python parity

At the same `traceSampleRatio`, the Java and Python extensions can decide
differently for the same trace id, because each uses its own OTel SDK's
trace-id formula. Decision (2026-10-16): **accept and document**. It is
harmless with parent-based propagation. For cross-language consistency, bucket
with a flagd `fractional` rule on `targetingKey` (the trace id). See
[UC-004 BR-008](use_cases/UC-004-target-trace-sampling.md#br-008-cross-language-ratio-parity-is-not-guaranteed-accepted-simon-2026-10-16)
and FR-009.

## 1. The formulas differ

The same trace id goes into each SDK's formula, and at 10% the answers can
differ.

```mermaid
flowchart LR
    T["trace id<br/>4bf92f3577b34da6fa3ce929d0e0e473"]
    T --> J["Java SDK formula<br/>lower 64 bits as signed long<br/>abs(x) &lt; 0.1 · Long.MAX_VALUE"]
    T --> P["Python SDK formula<br/>lower 64 bits unsigned<br/>x &lt; 0.1 · 2^64"]
    J --> JY["abs(x) ≈ 0.045 · Long.MAX_VALUE<br/>✅ sample"]
    P --> PN["x ≈ 0.977 · 2^64<br/>❌ drop"]
```

The lower 64 bits here are `fa3ce929d0e0e473`. The top bit is set, so Java
reads a small negative number (its absolute value is under the bound), while
Python reads a large unsigned one.

## 2. Why it usually doesn't matter

Only the service where the trace starts decides. Every service after it
follows the `sampled` flag in `traceparent`.

```mermaid
sequenceDiagram
    participant K as k6
    participant G as geocode (Python)
    participant W as weather (Java)
    K->>G: POST /geocode (no traceparent)
    Note over G: trace root → Python formula decides<br/>at traceSampleRatio=0.1 → sampled
    G->>W: HTTP call, traceparent …-01 (sampled)
    Note over W: has a parent → follows it<br/>Java formula never runs
    W-->>G: response
    Note over G,W: the whole trace is recorded, or the whole trace is dropped
```

## 3. When it does matter

It only goes wrong if two services each decide for the same trace id. For
example, a proxy in between keeps the trace id but drops the `sampled` flag.

```mermaid
sequenceDiagram
    participant G as geocode (Python)
    participant X as proxy (keeps trace id, drops sampled flag)
    participant W as weather (Java)
    Note over G: root → Python formula → sampled ✅
    G->>X: traceparent …-01
    X->>W: same trace id, no sampled decision
    Note over W: decides again → Java formula → drop ❌
    Note over G,W: half-recorded trace: geocode's spans exist, weather's are missing
```

## The fix for case 3

Bucket with a flagd `fractional` rule on the trace id. flagd computes the same
bucket in every language, so both services agree.

```json
"traceSampleRatio": {
  "state": "ENABLED",
  "defaultVariant": "tenth",
  "variants": { "all": 1.0, "tenth": 0.1, "none": 0.0 },
  "targeting": {
    "fractional": [
      { "var": "targetingKey" },
      ["all", 10],
      ["none", 90]
    ]
  }
}
```

Here `fractional` keeps 10% of traces (`all`) and drops 90% (`none`). The
bucket comes from the trace id, so both languages land in the same one.
