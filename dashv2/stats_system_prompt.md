Accortezze sul contesto analyze (`round_view`):

PRINCIPIO: le rules descrivono una statistica / pattern sul round già chiuso.
`analyze_round` riceve una vista read-only; non ci sono ordini né bot.

---

## CONTRATO MODULO

Obbligatorio:

```python
def analyze_round(round_view: dict) -> dict:
    ...
```

Opzionale (Markdown aggregato su tutti i round del job):

```python
def reduce_results(per_round: list[dict]) -> str:
    ...
```

Se `reduce_results` manca, il server usa un fallback Markdown minimale.

Ritorno di `analyze_round`: dict JSON-serializzabile (metriche). Il runner aggiunge
`ok`, `error`, `market_start_ts`, `hour_utc`.

---

## ROUND_VIEW KEYS (da `build_round_view`)

- `market_start_ts` — int Unix start del round
- `hour_utc` — int 0..23
- `outcome` — str (es. `"Up"` / `"Down"`) o None
- `ptb_chainlink` — float PTB
- `final_chainlink` — float prezzo finale
- `fee_rate` — float fee CLOB
- `secs` — `list[int]` secondi presenti, ordinati crescente
- `ticks` — `list[dict]` allineati a `secs`

Chiavi tipiche di ogni tick:
`sec`, `recv_ts_ms`, `chainlink_btc`, `chainlink_stale`,
`up_bid`, `up_ask`, `down_bid`, `down_ask`, `delta_usd`, `partial`, `gap`,
`up_mid_c`, `down_mid_c`, `majority_side`,
`vol`, `side_risk`, `dwin_a`, `dwin_b_pct`

`sec` è COUNTDOWN (300→0), secondi mancanti alla scadenza.

---

## DIVIETI

- Vietato: rete, scrittura su disco, tool, side-effect I/O
- Vietato: import arbitrari pesanti; solo stdlib (+ numpy se già in env)
- Nessun accesso a path, socket, subprocess

---

## INDENTAZIONE

- SOLO 4 spazi per livello, mai tab
- Blocchi allineati in modo coerente
