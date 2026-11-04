"""A Flagsmith environment document as a flagd flag set, for the demo flags.

The rules are the spec's (docs/spec/entity_model.md#flagsmith-mode, UC-008
BR-009, BR-013): the flags, their variants and metadata come from the
catalog (`00-baseline.json`); Flagsmith only decides which variant each flag
serves, by default and per segment override, and for a gated flag whether
it is served as in the catalog. `metadata.preset` names the preset file the
flags equal. Anything outside that subset raises TranslationError, and the
caller keeps its last good flag set.

Standard library only, so the CI checks run it without the Edge Proxy.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Iterable

from . import DEMO, PRESETS, STAGE_ORDER

# Flagsmith condition operators → JsonLogic. The numeric ones compare numbers.
COMPARISONS = {
    "EQUAL": "==",
    "NOT_EQUAL": "!=",
    "GREATER_THAN": ">",
    "GREATER_THAN_INCLUSIVE": ">=",
    "LESS_THAN": "<",
    "LESS_THAN_INCLUSIVE": "<=",
}
NUMERIC = {">", ">=", "<", "<="}

# The name of a flag set that equals no preset file (UC-008 BR-009).
CUSTOM = "custom"


class TranslationError(ValueError):
    """The environment uses something the translation does not support."""


def load_catalog(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def load_presets() -> dict[str, dict[str, Any]]:
    """The preset files in stage order, which `metadata.preset` is named after."""
    return {name: load_catalog(PRESETS / f"{name}.json") for name in STAGE_ORDER}


def gated_flags() -> set[str]:
    return set(json.loads(DEMO.read_text())["gated"])


def translate(document: dict[str, Any], catalog: dict[str, Any],
              presets: dict[str, dict] | None = None, gated: Iterable[str] | None = None) -> dict[str, Any]:
    presets = load_presets() if presets is None else presets
    gated = gated_flags() if gated is None else set(gated)
    defaults = {fs["feature"]["name"]: fs for fs in document.get("feature_states") or []}
    overrides: dict[str, list[tuple[float, int, dict, dict]]] = {}
    segments = (document.get("project") or {}).get("segments") or []
    for order, segment in enumerate(segments):
        for fs in segment.get("feature_states") or []:
            key = fs["feature"]["name"]
            if key in catalog["flags"]:
                overrides.setdefault(key, []).append((_priority(fs), order, segment, fs))

    flags = {}
    for key, base in catalog["flags"].items():
        flag = copy.deepcopy(base)
        flag.pop("targeting", None)
        fs = defaults.get(key)
        # A gated flag switched off (or missing) is the catalog's, without targeting.
        switched_off = key in gated and not (fs and fs.get("enabled"))
        if fs is not None and not switched_off:
            if not _is_boolean(base) and not fs.get("enabled"):
                # Served as disabled: the services fall back to their defaults.
                flag["state"] = "DISABLED"
            else:
                flag["defaultVariant"] = _variant(key, base, fs, "the default")
        chain: list[tuple[list[Any], str]] = []
        # Every override is checked, also those of a switched-off flag, so that
        # switching it on later is not what finds a bad one.
        for _, _, segment, fs in sorted(overrides.get(key, []), key=lambda o: o[:2]):
            name = segment.get("name", segment.get("id"))
            variant = _variant(key, base, fs, f"the override for segment {name!r}")
            rule = _segment_rule(segment)
            if not _is_boolean(base) and not fs.get("enabled"):
                continue  # a switched-off override of a non-boolean flag does not apply
            if chain and chain[-1][1] == variant:
                chain[-1][0].append(rule)
            else:
                chain.append(([rule], variant))
        if chain and not switched_off:
            args: list[Any] = []
            for rules, variant in chain:
                args += [_combine("or", rules), variant]
            args.append(flag["defaultVariant"])
            flag["targeting"] = {"if": args}
        flags[key] = flag

    name = next((n for n, preset in presets.items() if preset["flags"] == flags), CUSTOM)
    return {"$schema": catalog["$schema"], "metadata": {"preset": name}, "flags": flags}


def _priority(fs: dict) -> float:
    priority = (fs.get("feature_segment") or {}).get("priority")
    return math.inf if priority is None else priority


def _is_boolean(flag: dict) -> bool:
    return all(isinstance(v, bool) for v in flag["variants"].values())


def _variant(key: str, flag: dict, fs: dict, what: str) -> str:
    """The variant of `flag` that a Flagsmith feature state serves (a non-boolean one: its value)."""
    if fs.get("multivariate_feature_state_values"):
        raise TranslationError(f"{key}: {what} is a percentage split, which has no flagd counterpart here")
    if _is_boolean(flag):
        value: Any = bool(fs.get("enabled"))
    else:
        value = _typed(key, flag, fs.get("feature_state_value"), what)
    for name, candidate in flag["variants"].items():
        if type(candidate) is type(value) and candidate == value:
            return name
    raise TranslationError(f"{key}: {what} has the value {value!r}, which is not a variant "
                           f"({', '.join(map(repr, flag['variants'].values()))})")


def _typed(key: str, flag: dict, raw: Any, what: str) -> Any:
    sample = next(iter(flag["variants"].values()))
    if isinstance(sample, str):
        if isinstance(raw, str):
            return raw
    elif isinstance(sample, (int, float)) and not isinstance(raw, bool):
        try:
            number = float(raw)
        except (TypeError, ValueError):
            pass
        else:
            if math.isfinite(number):
                return number
    raise TranslationError(f"{key}: {what} has the value {raw!r}, not a {type(sample).__name__}")


def _segment_rule(segment: dict) -> Any:
    rules = segment.get("rules") or []
    if not rules:
        raise TranslationError(f"segment {segment.get('name')!r} has no rules")
    return _combine("and", [_rule(segment, r) for r in rules])


def _rule(segment: dict, rule: dict) -> Any:
    parts = [_condition(segment, c) for c in rule.get("conditions") or []]
    parts += [_rule(segment, r) for r in rule.get("rules") or []]
    if not parts:
        raise TranslationError(f"segment {segment.get('name')!r} has an empty {rule.get('type')} rule")
    kind = rule.get("type")
    if kind == "ALL":
        return _combine("and", parts)
    if kind == "ANY":
        return _combine("or", parts)
    if kind == "NONE":
        return {"!": _combine("or", parts)}
    raise TranslationError(f"segment {segment.get('name')!r} has a rule of type {kind!r}")


def _condition(segment: dict, condition: dict) -> dict:
    operator = condition.get("operator")
    prop = condition.get("property_", condition.get("property"))
    if operator not in COMPARISONS:
        raise TranslationError(f"segment {segment.get('name')!r} uses the operator {operator!r}")
    if not prop:
        raise TranslationError(f"segment {segment.get('name')!r} has a {operator} condition with no property")
    op = COMPARISONS[operator]
    value = condition.get("value")
    if op in NUMERIC:
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise TranslationError(f"segment {segment.get('name')!r}: {operator} needs a number, "
                                   f"not {value!r}") from None
    else:
        value = "" if value is None else str(value)
    return {op: [{"var": prop}, value]}


def _combine(op: str, parts: list[Any]) -> Any:
    """`and`/`or` of the parts: nested ones of the same kind flattened, one part as itself."""
    flat: list[Any] = []
    for part in parts:
        if isinstance(part, dict) and list(part) == [op]:
            flat += part[op]
        else:
            flat.append(part)
    return flat[0] if len(flat) == 1 else {op: flat}
