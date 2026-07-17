import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_REQUIRED = (
    "data_dir", "history_dir", "host", "port", "chart_previous_candles",
    "default_order_size_usd", "stall_reconnect_sec", "engine_plugin",
)


def load_config() -> dict:
    raw = json.loads((_ROOT / "setup.json").read_text(encoding="utf-8"))
    for key in _REQUIRED:
        if key not in raw: raise Exception(f"missing setup.json key: {key}")
    engine_plugin = raw["engine_plugin"]
    if engine_plugin is not None:
        engine_plugin = str(engine_plugin)
        if engine_plugin not in ("replay", "live"):
            raise Exception(f"invalid engine_plugin: {engine_plugin}")
    data_dir = (_ROOT / raw["data_dir"]).resolve()
    history_dir = (_ROOT / raw["history_dir"]).resolve()
    if not data_dir.is_dir(): raise Exception(f"data_dir not found: {data_dir}")
    history_dir.mkdir(parents=True, exist_ok=True)
    return {
        "root": _ROOT, "data_dir": data_dir, "history_dir": history_dir,
        "host": str(raw["host"]), "port": int(raw["port"]),
        "chart_previous_candles": int(raw["chart_previous_candles"]),
        "default_order_size_usd": float(raw["default_order_size_usd"]),
        "stall_reconnect_sec": float(raw["stall_reconnect_sec"]),
        "engine_plugin": engine_plugin,
    }
