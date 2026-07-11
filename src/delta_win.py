"""Probabilità delta_win: vittoria del lato indicato dal segno del delta al checkpoint."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from src.risk import norm_cdf
from src.setup import DELTA_WIN_CHECKPOINTS, DELTA_WIN_MODEL_PATH, VOLATILITY_WINDOWS_SEC

_ROOT = Path(__file__).resolve().parent.parent
_HOUR_BANDS_PATH = _ROOT / "hour_bands.json"
_artifact_cache: dict | None = None
_SIGMA_EPS = 1e-9


def hour_bands_hash() -> str:
    return hashlib.sha256(_HOUR_BANDS_PATH.read_bytes()).hexdigest()[:16]


def parse_delta_txt(cell: str) -> int | None:
    s = cell.strip()
    if s == "---":
        return None
    if s.endswith("$"):
        s = s[:-1]
    return int(s)


def parse_vol_txt(token: str) -> int | None:
    parts = token.split()
    if len(parts) != 2 or parts[1] == "---":
        return None
    return int(parts[1])


def parse_quote_side(quote: str) -> str:
    label = quote.strip().upper()
    if label == "UP":
        return "Up"
    if label == "DOWN":
        return "Down"
    raise Exception(f"invalid quote side: {quote!r}")


def parse_intraday_h(hdr: dict, start_ts: int) -> int:
    if "intraday" in hdr:
        raw = hdr["intraday"].strip()
        if not raw.startswith("H"):
            raise Exception(f"invalid intraday header: {raw}")
        return int(raw[1:])
    from src.lighter_ticks import hour_band
    return hour_band(start_ts)


def z_score_w(abs_delta: int, vol_w: int, window_sec: int, sec: int) -> float | None:
    if vol_w <= 0 or sec <= 0:
        return None
    sigma_step = vol_w / math.sqrt(window_sec - 1)
    denom = sigma_step * math.sqrt(sec)
    if denom <= _SIGMA_EPS:
        return None
    return abs_delta / denom


def brownian_win_prob(abs_delta: int, vol_w: int, window_sec: int, sec: int) -> float | None:
    z = z_score_w(abs_delta, vol_w, window_sec, sec)
    if z is None:
        return None
    return norm_cdf(z)


def _feature_vector(abs_delta: int, vols: dict[int, int], intraday_h: int) -> np.ndarray:
    feats = [math.log1p(abs_delta)]
    for w in VOLATILITY_WINDOWS_SEC:
        feats.append(math.log1p(vols[w]))
    for h in range(1, 7):
        feats.append(1.0 if intraday_h == h else 0.0)
    return np.asarray(feats, dtype=np.float64)


def _isotonic_predict(x: float, knots_x: list[float], knots_y: list[float]) -> float:
    if x <= knots_x[0]:
        return knots_y[0]
    if x >= knots_x[-1]:
        return knots_y[-1]
    for i in range(1, len(knots_x)):
        if x <= knots_x[i]:
            x0, x1 = knots_x[i - 1], knots_x[i]
            y0, y1 = knots_y[i - 1], knots_y[i]
            if x1 <= x0:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return knots_y[-1]


def load_delta_win_artifact(path: Path | None = None) -> dict:
    global _artifact_cache
    p = path if path is not None else Path(DELTA_WIN_MODEL_PATH)
    if not p.is_file():
        raise Exception(f"delta_win model not found: {p}")
    if _artifact_cache is not None and _artifact_cache.get("_path") == str(p):
        return _artifact_cache
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("hour_bands_hash") != hour_bands_hash():
        raise Exception(f"delta_win hour_bands_hash mismatch: {data.get('hour_bands_hash')} vs {hour_bands_hash()}")
    if set(data.get("checkpoints", [])) != set(DELTA_WIN_CHECKPOINTS):
        raise Exception("delta_win checkpoint list mismatch with setup.json")
    data["_path"] = str(p)
    _artifact_cache = data
    return data


def predict_delta_win(sec: int, abs_delta: int, vols: dict[int, int], intraday_h: int,
        artifact: dict | None = None) -> float | None:
    if sec not in DELTA_WIN_CHECKPOINTS:
        return None
    for w in VOLATILITY_WINDOWS_SEC:
        if vols[w] is None:
            return None
    art = artifact if artifact is not None else load_delta_win_artifact()
    sec_key = str(sec)
    if sec_key not in art["models_by_sec"]:
        raise Exception(f"delta_win model missing sec={sec}")
    m = art["models_by_sec"][sec_key]
    if m["type"] == "prevalence":
        return float(m["p"])
    if m["type"] == "brownian":
        return brownian_win_prob(abs_delta, vols[m["vol_window"]], m["vol_window"], sec)
    if m["type"] == "lookup":
        z = z_score_w(abs_delta, vols[m["vol_window"]], m["vol_window"], sec)
        if z is None:
            return None
        table = m["table"]
        for row in table:
            if z <= row["z_hi"]:
                return float(row["p"])
        return float(table[-1]["p"])
    if m["type"] == "logistic_isotonic":
        x = float(np.dot(_feature_vector(abs_delta, vols, intraday_h), np.asarray(m["coef"], dtype=np.float64)) + m["intercept"])
        p_raw = 1.0 / (1.0 + math.exp(-x))
        return _isotonic_predict(p_raw, m["iso_x"], m["iso_y"])
    raise Exception(f"unknown delta_win model type: {m['type']}")


def format_delta_win_cell(prob: float | None) -> str:
    if prob is None:
        return "---"
    return f"{prob * 100:.1f}%"


def delta_win_header_lines(artifact: dict) -> list[str]:
    return [
        f"  delta_win_model_version: {artifact['model_version']}",
        f"  delta_win_hour_bands_hash: {artifact['hour_bands_hash']}",
        f"  delta_win_status: {artifact['status']}",
        f"  delta_win_target: {artifact['target']}",
        f"  delta_win_label_source: {artifact['label_source']}",
        f"  delta_win_checkpoints: {artifact['checkpoints']}",
        f"  delta_win_training_samples: {artifact['training_sample_count']}",
        f"  delta_win_training_start_ts_min: {artifact['training_start_ts_min']}",
        f"  delta_win_training_start_ts_max: {artifact['training_start_ts_max']}",
        f"  delta_win_method: {artifact['method']}",
    ]


def delta_win_column_width() -> int:
    return 6


def checkpoint_stale_in_vol_window(rows_by_sec: dict[int, dict], sec: int, window: int) -> bool:
    for s in range(sec, sec + window):
        row = rows_by_sec.get(s)
        if row is None:
            raise Exception(f"missing sec {s} in round rows")
        if row["delta_stale"]:
            return True
    return False


def delta_win_from_row(sec: int, row: dict, rows_by_sec: dict[int, dict], intraday_h: int,
        artifact: dict) -> str:
    if sec not in DELTA_WIN_CHECKPOINTS:
        return "---"
    if checkpoint_stale_in_vol_window(rows_by_sec, sec, max(VOLATILITY_WINDOWS_SEC)):
        return "---"
    if row["delta"] is None:
        return "---"
    vols = row["vols"]
    for w in VOLATILITY_WINDOWS_SEC:
        if vols.get(w) is None:
            return "---"
    vol_int = {w: vols[w] for w in VOLATILITY_WINDOWS_SEC}
    p = predict_delta_win(sec, abs(row["delta"]), vol_int, intraday_h, artifact)
    return format_delta_win_cell(p)
