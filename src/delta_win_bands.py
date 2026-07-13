"""Lookup |delta| 0-150 per delta_win metodo A: pool empirico per H + espansione finestra."""



from src.setup import DELTA_WIN_WINDOW_EXPAND_STEP, DELTA_WIN_WINDOW_HALF_BASE



DELTA_LOOKUP_MAX = 150





def clamp_delta(abs_delta: int, max_delta: int = DELTA_LOOKUP_MAX) -> int:

    return min(abs_delta, max_delta)





def window_bounds(d: int, max_delta: int = DELTA_LOOKUP_MAX, half: int = DELTA_WIN_WINDOW_HALF_BASE) -> tuple[int, int]:

    return max(0, d - half), min(max_delta, d + half)





def pool_in_range(sec_samples: list[dict], lo: int, hi: int) -> list[dict]:

    return [s for s in sec_samples if lo <= s["abs_delta"] <= hi]





def fit_window_for_sec_h(samples: list[dict], sec: int, intraday_h: int, min_samples: int,

        half_base: int = DELTA_WIN_WINDOW_HALF_BASE, expand_step: int = DELTA_WIN_WINDOW_EXPAND_STEP,

        max_delta: int = DELTA_LOOKUP_MAX) -> dict[str, dict]:

    sec_samples = [s for s in samples if s["sec"] == sec and s["intraday_h"] == intraday_h]

    if not sec_samples:

        raise Exception(f"no samples for sec={sec} intraday_h={intraday_h}")

    out: dict[str, dict] = {}

    for center_d in range(max_delta + 1):

        half = half_base

        lo, hi = window_bounds(center_d, max_delta, half)

        pool = pool_in_range(sec_samples, lo, hi)

        while len(pool) < min_samples:

            if lo == 0 and hi == max_delta:

                break

            half += expand_step

            lo, hi = window_bounds(center_d, max_delta, half)

            pool = pool_in_range(sec_samples, lo, hi)

        if len(pool) < min_samples:

            continue

        n = len(pool)

        p_win = sum(s["y_win"] for s in pool) / n

        out[str(center_d)] = {

            "p_win": p_win, "n": n, "lo": lo, "hi": hi,

            "half": half, "expanded": half > half_base,

        }

    return out


