"""Measurement harness for Demo 2's numbers and decision D3 (UC-003, TC-003).

Runs inside the e2e runner image as the `bench` compose service
(compose.bench.yaml); `make bench` drives it:

    bench.py apply <baseline|noop|quiet-noise>
    bench.py measure <label> --mode <processor|sampler> --warmup S --seconds S
    bench.py report

What each number is (UC-003 BR-007), per service, at the service:
- CPU: container CPU time over the window / window length, % of one core
- RSS: container memory usage minus page cache at the end of the window, MB
- spans/s: spans with that service.name the collector received in the window
- export KB/s: those spans as OTLP protobuf (ResourceSpans) bytes, uncompressed

The decision cost (UC-003 BR-006) is the `noop` run's CPU minus the
baseline's: a recordSpan rule that reads a span attribute but never matches,
so every span is decided with a built context and none is dropped.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import socket
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, "/e2e/tests")
from flags import Flags  # noqa: E402  (the e2e flag helper: mtime bump + OFREP barrier)

from google.protobuf import json_format  # noqa: E402
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans  # noqa: E402

SERVICES = ("geocode", "weather")
PROJECT = os.environ.get("BENCH_PROJECT", "otelfeature-bench")
RESULTS = Path("/results")
SPANS_FILE = Path(os.environ.get("E2E_SPANS_FILE", "/out/spans.jsonl"))
RUN_ORDER = ["baseline", "noop", "quiet-noise-processor", "quiet-noise-sampler"]


# ── Docker API over the unix socket ───────────────────────────────────
class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str):
        super().__init__("localhost")
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._path)


def _docker(path: str):
    conn = _UnixConnection("/var/run/docker.sock")
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read()
    if response.status != 200:
        raise RuntimeError(f"docker {path}: HTTP {response.status} {body[:200]!r}")
    return json.loads(body)


def _container(service: str) -> str:
    filters = json.dumps({"label": [f"com.docker.compose.project={PROJECT}",
                                    f"com.docker.compose.service={service}"]})
    found = _docker(f"/containers/json?filters={urllib.parse.quote(filters)}")
    if len(found) != 1:
        raise RuntimeError(f"expected one running {service} container, found {len(found)}")
    return found[0]["Id"]


def _stats(container: str) -> dict:
    return _docker(f"/containers/{container}/stats?stream=false&one-shot=true")


def _rss_mb(stats: dict) -> float:
    memory = stats["memory_stats"]
    cache = memory.get("stats", {}).get("inactive_file", memory.get("stats", {}).get("total_inactive_file", 0))
    return (memory["usage"] - cache) / 1024 / 1024


# ── Spans from the collector file ─────────────────────────────────────
def _ids_to_base64(node):
    """OTLP/JSON writes ids as hex; the protobuf JSON mapping wants base64."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("traceId", "spanId", "parentSpanId") and isinstance(value, str):
                node[key] = base64.b64encode(bytes.fromhex(value)).decode()
            else:
                _ids_to_base64(value)
    elif isinstance(node, list):
        for item in node:
            _ids_to_base64(item)


def _span_totals(start: int, end: int) -> dict[str, dict[str, int]]:
    """Spans and protobuf bytes per service.name in [start, end) of the file."""
    totals = {service: {"spans": 0, "bytes": 0} for service in SERVICES}
    with SPANS_FILE.open("rb") as f:
        f.seek(start)
        data = f.read(end - start)
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line cut at the window edge
        for rs in request.get("resourceSpans", []):
            attrs = {a["key"]: a.get("value", {}).get("stringValue") for a in rs.get("resource", {}).get("attributes", [])}
            service = attrs.get("service.name")
            if service not in totals or attrs.get("service.instance.id") != service:
                continue
            totals[service]["spans"] += sum(len(ss.get("spans", [])) for ss in rs.get("scopeSpans", []))
            _ids_to_base64(rs)
            totals[service]["bytes"] += json_format.ParseDict(rs, ResourceSpans(), ignore_unknown_fields=True).ByteSize()
    return totals


def _file_size() -> int:
    return SPANS_FILE.stat().st_size if SPANS_FILE.exists() else 0


