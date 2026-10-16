#!/bin/sh
# AIUP spec lint (deterministic part of /spec-review) over docs/spec.
# Runs inside python:3.12-slim, locally (`make spec-lint`) and in CI
# (.github/workflows/spec-lint.yml). Extra arguments go to spec_lint.py,
# e.g. `--update-baseline` or `--report`.
#
# The scripts come from AI-Unified-Process/marketplace at a pinned commit
# (aiup-core 2.28.0). spec_lint.py imports validate_use_case.py and
# bpmn_paths.py from its sibling skill folders, so the folder layout is kept.
set -eu

AIUP_SHA="${AIUP_SHA:-05af8163838df704620ebe1121cd6019dbce276c}"
BASE="https://raw.githubusercontent.com/AI-Unified-Process/marketplace/${AIUP_SHA}/aiup-core/skills"
SKILLS="$(mktemp -d)"

python3 -I - "$BASE" "$SKILLS" <<'EOF'
import os, sys, urllib.request
base, dest = sys.argv[1], sys.argv[2]
for path in ("spec-review/scripts/spec_lint.py",
             "use-case-spec/scripts/validate_use_case.py",
             "test-case/scripts/bpmn_paths.py"):
    target = os.path.join(dest, path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with urllib.request.urlopen(base + "/" + path, timeout=30) as response:
        open(target, "wb").write(response.read())
EOF

exec python3 -B "$SKILLS/spec-review/scripts/spec_lint.py" --docs docs/spec "$@"
