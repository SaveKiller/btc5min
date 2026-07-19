Accortezze sul contesto runtime (ctx):

PRINCIPIO: le rules sono scritte dall'utente che guarda la **dashboard**. Etichette, percentuali e numeri vanno letti come in UI e mappati ai campi reali di `ctx`. Non trattare i nomi UI (Model A, Rq, zona rossa, LIQ2…) come variabili Python.

---

## LESSICO DASHBOARD → CTX

Sinonimi tipici → campo reale:

- SEC TO END / secondi mancanti / countdown → `sec` (COUNTDOWN 300→0, NON tempo trascorso)
- zone colorate → range su `sec` (vedi sotto)
- BTC/USD / prezzo BTC → `chainlink_btc`
- PTB → `ptb_chainlink`
- DELTA / delta / scostamento → `delta_usd` (int USD col segno)
- quota UP/DOWN / ask / centesimi sui pulsantoni → `up_ask_c` / `down_ask_c`
- bid → `up_bid_c` / `down_bid_c` (solo se chiesto esplicitamente)
- quota maggioritaria / lato favorito / majority → ask di `majority_side`
- Model A / indicatore A / DWinA / percentuale A / probabilità A → `dwin_a` (vedi shape + % card)
- Model B / indicatore B / DWinB / percentuale B / probabilità B → `dwin_b`
- n= / sample Model A → `dwin_a["n"]`
- Rq / Rs / risk → `risk[side]["rq"]` / `risk[side]["rs"]` (card UP o DOWN)
- LIQ2 → `liq2_ask_usd`
- Size → `size_usd` su ogni `order.place`; size già aperte in `open_orders[].size_usd`
- PNL / gain / profitto / perdita / MTM → `open_orders[].mtm_usd`
- Open orders / ordini aperti → `open_orders` (filtra per `strategy_id`)

`vol` (V30/V60/…) è in ctx ma **non** in UI oggi: usalo solo se le rules lo nominano esplicitamente.
OUTCOME: anti-spoiler — non usarlo durante il round.

---

## Regole di disambiguazione

1. LATO IMPLICITO: se le rules non dicono UP/DOWN, Model A/B e Rq/Rs si riferiscono alla **card del lato dell'azione** (ingresso → `majority_side`; gestione ordine → `order["side"]`).
2. % MODEL A/B COME IN CARD (non il grezzo TXT):
   - `raw = dwin_a["p_win_pct"]` (o B); `ref = dwin_ref_side`
   - se `side == ref` → `raw`, altrimenti `100 - raw`
   - confronti tipo `>= 75` usano questo intero 0–100; `None` / linette → condizione falsa
3. SHAPE: `dwin_a` / `dwin_b` sono dict (o `None`), **mai** float. Vietato `float(dwin_a)` / `float(dwin_b)`.
4. Rq/Rs: interi o `None`. In UI `Rq 9`+`Rs 9` sul lato non-favorito è “blank”: non usarli come segnale forte salvo richiesta esplicita.
5. QUOTA SENZA ASK/BID: se dice solo “quota” / soglie in centesimi, intendi SEMPRE l'ask (`up_ask_c` / `down_ask_c`). Bid solo se esplicito.
6. Apri o chiudi solo se `tradable` è True.
7. `mtm_usd` può essere `None`: non confrontarlo con numeri senza check; usa anche `mtm_available` / `close_enabled` prima di chiudere.

Snippet canonico (copialo/adattalo, non reinventarlo):

```python
def dwin_pct_for_side(ctx, side, key):  # key "a"|"b"
    block = ctx.get("dwin_a") if key == "a" else ctx.get("dwin_b")
    raw = None if not block else block.get("p_win_pct")
    ref = ctx.get("dwin_ref_side")
    if raw is None or ref is None:
        return None
    return raw if side == ref else 100 - raw
```

Esempio: "Model A >= 75% o Model B >= 75%" in ingresso sul majority:
`a = dwin_pct_for_side(ctx, majority_side, "a"); b = dwin_pct_for_side(ctx, majority_side, "b"); ok = (a is not None and a >= 75) or (b is not None and b >= 75)`.

---

## Tempo e zone colorate

- Nelle rules l'utente può (e deve poter) dire solo “zona bianca/verde/…”: è terminologia ufficiale. Tu le traduci in confronti su `sec`; non serve che le rules ripetano i secondi.
- `ctx["sec"]` è un COUNTDOWN: secondi MANCANTI alla scadenza (300 → 0). Esempio: "non entrare se mancano meno di 5 secondi" → `if sec < 5`. SBAGLIATO: `sec >= 300-5`.
- Zone colorate = tempo mancante:
  - zona bianca: 300s–241s
  - zona verde: 240s–181s
  - zona blu/azzurra: 180s–121s
  - zona gialla/arancio: 120s–61s
  - zona rossa: 60s–0s
  Esempio: "non aprire in zona bianca" → non place se `sec >= 241`.
  Esempio: "ordine positivo in zona rossa, non chiudere" → positivo e `sec < 61`.

---

## Ordini, size, indentazione

- `ctx["open_orders"]` = tutti gli ordini aperti della sessione. Filtra per `strategy_id` / `source`.
- Campi ordine: `id`, `side`, `size_usd`, `entry_sec`, `strategy_id`, `source`, `mtm_usd`, `mtm_available`, `close_enabled`.
- SIZE: ogni `order.place` DEVE includere `size_usd` (float USD). Può variare tra ordini. Se non è chiaro, default 10$.
- INDENTAZIONE: SOLO 4 spazi per livello, mai tab; blocchi coerenti.
