"""A model of one Flagsmith environment, driven by Flagsmith CLI calls.

It applies the subset of `flagsmith` commands the preset command uses to an
in-memory environment and renders the environment document Flagsmith would
serve for it. The CI checks use it to prove that each preset's CLI calls
translate back to that preset's file (TC-008 item 1), and the stub of
Flagsmith Cloud serves its documents (TC-008 items 3 to 5).

It follows the CLI's documented behaviour (flagsmith-cli v2): a value's type
is inferred like `--value` does, a new segment override starts from the
environment default and joins at the end, `flag reorder` assigns 0..n-1.
What real Flagsmith does beyond that is checked only in rehearsal (OQ-16).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class CLIError(RuntimeError):
    """What the CLI would report as an error (non-zero exit)."""


class Environment:
    def __init__(self, client_key: str = "demo-client-key"):
        self.client_key = client_key
        self.features: dict[str, dict[str, Any]] = {}
        self.segments: dict[str, dict[str, Any]] = {}
        # (feature, segment) -> {"enabled", "value", "priority"}
        self.overrides: dict[tuple[str, str], dict[str, Any]] = {}
        self.updated_at = datetime.now(timezone.utc)
        self._ids = 0

    def run(self, argv: list[str]) -> None:
        """Apply one CLI call, given without the leading `flagsmith`."""
        args, opts = _parse(argv)
        command = args[:2]
        if command == ["feature", "create"]:
            self._feature_create(args[2], opts)
        elif command in (["segment", "create"], ["segment", "update"]):
            self._segment_write(args[2], opts, create=command[1] == "create")
        elif command == ["flag", "update"]:
            self._flag_update(args[2], opts)
        elif command == ["flag", "delete"]:
            self._flag_delete(args[2], opts)
        elif command == ["flag", "reorder"]:
            self._flag_reorder(args[2], args[3:])
        else:
            raise CLIError(f"the model does not know `flagsmith {' '.join(argv)}`")
        self.updated_at = datetime.now(timezone.utc)

    def document(self) -> dict[str, Any]:
        """The environment document, in the shape Flagsmith's API serves it."""
        segments = []
        for name, segment in self.segments.items():
            states = [self._state(feature, o["enabled"], o["value"], priority=o["priority"])
                      for (feature, seg), o in self.overrides.items() if seg == name]
            segments.append({"id": segment["id"], "name": name, "rules": [_engine_rule(segment["rules"])],
                             "feature_states": states})
        return {
            "id": 1,
            "api_key": self.client_key,
            "name": "demo",
            "updated_at": self.updated_at.isoformat(),
            "feature_states": [self._state(name, f["enabled"], f["value"]) for name, f in self.features.items()],
            "identity_overrides": [],
            "project": {
                "id": 1,
                "name": "otelfeature-demo",
                "organisation": {"id": 1, "name": "otelfeature", "feature_analytics": False,
                                 "persist_trait_data": True, "stop_serving_flags": False},
                "hide_disabled_flags": False,
                "server_key_only_feature_ids": [],
                "segments": segments,
            },
        }

    def _state(self, feature: str, enabled: bool, value: Any, priority: int | None = None) -> dict:
        state = {
            "feature": {"id": self.features[feature]["id"], "name": feature, "type": "STANDARD"},
            "enabled": enabled,
            "feature_state_value": value,
            "featurestate_uuid": f"00000000-0000-4000-8000-{self.features[feature]['id']:012d}",
            "multivariate_feature_state_values": [],
        }
        if priority is not None:
            state["feature_segment"] = {"priority": priority}
        return state

    def _next_id(self) -> int:
        self._ids += 1
        return self._ids

    def _feature_create(self, name: str, opts: dict) -> None:
        if name in self.features:
            raise CLIError(f"feature {name} already exists")
        value = _infer(opts["--value"], None) if "--value" in opts else None
        self.features[name] = {"id": self._next_id(), "enabled": "--enabled" in opts, "value": value}

    def _segment_write(self, name: str, opts: dict, create: bool) -> None:
        if create == (name in self.segments):
            raise CLIError(f"segment {name} {'already exists' if create else 'not found'}")
        rules = json.loads(opts["--rules"])
        if create:
            self.segments[name] = {"id": self._next_id(), "rules": rules}
        else:
            self.segments[name]["rules"] = rules

    def _flag_update(self, feature: str, opts: dict) -> None:
        if feature not in self.features:
            raise CLIError(f"feature {feature} not found")
        segment = opts.get("--segment")
        if segment is None:
            target = self.features[feature]
        else:
            if segment not in self.segments:
                raise CLIError(f"segment {segment} not found")
            key = (feature, segment)
            if key not in self.overrides:
                default = self.features[feature]
                taken = [o["priority"] for (f, _), o in self.overrides.items() if f == feature]
                self.overrides[key] = {"enabled": default["enabled"], "value": default["value"],
                                       "priority": max(taken, default=-1) + 1}
            target = self.overrides[key]
            if "--priority" in opts:
                target["priority"] = int(opts["--priority"])
        if "--enable" in opts:
            target["enabled"] = True
        if "--disable" in opts:
            target["enabled"] = False
        if "--value" in opts:
            target["value"] = _infer(opts["--value"], opts.get("--type"))

    def _flag_delete(self, feature: str, opts: dict) -> None:
        key = (feature, opts["--segment"])
        if key not in self.overrides:
            raise CLIError(f"{feature} has no override for segment {opts['--segment']}")
        del self.overrides[key]

    def _flag_reorder(self, feature: str, segments: list[str]) -> None:
        overridden = {seg for (f, seg) in self.overrides if f == feature}
        if set(segments) != overridden or len(segments) != len(overridden):
            raise CLIError(f"reorder must name every overridden segment of {feature} once")
        for priority, seg in enumerate(segments):
            self.overrides[(feature, seg)]["priority"] = priority


# CLI options that take a value; every other option is a switch.
_VALUED = {"--value", "--type", "--segment", "--priority", "--rules", "--description"}


def _parse(argv: list[str]) -> tuple[list[str], dict[str, Any]]:
    args: list[str] = []
    opts: dict[str, Any] = {}
    it = iter(argv)
    for arg in it:
        if arg in _VALUED:
            opts[arg] = next(it)
        elif arg.startswith("--"):
            opts[arg] = True
        else:
            args.append(arg)
    return args, opts


def _infer(raw: str, forced: str | None) -> Any:
    """The value `--value` stores: like the CLI, `true`/`false` and integers are typed."""
    kind = forced or ("boolean" if raw in ("true", "false") else "integer" if _is_int(raw) else "string")
    if kind == "boolean":
        return raw == "true"
    if kind == "integer":
        return int(raw)
    return raw


def _is_int(raw: str) -> bool:
    try:
        int(raw)
    except ValueError:
        return False
    return True


def _engine_rule(rule: dict) -> dict:
    """A CLI rule file (`segment create --rules`) as the environment document holds it."""
    return {
        "type": rule["type"],
        "conditions": [{"operator": c["operator"], "property_": c.get("property"),
                        "value": None if c.get("value") is None else str(c["value"])}
                       for c in rule.get("conditions") or []],
        "rules": [_engine_rule(r) for r in rule.get("rules") or []],
    }
