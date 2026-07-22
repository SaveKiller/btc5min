#!/usr/bin/env python3
import json
from pathlib import Path

rows = [json.loads(l) for l in Path("/opt/btc5min/data/reports/resource_btc15m.jsonl").read_text().splitlines() if l.strip()]
print("n_samples", len(rows))


def rss_kb(row, unit):
    v = row["units"].get(unit, {}).get("VmRSS")
    if not v:
        return None
    return int(v.split()[0])


def avail_kb(row):
    return int(row["meminfo"]["MemAvailable"].split()[0])


total = 2097152
for unit in ("btc5min", "btc15min"):
    vals = [rss_kb(r, unit) for r in rows if rss_kb(r, unit) is not None]
    if vals:
        print(f"{unit} rss_kb min={min(vals)} max={max(vals)} last={vals[-1]}")

av = [avail_kb(r) for r in rows]
print(f"MemAvailable_kb min={min(av)} max={max(av)} last={av[-1]}")
print(f"free_pct_of_total_min={100 * min(av) / total:.1f}")

sums = []
for r in rows:
    e5 = r["units"].get("btc5min", {}).get("estab", 0) or 0
    e15 = r["units"].get("btc15min", {}).get("estab", 0) or 0
    sums.append(e5 + e15)
print("estab_sum max", max(sums), "last", sums[-1])

day = Path("/opt/btc5min/data/2026-07-22/bin")


def avg_size(glob):
    files = list(day.glob(glob))
    if not files:
        return 0, 0
    return len(files), sum(f.stat().st_size for f in files) / len(files)


n5, a5 = avg_size("btc5m_*.bin")
n15, a15 = avg_size("btc15m_*.bin")
print(f"today btc5m n={n5} avg_bytes={a5:.0f} est_mb_day={288 * a5 / 1e6:.1f}")
print(f"today btc15m n={n15} avg_bytes={a15:.0f} est_mb_day={96 * a15 / 1e6:.1f}")
print(f"combo_est_mb_day={(288 * a5 + 96 * a15) / 1e6:.1f}")
print(f"headroom_30d_gb={(99 * 1024 - 30 * (288 * a5 + 96 * a15) / 1e6) / 1024:.1f} (approx free 99G)")
