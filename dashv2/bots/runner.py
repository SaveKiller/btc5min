"""Caricamento e dispatch moduli strategy .py (importlib + cache mtime)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from dashv2.strategies import load_strategy, module_path


class StrategyRunner:
    """Cache moduli strategy_{id}_v{tip}.py; fan-out hook → azioni."""

    def __init__(self, strategies_root: Path) -> None:
        self.root = strategies_root
        self._cache: dict[str, tuple[float, ModuleType]] = {}

    def sync(self, strategy_ids: list[str]) -> None:
        keep = set(strategy_ids)
        for sid in list(self._cache):
            if sid not in keep:
                self._cache.pop(sid, None)
        for sid in strategy_ids:
            self._load(sid)

    def _load(self, strategy_id: str) -> ModuleType:
        data = load_strategy(self.root, strategy_id)
        path = module_path(self.root, strategy_id, data["version"])
        if not path.is_file():
            raise Exception(f"strategy module not found: {path}")
        mtime = path.stat().st_mtime
        cached = self._cache.get(strategy_id)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        name = f"dashv2_strategy_{strategy_id}_v{data['version']}"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        self._cache[strategy_id] = (mtime, mod)
        print(f"bot: loaded strategy module id={strategy_id} v{data['version']}", flush=True)
        return mod

    def dispatch(self, hook: str, strategy_ids: list[str], base_ctx: dict) -> list[tuple[str, dict]]:
        """Chiama hook su ogni strategy; ritorna (strategy_id, action). Skip su eccezione."""
        out: list[tuple[str, dict]] = []
        for sid in strategy_ids:
            try:
                mod = self._load(sid)
                fn = getattr(mod, hook)
                ctx = {**base_ctx, "strategy_id": sid}
                actions = fn(ctx) or []
                for act in actions:
                    out.append((sid, act))
            except Exception as e:
                print(f"bot: strategy {sid} {hook} error: {e}", flush=True)
        return out
