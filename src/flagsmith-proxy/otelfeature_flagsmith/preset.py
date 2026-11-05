"""The Flagsmith preset command: a stage preset applied with the Flagsmith CLI.

    flagsmith-flag <preset>          apply a preset, wait until flagd serves it
    flagsmith-flag seed              create the demo features, segments and overrides
    flagsmith-flag plan <preset>     print the CLI calls `<preset>` would make
    flagsmith-flag check [<preset>]  compare what Flagsmith holds with a preset file

(`docker compose -f compose.yaml -f compose.flagsmith.yaml run --rm
flagsmith-flag …`.) A preset file in src/flagd/presets is the state; demo.json
says which flags are gated and which segment overrides each preset switches
on (UC-008 BR-010, BR-014). Every override stays in Flagsmith, so a preset
is switches and values, the same an operator sets in the Flagsmith UI. The
command reads the environment document first and writes only what differs;
it creates or deletes an override only to repair one changed by hand
(missing, out of order, or not in demo.json). Without a document it writes
everything and ignores deleting an override that isn't there.

The flip counts once the proxy's flag set equals the preset file and flagd
serves it (BR-011). The document it diffed against can lag behind
Flagsmith's last write; if the proxy doesn't match within half the timeout,
it writes everything again.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from typing import Any, Callable

from . import CATALOG, DEMO, PRESETS
from .model import CLIError
from .translate import CUSTOM, TranslationError, load_catalog, translate, _is_boolean, _variant

EDGE_API_URL = os.environ.get("FLAGSMITH_EDGE_API_URL", "https://edge.api.flagsmith.com/api/v1")


def load(name: str) -> tuple[dict, dict, dict]:
    demo = json.loads(DEMO.read_text())
    if name not in demo["presets"]:
        raise SystemExit(f"unknown preset {name!r}, one of: {', '.join(demo['presets'])}")
    return demo, load_catalog(CATALOG), json.loads((PRESETS / f"{name}.json").read_text())


def segment_features(demo: dict) -> dict[str, str]:
    """Each segment is feature-specific to the one flag whose overrides use it."""
    return {e["segment"]: key for key, entries in demo["overrides"].items() for e in entries}


def seed_plan(document: dict | None = None) -> list[list[str]]:
    """Create the features and segments; existing segments get their rules again.

    The gated flags are created switched off, holding the value they serve
    once switched on. `seed` then applies 00-baseline blind, which creates
    every override.
    """
    demo, catalog = json.loads(DEMO.read_text()), load_catalog(CATALOG)
    features = {fs["feature"]["name"] for fs in (document or {}).get("feature_states") or []}
    segments = {s["name"] for s in ((document or {}).get("project") or {}).get("segments") or []}
    argv = []
    for key, flag in catalog["flags"].items():
        if key in features:
            continue
        create = ["feature", "create", key, "--description", flag.get("metadata", {}).get("description", key)]
        gated = key in demo["gated"]
        value = flag["variants"][demo["gated"][key] if gated else flag["defaultVariant"]]
        if isinstance(value, bool):
            argv.append(create + (["--enabled"] if value and not gated else []))
        else:
            argv.append(create + ["--value", _text(value)] + ([] if gated else ["--enabled"]))
    for name, feature in segment_features(demo).items():
        rules = json.dumps(demo["segments"][name], separators=(",", ":"))
        if name in segments:
            argv.append(["segment", "update", name, "--rules", rules])
        else:
            argv.append(["segment", "create", name, "--rules", rules, "--feature", feature])
    return argv


def apply_plan(name: str, document: dict | None = None) -> list[list[str]]:
    """The CLI calls that turn the environment in `document` into preset `name`."""
    demo, catalog, preset = load(name)
    known = document is not None
    current_states, current_overrides = _current(document, catalog) if known else ({}, {})
    on = demo["presets"][name]
    argv = []
    listed = {(key, e["segment"]) for key, entries in demo["overrides"].items() for e in entries}
    for key, seg in sorted(current_overrides):
        if (key, seg) not in listed:
            argv.append(["flag", "delete", key, "--segment", seg])
    for key, entries in demo["overrides"].items():
        flag = catalog["flags"][key]
        order = [seg for _, seg in sorted((o[0], seg) for (k, seg), o in current_overrides.items()
                                          if k == key and (k, seg) in listed)]
        for e in entries:
            seg, held = e["segment"], current_overrides.get((key, e["segment"]))
            # An override applies while switched on; a non-boolean one holds its variant. A
            # boolean one serves the flag's other variant, so its `serves` is only a check.
            wanted = (seg in on.get(key, []), None if _is_boolean(flag) else e["serves"])
            if held is None or held[1:] != wanted:
                argv.append(["flag", "update", key, "--segment", seg, *_state_args(flag, *wanted)])
            if held is None:
                order.append(seg)  # a new override joins at the end
        segments = [e["segment"] for e in entries]
        if len(segments) > 1 and (order != segments or not known):
            argv.append(["flag", "reorder", key, *segments])
    for key, flag in catalog["flags"].items():
        served = preset["flags"][key]
        if key in demo["gated"]:
            switched_on = served != flag
            wanted = _state(flag, served["defaultVariant"] if switched_on else demo["gated"][key], switched_on)
        else:
            wanted = _state(flag, served["defaultVariant"], True)
        if current_states.get(key) != wanted:
            argv.append(["flag", "update", key, *_state_args(flag, *wanted)])
    return argv


def execute(plan: list[list[str]], run: Callable[[list[str]], None]) -> None:
    for argv in plan:
        try:
            run(argv)
        except CLIError as error:
            if argv[:2] == ["flag", "delete"] and "no override" in str(error):
                continue
            raise


def _state(flag: dict, variant: str, switched_on: bool) -> tuple[bool, str | None]:
    """A feature state as (enabled, variant of its value); a boolean one has no value."""
    if _is_boolean(flag):
        return (flag["variants"][variant] and switched_on, None)
    return (switched_on, variant)


def _state_args(flag: dict, enabled: bool, variant: str | None) -> list[str]:
    switch = ["--enable" if enabled else "--disable"]
    if variant is None:
        return switch
    return ["--value", _text(flag["variants"][variant]), "--type", "string", *switch]


def _current(document: dict, catalog: dict) -> tuple[dict[str, tuple], dict[tuple[str, str], tuple]]:
    """Each flag's feature state now, by default and per segment override (with its priority)."""
    states = {}
    for fs in document.get("feature_states") or []:
        key = fs["feature"]["name"]
        if key in catalog["flags"]:
            states[key] = _held(key, catalog["flags"][key], fs)
    overrides = {}
    for segment in (document.get("project") or {}).get("segments") or []:
        for fs in segment.get("feature_states") or []:
            key = fs["feature"]["name"]
            if key in catalog["flags"]:
                priority = (fs.get("feature_segment") or {}).get("priority")
                overrides[(key, segment["name"])] = (float("inf") if priority is None else priority,
                                                     *_held(key, catalog["flags"][key], fs))
    return states, overrides


