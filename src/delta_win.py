"""Probabilità delta_win v2: metodo A (griglia |delta| per H + finestra ±2) e B (logistic_isotonic)."""

import ast
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from src.delta_win_bands import DELTA_LOOKUP_MAX, clamp_delta
from src.setup import DELTA_WIN_CHECKPOINTS, DELTA_WIN_MODEL_PATH, DELTA_WIN_TXT_COLUMNS, VOLATILITY_WINDOWS_SEC

_ROOT = Path(__file__).resolve().parent.parent
_HOUR_BANDS_PATH = _ROOT / "hour_bands.json"
_artifact_cache: dict | None = None
_DW_HI_OPEN = 1_000_000
_DW_A_COL_W = 28
_DW_B_COL_W = 5
_DW_COL_LABEL_A = "DWinA"
_DW_COL_LABEL_B = "DWinB"
_HOUR_BANDS = tuple(range(1, 7))


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


def _feature_vector(abs_delta: int, vols: dict[int, int], intraday_h: int) -> np.ndarray:
    feats = [math.log1p(abs_delta)]
    for w in VOLATILITY_WINDOWS_SEC:
        feats.append(math.log1p(vols[w]))
    for h in _HOUR_BANDS:
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


def _validate_delta_window_by_sec_h(data: dict) -> None:
    if data.get("delta_win_band_stratify") != "intraday_h":
        raise Exception(f"delta_win artifact delta_win_band_stratify must be intraday_h, got {data.get('delta_win_band_stratify')}")
    if "delta_window_by_sec_h" not in data:
        raise Exception("delta_win v2 artifact missing delta_window_by_sec_h")
    for key in ("delta_win_window_min_samples", "delta_win_window_half_base", "delta_win_window_expand_step"):
        if key not in data:
            raise Exception(f"delta_win v2 artifact missing {key}")
    for h in _HOUR_BANDS:
        hk = str(h)
        if hk not in data["delta_window_by_sec_h"]:
            raise Exception(f"delta_win delta_window_by_sec_h missing H={h}")
        for sec in DELTA_WIN_CHECKPOINTS:
            sk = str(sec)
            if sk not in data["delta_window_by_sec_h"][hk]:
                raise Exception(f"delta_win delta_window_by_sec_h[{h}] missing sec={sec}")
            for slot in data["delta_window_by_sec_h"][hk][sk].values():
                for field in ("p_win", "n", "lo", "hi", "half", "expanded"):
                    if field not in slot:
                        raise Exception(f"delta_win slot missing {field}")


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
        raise Exception(
            f"delta_win checkpoint list mismatch with setup.json: "
            f"artifact={data.get('checkpoints')} setup={list(DELTA_WIN_CHECKPOINTS)} — run python scripts/study_delta_win_v2.py"
        )
    if data.get("model_version") != 2:
        raise Exception(f"delta_win artifact version must be 2, got {data.get('model_version')}")
    if "logistic_by_sec" not in data:
        raise Exception("delta_win v2 artifact missing logistic_by_sec")
    _validate_delta_window_by_sec_h(data)
    data["_path"] = str(p)
    _artifact_cache = data
    return data


def predict_delta_win_a_window(sec: int, abs_delta: int, intraday_h: int,
        artifact: dict | None = None) -> tuple[float, int, int, int, bool] | None:
    if sec not in DELTA_WIN_CHECKPOINTS:
        raise Exception(f"predict_delta_win_a_window called outside checkpoint sec={sec}")
    art = artifact if artifact is not None else load_delta_win_artifact()
    hk, sec_key, d_key = str(intraday_h), str(sec), str(clamp_delta(abs_delta))
    if hk not in art["delta_window_by_sec_h"]:
        raise Exception(f"delta_win delta_window missing intraday_h={intraday_h}")
    if sec_key not in art["delta_window_by_sec_h"][hk]:
        raise Exception(f"delta_win delta_window missing sec={sec} intraday_h={intraday_h}")
    slot = art["delta_window_by_sec_h"][hk][sec_key].get(d_key)
    if slot is None:
        return None
    return float(slot["p_win"]), int(slot["lo"]), int(slot["hi"]), int(slot["n"]), bool(slot["expanded"])


