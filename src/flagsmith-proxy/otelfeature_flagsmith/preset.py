"""The Flagsmith preset command: a stage preset applied with the Flagsmith CLI.

    flagsmith-flag <preset>          apply a preset, wait until flagd serves it
    flagsmith-flag seed              create the demo features and segments
    flagsmith-flag plan <preset>     print the CLI calls `<preset>` would make
    flagsmith-flag check [<preset>]  compare what Flagsmith holds with a preset file

(`docker compose -f compose.yaml -f compose.flagsmith.yaml run --rm
flagsmith-flag …`.) A preset file in src/flagd/presets is the state; demo.json
says which segment overrides each preset switches on (UC-008 BR-009). The
command reads the environment document first and writes only what differs:
overrides created or deleted, values set, `flag reorder` when the order of a
flag's overrides changed, and `demoPreset` last (BR-010). Without a document
it writes everything and ignores deleting an override that isn't there.
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
from .translate import MARKER, TranslationError, load_catalog, translate, _variant

EDGE_API_URL = os.environ.get("FLAGSMITH_EDGE_API_URL", "https://edge.api.flagsmith.com/api/v1")


def load(name: str) -> tuple[dict, dict, dict]:
    demo = json.loads(DEMO.read_text())
    if name not in demo["presets"]:
        raise SystemExit(f"unknown preset {name!r}, one of: {', '.join(demo['presets'])}")
    return demo, load_catalog(CATALOG), json.loads((PRESETS / f"{name}.json").read_text())


def seed_plan(document: dict | None = None) -> list[list[str]]:
    """Create the features and segments the presets need; existing segments get their rules again."""
    demo, catalog = json.loads(DEMO.read_text()), load_catalog(CATALOG)
    features = {fs["feature"]["name"] for fs in (document or {}).get("feature_states") or []}
    segments = {s["name"] for s in ((document or {}).get("project") or {}).get("segments") or []}
    argv = []
    for key, flag in catalog["flags"].items():
        if key in features:
            continue
        create = ["feature", "create", key, "--description", flag.get("metadata", {}).get("description", key)]
        value = flag["variants"][flag["defaultVariant"]]
        argv.append(create + (["--enabled"] if value else []) if isinstance(value, bool)
                    else create + ["--value", _text(value), "--enabled"])
    if MARKER not in features:
        argv.append(["feature", "create", MARKER, "--value", "00-baseline", "--enabled",
                     "--description", "Preset last applied (UC-008 BR-010); not a flag the services read"])
    for name, rules in demo["segments"].items():
        argv.append(["segment", "update" if name in segments else "create", name,
                     "--rules", json.dumps(rules, separators=(",", ":"))])
    return argv


def apply_plan(name: str, document: dict | None = None) -> list[list[str]]:
    """The CLI calls that turn the environment in `document` into preset `name`."""
    demo, catalog, preset = load(name)
    known = document is not None
    current_defaults, current_overrides = _current(document, catalog) if known else ({}, {})
    on = demo["presets"][name]
    argv = []
    for key, entries in demo["overrides"].items():
        flag = catalog["flags"][key]
        wanted = [e["segment"] for e in entries if e["segment"] in on.get(key, [])]
        kept = sorted((p, seg) for (k, seg), (p, _) in current_overrides.items() if k == key and seg in wanted)
        order = [seg for _, seg in kept]
        for e in entries:
            seg, held = e["segment"], current_overrides.get((key, e["segment"]))
            if seg in wanted:
                if held is None or held[1] != e["serves"]:
                    argv.append(["flag", "update", key, "--segment", seg, *_value_args(flag, e["serves"])])
                if held is None:
                    order.append(seg)  # a new override joins at the end
            elif held is not None or not known:
                argv.append(["flag", "delete", key, "--segment", seg])
        if len(wanted) > 1 and (order != wanted or not known):
            argv.append(["flag", "reorder", key, *wanted])
    for key, flag in catalog["flags"].items():
        variant = preset["flags"][key]["defaultVariant"]
        if current_defaults.get(key) != variant:
            argv.append(["flag", "update", key, *_value_args(flag, variant)])
    argv.append(["flag", "update", MARKER, "--value", name, "--type", "string", "--enable"])
    return argv


def execute(plan: list[list[str]], run: Callable[[list[str]], None]) -> None:
    for argv in plan:
        try:
            run(argv)
        except CLIError as error:
            if argv[:2] == ["flag", "delete"] and "no override" in str(error):
                continue
            raise


def _current(document: dict, catalog: dict) -> tuple[dict[str, str], dict[tuple[str, str], tuple[float, Any]]]:
    """Which variant each flag serves now, by default and per segment override."""
    defaults = {}
    for fs in document.get("feature_states") or []:
        key = fs["feature"]["name"]
        if key in catalog["flags"]:
            defaults[key] = _served(key, catalog["flags"][key], fs)
    overrides = {}
    for segment in (document.get("project") or {}).get("segments") or []:
        for fs in segment.get("feature_states") or []:
            key = fs["feature"]["name"]
            if key in catalog["flags"]:
                priority = (fs.get("feature_segment") or {}).get("priority")
                overrides[(key, segment["name"])] = (float("inf") if priority is None else priority,
                                                     _served(key, catalog["flags"][key], fs))
    return defaults, overrides


def _served(key: str, flag: dict, fs: dict) -> str | None:
    is_boolean = all(isinstance(v, bool) for v in flag["variants"].values())
    if not is_boolean and not fs.get("enabled"):
        return None
    try:
        return _variant(key, flag, fs, "")
    except TranslationError:
        return None


def _value_args(flag: dict, variant: str) -> list[str]:
    value = flag["variants"][variant]
    if isinstance(value, bool):
        return ["--enable" if value else "--disable"]
    return ["--value", _text(value), "--type", "string", "--enable"]


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
    done = subprocess.run(["flagsmith", *argv, "--yes"], capture_output=True, text=True)
    if done.returncode != 0:
        raise CLIError((done.stderr or done.stdout).strip())


def wait_for_preset(name: str) -> bool:
    """Poll flagd's OFREP endpoint until the flag set names `name` (like src/flagd/flag.sh)."""
    url = os.environ.get("FLAGD_OFREP_URL", "http://flagd:8016").rstrip("/") + "/ofrep/v1/evaluate/flags"
    end = time.monotonic() + float(os.environ.get("FLAG_CONFIRM_TIMEOUT", "10"))
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
        execute(seed_plan(fetch_document()), run_cli)
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
        flag_set = translate(document, load_catalog(CATALOG))
        name = args[1] if len(args) > 1 else flag_set.get("metadata", {}).get("preset", "")
        expected = load(name)[2]
        if flag_set == expected:
            print(f"Flagsmith holds {name}")
            return 0
        print(f"Flagsmith does not hold {name}; it translates to:\n{json.dumps(flag_set, indent=2)}")
        return 1
    name = command
    load(name)
    execute(apply_plan(name, fetch_document()), run_cli)
    print(f"Flagsmith is now {name}, waiting for flagd to serve it", file=sys.stderr)
    if wait_for_preset(name):
        print(f"flagd serves {name}")
        return 0
    print(f"flagd does not serve {name} after {os.environ.get('FLAG_CONFIRM_TIMEOUT', '10')}s; "
          "see docker compose logs flagsmith-proxy", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
