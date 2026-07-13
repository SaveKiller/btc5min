"""Statistiche (prefisso li) sui round sintetici Lighter."""

import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.delta_win import parse_delta_txt, parse_intraday_h, parse_quote_side, parse_vol_txt
from src.setup import DELTA_WIN_SECS, DELTA_WIN_TXT_COLUMNS, TICKS_ROOT, VOLATILITY_WINDOWS_SEC

_LIGHTER_ROUNDS_DIR = "lighter-rounds5m"
_START_TS_RE = re.compile(r"btc5m_(\d+)_")


def _is_btc_cell(token: str) -> bool:
    return token.endswith("$") and token[:-1].isdigit()


def _parse_delta_win_cells(parts: list[str], start: int, btc_i: int) -> tuple[str | None, str | None, int]:
    dw_a, dw_b = None, None
    i = start
    while i < btc_i:
        if parts[i] == "---":
            if "a" in DELTA_WIN_TXT_COLUMNS and dw_a is None:
                dw_a = "---"
            elif "b" in DELTA_WIN_TXT_COLUMNS:
                dw_b = "---"
            i += 1
        elif i + 1 < btc_i and parts[i + 1].startswith("["):
            dw_a = f"{parts[i]} {parts[i + 1]}"
            i += 2
        else:
            if "b" in DELTA_WIN_TXT_COLUMNS and dw_b is None:
                dw_b = parts[i]
            elif "a" in DELTA_WIN_TXT_COLUMNS and dw_a is None:
                dw_a = parts[i]
            i += 1
    return dw_a, dw_b, i


def _parse_data_row_line(line: str) -> dict:
    parts = line.split()
    if len(parts) < 10:
        raise Exception(f"unparsable data row: {line}")
    rd_i = parts.index("Rd")
    sec = int(parts[0])
    delta = parse_delta_txt(parts[3])
    btc_i = next(i for i in range(4, rd_i) if _is_btc_cell(parts[i]))
    dw_a, dw_b, _ = _parse_delta_win_cells(parts, 4, btc_i)
    vols: dict[int, int | None] = {}
    i = btc_i + 1
    while i < rd_i:
        if not parts[i].startswith("V"):
            break
        w = int(parts[i][1:])
        vols[w] = parse_vol_txt(f"{parts[i]} {parts[i + 1]}")
        i += 2
    return {
        "sec": sec, "side": parse_quote_side(parts[2]), "delta": delta, "vols": vols,
        "delta_stale": delta is None, "delta_win_a": dw_a, "delta_win_b": dw_b,
    }


def li_rounds_root(root: Path | None = None) -> Path:
    base = root if root is not None else Path(TICKS_ROOT)
    path = base / _LIGHTER_ROUNDS_DIR
    if not path.is_dir():
        raise Exception(f"lighter rounds directory not found: {path}")
    return path


def iter_lighter_round_txt(root: Path | None = None) -> list[Path]:
    return sorted(li_rounds_root(root).rglob("btc5m_*.txt"))


def read_lighter_header(path: Path) -> dict:
    fields: dict[str, str] = {}
    warnings: list[str] = []
    in_warnings = False
    with path.open(encoding="utf-8") as f:
        if f.readline().rstrip("\n") != "header:":
            raise Exception(f"{path}: expected header:")
        for line in f:
            line = line.rstrip("\n")
            if line == "data:":
                break
            if line == "  warnings:":
                in_warnings = True
                continue
            if in_warnings:
                if line.startswith("    - "):
                    warnings.append(line[6:])
                continue
            if not line.startswith("  ") or ": " not in line:
                continue
            key, value = line[2:].split(": ", 1)
            fields[key] = value
    fields["warnings"] = warnings
    return fields


def read_lighter_data_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    in_data = False
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line == "data:":
                in_data = True
                continue
            if not in_data or not line or line.startswith("sec") or set(line) == {"-"}:
                continue
            rows.append(_parse_data_row_line(line))
    return rows

def _stale_in_vol_window(rows_by_sec: dict[int, dict], sec: int, window: int) -> bool:
    from src.vol_stats import vol_window_countdown_secs
    for s in vol_window_countdown_secs(sec, window):
        row = rows_by_sec.get(s)
        if row is None:
            raise Exception(f"missing sec {s} in round rows")
        if row["delta_stale"]:
            return True
    return False


