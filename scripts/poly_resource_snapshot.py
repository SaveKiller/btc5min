#!/usr/bin/env python3
"""Snapshot risorse collector su poly (stdout JSON line)."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


def read_status(pid: int) -> dict:
    out = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmSize:", "Threads:", "FDSize:")):
            k, v = line.split(":", 1)
            out[k] = v.strip()
    out["fd_count"] = len(list(Path(f"/proc/{pid}/fd").iterdir()))
    return out


def show_unit(unit: str) -> dict[str, str]:
    r = subprocess.run(["systemctl", "show", unit, "-p", "MainPID", "-p", "ActiveState"],
        capture_output=True, text=True)
    props = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v
    return props


def list_collector_units() -> list[str]:
    units = []
    for path in Path("/etc/systemd/system").glob("*.service"):
        name = path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "src.main" in text and "--asset" in text:
            units.append(name)
    return sorted(units)


def main() -> None:
    units = list_collector_units()
    if not units:
        units = ["btc5min", "btc15min"]
    payload = {"ts": int(time.time()), "units": {}}
    meminfo = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemTotal:", "MemFree:", "MemAvailable:", "Buffers:", "Cached:")):
            k, v = line.split(":", 1)
            meminfo[k] = v.strip()
    payload["meminfo"] = meminfo
    rss_sum = 0
    estab_sum = 0
    for unit in units:
        props = show_unit(unit)
        if not props:
            payload["units"][unit] = {"active": "missing"}
            continue
        active = props.get("ActiveState", "unknown")
        pid = int(props.get("MainPID", "0"))
        entry = {"active": active, "pid": pid}
        if pid > 0 and Path(f"/proc/{pid}").exists():
            entry.update(read_status(pid))
            ss = subprocess.run(["ss", "-tpn"], capture_output=True, text=True)
            entry["estab"] = sum(1 for ln in ss.stdout.splitlines() if f"pid={pid}," in ln and "ESTAB" in ln)
            if "VmRSS" in entry:
                rss_sum += int(entry["VmRSS"].split()[0])
            estab_sum += entry.get("estab", 0)
        payload["units"][unit] = entry
    payload["rss_sum_kb"] = rss_sum
    payload["estab_sum"] = estab_sum
    payload["unit_count"] = len(units)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
