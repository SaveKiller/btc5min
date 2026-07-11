"""Build feed .txt round sintetici Lighter da CSV raw-btc."""

import math
import sys
from datetime import datetime, timezone
from multiprocessing import Manager, Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.binary_format import OUTCOME_FROM_NAME
from src.lighter_gamma import (
    GAMMA_CACHE_NAME,
    GammaBroker,
    ensure_gamma_day,
    fetch_gamma,
    init_worker_broker,
    install_broker,
)
from src.lighter_sampling import WINDOW_SEC, build_ticks_array, load_csv_ticks, sample_round
from src.lighter_ticks import day_start_ts_from_path, hour_band
from src.lighter_txt_format import render_lighter_round_txt
from src.settlement import outcome_from_prices

NAN = float("nan")


def _hhmm_utc(start_ts: int) -> str:
    return datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%H%M")


def _txt_path(out_dir: Path, week_iso: str, start_ts: int) -> Path:
    return out_dir / week_iso / f"btc5m_{start_ts}_{_hhmm_utc(start_ts)}.txt"


def _day_round_starts(day_start: int) -> list[int]:
    day_end = day_start + 86400
    t = day_start
    starts: list[int] = []
    while t + WINDOW_SEC < day_end:
        starts.append(t)
        t += WINDOW_SEC
    return starts


def _build_header(start_ts: int, samples, gamma: dict) -> tuple[dict, list[str]]:
    ptb = round(samples[0].mid, 2)
    final = round(samples[300].mid, 2)
    outcome_lighter = outcome_from_prices(final, ptb)
    delta_lighter = final - ptb
    warnings: list[str] = []
    ptb_g = gamma.get("ptb")
    final_g = gamma.get("final")
    outcome_gamma = gamma.get("outcome")
    has_gamma_prices = ptb_g is not None and final_g is not None and not (
        isinstance(ptb_g, float) and math.isnan(ptb_g))
    if has_gamma_prices:
        ptb_gamma = round(float(ptb_g), 2)
        final_gamma = round(float(final_g), 2)
        delta_chainlink = final_gamma - ptb_gamma
        move_error = delta_lighter - delta_chainlink
    else:
        ptb_gamma = NAN
        final_gamma = NAN
        delta_chainlink = NAN
        move_error = NAN
        warnings.append("gamma metadata incomplete or missing")
    if outcome_gamma in ("Up", "Down"):
        outcome = OUTCOME_FROM_NAME[outcome_gamma]
        agreement: bool | None = outcome_gamma == outcome_lighter
        if agreement is False:
            warnings.append("outcome lighter disagrees with gamma official")
    else:
        outcome = OUTCOME_FROM_NAME[outcome_lighter]
        agreement = None
        if gamma.get("error"):
            warnings.append(f"gamma fetch failed: {gamma['error']}")
        else:
            warnings.append("outcome from lighter proxy, gamma outcome unavailable")
    header = {
        "market_start_ts": start_ts,
        "market_end_ts": start_ts + WINDOW_SEC,
        "intraday_h": hour_band(start_ts),
        "ptb_price": ptb,
        "ptb_chainlink": ptb,
        "ptb_gamma": ptb_gamma,
        "final_price": final,
        "final_chainlink": final,
        "final_gamma": final_gamma,
        "outcome_lighter": outcome_lighter,
        "outcome": outcome,
        "outcome_agreement": agreement,
        "delta_lighter": delta_lighter,
        "delta_chainlink": delta_chainlink,
        "move_error": move_error,
        "tick_count": WINDOW_SEC,
    }
    return header, warnings


