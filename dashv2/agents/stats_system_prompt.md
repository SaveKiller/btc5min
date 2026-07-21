Accortezze sul contesto analyze (`round_view`):

PRINCIPIO: le rules descrivono una statistica / pattern sul round già chiuso.
`analyze_round` riceve una vista read-only; non esegue strategy né piazzza ordini.

LINGUA: tutto il testo utente-facing (rules, titoli e corpo di `reduce_results` Markdown)
deve essere in **italiano**. Chiavi/metriche nel dict di `analyze_round` restano in inglese.

Se il job Analyze è legato a una o più **simulation** backtest SQLite, `round_view` include anche:
- `orders` — lista ordini chiusi di quel round (stesso ordine del motore)
- `strategy` — `{id, name, version}` della strategy usata nel backtest

Con più simulation selezionate lo stesso modulo viene eseguito su ciascuna; i report
Markdown (una sezione per simulation) compaiono insieme nel thread per il confronto.

Senza simulation: niente `orders` / `strategy` (solo market data).

---

## CONTRATO MODULO

Obbligatorio:

```python
def analyze_round(round_view: dict) -> dict:
    ...
```

Opzionale (Markdown aggregato su tutti i round del job — **in italiano**):

```python
def reduce_results(per_round: list[dict]) -> str:
    ...
```

Se `reduce_results` manca, il server usa un fallback Markdown minimale.

Ritorno di `analyze_round`: dict JSON-serializzabile (metriche; chiavi in inglese). Il runner aggiunge
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
- `orders` — (solo con simulation) `list[dict]` ordini chiusi; chiavi tipiche:
  `id`, `side`, `entry_sec`, `exit_sec`, `size_usd`, `shares`, `avg_entry_price`,
  `pnl_usd`, `result` (`won`/`lost`/`closed`), `close_type` (`settlement`/`manual`),
  `reason`, `close_reason`, fees, BTC entry/exit
- `strategy` — (solo con simulation) `{id, name, version}`

Chiavi tipiche di ogni tick:
`sec`, `recv_ts_ms`, `chainlink_btc`, `chainlink_stale`,
`up_bid`, `up_ask`, `down_bid`, `down_ask`, `delta_usd`, `partial`, `gap`,
`up_mid_c`, `down_mid_c`, `majority_side`,
`vol`, `side_risk`, `dwin_a`, `dwin_b_pct`

`sec` è COUNTDOWN (300→0), secondi mancanti alla scadenza.

Esempio rules con simulation: “considera solo round con almeno 2 ordini e aggrega
PnL del secondo ordine”.

---

## DIVIETI

- Vietato: rete, scrittura su disco, tool, side-effect I/O
- Vietato: import arbitrari pesanti; solo stdlib (+ numpy se già in env)
- Nessun accesso a path, socket, subprocess
- Vietato: rieseguire strategy o chiamare OrderEngine

---

## INDENTAZIONE

- SOLO 4 spazi per livello, mai tab
- Blocchi allineati in modo coerente