def predict_delta_win_a(sec: int, abs_delta: int, intraday_h: int, artifact: dict | None = None) -> float | None:
    if sec not in DELTA_WIN_CHECKPOINTS:
        return None
    win = predict_delta_win_a_window(sec, abs_delta, intraday_h, artifact)
    return None if win is None else win[0]


def predict_delta_win_b(sec: int, abs_delta: int, vols: dict[int, int], intraday_h: int,
        artifact: dict | None = None) -> float | None:
    if sec not in DELTA_WIN_CHECKPOINTS:
        return None
    for w in VOLATILITY_WINDOWS_SEC:
        if vols[w] is None:
            return None
    art = artifact if artifact is not None else load_delta_win_artifact()
    sec_key = str(sec)
    if sec_key not in art["logistic_by_sec"]:
        raise Exception(f"delta_win logistic missing sec={sec}")
    m = art["logistic_by_sec"][sec_key]
    x = float(np.dot(_feature_vector(abs_delta, vols, intraday_h), np.asarray(m["coef"], dtype=np.float64)) + m["intercept"])
    p_raw = 1.0 / (1.0 + math.exp(-x))
    return _isotonic_predict(p_raw, m["iso_x"], m["iso_y"])


def _fmt_band_range(lo: int, hi: int) -> str:
    if hi >= _DW_HI_OPEN:
        return f"{lo}$+" if lo > 0 else "0$+"
    if lo == hi == 0:
        return "0$"
    return f"{lo}$-{hi}$"


def _blank_cell(width: int) -> str:
    return " " * width


def format_delta_win_b_cell(prob: float | None) -> str:
    if prob is None:
        return "---"
    return f"{round(prob * 100)}%"


def format_delta_win_a_cell(prob: float | None, lo: int, hi: int, n: int, expanded: bool = False) -> str:
    if prob is None:
        return "---"
    star = "*" if expanded else ""
    return f"{round(prob * 100)}% [{_fmt_band_range(lo, hi)} n={n}{star}]"


def delta_win_a_column_width() -> int:
    return _DW_A_COL_W


def delta_win_b_column_width() -> int:
    return _DW_B_COL_W


def delta_win_columns_enabled() -> tuple[str, ...]:
    return DELTA_WIN_TXT_COLUMNS


def delta_win_block_width() -> int:
    w = 0
    if "a" in DELTA_WIN_TXT_COLUMNS:
        w += _DW_A_COL_W
    if "b" in DELTA_WIN_TXT_COLUMNS:
        if w:
            w += 1
        w += _DW_B_COL_W
    return w


def delta_win_data_header() -> str:
    parts = []
    if "a" in DELTA_WIN_TXT_COLUMNS:
        parts.append(f"{_DW_COL_LABEL_A:<{_DW_A_COL_W}}")
    if "b" in DELTA_WIN_TXT_COLUMNS:
        parts.append(f"{_DW_COL_LABEL_B:>{_DW_B_COL_W}}")
    return " ".join(parts)


def delta_win_row_part(sec: int, abs_delta: int, vols: dict[int, int], intraday_h: int,
        eligible: bool, artifact: dict) -> str:
    if not DELTA_WIN_TXT_COLUMNS:
        return ""
    at_checkpoint = sec in DELTA_WIN_CHECKPOINTS
    cells = []
    for col in DELTA_WIN_TXT_COLUMNS:
        w = _DW_A_COL_W if col == "a" else _DW_B_COL_W
        if not at_checkpoint:
            cells.append(_blank_cell(w))
        elif col == "a":
            if not eligible:
                cells.append(f"{'---':<{w}}")
            else:
                win = predict_delta_win_a_window(sec, abs_delta, intraday_h, artifact)
                if win is None:
                    cells.append(f"{'---':<{w}}")
                else:
                    p, lo, hi, n, expanded = win
                    cell = format_delta_win_a_cell(p, lo, hi, n, expanded)
                    cells.append(f"{cell:<{w}}")
        elif col == "b":
            if not eligible:
                cells.append(f"{'---':>{w}}")
            else:
                p = predict_delta_win_b(sec, abs_delta, vols, intraday_h, artifact)
                cells.append(f"{format_delta_win_b_cell(p):>{w}}")
    return " ".join(cells)