def li_delta_win_samples(path: Path, secs: tuple[int, ...] = DELTA_WIN_SECS) -> list[dict]:
    hdr = read_lighter_header(path)
    if hdr.get("source") != "lighter_synthetic":
        raise Exception(f"{path}: source is not lighter_synthetic")
    if hdr.get("outcome_agreement") == "nan":
        return []
    start_ts = _start_ts_from_name(path)
    outcome = hdr["outcome"]
    intraday_h = parse_intraday_h(hdr, start_ts)
    week = path.parent.name
    data_rows = read_lighter_data_rows(path)
    by_sec = {r["sec"]: r for r in data_rows}
    out: list[dict] = []
    for sec in secs:
        row = by_sec.get(sec)
        if row is None:
            raise Exception(f"{path}: missing delta_win sec={sec}")
        if _stale_in_vol_window(by_sec, sec, max(VOLATILITY_WINDOWS_SEC)):
            continue
        if row["delta"] is None:
            continue
        for w in VOLATILITY_WINDOWS_SEC:
            if row["vols"].get(w) is None:
                break
        else:
            y_win = 1 if row["side"] == outcome else 0
            out.append({
                "path": str(path), "start_ts": start_ts, "week": week, "sec": sec,
                "abs_delta": abs(row["delta"]), "vols": {w: row["vols"][w] for w in VOLATILITY_WINDOWS_SEC},
                "intraday_h": intraday_h, "side": row["side"], "outcome": outcome, "y_win": y_win,
                "outcome_agreement": hdr.get("outcome_agreement"),
            })
    return out


def li_collect_delta_win_dataset(root: Path | None = None) -> list[dict]:
    samples: list[dict] = []
    weeks = sorted({p.parent.name for p in iter_lighter_round_txt(root)})
    week_rank = {w: i for i, w in enumerate(weeks)}
    for path in iter_lighter_round_txt(root):
        for rec in li_delta_win_samples(path):
            rec["week_idx"] = week_rank[rec["week"]]
            samples.append(rec)
    return samples


def _collect_one_file(args: tuple[str, dict[str, int]]) -> list[dict]:
    path_str, week_rank = args
    path = Path(path_str)
    out: list[dict] = []
    for rec in li_delta_win_samples(path):
        rec["week_idx"] = week_rank[rec["week"]]
        out.append(rec)
    return out


def li_collect_delta_win_dataset_parallel(root: Path | None = None, workers: int = 8) -> list[dict]:
    from multiprocessing import Pool
    paths = [str(p) for p in iter_lighter_round_txt(root)]
    if not paths:
        raise Exception("no lighter round txt files")
    weeks = sorted({Path(p).parent.name for p in paths})
    week_rank = {w: i for i, w in enumerate(weeks)}
    if workers <= 1:
        return li_collect_delta_win_dataset(root)
    tasks = [(p, week_rank) for p in paths]
    samples: list[dict] = []
    with Pool(workers) as pool:
        for chunk in pool.imap_unordered(_collect_one_file, tasks, chunksize=32):
            samples.extend(chunk)
    return samples


def li_delta_win_audit(root: Path | None = None) -> dict:
    paths = iter_lighter_round_txt(root)
    weeks = Counter()
    agreement = Counter()
    missing_cp = Counter()
    eligible = 0
    by_sec = Counter()
    for path in paths:
        weeks[path.parent.name] += 1
        hdr = read_lighter_header(path)
        agreement[hdr.get("outcome_agreement", "?")] += 1
        recs = li_delta_win_samples(path)
        eligible += len(recs)
        for sec in DELTA_WIN_SECS:
            if not any(r["sec"] == sec for r in recs):
                missing_cp[sec] += 1
        by_sec.update(r["sec"] for r in recs)
    return {
        "round_count": len(paths), "weeks": dict(weeks), "outcome_agreement": dict(agreement),
        "eligible_delta_win_rows": eligible, "missing_delta_win_rounds": dict(missing_cp),
        "rows_by_sec": dict(by_sec),
    }


def _start_ts_from_name(path: Path) -> int:
    m = _START_TS_RE.match(path.name)
    if not m:
        raise Exception(f"unexpected lighter txt name: {path.name}")
    return int(m.group(1))


def _fmt_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _parse_audit_float(value: str) -> float | None:
    if value == "nan":
        return None
    return float(value)


def _print_table(title: str, rows: list[tuple[str, str]]) -> None:
    label_w = max(len(label) for label, _ in rows)
    val_w = max(len(value) for _, value in rows)
    line = "-" * (label_w + val_w + 3)
    print(title)
    print(line)
    for label, value in rows:
        print(f"  {label:<{label_w}}  {value}")
    print()