def build_day_csv(csv_path: Path, out_dir: Path) -> dict:
    week_iso = csv_path.parent.name
    day_start = day_start_ts_from_path(str(csv_path))
    starts = _day_round_starts(day_start)
    stats = {"attempted": len(starts), "written": 0, "skipped": 0, "present": 0, "gamma_prefetch": 0}
    pending = [t for t in starts if not _txt_path(out_dir, week_iso, t).is_file()]
    stats["present"] = len(starts) - len(pending)
    if not pending:
        return stats
    stats["gamma_prefetch"] = ensure_gamma_day(day_start)
    ts, bid, ask = load_csv_ticks(str(csv_path))
    for t in starts:
        dest = _txt_path(out_dir, week_iso, t)
        if dest.is_file():
            continue
        try:
            samples = sample_round(ts, bid, ask, t)
        except Exception:
            stats["skipped"] += 1
            continue
        gamma = fetch_gamma(t)
        header, warnings = _build_header(t, samples, gamma)
        ticks = build_ticks_array(samples)
        txt = render_lighter_round_txt(header, ticks, warnings)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(txt, encoding="utf-8")
        stats["written"] += 1
    return stats


def _worker_process_day(job: tuple[str, str]) -> tuple[str, dict]:
    csv_path, out_dir = job
    cp = Path(csv_path)
    stats = build_day_csv(cp, Path(out_dir))
    return f"{cp.parent.name}/{cp.name}", stats


def _fmt_stats(stats: dict) -> str:
    return (
        f"written={stats['written']} present={stats['present']} "
        f"skipped={stats['skipped']} attempted={stats['attempted']} "
        f"gamma_prefetch={stats['gamma_prefetch']}"
    )


def cmd_test_day(csv_path: str, out_dir: str, cache_name: str) -> None:
    cp = Path(csv_path)
    od = Path(out_dir)
    install_broker(GammaBroker.local(od / cache_name))
    stats = build_day_csv(cp, od)
    print(f"test-day {cp.name}: {_fmt_stats(stats)}", flush=True)


def cmd_all(input_root: str, out_dir: str, workers: int, cache_name: str) -> None:
    root = Path(input_root)
    od = Path(out_dir)
    cache_path = od / cache_name
    csv_files = sorted(root.rglob("raw-btc-*.csv"))
    if not csv_files:
        raise Exception(f"no raw-btc csv under {root}")
    if workers < 1:
        raise Exception(f"workers must be >= 1, got {workers}")
    total = {"attempted": 0, "written": 0, "skipped": 0, "present": 0, "gamma_prefetch": 0}
    jobs = [(str(p), str(od)) for p in csv_files]
    if workers == 1:
        install_broker(GammaBroker.local(cache_path))
        for csv_path in csv_files:
            stats = build_day_csv(csv_path, od)
            for k in total:
                total[k] += stats[k]
            print(f"{csv_path.parent.name}/{csv_path.name}: {_fmt_stats(stats)}", flush=True)
    else:
        manager = Manager()
        broker = GammaBroker.shared(manager, cache_path)
        initargs = (str(cache_path), broker.lock, broker.shared_cache)
        print(f"parallel pool: {workers} workers, {len(jobs)} days, gamma prefetch per giorno", flush=True)
        with Pool(workers, initializer=init_worker_broker, initargs=initargs) as pool:
            for label, stats in pool.imap_unordered(_worker_process_day, jobs):
                for k in total:
                    total[k] += stats[k]
                print(f"{label}: {_fmt_stats(stats)}", flush=True)
    print(f"all done: {_fmt_stats(total)}", flush=True)


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception(
            "usage: build_lighter_rounds.py test-day <csv> <out_dir> [cache_name] | "
            "all <input_root> <out_dir> <workers> [cache_name]")
    cmd = sys.argv[1]
    cache_name = sys.argv[-1] if len(sys.argv) > 2 and sys.argv[-1].endswith(".jsonl") else GAMMA_CACHE_NAME
    if cmd == "test-day":
        if len(sys.argv) not in (4, 5):
            raise Exception("usage: build_lighter_rounds.py test-day <csv> <out_dir> [cache_name]")
        cmd_test_day(sys.argv[2], sys.argv[3], cache_name)
    elif cmd == "all":
        if len(sys.argv) not in (5, 6):
            raise Exception("usage: build_lighter_rounds.py all <input_root> <out_dir> <workers> [cache_name]")
        cmd_all(sys.argv[2], sys.argv[3], int(sys.argv[4]), cache_name)
    else:
        raise Exception(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
