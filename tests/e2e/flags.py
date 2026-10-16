"""Flipping flags the way the stage runbook does, with a barrier.

A preset is copied over the flag file flagd watches (like `make flag`).
Two details make that reliable under test:

- flagd v0.17 (`--uri file:`) logs `"sync": "fileinfo"`: it polls the
  file's mtime and reloads only when it *increases*. The Python provider's
  file watcher does the same. Two writes in one timestamp tick keep the same
  mtime and the second one is ignored. So every write gets an mtime at
  least 1 s newer than the previous one (some filesystems keep whole
  seconds), and goes through a temp file + rename (atomic).
- Every write adds a throwaway flag `e2eRevision` with a fresh value. The
  barrier polls flagd's OFREP endpoint until it serves that value, so a test
  knows flagd has loaded *this* write before it starts counting spans.
  (The services get the same push over the sync stream, on their own
  schedule; tests that depend on a behaviour change still probe for it.)

This re-implements src/flagd/apply-preset.sh (same mtime rule) instead of
calling it, because of the extra revision flag: the file flagd reads is the
preset plus `e2eRevision`. Extensions ignore change events for flags they
don't read.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx

from spans import wait_until

REVISION_FLAG = "e2eRevision"


class Flags:
    def __init__(self, flags_file: Path, presets_dir: Path, ofrep_url: str):
        self.flags_file = flags_file
        self.presets_dir = presets_dir
        self.ofrep = httpx.Client(base_url=ofrep_url, timeout=2.0)

    def preset(self, name: str) -> dict:
        return json.loads((self.presets_dir / f"{name}.json").read_text(encoding="utf-8"))

    def apply(self, name: str, timeout: float = 5.0) -> None:
        """Apply a preset from src/flagd/presets and wait until flagd serves it."""
        self.write(self.preset(name), timeout=timeout)

    def write(self, config: dict, timeout: float = 5.0) -> None:
        revision = uuid.uuid4().hex
        config = json.loads(json.dumps(config))
        config["flags"][REVISION_FLAG] = {
            "state": "ENABLED",
            "defaultVariant": "current",
            "variants": {"current": revision},
        }
        before = self.flags_file.stat().st_mtime_ns if self.flags_file.exists() else 0
        tmp = self.flags_file.with_name(f".{self.flags_file.name}.{revision}.tmp")
        tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
        # At least one second newer: flagd compares mtimes, and some
        # filesystems keep whole seconds only.
        mtime = max(before + 1_000_000_000, os.stat(tmp).st_mtime_ns)
        os.utime(tmp, ns=(mtime, mtime))
        os.replace(tmp, self.flags_file)
        wait_until(lambda: self._revision_problem(revision), timeout=timeout)

    def evaluate(self, key: str, context: dict | None = None):
        r = self.ofrep.post(f"/ofrep/v1/evaluate/flags/{key}", json={"context": context or {}})
        r.raise_for_status()
        return r.json().get("value")

    def _revision_problem(self, revision: str) -> str | None:
        try:
            served = self.evaluate(REVISION_FLAG)
        except httpx.HTTPError as e:
            return f"OFREP not answering: {e!r}"
        return None if served == revision else f"flagd still serves revision {served!r}"
