import json
from pathlib import Path

_SETUP_PATH = Path(__file__).resolve().parent.parent / "setup.json"
_raw = json.loads(_SETUP_PATH.read_text(encoding="utf-8"))


def _req(key: str):
    if key not in _raw:
        raise Exception(f"setup.json missing required key: {key}")
    return _raw[key]


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
