"""Measurement harness for Demo 2's numbers and decision D3 (UC-003, TC-003).

Runs inside the e2e runner image as the `bench` compose service
(compose.bench.yaml); `make bench` drives it:

    bench.py apply <baseline|noop|quiet-noise>
    bench.py measure <label> --mode <processor|sampler> --warmup S --seconds S
    bench.py report

What each number is (UC-003 BR-007), per service, at the service:
- CPU: container CPU time per 5 s sample / 5 s, % of one core; mean and sd
  over the window
- Memory: container memory usage minus inactive file cache, mean over the
  window, MB (what `docker stats` shows; not the process RSS)
- req/s: the service's business requests (SERVER spans not on /health; no
  rule drops them), the check that every run got the same load
- spans/s: spans of that service instance the collector received
- export KB/s: those spans as OTLP protobuf (ResourceSpans), uncompressed

The decision cost (UC-003 BR-006) is a `noop` run's CPU minus the baseline's
in the same Java mode: a recordSpan rule that reads a span attribute but never
matches, so every span is decided with a built context and none is dropped.
Reported per span (µs, comparable with the extensions' micro-benchmarks,
NFR-005) and as % of one core.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import socket
import statistics
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
SAMPLE_SECONDS = 5.0
RUN_ORDER = ["baseline", "noop", "quiet-noise-processor",
             "baseline-sampler", "noop-sampler", "quiet-noise-sampler"]
SERVER_KIND = 2


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


def _sample(container: str) -> tuple[int, float]:
    """(CPU time in ns, memory usage minus inactive file cache in MB)."""
    stats = _docker(f"/containers/{container}/stats?stream=false&one-shot=true")
    memory = stats["memory_stats"]
    detail = memory.get("stats", {})
    cache = detail.get("total_inactive_file", detail.get("inactive_file", 0))
    usage = memory["usage"]
    return stats["cpu_stats"]["cpu_usage"]["total_usage"], (usage - cache if cache < usage else usage) / 1024 / 1024


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


def _url_path(span: dict) -> str | None:
    for a in span.get("attributes", []):
        if a["key"] in ("url.path", "http.target"):
            return a.get("value", {}).get("stringValue")
    return None


def _span_totals(start: int, end: int) -> dict[str, dict[str, int]]:
    """Per service instance in [start, end) of the file: spans, protobuf
    bytes, and business requests (SERVER spans not on /health)."""
    totals = {service: {"spans": 0, "bytes": 0, "requests": 0} for service in SERVICES}
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
            attrs = {a["key"]: a.get("value", {}).get("stringValue")
                     for a in rs.get("resource", {}).get("attributes", [])}
            service = attrs.get("service.name")
            if service not in totals or attrs.get("service.instance.id") != service:
                continue
            for ss in rs.get("scopeSpans", []):
                for span in ss.get("spans", []):
                    totals[service]["spans"] += 1
                    if span.get("kind") == SERVER_KIND and _url_path(span) not in (None, "/health"):
                        totals[service]["requests"] += 1
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
    previous = {s: _sample(c) for s, c in containers.items()}
    first_cpu = {s: previous[s][0] for s in SERVICES}
    cpu_samples = {s: [] for s in SERVICES}
    mem_samples = {s: [] for s in SERVICES}
    file0, t0 = _file_size(), time.monotonic()
    print(f"{label}: measuring {seconds:.0f} s", flush=True)
    last = t0
    while time.monotonic() - t0 < seconds:
        time.sleep(min(SAMPLE_SECONDS, seconds - (time.monotonic() - t0)))
        now = time.monotonic()
        for service, container in containers.items():
            cpu_ns, mem_mb = _sample(container)
            cpu_samples[service].append((cpu_ns - previous[service][0]) / 1e9 / (now - last) * 100)
            mem_samples[service].append(mem_mb)
            previous[service] = (cpu_ns, mem_mb)
        last = now
    file1, elapsed = _file_size(), time.monotonic() - t0
    spans = _span_totals(file0, file1)
    result = {"label": label, "mode": mode, "seconds": round(elapsed, 1), "services": {}}
    for service in SERVICES:
        cpu = cpu_samples[service]
        result["services"][service] = {
            "cpu_pct": round((previous[service][0] - first_cpu[service]) / 1e9 / elapsed * 100, 3),
            "cpu_sd": round(statistics.stdev(cpu), 3) if len(cpu) > 1 else 0.0,
            "mem_mb": round(statistics.mean(mem_samples[service]), 1),
            "req_per_s": round(spans[service]["requests"] / elapsed, 3),
            "spans_per_s": round(spans[service]["spans"] / elapsed, 3),
            "export_kb_per_s": round(spans[service]["bytes"] / 1024 / elapsed, 3),
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
    warnings = []
    print(f"# Measurement (OTelFeature/poc#27), {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n")
    print(f"{results['baseline']['seconds']:.0f} s per run, {os.environ.get('BENCH_SETTINGS', '')}. "
          "Deltas against `baseline` in the same Java mode. CPU: % of one core, mean ± sd of 5 s samples.\n")
    for service in SERVICES:
        print(f"## {service}\n")
        print("| Run | Java mode | CPU % | Memory MB | req/s | spans/s | export KB/s |")
        print("|---|---|---|---|---|---|---|")
        for run in runs:
            r = results[run]
            base_run = "baseline-sampler" if r["mode"] == "sampler" and "baseline-sampler" in results else "baseline"
            base = results[base_run]["services"][service]
            v = r["services"][service]
            own = run == base_run

            def cell(key):
                return f"{v[key]}{'' if own else _delta(v[key], base[key])}"
            print(f"| {run} | {r['mode']} | {v['cpu_pct']} ± {v['cpu_sd']}{'' if own else _delta(v['cpu_pct'], base['cpu_pct'])}"
                  f" | {cell('mem_mb')} | {v['req_per_s']} | {cell('spans_per_s')} | {cell('export_kb_per_s')} |")
            if base["req_per_s"] and abs(v["req_per_s"] - base["req_per_s"]) / base["req_per_s"] > 0.05:
                warnings.append(f"{service} {run}: {v['req_per_s']} req/s vs {base['req_per_s']} in {base_run}: "
                                "the runs did not get the same load")
        print()
        for noop, base_run in (("noop", "baseline"), ("noop-sampler", "baseline-sampler")):
            if noop in results and base_run in results:
                n, b = results[noop]["services"][service], results[base_run]["services"][service]
                delta_pct = n["cpu_pct"] - b["cpu_pct"]
                per_span_us = (delta_pct / 100 * 1e6 / n["spans_per_s"]) if n["spans_per_s"] else float("nan")
                print(f"Decision cost, {results[noop]['mode']} mode ({noop} − {base_run}, UC-003 BR-006): "
                      f"{delta_pct:+.3f} % of one core, {per_span_us:+.1f} µs per span "
                      f"(noise: sd {n['cpu_sd']} / {b['cpu_sd']})\n")
        if service == "geocode" and {"quiet-noise-processor", "quiet-noise-sampler"} <= results.keys():
            p = results["quiet-noise-processor"]["services"][service]["cpu_pct"]
            s = results["quiet-noise-sampler"]["services"][service]["cpu_pct"]
            print(f"Run-to-run noise: geocode's two 02-quiet-noise runs have the same configuration "
                  f"(the mode is Java-only) and differ by {s - p:+.3f} % of one core{_delta(s, p)}.\n")
    for w in warnings:
        print(f"> **Warning:** {w}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("apply")
    a.add_argument("run")
    m = sub.add_parser("measure")
    m.add_argument("label")
    m.add_argument("--mode", default="processor")
    m.add_argument("--warmup", type=float, default=120)
    m.add_argument("--seconds", type=float, default=300)
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