def _held(key: str, flag: dict, fs: dict) -> tuple[bool, str | None]:
    if _is_boolean(flag):
        return (bool(fs.get("enabled")), None)
    try:
        variant = _variant(key, flag, fs, "")
    except TranslationError:
        variant = None  # not a variant: written again
    return (bool(fs.get("enabled")), variant)


def _text(value: Any) -> str:
    return repr(value) if isinstance(value, float) else str(value)


# ── Against Flagsmith and flagd ─────────────────────────────────────────

def fetch_document() -> dict | None:
    key = os.environ.get("FLAGSMITH_SERVER_KEY")
    if not key:
        return None
    request = urllib.request.Request(f"{EDGE_API_URL.rstrip('/')}/environment-document/",
                                     headers={"X-Environment-Key": key})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except OSError as error:
        print(f"could not read the environment document ({error}); writing every value", file=sys.stderr)
        return None


def run_cli(argv: list[str]) -> None:
    print("flagsmith " + " ".join(argv), file=sys.stderr)
    cli_output(argv)


def cli_output(argv: list[str]) -> str:
    done = subprocess.run(["flagsmith", *argv, "--yes"], capture_output=True, text=True)
    if done.returncode != 0:
        raise CLIError((done.stderr or done.stdout).strip())
    return done.stdout


