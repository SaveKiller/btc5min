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
  sec, tradable, chainlink_btc, delta_usd, ptb_chainlink, liq2_ask_usd,
  up_ask_c, up_bid_c, down_ask_c, down_bid_c, up_mid_c, down_mid_c,
  majority_side, vol,
  dwin_ref_side: "Up"|"Down"|None,
  dwin_a: {"p_win_pct": int|None, "n": int|None} | None,
  dwin_b: {"p_win_pct": int|None} | None,
  risk: {"Up": {"rq": int|None, "rs": int|None}, "Down": {"rq": int|None, "rs": int|None}},
  open_orders (list of order dicts), strategy_id (str), bot_active (bool)

MAPPING UI (obbligatorio):
  - Model A / indicatore A / DWinA / percentuale A → dwin_a (MAI float(dwin_a))
  - Model B / indicatore B / DWinB / percentuale B → dwin_b (MAI float(dwin_b))
  - % Model A/B come in card: raw=p_win_pct; se side!=dwin_ref_side → 100-raw; confronti su 0..100
  - Rq/Rs → risk[side]["rq"|"rs"]; LIQ2 → liq2_ask_usd; PTB → ptb_chainlink

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


_CODED_SECTIONS = ("Apertura:", "Chiusura:", "Vincoli:")


def build_coded_rules_prompt(source: str) -> str:
    return f"""Leggi SOLO il modulo Python qui sotto (strategia Polymarket BTC Up/Down 5m).
Riscrivi ciò che il codice FA davvero, per un utente della dashboard che NON programma.

CRITICO SULL'OUTPUT:
- Rispondi SOLO con testo nelle tre sezioni obbligatorie sotto
- Niente markdown fences, niente codice, niente introduzioni
- Linguaggio COLLOQUIALE e naturale (italiano), come spiegheresti le regole a voce
- Usa termini della dashboard: quota Up/Down, lato maggioritario, Model A / Model B, PnL, size, zone colorate (bianca/verde/…), secondi mancanti, centesimi, percentuali
- VIETATO citare variabili/identificatori del codice o del contesto (es. ctx, mtm_usd, size_usd, majority_side, dwin_a, open_orders, sec, tradable, order.place, …)
- I numeri (soglie, secondi, percentuali, size in $) devono restare espliciti e non ambigui
- Non inventare regole assenti dal codice; non copiare docstring/commenti se contraddicono il flusso
- Non usare un template fisso di trading: elenca solo ciò che il codice implementa
- SOLO logica SPECIFICA di questa strategia. NON includere controlli generici di infrastruttura che valgono sempre e non distinguono la strategia, ad esempio:
  - "mercato operabile" / tradable
  - bot attivo / bot_active
  - close_enabled / mtm_available / "MTM disponibile"
  - presenza di campi None / "se i dati ci sono"
  Questi non sono regole di trading: se il mercato non è operabile la strategia non può fare nulla comunque.

TEMPO / COUNTDOWN (obbligatorio, errore frequente):
- Nel codice il campo secondi è un COUNTDOWN: secondi MANCANTI alla scadenza (tipicamente 300 → 0), NON il tempo trascorso dall'inizio round
- Zone colorate (terminologia UI): bianca 300–241, verde 240–181, blu 180–121, gialla/arancio 120–61, rossa 60–0 (valori = secondi mancanti)
- Confronti tipo ">= 241" / "< 61" vanno descritti come countdown o zona, MAI come "primi N secondi del round" / "dal secondo N in poi"
- Esempio CORRETTO: "non apre in zona bianca (quando mancano ancora almeno 241 secondi)"
- Esempio SBAGLIATO: "entro i primi 240 secondi" / "dal secondo 241 in poi non apre più"

Schema obbligatorio (heading esatti):

Apertura:
- ...

Chiusura:
- ...

Vincoli:
- ...

Se una sezione non ha condizioni rilevanti nel codice, metti un solo bullet "- (nessuna)".

Esempio di tono (NON copiare i contenuti, solo lo stile):
- Apri con size 100$ quando la quota maggioritaria resta tra 80c e 94c per almeno 2 secondi e Model A o Model B è almeno al 78%.

Modulo Python:
---
{source.strip()}
---
"""


def extract_coded_rules(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:\w+)?\s*\n(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    return t + ("\n" if t and not t.endswith("\n") else "")


def validate_coded_rules(text: str) -> None:
    for heading in _CODED_SECTIONS:
        if heading not in text:
            raise RuntimeError(f"coded_rules missing section: {heading}")


def generate_coded_rules(
    source: str, *, model_id: str, params: dict[str, str], max_attempts: int = 2,
) -> str:
    """Seconda pass: dal Python alle coded_rules schematiche."""
    prompt = build_coded_rules_prompt(source)
    last_err: BaseException | None = None
    for _ in range(max_attempts):
        with tempfile.TemporaryDirectory(prefix="dashv2-coded-") as tmp:
            raw = call_model(prompt, model_id=model_id, params=params, cwd=tmp)
        text = extract_coded_rules(raw)
        try:
            validate_coded_rules(text)
            return text
        except RuntimeError as e:
            last_err = e
    raise last_err