def delta_win_header_field(lines: list[str], key: str) -> str | None:
    prefix = f"  {key}:"
    for line in lines:
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
        if line.rstrip("\n") == "data:":
            break
    return None


def delta_win_txt_matches_artifact(lines: list[str], artifact: dict) -> bool:
    cp_raw = delta_win_header_field(lines, "delta_win_checkpoints")
    if cp_raw is None or ast.literal_eval(cp_raw) != list(artifact["checkpoints"]):
        return False
    if delta_win_header_field(lines, "delta_win_hour_bands_hash") != artifact["hour_bands_hash"]:
        return False
    if delta_win_header_field(lines, "delta_win_band_stratify") != artifact["delta_win_band_stratify"]:
        return False
    if int(delta_win_header_field(lines, "delta_win_lookup_max")) != int(artifact["delta_lookup_max"]):
        return False
    if int(delta_win_header_field(lines, "delta_win_window_half_base")) != int(artifact["delta_win_window_half_base"]):
        return False
    if int(delta_win_header_field(lines, "delta_win_window_expand_step")) != int(artifact["delta_win_window_expand_step"]):
        return False
    if int(delta_win_header_field(lines, "delta_win_window_min_samples")) != int(artifact["delta_win_window_min_samples"]):
        return False
    if int(delta_win_header_field(lines, "delta_win_model_version")) != int(artifact["model_version"]):
        return False
    return True


def delta_win_header_lines(artifact: dict) -> list[str]:
    return [
        f"  delta_win_model_version: {artifact['model_version']}",
        f"  delta_win_hour_bands_hash: {artifact['hour_bands_hash']}",
        f"  delta_win_band_stratify: {artifact['delta_win_band_stratify']}",
        f"  delta_win_status: {artifact['status']}",
        f"  delta_win_target: {artifact['target']}",
        f"  delta_win_label_source: {artifact['label_source']}",
        f"  delta_win_checkpoints: {artifact['checkpoints']}",
        f"  delta_win_training_samples: {artifact['training_sample_count']}",
        f"  delta_win_training_start_ts_min: {artifact['training_start_ts_min']}",
        f"  delta_win_training_start_ts_max: {artifact['training_start_ts_max']}",
        f"  delta_win_methods: [band, logistic]",
        f"  delta_win_lookup_max: {artifact['delta_lookup_max']}",
        f"  delta_win_window_half_base: {artifact['delta_win_window_half_base']}",
        f"  delta_win_window_expand_step: {artifact['delta_win_window_expand_step']}",
        f"  delta_win_window_min_samples: {artifact['delta_win_window_min_samples']}",
        f"  delta_win_txt_columns: {list(DELTA_WIN_TXT_COLUMNS)}",
    ]


def checkpoint_stale_in_vol_window(rows_by_sec: dict[int, dict], sec: int, window: int) -> bool:
    from src.vol_stats import vol_window_countdown_secs
    for s in vol_window_countdown_secs(sec, window):
        row = rows_by_sec.get(s)
        if row is None:
            raise Exception(f"missing sec {s} in round rows")
        if row["delta_stale"]:
            return True
    return False


def _row_eligible(sec: int, row: dict, rows_by_sec: dict[int, dict]) -> bool:
    if sec not in DELTA_WIN_CHECKPOINTS:
        return False
    if checkpoint_stale_in_vol_window(rows_by_sec, sec, max(VOLATILITY_WINDOWS_SEC)):
        return False
    if row["delta"] is None:
        return False
    for w in VOLATILITY_WINDOWS_SEC:
        if row["vols"].get(w) is None:
            return False
    return True


def delta_win_row_from_data(sec: int, row: dict, rows_by_sec: dict[int, dict], intraday_h: int,
        artifact: dict) -> str:
    eligible = _row_eligible(sec, row, rows_by_sec)
    vol_int = {w: row["vols"][w] for w in VOLATILITY_WINDOWS_SEC} if eligible else {w: 0 for w in VOLATILITY_WINDOWS_SEC}
    abs_delta = abs(row["delta"]) if row["delta"] is not None else 0
    return delta_win_row_part(sec, abs_delta, vol_int, intraday_h, eligible, artifact)
