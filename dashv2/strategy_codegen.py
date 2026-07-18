"""Generazione modulo Python strategy da testo rules (Cursor SDK)."""

from __future__ import annotations

import re
import tempfile

from dashv2.cursor_client import call_model

_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

_CONTRACT = '''
Il modulo DEVE esportare esattamente queste tre funzioni (firma fissa):

def on_round_start(ctx: dict) -> list[dict]:
    ...

def on_tick(ctx: dict) -> list[dict]:
    ...

def on_round_end(ctx: dict) -> list[dict]:
    ...

ctx (input tipico su ogni tick):
  sec, tradable, chainlink_btc, delta_usd,
  up_ask_c, up_bid_c, down_ask_c, down_bid_c, up_mid_c, down_mid_c,
  majority_side, vol, risk, dwin_ref_side, dwin_a, dwin_b,
  open_orders (list of order dicts), strategy_id (str), bot_active (bool)

Azioni ammesse (lista restituita dalle hook):
  {"cmd": "order.place", "side": "Up"|"Down", "size_usd": float, "reason": str opzionale}
  {"cmd": "order.close", "order_id": str, "reason": str opzionale}
  {"cmd": "order.cancel", "order_id": str, "reason": str opzionale}

Il campo reason (consigliato) spiega in una riga perché apri/chiudi (es. "majority 80c x2s", "TP +10%").

SIZE (obbligatorio su ogni order.place):
  - size_usd è un float USD scelto dalla strategy per quel singolo ordine
  - può essere diversa tra un ordine e l'altro nello stesso round (piccola/grande/scalare)
  - non esiste una size globale fissa: ogni place porta la propria size_usd
  - le size già piazzate si leggono da open_orders[].size_usd (filtra per strategy_id)

Se non c'è nulla da fare, ritorna [].
'''


def build_codegen_prompt(rules: str, system_prompt: str) -> str:
    return f"""Sei un generatore di codice Python per strategie di trading Polymarket BTC Up/Down 5m.

CRITICO SULL'OUTPUT:
- Rispondi SOLO con il codice Python del modulo (preferibilmente in un blocco ```python)
- NON usare tool, NON creare o modificare file su disco
- NON descrivere cosa hai fatto: l'output deve ESSERE il codice, non un riepilogo
- Niente markdown fuori dal fence del codice
- Indentazione: SOLO 4 spazi per livello, mai tab; blocchi allineati in modo coerente

{_CONTRACT}

PRE-PROMPT / ACCORTEZZE DI SISTEMA (obbligatorie):
{system_prompt.strip()}

Regole della strategia scritte dall'utente:
---
{rules.strip()}
---

Genera il modulo completo che implementa queste regole usando on_tick (e se serve on_round_start / on_round_end).
"""


def extract_python_source(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip() + "\n"
    # Fallback: tutto il testo se sembra già Python
    if "def on_tick" in text:
        return text.strip() + "\n"
    raise RuntimeError("no Python source found in model output")


def validate_module_source(source: str) -> None:
    compile(source, "<strategy>", "exec")
    ns: dict = {}
    exec(compile(source, "<strategy>", "exec"), ns, ns)
    if "on_tick" not in ns or not callable(ns["on_tick"]):
        raise RuntimeError("generated module missing callable on_tick")


def generate_strategy_module(
    rules: str, *, model_id: str, params: dict[str, str], system_prompt: str,
    max_attempts: int,
) -> str:
    """Chiama Cursor, estrae e valida il sorgente Python.

    Su SyntaxError/IndentationError ritenta fino a max_attempts senza propagare
    l'errore intermedio (il popup UI arriva solo se falliscono tutti i tentativi).
    """
    prompt = build_codegen_prompt(rules, system_prompt)
    last_err: BaseException | None = None
    for _ in range(max_attempts):
        with tempfile.TemporaryDirectory(prefix="dashv2-cursor-") as tmp:
            raw = call_model(prompt, model_id=model_id, params=params, cwd=tmp)
        source = extract_python_source(raw)
        try:
            validate_module_source(source)
            return source
        except SyntaxError as e:
            last_err = e
    raise last_err
