"""Fasce |delta| per delta_win metodo A: quantili, merge monotonia, p_win empirica."""

from collections import defaultdict

from src.setup import DELTA_WIN_BAND_MIN_SAMPLES


def _quantile_edges(values: list[int], n_bands: int) -> list[int]:
    if not values:
        raise Exception("no abs_delta values for band edges")
    sv = sorted(values)
    edges = []
    for q in range(1, n_bands):
        idx = min(len(sv) - 1, int(q * len(sv) / n_bands))
        edges.append(sv[idx])
    return sorted(set(edges))


def _assign_band(abs_delta: int, edges: list[int]) -> int:
    if abs_delta == 0:
        return 0
    for i, hi in enumerate(edges, start=1):
        if abs_delta <= hi:
            return i
    return len(edges) + 1


def _band_ranges(edges: list[int]) -> list[tuple[int, int]]:
    bands = [(0, 0)]
    lo = 1
    for hi in edges:
        bands.append((lo, hi))
        lo = hi + 1
    if edges:
        bands.append((edges[-1] + 1, 10**9))
    return bands


def _empirical_p(samples: list[dict]) -> tuple[float, int]:
    n = len(samples)
    if n == 0:
        raise Exception("empty band samples")
    p = sum(s["y_win"] for s in samples) / n
    return p, n


def _merge_low_sample_bands(bands: list[dict], min_samples: int) -> list[dict]:
    if not bands:
        raise Exception("empty bands list")
    out: list[dict] = []
    acc: list[dict] = []
    for b in bands:
        acc.append(b)
        total_n = sum(x["n"] for x in acc)
        if total_n >= min_samples or b is bands[-1]:
            lo = acc[0]["lo"]
            hi = acc[-1]["hi"]
            wins = sum(x["p_win"] * x["n"] for x in acc)
            n = sum(x["n"] for x in acc)
            out.append({"lo": lo, "hi": hi, "p_win": wins / n, "n": n})
            acc = []
    if acc:
        prev = out[-1]
        wins = prev["p_win"] * prev["n"] + sum(x["p_win"] * x["n"] for x in acc)
        n = prev["n"] + sum(x["n"] for x in acc)
        out[-1] = {"lo": prev["lo"], "hi": acc[-1]["hi"], "p_win": wins / n, "n": n}
    return out


def _enforce_monotonic(bands: list[dict]) -> list[dict]:
    if not bands:
        raise Exception("empty bands for monotonic merge")
    out = [dict(bands[0])]
    for b in bands[1:]:
        p = max(out[-1]["p_win"], b["p_win"])
        out.append({"lo": b["lo"], "hi": b["hi"], "p_win": p, "n": b["n"]})
    return out


def fit_bands_for_sec(samples: list[dict], sec: int, n_bands: int = 5,
        min_samples: int = DELTA_WIN_BAND_MIN_SAMPLES) -> list[dict]:
    sec_samples = [s for s in samples if s["sec"] == sec]
    if not sec_samples:
        raise Exception(f"no samples for sec={sec}")
    zero = [s for s in sec_samples if s["abs_delta"] == 0]
    pos = [s for s in sec_samples if s["abs_delta"] > 0]
    edges = _quantile_edges([s["abs_delta"] for s in pos], n_bands) if pos else []
    by_band: dict[int, list[dict]] = defaultdict(list)
    for s in sec_samples:
        by_band[_assign_band(s["abs_delta"], edges)].append(s)
    raw: list[dict] = []
    for bi in sorted(by_band):
        lo, hi = _band_ranges(edges)[bi]
        p, n = _empirical_p(by_band[bi])
        raw.append({"lo": lo, "hi": hi, "p_win": p, "n": n})
    merged = _merge_low_sample_bands(raw, min_samples)
    return _enforce_monotonic(merged)


def lookup_band(abs_delta: int, bands: list[dict]) -> dict:
    for b in bands:
        if b["lo"] <= abs_delta <= b["hi"]:
            return b
    return bands[-1]


def lookup_band_p_win(abs_delta: int, bands: list[dict]) -> float:
    return float(lookup_band(abs_delta, bands)["p_win"])
