import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "data" / "collector-poly.log"


def active_rounds_at(ts_str: str, rounds: dict) -> list[int]:
  """rounds: start_ts -> (spawn_line, done_line|None, done_secs|None)"""
  # parse log timestamp
  t = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
  active = []
  for start_ts, info in rounds.items():
    spawn_t = info["spawn_t"]
    done_t = info["done_t"]
    if spawn_t and t >= spawn_t and (done_t is None or t <= done_t):
      active.append(start_ts)
  return active


def main() -> tuple[list[int], list[int]]:
  log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else LOG
  lines = log_path.read_text(encoding="utf-8").splitlines()

  rounds: dict[int, dict] = {}
  events = defaultdict(list)

  for i, line in enumerate(lines, 1):
    m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)", line)
    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f") if m else None

    if m := re.search(r"round (\d+) sampling started", line):
      start = int(m.group(1))
      rounds.setdefault(start, {"spawn_t": None, "sample_t": None, "done_t": None, "done_secs": None, "outcome": None, "verify_err": [], "skipped": False})
      rounds[start]["sample_t"] = ts

    if m := re.search(r"round (\d+) skipped", line):
      start = int(m.group(1))
      rounds.setdefault(start, {"spawn_t": None, "sample_t": None, "done_t": None, "done_secs": None, "outcome": None, "verify_err": [], "skipped": True})
      rounds[start]["skipped"] = True

    if m := re.search(r"round (\d+) done (\d+) seconds outcome=(\w+) file=(\S+)", line):
      start = int(m.group(1))
      rounds.setdefault(start, {"spawn_t": None, "sample_t": None, "done_t": None, "done_secs": None, "outcome": None, "verify_err": [], "skipped": False})
      rounds[start]["done_t"] = ts
      rounds[start]["done_secs"] = int(m.group(2))
      rounds[start]["outcome"] = m.group(3)
      rounds[start]["file"] = m.group(4)

    if m := re.search(r"round (\d+) final_chainlink=.* outcome=(\w+)", line):
      start = int(m.group(1))
      rounds.setdefault(start, {"spawn_t": None, "done_t": None, "done_secs": None, "outcome": None, "verify_err": []})
      rounds[start]["settlement"] = m.group(2)

    if m := re.search(r"ERROR round (\d+) verify: (.+)", line):
      start = int(m.group(1))
      rounds.setdefault(start, {"spawn_t": None, "done_t": None, "done_secs": None, "outcome": None, "verify_err": []})
      rounds[start]["verify_err"].append(m.group(2))
      events["verify_error"].append((i, line, start, m.group(2)))

    for key, pat in [
      ("chainlink_stall", r"chainlink stall"),
      ("chainlink_ws_error", r"chainlink ws error"),
      ("clob_ws_drop", r"clob round (\d+) ws drop"),
      ("round_failed", r"ERROR round (\d+) failed"),
      ("no_seconds", r"no seconds collected"),
    ]:
      if m := re.search(pat, line):
        events[key].append((i, line, ts, m.groups()))

  done = [r for r in rounds.values() if r.get("done_secs") is not None]
  computed = [ts for ts, r in rounds.items() if r.get("settlement") == "computed"]
  bad_ticks = [(ts, r) for ts, r in rounds.items() if r.get("done_secs") not in (None, 300)]

  print("=== RIEPILOGO ===")
  print(f"righe log: {len(lines)}")
  print(f"round completati: {len(done)}")
  print(f"chainlink stall: {len(events['chainlink_stall'])}")
  print(f"chainlink ws error: {len(events['chainlink_ws_error'])}")
  print(f"clob ws drop: {len(events['clob_ws_drop'])}")
  print(f"verify ERROR: {len(events['verify_error'])}")
  print(f"round failed: {len(events['round_failed'])}")
  print(f"no seconds: {len(events['no_seconds'])}")
  print(f"outcome=computed (gamma timeout): {len(computed)}")
  print(f"done con tick != 300: {len(bad_ticks)}")

  print("\n=== CHAINLINK STALL / WS ERROR (round in campionamento) ===")
  for key in ("chainlink_stall", "chainlink_ws_error"):
    for ln, line, ts, _ in events[key]:
      active = []
      if ts:
        for start_ts, info in rounds.items():
          if info.get("skipped") or not info.get("sample_t"):
            continue
          if ts >= info["sample_t"]:
            if info.get("done_t") is None or ts <= info["done_t"]:
              active.append(start_ts)
      print(f"L{ln} [{ts}] sampling_active={active}")
      print(f"  {line.split(', ', 2)[-1]}")

  print("\n=== VERIFY ERROR ===")
  for ln, line, start, err in events["verify_error"]:
    print(f"L{ln} round {start}: {err}")

  print("\n=== ROUND A RISCHIO CHAINLINK (stall/error durante campionamento) ===")
  risky = set()
  for key in ("chainlink_stall", "chainlink_ws_error"):
    for ln, line, ts, _ in events[key]:
      if not ts:
        continue
      for start_ts, info in rounds.items():
        if info.get("skipped") or not info.get("sample_t"):
          continue
        if ts >= info["sample_t"]:
          if info.get("done_t") is None or ts <= info["done_t"]:
            risky.add(start_ts)
  for ts in sorted(risky):
    r = rounds[ts]
    print(f"  {ts} done={r.get('done_secs')} settlement={r.get('settlement')} verify={r.get('verify_err')} file={r.get('file')}")

  print("\n=== OUTCOME COMPUTED (affidabilità settlement, non chainlink feed) ===")
  print(f"  {len(computed)} round su {len(done)} ({100*len(computed)/max(len(done),1):.1f}%)")

  print("\n=== CLOB WS DROP (quote LOB mancanti, chainlink ok) ===")
  clob_rounds = sorted({int(g[0]) for _, _, _, g in events["clob_ws_drop"]})
  print(f"  {len(clob_rounds)} round distinti con drop CLOB")

  verify_rounds = sorted({start for _, _, start, _ in events["verify_error"]})
  return sorted(risky), verify_rounds


