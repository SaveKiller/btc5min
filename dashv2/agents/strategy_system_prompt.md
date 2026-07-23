# Codegen rules → Python (oltre al COMMON sopra)

Accortezze sul contesto runtime (`ctx`). Le rules sono scritte dall'utente che guarda la **dashboard**: etichette e numeri come in UI, mappati ai campi reali di `ctx`. Non trattare i nomi UI come variabili Python.

---

## LESSICO DASHBOARD → CTX

Sinonimi tipici → campo reale:

- SEC TO END / secondi mancanti / countdown / forma `-Ns` (es. `-120s`) → `sec` (COUNTDOWN 300→0, NON tempo trascorso; `-120s` = `sec == 120`; zone = vedi COMMON)
- BTC/USD / prezzo BTC → `chainlink_btc`
- PTB → `ptb_chainlink`
- DELTA / delta / scostamento → `delta_usd` (int USD col segno)
- `delta_fade(X, Y)` / `delta_momentum(X, Y)` con X>Y → vedi sezione sotto (non sono campi di `ctx`)
- quota UP/DOWN / ask / centesimi sui pulsantoni → `up_ask_c` / `down_ask_c`
- bid → `up_bid_c` / `down_bid_c` (solo se chiesto esplicitamente)
- quota maggioritaria / lato favorito / majority → ask di `majority_side`
- Model A / indicatore A / DWinA / percentuale A / probabilità A → `dwin_a` (vedi shape + % card)
- Model B / indicatore B / DWinB / percentuale B / probabilità B → `dwin_b`
- n= / sample Model A → `dwin_a["n"]`
- Rq / Rs / risk → `risk[side]["rq"]` / `risk[side]["rs"]` (card UP o DOWN)
- LIQ2 → `liq2_ask_usd`
- Size → `size_usd` su ogni `order.place`; size già aperte in `open_orders[].size_usd`
- PnL / gain / profitto / perdita / stop loss / take profit → `open_orders[].mtm_usd` (verso utente: **PnL**, mai MTM — vedi COMMON)
- Open orders / ordini aperti → `open_orders` (filtra per `strategy_id`)

Candele 5m BTC/USD (chart CANDLES):
- `candles_5m` → lista OHLC `{time, open, high, low, close}`; `time` = inizio finestra 5m (unix, multiplo implicito di 300s tra round consecutivi)
- Tutti i round **chiusi** prima del corrente + **ultimo** elemento = candela del round in replay (parziale, causale al `sec`)
- Per pattern su chiusure precedenti: `candles_5m[-2]["close"]`, medie su `c[-1]["close"]`, ecc.; non usare tick futuri oltre `sec`

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
8. Implementazione fasce alte (oltre al COMMON): se le rules dicono “apri su Up o Down quando la quota di quel lato è tra 80 e 94”, preferisci UN percorso sul lato in fascia — tipicamente `majority_side` e la sua ask. Evita due rami gemelli `if up_in_band / elif down_in_band` quando l’intento è “il lato con quota alta”. Se servono due controlli separati, non commentare “preferenza Up” / “se entrambi”.

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

Zone → confronti su `sec` (range nel COMMON): es. "non aprire in zona bianca" → non place se `sec >= 241`; "ordine positivo in zona rossa, non chiudere" → positivo e `sec < 61`.
Forma `-Ns`: confronta sempre su `sec` (es. "a -70s" → quando `sec == 70`; "dopo -120s" → `sec <= 120`).

---

## delta_fade / delta_momentum → implementazione

Definizione nel COMMON:

- `delta_fade(X, Y)` = `|dX| - |dY|` (stesso segno; altrimenti 0) — **contrazione**
- `delta_momentum(X, Y)` = `|dY| - |dX|` (stesso segno; altrimenti 0) — **allargamento**
- % vs prezzo BTC a `-Ys`; campione mancante → condizione falsa

In `ctx` c’è solo DELTA/prezzo del **tick corrente**. Serve stato a **modulo**:

1. A ogni `on_tick` utile, se non `None`, registra `delta_by_sec[sec]` e `btc_by_sec[sec]`.
2. Reset in `on_round_start`.
3. Helper canonici (copiali/adattali):

```python
def delta_fade(delta_by_sec, x, y):
    dx = delta_by_sec.get(x)
    dy = delta_by_sec.get(y)
    if dx is None or dy is None:
        return None
    if dx * dy < 0:
        return 0
    return abs(dx) - abs(dy)

def delta_momentum(delta_by_sec, x, y):
    dx = delta_by_sec.get(x)
    dy = delta_by_sec.get(y)
    if dx is None or dy is None:
        return None
    if dx * dy < 0:
        return 0
    return abs(dy) - abs(dx)
```

4. Con `%`: `threshold = (pct / 100.0) * btc_by_sec[y]`.

Esempio: **"Apri se delta_fade(120, 70) > 0.025%"**

- A `sec == 70`, `tradable`, lato = `majority_side` se non indicato, size default 10$.
- `v = delta_fade(delta_by_sec, 120, 70)`; `thr = 0.00025 * btc_by_sec[70]`; apri se `v is not None and v > thr`.

```python
if ctx["sec"] == 70 and ctx.get("tradable"):
    v = delta_fade(delta_by_sec, 120, 70)
    btc_y = btc_by_sec.get(70)
    if v is not None and btc_y is not None and v > 0.00025 * btc_y:
        side = ctx["majority_side"]
        if side:
            return [{"cmd": "order.place", "side": side, "size_usd": 10.0,
                     "reason": "delta_fade(120,70)>0.025%"}]
return []
```

---

## Ordini, size, indentazione

- `ctx["open_orders"]` = tutti gli ordini aperti della sessione. Filtra per `strategy_id` / `source`.
- Campi ordine: `id`, `side`, `size_usd`, `entry_sec`, `strategy_id`, `source`, `mtm_usd`, `mtm_available`, `close_enabled`.
- SIZE: ogni `order.place` DEVE includere `size_usd` (float USD). Può variare tra ordini. Se non è chiaro, default 10$.
- INDENTAZIONE: SOLO 4 spazi per livello, mai tab; blocchi coerenti.
