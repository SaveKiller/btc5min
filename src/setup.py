import json
from pathlib import Path

_SETUP_PATH = Path(__file__).resolve().parent.parent / "setup.json"
_raw = json.loads(_SETUP_PATH.read_text(encoding="utf-8"))


def _req(key: str):
    if key not in _raw:
        raise Exception(f"setup.json missing required key: {key}")
    return _raw[key]


TICKS_ROOT = str(_req("ticks_root"))

OUTCOME_WAIT_SEC = float(_req("outcome_wait_sec"))
GAMMA_PATCH_WAIT_SEC = float(_req("gamma_patch_wait_sec"))
GAMMA_POLL_SEC = float(_req("gamma_poll_sec"))
PREP_AHEAD_SEC = float(_req("prep_ahead_sec"))
STALL_RECONNECT_SEC = float(_req("stall_reconnect_sec"))
PING_INTERVAL_SEC = float(_req("ping_interval_sec"))
RECONNECT_COOLDOWN_SEC = float(_req("reconnect_cooldown_sec"))
RATE_LIMIT_BACKOFF_SEC = float(_req("rate_limit_backoff_sec"))

_raw_windows = _req("volatility_windows_sec")
if not isinstance(_raw_windows, list) or len(_raw_windows) == 0:
    raise Exception("volatility_windows_sec must be a non-empty list")
_windows = [int(w) for w in _raw_windows]
if len(set(_windows)) != len(_windows):
    raise Exception("volatility_windows_sec contains duplicates")
for w in _windows:
    if w <= 0:
        raise Exception(f"volatility_windows_sec contains invalid value: {w}")
VOLATILITY_WINDOWS_SEC = sorted(_windows)
VOLATILITY_MIN_CHANGES = int(_req("volatility_min_changes"))
if VOLATILITY_MIN_CHANGES <= 0:
    raise Exception("volatility_min_changes must be > 0")

RISK_MODEL_VERSION = int(_req("risk_model_version"))
RISK_TARGET = str(_req("risk_target"))
RISK_LABEL_SOURCE = str(_req("risk_label_source"))
RISK_PTB_SOURCE = str(_req("risk_ptb_source"))
RISK_PRIMARY_VOL_WINDOW_SEC = int(_req("risk_primary_vol_window_sec"))
if RISK_PRIMARY_VOL_WINDOW_SEC not in VOLATILITY_WINDOWS_SEC:
    raise Exception("risk_primary_vol_window_sec must be in volatility_windows_sec")
RISK_MIN_VOL_COVERAGE_RATIO = float(_req("risk_min_vol_coverage_ratio"))
if not (0.0 < RISK_MIN_VOL_COVERAGE_RATIO <= 1.0):
    raise Exception("risk_min_vol_coverage_ratio must be in (0, 1]")
RISK_TIE_BAND = float(_req("risk_tie_band"))
if RISK_TIE_BAND <= 0:
    raise Exception("risk_tie_band must be > 0")
_raw_buckets = _req("risk_probability_buckets")
if not isinstance(_raw_buckets, list) or len(_raw_buckets) != 8:
    raise Exception("risk_probability_buckets must be a list of 8 ascending thresholds")
RISK_PROBABILITY_BUCKETS = [float(x) for x in _raw_buckets]
for i in range(1, len(RISK_PROBABILITY_BUCKETS)):
    if RISK_PROBABILITY_BUCKETS[i] <= RISK_PROBABILITY_BUCKETS[i - 1]:
        raise Exception("risk_probability_buckets must be strictly ascending")
RISK_FLIP_HYSTERESIS_C = int(_req("risk_flip_hysteresis_c"))
RISK_FLIP_PERSIST_SEC = int(_req("risk_flip_persist_sec"))
if RISK_FLIP_HYSTERESIS_C <= 0 or RISK_FLIP_PERSIST_SEC <= 0:
    raise Exception("risk_flip_hysteresis_c and risk_flip_persist_sec must be > 0")

DELTA_WIN_MODEL_VERSION = int(_req("delta_win_model_version"))
DELTA_WIN_CHECKPOINTS_START = int(_req("delta_win_checkpoints_start"))
DELTA_WIN_CHECKPOINTS_END = int(_req("delta_win_checkpoints_end"))
DELTA_WIN_CHECKPOINTS_STEP = int(_req("delta_win_checkpoints_step"))
if DELTA_WIN_CHECKPOINTS_STEP <= 0:
    raise Exception("delta_win_checkpoints_step must be > 0")
if DELTA_WIN_CHECKPOINTS_START <= DELTA_WIN_CHECKPOINTS_END:
    raise Exception("delta_win_checkpoints_start must be > delta_win_checkpoints_end")
_dw_cps: list[int] = []
_s = DELTA_WIN_CHECKPOINTS_START
while _s >= DELTA_WIN_CHECKPOINTS_END:
    _dw_cps.append(_s)
    _s -= DELTA_WIN_CHECKPOINTS_STEP
DELTA_WIN_CHECKPOINTS = tuple(_dw_cps)
DELTA_WIN_MODEL_PATH = str(_req("delta_win_model_path"))
DELTA_WIN_WINDOW_HALF_BASE = int(_req("delta_win_window_half_base"))
DELTA_WIN_WINDOW_EXPAND_STEP = int(_req("delta_win_window_expand_step"))
DELTA_WIN_WINDOW_MIN_SAMPLES = int(_req("delta_win_window_min_samples"))
if DELTA_WIN_WINDOW_HALF_BASE <= 0:
    raise Exception("delta_win_window_half_base must be > 0")
if DELTA_WIN_WINDOW_EXPAND_STEP <= 0:
    raise Exception("delta_win_window_expand_step must be > 0")
if DELTA_WIN_WINDOW_MIN_SAMPLES <= 0:
    raise Exception("delta_win_window_min_samples must be > 0")
_raw_dw_txt_cols = _req("delta_win_txt_columns")
if not isinstance(_raw_dw_txt_cols, list) or len(_raw_dw_txt_cols) == 0:
    raise Exception("delta_win_txt_columns must be a non-empty list")
DELTA_WIN_TXT_COLUMNS = tuple(str(x) for x in _raw_dw_txt_cols)
for _col in DELTA_WIN_TXT_COLUMNS:
    if _col not in ("a", "b"):
        raise Exception(f"delta_win_txt_columns invalid entry: {_col!r}")
