#!/usr/bin/env python3
"""Sample one Linux process using /proc without external dependencies."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def _process_ticks(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
    return int(fields[13]) + int(fields[14])


def _memory_kib(pid: int) -> tuple[int, int]:
    values = {}
    for line in Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, value, _unit = line.split()
            values[key.rstrip(":")] = int(value)
    return values.get("VmRSS", 0), values.get("VmHWM", 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    clock_ticks = os.sysconf("SC_CLK_TCK")
    started_at = time.monotonic()
    previous_at = started_at
    previous_ticks = _process_ticks(args.pid)
    samples = []
    while time.monotonic() - started_at < args.duration:
        time.sleep(args.interval)
        sampled_at = time.monotonic()
        ticks = _process_ticks(args.pid)
        rss_kib, high_water_kib = _memory_kib(args.pid)
        elapsed = sampled_at - previous_at
        samples.append(
            {
                "elapsed_seconds": round(sampled_at - started_at, 3),
                "one_core_cpu_percent": round((ticks - previous_ticks) / clock_ticks / elapsed * 100, 3),
                "rss_mib": round(rss_kib / 1024, 3),
                "high_water_mib": round(high_water_kib / 1024, 3),
            }
        )
        previous_at = sampled_at
        previous_ticks = ticks

    result = {
        "pid": args.pid,
        "cpu_basis": "delta process utime+stime / wall time; 100% equals one logical CPU",
        "duration_seconds": round(time.monotonic() - started_at, 3),
        "sample_interval_seconds": args.interval,
        "sample_count": len(samples),
        "average_one_core_cpu_percent": round(
            sum(item["one_core_cpu_percent"] for item in samples) / len(samples), 3
        ),
        "peak_one_core_cpu_percent": max(item["one_core_cpu_percent"] for item in samples),
        "average_rss_mib": round(sum(item["rss_mib"] for item in samples) / len(samples), 3),
        "peak_rss_mib": max(item["rss_mib"] for item in samples),
        "process_high_water_mib": max(item["high_water_mib"] for item in samples),
        "samples": samples,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
