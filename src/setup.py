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