# ── Commands ──────────────────────────────────────────────────────────
def apply(run: str) -> None:
    flags = Flags(Path(os.environ["E2E_FLAGS_FILE"]), Path(os.environ["E2E_PRESETS_DIR"]),
                  os.environ.get("FLAGD_OFREP_URL", "http://flagd:8016"))
    if run == "baseline":
        flags.apply("00-baseline")
    elif run == "quiet-noise":
        flags.apply("02-quiet-noise")
    elif run == "noop":
        config = flags.preset("00-baseline")
        config["flags"]["recordSpan"]["targeting"] = {
            "if": [{"==": [{"var": "url.path"}, "/never-matches"]}, "off", "on"]
        }
        flags.write(config)
    else:
        raise SystemExit(f"unknown run {run!r}")
    print(f"flags: {run}", flush=True)


def measure(label: str, mode: str, warmup: float, seconds: float) -> None:
    print(f"{label}: warming up {warmup:.0f} s", flush=True)
    time.sleep(warmup)
    containers = {s: _container(s) for s in SERVICES}
    cpu0 = {s: _stats(c)["cpu_stats"]["cpu_usage"]["total_usage"] for s, c in containers.items()}
    file0, t0 = _file_size(), time.monotonic()
    print(f"{label}: measuring {seconds:.0f} s", flush=True)
    time.sleep(seconds)
    end_stats = {s: _stats(c) for s, c in containers.items()}
    file1, t1 = _file_size(), time.monotonic()
    elapsed = t1 - t0
    spans = _span_totals(file0, file1)
    result = {"label": label, "mode": mode, "seconds": round(elapsed, 1), "services": {}}
    for service in SERVICES:
        cpu_ns = end_stats[service]["cpu_stats"]["cpu_usage"]["total_usage"] - cpu0[service]
        result["services"][service] = {
            "cpu_pct": round(cpu_ns / 1e9 / elapsed * 100, 2),
            "rss_mb": round(_rss_mb(end_stats[service]), 1),
            "spans_per_s": round(spans[service]["spans"] / elapsed, 2),
            "export_kb_per_s": round(spans[service]["bytes"] / 1024 / elapsed, 2),
        }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{label}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


def _delta(value: float, base: float) -> str:
    if not base:
        return ""
    return f" ({(value - base) / base * 100:+.0f}%)"


def report() -> None:
    results = {p.stem: json.loads(p.read_text()) for p in RESULTS.glob("*.json")}
    runs = [r for r in RUN_ORDER if r in results]
    if "baseline" not in results:
        raise SystemExit("no baseline result")
    print(f"# Measurement (OTelFeature/poc#27), {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n")
    print(f"Window {results['baseline']['seconds']:.0f} s per run. Deltas against the baseline.\n")
    for service in SERVICES:
        base = results["baseline"]["services"][service]
        print(f"## {service}\n")
        print("| Run | Java mode | CPU % | RSS MB | spans/s | export KB/s |")
        print("|---|---|---|---|---|---|")
        for run in runs:
            r = results[run]
            v = r["services"][service]
            cells = [f"{v[k]}{_delta(v[k], base[k]) if run != 'baseline' else ''}"
                     for k in ("cpu_pct", "rss_mb", "spans_per_s", "export_kb_per_s")]
            print(f"| {run} | {r['mode']} | " + " | ".join(cells) + " |")
        if "noop" in results:
            cost = results["noop"]["services"][service]["cpu_pct"] - base["cpu_pct"]
            print(f"\nDecision cost (targeted no-op − baseline, UC-003 BR-006): {cost:+.2f} % of one core\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("apply")
    a.add_argument("run")
    m = sub.add_parser("measure")
    m.add_argument("label")
    m.add_argument("--mode", default="processor")
    m.add_argument("--warmup", type=float, default=45)
    m.add_argument("--seconds", type=float, default=120)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "apply":
        apply(args.run)
    elif args.command == "measure":
        measure(args.label, args.mode, args.warmup, args.seconds)
    else:
        report()


if __name__ == "__main__":
    main()