def analyze_txt_files(risky_ts: list[int]) -> None:
  import re
  data = Path(__file__).resolve().parent.parent / "data"
  print("\n=== ANALISI FILE TXT ROUND A RISCHIO ===")
  for ts in risky_ts:
    matches = list(data.glob(f"**/btc5m_{ts}.txt"))
    p = matches[0] if matches else data / "txt" / f"btc5m_{ts}.txt"
    if not p.exists():
      print(f"{ts}: file mancante")
      continue
    text = p.read_text(encoding="utf-8")
    warns = []
    in_w = False
    for line in text.splitlines():
      if line == "  warnings:":
        in_w = True
        continue
      if in_w:
        if line.startswith("    - "):
          warns.append(line[6:])
        else:
          break
    rows = []
    for line in text.splitlines():
      m = re.search(r"btc=\s*([\d.]+)", line)
      if m and line[:3].strip().isdigit():
        sec = int(line.split()[0])
        partial = " --- " in line or "DOWN ---" in line or " UP  ---" in line
        rows.append((sec, float(m.group(1)), partial))
    flats = []
    if rows:
      s = rows[0]
      prev = rows[0]
      for cur in rows[1:]:
        if cur[1] == prev[1]:
          prev = cur
        else:
          if prev[0] - s[0] >= 4:
            flats.append((s[0], prev[0], s[1], prev[0] - s[0] + 1))
          s = cur
          prev = cur
      if prev[0] - s[0] >= 4:
        flats.append((s[0], prev[0], s[1], prev[0] - s[0] + 1))
    stale_ticks = None
    for line in text.splitlines():
      if line.strip().startswith("stale_ticks:"):
        stale_ticks = line.split(":", 1)[1].strip()
    delta_stale = sum(1 for line in text.splitlines() if "  ---" in line and "gain=" in line)
    print(f"\n{ts}: ticks={len(rows)} partial_quote={sum(1 for r in rows if r[2])} "
          f"delta_stale={delta_stale} stale_ticks={stale_ticks} warnings={warns}")
    for lo, hi, price, n in flats[:3]:
      print(f"  btc flat {hi}-{lo} sec ({n} tick) @ {price}")


if __name__ == "__main__":
  risky, verify_rounds = main()
  analyze_txt_files(sorted(set(risky) | set(verify_rounds)))