def wait_for_proxy(expected: dict, seconds: float) -> bool:
    """Poll the proxy until its flag set is `expected` (the preset file)."""
    url = os.environ.get("FLAGSMITH_PROXY_URL", "http://flagsmith-proxy:8000").rstrip("/") + "/api/v1/flagd/flags.json"
    headers = {"Authorization": f"Bearer {os.environ.get('FLAGSMITH_CLIENT_KEY', '')}"}
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=2) as response:
                if json.load(response) == expected:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    return False


def wait_for_preset(name: str, seconds: float) -> bool:
    """Poll flagd's OFREP endpoint until the flag set names `name` (like src/flagd/flag.sh)."""
    url = os.environ.get("FLAGD_OFREP_URL", "http://flagd:8016").rstrip("/") + "/ofrep/v1/evaluate/flags"
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        request = urllib.request.Request(url, data=b'{"context":{}}', headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.load(response)
            if any((f.get("metadata") or {}).get("preset") == name for f in body.get("flags", [])):
                return True
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    return False


def main(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    command = args[0]
    if command == "seed":
        # `segment list` shows only project-wide segments; a demo one there is
        # from an earlier seed and cannot be made feature-specific.
        listed = json.loads(cli_output(["segment", "list", "--json"]) or "[]")
        demo = json.loads(DEMO.read_text())
        stale = sorted({s.get("name") for s in listed} & set(demo["segments"]))
        if stale:
            print(f"project-wide segments {', '.join(stale)} are from an earlier seed; delete them in "
                  "the Flagsmith UI (Segments) and run seed again, which creates them feature-specific",
                  file=sys.stderr)
            return 1
        execute(seed_plan(fetch_document()), run_cli)
        execute(apply_plan("00-baseline"), run_cli)  # blind: creates every override
        return 0
    if command == "plan" and len(args) == 2:
        for argv in apply_plan(args[1], fetch_document()):
            print("flagsmith " + " ".join(argv))
        return 0
    if command == "check":
        document = fetch_document()
        if document is None:
            print("check needs FLAGSMITH_SERVER_KEY and a reachable FLAGSMITH_EDGE_API_URL", file=sys.stderr)
            return 2
        try:
            flag_set = translate(document, load_catalog(CATALOG))
        except TranslationError as error:
            print(f"the proxy would reject this environment: {error}")
            return 1
        name = args[1] if len(args) > 1 else flag_set["metadata"]["preset"]
        if name == CUSTOM:
            print(f"Flagsmith holds no preset; it translates to:\n{json.dumps(flag_set, indent=2)}")
            return 1
        expected = load(name)[2]
        if flag_set == expected:
            print(f"Flagsmith holds {name}")
            return 0
        print(f"Flagsmith does not hold {name}; it translates to:\n{json.dumps(flag_set, indent=2)}")
        return 1
    name = command
    expected = load(name)[2]
    timeout = float(os.environ.get("FLAG_CONFIRM_TIMEOUT", "10"))
    start = time.monotonic()
    plan = apply_plan(name, fetch_document())
    if not plan:
        # Held already, by the document; read it once more, in case a switch in the
        # Flagsmith UI just before is not in it yet (BR-011).
        time.sleep(1)
        plan = apply_plan(name, fetch_document())
    execute(plan, run_cli)
    print(f"Flagsmith is now {name}, waiting for flagd to serve it", file=sys.stderr)
    if not wait_for_proxy(expected, timeout / 2):
        print("the proxy does not serve the preset yet (stale document?); writing every value", file=sys.stderr)
        execute(apply_plan(name), run_cli)
    left = lambda: max(timeout - (time.monotonic() - start), 1.0)
    if wait_for_proxy(expected, left()) and wait_for_preset(name, left()):
        print(f"flagd serves {name}")
        return 0
    print(f"flagd does not serve {name} after {timeout:g}s; "
          "see docker compose logs flagsmith-proxy", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
