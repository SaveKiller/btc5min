import json
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_AGENTS = _ROOT / "agents"
_COMMON_PROMPT_PATH = _AGENTS / "common_prompt.md"
_STRATEGY_SYSTEM_PROMPT_PATH = _AGENTS / "strategy_system_prompt.md"
_STATS_SYSTEM_PROMPT_PATH = _AGENTS / "stats_system_prompt.md"
_AGENT_SYSTEM_PROMPT_PATH = _AGENTS / "agent_system_prompt.md"
_CODED_RULES_PROMPT_PATH = _AGENTS / "coded_rules_prompt.md"
_REQUIRED = (
    "data_dir", "history_dir", "host", "port",
    "default_order_size_usd", "stats_workers", "stall_reconnect_sec", "engine_plugin",
    "cursor_label", "cursor_models", "agent_cursor_label", "all_tabs", "hide_tabs",
)

UI_TAB_KEYS = (
    "candles", "accounts", "strategy", "backtest", "backtest_analysis", "round_chat",
)

_CMD_UI_TAB: dict[str, str] = {}
for _cmd in (
    "bot.list", "bot.set_active",
    "strategy.list", "strategy.create", "strategy.update", "strategy.clone",
    "strategy.delete", "strategy.load", "strategy.unload",
):
    _CMD_UI_TAB[_cmd] = "strategy"
for _cmd in (
    "stats.backtest.start", "stats.job.cancel",
    "stats.simulation.list", "stats.simulation.load", "stats.simulation.delete",
):
    _CMD_UI_TAB[_cmd] = "backtest"
for _cmd in (
    "stats.analyze.start", "stats.analyze.list", "stats.analyze.delete",
    "stats.chat.send", "stats.chat.history", "stats.chat.clear", "stats.rules.apply",
):
    _CMD_UI_TAB[_cmd] = "backtest_analysis"
for _cmd in (
    "agent.chat.send", "agent.chat.history", "agent.rules.apply",
    "agent.executions.list", "agent.session.select", "agent.session.delete",
):
    _CMD_UI_TAB[_cmd] = "round_chat"


def parse_all_tabs(raw) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise Exception("all_tabs must be a non-empty list")
    out = [str(entry) for entry in raw]
    if out != list(UI_TAB_KEYS):
        raise Exception(f"all_tabs must match {list(UI_TAB_KEYS)!r}")
    return out


def parse_hide_tabs(raw) -> list[str]:
    if not isinstance(raw, list):
        raise Exception("hide_tabs must be a list")
    out: list[str] = []
    for entry in raw:
        key = str(entry)
        if key not in UI_TAB_KEYS:
            raise Exception(f"invalid hide_tabs entry: {key!r}")
        if key in out:
            raise Exception(f"duplicate hide_tabs entry: {key!r}")
        out.append(key)
    if len(out) >= len(UI_TAB_KEYS):
        raise Exception("hide_tabs cannot hide every tab")
    return out


def visible_ui_tabs(hidden: list[str]) -> list[str]:
    hidden_set = set(hidden)
    return [key for key in UI_TAB_KEYS if key not in hidden_set]


def cmd_ui_tab(cmd: str) -> str | None:
    return _CMD_UI_TAB.get(cmd)


def ui_tab_allows(cmd: str, enabled_tabs: set[str]) -> bool:
    need = cmd_ui_tab(cmd)
    if need is None:
        return True
    return need in enabled_tabs


def resolve_cursor_model(cursor_label: str, cursor_models: list[dict]) -> dict:
    """Risolve cursor_label → entry {id, label, params}."""
    for entry in cursor_models:
        if entry["label"] == cursor_label:
            return entry
    raise Exception(f"cursor_label not found in cursor_models: {cursor_label!r}")


