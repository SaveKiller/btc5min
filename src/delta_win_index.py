"""Indici campioni delta_win per fit parallelo senza scan ripetuti."""

from collections import defaultdict


def build_sec_h_index(samples: list[dict]) -> dict[tuple[int, int], list[dict]]:
    out: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for s in samples:
        out[(s["sec"], s["intraday_h"])].append(s)
    return dict(out)


def sec_buckets(samples: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    for s in samples:
        out[s["sec"]].append(s)
    return dict(out)
