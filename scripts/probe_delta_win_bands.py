"""Probe win rate osservato per fascia |delta| sui round reali (supporto metodo A)."""

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.convert import iter_round_bin_paths
from src.delta_win import load_delta_win_artifact
from scripts.eval_delta_win_v2_compare import collect_real_samples

_DATA_DIR = _ROOT / "data"
_REPORTS = _DATA_DIR / "reports"


def _band_table(samples: list[dict]) -> list[dict]:
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for s in samples:
        groups[(s["sec"], s["band"])].append(s)
    rows = []
    for (sec, band), items in sorted(groups.items()):
        wins = sum(s["y_win"] for s in items)
        n = len(items)
        pa = sum(s["p_a"] for s in items) / n
        rows.append({
            "sec": sec, "band": band, "n": n,
            "win_rate_observed": wins / n, "p_a_mean": pa,
            "gap_pp": (wins / n - pa) * 100,
        })
    return rows


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR
    artifact = load_delta_win_artifact()
    bin_paths = iter_round_bin_paths(data_dir)
    if not bin_paths:
        raise Exception(f"no bin files under {data_dir}")
    samples = collect_real_samples(bin_paths, artifact)
    if not samples:
        raise Exception("no eligible samples")
    table = _band_table(samples)
    sec90 = [r for r in table if r["sec"] == 90 and r["n"] >= 50]
    spread90 = max(r["win_rate_observed"] for r in sec90) - min(r["win_rate_observed"] for r in sec90) if len(sec90) >= 2 else 0.0
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "eligible_samples": len(samples),
        "bands": table,
        "sec90_bands_n50": len(sec90),
        "sec90_win_rate_spread_pp": spread90 * 100,
    }
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = _REPORTS / f"delta_win_bands_probe_{ts}.json"
    out.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(f"written {out}")
    print(f"bands={len(table)} sec90_spread={spread90 * 100:.1f}pp")


if __name__ == "__main__":
    main()