def _read_prompt(path: Path, label: str) -> str:
    if not path.is_file():
        raise Exception(f"{label} not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def reload_common_prompt() -> str:
    """Rilegge dashv2/agents/common_prompt.md (dominio condiviso)."""
    return _read_prompt(_COMMON_PROMPT_PATH, "common prompt")


def _with_common(specific: str) -> str:
    return f"{reload_common_prompt()}\n\n{specific.strip()}"


def reload_strategy_codegen_system_prompt() -> str:
    """COMMON + dashv2/agents/strategy_system_prompt.md (hot-reload pre-codegen)."""
    return _with_common(_read_prompt(_STRATEGY_SYSTEM_PROMPT_PATH, "strategy system prompt"))


def reload_stats_codegen_system_prompt() -> str:
    """COMMON + dashv2/agents/stats_system_prompt.md (hot-reload pre-codegen analyze)."""
    return _with_common(_read_prompt(_STATS_SYSTEM_PROMPT_PATH, "stats system prompt"))


def reload_agent_system_prompt() -> str:
    """COMMON + dashv2/agents/agent_system_prompt.md."""
    return _with_common(_read_prompt(_AGENT_SYSTEM_PROMPT_PATH, "agent system prompt"))


def reload_coded_rules_prompt() -> str:
    """COMMON + dashv2/agents/coded_rules_prompt.md (placeholder {{SOURCE}} ancora da sostituire)."""
    return _with_common(_read_prompt(_CODED_RULES_PROMPT_PATH, "coded rules prompt"))


def load_config() -> dict:
    raw = json.loads((_ROOT / "setup.json").read_text(encoding="utf-8"))
    for key in _REQUIRED:
        if key not in raw: raise Exception(f"missing setup.json key: {key}")
    engine_plugin = raw["engine_plugin"]
    if engine_plugin is not None:
        engine_plugin = str(engine_plugin)
        if engine_plugin not in ("replay", "live"):
            raise Exception(f"invalid engine_plugin: {engine_plugin}")
    cursor_models = raw["cursor_models"]
    if not cursor_models:
        raise Exception("cursor_models must not be empty")
    labels = [e["label"] for e in cursor_models]
    if len(labels) != len(set(labels)):
        raise Exception("cursor_models labels must be unique")
    for e in cursor_models:
        if "id" not in e or "label" not in e or "params" not in e:
            raise Exception(f"invalid cursor_models entry: {e!r}")
    cursor_label = str(raw["cursor_label"])
    cursor_model = resolve_cursor_model(cursor_label, cursor_models)
    agent_cursor_label = str(raw["agent_cursor_label"])
    agent_cursor_model = resolve_cursor_model(agent_cursor_label, cursor_models)
    system_prompt = reload_strategy_codegen_system_prompt()
    stats_system_prompt = reload_stats_codegen_system_prompt()
    data_dir = (_ROOT / raw["data_dir"]).resolve()
    history_dir = (_ROOT / raw["history_dir"]).resolve()
    if not data_dir.is_dir(): raise Exception(f"data_dir not found: {data_dir}")
    history_dir.mkdir(parents=True, exist_ok=True)
    hide_tabs = parse_hide_tabs(raw["hide_tabs"])
    parse_all_tabs(raw["all_tabs"])
    ui_tabs = visible_ui_tabs(hide_tabs)
    port = int(raw["port"])
    if "DASHV2_PORT" in os.environ:
        port = int(os.environ["DASHV2_PORT"])
    return {
        "root": _ROOT, "data_dir": data_dir, "history_dir": history_dir,
        "host": str(raw["host"]), "port": port,
        "default_order_size_usd": float(raw["default_order_size_usd"]),
        "stats_workers": int(raw["stats_workers"]),
        "stall_reconnect_sec": float(raw["stall_reconnect_sec"]),
        "engine_plugin": engine_plugin,
        "hide_tabs": hide_tabs,
        "ui_tabs": ui_tabs,
        "cursor_label": cursor_label,
        "cursor_models": cursor_models,
        "cursor_model": cursor_model,
        "agent_cursor_label": agent_cursor_label,
        "agent_cursor_model": agent_cursor_model,
        "strategy_codegen_system_prompt": system_prompt,
        "stats_codegen_system_prompt": stats_system_prompt,
    }
