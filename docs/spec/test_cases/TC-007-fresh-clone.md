# Test Case: Fresh clone runs the demo

## Overview

- **ID:** TC-007
- **Goal:** An adopter clones the public repository on a machine with only Docker and gets a running demo with `make start`.
- **Priority:** Medium
- **Status:** Draft

## Roles

- Adopter: clones and starts.

## Preconditions

- Repository public (owner action, OTelFeature/poc#31).
- Clean machine with Docker only.

## Flow

| Step | Name | Description | Test Data | Use Case |
|---|---|---|---|---|
| 1 | Clone | Clone the repository | public URL from the slide | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |
| 2 | Start | Run the start command | `make start` | [UC-009](../use_cases/UC-009-try-demo-from-public-repo.md) |
| 3 | Verify | Traces from both services in Aspire at `http://localhost:18888` | - | - |

## Validation

1. **Secrets (OTelFeature/poc#31):** `gitleaks` is clean on the full history.
2. **Docs:** README has "Try it in 5 minutes" and links both extensions; env-var tiers documented (OTelFeature/poc#14).

## Postconditions

- `make stop` removes the stack.
