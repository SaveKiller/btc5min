"""Generazione modulo Python analyze da testo rules (Cursor SDK)."""

from __future__ import annotations

import re
import tempfile

from dashv2.agents.cursor_client import call_model

_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

_CONTRACT = '''
Il modulo DEVE esportare:

def analyze_round(round_view: dict) -> dict:
    ...

Opzionale:

def reduce_results(per_round: list[dict]) -> str:
    ...  # Markdown aggregato IN ITALIANO; se assente il server usa un fallback

round_view (read-only, da build_round_view):
  market_start_ts: int
  hour_utc: int
  outcome: str | None
  ptb_chainlink: float
  final_chainlink: float
  fee_rate: float
  secs: list[int]          # secondi presenti, ordinati
  ticks: list[dict]        # un dict per sec, stesso ordine di secs
  orders: list[dict]       # SOLO se Analyze su simulation backtest
  strategy: dict           # SOLO se simulation: {id, name, version}

Chiavi tipiche di ogni tick:
  sec, recv_ts_ms, chainlink_btc, chainlink_stale,
  up_bid, up_ask, down_bid, down_ask, delta_usd, partial, gap,
  up_mid_c, down_mid_c, majority_side,
  vol, side_risk, dwin_a, dwin_b_pct

Chiavi tipiche di ogni order (se presente):
  id, side, entry_sec, exit_sec, size_usd, shares, avg_entry_price,
  pnl_usd, result (won|lost|closed), close_type (settlement|manual),
  reason, close_reason, entry_fee_usd, exit_fee_usd, entry_btc, exit_btc

analyze_round deve ritornare un dict JSON-serializzabile (metriche per-round).
Il runner mergea ok/error/market_start_ts/hour_utc sopra quel dict.

Vietato: rete, scrittura su disco, import arbitrari pesanti, rieseguire strategy.
Consentito: stdlib (+ numpy solo se già in env). Nessun side-effect I/O.
'''


def build_codegen_prompt(rules: str, system_prompt: str) -> str:
    return f"""Sei un generatore di codice Python per analyze stats su round Polymarket BTC Up/Down 5m.

CRITICO SULL'OUTPUT:
- Rispondi SOLO con il codice Python del modulo (preferibilmente in un blocco ```python)
- NON usare tool, NON creare o modificare file su disco
- NON descrivere cosa hai fatto: l'output deve ESSERE il codice, non un riepilogo
- Niente markdown fuori dal fence del codice
- Indentazione: SOLO 4 spazi per livello, mai tab; blocchi allineati in modo coerente

{_CONTRACT}

PRE-PROMPT / ACCORTEZZE DI SISTEMA (obbligatorie):
{system_prompt.strip()}

Regole dell'analyze scritte dall'utente:
---
{rules.strip()}
---

Genera il modulo completo che implementa queste regole con analyze_round (e reduce_results se serve aggregare Markdown).
"""


def extract_python_source(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip() + "\n"
    if "def analyze_round" in text:
        return text.strip() + "\n"
    raise RuntimeError("no Python source found in model output")


def validate_analyze_source(source: str) -> None:
    compile(source, "<analyze>", "exec")
    ns: dict = {}
    exec(compile(source, "<analyze>", "exec"), ns, ns)
    if "analyze_round" not in ns or not callable(ns["analyze_round"]):
        raise RuntimeError("generated module missing callable analyze_round")


def generate_analyze_module(
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
            validate_analyze_source(source)
            return source
        except SyntaxError as e:
            last_err = e
    raise last_err