def li_summary(root: Path | None = None) -> dict:
    rounds_root = li_rounds_root(root)
    paths = iter_lighter_round_txt(root)
    if not paths:
        raise Exception(f"no lighter round txt files under {rounds_root}")

    outcome = Counter()
    outcome_lighter = Counter()
    agreement = Counter()
    tick_counts = Counter()
    weeks = Counter()
    ptb_gamma_nan = 0
    final_gamma_nan = 0
    with_warnings = 0
    stale_ticks_sum = 0
    move_error_sum = 0.0
    move_error_abs_sum = 0.0
    move_error_n = 0
    start_ts_list: list[int] = []

    for path in paths:
        hdr = read_lighter_header(path)
        if hdr.get("source") != "lighter_synthetic":
            raise Exception(f"{path}: source is not lighter_synthetic")
        start_ts_list.append(_start_ts_from_name(path))
        weeks[path.parent.name] += 1
        outcome[hdr["outcome"]] += 1
        outcome_lighter[hdr["outcome_lighter"]] += 1
        agreement[hdr["outcome_agreement"]] += 1
        tick_counts[int(hdr["tick_count"])] += 1
        if hdr["ptb_gamma"] == "nan":
            ptb_gamma_nan += 1
        if hdr["final_gamma"] == "nan":
            final_gamma_nan += 1
        if hdr["warnings"]:
            with_warnings += 1
        stale_ticks_sum += int(hdr["stale_ticks"])
        move_error = _parse_audit_float(hdr["move_error"])
        if move_error is not None:
            move_error_sum += move_error
            move_error_abs_sum += abs(move_error)
            move_error_n += 1

    n = len(paths)
    t_min, t_max = min(start_ts_list), max(start_ts_list)
    full_ticks = tick_counts.get(300, 0)
    disagree = agreement.get("FALSE", 0)
    if move_error_n == 0:
        raise Exception("no rounds with move_error (gamma delta unavailable on all rounds)")

    return {
        "rounds_root": str(rounds_root),
        "round_count": n,
        "week_folders": len(weeks),
        "weeks": dict(sorted(weeks.items())),
        "start_ts_min": t_min,
        "start_ts_max": t_max,
        "start_utc_min": _fmt_utc(t_min),
        "start_utc_max": _fmt_utc(t_max),
        "outcome": dict(outcome),
        "outcome_lighter": dict(outcome_lighter),
        "outcome_agreement": dict(agreement),
        "tick_count_300": full_ticks,
        "tick_count_other": n - full_ticks,
        "ptb_gamma_nan": ptb_gamma_nan,
        "final_gamma_nan": final_gamma_nan,
        "rounds_with_warnings": with_warnings,
        "outcome_disagreement": disagree,
        "stale_ticks_avg": stale_ticks_sum / n,
        "move_error_avg": move_error_sum / move_error_n,
        "move_error_abs_avg": move_error_abs_sum / move_error_n,
        "move_error_rounds": move_error_n,
    }


def print_li_summary(root: Path | None = None) -> None:
    s = li_summary(root)
    n = s["round_count"]
    up = s["outcome"].get("Up", 0)
    down = s["outcome"].get("Down", 0)
    up_li = s["outcome_lighter"].get("Up", 0)
    down_li = s["outcome_lighter"].get("Down", 0)
    agree = s["outcome_agreement"].get("TRUE", 0)
    disagree = s["outcome_agreement"].get("FALSE", 0)
    agree_nan = s["outcome_agreement"].get("nan", 0)

    print("Lighter rounds - sommario generale\n")
    _print_table("Database", [
        ("root", s["rounds_root"]),
        ("round totali", str(n)),
        ("settimane ISO", str(s["week_folders"])),
        ("da", s["start_utc_min"]),
        ("a", s["start_utc_max"]),
    ])
    _print_table("Outcome gamma (ufficiale)", [
        ("Up", f"{up}  ({100 * up / n:.1f}%)"),
        ("Down", f"{down}  ({100 * down / n:.1f}%)"),
    ])
    _print_table("Outcome lighter", [
        ("Up", str(up_li)),
        ("Down", str(down_li)),
    ])
    _print_table("Outcome agreement", [
        ("TRUE", str(agree)),
        ("FALSE", str(disagree)),
        ("nan", str(agree_nan)),
    ])
    _print_table("Qualita e audit", [
        ("tick_count 300", str(s["tick_count_300"])),
        ("tick_count altro", str(s["tick_count_other"])),
        ("ptb_gamma nan", str(s["ptb_gamma_nan"])),
        ("final_gamma nan", str(s["final_gamma_nan"])),
        ("round con warnings", str(s["rounds_with_warnings"])),
        ("stale_ticks media", f"{s['stale_ticks_avg']:.2f}"),
        ("move_error medio", f"{s['move_error_avg']:+.2f}$  ({s['move_error_rounds']} round)"),
        ("|move_error| medio", f"{s['move_error_abs_avg']:.2f}$"),
    ])
    week_rows = [(week, str(count)) for week, count in s["weeks"].items()]
    _print_table("Round per settimana", week_rows)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("summary", "li_summary"):
        print_li_summary()
        return
    raise Exception("usage: python -m src.listats [summary]")


if __name__ == "__main__":
    main()
