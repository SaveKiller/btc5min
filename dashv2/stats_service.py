"""Chat Stats + apply rules (codegen analyze) — thread dedicato, non legato a session_id replay."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dashv2.config import reload_stats_codegen_system_prompt
from dashv2.agents.cursor_client import call_model
from dashv2.agents.stats_codegen import generate_analyze_module
from dashv2.stats_modules import (
    create_analyze,
    list_analyzes,
    load_analyze,
    set_analyze_rules,
    write_analyze_module,
)

_THREAD_TAIL = 30
_RULES_FENCE_RE = re.compile(r"```rules\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

_CHAT_SYSTEM = """Sei l'assistente Stats della dashboard BTC Up/Down 5m.
LINGUA: rispondi SEMPRE in italiano (anche se l'utente scrive in inglese).
L'utente chiede statistica/analisi su una o più simulation backtest (con orders).
Il server applicherà automaticamente le rules (codegen + batch su ogni simulation
selezionata): NON dire di premere Applica, NON spiegare il flusso interno.

DECISIONI / CHIARIMENTI (obbligatorio):
- NON fare domande all'utente. Non attendere conferme.
- Se per procedere ti servirebbero scelte (ambiguità, scope, metriche, filtri, aggregazioni),
  adotta subito le risposte raccomandate e procedi.
- Nel messaggio breve: una riga che elenca le scelte assunte (es. «Assumo: …»),
  poi al massimo un’altra frase; niente elenco di domande.

Rispondi in 1-2 frasi brevi in italiano (inclusa la riga scelte se serve), poi metti le rules in:

```rules
...testo rules concise in italiano...
```

Le rules usano round_view['orders'] e round_view['strategy']; lo stesso modulo
analyze verrà eseguito su ciascuna simulation selezionata e i report verranno
mostrati insieme per il confronto.
Il report Markdown arriverà dopo come messaggio successivo nel thread (anche quello in italiano).
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _thread_path(history_dir: Path) -> Path:
    d = history_dir / "stats"
    d.mkdir(parents=True, exist_ok=True)
    return d / "thread.json"


def load_stats_thread(history_dir: Path) -> list[dict]:
    path = _thread_path(history_dir)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["messages"])


def save_stats_thread(history_dir: Path, messages: list[dict]) -> None:
    path = _thread_path(history_dir)
    payload = {"updated_at_utc": _utc_now_iso(), "messages": messages}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def clear_stats_thread(history_dir: Path) -> None:
    """Svuota la chat Analyze."""
    save_stats_thread(history_dir, [])


def append_stats_message(history_dir: Path, role: str, content: str) -> dict:
    messages = load_stats_thread(history_dir)
    msg = {"role": role, "content": content, "ts": _utc_now_iso()}
    messages.append(msg)
    save_stats_thread(history_dir, messages)
    return msg


def extract_proposed_rules(reply: str) -> dict | None:
    m = _RULES_FENCE_RE.search(reply)
    if not m:
        return None
    return {"rules": m.group(1).strip()}


class StatsService:
    """Orchestrazione chat Stats + apply rules → codegen modulo analyze."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.history_dir = Path(cfg["history_dir"])

    def run_turn(self, user_text: str, simulations: list[dict]) -> dict:
        append_stats_message(self.history_dir, "user", user_text)
        thread = load_stats_thread(self.history_dir)[-_THREAD_TAIL:]
        blob = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in thread)
        analyzes = list_analyzes(self.history_dir)
        prompt = (
            f"{_CHAT_SYSTEM}\n\n"
            f"=== SIMULATIONS SELEZIONATE ===\n{json.dumps(simulations, ensure_ascii=False)}\n\n"
            f"=== ANALYZE ESISTENTI ===\n{json.dumps(analyzes, ensure_ascii=False)}\n\n"
            f"=== CRONOLOGIA ===\n{blob}\n\n"
            "Rispondi all'ultimo messaggio utente."
        )
        model = self.cfg["agent_cursor_model"]
        with tempfile.TemporaryDirectory(prefix="dashv2-stats-") as td:
            raw = call_model(
                prompt, model_id=model["id"], params=model["params"], cwd=td,
                reject_meta=False,
            )
        reply = raw.strip()
        proposed = extract_proposed_rules(reply)
        display = _RULES_FENCE_RE.sub("", reply).strip()
        if not display:
            display = "Ok, lancio l'analisi…"
        msg = append_stats_message(self.history_dir, "assistant", display)
        return {"message": msg, "proposed_rules": proposed}

    def apply_rules(self, rules: str, analyze_id: str | None, name: str | None) -> dict:
        """Codegen + salva modulo; crea analyze se analyze_id assente."""
        rules = rules.strip()
        if not rules:
            raise Exception("rules required")
        if analyze_id:
            data = set_analyze_rules(self.history_dir, analyze_id, rules)
        else:
            data = create_analyze(self.history_dir, name, rules)
            analyze_id = data["id"]
        system_prompt = reload_stats_codegen_system_prompt()
        self.cfg["stats_codegen_system_prompt"] = system_prompt
        model = self.cfg["cursor_model"]
        print(f"stats codegen analyze {analyze_id} with {model['label']}", flush=True)
        source = generate_analyze_module(
            rules, model_id=model["id"], params=model["params"],
            system_prompt=system_prompt, max_attempts=3,
        )
        write_analyze_module(self.history_dir, analyze_id, source)
        data = load_analyze(self.history_dir, analyze_id)
        return {"ok": True, "analyze": {
            "id": data["id"], "name": data["name"], "rules": data["rules"],
            "module_file": data.get("module_file"),
            "created_at_utc": data["created_at_utc"], "updated_at_utc": data["updated_at_utc"],
        }}
