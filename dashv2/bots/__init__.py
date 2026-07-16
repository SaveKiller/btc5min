"""Discovery plugin bot in dashv2/bots/."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

_BOTS_DIR = Path(__file__).resolve().parent


def list_bot_infos() -> list[dict]:
    out: list[dict] = []
    for path in sorted(_BOTS_DIR.glob("*_bot.py")):
        mod = importlib.import_module(f"dashv2.bots.{path.stem}")
        out.append({
            "id": mod.BOT_ID, "name": mod.BOT_NAME, "kind": mod.BOT_KIND,
            "config_file": getattr(mod, "CONFIG_FILE", None),
        })
    return out


def load_bot(bot_id: str):
    """Carica plugin + config JSON del bot."""
    for path in sorted(_BOTS_DIR.glob("*_bot.py")):
        mod = importlib.import_module(f"dashv2.bots.{path.stem}")
        if mod.BOT_ID != bot_id:
            continue
        config = {}
        cfg_name = getattr(mod, "CONFIG_FILE", None)
        if cfg_name:
            config = json.loads((_BOTS_DIR / cfg_name).read_text(encoding="utf-8"))
        return mod.create_bot(config)
    raise Exception(f"bot not found: {bot_id}")
