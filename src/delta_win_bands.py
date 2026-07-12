"""Lookup |delta| 0-150 per delta_win metodo A: p_win empirica + finestra runtime ±2."""

from src.setup import DELTA_WIN_BAND_MIN_SAMPLES

DELTA_LOOKUP_MAX = 150
DELTA_WINDOW_HALF = 2


def clamp_delta(abs_delta: int, max_delta: int = DELTA_LOOKUP_MAX) -> int:
    return min(abs_delta, max_delta)


def window_bounds(d: int, max_delta: int = DELTA_LOOKUP_MAX, half: int = DELTA_WINDOW_HALF) -> tuple[int, int]:
    return max(0, d - half), min(max_delta, d + half)


def _pool_samples(sec_samples: list[dict], d: int, radius: int, max_delta: int) -> list[dict]:
    lo, hi = max(0, d - radius), min(max_delta, d + radius)
    return [s for s in sec_samples if lo <= s["abs_delta"] <= hi]


def fit_delta_p_for_sec(samples: list[dict], sec: int, max_delta: int = DELTA_LOOKUP_MAX,
        min_samples: int = DELTA_WIN_BAND_MIN_SAMPLES) -> dict[str, dict]:
    sec_samples = [s for s in samples if s["sec"] == sec]
    if not sec_samples:
        raise Exception(f"no samples for sec={sec}")
    out: dict[str, dict] = {}
    for d in range(max_delta + 1):
        radius = 0
        pool = _pool_samples(sec_samples, d, radius, max_delta)
        while len(pool) < min_samples and radius < max_delta:
            radius += 1
            pool = _pool_samples(sec_samples, d, radius, max_delta)
        if not pool:
            raise Exception(f"no samples for sec={sec} delta={d}")
        n = len(pool)
        p_win = sum(s["y_win"] for s in pool) / n
        out[str(d)] = {"p_win": p_win, "n": n, "merge_radius": radius}
    return out


def mean_p_window(table: dict[str, dict], lo: int, hi: int) -> float:
    ps = [float(table[str(i)]["p_win"]) for i in range(lo, hi + 1)]
    return sum(ps) / len(ps)
