"""Caricamento e dispatch moduli strategy .py (importlib + cache mtime)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from dashv2.strategies import module_path, version_snapshot, load_strategy


class StrategyRunner:
    """Cache moduli strategy_{id}_v{N}.py; fan-out hook → azioni."""

    def __init__(self, strategies_root: Path) -> None:
        self.root = strategies_root
        self._cache: dict[str, tuple[float, int, ModuleType]] = {}
        self._versions: dict[str, int] = {}

    def sync(self, active: list[dict]) -> None:
        """active = [{id, version}, …] — una versione per strategy_id."""
        self._versions = {e["id"]: int(e["version"]) for e in active}
        keep = set(self._versions)
        for sid in list(self._cache):
            if sid not in keep:
                self._cache.pop(sid, None)
        for sid, ver in self._versions.items():
            self._load(sid, ver)

    def _load(self, strategy_id: str, version: int) -> ModuleType:
        data = load_strategy(self.root, strategy_id)
        version_snapshot(data, version)
        path = module_path(self.root, strategy_id, version)
        if not path.is_file():
            raise Exception(f"strategy module not found: {path}")
        mtime = path.stat().st_mtime
        cached = self._cache.get(strategy_id)
        if cached is not None and cached[0] == mtime and cached[1] == version:
            return cached[2]
        name = f"dashv2_strategy_{strategy_id}_v{version}"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        self._cache[strategy_id] = (mtime, version, mod)
        print(f"bot: loaded strategy module id={strategy_id} v{version}", flush=True)
        return mod

    def dispatch(self, hook: str, strategy_ids: list[str], base_ctx: dict) -> list[tuple[str, dict]]:
        """Chiama hook su ogni strategy; ritorna (strategy_id, action). Skip su eccezione."""
        out: list[tuple[str, dict]] = []
        for sid in strategy_ids:
            try:
                ver = self._versions[sid]
                mod = self._load(sid, ver)
                fn = getattr(mod, hook)
                ctx = {**base_ctx, "strategy_id": sid, "strategy_version": ver}
                actions = fn(ctx) or []
                for act in actions:
                    out.append((sid, act))
            except Exception as e:
                print(f"bot: strategy {sid} {hook} error: {e}", flush=True)
        return out
