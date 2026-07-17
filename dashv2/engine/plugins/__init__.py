"""Discovery plugin Engine."""

from __future__ import annotations


def list_engine_plugin_ids() -> list[str]:
    return ["replay", "live"]
